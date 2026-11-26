# Chế độ stream, stats, mutate và write của thuật toán khi được hỗ trợ

Khi phân tích đồ thị bằng Neo4j, chúng ta có thể muốn **xem thử điểm xếp hạng của từng node**, **xem thống kê chung**, **dùng kết quả làm đầu vào cho thuật toán tiếp theo**, hoặc **lưu kết quả để ứng dụng đọc lâu dài**. Cùng một thuật toán có thể đáp ứng những mục tiêu đó bằng các **chế độ thực thi (execution modes)** khác nhau: `stream`, `stats`, `mutate` và `write`.

Bài học thuộc chương **Thuật toán đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng property graph, Cypher, index/constraint, Java Driver, Spring Data Neo4j và các kỹ thuật vận hành Neo4j. Trong phần thuật toán, cần phân biệt **Neo4j Database** (dữ liệu gốc, được lưu bền vững) với **Neo4j Graph Data Science – GDS** (thư viện thuật toán và đồ thị được chiếu vào bộ nhớ). Việc chọn chế độ quyết định **kết quả được trả ở đâu, có được lưu không và tác động đến hệ thống là gì**.

> **Phạm vi:** Những tên thủ tục `gds.*` trong bài yêu cầu **Graph Data Science** tương thích đã được cài đặt, cấp quyền và có tài nguyên phù hợp. GDS là thư viện riêng, không phải mọi bản Neo4j đều có sẵn. Hỗ trợ từng mode, tùy chọn và trường `YIELD` **phụ thuộc thuật toán và phiên bản GDS**. Ví dụ dùng PageRank vì thuật toán này hỗ trợ đủ bốn chế độ trong tài liệu GDS hiện hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả luồng **Neo4j Database → GDS named graph → thuật toán → kết quả**.
2. Phân biệt chính xác bốn chế độ `stream`, `stats`, `mutate` và `write`.
3. Chạy cùng thuật toán PageRank ở bốn chế độ và xác minh vị trí lưu kết quả.
4. Giải thích vì sao `mutate` không tự cập nhật dữ liệu gốc, còn `write` không tự đồng bộ lại named graph đã chiếu.
5. Kiểm tra mode có được một thuật toán hỗ trợ trước khi gọi thủ tục.
6. Chọn mode phù hợp với phân tích tạm thời, pipeline nhiều thuật toán và ứng dụng Java/Spring Data Neo4j.

## 2. Hai lớp đồ thị cần phân biệt

Trong Neo4j Database, node và relationship được lưu thành các đối tượng dữ liệu thực. Câu Cypher như `MATCH (p:Person)-[:FOLLOWS]->(other)` truy vấn trực tiếp các đối tượng đó.

Phần lớn thuật toán GDS chạy trên một **named graph** đã được **project** (chiếu) từ database vào bộ nhớ và quản lý trong **GDS Graph Catalog**. Named graph chọn những label, relationship type và thuộc tính cần cho thuật toán. Nó thường phản ánh dữ liệu tại thời điểm chiếu, **không phải bản sao tự động cập nhật liên tục** khi database thay đổi.

~~~mermaid
flowchart TD
    DB["Neo4j Database<br/>node, relationship, property lưu bền vững"]
    P["Chiếu đồ thị (graph projection)"]
    G["GDS named graph<br/>trong bộ nhớ / Graph Catalog"]
    A["Thuật toán PageRank"]
    S["stream: nhiều hàng điểm số"]
    T["stats: một hàng thống kê"]
    M["mutate: thêm thuộc tính vào named graph"]
    W["write: ghi thuộc tính vào Neo4j Database"]
    DB --> P --> G --> A
    A --> S
    A --> T
    A --> M --> G
    A --> W --> DB
~~~

Tên mode **không cho biết độ chính xác của thuật toán**. Bốn mode đều thực hiện phép tính theo cấu hình thuật toán; khác biệt trọng tâm là **cách xuất và lưu kết quả**.

## 3. So sánh nhanh bốn chế độ

| Mode | Đầu ra trực tiếp | Có thay đổi GDS named graph? | Có ghi vào Neo4j Database? | Mục đích thường gặp |
|---|---|---|---|---|
| `stream` | Nhiều hàng, thường là `nodeId`/`score` hoặc cặp node | Không | Không | Xem và xử lý kết quả bằng Cypher/ứng dụng |
| `stats` | **Một hàng** thống kê, chẳng hạn phân bố điểm và thời gian tính | Không | Không | Đánh giá phân bố, kiểm tra cấu hình hoặc hiệu năng |
| `mutate` | **Một hàng** thống kê; kết quả được thêm vào named graph | **Có** | Không | Ghép nhiều thuật toán trong GDS |
| `write` | **Một hàng** thống kê; kết quả được ghi xuống database | Không tự cập nhật projection | **Có** | Lưu điểm/nhãn quan hệ để ứng dụng truy vấn lâu dài |

