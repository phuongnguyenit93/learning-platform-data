# Ánh xạ ManyToMany qua JoinTable

Trong mô hình đối tượng Java, một sinh viên có thể đăng ký nhiều khóa học; đồng thời một khóa học có thể có nhiều sinh viên. Đây là quan hệ **nhiều-nhiều** (*many-to-many*). Trong cơ sở dữ liệu quan hệ, liên kết đó thường được lưu qua một **bảng nối** (*join table*), thay vì một cột chứa danh sách ID.

JPA/Jakarta Persistence cung cấp `@ManyToMany` để mô tả association giữa các entity và `@JoinTable` để xác định tên bảng nối, các cột khóa ngoại và những thông tin mapping liên quan. Tuy chỉ cần vài dòng annotation, một thiết kế đúng phải giải quyết thêm vấn đề về **phía sở hữu quan hệ**, cách lưu/xóa liên kết, tính duy nhất của cặp khóa, vòng đời entity, fetch strategy và khả năng mở rộng khi bảng nối có thuộc tính nghiệp vụ.

Bài học này nằm trong chương **Quan hệ nhiều-nhiều**, thuộc chủ đề **Data Persistence Relational Access ORM JPA**. Các ví dụ sử dụng package `jakarta.persistence`; dự án JPA cũ có thể dùng namespace `javax.persistence` phù hợp với phiên bản của mình.

## 1. Mô hình dữ liệu: tại sao cần bảng thứ ba?

Giả sử có hai đối tượng:

- `Student`: sinh viên, có `id`, `fullName`.
- `Course`: khóa học, có `id`, `title`.

Một sinh viên có thể học nhiều khóa, và một khóa có nhiều sinh viên. Nếu thêm một cột `course_id` trong `students` thì mỗi sinh viên chỉ liên kết được một khóa. Nếu thêm một cột `student_id` trong `courses` thì mỗi khóa chỉ liên kết được một sinh viên.

Ta cũng không nên lưu một chuỗi danh sách ID như `"10,11,12"` trong một cột: database khó áp dụng foreign key trên từng giá trị, khó index và JOIN, cũng như khó kiểm soát trùng lặp và cập nhật đồng thời.

Giải pháp thường dùng là ba bảng:

```text
students                  student_courses               courses
┌────┬─────────────┐       ┌────────────┬───────────┐    ┌────┬───────────┐
│ id │ full_name   │       │ student_id │ course_id │    │ id │ title     │
├────┼─────────────┤       ├────────────┼───────────┤    ├────┼───────────┤
│  1 │ Nguyễn An   │◄──────│ 1          │ 10        │───►│ 10 │ Java Core │
│  2 │ Trần Bình   │◄──┐   │ 1          │ 11        │───►│ 11 │ JPA       │
└────┴─────────────┘   └───│ 2          │ 11        │────└────┴───────────┘
                          └────────────┴───────────┘
```

Một hàng trong bảng `student_courses` biểu diễn một **liên kết**:

| student_id | course_id | Ý nghĩa |
| ---: | ---: | --- |
| 1 | 10 | Sinh viên 1 đăng ký khóa 10 |
| 1 | 11 | Sinh viên 1 đăng ký khóa 11 |
| 2 | 11 | Sinh viên 2 đăng ký khóa 11 |

Nhờ thiết kế này, cùng một sinh viên có thể xuất hiện ở nhiều hàng liên kết, và cùng một khóa học cũng có thể xuất hiện ở nhiều hàng. Nhưng cặp `(student_id, course_id)` thường phải duy nhất để tránh một lần đăng ký bị nhân bản.

### Cấu trúc SQL minh họa

```sql
CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE courses (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE student_courses (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,

    CONSTRAINT pk_student_courses
        PRIMARY KEY (student_id, course_id),

    CONSTRAINT fk_sc_student
        FOREIGN KEY (student_id) REFERENCES students(id),

    CONSTRAINT fk_sc_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
);
```

- Primary key tổng hợp ngăn trùng cặp liên kết.
- Foreign key ngăn liên kết tới một sinh viên hoặc khóa học không tồn tại.
- Bảng nối không cần một bản ghi riêng khi sinh viên chưa học khóa nào.
- Bảng nối cũng không cần một bản ghi riêng khi khóa học chưa có sinh viên.

Đây là cấu trúc dữ liệu thường được `@ManyToMany` ánh xạ.

## 2. Ý nghĩa của `@ManyToMany` và `@JoinTable`

Trong class `Student`, mapping có thể viết:

```java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
```

Giải thích:

| Thành phần | Ý nghĩa |
| --- | --- |
| `@ManyToMany` | Mô tả quan hệ nhiều-nhiều giữa `Student` và `Course` |
| `fetch = FetchType.LAZY` | Chọn chiến lược tải trễ; đây cũng là mặc định của `@ManyToMany` |
| `@JoinTable(name = "student_courses")` | Bảng vật lý lưu các cặp liên kết |
| `joinColumns` | Cột trong bảng nối tham chiếu entity **đang chứa field**, tức `Student` |
| `inverseJoinColumns` | Cột trong bảng nối tham chiếu entity **đích**, tức `Course` |
| `Set<Course>` | Collection Java biểu diễn tập khóa học của sinh viên |

Nhớ quy tắc:

**`joinColumns` trỏ về entity sở hữu mapping; `inverseJoinColumns` trỏ tới entity liên quan.**

Nếu annotation này nằm trong `Course` với collection `Set<Student> students` và `Course` được chọn làm owning side thì hai cột đảo vai trò:

```java
@ManyToMany
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(name = "course_id"),
    inverseJoinColumns = @JoinColumn(name = "student_id")
)
private Set<Student> students = new HashSet<>();
```

Bảng SQL vẫn có thể là `student_courses`. Khác biệt là class đang giữ mapping owner.

## 3. ManyToMany đơn hướng: Student biết Course

Trước tiên, ta xây dựng quan hệ **đơn hướng** (*unidirectional*): `Student` có collection các `Course`; class `Course` không có collection sinh viên ngược lại.

### `Course.java`

```java
import jakarta.persistence.*;

@Entity
@Table(name = "courses")
public class Course {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    protected Course() {
        // Constructor cho JPA.
    }

    public Course(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        this.title = title.trim();
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

### `Student.java`

```java
import jakarta.persistence.*;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "students")
public class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    protected Student() {
        // Constructor cho JPA.
    }

    public Student(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("fullName");
        }
        this.fullName = fullName.trim();
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Set<Course> getCourses() {
        return Collections.unmodifiableSet(courses);
    }

    public void enroll(Course course) {
        if (course == null) {
            throw new IllegalArgumentException("course");
        }
        courses.add(course);
    }

    public void withdraw(Course course) {
        if (course != null) {
            courses.remove(course);
        }
    }
}
```

Điểm quan trọng:

- `Student.courses` là phía duy nhất ánh xạ association.
- `Course` không có `getStudents()`.
- Bảng nối `student_courses` vẫn cho phép tìm các sinh viên của một khóa bằng JPQL hoặc SQL.
- Không cần tạo một Java entity thứ ba cho mỗi hàng nối nếu bảng chỉ biểu diễn sự hiện diện/vắng mặt của liên kết.
- Collection được khởi tạo để object mới có thể gọi `enroll()` an toàn; khi entity được tải, provider có thể thay bằng persistent collection wrapper.

## 4. Tạo entity mới và lưu liên kết

Đoạn sau dùng `EntityManager` với transaction resource-local:

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    em.getTransaction().begin();

    Course javaCore = new Course("Java Core");
    Course jpa = new Course("JPA và ORM");
    Student an = new Student("Nguyễn An");

    em.persist(javaCore);
    em.persist(jpa);
    em.persist(an);

    an.enroll(javaCore);
    an.enroll(jpa);

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Dữ liệu tương đương sau khi commit thành công:

```text
students:
  (student_id_of_an, "Nguyễn An")

courses:
  (course_id_of_javaCore, "Java Core")
  (course_id_of_jpa, "JPA và ORM")

student_courses:
  (student_id_of_an, course_id_of_javaCore)
  (student_id_of_an, course_id_of_jpa)
```

Provider và database quyết định ID thực tế được sinh. Không nên giả định ID trong ví dụ sẽ luôn là 1, 10 hoặc 11.

### Vì sao gọi `persist` cho từng Course?

Mapping `@ManyToMany` ở trên không có `cascade = CascadeType.PERSIST`. Khi đó, `persist(student)` không có hợp đồng tự động lưu mọi `Course` new/transient trong collection. Nếu thêm một `new Course(...)` nhưng không persist, thao tác có thể thất bại khi provider đồng bộ liên kết.

Trong mô hình này, `Course` có vòng đời độc lập: khóa học được quản lý riêng và sinh viên chỉ tham gia. Persist riêng từng Course là lựa chọn rõ ràng.

### Thời điểm phát SQL

`persist()` đưa một entity new vào persistence context theo ngữ nghĩa JPA; `flush()` đồng bộ các thay đổi đang chờ với database; `commit()` xác nhận transaction. Provider có thể gom hoặc sắp các thao tác SQL khác nhau tùy khóa sinh tự động, batch configuration và ràng buộc tham chiếu.

Không nên kỳ vọng mỗi lần gọi `enroll()` lập tức có một câu `INSERT`.

## 5. Thêm và xóa liên kết giữa các entity đã tồn tại

Khi Student và Course đã có trong database:

```java
em.getTransaction().begin();

Student student = em.find(Student.class, studentId);
Course course = em.find(Course.class, courseId);

if (student == null || course == null) {
    throw new IllegalArgumentException("Student or Course not found");
}

