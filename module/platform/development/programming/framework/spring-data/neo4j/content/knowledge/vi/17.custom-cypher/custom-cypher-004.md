# Truy vấn qua nhiều relationship và điều kiện trên thuộc tính quan hệ

Một truy vấn Cypher thường cần đi qua nhiều relationship để tìm đúng phần dữ liệu nghiệp vụ. Ví dụ, muốn tìm sinh viên đã đăng ký một khóa học được mở trong học kỳ cụ thể, ứng dụng cần đi từ `Student` qua `ENROLLED_IN` đến `Course`, rồi qua `OFFERED_BY` đến `Department`. Điều kiện truy vấn có thể nằm trên node như mã khoa, đồng thời nằm trên relationship như trạng thái đăng ký, điểm số, học kỳ hoặc cơ sở đào tạo.

Khi viết custom Cypher trong Spring Data Neo4j, cần đặt biến cho từng relationship, lọc đúng thuộc tính trên từng cạnh và trả về cấu trúc kết quả phù hợp. Bài học này trình bày cách mô hình hóa, viết truy vấn nhiều bước, truyền tham số và ánh xạ kết quả thành projection.

## 1. Mô hình đồ thị có thuộc tính trên relationship

Giả sử hệ thống đào tạo có ba loại node:

- `Student`: sinh viên, có `studentId` và `name`.
- `Course`: khóa học, có `courseCode` và `title`.
- `Department`: khoa phụ trách, có `departmentCode` và `name`.

Hai loại relationship nối các node:

```text
(Student)-[ENROLLED_IN]->(Course)-[OFFERED_BY]->(Department)
```

Mỗi relationship mang dữ liệu riêng:

| Relationship | Thuộc tính | Ý nghĩa |
|---|---|---|
| `ENROLLED_IN` | `status` | Trạng thái đăng ký của sinh viên trong khóa học |
| `ENROLLED_IN` | `score` | Điểm của sinh viên trong khóa học |
| `ENROLLED_IN` | `enrolledOn` | Ngày đăng ký |
| `OFFERED_BY` | `term` | Học kỳ mở khóa học |
| `OFFERED_BY` | `campus` | Cơ sở tổ chức khóa học |

Việc đặt `status` và `score` trên `ENROLLED_IN` có ý nghĩa vì các giá trị này thuộc về mối quan hệ giữa một sinh viên và một khóa học. Một sinh viên có thể có trạng thái hoặc điểm khác nhau ở từng khóa học. Tương tự, `term` và `campus` mô tả lần mở khóa học của khoa, không nhất thiết là thuộc tính cố định của node `Course`.

## 2. Ánh xạ relationship properties trong Spring Data Neo4j

Spring Data Neo4j dùng `@RelationshipProperties` để ánh xạ các thuộc tính nằm trên relationship và `@TargetNode` để chỉ node đích của relationship đó.

Ví dụ lớp `Enrollment`:

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

Entity `Student` chứa collection các enrollment:

```java
@Node("Student")
public class Student {
    @Id
    private String studentId;

    private String name;

    @Relationship(type = "ENROLLED_IN", direction = Relationship.Direction.OUTGOING)
    private Set<Enrollment> enrollments = new HashSet<>();
}
```

Tương tự, mô hình lần mở khóa học:

```java
@RelationshipProperties
public class Offering {
    @TargetNode
    private Department department;

    private String term;
    private String campus;
}

@Node("Course")
public class Course {
    @Id
    private String courseCode;

    private String title;

    @Relationship(type = "OFFERED_BY", direction = Relationship.Direction.OUTGOING)
    private Set<Offering> offerings = new HashSet<>();
}
```

`Department` là node entity có định danh `departmentCode` và thuộc tính `name`. Các đoạn mã trên tập trung vào cấu trúc mapping; ứng dụng thực tế cần bổ sung constructor, getter, validation và các phương thức miền phù hợp.

Khi relationship có property, collection chứa đối tượng `Enrollment` hoặc `Offering`, thay vì chỉ chứa node đích. Nhờ đó, ứng dụng có thể đọc được cả node liên quan lẫn dữ liệu gắn trên cạnh.

## 3. MATCH qua nhiều relationship

