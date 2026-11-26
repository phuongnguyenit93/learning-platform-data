# Độ trung tâm với PageRank và các thước đo mức độ ảnh hưởng

## 1. Từ đồ thị liên kết đến câu hỏi “ai có ảnh hưởng?”

Trong mô hình **property graph** của Neo4j, node biểu diễn thực thể và relationship biểu diễn liên kết giữa các thực thể. Với mạng người dùng, graph có thể lưu quan hệ theo dõi; với hệ thống học thuật, graph có thể lưu bài báo trích dẫn bài báo khác; với ứng dụng thương mại, graph có thể lưu website giới thiệu website khác hoặc sản phẩm được đề cập cùng nhau.

Các câu hỏi thường gặp là:

- Tài khoản nào có **nhiều người theo dõi** nhất?
- Tài khoản nào được **những người có uy tín** theo dõi, dù số follower không phải lớn nhất?
- Ai là **cầu nối** giữa hai cộng đồng ít tương tác?
- Node nào có khoảng cách ngắn đến nhiều node khác?
- Khi cần chọn một số tài khoản để ưu tiên phân tích, nên dựa vào thước đo nào?

Những câu hỏi này liên quan đến **centrality (độ trung tâm)**, nhưng không có một định nghĩa “ảnh hưởng” duy nhất cho mọi ứng dụng. **PageRank** đo mức độ quan trọng dựa trên cấu trúc liên kết có hướng và sự phân phối tầm quan trọng qua các liên kết. Những thước đo khác như **degree**, **betweenness**, **closeness** và **eigenvector centrality** phản ánh các khía cạnh khác nhau.

Bài học thuộc chương **Thuật toán đồ thị** của module Neo4j. Trọng tâm là mô hình hóa đúng hướng relationship bằng Cypher, hiểu ý nghĩa điểm số, tính PageRank với **Neo4j Graph Data Science (GDS)**, so sánh thước đo và sử dụng kết quả có trách nhiệm trong Java Driver/Spring Data Neo4j.

> **Giới hạn của điểm số:** Độ trung tâm là một đặc tính của **graph được chọn** theo **thước đo đã định nghĩa**. Nó không chứng minh một người là chuyên gia, đáng tin, có quyền lực thực tế hay có tác động tích cực. Diễn giải luôn phụ thuộc dữ liệu, hướng quan hệ, phạm vi và thời điểm.

## 2. Phân biệt các thước đo trung tâm

| Thước đo | Ý tưởng | Câu hỏi phù hợp | Điểm hạn chế đáng chú ý |
|---|---|---|---|
| **In-degree** | Đếm số relationship đi **vào** node | Ai được theo dõi/trích dẫn nhiều? | Xem mọi liên kết như nhau; không xét uy tín nguồn |
| **Out-degree** | Đếm số relationship đi **ra** node | Ai theo dõi hoặc trích dẫn nhiều? | Không đo trực tiếp mức độ được công nhận |
| **PageRank** | Điểm số đi qua các liên kết theo quá trình ngẫu nhiên | Ai nhận được liên kết từ những node quan trọng? | Nhạy với hướng/cấu trúc; không đo chất lượng nội dung |
| **Eigenvector centrality** | Một node có điểm cao khi nối với node có điểm cao | Ai kết nối với nhóm quan trọng? | Phụ thuộc cấu trúc thành phần/hướng và cách chuẩn hóa |
| **Betweenness centrality** | Node nằm trên bao nhiêu đường đi ngắn nhất giữa các cặp | Ai là cầu nối kết nối các nhóm? | Tốn chi phí với graph lớn; giả định đường ngắn nhất có ý nghĩa |
| **Closeness centrality** | Khoảng cách từ node đến các node khác | Ai có khả năng tiếp cận phần còn lại nhanh? | Graph không liên thông cần định nghĩa/chuẩn hóa phù hợp |

Hai node có thể **đồng hạng in-degree** nhưng **khác PageRank** vì chất lượng cấu trúc của người trỏ tới chúng khác nhau. Một node nối hai cụm có thể có **betweenness cao** mà không có nhiều người theo dõi. Vì vậy, lựa chọn thuật toán phải dựa trên **câu hỏi nghiệp vụ**, không phải tên thuật toán phổ biến nhất.

### 2.1. Đếm liên kết khác với đánh giá vị trí trong mạng

Giả sử tài khoản A có 20 follower đều là tài khoản mới ít liên kết; tài khoản B có 5 follower, nhưng mỗi follower lại được nhiều tài khoản có vị trí quan trọng theo dõi. In-degree sẽ ưu tiên A. PageRank có thể ưu tiên B vì điểm của nguồn liên kết được phân phối tới B.

Không thể khẳng định B luôn thắng: PageRank còn phụ thuộc **số liên kết đi ra của mỗi nguồn**, vòng liên kết, node không có cạnh đi ra, damping factor và toàn bộ cấu trúc graph.

## 3. Hướng relationship quyết định ý nghĩa điểm

Với social graph, định nghĩa:

~~~cypher
(a:Person)-[:FOLLOWS]->(b:Person)
~~~

nghĩa là **a theo dõi b**. Trong graph có hướng này, một cạnh hướng **từ người theo dõi sang người được theo dõi**.

Nếu PageRank truyền điểm **theo chiều cạnh**, node **b** nhận đóng góp từ **a**. Đây là quy ước hợp lý cho bài toán “ai được cộng đồng chú ý?”. Nếu lại thiết kế cạnh theo chiều **người được theo dõi → người theo dõi**, cùng thuật toán có thể đo hiện tượng khác.

Ví dụ:

~~~text
(An) ----FOLLOWS----> (Minh)
(Vy) ----FOLLOWS----> (Minh)
(Khoa) --FOLLOWS----> (Minh)
(Minh) --FOLLOWS----> (An)
(Lan) --FOLLOWS----> (Vy)
(Lan) --FOLLOWS----> (Minh)
(Linh) -FOLLOWS----> (An)
(Linh) -FOLLOWS----> (Khoa)
~~~

