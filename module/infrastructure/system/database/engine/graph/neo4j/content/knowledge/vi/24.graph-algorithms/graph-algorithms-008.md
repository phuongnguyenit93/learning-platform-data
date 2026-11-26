# Thuật toán đường đi có trọng số và bài toán khoảng cách

## 1. Đường đi ngắn nhất không phải lúc nào cũng có ít cạnh nhất

Trong **Neo4j**, một đường đi (*path*) là chuỗi node nối với nhau bằng các relationship. Một relationship có thể mang thuộc tính số như **km**, **minutes**, **cost** hoặc **riskScore**. Khi ứng dụng cần tìm đường vận chuyển, tuyến xử lý nhanh nhất, chuỗi phụ thuộc ít rủi ro nhất hoặc chi phí giao dịch thấp nhất, chỉ đếm số quan hệ (*hop*) thường không trả lời đúng câu hỏi.

Bài học thuộc chương **Thuật toán đồ thị** trong module **DATABASE_ENGINE_GRAPH_NEO4J**. Mục tiêu là hiểu **bài toán khoảng cách có trọng số**, chọn thuật toán phù hợp, chạy trên đồ thị **property graph** bằng **Neo4j Graph Data Science (GDS)** và đánh giá những giới hạn về dữ liệu, bộ nhớ, hướng quan hệ và tính đúng đắn.

Hãy phân biệt:

| Câu hỏi | Đại lượng tối ưu | Cách tiếp cận |
|---|---|---|
| Từ A đến D qua ít quan hệ nhất? | **Số hop** | Cypher **shortestPath()** hoặc **SHORTEST** |
| Tuyến A → D có tổng chiều dài thấp nhất? | **Tổng km** của từng relationship | GDS **Dijkstra** với thuộc tính **km** |
| Tuyến A → D mất ít thời gian nhất? | **Tổng phút** của từng relationship | GDS **Dijkstra** với thuộc tính **minutes** |
| Có những tuyến thay thế gần tối ưu nào? | **k đường** theo tổng trọng số | GDS **Yen** |
| Khoảng cách từ A đến mọi node có thể tới? | Tổng trọng số tối thiểu từ **một nguồn** | GDS **Dijkstra Single-Source** hoặc **Delta-Stepping** |
| Đồ thị có cạnh mang trọng số âm? | Tổng trọng số, có thể có chu trình âm | **Bellman–Ford**; phải phân tích chu trình âm |

**Quan trọng:** Cypher **shortestPath()**, **allShortestPaths()** và path selector **SHORTEST** chọn đường theo **số relationship**. Chúng **không tự tối ưu tổng thuộc tính km/minutes/cost**. Kể cả ở Cypher 25, bài toán *weighted shortest path* thường dùng thuật toán trong GDS.

## 2. Mô hình toán học của đường đi có trọng số

Xét đồ thị có hướng \(G=(V,E)\), với mỗi relationship \(e\) mang trọng số \(w(e)\). Nếu đường đi từ A đến D là \(p=(e_1,e_2,\dots,e_k)\), chi phí của đường được tính bằng:

\[
C(p)=\sum_{i=1}^{k} w(e_i)
\]

Đường tối ưu giữa hai node \(s,t\) là:

\[
p^*=\underset{p:s\leadsto t}{\operatorname{arg\,min}}\;C(p)
\]

**Giả định của mô hình:** chi phí của một đường bằng tổng chi phí từng cạnh, và mỗi cạnh có trọng số thích hợp với thuật toán. Với Dijkstra trong GDS, dùng **trọng số không âm**, thực tế nên lưu các giá trị số hữu hạn và dương cho ví dụ định tuyến. Nếu chi phí phụ thuộc thời điểm xuất phát, thời gian chờ, dung lượng đã sử dụng hoặc trạng thái dọc đường, tổng đơn giản có thể không còn đủ để biểu diễn bài toán; khi đó cần mô hình/trình giải chuyên biệt.

Một đồ thị có thể có nhiều cách đo khoảng cách:

- **Hop distance:** mỗi cạnh tính là 1, đo số bước.
- **Weighted distance:** mỗi cạnh có trọng số km, phút, tiền hoặc một đơn vị rõ ràng.
- **Reachability:** chỉ hỏi có đường hay không, chưa phải bài toán tối ưu chi phí.

Tất cả trọng số trong một lần chạy phải có **cùng đơn vị và ý nghĩa**. Không cộng giá tiền với km rồi gọi kết quả là “khoảng cách” nếu chưa định nghĩa hàm chi phí tổng hợp.

## 3. Dựng đồ thị thực hành: cùng điểm đầu–cuối, ba đáp án tối ưu

Để tránh đụng dữ liệu nghiệp vụ, dùng nhãn **DemoWeightedPlace** và loại quan hệ **DEMO_WEIGHTED_ROUTE**. Chạy đoạn tạo dữ liệu **một lần trên cơ sở dữ liệu thử nghiệm**:

~~~cypher
CREATE CONSTRAINT demo_weighted_place_code IF NOT EXISTS
FOR (n:DemoWeightedPlace)
REQUIRE n.code IS UNIQUE;
~~~

