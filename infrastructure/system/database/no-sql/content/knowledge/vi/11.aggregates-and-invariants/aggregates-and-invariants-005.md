# Kiểm tra duy nhất và cạnh tranh khi tạo bản ghi mới

## 1. Vì sao “kiểm tra rồi tạo” có thể làm sai dữ liệu?

Trong các hệ NoSQL, dữ liệu thường được tổ chức theo **nhóm có cùng vòng đời và bất biến nghiệp vụ**: người dùng, giỏ hàng, đơn hàng, phiên đặt chỗ, tài khoản của một tổ chức. Một nhóm dữ liệu có thể được lưu trong một tài liệu, một item, một partition hoặc nhiều bản ghi có liên hệ. Cách nhóm quyết định những thay đổi nào có thể được kiểm tra và ghi **nguyên tử**.

Xét yêu cầu đơn giản:

> Mỗi người dùng chỉ được đăng ký một tài khoản với cùng địa chỉ email đã chuẩn hóa.

Ứng dụng nhận yêu cầu đăng ký email `an@example.com`. Một cách viết dễ gặp:

```text
1. SELECT/FIND user WHERE email = "an@example.com"
2. Nếu không tồn tại:
      INSERT/PUT user(email = "an@example.com")
3. Trả kết quả tạo thành công
```

Nếu chỉ có một yêu cầu, quy trình trên có thể trông như hoạt động đúng. Nhưng khi hai yêu cầu chạy đồng thời:

```text
Thời gian       Request A                 Request B
   |
   v            Kiểm tra email            |
                -> chưa tồn tại           |
                                          Kiểm tra email
                                          -> chưa tồn tại
                Tạo user U1               |
                -> thành công             |
                                          Tạo user U2
                                          -> thành công
   |
   v            Cả U1 và U2 cùng email
```

Mỗi request đã làm đúng **theo kết quả kiểm tra nó nhận được**, nhưng kết quả toàn hệ thống vi phạm quy tắc duy nhất. Đây là một **race condition** do thao tác kiểm tra và ghi không được bảo vệ bằng một bảo đảm nguyên tử chung.

Bài học này giải thích cách mô tả ràng buộc duy nhất, chọn nơi thực thi bất biến, dùng thao tác ghi có điều kiện hoặc chỉ mục duy nhất, xử lý retry và những giới hạn đặc biệt của NoSQL phân tán.

## 2. Ràng buộc duy nhất là một bất biến nghiệp vụ

**Bất biến (invariant)** là điều kiện phải luôn đúng tại những thời điểm hệ thống cam kết trạng thái nghiệp vụ hợp lệ. Ví dụ:

- Trong một tenant, không có hai tài khoản cùng username đã chuẩn hóa.
- Một mã đơn hàng chỉ thuộc về một đơn.
- Một mã đặt chỗ không được tạo trùng cho hai người dùng.
- Với mỗi sự kiện, một ghế chỉ có tối đa một đặt chỗ đang được xác nhận, theo mô hình trạng thái được chọn.
- Một external transaction ID không được dẫn tới hai giao dịch nghiệp vụ khác nhau.

Một phát biểu đủ rõ phải xác định **phạm vi**, **khóa duy nhất**, **điều kiện áp dụng** và **hành vi khi xung đột**.

Ví dụ:

> Với mỗi `tenantId`, tại mọi thời điểm có tối đa một tài khoản hoạt động có `usernameCanonical` bằng giá trị đã cho. Khi hai thao tác tạo cạnh tranh, tối đa một thao tác được phép cam kết quyền sở hữu username đó.

Phát biểu này khác với “username không được trùng” vì nó làm rõ:

1. Duy nhất **toàn hệ thống** hay chỉ **trong tenant**?
2. So sánh theo giá trị người dùng gõ hay dạng chuẩn hóa?
3. Tài khoản bị xóa/khóa có còn giữ username không?
4. Hai request đến cùng lúc thì request nào thắng?
5. Nếu request thành công nhưng response bị mất, gọi lại thế nào?

### 2.1. Mô hình bằng logic

Gọi `Users` là tập tài khoản hoạt động và `norm` là hàm chuẩn hóa username theo chính sách nghiệp vụ.

Bất biến duy nhất trong tenant:

\[
\forall u,v \in Users:
(u.tenantId=v.tenantId \land norm(u.username)=norm(v.username))
\Rightarrow u.id=v.id
\]

Nói đơn giản: hai tài khoản cùng tenant và cùng username chuẩn hóa **phải là cùng một tài khoản**.

Một bất biến khác chỉ yêu cầu `userId` là duy nhất toàn cục. Bảo đảm về `userId` **không tự bảo đảm** username duy nhất. Chọn sai khóa kiểm tra là nguồn lỗi rất phổ biến trong NoSQL.

### 2.2. Tính duy nhất khác tính đầy đủ và hợp lệ

| Ràng buộc | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Duy nhất | Không trùng `emailCanonical` | Có nhiều thực thể giữ cùng khóa không? |
| Bắt buộc | `emailCanonical` không được thiếu | Mọi thực thể có trường này không? |
| Kiểu dữ liệu | Email là string | Giá trị có đúng kiểu không? |
| Định dạng | Email vượt qua validation đã thống nhất | Dữ liệu có hợp lệ theo chính sách không? |
| Quan hệ | `tenantId` tham chiếu tenant tồn tại | Liên kết có hợp lệ không? |
| Điều kiện nghiệp vụ | Một user chỉ được tạo tối đa 3 dự án | Cần phối hợp đếm, kiểm tra và ghi trong một phạm vi nguyên tử |

Unique index xử lý một loại bất biến rất quan trọng nhưng không thay thế toàn bộ validation và giao dịch nghiệp vụ.

## 3. Vì sao đọc trước khi ghi không phải là khóa bảo vệ?

Xem đoạn giả mã:

```java
User existing = repository.findByEmailCanonical(emailCanonical);

if (existing != null) {
    throw new EmailAlreadyUsedException();
}

repository.insert(new User(newId(), emailCanonical));
```

Vấn đề nằm ở **khoảng thời gian giữa điều kiện và thay đổi trạng thái**.

- Request A và B có thể đọc cùng trạng thái cũ.
- Cả hai cùng vượt qua điều kiện.
- Nếu database chỉ bảo đảm ID của từng bản ghi là duy nhất, hai ID khác nhau sẽ không xung đột ở tầng lưu trữ.
- Kết quả cuối cùng vi phạm bất biến về email.

Hiện tượng này thường được gọi là **time-of-check to time-of-use (TOCTOU)**. Nó có thể xảy ra cả khi hai request chạy trên cùng một máy; với nhiều instance hoặc vùng địa lý, việc phối hợp còn khó hơn.

### 3.1. Thay `findByEmail` bằng đọc mạnh hơn có đủ không?

**Không mặc định.** Một lượt đọc nhất quán mạnh chỉ cho biết trạng thái tại lúc đọc. Nếu cả hai request đọc trước khi bất kỳ request nào ghi, cả hai vẫn có thể thấy “chưa tồn tại”.

Cần một trong các cơ chế có khả năng **nguyên tử hóa việc kiểm tra điều kiện và giữ quyền tạo**:

- Unique constraint/index có hiệu lực tại lúc ghi.
- Conditional insert / compare-and-set trên cùng khóa bảo vệ.
- Transaction có mức cô lập và cơ chế xung đột phù hợp.
- Giao thức phân bổ tên/ID duy nhất qua một nơi có thể tuần tự hóa yêu cầu.
- Mô hình khác tương đương, nhưng phải xác định rõ phạm vi bảo đảm.

Không được kết luận rằng một cặp thao tác `read(); write();` tạo thành một giao dịch chỉ vì chúng diễn ra liên tiếp trong một hàm Java.

### 3.2. Kiểm tra trước vẫn có ích, nhưng chỉ để cải thiện trải nghiệm

Ứng dụng có thể kiểm tra sơ bộ “email có vẻ đã được dùng” để hiển thị phản hồi sớm. Tuy nhiên, **kết quả của phép kiểm tra sơ bộ không phải lời bảo đảm**. Bước tạo cuối cùng vẫn cần cơ chế nguyên tử tại nơi thực thi bất biến.

Quy trình hợp lý:

```text
Client nhập email
       |
       v
Kiểm tra định dạng/chuẩn hóa
       |
       v
[Tuỳ chọn] kiểm tra tồn tại để gợi ý
       |
       v
Thao tác tạo có unique/condition nguyên tử
       |
       +--> thành công: trả bản ghi
       |
       +--> xung đột: trả lỗi phù hợp hoặc kết quả idempotent
```

## 4. Chọn đúng phạm vi bảo đảm: một bản ghi, một partition hay toàn hệ

Các NoSQL database có ranh giới nguyên tử khác nhau. Khi phát biểu “không được trùng”, phải biết nơi nào có thể quyết định **một người thắng, một người thua**.

