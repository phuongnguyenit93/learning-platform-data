# Độ tương đồng, gợi ý liên kết và biểu diễn nút bằng vector

Trong một đồ thị, hai node có thể **giống nhau dù không có quan hệ trực tiếp**: hai khách hàng mua nhiều sản phẩm chung, hai bài viết được đọc bởi cùng nhóm người dùng, hoặc hai tài khoản tương tác với những chủ đề gần nhau. Các thuật toán đồ thị tận dụng cấu trúc liên kết và thuộc tính để định lượng độ tương đồng, gợi ý một liên kết chưa tồn tại và biểu diễn node thành vector số phục vụ tìm kiếm, phân cụm hoặc mô hình học máy.

Bài học thuộc chương **Thuật toán đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Neo4j dùng mô hình **property graph** gồm node, relationship, label và property; Cypher giúp truy vấn quan hệ, còn **Neo4j Graph Data Science (GDS)** cung cấp những thuật toán phân tích như Node Similarity, FastRP và kNN trên đồ thị được chiếu vào bộ nhớ. Việc tính toán kết quả thường cần kết hợp với index, constraint, truy vấn Cypher, Java Driver hoặc Spring Data Neo4j khi đưa vào ứng dụng.

Sau bài này, bạn có thể:

- Phân biệt **node similarity**, **link prediction** và **node embedding**.
- Tính và diễn giải Jaccard, common neighbors và các tín hiệu tương đồng cấu trúc.
- Tạo in-memory graph projection, dùng Node Similarity để khám phá cặp node giống nhau và tạo gợi ý liên kết bằng Cypher.
- Dùng FastRP tạo vector cấu trúc, so sánh bằng kNN và hiểu lúc nào nên dùng vector index.
- Đánh giá top-K, tránh rò rỉ dữ liệu khi huấn luyện dự đoán liên kết, xử lý cold start và những thiên lệch phổ biến.
- Thiết kế luồng thử nghiệm, triển khai và bảo trì kết quả thuật toán mà không làm mất tính đúng đắn của dữ liệu gốc.

## 1. Ba bài toán liên quan nhưng có đầu ra khác nhau

| Bài toán | Câu hỏi cần trả lời | Đầu ra | Ví dụ |
| --- | --- | --- | --- |
| **Độ tương đồng node** (*node similarity*) | Hai node giống nhau đến mức nào theo quan hệ hoặc thuộc tính? | Cặp node và điểm số. | U1 và U2 có nhiều sản phẩm từng mua chung. |
| **Gợi ý/dự đoán liên kết** (*link prediction*) | Giữa hai node hiện chưa nối trực tiếp, có nên đề xuất một cạnh không? | Cặp node ứng viên, điểm xếp hạng hoặc xác suất từ mô hình đã hiệu chỉnh. | Gợi ý U1 quan tâm sản phẩm P4. |
| **Biểu diễn node bằng vector** (*node embedding*) | Mã hóa cấu trúc/ngữ cảnh của node thành dãy số như thế nào? | Vector \((x_1,\ldots,x_d)\) cho mỗi node. | Vector 64 chiều của mỗi người dùng để tìm hàng xóm gần. |

Ba bài toán có thể kết hợp, nhưng **điểm tương đồng không phải xác suất sẽ phát sinh liên kết**, và **vector không tự biểu diễn đầy đủ ý nghĩa nghiệp vụ**. Ví dụ, hai khách cùng mua hàng thiết yếu có độ tương đồng cao nhưng chưa chắc nên được gợi ý kết bạn.

Một pipeline thường gặp:

~~~text
Node + relationship trong Neo4j
             |
             v
   Chọn loại cạnh, thời gian,
     tenant và node hợp lệ
             |
             v
      Graph projection GDS
             |
       +-----+------+
       |            |
       v            v
 Node Similarity   FastRP / Node2Vec
       |            |
       |            v
       |          Embedding
       |            |
       |            v
       |           kNN
       +-----+------+
             |
             v
   Lọc ứng viên chưa liên kết
   + quy tắc sản phẩm và quyền
             |
             v
   Xếp hạng, đánh giá, phục vụ
~~~

Đường đi thực tế có thể ngắn hơn: với bài toán nhỏ, Cypher và phép đếm hàng xóm chung đã đủ; không cần huấn luyện hay lưu embedding chỉ để trả một truy vấn đơn giản.

## 2. Đồ thị ví dụ: người dùng tương tác với sản phẩm

Ta dùng mô hình hai phía (*bipartite graph*):

~~~text
(:GdsDemoUser {userId})
       |
       | [:DEMO_INTERACTED]
       v
(:GdsDemoItem {itemId})
~~~

Dữ liệu thử nghiệm:

| Người dùng | Sản phẩm đã tương tác |
| --- | --- |
| U1 | P1, P2, P3 |
| U2 | P1, P2, P4 |
| U3 | P2, P4 |
| U4 | P5 |

U1 và U2 cùng quan tâm P1, P2; U2 và U3 cùng quan tâm P2, P4; U4 chưa có sản phẩm chung với ba người còn lại. Mô hình và dữ liệu này cho phép tính tay kết quả để đối chiếu với thuật toán.

Chỉ thực hiện các lệnh tạo dữ liệu trong **database học tập được phép thay đổi**. Label, type và tên index/constraint có tiền tố demo để dễ phân biệt với dữ liệu ứng dụng.

### 2.1. Bảo vệ khóa định danh

~~~cypher
CREATE CONSTRAINT gds_demo_user_id_unique IF NOT EXISTS
FOR (u:GdsDemoUser)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT gds_demo_item_id_unique IF NOT EXISTS
FOR (i:GdsDemoItem)
REQUIRE i.itemId IS UNIQUE;
~~~

Hai uniqueness constraint ngăn nhiều node cùng label mang khóa trùng khi thuộc tính có giá trị. Trong hệ thống thật, cần đánh giá thêm yêu cầu bắt buộc có khóa và các key/existence constraint theo phiên bản, edition Neo4j.

### 2.2. Nạp dữ liệu

~~~cypher
UNWIND [
  {userId: 'U1', items: ['P1', 'P2', 'P3']},
  {userId: 'U2', items: ['P1', 'P2', 'P4']},
  {userId: 'U3', items: ['P2', 'P4']},
  {userId: 'U4', items: ['P5']}
] AS row
MERGE (u:GdsDemoUser {userId: row.userId})
WITH u, row
UNWIND row.items AS itemId
MERGE (i:GdsDemoItem {itemId: itemId})
MERGE (u)-[:DEMO_INTERACTED]->(i);
~~~

