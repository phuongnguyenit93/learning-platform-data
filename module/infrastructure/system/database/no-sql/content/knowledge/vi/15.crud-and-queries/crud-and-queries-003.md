# Cập nhật có điều kiện và kiểm tra phiên bản hiện tại

Một thao tác CRUD trong NoSQL thường trông đơn giản: đọc một document theo khóa, sửa vài trường rồi ghi lại. Tuy nhiên, khi nhiều request cùng cập nhật một bản ghi, một lần **đọc–kiểm tra–ghi** không có bảo đảm nguyên tử có thể khiến hệ thống **mất cập nhật (lost update)**, **bán vượt tồn kho**, **xác nhận cùng đơn hai lần** hoặc làm sai trạng thái nghiệp vụ.

**Cập nhật có điều kiện (conditional update)** là một thao tác mà dữ liệu chỉ được thay đổi nếu một điều kiện trên trạng thái hiện tại vẫn đúng **ngay tại thời điểm commit**. **Kiểm tra phiên bản hiện tại (version check)** là dạng phổ biến: client chỉ được ghi nếu bản ghi chưa đổi kể từ lúc client đọc. Kỹ thuật này liên quan đến **compare-and-set (CAS)** và **optimistic concurrency control (OCC)**.

Ví dụ:

~~~text
Chỉ sửa đơn nếu version hiện tại vẫn là 7.
Chỉ giảm tồn nếu available >= requestedQuantity.
Chỉ chuyển Order sang CONFIRMED nếu status hiện là PENDING.
Chỉ tạo username nếu canonical username chưa tồn tại.
Chỉ xóa tài liệu nếu không ai sửa sau lúc người dùng đọc.
~~~

Điểm cốt lõi là **điều kiện và hành động ghi phải được bảo vệ trong cùng ranh giới nguyên tử của hệ lưu trữ có thẩm quyền**. Một câu lệnh đọc rồi một câu lệnh ghi độc lập không thể thay thế yêu cầu này, dù cả hai đều chạy rất nhanh.

> **Lưu ý phạm vi:** Các ví dụ MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis, Cosmos DB và HTTP nhằm minh họa cơ chế thường gặp. Cú pháp, consistency, transaction, giới hạn và chi phí phụ thuộc sản phẩm, phiên bản và cấu hình. Các đoạn pseudocode không phải cú pháp chung cho mọi hệ NoSQL.

## 1. Bài toán lost update

Giả sử document Order:

~~~json
{
  "tenantId": "T-10",
  "orderId": "O-100",
  "status": "DRAFT",
  "shippingAddress": "Địa chỉ A",
  "coupon": null,
  "version": 7
}
~~~

Hai nhân viên cùng mở đơn:

~~~text
Thời điểm      Client A                      Client B
-----------------------------------------------------------------
T0             READ Order version=7           READ Order version=7
T1             Đổi shippingAddress = B        Đặt coupon = SALE
T2             PUT toàn document version=8
T3                                           PUT toàn document version=8

Kết quả cuối có thể còn coupon=SALE
nhưng shippingAddress quay về A.
~~~

Client B ghi cả bản sao đã đọc từ trước khi A sửa. Lệnh PUT có thể **nguyên tử ở cấp một document** nhưng không ngăn lần ghi dựa trên state cũ ghi đè lần trước.

### 1.1. Race giữa kiểm tra và ghi

Trong bài toán tồn kho:

~~~text
available = 5

Request A: READ available=5 => đủ để giữ 4
Request B: READ available=5 => đủ để giữ 3
Request A: WRITE available=1
Request B: WRITE available=2
~~~

Cả hai khách có thể nhận thông báo giữ hàng thành công, dù tổng yêu cầu là 7. Lỗi không chỉ là số tồn cuối cùng sai mà còn là **hai quyết định đã được đưa ra trên một điều kiện không còn đúng**.

Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**. Khoảng cách giữa kiểm tra và hành động có thể rất nhỏ nhưng vẫn tồn tại race.

### 1.2. Đưa điều kiện xuống nơi commit

Thay vì:

~~~text
current = read(key)
if current.version == 7:
    write(newValue)
~~~

ứng dụng phải yêu cầu thao tác khái niệm:

~~~text
conditionalUpdate(
    key = (T-10, O-100),
    condition = current.version == 7,
    changes = {
        shippingAddress: "Địa chỉ B",
        version: 8
    }
)
~~~

Nếu version đã là 8, lần ghi không được áp dụng. Client nhận một kết quả condition failed hoặc conflict.

~~~mermaid
flowchart TD
    A["Đọc record + version = 7"] --> B["Tạo thay đổi dự kiến"]
    B --> C["Conditional write: expectedVersion = 7"]
    C --> D{"Version hiện tại còn là 7?"}
    D -->|Có| E["Commit thay đổi và version mới"]
    D -->|Không| F["Không ghi, báo conflict"]
    F --> G["Đọc lại, merge hoặc retry có kiểm soát"]
~~~

## 2. Phân biệt những cơ chế gần nhau