| Phạm vi cần duy nhất | Ví dụ | Cách tổ chức có thể phù hợp |
|---|---|---|
| Trong một tài liệu | Một SKU không xuất hiện hai lần trong array theo quy tắc riêng | Atomic update với điều kiện hoặc tái tổ chức thành các phần tử có khóa |
| Theo một khóa item | Chỉ một item `USERNAME#tenant#name` | Conditional put/insert-if-absent |
| Trong một partition | Một tên trong phạm vi tenant/partition có khóa định danh | CAS/LWT/transaction theo bảo đảm của sản phẩm |
| Trong một collection | `emailCanonical` của mọi user | Unique index/constraint nếu sản phẩm hỗ trợ đúng phạm vi |
| Giữa nhiều collection/bảng | Bản ghi username và profile phải được tạo cùng nhau | Transaction phù hợp hoặc giao thức reservation + phục hồi |
| Xuyên nhiều vùng ghi độc lập | Tên duy nhất toàn cầu | Cần một nơi quyết định tuần tự/consensus hoặc thiết kế khác chứng minh được bất biến |

**Một hệ thống phân tán không thể bảo đảm độc lập hai nơi cùng nhận ghi tạo một tên toàn cục, trong khi chúng không có giao thức phối hợp, rồi mặc định luôn giữ được tính duy nhất tại thời điểm nhận cả hai ghi.** Nếu yêu cầu cho phép xung đột tạm thời và giải quyết sau, đó là một hợp đồng khác với “không bao giờ trùng”.

### 4.1. Đặt khóa mà database thật sự bảo vệ

Giả sử lưu:

```json
{
  "_id": "user-001",
  "tenantId": "T1",
  "usernameCanonical": "an"
}
```

Nếu database chỉ bảo vệ `_id`, hai document khác `_id` nhưng cùng `tenantId` và `usernameCanonical` có thể cùng tồn tại.

Để bảo vệ username theo tenant, ta cần **khóa hoặc constraint tương ứng với cặp `(tenantId, usernameCanonical)`**, chứ không chỉ dựa trên user ID.

## 5. Cách 1: unique index trong document database

### 5.1. Ví dụ với MongoDB

Giả sử mỗi tài khoản có:

```javascript
{
  _id: "user-001",
  tenantId: "T1",
  username: "An",
  usernameCanonical: "an",
  displayName: "An Nguyễn"
}
```

Nếu username phải duy nhất trong mỗi tenant, có thể tạo unique compound index:

```javascript
db.users.createIndex(
  { tenantId: 1, usernameCanonical: 1 },
  {
    unique: true,
    name: "uq_users_tenant_username"
  }
);
```

Sau khi chỉ mục đã được tạo thành công, hai thao tác insert có cùng cặp giá trị được bảo vệ sẽ không được chấp nhận đồng thời như hai document hợp lệ trong phạm vi unique index đó:

```javascript
db.users.insertOne({
  _id: "user-001",
  tenantId: "T1",
  username: "An",
  usernameCanonical: "an"
});

// Insert khác _id nhưng trùng cặp tenantId + usernameCanonical
db.users.insertOne({
  _id: "user-002",
  tenantId: "T1",
  username: "AN",
  usernameCanonical: "an"
});
// Bị từ chối bởi unique index nếu bản ghi đầu đã tồn tại.
```

Với MongoDB, xung đột unique index thường trả **duplicate key error** mã `11000`. Ứng dụng cần nhận diện và chuyển thành lỗi nghiệp vụ phù hợp, thay vì trả nguyên lỗi database cho client.

### 5.2. Unique index khác với truy vấn kiểm tra trước

Thao tác `insertOne` và phép kiểm tra unique index được database điều phối khi ghi. Hai request cùng cạnh tranh có thể cùng cố insert, nhưng chỉ một bản ghi có cùng khóa duy nhất được chấp nhận theo bảo đảm của chỉ mục.

Vì vậy, điểm quyết định đúng đắn là **kết quả ghi cuối cùng**, không phải kết quả `findOne` trước đó.

Ví dụ ý tưởng xử lý ở backend:

```text
try:
    insert user
    return 201 CREATED
catch duplicate-key:
    return 409 CONFLICT
catch network-error:
    determine whether write committed before retry
```

Một duplicate key trên `usernameCanonical` có thể có ý nghĩa “tên đã được dùng”; nhưng nếu document còn nhiều unique index khác, cần xác định **index nào bị vi phạm** hoặc quy chiếu hợp lý để không trả sai loại xung đột.

### 5.3. Dữ liệu đã trùng trước khi tạo index

Nếu collection hiện đã có hai document cùng username, thao tác tạo unique index có thể thất bại vì không thể xây dựng chỉ mục bảo đảm duy nhất trên dữ liệu vi phạm.

Một quy trình áp dụng trong hệ đang chạy:

1. Xác định chuẩn hóa username.
2. Tìm các cặp trùng trong phạm vi tenant.
3. Quyết định bản ghi chuẩn và cách xử lý tài khoản trùng.
4. Dừng hoặc thay đổi luồng ghi tạo thêm trùng trong quá trình chuyển đổi.
5. Tạo unique index và xác nhận tạo thành công.
6. Triển khai logic bắt duplicate-key khi tạo mới.

Không được xem việc chạy lệnh `createIndex` là thành công chỉ vì code đã gửi lệnh; phải kiểm tra database thật sự tạo index mà không có lỗi.

### 5.4. Trường thiếu và giá trị null

Trong MongoDB, unique index thông thường có ngữ nghĩa đối với trường thiếu/null khác với yêu cầu “mọi user bắt buộc có email”. Ví dụ, một unique single-field index có thể xem document thiếu trường như một giá trị null cho mục đích entry index, dẫn đến hạn chế số document cùng giá trị đó.

Nếu email **không bắt buộc**, có thể dùng **partial unique index** để chỉ áp dụng ràng buộc cho những document phù hợp điều kiện:

```javascript
db.users.createIndex(
  { emailCanonical: 1 },
  {
    unique: true,
    name: "uq_users_email_when_string",
    partialFilterExpression: {
      emailCanonical: { $type: "string" }
    }
  }
);
```

Ở đây, ràng buộc chỉ áp dụng cho document có `emailCanonical` thuộc kiểu string; document không có trường hoặc trường không phải string nằm ngoài phạm vi index. Điều này **không đồng nghĩa** mọi dữ liệu ngoài phạm vi index là hợp lệ: cần validation nếu email bắt buộc hoặc không chấp nhận giá trị null/sai kiểu.

Tương tự, `""` là một string; nếu nhiều user cùng có email rỗng, partial index trên string vẫn có thể gây xung đột. Nên chuẩn hóa và từ chối email rỗng theo nghiệp vụ.

### 5.5. Ràng buộc khi sharding

Trong MongoDB sharded collection, khả năng tạo unique index **bị giới hạn bởi shard key và cấu hình**. Thông thường, unique index trên sharded collection phải chứa shard key như một tiền tố theo quy tắc của MongoDB; với hashed shard key cũng có những hạn chế riêng.

Ví dụ, nếu cần username duy nhất **toàn cầu**, nhưng dữ liệu được shard theo `tenantId`, một index chỉ gồm `usernameCanonical` không tự nhiên đảm bảo duy nhất toàn cầu trong mọi cấu hình. Phải thiết kế shard key/unique index phù hợp hoặc duy trì một nơi đặt khóa bảo vệ riêng.

Không nên quyết định shard key tách rời khỏi bất biến cần bảo vệ.

### 5.6. Update và upsert cũng có thể vi phạm unique

Unique index không chỉ áp dụng lúc tạo tài khoản. Nếu user đổi username sang giá trị của người khác, `updateOne` vẫn phải được kiểm tra ràng buộc.

Với `upsert`, hai request cùng không tìm thấy bản ghi có thể cùng thử insert. Unique index ngăn trùng dữ liệu, nhưng **ứng dụng vẫn có thể nhận duplicate-key từ một request cạnh tranh** và cần xử lý. `upsert:true` không tự thay thế việc thiết kế filter và key đúng.

Một mẫu “tìm hoặc tạo” cần suy nghĩ riêng về trường hợp tên đã tồn tại nhưng thuộc về người khác. Không được tự động coi mọi duplicate-key là yêu cầu đã được thực hiện cho chính người gọi.

## 6. Cách 2: conditional write ở kho key–value hoặc item store

Một số hệ NoSQL có cơ chế tạo item **chỉ khi khóa chưa tồn tại**, thường gọi là conditional put, insert-if-absent hoặc compare-and-set.

Ý tưởng:

```text
AtomicCreate(key, value)
    IF key chưa tồn tại
    THEN ghi key=value và trả thành công
    ELSE không ghi và trả xung đột
```

Cả điều kiện “chưa có” và thao tác “tạo” phải là một hành động được database bảo đảm nguyên tử trong phạm vi khóa đó.

### 6.1. Ví dụ với Amazon DynamoDB

Giả sử bảng `Usernames` có partition key `PK`. Ta tổ chức mỗi username thành **một item giữ quyền sở hữu**:

```json
{
  "PK": "USERNAME#T1#an",
  "userId": "user-001",
  "state": "OWNED"
}
```

Dùng `PutItem` với điều kiện:

```json
{
  "TableName": "Usernames",
  "Item": {
    "PK": {"S": "USERNAME#T1#an"},
    "userId": {"S": "user-001"},
    "state": {"S": "OWNED"}
  },
  "ConditionExpression": "attribute_not_exists(PK)"
}
```

Đây là dạng request minh họa cho API DynamoDB. Với một item có cùng primary key, nếu đã tồn tại, điều kiện thất bại thay vì ghi đè. Database thực hiện phép kiểm tra và ghi theo bảo đảm conditional write của nó.