~~~cypher
CREATE
  (a:DemoWeightedPlace {code: 'A'}),
  (b:DemoWeightedPlace {code: 'B'}),
  (c:DemoWeightedPlace {code: 'C'}),
  (d:DemoWeightedPlace {code: 'D'}),
  (e:DemoWeightedPlace {code: 'E'}),
  (f:DemoWeightedPlace {code: 'F'}),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 20.0, minutes: 25.0}]->(d),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 7.0,  minutes: 4.0}]->(b),
  (b)-[:DEMO_WEIGHTED_ROUTE {km: 5.0,  minutes: 5.0}]->(d),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 4.0,  minutes: 6.0}]->(c),
  (c)-[:DEMO_WEIGHTED_ROUTE {km: 4.0,  minutes: 7.0}]->(d),
  (a)-[:DEMO_WEIGHTED_ROUTE {km: 1.0,  minutes: 4.0}]->(e),
  (e)-[:DEMO_WEIGHTED_ROUTE {km: 1.0,  minutes: 4.0}]->(f),
  (f)-[:DEMO_WEIGHTED_ROUTE {km: 1.0,  minutes: 4.0}]->(d);
~~~

Sơ đồ các cạnh có hướng; nhãn cạnh ghi **km / phút**:

~~~mermaid
flowchart LR
  A((A)) -->|"20 / 25"| D((D))
  A -->|"7 / 4"| B((B))
  B -->|"5 / 5"| D
  A -->|"4 / 6"| C((C))
  C -->|"4 / 7"| D
  A -->|"1 / 4"| E((E))
  E -->|"1 / 4"| F((F))
  F -->|"1 / 4"| D
~~~

Từ A đến D có bốn tuyến:

| Đường | Hop | Tổng km | Tổng phút |
|---|---:|---:|---:|
| A → D | **1** | 20 | 25 |
| A → B → D | 2 | 12 | **9** |
| A → C → D | 2 | 8 | 13 |
| A → E → F → D | 3 | **3** | 12 |

Như vậy:

1. **Ít hop nhất:** A → D, một relationship.
2. **Ít km nhất:** A → E → F → D, **3 km**, dù đi qua ba relationship.
3. **Ít phút nhất:** A → B → D, **9 phút**, dù dài 12 km.

Số liệu chỉ phục vụ minh họa, không biểu diễn bản đồ giao thông thực. Chúng chứng minh rằng “đường ngắn nhất” chưa có nghĩa chính xác cho tới khi chỉ rõ **hàm chi phí**.

## 4. Dùng Cypher thuần để kiểm tra kết quả trên đồ thị nhỏ

Để học cách tính chi phí một đường, có thể liệt kê những đường ngắn vừa phải rồi dùng **reduce()**:

~~~cypher
MATCH (s:DemoWeightedPlace {code: 'A'}),
      (t:DemoWeightedPlace {code: 'D'})
MATCH p = (s)-[:DEMO_WEIGHTED_ROUTE*1..4]->(t)
WITH p,
     reduce(total = 0.0, r IN relationships(p) |
            total + r.km) AS totalKm,
     reduce(total = 0.0, r IN relationships(p) |
            total + r.minutes) AS totalMinutes
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops,
       totalKm,
       totalMinutes
ORDER BY totalKm, hops;
~~~

Kết quả theo km lần lượt là **3**, **8**, **12**, **20** như bảng ở mục 3. Có thể thay **ORDER BY totalKm** bằng **ORDER BY totalMinutes** để kiểm tra mục tiêu thời gian.

**Không dùng cách này làm mặc định trên đồ thị lớn:** truy vấn phải tìm các đường ứng viên trong phạm vi **1..4 hop** rồi mới cộng và sắp xếp. Nếu tăng độ sâu hay số nhánh, số đường có thể tăng rất nhanh. **LIMIT 1** sau **ORDER BY totalKm** không biến phép liệt kê thành Dijkstra; trong trường hợp xấu, bộ máy vẫn phải đánh giá nhiều đường trước khi chọn đường rẻ nhất.

Cũng không viết:

~~~cypher
MATCH p = shortestPath(
  (:DemoWeightedPlace {code: 'A'})
  -[:DEMO_WEIGHTED_ROUTE*1..4]->
  (:DemoWeightedPlace {code: 'D'})
)
RETURN reduce(cost = 0.0, r IN relationships(p) |
              cost + r.km) AS km;
~~~

với kỳ vọng đó là đường ít km. **shortestPath()** trước hết chọn đường ít hop, nên trong đồ thị này sẽ chọn **A → D** và cho kết quả **20 km**, không phải **3 km**.

## 5. Chuẩn bị Neo4j Graph Data Science

Các đoạn từ mục này sử dụng **GDS**, một thư viện thuật toán **cần được cài đặt và cho phép thực thi riêng**, không phải lệnh Cypher lõi. Phiên bản GDS phải tương thích với bản Neo4j đang dùng. GDS có thể sẵn có qua môi trường dịch vụ được hỗ trợ hoặc plugin trên máy chủ tự quản lý; quy trình cài và quyền truy cập khác nhau tùy môi trường.

