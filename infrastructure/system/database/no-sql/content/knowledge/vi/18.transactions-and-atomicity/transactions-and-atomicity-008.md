# Đọc-sửa-ghi tại ứng dụng và nguy cơ ghi đè cập nhật

Trong một ứng dụng NoSQL, nhiều thao tác cập nhật được viết theo một chuỗi có vẻ rất tự nhiên: **đọc bản ghi hiện tại, thay đổi giá trị trong ứng dụng, rồi ghi kết quả trở lại database**. Mẫu này gọi là *read–modify–write* (RMW), hay **đọc–sửa–ghi**. Nó thường xuất hiện khi tăng bộ đếm, giảm tồn kho, sửa thông tin khách hàng, thêm sản phẩm vào giỏ, đổi trạng thái đơn hàng hoặc giữ chỗ.

Với một request chạy riêng lẻ, RMW thường hoạt động. Nhưng hai request có thể cùng đọc một giá trị cũ, cùng tính ra kết quả mới rồi lần lượt ghi. Khi đó **một cập nhật có thể bị mất**, dù mỗi câu lệnh database riêng lẻ đều được thực thi nguyên tử.

Điều này đặc biệt quan trọng với NoSQL vì các hệ có **ranh giới nguyên tử khác nhau**: một document trong MongoDB, một item trong DynamoDB, một conditional operation trên partition theo khả năng Cassandra, hoặc những lệnh và transaction của Redis. Việc chọn đúng khóa dữ liệu chưa đủ; phải thiết kế **điều kiện ghi và quy tắc xử lý cạnh tranh**.

Bài học sẽ giải thích lỗi *lost update*, cơ chế cập nhật nguyên tử, *compare-and-set* (CAS), *optimistic locking*, idempotency, transaction và workflow nhiều dịch vụ. Các ví dụ tập trung vào MongoDB, DynamoDB, Cassandra/CQL và Redis, đồng thời liên hệ tới Java và kiểm thử đồng thời.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, bạn có thể:

1. Vẽ được dòng thời gian gây lost update trong chuỗi đọc–sửa–ghi.
2. Phân biệt lost update với stale read, write skew, duplicate execution và ABA.
3. Viết cập nhật nguyên tử có điều kiện cho counter, tồn kho và trạng thái nghiệp vụ.
4. Sử dụng version/CAS để từ chối những thay đổi dựa trên dữ liệu đã cũ.
5. Xử lý conflict, timeout và retry mà không tạo tác động trùng.
6. Hiểu giới hạn của thao tác một item/document so với transaction nhiều item và nhiều dịch vụ.
7. Thiết kế kiểm thử đồng thời để xác nhận **bất biến nghiệp vụ** chứ không chỉ giá trị cuối.

## 2. Bài toán xuyên suốt: hai khách mua sản phẩm cuối cùng

Giả sử nguồn dữ liệu tồn kho chứa:

~~~json
{
  "tenantId": "merchant-a",
  "sku": "SKU-7",
  "available": 1,
  "version": 12
}
~~~

Hai khách A và B cùng bấm mua một sản phẩm. Code ứng dụng kiểu RMW:

~~~java
Inventory current = repository.findBySku("SKU-7");

if (current.available() >= 1) {
    repository.saveAvailable("SKU-7", current.available() - 1);
    return "RESERVED";
}
return "OUT_OF_STOCK";
~~~

Nếu A chạy xong trước khi B đọc:

~~~text
A đọc 1 -> ghi 0 -> RESERVED
B đọc 0 -> OUT_OF_STOCK
~~~

Nhưng khi hai request xen kẽ:

~~~text
Thời điểm    Request A                       Request B
---------    ----------------------------    ----------------------------
t1           READ available = 1
t2                                            READ available = 1
t3           Kiểm tra 1 >= 1: đúng
t4                                            Kiểm tra 1 >= 1: đúng
t5           WRITE available = 0
t6                                            WRITE available = 0
t7           Trả RESERVED
t8                                            Trả RESERVED

Kết quả: available = 0, nhưng có hai khách được xác nhận giữ hàng.
~~~

Điều nguy hiểm là **stock không âm**, nên một phép kiểm tra chỉ nhìn `available >= 0` có thể bỏ sót lỗi. Bất biến thực sự cần kiểm tra là **số lượng hàng được xác nhận giữ không vượt lượng hàng có thể cung cấp**.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Inventory DB
    participant B as Request B
    A->>DB: GET available
    DB-->>A: 1
    B->>DB: GET available
    DB-->>B: 1
    A->>A: Tính 1 - 1 = 0
    B->>B: Tính 1 - 1 = 0
    A->>DB: SET available = 0
    DB-->>A: OK
    B->>DB: SET available = 0
    DB-->>B: OK
    Note over A,B: Hai ý định được xác nhận dù chỉ có một sản phẩm
~~~

**Nguyên nhân:** điều kiện “còn hàng” và hành động “giữ hàng” không được kiểm tra/thực hiện trong cùng một ranh giới nhất quán.

## 3. Lost update: một lần thay đổi biến mất

Ví dụ tăng bộ đếm:

~~~text
counter ban đầu = 10

A đọc 10
B đọc 10
A tính 11
B tính 11
A ghi 11
B ghi 11

counter cuối = 11
mong muốn = 12
~~~

**Lost update** là việc một tác động ghi bị ghi đè hoặc không được tích lũy vì các writer dùng cùng giá trị cũ. Nếu hệ thống dùng quy tắc chọn giá trị theo thời gian ghi (*last-write-wins*), database có thể nhất quán về **giá trị cuối** nhưng không bảo toàn đủ **ý định tăng** của cả hai request.

### 3.1. Một lệnh ghi nguyên tử không làm cả chuỗi nguyên tử

Trong MongoDB, một thao tác `updateOne` trên một document có bảo đảm nguyên tử thích hợp. Tuy nhiên chuỗi:

~~~text
findOne
  ... tính toán trong service ...
updateOne
~~~

gồm **hai lần làm việc với database**. Request khác vẫn có thể chen vào sau `findOne` và trước `updateOne`. Điều tương tự xảy ra với DynamoDB `GetItem + PutItem`, Cassandra `SELECT + UPDATE`, Redis `GET + SET`.

### 3.2. Ghi đè toàn bộ document còn nguy hiểm hơn

Ban đầu:

~~~json
{
  "userId": "U42",
  "displayName": "Lan",
  "email": "lan@example.test",
  "version": 4
}
~~~

Hai người cùng đọc version 4:

- A sửa tên thành **Lan Anh**.
- B sửa email thành **new@example.test**.

Nếu cả hai tải về rồi ghi lại toàn bộ document bằng bản chụp đã sửa một field, B có thể vô tình ghi `displayName = "Lan"` trở lại, làm mất thay đổi của A.

Đôi khi chỉ cập nhật đúng field bằng phép patch/`$set` thay cho *replace whole document* sẽ tránh ghi đè **những trường thật sự độc lập**. Nhưng nếu field mới **phụ thuộc vào những field khác đã đọc**, vẫn phải phát hiện dữ liệu đã thay đổi.

## 4. Phân biệt các lỗi đồng thời