Điều cốt lõi là **toàn bộ phạm vi uniqueness đã được ánh xạ thành cùng một item key**. Nếu mỗi user có `PK = USER#userId` và chỉ thêm thuộc tính `usernameCanonical`, `attribute_not_exists(PK)` chỉ bảo vệ user ID, **không tự bảo vệ username**.

### 6.2. Thao tác điều kiện khác truy vấn phụ qua secondary index

Một thiết kế dễ mắc lỗi:

```text
1. Query GSI emailIndex xem email có ai dùng chưa
2. Nếu không thấy -> PutItem USER#newUserId
```

Một global secondary index không nên được coi là nơi thực thi unique constraint nếu sản phẩm không cung cấp bảo đảm tương ứng. Kết quả truy vấn có thể không bảo vệ được race, và ở DynamoDB GSI còn có ngữ nghĩa cập nhật bất đồng bộ.

Nếu cần email duy nhất, hãy có item/khóa bảo vệ email và thực hiện **conditional write** trực tiếp trên khóa đó.

### 6.3. Tạo cả item username và hồ sơ người dùng

Nếu thao tác tạo cần hai item:

1. `USERNAME#T1#an` — giữ quyền sở hữu username.
2. `USER#user-001` — hồ sơ người dùng.

Dùng hai `PutItem` độc lập có thể tạo trạng thái nửa chừng:

```text
Ghi reservation thành công
     |
     X  Ghi user profile thất bại
     |
Username bị chiếm nhưng user chưa tồn tại
```

DynamoDB có `TransactWriteItems` để nhóm các thay đổi item vào một transaction theo giới hạn và bảo đảm được hỗ trợ. Có thể đưa hai `Put` vào cùng transaction, trong đó item username có điều kiện `attribute_not_exists(PK)` và item user có điều kiện tương ứng.

Mô hình request ý tưởng:

```text
TransactWriteItems:
  Put USERNAME#T1#an
      IF attribute_not_exists(PK)
  Put USER#user-001
      IF attribute_not_exists(PK)
=> Cùng commit hoặc cùng không commit
```

Cần kiểm tra hạn mức, điều kiện transaction, lỗi xung đột và các lựa chọn idempotent token theo API thực tế. Việc giao dịch bảo đảm nguyên tử giữa hai item **không tự bảo đảm** mọi quy tắc khác, như giới hạn số lượng user trong tenant nếu chưa được đưa vào giao thức bảo vệ.

### 6.4. Tenant và chuẩn hóa khóa

Nếu username chỉ duy nhất trong tenant:

```text
USERNAME#T1#an
USERNAME#T2#an
```

là hai khóa khác nhau nên được phép cùng tồn tại. Nếu nghiệp vụ yêu cầu toàn hệ không được trùng, bỏ phần tenant hoặc thay bằng namespace phù hợp.

Quy tắc tạo chuỗi khóa phải ổn định và tránh mơ hồ. Ví dụ giá trị tenant hoặc username có chứa dấu `#` cần được mã hóa hoặc biểu diễn có phân cách không thể nhập nhằng. Một hệ thống tốt dùng cấu trúc key có hợp đồng định danh rõ, không ghép chuỗi tùy tiện mà có nguy cơ va chạm.

## 7. Cách 3: lightweight transaction / IF NOT EXISTS trong wide-column

Với Apache Cassandra, thao tác `INSERT IF NOT EXISTS` dùng cơ chế **lightweight transaction (LWT)** để áp dụng điều kiện tạo khi khóa chính chưa tồn tại.

Ví dụ, cần username duy nhất trong tenant:

```sql
CREATE TABLE usernames_by_tenant (
    tenant_id text,
    username_canonical text,
    user_id uuid,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, username_canonical))
);
```

Ở bảng này, khóa phân vùng ghép `(tenant_id, username_canonical)` chính là cặp mà ứng dụng muốn bảo vệ.

Thao tác tạo:

```sql
INSERT INTO usernames_by_tenant
    (tenant_id, username_canonical, user_id, created_at)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
```

Kết quả CQL có trường `[applied]` cho biết điều kiện có được áp dụng hay không:

```text
[applied] = true  -> thêm reservation thành công
[applied] = false -> khóa đã có (thường kèm giá trị hiện có)
```

### 7.1. Vì sao không chỉ dùng INSERT thường?

Cassandra `INSERT` thông thường có tính chất upsert theo primary key. Nếu hai request ghi cùng khóa nhưng user khác nhau, hệ thống có thể giải quyết xung đột theo quy tắc timestamp mà không báo cho cả hai rằng **một người bị từ chối giữ tên**.

LWT đặt phép kiểm tra điều kiện và cập nhật trong một giao thức đồng thuận cho phạm vi mà nó bảo vệ. Vì vậy, nó phù hợp hơn khi cần xác định **chính xác người giành quyền sở hữu một khóa**.

### 7.2. Phạm vi của LWT không tự mở rộng sang mọi bảng

Giả sử sau khi giữ username thành công, ứng dụng tiếp tục tạo profile ở một bảng khác:

```text
INSERT usernames_by_tenant ... IF NOT EXISTS  -> applied = true
INSERT users_by_id ...                        -> lỗi mạng
```

Username đã được giữ nhưng user profile có thể chưa được tạo. Điều kiện của bảng thứ nhất không biến hai thao tác thành một transaction nguyên tử xuyên bảng.

Cần một giao thức khôi phục:

- Lưu trạng thái reservation như `PENDING`/`ACTIVE` và owner ID.
- Retry tạo profile với cùng owner ID một cách idempotent.
- Xác minh kết quả khi không biết thao tác trước đã commit hay chưa.
- Có job phát hiện reservation treo và quy tắc thu hồi hoặc hoàn tất.
- Không thu hồi một reservation chỉ dựa vào timeout nếu thao tác gốc còn có khả năng đang hoàn tất.

Nếu cần transaction nhiều thực thể với bảo đảm mạnh, phải đánh giá liệu Cassandra có thực sự phù hợp cho yêu cầu đó hay không, hoặc chọn nguồn khác có giao dịch phù hợp.

### 7.3. LWT không nên dùng vô tội vạ

LWT thường tốn thêm lượt trao đổi và công đồng thuận so với ghi không điều kiện. Nó hữu ích cho các bất biến cần quyết định duy nhất, nhưng không nhất thiết thích hợp cho mọi bản ghi telemetry hoặc sự kiện có thể tự sinh ID độc lập.

Một bảng bảo vệ khóa cần thiết kế đúng partition key. Nếu mô hình hóa sai và LWT chỉ bảo vệ `user_id`, nó không cung cấp uniqueness cho email.

## 8. Cách 4: cùng một khóa quyết định bằng thiết kế aggregate

Một trong những cách đơn giản nhất để tránh đua tranh là **đưa điều kiện cần bảo vệ và thay đổi trạng thái vào cùng một đơn vị có thao tác nguyên tử**.

Ví dụ một hệ key–value/document có item theo username:

```text
PK = TENANT#T1#USERNAME#an
value = {
    ownerUserId: "user-001",
    createdAt: "...",
    state: "OWNED"
}
```

Mỗi request tạo username `an` trong T1 đều đụng tới **cùng khóa**. Database có cơ chế “create only if absent” ở khóa này có thể quyết định winner.

Đây là lý do quan trọng của việc **nhóm dữ liệu quanh bất biến**: nếu những yêu cầu cạnh tranh đều đến đúng một nơi, việc kiểm soát tính duy nhất đơn giản hơn so với để chúng tạo các bản ghi rời rồi cố phát hiện trùng sau.

### 8.1. Một tài liệu có thể chứa tập tên đã chiếm?

Có thể tạo một tài liệu tenant chứa danh sách username, rồi cập nhật atomically khi tên chưa có. Tuy nhiên, cách này có thể không phù hợp nếu tenant có hàng triệu username:

- Tài liệu có giới hạn kích thước.
- Một tài liệu nhận mọi lượt đăng ký có thể thành hot spot.
- Cập nhật đồng thời tranh chấp cùng một aggregate.
- Việc truy cập/xóa từng username có thể phức tạp.

Thường hợp lý hơn là **một item/khóa bảo vệ cho mỗi username** nếu database hỗ trợ conditional create theo key. Điều quan trọng là cơ chế thực thi trên **đúng khóa bất biến**, không phải gom tất cả dữ liệu vào một document vô hạn.

### 8.2. Chọn ranh giới aggregate theo nghiệp vụ

| Bất biến | Aggregate/khóa có thể bảo vệ | Cần chú ý |
|---|---|---|
| Username duy nhất trong tenant | `TENANT#id#USERNAME#canonical` | Đồng bộ với profile |
| Mã vé duy nhất cho sự kiện | `EVENT#id#TICKET#code` | Không tái cấp vé ngoài ý muốn |
| Một người chỉ một lần tham gia chiến dịch | `CAMPAIGN#id#USER#id` | Retry và trạng thái tham gia |
| Chỉ một webhook event được xử lý | `PROVIDER#name#EVENT#id` | Dedup và tác động nghiệp vụ |
| Một ghế được giữ bởi một booking còn hiệu lực | `EVENT#id#SEAT#number` | TTL, trạng thái, phiên đặt và giao dịch thanh toán |

