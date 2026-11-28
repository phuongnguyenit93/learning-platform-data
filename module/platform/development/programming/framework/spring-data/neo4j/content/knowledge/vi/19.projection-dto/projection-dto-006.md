# Thuộc tính quan hệ và các giới hạn kiểu dữ liệu trong projection

Trong Neo4j, dữ liệu nghiệp vụ không chỉ nằm trên node. Một relationship cũng có thể mang các thuộc tính riêng như vai trò, trạng thái, điểm số, ngày tham gia hoặc số lượng. Khi dùng Spring Data Neo4j, các thuộc tính này thường được ánh xạ bằng `@RelationshipProperties` và `@TargetNode`. Nếu API chỉ cần một phần dữ liệu, projection hoặc DTO có thể trả về đúng phần cần thiết mà không phải đưa toàn bộ entity graph ra ngoài.

Tuy nhiên, projection có quy tắc ánh xạ riêng. Interface projection phải trỏ đến property có trong mô hình domain; DTO projection có thể nhận thêm giá trị từ custom query nhưng alias và kiểu dữ liệu phải tương thích. Một số cấu trúc như `Map` không được hỗ trợ trong cơ chế bổ sung thuộc tính DTO của Spring Data Neo4j. Hiểu rõ các giới hạn này giúp chọn đúng hình dạng kết quả và tránh lỗi khi ánh xạ thuộc tính relationship.

## 1. Mô hình hóa thuộc tính trên relationship

Giả sử hệ thống đào tạo quản lý sinh viên và khóa học. Một sinh viên đăng ký nhiều khóa học; mỗi lần đăng ký có trạng thái, điểm và ngày đăng ký riêng:

```text
(Student)-[ENROLLED_IN {
    status: 'COMPLETED',
    score: 8.5,
    enrolledOn: date('2026-09-01')
}]->(Course)
```

`status`, `score` và `enrolledOn` mô tả mối quan hệ đăng ký giữa một sinh viên và một khóa học. Chúng không phải thuộc tính chung của `Student` hoặc `Course`: cùng một sinh viên có thể đạt điểm khác nhau ở từng khóa học.

Spring Data Neo4j dùng `@RelationshipProperties` để ánh xạ lớp đại diện cho relationship và `@TargetNode` để xác định node đích:

```java
@RelationshipProperties
public class Enrollment {

    @TargetNode
    private Course course;

    private String status;
    private Double score;
    private LocalDate enrolledOn;
}
```

Entity nguồn chứa collection các đối tượng relationship:

```java
@Node("Student")
public class Student {

    @Id
    private String studentId;

    private String name;

    @Relationship(type = "ENROLLED_IN", direction = Relationship.Direction.OUTGOING)
    private List<Enrollment> enrollments = new ArrayList<>();
}
```

`Course` là node entity riêng:

```java
@Node("Course")
public class Course {

    @Id
    private String courseCode;

    private String title;
}
```

Khi đọc `Student`, collection `enrollments` chứa các đối tượng `Enrollment`. Mỗi đối tượng vừa có property của relationship (`status`, `score`, `enrolledOn`), vừa tham chiếu node đích qua `course`.

## 2. Interface projection nhiều cấp cho relationship properties

Interface projection là proxy dựa trên entity domain. Các accessor thông thường phải tương ứng với property trong mô hình domain. Với relationship properties, Spring Data Neo4j xem lớp được đánh dấu `@RelationshipProperties` như một entity ở cấp trung gian của projection nhiều tầng.

Có thể định nghĩa projection theo đúng cấu trúc `Student → Enrollment → Course`:

```java
public interface StudentEnrollmentView {

    String getStudentId();
    String getName();
    List<EnrollmentView> getEnrollments();

    interface EnrollmentView {
        String getStatus();
        Double getScore();
        LocalDate getEnrolledOn();
        CourseView getCourse();
    }

    interface CourseView {
        String getCourseCode();
        String getTitle();
    }
}
```

Repository có thể trả về projection thay cho entity đầy đủ:

```java
public interface StudentRepository extends Neo4jRepository<Student, String> {

    Optional<StudentEnrollmentView> findProjectedByStudentId(String studentId);
}
```

Đường đi của projection khớp với mô hình domain:

| Accessor projection | Property domain | Nguồn dữ liệu |
|---|---|---|
| `getStudentId()` | `Student.studentId` | Property trên node `Student` |
| `getEnrollments()` | `Student.enrollments` | Collection relationship `ENROLLED_IN` |
| `getStatus()` | `Enrollment.status` | Property trên relationship |
| `getScore()` | `Enrollment.score` | Property trên relationship |
| `getCourse()` | `Enrollment.course` | Node đích của relationship |
| `getTitle()` | `Course.title` | Property trên node `Course` |

Projection nhiều cấp giúp giới hạn các trường cần đọc ở từng tầng. Nếu màn hình chỉ cần trạng thái, điểm và tiêu đề khóa học, không cần mở rộng thêm các quan hệ khác của `Course`.

### Lưu ý về ranh giới của projection

Tên accessor phải đi theo property của lớp tương ứng. Ví dụ `EnrollmentView.getScore()` ánh xạ `Enrollment.score`, không phải `Student.score`. Nếu khai báo một getter ở sai cấp, framework không thể tự suy luận rằng getter đó thuộc relationship bên dưới.

Các projection lồng nhau cũng bị giới hạn theo entity mà chúng đại diện. `RelationshipProperties` là một phần của chuỗi entity đó, nên cần có projection trung gian cho relationship nếu muốn truy cập các property trên cạnh và node đích.

## 3. DTO projection cho kết quả phẳng từ custom Cypher

Khi API cần một hàng dữ liệu phẳng, chẳng hạn một dòng cho mỗi lần đăng ký, DTO thường dễ sử dụng hơn projection lồng nhau.

Ví dụ DTO bằng Java record:

```java
public record EnrollmentRow(
    String studentId,
    String studentName,
    String courseCode,
    String courseTitle,
    String enrollmentStatus,
    Double score,
    LocalDate enrolledOn
) {}
```

Custom query trả các property của node và relationship thành các cột có alias tương ứng:

```java
public interface StudentRepository extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
        WHERE s.studentId = $studentId
        RETURN s.studentId AS studentId,
               s.name AS studentName,
               c.courseCode AS courseCode,
               c.title AS courseTitle,
               e.status AS enrollmentStatus,
               e.score AS score,
               e.enrolledOn AS enrolledOn
        ORDER BY c.courseCode
        """)
    List<EnrollmentRow> findEnrollmentRows(
        @Param("studentId") String studentId
    );
}
```

Trong truy vấn, `e` là biến relationship `ENROLLED_IN`. Vì vậy `e.status`, `e.score` và `e.enrolledOn` lấy dữ liệu trên cạnh. Các alias như `enrollmentStatus` và `score` phải khớp chính xác với tên component của record. Mỗi dòng kết quả được chuyển thành một `EnrollmentRow`.

DTO phù hợp khi dữ liệu trả về là một hình dạng riêng của API hoặc báo cáo. DTO không cần giống hệt entity domain và custom query có thể bổ sung các giá trị được tính trong Cypher.

## 4. DTO có thể nhận thêm thuộc tính từ kết quả query

Khác với interface projection thông thường, DTO projection của Spring Data Neo4j linh hoạt hơn khi dùng với custom query. Framework trước hết ánh xạ các property của domain type. Với thuộc tính bổ sung trong DTO, SDN tìm giá trị tương ứng trong record kết quả.

Ví dụ cần thêm tổng số khóa học và điểm trung bình của sinh viên:

```java
public record StudentEnrollmentStats(
    String studentId,
    Long enrollmentCount,
    Double averageScore
) {}
```

```java
@Query("""
    MATCH (s:Student {studentId: $studentId})
    OPTIONAL MATCH (s)-[e:ENROLLED_IN]->(:Course)
    RETURN s.studentId AS studentId,
           count(e) AS enrollmentCount,
           avg(e.score) AS averageScore
    """)
Optional<StudentEnrollmentStats> findEnrollmentStats(
    @Param("studentId") String studentId
);
```

`enrollmentCount` và `averageScore` không phải property được lưu trực tiếp trên node `Student`; chúng là giá trị tổng hợp của custom query. Alias trong record kết quả phải khớp tên component `enrollmentCount` và `averageScore`.

Khi sinh viên tồn tại nhưng chưa có đăng ký, `OPTIONAL MATCH` giữ lại dòng của sinh viên: `count(e)` là `0`, còn `avg(e.score)` là `null`. Khi sinh viên không tồn tại, không có dòng kết quả và `Optional` là empty. Vì vậy, `Long` và `Double` trong DTO là kiểu wrapper phù hợp với trường hợp có thể null; không nên dùng primitive `double` nếu cột có thể không có giá trị.