Đăng nhập bằng tài khoản được phép xem thủ tục và xác nhận có GDS:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'gds.'
RETURN name
ORDER BY name
LIMIT 20;
~~~

Nếu không thấy **gds.graph.project** và **gds.shortestPath.dijkstra.stream**, cần kiểm tra cài đặt, tương thích, cấu hình nạp thủ tục và quyền truy cập. **Không** diễn giải lỗi *Unknown procedure* thành “Neo4j không hỗ trợ đường đi có trọng số”.

### 5.1. Graph projection là gì?

GDS tính toán trên **named graph** được **project** vào bộ nhớ, không tự chạy trực tiếp trên mọi relationship của database cho mỗi lệnh thuật toán. Projection xác định:

- **Tập node:** nhãn node nào thuộc bài toán.
- **Tập relationship:** loại quan hệ nào được duyệt.
- **Hướng:** **NATURAL** theo hướng đã lưu, **REVERSE** nếu đảo chiều, hoặc **UNDIRECTED** nếu được phép đi cả hai hướng.
- **Trọng số:** thuộc tính quan hệ số nào cần đưa vào đồ thị tính toán, ví dụ **km** và **minutes**.

Tạo projection từ đồ thị mẫu:

~~~cypher
CALL gds.graph.project(
  'demoWeightedRoutes',
  'DemoWeightedPlace',
  {
    DEMO_WEIGHTED_ROUTE: {
      orientation: 'NATURAL',
      properties: ['km', 'minutes']
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Kết quả mong đợi khi chỉ có đúng dữ liệu ví dụ: **6 node, 8 relationship**. Nếu đã tạo projection tên **demoWeightedRoutes**, việc tạo lại cùng tên sẽ gặp lỗi; hãy dùng projection hiện có hoặc chủ động **drop** rồi tạo lại theo quy trình ở mục 11.

**Tại sao NATURAL?** Tất cả các cạnh của ví dụ được lưu từ A về D. Nếu đổi sang **UNDIRECTED**, thuật toán được phép đi ngược và có thể xuất hiện những đường không hợp lệ về nghiệp vụ. Tương tự, nếu chỉ project một loại quan hệ nhưng loại quan hệ quan trọng khác bị bỏ qua, đường tối ưu trên projection chưa chắc tối ưu trên toàn dữ liệu thật.

### 5.2. Dữ liệu trọng số phải được kiểm tra trước projection

Chạy kiểm tra để phát hiện trọng số thiếu, không hợp lệ về giá trị hoặc không đúng ràng buộc nghiệp vụ:

~~~cypher
MATCH (:DemoWeightedPlace)-[r:DEMO_WEIGHTED_ROUTE]->
      (:DemoWeightedPlace)
WHERE r.km IS NULL OR r.minutes IS NULL
   OR r.km <= 0 OR r.minutes <= 0
RETURN count(r) AS invalidRoutes;
~~~

Với ví dụ, kết quả là **0**. Trên database thật còn phải kiểm tra **kiểu numeric**, giá trị vô hạn/NaN nếu nguồn sinh ra giá trị đặc biệt, tính nhất quán đơn vị và số đo bất thường. Các property số không hiện diện trong projection có thể trở thành giá trị mặc định như **NaN**, không nên mặc định rằng thuật toán sẽ biết cách sửa lỗi dữ liệu.

Nếu bài toán loại bỏ cạnh **inactive**, tuyến bị cấm, hoặc chỉ cho phép các khoảng thời gian cụ thể, phải **lọc trước khi project** hoặc chọn đúng *subgraph* có ý nghĩa. Lọc đường **sau** khi thuật toán đã chọn đường rẻ nhất có thể khiến kết quả sai: tuyến hợp lệ rẻ nhất chưa chắc là tuyến được tính rồi lọc.

## 6. Dijkstra Source–Target: đường có tổng km nhỏ nhất

**Dijkstra** duy trì khoảng cách tốt nhất đã biết từ node nguồn đến các node khác. Với trọng số **không âm**, khi lấy node có khoảng cách nhỏ nhất khỏi hàng đợi ưu tiên, thuật toán có thể chốt khoảng cách tối ưu của node đó. Trong GDS, biến thể **Source–Target** tìm đường từ một nguồn đến một hoặc nhiều đích.

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (target:DemoWeightedPlace {code: 'D'})
CALL gds.shortestPath.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNodes: [target],
    relationshipWeightProperty: 'km'
  }
)
YIELD totalCost, nodeIds, costs
RETURN totalCost AS totalKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route,
       costs AS cumulativeKm;
~~~

Kết quả kỳ vọng:

~~~text
totalKm: 3.0
route: ["A", "E", "F", "D"]
cumulativeKm: [0.0, 1.0, 2.0, 3.0]
~~~

Đọc từng tham số:

| Tham số/kết quả | Ý nghĩa |
|---|---|
| **sourceNode** | Node bắt đầu, được tìm từ database |
| **targetNodes** | Một node đích hoặc danh sách node đích; dạng **[target]** ở ví dụ |
| **relationshipWeightProperty** | Tên property trên relationship đã project, ở đây **km** |
| **totalCost** | Tổng trọng số tối thiểu; đơn vị là km vì chọn property km |
| **nodeIds** | ID các node trên đường trong thứ tự duyệt |
| **costs** | Tổng trọng số tích lũy khi tới mỗi node trên đường |

**Lưu ý phiên bản API:** trong tài liệu GDS hiện hành, **targetNodes** được khuyến nghị cho Dijkstra Source–Target; dạng **targetNode** đơn lẻ của thuật toán này đã được đánh dấu deprecated. Trường **nodeIds** không phải mã nghiệp vụ nên ví dụ chuyển từng node ID về **code** để hiển thị.

**Stream** là chế độ đọc kết quả, **không ghi đường mới** trở lại database. Các chế độ **write** hoặc **mutate** có tác động dữ liệu khác và chỉ cần khi quy trình thực sự đòi hỏi lưu kết quả.

### 6.1. Đổi hàm chi phí: ít phút nhất

Không cần sửa relationship; chỉ đổi trọng số cần tối ưu:

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (target:DemoWeightedPlace {code: 'D'})
CALL gds.shortestPath.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNodes: [target],
    relationshipWeightProperty: 'minutes'
  }
)
YIELD totalCost, nodeIds
RETURN totalCost AS totalMinutes,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route;
~~~