Lưu ý trường hợp ghế: “mỗi ghế chỉ có một booking đang giữ” liên quan tới **trạng thái và thời hạn**. Không phải chỉ cần ID ghế duy nhất là hệ đã giải quyết việc hết hạn, trả ghế và thanh toán muộn.

## 9. Unique index khác với idempotency key

Hai cơ chế thường bị nhầm:

- **Uniqueness** đảm bảo không có hai thực thể khác nhau cùng giữ một khóa nghiệp vụ.
- **Idempotency** giúp lặp lại **cùng một yêu cầu** không tạo thêm tác dụng phụ ngoài mong muốn.

Giả sử hai request:

- Request A: đăng ký `an@example.com` cho người dùng `U1`, idempotency key `req-A`.
- Request B: đăng ký cùng email cho người dùng `U2`, idempotency key `req-B`.

Dù mỗi request có idempotency key khác nhau và được gửi đúng một lần, chúng vẫn xung đột về email. Cần unique constraint/conditional create.

Ngược lại, request A có thể được client gửi lại 3 lần vì mạng chậm. Nếu mỗi lần tạo user ID mới, hệ thống có thể cố tạo 3 bản ghi, hai lần cuối gặp duplicate email. Bất biến uniqueness vẫn giữ, nhưng client không biết rằng retry của nó nên nhận **kết quả thành công của lần đầu** chứ không phải lỗi “email thuộc về người khác”.

### 9.1. Một idempotency record

Ví dụ:

```json
{
  "idempotencyKey": "req-A",
  "requestHash": "hash-of-canonical-request",
  "status": "COMPLETED",
  "resultUserId": "user-001",
  "responseCode": 201
}
```

Khi một yêu cầu có key cũ trở lại:

- Nếu nội dung yêu cầu giống và kết quả đã hoàn tất, trả lại kết quả đã lưu.
- Nếu key giống nhưng nội dung khác, từ chối vì sử dụng lại key sai.
- Nếu yêu cầu cũ vẫn đang xử lý, trả trạng thái đang xử lý hoặc chờ theo chính sách.
- Nếu chưa có key, tranh quyền xử lý bằng thao tác tạo có điều kiện/nguyên tử.

Để hai request cùng idempotency key không đồng thời được xử lý như hai yêu cầu mới, bản thân bảng idempotency cũng cần **unique key hoặc conditional create**.

### 9.2. Chọn phạm vi và thời hạn idempotency

Một idempotency key thường cần gắn với:

- Chủ thể hoặc tenant.
- Loại thao tác.
- Bản nội dung đã chuẩn hóa hoặc hash nội dung.
- Kết quả và trạng thái xử lý.
- Chính sách lưu/TTL.

Nếu xóa idempotency record quá sớm, một retry rất muộn có thể chạy lại tác động phụ. Nếu giữ mãi, cần tính chi phí lưu trữ và quyền dữ liệu. Thời hạn phải dựa trên thời gian retry tối đa, nghiệp vụ và hợp đồng API.

**Idempotency không thay thế tính duy nhất của trường nghiệp vụ.** Nó giải quyết một chiều khác của cạnh tranh.

## 10. Khi kết quả ghi không rõ: timeout không có nghĩa là thất bại

Một lỗi thường bị bỏ qua:

```text
Client                     Database
  | -- conditional create --> |
  |                            | ghi thành công
  | <---- phản hồi bị mất ------X
  |
  |  client bị timeout
```

Client biết **không nhận được phản hồi**, chứ chưa biết thao tác có commit hay không. Nếu vội thử lại bằng **ID mới** hoặc bỏ qua trạng thái cũ, có thể tạo lỗi ở những đường khác.

Cách xử lý:

1. Gửi lại cùng idempotency key/owner ID nếu thiết kế cho phép.
2. Đọc khóa bảo vệ theo chế độ nhất quán phù hợp để xác nhận owner.
3. Nếu khóa thuộc **chính yêu cầu đó**, tiếp tục/hoàn tất các bước còn thiếu.
4. Nếu khóa thuộc request khác, trả conflict.
5. Nếu chưa có khóa, có thể thử lại thao tác điều kiện.
6. Nếu vẫn không thể xác định, trả trạng thái **unknown/pending** có cách tra cứu thay vì khẳng định thất bại chắc chắn.

Ví dụ: khi `PutItem` đặt `USERNAME#T1#an` thành công nhưng HTTP response bị mất, lần retry có thể nhận `ConditionalCheckFailed`. Điều đó không nhất thiết nghĩa là **người khác chiếm tên**; cần so `userId`/request token đang giữ khóa.

### 10.1. Hậu quả của việc dùng ID ngẫu nhiên mới khi retry

Nếu lần đầu tạo `U1` và lần retry sinh `U2` cho cùng yêu cầu, việc kiểm tra owner rất khó phân biệt. Nên có **định danh ổn định cho operation hoặc aggregate** ngay từ đầu, và gắn nó với idempotency key.

Một cách là tạo UUID cho user ở phía service trước khi bắt đầu chuỗi thao tác và sử dụng lại trong mọi lần retry của cùng operation.

## 11. Reservation pattern: giữ khóa trước, hoàn tất dữ liệu sau

Khi hệ thống không hỗ trợ transaction đủ mạnh để tạo hai cấu trúc liên quan, có thể dùng **reservation**.

Trạng thái gợi ý:

```text
        Claim unique name
               |
               v
         PENDING(ownerId)
               |
         +-----+------+
         |            |
         v            v
     Hoàn tất       Hủy/khôi phục
       |                |
       v                v
 ACTIVE(ownerId)   RELEASED hoặc đã xóa
```

Quy trình đăng ký:

1. Chuẩn hóa username và tạo `operationId`/`userId` ổn định.
2. Thực hiện `insert-if-absent` để giữ khóa tên với owner và trạng thái `PENDING`.
3. Nếu xung đột với owner khác, dừng và trả lỗi.
4. Tạo user profile theo cùng `userId`, idempotent.
5. Chuyển reservation sang `ACTIVE` bằng thao tác có điều kiện theo owner/phiên bản.
6. Nếu một bước lỗi, worker phục hồi tiếp tục hoặc bù trừ dựa trên trạng thái đã lưu.

### 11.1. Vì sao reservation cần owner và version?

Nếu chỉ lưu:

```text
username = "an"; reserved = true
```

ta không biết ai đã giữ khóa hoặc thao tác nào có quyền hoàn tất. Trường `ownerId` và `operationId` giúp phân biệt retry cũ với yêu cầu khác.

Thêm `reservationVersion`/fencing token có thể cần thiết khi một quyền giữ chỗ được thu hồi và cấp lại, để một worker cũ không hoàn tất trên một phiên mới.

Ví dụ:

```json
{
  "key": "TENANT#T1#USERNAME#an",
  "ownerUserId": "user-001",
  "operationId": "req-A",
  "reservationVersion": 4,
  "state": "PENDING"
}
```

Một worker chỉ được chuyển `PENDING` sang `ACTIVE` nếu owner và version vẫn khớp. Điều kiện này phải được kiểm tra **nguyên tử** ở nơi giữ khóa.

### 11.2. Không giải phóng tùy tiện vì timeout

Giả sử worker A đặt reservation, xử lý chậm. Worker dọn dẹp thấy reservation “quá 30 giây” và xóa. Worker B lấy tên. Worker A sau đó tiếp tục tạo user.

Nếu không có fencing/version check, hai hồ sơ có thể tưởng cùng sở hữu username.

TTL hoặc timeout chỉ là gợi ý phát hiện reservation cần xử lý. Quy trình thu hồi phải kiểm chứng trạng thái, owner, hiệu lực của operation và bảo đảm writer cũ không thể hoàn tất sau khi quyền sở hữu đã chuyển.

### 11.3. Saga và thao tác bù trừ

Một **saga** mô hình hóa công việc qua nhiều bước độc lập, mỗi bước có cơ chế retry và có thể có thao tác bù trừ. Trong tạo user:

- Claim username.
- Create profile.
- Activate username.
- Nếu cuối cùng không thể tạo profile, release username sau khi xác nhận an toàn.

Bù trừ không nhất thiết đảo ngược thời gian như transaction rollback; trong hệ phân tán, những hành động đã quan sát được có thể yêu cầu workflow riêng. Cần lưu tiến độ để khởi động lại không bị quên một bước.

## 12. Vì sao Redis SET NX hoặc distributed lock chưa chắc đủ?

Một hệ dùng Redis có thể chạy:

```text
SET unique:tenant:T1:username:an user-001 NX
```

Theo ngữ nghĩa lệnh, `NX` chỉ ghi khi key chưa tồn tại. Với dữ liệu lưu và bảo đảm của Redis đang dùng, nó có thể hữu ích để tranh quyền giữ **một key trong Redis**.

Nhưng nếu profile được lưu trong một database khác:

```text
Redis: SET NX -> thành công
MongoDB: INSERT user -> thất bại
```

giữa hai hệ chưa có transaction chung. Hoặc Redis có cơ chế failover/độ bền làm mất key mới ghi theo cấu hình, trong khi profile ở nguồn vẫn tồn tại. Khi đó việc giữ khóa Redis **không đủ chứng minh uniqueness vĩnh viễn** tại nguồn khác.

### 12.1. Distributed lock là cơ chế phối hợp, không phải ràng buộc dữ liệu cuối cùng

Một distributed lock có thể giúp giảm tranh chấp, nhưng cần hiểu:

- Lease hết hạn trong khi worker cũ vẫn chạy.
- Worker gặp GC pause hoặc mạng chậm, không biết mình mất lock.
- Hai worker có thể hành động theo những nhận thức khác nhau nếu hệ lock không có bảo đảm phù hợp.
- Có thể cần **fencing token** và nơi ghi cuối cùng từ chối thao tác mang token cũ.
- Nếu dữ liệu chính có unique index/conditional write, đó vẫn là hàng rào bảo vệ bất biến đáng tin cậy hơn cho khóa được hỗ trợ.

**Không dùng “lấy lock rồi đọc/ghi” như bằng chứng đủ cho uniqueness xuyên hệ**, trừ khi toàn bộ giao thức lock, fencing, failure handling và nguồn dữ liệu được thiết kế, kiểm chứng.

### 12.2. Dùng Redis đúng chỗ

Redis có thể phù hợp để:

- Giảm số request cạnh tranh quá cao trên cùng username.
- Giữ một claim tạm thời khi nghiệp vụ chấp nhận và có nguồn quyết định cuối.
- Cache kết quả kiểm tra sơ bộ.
- Điều phối các tác vụ không đòi hỏi bất biến duy nhất mạnh.

Nếu cần bảo đảm chỉ có một user giữ một email, nên đặt **hàng rào kiểm tra nguyên tử ở nguồn authoritative hoặc khóa bảo vệ bền vững**.

## 13. Tính duy nhất theo điều kiện: active, soft delete và vòng đời bản ghi

Không phải lúc nào uniqueness cũng là “không trùng trong toàn bộ lịch sử”.

Ví dụ chính sách:

> Chỉ một tài khoản đang hoạt động trong tenant được giữ username `an`. Sau khi tài khoản bị xóa và qua giai đoạn chờ, username có thể được cấp lại.

Khi đó cần định nghĩa:

- Tài khoản `ACTIVE` và `PENDING` có giữ tên không?
- `DISABLED` hoặc `DELETED` có giữ tên không?
- Người dùng có được khôi phục tài khoản đã xóa không?
- Sau bao lâu tên có thể cấp lại?
- Ai có quyền thu hồi một tên đang tranh chấp?
- Request xóa và request tạo mới đồng thời được xử lý theo thứ tự nào?

### 13.1. Partial unique index cho dữ liệu hoạt động

Trong MongoDB, có thể tạo một partial unique index áp dụng cho trạng thái nhất định, ví dụ:

```javascript
db.users.createIndex(
  { tenantId: 1, usernameCanonical: 1 },
  {
    unique: true,
    name: "uq_active_username_per_tenant",
    partialFilterExpression: {
      state: "ACTIVE"
    }
  }
);
```

Ràng buộc chỉ bảo vệ các document thỏa `state = "ACTIVE"`. Hai user cùng username ở trạng thái khác có thể tồn tại nếu các quy tắc khác cho phép.

**Hệ quả:** hai request cùng chuyển những hồ sơ khác nhau sang `ACTIVE` sẽ cạnh tranh tại unique index; một thao tác có thể bị từ chối. Nếu `PENDING` cũng phải giữ tên, index chỉ áp dụng `ACTIVE` chưa đáp ứng đầy đủ bất biến. Khi đó dùng reservation hoặc chính sách partial filter bao phủ tập trạng thái được giữ.

### 13.2. Thu hồi và cấp lại tên có race

Giả sử:

- User U1 đang giữ username `an`.
- Request A xóa U1.
- Request B tạo U2 với username `an`.
- Request C khôi phục U1.

Nếu quy tắc không xác định rõ thứ tự và quyền sở hữu, B và C có thể cùng nghĩ mình được dùng tên.

Cần một **điểm quyết định quyền sở hữu** và điều kiện chuyển trạng thái được bảo vệ nguyên tử. Ví dụ, chỉ owner hiện tại hoặc workflow được ủy quyền mới được release; restore U1 phải claim lại tên và có thể thất bại nếu tên đã được cấp cho U2 theo chính sách.

### 13.3. TTL không tự bảo đảm cleanup đúng thời điểm

Với TTL/expiration, dữ liệu có thể bị xóa bất đồng bộ hoặc theo cơ chế của sản phẩm. Không nên đồng nhất “thời hạn đã qua” với “khóa đã được giải phóng và mọi writer cũ đã mất quyền”.

Nếu uniqueness có liên quan đến đặt chỗ thời hạn ngắn, mô hình cần phiên bản, trạng thái và chính sách xét thời gian tại nguồn có đồng hồ/điều kiện đáng tin cậy.

## 14. Chuẩn hóa tên và email trước khi kiểm tra duy nhất

Nếu hệ thống cho phép username không phân biệt hoa thường:

```text
"An"   -> "an"
"AN"   -> "an"
"an"   -> "an"
```

Thì nên lưu thêm **khóa chuẩn hóa**:

```json
{
  "usernameDisplay": "An",
  "usernameCanonical": "an"
}
```

và tạo unique index/conditional key trên `usernameCanonical`.

### 14.1. Cần một chính sách canonicalization cố định

Các câu hỏi:

- Chữ hoa/chữ thường có được xem như nhau không?
- Có trim khoảng trắng ở đầu/cuối không?
- Có cho Unicode không?
- Có dùng Unicode normalization (NFC/NFKC) không?
- Có phân biệt ký tự theo ngôn ngữ hoặc locale không?
- Có cho ký tự dễ gây nhầm lẫn thị giác không?
- Đổi chính sách trong tương lai sẽ migrate dữ liệu ra sao?

**Không nên viết `toLowerCase()` ngẫu nhiên ở mỗi service** rồi cho rằng mọi ngôn ngữ và locale đều xử lý giống nhau. Một service dùng quy tắc khác có thể tạo key khác cho cùng username nhìn giống nhau.

Ví dụ Java:

```java
import java.text.Normalizer;
import java.util.Locale;

public final class UsernamePolicy {
    private UsernamePolicy() {}

    public static String canonicalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("username is required");
        }

        String normalized =
                Normalizer.normalize(input.trim(), Normalizer.Form.NFC);
        String canonical = normalized.toLowerCase(Locale.ROOT);

        if (canonical.isBlank()) {
            throw new IllegalArgumentException("username is blank");
        }
        return canonical;
    }
}
```

Đây là **chính sách minh họa**, không phải chuẩn duy nhất cho mọi sản phẩm. Nó chưa giải quyết hết vấn đề Unicode case folding, ký tự tương tự hoặc giới hạn ký tự được phép. Nhiều hệ có thể chọn bộ ký tự username hẹp hơn và validation cụ thể để tránh nhầm lẫn.

### 14.2. Email cần chính sách riêng

Địa chỉ email phức tạp hơn username:

- Domain thường được xử lý không phân biệt hoa thường theo quy tắc tên miền.
- Phần local trước `@` không nên tự ý chuẩn hóa theo quy tắc của một nhà cung cấp cụ thể nếu nghiệp vụ chưa quyết định.
- Quy tắc dấu chấm hoặc alias kiểu `+tag` có thể khác giữa các nhà cung cấp.
- Unicode và domain quốc tế cần chính sách kiểm tra/biểu diễn riêng.
- Có thể yêu cầu xác minh email để xác nhận quyền sở hữu, nhưng xác minh là một bất biến khác với uniqueness.

Nếu sản phẩm chọn “email không phân biệt hoa thường ở toàn địa chỉ” như quy tắc nghiệp vụ, cần thống nhất và áp dụng nhất quán từ API, database, luồng đăng ký đến migration; không mặc định đó là quy tắc phổ quát phù hợp mọi hệ thống email.

### 14.3. Collation và normalized field

Một số database hỗ trợ **collation** cho so sánh không phân biệt hoa thường hoặc theo locale. Có thể dùng unique index với collation thích hợp trong phạm vi sản phẩm. Tuy nhiên, ứng dụng và mọi truy vấn phải hiểu quy tắc đó.

Lưu `canonicalKey` minh bạch cũng là một lựa chọn, đặc biệt khi nhiều hệ hoặc ngôn ngữ lập trình cùng tham gia. Cần tránh việc vừa dùng collation vừa dùng chuẩn hóa khác nhau dẫn đến kết quả khó giải thích.

## 15. Tạo ID không trùng và tạo business key duy nhất là hai bài toán khác

### 15.1. ID ngẫu nhiên không phải constraint cho email

UUID được thiết kế để giảm xác suất va chạm, thường rất hữu ích cho ID bản ghi phân tán. Nhưng dù hai user được tạo với UUID khác nhau, chúng vẫn có thể mang cùng email.

~~~text
userId=UUID-A, email=an@example.com
userId=UUID-B, email=an@example.com
~~~

Nếu bất biến nghiệp vụ là email duy nhất, phải bảo vệ **email**, không phải chỉ dùng UUID.

### 15.2. ID tuần tự và cấp phát theo thứ tự

Một hệ cần số hóa đơn tăng dần có thể phải dùng sequence allocator hoặc bộ cấp phát ID có bảo đảm riêng. Điều đó khác với uniqueness của user-provided username:

- ID do hệ thống tạo có thể tránh tranh chấp bằng thuật toán/cấp phát.
- Username do người dùng chọn thì hai người có thể cùng muốn một giá trị, phải có người thắng và người thua.

