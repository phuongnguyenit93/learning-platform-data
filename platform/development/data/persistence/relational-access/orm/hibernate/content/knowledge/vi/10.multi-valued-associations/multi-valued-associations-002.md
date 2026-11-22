# `@OneToMany` một chiều và các phương án bảng liên kết hoặc cột liên kết

Trong Hibernate và Jakarta Persistence, `@OneToMany` biểu diễn quan hệ **một entity cha có nhiều entity con**. Nếu ứng dụng chỉ cần đi từ cha đến con, còn entity con không cần tham chiếu ngược tới cha, đây là quan hệ **một chiều** (*unidirectional association*).

Có hai cách quan trọng để lưu một `@OneToMany` một chiều trong cơ sở dữ liệu quan hệ:

1. **Bảng liên kết** (*join table/link table*): một bảng thứ ba chứa khóa ngoại tới cha và con. Đây là cách ánh xạ mặc định của Hibernate/Jakarta Persistence cho unidirectional `@OneToMany` khi không chỉ định phương án khác.
2. **Cột khóa ngoại trong bảng con** (*foreign key in child table*): một cột như `project_id` nằm ngay trong bảng con; khai báo bằng `@JoinColumn` trên collection của entity cha.

Hai cách có thể thể hiện cùng một quan hệ ở Java nhưng khác **DDL, constraint, số SQL được thực thi và cách thay đổi liên kết**. Hiểu rõ điểm này giúp tránh việc Hibernate tự sinh bảng trung gian ngoài dự kiến, thao tác xóa/chèn lại nhiều hàng hoặc vi phạm `NOT NULL` khi persist con.

## 1. Thế nào là `@OneToMany` một chiều?

Giả sử một dự án có nhiều công việc:

```text
Project (id = 42)
  ├─ TaskItem (id = 101, title = "Thiết kế database")
  ├─ TaskItem (id = 102, title = "Viết API")
  └─ TaskItem (id = 103, title = "Kiểm thử")
```

`TaskItem` là **entity**, có `@Id`, có thể được truy vấn/cập nhật độc lập về định danh. Entity `Project` giữ collection các task:

```java
@OneToMany
private Set<TaskItem> tasks = new HashSet<>();
```

Nhưng `TaskItem` **không khai báo**:

```java
@ManyToOne
private Project project;
```

Vì vậy, ứng dụng điều hướng được từ cha:

```java
project.getTasks();
```

nhưng không có quan hệ object ngược:

```java
task.getProject(); // Không tồn tại trong mô hình một chiều.
```

**Một chiều chỉ nói về khả năng điều hướng trong Java.** Database vẫn có thể lưu `task_items.project_id` làm FK đến `projects.id`; không cần entity `TaskItem` có thuộc tính Java `project` để tồn tại cột đó.

### 1.1. Phân biệt với những kiểu collection khác

| Mapping | Loại phần tử | Có ID entity riêng? | Ý nghĩa |
| --- | --- | --- | --- |
| `@OneToMany` | Entity con | Có | Một cha liên kết nhiều entity con |
| `@ElementCollection` | Basic value hoặc `@Embeddable` | Không | Các giá trị thuộc owner |
| `@ManyToMany` | Entity phía bên kia | Có | Một phần tử có thể được nhiều owner cùng liên kết |
| `@OneToOne` | Entity khác | Có | Một entity liên kết tối đa một entity ở phía kia |

Một `List<String>` chứa tag thường phù hợp `@ElementCollection`. Một `Set<TaskItem>` gồm các task có `id` và vòng đời entity là `@OneToMany`. Nếu một task phải tham gia nhiều project đồng thời, phải xem xét `@ManyToMany` hoặc entity liên kết thay vì ép nó vào mô hình một-nhiều.

## 2. Hai schema khác nhau cho cùng quan hệ

### Phương án A — Bảng liên kết

```text
projects                      project_tasks                   task_items
+----+-----------+             +------------+---------+        +-----+------------+
| id | name      |             | project_id | task_id |        | id  | title      |
+----+-----------+             +------------+---------+        +-----+------------+
| 42 | Migration |------------>| 42         | 101     |------->| 101 | Thiết kế DB|
|    |           |------------>| 42         | 102     |------->| 102 | Viết API   |
|    |           |------------>| 42         | 103     |------->| 103 | Kiểm thử   |
+----+-----------+             +------------+---------+        +-----+------------+
                                  FK to       FK to
                                  projects    task_items
```

Quan hệ được biểu diễn trong `project_tasks`. Bảng `task_items` không cần cột `project_id`.

### Phương án B — FK trực tiếp trong bảng con

```text
projects                             task_items
+----+-----------+                   +-----+------------+------------+
| id | name      |                   | id  | title      | project_id |
+----+-----------+                   +-----+------------+------------+
| 42 | Migration |------------------>| 101 | Thiết kế DB| 42         |
|    |           |------------------>| 102 | Viết API   | 42         |
|    |           |------------------>| 103 | Kiểm thử   | 42         |
+----+-----------+                   +-----+------------+------------+
```

Cột `project_id` của mỗi `TaskItem` tham chiếu `Project.id`. Không cần bảng trung gian.

| Tiêu chí | `@JoinTable` (bảng liên kết) | `@JoinColumn` (FK ở con) |
| --- | --- | --- |
| Vị trí lưu quan hệ | Bảng thứ ba | Cột trong bảng con |
| Số bảng | 3 | 2 |
| Cách Hibernate thường chọn nếu chỉ ghi `@OneToMany` một chiều | Mặc định | Cần khai báo rõ |
| Đọc theo cha | Join từ bảng link đến child | Tìm trực tiếp theo child FK |
| Gỡ quan hệ nhưng giữ entity con | Xóa hàng link | Gán FK thành `NULL` nếu cho phép |
| Chi phí cập nhật | Có thể xóa/tạo lại nhiều link rows | Có thể phát thêm `UPDATE` child FK |
| Con có thể chưa thuộc cha | Không có link | `project_id` nullable |
| Ràng buộc mỗi con thuộc tối đa một cha | `UNIQUE(child_id)` trên bảng link | Mỗi hàng con chứa một giá trị FK |
| Cần lưu metadata trên chính liên kết | Có bảng link nhưng chưa có entity quản lý | Có thể cần thiết kế lại |

