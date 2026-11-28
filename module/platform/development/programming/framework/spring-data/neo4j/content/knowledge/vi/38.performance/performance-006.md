# Tối ưu truy vấn bằng index và điểm bắt đầu phù hợp

Một truy vấn Cypher có thể trả về rất ít kết quả nhưng vẫn tốn nhiều thời gian nếu database phải quét quá nhiều node, kiểm tra nhiều property hoặc mở rộng những nhánh graph có độ lớn cao. Trong Spring Data Neo4j (SDN), repository và Neo4jClient gửi Cypher tới Neo4j; query planner của database quyết định cách tìm điểm bắt đầu, duyệt relationship và lọc kết quả.

Hai yếu tố thường quyết định chi phí truy vấn là **index phù hợp** và **điểm bắt đầu có tính chọn lọc**. Index giúp tìm nhanh các node hoặc relationship thỏa điều kiện trên property. Điểm bắt đầu tốt giới hạn số graph element cần duyệt trước khi mở rộng các relationship tiếp theo. Chỉ tạo index mà không kiểm tra query plan chưa đủ để bảo đảm truy vấn nhanh.

Bài học này trình bày cách chọn anchor node, lựa chọn loại index, thiết kế composite index, đọc EXPLAIN/PROFILE và viết query thân thiện với index trong ứng dụng SDN.

## Query planner chọn điểm bắt đầu như thế nào?

Khi nhận Cypher, Neo4j phân tích pattern và predicate, ước lượng số hàng trung gian rồi chọn execution plan. Với một truy vấn graph, planner cần tìm một tập node hoặc relationship ban đầu, sau đó mở rộng các cạnh để tìm phần còn lại của pattern.

Ví dụ hệ thống quản lý nhân viên và phòng ban:

~~~text
(Person) -[:WORKS_IN]-> (Department)
~~~

Giả sử có:

- 2.000.000 node Person.
- 4.000 node Department.
- Mỗi nhân viên có một employeeCode duy nhất.
- Mỗi phòng ban có một departmentCode duy nhất.

Truy vấn tìm nhân viên theo mã và phòng ban:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
      -[:WORKS_IN]->
      (d:Department)
RETURN p, d;
~~~

Nếu có index hoặc uniqueness constraint trên Person.employeeCode, database có thể tìm trực tiếp một Person bằng index seek rồi đi theo relationship WORKS_IN. Đây thường là điểm bắt đầu hiệu quả vì predicate chỉ khớp một node.

Nếu query bắt đầu từ toàn bộ Person mà không có index hữu ích, database có thể phải quét label rồi kiểm tra property. Nếu bắt đầu từ một node có hàng trăm nghìn relationship, bước mở rộng cũng có thể tạo ra nhiều hàng trung gian trước khi lọc.

**Anchor point** là node hoặc relationship được dùng làm điểm xuất phát để truy vấn tiếp tục duyệt graph. Một anchor tốt thường có các đặc điểm:

- Có label hoặc relationship type cụ thể.
- Có predicate trên property đã được index.
- Predicate có tính chọn lọc cao, tạo ra ít kết quả.
- Từ anchor có đường đi ngắn và có hướng rõ ràng tới phần graph cần lấy.
- Không phải mở rộng một node có degree quá lớn nếu có thể chọn điểm bắt đầu hẹp hơn.

Không phải cứ chọn label có ít node nhất là tốt. Planner cân nhắc cardinality, index, statistics, chi phí mở rộng và các predicate khác. Cũng không thể ép điểm bắt đầu chỉ bằng cách viết pattern trước trong câu Cypher; planner có thể sắp xếp lại các bước thực thi. Hãy kiểm tra plan thực tế.

## Index giúp tìm anchor nhanh hơn

Index là cấu trúc phụ trợ để tìm graph element theo label/type và giá trị property. Nếu không có index phù hợp, Neo4j có thể phải quét các node thuộc label rồi lọc property.

Ví dụ query:

~~~cypher
MATCH (p:Person)
WHERE p.email = $email
RETURN p;
~~~

Nếu có range index hoặc uniqueness constraint trên Person.email, planner có thể dùng index để tìm node thỏa điều kiện. Nếu không có, plan có thể chứa NodeByLabelScan và Filter.

Tạo range index:

~~~cypher
CREATE RANGE INDEX person_email_range
IF NOT EXISTS
FOR (p:Person)
ON (p.email);
~~~

