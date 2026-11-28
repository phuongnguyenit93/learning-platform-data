# Thực nghiệm save đồ thị được tải đầy đủ hoặc một phần

## Mục tiêu capstone

Bạn sẽ xây dựng một bài thực nghiệm nhỏ với Course và Student để quan sát cách Spring Data Neo4j (SDN) lưu một object graph trong ba tình huống:

1. Đọc đầy đủ aggregate root cùng các relationship được mô hình hóa, sửa một quan hệ rồi gọi save.
2. Chỉ đọc node gốc bằng custom Cypher, sau đó gọi save thông thường trên object graph chưa đầy đủ.
3. Đọc một phần graph, nhưng dùng saveAs với projection để giới hạn chính xác các thuộc tính được phép ghi.

Sau bài này, bạn có thể:

- Giải thích thế nào là object graph đầy đủ theo mapping của SDN.
- Nhận biết object được tạo từ custom query có thể thiếu relationship.
- Dự đoán tác động của save khi collection relationship chưa được hydrate.
- Dùng Neo4jTemplate.saveAs để ghi có giới hạn theo projection.
- Viết custom query trả một record cho mỗi root node và gom relationship/node bằng collect.
- Thiết kế kiểm thử để chứng minh node và relationship còn nguyên sau khi lưu.
- Chọn giữa repository.save, Neo4jTemplate.saveAs và Cypher cập nhật trực tiếp theo phạm vi thay đổi.

## 1. Bài toán: cập nhật một node nhưng không muốn làm mất relationship

Một hệ thống đào tạo có Course và Student. Một khóa học có nhiều học viên; một học viên có thể tham gia nhiều khóa học.

Ví dụ graph ban đầu:

~~~text
(:Course {code: "GRAPH-101", title: "Graph Fundamentals"})
    -[:ENROLLED]->
(:Student {code: "S-001", name: "An"})

(:Course {code: "GRAPH-101"})
    -[:ENROLLED]->
(:Student {code: "S-002", name: "Binh"})
~~~

Ứng dụng cần đổi tiêu đề khóa học. Có hai cách đọc dữ liệu thường gặp:

- Đọc aggregate root bằng repository query do SDN tạo. Mapping có thể lấy cả các relationship được khai báo trong domain model.
- Dùng custom Cypher chỉ trả về node Course. Object nhận được có các thuộc tính node, nhưng không có đủ dữ liệu để biết toàn bộ học viên đang liên kết.

Nếu gọi save thông thường với object thứ hai, SDN nhận được một graph trong bộ nhớ không có các relationship đã tồn tại. Khi persist, collection rỗng có thể được hiểu là tập quan hệ mong muốn hiện tại. Những quan hệ không có trong object có nguy cơ bị xóa.

Đây là vấn đề của ranh giới dữ liệu được đọc và ranh giới dữ liệu được ghi. Một object có đủ các field Java không có nghĩa là toàn bộ graph liên quan đã được tải.

## 2. Quy tắc cần kiểm chứng

Trong SDN 8.x, Neo4jOperations.save(entity) lưu entity cùng các related entities của nó. Đây là thao tác phù hợp khi object graph chứa đầy đủ dữ liệu mà bạn muốn đồng bộ.

Neo4jTemplate cũng cung cấp saveAs(entity, Projection.class). Projection đóng vai trò bản thiết kế cho thao tác ghi: chỉ các thuộc tính và relationship được định nghĩa trong projection mới được cập nhật.

Hai nguyên tắc cần giữ:

- Nếu dùng save thông thường, hãy tải ít nhất toàn bộ dữ liệu mà bạn dự định persist sau đó.
- Nếu object chỉ được tải một phần, hãy giới hạn phần được ghi bằng saveAs/projection hoặc dùng Cypher cập nhật đúng thuộc tính.

Không nên xem collection rỗng là dấu hiệu “chưa tải”. Trong object model thông thường, collection rỗng có thể mang nghĩa “không còn phần tử nào”. Ứng dụng cần xác định rõ dữ liệu nào đã được đọc trước khi quyết định ghi.

## 3. Chuẩn bị domain model

Dùng Course làm aggregate root. Course sở hữu relationship ENROLLED đi tới Student. Student không khai báo ngược lại collection Course trong ví dụ này để tránh tự mở rộng mapping thành một graph hai chiều lớn.

