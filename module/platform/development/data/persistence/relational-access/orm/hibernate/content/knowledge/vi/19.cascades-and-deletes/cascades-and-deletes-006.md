# Rủi ro truyền REMOVE qua quan hệ nhiều với nhiều

Trong Hibernate/JPA, quan hệ **nhiều với nhiều** (`@ManyToMany`) thường biểu diễn việc nhiều entity cùng tham chiếu tới nhiều entity khác. Ví dụ một `User` có nhiều `Role` và một `Role` được gán cho nhiều `User`; một `Post` có nhiều `Tag` và một `Tag` có thể xuất hiện ở nhiều bài viết; một `Student` đăng ký nhiều `Course` và mỗi khóa học có nhiều sinh viên.

Các entity ở hai đầu thường có **vòng đời độc lập**. Khi một người dùng bị xóa, các role dùng chung vẫn phải tồn tại. Khi một bài viết bị xóa, các tag còn được bài viết khác sử dụng vẫn phải tồn tại. Vì vậy, truyền `CascadeType.REMOVE` qua quan hệ nhiều với nhiều có thể gây hậu quả nghiêm trọng: thao tác xóa một entity lan sang các entity đích được chia sẻ, dẫn tới xóa dữ liệu ngoài ý muốn hoặc lỗi ràng buộc khóa ngoại.

Điểm quan trọng cần phân biệt:

- **Xóa liên kết**: xóa hàng trong join table để hai entity không còn liên hệ với nhau.
- **Xóa entity**: xóa chính hàng của entity ở bảng đích.
- **Cascade REMOVE**: lan truyền thao tác remove của ORM từ entity nguồn sang entity liên quan theo mapping.
- **Database ON DELETE CASCADE**: quy tắc ở database khi xóa hàng được tham chiếu; trong quan hệ nhiều với nhiều, nó thường dùng để dọn hàng join table.

Bài học tập trung vào rủi ro khi cascade REMOVE qua `@ManyToMany`, cách thiết kế mapping an toàn, quản lý hai phía của quan hệ, thay thế bằng association entity khi cần và phân biệt cascade ORM với cascade ở database.

## 1. Quan hệ nhiều với nhiều được lưu như thế nào?

Một quan hệ nhiều với nhiều thường được biểu diễn bằng **join table** chứa khóa ngoại tới hai bảng entity.

Ví dụ `User` và `Role`:

~~~mermaid
erDiagram
    USERS ||--o{ USER_ROLES : has
    ROLES ||--o{ USER_ROLES : assigned
    USERS {
        bigint id PK
        varchar username
    }
    ROLES {
        bigint id PK
        varchar name
    }
    USER_ROLES {
        bigint user_id FK
        bigint role_id FK
    }
~~~

Schema minh họa:

~~~sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE roles (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_user
        FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_user_roles_role
        FOREIGN KEY (role_id) REFERENCES roles(id)
);
~~~

Một hàng `user_roles` chỉ thể hiện liên kết giữa một user và một role. Nó không phải bản sao của User hoặc Role.

Ví dụ:

| user_id | role_id |
| ---: | ---: |
| 10 | 1 |
| 10 | 2 |
| 11 | 1 |

User 10 có Role 1 và 2. User 11 cũng có Role 1. Nếu xóa User 10, hệ thống thường chỉ cần xóa hai hàng liên kết có `user_id = 10`; Role 1 vẫn được User 11 dùng và Role 2 có thể còn được các user khác hoặc hệ thống khác tham chiếu.

**Join table chính là nơi lưu quan hệ; nó không làm cho hai entity ở hai đầu trở thành chủ sở hữu vòng đời của nhau.**

## 2. Mapping @ManyToMany an toàn

Một mapping hai chiều phổ biến:

~~~java
import jakarta.persistence.*;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @ManyToMany
    @JoinTable(
        name = "user_roles",
        joinColumns = @JoinColumn(name = "user_id"),
        inverseJoinColumns = @JoinColumn(name = "role_id")
    )
    private Set<Role> roles = new HashSet<>();

    protected User() {}

    public User(String username) {
        this.username = username;
    }

    public void addRole(Role role) {
        if (roles.add(role)) {
            role.addUserInternal(this);
        }
    }

    public void removeRole(Role role) {
        if (roles.remove(role)) {
            role.removeUserInternal(this);
        }
    }

    public Set<Role> getRoles() {
        return Set.copyOf(roles);
    }
}
~~~

Phía Role:

~~~java
import jakarta.persistence.*;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "roles")
public class Role {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @ManyToMany(mappedBy = "roles")
    private Set<User> users = new HashSet<>();