student.enroll(course);
em.getTransaction().commit();
```

Nếu chưa có liên kết, mục tiêu đồng bộ về mặt SQL là:

```sql
INSERT INTO student_courses(student_id, course_id)
VALUES (?, ?);
```

Để rút khỏi khóa học:

```java
em.getTransaction().begin();

Student student = em.find(Student.class, studentId);
Course course = em.find(Course.class, courseId);

if (student == null || course == null) {
    throw new IllegalArgumentException("Student or Course not found");
}

student.withdraw(course);
em.getTransaction().commit();
```

Tác động mong muốn:

```sql
DELETE FROM student_courses
WHERE student_id = ? AND course_id = ?;
```

**Xóa hàng nối không có nghĩa xóa Course hoặc Student.** Sinh viên rút khỏi một lớp không khiến khóa học biến mất khỏi hệ thống.

Trong một số mapping/collection, provider có thể dùng chiến lược SQL phức tạp hơn việc xóa đúng một hàng; hãy xem SQL thực tế nếu số câu lệnh là tiêu chí hiệu năng.

## 6. ManyToMany hai hướng với `mappedBy`

Khi cần từ `Course` đi đến tập sinh viên đã đăng ký, ta bổ sung collection ngược.

**Student là owning side:**

```java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
```

**Course là inverse side:**

```java
@ManyToMany(mappedBy = "courses", fetch = FetchType.LAZY)
private Set<Student> students = new HashSet<>();
```

Với mapping này:

- `Student.courses` sở hữu mapping và chỉ ra join table.
- `Course.students` là phía đối ứng.
- `mappedBy = "courses"` trỏ tới **tên field Java `Student.courses`**.
- Hai phía cùng biểu diễn **một association** và cùng một bảng `student_courses`.
- Không khai báo thêm `@JoinTable` khác trên `Course.students` cho cùng quan hệ.

Sơ đồ:

```text
Student.courses                         Course.students
@ManyToMany                              @ManyToMany(mappedBy="courses")
@JoinTable("student_courses")
        │                                       │
        │       owning / inverse                │
        └───────── student_courses ─────────────┘
                  (student_id, course_id)
```

**Owning side là khái niệm ánh xạ JPA**, không có nghĩa Student quan trọng hơn Course về nghiệp vụ. Có thể chọn Course sở hữu nếu thiết kế phù hợp, nhưng khi đó phải đảo vai trò của `@JoinTable` và `mappedBy` nhất quán.

### Lỗi thường gặp khi dùng `mappedBy`

Sai:

```java
@ManyToMany(mappedBy = "student_courses")
private Set<Student> students;
```

Bởi vì `student_courses` là tên bảng SQL, không phải thuộc tính Java trên Student.

Đúng:

```java
@ManyToMany(mappedBy = "courses")
private Set<Student> students;
```

## 7. Đồng bộ collection ở cả hai phía

Khi quan hệ hai hướng, hai collection trong bộ nhớ cùng phản ánh một liên kết.

Nếu chỉ sửa `Student.courses`:

```java
// Giả sử code có quyền sửa collection.
student.getCourses().add(course);
```

thì `Course.students` có thể chưa được cập nhật. Nếu chỉ sửa `Course.students`, owning side không đổi, provider không có nghĩa vụ coi đó là yêu cầu ghi một liên kết mới.

Do đó, nên có helper ở owning side và method nội bộ ở phía đối ứng.

**Trong Student:**

```java
public void enroll(Course course) {
    if (course == null) {
        throw new IllegalArgumentException("course");
    }

    if (courses.add(course)) {
        course.attachStudent(this);
    }
}

public void withdraw(Course course) {
    if (course != null && courses.remove(course)) {
        course.detachStudent(this);
    }
}
```

**Trong Course:**

```java
@ManyToMany(mappedBy = "courses")
private Set<Student> students = new HashSet<>();

public Set<Student> getStudents() {
    return Collections.unmodifiableSet(students);
}

void attachStudent(Student student) {
    students.add(student);
}

