# Thiết kế entity, ID và relationship có thuộc tính

Trong một ứng dụng quản lý khóa học, `Student` và `Course` là hai thực thể có danh tính riêng. Việc một học viên đăng ký một khóa học lại là một sự kiện gắn hai thực thể đó với nhau. Sự kiện đăng ký còn có dữ liệu riêng như lần đăng ký, thời điểm đăng ký, trạng thái và điểm cuối khóa. Những dữ liệu này mô tả **mối quan hệ giữa học viên và khóa học**, vì vậy có thể được lưu trực tiếp trên relationship trong Neo4j.

Bài thực hành này thiết kế một mô hình Spring Data Neo4j (SDN) hoàn chỉnh ở mức domain: node entity, chiến lược ID, optimistic locking và relationship properties. Ta sẽ dùng `@Node`, `@Id`, `@Version`, `@Relationship`, `@RelationshipProperties`, `@RelationshipId` và `@TargetNode`, sau đó kết nối các entity bằng repository và service có transaction.

## 1. Bài toán và yêu cầu nghiệp vụ

Xây dựng phần dữ liệu cho hệ thống đào tạo với các yêu cầu:

- Một học viên có thể đăng ký nhiều khóa học.
- Một khóa học có thể có nhiều học viên.
- Một học viên có thể học lại cùng khóa học ở các lần khác nhau.
- Mỗi lần đăng ký lưu `attemptNo`, `enrolledAt`, `status` và `finalScore`.
- Có thể tải một học viên cùng các lần đăng ký và khóa học tương ứng.
- Có thể cập nhật trạng thái hoặc điểm của một lần đăng ký mà không thay đổi danh tính của hai node đầu mút.
- ID node ổn định và có thể dùng trong API hoặc tích hợp với hệ thống khác.

Ta cần phân biệt ba loại dữ liệu:

| Dữ liệu | Ví dụ | Nơi lưu trong graph |
|---|---|---|
| Danh tính học viên | `studentId`, `fullName`, `email` | Property của node `Student` |
| Danh tính khóa học | `courseCode`, `title`, `credits` | Property của node `Course` |
| Thông tin của một lần đăng ký | `attemptNo`, `enrolledAt`, `status`, `finalScore` | Property của relationship `ENROLLED_IN` |

Nếu đặt `status` hoặc `finalScore` lên node `Student`, ta sẽ không biết giá trị đó thuộc lần đăng ký nào. Đó là dấu hiệu cho thấy dữ liệu thuộc về relationship.

## 2. Phác thảo graph trước khi viết Java

Mô hình cần biểu diễn một node học viên, một node khóa học và relationship có thuộc tính ở giữa:

```text
(:Student)
    |
    | ENROLLED_IN {
    |   attemptNo,
    |   enrolledAt,
    |   status,
    |   finalScore
    | }
    v
(:Course)
```

Ví dụ dữ liệu:

```cypher
(:Student {
    studentId: 'STU-1001',
    fullName: 'Nguyen An',
    email: 'an@example.test'
})
  -[:ENROLLED_IN {
      attemptNo: 1,
      enrolledAt: datetime('2026-09-01T08:00:00Z'),
      status: 'COMPLETED',
      finalScore: 8.5
    }]->
(:Course {
    courseCode: 'NEO4J-101',
    title: 'Graph Data Fundamentals',
    credits: 3
})
```

Relationship có hướng từ `Student` đến `Course`. Ta chỉ khai báo hướng điều hướng này trong entity `Student`; không cần thêm collection ngược trong `Course` nếu các use case có thể tìm học viên theo truy vấn riêng. Thiết kế một chiều giúp mapping rõ ràng và tránh mở rộng graph ngoài nhu cầu.

## 3. Quyết định node nào là entity và dữ liệu nào là relationship

`Student` và `Course` là node entity vì chúng có danh tính, tồn tại độc lập và được truy vấn riêng. `Enrollment` trong mô hình này là relationship properties vì nó mô tả một lần kết nối giữa đúng một học viên và một khóa học.

Hãy tự hỏi:

- Dữ liệu có ý nghĩa độc lập ngoài hai đầu mút hay không?
- Nó có cần được tìm kiếm, phân quyền hoặc tham chiếu từ nhiều nơi bằng ID riêng không?
- Nó có cần thêm các relationship khác, ví dụ người duyệt, hóa đơn hoặc chứng chỉ không?
- Nó có vòng đời và trạng thái nghiệp vụ phức tạp riêng không?

Nếu `Enrollment` chỉ mô tả lần đăng ký giữa `Student` và `Course`, relationship properties là phù hợp. Nếu về sau enrollment có vòng đời độc lập, nhiều node liên quan hoặc cần một khóa nghiệp vụ riêng, hãy cân nhắc mô hình hóa `Enrollment` thành node:

```text
(:Student)-[:HAS_ENROLLMENT]->(:Enrollment)-[:FOR_COURSE]->(:Course)
```

Không nên chọn relationship properties chỉ vì nó viết ít code hơn. Hãy chọn theo ngữ nghĩa và cách hệ thống cần truy vấn, cập nhật, bảo vệ dữ liệu.

## 4. Chọn chiến lược ID cho node

SDN dùng `@Id` để xác định property hoặc định danh được dùng làm identity của entity Java. Có ba lựa chọn phổ biến:

| Chiến lược | Cách khai báo | Khi phù hợp |
|---|---|---|
| ID nghiệp vụ được cấp sẵn | `@Id private String studentId;` | Có mã ổn định từ nghiệp vụ hoặc hệ thống nguồn |
| UUID do SDN sinh | `@Id @GeneratedValue(UUIDStringGenerator.class) private String id;` | Muốn ID surrogate ổn định, có thể sinh ở nhiều instance ứng dụng |
| ID nội bộ Neo4j | `@Id @GeneratedValue private Long id;` | ID kỹ thuật chỉ dùng trong phạm vi database |

Không dùng tên hoặc email có thể thay đổi làm ID chính nếu chúng không thật sự bất biến và duy nhất. ID nội bộ Neo4j phù hợp cho định danh kỹ thuật, nhưng không nên dùng làm mã công khai lâu dài vì ID nội bộ không phải business key của ứng dụng.

Trong capstone này, ta dùng ID nghiệp vụ dạng `String`: `studentId` và `courseCode`. Cách này giúp API và dữ liệu tích hợp sử dụng mã ổn định, dễ đọc.

## 5. Vì sao ID được cấp sẵn cần @Version?

Khi application tự gán ID trước khi gọi SDN, framework không thể chỉ dựa vào việc ID có `null` hay không để biết object mới hay đã tồn tại. Với business ID, `@Version` giúp SDN nhận diện trạng thái mới và hỗ trợ optimistic locking.

Khai báo field version kiểu `Long`:

```java
@Version
private Long version;
```

Với entity mới, version ban đầu để `null`; SDN quản lý giá trị sau khi lưu và tự tăng trong các lần cập nhật phù hợp. Không tự gán hoặc tự tăng version trong service. Kiểu wrapper `Long` biểu diễn được trạng thái chưa có version, trong khi `long` luôn có giá trị mặc định `0`.

`@Version` không thay thế uniqueness constraint. `@Version` phát hiện cập nhật dựa trên dữ liệu cũ; uniqueness constraint bảo vệ database khỏi hai node có cùng business ID.

## 6. Khai báo node Student

Tạo `Student.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Student")
public class Student {

    @Id
    private String studentId;

    @Version
    private Long version;

    private String fullName;
    private String email;

    @Relationship(type = "ENROLLED_IN", direction = Relationship.Direction.OUTGOING)
    private List<Enrollment> enrollments = new ArrayList<>();

    protected Student() {
    }

    public Student(String studentId, String fullName, String email) {
        this.studentId = studentId;
        this.fullName = fullName;
        this.email = email;
    }

    public String getStudentId() {
        return studentId;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public Long getVersion() {
        return version;
    }

    public List<Enrollment> getEnrollments() {
        return List.copyOf(enrollments);
    }

    public void enroll(Course course, int attemptNo, java.time.ZonedDateTime enrolledAt) {
        if (attemptNo < 1) {
            throw new IllegalArgumentException("attemptNo phải lớn hơn hoặc bằng 1");
        }
        enrollments.add(new Enrollment(course, attemptNo, enrolledAt));
    }

    public Optional<Enrollment> findAttempt(String courseCode, int attemptNo) {
        return enrollments.stream()
            .filter(enrollment -> enrollment.getCourse().getCourseCode().equals(courseCode))
            .filter(enrollment -> enrollment.getAttemptNo() == attemptNo)
            .findFirst();
    }
}
```