    protected Role() {}

    public Role(String name) {
        this.name = name;
    }

    void addUserInternal(User user) {
        users.add(user);
    }

    void removeUserInternal(User user) {
        users.remove(user);
    }

    public Set<User> getUsers() {
        return Set.copyOf(users);
    }
}
~~~

Trong ví dụ:

- `User.roles` là **owning side** của association vì khai báo `@JoinTable`.
- `Role.users` là phía đối ứng với `mappedBy = "roles"`.
- Tên `mappedBy` là tên thuộc tính Java ở phía owning side, không phải tên cột SQL.
- Không có `CascadeType.REMOVE` ở cả hai phía.
- Thêm hoặc bỏ liên kết được thực hiện bằng helper method để giữ hai collection Java nhất quán.

Nếu chỉ cần một chiều, có thể bỏ collection ngược `Role.users` và dùng một `@ManyToMany` duy nhất. Không cần tạo quan hệ hai chiều chỉ vì database có hai khóa ngoại.

### 2.1. Không khai báo CascadeType.ALL một cách mặc định

Mapping sau rất dễ gây rủi ro:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Role> roles = new HashSet<>();
~~~

`CascadeType.ALL` bao gồm `PERSIST`, `MERGE`, `REMOVE`, `REFRESH` và `DETACH`. Vì vậy, `ALL` không chỉ có nghĩa “lưu các liên kết”. Nó còn truyền thao tác remove tới entity liên quan.

Với Role được chia sẻ giữa nhiều User, xóa một User có thể dẫn tới yêu cầu xóa cả Role. Đối với các entity dùng chung như Role, Tag, Category hoặc Course, thường không nên cascade toàn bộ vòng đời từ entity này sang entity kia.

### 2.2. Cascade không phải điều kiện để lưu join table

Sau khi hai entity đã tồn tại:

~~~java
User user = em.find(User.class, userId);
Role role = em.find(Role.class, roleId);

user.addRole(role);

em.flush();
~~~

Hibernate có thể ghi hàng liên kết vào `user_roles` theo mapping. Không cần cascade PERSIST hoặc REMOVE sang Role chỉ để tạo association row.

Nếu User hoặc Role mới, cần quyết định rõ entity nào được tạo bởi use case. Với entity đích dùng chung, thường tạo/lưu nó bằng thao tác riêng rồi mới gán liên kết.

## 3. Cascade REMOVE nguy hiểm ở điểm nào?

`CascadeType.REMOVE` nói rằng khi entity nguồn được remove, thao tác remove được lan truyền tới entity đích của association theo mapping. Cơ chế này có ý nghĩa với những quan hệ mà entity con **thực sự phụ thuộc vòng đời** vào entity cha, ví dụ một `Order` sở hữu các `OrderLine` chỉ có ý nghĩa trong đơn hàng.

Nhưng với quan hệ nhiều với nhiều, các entity ở hai đầu thường có thể được chia sẻ. Xóa một đầu không đồng nghĩa xóa đầu còn lại.

Ví dụ không an toàn:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    @ManyToMany(cascade = CascadeType.REMOVE)
    private Set<Role> roles = new HashSet<>();
}
~~~

Giả sử:

~~~text
User A ───── Role ADMIN
User B ───── Role ADMIN
User C ───── Role VIEWER
~~~

Nếu xóa User A mà REMOVE được cascade sang Role ADMIN, provider có thể cố xóa Role ADMIN dù User B vẫn đang tham chiếu role đó. Hệ quả có thể là:

- Xóa mất role dùng chung, làm mất quyền của User B.
- Gặp lỗi khóa ngoại do hàng join table của User B vẫn tham chiếu Role ADMIN.
- Phát sinh chuỗi xóa ngoài phạm vi mà use case ban đầu dự định.
- Làm dữ liệu domain không còn nhất quán, dù transaction cuối cùng rollback vì constraint.

Kết quả SQL chính xác và thời điểm lỗi phụ thuộc provider, mapping, thứ tự action và database. Nhưng **thiết kế đã đặt sai hướng vòng đời**: User không sở hữu vòng đời của Role dùng chung.

### 3.1. Rủi ro khi cascade REMOVE ở cả hai phía

