# Giới hạn độ sâu, hướng và loại quan hệ khi duyệt đồ thị

## 1. Vì sao duyệt đồ thị cần giới hạn?

Trong **Neo4j**, dữ liệu được tổ chức theo mô hình **property graph**: node biểu diễn thực thể, relationship biểu diễn liên kết có hướng và có loại, còn property mô tả thuộc tính. Cypher cho phép đi từ một node qua nhiều relationship để tìm người quen, phụ thuộc dịch vụ, đường đi, tuyến giao hàng hoặc ảnh hưởng của một sự kiện.

Nhưng một truy vấn duyệt quá rộng có thể tạo ra số lượng **đường đi ứng viên** rất lớn, dù số node đích khác nhau không nhiều. Vì vậy, trong chương **Tối ưu truy vấn** của module **DATABASE_ENGINE_GRAPH_NEO4J**, ba lựa chọn quan trọng nhất khi viết mẫu duyệt là:

1. **Độ sâu:** được phép đi qua tối thiểu và tối đa bao nhiêu relationship?
2. **Hướng:** đi theo chiều relationship, ngược chiều hay cả hai chiều?
3. **Loại relationship:** chỉ dùng những quan hệ nào có ý nghĩa đối với câu hỏi nghiệp vụ?

Ba giới hạn này vừa làm rõ **ý nghĩa kết quả**, vừa giúp Neo4j hạn chế không gian tìm kiếm. Chúng phải được chọn đúng theo nghiệp vụ; một truy vấn rất nhanh nhưng loại bỏ đường đi hợp lệ vẫn là truy vấn sai.

### 1.1. Số đường đi có thể tăng theo cấp số nhân

Giả sử trung bình mỗi node có **b** relationship phù hợp để đi tiếp. Khi xét đường đi có đúng **d** bước, số nhánh tối đa trong mô hình đơn giản có thể tăng gần theo **b^d**. Nếu lấy tất cả độ sâu từ 1 đến d, số đường tiềm năng có thể tăng gần như:

\[
  b + b^2 + \cdots + b^d
\]

Ví dụ minh họa với **b = 8**:

| Độ sâu | Số nhánh của riêng tầng đó, ước lượng |
|---|---:|
| 1 | 8 |
| 2 | 64 |
| 3 | 512 |
| 4 | 4.096 |
| 5 | 32.768 |

Đây **không phải công thức dự báo số đường thực tế**: đồ thị có chu trình, quan hệ trùng đích, các nhánh bị loại bởi hướng/loại và quy tắc không dùng lại cùng relationship trong một kết quả MATCH. Tuy nhiên, nó cho thấy vì sao tăng giới hạn độ sâu từ 3 lên 5 có thể khiến khối lượng công việc đổi rất mạnh.

**Phân biệt:** một node đích có thể xuất hiện qua nhiều đường đi khác nhau; do đó **số đường đi**, **số node đích duy nhất**, **số dòng trung gian** và **số dòng trả về** không phải một đại lượng.

## 2. Đồ thị ví dụ dùng xuyên suốt bài

Trong cơ sở dữ liệu **thử nghiệm**, tạo constraint và dữ liệu sau **một lần**. Không chạy đoạn CREATE nhiều lần vì sẽ tạo dữ liệu trùng.

~~~cypher
CREATE CONSTRAINT demo_traverse_code IF NOT EXISTS
FOR (n:DemoTraversePerson)
REQUIRE n.code IS UNIQUE;
~~~

~~~cypher
CREATE
  (a:DemoTraversePerson {code: 'A', enabled: true}),
  (b:DemoTraversePerson {code: 'B', enabled: true}),
  (c:DemoTraversePerson {code: 'C', enabled: true}),
  (d:DemoTraversePerson {code: 'D', enabled: true}),
  (e:DemoTraversePerson {code: 'E', enabled: true}),
  (f:DemoTraversePerson {code: 'F', enabled: true}),
  (a)-[:KNOWS {active: true}]->(b),
  (a)-[:KNOWS {active: true}]->(c),
  (b)-[:KNOWS {active: true}]->(d),
  (c)-[:KNOWS {active: false}]->(d),
  (a)-[:COLLEAGUE {active: true}]->(e),
  (e)-[:KNOWS {active: true}]->(d),
  (d)-[:KNOWS {active: true}]->(f);
~~~

Sơ đồ (mũi tên là hướng relationship đã lưu):

