# Ánh xạ quan hệ có thuộc tính và kiểm soát hướng quan hệ

Trong Neo4j, relationship không chỉ kết nối hai node mà còn có thể mang **property** riêng: ngày bắt đầu, vai trò, trạng thái, điểm đánh giá, số lượng, thời điểm hiệu lực... Khi xây dựng ứng dụng Java với **Spring Data Neo4j (SDN)**, cần ánh xạ chính xác cả **thuộc tính của relationship** và **chiều của cạnh** để dữ liệu lưu xuống property graph đúng với ý nghĩa nghiệp vụ.

Bài thuộc chương **Spring Data Neo4j** của module `DATABASE_ENGINE_GRAPH_NEO4J`, nơi Neo4j được sử dụng để mô hình hóa dữ liệu liên kết, truy vấn node/relationship bằng Cypher, tối ưu bằng index và constraint, đồng thời tích hợp Java Driver và Spring Data Neo4j. Trọng tâm là các annotation `@Node`, `@Relationship`, `@RelationshipProperties`, `@TargetNode`, `@RelationshipId`, cách dùng `OUTGOING`/`INCOMING`, và những tình huống dễ tạo cạnh ngược chiều hoặc mất thuộc tính khi cập nhật.

Ví dụ nhắm tới Spring Data Neo4j hiện đại, đặc biệt dòng SDN 7.x cùng Spring Boot 3.x. Các chi tiết API và hành vi lưu dữ liệu cần được đối chiếu với phiên bản SDN/Neo4j thật sự chạy trong dự án; bài không thay thế kiểm thử tích hợp.

Sau bài học, bạn có thể:

- Phân biệt thuộc tính node với thuộc tính relationship trong property graph.
- Ánh xạ relationship có property thành một lớp `@RelationshipProperties` với `@TargetNode`.
- Xác định đúng chiều của relationship khi đọc/ghi từ mỗi đầu node.
- Sử dụng repository và service để lưu một aggregate có relationship properties.
- Dùng truy vấn Cypher tường minh khi chỉ cần cập nhật một quan hệ, tránh thao tác trên aggregate chưa tải đủ.
- Kiểm tra hướng cạnh, số lượng cạnh, dữ liệu property và các lỗi khi lưu bằng integration test.

## 1. Relationship có thuộc tính là gì?

Xét nghiệp vụ **sinh viên đăng ký khóa học**:

~~~text
(:Student {studentId:'S01', fullName:'An'})
          |
          | [:ENROLLED_IN {
          |    enrollmentKey:'S01|C101',
          |    enrolledOn:date('2026-01-12'),
          |    status:'ACTIVE',
          |    score:85
          | }]
          v
(:Course {code:'C101', title:'Nhập môn đồ thị'})
~~~

Đồ thị có:

- Node `Student` lưu thông tin sinh viên.
- Node `Course` lưu thông tin khóa học.
- Relationship `ENROLLED_IN` **đi từ Student đến Course**.
- Các property `enrolledOn`, `status`, `score` mô tả **lần/quan hệ đăng ký cụ thể**, không mô tả bản thân sinh viên hay khóa học.

Một khóa học có thể được nhiều sinh viên đăng ký với thời điểm, trạng thái và điểm số khác nhau. Vì vậy, đặt `score` hoặc `enrolledOn` trên `Course` sẽ làm mất sự phân biệt giữa các lượt đăng ký.

Truy vấn Cypher đọc đúng hướng và property:

~~~cypher
MATCH (s:Student {studentId: 'S01'})
      -[e:ENROLLED_IN]->(c:Course {code: 'C101'})
RETURN s.studentId AS studentId,
       c.code AS courseCode,
       e.enrolledOn AS enrolledOn,
       e.status AS status,
       e.score AS score;
~~~

**Quan trọng:** lớp Java mô tả relationship properties **không mặc nhiên tạo node trung gian**. Nếu dùng `@RelationshipProperties`, đồ thị vẫn có một cạnh `(:Student)-[:ENROLLED_IN]->(:Course)` mang property, chứ không phải `(:Student)-[:HAS]->(:Enrollment)-[:TO]->(:Course)`.

## 2. Phân biệt hai mô hình: property trên cạnh và node trung gian

| Tiêu chí | Relationship có property | Enrollment là node riêng |
| --- | --- | --- |
| Cấu trúc | `(Student)-[ENROLLED_IN]->(Course)` | `(Student)-[:HAS]->(Enrollment)-[:FOR]->(Course)` |
| Thuộc tính đăng ký | Trực tiếp trên `ENROLLED_IN`. | Trên node `Enrollment`. |
| Số bước đi từ Student đến Course | Một relationship. | Thường là hai relationship. |
| Phù hợp khi | Đăng ký chủ yếu là mối liên hệ giữa hai thực thể, có vài property. | Đăng ký có vòng đời độc lập, nhiều quan hệ riêng, lịch sử phức tạp hoặc cần được tham chiếu như thực thể. |
| Đánh đổi | Khó biểu diễn một số mô hình cần nhiều loại cạnh nối *vào chính lần đăng ký*. | Tăng số node và số bước traversal; cần quản lý mô hình phong phú hơn. |

Không có quy tắc “mọi bảng liên kết trong RDBMS phải thành node” hoặc “mọi quan hệ nhiều–nhiều phải dùng relationship properties”. Hãy xác định trước **bất biến nghiệp vụ**: liệu một sinh viên có thể đăng ký lại cùng khóa ở học kỳ khác? Nếu có, cùng hai endpoint có thể cần nhiều relationship có `enrollmentKey` khác nhau, hoặc một thực thể Enrollment có định danh riêng để quản lý các lần đăng ký.

Trong ví dụ dưới đây, giả định **mỗi cặp sinh viên–khóa học chỉ có một đăng ký đang quản lý**; hệ thống có thể định danh đăng ký bằng một khóa nghiệp vụ riêng. Khi chuyển sang mô hình nhiều lần đăng ký, cần thêm học kỳ hoặc mã lượt vào khóa.

## 3. Các annotation cốt lõi

