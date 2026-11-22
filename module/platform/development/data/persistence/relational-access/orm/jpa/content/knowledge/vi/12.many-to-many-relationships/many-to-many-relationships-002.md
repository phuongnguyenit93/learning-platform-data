# Lựa chọn phía sở hữu và đồng bộ tập liên kết trong quan hệ nhiều-nhiều JPA

Quan hệ nhiều-nhiều (*many-to-many*) xuất hiện khi **một entity có thể liên kết với nhiều entity khác và mỗi entity ở phía đối diện cũng có thể liên kết với nhiều entity phía đầu**. Ví dụ: sinh viên đăng ký nhiều khóa học, khóa học có nhiều sinh viên; tác giả viết nhiều cuốn sách, một cuốn sách có nhiều tác giả; nhân viên tham gia nhiều dự án, dự án có nhiều nhân viên.

Trong Java, hai phía thường giữ một tập tham chiếu tới nhau. Trong cơ sở dữ liệu quan hệ, liên kết nhiều-nhiều thông thường được biểu diễn bằng **bảng nối** (*join table*) chứa khóa ngoại tham chiếu cả hai bảng. Với JPA, phải xác định rõ **phía sở hữu quan hệ** (*owning side*) và, nếu mapping hai chiều, **phía nghịch đảo** (*inverse side*) qua `mappedBy`.

Bài học tập trung vào hai quyết định luôn đi cùng nhau:

1. **Chọn phía sở hữu:** phía nào định nghĩa bảng nối và quyết định các liên kết cần ghi hoặc xóa ở database?
2. **Đồng bộ tập liên kết:** khi thêm hoặc bỏ một quan hệ, làm thế nào để hai collection của object graph Java luôn phản ánh cùng một sự thật?

Một điểm quan trọng: **sở hữu quan hệ trong JPA không đồng nghĩa sở hữu vòng đời entity, quyền truy cập dữ liệu hay trách nhiệm nghiệp vụ**. Cần xem xét các khái niệm này riêng biệt khi thiết kế.

## 1. Từ quan hệ miền nghiệp vụ đến bảng nối

Giả sử trường học có hai entity:

- `Student`: sinh viên, có `id`, `studentCode` và `fullName`.
- `Course`: khóa học, có `id`, `courseCode` và `title`.

Một sinh viên có thể học nhiều khóa; mỗi khóa có thể có nhiều sinh viên:

```text
       Student (N)                       Course (N)
    +----------------+              +----------------+
    | id             |              | id             |
    | student_code   |              | course_code    |
    | full_name      |              | title          |
    +----------------+              +----------------+
          |                                |
          | N                            N |
          +------------+-------------------+
                       |
                  student_course
               +------------------+
               | student_id  (FK) |
               | course_id   (FK) |
               +------------------+
```

DDL minh họa:

```sql
CREATE TABLE student (
    id BIGINT PRIMARY KEY,
    student_code VARCHAR(40) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE course (
    id BIGINT PRIMARY KEY,
    course_code VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE student_course (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,

    CONSTRAINT pk_student_course
        PRIMARY KEY (student_id, course_id),

    CONSTRAINT fk_sc_student
        FOREIGN KEY (student_id) REFERENCES student(id),

    CONSTRAINT fk_sc_course
        FOREIGN KEY (course_id) REFERENCES course(id)
);
```

Cú pháp tạo khóa tự sinh sẽ khác theo hệ quản trị; ví dụ SQL cố ý tách phần đó khỏi cấu trúc quan hệ.

Dữ liệu giả định:

**Bảng `student`**

| id | student_code | full_name |
|---:|---|---|
| 1 | ST-001 | Nguyễn An |
| 2 | ST-002 | Trần Bình |

**Bảng `course`**

| id | course_code | title |
|---:|---|---|
| 10 | JAVA-CORE | Java căn bản |
| 20 | JPA-ORM | Lập trình JPA |

**Bảng `student_course`**

| student_id | course_id | Ý nghĩa |
|---:|---:|---|
| 1 | 10 | An học Java căn bản |
| 1 | 20 | An học JPA |
| 2 | 20 | Bình học JPA |

Bảng nối lưu **một dòng cho mỗi cặp liên kết**. Khóa chính ghép hai cột ngăn ghi trùng một cặp sinh viên–khóa học ở mức database.

Ở mức Java, chúng ta muốn điều hướng:

```java
student.getCourses(); // Các khóa của một sinh viên.
course.getStudents(); // Các sinh viên của một khóa.
```

Hai collection này mô tả **cùng một tập liên kết**, nên phải được cấu hình nhất quán.

## 2. Owning side và inverse side trong `@ManyToMany`

### 2.1. Phía sở hữu quản lý bảng nối

JPA sử dụng **owning side** làm nguồn thông tin để cập nhật liên kết ở bảng `student_course`. Ở phía này, chúng ta thường khai báo:

```java
@ManyToMany
@JoinTable(
    name = "student_course",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
```

Giả sử đoạn trên nằm trong `Student`, thì `Student.courses` là **phía sở hữu**.

Hai nhóm cột trong `@JoinTable` có ý nghĩa:

- `joinColumns`: khóa ngoại trong bảng nối tham chiếu **entity chứa owning attribute**, ở đây là `Student`.
- `inverseJoinColumns`: khóa ngoại trong bảng nối tham chiếu **entity ở phía còn lại**, ở đây là `Course`.

Các từ “join” và “inverse join” mô tả chiều của mapping đối với **chủ sở hữu bảng nối**, không phải yêu cầu thứ tự cột trong bảng SQL.

### 2.2. Phía nghịch đảo dùng `mappedBy`

Phía `Course` định nghĩa:

```java
@ManyToMany(mappedBy = "courses")
private Set<Student> students = new HashSet<>();
```

`mappedBy = "courses"` có nghĩa là:

> Collection `Course.students` là chiều ngược lại của quan hệ mà **thuộc tính Java `Student.courses`** đang sở hữu.

Không có bảng nối thứ hai. Cả hai phía dùng cùng `student_course`.

**`mappedBy` là tên thuộc tính Java phía owner**, không phải:

- Tên bảng `student_course`.
- Tên cột `student_id` hay `course_id`.
- Tên class `Student`.
- Tên khóa ngoại hoặc tên constraint.

Ví dụ:

```java
// ĐÚNG: thuộc tính Java của Student.
@ManyToMany(mappedBy = "courses")
private Set<Student> students;

// SAI: dùng tên bảng nối.
@ManyToMany(mappedBy = "student_course")
private Set<Student> students;

// SAI: dùng tên cột FK.
@ManyToMany(mappedBy = "student_id")
private Set<Student> students;
```

### 2.3. Phía inverse vẫn là một quan hệ có thể đọc

Phía nghịch đảo không có nghĩa collection chỉ dùng để hiển thị hoặc bị cấm thay đổi trong Java. Ta vẫn có thể:

```java
course.getStudents();
```

hoặc query qua `Course.students` trong JPQL. Phía inverse chỉ **không phải nguồn quyết định việc cập nhật bảng nối** khi lưu liên kết.

Nếu chỉ sửa `Course.students` mà không sửa `Student.courses`, JPA không có cam kết sẽ ghi row liên kết theo ý muốn. Hơn nữa, object graph đang sống có thể trở nên lệch giữa hai phía.

## 3. Có bắt buộc phải chọn Student làm owner?

**Không.** Trong quan hệ nhiều-nhiều hai chiều, về mặt mapping JPA, cả hai phía đều có thể được chọn làm owner, miễn cấu hình nhất quán và chỉ có **một phía** quản lý liên kết.

Phương án A – `Student` sở hữu:

```text
Student.courses
    @ManyToMany
    @JoinTable(name="student_course", ...)
          |
          | sở hữu liên kết
          v
     student_course
          ^
          | mappedBy="courses"
Course.students
    @ManyToMany(mappedBy="courses")
```

Phương án B – `Course` sở hữu:

```text
Course.students
    @ManyToMany
    @JoinTable(name="student_course", ...)
          |
          | sở hữu liên kết
          v
     student_course
          ^
          | mappedBy="students"
Student.courses
    @ManyToMany(mappedBy="students")
```

