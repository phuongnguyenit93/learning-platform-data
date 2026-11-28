# Chọn đầu chịu trách nhiệm cập nhật khi mô hình có hai chiều

Trong Neo4j, relationship có hướng và nối hai node. Ở tầng Java, Spring Data Neo4j (SDN) có thể ánh xạ cùng một relationship từ cả node nguồn lẫn node đích. Cách ánh xạ hai chiều giúp điều hướng thuận tiện, nhưng cũng đặt ra câu hỏi: khi cần thêm hoặc xóa quan hệ, phần nào của ứng dụng chịu trách nhiệm ghi thay đổi đó?

Cần phân biệt hướng của relationship trong graph, hướng ánh xạ bằng `@Relationship` và quyền chịu trách nhiệm cập nhật trong nghiệp vụ. Hướng ánh xạ cho SDN biết cách đọc hoặc ghi quan hệ tương ứng với entity. Quyền cập nhật nên được xác định rõ ở tầng domain/service để mọi thao tác đi qua một quy tắc nhất quán.

## 1. Hướng relationship không tự quyết định đầu chịu trách nhiệm nghiệp vụ

Giả sử hệ thống quản lý việc sinh viên đăng ký khóa học. Graph có relationship `ENROLLED_IN` từ `Student` đến `Course`:

~~~text
(Student)-[:ENROLLED_IN]->(Course)
~~~

Trong SDN, `direction = OUTGOING` trên `Student` mô tả quan hệ đi từ sinh viên đến khóa học. Ở phía `Course`, cùng relationship có thể được nhìn theo hướng `INCOMING`. Hai cách nhìn này cùng biểu diễn một relationship trong Neo4j; không cần tạo thêm relationship ngược.

`@Relationship(direction = OUTGOING)` và `@Relationship(direction = INCOMING)` mô tả cách ánh xạ quan hệ tương ứng với node hiện tại. Chúng không phải cơ chế phân quyền hay một khai báo owner tương tự `mappedBy` trong JPA. Vì vậy, ứng dụng cần tự quy định entity hoặc use case nào là đầu mối thực hiện thay đổi.

Một quy ước dễ duy trì là chọn một aggregate root hoặc service làm nơi điều phối việc tạo và xóa relationship. Các chức năng khác có thể truy vấn graph theo chiều ngược mà không cần tự ghi lại cùng một quan hệ.

## 2. Mô hình hóa hai phía của cùng một relationship

Ví dụ ánh xạ quan hệ từ phía `Student`:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Node("Student")
public class Student {
    @Id
    private String id;

    private String name;

    @Relationship(type = "ENROLLED_IN", direction = Relationship.Direction.OUTGOING)
    private Set<Course> courses = new HashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Ở phía `Course`, có thể ánh xạ cùng quan hệ theo chiều vào:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Node("Course")
public class Course {
    @Id
    private String id;

    private String title;

