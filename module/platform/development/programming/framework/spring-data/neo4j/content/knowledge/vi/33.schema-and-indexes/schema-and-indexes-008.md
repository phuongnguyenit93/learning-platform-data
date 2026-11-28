# Đánh đổi giữa hiệu năng đọc, chi phí ghi và dung lượng chỉ mục

Trong Neo4j, index giúp database tìm nhanh các node hoặc relationship phù hợp với điều kiện truy vấn mà không phải quét toàn bộ tập dữ liệu. Tuy nhiên, mỗi index cũng cần dung lượng lưu trữ và phải được duy trì khi dữ liệu thay đổi. Vì vậy, thêm index có thể làm truy vấn đọc nhanh hơn nhưng tăng chi phí ghi, thời gian khởi tạo schema và footprint lưu trữ.

Thiết kế schema tốt không phải là tạo index cho mọi property. Mục tiêu là chọn đúng index cho các truy vấn quan trọng, dựa trên tần suất đọc/ghi, độ chọn lọc của điều kiện, kích thước dữ liệu và kế hoạch thực thi thực tế. Bài học này tập trung vào cách đánh giá sự đánh đổi đó trong ứng dụng Spring Data Neo4j.

## 1. Index giải quyết phần nào của truy vấn graph?

Một truy vấn graph thường bắt đầu bằng việc tìm một hoặc nhiều node neo (anchor nodes), sau đó đi theo relationship để lấy phần graph cần thiết. Index có thể giúp tìm node bắt đầu nhanh hơn. Khi đã có node bắt đầu, Neo4j có thể duyệt relationship bằng cấu trúc adjacency của graph.

Ví dụ:

~~~cypher
MATCH (person:Person {email: $email})-[:MEMBER_OF]->(team:Team)
RETURN person, team
~~~

Nếu không có index phù hợp cho Person.email, database có thể phải kiểm tra nhiều node mang label Person để tìm email cần thiết. Nếu có range index phù hợp, planner có thể dùng index seek để định vị node trước khi duyệt MEMBER_OF.

Index không làm mọi bước traversal tự động nhanh hơn. Nếu truy vấn đã tìm được một node bắt đầu rất chọn lọc và chỉ duyệt một số ít relationship, index bổ sung trên các property không được dùng để lọc có thể không mang lại lợi ích.

~~~mermaid
flowchart LR
    A["Điều kiện trên Person.email"] --> B{"Có index phù hợp?"}
    B -->|Có| C["Index seek tìm node bắt đầu"]
    B -->|Không| D["Label scan và lọc property"]
    C --> E["Duyệt relationship MEMBER_OF"]
    D --> E
    E --> F["Trả kết quả graph"]
~~~

Hãy xác định phần truy vấn tốn kém trước khi tạo index. Index tối ưu bước tìm điểm bắt đầu hoặc lọc property; nó không thay thế việc thiết kế pattern traversal hợp lý.

## 2. Các loại index thường gặp trong Neo4j

Neo4j cung cấp nhiều loại index cho các kiểu truy vấn khác nhau. Với các phiên bản Neo4j 5.x hiện đại, những nhóm thường gặp gồm:

| Loại index | Dữ liệu / truy vấn phù hợp | Ghi chú |
| --- | --- | --- |
| Range index | Equality, range, so sánh, IN, prefix và sắp xếp trên property được hỗ trợ | Là lựa chọn phổ biến cho property lookup thông thường |
| Text index | Tìm chuỗi theo CONTAINS hoặc ENDS WITH | Dành cho predicate chuỗi mà range index không tối ưu |
| Full-text index | Tìm kiếm từ/cụm từ có phân tích văn bản, scoring và tokenization | Được gọi tường minh bằng full-text procedure; không tự động được Cypher planner chọn như range index |
| Point index | Truy vấn không gian như khoảng cách hoặc vùng giao nhau | Dành cho property kiểu point |
| Vector index | Tìm kiếm láng giềng gần nhất theo embedding/vector | Phục vụ similarity search, thường trả về kết quả gần đúng theo cấu hình |
| Token lookup index | Tìm node theo label hoặc relationship theo type | Neo4j tự quản lý các lookup index hệ thống này trong cấu hình thông thường |

Không chọn index chỉ theo tên loại. Hãy chọn theo predicate và kiểu property mà truy vấn thực sự dùng.

Ví dụ range index cho email:

~~~cypher
CREATE RANGE INDEX person_email IF NOT EXISTS
FOR (person:Person)
ON (person.email)
~~~

Range index hỗ trợ các phép tra cứu property phổ biến như:

~~~cypher
MATCH (person:Person)
WHERE person.email = $email
RETURN person
~~~

~~~cypher
MATCH (person:Person)
WHERE person.age >= $minimumAge
RETURN person
~~~

~~~cypher
MATCH (person:Person)
WHERE person.name STARTS WITH $prefix
RETURN person
~~~

Text index phù hợp hơn với điều kiện substring hoặc suffix:

~~~cypher
CREATE TEXT INDEX person_name_text IF NOT EXISTS
FOR (person:Person)
ON (person.name)
~~~

~~~cypher
MATCH (person:Person)
WHERE person.name CONTAINS $fragment
RETURN person
~~~

Không nên tạo text index thay cho full-text search nếu use case cần phân tích từ, xếp hạng mức độ liên quan hoặc tìm kiếm theo nhiều trường. Ngược lại, không cần full-text index chỉ để kiểm tra equality hoặc prefix đơn giản.

Ví dụ full-text index trên hai property:

~~~cypher
CREATE FULLTEXT INDEX person_fulltext IF NOT EXISTS
FOR (person:Person)
ON EACH [person.name, person.bio]
~~~

Full-text index được gọi tường minh qua procedure:

~~~cypher
CALL db.index.fulltext.queryNodes("person_fulltext", $searchText)
YIELD node, score
RETURN node, score
ORDER BY score DESC
~~~

Procedure trả về node cùng điểm liên quan. Đây là một luồng tìm kiếm khác với predicate property thông thường; hãy benchmark cả chất lượng kết quả và chi phí index population khi dữ liệu văn bản lớn.

## 3. Chọn index theo độ chọn lọc (selectivity)

Độ chọn lọc thể hiện predicate thu hẹp tập dữ liệu đầu vào đến mức nào. Một điều kiện trả về 1 node trong hàng triệu node thường chọn lọc hơn điều kiện trả về hàng trăm nghìn node.

Ví dụ:

- Person.id = $id thường rất chọn lọc nếu ID duy nhất.
- Person.email = $email thường chọn lọc nếu email gần như duy nhất.
- Person.status = "ACTIVE" có thể ít chọn lọc nếu phần lớn người dùng đều active.
- Person.country = "VN" có thể trả về một phần lớn dữ liệu nếu nhiều node cùng quốc gia.

Index trên property ít chọn lọc vẫn có thể hữu ích, đặc biệt khi kết hợp với điều kiện khác hoặc giảm số property phải đọc. Nhưng không nên mặc định index nào cũng cải thiện query. Planner có thể chọn scan nếu dự đoán chi phí scan thấp hơn index lookup cộng với việc truy cập các kết quả.

Ví dụ hai truy vấn:

~~~cypher
MATCH (person:Person)
WHERE person.email = $email
RETURN person
~~~

~~~cypher
MATCH (person:Person)
WHERE person.status = $status
RETURN person
~~~

Nếu email gần như duy nhất, range index có thể giúp giảm mạnh số node cần kiểm tra. Nếu status chỉ có hai giá trị và phần lớn node mang cùng một giá trị, index có thể không giảm đáng kể lượng dữ liệu cần xử lý.

Độ chọn lọc phụ thuộc phân bố dữ liệu thật. Đừng đánh giá dựa trên vài chục record trong môi trường phát triển rồi áp dụng nguyên xi cho production.

## 4. Composite index và thứ tự property

Composite index chứa nhiều property trên cùng một label hoặc relationship type. Nó phù hợp khi truy vấn thường xuyên lọc theo một tổ hợp điều kiện.

Ví dụ ứng dụng đa tenant thường tìm Person theo tenant và email:

~~~cypher
CREATE RANGE INDEX person_tenant_email IF NOT EXISTS
FOR (person:Person)
ON (person.tenantId, person.email)
~~~

Truy vấn tương ứng:

~~~cypher
MATCH (person:Person)
WHERE person.tenantId = $tenantId
  AND person.email = $email
RETURN person
~~~

Thứ tự property trong composite index có ý nghĩa. Hãy đặt property thường được dùng làm điều kiện dẫn đầu phù hợp với tập truy vấn. Range index composite thường khai thác hiệu quả các predicate trên các property đầu của index; khả năng seek cụ thể còn phụ thuộc tổ hợp equality/range, thứ tự property và phiên bản planner.

