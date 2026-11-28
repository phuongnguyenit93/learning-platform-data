# Nhận diện full scan, số bước duyệt lớn và tích Descartes

Hiệu năng của truy vấn graph phụ thuộc nhiều vào cách Neo4j tìm node bắt đầu, mở rộng relationship và kết hợp các pattern. Một truy vấn có thể chậm dù chỉ trả về vài dòng vì database đã quét hàng triệu node, duyệt qua một vùng graph lớn hoặc tạo ra số tổ hợp trung gian khổng lồ trước khi lọc kết quả.

Trong Spring Data Neo4j (SDN), các truy vấn này có thể đến từ derived query, @Query, Cypher-DSL hoặc Neo4jClient. SDN ánh xạ và thực thi Cypher; việc chọn access path và operator thực thi do Cypher planner của Neo4j quyết định. Vì vậy, cần đọc execution plan của chính câu Cypher được chạy với dữ liệu và tham số đại diện.

Bài học tập trung vào ba dấu hiệu thường gặp: full scan, traversal có quá nhiều bước hoặc nhánh, và Cartesian product giữa các pattern không liên kết. Mục tiêu là tìm đúng nguyên nhân, sửa query mà vẫn giữ nguyên ý nghĩa nghiệp vụ và đo lại hiệu quả.

## 1. Ba nguồn gây tốn kém thường gặp

Một truy vấn graph thường có ba phần:

1. Tìm node hoặc relationship làm điểm bắt đầu.
2. Mở rộng qua các relationship để lấy phần graph liên quan.
3. Kết hợp, lọc, sắp xếp và trả kết quả.

Ba vấn đề trong bài thường xuất hiện ở các phần này:

| Dấu hiệu | Điều gì xảy ra | Hệ quả |
| --- | --- | --- |
| Full scan | Neo4j kiểm tra toàn bộ node hoặc toàn bộ node mang một label để tìm dữ liệu phù hợp | Tốn DB Hits và thời gian khi tập dữ liệu lớn |
| Traversal quá rộng | Truy vấn mở rộng qua nhiều relationship, nhiều tầng hoặc nhiều nhánh | Số đường đi và node trung gian tăng nhanh |
| Cartesian product | Hai tập pattern độc lập được kết hợp thành mọi cặp có thể | Số dòng trung gian bằng tích kích thước hai tập |

Một query trả về 10 dòng không có nghĩa nó chỉ xử lý 10 đối tượng. Hãy nhìn số dòng và DB Hits ở từng operator trong execution plan, không chỉ nhìn số kết quả cuối cùng.

## 2. Đọc execution plan bằng EXPLAIN và PROFILE

EXPLAIN yêu cầu Neo4j lập kế hoạch thực thi nhưng không chạy truy vấn. Nó hữu ích để xem planner dự định dùng scan, index seek, traversal hay phép kết hợp nào.

PROFILE thực thi truy vấn và trả về số liệu của các operator. Dùng PROFILE cho query đọc trên dữ liệu đại diện để xem số dòng thực tế, DB Hits, thời gian và thông tin page cache. Với truy vấn ghi, PROFILE có thể thực hiện thay đổi dữ liệu; chỉ chạy trên môi trường kiểm thử hoặc với dữ liệu an toàn.

Ví dụ:

~~~cypher
EXPLAIN
MATCH (person:Person)
WHERE person.email = $email
RETURN person
~~~

~~~cypher
PROFILE
MATCH (person:Person)
WHERE person.email = $email
RETURN person
~~~

Khi đọc plan, chú ý các thông tin:

| Chỉ số | Cách hiểu |
| --- | --- |
| Operator | Loại thao tác planner chọn, ví dụ scan, seek, expand, sort hoặc CartesianProduct |
| Estimated Rows | Số dòng planner ước lượng operator sẽ phát ra |
| Rows | Số dòng thực tế operator phát ra khi PROFILE |
| DB Hits | Số lần operator truy cập các cấu trúc dữ liệu của storage engine; đây không phải số lần đọc đĩa |
| Page Cache Hits/Misses | Thông tin truy cập page cache nếu phiên bản và cách hiển thị plan cung cấp |
| Time | Thời gian thực thi được ghi nhận cho operator hoặc query |
| Memory | Bộ nhớ operator sử dụng nếu plan hiển thị |