Khi chạy lại trên fixture sạch, `MERGE` có thể tránh tạo thêm cạnh giống hệt cùng type và endpoint trong trường hợp đơn luồng. Trong hệ thống ghi đồng thời, cần thiết kế thêm ràng buộc định danh sự kiện/luồng ghi nếu dữ liệu yêu cầu không có nhiều lần tương tác trùng cặp. Neo4j không mặc nhiên giới hạn “mỗi cặp endpoint chỉ có một relationship” cho mọi trường hợp.

Kiểm tra dữ liệu:

~~~cypher
MATCH (u:GdsDemoUser)-[:DEMO_INTERACTED]->(i:GdsDemoItem)
RETURN u.userId AS userId,
       collect(DISTINCT i.itemId) AS items
ORDER BY userId;
~~~

Trong dữ liệu thực tế, `DEMO_INTERACTED` có thể biểu diễn “đã từng quan tâm” thay vì số lần click. Nếu mỗi click là một relationship sự kiện riêng, hãy xác định cách **loại trùng theo sản phẩm** trước khi áp dụng phép đo độ tương đồng dựa trên tập hàng xóm.

## 3. Độ tương đồng từ tập hàng xóm

Gọi \(N(u)\) là tập sản phẩm mà người dùng \(u\) tương tác. Các thuật toán cấu trúc đo quan hệ giữa \(N(u)\) và \(N(v)\), không nhất thiết cần văn bản hay embedding.

### 3.1. Common neighbors

Điểm đơn giản nhất là số phần tử chung:

\[
\operatorname{CN}(u,v)=|N(u)\cap N(v)|.
\]

Với dữ liệu ví dụ:

- `CN(U1,U2) = 2` vì cùng P1, P2.
- `CN(U2,U3) = 2` vì cùng P2, P4.
- `CN(U1,U3) = 1` vì cùng P2.
- `CN(U1,U4) = 0`.

Common neighbors có thể thiên về những người dùng hoạt động nhiều vì họ có nhiều cơ hội trùng sản phẩm. Hai cặp có cùng điểm 2 chưa chắc có tỷ lệ sở thích chung như nhau.

### 3.2. Jaccard similarity

Jaccard chuẩn hóa số hàng xóm chung theo kích thước hợp:

\[
\operatorname{Jaccard}(u,v)=
\frac{|N(u)\cap N(v)|}{|N(u)\cup N(v)|}.
\]

Với hai tập không rỗng, kết quả từ 0 đến 1; 1 nghĩa là hai tập bằng nhau. Khi cả hai tập đều rỗng, mẫu số bằng 0 và phải xác định quy ước xử lý thay vì tự chia.

| Cặp | Giao | Hợp | Jaccard |
| --- | ---: | ---: | ---: |
| U1, U2 | 2 | 4 | 0,500 |
| U1, U3 | 1 | 4 | 0,250 |
| U2, U3 | 2 | 3 | 0,667 |
| U1, U4 | 0 | 4 | 0 |

**Điểm đáng chú ý:** U1–U2 và U2–U3 có cùng hai sản phẩm chung, nhưng U2–U3 có tỷ lệ trùng cao hơn vì tổng tập sở thích của hai người nhỏ hơn.

Có thể kiểm chứng phép tính bằng Cypher:

~~~cypher
MATCH (:GdsDemoUser {userId: 'U1'})
      -[:DEMO_INTERACTED]->(ia:GdsDemoItem)
WITH collect(DISTINCT ia.itemId) AS aItems
MATCH (:GdsDemoUser {userId: 'U2'})
      -[:DEMO_INTERACTED]->(ib:GdsDemoItem)
WITH aItems, collect(DISTINCT ib.itemId) AS bItems
WITH aItems, bItems,
     size([x IN aItems WHERE x IN bItems]) AS common
RETURN common,
       size(aItems) + size(bItems) - common AS unionSize,
       toFloat(common) /
         (size(aItems) + size(bItems) - common) AS jaccard;
~~~

Kết quả trên fixture là `common = 2`, `unionSize = 4` và `jaccard = 0.5`. Đây là ví dụ dễ hiểu cho một cặp node; tính cho hàng triệu cặp nên xem xét thuật toán GDS và chiến lược giới hạn ứng viên.

### 3.3. Cosine, overlap và các phương pháp giảm ảnh hưởng của hub

Nếu biểu diễn mỗi người dùng bằng vector nhị phân thể hiện sản phẩm đã tương tác, cosine similarity là:

\[
\operatorname{Cosine}(u,v)=
\frac{|N(u)\cap N(v)|}
{\sqrt{|N(u)|\,|N(v)|}}.
\]

Hệ số overlap đo \(|N(u)\cap N(v)|/\min(|N(u)|,|N(v)|)\) khi tập nhỏ hơn không rỗng. Overlap có thể bằng 1 khi toàn bộ sở thích của một người nằm trong tập sở thích lớn hơn của người khác, dù hai tập không bằng nhau.

Trong dự đoán liên kết, một **sản phẩm cực kỳ phổ biến** có thể làm mọi người “giống nhau” chỉ vì ai cũng tương tác. Những heuristic như *Adamic–Adar* hoặc *Resource Allocation* giảm đóng góp của hàng xóm có bậc lớn:

\[
\operatorname{AA}(u,v)=
\sum_{z\in N(u)\cap N(v)}\frac{1}{\log |N(z)|},
\qquad
\operatorname{RA}(u,v)=
\sum_{z\in N(u)\cap N(v)}\frac{1}{|N(z)|}.
\]

Các công thức cần điều kiện bậc phù hợp; không áp dụng mẫu số `log(1)=0` một cách máy móc. Trong đồ thị hai phía, \(N(z)\) là tập người dùng gắn với sản phẩm \(z\). Các phép đo này thể hiện giả định: *cùng quan tâm một sản phẩm hiếm có thể chứa nhiều tín hiệu hơn cùng quan tâm một sản phẩm mà gần như ai cũng có*.

Không có chỉ số nào luôn phù hợp. Tùy mục tiêu, độ phổ biến còn có thể là tín hiệu hữu ích thay vì nhiễu. Quyết định cần dựa trên bộ dữ liệu đánh giá và chính sách sản phẩm.

## 4. Tính Node Similarity với Neo4j Graph Data Science

**GDS là thành phần riêng cần được cài đặt/cấp phép phù hợp và tương thích với phiên bản Neo4j đang chạy.** Các procedure `gds.*` dưới đây sẽ không hoạt động nếu hệ thống chỉ cài Neo4j mà chưa có GDS. Cú pháp minh họa dành cho dòng GDS 2.x; kiểm tra tài liệu phiên bản cài đặt trước khi triển khai thật.

