from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')

# Configuración de la base de datos
if os.environ.get('DATABASE_URL'):
    # Configuración para PostgreSQL en producción
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    # Configuración para SQLite en desarrollo
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Asegurar que la carpeta de uploads exista
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120))
    bio = db.Column(db.Text, default='')
    profile_pic = db.Column(db.String(200))
    posts = db.relationship('Post', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    followers = db.relationship('Follow',
                            foreign_keys='Follow.follower_id',
                            backref=db.backref('follower', lazy='joined'),
                            lazy='dynamic',
                            cascade='all, delete-orphan')
    following = db.relationship('Follow',
                            foreign_keys='Follow.followed_id',
                            backref=db.backref('followed', lazy='joined'),
                            lazy='dynamic',
                            cascade='all, delete-orphan')
    groups = db.relationship('Group', secondary='group_members', backref='members')
    created_groups = db.relationship('Group', backref='creator')

class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    posts = db.relationship('Post', backref='group', lazy=True)

group_members = db.Table('group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True)
)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_path = db.Column(db.String(200))
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    likes = db.relationship('Like', backref='post', lazy=True)
    comments = db.relationship('Comment', backref='post', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        posts = Post.query.order_by(Post.timestamp.desc()).all()
        return render_template('index.html', posts=posts)
    return redirect(url_for('login'))

@app.route('/explorar')
def explore():
    users = User.query.all()
    return render_template('explore.html', users=users)

@app.route('/perfil/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=user, posts=posts)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        bio = request.form.get('bio', '')
        profile_pic = request.files.get('profile_pic')
        
        if profile_pic and allowed_file(profile_pic.filename):
            filename = secure_filename(profile_pic.filename)
            profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.profile_pic = 'uploads/' + filename
        
        current_user.bio = bio
        db.session.commit()
        flash('¡Perfil actualizado exitosamente!')
        return redirect(url_for('profile', username=current_user.username))
    
    return render_template('edit_profile.html')

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    user_to_follow = User.query.filter_by(username=username).first_or_404()
    
    if user_to_follow == current_user:
        flash('No puedes seguirte a ti mismo.')
        return redirect(url_for('profile', username=username))
    
    # Verificar si ya sigue al usuario
    if not current_user.following.filter_by(followed_id=user_to_follow.id).first():
        follow = Follow(follower=current_user, followed=user_to_follow)
        db.session.add(follow)
        db.session.commit()
        flash(f'¡Ahora sigues a {username}!')
    else:
        flash('Ya sigues a este usuario.')
    
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    user_to_unfollow = User.query.filter_by(username=username).first_or_404()
    
    if user_to_unfollow == current_user:
        flash('No puedes dejar de seguirte a ti mismo.')
        return redirect(url_for('profile', username=username))
    
    # Buscar y eliminar la relación de seguimiento
    follow = current_user.following.filter_by(followed_id=user_to_unfollow.id).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f'Has dejado de seguir a {username}.')
    else:
        flash('No estabas siguiendo a este usuario.')
    
    return redirect(url_for('profile', username=username))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('El nombre de usuario ya está en uso.')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('El correo electrónico ya está registrado.')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.password_hash = generate_password_hash(password)
        db.session.add(user)
        db.session.commit()
        flash('¡Registro exitoso! Por favor inicia sesión.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Usuario o contraseña incorrectos.')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.')
    return redirect(url_for('login'))

@app.route('/post', methods=['POST'])
@login_required
def create_post():
    content = request.form['content']
    image = request.files.get('image')
    image_path = None
    
    if image and allowed_file(image.filename):
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_path = 'uploads/' + filename
    
    post = Post(content=content, image_path=image_path, author=current_user)
    db.session.add(post)
    db.session.commit()
    flash('¡Post creado exitosamente!')
    return redirect(url_for('index'))

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if like:
        db.session.delete(like)
        db.session.commit()
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        db.session.commit()
    
    return redirect(request.referrer or url_for('index'))

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    
    if content:
        comment = Comment(content=content, author=current_user, post=post)
        db.session.add(comment)
        db.session.commit()
        flash('¡Comentario agregado!')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    
    if comment.author != current_user:
        flash('No tienes permiso para eliminar este comentario.')
        return redirect(url_for('index'))
    
    db.session.delete(comment)
    db.session.commit()
    flash('Comentario eliminado.')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/groups')
@login_required
def groups():
    user_groups = current_user.groups
    other_groups = Group.query.filter(~Group.members.contains(current_user)).all()
    return render_template('groups.html', user_groups=user_groups, other_groups=other_groups)

@app.route('/group/<int:group_id>')
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    posts = Post.query.filter_by(group_id=group_id).order_by(Post.timestamp.desc()).all()
    return render_template('group.html', group=group, posts=posts)

@app.route('/create_group', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if name:
            group = Group(name=name, description=description, creator=current_user)
            group.members.append(current_user)
            db.session.add(group)
            db.session.commit()
            flash('¡Grupo creado exitosamente!')
            return redirect(url_for('view_group', group_id=group.id))
    
    return render_template('create_group.html')

@app.route('/join_group/<int:group_id>', methods=['POST'])
@login_required
def join_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        group.members.append(current_user)
        db.session.commit()
        flash(f'Te has unido al grupo {group.name}')
    return redirect(url_for('view_group', group_id=group.id))

@app.route('/leave_group/<int:group_id>', methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user in group.members:
        group.members.remove(current_user)
        db.session.commit()
        flash(f'Has dejado el grupo {group.name}')
    return redirect(url_for('groups'))

@app.route('/create_group_post/<int:group_id>', methods=['POST'])
@login_required
def create_group_post(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user not in group.members:
        flash('Debes ser miembro del grupo para publicar')
        return redirect(url_for('view_group', group_id=group_id))
    
    content = request.form.get('content')
    if content:
        image = request.files.get('image')
        image_path = None
        
        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            image_path = os.path.join('uploads', filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        post = Post(content=content, author=current_user, group_id=group_id, image_path=image_path)
        db.session.add(post)
        db.session.commit()
        flash('¡Publicación creada!')
    
    return redirect(url_for('view_group', group_id=group_id))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
