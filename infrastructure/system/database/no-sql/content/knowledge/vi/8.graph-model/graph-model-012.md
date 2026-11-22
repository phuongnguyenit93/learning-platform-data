# Thực nghiệm quan hệ người dùng, phụ thuộc hoặc gợi ý kết nối

## 1. Mục tiêu thực nghiệm

Cơ sở dữ liệu NoSQL **mô hình đồ thị (graph database)** phù hợp với bài toán mà **quan hệ giữa các thực thể** quan trọng không kém thuộc tính của từng thực thể. Thay vì chỉ đặt mã người dùng trong một mảng hoặc thực hiện nhiều lần ghép dữ liệu, mô hình đồ thị biểu diễn trực tiếp các thực thể thành **đỉnh (node/vertex)** và mối liên hệ thành **cạnh (relationship/edge)**.

Bài học này thực hành ba nhóm thao tác thường gặp:

1. **Khám phá quan hệ người dùng:** ai đang theo dõi ai, quan hệ một bước và hai bước khác nhau thế nào.
2. **Gợi ý kết nối:** đề xuất tài khoản chưa được theo dõi dựa trên các đường quan hệ và giải thích điểm gợi ý.
3. **Phân tích phụ thuộc:** dịch vụ nào phụ thuộc trực tiếp hoặc gián tiếp vào một dịch vụ khác, tìm đường phụ thuộc và phát hiện chu trình.

Mục tiêu không phải chỉ lấy được danh sách đỉnh, mà còn hiểu được **hướng cạnh, phạm vi duyệt, cách tránh kết quả trùng, cách đo chi phí và giới hạn của kết luận suy ra từ graph**.

Ví dụ dùng **Neo4j với ngôn ngữ Cypher** để dễ tái hiện. Các nguyên tắc về đỉnh, cạnh và traversal áp dụng cho nhiều graph database khác, nhưng cú pháp truy vấn, chỉ mục, transaction và giới hạn thực thi có thể khác nhau.

## 2. Tư duy từ quan hệ: node, edge, thuộc tính và đường đi

Giả sử một ứng dụng học tập có người dùng, khóa học và các mối quan hệ giữa người dùng. Các câu hỏi cần trả lời gồm:

- “An đang theo dõi những ai?”
- “Bạn của những người An theo dõi là ai?”
- “Ai được nhiều người mà An theo dõi kết nối đến?”
- “An có đang theo dõi tài khoản được đề xuất chưa?”

Một bảng hoặc tài liệu chứa danh sách `followingIds` có thể trả lời câu hỏi đầu tiên. Khi cần đi thêm hai hoặc ba bước và lọc theo trạng thái từng người dùng, việc biểu diễn trực tiếp thành cạnh đồ thị sẽ dễ diễn đạt hơn.

### 2.1. Các thành phần trong đồ thị có hướng

~~~text
(u1:User {name:"An"})  --[:FOLLOWS]-->  (u2:User {name:"Bình"})
       |                                       |
       +-------------[:FOLLOWS]------------> (u3:User {name:"Chi"})
~~~

Trong một graph database dạng property graph:

- **Node** mô tả thực thể, ví dụ `User` hoặc `Service`.
- **Label** nhóm node theo loại, ví dụ `:User`, `:Service`.
- **Relationship type** định nghĩa ngữ nghĩa cạnh, ví dụ `:FOLLOWS` hoặc `:DEPENDS_ON`.
- **Property** mô tả thuộc tính node/cạnh, ví dụ `userId`, `name`, `since`.
- **Path** là chuỗi các node và relationship nối nhau.
- **Traversal** là phép đi theo các cạnh dựa trên hướng, loại cạnh và độ sâu.

**Hướng cạnh mang ý nghĩa nghiệp vụ.** `(A)-[:FOLLOWS]->(B)` nghĩa là A theo dõi B; không thể mặc nhiên hiểu B cũng theo dõi A. Tương tự, `(Web)-[:DEPENDS_ON]->(API)` nghĩa là Web cần API; tác động ngược khi API gặp lỗi phải được tìm qua các cạnh đi **về phía node phụ thuộc**, tức duyệt ngược hướng `DEPENDS_ON`.

### 2.2. Những khái niệm cần phân biệt trong kết quả truy vấn

| Khái niệm | Ý nghĩa | Trong ví dụ |
|---|---|---|
| Hàng xóm một bước | Node nối trực tiếp bằng cạnh phù hợp | Người An theo dõi trực tiếp |
| Hàng xóm hai bước | Node đến được qua hai cạnh | Người được người An theo dõi tiếp tục theo dõi |
| Đường đi | Một chuỗi quan hệ từ nguồn đến đích | An → Bình → Dũng |
| Độ dài đường đi | Số cạnh trên đường đi | Hai cạnh có độ dài 2 |
| Đường đi ngắn nhất | Đường có số cạnh ít nhất trong tập quan hệ đã xét, nếu không có trọng số | Đường phụ thuộc ít bước nhất |
| Bậc vào/bậc ra | Số cạnh đi vào/đi ra theo hướng đã quy định | Số người theo dõi một người / số người người đó theo dõi |
| Chu trình | Đường đi qua các cạnh rồi quay lại điểm xuất phát | API → Catalog → Cache → API |

Graph cho phép đặt câu hỏi theo quan hệ, nhưng **không tự khẳng định một quan hệ là đúng hoặc có tác động nghiệp vụ**. Chất lượng dữ liệu đầu vào và quy tắc diễn giải vẫn rất quan trọng.

## 3. Chuẩn bị môi trường và dữ liệu mẫu

Có thể chạy những truy vấn trong bài bằng **Neo4j Browser** hoặc công cụ tương đương kết nối với một database Neo4j dùng cho học tập. Các ví dụ dùng cú pháp Cypher phổ biến trên Neo4j 5.x; môi trường được quản lý và phiên bản khác có thể có khác biệt về quyền tạo constraint hoặc các tiện ích của công cụ.

**Dùng database thử nghiệm riêng** vì bài có thao tác tạo node và relationship. Nếu môi trường không cho tạo constraint, người học cần quyền thích hợp hoặc dùng database bài thực hành đã được chuẩn bị.

Các script dưới đây sử dụng khóa nghiệp vụ `userId` và `serviceId`. Chúng không phụ thuộc ID nội bộ do DBMS cấp; ID nội bộ có thể thay đổi khi tái tạo, import hoặc chuyển dữ liệu.

### 3.1. Hai đồ thị được dùng trong bài

| Graph | Node | Relationship | Câu hỏi chính |
|---|---|---|---|
| Mạng người dùng | `:User` | `:FOLLOWS` | Theo dõi trực tiếp, hai bước và gợi ý kết nối |
| Phụ thuộc dịch vụ | `:Service` | `:DEPENDS_ON` | Phụ thuộc, đường truyền ảnh hưởng và chu trình |