**Chú ý:** mỗi thuật toán có thể chỉ cung cấp **một số mode**. Với thuật toán trả node score như PageRank, `mutate`/`write` thường ghi **node property**; với thuật toán tìm độ tương tự có thể ghi **relationship** hoặc thuộc tính relationship. Hãy xem tài liệu riêng của thuật toán, không suy từ PageRank rằng mọi thuật toán đều trả `nodeId, score` hay nhận `mutateProperty`/`writeProperty`.

Một cách ghi nhớ:

- **`stream`:** “Cho tôi xem kết quả từng phần tử.”
- **`stats`:** “Cho tôi bức tranh tổng thể.”
- **`mutate`:** “Đưa kết quả vào đồ thị GDS để xử lý tiếp.”
- **`write`:** “Lưu kết quả về Neo4j Database để các truy vấn và ứng dụng sử dụng.”

## 4. Chuẩn bị môi trường và đồ thị thực hành

### 4.1. Kiểm tra GDS đã được cài đặt

Trên Neo4j Browser hoặc một công cụ chạy Cypher, kiểm tra:

~~~cypher
RETURN gds.version() AS gdsVersion;
~~~

Để xem chính xác các mode PageRank có trên DBMS hiện tại:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'gds.pageRank.'
RETURN name
ORDER BY name;
~~~

Nếu GDS chưa được cài, không có quyền gọi thủ tục hoặc phiên bản không tương thích, các câu lệnh `gds.*` có thể không chạy. Không sửa quyền của tài khoản ứng dụng hoặc triển khai plugin khi chưa được phép; dùng một môi trường GDS thực hành đã được cấp quyền.

### 4.2. Tạo dữ liệu nhỏ, xác định được kết quả liên kết

Để tránh đụng dữ liệu nghiệp vụ, ví dụ dùng label riêng `ModePerson` và chạy trong **database thử nghiệm**. Các quan hệ đều có hướng.

~~~cypher
CREATE CONSTRAINT mode_person_id_unique IF NOT EXISTS
FOR (p:ModePerson)
REQUIRE p.personId IS UNIQUE;
~~~

~~~cypher
MERGE (a:ModePerson {personId: 'A'})
MERGE (b:ModePerson {personId: 'B'})
MERGE (c:ModePerson {personId: 'C'})
MERGE (d:ModePerson {personId: 'D'})
MERGE (e:ModePerson {personId: 'E'})
MERGE (a)-[:FOLLOWS]->(b)
MERGE (a)-[:FOLLOWS]->(c)
MERGE (b)-[:FOLLOWS]->(c)
MERGE (c)-[:FOLLOWS]->(a)
MERGE (c)-[:FOLLOWS]->(d)
MERGE (d)-[:FOLLOWS]->(c)
MERGE (e)-[:FOLLOWS]->(d);
~~~

~~~mermaid
flowchart LR
    A((A)) -->|FOLLOWS| B((B))
    A --> C((C))
    B --> C
    C --> A
    C --> D((D))
    D --> C
    E((E)) --> D
~~~

Sơ đồ chỉ giúp hình dung; **danh sách cạnh là nguồn xác định đồ thị mẫu**. Nếu chạy thêm các lệnh ngoài bài, hãy kiểm tra lại graph trước khi suy luận thứ hạng.

Kiểm tra dữ liệu nguồn:

~~~cypher
MATCH (p:ModePerson)
WITH count(p) AS nodes
MATCH (:ModePerson)-[r:FOLLOWS]->(:ModePerson)
RETURN nodes, count(r) AS relationships;
// Trên database thực hành chỉ có dữ liệu mẫu: nodes = 5, relationships = 7
~~~

### 4.3. Project một GDS named graph