Nếu cả User.roles và Role.users đều cascade REMOVE, đồ thị có thể dẫn thao tác xóa đi qua nhiều User và Role liên quan:

~~~text
Remove User A
    ↓
Remove Role ADMIN
    ↓
Remove các User liên quan tới ADMIN
    ↓
Remove các Role liên quan tới những User đó
    ↓
...
~~~

Provider có thể theo dõi identity để tránh xử lý lặp vô hạn, nhưng điều đó không làm ý nghĩa nghiệp vụ trở nên an toàn. Thao tác xóa có thể lan rất rộng, xóa nhầm nhiều entity dùng chung hoặc vướng constraint.

**Không cấu hình REMOVE hai chiều để “đảm bảo xóa sạch quan hệ”.** Việc dọn join table là nhiệm vụ khác với xóa các entity ở hai đầu.

### 3.2. JPA portability: REMOVE trên ManyToMany không phải mapping di động

Theo quy tắc Jakarta Persistence, tùy chọn cascade `REMOVE` chỉ nên được áp dụng cho association `@OneToOne` và `@OneToMany`. Ứng dụng portable **không được dựa vào cascade REMOVE trên các loại quan hệ khác**, bao gồm `@ManyToMany` và `@ManyToOne`.

Một provider cụ thể có thể chấp nhận mapping và thực thi theo extension/behavior riêng, nhưng code khi đó không còn portable giữa các JPA provider và có thể tạo hậu quả xóa dữ liệu nghiêm trọng.

Vì thế, dù một cấu hình thử nghiệm chạy được trên một phiên bản Hibernate, vẫn không nên dùng `CascadeType.REMOVE` hoặc `CascadeType.ALL` trên `@ManyToMany`.

## 4. Xóa liên kết khác với xóa entity

Đây là điểm quan trọng nhất khi làm việc với many-to-many.

### 4.1. Bỏ một Role khỏi User

~~~java
User user = em.find(User.class, userId);
Role role = em.find(Role.class, roleId);

user.removeRole(role);

em.flush();
~~~

Nếu `User.roles` là owning side, Hibernate có thể xóa hàng association tương ứng:

~~~sql
DELETE FROM user_roles
WHERE user_id = ? AND role_id = ?;
~~~

Hàng trong bảng `roles` vẫn còn. User vẫn tồn tại. Chỉ liên kết giữa hai entity bị bỏ.

### 4.2. Xóa User

~~~java
User user = em.find(User.class, userId);
em.remove(user);
~~~

Với mapping many-to-many thông thường không cascade REMOVE, provider xử lý association rows liên quan để có thể xóa User mà không xóa Role. SQL về mặt ý nghĩa có thể tương đương:

~~~sql
DELETE FROM user_roles
WHERE user_id = ?;

DELETE FROM users
WHERE id = ?;
~~~

Role rows vẫn tồn tại. Thứ tự và hình thức SQL thực tế do provider/database quyết định; foreign key và database cascade cũng có thể tham gia.

### 4.3. Xóa Role

Nếu thực sự muốn xóa một Role khỏi hệ thống, đó là một use case riêng:

~~~java
Role role = em.find(Role.class, roleId);
// Xác định và dọn các association tới role theo thiết kế.
em.remove(role);
~~~

Cần bảo đảm các hàng join table không còn tham chiếu Role, hoặc có FK/database rule được thiết kế để dọn chúng. Đồng thời phải kiểm tra Role còn được dùng bởi user, policy hoặc thành phần khác hay không.

**Không biến việc xóa User thành lý do xóa Role.** Quyết định xóa entity dùng chung phải thuộc một use case nghiệp vụ riêng.

## 5. Owning side và mappedBy không quyết định cascade ownership

Trong mapping:

~~~java
@ManyToMany
@JoinTable(name = "user_roles")
private Set<Role> roles;
~~~

`User.roles` là owning side của **association mapping**. Điều đó có nghĩa Hibernate dựa vào phía này để ghi liên kết vào join table.

Nó không có nghĩa:

- User sở hữu vòng đời Role.
- Role phải bị xóa khi User bị xóa.
- Cascade REMOVE được phép hoặc an toàn.
- Bảng Role phụ thuộc vào bảng User.

Tương tự, `mappedBy` trên Role chỉ đánh dấu phía inverse của association. Nó không có nghĩa Role “không được quản lý” hoặc không thể bị xóa độc lập.