Với thuộc tính định danh nghiệp vụ phải duy nhất, nên dùng uniqueness constraint thay vì chỉ tạo index thường:

~~~cypher
CREATE CONSTRAINT person_email_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
~~~

Uniqueness constraint bảo vệ tính toàn vẹn và Neo4j tạo index hỗ trợ constraint. Không cần tạo thêm một range index trùng lặp trên cùng label/property chỉ để tăng tốc query.

Index không phải cache miễn phí. Neo4j cần lưu và cập nhật index khi property được thêm, sửa hoặc xóa. Mỗi index làm tăng dung lượng lưu trữ và chi phí ghi; chỉ tạo index phục vụ những pattern truy vấn có thật.

## Các loại index thường gặp

Neo4j cung cấp nhiều loại index cho các dạng tìm kiếm khác nhau. Chọn index theo predicate và kiểu dữ liệu trong Cypher.

| Loại index | Mục đích chính | Ví dụ use case |
|---|---|---|
| Token lookup | Tìm node theo label hoặc relationship theo type | MATCH (p:Person) hoặc MATCH ()-[:WORKS_IN]->() |
| Range | Equality, range, prefix và các truy vấn có thứ tự trên property phù hợp | email = $email, age >= $minAge, createdAt |
| Text | Tìm kiếm chuỗi theo nội dung như CONTAINS hoặc ENDS WITH | Tìm tên chứa một từ |
| Point | Truy vấn không gian dựa trên tọa độ | Tìm địa điểm trong bán kính |
| Full-text | Tìm kiếm từ/cụm từ có analyzer và relevance score | Tìm tài liệu hoặc tên gần với cụm từ |
| Vector | Tìm vector tương đồng | Tìm sản phẩm hoặc nội dung gần embedding |

Neo4j tự tạo token lookup indexes trong các database thông thường để hỗ trợ tra label và relationship type. Token lookup index không thay thế property index: nó tìm node mang label Person, nhưng không tự tìm nhanh một node theo Person.email.

### Range index

Range index là lựa chọn phổ biến cho equality, so sánh khoảng và một số predicate trên property:

~~~cypher
CREATE RANGE INDEX person_age_range
IF NOT EXISTS
FOR (p:Person)
ON (p.age);
~~~

Query có thể sử dụng index:

~~~cypher
MATCH (p:Person)
WHERE p.age >= $minimumAge
  AND p.age < $maximumAge
RETURN p.employeeCode, p.fullName, p.age;
~~~

Range index cũng hữu ích với các truy vấn theo thời gian, mã, trạng thái hoặc số lượng có thể so sánh. Để biết predicate cụ thể có được index hỗ trợ hay không, kiểm tra query plan thay vì suy ra chỉ từ tên index.

### Text index

Text index tối ưu các predicate tìm kiếm chuỗi như CONTAINS và ENDS WITH:

~~~cypher
CREATE TEXT INDEX person_name_text
IF NOT EXISTS
FOR (p:Person)
ON (p.fullName);
~~~

~~~cypher
MATCH (p:Person)
WHERE p.fullName CONTAINS $fragment
RETURN p.employeeCode, p.fullName
LIMIT 50;
~~~

Range index thường phù hợp hơn với equality hoặc prefix lookup. Text index phù hợp hơn với tìm kiếm substring. Hãy so sánh plan và dữ liệu thực tế; một text index không tự giải quyết yêu cầu tìm kiếm ngôn ngữ tự nhiên, stemming, ranking hoặc fuzzy matching.

### Full-text index

Full-text index dùng analyzer để tách và xử lý từ, đồng thời trả về điểm relevance. Khác với range/text index được planner chọn trong query plan thông thường, full-text index thường được gọi tường minh qua procedure.

Tạo full-text index:

~~~cypher
CREATE FULLTEXT INDEX person_name_fulltext
IF NOT EXISTS
FOR (p:Person)
ON EACH [p.fullName];
~~~

Truy vấn:

~~~cypher
CALL db.index.fulltext.queryNodes(
    "person_name_fulltext",
    $searchText
)
YIELD node, score
RETURN node.employeeCode AS employeeCode,
       node.fullName AS fullName,
       score
ORDER BY score DESC
LIMIT 20;
~~~

Full-text index phù hợp với tìm kiếm theo từ và điểm liên quan. Nó không thay thế uniqueness constraint hoặc range index dùng để tra cứu chính xác theo khóa.

