# Phân biệt truy vấn đường đi bằng Cypher với thuật toán đồ thị chuyên dụng

Trong Neo4j, cả **truy vấn đường đi bằng Cypher** lẫn **thuật toán đồ thị chuyên dụng** đều làm việc trên các node và relationship của property graph. Tuy nhiên, chúng giải quyết những lớp bài toán khác nhau:

- **Cypher** diễn tả mẫu quan hệ cần tìm, lọc dữ liệu, ghép điều kiện nghiệp vụ và trả về node, relationship hoặc path phù hợp.
- **Thuật toán đồ thị** giải một bài toán được xác định rõ trên cấu trúc mạng, chẳng hạn đường có **tổng trọng số nhỏ nhất**, khả năng tiếp cận, độ quan trọng của node hoặc các thành phần liên thông. Với Neo4j, nhiều thuật toán này được cung cấp qua thư viện **Graph Data Science (GDS)**, thường chạy trên một đồ thị được chiếu vào bộ nhớ.

Chủ đề thuộc chương **Đường đi và duyệt đồ thị** của module **DATABASE_ENGINE_GRAPH_NEO4J**: sử dụng Neo4j để mô hình hóa dữ liệu liên kết theo property graph, truy vấn quan hệ và đường đi bằng Cypher, kết hợp index/constraint, nhập dữ liệu, Java Driver, Spring Data Neo4j và các cân nhắc vận hành. Mục tiêu của bài là nhận diện **khi nào nên truy vấn một mẫu đường đi, khi nào cần một thuật toán**, tránh nhầm “đường ngắn nhất theo số chặng” với “đường tối ưu theo chi phí”.

## 1. Hiểu đúng đối tượng: đường đi, số chặng và trọng số

Xét một mạng các điểm trung chuyển, mỗi quan hệ `:TRIP` cho biết thời gian di chuyển:

```text
(A) ──90 phút──▶ (B)
 │
 └──10 phút──▶ (C) ──10 phút──▶ (B)
```

Có hai đường đi từ A đến B:

| Đường đi | Số chặng (hops) | Tổng thời gian (weight/cost) |
| --- | ---: | ---: |
| A → B | 1 | 90 phút |
| A → C → B | 2 | 20 phút |

Nếu hỏi **“ít chặng nhất?”**, đáp án là A → B. Nếu hỏi **“nhanh nhất xét theo phút?”**, đáp án là A → C → B. Hai đáp án đều đúng với hai mục tiêu khác nhau.

Một path trong Cypher là một chuỗi các node được nối bởi relationship phù hợp. Một số hàm quan trọng:

| Hàm Cypher | Ý nghĩa |
| --- | --- |
| `nodes(p)` | Danh sách node trên path `p` theo thứ tự |
| `relationships(p)` | Danh sách relationship trên path |
| `length(p)` | Số relationship của path, tức số chặng |
| `reduce(...)` | Có thể cộng trọng số từ các relationship trên path |
| `shortestPath(...)` | Tìm đường ngắn nhất theo **số relationship** trong mẫu cho trước |

**Điểm quyết định:** một thuộc tính như `r.minutes` là **trọng số nghiệp vụ**, còn `length(p)` chỉ đếm relationship. Việc có thuộc tính `minutes` trên relationship không khiến `shortestPath()` tự động tối ưu theo phút.

## 2. Dựng một đồ thị nhỏ để quan sát

Các ví dụ dưới đây dùng label `:Stop`, thuộc tính `code` và relationship có hướng `:TRIP`. Thực hành trên database thử nghiệm:

```cypher
MERGE (a:Stop {code: 'A'})
MERGE (b:Stop {code: 'B'})
MERGE (c:Stop {code: 'C'})
MERGE (a)-[ab:TRIP]->(b)
SET ab.minutes = 90
MERGE (a)-[ac:TRIP]->(c)
SET ac.minutes = 10
MERGE (c)-[cb:TRIP]->(b)
SET cb.minutes = 10;
```

