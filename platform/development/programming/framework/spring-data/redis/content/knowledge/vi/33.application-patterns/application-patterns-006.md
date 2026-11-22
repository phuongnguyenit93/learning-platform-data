# Chống yêu cầu trùng và quản lý khóa lũy đẳng với Spring Data Redis

> **Module:** Spring Data Redis  
> **Chương:** Mẫu ứng dụng  
> **Chủ đề:** Thiết kế xử lý yêu cầu lặp lại trong ứng dụng Spring Boot, sử dụng Redis để đăng ký khóa lũy đẳng (*idempotency key*), kiểm soát yêu cầu đồng thời, lưu kết quả để trả lại khi retry và phối hợp với cơ sở dữ liệu hoặc hệ thống nghiệp vụ nhằm tránh tác dụng phụ bị lặp.

## 1. Vấn đề thực tế: người dùng gửi một yêu cầu, server có thể nhận nhiều lần

Giả sử người dùng nhấn **Đặt hàng**. Server tạo đơn hàng thành công nhưng response bị mất do mạng. Trình duyệt hoặc client thử gửi lại:

~~~text
Client                      Spring Boot              Database
  | POST /orders (K=abc) ----> |                         |
  |                            | -- CREATE order ------> |
  |                            | <--- order=o-101 ------ |
  |          (mất response)  X |                         |
  | POST /orders (K=abc) ----> |                         |
  |                            | -- CREATE order ------> |
  |                            | <--- order=o-102 ------ |
  | <--- order=o-102 --------- |                         |
~~~

Ý định nghiệp vụ là **tạo một đơn hàng**, nhưng kết quả là hai đơn. Những tình huống khác cũng có thể gây lặp:

- Người dùng nhấn nút hai lần rất nhanh.
- HTTP client tự retry vì timeout, lỗi kết nối hoặc `502`/`503`.
- Load balancer gửi request tới một instance khác sau khi instance đầu bị ngắt.
- Gateway hoặc hệ thống đồng bộ gửi lại request khi không biết kết quả trước đó.
- Webhook được nhà cung cấp gửi nhiều lần để tăng xác suất giao nhận.
- Consumer xử lý message thành công rồi crash trước khi gửi acknowledgement.
- Một tác vụ chạy theo lịch được kích hoạt lặp do failover.
- Một request được gửi lại sau khi mobile app mất kết nối.

Không thể giải quyết đầy đủ bằng cách **disable nút trên UI** hoặc “client nhớ chỉ gọi một lần”: nhiều nguồn gửi request không nằm dưới quyền kiểm soát của server, và network có thể khiến client không biết request trước đã thực thi chưa.

Mục tiêu là: **nhiều lần gửi cùng một ý định nghiệp vụ không tạo nhiều tác dụng phụ không mong muốn**, đồng thời cho phép khách hàng gửi một yêu cầu *mới* thật sự khi cần.

### 1.1. Định nghĩa lũy đẳng

Một operation lý tưởng có tính lũy đẳng nếu thực hiện lặp lại với cùng ngữ nghĩa sẽ dẫn tới cùng trạng thái cuối, thay vì nhân đôi tác dụng phụ.

Ví dụ:

~~~redis
SET feature:enabled true
SET feature:enabled true
~~~

Hai lần đặt cùng giá trị tạo cùng trạng thái cuối. Ngược lại:

~~~redis
INCR orders:created
INCR orders:created
~~~

Hai lần `INCR` làm bộ đếm tăng hai lần; tự thân command này **không lũy đẳng** nếu mục tiêu là “một business event chỉ được đếm một lần”.

Ở tầng HTTP:

- `PUT /profiles/101` với cùng body *có thể* được thiết kế lũy đẳng.
- `POST /orders` thường tạo tài nguyên mới và không tự lũy đẳng.
- HTTP method không đủ để kết luận nghiệp vụ chắc chắn lũy đẳng: một `PUT` có thể có side effect như gửi email hoặc append log nếu code viết không đúng.

**Idempotency key** giúp định danh **cùng một ý định thao tác** khi request được gửi lại. Nó không tự biến code nghiệp vụ thành giao dịch nguyên tử; server phải thiết kế cách sử dụng khóa một cách chính xác.

### 1.2. Ba khái niệm dễ nhầm

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Deduplication** | Đã thấy identifier/event này chưa? | Bỏ qua webhook có cùng event ID |
| **Idempotency** | Nếu cùng thao tác được yêu cầu lại, kết quả/tác dụng phụ phải thế nào? | Trả lại cùng order ID cho cùng Idempotency-Key |
| **Mutual exclusion / lock** | Hai worker có được chạy vùng code cùng lúc không? | Chỉ một worker giữ lease xử lý key tại một thời điểm |

Một Redis lock có TTL có thể chặn hai request **đang đồng thời**, nhưng không tự biết request đã thành công trước đó. Một Redis set lưu “đã thấy key” có thể ngăn thực hiện lần hai nhưng không trả lại response cũ. Một hệ thống lũy đẳng hoàn chỉnh thường cần **trạng thái xử lý, dấu vết kết quả và quy tắc retry**.

## 2. Idempotency-Key là gì?

Client phát sinh một identifier ổn định cho **một logical operation**. Khi retry cùng ý định, client gửi **lại đúng khóa đó**.

Ví dụ HTTP:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 5ab802da-df68-414f-959c-ff41bbfd8f87

{
  "sku": "desk-01",
  "quantity": 2
}
~~~

Nếu client không nhận được response và retry, nó giữ nguyên header và body. Nếu người dùng chủ động tạo **một đơn hàng thứ hai**, client phát sinh Idempotency-Key mới.

### 2.1. Phân biệt khóa client với Redis key

Trong hệ thống thường có ít nhất hai khóa:

1. **Idempotency-Key do client cung cấp:** ví dụ một UUID hoặc token ngẫu nhiên.
2. **Redis key nội bộ:** tạo từ phạm vi nghiệp vụ và khóa client, ví dụ `idem:v1:7ac3...`.

Không nên dùng nguyên chuỗi do client cung cấp làm tên Redis key nếu thiếu validation và namespace. Redis key thường nên được tạo từ:

~~~text
Redis key = prefix + hash(
    authenticatedTenantId,
    HTTP operation / endpoint identity,
    client Idempotency-Key
)
~~~

Vì sao cần scope? Khách của tenant A và tenant B đều có thể gửi khóa `request-001` nhưng không nên bị coi là **cùng một yêu cầu**. Cùng một client key dùng cho `POST /orders` và `POST /refunds` cũng không nên đụng nhau.

### 2.2. Những đặc tính nên có của client key

- **Ổn định qua retry** của cùng một ý định.
- **Khác nhau** cho các ý định mới.
- **Khó đoán hoặc có entropy đủ tốt**, ví dụ UUID v4.
- **Được giới hạn độ dài và ký tự hợp lệ** để bảo vệ bộ nhớ và logging.
- Không chứa access token, mật khẩu, thông tin thẻ hay dữ liệu nhạy cảm.
- Có một **khoảng thời gian được hỗ trợ**: server không thể giữ vô hạn mọi khóa đã sử dụng.

Không dùng timestamp tính tới giây hoặc mã sản phẩm làm Idempotency-Key chung nếu nhiều thao tác độc lập có thể cùng có giá trị đó. Cũng không tạo khóa mới cho **mỗi lần retry**: như vậy server không có dấu hiệu để biết chúng là cùng một logical operation.

### 2.3. Tại sao không dùng request fingerprint làm Idempotency-Key duy nhất?

Hai lần đặt cùng SKU và cùng số lượng **có thể** là hai đơn hàng thực sự khác nhau:

~~~text
Lần 1: mua 1 bàn desk-01
Lần 2: sau 1 giờ, mua thêm 1 bàn desk-01
~~~

Nếu server dùng hash body làm khóa duy nhất, lần 2 có thể bị coi là duplicate sai. Vì thế:

- **Client idempotency key** phân biệt logical operations.
- **Request fingerprint** xác nhận một key không bị dùng lại với payload **khác**.

Hai khái niệm bổ sung cho nhau chứ không thay thế nhau.

## 3. Các kết quả cần trả khi gặp một khóa đã tồn tại

Giả sử endpoint `POST /orders` nhận Idempotency-Key `K`. Cần xác định quy tắc xử lý:

| Tình huống | Điều cần làm | HTTP response có thể chọn |
|---|---|---|
| Chưa từng thấy `K` | Đăng ký quyền xử lý và thực thi | `201 Created` khi hoàn tất |
| Đã hoàn tất `K` với cùng fingerprint | Không thực hiện lại, trả **cùng kết quả trước** | Trả lại `201` + body/orderId đã lưu |
| `K` đang được worker khác xử lý | Không chạy side effect lần hai | `409 Conflict`, `202 Accepted` hoặc cách báo “in progress” đã công bố |
| `K` đã dùng với request khác | Từ chối tái sử dụng sai | `409 Conflict` |
| Redis/key store lỗi hoặc trạng thái không rõ | Không âm thầm coi như request mới | `503`/chính sách fail-closed; hoặc dùng sổ giao dịch bền vững |
| Khóa cũ đã hết TTL | Không còn được Redis dedupe nếu không có nguồn bền vững khác | Cần quy định retry window và đối soát |
| Business operation thất bại chắc chắn trước khi có side effect | Có thể cho retry theo policy | Chỉ khi phân biệt được lỗi chắc chắn và lỗi mơ hồ |
| Business operation có thể thành công nhưng response mất | Không được tùy tiện làm lại | Tra cứu trạng thái chuẩn hoặc dùng idempotency ở nguồn bền vững |

Việc chọn `202` hay `409` cho trạng thái đang chạy là một **hợp đồng API**, không phải quy tắc cứng của Redis. Có thể cung cấp `Location` để client tra trạng thái và `Retry-After` khi hợp lý, nhưng cách tốt nhất phụ thuộc kiểu request và thời gian xử lý.