Các điểm cần chú ý:

- `@Node("Student")` ánh xạ class với node có label `Student`.
- `@Id` đánh dấu `studentId` là identity được SDN dùng cho entity.
- `@Version` hỗ trợ nhận diện entity mới và kiểm soát cập nhật cạnh tranh.
- `@Relationship` xác định type `ENROLLED_IN` và hướng `OUTGOING`.
- `List<Enrollment>` cho phép một học viên có nhiều lần đăng ký, kể cả nhiều lần với cùng khóa học.
- Constructor không tham số để `protected` cho mapping; constructor còn lại phục vụ nghiệp vụ.

## 7. Khai báo node Course

Tạo `Course.java`:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Course")
public class Course {

    @Id
    private String courseCode;

    @Version
    private Long version;

    private String title;
    private int credits;

    protected Course() {
    }

    public Course(String courseCode, String title, int credits) {
        this.courseCode = courseCode;
        this.title = title;
        this.credits = credits;
    }

    public String getCourseCode() {
        return courseCode;
    }

    public String getTitle() {
        return title;
    }

    public int getCredits() {
        return credits;
    }

    public Long getVersion() {
        return version;
    }
}
```

`Course` không khai báo collection `students` hoặc `enrollments` ngược. Khi cần liệt kê học viên của một khóa học, ta có thể dùng repository query hoặc Cypher riêng. Nhờ vậy, mỗi aggregate có một hướng điều hướng rõ ràng.

## 8. Khai báo relationship properties Enrollment

Neo4j cho phép relationship có property. SDN dùng `@RelationshipProperties` để ánh xạ loại dữ liệu này. Tạo `Enrollment.java`:

```java
import java.time.ZonedDateTime;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Enrollment {

    @RelationshipId
    private Long id;

    @TargetNode
    private Course course;

    private int attemptNo;
    private ZonedDateTime enrolledAt;
    private String status;
    private Double finalScore;

    protected Enrollment() {
    }

    public Enrollment(Course course, int attemptNo, ZonedDateTime enrolledAt) {
        this.course = course;
        this.attemptNo = attemptNo;
        this.enrolledAt = enrolledAt;
        this.status = "ACTIVE";
    }

    public Course getCourse() {
        return course;
    }

    public int getAttemptNo() {
        return attemptNo;
    }

    public ZonedDateTime getEnrolledAt() {
        return enrolledAt;
    }

    public String getStatus() {
        return status;
    }

    public Double getFinalScore() {
        return finalScore;
    }

    public void complete(double score) {
        if (score < 0.0 || score > 10.0) {
            throw new IllegalArgumentException("Điểm phải nằm trong khoảng 0 đến 10");
        }
        this.finalScore = score;
        this.status = "COMPLETED";
    }
}
```

`Enrollment` không có `@Node`; đây không phải node entity. `@TargetNode` chỉ rõ node ở đầu đích của relationship theo góc nhìn `Student`. `@RelationshipId` lưu định danh nội bộ của relationship để SDN nhận diện đúng relationship hiện có khi đồng bộ graph. Trường này không phải mã đăng ký nghiệp vụ và không nên đưa ra API.

Relationship properties class cần một trường `@TargetNode` để xác định node đầu kia và trường relationship ID theo quy ước của SDN. Không tự gán `id`; SDN quản lý giá trị đó.

## 9. Ghép ba class thành domain model

Sau khi tạo ba file, mô hình có cấu trúc:

```text
Student.java
  @Node("Student")
  @Id studentId
  @Version version
  List<Enrollment> enrollments
       |
       | @Relationship("ENROLLED_IN")
       v