## 5. Giới hạn kiểu dữ liệu trong DTO projection

Với các thuộc tính bổ sung mà custom query trả về cho DTO, Spring Data Neo4j yêu cầu kiểu dữ liệu phải thuộc nhóm có thể ánh xạ:

- **Simple types:** các kiểu đơn giản được SDN nhận diện trong `Neo4jSimpleTypes`, có thể chuyển đổi từ giá trị Neo4j.
- **Persistent entities đã biết:** các kiểu entity được Spring Data Neo4j nhận diện trong metadata mapping.
- **Collection của các kiểu được hỗ trợ:** có thể dùng collection chứa simple type hoặc persistent entity phù hợp.
- **Map:** không được hỗ trợ như một thuộc tính bổ sung của DTO theo cơ chế projection này.

Tên thuộc tính bổ sung phải khớp chính xác với tên cột trong record. Nếu DTO khai báo `averageScore`, query phải trả `AS averageScore`; alias `avgScore` không tự động được coi là cùng tên.

| Hình dạng kết quả | Hướng ánh xạ phù hợp |
|---|---|
| `String`, `Long`, `Double`, kiểu thời gian được hỗ trợ | Component scalar trong DTO hoặc getter projection tương ứng |
| Node entity đã biết | Thuộc tính DTO có kiểu entity hoặc nested projection theo mô hình |
| Collection scalar/entity được hỗ trợ | Collection có generic type rõ ràng |
| Map tùy ý như `Map<String, Object>` | Không dùng làm thuộc tính bổ sung DTO projection; cân nhắc `Neo4jClient` và ánh xạ thủ công |
| Cấu trúc lồng nhiều cấp | Interface projection nhiều cấp hoặc DTO có cấu trúc persistent entity được hỗ trợ |

Không nên khai báo `Object` hoặc `Map<String, Object>` với kỳ vọng SDN tự suy luận một cấu trúc động bất kỳ. Nếu kết quả có nhiều hình dạng hoặc cần giữ các key tùy ý, hãy đọc record bằng `Neo4jClient` và tự chuyển đổi theo hợp đồng API.

## 6. Giới hạn của interface projection

Interface projection thông thường là proxy trên entity domain. Các getter phải phân giải được thành property của entity tương ứng. Ví dụ, nếu `Student` không có property `averageScore`, việc thêm `Double getAverageScore()` vào interface không tự khiến SDN tính trung bình điểm đăng ký.

Với dữ liệu tổng hợp hoặc cột mới được tạo trong custom Cypher, dùng DTO projection hoặc `Neo4jClient` sẽ phù hợp hơn. Cần phân biệt:

| Nhu cầu | Lựa chọn |
|---|---|
| Đọc một phần property đã có trên node | Interface projection |
| Đọc relationship properties đã có trong entity mapping | Interface projection lồng qua lớp `@RelationshipProperties` |
| Đọc một phần node đích liên kết | Nested interface projection |
| Thêm cột tổng hợp không có trong entity | DTO projection với `@Query` |
| Ánh xạ map hoặc kiểu kết quả tùy chỉnh | `Neo4jClient` với mapper thủ công |

## 7. Xử lý null và kiểu Java tương ứng

Các property trên relationship có thể không tồn tại. Ví dụ, đăng ký mới có thể chưa có điểm; do đó `e.score` là null. Projection cần phản ánh khả năng này:

```java
public interface EnrollmentView {
    String getStatus();
    Double getScore();
    LocalDate getEnrolledOn();
}
```

`Double` và `LocalDate` là kiểu tham chiếu, có thể biểu diễn null. Nếu dùng `double`, giá trị null không thể được biểu diễn tự nhiên và có thể dẫn đến lỗi chuyển đổi hoặc giá trị mặc định không đúng ý nghĩa nghiệp vụ.

Khi dùng `Neo4jClient` để ánh xạ thủ công, kiểm tra null trước khi gọi hàm chuyển đổi:

```java
Double score = record.get("score").isNull()
    ? null
    : record.get("score").asDouble();
```

Với kết quả tổng hợp:

- `count(e)` trả số đếm dạng số nguyên 64-bit, thường ánh xạ vào `Long`.
- `avg(e.score)` trả giá trị trung bình dạng số thực và có thể null khi không có giá trị hợp lệ.
- `collect(e.status)` trả collection các giá trị khác null; cần khai báo kiểu collection và kiểu phần tử tương thích.