### 4.1. Graph projection trong bộ nhớ

GDS tính toán trên một **đồ thị được chiếu vào bộ nhớ** (*named graph projection*). Projection cho phép chọn label, loại relationship, hướng và property cần thiết. Nó **khác** với đồ thị bền vững đang lưu trên Neo4j.

~~~cypher
CALL gds.graph.project(
  'gds_demo_recommendations',
  ['GdsDemoUser', 'GdsDemoItem'],
  {DEMO_INTERACTED: {orientation: 'UNDIRECTED'}}
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Projection trên gồm các node demo và cạnh tương tác, coi mỗi cạnh là **hai chiều trong bộ nhớ** để có thể so sánh tập hàng xóm. Điều này không sửa hướng của relationship `DEMO_INTERACTED` được lưu trong database. Số relationship hiển thị có thể phản ánh cách GDS biểu diễn hướng `UNDIRECTED`; không nhất thiết bằng số relationship `DEMO_INTERACTED` bền vững.

Trước khi tạo cùng tên một lần nữa, kiểm tra catalog:

~~~cypher
CALL gds.graph.list('gds_demo_recommendations')
YIELD graphName, nodeCount, relationshipCount, memoryUsage
RETURN graphName, nodeCount, relationshipCount, memoryUsage;
~~~

Named graph chiếm bộ nhớ của GDS và có vòng đời riêng. Thay đổi node/relationship trong database sau khi projection được tạo **không tự động cập nhật mọi cấu trúc đã được chiếu**; cần làm mới projection theo cách phù hợp trước khi tính lại thuật toán.

### 4.2. Chạy Node Similarity

~~~cypher
CALL gds.nodeSimilarity.stream(
  'gds_demo_recommendations',
  {
    topK: 10,
    similarityCutoff: 0.01
  }
)
YIELD node1, node2, similarity
WITH gds.util.asNode(node1) AS a,
     gds.util.asNode(node2) AS b,
     similarity
WHERE a:GdsDemoUser AND b:GdsDemoUser
RETURN a.userId AS userA,
       b.userId AS userB,
       similarity
ORDER BY similarity DESC, userA ASC, userB ASC;
~~~

Trong projection này, điểm Node Similarity mặc định dựa trên **Jaccard của hàng xóm**. Với dữ liệu demo và không có cạnh trùng, các cặp U2–U3, U1–U2 và U1–U3 có các giá trị tương ứng khoảng `0.667`, `0.5` và `0.25`. Cặp liên quan U4 có điểm 0 nên không vượt qua `similarityCutoff: 0.01`.

Điểm cần đọc đúng:

- `node1`, `node2` là **ID node trong graph projection GDS**; `gds.util.asNode(...)` ánh xạ về node Neo4j khi projection còn tương ứng.
- `topK` giới hạn số cặp được giữ **theo quy tắc của thuật toán**, không đồng nghĩa lấy top-K chung của toàn bộ đồ thị; cùng cặp có thể được trình bày theo hai chiều tùy cấu hình/kết quả.
- Vì projection gồm cả `GdsDemoUser` và `GdsDemoItem`, thuật toán còn có thể xét sự tương đồng giữa các sản phẩm. Bộ lọc `WHERE a:GdsDemoUser AND b:GdsDemoUser` chỉ giữ kết quả người dùng **sau khi thuật toán chạy**; nó không giảm chi phí tính các cặp loại khác.
- Ở đồ thị lớn, hãy giới hạn phạm vi node/relationship và dùng bộ lọc nguồn/đích của thuật toán nếu phiên bản GDS cung cấp, thay vì chỉ lọc kết quả cuối. Đánh giá cả yêu cầu bộ nhớ.

### 4.3. Ước lượng tài nguyên trước khi chạy

~~~cypher
CALL gds.nodeSimilarity.stream.estimate(
  'gds_demo_recommendations',
  {
    topK: 10,
    similarityCutoff: 0.01
  }
)
YIELD nodeCount, relationshipCount, requiredMemory
RETURN nodeCount, relationshipCount, requiredMemory;
~~~

Mẫu `.estimate` giúp ước lượng nhu cầu tài nguyên theo thuật toán, nhưng **không phải lời bảo đảm thời gian chạy**. Với đồ thị có các item cực kỳ phổ biến, số cặp ứng viên có thể rất lớn. Không lấy kết quả trên bốn user rồi suy ra chi phí trên hàng triệu user bằng tỉ lệ tuyến tính.

## 5. Gợi ý liên kết từ hàng xóm chung

**Node similarity** chỉ cho biết người dùng giống nhau; một ứng dụng đề xuất sản phẩm cần thêm bước chuyển điểm tương đồng thành **sản phẩm chưa tương tác**.

### 5.1. Gợi ý ứng viên bằng Cypher

Với U1, ta có thể lấy các người dùng tương tác chung ít nhất một sản phẩm, tìm sản phẩm họ đã tương tác nhưng U1 chưa có:

~~~cypher
MATCH (u:GdsDemoUser {userId: 'U1'})
      -[:DEMO_INTERACTED]->(seed:GdsDemoItem)
MATCH (peer:GdsDemoUser)-[:DEMO_INTERACTED]->(seed)
WHERE peer <> u
MATCH (peer)-[:DEMO_INTERACTED]->(candidate:GdsDemoItem)
WHERE NOT EXISTS {
  MATCH (u)-[:DEMO_INTERACTED]->(candidate)
}
RETURN candidate.itemId AS suggestedItem,
       count(DISTINCT peer) AS supportingPeers,
       count(DISTINCT seed) AS sharedSeedItems
ORDER BY supportingPeers DESC,
         sharedSeedItems DESC,
         suggestedItem ASC
LIMIT 10;
~~~

Trên dữ liệu demo, **P4** được gợi ý cho U1 vì U2 và U3 đều tương tác với P4, trong khi U1 chưa có. Hai thước đo:

- `supportingPeers` đếm số người dùng khác có khả năng giới thiệu sản phẩm.
- `sharedSeedItems` đếm số sản phẩm ban đầu nối U1 với tập peer có gợi ý sản phẩm đó.

Chúng là **heuristic xếp hạng**, không phải xác suất mua hàng. Dùng `DISTINCT` giúp không vô tình đếm nhiều lần cùng peer qua nhiều sản phẩm seed.

### 5.2. Kết hợp điểm similarity với gợi ý

Một ý tưởng nâng cao là tính \(s(u,v)\) giữa user mục tiêu \(u\) và peer \(v\), rồi cộng điểm từ các peer đã tương tác với item ứng viên:

\[
\operatorname{score}(u,i)
=\sum_{v\in P(i)}s(u,v),
\]

trong đó \(P(i)\) gồm những peer có sản phẩm \(i\) và đã qua bộ lọc ứng viên. Có thể nhân thêm trọng số thời gian hoặc chất lượng tín hiệu. Nếu dùng điểm Jaccard, một peer gần hơn có thể đóng góp nhiều hơn một peer chỉ có một sản phẩm chung.

**Phải định nghĩa ý nghĩa của mỗi cạnh:** `VIEWED`, `LIKED` và `BOUGHT` khác nhau về giá trị tín hiệu; gộp chúng thành một `INTERACTED` không trọng số có thể làm mất thông tin. Nếu người dùng chỉ xem sản phẩm, gợi ý mua dựa trên xem hàng không đồng nghĩa dự đoán mua chính xác.

### 5.3. Dự đoán liên kết trong đồ thị đồng nhất

Với `(:Person)-[:FOLLOWS]->(:Person)`, bài toán có thể là gợi ý người để theo dõi. Các phép đo như common neighbors, Adamic–Adar hoặc resource allocation dùng cấu trúc hai-hop làm feature. Tuy nhiên, **hướng cạnh là yếu tố nghiệp vụ**:

~~~text
(A)-[:FOLLOWS]->(B)
(C)-[:FOLLOWS]->(B)
~~~

A và C cùng theo dõi B nhưng điều đó không chứng minh A muốn theo dõi C. Định nghĩa tập hàng xóm đầu vào/đầu ra, loại cạnh ứng viên, tính hợp lệ của quan hệ và người dùng đã chặn nhau là những phần của bài toán link prediction. Tính điểm cao không tự cho phép ghi cạnh vào Neo4j.

## 6. Dự đoán liên kết bằng mô hình học máy

Heuristic thường dễ giải thích, nhưng khi có nhiều nguồn tín hiệu, mô hình link prediction có thể học từ dữ liệu quá khứ:

~~~text
Đồ thị + nhãn liên kết lịch sử
             |
   Chia train / validation / test
             |
   Tạo feature trên đồ thị train
   (neighbors, PageRank, embeddings,
    thuộc tính, tín hiệu thời gian...)
             |
   Huấn luyện mô hình
             |
   Chấm điểm cặp node ứng viên
             |
   Đánh giá và chọn ngưỡng / top-K
             |
   Triển khai + giám sát + tái huấn luyện
~~~

Trong GDS có các workflow/pipeline học máy cho dự đoán liên kết tùy phiên bản và edition. Cú pháp cấu hình pipeline, lựa chọn mô hình và tính năng huấn luyện có thể thay đổi; nên kiểm tra khả năng hiện có trên hệ thống trước khi đưa một lệnh pipeline cụ thể vào migration hoặc job.

### 6.1. Positive, negative và candidate

- **Positive**: liên kết thật từng phát sinh trong giai đoạn quan sát, theo định nghĩa nghiệp vụ rõ ràng.
- **Negative**: cặp chưa có liên kết được chọn làm mẫu âm; **chưa có cạnh không luôn đồng nghĩa là không bao giờ có cạnh**.
- **Candidate**: cặp hợp lệ cần chấm điểm ở thời điểm dự đoán, sau khi lọc các cạnh đã tồn tại và điều kiện quyền/trạng thái.

Trong một đồ thị rất thưa, số cặp không liên kết có thể áp đảo số cặp liên kết. Nếu chọn negative quá dễ, mô hình có thể cho điểm kiểm thử rất đẹp nhưng không giúp phân biệt những ứng viên khó nhất trong sản phẩm thật.

### 6.2. Tránh rò rỉ dữ liệu (*data leakage*)

Giả sử dự đoán người dùng sẽ tương tác sản phẩm vào tháng 10. Nếu tạo graph projection hoặc embedding trên **toàn bộ dữ liệu đến tháng 11**, mô hình có thể đã “nhìn thấy” chính các cạnh cần dự đoán. Kết quả offline khi đó cao giả tạo.

Cách tổ chức phù hợp cho bài toán theo thời gian:

1. Chốt thời điểm dự đoán \(T\) và tập sự kiện quan sát được trước \(T\).
2. Tạo feature, graph projection và embedding **chỉ từ dữ liệu được phép biết tại \(T\)**.
3. Xác định liên kết phát sinh trong cửa sổ sau \(T\) làm nhãn kiểm thử.
4. Dùng validation để chọn tham số và test tách biệt để báo cáo cuối.
5. Không dùng cùng một cạnh mục tiêu trong đồ thị tạo feature và trong nhãn “cần dự đoán”.

Đối với quan hệ không có thời gian, phải xây dựng chiến lược tách cạnh và chọn mẫu phù hợp, đồng thời giữ cho đồ thị huấn luyện đủ cấu trúc cần thiết. Việc tách ngẫu nhiên cũng có thể làm lộ thông tin khi các cạnh liên quan cùng một thực thể xuất hiện ở cả hai tập.

## 7. Node embedding: chuyển cấu trúc đồ thị thành vector

Embedding ánh xạ mỗi node \(v\) thành một vector:

\[
f(v)\in\mathbb{R}^{d},
\]

với \(d\) là số chiều do cấu hình thuật toán quy định (ví dụ 64 hoặc 128). Một thuật toán tốt cố gắng giữ lại những tín hiệu hữu ích về cấu trúc hoặc ngữ cảnh trong không gian vector để các node có tính chất liên quan được đặt gần nhau.

| Phương pháp | Tín hiệu chính | Khi nào cân nhắc |
| --- | --- | --- |
| **FastRP** | Phép chiếu ngẫu nhiên có xét cấu trúc hàng xóm theo các bậc lan truyền; có thể dùng feature. | Cần embedding cấu trúc nhanh trên đồ thị lớn, làm đầu vào kNN/ML. |
| **Node2Vec** | Random walks lấy mẫu ngữ cảnh node, học biểu diễn từ các chuỗi node. | Muốn điều chỉnh khám phá cấu trúc cục bộ/toàn cục; chấp nhận chi phí walk và huấn luyện. |
| **GraphSAGE** | Học hàm tổng hợp tín hiệu hàng xóm/thuộc tính, có thể áp dụng cho node mới trong điều kiện phù hợp. | Có đặc trưng node, nhu cầu học biểu diễn có khả năng suy diễn sang node chưa thấy. |
| **Text embedding** từ mô tả node | Ý nghĩa văn bản của title/description. | Tìm tương đồng nội dung; không tự mã hóa cấu trúc quan hệ nếu không kết hợp thông tin đồ thị. |

Embedding FastRP/Node2Vec chủ yếu dựa trên **cấu trúc đồ thị**. Vector từ mô hình ngôn ngữ chủ yếu dựa vào **nội dung văn bản**. Chúng không hoán đổi cho nhau, và cũng không tự dùng chung một không gian số có thể so sánh trực tiếp.

### 7.1. Ví dụ FastRP stream

Sau khi tạo projection `gds_demo_recommendations`, chạy:

~~~cypher
CALL gds.fastRP.stream(
  'gds_demo_recommendations',
  {
    embeddingDimension: 64,
    randomSeed: 42
  }
)
YIELD nodeId, embedding
WITH gds.util.asNode(nodeId) AS n, embedding
WHERE n:GdsDemoUser
RETURN n.userId AS userId,
       size(embedding) AS dimensions,
       embedding[0..5] AS firstFiveValues
ORDER BY userId;
~~~

Mỗi `GdsDemoUser` có vector 64 chiều; ví dụ chỉ hiển thị năm giá trị đầu cho dễ xem. **Các phần tử vector không phải các thuộc tính có nhãn như “độ yêu thích sản phẩm P1”**; chúng là tọa độ học/tính từ cấu trúc. Không diễn giải từng chiều riêng như một quy tắc nghiệp vụ.

`randomSeed` hỗ trợ khả năng lặp lại trong điều kiện nhất định, nhưng khác phiên bản, cấu hình thực thi, thứ tự dữ liệu hoặc thuật toán có thể cho vector không trùng từng bit. Nếu so sánh chất lượng giữa hai lần chạy, phải ghi lại cấu hình, phiên bản GDS, dữ liệu projection và cách chuẩn hóa.

### 7.2. Đặt tên chiều và đo độ gần

Hai cách so sánh vector phổ biến:

\[
\operatorname{cosine}(a,b)
=\frac{a\cdot b}{\lVert a\rVert\lVert b\rVert},
\qquad
\operatorname{distance}_{2}(a,b)
=\sqrt{\sum_{j=1}^{d}(a_j-b_j)^2}.
\]

Cosine chú ý **góc** giữa các vector, khoảng cách Euclid chú ý độ chênh lệch tọa độ. Lựa chọn phù hợp phụ thuộc cách tạo embedding, chuẩn hóa và mục tiêu. Hai vector có cosine cao chưa chắc biểu diễn cùng một người dùng về mặt nghiệp vụ; dữ liệu đầu vào và phương pháp học quyết định ý nghĩa của “gần”.

Không so sánh trực tiếp vector FastRP 64 chiều với vector text embedding 64 chiều chỉ vì có cùng số phần tử. Chúng được tạo từ hai quá trình và không gian biểu diễn khác nhau.

## 8. Kết hợp FastRP và kNN để tìm node gần nhau

`gds.fastRP.stream` chỉ trả vector trong kết quả truy vấn. Nếu muốn dùng lại kết quả trong GDS để tính kNN, có thể dùng chế độ **mutate** ghi property vector vào **in-memory graph**, không ghi xuống các node bền vững.

### 8.1. Tính embedding vào graph projection

~~~cypher
CALL gds.fastRP.mutate(
  'gds_demo_recommendations',
  {
    embeddingDimension: 64,
    randomSeed: 42,
    mutateProperty: 'fastRpEmbedding'
  }
)
YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
~~~

Property `fastRpEmbedding` ở bước này tồn tại trong graph catalog của GDS. Nó chưa nhất thiết xuất hiện dưới dạng `n.fastRpEmbedding` khi truy vấn node Neo4j bằng Cypher.

### 8.2. Tìm láng giềng gần trên vector

~~~cypher
CALL gds.knn.stream(
  'gds_demo_recommendations',
  {
    nodeProperties: ['fastRpEmbedding'],
    topK: 8
  }
)
YIELD node1, node2, similarity
WITH gds.util.asNode(node1) AS a,
     gds.util.asNode(node2) AS b,
     similarity
WHERE a:GdsDemoUser AND b:GdsDemoUser
RETURN a.userId AS userA,
       b.userId AS userB,
       similarity
ORDER BY similarity DESC, userA ASC, userB ASC;
~~~

kNN tìm hàng xóm gần nhau trong **không gian vector**. Kết quả không bắt buộc trùng xếp hạng Jaccard vì FastRP đã mã hóa cấu trúc thành vector và kNN áp dụng phép đo trong không gian đó. GDS kNN có các cơ chế lấy mẫu/tìm kiếm gần đúng tùy cấu hình và quy mô; không nên mặc định đây là phép so sánh chính xác mọi cặp.

Projection ví dụ có **cả người dùng và sản phẩm**. `topK: 8` đủ rộng cho đồ thị demo có chín node, nhưng khi dùng cho hệ thống lớn, lọc `WHERE a:GdsDemoUser AND b:GdsDemoUser` **sau** kNN có thể khiến kết quả chỉ còn rất ít người dùng vì các hàng xóm gần nhất là sản phẩm. Nếu sản phẩm yêu cầu top-K **chỉ giữa người dùng**, hãy tạo projection vector dành riêng cho node người dùng hoặc cấu hình bộ lọc nguồn/đích phù hợp với phiên bản GDS, rồi mới áp dụng top-K.

### 8.3. Đọc, mutate, write khác nhau thế nào?

| Chế độ GDS | Kết quả | Thay đổi Neo4j bền vững? |
| --- | --- | --- |
| `stream` | Trả hàng/điểm/vector cho Cypher hoặc driver. | Không. |
| `stats` (nếu thuật toán hỗ trợ) | Thống kê tổng hợp về phép chạy. | Không. |
| `mutate` | Thêm node/relationship property vào graph GDS trong bộ nhớ. | Không trực tiếp. |
| `write` | Ghi property hoặc relationship được thuật toán hỗ trợ vào Neo4j. | Có. |

Khi cần lưu kết quả đề xuất hoặc embedding để phục vụ nhiều request, cần quyết định rõ nơi lưu, tần suất làm mới và phiên bản kết quả. **Không coi projection GDS như một database bền vững**.

## 9. Lưu embedding và truy vấn bằng vector index

GDS kNN thích hợp khi muốn tính hàng xóm trên một graph projection. Nếu ứng dụng có embedding đã được ghi dưới dạng thuộc tính node, **vector index của Neo4j** có thể hỗ trợ truy vấn gần đúng top-K theo vector, thường dùng trong đường đọc trực tuyến.

### 9.1. Ghi vector demo trở lại Neo4j

Trên database học tập, sau khi đã chạy `fastRP.mutate`:

~~~cypher
CALL gds.graph.nodeProperties.write(
  'gds_demo_recommendations',
  ['fastRpEmbedding']
)
YIELD propertiesWritten
RETURN propertiesWritten;
~~~

Lệnh ghi property này tác động tới các node demo được chứa trong projection; nó không tự tạo quan hệ dự đoán. Khi dùng trong production, cân nhắc chỉ ghi lên tập node mong muốn, kiểm tra bộ nhớ và độ lớn thuộc tính vector, đồng thời gắn metadata như `embeddingVersion`/`calculatedAt` cho quy trình vận hành.

### 9.2. Tạo vector index cho người dùng

Ví dụ cú pháp Neo4j 5 có hỗ trợ vector index:

~~~cypher
CREATE VECTOR INDEX gds_demo_user_embedding_idx IF NOT EXISTS
FOR (u:GdsDemoUser)
ON (u.fastRpEmbedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 64,
    `vector.similarity_function`: 'cosine'
  }
};
~~~