void detachStudent(Student student) {
    students.remove(student);
}
```

Cách dùng:

```java
student.enroll(course);
student.withdraw(course);
```

Sau `enroll(course)`, object graph cùng ghi nhận liên kết ở hai phía. Method nội bộ của Course không gọi ngược `Student.enroll()` để tránh đệ quy.

Các helper trên dựa vào `Set.add/remove`. Với entity JPA có generated ID, chiến lược `equals()/hashCode()` cần ổn định: nếu hash code thay đổi khi ID từ `null` thành giá trị DB trong lúc object đã nằm trong `HashSet`, việc kiểm tra hoặc xóa phần tử có thể sai. Cần quy ước equality phù hợp với vòng đời entity/proxy và các persistence context khác nhau.

**Set chỉ bảo vệ tập hợp theo Java semantics trong một object graph; database vẫn cần unique constraint để xử lý concurrency.**

## 8. `@JoinTable` khai báo tên cột và khóa tham chiếu

Có thể chỉ rõ cột được tham chiếu bên bảng Student/Course:

```java
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(
        name = "student_id",
        referencedColumnName = "id"
    ),
    inverseJoinColumns = @JoinColumn(
        name = "course_id",
        referencedColumnName = "id"
    )
)
```

`referencedColumnName = "id"` chỉ tên cột khóa bên bảng entity được tham chiếu. Với khóa chính đơn giản `id`, thường có thể bỏ để dùng mặc định.

Tóm tắt các tên:

| Thành phần | Là tên gì? |
| --- | --- |
| `Student.courses` | Thuộc tính Java, association owning side |
| `Course.students` | Thuộc tính Java, association inverse side |
| `mappedBy = "courses"` | Tên thuộc tính Java ở phía owning |
| `@JoinTable(name = "student_courses")` | Tên bảng SQL trung gian |
| `@JoinColumn(name = "student_id")` | Cột SQL trong bảng nối trỏ tới Student |
| `@JoinColumn(name = "course_id")` | Cột SQL trong bảng nối trỏ tới Course |

Đừng trộn tên field Java, tên cột và tên bảng khi viết `mappedBy`.

### Schema và ràng buộc bổ sung

```java
@ManyToMany
@JoinTable(
    name = "student_courses",
    schema = "academy",
    joinColumns = @JoinColumn(
        name = "student_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_sc_student")
    ),
    inverseJoinColumns = @JoinColumn(
        name = "course_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_sc_course")
    ),
    uniqueConstraints = @UniqueConstraint(
        name = "uq_sc_pair",
        columnNames = {"student_id", "course_id"}
    )
)
private Set<Course> courses = new HashSet<>();
```

`schema = "academy"` là ví dụ về namespace SQL khi database hỗ trợ. Các annotation mô tả metadata của mapping/schema generation; chúng không tự sửa một schema production đang được quản lý bằng migration độc lập.

Khi đã dùng `PRIMARY KEY(student_id, course_id)`, thông thường không cần thêm một unique constraint trùng chính xác trên cùng cặp cột, vì mục đích trùng lặp.

## 9. Index bảng nối cho cả hai chiều truy vấn

Một khóa chính tổng hợp `(student_id, course_id)` thường tạo index thuận tiện cho truy vấn xuất phát từ `student_id`:

```sql
SELECT course_id
FROM student_courses
WHERE student_id = 1;
```

Nhưng để lấy sinh viên của một khóa học:

```sql
SELECT student_id
FROM student_courses
WHERE course_id = 11;
```

có thể hữu ích khi có thêm index theo thứ tự ngược:

```sql
CREATE INDEX idx_sc_course_student
ON student_courses(course_id, student_id);
```

Quyết định tạo index dựa vào kích thước bảng, truy vấn, ràng buộc hiện có và kế hoạch thực thi của database. Mapping hai hướng trong Java **không có nghĩa JPA đã tạo index tối ưu cho mọi truy vấn hai chiều**.

## 10. Truy vấn JPQL qua ManyToMany

JPA cho phép JPQL đi theo collection association thay vì viết trực tiếp tên join table.

### Các khóa học của một sinh viên

```java
List<Course> courses = em.createQuery(
    "SELECT c FROM Student s JOIN s.courses c " +
    "WHERE s.id = :sid",
    Course.class
).setParameter("sid", studentId)
 .getResultList();
```

Provider tự dịch phép JOIN association thành SQL dùng bảng nối phù hợp.

### Các sinh viên của một khóa học khi mapping hai hướng

```java
List<Student> students = em.createQuery(
    "SELECT s FROM Course c JOIN c.students s " +
    "WHERE c.id = :cid",
    Student.class
).setParameter("cid", courseId)
 .getResultList();
```

### Query ngược mà không cần mapping hai hướng

Kể cả khi `Course` không có `students`, ta vẫn có thể xuất phát từ Student:

```java
List<Student> students = em.createQuery(
    "SELECT DISTINCT s FROM Student s JOIN s.courses c " +
    "WHERE c.id = :cid",
    Student.class
).setParameter("cid", courseId)
 .getResultList();
```

Vì vậy, không cần thêm hai hướng chỉ để hỗ trợ một truy vấn ngược qua repository.

### Kiểm tra một liên kết

```java
boolean exists = !em.createQuery(
    "SELECT s.id FROM Student s JOIN s.courses c " +
    "WHERE s.id = :sid AND c.id = :cid",
    Long.class
).setParameter("sid", studentId)
 .setParameter("cid", courseId)
 .setMaxResults(1)
 .getResultList()
 .isEmpty();