| Hiện tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Lost update** | Một cập nhật bị mất do ghi từ snapshot cũ | Hai lần tăng cho ra +1 |
| **Stale read** | Đọc trạng thái chưa mới nhất ở nguồn có thẩm quyền | Cache vẫn báo stock 5 |
| **Dirty read** | Đọc thay đổi chưa commit mà có thể rollback | Phụ thuộc isolation của engine |
| **Non-repeatable read** | Đọc lại entity trong cùng chuỗi logic thấy giá trị khác | Giá đổi giữa hai lần đọc |
| **Write skew** | Hai transaction ghi entity khác nhau, cùng vi phạm một ràng buộc | Hai nhân viên cùng rời ca trực |
| **Duplicate execution** | Một ý định được thực thi nhiều lần vì retry | Trừ stock hai lần sau timeout |
| **ABA** | Giá trị thay đổi A→B→A, việc so giá trị cuối không phát hiện vòng thay đổi | READY→CANCELLED→READY |

### 4.1. Write skew khác lost update

Giả sử hệ thống trực ca có luật **phải còn ít nhất một bác sĩ trực**:

~~~text
Doctor A: ON_DUTY
Doctor B: ON_DUTY

TA đọc cả hai: thấy B trực, cho A nghỉ.
TB đọc cả hai: thấy A trực, cho B nghỉ.

TA sửa record A -> OFF_DUTY
TB sửa record B -> OFF_DUTY
~~~

Hai transaction **ghi trên hai document khác nhau**, nên CAS riêng từng document có thể đều thành công. Sau cùng không ai trực.

Điều này minh họa rằng **nguyên tử trên từng item/document chưa đủ cho bất biến đa item**. Ngay cả transaction có snapshot isolation không phải lúc nào cũng ngăn write skew nếu thiếu cơ chế tạo xung đột hoặc ràng buộc phù hợp.

### 4.2. Stale read có thể trở thành lỗi ghi

Đọc một search index chậm vài giây để hiển thị là vấn đề độ mới. Nhưng nếu từ giá trị cache cũ mà ứng dụng quyết định giữ hàng rồi ghi không điều kiện, **stale read đã trở thành đầu vào gây ghi sai**.

Điều kiện ghi trên nguồn có thẩm quyền mới là điểm kiểm soát quan trọng, không phải giả định rằng mọi replica đều có dữ liệu mới nhất.

## 5. Xác định bất biến trước khi chọn công nghệ

Mỗi thao tác cần nêu câu hỏi **điều gì phải luôn đúng**:

| Thao tác | Bất biến | Hướng bảo vệ |
| --- | --- | --- |
| Tăng lượt xem | Mỗi ý định được tính theo chính sách đã chọn | Atomic increment và retry semantics |
| Giữ hàng | Không giữ vượt stock sẵn có | Conditional decrement + idempotency |
| Chuyển trạng thái đơn | Chỉ chuyển từ trạng thái hợp lệ | Conditional update/state machine |
| Sửa hồ sơ | Không vô tình mất bản sửa của người khác | Field patch hoặc version/CAS |
| Dùng voucher một lần | Một mã chỉ redeem theo giới hạn | Unique/conditional write + transaction nếu cần |
| Tạo Order và Reservation | Không có reservation/stock mồ côi | Transaction hoặc workflow phục hồi được |
| Nhận callback thanh toán | Một giao dịch không bị ghi nhận hai lần | Event/request ID và ledger có thẩm quyền |

**Không có một phương án duy nhất** cho mọi tình huống. Phép cộng đồng thời đơn giản khác rất xa cập nhật một ràng buộc xuyên nhiều dịch vụ.

## 6. Giải pháp 1: đưa phép sửa vào một thao tác nguyên tử

Thay vì:

~~~text
READ available=10
COMPUTE newAvailable=8
WRITE available=8
~~~

cần biểu diễn ý định:

~~~text
IF available >= 2:
    available := available - 2
ELSE:
    refuse
~~~

Database có thể thực hiện điều kiện cùng mutation trong **một thao tác nguyên tử** theo khả năng tương ứng.

Với increment đơn giản, một atomic `INCREMENT` tránh lost update do hai lần RMW tách rời. Với tồn kho, cần **điều kiện không âm** trong cùng thao tác. Với nhiều item khác nhau, cần xem engine có transaction phù hợp hay không.

### 6.1. Atomicity không đồng nghĩa idempotency

Một request `stock -= 1` có thể được thực thi nguyên tử. Nhưng khi response mất và client gửi lại **cùng request**, database có thể trừ tiếp lần thứ hai. Bảo đảm **không mất update khi có nhiều request khác nhau** và bảo đảm **một ý định chỉ áp một lần** là hai vấn đề riêng.

## 7. MongoDB: `$inc` và filter có điều kiện

MongoDB hỗ trợ nguyên tử trên một document cho mutation thích hợp. Ví dụ tồn kho:

~~~javascript
{
  tenantId: "merchant-a",
  sku: "SKU-7",
  available: 10,
  version: 7
}
~~~

### 7.1. Mẫu RMW không an toàn

~~~javascript
const item = db.inventory.findOne({
  tenantId: "merchant-a",
  sku: "SKU-7"
});

if (item.available >= 2) {
  db.inventory.updateOne(
    { tenantId: "merchant-a", sku: "SKU-7" },
    { $set: { available: item.available - 2 } }
  );
}
~~~

`item.available` được đọc **trước** mutation, nên có thể đã cũ khi lệnh `updateOne` chạy.

### 7.2. Conditional atomic decrement

~~~javascript
db.inventory.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);

const qty = 2;
const result = db.inventory.updateOne(
  {
    tenantId: "merchant-a",
    sku: "SKU-7",
    available: { $gte: qty }
  },
  {
    $inc: { available: -qty },
    $currentDate: { updatedAt: true }
  }
);

if (result.modifiedCount === 1) {
  print("RESERVED");
} else {
  print("NOT_RESERVED");
}
~~~

Điều kiện `available >= qty` được đánh giá cùng thao tác cập nhật document. Hai request cạnh tranh không thể cùng trừ vượt mức stock còn lại **nếu tất cả writer cùng tuân theo cơ chế bảo vệ này**.

Các điểm cần lưu ý:

- Unique index giúp bảo đảm một bản ghi tồn kho trên mỗi cặp tenant/SKU, nhưng điều kiện routing/shard key cần phù hợp với cấu hình sharding.
- `modifiedCount=0` có thể nghĩa là **không có SKU** hoặc **không đủ hàng**; cần xử lý trạng thái trả về phù hợp.
- Một lệnh có thể throw exception hoặc timeout; phải phân biệt lỗi hạ tầng với kết quả nghiệp vụ.
- `$inc` không tự bảo vệ khỏi **retry cùng ý định** sau khi update đã commit.
- `$currentDate` dùng để ghi thời gian, không phải cơ chế concurrency version.

### 7.3. State transition có điều kiện

Quy tắc nghiệp vụ:

~~~text
CREATED -> PAID -> READY_TO_SHIP -> SHIPPED
                     |
                     +-> CANCELLED (khi còn đủ điều kiện)
~~~

Thay vì:

~~~javascript
db.orders.updateOne(
  { orderId: "O900" },
  { $set: { status: "SHIPPED" } }
);
~~~

hãy ghi với điều kiện nguồn đang ở trạng thái cho phép:

~~~javascript
const result = db.orders.updateOne(
  {
    tenantId: "merchant-a",
    orderId: "O900",
    status: "READY_TO_SHIP"
  },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 },
    $currentDate: { updatedAt: true }
  }
);
~~~

Nếu một request khác đã hủy hoặc đổi trạng thái đơn trước, điều kiện không còn khớp. API phải phân loại **đơn không tồn tại, không có quyền, trạng thái không hợp lệ hoặc đã được xử lý**.