Kết quả kỳ vọng là **9 phút**, tuyến **A → B → D**. Đường **A → E → F → D** tuy dài **3 km** nhưng mất **12 phút**. Đây là lý do các API định tuyến phải nói rõ tối ưu theo km hay phút.

### 6.2. Một nguồn và nhiều đích

Khi cần từ A đến hai đích D và F, có thể đưa cả hai vào **targetNodes**, tránh dùng cùng truy vấn cho từng đích một cách máy móc:

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (d:DemoWeightedPlace {code: 'D'}),
      (f:DemoWeightedPlace {code: 'F'})
CALL gds.shortestPath.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNodes: [d, f],
    relationshipWeightProperty: 'km'
  }
)
YIELD targetNode, totalCost, nodeIds
RETURN gds.util.asNode(targetNode).code AS target,
       totalCost AS totalKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route
ORDER BY target;
~~~

Trong đồ thị mẫu, **A → F** có giá **2 km** qua E, còn **A → D** có giá **3 km** qua E và F.

## 7. Dijkstra Single–Source: khoảng cách từ một điểm đến các điểm khác

Nếu yêu cầu “khoảng cách từ kho A tới **mọi địa điểm có thể tới**” thay vì chỉ đến D, dùng biến thể **Single–Source**. GDS hiện hành đặt tên thủ tục:

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'})
CALL gds.allShortestPaths.dijkstra.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    relationshipWeightProperty: 'km'
  }
)
YIELD targetNode, totalCost, nodeIds
RETURN gds.util.asNode(targetNode).code AS destination,
       totalCost AS distanceKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route
ORDER BY distanceKm, destination;
~~~

Tên **allShortestPaths.dijkstra** trong GDS ở đây có nghĩa tính đường ngắn nhất từ **một nguồn tới các đích có thể tới**, **không** có nghĩa tự trả mọi đường đồng hạng cho cùng một cặp nguồn–đích.

Theo đồ thị mẫu, khoảng cách nhỏ nhất từ A đến:

| Đích | Tổng km nhỏ nhất | Một đường tối ưu |
|---|---:|---|
| B | 7 | A → B |
| C | 4 | A → C |
| D | 3 | A → E → F → D |
| E | 1 | A → E |
| F | 2 | A → E → F |

Tùy API, kết quả có thể còn gồm node nguồn A với khoảng cách **0**. Với node không thể tới được từ A theo hướng quan hệ đã project, không suy ra “khoảng cách là 0”: chúng không có đường hợp lệ.

**Khi nào chọn Single–Source?** Tính một bản đồ khoảng cách từ trung tâm phân phối, đánh giá khả năng phục vụ, xây dựng vùng phủ theo chi phí hoặc xác định các điểm vượt ngưỡng. Nếu chỉ cần **một cặp A–D**, Source–Target thường phù hợp hơn.

### 7.1. Delta-Stepping khi cần tính toán song song

**Delta-Stepping Single–Source** là biến thể cho phép xử lý các nhóm khoảng cách song song, hữu ích ở một số đồ thị lớn. Trong GDS, thủ tục tương ứng là **gds.allShortestPaths.delta.stream**. Nó có tham số **delta** ảnh hưởng cách nhóm khoảng cách và hiệu quả xử lý; cần benchmark thực tế. Dijkstra Single–Source của GDS dùng triển khai tuần tự, nên tăng **concurrency** của thuật toán đó không tự biến nó thành phiên bản song song.

Chọn Delta-Stepping khi workload thật cho thấy cần tốc độ Single–Source ở quy mô lớn, chứ không mặc định mọi trường hợp nó đều nhanh hơn Dijkstra.