Enrollment.java
  @RelationshipProperties
  @RelationshipId id
  @TargetNode Course course
  attemptNo
  enrolledAt
  status
  finalScore
       |
       | target node
       v
Course.java
  @Node("Course")
  @Id courseCode
  @Version version
```

Đây là một quan hệ nhiều-nhiều: một học viên có thể có nhiều enrollment; một khóa học có thể được nhiều học viên tham gia. Neo4j lưu từng enrollment thành một relationship riêng.

## 10. Phân biệt ID của node và ID của relationship

Trong mô hình này có ba loại định danh khác nhau:

| Field | Đối tượng | Vai trò | Có phải business ID? |
|---|---|---|---|
| `Student.studentId` | Node Student | ID nghiệp vụ của học viên | Có |
| `Course.courseCode` | Node Course | Mã nghiệp vụ của khóa học | Có |
| `Enrollment.id` | Relationship ENROLLED_IN | ID nội bộ để SDN nhận diện relationship | Không |

Không nhầm `@RelationshipId` với `@Id` của node. Relationship ID không thay thế `attemptNo`; `attemptNo` là dữ liệu nghiệp vụ để phân biệt các lần học lại.

Nếu API cần mã enrollment ổn định để client tham chiếu, hoặc enrollment có lifecycle độc lập, hãy cân nhắc chuyển enrollment thành node entity có `enrollmentId` riêng. Không nên lấy relationship internal ID làm public identifier.

## 11. Tạo uniqueness constraint cho ID nghiệp vụ

`@Id` xác định identity trong mapping SDN, nhưng không tự tạo uniqueness constraint trong database. Để Neo4j bảo vệ business ID trước mọi client ghi dữ liệu, tạo constraint:

```cypher
CREATE CONSTRAINT student_id_unique IF NOT EXISTS
FOR (s:Student)
REQUIRE s.studentId IS UNIQUE;

CREATE CONSTRAINT course_code_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseCode IS UNIQUE;
```

Constraint đảm bảo không có hai node `Student` cùng `studentId` và không có hai node `Course` cùng `courseCode`. Các constraint này nên được quản lý bằng migration/schema deployment thay vì chờ ứng dụng lưu entity đầu tiên.

Nếu email cũng cần duy nhất, có thể tạo thêm constraint trên `Student.email`. Không tạo uniqueness constraint cho `fullName` vì nhiều học viên có thể trùng tên.

## 12. Tạo repository cho hai node entity

Tạo `StudentRepository.java`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface StudentRepository extends Neo4jRepository<Student, String> {

    Optional<Student> findByEmail(String email);
}
```