Không thay null bằng `0` nếu nghiệp vụ cần phân biệt “chưa có điểm” với “điểm bằng 0”. Nếu muốn giá trị mặc định, hãy thể hiện rõ trong Cypher bằng `coalesce()` hoặc trong service theo quy tắc nghiệp vụ.

## 8. Alias là hợp đồng giữa Cypher và DTO

Với DTO projection, alias là một phần của hợp đồng ánh xạ. Ví dụ:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
RETURN s.studentId AS studentId,
       e.status AS enrollmentStatus,
       e.score AS score
```

phải tương ứng với DTO:

```java
public record EnrollmentSummary(
    String studentId,
    String enrollmentStatus,
    Double score
) {}
```

Nếu đổi alias `enrollmentStatus` thành `status` mà không đổi DTO, framework không có cơ sở để tự đoán rằng hai tên này đồng nghĩa. Tương tự, kiểu dữ liệu trả về cần phù hợp với kiểu component. Hãy kiểm tra alias và kiểu của từng cột khi gặp lỗi mapping.

## 9. Projection là hình dạng đọc, không mặc nhiên là entity đầy đủ

Projection giúp giảm lượng dữ liệu truyền từ Neo4j và giới hạn phần object graph được dựng. Nhưng projection không nhất thiết chứa toàn bộ dữ liệu của aggregate. Nếu dùng projection như blueprint để ghi qua `Neo4jTemplate`, chỉ các property và relationship được khai báo trong projection mới được cập nhật.

Ví dụ, projection chỉ tải hai trong số năm relationship của một node. Nếu sau đó dùng chính projection đó để lưu như trạng thái đầy đủ, những relationship không có trong projection có thể bị loại khỏi trạng thái được ghi. Tài liệu Spring Data Neo4j khuyến cáo cần tải ít nhất toàn bộ dữ liệu sẽ được lưu lại để tránh xóa dữ liệu, đặc biệt là relationship.

Vì vậy:

- Dùng projection đọc cho API và báo cáo khi chỉ cần một phần dữ liệu.
- Không chuyển interface projection thành entity có thể ghi nếu chưa bổ sung đủ dữ liệu cần bảo toàn.
- Khi muốn lưu theo projection blueprint, xác định rõ các field và relationship được phép cập nhật.
- Với thao tác cập nhật nghiệp vụ, cân nhắc đọc aggregate đầy đủ theo đúng ranh giới cần ghi rồi mới lưu.

## 10. Dùng Neo4jClient khi cần kiểu kết quả linh hoạt

Khi custom query trả về cấu trúc không phù hợp với giới hạn DTO projection, `Neo4jClient` cho phép đọc từng record và ánh xạ thủ công. Ví dụ, cần trả về một map kết quả để xây dựng báo cáo động:

```java
var rows = neo4jClient.query("""
    MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
    WHERE s.studentId = $studentId
    RETURN s.studentId AS studentId,
           c.courseCode AS courseCode,
           e.status AS status,
           e.score AS score
    ORDER BY c.courseCode
    """)
    .bind(studentId).to("studentId")
    .fetch()
    .all();