Dữ liệu tên người và dịch vụ chỉ mang tính minh họa. Không cần dữ liệu cá nhân thật để thực hành traversal.

### 3.2. Tạo ràng buộc duy nhất cho khóa nghiệp vụ

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT service_id_unique IF NOT EXISTS
FOR (s:Service)
REQUIRE s.serviceId IS UNIQUE;
~~~

Ràng buộc duy nhất giúp tránh tạo nhiều node `User` có cùng `userId` hoặc nhiều node `Service` có cùng `serviceId`. Nó cũng hỗ trợ những truy vấn xác định node theo khóa. Một graph lớn thường cần index phù hợp với các truy vấn lọc quan trọng; không phải mọi thuộc tính đều nên được đánh chỉ mục.

## 4. Thực nghiệm A: tạo mạng quan hệ người dùng

### 4.1. Bộ dữ liệu

Sử dụng tám người dùng:

| ID | Tên hiển thị | Trạng thái |
|---|---|---|
| `u1` | An | ACTIVE |
| `u2` | Bình | ACTIVE |
| `u3` | Chi | ACTIVE |
| `u4` | Dũng | ACTIVE |
| `u5` | Hà | ACTIVE |
| `u6` | Lan | ACTIVE |
| `u7` | Mai | ACTIVE |
| `u8` | Nam | ACTIVE |

Tạo các node:

~~~cypher
UNWIND [
  {id: 'u1', name: 'An'},
  {id: 'u2', name: 'Bình'},
  {id: 'u3', name: 'Chi'},
  {id: 'u4', name: 'Dũng'},
  {id: 'u5', name: 'Hà'},
  {id: 'u6', name: 'Lan'},
  {id: 'u7', name: 'Mai'},
  {id: 'u8', name: 'Nam'}
] AS item
MERGE (u:User {userId: item.id})
SET u.name = item.name,
    u.status = 'ACTIVE';
~~~

`UNWIND` biến danh sách thành các hàng; `MERGE` tìm node theo mẫu được chỉ định hoặc tạo nếu chưa có; `SET` cập nhật thuộc tính. Ràng buộc unique giúp bảo đảm `userId` là định danh nghiệp vụ trong mô hình này.

### 4.2. Tạo các quan hệ theo dõi có hướng

~~~cypher
UNWIND [
  {from: 'u1', to: 'u2'},
  {from: 'u1', to: 'u3'},
  {from: 'u2', to: 'u4'},
  {from: 'u2', to: 'u5'},
  {from: 'u3', to: 'u4'},
  {from: 'u3', to: 'u6'},
  {from: 'u5', to: 'u6'},
  {from: 'u4', to: 'u7'},
  {from: 'u6', to: 'u7'},
  {from: 'u8', to: 'u2'}
] AS rel
MATCH (from:User {userId: rel.from})
MATCH (target:User {userId: rel.to})
MERGE (from)-[:FOLLOWS]->(target);
~~~

Đồ thị thu được có cấu trúc logic:

~~~mermaid
flowchart LR
  A["u1: An"] -->|FOLLOWS| B["u2: Bình"]
  A -->|FOLLOWS| C["u3: Chi"]
  B -->|FOLLOWS| D["u4: Dũng"]
  B -->|FOLLOWS| E["u5: Hà"]
  C -->|FOLLOWS| D
  C -->|FOLLOWS| F["u6: Lan"]
  E -->|FOLLOWS| F
  D -->|FOLLOWS| G["u7: Mai"]
  F -->|FOLLOWS| G
  H["u8: Nam"] -->|FOLLOWS| B
~~~

**Điểm cần quan sát:** An theo dõi Bình và Chi; cả Bình lẫn Chi đều theo dõi Dũng; chỉ Bình theo dõi Hà; chỉ Chi theo dõi Lan. Vì vậy Dũng có hai con đường dài hai cạnh từ An, còn Hà và Lan có một con đường.

`MERGE (from)-[:FOLLOWS]->(target)` giúp những lần chạy lại script không tạo thêm cạnh cùng loại và hướng giữa hai node đã khớp. Điều này không thay thế mọi ràng buộc nghiệp vụ: nếu hệ cho nhiều loại quan hệ có thuộc tính thời gian hoặc trạng thái, cần thiết kế khóa và ngữ nghĩa cho từng edge rõ ràng.

## 5. Truy vấn trực tiếp, hai bước và hướng cạnh

### 5.1. Ai được An theo dõi trực tiếp?

~~~cypher
MATCH (an:User {userId: 'u1'})-[:FOLLOWS]->(person:User)
RETURN person.userId AS userId,
       person.name AS name
ORDER BY userId;
~~~

Kết quả mong đợi:

| userId | name |
|---|---|
| u2 | Bình |
| u3 | Chi |

Trong mẫu `(an)-[:FOLLOWS]->(person)`, mũi tên hướng từ An đến người được An theo dõi. Nếu đảo chiều:

~~~cypher
MATCH (person:User)-[:FOLLOWS]->(an:User {userId: 'u1'})
RETURN person.userId AS userId;
~~~

Trên bộ dữ liệu hiện tại, truy vấn đảo chiều trả về **không có hàng nào** vì chưa định nghĩa ai theo dõi An.

**Không có kết quả không có nghĩa truy vấn sai**: trong đồ thị có hướng, truy vấn theo hai chiều trả lời hai câu hỏi khác nhau.

### 5.2. Người ở đúng hai bước từ An

~~~cypher
MATCH (an:User {userId: 'u1'})
      -[:FOLLOWS]->(bridge:User)
      -[:FOLLOWS]->(candidate:User)
RETURN bridge.userId AS via,
       candidate.userId AS candidateId,
       candidate.name AS candidateName
ORDER BY candidateId, via;
~~~

Kết quả:

| via | candidateId | candidateName |
|---|---|---|
| u2 | u4 | Dũng |
| u3 | u4 | Dũng |
| u2 | u5 | Hà |
| u3 | u6 | Lan |

Dũng xuất hiện **hai lần** vì có hai đường đi hợp lệ: An → Bình → Dũng và An → Chi → Dũng. Đó là tính chất quan trọng của phép duyệt: một node đích có thể xuất hiện qua nhiều đường khác nhau.

Nếu chỉ cần danh sách node đích:

~~~cypher
MATCH (:User {userId: 'u1'})-[:FOLLOWS]->(:User)
      -[:FOLLOWS]->(candidate:User)
RETURN DISTINCT candidate.userId AS candidateId,
                candidate.name AS name
ORDER BY candidateId;
~~~

