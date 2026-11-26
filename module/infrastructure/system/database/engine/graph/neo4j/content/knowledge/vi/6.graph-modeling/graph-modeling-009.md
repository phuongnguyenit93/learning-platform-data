# Xử lý nút có bậc quá cao và tránh mô hình làm truy vấn bùng nổ

## 1. Bối cảnh và mục tiêu

Trong **thiết kế mô hình (graph modeling)** với Neo4j, node và relationship giúp diễn tả những liên kết mà mô hình quan hệ thường phải nối nhiều bảng mới tìm được. Tuy nhiên, một mô hình sát nghiệp vụ vẫn có thể tạo ra truy vấn rất đắt nếu có node nối tới quá nhiều node khác hoặc nếu truy vấn mở rộng đồng thời qua nhiều nhánh.

Bài này tập trung vào hai vấn đề thường gặp:

- **Node có bậc rất cao (high-degree node, thường gọi là supernode):** ví dụ một chủ đề phổ biến được gắn với hàng triệu bài viết, hoặc một tài khoản có hàng triệu lượt tương tác.
- **Bùng nổ số đường đi hoặc số dòng trung gian (fan-out/cardinality explosion):** mỗi lần đi qua relationship, tập kết quả có thể nhân lên; một số mẫu `MATCH` còn tạo tích Descartes giữa các nhánh độc lập.

Sau bài học, bạn có thể xác định node và đường duyệt gây tải, viết Cypher có điểm bắt đầu chọn lọc, quyết định khi nào cần thay đổi mô hình, và sử dụng `EXPLAIN`/`PROFILE` để đánh giá bằng số liệu.

### 1.1. Mô hình ví dụ xuyên suốt

Giả sử xây dựng mạng xã hội nội bộ với các thực thể và quan hệ:

```text
(:User)-[:FOLLOWS]->(:User)
(:User)-[:AUTHORED]->(:Post)
(:User)-[:LIKED]->(:Post)
(:Post)-[:HAS_TOPIC]->(:Topic)
```

Các thuộc tính thường dùng gồm `User.id`, `Post.id`, `Post.publishedAt` (kiểu `datetime`) và `Topic.id`. Một `Topic` như `"database"` có thể được gắn với hàng triệu `Post`. Cách tổ chức quan hệ này rất tự nhiên, nhưng việc bắt đầu một truy vấn từ chủ đề phổ biến có thể phải xét một lượng lớn bài viết.

> **Nguyên tắc nền tảng:** số relationship lớn tự nó chưa chứng minh mô hình sai. Vấn đề xuất hiện khi truy vấn thường xuyên phải mở rộng qua quá nhiều relationship hoặc tạo quá nhiều kết quả trung gian so với đầu ra cần lấy.

## 2. Supernode và sự bùng nổ fan-out là gì?

### 2.1. Bậc của node không đồng nghĩa chi phí của mọi truy vấn

**Bậc (degree)** của một node là số relationship gắn với node đó. Cần phân biệt bậc tổng với số relationship phù hợp **loại** và **hướng** truy vấn.

Ví dụ một `Topic` có 2 triệu quan hệ `HAS_TOPIC` đi vào nhưng chỉ vài quan hệ quản trị khác. Truy vấn đi theo một loại quan hệ có ít cạnh có thể vẫn rẻ; truy vấn đi ngược qua toàn bộ `HAS_TOPIC` có thể phải duyệt lượng dữ liệu rất lớn.

Neo4j có cơ chế lưu trữ hỗ trợ node dày đặc quan hệ (dense nodes), nên không nên áp dụng một ngưỡng bậc cố định để kết luận cần tái thiết kế. Hãy đo chi phí theo **mẫu truy vấn, phân phối dữ liệu và mục tiêu độ trễ** thực tế.

### 2.2. Vì sao số dòng có thể nhân nhanh?

Giả sử một truy vấn khởi đầu với 1.000 node, trung bình mỗi node mở ra 200 quan hệ ở bước tiếp theo, rồi mỗi kết quả lại mở ra 20 quan hệ:

```text
1.000 điểm bắt đầu
     × 200 nhánh
     ×  20 nhánh
 = 4.000.000 kết hợp/đường đi tiềm năng
```

Đây là **ước lượng minh họa**, không phải công thức thời gian chạy hay con số chắc chắn. Bộ lập kế hoạch có thể đổi thứ tự các phép duyệt, áp dụng bộ lọc sớm hoặc loại trùng; tuy nhiên phép nhân fan-out cho thấy vì sao kết quả cuối chỉ vài chục dòng vẫn có thể cần xử lý rất nhiều dữ liệu.

Cần phân biệt ba hiện tượng:

| Hiện tượng | Dấu hiệu điển hình | Hệ quả |
| --- | --- | --- |
| Supernode | Một node có số quan hệ rất lớn theo loại/hướng đang duyệt | Mở rộng một bước cũng có thể tốn kém |
| Fan-out qua nhiều bước | Số dòng tăng mạnh sau mỗi phép duyệt | Nhiều lần truy cập dữ liệu, áp lực CPU và bộ nhớ |
| Tích Descartes | Hai nhánh `MATCH` độc lập rồi ghép mọi cặp | Số dòng xấp xỉ tích kích thước hai tập |

Một truy vấn còn có thể bị chậm do `DISTINCT`, `ORDER BY`, `collect()` hoặc gom nhóm trên tập trung gian lớn, dù số dòng trả về nhỏ.

## 3. Nhận diện vấn đề từ Cypher và kế hoạch thực thi

### 3.1. Truy vấn bắt đầu từ một chủ đề cực phổ biến

Mục tiêu: lấy các bài viết gần đây thuộc một chủ đề.

```cypher
MATCH (t:Topic {id: $topicId})<-[:HAS_TOPIC]-(p:Post)
WHERE p.publishedAt >= datetime($from)
  AND p.publishedAt < datetime($to)
RETURN p.id AS postId, p.publishedAt AS publishedAt
ORDER BY publishedAt DESC, postId DESC
LIMIT $pageSize;
```

Mẫu này **đúng về mặt ý nghĩa** nếu `Topic.id` là duy nhất. Nhưng nếu `$topicId` trỏ tới một chủ đề có hàng triệu bài và khoảng thời gian chỉ một ngày, hướng mở rộng từ chủ đề có nguy cơ xét quá nhiều bài trước khi lọc. Neo4j có thể chọn kế hoạch tốt hơn; cần xem `EXPLAIN`/`PROFILE` thay vì suy luận chỉ từ thứ tự viết `MATCH`.

### 3.2. Dùng EXPLAIN trước, PROFILE trên dữ liệu thích hợp

```cypher
EXPLAIN
MATCH (t:Topic {id: $topicId})<-[:HAS_TOPIC]-(p:Post)
WHERE p.publishedAt >= datetime($from)
  AND p.publishedAt < datetime($to)
RETURN p.id
ORDER BY p.publishedAt DESC
LIMIT $pageSize;
```

`EXPLAIN` trả kế hoạch dự kiến mà không thực thi truy vấn. Sau đó chạy cùng truy vấn với `PROFILE` trên môi trường thử nghiệm hoặc dữ liệu thích hợp để quan sát thực tế.

Tùy phiên bản Neo4j và công cụ truy cập, hãy xem:

- **Rows** ở từng operator: dòng bắt đầu tăng vọt tại bước nào?
- **DB Hits**: nơi nào đang truy cập quá nhiều record/relationship?
- Operator như `NodeByLabelScan`, `NodeIndexSeek`, `Expand(All)`, `Expand(Into)`, các phép mở rộng đường đi, `CartesianProduct`, `Sort` và `EagerAggregation`.
- Thời gian, bộ nhớ, page cache (nếu kế hoạch/công cụ cung cấp): có phần nào đọc hoặc giữ nhiều dữ liệu trung gian?