### 3.1. Cần lưu response gì?

Nếu mục tiêu là replay cùng kết quả, một bản ghi hoàn tất có thể lưu:

- HTTP status, ví dụ `201`.
- Response body đã được chuẩn hóa hoặc chính xác như lần đầu.
- Một tập headers phù hợp như `Location`.
- Business resource ID, ví dụ `orderId`.
- Fingerprint của request.
- Thời điểm tạo/hoàn tất và version schema.

Không nên lưu mọi HTTP header vô điều kiện, vì các header như session cookie, token hoặc trace identifier có thể không phù hợp để replay. Khi trả lại, cần tái áp dụng **authorization** cho caller hiện tại. Idempotency record không được trở thành cách để người dùng khác đọc response nhạy cảm chỉ vì đoán được một khóa.

## 4. Mô hình trạng thái: NEW → PROCESSING → SUCCEEDED

Một thiết kế thực tế dùng ít nhất hai trạng thái được lưu:

- **PROCESSING:** một worker đã claim khóa và đang xử lý.
- **SUCCEEDED:** operation thành công, có response để replay.

Có thể bổ sung:

- **FAILED_FINAL:** thất bại xác định, không nên retry cùng key nếu hợp đồng yêu cầu lưu lỗi cuối cùng.
- **RECONCILIATION_REQUIRED:** kết quả không rõ, cần đối soát với nguồn chuẩn.
- **EXPIRED:** trạng thái không còn trong Redis; đây thường là sự **vắng mặt của key**, không nhất thiết một giá trị thật lưu trong Redis.

~~~mermaid
flowchart TD
    START["Request (tenant, operation, key, fingerprint)"] --> CLAIM{"SET key PROCESSING NX EX"}
    CLAIM -- "Tạo thành công" --> PROCESS["Worker sở hữu lease"]
    CLAIM -- "Key đã tồn tại" --> GET["Đọc state/fingerprint"]
    GET --> FINGER{"Fingerprint khớp?"}
    FINGER -- "Không" --> CONFLICT["409: key dùng cho payload khác"]
    FINGER -- "Có" --> STATE{"State?"}
    STATE -- "SUCCEEDED" --> REPLAY["Trả response đã lưu"]
    STATE -- "PROCESSING" --> BUSY["Báo đang xử lý / poll / retry sau"]
    STATE -- "FAILED_FINAL" --> FINAL["Trả kết quả lỗi cuối đã lưu"]
    PROCESS --> BUSINESS["Thực hiện nghiệp vụ có idempotency tại nguồn"]
    BUSINESS --> SUCCESS["Nguồn xác nhận thành công"]
    SUCCESS --> CAS["Lua CAS: PROCESSING -> SUCCEEDED"]
    CAS --> RETURN["Trả response"]
    BUSINESS --> UNKNOWN["Lỗi hoặc outcome không chắc chắn"]
    UNKNOWN --> RECON["Không xóa bừa: đối soát trạng thái"]
~~~

Bản ghi `PROCESSING` cần chứa **owner token** hoặc một mã claim ngẫu nhiên để nhận biết worker nào có quyền chuyển trạng thái. Nếu không kiểm tra owner, worker cũ có thể ghi đè kết quả mới sau khi lease hết hạn.

### 4.1. Vì sao cần trạng thái PROCESSING?

Nếu chỉ lưu kết quả sau khi xử lý:

~~~text
Worker A: GET idem:K -> không tồn tại
Worker B: GET idem:K -> không tồn tại
Worker A: tạo order o-101
Worker B: tạo order o-102
Worker A: SET idem:K = o-101
Worker B: SET idem:K = o-102
~~~

Bản ghi cuối cùng chỉ còn `o-102`, nhưng **hai side effects đã xảy ra**.

Để ngăn cả hai worker cùng bước vào đoạn xử lý, phải có một thao tác claim có điều kiện **nguyên tử** trước business operation.

## 5. Redis SET NX EX: thao tác claim nguyên tử

Redis hỗ trợ:

~~~redis
SET idem:v1:example "PROCESSING:token-abc" NX EX 60
~~~

Ý nghĩa:

- `NX`: chỉ ghi khi key **chưa tồn tại**.
- `EX 60`: key được gắn TTL 60 giây cùng trong một command.
- Nếu ghi thành công, client có thể coi đã claim được key.
- Nếu key đã tồn tại, Redis không ghi đè và trả kết quả không thành công cho điều kiện NX.

Trong Spring Data Redis:

~~~java
Boolean claimed = stringRedisTemplate.opsForValue()
        .setIfAbsent(
                "idem:v1:example",
                "PROCESSING:token-abc",
                Duration.ofSeconds(60));

if (Boolean.TRUE.equals(claimed)) {
    // Client đã claim.
} else if (Boolean.FALSE.equals(claimed)) {
    // Key đã tồn tại; cần đọc trạng thái.
} else {
    // Một số ngữ cảnh pipelining/transaction không trả ngay
    // Boolean; không được nhầm null với false hoặc true.
}
~~~

Với lời gọi thông thường ngoài pipeline/transaction, kết quả thường là Boolean. Dùng `Boolean.TRUE.equals(...)` tránh lỗi `NullPointerException` khi kết quả null trong ngữ cảnh đặc biệt.

### 5.1. Vì sao không dùng GET rồi SET?

Không an toàn:

~~~java
if (redis.opsForValue().get(key) == null) {
    redis.opsForValue().set(key, "PROCESSING");
    performBusinessAction();
}
~~~

Hai worker có thể cùng nhìn thấy key chưa tồn tại trước khi một worker gọi SET. Đây là lỗi *check-then-act race*.

Tương tự, tránh:

~~~java
if (redis.opsForValue().setIfAbsent(key, token)) {
    redis.expire(key, Duration.ofSeconds(60));
}
~~~

nếu API hỗ trợ `setIfAbsent(key, value, Duration)`. Khi SETNX và EXPIRE là **hai commands**, crash ở giữa có thể tạo khóa không TTL, gây kẹt mãi. `SET ... NX EX ...` thực hiện điều kiện và TTL trong một command.

### 5.2. Claim là lease, không phải quyền sở hữu vĩnh viễn

Một key PROCESSING với TTL 60 giây nghĩa là sau 60 giây key có thể hết hạn, ngay cả khi worker ban đầu vẫn đang xử lý.

~~~text
t=00  Worker A claim key K với TTL 60s
t=10  A bắt đầu gọi một service chậm
t=60  Redis key K hết hạn
t=61  Worker B claim lại key K thành công
t=62  A vẫn đang chạy
t=63  B cũng đang chạy
~~~

Redis đã làm đúng theo TTL. **SET NX EX không thể đảm bảo tuyệt đối chỉ một side effect** nếu lease ngắn hơn thời gian xử lý, hoặc worker bị pause, mất mạng, failover.

Giải pháp phải xét tầng nghiệp vụ:

- Sử dụng lease đủ phù hợp và có thể gia hạn khi cần.
- CAS theo owner token khi hoàn tất.
- Dùng operation ID/idempotency key ở **nguồn thực hiện side effect**.
- Dùng unique constraint/transaction của database nếu thao tác đòi bền vững.
- Dùng fencing/version token khi tài nguyên downstream có hỗ trợ từ chối chủ sở hữu cũ.

Không trình bày Redis lease như “exactly-once” của một business transaction.

## 6. Thiết kế Redis key, fingerprint và thời gian sống

### 6.1. Tên Redis key nội bộ

Một mẫu:

~~~text
idem:<schema-version>:<sha256(scope + client-key)>
~~~

Trong đó scope có thể bao gồm:

~~~text
authenticated tenant ID
+ operation ID (POST /orders, POST /refunds...)
+ API contract version
+ client Idempotency-Key
~~~

Ví dụ:

~~~text
idem:v1:9d99d7d3a8ae9d52...
~~~

SHA-256 là công cụ tạo khóa có độ dài ổn định và giảm việc lộ identifier thô trong Redis key. Nó **không thay thế** xác thực hoặc kiểm tra quyền: client có thể biết Idempotency-Key nhưng không có quyền xem đơn hàng của tenant khác.

### 6.2. Fingerprint của nội dung request

Server tính fingerprint ổn định:

~~~text
fingerprint = SHA-256(
    operation contract version
    + canonicalized business request body
)
~~~

Cùng một key + cùng fingerprint => có thể là retry cùng ý định.

Cùng một key + fingerprint khác => từ chối `409 Conflict`.

**Canonicalization cần được định nghĩa**. Hai JSON sau có thể là cùng một business request dù bytes khác nhau:

~~~json
{"sku":"desk-01","quantity":2}
~~~

~~~json
{
  "quantity": 2,
  "sku": "desk-01"
}
~~~

Nếu hash raw HTTP body, hai payload trên ra fingerprint khác nhau. Có thể chọn:

- Parse vào DTO với field cố định, serialize canonical dưới quy tắc ổn định.
- Định nghĩa thứ tự field rõ ràng trước khi hash.
- Chuẩn hóa Unicode, số thập phân, currency, timezone khi nghiệp vụ yêu cầu.
- Bỏ qua metadata không ảnh hưởng kết quả như tracing header.
- Bắt buộc giữ những field **có tác động nghiệp vụ** như amount, currency, shipping address, discount code.

Không tùy tiện chuẩn hóa hai request khác nhau thành cùng fingerprint nếu một field thực tế ảnh hưởng side effect.

### 6.3. TTL cho PROCESSING và TTL cho kết quả hoàn tất

Hai TTL không nên bị đánh đồng.