### Point index

Point index hỗ trợ truy vấn dữ liệu không gian. Ví dụ node Place có property location kiểu point:

~~~cypher
CREATE POINT INDEX place_location
IF NOT EXISTS
FOR (p:Place)
ON (p.location);
~~~

Có thể tìm địa điểm trong khoảng cách:

~~~cypher
MATCH (p:Place)
WHERE point.distance(p.location, $origin) <= $radiusMeters
RETURN p.name, p.location
ORDER BY point.distance(p.location, $origin)
LIMIT 50;
~~~

Point index hữu ích khi truy vấn dùng các predicate không gian được hỗ trợ. Kiểm tra query plan để xác nhận index thực sự được sử dụng.

### Vector index

Vector index phục vụ tìm kiếm tương đồng giữa embedding, chẳng hạn tìm nội dung có vector gần với vector truy vấn. Đây là loại index chuyên biệt, phụ thuộc phiên bản Neo4j và cấu hình vector dimensions/similarity function. Không dùng vector index cho tra cứu equality theo ID hoặc thay thế range index.

Khi dùng vector search, hãy theo tài liệu đúng phiên bản Neo4j về cách tạo vector index, truy vấn top-k và xử lý kết quả. Đừng giả định vector index tự động được dùng cho mọi câu MATCH; cần dùng API/procedure/vector query tương ứng của phiên bản.

## Chọn index theo predicate

Một số pattern thường gặp:

| Predicate trong Cypher | Index thường phù hợp |
|---|---|
| p.email = $email | Range hoặc uniqueness constraint |
| p.age >= $minAge | Range |
| p.createdAt < $cutoff | Range |
| p.name STARTS WITH $prefix | Range hoặc text tùy query/version |
| p.name CONTAINS $fragment | Text |
| p.name ENDS WITH $suffix | Text |
| point.distance(p.location, $point) < $radius | Point |
| Tìm từ/cụm từ và relevance score | Full-text |
| Tìm embedding gần nhất | Vector |

Predicate có thể trông tương tự nhưng khả năng sử dụng index khác nhau theo loại index, phiên bản và cách viết query. Hãy kiểm tra execution plan. Một index tồn tại không có nghĩa mọi predicate trên property đó đều dùng được index.

## Composite index và thứ tự property

Nếu ứng dụng thường truy vấn theo nhiều điều kiện cùng lúc, composite index có thể giúp planner tìm đúng nhóm record ngay từ đầu.

Ví dụ phần lớn truy vấn danh sách nhân viên đều lọc theo tenant, trạng thái và sắp xếp theo ngày tạo:

~~~cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
RETURN p.employeeCode, p.fullName, p.createdAt
ORDER BY p.createdAt DESC
LIMIT 50;
~~~

Có thể tạo composite range index:

~~~cypher
CREATE RANGE INDEX person_tenant_status_created
IF NOT EXISTS
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt);
~~~

Thứ tự property có ý nghĩa. Composite index thường được sử dụng hiệu quả khi query có predicate trên property đứng đầu index; các property tiếp theo có thể tiếp tục thu hẹp phạm vi. Nếu query chỉ lọc theo status mà index bắt đầu bằng tenantId, index đó có thể không phải lựa chọn phù hợp.

Một số quy tắc thiết kế:

1. Đặt property thường xuất hiện trong điều kiện equality và có tính chọn lọc phù hợp ở đầu index.
2. Sắp xếp property theo các pattern truy vấn thực tế, không theo thứ tự field trong entity.
3. Nếu query chỉ tìm theo tenantId, index composite bắt đầu bằng tenantId có thể đáp ứng.
4. Nếu query chỉ tìm theo status, cân nhắc index riêng bắt đầu bằng status nếu đây là workload quan trọng.
5. Đo plan trước khi tạo thêm index; tránh tạo nhiều composite index chỉ khác thứ tự mà không có truy vấn tương ứng.

Ví dụ uniqueness constraint trên composite business key:

~~~cypher
CREATE CONSTRAINT person_tenant_employee_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.employeeCode) IS UNIQUE;
~~~

Constraint này vừa bảo vệ tổ hợp business key không trùng vừa tạo index hỗ trợ tra cứu theo tổ hợp. Nếu nghiệp vụ yêu cầu mỗi property phải tồn tại, cần thêm existence hoặc dùng node key constraint ở edition/phiên bản hỗ trợ; uniqueness không tự bắt buộc property xuất hiện.