Khóa cấu hình `vector.dimensions` phải phù hợp với vector thật. Khi index chưa đạt trạng thái `ONLINE`, không nên coi kết quả tra cứu là sẵn sàng:

~~~cypher
SHOW INDEXES
YIELD name, type, state, properties
WHERE name = 'gds_demo_user_embedding_idx'
RETURN name, type, state, properties;
~~~

### 9.3. Tìm user gần nhất với vector của U1

~~~cypher
MATCH (u:GdsDemoUser {userId: 'U1'})
WITH u, u.fastRpEmbedding AS queryVector
CALL db.index.vector.queryNodes(
  'gds_demo_user_embedding_idx',
  4,
  queryVector
)
YIELD node, score
WHERE node <> u
RETURN node.userId AS suggestedUserId, score
ORDER BY score DESC, suggestedUserId ASC
LIMIT 3;
~~~

Query trả các node gần trong index theo cách tính điểm của vector index. Nó **không chứng minh** khả năng sẽ kết bạn hoặc mua sản phẩm; cần qua bước lọc nghiệp vụ, đánh giá và xếp hạng. Chức năng vector index, cú pháp procedure và phương thức tìm kiếm mới có thể thay đổi theo phiên bản Neo4j; hãy xác minh trên môi trường vận hành. Không trộn `score` của vector index với Jaccard/GDS kNN như thể cùng một thang đo.

