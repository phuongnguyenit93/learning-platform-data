# Mạng xã hội: kết nối, bạn chung và khoảng cách quan hệ

Một mạng xã hội thường phải trả lời những câu hỏi tưởng chừng đơn giản: **An đã kết bạn với Bình chưa?**, **An và Dũng có bao nhiêu bạn chung?**, **nên gợi ý An kết nối với ai?**, hoặc **hai người cách nhau bao nhiêu bước quan hệ?** Những câu hỏi này đều dựa trên **mối liên kết giữa các thực thể**, nên rất phù hợp để biểu diễn và truy vấn bằng property graph của Neo4j.

Bài thuộc chương **Ứng dụng đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng Neo4j để mô hình hóa node, relationship và property; khai thác Cypher để tìm quan hệ và đường đi; tạo index/constraint, tối ưu truy vấn và tích hợp qua Java Driver hoặc Spring Data Neo4j. Trong bài này, chúng ta xây một **mạng xã hội nhỏ nhưng có kết quả xác định**, từ đó đi từ mô hình dữ liệu đến truy vấn, kiểm thử, hiệu năng và bảo vệ quyền riêng tư.

> **Phạm vi:** Ví dụ sử dụng Neo4j 5.x và cú pháp Cypher 5 phổ biến. Các ví dụ tập trung vào quan hệ bạn bè đã được chấp nhận (`FRIEND`); chức năng gửi lời mời, chặn người dùng và phân quyền hiển thị được thảo luận như phần mở rộng. Khi dùng Neo4j ở bản Cypher mới hơn, hãy kiểm tra phiên bản và cú pháp shortest-path được hỗ trợ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn mô hình phù hợp giữa **quan hệ có hướng `FOLLOWS`** và **tình bạn hai chiều `FRIEND`**.
2. Thiết kế node người dùng, relationship và khóa nghiệp vụ ổn định; giải thích vì sao cần uniqueness constraint.
3. Viết Cypher tìm bạn trực tiếp, kiểm tra hai người đã kết nối hay chưa và **đếm bạn chung**.
4. Xây truy vấn **gợi ý kết bạn qua hai bước**, loại chính người dùng, người đã kết bạn và đối tượng bị chặn.
5. Tìm **đường đi ngắn nhất theo số cạnh** và phân biệt khoảng cách graph với điểm thân thiết ngoài đời thực.
6. Sử dụng `EXPLAIN`/`PROFILE` và giới hạn phạm vi duyệt để tránh truy vấn bùng nổ trên mạng có nhiều hub.
7. Gọi truy vấn qua Java Driver/Spring Data Neo4j và lập các kiểm thử kết quả, quyền riêng tư, trường hợp biên.

## 2. Tại sao quan hệ mạng xã hội phù hợp với đồ thị?

Trong mô hình quan hệ, bạn có thể lưu bảng `users` và bảng `friendships(user_a_id, user_b_id)`, rồi dùng phép JOIN để tìm bạn chung. Cách đó hoàn toàn hợp lệ, nhất là với tác vụ đơn giản. Mô hình đồ thị trở nên tự nhiên khi câu hỏi tập trung vào **đường đi có số bước thay đổi** hoặc nhiều kiểu quan hệ đan xen:

- Người dùng A là bạn của B; B là bạn của D.
- A và D không phải bạn trực tiếp nhưng có thể **giới thiệu qua B**.
- Một người có thể vừa theo dõi một tác giả, vừa thuộc cùng nhóm, vừa làm việc tại cùng công ty.
- Quyền hiển thị có thể phụ thuộc vào quan hệ và trạng thái của tài khoản.

Trong Neo4j, ta biểu diễn **đối tượng** bằng node, **kết nối** bằng relationship và **thuộc tính** trên cả hai.

~~~mermaid
flowchart LR
    A["SocialUser<br/>A · An"]
    B["SocialUser<br/>B · Bình"]
    C["SocialUser<br/>C · Chi"]
    D["SocialUser<br/>D · Dũng"]
    A ---|FRIEND| B
    A ---|FRIEND| C
    B ---|FRIEND| C
    B ---|FRIEND| D
    C ---|FRIEND| D
~~~

Sơ đồ biểu diễn tình bạn **không phân biệt hướng ở tầng nghiệp vụ**. Neo4j vẫn lưu mỗi relationship với hướng vật lý; khi truy vấn tình bạn, ta có thể viết pattern **không chỉ định hướng** như `(a)-[:FRIEND]-(b)`.

**Lợi thế của đồ thị không thay thế việc thiết kế truy vấn tốt.** Một truy vấn mở rộng hai bước trên các tài khoản có hàng triệu hàng xóm vẫn có thể rất đắt. Chúng ta cần mô hình rõ ràng, chỉ mục thích hợp, phạm vi duyệt hợp lý và kiểm thử tải.

## 3. Quyết định trước: `FOLLOWS` hay `FRIEND`?

Đây là quyết định ngữ nghĩa quan trọng nhất của một mạng xã hội:

| Quan hệ | Hướng nghiệp vụ | Ví dụ | Cypher điển hình |
|---|---|---|---|
| `FOLLOWS` | **Có hướng** | An theo dõi Bình, nhưng Bình chưa chắc theo dõi lại | `(an)-[:FOLLOWS]->(binh)` |
| `FRIEND` | **Hai chiều** ở mức nghiệp vụ | An và Bình đã chấp nhận kết bạn | `(an)-[:FRIEND]-(binh)` |
| `FRIEND_REQUEST` | Có hướng, có trạng thái | An gửi lời mời tới Bình | `(an)-[:FRIEND_REQUEST]->(binh)` |
| `BLOCKED` | Thường có hướng | An chặn Bình | `(an)-[:BLOCKED]->(binh)` |
| `MEMBER_OF` | Có hướng theo mô hình | An là thành viên nhóm G | `(an)-[:MEMBER_OF]->(g)` |

### 3.1. Hai cách lưu tình bạn

**Cách A — Một relationship cho mỗi cặp bạn bè (được dùng trong bài):**

~~~cypher
// Chỉ lưu một cạnh cho một cặp.
(a:SocialUser)-[:FRIEND]->(b:SocialUser)
~~~

- Ứng dụng coi tình bạn là hai chiều, nên truy vấn bằng `-[:FRIEND]-`.
- Chọn một hướng **quy ước**, chẳng hạn `userId` nhỏ hơn → `userId` lớn hơn.
- Không cần tạo hai cạnh đối xứng.
- Khi đọc `(a)-[:FRIEND]-(b)`, Cypher khớp cạnh theo một trong hai hướng.

**Cách B — Lưu hai cạnh đối xứng:**

~~~cypher
(a)-[:FRIEND]->(b)
(b)-[:FRIEND]->(a)
~~~

Cách này có thể phù hợp với một số yêu cầu khác, nhưng phải quản lý chặt tính đối xứng và chống trùng; nếu không, đếm bạn/quan hệ có thể bị **đếm đôi**. Với bài toán kết bạn hai chiều thông thường, một cạnh duy nhất thường đơn giản hơn.

> **Không được dùng `-[:FRIEND]->` để tìm toàn bộ bạn** nếu dữ liệu lưu theo Cách A. Hướng mũi tên chỉ là quy ước lưu trữ; truy vấn phải dùng `-[:FRIEND]-` khi nghiệp vụ coi quan hệ là đối xứng.

### 3.2. Không trộn “theo dõi” với “đã là bạn”

Hai người cùng theo dõi một nghệ sĩ **không có nghĩa họ đã kết bạn**. Hai người theo dõi lẫn nhau cũng chưa chắc tương đương với quan hệ `FRIEND` đã được chấp nhận. Hãy đặt tên relationship theo **sự kiện nghiệp vụ** và không thay thế ý nghĩa bằng một phép so đường đi tiện tay.

## 4. Mô hình property graph dùng trong bài

