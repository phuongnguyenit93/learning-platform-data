# Tìm đường đi ngắn nhất và lựa chọn cú pháp phù hợp phiên bản

Trong **Neo4j**, mô hình *property graph* biểu diễn thực thể bằng **node**, liên kết bằng **relationship**, và thuộc tính bằng các cặp khóa–giá trị. Khi truy vấn một mạng giao thông, hệ thống phụ thuộc, mạng xã hội hoặc luồng xử lý, câu hỏi thường gặp là: **đi từ node A đến node D qua ít liên kết nhất bằng cách nào?** Cypher cung cấp cả các hàm đường đi ngắn nhất lâu đời lẫn các **path selector** mới. Việc chọn đúng cú pháp phụ thuộc vào phiên bản Neo4j/Cypher và ý nghĩa của từ “ngắn nhất”.

## 1. Xác định đúng bài toán trước khi truy vấn

| Nhu cầu | Ý nghĩa | Công cụ thích hợp |
|---|---|---|
| Có đường nối A với D không? | Chỉ kiểm tra khả năng đi tới | Mẫu đường đi có giới hạn độ sâu, hoặc selector **ANY** ở phiên bản hỗ trợ |
| Một đường đi ít cạnh nhất | Tối thiểu số **hop** (relationship) | **shortestPath()** hoặc **SHORTEST 1** / **ANY SHORTEST** |
| Mọi đường đi đồng hạng ít cạnh nhất | Trả toàn bộ đường cùng số hop nhỏ nhất | **allShortestPaths()** hoặc **ALL SHORTEST** |
| Một số đường ngắn nhất hoặc các nhóm độ dài ngắn nhất | Lấy nhiều phương án theo thứ tự số hop | **SHORTEST k**, **SHORTEST k GROUPS** |
| Đường có tổng km, thời gian, chi phí thấp nhất | Tối thiểu **tổng trọng số** của các cạnh | Thuật toán có trọng số, ví dụ **Dijkstra** của Graph Data Science (GDS) |

**Điểm then chốt:** Cypher **shortestPath()/SHORTEST** mặc định tối ưu **số cạnh**, không cộng thuộc tính khoảng cách hoặc chi phí của cạnh. Một đường có ba hop có thể ngắn hơn về km so với đường hai hop.

Hướng cạnh cũng là một phần của điều kiện: mẫu **(a)-[:CONNECTS]->(b)** đi theo chiều relationship; **(a)-[:CONNECTS]-(b)** cho phép đi cả hai chiều.

## 2. Dựng đồ thị mẫu tự chứa

Chạy đoạn sau **một lần trên cơ sở dữ liệu thử nghiệm**; ví dụ dùng nhãn DemoStop và loại quan hệ CONNECTS để tránh nhầm với dữ liệu nghiệp vụ khác:

~~~cypher
CREATE
  (a:DemoStop {code: 'A'}),
  (b:DemoStop {code: 'B'}),
  (c:DemoStop {code: 'C'}),
  (d:DemoStop {code: 'D'}),
  (e:DemoStop {code: 'E'}),
  (f:DemoStop {code: 'F'})
CREATE
  (a)-[:CONNECTS {km: 4.0, active: true}]->(b),
  (b)-[:CONNECTS {km: 4.0, active: true}]->(d),
  (a)-[:CONNECTS {km: 10.0, active: false}]->(c),
  (c)-[:CONNECTS {km: 10.0, active: true}]->(d),
  (a)-[:CONNECTS {km: 1.0, active: true}]->(e),
  (e)-[:CONNECTS {km: 1.0, active: true}]->(f),
  (f)-[:CONNECTS {km: 1.0, active: true}]->(d);
~~~

Có ba đường đi có hướng từ A đến D:

| Đường đi | Số hop | Tổng km | Tình trạng |
|---|---:|---:|---|
| A → B → D | 2 | 8 | Các cạnh đều active |
| A → C → D | 2 | 20 | A → C không active |
| A → E → F → D | 3 | 3 | Các cạnh đều active |

Vì vậy, nếu **không lọc active**, đường ít hop nhất có **hai đáp án đồng hạng**: A → B → D và A → C → D. Nếu xét **tổng km**, đường A → E → F → D lại tối ưu hơn. Những kết quả này sẽ được dùng xuyên suốt bài.

## 3. Cú pháp tương thích Neo4j 4.x và các bản 5.x đầu tiên