## Chọn điểm bắt đầu có tính chọn lọc

Giả sử cần tìm nhân viên trong một phòng ban theo mã nhân viên. Có hai cách mô tả pattern:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
      -[:WORKS_IN]->
      (d:Department)
RETURN p, d;
~~~

~~~cypher
MATCH (d:Department {departmentCode: $departmentCode})
      <-[:WORKS_IN]-
      (p:Person)
WHERE p.employeeCode = $employeeCode
RETURN p, d;
~~~

Cả hai biểu diễn cùng pattern quan hệ. Planner có thể chọn Person hoặc Department làm điểm bắt đầu dựa trên index và statistics. Nếu employeeCode duy nhất, bắt đầu từ Person thường tạo một hàng. Nếu departmentCode chỉ có vài giá trị và mỗi phòng ban có hàng chục nghìn nhân viên, bắt đầu từ Department có thể tạo tập lớn hơn trước khi lọc Person.

Tối ưu anchor point theo quy trình:

- Xác định predicate nào thu hẹp kết quả nhiều nhất.
- Đảm bảo label/type và property được viết rõ trong pattern.
- Tạo index phù hợp với predicate đó.
- Giữ hướng relationship và loại relationship cụ thể để hạn chế mở rộng.
- Dùng EXPLAIN hoặc PROFILE xem planner đã chọn anchor nào.
- Kiểm tra số hàng trung gian sau từng operator; nếu số hàng tăng đột biến, xem lại anchor hoặc đường duyệt graph.

Index giúp tìm anchor nhưng không làm cho mọi bước sau trở nên miễn phí. Nếu một node có hàng triệu relationship, việc mở rộng từ node đó vẫn tốn chi phí. Có thể cần thêm điều kiện trên relationship, giới hạn độ sâu traversal, hoặc chọn một node đầu vào hẹp hơn.

## Đọc EXPLAIN và PROFILE

Hai lệnh này giúp hiểu cách Neo4j thực thi query:

- EXPLAIN lập execution plan và ước lượng chi phí, nhưng không chạy query.
- PROFILE thực thi query và thu thập số liệu thực tế của các operator.

Ví dụ:

~~~cypher
EXPLAIN
MATCH (p:Person)
WHERE p.email = $email
RETURN p;
~~~

Sau khi kiểm tra plan ước lượng, dùng PROFILE trên dữ liệu test hoặc staging:

~~~cypher
PROFILE
MATCH (p:Person)
WHERE p.email = $email
RETURN p;
~~~

Một số operator thường gặp:

| Operator | Ý nghĩa |
|---|---|
| NodeIndexSeek | Tìm node bằng index predicate |
| NodeUniqueIndexSeek | Tìm node bằng unique index/constraint |
| NodeByLabelScan | Quét các node có label rồi xử lý tiếp |
| AllNodesScan | Quét toàn bộ node |
| Expand(All) | Mở rộng relationship từ node đầu vào |
| Filter | Kiểm tra predicate trên các hàng đầu vào |
| Sort | Sắp xếp hàng kết quả |
| EagerAggregation | Gom dữ liệu trước khi tổng hợp trong trường hợp cần materialize |
| NodeIndexContainsScan | Dùng text index cho predicate substring được hỗ trợ |

Khi đọc plan, tập trung vào:

- **Rows:** số hàng được operator nhận và phát ra.
- **DB Hits:** số lần operator truy cập dữ liệu trong store/index.
- **Estimated Rows:** số hàng planner dự đoán.
- **Memory:** lượng bộ nhớ một số operator sử dụng.
- **Page cache hits/misses:** dấu hiệu dữ liệu được đọc từ page cache hay phải nạp từ storage.

Tên operator và số liệu có thể thay đổi theo phiên bản Neo4j và runtime. Không so sánh trực tiếp hai plan nếu dataset, tham số, cache state hoặc phiên bản khác nhau.

### Nhận biết anchor chưa tốt

Một plan có thể bắt đầu bằng NodeByLabelScan trên label rất lớn, sau đó mới dùng Filter để giữ lại vài node. Nếu query thường xuyên chạy theo một property có tính chọn lọc cao, cân nhắc index trên property đó.