Nếu `Expand(All)` tạo hàng triệu dòng rồi `Filter` chỉ giữ vài trăm dòng, nên xem xét cách rút nhỏ ứng viên **trước** khi mở rộng. Nếu thấy `CartesianProduct`, kiểm tra những nhánh đang ghép có thật sự cần mọi cặp hay không.

Không so sánh thời gian của các truy vấn trên dữ liệu khác nhau hoặc với tham số có độ chọn lọc rất khác nhau. Chạy nhiều lần trong điều kiện tương đương, quan sát cả dữ liệu phổ biến lẫn dữ liệu thưa.

### 3.3. Kiểm tra ràng buộc và index

Dùng các lệnh quản trị phù hợp quyền truy cập để xem cấu trúc hiện có:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Có thể tạo ràng buộc định danh và index thời gian cho mô hình ví dụ:

```cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT post_id_unique IF NOT EXISTS
FOR (p:Post) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.id IS UNIQUE;

CREATE INDEX post_published_at IF NOT EXISTS
FOR (p:Post) ON (p.publishedAt);
```

Các câu lệnh trên dùng cú pháp Cypher phù hợp với Neo4j 5. Index giúp tìm **điểm bắt đầu chọn lọc** khi bộ lập kế hoạch đánh giá có lợi; index không tự giảm số đường đi nếu truy vấn vẫn cần duyệt tất cả các quan hệ của một supernode.

## 4. Cách tối ưu truy vấn trước khi sửa mô hình

### 4.1. Bắt đầu từ tập ứng viên nhỏ nhất có thể

Nếu truy vấn chủ yếu tìm bài viết trong một khoảng thời gian rất hẹp, có thể viết lại thành tìm bài viết theo thời gian rồi kiểm tra xem bài đó có thuộc chủ đề hay không:

```cypher
MATCH (p:Post)
WHERE p.publishedAt >= datetime($from)
  AND p.publishedAt < datetime($to)
  AND EXISTS {
    MATCH (p)-[:HAS_TOPIC]->(:Topic {id: $topicId})
  }
RETURN p.id AS postId, p.publishedAt AS publishedAt
ORDER BY publishedAt DESC, postId DESC
LIMIT $pageSize;
```

Điều kiện `EXISTS` chỉ cần xác nhận có đường nối phù hợp, không cần nhân bản dòng kết quả theo các đường nối tìm được. Index trên `Post.publishedAt` có thể giúp nếu khoảng thời gian đủ hẹp. Nếu chủ đề hiếm nhưng khoảng thời gian rộng, cách bắt đầu từ `Topic` lại có thể tốt hơn. **Hai cách viết là phương án để đo đạc, không có phương án luôn thắng.**

Khi truy vấn có ngữ cảnh người xem, một điểm bắt đầu khác là người dùng:

```cypher
MATCH (viewer:User {id: $viewerId})-[:FOLLOWS]->(author:User)
MATCH (author)-[:AUTHORED]->(p:Post)
WHERE p.publishedAt >= datetime($from)
  AND p.publishedAt < datetime($to)
  AND EXISTS {
    MATCH (p)-[:HAS_TOPIC]->(:Topic {id: $topicId})
  }
RETURN DISTINCT p.id AS postId, p.publishedAt AS publishedAt
ORDER BY publishedAt DESC, postId DESC
LIMIT $pageSize;
```

Truy vấn này trả **bài của các tác giả được người xem theo dõi**; do đó nghiệp vụ đã khác với truy vấn trả mọi bài của chủ đề. Chỉ áp dụng khi đây thật sự là yêu cầu. Nếu người xem theo dõi rất nhiều tác giả, hoặc tác giả có lượng bài khổng lồ, hướng này vẫn có thể tốn kém.

### 4.2. Dùng loại quan hệ, chiều duyệt và nhãn một cách cụ thể

Cần diễn đạt rõ đường cần đi:

```cypher
MATCH (u:User {id: $userId})-[:LIKED]->(p:Post)
WHERE p.publishedAt >= datetime($from)
RETURN p.id
LIMIT $pageSize;
```

So với một mẫu quá rộng như `(u)--(x)` hoặc `(u)-[*]-(x)`, việc định rõ `LIKED`, chiều mũi tên và nhãn `Post` hạn chế các nhánh không liên quan, đồng thời giúp người đọc hiểu nghiệp vụ. Tuy vậy, nếu `u` đã thích hàng triệu bài thì truy vấn vẫn phải cân nhắc tập ứng viên và thời gian.

### 4.3. Giới hạn độ sâu đường đi và số đường đi cần trả

Tránh đường đi không giới hạn nếu bài toán chỉ cần kết nối trong một số bước nhỏ:

```cypher
MATCH path =
  (start:User {id: $startId})-[:FOLLOWS*1..2]->(target:User)
WHERE target.id = $targetId
RETURN path
LIMIT 5;
```

`*1..2` chỉ cho phép một hoặc hai bước, giúp giới hạn độ sâu so với `*1..` hoặc `*`. Nhưng nếu mỗi người theo dõi hàng trăm nghìn người, **hai bước vẫn có thể tạo số đường đi khổng lồ**. `LIMIT 5` hạn chế số dòng được trả; tùy kế hoạch, thao tác sắp xếp, lọc hoặc duyệt trước đó vẫn có thể cần xử lý nhiều dòng. Không dùng `LIMIT` để thay cho việc kiểm soát fan-out.

Khi nghiệp vụ cần một đường đi ngắn nhất giữa hai node đã biết, xem xét các khả năng tìm đường đi ngắn nhất của Cypher và đo kế hoạch riêng. Một phép tìm đường ngắn nhất không tương đương với việc liệt kê tất cả đường đi, và cũng không bảo đảm rẻ trên mọi đồ thị.

### 4.4. Tránh tích Descartes do các nhánh MATCH độc lập

Ví dụ sau đếm tương tác từ hai tập nhưng đã tạo các tổ hợp cặp trước khi gom:

```cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(f:User),
      (u)-[:LIKED]->(p:Post)
RETURN count(DISTINCT f) AS followingCount,
       count(DISTINCT p) AS likedPostCount;
```

Nếu `u` theo dõi 10.000 người và thích 5.000 bài, đầu vào của bước gom có thể lên tới **50 triệu tổ hợp**, dù đầu ra chỉ có một dòng. Vì hai nhánh không cần ghép từng cặp, có thể tính riêng bằng subquery:

```cypher
MATCH (u:User {id: $userId})
CALL {
  WITH u
  MATCH (u)-[:FOLLOWS]->(f:User)
  RETURN count(DISTINCT f) AS followingCount
}
CALL {
  WITH u
  MATCH (u)-[:LIKED]->(p:Post)
  RETURN count(DISTINCT p) AS likedPostCount
}
RETURN u.id AS userId, followingCount, likedPostCount;
```

Tổng chi phí duyệt từng nhánh vẫn phụ thuộc số quan hệ thực tế, nhưng đã tránh việc nhân hai nhánh thành toàn bộ cặp. Với dữ liệu bảo đảm không có nhiều relationship trùng giữa cùng cặp node cho loại quan hệ đó, có thể cân nhắc bỏ `DISTINCT` khi đếm để giảm chi phí.

Nếu cần trả danh sách, chỉ `collect()` trên tập được giới hạn hợp lý; thu gom hàng triệu node/relationship vào một giá trị có thể gây áp lực bộ nhớ.

### 4.5. Phân trang theo khóa có thứ tự ổn định

Đối với trang tin, nên chỉ lấy một cửa sổ dữ liệu và có khóa sắp xếp ổn định. Ví dụ nếu `publishedAt` và `id` xác định thứ tự giảm dần, có thể dùng cursor của bản ghi cuối trang trước:

```cypher
MATCH (p:Post)
WHERE p.publishedAt >= datetime($from)
  AND p.publishedAt < datetime($to)
  AND (
    $cursorTime IS NULL
    OR p.publishedAt < datetime($cursorTime)
    OR (
      p.publishedAt = datetime($cursorTime)
      AND p.id < $cursorId
    )
  )
  AND EXISTS {
    MATCH (p)-[:HAS_TOPIC]->(:Topic {id: $topicId})
  }
RETURN p.id AS postId, p.publishedAt AS publishedAt
ORDER BY publishedAt DESC, postId DESC
LIMIT $pageSize;
```

Trang đầu truyền `cursorTime = null`; các trang sau truyền thời điểm và ID của bản ghi cuối. Cần đảm bảo `id` duy nhất, giá trị thời gian nhất quán và không thay đổi thứ tự trong vòng đời phân trang. Đổi `SKIP` rất lớn lấy keyset pagination thường giảm việc bỏ qua nhiều dòng, nhưng **không** tự giải quyết một traversal fan-out quá lớn trước bước phân trang.

## 5. Khi nào cần thay đổi mô hình đồ thị?

Nếu các truy vấn phổ biến đã chọn được điểm bắt đầu hợp lý, có đủ bộ lọc và index nhưng vẫn thường xuyên phải duyệt supernode, hãy đánh giá thay đổi cấu trúc. Thiết kế phải xuất phát từ **những câu hỏi ứng dụng cần trả lời**, không chỉ từ số lượng cạnh của node.

### 5.1. Chia cụm theo thời gian hoặc ngữ cảnh truy cập (bucketing)

Thay vì gắn toàn bộ bài viết trực tiếp vào một chủ đề rất phổ biến:

```text
(:Topic)<-[:HAS_TOPIC]-(:Post)  [hàng triệu Post]
```

có thể lưu một mô hình đọc theo ngày:

```text
(:Topic)-[:HAS_DAY]->(:TopicDay)<-[:IN_TOPIC_DAY]-(:Post)
                           day = 2026-11-25
```

Mỗi `TopicDay` đại diện cho **một chủ đề và một ngày**, với thuộc tính `key` duy nhất (ví dụ `"database|2026-11-25"`). `Topic` bây giờ nối tới các bucket, còn mỗi truy vấn theo ngày chỉ mở rộng tới bài thuộc bucket cần đọc.

Tạo constraint và ghi dữ liệu ví dụ:

```cypher
CREATE CONSTRAINT topic_day_key_unique IF NOT EXISTS
FOR (b:TopicDay) REQUIRE b.key IS UNIQUE;
```

```cypher
MERGE (t:Topic {id: $topicId})
MERGE (p:Post {id: $postId})
SET p.publishedAt = datetime($publishedAt)
MERGE (b:TopicDay {key: $topicId + "|" + $day})
SET b.day = date($day)
MERGE (t)-[:HAS_DAY]->(b)
MERGE (p)-[:IN_TOPIC_DAY]->(b);
```

Ở đây `$day` có định dạng `YYYY-MM-DD`; ứng dụng phải định nghĩa rõ múi giờ dùng để quy đổi `publishedAt` thành ngày. Với một bài có nhiều chủ đề, cần tạo liên kết đến bucket tương ứng của từng chủ đề.

Truy vấn bài viết trong một ngày:

```cypher
MATCH (t:Topic {id: $topicId})-[:HAS_DAY]->(b:TopicDay {day: date($day)})
MATCH (p:Post)-[:IN_TOPIC_DAY]->(b)
WHERE p.publishedAt >= datetime($from)
  AND p.publishedAt < datetime($to)
RETURN p.id AS postId, p.publishedAt AS publishedAt
ORDER BY publishedAt DESC, postId DESC
LIMIT $pageSize;
```