Dữ liệu cuối cùng trong bảng nối có thể giống nhau nếu hai cấu hình `@JoinTable` tương ứng được khai báo đúng.

**Không chọn owner theo chiều “một” hoặc “nhiều”** như quan hệ một-nhiều; ở many-to-many, cả hai bên đều là “nhiều”. Cũng không có quy tắc bắt buộc entity được tạo trước, có ID nhỏ hơn, hoặc đứng bên trái sơ đồ phải là owner.

### 3.1. Tiêu chí thực tế để lựa chọn

| Câu hỏi | Ý nghĩa đối với quyết định |
|---|---|
| Luồng nghiệp vụ thường **thêm/xóa liên kết từ đâu**? | Chọn phía mà service hoặc aggregate thường thao tác là owner sẽ giúp cập nhật tự nhiên hơn |
| Entity nào giữ phương thức điều phối liên kết? | Đặt helper method công khai tại nơi có trách nhiệm nghiệp vụ rõ ràng |
| API phổ biến là “sinh viên đăng ký khóa” hay “khóa học nhận sinh viên”? | Giúp chọn API nhất quán; không phải quy tắc cứng |
| Schema đã có bảng nối và tên FK chưa? | Cần giữ `@JoinTable` khớp schema và migration đang chạy |
| Có một phía được cập nhật thường xuyên hơn? | Cân nhắc chi phí tải collection và kiểm soát concurrency của phía đó |
| Liên kết có dữ liệu như ngày đăng ký, điểm số? | Có thể cần **entity trung gian** thay vì `@ManyToMany` trực tiếp |
| Cần quản lý liên kết từ cả hai use case? | Vẫn chọn một owner và để phía còn lại **ủy quyền** thay đổi về owner |

Một hướng dễ hiểu trong ví dụ trường học là chọn `Student.courses` làm owner vì nghiệp vụ diễn đạt “sinh viên đăng ký/hủy đăng ký khóa học”. Nhưng nếu mô hình tập trung vào khóa học và quản lý sĩ số bằng `Course.addStudent(student)`, hoàn toàn có thể chọn Course làm owner.

Điều quan trọng hơn “chọn phía nào” là **mọi thao tác cập nhật đều đi qua phía đã chọn** và cả hai collection được đồng bộ trong bộ nhớ.

### 3.2. Không dựa vào cascade để chọn owner

Một phía có `cascade = CascadeType.PERSIST` không tự trở thành owner. Cascade là việc truyền thao tác lifecycle entity; owner là việc **ai ghi liên kết của bảng nối**.

Tương tự, `fetch = FetchType.LAZY`, `@OrderBy` và các yếu tố presentation không quyết định ownership.

## 4. Mapping hai chiều hoàn chỉnh

Dưới đây là hai entity có thể dùng làm điểm xuất phát trong ứng dụng. Chúng dùng Jakarta Persistence với field access. Mỗi entity giữ `Set` riêng và chỉ cho phép bên ngoài thay đổi quan hệ qua helper method.

### 4.1. `Student` – owning side

```java
package com.example.school.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.Table;

import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "student")
public class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "student_code", nullable = false, unique = true)
    private String studentCode;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    protected Student() {
        // Constructor cần thiết cho JPA.
    }

    public Student(String studentCode, String fullName) {
        this.studentCode = Objects.requireNonNull(studentCode);
        this.fullName = Objects.requireNonNull(fullName);
    }

    public Long getId() {
        return id;
    }

    public String getStudentCode() {
        return studentCode;
    }

    public Set<Course> getCourses() {
        return Collections.unmodifiableSet(courses);
    }

    public void enroll(Course course) {
        Objects.requireNonNull(course, "course");

        if (courses.add(course)) {
            course.addStudentInternal(this);
        }
    }

    public void withdraw(Course course) {
        Objects.requireNonNull(course, "course");

        if (courses.remove(course)) {
            course.removeStudentInternal(this);
        }
    }
}
```

Đặc điểm:

- `Student.courses` mang `@JoinTable` nên là **owner**.
- `Set<Course>` biểu diễn tập liên kết không có thứ tự nghiệp vụ và không muốn thêm trùng theo ngữ nghĩa `Set`.
- `enroll` cập nhật `Student.courses` trước, rồi báo cho phía `Course.students`.
- `withdraw` xóa khỏi phía owner và phía inverse.
- `Collections.unmodifiableSet` ngăn code bên ngoài thay đổi collection trực tiếp, bỏ qua helper.
- Không khai báo `CascadeType.REMOVE` hoặc `CascadeType.ALL`: khóa học tồn tại độc lập với sinh viên.

Bản thân code chưa hiện thực `equals/hashCode` cho entity. Khi dùng `Set` với entity được load từ các persistence context khác nhau hoặc proxy, ứng dụng cần một **chiến lược equality nhất quán**; phần sau giải thích chi tiết. Trong cùng một persistence context, JPA thường quản lý một instance cho mỗi entity type + ID, nên ví dụ phục vụ minh họa tốt cho thao tác liên kết managed entity.

### 4.2. `Course` – inverse side

```java
package com.example.school.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.Table;

import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "course")
public class Course {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "course_code", nullable = false, unique = true)
    private String courseCode;

    @Column(name = "title", nullable = false)
    private String title;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    protected Course() {
    }

    public Course(String courseCode, String title) {
        this.courseCode = Objects.requireNonNull(courseCode);
        this.title = Objects.requireNonNull(title);
    }

    public Long getId() {
        return id;
    }

    public String getCourseCode() {
        return courseCode;
    }

    public Set<Student> getStudents() {
        return Collections.unmodifiableSet(students);
    }

    // Để hỗ trợ use case bắt đầu từ Course:
    public void register(Student student) {
        Objects.requireNonNull(student, "student");
        student.enroll(this); // Ủy quyền cho owning side.
    }

    public void unregister(Student student) {
        Objects.requireNonNull(student, "student");
        student.withdraw(this); // Ủy quyền cho owning side.
    }

    // Chỉ Student.enroll/withdraw gọi hai phương thức này.
    void addStudentInternal(Student student) {
        students.add(student);
    }

    void removeStudentInternal(Student student) {
        students.remove(student);
    }
}
```

Điểm đáng chú ý: dù code có thể bắt đầu ở `course.register(student)`, phương thức vẫn gọi `student.enroll(this)`, là nơi **cập nhật tập owner**. Việc chuyển tiếp giúp mọi use case sử dụng cùng một quy tắc thay đổi liên kết.

Hai helper nội bộ không gọi ngược `student.enroll()` để tránh đệ quy vô hạn.

## 5. Từng bước thêm một liên kết

Giả sử Student 1 và Course 20 đã có trong database.

Trong một transaction:

```java
Student student = entityManager.find(Student.class, 1L);
Course course = entityManager.find(Course.class, 20L);

// Hàm helper sửa cả hai collection trong Java.
student.enroll(course);

// Khi flush/commit, JPA đồng bộ owning collection.
```

Object graph sau `enroll`:

```text
student(id=1)
  courses:
    - course(id=20)
        students:
          - student(id=1)
```

JPA đọc sự thay đổi ở owning attribute `Student.courses` và có thể phát lệnh SQL tương đương:

```sql
INSERT INTO student_course(student_id, course_id)
VALUES (1, 20);
```

Lệnh SQL chính xác và thời điểm thực thi phụ thuộc provider, flush mode, transaction và dữ liệu đã có. `student.enroll(course)` **chỉ thay đổi trạng thái Java ngay lập tức**; không đồng nghĩa một lệnh INSERT đã được gửi và commit ngay tại dòng đó.

### 5.1. Vì sao cần cập nhật cả hai collection?

Vì ở Java, hai tham chiếu cần kể cùng một câu chuyện:

```java
boolean inOwner = student.getCourses().contains(course);
boolean inInverse = course.getStudents().contains(student);

// Sau helper đúng, cả hai được kỳ vọng là true.
```

Nếu chỉ cập nhật phía owner, JPA có thể lưu bảng nối đúng nhưng `course.getStudents()` đã được tải trước đó có thể vẫn không chứa student. Đó là **object graph thiếu nhất quán** trong cùng phiên làm việc.