~~~cypher
CALL gds.graph.project(
    'modeLessonGraph',
    'ModePerson',
    'FOLLOWS'
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Với đúng dữ liệu mẫu, `nodeCount = 5` và `relationshipCount = 7`. Cú pháp trên là **native projection** đơn giản: chọn node theo label và relationship theo type; với bài toán thực tế có thể dùng **Cypher projection** để định nghĩa tập dữ liệu linh hoạt hơn.

Graph có tên `modeLessonGraph` sẽ nằm trong bộ nhớ của GDS. Nếu cùng tên đã tồn tại trong catalog, projection mới có thể thất bại; kiểm tra trước:

~~~cypher
CALL gds.graph.list('modeLessonGraph')
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Trong bài thực hành, nên tạo projection **một lần** và dùng cùng tên trong các bước tiếp theo. Không cần project lại trước **mỗi lần** chạy mode, trừ khi cố ý cập nhật dữ liệu đầu vào hoặc muốn loại bỏ các thuộc tính đã `mutate`.

## 5. `stream` — xem kết quả chi tiết mà không ghi dữ liệu

`stream` trả kết quả trực tiếp cho Cypher dưới dạng **các hàng**. Với PageRank, mỗi node có một `nodeId` và một `score`. Hàm `gds.util.asNode(nodeId)` giúp truy cập node gốc trong database để lấy khóa đọc được.

~~~cypher
CALL gds.pageRank.stream('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId,
       score
ORDER BY score DESC, personId ASC;
~~~

Kết quả có **tối đa năm hàng node** trong graph mẫu. Điểm số là kết quả phép tính PageRank; không nên tự áp một giá trị cố định nếu chưa chạy truy vấn, vì chúng còn phụ thuộc cấu hình, hội tụ và phiên bản GDS.

`stream` phù hợp khi:

- Cần lấy danh sách **top N** node quan trọng để hiển thị hoặc phân tích tức thời.
- Muốn nối kết quả với các thuộc tính khác của Neo4j để tạo báo cáo.
- Cần kiểm tra chất lượng dữ liệu và thứ hạng **trước khi quyết định lưu**.
- Ứng dụng Java Driver chỉ muốn đọc kết quả mà không cập nhật graph.

Ví dụ lấy ba người có điểm cao nhất:

~~~cypher
CALL gds.pageRank.stream('modeLessonGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC, personId ASC
LIMIT 3;
~~~

**Bẫy thường gặp:** `LIMIT 3` giới hạn **số hàng trả về sau khi tính**, không mặc nhiên khiến PageRank chỉ xử lý ba node. Thuật toán vẫn cần tính trên phần graph được chọn. Với graph lớn, streaming tất cả kết quả qua mạng có thể tốn RAM/băng thông ở client; chỉ lấy những cột cần thiết, phân trang hoặc cân nhắc mode khác tùy nghiệp vụ.

`stream` không tạo thuộc tính mới trên node gốc. Sau khi chạy `stream`, truy vấn `MATCH (p:ModePerson) RETURN p.pageRankScore` không tự xuất hiện điểm PageRank, trừ khi thuộc tính đó đã được ghi từ trước bởi thao tác khác.

## 6. `stats` — đọc thống kê tổng hợp của thuật toán

`stats` cũng **chạy phép tính**, nhưng thay vì trả một hàng cho mỗi node, nó trả **một hàng thống kê**. Các trường có thể gồm phân bố điểm, số vòng lặp, trạng thái hội tụ và thời gian tính, tùy thuật toán.

~~~cypher
CALL gds.pageRank.stats('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20
})
YIELD ranIterations, didConverge, computeMillis, centralityDistribution
RETURN ranIterations,
       didConverge,
       computeMillis,
       centralityDistribution.min AS minScore,
       centralityDistribution.max AS maxScore;
~~~

Ý nghĩa một số trường PageRank:

| Trường | Cách hiểu |
|---|---|
| `ranIterations` | Số vòng lặp thuật toán đã chạy trong lần gọi này |
| `didConverge` | Thuật toán có đạt điều kiện hội tụ được cấu hình hay không |
| `computeMillis` | Thời gian dành cho giai đoạn tính toán mà procedure báo cáo; không nhất thiết bằng độ trễ end-to-end |
| `centralityDistribution` | Thông tin phân bố điểm trung tâm, như min/max và các thống kê khác được hỗ trợ |

`stats` **không trả** bảng `personId → score` và **không ghi** thuộc tính vào named graph hoặc Neo4j Database. Nếu muốn tra điểm một node cụ thể, hãy dùng `stream`, `mutate` hoặc `write` theo nơi cần đọc kết quả.

**Không nhầm `stats` với câu lệnh rẻ chỉ đọc metadata:** nó có thể phải thực thi toàn bộ thuật toán để tạo thống kê. Trên graph lớn, `stats` vẫn tiêu tốn CPU và bộ nhớ.

### Dùng `stats` để thử cấu hình

Ví dụ, chạy lại với `maxIterations` khác nhau, giữ nguyên named graph:

~~~cypher
CALL gds.pageRank.stats('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 50,
    tolerance: 0.0000001
})
YIELD ranIterations, didConverge, centralityDistribution
RETURN ranIterations, didConverge,
       centralityDistribution.max AS maxScore;
~~~

Thay `maxIterations` hoặc `tolerance` có thể thay kết quả hội tụ. Khi so sánh các mode, dùng **cùng cấu hình** nếu muốn các điểm PageRank có thể đối chiếu với nhau.

## 7. `mutate` — ghi kết quả vào **GDS named graph**

`mutate` tính thuật toán rồi đưa kết quả vào **đồ thị trong bộ nhớ của GDS**, thường dưới tên một node property chỉ định bởi `mutateProperty`. Trên ví dụ PageRank:

~~~cypher
CALL gds.pageRank.mutate('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20,
    mutateProperty: 'pageRankMemory'
})
YIELD nodePropertiesWritten, mutateMillis
RETURN nodePropertiesWritten, mutateMillis;
~~~