`DISTINCT` loại các hàng đích trùng ở kết quả. Tuy nhiên, **không nên dùng `DISTINCT` quá sớm** nếu bài toán cần đếm số đường đi hoặc số người trung gian: làm vậy có thể mất thông tin để chấm điểm.

### 5.3. Dùng tham số khi truy vấn từ ứng dụng

Trong code ứng dụng, nên truyền `userId` như **tham số**, không ghép trực tiếp nội dung người dùng vào chuỗi Cypher:

~~~cypher
MATCH (me:User {userId: $viewerId})-[:FOLLOWS]->(target:User)
RETURN target.userId AS userId, target.name AS name
ORDER BY userId;
~~~

Ví dụ truyền tham số logic là `viewerId = 'u1'` qua driver hoặc giao diện truy vấn. Việc truyền tham số tách dữ liệu đầu vào khỏi cú pháp truy vấn, giúp truy vấn dễ tái sử dụng và tránh những rủi ro khi nối chuỗi từ dữ liệu không tin cậy.

## 6. Thực nghiệm B: gợi ý kết nối dựa trên người trung gian

Bây giờ đặt câu hỏi:

> “Người An chưa theo dõi nhưng được nhiều người An đang theo dõi tiếp tục theo dõi là ai?”

Đây là một thuật toán gợi ý dựa trên **đường đi hai bước có hướng**. Có thể gọi là *follow-of-follow recommendation*. Trong mạng bạn bè vô hướng, cách tiếp cận gần với “bạn của bạn”; với quan hệ theo dõi có hướng, cần giữ đúng ngữ nghĩa mũi tên.

### 6.1. Quy tắc gợi ý

Một node `candidate` đủ điều kiện nếu:

1. Có đường `An -[:FOLLOWS]-> bridge -[:FOLLOWS]-> candidate`.
2. `candidate` **không phải An**.
3. An **chưa theo dõi trực tiếp** `candidate`.
4. Tài khoản đích đang ở trạng thái `ACTIVE`.
5. Một candidate có nhiều `bridge` khác nhau sẽ được chấm điểm cao hơn.

Điểm minh họa:

\[
\operatorname{score}(u,c)
= \left|\{b \mid u \rightarrow b \land b \rightarrow c\}\right|.
\]

Điểm là **số người trung gian khác nhau**, chưa phải xác suất hai người sẽ kết nối. Điểm 2 nghĩa là có hai trung gian, không phải “khả năng kết nối 2%” hay “độ phù hợp gấp đôi” theo nghĩa thống kê.

### 6.2. Truy vấn Cypher

~~~cypher
MATCH (me:User {userId: 'u1'})
      -[:FOLLOWS]->(bridge:User)
      -[:FOLLOWS]->(candidate:User)
WHERE candidate <> me
  AND candidate.status = 'ACTIVE'
  AND NOT EXISTS {
    MATCH (me)-[:FOLLOWS]->(candidate)
  }
WITH candidate,
     collect(DISTINCT bridge.userId) AS viaUsers
RETURN candidate.userId AS candidateId,
       candidate.name AS name,
       size(viaUsers) AS score,
       viaUsers
ORDER BY score DESC, candidateId ASC
LIMIT 10;
~~~

Kết quả mong đợi:

| candidateId | name | score | Trung gian |
|---|---|---:|---|
| u4 | Dũng | 2 | u2 và u3 |
| u5 | Hà | 1 | u2 |
| u6 | Lan | 1 | u3 |

Thứ tự các phần tử bên trong `viaUsers` không được bảo đảm nếu không sắp xếp tường minh. Bảng chỉ thể hiện tập trung gian, không đòi thứ tự của mảng đó.

**Giải thích từng đoạn:**

- `MATCH` tìm đường hai cạnh từ An qua một người được theo dõi tới candidate.
- `candidate <> me` loại chính An nếu sau này có chu trình.
- `candidate.status = 'ACTIVE'` loại tài khoản không còn hoạt động.
- `NOT EXISTS { MATCH (me)-[:FOLLOWS]->(candidate) }` loại người An đã theo dõi trực tiếp.
- `collect(DISTINCT bridge.userId)` chỉ giữ mỗi trung gian một lần.
- `size(viaUsers)` là điểm chấm theo số trung gian.
- `ORDER BY score DESC, candidateId ASC` ưu tiên điểm cao, phá hòa theo ID để kết quả ổn định hơn.
- `LIMIT 10` giới hạn số hàng trả về; **không nhất thiết giới hạn toàn bộ chi phí duyệt và gom nhóm trước đó**.

Ở dữ liệu này, Dũng được đề xuất đầu tiên vì có hai đường khác nhau; Hà và Lan hòa điểm nên được xếp theo `candidateId`.

### 6.3. Điều gì xảy ra nếu đã theo dõi người được gợi ý?

Thử thêm cạnh:

~~~cypher
MATCH (an:User {userId: 'u1'})
MATCH (dung:User {userId: 'u4'})
MERGE (an)-[:FOLLOWS]->(dung);
~~~

Chạy lại truy vấn gợi ý. Dũng **không còn đủ điều kiện** vì An đã theo dõi trực tiếp. Các kết quả Hà và Lan vẫn hợp lệ.

Để trả môi trường về dữ liệu gốc sau thực nghiệm:

~~~cypher
MATCH (an:User {userId: 'u1'})
      -[r:FOLLOWS]->
      (dung:User {userId: 'u4'})
DELETE r;
~~~

Chỉ xóa **cạnh cụ thể vừa tạo**, không xóa node hay các cạnh khác. Nếu đang làm trên database dùng chung, chỉ chạy phần thay đổi có chủ đích trong môi trường thử nghiệm và bảo đảm dữ liệu mẫu thuộc phạm vi bài thực hành.

## 7. Cùng dữ liệu, hai định nghĩa gợi ý khác nhau

Graph database giúp truy vấn nhiều cấu trúc quan hệ, nhưng **thuật toán gợi ý là lựa chọn nghiệp vụ**, không phải đặc tính tự động của graph.

### 7.1. Phương pháp A: người được người tôi theo dõi tiếp tục theo dõi

Đây là `An → Bình → Dũng`. Truy vấn phần trước trả về Dũng, Hà, Lan.

### 7.2. Phương pháp B: người có đối tượng theo dõi giống tôi

Một cách khác là tìm tài khoản **cũng theo dõi cùng người** với An:

~~~cypher
MATCH (me:User {userId: 'u1'})
      -[:FOLLOWS]->(shared:User)
      <-[:FOLLOWS]-(candidate:User)
WHERE candidate <> me
  AND candidate.status = 'ACTIVE'
  AND NOT EXISTS {
    MATCH (me)-[:FOLLOWS]->(candidate)
  }