Ba khái niệm cần tách biệt:

| Khái niệm | Câu hỏi |
| --- | --- |
| Owning side JPA | Phía nào điều khiển ghi association/join table? |
| Cascade | Thao tác entity nào được lan truyền qua association? |
| Domain lifecycle ownership | Entity nào quyết định tạo, sửa và xóa entity khác theo nghiệp vụ? |

Một owning side có thể quản lý join table mà không có bất kỳ cascade REMOVE nào.

### 5.1. Sửa cả hai collection Java

Với quan hệ hai chiều, helper method nên đồng bộ hai phía:

~~~java
public void addRole(Role role) {
    if (roles.add(role)) {
        role.addUserInternal(this);
    }
}

public void removeRole(Role role) {
    if (roles.remove(role)) {
        role.removeUserInternal(this);
    }
}
~~~

Nếu chỉ sửa inverse collection `Role.users` mà không sửa owning side `User.roles`, thay đổi có thể không được ghi vào join table như mong muốn. Nếu chỉ sửa owning side, SQL association có thể đúng nhưng object graph trong RAM vẫn không nhất quán.

Helper method giúp giảm sai sót; không nên expose collection mutable để mọi nơi tùy ý sửa.

## 6. Ví dụ an toàn: xóa User nhưng giữ Role

Một service minh họa:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void deleteUser(Long userId) {
        User user = em.find(User.class, userId);

        if (user == null) {
            return;
        }

        em.remove(user);
    }
}
~~~

Mapping User–Role không cascade REMOVE. Khi remove User, provider quản lý association rows cần thiết theo mapping. Các Role vẫn tồn tại và có thể được User khác sử dụng.

Trong một số schema hoặc mapping phức tạp, việc xóa entity có thể cần xử lý association rõ hơn, nhất là khi có join table tùy chỉnh, nhiều quan hệ hoặc database constraint. Điều quan trọng là **không cascade remove tới Role dùng chung**.

### 6.1. Kiểm tra kết quả trong database

Sau khi transaction commit:

~~~sql
SELECT * FROM users WHERE id = 10;

SELECT * FROM roles WHERE id = 1;

SELECT * FROM user_roles WHERE user_id = 10;
~~~

Kết quả mong muốn trong use case xóa User 10:

- User 10 không còn.
- Các hàng association có user_id 10 không còn.
- Role 1 vẫn còn nếu chưa có use case riêng xóa Role.
- Các association của User khác tới Role 1 vẫn còn.

Kiểm tra này mô tả kết quả nghiệp vụ; SQL cụ thể Hibernate phát có thể khác.

## 7. Database ON DELETE CASCADE không giống CascadeType.REMOVE

Hai cơ chế cùng có chữ “cascade” nhưng hoạt động ở hai tầng khác nhau.

| Cơ chế | Tầng | Ý nghĩa |
| --- | --- | --- |
| `CascadeType.REMOVE` | JPA/Hibernate ORM | Khi remove entity nguồn, provider lan thao tác remove tới entity đích |
| `ON DELETE CASCADE` | Database FK | Khi hàng được tham chiếu bị xóa, database tự xóa các hàng con tham chiếu FK đó |
| Xóa association row | Join table mapping/SQL | Xóa liên kết giữa hai entity, giữ entity ở hai đầu |

### 7.1. ON DELETE CASCADE thường chỉ dọn join rows

Có thể khai báo FK của join table:

~~~sql
ALTER TABLE user_roles
ADD CONSTRAINT fk_user_roles_user
FOREIGN KEY (user_id)
REFERENCES users(id)
ON DELETE CASCADE;
~~~

Khi một hàng `users` bị xóa, database có thể tự xóa các hàng `user_roles` tham chiếu tới user đó.

Điều này **không xóa hàng `roles`**. Hướng cascade là từ hàng được tham chiếu `users` tới các hàng con `user_roles` chứa FK; Role không phải con của User trong cấu trúc FK đó.

Tương tự, FK `user_roles.role_id REFERENCES roles(id) ON DELETE CASCADE` có thể dọn association rows khi xóa Role, nhưng không xóa User.

### 7.2. Không nhầm với ORM cascade sang entity đích

Nếu dùng `CascadeType.REMOVE` từ User sang Role, Hibernate đang được yêu cầu xóa entity Role. Nếu dùng FK ON DELETE CASCADE trên `user_roles.user_id`, database chỉ dọn hàng join table phụ thuộc vào User.