Để tìm sinh viên, khóa học và khoa, viết pattern nối liên tiếp các node và relationship:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[o:OFFERED_BY]->(d:Department)
RETURN s, e, c, o, d
```

Trong pattern:

- `s` là node `Student`.
- `e` là relationship `ENROLLED_IN` nối sinh viên đến khóa học.
- `c` là node `Course`.
- `o` là relationship `OFFERED_BY` nối khóa học đến khoa.
- `d` là node `Department`.

Mỗi biến relationship (`e`, `o`) cho phép truy cập các property của chính relationship đó. Nếu bỏ biến, ví dụ `-[:ENROLLED_IN]->`, truy vấn vẫn đi qua cạnh nhưng không thể tham chiếu trực tiếp đến property của cạnh trong các biểu thức tiếp theo.

Hướng mũi tên phải khớp với mô hình đồ thị. Nếu dữ liệu được tạo theo hướng ngược lại, pattern trên sẽ không tìm thấy đường đi. Có thể đảo chiều pattern khi cần:

```cypher
MATCH (d:Department)<-[o:OFFERED_BY]-(c:Course)<-[e:ENROLLED_IN]-(s:Student)
RETURN s, e, c, o, d
```

Hai pattern trên biểu diễn cùng hướng relationship trong đồ thị, chỉ khác cách viết từ trái sang phải.

## 4. Đặt điều kiện trên thuộc tính của từng relationship

Sau khi đặt biến cho relationship, có thể dùng `WHERE` để lọc property của từng cạnh. Ví dụ, tìm sinh viên có đăng ký đang hoạt động, điểm từ ngưỡng yêu cầu, và khóa học được mở trong học kỳ cụ thể tại một khoa:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[o:OFFERED_BY]->(d:Department)
WHERE e.status = $status
  AND e.score >= $minScore
  AND o.term = $term
  AND d.departmentCode = $departmentCode
RETURN s, e, c, o, d
```

Điều kiện được áp dụng như sau:

1. `e.status = $status` lọc trạng thái đăng ký trên relationship `ENROLLED_IN`.
2. `e.score >= $minScore` lọc điểm trên chính relationship đăng ký đó.
3. `o.term = $term` lọc lần mở khóa học trên relationship `OFFERED_BY`.
4. `d.departmentCode = $departmentCode` lọc node khoa.

Điều quan trọng là `e.score` và `o.term` thuộc hai relationship khác nhau. Không nên nhầm chúng thành property của `Student`, `Course` hoặc `Department`.

Có thể kết hợp điều kiện bằng `OR`, nhưng nên dùng dấu ngoặc để giữ đúng ý nghĩa:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[o:OFFERED_BY]->(d:Department)
WHERE e.status = $status
  AND (e.score >= $minScore OR e.status = 'EXEMPT')
  AND o.term = $term
RETURN s, c, d, e.score AS score, o.campus AS campus
```

Ở đây, trạng thái đăng ký phải khớp `$status`, đồng thời điểm đạt ngưỡng hoặc trạng thái được miễn điểm. Các điều kiện học kỳ vẫn áp dụng cho relationship `OFFERED_BY`.

## 5. Viết custom query trong repository

Trong Spring Data Neo4j, `@Query` cho phép khai báo Cypher trực tiếp trên repository. Khi kết quả là các trường tùy chỉnh từ nhiều node và relationship, interface projection giúp trả đúng dữ liệu cần dùng mà không phải dựng toàn bộ entity graph.

Định nghĩa projection:

```java
public interface EnrollmentPathView {
    String getStudentId();
    String getStudentName();
    String getCourseCode();
    String getCourseTitle();
    String getEnrollmentStatus();
    Double getScore();
    String getTerm();
    String getCampus();
    String getDepartmentCode();
    String getDepartmentName();
}
```

Repository sử dụng Cypher và tham số có tên:

```java
public interface StudentRepository extends Neo4jRepository<Student, String> {