**Phân biệt quan trọng:** tạo vector index **không tự tạo embedding**. Phải có bước tính vector, ghi vector và kiểm tra độ mới. Khi mô hình embedding hoặc chiều vector thay đổi, cần lập kế hoạch xây index và chuyển luồng đọc tương thích.

## 10. Đánh giá chất lượng gợi ý

Một thuật toán trả về điểm số không đồng nghĩa đã hữu ích. Đánh giá cần bắt đầu từ **mục tiêu sản phẩm** và cách người dùng tương tác.

### 10.1. Chỉ số top-K

Giả sử với người dùng U, hệ thống đề xuất 5 sản phẩm và trong kỳ đo thực tế có 2 sản phẩm thuộc danh sách đó được người dùng tương tác. Một số chỉ số:

| Chỉ số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Precision@K | Trong K gợi ý, bao nhiêu gợi ý là kết quả liên quan theo nhãn đánh giá? | Không cho biết tất cả kết quả liên quan đã được tìm thấy. |
| Recall@K | Trong các kết quả liên quan, bao nhiêu xuất hiện ở top-K? | Cần biết/tạo được tập kết quả liên quan đủ tin cậy. |
| Hit Rate@K | Tỷ lệ trường hợp có ít nhất một gợi ý đúng trong top-K. | Có thể cao dù thứ tự và phần còn lại của danh sách kém. |
| MRR / NDCG@K | Đánh giá vị trí của kết quả đúng, NDCG còn hỗ trợ mức liên quan khác nhau. | Phù hợp khi thứ tự hiển thị quan trọng. |
| ROC-AUC, PR-AUC | Đánh giá khả năng phân biệt cặp positive và negative. | Phụ thuộc cách lấy mẫu; PR-AUC hữu ích khi lớp dương hiếm. |
| Coverage / Diversity / Novelty | Phạm vi item và độ đa dạng gợi ý. | Cần thiết để phát hiện chỉ đề xuất item quá phổ biến. |