WITH candidate,
     collect(DISTINCT shared.userId) AS sharedFollowees
RETURN candidate.userId AS candidateId,
       candidate.name AS name,
       size(sharedFollowees) AS score,
       sharedFollowees
ORDER BY score DESC, candidateId ASC;
~~~

Với dữ liệu mẫu, kết quả là **Nam (`u8`)**, có một tài khoản được cả An và Nam theo dõi: Bình (`u2`).

Hai cách gợi ý có kết quả khác nhau:

| Cách gợi ý | Loại quan hệ đang tìm | Ví dụ trả về cho An |
|---|---|---|
| Follow-of-follow | An theo dõi B; B theo dõi C | Dũng, Hà, Lan |
| Shared followees | An và C cùng theo dõi B | Nam |

Phương pháp A dựa trên **đường tiếp nối**; phương pháp B dựa trên **sự tương đồng trong tập đối tượng đã theo dõi**. Không nên đặt cả hai dưới tên “bạn chung” rồi giả định chúng tương đương.

### 7.3. Từ đếm trung gian đến chuẩn hóa điểm

Đếm trung gian có thể thiên lệch về tài khoản theo dõi rất nhiều người. Với đồ thị lớn, có thể cân nhắc:

- **Jaccard similarity** trên tập quan hệ phù hợp: kích thước giao chia kích thước hợp; có giá trị từ 0 đến 1 nếu cả hai tập được định nghĩa đúng.
- **Adamic–Adar:** tăng trọng số cho láng giềng chung hiếm hơn; thường được dùng trong bài toán dự đoán liên kết.
- **Trọng số thời gian:** giảm trọng số của kết nối quá cũ hoặc kém liên quan theo nghiệp vụ.
- **Điểm kết hợp:** lấy tín hiệu quan hệ, sở thích, ngữ cảnh và những quy tắc loại trừ.

Cần định nghĩa **quan hệ nào** được dùng làm tập để tính Jaccard; đồ thị có hướng có thể dùng tập outgoing, incoming hoặc cả hai, và kết quả sẽ khác nhau. Một điểm số “hợp lý” phải được đánh giá bằng mục tiêu sản phẩm, không chỉ bằng việc kết quả trông có vẻ đúng trên vài người dùng mẫu.

### 7.4. Ràng buộc riêng tư và tính đúng đắn của gợi ý

Khi chuyển từ dữ liệu mẫu sang người dùng thật, thường cần loại:

- Tài khoản người dùng đã chặn hoặc đã bị chặn.
- Tài khoản ẩn/không cho phép khám phá.
- Tài khoản vô hiệu hóa, bị hạn chế hoặc không phù hợp quyền truy cập.
- Quan hệ không còn hiệu lực hoặc dữ liệu đang bị xóa theo yêu cầu.

Giả sử hệ có cạnh `BLOCKS`, có thể thêm điều kiện logic:

~~~cypher
AND NOT EXISTS {
  MATCH (me)-[:BLOCKS]->(candidate)
}
AND NOT EXISTS {
  MATCH (candidate)-[:BLOCKS]->(me)
}
~~~

Đây là **phần minh họa điều kiện** cần thêm vào `WHERE` của một truy vấn hoàn chỉnh, không phải câu lệnh Cypher độc lập. Ví dụ gốc chưa tạo cạnh `BLOCKS`, nên những điều kiện này không làm thay đổi kết quả dữ liệu mẫu. Ứng dụng thực tế còn cần kiểm soát phân quyền ở API và khi truy vấn dữ liệu, không chỉ lọc sau khi gợi ý.

## 8. Thực nghiệm C: mô hình hóa phụ thuộc giữa các dịch vụ

Graph không chỉ dùng cho mạng người dùng. Trong hệ thống phần mềm, dịch vụ thường phụ thuộc nhiều dịch vụ khác; câu hỏi “DB bị lỗi thì thành phần nào có thể bị ảnh hưởng?” là một phép duyệt đồ thị **theo chiều ngược**.

### 8.1. Quy ước hướng cạnh

Ta định nghĩa:

~~~text
(A)-[:DEPENDS_ON]->(B)
nghĩa là A cần B để thực hiện một hoặc nhiều chức năng.
~~~

Ví dụ `Web → API`, `API → Auth`, `Auth → DB`.

Để tìm tất cả **phụ thuộc của Web**, đi theo chiều mũi tên. Để tìm các **thành phần có thể bị ảnh hưởng nếu DB lỗi**, đi ngược chiều mũi tên từ DB.

### 8.2. Tạo các node dịch vụ

~~~cypher
UNWIND [
  {id: 'svc-web', name: 'Web'},
  {id: 'svc-api', name: 'API'},
  {id: 'svc-auth', name: 'Auth'},
  {id: 'svc-catalog', name: 'Catalog'},
  {id: 'svc-order', name: 'Orders'},
  {id: 'svc-db', name: 'DB'},
  {id: 'svc-cache', name: 'Cache'},
  {id: 'svc-notify', name: 'Notifications'},
  {id: 'svc-metrics', name: 'Metrics'}
] AS item
MERGE (s:Service {serviceId: item.id})
SET s.name = item.name;
~~~

### 8.3. Tạo quan hệ phụ thuộc

~~~cypher
UNWIND [
  {from: 'svc-web', to: 'svc-api'},
  {from: 'svc-api', to: 'svc-auth'},
  {from: 'svc-api', to: 'svc-catalog'},
  {from: 'svc-api', to: 'svc-order'},
  {from: 'svc-auth', to: 'svc-db'},
  {from: 'svc-catalog', to: 'svc-db'},
  {from: 'svc-catalog', to: 'svc-cache'},
  {from: 'svc-order', to: 'svc-db'},
  {from: 'svc-order', to: 'svc-notify'},
  {from: 'svc-notify', to: 'svc-cache'}
] AS dep
MATCH (a:Service {serviceId: dep.from})
MATCH (b:Service {serviceId: dep.to})
MERGE (a)-[:DEPENDS_ON]->(b);
~~~

Đồ thị logic:

~~~mermaid
flowchart TD
  Web["Web"] --> API["API"]
  API --> Auth["Auth"]
  API --> Catalog["Catalog"]
  API --> Orders["Orders"]
  Auth --> DB["DB"]
  Catalog --> DB
  Catalog --> Cache["Cache"]
  Orders --> DB
  Orders --> Notify["Notifications"]
  Notify --> Cache
  Metrics["Metrics: độc lập"]
~~~

Mỗi mũi tên là một cạnh `DEPENDS_ON`, hướng từ dịch vụ tiêu thụ tới dịch vụ mà nó cần. Node Metrics trong ví dụ không có cạnh, giúp nhận ra dịch vụ **không nằm trong tập ảnh hưởng theo mô hình này**.