Plan thường được hiển thị dưới dạng cây. Hãy theo dõi từ các operator đầu vào ở phía dưới lên operator kết quả ở phía trên. Một operator phát ra rất nhiều Rows có thể khiến tất cả operator phía trên phải xử lý lượng dữ liệu lớn hơn.

DB Hits cao là dấu hiệu cần điều tra, nhưng không tự nó chứng minh có disk I/O cao. Tương tự, một operator có nhiều Rows có thể đúng với yêu cầu nếu ứng dụng thực sự cần tất cả kết quả đó. Phải so sánh số liệu với ý nghĩa truy vấn.

Tên operator có thể thay đổi giữa các phiên bản Neo4j và các chiến lược planner. Các tên trong bài là những operator thường gặp, không phải danh sách cố định cho mọi phiên bản.

## 3. Nhận diện full scan

Full scan xảy ra khi Neo4j phải kiểm tra một tập node lớn để tìm những node thỏa điều kiện. Trong plan, các operator thường cần chú ý:

| Operator | Ý nghĩa |
| --- | --- |
| AllNodesScan | Quét toàn bộ node trong database |
| NodeByLabelScan | Quét các node có một label cụ thể |
| NodeIndexScan | Duyệt các entry của index thay vì seek tới một vùng chọn lọc |
| NodeIndexSeek | Dùng index để định vị các entry phù hợp với điều kiện |

NodeByLabelScan không giống AllNodesScan: nó giới hạn ở một label, nhưng vẫn có thể tốn kém nếu label đó chứa phần lớn graph. NodeIndexScan cũng không đồng nghĩa với lookup chọn lọc; operator này có thể duyệt nhiều entry index. NodeIndexSeek thường cho biết planner có thể định vị theo một predicate phù hợp.

### 3.1. Truy vấn không có điểm neo chọn lọc

Ví dụ tìm Person bằng email:

~~~cypher
MATCH (person:Person)
WHERE person.email = $email
RETURN person
~~~

Nếu chưa có index phù hợp trên Person.email, plan có thể dùng NodeByLabelScan rồi Filter. Nếu label Person có hàng triệu node, database phải kiểm tra nhiều node dù kết quả chỉ có một người.

Tạo range index phù hợp:

~~~cypher
CREATE RANGE INDEX person_email IF NOT EXISTS
FOR (person:Person)
ON (person.email)
~~~

Sau khi index đã ONLINE, chạy lại PROFILE với cùng tham số. Planner có thể dùng NodeIndexSeek để tìm Person theo email.

Nếu email phải duy nhất, hãy chọn uniqueness constraint ngay từ đầu thay cho index độc lập ở ví dụ trên:

~~~cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE person.email IS UNIQUE
~~~

Constraint bảo vệ tính duy nhất và được Neo4j hỗ trợ bằng backing index. Không tạo thêm index trùng mục đích nếu constraint đã cung cấp index cần thiết.

### 3.2. Thiếu label hoặc predicate không khai thác được index

Truy vấn sau tìm tất cả node có property email, không giới hạn label:

~~~cypher
MATCH (node)
WHERE node.email = $email
RETURN node
~~~

Nếu domain chỉ lưu email trên Person, thêm label giúp giới hạn phạm vi:

~~~cypher
MATCH (person:Person)
WHERE person.email = $email
RETURN person
~~~

Một biểu thức áp dụng hàm lên property cũng có thể khiến planner không dùng được index thông thường theo cách mong đợi:

~~~cypher
MATCH (person:Person)
WHERE toLower(person.email) = toLower($email)
RETURN person
~~~

Nếu ứng dụng cần so sánh không phân biệt chữ hoa/thường, cân nhắc chuẩn hóa email khi ghi và chuẩn hóa tham số trước khi truy vấn, sau đó so sánh trực tiếp property với parameter. Chỉ làm vậy nếu quy tắc chuẩn hóa phù hợp với domain và dữ liệu hiện có đã được backfill.