Điểm mạnh là giới hạn được miền dữ liệu cần xem theo ngày. Đổi lại, hệ thống có thêm node/relationship và trách nhiệm duy trì tính nhất quán. Nếu một chủ đề vẫn có vài triệu bài **mỗi ngày**, bucket theo ngày còn quá thô: có thể phân theo giờ, phân theo nhóm nghiệp vụ hoặc thêm shard, nhưng luôn cân đối số bucket, độ phức tạp đọc nhiều bucket và ghi đồng thời.

**Lưu ý quan trọng về di trú:** chuyển từ `HAS_TOPIC` sang `IN_TOPIC_DAY` làm thay đổi những truy vấn đang đọc mô hình cũ. Cần lập kế hoạch backfill, kiểm tra số liệu đối chiếu, thay đổi truy vấn đọc và quy trình ghi trước khi ngừng dùng quan hệ cũ. Không mặc nhiên giữ cả hai mô hình mãi mãi vì sẽ làm tăng chi phí đồng bộ.

### 5.2. Biến relationship thành node sự kiện khi nghiệp vụ cần

Nếu một tương tác có vòng đời hoặc nhiều thuộc tính riêng (thời điểm, nguồn phát sinh, trạng thái kiểm duyệt), đôi khi thích hợp mô hình hóa bằng node sự kiện:

```text
(:User)-[:PERFORMED]->(:Reaction {at, source, status})-[:ON_POST]->(:Post)
```

Cách này cho phép truy vấn và quản lý `Reaction` như một thực thể độc lập. Tuy nhiên, **chỉ thêm `Reaction` không làm giảm bậc của `User`**: người thực hiện hàng triệu tương tác vẫn có hàng triệu cạnh `PERFORMED`. Muốn giảm fan-out của truy vấn theo người dùng và thời gian, cần kết hợp điểm bắt đầu chọn lọc, index thuộc tính sự kiện, hoặc bucket thời gian theo người dùng.

Không nên reify tất cả relationship một cách máy móc; số lượng node, cạnh, độ dài traversal và chi phí cập nhật cũng tăng lên.

### 5.3. Tạo mô hình đọc cho truy vấn rất phổ biến

Nếu giao diện chỉ cần tổng số bài theo chủ đề hoặc top bài tương tác trong một khung thời gian, có thể lưu dữ liệu dẫn xuất như `TopicStats`, `DailyTopicStats` hoặc danh sách ID top-N được cập nhật theo lô/sự kiện. Khi đó yêu cầu giao diện không cần duyệt lại mọi `Post` và `LIKED` ở mỗi lần mở trang.

Đánh đổi: dữ liệu dẫn xuất có thể chậm cập nhật, cần quy tắc xử lý sự kiện trễ, cập nhật lặp, sửa/xóa tương tác và đối soát định kỳ. Chỉ chọn khi mức nhất quán và độ trễ cập nhật được nghiệp vụ chấp nhận.

### 5.4. Giữ supernode khi đó là lựa chọn hợp lý

Ví dụ `Country` nối tới rất nhiều `City`, hay `Topic` nối tới nhiều `Post`, có thể diễn tả chính xác nghiệp vụ. Nếu phần lớn truy vấn bắt đầu từ một `Post` rồi đi **một bước** tới `Topic`, node có bậc cao phía `Topic` chưa chắc là vấn đề đáng xử lý.

Việc chia bucket sẽ không có ích nếu mọi truy vấn vẫn phải đọc toàn bộ bucket và hợp nhất toàn bộ kết quả. Hãy tránh tăng độ phức tạp mô hình chỉ để bậc của node nhỏ hơn trên giấy.