Nếu chỉ cập nhật inverse, object graph cũng thiếu nhất quán, đồng thời JPA có thể **không ghi row bảng nối** vì owner không đổi.

Vì vậy helper phải bảo đảm hai việc:

1. **Persistence correctness:** cập nhật owning collection.
2. **In-memory consistency:** cập nhật collection inverse tương ứng.

Hai yêu cầu này độc lập về bản chất, nhưng đều cần trong một mapping hai chiều đáng tin cậy.

### 5.2. Tạo mới cả hai entity không có cascade

Trong ví dụ mapping trên, `@ManyToMany` không cấu hình cascade. Hãy persist từng entity mới trước khi transaction kết thúc:

```java
Student student = new Student("ST-003", "Lê Chi");
Course course = new Course("JDBC", "JDBC căn bản");

entityManager.persist(student);
entityManager.persist(course);

student.enroll(course);

// Trong transaction, JPA xử lý thứ tự ghi entity và bảng nối.
// Với IDENTITY, provider có thể cần INSERT để lấy ID trước
// khi ghi student_course.
```

Vì không có cascade, `persist(student)` không tự tạo `Course` độc lập nếu nó chưa được persist. Việc liên kết hai entity mới chưa managed mà bỏ qua persist/cascade có thể dẫn tới lỗi về trạng thái transient hoặc FK.

Trong service dùng Spring hay Jakarta EE, transaction có thể do container/framework quản lý; đoạn code chỉ mô tả thao tác entity, không giả định cụ thể cách mở/đóng transaction.

### 5.3. Kiểm tra thêm trùng

`Set.add(course)` trả `false` khi collection đã chứa phần tử bằng nhau theo chính sách equality. Helper đã viết tránh cập nhật inverse một cách thừa khi không thêm phần tử mới.

Tuy nhiên, **`Set` chỉ chống trùng trong bộ nhớ theo `equals/hashCode`**, không phải ràng buộc toàn cục giữa hai transaction. Cần **khóa chính ghép hoặc unique constraint** trên `(student_id, course_id)` để ngăn cặp trùng trong database.

Nếu hai request cùng đăng ký một khóa cho một sinh viên, có thể xảy ra race condition. Service phải quyết định cách xử lý vi phạm unique, kiểm soát concurrency hoặc logic idempotency phù hợp.

## 6. Từng bước xóa một liên kết

Giả sử Student 1 không còn học Course 20:

```java
Student student = entityManager.find(Student.class, 1L);
Course course = entityManager.find(Course.class, 20L);

student.withdraw(course);
```

Trong Java:

- `student.courses` không còn `course`.
- `course.students` không còn `student`.

JPA có thể đồng bộ bằng SQL tương đương:

```sql
DELETE FROM student_course
WHERE student_id = 1
  AND course_id = 20;
```

**Không phải**:

```sql
DELETE FROM course WHERE id = 20;
```

Việc rút khỏi khóa học chỉ **xóa liên kết**, không xóa bản thân khóa học. Course 20 có thể vẫn được nhiều sinh viên khác sử dụng.

Cũng không tự xóa Student 1. `@ManyToMany` là quan hệ giữa **hai entity có vòng đời độc lập** trong ví dụ này.

### 6.1. Nếu chỉ sửa inverse thì sao?

Đoạn sai ý định:

```java
// Giả sử code cho phép thao tác trực tiếp collection.
course.getMutableStudents().remove(student);

// Chưa sửa student.courses.
```

Với mapping `Student.courses` là owner, yêu cầu xóa liên kết trong database không được biểu đạt bằng cách sửa inverse collection đơn lẻ. Dù in-memory `course.students` đã mất phần tử, row `student_course` có thể vẫn tồn tại sau commit.

Hãy gọi:

```java
course.unregister(student);
```

Phương thức này ủy quyền về owner và đồng bộ cả hai phía.

### 6.2. Nếu chỉ sửa owning side thì sao?

```java
student.getMutableCourses().remove(course);
```

Owner đã đổi nên JPA có thể xóa join row. Tuy nhiên, nếu `course.students` đã load, collection đó có thể vẫn chứa student. Sau khi làm mới state hoặc mở persistence context mới, dữ liệu phản ánh database, nhưng **trong context hiện tại** code có thể đưa ra quyết định dựa trên object graph sai.

Thêm/xóa bằng helper là cách đơn giản để tránh trạng thái lệch ngay trong ứng dụng.

## 7. Mối quan hệ giữa owner, `mappedBy` và tên cột

Đặt các khái niệm cạnh nhau:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Owning attribute | `Student.courses` | Nguồn cập nhật tập liên kết |
| Inverse attribute | `Course.students` | Cách điều hướng ngược trong object graph |
| `mappedBy` | `"courses"` | Tên thuộc tính Java ở owning side |
| Join table | `student_course` | Bảng chứa các cặp quan hệ |
| `joinColumns` | `student_id` | FK từ join table tới entity owning side |
| `inverseJoinColumns` | `course_id` | FK từ join table tới entity phía đối diện |
| Khóa chính/unique | `(student_id, course_id)` | Ngăn trùng liên kết ở DB |
| Cascade | Ví dụ `PERSIST` hoặc `MERGE` | Lan truyền thao tác lifecycle entity; không quyết định owner |
| Fetch | `LAZY` hoặc `EAGER` | Điều khiển yêu cầu tải dữ liệu; không quyết định owner |

Đặc biệt, nếu đổi tên Java field:

```java
// Trước:
private Set<Course> courses;

// Sau:
private Set<Course> enrolledCourses;
```

thì phía inverse phải đổi thành:

```java
@ManyToMany(mappedBy = "enrolledCourses")
private Set<Student> students;
```

Cột SQL `student_id`, `course_id` không cần đổi chỉ vì tên Java field được refactor.

## 8. Vì sao không khai báo hai phía đều là owner?

Một lỗi thường gặp là viết:

```java
// Student.java
@ManyToMany
@JoinTable(name = "student_course")
private Set<Course> courses;

// Course.java
@ManyToMany
@JoinTable(name = "student_course")
private Set<Student> students;
```

Với hai annotation không có `mappedBy`, JPA được mô tả **hai association sở hữu độc lập**, dù chúng có thể tình cờ dùng cùng một tên bảng nối. Điều này tạo mapping mâu thuẫn hoặc các thao tác SQL không như mong đợi, tùy provider và cấu hình.

Sửa bằng cách:

- Giữ `@JoinTable` tại **một** bên owner.
- Bên còn lại dùng `@ManyToMany(mappedBy = "...")` trỏ chính xác tới attribute owner.
- Đồng bộ hai collection thông qua helper.

**Không tạo thêm `@JoinTable` ở phía inverse** cho cùng một quan hệ hai chiều. Nếu cần hai quan hệ nhiều-nhiều thực sự khác nhau giữa cùng hai entity, hãy đặt tên thuộc tính và bảng nối riêng biệt với ý nghĩa nghiệp vụ rõ ràng.

Ví dụ một ứng dụng có thể có cả `Project.members` và `Project.reviewers` đều trỏ tới `Employee`, nhưng đó là **hai quan hệ riêng**. Mỗi quan hệ cần cấu hình mapping và bảng nối tương ứng; không dùng chung `mappedBy` một cách tùy tiện.

## 9. `Set`, `List` và tính đúng đắn của liên kết

### 9.1. Vì sao thường chọn `Set`?

Một quan hệ “sinh viên đã đăng ký khóa học hay chưa” có ngữ nghĩa **membership**: hoặc có, hoặc không. `Set` phù hợp vì:

- Không mong muốn hai phần tử giống nhau theo `equals`.
- Có thể diễn đạt thêm/bỏ bằng `add` và `remove`.
- Không mặc định yêu cầu thứ tự đăng ký.
- Phù hợp với unique key cho cặp `(student_id, course_id)`.

Ví dụ:

```java
private Set<Course> courses = new HashSet<>();
```