Một plan khác có thể bắt đầu bằng NodeIndexSeek, nhưng sau đó Expand(All) tạo ra hàng trăm nghìn hàng. Trong trường hợp này index đã giúp tìm anchor, nhưng pattern relationship hoặc độ phân nhánh mới là phần tốn chi phí.

Không phải NodeByLabelScan luôn xấu. Nếu query cần phần lớn node của một label, label scan có thể rẻ hơn index seek rồi truy cập từng record. Mục tiêu là giảm tổng chi phí, không phải ép mọi query phải có NodeIndexSeek.

## Viết predicate để planner dùng index

Hãy giữ property được index ở dạng predicate mà index hỗ trợ.

Dùng so sánh trực tiếp:

~~~cypher
MATCH (p:Person)
WHERE p.email = $email
RETURN p;
~~~

Tránh bọc property trong function nếu không cần thiết:

~~~cypher
MATCH (p:Person)
WHERE toLower(p.email) = toLower($email)
RETURN p;
~~~

Biểu thức biến đổi property như toLower(p.email) có thể ngăn range index thông thường được dùng cho seek. Nếu cần so sánh không phân biệt hoa thường, có thể lưu thêm property đã chuẩn hóa, chẳng hạn emailNormalized, index property đó và chuẩn hóa giá trị đầu vào ở tầng ứng dụng:

~~~cypher
MATCH (p:Person)
WHERE p.emailNormalized = $normalizedEmail
RETURN p;
~~~

Với điều kiện thời gian, biến đổi tham số thay vì property:

~~~cypher
MATCH (p:Person)
WHERE p.createdAt >= datetime($from)
  AND p.createdAt < datetime($to)
RETURN p;
~~~

Điều này giữ property createdAt trực tiếp trong range predicate. Hãy thống nhất kiểu dữ liệu được lưu và kiểu tham số truyền vào.

Sử dụng parameter thay vì nối chuỗi giá trị vào Cypher. Parameter giúp tái sử dụng query plan và tránh lỗi escaping/injection:

~~~java
client.query("""
        MATCH (p:Person)
        WHERE p.email = $email
        RETURN p
        """)
    .bind(email).to("email")
    .fetchAs(Person.class)
    .one();
~~~

Không thể parameter hóa label, relationship type hoặc tên property theo cách giống value parameter trong mọi ngữ cảnh Cypher. Nếu cần chọn động cấu trúc query, hãy dùng allowlist các identifier hợp lệ và không nối trực tiếp input không tin cậy.

## Kết hợp index với relationship traversal

Trong graph, index thường giúp tìm node đầu vào; sau đó Neo4j đi theo relationship từ node đó. Nếu đã biết employeeCode, query sau có thể tìm một nhân viên rồi lấy phòng ban:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
      -[r:WORKS_IN]->
      (d:Department)
RETURN p.employeeCode, d.departmentCode, r.role;
~~~

Nếu cần tìm các nhân viên thuộc một phòng ban, có thể bắt đầu từ Department có mã được index:

~~~cypher
MATCH (d:Department {departmentCode: $departmentCode})
      <-[r:WORKS_IN]-
      (p:Person)
RETURN p.employeeCode, p.fullName, r.role
ORDER BY p.employeeCode;
~~~

Khi truy vấn cần bắt đầu trực tiếp từ relationship property, có thể tạo index trên relationship type:

~~~cypher
CREATE RANGE INDEX works_on_since_range
IF NOT EXISTS
FOR ()-[r:WORKS_ON]-()
ON (r.since);
~~~

~~~cypher
MATCH (p:Person)-[r:WORKS_ON]->(d:Department)
WHERE r.since >= date($fromDate)
RETURN p.employeeCode, d.departmentCode, r.since;
~~~

Relationship property index hữu ích khi predicate trên property cạnh là điểm tìm kiếm. Nếu query đã bắt đầu từ một node được chọn lọc và chỉ mở rộng vài relationship, traversal adjacency có thể hiệu quả hơn việc tìm relationship qua index; hãy so sánh hai plan trên dữ liệu thực tế.

Khi lựa chọn hướng:

- Dùng relationship type cụ thể thay cho pattern relationship không giới hạn nếu nghiệp vụ đã biết loại cạnh.
- Chỉ định hướng nếu quan hệ có hướng nghiệp vụ rõ ràng.
- Tránh traversal không giới hạn độ sâu khi chỉ cần một hoặc hai bước.
- Nếu lọc theo property của relationship, cân nhắc index trên relationship type/property và xác nhận bằng PROFILE.
- Trả về đúng các property cần dùng thay vì toàn bộ graph nếu không cần ánh xạ entity graph đầy đủ.