| Khái niệm | Ý nghĩa | Điều không tự bảo đảm |
|---|---|---|
| **Atomic write** | Một phạm vi ghi được áp dụng toàn bộ hoặc không | Hai writer không mất cập nhật nếu cùng đọc state cũ |
| **Conditional update** | Chỉ ghi khi predicate hiện tại thỏa | Mọi bất biến ngoài phạm vi predicate |
| **Compare-and-set (CAS)** | So sánh expected value/version rồi ghi nếu khớp | Transaction xuyên nhiều item nếu CAS chỉ một item |
| **Optimistic concurrency control (OCC)** | Đọc không giữ khóa dài, phát hiện xung đột lúc ghi | Tự hợp nhất các thay đổi |
| **Pessimistic locking** | Giữ quyền truy cập/khóa để ngăn writer khác | Latency, throughput và availability tốt ở mọi tải |
| **Transaction** | Commit nhóm thao tác theo phạm vi có bảo đảm | Nguyên tử với hệ bên ngoài không cùng transaction |
| **Version/revision/ETag** | Token nhận diện một phiên bản | Có hiệu lực nếu backend không kiểm tra khi ghi |
| **Idempotency key** | Gắn các retry với cùng một ý định | Bảo vệ hai ý định khác nhau cùng cập nhật |

### 2.1. Chu trình optimistic concurrency

1. Client đọc trạng thái và version.
2. Domain layer tính thay đổi từ trạng thái đó.
3. Client gửi `expectedVersion` và thay đổi.
4. Database kiểm tra condition tại lúc ghi.
5. Nếu thành công, hệ cấp version mới.
6. Nếu không khớp, ứng dụng xử lý conflict.

OCC thường phù hợp khi tranh chấp không quá cao. Khi hàng nghìn writer cùng sửa một item, rất nhiều CAS có thể thất bại và retry, khiến hotspot nghiêm trọng hơn.

### 2.2. Timestamp không tự nhiên là version an toàn

Một số hệ dùng trường `updatedAt` để thể hiện lần sửa mới nhất. Nhưng timestamp có độ phân giải giới hạn, các máy có thể lệch đồng hồ, và hai lần ghi gần nhau có thể nhận cùng giá trị. **Không mặc định updatedAt đủ mạnh để làm token chống lost update** nếu chưa chứng minh semantics.

Version đáng tin thường là counter được tăng nguyên tử, revision do database phát hành hoặc opaque ETag có phạm vi bảo vệ phù hợp.

## 3. Thiết kế trường version

Một document có thể lưu:

~~~json
{
  "tenantId": "T-10",
  "orderId": "O-100",
  "status": "DRAFT",
  "shippingAddress": "Địa chỉ A",
  "version": 7
}
~~~

Thao tác:

~~~text
UPDATE Order
SET shippingAddress = "Địa chỉ B",
    version = 8
WHERE tenantId = T-10
  AND orderId = O-100
  AND version = 7
~~~

Đây là pseudocode. Điều kiện được kiểm tra và thay đổi được thực hiện **nguyên tử** theo cơ chế của database.

### 3.1. Contract quan trọng

- Version được khởi tạo cùng bản ghi, ví dụ từ 1.
- Mọi thay đổi có thể ảnh hưởng invariant của aggregate đều đổi version.
- Kiểm tra version và ghi state/version nằm trong cùng một thao tác nguyên tử.
- Client chỉ gửi expectedVersion, không được tự bỏ qua kiểm tra.
- API, background worker, consumer và migration đều theo cùng version policy hoặc cách isolation tương đương.
- Có chính sách khi bản ghi bị xóa rồi tạo lại cùng ID.
- Version có kiểu ổn định và miền giá trị đủ lớn.

### 3.2. Version số và opaque token

Khi ứng dụng tự quản lý số nguyên, version có thể tăng 7 lên 8. Nhưng ETag do database phát hành thường là token **opaque**; không được tự cộng 1 hay diễn giải phần bên trong.

### 3.3. Version chung hay từng field?

Một version cho toàn Order giúp phát hiện mọi thay đổi liên quan, nhưng cũng khiến hai writer sửa hai field độc lập có thể conflict. Version theo nhóm field có thể giảm tranh chấp, song chỉ an toàn khi những nhóm đó **không có bất biến chung**. Coupon và phí vận chuyển có thể ảnh hưởng cùng tổng tiền nên không thể tùy tiện tách version.

## 4. Kết quả của conditional update

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| **UPDATED** | Condition đúng, thay đổi đã commit theo ACK của DB | Trả state/version mới |
| **VERSION_CONFLICT** | Bản ghi đã đổi từ lúc client đọc | Refresh hoặc merge có kiểm soát |
| **PRECONDITION_FAILED** | State nghiệp vụ hiện tại không phù hợp | Báo điều kiện nghiệp vụ không đạt |
| **NOT_FOUND** | Không có record theo key phù hợp | Không tự tạo nếu endpoint chỉ cho update |
| **DUPLICATE_KEY** | Conditional create bị từ chối | Đối chiếu idempotency hoặc báo trùng |
| **UNKNOWN_OUTCOME** | Timeout, chưa biết chắc đã commit chưa | Đối soát theo commandId |
| **RETRYABLE_FAILURE** | Throttling, node/network lỗi tạm thời | Retry giới hạn với backoff |
| **FORBIDDEN** | Không có quyền truy cập | Không xử lý như conflict |

Filter gồm tenantId, orderId, version và status mà không khớp có thể do **ID không tồn tại, tenant sai, version cũ hoặc trạng thái đã đổi**. Không nên tự kết luận mọi thao tác cập nhật 0 record đều là stale version.

### 4.1. Không biến OCC thành last-write-wins