## 9. Truy vấn phụ thuộc trực tiếp và gián tiếp

### 9.1. API phụ thuộc trực tiếp vào những dịch vụ nào?

~~~cypher
MATCH (:Service {serviceId: 'svc-api'})
      -[:DEPENDS_ON]->(dep:Service)
RETURN dep.serviceId AS serviceId,
       dep.name AS name
ORDER BY serviceId;
~~~

Kết quả trực tiếp:

| serviceId | name |
|---|---|
| svc-auth | Auth |
| svc-catalog | Catalog |
| svc-order | Orders |

**Direct dependency** có đúng một cạnh từ nguồn tới đích.

### 9.2. Web phụ thuộc vào những dịch vụ nào ở tối đa năm bước?

~~~cypher
MATCH p = (root:Service {serviceId: 'svc-web'})
          -[:DEPENDS_ON*1..5]->(dep:Service)
WITH dep, min(length(p)) AS minHops
RETURN dep.serviceId AS serviceId,
       dep.name AS name,
       minHops
ORDER BY minHops ASC, serviceId ASC;
~~~

`*1..5` nghĩa là duyệt từ **một đến năm cạnh**. `length(p)` là số cạnh của đường đi, còn `min(length(p))` lấy số bước ít nhất trong những đường phù hợp.

Kết quả mong đợi:

| serviceId | minHops | Một đường giải thích |
|---|---:|---|
| svc-api | 1 | Web → API |
| svc-auth | 2 | Web → API → Auth |
| svc-catalog | 2 | Web → API → Catalog |
| svc-order | 2 | Web → API → Orders |
| svc-cache | 3 | Web → API → Catalog → Cache |
| svc-db | 3 | Web → API → Auth → DB |
| svc-notify | 3 | Web → API → Orders → Notifications |

Có nhiều đường khác nhau tới DB và Cache; bảng chỉ ghi một ví dụ cho mỗi kết quả. Node `svc-metrics` không xuất hiện vì không có đường `DEPENDS_ON` từ Web tới nó.

**Phạm vi độ sâu phải được lựa chọn có chủ đích.** Trên đồ thị lớn, duyệt không giới hạn có thể gặp rất nhiều đường đi. Giới hạn số bước chỉ giới hạn độ sâu, không đảm bảo số đường đi ít nếu bậc của nhiều node cao.

### 9.3. Tìm một đường phụ thuộc ngắn nhất

~~~cypher
MATCH (root:Service {serviceId: 'svc-web'})
MATCH (target:Service {serviceId: 'svc-db'})
MATCH p = shortestPath(
  (root)-[:DEPENDS_ON*..5]->(target)
)
RETURN [n IN nodes(p) | n.serviceId] AS path,
       length(p) AS hops;
~~~

Một kết quả có thể là:

~~~text
[svc-web, svc-api, svc-auth, svc-db] | 3
~~~

Có các đường ngắn nhất khác dài ba cạnh, ví dụ qua `svc-catalog` hoặc `svc-order`. Hàm `shortestPath` trong truy vấn này chọn **một** đường ngắn nhất theo số cạnh; không mặc định xác định duy nhất đường nào khi nhiều đường hòa nhau. Nếu cần liệt kê tất cả đường ngắn nhất, cần dùng cách truy vấn phù hợp với yêu cầu và phiên bản DBMS.

## 10. Phân tích tác động khi một dịch vụ gặp sự cố

Giả sử `svc-db` bị lỗi. Những dịch vụ nào có đường phụ thuộc trực tiếp hoặc gián tiếp đến DB?

Muốn biết điều đó, bắt đầu từ node DB và **duyệt ngược** cạnh `DEPENDS_ON`:

~~~cypher
MATCH p = (failed:Service {serviceId: 'svc-db'})
          <-[:DEPENDS_ON*1..5]-(affected:Service)
WITH affected, min(length(p)) AS dependencyHops
RETURN affected.serviceId AS serviceId,
       affected.name AS name,
       dependencyHops
ORDER BY dependencyHops ASC, serviceId ASC;
~~~

Kết quả dự kiến:

| serviceId | dependencyHops | Lý do |
|---|---:|---|
| svc-auth | 1 | Auth cần DB |
| svc-catalog | 1 | Catalog cần DB |
| svc-order | 1 | Orders cần DB |
| svc-api | 2 | API cần Auth/Catalog/Orders |
| svc-web | 3 | Web cần API |

Như vậy, DB có **ba dịch vụ phụ thuộc trực tiếp** và **hai dịch vụ phụ thuộc gián tiếp** trong đồ thị mẫu.

Điều này cho phép một công cụ vận hành trả lời: “Khi DB gặp sự cố, cần kiểm tra những thành phần nào trước?”

### 10.1. “Có đường phụ thuộc” không chứng minh “chắc chắn ngừng hoạt động”

Kết quả trên là **phạm vi có khả năng bị ảnh hưởng (potential blast radius)**. Một dịch vụ có thể có fallback, cache, chế độ chỉ đọc hoặc tính năng không phụ thuộc DB trong một số request. Ngược lại, một cạnh thiếu trong graph có thể làm bỏ sót thành phần thực sự bị ảnh hưởng.

Trong production, nên bổ sung metadata quan hệ như:

- `criticality`: phụ thuộc bắt buộc hay tùy chọn.
- `feature`: tính năng nào cần phụ thuộc này.
- `environment`: dev, staging hay production.
- `updatedAt`: lần kiểm chứng quan hệ gần nhất.
- `owner` hoặc nguồn tạo dữ liệu: nhóm phụ trách hoặc công cụ discovery.

Cùng với graph, hệ thống quan sát thực tế cần xem **traces, logs, metrics và health checks** để kết luận mức ảnh hưởng.

### 10.2. Khác biệt giữa upstream và downstream

Với quy ước `A DEPENDS_ON B`:

- **Downstream dependencies của A** theo nghĩa “A cần các thành phần nào” được tìm bằng hướng `A → B`.
- **Upstream consumers của B** theo nghĩa “ai phụ thuộc vào B” được tìm bằng hướng ngược `B ← A`.

Hai thuật ngữ “upstream/downstream” đôi khi được dùng theo quy ước khác giữa đội ngũ. Trong tài liệu và truy vấn, nên luôn nêu **hướng cạnh cụ thể** để tránh hiểu ngược.

## 11. Phát hiện chu trình phụ thuộc

Một hệ thống có các phụ thuộc:

~~~text
API → Catalog → Cache → API
~~~