    @Relationship(type = "ENROLLED_IN", direction = Relationship.Direction.INCOMING)
    private Set<Student> students = new HashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

Với hai khai báo này, `Student.courses` và `Course.students` là hai góc nhìn của relationship `ENROLLED_IN`. Khi đọc một sinh viên, ứng dụng có thể điều hướng đến các khóa học; khi đọc một khóa học, ứng dụng có thể điều hướng đến các sinh viên.

Tuy nhiên, việc có hai thuộc tính Java không có nghĩa hai collection tự động đồng bộ trong bộ nhớ mỗi khi một bên thay đổi. Nếu ứng dụng đang giữ cả `Student` và `Course`, thêm khóa học vào `student.getCourses()` không tự động thêm sinh viên vào `course.getStudents()`. Muốn cả hai object đang nằm trong bộ nhớ phản ánh cùng trạng thái, code domain phải cập nhật cả hai tham chiếu hoặc tải lại dữ liệu sau khi ghi.

## 3. Chọn một đầu làm write owner ở tầng nghiệp vụ

Trong ví dụ đăng ký học, có thể chọn `Student` làm đầu mối chịu trách nhiệm thay đổi quan hệ. Mọi thao tác đăng ký hoặc hủy đăng ký đều đi qua `EnrollmentService`. Phía `Course` chủ yếu phục vụ truy vấn danh sách sinh viên.

Quy tắc này nên được thể hiện trong API của service: caller gửi `studentId` và `courseId`; service kiểm tra điều kiện đăng ký rồi thực hiện một thao tác ghi. Caller không tự sửa `Course.students` ở nhiều nơi khác nhau.

Ví dụ cập nhật relationship bằng Cypher qua repository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface StudentRepository extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (student:Student {id: $studentId})
        MATCH (course:Course {id: $courseId})
        MERGE (student)-[:ENROLLED_IN]->(course)
        """)
    void enroll(@Param("studentId") String studentId,
                @Param("courseId") String courseId);

    @Query("""
        MATCH (student:Student {id: $studentId})
              -[enrollment:ENROLLED_IN]->
              (course:Course {id: $courseId})
        DELETE enrollment
        """)
    void unenroll(@Param("studentId") String studentId,
                  @Param("courseId") String courseId);
}
~~~

`MERGE` tìm hoặc tạo pattern relationship giữa cặp node đó, nên các lần gọi tuần tự với cùng pattern sẽ dùng lại relationship đã có. Hai lệnh `MATCH` yêu cầu cả sinh viên và khóa học phải tồn tại; nếu một node không tồn tại, truy vấn không tạo ra relationship. Với yêu cầu duy nhất nghiêm ngặt dưới tải đồng thời, cần thiết kế thêm kiểm soát cạnh tranh phù hợp; không coi riêng `MERGE` là ràng buộc duy nhất cho mọi tình huống.

Service là nơi đặt quy tắc nghiệp vụ và transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EnrollmentService {
    private final StudentRepository studentRepository;

    public EnrollmentService(StudentRepository studentRepository) {
        this.studentRepository = studentRepository;
    }

    @Transactional
    public void enroll(String studentId, String courseId) {
        // Có thể kiểm tra điều kiện đăng ký trước khi ghi.
        studentRepository.enroll(studentId, courseId);
    }

    @Transactional
    public void unenroll(String studentId, String courseId) {
        studentRepository.unenroll(studentId, courseId);
    }
}
~~~

Trong hệ thống thực tế, service có thể kiểm tra trạng thái khóa học, giới hạn sĩ số, thời hạn đăng ký hoặc quyền của sinh viên. Các thao tác kiểm tra và ghi cần nằm trong transaction phù hợp để giữ tính nhất quán. Nếu có nhiều request đồng thời đăng ký suất cuối cùng, cần thiết kế thêm cơ chế kiểm soát cạnh tranh cho điều kiện sĩ số; `MERGE` relationship không tự bảo đảm giới hạn nghiệp vụ đó.

## 4. Truy vấn từ đầu ngược lại mà không cần ghi từ đầu đó

Dù `Student` là đầu mối ghi, ứng dụng vẫn có thể tìm sinh viên theo một khóa học bằng Cypher:

~~~cypher
MATCH (course:Course {id: $courseId})<-[:ENROLLED_IN]-(student:Student)
RETURN student.id AS id, student.name AS name
ORDER BY name
~~~

Repository ở phía `Course` có thể cung cấp chức năng đọc này:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface StudentSummary {
    String getId();
    String getName();
}

public interface CourseRepository extends Neo4jRepository<Course, String> {

    @Query("""
        MATCH (course:Course {id: $courseId})<-[:ENROLLED_IN]-(student:Student)
        RETURN student.id AS id, student.name AS name
        ORDER BY name
        """)
    List<StudentSummary> findStudents(@Param("courseId") String courseId);
}
~~~

Truy vấn đi ngược hướng relationship đã lưu để tìm sinh viên. Nó không cần tạo một relationship khác từ `Course` đến `Student`, và cũng không cần gọi `save(course)` chỉ để cập nhật danh sách sinh viên.

Nếu cần số lượng đăng ký, dùng phép tổng hợp thay vì tải toàn bộ entity:

~~~cypher
MATCH (course:Course {id: $courseId})
OPTIONAL MATCH (course)<-[:ENROLLED_IN]-(student:Student)
RETURN course.id AS courseId, count(DISTINCT student) AS enrollmentCount
~~~

Cách đọc riêng bằng projection giúp hợp đồng API rõ ràng và không làm phát sinh thao tác ghi ngoài ý muốn.

## 5. Đồng bộ hai phía trong bộ nhớ

Nếu domain đang giữ cả hai entity và cần thao tác trên object graph trước khi lưu, hãy cung cấp phương thức nghiệp vụ có tên rõ ràng để cập nhật hai phía:

~~~java
public void addCourse(Course course) {
    courses.add(course);
    course.addStudentReference(this);
}

public void addStudentReference(Student student) {
    students.add(student);
}
~~~

Ví dụ này chỉ minh họa đồng bộ object trong bộ nhớ. Nó không thay thế quy ước write owner và không có nghĩa SDN tự biết collection nào là nguồn chân lý khi hai phía khác nhau. Hãy xác định rõ object nào được lưu làm aggregate root và tránh gọi `save` từ cả hai phía cho cùng một thay đổi nếu chưa thiết kế rõ tác động của từng lần lưu.

Nếu không cần cả hai object tồn tại trong cùng một object graph, cách đơn giản hơn là chỉ ánh xạ collection ở phía write owner và dùng truy vấn Cypher để đọc chiều ngược. Đây thường là lựa chọn dễ kiểm soát hơn đối với quan hệ có số lượng lớn hoặc có vòng tham chiếu.

## 6. Rủi ro khi lưu từ phía không chịu trách nhiệm

Một entity SDN có thể chứa các trường `@Relationship` mà mapper dùng để đồng bộ graph khi lưu. Nếu ứng dụng đọc một entity với quan hệ chưa tải đầy đủ, thay đổi một thuộc tính đơn giản rồi lưu lại, cần hiểu rõ hình dạng graph được đưa vào thao tác save và hành vi của phiên bản SDN đang dùng.

Các rủi ro khi nhiều nơi cùng ghi một relationship gồm:

- Hai service có thể áp dụng quy tắc khác nhau cho cùng một quan hệ.
- Một collection chỉ chứa một phần dữ liệu có thể bị hiểu nhầm là toàn bộ trạng thái quan hệ cần lưu.
- Object đang nằm trong bộ nhớ có thể giữ collection ngược đã cũ sau khi một transaction khác thay đổi graph.
- Lưu cả hai entity ở hai thời điểm khác nhau có thể làm việc điều tra lỗi khó hơn vì không rõ thao tác nào là nguồn thay đổi cuối cùng.

Để giảm rủi ro, hãy:

1. Quy định một service hoặc aggregate root chịu trách nhiệm ghi relationship.
2. Dùng projection/DTO cho các màn hình chỉ đọc hoặc các truy vấn chiều ngược.
3. Không dùng entity có collection quan hệ chưa đầy đủ làm dữ liệu đầu vào cho thao tác save toàn graph.
4. Sau thao tác ghi, tải lại dữ liệu nếu cần object graph mới nhất ở cả hai phía.
5. Dùng transaction cho các bước kiểm tra và cập nhật cần tính nguyên tử.

## 7. Relationship có thuộc tính riêng

Nếu relationship có dữ liệu như ngày đăng ký, trạng thái hoặc nguồn đăng ký, hãy dùng relationship properties. Ví dụ:

~~~java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Enrollment {
    @RelationshipId
    private Long id;

    private LocalDate enrolledAt;

    private String status;

    @TargetNode
    private Course course;
}
~~~

Phía `Student` có thể ánh xạ collection `Set<Enrollment>` theo hướng `OUTGOING`:

~~~java
@Relationship(type = "ENROLLED_IN", direction = Relationship.Direction.OUTGOING)
private Set<Enrollment> enrollments = new HashSet<>();
~~~

Khi đó, service chịu trách nhiệm cập nhật relationship cũng cần quản lý các thuộc tính của enrollment như trạng thái và ngày đăng ký. Nếu `Course` cũng ánh xạ quan hệ theo chiều vào, hãy xác định rõ cách đọc và cập nhật relationship properties từ phía đó để tránh hai biểu diễn trong bộ nhớ mâu thuẫn.

Khi relationship có thuộc tính riêng, không nên chỉ xóa rồi tạo lại quan hệ nếu nghiệp vụ cần giữ lịch sử hoặc định danh relationship. Hãy quyết định rõ thao tác là cập nhật trạng thái relationship hiện tại, kết thúc một enrollment hay tạo một enrollment mới theo mô hình lịch sử.

## 8. Chọn chiến lược theo loại quan hệ

| Tình huống | Chiến lược phù hợp |
| --- | --- |
| Quan hệ đơn giản, một use case chủ yếu ghi từ một phía | Một collection `@Relationship` làm đường ghi chính |
| Cần truy vấn thường xuyên từ phía còn lại | Viết Cypher chiều ngược hoặc thêm ánh xạ inverse có quy ước chỉ đọc |
| Hai phía cần được thao tác trong cùng domain operation | Một service điều phối, đồng bộ object trong bộ nhớ và lưu theo quy ước đã chọn |
| Quan hệ có thuộc tính nghiệp vụ | `@RelationshipProperties` và một đầu mối quản lý trạng thái relationship |
| Quan hệ lớn hoặc collection thường phân trang | Truy vấn projection riêng, tránh tải cả collection vào entity |

## 9. Bài tập tự kiểm tra

1. Trong graph `(Student)-[:ENROLLED_IN]->(Course)`, `OUTGOING` trên `Student` và `INCOMING` trên `Course` mô tả điều gì?
2. Vì sao hướng `@Relationship` không tự quyết định service nào có quyền cập nhật nghiệp vụ?
3. Chọn `Student` làm write owner: hãy mô tả luồng đăng ký và hủy đăng ký một khóa học.
4. Viết truy vấn Cypher tìm tất cả sinh viên từ `courseId` mà không tạo relationship ngược.
5. Vì sao thay đổi `Student.courses` không tự cập nhật `Course.students` trong hai object đang nằm trong bộ nhớ?
6. Khi relationship có `status` và `enrolledAt`, cần bổ sung trách nhiệm gì cho service quản lý quan hệ?

Khi hoàn thành bài học, bạn cần xác định được một đầu mối ghi relationship rõ ràng, hiểu cách SDN ánh xạ cùng relationship từ hai hướng và biết cách truy vấn chiều ngược mà không tạo ra nhiều nơi cùng chịu trách nhiệm cập nhật. Điều này giúp mô hình quan hệ nhất quán, dễ kiểm thử và dễ bảo trì.