Ở các phiên bản trước khi có path selector, Cypher dùng hai hàm:

- **shortestPath(pattern)**: chọn một đường đi có số hop nhỏ nhất giữa một cặp đầu–cuối; nếu nhiều đường đồng hạng thì đường được chọn **không bảo đảm cố định**.
- **allShortestPaths(pattern)**: trả tất cả các đường cùng số hop tối thiểu.

### 3.1. Lấy một đường đi ngắn nhất

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = shortestPath((s)-[:CONNECTS*1..6]->(t))
RETURN
  [n IN nodes(p) | n.code] AS stops,
  length(p) AS hops;
~~~

Giải nghĩa cú pháp:

1. **s** và **t** được tìm bằng nhãn và thuộc tính để xác định điểm đầu, điểm cuối.
2. **[:CONNECTS*1..6]** là quan hệ có độ dài biến thiên kiểu cũ, từ **1 đến 6** cạnh, theo chiều mũi tên.
3. **shortestPath(...)** chọn một đường có ít hop nhất trong phạm vi đã nêu.
4. **nodes(p)** là danh sách node trên đường; **length(p)** trả số relationship, **không phải tổng km**.

Kết quả có thể là A → B → D **hoặc** A → C → D, đều có **2 hop**. Không nên viết kiểm thử phụ thuộc vào việc hàm luôn chọn B.

### 3.2. Lấy tất cả các đường đồng hạng

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = allShortestPaths((s)-[:CONNECTS*1..6]->(t))
RETURN
  [n IN nodes(p) | n.code] AS stops,
  length(p) AS hops
ORDER BY stops;
~~~

Kết quả: **[A, B, D]** và **[A, C, D]**, mỗi đường 2 hop. Mệnh đề **ORDER BY** chỉ sắp xếp hàng đầu ra để dễ xem; nó không thay đổi cách chọn đường.

### 3.3. Lọc cạnh hợp lệ trước khi chọn đường

Một yêu cầu thực tế là chỉ đi qua các tuyến đang hoạt động:

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = allShortestPaths((s)-[:CONNECTS*1..6]->(t))
WHERE all(r IN relationships(p) WHERE r.active = true)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

Khi **WHERE** thuộc cùng mệnh đề **MATCH** chứa phép chọn đường ngắn nhất, điều kiện tham gia vào quá trình xét đường hợp lệ. Trong mẫu này, A → C → D bị loại, nên kết quả là **[A, B, D]** với 2 hop.

**Chú ý:** không được giả định rằng cứ tìm một đường ngắn nhất bất kỳ rồi lọc sau đó sẽ tương đương với tìm đường ngắn nhất **trong tập đường hợp lệ**. Nếu cần đường hợp lệ ngắn nhất, hãy đưa ràng buộc vào bước tìm kiếm.

## 4. Cú pháp path selector từ Neo4j 5.21

Neo4j 5.21 bổ sung cách diễn đạt gần với chuẩn GQL bằng các từ khóa **SHORTEST**, **ALL SHORTEST**, **SHORTEST k GROUPS**. Để biểu diễn số hop biến thiên, các ví dụ dưới dùng lượng từ trên relationship, chẳng hạn **-[:CONNECTS]->{1,6}** (từ 1 đến 6 cạnh). Cú pháp lượng từ này có từ Neo4j **5.9**; kết hợp với selector yêu cầu bản hỗ trợ selector, tức **5.21 trở lên**.