Không loại bỏ label hoặc điều kiện chỉ để query ngắn hơn. Label, property predicate và index cùng nhau giúp planner xác định điểm bắt đầu phù hợp.

### 3.3. Full scan không phải lúc nào cũng là lỗi

Scan có thể hợp lý khi tập dữ liệu nhỏ, query cần phần lớn node, predicate ít chọn lọc hoặc chi phí seek cộng với việc đọc kết quả lớn hơn chi phí scan. Một truy vấn báo cáo cần đọc toàn bộ Person có thể không được cải thiện chỉ bằng cách thêm index.

Không đặt mục tiêu loại bỏ mọi scan. Mục tiêu là tránh scan lớn không cần thiết trong query có thể bắt đầu từ một tập dữ liệu chọn lọc hơn.

## 4. Nhận diện traversal có quá nhiều bước

Graph traversal bắt đầu từ node rồi đi qua relationship. Một traversal có thể tốn kém khi:

- Đi qua quá nhiều tầng relationship.
- Dùng relationship type quá rộng hoặc không chỉ định hướng.
- Bắt đầu từ một tập node lớn thay vì một node neo chọn lọc.
- Có degree cao, tức một node nối tới rất nhiều node khác.
- Dùng variable-length path với giới hạn sâu hoặc không giới hạn.
- Giữ lại nhiều path trung gian trong khi nghiệp vụ chỉ cần node đích hoặc câu trả lời có/không.

Các operator thường thấy trong plan gồm Expand(All), VarLengthExpand(All), Expand(Into) hoặc các biến thể theo phiên bản. Hãy xem Rows và DB Hits sau mỗi bước mở rộng để biết graph tăng nhanh ở đâu.

### 4.1. Variable-length traversal quá rộng

Ví dụ tìm mọi người có thể tiếp cận từ một Person qua quan hệ KNOWS:

~~~cypher
MATCH (start:Person {businessId: $personId})
MATCH path = (start)-[:KNOWS*1..8]->(target:Person)
RETURN path
~~~

Nếu mỗi người có trung bình nhiều hàng chục quan hệ KNOWS, số nhánh có thể tăng rất nhanh theo độ sâu. Đây là tăng trưởng tổ hợp theo số tầng và degree, không phải chỉ là chi phí tuyến tính theo độ dài đường đi.

Nếu use case chỉ cần tìm người ở tối đa ba bước, giới hạn đúng phạm vi:

~~~cypher
MATCH (start:Person {businessId: $personId})
MATCH (start)-[:KNOWS*1..3]->(target:Person)
RETURN DISTINCT target
~~~

Việc giới hạn độ sâu phải xuất phát từ quy tắc nghiệp vụ. Không giảm giới hạn tùy tiện nếu ứng dụng thực sự cần tìm đường dài hơn.

Nếu chỉ cần kiểm tra có tồn tại đường đi hay không, dùng EXISTS thay vì trả về mọi path:

~~~cypher
MATCH (start:Person {businessId: $personId})
RETURN EXISTS {
    MATCH (start)-[:KNOWS*1..3]->(:Person {businessId: $targetId})
} AS connected
~~~

Cách này thể hiện rõ mục tiêu kiểm tra tồn tại và tránh trả toàn bộ path cho client.

### 4.2. Chỉ rõ relationship type và hướng

Mẫu không chỉ rõ relationship type hoặc hướng có thể mở rộng sang nhiều cạnh hơn nghiệp vụ cần:

~~~cypher
MATCH (start:Person {businessId: $personId})-[relationship*1..3]-(target)
RETURN target
~~~

Nếu nghiệp vụ chỉ đi theo hướng từ người giới thiệu tới người được giới thiệu, chỉ định relationship type và hướng:

~~~cypher
MATCH (start:Person {businessId: $personId})
      -[:REFERRED_TO*1..3]->
      (target:Person)
RETURN DISTINCT target
~~~