## 3. Entity con dùng chung cho hai ví dụ

Lớp `TaskItem` không biết đối tượng `Project`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "task_items")
public class TaskItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    protected TaskItem() {
        // Constructor không tham số cho Jakarta Persistence.
    }

    public TaskItem(String title) {
        this.title = Objects.requireNonNull(title);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String title) {
        this.title = Objects.requireNonNull(title);
    }
}
```

Đây là entity có primary key riêng. Nó khác một giá trị `@Embeddable` thuộc `@ElementCollection`, vì có danh tính được persistence context theo dõi và có thể tồn tại như một đối tượng domain riêng.

## 4. Phương án A: `@OneToMany` một chiều dùng `@JoinTable`

Nếu chỉ viết `@OneToMany` trên collection mà không nêu `@JoinColumn`, Hibernate thường dùng **join table**. Khai báo `@JoinTable` giúp tên bảng và cột rõ ràng hơn:

```java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "projects")
public class Project {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    @OneToMany(
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    @JoinTable(
        name = "project_tasks",
        joinColumns = @JoinColumn(name = "project_id"),
        inverseJoinColumns = @JoinColumn(
            name = "task_id",
            unique = true
        )
    )
    private Set<TaskItem> tasks = new HashSet<>();

    protected Project() {
    }

    public Project(String name) {
        this.name = Objects.requireNonNull(name);
    }

    public Long getId() {
        return id;
    }

    public Set<TaskItem> getTasks() {
        return Collections.unmodifiableSet(tasks);
    }

    public void addTask(TaskItem task) {
        tasks.add(Objects.requireNonNull(task));
    }

    public void removeTask(TaskItem task) {
        tasks.remove(task);
    }
}
```

Giải nghĩa:

- `@OneToMany` biểu diễn bội số một-nhiều của các **entity**.
- `@JoinTable(name = "project_tasks")` chọn bảng trung gian.
- `joinColumns` là FK từ bảng trung gian **về bảng của `Project`**.
- `inverseJoinColumns` là FK từ bảng trung gian **về bảng của `TaskItem`**.
- `unique = true` trên `task_id` thể hiện rằng một task không thể liên kết với hai project cùng lúc.
- `cascade = CascadeType.ALL` làm thao tác như persist/remove từ cha có thể lan tới các task.
- `orphanRemoval = true` yêu cầu xóa entity con khi nó bị tách khỏi quan hệ sở hữu, phù hợp nếu con phụ thuộc vòng đời vào cha.

**Lựa chọn cascade và orphan removal ở đây phục vụ một domain cụ thể**: task chỉ tồn tại trong project. Không sao chép nguyên mẫu này nếu task có lịch sử/vòng đời riêng hoặc cần chuyển project thường xuyên.

### 4.1. DDL minh họa

```sql
CREATE TABLE projects (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);

CREATE TABLE task_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE project_tasks (
    project_id BIGINT NOT NULL,
    task_id BIGINT NOT NULL,

    CONSTRAINT pk_project_tasks
        PRIMARY KEY (project_id, task_id),

    CONSTRAINT uq_project_tasks_task
        UNIQUE (task_id),

    CONSTRAINT fk_project_tasks_project
        FOREIGN KEY (project_id) REFERENCES projects(id),

    CONSTRAINT fk_project_tasks_task
        FOREIGN KEY (task_id) REFERENCES task_items(id)
);
```

DDL trên minh họa với cú pháp PostgreSQL hiện đại; cú pháp sinh khóa và tên constraint có thể khác ở DBMS khác. Hibernate DDL generator có thể không tạo **chính xác** cùng tên constraint hoặc index; cần quản lý schema bằng migration trong hệ thống triển khai thực tế.

Hai ràng buộc rất đáng chú ý:

```sql
PRIMARY KEY (project_id, task_id)
UNIQUE (task_id)
```

`PRIMARY KEY(project_id, task_id)` chỉ ngăn trùng một cặp. Nếu **không** có `UNIQUE(task_id)`, database vẫn có thể chấp nhận:

```text
project_id  task_id
42          101
43          101   ← một task được gán hai project
```

Điều đó phá vỡ bội số một-nhiều trong model. `UNIQUE(task_id)` bảo đảm mỗi task có tối đa một owner qua bảng liên kết. Với `@ManyToMany`, ngược lại, nhiều hàng có cùng `task_id` và khác `project_id` có thể là dữ liệu hợp lệ.

### 4.2. Persist cha và con

Ví dụ dùng Jakarta Persistence với transaction resource-local:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Project project = new Project("Migration");
    project.addTask(new TaskItem("Thiết kế database"));
    project.addTask(new TaskItem("Viết API"));

    em.persist(project); // Cascade PERSIST xuống con.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Giả sử database cấp `Project.id = 42` và hai task có ID `101`, `102`, dữ liệu có dạng:

```text
projects:
  (42, "Migration")

task_items:
  (101, "Thiết kế database")
  (102, "Viết API")

project_tasks:
  (42, 101)
  (42, 102)
```

SQL về mặt ý tưởng:

```sql
INSERT INTO projects(name) VALUES ('Migration');

INSERT INTO task_items(title) VALUES ('Thiết kế database');
INSERT INTO task_items(title) VALUES ('Viết API');

INSERT INTO project_tasks(project_id, task_id) VALUES (42, 101);
INSERT INTO project_tasks(project_id, task_id) VALUES (42, 102);
```

Đây là **SQL minh họa**, không phải log đã chạy. Thứ tự SQL, generated ID, batching và thời điểm flush phụ thuộc Hibernate, JDBC driver, dialect và cấu hình.

## 5. Vì sao xóa một con có thể tạo nhiều SQL với bảng link?

Giả sử project đang có task `101`, `102`, `103`. Trong transaction, ứng dụng gỡ task `102`:

```java
project.removeTask(task102);
```

Theo ví dụ trong Hibernate ORM User Guide, khi flush unidirectional `@OneToMany` qua bảng link, Hibernate có thể:

```sql
DELETE FROM project_tasks
WHERE project_id = 42;

INSERT INTO project_tasks(project_id, task_id)
VALUES (42, 101);

INSERT INTO project_tasks(project_id, task_id)
VALUES (42, 103);

DELETE FROM task_items
WHERE id = 102;
```

Với `orphanRemoval = true`, task bị gỡ cũng bị xóa khỏi bảng entity. Điều bất ngờ là **một lần remove ở Java có thể xóa tất cả link rows của project rồi chèn lại những link còn giữ**. Đây là hành vi Hibernate ghi nhận trong ví dụ unidirectional `@OneToMany`, nhưng không có nghĩa mọi phiên bản, collection type và mapping luôn phát đúng từng statement trên.

Nếu project có 500 task và gỡ một task, chiến lược này có thể tạo rất nhiều row changes ở bảng trung gian. Hệ quả gồm tăng transaction log, công việc index, độ dài transaction và ảnh hưởng locking. Vì vậy, khi association cập nhật nhiều, cần quan sát SQL thực tế thay vì đánh giá theo vẻ đơn giản của `tasks.remove(x)`.

### 5.1. Nếu không bật orphanRemoval

Xem mapping:

```java
@OneToMany(cascade = CascadeType.PERSIST)
@JoinTable(
    name = "project_tasks",
    joinColumns = @JoinColumn(name = "project_id"),
    inverseJoinColumns = @JoinColumn(name = "task_id", unique = true)
)
private Set<TaskItem> tasks = new HashSet<>();
```

Khi task bị loại khỏi collection, **liên kết** không còn trong bảng `project_tasks`, nhưng entity `TaskItem` **không tự động bị xóa** vì hành động gỡ quan hệ. Hàng task có thể tồn tại độc lập trong `task_items`.

Phải tách biệt:

- **Gỡ association**: xóa hàng của bảng liên kết.
- **Xóa entity**: thực hiện thao tác `REMOVE` đối với task, trực tiếp hoặc qua cơ chế orphan removal/cascade được cấu hình.

Với task có lịch sử audit, vòng đời tách biệt hoặc được dùng trong các công việc khác, xóa hẳn entity con có thể không phải quyết định đúng.

## 6. Phương án B: `@OneToMany` một chiều dùng `@JoinColumn`

Nếu muốn FK nằm trong bảng `task_items`, **thay** mapping `@JoinTable` ở entity `Project` bằng:

```java
@OneToMany(
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
@JoinColumn(
    name = "project_id",
    referencedColumnName = "id"
)
private Set<TaskItem> tasks = new HashSet<>();
```

Đây là **mapping thay thế**, không chạy đồng thời với `@JoinTable` trên cùng một collection.

Vị trí annotation dễ gây nhầm lẫn: `@JoinColumn` đặt **trên field collection của Project** nhưng `project_id` được lưu trong **bảng con** (`task_items`). Jakarta Persistence đặc tả rõ vị trí FK trong trường hợp unidirectional OneToMany dùng foreign-key mapping.

### 6.1. Schema tương ứng

```sql
CREATE TABLE projects (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);

CREATE TABLE task_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    project_id BIGINT,
    CONSTRAINT fk_task_items_project
        FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

Không còn bảng `project_tasks`. Để đọc các task của `Project(42)`:

```sql
SELECT t.id, t.title
FROM task_items t
WHERE t.project_id = 42;
```

Trong class `TaskItem` vẫn có thể **không khai báo property `project`**. Quyền điều hướng một chiều ở Java và vị trí FK vật lý ở SQL là hai đặc điểm độc lập.

### 6.2. Thứ tự INSERT và UPDATE FK

Một hạn chế thực tế của mapping `@OneToMany @JoinColumn` một chiều là Hibernate **có thể** tạo SQL theo hai bước:

```sql
INSERT INTO projects(name) VALUES ('Migration');

INSERT INTO task_items(title) VALUES ('Viết API');

UPDATE task_items
SET project_id = 42
WHERE id = 102;
```

Vì phía parent collection quản lý relationship, Hibernate có thể persist row của child trước rồi đồng bộ cột FK trong một thao tác `UPDATE`.

Đây **không phải bảo đảm mọi Hibernate version đều luôn phát `INSERT` rồi `UPDATE`**, nhưng là trường hợp quan trọng phải kiểm tra. Nếu database có:

```sql
project_id BIGINT NOT NULL
```

mà statement `INSERT INTO task_items` chưa chứa `project_id`, database có thể từ chối **trước khi Hibernate thực hiện UPDATE**.

Vì vậy:

1. Không tự coi `@JoinColumn(nullable=false)` là bảo đảm provider luôn đưa FK vào cùng câu `INSERT`.
2. Quan sát SQL với đúng phiên bản Hibernate, chiến lược sinh ID và DBMS sẽ triển khai.
3. Nếu FK phải `NOT NULL` và nghiệp vụ luôn gán cha ngay từ lúc tạo con, **bidirectional `@ManyToOne` sở hữu FK** thường là một phương án đáng cân nhắc.
4. Nếu chấp nhận con chưa thuộc cha, giữ FK nullable và quy định rõ hành vi của trạng thái đó.

### 6.3. `nullable = false` có thể được khai báo thế nào?

```java
@OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)
@JoinColumn(name = "project_id", nullable = false)
private Set<TaskItem> tasks = new HashSet<>();
```

Thuộc tính này diễn đạt constraint dự kiến cho cột FK và có thể tham gia DDL generation. Tuy vậy, **metadata không tự khắc phục thứ tự DML**. Cần kiểm tra insert, remove, orphan deletion và migration schema bằng integration test phù hợp. Không nên hạ constraint trong database chỉ để che một lỗi lifecycle mà chưa hiểu hậu quả dữ liệu.

### 6.4. Gỡ con khi FK ở bảng con

Nếu `orphanRemoval = false` và ứng dụng gỡ task khỏi collection, Hibernate có thể cần:

```sql
UPDATE task_items
SET project_id = NULL
WHERE id = 102;
```

Điều này chỉ phù hợp nếu `project_id` **cho phép `NULL`**. Nếu FK `NOT NULL`, phải chọn mô hình nghiệp vụ khác: xóa con khi rời owner, chuyển con sang owner khác, hoặc thay thiết kế mapping.

Khi `orphanRemoval = true`, Hibernate cần xóa entity con đã trở thành orphan. Không nên khẳng định provider sẽ luôn bỏ qua mọi bước UPDATE FK trung gian trong mọi phiên bản; hành vi thực tế chịu ảnh hưởng của mapping và thứ tự flush.

## 7. So sánh các thao tác trong hai phương án

| Thao tác | Dùng bảng liên kết | Dùng FK trực tiếp ở child |
| --- | --- | --- |
| Tạo parent và nhiều child | INSERT parent, child và hàng link | INSERT parent/child; có thể thêm UPDATE FK |
| Tải children theo parent | JOIN qua bảng link | Filter/join bằng FK trong child |
| Gỡ child nhưng không xóa entity | Xóa liên kết ở bảng link, có thể tái tạo các link còn lại | Set FK của child thành NULL nếu cho phép |
| Gỡ child có orphan removal | Gỡ link và xóa child | Xóa child, có thể kèm thao tác FK tùy provider |
| Xóa parent và các child | Xóa links, child và parent theo cascade/lifecycle | Xóa child và parent theo cascade/lifecycle |
| Chuyển child từ A sang B | Chuyển link, bảo đảm UNIQUE(child_id) | Thay giá trị FK child |
| Thêm thứ tự trong danh sách | Cột vị trí có thể nằm ở link table | Cột vị trí có thể nằm trong bảng child |
| Tối ưu ghi | Có thể chịu chi phí tái tạo nhiều link rows | Có thể tốn SQL UPDATE FK, nhưng không cần bảng thứ ba |

Các hàng trong bảng chỉ mô tả **logic hoặc hành vi có thể xảy ra**, không hứa số statement cố định. Batching, insert ordering, schema generation và collection semantics phụ thuộc Hibernate version và mapping.

## 8. “Owning side” trong quan hệ một chiều

Một quan hệ một chiều chỉ khai báo ở một bên, nên **bên có quan hệ là owning side**:

- `Project.tasks` sở hữu association khi dùng `@OneToMany @JoinTable`.
- `Project.tasks` cũng sở hữu association khi dùng unidirectional `@OneToMany @JoinColumn`, dù FK nằm vật lý ở `task_items`.
- Entity `TaskItem` không có field association ngược và không điều khiển relationship thông qua JPA mapping của chính nó.

Vì vậy, không thể suy đơn giản rằng “bảng nào chứa FK thì entity tương ứng luôn owning side”. Điều này **đúng điển hình với `@ManyToOne` của quan hệ hai chiều**, nhưng **không đúng trong trường hợp một chiều với FK ở bảng con**.

### 8.1. Đừng đặt `mappedBy` khi không có field ngược

Sai nếu `TaskItem` không có property `project`:

```java
@OneToMany(mappedBy = "project")
private Set<TaskItem> tasks;
```

`mappedBy = "project"` yêu cầu trong class `TaskItem` phải có một **thuộc tính Java** tên `project` mô tả quan hệ ngược, thường là:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "project_id")
private Project project;
```

Khi đã thêm field đó và dùng `mappedBy`, mapping chuyển thành quan hệ **hai chiều**, không còn là ví dụ một chiều. Tên trong `mappedBy` là tên property/field Java, **không phải tên cột SQL**.

## 9. Phương án hai chiều thường được dùng với FK ở bảng con

Một cách thay thế cho unidirectional `@JoinColumn`:

```java
// Trong Project:
@OneToMany(
    mappedBy = "project",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private Set<TaskItem> tasks = new HashSet<>();

// Trong TaskItem:
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "project_id", nullable = false)
private Project project;
```

Trong mapping **hai chiều** này, phía `@ManyToOne` của `TaskItem` **sở hữu FK**. Để giữ mô hình Java nhất quán, entity cha thường có helper methods:

```java
public void addTask(TaskItem task) {
    tasks.add(task);
    task.setProject(this);
}

public void removeTask(TaskItem task) {
    tasks.remove(task);
    task.setProject(null);
}
```

Đây là **đoạn minh họa**; để biên dịch cần method `setProject` và các class/import đầy đủ. Với orphan removal, tách task có thể dẫn tới xóa entity chứ không giữ lại hàng với FK `NULL`.

Khi child quản lý trực tiếp `project_id`, Hibernate thường có đủ thông tin để đưa FK vào SQL `INSERT` hoặc `UPDATE` con theo trạng thái entity. Việc remove một child không nhất thiết làm tái tạo toàn bộ link rows như ví dụ join table một chiều.

Tuy nhiên, quan hệ hai chiều có chi phí thiết kế: ứng dụng phải đồng bộ **cả `Project.tasks` và `TaskItem.project`** trong bộ nhớ. Chọn dựa trên nhu cầu điều hướng, vòng đời và khối lượng cập nhật.

## 10. Cascade và orphanRemoval là quyết định khác nhau

`@OneToMany` không mặc định tự persist mọi con. Cascade và orphan removal phải được chọn theo domain:

| Cấu hình | Tác dụng |
| --- | --- |
| Không cascade | Persist/remove cha không tự làm tương tự cho mọi con |
| `CascadeType.PERSIST` | Persist cha có thể persist những con được liên kết |
| `CascadeType.MERGE` | Merge trạng thái cha có thể lan xuống con |
| `CascadeType.REMOVE` | Remove cha lan xuống con ở phạm vi quan hệ |
| `CascadeType.ALL` | Gồm PERSIST, MERGE, REMOVE, REFRESH, DETACH |
| `orphanRemoval = true` | Xóa con khi bị tách khỏi relationship sở hữu, theo quy tắc đặc tả |

Ba tình huống nên phân biệt:

**Tình huống A — Thêm task mới:**

```java
project.addTask(new TaskItem("Tạo API"));
em.persist(project);
```

Nếu project mới và mapping có cascade `PERSIST`, Hibernate có thể đưa task mới vào trạng thái persistent cùng parent.

**Tình huống B — Gỡ một task:**

```java
project.removeTask(existingTask);
```

Với `orphanRemoval=true`, task cũ có thể bị `REMOVE`. Với `orphanRemoval=false`, chỉ association được gỡ, nếu schema và lifecycle cho phép.

**Tình huống C — Xóa cả project:**

```java
em.remove(project);
```

Với cascade REMOVE/ALL, Hibernate có thể xóa các task liên quan. Nếu task cần được giữ để audit, cấu hình này có thể sai về nghiệp vụ. `ON DELETE CASCADE` ở database là cơ chế riêng, không đồng nghĩa CascadeType.REMOVE.

Không mặc định bật cascade từ con ngược lên cha nếu chuyển sang mapping hai chiều; xóa một task không nên bất ngờ xóa luôn project.

### 10.1. Entity con mới, managed và detached

Orphan removal được định nghĩa cho quan hệ với entity phụ thuộc và có chi tiết theo trạng thái entity. Một task mới chưa persist có thể **chưa có bản ghi DB để xóa**. Entity detached không tự động được dirty-check như entity managed. Cần hiểu trạng thái, flush và transaction thay vì nghĩ “xóa khỏi Java collection sẽ lập tức gửi SQL”.

## 11. `Set`, `List`, thứ tự và vấn đề equality

### 11.1. Dùng `Set<TaskItem>`

`Set` thích hợp khi mỗi object không được trùng theo equality của Java. Nhưng `Set` dùng `equals()` và `hashCode()`, trong khi Hibernate quản lý identity của entity bằng khóa chính.

Nếu ID được sinh sau persist, một `hashCode()` dựa vào `id` có thể thay đổi từ lúc chưa có ID sang lúc đã có ID. Điều này có thể làm `HashSet.remove()`/`contains()` hoạt động bất ngờ.

Với ví dụ nhỏ, `TaskItem` không tự override `equals/hashCode`. Trong ứng dụng thực, cần chọn một chính sách equality ổn định, phù hợp việc entity mới/managed/detached có thể đến từ những persistence context khác nhau.

### 11.2. `List<TaskItem>` không tự đảm bảo thứ tự trong database

```java
@OneToMany
private List<TaskItem> tasks = new ArrayList<>();
```

Một `List` có thứ tự trong bộ nhớ Java, nhưng thứ tự **không nhất thiết được duy trì sau reload** nếu không khai báo mapping thứ tự phù hợp. Hibernate có thể dùng bag/list semantics khác nhau theo phiên bản và cấu hình.

Nếu thứ tự do người dùng lựa chọn phải được lưu bền vững, dùng `@OrderColumn`:

```java
@OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)
@JoinTable(
    name = "project_tasks",
    joinColumns = @JoinColumn(name = "project_id"),
    inverseJoinColumns = @JoinColumn(name = "task_id", unique = true)
)
@OrderColumn(name = "task_position")
private List<TaskItem> tasks = new ArrayList<>();
```

Trong cách lưu bằng bảng link, bảng có thể chứa `task_position`:

```text
project_id | task_id | task_position
42         | 101     | 0
42         | 103     | 1
42         | 102     | 2
```

Thêm, xóa hoặc chuyển vị trí giữa danh sách có thể dẫn tới việc **cập nhật index của nhiều hàng**. Với FK trực tiếp ở child, cột vị trí có thể được lưu trong bảng con theo mapping tương ứng.

### 11.3. `@OrderBy` khác `@OrderColumn`

```java
@OneToMany
@OrderBy("title ASC")
private List<TaskItem> tasks = new ArrayList<>();
```

`@OrderBy` lấy dữ liệu đã có và **sắp xếp theo `TaskItem.title`**, không lưu thứ tự kéo-thả do người dùng đặt. `@OrderColumn` biểu diễn **vị trí của phần tử**. Không dùng cả hai trên cùng collection như hai cơ chế cùng xác định thứ tự.

### 11.4. Trùng phần tử và cardinality

`ArrayList` cho phép thêm cùng một object hai lần, nhưng `@OneToMany` có nghĩa một entity con không có hai liên kết chủ sở hữu cùng lúc. Schema join table với `UNIQUE(task_id)` không cho cùng `task_id` xuất hiện trong hai hàng. Nếu nghiệp vụ cần nhiều bản ghi gán cùng task với vai trò hoặc thời điểm khác nhau, nên có **entity liên kết** thay vì trông chờ vào duplicate trong Java List.

## 12. Lazy loading và fetch plan

`@OneToMany` mặc định dùng `FetchType.LAZY` trong Jakarta Persistence. Hibernate thường quản lý collection bằng một wrapper có thể chỉ tải khi truy cập:

```java
Project project = em.find(Project.class, 42L);