Nhưng `Set` chỉ phát huy hiệu quả nếu **`equals/hashCode` ổn định và đúng**. Nếu equality của entity thay đổi sau khi thêm vào Set, `remove` có thể không tìm thấy phần tử.

### 9.2. Có thể dùng `List` không?

Có:

```java
@ManyToMany
@JoinTable(name = "student_course", ...)
private List<Course> courses = new ArrayList<>();
```

Nhưng cần xác định ý nghĩa:

- `List` cho phép trùng phần tử ở cấp Java.
- Một `List` không có `@OrderColumn` không mặc nhiên lưu thứ tự chèn một cách portable.
- `@OrderBy` yêu cầu sắp xếp dựa trên thuộc tính entity khi đọc, khác với việc lưu vị trí của từng quan hệ.
- `@OrderColumn` dùng cho các mapping collection thích hợp khi muốn giữ thứ tự bền vững, có ảnh hưởng schema và SQL.
- Trong các provider, collection dạng bag/list có thể khiến thao tác xóa/thêm và fetch join có hành vi hoặc chi phí khác với Set.

Nếu nghiệp vụ chỉ cần “có đăng ký hay không”, **`Set` và unique constraint** thường mô tả chính xác ý nghĩa hơn.

### 9.3. Equality của entity là vấn đề thực tế

Giả sử `Course.id` được database tạo khi persist. Trước persist, `id == null`; sau persist, `id` có giá trị.

Một cách triển khai nguy hiểm:

```java
@Override
public int hashCode() {
    return Objects.hash(id);
}
```

Nếu thêm Course vào `HashSet` khi `id` chưa được gán, rồi ID xuất hiện làm hash thay đổi, object có thể nằm sai bucket. Khi đó:

```java
student.getCourses().contains(course);
student.getCourses().remove(course);
```

có thể trả kết quả không mong đợi. Lỗi này ảnh hưởng trực tiếp đến helper đồng bộ liên kết.

Một số hướng thiết kế equality:

- Dựa trên **business key duy nhất, ổn định và bất biến** (nếu thực sự đáp ứng các điều kiện này).
- Dựa trên database ID cho entity đã persist, kèm chiến lược `hashCode` ổn định và xử lý `null`/proxy thích hợp.
- Dùng object identity trong phạm vi rõ ràng, ví dụ cùng một persistence context, và không giả định so sánh có hiệu lực giữa các detached instance.

Không có một mẫu `equals/hashCode` phù hợp mọi entity, đặc biệt khi có proxy hoặc ID tự sinh. Tránh sinh `equals/hashCode` từ **toàn bộ collection quan hệ**.

### 9.4. Không đưa hai collection vào `toString()` hoặc `equals()`

Với quan hệ hai chiều:

```text
Student.toString()
  -> courses
      -> Course.toString()
          -> students
              -> Student.toString()
                  -> ...
```

Có nguy cơ đệ quy vô hạn, `StackOverflowError` hoặc kích hoạt hàng loạt lazy loading. Một số annotation sinh tự động từ Lombok như `@Data` có thể đưa association vào các phương thức này nếu không cấu hình loại trừ.

Nên giữ `toString` ở các trường scalar cần thiết; định nghĩa equality theo identity phù hợp với entity, không so sánh cả object graph.

### 9.5. Giữ nguyên collection persistent đang được JPA quản lý

Sau khi tải một entity, provider có thể thay collection bằng wrapper phục vụ theo dõi thay đổi. Tránh viết setter tùy ý thay thế hẳn collection:

```java
public void setCourses(Set<Course> newCourses) {
    this.courses = newCourses; // Dễ bỏ qua đồng bộ inverse.
}
```

Ngay cả nếu provider vẫn phát hiện thay đổi, code này không cập nhật `Course.students` và có thể khiến logic membership, orphan/link tracking hay lazy loading khó kiểm soát.

Một cách rõ ràng hơn là gọi helper thêm/bỏ có kiểm soát, hoặc thực hiện thao tác đồng bộ tập hợp bằng cách so sánh các phần tử cần thêm và cần xóa.

## 10. Đồng bộ một tập liên kết với danh sách mới

Nghiệp vụ thường không chỉ thêm/bỏ một course, mà nhận cả danh sách course ID mới từ giao diện:

```json
{
  "studentId": 1,
  "courseIds": [10, 20, 30]
}
```

Với JPA, không nên tạo các entity giả chỉ gồm ID rồi thay nguyên collection mà không kiểm tra tồn tại. Service có thể tải các `Course` tương ứng và áp dụng thay đổi qua helper.

Giả sử `desiredCourses` là một `Set<Course>` đã được giải quyết từ ID trong transaction, và các entity nằm trong persistence context thích hợp:

```java
public void replaceEnrollments(
        Student student,
        Set<Course> desiredCourses
) {
    Set<Course> current = new HashSet<>(student.getCourses());

    for (Course existing : current) {
        if (!desiredCourses.contains(existing)) {
            student.withdraw(existing);
        }
    }

    for (Course desired : desiredCourses) {
        if (!student.getCourses().contains(desired)) {
            student.enroll(desired);
        }
    }
}
```

Ý nghĩa:

1. Tạo bản sao `current` để tránh sửa trực tiếp một collection đang được duyệt.
2. Bỏ liên kết không còn nằm trong tập mong muốn.
3. Thêm các liên kết mới.
4. Giữ nguyên các liên kết không đổi.
5. Mọi thay đổi đi qua helper, đảm bảo owner và inverse nhất quán.

**Điều kiện:** `equals/hashCode` của `Course` phải phù hợp để `contains` hoạt động. Với các entity khác instance nhưng cùng ID, so sánh theo object identity có thể không đủ. Trong nhiều ứng dụng, so sánh theo **ID ổn định** ở tầng service rồi gọi helper trên các managed entity sẽ dễ kiểm soát hơn.

### 10.1. So sánh theo ID khi nhận input từ API

Một hướng ở service:

```java
Set<Long> desiredIds = new HashSet<>(request.courseIds());

// Bước 1: xác thực ID, quyền đăng ký và khóa học tồn tại.
// Bước 2: tải các Course cần dùng trong transaction.
// Bước 3: so sánh theo Course.id và gọi helper enroll/withdraw.
// Bước 4: để JPA flush/commit các thay đổi của owning collection.
```

Không nhận các đối tượng `Course` tùy ý do client gửi rồi gọi `merge` hàng loạt chỉ để xây liên kết. Entity manager cần biết các tham chiếu đúng, còn service phải kiểm tra quyền và quy tắc đăng ký.

### 10.2. Bất biến nghiệp vụ trong thao tác đồng bộ

Ví dụ một khóa học có giới hạn 30 chỗ, không cho đăng ký sau hạn và chỉ người đủ điều kiện mới được tham gia. Helper `enroll` thuần liên kết chưa giải quyết các quy tắc đó.

Có thể tổ chức service:

```java
@Transactional
public void enrollStudent(Long studentId, Long courseId) {
    Student student = studentRepository.findById(studentId)
        .orElseThrow();

    Course course = courseRepository.findById(courseId)
        .orElseThrow();

    enrollmentPolicy.checkAllowed(student, course);

    student.enroll(course);
}
```

Đây là minh họa theo Spring Data/JPA; `@Transactional` và repository là thành phần Spring, không phải cú pháp bắt buộc của Jakarta Persistence. Kiểm tra sĩ số trong nhiều transaction đồng thời cần chiến lược khóa hoặc constraint phù hợp để tránh vượt giới hạn, không chỉ `Set.add`.

## 11. Quan hệ một chiều và hai chiều: có cần `mappedBy` không?

Nếu ứng dụng **chỉ cần truy vấn từ Student sang Course**, không nhất thiết phải khai báo `Course.students`.

Ví dụ một chiều:

```java
@Entity
public class Student {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    protected Student() {
    }
}
```

Trong cách này:

- `Student.courses` là phía duy nhất khai báo association.
- Không có inverse collection, nên **không có `mappedBy`**.
- Không cần helper sửa `Course.students` vì property đó không tồn tại.
- Bảng nối vẫn được quản lý bởi mapping của `Student.courses`.

**Quan hệ một chiều không làm thay đổi bản chất nhiều-nhiều trong database.** Nó chỉ thu hẹp đường điều hướng trong mô hình Java.