Nếu saveIfVersion thất bại rồi ứng dụng bỏ expectedVersion và PUT toàn document, cơ chế OCC đã bị vô hiệu hóa. Conflict phải được xử lý như một kết quả có ý nghĩa, không phải lỗi cần ép ghi bằng mọi giá.

## 5. MongoDB: filter cùng thao tác update

Một ví dụ updateOne:

~~~javascript
const result = await db.collection("orders").updateOne(
  {
    _id: "O-100",
    tenantId: "T-10",
    version: 7
  },
  {
    $set: {
      shippingAddress: "Địa chỉ B"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  // Không có document khớp toàn bộ filter.
  // Cần phân biệt not found, wrong tenant, stale version.
}
~~~

Trong MongoDB, cập nhật trên một document có tính nguyên tử theo phạm vi hỗ trợ. **Condition version phải nằm trong filter của chính lệnh ghi**, không phải một truy vấn đọc riêng rồi mới update không điều kiện.

### 5.1. Bổ sung trạng thái nghiệp vụ

~~~javascript
const result = await db.collection("orders").updateOne(
  {
    _id: "O-100",
    tenantId: "T-10",
    version: 7,
    status: "DRAFT"
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 }
  }
);
~~~

Lệnh không ghi nếu Order không còn DRAFT. Nhưng các điều kiện phụ thuộc Inventory hoặc Payment vẫn cần được xác minh ở nguồn có thẩm quyền riêng.

### 5.2. Upsert và OCC

Nếu bật upsert trong filter có expectedVersion, record hiện tại với version khác sẽ không khớp và lệnh có thể cố insert bản ghi mới. Kết quả tùy unique key/index và có thể không đúng ý định. Endpoint chỉ sửa existing document thường nên tách rõ khỏi create/upsert.

### 5.3. ODM không phải lúc nào cũng tự quản lý version

Một ODM có thể tự tăng version cho thao tác save nhưng không áp dụng giống nhau cho updateOne, findOneAndUpdate hay bulk writes. Cần kiểm tra lệnh thực tế gửi tới database có condition hay không.

### 5.4. Hai updateOne không tự tạo transaction chung

Nếu invariant yêu cầu cập nhật hai document cùng lúc, CAS riêng từng document không đủ. Cần transaction đa document với bảo đảm phù hợp hoặc thiết kế lại boundary.

## 6. DynamoDB: ConditionExpression

Amazon DynamoDB có thể kiểm tra condition trong thao tác ghi một item:

~~~javascript
const params = {
  TableName: "Orders",
  Key: {
    PK: "TENANT#T-10",
    SK: "ORDER#O-100"
  },
  ConditionExpression: "#v = :old AND #st = :draft",
  UpdateExpression:
    "SET #address = :newAddress, #v = #v + :one",
  ExpressionAttributeNames: {
    "#v": "version",
    "#st": "status",
    "#address": "shippingAddress"
  },
  ExpressionAttributeValues: {
    ":old": 7,
    ":draft": "DRAFT",
    ":newAddress": "Địa chỉ B",
    ":one": 1
  }
};
~~~

Đây là cấu trúc tham số minh họa kiểu DocumentClient. Với low-level SDK có thể cần kiểu AttributeValue khác. Cần dùng đúng client và xử lý response/error của API thực tế.

### 6.1. Conditional stock decrement

~~~text
Key: INVENTORY#SKU-A
Condition: available >= requestedQuantity
Update: available = available - requestedQuantity
~~~

Khi condition và phép trừ được thực thi nguyên tử trên item có thẩm quyền, nó ngăn giữ vượt available trong phạm vi đó. Tuy nhiên, **retry cùng một reservation sau timeout** vẫn có thể trừ hai lần nếu không có idempotency key/reservationId được ghi nhận an toàn.

### 6.2. Condition failed không phải throttling

Lỗi điều kiện như ConditionalCheckFailedException (tùy API) nghĩa là predicate không thỏa, không nên retry mù như lỗi mạng. Nếu muốn thử lại, phải đọc state và đánh giá lại ý định.

### 6.3. Transaction nhiều item và nhiều region

Nếu invariant liên quan nhiều item, cần xem transaction API phù hợp như TransactWriteItems cùng giới hạn hiện hành. Với kiến trúc multi-region, CAS tại một region không mặc nhiên bảo vệ invariant toàn cầu trước writer ở region khác; phải xác minh replication/conflict semantics.

## 7. Cassandra/ScyllaDB: Lightweight Transaction

Các hệ thuộc họ Cassandra hỗ trợ câu lệnh CQL điều kiện trong những phạm vi nhất định, thường gắn với **lightweight transaction (LWT)**:

~~~sql
CREATE TABLE order_state (
    tenant_id text,
    order_id text,
    status text,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Một câu lệnh điều kiện:

~~~sql
UPDATE order_state
SET status = 'CONFIRMED',
    version = 8
WHERE tenant_id = 'T-10'
  AND order_id = 'O-100'
IF version = 7;
~~~

Kết quả có thể mang trường **[applied]** để biết condition đã được áp dụng hay chưa.

### 7.1. LWT khác ghi thường theo timestamp

Ghi thông thường trong Cassandra/ScyllaDB có thể dùng write timestamp để hòa giải phiên bản. **Last-write-wins by timestamp không kiểm tra bất biến nghiệp vụ**, vì vậy không thay thế LWT khi cần điều kiện trạng thái hiện tại.

### 7.2. Phạm vi và chi phí

LWT có thêm phối hợp, latency và contention. Không thể suy từ một câu lệnh IF trên một row rằng hệ hỗ trợ transaction tùy ý trên nhiều partition. Cần xác minh tính năng/batch, mức consistency và benchmark theo workload thực.

### 7.3. Timeout không chắc là thất bại

Nếu client không nhận được ACK, LWT có thể đã commit. Phải dùng commandId/idempotency hoặc đọc đối soát state trước khi thử lại một thao tác có hiệu ứng.

## 8. Redis: WATCH và Lua

### 8.1. WATCH + MULTI/EXEC

~~~text
WATCH inventory:SKU-A
available = GET inventory:SKU-A

if available < requested:
    UNWATCH
    return INSUFFICIENT

MULTI
DECRBY inventory:SKU-A requested
EXEC
~~~

Đây là pseudocode. Nếu key được theo dõi đã thay đổi trước EXEC, transaction có thể bị hủy. Client phải xử lý kết quả và retry có giới hạn. Với Redis Cluster, failover hoặc key expiration, cần xem semantics và phạm vi key theo sản phẩm/cấu hình.

### 8.2. Script nguyên tử

~~~lua
local key = KEYS[1]
local amount = tonumber(ARGV[1])
local available = tonumber(redis.call("GET", key) or "0")

if amount == nil or amount <= 0 then
    return {err = "INVALID_AMOUNT"}
end

if available < amount then
    return 0
end

redis.call("DECRBY", key, amount)
return 1
~~~

Trong phạm vi Redis hỗ trợ, script được thực hiện nguyên tử. Nhưng ví dụ **chưa idempotent**: nếu response mất sau khi trừ, retry có thể trừ tiếp. Cần reservationId và dấu kết quả được lưu trong cùng ranh giới đáng tin, cộng với đánh giá durability/failover.

### 8.3. Cache chưa chắc có thẩm quyền

Nếu Redis chỉ là cache của Inventory ở database khác, CAS thành công trên cache không chứng minh nguồn tồn kho đã thay đổi. Phải xác định nơi ra quyết định nghiệp vụ cuối cùng.

## 9. ETag và revision token

Một số document database có revision token do hệ quản trị phát hành, ví dụ Azure Cosmos DB for NoSQL với **_etag** và điều kiện If-Match cho những thao tác được hỗ trợ.

~~~text
READ Order -> etag = opaque-token-A

REPLACE/PATCH with If-Match = opaque-token-A

Nếu document đã thay đổi:
    precondition fails
~~~

Không tự coi ETag là timestamp hoặc số cần cộng 1. Với transaction batch, logical partition và nhiều region, phải xác minh phạm vi điều kiện và consistency cụ thể.

## 10. HTTP API: If-Match và lỗi precondition

Một GET:

~~~http
GET /orders/O-100 HTTP/1.1
Authorization: Bearer ...

HTTP/1.1 200 OK
ETag: "order-rev-7"
Content-Type: application/json

{"orderId":"O-100","status":"DRAFT","version":7}
~~~

Client PATCH:

~~~http
PATCH /orders/O-100 HTTP/1.1
Authorization: Bearer ...
If-Match: "order-rev-7"
Content-Type: application/json

{"shippingAddress":"Địa chỉ B"}
~~~

Server cần xác thực quyền, validate body, chuyển token sang condition ở database và chỉ ghi khi khớp. Nếu If-Match không còn đúng, **HTTP 412 Precondition Failed** phù hợp. Nếu API bắt buộc header mà client thiếu, **428 Precondition Required** có thể phù hợp. **409 Conflict** thường dành cho conflict nghiệp vụ theo API contract.

### 10.1. Strong/weak ETag

If-Match dùng strong comparison. Weak ETag có tiền tố W/ không phải strong validator tương đương cho mọi thao tác. Nếu ETag dùng để ngăn lost update, phải phát hành token với semantics phù hợp.

### 10.2. Header không đủ nếu backend bỏ qua

Nếu server nhận If-Match nhưng thực hiện PUT không điều kiện, cơ chế không an toàn. Condition phải được thực thi ở ranh giới commit.

### 10.3. Scope của ETag

Nếu token chỉ đổi khi một field thay đổi, trong khi command phụ thuộc một field khác, có thể không phát hiện stale state. ETag cần phản ánh những thay đổi có liên quan tới invariant được bảo vệ.

## 11. Predicate trạng thái nghiệp vụ

Version check trả lời **có thay đổi nào được commit kể từ lúc đọc không**. Predicate trạng thái kiểm tra **command có còn hợp lệ ở hiện tại không**.

Ví dụ:

~~~text
UPDATE Order
SET status = CONFIRMED,
    version = 8
WHERE id = O-100
  AND version = 7
  AND status = PENDING
~~~

Nếu Order đã CANCELED, command không được phép làm nó CONFIRMED. Nhưng điều kiện “đã giữ đủ tồn kho” có thể thuộc Inventory riêng; phải xác nhận từ nguồn có thẩm quyền, không chỉ dùng dữ liệu projection trễ.

### 11.1. Domain validation không thể tách khỏi commit

~~~text
READ Order
if status == PENDING:
    validateBusinessRules()
    WRITE status = CONFIRMED // Không có condition: vẫn race.
~~~

Sau khi validation xong, state có thể đổi. Điều kiện quan trọng phải được bảo vệ bằng CAS hoặc transaction có mức cách ly phù hợp.

### 11.2. Conditional delete

Client đọc Order DRAFT version 7, nhưng người khác vừa xác nhận. Lệnh xóa cũ phải bị từ chối:

~~~text
DELETE Order O-100
IF version = 7 AND status = DRAFT
~~~

Xóa nhiều hệ như cache/search/archive còn cần workflow riêng; CAS ở nguồn chỉ bảo vệ quyết định xóa bản ghi có thẩm quyền.

### 11.3. Conditional create

Tạo username cần kiểm tra canonical key chưa tồn tại bằng unique index hoặc conditional put. Query-before-insert không đủ để ngăn hai request đồng thời tạo trùng.

## 12. Version khác idempotency

Nếu client tạo Order thành công nhưng response mất:

~~~text
POST /orders
Idempotency-Key: req-7281

Lần 1: tạo O-100.
Lần 2: gửi lại cùng req-7281.
~~~

**Idempotency** giúp lần 2 không tạo O-101. **Version check** bảo vệ hai lệnh thay đổi khác nhau cùng dựa trên version cũ.

| Rủi ro | Cơ chế chủ đạo |
|---|---|
| Retry cùng create command | Idempotency key |
| Hai writer sửa cùng document | Version/CAS |
| Username unique | Conditional insert/unique key |
| Stock không âm | Predicate nguyên tử và reservationId |
| Commit nhiều item | Transaction đúng phạm vi |
| Phát event sau commit | Transactional outbox/CDC, consumer idempotent |

### 12.1. Unknown outcome

Một request trừ kho 2 có thể đã commit nhưng ACK bị mất. Nếu client đọc version mới rồi trừ thêm 2, nó đã xử lý cùng ý định hai lần. Cần commandId/reservationId ổn định và khả năng tra kết quả đã xử lý.

### 12.2. Không retry mù

Condition failed không phải network failure. Retry lại cùng condition thường không thành công; phải đọc lại state và đánh giá lại command. Với timeout không biết kết quả, retry phải có idempotency hoặc đối soát.

## 13. Các chiến lược xử lý conflict

### 13.1. Trả conflict cho người dùng

Phù hợp khi merge tự động dễ làm sai. UI tải lại bản mới, cho người dùng so sánh và gửi một ý định cập nhật mới.

### 13.2. Retry giới hạn

Một command an toàn để áp dụng lại có thể dùng:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    current = read()
    candidate = applyCommand(current, command)
    outcome = saveIfVersion(current.version, candidate)
    if outcome == SUCCESS:
        return SUCCESS
    if outcome != VERSION_CONFLICT:
        return handleOtherOutcome(outcome)
    wait with bounded backoff and jitter
return CONFLICT
~~~

Không retry vô hạn. Hàng nghìn writer cùng tranh version có thể tạo **retry storm**.

### 13.3. Merge phải giữ invariant

Người A đổi địa chỉ, người B đổi coupon. Hai field khác nhau chưa chắc độc lập: coupon có thể ảnh hưởng phí vận chuyển và tổng tiền. Một merge đúng áp dụng lại business command trên state mới, không chỉ ghép hai JSON patch.

### 13.4. Queue hoặc single writer

Với aggregate quá nóng, đưa command vào queue theo key hoặc chọn một owner tuần tự hóa có thể phù hợp. Đánh đổi là latency, backlog, failover và yêu cầu đảm bảo thứ tự/idempotency.

## 14. Các trường hợp biên

### 14.1. ABA

~~~text
T0: status = DRAFT
T1: status = REVIEW
T2: status = DRAFT
~~~

Client cũ chỉ kiểm tra status DRAFT không phát hiện đã có thay đổi giữa chừng. Nếu cần nhận biết mọi cập nhật liên quan, dùng version/generation token. Một số command chỉ cần current value vẫn có thể hợp lệ; phải xác định bất biến thực sự.

### 14.2. Xóa rồi tạo lại cùng ID

Order O-100 version 7 bị xóa, sau đó một thực thể mới cũng dùng O-100 version 1. Cần tránh client cũ thao tác nhầm đối tượng mới; có thể không tái sử dụng ID hoặc dùng generationId/tombstone theo policy.

### 14.3. Version bị tràn hoặc sai kiểu

Version lúc là số, lúc là chuỗi có thể gây so sánh sai. Chọn kiểu dữ liệu đủ lớn, chuẩn hóa từ đầu và quản lý migration.

### 14.4. Writer nền không tăng version

Một job cập nhật status nhưng không thay revision có thể làm OCC mất tác dụng. Tất cả writer ảnh hưởng aggregate phải tuân thủ policy hoặc cơ chế transaction tương đương.

### 14.5. Stale replica

Read replica có thể trả version 7 khi primary đã 8. CAS tại nguồn có thẩm quyền vẫn từ chối ghi cũ, nhưng tỷ lệ conflict tăng. Cần cân nhắc read consistency, routing và read-your-writes khi UX yêu cầu.

### 14.6. Multi-region

Hai region cùng chấp nhận CAS cục bộ rồi hòa giải conflict theo cơ chế khác không tự bảo vệ invariant toàn cầu. Với kho/số dư, có thể cần single writer, quota cấp trước hoặc coordination.

## 15. CAS một item không bảo vệ bất biến xuyên record

Giả sử bệnh viện yêu cầu luôn có ít nhất một bác sĩ trực:

~~~text
Doctor A: onCall=true
Doctor B: onCall=true

A đọc B đang trực -> CAS A thành false.
B đọc A đang trực -> CAS B thành false.

Kết quả: A=false, B=false, quy tắc bị vi phạm.
~~~

Mỗi CAS có thể đúng trên record riêng; invariant “ít nhất một người trực” liên quan **hai record**. Đây là ví dụ của **write skew**. Cần transaction với isolation thích hợp hoặc một aggregate/record chung giữ quy tắc.

### 15.1. Chuyển tiền

CAS trừ Account A rồi CAS cộng Account B không tự tạo transaction chuyển tiền. Crash giữa hai bước làm quy trình không hoàn tất. Cần transaction đa item phù hợp hoặc workflow/ledger có trạng thái bền, idempotency và đối soát.

### 15.2. Uniqueness

Hai request kiểm tra usernameKey chưa có rồi tạo hai User khác nhau. CAS trên từng User không bảo vệ uniqueness chung. Phải có một điểm cạnh tranh theo canonical username hoặc index/transaction tương đương.

### 15.3. External side effects

CAS Order sang CONFIRMED không tự đảm bảo email hoặc thanh toán bên ngoài xảy ra đúng một lần. Có thể dùng transactional outbox và worker với idempotency, cùng công cụ đối soát.

## 16. Case study: Order, Inventory và Payment

~~~mermaid
flowchart LR
    O["Order aggregate"] --> I["Inventory aggregate"]
    O --> P["Payment aggregate"]
    O --> R["OrdersByCustomer read model"]
~~~

- Order sở hữu state transition/version.
- Inventory sở hữu invariant không giữ vượt tồn.
- Payment sở hữu paymentId, capture/refund và gateway state.
- Read model phục vụ truy vấn và có thể trễ, không phải nguồn quyết định.

Một saga có thể gồm:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RESERVING: ReserveInventory
    RESERVING --> RESERVED: Giữ đủ SKU
    RESERVING --> CANCELING: Thiếu hàng
    RESERVED --> PAYING: RequestPayment
    PAYING --> CONFIRMED: Payment confirmed
    PAYING --> CANCELING: Payment failed
    CANCELING --> CANCELED: Release/compensate
    CONFIRMED --> [*]
    CANCELED --> [*]
~~~

Nếu InventoryReserved đến muộn sau khi Order CANCELED, conditional state transition của Order phải từ chối chuyển sang RESERVED. Workflow cần giải phóng reservation một cách idempotent.

**TTL của reservation không tự trả kho hoặc hoàn tiền.** Cần timeout handler, trạng thái bền và đối soát.

## 17. Partition key và contention

Những key thường gặp:

~~~text
Order:    (tenantId, orderId)
Stock:    (warehouseId, sku)
Username: (tenantId, canonicalUsername)
~~~

### 17.1. Hot key

Một SKU flash sale có thể nhận hàng nghìn CAS/giây, gây conflict và retry. Các cách xem xét:

- Atomic conditional decrement trực tiếp.
- Queue/rate limit theo SKU.
- Bounded retry với exponential backoff và jitter.
- Cấp quota trước cho shard, bảo đảm tổng quota không vượt tồn.
- Hàng chờ mua nếu phải điều tiết đỉnh tải.

Chỉ chia bản ghi tồn kho thành nhiều shard ngẫu nhiên không tự bảo vệ tổng số lượng.

### 17.2. Partition theo tenant

Đặt tất cả Order trong một partition tenantId có thể làm tenant lớn thành hot partition. Khóa kết hợp tenantId + orderId có thể phù hợp hơn cho truy cập từng Order, còn lịch sử theo khách cần index/read model riêng.

### 17.3. Hotspot và tổng capacity

Cluster có thể còn nhiều CPU nhưng một aggregate được cập nhật liên tục vẫn là điểm nghẽn do contention. Theo dõi conflict, retry và p99 **theo key hoặc nhóm key**, không chỉ xem số node.

## 18. Ví dụ Java: repository thật sự phải CAS

Một interface đơn giản:

~~~java
public record OrderKey(String tenantId, String orderId) {}

public record Order(
    OrderKey key,
    long version,
    String status,
    String address
) {}

public sealed interface SaveResult
    permits SaveResult.Saved, SaveResult.Conflict,
            SaveResult.NotFound {

    record Saved(Order order) implements SaveResult {}
    record Conflict() implements SaveResult {}
    record NotFound() implements SaveResult {}
}

public interface OrderRepository {
    Order findById(OrderKey key);

    // Implementation bắt buộc phải dùng atomic conditional write.
    SaveResult saveIfVersion(
        OrderKey key,
        long expectedVersion,
        Order newState
    );
}
~~~

Một implementation sai:

~~~java
if (repository.findById(key).version() == expectedVersion) {
    repository.saveWithoutCondition(candidate);
}
~~~

Giữa read và write còn race. Repository phải chuyển expectedVersion thành condition thực sự của database hoặc bảo vệ bằng transaction có isolation thích hợp.

### 18.1. Service dùng OCC

~~~java
public final class ChangeAddressService {
    private final OrderRepository repository;

    public ChangeAddressService(OrderRepository repository) {
        this.repository = repository;
    }

    public SaveResult changeAddress(
        OrderKey key,
        long expectedVersion,
        String newAddress
    ) {
        Order current = repository.findById(key);
        if (current == null) {
            return new SaveResult.NotFound();
        }

        if (!"DRAFT".equals(current.status())
                || current.version() != expectedVersion) {
            return new SaveResult.Conflict();
        }

        Order candidate = new Order(
            key,
            expectedVersion + 1,
            current.status(),
            newAddress
        );

        return repository.saveIfVersion(
            key, expectedVersion, candidate
        );
    }
}
~~~

Đây là ví dụ tối giản, không phải service production đầy đủ. Kiểm tra tại service giúp phân loại sớm, nhưng chỉ thao tác CAS ở repository mới đóng race. Nếu background writer thay status mà không đổi version, cần thêm condition status hoặc thống nhất version policy.

## 19. PUT, PATCH, upsert và delete

| Thao tác | Rủi ro | Biện pháp |
|---|---|---|
| PUT/replace document | Ghi đè thay đổi của writer khác | Version/If-Match |
| PATCH một vài field | Logic có thể dựa trên state cũ | Predicate/expectedVersion |
| Increment/decrement | Retry áp dụng hai lần | Atomic update + idempotency |
| Create-if-absent | Hai request tạo cùng key | Unique/conditional create |
| Upsert | Version filter sai tạo record không mong muốn | Tách create/update |
| DELETE | Client cũ xóa record đã đổi | Conditional delete |

### 19.1. Xóa rồi hồi sinh

Một CDC event cũ được replay hoặc upsert không điều kiện có thể tạo lại document đã xóa. Cần deletion state/tombstone, revision/generation policy hoặc cơ chế nguồn có thẩm quyền khác để chặn event cũ.

### 19.2. Multi-tenancy và quyền truy cập

Condition phải dùng tenantId từ ngữ cảnh đã xác thực, không tin tenantId do client gửi. Không trả thông tin về bản ghi tenant khác qua thông báo stale version.

## 20. Kiểm thử concurrency

| Trường hợp | Kết quả mong đợi |
|---|---|
| Hai writer cùng expectedVersion=7 | Theo OCC toàn aggregate, chỉ một commit |
| Stock=5, hai request giữ 4 và 3 | Không giữ vượt tồn |
| Retry cùng reservationId | Không trừ hai lần |
| UPDATE và DELETE đồng thời | Không xóa record version mới bằng request cũ |
| Đọc từ replica version cũ | CAS tại nguồn không ghi đè state mới |
| Timeout sau commit | Không thực thi cùng command hai lần |
| Background writer thay state | Version hoặc condition phản ánh thay đổi |
| Delete rồi create cùng ID | Token cũ không sửa nhầm thế hệ mới |
| Ghi cùng aggregate từ hai region | Invariant được kiểm chứng theo topology |
| Hàng nghìn CAS trên một key | Backoff/rate limit không tạo retry storm |

### 20.1. Barrier test hai writer

~~~text
1. Tạo Order version 7.
2. Hai worker cùng đọc version 7.
3. Dùng barrier cho hai thao tác save chạy đồng thời.
4. Kiểm tra chỉ một thao tác thành công.
5. Đọc nguồn có thẩm quyền để xác minh version và state.
~~~

Chỉ kiểm tra response không đủ; cần kiểm tra **trạng thái cuối**.

### 20.2. Test unknown outcome

Giả lập server đã commit nhưng ACK bị mất. Client retry cùng commandId phải nhận kết quả logic tương ứng hoặc được đối soát, không tạo hiệu ứng nghiệp vụ thứ hai.

## 21. Observability và vận hành

| Metric | Ý nghĩa |
|---|---|
| Conditional write success rate | Tỷ lệ condition thành công |
| Version conflict rate | Mức tranh chấp theo aggregate |
| Business predicate failures | Lệnh bị từ chối hợp lệ vì state/stock |
| CAS/LWT p95/p99 latency | Chi phí cập nhật có điều kiện |
| Retry count và backoff | Phát hiện retry storm |
| Hot key/partition throughput | Tìm điểm nghẽn riêng |
| Unknown-outcome commands | Các request cần đối soát |
| Duplicate commands prevented | Hiệu quả idempotency |
| Invariant mismatch | Dữ liệu sai sau sự cố |
| Stale-read conflict rate | Ảnh hưởng của replica chậm |

Nên phân loại condition failed thành **VERSION_STALE**, **INVALID_STATE_TRANSITION**, **INSUFFICIENT_STOCK**, **DUPLICATE_KEY** và các trường hợp khác. Chúng không có cùng ý nghĩa và không nên dùng cùng retry policy.

## 22. Những ngộ nhận phổ biến

### “Đã đọc version trong Java rồi mới ghi là đủ”

Không. Nếu hai lệnh tách nhau, writer khác có thể chen vào.

### “Atomic document update ngăn mọi lost update”

Không. Atomicity không thay thế kiểm soát các writer dùng snapshot cũ.

### “Dùng updatedAt làm version luôn an toàn”

Độ phân giải và đồng hồ không mặc định đủ chính xác/đơn điệu.

### “Chỉ kiểm tra status là biết record chưa bị sửa”

ABA và những field khác có thể làm giả định sai.

### “Conflict là lỗi, cứ retry tới khi thành công”

Conflict có thể là kết quả hợp lệ. Retry vô hạn gây tải và có thể làm sai ý định.

### “CAS đảm bảo retry decrement không bị trừ hai lần”

Không. Retry cùng nghiệp vụ vẫn cần idempotency.

### “CAS một Order bảo vệ cả Inventory và Payment”

Không. Phải xét phạm vi invariant và transaction của từng nguồn.

### “LWT luôn rẻ như ghi thường”

LWT thường có chi phí phối hợp riêng, đặc biệt trên hot partition.

### “Upsert cho mọi update luôn tiện”

Upsert kết hợp version filter có thể tạo record mới ngoài ý định.

### “Có If-Match là backend tự an toàn”

Không nếu server không chuyển điều kiện xuống DB.

### “CAS cục bộ ở mọi region tạo nhất quán toàn cầu”

Không mặc định. Cần kiểm tra cách replication và xử lý conflict.

### “Tách version theo field luôn tốt hơn”

Nếu các field cùng invariant, tách version có thể làm mất bảo đảm cần thiết.

## 23. Quy trình thiết kế conditional update

1. **Xác định invariant** cần bảo vệ.
2. **Chọn owner** và key có thẩm quyền.
3. **Chọn condition**: expectedVersion, status, available hoặc kết hợp.
4. **Chọn thao tác DB** đảm bảo kiểm tra và ghi nguyên tử.
5. **Thiết kế version policy** cho tất cả writer, kể cả background job.
6. **Bổ sung idempotency** nếu cùng command có thể được gửi lại.
7. **Phân loại outcome**: success, conflict, missing, timeout, validation.
8. **Chọn conflict strategy**: refresh, merge, bounded retry.
9. **Xét nhiều record/region** để chọn transaction hoặc workflow.
10. **Kiểm thử concurrency/failure** và theo dõi metric.

Một quyết định mẫu:

~~~text
Use case: Change shipping address
Aggregate: Order
Key: (tenantId, orderId)
Precondition: status = DRAFT
Concurrency token: version
Atomic operation: update document if version and status match
Version policy: increment on each relevant commit
Conflict: return precondition failure; client refreshes
Idempotency: separate for external effects
Consistency: write at source of truth; stale reads may conflict
Monitoring: conflict rate, retry count, p99 latency
~~~

## 24. Bài tập thực hành

### Bài 1 — Hai người sửa một đơn

Order version 7 có địa chỉ A và coupon rỗng. Người A đổi địa chỉ thành B, người B áp coupon SALE, cả hai đọc version 7. Mô tả lost update, CAS và cách xử lý conflict không mất dữ liệu.

### Bài 2 — Giữ hàng

Kho còn 5, hai request muốn giữ 4 và 3. Viết predicate atomic, thêm reservationId và cách đối soát sau timeout.

### Bài 3 — ABA

Record đi qua DRAFT -> REVIEW -> DRAFT. Vì sao client cũ chỉ kiểm tra DRAFT có thể bỏ sót thay đổi? Khi nào cần version/generation?

### Bài 4 — MongoDB

Viết updateOne với filter gồm ID, tenant, version=10, status=DRAFT; cập nhật địa chỉ và tăng version. Giải thích matchedCount bằng 0 và rủi ro upsert.

### Bài 5 — DynamoDB

Thiết kế ConditionExpression và UpdateExpression để giảm stock khi đủ. Làm sao retry cùng reservationId không trừ hai lần?

### Bài 6 — Cassandra LWT

Hai writer muốn chuyển Order version 4 sang CONFIRMED và CANCELED. Viết CQL IF version=4, mô tả kết quả cạnh tranh và tradeoff LWT.

### Bài 7 — HTTP If-Match

GET trả ETag rev-17, PATCH gửi If-Match rev-17 trong khi source đã rev-18. Chọn response HTTP, mô tả backend CAS và phân biệt thiếu If-Match với token cũ.

### Bài 8 — Write skew

Hai bác sĩ đang trực, quy tắc yêu cầu ít nhất một người trực. Hai request tự tắt ca sau khi đọc người kia. Giải thích vì sao CAS từng bác sĩ chưa đủ và đề xuất cách bảo vệ.

### Bài 9 — Multi-region

Hai region tiếp nhận giữ hàng đồng thời khi replication trễ. Phân tích rủi ro CAS cục bộ, so sánh single writer và quota vùng.

### Bài 10 — Retry storm

1.000 request cùng tranh một stock item, nhiều CAS fail rồi retry ngay và một số request timeout sau commit. Thiết kế bounded retry, idempotency, metric và phương án queue.

---

**Kết luận:** Cập nhật có điều kiện biến kỳ vọng của client thành **một tiền điều kiện phải còn đúng ngay tại thời điểm commit**. Version check phát hiện ghi từ trạng thái cũ và giảm nguy cơ lost update; predicate nghiệp vụ giúp bảo vệ trạng thái và tồn kho trong phạm vi có thẩm quyền. Nhưng CAS không thay thế idempotency, transaction xuyên nhiều item, workflow nhiều aggregate hay kiểm soát quyền. Để CRUD NoSQL đúng trong điều kiện phân tán, cần xác định **invariant thuộc đâu, điều kiện nào được kiểm tra nguyên tử, cách xử lý conflict/timeout và các phép thử cạnh tranh chứng minh hệ thống hoạt động đúng**.