```

Đây là cách biểu diễn rõ truy vấn kiểm tra tồn tại liên kết, thay vì phải tải toàn bộ collection lớn chỉ để gọi `contains()`.

## 11. Fetch LAZY và N+1

Mặc định `@ManyToMany` sử dụng `FetchType.LAZY`. Provider có thể trì hoãn nạp các khóa học cho tới khi collection được truy cập:

```java
Student student = em.find(Student.class, studentId);
int count = student.getCourses().size();
```

Trong một số provider, thao tác `size()` có thể kích hoạt SQL đọc collection; nếu persistence context đã đóng và collection chưa được tải, truy cập lazy có thể thất bại.

### Ví dụ N+1

```java
List<Student> students = em.createQuery(
    "SELECT s FROM Student s",
    Student.class
).getResultList();

for (Student s : students) {
    System.out.println(s.getCourses().size());
}
```

Có thể xảy ra một truy vấn lấy Student, rồi một truy vấn cho mỗi Student để tải khóa học. Điều này gọi là N+1. Không nên sửa bằng cách đặt tất cả collection thành `EAGER` vì có thể tải thừa dữ liệu trong các use case khác.

### Fetch join khi cần object graph

```java
List<Student> students = em.createQuery(
    "SELECT DISTINCT s FROM Student s " +
    "LEFT JOIN FETCH s.courses " +
    "WHERE s.id IN :ids",
    Student.class
).setParameter("ids", selectedStudentIds)
 .getResultList();
```

`LEFT JOIN FETCH` giữ cả sinh viên chưa có khóa học và yêu cầu tải courses. `DISTINCT` diễn đạt ý định tránh trùng root Student khi JOIN tạo nhiều hàng.

**Cẩn trọng với pagination:** collection fetch join có thể nhân nhiều hàng SQL cho mỗi Student; giới hạn trực tiếp bằng `setMaxResults` có thể khiến phân trang bị sai hoặc provider xử lý kém hiệu quả. Một chiến lược là query trang ID trước rồi fetch dữ liệu quan hệ theo tập ID, hoặc dùng DTO projection nếu không cần managed entity.

### Entity graph

```java
EntityGraph<Student> graph =
    em.createEntityGraph(Student.class);
graph.addAttributeNodes("courses");

Map<String, Object> hints = Map.of(
    "jakarta.persistence.fetchgraph", graph
);

Student student = em.find(Student.class, studentId, hints);
```

Entity graph kiểm soát fetch plan theo use case; nó không thay đổi owning side hoặc schema join table.

## 12. Cascade và sự khác biệt giữa xóa liên kết với xóa entity

Các Student thường chia sẻ Course. Do vậy, hãy cân nhắc kỹ trước khi dùng:

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses;
```

`CascadeType.ALL` bao gồm `REMOVE`. Nếu xóa một Student mà remove được cascade sang các Course liên quan, các khóa học dùng chung có thể bị xóa sai hoặc phát sinh vi phạm FK.

Phân biệt:

| Thao tác | Ý nghĩa |
| --- | --- |
| `student.withdraw(course)` | Xóa liên kết trong join table |
| `em.remove(student)` | Xóa entity Student, cùng việc xử lý liên kết liên quan |
| `em.remove(course)` | Xóa entity Course, phải xét những liên kết đang tồn tại |
| `CascadeType.REMOVE` | Lan truyền thao tác xóa entity, không phải chỉ xóa hàng nối |

`@ManyToMany` **không có thuộc tính `orphanRemoval`** trong JPA chuẩn. Một Course không còn nằm trong collection của một Student vẫn có thể được các Student khác sử dụng; nó không mặc nhiên là entity mồ côi.

Trong nhiều ứng dụng, nên không bật cascade ở `@ManyToMany`, persist Course riêng và chỉ quản lý quan hệ khi đăng ký/rút học. Nếu có use case cụ thể cần `CascadeType.PERSIST`, hãy xác định chính xác vòng đời và tránh thêm REMOVE chỉ cho tiện.

## 13. Collection Java không thay ràng buộc SQL

`Set<Course>` loại trùng theo `equals()/hashCode()` trong JVM. Nhưng hai request đồng thời có thể chạy trong hai persistence context:

```text
Transaction T1                 Transaction T2
thêm Student 1–Course 10       thêm Student 1–Course 10
            │                              │
            └──── tranh chấp cùng cặp ─────┘
```

`Set` của T1 không thể nhìn thấy tập của T2. Nếu cả hai cùng cố insert, unique constraint hoặc primary key tổng hợp trên bảng nối ngăn hai hàng trùng cặp.

Do đó:

- Dùng collection semantics phù hợp ở Java.
- Dùng `PRIMARY KEY` hoặc `UNIQUE` phù hợp ở database.
- Xử lý exception hoặc cạnh tranh transaction theo chính sách nghiệp vụ.
- Không chỉ dựa vào một phép `contains()` trước khi ghi để bảo đảm không trùng khi nhiều request cùng chạy.