`MERGE` giúp tránh tạo lại các mẫu đã khớp, nhưng chỉ hoạt động chắc chắn với danh tính `Stop.code` khi dữ liệu không có node trùng mã. Một hệ thống thực tế nên đặt **uniqueness constraint** cho mã điểm dừng, sau khi bảo đảm dữ liệu hiện có không trùng:

```cypher
CREATE CONSTRAINT stop_code_unique IF NOT EXISTS
FOR (s:Stop)
REQUIRE s.code IS UNIQUE;
```

Constraint này phục vụ tính nhất quán của danh tính; việc lựa chọn và đánh giá index cũng giúp truy vấn định vị node nguồn/đích nhanh hơn. Nếu chạy đồng thời trong môi trường dùng chung, kiểm tra trước các label, quan hệ và constraint hiện có.

## 3. Cypher: mô tả mẫu và truy vấn các đường đi

### 3.1. Tìm những đường phù hợp trong một giới hạn số chặng

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = (start)-[:TRIP*1..3]->(finish)
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       reduce(total = 0, r IN relationships(p) |
              total + r.minutes) AS totalMinutes
ORDER BY hops, route;
```

Đây là **truy vấn mẫu đường đi**: kết quả gồm các path có từ 1 đến 3 relationship `:TRIP`, đi đúng chiều mũi tên. Trên đồ thị ví dụ, có hai dòng: A → B và A → C → B.

Các điểm cần nắm:

- `*1..3` là giới hạn **độ dài đường theo số relationship**, không phải giới hạn thời gian.
- `->` yêu cầu quan hệ theo chiều dữ liệu; `-[:TRIP*1..3]-` cho phép đi theo cả hai chiều.
- Một path được khớp bởi mẫu Cypher thông thường không dùng lại cùng một relationship trong chính path đó; tuy nhiên **node vẫn có thể xuất hiện nhiều lần**, nên “không đi qua node lặp” là một ràng buộc bổ sung nếu nghiệp vụ yêu cầu.
- Số đường phù hợp có thể tăng rất nhanh khi số nhánh hoặc độ sâu tăng. Nên giới hạn độ dài và đặt điều kiện nguồn, đích, loại quan hệ, hướng duyệt phù hợp.

### 3.2. Tìm đường có ít chặng nhất bằng Cypher

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = shortestPath((start)-[:TRIP*]->(finish))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       reduce(total = 0, r IN relationships(p) |
              total + r.minutes) AS totalMinutes;
```

Kết quả kỳ vọng từ dữ liệu mẫu:

```text
route       hops    totalMinutes
['A','B']   1       90
```

`shortestPath()` chọn **ít relationship nhất**. Nếu có nhiều đường cùng ít chặng nhất, hàm này trả về một đường trong số đó; khi cần mọi đường cùng đạt số chặng nhỏ nhất, có thể xét `allShortestPaths()`.

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = allShortestPaths((start)-[:TRIP*]->(finish))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
```

Không nên suy diễn thứ tự giữa các đường đồng hạng khi không có tiêu chí sắp xếp rõ ràng. Mọi đường ngắn nhất có thể vẫn rất nhiều; trả toàn bộ chúng có thể tốn bộ nhớ và thời gian.

> **Lưu ý phiên bản:** `shortestPath()` và `allShortestPaths()` là cú pháp quen thuộc của Cypher trong Neo4j 5. Các phiên bản/ngôn ngữ Cypher mới có thêm cách viết cho mẫu đường đi ngắn nhất. Khi áp dụng, đối chiếu cú pháp với phiên bản Neo4j đang chạy; khái niệm **số chặng** và **tổng trọng số** vẫn cần được phân biệt.

### 3.3. Có thể dùng Cypher để chọn tổng phút nhỏ nhất không?

Với **đồ thị rất nhỏ và độ sâu đã được giới hạn**, có thể liệt kê các path rồi tính tổng phút:

```cypher
MATCH (start:Stop {code: 'A'})
MATCH (finish:Stop {code: 'B'})
MATCH p = (start)-[:TRIP*1..3]->(finish)
WHERE all(r IN relationships(p) WHERE
          r.minutes IS NOT NULL AND r.minutes >= 0)