Tạo `CourseRepository.java`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CourseRepository extends Neo4jRepository<Course, String> {
}
```

Không cần tạo repository riêng cho `Enrollment` vì nó là relationship properties class, không phải node aggregate. Các thao tác đăng ký được thực hiện thông qua aggregate `Student` trong mô hình này.

## 13. Viết service đăng ký khóa học

Service cần đọc hai node đầu mút, tạo relationship properties rồi lưu aggregate. Đặt toàn bộ thao tác trong một transaction để việc đọc và ghi có ranh giới nhất quán.

```java
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrollmentService {

    private final StudentRepository studentRepository;
    private final CourseRepository courseRepository;

    public EnrollmentService(
            StudentRepository studentRepository,
            CourseRepository courseRepository) {
        this.studentRepository = studentRepository;
        this.courseRepository = courseRepository;
    }

    @Transactional
    public Student enroll(String studentId, String courseCode, int attemptNo) {
        Student student = studentRepository.findById(studentId)
            .orElseThrow(() -> new StudentNotFoundException(studentId));

        Course course = courseRepository.findById(courseCode)
            .orElseThrow(() -> new CourseNotFoundException(courseCode));

        student.enroll(course, attemptNo, ZonedDateTime.now(ZoneOffset.UTC));

        return studentRepository.save(student);
    }
}
```

`StudentNotFoundException` và `CourseNotFoundException` là exception nghiệp vụ do ứng dụng định nghĩa. `ZonedDateTime` lưu mốc thời gian có múi giờ; ví dụ dùng UTC để nhất quán giữa các instance ứng dụng.

Trong mô hình này, `attemptNo` phân biệt các lần đăng ký. Service thực tế cần kiểm tra quy tắc attempt, ví dụ attempt kế tiếp phải lớn hơn attempt gần nhất. Quy tắc đó thuộc domain và nên được đặt trong service hoặc aggregate, không phụ thuộc vào UI.

## 14. Cập nhật trạng thái và điểm trên relationship

Một lợi ích của relationship properties là có thể cập nhật dữ liệu của mối quan hệ mà không biến nó thành node. Ví dụ hoàn tất lần đăng ký thứ hai:

```java
@Transactional
public Student completeAttempt(
        String studentId,
        String courseCode,
        int attemptNo,
        double finalScore) {

    Student student = studentRepository.findById(studentId)
        .orElseThrow(() -> new StudentNotFoundException(studentId));

    Enrollment enrollment = student.findAttempt(courseCode, attemptNo)
        .orElseThrow(() -> new EnrollmentNotFoundException(studentId, courseCode, attemptNo));

    enrollment.complete(finalScore);
    return studentRepository.save(student);
}
```

Đây là method bổ sung vào `EnrollmentService`. Nó thay đổi `status` và `finalScore` của đúng relationship được tìm theo khóa học và lần đăng ký, sau đó lưu lại aggregate `Student`.

Khi relationship có `@RelationshipId`, SDN có thể nhận diện relationship đã tồn tại và cập nhật nó thay vì coi mọi quan hệ như một quan hệ mới. Không tạo một `Enrollment` object mới khi mục tiêu là cập nhật lần đăng ký cũ.

## 15. Đọc graph bằng Cypher để kiểm tra mapping

Sau khi đăng ký, dùng Cypher kiểm tra cả node và property trên relationship:

```cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN]->
      (c:Course)
RETURN s.studentId AS studentId,
       s.fullName AS studentName,
       c.courseCode AS courseCode,
       c.title AS courseTitle,
       e.attemptNo AS attemptNo,
       e.enrolledAt AS enrolledAt,
       e.status AS status,
       e.finalScore AS finalScore
ORDER BY e.attemptNo;
```

Query thể hiện đúng vị trí của dữ liệu:

- `s.*` là property trên node `Student`.
- `c.*` là property trên node `Course`.
- `e.*` là property trên relationship `ENROLLED_IN`.

Nếu `finalScore` chưa có, giá trị có thể là `null`. Không cần tạo node phụ chỉ để lưu một thuộc tính mô tả lần đăng ký.

## 16. So sánh mapping với Cypher thuần

Các annotation SDN mô tả cấu trúc Java tương ứng với graph:

| Java | Neo4j |
|---|---|
| `@Node("Student")` | Label `Student` |
| `@Id studentId` | Property identity `studentId` của node |
| `@Version version` | Property version do SDN quản lý |
| `@Relationship(type = "ENROLLED_IN")` | Relationship type `ENROLLED_IN` |
| `@RelationshipProperties` | Class ánh xạ property của relationship |
| `@TargetNode Course course` | Node `Course` ở đầu kia |
| `@RelationshipId Long id` | Internal relationship identity dùng trong mapping |

SDN tạo và ánh xạ Cypher dựa trên metadata. Khi dùng repository hoặc `Neo4jTemplate`, không cần tự viết Cypher cho CRUD cơ bản. Custom Cypher hữu ích khi cần traversal, aggregate hoặc read model riêng; khi đó cần trả đủ node và relationship mà mapper cần.

## 17. Một số quy tắc thiết kế relationship có thuộc tính

**Đặt property đúng chỗ.** `enrolledAt`, `attemptNo`, `status` và `finalScore` mô tả một lần đăng ký nên thuộc relationship. `fullName` thuộc Student; `title` thuộc Course.

**Chọn hướng rõ ràng.** `Student -> Course` là hướng được khai báo. Nếu cần danh sách học viên của khóa học, truy vấn ngược bằng repository/Cypher thay vì mặc định thêm mapping hai chiều.

**Dùng collection có chủ đích.** `List<Enrollment>` thể hiện các lần đăng ký có thứ tự nghiệp vụ qua `attemptNo`; không dựa vào thứ tự collection để biểu diễn lần học.

**Giữ relationship ID nội bộ.** `@RelationshipId` giúp SDN quản lý identity của relationship. Business identifier như `attemptNo` vẫn là property riêng.

**Không nhồi lifecycle độc lập vào relationship.** Khi Enrollment cần nhiều quan hệ khác, nhiều aggregate tham chiếu hoặc một ID công khai riêng, chuyển nó thành node.

## 18. Kiểm thử mapping node và relationship properties

Có thể dùng `@DataNeo4jTest` để kiểm tra mapping với Neo4j test database được cấu hình trong dự án:

```java
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataNeo4jTest
class EnrollmentMappingTest {