Ví dụ, nếu ứng dụng thường có cả hai dạng truy vấn:

~~~cypher
MATCH (person:Person)
WHERE person.tenantId = $tenantId
RETURN person
~~~

~~~cypher
MATCH (person:Person)
WHERE person.tenantId = $tenantId
  AND person.email = $email
RETURN person
~~~

Composite index (tenantId, email) có thể phục vụ cả truy vấn theo tenant và truy vấn theo tenant + email. Nếu ứng dụng chỉ tìm theo email mà không có tenantId, đừng giả định composite index này sẽ thay thế tốt index bắt đầu bằng email. Hãy kiểm tra execution plan của đúng query pattern.

Không tạo cả hai index (tenantId) và (tenantId, email) một cách tự động. Composite index có thể khiến index đơn trở nên dư thừa cho một số truy vấn, nhưng quyết định cần dựa trên plan, tần suất truy vấn và chi phí ghi.

## 5. Index có thể hỗ trợ ORDER BY

Range index có thể giúp một số truy vấn trả dữ liệu theo thứ tự property mà không cần một bước sort riêng, nếu predicate, hướng sắp xếp và cấu trúc index phù hợp.

Ví dụ:

~~~cypher
MATCH (person:Person)
WHERE person.tenantId = $tenantId
RETURN person.id, person.name
ORDER BY person.email
LIMIT 50
~~~

Một index bắt đầu bằng tenantId và tiếp theo là email có thể phù hợp với mẫu lọc và sắp xếp này:

~~~cypher
CREATE RANGE INDEX person_tenant_email IF NOT EXISTS
FOR (person:Person)
ON (person.tenantId, person.email)
~~~

Tuy nhiên, không thể kết luận rằng chỉ cần tạo index này thì Neo4j chắc chắn bỏ được sort. Planner phải có khả năng khai thác thứ tự index cho đúng predicate và order. Dùng EXPLAIN/PROFILE để xác nhận có operator sort hay không và số dòng thực tế được xử lý.

Nếu query có ORDER BY trên property khác với property index hoặc có nhiều điều kiện không tương thích, database vẫn có thể cần sort. Đừng tạo index chỉ dựa trên một đoạn Cypher mà chưa xem plan.

## 6. Index cho relationship properties

Node index thường được dùng để tìm node bắt đầu traversal. Nếu truy vấn cần lọc trực tiếp theo property của relationship, có thể cân nhắc relationship range index ở các phiên bản Neo4j hỗ trợ.

Ví dụ quan hệ PURCHASED có property purchasedAt:

~~~cypher
CREATE RANGE INDEX purchased_at IF NOT EXISTS
FOR ()-[purchase:PURCHASED]-()
ON (purchase.purchasedAt)
~~~

Truy vấn:

~~~cypher
MATCH (customer:Customer)-[purchase:PURCHASED]->(product:Product)
WHERE purchase.purchasedAt >= $from
  AND purchase.purchasedAt < $to
RETURN customer, product, purchase
~~~

Relationship index chỉ đáng cân nhắc nếu workload thực sự bắt đầu hoặc lọc theo property relationship với tần suất và quy mô đủ lớn. Nếu truy vấn luôn bắt đầu từ một Customer có ID rất chọn lọc rồi chỉ duyệt vài relationship, index trên PURCHASED.purchasedAt có thể không cần thiết.

Kiểm tra phiên bản Neo4j và cú pháp index được hỗ trợ trước khi dùng relationship index, vì khả năng và cú pháp đã thay đổi theo các phiên bản.

## 7. Constraint và index không phải cùng một mục đích

Constraint bảo vệ tính toàn vẹn dữ liệu; index tối ưu truy vấn. Một số constraint có index backing do Neo4j quản lý.

Ví dụ uniqueness constraint cho email:

~~~cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE person.email IS UNIQUE
~~~

Constraint này đảm bảo các node Person không có cùng giá trị email được đặt theo quy tắc uniqueness. Neo4j tạo và quản lý backing range index để thực thi constraint; không cần tạo thêm một range index trùng lặp cho cùng mục đích.

Phân biệt một số loại schema rule:

| Schema rule | Mục tiêu | Quan hệ với index |
| --- | --- | --- |
| Range index | Tăng tốc property lookup | Index độc lập |
| Uniqueness constraint | Bảo đảm property duy nhất | Có backing range index |
| Key constraint | Bảo đảm property tồn tại và duy nhất theo khả năng edition/phiên bản | Được hỗ trợ bởi index |
| Property existence constraint | Bảo đảm property tồn tại | Không nên giả định có backing index tra cứu |
| Property type constraint | Bảo đảm property đúng kiểu | Không đồng nghĩa có index để tăng tốc query |

Khả năng constraint phụ thuộc edition và phiên bản Neo4j. Kiểm tra tài liệu phiên bản database đang triển khai trước khi đưa constraint vào migration.

Nếu uniqueness constraint đã tạo backing index, không tạo thêm một index độc lập cùng label/property chỉ để tìm kiếm equality. Index trùng lặp tiêu tốn dung lượng và tăng công việc cập nhật.

## 8. Chi phí ghi: mỗi index cần được duy trì

Khi tạo, cập nhật hoặc xóa node/relationship, Neo4j phải duy trì các index liên quan đến label, relationship type và property bị ảnh hưởng. Vì vậy, thêm index có thể làm thao tác ghi tốn thời gian và tài nguyên hơn.

Ví dụ một node Person có bốn property được index:

- email
- status
- tenantId
- createdAt

Khi tạo Person, database cần cập nhật các index liên quan. Khi đổi email hoặc status, những index tương ứng cũng phải được cập nhật. Nếu có nhiều index trên các property ít dùng trong query, chi phí ghi tăng mà lợi ích đọc thấp.

| Thay đổi dữ liệu | Tác động index có thể phát sinh |
| --- | --- |
| Tạo node mang label có index | Thêm entry vào các index phù hợp |
| Đổi property được index | Cập nhật entry cũ và entry mới |
| Xóa node hoặc relationship được index | Gỡ entry liên quan |
| Đổi label hoặc relationship type | Thay đổi tập index áp dụng |
| Tạo index mới | Database phải scan/populate dữ liệu hiện có và duy trì index trong quá trình đó |

Index không chỉ tác động đến câu lệnh CREATE. Một workload cập nhật liên tục các property được index cũng phải trả chi phí duy trì. Hãy xem tần suất update và tỷ lệ read/write khi quyết định index.

## 9. Dung lượng lưu trữ và bộ nhớ

Mỗi index có cấu trúc dữ liệu riêng trên đĩa. Dung lượng phụ thuộc số lượng entry, độ dài giá trị, số property trong composite index, loại index và dữ liệu thực tế.

Các hệ quả cần cân nhắc:

- Index chiếm thêm dung lượng trên đĩa.
- Working set của index có thể chiếm page cache và cạnh tranh với dữ liệu graph.
- Composite index và nhiều index chồng lặp làm tăng footprint.
- Full-text và vector index có cấu trúc riêng, có thể có yêu cầu bộ nhớ/tài nguyên khác range index.
- Index population cần đọc dữ liệu hiện có và tiêu thụ tài nguyên trong lúc khởi tạo.

Không có một tỷ lệ cố định giữa kích thước index và kích thước graph. Hãy đo trên dữ liệu đại diện, theo dõi dung lượng database và page cache, rồi dự trù tăng trưởng.

Index không nhất thiết phải nằm toàn bộ trong RAM để được sử dụng, nhưng nếu working set thường xuyên được cache, truy vấn có thể giảm I/O đáng kể. Ngược lại, thêm quá nhiều index có thể làm cache pressure tăng và ảnh hưởng cả truy vấn khác.

## 10. Index population và trạng thái ONLINE

Khi tạo index trên database đã có dữ liệu, Neo4j cần populate index từ các node hoặc relationship hiện tại. Index có thể tồn tại ở trạng thái chưa sẵn sàng trong quá trình population. Không nên giả định index vừa tạo đã lập tức phục vụ query.

Có thể kiểm tra trạng thái:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties,
      state, populationPercent, owningConstraint
RETURN name, type, entityType, labelsOrTypes, properties,
       state, populationPercent, owningConstraint
ORDER BY name
~~~

Trước khi đánh giá hiệu năng query sau khi tạo index, xác nhận trạng thái index là ONLINE. Nếu index đang POPULATING, plan hoặc thời gian truy vấn có thể chưa phản ánh trạng thái hoạt động bình thường.

Tạo index trong production cần được xem như một thay đổi schema có chi phí. Với graph lớn, hãy lập kế hoạch triển khai, theo dõi tài nguyên và xác nhận trạng thái index sau migration.