## 8. Yen: lấy k tuyến thay thế theo tổng trọng số

Ứng dụng giao hàng hoặc dự phòng kết nối thường cần **nhiều tuyến**, để có thể chọn tuyến thứ hai khi tuyến tốt nhất không sử dụng được. **Yen's k-shortest paths** tìm tối đa **k** đường theo thứ tự **tổng trọng số** và tránh trả lại một đường đã được tìm. Khác với **SHORTEST k** trong Cypher, kết quả ở đây được xếp theo **chi phí trọng số**, không phải số hop.

~~~cypher
MATCH (source:DemoWeightedPlace {code: 'A'}),
      (target:DemoWeightedPlace {code: 'D'})
CALL gds.shortestPath.yens.stream(
  'demoWeightedRoutes',
  {
    sourceNode: source,
    targetNode: target,
    k: 3,
    relationshipWeightProperty: 'km'
  }
)
YIELD index, totalCost, nodeIds
RETURN index,
       totalCost AS totalKm,
       [nodeId IN nodeIds | gds.util.asNode(nodeId).code] AS route
ORDER BY index;
~~~

Ba tuyến trả về trên đồ thị ví dụ:

| Thứ tự | Đường | Tổng km |
|---|---|---:|
| 0 | A → E → F → D | 3 |
| 1 | A → C → D | 8 |
| 2 | A → B → D | 12 |

Tuyến trực tiếp A → D có chi phí **20 km** nên là phương án tiếp theo. Nếu đồ thị chỉ có ít hơn **k** đường hợp lệ, thuật toán không thể tạo thêm đường không tồn tại. Với các đường đồng hạng chi phí, không nên giả định thứ tự cố định giữa các kết quả nếu API không bảo đảm thứ tự phụ.

**Giới hạn:** càng tăng k, tổng chi phí tính toán thường càng lớn. Không dùng k = 1000 chỉ vì giao diện hiển thị ba gợi ý. Nếu cần các phương án thực sự độc lập về đường bộ, nút trung gian hoặc vùng địa lý, chỉ xếp **k** đường rẻ nhất có thể chưa đủ: các đường có thể dùng nhiều đoạn chung.

## 9. Chọn thuật toán phù hợp với điều kiện dữ liệu

| Thuật toán | Bài toán | Điều kiện quan trọng | Điểm cần cân nhắc |
|---|---|---|---|
| **BFS / Cypher SHORTEST** | Ít **hop** nhất | Mỗi cạnh coi như chi phí 1 | Không tối ưu km/phút khác nhau |
| **Dijkstra Source–Target** | Một nguồn → một hoặc nhiều đích | Trọng số không âm, mô hình cộng được | Phù hợp bài toán có mục tiêu rõ ràng |
| **Dijkstra Single–Source** | Một nguồn → mọi đích có thể tới | Trọng số không âm | Có thể tính nhiều hơn nhu cầu nếu chỉ hỏi một đích |
| **Delta-Stepping** | Một nguồn → mọi đích, cần song song | Trọng số không âm, cần tinh chỉnh delta | Benchmark cùng đồ thị và tài nguyên |
| **A\*** | Một nguồn → một đích, có heuristic hướng đích | Heuristic phải phù hợp với đơn vị trọng số và không đánh giá vượt chi phí thực nếu cần tối ưu | Có thể giảm tìm kiếm khi tọa độ tốt; không mặc định nhanh hơn mọi lúc |
| **Yen** | k đường thay thế theo tổng trọng số | Trọng số dương phù hợp, k vừa phải | Tốn hơn khi k lớn; các đường có thể chồng lắp |
| **Bellman–Ford** | Single–Source khi có trọng số âm | Không có chu trình âm reachable nếu muốn khoảng cách hữu hạn | Chậm hơn ở nhiều trường hợp; cần xử lý chu trình âm |

### 9.1. A*: dùng heuristic để ưu tiên hướng tìm kiếm

**A\*** đánh giá các node bằng chi phí đã đi **g(n)** cộng với ước lượng phần còn lại **h(n)**. Nếu **h(n)** là một cận dưới hợp lệ của chi phí từ n đến đích (*admissible heuristic*), A\* có thể giữ tính tối ưu trong những điều kiện tương ứng.

GDS A\* hỗ trợ dùng các property **latitude** và **longitude** của node làm thông tin tọa độ. Để thực hành cần **project cả hai thuộc tính tọa độ**, ngoài trọng số quan hệ, và chọn đơn vị chi phí nhất quán với heuristic. Với trọng số **km**, khoảng cách đường chim bay thường có thể đóng vai trò cận dưới nếu các cạnh biểu diễn quãng đường thực không thể ngắn hơn khoảng cách địa lý. Với trọng số **minutes**, không được đem số **km** cộng trực tiếp với **phút**.

Ví dụ **chỉ mang tính khung tham khảo**, cần có dữ liệu tọa độ thực và projection phù hợp mới chạy được:

~~~cypher
MATCH (s:GeoPlace {code: $from}),
      (t:GeoPlace {code: $to})