~~~mermaid
flowchart LR
  A((A)) -->|KNOWS, active| B((B))
  A -->|KNOWS, active| C((C))
  B -->|KNOWS, active| D((D))
  C -->|KNOWS, inactive| D
  A -->|COLLEAGUE, active| E((E))
  E -->|KNOWS, active| D
  D -->|KNOWS, active| F((F))
~~~

Các tuyến có hướng từ A đến D gồm:

| Tuyến | Số hop | Loại quan hệ | Tình trạng |
|---|---:|---|---|
| A → B → D | 2 | KNOWS, KNOWS | Cả hai active |
| A → C → D | 2 | KNOWS, KNOWS | C → D inactive |
| A → E → D | 2 | COLLEAGUE, KNOWS | Cả hai active |

**Hop** là một relationship được duyệt; đường A → B → D có **2 hop**, dù gồm **3 node**. Các truy vấn tiếp theo không cần xóa đồ thị để thử nhiều cách giới hạn.

## 3. Giới hạn độ sâu ngay trong mẫu Cypher

### 3.1. Cú pháp variable-length relationship tương thích Neo4j đời cũ

Truy vấn tìm người có thể đến từ A bằng một hoặc hai quan hệ **KNOWS** theo chiều mũi tên:

~~~cypher
MATCH (start:DemoTraversePerson {code: 'A'})
MATCH p = (start)-[:KNOWS*1..2]->(target:DemoTraversePerson)
RETURN
  target.code AS target,
  length(p) AS hops,
  [n IN nodes(p) | n.code] AS route
ORDER BY hops, target;
~~~

Biểu thức **[:KNOWS*1..2]** có ba thành phần:

- **KNOWS:** chỉ đi qua relationship thuộc loại KNOWS.
- **1..2:** đi tối thiểu **1**, tối đa **2** relationship.
- **->:** chỉ theo chiều **từ node đầu đến node cuối** của relationship đã lưu.

Với dữ liệu mẫu, có các đường **A → B**, **A → C** (1 hop), **A → B → D**, **A → C → D** (2 hop). Truy vấn **không** trả A → B → D → F vì phải đi 3 hop.

Các trường hợp độ sâu thường dùng:

| Mẫu Cypher truyền thống | Ý nghĩa |
|---|---|
| **[:KNOWS]** | Đúng một relationship |
| **[:KNOWS*2]** | Đúng hai relationship |
| **[:KNOWS*1..3]** | Một đến ba relationship |
| **[:KNOWS*0..3]** | Không đến ba relationship, gồm cả đường 0 hop |
| **[:KNOWS*]** | Từ một relationship trở lên, **không có giới hạn trên tường minh** |
| **[:KNOWS*2..]** | Từ hai relationship trở lên, **không có giới hạn trên tường minh** |

**Cảnh báo:** nếu không thực sự cần duyệt toàn bộ phạm vi có thể tới, tránh mẫu không giới hạn trên như **[*]** hoặc **[*1..]** trong các truy vấn có khả năng tạo nhiều đường. Dù quy tắc mặc định không lặp relationship hạn chế số đường trên một đồ thị hữu hạn, số đường có thể vẫn khổng lồ.

### 3.2. Độ sâu 0 có nghĩa gì?

~~~cypher
MATCH (start:DemoTraversePerson {code: 'A'})
MATCH p = (start)-[:KNOWS*0..2]->(target)
RETURN target.code AS target, length(p) AS hops
ORDER BY hops, target;
~~~

Vì giới hạn bắt đầu từ **0**, kết quả bao gồm chính **A** với **0 hop**, ngoài các đường dài 1–2 hop. Dùng **0..n** khi quan hệ “có thể tới trong tối đa n bước” cho phép chính node nguồn. Nếu người dùng muốn **ít nhất một liên kết**, bắt đầu từ **1**.

### 3.3. Cú pháp quantified relationship trong Neo4j 5.9 trở lên

Từ **Neo4j 5.9**, Cypher có **quantified relationships** và **quantified path patterns**. Truy vấn có thể viết:

~~~cypher
MATCH (start:DemoTraversePerson {code: 'A'})
MATCH p = (start)-[:KNOWS]->{1,2}(target:DemoTraversePerson)
RETURN target.code AS target, length(p) AS hops
ORDER BY hops, target;
~~~

**-[:KNOWS]->{1,2}** có nghĩa từ 1 đến 2 quan hệ KNOWS theo chiều đi ra. Lượng từ **{1,2}** đứng **sau** toàn bộ relationship pattern; nó không được viết giữa dấu ngoặc vuông như mẫu cũ.