`@Version` trên entity owner có thể liên quan tới optimistic locking, nhưng không nên mặc định mọi provider sẽ nâng version cho mọi biến đổi bảng nối theo một cách giống nhau. Với yêu cầu concurrency nghiêm ngặt, kiểm chứng SQL/locking theo provider và database thực tế.

## 14. Khi bảng nối cần dữ liệu nghiệp vụ: mô hình Enrollment

`@ManyToMany` phù hợp khi bảng `student_courses` chỉ có các khóa liên kết. Nhưng nếu hệ thống cần lưu:

- `enrolledAt`: thời điểm đăng ký.
- `status`: đang học, hoàn thành, đã rút.
- `grade`: điểm số.
- `approvedBy`: người phê duyệt.

thì một hàng nối đã có **đời sống nghiệp vụ riêng**. Collection `Set<Course>` không có chỗ trực tiếp để chứa `grade` ứng với từng cặp Student–Course.

Khi đó nên tạo entity `Enrollment`, thay một ManyToMany trực tiếp bằng hai ManyToOne:

```text
Student 1 ── * Enrollment * ── 1 Course
                │
                ├── enrolledAt
                ├── status
                └── grade
```

### Cấu trúc SQL

```sql
CREATE TABLE enrollments (
    student_id BIGINT NOT NULL REFERENCES students(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    enrolled_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    grade DECIMAL(5,2),
    PRIMARY KEY (student_id, course_id)
);
```