// Collection có thể chưa được tải:
int count = project.getTasks().size();
```

Lời gọi `size()` có thể khiến Hibernate thực thi SQL; việc có phát SQL phụ thuộc collection đã khởi tạo chưa, cache/fetch mode và những tối ưu tương ứng.

### 12.1. LazyInitializationException

```java
Project project;

EntityManager em = emf.createEntityManager();
try {
    project = em.find(Project.class, 42L);
} finally {
    em.close();
}

project.getTasks().size(); // Có thể báo LazyInitializationException.
```

Nếu collection còn lazy và session đã đóng, Hibernate không còn ngữ cảnh để tải nó. Cách xử lý tốt là để service lấy dữ liệu cần thiết **trong transaction/persistence context phù hợp**, rồi trả về DTO hoặc sử dụng fetch plan cụ thể. Không bật `EAGER` cho mọi association để chữa tạm vì có thể tăng lượng dữ liệu và query count.

### 12.2. JPQL `JOIN FETCH`

```java
Project project = em.createQuery(
        "select distinct p from Project p " +
        "left join fetch p.tasks " +
        "where p.id = :id",
        Project.class
    )
    .setParameter("id", 42L)
    .getSingleResult();
```

Query yêu cầu tải các task khi lấy project. Với join table Hibernate có thể join qua bảng link; với FK trực tiếp, SQL có thể join thẳng tới `task_items`.

Khi fetch nhiều collection trong một query, có thể gặp **nhân số hàng SQL** hoặc lỗi kiểu `MultipleBagFetchException` trong Hibernate nếu join nhiều bag. Phân trang parent cùng collection fetch cũng có giới hạn; nên thiết kế truy vấn theo use case thay vì join fetch mọi thứ.

### 12.3. N+1 query

```java
List<Project> projects = em.createQuery(
    "select p from Project p", Project.class
).getResultList();