Không nên dùng thuật toán tạo ID độc nhất để thay thế cơ chế tranh quyền sở hữu một tên nghiệp vụ.

### 15.3. Business key có thể thay đổi

`userId` thường bất biến, nhưng `emailCanonical` hoặc `usernameCanonical` có thể thay đổi. Khi user đổi email:

1. Giữ email mới bằng thao tác điều kiện.
2. Đổi trường email trong hồ sơ theo cơ chế đúng.
3. Giải phóng email cũ vào thời điểm an toàn.
4. Cập nhật các read model/search index phụ.
5. Phục hồi nếu một bước không thành công.

Nếu nguồn hỗ trợ transaction nguyên tử giữa các bản ghi liên quan, dùng transaction có thể đơn giản hóa; nếu không, cần giao thức chuyển quyền sở hữu với version và reconciliation. Không thể chỉ cập nhật trường email rồi hy vọng chỉ mục/bảng reservation tự theo kịp.

## 16. Ghi hai bản ghi khác nhau vẫn cần phân biệt quyền sở hữu và dữ liệu dẫn xuất

Một hệ có thể lưu:

~~~text
users_by_id:
    USER#U1 -> {emailCanonical: "an@example.com"}

users_by_email:
    EMAIL#an@example.com -> {userId: "U1"}
~~~

`users_by_email` đồng thời đóng vai trò **khóa bảo vệ** và đường tra cứu. Nhưng nếu nó chỉ được cập nhật bất đồng bộ như một read model từ event stream, tính duy nhất **không được bảo đảm tại thời điểm tạo**.

Ví dụ:

~~~text
T0: U1 được tạo trong users_by_id
T1: event cập nhật users_by_email chưa chạy
T2: U2 được tạo, đọc email index vẫn rỗng
T3: cả U1 và U2 cùng tồn tại
~~~

Muốn dùng `users_by_email` để quyết định uniqueness, thao tác claim phải chạy **trước hoặc trong cùng transaction** với bước tạo user, bằng conditional create có bảo đảm nguyên tử. Nếu nó chỉ là chỉ mục tìm kiếm/analytics bất đồng bộ thì không nên được xem là nơi ra quyết định cuối.

### 16.1. CQRS và read model không thay thế command-side invariant

Trong kiến trúc tách write model và read model, luồng ghi (command side) phải bảo vệ bất biến. Read model có thể được dùng để hiển thị “username có vẻ sẵn có” nhưng không được quyết định cuối cùng việc ai sở hữu username nếu nó có độ trễ đồng bộ.

Nguyên tắc:

> **Bất biến phải được kiểm tra tại điểm cam kết thay đổi**, trên dữ liệu và cơ chế nhất quán phù hợp, không dựa vào một bản sao đọc có thể cập nhật trễ.

## 17. Cạnh tranh xuyên nhiều vùng và những giới hạn phân tán

### 17.1. Hai vùng cùng tạo một khóa

Giả sử ứng dụng có hai vùng A và B đều nhận ghi. Mỗi vùng cho phép tạo username `an` khi ở bản sao địa phương chưa có.

~~~text
Region A                          Region B
   |                                 |
   | Check "an" = absent             | Check "an" = absent
   |                                 |
   | Create owner U1                 | Create owner U2
   |                                 |
   +-------- Replication later ------+
                    |
                    v
             Conflict detected
~~~

Nếu hai vùng nhận và xác nhận thao tác mà không cần đồng thuận/điều phối về khóa đó, hệ thống có thể không giữ được bất biến “không trùng tại bất kỳ thời điểm nào”.

Giải pháp tùy yêu cầu:

- Chọn **một vùng/partition authoritative** cho việc cấp username.
- Dùng database hoặc giao thức có bảo đảm unique/linearizable conditional create xuyên phạm vi cần bảo vệ.
- Định tuyến cùng một business key về cùng nơi quyết định.
- Hoặc thay đổi hợp đồng: cho phép giữ chỗ tạm và giải quyết xung đột, nếu nghiệp vụ thực sự chấp nhận.

Không có một tùy chọn “eventual consistency” nào tự bảo đảm uniqueness mạnh xuyên nhiều nơi ghi độc lập mà không có giao thức phù hợp.

### 17.2. Tradeoff khi một vùng không thể liên lạc

Nếu uniqueness toàn cầu là bắt buộc và mạng giữa hai vùng bị phân tách, hệ thống có thể cần **từ chối hoặc trì hoãn** thao tác tạo username ở vùng không thể xác nhận quyền sở hữu. Cho phép tất cả vùng tự tạo trong lúc mất liên lạc có thể tăng khả dụng trước mắt nhưng dẫn đến xung đột khi đồng bộ lại.

Đây là ví dụ cụ thể của việc lựa chọn giữa **tính đúng đắn của bất biến** và **khả năng chấp nhận yêu cầu trong điều kiện sự cố**.

### 17.3. Sharding và uniqueness theo namespace

Nếu username duy nhất trong tenant, có thể dùng tenant làm một phần định tuyến/khóa bảo vệ. Nếu username phải duy nhất toàn cầu, việc phân shard theo tenant có thể khiến cùng tên nằm ở các shard khác nhau. Cần có cơ chế bảo vệ global key tương ứng.

**Phạm vi nghiệp vụ quyết định phạm vi phối hợp.** Không nên thiết kế partition/shard key chỉ từ cân bằng tải rồi mới phát hiện các bất biến cần bảo vệ nằm trên nhiều nơi.

## 18. Unique constraint không thay cho giới hạn số lượng hoặc tính đúng của trạng thái

Ví dụ **mỗi tài khoản chỉ có tối đa 3 dự án**. Đây không phải một phép duy nhất đơn giản theo khóa tên. Hai request tạo dự án cạnh tranh có thể cùng thấy đang có 2 dự án:

~~~text
A: count projects -> 2
B: count projects -> 2
A: insert project P3
B: insert project P4
=> 4 dự án, vi phạm giới hạn
~~~

Đây cũng là TOCTOU, nhưng unique index trên `projectId` không giải quyết. Có thể cần:

- Cập nhật một aggregate/counter có điều kiện nguyên tử.
- Transaction kiểm tra và ghi trong phạm vi phù hợp.
- Cơ chế phân bổ slot cố định theo khóa `slot#1..3` với conditional create (nếu thiết kế đúng và quản lý release/retry).
- Hoặc workflow có bảo đảm khác.

Tương tự, “chỉ bán một ghế cho một người” có thể có khóa ghế duy nhất; còn “giảm tồn kho nhưng không âm” cần conditional decrement/transaction, không đơn giản là unique index.

Nhóm dữ liệu theo bất biến giúp ta nhận ra **cơ chế bảo vệ thích hợp với từng loại quy tắc**, chứ không chỉ thêm unique index khắp nơi.

## 19. Ví dụ hoàn chỉnh: API đăng ký username với MongoDB

### 19.1. Schema và chỉ mục

Giả sử có collection `users`; ID user là UUID dạng string và username đã chuẩn hóa phải duy nhất trong tenant:

```javascript
db.users.createIndex(
  { tenantId: 1, usernameCanonical: 1 },
  {
    unique: true,
    name: "uq_tenant_username"
  }
);
```

Một document:

```json
{
  "_id": "eae3b945-1518-4eea-9d02-b10c29db4762",
  "tenantId": "T1",
  "usernameDisplay": "An",
  "usernameCanonical": "an",
  "createdAt": "2026-11-14T08:30:00Z"
}
```

Đây là **JSON biểu diễn dữ liệu**, còn khi ghi thật có thể dùng kiểu BSON Date cho `createdAt`. Điều trọng yếu cho uniqueness là bộ khóa `tenantId` và `usernameCanonical`, không phải kiểu thời gian.

### 19.2. Logic tạo ở tầng dịch vụ

Ví dụ Java dùng MongoDB sync driver, mã khái niệm với `MongoCollection<Document>`. Trình bày các phần cốt lõi, giả sử người gọi đã có `tenantId`, `username` hợp lệ và có bộ phát `userId` ổn định cho thao tác.

```java
import com.mongodb.MongoWriteException;
import com.mongodb.ErrorCategory;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Date;

public final class UsernameRegistration {
    private final MongoCollection<Document> users;

    public UsernameRegistration(MongoCollection<Document> users) {
        this.users = users;
    }

    public String register(
            String tenantId,
            String usernameDisplay,
            String usernameCanonical,
            String userId) {

        Document user = new Document("_id", userId)
                .append("tenantId", tenantId)
                .append("usernameDisplay", usernameDisplay)
                .append("usernameCanonical", usernameCanonical)
                .append("createdAt", new Date());

        try {
            users.insertOne(user);
            return userId;
        } catch (MongoWriteException e) {
            if (e.getError().getCategory() == ErrorCategory.DUPLICATE_KEY) {
                // Cần xác định xung đột ID hay username tùy schema/index,
                // rồi xử lý trùng yêu cầu hay tên đã thuộc người khác.
                throw new IllegalStateException(
                        "Unique key conflict while registering user", e);
            }
            throw e;
        }
    }
}
```

Mẫu này minh họa **database là nơi quyết định xung đột**. Code thực tế cần thêm:

- Mapping rõ duplicate trên từng index thành lỗi nghiệp vụ/HTTP response.
- Idempotency key và quy tắc retry khi kết quả ghi không xác định.
- Validation/authorization theo tenant.
- Timeout, write concern và logging phù hợp.
- Nếu user còn phải tạo nhiều thực thể liên quan, giao dịch hoặc workflow khôi phục.
- Kiểm tra trạng thái sau lỗi network khi database có thể đã nhận ghi.

Không nên biến ví dụ này thành “bắt mọi exception rồi trả email đã tồn tại”; điều đó che giấu lỗi mạng và các sự cố không liên quan.

### 19.3. Có nên gọi `findOne` trước?

Có thể gọi để hiển thị gợi ý sớm, nhưng **không được dựa vào nó để bảo đảm bất biến**. Câu lệnh `insertOne` vẫn phải cạnh tranh trên unique index.

Một API rõ ràng có thể phản hồi:

| Kết quả | HTTP minh họa | Ý nghĩa |
|---|---:|---|
| Tạo thành công | 201 | Username đã được giữ và hồ sơ được tạo |
| Username thuộc request khác | 409 | Xung đột khóa nghiệp vụ |
| Payload không hợp lệ | 400/422 | Không hợp lệ theo hợp đồng API |
| Retry cùng idempotency key đã thành công | 200/201 theo hợp đồng | Trả lại cùng kết quả đã lưu |
| Trạng thái chưa xác định do mạng | 202 hoặc lỗi có retry policy rõ | Cần truy vấn trạng thái, không khẳng định thất bại |

Mã HTTP là ví dụ thiết kế API, không phải quy tắc duy nhất. Quan trọng là client biết **đã tạo**, **bị xung đột**, hay **chưa biết kết quả cuối cùng**.

## 20. Ví dụ đặt chỗ: uniqueness có thời hạn và thanh toán

Giả sử một sự kiện có ghế `A12`. Bất biến:

> Tại một thời điểm, không có hai booking `CONFIRMED` khác nhau cùng giữ `(eventId, seatId)`.

Một mô hình booking theo ID:

```json
{
  "bookingId": "B1",
  "eventId": "E1",
  "seatId": "A12",
  "userId": "U1",
  "state": "PENDING_PAYMENT"
}
```

Hai booking `PENDING_PAYMENT` có được phép tồn tại cùng ghế không? Nếu chỉ có một người được giữ tạm, cần bảo vệ ngay ở trạng thái hold. Nếu không, hai người có thể cùng đến bước thanh toán.

### 20.1. Mô hình khóa ghế

Một item bảo vệ:

```text
PK = EVENT#E1#SEAT#A12
ownerBookingId = B1
state = HELD
holdExpiresAt = ...
fencingVersion = 15
```

Một request đặt ghế mới chỉ được claim nếu chưa có owner hợp lệ theo điều kiện nguyên tử. Khi hết hạn, việc cấp lại phải đồng thời **tăng version/fencing** hoặc cách bảo vệ tương đương để booking cũ không xác nhận sau khi mất quyền.

### 20.2. Thanh toán đến muộn

Một race điển hình:

```text
T0: B1 giữ ghế A12
T1: B1 hết thời gian giữ
T2: Ghế được cấp cho B2
T3: Payment callback của B1 đến muộn
```

Nếu callback chỉ cập nhật `booking B1 -> CONFIRMED` mà không kiểm tra quyền giữ ghế còn hiệu lực, hệ thống có thể xác nhận cả B1 và B2.

Do đó, **ràng buộc duy nhất trên booking ID hoàn toàn không đủ**. Cần kiểm tra nguyên tử trạng thái ghế/owner/version hoặc dùng transaction phù hợp khi xác nhận. Nếu callback không thể xác nhận đúng, cần workflow hoàn tiền/đối soát theo nghiệp vụ.

Ví dụ này cho thấy **“duy nhất” thường gắn với trạng thái vòng đời và quan hệ sở hữu**, không chỉ là một cột.

## 21. Quan sát và kiểm thử race condition

Không thể phát hiện mọi lỗi cạnh tranh bằng cách gửi tuần tự vài request. Khi thiết kế một bất biến, cần mô tả **kết quả được phép khi nhiều client cùng cạnh tranh**.

### 21.1. Kiểm thử đồng thời cùng username

Một kịch bản:

1. Xóa dữ liệu thử hoặc chọn một tenant + username hoàn toàn mới.
2. Tạo 100 request với cùng `tenantId` và `usernameCanonical`.
3. Cho chúng bắt đầu gần đồng thời bằng một barrier.
4. Đếm số thao tác thực sự commit thành công.
5. Đọc trạng thái cuối cùng bằng cách phù hợp với consistency của nguồn.
6. Đảm bảo chỉ có một owner hợp lệ; các request khác bị xung đột hoặc trùng cùng idempotency operation theo hợp đồng.

Kỳ vọng với **100 operation khác nhau cạnh tranh cùng tên**:

```text
Số owner cuối cùng cho (tenantId, usernameCanonical): 1
Số operation tạo owner mới thành công:                 1
Các operation còn lại:                                conflict/đã xác minh không tạo thêm
```

Không nên buộc “chỉ một HTTP 201” nếu mô hình idempotency cho phép nhiều retry cùng một operation nhận lại cùng kết quả thành công. Cần phân biệt **số operation độc lập** với **số lần nhận response thành công**.

### 21.2. Kiểm thử cùng idempotency key

Gửi 20 lần cùng một request và cùng idempotency key trong lúc nhiều worker chạy.

Kỳ vọng:

- Tối đa một business effect.
- Mọi request thành công đều quy về cùng `userId` và nội dung.
- Dùng lại key với payload khác bị từ chối.
- Không tạo reservation treo vĩnh viễn sau lỗi.
- Sau crash/restart, hệ có thể khôi phục trạng thái.

### 21.3. Kiểm thử lỗi giữa các bước

Với reservation workflow:

| Thời điểm cố ý gây lỗi | Trạng thái có thể còn lại | Điều cần quan sát |
|---|---|---|
| Trước claim | Chưa có khóa | Retry có tạo đúng một owner? |
| Sau claim, trước profile | Reservation PENDING | Có worker hoàn tất/giải phóng an toàn? |
| Sau profile, trước activate | Profile tồn tại, claim chưa ACTIVE | Có khôi phục về trạng thái hợp lệ? |
| Sau commit, trước trả HTTP | Client không biết kết quả | Retry có nhận lại cùng owner? |
| Sau release, trước claim mới | Khóa sắp được tái cấp | Writer cũ có bị fencing chặn? |
| Đang sync read model | Search chưa có dữ liệu | Command side vẫn giữ uniqueness? |

### 21.4. Metric hữu ích

- Tỷ lệ duplicate-key/conditional-check failures.
- Số reservation ở `PENDING` và tuổi của reservation lâu nhất.
- Số retry và kết quả “unknown commit”.
- Thời gian hoàn tất đăng ký p95/p99.
- Số bản ghi orphan: claim có nhưng profile thiếu, hoặc profile có nhưng claim không khớp.
- Số trường hợp phát hiện hai owner cho cùng business key (phải là chỉ số cảnh báo nghiêm trọng).
- Tỷ lệ idempotency replay và mismatch request hash.
- Thời gian phản hồi khi vùng dữ liệu/broker bị sự cố.

Một hệ thống có lỗi xung đột nhiều không nhất thiết bị hỏng: đó có thể là dấu hiệu nhiều người muốn cùng một username. Cần phân biệt **xung đột hợp lệ được database từ chối** với **vi phạm bất biến đã xảy ra**.

## 22. Hướng thiết kế khi yêu cầu duy nhất thay đổi

### 22.1. Từ duy nhất toàn cục sang duy nhất trong tenant

Nếu trước đây username duy nhất toàn cục, chuyển sang unique theo cặp tenant + username có thể cho phép nhiều tenant giữ tên giống nhau. Cần:

- Xác định phạm vi định danh trong API và URL.
- Đổi index/reservation key.
- Kiểm tra mọi đường tra cứu cũ chỉ dựa trên username.
- Không để ứng dụng vô tình đăng nhập nhầm tenant.
- Đánh giá dữ liệu cũ và luồng chuyển đổi.

### 22.2. Từ phân biệt hoa thường sang không phân biệt

Nếu trước đây có cả `"An"` và `"an"` trong cùng tenant, tạo canonical field mới sẽ khiến hai giá trị trùng.

Cần quy trình phát hiện xung đột và chính sách giải quyết: mời đổi tên, giữ tên cho owner đã xác nhận hoặc quy tắc chuyển đổi có giải thích. Không tự động chạy migration ép cả hai vào cùng canonical key rồi hy vọng database xử lý.

### 22.3. Thêm soft delete và tái sử dụng username

Việc cho phép username được cấp lại thay đổi bất biến. Cần định nghĩa thời điểm thu hồi, xử lý restore và retry cũ. Hệ thống reservation/unique partial index phải phản ánh rõ trạng thái giữ tên.

### 22.4. Chuyển từ một vùng sang nhiều vùng ghi

Khi mở rộng multi-region, nếu username phải duy nhất toàn cầu, phải đánh giá lại nơi thực thi constraint. Một thiết kế hoạt động khi mọi ghi đến một database trung tâm chưa chắc giữ nguyên bảo đảm nếu chuyển sang hai bản sao nhận ghi độc lập.

**Thay đổi topology có thể thay đổi bảo đảm bất biến**, kể cả khi code API không đổi.