CALL gds.shortestPath.astar.stream(
  'geoRoutesWithCoordinates',
  {
    sourceNode: s,
    targetNode: t,
    latitudeProperty: 'latitude',
    longitudeProperty: 'longitude',
    relationshipWeightProperty: 'km'
  }
)
YIELD totalCost, nodeIds
RETURN totalCost AS totalKm, nodeIds;
~~~

**Không chạy đoạn này trên demoWeightedRoutes:** graph mẫu chưa có latitude/longitude. Thay vì gán tọa độ giả để làm đẹp kết quả, hãy dùng dữ liệu thực và xác minh heuristic phù hợp với hàm chi phí.

### 9.2. Bellman–Ford: cạnh trọng số âm và chu trình âm

Dijkstra không phù hợp cho đồ thị có trọng số âm. **Bellman–Ford** có thể tìm đường ngắn nhất từ một nguồn khi có cạnh âm và **không có chu trình âm reachable** làm chi phí giảm vô hạn. Ví dụ quan hệ “chi phí ưu đãi” âm có thể khiến việc đi vòng liên tục làm tổng chi phí ngày càng nhỏ; khi đó “đường tối ưu hữu hạn” không còn xác định theo mô hình cho phép lặp vòng.

Trong GDS, thủ tục **Bellman–Ford Single–Source** được tài liệu mô tả kèm cơ chế nhận diện chu trình âm. Đây là lựa chọn cho trường hợp thực sự có trọng số âm; không nên thêm trọng số âm vào projection mẫu đang dùng Dijkstra rồi tiếp tục tin kết quả.

## 10. Những yếu tố làm sai kết quả dù thuật toán chạy thành công

### 10.1. Hướng và loại relationship

Trong GDS projection, **NATURAL** tôn trọng hướng đã lưu. Ví dụ có cạnh A → B nhưng không có B → A thì kết quả đi ngược có thể không tồn tại. **UNDIRECTED** cho phép duyệt cả hai hướng và có thể biến một mạng giao thông một chiều thành mạng hai chiều giả.

Ngoài ra, chỉ nên project những loại quan hệ phù hợp: tuyến **ROAD**, **RAIL**, **AIR** hoặc **DEPENDS_ON** là các ý nghĩa khác nhau. Trộn chúng mà không định nghĩa hàm chi phí có thể tạo đường không hợp lệ về nghiệp vụ.

### 10.2. Cạnh thiếu, trọng số lỗi và giá trị đặc biệt

Trước khi chạy phải rà soát:

- Thuộc tính trọng số có mặt ở mọi cạnh được dùng.
- Giá trị là số **hữu hạn**, không phải STRING, null hoặc NaN.
- Không có cạnh âm nếu dùng Dijkstra/A\*/Yen theo giả định tương ứng.
- Giá trị 0 có hợp lệ theo miền dữ liệu hay không; trong bài ví dụ, mỗi cạnh có chi phí dương.
- Đơn vị nhất quán: **phút với phút**, **km với km**.
- Quy tắc cho nhiều relationship song song A → B: đó là hai phương án khác nhau hay dữ liệu trùng cần loại?

GDS projection có thể dùng giá trị mặc định cho property thiếu; chỉ chạy thành công bước projection **không chứng minh dữ liệu trọng số đã sạch**.

### 10.3. Projection là ảnh chụp dữ liệu, không tự đồng bộ theo mỗi giao dịch

Một named graph GDS nằm trong **graph catalog ở bộ nhớ** và **không tự cập nhật** mỗi khi transaction Cypher sửa property **km** hay thêm relationship trong database. Nếu thay đổi bảng cước hoặc đóng một tuyến sau khi project, kết quả của thuật toán trên projection cũ có thể **stale**.

Quy trình định tuyến có dữ liệu thay đổi cần định nghĩa chính sách:

1. Projection được tạo hoặc làm mới ở mốc thời gian nào?
2. Kết quả được phép trễ so với cập nhật giao thông bao lâu?
3. Làm sao xây projection mới, đổi sang tên/version mới và giải phóng projection cũ có kiểm soát?
4. Cần đánh giá lại tuyến trước khi thực hiện nghiệp vụ quan trọng hay không?

Đừng giả định một câu **SET r.km = ...** sẽ lập tức thay đổi kết quả của **gds.shortestPath.dijkstra.stream** trên named graph đã tồn tại.

### 10.4. Điều kiện ngoài tổng trọng số

Một số yêu cầu cần “đường ít km nhất **nhưng không đi qua vùng cấm**, tối đa ba lần chuyển tuyến, không quá 30 phút, không lặp node”. Những ràng buộc đó **không được giải quyết tự động** chỉ bằng cách đặt **relationshipWeightProperty: 'km'**.

Cần lọc dữ liệu phù hợp vào projection, đặt thêm mô hình trạng thái, kết hợp bước xác thực đường hoặc chọn thuật toán hỗ trợ ràng buộc. **Lọc sau khi tìm một đường tối ưu** đôi khi làm mất lời giải: đường hợp lệ thứ hai có thể rẻ hơn mọi đường còn lại mà không được tính lại.

### 10.5. Bài toán nhiều tiêu chí