    @Autowired
    StudentRepository studentRepository;

    @Autowired
    CourseRepository courseRepository;

    @Test
    void mapsRelationshipPropertiesBetweenStudentAndCourse() {
        Course course = courseRepository.save(
            new Course("NEO4J-101", "Graph Data Fundamentals", 3)
        );

        Student student = new Student(
            "STU-1001", "Nguyen An", "an@example.test"
        );
        student.enroll(
            course,
            1,
            ZonedDateTime.of(2026, 9, 1, 8, 0, 0, 0, ZoneOffset.UTC)
        );

        studentRepository.save(student);

        Student loaded = studentRepository.findById("STU-1001").orElseThrow();
        Enrollment enrollment = loaded.getEnrollments().get(0);

        assertThat(enrollment.getCourse().getCourseCode()).isEqualTo("NEO4J-101");
        assertThat(enrollment.getAttemptNo()).isEqualTo(1);
        assertThat(enrollment.getStatus()).isEqualTo("ACTIVE");
        assertThat(enrollment.getEnrolledAt()).isEqualTo(
            ZonedDateTime.of(2026, 9, 1, 8, 0, 0, 0, ZoneOffset.UTC)
        );
        assertThat(enrollment.getFinalScore()).isNull();
    }
}
```

Test dùng `get(0)` sau khi đã tạo đúng một enrollment. Cần database Neo4j phù hợp với cấu hình test của ứng dụng; không thể xác nhận mapping relationship properties chỉ bằng mock repository.

`@DataNeo4jTest` thường chạy trong transaction kiểm thử và rollback sau test. Assertion trong test xác nhận SDN đã ghi và đọc được relationship trong transaction đó; nếu cần kiểm tra dữ liệu tồn tại sau commit thực tế, hãy dùng test không có test-managed transaction hoặc kết thúc transaction test tường minh.

## 19. Những trường hợp cần kiểm thử thêm

1. Lưu một Student chưa có enrollment và xác nhận collection đọc về rỗng.
2. Lưu một Student với nhiều Course khác nhau.
3. Lưu hai lần enrollment cho cùng một Course với `attemptNo` khác nhau.
4. Đọc lại và xác nhận `status`, `enrolledAt`, `attemptNo` nằm trên relationship.
5. Cập nhật điểm của một lần đăng ký và xác nhận lần đăng ký khác không đổi.
6. Xác nhận `studentId` và `courseCode` không trùng nhờ constraint database.
7. Cập nhật đồng thời cùng Student và xác nhận optimistic locking hoạt động.
8. Xác nhận query ngược từ Course tìm được các Student cần thiết dù entity không khai báo relationship hai chiều.
9. Xác nhận không đưa `Enrollment.id` nội bộ vào response API.
10. Kiểm tra hành vi khi chuyển Enrollment thành node nếu nghiệp vụ phát sinh nhu cầu lifecycle độc lập.

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SDN không nhận class Enrollment là relationship properties | Thiếu `@RelationshipProperties` | Đánh dấu class bằng annotation đúng package SDN. |
| Không biết node đầu kia của relationship là gì | Thiếu hoặc khai báo sai `@TargetNode` | Khai báo đúng một field target node trong relationship properties class. |
| Relationship bị ghi lại như quan hệ mới hoặc mất property | Thiếu relationship ID mapping | Khai báo field `Long` với `@RelationshipId` và để SDN quản lý. |
| Gán `@Node` cho Enrollment trong khi muốn lưu property trên cạnh | Nhầm relationship properties với node entity | Dùng `@RelationshipProperties` cho dữ liệu thuộc mối quan hệ. |
| `@Id` đã có nhưng database vẫn chứa ID trùng | Chưa có uniqueness constraint | Tạo constraint trên label và property ID. |
| Entity dùng assigned ID nhưng trạng thái mới/cũ không được nhận diện đúng | Thiếu `@Version` | Thêm field `Long` với `@Version` và không tự chỉnh version. |
| Relationship không được đọc như mong muốn | Sai type hoặc direction | Kiểm tra type, `OUTGOING`/`INCOMING` và chiều thực tế trong graph. |
| Graph bị tải quá rộng | Mapping quan hệ hai chiều không cần thiết | Giữ một hướng điều hướng hoặc dùng projection/query giới hạn. |
| Không thể cập nhật đúng một lần đăng ký | Chỉ tìm theo Student và Course, bỏ qua attempt | Dùng business property như `attemptNo` để xác định lần đăng ký. |
| Cần tham chiếu Enrollment từ nhiều aggregate | Relationship properties không có business identity riêng | Cân nhắc chuyển Enrollment thành node entity. |

## 21. Quy trình thiết kế entity, ID và relationship có thuộc tính

1. Viết yêu cầu nghiệp vụ và xác định thực thể tồn tại độc lập.
2. Chọn node label cho từng entity, ví dụ `Student` và `Course`.
3. Chọn ID ổn định cho mỗi node; tránh dùng field có thể thay đổi làm business ID.
4. Nếu dùng assigned ID, thêm `@Version Long` để SDN nhận diện entity mới và hỗ trợ optimistic locking.
5. Xác định dữ liệu nào mô tả mối liên kết; chuyển chúng thành relationship properties.
6. Khai báo class relationship bằng `@RelationshipProperties`, một `@TargetNode` và `@RelationshipId`.
7. Khai báo relationship ở aggregate sở hữu với type và direction rõ ràng.
8. Tạo repository cho node aggregate, không tạo repository cho relationship properties class.
9. Tạo uniqueness constraint cho business ID ở cấp Neo4j.
10. Viết service transaction để đọc hai đầu mút, tạo/cập nhật relationship properties và lưu aggregate.
11. Kiểm tra graph bằng Cypher để xác nhận property nằm đúng trên node hoặc relationship.
12. Viết integration test cho create, read, update, nhiều relationship và concurrency.
13. Đánh giá lại mô hình nếu relationship bắt đầu có lifecycle, identity hoặc các quan hệ riêng.

## 22. Ghi nhớ

`@Node` ánh xạ entity Java thành node Neo4j; `@Id` xác định identity của node; `@Version` hỗ trợ nhận diện entity mới và optimistic locking khi dùng ID được cấp sẵn. ID nghiệp vụ nên ổn định, và uniqueness constraint phải được tạo riêng ở database để bảo vệ tính duy nhất.

Khi dữ liệu mô tả mối liên kết giữa hai node, dùng `@RelationshipProperties` cùng `@TargetNode` để biểu diễn node đích và các property của relationship. `@RelationshipId` là định danh nội bộ phục vụ mapping, không phải business ID. Chọn type và direction rõ ràng, tránh mapping hai chiều nếu không cần. Nếu mối quan hệ có vòng đời hoặc danh tính độc lập, hãy chuyển nó thành node entity. Kết hợp domain model, constraint, repository, transaction và integration test sẽ tạo nền tảng graph dễ hiểu, an toàn khi cập nhật và phù hợp với nghiệp vụ.

## Tài liệu tham khảo

- [Spring Data Neo4j – Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j – Handling and provisioning of unique IDs](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Spring Data Neo4j – RelationshipProperties API](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/schema/RelationshipProperties.html)
- [Spring Data Neo4j – RelationshipId API](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/schema/RelationshipId.html)
- [Neo4j Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