Ví dụ minh họa: 5 gợi ý có 2 kết quả đúng thì `Precision@5 = 2/5 = 0.4`. Nếu tổng số item liên quan trong tập kiểm chứng là 4 thì `Recall@5 = 2/4 = 0.5`. Không áp dụng phép tính này trực tiếp cho dữ liệu người dùng chưa từng được tiếp xúc với các item: thiếu tương tác không chắc là không quan tâm.

### 10.2. Offline và online

- **Offline:** dùng dữ liệu lịch sử với chia tách thời gian; giúp so sánh thuật toán có thể lặp lại trước triển khai.
- **Online:** theo dõi CTR, chuyển đổi, mức hài lòng, tỷ lệ khiếu nại, ảnh hưởng đến tốc độ tải và các rủi ro nghiệp vụ.

Chỉ số offline tốt có thể không dẫn đến kết quả online tốt do thiên lệch hiển thị, hiệu ứng “vòng lặp gợi ý”, thay đổi hành vi người dùng hoặc tính mới của item. Cần kiểm soát điều kiện thí nghiệm khi đánh giá tác động thật.

### 10.3. Bộ dữ liệu đánh giá có tính đại diện

Tối thiểu kiểm thử:

1. Người dùng hoạt động ít, trung bình và rất nhiều.
2. Item ít tương tác và item cực kỳ phổ biến (*hub*).
3. Người dùng mới hoặc item mới (*cold start*).
4. Nhiều tenant hoặc phân khúc với quy tắc dữ liệu khác nhau.
5. Tình huống cập nhật/xóa node, thay đổi quyền và cạnh xuất hiện sau thời điểm tính embedding.
6. Các cặp có điểm giống nhau để kiểm tra cách phá hòa và ổn định phân trang.

Với người dùng/item mới chưa có cạnh, node similarity dựa trên hàng xóm thường cho rất ít tín hiệu. Có thể bổ sung thuộc tính nội dung, thông tin ngữ cảnh được phép sử dụng hoặc gợi ý phổ biến có kiểm soát, nhưng phải phân biệt rõ đây là chiến lược cold start.

## 11. Hiệu năng và an toàn dữ liệu khi chạy thuật toán

### 11.1. Bùng nổ cặp ứng viên

Với \(n\) node, số cặp node phân biệt có thể lên đến \(n(n-1)/2\). Một thuật toán không nhất thiết duyệt mọi cặp theo cách ngây thơ, nhưng việc so sánh tương đồng trong đồ thị lớn vẫn có thể tốn bộ nhớ và CPU, đặc biệt khi có **supernode** nối với hàng triệu node.