Minimize **km** và minimize **minutes** đồng thời thường không có một đáp án tốt nhất tuyệt đối. Ví dụ A → E → F → D ít km, nhưng A → B → D ít phút. Một cách đơn giản là định nghĩa:

\[
\operatorname{score}(p)
= \alpha \cdot \operatorname{km}(p)
+ \beta \cdot \operatorname{minutes}(p)
\]

Trong đó \(\alpha,\beta\) có đơn vị/quy đổi nhất quán và phản ánh lựa chọn nghiệp vụ. **Đây là hàm mục tiêu mới**, không còn gọi là “ngắn nhất theo km” hoặc “nhanh nhất theo phút”. Nếu cần nhiều phương án Pareto, thiết kế phải trả các phương án không bị thống trị thay vì lấy một tuyến từ công thức tổng có trọng số duy nhất.

## 11. Hiệu năng, quyền truy cập và vòng đời projection

### 11.1. Ước lượng tài nguyên

Projection cần **RAM** cho node, relationship và các property đã nạp. Tối ưu bằng cách chỉ lấy nhãn, loại quan hệ và thuộc tính thật sự cần, thay vì project toàn bộ graph nếu bài toán chỉ xét mạng định tuyến.

Trước khi chạy thuật toán nặng, dùng các chế độ **estimate** của GDS khi được hỗ trợ; theo dõi dung lượng projection, thời gian tạo, **computeMillis**, mức sử dụng bộ nhớ và độ trễ p95 của luồng yêu cầu thực. Không đánh giá hiệu năng chỉ từ đồ thị thử nghiệm có 6 node.

**Dijkstra Source–Target** trong GDS được triển khai với hàng đợi ưu tiên và thực hiện trên **một luồng cho phép tính thuật toán**; tăng **concurrency** không phải cách cải thiện trực tiếp phần tính lõi của biến thể này. Nếu cần nhiều đích, ưu tiên cấu hình **targetNodes** hợp lý hoặc xem xét bài toán Single–Source.

### 11.2. Không nhầm stream, mutate và write

| Chế độ | Tác động | Nên dùng khi |
|---|---|---|
| **stream** | Trả kết quả để xem hoặc xử lý tiếp, không ghi đường mới | Tính tuyến theo yêu cầu |
| **mutate** | Ghi kết quả vào **named graph** trong bộ nhớ | Chuỗi xử lý bằng nhiều thuật toán GDS |
| **write** | Ghi quan hệ/thuộc tính kết quả vào **database** | Bài toán thật sự cần lưu kết quả và quản lý vòng đời |

Không dùng **write** chỉ để hiển thị một tuyến. Việc ghi kết quả có thể tạo thêm relationship tổng hợp, tiêu tốn dung lượng và gây nhầm lẫn với dữ liệu tuyến gốc nếu không đặt tên/kiểm soát rõ.

### 11.3. Kiểm tra và giải phóng projection thử nghiệm

~~~cypher
CALL gds.graph.list('demoWeightedRoutes')
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Sau khi hoàn tất bài thực hành, nếu không còn phiên nào khác dùng projection này:

~~~cypher
CALL gds.graph.drop('demoWeightedRoutes')
YIELD graphName
RETURN graphName;
~~~

Lệnh **gds.graph.drop** xóa **projection trong bộ nhớ**, **không xóa** sáu node hoặc tám relationship gốc trong database. Việc giữ projection lâu dài làm tăng chi phí bộ nhớ; hãy giải phóng những projection không còn được sử dụng.

Trong ứng dụng **Java Driver/Spring Data Neo4j**, tham số hóa **$from** và **$to** khi tìm node nguồn/đích; chỉ cho người dùng chọn tên projection hoặc property trọng số từ **danh sách được kiểm duyệt**. Người dùng không được tự đưa vào một tên graph tùy ý khiến ứng dụng truy vấn dữ liệu ngoài phạm vi cho phép. Tài khoản chạy GDS cần quyền gọi procedure và quyền đọc dữ liệu thích hợp, phụ thuộc cấu hình Neo4j/edition.

## 12. Các lỗi thường gặp và cách xử lý

| Lỗi / dấu hiệu | Nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Dijkstra cho A → D dù A → E → F → D có 3 km | Dùng Cypher shortestPath() ít hop thay vì tối ưu trọng số | Dùng GDS Dijkstra với **relationshipWeightProperty: 'km'** |
| Kết quả theo phút giống kết quả theo km dù dữ liệu khác nhau | Chưa đổi property trọng số khi chạy | Kiểm tra **relationshipWeightProperty** |
| **Unknown procedure gds...** | GDS chưa có, không tương thích hoặc thiếu quyền/nạp | Kiểm tra cài đặt, SHOW PROCEDURES và phiên bản |
| **Graph already exists** | Named graph đã project trước đó | Kiểm tra catalog; chỉ drop/recreate khi được phép |
| Có đường trong DB nhưng GDS không tìm thấy | Sai orientation, label, type hoặc projection cũ | Xem danh mục projection và dữ liệu nguồn |
| Chi phí bất thường | Sai đơn vị, thiếu property, trọng số âm/NaN, kiểu dữ liệu không phải số | Kiểm tra và chuẩn hóa dữ liệu trước projection |
| Kết quả vẫn cũ sau khi sửa relationship | Projection không được làm mới | Xây projection mới theo quy trình refresh |
| **Out of memory** khi project | Graph lớn, nhiều property, tài nguyên không đủ | Giảm tập dữ liệu, kiểm tra memory estimation, sizing |
| Truy vấn trả quá nhiều tuyến | Chọn Yen với k lớn hoặc tính Single–Source khi không cần | Chọn đúng thuật toán và giới hạn số phương án |
| Đường tìm được đi qua tuyến cấm | Projection chứa cạnh không hợp lệ | Lọc cạnh ngay trong projection hoặc mô hình ràng buộc |