```

Ở đây, kết quả được đọc thành các map theo alias cột thay vì yêu cầu DTO projection tự ánh xạ một thuộc tính Map bổ sung. Với ứng dụng có schema response cố định, DTO vẫn dễ kiểm soát kiểu hơn; map chỉ nên dùng khi cấu trúc thực sự cần linh hoạt.

Nếu cần xử lý chuyển đổi riêng, có thể dùng `fetchAs(...).mappedBy(...)` để đọc từng `Record`, kiểm tra null, chuyển kiểu và tạo DTO theo logic của ứng dụng.

Với DTO class thông thường, hãy cung cấp một constructor mà Spring Data có thể dùng để xác định input properties. Nếu class có nhiều constructor, đánh dấu constructor mong muốn bằng `@PersistenceCreator`. Java record thường thuận tiện vì có canonical constructor tương ứng trực tiếp với các record component.

## 11. Kiểm thử projection có relationship properties

Integration test nên xác minh cả dữ liệu trên node, relationship và node đích. Một kịch bản phù hợp:

1. Tạo một `Student` và hai `Course`.
2. Tạo hai relationship `ENROLLED_IN` với trạng thái, điểm và ngày đăng ký khác nhau.
3. Đọc bằng interface projection và xác nhận collection `enrollments` có đủ hai phần tử.
4. Xác nhận mỗi phần tử chứa đúng `status`, `score`, `enrolledOn` và projection `course`.
5. Đọc bằng DTO custom query và xác nhận alias, thứ tự dòng, kiểu số và kiểu ngày.
6. Tạo một enrollment chưa có điểm để xác nhận `score` là null mà không gây lỗi.
7. Kiểm tra trường hợp student không tồn tại và trường hợp student tồn tại nhưng không có enrollment.
8. Kiểm tra DTO projection với alias sai hoặc kiểu không tương thích để phát hiện lỗi mapping trong quá trình phát triển.

Test nên chạy trên Neo4j cô lập. Không chỉ kiểm tra số lượng phần tử; hãy xác nhận từng property thuộc đúng relationship, tránh nhầm `score` của enrollment này với enrollment khác.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Projection không đọc được điểm trên relationship | Getter được khai báo ở cấp `Student` thay vì projection trung gian `Enrollment` | Tạo nested projection cho lớp `@RelationshipProperties`. |
| Nested projection không đọc được node đích | Tên accessor không khớp property `@TargetNode` | Khai báo getter theo property node đích, ví dụ `getCourse()`. |
| DTO có trường mới luôn null | Custom query thiếu alias hoặc alias không khớp chính xác tên DTO | Đặt `AS` trùng tên component/property DTO. |
| DTO projection báo kiểu không hỗ trợ | Thuộc tính bổ sung dùng Map hoặc kiểu không thuộc nhóm được SDN hỗ trợ | Dùng simple type, persistent entity/collection phù hợp hoặc tự map bằng `Neo4jClient`. |
| Lỗi khi ánh xạ điểm null | Dùng primitive `double` hoặc gọi chuyển đổi mà không kiểm tra null | Dùng `Double` và xử lý null rõ ràng. |
| Kết quả collection thiếu relationship | Query không trả đủ dữ liệu cần cho mapping hoặc pattern chỉ match một phần | Kiểm tra Cypher, biến relationship và dữ liệu được trả về. |
| Lưu projection làm mất relationship | Dùng projection một phần như blueprint ghi toàn bộ aggregate | Tải đủ dữ liệu cần bảo toàn hoặc giới hạn rõ phần được phép ghi. |

## 13. Quy trình chọn projection

1. Xác định kết quả cần biểu diễn theo cấu trúc domain hay theo hàng báo cáo phẳng.
2. Nếu cần đọc entity graph, ánh xạ relationship bằng `@RelationshipProperties` và tạo nested interface projection theo từng cấp.
3. Nếu cần cột tính toán hoặc alias mới, dùng DTO projection với custom `@Query`.
4. Kiểm tra mỗi alias có khớp chính xác với getter hoặc tên component DTO.
5. Chọn kiểu Java tương ứng với kiểu Neo4j; dùng wrapper cho giá trị có thể null.
6. Tránh Map trong thuộc tính bổ sung của DTO projection; dùng `Neo4jClient` nếu cần kết quả dạng map.
7. Kiểm tra số dòng, collection rỗng, null, relationship lặp và dữ liệu không tồn tại.
8. Nếu projection được dùng để ghi, bảo đảm đã tải đủ property và relationship cần giữ lại.

## 14. Ghi nhớ

Với Spring Data Neo4j, thuộc tính trên relationship được ánh xạ thành lớp `@RelationshipProperties`. Interface projection nhiều cấp có thể đi qua entity nguồn, lớp relationship properties và node đích bằng các accessor khớp với property của từng cấp.

DTO projection phù hợp với kết quả phẳng hoặc giá trị tổng hợp từ custom Cypher. Thuộc tính bổ sung trong DTO phải khớp chính xác alias và dùng simple type, persistent entity hoặc collection được hỗ trợ; Map không được hỗ trợ trong cơ chế này. Khi cần kết quả linh hoạt, hãy dùng `Neo4jClient` để tự ánh xạ record. Luôn kiểm tra null, kiểu dữ liệu và số dòng, đồng thời nhớ rằng projection đọc một phần không tự động là dữ liệu đầy đủ để ghi lại aggregate.

## Tài liệu tham khảo

- [Spring Data Neo4j – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Commons – Projections](https://docs.spring.io/spring-data/neo4j/reference/repositories/projections.html)