Index không thay thế mô hình graph hợp lý. Một anchor chọn lọc và đường relationship rõ ràng thường quan trọng hơn việc tạo hàng loạt index.

## Dùng index trong Spring Data Neo4j

Repository method được dẫn xuất từ tên method có thể tạo predicate tương ứng. Ví dụ:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByEmail(String email);

    List<Person> findByAgeGreaterThanEqualAndActiveTrue(int minimumAge);
}
~~~

Nếu database có index phù hợp với Person.email hoặc query theo age, planner có thể dùng index. Tên method repository không tự tạo index; schema cần được quản lý riêng bằng Cypher migration hoặc công cụ quản trị.

Với custom query, giữ label và property predicate rõ ràng:

~~~java
@Query("""
    MATCH (p:Person {employeeCode: $employeeCode})
          -[:WORKS_IN]->
          (d:Department)
    RETURN p
    """)
Optional<Person> findPersonWorkingInDepartment(String employeeCode);
~~~

Ví dụ trên dùng pattern relationship để giới hạn Person phù hợp, nhưng chỉ trả node p. Nó không yêu cầu SDN ánh xạ Department thành một trường kết quả riêng. Nếu muốn nhận cả hai đối tượng, hãy dùng DTO/projection phù hợp và trả các trường tương ứng.

Neo4jClient phù hợp khi cần kiểm soát Cypher và ánh xạ kết quả:

~~~java
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import reactor.core.publisher.Flux;

public record PersonDepartment(
    String employeeCode,
    String departmentCode
) {
}
~~~

~~~java
private final ReactiveNeo4jClient neo4jClient;

Flux<PersonDepartment> findDepartmentForEmployee(String employeeCode) {
    return neo4jClient.query("""
            MATCH (p:Person {employeeCode: $employeeCode})
                  -[:WORKS_IN]->
                  (d:Department)
            RETURN p.employeeCode AS employeeCode,
                   d.departmentCode AS departmentCode
            """)
        .bind(employeeCode).to("employeeCode")
        .fetchAs(PersonDepartment.class)
        .mappedBy((typeSystem, record) ->
            new PersonDepartment(
                record.get("employeeCode").asString(),
                record.get("departmentCode").asString()
            )
        )
        .all();
}
~~~

Index được tạo ở Neo4j database, không phải bằng cách thêm annotation tùy ý vào repository method. Hãy version hóa các lệnh CREATE INDEX hoặc CREATE CONSTRAINT trong quy trình migration để môi trường development, staging và production có cùng schema.

## Index và ORDER BY, LIMIT, pagination

Một range index có thể giúp một số query trả kết quả theo thứ tự property đã index mà không cần operator Sort, nếu điều kiện lọc và thứ tự sắp xếp phù hợp với index. Ví dụ:

~~~cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = "ACTIVE"
RETURN p.employeeCode, p.createdAt
ORDER BY p.createdAt DESC
LIMIT 50;
~~~

Composite index (tenantId, status, createdAt) có thể giúp tìm tập con và cung cấp thứ tự phù hợp sau khi các property đứng trước được cố định bằng equality. Cần kiểm tra plan xem Sort có còn hay không.

LIMIT giới hạn số hàng được trả về, nhưng không tự động làm query rẻ nếu database vẫn phải quét hoặc sắp xếp lượng dữ liệu rất lớn trước khi chọn các hàng đầu tiên. Kết hợp index, predicate chọn lọc và thứ tự ổn định.

Với pagination sâu, SKIP lớn có thể yêu cầu database bỏ qua nhiều hàng. Có thể dùng keyset pagination với property có index:

~~~cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.employeeCode > $lastEmployeeCode
RETURN p.employeeCode, p.fullName
ORDER BY p.employeeCode
LIMIT $pageSize;
~~~

Điều kiện employeeCode > $lastEmployeeCode cần phù hợp với thứ tự sort và index. Nếu business key không duy nhất, thêm tie-breaker ổn định như id vào điều kiện và thứ tự. Đừng dùng cursor từ tenant này cho tenant khác; cursor phải gắn với filter và scope ban đầu.

## Index có chi phí: không tạo quá nhiều