| Annotation | Đặt ở đâu? | Tác dụng |
| --- | --- | --- |
| `@Node("Student")` | Lớp entity của node. | Ánh xạ đối tượng thành node có label `Student`. |
| `@Id` | Trường khóa của node. | Chỉ định thuộc tính định danh thực thể ở tầng SDN. |
| `@Relationship(type="ENROLLED_IN", direction=...)` | Field ở node chủ sở hữu mapping. | Khai báo loại và **chiều tương đối với node chứa field**. |
| `@RelationshipProperties` | Lớp chứa property của cạnh. | Đánh dấu đối tượng là biểu diễn một relationship có property. |
| `@TargetNode` | Một field trong lớp relationship properties. | Chỉ đến **node còn lại** trong relationship được ánh xạ. |
| `@RelationshipId` | Field trong lớp relationship properties. | Giữ định danh kỹ thuật của relationship do SDN quản lý để hỗ trợ nhận diện relationship đã lưu. |
| `@Property("...")` | Field node hoặc relationship properties, khi cần. | Đặt tên property trong Neo4j khác tên field Java. |

Một lớp `@RelationshipProperties` thông thường cần **một `@TargetNode`** và định danh relationship theo cơ chế SDN hỗ trợ. Không thay `@RelationshipId` bằng `@Id` của node; relationship không trở thành node chỉ vì Java có đối tượng biểu diễn nó.

`@RelationshipId` không phải khóa nghiệp vụ được gửi ra API. Không tự gán hoặc suy ra rằng ID kỹ thuật của relationship là ổn định qua mọi lần xóa/tạo lại hoặc nhập lại dữ liệu. Khi hệ thống cần định danh đăng ký từ bên ngoài, dùng một property nghiệp vụ riêng như `enrollmentKey` và cân nhắc constraint tương ứng.

## 4. Ánh xạ hoàn chỉnh một quan hệ có property

Ví dụ gồm ba lớp riêng trong cùng package Java: `Student.java`, `Course.java` và `Enrollment.java`.

### 4.1. Node Course

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Course")
public class Course {
    @Id
    private String code;

    private String title;

    public Course() {
    }

    public Course(String code, String title) {
        this.code = code;
        this.title = title;
    }

