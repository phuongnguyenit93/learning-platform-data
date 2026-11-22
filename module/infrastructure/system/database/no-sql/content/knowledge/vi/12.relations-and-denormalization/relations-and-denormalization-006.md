# Chỉ mục đảo hoặc bảng tra cứu phụ cho quan hệ hai chiều

## 1. Bài toán: lưu quan hệ theo một chiều nhưng phải truy vấn từ cả hai phía

Một ứng dụng học tập có chức năng **theo dõi giảng viên**. Khi người học An theo dõi giảng viên Bình, hệ thống cần trả lời ít nhất hai câu hỏi:

1. **An đang theo dõi những giảng viên nào?**
2. **Những người học nào đang theo dõi Bình?**

Hai câu hỏi dùng cùng một quan hệ nghiệp vụ, nhưng **điểm bắt đầu truy vấn khác nhau**. Nếu chỉ lưu danh sách người được theo dõi theo khóa người theo dõi, câu hỏi thứ hai có thể phải duyệt rất nhiều bản ghi.

Giả sử dữ liệu:

~~~text
An  --FOLLOWS--> Bình
An  --FOLLOWS--> Chi
Dung --FOLLOWS--> Bình
~~~

Mô hình lưu đơn giản:

~~~text
following[An]   = [Bình, Chi]
following[Dung] = [Bình]
~~~

Tìm “An theo dõi ai?” là đọc một danh sách. Nhưng tìm “Ai theo dõi Bình?” thì phải xem lần lượt danh sách của An, Dung và tất cả người khác nếu không có cấu trúc tra cứu bổ sung.

Ta có thể chuẩn bị thêm ánh xạ:

~~~text
followers[Bình] = [An, Dung]
followers[Chi]  = [An]
~~~

Đó là ý tưởng của **chỉ mục đảo theo quan hệ (reverse relationship index)** hoặc **bảng tra cứu phụ (reverse lookup table)**: lưu hoặc duy trì đường truy cập từ phía còn lại để không phải quét toàn bộ dữ liệu.

Trong NoSQL, cách thiết kế này thường được dùng cho:

- Người theo dõi và người được theo dõi.
- Người học và khóa học.
- Khách hàng và đơn hàng.
- Sản phẩm và danh mục/tag.
- Thành viên và nhóm.
- Bài viết và các lượt thích.
- Chủ xe và xe; xe và các booking liên quan.

**Mục tiêu bài học:** Biết cách thiết kế hai hướng đọc cho một quan hệ; phân biệt một chỉ mục bổ sung với việc nhân đôi bản ghi; mô tả cách duy trì dữ liệu khi tạo, sửa và xóa quan hệ; hiểu phạm vi bảo đảm và các đánh đổi về mạng, độ trễ, write amplification, hotspot và phân trang.

## 2. Quan hệ hai chiều trong truy vấn không nhất thiết là quan hệ đối xứng

### 2.1. Một cạnh có hướng nhưng được hỏi từ hai đầu

Ký hiệu quan hệ theo dõi:

\[
R \subseteq U \times U
\]

Trong đó \(U\) là tập người dùng; \((a,b)\in R\) có nghĩa **a theo dõi b**. Ta có:

\[
F(a)=\{b\mid(a,b)\in R\}
\]

là tập những người **a đang theo dõi**; còn:

\[
B(b)=\{a\mid(a,b)\in R\}
\]

là tập những người **theo dõi b**.

F là đường tra theo **nguồn** (forward lookup); B là đường tra theo **đích** (reverse lookup).

Một quan hệ có hướng **An → Bình** xuất hiện trong cả hai kết quả:

~~~text
F(An)   chứa Bình.
B(Bình) chứa An.
~~~

Nhưng điều đó **không có nghĩa Bình → An tồn tại**. Hai chiều truy vấn chỉ là hai góc nhìn trên **cùng một cạnh nghiệp vụ**.

### 2.2. Phân biệt ba trường hợp

| Trường hợp | Dữ liệu biểu diễn | Ý nghĩa |
|---|---|---|
| Một cạnh có hướng | An → Bình | An theo dõi Bình |
| Cạnh ngược chiều cũng tồn tại | An → Bình và Bình → An | Hai người theo dõi lẫn nhau |
| Cấu trúc tra cứu đảo | following[An] có Bình và followers[Bình] có An | Hai đường truy vấn cho **một cạnh An → Bình** |

Một lỗi thường gặp là tạo cạnh Bình → An chỉ vì muốn tìm người theo dõi Bình. Cạnh ngược chiều sẽ làm sai nghĩa nghiệp vụ: nó tuyên bố **Bình theo dõi An**, không phải “An là một follower của Bình”.

### 2.3. Sơ đồ hai hướng đọc

~~~mermaid
flowchart LR
    An["An"]
    Binh["Bình"]
    Chi["Chi"]
    Dung["Dung"]
    An -->|FOLLOWS| Binh
    An -->|FOLLOWS| Chi
    Dung -->|FOLLOWS| Binh
~~~

Từ đồ thị trên:

- Đọc các cạnh đi ra khỏi An → Bình, Chi.
- Đọc các cạnh đi vào Bình → An, Dung.
- Đọc những người theo dõi lẫn nhau cần kiểm tra **cả hai cạnh đối hướng**, không chỉ tìm một chiều.

## 3. “Chỉ mục đảo” ở đây khác gì inverted index của tìm kiếm văn bản?

Thuật ngữ **chỉ mục đảo** dễ gây nhầm với **inverted index** của công cụ tìm kiếm toàn văn.

Trong full-text search:

~~~text
token "NoSQL"    -> [Tài liệu D1, D4, D9]
token "Database" -> [Tài liệu D1, D2]
~~~

Đây là phép ánh xạ từ **từ/token sang các tài liệu chứa token**.

Trong quan hệ nghiệp vụ:

~~~text
following[An]   -> [Bình, Chi]
followers[Bình] -> [An, Dung]
~~~

Đây là phép ánh xạ từ **một đầu của quan hệ sang những đầu còn lại**.

Hai cách làm có nguyên tắc chung: **chuyển việc tìm kiếm trên tập lớn thành phép tra cứu bằng khóa đã lập chỉ mục**. Nhưng cấu trúc, tính duy nhất, cập nhật, cách tính thứ tự và giới hạn dữ liệu khác nhau.

Trong bài này, khi nói **reverse index**, ta chủ yếu nói về **chỉ mục truy cập quan hệ theo chiều ngược**, không phải bộ máy phân tích từ khóa với tokenizer, BM25 hay relevance score.

## 4. Nếu không có đường tra cứu phụ thì vấn đề gì xảy ra?

### 4.1. Mô hình chỉ lưu theo nguồn

Một bảng key–value đơn giản:

~~~text
Key                 Value
------------------------------------
following:An        [Bình, Chi]
following:Dung      [Bình]
following:Hoa       [Chi, Dung]
~~~

Đường đọc theo nguồn là:

~~~text
GET following:An -> [Bình, Chi]
~~~

Nhưng đường đọc theo đích là:

~~~text
Ai theo dõi Bình?
  Với mỗi người X:
    đọc following:X
    kiểm tra có Bình không
~~~

Đó là **quét theo ứng dụng**. Khi số người tăng lên hàng triệu, độ trễ và lưu lượng mạng có thể tăng mạnh, khó kiểm soát chi phí.

### 4.2. Một chỉ mục đảo thay đổi cách tìm

Chuẩn bị:

~~~text
Key                 Value
------------------------------------
followers:Bình      [An, Dung]
followers:Chi       [An, Hoa]
followers:Dung      [Hoa]
~~~

Lúc này:

~~~text
GET followers:Bình -> [An, Dung]
~~~

Không cần duyệt tất cả following:*.

### 4.3. Chi phí được chuyển từ đường đọc sang đường ghi

Khi An theo dõi Bình:

~~~text
Thay đổi chính:
  following[An] thêm Bình

Thay đổi đường đảo:
  followers[Bình] thêm An
~~~

Khi An bỏ theo dõi Bình:

~~~text
following[An] xóa Bình
followers[Bình] xóa An
~~~

Hai tập phải cùng phản ánh **một sự kiện nghiệp vụ**. Nếu chỉ cập nhật một tập, hai API sẽ trả lời mâu thuẫn.