| Mẫu truyền thống | Quantified relationship | Số hop |
|---|---|---|
| **-[:KNOWS*1..3]->** | **-[:KNOWS]->{1,3}** | 1–3 |
| **-[:KNOWS*2]->** | **-[:KNOWS]->{2}** | Đúng 2 |
| **-[:KNOWS*0..3]->** | **-[:KNOWS]->{0,3}** | 0–3 |
| **-[:KNOWS*]->** | **-[:KNOWS]->+** | Từ 1, không giới hạn trên |
| **-[:KNOWS*0..]->** | **-[:KNOWS]->*** | Từ 0, không giới hạn trên |

**Không nhầm dấu sao:** mẫu cũ **-[:KNOWS*]->** tối thiểu **1 hop**, còn mẫu quantified mới **-[:KNOWS]->*** cho phép **0 hop**. Đây là điểm cần đặc biệt chú ý khi chuyển cú pháp.

Trong một truy vấn cần tương thích **Neo4j 4.x hoặc Neo4j 5.0–5.8**, vẫn dùng mẫu **[*m..n]** truyền thống. Cú pháp quantified chỉ dùng khi máy chủ và ngôn ngữ Cypher đang chọn hỗ trợ.

## 4. Chỉ duyệt đúng hướng quan hệ

Cypher có ba cách chỉ định hướng cho một relationship:

| Mẫu | Hướng đi khi khớp mẫu |
|---|---|
| **(a)-[:KNOWS]->(b)** | Từ **a đến b** theo hướng đã lưu |
| **(a)<-[:KNOWS]-(b)** | Từ **b đến a** theo hướng đã lưu |
| **(a)-[:KNOWS]-(b)** | Chấp nhận relationship theo **cả hai hướng** |

Điều này cũng áp dụng cho đường dài nhiều hop. So sánh ba truy vấn có cùng điểm A và D:

### 4.1. Đi xuôi từ A tới D

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS*1..2]->(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Kết quả là **A → B → D** và **A → C → D**. Đường qua E bị loại vì chặng đầu là **COLLEAGUE**, không phải KNOWS.

### 4.2. Chỉ cho phép quan hệ trỏ vào A

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)<-[:KNOWS*1..2]-(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Kết quả **không có hàng**: dữ liệu mẫu không có tuyến có hướng KNOWS từ D quay về A. Nếu ứng dụng hiểu “A biết B” là hai chiều nhưng dữ liệu chỉ lưu **A → B**, cú pháp đi ngược sẽ không tự suy ra **B → A**.

### 4.3. Cho phép đi cả hai hướng

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS*1..2]-(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Truy vấn có thể duyệt các relationship KNOWS bất kể chiều lưu, nên vẫn tìm A–B–D và A–C–D. Cho phép đi hai chiều **không thay đổi** chiều relationship được lưu trong database, mà chỉ thay đổi **quy tắc khớp mẫu**.

**Tác động hiệu năng:** với một node có nhiều quan hệ vào và ra, mẫu vô hướng **-[]-** có thể phải xét nhiều ứng viên hơn mẫu có hướng **-[]->**. Tuy nhiên, độ lợi thực tế còn phụ thuộc độ phân bố quan hệ. Không đổi hướng chỉ để tăng tốc nếu nghiệp vụ cần đi cả hai chiều.

## 5. Chỉ duyệt đúng loại relationship

Trong property graph, các loại **KNOWS**, **COLLEAGUE**, **MANAGES**, **DEPENDS_ON**, **OWNS** mang ý nghĩa khác nhau. Bỏ điều kiện type có thể khiến truy vấn trộn những tuyến không hợp lệ về nghiệp vụ.

### 5.1. Giới hạn một loại

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH p = (s)-[:KNOWS*1..2]->(target)
RETURN target.code AS target, length(p) AS hops;
~~~

Neo4j chỉ mở rộng những relationship **KNOWS** theo hướng đã nêu. Ở đồ thị mẫu, đường A → E → D không được xét vì A → E là **COLLEAGUE**.

### 5.2. Cho phép một tập loại cụ thể

Trong mẫu truyền thống, dùng **|** để kết hợp những loại được phép:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS|COLLEAGUE*1..2]->(t)
RETURN [n IN nodes(p) | n.code] AS route
ORDER BY route;
~~~