### 3.1. Course

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Course")
public class Course {

    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String title;
    private String description;

    @Relationship(
        type = "ENROLLED",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Student> students = new LinkedHashSet<>();

    protected Course() {
    }

    public Course(String code, String title, String description) {
        this.code = code;
        this.title = title;
        this.description = description;
    }

    public Long getId() {
        return id;
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

    public String getDescription() {
        return description;
    }

    public Set<Student> getStudents() {
        return students;
    }
}
~~~

### 3.2. Student

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Student")
public class Student {

    @Id
    @GeneratedValue
    private Long id;

    private String code;
    private String name;

    protected Student() {
    }

    public Student(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }
}
~~~

Trong ví dụ này, id do SDN sinh ra dùng để nhận diện entity. Thuộc tính code là mã nghiệp vụ để tìm khóa học và học viên trong bài thực nghiệm. Với domain dùng business ID làm @Id thay cho ID được sinh, cần thiết kế @Version theo quy tắc optimistic locking của SDN.

## 4. Khai báo repository và custom query

Khai báo repository cho Course và Student. CourseRepository có cả finder thông thường và custom query chỉ trả về node Course:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CourseRepository
        extends Neo4jRepository<Course, Long> {

    Optional<Course> findByCode(String code);

    @Query("""
        MATCH (c:Course {code: $code})
        RETURN c
        """)
    Optional<Course> findRootOnlyByCode(@Param("code") String code);
}
~~~

Repository cho Student:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface StudentRepository
        extends Neo4jRepository<Student, Long> {
}
~~~

Phương thức findRootOnlyByCode chỉ trả về node c. Nó cố ý không trả relationship ENROLLED và các node Student. Đây là dữ liệu đầu vào của thử nghiệm partial graph.

Trong dự án thật, custom query có thể trả về một phần graph do chỉ match một nhánh, giới hạn số quan hệ, chỉ trả root node, hoặc dùng projection chỉ có một số thuộc tính. Cần hiểu rõ query trả về những gì trước khi đưa object kết quả vào thao tác save.

## 5. Chuẩn bị dữ liệu thử nghiệm

Mỗi thử nghiệm cần bắt đầu từ graph có cùng trạng thái ban đầu: một Course và hai Student được nối bằng hai relationship ENROLLED.

~~~java
private Course seedCourse() {
    Student an = studentRepository.save(
        new Student("S-001", "An")
    );

    Student binh = studentRepository.save(
        new Student("S-002", "Binh")
    );

    Course course = new Course(
        "GRAPH-101",
        "Graph Fundamentals",
        "Introduction to graph persistence"
    );

    course.getStudents().add(an);
    course.getStudents().add(binh);

    return courseRepository.save(course);
}
~~~

Sau khi seed, kiểm tra số node và relationship bằng Cypher:

~~~cypher
MATCH (c:Course {code: "GRAPH-101"})
OPTIONAL MATCH (c)-[r:ENROLLED]->(s:Student)
RETURN c.code AS course,
       count(DISTINCT s) AS studentCount,
       count(r) AS enrollmentCount
~~~

Kết quả mong đợi:

| Chỉ số | Giá trị |
| --- | ---: |
| Course | 1 |
| Student | 2 |
| ENROLLED | 2 |

Dùng database test riêng hoặc test transaction rollback. Không chạy thử nghiệm có chủ đích xóa relationship trên dữ liệu dùng chung.

## 6. Thử nghiệm A: tải đầy đủ graph rồi save

Đọc Course bằng finder được SDN tạo từ repository:

~~~java
Course course = courseRepository.findByCode("GRAPH-101")
    .orElseThrow();

assertThat(course.getStudents())
    .extracting(Student::getCode)
    .containsExactlyInAnyOrder("S-001", "S-002");
~~~

Với domain model này, query do SDN tạo có thể hydrate các relationship được khai báo trên Course. Đây là graph đầy đủ theo phạm vi mapping đang dùng; nó không có nghĩa toàn bộ database hoặc mọi relationship không khai báo trong model đều được tải.

Bây giờ xóa học viên S-002 khỏi collection và đổi tiêu đề:

~~~java
course.getStudents().removeIf(
    student -> student.getCode().equals("S-002")
);

course.setTitle("Graph Persistence Lab");

course = courseRepository.save(course);
~~~

Đọc lại từ database:

~~~java
Course reloaded = courseRepository.findByCode("GRAPH-101")
    .orElseThrow();

assertThat(reloaded.getTitle())
    .isEqualTo("Graph Persistence Lab");

assertThat(reloaded.getStudents())
    .extracting(Student::getCode)
    .containsExactly("S-001");
~~~

Kết quả mong đợi:

- Thuộc tính title được cập nhật.
- Relationship ENROLLED tới S-001 vẫn còn.
- Relationship ENROLLED tới S-002 bị xóa vì ứng dụng đã chủ động loại học viên đó khỏi collection đầy đủ.
- Student S-002 vẫn là node độc lập trong graph nếu không có thao tác xóa node riêng.

Đây là hành vi phù hợp: ứng dụng đã tải đầy đủ association cần quản lý, sau đó biểu diễn trạng thái quan hệ mong muốn trong collection và persist thay đổi.

## 7. Thử nghiệm B: chỉ tải root node rồi gọi save thông thường

Khởi tạo lại fixture để có hai relationship. Dùng custom query chỉ trả về Course:

~~~java
Course partial = courseRepository
    .findRootOnlyByCode("GRAPH-101")
    .orElseThrow();

assertThat(partial.getCode()).isEqualTo("GRAPH-101");
assertThat(partial.getStudents()).isEmpty();
~~~

Object này chỉ có root node và các thuộc tính được trả về. Collection students không phản ánh hai relationship đang tồn tại trong database.

Chỉ đổi title rồi gọi save thông thường:

~~~java
partial.setTitle("Renamed from a partial graph");

courseRepository.save(partial);
~~~

Sau đó tải lại bằng finder đầy đủ và kiểm tra:

~~~java
Course reloaded = courseRepository.findByCode("GRAPH-101")
    .orElseThrow();

assertThat(reloaded.getTitle())
    .isEqualTo("Renamed from a partial graph");

assertThat(reloaded.getStudents()).isEmpty();
~~~

Trong thử nghiệm này, save nhận được một object graph không có association. Vì save thông thường lưu cả các related entities theo object được truyền vào, trạng thái association rỗng có thể được ghi thành trạng thái mong muốn. Hai relationship ENROLLED bị loại khỏi graph.

Đây là tình huống nguy hiểm: ý định nghiệp vụ chỉ là đổi title, nhưng object được lưu lại biểu diễn một graph thiếu relationship.

Không suy luận rằng một collection rỗng luôn có nghĩa xóa quan hệ trong mọi API hoặc mọi mapping tùy chỉnh. Hãy kiểm tra chính xác query, projection và cách object được khởi tạo. Quy tắc an toàn là không dùng save toàn phần cho một object mà association chưa được tải đầy đủ.

## 8. Thử nghiệm C: partial graph và saveAs với projection chỉ gồm thuộc tính node

Tạo lại fixture có hai học viên. Đọc root-only như thử nghiệm B:

~~~java
Course partial = courseRepository
    .findRootOnlyByCode("GRAPH-101")
    .orElseThrow();

partial.setTitle("Updated without loading students");
~~~

Định nghĩa projection cho những thuộc tính được phép ghi:

~~~java
public interface CourseCoreProjection {

    Long getId();

    String getCode();

    String getTitle();

    String getDescription();
}
~~~

Dùng Neo4jTemplate để persist theo projection:

~~~java
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class CourseUpdateService {

    private final CourseRepository courseRepository;
    private final Neo4jTemplate neo4jTemplate;

    public CourseUpdateService(
            CourseRepository courseRepository,
            Neo4jTemplate neo4jTemplate) {
        this.courseRepository = courseRepository;
        this.neo4jTemplate = neo4jTemplate;
    }

    public CourseCoreProjection renameCourse(String code) {
        Course partial = courseRepository
            .findRootOnlyByCode(code)
            .orElseThrow();

        partial.setTitle("Updated without loading students");

        return neo4jTemplate.saveAs(
            partial,
            CourseCoreProjection.class
        );
    }
}
~~~

Projection không khai báo students. Vì vậy thao tác saveAs chỉ cập nhật các thuộc tính node có trong projection và không đồng bộ collection students đang thiếu dữ liệu.

Kiểm tra lại:

~~~java
Course reloaded = courseRepository.findByCode("GRAPH-101")
    .orElseThrow();

assertThat(reloaded.getTitle())
    .isEqualTo("Updated without loading students");

assertThat(reloaded.getStudents())
    .extracting(Student::getCode)
    .containsExactlyInAnyOrder("S-001", "S-002");
~~~

Kết quả mong đợi:

| Thành phần | Kết quả |
| --- | --- |
| Course.title | Được cập nhật |
| Course.description | Giữ nguyên |
| Course.students | Không bị thay đổi |
| ENROLLED | Vẫn có 2 relationship |

Đây là lựa chọn phù hợp khi nghiệp vụ chỉ cập nhật thuộc tính của root node và không cần đọc hoặc ghi association.

Lưu ý: đối tượng trả về từ saveAs là projection, không phải một aggregate đã hydrate đầy đủ. Không dùng nó như thể đó là Course đầy đủ rồi tiếp tục gọi repository.save. Nếu cần thao tác tiếp trên toàn bộ graph, hãy đọc lại entity bằng một query đầy đủ.

## 9. Thử nghiệm D: projection có relationship khi muốn cập nhật association

Nếu nghiệp vụ cần thay đổi collection students, projection phải mô tả cả association đó.

~~~java
public interface CourseWithStudentsProjection {

    Long getId();

    String getTitle();

    Set<StudentProjection> getStudents();

    interface StudentProjection {
        Long getId();

        String getCode();

        String getName();
    }
}
~~~

Đọc đầy đủ Course trước khi thay đổi association:

~~~java
Course course = courseRepository.findByCode("GRAPH-101")
    .orElseThrow();

course.setTitle("Selected relationship update");

course.getStudents().removeIf(
    student -> student.getCode().equals("S-002")
);

CourseWithStudentsProjection saved = neo4jTemplate.saveAs(
    course,
    CourseWithStudentsProjection.class
);
~~~

Projection có students, nên association này nằm trong phạm vi được persist. Kết quả sau khi tải lại cần có một học viên:

~~~java
Course reloaded = courseRepository.findByCode("GRAPH-101")
    .orElseThrow();

assertThat(reloaded.getStudents())
    .extracting(Student::getCode)
    .containsExactly("S-001");
~~~

Projection có thể giới hạn những thuộc tính Student được ghi. Tuy nhiên, nếu projection bao gồm toàn bộ association students, collection được truyền vào vẫn cần chứa đầy đủ các quan hệ mà ứng dụng muốn giữ lại. Không dùng một tập con lấy từ truy vấn phân trang như thể nó là toàn bộ danh sách.

## 10. Custom Cypher phải trả đủ dữ liệu để hydrate association

SDN xử lý kết quả query theo record. Khi custom query trả nhiều record cho cùng một root node, object mapping có thể không ghép các relationship thành một aggregate hoàn chỉnh như bạn mong muốn.

Ví dụ query dễ gây vấn đề:

~~~cypher
MATCH (c:Course {code: $code})-[r:ENROLLED]->(s:Student)
RETURN c, r, s
~~~

Nếu Course có hai học viên, query tạo hai record cho cùng một node Course. Một object Course có thể xuất hiện lặp lại trong kết quả, trong khi từng record chỉ mang một phần relationship.

Để trả một record cho root và gom các quan hệ:

~~~cypher
MATCH (c:Course {code: $code})
OPTIONAL MATCH (c)-[r:ENROLLED]->(s:Student)
RETURN c, collect(r), collect(s)
~~~

Kết quả có một record chứa node c, danh sách relationship và danh sách Student liên quan. SDN có thể sử dụng các collection đó để hydrate association cho Course.

Một số điểm cần nhớ khi viết custom query:

- Trả về một record cho mỗi root entity cần map.
- Dùng collect để gom relationship và related node thay vì tạo nhiều record lặp root.
- Trả về cả relationship và node đích nếu cần map association.
- Nếu cần map nhiều cấp, phải trả đủ nodes/relationships cho những cấp đó.
- Với nhiều path, cần gom hoặc giảm các node và relationship trùng lặp.
- Không giả định chỉ trả về root node sẽ cung cấp đầy đủ association cho một lần save sau đó.

## 11. So sánh các lựa chọn persist

| Tình huống | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Đã tải đầy đủ association và muốn đồng bộ toàn bộ aggregate | repository.save(entity) hoặc template.save(entity) | Object graph biểu diễn đầy đủ trạng thái quan hệ cần ghi |
| Chỉ tải root node, muốn cập nhật title | Neo4jTemplate.saveAs(entity, CoreProjection.class) | Projection giới hạn thao tác vào thuộc tính root |
| Chỉ muốn cập nhật một vài field và không cần map object | Custom Cypher với MATCH/SET | Ghi đúng property, không cần serialize object graph |
| Muốn thêm/xóa association | Tải đủ collection rồi save, hoặc saveAs với projection có association | SDN cần biết tập quan hệ mong muốn |
| Chỉ có một phần collection do phân trang | Không save collection đó như toàn bộ aggregate | Phần không được tải có thể bị hiểu là đã bị loại bỏ |
| Cần lưu nhiều root theo cùng một projection | saveAllAs hoặc fluent save operation | Áp dụng cùng ranh giới persist cho nhiều entity |

Một ví dụ cập nhật một thuộc tính bằng Cypher:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public class CourseCypherUpdater {

    private final Neo4jClient neo4jClient;

    public CourseCypherUpdater(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public void rename(String code, String newTitle) {
        neo4jClient.query("""
            MATCH (c:Course {code: $code})
            SET c.title = $title
            RETURN c.code AS code
            """)
            .bind(code).to("code")
            .bind(newTitle).to("title")
            .fetch()
            .one();
    }
}
~~~

Custom Cypher phù hợp khi thao tác nhỏ, rõ ràng và không cần map toàn bộ aggregate. Khi dùng Cypher trực tiếp, ứng dụng chịu trách nhiệm giữ nhất quán với domain logic, optimistic locking, auditing và các quy tắc cập nhật khác của mình.

## 12. Thực nghiệm kiểm thử tích hợp

Đặt các thử nghiệm vào một test class sử dụng Neo4j test database riêng. Có thể dùng @DataNeo4jTest hoặc @SpringBootTest theo phạm vi cần kiểm tra; cấu hình Testcontainers hoặc Neo4j test server theo môi trường dự án.

Ví dụ cấu trúc test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jTemplate;

@DataNeo4jTest
class CourseGraphSaveExperimentTest {

    @Autowired
    CourseRepository courseRepository;

    @Autowired
    StudentRepository studentRepository;

    @Autowired
    Neo4jTemplate neo4jTemplate;

    private Course seedCourse() {
        Student an = studentRepository.save(
            new Student("S-001", "An")
        );

        Student binh = studentRepository.save(
            new Student("S-002", "Binh")
        );

        Course course = new Course(
            "GRAPH-101",
            "Graph Fundamentals",
            "Introduction to graph persistence"
        );

        course.getStudents().add(an);
        course.getStudents().add(binh);

        return courseRepository.save(course);
    }

    @Test
    void fullGraphSavePersistsIntentionalRelationshipRemoval() {
        seedCourse();

        Course course = courseRepository
            .findByCode("GRAPH-101")
            .orElseThrow();

        assertThat(course.getStudents()).hasSize(2);

        course.getStudents().removeIf(
            student -> student.getCode().equals("S-002")
        );

        courseRepository.save(course);

        Course reloaded = courseRepository
            .findByCode("GRAPH-101")
            .orElseThrow();

        assertThat(reloaded.getStudents())
            .extracting(Student::getCode)
            .containsExactlyInAnyOrder("S-001");
    }

    @Test
    void partialGraphAndSaveAsPreservesUnselectedRelationships() {
        seedCourse();

        Course partial = courseRepository
            .findRootOnlyByCode("GRAPH-101")
            .orElseThrow();

        assertThat(partial.getStudents()).isEmpty();

        partial.setTitle("Updated safely");

        neo4jTemplate.saveAs(
            partial,
            CourseCoreProjection.class
        );

        Course reloaded = courseRepository
            .findByCode("GRAPH-101")
            .orElseThrow();

        assertThat(reloaded.getTitle()).isEqualTo("Updated safely");
        assertThat(reloaded.getStudents()).hasSize(2);
    }
}
~~~

Ví dụ dùng package @DataNeo4jTest của Spring Boot 4: org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest. Với Spring Boot 3, import tương ứng là org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest. Đoạn test minh họa hai hành vi chính; bổ sung import domain/repository và cấu hình test database theo dự án. Mỗi test phải bắt đầu với fixture độc lập để kết quả của thử nghiệm trước không ảnh hưởng thử nghiệm sau.

### 12.1. Thêm test chứng minh rủi ro

Có thể thêm một test riêng để minh họa việc gọi save thông thường trên root-only object:

~~~java
@Test
void savingRootOnlyObjectCanRemoveAssociationsMissingFromObject() {
    seedCourse();

    Course partial = courseRepository
        .findRootOnlyByCode("GRAPH-101")
        .orElseThrow();

    assertThat(partial.getStudents()).isEmpty();

    partial.setTitle("Unsafe partial save");
    courseRepository.save(partial);

    Course reloaded = courseRepository
        .findByCode("GRAPH-101")
        .orElseThrow();

    assertThat(reloaded.getTitle()).isEqualTo("Unsafe partial save");
    assertThat(reloaded.getStudents()).isEmpty();
}
~~~

Test này là một thí nghiệm có chủ đích để thấy hậu quả của việc persist object graph thiếu association. Chỉ chạy trong test database cô lập.

## 13. Kiểm tra trực tiếp graph sau mỗi lần save

Không chỉ assertion trên object được trả về. Hãy truy vấn lại graph bằng repository hoặc Cypher để xác nhận dữ liệu thực sự còn trong database.

Đếm node Student liên kết với Course:

~~~cypher
MATCH (c:Course {code: $code})
OPTIONAL MATCH (c)-[r:ENROLLED]->(s:Student)
RETURN count(DISTINCT s) AS students,
       count(r) AS relationships
~~~

Liệt kê các relationship:

~~~cypher
MATCH (c:Course {code: $code})-[r:ENROLLED]->(s:Student)
RETURN c.code AS course,
       type(r) AS relationship,
       s.code AS student
ORDER BY student
~~~

Kiểm tra từng kịch bản:

| Kịch bản | Số relationship sau save |
| --- | ---: |
| Full load, xóa chủ động một Student | 1 |
| Partial root, save thông thường | Có thể còn 0 |
| Partial root, saveAs core projection | 2 |
| Full load, saveAs projection có students sau khi xóa một Student | 1 |

Kết quả cuối cùng phụ thuộc đúng fixture và projection. Nếu số liệu không như dự kiến, hãy kiểm tra query trả về, collection được hydrate và các thuộc tính nằm trong projection.

## 14. Những yếu tố làm graph chỉ được tải một phần

| Nguồn dữ liệu | Vì sao graph có thể thiếu | Cách xử lý |
| --- | --- | --- |
| Custom @Query chỉ RETURN root node | Record không mang các relationship cần map | Trả thêm relationship và related nodes hoặc dùng saveAs |
| Custom query trả nhiều record cùng root | Mỗi record chỉ mang một phần association | collect relationship và node thành một record cho mỗi root |
| Projection chỉ có một vài field | Các field/relationship khác không thuộc projection | Dùng projection làm ranh giới save |
| Query có LIMIT hoặc phân trang | Chỉ có một phần collection được đọc | Không persist collection đó như trạng thái đầy đủ |
| Mapping chỉ khai báo một hướng relationship | Object graph không đại diện toàn bộ các hướng trong database | Chọn aggregate root và hướng mapping có chủ đích |
| Model có nhiều relationship hai chiều | Truy vấn có thể mở rộng graph rất sâu | Hạn chế mapping hai chiều không cần thiết, dùng projection |
| Tự tạo object từ request DTO | Association có thể không được tải từ database | Đọc aggregate hoặc dùng saveAs/Cypher có phạm vi rõ |
| Một projection chỉ có scalar field | Không có dữ liệu để cập nhật association | Dùng projection có association nếu nghiệp vụ muốn thay đổi quan hệ |

Một graph “đầy đủ” luôn được xác định theo mục đích persist. Bạn không cần tải toàn bộ database. Bạn cần tải đủ những thuộc tính và relationship mà thao tác save sẽ quản lý.

## 15. Lưu ý về RelationshipProperties và quan hệ có thuộc tính

Trong hệ thống thực tế, relationship có thể chứa semester, score, role hoặc createdAt. Khi đó dùng @RelationshipProperties và @TargetNode để ánh xạ relationship thành class riêng.

Ví dụ:

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Enrollment {

    @RelationshipId
    private Long id;

    private String semester;
    private Integer score;

    @TargetNode
    private Student student;

    protected Enrollment() {
    }

    public Enrollment(
            Student student,
            String semester,
            Integer score) {
        this.student = student;
        this.semester = semester;
        this.score = score;
    }
}
~~~

Course có thể thay Set<Student> bằng Set<Enrollment>:

~~~java
@Relationship(type = "ENROLLED", direction = Relationship.Direction.OUTGOING)
private Set<Enrollment> enrollments = new LinkedHashSet<>();
~~~

Khi dùng relationship properties:

- Khai báo @RelationshipId để SDN nhận diện relationship nội bộ khi persist.
- @TargetNode xác định node ở đầu kia của relationship.
- Projection dùng để persist association cần bao gồm property quan hệ và target node tương ứng.
- Nếu chỉ đọc một phần Enrollment rồi ghi cả collection, các relationship không được tải vẫn có thể bị loại khỏi trạng thái ghi.
- Muốn sửa một thuộc tính trên một relationship, hãy tải đủ association cần quản lý hoặc viết Cypher cập nhật đúng relationship theo điều kiện định danh.

## 16. Transaction và đồng thời cập nhật

Các thử nghiệm nên chạy trong transaction để seed, save và assertion có ranh giới nhất quán. Khi một use case cập nhật node và relationship cùng lúc, đặt thao tác trong cùng transaction nếu chúng cần commit hoặc rollback cùng nhau.

Với ứng dụng có nhiều request cùng sửa một Course, cân nhắc optimistic locking bằng @Version. SDN hỗ trợ @Version trên field Long; giá trị được SDN tăng tự động và không nên tự chỉnh tay.

Khi xảy ra optimistic locking failure:

1. Đọc lại aggregate mới nhất từ database.
2. Xác định thay đổi nào của người dùng còn hợp lệ.
3. Áp dụng lại thay đổi trên graph mới.
4. Persist bằng save hoặc saveAs với projection phù hợp.
5. Không retry mù trên một object graph cũ có thể đã thiếu relationship.

Projection giúp giới hạn phạm vi ghi nhưng không thay thế transaction hoặc cơ chế xử lý concurrent update.

## 17. Quy trình quyết định trước khi gọi save

Trước mỗi thao tác persist, hãy tự trả lời:

1. Object này được lấy từ repository finder, custom Cypher, projection hay được tạo từ request?
2. Query đã trả tất cả relationship mà thao tác sẽ quản lý chưa?
3. Collection rỗng có phải trạng thái nghiệp vụ thật hay chỉ vì query không lấy association?
4. Tôi muốn cập nhật root properties, một relationship hay toàn bộ aggregate?
5. Nếu dùng saveAs, projection đã bao gồm đúng các field/association cần ghi chưa?
6. Nếu projection có association, collection có đầy đủ các quan hệ cần giữ lại không?
7. Tôi có thể dùng Cypher SET trực tiếp cho một thay đổi đơn giản không?
8. Test có xác nhận graph sau commit/rollback bằng một lần đọc mới không?

Quy tắc lựa chọn:

~~~text
Đã tải đủ dữ liệu cần persist?
    |
    +-- Có --> save(entity) nếu muốn đồng bộ graph đó
    |
    +-- Không
          |
          +-- Chỉ đổi scalar fields?
          |      +-- saveAs(entity, CoreProjection)
          |      +-- hoặc Cypher MATCH/SET
          |
          +-- Muốn đổi relationship?
                 +-- Tải đầy đủ association cần quản lý
                 +-- Dùng projection có association
                 +-- Hoặc cập nhật relationship bằng Cypher
~~~

## 18. Tiêu chí hoàn thành capstone

Bài thực nghiệm được xem là hoàn thành khi bạn chứng minh được:

- [ ] Tạo được một Course liên kết với ít nhất hai Student.
- [ ] Đọc Course bằng finder sinh tự động và xác nhận association được hydrate.
- [ ] Xóa có chủ đích một Student khỏi collection đầy đủ rồi save.
- [ ] Đọc lại và xác nhận chỉ relationship được chọn bị xóa.
- [ ] Viết custom query chỉ trả root node.
- [ ] Chứng minh object nhận được thiếu collection students.
- [ ] Chạy thử save thông thường trên partial graph trong database cô lập và quan sát rủi ro mất relationship.
- [ ] Dùng saveAs với projection chỉ gồm root properties.
- [ ] Xác nhận relationship không nằm trong projection vẫn còn.
- [ ] Tạo projection có relationship và kiểm tra association được cập nhật theo dữ liệu đã tải.
- [ ] Có Cypher kiểm tra số node và relationship sau mỗi kịch bản.
- [ ] Giải thích được vì sao một object graph đầy đủ theo mapping không đồng nghĩa với toàn bộ graph trong database.

## 19. Bài mở rộng

1. Thêm Enrollment có semester và score bằng @RelationshipProperties. Tạo projection chỉ ghi title của Course và chứng minh thuộc tính relationship không đổi.
2. Tạo projection có enrollments, thay score của một Enrollment và xác minh các relationship còn lại.
3. Viết custom query trả Course cùng collect(r) và collect(s), sau đó so sánh object mapping với query chỉ RETURN c.
4. Tạo truy vấn phân trang Student và giải thích vì sao không thể save collection trang đầu như toàn bộ students của Course.
5. Dùng saveAllAs để persist nhiều Course theo cùng projection và xác minh các relationship ngoài projection vẫn còn.
6. Viết Cypher cập nhật title và so sánh với saveAs về số dữ liệu phải đọc, ranh giới transaction và khả năng áp dụng callback.
7. Bật @Version, tạo hai transaction cùng đọc một Course rồi thử cập nhật để quan sát optimistic locking.

## 20. Câu hỏi tự kiểm tra

1. Thế nào là một object graph đầy đủ theo mapping của SDN?
2. Vì sao save thông thường có thể xóa relationship khi object chỉ được tải một phần?
3. Custom query chỉ RETURN node root có đủ dữ liệu để persist toàn bộ association không?
4. Vì sao custom query có relationship nên gom dữ liệu bằng collect?
5. saveAs khác save ở ranh giới persist như thế nào?
6. Projection không khai báo relationship có làm thay đổi relationship đó không?
7. Nếu projection khai báo một collection relationship nhưng object chỉ chứa một phần collection, điều gì có thể xảy ra?
8. Khi nào nên dùng Cypher MATCH/SET thay vì map entity rồi save?
9. Vì sao không nên coi collection rỗng là trạng thái “chưa tải”?
10. Làm thế nào kiểm chứng relationship còn nguyên sau một lần save?
11. Vì sao không nên ánh xạ hai chiều mọi relationship trong graph?
12. @Version hỗ trợ gì khi nhiều request cùng cập nhật aggregate?
13. Kết quả trả về từ saveAs có nên được dùng tiếp như một entity đầy đủ không?
14. Cần làm gì trước khi persist một entity được dựng từ request DTO?

## Tài liệu tham khảo

- [Spring Data Neo4j – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j – Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j – Neo4jOperations API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jOperations.html)
- [Spring Data Neo4j – Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j – Custom Queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j – FAQ: Mapping named paths](https://docs.spring.io/spring-data/neo4j/reference/faq.html)

## Kết luận

save(entity) phù hợp khi object graph chứa đầy đủ các thuộc tính và relationship mà ứng dụng muốn đồng bộ. Nếu object chỉ được hydrate một phần, collection thiếu dữ liệu có thể bị hiểu thành trạng thái quan hệ cần ghi và dẫn tới mất relationship.

Với thao tác chỉ cập nhật một phần graph, hãy dùng saveAs cùng projection để xác định rõ field và association được phép persist, hoặc dùng Cypher cập nhật trực tiếp khi phạm vi thay đổi nhỏ. Với custom query, trả về đủ node và relationship theo cấu trúc record mà SDN có thể map. Luôn đọc lại graph sau save để kiểm chứng node, relationship và property thực tế trong database.