    @Query("""
        MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[o:OFFERED_BY]->(d:Department)
        WHERE e.status = $status
          AND e.score >= $minScore
          AND o.term = $term
          AND d.departmentCode = $departmentCode
        RETURN s.studentId AS studentId,
               s.name AS studentName,
               c.courseCode AS courseCode,
               c.title AS courseTitle,
               e.status AS enrollmentStatus,
               e.score AS score,
               o.term AS term,
               o.campus AS campus,
               d.departmentCode AS departmentCode,
               d.name AS departmentName
        ORDER BY e.score DESC, s.studentId ASC
        """)
    List<EnrollmentPathView> searchEnrollmentPaths(
        @Param("status") String status,
        @Param("minScore") Double minScore,
        @Param("term") String term,
        @Param("departmentCode") String departmentCode
    );
}
```

Alias trong `RETURN` cần tương ứng với tên property mà projection cung cấp. Ví dụ `s.studentId AS studentId` ánh xạ tới `getStudentId()`, còn `e.score AS score` ánh xạ tới `getScore()`.

Mỗi dòng kết quả đại diện cho một đường đi phù hợp `Student → Course → Department`. Nếu một sinh viên đăng ký nhiều khóa học trong cùng khoa và học kỳ, sinh viên đó có thể xuất hiện ở nhiều dòng. Đây là kết quả đúng nếu báo cáo cần từng enrollment; nếu cần một dòng cho mỗi sinh viên, phải dùng aggregation hoặc `DISTINCT` theo đúng tập trường mong muốn.

## 6. Truyền tham số an toàn và đúng kiểu

Các giá trị đầu vào nên được truyền bằng tham số có tên như `$status`, `$minScore`, `$term` và `$departmentCode`. Trong repository, dùng `@Param` để liên kết tham số Java với placeholder Cypher.

Không nối chuỗi đầu vào vào câu truy vấn:

```java
// Không nên: dữ liệu đầu vào bị ghép trực tiếp vào Cypher
String cypher = "MATCH (s:Student) WHERE s.name = '" + studentName + "' RETURN s";
```

Hãy dùng tham số:

```cypher
MATCH (s:Student)
WHERE s.name = $studentName
RETURN s
```

Tham số bảo vệ giá trị đầu vào khỏi bị diễn giải như một phần cú pháp Cypher và giúp tái sử dụng câu truy vấn. Kiểu Java cũng nên tương thích với kiểu property: `Double` cho điểm dạng số thực, `LocalDate` cho ngày, `String` cho mã hoặc trạng thái.

Tham số thông thường thay thế giá trị trong biểu thức, không thay thế tùy ý tên label, relationship type hoặc tên property. Nếu cần thay đổi cấu trúc pattern, hãy thiết kế truy vấn có kiểm soát và chỉ chọn từ những cấu trúc đã được cho phép.

## 7. Điều kiện trên nhiều relationship trong cùng một đường đi

Khi truy vấn đi qua nhiều cạnh, mỗi relationship có thể có điều kiện độc lập. Ví dụ, cần chọn sinh viên đăng ký sau một ngày nhất định và khóa học được mở tại cơ sở chính:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[o:OFFERED_BY]->(d:Department)
WHERE e.enrolledOn >= date($fromDate)
  AND e.status IN ['ACTIVE', 'COMPLETED']
  AND o.campus = $campus
  AND d.departmentCode = $departmentCode
RETURN s.name AS studentName,
       c.title AS courseTitle,
       e.enrolledOn AS enrolledOn,
       e.status AS enrollmentStatus,
       o.campus AS campus
ORDER BY e.enrolledOn DESC
```

`e.enrolledOn` và `e.status` cùng thuộc relationship đăng ký. `o.campus` thuộc relationship mở khóa học. `d.departmentCode` thuộc node khoa. Phân biệt rõ chủ sở hữu của từng property là bước quan trọng để tránh lọc nhầm dữ liệu.

Nếu cần điều kiện `OR` giữa các thuộc tính trên hai cạnh, hãy nhóm tường minh:

```cypher
WHERE (e.score >= $minScore AND e.status = 'ACTIVE')
   OR (o.campus = $preferredCampus AND e.status = 'EXEMPT')
```

Không bỏ dấu ngoặc khi hai nhánh có nhiều điều kiện. Nếu không, độ ưu tiên toán tử có thể làm truy vấn trả về nhiều đường đi hơn dự kiến.

## 8. OPTIONAL MATCH khi relationship có thể không tồn tại

`MATCH` yêu cầu toàn bộ pattern phải tồn tại. Nếu một khóa học chưa có relationship `OFFERED_BY`, truy vấn `MATCH` qua cả hai relationship sẽ loại khóa học đó khỏi kết quả.