Việc chỉ rõ type và direction thu hẹp tập cạnh có thể được duyệt. Chỉ áp dụng hướng nếu mô hình dữ liệu thực sự có ý nghĩa định hướng; không thay đổi hướng chỉ để cải thiện tốc độ rồi làm sai kết quả.

### 4.3. Bắt đầu từ node có tính chọn lọc

Nếu query bắt đầu bằng tất cả Person rồi mới lọc sâu trong graph, lượng node phải mở rộng có thể rất lớn.

Ví dụ nên bắt đầu từ một node có khóa nghiệp vụ được index:

~~~cypher
MATCH (start:Person {
    tenantId: $tenantId,
    businessId: $personId
})
MATCH (start)-[:MEMBER_OF]->(team:Team)
WHERE team.status = "ACTIVE"
RETURN team
~~~

Index trên tổ hợp tenantId và businessId giúp tìm điểm bắt đầu trong shared database. Sau đó query chỉ mở rộng từ node đó.

Nếu query cần tìm từ nhiều điểm bắt đầu, hãy đo số node đầu vào và cân nhắc lọc chúng trước khi traversal. Việc giảm số điểm bắt đầu thường hiệu quả hơn chỉ giảm một bước ở cuối graph.

### 4.4. Không materialize path khi chỉ cần node hoặc boolean

Nếu query trả path:

~~~cypher
MATCH path = (start:Person {businessId: $personId})
             -[:KNOWS*1..4]->
             (target:Person)
RETURN path
~~~

Neo4j phải giữ thông tin đường đi để trả về. Nếu ứng dụng chỉ cần danh sách node đích, trả node đích và loại bỏ trùng nếu đúng semantics:

~~~cypher
MATCH (start:Person {businessId: $personId})
      -[:KNOWS*1..4]->
      (target:Person)
RETURN DISTINCT target
~~~

DISTINCT có chi phí khử trùng lặp và có thể cần bộ nhớ. Chỉ dùng khi nghiệp vụ cần mỗi target xuất hiện một lần; nếu số path hoặc số lần kết nối là kết quả cần thiết, không được loại bỏ chúng.

## 5. Hiểu độ tăng trưởng của traversal

Giả sử một node có trung bình b relationship phù hợp ở mỗi bước. Với độ sâu d, số nhánh có thể tăng theo tổng b + b² + ... + bᵈ trong trường hợp đơn giản. Đây chỉ là mô hình ước lượng trực quan; graph thực tế có degree không đồng đều, chu trình, quy tắc uniqueness và các predicate lọc.

Ví dụ nếu mỗi node trung bình có 8 cạnh phù hợp, mở rộng tới 4 tầng có thể xem xét hàng nghìn đường đi ứng viên từ một điểm bắt đầu. Một vài node có degree đặc biệt cao còn có thể tạo ra phần lớn chi phí.

Hãy đo:

- Số node bắt đầu trước traversal.
- Số relationship được mở rộng.
- Số Rows sau từng Expand hoặc VarLengthExpand.
- Số target cuối cùng.
- Số path trung gian nếu query trả path.
- DB Hits và thời gian của operator mở rộng.

Đừng chỉ nhìn độ sâu. Một traversal ba bước trên node có degree hàng chục nghìn có thể đắt hơn traversal sáu bước trên graph thưa.

## 6. Nhận diện Cartesian product

Cartesian product xuất hiện khi hai tập pattern độc lập được kết hợp mà không có relationship hoặc điều kiện nối giữa chúng. Nếu tập A có m dòng và tập B có n dòng, phép kết hợp có thể tạo m × n dòng.

Ví dụ:

~~~cypher
MATCH (person:Person)
MATCH (team:Team)
WHERE person.status = "ACTIVE"
  AND team.region = $region
RETURN person, team
~~~

Nếu có 20.000 Person active và 500 Team ở region được chọn, query có thể tạo 10 triệu cặp Person-Team trước khi trả kết quả. Nếu nghiệp vụ muốn tìm các team mà mỗi person thực sự là thành viên, truy vấn đã thiếu relationship pattern.