| Loại trạng thái | Mục tiêu | Cách chọn TTL |
|---|---|---|
| `PROCESSING` | Lease để tránh worker khác chạy đồng thời | Theo timeout xử lý, watchdog và yêu cầu recovery |
| `SUCCEEDED` | Replay result khi client retry | Theo retry window công bố, yêu cầu nghiệp vụ và thời gian đối soát |
| `FAILED_FINAL` | Replay lỗi xác định nếu cần | Theo hợp đồng API |
| Bản ghi bền vững trong DB | Bảo đảm cùng business operation không nhân đôi | Theo retention nghiệp vụ/compliance, không đồng nhất với Redis TTL |

Ví dụ đặt `PROCESSING` 2 phút và `SUCCEEDED` 24 giờ **chỉ là lựa chọn minh họa**. Nếu partner có quyền retry trong 7 ngày, lưu kết quả Redis 24 giờ không đủ; cần một durable idempotency ledger hoặc retention tương ứng.

TTL ngắn quá khiến retry muộn có thể được coi là request mới. TTL dài quá gây tích lũy key trong RAM. Cần theo dõi số lượng keys, giá trị response, retention và eviction.

## 7. Một Redis record duy nhất: dễ chuyển trạng thái nguyên tử

Có hai hướng lưu trữ:

1. **Một Redis String key** chứa JSON trạng thái PROCESSING hoặc SUCCEEDED.
2. **Nhiều Redis keys**: một key lock/lease, một key kết quả và metadata.

Để tránh cửa sổ trạng thái không đồng bộ giữa các key, ví dụ ưu tiên **một key JSON** và chuyển trạng thái bằng Lua compare-and-set.

### 7.1. Bản ghi PROCESSING

~~~json
{
  "state": "PROCESSING",
  "fingerprint": "sha256-of-request",
  "ownerToken": "f7238bd1-c536-48f1-99ad-f3a30bb842fa",
  "httpStatus": null,
  "responseBody": null
}
~~~

### 7.2. Bản ghi SUCCEEDED

~~~json
{
  "state": "SUCCEEDED",
  "fingerprint": "sha256-of-request",
  "ownerToken": "f7238bd1-c536-48f1-99ad-f3a30bb842fa",
  "httpStatus": 201,
  "responseBody": "{\"orderId\":\"o-101\",\"status\":\"CREATED\"}"
}
~~~

Lưu response body dưới dạng JSON string bên trong một JSON record là một lựa chọn có chủ đích: client nhận lại body ban đầu, còn service quản lý metadata. Có thể lưu business result theo một structure khác nếu muốn giảm dung lượng và kiểm soát schema.

**Điểm cần thiết kế:** phần response được lưu phải đáp ứng chính sách bảo mật, kiểm soát kích thước và versioning. Nếu response chứa thông tin cá nhân, cần hạn chế quyền Redis, TTL, log và có thể cân nhắc chỉ lưu resource ID rồi dựng response từ database ở lần replay.

### 7.3. Không dùng Java object serialization không kiểm soát

Trong ví dụ này chọn:

- `StringRedisTemplate` để Redis key/value là UTF-8 String.
- Jackson `ObjectMapper` để chuyển `IdempotencyRecord` ↔ JSON.
- Version trong key prefix `idem:v1:`.
- JSON payload không chứa tên Java class nội bộ.

Nếu đổi định dạng lưu record, cần duy trì khả năng đọc dữ liệu cũ trong khoảng TTL hoặc thay prefix version. Không nên đổi từ JSON sang JDK serialization trên cùng namespace mà không có kế hoạch.

## 8. Lua CAS: chỉ chủ sở hữu mới được ghi kết quả

Giả sử worker A claim thành công. Trước khi xử lý xong, lease hết hạn và worker B claim. Nếu A cứ gọi:

~~~redis
SET idem:K "{\"state\":\"SUCCEEDED\",...}"
~~~

A có thể ghi đè trạng thái mà B đang sở hữu. Nguy hiểm hơn, A có thể ghi một response cũ sau khi B đã hoàn tất.

Giải pháp là **compare-and-set** ngay trên Redis server. Chỉ thay trạng thái khi giá trị hiện tại vẫn là bản PROCESSING mà worker đã claim.

### 8.1. Script kết thúc có điều kiện

~~~lua
-- KEYS[1]: Redis idempotency key
-- ARGV[1]: JSON PROCESSING mà owner đã lưu
-- ARGV[2]: JSON SUCCEEDED muốn ghi
-- ARGV[3]: TTL của kết quả, milliseconds

if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end

redis.call('PSETEX', KEYS[1], tonumber(ARGV[3]), ARGV[2])
return 1
~~~

Mọi bước `GET`-so sánh-`PSETEX` chạy trong **một Lua script atomic** trên Redis server; worker cũ không thể ghi đè một giá trị khác khi script chạy.

Script chỉ truy cập **một Redis key**, thuận tiện cả khi dùng Redis Cluster vì không có chuyện hai key thuộc hai slots khác nhau. Nếu mở rộng script để truy cập thêm Redis keys, phải tuân thủ cluster hash slot constraints.

### 8.2. Tại sao so sánh cả JSON có thể dùng được?

Trong mẫu, worker giữ nguyên **chuỗi JSON chính xác** mà nó đã đưa vào Redis ở bước claim. Script so sánh nguyên byte string với current value. Điều này an toàn cho CAS nếu không có code khác sửa record khi đang PROCESSING.

Trong hệ thống có heartbeat cập nhật TTL hoặc thêm metadata động bằng cách viết lại JSON, so sánh toàn chuỗi có thể không phù hợp vì record đã thay đổi. Khi đó nên:

- Lưu token ở field ổn định trong Redis Hash và dùng Lua `HGET` so sánh token.
- Hoặc dùng một model JSON có token được parse/xử lý phù hợp tại server.
- Thiết kế CAS tách giữa **owner token** và **trạng thái** thay vì phụ thuộc toàn bộ value.
- Không cho một worker gia hạn lease của worker khác.

CAS bảo vệ việc **ghi record kết quả trong Redis**, không tự bảo vệ side effect đã chạy ở database/payment provider trước khi CAS.

## 9. Ví dụ Spring Boot: các lớp dữ liệu và hợp đồng nghiệp vụ

Ví dụ dùng **Java 17+**, Spring Boot với Spring Data Redis imperative, Jackson và Spring Web. Mục tiêu là minh họa một idempotency gate rõ ràng, không tuyên bố Redis là nguồn bảo đảm exactly-once cho giao dịch quan trọng.

### 9.1. Dependency

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Spring Boot thường cung cấp `StringRedisTemplate` khi có connection factory thích hợp. Jackson được cung cấp qua web starter trong cấu hình phổ biến.

Kết nối Redis dùng YAML:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Nếu production chạy cluster, Sentinel, Redis managed/TLS hoặc ACL, cần thay cấu hình tương ứng. Redis idempotency store cần monitoring, timeout và chính sách RAM/eviction cụ thể.

### 9.2. Request và kết quả nghiệp vụ

~~~java
// File CreateOrderRequest.java
public record CreateOrderRequest(
        String sku,
        int quantity) {
}

// File OrderReceipt.java
public record OrderReceipt(
        String orderId,
        String status) {
}
~~~

Hợp đồng lớp nghiệp vụ:

~~~java
// File OrderApplicationService.java
public interface OrderApplicationService {

    OrderReceipt createOrGet(
            String tenantId,
            String operationKey,
            String requestFingerprint,
            CreateOrderRequest request);
}
~~~

**Đây là interface ứng dụng, không phải API có sẵn từ Spring Data Redis.**

`createOrGet` phải có semantics bền vững: nếu cùng `tenantId + operationKey` được gọi lại, nó trả về đơn hàng đã ghi thay vì tạo đơn mới, đồng thời kiểm tra fingerprint. Trong hệ thống quan trọng, implementation cần transaction và unique constraint ở database hoặc idempotency do payment provider hỗ trợ.

Nếu nghiệp vụ không có tầng đảm bảo này, Redis gate bên ngoài chỉ là **best effort deduplication trong thời gian TTL**.

### 9.3. Redis record có thể serialize thành JSON

~~~java
// File IdempotencyRecord.java
public record IdempotencyRecord(
        String state,
        String fingerprint,
        String ownerToken,
        Integer httpStatus,
        String responseBody) {
}
~~~

Trong thực tế có thể bổ sung createdAt, completedAt, schemaVersion, businessResourceId, correlationId và checksum kết quả. Không cần lưu raw request body nếu fingerprint đã đủ để xác minh reuse trong policy của API.

## 10. Viết lớp Redis gate: claim, đọc, hoàn tất