for (Project p : projects) {
    System.out.println(p.getTasks().size());
}
```

Nếu 100 project dẫn tới 100 SELECT riêng khi truy cập collection, đó là vấn đề N+1. Tùy dữ liệu, có thể chọn fetch join có kiểm soát, entity graph, batch fetching hoặc truy vấn DTO. **Đo SQL và row count thực tế** trước khi thay fetch strategy.

## 13. JPQL khi phía con không có `project`

Vì `TaskItem` không khai báo quan hệ ngược, câu sau không hợp lệ trong JPQL:

```java
// Sai nếu TaskItem không có thuộc tính Java project.
"select t from TaskItem t where t.project.id = :projectId"
```

Thay vào đó, đi từ `Project.tasks`:

```java
List<TaskItem> tasks = em.createQuery(
        "select t from Project p join p.tasks t " +
        "where p.id = :projectId",
        TaskItem.class
    )
    .setParameter("projectId", 42L)
    .getResultList();
```

Truy vấn hoạt động với **cả `@JoinTable` lẫn `@JoinColumn`**, vì JPQL dùng metadata quan hệ trong entity model.

Một truy vấn tìm các project có task với tên cụ thể:

```java
List<Project> projects = em.createQuery(
        "select distinct p from Project p join p.tasks t " +
        "where t.title = :title",
        Project.class
    )
    .setParameter("title", "Viết API")
    .getResultList();