Minh có nhiều cạnh đi vào hơn An, nhưng điểm PageRank cụ thể phải được tính trên toàn mạng. Cạnh `FOLLOWS` ở đây chỉ phản ánh sự quan tâm thông qua theo dõi; không bảo đảm follower thật, tài khoản có hoạt động hay mối quan hệ có chất lượng.

### 3.1. Relationship có hướng và vô hướng

Trong GDS, một relationship có thể được **project** theo hướng gốc, đảo hướng hoặc dạng vô hướng, tùy mục đích thuật toán. Với PageRank:

- **Hướng gốc (NATURAL):** phù hợp khi cạnh đã đi từ “nguồn đề cử” sang “đối tượng được đề cử”.
- **Đảo hướng (REVERSE):** biến hướng chuyển điểm, có thể dùng cho câu hỏi đối xứng khác.
- **Vô hướng (UNDIRECTED):** xem hai đầu có thể đi tới nhau; ý nghĩa tương tự mạng tương tác hai chiều, không còn là uy tín do liên kết đi vào ban đầu.

**Không hoán đổi các hướng để “làm điểm đẹp hơn”**. Phải định nghĩa đúng thực tế dữ liệu rồi mới chọn cấu hình projection.

## 4. PageRank trực giác: “người lướt ngẫu nhiên”

Hãy tưởng tượng một người bắt đầu ở một node, chọn ngẫu nhiên một relationship đi ra để di chuyển sang node khác. Người này thường tiếp tục đi theo cạnh; thỉnh thoảng chuyển ngẫu nhiên tới một node trong graph để tránh bị mắc kẹt mãi trong một khu vực.

**PageRank** ước lượng mức độ một node được ghé thăm khi quá trình này diễn ra nhiều lần. Vì thế:

1. Node nhận nhiều link có thể được ghé thăm thường xuyên.
2. Link từ node vốn thường được ghé thăm có đóng góp đáng kể.
3. Nếu một node trỏ đến rất nhiều nơi, đóng góp theo mỗi cạnh được phân chia.
4. Việc “nhảy ngẫu nhiên” cho phép node không được trỏ trực tiếp vẫn nhận một phần điểm và góp phần xử lý các khu vực tách rời.

Thuật toán được đề xuất ban đầu trong bối cảnh xếp hạng trang web, nhưng có thể áp dụng cho nhiều loại mạng có cạnh thể hiện một hình thức giới thiệu, tham chiếu hoặc chú ý.

### 4.1. Công thức cơ bản

Với graph có `N` node, **damping factor** `d`, và `In(v)` là tập node có cạnh đi vào `v`, dạng trực giác của PageRank khi các node nguồn đều có ít nhất một cạnh đi ra là:

\[
PR(v)=\frac{1-d}{N}+d\sum_{u\in In(v)}\frac{PR(u)}{outDegree(u)}
\]

Trong đó:

- `PR(v)` là điểm PageRank của node `v`.
- `d` là xác suất tiếp tục theo cạnh, thường dùng giá trị minh họa **0,85**.
- `outDegree(u)` là số cạnh đi ra khỏi `u`.
- `PR(u) / outDegree(u)` là đóng góp từ nguồn `u` khi chọn đều giữa các cạnh đi ra.

Các lần lặp cập nhật điểm cho tới khi đạt giới hạn lặp hoặc điều kiện hội tụ theo triển khai. Vì PageRank phụ thuộc toàn graph, **không** thể chỉ đếm hàng xóm trực tiếp để tính chính xác điểm trong mọi tình huống.

**Lưu ý với node không có cạnh đi ra (dangling node):** mẫu số `outDegree = 0` không được dùng trực tiếp. Một cách diễn giải toán học thường gặp là tái phân phối khối lượng xác suất của các node đó theo quy tắc teleportation. Các thư viện có thể xử lý chuẩn hóa và hội tụ theo chi tiết triển khai riêng; không tự khẳng định tổng score hoặc khoảng score của GDS giống hệt mọi sách giáo khoa.

### 4.2. Tại sao hệ số d quan trọng?

Nếu `d` nhỏ, ảnh hưởng của thành phần nhảy ngẫu nhiên lớn; sự khác biệt do cấu trúc liên kết thường giảm. Nếu `d` lớn, đường đi qua các cạnh đóng vai trò quan trọng hơn; vùng graph dày đặc hoặc có vòng liên kết có thể giữ ảnh hưởng mạnh hơn.

Giá trị **0,85** là lựa chọn khởi đầu phổ biến, không phải hằng số bắt buộc. Hãy kiểm tra tính ổn định của thứ hạng với các giá trị hợp lý khi kết quả được dùng để ra quyết định quan trọng.

### 4.3. Node có điểm cao không nhất thiết có nhiều cạnh

Ví dụ, An chỉ nhận link từ Minh nhưng Minh là node nhận nhiều link quan trọng. An có thể nhận một phần PageRank đáng kể. Ngược lại, một node có nhiều follower nhưng follower luôn trỏ tới hàng trăm node khác có thể nhận đóng góp nhỏ trên từng cạnh.

Điểm này giải thích vì sao **PageRank đo cấu trúc uy tín được truyền**, còn **in-degree đo số lượng liên kết trực tiếp**.

## 5. Chuẩn bị đồ thị thử nghiệm trong Neo4j

Các câu lệnh ghi sau đây dành cho **database thực hành riêng**. Nhãn `InfluenceDemoUser` được đặt rõ để không trộn với nhãn `Person` nghiệp vụ.

### 5.1. Tạo sáu node thử nghiệm

~~~cypher
MERGE (an:InfluenceDemoUser {handle: 'an'})
MERGE (minh:InfluenceDemoUser {handle: 'minh'})
MERGE (vy:InfluenceDemoUser {handle: 'vy'})
MERGE (khoa:InfluenceDemoUser {handle: 'khoa'})
MERGE (lan:InfluenceDemoUser {handle: 'lan'})
MERGE (linh:InfluenceDemoUser {handle: 'linh'})
MERGE (an)-[:FOLLOWS]->(minh)
MERGE (vy)-[:FOLLOWS]->(minh)
MERGE (khoa)-[:FOLLOWS]->(minh)
MERGE (minh)-[:FOLLOWS]->(an)
MERGE (lan)-[:FOLLOWS]->(vy)
MERGE (lan)-[:FOLLOWS]->(minh)
MERGE (linh)-[:FOLLOWS]->(an)
MERGE (linh)-[:FOLLOWS]->(khoa);
~~~