## 11. Đo hiệu quả bằng EXPLAIN và PROFILE

Đừng kết luận index tốt chỉ vì truy vấn chạy nhanh hơn một lần trên máy phát triển. Hãy dùng execution plan để hiểu Neo4j đang làm gì.

EXPLAIN xây dựng kế hoạch thực thi nhưng không chạy truy vấn. PROFILE thực thi truy vấn và cung cấp số liệu thực tế của các operator. Với query ghi, PROFILE có thể thực hiện thay đổi dữ liệu; chỉ dùng trong môi trường kiểm thử hoặc với dữ liệu an toàn.

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

Một số operator thường gặp:

| Operator | Ý nghĩa tổng quát |
| --- | --- |
| NodeByLabelScan | Quét các node có label |
| NodeIndexSeek | Dùng index để tìm node theo điều kiện seek |
| NodeIndexScan | Duyệt các entry của index |
| Filter | Lọc các dòng theo predicate |
| Expand(All) | Duyệt relationship từ node đầu vào |
| Sort | Sắp xếp kết quả |
| ProduceResults | Phát kết quả cho client |

Khi so sánh trước và sau khi thêm index, chú ý:

- Operator scan có được thay bằng index seek không?
- Số dòng đầu ra của từng operator có giảm không?
- DB Hits có giảm ở các bước tìm node/lọc property không?
- Có sort hoặc expand lớn nào vẫn chiếm phần lớn chi phí không?
- Tổng thời gian và lượng dữ liệu trả về có phù hợp với mục tiêu không?

Một index seek không tự động chứng minh query tối ưu. Nếu index trả về hàng trăm nghìn node rồi tiếp tục mở rộng graph lớn, bottleneck có thể nằm ở bước sau.

## 12. Ví dụ thiết kế index theo workload

Giả sử một nền tảng quản lý thành viên có graph:

- Person(tenantId, email, status, createdAt)
- Team(tenantId, slug, name)
- Person -[:MEMBER_OF {joinedAt}]-> Team

Workload:

| Truy vấn | Tần suất giả định | Mục tiêu |
| --- | --- | --- |
| Tìm Person theo tenant và email | Rất cao | Lookup nhanh, kết quả gần như duy nhất |
| Liệt kê Person theo tenant và status | Cao | Lọc theo tenant/status |
| Liệt kê Team theo tenant và slug | Trung bình | Lookup theo khóa nghiệp vụ |
| Tìm membership mới nhất của một Person | Cao | Traversal từ Person, sắp xếp theo joinedAt |
| Tìm kiếm tên chứa một cụm từ | Thấp | Text search |

Một tập index ban đầu có thể là:

~~~cypher
CREATE RANGE INDEX person_tenant_email IF NOT EXISTS
FOR (person:Person)
ON (person.tenantId, person.email);

CREATE RANGE INDEX person_tenant_status IF NOT EXISTS
FOR (person:Person)
ON (person.tenantId, person.status);

CREATE RANGE INDEX team_tenant_slug IF NOT EXISTS
FOR (team:Team)
ON (team.tenantId, team.slug);

CREATE TEXT INDEX person_name_text IF NOT EXISTS
FOR (person:Person)
ON (person.name);
~~~

Nếu tenantId + email phải duy nhất trong phạm vi tenant, cân nhắc uniqueness constraint phù hợp với khả năng composite uniqueness của phiên bản Neo4j đang dùng. Constraint vừa bảo vệ dữ liệu vừa cung cấp backing index.

Ví dụ composite uniqueness constraint trên hai property:

~~~cypher
CREATE CONSTRAINT person_tenant_email_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE (person.tenantId, person.email) IS UNIQUE
~~~

Constraint này bảo đảm tổ hợp tenantId và email là duy nhất theo semantics của Neo4j; nó không có nghĩa riêng từng property phải duy nhất trên toàn graph.

Với membership, nếu truy vấn luôn bắt đầu từ Person theo ID rồi duyệt các relationship MEMBER_OF, index trên joinedAt của relationship có thể không cần thiết. Nếu workload có truy vấn tìm membership theo khoảng thời gian trên toàn graph, hãy đo và cân nhắc relationship index.

Tập index trên chỉ là giả thuyết ban đầu. Hãy chạy query representative, xem plan và benchmark trên dữ liệu có phân bố gần production. Có thể một index composite (tenantId, status, createdAt) phục vụ tốt hơn một số truy vấn, hoặc một index đơn trở nên dư thừa; chỉ giữ sau khi đã đo.