```

Trong JPQL, tên entity/class và field Java (`TaskItem`, `title`) khác với tên bảng/cột SQL (`task_items`, `title`). Provider chuyển chúng thành SQL phù hợp với schema.

## 14. Constraint và index cần thiết

### 14.1. Với join table

Schema thường cần:

```sql
PRIMARY KEY (project_id, task_id)
UNIQUE (task_id)
FOREIGN KEY (project_id) REFERENCES projects(id)
FOREIGN KEY (task_id) REFERENCES task_items(id)
```

Lưu ý `UNIQUE(task_id)` bảo vệ bội số **một con tối đa một cha**. PK ghép một mình không đủ. Index bắt đầu bằng `project_id` có thể có ích khi tải toàn bộ task của project, tùy DBMS.

### 14.2. Với FK trực tiếp

Schema:

```sql
task_items(
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    project_id BIGINT REFERENCES projects(id)
)
```

- **Không đặt `UNIQUE(project_id)`**, vì làm vậy mỗi project chỉ có tối đa một task, vô tình biến bội số thành 1:1.
- Nếu task bắt buộc có project, cần giải quyết `NOT NULL` và thứ tự SQL persist.
- Index `project_id` có thể hữu ích khi tìm task theo project:

```sql
CREATE INDEX idx_task_items_project
ON task_items(project_id);
```

Tùy hệ quản trị, FK có thể không tự được đánh index, nên cần xem query plan trước khi quyết định.

### 14.3. Annotation và database phải nhất quán

`@JoinTable`, `@JoinColumn`, `unique` và `nullable` có thể ảnh hưởng DDL do Hibernate sinh, nhưng không đảm bảo database production đã có constraint tương ứng. Nếu schema được quản lý qua Flyway/Liquibase, hãy cập nhật migration, đối chiếu entity mapping và kiểm tra các thao tác ghi thực tế.

## 15. Transaction, `flush()` và collection managed

Khi `Project` đang managed, Hibernate có thể theo dõi thay đổi của collection:

```java
Project project = em.find(Project.class, 42L);
project.addTask(new TaskItem("Viết tài liệu"));
em.flush();
```

Nếu `cascade = PERSIST` hoặc `ALL`, task mới có thể được đưa vào persistence context khi Hibernate xử lý thay đổi. Nếu không cấu hình cascade, ứng dụng cần quản lý trạng thái của task rõ ràng; không mặc định chỉ add vào collection sẽ persist một entity transient.

`flush()` là đồng bộ thay đổi với database, **chưa phải commit**. Transaction có thể rollback sau đó. Những lỗi FK, UNIQUE, NOT NULL hoặc orphan deletion thường chỉ xuất hiện khi flush hoặc commit.

### 15.1. Đừng tùy tiện thay cả field collection của entity managed

Trong ví dụ:

```java
private Set<TaskItem> tasks = new HashSet<>();
```

Khi entity đang managed, Hibernate có thể dùng collection wrapper để dirty-check. Thay field bằng một `new HashSet<>()` tùy tiện có thể làm mất liên kết với wrapper, phát nhiều SQL hoặc gây lỗi với mapping orphan removal.

Nên cung cấp method như:

```java
public void addTask(TaskItem task) {
    tasks.add(Objects.requireNonNull(task));
}