## 8. Giải pháp 2: optimistic locking bằng version/CAS

**Optimistic concurrency control** cho phép chuẩn bị thay đổi dựa trên snapshot, nhưng **chỉ ghi nếu snapshot vẫn còn hiệu lực**.

Một document:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "status": "PAID",
  "shippingAddress": "Địa chỉ A",
  "version": 7
}
~~~

Client đọc version 7 và muốn sửa địa chỉ:

~~~javascript
const result = db.orders.updateOne(
  {
    tenantId: "merchant-a",
    orderId: "O900",
    version: 7,
    status: "PAID"
  },
  {
    $set: { shippingAddress: "Địa chỉ B" },
    $inc: { version: 1 },
    $currentDate: { updatedAt: true }
  }
);

if (result.modifiedCount !== 1) {
  print("CONFLICT_OR_NOT_ALLOWED");
}
~~~

Nếu writer khác cập nhật Order và tăng version lên 8, request này **không ghi đè dựa trên version 7**.

### 8.1. Vì sao tăng version cùng thao tác?

Không nên:

~~~text
1. UPDATE shippingAddress
2. UPDATE version
~~~

vì có thể crash giữa hai bước và để lại nội dung mới với version cũ. Trong một document, `$set` và `$inc` trong cùng update cho phép cập nhật nội dung và version trong một thao tác.

### 8.2. Version không phải timestamp

`updatedAt` có độ phân giải hữu hạn, có thể trùng giữa hai mutation hoặc chịu ảnh hưởng clock. `version` là token logic để nhận biết **entity đã bị thay đổi kể từ lần đọc**. Mọi writer cần tăng version theo quy ước; nếu một đường import ghi thẳng mà không tăng version, OCC mất hiệu lực.

### 8.3. Cập nhật đúng field hay từ chối cả document?

Nếu A đổi tên và B đổi ngôn ngữ giao diện, cả hai update field riêng và độc lập có thể cùng hợp lệ. Dùng một version cho toàn document sẽ tạo **conflict bảo thủ** khi B sửa sau A.

Tuy nhiên khi nhiều field cùng tạo thành một ràng buộc (ví dụ địa chỉ gồm đường/phường/thành phố), không nên tự trộn nửa dữ liệu của A với nửa của B. Cần xem các field như một **đơn vị logic** hoặc yêu cầu người dùng giải quyết xung đột.

### 8.4. `findOneAndUpdate`

Nếu cần dữ liệu ngay sau mutation:

~~~javascript
const updated = db.orders.findOneAndUpdate(
  {
    tenantId: "merchant-a",
    orderId: "O900",
    version: 7
  },
  {
    $set: { shippingAddress: "Địa chỉ B" },
    $inc: { version: 1 }
  },
  { returnDocument: "after" }
);
~~~

Kết quả null/không có document khớp điều kiện cần được xử lý như conflict hoặc not-found. Một lệnh này không tự giao dịch với các bản ghi/ứng dụng khác.

## 9. DynamoDB: ConditionExpression trên cùng UpdateItem

DynamoDB có conditional writes cho một item. Một `UpdateItem` có thể kiểm tra version, tồn kho rồi cập nhật trong **một yêu cầu**.

Item minh họa:

~~~json
{
  "tenantId": "merchant-a",
  "sku": "SKU-7",
  "available": 10,
  "version": 7
}
~~~

Ví dụ Python/boto3:

~~~python
import boto3
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table("Inventory")

quantity = 2
expected_version = 7

try:
    response = table.update_item(
        Key={"tenantId": "merchant-a", "sku": "SKU-7"},
        UpdateExpression=(
            "SET available = available - :qty, "
            "#ver = #ver + :one"
        ),
        ConditionExpression=(
            "attribute_exists(available) "
            "AND available >= :qty "
            "AND #ver = :expected"
        ),
        ExpressionAttributeNames={"#ver": "version"},
        ExpressionAttributeValues={
            ":qty": quantity,
            ":one": 1,
            ":expected": expected_version,
        },
        ReturnValues="ALL_NEW",
    )
    print("UPDATED", response["Attributes"])
except ClientError as exc:
    code = exc.response["Error"]["Code"]
    if code == "ConditionalCheckFailedException":
        print("CONFLICT_OR_INSUFFICIENT_STOCK")
    else:
        raise
~~~

Trong ví dụ, table cần key schema đúng như `tenantId + sku` và các field Number tồn tại với kiểu phù hợp.

### 9.1. Tại sao kiểm tra condition trong cùng lệnh?

Hai request đều đọc version 7. Request A cập nhật lên 8; request B gửi với `#ver = :expected` vẫn bằng 7 sẽ **thất bại có điều kiện**. Không có khoảng chen giữa khi kiểm tra condition và cập nhật item.

### 9.2. Khi nào bỏ expectedVersion?

Nếu nghiệp vụ chỉ yêu cầu **trừ stock miễn còn đủ**, các reservation độc lập có thể dùng:

~~~text
SET available = available - qty
CONDITION available >= qty
~~~

thay vì bắt tất cả client mang expectedVersion từ một lần đọc trước. Điều này có thể giảm conflict không cần thiết. Với **sửa nội dung dựa trên một bản form cũ**, version lại có giá trị vì người dùng cần biết bản ghi đã thay đổi.

### 9.3. Condition failed khác lỗi hạ tầng

- `ConditionalCheckFailedException`: không đạt điều kiện, có thể là conflict hoặc hết hàng.
- Throttling/lỗi tạm thời: áp retry và backoff theo hướng dẫn/giới hạn thích hợp.
- Timeout/unknown outcome: mutation có thể đã thực thi; phải xác minh hoặc dùng idempotency, **không tự trừ lại**.

Không retry vô hạn mọi lỗi như nhau.

## 10. Cassandra/CQL: lightweight transaction và CAS

Cassandra có cơ chế conditional update thường gọi là **lightweight transaction (LWT)**. Đây là cách thực hiện CAS trên dữ liệu trong phạm vi engine hỗ trợ, với chi phí phối hợp cao hơn ghi thông thường.

Tạo bảng tồn kho:

~~~sql
CREATE TABLE inventory_by_sku (
    tenant_id text,
    sku text,
    available int,
    version bigint,
    PRIMARY KEY ((tenant_id, sku))
);
~~~

Đọc:

~~~sql
SELECT available, version
FROM inventory_by_sku
WHERE tenant_id = 'merchant-a'
  AND sku = 'SKU-7';
~~~

Giả sử kết quả là `available=10, version=7`. Ứng dụng tính giá trị mới là 8 và gửi:

~~~sql
UPDATE inventory_by_sku
SET available = 8,
    version = 8
WHERE tenant_id = 'merchant-a'
  AND sku = 'SKU-7'
IF version = 7 AND available = 10;
~~~

Nếu request khác đã ghi thay đổi, CAS có thể trả `[applied] = false` (và thông tin hiện tại theo cơ chế driver/CQL). Worker phải xử lý bằng đọc lại rồi quyết định **ý định còn hợp lệ không**.

### 10.1. Vì sao không dùng arithmetic update tùy ý?

Với cột số **thường** trong CQL, không được giả định cú pháp:

~~~sql
-- Không phải kiểu UPDATE số nguyên thường có thể dùng tùy ý:
UPDATE inventory_by_sku
SET available = available - 2
WHERE tenant_id = 'merchant-a' AND sku = 'SKU-7';
~~~