Cách giảm chi phí:

- Chọn projection chỉ chứa label, relationship type và khoảng thời gian thật sự cần.
- Giới hạn tenant/nhóm nghiệp vụ khi thuật toán và mô hình cho phép.
- Đặt ngưỡng bậc tối thiểu/tối đa và phạm vi top-K theo phương pháp được hỗ trợ.
- Ước lượng bộ nhớ GDS trước khi chạy; chạy batch theo lịch phù hợp với tải đọc/ghi.
- Dùng truy xuất vector gần đúng khi bài toán cho phép đánh đổi tốc độ và độ chính xác.
- Đo p50/p95/p99, thời gian projection, thời gian thuật toán và chi phí tái tính, không chỉ đo thời gian trả một query demo.

Hãy kiểm tra cẩn thận nếu loại supernode: đôi khi node phổ biến lại chứa thông tin quan trọng. Quyết định này làm thay đổi kết quả chứ không chỉ giảm tải.

### 11.2. Phiên bản và độ mới của embedding

Một vector đã tính từ đồ thị hôm qua có thể trở nên kém hữu ích khi nhiều cạnh mới xuất hiện. Khi ghi embedding hoặc kết quả gợi ý để phục vụ online, lưu thông tin vận hành như:

| Metadata | Mục đích |
| --- | --- |
| `algorithmVersion`, tham số thuật toán | Biết cách tái tạo vector/điểm. |
| `graphSnapshotAt` hoặc watermark nguồn | Biết dữ liệu đầu vào đến thời điểm nào. |
| `embeddingDimension`, similarity function | Đảm bảo dữ liệu tương thích với index và query. |
| `calculatedAt` | Theo dõi tuổi kết quả và chính sách hết hạn. |
| `tenantId` / phạm vi quyền | Tránh dùng gợi ý từ dữ liệu không được phép. |

Nếu embedding cũ và mới được tạo từ **hai mô hình hoặc không gian số khác nhau**, không nên trộn chúng để tìm nearest neighbors mà không kiểm chứng độ tương thích. Một cách triển khai thường dùng là tính phiên bản mới, đánh giá, chuyển đường đọc rồi mới xóa dữ liệu/index cũ.

### 11.3. Quyền truy cập và tính công bằng

Mối liên kết giữa hai người dùng có thể nhạy cảm ngay cả khi không hiển thị thuộc tính cá nhân. Graph projection và embedding cần tuân thủ chính sách quyền/tenant: không để một người suy ra mạng lưới quan hệ riêng tư thông qua danh sách gợi ý hoặc điểm tương đồng.

Đồng thời, dữ liệu hành vi quá khứ có thể ưu tiên nhóm người dùng/item đã phổ biến và làm giảm cơ hội của nhóm mới. Đánh giá coverage, độ đa dạng, thiên lệch theo nhóm hợp lệ và khả năng giải thích của các gợi ý quan trọng. Không dùng score của thuật toán như một quyết định tự động có độ tin cậy tuyệt đối.

## 12. Tích hợp kết quả từ Java Driver và Spring Data Neo4j

Trong ứng dụng, job GDS thường chạy theo lịch để tính similarity hoặc embedding, còn API đọc dữ liệu đã materialize và áp dụng quy tắc nghiệp vụ. Với một phép truy vấn thuật toán nhỏ, Java Driver cũng có thể gọi trực tiếp procedure:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

import java.util.List;

public final class GraphSimilarityJob {
    private final Driver driver;

    public GraphSimilarityJob(Driver driver) {
        this.driver = driver;
    }