Nếu muốn vẫn giữ sinh viên và khóa học dù chưa có thông tin mở khóa, dùng `OPTIONAL MATCH`:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)
WHERE e.status = $status
OPTIONAL MATCH (c)-[o:OFFERED_BY]->(d:Department)
WHERE o.term = $term
RETURN s.studentId AS studentId,
       c.courseCode AS courseCode,
       o.term AS term,
       d.departmentCode AS departmentCode
```

Điều kiện `WHERE` ngay sau `OPTIONAL MATCH` thuộc phần pattern tùy chọn. Nếu không có relationship phù hợp với học kỳ, hàng kết quả vẫn có thể được giữ lại, trong đó `o` và `d` là `null`.

Ngược lại, nếu đặt điều kiện `o.term = $term` ở một `WHERE` độc lập sau khi đã hoàn tất phần optional, những dòng có `o = null` sẽ bị loại. Khi muốn giữ bản ghi bên trái, cần đặt điều kiện đúng phạm vi của `OPTIONAL MATCH` hoặc dùng biểu thức điều kiện phù hợp.

## 9. Tổng hợp kết quả qua nhiều relationship

Nếu báo cáo cần số sinh viên và điểm trung bình theo khoa, có thể dùng aggregation sau khi lọc đường đi:

```cypher
MATCH (s:Student)-[e:ENROLLED_IN]->(c:Course)-[o:OFFERED_BY]->(d:Department)
WHERE e.status = $status
  AND o.term = $term
WITH d, count(DISTINCT s) AS studentCount,
     count(DISTINCT c) AS courseCount,
     avg(e.score) AS averageScore
RETURN d.departmentCode AS departmentCode,
       d.name AS departmentName,
       studentCount,
       courseCount,
       averageScore