public void removeTask(TaskItem task) {
    tasks.remove(task);
}
```

Nếu cần thay toàn bộ collection, thiết kế thao tác **điều chỉnh nội dung collection managed hiện tại**, hoặc rõ ràng về merge/lifecycle, thay vì ném một object collection hoàn toàn mới vào field.

### 15.2. Detached entity và merge

Khi đóng `EntityManager`, project trở thành detached. Thay collection sau đó **không tự phát SQL**. Khi gọi:

```java
Project managed = em.merge(detachedProject);
```

`merge()` trả về một bản **managed**, còn object được truyền vào vẫn detached. Việc merge một collection cũ có thể ghi đè thay đổi mới của request khác. Với API cập nhật từng task, thường nên load project hiện tại trong transaction và thực hiện delta add/remove, đồng thời dùng optimistic locking nếu nghiệp vụ cần.

### 15.3. `@Version` và concurrency

```java
@Version
private long version;
```

Có thể giúp Hibernate phát hiện xung đột cập nhật entity; đối với collection do owner quản lý, việc tăng version và xử lý xung đột phụ thuộc mapping và đường cập nhật. Native SQL hoặc bulk JPQL có thể không tuân theo lifecycle của ORM. Nếu nhiều request thêm/gỡ task đồng thời, phải thiết kế và kiểm tra concurrency trên use case thật.

## 16. Khi nào một chiều là lựa chọn hợp lý?

### 16.1. Chọn join table khi

- Schema đang có bảng liên kết và không muốn sửa bảng con.
- Con có thể tồn tại độc lập mà không có parent, vì một task có thể chưa xuất hiện trong bảng liên kết.
- Collection nhỏ, ít thay đổi và chi phí duy trì bảng link chấp nhận được.
- Cần giữ các liên kết tách khỏi hàng con, nhưng chưa cần metadata/lifecycle riêng trên liên kết.

Không nên chỉ vì ít annotation mà chọn join table cho collection rất lớn hoặc cập nhật thường xuyên; cần xem chi phí xóa/chèn lại link rows.

### 16.2. Chọn FK trực tiếp khi

- Schema tự nhiên đã có `task_items.project_id`.
- Muốn tránh bảng thứ ba và đọc task theo parent hiệu quả.
- Một task thuộc tối đa một project tại một thời điểm.
- Đã kiểm tra Hibernate phát SQL phù hợp với `nullable`, `orphanRemoval`, generated IDs và schema.

Nếu **FK phải NOT NULL từ thời điểm INSERT**, hoặc cần cập nhật liên kết thường xuyên, nên đánh giá quan hệ hai chiều với `@ManyToOne` sở hữu FK.

### 16.3. Chọn quan hệ hai chiều khi

- Child thực sự cần biết parent (`task.getProject()`).
- Thao tác thêm/gỡ/chuyển child thường xuyên.
- Cần query trực tiếp từ child theo parent.
- Muốn Hibernate có quyền kiểm soát FK ngay trong state của child để tránh các thao tác association bổ sung.

Chi phí của quan hệ hai chiều là phải đồng bộ cả hai phía trong Java và giữ helper methods đúng.

## 17. Nếu bảng liên kết có metadata nghiệp vụ thì sao?

Một association có thể mang thêm thông tin:

```text
project_id
task_id
assigned_at
assigned_by
assignment_status
display_order
```

Khi đó có thể tạo **entity liên kết** (`ProjectAssignment`) thay vì một link table ẩn trong `@OneToMany`:

```java
@Entity
public class ProjectAssignment {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private TaskItem task;