WITH p,
     reduce(total = 0, r IN relationships(p) |
            total + r.minutes) AS totalMinutes
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       totalMinutes
ORDER BY totalMinutes ASC, hops ASC
LIMIT 1;
```

Kết quả là A → C → B với 20 phút. Nhưng cơ chế này có **điểm yếu về độ mở rộng**: để tìm ứng viên rẻ nhất, truy vấn có thể phải tạo và tính chi phí cho rất nhiều path. `LIMIT 1` ở cuối không đảm bảo engine có thể bỏ qua công việc tạo ứng viên trước đó. Nếu giới hạn `*1..3` thấp hơn độ dài của đường tối ưu thực tế, kết quả còn có thể bỏ sót lời giải tốt nhất.

Tức là Cypher *có thể tính chi phí của một path*, nhưng cách liệt kê mọi path rồi sắp xếp không phải lựa chọn mặc định cho bài toán **shortest weighted path** trên đồ thị lớn.

## 4. Thuật toán đồ thị chuyên dụng giải bài toán gì?

Một thuật toán nhận vào **cấu trúc đồ thị, node nguồn/đích, thuộc tính trọng số và các điều kiện cụ thể**, rồi tính toán theo mục tiêu xác định. Ví dụ:

| Nhu cầu | Hướng tiếp cận điển hình | Kết quả mong muốn |
| --- | --- | --- |
| Tìm quan hệ liên kết trong 1–3 bước, kèm lọc thuộc tính | Cypher `MATCH` và mẫu đường đi | Các path/quan hệ khớp điều kiện |
| Ít chặng nhất giữa hai node | Cypher `shortestPath()`, hoặc BFS phù hợp | Đường ít relationship nhất |
| Tổng thời gian hoặc chi phí không âm nhỏ nhất | **Dijkstra** trong GDS | Đường có tổng trọng số nhỏ nhất |
| Đường chi phí thấp với heuristic vị trí hợp lệ | **A\*** trong GDS | Đường tối ưu theo điều kiện thuật toán, có thể giảm không gian tìm kiếm |
| Nhiều tuyến thay thế theo chi phí | **Yen's k-shortest paths** trong GDS | Một tập đường ngắn theo thứ tự chi phí |
| Duyệt từ một nguồn theo từng lớp / theo nhánh | **BFS / DFS** | Tập node hoặc đường duyệt theo quy tắc |
| Các cụm không liên thông với nhau | **Weakly Connected Components (WCC)** | Mã thành phần liên thông của node |
| Chấm điểm độ quan trọng của node trong mạng | **PageRank** | Điểm số của mỗi node |
| Nhận diện cộng đồng trong mạng | **Louvain** hoặc thuật toán cộng đồng khác | Nhãn cộng đồng cho node |

Các thuật toán như PageRank, WCC hay Louvain **không trả lời trực tiếp “đường đi nào?”**. Chúng giải những bài toán phân tích toàn mạng mà một câu `MATCH` đơn giản không có cơ chế tối ưu tương ứng.

**Không phải cứ có đường đi là phải dùng GDS.** Nếu mục tiêu là kiểm tra “người này có quan hệ `:KNOWS` với người kia trong tối đa 2 bước và cùng thành phố hay không?”, Cypher tự nhiên hơn vì biểu diễn điều kiện dữ liệu trực tiếp.

## 5. Dijkstra trong Neo4j Graph Data Science

### 5.1. Tư duy tổng quát

Dijkstra tìm đường từ một nguồn tới đích với **tổng trọng số nhỏ nhất** khi các trọng số cạnh phù hợp là **không âm**. Thuật toán không đơn thuần chọn ít cạnh; nó tích lũy chi phí và mở rộng theo chi phí nhỏ nhất đã biết.

Với ví dụ A/B/C, Dijkstra ưu tiên A → C → B vì 10 + 10 = 20, thấp hơn 90. Hãy chọn trọng số theo đúng mục tiêu: phút, đồng, khoảng cách, rủi ro đã quy đổi hợp lệ... Nếu muốn tối ưu nhiều tiêu chí đồng thời, cần xác định quy tắc tối ưu hoặc mô hình chi phí rõ ràng.

Trước khi dùng GDS, môi trường Neo4j phải có thư viện GDS tương thích với phiên bản server và người dùng phải có quyền gọi procedure cần thiết. GDS thường làm việc qua **named graph projection** — một biểu diễn đồ thị trong bộ nhớ dùng cho thuật toán.

### 5.2. Chiếu đồ thị vào bộ nhớ

```cypher
CALL gds.graph.project(
  'stopTrips',
  'Stop',
  {
    TRIP: {
      type: 'TRIP',
      orientation: 'NATURAL',
      properties: 'minutes'
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
```

Trong ví dụ:

- `'Stop'` chọn các node phù hợp; `'TRIP'` chọn relationship cần dùng.
- `orientation: 'NATURAL'` giữ chiều quan hệ như đồ thị Neo4j đã lưu.
- `minutes` được đưa vào projection làm trọng số.
- `'stopTrips'` là **tên của đồ thị GDS trong bộ nhớ**, không phải tên database Neo4j và không phải một label mới.

Projection cần đủ node, relationship và thuộc tính cho bài toán. Nếu mạng có quan hệ một chiều nhưng đặt projection thành vô hướng, kết quả có thể cho phép đi theo chiều mà nghiệp vụ không cho phép. Nếu `minutes` thiếu hoặc có kiểu không phù hợp, cần làm sạch dữ liệu trước khi chạy thuật toán.

### 5.3. Chạy Dijkstra có trọng số

```cypher
MATCH (source:Stop {code: 'A'})
MATCH (target:Stop {code: 'B'})
CALL gds.shortestPath.dijkstra.stream('stopTrips', {
  sourceNode: source,
  targetNode: target,
  relationshipWeightProperty: 'minutes'
})
YIELD totalCost, nodeIds
RETURN [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route,
       totalCost AS totalMinutes;
```

Kết quả kỳ vọng:

```text
route           totalMinutes
['A','C','B']    20.0
```

Điểm cần chú ý:

1. `sourceNode` và `targetNode` phải nằm trong projection `stopTrips`.
2. `relationshipWeightProperty` chọn **thuộc tính dùng làm chi phí**; nếu tối ưu khoảng cách thay vì thời gian, không thể giữ nguyên tên `minutes`.
3. Đường trả về được xác định theo **tổng trọng số**, không nhất thiết theo số relationship.
4. Nếu dữ liệu gốc được sửa sau khi tạo projection, cần có chiến lược **làm mới hoặc tái tạo projection** trước khi dựa vào kết quả mới.
5. Với đường không tồn tại, cần xử lý trường hợp không nhận được đường kết quả, thay vì tự gán tổng chi phí bằng 0.

Khi không còn sử dụng projection thử nghiệm, giải phóng bộ nhớ bằng:

```cypher
CALL gds.graph.drop('stopTrips')
YIELD graphName
RETURN graphName;
```

Chỉ drop graph do bạn sở hữu hoặc không còn phiên phân tích nào cần đến; named graph GDS có thể được dùng chung trong một phạm vi quản lý.

### 5.4. Vì sao không luôn dùng Dijkstra?

GDS có bước chuẩn bị dữ liệu và chi phí bộ nhớ; Cypher truy vấn trực tiếp lên store và hỗ trợ biểu thức lọc phức tạp trên property graph. Nếu ứng dụng chỉ kiểm tra quan hệ ở độ sâu 1–2, việc projection toàn bộ mạng có thể không cần thiết.

Ngược lại, chạy nhiều bài toán weighted shortest path, centrality hoặc cộng đồng trên cùng mạng có thể tận dụng lại projection đã chuẩn bị. Cân nhắc dữ liệu có cập nhật liên tục hay không, số truy vấn, dung lượng đồ thị và độ trễ yêu cầu.

## 6. BFS, DFS, đường ngắn nhất: không đồng nghĩa

**Breadth-First Search (BFS)** đi từ node nguồn theo từng lớp khoảng cách tính bằng số cạnh. Với cạnh cùng chi phí, BFS rất phù hợp để tìm đường ít bước; nó còn dùng để khảo sát các node có thể đến được trong một độ sâu nhất định.

**Depth-First Search (DFS)** đi sâu theo một nhánh rồi quay lui. DFS hữu ích cho khám phá cấu trúc, nhưng path mà DFS gặp đầu tiên **không bảo đảm là path ít chặng hay ít trọng số nhất**.

**Dijkstra** xem xét trọng số không âm; thứ tự khám phá được điều khiển bởi tổng chi phí tốt nhất đã biết.

**A\*** cũng tìm đường chi phí nhỏ theo trọng số nhưng sử dụng thêm một **heuristic** ước lượng phần chi phí từ node hiện tại tới đích. Để bảo đảm tối ưu, heuristic phải thỏa những điều kiện cần thiết, ví dụ không đánh giá quá cao chi phí thực tế còn lại. Nếu thời gian di chuyển là trọng số, khoảng cách đường chim bay chưa tự nó là một ước lượng theo phút; phải quy đổi với giả định phù hợp.

Ví dụ lựa chọn sai:

- Dùng BFS để tìm chuyến đi **ít phút nhất** khi mỗi chặng có thời gian khác nhau.
- Dùng DFS vì “đi sâu sẽ nhanh đến đích hơn”, rồi coi đường đầu tiên là tối ưu.
- Dùng Dijkstra với trọng số **âm** hoặc dữ liệu chi phí bị thiếu mà không xây dựng quy tắc xử lý.
- Dùng A\* với heuristic không cùng đơn vị hoặc không được kiểm chứng, rồi tuyên bố luôn tối ưu.

Nếu bài toán yêu cầu tuyến đường qua các chặng bắt buộc, có điều kiện chuyển tuyến, giới hạn thời gian hoặc chi phí thay đổi theo thời điểm, cần đánh giá xem mô hình đồ thị và thuật toán đang chọn có thực sự mô tả đúng các ràng buộc đó hay không.

## 7. So sánh theo cơ chế, chi phí và cách dùng

| Khía cạnh | Truy vấn đường đi bằng Cypher | Thuật toán chuyên dụng qua GDS |
| --- | --- | --- |
| Đầu vào | Mẫu `MATCH`, điều kiện `WHERE`, dữ liệu property graph | Projection và cấu hình thuật toán |
| Mục tiêu | Tìm mẫu, lọc, ghép và trình bày dữ liệu | Tính đường tối ưu, khả năng tiếp cận, score, cluster... |
| Trọng số | Tự tính bằng biểu thức; `shortestPath()` theo hops | Dijkstra/A\* tối ưu theo thuộc tính trọng số |
| Kết quả | Dòng, node, relationship, path, giá trị tổng hợp | Chi phí, node IDs, path, score, community... tùy thuật toán |
| Hiệu năng | Mạnh khi ràng buộc mẫu rõ; liệt kê đường sâu có thể bùng nổ | Tối ưu theo bài toán thuật toán; tốn chi phí tạo và giữ projection |
| Dữ liệu mới | Đọc theo giao dịch/điều kiện truy vấn đang thực hiện | Cần quản lý vòng đời và độ mới của projection |
| Tích hợp ứng dụng | Dùng trực tiếp với Java Driver, Spring Data Neo4j | Gọi procedure GDS qua Cypher/Driver; xử lý quyền và tài nguyên |
| Kỹ năng cần có | Mô hình và cú pháp path, hiểu execution plan | Hiểu thuật toán, tiền điều kiện, projection, bộ nhớ, thống kê |

### Những hiểu nhầm thường gặp

**“Cypher không có thuật toán đường ngắn nhất.”** Sai. Cypher hỗ trợ đường ngắn nhất theo số cạnh với các cú pháp phù hợp. Khác biệt chính là **định nghĩa mục tiêu** và **quy mô công việc**.

**“Dùng GDS thì kết quả tự động chính xác hơn.”** Không hẳn. Nếu projection sai chiều, bỏ sót cạnh, dùng sai weight hoặc chưa cập nhật dữ liệu mới, thuật toán có thể tính đúng trên **một đồ thị đầu vào sai**.

**“`LIMIT 1` sẽ làm truy vấn liệt kê mọi path trở nên rẻ.”** Không được bảo đảm. Việc tạo và tính ứng viên vẫn có thể rất tốn kém trước lúc áp dụng `ORDER BY ... LIMIT 1`.

**“Shortest path luôn là tuyến nhanh nhất.”** Chỉ khi định nghĩa độ dài và trọng số trùng với mục tiêu. `length(p)` không suy ra `minutes`, `price` hoặc mức độ rủi ro.

## 8. Thiết kế hệ thống Java và Spring Data Neo4j

Với hệ thống giao thông có API `GET /routes?from=A&to=B&objective=time`, tầng dịch vụ có thể chọn nhánh xử lý theo `objective`:

```text
Yêu cầu tính tuyến
       |
       v
Xác thực node nguồn/đích, mục tiêu tối ưu, dữ liệu chi phí
       |
       +-- Quan hệ / số chặng nhỏ nhất ------> Cypher path / shortestPath
       |
       +-- Tổng phút / tổng chi phí ---------> GDS Dijkstra/A* với weight hợp lệ
       |
       +-- Phân tích mạng theo lô ------------> GDS WCC, PageRank, cộng đồng...
       |
       v
Kiểm tra kết quả, độ mới dữ liệu, trả tuyến và tiêu chí tối ưu
```

Trong ứng dụng Java:

- **Neo4j Java Driver** gửi câu Cypher và tham số (mã trạm, node nguồn/đích, mục tiêu), rồi đọc kết quả. Có thể gọi `gds.shortestPath.dijkstra.stream` như một procedure trong Cypher khi môi trường đã cài GDS.
- **Spring Data Neo4j** thuận tiện khi quản lý entity node/relationship và truy vấn nghiệp vụ; truy vấn GDS đặc thù có thể cần repository query tùy biến hoặc Driver phù hợp.
- **Không nên tự ghép chuỗi từ dữ liệu người dùng** để tạo truy vấn, nhất là ID và tên tham số. Với Cypher, giá trị nguồn/đích nên được truyền bằng tham số, ví dụ `$fromCode` và `$toCode`.
- **Cần phản hồi rõ tiêu chí tuyến:** `objective: "MIN_HOPS"` hay `"MIN_MINUTES"`, cùng `hops` và `totalMinutes` nếu có. Tránh một trường duy nhất tên `shortest` mà không nêu đơn vị.

Ví dụ truy vấn định vị hai điểm bằng tham số, thích hợp gọi qua Driver:

```cypher
MATCH (source:Stop {code: $fromCode})
MATCH (target:Stop {code: $toCode})
MATCH p = shortestPath((source)-[:TRIP*]->(target))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
```

Với hệ thống lớn, cần phân biệt **truy vấn giao dịch trực tuyến** với **tác vụ phân tích nặng**. Một số thuật toán có chi phí CPU/RAM cao; việc chạy lặp không kiểm soát trong đường xử lý request có thể gây độ trễ hoặc ảnh hưởng các workload còn lại.

## 9. Tối ưu và vận hành có trách nhiệm

### Cho truy vấn Cypher

1. **Xác định nguồn/đích chặt chẽ.** Dùng thuộc tính có uniqueness constraint hoặc index phù hợp để không mở rộng từ toàn bộ node.
2. **Giới hạn mẫu path khi bài toán cho phép.** `*1..4` an toàn hơn về phạm vi tìm kiếm so với duyệt vô hạn, nhưng chỉ đúng khi yêu cầu thật sự giới hạn 4 chặng.
3. **Giữ đúng hướng và loại quan hệ.** Chuyển thành vô hướng vô tình có thể tạo ra tuyến không hợp lệ.
4. **Dùng `EXPLAIN` / `PROFILE` để quan sát kế hoạch và số lượng dòng.** Tối ưu cần dựa trên hình dạng dữ liệu thực tế, không chỉ đo số ký tự của câu truy vấn.
5. **Cẩn thận với tổng chi phí bị thiếu.** `reduce` cộng giá trị `null` có thể làm kết quả không còn là số; cần lọc hoặc có quy tắc dữ liệu rõ ràng.

### Cho thuật toán GDS

1. **Kiểm tra điều kiện đầu vào.** Thuộc tính weight phải đúng kiểu số và thỏa ràng buộc của thuật toán (Dijkstra: không âm).
2. **Chọn projection vừa đủ.** Node label, loại relationship, chiều và thuộc tính chi phí đều ảnh hưởng kết quả lẫn bộ nhớ.
3. **Giám sát tài nguyên và thời gian.** Những bài toán phân tích trên đồ thị lớn cần kiểm tra dung lượng bộ nhớ và mức độ cạnh tranh tài nguyên.
4. **Quản lý tính mới.** Graph projection không nên được coi là tự động đồng bộ mọi thay đổi của store.
5. **Quản lý vòng đời graph.** Tái sử dụng projection khi hợp lý; giải phóng projection thử nghiệm, tránh drop projection do job khác đang sử dụng.
6. **Kiểm chứng trên trường hợp nhỏ có đáp án biết trước.** Ví dụ A/B/C ở đầu bài sẽ bắt lỗi chọn nhầm tối ưu theo chặng thay vì theo phút.

## 10. Bài tập áp dụng

**Bài tập 1 — Hai mục tiêu khác nhau.** Với mạng A → B (90 phút), A → C (10 phút), C → B (10 phút), hãy viết một truy vấn Cypher lấy đường ít chặng nhất và một truy vấn GDS Dijkstra lấy đường ít phút nhất. Giải thích vì sao đáp án khác nhau.

**Bài tập 2 — Đường tối ưu có ràng buộc.** Yêu cầu chỉ đi qua quan hệ `:TRIP` có `active = true`. Vì sao projection GDS chứa cả chuyến không hoạt động có thể cho kết quả sai? Đề xuất cách lọc đúng dữ liệu trước khi tính.

**Bài tập 3 — Tính cập nhật.** Thời gian A → B được sửa từ 90 xuống 5 phút. Truy vấn Cypher đọc dữ liệu mới, nhưng GDS đang dùng projection cũ. Ứng dụng nên làm gì trước khi công bố kết quả “nhanh nhất”?

**Bài tập 4 — Bùng nổ đường đi.** Một mạng xã hội có hàng triệu node; yêu cầu liệt kê mọi đường dài tối đa 10 quan hệ giữa hai người. Hãy nêu rủi ro và cách thu hẹp bài toán trước khi viết Cypher.

**Bài tập 5 — Không phải bài toán đường đi.** Một nhóm phân tích cần tìm các thành phần kết nối và người có ảnh hưởng trong mạng. Hãy đề xuất thuật toán phù hợp với từng mục tiêu và giải thích vì sao không chỉ dùng `shortestPath()`.

### Kiến thức cần ghi nhớ

- **Cypher `MATCH`:** phù hợp mô tả cấu trúc quan hệ và trả về những path khớp điều kiện.
- **Cypher `shortestPath()`:** chọn đường ngắn nhất theo **số relationship** trong phạm vi mẫu.
- **GDS Dijkstra/A\*:** phục vụ bài toán đường theo **trọng số** với các điều kiện thuật toán cụ thể.
- **BFS/DFS:** khác nhau về thứ tự và chiến lược duyệt; DFS không mặc nhiên trả đường tối ưu.
- **GDS WCC/PageRank/cộng đồng:** phục vụ phân tích **toàn mạng**, không đơn thuần tìm một path.
- **Kết quả đáng tin cậy:** phụ thuộc vào mô hình hướng cạnh, dữ liệu trọng số, giới hạn nghiệp vụ, độ mới của projection và phương pháp đo hiệu năng.

Việc chọn Cypher hay thuật toán đồ thị không phải cuộc thi xem công cụ nào “mạnh hơn”. Hãy định nghĩa chính xác **câu hỏi cần trả lời**, dữ liệu nào là trọng số, phạm vi mạng và độ mới yêu cầu; sau đó chọn cơ chế giải quyết tương ứng.