### 4.1. SHORTEST 1 hoặc ANY SHORTEST: lấy một đường

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 1 (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

Có thể viết tương đương:

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = ANY SHORTEST (s)-[:CONNECTS]->+(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

Ký hiệu **+** nghĩa là **một hoặc nhiều** cạnh và không đặt giới hạn trên tường minh; **{1,6}** đặt mức tối đa là sáu. Cả hai ví dụ lấy **một** trong hai đường 2 hop đồng hạng. Dùng dấu **+** khi bài toán thực sự cần độ dài không bị chặn và đã đánh giá chi phí tìm kiếm; dùng giới hạn trên khi có quy tắc nghiệp vụ về số bước.

### 4.2. ALL SHORTEST: lấy mọi đường có số hop nhỏ nhất

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = ALL SHORTEST (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops
ORDER BY stops;
~~~

Kết quả gồm **[A, B, D]** và **[A, C, D]**. Số hàng có thể lớn nếu đồ thị có nhiều đường đồng hạng; **ALL SHORTEST** không mang nghĩa “mọi đường đi có thể có”.

### 4.3. SHORTEST k: lấy k đường theo thứ tự số hop

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 2 (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops
ORDER BY hops, stops;
~~~

Ở đây có hai đường dài 2 hop nên lấy đủ hai đường đó. **k đếm số đường**, không đếm số mức độ dài. Nếu tại ranh giới chọn k có nhiều đường cùng độ dài, không nên phụ thuộc vào một thứ tự chọn cụ thể giữa các đường đồng hạng.

### 4.4. SHORTEST k GROUPS: lấy k nhóm độ dài

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 2 GROUPS (s)-[:CONNECTS]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops
ORDER BY hops, stops;
~~~

Kết quả gồm **ba đường**: nhóm độ dài 2 có hai đường A → B → D, A → C → D; nhóm độ dài 3 có một đường A → E → F → D. Ở đây **2 GROUPS có thể trả nhiều hơn 2 hàng**.

| Selector | Tiêu chí trả kết quả trên đồ thị mẫu |
|---|---|
| SHORTEST 1 / ANY SHORTEST | Một trong hai đường 2 hop |
| ALL SHORTEST | Cả hai đường 2 hop |
| SHORTEST 2 | Hai đường 2 hop |
| SHORTEST 2 GROUPS | Hai đường 2 hop **và** một đường 3 hop |

### 4.5. Lọc quan hệ trực tiếp trong mẫu hiện đại

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = ALL SHORTEST
  (s)-[r:CONNECTS WHERE r.active = true]->{1,6}(t)
RETURN [n IN nodes(p) | n.code] AS stops, length(p) AS hops;
~~~

Điều kiện trên từng relationship nằm ngay trong mẫu mở rộng, giúp loại cạnh không hoạt động khi tìm đường. Kết quả là **[A, B, D]**. Nếu cả A → B → D cũng bị chặn, thuật toán mới xét A → E → F → D với 3 hop, thay vì coi “không có đường” chỉ vì mọi đường 2 hop bị chặn.

## 5. Chọn cú pháp theo phiên bản và mục tiêu

| Neo4j / ngôn ngữ | Cú pháp nên dùng cho bài toán ít hop | Ghi chú tương thích |
|---|---|---|
| **Neo4j 4.x**, **5.0–5.8** | shortestPath(), allShortestPaths() với **[*1..n]** hoặc **[:TYPE*1..n]** | Chưa có quantified relationships hoặc SHORTEST selector mới |
| **Neo4j 5.9–5.20** | shortestPath(), allShortestPaths() | Có quantified path patterns/relationships, nhưng chưa có selector **SHORTEST** |
| **Neo4j 5.21 trở lên với Cypher 5** | Ưu tiên **SHORTEST 1**, **ALL SHORTEST**, **SHORTEST k/GROUPS** | Hàm cũ vẫn dùng được nhưng không theo cú pháp GQL |
| **Neo4j 2025.06 trở lên với Cypher 25** | Ưu tiên **SHORTEST** và lượng từ dạng **+**, **{m,n}** | Cypher 25 được giới thiệu từ 2025.06; ngôn ngữ mặc định tùy cấu hình/database |

Khi duy trì ứng dụng qua nhiều phiên bản:

1. Kiểm tra phiên bản máy chủ Neo4j **và** ngôn ngữ Cypher thực sự được cấu hình cho cơ sở dữ liệu.
2. Với mã phải chạy trên Neo4j 4.x hoặc 5.x trước 5.21, dùng cú pháp hàm cũ; đừng đưa **SHORTEST** vào truy vấn dùng chung.
3. Với hệ thống mới đã hỗ trợ, dùng selector để thể hiện rõ muốn **một đường**, **tất cả đường đồng hạng** hay **k nhóm độ dài**.
4. Trên những phiên bản cho phép chọn ngôn ngữ, có thể dùng tiền tố **CYPHER 5** cho truy vấn tương thích cũ hoặc **CYPHER 25** cho truy vấn tương ứng. Tiền tố này **không nâng cấp** được server cũ thành server hỗ trợ cú pháp mới.

Ví dụ khi chạy cú pháp cũ trên server đời mới có hỗ trợ Cypher 5:

~~~cypher
CYPHER 5
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = shortestPath((s)-[:CONNECTS*1..6]->(t))
RETURN [n IN nodes(p) | n.code] AS stops;
~~~

Không nên “chuyển đổi cơ học” **shortestPath()** thành **SHORTEST 1** nếu ứng dụng đang dùng điều kiện lọc hoặc nhiều đoạn path phức tạp: cần đối chiếu lại cách ràng buộc được áp dụng, độ dài tối thiểu, hướng cạnh và số dòng kết quả.

## 6. Nếu “ngắn nhất” nghĩa là ít km hoặc ít thời gian

Đường có **ít hop nhất** trong ví dụ là A → B → D hoặc A → C → D. Đường có **tổng km nhỏ nhất** lại là **A → E → F → D = 3 km**, dù đi qua 3 hop. Biểu thức kiểu **ORDER BY reduce(...) LIMIT 1** trên các đường được liệt kê thủ công có thể tăng số đường phải duyệt rất lớn, nên không phải cách mặc định cho bài toán có trọng số ở đồ thị lớn.

Khi cài **Neo4j Graph Data Science (GDS)**, có thể tạo *graph projection* rồi dùng Dijkstra. Ví dụ sau là **phần mở rộng tùy chọn**, không phải cú pháp Cypher lõi; cần cài GDS và chưa có projection trùng tên:

~~~cypher
CALL gds.graph.project(
  'demoRoutes',
  'DemoStop',
  {
    CONNECTS: {
      orientation: 'NATURAL',
      properties: 'km'
    }
  }
);
~~~

~~~cypher
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
CALL gds.shortestPath.dijkstra.stream('demoRoutes', {
  sourceNode: s,
  targetNodes: t,
  relationshipWeightProperty: 'km'
})
YIELD totalCost, nodeIds
RETURN
  totalCost AS km,
  [id IN nodeIds | gds.util.asNode(id).code] AS stops;
~~~

Kết quả kỳ vọng: **3 km**, **[A, E, F, D]**. Projection phải chứa đúng loại cạnh, hướng và các tuyến **được phép sử dụng**; trong hệ thống thật, cần bảo đảm các cạnh đóng (active = false) không được đưa vào projection phục vụ định tuyến. Dijkstra yêu cầu trọng số phù hợp với thuật toán, thông thường là số không âm; nếu cần tối ưu thời gian, dùng thuộc tính thời gian thay vì km.

## 7. Hiệu năng và các lỗi thường gặp

### 7.1. Thu hẹp hai đầu mút và số hop

Tìm một cặp node cụ thể thường hiệu quả hơn việc lấy mọi cặp nguồn–đích rồi tính đường ngắn nhất cho từng cặp. Trên dữ liệu sản xuất, nên dùng khóa nghiệp vụ có tính duy nhất và tạo constraint/index phù hợp:

~~~cypher
CREATE CONSTRAINT demo_stop_code IF NOT EXISTS
FOR (n:DemoStop)
REQUIRE n.code IS UNIQUE;
~~~

Khi source và target được xác định rõ, bộ lập kế hoạch có cơ hội dùng phép tìm kiếm từ hai phía. Có thể dùng **EXPLAIN** (xem kế hoạch, không chạy dữ liệu) hoặc **PROFILE** (thực thi và đo số dòng, db hits, thời gian) để đánh giá:

~~~cypher
PROFILE
MATCH (s:DemoStop {code: 'A'}), (t:DemoStop {code: 'D'})
MATCH p = SHORTEST 1 (s)-[:CONNECTS]->{1,6}(t)
RETURN length(p) AS hops;
~~~

Trong kế hoạch có thể gặp **ShortestPath**, **StatefulShortestPath(Into)** hoặc **StatefulShortestPath(All)** tùy mẫu, phiên bản và số cặp đầu–cuối. Đừng giả định mọi truy vấn SHORTEST sẽ dùng cùng một toán tử. Ràng buộc độ sâu **{1,6}** giúp giới hạn phạm vi, nhưng cũng **loại** lời giải nếu đường ngắn nhất thực tế có hơn 6 cạnh.

### 7.2. Phân biệt lọc trong lúc tìm với lọc sau khi tìm

Điều kiện có thể đánh giá trên từng cạnh, chẳng hạn **r.active = true**, thường có thể loại các nhánh không hợp lệ sớm. Điều kiện chỉ kiểm tra được sau khi biết toàn bộ đường đi có thể buộc bộ máy xét nhiều phương án hơn, thậm chí phải dùng tìm kiếm vét cạn. Đây là lý do nên đưa ràng buộc thích hợp vào relationship/node pattern hoặc cùng MATCH.

Ngược lại, nếu trước tiên tìm **một** đường ít hop rồi lọc bỏ vì tổng km quá lớn, truy vấn đó **không** tự chuyển sang trả đường tiếp theo có chi phí hợp lệ. Cần xác định rõ tiêu chí nằm trong bài toán tối ưu hay chỉ là bước sàng lọc kết quả.

### 7.3. Dữ liệu đầu vào và ngữ nghĩa

- **Không có đường:** MATCH đường đi ngắn nhất không trả hàng cho cặp nguồn–đích đó. Nếu API cần hiển thị “không tìm thấy”, xử lý trường hợp không có hàng hoặc dùng OPTIONAL MATCH khi thích hợp.
- **Hướng cạnh:** truy vấn có **->** sẽ không tự đi ngược chiều; nếu bài toán có hai chiều, phải mô hình hóa hoặc dùng mẫu không hướng có chủ đích.
- **Hai đầu mút trùng nhau:** đường dài 0 hop là một trường hợp nghiệp vụ riêng; hàm **shortestPath()** cũ có hạn chế khi hai đầu trùng nhau. Xử lý yêu cầu A → A rõ ràng, thay vì giả định mọi cú pháp đều cho cùng kết quả.
- **Nhiều đường đồng hạng:** shortestPath()/SHORTEST 1 không cam kết chọn cùng một đường sau mỗi lần chạy hoặc sau khi thay đổi dữ liệu. Dùng ALL SHORTEST nếu cần mọi phương án.
- **Kết quả quá lớn:** ALL SHORTEST hoặc SHORTEST k GROUPS có thể trả nhiều đường; cân nhắc phân trang, giới hạn phạm vi và yêu cầu người dùng thực sự.
- **Bảo mật tham số:** trong ứng dụng Java Driver hoặc Spring Data Neo4j, truyền **$from**, **$to** dưới dạng tham số để tránh ghép chuỗi từ dữ liệu người dùng; kiểm soát kiểu relationship và giới hạn chiều dài bằng cấu hình truy vấn được kiểm duyệt.

## 8. Thực hành và tự kiểm tra

1. Chạy **ALL SHORTEST** trên đồ thị mẫu, xác nhận có đúng hai đường 2 hop. Sau đó lọc **active = true** trong mẫu và giải thích vì sao chỉ còn A → B → D.
2. Chạy **SHORTEST 2 GROUPS**, xác nhận có ba hàng thay vì hai. Đổi thành **SHORTEST 2** và giải thích khác biệt giữa “2 đường” và “2 nhóm độ dài”.
3. Tìm đường A → D ít hop và đường A → D ít km; giải thích vì sao kết quả tối ưu khác nhau. Nếu hệ thống chưa cài GDS, có thể tính tổng km của **ba** đường mẫu để kiểm tra nhận định, nhưng không lấy cách liệt kê toàn bộ đường làm thiết kế cho dữ liệu lớn.
4. Thử đổi hướng query thành **D → A**. Với các cạnh có hướng trong dữ liệu mẫu, sẽ không có đường; giải thích vì sao bỏ hướng mũi tên có thể trả kết quả khác.

**Ghi nhớ:** trước mỗi truy vấn, xác định **tiêu chí tối ưu** (hop hay trọng số), **quy tắc đường hợp lệ** (hướng, loại cạnh, thuộc tính, giới hạn độ sâu), **số kết quả muốn lấy** (một, tất cả đồng hạng, k đường hay k nhóm), rồi mới chọn cú pháp tương thích **phiên bản Neo4j/Cypher**.

### Tài liệu chính thức

- [Neo4j Cypher 5 – Shortest paths](https://neo4j.com/docs/cypher-manual/5/patterns/shortest-paths/)
- [Neo4j Cypher 5 – Variable-length paths](https://neo4j.com/docs/cypher-manual/5/patterns/variable-length-paths/)
- [Neo4j Cypher 25 – Shortest paths](https://neo4j.com/docs/cypher-manual/25/patterns/shortest-paths/)
- [Neo4j Cypher – Additions, deprecations, removals, and compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/)
- [Neo4j Graph Data Science – Dijkstra Source-Target Shortest Path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