có **chu trình**, nghĩa là API gián tiếp phụ thuộc trở lại chính mình. Những chu trình như vậy có thể làm phức tạp thứ tự khởi động, xử lý sự cố, phân tầng kiến trúc hoặc việc suy luận về phụ thuộc. Không phải mọi chu trình đều khiến hệ thống sai; cần xem quan hệ mô tả **dependency lúc khởi động**, **request thời gian chạy** hay loại tương tác nào.

### 11.1. Tìm chu trình trong dữ liệu hiện có

Với dữ liệu gốc chưa thêm cạnh tạo vòng:

~~~cypher
MATCH p = (s:Service)-[:DEPENDS_ON*1..6]->(s)
RETURN [n IN nodes(p) | n.serviceId] AS cycle
LIMIT 10;
~~~

Dữ liệu gốc không có chu trình nên không có kết quả.

**Giải thích:** mẫu bắt đầu và kết thúc ở cùng một node `s`, đi qua từ một đến sáu cạnh `DEPENDS_ON`. Nếu có chu trình dài hơn sáu cạnh, truy vấn giới hạn này có thể bỏ sót. Đồ thị lớn cần phương pháp phát hiện cycle phù hợp hơn với quy mô và yêu cầu.

### 11.2. Chủ động tạo một chu trình thử nghiệm

~~~cypher
MATCH (cache:Service {serviceId: 'svc-cache'})
MATCH (api:Service {serviceId: 'svc-api'})
MERGE (cache)-[:DEPENDS_ON]->(api);
~~~

Chạy lại truy vấn phát hiện chu trình. Một chu trình có thể tìm thấy là:

~~~text
[svc-api, svc-catalog, svc-cache, svc-api]
~~~

Cũng có thể thấy một chu trình liên quan đến API → Orders → Notifications → Cache → API. Nếu truy vấn trả nhiều chu trình cùng cấu trúc với điểm xuất phát khác, cần chuẩn hóa kết quả trước khi đếm số chu trình duy nhất.

### 11.3. Khôi phục đồ thị về trạng thái ban đầu

~~~cypher
MATCH (cache:Service {serviceId: 'svc-cache'})
      -[r:DEPENDS_ON]->
      (api:Service {serviceId: 'svc-api'})
DELETE r;
~~~

Lệnh xóa đúng cạnh vừa thêm để thực nghiệm. Các node và phụ thuộc gốc được giữ lại.

## 12. Những truy vấn đồ thị cơ bản đang giải quyết vấn đề gì?

| Nhu cầu | Mẫu truy vấn | Ứng dụng |
|---|---|---|
| Tìm láng giềng trực tiếp | Một cạnh từ node đầu | Danh sách người được theo dõi; phụ thuộc trực tiếp |
| Tìm các kết nối qua trung gian | Đường hai cạnh | Follow-of-follow; người có quan hệ chung |
| Lọc node đã biết | `NOT EXISTS` trên cạnh trực tiếp | Loại đề xuất đã kết nối |
| Chấm điểm theo số trung gian | `count(DISTINCT ...)` hoặc tập hợp trung gian | Xếp hạng gợi ý dễ giải thích |
| Tìm đường tới đích | Variable-length path | Phân tích chuỗi phụ thuộc |
| Đường ngắn nhất | Shortest path | Số bước liên hệ ít nhất |
| Duyệt ngược quan hệ | Mũi tên đi từ phía consumer về node bị lỗi | Phạm vi ảnh hưởng sự cố |
| Phát hiện vòng | Đường trở lại node xuất phát | Chu trình phụ thuộc |
| Giới hạn kết quả | `ORDER BY`, `LIMIT`, phân trang | API không trả dữ liệu quá lớn |

Mỗi pattern nên được chọn dựa trên **ý nghĩa cạnh và hướng cạnh**. Nếu không xác định rõ điều này, truy vấn có thể chạy thành công nhưng trả về câu trả lời sai về nghiệp vụ.

## 13. Đo hiệu năng và hiểu giới hạn traversal

### 13.1. Số bước và số đường đi không giống nhau

Giả sử mỗi người trung bình theo dõi 100 người. Một traversal hai bước có thể khám phá tối đa khoảng 10.000 tổ hợp đường trong trường hợp đơn giản, chưa tính trùng và các bộ lọc. Ba bước có thể lớn hơn nhiều.

Đó là hiện tượng **bùng nổ số nhánh (branching explosion)**. Một truy vấn chỉ duyệt ba bước vẫn có thể rất nặng nếu đi qua các node có bậc cực lớn.

Các yếu tố ảnh hưởng chi phí:

- Bậc vào và bậc ra của các node.
- Số bước traversal.
- Lựa chọn hướng và loại cạnh.
- Chỉ mục để tìm node khởi đầu.
- Bộ lọc được áp dụng sớm hay muộn.
- Số đường đi trùng tới cùng node.
- Nhu cầu tính tổng, sắp xếp và phân trang.
- Mô hình phân phối dữ liệu nếu graph database triển khai trên nhiều máy.

### 13.2. EXPLAIN và PROFILE

Với Neo4j, có thể dùng `EXPLAIN` để xem kế hoạch dự kiến, hoặc `PROFILE` để thực thi truy vấn và xem thống kê thực tế. Ví dụ:

~~~cypher
EXPLAIN
MATCH (me:User {userId: 'u1'})
      -[:FOLLOWS]->(bridge:User)
      -[:FOLLOWS]->(candidate:User)
WHERE candidate <> me
RETURN candidate.userId;
~~~

~~~cypher
PROFILE
MATCH (me:User {userId: 'u1'})
      -[:FOLLOWS]->(bridge:User)
      -[:FOLLOWS]->(candidate:User)
WHERE candidate <> me
RETURN DISTINCT candidate.userId;
~~~

Khi quan sát kế hoạch, cần chú ý:

- Truy vấn có tìm node bắt đầu qua index/constraint hay phải scan rộng?
- Những operator nào mở rộng relationship nhiều lần?
- Số hàng trung gian có tăng mạnh so với kết quả cuối?
- Có aggregation, sort hoặc duplicate elimination tốn chi phí không?
- Thời gian phản hồi và mức sử dụng bộ nhớ thay đổi ra sao khi dữ liệu tăng?

`PROFILE` thực thi truy vấn thật. Trong bài đang dùng truy vấn đọc nên thuận tiện quan sát; nếu áp dụng cho câu lệnh ghi, cần nhớ lệnh có thể tạo thay đổi dữ liệu. **Không nên coi kết quả trên tám người dùng mẫu là benchmark để dự đoán hiệu năng với hàng triệu người.**

### 13.3. Cách thiết kế thử tải có ý nghĩa

Một thử nghiệm tiếp theo có thể tạo dữ liệu tổng hợp ở nhiều quy mô:

| Quy mô dữ liệu | Câu hỏi cần đo |
|---|---|
| 100 người dùng, vài trăm cạnh | Kết quả traversal có đúng với bộ dữ liệu quan sát được không? |
| 10.000 người dùng, hàng trăm nghìn cạnh | Điểm gợi ý, số hàng trung gian, p95 và index có thay đổi thế nào? |
| 1 triệu người dùng, phân bố bậc lệch | Node có hàng trăm nghìn người theo dõi có gây bùng nổ traversal không? |
| Đồ thị dịch vụ nhiều tầng | Query tìm đường phụ thuộc và blast radius trong giới hạn số bước có ổn định không? |

Các quy mô trên là **kịch bản thử**, không phải tuyên bố một phiên bản Neo4j hoặc hệ graph bất kỳ có thể đáp ứng mọi mức tải đó trên một cấu hình cố định. Cần dùng dữ liệu có **phân bố bậc thực tế**, vì đồ thị mà tất cả node đều có cùng số cạnh thường che giấu tình huống nóng ở các tài khoản/dịch vụ nổi bật.

## 14. Graph database so với document hoặc relational database

Một bài toán gợi ý kết nối có thể triển khai bằng nhiều mô hình, nhưng chi phí thiết kế và truy vấn khác nhau.

### 14.1. Document chứa danh sách tham chiếu

~~~json
{
  "_id": "u1",
  "name": "An",
  "followingIds": ["u2", "u3"]
}
~~~

Đọc trực tiếp người An theo dõi có thể rất thuận tiện. Nhưng gợi ý hai bước cần lấy document của `u2` và `u3`, hợp các danh sách theo dõi, loại người đã theo dõi, rồi đếm trung gian. Với dữ liệu nhỏ, cách này hoàn toàn khả thi; khi mở rộng số bước và số nhánh, ứng dụng cần quản lý nhiều vòng truy vấn hoặc dùng aggregation thích hợp của DBMS.

### 14.2. Mô hình quan hệ

Có thể dùng bảng `users` và bảng cạnh `follows(from_user_id, to_user_id)`. Truy vấn hai bước sử dụng self-join, còn đường đi nhiều bước có thể dùng recursive CTE nếu DBMS hỗ trợ.

### 14.3. Property graph

Property graph biểu diễn quan hệ thành đối tượng truy vấn trực tiếp, giúp viết các pattern như:

~~~cypher
(me)-[:FOLLOWS]->(bridge)-[:FOLLOWS]->(candidate)
~~~

hoặc:

~~~cypher
(failed)<-[:DEPENDS_ON*1..5]-(affected)
~~~

Cách diễn đạt ngắn gọn có ích khi quan hệ đa dạng và thay đổi theo số bước. Nhưng **graph database không mặc nhiên nhanh hơn mọi document/relational DBMS**. Đọc một hồ sơ theo ID, tổng hợp số liệu dạng bảng hoặc scan dữ liệu lớn có thể phù hợp với mô hình khác. Lựa chọn cần dựa trên truy vấn, chỉ mục, khối lượng dữ liệu, transaction và chi phí vận hành.

| Loại thao tác | Document | Quan hệ | Graph |
|---|---|---|---|
| Đọc một thực thể theo ID | Rất tự nhiên | Rất tự nhiên | Rất tự nhiên |
| Lọc thuộc tính và tổng hợp đơn giản | Phụ thuộc engine/index | Mạnh với SQL/index | Có thể thực hiện, nhưng tùy hệ |
| Kết nối một hoặc hai bước | Có thể qua tham chiếu/aggregation | Có thể qua JOIN | Tự nhiên với relationship |
| Traversal nhiều bước biến độ dài | Có thể phức tạp | Recursive query | Mô hình truy vấn trực tiếp |
| Đếm/giải thích đường kết nối | Cần thiết kế kỹ | CTE/JOIN phù hợp | Pattern path rõ ràng |
| Khối lượng giao dịch nhiều thực thể | Tùy khả năng DBMS | Giao dịch SQL rất phổ biến | Tùy graph DBMS và cấu hình |

## 15. Thực nghiệm nâng cao: đánh giá chất lượng gợi ý

Truy vấn đúng cú pháp mới là điểm khởi đầu. Một hệ gợi ý thực tế cần định nghĩa **mục tiêu đo được**.

### 15.1. Một vài chỉ số phù hợp

- **Precision@K:** trong K gợi ý đầu, bao nhiêu gợi ý được xem là phù hợp theo nhãn đánh giá hoặc hành vi đã chọn.
- **Recall@K:** trong các kết nối phù hợp có thể đề xuất, hệ thống tìm được bao nhiêu ở K vị trí đầu.
- **CTR (click-through rate):** tỷ lệ gợi ý được nhấp trong điều kiện hiển thị đã định nghĩa.
- **Acceptance/follow rate:** tỷ lệ gợi ý dẫn tới hành động theo dõi/kết nối.
- **Coverage:** bao nhiêu người dùng có đủ dữ liệu để nhận đề xuất; có lệch về nhóm người dùng hoạt động nhiều không?
- **Diversity:** gợi ý có quá tập trung vào một cụm quan hệ không?
- **Latency p95/p99:** thời gian dựng danh sách gợi ý dưới tải thực tế.

Những chỉ số tương tác như CTR không tự biểu thị chất lượng dài hạn. Hệ cần cân nhắc quyền riêng tư, lọc nội dung, an toàn người dùng và tình huống người dùng không muốn được gợi ý.

### 15.2. Phân biệt thuật toán đề xuất với dữ liệu tạo nhãn

Nếu dùng kết nối tương lai làm nhãn đánh giá, cần tránh **rò rỉ dữ liệu thời gian (temporal leakage)**: chỉ sử dụng những cạnh đã tồn tại trước mốc tạo gợi ý. Nếu không, thuật toán có thể nhìn thấy chính kết quả tương lai mà nó được yêu cầu dự đoán.

Một thực nghiệm offline có thể:

1. Chọn thời điểm cắt dữ liệu `T0`.
2. Xây graph chỉ từ các cạnh có hiệu lực đến `T0`.
3. Tạo gợi ý cho người dùng từ graph ở `T0`.
4. So sánh với những kết nối mới trong khoảng `T0 → T1`.
5. Tính chỉ số và phân tích theo nhóm người dùng, bậc node, tuổi tài khoản hoặc mức hoạt động.

Đây là một thiết kế đánh giá, chưa phải bằng chứng nhân quả rằng mô hình làm người dùng kết nối nhiều hơn. Khi cần kết luận tác động sản phẩm, phải có thiết kế thực nghiệm phù hợp, ví dụ A/B test với định nghĩa chỉ số và điều kiện an toàn rõ ràng.