ORDER BY averageScore DESC
```

Các biểu thức tổng hợp được tính trên các đường đi còn lại sau `WHERE`. `count(DISTINCT s)` đếm sinh viên khác nhau, `count(DISTINCT c)` đếm khóa học khác nhau, còn `avg(e.score)` tính trung bình điểm của các enrollment trong nhóm.

Nếu một sinh viên có nhiều enrollment hợp lệ trong cùng nhóm, `studentCount` vẫn chỉ đếm sinh viên một lần nhưng `averageScore` tính trên từng relationship enrollment. Hãy xác định rõ mẫu số và đơn vị của báo cáo trước khi viết aggregation. Nếu cần trung bình theo sinh viên, trước tiên phải gom điểm ở cấp sinh viên rồi mới tính trung bình cấp khoa.

## 10. Tối ưu truy vấn nhiều relationship

Truy vấn nhiều bước có thể tạo nhiều đường đi trung gian. Để giữ chi phí ở mức hợp lý:

- **Bắt đầu từ node có điều kiện chọn lọc:** lọc theo mã khoa, mã sinh viên hoặc mã khóa học phù hợp để giảm số node đầu vào.
- **Đặt label và relationship type rõ ràng:** tránh pattern quá tổng quát như `(a)-[r]->(b)` nếu nghiệp vụ đã biết loại cạnh.
- **Dùng tham số và kiểu dữ liệu nhất quán:** tránh ép kiểu hoặc chuyển đổi chuỗi trên mỗi relationship khi truy vấn thường xuyên.
- **Chỉ trả về trường cần thiết:** dùng projection cho kết quả báo cáo thay vì trả toàn bộ entity graph.
- **Kiểm soát cardinality:** nhiều nhánh relationship trong cùng pattern có thể nhân số dòng. Dùng `WITH`, `collect(DISTINCT ...)` hoặc subquery khi cần tổng hợp từng nhánh riêng.
- **Kiểm tra index:** index trên property node dùng để xác định điểm bắt đầu, như `departmentCode`, `studentId` hoặc `courseCode`, có thể giúp truy vấn chọn lọc hơn. Khả năng dùng index cho relationship property phụ thuộc phiên bản và loại index Neo4j; cần xác minh bằng kế hoạch thực thi.
- **Dùng EXPLAIN và PROFILE:** kiểm tra operator, số hàng và lượng dữ liệu được duyệt bằng dữ liệu gần với thực tế.

Ví dụ tạo index cho mã khoa:

```cypher
CREATE INDEX department_code_index IF NOT EXISTS
FOR (d:Department)
ON (d.departmentCode)
```

Nếu truy vấn lọc thường xuyên theo `e.status` hoặc `o.term`, hãy kiểm tra khả năng tạo relationship property index trên phiên bản Neo4j đang dùng và xác nhận planner có sử dụng nó. Không tạo index chỉ vì một property xuất hiện trong `WHERE`; index cũng có chi phí lưu trữ và cập nhật.

## 11. Kiểm thử kết quả truy vấn

Integration test nên tạo dữ liệu gồm nhiều trường hợp để xác minh từng điều kiện trên relationship:

1. Sinh viên có enrollment `ACTIVE`, điểm đạt ngưỡng, khóa học mở đúng học kỳ và đúng khoa.
2. Sinh viên có điểm thấp hơn ngưỡng.
3. Sinh viên có trạng thái `CANCELLED`.
4. Khóa học được mở ở học kỳ khác.
5. Khóa học thuộc khoa khác.
6. Khóa học chưa có relationship `OFFERED_BY` để kiểm tra hành vi của `OPTIONAL MATCH`.

Với mỗi trường hợp, xác nhận cả số dòng và các giá trị projection. Đặc biệt, kiểm tra rằng `score` được lấy từ `ENROLLED_IN`, còn `term` và `campus` được lấy từ `OFFERED_BY`.

Khi kiểm thử aggregation, tạo dữ liệu có một sinh viên tham gia nhiều khóa học trong cùng khoa để xác nhận `count(DISTINCT s)` không đếm trùng. Nếu tính trung bình, kiểm tra đúng đơn vị tổng hợp và xử lý điểm `null` theo quy tắc nghiệp vụ.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có kết quả dù node tồn tại | Hướng relationship trong pattern không khớp đồ thị | Kiểm tra hướng cạnh bằng `MATCH` đơn giản hoặc đảo pattern. |
| Lọc sai giá trị relationship | Dùng property trên node thay vì biến relationship | Đặt biến cho cạnh, ví dụ `[e:ENROLLED_IN]`, rồi lọc `e.status`. |
| Kết quả có quá nhiều dòng | Một node tham gia nhiều đường đi hoặc nhiều nhánh bị nhân chéo | Xác định đơn vị một dòng, dùng `DISTINCT`, `WITH` hoặc aggregation phù hợp. |
| Projection có trường `null` | Alias trong `RETURN` không khớp getter hoặc property thực sự thiếu | Đối chiếu alias và tên getter; kiểm tra dữ liệu nguồn. |
| OPTIONAL MATCH không giữ bản ghi bên trái | Điều kiện trên quan hệ tùy chọn đặt ở `WHERE` sau đó | Đặt điều kiện ngay sau `OPTIONAL MATCH` để nó thuộc pattern tùy chọn. |
| Truy vấn chậm khi dữ liệu tăng | Pattern rộng, điểm bắt đầu kém chọn lọc hoặc cardinality lớn | Dùng index phù hợp, giới hạn pattern và đo bằng `PROFILE`. |

## 13. Ghi nhớ

Để truy vấn qua nhiều relationship, hãy đặt biến cho từng cạnh và dùng đúng biến khi lọc thuộc tính quan hệ. Trong mô hình ví dụ, `e.status`, `e.score` và `e.enrolledOn` thuộc `ENROLLED_IN`; `o.term` và `o.campus` thuộc `OFFERED_BY`. `MATCH` nối các node theo hướng relationship, còn `WHERE` kết hợp điều kiện trên node và từng cạnh.

Trong Spring Data Neo4j, dùng `@RelationshipProperties` và `@TargetNode` để ánh xạ dữ liệu trên relationship. Dùng `@Query` với tham số có tên để viết Cypher rõ ràng, và projection khi kết quả chỉ cần một tập trường cụ thể. Khi có quan hệ tùy chọn, đặt điều kiện đúng phạm vi `OPTIONAL MATCH`; khi tổng hợp, xác định rõ đơn vị đếm và tính trung bình. Cuối cùng, đo cardinality và kế hoạch thực thi trước khi tối ưu index hoặc mở rộng truy vấn.