### 10.1. Cài đặt

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisIdempotencyGate {

    private static final Duration LEASE = Duration.ofMinutes(2);
    private static final Duration RESULT_TTL = Duration.ofHours(24);

    private static final DefaultRedisScript<Long> FINISH_SCRIPT =
            new DefaultRedisScript<>();

    static {
        FINISH_SCRIPT.setScriptText("""
            if redis.call('GET', KEYS[1]) ~= ARGV[1] then
                return 0
            end
            redis.call('PSETEX', KEYS[1], tonumber(ARGV[3]), ARGV[2])
            return 1
            """);
        FINISH_SCRIPT.setResultType(Long.class);
    }

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public RedisIdempotencyGate(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public String redisKey(
            String tenantId, String operation, String clientKey) {
        // Các giá trị đầu vào phải được validate trước khi gọi.
        String scoped = tenantId + "\u0000"
                + operation + "\u0000" + clientKey;
        return "idem:v1:" + sha256(scoped);
    }

    public Claim tryClaim(String key, String fingerprint) {
        String token = UUID.randomUUID().toString();

        IdempotencyRecord processing = new IdempotencyRecord(
                "PROCESSING", fingerprint, token, null, null);
        String json = encode(processing);

        Boolean claimed =
                redis.opsForValue().setIfAbsent(key, json, LEASE);

        if (Boolean.TRUE.equals(claimed)) {
            return new Claim(true, json, processing);
        }

        if (Boolean.FALSE.equals(claimed)) {
            return new Claim(false, null, read(key));
        }

        throw new IllegalStateException(
                "Redis claim result unavailable");
    }

    public IdempotencyRecord read(String key) {
        String json = redis.opsForValue().get(key);
        if (json == null) {
            return null;
        }
        try {
            return mapper.readValue(json, IdempotencyRecord.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot decode idempotency record", ex);
        }
    }

    public boolean finish(
            String key,
            String expectedProcessingJson,
            IdempotencyRecord completed) {

        String completedJson = encode(completed);

        Long changed = redis.execute(
                FINISH_SCRIPT,
                List.of(key),
                expectedProcessingJson,
                completedJson,
                Long.toString(RESULT_TTL.toMillis()));

        return Long.valueOf(1L).equals(changed);
    }

    private String encode(IdempotencyRecord record) {
        try {
            return mapper.writeValueAsString(record);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize idempotency record", ex);
        }
    }

    public static String sha256(String value) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public record Claim(
            boolean acquired,
            String expectedProcessingJson,
            IdempotencyRecord current) {
    }
}
~~~

Giải thích:

- `tryClaim` dùng một lệnh Redis `SET NX EX` cho state PROCESSING và TTL.
- Khi key đã tồn tại, nó đọc state/fingerprint để caller quyết định replay, conflict hoặc báo in-progress.
- `finish` sử dụng Lua CAS để không ghi đè state của owner khác.
- `sha256` tạo tên Redis key nội bộ có độ dài cố định.
- `IdempotencyRecord` được encode JSON bằng Jackson và Redis String serializer, không sử dụng Java object serialization mặc định.

### 10.2. Một cửa sổ race nhỏ khi đọc existing record

Kịch bản:

~~~text
SET NX trả false: key tồn tại
Ngay sau đó key hết TTL
GET trả null
~~~

Điều này có thể xảy ra vì `SET NX` và `GET` của nhánh existing là hai commands khác nhau. **Không được** suy ra `GET null` đồng nghĩa request chưa từng được xử lý và chạy nghiệp vụ ngay.

Caller có thể trả trạng thái tạm thời và yêu cầu retry, hoặc có cơ chế tra cứu durable ledger để quyết định. Nếu thử claim lại, phải chạy lại **atomic claim** chứ không tự bỏ qua.

### 10.3. Giới hạn khi lease hết giữa lúc xử lý

Lua CAS sẽ trả 0 nếu lease đã hết hoặc bị owner mới thay thế. Không được hiểu “CAS=0 nên nghiệp vụ trước đó chưa xảy ra”. Việc tạo đơn hàng có thể đã commit trước khi Redis từ chối ghi cache result.

Đó là lý do `OrderApplicationService.createOrGet` cần bảo đảm bền vững riêng. Redis gate giúp giảm lệnh xử lý trùng, **không phải nơi duy nhất bảo đảm một order được tạo đúng một lần**.

## 11. Service kết hợp Redis gate và nghiệp vụ

Ví dụ này trả trực tiếp `ResponseEntity<String>` để minh họa replay lại response body đã lưu.

~~~java
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class IdempotentOrderFacade {

    private static final Pattern IDEMPOTENCY_KEY =
            Pattern.compile("[A-Za-z0-9._-]{8,128}");

    private final RedisIdempotencyGate gate;
    private final OrderApplicationService orders;
    private final ObjectMapper mapper;

    public IdempotentOrderFacade(
            RedisIdempotencyGate gate,
            OrderApplicationService orders,
            ObjectMapper mapper) {
        this.gate = gate;
        this.orders = orders;
        this.mapper = mapper;
    }

    public ResponseEntity<String> create(
            String authenticatedTenantId,
            String clientKey,
            CreateOrderRequest request) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || clientKey == null
                || !IDEMPOTENCY_KEY.matcher(clientKey).matches()
                || request == null
                || request.sku() == null
                || !request.sku().matches("[A-Za-z0-9._-]{1,64}")
                || request.quantity() <= 0) {

            return ResponseEntity.badRequest()
                    .body("Invalid request or Idempotency-Key");
        }

        String operation = "POST:/api/orders:v1";
        String redisKey = gate.redisKey(
                authenticatedTenantId, operation, clientKey);

        // Với DTO này, encoding field theo một thứ tự rõ ràng.
        String fingerprint = RedisIdempotencyGate.sha256(
                "CreateOrder:v1\u0000"
                + request.sku() + "\u0000"
                + request.quantity());

        RedisIdempotencyGate.Claim claim =
                gate.tryClaim(redisKey, fingerprint);

        if (!claim.acquired()) {
            IdempotencyRecord existing = claim.current();

            if (existing == null) {
                // Key có thể vừa hết TTL giữa SET NX và GET.
                return ResponseEntity.status(503)
                        .body("State changed; retry safely");
            }

            if (!fingerprint.equals(existing.fingerprint())) {
                return ResponseEntity.status(409)
                        .body("Idempotency-Key reused with new payload");
            }

            if ("SUCCEEDED".equals(existing.state())) {
                return ResponseEntity
                        .status(existing.httpStatus())
                        .body(existing.responseBody());
            }

            if ("PROCESSING".equals(existing.state())) {
                return ResponseEntity.status(409)
                        .body("Request is still processing");
            }

            return ResponseEntity.status(503)
                    .body("Idempotency state requires reconciliation");
        }

        // Chỉ worker sở hữu claim đi tới nghiệp vụ.
        // Nguồn nghiệp vụ vẫn phải tự bảo đảm createOrGet lũy đẳng.
        OrderReceipt receipt = orders.createOrGet(
                authenticatedTenantId,
                clientKey,
                fingerprint,
                request);

        String body;
        try {
            body = mapper.writeValueAsString(receipt);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize order receipt", ex);
        }

        IdempotencyRecord completed = new IdempotencyRecord(
                "SUCCEEDED",
                fingerprint,
                claim.current().ownerToken(),
                201,
                body);

        boolean stored = gate.finish(
                redisKey,
                claim.expectedProcessingJson(),
                completed);

        if (!stored) {
            // Business operation có thể đã commit.
            // Tuyệt đối không tự tạo order lần hai.
            return ResponseEntity.status(503)
                    .body("Order outcome recorded; reconcile state");
        }

        return ResponseEntity.status(201).body(body);
    }
}
~~~

### 11.1. Phần nào là ví dụ và phần nào là cam kết?

- Code facade cho thấy **giao thức Redis gate**: claim → validate existing → gọi nghiệp vụ → CAS lưu kết quả.
- `OrderApplicationService` là dependency **bắt buộc do ứng dụng triển khai**.
- Giả định quan trọng: `orders.createOrGet(...)` **đã có** durable idempotency để phòng trường hợp Redis lease hết hạn/failover.
- Code minh họa chưa thêm controller, authentication, tracing, circuit breaker, logging, timeout và HTTP error mapping đầy đủ.
- Nhánh Redis lỗi sẽ ném exception qua template nếu không có handler phía API; production cần mapping thành response hợp lệ.
- Nhánh lỗi nghiệp vụ **không xóa claim ngay** vì chưa biết side effect có xảy ra hay chưa. Phải có recovery/reconciliation theo chính sách.

Nếu không có durable protection ở nguồn, đoạn mẫu **chỉ là lớp chống trùng best effort**, không được quảng bá là “exactly once” cho thanh toán hay đơn hàng.

### 11.2. Tạo endpoint trong Spring MVC

Một controller có thể lấy tenant ID từ principal đã xác thực, không tin một header `X-Tenant-Id` tùy ý do client gửi:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final IdempotentOrderFacade facade;
    private final TenantIdentity tenantIdentity;

    public OrderController(
            IdempotentOrderFacade facade,
            TenantIdentity tenantIdentity) {
        this.facade = facade;
        this.tenantIdentity = tenantIdentity;
    }

    @PostMapping
    public ResponseEntity<String> create(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderRequest request) {

        String tenantId = tenantIdentity.currentTenantId();
        return facade.create(tenantId, key, request);
    }
}
~~~

`TenantIdentity` là abstraction do ứng dụng tự cung cấp, lấy tenant đã được xác thực/ủy quyền từ security context.

Một request thiếu header cần được trả lỗi HTTP phù hợp do Spring MVC và API contract xử lý; không tự phát sinh key mới trên server trong trường hợp client **đang retry** mà không giữ được key cũ, vì server không thể biết hai request có cùng logical intent.

## 12. Đảm bảo bền vững: Redis gate không thay transaction nghiệp vụ

Đây là giới hạn quan trọng nhất.

### 12.1. Tình huống Redis lưu claim nhưng database tạo order thành công, rồi ứng dụng crash

~~~text
1. Redis: idem:K = PROCESSING (TTL 2 phút)
2. Database: tạo order o-101 và COMMIT
3. Spring instance crash trước khi ghi SUCCEEDED lên Redis
4. Client retry:
   - Trong TTL: nhận PROCESSING
   - Sau TTL: Redis key mất, có thể claim mới
5. Nếu nghiệp vụ không có idempotency ở DB:
   - Request sau TTL có thể tạo o-102
~~~

Lưu result ở Redis sau DB commit là **hai operations ở hai hệ thống khác nhau**. Redis CAS không tạo distributed transaction với database.

### 12.2. Bản ghi durable idempotency ledger

Với nghiệp vụ quan trọng, dùng một bảng idempotency trong database nguồn:

~~~sql
CREATE TABLE idempotency_operations (
    tenant_id         VARCHAR(64)  NOT NULL,
    operation_name    VARCHAR(100) NOT NULL,
    idempotency_key   VARCHAR(128) NOT NULL,
    request_hash      CHAR(64)     NOT NULL,
    state             VARCHAR(32)  NOT NULL,
    resource_id       VARCHAR(128),
    response_json     TEXT,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Một transaction thích hợp có thể:

1. Thử đăng ký operation bằng unique key.
2. Nếu key đã tồn tại, so sánh `request_hash`.
3. Nếu operation đã thành công, trả lại stored result/resource ID.
4. Nếu chưa xử lý và caller có quyền claim theo transaction/row-lock/version, tiến hành nghiệp vụ.
5. Ghi order cùng cập nhật operation thành `SUCCEEDED` **trong cùng DB transaction**, nếu nghiệp vụ và nguồn dữ liệu cho phép.
6. Commit.
7. Redis cache có thể được cập nhật sau commit để các retry sau nhanh hơn.

Điểm quan trọng là **unique constraint và transaction DB**, không phải việc dùng một bảng tên `idempotency_operations`. Phải đảm bảo việc tạo order và đánh dấu operation thành công thực sự nằm trong một commit boundary phù hợp.

### 12.3. Giao thức SQL minh họa

Một hướng phổ biến trên PostgreSQL:

~~~sql
INSERT INTO idempotency_operations (
    tenant_id, operation_name, idempotency_key,
    request_hash, state, created_at, updated_at
)
VALUES (
    :tenant_id, :operation_name, :key,
    :request_hash, 'PROCESSING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING;
~~~

Sau đó cần **kiểm tra số hàng được insert**, xử lý collision và giao dịch hiện có với locking/versioning thích hợp. Không được coi câu `INSERT ... ON CONFLICT DO NOTHING` riêng lẻ là đã đủ đảm bảo atomic giữa ledger và đơn hàng.

Trong một transaction thích hợp, tạo order và cập nhật:

~~~sql
UPDATE idempotency_operations
SET state = 'SUCCEEDED',
    resource_id = :order_id,
    response_json = :response_json,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND operation_name = :operation_name
  AND idempotency_key = :key;
~~~

Các SQL snippets là định hướng về uniqueness và commit boundary, không phải một stored procedure production hoàn chỉnh. Với transaction lock, lỗi deadlock, constraint và retry phải có chính sách rõ.

### 12.4. Khi có hệ thống thanh toán bên ngoài

Nếu side effect là gọi payment provider, transaction database **không thể tự commit nguyên tử với payment API**. Nên:

- Truyền idempotency key ổn định xuống provider **nếu provider hỗ trợ**.
- Lưu operation ID và trạng thái tại DB trước khi gọi provider.
- Nếu timeout, **tra cứu payment status** theo operation ID/provider request ID trước khi retry.
- Dùng outbox/saga/workflow để thực hiện side effect một cách có trạng thái và có thể khôi phục.
- Không giả định HTTP 504 nghĩa provider chắc chắn chưa thu tiền.

Idempotency phải được triển khai **tại ranh giới side effect**, không chỉ ở Redis API gateway.

## 13. Khác biệt giữa duplicate suppression và replay response

Một pattern rất nhẹ là:

~~~java
Boolean first = redis.opsForValue().setIfAbsent(
        "webhook:seen:" + eventId,
        "1",
        Duration.ofDays(2));

if (Boolean.TRUE.equals(first)) {
    processWebhook();
}
~~~

Cách này chỉ đánh dấu **đã nhìn thấy** sự kiện, không biết `processWebhook()` thành công hay không.

### 13.1. Vấn đề đánh dấu trước khi xử lý

~~~text
SETNX seen:event-101 = true   -> thành công
processWebhook()             -> lỗi giữa chừng
Webhook được gửi lại          -> bị chặn vì seen đã tồn tại
~~~

Một event **chưa xử lý thành công** bị coi là đã xử lý. Điều này có thể gây mất công việc.

### 13.2. Vấn đề đánh dấu sau khi xử lý

~~~text
Worker A: thấy event chưa xử lý
Worker B: thấy event chưa xử lý
A: process webhook
B: process webhook
A: set seen
B: set seen
~~~

Nếu không claim trước bằng nguyên tử, hai worker có thể xử lý cùng event.

### 13.3. Khi nào SET NX đơn giản có thể đủ?

Phù hợp với tín hiệu *best effort* mà việc bỏ lỡ hoặc trùng có thể chấp nhận, ví dụ một notification phụ ít quan trọng. Không dùng đơn thuần cho:

- Xác nhận thanh toán.
- Ghi sổ kế toán.
- Cấp quyền sử dụng có tính pháp lý.
- Chuyển tiền.
- Đồng bộ hàng tồn kho chuẩn.
- Những webhook bắt buộc được xử lý cuối cùng.

Với event quan trọng, sử dụng durable inbox/ledger và xác nhận xử lý sau khi side effect hoàn tất, kết hợp retry/idempotency.

## 14. Vì sao không chỉ dùng Redis distributed lock?

Một khóa phân tán theo mẫu:

~~~redis
SET lock:order:101 token-abc NX PX 30000
~~~

giúp **loại trừ lẫn nhau trong thời gian lease**. Nhưng nó không lưu business result và không bảo đảm giao dịch đã hoàn tất trước khi lease hết hạn.

### 14.1. Vấn đề owner cũ xóa lock mới

Không an toàn:

~~~text
t=0   Worker A lấy lock token=A
t=30  Lock A hết hạn
t=31  Worker B lấy lock token=B
t=32  Worker A gọi DEL lock (xóa lock của B)
t=33  Worker C cũng lấy được lock
~~~

Không dùng `DEL` vô điều kiện để giải phóng lock đã hết hạn hoặc đã thuộc owner khác.

### 14.2. Lua compare-and-delete

~~~lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
~~~

Chỉ xóa khi Redis value khớp owner token. Mẫu này giải quyết lỗi A xóa lock B, nhưng **không ngăn worker A đã bắt đầu side effect trước khi lease mất**. Tài nguyên downstream cần tự từ chối chủ sở hữu cũ nếu muốn bảo vệ tuyệt đối.

### 14.3. Fencing token

Một *fencing token* là sequence/version tăng đơn điệu được cấp cùng quyền thao tác, và **tài nguyên cuối cùng** phải lưu token cao nhất đã nhận, từ chối token nhỏ hơn.

~~~text
Worker A nhận fencing token 41
Worker A bị pause
Worker B nhận fencing token 42
Storage ghi nhận token 42 và thực hiện update B
Worker A trở lại với token 41
Storage từ chối update A
~~~

Chỉ tạo token trong Redis mà downstream không kiểm tra token thì **không có fencing effect**. Redis failover và durability cũng phải được cân nhắc nếu fencing sequence được giữ ở đó.

### 14.4. Redlock có thay unique constraint không?

Một số hệ thống sử dụng thuật toán distributed lock như Redlock. Dù triển khai lock theo thuật toán nào, nó không tự biến HTTP side effect, database commit và payment gateway thành một transaction nguyên tử. Với yêu cầu “tạo một đơn hàng duy nhất”, unique constraint và durable operation ID ở nguồn chuẩn thường là điều cần thiết.

## 15. Gia hạn lease PROCESSING an toàn

Một business operation có thể kéo dài hơn dự kiến, ví dụ chờ payment provider. Tăng TTL cố định lên hàng giờ làm retry bị kẹt lâu khi worker chết; giảm TTL quá ngắn tạo nguy cơ owner thứ hai.

Một chiến lược là **heartbeat** gia hạn lease trong khi worker đang sống và còn quyền sở hữu.

### 15.1. Chỉ owner được extend

Với JSON PROCESSING bất biến, có thể dùng Lua:

~~~lua
-- KEYS[1]: idempotency key
-- ARGV[1]: JSON value owner đã claim
-- ARGV[2]: lease mới, milliseconds

if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
~~~

Nếu current value đã bị worker khác thay đổi hoặc chuyển thành SUCCEEDED, script không gia hạn. Nếu heartbeat không nhận được kết quả vì timeout, không nên mặc nhiên suy ra quyền sở hữu vẫn còn.

### 15.2. Lease extension không đủ cho exactly-once

- JVM có thể bị pause quá lâu do GC.
- Network partition có thể khiến heartbeat không tới Redis.
- Redis failover có thể gây thay đổi trạng thái được nhìn thấy.
- Worker không biết lease đã mất nhưng vẫn có thể gửi side effect tới database.
- Người khác có thể claim sau TTL.

Vì vậy, gia hạn lease chủ yếu giúp giảm concurrent work. **Nguồn nghiệp vụ vẫn phải kiểm tra idempotency/fencing**.

### 15.3. Chiến lược recovery sau crash

Có thể lưu durable operation status tại DB. Khi gặp Redis PROCESSING quá lâu, một worker/reconciler kiểm tra:

1. Operation có tồn tại trong DB ledger không?
2. Đã có order/payment result tương ứng chưa?
3. Nếu thành công, khôi phục SUCCEEDED và replay response.
4. Nếu đang xử lý bởi worker khác, không thực thi lại.
5. Nếu thất bại xác định trước side effect, cho retry theo policy.
6. Nếu outcome mơ hồ, tra external provider hoặc đưa vào workflow cần đối soát.

Không chỉ chờ Redis key hết TTL rồi mặc định tạo operation mới.

## 16. Lựa chọn cache kết quả trả về: store response hay store resource ID?

### 16.1. Store nguyên response

~~~json
{
  "state": "SUCCEEDED",
  "httpStatus": 201,
  "responseBody": "{\"orderId\":\"o-101\",\"status\":\"CREATED\"}"
}
~~~

Ưu điểm:

- Retry có thể trả đúng response lần đầu.
- Không cần query database thêm.
- Có thể giữ semantics `201` và `Location` theo contract.

Hạn chế:

- Tốn RAM nếu response lớn.
- Có thể lưu dữ liệu nhạy cảm.
- Response có thể chứa timestamp hoặc field sau này thay đổi.
- Schema response có thể không đọc được sau nâng cấp code nếu serialize theo Java class.
- Cần chính sách giữ/đổi headers an toàn.

### 16.2. Store business result ID

~~~json
{
  "state": "SUCCEEDED",
  "resourceId": "o-101",
  "httpStatus": 201
}
~~~

Ưu điểm:

- Redis entry nhỏ hơn.
- Có thể đọc bản hiện hành từ database để dựng response.
- Tránh lưu bản sao nhạy cảm không cần thiết.

Hạn chế:

- Response sau retry có thể **khác body lần đầu** nếu dữ liệu đã thay đổi.
- Phải query nguồn để replay.
- Cần contract quy định “same business outcome” hay “same exact HTTP response”.

Với API cần replay **chính xác** response, lưu đủ status/body/headers an toàn. Với API chỉ yêu cầu không tạo tài nguyên trùng, lưu resource ID ở durable ledger và dựng response mới có thể là lựa chọn hợp lý.

### 16.3. Lỗi nào nên lưu?

Có thể phân loại:

| Loại kết quả | Có nên lưu terminal result? | Lý do |
|---|---|---|
| Tạo order thành công | Có | Bảo đảm retry trả cùng order |
| Business validation thất bại trước side effect | Tùy hợp đồng | Có thể trả lại cùng lỗi, hoặc cho client sửa request với key mới |
| `409` vì key reuse với body khác | Không ghi đè original record | Giữ contract của key gốc |
| Tạm thời `503` do Redis/database lỗi | Thường không chốt terminal | Cần cho phép recovery, nhưng phải tránh làm lại side effect không rõ |
| Payment provider trả outcome cuối xác định | Có thể lưu nếu đã xác minh | Giúp replay quyết định cuối |
| Network timeout tới payment provider | Không coi là “payment chưa xảy ra” | Cần đối soát trạng thái |

Không dùng một catch-all kiểu “bất cứ exception nào cũng SET FAILED rồi cho retry” nếu operation đã có thể commit thành công trước khi exception được ném.

## 17. Khi hai request cùng lúc tới hai pod Spring Boot

Giả sử Pod A và Pod B đều nhận cùng key `K`:

~~~mermaid
sequenceDiagram
    participant CA as Client request A
    participant A as Spring Pod A
    participant R as Redis
    participant B as Spring Pod B
    participant CB as Client request B
    participant DB as Database
    CA->>A: POST /orders K
    CB->>B: POST /orders K
    A->>R: SET K PROCESSING NX EX
    B->>R: SET K PROCESSING NX EX
    R-->>A: TRUE
    R-->>B: FALSE
    B->>R: GET K
    R-->>B: PROCESSING
    B-->>CB: In progress
    A->>DB: createOrGet(K)
    DB-->>A: order o-101
    A->>R: Lua CAS PROCESSING -> SUCCEEDED
    R-->>A: 1
    A-->>CA: 201 o-101
~~~

Vì `SET ... NX EX` là một Redis command, trong điều kiện một primary node đang xử lý các requests, chỉ một request claim key tại một thời điểm. Điều này giúp loại bỏ cuộc đua `GET`-rồi-`SET`.

Nhưng Redis replication/failover và lease expiration có thể khiến một claim đã được phản hồi thành công không còn được nhìn thấy sau failover hoặc key hết TTL. Vì vậy không coi sơ đồ là cam kết side effect đúng một lần trong mọi failure mode.

### 17.1. Request đã hoàn tất rồi client retry

~~~text
Request A: claim -> create order o-101 -> store SUCCEEDED
Request B: claim=false -> GET SUCCEEDED -> replay o-101
~~~

Không được gọi `orders.createOrGet(...)` lần nữa trong nhánh replay nếu kết quả đã có, trừ khi hợp đồng chủ động tái xác minh với nguồn chuẩn.

### 17.2. Request đang chạy lâu

Có thể báo:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"REQUEST_IN_PROGRESS"}
~~~

Hoặc thiết kế API async:

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/op-101
~~~

Nếu có endpoint lấy status, nó phải kiểm tra quyền truy cập và không làm lộ response của tenant khác.

## 18. Redis Cluster và khóa lũy đẳng

Một key đơn:

~~~text
idem:v1:<hash>
~~~

được Redis Cluster phân bố vào một hash slot. `SET NX`, `GET` và Lua CAS chỉ tham chiếu **một key** nên không gặp `CROSSSLOT` do nhiều key.

Nếu ứng dụng tạo thêm:

~~~text
idem:lock:<hash>
idem:result:<hash>
idem:metadata:<hash>
~~~

và muốn xử lý nhiều key atomically trong một script, phải dùng **cùng hash tag**:

~~~text
idem:{op-101}:lock
idem:{op-101}:result
idem:{op-101}:metadata
~~~

Nhưng tag có thể làm tập trung tải. Tốt nhất thường là **một Redis key chứa state/result đủ nhỏ** nếu phù hợp, vì giảm số command và giảm yêu cầu cross-key atomicity.

### 18.1. Tại sao không dùng một tag toàn cục?

Không nên đặt:

~~~text
idem:{all}:request-1
idem:{all}:request-2
idem:{all}:request-3
~~~

Tất cả keys cùng tag `all` rơi vào một hash slot và có thể gây hot shard. Hash tag nên dùng theo operation/aggregate nhỏ nhất thật sự cần co-location, không theo toàn hệ thống.

### 18.2. Lua CAS và cluster failover

Lua CAS chỉ bảo vệ atomic transition **trên primary node xử lý key tại thời điểm đó**. Không có distributed transaction với database và không bảo đảm một bản ghi vừa xác nhận đã được sao chép bền vững sang replica trước failover theo mọi cấu hình.

Nếu business yêu cầu durability mạnh, Redis chỉ nên là một lớp tăng tốc và trạng thái chuẩn phải ở hệ thống durable phù hợp.

## 19. Redis expiration, eviction và quản trị bộ nhớ

Một hệ thống có hàng triệu Idempotency-Key mới mỗi ngày có thể tạo rất nhiều Redis keys.

### 19.1. Ước lượng bộ nhớ

Ví dụ:

~~~text
Tốc độ:              100 requests/giây
Retention kết quả:    24 giờ
Số keys ước lượng:    100 × 86.400 = 8.640.000 keys
~~~

Nếu mỗi entry có payload vài trăm bytes cộng overhead key/object/allocator, tổng bộ nhớ có thể rất lớn. Không lấy riêng độ dài JSON làm tổng RAM thật. Cần benchmark và đo Redis `used_memory`/memory fragmentation.

Một số lựa chọn:

- TTL phù hợp cửa sổ client retry và đối soát.
- Lưu result ID thay vì toàn bộ HTTP body nếu hợp đồng cho phép.
- Không đưa request body thô/PII vào key.
- Giới hạn retention ở Redis và chuyển kết quả bền vững sang DB.
- Dùng namespace/version rõ ràng.
- Monitor memory, hit/miss và eviction.

### 19.2. Eviction có thể phá idempotency window

Giả sử `SUCCEEDED` có TTL 24 giờ. Nếu Redis chạy `allkeys-lru` và thiếu RAM, entry có thể bị **evict sau 5 phút**. Một retry sau 6 phút sẽ thấy key không tồn tại và claim mới.

Do đó:

> **TTL 24 giờ không đồng nghĩa Redis cam kết giữ một idempotency record 24 giờ.**

Nếu Redis là lớp duy nhất chống trùng cho nghiệp vụ nhạy cảm, eviction hoặc mất dữ liệu do failover có thể làm vi phạm đảm bảo. Cần durable ledger hoặc memory/eviction policy phù hợp với độ tin cậy nghiệp vụ, và ngay cả `noeviction` vẫn có thể khiến write thất bại khi đầy RAM.

### 19.3. Các metric Redis hữu ích

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
~~~

Một số managed Redis có thể hạn chế `CONFIG GET`; dùng control plane/monitoring thay thế.

Đặc biệt theo dõi:

- `evicted_keys`.
- `expired_keys`.
- `used_memory`.
- Error rates khi `SET NX`/Lua/GET.
- Timeouts và reconnect.
- Claim contention và số lần xử lý lại.

Không dùng `KEYS idem:*` liên tục trong production lớn để thống kê; nên dùng application metrics, Redis monitoring và `SCAN` có kiểm soát.

## 20. Theo dõi và đo hành vi idempotency

Nên có metrics ở tầng application:

| Metric | Ý nghĩa |
|---|---|
| `idempotency_claim_total{result="acquired"}` | Số operation mới bắt đầu |
| `idempotency_claim_total{result="existing"}` | Số lần key đã tồn tại |
| `idempotency_replay_total` | Số lần trả lại response đã có |
| `idempotency_inflight_conflict_total` | Số request trùng khi đang xử lý |
| `idempotency_payload_conflict_total` | Số key bị tái sử dụng với payload khác |
| `idempotency_cas_failed_total` | Hoàn tất nhưng owner/state không còn khớp |
| `idempotency_reconcile_total` | Số operation cần đối soát |
| `idempotency_store_error_total` | Redis errors hoặc serialization errors |
| `idempotency_processing_duration` | Thời gian từ claim tới kết quả nghiệp vụ |
| `idempotency_response_size_bytes` | Kích thước payload kết quả được lưu |

Không đưa Idempotency-Key thô, request hash hoặc user ID có cardinality cao vào metric labels. Có thể log một identifier đã hash hoặc truncate phục vụ điều tra, nhưng phải giữ chính sách bảo vệ dữ liệu.

### 20.1. Structured logs

Một log hợp lý:

~~~json
{
  "operation": "POST:/api/orders:v1",
  "state": "SUCCEEDED",
  "redisKeySuffix": "a5f...e90",
  "businessResourceId": "o-101",
  "event": "IDEMPOTENCY_COMPLETED"
}
~~~

Không log toàn bộ payment details, card data hoặc access token. Mục tiêu log là biết operation nào được claim/replayed/conflicted và có thể liên kết với transaction nguồn.

### 20.2. Tín hiệu cảnh báo

- `CAS failed` tăng đột biến: lease có thể quá ngắn, Redis failover hoặc owner bị mất.
- `PROCESSING` kéo dài: business service chậm hoặc workflow crash.
- Payload conflicts tăng: client có thể tái sử dụng key sai.
- Evictions tăng: TTL không còn là giới hạn retention đáng tin.
- Redis errors tăng: nguy cơ fail-open sai hoặc không thể claim.
- Database unique constraint conflicts tăng: nhiều requests đi vòng qua Redis gate hoặc bị retry sau TTL.
- Replay rate tăng rất cao: client retry storm hoặc network issue.

## 21. Testing: xác nhận cả concurrency và failure modes

### 21.1. Bộ thử nghiệm tối thiểu

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Một request mới | Claim thành công, tạo một order, lưu SUCCEEDED |
| Retry cùng key/body sau khi hoàn tất | Không tạo order khác, trả cùng orderId |
| Hai request đồng thời cùng key/body | Chỉ một request claim tại thời điểm ban đầu, request kia nhận processing/replay |
| Cùng key nhưng body khác | `409`, không ghi đè record gốc |
| Cùng body nhưng key mới | Cho phép tạo operation mới |
| Cùng key của hai tenant | Độc lập nhờ scope |
| Redis GET trả null ngay sau claim=false | Không chạy business mù |
| Worker crash sau claim, trước side effect | Lease hết hoặc recovery cho phép xử lý lại an toàn |
| Crash sau DB commit, trước Redis SUCCEEDED | Durable ledger ngăn tạo order thứ hai |
| Lease hết khi worker cũ đang xử lý | Redis CAS từ owner cũ thất bại; DB vẫn bảo vệ side effect |
| Redis evict SUCCEEDED trước TTL | Durable ledger vẫn ngăn duplicate |
| Redis outage | Fail-closed hoặc fallback durable ledger theo policy; không tạo duplicate |
| Retry của payment provider timeout | Tra cứu outcome trước khi gửi lại nếu không có provider idempotency |

### 21.2. Một ví dụ về kiểm tra duplicate response

Giả sử lần đầu:

~~~http
POST /api/orders
Idempotency-Key: 5ab802da-df68-414f-959c-ff41bbfd8f87
Content-Type: application/json

{"sku":"desk-01","quantity":2}
~~~

Server trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"o-101","status":"CREATED"}
~~~