    public List<Record> userPairs() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                CALL gds.nodeSimilarity.stream(
                  'gds_demo_recommendations',
                  {topK: 10, similarityCutoff: 0.01}
                )
                YIELD node1, node2, similarity
                WITH gds.util.asNode(node1) AS a,
                     gds.util.asNode(node2) AS b,
                     similarity
                WHERE a:GdsDemoUser AND b:GdsDemoUser
                RETURN a.userId AS userA,
                       b.userId AS userB,
                       similarity
                ORDER BY similarity DESC, userA ASC, userB ASC
                """).list();
        }
    }
}
~~~

Ví dụ giả định đã có `Driver` và named graph projection như mục 4; tên database `neo4j` chỉ là minh họa. Trong production, nên trả DTO thay cho `Record`, kiểm soát thời gian chạy, memory estimate và phân trang/tập kết quả. Không nên chạy thuật toán toàn đồ thị trong mỗi request HTTP nếu chi phí lớn.

Với **Spring Data Neo4j**, entity/repository giúp làm việc với node, relationship và thuộc tính, còn GDS được gọi qua Cypher/driver/client phù hợp. Annotation ánh xạ entity **không tự tạo embedding hoặc tính similarity**. Phân tách job tính toán, nơi lưu kết quả và API đọc giúp kiểm soát độ mới cũng như tải tài nguyên.

## 13. Kiểm tra và dọn dữ liệu thử nghiệm

Nếu triển khai theo trình tự mục 2–9, hãy xác minh:

~~~cypher
MATCH (u:GdsDemoUser)
RETURN count(u) AS userCount;
~~~

~~~cypher
MATCH (u:GdsDemoUser)-[r:DEMO_INTERACTED]->(i:GdsDemoItem)
RETURN count(r) AS interactionCount,
       count(DISTINCT u) AS usersWithInteractions,
       count(DISTINCT i) AS itemsWithInteractions;
~~~

Khi dùng đúng fixture, có 4 user, 5 item và 9 quan hệ tương tác. Nếu có nhiều bản ghi hơn, kiểm tra xem database có dữ liệu demo cũ hay không trước khi so kết quả thuật toán.

Sau khi hoàn thành, có thể giải phóng **projection trong bộ nhớ**:

~~~cypher
CALL gds.graph.drop('gds_demo_recommendations');
~~~

Nếu đã tạo vector index ở mục 9 và không dùng nữa:

~~~cypher
DROP INDEX gds_demo_user_embedding_idx IF EXISTS;
~~~

Để dọn các node demo khỏi **database học tập riêng**, chỉ xóa đúng label bài thực hành:

~~~cypher
MATCH (u:GdsDemoUser)
DETACH DELETE u;
~~~

~~~cypher
MATCH (i:GdsDemoItem)
DETACH DELETE i;
~~~

Cuối cùng có thể xóa hai constraint demo nếu chúng không còn được dùng:

~~~cypher
DROP CONSTRAINT gds_demo_user_id_unique IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT gds_demo_item_id_unique IF EXISTS;
~~~

Lệnh `DETACH DELETE` xóa cả relationship của node mục tiêu; chỉ dùng khi đã xác nhận tất cả node đó là fixture thuộc phạm vi bài tập. Không xóa label/relationship khác hoặc chạy dọn hàng loạt trên database production.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra / xử lý |
| --- | --- | --- |
| `There is no procedure with the name gds...` | Chưa cài GDS, sai phiên bản hoặc thiếu quyền. | Kiểm tra plugin/edition, phiên bản và quyền thực thi. |
| Graph projection đã tồn tại | Chạy lại `gds.graph.project` với cùng tên trong catalog. | Xem `gds.graph.list`, dùng đúng projection hoặc drop/recreate có kiểm soát. |
| Kết quả similarity khác tính tay | Cạnh trùng, hướng projection, trọng số, bộ lọc, thuật toán hay top-K khác. | In tập hàng xóm thực tế rồi đối chiếu định nghĩa điểm. |
| U4 không có gợi ý | Không có hàng xóm chung trong mẫu. | Thiết kế cold-start fallback thay vì cố buộc điểm giống nhau. |
| kNN trả item khi cần user | Projection chứa cả user và item; lọc sau kNN. | Dùng projection/bộ lọc chỉ chứa user trước khi xếp top-K. |
| Embedding không thấy trong `MATCH (n) RETURN n.embedding` | Mới dùng `stream` hoặc `mutate`, chưa ghi xuống Neo4j. | Phân biệt ba chế độ và ghi property nếu cần. |
| Vector index không trả kết quả | Chưa `ONLINE`, vector thiếu/sai chiều/sai kiểu hoặc query không tương thích. | Kiểm tra `SHOW INDEXES` và property vector trên node. |
| Offline score cao bất thường | Nhãn/cạnh cần dự đoán đã rò rỉ vào graph tạo feature. | Chia train/test trước khi tính feature/embedding. |
| Gợi ý đã có liên kết | Chưa loại cặp đã có cạnh. | Dùng `NOT EXISTS { MATCH ... }` trên quan hệ nghiệp vụ cần loại. |
| Gợi ý giữa hai tenant | Projection hoặc bộ lọc không áp dụng ranh giới quyền. | Kiểm tra nguồn dữ liệu, quyền, tenant và pipeline phục vụ. |
| Tài nguyên GDS tăng mạnh | Projection quá rộng, supernode hoặc thuật toán sinh nhiều cặp. | Estimate bộ nhớ, đo degree, giới hạn phạm vi và chọn job thích hợp. |

## 15. Bài tập tự thực hành

**Bài 1 — Tính tay.** Với tập U1 = {P1, P2, P3}, U2 = {P1, P2, P4}, U3 = {P2, P4}, hãy tính common neighbors, Jaccard và cosine cho ba cặp. Giải thích vì sao thứ hạng theo Jaccard có thể khác common neighbors.

**Bài 2 — Node Similarity.** Tạo fixture ở mục 2, projection ở mục 4 và chạy `gds.nodeSimilarity.stream`. So sánh điểm của U1–U2 với giá trị tính tay; giải thích vì sao kết quả của U4 có thể vắng mặt khi `similarityCutoff > 0`.

**Bài 3 — Gợi ý sản phẩm.** Viết truy vấn trả các sản phẩm mà U1 chưa tương tác nhưng các peer có sản phẩm chung với U1 đã tương tác. Xếp hạng theo số peer giới thiệu. Trong fixture, sản phẩm nào nên đứng đầu?

**Bài 4 — Từ heuristic sang ML.** Mô tả cách chia train/validation/test theo thời gian cho nhiệm vụ dự đoán cạnh `:BOUGHT`. Chỉ rõ điều gì xảy ra nếu embedding được tính từ đồ thị đã chứa các cạnh mua hàng thuộc tập test.

**Bài 5 — Embedding và kNN.** Tính FastRP vector 64 chiều, mutate vào named graph và chạy kNN. Vì sao điểm kNN không nhất thiết trùng Jaccard? Nêu cách bảo đảm các ứng viên so sánh đều là user trước khi lấy top-K.

**Bài 6 — Cold start và vận hành.** Một sản phẩm mới chưa có cạnh `DEMO_INTERACTED` nhưng có mô tả văn bản đầy đủ. Đề xuất cách gợi ý sản phẩm đó, lịch làm mới vector và chỉ số đánh giá để biết chiến lược có cải thiện trải nghiệm hay không.

**Bài 7 — Quyền truy cập.** Một đồ thị có user từ nhiều tenant và một số mối quan hệ riêng tư. Hãy mô tả các kiểm soát cần áp dụng ở projection, tính điểm, lưu embedding và API để tránh lộ liên kết ngoài phạm vi được phép.

## 16. Checklist trước khi đưa thuật toán vào hệ thống thật

1. **Đúng bài toán:** đang đo độ tương đồng, dự đoán một cạnh hay chỉ cần tìm vector gần?
2. **Đúng đồ thị:** label, type, hướng quan hệ, trọng số, thời gian và tenant trong projection có phản ánh dữ liệu được phép sử dụng?
3. **Đúng tín hiệu:** đã xử lý cạnh trùng, supernode, cold start, popularity bias và sự khác biệt giữa xem, thích, mua chưa?
4. **Đúng cách đánh giá:** train/test được chia tránh leakage, metric top-K gắn với mục tiêu sản phẩm và có thử nghiệm online thích hợp?
5. **Đủ khả năng vận hành:** có estimate bộ nhớ, lịch tính lại, metadata phiên bản, chiến lược cập nhật node/edge và cách xóa graph projection?
6. **Đúng quyền dữ liệu:** điểm, vector và gợi ý có thể làm lộ mối quan hệ riêng tư hoặc vượt ranh giới tenant hay không?
7. **Có phương án đối chiếu:** có baseline Cypher/heuristic đơn giản để chứng minh GDS hoặc embedding thực sự mang lại giá trị?

**Điểm cốt lõi:** độ tương đồng giúp đo mối liên hệ từ cấu trúc, dự đoán liên kết dùng những tín hiệu đó để xếp hạng **các cạnh chưa tồn tại**, còn node embedding nén cấu trúc/ngữ cảnh vào vector để các phép toán gần nhau thực hiện thuận tiện hơn. Với Neo4j, cần phối hợp **Cypher, graph projection GDS, thuật toán, index và quy tắc nghiệp vụ**; chất lượng mô hình được quyết định bởi dữ liệu đầu vào, cách đánh giá và khả năng vận hành, không chỉ bởi một con số similarity.