    private Instant assignedAt;
}
```

Đoạn code minh họa phải bổ sung import, constructor, getters và table/column mapping để thành một lớp hoàn chỉnh. Phía `Project` có thể dùng:

```java
@OneToMany(mappedBy = "project")
private List<ProjectAssignment> assignments;
```

Mỗi **liên kết** bây giờ có ID/lifecycle riêng. Đây là mô hình khác với `@OneToMany` một chiều; nó phù hợp khi trạng thái gán có ý nghĩa độc lập hoặc một task được nhiều project sử dụng với vai trò khác nhau.

## 18. Migration giữa hai kiểu lưu

Nếu đang có:

```text
projects + task_items + project_tasks
```

và muốn chuyển sang:

```text
projects + task_items(project_id)
```

không thể chỉ thay annotation; cần migration dữ liệu:

1. Kiểm tra có task nào liên kết với **hơn một** project không. Nếu có, quan hệ không chuyển thẳng vào một cột FK được.
2. Thêm `project_id` vào `task_items`, ban đầu có thể nullable để backfill.
3. Chuyển từng `(project_id, task_id)` từ link table sang cột FK trong bảng con.
4. Quyết định xử lý task không có link; có được để `NULL` hay phải gán owner?
5. Thêm FK/index và `NOT NULL` khi đáp ứng dữ liệu/đường ghi mới.
6. Thay mapping và truy vấn trong ứng dụng, bảo đảm không có hai luồng ghi quan hệ mâu thuẫn.
7. Xóa bảng link sau khi code mới đã chạy ổn định và có kế hoạch rollback.

Chiều ngược lại cũng cần tạo bảng liên kết, backfill từ `task_items.project_id` và chuyển các constraint phù hợp.

Trong triển khai rolling deployment, cần tính tới thời gian mã cũ và mã mới cùng hoạt động. Không xóa bảng/cột đang được phiên bản cũ sử dụng khi chưa có kế hoạch tương thích.

## 19. Lỗi phổ biến và cách nhận diện

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Hibernate tạo thêm bảng `project_tasks` ngoài ý muốn | Dùng `@OneToMany` một chiều mặc định | Đặt `@JoinTable` để kiểm soát hoặc `@JoinColumn` nếu muốn FK child |
| `@JoinColumn` trên `Project` nhưng không thấy cột mới ở `projects` | FK của unidirectional OneToMany nằm ở **bảng đích** | Kiểm tra `task_items.project_id` |
| Task INSERT lỗi `project_id NOT NULL` | Hibernate có thể insert child trước rồi update FK | Xem SQL thật; cân nhắc bidirectional `@ManyToOne` |
| Gỡ một task dẫn tới rất nhiều DELETE/INSERT link | Hibernate đồng bộ collection bằng cách tạo lại link rows | Đo workload; xem xét FK trực tiếp hoặc hai chiều |
| Một task xuất hiện trong hai project | Bảng link thiếu UNIQUE(task_id), hoặc domain thực tế là ManyToMany | Bổ sung constraint và chọn đúng cardinality |
| `mappedBy` trỏ tới field không tồn tại | Con không có thuộc tính quan hệ ngược | Bỏ `mappedBy` cho một chiều hoặc thêm `@ManyToOne` để thành hai chiều |
| Gỡ task nhưng hàng con vẫn tồn tại | Chỉ gỡ association, không có orphan removal | Xác định muốn unlink hay delete |
| Xóa project làm mất tasks | Cascade REMOVE/ALL, orphanRemoval hoặc database cascade | Thiết kế lại vòng đời và quy tắc xóa |
| FK NULL không được phép khi unlink | Bảng con dùng NOT NULL nhưng không xóa con | Chọn delete/chuyển owner hoặc thay schema nghiệp vụ |
| LazyInitializationException khi trả API | Collection LAZY sau khi session đóng | Fetch trong service/transaction và chuyển DTO |
| Thứ tự List thay đổi sau reload | Thiếu persistent ordering | Dùng `@OrderColumn` hoặc `@OrderBy` phù hợp |
| Gỡ phần tử khỏi Set không được | equals/hashCode hoặc object identity chưa ổn định | Kiểm tra cách nhận diện entity và lifecycle |
| Merge collection gây mất cập nhật mới | Detached state cũ ghi đè toàn bộ | Load managed rồi áp dụng thao tác cụ thể |
| Đổi annotation mà dữ liệu không đúng | Chưa migrate schema/dữ liệu | Lập migration, backfill và constraint đồng bộ |

## 20. Tự kiểm tra qua các tình huống

### Bài tập 1: Mặc định lưu quan hệ ra sao?

```java
@Entity
class Project {
    @Id
    Long id;