Đoạn này cho phép **KNOWS hoặc COLLEAGUE ở từng hop**, nên trả ba tuyến A → B → D, A → C → D và A → E → D.

Với cú pháp quantified relationship (Neo4j 5.9+), giới hạn tương đương:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS|COLLEAGUE]->{1,2}(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Khi chỉ cần một tập loại hữu hạn, **ghi trực tiếp các loại vào relationship pattern** để bộ lập kế hoạch biết điều kiện mở rộng. Đừng dùng mẫu chung **-[*1..n]-** rồi lọc **type(r)** sau khi tạo đường nếu bạn đã biết rõ loại nào hợp lệ.

### 5.3. Loại relationship là quy tắc ở từng hop

Mẫu **[:KNOWS|COLLEAGUE*1..2]** có nghĩa **mỗi hop** được phép là KNOWS **hoặc** COLLEAGUE. Nó **không** bắt buộc toàn bộ đường chỉ có một loại duy nhất. Trong ví dụ A → E → D, chặng đầu là COLLEAGUE, chặng sau là KNOWS và vẫn khớp mẫu.

Nếu nghiệp vụ yêu cầu thứ tự loại cố định, hãy viết mẫu tương ứng:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH p = (s)-[:COLLEAGUE]->(colleague)-[:KNOWS]->(target)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Kết quả là A → E → D. Mẫu này rõ ràng và thu hẹp không gian tìm kiếm hơn cách cho phép mọi tổ hợp KNOWS/COLLEAGUE hai bước rồi lọc chuỗi loại ở cuối.

## 6. Phối hợp ba giới hạn với điều kiện trên property

Trong thực tế, chỉ những relationship **active = true** mới được phép đi qua. Nên đưa điều kiện này vào quá trình tìm đường khi cú pháp và phiên bản hỗ trợ.

### 6.1. Mẫu truyền thống, lọc trên toàn đường

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[:KNOWS*1..3]->(t)
WHERE all(r IN relationships(p) WHERE r.active = true)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Kết quả chỉ còn **A → B → D**. Tuy nhiên, biểu thức **all(...)** dùng danh sách relationship của đường đi hoàn chỉnh; tùy khả năng tối ưu và kế hoạch thực tế, hệ thống có thể phải tạo nhiều ứng viên rồi loại những đường chứa cạnh không active.

### 6.2. Inline relationship predicate trong cú pháp mới

Ở phiên bản hỗ trợ quantified relationships và relationship WHERE (Neo4j 5.9+), có thể đặt điều kiện **ngay tại bước mở rộng**:

~~~cypher
MATCH (s:DemoTraversePerson {code: 'A'})
MATCH (t:DemoTraversePerson {code: 'D'})
MATCH p = (s)-[r:KNOWS WHERE r.active = true]->{1,3}(t)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Đây là cùng bài toán nghiệp vụ: chỉ dùng **KNOWS**, đi **xuôi**, tối đa **3 hop** và chỉ đi qua quan hệ **active**. Điều kiện trên từng relationship có thể giúp cắt nhánh không hợp lệ **trong lúc mở rộng** thay vì sau khi đã lập đường. Với đồ thị mẫu, C → D không được chọn.

Nếu có điều kiện trên **node trung gian**, quantified path pattern cho phép viết predicate trực tiếp bên trong đoạn lặp, nhưng cần kiểm tra chính xác ngữ nghĩa của node đầu và cuối: điều kiện trong đoạn lặp có thể áp dụng cho một đầu mút ở **mỗi lần lặp**, không chỉ node ở giữa toàn tuyến.

**Không đồng nhất “lọc kết quả cuối” với “giới hạn đường hợp lệ”.** Nếu chỉ chọn một đường ngắn nhất rồi mới bỏ nó vì một cạnh inactive, hệ thống không tự có nghĩa vụ trả đường thay thế hợp lệ. Ràng buộc phải được đưa vào bài toán chọn đường từ đầu.

## 7. Neo4j có thể tối ưu thêm khi biết điểm đầu và điểm cuối

### 7.1. Bắt đầu từ node đã xác định rõ

So sánh:

~~~cypher
// Quét những cặp node và đường đi rất rộng.
MATCH p = (a:DemoTraversePerson)-[:KNOWS*1..3]->(b)
RETURN b.code, length(p);
~~~

với:

~~~cypher
// Xác định một điểm đầu cụ thể trước khi duyệt.
MATCH (a:DemoTraversePerson {code: $sourceCode})
MATCH p = (a)-[:KNOWS*1..3]->(b)
RETURN b.code, length(p);
~~~

Ở truy vấn thứ hai, **$sourceCode** được truyền bằng tham số từ ứng dụng Java Driver/Spring Data Neo4j; constraint duy nhất ở mục 2 cung cấp index hỗ trợ tìm **một** node nguồn. Như vậy, bộ máy chỉ phải duyệt từ nguồn cần quan tâm.

Khi cả nguồn và đích đã biết, ràng buộc cả hai:

~~~cypher
MATCH (a:DemoTraversePerson {code: $sourceCode})
MATCH (b:DemoTraversePerson {code: $targetCode})
MATCH p = (a)-[:KNOWS*1..3]->(b)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Bộ lập kế hoạch có thể chọn toán tử **VarLengthExpand(Into)** để nối hai đầu mút đã biết, tùy dữ liệu và phiên bản. Không có nghĩa mọi truy vấn sẽ dùng đúng một operator; cần đọc kế hoạch thực tế.

### 7.2. Chỉ cần tập node đích hay cần từng path?

Truy vấn trả đường:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*1..3]->(b)
RETURN b.code AS destination, [n IN nodes(p) | n.code] AS route;
~~~