**Đánh đổi chính:** Việc đọc theo chiều ngược trở nên hiệu quả hơn, nhưng ứng dụng có thêm chi phí cập nhật, đồng bộ, sửa sai và lưu trữ.

## 5. Ba cách thiết kế đường tra cứu ngược

Có ba kiểu triển khai phổ biến, không nên coi chúng hoàn toàn tương đương.

### 5.1. Cách A: Một bản ghi quan hệ, hai chỉ mục

Lưu mỗi quan hệ **một lần**:

~~~json
{
  "followerId": "An",
  "followedId": "Binh",
  "createdAt": "2026-11-14T09:00:00Z",
  "status": "ACTIVE"
}
~~~

Tạo chỉ mục:

~~~text
Index forward: (followerId, followedId)
Index reverse: (followedId, followerId)
~~~

Khi truy vấn theo followerId, dùng chỉ mục forward; khi truy vấn theo followedId, dùng chỉ mục reverse. **Bản ghi nghiệp vụ không nhất thiết bị nhân đôi**, nhưng dữ liệu cấu trúc index có bản sao các khóa để hỗ trợ hai hướng đọc.

Ưu điểm:

- Chỉ có một record quan hệ được sửa hoặc xóa.
- Index do cơ sở dữ liệu duy trì cùng với thao tác ghi theo bảo đảm sản phẩm.
- Dễ áp dụng unique constraint trên cặp nguồn–đích khi hỗ trợ.

Đánh đổi:

- Mỗi lần ghi còn phải bảo trì thêm chỉ mục.
- Chỉ mục tiêu tốn dung lượng và tài nguyên ghi.
- Một số NoSQL không hỗ trợ chỉ mục thứ cấp cần thiết hoặc chỉ hỗ trợ đọc eventual trên index.

### 5.2. Cách B: Một record chính và một chỉ mục thứ cấp được quản lý

Trong một cơ sở dữ liệu theo partition key/sort key, có thể lưu item theo hướng chính và tạo **secondary index** giúp truy vấn ngược.

~~~text
Primary key:        followerId + followedId
Secondary index:    followedId + followerId
~~~

Đây cũng thường là một item nghiệp vụ duy nhất. Nhưng chỉ mục thứ cấp có thể được cập nhật **bất đồng bộ**, tùy sản phẩm. Ví dụ DynamoDB GSI là eventually consistent.

Ưu điểm: Không cần tự viết hai thao tác Insert cho hai item. Đổi lại, phải chấp nhận **mức nhất quán, giới hạn và chi phí** của secondary index.

### 5.3. Cách C: Hai bản ghi hoặc hai bảng read model

Nếu hệ không hỗ trợ truy cập ngược hiệu quả bằng một chỉ mục, chủ động ghi hai bản chiếu:

~~~text
forward item:
  PK = FOLLOWING#An
  SK = USER#Binh

reverse item:
  PK = FOLLOWERS#Binh
  SK = USER#An
~~~

Cùng một quan hệ An → Bình được biểu diễn ở hai đường đọc.

Ưu điểm:

- Kiểm soát được khóa phân vùng và cách sắp xếp riêng từng hướng.
- Có thể phục vụ hai mẫu truy vấn rất khác nhau.
- Phù hợp với hệ được tối ưu cho truy vấn theo partition key.

Đánh đổi:

- Phải duy trì đồng bộ hai bản chiếu.
- Có thể tăng write amplification.
- Nếu hai thao tác ở hai partition/hệ độc lập, không mặc nhiên có transaction nguyên tử.

### 5.4. Khi nào mô hình đồ thị tự nhiên hơn?

Trong một **graph database** có hỗ trợ duyệt cạnh đi ra và cạnh đi vào, một cạnh có hướng An → Bình có thể được đọc từ hai nút mà không cần ứng dụng tự tạo bảng following/followers. Hệ đồ thị có cấu trúc nội bộ phù hợp để duyệt adjacency.

Tuy nhiên, **không vì thế mà truy vấn nhiều hop luôn rẻ**, nhất là khi có nút bậc rất cao hoặc số đường đi tăng nhanh. Cần đánh giá chỉ mục nút xuất phát, phạm vi duyệt, loại cạnh, số hop và cấu trúc dữ liệu thực tế.

## 6. Thiết kế dữ liệu và quy tắc nghiệp vụ cho quan hệ hai chiều

### 6.1. Định danh quan hệ

Một bản ghi FOLLOWS có thể dùng khóa:

\[
K = (\text{followerId},\ \text{followedId})
\]

Nếu mỗi người chỉ được theo dõi một đối tượng một lần ở cùng thời điểm, đây có thể là **khóa duy nhất theo nghiệp vụ**.

~~~text
(An, Bình) -> một quan hệ FOLLOWS hiện hành
(Bình, An) -> một quan hệ khác, không được gộp
~~~

Với ứng dụng nhiều tenant, phạm vi khóa có thể là:

\[
K = (\text{tenantId},\ \text{followerId},\ \text{followedId})
\]

Không nên dùng cặp ID mà bỏ tenantId nếu ID chỉ duy nhất bên trong từng tenant.

### 6.2. Quan hệ có thể có nhiều lần hợp lệ

Không phải mọi quan hệ đều có unique key theo cặp nguồn–đích.

Ví dụ:

~~~text
Learner L001 đăng ký Course C101 lần E1001.
Learner L001 đăng ký lại Course C101 lần E2026.
~~~

Nếu cần lưu hai lần học, khóa định danh phải có **enrollmentId** hoặc kỳ học/phần tử tương đương:

\[
K = (\text{learnerId},\ \text{courseId},\ \text{enrollmentId})
\]

Chỉ mục đảo theo courseId cũng phải phân biệt từng lần đăng ký nếu API cần “bao nhiêu lượt”, không chỉ “bao nhiêu người khác nhau”.

### 6.3. Thiết kế trường trong bản chiếu

Ví dụ một cạnh FOLLOWS:

~~~json
{
  "tenantId": "T1",
  "followerId": "An",
  "followedId": "Binh",
  "createdAt": "2026-11-14T09:00:00Z",
  "status": "ACTIVE",
  "relationVersion": 3
}
~~~

Đường đảo có thể chứa:

~~~json
{
  "tenantId": "T1",
  "followedId": "Binh",
  "followerId": "An",
  "createdAt": "2026-11-14T09:00:00Z",
  "status": "ACTIVE",
  "relationVersion": 3
}
~~~

Không nhất thiết sao chép toàn bộ hồ sơ của An và Bình vào cả hai nơi. Chỉ nên nhân những trường cần trả lời truy vấn hoặc hiển thị danh sách. Nếu người dùng đổi tên liên tục, việc nhân displayName vào hàng triệu follower records có thể gây write fan-out rất lớn.

### 6.4. Hợp đồng hai chiều

Nếu quan hệ là tập các cặp:

~~~text
R = { (An, Bình), (An, Chi), (Dung, Bình) }
~~~

thì hai cấu trúc cần phản ánh cùng R:

~~~text
Forward(An)    = {Bình, Chi}
Forward(Dung)  = {Bình}

Reverse(Bình)  = {An, Dung}
Reverse(Chi)   = {An}
~~~

Một invariant mong muốn:

\[
b\in F(a)\ \Leftrightarrow\ a\in B(b).
\]

Nếu hệ dùng cập nhật bất đồng bộ, invariant này có thể chỉ đúng **sau khi pipeline hội tụ**, không phải tại mọi thời điểm. Cần viết rõ phạm vi bảo đảm mong muốn.

## 7. MongoDB: một collection quan hệ và hai chỉ mục

### 7.1. Lưu cạnh một lần

Một collection **follows**:

~~~javascript
db.follows.insertOne({
  tenantId: "T1",
  followerId: "An",
  followedId: "Binh",
  createdAt: new Date("2026-11-14T09:00:00Z")
});
~~~

Đối với mô hình chỉ giữ **quan hệ hiện hành**, có thể tạo unique index trên cặp có hướng trong tenant:

~~~javascript
db.follows.createIndex(
  { tenantId: 1, followerId: 1, followedId: 1 },
  { unique: true }
);
~~~

Index này bảo vệ “một cặp An → Bình chỉ có một record” trong phạm vi các trường đã chọn. Nó **không cấm Bình → An**, vì đó là cặp có hướng khác.

### 7.2. Chỉ mục forward: người tôi theo dõi