Nếu năm node đều có kết quả, `nodePropertiesWritten` dự kiến là **5**. Đây là số thuộc tính ghi vào **projection**, **không phải** số node vừa được tạo hoặc số thuộc tính trong Neo4j Database.

Để kiểm tra điểm đã được thêm vào named graph:

~~~cypher
CALL gds.graph.nodeProperty.stream(
    'modeLessonGraph',
    'pageRankMemory'
)
YIELD nodeId, propertyValue
RETURN gds.util.asNode(nodeId).personId AS personId,
       propertyValue AS pageRankScore
ORDER BY pageRankScore DESC, personId;
~~~

Trong khi đó, query vào database:

~~~cypher
MATCH (p:ModePerson)
RETURN p.personId AS personId,
       p.pageRankMemory AS dbProperty
ORDER BY personId;
~~~

**Nếu trước đó chưa ai ghi thuộc tính `pageRankMemory` vào database**, cột `dbProperty` sẽ là `null`: `mutate` **không** tự chuyển kết quả từ bộ nhớ GDS xuống Neo4j Database.

`mutate` đặc biệt phù hợp cho **pipeline nhiều thuật toán**. Ví dụ, chạy PageRank rồi sử dụng thuộc tính `pageRankMemory` làm feature của một thuật toán GDS hỗ trợ `nodeProperties`/`featureProperties`, không cần ghi dữ liệu trung gian xuống database và project lại.

### Những lưu ý quan trọng với `mutate`

1. **Tên thuộc tính không được có sẵn trên projected graph** đối với phép mutate theo tài liệu GDS. Chạy lại cùng mode với cùng `mutateProperty` có thể gây lỗi; hãy dùng tên khác hoặc chủ động loại thuộc tính/cấu trúc cũ trong môi trường thực hành.
2. **Tốn bộ nhớ GDS:** named graph sẽ giữ thêm kết quả; với vector embedding hoặc nhiều thuật toán, phần tăng thêm có thể lớn.
3. **Vòng đời giới hạn:** named graph thường tồn tại trong Graph Catalog cho đến khi bị drop, database/DBMS dừng hoặc tài nguyên được giải phóng theo cơ chế của hệ thống. Nó không phải bản dữ liệu bền vững thay cho Neo4j Database.
4. **Không tác động tự động đến DB:** truy vấn Cypher thường hoặc ứng dụng Spring Data Neo4j đọc node từ database sẽ không thấy property chỉ tồn tại trong projection.

## 8. `write` — lưu kết quả về **Neo4j Database**

`write` tính thuật toán trên named graph rồi ghi kết quả về database. Với PageRank, chỉ định thuộc tính đích bằng `writeProperty`:

~~~cypher
CALL gds.pageRank.write('modeLessonGraph', {
    dampingFactor: 0.85,
    maxIterations: 20,
    writeProperty: 'pageRankDatabase'
})
YIELD nodePropertiesWritten, writeMillis
RETURN nodePropertiesWritten, writeMillis;
~~~

Để xác nhận dữ liệu đã được **ghi bền vững** vào các node `ModePerson`:

~~~cypher
MATCH (p:ModePerson)
RETURN p.personId AS personId,
       p.pageRankDatabase AS pageRankScore
ORDER BY pageRankScore DESC, personId;
~~~

Khác với `mutate`, thuộc tính `pageRankDatabase` hiện nằm trên **node của database**. Các truy vấn Cypher thông thường, Java Driver và Spring Data Neo4j có thể đọc được nó theo quyền và mapping ứng dụng. Nếu mô hình domain của Spring Data Neo4j cần đưa trường này vào entity, phải cập nhật mapping/schema ứng dụng có chủ đích; `write` không tự sửa lớp Java.