Mỗi index tiêu thụ dung lượng và cần được cập nhật khi dữ liệu thay đổi. Nếu một node có nhiều property index, thao tác ghi có thể phải duy trì nhiều cấu trúc phụ trợ.

Trước khi tạo index, hãy trả lời:

- Query nào sẽ sử dụng index?
- Query có đủ thường xuyên hoặc đủ quan trọng không?
- Predicate có tính chọn lọc không?
- Có thể dùng uniqueness/key constraint thay cho index thường không?
- Đã có composite index hoặc constraint bao phủ cùng pattern chưa?
- Index có làm tăng chi phí ghi đáng kể với workload hiện tại không?

Tránh tạo index cho mọi property của entity. Một field hiếm khi được lọc, có ít giá trị khác nhau hoặc chỉ được trả về trong kết quả có thể không cần index.

Index có tính chọn lọc thấp, ví dụ boolean active, có thể không giúp nhiều nếu phần lớn node đều có cùng giá trị. Nếu query luôn lọc tenantId và status, composite index theo đúng pattern có thể hữu ích hơn nhiều index riêng lẻ; hãy xác nhận bằng dữ liệu thực tế.

## Theo dõi trạng thái và quản lý index

Sau khi tạo index, kiểm tra trạng thái:

~~~cypher
SHOW INDEXES;
~~~

Có thể xem các trường cần thiết:

~~~cypher
SHOW INDEXES YIELD
    name, type, entityType, labelsOrTypes,
    properties, state, populationPercent
RETURN *;
~~~

Index mới tạo cần thời gian population. Chỉ khi trạng thái sẵn sàng thì planner mới có thể sử dụng đầy đủ index. Nếu index ở trạng thái POPULATING trong thời gian dài, kiểm tra log, tải hệ thống và tiến trình population.

Xóa index không còn cần thiết:

~~~cypher
DROP INDEX person_email_range IF EXISTS;
~~~

Không drop index đang được constraint sở hữu; index của uniqueness/key constraint được quản lý cùng constraint. Trước khi xóa index, kiểm tra query plan của workload liên quan và xác nhận không còn query quan trọng phụ thuộc vào nó.

Sau khi thay đổi schema hoặc dữ liệu đáng kể, theo dõi query plan và thống kê index. Không cần tạo lại index theo lịch nếu chưa có bằng chứng vấn đề; để Neo4j quản lý lifecycle index theo cơ chế của phiên bản.

## Khi nào cân nhắc index hint?

Neo4j có query planner dựa trên cost và statistics. Thông thường nên để planner tự chọn index. Cypher có hỗ trợ index hint như:

~~~cypher
MATCH (p:Person)
USING INDEX p:Person(email)
WHERE p.email = $email
RETURN p;
~~~

Hint yêu cầu planner sử dụng index chỉ định nếu hợp lệ. Chỉ cân nhắc hint khi đã đo bằng PROFILE, hiểu vì sao planner chọn plan kém và xác nhận index đó tốt ổn định trên workload thực tế.

Hint có thể làm query kém đi khi dữ liệu, phân bố giá trị hoặc schema thay đổi. Không dùng hint để che giấu index thiết kế sai, statistics cũ hoặc query có predicate không chọn lọc.

## Quy trình tối ưu một query thực tế

Khi một repository method hoặc Cypher query chạy chậm, thực hiện theo thứ tự:

1. **Đo baseline:** ghi lại p50/p95 latency, số lần gọi, số record và tham số đại diện.
2. **Kiểm tra query:** xác định label/type, predicate, relationship traversal, sort và aggregation.
3. **EXPLAIN:** xem planner ước lượng anchor, operator và cardinality.
4. **PROFILE trên môi trường phù hợp:** xem Rows, DB Hits, memory và page cache.
5. **Chọn index:** range, text, point hoặc full-text/vector theo predicate.
6. **Chọn anchor:** ưu tiên predicate có tính chọn lọc và đường graph có degree phù hợp.
7. **Viết lại predicate:** tránh biến đổi property đã index nếu có thể chuẩn hóa trước.
8. **Đo lại:** dùng cùng dataset, tham số, concurrency và trạng thái cache tương đương.
9. **Kiểm tra write overhead:** đo tốc độ ghi và dung lượng sau khi thêm index.
10. **Version hóa schema:** đưa index/constraint vào migration và kiểm tra trạng thái ở từng môi trường.