**Đối tượng bị xóa khác nhau hoàn toàn.** Đối với many-to-many chia sẻ, mục tiêu thường là xóa association rows chứ không xóa entity ở đầu bên kia.

### 7.3. Hibernate @OnDelete

Hibernate có annotation extension như `@OnDelete(action = OnDeleteAction.CASCADE)` trong một số mapping để yêu cầu/diễn đạt database-level cascade qua foreign key. Nó không đồng nghĩa với `CascadeType.REMOVE` và không biến entity đích thành con có vòng đời bị xóa theo ORM.

Cần kiểm tra DDL thực tế, migration và database đang dùng. Khi database tự dọn hàng, persistence context/cache có thể cần được xử lý phù hợp nếu ứng dụng đã nạp những association rows hoặc entity liên quan.

## 8. Vì sao ManyToMany thường không dùng orphanRemoval?

`orphanRemoval = true` được thiết kế cho những quan hệ `@OneToOne` hoặc `@OneToMany` có entity con phụ thuộc vòng đời vào cha. `@ManyToMany` không có semantics orphan removal portable tương tự.

Ví dụ:

~~~java
@ManyToMany(orphanRemoval = true) // Không phải mapping JPA hợp lệ/portable.
private Set<Tag> tags;
~~~

Khi một Post bỏ Tag, Tag có thể còn được nhiều Post khác sử dụng. Việc bỏ liên kết không chứng minh Tag trở thành “orphan” cần xóa.

Thao tác đúng thường là xóa association row:

~~~java
post.removeTag(tag);
~~~

Tag entity vẫn tồn tại.

Nếu muốn xóa các Tag không còn được Post nào sử dụng, đó là một **quy trình dọn dữ liệu riêng**: phải xác định không còn tham chiếu ở bất kỳ nơi nào, xử lý concurrency và xóa có chủ đích. Không nên dùng orphanRemoval hoặc cascade REMOVE trên many-to-many để giả định việc đó tự xảy ra.

## 9. Khi nào nên chuyển ManyToMany thành association entity?

Một `@ManyToMany` đơn giản phù hợp khi quan hệ chỉ là một liên kết thuần. Nhưng nhiều quan hệ có thuộc tính và vòng đời riêng:

- User được gán Role vào thời điểm nào, bởi ai?
- Student đăng ký Course với trạng thái ENROLLED, DROPPED hay COMPLETED.
- Post được gắn Tag bởi người dùng nào và lúc nào?
- User có Role trong một tổ chức cụ thể, kèm thời hạn hoặc phạm vi.

Khi association có dữ liệu riêng, nên mô hình hóa **association entity** thay vì một join table ẩn sau `@ManyToMany`.

### 9.1. UserRole là entity riêng

~~~java
@Entity
@Table(
    name = "user_roles",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_user_role",
        columnNames = {"user_id", "role_id"}
    )
)
public class UserRole {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;

    @Column(name = "assigned_at", nullable = false)
    private Instant assignedAt;

    protected UserRole() {}

    public UserRole(User user, Role role, Instant assignedAt) {
        this.user = user;
        this.role = role;
        this.assignedAt = assignedAt;
    }
}
~~~

User có collection association entity:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    @OneToMany(
        mappedBy = "user",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<UserRole> memberships = new ArrayList<>();

    public void assign(Role role) {
        UserRole membership = new UserRole(
            this, role, Instant.now()
        );
        memberships.add(membership);
    }

    public void unassign(UserRole membership) {
        memberships.remove(membership);
    }
}
~~~

Role có thể chỉ cần collection đọc ngược:

~~~java
@Entity
public class Role {

    @Id
    private Long id;

    @OneToMany(mappedBy = "role")
    private List<UserRole> memberships = new ArrayList<>();
}
~~~

Ở thiết kế minh họa này:

- User là chủ vòng đời của các hàng UserRole membership.
- Cascade REMOVE/ALL từ User tới UserRole là quan hệ OneToMany có ý nghĩa phụ thuộc.
- UserRole tham chiếu Role qua ManyToOne.
- Xóa User có thể xóa các membership rows, nhưng không cascade remove tới Role.
- Xóa Role cần có quy trình xử lý các membership tham chiếu tới nó, hoặc FK/database cleanup được thiết kế phù hợp.