### `write` không tự cập nhật named graph

Sau `write`, projection `modeLessonGraph` có thể **chưa có** property `pageRankDatabase`, vì nó được tạo trước khi `write` diễn ra. Do đó:

- `MATCH (p:ModePerson) RETURN p.pageRankDatabase`: đọc được giá trị từ **database**.
- `CALL gds.graph.nodeProperty.stream('modeLessonGraph', 'pageRankDatabase')`: có thể báo **không tìm thấy property trong projection**.
- Nếu thuật toán GDS tiếp theo cần `pageRankDatabase` làm input trong memory, phải **project lại** graph với thuộc tính phù hợp, hoặc dùng `mutate` trong pipeline ngay từ đầu.

**Cảnh báo ghi dữ liệu:** nếu thuộc tính `pageRankDatabase` đã tồn tại trên các node, `write` có thể thay thế giá trị theo kết quả hiện tại. Dùng tên property phù hợp, thống nhất quy trình làm mới dữ liệu và kiểm thử trên bản sao trước khi ghi trong production.

GDS có thể sử dụng **các transaction riêng** cho giai đoạn ghi kết quả; đừng mặc định rằng toàn bộ một lần chạy `write` có thể rollback như một cập nhật Cypher đơn lẻ. Khi xảy ra lỗi giữa quá trình ghi, cần đối chiếu trạng thái cuối của dữ liệu đích, chính sách chạy lại và tài liệu transaction handling của phiên bản đang dùng.

## 9. Chạy thử bốn mode theo đúng thứ tự

Quy trình khuyến nghị để học và giảm tác động không mong muốn:

1. **Project graph:** chạy `gds.graph.project` và xác nhận số node/relationship đúng dữ liệu nguồn.
2. **`stream`:** kiểm tra danh sách node và thứ hạng; không có side effect lên graph.
3. **`stats`:** xem mức độ hội tụ, phân bố điểm và thời gian tính; kiểm tra cấu hình thuật toán.
4. **`mutate`:** lưu score vào `pageRankMemory` trong GDS graph rồi đọc lại qua `gds.graph.nodeProperty.stream`.
5. **`write`:** chỉ sau khi xác nhận nhu cầu, ghi score vào `pageRankDatabase` của node gốc; kiểm tra lại bằng `MATCH`.

Các bước `stream`, `stats`, `mutate`, `write` là **những lần chạy thuật toán riêng biệt**. Gọi `write` sau `mutate` không có nghĩa `write` chỉ chuyển lại kết quả đã tính trước; procedure thường **tính lại thuật toán** với cấu hình được truyền. Nếu thay `dampingFactor` hoặc `maxIterations`, điểm của hai bước có thể khác nhau.

### Kiểm tra sau từng bước

| Thời điểm | Named graph có `pageRankMemory`? | Database có `pageRankDatabase`? |
|---|---|---|
| Vừa project | Không | Không, nếu DB ban đầu chưa có |
| Sau `stream` | Không | Không |
| Sau `stats` | Không | Không |
| Sau `mutate` | **Có** | Không |
| Sau `write` | **Có** | **Có** |

Bảng giả định ví dụ chạy lần đầu trên dữ liệu thử chưa có các property đó và không có tác vụ ngoài bài cùng thay đổi trạng thái.

## 10. Chế độ nào được hỗ trợ? Đừng suy đoán từ tên thuật toán

Cú pháp tổng quát khi mode được cung cấp:

~~~cypher
CALL gds.<algorithm>.<executionMode>(
    'namedGraph',
    { /* cấu hình riêng của thuật toán và mode */ }
)
YIELD ...;
~~~

Đây là **mẫu minh họa**, không phải một câu Cypher hoàn chỉnh để chạy nguyên văn. Một số thuật toán hỗ trợ đủ bốn mode, một số chỉ hỗ trợ một phần. Những thuật toán trả kết quả khác loại (node score, community ID, similarity relationship, đường đi) có **trường `YIELD`, tính chất dữ liệu và cấu hình mutate/write khác nhau**.

Khi bắt đầu với một thuật toán mới:

1. Mở trang tài liệu của **chính thuật toán đó**, tìm phần **Syntax** và bảng **modes**.
2. Kiểm tra **`SHOW PROCEDURES`** trên máy chủ thực tế để biết những tên thủ tục nào đã được nạp.
3. Kiểm tra **yêu cầu graph**: có hỗ trợ đồ thị có hướng không, có cần weight property không, kiểu property nào, có hỗ trợ lọc label/relationship type không.
4. Đọc cấu hình bắt buộc của mode, chẳng hạn `mutateProperty` hay `writeProperty` cho thuật toán tạo node score.
5. Đọc **trường trả về `YIELD`**. Đừng dùng `YIELD nodeId, score` cho một thuật toán chỉ xuất relationship hoặc thống kê.