    @OneToMany
    List<TaskItem> tasks;
}
```

`TaskItem` không có `project`, và không khai báo `@JoinColumn`. Hibernate thường lưu quan hệ ở đâu?

**Đáp án:** Trong một **join table** giữa Project và TaskItem. Tên bảng/cột được suy từ quy tắc mặc định và naming strategy nếu không khai báo tường minh.

### Bài tập 2: FK ở đâu?

```java
@OneToMany
@JoinColumn(name = "project_id")
private Set<TaskItem> tasks;
```

**Đáp án:** Trong bảng của **TaskItem**, không phải bảng của Project. `@JoinColumn` đặt trên collection của parent để điều khiển quan hệ một chiều.

### Bài tập 3: Tại sao phải UNIQUE(task_id)?

Bảng link có `(project_id=42, task_id=101)` và `(project_id=43, task_id=101)`. Điều gì sai?

**Đáp án:** Một task có hai owner; điều này không phù hợp với quan hệ 1:N. `UNIQUE(task_id)` chặn tình huống đó; nếu nghiệp vụ thật sự cần chia sẻ, nên dùng mô hình khác.

### Bài tập 4: Gỡ task có xóa task không?

Mapping không có `orphanRemoval`. Gọi `project.removeTask(task)`, rồi commit. Task có bị `DELETE` khỏi `task_items` không?

**Đáp án:** Không mặc nhiên. Thường chỉ association bị gỡ; muốn xóa entity phải có quy tắc xóa phù hợp. Nếu FK `NOT NULL` với kiểu FK trực tiếp, chỉ unlink mà không xóa có thể bị constraint từ chối.

### Bài tập 5: Xóa một task gây nhiều SQL?

Vì sao `tasks.remove(x)` có thể khiến Hibernate xóa hàng trăm hàng trong bảng link rồi chèn lại?

**Đáp án:** Đây là chiến lược đồng bộ collection mà Hibernate mô tả cho unidirectional OneToMany dùng bảng liên kết. Nếu collection lớn và cập nhật thường xuyên, cân nhắc thay mapping dựa trên SQL và hiệu năng thực.

### Bài tập 6: `mappedBy` không hoạt động?

Tại sao `@OneToMany(mappedBy="project")` báo lỗi khi `TaskItem` không khai báo `project`?

**Đáp án:** `mappedBy` phải trỏ đến property quan hệ ngược trên child; không dùng nó cho một chiều. Nếu muốn hai chiều, thêm `TaskItem.project @ManyToOne` và duy trì hai phía nhất quán.

### Bài tập 7: Task bắt buộc thuộc project?

Database dùng `task_items.project_id NOT NULL`, nhưng khi persist bằng unidirectional `@JoinColumn` Hibernate thực hiện INSERT child trước khi UPDATE FK. Cần xử lý thế nào?

**Đáp án:** Xác nhận mapping/SQL trên phiên bản thực tế; có thể cân nhắc quan hệ hai chiều `@ManyToOne` sở hữu FK để Hibernate biết FK trong state của child ngay khi INSERT. Không bỏ NOT NULL nếu yêu cầu nghiệp vụ thật sự bắt buộc.

### Bài tập 8: Thứ tự kéo-thả?

Nếu người dùng muốn chuyển một task từ vị trí 5 lên vị trí 2, dùng `@OrderBy("title")` có hợp lý không?

**Đáp án:** Không. `@OrderBy` sắp xếp theo giá trị `title`; `@OrderColumn` hoặc cơ chế sort-order nghiệp vụ mới biểu diễn vị trí kéo-thả.

## 21. Nguồn tài liệu chính thức

- [Jakarta Persistence 3.2 — `@OneToMany`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToMany.html): cardinality, `mappedBy`, cascade, orphan removal và các mapping FK/join table.
- [Jakarta Persistence 3.2 — `@JoinTable`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/JoinTable.html): owning side, `joinColumns`, `inverseJoinColumns`, quy tắc tên bảng.
- [Jakarta Persistence 3.2 — `@JoinColumn`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/JoinColumn.html): vị trí foreign-key column và cách ánh xạ quan hệ một chiều.
- [Jakarta Persistence 3.2 — Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): các nguyên tắc sở hữu quan hệ, default mapping, vòng đời và transaction.
- [Hibernate ORM 7.2 User Guide — `@OneToMany`](https://docs.hibernate.org/orm/7.2/userguide/html_single/#associations-one-to-many): ví dụ SQL của unidirectional OneToMany và chi phí xóa/chèn lại bảng liên kết.
- [Hibernate ORM User Guide bản ổn định](https://docs.hibernate.org/stable/orm/userguide/html_single/): collection semantics, fetch plan và lifecycle; dùng tài liệu đúng phiên bản dự án.

Các ví dụ dùng namespace `jakarta.persistence.*`. Dự án JPA cũ có thể dùng `javax.persistence.*` và cần đối chiếu version Jakarta Persistence/Hibernate trước khi nâng cấp. SQL minh họa không phải kết quả đã chạy, và cú pháp DDL có thể thay đổi giữa PostgreSQL, MySQL, Oracle hoặc DBMS khác.

## Kết luận

`@OneToMany` **một chiều** cho phép entity cha quản lý collection entity con mà child không có quan hệ object ngược. Khi không cấu hình riêng, Hibernate thường dùng **bảng liên kết**; khai báo `@JoinColumn` trên collection sẽ chuyển quan hệ sang **khóa ngoại nằm ở bảng con**.

Với bảng liên kết, cần bảo đảm FK, PK và thường là `UNIQUE(child_id)` để một con có tối đa một cha; thay đổi collection có thể gây nhiều thao tác xóa/chèn lại link rows. Với FK trực tiếp, schema gọn hơn nhưng việc Hibernate đồng bộ FK có thể phát thêm `UPDATE` và cần đặc biệt lưu ý constraint `NOT NULL`.

Hãy chọn mapping theo **schema, vòng đời con, tần suất thay đổi, khả năng chia sẻ child, kế hoạch fetch và SQL thực tế**. Nếu cần thao tác ghi thường xuyên, truy vấn ngược từ con hoặc FK bắt buộc khi INSERT, quan hệ hai chiều với `@ManyToOne` sở hữu FK thường là một phương án đáng đánh giá. Dù chọn cách nào, hãy giữ nhất quán giữa **mapping Java, constraint database và transaction**.