Đây là ví dụ về **xóa entity association** thay vì xóa entity được tham chiếu.

### 9.2. Vì sao association entity dễ kiểm soát hơn?

Nó cho phép lưu `assignedAt`, `assignedBy`, `status`, `expiresAt`; áp dụng `@Version` riêng nếu membership cần concurrency; audit việc gán/bỏ liên kết; dùng cascade REMOVE từ aggregate quản lý membership tới chính membership; và giữ Role là entity độc lập.

Không phải lúc nào cũng cần association entity. Nếu quan hệ chỉ là hai FK và không có thuộc tính riêng, `@ManyToMany` đơn giản vẫn có thể phù hợp.

## 10. Ví dụ khác: Post và Tag

Mapping Post–Tag có cùng rủi ro:

~~~java
@Entity
public class Post {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "post_tags",
        joinColumns = @JoinColumn(name = "post_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();
}
~~~

~~~java
@Entity
public class Tag {

    @Id
    private Long id;

    @ManyToMany(mappedBy = "tags")
    private Set<Post> posts = new HashSet<>();
}
~~~

Một tag `java` có thể được gắn vào hàng nghìn Post. Xóa một Post chỉ nên xóa các hàng `post_tags` có `post_id` tương ứng; Tag `java` vẫn được các Post khác dùng.

Nếu Post khai báo:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Tag> tags;
~~~

thì REMOVE trong ALL có thể truyền sang Tag và cố xóa entity dùng chung. Đây là cấu hình không nên sử dụng.

## 11. Ví dụ Student và Course

Một Student có thể đăng ký nhiều Course, một Course có nhiều Student:

~~~java
@Entity
public class Student {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
~~~

~~~java
@Entity
public class Course {