### 4.1. Node và property

Ta dùng nhãn `:SocialUser` với:

| Property | Kiểu ví dụ | Mục đích |
|---|---|---|
| `userId` | String | Khóa nghiệp vụ ổn định, duy nhất |
| `displayName` | String | Tên hiển thị |
| `isActive` | Boolean | Trạng thái tài khoản phục vụ lọc nghiệp vụ |

Trong hệ thống thật còn có thể có `createdAt`, chế độ riêng tư, trạng thái khóa tài khoản, địa chỉ liên hệ hoặc thông tin profile. **Không đưa dữ liệu nhạy cảm vào kết quả query khi không cần thiết**.

Quan hệ `:FRIEND` có thể có:

| Property | Ý nghĩa |
|---|---|
| `pairKey` | Khóa định danh của cặp người dùng, dùng chống tạo cạnh trùng |
| `since` | Thời điểm quan hệ được chấp nhận |
| `source` | Nguồn kết nối nếu nghiệp vụ cần kiểm toán |

Trong phần mẫu, dùng `pairKey` để minh họa một cách bảo vệ tính duy nhất của relationship. Không dùng internal ID hay `elementId()` thay `userId` làm khóa bền vững.

### 4.2. Constraint trước khi nạp dữ liệu

Chạy trên **database thử nghiệm riêng**:

~~~cypher
CREATE CONSTRAINT social_user_id_unique IF NOT EXISTS
FOR (u:SocialUser)
REQUIRE u.userId IS UNIQUE;
~~~

Với bản Neo4j hỗ trợ relationship property uniqueness, có thể bảo vệ `pairKey`:

~~~cypher
CREATE CONSTRAINT social_friend_pair_unique IF NOT EXISTS
FOR ()-[r:FRIEND]-()
REQUIRE r.pairKey IS UNIQUE;
~~~

Constraint node giúp tìm người dùng theo `userId` và ngăn hai node cùng khóa. Constraint trên `pairKey` giúp ngăn hai cạnh `FRIEND` có **cùng khóa cặp** khi mọi luồng ghi đều thiết lập property đó nhất quán.

**Giới hạn:** uniqueness của property không tự bắt buộc property phải tồn tại. Nếu một luồng ghi tạo `:FRIEND` **không có `pairKey`**, constraint uniqueness đơn thuần không phát hiện cặp đó là trùng. Cần validation, quy tắc ghi tập trung và, khi edition hỗ trợ, cân nhắc thêm existence/key constraint phù hợp.

## 5. Tạo đồ thị mẫu: 7 người, 9 quan hệ bạn bè

Các ký hiệu người dùng:

| userId | displayName |
|---|---|
| A | An |
| B | Bình |
| C | Chi |
| D | Dũng |
| E | Em |
| F | Phúc |
| G | Giang |

### 5.1. Nạp node

~~~cypher
UNWIND [
  {id: 'A', name: 'An'},
  {id: 'B', name: 'Bình'},
  {id: 'C', name: 'Chi'},
  {id: 'D', name: 'Dũng'},
  {id: 'E', name: 'Em'},
  {id: 'F', name: 'Phúc'},
  {id: 'G', name: 'Giang'}
] AS row
MERGE (u:SocialUser {userId: row.id})
SET u.displayName = row.name,
    u.isActive = true;
~~~

### 5.2. Nạp relationship

Dữ liệu mẫu lưu một cạnh `FRIEND` cho mỗi cặp, theo thứ tự `left < right` (so sánh ID dạng chuỗi):

~~~cypher
UNWIND [
  {left: 'A', right: 'B'},
  {left: 'A', right: 'C'},
  {left: 'B', right: 'C'},
  {left: 'B', right: 'D'},
  {left: 'C', right: 'D'},
  {left: 'C', right: 'E'},
  {left: 'D', right: 'F'},
  {left: 'E', right: 'F'},
  {left: 'F', right: 'G'}
] AS pair
MATCH (a:SocialUser {userId: pair.left})
MATCH (b:SocialUser {userId: pair.right})
MERGE (a)-[r:FRIEND {pairKey: pair.left + '|' + pair.right}]->(b);
~~~

Trong dữ liệu này, các cặp là:

~~~text
A—B, A—C, B—C, B—D, C—D, C—E, D—F, E—F, F—G
~~~

~~~mermaid
flowchart LR
    A((A)) --- B((B))
    A --- C((C))
    B --- C
    B --- D((D))
    C --- D
    C --- E((E))
    D --- F((F))
    E --- F
    F --- G((G))
~~~

### 5.3. Xác minh fixture

~~~cypher
MATCH (u:SocialUser)
RETURN count(u) AS users;
// Kỳ vọng: 7 trên database mẫu.
~~~

~~~cypher
MATCH (:SocialUser)-[r:FRIEND]->(:SocialUser)
RETURN count(r) AS friendships;
// Kỳ vọng: 9 trên database mẫu.
~~~

~~~cypher
MATCH (u:SocialUser)-[:FRIEND]-(friend:SocialUser)
RETURN u.userId AS userId,
       count(DISTINCT friend) AS degree
ORDER BY userId;
~~~

Kết quả số bạn trực tiếp (`degree`) kỳ vọng:

| User | A | B | C | D | E | F | G |
|---|---:|---:|---:|---:|---:|---:|---:|
| Số bạn | 2 | 3 | 4 | 3 | 2 | 3 | 1 |

Tổng số bậc bằng `18 = 2 × 9` vì mỗi cạnh vô hướng được đếm là bạn của **hai đầu mút**. Đây là phép kiểm tra dữ liệu mẫu hữu ích, nhưng **không dùng** tổng này thay cho xác minh từng cặp ID nếu yêu cầu nghiệp vụ cao.

**Chạy theo thứ tự:** tạo constraint → nạp node → nạp relationship → xác minh. Các lệnh `MERGE` có thể chạy lại trên dữ liệu mẫu nhất quán, nhưng không tự giải quyết mọi trường hợp có cạnh trùng từ trước hoặc dữ liệu bị sửa ngoài bài.

## 6. Tìm bạn trực tiếp — duyệt một bước

**Câu hỏi:** An (`A`) đã kết bạn với ai?

~~~cypher
MATCH (me:SocialUser {userId: 'A'})-[:FRIEND]-
      (friend:SocialUser)
RETURN DISTINCT friend.userId AS friendId,
       friend.displayName AS name
ORDER BY friendId;
~~~

Kết quả:

| friendId | name |
|---|---|
| B | Bình |
| C | Chi |

Mẫu `-[:FRIEND]-` không quy định hướng. Nếu viết `(me)-[:FRIEND]->(friend)`, kết quả phụ thuộc **hướng vật lý** khi dữ liệu được tạo; với lưu trữ một cạnh theo thứ tự khóa, truy vấn có hướng có thể bỏ sót bạn.

### 6.1. Truy vấn tham số hóa

Trong Java Driver hoặc Spring Data Neo4j, dùng tham số:

~~~cypher
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (friend:SocialUser)
WHERE friend.isActive = true
RETURN DISTINCT friend.userId AS friendId,
       friend.displayName AS name
ORDER BY friendId;
~~~

Đừng ghép `userId` từ HTTP request trực tiếp thành một chuỗi Cypher. Ngoài nguy cơ Cypher injection, dùng tham số còn cho phép một template query rõ ràng, dễ đo đạc và kiểm thử.

### 6.2. Kiểm tra hai người có phải bạn chưa

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
RETURN EXISTS {
    MATCH (a)-[:FRIEND]-(b)
} AS areFriends;
~~~

Với dữ liệu mẫu:

- `A` và `B` → `true`.
- `A` và `D` → `false`.