## 13. Bài tập vận dụng

### Bài 1 — Ba cách hiểu “ngắn nhất”

Trên đồ thị mục 3, hãy dự đoán đường tối ưu và chi phí tương ứng cho ba mục tiêu: **ít hop**, **ít km**, **ít phút**. Chứng minh bằng bảng các tuyến và giải thích vì sao không thể dùng cùng một phép **shortestPath()** cho cả ba.

### Bài 2 — Tự chạy Dijkstra

Tạo projection chứa **km** và **minutes**, chạy Dijkstra từ A đến D theo từng trọng số, đối chiếu **totalCost**, **nodeIds** và **costs** với bảng. Đổi orientation sang **UNDIRECTED** ở một projection khác và giải thích sự khác nhau về những tuyến có thể đi.

### Bài 3 — Single–Source và trường hợp không thể tới

Tính khoảng cách tối thiểu từ A tới B, C, D, E, F. Sau đó chạy từ D tới A trên projection **NATURAL** và giải thích tại sao không thể mặc định có đường quay lại. Đừng coi trường hợp không có đường là khoảng cách bằng 0.

### Bài 4 — Các tuyến dự phòng

Chạy **Yen k = 3** theo **km**. Viết ba tuyến thu được và so sánh với câu hỏi “ba đường ít hop nhất”. Thảo luận vì sao ba tuyến được chọn vẫn có thể chồng lắp nhiều cạnh trên một graph khác.

### Bài 5 — Projection lỗi thời

Sau khi project, sửa **km** của cạnh A → D từ **20** thành **0.5** trong **database thử nghiệm** rồi chạy lại GDS trên projection cũ. Dự đoán kết quả; sau đó làm mới projection và kiểm tra đường đi mới. Khôi phục dữ liệu ví dụ nếu còn sử dụng cho bài tập khác.

### Bài 6 — Chọn thuật toán

Với mỗi trường hợp, chọn cách phù hợp và nêu giả định:

1. Mạng lưới giao hàng có trọng số km dương, một kho tới một khách hàng.
2. Một trung tâm tới hàng triệu điểm, muốn tận dụng xử lý song song.
3. Bản đồ có tọa độ chính xác, cần tìm tuyến tối ưu theo đơn vị tương thích với heuristic.
4. Cần năm tuyến thay thế theo tổng chi phí.
5. Có cạnh trọng số âm và cần phát hiện chu trình âm có thể tới từ nguồn.

## 14. Ghi nhớ

**Khoảng cách trong đồ thị phải được định nghĩa bằng hàm chi phí trước khi chọn thuật toán.** Cypher **SHORTEST** tối ưu số hop; với trọng số trên relationship, dùng **GDS Dijkstra** cho một tuyến hoặc khoảng cách từ một nguồn, **Yen** cho các tuyến thay thế, **A\*** khi có heuristic phù hợp, **Bellman–Ford** khi phải xử lý cạnh âm. Kết quả chỉ đúng trên **đồ thị được project**, với hướng, loại quan hệ, trọng số và thời điểm dữ liệu đã chọn.

Quy trình áp dụng vào production: **định nghĩa đơn vị chi phí → kiểm tra dữ liệu → chọn projection đúng nghĩa → chọn thuật toán theo mục tiêu → so kết quả với mẫu nhỏ → đo tài nguyên và tính mới của projection**. Mỗi bước cần được kiểm chứng; việc thuật toán chạy thành công chưa đủ chứng minh đó là tuyến nghiệp vụ tối ưu.

### Tài liệu chính thức

- [Neo4j Cypher Manual – Shortest paths và phân biệt GDS](https://neo4j.com/docs/cypher-manual/25/patterns/shortest-paths/)
- [Neo4j GDS – Dijkstra Source-Target Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
- [Neo4j GDS – Dijkstra Single-Source Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-single-source/)
- [Neo4j GDS – Yen’s Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/yens/)
- [Neo4j GDS – A* Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/astar/)
- [Neo4j GDS – Delta-Stepping Single-Source](https://neo4j.com/docs/graph-data-science/current/algorithms/delta-single-source/)
- [Neo4j GDS – Bellman-Ford Single-Source](https://neo4j.com/docs/graph-data-science/current/algorithms/bellman-ford-single-source/)
- [Neo4j GDS – Native graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