Cassandra không phải một SQL engine hỗ trợ mọi biểu thức số học trên cột thường. **Counter columns** có ngữ nghĩa riêng; tăng counter không tự bảo vệ `available >= 2` hoặc idempotency khi request bị retry.

### 10.2. Chi phí LWT

Conditional mutation cần phối hợp phiên bản/đồng thuận theo cơ chế hệ thống, vì vậy thường có latency và mức tranh chấp cao hơn ghi thông thường. Với **SKU rất nóng**, nhiều request có thể thất bại rồi retry, gây tải tăng và p99 xấu.

Phải đo:

- Tỷ lệ CAS thành công/thất bại.
- Latency p95/p99 của LWT.
- Tần suất retry theo SKU.
- Contention/hot partition.
- Hiệu quả của phương án phân bổ stock theo kho/shard, nếu nghiệp vụ cho phép.

### 10.3. Không mặc định CQL BATCH là transaction tổng quát

`BEGIN BATCH ... APPLY BATCH` có các bảo đảm và giới hạn riêng. Một batch qua nhiều partition **không thay thế tùy ý transaction có isolation bảo vệ mọi invariant đa entity**. Thiết kế cần bám đúng phạm vi CAS/transaction của engine và phiên bản đang dùng.

## 11. Redis: WATCH/MULTI/EXEC

Trong Redis, mỗi lệnh `GET` hoặc `SET` riêng lẻ không bị chen giữa trong lúc chính lệnh đó thực thi; nhưng:

~~~text
GET stock:SKU-7
... xử lý trong ứng dụng ...
SET stock:SKU-7 8
~~~

vẫn có cửa sổ xung đột. Redis cung cấp `WATCH` để quan sát thay đổi trước khi thực thi transaction:

~~~text
WATCH stock:SKU-7
GET stock:SKU-7
MULTI
SET stock:SKU-7 8
EXEC
~~~

Nếu key bị thay đổi sau WATCH và trước EXEC, transaction có thể bị hủy theo ngữ nghĩa WATCH/EXEC.

### 11.1. Ví dụ Python với redis-py

~~~python
import redis
from redis.exceptions import WatchError

r = redis.Redis(host="localhost", port=6379, decode_responses=True)


def reserve(key: str, quantity: int, max_attempts: int = 5) -> bool:
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    for _ in range(max_attempts):
        with r.pipeline() as pipe:
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if raw is None:
                    pipe.unwatch()
                    return False

                current = int(raw)
                if current < quantity:
                    pipe.unwatch()
                    return False

                pipe.multi()
                pipe.set(key, current - quantity, keepttl=True)
                pipe.execute()
                return True
            except WatchError:
                # Có writer chen vào, thử lại với snapshot mới.
                continue

    raise RuntimeError("Too much contention; retry later")
~~~

Trong code này, `WATCH` phát hiện key đã đổi; request retry có giới hạn để tránh tranh chấp vô tận. `keepttl=True` giữ TTL hiện có nếu key có hạn; bỏ lựa chọn này nếu không thích hợp với chính sách vòng đời.

**WATCH/CAS không bảo đảm chống retry cùng ý định sau khi EXEC thành công mà response bị mất**. Cần request ID và dedup state ở cấp nghiệp vụ.

### 11.2. Lua: check và decrement trong một script

Một lựa chọn khác:

~~~lua
-- KEYS[1] là stock key.
-- ARGV[1] là số lượng cần giữ.
local qty = tonumber(ARGV[1])
if not qty or qty <= 0 then
    return redis.error_reply("INVALID_QUANTITY")
end

local raw = redis.call("GET", KEYS[1])
if not raw then
    return 0
end

local current = tonumber(raw)
if not current or current < qty then
    return 0
end

redis.call("DECRBY", KEYS[1], qty)
return 1
~~~

Lệnh khác không chen giữa các bước của script theo cơ chế Redis. Tuy nhiên **Lua script không cung cấp rollback tự động cho mọi mutation đã làm trước khi phát sinh lỗi**; cần validate đầu vào và điều kiện trước khi mutate, nhất là script nhiều key. Redis Cluster còn có quy tắc hash slot đối với script/transaction nhiều key.

### 11.3. Redis không thể commit chung với MongoDB

Nếu Redis chỉ là cache, còn tồn kho chuẩn ở MongoDB, script Redis thành công **không tự bảo đảm** MongoDB đã cập nhật hoặc Order đã tạo. Phải xác định nguồn chuẩn và workflow đồng bộ/đối soát rõ ràng.

## 12. Khi nào dùng atomic operation, khi nào dùng version?

| Nhu cầu | Phép cập nhật nguyên tử theo điều kiện | CAS với version |
| --- | --- | --- |
| `counter += 1` | Thường phù hợp | Thường không cần nếu không phụ thuộc snapshot |
| `stock -= qty` khi đủ | Rất phù hợp nếu engine hỗ trợ | Cũng dùng được, có thể nhiều conflict |
| Sửa hồ sơ đã mở trên màn hình | Patch field độc lập có thể đủ | Phù hợp để phát hiện bản sửa cũ |
| Đổi trạng thái theo state machine | Condition trên trạng thái | Version thêm bảo vệ snapshot |
| Cập nhật nhiều field phụ thuộc nhau | Cùng update một document hoặc transaction | CAS theo aggregate/document version |
| Cập nhật nhiều item | Không đủ nếu chỉ atomic từng item | Cần transaction/thiết kế invariant bổ sung |

Version giúp phát hiện một entity bị thay đổi **kể từ lần đọc**, còn atomic operation biểu diễn một thay đổi có thể thực hiện trực tiếp trên trạng thái mới nhất. Không phải mọi thao tác cần cả hai, nhưng với nghiệp vụ quan trọng có thể phải dùng đồng thời condition, version và idempotency.

## 13. Retry và kết quả không xác định

Một lỗi phân tán quan trọng:

~~~text
Client gửi: reserve(quantity=2)
Database commit thành công.
Network làm mất response.
Client nhận timeout.
~~~

Từ góc nhìn client, đây là **unknown outcome**. Nếu tự gửi lại lệnh trừ kho, một ý định có thể trừ hai lần.

~~~mermaid
flowchart TD
    A["Gửi conditional update"] --> B{"Kết quả?"}
    B -->|Đã xác nhận success| C["Trả success"]
    B -->|Condition failed| D["Đọc source, xử lý conflict"]
    B -->|Throttling/lỗi tạm| E["Bounded retry + backoff/jitter"]
    B -->|Timeout/không rõ commit| F["Tra trạng thái theo requestId"]
    F --> G{"Ý định đã áp?"}
    G -->|Có| C
    G -->|Chưa| E
    G -->|Chưa xác định| H["PENDING + reconciliation"]
~~~

### 13.1. Conflict là kết quả nghiệp vụ có thể bình thường

Nếu hai khách cùng mua sản phẩm cuối cùng, một conditional write thất bại là **đúng**, không phải outage. Trong khi đó throttling hoặc kết nối tạm lỗi có thể nên retry. Cần phân loại lỗi **trước** khi chọn backoff và HTTP response.

### 13.2. Retry CAS phải tạo quyết định mới

Khi CAS từ version 7 thất bại:

1. Đọc lại source ở mức nhất quán phù hợp.
2. Hiểu version 8 đã thay đổi những gì.
3. Kiểm tra ý định còn hợp lệ không.
4. Nếu hợp lệ, tạo lệnh mới có điều kiện/version mới.
5. Nếu không, trả conflict hoặc yêu cầu người dùng xử lý.

Không đổi version 7 thành 8 rồi ghi đè tự động trong mọi trường hợp. Với sửa nội dung từ giao diện, việc tự retry mù có thể làm mất ý định của người dùng khác.

### 13.3. Bounded retry

Nhiều client cùng CAS một hot key có thể tạo *retry storm*. Cần giới hạn:

- Số lần thử.
- Tổng thời gian chờ.
- Backoff lũy tiến cùng jitter.
- Khả năng chịu tải của DB.
- Mã phản hồi và cách người dùng thử lại theo nghiệp vụ.

Không dùng vòng `while(true)` không giới hạn.

## 14. Idempotency: một ý định chỉ tạo một tác động

**Idempotency ở cấp nghiệp vụ** bảo đảm một request được gửi lại không làm tăng thêm tác động.

Ví dụ client gửi:

~~~json
{
  "requestId": "reserve-2026-00042",
  "tenantId": "merchant-a",
  "sku": "SKU-7",
  "quantity": 2
}
~~~

`requestId` phải ổn định qua retry của **cùng ý định**, đồng thời không được tái dùng cho một nội dung khác.

Một bản ghi idempotency:

~~~json
{
  "tenantId": "merchant-a",
  "requestId": "reserve-2026-00042",
  "payloadHash": "hash-of-canonical-request",
  "state": "SUCCEEDED",
  "reservationId": "R900",
  "result": {
    "reservedQuantity": 2
  }
}
~~~

Khi nhận lại request:

- Nếu ID và payload khớp, trả kết quả đã xác nhận hoặc trạng thái đang xử lý.
- Nếu ID trùng nhưng payload khác, từ chối tái sử dụng.
- Nếu record ở `PENDING`, không tự trừ lại; xác minh tiến độ.
- Nếu request đã hết cửa sổ retry/replay theo chính sách, xử lý dựa trên rule đã định nghĩa.

### 14.1. CAS và idempotency giải quyết hai lỗi khác nhau

| Cơ chế | Ngăn gì? | Chưa tự ngăn gì? |
| --- | --- | --- |
| Atomic decrement | Hai writer ghi từ cùng giá trị cũ | Một request retry gây hai decrement |
| CAS/version | Ghi dựa trên snapshot đã cũ | Cùng ý định được chạy lại sau thành công |
| Idempotency record | Cùng request được áp nhiều lần | Hai request độc lập tranh cùng stock |
| Transaction | Tập mutation nằm trong một ranh giới | Tác động bên ngoài hoặc ngữ nghĩa nghiệp vụ sai |
| State machine | Transition không hợp lệ | Message consumer gửi thông báo hai lần |

### 14.2. Lỗi khi ghi dedup sau mutation

~~~text
1. Trừ tồn kho.
2. Ghi requestId vào bảng dedup.
~~~

Nếu process chết giữa hai bước, retry không thấy requestId và trừ tiếp. Đổi thứ tự cũng có lỗi: record dedup tồn tại nhưng stock chưa giảm.

Cần transaction bao phủ mutation và dedup **nếu cùng hệ hỗ trợ**, hoặc một workflow có trạng thái bền vững và cơ chế phục hồi/đối soát. Không được gọi đây là exactly-once chỉ vì ghi một record dedup sau khi cập nhật.

### 14.3. Thời hạn giữ dedup

Nếu broker có thể replay sau 14 ngày nhưng idempotency record hết hạn sau 1 ngày, cùng sự kiện cũ có thể quay lại và bị thực thi như mới. Retention của dedup/tombstone phải bao phủ **cửa sổ retry, replay và restore** được thiết kế.

## 15. Một item khác nhiều item

Một reservation thường liên quan:

~~~text
Inventory SKU-7
Reservation R900
Order O900
Outbox event OrderReserved
~~~

Nếu chỉ giảm stock nhưng không tạo reservation, hệ thống có thể giữ hàng mồ côi. Nếu tạo reservation rồi giảm stock thất bại, khách thấy giữ hàng không tồn tại.

### 15.1. Transaction trong cùng database

Nếu engine hỗ trợ transaction phù hợp:

~~~text
BEGIN TRANSACTION
  kiểm tra tồn kho bằng điều kiện có thẩm quyền
  giảm tồn kho
  tạo reservation với requestId duy nhất
  ghi outbox event (nếu cùng transaction)
COMMIT
~~~

Ngay cả khi có transaction, cần hiểu **isolation và cách bảo vệ invariant**. Đọc nhiều document rồi ghi các document khác nhau có thể vẫn gặp write skew nếu không có xung đột/ràng buộc phù hợp.

### 15.2. MongoDB multi-document transactions

MongoDB có hỗ trợ giao dịch nhiều document trong phạm vi và cấu hình tương ứng. Có thể phối hợp sửa inventory, tạo reservation và ghi outbox trong một transaction.

Nhưng:

- Có chi phí và giới hạn transaction.
- Write conflict có thể yêu cầu retry.
- Commit có thể có kết quả không rõ với client sau timeout.
- Callback transaction được chạy lại theo cơ chế driver **không nên chứa gọi payment gateway, gửi email hoặc side effect ngoài database**.
- Transaction không mặc nhiên giải quyết mọi invariant đa document nếu chưa thiết kế đúng isolation và điều kiện ghi.

### 15.3. DynamoDB TransactWriteItems

Trong DynamoDB, transaction có thể phối hợp:

~~~text
Item Inventory SKU-7:
  Conditional update nếu available >= qty.

Item Reservation R900:
  Put nếu chưa tồn tại khóa reservation/requestId.
~~~

Khi dùng `TransactWriteItems`, phải tuân thủ giới hạn số item/kích thước của API và không tác động cùng một item bằng hai action riêng trong cùng transaction theo quy tắc dịch vụ. Client request token giúp xử lý idempotency **trong phạm vi/cửa sổ dịch vụ quy định**, không tự thay thế requestId nghiệp vụ bền vững khi replay kéo dài.

### 15.4. Cassandra và ranh giới partition

Một LWT trên một partition không tự biến mọi cập nhật ở nhiều partition thành transaction tổng quát. BATCH CQL thông thường **không thay thế tùy ý isolation trên nhiều entity**. Nếu invariant đòi phối hợp nhiều bản ghi, cần lựa chọn mô hình khóa hoặc hệ có bảo đảm transaction phù hợp, thay vì hy vọng một batch sẽ bảo vệ mọi ràng buộc.

## 16. Nhiều dịch vụ: Saga và bù trừ

Giữ hàng, thanh toán và giao vận có thể thuộc các dịch vụ khác:

~~~text
Orders service
Inventory service
Payments service
Shipping service
~~~

Một transaction database không thể tự commit nguyên tử với mọi **external API**.

~~~mermaid
flowchart TD
    A["Tạo ý định đặt hàng"] --> B["Giữ hàng theo requestId"]
    B --> C{"Giữ được hàng?"}
    C -->|Không| X["Từ chối / hết hàng"]
    C -->|Có| D["Thanh toán theo idempotency key"]
    D --> E{"Có xác nhận từ nguồn thanh toán?"}
    E -->|Có| F["Xác nhận Order"]
    E -->|Không| G["Giải phóng reservation idempotently"]
    F --> H["Phát event đã commit qua outbox"]