**Trường hợp biên:** nếu một trong hai ID không tồn tại, hai câu `MATCH` không sinh hàng, nên truy vấn **không trả một record chứa `false`**. Tầng ứng dụng cần phân biệt **user không tồn tại** với **hai user tồn tại nhưng chưa là bạn**, chẳng hạn kiểm tra tài khoản trước hoặc dùng một query có `OPTIONAL MATCH` và quy tắc trả kết quả rõ ràng.

## 7. Bạn chung — giao của hai tập hàng xóm

Về mặt tập hợp, gọi `N(u)` là tập người dùng có cạnh `FRIEND` với `u`:

~~~text
N(A) = {B, C}
N(D) = {B, C, F}

Bạn chung của A và D = N(A) ∩ N(D) = {B, C}
~~~

Cypher có thể diễn đạt trực tiếp bằng hai cạnh:

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
WHERE a <> b
MATCH (a)-[:FRIEND]-(common:SocialUser)-[:FRIEND]-(b)
RETURN DISTINCT common.userId AS commonFriendId,
       common.displayName AS name
ORDER BY commonFriendId;
~~~

Với `userA = 'A'`, `userB = 'D'`:

| commonFriendId | name |
|---|---|
| B | Bình |
| C | Chi |

**Cypher hoạt động thế nào?**

1. Tìm node `a` và `b` theo unique business ID.
2. Mở rộng từ `a` qua một cạnh `FRIEND` đến `common`.
3. Chỉ giữ `common` có một cạnh `FRIEND` khác nối đến `b`.
4. Trả về `DISTINCT` vì dữ liệu bẩn có thể có nhiều cạnh cùng cặp, gây trùng hàng.

`a <> b` ngăn việc “so một người với chính họ” bị hiểu nhầm là bài toán bạn chung. Với quan hệ bạn bè một cạnh cho mỗi cặp, người dùng `common` không phải `a` hoặc `b` khi dữ liệu không có self-loop; nhưng trong hệ thống cho phép dữ liệu bất thường, vẫn nên test self-loop và cạnh trùng.

### 7.1. Đếm số bạn chung, kể cả khi không có bạn chung

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
WHERE a <> b
OPTIONAL MATCH (a)-[:FRIEND]-(common:SocialUser)-[:FRIEND]-(b)
RETURN count(DISTINCT common) AS mutualCount;
~~~

Với `A` và `D`, kết quả `mutualCount = 2`. Nếu hai người **tồn tại, khác nhau** nhưng không có bạn chung, `OPTIONAL MATCH` kết hợp `count(DISTINCT common)` sẽ trả `0`. Nếu không có một trong hai ID, phần `MATCH` ban đầu không sinh hàng và query cũng **không trả record**.

### 7.2. “Bạn chung” không phải “theo dõi chung”

Trong mạng theo dõi có hướng:

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
MATCH (a)-[:FOLLOWS]->(same:SocialUser)<-[:FOLLOWS]-(b)
RETURN DISTINCT same.userId AS bothFollow;
~~~

Query này trả **tài khoản mà cả A và B cùng theo dõi**, khác với người đang theo dõi cả hai, và khác với bạn chung qua `FRIEND`. Luôn xác định **hướng cạnh và ý nghĩa nghiệp vụ** trước khi gọi một kết quả là “mutual”.

## 8. Gợi ý kết bạn — người cách hai bước

Một nguyên tắc gợi ý đơn giản là **friend-of-a-friend**: tìm những người chưa kết bạn trực tiếp với `me` nhưng có nhiều bạn chung. Với đồ thị mẫu:

~~~text
A đã kết bạn với B và C.

A → B → D    (bạn chung B)
A → C → D    (bạn chung C)
A → C → E    (bạn chung C)

Gợi ý cho A:
D có 2 bạn chung (B, C).
E có 1 bạn chung (C).
~~~

### 8.1. Truy vấn gợi ý cơ bản

~~~cypher
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND candidate.isActive = true
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId,
       candidate.displayName AS name,
       mutualCount
ORDER BY mutualCount DESC, candidateId ASC
LIMIT 20;
~~~

Với `userId = 'A'`:

| candidateId | name | mutualCount |
|---|---|---:|
| D | Dũng | 2 |
| E | Em | 1 |

**Các điều kiện là cần thiết:**

- `candidate <> me`: điều kiện phòng thủ để không đề xuất chính người đang xem. Với dữ liệu mẫu một cạnh cho mỗi cặp, Cypher không tái sử dụng cùng một relationship trong một path `MATCH`, nên vòng `A → B → A` qua **cùng một cạnh** thực ra không xuất hiện; điều kiện vẫn có ích nếu mô hình hoặc dạng truy vấn thay đổi.
- `NOT EXISTS { MATCH (me)-[:FRIEND]-(candidate) }`: loại những người **đã là bạn**.
- `count(DISTINCT bridge)`: đếm **số người trung gian khác nhau**, không phải số đường có thể bị nhân vì quan hệ trùng.
- `ORDER BY mutualCount DESC, candidateId ASC`: ưu tiên nhiều bạn chung, đồng thời tạo thứ tự ổn định khi bằng điểm.
- `LIMIT 20`: giới hạn danh sách trả về, **không bảo đảm engine chỉ cần duyệt 20 ứng viên** trước khi tính `mutualCount`.

### 8.2. Tôn trọng trạng thái chặn

Nếu có quan hệ `BLOCKED` có hướng, cần loại những ứng viên bị một trong hai phía chặn:

~~~cypher
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND candidate.isActive = true
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
  AND NOT EXISTS {
      MATCH (me)-[:BLOCKED]->(candidate)
  }
  AND NOT EXISTS {
      MATCH (candidate)-[:BLOCKED]->(me)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId,
       candidate.displayName AS name,
       mutualCount
ORDER BY mutualCount DESC, candidateId ASC
LIMIT $limit;
~~~

Nếu dữ liệu mẫu chưa tạo cạnh `BLOCKED`, kết quả vẫn là `D` rồi `E`. Trên production, còn cần kiểm tra trạng thái **lời mời đang chờ, tài khoản riêng tư, giới hạn tuổi, phạm vi tổ chức, trạng thái khóa và quyền xem bạn chung**. Không chỉ dựa vào một truy vấn lọc để bảo đảm mọi chính sách riêng tư đã được áp dụng.

### 8.3. Điểm gợi ý có nhiều cách tính

Đếm bạn chung là **một heuristic**, không phải thước đo đúng tuyệt đối:

| Điểm | Ý nghĩa | Ưu/nhược |
|---|---|---|
| **Common neighbors** | `|N(a) ∩ N(b)|` | Dễ giải thích; ưu tiên người có nhiều bạn |
| **Jaccard similarity** | `|N(a) ∩ N(b)| / |N(a) ∪ N(b)|` | Chuẩn hóa theo quy mô mạng của hai người |
| **Adamic–Adar** | Bạn chung ít kết nối được trọng số cao hơn | Giảm tác động của các hub; phức tạp hơn |
| **Graph embedding/ML** | Điểm từ mô hình học máy trên graph | Có thể biểu diễn tín hiệu phức tạp, cần pipeline và đánh giá công bằng/riêng tư |

Ví dụ, A có hai bạn là B/C, D có ba bạn B/C/F, nên `Jaccard(A,D) = 2 / 3`. Với E có hai bạn C/F, `Jaccard(A,E) = 1 / 3`. Trường hợp hai tập hàng xóm đều rỗng cần quy định riêng (chẳng hạn trả điểm 0, không chia cho 0).

Nếu có Graph Data Science (GDS), một số thuật toán dự đoán liên kết/độ tương đồng có thể hỗ trợ gợi ý ở quy mô lớn, tùy phiên bản và license. **Không bắt buộc cài GDS** để chạy các truy vấn bạn chung cơ bản trong bài.

## 9. Khoảng cách quan hệ — đường đi ngắn nhất

Trong đồ thị tình bạn, **khoảng cách theo số bước (hop distance)** giữa hai người là số cạnh `FRIEND` trên **đường đi ngắn nhất** nối họ.

Ví dụ:

| Cặp | Khoảng cách ngắn nhất | Một đường đi hợp lệ |
|---|---:|---|
| A — B | 1 | A → B |
| A — D | 2 | A → B → D |
| A — E | 2 | A → C → E |
| A — F | 3 | A → C → E → F |
| A — G | 4 | A → C → E → F → G |

Có thể tồn tại **nhiều đường đi ngắn nhất** cùng số bước. Chẳng hạn A đến D có hai đường đi dài 2: `A–B–D` và `A–C–D`. Đừng viết test cứng rằng kết quả **phải chọn một chuỗi node cụ thể** khi thuật toán chỉ bảo đảm độ dài ngắn nhất.

### 9.1. Truy vấn `shortestPath` theo số hop

Với cú pháp Cypher 5 thông dụng:

~~~cypher
MATCH (start:SocialUser {userId: $fromId})
MATCH (finish:SocialUser {userId: $toId})
WHERE start <> finish
OPTIONAL MATCH p = shortestPath(
    (start)-[:FRIEND*1..6]-(finish)
)
RETURN
    CASE WHEN p IS NULL THEN null ELSE length(p) END AS hops,
    CASE WHEN p IS NULL
         THEN []
         ELSE [u IN nodes(p) | u.userId]
    END AS pathUserIds;
~~~

Với `fromId = 'A'` và `toId = 'G'`, mong đợi `hops = 4`. Một đường đi hợp lệ là `['A', 'B', 'D', 'F', 'G']` hoặc `['A', 'C', 'E', 'F', 'G']`, tùy cách Neo4j chọn đường đi.

**Giải thích từng phần:**

- `shortestPath(...)` tìm một đường có **ít cạnh nhất** trong mẫu.
- `*1..6` giới hạn số cạnh từ **1 tới 6**. Đây là giới hạn truy vấn, **không phải** bán kính quan hệ cố định của mọi mạng xã hội.
- `length(p)` trả số relationship trong path.
- `nodes(p)` trả các node nằm trên đường đi, sau đó list comprehension lấy `userId`.
- `OPTIONAL MATCH` giúp trả `null`/`[]` khi hai người đều tồn tại nhưng **không có đường trong tối đa sáu bước**.

**Trường hợp biên:**

- Nếu `start` hoặc `finish` không tồn tại, các `MATCH` đầu không có hàng; query **không trả record**. Ứng dụng phải xử lý riêng.
- Nếu hai ID bằng nhau, điều kiện `start <> finish` loại hàng; về mặt toán học khoảng cách từ một node đến chính nó là **0**. Ứng dụng có thể trả 0 trước khi chạy query.
- Nếu kết quả `p IS NULL` với giới hạn 6, chỉ được kết luận **không tìm thấy đường dài tối đa 6 bước**, không phải toàn mạng hoàn toàn không liên thông.
- Nếu tồn tại nhiều đường đi ngắn nhất, đường cụ thể được chọn không nhất thiết ổn định qua phiên bản/kế hoạch.

Trên Neo4j mới hỗ trợ **path selectors** như `ANY SHORTEST`, có thể dùng cú pháp lựa chọn đường đi thay cho hàm `shortestPath(...)` theo tài liệu phiên bản đích. Không trộn cú pháp mới với một server Cypher cũ chưa hỗ trợ.

### 9.2. Khi cần tất cả đường đi ngắn nhất

~~~cypher
MATCH (a:SocialUser {userId: 'A'})
MATCH (d:SocialUser {userId: 'D'})
MATCH p = allShortestPaths((a)-[:FRIEND*1..3]-(d))
RETURN [u IN nodes(p) | u.userId] AS pathUserIds,
       length(p) AS hops
ORDER BY pathUserIds;
~~~

Với dữ liệu mẫu, có **hai đường đi dài 2** qua B và C. Trên graph lớn, số đường đi ngắn nhất có thể tăng rất mạnh; **không dùng `allShortestPaths` không giới hạn** để trả tất cả đường của hai người trên một mạng nhiều triệu node.

### 9.3. Khoảng cách theo hop khác đường có trọng số

Trong mạng xã hội, đường đi qua hai bạn thân có thể được đánh giá khác đường đi qua hai tài khoản ít tương tác. Nhưng `shortestPath` thông thường tối thiểu hóa **số cạnh**, không tối thiểu hóa tổng trọng số tương tác.

Nếu cần khoảng cách có trọng số (ví dụ chi phí kết nối không âm), xem xét thuật toán **Dijkstra** hoặc những biến thể đường đi có trọng số được bản Neo4j GDS hỗ trợ. Khi chọn trọng số, phải xác định rõ **giá trị càng nhỏ là đường càng tốt** hay ngược lại; số lần tương tác cao không tự động là “chi phí nhỏ” trừ khi đã chuyển đổi ý nghĩa của feature.

**Đường đi gần không đồng nghĩa hai người thân thiết hoặc đáng tin cậy.** Hệ thống giới thiệu bạn cần phân biệt tín hiệu graph với chính sách an toàn, quyền hiển thị và nguy cơ suy diễn thông tin cá nhân.

## 10. Khi mô hình là `FOLLOWS` có hướng

Nếu ứng dụng thiên về theo dõi (tác giả, kênh, nội dung), đừng dùng query bạn bè vô hướng cho `FOLLOWS`.

Giả sử dữ liệu:

~~~cypher
MATCH (a:SocialUser {userId: 'A'})
MATCH (b:SocialUser {userId: 'B'})
MATCH (c:SocialUser {userId: 'C'})
MERGE (a)-[:FOLLOWS]->(b)
MERGE (c)-[:FOLLOWS]->(b)
MERGE (b)-[:FOLLOWS]->(a);
~~~

Lưu ý lệnh bổ sung cạnh `FOLLOWS` vào **cùng graph mẫu** nhưng không thay các cạnh `FRIEND`. Khi đó:

~~~cypher
// Những tài khoản B theo dõi:
MATCH (b:SocialUser {userId: 'B'})-[:FOLLOWS]->
      (following:SocialUser)
RETURN following.userId AS followingId;
// Theo fixture FOLLOWS bổ sung: A
~~~

~~~cypher
// Những tài khoản theo dõi B:
MATCH (follower:SocialUser)-[:FOLLOWS]->
      (b:SocialUser {userId: 'B'})
RETURN follower.userId AS followerId
ORDER BY followerId;
// A, C
~~~

Kiểm tra **theo dõi lẫn nhau**:

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
RETURN EXISTS { MATCH (a)-[:FOLLOWS]->(b) } AS aFollowsB,
       EXISTS { MATCH (b)-[:FOLLOWS]->(a) } AS bFollowsA;
~~~

Nếu cả hai trường đều `true`, đó là **mutual following**; việc tự biến nó thành quan hệ `FRIEND` còn phụ thuộc luật sản phẩm. Trong graph có hướng, khoảng cách `A → B` có thể **khác** khoảng cách `B → A`; với `FRIEND` vô hướng, khoảng cách giữa hai đầu mút là đối xứng.

## 11. Thiết kế thao tác kết bạn không trùng dữ liệu

Ở mô hình một cạnh cho một cặp, cần tạo quan hệ theo **thứ tự ID chuẩn hóa** để request `A kết bạn B` và `B kết bạn A` dẫn tới **cùng một cặp**.

~~~cypher
MATCH (u:SocialUser {userId: $userA})
MATCH (v:SocialUser {userId: $userB})
WHERE u <> v
WITH
    CASE WHEN u.userId < v.userId THEN u ELSE v END AS leftUser,
    CASE WHEN u.userId < v.userId THEN v ELSE u END AS rightUser
WITH leftUser, rightUser,
     leftUser.userId + '|' + rightUser.userId AS canonicalPairKey
MERGE (leftUser)-[r:FRIEND {pairKey: canonicalPairKey}]->(rightUser)
ON CREATE SET r.since = datetime()
RETURN r.pairKey AS pairKey;
~~~

**Điều kiện trước khi chạy:** ứng dụng đã xác minh lời mời **được chấp nhận**, cả hai tài khoản đủ điều kiện kết nối, không có trạng thái chặn và người gọi có quyền. Query trên **chỉ tập trung lưu relationship**; không được dùng nó trực tiếp làm endpoint “kết bạn với bất kỳ ai” bỏ qua validation/authorization.

### Tại sao cần constraint?

`MERGE` giúp nhận diện mẫu đã tồn tại trong một transaction, nhưng với nhiều giao dịch đồng thời, **chỉ một câu `MERGE` không thay được ràng buộc tính duy nhất ở database**. Nếu cần chống tạo trùng dưới tải, nên có unique constraint trên `pairKey` và bắt buộc mọi đường ghi đều thiết lập nó theo cùng quy tắc.

Nếu giao dịch gặp lỗi uniqueness dưới cạnh tranh, Java Driver có thể trả lỗi schema không phải transient; không retry vô hạn. Tầng dịch vụ có thể đọc lại quan hệ sau lỗi để xác định request đã được xử lý hay là xung đột dữ liệu.

### Mô hình lời mời thay vì tạo bạn ngay

Một sản phẩm thực tế thường đi qua:

~~~mermaid
flowchart LR
    A["A gửi lời mời B"] --> P["FRIEND_REQUEST<br/>PENDING"]
    P -->|"B chấp nhận"| F["FRIEND<br/>một cạnh chuẩn hóa"]
    P -->|"B từ chối"| R["REJECTED / lưu lịch sử theo chính sách"]
    P -->|"A hủy"| C["CANCELLED"]
~~~

Trạng thái lời mời có thể lưu trên relationship hoặc node sự kiện riêng để quản lý audit. Nếu cần nhiều lịch sử lời mời theo thời gian, một relationship `FRIEND_REQUEST` duy nhất cập nhật state có thể không đủ để giữ lịch sử. Quyết định phụ thuộc nghiệp vụ, không phải quy tắc bắt buộc của Neo4j.

## 12. Java Driver: đưa gợi ý kết bạn vào ứng dụng

Một cách tích hợp là giữ Cypher có tham số trong lớp repository, dùng **managed read transaction** và ánh xạ kết quả sang DTO. Ví dụ Java 17+ và Neo4j Java Driver phiên bản hỗ trợ `executeRead`:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class SocialGraphQueries {
    private final Driver driver;
    private final String database;

    public record Suggestion(
            String userId, String displayName, long mutualCount) {}

    public SocialGraphQueries(Driver driver, String database) {
        this.driver = driver;
        this.database = database;
    }

    public List<Suggestion> suggestFriends(String viewerId, int limit) {
        if (viewerId == null || viewerId.isBlank()) {
            throw new IllegalArgumentException("viewerId is required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        try (Session session =
                driver.session(SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                    MATCH (me:SocialUser {userId: $viewerId})
                          -[:FRIEND]-(bridge:SocialUser)
                          -[:FRIEND]-(candidate:SocialUser)
                    WHERE candidate <> me
                      AND candidate.isActive = true
                      AND NOT EXISTS {
                          MATCH (me)-[:FRIEND]-(candidate)
                      }
                      AND NOT EXISTS {
                          MATCH (me)-[:BLOCKED]->(candidate)
                      }
                      AND NOT EXISTS {
                          MATCH (candidate)-[:BLOCKED]->(me)
                      }
                    WITH candidate,
                         count(DISTINCT bridge) AS mutualCount
                    RETURN candidate.userId AS id,
                           candidate.displayName AS name,
                           mutualCount
                    ORDER BY mutualCount DESC, id ASC
                    LIMIT $limit
                    """, Map.of(
                            "viewerId", viewerId,
                            "limit", limit))
                    .list(record -> new Suggestion(
                            record.get("id").asString(),
                            record.get("name").asString(),
                            record.get("mutualCount").asLong())));
        }
    }
}
~~~

Lời gọi:

~~~java
// Driver nên là instance dùng lâu dài, quản lý tập trung.
SocialGraphQueries queries = new SocialGraphQueries(driver, "neo4j");
var suggestions = queries.suggestFriends("A", 10);
// Dữ liệu mẫu: D có mutualCount 2, E có mutualCount 1.
~~~

**Các điểm kỹ thuật:**

1. `Driver` thường dùng chung nhiều thread và được quản lý theo vòng đời ứng dụng; `Session` tạo ngắn hạn cho từng tác vụ, **không** chia sẻ giữa thread.
2. `executeRead` báo driver đây là **read transaction** và có thể retry lỗi tạm thời theo chính sách; callback chỉ đọc và ánh xạ nên phù hợp để chạy lại.
3. `Map.of` và tham số `$viewerId`, `$limit` tránh nối dữ liệu người dùng vào cấu trúc Cypher.
4. Chuyển về DTO `Suggestion` thay vì trả cả node/relationship giúp giới hạn thông tin API.
5. Giới hạn `limit` ở tầng Java để tránh endpoint bị yêu cầu trả số lượng quá lớn; nhưng lượng ứng viên cần duyệt/tổng hợp trước `LIMIT` vẫn phụ thuộc graph.
6. Query chỉ thể hiện **một phần** chính sách sản phẩm. Tầng dịch vụ phải kiểm tra quyền người gọi, trạng thái bạn chung, visibility của candidate và chống lạm dụng API.

### 12.1. Đọc khoảng cách quan hệ từ Java

Có thể dùng cùng `Driver` cho truy vấn khoảng cách. Vì `hops` có thể là `null`, không nên gọi `asInt()` trực tiếp khi chưa kiểm tra:

~~~java
import java.util.Map;
import java.util.OptionalInt;

public OptionalInt distance(String fromId, String toId) {
    if (fromId.equals(toId)) {
            // API thực tế phải xác minh user tồn tại và có quyền truy cập.
        return OptionalInt.of(0);
    }
    try (Session session =
            driver.session(SessionConfig.forDatabase(database))) {
        return session.executeRead(tx -> {
            var record = tx.run("""
                MATCH (a:SocialUser {userId: $fromId})
                MATCH (b:SocialUser {userId: $toId})
                OPTIONAL MATCH p = shortestPath(
                    (a)-[:FRIEND*1..6]-(b)
                )
                RETURN CASE WHEN p IS NULL
                            THEN null
                            ELSE length(p)
                       END AS hops
                """, Map.of(
                    "fromId", fromId,
                    "toId", toId)).single();
            return record.get("hops").isNull()
                    ? OptionalInt.empty()
                    : OptionalInt.of(record.get("hops").asInt());
        });
    }
}
~~~

Đoạn `distance` là **phương thức bổ sung** vào `SocialGraphQueries` ở trên, cần đặt trong cùng class để dùng `driver` và `database`. Nếu người dùng đầu vào không tồn tại, `.single()` sẽ ném lỗi; ứng dụng cần phân biệt `404 Not Found`, `403 Forbidden` và “không có đường trong giới hạn” theo đặc tả API của mình.

## 13. Spring Data Neo4j: repository và mapping

Với Spring Data Neo4j, một entity đơn giản:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("SocialUser")
public class SocialUser {
    @Id
    private String userId;
    private String displayName;
    private boolean isActive;

    protected SocialUser() {}

    public SocialUser(String userId, String displayName) {
        this.userId = userId;
        this.displayName = displayName;
        this.isActive = true;
    }

    public String getUserId() { return userId; }
    public String getDisplayName() { return displayName; }
    public boolean isActive() { return isActive; }
}
~~~

Repository chỉ đọc bạn trực tiếp:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface SocialUserRepository
        extends Neo4jRepository<SocialUser, String> {

    @Query("""
        MATCH (me:SocialUser {userId: $userId})
              -[:FRIEND]-(friend:SocialUser)
        WHERE friend.isActive = true
        RETURN DISTINCT friend
        ORDER BY friend.userId
        """)
    List<SocialUser> findActiveFriends(@Param("userId") String userId);
}
~~~

Đây là mô hình **entity chỉ gồm thuộc tính của node**, chưa map các relationship. Vì vậy `RETURN DISTINCT friend` phù hợp để đọc đối tượng `SocialUser` đơn giản. Với entity có `@Relationship` và custom query trả đồ thị phức tạp, cần đọc hướng dẫn SDN về **mapping relationship và kết quả custom query**; không giả định `RETURN friend` luôn tải đầy đủ mọi cạnh liên quan.

**Chú ý:**

- `@Id` đánh dấu khóa định danh trong ánh xạ Java, **không tự chứng minh uniqueness constraint đã được tạo trong Neo4j**.
- `@Query` là Cypher do lập trình viên viết; kiểm thử nó bằng Neo4j thật. Repository derived query cũng cần test vì framework có thể sinh Cypher khác tưởng tượng.
- Với truy vấn chỉ cần thống kê bạn chung hoặc gợi ý, trả **DTO/projection** hoặc dùng `Neo4jClient` để map scalar thường phù hợp hơn việc tải một object graph lớn.
- Dùng `@Transactional(readOnly = true)` ở tầng service khi phù hợp, nhưng annotation này **không thay thế kiểm soát quyền xem bạn bè**.

## 14. Tối ưu Cypher trên mạng xã hội lớn

Mạng xã hội thật có thể chứa hàng triệu người và những node “hub” với rất nhiều người theo dõi. Truy vấn hai bước có thể nhân rất nhiều hàng trung gian:

~~~text
Một node có 10.000 bạn/hàng xóm.
Mỗi người hàng xóm lại kết nối 10.000 người.

Phép mở rộng hai bước có thể sinh tới 100.000.000 lượt
ghép đường đi trước khi loại trùng và giới hạn kết quả.

Đây là ước lượng minh họa về bậc node, không phải kết quả benchmark.
~~~

### 14.1. Bắt đầu từ node có chỉ mục

~~~cypher
CREATE CONSTRAINT social_user_id_unique IF NOT EXISTS
FOR (u:SocialUser)
REQUIRE u.userId IS UNIQUE;
~~~

Neo4j có thể tìm `userId` nhanh nhờ index nền của constraint, rồi mở rộng quan hệ từ đúng một node. Thay vì duyệt **mọi** cặp hai bước trong toàn mạng rồi lọc theo `userId`, viết query có điểm xuất phát rõ.

### 14.2. Giới hạn độ sâu và loại quan hệ

- Gợi ý bạn chung: chỉ cần **hai cạnh `FRIEND`**.
- Khoảng cách xã hội: quy định **giới hạn hop** hoặc ngân sách tài nguyên nếu API không thể chờ một tìm kiếm không giới hạn.
- Nếu graph có `FRIEND`, `FOLLOWS`, `MEMBER_OF`, đừng dùng `--` không chỉ định type khi nghiệp vụ chỉ tính tình bạn.
- Không dùng `allShortestPaths` vô hạn trên cặp hub nếu endpoint chỉ cần **một** đường đi ngắn nhất.

### 14.3. Đọc kế hoạch thực thi

~~~cypher
EXPLAIN
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId, mutualCount
ORDER BY mutualCount DESC, candidateId
LIMIT 20;
~~~

`EXPLAIN` chỉ xây kế hoạch; `PROFILE` sẽ **thực thi** query và cho thấy các chỉ số như `Rows`, `DB Hits` và operator sử dụng. Với truy vấn chỉ đọc trên môi trường test, bạn có thể dùng `PROFILE`:

~~~cypher
PROFILE
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId, mutualCount
ORDER BY mutualCount DESC, candidateId
LIMIT 20;
~~~

Quan sát:

| Vị trí kế hoạch | Câu hỏi |
|---|---|
| Tìm `me` | Có dùng index từ `userId` hay quét label? |
| `Expand` ở bước thứ nhất | Người dùng này có bao nhiêu hàng xóm? |
| `Expand` ở bước thứ hai | Số hàng trung gian có tăng đột biến? |
| `AntiSemiApply`/kiểm tra `NOT EXISTS` | Chi phí loại người đã kết bạn và người bị chặn? |
| `Aggregation`/`Distinct` | Có nhiều hàng trùng cần gom không? |
| `Sort`/`Top` | Query có phải sắp rất nhiều ứng viên trước `LIMIT`? |

Tên operator có thể khác giữa các bản Neo4j và planner. **Không đặt điều kiện test rằng một tên operator cụ thể bắt buộc phải xuất hiện** trên mọi phiên bản; quan trọng hơn là kết quả, độ chọn lọc, lượng hàng trung gian và chi phí thực.

### 14.4. Khi nào nên tính trước kết quả?

Nếu người dùng mở trang gợi ý hàng nghìn lần/giây, có thể cân nhắc:

- Chạy job định kỳ sinh top gợi ý theo người dùng và lưu vào cache.
- Làm mới gợi ý khi quan hệ bạn bè hoặc trạng thái chặn thay đổi.
- Chỉ tính online trong phạm vi tập ứng viên hẹp; để mô hình GDS/ML xử lý xếp hạng nặng offline.
- Thiết kế thời hạn hiệu lực cache và cách xóa dữ liệu khi người dùng thu hồi quyền hiển thị.

Không được dùng **gợi ý cache cũ** để lách chính sách block/private: lúc trả API vẫn phải kiểm tra những quy tắc bảo mật đang có hiệu lực.

## 15. Quyền riêng tư và tính an toàn của quan hệ

Mạng xã hội chứa thông tin nhạy cảm về **ai quen ai**, không chỉ thông tin profile. Ngay cả khi không trả email hay tên thật, việc trả toàn bộ danh sách bạn chung hoặc các node trung gian trên một đường đi vẫn có thể tiết lộ quan hệ mà người dùng muốn giữ kín.

### 15.1. Phân biệt ba lớp kiểm soát

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| **Database RBAC** | Tài khoản dịch vụ chỉ đọc label/property cần thiết | Chặn quyền quá rộng ở tầng Neo4j theo khả năng edition |
| **Business authorization** | A được xem danh sách bạn của B hay không? | Quy tắc theo viewer, quyền riêng tư và trạng thái quan hệ |
| **API data minimization** | Trả `candidateId, displayName, mutualCount` thay vì toàn node | Giới hạn dữ liệu ra client |

Neo4j không tự hiểu “viewer hiện tại” theo phiên HTTP của mạng xã hội. Tài khoản DB có quyền đọc graph **không có nghĩa mọi người dùng ứng dụng được xem toàn bộ graph**. Tầng ứng dụng phải thực thi chính sách hiển thị theo danh tính viewer, kết hợp phân quyền DB và test riêng tư.

### 15.2. Đường đi có thể rò quan hệ ẩn

Giả sử A được phép biết “cách B ba bước”, nhưng không được phép xem rằng B kết nối với một người cụ thể. Trả `nodes(path)` nguyên vẹn có thể làm lộ node trung gian đó.

Vì vậy, API nên xác định rõ:

- Được trả **chỉ số hop** hay được trả **danh sách trung gian**?
- Có được duyệt các cạnh/nhân vật bị đặt chế độ private không?
- Có loại tài khoản bị chặn/ẩn **trong lúc duyệt đường đi** không, hay mới lọc sau khi tìm xong?
- Số bạn chung có được công bố khi một phần bạn chung thuộc quan hệ riêng tư không?

**Chỉ lọc node đích sau khi tính đường đi có thể không đủ**: nếu đường đi được tìm qua các cạnh mà viewer không có quyền biết, kết quả khoảng cách hoặc số bạn chung vẫn có thể tiết lộ thông tin gián tiếp.

### 15.3. Những kiểm soát thực tế nên có

- Kiểm tra authorization trên **mỗi endpoint**, không chỉ trên giao diện người dùng.
- Chỉ chạy Cypher với **tham số**, validate ID và giới hạn kích thước kết quả.
- Thiết kế chính sách block, private, disabled và lời mời đang chờ **nhất quán** với cache và các job nền.
- Áp dụng rate limit để tránh việc một client thu thập hàng loạt đồ thị bạn bè qua API.
- Không ghi tên thật, email, danh sách bạn chung hoặc toàn query parameters nhạy cảm vào log không được bảo vệ.
- Kiểm tra quyền đọc/ghi thực tế của Java Driver/SDN runtime identity; không sử dụng tài khoản admin.

## 16. Kiểm thử tích hợp và kết quả mong đợi

Với dữ liệu mẫu ở mục 5, có thể lập các assertion độc lập với implementation:

| Chức năng | Đầu vào | Kỳ vọng |
|---|---|---|
| Lấy bạn trực tiếp | A | B, C |
| Lấy số bạn | C | 4 |
| Kiểm tra đã kết bạn | A, B | `true` |
| Kiểm tra chưa kết bạn | A, D | `false` |
| Bạn chung | A, D | B, C |
| Số bạn chung | A, E | 1 (C) |
| Gợi ý hai bước | A | D (2), E (1) |
| Khoảng cách | A, D | 2 |
| Khoảng cách | A, G | 4 |
| Đường ngắn nhất A–D | A, D | Một trong A–B–D hoặc A–C–D |
| Khoảng cách chính mình | A, A | 0 theo đặc tả toán học |
| Người không tồn tại | A, Z | Phản hồi “not found” do ứng dụng định nghĩa |

### 16.1. Các ca dữ liệu bất thường phải thử

1. **Người dùng không tồn tại:** phân biệt ID thiếu với kết quả quan hệ rỗng.
2. **Người dùng không có bạn:** trả danh sách rỗng và độ dài khoảng cách theo chính sách rõ ràng.
3. **Hai người ở hai thành phần không liên thông:** không có path, nhưng không được báo khoảng cách 0.
4. **Hai người đã kết bạn:** không được xuất hiện trong danh sách đề xuất.
5. **Ứng viên bị chặn:** không xuất hiện khi viewer chặn hoặc bị ứng viên chặn.
6. **Nhiều đường ngắn nhất:** assert `length` và tính hợp lệ của các cạnh, không assert thứ tự chọn path tùy planner.
7. **Relationship trùng:** kiểm tra dữ liệu cũ có cạnh song song làm nhân hàng/sai count hay không.
8. **Self-loop:** không được tự kết bạn; test validation trước khi ghi.
9. **Tài khoản inactive/private:** lọc đúng trong gợi ý và khi xem quan hệ, theo chính sách sản phẩm.
10. **Nhiều yêu cầu kết bạn đồng thời:** constraint/transaction phải giữ đúng một quan hệ theo cặp.

### 16.2. Kiểm thử bằng Neo4j thật

Với Java Driver, JUnit 5 hoặc Spring Data Neo4j `@DataNeo4jTest`, nên chạy test trên **Neo4j Testcontainers hoặc database test cô lập**, không chỉ mock repository. Lý do:

- Neo4j mới thực hiện `MATCH`, `EXISTS`, `shortestPath` và uniqueness constraint.
- Mapper Java/SDN có thể khác kỳ vọng dù câu Cypher viết tay đúng.
- Kiểm thử transaction và race condition cần môi trường DB thật.
- Dữ liệu fixture có thể được xác minh từ một truy vấn Cypher **độc lập** với repository đang kiểm thử.

Ví dụ JUnit ở mức ý tưởng với AssertJ:

~~~java
@Test
void suggestsTwoHopFriendsInExpectedOrder() {
    // Chuẩn bị: Neo4j test DB đã được seed đúng 7 node / 9 cạnh.
    var actual = queries.suggestFriends("A", 10);

    assertThat(actual)
            .extracting(SocialGraphQueries.Suggestion::userId)
            .containsExactly("D", "E");

    assertThat(actual)
            .extracting(SocialGraphQueries.Suggestion::mutualCount)
            .containsExactly(2L, 1L);
}
~~~

Đây là **phương thức test bổ sung**, cần đặt trong lớp JUnit có `queries`, dependency AssertJ và quá trình setup dữ liệu riêng. Test không tự khởi tạo Neo4j; nhiệm vụ tích hợp là bảo đảm fixture được tạo/rollback/cleanup theo đúng vòng đời.

### 16.3. Kiểm tra không tăng cạnh khi lặp request

~~~cypher
MATCH (a:SocialUser {userId: 'A'})-[r:FRIEND]-
      (b:SocialUser {userId: 'B'})
RETURN count(r) AS edgesBetweenAAndB;
// Kỳ vọng: 1 nếu lưu một cạnh cho một cặp.
~~~

Thực hiện lại thao tác ghi cùng một cặp theo quy trình nghiệp vụ, rồi chạy query trên. Kết quả vẫn phải là **1**. Nếu hai cạnh được tạo bởi hai transaction đồng thời, cần xác minh constraint `pairKey`, luồng chuẩn hóa hướng và cách xử lý lỗi cạnh tranh.

## 17. Quy trình đưa vào production

### Bước 1 — Chốt hợp đồng nghiệp vụ

Xác định `FRIEND` là quan hệ đã chấp nhận, `FOLLOWS` có hướng, điều kiện block/private, và liệu hệ thống có cho phép nhiều quan hệ cùng cặp ở những loại edge khác không.

### Bước 2 — Thiết kế khóa và migration

Lập unique constraint cho `userId`; nếu dùng một cạnh cho cặp bạn bè, chuẩn hóa `pairKey`. Kiểm tra data cũ trùng node/relationship **trước** khi bật constraint mới. Không tự xóa node trùng nếu chúng còn mang relationship nghiệp vụ cần xử lý.

### Bước 3 — Kiểm thử truy vấn trên dữ liệu nhỏ

Chạy những truy vấn trong bài, assert kết quả mẫu rõ ràng: A có B/C, A–D có B/C là bạn chung, A–G cách bốn bước. Kiểm tra cùng ID, không có bạn, không liên thông và blocked.

### Bước 4 — Test với phân bố bậc thực tế

Tạo dataset đại diện về số node, số cạnh và các **hub có độ kết nối cao**. Đo p50/p95/p99 của API, số hàng trung gian, `DB Hits`, CPU, connection pool và sức chứa. Không suy hiệu năng production từ graph 7 node.

### Bước 5 — Thiết kế riêng tư và giới hạn API

Chạy positive/negative authorization tests bằng danh tính thực của ứng dụng, kiểm tra kết quả không rò người/cạnh private và số bạn chung bị che theo chính sách. Chỉ trả DTO cần thiết, có rate limit và cơ chế vô hiệu cache.

### Bước 6 — Quan sát và tối ưu liên tục

Giám sát tần suất truy vấn hai bước, số candidate, latency p95/p99, lỗi Java Driver/Neo4j, query plan thay đổi và trường hợp dữ liệu trùng. Với gợi ý chạy nặng, cân nhắc batch/cache hoặc pipeline GDS đã kiểm chứng.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều đúng hơn | Cách tránh |
|---|---|---|
| `FRIEND` lưu theo một hướng nghĩa là tình bạn chỉ một chiều | Hướng vật lý khác ngữ nghĩa hai chiều | Dùng `-[:FRIEND]-` khi đọc và một cạnh chuẩn hóa |
| `FOLLOWS` là đồng nghĩa của `FRIEND` | Theo dõi có hướng, có thể không được đáp lại | Định nghĩa type theo sản phẩm |
| Đếm `count(*)` luôn bằng số bạn chung | Cạnh song song hoặc nhiều path có thể nhân hàng | `count(DISTINCT bridge)` và kiểm tra dữ liệu trùng |
| Bạn của bạn luôn là gợi ý mới | Có thể là chính mình hoặc bạn hiện có | Loại `candidate = me` và dùng `NOT EXISTS` |
| `LIMIT 20` bảo đảm chỉ duyệt 20 hàng | Limit thường ở cuối query | Phân tích `PROFILE`, hạn chế fan-out |
| Khoảng cách 2 nghĩa là tin tưởng nhau | Chỉ là hai cạnh trong graph | Không suy luận phẩm chất/tin cậy cá nhân |
| `shortestPath` luôn chọn cùng một chuỗi ID | Có thể có nhiều đường ngắn nhất | Test khoảng cách và tính hợp lệ của path |
| Không tìm thấy path ≤ 6 nghĩa là hai người không liên thông | Có thể tồn tại đường dài hơn 6 | Phân biệt “vượt giới hạn” với “không liên thông” |
| `MERGE` tự chống mọi cạnh trùng do concurrency | Phụ thuộc constraint, khóa và quy ước ghi | Canonical pair key + unique constraint |
| `@Id` trong SDN là constraint ở DB | Chỉ là metadata mapping Java | Tạo/kiểm tra constraint bằng Cypher |
| Chỉ lọc blocked candidate là đã bảo vệ riêng tư | Node/cạnh trung gian hoặc cache cũng có thể lộ thông tin | Authorization trên đường duyệt và API |
| Mock repository là đủ để test graph path | Mock không chạy Cypher hay kiểm tra schema | Integration test với Neo4j thật |

## 19. Bài tập thực hành

### Bài 1 — Tính bạn chung

Với graph 7 người của bài, hãy tìm bạn chung của `B` và `C`. Dự đoán kết quả trước khi chạy query.

**Gợi ý đáp án:** `N(B) = {A,C,D}`, `N(C) = {A,B,D,E}`, nên bạn chung là `{A,D}`, số lượng **2**. Cypher tương tự mục 7, thay `userA='B'` và `userB='C'`.

### Bài 2 — Gợi ý bạn cho G

G chỉ là bạn với F. Những tài khoản nào cách G **đúng hai bước** qua `FRIEND` mà chưa là bạn trực tiếp?

**Gợi ý đáp án:** D và E (qua F), mỗi người có **1 bạn chung** với G. A/B/C ở xa hơn hai bước nên không xuất hiện trong gợi ý hai bước từ G với dữ liệu mẫu.

### Bài 3 — Đường đi ngắn nhất

Tính khoảng cách `A → F` và `A → G`. Có nên assert một đường đi A–F cụ thể không?

**Gợi ý đáp án:** `A–F = 3`, `A–G = 4`. A–F có thể đi qua B–D hoặc C–D/C–E; bài test nên kiểm tra độ dài và quan hệ giữa các node, không cứng hóa một đường duy nhất.

### Bài 4 — Sửa truy vấn gợi ý thiếu điều kiện

~~~cypher
MATCH (me:SocialUser {userId: 'A'})-[:FRIEND]-
      (f)-[:FRIEND]-(candidate)
RETURN candidate.userId;
~~~

Query trên có vấn đề gì?

**Gợi ý đáp án:** Nó có thể trả người đã là bạn (đi A–B–C), trả trùng candidate theo nhiều path và không tuân thủ block/private. Nên có điều kiện phòng thủ loại `candidate = me`; riêng vòng `A–B–A` qua một cạnh duy nhất không xuất hiện trong `MATCH` này do quy tắc không tái sử dụng cùng relationship trong một path. Cần loại bạn trực tiếp bằng `NOT EXISTS`, gom theo `candidate` và `count(DISTINCT f)`, sắp xếp/limit, thêm chính sách visibility.

### Bài 5 — Đếm FOLLOWS khác FRIEND

Một người A theo dõi B, nhưng B không theo dõi lại. Bạn cần xác định A đang theo dõi ai và những người theo dõi A; có nên dùng `-[:FOLLOWS]-` cho cả hai truy vấn?

**Gợi ý đáp án:** Không. Dùng `(A)-[:FOLLOWS]->(following)` cho danh sách A theo dõi và `(follower)-[:FOLLOWS]->(A)` cho người theo dõi A. Mẫu vô hướng sẽ trộn hai vai trò.

### Bài 6 — Đường đi và quyền riêng tư

Một người dùng có quyền xem **khoảng cách quan hệ** nhưng không được xem **danh sách bạn của tài khoản riêng tư**. API trả `pathUserIds` gồm tất cả người trung gian. Rủi ro nào có thể xảy ra?

**Gợi ý đáp án:** Path có thể tiết lộ quan hệ private hoặc tình trạng chặn. Cần kiểm tra chính sách trên cạnh/node trong lúc duyệt, chỉ trả hop count khi phù hợp, và test dữ liệu private/block theo danh tính viewer.

### Bài 7 — Mở rộng trên hub

Một tài khoản có 50.000 bạn, mỗi bạn có 20.000 bạn. Truy vấn hai bước có thể phát sinh bao nhiêu lượt mở rộng trước khi loại trùng? Nên tối ưu bằng gì?

**Gợi ý đáp án:** Ước lượng thô có thể lên đến `50.000 × 20.000 = 1.000.000.000` lượt mở rộng (không đồng nghĩa một tỷ candidate duy nhất). Cần xem `PROFILE` và dữ liệu thực, lọc đúng type, giới hạn tập hàng xóm theo nghiệp vụ, cân nhắc precompute/cache, dùng pipeline phù hợp và không coi `LIMIT` ở cuối là biện pháp đủ.

## 20. Tài liệu tham khảo

- [Neo4j Cypher — Patterns và relationship direction](https://neo4j.com/docs/cypher-manual/current/patterns/)
- [Neo4j Cypher — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/)
- [Neo4j Cypher — Shortest paths](https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/)
- [Neo4j Cypher — Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/)
- [Neo4j Cypher — Indexes and constraints](https://neo4j.com/docs/cypher-manual/current/schema/)
- [Neo4j Cypher — Query tuning with EXPLAIN/PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Graph Data Science — Algorithms](https://neo4j.com/docs/graph-data-science/current/algorithms/)

Các liên kết `current` có thể thay đổi theo release. Với Neo4j 5, Cypher 25 hoặc GDS trên một gói managed cụ thể, hãy đối chiếu cú pháp, edition, quyền và thuật toán được hỗ trợ trước khi áp dụng vào production.

## 21. Ghi nhớ

- **`SocialUser` là node, `FRIEND`/`FOLLOWS` là relationship**; chọn đúng hướng và ngữ nghĩa quan hệ trước khi viết Cypher.
- **Một cạnh `FRIEND` cho mỗi cặp** là mô hình đơn giản cho tình bạn hai chiều; cần quy ước canonical pair và constraint để tránh trùng.
- **Bạn chung là giao của hai tập hàng xóm**; dùng hai bước `FRIEND` và `DISTINCT` khi cần tránh nhân số hàng.
- **Gợi ý qua hai bước** phải loại chính mình, bạn đã có và đối tượng bị chặn; số bạn chung là tín hiệu xếp hạng dễ giải thích, không phải thước đo duy nhất.
- **Khoảng cách quan hệ là số hop ngắn nhất** trong phạm vi được phép duyệt; không đồng nghĩa mức thân thiết và không mặc nhiên cho phép lộ các node trung gian.
- **Hiệu năng phụ thuộc bậc node, giới hạn traversal và kế hoạch thực thi**; `LIMIT` không thay việc tối ưu query.
- **Java Driver/SDN, constraint, kiểm thử tích hợp và chính sách riêng tư** là phần bắt buộc để đưa truy vấn graph từ demo vào ứng dụng thực tế.