### Khóa tổng hợp với `@Embeddable`

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class EnrollmentId implements Serializable {

    private Long studentId;
    private Long courseId;

    protected EnrollmentId() {}

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = Objects.requireNonNull(studentId);
        this.courseId = Objects.requireNonNull(courseId);
    }

    public Long getStudentId() { return studentId; }
    public Long getCourseId() { return courseId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EnrollmentId value)) return false;
        return Objects.equals(studentId, value.studentId)
            && Objects.equals(courseId, value.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

### Entity liên kết với `@EmbeddedId` và `@MapsId`

```java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "enrollments")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @MapsId("studentId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @MapsId("courseId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private Instant enrolledAt;

    @Column(nullable = false, length = 20)
    private String status;

    protected Enrollment() {}

    public Enrollment(Student student, Course course, Instant time) {
        if (student == null || course == null || time == null) {
            throw new IllegalArgumentException("Missing enrollment data");
        }
        if (student.getId() == null || course.getId() == null) {
            throw new IllegalArgumentException(
                "Persist Student and Course before Enrollment"
            );
        }

        this.student = student;
        this.course = course;
        this.id = new EnrollmentId(student.getId(), course.getId());
        this.enrolledAt = time;
        this.status = "IN_PROGRESS";
    }

    public EnrollmentId getId() { return id; }

    public void complete() {
        status = "COMPLETED";
    }
}
```

`@MapsId` dùng association để xác định thành phần khóa tổng hợp. Ví dụ yêu cầu Student và Course đã có ID; nếu tạo đồng thời với identity sinh từ database, cần sắp xếp thao tác persist/cascade phù hợp.

Phía Student có thể thay `Set<Course>` bằng:

```java
@OneToMany(mappedBy = "student")
private Set<Enrollment> enrollments = new HashSet<>();
```

Phía Course có thể có:

```java
@OneToMany(mappedBy = "course")
private Set<Enrollment> enrollments = new HashSet<>();
```

Không nên giữ thêm mapping `@ManyToMany` ghi cùng bảng với Enrollment một cách vô thức, vì dễ có hai đường cập nhật association dẫn tới xung đột.

### ID riêng cho Enrollment

Nếu Enrollment cần ID độc lập, có thể dùng `@Id @GeneratedValue` và vẫn khai báo hai `@ManyToOne`. Khi business rule là một sinh viên chỉ có một đăng ký cho một khóa, giữ unique constraint trên cặp student/course. Nếu cho phép đăng ký nhiều lần theo học kỳ, phải thiết kế lại khóa nghiệp vụ, chẳng hạn có `term_id` hoặc `attempt`.

## 15. Khi nào chọn ManyToMany, khi nào chọn association entity?

| Yêu cầu | `@ManyToMany + @JoinTable` | `Enrollment` entity |
| --- | --- | --- |
| Liên kết chỉ có hai khóa ngoại | Gọn, phù hợp | Có thể nhưng thêm độ phức tạp |
| Liên kết có trạng thái/điểm/ngày đăng ký | Không biểu diễn trực tiếp | Phù hợp |
| Cần audit hoặc xóa mềm từng liên kết | Hạn chế | Dễ mô hình hóa |
| Cần ID riêng cho từng liên kết | Không có entity đại diện | Có thể |
| Cần cập nhật từng liên kết theo quy tắc nghiệp vụ | Chỉ thông qua thay đổi collection | Có method/lifecycle riêng |
| Hai entity có vòng đời độc lập | Phù hợp nếu cascade chọn đúng | Vẫn phù hợp |

Một quy tắc thực dụng: **nếu bảng nối bắt đầu mang thông tin mà nghiệp vụ cần đọc, cập nhật hoặc audit, nên xem nó là entity thay vì chỉ là bảng ẩn của ManyToMany**.

## 16. Migration và thay đổi mapping

### Đổi tên bảng nối

Nếu database hiện có `student_course_links(student_fk, course_fk)` mà code mới chuyển sang `student_courses(student_id, course_id)`, chỉ sửa `@JoinTable` không tự di chuyển dữ liệu. Có thể tạo bảng mới rỗng hoặc khiến câu SQL truy cập sai bảng.

Cần migration DDL/dữ liệu hoặc giữ mapping trùng với schema hiện hữu.

### Chuyển đơn hướng thành hai hướng

Nếu `Student.courses` đã là owning side, thêm `Course.students` với `mappedBy = "courses"` thường vẫn dùng cùng bảng nối. Không cần tạo join table thứ hai. Phải bảo đảm hai mapping mô tả cùng association, không phải hai association độc lập.

### Chuyển ManyToMany thành Enrollment

Khi thêm cột `enrolled_at` và `status`:

1. Xác định giá trị cho dữ liệu lịch sử.
2. Mở rộng schema theo thứ tự cho phép các phiên bản ứng dụng còn chạy.
3. Chuyển từ thao tác collection sang thao tác Enrollment entity.
4. Backfill giá trị mới nếu cần.
5. Cập nhật repository, dịch vụ, API và báo cáo.
6. Kiểm tra unique constraint, index và các transaction cạnh tranh.

Đặc biệt, nếu còn instance cũ insert join table không có `enrolled_at` trong khi schema mới đã yêu cầu `NOT NULL` và không có default, rolling deployment có thể gây lỗi. Nên lập kế hoạch **expand–migrate–contract** phù hợp.

## 17. Tránh trả entity hai hướng trực tiếp qua JSON

Nếu Student có collection Course, còn Course có collection Student, serializer có thể đi vòng:

```text
Student
  courses[0]
    students[0]
      courses[0]
        students[0]
          ...
```

Việc trả JPA entity trực tiếp ra API có thể khiến:

- Dữ liệu lặp rất lớn hoặc vòng đệ quy.
- Lazy loading phát sinh nhiều SQL ngoài dự kiến.
- Lỗi khi persistence context đóng.
- Lộ cấu trúc nội bộ không phải hợp đồng API.

Nên thiết kế DTO theo nhu cầu, ví dụ:

```java
public record CourseView(Long id, String title) {}

public record StudentView(
    Long id,
    String fullName,
    List<CourseView> courses
) {}
```

Annotation JSON của Jackson không phải là mapping JPA; dù có thể hữu ích, chúng không thay thế thiết kế endpoint và fetch plan rõ ràng.

## 18. Những lỗi thường gặp

**Đảo hai cột trong `@JoinTable`.** Nếu annotation nằm trong Student, `joinColumns` trỏ Student và `inverseJoinColumns` trỏ Course. Đảo ngược có thể gây sai schema hoặc dữ liệu.

**Dùng `mappedBy` là tên bảng nối.** `mappedBy` phải là tên property của owning entity.

**Cả hai phía cùng khai báo bảng nối cho một association.** Điều này dễ tạo hai mapping độc lập. Một phía sở hữu, phía còn lại dùng `mappedBy`.

**Chỉ sửa inverse collection.** Cập nhật `Course.students` mà không sửa `Student.courses` không phải thao tác đáng tin cậy để ghi join table.

**Bật `CascadeType.ALL` mà không xét xóa Course.** REMOVE có thể lan truyền tới entity dùng chung.

**Không có unique constraint ở bảng nối.** `Set` không ngăn trùng xuyên transaction.

**Đưa thuộc tính nghiệp vụ vào join table nhưng vẫn dùng ManyToMany trực tiếp.** Tạo association entity nếu phải quản lý dữ liệu của chính liên kết.

**Tải toàn bộ collection chỉ để kiểm tra membership.** Query tồn tại thường phù hợp hơn cho collection lớn.

**Dùng List rồi mặc định thứ tự được lưu.** Cần mapping order hoặc truy vấn phù hợp.

**Cập nhật join table bằng SQL ngoài JPA rồi dùng lại collection đã nạp.** Persistence context và shared cache có thể stale; cần ranh giới đồng bộ rõ ràng.

## 19. Bài tập thực hành

### Bài 1: Nhận diện cột khóa

```java
@ManyToMany
@JoinTable(
    name = "teacher_subjects",
    joinColumns = @JoinColumn(name = "teacher_id"),
    inverseJoinColumns = @JoinColumn(name = "subject_id")
)
private Set<Subject> subjects;
```

Annotation ở class `Teacher`. Cột nào tham chiếu Teacher, cột nào tham chiếu Subject?

**Đáp án:** `teacher_id` tham chiếu Teacher; `subject_id` tham chiếu Subject.

### Bài 2: Thêm phía đối ứng

`Teacher.subjects` là owning side. Class `Subject` cần collection giáo viên.

```java
@ManyToMany(mappedBy = "subjects")
private Set<Teacher> teachers = new HashSet<>();
```

`mappedBy` phải là `"subjects"`, không phải `"teacher_subjects"`.

### Bài 3: Xóa liên kết

Sinh viên 1 rút khỏi khóa 10 nhưng nhiều sinh viên khác vẫn học khóa đó.

**Đáp án:** Xóa cặp khóa trong join table; giữ nguyên Course 10 và Student 1.

### Bài 4: Hai request cùng đăng ký

Hai transaction cùng thêm một cặp Student–Course.

**Đáp án:** `HashSet` của một transaction không biết thao tác của transaction khác. Cần PK hoặc UNIQUE trên cặp khóa ở database và cách xử lý exception phù hợp.

### Bài 5: Thêm trạng thái đăng ký

Cần lưu `enrolledAt`, `status` và `grade` cho từng lần đăng ký.

**Đáp án:** Cân nhắc `Enrollment` entity với hai quan hệ `@ManyToOne` và các field riêng; `@ManyToMany` thuần túy không biểu diễn đầy đủ metadata của hàng nối.

### Bài 6: Truy vấn Course có bao nhiêu sinh viên

Không cần load tất cả Student nếu chỉ hiển thị count. Dùng JPQL aggregate hoặc projection tương ứng để hạn chế chi phí tải object graph.

### Bài 7: Phân trang

Một trang hiển thị 20 Student, mỗi Student có nhiều Course. Không nên tự động áp pagination trực tiếp lên query `JOIN FETCH` collection. Cân nhắc lấy ID trang trước rồi nạp dữ liệu, hoặc DTO truy vấn theo nhu cầu.

## 20. Câu hỏi thiết kế trước khi dùng JoinTable

Khi xây dựng một relation nhiều-nhiều, hãy lần lượt xác định:

1. Hai phía thật sự có cardinality nhiều-nhiều không?
2. Bảng nối chỉ có khóa ngoại hay còn chứa dữ liệu nghiệp vụ?
3. Entity nào sẽ là owning side và có `@JoinTable`?
4. `joinColumns` và `inverseJoinColumns` tham chiếu đúng bảng/cột chưa?
5. Có cần khai báo phía đối ứng bằng `mappedBy` không?
6. Mỗi cặp liên kết có cần duy nhất không và DB bảo đảm bằng constraint nào?
7. Index có phục vụ truy vấn theo cả hai chiều không?
8. Student/Course có vòng đời độc lập và có nên tránh cascade remove không?
9. Entity đích đã tồn tại/managed trước khi tạo liên kết chưa?
10. Collection dùng Set hay List; equality/hashCode có ổn định không?
11. Khi hai hướng, helper có đồng bộ cả hai phía không?
12. Có N+1, pagination hoặc collection lớn cần tối ưu query không?
13. API JSON có thể gặp vòng tham chiếu không?
14. Thay đổi mapping có đòi hỏi migration dữ liệu lịch sử không?
15. Transaction đồng thời có thể tạo liên kết trùng hoặc mất cập nhật không?

## Kết luận

**`@ManyToMany` mô tả quan hệ nhiều-nhiều giữa hai entity, còn `@JoinTable` xác định bảng nối SQL lưu các cặp liên kết.** `joinColumns` tham chiếu owning entity; `inverseJoinColumns` tham chiếu entity đích. Với quan hệ hai hướng, phía đối ứng sử dụng `mappedBy` để chỉ về field Java ở phía sở hữu.

Khi thêm hoặc xóa một phần tử của collection phía owning trong persistence context phù hợp, JPA đồng bộ **liên kết trong bảng nối**, chứ không mặc nhiên tạo hay xóa entity dùng chung. Vì thế cần hiểu lifecycle, cascade, equality của collection, constraint trên cặp khóa và những truy vấn phục vụ use case thực tế.

Nếu bảng nối chỉ có hai khóa ngoại, `@ManyToMany` là lựa chọn gọn và phù hợp. Khi liên kết có ngày đăng ký, trạng thái, điểm số hoặc identity riêng, nên chuyển sang **association entity** để biểu diễn quy tắc nghiệp vụ và dữ liệu của chính liên kết ấy.

Câu hỏi cuối cùng cần luôn rõ ràng là: **“Ai sở hữu mapping, bảng nối lưu khóa gì, thao tác Java nào đổi liên kết và có dữ liệu nghiệp vụ nào thuộc riêng hàng nối không?”**. Khi trả lời đúng, ta có thể dùng `@ManyToMany` và `@JoinTable` nhất quán, dễ bảo trì và tránh những lỗi dữ liệu khó phát hiện.