~~~javascript
db.follows.createIndex({
  tenantId: 1,
  followerId: 1,
  createdAt: -1,
  _id: 1
});
~~~

Truy vấn:

~~~javascript
db.follows
  .find(
    { tenantId: "T1", followerId: "An" },
    { followedId: 1, createdAt: 1 }
  )
  .sort({ createdAt: -1, _id: 1 })
  .limit(20);
~~~

Index này hỗ trợ lọc theo tenantId + followerId và phục vụ thứ tự mới nhất trước cùng khóa phụ ổn định. Unique index trên cặp follower/followed vẫn cần để kiểm soát nghiệp vụ; một index phục vụ sort **không tự là unique**.

### 7.3. Chỉ mục reverse: ai theo dõi tôi?

~~~javascript
db.follows.createIndex({
  tenantId: 1,
  followedId: 1,
  createdAt: -1,
  _id: 1
});
~~~

Truy vấn:

~~~javascript
db.follows
  .find(
    { tenantId: "T1", followedId: "Binh" },
    { followerId: 1, createdAt: 1 }
  )
  .sort({ createdAt: -1, _id: 1 })
  .limit(20);
~~~

**Đặc điểm:** Bản ghi FOLLOWS chỉ có **một phiên bản trong collection**, còn hai index phục vụ hai hướng đọc. Khi record bị xóa, cơ sở dữ liệu cập nhật các index theo ngữ nghĩa ghi và mức bảo đảm của hệ thống; ứng dụng không phải tự xóa một “hàng reverse” riêng.

### 7.4. Kiểm tra hai người có theo dõi lẫn nhau không

Hai quan hệ ngược chiều phải **cùng tồn tại**:

~~~javascript
const anFollowsBinh = await db.follows.findOne({
  tenantId: "T1",
  followerId: "An",
  followedId: "Binh"
});

const binhFollowsAn = await db.follows.findOne({
  tenantId: "T1",
  followerId: "Binh",
  followedId: "An"
});

const mutual = Boolean(anFollowsBinh && binhFollowsAn);
~~~

Đây là minh họa logic truy vấn. Nếu cần câu trả lời là snapshot nguyên tử dưới những thay đổi đồng thời, hai lần đọc riêng không tự bảo đảm điều đó. Mức nhất quán đọc và transaction/snapshot tùy yêu cầu nghiệp vụ.

### 7.5. Lưu lịch sử thay vì chỉ quan hệ hiện hành

Nếu nghiệp vụ cần biết An đã theo dõi Bình **nhiều giai đoạn**, unique index trực tiếp trên cặp sẽ cấm nhiều record lịch sử cùng cặp.

Một thiết kế:

- Collection follows_current giữ tối đa một quan hệ đang hoạt động theo cặp.
- Collection follow_events lưu FOLLOWED/UNFOLLOWED với eventId và timestamp.

Hoặc có thể dùng các record lịch sử có validFrom/validTo và một **partial unique index** cho những record có status = ACTIVE, nếu sản phẩm hỗ trợ và schema được chọn phù hợp.

Không được kỳ vọng index duy nhất trên (tenantId, followerId, followedId) vừa cho phép lưu vô hạn các giai đoạn lịch sử vừa ngăn chỉ một giai đoạn ACTIVE mà không có điều kiện bổ sung.

## 8. DynamoDB: GSI để đi theo chiều ngược

### 8.1. Bảng với khóa chính theo follower

Giả sử bảng SocialRelations có các thuộc tính:

~~~text
PK            SK               GSI1PK          GSI1SK
-------------------------------------------------------------------
FOLLOWING#An  USER#Binh        FOLLOWERS#Binh  2026-11-14T09:00:00Z#An
FOLLOWING#An  USER#Chi         FOLLOWERS#Chi   2026-11-14T09:05:00Z#An
FOLLOWING#Dung USER#Binh       FOLLOWERS#Binh  2026-11-14T09:07:00Z#Dung
~~~

Các trường của item có thể gồm:

~~~json
{
  "PK": "FOLLOWING#An",
  "SK": "USER#Binh",
  "GSI1PK": "FOLLOWERS#Binh",
  "GSI1SK": "2026-11-14T09:00:00Z#An",
  "relationType": "FOLLOWS",
  "createdAt": "2026-11-14T09:00:00Z"
}
~~~

Trong một bảng nhiều tenant, khóa phải mã hóa cả tenantId hoặc sử dụng những thành phần khóa khác bảo đảm tách tenant. Ví dụ trên cố ý bỏ tenant để minh họa hình dạng truy vấn.

### 8.2. Query theo hướng forward

Ví dụ AWS SDK for JavaScript v3 với Document Client:

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  QueryCommand
} from "@aws-sdk/lib-dynamodb";

const docClient = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: "ap-southeast-1" })
);

const forward = await docClient.send(new QueryCommand({
  TableName: "SocialRelations",
  KeyConditionExpression: "PK = :pk AND begins_with(SK, :p)",
  ExpressionAttributeValues: {
    ":pk": "FOLLOWING#An",
    ":p": "USER#"
  },
  Limit: 20
}));
~~~

Truy vấn đọc từ bảng chính theo PK. Trong mẫu này, sort key USER#... giúp tra theo người được theo dõi, **không sắp theo thời gian tạo quan hệ**.

### 8.3. Query theo hướng reverse qua GSI

Tạo GSI1 có partition key **GSI1PK** và sort key **GSI1SK**. Truy vấn:

~~~javascript
const reverse = await docClient.send(new QueryCommand({
  TableName: "SocialRelations",
  IndexName: "GSI1",
  KeyConditionExpression: "GSI1PK = :pk",
  ExpressionAttributeValues: {
    ":pk": "FOLLOWERS#Binh"
  },
  ScanIndexForward: false,
  Limit: 20
}));
~~~

Nếu GSI1SK là chuỗi thời gian UTC theo định dạng cố định có thứ tự từ điển, thêm followerId làm thành phần phụ, kết quả có thể trả người theo dõi mới nhất trước theo trường được index.

**Phạm vi bảo đảm quan trọng:** **DynamoDB Global Secondary Index (GSI) được cập nhật bất đồng bộ và chỉ hỗ trợ eventually consistent read.** Không thể bật ConsistentRead: true trên GSI để biến nó thành đọc nhất quán mạnh.

Vì vậy sau khi An theo dõi Bình:

~~~text
PutItem vào bảng SocialRelations   -> thành công.
Query GSI1 theo FOLLOWERS#Binh      -> có thể chưa thấy An ngay.
~~~

Đây là độ trễ của **đường đọc đảo**, không nhất thiết là thất bại của thao tác tạo quan hệ ở bảng chính.

### 8.4. Lưu ý về GSI và quyền nghiệp vụ

Nếu FOLLOWS chỉ là danh sách hiển thị, độ trễ GSI vài khoảnh khắc có thể chấp nhận tùy sản phẩm. Nếu một quy tắc như “đã theo dõi thì được quyền vào nhóm kín” phải có hiệu lực ngay, không nên lấy kết quả GSI eventual làm bằng chứng duy nhất cho phép hoặc từ chối quyền.

Ứng dụng có thể xác minh một item chính theo full key với mức đọc phù hợp trong cùng Region trước khi quyết định. Những bảo đảm vẫn phụ thuộc topology, Region và loại API.

### 8.5. Kiểm soát tạo trùng trên item chính

Để cấm một cặp theo dõi trùng nhau trên bảng chính:

~~~javascript
import { PutCommand } from "@aws-sdk/lib-dynamodb";

await docClient.send(new PutCommand({
  TableName: "SocialRelations",
  Item: {
    PK: "FOLLOWING#An",
    SK: "USER#Binh",
    GSI1PK: "FOLLOWERS#Binh",
    GSI1SK: "2026-11-14T09:00:00Z#An",
    relationType: "FOLLOWS"
  },
  ConditionExpression: "attribute_not_exists(PK)"
}));
~~~

Điều kiện được đánh giá tại thao tác ghi trên item chính. Hai yêu cầu cùng tạo **cùng primary key** không thể đều được coi là tạo mới thành công trong phạm vi ghi có điều kiện được hỗ trợ.

Nhưng việc item xuất hiện trong GSI vẫn có thể trễ. **Unique pair** ở bảng chính và **read freshness** của index là hai vấn đề riêng.

## 9. DynamoDB: hai item vật lý để có hai đường đọc trực tiếp