## 6. Các sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Duyệt từ `Topic` phổ biến rồi mới lọc `Post.publishedAt` | Có thể mở rất nhiều bài không thuộc khoảng cần tìm | Thử điểm bắt đầu `Post` theo thời gian hoặc bucket có chủ đích; đo `PROFILE` |
| Dùng `[:REL*]` hoặc độ sâu mở | Có thể tạo rất nhiều đường đi, kể cả đường vòng | Giới hạn độ sâu, hướng, loại quan hệ, điểm đầu/đích; chọn thuật toán đường đi đúng nhu cầu |
| Đặt `LIMIT 20` và cho rằng chắc chắn chỉ xử lý 20 dòng | Một số phép lọc/sắp xếp/duyệt đã có thể xử lý nhiều dữ liệu trước `LIMIT` | Quan sát Rows và DB Hits trước operator giới hạn |
| Ghép hai nhánh độc lập trong cùng `MATCH` | Tạo tích Descartes hoặc nhân nhánh không cần thiết | Tách nhánh bằng subquery hay thay đổi yêu cầu kết quả |
| `collect()` tất cả rồi lọc trong ứng dụng | Chuyển chi phí bộ nhớ, mạng và xử lý sang nơi khác | Lọc, giới hạn và phân trang ngay trong truy vấn |
| Thêm bucket hoặc node sự kiện cho mọi quan hệ | Tăng ghi, lưu trữ và độ phức tạp mà không chắc giảm chi phí đọc | Chọn theo truy vấn thường gặp và dữ liệu đo thực tế |
| Dựa vào tổng bậc của node như một ngưỡng cố định | Bỏ qua loại/hướng relationship, index và sự phân bố dữ liệu | Đo số cạnh thực sự duyệt theo từng truy vấn và tham số |

## 7. Quy trình xử lý một truy vấn có nguy cơ bùng nổ

1. **Xác định yêu cầu đầu ra:** cần danh sách node, một đường ngắn nhất, đếm, top-N hay mọi đường đi? Những yêu cầu này có chi phí khác nhau.
2. **Đo phân phối dữ liệu:** chủ đề/người dùng nào có bậc cao, theo từng loại và hướng relationship? Có tính lệch mạnh giữa giá trị phổ biến và hiếm không?
3. **Chạy `EXPLAIN`, sau đó `PROFILE` phù hợp:** ghi lại Rows, DB Hits và vị trí bùng nổ; tránh đánh giá chỉ bằng thời gian chạy một lần.
4. **Tối ưu truy vấn:** dùng nhãn, loại/hướng quan hệ, điều kiện chọn lọc, index, `EXISTS`, subquery, giới hạn độ sâu và phân trang phù hợp.
5. **Đo lại trên các trường hợp đại diện:** đối chiếu ngữ nghĩa kết quả, độ trễ, chi phí đọc và bộ nhớ với cùng dữ liệu/tham số.
6. **Chỉ sau đó cân nhắc đổi mô hình:** bucket, node sự kiện hoặc dữ liệu dẫn xuất khi còn chi phí lớn trong các truy vấn quan trọng; kiểm tra tác động ghi và di trú.

Một chỉ số thực tế rất hữu ích là **số dòng trung gian và DB Hits trên mỗi bản ghi hữu ích được trả về**. Khi tỷ lệ này cao bất thường, truy vấn có thể đang làm nhiều việc không đóng góp trực tiếp cho kết quả.

## 8. Tình huống thực hành

Giả sử chủ đề `"database"` có **2.000.000 bài viết**, trung bình mỗi bài có **50 lượt thích**. Một truy vấn mở rộng từ chủ đề qua bài viết rồi qua lượt thích có thể chạm tới khoảng **100.000.000 cặp bài viết–người thích** trước khi tiếp tục lọc, trong một giả định không có bộ lọc sớm. Trong khi đó, bảng tin chỉ cần 20 bài mới nhất cùng số lượt thích của mỗi bài.

Cách tiếp cận:

- Trước hết chọn 20 bài đúng chủ đề và cửa sổ thời gian, kiểm tra bằng `PROFILE` rằng bước lấy ứng viên có độ chọn lọc tốt. Nguồn ứng viên có thể là index thời gian, bucket, hoặc điểm bắt đầu khác tùy dữ liệu.
- Với **20 bài đã chọn**, mới tính số lượt thích theo từng bài. Nếu lượt thích của từng bài cũng rất lớn và số đếm được hỏi liên tục, đánh giá việc duy trì bộ đếm dẫn xuất.
- Thử tham số cho cả chủ đề phổ biến và hiếm. Đối chiếu tập bài và số đếm trước/sau tối ưu, tránh cải thiện tốc độ bằng cách vô tình đổi yêu cầu nghiệp vụ.