Nên cân nhắc **hai chiều** khi truy vấn từ cả hai phía là nhu cầu thường xuyên, hoặc logic nghiệp vụ cần giữ hai collection tương ứng. Quan hệ hai chiều làm mô hình tiện điều hướng nhưng cũng tăng trách nhiệm đồng bộ và có nguy cơ vòng lặp JSON/`toString`.

Một khi đã có hai phía, không được coi chúng là hai association độc lập chỉ vì code muốn đi hai chiều.

## 12. Chọn lại phía sở hữu sau khi hệ thống đã có dữ liệu

Về lý thuyết có thể đổi từ `Student.courses` owner sang `Course.students` owner. Nhưng trong dự án đang vận hành, phải xem xét:

- Tên bảng nối đã được tạo hoặc migration đã kiểm soát.
- Hướng `joinColumns` và `inverseJoinColumns`.
- Tên FK, unique constraint và thứ tự cột.
- Những service/helper hiện đang cập nhật owning collection.
- Truy vấn, entity graph và test phụ thuộc tên attribute.
- Cách provider theo dõi thay đổi collection.

Ví dụ trước đổi:

```java
// Student (owner)
@ManyToMany
@JoinTable(
    name = "student_course",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses;
```

Sau đổi, nếu muốn `Course.students` thành owner:

```java
// Course (owner mới)
@ManyToMany
@JoinTable(
    name = "student_course",
    joinColumns = @JoinColumn(name = "course_id"),
    inverseJoinColumns = @JoinColumn(name = "student_id")
)
private Set<Student> students;

// Student (inverse mới)
@ManyToMany(mappedBy = "students")
private Set<Course> courses;
```

**Lưu ý hướng cột đã đảo:** ở phía Course mới, `joinColumns` phải tham chiếu Course, nên là `course_id`.

Nếu giữ tên bảng và cột giống schema cũ, có thể không cần đổi dữ liệu bảng nối. Nhưng code thay đổi owner và luồng cập nhật; nếu mapping tự sinh schema, thiếu cấu hình tường minh có thể khiến provider chọn tên mặc định khác.

Nên xem đây là **thay đổi mapping có ảnh hưởng ứng dụng**, cần migration hoặc xác nhận schema tương ứng trong quy trình phát hành. Không sửa mỗi `mappedBy` rồi cho rằng hành vi không đổi.

## 13. Cascade và việc xóa entity liên quan

### 13.1. Cascade khác ownership

Các loại cascade của JPA như `PERSIST`, `MERGE`, `REMOVE`, `REFRESH`, `DETACH` được dùng để truyền thao tác lifecycle sang entity liên quan.

Ví dụ:

```java
@ManyToMany(cascade = {
    CascadeType.PERSIST,
    CascadeType.MERGE
})
private Set<Course> courses;
```

Cấu hình trên cho phép lan truyền persist/merge trong những trường hợp phù hợp. Nó **không** làm phía này thành owner nếu nó đã được đánh dấu `mappedBy`, và cũng **không đồng nghĩa** thêm phần tử vào inverse collection sẽ được ghi sang join table.

Khi hai entity độc lập như `Student` và `Course`, nhiều dự án chọn **không cascade** hoặc chỉ cascade rất hạn chế để tránh tạo/xóa ngoài ý muốn.

### 13.2. Vì sao tránh `CascadeType.REMOVE` trong many-to-many?

Giả sử:

```text
Student An  ------+
                  |
                  +------> Course JPA
                  |
Student Bình -----+
```

Nếu xóa Student An, điều hợp lý là xóa các dòng nối `student_course` của An, không xóa `Course JPA` vì Bình vẫn đang học.

Nếu cấu hình:

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses;
```

thì `ALL` gồm cả `REMOVE`, có thể khiến việc xóa Student cố gắng xóa các Course liên quan. Điều này nguy hiểm với entity được nhiều bên tham chiếu, có thể thất bại vì FK hoặc phá dữ liệu nếu schema cho phép.

**Khuyến nghị cho hai entity độc lập:** không cascade remove xuyên quan hệ nhiều-nhiều. Quản lý vòng đời của Student và Course riêng; bảng nối bị xóa theo thao tác liên kết hoặc khi xóa entity theo cơ chế JPA/DB phù hợp.

### 13.3. `orphanRemoval` không áp dụng cho `@ManyToMany`

`orphanRemoval` là thuộc tính của những mapping như `@OneToOne` và `@OneToMany`; **`@ManyToMany` không có phần tử `orphanRemoval`**.

Xóa một Course khỏi `student.courses` có nghĩa là **xóa quan hệ**, không phải “Course trở thành orphan và phải bị xóa”.

Nếu đối tượng liên kết không có vòng đời độc lập, nên đánh giá lại liệu đây có thật sự là quan hệ nhiều-nhiều giữa hai entity độc lập hay nên dùng một entity liên kết.

## 14. Khi bảng nối có dữ liệu riêng: dùng entity trung gian

Trong nhiều hệ thống, “đăng ký khóa học” không chỉ là cặp ID. Nó có thể chứa:

- Thời điểm đăng ký.
- Trạng thái được duyệt, đang học, đã hủy.
- Điểm thi.
- Người phê duyệt.
- Giá học phí hoặc lịch sử thay đổi.

Khi đó bảng nối có thêm thuộc tính:

```sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    grade VARCHAR(10),

    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(id),
    FOREIGN KEY (course_id) REFERENCES course(id)
);
```

Bảng `enrollment` lúc này có **dữ liệu và quy tắc nghiệp vụ riêng**. Mô hình hóa nó như entity `Enrollment` thường rõ hơn:

```text
Student (1) ------------ (N) Enrollment (N) ------------ (1) Course
                                |
                                +-- enrolledAt
                                +-- status
                                +-- grade
```

### 14.1. Ví dụ `Enrollment` dùng khóa ghép

```java
@Embeddable
public class EnrollmentId implements java.io.Serializable {

    private Long studentId;
    private Long courseId;

    protected EnrollmentId() {
    }

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = studentId;
        this.courseId = courseId;
    }

    public Long getStudentId() { return studentId; }
    public Long getCourseId() { return courseId; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof EnrollmentId other)) return false;
        return java.util.Objects.equals(studentId, other.studentId)
            && java.util.Objects.equals(courseId, other.courseId);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(studentId, courseId);
    }
}
```

```java
@Entity
@Table(name = "enrollment")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("studentId")
    @JoinColumn(name = "student_id")
    private Student student;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("courseId")
    @JoinColumn(name = "course_id")
    private Course course;

    private java.time.Instant enrolledAt;

    @Enumerated(EnumType.STRING)
    private EnrollmentStatus status;

    protected Enrollment() {
    }

    public Enrollment(Student student, Course course) {
        this.student = java.util.Objects.requireNonNull(student);
        this.course = java.util.Objects.requireNonNull(course);
        this.enrolledAt = java.time.Instant.now();
        this.status = EnrollmentStatus.ACTIVE;
        // ID được ánh xạ từ các association qua @MapsId.
    }
}

enum EnrollmentStatus {
    ACTIVE,
    CANCELLED
}
```

Ví dụ này tập trung vào cấu trúc mapping. Để dùng trong ứng dụng thực tế, cần thiết kế đầy đủ cách khởi tạo/đồng bộ khóa ghép, vòng đời entity và helper ở hai phía, nhất là trước khi ID của Student/Course được cấp. `@MapsId` cho phép các thành phần khóa dẫn xuất từ ID của các association.

Có thể thay khóa ghép bằng surrogate ID `Long` và unique constraint `(student_id, course_id)` khi nghiệp vụ thuận lợi hơn.

### 14.2. Lúc này ownership nằm ở đâu?

Ta không còn dùng một `@ManyToMany` trực tiếp. Thay vào đó có hai quan hệ:

```java
// Trong Enrollment
@ManyToOne
@MapsId("studentId")
private Student student;