~~~

Cần bổ sung:

- Reservation có thời hạn và quyền giải phóng rõ ràng.
- Thanh toán bị timeout có thể đã thành công; cần truy vấn trạng thái giao dịch/provider trước khi charge lại.
- Compensation `release stock` cũng phải idempotent.
- Message/webhook trùng hoặc đến sai thứ tự không được kéo state machine lùi lại.
- Outbox/retry đảm bảo sự kiện thay đổi được phát lại khi worker chết.

**Compensation không phải rollback nguyên tử xuyên hệ**. Nó là một thao tác mới, có thể thất bại và cũng cần xử lý/đối soát.

## 17. Đừng dùng cache để quyết định ghi quan trọng

Một SKU có thể xuất hiện ở nhiều nơi:

~~~text
Inventory source: available = 10
Redis cache:      available = 11 (cũ)
Search index:     available = 12 (chưa refresh)
Product page:     "Còn hàng"
~~~

Cache/search có thể phục vụ hiển thị gần đúng theo chính sách, nhưng một lệnh **giữ hàng** phải đi qua nguồn có quyền quyết định hoặc một reservation authority được thiết kế rõ.

### 17.1. Read-your-writes

Sau conditional update thành công, UI có thể vẫn thấy stock cũ trong cache. Có thể:

- Trả trạng thái mới từ mutation ở nguồn chuẩn.
- Đọc nguồn của item vừa sửa.
- Chờ read model bắt kịp version theo yêu cầu.
- Hiển thị trạng thái đang đồng bộ.

**Không retry reserve chỉ vì cache chưa đổi.**

### 17.2. Đọc eventual consistent có ảnh hưởng gì?

Một replica trả version 7 trong khi source đã là version 8. CAS với expectedVersion 7 sẽ bị từ chối. Điều này có thể gây thêm conflict nhưng vẫn bảo vệ mutation nếu condition được kiểm tra ở nguồn có thẩm quyền.

Nếu cần giảm stale reads, có thể chọn mức nhất quán đọc mạnh hơn theo khả năng engine và chi phí chấp nhận. Điều quan trọng là **điều kiện lúc ghi**, không phải kỳ vọng mọi lần đọc đều luôn mới.

## 18. ABA: dữ liệu quay về cùng giá trị nhưng phiên bản đã đổi

Giả sử:

~~~text
status = READY
  -> CANCELLED
  -> READY
~~~

Client cũ chỉ nhìn `status == READY` sẽ không biết trạng thái đã trải qua hai thay đổi. Nếu quyết định thao tác cần dựa trên **đúng phiên bản được người dùng xem**, điều kiện nên gồm:

~~~text
IF status = READY AND version = 7:
    SET status = SHIPPED, version = 8
~~~

Sau chuỗi A→B→A, version tăng và lệnh cũ bị từ chối.

### 18.1. Xóa rồi tạo lại cùng ID

Nếu một entity bị xóa rồi được tạo lại cùng khóa với version reset về 1, request rất cũ với `expectedVersion=1` có thể khớp nhầm entity mới. Cần quyết định:

- ID có được phép tái sử dụng không?
- Có `generation/epoch` đại diện vòng đời entity không?
- Dấu xóa/tombstone nghiệp vụ được giữ bao lâu?
- Version có được quản lý xuyên lần recreate không?

CAS đúng ở cấp số version không đủ nếu **identity** không ổn định.

## 19. Read model: nguồn chuẩn an toàn vẫn có thể bị ghi đè ở projection

Nguồn Orders có thể đã dùng CAS thành công:

~~~text
v7 -> READY_TO_SHIP
v8 -> SHIPPED
~~~

Nhưng worker cập nhật read model nhận event v8 trước, sau đó mới v7. Nếu chỉ `SET projection.status = event.status`, projection bị kéo ngược về READY.

Một projector có thể lưu:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "status": "SHIPPED",
  "lastAppliedSourceVersion": 8
}
~~~

Nếu event v7 đến sau, worker bỏ qua vì đã áp v8.

### 19.1. Sparse projection và hàng đã xóa

Nếu read model chỉ chứa các đơn READY, event v8 có thể **xóa row**. Khi đó `lastAppliedSourceVersion` trong row cũng biến mất. Event v7 đến muộn có thể tạo lại hàng READY. Cần **watermark/deletion ledger bền vững độc lập với row sparse**, hoặc cơ chế xử lý tuần tự và replay đáng tin cậy.

### 19.2. Progress cũng phải được cập nhật an toàn

Nếu worker:

~~~text
1. Ghi summary/read model
2. Ghi progress version
~~~

rồi chết giữa hai bước, event được retry có thể áp lại delta. Đổi thứ tự cũng có cửa sổ lỗi. Cần transaction phù hợp, mutation idempotent theo contribution, hoặc workflow có checkpoint và reconciliation.

### 19.3. Backfill không được đè event mới

Snapshot backfill đọc O900 v7 khi live worker đã áp v8. Nếu backfill ghi v7 mà không kiểm tra, projection sẽ lùi. Khi xây bảng đọc mới cần mốc replay, version-gating và đối soát với source.

## 20. Java: tái hiện lost update có kiểm soát

Trong Java, có thể minh họa lỗi bằng hai thread cùng đọc giá trị trước khi được phép ghi. Ví dụ **chỉ dùng in-memory object để giải thích interleaving**, không đại diện cơ chế transaction của một NoSQL cụ thể:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LostUpdateDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger storedValue = new AtomicInteger(10);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch permitWrites = new CountDownLatch(1);

        Runnable unsafeRmw = () -> {
            int snapshot = storedValue.get();
            bothRead.countDown();
            try {
                permitWrites.await();
                // set(snapshot + 1) là write một giá trị đã tính từ bản cũ.
                storedValue.set(snapshot + 1);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(unsafeRmw, "A");
        Thread b = new Thread(unsafeRmw, "B");
        a.start();
        b.start();

        bothRead.await();
        permitWrites.countDown();
        a.join();
        b.join();

        System.out.println(storedValue.get()); // 11, không phải 12
    }
}
~~~

Mặc dù `AtomicInteger.set()` là một thao tác thread-safe, **phép tính từ snapshot cũ không được nối nguyên tử với set**. Nếu cùng một mục tiêu chỉ là tăng counter trong một JVM, `incrementAndGet()` hoặc `compareAndSet()` có thể bảo vệ update. Nhưng **AtomicInteger trong Java không bảo vệ trạng thái nằm ở database được nhiều process truy cập**; phải dùng điều kiện ghi tại database hoặc một thành phần authority tương ứng.

### 20.1. CAS trong Java làm mẫu tư duy

~~~java
int oldValue;
int newValue;
do {
    oldValue = storedValue.get();
    newValue = oldValue + 1;
} while (!storedValue.compareAndSet(oldValue, newValue));
~~~

Loop đọc lại khi có xung đột. Với database, không thể thay `compareAndSet` bằng hai API `GET + SET` rồi kỳ vọng cùng tính chất; phải dùng **CAS/conditional write thực sự được engine hỗ trợ**.

## 21. Integration test: 50 client tranh một sản phẩm

Kiểm thử tuần tự ít có khả năng bộc lộ race. Một test mạnh hơn khởi tạo stock=1, tạo 50 request đồng thời, mỗi request giữ 1.

Kỳ vọng:

~~~text
Số reservation độc lập thành công = 1
Số request không giữ được = 49
available cuối = 0
Không có hai Order cùng được xác nhận cho một sản phẩm duy nhất
~~~

### 21.1. Ví dụ Python/PyMongo trên môi trường thử nghiệm

~~~python
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pymongo import MongoClient

client = MongoClient("mongodb://127.0.0.1:27017")
inventory = client["nosql_rmw_lab"]["inventory"]

sku = "SKU-INTEGRATION-TEST-1"
inventory.replace_one(
    {"_id": sku},
    {"_id": sku, "available": 1},
    upsert=True
)

workers = 50
gate = Barrier(workers)


def reserve_once(worker_id):
    gate.wait()
    result = inventory.update_one(
        {"_id": sku, "available": {"$gte": 1}},
        {"$inc": {"available": -1}}
    )
    return result.modified_count == 1


with ThreadPoolExecutor(max_workers=workers) as executor:
    results = list(executor.map(reserve_once, range(workers)))

remaining = inventory.find_one({"_id": sku})["available"]
print("successful reservations:", sum(results))
print("remaining stock:", remaining)

assert sum(results) == 1
assert remaining == 0
~~~

Ví dụ chỉ tác động một document trong **database test riêng**. Nó không tạo Order/Payment hay chứng minh idempotency sau timeout. Một lần chạy thành công cũng không bao phủ mọi interleaving.

### 21.2. Những test cần bổ sung

| Tình huống | Bất biến phải kiểm tra |
| --- | --- |
| 100 request độc lập tăng counter | Nếu 100 ý định được xác nhận, tổng tăng đủ 100 |
| 50 request mua stock=1 | Chỉ một reservation được chấp nhận |
| Hai admin cùng sửa form v7 | Không im lặng mất bản sửa |
| Response mất sau commit | Retry cùng requestId không trừ thêm |
| Concurrent write và delete/recreate | Không khớp nhầm generation |
| Event v8 rồi v7 | Projection không đi lùi |
| Worker chết giữa summary và checkpoint | Retry không nhân đôi delta |
| Inventory commit, Order insert thất bại | Có workflow phục hồi/compensation |
| CAS thất bại liên tục ở hot key | Retry có giới hạn, không làm nghẽn hệ |

Test phải đếm **số ý định thực sự thành công**, không chỉ assert số tồn kho cuối không âm. Nếu source hoặc response có độ mới khác nhau, dùng phương pháp đọc để xác minh phù hợp với hệ.

### 21.3. Chaos và fault injection

Lỗi khó nhất thường xảy ra khi:

~~~text
Database đã commit
Client hoặc worker chết trước khi ghi dedup/checkpoint
~~~

Cần mô phỏng mất network, timeout, process restart, retry event và chuyển leader/replica theo khả năng môi trường kiểm thử. Không áp lỗi phá hoại vào production nếu không có kế hoạch an toàn.

## 22. Theo dõi xung đột trong production

| Metric | Ý nghĩa |
| --- | --- |
| `conditional_write_attempts_total` | Tổng số lần thử |
| `cas_conflicts_total` | Điều kiện/version không khớp |
| `cas_retries_total` | Retry tạo thêm tải |
| `retry_exhausted_total` | Không thể hoàn thành trong ngân sách thử |
| `unknown_outcome_total` | Timeout cần xác minh/đối soát |
| `idempotency_duplicates_total` | RequestId đã từng xử lý được gửi lại |
| `payload_mismatch_total` | Cùng requestId nhưng nội dung khác |
| `invariant_violations_total` | Vượt stock, double reservation, transition sai |
| `write_p95_p99` | Tail latency của conditional write/LWT |
| `hot_key_write_qps` | Một entity gây contention |
| `projection_version_lag` | Bản chiếu chậm so với nguồn |
| `compensation_pending_total` | Workflow nhiều bước đang chờ xử lý |

### 22.1. Conflict không mặc nhiên là outage

Khi có một sản phẩm cuối và 100 request, nhiều conditional write bị từ chối là **đúng nghiệp vụ**. Nhưng nếu hầu hết thao tác cập nhật hồ sơ đều xung đột do một worker sửa `updatedAt` liên tục, cần xem lại aggregate boundary hoặc version granularity.

### 22.2. Tính đúng quan trọng hơn tối ưu latency cục bộ

CAS/LWT có thể chậm hơn unconditional write nhưng giữ invariant. Khi benchmark cần đánh giá cùng:

~~~text
correctness và số ý định được chấp nhận
successful throughput
p50/p95/p99
conflict/retry rate
CPU/network/storage cost
recovery behavior
~~~

Một thiết kế nhanh nhưng bán hai đơn khi chỉ còn một sản phẩm **không phải phương án tối ưu**.

## 23. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đọc rồi `save(value+1)` | Mất một trong hai lần tăng | Atomic increment/CAS |
| Check stock ở app rồi ghi không điều kiện | Oversell dù stock không âm | Conditional decrement |
| Replace toàn document chỉ để sửa một field | Làm mất field người khác mới sửa | Patch đúng field/OCC |
| Dùng `updatedAt` như version duy nhất | Trùng timestamp hoặc lệch clock | Version/CAS |
| Thấy condition failed rồi retry mãi | Conflict hoặc hết hàng bị che giấu | Xử lý theo nghiệp vụ, retry có giới hạn |
| Timeout thì trừ lại ngay | Same intent có thể áp hai lần | Idempotency và xác minh kết quả |
| Lưu dedup record sau update không transaction | Crash giữa hai ghi gây double apply | Atomic transaction hoặc workflow phục hồi |
| CAS v7 lỗi rồi tự set v8 bằng dữ liệu cũ | Ghi đè bản sửa mới | Đọc lại và merge có ý thức |
| Dùng LWT cho mọi field | Tăng contention/p99 không cần thiết | Chỉ CAS khi invariant đòi |
| Cho rằng CQL BATCH bảo vệ mọi invariant | Không có isolation tổng quát theo ý muốn | Xem đúng phạm vi engine |
| Redis Lua thành công nên MongoDB cũng đúng | Hai hệ không có transaction chung | Source authority và saga |
| Transaction callback gọi payment gateway | Retry có thể charge lại | Tách side effect ngoài, idempotency |
| Quyết định stock từ cache | Cache có thể stale | Ghi có điều kiện ở nguồn chuẩn |
| Projector áp event cũ | Bản đọc quay về trạng thái cũ | Version gating/progress |
| Xóa sparse row rồi mất version | Event cũ tạo lại bản ghi | Deletion ledger/tombstone |
| Chỉ check giá trị hiện tại, bỏ ABA | Không biết entity đã thay đổi vòng | Version/generation |
| Chỉ assert stock >= 0 | Vẫn có thể xác nhận nhiều reservation | Assert số intent thành công |
| Chỉ test tuần tự | Không gặp interleaving thực | Integration test đồng thời |

## 24. Bài tập vận dụng

### Bài 1 — Hai lần tăng bị mất

`views=5`. Hai request đọc 5, cùng tính 6 và cùng ghi 6.

1. Vẽ timeline thể hiện lost update.
2. Giá trị cuối thực tế và giá trị mong muốn là gì?
3. Sử dụng `$inc` thay đổi bảo đảm nào?
4. Nếu response mất sau commit, cùng request retry có thể làm gì?

### Bài 2 — Chống oversell

Stock ban đầu = 3, hai request độc lập cùng muốn mua 2:

- Tại sao đọc rồi ghi không điều kiện có thể xác nhận cả hai?
- Viết lệnh conditional update cho MongoDB hoặc DynamoDB.
- Khi request A thành công, request B sẽ gặp điều kiện gì?
- Tại sao cần đếm số reservation được chấp nhận thay vì chỉ kiểm tra stock cuối?

### Bài 3 — Form version 10

A và B cùng mở hồ sơ version 10. A đổi tên, B đổi email.

- Thiết kế CAS document-level.
- Nếu hai field độc lập, giải thích ưu/nhược của patch theo field.
- Nếu cả hai đổi địa chỉ gồm nhiều thuộc tính, có nên merge từng field tự động không?

### Bài 4 — Cassandra LWT

Row có `available=7, version=4`, request muốn giảm 3.

1. Viết CQL conditional update theo giá trị/version đã đọc.
2. Xử lý khi `[applied]` là false.
3. Vì sao không dùng tùy ý arithmetic update trên cột int thường?
4. CAS rất nóng ảnh hưởng latency và retry ra sao?

### Bài 5 — Redis WATCH

Hai client dùng WATCH/MULTI/EXEC trên cùng key:

- Khi nào một EXEC bị hủy?
- Client cần làm gì sau WatchError?
- Nếu EXEC thành công nhưng response mất, tại sao vẫn cần requestId?
- Lua script giúp loại bỏ khoảng chen giữa như thế nào và có rollback khi script error sau mutation không?

### Bài 6 — Nhiều item

Một thao tác giữ hàng phải cập nhật Inventory và tạo Reservation.

1. Vì sao hai cập nhật riêng có thể lệch?
2. Khi nào dùng multi-item transaction?
3. Nếu hai hệ không chung transaction, cần saga và bù trừ nào?
4. Cần ID/idempotency ở những bước gì?

### Bài 7 — ABA và recreate

Trạng thái trải qua `READY -> CANCELLED -> READY`. Client cũ chỉ so status.

1. Tại sao không phát hiện lịch sử thay đổi?
2. Version giúp thế nào?
3. Nếu entity bị xóa và tạo lại cùng ID với version reset, cần thêm generation hoặc quy tắc gì?

### Bài 8 — Event đến sai thứ tự

Nguồn Order:

~~~text
v5 = PAID
v6 = READY_TO_SHIP
v7 = SHIPPED
~~~

Projector nhận v7 rồi v6. Thiết kế cơ chế ngăn v6 tạo lại row READY sau khi v7 đã xóa. Giải thích vì sao ledger cần sống độc lập với row sparse.

### Bài 9 — Kiểm thử đồng thời

Thiết kế một test 100 client mua stock=1 và test 100 request tăng counter. Chỉ ra:

- Barrier hoặc cơ chế tạo tranh chấp.
- Assertions về số ý định thành công.
- Một test retry sau simulated timeout.
- Một test CAS conflict.
- Metrics cần thu để quan sát contention.

### Bài 10 — Chọn cơ chế phù hợp

| Trường hợp | Cơ chế cần phân tích |
| --- | --- |
| Counter lượt xem | Atomic increment và chính sách duplicate |
| Voucher dùng tối đa một lần | Conditional write/uniqueness |
| Hai admin sửa giá | Version/OCC |
| Chuyển Order PAID → SHIPPED | State machine + conditional update |
| Giữ hàng + tạo reservation | Transaction hoặc saga |
| CDC cập nhật read model | Version + idempotent projector |
| Gửi yêu cầu thanh toán | Idempotency key + reconciliation |

Với từng trường hợp, nêu **nguồn sự thật, ranh giới nguyên tử, conflict handling và retry semantics**.

## 25. Quy trình thiết kế ghi an toàn

~~~mermaid
flowchart TD
    A["Phát sinh thao tác cập nhật"] --> B["Xác định invariant và nguồn chuẩn"]
    B --> C{"Trong một item/document?"}
    C -->|Có| D{"Atomic operation + condition đủ?"}
    D -->|Có| E["Conditional atomic update"]
    D -->|Không| F["Version/CAS và xử lý conflict"]
    C -->|Không| G{"Transaction bao phủ mọi item?"}
    G -->|Có| H["Transaction + conditional writes"]
    G -->|Không| I["Saga/workflow + checkpoint + compensation"]
    E --> J["Idempotency và unknown outcome"]
    F --> J
    H --> J
    I --> J
    J --> K["Concurrent + timeout + replay tests"]
    K --> L["Giám sát invariant, conflict, retry, p95/p99"]
~~~

Trước khi triển khai một read–modify–write, hãy trả lời:

1. **Bất biến nào phải luôn đúng?** Không âm, không trùng, không mất bản sửa hay đúng state machine?
2. **Ai sở hữu dữ kiện chuẩn?** Cache/read model có đủ thẩm quyền để quyết định không?
3. **Tính toán phụ thuộc những field nào đã đọc?** Điều gì xảy ra nếu chúng đổi trước khi ghi?
4. **Database có atomic conditional update phù hợp không?** Trên một item, một partition hay nhiều item?
5. **Có thể biểu diễn thành atomic operation thay vì RMW tại ứng dụng không?**
6. **Version conflict phải được trả về hay được tính lại?**
7. **Sau timeout, có chứng minh request đã áp chưa không?**
8. **Nếu message được gửi lại, cùng ý định có bị thực hiện hai lần không?**
9. **Nếu có nhiều hệ, crash giữa các bước được phục hồi thế nào?**
10. **Integration test kiểm chứng đúng bất biến nào, và production có metric cảnh báo nào?**

## Kết luận

**Đọc–sửa–ghi ở ứng dụng là một cửa sổ race condition.** Hai request có thể đọc cùng một bản cũ rồi ghi giá trị đã tính mà không phát hiện thay đổi của request kia. Việc mỗi lệnh đọc hoặc ghi nguyên tử **không khiến cả chuỗi RMW nguyên tử**.

Các nguyên tắc quan trọng nhất:

- **Đưa điều kiện và phép cập nhật vào cùng mutation khi có thể:** MongoDB `$inc` với filter, DynamoDB `ConditionExpression` + `UpdateExpression`, Redis atomic command hoặc Lua.
- **Dùng CAS/version khi bản sửa phụ thuộc phiên bản đã xem:** MongoDB version filter, DynamoDB conditional write, Cassandra LWT, Redis WATCH.
- **Phân biệt conflict với lỗi hạ tầng và unknown outcome:** không retry vô hạn hay tự áp lại mutation sau timeout mà không xác minh.
- **Idempotency khác CAS:** CAS ngăn stale write, còn requestId/dedup ngăn cùng một ý định bị thực thi trùng.
- **Một item khác nhiều item và nhiều dịch vụ:** transaction có phạm vi; external payment/shipping cần workflow, bù trừ và đối soát.
- **Đừng dựa vào cache hoặc timestamp như nguồn phiên bản:** nguồn có thẩm quyền, điều kiện nghiệp vụ và logical version mới bảo vệ invariant.
- **Kiểm thử đồng thời phải đếm các ý định thành công**, không chỉ xem giá trị cuối hoặc chạy từng request tuần tự.

Thiết kế NoSQL an toàn không có nghĩa mọi thao tác phải dùng một transaction lớn. Nó có nghĩa **chọn đúng ranh giới cần nguyên tử, kiểm tra điều kiện tại lúc ghi, xử lý xung đột minh bạch, chống retry trùng và có đường khôi phục nếu những bước không thể commit cùng lúc**.