Ví dụ minh họa cách chỉ mở rộng lượt thích sau khi đã chọn trang bài viết:

```cypher
CALL {
  MATCH (p:Post)
  WHERE p.publishedAt >= datetime($from)
    AND p.publishedAt < datetime($to)
    AND EXISTS {
      MATCH (p)-[:HAS_TOPIC]->(:Topic {id: $topicId})
    }
  RETURN p
  ORDER BY p.publishedAt DESC, p.id DESC
  LIMIT $pageSize
}
OPTIONAL MATCH (u:User)-[:LIKED]->(p)
RETURN p.id AS postId,
       p.publishedAt AS publishedAt,
       count(u) AS likeCount
ORDER BY publishedAt DESC, postId DESC;
```

Subquery có giới hạn chọn trang trước khi mở rộng `LIKED` tại truy vấn ngoài. Nó giảm số **bài viết** phải xử lý lượt thích, nhưng vẫn duyệt tất cả lượt thích của từng bài được chọn để đếm; với bài có hàng triệu lượt thích, nên đo kỹ hoặc dùng bộ đếm được duy trì sẵn. Truy vấn cũng giả định mỗi người chỉ có tối đa một relationship `LIKED` đến cùng bài; nếu không, `count(u)` đếm số relationship khớp, không phải số người duy nhất.

### Câu hỏi tự kiểm tra

1. Một `Topic` có 5 triệu cạnh `HAS_TOPIC`, nhưng truy vấn phổ biến là `(p:Post)-[:HAS_TOPIC]->(t:Topic)` cho một bài viết cụ thể. Có bắt buộc phải chia bucket không? **Không**; cần đo chi phí của đường duyệt thực tế trước.
2. Tại sao `LIMIT 10` ở cuối truy vấn có thể vẫn tốn kém? **Vì** nhiều operator trước đó có thể đã mở rộng, gom, sắp xếp hoặc lọc một tập trung gian rất lớn.
3. Khi nào bucket theo ngày hiệu quả? **Khi** phần lớn truy vấn chỉ cần một hoặc vài ngày và mỗi bucket nhỏ hơn đáng kể so với toàn bộ tập, với chi phí quản lý chấp nhận được.
4. Việc tạo `Reaction` node có tự khắc phục supernode `User` không? **Không**; nó phục vụ mô hình nghiệp vụ sự kiện, còn lượng `PERFORMED` của người dùng vẫn có thể rất lớn.
5. Có thể quyết định giữa bắt đầu từ `Topic` và `Post.publishedAt` chỉ bằng nhìn Cypher không? **Không**; độ chọn lọc thực tế và kế hoạch `PROFILE` mới là căn cứ.

## 9. Ghi nhớ

Trong Neo4j, thiết kế đồ thị tốt cần cân bằng **độ tự nhiên của quan hệ**, **độ chọn lọc của điểm bắt đầu** và **số dòng phải mở rộng qua từng bước**. Đối với supernode, hãy ưu tiên hiểu truy vấn đang duyệt loại/hướng cạnh nào và bùng nổ ở operator nào. Với nhu cầu đọc có giới hạn rõ ràng theo thời gian hoặc ngữ cảnh, bucket hay mô hình đọc dẫn xuất có thể giúp giảm fan-out; còn với đường đi tùy ý, cần đặc biệt kiểm soát độ sâu, điểm đầu/đích và số đường đi cần tìm.

Mọi quyết định tối ưu cần được kiểm chứng bằng `EXPLAIN`/`PROFILE`, dữ liệu đại diện và kết quả nghiệp vụ đúng.