có thể trả **nhiều hàng cho cùng b** do có nhiều path. Nếu chỉ cần danh sách đích duy nhất:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (a)-[:KNOWS*1..3]->(b)
RETURN DISTINCT b.code AS destination
ORDER BY destination;
~~~

Bỏ biến path và dùng **DISTINCT** giúp thể hiện nhu cầu đầu ra khác. Trong một số kế hoạch, Neo4j có thể chọn **VarLengthExpand(Pruning)** để tránh phát lại các end node trùng nhau. Nhưng **DISTINCT không bảo đảm rằng hệ thống không cần duyệt nhiều cạnh**: vẫn phải xem **PROFILE** để đánh giá tài nguyên.

### 7.3. Chỉ cần biết có đường hay không

Nếu giao diện chỉ hỏi “A có thể đến D trong tối đa 3 bước KNOWS không?”, truy vấn trả danh sách mọi path là thừa. Dùng biểu thức tồn tại:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
RETURN EXISTS {
  MATCH (a)-[:KNOWS*1..3]->(b)
} AS reachable;
~~~

Kết quả là **true** trên dữ liệu mẫu. Biểu thức **EXISTS** thể hiện rằng ứng dụng chỉ cần kết quả đúng/sai, cho phép công cụ thực thi dùng chiến lược phù hợp với bài toán tồn tại.

### 7.4. Nếu chỉ cần một đường ít hop nhất

Đừng mặc định dùng:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
MATCH p = (a)-[:KNOWS*1..4]->(b)
RETURN p
ORDER BY length(p)
LIMIT 1;
~~~

Truy vấn sắp xếp theo độ dài đường đi có thể phải xử lý rất nhiều đường ứng viên. Khi yêu cầu thực sự là **một đường có ít relationship nhất**, nên cân nhắc toán tử đường ngắn nhất chuyên dụng:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
MATCH p = shortestPath((a)-[:KNOWS*1..4]->(b))
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
~~~

Ở **Neo4j 5.21+** với Cypher hỗ trợ path selector:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (b:DemoTraversePerson {code: 'D'})
MATCH p = SHORTEST 1 (a)-[:KNOWS]->{1,4}(b)
RETURN [n IN nodes(p) | n.code] AS route,
       length(p) AS hops;
~~~

Trong dữ liệu mẫu, A → B → D và A → C → D đều có 2 hop, nên **một** đường ngắn nhất có thể là một trong hai tuyến. Nếu cần mọi đường đồng hạng, dùng **allShortestPaths()** hoặc **ALL SHORTEST** ở phiên bản hỗ trợ. Nếu cần tối thiểu **tổng km/giá tiền**, đó là bài toán đường đi có trọng số, không phải chỉ đơn thuần tối thiểu số hop.

## 8. EXPLAIN và PROFILE: chứng minh việc giới hạn có ích

### 8.1. Đo trước và sau thay đổi

Chạy truy vấn trong **database thử nghiệm**; dùng cùng dữ liệu và tham số để so sánh:

~~~cypher
EXPLAIN
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*1..5]->(b)
RETURN b.code, length(p);
~~~