@ManyToOne
@MapsId("courseId")
private Course course;
```

Các `@ManyToOne` trong `Enrollment` là owning sides của liên kết với `Student` và `Course`.

Nếu muốn điều hướng từ Student/Course:

```java
// Trong Student
@OneToMany(mappedBy = "student")
private Set<Enrollment> enrollments;

// Trong Course
@OneToMany(mappedBy = "course")
private Set<Enrollment> enrollments;
```

`mappedBy` lúc này trỏ tới `Enrollment.student` và `Enrollment.course`, không còn trỏ tới một `Set<Course>`/`Set<Student>` trực tiếp.

**Tín hiệu cần dùng entity trung gian:** khi “liên kết” cần được tìm kiếm, phê duyệt, đánh giá, ghi lịch sử hoặc sửa trạng thái như một khái niệm nghiệp vụ độc lập, `Enrollment` thường hợp lý hơn `@ManyToMany` thuần túy.

## 15. Giao dịch và trạng thái entity khi đồng bộ collection

### 15.1. Thao tác trên entity managed

Trong transaction:

```java
Student student = entityManager.find(Student.class, studentId);
Course course = entityManager.find(Course.class, courseId);

student.enroll(course);

// JPA dirty checking/collection tracking.
// Khi flush/commit, bảng nối được đồng bộ.
```

Provider có thể quản lý collection qua wrapper, snapshot hoặc cơ chế theo dõi thay đổi. Không bắt buộc phải gọi `entityManager.persist(student)` lại khi `student` đang managed.

`flush()` **không phải `commit()`**: SQL có thể đã chạy trong transaction nhưng kết quả còn có thể rollback.

### 15.2. Thao tác trên entity detached

Giả sử entity đã tách khỏi persistence context:

```java
Student detachedStudent = ...; // Được lấy từ request/cached object.
detachedStudent.enroll(detachedCourse);
```

Việc sửa detached object **không tự ghi database**. Có thể dùng `merge` để sao chép state vào managed instance trong trường hợp phù hợp, nhưng đây không phải lựa chọn an toàn mặc định cho mọi request cập nhật collection.

Đối với thao tác “đăng ký khóa học ID 20”, cách dễ kiểm soát hơn thường là:

1. Trong transaction, tìm `Student` managed theo ID.
2. Tìm `Course` managed hoặc reference phù hợp.
3. Xác thực quyền và điều kiện nghiệp vụ.
4. Gọi `student.enroll(course)`.
5. Commit transaction và xử lý xung đột/constraint nếu có.

Không để client gửi một graph entity lớn rồi `merge` không kiểm soát, vì có thể vô tình thêm/xóa nhiều liên kết hoặc ghi đè những thuộc tính không thuộc quyền sửa của client.

### 15.3. Kết quả `merge` là managed instance

Nếu dùng `merge`:

```java
Student managedStudent = entityManager.merge(detachedStudent);
```

Instance trả về mới là đối tượng managed theo hợp đồng JPA; `detachedStudent` vẫn detached. Cách xử lý các collection và cascade cần đúng mapping; không coi `merge` như “ghi trực tiếp mọi thứ từ DTO”.

### 15.4. Xóa entity và dọn bảng nối

Khi xóa một Student có liên kết tới Course, hệ thống phải bảo đảm các dòng nối không còn tham chiếu Student đã bị xóa. Provider có thể dọn join table trong quá trình remove; DB cũng có thể có `ON DELETE CASCADE` nếu schema được cấu hình như vậy.

Cần xác định chính sách xóa tương ứng với database và JPA provider. **Không nên tự coi việc xóa Student là lý do xóa Course**. Ngoài ra, nếu dùng SQL trực tiếp để xóa hoặc bulk operation, persistence context có thể còn state stale và không tự đồng bộ object graph đang managed.

## 16. Concurrency và ràng buộc tính duy nhất

### 16.1. Hai transaction cùng thêm một liên kết

Giả sử hai request cùng lúc muốn đăng ký:

```text
Transaction A                 Transaction B
-------------------------     -------------------------
Đọc Student 1                Đọc Student 1
Kiểm tra chưa học Course 20  Kiểm tra chưa học Course 20
Thêm Course 20 vào Set       Thêm Course 20 vào Set
INSERT join row              INSERT join row
COMMIT                       COMMIT hoặc conflict
```

`Set` trong từng transaction có thể đều thấy “chưa có”. Không thể dùng riêng `Set.contains` để ngăn trùng trong hệ thống nhiều transaction.

Cần:

- Khóa chính ghép hoặc unique constraint trên `(student_id, course_id)`.
- Xử lý lỗi uniqueness phù hợp và xác định thao tác có nên idempotent không.
- Nếu phải kiểm tra sĩ số hoặc một điều kiện tổng hợp, dùng transaction isolation/locking phù hợp để tránh vượt invariant.

### 16.2. `@Version` có tự giải quyết mọi race condition?

Có thể cấu hình optimistic locking trên entity:

```java
@Version
private long version;
```

Nhưng tác động của thay đổi association collection đối với version của owner có thể phụ thuộc vào mapping và cơ chế provider, đặc biệt với bulk SQL hoặc thay đổi qua quan hệ inverse.

**Đừng giả định chỉ có `@Version` là bảng nối được bảo vệ toàn diện khỏi mọi insert trùng và vi phạm sĩ số.** Unique constraint và chiến lược transaction vẫn cần thiết.

### 16.3. Xóa cùng một liên kết hai lần

Hai request cùng rút một sinh viên khỏi cùng khóa có thể cùng quan sát liên kết đã tồn tại. Tùy transaction, request thứ hai có thể thấy collection đã đổi hoặc gặp tình huống cạnh tranh.

Service nên xác định semantics:

- **Idempotent withdrawal:** nếu liên kết đã không tồn tại, coi trạng thái mong muốn đã đạt.
- **Strict validation:** nếu không có đăng ký thì trả lỗi nghiệp vụ.
- **Audit:** nếu cần ghi nhận từng thao tác hủy, entity trung gian có trạng thái/lịch sử có thể phù hợp hơn xóa row join thuần túy.

Đây là quyết định nghiệp vụ, không phải hành vi do `mappedBy` tự xác định.

## 17. Tải dữ liệu nhiều-nhiều và N+1

### 17.1. `@ManyToMany` mặc định LAZY

Nếu không chỉ định:

```java
@ManyToMany
private Set<Course> courses;
```

mapping collection có **`FetchType.LAZY` mặc định** theo JPA. Điều đó có nghĩa dữ liệu collection được yêu cầu tải lazily theo cơ chế provider; thời điểm SQL thực tế còn phụ thuộc fetch plan, truy vấn và persistence context.

Đừng chỉ để phục vụ API mà trả trực tiếp entity sau khi transaction đóng rồi mong serializer tự đọc `courses`. Có thể gặp lazy initialization error hoặc truy vấn bất ngờ nếu context còn mở.

### 17.2. N+1 khi duyệt nhiều Student

```java
List<Student> students = entityManager.createQuery(
    "select s from Student s",
    Student.class
).getResultList();