Ví dụ kiểm tra PageRank:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name IN [
    'gds.pageRank.stream',
    'gds.pageRank.stats',
    'gds.pageRank.mutate',
    'gds.pageRank.write'
]
RETURN name
ORDER BY name;
~~~

Nếu một tên không xuất hiện hoặc người dùng không có quyền chạy, hãy đọc thông báo lỗi, kiểm tra phiên bản/quyền và tài liệu triển khai. Đừng tự thay thế bằng mode khác vì **side effect và kiểu kết quả có thể hoàn toàn khác**.

## 11. Ước lượng bộ nhớ, quan sát thời gian và tiến độ

Chạy thuật toán trên graph lớn có thể đòi hỏi nhiều bộ nhớ, đặc biệt khi `mutate` cần giữ kết quả trong projection hoặc `stream` trả rất nhiều hàng qua mạng. GDS có các procedure `estimate` cho những mode được hỗ trợ. Ví dụ:

~~~cypher
CALL gds.pageRank.write.estimate('modeLessonGraph', {
    writeProperty: 'pageRankDatabase',
    maxIterations: 20,
    dampingFactor: 0.85
})
YIELD nodeCount, relationshipCount, requiredMemory
RETURN nodeCount, relationshipCount, requiredMemory;
~~~

`estimate` giúp xem yêu cầu bộ nhớ trước khi chạy, **không thực thi thuật toán PageRank và không ghi score**. Các ước lượng là công cụ lập kế hoạch tài nguyên, không thay thế việc quan sát RAM, CPU, runtime và tác động đến tải ghi thật.

Với PageRank:

| Thông tin | Đọc ở đâu? | Ý nghĩa và giới hạn |
|---|---|---|
| `computeMillis` | `stats`/`mutate`/`write` khi có | Thời gian pha tính của GDS, không gồm mọi chi phí mạng/client |
| `mutateMillis` | `mutate` khi có | Thời gian cập nhật projection |
| `writeMillis` | `write` khi có | Thời gian ghi kết quả xuống database theo báo cáo procedure |
| `nodePropertiesWritten` | `mutate`/`write` của PageRank | Số property kết quả được ghi; cần phân biệt **đích ghi** |
| `ranIterations`, `didConverge` | Các mode có thống kê | Số vòng lặp và mức hội tụ cho cấu hình đã chạy |
| Số hàng stream | `stream` | Số node/pair/path trong kết quả, không nhất thiết số node gốc duy nhất |

Nếu thư viện/phiên bản cung cấp `jobId`, `logProgress` và các cơ chế tiến độ, hãy dùng chúng để theo dõi job chạy lâu. Cần phân biệt **tiến độ thuật toán**, **tiến độ ghi** và **tiến độ truyền kết quả về client**.

## 12. Chọn mode theo tình huống nghiệp vụ

| Nhu cầu | Chọn ban đầu | Vì sao |
|---|---|---|
| Tính thử PageRank trên graph người theo dõi và trả top 10 | `stream` | Không cần ghi và có thể lọc/sắp xếp ngay trong Cypher |
| Xem phân bố score, mức hội tụ, thời gian tính | `stats` | Trả thống kê gọn, không cần toàn bộ node score |
| Chạy PageRank, sau đó dùng score làm thuộc tính đầu vào cho thuật toán GDS khác | `mutate` | Giữ kết quả trong named graph để xử lý tiếp |
| Ứng dụng Java/Spring Data Neo4j cần đọc điểm PageRank bằng `MATCH` mỗi ngày | `write` | Kết quả nằm trong Neo4j Database, có thể truy vấn lại |
| Chỉ cần lưu kết quả của một số node để báo cáo | `stream` rồi ghi có chọn lọc bằng ứng dụng/Cypher nếu phù hợp | Giảm nhu cầu ghi toàn bộ khi chỉ dùng ít kết quả |
| Chạy nhiều thuật toán, chỉ cuối pipeline mới cần persist | `mutate` ở các bước trung gian, sau đó xuất/ghi kết quả cần thiết | Giảm số lần ghi trung gian và project lại |

### Ví dụ với Java Driver và Spring Data Neo4j