~~~cypher
PROFILE
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*1..2]->(b)
RETURN b.code, length(p);
~~~

**EXPLAIN** chỉ lập kế hoạch, không chạy truy vấn; **PROFILE** thực thi và cung cấp phép đo, nên với câu lệnh ghi nó cũng có thể **thay đổi dữ liệu**. Chỉ dùng PROFILE cho truy vấn có khả năng gây tải khi đã đánh giá tài nguyên.

### 8.2. Những chỉ số cần đọc

| Chỉ số/toán tử | Cách diễn giải |
|---|---|
| **Estimated Rows** | Ước lượng số dòng do planner dự đoán, không phải kết quả đo |
| **Rows** | Số dòng thực tế mỗi toán tử sinh ra khi PROFILE |
| **DB Hits** | Số thao tác truy cập dữ liệu mức thấp; khác số dòng trả về |
| **Memory (Bytes)** | Bộ nhớ đỉnh của toán tử được hiển thị nếu có |
| **NodeUniqueIndexSeek** | Có thể xuất hiện khi xác định node theo khóa duy nhất |
| **VarLengthExpand(All)** | Mở rộng những đường có độ dài thay đổi từ node |
| **VarLengthExpand(Into)** | Tìm đường có độ dài thay đổi giữa hai node đã xác định |
| **VarLengthExpand(Pruning)** | Mở rộng với loại bỏ các end node trùng khi nhu cầu phù hợp |
| **Filter / Sort / Distinct** | Cho biết các bước lọc, sắp xếp hoặc khử trùng lặp có thể cần xử lý nhiều dòng |

Tên operator, phương thức runtime và khả năng tối ưu có thể khác nhau theo Neo4j/Cypher. **Không áp đặt** rằng một mẫu nhất định luôn có cùng execution plan trên mọi database.

Để đánh giá đúng: so sánh **cùng mẫu dữ liệu**, **cùng các tham số đại diện**, lượng dòng và DB Hits **ở từng toán tử**, không chỉ thời gian của một lần chạy. Với tập sáu node ở mục 2, sự khác biệt nhỏ có thể bị chi phối bởi overhead; phép đo tải lớn mới đáng tin cậy cho quyết định tối ưu.

### 8.3. Vì sao LIMIT không thay cho giới hạn độ sâu?

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH p = (a)-[:KNOWS*]->(b)
RETURN p
LIMIT 10;
~~~

**LIMIT 10** giới hạn số hàng **trả về**, không định nghĩa chiều dài đường tối đa. Tùy kế hoạch, bộ máy có thể dừng sớm sau khi có đủ hàng hoặc vẫn phải xử lý khối lượng lớn, nhất là khi có **ORDER BY**, **DISTINCT**, phép tổng hợp hay điều kiện áp dụng sau mở rộng.

Nếu nghiệp vụ chỉ cho phép tối đa ba quan hệ, hãy đặt **[*1..3]** hoặc **->{1,3}** **ngay trong mẫu**. Sau đó mới thêm **LIMIT** nếu giao diện cần giới hạn số hàng hiển thị.

## 9. Một quy trình tối ưu có thể áp dụng vào ứng dụng thật

| Bước | Câu hỏi | Ví dụ quyết định |
|---|---|---|
| **1. Xác định ý nghĩa** | Truy vấn tìm ảnh hưởng, quan hệ quản lý hay tất cả đường? | Chỉ những cạnh **DEPENDS_ON** |
| **2. Xác định nguồn/đích** | Có khóa nghiệp vụ đủ chọn lọc để neo điểm bắt đầu? | **Service.id = $sourceId** có index/constraint |
| **3. Đặt độ sâu** | Hệ thống thật cần xét tối đa mấy tầng? | 1–4 hop, theo yêu cầu nghiệp vụ |
| **4. Đặt hướng** | Có được đi ngược quan hệ đã lưu? | Phụ thuộc theo chiều **->** |
| **5. Chọn loại** | Những quan hệ nào hợp lệ ở từng hop? | **:DEPENDS_ON** thay vì quan hệ bất kỳ |
| **6. Lọc sớm** | Mỗi cạnh/node phải thỏa thuộc tính nào? | **r.enabled = true** ngay trong mẫu mới |
| **7. Chọn loại kết quả** | Cần mọi path, node đích duy nhất, boolean hay một shortest path? | **EXISTS** nếu chỉ cần kiểm tra |
| **8. Kiểm chứng** | Plan, DB Hits, số hàng, p95 trước/sau ra sao? | So sánh **PROFILE** trên workload đại diện |