Lần thứ hai, **cùng key và cùng request**:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"o-101","status":"CREATED"}
~~~

Không xuất hiện `o-102` trong database.

Nếu cùng key nhưng `quantity=3`:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"IDEMPOTENCY_KEY_REUSED"}
~~~

### 21.3. Test cạnh tranh bằng nhiều workers

Một test tích hợp có thể khởi động nhiều futures/request threads gửi cùng key, nhưng chỉ quan sát **một order ID** sau khi mọi requests hoàn tất hoặc được replay. Không đủ chỉ kiểm tra bao nhiêu lần Redis SET NX trả TRUE: vẫn cần kiểm tra durable side effect tại nguồn.

Khi có Redis Cluster, thử failover/connection interruption trên môi trường staging để xác định rủi ro mất claim/result. Không mô phỏng “network success” bằng mock rồi coi đó là bằng chứng durability.

### 21.4. Test TTL

Một test có thể tạo PROCESSING với TTL ngắn để quan sát `PTTL` rồi kiểm tra CAS không được phép thay state sau khi owner token không còn khớp. Tuy nhiên test này **không** chứng minh lũy đẳng end-to-end nếu operation có external side effect. Phải có test ledger/transaction và recovery tương ứng.

## 22. Một số mô hình ứng dụng thực tế