    public String getCode() {
        return code;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Ở đây `@Id` là khóa nghiệp vụ `Course.code`; ví dụ sử dụng khóa chuỗi do ứng dụng cung cấp. Nếu ứng dụng muốn SDN tự sinh khóa node, cấu hình `@GeneratedValue`/ID strategy là một vấn đề riêng, không liên quan trực tiếp tới chiều relationship.

### 4.2. Lớp Enrollment ánh xạ property của cạnh

~~~java
import java.time.LocalDate;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Enrollment {
    @RelationshipId
    private Long id;

    @TargetNode
    private Course course;

    private String enrollmentKey;
    private LocalDate enrolledOn;
    private String status;
    private Integer score;

    public Enrollment() {
    }

    public Enrollment(String enrollmentKey, Course course,
                      LocalDate enrolledOn, String status) {
        this.enrollmentKey = enrollmentKey;
        this.course = course;
        this.enrolledOn = enrolledOn;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public Course getCourse() {
        return course;
    }

    public String getEnrollmentKey() {
        return enrollmentKey;
    }

    public LocalDate getEnrolledOn() {
        return enrolledOn;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Integer getScore() {
        return score;
    }

    public void setScore(Integer score) {
        this.score = score;
    }
}
~~~

Lưu ý các nhóm field:

- `id` được gắn `@RelationshipId`: **định danh kỹ thuật**, không phải property nghiệp vụ do client nhập. Để SDN quản lý nó.
- `course` được gắn `@TargetNode`: chỉ tới node còn lại của quan hệ tính từ `Student`.
- `enrollmentKey`, `enrolledOn`, `status`, `score` là **property của relationship `ENROLLED_IN`**.
- `LocalDate` phù hợp với property ngày không mang giờ; nếu nghiệp vụ cần dấu thời gian và múi giờ, cân nhắc kiểu temporal được Neo4j/SDN hỗ trợ và quy ước thời gian nhất quán.

Không đặt `@Node` lên `Enrollment` trong mô hình này. Nếu thêm một field tham chiếu trực tiếp tới `Student` bên trong Enrollment rồi coi đó là một quan hệ riêng, có thể tạo vòng tham chiếu Java và cấu trúc mapping không như dự kiến. Node gốc `Student` được xác định bởi field `@Relationship` ở phần tiếp theo.

### 4.3. Node Student khai báo hướng OUTGOING

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Student")
public class Student {
    @Id
    private String studentId;

    private String fullName;

    @Relationship(
        type = "ENROLLED_IN",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Enrollment> enrollments = new ArrayList<>();

    public Student() {
    }

    public Student(String studentId, String fullName) {
        this.studentId = studentId;
        this.fullName = fullName;
    }

    public String getStudentId() {
        return studentId;
    }

    public String getFullName() {
        return fullName;
    }

    public List<Enrollment> getEnrollments() {
        return enrollments;
    }

    public void addEnrollment(Enrollment enrollment) {
        enrollments.add(enrollment);
    }
}
~~~

Với `@Relationship(... OUTGOING)` trên `Student.enrollments` và `Enrollment.course` là `@TargetNode`, mô hình Java tương ứng:

~~~text
Student entity
  | enrollments: List<Enrollment>
  |    |-- id (relationship identity)
  |    |-- enrollmentKey, enrolledOn, status, score
  |    '-- course: Course (@TargetNode)
  |
  v
Neo4j: (Student)-[e:ENROLLED_IN { ... }]->(Course)
~~~

**Đừng nhầm:** một danh sách `List<Enrollment>` không có nghĩa mỗi Enrollment là node. Đây là cách SDN đóng gói **relationship + property + node đích** thành một đối tượng Java.

## 5. Kiểm soát hướng: OUTGOING và INCOMING

Neo4j lưu mỗi relationship với một **node bắt đầu** và **node kết thúc**. Trong Cypher, hướng được biểu diễn bằng mũi tên:

~~~cypher
// Đi từ Student sang Course.
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
RETURN s.studentId, c.code, e.status;
~~~

~~~cypher
// Cùng cạnh đó nhưng đọc từ phía Course.
MATCH (c:Course)<-[e:ENROLLED_IN]-(s:Student)
RETURN c.code, s.studentId, e.status;
~~~

Hai truy vấn trên **mô tả cùng một hướng cạnh vật lý**: `Student → Course`. Truy vấn thứ hai chỉ bắt đầu từ đầu còn lại của cạnh.

| Nơi đặt field `@Relationship` | Direction | Cạnh được ánh xạ |
| --- | --- | --- |
| `Student` | `OUTGOING` | `(Student)-[:ENROLLED_IN]->(Course)` |
| `Course` | `INCOMING` | `(Student)-[:ENROLLED_IN]->(Course)` |
| `Course` | `OUTGOING` | `(Course)-[:ENROLLED_IN]->(Student)` — ngược mô hình đang chọn |
| `Student` | `INCOMING` | `(Course)-[:ENROLLED_IN]->(Student)` — ngược mô hình đang chọn |

**Quy tắc:** hướng của annotation là **tương đối với node Java chứa field**, không phải hướng “điều hướng con trỏ Java” hoặc tên lớp relationship properties.

### 5.1. Đọc từ đầu Course bằng INCOMING

Nếu một màn hình chỉ cần biết sinh viên nào đăng ký một khóa học, cách biểu diễn phía Course có thể là:

~~~java
@Node("Course")
public class CourseView {
    @Id
    private String code;

    @Relationship(
        type = "ENROLLED_IN",
        direction = Relationship.Direction.INCOMING
    )
    private List<Student> students;

    // Các constructor/getter khác được lược bỏ.
}
~~~

Đây là **ví dụ ánh xạ riêng cho góc nhìn từ Course**. Đừng dùng đồng thời `Course` và `CourseView` như hai aggregate có quyền cập nhật cùng một tập relationship nếu chưa hiểu cách SDN quản lý lưu đồ thị. Ngoài ra, `List<Student>` **không mang các property `status`, `enrolledOn` của relationship** trong đối tượng Java; nó chỉ biểu diễn node liên kết. Khi cần đọc các property từ đầu Course, có thể viết query Cypher/projection riêng, hoặc định nghĩa một lớp relationship-properties phía đó với `@TargetNode` là `Student` và kiểm soát quyền ghi của từng aggregate.

Không tự gán rằng cùng một lớp `Enrollment` có `@TargetNode Course` sẽ tự tái sử dụng hoàn hảo cho một field `INCOMING` trên `Course`. Với ánh xạ từ đầu Course, node “còn lại” chính là `Student`, vì vậy cấu trúc wrapper cần xét lại.

### 5.2. Truy vấn không ghi hướng thì sao?

~~~cypher
MATCH (a:Student)-[e:ENROLLED_IN]-(b:Course)
RETURN a.studentId, b.code;
~~~

Mẫu `-[e]-` không ràng buộc hướng; có thể hữu ích khi khảo sát dữ liệu nhưng cũng có thể **che giấu cạnh tạo sai chiều**. Với nghiệp vụ đăng ký khóa học, nên chỉ rõ mũi tên ở truy vấn đọc quan trọng và đặc biệt ở truy vấn ghi.

### 5.3. Mối quan hệ không tự có “nghịch đảo” ở tầng Java

Nếu `Student.enrollments` được thay đổi trong bộ nhớ, một field `Course.students` trên một đối tượng khác **không mặc nhiên đồng bộ ngay trong bộ nhớ** như một cấu trúc hai chiều được ORM bảo đảm. Cả hai biểu diễn có thể đọc cùng một relationship trong Neo4j, nhưng vòng đời đối tượng, thời điểm load và phạm vi save là những việc riêng.

Đặc biệt tránh cấu hình cả hai phía để cùng tự động ghi, rồi lần lượt lưu một đối tượng chỉ chứa **tập cạnh chưa tải đủ**. Một thay đổi ở phía sau có thể xóa hoặc ghi đè thông tin phía trước tùy trạng thái aggregate/mapping.

## 6. Repository và service lưu quan hệ có property

Định nghĩa repository cơ bản:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface StudentRepository
        extends Neo4jRepository<Student, String> {
}
~~~

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CourseRepository
        extends Neo4jRepository<Course, String> {
}
~~~

Một service có thể kiểm tra node nguồn và đích, sau đó thêm wrapper Enrollment vào aggregate Student:

~~~java
import java.time.LocalDate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrollmentService {
    private final StudentRepository students;
    private final CourseRepository courses;

    public EnrollmentService(StudentRepository students,
                             CourseRepository courses) {
        this.students = students;
        this.courses = courses;
    }

    @Transactional
    public void enroll(String studentId, String courseCode,
                       LocalDate enrolledOn) {
        Student student = students.findById(studentId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy sinh viên"));
        Course course = courses.findById(courseCode)
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy khóa học"));

        boolean alreadyEnrolled = student.getEnrollments().stream()
            .anyMatch(e -> courseCode.equals(e.getCourse().getCode()));
        if (alreadyEnrolled) {
            throw new IllegalStateException("Đã có đăng ký");
        }

        // Chỉ là ví dụ khóa nghiệp vụ cho dữ liệu thử nghiệm.
        String enrollmentKey = studentId + "|" + courseCode;
        student.addEnrollment(new Enrollment(
            enrollmentKey, course, enrolledOn, "ACTIVE"));

        students.save(student);
    }
}
~~~

Các giả định của ví dụ:

1. Hai node đã tồn tại, khóa định danh là duy nhất và mỗi cặp Student–Course có tối đa một đăng ký.
2. `Student` được tải với tập relationship cần quản lý **đầy đủ** trong ngữ cảnh save; nếu một query chỉ nạp một phần, không được mặc định save toàn aggregate là cách cập nhật an toàn.
3. Các ID demo không chứa ký tự `|`; trong production, khóa ghép cần chuẩn hóa/escape rõ ràng hoặc dùng một mã đăng ký độc lập, không ghép chuỗi tùy tiện.
4. `@Transactional` cần chạy qua Spring proxy với transaction manager Neo4j phù hợp. Tự gọi method `@Transactional` từ một method khác trong chính bean có thể không đi qua cơ chế transaction của proxy.
5. Kiểm tra `alreadyEnrolled` là bảo vệ ở tầng nghiệp vụ **trong một phiên đọc**, chưa tự chống mọi race condition nếu có hai request đồng thời. Phải thêm chiến lược khóa/constraint và kiểm thử cạnh tranh khi dữ liệu quan trọng.

Sau khi lưu thành công, có thể kiểm tra bằng Cypher:

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN]->(c:Course {code: $courseCode})
RETURN s.studentId AS studentId,
       c.code AS courseCode,
       e.enrollmentKey AS enrollmentKey,
       e.enrolledOn AS enrolledOn,
       e.status AS status;
~~~

`save(...)` sẽ ghi node và các quan hệ thuộc aggregate theo mô hình ánh xạ của SDN. Không coi nó là câu lệnh “chỉ thêm đúng một relationship” trong mọi trường hợp. Nếu cập nhật lẻ một đăng ký trong tập rất lớn, một câu Cypher được thiết kế tường minh có thể dễ kiểm soát hơn.

## 7. Lưu và cập nhật relationship bằng Cypher tường minh

Khi ứng dụng chỉ muốn cập nhật **một** enrollment mà không tải toàn bộ danh sách sinh viên–khóa học, có thể đặt câu truy vấn Cypher trong repository hoặc gọi qua `Neo4jClient`.

### 7.1. Tạo/cập nhật một relationship có khóa nghiệp vụ

~~~cypher
MATCH (s:Student {studentId: $studentId})
MATCH (c:Course {code: $courseCode})
MERGE (s)-[e:ENROLLED_IN {
  enrollmentKey: $enrollmentKey
}]->(c)
ON CREATE SET e.enrolledOn = $enrolledOn
SET e.status = $status
RETURN count(e) AS matchedRelationships;
~~~

Điểm cần hiểu:

- `MATCH` xác minh cả hai endpoint. Nếu một endpoint không có, **không tạo quan hệ**, và `count(e)` bằng 0; service phải coi đó là tình trạng cần xử lý chứ không mặc định đã thành công.
- `MERGE` khớp **mẫu đầy đủ** theo type, hướng, endpoint và property `enrollmentKey`. Không có cạnh phù hợp thì tạo cạnh mới.
- Nếu đã có cạnh cùng hai endpoint nhưng **thiếu `enrollmentKey`** từ dữ liệu cũ, `MERGE` có thể tạo thêm cạnh khác; trước migration cần kiểm tra/dọn dữ liệu cũ.
- Nếu nhiều cạnh trùng đã tồn tại, một `MERGE` không tự sửa dữ liệu lịch sử về đúng một cạnh; phải đối soát và xử lý nguyên nhân.
- `ON CREATE SET` chỉ đặt ngày lần đầu tạo; `SET e.status` được áp dụng khi tạo hoặc khi khớp. Nếu nghiệp vụ cho phép chỉnh ngày đăng ký, thiết kế chính sách khác.

Có thể khai báo một truy vấn tương tự trong repository:

~~~java
import java.time.LocalDate;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface EnrollmentCommandRepository
        extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (s:Student {studentId: $studentId})
        MATCH (c:Course {code: $courseCode})
        MERGE (s)-[e:ENROLLED_IN {
          enrollmentKey: $enrollmentKey
        }]->(c)
        ON CREATE SET e.enrolledOn = $enrolledOn
        SET e.status = $status
        RETURN count(e)
        """)
    long upsertEnrollment(
        @Param("studentId") String studentId,
        @Param("courseCode") String courseCode,
        @Param("enrollmentKey") String enrollmentKey,
        @Param("enrolledOn") LocalDate enrolledOn,
        @Param("status") String status);
}
~~~

Hãy kiểm tra số kết quả trả về và ánh xạ kiểu scalar trên đúng phiên bản Spring Data Neo4j được dùng. Trong ứng dụng thật, nên gọi từ service có `@Transactional`, kiểm soát đầu vào, quyền ghi và lỗi uniqueness. Không truyền tên label/type động từ dữ liệu không tin cậy bằng cách nối chuỗi query.

### 7.2. Constraint cho khóa relationship

Nếu ứng dụng quyết định `enrollmentKey` là định danh toàn cục của một đăng ký:

~~~cypher
CREATE CONSTRAINT enrollment_key_unique IF NOT EXISTS
FOR ()-[e:ENROLLED_IN]-()
REQUIRE e.enrollmentKey IS UNIQUE;
~~~

Constraint này hạn chế **hai relationship `ENROLLED_IN` có cùng `enrollmentKey` khi property hiện diện**. Nó không tự bảo đảm mọi relationship có `enrollmentKey`, cũng không tự bảo đảm mỗi cặp Student–Course chỉ có một cạnh nếu các cạnh dùng khóa khác nhau. Trong hệ thống cần khóa tồn tại lẫn duy nhất, hãy đánh giá relationship key/existence theo phiên bản và edition Neo4j; đồng thời thiết kế quy tắc định danh nghiệp vụ và xử lý đồng thời.

Ví dụ, khi hai request cùng tạo đăng ký, cả hai có thể vượt qua kiểm tra `alreadyEnrolled` trước khi ghi. Constraint trên **cùng khóa nghiệp vụ được sinh ổn định** giúp chặn việc commit hai cạnh cùng khóa; service phải bắt lỗi, đọc lại trạng thái và quyết định retry/idempotency đúng cách.

### 7.3. Cập nhật riêng property của cạnh

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN {enrollmentKey: $enrollmentKey}]->
      (c:Course {code: $courseCode})
SET e.status = $newStatus
RETURN e.enrollmentKey AS enrollmentKey,
       e.status AS status;
~~~

Truy vấn này chỉ thay property `status` của cạnh phù hợp. Nếu không có relationship, truy vấn trả 0 hàng; service nên phân biệt “không tìm thấy” với “đã cập nhật”. Nếu có nhiều cạnh cùng cặp endpoint do dữ liệu hỏng, cần kiểm tra count và xử lý thay vì âm thầm cập nhật tất cả.

### 7.4. Xóa đúng cạnh thay vì xóa node

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN {enrollmentKey: $enrollmentKey}]->
      (c:Course {code: $courseCode})
DELETE e;
~~~

`DELETE e` chỉ xóa relationship khớp, **không xóa Student hoặc Course**. Không dùng `DETACH DELETE s` hoặc `DETACH DELETE c` để “hủy một đăng ký”; thao tác đó sẽ xóa cả node và các quan hệ liên kết khác.

Nếu nghiệp vụ cần lưu lịch sử hủy, thay xóa vật lý bằng `SET e.status = 'CANCELLED'` hoặc một mô hình sự kiện riêng. Quyết định đó ảnh hưởng query đọc, số cạnh và bất biến “một đăng ký đang hoạt động”.

## 8. Đọc từ repository mà vẫn giữ relationship properties

Một truy vấn chỉ trả `Student` hoặc `Course` có thể không đủ để SDN dựng toàn bộ quan hệ và các thuộc tính như mong muốn trong **custom @Query**. Khi muốn trả một aggregate Student gồm các Enrollment, cần cho mapper thấy root, relationship và target node.

Ví dụ:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface StudentGraphRepository
        extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (s:Student {studentId: $studentId})
        OPTIONAL MATCH (s)-[e:ENROLLED_IN]->(c:Course)
        RETURN s, collect(e), collect(c)
        """)
    Optional<Student> findWithEnrollments(
        @Param("studentId") String studentId);
}
~~~

`OPTIONAL MATCH` cho phép sinh viên không có đăng ký vẫn được trả về. `collect(e)` và `collect(c)` chuyển các cạnh và node liên quan vào cùng cấu trúc kết quả để mapper có dữ liệu dựng `Student.enrollments`. Cách viết projection/return shape cho custom query có thể chịu ảnh hưởng của phiên bản SDN; cần xác minh bằng integration test.

**Cảnh báo về aggregate chưa tải đủ:** nếu một truy vấn custom chỉ trả một phần danh sách Enrollment (ví dụ top 3 hoặc chỉ ACTIVE) rồi bạn chỉnh trường `fullName` và gọi `students.save(student)`, SDN có thể coi danh sách quan hệ trong đối tượng là trạng thái muốn duy trì và **ghi lại/xóa các quan hệ không có trong đối tượng** theo cơ chế save của phiên bản và loại mapping. Đừng dùng kết quả đọc một phần như một aggregate đầy đủ để ghi ngược mà không kiểm thử hành vi.

Nếu màn hình chỉ cần một danh sách hiển thị, dùng projection DTO đọc đơn giản sẽ giảm nguy cơ save nhầm:

~~~cypher
MATCH (s:Student {studentId: $studentId})
      -[e:ENROLLED_IN]->(c:Course)
RETURN c.code AS courseCode,
       c.title AS courseTitle,
       e.enrolledOn AS enrolledOn,
       e.status AS status,
       e.score AS score
ORDER BY courseCode;
~~~

Truy vấn trên chủ ý trả **dòng dữ liệu**, không phải một root aggregate cần lưu lại. Trong Java có thể ánh xạ kết quả qua `Neo4jClient` hoặc repository projection tương ứng với phiên bản SDN đang dùng.

## 9. Nhiều quan hệ, cardinality và identity

Một người học có thể đăng ký nhiều khóa:

~~~text
(Student S01)-[:ENROLLED_IN {status:'ACTIVE'}]->(Course C101)
      |
      '--[:ENROLLED_IN {status:'ACTIVE'}]----->(Course C102)
~~~

`List<Enrollment>` mô tả nhiều relationship; `Set<Enrollment>` cũng có thể phù hợp khi quy tắc Java định nghĩa đúng equality/hashCode. Cần phân biệt:

1. **Cardinality của mô hình Java:** một field là `Enrollment` hay `List<Enrollment>`.
2. **Số relationship thực tế:** Neo4j cho phép nhiều cạnh cùng type giữa cùng hai node nếu không có quy tắc ghi/ràng buộc ngăn điều đó.
3. **Định danh kỹ thuật:** `@RelationshipId` do SDN quản lý để nhận biết cạnh đã lưu.
4. **Định danh nghiệp vụ:** `enrollmentKey` được ứng dụng đặt và kiểm tra bằng constraint/luồng ghi.

Không dựa vào một `Set` với `equals/hashCode` dùng ID kỹ thuật khi ID còn null để bảo đảm “một sinh viên chỉ đăng ký một khóa một lần”. Hai đối tượng mới có thể cùng đại diện một cặp Student–Course; kiểm tra ở service và constraint là ranh giới khác.

### 9.1. Trường hợp có nhiều lần đăng ký cùng khóa

Nếu một sinh viên được đăng ký lại khóa C101 vào học kỳ khác:

~~~text
(Student S01)-[:ENROLLED_IN {
  enrollmentKey:'E-2026-SPRING-S01-C101',
  term:'2026-SPRING'
}]->(Course C101)

(Student S01)-[:ENROLLED_IN {
  enrollmentKey:'E-2026-FALL-S01-C101',
  term:'2026-FALL'
}]->(Course C101)
~~~

Đây là hai relationship riêng có cùng endpoint và type nhưng khác **khóa đăng ký**. Một câu `MERGE (s)-[e:ENROLLED_IN]->(c)` không có khóa lần đăng ký có thể khớp cả hai và cập nhật sai. Nếu nghiệp vụ có nhiều lần, hãy đưa term/enrollmentId vào điều kiện định danh và suy nghĩ xem Enrollment nên chuyển thành node độc lập hay chưa.

## 10. Kiểm soát đường đi và ngăn cạnh sai hướng

Nguyên tắc thiết kế tốt là chọn một **canonical direction** cho mỗi relationship type và ghi rõ nó trong tài liệu miền:

| Type | Đầu bắt đầu | Đầu kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| `ENROLLED_IN` | `Student` | `Course` | Sinh viên đăng ký khóa học. |
| `TEACHES` | `Teacher` | `Course` | Giảng viên dạy khóa học. |
| `PREREQUISITE_OF` | `Course` điều kiện tiên quyết | `Course` học sau | Khóa trước là điều kiện của khóa sau. |

Với loại quan hệ có ý nghĩa rõ ràng theo chiều, hãy giữ đúng chiều trong cả Cypher và annotation. Một lỗi thường thấy:

~~~cypher
// SAI với hợp đồng ENROLLED_IN đã chọn:
MERGE (c:Course {code: $courseCode})
      -[:ENROLLED_IN]->
      (s:Student {studentId: $studentId});
~~~

Lệnh trên có thể tạo/match node và tạo cạnh **Course → Student**. Nó không phải phép đọc ngược từ Course, mà là một hướng vật lý sai so với mô hình. Việc hai đầu là cùng hai node không làm hai cạnh ngược chiều trở thành một.

Truy vấn tìm cạnh sai hướng:

~~~cypher
MATCH (c:Course)-[e:ENROLLED_IN]->(s:Student)
RETURN c.code AS courseCode,
       s.studentId AS studentId,
       e.enrollmentKey AS enrollmentKey
LIMIT 50;
~~~

Trên mô hình chỉ cho phép `Student → Course`, truy vấn phải trả **0 hàng**. Khi có kết quả, hãy điều tra nguồn ghi trước khi sửa; không tự xóa hàng loạt vì có thể loại relationship được tạo bởi một use case khác dùng chung type sai thiết kế.

### 10.1. Kiểm tra một student có đúng các quan hệ cần thiết

~~~cypher
MATCH (s:Student {studentId: $studentId})
OPTIONAL MATCH (s)-[e:ENROLLED_IN]->(c:Course)
RETURN s.studentId AS studentId,
       count(e) AS relationshipCount,
       count(DISTINCT c) AS distinctCourses,
       collect(DISTINCT c.code) AS courseCodes;
~~~

Nếu bài toán cho phép tối đa một đăng ký trên mỗi khóa, `relationshipCount` phải bằng `distinctCourses` cho một sinh viên có đầy đủ endpoint. Nếu muốn cho phép học lại nhiều lần, **đây không còn là bất biến đúng**; cần chuyển sang kiểm tra số lần theo enrollmentKey/term.

### 10.2. Kiểm tra relationship thiếu thuộc tính quan trọng

~~~cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
WHERE e.enrollmentKey IS NULL
   OR e.enrolledOn IS NULL
   OR e.status IS NULL
RETURN s.studentId AS studentId,
       c.code AS courseCode,
       e.enrollmentKey AS enrollmentKey,
       e.enrolledOn AS enrolledOn,
       e.status AS status
ORDER BY studentId, courseCode
LIMIT 100;
~~~

Kết quả nên rỗng nếu tất cả enrollment hợp lệ đều phải có các property này. SDN annotation không tự biến mọi field Java thành database constraint; muốn bắt buộc tồn tại phải thiết kế schema và kiểm tra đầu vào phù hợp.

## 11. Transaction, cập nhật đồng thời và dữ liệu thiếu

Khi tạo một quan hệ và cập nhật trạng thái node liên quan, thực hiện các ghi cần nguyên tử **trong cùng transaction**. Dùng `@Transactional` của Spring đúng ranh giới service hoặc Neo4j Java Driver explicit/managed transaction phù hợp.

Những tình huống cần xử lý:

- **Endpoint không tồn tại:** `MATCH` trả 0 hàng, không được báo tạo thành công chỉ vì câu lệnh không ném exception.
- **Giao dịch đồng thời:** hai request có thể cùng thấy sinh viên chưa đăng ký và cùng cố tạo; uniqueness business key và chính sách retry cần được kiểm thử.
- **Aggregate tải không đầy đủ:** tránh `save` ghi lại một tập cạnh có một phần bị thiếu do custom query.
- **Cập nhật một property:** ưu tiên query chỉ sửa property của relationship mục tiêu khi không cần thay toàn bộ aggregate.
- **Quan hệ trùng từ dữ liệu cũ:** trước khi áp dụng `MERGE` hoặc constraint mới, đối soát số lượng cạnh và khóa nghiệp vụ.
- **Hủy đăng ký:** xác định dùng delete vật lý hay status `CANCELLED`; mỗi lựa chọn ảnh hưởng dữ liệu lịch sử và câu query.
- **Thiếu tenant:** ở hệ thống nhiều tenant, khóa `studentId` hoặc `courseCode` có thể không duy nhất toàn cục; dùng composite key (tenantId, businessId) và lọc cả hai endpoint.

Ví dụ truy vấn có điều kiện tenant, nếu trong database dùng khóa ghép:

~~~cypher
MATCH (s:Student {
  tenantId: $tenantId, studentId: $studentId
})
MATCH (c:Course {
  tenantId: $tenantId, code: $courseCode
})
MERGE (s)-[e:ENROLLED_IN {
  enrollmentKey: $enrollmentKey
}]->(c)
ON CREATE SET e.enrolledOn = $enrolledOn
SET e.status = $status
RETURN count(e) AS matchedRelationships;
~~~

Đây là biến thể minh họa **khi đã thêm `tenantId` vào cả hai loại node và thiết kế constraint ghép tương ứng**. Không dùng nó nguyên trạng cho hai lớp Java ở mục 4 nếu chưa thêm trường `tenantId` và cập nhật khóa định danh/luồng ghi.

## 12. Kiểm thử tích hợp: xem hình dạng đồ thị thực sự được lưu

Unit test chỉ kiểm tra `student.addEnrollment(...)` gọi thành công **không chứng minh** SDN đã lưu property và chiều cạnh đúng. Cần integration test trên một Neo4j thực, tốt nhất là instance/DB dành riêng cho test (ví dụ qua Testcontainers) và cấu hình SDN cùng phiên bản với ứng dụng.

### 12.1. Ma trận test tối thiểu

| Test | Hành động | Điều cần assert bằng Cypher |
| --- | --- | --- |
| T01 | Save một Student có Enrollment tới Course. | Có đúng một cạnh `Student-[ENROLLED_IN]->Course`, property đúng. |
| T02 | Tải Student lại qua repository. | `enrollments` có đúng Course target và các field property. |
| T03 | Truy vấn từ Course bằng `INCOMING`. | Nhìn thấy sinh viên gốc, không tạo cạnh ngược. |
| T04 | Thay `status` của một Enrollment. | Chỉ relationship phù hợp đổi trạng thái, node endpoint không bị thay sai. |
| T05 | Xóa relationship đăng ký. | Chỉ cạnh bị xóa; Student và Course vẫn tồn tại. |
| T06 | Hai request đồng thời tạo cùng enrollmentKey. | Không commit hai cạnh cùng khóa; lỗi được xử lý đúng. |
| T07 | Dữ liệu chứa cạnh sai hướng. | Query phát hiện cạnh sai; luồng đọc không coi cạnh sai là đăng ký hợp lệ. |
| T08 | Aggregate đọc một phần rồi save. | Không xóa mất các quan hệ khác; nếu nguy cơ tồn tại, đổi cách cập nhật. |
| T09 | Hai lần đăng ký cùng khóa khác term (nếu nghiệp vụ cho phép). | Có hai relationship được phân biệt bằng khóa/term, không ghi đè nhầm. |
| T10 | Endpoint không tồn tại. | Không có cạnh mới và service báo lỗi nghiệp vụ thích hợp. |

Các test phải biết chắc dữ liệu fixture ban đầu, không chạy chung với dữ liệu người dùng. Khi assert rollback hoặc commit, đọc bằng transaction độc lập khi cần; không chỉ kiểm tra trạng thái của object còn nằm trong bộ nhớ.

### 12.2. Cypher kiểm tra chiều, property, số lượng

Sau khi test gọi service đăng ký S01 vào C101:

~~~cypher
MATCH (s:Student {studentId: 'S01'})
      -[e:ENROLLED_IN]->(c:Course {code: 'C101'})
RETURN count(e) AS relationshipCount,
       collect(e.status) AS statuses,
       collect(e.enrollmentKey) AS businessKeys,
       collect(e.enrolledOn) AS enrolledDates;
~~~

Với fixture chỉ có một đăng ký, kỳ vọng `relationshipCount = 1`, danh sách trạng thái chứa `'ACTIVE'`, khóa nghiệp vụ và ngày tương ứng với yêu cầu. Kiểm tra chiều ngược:

~~~cypher
MATCH (c:Course {code: 'C101'})
      -[e:ENROLLED_IN]->
      (s:Student {studentId: 'S01'})
RETURN count(e) AS reversedRelationships;
~~~

Giá trị mong đợi của `reversedRelationships` là **0**. Nếu muốn kiểm tra cả hai hướng dưới một pattern vô hướng, có thể đọc và so sánh `startNode(e)`/`endNode(e)`; điều quan trọng là assert **hướng vật lý**.

### 12.3. Test mapper với Java repository

Một skeleton tích hợp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;

@DataNeo4jTest
class RelationshipMappingTest {
    @Autowired
    StudentRepository students;

    @Autowired
    CourseRepository courses;

    @Test
    void loadsRelationshipProperties() {
        Course course = courses.save(
            new Course("C101", "Nhập môn đồ thị"));
        Student student = new Student("S01", "An");
        student.addEnrollment(new Enrollment(
            "S01|C101", course, LocalDate.of(2026, 1, 12), "ACTIVE"));

        students.save(student);
        Student reloaded = students.findById("S01").orElseThrow();

        assertThat(reloaded.getEnrollments()).hasSize(1);
        Enrollment loaded = reloaded.getEnrollments().get(0);
        assertThat(loaded.getCourse().getCode()).isEqualTo("C101");
        assertThat(loaded.getStatus()).isEqualTo("ACTIVE");
        assertThat(loaded.getEnrolledOn())
            .isEqualTo(LocalDate.of(2026, 1, 12));
    }
}
~~~

Mẫu này minh họa API test và cần được chạy với một **Neo4j test instance đã cấu hình**, không tự khởi chạy database chỉ nhờ `@DataNeo4jTest`. Một số cấu hình test có transaction được rollback tự động; vì vậy bổ sung test đọc Cypher trong transaction độc lập để chứng minh **cạnh đã commit** nếu yêu cầu kiểm thử tính bền vững. Khi nhiều test cùng chạy, dùng khóa fixture khác nhau hoặc làm sạch database test để tránh false positive/negative.

## 13. Lỗi thường gặp khi ánh xạ quan hệ

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cạnh được tạo ngược chiều | `@Relationship(direction = INCOMING)` đặt trên Student dù mô hình yêu cầu OUTGOING; hoặc Cypher MERGE ngược. | Viết bảng canonical direction, kiểm tra mũi tên trong Cypher và test chiều. |
| Có node Course nhưng không có property Enrollment | Field là `List<Course>` thay vì `List<Enrollment>` chứa `@RelationshipProperties`. | Dùng wrapper có `@TargetNode`, đưa property lên wrapper. |
| Neo4j xuất hiện node Enrollment không mong muốn | Dùng `@Node` cho Enrollment trong mô hình định lưu property trên cạnh. | Chọn dứt khoát mô hình node trung gian hay relationship có property. |
| Load không thấy Enrollment | Custom Cypher không trả root + relationship + target, hoặc hướng/type sai. | Kiểm tra return shape, annotation và query bằng integration test. |
| Save làm mất cạnh khác | Lưu aggregate từ đối tượng chỉ tải một phần relationship. | Dùng query cập nhật hẹp hoặc tải đủ aggregate; test với nhiều cạnh sẵn có. |
| Sau retry có hai cạnh Student–Course | Không có khóa nghiệp vụ đủ ổn định hoặc không chặn ghi đồng thời. | Thiết kế `enrollmentKey` và uniqueness, xử lý retry/idempotency. |
| Tạo đăng ký không báo lỗi nhưng không có cạnh | Endpoint không tồn tại nên `MATCH` trả 0 hàng. | Kiểm tra số hàng ảnh hưởng và trả lỗi nghiệp vụ. |
| Thêm INCOMING ở Course dẫn đến ghi đè không mong muốn | Hai aggregate cùng được dùng để ghi trạng thái cạnh nhưng load không đồng bộ. | Quy định đầu ghi chính và tách read model/projection. |
| `@RelationshipId` được dùng như mã đăng ký công khai | Nhầm ID kỹ thuật với khóa nghiệp vụ. | Dùng property business key và constraint riêng. |
| Cập nhật nhiều lần đăng ký bị ghi nhầm | `MERGE` theo endpoint/type mà không có khóa lần đăng ký. | Thêm enrollmentKey/term vào pattern hoặc dùng node Enrollment. |
| Sai tenant ở node đích | Lookup Course chỉ theo code khi code trùng giữa tenant. | Ràng buộc tenant trên cả hai endpoint và khóa ghép tương ứng. |
| Query vô hướng trả dữ liệu dù cạnh sai chiều | Dùng `-[:ENROLLED_IN]-` khi nghiệp vụ cần mũi tên cụ thể. | Dùng `->` hoặc `<-` theo hợp đồng. |

## 14. Câu hỏi luyện tập

**Bài 1 — Chọn vị trí property.** Hệ thống có `Student`, `Course` và thông tin `score`, `enrolledOn`, `status`. Giải thích vì sao ba trường sau thuộc relationship, không thuộc node `Student` hoặc `Course`. Nêu một tình huống khiến bạn chuyển Enrollment thành node riêng.

**Bài 2 — Mũi tên hai phía.** Với cạnh `(Student)-[:ENROLLED_IN]->(Course)`, viết annotation `@Relationship` tương ứng khi field nằm ở Student và khi field nằm ở Course. Viết hai truy vấn Cypher đọc cùng một cạnh từ hai hướng quan sát.

**Bài 3 — Thiếu @TargetNode.** Một lớp `@RelationshipProperties` chứa `status` nhưng không có trường `@TargetNode`. Hãy giải thích vì sao mapper không biết đầy đủ endpoint cần ghép, và chỉnh lớp cho đúng.

**Bài 4 — Dữ liệu trùng.** Một sinh viên có hai relationship `ENROLLED_IN` tới cùng Course, nhưng nghiệp vụ chỉ cho phép một. Thiết kế truy vấn phát hiện, cách sửa dữ liệu hiện có, constraint và service update để giảm nguy cơ tái diễn.

**Bài 5 — Hai lần đăng ký.** Sinh viên có thể đăng ký cùng khóa ở hai học kỳ. Hãy chọn khóa định danh mới và điều chỉnh lớp relationship properties/query `MERGE`. Giải thích vì sao `MERGE (student)-[:ENROLLED_IN]->(course)` không đủ.

**Bài 6 — Aggregate không đầy đủ.** Một repository query chỉ lấy ba enrollment đầu rồi code sửa `fullName` và `save(student)`. Những relationship còn lại có nguy cơ gì? Đề xuất một truy vấn chỉ cập nhật tên sinh viên và bộ integration test cần chạy.

**Bài 7 — Multi-tenant.** Cả hai tenant A và B đều có Student mã S01 và Course mã C101. Thiết kế khóa và truy vấn tạo `ENROLLED_IN` để không nối nhầm dữ liệu giữa hai tenant.

**Bài 8 — Kiểm thử hướng.** Viết hai assertion Cypher: một yêu cầu đúng một cạnh `Student → Course` với `status = 'ACTIVE'`, một yêu cầu không có cạnh `Course → Student` cùng type. Hãy giải thích vì sao chỉ xem dữ liệu Java sau khi save là chưa đủ.

## 15. Checklist trước khi đưa mapping vào production

1. **Định nghĩa miền dữ liệu:** relationship nào tồn tại, từ loại node nào đến loại node nào, và property thuộc node hay cạnh?
2. **Chọn hướng chuẩn:** mỗi type có canonical direction; annotation `OUTGOING`/`INCOMING` được viết tương đối đúng từ lớp sở hữu field.
3. **Chọn identity:** `@Id` là khóa node, `@RelationshipId` là kỹ thuật; khóa nghiệp vụ của relationship được quản lý riêng.
4. **Thiết kế aggregate:** ai được phép ghi tập relationship? Có custom query chỉ tải một phần và vô tình gọi `save` không?
5. **Bảo vệ dữ liệu:** constraint phù hợp, kiểm tra endpoint và tenant, xử lý cập nhật đồng thời và event retry.
6. **Kiểm thử đọc/ghi:** assert node, relationship type, hướng, số lượng, property, truy vấn INCOMING và trường hợp lỗi.
7. **Đo hiệu năng:** tải cả một tập relationship có hợp lý không, hay cần Cypher projection/cập nhật hẹp cho một màn hình cụ thể?
8. **Vận hành thay đổi:** có migration cho type/property mới, backfill relationship cũ, kiểm tra dữ liệu trùng và kế hoạch rollback không?

**Kết luận:** trong Spring Data Neo4j, `@RelationshipProperties` cho phép mô hình hóa **property của cạnh**, `@TargetNode` xác định node còn lại, còn `@Relationship(direction=...)` quy định **hướng vật lý của relationship tương đối với node đang ánh xạ**. Thiết kế đúng ba khía cạnh này, cùng với khóa nghiệp vụ, truy vấn Cypher có kiểm soát và integration test, giúp ứng dụng lưu property graph chính xác và tránh các lỗi quan hệ trùng, ngược chiều hoặc bị mất khi cập nhật aggregate.