for (Student student : students) {
    System.out.println(student.getCourses().size());
}
```

Nếu provider phải tải collection riêng cho mỗi student, một query danh sách có thể kéo theo nhiều query bảng nối/khóa học. Đây là một biểu hiện của **N+1**.

Giải pháp phụ thuộc use case:

- `JOIN FETCH` khi cần graph entity cùng collection, chú ý nhân bản row khi join.
- Entity graph để diễn đạt fetch plan.
- DTO projection khi chỉ cần vài cột hoặc số lượng liên kết.
- Query aggregate như `COUNT` khi chỉ cần tổng số khóa.
- Batch fetching nếu provider hỗ trợ và workload phù hợp.

Ví dụ chỉ lấy số khóa học:

```java
List<Object[]> rows = entityManager.createQuery(
    """
    select s.id, count(c)
    from Student s
    left join s.courses c
    group by s.id
    """,
    Object[].class
).getResultList();
```

Query này không cần load toàn bộ `Course` entity chỉ để đếm. Đây là ví dụ về **truy vấn theo dữ liệu cần thiết**, tách khỏi vấn đề owner của quan hệ.

### 17.3. Fetch join có thể nhân bản row

```java
List<Student> students = entityManager.createQuery(
    """
    select distinct s
    from Student s
    left join fetch s.courses
    where s.id in :ids
    """,
    Student.class
)
.setParameter("ids", List.of(1L, 2L))
.getResultList();
```

Một Student có 10 Course có thể xuất hiện 10 dòng trong SQL result set. JPA/provider phải xử lý các row này để dựng entity và collection. `DISTINCT` ở JPQL diễn đạt kết quả root entity không trùng; cách SQL/provider xử lý chi tiết có thể khác.

Với pagination, fetch join collection cần đặc biệt thận trọng vì việc nhân bản row có thể làm giới hạn SQL không còn tương ứng số Student mong muốn. Một chiến lược phổ biến là phân trang Student ID trước, rồi query các Course cần thiết theo các ID đó.

Ownership và fetch là hai mối quan tâm khác nhau. Đổi owning side không phải cách tự động loại bỏ N+1.

## 18. Tương tác với API và serialization

Một DTO đầu vào nên biểu diễn yêu cầu nghiệp vụ, ví dụ:

```java
public record ReplaceStudentCoursesRequest(
    Set<Long> courseIds
) {
}
```

Một DTO đầu ra:

```java
public record CourseSummary(
    Long id,
    String courseCode,
    String title
) {
}

public record StudentCourseResponse(
    Long studentId,
    Set<CourseSummary> courses
) {
}
```

DTO không phải JPA entity; nó giúp API kiểm soát những trường được công bố. Service có trách nhiệm chuyển các Course ID thành entity và áp dụng thay đổi qua helper.

Không nên trả trực tiếp cả `Student` lẫn `Course` với hai collection hai chiều cho JSON serializer. Có thể dẫn tới:

```text
Student
  -> Course
      -> Student
          -> Course
              -> ...
```

Ngoài vòng lặp, serializer có thể kích hoạt lazy loading lớn hoặc trả dữ liệu ngoài hợp đồng API.

Dùng DTO hoặc cấu hình serialization có chủ đích; không thay đổi `mappedBy` chỉ để giải quyết vòng tham chiếu JSON.

## 19. Những nhầm lẫn và lỗi triển khai thường gặp

### 19.1. “Entity cha phải là owner”

Trong nhiều-nhiều, không có phía “một” để xác định owner theo FK. Student hoặc Course đều có thể là owner. Hãy chọn theo API cập nhật, schema và tính nhất quán, không theo thứ tự khai báo.

### 19.2. “`mappedBy` phải bằng tên bảng nối”

Sai. `mappedBy` cần **tên persistent attribute Java** trên owning entity. Trong ví dụ, `mappedBy = "courses"`, còn bảng nối tên `student_course`.

### 19.3. “Có `@JoinTable` trên cả hai phía càng chắc chắn”

Sai. Hai phía cùng quản lý một association có thể tạo mapping mâu thuẫn. Chỉ một phía sở hữu; phía inverse dùng `mappedBy`.

### 19.4. “Chỉ thêm vào phía inverse là JPA sẽ ghi liên kết”

Không được bảo đảm. Phía owner mới là nguồn cập nhật join table. Gọi helper đảm bảo sửa owner và inverse.

### 19.5. “Chỉ sửa owner là ứng dụng đã hoàn toàn nhất quán”

Database có thể được cập nhật đúng, nhưng inverse collection đã loaded trong cùng context có thể stale. Đồng bộ cả hai phía để code nghiệp vụ có graph nhất quán.

### 19.6. “`CascadeType.ALL` là lựa chọn an toàn mặc định”

Không. `ALL` gồm `REMOVE`, có thể cố xóa Course khi xóa Student. Với hai entity độc lập, không cascade remove chỉ vì có many-to-many.

### 19.7. “Xóa khỏi collection đồng nghĩa xóa entity đích”

Không. Trong quan hệ nhiều-nhiều thuần, xóa khỏi owning collection có nghĩa xóa **dòng nối**, không xóa Course hay Student.

### 19.8. “`orphanRemoval = true` dùng được trên `@ManyToMany`”

Không. Annotation `@ManyToMany` không có thuộc tính `orphanRemoval`. Nếu liên kết có vòng đời riêng, xem xét entity trung gian.

### 19.9. “Dùng `Set` là DB không bao giờ có cặp trùng”

Không. Hai transaction có thể thêm đồng thời; cần PK ghép hoặc unique constraint trong DB.

### 19.10. “Mọi entity có ID tự sinh đều có thể dùng `Objects.hash(id)`”

Không an toàn nếu hash của một object đổi sau khi ID xuất hiện. Điều này làm việc thêm/bỏ trong `HashSet` sai. Cần equality ổn định với vòng đời entity.

### 19.11. “`List` luôn bảo toàn thứ tự chèn xuống database”

Không mặc định. Cần phân biệt `@OrderBy` và `@OrderColumn`, cũng như ý nghĩa business order của collection.

### 19.12. “`@ManyToMany(fetch = EAGER)` sẽ chạy nhanh hơn”

Không thể kết luận. EAGER có thể tải số lượng lớn row hoặc phát secondary selects. Đo SQL và chỉ tải tập liên kết khi use case cần.

### 19.13. “Thay cả `Set` bằng một Set mới là cách tốt nhất để cập nhật”

Có thể phá tính nhất quán inverse, phụ thuộc wrapper provider hoặc gây nhiều SQL không cần. Thao tác thêm/bỏ qua helper, hoặc tính chênh lệch tập hợp, thường rõ ràng hơn.

### 19.14. “`mappedBy` làm inverse side trở thành read-only”

Inverse vẫn có thể được dùng để đọc, query và giữ object graph. Nó chỉ không quyết định các thay đổi join table khi ghi.

### 19.15. “Khi thêm metadata vào bảng nối, chỉ cần thêm `@Column` vào `@ManyToMany`”

Không phù hợp. `@ManyToMany` trực tiếp chủ yếu mô tả liên kết hai entity; khi link có thuộc tính riêng, dùng entity trung gian như `Enrollment` với hai `@ManyToOne` thường diễn đạt đầy đủ hơn.

### 19.16. “Cứ gọi `merge` một detached Student là mọi liên kết sẽ đúng”

Không chắc. `merge` có quy tắc cascade, state graph và đối tượng managed trả về. Service nên thao tác trên managed Student và Course trong transaction để kiểm soát thay đổi cụ thể.

## 20. Quy trình lựa chọn và triển khai

Khi thiết kế một quan hệ nhiều-nhiều JPA, có thể đi theo quy trình sau:

1. **Xác định bản chất nghiệp vụ:** hai phía có vòng đời độc lập không? Liên kết có thuộc tính riêng không?
2. **Kiểm tra schema:** cần bảng nối nào, FK nào, unique/primary key cho cặp nào?
3. **Quyết định chiều điều hướng:** một chiều có đủ không, hay cần hai chiều?
4. **Chọn owner:** bên thường chịu trách nhiệm thêm/bỏ liên kết trong service/aggregate.
5. **Khai báo `@JoinTable` tại owner:** đặt đúng `joinColumns` và `inverseJoinColumns`.
6. **Khai báo `mappedBy` ở inverse:** trỏ tới tên Java attribute của owner, không trỏ tới tên cột SQL.
7. **Tạo helper method đồng bộ:** mỗi thao tác thêm/bỏ phải sửa owning collection và inverse collection tương ứng.
8. **Chọn collection có ngữ nghĩa phù hợp:** thường `Set` cho membership; xây equality ổn định nếu cần.
9. **Cân nhắc cascade:** tránh `REMOVE` giữa hai entity độc lập; không tìm `orphanRemoval` ở `@ManyToMany`.
10. **Kiểm soát transaction và concurrency:** thao tác trên managed entity, bảo vệ PK/unique constraint, xác định semantics của xung đột.
11. **Kiểm soát fetch và API:** tránh trả object graph hai chiều trực tiếp, sử dụng projection/DTO hoặc fetch plan theo use case.
12. **Nếu link có metadata/lifecycle riêng:** cân nhắc thay `@ManyToMany` bằng entity trung gian.

Sơ đồ quyết định:

```text
                  Hai entity liên kết N:N?
                            |
                            v
           Bảng nối có thuộc tính/lifecycle riêng?
                    /                 \
                  Có                 Không
                   |                   |
                   v                   v
           Entity liên kết       @ManyToMany trực tiếp
           (hai @ManyToOne)             |
                                        v
                             Cần điều hướng hai chiều?
                                /             \
                              Không           Có
                               |               |
                               v               v
                       Một bên @JoinTable   Chọn một owner
                       không mappedBy            |
                                                v
                                   Owner: @JoinTable
                                   Inverse: mappedBy
                                                |
                                                v
                                   Helper thêm/bỏ cập nhật
                                   cả owning và inverse Set
                                                |
                                                v
                                   Ràng buộc UNIQUE/PK +
                                   transaction + fetch plan