    @Id
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
~~~

Xóa Student không có nghĩa xóa Course. Xóa Course cũng không có nghĩa xóa Student. Chỉ những enrollment associations cần được gỡ bỏ.

Trong thực tế, quan hệ đăng ký thường có thuộc tính riêng như ngày đăng ký, điểm, trạng thái và học kỳ. Khi đó nên dùng `Enrollment` entity với `@ManyToOne Student` và `@ManyToOne Course`, thay vì many-to-many thuần.

## 12. Cascade nào có thể cân nhắc trên ManyToMany?

Không có một danh sách cascade dùng chung cho mọi association. Với entity đích dùng chung, **không cascade thao tác làm thay đổi vòng đời của entity đích một cách vô ý**.

| Cascade | Cần cân nhắc |
| --- | --- |
| `PERSIST` | Chỉ khi use case thực sự tạo entity đích cùng nguồn; thường không cần với Role/Tag đã tồn tại |
| `MERGE` | Có thể lan trạng thái detached sang entity dùng chung; cần thận trọng |
| `REMOVE` | Không nên dùng trên ManyToMany; không portable theo JPA và có rủi ro xóa entity được chia sẻ |
| `REFRESH` | Có thể đọc lại entity đích ngoài dự định và tốn thêm query; chỉ dùng khi có lý do |
| `DETACH` | Có thể lan thao tác detach; cân nhắc phạm vi persistence context |
| `ALL` | Bao gồm REMOVE, nên tránh trên ManyToMany dùng chung |

Mapping tối giản không khai báo cascade thường là lựa chọn dễ kiểm soát:

~~~java
@ManyToMany
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles = new HashSet<>();
~~~

Sau đó service tải User và Role đã tồn tại, thêm/bỏ liên kết bằng helper method và commit transaction.

## 13. Xóa một entity dùng chung một cách có chủ đích

Giả sử cần xóa Role `LEGACY_VIEWER` khỏi hệ thống. Đây là thao tác khác với xóa User.

Một quy trình có thể gồm:

1. Kiểm tra quyền thực hiện thao tác quản trị.
2. Xác định các association hiện có tới Role.
3. Xóa hoặc chuyển các association theo quy tắc nghiệp vụ.
4. Kiểm tra Role không còn được tham chiếu bởi dữ liệu khác.
5. Xóa Role trong transaction phù hợp.
6. Xử lý cache hoặc dữ liệu được materialize nếu có.
7. Ghi audit/event theo yêu cầu.

Nếu mapping hai chiều được load trong persistence context, có thể gỡ liên kết hai phía bằng helper:

~~~java
for (User user : new ArrayList<>(role.getUsers())) {
    user.removeRole(role);
}

em.remove(role);
~~~

Đây là pseudocode minh họa; cần bảo đảm Role.users đã được load, quan hệ owning side được sửa, collection không bị sửa đồng thời không an toàn và transaction đủ phạm vi. Với số lượng liên kết rất lớn, thao tác từng entity có thể tốn bộ nhớ/query; khi đó cân nhắc bulk delete join rows hoặc database FK cascade, đồng thời xử lý persistence context/cache.

**Không cascade REMOVE từ Role tới User chỉ để xóa hết liên kết.** Gỡ liên kết và xóa Role là hai hành động riêng.

## 14. Xóa join table bằng bulk SQL: lưu ý persistence context

Một native SQL có thể dọn association rows:

~~~java
int removed = em.createNativeQuery("""
    DELETE FROM user_roles
    WHERE user_id = :userId
    """)
    .setParameter("userId", userId)
    .executeUpdate();
~~~

Câu lệnh này chỉ xóa hàng join table. Nó không xóa Role hoặc User. Nhưng nếu persistence context đang giữ User/Role với collection `roles`/`users` đã được nạp, object graph trong RAM có thể stale sau bulk SQL.

Một quy trình có thể cần:

~~~java
em.flush();

em.createNativeQuery("""
    DELETE FROM user_roles
    WHERE user_id = :userId
    """)
    .setParameter("userId", userId)
    .executeUpdate();

em.clear();
~~~

`flush()` đồng bộ pending changes trước native DML; `clear()` detach toàn bộ managed entities để lần đọc sau nạp lại state. Cách này ảnh hưởng toàn persistence context, nên chỉ dùng khi phù hợp. Có thể chọn refresh một entity hoặc kết thúc transaction/context tùy nhu cầu.

Bulk SQL bỏ qua một số lifecycle callbacks/cascade của entity và cần được quản lý như một command riêng.

## 15. Các lỗi thường gặp

| Cấu hình hoặc hành động | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| `@ManyToMany(cascade = REMOVE)` | Xóa entity đích dùng chung | Bỏ REMOVE; chỉ xóa association row |
| `@ManyToMany(cascade = ALL)` | ALL bao gồm REMOVE và có thể lan xóa | Chọn cascade tối thiểu hoặc không cascade |
| Cascade REMOVE ở cả hai phía | Thao tác xóa lan rộng qua đồ thị | Giữ vòng đời hai entity độc lập |
| Xóa User nhưng muốn giữ Role | Cascade remove có thể xóa Role hoặc gây FK error | Không cascade REMOVE; dọn join rows |
| Bỏ Role khỏi collection nhưng Role biến mất | Nhầm xóa link với xóa entity | Chỉ cập nhật association |
| Đặt orphanRemoval trên ManyToMany | Không phù hợp/không portable với JPA | Dùng association entity nếu cần lifecycle của link |
| Chỉ sửa inverse collection | Join table có thể không được cập nhật | Sửa owning side và đồng bộ cả hai phía Java |
| Dùng ON DELETE CASCADE và tưởng nó xóa entity đích | Nhầm hướng FK cascade | Hiểu FK chỉ dọn hàng tham chiếu phù hợp |
| Xóa Role khi còn User tham chiếu | FK constraint hoặc dữ liệu quyền không nhất quán | Gỡ association có chủ đích trước |
| Bulk delete join table khi collection đã load | Persistence context giữ collection cũ | Flush/clear/refresh theo phạm vi |
| Dùng ManyToMany cho quan hệ có trạng thái | Khó lưu ngày gán, audit, status | Mô hình association entity |

## 16. Checklist thiết kế quan hệ nhiều với nhiều

Trước khi cấu hình `@ManyToMany`, hãy hỏi:

1. **Hai entity có vòng đời độc lập không?** Nếu có, không cascade REMOVE qua lại.
2. **Một entity đích có thể được chia sẻ không?** Nếu có, không để việc xóa một nguồn xóa entity dùng chung.
3. **Use case cần xóa entity hay chỉ bỏ liên kết?** Tách hai thao tác.
4. **Owning side nằm ở đâu?** Xác định `@JoinTable` và `mappedBy` chính xác.
5. **Có cần quan hệ hai chiều không?** Chỉ thêm inverse collection khi use case thực sự cần.
6. **Có cần cascade không?** Chọn từng cascade type; tránh ALL theo thói quen.
7. **Có thuộc tính trên liên kết không?** Nếu có, cân nhắc association entity.
8. **Database FK được cấu hình thế nào?** Xem constraint và ON DELETE CASCADE ở join table.
9. **Bulk SQL có làm stale persistence context không?** Lên kế hoạch clear/refresh.
10. **Có test xóa entity dùng chung không?** Kiểm tra entity đích vẫn tồn tại và các link được dọn đúng.

## 17. Bài tập thực hành

### Bài 1 — User và Role

Một User có Role ADMIN; một User khác cũng có Role ADMIN. Nếu User đầu tiên bị xóa, dữ liệu nào cần bị xóa trong schema có join table? Vì sao Role ADMIN phải còn?

### Bài 2 — Cascade ALL

Một developer khai báo:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Tag> tags;
~~~

Hãy liệt kê các thao tác cascade có trong ALL và giải thích vì sao REMOVE nguy hiểm khi một Tag được nhiều Post chia sẻ.

### Bài 3 — Owning side

User.roles có `@JoinTable`, Role.users có `mappedBy = "roles"`. Khi bỏ một Role khỏi User, cần cập nhật phía nào để association được ghi? Vì sao nên có helper method đồng bộ hai collection?

### Bài 4 — Database cascade

FK `user_roles.user_id` tham chiếu `users.id` với `ON DELETE CASCADE`. Khi xóa một User, database sẽ xóa hàng nào? Có xóa Role không? Giải thích hướng cascade của FK.

### Bài 5 — Orphan removal

Một Post bỏ Tag `java` khỏi collection. Có nên xóa Tag vì không còn được Post này sử dụng không? Vì sao orphanRemoval không phải giải pháp phù hợp cho ManyToMany?

### Bài 6 — Association entity

Một Student đăng ký Course với các thuộc tính `enrolledAt`, `status` và `grade`. Hãy thiết kế entity `Enrollment` với hai `@ManyToOne` và giải thích tại sao có thể cascade REMOVE từ Student tới Enrollment mà không cascade sang Course.

### Bài 7 — Xóa Role quản trị

Hệ thống muốn xóa Role không còn dùng. Hãy nêu quy trình kiểm tra và dọn join rows trước khi xóa Role, đồng thời đề cập persistence context nếu dùng bulk SQL.

### Bài 8 — Đánh giá tính portable

Một mapping Hibernate chấp nhận `@ManyToMany(cascade = REMOVE)` trong môi trường phát triển. Vì sao ứng dụng vẫn không nên dựa vào mapping đó khi cần portable theo Jakarta Persistence?

### Gợi ý trả lời

- **Bài 1:** Xóa User và association rows có user_id tương ứng; Role ADMIN cùng các link của User khác vẫn còn.
- **Bài 2:** ALL gồm PERSIST, MERGE, REMOVE, REFRESH, DETACH; REMOVE có thể xóa Tag được chia sẻ.
- **Bài 3:** Cập nhật owning side User.roles; helper method đồng bộ Role.users để object graph nhất quán.
- **Bài 4:** Xóa các hàng user_roles tham chiếu User; không xóa Role vì FK đó không trỏ tới Role.
- **Bài 5:** Chỉ xóa link; Tag có vòng đời độc lập và có thể được Post khác dùng. Muốn dọn Tag không còn dùng cần một quy trình riêng.
- **Bài 6:** Student có OneToMany Enrollment với cascade/orphan removal phù hợp; Enrollment ManyToOne Course không cascade REMOVE.
- **Bài 7:** Xác thực quyền, kiểm tra tham chiếu, dọn association rows, xử lý cache/context rồi mới xóa Role.
- **Bài 8:** JPA chỉ coi REMOVE cascade portable cho OneToOne/OneToMany; behavior trên ManyToMany không portable và có thể khác provider.

---

**Ghi nhớ:** Trong `@ManyToMany`, hai entity thường được chia sẻ và có vòng đời độc lập. **Xóa một liên kết chỉ nên xóa hàng join table; không đồng nghĩa xóa entity ở đầu kia.** Tránh `CascadeType.REMOVE` và `CascadeType.ALL` trên ManyToMany: ngoài rủi ro xóa dữ liệu dùng chung, REMOVE trên loại association này không phải mapping portable theo Jakarta Persistence. Khi quan hệ có lifecycle/thuộc tính riêng, hãy mô hình hóa join row thành association entity để kiểm soát cascade rõ ràng.