## 23. Những sai lầm thường gặp

**“Kiểm tra `exists()` trước insert là đủ.”** Sai khi có concurrent requests. Phép kiểm tra và tạo phải được bảo vệ nguyên tử.

**“Chỉ cần một UUID độc nhất cho user là email cũng duy nhất.”** Không. Khóa ID và business key là hai điều kiện khác nhau.

**“Đọc nhất quán mạnh trước khi ghi sẽ tự tránh race.”** Không mặc định; hai lượt đọc vẫn có thể cùng thấy giá trị cũ. Cần conditional write/unique constraint hoặc transaction phù hợp.

**“Upsert luôn tương đương insert-if-absent.”** Không. Upsert có thể cập nhật tài liệu đã có và cần unique key, filter cùng xử lý race đúng.

**“Bắt duplicate-key rồi luôn trả yêu cầu đã thành công.”** Sai. Xung đột có thể thuộc về một người khác; cần so owner và idempotency operation.

**“Secondary index hoặc search index đã đủ bảo vệ uniqueness.”** Không nếu index chỉ để truy vấn hoặc cập nhật bất đồng bộ và không cung cấp constraint.

**“Một LWT hoặc conditional write tự làm mọi bảng nhất quán.”** Không. Nó bảo vệ trong phạm vi được định nghĩa; cập nhật nhiều thực thể cần transaction/workflow riêng.

**“Đặt Redis lock trước khi ghi database là chắc chắn không trùng.”** Không nếu lock hết hạn, failover hoặc không có fencing/bảo đảm tại nơi ghi.

**“TTL hết hạn là claim chắc chắn đã được thu hồi an toàn.”** Không; cần xét thời điểm xóa thật và worker cũ vẫn có thể hoàn tất.

**“Transaction là đủ dù nghiệp vụ được quyết định từ một read model cập nhật chậm.”** Không. Transaction phải kiểm tra ràng buộc trên nguồn authoritative hoặc khóa bảo vệ đúng, không chỉ dùng kết quả đọc không đảm bảo.

**“Hai vùng cùng chấp nhận tạo rồi sẽ đồng bộ mà không có xung đột.”** Không nếu không có phối hợp và cùng business key.

**“Uniqueness luôn áp dụng cho mọi bản ghi lịch sử.”** Không nhất thiết; có thể áp dụng theo tenant, trạng thái hoạt động hoặc thời hạn. Phạm vi cần được định nghĩa rõ.

## 24. Bài tập vận dụng

### Bài tập 1: tìm race

Hai request đồng thời tạo người dùng với email giống nhau:

```text
A: findByEmail -> null
B: findByEmail -> null
A: insert User U1
B: insert User U2
```

**Câu hỏi:** Tại sao hai request đều có thể thành công? Cách sửa nào tốt hơn việc thêm một lệnh `findByEmail` nữa?

**Gợi ý:** Cả hai phép kiểm tra có thể chạy trước bất kỳ thao tác ghi nào. Cần unique index trên email canonical hoặc conditional create ở khóa bảo vệ email, tùy database.

### Bài tập 2: chọn phạm vi

Mỗi tenant được phép có username `admin`, nhưng trong cùng tenant chỉ một tài khoản được dùng `admin`.

**Câu hỏi:** Khóa duy nhất nên là `usernameCanonical` hay cặp `(tenantId, usernameCanonical)`?

**Gợi ý:** Cặp `(tenantId, usernameCanonical)` vì uniqueness theo tenant. Khóa chỉ chứa username sẽ cấm các tenant khác sử dụng cùng tên ngoài yêu cầu.

### Bài tập 3: thay đổi trạng thái

Hệ thống lưu username với `state = ACTIVE` hoặc `DELETED`. Username được phép cấp lại khi user đã `DELETED`.

**Câu hỏi:** Partial unique index chỉ trên `ACTIVE` đã đủ chưa nếu còn trạng thái `PENDING_REGISTRATION` giữ chỗ tên?

**Gợi ý:** Chưa đủ nếu `PENDING_REGISTRATION` cũng phải giữ tên. Cần điều kiện unique bao phủ mọi trạng thái giữ quyền sở hữu hoặc reservation riêng.

### Bài tập 4: lựa chọn DynamoDB key

Bảng `Users` dùng `PK = USER#userId`. Một GSI cho phép tìm theo `emailCanonical`.

**Câu hỏi:** Vì sao không thể chỉ query GSI rồi `PutItem USER#newId` để bảo đảm email duy nhất?

**Gợi ý:** GSI không phải unique constraint và không nguyên tử hóa truy vấn với PutItem. Cần item bảo vệ `EMAIL#canonical` với conditional write, có thể dùng transaction để tạo profile cùng claim.

### Bài tập 5: Cassandra LWT

Cassandra có bảng:

```sql
CREATE TABLE users_by_id (
  user_id uuid PRIMARY KEY,
  email text
);
```

Ứng dụng chạy `INSERT ... IF NOT EXISTS` theo `user_id`.

**Câu hỏi:** Cách đó đã bảo vệ email duy nhất chưa?

**Gợi ý:** Chưa. LWT bảo vệ sự tồn tại của `user_id`, không bảo vệ hai bản ghi khác user ID có cùng email. Cần khóa bảo vệ theo email hoặc mô hình/constraint khác đúng phạm vi.

### Bài tập 6: timeout sau khi commit

Một request giữ tên `an` với `ownerUserId = U1`, nhưng client timeout. Retry thấy tên đã tồn tại.

**Câu hỏi:** Có nên báo ngay “tên thuộc người khác” không?

**Gợi ý:** Cần đối chiếu owner/operationId. Nếu tên do chính request U1 giữ, tiếp tục trả kết quả idempotent hoặc hoàn tất workflow. Nếu owner khác, mới là conflict thực sự.

### Bài tập 7: số lượng dự án

Mỗi tenant được tạo tối đa 5 dự án. Hai request cạnh tranh cùng đọc `count=4` rồi tạo dự án khác ID.

**Câu hỏi:** Unique index trên `projectId` giải quyết được không?

**Gợi ý:** Không. Bất biến liên quan đến giới hạn số lượng; cần conditional counter/slot/transaction phù hợp với phạm vi tenant.

### Bài tập 8: multi-region

Hai region A và B cùng tiếp nhận đăng ký `globalUsername = "an"` ngay khi mất kết nối với nhau. Mỗi region chấp nhận một user mới.

**Câu hỏi:** Kết quả có thể vi phạm bất biến gì? Muốn giữ duy nhất toàn cầu thì cần thay đổi gì?

**Gợi ý:** Có thể có hai owner của cùng username. Cần một điểm quyết định tuần tự/conditional create toàn cầu hoặc giao thức nhất quán phù hợp; một vùng có thể phải trì hoãn/từ chối request khi không thể xác nhận quyền sở hữu.

### Bài tập 9: cách xử lý duplicate event

Một request tạo user được gửi lại 5 lần với cùng `idempotencyKey`. Một request khác đến với key khác nhưng cùng email.

**Câu hỏi:** Kết quả đúng của hai nhóm request là gì?

**Gợi ý:** Năm lần gửi cùng operation nên quy về một kết quả user. Operation khác cùng email phải bị từ chối nếu người đầu đã giành quyền sở hữu, không được xem là retry của người đầu.

### Bài tập 10: reservation hết hạn

User U1 giữ một ghế trong 3 phút. Sau 3 phút, U2 giữ ghế; callback thanh toán của U1 đến sau.

**Câu hỏi:** Cần kiểm tra gì trước khi xác nhận U1?

**Gợi ý:** Xác nhận phải kiểm tra owner hiện tại, trạng thái hold và version/fencing token theo điều kiện nguyên tử. Không thể chỉ dựa vào việc callback là thanh toán “thành công”.

## 25. Kết luận

**Tính duy nhất là một bất biến phải được bảo vệ tại thời điểm thay đổi trạng thái được cam kết**, không phải chỉ là một truy vấn `exists()` trước khi tạo. Khi nhiều request chạy cạnh tranh, thao tác “đọc không thấy rồi insert” không nguyên tử có thể tạo hai bản ghi vi phạm quy tắc dù từng request riêng lẻ trông hợp lý.

Trong NoSQL, cách bảo vệ phụ thuộc vào **phạm vi khóa nghiệp vụ và bảo đảm của sản phẩm**: unique index trong document database, conditional put trong item/key–value store, `IF NOT EXISTS`/LWT trong wide-column, transaction phù hợp hoặc một khóa reservation authoritative. Cần phân biệt uniqueness theo ID với uniqueness của email/username, phân biệt cơ chế bảo vệ một key với giao dịch nhiều thực thể, và phân biệt đọc phụ trợ với nơi quyết định cuối cùng.

Thiết kế hoàn chỉnh còn phải xử lý **chuẩn hóa khóa, duplicate-key, retry không biết kết quả, idempotency, đổi tên, xóa/tái cấp quyền sở hữu, multi-region và sự cố giữa các bước**. Khi những yêu cầu cạnh tranh đều bị buộc phải đi qua một điều kiện kiểm tra–ghi nguyên tử trên đúng khóa bảo vệ, hệ thống mới có cơ sở tin cậy để giữ bất biến “chỉ một người được tạo hoặc sở hữu giá trị này”, kể cả trong lúc tải cao và lỗi mạng.