```

## 21. Bài tập vận dụng

### Bài 1: Chỉ ra owning side

```java
@Entity
class Author {
    @ManyToMany
    @JoinTable(
        name = "author_book",
        joinColumns = @JoinColumn(name = "author_id"),
        inverseJoinColumns = @JoinColumn(name = "book_id")
    )
    Set<Book> books = new HashSet<>();
}

@Entity
class Book {
    @ManyToMany(mappedBy = "books")
    Set<Author> authors = new HashSet<>();
}
```

**Câu hỏi:** Ai sở hữu quan hệ? `mappedBy` trỏ tới đâu?

**Đáp án:** `Author.books` sở hữu join table `author_book`. `Book.authors` là inverse và `mappedBy = "books"` trỏ tới tên thuộc tính `Author.books`.

### Bài 2: Thêm liên kết từ inverse side

Developer viết:

```java
book.getAuthors().add(author);
```

**Câu hỏi:** Liệu có chắc một dòng `author_book` được tạo?

**Đáp án:** Không, nếu chỉ sửa inverse side. Cần cập nhật owning collection `author.books`; đồng thời giữ `book.authors` đồng bộ. Nên dùng helper `author.addBook(book)` hoặc `book.addAuthor(author)` ủy quyền tới owner.

### Bài 3: Giải thích `joinColumns` và `inverseJoinColumns`

Trong `Author.books`:

```java
@JoinTable(
    name = "author_book",
    joinColumns = @JoinColumn(name = "author_id"),
    inverseJoinColumns = @JoinColumn(name = "book_id")
)
```

**Câu hỏi:** Tại sao `author_id` là `joinColumns`?

**Đáp án:** Vì `Author` chứa owning attribute. `joinColumns` là FK trong bảng nối tham chiếu owning entity; `inverseJoinColumns` trỏ tới entity đích `Book`.

### Bài 4: Đổi owner sang Book

Muốn `Book.authors` trở thành owner.

**Yêu cầu:** Đổi hai khai báo.

**Đáp án gợi ý:**

```java
// Book (owner mới)
@ManyToMany
@JoinTable(
    name = "author_book",
    joinColumns = @JoinColumn(name = "book_id"),
    inverseJoinColumns = @JoinColumn(name = "author_id")
)
private Set<Author> authors;

// Author (inverse mới)
@ManyToMany(mappedBy = "authors")
private Set<Book> books;
```

Phải chỉnh helper và mọi luồng cập nhật để chúng sửa `Book.authors` làm nguồn chính.

### Bài 5: Xóa sinh viên khỏi khóa học

`Student.courses` là owner. Một ứng dụng gọi:

```java
student.withdraw(course);
```

**Câu hỏi:** Bảng nào nên được thay đổi, những entity nào được giữ lại?

**Đáp án:** Xóa cặp `(student_id, course_id)` trong bảng `student_course`. Row `student` và `course` vẫn còn; course có thể tiếp tục được sinh viên khác sử dụng.

### Bài 6: Có nên dùng `CascadeType.ALL`?

`Course` có 100 sinh viên. Một người đề xuất:

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses;
```

**Câu hỏi:** Nguy cơ khi xóa Student là gì?

**Đáp án:** `ALL` có `REMOVE`; provider có thể cố xóa Course thay vì chỉ xóa join row. Điều đó không phù hợp khi Course tồn tại độc lập và đang được sinh viên khác tham chiếu.

### Bài 7: Vì sao cần unique constraint?

Hai request cùng đăng ký Student 1 vào Course 10. Mỗi transaction kiểm tra Set và thấy chưa có liên kết.

**Câu hỏi:** `Set` có ngăn được cặp trùng trong DB không?

**Đáp án:** Không. Hai transaction có trạng thái riêng. Dùng PK ghép hoặc `UNIQUE(student_id, course_id)` tại DB, và thiết kế service xử lý thao tác đồng thời.

### Bài 8: Chuyển many-to-many thành entity liên kết

Bảng `student_course` được bổ sung `enrolled_at` và `grade`.

**Câu hỏi:** Nên ánh xạ thế nào?

**Đáp án:** Tạo entity `Enrollment` chứa dữ liệu liên kết và hai `@ManyToOne` tới Student, Course. Có thể dùng khóa ghép qua `@EmbeddedId`/`@MapsId` hoặc surrogate ID với unique key phù hợp.

### Bài 9: Thứ tự của quan hệ

UI cần hiển thị khóa học theo thời điểm đăng ký. Collection `Set<Course>` không có metadata thời điểm.

**Câu hỏi:** `@OrderBy("title")` có diễn đạt đúng không?

**Đáp án:** Không, nó sắp theo thuộc tính title của Course, không theo thời điểm đăng ký. Nếu thời điểm là thuộc tính của liên kết, nên cân nhắc `Enrollment.enrolledAt` và query order theo field đó.

### Bài 10: Khi nào không cần mapping hai chiều?

Ứng dụng chỉ có use case lấy các quyền (Role) của User, không cần truy cập từ Role về tập User qua object model.

**Câu hỏi:** Có cần `Role.users` và `mappedBy` không?

**Đáp án:** Không bắt buộc. Có thể dùng `@ManyToMany` một chiều ở `User.roles` với `@JoinTable`. Bảng nối vẫn biểu diễn many-to-many; tránh tạo collection inverse khi không cần thiết.

## 22. Ghi nhớ cốt lõi

- Trong `@ManyToMany` hai chiều, **chỉ một phía là owning side**. Phía đó định nghĩa `@JoinTable` và quản lý việc thêm/xóa liên kết ở bảng nối.
- Phía inverse dùng **`mappedBy` trỏ tới tên thuộc tính Java phía owner**. Nó không trỏ tới tên bảng hay tên cột SQL.
- Có thể chọn **một trong hai phía** làm owner. Lựa chọn nên phù hợp với luồng cập nhật nghiệp vụ và schema, rồi được sử dụng nhất quán.
- Khi sửa quan hệ hai chiều, hãy cập nhật **owning collection** để JPA ghi liên kết và **inverse collection** để object graph Java đúng ngay trong transaction.
- **`Set` không thay thế unique constraint**; equality của entity phải phù hợp nếu dùng `HashSet`, nhất là khi ID sinh tự động hoặc entity detached.
- Thêm/xóa một liên kết many-to-many thường chỉ thêm/xóa **row bảng nối**, không tự xóa entity ở phía bên kia.
- **Không tùy ý cascade REMOVE** qua many-to-many giữa entity độc lập; `@ManyToMany` cũng không hỗ trợ `orphanRemoval`.
- Nếu liên kết có dữ liệu hoặc vòng đời riêng, hãy cân nhắc **entity trung gian** như `Enrollment` với hai `@ManyToOne`.
- Fetch strategy, transaction, concurrency và DTO/API là các mối quan tâm riêng, cần xử lý cùng thiết kế mà không nhầm với ownership.

Khi cần quyết định một quan hệ nhiều-nhiều trong JPA, hãy bắt đầu từ **bảng nối lưu gì và thao tác nghiệp vụ nào làm thay đổi cặp khóa ngoại**. Sau đó chọn một owning attribute, để phía còn lại tham chiếu bằng `mappedBy` và triển khai helper thống nhất. Cách này giữ **schema, trạng thái Java và hành vi persistence** cùng biểu diễn một tập liên kết chính xác.