### 9.1. Thiết kế không dùng GSI

Thay vì một item cùng GSI, ta có thể lưu hai item:

~~~text
Item 1:
  PK = FOLLOWING#An
  SK = USER#Binh
  relationId = An#Binh

Item 2:
  PK = FOLLOWERS#Binh
  SK = USER#An
  relationId = An#Binh
~~~

Hai thao tác Query đều đọc từ bảng chính với khóa phân vùng tương ứng. Trong những trường hợp DynamoDB hỗ trợ, thao tác đọc trên bảng có thể chọn strong consistency; đây là điểm khác với GSI eventual.

Nhược điểm là ứng dụng phải **duy trì hai item**. Nếu chỉ ghi Item 1, các API sẽ trả lời không thống nhất.

### 9.2. Dùng transaction khi cần hai item cùng thành công

Ví dụ minh họa:

~~~javascript
import { TransactWriteCommand } from "@aws-sdk/lib-dynamodb";

await docClient.send(new TransactWriteCommand({
  TransactItems: [
    {
      Put: {
        TableName: "SocialRelations",
        Item: {
          PK: "FOLLOWING#An",
          SK: "USER#Binh",
          relationId: "An#Binh",
          createdAt: "2026-11-14T09:00:00Z"
        },
        ConditionExpression: "attribute_not_exists(PK)"
      }
    },
    {
      Put: {
        TableName: "SocialRelations",
        Item: {
          PK: "FOLLOWERS#Binh",
          SK: "USER#An",
          relationId: "An#Binh",
          createdAt: "2026-11-14T09:00:00Z"
        },
        ConditionExpression: "attribute_not_exists(PK)"
      }
    }
  ]
}));
~~~

Trong phạm vi transaction mà DynamoDB hỗ trợ, hai item có thể được ghi theo tính chất nguyên tử: nếu một điều kiện tạo mới thất bại, transaction không chấp nhận chỉ một phần của nhóm thao tác.

**Giới hạn cần nhớ:**

- Transaction có giới hạn về số thao tác, kích thước và kiểu thao tác.
- Không tự tạo transaction xuyên nhiều dịch vụ độc lập hoặc mọi Region.
- Nếu client timeout sau khi transaction commit, lần retry phải xử lý trạng thái không rõ kết quả và tính idempotent.
- Nếu dữ liệu đã lệch từ trước (chỉ có một item), transaction Put cả hai với điều kiện “chưa tồn tại” có thể thất bại; cần quy trình repair riêng.

Không nên dùng transaction nhiều item cho mọi bản chiếu ở quy mô rất lớn nếu việc ghi bất đồng bộ đã đáp ứng yêu cầu độ mới và giảm chi phí đáng kể.

### 9.3. Chọn giữa GSI và hai item

| Tiêu chí | Một item + GSI | Hai item trong bảng |
|---|---|---|
| Lưu quan hệ chính | Một item | Hai bản chiếu |
| Ai duy trì đường đảo? | Dịch vụ DynamoDB cập nhật GSI | Ứng dụng hoặc transaction/projection worker |
| Mức nhất quán đọc đảo | Eventual trên GSI | Có thể chọn strong read trên bảng khi phù hợp |
| Chi phí write/storage | Có chi phí cập nhật và lưu GSI | Có chi phí thêm item và cập nhật |
| Hai hướng có sort key khác nhau | Dễ thiết kế riêng khóa GSI | Có thể thiết kế riêng SK của từng item |
| Logic xóa/repair | Xóa item chính; GSI hội tụ theo cơ chế dịch vụ | Phải bảo đảm xóa/sửa cả hai view |
| Phù hợp | Danh sách hiển thị chấp nhận trễ | Đường đọc cần trực tiếp và có cơ chế đồng bộ rõ |

Đây là ma trận lựa chọn, không phải kết luận GSI luôn chậm hoặc hai item luôn tốt hơn. Phải đo chi phí và chọn theo yêu cầu consistency, thứ tự kết quả và tải dữ liệu.

## 10. Cassandra/ScyllaDB: hai bảng theo hai truy vấn

### 10.1. Bảng theo người theo dõi

Ví dụ CQL:

~~~sql
CREATE TABLE following_by_user (
    tenant_id text,
    follower_id text,
    followed_id text,
    created_at timestamp,
    PRIMARY KEY (
        (tenant_id, follower_id),
        followed_id
    )
);
~~~

Truy vấn:

~~~sql
SELECT followed_id, created_at
FROM following_by_user
WHERE tenant_id = 'T1'
  AND follower_id = 'An';
~~~

Khóa phân vùng gồm tenant_id + follower_id; clustering column là followed_id. Một partition chứa danh sách người được theo dõi.

### 10.2. Bảng đảo theo người được theo dõi

~~~sql
CREATE TABLE followers_by_user (
    tenant_id text,
    followed_id text,
    follower_id text,
    created_at timestamp,
    PRIMARY KEY (
        (tenant_id, followed_id),
        follower_id
    )
);
~~~

Truy vấn:

~~~sql
SELECT follower_id, created_at
FROM followers_by_user
WHERE tenant_id = 'T1'
  AND followed_id = 'Binh';
~~~

Điểm chính: **đảo vị trí khóa phân vùng** để dữ liệu cùng câu hỏi “ai theo dõi Bình?” được nhóm vào partition phù hợp. Đây là lặp dữ liệu theo truy vấn.

### 10.3. Ghi hai bảng

~~~sql
INSERT INTO following_by_user (
    tenant_id, follower_id, followed_id, created_at
) VALUES ('T1', 'An', 'Binh', '2026-11-14T09:00:00Z');

INSERT INTO followers_by_user (
    tenant_id, followed_id, follower_id, created_at
) VALUES ('T1', 'Binh', 'An', '2026-11-14T09:00:00Z');
~~~

Hai lệnh INSERT độc lập có thể gặp lỗi giữa chừng. Cassandra có BATCH với ngữ nghĩa và giới hạn riêng, nhưng **BATCH không nên được hiểu như một transaction SQL đa hàng với isolation/rollback tổng quát**, nhất là khi dữ liệu nằm ở nhiều partition.

Nếu nguồn nghiệp vụ cần bảo đảm nghiêm ngặt, cần xác định cơ chế được hệ hỗ trợ hoặc thiết kế một nguồn quan hệ có thẩm quyền rồi đồng bộ bảng đảo với retry/repair. Không được suy từ việc cùng dùng CQL mà hai bảng luôn nhất quán tức thời.

### 10.4. Sort theo thời điểm cần clustering key khác

Hai bảng trên sắp theo ID người dùng, **không phải created_at**. Nếu API cần “20 follower mới nhất”, có thể thiết kế bảng chuyên biệt:

~~~sql
CREATE TABLE followers_recent_by_user (
    tenant_id text,
    followed_id text,
    created_at timestamp,
    follower_id text,
    PRIMARY KEY (
        (tenant_id, followed_id),
        created_at,
        follower_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    follower_id ASC
);
~~~

Lúc này cần quyết định:

- Khi bỏ theo dõi, ứng dụng có biết created_at để xóa đúng row không?
- Nếu theo dõi lại, đó là một khoảng quan hệ mới hay cùng quan hệ cũ?
- Nếu created_at trùng nhau, follower_id có đủ phân biệt từng quan hệ không?
- Nếu một người có nhiều lần theo dõi trong lịch sử, có cần relationId riêng không?

Nếu dùng (created_at, follower_id) làm clustering key, việc đổi created_at không phải một phép cập nhật cột thường: đó là **thay đổi định danh hàng**, thường cần xóa hàng cũ và tạo hàng mới.

### 10.5. Độ lớn partition và người nổi tiếng

Một người nổi tiếng có thể có hàng triệu follower. Nếu tất cả follower nằm trong cùng partition của bảng followers_by_user, phải đánh giá:

- Kích thước partition và số row.
- Tần suất ghi và fan-in.
- Độ trễ đọc/compaction/tombstone.
- Phân trang khi lượng dữ liệu rất lớn.

Có thể thêm bucket hoặc shard vào partition key nhưng khi đó truy vấn “mọi follower” phải **fan-out qua nhiều partition** rồi ghép kết quả. Chia tải ghi tốt hơn thường đổi lấy độ phức tạp đọc lớn hơn.

## 11. Redis: tập người theo dõi và tập người được theo dõi

### 11.1. Dùng SET để biểu diễn quan hệ duy nhất

Redis hỗ trợ kiểu **set** chứa phần tử duy nhất. Ta có thể tạo:

~~~redis
SADD following:An Binh
SADD followers:Binh An

SADD following:An Chi
SADD followers:Chi An

SADD following:Dung Binh
SADD followers:Binh Dung
~~~

Đọc hai hướng:

~~~redis
SMEMBERS following:An
SMEMBERS followers:Binh
~~~

Kiểm tra quan hệ:

~~~redis
SISMEMBER following:An Binh
~~~

Xóa quan hệ:

~~~redis
SREM following:An Binh
SREM followers:Binh An
~~~

Ưu điểm: SADD/SREM theo phần tử có tính lặp an toàn với tư cách **thêm hoặc xóa thành viên tập hợp**. Gửi lại SADD cùng member không tạo phần tử set thứ hai.

### 11.2. Hai lệnh không tự tạo một thao tác nguyên tử

Nếu ứng dụng chạy:

~~~text
SADD following:An Binh    -> thành công
Mất kết nối
SADD followers:Binh An    -> chưa chạy
~~~

thì dữ liệu lệch.

Redis có MULTI/EXEC, Lua hoặc Functions trong những phạm vi được hỗ trợ. Tuy nhiên cần phân biệt:

- Một lệnh SADD riêng nguyên tử tại Redis xử lý khóa.
- MULTI/EXEC thực thi nhóm lệnh theo ngữ nghĩa Redis, nhưng **không có rollback tổng quát khi lỗi thời gian chạy**.
- Trong Redis Cluster, thao tác đa khóa/script thường bị ràng buộc bởi **hash slot**. following:An và followers:Binh có thể ở các slot khác nhau nên không thể mặc định đặt chung trong một thao tác đa khóa.
- Replication/failover và persistence ảnh hưởng durability và khả năng các bản sao quan sát ghi.

Với yêu cầu chỉ là cache hoặc danh sách gần đúng, có thể chấp nhận **eventual repair**. Nếu quan hệ quyết định quyền hoặc giao dịch quan trọng, cần chọn nguồn lưu chính có ràng buộc/giao dịch phù hợp thay vì coi hai Redis set là sự thật duy nhất mà không có bảo đảm.

### 11.3. Set không lưu thứ tự thời gian

SMEMBERS không hứa trả theo thứ tự thêm. Nếu muốn follower mới nhất trước, có thể dùng **sorted set (ZSET)** với score biểu diễn thời điểm theo quy ước:

~~~redis
ZADD followersByTime:Binh 1794646800 An
ZREVRANGE followersByTime:Binh 0 19 WITHSCORES
~~~

Score ở đây chỉ là **mốc thời gian minh họa**. Hệ thực tế cần dùng timestamp được tính nhất quán theo nguồn sự kiện, xét độ chính xác, trùng thời điểm và ý nghĩa khi unfollow/refollow.

ZSET dùng member làm định danh duy nhất; nếu cần lưu nhiều **lần theo dõi lịch sử** của cùng An đối với Bình, chỉ dùng member = An sẽ không giữ được từng lần. Khi đó cần relationId hoặc một cấu trúc history riêng.

### 11.4. Tránh đọc toàn bộ tập cực lớn

SMEMBERS trả toàn bộ tập. Với hàng triệu follower, một response rất lớn có thể gây áp lực mạng và bộ nhớ. Redis có **SSCAN** để duyệt theo cursor, hoặc có thể dùng ZSET với truy vấn theo trang/cursor thích hợp. Dù vậy, scan nhiều lần không tự tạo snapshot cố định nếu tập hợp thay đổi.

Đối với dữ liệu follower cực lớn, nên đánh giá tính phù hợp của Redis làm nguồn chính, cache, hoặc một thành phần trong kiến trúc đa tầng.

## 12. Quan hệ nhiều–nhiều: người học và khóa học

### 12.1. Từ một quan hệ tới hai truy vấn

Cho:

~~~text
L001 --ENROLLED_IN--> C101
L001 --ENROLLED_IN--> C102
L002 --ENROLLED_IN--> C101
~~~

Hai câu hỏi:

- Người học L001 đang tham gia khóa nào?
- Khóa C101 có những người học nào?

Hai góc nhìn:

~~~text
courses_by_learner[L001] = [C101, C102]
learners_by_course[C101] = [L001, L002]
~~~

Đây là một quan hệ **N:M**, nhưng không bắt buộc dùng bảng nối SQL. Có thể dùng một collection cạnh với hai index, GSI, hoặc hai read table tùy công nghệ.

### 12.2. Quan hệ có thuộc tính

Một lần đăng ký có:

~~~json
{
  "enrollmentId": "E1001",
  "learnerId": "L001",
  "courseId": "C101",
  "enrolledAt": "2026-10-01T00:00:00Z",
  "status": "ACTIVE",
  "progressPercent": 65
}
~~~

Khi xây bảng đảo theo courseId, cần quyết định copy những field nào:

- **learnerId, enrollmentId:** Cần để định danh và liên kết.
- **enrolledAt:** Cần nếu phân trang theo thời điểm đăng ký.
- **status:** Cần nếu chỉ hiển thị người đang học; có thể bị trễ.
- **progressPercent:** Chỉ nên lặp nếu màn danh sách giảng viên thực sự cần, vì progress có thể đổi liên tục.

Không nên nhân toàn bộ hồ sơ người học và mọi bài làm vào mỗi read model nếu câu hỏi chỉ là “bao nhiêu người đã đăng ký”.

### 12.3. Đếm lượt khác đếm người

Nếu L001 đăng ký khóa C101 hai lần trong các kỳ khác nhau:

~~~text
E1001: L001 -> C101 (kỳ 1)
E2008: L001 -> C101 (kỳ 2)
~~~

thì:

- Số **lượt đăng ký** = 2.
- Số **người học khác nhau** = 1.

Nếu bảng reverse chỉ lưu learnerId một lần trong set, nó trả lời được “bao nhiêu người khác nhau”, nhưng **mất thông tin hai lượt đăng ký**. Nếu cần lịch sử nhiều lượt, khóa phải chứa enrollmentId hoặc một định danh tương đương.

Mỗi index phải phản ánh đúng **đơn vị quan hệ** mà truy vấn cần đếm.

## 13. Thao tác tạo và xóa quan hệ: ranh giới nhất quán

### 13.1. Quy trình đồng bộ mạnh trong một phạm vi transaction

Nếu hai bản ghi forward/reverse nằm trong cùng phạm vi transaction được hệ hỗ trợ, có thể thực hiện:

~~~text
BEGIN
  xác nhận quan hệ An -> Bình hợp lệ
  tạo forward(An, Bình) nếu chưa có
  tạo reverse(Bình, An) nếu chưa có
COMMIT
~~~

Điều kiện **nếu chưa có** phải được thực thi ở điểm ghi, không chỉ kiểm tra trước bên ngoài transaction. Nếu hai client cùng theo dõi Bình từ An, một phép GET rồi INSERT không điều kiện có thể dẫn đến trùng.

Ngay cả khi transaction của một Region thành công, không được mặc định hai item ở mọi Region/replica khác đều đã nhìn thấy ngay; phạm vi consistency phụ thuộc hệ cụ thể.

### 13.2. Quy trình cập nhật bất đồng bộ

Với quan hệ không yêu cầu cả hai hướng xuất hiện tức thời, có thể chọn một **nguồn có thẩm quyền**:

~~~mermaid
flowchart TD
    A["API: An theo dõi Bình"] --> B["Quan hệ FOLLOWS nguồn"]
    B --> C["Outbox / CDC"]
    C --> D["Event stream"]
    D --> E["Reverse projection worker"]
    E --> F["followers_by_user"]
    F --> G["API: người theo dõi Bình"]
~~~

Nguồn nhận yêu cầu theo quy tắc duy nhất/transaction của nó; worker xây bảng đảo từ event. Đường đảo có thể trễ một khoảng thời gian. Cần:

1. Phát sự kiện đáng tin cậy sau commit.
2. Chống xử lý event trùng.
3. Ngăn event cũ ghi đè event mới.
4. Xử lý delete/unfollow.
5. Có khả năng backfill/rebuild và đối soát.

### 13.3. Transactional outbox

Nếu cơ sở dữ liệu nguồn hỗ trợ transaction, có thể ghi quan hệ và outbox event trong cùng transaction:

~~~text
transaction:
    CREATE FOLLOWS(An, Bình) nếu chưa tồn tại
    INSERT OUTBOX(
        eventId = EVT-1001,
        relationId = REL-An-Binh,
        version = 1,
        type = FOLLOW_CREATED
    )
commit
~~~

Worker lấy event từ outbox rồi cập nhật bảng đảo.

Outbox giảm khoảng trống “quan hệ đã commit nhưng ứng dụng chết trước khi phát event”, nhưng không tự giải quyết mọi vấn đề: worker vẫn có thể nhận lại event, lag, thiếu quyền ghi hoặc gặp lỗi projection.

### 13.4. Sửa sai khi hai hướng bị lệch

Nếu nguồn R có:

~~~text
(An, Bình) ACTIVE
~~~

nhưng reverse index chưa có An trong followers[Bình], cần một quy trình sửa:

~~~text
Đọc quan hệ có thẩm quyền
Tính reverse entry kỳ vọng
So với dữ liệu reverse thực tế
Tạo entry thiếu hoặc xóa entry thừa
Ghi nhận nguyên nhân và phiên bản đã xử lý
~~~

Đối soát chỉ từ hai bản sao mà không xác định bên nào là nguồn có thể gây lỗi: nếu forward và reverse khác nhau, **không biết bản nào đúng**. Phải có nguồn có thẩm quyền hoặc quy tắc hòa giải rõ ràng.

## 14. Retry, idempotency và thứ tự sự kiện

### 14.1. Lệnh tạo quan hệ có thể bị gửi hai lần

Ví dụ:

~~~text
Client gửi FOLLOW An -> Bình.
Server đã tạo thành công, nhưng response bị mất.
Client retry.
~~~

Nếu dùng một khóa nghiệp vụ cố định (tenantId, followerId, followedId) và conditional insert, lần retry có thể nhận trạng thái “đã tồn tại”. Ứng dụng cần phân biệt **cùng ý định đã thực hiện** với **xung đột thực sự** và trả kết quả phù hợp.

Một eventId hoặc idempotencyKey ổn định giúp truy vết thao tác. Nhưng việc có một trường eventId trong JSON không tự chặn xử lý hai lần: phải kiểm soát ở **điểm áp dụng tác dụng phụ**.

### 14.2. Event đến sai thứ tự

Giả sử:

~~~text
v1: An FOLLOW Bình
v2: An UNFOLLOW Bình
v3: An FOLLOW Bình lại
~~~

Do retry hoặc worker song song, reverse projection nhận:

~~~text
v3 -> v1 -> v2
~~~

Nếu cập nhật vô điều kiện theo thứ tự nhận, kết quả cuối có thể là “An không còn theo dõi Bình”, trong khi nguồn đã ở v3.

Quy tắc bảo vệ:

~~~text
Chỉ áp dụng event cho relationId nếu:
    event.version > storedProjectionVersion
~~~

Với bản sao không giữ trạng thái khi xóa, cần lưu **tombstone phiên bản** hoặc một cơ chế đủ mạnh để không cho event cũ tạo lại quan hệ đã xóa.

### 14.3. Một relationId hay nhiều lần theo dõi?

Có hai cách hiểu:

**A. Quan hệ hiện hành:** Cặp An–Bình có một identity ổn định; follow/unfollow là các phiên bản trạng thái của cùng quan hệ.

**B. Lịch sử nhiều giai đoạn:** Mỗi lần theo dõi có một relationId hoặc interval riêng; current relationship được dẫn xuất từ các event.

Nếu vừa muốn “một cạnh ACTIVE” vừa giữ lịch sử, cần thiết kế khóa và quy tắc phiên bản phù hợp. Không được dùng cặp ID làm khóa duy nhất cho tất cả bản ghi lịch sử rồi thắc mắc vì sao không lưu được hai lần hợp lệ.

## 15. Phân trang và thứ tự kết quả ở hai hướng

### 15.1. Hai chiều có thể yêu cầu thứ tự khác nhau

Ứng dụng có thể muốn:

- **Following của An:** Sắp theo thời điểm An bắt đầu theo dõi mới nhất.
- **Followers của Bình:** Sắp theo thời điểm người khác theo dõi Bình mới nhất.
- **Thành viên nhóm:** Sắp theo tên hoặc vai trò.
- **Đơn theo khách:** Mới nhất trước.
- **Đơn theo cửa hàng:** Ưu tiên PENDING trước, rồi theo thời gian.

Không nhất thiết cùng một sort key phục vụ được mọi thứ tự. Bảng phụ hoặc secondary index phải được thiết kế theo **filter + order + limit** của từng API.

### 15.2. Cursor cần có thứ tự phụ ổn định

Nếu hai người theo dõi Bình ở cùng timestamp, cursor chỉ chứa createdAt có thể bỏ sót hoặc lặp bản ghi. Một khóa sắp xếp:

~~~text
(createdAt DESC, followerId ASC)
~~~

cho thứ tự ổn định hơn khi timestamp trùng. Với lịch sử nhiều lần follow từ cùng người, có thể cần thêm relationId.

Không nên dùng offset vô hạn cho danh sách hàng triệu follower nếu hệ dữ liệu không hỗ trợ hiệu quả. Tùy hệ, có thể dùng:

- Paging state/cursor của driver.
- Keyset pagination theo khóa đầy đủ.
- DynamoDB LastEvaluatedKey.
- Redis SSCAN hoặc các lệnh phân trang theo sorted set.

### 15.3. Một trang không luôn là snapshot cố định

Giữa trang 1 và trang 2 có thể có người theo dõi mới hoặc bỏ theo dõi. Nếu không có snapshot/điểm mốc phù hợp, một vài entry có thể dịch vị trí.

Nếu cần danh sách cố định “tại thời điểm T”, phải định nghĩa mốc thời gian, version hoặc cơ chế snapshot mà hệ hỗ trợ; cursor đơn thuần không đảm bảo điều đó.

## 16. Hot key, supernode và phân phối tải

### 16.1. Một đầu quan hệ có thể có bậc cực cao

Ví dụ Bình là giảng viên nổi tiếng với 2 triệu follower:

~~~text
followers[Bình] = [An, Dung, Hoa, ... 2.000.000 người]
~~~

Nếu tất cả entry nằm trong một partition hoặc một set rất lớn:

- Tải ghi tập trung khi có nhiều lượt follow/unfollow.
- Đọc cả danh sách có thể truyền lượng dữ liệu khổng lồ.
- Partition có thể trở nên quá lớn trong một số hệ wide-column.
- Xóa/đối soát một lượng lớn entry tốn tài nguyên.

Điều này thường gọi là **hot key/hot partition** hoặc **supernode** tùy mô hình.

### 16.2. Chia bucket hoặc shard cho chiều đảo

Một phương án:

~~~text
followers:Bình:shard-0
followers:Bình:shard-1
followers:Bình:shard-2
...
followers:Bình:shard-15
~~~

Mỗi follower được gán shard theo hash ổn định của followerId (hoặc relationId nếu cần lưu nhiều lần). Việc này có thể phân phối ghi thành nhiều partition nhưng làm đọc phức tạp:

~~~text
Đọc shard 0..15
Hợp nhất kết quả
Sắp theo thời gian/ID
Phân trang qua nhiều shard
~~~

**Đánh đổi:** Tăng khả năng phân phối tải ghi nhưng tăng fan-out đọc, số request và trạng thái cursor. Không nên sharding theo cảm tính nếu đường đọc “followers mới nhất” là chức năng quan trọng mà không có kế hoạch merge.

### 16.3. Quy mô và tỷ lệ quan hệ

Một đồ thị có 1 triệu người và trung bình 100 quan hệ theo dõi mỗi người có thể có khoảng 100 triệu cạnh có hướng. Nếu mỗi quan hệ được lưu hai item, số item read model tăng lên khoảng 200 triệu, chưa tính index và metadata.

\[
\text{Số bản chiếu} \approx
\text{Số quan hệ} \times \text{số hướng lưu riêng}
\]

Đây là ước lượng cấp mô hình, không phải dung lượng storage chính xác. Kích thước item, compression, replication, secondary index và tombstone còn có thể làm tổng chi phí khác đáng kể.

### 16.4. Đếm follower không nhất thiết phải đọc tất cả

Nếu API chỉ hiển thị “Bình có 2 triệu follower”, không nên mỗi lần gọi API lại tải toàn bộ set/bảng follower để đếm. Có thể sử dụng:

- Phép đếm được hệ hỗ trợ với chi phí phù hợp trong phạm vi dữ liệu.
- Bộ đếm/aggregate được duy trì có chủ đích.
- Số liệu gần đúng khi sản phẩm cho phép.

Nhưng **bộ đếm** cần chống retry đếm trùng và xử lý unfollow đúng. Số follower hiển thị có thể được phép trễ, trong khi quan hệ có hiệu lực tại nguồn cần đúng theo quy tắc.

## 17. Bảo mật và quyền truy cập trên đường đảo

### 17.1. Đảo chiều truy vấn có thể làm lộ dữ liệu

Trong một hệ nội bộ, truy vấn “Những nhân viên nào thuộc dự án P?” có thể chứa thông tin nhạy cảm. Nếu chỉ bảo vệ API “Dự án của tôi” mà quên API “Thành viên của dự án”, người dùng có thể liệt kê thành viên không được phép thấy.

**Cả hai chiều đọc** cần thực hiện authorization theo ngữ cảnh và đối tượng.

### 17.2. Phạm vi tenant

Nếu ID được tái sử dụng trong những tenant khác nhau:

~~~text
Tenant T1: user An
Tenant T2: user An
~~~

thì khóa followers:An toàn cục không phù hợp. Cần phân vùng định danh:

~~~text
followers:T1:An
followers:T2:An
~~~

Tương tự, MongoDB unique index cần chứa tenantId nếu quan hệ chỉ duy nhất trong tenant; DynamoDB PK/GSI và Cassandra partition key cũng phải thể hiện phạm vi đó.

### 17.3. Xóa tài khoản

Khi một user bị xóa, có thể cần xử lý:

- Các quan hệ user đó là follower (cạnh đi ra).
- Các quan hệ user đó được theo dõi (cạnh đi vào).
- Các read model theo hai hướng.
- Bộ đếm follower/following.
- Cache, search, notification và dữ liệu lịch sử.

Đường tra cứu đảo giúp tìm các quan hệ liên quan để xử lý, nhưng cũng phải có quy trình tránh sự kiện cũ **hồi sinh** cạnh đã xóa và tránh làm lộ danh tính người dùng không còn hợp lệ.

## 18. Sự cố và cách quan sát hệ thống

### 18.1. Một hướng có dữ liệu, hướng còn lại không có

Ví dụ:

~~~text
GET following[An]   -> có Bình
GET followers[Bình] -> không có An
~~~

Nguyên nhân có thể:

- Worker chưa nhận event.
- Ghi một bản chiếu thất bại.
- Event bị bỏ qua hoặc hết retention.
- Reverse index là eventually consistent và chưa hội tụ.
- Sai tenantId hoặc khóa định danh.
- Một luồng delete được xử lý sai thứ tự.

Không nên “sửa” bằng cách thêm ngược FOLLOWS Bình → An; đó là **thay đổi nghiệp vụ sai hướng**.

### 18.2. Chỉ số vận hành quan trọng

| Chỉ số | Phát hiện |
|---|---|
| Forward/reverse mismatch count | Hai hướng không cùng tập quan hệ |
| Projection lag | Bảng đảo chậm hơn nguồn |
| Event backlog | Consumer không xử lý kịp |
| Retry / DLQ count | Sự kiện chưa hoàn tất |
| Version gap | Bản đảo đại diện phiên bản cũ |
| Hot partition/key latency | Một đối tượng có quá nhiều follower |
| Read p95/p99 | Độ trễ của API theo hai hướng |
| Storage/index size | Chi phí tăng từ duplication |
| Repair success/failure | Khả năng đưa bản đảo về đúng nguồn |

### 18.3. Đối soát theo nguồn có thẩm quyền

Ví dụ giả mã:

~~~text
for each authoritative relation (a -> b):
    assert forward(a) contains b
    assert reverse(b) contains a

for each reverse entry (b <- a):
    verify authoritative relation (a -> b) exists

repair missing or stale entries with version protection
~~~

Khi quy mô rất lớn, có thể đối soát theo bucket, mốc version hoặc lấy mẫu; một lần quét toàn bộ 100 triệu quan hệ sẽ tốn tài nguyên. Cần định nghĩa **mức độ chính xác và thời gian hội tụ** mà hệ thống cam kết.

### 18.4. Tạo lại bảng đảo

Nếu bảng followers_by_user hỏng, có thể rebuild từ nguồn:

1. Ghi nhận mốc thay đổi của nguồn hoặc CDC.
2. Quét nguồn theo partition, tạo reverse entries.
3. Nhận các event diễn ra trong thời gian quét.
4. Hòa giải version/delete để event cũ không ghi đè mới.
5. Đối chiếu số lượng, khóa thiếu/thừa, độ trễ.
6. Chuyển đường đọc sang bản đảo mới.

Nếu chỉ quét nguồn rồi bắt đầu nghe event **sau khi quét xong**, thay đổi xảy ra ở khoảng trống có thể bị bỏ lỡ.

## 19. Chọn phương án nào cho từng tình huống?

| Tình huống | Gợi ý lựa chọn | Điều cần xác minh |
|---|---|---|
| Collection quan hệ trong MongoDB, chỉ cần hai hướng và sort rõ | Một record + hai compound index | Unique scope, thứ tự, chi phí index |
| DynamoDB, đọc ngược chấp nhận trễ | Một item + GSI | GSI eventual, index key và projection |
| DynamoDB, cần hai bảng đọc trực tiếp cùng transaction | Hai item + TransactWriteItems nếu trong phạm vi hỗ trợ | Giới hạn transaction, retry, đọc strong khi cần |
| Cassandra/ScyllaDB, hai query pattern theo partition khác nhau | Hai bảng theo hai khóa truy cập | Consistency, update/repair, hot partition |
| Redis làm cache followers/following | Hai SET/ZSET theo khóa | Atomicity đa khóa, Cluster slots, persistence, memory |
| Quan hệ đồ thị nhiều hop | Graph database hoặc mô hình truy vấn phù hợp | Độ phức tạp traversal, supernode, bậc nút |
| Quan hệ quyết định quyền hoặc tiền | Nguồn có thẩm quyền với ghi có điều kiện/transaction | Không dựa vào reverse index eventual để ra quyết định |

Một lựa chọn không loại trừ lựa chọn khác. Ví dụ nguồn MongoDB có unique pair, đồng thời hệ thống duy trì Redis SET làm cache danh sách follower hoặc một search index để tìm kiếm hồ sơ.

Trong trường hợp đó, cần biết **thành phần nào là nguồn thật, thành phần nào là bản sao, bản sao có thể cũ bao lâu và ai chịu trách nhiệm sửa sai**.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tạo cạnh Bình → An để phục vụ reverse query của An → Bình | Làm sai nghĩa FOLLOWS | Chỉ tạo index/lookup đảo, không tạo quan hệ nghiệp vụ ngược |
| Chỉ lưu forward nhưng cần đọc reverse thường xuyên | Quét toàn bảng hoặc N+1 | Thêm index hoặc bảng tra phụ |
| Ghi hai bảng độc lập và coi là transaction | Một hướng có, một hướng thiếu | Transaction đúng phạm vi hoặc event+repair |
| Đọc GSI DynamoDB như strong consistency | Không thấy quan hệ vừa tạo | Chấp nhận eventual hoặc xác minh bảng chính |
| Dùng Redis SADD hai khóa mà không xét Cluster | Cross-slot/atomicity không như kỳ vọng | Thiết kế topology và nguồn có thẩm quyền |
| Dùng set theo userId khi cần lịch sử nhiều lần | Mất enrollmentId/lượt theo dõi | Định danh từng lần và lưu history |
| Không có unique pair ở nguồn | Một cặp tạo nhiều record do retry | Unique index/conditional write theo phạm vi |
| Event cũ ghi đè event mới | Quan hệ vừa hủy bị hồi sinh | Version/CAS/tombstone |
| Chỉ kiểm tra source rồi ghi vô điều kiện | Race giữa nhiều client | Điều kiện tại điểm ghi |
| Lưu toàn bộ hồ sơ vào từng reverse entry | Write fan-out khi sửa profile | Chỉ lưu field cần thiết; batch lookup khi hợp lý |
| Đọc mọi follower trong một request | Payload lớn, quá tải | Phân trang/cursor, aggregate riêng |
| Một partition cho hàng triệu follower | Hot key/large partition | Cân nhắc shard/bucket và chi phí merge |
| Không có tenant trong khóa | Va chạm và rò dữ liệu | Khóa/index theo tenant, kiểm tra authorization |
| Đếm entry thay vì đếm người duy nhất | Sai khi có nhiều lượt quan hệ | Chọn đúng đơn vị và DISTINCT/ID |
| Không có rebuild | Bảng đảo lệch lâu dài | CDC/checkpoint/đối soát và backfill |

## 21. Bài tập thực hành

### Bài 1. Nhận diện chiều của quan hệ

Cho:

~~~text
An   FOLLOWS Bình
An   FOLLOWS Chi
Dung FOLLOWS Bình
Bình FOLLOWS An
~~~

Hãy:

1. Viết tập following và followers cho từng người.
2. Xác định những cặp thực sự theo dõi lẫn nhau.
3. Giải thích vì sao followers[Bình] có An không đồng nghĩa cần tạo thêm cạnh Bình → An.
4. Nêu đường truy vấn phù hợp khi người dùng mở trang “Ai theo dõi Bình?”.

**Gợi ý:** following[An] chứa Bình và Chi; followers[Bình] chứa An và Dung. An/Bình theo dõi lẫn nhau do tồn tại **hai cạnh nghiệp vụ đối hướng**.

### Bài 2. MongoDB một nguồn, hai index

Một collection enrollment có:

~~~json
{
  "tenantId": "T1",
  "learnerId": "L001",
  "courseId": "C101",
  "enrollmentId": "E1001",
  "joinedAt": "2026-09-01T00:00:00Z",
  "status": "ACTIVE"
}
~~~

Thiết kế:

1. Index phục vụ “các khóa của L001”.
2. Index phục vụ “những người học của C101”.
3. Điều kiện duy nhất để ngăn trùng enrollmentId trong một tenant.
4. Truy vấn trả 20 enrollment mới nhất theo courseId.
5. Phương án giữ nhiều lượt đăng ký cùng learnerId và courseId mà không bị chặn nhầm bởi unique pair.

**Gợi ý:** Cần phân biệt identity của **một lượt đăng ký** (enrollmentId) với cặp learner–course; dùng compound index với trường lọc đứng đầu và joinedAt làm khóa sort.

### Bài 3. Chọn giữa GSI và hai item DynamoDB

Một ứng dụng cần:

- Một người có thể theo dõi nhiều người khác.
- API “người tôi theo dõi” phải đọc theo khóa chính.
- API “ai theo dõi tôi” được phép cập nhật chậm vài giây.
- Một tính năng bảo mật cần kiểm tra chính xác **An đã theo dõi Bình chưa** trong phạm vi yêu cầu.

Hãy chọn cấu trúc item chính, GSI và đường xác minh cho tính năng bảo mật. Giải thích tại sao không dùng Query GSI eventual làm bằng chứng duy nhất của trạng thái quan hệ tức thời.

Sau đó đổi yêu cầu: **cả hai danh sách phải được cập nhật trong cùng một transaction tại một Region, với ít bản ghi**. Mô hình hai item có thể thay đổi lựa chọn ra sao?

### Bài 4. Cassandra hai bảng đọc

Cho hai bảng:

~~~text
following_by_user(tenantId, followerId, followedId)
followers_by_user(tenantId, followedId, followerId)
~~~

Hãy:

1. Chọn partition key và clustering key để truy vấn một user không phải quét toàn hệ thống.
2. Viết ý tưởng INSERT cho quan hệ An → Bình vào cả hai bảng.
3. Mô tả lỗi khi chỉ ghi thành công bảng đầu.
4. Đề xuất phương án đồng bộ/repair.
5. Nếu Bình có 10 triệu follower, cần phân tích rủi ro partition nào?

### Bài 5. Retry và unfollow

Luồng event:

~~~text
v1: FOLLOW An -> Bình
v2: UNFOLLOW An -> Bình
v3: FOLLOW An -> Bình
~~~

Projection nhận v3 trước, v1 sau, rồi v2 cuối.

Hãy xác định trạng thái cuối đúng và giải thích cách dùng version/CAS hoặc tombstone để tránh ghi đè sai thứ tự. Nếu lịch sử theo dõi từng giai đoạn cũng phải được lưu, schema identity cần đổi như thế nào?

### Bài 6. Tính chi phí bản chiếu

Một mạng xã hội có 500.000 người dùng, trung bình mỗi người theo dõi 200 tài khoản.

1. Ước lượng tổng số quan hệ FOLLOWS có hướng.
2. Nếu lưu một forward và một reverse item cho mỗi quan hệ, có bao nhiêu item bản chiếu?
3. Nếu mỗi item trung bình chiếm 150 byte phần dữ liệu ứng dụng, ước tính dung lượng thô chưa gồm index và replication.
4. Liệt kê những yếu tố khiến dung lượng vận hành thực tế lớn hơn phép tính.

**Gợi ý:**

\[
500.000 \times 200 = 100.000.000\ \text{quan hệ}.
\]

\[
100.000.000 \times 2 = 200.000.000\ \text{item}.
\]

Với 150 byte/item, dung lượng thô khoảng 30 GB; thực tế còn có overhead, index, replication, partition metadata, tombstone và những thuộc tính khác.

### Bài 7. Thiết kế theo quyền và tenant

Hai tenant T1 và T2 đều có người dùng mã An và Bình. T1 có quan hệ An → Bình, T2 không có.

Hãy đề xuất:

1. Khóa forward/reverse phân biệt tenant.
2. Truy vấn chỉ đọc dữ liệu được phép thấy.
3. Quy tắc tạo/xóa quan hệ ngăn user tự sửa tenantId.
4. Cách xử lý dữ liệu reverse khi người dùng bị xóa.

**Gợi ý:** Tenant cần nằm trong khóa hoặc phạm vi partition/index và phải được ràng buộc từ identity đã xác thực. Không tin tenantId do client tự gửi để quyết định quyền.

## 22. Tổng kết

**Chỉ mục đảo hoặc bảng tra cứu phụ** giải quyết bài toán **một quan hệ nhưng có nhiều điểm bắt đầu truy vấn**. Khi lưu An → Bình, ta thường muốn đọc được cả “An theo dõi ai?” và “Ai theo dõi Bình?” mà không phải quét tất cả quan hệ.

Các nguyên tắc cần ghi nhớ:

1. **Đảo chiều truy vấn không đồng nghĩa đảo chiều nghiệp vụ.** Reverse lookup của An → Bình không tạo quan hệ Bình → An.
2. **Một record với hai index** thường là lựa chọn tốt khi cơ sở dữ liệu hỗ trợ chỉ mục phù hợp; **hai bảng/read model** phù hợp khi hai mẫu truy vấn cần khóa phân vùng riêng.
3. **MongoDB compound indexes, DynamoDB GSI, Cassandra dual tables, Redis SET/ZSET** có những mức đồng bộ, giới hạn và chi phí khác nhau. Phải gắn kết luận với sản phẩm và cách triển khai cụ thể.
4. **Mức nhất quán phải được nói rõ:** GSI có thể trễ; hai ghi độc lập có thể lệch; transaction chỉ bảo vệ trong phạm vi được hỗ trợ.
5. **Quan hệ phải có identity phù hợp:** Cặp source–target cho một quan hệ hiện hành; relationId/enrollmentId nếu cần lưu nhiều lần hợp lệ.
6. **Cần chống retry, event sai thứ tự và hồi sinh dữ liệu đã xóa**, đồng thời duy trì khả năng backfill và đối soát.
7. **Giảm quét khi đọc thường tăng chi phí ghi và lưu trữ.** Với supernode, fan-out, phân trang và quyền riêng tư, cần đo tải thực tế trước khi nhân bản dữ liệu.

Câu hỏi quyết định không chỉ là “Có nên tạo bảng đảo không?” mà là: **Hai API cần truy vấn theo khóa nào, yêu cầu độ mới ra sao, dữ liệu gốc thuộc về ai và làm thế nào bảo đảm mọi đường đọc cùng phản ánh đúng một quan hệ nghiệp vụ?**