## 13. Dấu hiệu index dư thừa hoặc không hiệu quả

Một index đáng được xem xét lại khi:

- Không có truy vấn quan trọng nào dùng đến nó.
- Có một composite index khác đã bao phủ cùng pattern lọc.
- Property có cardinality thấp và query vẫn đọc phần lớn dữ liệu.
- Index được tạo cho một query hiếm, trong khi workload ghi rất lớn.
- Index gần như trùng với backing index của uniqueness constraint.
- Index làm tăng đáng kể dung lượng hoặc thời gian ghi mà không cải thiện SLA đọc.

Không xóa index chỉ vì một lần PROFILE không dùng nó. Planner có thể không chọn index do thống kê, tham số hoặc quy mô dữ liệu hiện tại. Hãy kiểm tra nhiều query shape, thống kê và workload thực tế trước khi loại bỏ.

Có thể xem danh sách index và constraint bằng:

~~~cypher
SHOW INDEXES;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Khi đã xác nhận index không còn cần thiết, xóa bằng tên:

~~~cypher
DROP INDEX person_name_text IF EXISTS
~~~

Không drop index đang được constraint sở hữu. Với backing index của constraint, hãy quản lý constraint theo đúng quy trình schema thay vì cố xóa index nội bộ.

## 14. Quy trình chọn index cho ứng dụng SDN

1. Thu thập các query pattern thực tế từ repository, @Query, Cypher-DSL và Neo4jClient.
2. Ghi lại tần suất đọc, ghi, update và yêu cầu latency của từng query.
3. Xác định label/relationship type, property predicate, sort và số dòng kết quả.
4. Kiểm tra schema hiện tại để tránh tạo index trùng constraint hoặc index đã có.
5. Chọn loại index theo predicate: range, text, full-text, point hoặc vector.
6. Đánh giá độ chọn lọc và thứ tự property của composite index.
7. Tạo index/constraint bằng migration hoặc quy trình schema có kiểm soát.
8. Chờ index ONLINE và xác minh trạng thái.
9. Dùng EXPLAIN/PROFILE để so sánh operator, DB Hits và số dòng.
10. Benchmark cả đọc lẫn ghi trên dữ liệu đại diện.
11. Theo dõi dung lượng, page cache và chi phí cập nhật sau triển khai.
12. Loại bỏ index dư thừa sau khi có bằng chứng từ workload.

Trong Spring Data Neo4j, annotation mapping entity không có nghĩa mọi property sẽ tự được index. Hãy quản lý index và constraint bằng schema migration hoặc công cụ quản trị schema của dự án. Không phụ thuộc vào việc khởi động ứng dụng để tự tạo toàn bộ index production mà không có kế hoạch triển khai.

## 15. Bài tập tự kiểm tra

1. Vì sao index giúp đọc nhanh hơn nhưng có thể làm ghi chậm hơn?
2. Khi nào range index phù hợp hơn text index hoặc full-text index?
3. Độ chọn lọc của property ảnh hưởng thế nào đến quyết định dùng index?
4. Vì sao thứ tự property trong composite index quan trọng?
5. Uniqueness constraint có quan hệ gì với backing range index?
6. Vì sao không nên tạo index trùng với index mà constraint đã quản lý?
7. Trạng thái ONLINE của index cho biết điều gì?
8. EXPLAIN khác PROFILE ở điểm nào?
9. Vì sao một truy vấn có NodeIndexSeek vẫn có thể chậm?
10. Khi nào relationship property index có thể hữu ích?
11. Những chỉ số nào cần so sánh khi benchmark trước và sau khi thêm index?
12. Vì sao không nên tạo index cho mọi property của entity?

Khi hoàn thành bài học, bạn cần lựa chọn index theo query workload và độ chọn lọc, dự đoán được chi phí duy trì khi ghi, kiểm tra footprint lưu trữ và xác minh lợi ích bằng execution plan. Đây là cách cân bằng hiệu năng đọc, chi phí ghi và dung lượng index trong ứng dụng Spring Data Neo4j.

## Tài liệu tham khảo

- [Neo4j Manual – Indexes for search performance](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Manual – Range indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/using-indexes/)
- [Neo4j Manual – Indexes and query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
- [Neo4j Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Spring Data Neo4j – Object mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)