### 9.1. Ví dụ phân tích phụ thuộc dịch vụ

Giả sử mô hình có quan hệ **(:Service)-[:DEPENDS_ON]->(:Service)**. Để tìm các dịch vụ bị phụ thuộc trực tiếp hoặc gián tiếp trong tối đa bốn tầng theo hướng lưu:

~~~cypher
MATCH (root:Service {serviceId: $serviceId})
MATCH (root)-[:DEPENDS_ON*1..4]->(dependency:Service)
RETURN DISTINCT dependency.serviceId AS serviceId
ORDER BY serviceId;
~~~

Tại sao mẫu này có thể tốt hơn **(root)-[*]-(anything)**?

- Neo **một** Service theo khóa được index.
- Hướng **->** phản ánh từ dịch vụ tới dependency, tránh đi sang chiều “phụ thuộc ngược” ngoài yêu cầu.
- Loại **DEPENDS_ON** loại các quan hệ như **OWNED_BY**, **RUNS_ON**, **MONITORED_BY**.
- Độ sâu tối đa **4** ngăn mở rộng sang những tầng chưa cần đến.
- **DISTINCT** phù hợp vì giao diện yêu cầu danh sách dịch vụ, không cần từng đường.

Tuy nhiên, nếu nghiệp vụ hỏi “những dịch vụ sẽ bị ảnh hưởng khi service X ngừng hoạt động?”, có thể cần duyệt **ngược** hướng **DEPENDS_ON**:

~~~cypher
MATCH (failed:Service {serviceId: $serviceId})
MATCH (affected:Service)-[:DEPENDS_ON*1..4]->(failed)
RETURN DISTINCT affected.serviceId AS affectedServiceId;
~~~

Cùng một loại relationship, nhưng **đảo hướng duyệt dẫn tới câu trả lời nghiệp vụ khác**. Đây là lý do tối ưu phải bắt đầu từ ngữ nghĩa dữ liệu, không chỉ từ chỉ số DB Hits.

### 9.2. Tránh tự ghép cú pháp từ đầu vào không tin cậy

Trong Java Driver hoặc Spring Data Neo4j, luôn dùng tham số **$serviceId** cho giá trị thuộc tính. Tuy nhiên, trong mẫu truyền thống, **độ sâu trên mệnh đề [*m..n]**, hướng mũi tên và loại relationship là một phần của **cấu trúc truy vấn**, không đơn giản thay bằng tham số giá trị.

Với API cho người dùng chọn độ sâu, ứng dụng nên giới hạn vào một tập cấu hình **đã kiểm soát** (ví dụ 1–2, 1–3 hoặc 1–4) rồi chọn mẫu Cypher tương ứng; kiểm tra dữ liệu đầu vào chặt chẽ. Không ghép trực tiếp chuỗi type, dấu mũi tên hoặc giới hạn từ input tùy ý thành câu truy vấn.

## 10. Các lỗi thường gặp khi duyệt đồ thị

1. **Không đặt giới hạn trên:** mẫu **[*]**, **->+** trên đồ thị kết nối dày có thể tạo cực nhiều đường, dù query cuối chỉ trả vài node.
2. **Dùng WHERE length(p) <= 3 thay cho bound rõ ràng:** đôi khi planner tối ưu được, nhưng viết giới hạn **trong mẫu** thể hiện ý nghĩa và cung cấp ràng buộc trực tiếp cho mở rộng.
3. **Quên hướng:** dùng **-[]-** không có nghĩa relationship trong dữ liệu hai chiều; nó chỉ cho phép truy vấn đi cả hai hướng.
4. **Quên loại:** **-[*1..3]-** có thể đi qua nhiều loại quan hệ không liên quan và làm tăng số nhánh.
5. **Nhầm hop với node:** **length(p)** đếm relationship, còn **size(nodes(p))** đếm node trên path, thường bằng số hop cộng một.
6. **Đường đi và node đích không đồng nhất:** **DISTINCT** kết quả có thể rất ít dù số path trung gian rất lớn.
7. **Nghĩ LIMIT kiểm soát chiều sâu:** LIMIT chỉ giới hạn hàng đầu ra; cần thêm bound trong pattern.
8. **Lọc trạng thái cạnh quá muộn:** điều kiện **active** đặt sau khi hình thành tất cả path có thể không tiết kiệm mở rộng; ưu tiên predicate inline khi phiên bản hỗ trợ.
9. **Giả định đường đi không thể quay lại node cũ:** mặc định Cypher không lặp **cùng relationship** trong một kết quả MATCH, nhưng **node có thể xuất hiện nhiều lần** qua các relationship khác nhau. Với Cypher 25 mới, có thêm path/match mode đặc biệt; không áp dụng giả định này mù quáng khi dùng **REPEATABLE ELEMENTS**.
10. **Chỉ nhìn thời gian chạy một lần:** không xem plan, độ chọn lọc và DB Hits dẫn đến kết luận thiếu căn cứ.