### 22.1. Tạo đơn hàng qua REST API

**Bối cảnh:** client retry khi timeout.

**Cấu trúc khuyến nghị:**

- Client tạo Idempotency-Key cho từng lần nhấn xác nhận đặt hàng.
- Redis `SET NX EX` giảm việc xử lý đồng thời.
- Database có unique operation key và order creation trong transaction thích hợp.
- Redis lưu response để replay nhanh.
- Retry sau khi Redis mất record vẫn kiểm tra database trước khi tạo mới.

Redis là **fast-path coordination + response cache**, database là **nguồn quyết định trùng hay không**.

### 22.2. Webhook thanh toán

**Bối cảnh:** payment provider phát lại cùng event nhiều lần và có thể phát sự kiện đến sai thứ tự.

**Cấu trúc khuyến nghị:**

- Lấy `providerEventId` và `paymentId` đã xác thực từ webhook.
- Dùng durable inbox unique theo provider + event ID.
- Kiểm tra trạng thái payment và version để không áp sự kiện cũ lên trạng thái mới.
- Redis `SET NX` có thể giảm duplicate work.
- Chỉ đánh dấu handled sau khi side effect trong hệ thống hoàn tất.
- Không chỉ trả `200` và bỏ qua lần retry nếu lần xử lý đầu chưa commit.

Webhook signature verification và idempotency là hai kiểm soát khác nhau: sự kiện có chữ ký đúng vẫn có thể được gửi nhiều lần.

### 22.3. Gửi email theo sự kiện

**Bối cảnh:** một message có thể được xử lý lại sau crash.

Nếu gửi email là side effect không hỗ trợ idempotency ở provider:

1. Lưu business event ID và trạng thái trong durable store.
2. Claim xử lý.
3. Gửi mail với provider request ID nếu có.
4. Ghi nhận provider message ID và trạng thái.
5. Khi outcome mơ hồ, hỏi provider hoặc có policy chấp nhận rủi ro duplicate.

Redis set key giúp giảm concurrency, nhưng không tự làm email provider có exactly-once delivery.

### 22.4. Tạo mã giảm giá

**Bối cảnh:** nhiều clicks tạo mã khuyến mại có giá trị.

Có thể dùng một Redis key `idem:coupon:<operationId>` làm claim, nhưng việc tạo mã phải được bảo vệ bằng unique constraint hoặc atomic reservation tương ứng tại nguồn phát mã. Nếu mã có TTL và số lượng giới hạn, cần tách **TTL của coupon** khỏi **TTL của idempotency record**.

### 22.5. Consumer đọc Redis Streams

**Bối cảnh:** handler xử lý Stream entry rồi crash trước `XACK`.

~~~text
XREADGROUP -> record eventId=e-101
DB update completed
Crash trước XACK
Record được reclaim -> handler chạy lại
~~~

Consumer cần durable idempotency theo `eventId` hoặc business aggregate/version. Redis `XACK` chỉ xác nhận xử lý record trong consumer group; nó không có transaction tự động với database.

Một key `seen:e-101` trong Redis có thể giúp giảm duplicate compute, nhưng không thay durable inbox nếu xử lý bắt buộc đúng và không mất.

### 22.6. Tác vụ scheduler trên nhiều pod

**Bối cảnh:** mỗi phút chạy job đồng bộ và có thể có hai pod kích hoạt cùng lúc.

Một Redis lease có thể giúp chỉ một pod chạy job trong khoảng dự kiến. Nhưng nếu job dài, GC pause hoặc Redis failover, hai pod có thể cùng chạy. Với batch cập nhật dữ liệu quan trọng, cần job-run ID, durable checkpoint, idempotent update và fencing/version để tránh kết quả cũ ghi đè.

Không nhầm **distributed scheduler locking** với **request idempotency**: chúng liên quan nhưng có phạm vi và vòng đời khác nhau.

## 23. Những sai lầm thường gặp

### 23.1. GET rồi SET để kiểm tra khóa

Hai request song song đều có thể đọc null và cùng xử lý.

**Thay bằng:** `SET key value NX EX ...` hoặc một Lua script claim nguyên tử.

### 23.2. SETNX rồi EXPIRE trong hai lệnh

Crash ở giữa có thể tạo key không TTL.

**Thay bằng:** `setIfAbsent(key, value, Duration)` tương ứng `SET NX EX`.

### 23.3. Chỉ ghi key khi xử lý xong

Không ngăn hai request đồng thời cùng thực hiện side effect.

**Thay bằng:** claim PROCESSING trước, rồi CAS sang SUCCEEDED.

### 23.4. Chỉ lưu “đã thấy key” trước khi xử lý

Nếu worker crash sau khi đánh dấu nhưng trước khi xử lý, lần retry bị bỏ qua và mất công việc.

**Thay bằng:** phân biệt PROCESSING/SUCCEEDED và có đường recovery.

### 23.5. Xóa claim trong mọi catch block

Nếu business commit thành công nhưng response bị mất, xóa claim khiến retry chạy lại side effect.

**Thay bằng:** xác định outcome tại nguồn hoặc giữ trạng thái cần reconciliation; không xóa theo cảm tính.

### 23.6. Dùng TTL quá ngắn

Worker còn chạy nhưng lease đã hết, worker khác claim. Cả hai có thể đi tới side effect.

**Thay bằng:** lease phù hợp, heartbeat có CAS và durable idempotency/fencing ở nguồn.

### 23.7. Dùng TTL quá dài mà không có recovery

Worker chết, retry bị kẹt lâu ở PROCESSING.

**Thay bằng:** tách lease TTL và completed retention, có operation status/reconciler.

### 23.8. Tưởng SET NX đảm bảo exactly-once

Redis có thể expire/evict/failover; side effect có thể commit trước khi lưu SUCCEEDED. **SET NX chỉ là một phần của giao thức.**

### 23.9. Chỉ dựa vào Redis cho chuyển tiền

Redis gate không thay transaction và unique constraints của nơi ghi sổ, đặc biệt khi có external payment provider.

**Thay bằng:** durable ledger + transaction/outbox/provider idempotency theo ranh giới nghiệp vụ.

### 23.10. Cùng key nhưng body khác vẫn replay

Điều này có thể trả order của request khác cho một thao tác mới vô tình dùng lại key.

**Thay bằng:** request fingerprint và HTTP 409.

### 23.11. Dùng body hash làm idempotency key duy nhất

Hai ý định khác nhau có cùng body có thể bị chặn sai.

**Thay bằng:** key do client phát cho logical operation, hash body chỉ để xác minh reuse.