Plan có thể hiển thị operator CartesianProduct. Hãy kiểm tra số Rows từ hai nhánh đầu vào và số Rows sau operator này. Đây thường là dấu hiệu rõ ràng của hai pattern rời rạc.

### 6.1. Nối các pattern bằng relationship đúng với domain

Nếu mục tiêu là lấy Team mà Person là thành viên, truy vấn nên biểu diễn quan hệ graph:

~~~cypher
MATCH (person:Person)
      -[:MEMBER_OF]->
      (team:Team)
WHERE person.status = "ACTIVE"
  AND team.region = $region
RETURN person, team
~~~

Bây giờ mỗi cặp kết quả phải có relationship MEMBER_OF thực sự. Query không tạo mọi cặp Person-Team độc lập.

Nếu có tenant boundary, thêm tenant predicate vào node và relationship theo mô hình dữ liệu:

~~~cypher
MATCH (person:Person {
    tenantId: $tenantId,
    status: "ACTIVE"
})-[membership:MEMBER_OF {
    tenantId: $tenantId
}]->(team:Team {
    tenantId: $tenantId,
    region: $region
})
RETURN person, team
~~~

Không thêm relationship chỉ để loại Cartesian product nếu nghiệp vụ thực sự cần kết hợp hai tập độc lập. Khi đó hãy biểu đạt rõ phép kết hợp và giới hạn dữ liệu đầu vào.

### 6.2. Khi cần thống kê hai tập độc lập

Nếu mục tiêu là đếm số Person active và số Team theo region, không cần tạo từng cặp Person-Team. Có thể aggregate từng tập trong subquery:

~~~cypher
CALL {
    MATCH (person:Person)
    WHERE person.status = "ACTIVE"
    RETURN count(person) AS activePeople
}
CALL {
    MATCH (team:Team)
    WHERE team.region = $region
    RETURN count(team) AS regionalTeams
}
RETURN activePeople, regionalTeams
~~~

Mỗi subquery trả một dòng tổng hợp, nên query không cần tạo tích giữa toàn bộ Person và Team.

### 6.3. Cartesian product có thể là chủ đích

Có trường hợp nghiệp vụ thật sự cần mọi tổ hợp, ví dụ tạo ma trận so sánh giữa các kịch bản và các khu vực. Khi đó Cartesian product là một phần của yêu cầu, không phải lỗi planner.

Tuy nhiên, hãy ước lượng kích thước kết quả trước khi chạy. Nếu cần mọi cặp, hãy giới hạn quy mô đầu vào, phân trang hoặc xử lý theo batch. LIMIT đặt ở cuối không nhất thiết ngăn database tạo và xử lý phần lớn tổ hợp trung gian trước khi áp dụng giới hạn.

## 7. Lọc sớm và giảm số dòng trung gian

WITH có thể giúp tách các giai đoạn của query, nhưng bản thân WITH không tự làm query nhanh hơn. Lợi ích xuất hiện khi nó đi cùng predicate, aggregation, DISTINCT hoặc LIMIT phù hợp để giảm số dòng được chuyển sang giai đoạn tiếp theo.

Ví dụ lọc Person theo tenant và trạng thái trước khi mở rộng:

~~~cypher
MATCH (person:Person {tenantId: $tenantId})
WHERE person.status = "ACTIVE"
WITH person
MATCH (person)-[:MEMBER_OF]->(team:Team)
WHERE team.status = "ACTIVE"
RETURN person, team
~~~

Nếu có index phù hợp trên tenantId/status, planner có thể giảm tập node đầu vào trước traversal. Hãy kiểm tra plan để xác nhận, vì planner có thể tự di chuyển predicate khi an toàn và phù hợp.

Không đặt LIMIT sớm nếu nó làm thay đổi semantics, ví dụ chỉ lấy 100 Person đầu tiên trong khi nghiệp vụ yêu cầu mọi Person active. Tối ưu phải giữ đúng tập kết quả.

## 8. Sửa truy vấn trong Spring Data Neo4j