Lệnh này tạo hoặc dùng lại các node theo `handle` trong graph thử nghiệm, rồi bảo đảm có các mẫu relationship `FOLLOWS` được chỉ định. Trong triển khai thực tế, tạo uniqueness constraint cho ID ổn định trước khi có nhiều worker cùng ghi:

~~~cypher
CREATE CONSTRAINT influence_demo_handle_unique IF NOT EXISTS
FOR (u:InfluenceDemoUser)
REQUIRE u.handle IS UNIQUE;
~~~

Nếu muốn tạo dữ liệu mới từ đầu, nên tạo constraint **trước** câu MERGE trong môi trường trống. Nếu graph đã có dữ liệu trùng `handle` thì câu tạo constraint có thể thất bại; cần xử lý trùng đúng nghiệp vụ.

Trong bài thực hành, chạy khởi tạo một lần trên database cô lập; việc MERGE lại không thay thế mọi kiểm tra concurrency hoặc quy tắc uniqueness dành cho dữ liệu thật.

### 5.2. Kiểm tra hướng và số cạnh

~~~cypher
MATCH (a:InfluenceDemoUser)-[r:FOLLOWS]->(b:InfluenceDemoUser)
RETURN a.handle AS follower,
       type(r) AS relationship,
       b.handle AS followed
ORDER BY follower, followed;
~~~

Với graph thử nghiệm mới tạo, kỳ vọng có **6 node và 8 relationship** kiểu FOLLOWS. Nếu đã có dữ liệu mang cùng nhãn hoặc cùng ID, số lượng thực tế cần được kiểm tra trước khi suy luận về kết quả thuật toán.

## 6. Dùng Cypher tính in-degree trước khi chạy PageRank

Đếm follower trực tiếp là điểm khởi đầu dễ kiểm chứng:

~~~cypher
MATCH (u:InfluenceDemoUser)
OPTIONAL MATCH (f:InfluenceDemoUser)-[:FOLLOWS]->(u)
RETURN u.handle AS handle,
       count(DISTINCT f) AS followerCount
ORDER BY followerCount DESC, handle ASC;
~~~

Với dữ liệu trên:

- Minh được **An, Vy, Khoa và Lan** theo dõi: in-degree = **4**.
- An được **Minh và Linh** theo dõi: in-degree = **2**.
- Vy được **Lan** theo dõi: in-degree = **1**.
- Khoa được **Linh** theo dõi: in-degree = **1**.
- Lan và Linh không có follower trong tập thử: in-degree = **0**.

**OPTIONAL MATCH** giữ cả các node không có follower. `count(DISTINCT f)` đếm **số node follower phân biệt**, không phải số relationship. Nếu mô hình có thể cho cùng cặp người dùng nhiều cạnh `FOLLOWS`, đếm relationship bằng `count(r)` sẽ cho đại lượng khác; cần chọn đúng cách đếm theo nghiệp vụ.

### 6.1. Out-degree trả lời một câu hỏi khác

~~~cypher
MATCH (u:InfluenceDemoUser)
OPTIONAL MATCH (u)-[:FOLLOWS]->(v:InfluenceDemoUser)
RETURN u.handle AS handle,
       count(DISTINCT v) AS followingCount
ORDER BY followingCount DESC, handle ASC;
~~~

Ở đây Lan và Linh có mỗi người **2** cạnh đi ra, trong khi Minh có **1**. Một người **theo dõi nhiều người** không đồng nghĩa là **được nhiều người theo dõi**.

Tránh tính cả in-degree và out-degree qua hai OPTIONAL MATCH trong cùng pipeline mà chưa tổng hợp riêng, vì các tổ hợp cạnh đi vào × đi ra có thể **nhân hàng**, làm sai phép đếm không dùng DISTINCT.

## 7. Graph Data Science: PageRank chạy trên projection

**Neo4j Graph Data Science (GDS)** là thư viện thuật toán và xử lý graph riêng, có yêu cầu cài đặt, quyền sử dụng và khả năng hỗ trợ phụ thuộc môi trường/phiên bản. Một Neo4j database thông thường **không mặc nhiên có tất cả procedure GDS**.

GDS thường tính thuật toán trên một **named graph projection trong bộ nhớ**, được dựng từ dữ liệu graph lưu trong Neo4j. Việc tạo projection **không đồng nghĩa sao chép node mới vào database**; nó tạo cấu trúc phục vụ thuật toán. Projection tiêu thụ bộ nhớ và có vòng đời cần quản lý.

Các ví dụ sau minh họa cú pháp phổ biến trong **GDS 2.x**; trước khi dùng ở môi trường thật, đối chiếu procedure/config của **phiên bản GDS đã cài**.

### 7.1. Tạo named graph từ node và relationship