### 23.12. Không scope theo tenant và operation

Tenant A và B có thể đụng cùng key; nguy hiểm hơn, một tenant có thể xem response của tenant khác nếu thiếu authorization.

**Thay bằng:** scope từ identity đã xác thực, operation route và version.

### 23.13. Ghi đè SUCCEEDED bằng PROCESSING

Một retry không được đặt lại trạng thái đã hoàn tất.

**Thay bằng:** `SET NX` cho claim, CAS theo owner khi finalize và không dùng SET vô điều kiện.

### 23.14. Trả response “đã thành công” trước khi side effect xác nhận

Redis lock thành công không có nghĩa order/payment đã commit. Chỉ trả success khi nguồn có bằng chứng kết quả.

### 23.15. Bỏ qua Redis eviction

Key có TTL vẫn có thể bị loại trước hạn, làm duplicate request lọt qua.

**Thay bằng:** sizing, monitoring, durable ledger và chọn eviction policy có chủ đích.

### 23.16. Dùng @Cacheable thay idempotency gate

Spring Cache `@Cacheable` tối ưu kết quả method; trong một số trường hợp cache miss đồng thời vẫn có thể gọi method nhiều lần, và cache không cung cấp tự động durable transaction với side effect.

**Thay bằng:** một cơ chế claim/ledger/response replay được thiết kế rõ ràng. `@Cacheable(sync=true)` không phải cam kết distributed exactly-once across pods.

## 24. Câu hỏi thường gặp

**Câu 1. Idempotency key có giống Redis key không?**

Không. Client key định danh logical request; Redis key nên là namespace/scoped representation do server tạo. Cần phân biệt với business resource ID.

**Câu 2. Có thể bỏ fingerprint không?**

Nếu không có fingerprint, cùng một client key có thể bị dùng lại với body khác mà server vẫn replay kết quả cũ. Với API có nhiều parameters ảnh hưởng side effect, fingerprint rất nên có.

**Câu 3. Vì sao phải dùng SET NX?**

Vì thao tác “chỉ tạo khi key chưa tồn tại” phải nguyên tử. GET rồi SET riêng có race.

**Câu 4. Vì sao phải gắn TTL ngay lúc SET NX?**

Để tránh claim vĩnh viễn khi worker crash trước bước EXPIRE. Dùng `SET key value NX EX seconds` hoặc API `setIfAbsent(key,value,Duration)`.

**Câu 5. Có nên lưu nguyên HTTP response trong Redis không?**

Có thể, khi cần replay chính xác. Phải bảo vệ dữ liệu nhạy cảm và tính dung lượng. Nếu chỉ cần không tạo resource trùng, có thể lưu resource ID và dựng response theo contract.

**Câu 6. Có nên xóa khóa sau khi xử lý thành công?**

Thông thường **không** ngay lập tức, nếu còn một cửa sổ mà client sẽ retry. Nên chuyển sang SUCCEEDED với retention TTL và replay khi key được dùng lại.

**Câu 7. Nếu operation thất bại, có xóa PROCESSING để client thử lại ngay không?**

Chỉ khi chắc chắn side effect chưa xảy ra hoặc retry được bảo vệ bởi durable idempotency. Nếu outcome mơ hồ, phải reconcile thay vì xóa mù.

**Câu 8. Redis SET NX có chặn được hai pod cùng lúc không?**

Trong điều kiện một primary xử lý cùng key và lease chưa hết, claim nguyên tử chỉ cho một winner. Nó không bảo đảm duy nhất side effect nếu lease hết, failover hoặc external system khác.

**Câu 9. Retry sau TTL kết quả có còn được bảo vệ không?**

Chỉ Redis record thì không. Cần quy định retry window hoặc dùng ledger bền vững để bảo đảm trong thời hạn dài hơn.

**Câu 10. Hash request body thô có đủ không?**

Không luôn. JSON khác whitespace/key order có thể có cùng semantics. Cần canonicalization/DTO normalized và contract version rõ.

**Câu 11. Lua CAS giải quyết điều gì?**

Nó ngăn worker không còn sở hữu trạng thái Redis ghi đè record hiện tại. Nó không undo side effect đã commit trong database.

**Câu 12. Có cần distributed lock library như Redisson không?**

Tùy kiến trúc. Library có thể giúp quản lý lease/lock, nhưng **định nghĩa idempotency, response replay và durable side effect** vẫn phải do ứng dụng thiết kế.

**Câu 13. Vì sao gọi payment provider phải dùng key xuống provider?**

Vì Redis và database nội bộ không thể biết chắc external payment đã thu tiền khi response mất. Nếu provider hỗ trợ idempotency theo key, nó có thể tránh xử lý trùng tại chính ranh giới tạo side effect.

**Câu 14. Webhook có eventId rồi còn cần Idempotency-Key header không?**

Không nhất thiết. Có thể dùng verified provider event ID làm logical dedupe key, nhưng phải scope theo provider/tenant/event type và quản lý sự kiện đến sai thứ tự.

**Câu 15. HTTP 409 hay 202 cho PROCESSING?**

Cả hai có thể xuất hiện theo thiết kế API: `409` diễn đạt conflict với operation đang xử lý; `202` diễn đạt request đã được chấp nhận và client có thể poll status. Cần công bố một contract nhất quán.

**Câu 16. Có cần giữ cả Redis và database ledger không?**

Không bắt buộc ở mọi use case. Nếu business operation chỉ là best-effort notification, Redis có thể đủ. Nếu yêu cầu không tạo duplicate resource/charge dù Redis failover hoặc key bị evict, durable ledger ở nguồn nghiệp vụ là lớp quan trọng.

## 25. Checklist thiết kế trước khi đưa vào production

1. **Logical operation** đã được định nghĩa rõ chưa? Cùng request key nghĩa là cùng ý định nào?
2. **Client key** có ổn định qua retry, đủ entropy và giới hạn độ dài không?
3. **Scope** có bao gồm tenant/người dùng đã xác thực và operation name không?
4. **Fingerprint** có bao gồm đầy đủ field ảnh hưởng side effect không?
5. **Claim** có dùng một command nguyên tử `SET NX EX` không?
6. **State** có phân biệt PROCESSING, SUCCEEDED và outcome mơ hồ không?
7. **Owner token** có được kiểm tra khi finalize/extend/release không?
8. **Completed response** có được lưu/replay theo contract không?
9. **PROCESSING TTL** có tính tới p99 latency, GC pause và workflow timeout không?
10. **Completed TTL** có bao phủ retry window được công bố không?
11. **Eviction/failover** có thể làm mất idempotency record không? Nếu có, side effect bảo vệ thế nào?
12. **Database/source of truth** có unique constraint hoặc idempotent operation ID không?
13. **External provider** có API idempotency hoặc query-status để xử lý timeout không?
14. **Lỗi Redis** được fail-closed hay fallback durable ledger; có ai vô tình gọi side effect nếu claim không rõ không?
15. **Recovery** có thể đối soát operation sau crash/lease expiration không?
16. **Multi-instance concurrency test** có kiểm tra kết quả ở database thay vì chỉ kiểm tra Redis SET NX không?
17. **Security** có tránh tenant collision, key guessing, response disclosure, PII in Redis/logs không?
18. **Metrics** có theo dõi claim, replay, conflicts, CAS failures và reconciliation không?
19. **Schema/version** của Redis key/value có ổn định qua deploy không?
20. **Ownership** của business outcome, retry policy và idempotency window đã được ghi thành API contract chưa?

## 26. Tổng kết

**Chống yêu cầu trùng không chỉ là đặt một Redis lock.** Mẫu xử lý hữu ích gồm:

1. Client gửi một `Idempotency-Key` ổn định cho cùng logical operation.
2. Server scope khóa theo authenticated tenant và operation, đồng thời tính fingerprint của request.
3. Redis `SET NX EX` claim nguyên tử trạng thái PROCESSING.
4. Request trùng nhận thông tin đang xử lý hoặc được **replay** kết quả SUCCEEDED.
5. Worker thực thi nghiệp vụ với **idempotency ở nguồn side effect** khi cần độ tin cậy mạnh.
6. Worker dùng Lua CAS theo owner token để chuyển trạng thái Redis sang SUCCEEDED và đặt TTL lưu kết quả.
7. Khi outcome mơ hồ, lease hết, failover hoặc Redis record mất, ứng dụng **đối soát nguồn chuẩn** thay vì giả định an toàn để làm lại.
8. Theo dõi memory, TTL/eviction, conflicts, retry và các trường hợp cần recovery.

Redis rất phù hợp để giảm duplicate work và lưu kết quả replay nhanh trên nhiều Spring Boot instances. Nhưng **lũy đẳng end-to-end phải được bảo vệ tại nơi side effect thực sự xảy ra**, đặc biệt với tạo đơn hàng, chuyển tiền, thanh toán, webhook và giao dịch dữ liệu bền vững.

## Tài liệu tham khảo

- Redis — [SET command](https://redis.io/docs/latest/commands/set/): `NX`, `EX`/`PX` và tạo key có điều kiện.
- Redis — [EXPIRE command](https://redis.io/docs/latest/commands/expire/): TTL và lifecycle của Redis key.
- Redis — [PSETEX command](https://redis.io/docs/latest/commands/psetex/): lưu value với TTL tính bằng milliseconds.
- Redis — [Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/): atomic server-side scripts và các giới hạn.
- Redis — [Distributed locks](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/): owner token, lease, compare-and-delete và những lưu ý.
- Redis — [Key eviction](https://redis.io/docs/latest/reference/eviction/): `maxmemory` và nguy cơ evict key trước TTL.
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): StringRedisTemplate, serializer, Redis operations.
- Spring Data Redis — [Redis Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript`/`DefaultRedisScript` và thực thi Lua.
- Spring Data Redis — [Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): giới hạn MULTI/EXEC và khác biệt với transaction của database.