Không chỉ tối ưu thời gian query đơn lẻ. Một query nhanh khi chạy một lần có thể trở thành nút thắt khi hàng trăm request đồng thời, vì vậy cần đo cả tải và độ trễ tail.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo index nhưng không kiểm tra plan | Query có thể vẫn scan hoặc không dùng index | Dùng EXPLAIN/PROFILE để xác nhận |
| Bắt đầu từ label quá rộng | Nhiều node được kiểm tra trước khi lọc | Chọn predicate có tính chọn lọc và index phù hợp |
| Cho rằng pattern viết đầu tiên là anchor | Planner có thể sắp xếp lại execution plan | Đọc plan thực tế |
| Dùng range index cho substring search | Predicate CONTAINS có thể không được tối ưu như mong đợi | Cân nhắc text index |
| Nhầm text index với full-text index | Không có analyzer hoặc relevance score như yêu cầu | Dùng full-text index và procedure phù hợp |
| Tạo nhiều index riêng lẻ cho query nhiều điều kiện | Tăng chi phí ghi nhưng không cải thiện plan như mong muốn | Thiết kế composite index theo workload |
| Sắp xếp property composite index không phù hợp | Query không dùng được prefix index mong muốn | Đặt property đầu theo pattern equality thường dùng |
| Bọc property bằng toLower() hoặc function | Index seek thông thường có thể không được dùng | Lưu property đã chuẩn hóa và index property đó |
| Dùng index cho property ít chọn lọc | Index seek có thể tốn hơn scan | Đo cardinality và so sánh plan |
| Cho rằng index làm traversal luôn nhanh | Expand từ node degree lớn vẫn tạo nhiều hàng | Chọn anchor và relationship path phù hợp |
| Dùng LIMIT nhưng query vẫn scan/sort toàn bộ | Ít kết quả trả về nhưng DB Hits vẫn cao | Kết hợp predicate chọn lọc, index và ordering |
| Tạo index trùng constraint | Dư thừa hoặc xung đột schema | Kiểm tra index do uniqueness/key constraint sở hữu |
| PROFILE truy vấn ghi trên production | Thao tác thật có thể được thực thi | Dùng EXPLAIN hoặc môi trường staging an toàn |
| Dùng index hint mà không đo | Plan bị cố định có thể kém khi dữ liệu đổi | Chỉ dùng hint sau khi đo và theo dõi |

## Bài tập thực hành

Với graph Person, Department và WORKS_IN, hãy thực hiện:

1. Tạo ít nhất 100.000 Person và 1.000 Department với phân bố dữ liệu thực tế.
2. Viết query tìm Person theo employeeCode; chạy EXPLAIN trước khi có index.
3. Tạo range index hoặc uniqueness constraint cho employeeCode, chạy lại EXPLAIN và PROFILE.
4. So sánh NodeByLabelScan với NodeIndexSeek và ghi lại Rows/DB Hits.
5. Viết query tìm Person theo age trong một khoảng và tạo range index.
6. Viết query tìm tên có chứa chuỗi, tạo text index và xác nhận operator tương ứng.
7. Tạo composite index (tenantId, status, createdAt) cho query danh sách nhân viên theo tenant.
8. Thay đổi thứ tự property composite index trong database test và quan sát query nào còn dùng index.
9. So sánh query bắt đầu từ Person có employeeCode duy nhất với query bắt đầu từ Department có nhiều nhân viên.
10. Tìm một query có Expand(All) tạo nhiều hàng và thử chọn anchor hoặc hướng relationship khác.
11. Dùng keyset pagination với property có index và so sánh với SKIP lớn.
12. Đo read latency, write latency và dung lượng index trước/sau khi thêm index; chọn cấu hình dựa trên workload.

Khi tối ưu SDN với Neo4j, hãy chọn index theo predicate thực tế và điểm bắt đầu có tính chọn lọc. Dùng EXPLAIN để hiểu kế hoạch, PROFILE để đo dữ liệu thực tế, rồi kiểm tra cả chi phí mở rộng relationship lẫn chi phí duy trì index khi ghi. Index tốt giúp tìm anchor nhanh; query tốt giữ số hàng trung gian nhỏ và chỉ đọc phần graph mà nghiệp vụ cần.

Tài liệu tham khảo chính thức:

- [Neo4j Cypher Manual - Search-performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/)
- [Neo4j Cypher Manual - Indexes for search performance](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual - EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual - Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Spring Data Neo4j - Repository query methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)