~~~cypher
CALL gds.graph.project(
  'influenceDemoGraph',
  'InfluenceDemoUser',
  'FOLLOWS'
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Projection sử dụng label `InfluenceDemoUser` và relationship type `FOLLOWS` với hướng tự nhiên của cạnh (trong cấu hình đơn giản này). Trên dữ liệu ví dụ trống ban đầu, kỳ vọng **6 node và 8 relationship**.

Tên `influenceDemoGraph` là tên của một **projection trong GDS catalog**, không phải label, database name hoặc tệp CSV. Khi graph cùng tên đã tồn tại trong catalog hiện hành, cần quyết định sử dụng lại hay xóa projection cũ có kiểm soát trước khi tạo mới.

### 7.2. Tính PageRank và trả top node

~~~cypher
CALL gds.pageRank.stream(
  'influenceDemoGraph',
  {
    dampingFactor: 0.85,
    maxIterations: 40
  }
)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

Ý nghĩa:

- `gds.pageRank.stream` tính thuật toán trên graph projection và trả **dòng điểm số**, không tự ghi property mới vào node đã lưu.
- `nodeId` là định danh node trong projection. `gds.util.asNode(nodeId)` hỗ trợ lấy lại node Neo4j tương ứng trong các loại projection phù hợp.
- `score` là giá trị PageRank tính được.
- `ORDER BY score DESC` xếp node điểm cao trước.

Để giới hạn kết quả top 3:

~~~cypher
CALL gds.pageRank.stream('influenceDemoGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC
LIMIT 3;
~~~

**Không tự điền số PageRank “dự kiến”** nếu chưa chạy thuật toán: score phụ thuộc phép lặp, cấu hình và graph được project. Có thể kiểm tra rằng Minh có in-degree cao, nhưng điều đó không chứng minh thứ tự PageRank cuối cùng khi chưa tính.

### 7.3. Dạng tương đương khi cần điều chỉnh thuật toán

Các cấu hình thường cần cân nhắc:

| Tham số | Ảnh hưởng |
|---|---|
| `dampingFactor` | Mức độ ưu tiên đi theo relationship so với teleportation |
| `maxIterations` | Giới hạn số vòng lặp cho thuật toán |
| `tolerance` nếu phiên bản hỗ trợ | Ngưỡng hội tụ để kết thúc sớm khi điểm thay đổi đủ nhỏ |
| `relationshipWeightProperty` | Sử dụng trọng số cạnh đã được project |
| `concurrency` nếu được hỗ trợ | Mức song song thực thi và áp lực tài nguyên |

Kết quả có thể biến đổi giữa các cấu hình. Hãy ghi lại **phiên bản GDS, tên projection, cấu hình và thời điểm chụp graph** nếu cần kiểm toán hoặc tái lập bảng xếp hạng.

### 7.4. Giải phóng projection

Sau khi đã dùng xong projection thử nghiệm:

~~~cypher
CALL gds.graph.drop('influenceDemoGraph')
YIELD graphName
RETURN graphName;
~~~

Thao tác này giải phóng **named graph GDS trong bộ nhớ**. Nó **không xóa** các node/relationship của Neo4j database gốc.

Không drop projection đang được job khác sử dụng. Trong ứng dụng, nên có tên và vòng đời projection rõ ràng cho từng pipeline.

## 8. PageRank có trọng số: khi link không có sức nặng bằng nhau

Nhiều hệ thống có mức độ tương tác khác nhau, ví dụ:

- Liên kết từ một tài khoản hoạt động thường xuyên có độ tin cậy khác liên kết từ tài khoản mới.
- Một quan hệ trích dẫn được phân loại là trích dẫn trọng yếu hoặc chỉ nhắc đến.
- Độ mạnh của mối quan hệ được xây từ số lần tương tác, có giới hạn để tránh spam.

Khi dùng **weighted PageRank**, mỗi cạnh được gán trọng số không âm hợp lệ theo semantics và yêu cầu của GDS; thuật toán dùng trọng số để phân phối đóng góp từ node nguồn qua các cạnh đi ra. Để diễn giải như xác suất lựa chọn, dùng trọng số **dương** và tổng trọng số đi ra **lớn hơn 0**.

Cách diễn giải phần đóng góp từ `u` sang `v` có thể viết:

\[
PR(u)\cdot\frac{w(u,v)}{\sum_{(u,x)\in E}w(u,x)}
\]

Một cạnh từ nguồn chỉ có **một** cạnh đi ra vẫn nhận toàn bộ phần đóng góp theo đường đó, dù trọng số của riêng cạnh là 1 hay 3. Trọng số có tác dụng rõ khi nguồn có **nhiều lựa chọn đi ra**.

### 8.1. Gán trọng số minh họa

Trên graph demo, trước tiên gán mọi relationship FOLLOWS cùng trọng số:

~~~cypher
MATCH (:InfluenceDemoUser)-[r:FOLLOWS]->(:InfluenceDemoUser)
SET r.strength = 1.0;
~~~

Tăng trọng số của cạnh Lan → Minh (Lan còn một cạnh tới Vy):

~~~cypher
MATCH (:InfluenceDemoUser {handle: 'lan'})-[r:FOLLOWS]->
      (:InfluenceDemoUser {handle: 'minh'})
SET r.strength = 3.0;
~~~

Trong bài học này, trọng số 3 **chỉ có tính minh họa**, không phải công thức đo “sức ảnh hưởng thật”. Trên dữ liệu thực tế, phải xác định nguồn và quy tắc tính `strength`, loại bỏ dữ liệu gian lận, chuẩn hóa và kiểm tra phân phối trọng số.

### 8.2. Project thuộc tính cạnh và chạy weighted PageRank

~~~cypher
CALL gds.graph.project(
  'influenceWeightedGraph',
  'InfluenceDemoUser',
  {
    FOLLOWS: {
      orientation: 'NATURAL',
      properties: ['strength']
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

~~~cypher
CALL gds.pageRank.stream(
  'influenceWeightedGraph',
  {
    dampingFactor: 0.85,
    relationshipWeightProperty: 'strength',
    maxIterations: 40
  }
)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

Cần đảm bảo thuộc tính được project **trên tất cả relationship dùng trong thuật toán** và có kiểu số phù hợp. Nếu một số cạnh thiếu `strength`, tùy cấu hình projection có thể cần cung cấp giá trị mặc định hoặc làm sạch dữ liệu trước khi tạo graph; không mặc định GDS sẽ tự hiểu các cạnh thiếu bằng 1.0.

Sau thử nghiệm, có thể giải phóng projection:

~~~cypher
CALL gds.graph.drop('influenceWeightedGraph')
YIELD graphName
RETURN graphName;
~~~

### 8.3. Không nhầm trọng số tương tác với bằng chứng về uy tín

Nếu tài khoản A liên tục tạo hàng nghìn tương tác tự động với B, weighted PageRank có thể đẩy điểm B lên cao nếu strength tăng theo số tương tác một cách không kiểm soát. Cần có quy tắc chống gian lận, giới hạn trọng số, chọn khoảng thời gian và xác thực chất lượng dữ liệu trước khi dùng điểm xếp hạng trong sản phẩm.

## 9. Đối chiếu PageRank với betweenness centrality

**Betweenness** đo mức độ node nằm trên các **đường đi ngắn nhất** giữa các cặp node khác. Với graph gồm hai cộng đồng ít liên kết, node nối giữa hai cộng đồng có thể là “cầu” mà nhiều đường đi ngắn nhất đi qua.

Giả sử:

~~~text
Nhóm A:  A1 --- A2 --- A3
                  |
                  X
                  |
Nhóm B:  B1 --- B2 --- B3
~~~

Node X có thể có betweenness cao vì nhiều đường từ nhóm A tới nhóm B phải đi qua X. Nhưng X có thể chỉ có vài cạnh trực tiếp. Đó là vai trò **kết nối luồng di chuyển**, không giống “được đề cử bởi nhiều node quan trọng” của PageRank.

### 9.1. Tính betweenness bằng GDS

Trên projection demo đã tạo ở mục 7:

~~~cypher
CALL gds.betweenness.stream('influenceDemoGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

Nếu đã drop projection ở mục 7.4, phải tạo lại nó trước khi chạy ví dụ này.

**Diễn giải:** Betweenness dựa trên các đường đi ngắn nhất theo mô hình và hướng relationship của graph. Nếu graph có hướng nhưng hành vi kinh doanh cần đi hai chiều, kết quả sẽ khác đáng kể. Với graph lớn, tính chính xác betweenness có thể tốn nhiều tài nguyên; tùy phiên bản GDS có thể dùng chế độ ước lượng/sampling nếu được hỗ trợ và phù hợp yêu cầu.

### 9.2. Khi nào ưu tiên betweenness?

Phù hợp khi muốn:

- Phát hiện những điểm trung gian nối các cộng đồng.
- Xác định node có thể quan trọng với luồng kết nối hoặc truyền tin.
- Đánh giá điểm phụ thuộc trong đồ thị quy trình hoặc mạng kết nối.

Không nên dùng betweenness để kết luận node đó được cộng đồng tin cậy hoặc có nội dung chất lượng. Một nút cổ chai kỹ thuật cũng có thể có betweenness cao.

## 10. Closeness, eigenvector và các thước đo bổ sung

### 10.1. Closeness centrality: khoảng cách tới phần còn lại

**Closeness** thường dựa trên nghịch đảo tổng khoảng cách đường đi ngắn nhất từ một node đến những node khác có thể tới được. Nếu mỗi cạnh có thể đại diện cho một bước truyền thông tin, node gần nhiều node khác có thể có lợi thế về **khả năng tiếp cận nhanh**.

~~~cypher
CALL gds.closeness.stream('influenceDemoGraph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).handle AS handle,
       score
ORDER BY score DESC, handle ASC;
~~~

Với graph **không liên thông** hoặc **có hướng** và không phải mọi node đều tiếp cận được nhau, các định nghĩa closeness có thể xử lý node không tới được theo những cách khác nhau. **Không so sánh score một cách máy móc giữa những graph có cấu trúc kết nối khác nhau** mà chưa biết cách GDS định nghĩa điểm.

### 10.2. Eigenvector centrality: quan trọng vì nối với người quan trọng

Eigenvector centrality gán điểm theo ý tưởng **hàng xóm có điểm cao đóng góp nhiều hơn**. Khác với PageRank, công thức và chuẩn hóa thường dựa trên bài toán vector riêng của ma trận liên kết, không có cùng cơ chế teleportation để xử lý mọi đặc điểm cấu trúc của mạng có hướng.

Trong một số graph có hướng, phân rã thành thành phần, hoặc không liên thông, tính ổn định và khả năng diễn giải eigenvector có thể khác PageRank đáng kể. Dùng PageRank khi muốn một cơ chế lan truyền điểm có damping/teleportation dễ diễn giải; cân nhắc eigenvector khi mô hình mạng và yêu cầu toán học phù hợp.

Nếu phiên bản GDS cung cấp procedure eigenvector tương ứng, có thể tính trên cùng projection rồi so sánh thứ hạng. Kiểm tra danh mục thuật toán thực tế thay vì giả định mọi bản cài GDS đều có cùng phương thức.

### 10.3. Degree trung tâm: baseline rất hữu ích

Với graph nhỏ hoặc nhu cầu chỉ cần số follower, **in-degree bằng Cypher** có thể đủ và dễ hiểu hơn chạy PageRank. Đừng triển khai pipeline GDS, cache và lịch recompute nếu KPI nghiệp vụ thực sự chỉ yêu cầu “bao nhiêu tài khoản phân biệt đang theo dõi người này”.

Ở graph lớn, việc so sánh top PageRank với top in-degree cũng giúp kiểm tra thuật toán đang phản ánh đúng hiện tượng mong muốn hay bị chi phối bởi những cụm liên kết bất thường.

## 11. Viết điểm số ra Neo4j hay chỉ đọc kết quả?

GDS thường có các chế độ tính toán như **stream** (trả kết quả), **stats** (thống kê) và các chế độ ghi/mutate tùy thuật toán. Với nhu cầu báo cáo hoặc thử nghiệm một lần, `stream` thường là lựa chọn đơn giản.

Nếu ứng dụng cần gọi API liên tục để lấy top tài khoản, có thể lưu score để truy vấn nhanh hơn sau khi tính theo lô. Trước khi lưu, phải xác định:

- Tên property, ví dụ `pageRankScore`.
- Projection nào đã dùng và được tạo từ dữ liệu ở thời điểm nào.
- Cấu hình damping factor, trọng số, số lần lặp.
- Ngày giờ tính và phiên bản thuật toán.
- Khi nào score hết hiệu lực và được tính lại.

Ví dụ với GDS 2.x có thể sử dụng write mode:

~~~cypher
CALL gds.pageRank.write(
  'influenceDemoGraph',
  { writeProperty: 'pageRankScore' }
)
YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
~~~

**Cảnh báo:** Đây là thao tác **ghi property vào database** đối với những node được chiếu. Chỉ dùng trong database thực hành hoặc pipeline được phê duyệt và có chiến lược cập nhật. Khi chạy lại với cấu hình khác, property `pageRankScore` cũ có thể bị thay thế; các ứng dụng đọc cần biết phiên bản dữ liệu.

### 11.1. Score là ảnh chụp theo thời gian

Nếu graph thay đổi sau khi tính xong, property lưu PageRank **không tự động cập nhật** chỉ vì có relationship mới. Nếu sử dụng PageRank trong sản phẩm, cần quyết định lịch tính lại:

- Theo ngày/giờ khi đồ thị thay đổi vừa phải.
- Sau khi một lô dữ liệu nhập hoàn tất.
- Theo ngưỡng số lượng thay đổi đáng kể.
- Trên graph được chọn trong một cửa sổ thời gian.

Không nên hứa tính lại toàn bộ PageRank sau mọi relationship write nếu chưa đo chi phí.

### 11.2. Không coi score từ hai projection khác nhau là cùng thang đo

Nếu một projection có 100 nghìn node còn projection khác chỉ có 1 nghìn, hoặc hai bản chạy dùng trọng số/damping khác nhau, không thể so điểm thô một cách vô điều kiện. Nếu cần bảng xếp hạng giữa nhóm, phải xác định cách **chuẩn hóa và đối chiếu trong cùng ngữ cảnh**.

## 12. PageRank trên graph có nhiều loại relationship

Một graph xã hội có thể lưu:

~~~text
(:Person)-[:FOLLOWS]->(:Person)
(:Person)-[:MENTIONS]->(:Person)
(:Person)-[:WORKS_WITH]->(:Person)
(:Person)-[:BLOCKS]->(:Person)
~~~

Không nên project **mọi loại relationship** rồi chạy PageRank mà không xét ý nghĩa:

- `FOLLOWS` có thể mang nghĩa quan tâm.
- `MENTIONS` có thể là trích dẫn tích cực hoặc phê bình.
- `WORKS_WITH` thường đối xứng về nghiệp vụ dù lưu theo một hướng quy ước.
- `BLOCKS` không nên mặc nhiên được diễn giải là “bỏ phiếu tín nhiệm”.

Nếu trộn cạnh tiêu cực vào PageRank dương, tài khoản bị nhiều người chặn có thể tăng điểm theo một định nghĩa méo mó. Đầu tiên hãy chọn loại cạnh có ý nghĩa, quyết định hướng, sau đó cân nhắc trọng số.

### 12.1. Kết hợp với community detection

PageRank toàn graph có thể ưu tiên node ở cộng đồng rất lớn. Khi ứng dụng cần gợi ý người ảnh hưởng **trong từng cộng đồng/chủ đề**, có thể phân nhóm graph rồi so centrality trong phạm vi phù hợp.

Một kết quả **top PageRank toàn hệ thống** không nhất thiết giúp tìm một người có ảnh hưởng mạnh trong một cộng đồng nhỏ. Cần nêu rõ phạm vi phép đo khi hiển thị kết quả.

### 12.2. Lọc graph theo thời gian

Trong mạng theo dõi, cạnh tạo từ nhiều năm trước có thể không còn thể hiện sự tương tác hiện tại. Nếu nghiệp vụ quan tâm ảnh hưởng “30 ngày gần đây”, cần mô hình hóa hoặc chọn dữ liệu theo khoảng thời gian phù hợp trước khi project.

Tuy nhiên, **FOLLOWS** thường chỉ có thời điểm bắt đầu, không cho biết mức độ hoạt động. Một bài toán ảnh hưởng gần đây có thể cần loại cạnh sự kiện khác (ví dụ tương tác), cùng quy tắc chống spam, retention và cách tổng hợp trọng số.

## 13. Kiểm tra chất lượng dữ liệu trước khi tính trung tâm

Thuật toán có thể chạy thành công trên graph **sai dữ liệu**, tạo ra bảng xếp hạng có vẻ hợp lý nhưng không có giá trị.

### 13.1. Kiểm tra khóa và cạnh trùng

~~~cypher
MATCH (u:InfluenceDemoUser)
WITH u.handle AS handle, count(u) AS n
WHERE n > 1
RETURN handle, n;
~~~

Nếu trong graph có nhiều node cùng `handle` thì việc tính “ảnh hưởng của một người” đang bị tách thành nhiều đối tượng.

Đếm các cặp cạnh FOLLOWS trùng:

~~~cypher
MATCH (a:InfluenceDemoUser)-[r:FOLLOWS]->(b:InfluenceDemoUser)
WITH a.handle AS follower,
     b.handle AS followed,
     count(r) AS relationships
WHERE relationships > 1
RETURN follower, followed, relationships
ORDER BY relationships DESC;
~~~

Nếu mô hình quy định mỗi cặp chỉ có một FOLLOWS, cạnh trùng là lỗi cần xử lý. Với thuật toán, nhiều cạnh có thể làm thay đổi tổng trọng số hoặc mức đóng góp, nên không thể xem việc nhập trùng là vô hại.

### 13.2. Phân biệt nhiều tài khoản và nhiều người thật

Một cá nhân có thể sở hữu nhiều tài khoản; tài khoản giả có thể tạo ra cụm theo dõi bất thường. PageRank hoạt động trên **các node thực tế được project**, không tự suy ra danh tính thật.

Nếu score dùng để xếp hạng người dùng, cần có bước xác định dữ liệu đáng tin cậy, hạn chế spam/bot và cân nhắc ảnh hưởng của dữ liệu thiếu. Đây là phần của chất lượng mô hình, không phải thay đổi công thức PageRank.

### 13.3. Kiểm tra node cô lập và dangling node

~~~cypher
MATCH (u:InfluenceDemoUser)
WHERE NOT EXISTS {
    MATCH (u)-[:FOLLOWS]->(:InfluenceDemoUser)
}
RETURN u.handle AS handle;
~~~

Truy vấn tìm node **không có cạnh FOLLOWS đi ra trong phạm vi nhãn demo**. Với PageRank đây là trường hợp dangling node. Nó khác với **node cô lập** (không có cạnh vào lẫn cạnh ra).

Neo4j/GDS có cách xử lý các node này trong thuật toán, nhưng chúng vẫn ảnh hưởng đến điểm và cách diễn giải. Một projection bỏ sót relationship do lọc nhãn sai có thể vô tình tạo nhiều node dangling không mong muốn.

## 14. Dùng Java Driver để lấy bảng xếp hạng

Một API có thể đọc PageRank bằng GDS stream và chỉ trả các cột cần thiết cho frontend. Ví dụ Java Driver ở mức minh họa:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class InfluenceQueryService {
    public record InfluenceScore(String handle, double score) {}

    private final Driver driver;

    public InfluenceQueryService(Driver driver) {
        this.driver = driver;
    }

    public List<InfluenceScore> topInfluencers(
            String graphName, int requestedLimit) {
        if (graphName == null || graphName.isBlank()) {
            throw new IllegalArgumentException("graphName is required");
        }
        int limit = Math.max(1, Math.min(requestedLimit, 100));

        String cypher = """
            CALL gds.pageRank.stream(
                $graphName,
                { dampingFactor: $damping, maxIterations: $iterations }
            )
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).handle AS handle, score
            ORDER BY score DESC, handle ASC
            LIMIT $limit
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "graphName", graphName,
                    "damping", 0.85,
                    "iterations", 40,
                    "limit", limit
                )).list(row -> new InfluenceScore(
                    row.get("handle").asString(),
                    row.get("score").asDouble()
                ))
            );
        }
    }
}
~~~

Điều kiện sử dụng:

- Named graph `graphName` đã được tạo trong GDS catalog có thể được session truy cập.
- GDS procedure cần tồn tại, được cấp quyền và hỗ trợ các config tương ứng.
- Node được project có property `handle` khác null; nếu không, mapper phải xử lý giá trị thiếu.
- `session.executeRead` phù hợp với ví dụ `stream` chỉ đọc. Nếu đổi sang write mode, cần chọn transaction và quyền ghi phù hợp.
- `Driver` nên được tái sử dụng ở mức ứng dụng; `Session` có vòng đời ngắn.
- `limit` giới hạn **kết quả trả về**, không có nghĩa GDS chỉ tính PageRank cho đúng số node đó. Thuật toán vẫn cần xử lý graph projection theo cấu hình của nó.

Với **Spring Data Neo4j**, có thể dùng `Neo4jClient` với custom query và mapper sang DTO nếu API cần bảng xếp hạng. Không nhất thiết nạp đầy đủ aggregate entity và relationship để trả top score. Khi chỉ đọc điểm đã lưu, truy vấn có thể dùng `MATCH ... RETURN` thay cho chạy lại thuật toán trong mỗi HTTP request.

## 15. Hiệu năng và vận hành pipeline centrality

### 15.1. GDS không phải phép đếm nhỏ trong Cypher

Với graph vài node, các thuật toán rất dễ chạy. Khi graph có hàng triệu node và relationship, GDS cần tài nguyên để:

1. **Đọc và project** các node/relationship từ Neo4j vào graph trong bộ nhớ.
2. **Chạy nhiều vòng lặp** truyền PageRank qua cấu trúc liên kết.
3. **Trả hoặc ghi** kết quả điểm số.
4. **Giải phóng projection** khi hết nhu cầu.

Chi phí bộ nhớ thường tăng theo quy mô node/cạnh và property được project; thời gian tính còn phụ thuộc cấu hình, số vòng lặp và độ phức tạp của graph. Không nên suy ra một giá trị RAM hay thời gian chạy cố định chỉ từ số node.

### 15.2. Dùng kiểm tra bộ nhớ và tài nguyên

Một số procedure GDS có chế độ **estimate** để ước lượng bộ nhớ trước khi chạy; cú pháp và output tùy phiên bản. Trước job production, hãy kiểm tra khả năng estimate mà phiên bản đang triển khai hỗ trợ, theo dõi RAM, tải CPU và graph catalog.

Chỉ project **label, relationship type, property** thực sự cần. Với PageRank không trọng số, nếu không dùng bất kỳ property nào trên cạnh thì đừng nạp toàn bộ property chuỗi/dữ liệu lớn một cách không cần thiết.

### 15.3. Chọn lịch tính phù hợp

| Loại nhu cầu | Chiến lược tham khảo |
|---|---|
| Phân tích một lần | Projection → stream → xuất báo cáo → drop |
| Dashboard cập nhật theo ngày | Tính theo batch có lịch, lưu score kèm timestamp |
| API yêu cầu độ trễ thấp | Đọc score đã tính thay vì chạy toàn graph mỗi request |
| Graph cập nhật liên tục | Cân nhắc chu kỳ cập nhật và mức chấp nhận score cũ |
| Graph lớn, nhiều cộng đồng | Chọn graph con/thuật toán phù hợp, kiểm tra chi phí và bias |

Không có một lịch recompute đúng cho mọi ứng dụng. **PageRank là score của trạng thái graph tại thời điểm tính**; hiển thị score mà không biết thời điểm và phạm vi có thể gây hiểu lầm.

### 15.4. Đo độ ổn định thay vì chỉ xem top 1

Khi thay đổi damping hoặc lọc relationship, hãy so:

- Tỷ lệ trùng nhau của **top 10/top 100**.
- Mức biến động thứ hạng giữa hai lần chạy.
- Sự nhạy cảm khi bỏ tài khoản nghi vấn hoặc cạnh trùng.
- Chênh lệch giữa PageRank và in-degree.
- Tính giải thích được của các node lên/xuống hạng.

Nếu top thay đổi mạnh vì một vài cạnh dữ liệu mới, cần kiểm tra đây là tín hiệu nghiệp vụ thật hay do dữ liệu thiếu/sai.

## 16. Những nhầm lẫn thường gặp

**“PageRank chỉ là đếm follower.”** Sai. Nó phân phối điểm từ nguồn liên kết dựa trên cấu trúc mạng và damping; in-degree chỉ đếm cạnh trực tiếp.

**“Cứ nhiều cạnh đi ra là có PageRank cao.”** Không đúng với quy ước FOLLOWS từ follower tới người được theo dõi. Cạnh đi ra phân phối điểm của node nguồn sang node khác; hướng quan hệ phải được xem xét.

**“Score cao nghĩa là người đó có chất lượng nội dung cao.”** Sai. Score không tự kiểm định chất lượng, tính xác thực hoặc ý nghĩa đạo đức của hành vi.

**“GDS đã có sẵn trong mọi Neo4j database.”** Không nên giả định. GDS là thư viện cần cài đặt/cấp quyền theo môi trường và phiên bản.

**“PageRank.stream lưu luôn score vào node.”** Không. Stream chỉ trả kết quả. Muốn lưu property cần thao tác ghi có chủ đích và kiểm tra quyền, tác động dữ liệu.

**“Chỉ cần LIMIT 10 thì thuật toán chỉ chạy trên 10 node.”** Không. LIMIT giới hạn hàng trả về sau khi tính; chi phí thuật toán có thể vẫn trải trên graph đã project.

**“Thêm FOLLOWS chiều ngược giúp tính nhanh hơn.”** Không có cơ sở chung. Việc đảo/tạo thêm cạnh làm thay đổi dữ liệu và ý nghĩa phép đo; muốn phân tích hướng ngược có thể thay đổi orientation projection theo thiết kế.

**“Có thể trộn FOLLOWS, BLOCKS và MENTIONS rồi PageRank đo tín nhiệm.”** Không chính xác. Mỗi loại relationship mang ngữ nghĩa khác; cần chọn và định nghĩa trước khi tính.

**“Hai score từ hai graph khác nhau luôn so được.”** Sai. Phạm vi graph, chuẩn hóa, tham số và cách tính ảnh hưởng tới ý nghĩa score.

**“Chạy lại PageRank tự cập nhật thuộc tính đã lưu từ hôm qua.”** Không. Cần một job ghi có kiểm soát hoặc cơ chế cập nhật score theo pipeline.

## 17. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài 1. Chọn đúng hướng FOLLOWS

Một node A theo dõi B. Bạn muốn PageRank ưu tiên node **được** nhiều tài khoản quan trọng theo dõi.

**Câu hỏi:** Nên chọn cạnh nào?

**Gợi ý:** `(A)-[:FOLLOWS]->(B)` và project theo hướng tự nhiên. Điểm của A có thể chuyển theo chiều A → B.

### Bài 2. In-degree và PageRank có giống nhau?

Node P được 30 tài khoản ít liên kết theo dõi; node Q được 4 tài khoản có vị trí quan trọng theo dõi.

**Câu hỏi:** Nếu P có in-degree cao hơn, có kết luận P cũng có PageRank cao hơn không?

**Đáp án:** Không. PageRank còn xét cấu trúc liên kết và lượng điểm nguồn phân phối trên các cạnh đi ra. Cần tính trên graph đầy đủ.

### Bài 3. Phát hiện cầu nối

Bạn có hai nhóm hầu như không tương tác, chỉ có một node trung gian nối các đường đi giữa nhóm.

**Câu hỏi:** Degree, PageRank hay betweenness phù hợp nhất để đo vai trò “cầu nối”?

**Đáp án:** **Betweenness centrality** là lựa chọn trực tiếp hơn cho vai trò nằm trên các đường ngắn nhất; sau đó kiểm tra ý nghĩa của đường đi và hướng graph.

### Bài 4. Ý nghĩa của trọng số cạnh

Lan có hai cạnh đi ra: Lan → Minh với strength 3, Lan → Vy với strength 1.

**Câu hỏi:** Trong cách diễn giải xác suất theo trọng số, phần đóng góp của Lan sẽ phân chia như thế nào?

**Đáp án:** Theo tỷ lệ **3/4** sang Minh và **1/4** sang Vy (trước các thành phần khác của thuật toán). Đây là tỷ lệ trên các cạnh đi ra của Lan, không phải toàn bộ PageRank của Minh hay Vy.

### Bài 5. Node không có cạnh đi ra

Một node không theo dõi ai nhưng được nhiều tài khoản khác theo dõi.

**Câu hỏi:** Có thể bỏ qua node đó khi tính PageRank vì out-degree = 0 không?

**Đáp án:** Không. Nó vẫn có thể nhận điểm từ các cạnh đi vào; thuật toán phải xử lý dangling node theo quy tắc phù hợp.

### Bài 6. Graph projection và lưu dữ liệu

Bạn chạy `gds.pageRank.stream` và có các score, nhưng sau đó query `MATCH (u) RETURN u.pageRankScore` thì property không tồn tại.

**Câu hỏi:** Vì sao?

**Đáp án:** Stream chỉ trả hàng score, không ghi vào property. Cần lưu có chủ đích bằng write mode/pipeline phù hợp nếu muốn query property sau đó.

### Bài 7. API lấy top 10

Một endpoint gọi GDS stream rồi `LIMIT 10`.

**Câu hỏi:** Đã tối ưu thuật toán để chỉ xử lý 10 node chưa?

**Đáp án:** Chưa. LIMIT chỉ giới hạn kết quả đầu ra; GDS vẫn xử lý graph projection cần thiết để tính score.

### Bài 8. Thứ hạng tăng bất thường

Một tài khoản mới nhận 20.000 FOLLOWS chỉ sau vài phút và lọt top PageRank.

**Câu hỏi:** Có thể kết luận người này đang có ảnh hưởng lớn không?

**Gợi ý:** Cần kiểm tra bot/spam, tài khoản mới, cạnh trùng, trọng số, thời gian quan sát và chất lượng dữ liệu trước khi diễn giải score.

## 18. Ghi nhớ

**Degree** trả lời “có bao nhiêu liên kết trực tiếp?”, **PageRank** trả lời “node nhận bao nhiêu tầm quan trọng được phân phối qua các liên kết?”, **betweenness** trả lời “ai nằm giữa nhiều đường đi ngắn nhất?”, còn **closeness** đề cập khả năng tiếp cận mạng qua khoảng cách. Chúng đo **các vai trò khác nhau**, nên không thể thay thế nhau tùy tiện.

Để áp dụng PageRank trong Neo4j, hãy định nghĩa **relationship type và hướng** theo nghiệp vụ, kiểm tra khóa/trùng lặp, dựng **GDS named graph projection**, chạy `gds.pageRank.stream` với cấu hình rõ ràng, so với thước đo baseline và chỉ lưu score khi có nhu cầu vận hành. Điểm số chỉ có ý nghĩa trong phạm vi graph, dữ liệu và thời điểm được tính; việc kiểm chứng chất lượng dữ liệu và diễn giải kết quả quan trọng không kém câu lệnh Cypher.