Các vấn đề trong execution plan có thể bắt nguồn từ bất kỳ nơi nào tạo Cypher. Hãy kiểm tra cả repository và code gọi client.

Repository với @Query:

~~~java
import java.util.Collection;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person {
            tenantId: $tenantId,
            email: $email
        })
        RETURN person
        """)
    Collection<Person> findByTenantAndEmail(
        @Param("tenantId") String tenantId,
        @Param("email") String email
    );
}
~~~

Neo4jClient cũng cần dùng parameter binding:

~~~java
var people = neo4jClient.query("""
        MATCH (person:Person {
            tenantId: $tenantId,
            email: $email
        })
        RETURN person
        """)
    .bind(tenantId).to("tenantId")
    .bind(email).to("email")
    .fetch()
    .all();
~~~

Ở ví dụ Neo4jClient, fetch().all() trả về các record dưới dạng map; nếu cần ánh xạ thành entity/DTO, bổ sung fetchAs(...).mappedBy(...) theo kiểu kết quả mong muốn.

Parameter binding giúp tái sử dụng query plan và tách dữ liệu khỏi cấu trúc Cypher. Nó không tự loại bỏ full scan, traversal quá rộng hoặc Cartesian product. Cần tối ưu query shape và schema tương ứng.

Với Cypher-DSL, hãy kiểm tra Cypher được render cuối cùng. Đừng chỉ review biểu thức DSL vì pattern rời rạc hoặc điều kiện thiếu vẫn có thể xuất hiện trong câu query cuối.

## 9. So sánh trước và sau khi tối ưu

Giả sử query tìm Person theo email ban đầu có plan:

~~~text
ProduceResults
  Filter
    NodeByLabelScan
~~~

Sau khi tạo index và giữ predicate phù hợp, plan có thể trở thành:

~~~text
ProduceResults
  NodeIndexSeek
~~~

Đây là một thay đổi access path có thể giảm số node cần kiểm tra. Nhưng chỉ số liệu PROFILE mới cho biết mức cải thiện thực tế.

Với traversal, so sánh Rows và DB Hits ở operator Expand/VarLengthExpand trước và sau khi giới hạn đúng độ sâu, chỉ rõ relationship type hoặc giảm điểm bắt đầu.

Với Cartesian product, so sánh số Rows trước và sau operator CartesianProduct. Sau khi nối pattern bằng relationship hoặc aggregate hai nhánh độc lập, số dòng trung gian có thể giảm mạnh.

Ghi lại cùng một bộ thông tin cho mỗi lần đo:

| Thông tin | Trước tối ưu | Sau tối ưu |
| --- | --- | --- |
| Query và parameter đại diện | Ghi lại | Giữ nguyên |
| Operator chính | Scan/Expand/CartesianProduct | Seek/traversal hẹp hơn hoặc plan phù hợp |
| Rows trung gian | Số liệu PROFILE | Số liệu PROFILE |
| DB Hits | Số liệu PROFILE | Số liệu PROFILE |
| Page cache hits/misses | Nếu có | Nếu có |
| Thời gian thực thi | Đo nhiều lần | Đo nhiều lần |
| Kích thước kết quả | Số dòng và payload | Phải giữ đúng semantics |

Đo nhiều lần để giảm ảnh hưởng của cache warm-up và dao động hệ thống. Dùng dữ liệu có quy mô, phân bố degree và cardinality gần production. Không so sánh một lần chạy lạnh với một lần chạy nóng rồi kết luận index đã cải thiện query.

## 10. Quy trình chẩn đoán một query chậm

1. Lấy đúng Cypher được thực thi và parameter đại diện từ repository, Neo4jClient hoặc Cypher-DSL.
2. Xác nhận kết quả mong đợi và số dòng đầu ra hợp lý.
3. Chạy EXPLAIN để xem planner dự định dùng operator nào.
4. Chạy PROFILE trên query đọc hoặc môi trường an toàn.
5. Kiểm tra AllNodesScan, NodeByLabelScan, NodeIndexScan và khả năng dùng NodeIndexSeek.
6. Kiểm tra Expand và VarLengthExpand, số Rows sau mỗi tầng và degree của node bắt đầu.
7. Kiểm tra CartesianProduct và các pattern không có relationship/điều kiện nối.
8. Tìm predicate có thể lọc sớm mà không thay đổi semantics.
9. Thay đổi một yếu tố: index, điểm bắt đầu, độ sâu, relationship type/direction hoặc cách nối pattern.
10. PROFILE lại với cùng tham số và dữ liệu tương đương.
11. Đo cả read latency, write cost và dung lượng index nếu thay đổi schema.
12. Lưu lại query plan và số liệu để theo dõi hồi quy hiệu năng.

Nếu query chạy nhanh trên local nhưng chậm ở production, kiểm tra chênh lệch số lượng node, phân bố property, degree, index state, cache và concurrency. Execution plan phụ thuộc dữ liệu và thống kê; cùng một query có thể có chi phí khác nhau giữa hai môi trường.

## 11. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| Mọi NodeByLabelScan đều phải được thay bằng index | Scan có thể phù hợp với tập nhỏ hoặc query cần phần lớn dữ liệu |
| Có NodeIndexSeek nghĩa là query đã tối ưu | Các operator phía sau vẫn có thể mở rộng graph hoặc tạo nhiều dòng |
| Query trả ít kết quả thì chắc chắn rẻ | Có thể đã xử lý lượng dữ liệu trung gian rất lớn |
| Thêm DISTINCT luôn sửa được Cartesian product | DISTINCT chỉ loại dòng trùng sau khi các dòng đã được tạo và có thể tốn bộ nhớ |
| Thêm LIMIT ở cuối luôn giảm công việc | Operator phía trước vẫn có thể phải xử lý phần lớn input |
| Dùng WITH là query tự động nhanh hơn | WITH chỉ hữu ích khi giảm hoặc kiểm soát dòng trung gian |
| Parameter binding loại bỏ full scan | Binding bảo vệ và tái sử dụng query; index và query shape mới quyết định access path |
| Traversal càng ít tầng càng tốt trong mọi trường hợp | Độ sâu phải phản ánh đúng nghiệp vụ; cần tối ưu cả degree và điểm bắt đầu |

## 12. Bài tập tự kiểm tra

1. AllNodesScan khác NodeByLabelScan và NodeIndexSeek như thế nào?
2. Vì sao NodeIndexScan vẫn có thể đọc nhiều entry?
3. Khi nào full scan là lựa chọn hợp lý của planner?
4. Những yếu tố nào làm variable-length traversal tăng nhanh về chi phí?
5. Vì sao chỉ rõ relationship type và direction có thể giảm số nhánh được duyệt?
6. Khi nào nên trả node đích thay vì trả toàn bộ path?
7. Cartesian product tạo ra bao nhiêu dòng nếu hai đầu vào có m và n dòng?
8. Làm thế nào để thay Cartesian product bằng relationship pattern đúng domain?
9. Khi hai tập dữ liệu cần được thống kê độc lập, vì sao aggregate trong subquery hiệu quả hơn tạo mọi cặp?
10. EXPLAIN và PROFILE khác nhau ở điểm nào?
11. DB Hits có đồng nghĩa với số lần đọc đĩa không?
12. Vì sao cần đo lại query bằng cùng parameter và dữ liệu đại diện sau mỗi thay đổi?

Khi hoàn thành bài học, bạn cần đọc được plan để nhận diện scan lớn, traversal quá rộng và Cartesian product; biết chọn điểm bắt đầu, relationship pattern và cách lọc phù hợp; đồng thời chứng minh thay đổi bằng số liệu PROFILE. Đây là nền tảng để tối ưu truy vấn Cypher được gọi từ repository, Neo4jClient và các thành phần khác của Spring Data Neo4j.

## Tài liệu tham khảo

- [Neo4j Cypher Manual – Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
- [Neo4j Cypher Manual – Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual – Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual – Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/)
- [Spring Data Neo4j – Custom queries and repositories](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)