- **Java Driver:** có thể chạy `gds.pageRank.stream` và đọc các hàng `personId/score` từ `Result`; khi dữ liệu rất lớn, phải quản lý thời gian đọc, network và memory của client.
- **Spring Data Neo4j:** truy vấn domain bình thường chỉ đọc thuộc tính **đã có trên Neo4j Database**. Nếu ứng dụng cần điểm PageRank như một property của entity, cần tính đến `write`, quyền ghi và mapping entity.
- **Pipeline phân tích:** nếu chỉ GDS dùng score cho thuật toán kế tiếp, `mutate` tránh việc ghi DB rồi project lại; đừng ghi quá sớm chỉ để dữ liệu tạm xuất hiện trong entity Java.

Ví dụ truy vấn ứng dụng sau khi đã chạy `write`:

~~~cypher
MATCH (p:ModePerson)
WHERE p.pageRankDatabase IS NOT NULL
RETURN p.personId AS personId, p.pageRankDatabase AS score
ORDER BY score DESC, personId
LIMIT 10;
~~~

Với nhiều lần chạy theo kỳ, hãy quy định **lúc nào cập nhật score, phiên bản thuật toán nào, thuộc tính nào lưu, và người dùng ứng dụng có được nhìn thấy dữ liệu trong lúc cập nhật hay không**. Đây là yêu cầu vận hành riêng của việc persist.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
|---|---|---|
| “`stream` chỉ chạy trên các hàng sau `LIMIT`” | Thuật toán có thể tính toàn graph, `LIMIT` giới hạn hàng trả | Ước lượng tài nguyên trên graph đã chọn |
| “`stats` lấy nhanh thống kê đã có từ lần `stream`” | `stats` thường chạy thuật toán riêng | Cân nhắc chi phí tính và cấu hình giống nhau |
| “`mutate` đã lưu vào DB” | Nó cập nhật **named graph trong bộ nhớ** | Đọc bằng GDS graph property stream; dùng `write` nếu cần DB |
| “`write` đã thêm property vào projection” | Named graph không tự đồng bộ DB sau write | Project lại hoặc dùng mutate nếu cần tiếp tục trong GDS |
| “Mọi thuật toán có bốn mode” | Mode và `YIELD` tùy thuật toán/phiên bản | Kiểm tra Syntax và `SHOW PROCEDURES` |
| “Chạy lại mutate cùng tên luôn ổn” | Mutate property có thể đã tồn tại và gây lỗi | Quản lý vòng đời property/graph hoặc đặt tên mới |
| “Điểm PageRank là một xác suất cộng lại bằng 1” | Các score mặc định của GDS PageRank không nhất thiết chuẩn hóa thành xác suất | Chỉ áp dụng scaler/diễn giải xác suất khi có cấu hình phù hợp |
| “`write` là một transaction nguyên tử duy nhất” | GDS có thể dùng transaction riêng trong pha ghi | Thiết kế kiểm tra sau lỗi và chính sách chạy lại |
| “Chỉ cần `MATCH` là cập nhật được score trong GDS memory” | Cypher `MATCH` đọc database, không tự sửa projection | Dùng thao tác GDS đúng lớp dữ liệu |
| “GDS luôn có sẵn cùng Neo4j” | GDS là thư viện/khả năng triển khai riêng | Kiểm tra cài đặt, phiên bản, license và quyền |

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài 1 — Chọn mode

Một nhóm phân tích muốn tính community của người dùng và dùng community ID làm đầu vào cho thuật toán tiếp theo, **không muốn ghi thuộc tính trung gian vào database**. Nếu thuật toán community đó hỗ trợ `mutate`, nên chọn mode nào?

<details>
<summary>Đáp án</summary>

Chọn `mutate`. Nó đưa community ID vào named graph để các thuật toán GDS tiếp theo có thể sử dụng. Cần kiểm tra thuật toán tiếp theo thực sự hỗ trợ đọc thuộc tính đó và có cùng định nghĩa node/relationship trong projection.

</details>

### Bài 2 — Đọc kết quả không ghi