## 16. Những lỗi phổ biến khi thực nghiệm graph

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Nhầm hướng cạnh `FOLLOWS` | Trả danh sách người theo dõi thay vì người được theo dõi | Quy định hướng và viết truy vấn có mũi tên tường minh |
| Đếm trực tiếp số hàng đường đi | Một candidate có thể được tính nhiều lần do đường trùng | Dùng `DISTINCT` theo đúng đơn vị đang đếm |
| Dùng `DISTINCT` quá sớm | Mất số lượng trung gian để chấm điểm | Gom nhóm và đếm trước khi bỏ trùng kết quả |
| Không loại quan hệ đã tồn tại | Đề xuất người đã theo dõi | Kiểm tra cạnh trực tiếp bằng `NOT EXISTS` |
| Không loại chính người xem | Có thể tự gợi ý khi graph có chu trình | Điều kiện `candidate <> me` |
| Dùng một loại cạnh để biểu diễn nhiều ngữ nghĩa | Không phân biệt quan hệ theo dõi, chặn hoặc phụ thuộc | Đặt relationship type rõ ràng |
| Traversal không giới hạn trên graph lớn | Bùng nổ số đường đi và tài nguyên | Giới hạn độ sâu, lọc sớm, quan sát cardinality |
| `LIMIT 10` được hiểu là chỉ duyệt 10 node | Vẫn có thể phải xử lý rất nhiều kết quả trung gian | Xem kế hoạch truy vấn và chiến lược giới hạn từ sớm |
| Phụ thuộc đảo hướng | Sai kết luận blast radius | Duyệt từ node bị lỗi theo chiều ngược `DEPENDS_ON` |
| Dựa vào graph lỗi thời | Đề xuất và phân tích sự cố không đúng hiện trạng | Đồng bộ nguồn, lưu `updatedAt`/nguồn phát, theo dõi độ tươi |
| Xem có đường phụ thuộc là chắc chắn sự cố | Báo động quá mức | Kết hợp criticality, fallback và telemetry |
| Không có định danh nghiệp vụ ổn định | Import lại có thể tạo node trùng hoặc khó liên kết | Dùng `userId`, `serviceId` và ràng buộc phù hợp |

## 17. Bài tập tự luyện với bộ dữ liệu trên

### Bài 1: Đếm số người được theo dõi trực tiếp

Viết truy vấn trả `userId` cùng số lượng tài khoản mà mỗi người dùng đang theo dõi. Người dùng không theo dõi ai vẫn phải xuất hiện với số đếm bằng 0.

Gợi ý: dùng `OPTIONAL MATCH` để giữ node không có cạnh.

~~~cypher
MATCH (u:User)
OPTIONAL MATCH (u)-[:FOLLOWS]->(target:User)
RETURN u.userId AS userId,
       u.name AS name,
       count(DISTINCT target) AS followingCount
ORDER BY userId;
~~~

Trong dữ liệu mẫu, `u1` theo dõi 2 người; `u7` theo dõi 0 người. Đây là ví dụ về **bậc ra theo loại cạnh FOLLOWS**.

### Bài 2: Tìm những người có thể đi tới từ An trong tối đa ba bước

~~~cypher
MATCH p = (:User {userId: 'u1'})
          -[:FOLLOWS*1..3]->(target:User)
RETURN target.userId AS userId,
       min(length(p)) AS minHops
ORDER BY minHops, userId;
~~~

Hãy phân biệt người ở **đúng ba bước** với người có **đường ngắn nhất dài ba bước**. Một node có thể được đi tới theo nhiều đường khác nhau; nếu có thêm cạnh trực tiếp, độ dài đường ngắn nhất của nó có thể thay đổi.

### Bài 3: Đề xuất theo hai tiêu chí

Tạo hai bảng gợi ý cho An:

- Bảng A: người được người An theo dõi tiếp tục theo dõi, chấm bằng số trung gian.
- Bảng B: người cùng theo dõi những tài khoản mà An theo dõi, chấm bằng số đối tượng theo dõi chung.

So sánh danh sách và giải thích vì sao **Dũng** xuất hiện trong A, còn **Nam** xuất hiện trong B.

### Bài 4: Phụ thuộc của Catalog

Tìm những dịch vụ mà Catalog phụ thuộc trực tiếp và gián tiếp. Đồ thị mẫu cho biết Catalog cần `svc-db` và `svc-cache` trực tiếp, nên giới hạn một bước đã trả đủ.

### Bài 5: Phạm vi ảnh hưởng khi Cache bị lỗi

Duyệt ngược `DEPENDS_ON` từ `svc-cache`. Trên đồ thị mẫu, những dịch vụ có đường phụ thuộc đến Cache là **Catalog, Notifications, Orders, API và Web**. Dùng `DISTINCT` hoặc phép gom nhóm thích hợp để mỗi dịch vụ chỉ xuất hiện một lần dù có nhiều đường.

### Bài 6: Phát hiện phụ thuộc vòng

Thêm cạnh `Cache → API` trong database thử nghiệm, chạy truy vấn cycle và giải thích vì sao tạo ra chu trình. Sau đó xóa đúng cạnh vừa thêm. Hãy thảo luận: chu trình này chỉ đáng cảnh báo về mặt kiến trúc, hay thực sự làm hệ thống không thể khởi động? Thông tin nào cần thêm để kết luận?

## 18. Kết luận

Thực nghiệm quan hệ người dùng, phụ thuộc dịch vụ và gợi ý kết nối cho thấy thế mạnh của **mô hình đồ thị nằm ở khả năng diễn đạt và khai thác quan hệ**:

- **Quan hệ một bước** trả lời ai kết nối trực tiếp với ai.
- **Đường hai bước và số trung gian** tạo cách gợi ý đơn giản, giải thích được.
- **Các định nghĩa quan hệ khác nhau** dẫn đến kết quả gợi ý khác nhau, dù sử dụng cùng dữ liệu.
- **Traversal theo hướng phụ thuộc** giúp tìm các dịch vụ liên quan, đường ngắn nhất và phạm vi có thể bị ảnh hưởng khi xảy ra sự cố.
- **Phát hiện chu trình** hỗ trợ phân tích kiến trúc và tính hợp lệ của mô hình phụ thuộc.

Khi chuyển sang hệ thống thật, cần bảo vệ thêm **định danh và tính đúng đắn của cạnh, quyền riêng tư, độ tươi dữ liệu, giới hạn số bước duyệt, bậc node bất thường, tính ổn định của điểm xếp hạng và chi phí vận hành**. Một graph database giúp mô tả và truy vấn các kết nối rõ ràng; giá trị thực tế đến từ việc **chọn đúng ngữ nghĩa quan hệ, đặt đúng câu hỏi và kiểm chứng kết quả dưới workload đại diện**.