## 11. Bài tập vận dụng

### Bài 1 — Phân tích kết quả

Trên đồ thị mẫu, dự đoán các đường từ A đến D theo mỗi mẫu:

~~~cypher
MATCH (a:DemoTraversePerson {code: 'A'})
MATCH (d:DemoTraversePerson {code: 'D'})
MATCH p = (a)-[:KNOWS*1..2]->(d)
RETURN [n IN nodes(p) | n.code] AS route;
~~~

Sau đó đổi **KNOWS** thành **KNOWS|COLLEAGUE**, rồi thêm điều kiện chỉ đi qua relationship **active = true**. Giải thích vì sao số đường thay đổi.

### Bài 2 — Sửa truy vấn quá rộng

Đầu vào là:

~~~cypher
MATCH p = (a:DemoTraversePerson)-[*]-(b)
RETURN p
LIMIT 100;
~~~

Yêu cầu mới là “từ người A, tìm những người quen qua tối đa ba bước KNOWS, chỉ theo hướng quan hệ đã lưu”. Viết lại truy vấn có **neo source**, **hướng**, **type**, **bound** và chọn đầu ra phù hợp.

### Bài 3 — Đảo nghĩa nghiệp vụ khi đổi hướng

Cho dữ liệu **Service A DEPENDS_ON Service B**, **Service C DEPENDS_ON Service A**. Truy vấn nào tìm các dependency của A? Truy vấn nào tìm các service sẽ bị ảnh hưởng nếu A lỗi? Dùng hướng mũi tên để chứng minh.

### Bài 4 — Thử kế hoạch

Chạy **EXPLAIN/PROFILE** với độ sâu 1..2 và 1..4 trên một dataset đủ lớn trong môi trường thử nghiệm. Ghi **Rows**, **DB Hits**, toán tử mở rộng đường và p95 latency. Kiểm tra xem giới hạn độ sâu nào đủ theo yêu cầu nghiệp vụ và có lợi cho tài nguyên.

### Bài 5 — Chọn công cụ cho mục tiêu

Với cùng cặp source–target, viết ra mục tiêu phù hợp nhất cho ba câu hỏi: (a) có đường đi không, (b) cần một đường ít hop nhất, (c) cần mọi đường có tối đa ba hop. Cho biết vì sao trả mọi path rồi **ORDER BY ... LIMIT 1** chưa chắc tối ưu cho câu (b).

## Ghi nhớ

Giới hạn **độ sâu**, **hướng** và **loại relationship** ngay trong Cypher là cách trực tiếp để tránh duyệt lan rộng và giữ kết quả đúng ngữ nghĩa. Hãy bắt đầu từ node có định danh chọn lọc, đặt bound nghiệp vụ, chỉ mở rộng đúng chiều và đúng type, đưa predicate lên từng cạnh khi có thể, rồi chọn **path**, **node đích**, **EXISTS** hoặc **shortest path** theo nhu cầu đầu ra. Cuối cùng, dùng **EXPLAIN/PROFILE** để xác minh tác động thực tế thay vì suy đoán tốc độ từ cú pháp.

### Tài liệu Neo4j chính thức

- [Cypher 5 – Variable-length paths và quantified relationships](https://neo4j.com/docs/cypher-manual/5/patterns/variable-length-paths/)
- [Cypher – Variable-length paths, syntax và bounds](https://neo4j.com/docs/cypher-manual/current/patterns/reference/variable-length-paths/)
- [Cypher – Node and relationship patterns, directionality](https://neo4j.com/docs/cypher-manual/current/patterns/reference/node-and-relationship-patterns/)
- [Cypher – Understanding query plans, EXPLAIN và PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Cypher – Query plan operators](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/)
- [Cypher – Paths with unique relationships](https://neo4j.com/docs/cypher-manual/current/patterns/unique-relationship-paths/)