Hãy viết truy vấn để lấy ba người có PageRank cao nhất trên `modeLessonGraph`, không cập nhật DB.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
CALL gds.pageRank.stream('modeLessonGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC, personId ASC
LIMIT 3;
~~~

Sử dụng `stream`. `LIMIT 3` chỉ giảm số hàng đưa ra sau tính toán.

</details>

### Bài 3 — Phân biệt memory và database

Sau khi chạy:

~~~cypher
CALL gds.pageRank.mutate('modeLessonGraph', {
    mutateProperty: 'scoreOnlyInMemory'
})
YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
~~~

Bạn chạy `MATCH (p:ModePerson) RETURN p.scoreOnlyInMemory` và thấy `null`. Có phải GDS mất kết quả?

<details>
<summary>Đáp án</summary>

Chưa thể kết luận. `mutate` ghi property vào projected graph. Kiểm tra bằng `CALL gds.graph.nodeProperty.stream('modeLessonGraph', 'scoreOnlyInMemory') YIELD nodeId, propertyValue RETURN nodeId, propertyValue`. `MATCH` đọc từ database nên không tự thấy property này.

</details>

### Bài 4 — Tác động của `write`

Một job PageRank chạy mỗi đêm với `writeProperty: 'pageRankDatabase'`. Ban ngày, ứng dụng xếp hạng bằng `ORDER BY p.pageRankDatabase DESC`. Hãy nêu ít nhất ba điều cần kiểm tra trước khi đưa vào production.

<details>
<summary>Gợi ý đáp án</summary>

Cần kiểm tra graph projection phản ánh dữ liệu cần tính; quyền ghi và nguy cơ ghi đè thuộc tính; bộ nhớ và thời gian viết; chính sách xử lý nếu job dừng giữa chừng; thời điểm ứng dụng đọc dữ liệu; tính nhất quán của tham số và version thuật toán; chỉ mục nếu truy vấn sắp xếp trên property đó thường xuyên. Nếu kết quả cần đảm bảo “đổi phiên bản một lần”, cân nhắc ghi sang thuộc tính/bản dữ liệu mới rồi chuyển cách đọc theo quy trình ứng dụng.

</details>

### Bài 5 — Kết quả thống kê

Nếu chỉ có nhu cầu biết `didConverge` và `centralityDistribution.max` của PageRank, nên chọn mode nào? Kết quả có được tự lưu vào GDS graph hoặc database không?

<details>
<summary>Đáp án</summary>

`stats` phù hợp nếu phiên bản PageRank hỗ trợ và không cần giá trị từng node. Nó trả một hàng thống kê, không lưu node score vào named graph hoặc database.

</details>

## 15. Dọn dẹp đồ thị GDS sau thực hành

Khi không còn cần named graph trong GDS, có thể giải phóng bộ nhớ:

~~~cypher
CALL gds.graph.drop('modeLessonGraph')
YIELD graphName
RETURN graphName;
~~~

Lệnh trên **xóa named graph khỏi GDS Graph Catalog**, đồng thời giải phóng các property được `mutate` vào graph đó. Nó **không xóa** các node `ModePerson`/relationship `FOLLOWS` trong Neo4j Database và **không xóa** property `pageRankDatabase` đã được `write` xuống DB.

Nếu muốn xóa dữ liệu thực hành khỏi database, đó là một thao tác **riêng và có tác dụng ghi/xóa**, phải bảo đảm database không chứa dữ liệu cần giữ. Việc dọn catalog không thay thế việc quản lý vòng đời dữ liệu nghiệp vụ.

## 16. Tài liệu tham khảo

- [GDS — Syntax overview và các execution mode](https://neo4j.com/docs/graph-data-science/current/algorithms/syntax/)
- [GDS — Running algorithms: stream, stats, mutate, write](https://neo4j.com/docs/graph-data-science/current/common-usage/running-algos/)
- [GDS — PageRank: tham số và ví dụ của bốn mode](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)
- [GDS — Tạo named graph trong bộ nhớ](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/)
- [GDS — Đọc property đã mutate trong projected graph](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-reads/graph-stream-nodes/)
- [GDS — Transaction handling khi ghi kết quả](https://neo4j.com/docs/graph-data-science/current/production-deployment/transaction-handling/)

Các trang `current` được cập nhật theo phiên bản GDS mới. Khi áp dụng cho dự án, đối chiếu bản cài đặt, cú pháp từng thuật toán và quyền thực thi trong môi trường cụ thể.

## 17. Ghi nhớ

- **`stream` trả chi tiết**, phù hợp kiểm tra và xử lý đầu ra mà không ghi kết quả.
- **`stats` trả một hàng thống kê** nhưng vẫn có thể chạy đầy đủ phép tính; không trả score từng node.
- **`mutate` lưu kết quả trong GDS named graph**, hữu ích cho chuỗi thuật toán; không tự cập nhật database.
- **`write` ghi vào Neo4j Database**, phù hợp ứng dụng dùng kết quả lâu dài; không tự làm mới projection đã tồn tại.
- **Chỉ dùng mode được thuật toán hỗ trợ**, với cấu hình và `YIELD` theo tài liệu đúng phiên bản GDS.
- **Đánh giá kết quả, tài nguyên và tác động ghi trước khi triển khai**, đặc biệt với graph lớn và dữ liệu nghiệp vụ.
