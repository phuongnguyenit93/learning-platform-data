# Giới hạn sử dụng MONITOR và ghi log dữ liệu nhạy cảm trong Spring Data Redis

## 1. Bối cảnh: quan sát hệ thống không có nghĩa được ghi lại mọi dữ liệu

Trong một ứng dụng Spring Boot dùng **Spring Data Redis**, nhóm phát triển có thể muốn biết:

- Có bao nhiêu lệnh `GET`, `SET`, `HGETALL`, `EVAL` hoặc `XADD` đang được gửi?
- Vì sao Redis chậm đột ngột, cache miss tăng hoặc một endpoint HTTP có p99 cao?
- Có phải một service đang liên tục ghi lại key đã hết hạn?
- Một consumer Redis Streams có đang nhận hoặc ACK message không?
- Có client nào đang tạo tải bất thường trên Redis?
- Redis Cluster đang gặp timeout, redirect hoặc mất cân bằng lệnh giữa các node?
- Spring Cache có đang phát sinh nhiều Redis commands hơn dự tính không?

Lệnh Redis `MONITOR` trông giống công cụ rất thuận tiện vì cho phép xem một dòng các command đang được xử lý. Tuy nhiên, đây cũng là một trong những công cụ quan sát có rủi ro cao:

1. **Hiệu năng:** Redis phải chuyển một lượng lớn thông tin lệnh cho các kết nối đang MONITOR, làm phát sinh CPU, network và chi phí định dạng dữ liệu.
2. **Bảo mật:** command arguments có thể chứa password, token, JSON hồ sơ người dùng, thông tin giao dịch và dữ liệu cá nhân.
3. **Phạm vi:** MONITOR không phải công cụ phân tích query cấp nghiệp vụ, không tự cho biết kết quả lệnh, latency HTTP hay nguyên nhân lỗi Java.
4. **Dữ liệu quan sát:** nếu stdout của MONITOR được ghi vào terminal history, file, CI log, hệ thống log tập trung hoặc bản ghi màn hình, dữ liệu nhạy cảm có thể tồn tại lâu hơn dữ liệu gốc trong Redis.
5. **Quản trị quyền:** quyền truy cập công cụ chẩn đoán có thể trở thành quyền xem dữ liệu của nhiều tenant/service khác nhau.

Vì vậy, nguyên tắc của chương **Quan sát** là:

> **Thu thập đúng tín hiệu cần thiết với quyền hạn, độ chi tiết và thời gian lưu nhỏ nhất. MONITOR không phải phương án mặc định để debug Spring Data Redis trên production.**

Bài này tập trung vào giới hạn của `MONITOR`, các đường rò rỉ dữ liệu khi ghi log Redis, công cụ thay thế phù hợp và cách xây dựng observability an toàn trong ứng dụng Java.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `MONITOR` hiển thị gì, không hiển thị gì và vì sao nó có overhead.
2. Phân tích rủi ro lộ dữ liệu từ **tên key**, **command arguments**, **metadata client** và **application logs**.
3. Phân biệt Redis `MONITOR`, `SLOWLOG`, `INFO commandstats`, `LATENCY`, tracing và metrics.
4. Xác định khi nào được phép dùng MONITOR trong môi trường kiểm thử hoặc sự cố production có phê duyệt.
5. Thiết kế logging theo **allowlist**, không ghi raw key, payload, token hoặc full request body.
6. Áp dụng Micrometer và Spring Data Redis để đo latency, failure, cache hit/miss bằng tags có cardinality thấp.
7. Nhận diện rủi ro khi bật TRACE/wire logging của Lettuce, Netty, Spring WebFlux và công cụ APM.
8. Thiết kế quy trình masking, kiểm soát truy cập, retention, auditing và xử lý log lộ bí mật.
9. Xây dựng runbook chẩn đoán Redis có thể vận hành và thu hồi an toàn.
10. Phân biệt sự cần thiết của một tín hiệu quan sát với việc thu thập toàn bộ nội dung dữ liệu.

---

## 2. MONITOR là gì?

`MONITOR` là lệnh Redis chuyển kết nối gọi lệnh sang chế độ nhận một luồng thông tin về các command mà Redis đang xử lý theo cơ chế của server và phiên bản.

Ví dụ **chỉ trong môi trường lab có dữ liệu giả**:

```bash
redis-cli -h 127.0.0.1 -p 6379 MONITOR
```

Một terminal khác:

```bash
redis-cli -h 127.0.0.1 -p 6379 SET lab:product:42 '{"name":"Demo Product","active":true}'
redis-cli -h 127.0.0.1 -p 6379 GET lab:product:42
redis-cli -h 127.0.0.1 -p 6379 DEL lab:product:42
```

Terminal MONITOR có thể hiển thị các bản ghi tương tự:

```text
<timestamp> [0 127.0.0.1:<port>] "SET" "lab:product:42" "{\"name\":\"Demo Product\",\"active\":true}"
<timestamp> [0 127.0.0.1:<port>] "GET" "lab:product:42"
<timestamp> [0 127.0.0.1:<port>] "DEL" "lab:product:42"
```

Đây là **minh họa định dạng**, không phải output thu thập từ hệ thống thật. Cú pháp, cách escape, metadata và những command được hiển thị có thể khác giữa các Redis versions.

MONITOR giúp trả lời câu hỏi:

> Redis server này đang nhận và xử lý những command nào, với những arguments nào được server đưa ra trong luồng monitor?

Nó **không trực tiếp trả lời**:

- Tại sao một HTTP request mất 200 ms?
- Một command có trả đúng value cho ứng dụng không?
- JSON response sau `GET` là gì?
- Redis Stream handler đã commit database hay chưa?
- Một transaction nhiều service đã hoàn tất nghiệp vụ chưa?
- Tên user/tenant có hợp lệ về authorization hay không?
- Mọi command của tất cả node trong Redis Cluster có xuất hiện trên một kết nối MONITOR không?

### 2.1. MONITOR hiển thị command, không phải response

Giả sử ứng dụng gọi:

```redis
GET lab:product:42
```

MONITOR có thể hiển thị tên lệnh và tên key, nhưng không có nghĩa nó phát ra chính nội dung value mà `GET` trả về.

Ngược lại, với một lệnh ghi:

```redis
SET lab:product:42 '{"name":"Demo Product","active":true}'
```

nội dung value được gửi **như argument đầu vào**, nên có thể xuất hiện trong luồng MONITOR.

Điều này tạo một quy tắc quan sát quan trọng:

| Loại command | Điều có thể lộ trong MONITOR |
|---|---|
| `GET key` | Tên key; tên key tự nó có thể chứa PII hoặc token |
| `MGET key1 key2` | Nhiều tên key |
| `SET key value` | Tên key và value được gửi |
| `HSET key field value` | Key, field và value |
| `LPUSH`/`RPUSH` | Key và các phần tử thêm vào |
| `XADD stream * field value` | Stream key, field names, event payload |
| `PUBLISH channel message` | Channel và message payload |
| `EVAL script numkeys keys args...` | Nội dung script/keys/arguments theo hành vi monitor |
| `DEL key` | Tên key, có thể chứa định danh nhạy cảm |
| `EXPIRE key seconds` | Tên key và điều kiện thời hạn |
| `AUTH`/các lệnh xác thực | Phải kiểm tra hành vi che giấu theo Redis version; không dựa vào MONITOR để bảo vệ mọi bí mật |

Một số command hoặc argument được Redis bảo vệ/lọc ở một số phiên bản vì lý do bảo mật. **Không được coi đó là cam kết rằng mọi loại bí mật khác cũng được che.** Những lệnh ứng dụng tự định nghĩa payload như `SET`, `HSET`, `XADD`, `PUBLISH` và `EVAL` vẫn có thể vô tình chứa nội dung nhạy cảm.

### 2.2. MONITOR không phải packet capture

MONITOR là khả năng quan sát ở mức Redis server, không phải ảnh chụp gói tin mạng đầy đủ. Nó không thay thế TCP capture, không cung cấp tất cả reply bytes và không bao phủ toàn bộ thời gian chờ network/client.

Nếu Redis client gặp `RedisCommandTimeoutException`, MONITOR thấy command đã tới server có thể là một tín hiệu hữu ích, nhưng **không đủ** để xác định:

- Reply có được Redis gửi thành công không?
- Client có nhận hoặc decode reply không?
- Lệnh có được giữ bền vững qua failover không?
- Một service khác có retry lệnh sau đó không?

Đặc biệt, một command xuất hiện trên MONITOR không phải receipt bảo đảm exactly-once business effect.

---

## 3. Vì sao MONITOR có thể ảnh hưởng hiệu năng?

Redis được tối ưu cho xử lý commands với overhead thấp. Khi một client bật MONITOR, server phải bổ sung công việc để tạo và đẩy thông tin command sang kết nối quan sát.

Hình dung:

```text
                       Redis
                         |
       +-----------------+------------------+
       |                 |                  |
   Client A          Client B           Client C
   GET/SET           HGETALL            XADD/EVAL
       |                 |                  |
       +-----------------+------------------+
                         |
                         v
                    Command path
                         |
              +----------+-----------+
              |                      |
              v                      v
       Execute commands      Produce MONITOR output
              |                      |
              v                      v
       Application replies     MONITOR clients
                                      |
                               terminal / socket
```

Tác động có thể gồm:

- CPU dùng để định dạng và sao chép command/arguments.
- Tăng network egress từ Redis tới client quan sát.
- Thêm chi phí xử lý connection/output buffers.
- Nhiều dữ liệu phải truyền nếu value/args lớn.
- Nguy cơ tăng tail latency dưới tải cao.
- Nhiều MONITOR clients có thể làm chi phí quan sát cao hơn.
- Chậm ở phía MONITOR client làm quá trình xuất dữ liệu quan sát trở thành một nguồn áp lực tài nguyên.

Điều quan trọng là **không có hệ số overhead cố định** áp dụng cho mọi workload.

Một Redis chỉ xử lý vài commands/s trong lab có thể hầu như không chịu ảnh hưởng đáng kể. Một Redis production xử lý hàng chục hoặc hàng trăm nghìn commands/s với nhiều payload lớn có thể bị ảnh hưởng mạnh.

### 3.1. MONITOR không tự giới hạn theo command family

Khi điều tra “vì sao `HGETALL` chậm?”, ta có thể chỉ cần số lượng/timing của `HGETALL`. Nhưng MONITOR được thiết kế để xuất luồng thông tin command rộng, chứ không phải một query server-side giới hạn chỉ những keys/operations mà một service quan tâm.

Nếu sau đó chạy:

```text
MONITOR -> grep "HGETALL"
```

thì bước lọc **sau khi nhận dữ liệu** không làm Redis giảm lượng thông tin đã phải xử lý/gửi tới monitor client. Nó cũng không ngăn dữ liệu command khác tiếp xúc với quá trình đọc stdout trước khi lọc.

**Đừng coi pipe qua grep là cơ chế bảo vệ quyền truy cập hoặc redaction đáng tin cậy.**

### 3.2. Throughput tăng, dữ liệu MONITOR tăng

Một mô hình tư duy:

```text
Commands/s lớn
    x bytes thông tin trung bình mỗi command
    x số luồng monitor cần phục vụ
    = lượng công việc quan sát bổ sung đáng kể
```

Đây không phải công thức dự báo chính xác bandwidth do còn encoding, protocol, buffers và implementation.

Trong một hệ thống có nhiều `SET` payload JSON lớn, output MONITOR có thể còn nặng hơn một hệ thống chủ yếu gọi `INCR` với key ngắn, dù commands/s bằng nhau.

### 3.3. Đo hiệu năng bằng MONITOR có thể làm thay đổi thứ đang đo

Nếu bật MONITOR để xác định latency tối đa Redis chịu được, công cụ quan sát có thể ảnh hưởng chính latency và throughput của hệ thống.

Đây là hiệu ứng observer overhead: số đo từ production đang MONITOR không nhất thiết đại diện cho production bình thường.

Muốn đo:

- Commands/s: ưu tiên `INFO stats`/`INFO commandstats`.
- Server execution time: ưu tiên `SLOWLOG`/`INFO commandstats` theo mức cần thiết.
- Client round-trip: ưu tiên Lettuce/Micrometer instrumentation.
- End-to-end latency: ưu tiên HTTP/server metrics và distributed tracing.
- Memory: ưu tiên `INFO memory`, `MEMORY USAGE` sampling có giới hạn.

MONITOR chỉ nên nằm ở cuối chuỗi chẩn đoán khi thực sự cần nhìn một **lệnh cụ thể được gửi ra sao** và các công cụ ít xâm lấn không đủ.

### 3.4. Không chạy MONITOR cùng benchmark rồi báo kết quả như baseline

Nếu muốn benchmark Redis:

```text
Baseline:
    Redis chạy bình thường, không có MONITOR.

Diagnostic run:
    Redis đang có MONITOR theo dõi.
```

Phải ghi rõ hai trường hợp khác nhau. Đừng chạy `redis-benchmark` trên production chỉ vì muốn “xem MONITOR có ảnh hưởng không” nếu chưa có môi trường và quyền kiểm thử phù hợp.

---

## 4. Rủi ro số một: tên Redis key có thể chứa dữ liệu nhạy cảm

Nhiều đội chỉ che **value** mà quên **key name**.

Ví dụ những cách đặt tên key có rủi ro:

```text
session:<real-access-token>
user:<real-email-address>:profile
password-reset:<reset-token>
otp:<phone-number>
invoice:<customer-name>:<invoice-number>
tenant:<company-confidential-name>:orders
payment:<card-pan-or-other-sensitive-id>
```

Chỉ cần một `GET`, `DEL`, `EXPIRE` hoặc `TTL` với tên key như vậy, log/trace có khả năng lộ thông tin.

Ví dụ:

```redis
GET session:<token-value>
```

Dù MONITOR không nhìn thấy response, **tên key đã chứa secret**.

### 4.1. Không đặt secret vào tên key

Tốt hơn là dùng một định danh không nhạy cảm, không thể dễ dàng suy ra từ PII:

```text
session:<opaque-random-id>
user:<internal-surrogate-id>:profile
password-reset:<opaque-token-id>
```

Tuy vậy, **opaque ID cũng có thể là dữ liệu nhạy cảm** nếu nó cho phép liên kết người dùng hoặc truy cập tài nguyên. Không mặc định “UUID không phải PII” trong mọi trường hợp.

Cần áp dụng chính sách logging cho cả key nội bộ khi chúng có thể liên kết tới cá nhân, tài khoản hoặc hoạt động.

### 4.2. Redis Cluster hash tag cũng có thể lộ PII

Ví dụ:

```text
user:{someone@example.com}:cart
user:{someone@example.com}:settings
```

Dấu `{...}` giúp các key cùng slot, nhưng làm email nằm lộ rõ trong tên key.

Nên thiết kế tag theo aggregate ID đã chuẩn hóa:

```text
user:{u-7b1d}:cart
user:{u-7b1d}:settings
```

Nếu cần ánh xạ email → internal ID, dữ liệu ánh xạ phải được bảo vệ bằng quyền và retention tương ứng.

Việc đưa raw email vào hash tag **không bắt buộc** để Redis Cluster hoạt động.

### 4.3. Định danh đo lường khác định danh khóa

Metric tag có thể ghi:

```text
cache = "profile"
command = "GET"
outcome = "success"
```

Không cần ghi:

```text
key = "user:{u-7b1d}:profile"
```

Nếu cần theo dõi một incident cụ thể, có thể dùng **correlation ID ngẫu nhiên** trong log ứng dụng, với khả năng truy ngược tới business object qua hệ thống có quyền kiểm soát.

Không biến Redis key thành label của mọi metrics series.

---

## 5. Value và command arguments là bề mặt lộ dữ liệu lớn

Giả sử Spring Data Redis lưu một session:

```java
redis.opsForValue().set(key, serializedSession);
```

Payload có thể chứa:

```json
{
  "sessionId": "<redacted>",
  "userId": "<redacted>",
  "roles": ["USER"],
  "refreshToken": "<redacted>",
  "device": "<redacted>"
}
```

Nếu MONITOR hoặc debug logger ghi raw `SET` arguments, các trường này có thể bị sao chép sang nơi khác.

Những nhóm data cần cẩn trọng:

| Loại dữ liệu | Ví dụ | Tác hại nếu lộ |
|---|---|---|
| Credentials | Password, API key, access token, refresh token | Truy cập trái phép |
| Session | Session identifier, authentication cookies | Chiếm dụng phiên |
| PII | Email, số điện thoại, địa chỉ, số định danh | Xâm phạm quyền riêng tư |
| Financial | Thông tin thanh toán, giao dịch, hạn mức | Rủi ro tài chính/bảo mật |
| Health/sensitive domain | Hồ sơ hoặc thuộc tính nhạy cảm | Hậu quả nghiêm trọng theo ngữ cảnh |
| Internal business | Giá nội bộ, chiến lược, dữ liệu khách hàng doanh nghiệp | Lộ bí mật kinh doanh |
| Security control | OTP, reset token, revocation state | Bỏ qua/ảnh hưởng cơ chế xác thực |
| Authorization | Roles, permissions, tenant bindings | Lộ cấu trúc phân quyền |
| Device/location | IP, device IDs, vị trí | Liên kết hoặc theo dõi cá nhân |

Không phải mọi giá trị Redis đều nhạy cảm. Nhưng **MONITOR không tự phân loại nội dung nghiệp vụ** để quyết định cái gì an toàn.

### 5.1. Redis Hash và JSON modules

Không chỉ `SET` mới lộ data:

```redis
HSET lab:user:42 email "<redacted-email>" phone "<redacted-phone>"
```

hoặc command JSON của một Redis module:

```text
JSON.SET <key> <path> <json-document>
```

cũng có thể chứa dữ liệu ngay trong argument.

Tương tự, `EVAL`/`FCALL` có thể nhận input qua `KEYS`/`ARGV`; tên script hoặc nội dung logic cũng có thể lộ thông tin nội bộ.

### 5.2. Redis Streams

Một event được ghi:

```redis
XADD orders:events * eventId evt-42 type OrderCreated customerId "<redacted>"
```

thường chứa event metadata và payload. Đôi khi producer gửi cả JSON String trong một field `payload`.

Nếu dùng MONITOR để xác định có `XADD` hay không, observer có thể xem được **cả nội dung event**. Đối với thông tin giao dịch, đây có thể là dữ liệu nhạy cảm không thuộc phạm vi của người đang debug infrastructure.

Thay vì raw MONITOR, có thể đo:

```text
XADD count
XADD latency
Stream key family
XLEN
Consumer group lag
XPENDING
Handler success/failure
```

mà không ghi field values.

### 5.3. Redis Pub/Sub

Một publication:

```redis
PUBLISH notifications.user "<redacted-json-payload>"
```

có thể chứa nội dung notification hoặc thông tin người nhận. Khi chẩn đoán fan-out, thường chỉ cần:

```text
channel family
published messages/s
subscriber count
error/drop/reconnect rate
```

Dùng Pub/Sub message content để làm log debug thường không cần thiết và có nguy cơ đưa dữ liệu cá nhân sang log tập trung.

### 5.4. Redis scripting

Một Lua script có thể nhận:

```text
KEYS:
  inventory:{sku-42}:available

ARGV:
  quantity
  requestId
  serialized business data
```

Khi bật logging raw command, `ARGV` có thể tiết lộ payload. Vì thế, chính sách “không log SET values” **chưa đủ**; phải bao phủ mọi command mang payload.

---

## 6. MONITOR có được Redis tự che thông tin nhạy cảm không?

Một số Redis versions có hành vi bảo vệ một số lệnh xác thực hoặc command nhạy cảm khi xuất MONITOR hay các giao diện quan sát. Nhưng mức che giấu và danh sách lệnh không nên được khẳng định như một cơ chế bảo vệ tất cả bí mật ứng dụng.

Ví dụ:

```text
Lệnh AUTH dùng cơ chế Redis xác thực:
    Có thể được bảo vệ/ẩn theo version và interface.

Lệnh SET api-key:tenant-7 "<actual-secret>":
    Là write thông thường của application.
    Redis không tự biết value này là API key.
```

Kể cả nếu Redis che `AUTH`, một access token được app đặt trong `SET` vẫn có thể xuất hiện như argument bình thường.

**Không xây security policy dựa vào giả định rằng MONITOR luôn có automatic redaction.**

### 6.1. TLS bảo vệ network, không có nghĩa người MONITOR không xem được plaintext

TLS giữa Spring Data Redis client và Redis giúp bảo vệ dữ liệu trên đường truyền. Nhưng Redis phải xử lý command arguments sau khi giải mã.

Một client được phép MONITOR có thể quan sát thông tin command theo cơ chế Redis; TLS **không tự che payload khỏi người có quyền truy cập vào MONITOR**.

Tương tự, TLS giữa app và Redis không ngăn ứng dụng tự ghi raw payload vào logs của chính nó.

### 6.2. Mã hóa value ở tầng ứng dụng

Nếu một số value được mã hóa **trước khi gửi tới Redis**, MONITOR có thể thấy ciphertext thay vì plaintext cho những value đó.

Tuy nhiên:

- Key names, command names và nhiều metadata vẫn có thể lộ.
- Những field không mã hóa vẫn xuất hiện.
- Search/indexing/debugging có thể thay đổi.
- Secret/key management trở thành yêu cầu quan trọng.
- Không được ghi encryption keys hoặc plaintext trước khi encrypt vào logs.
- Encryption ở application layer không thay thế việc hạn chế quyền MONITOR.

Đây là một lớp bảo vệ bổ sung, không phải giấy phép để MONITOR toàn bộ production không giới hạn.

---

## 7. MONITOR trong Redis Cluster: một node không phải toàn bộ cluster

Redis Cluster có nhiều primary node quản lý các hash slots khác nhau.

```text
Spring Data Redis / Lettuce cluster client
                  |
          +-------+-------+
          |       |       |
          v       v       v
       Primary A Primary B Primary C
          |       |       |
          +-- MONITOR trên B
                  |
                  v
          Những command thấy tại B
```

Một kết nối MONITOR tới Primary B **không tự là view hợp nhất hoàn chỉnh của A, B và C**. Những lệnh được định tuyến tới các node khác có thể không hiện trong output của B.

Ngoài ra:

- Replica và primary có thể nhận các nhóm traffic khác nhau.
- Slot ownership có thể đổi khi resharding.
- Redirect `MOVED`/`ASK` ảnh hưởng nơi command cuối cùng được thực thi.
- Các Redis deployment/managed services có thể giới hạn quyền MONITOR.
- Command hoặc thông tin hoạt động nội bộ không nhất thiết phản ánh toàn bộ business request path.

Do đó, không nên báo:

> “Đã MONITOR một Redis node, không thấy SET nên cả cluster không có SET.”

Đó là kết luận vượt phạm vi quan sát.

### 7.1. Càng nhiều MONITOR connections càng tăng rủi ro

Để quan sát toàn cluster bằng MONITOR, operator có thể phải kết nối đến nhiều node, khiến lượng dữ liệu chẩn đoán và bề mặt lộ thông tin tăng.

Thay vì cách đó, nếu câu hỏi chỉ là “primary nào có nhiều `HGETALL`?”, hãy lấy `INFO commandstats` **trên từng node**. Nếu câu hỏi là “node nào có p99 cao?”, đo client/HTTP metrics cùng Redis latency telemetry.

### 7.2. Redis Sentinel và managed Redis

Sentinel quản lý availability/failover theo topology của Redis, không làm mọi MONITOR output tự hợp nhất thành một luồng application-level.

Dịch vụ managed Redis có thể chặn MONITOR hoặc cung cấp cơ chế performance insights riêng. Việc công cụ không được hỗ trợ không phải lý do tự tìm cách vượt quyền; cần chọn metrics/diagnostic interfaces được nhà cung cấp cho phép.

---

## 8. Những công cụ quan sát thay thế ít xâm lấn hơn

Thông thường ta có thể giải quyết hầu hết nhu cầu vận hành mà không cần xem raw payload.

| Nhu cầu | Công cụ ưu tiên | Có thể lộ dữ liệu nhạy cảm? | Lưu ý |
|---|---|---|---|
| Commands/s | `INFO stats` | Thường là counters, ít hơn MONITOR | Không cho per-request details |
| Tỷ lệ GET/SET/EVAL | `INFO commandstats` | Chủ yếu aggregated counts/timing | Theo từng node |
| Redis server execution time | `INFO commandstats` | Ít payload hơn MONITOR | Mean không phải p99 |
| Lệnh chạy chậm | `SLOWLOG GET` | **Có thể lộ keys/args** | Cần quyền/retention thích hợp |
| Latency spikes | `LATENCY LATEST`/`LATENCY DOCTOR` | Chủ yếu metadata sự kiện | Phụ thuộc cấu hình/version |
| Memory tổng | `INFO memory`/`MEMORY STATS` | Ít payload trực tiếp | Không thay per-key sampling |
| Số client | `INFO clients` | Thống kê tổng hợp | Không thay client diagnosis |
| Connection cụ thể | `CLIENT LIST` | Có IP, tên client, metadata | Bảo vệ như dữ liệu vận hành |
| ACL/auth failures | `ACL LOG` | Có username/source metadata | Chỉ dùng với quyền phù hợp |
| Cache hit/miss | Spring Cache/Micrometer | Tùy tags | Không log raw key |
| Redis client RTT | Lettuce/Micrometer observation | Tùy instrumentation | Tránh command args |
| HTTP p95/p99 | Spring Boot Actuator | Có thể lộ URI nếu cấu hình sai | Dùng route template |
| Trace request chậm | OpenTelemetry/Tracing | Có thể lộ attributes | Redaction/allowlist |
| Một command chính xác trên lab | MONITOR | **Rủi ro cao** | Dữ liệu giả, thời gian ngắn |

Không có công cụ nào tự tuyệt đối an toàn. `SLOWLOG` và tracing cũng có thể lưu dữ liệu nhạy cảm nếu cấu hình cẩu thả.

### 8.1. Nguyên tắc chọn công cụ theo câu hỏi

Thay vì bắt đầu từ:

```text
Tôi muốn biết Redis đang làm gì
    -> MONITOR
```

hãy viết rõ câu hỏi:

```text
Tôi muốn biết:
    (A) Redis đang nhận bao nhiêu GET/s?
    (B) Command nào có execution time cao?
    (C) Spring endpoint nào đang timeout?
    (D) Có phải writer đang gửi key format sai?
```

Sau đó:

```text
(A) INFO commandstats + client metrics.
(B) SLOWLOG/LATENCY + timing.
(C) HTTP traces + Lettuce metrics.
(D) Unit/integration test key factory + bounded
    application-level diagnostic log đã redact.
```

MONITOR chỉ nên là công cụ cuối khi cần chứng cứ command-level mà các lựa chọn này chưa cung cấp.

---

## 9. INFO stats và commandstats

Redis cung cấp:

```redis
INFO stats
INFO commandstats
```

Một số trường có thể gồm:

```text
total_commands_processed
instantaneous_ops_per_sec
keyspace_hits
keyspace_misses
cmdstat_get
cmdstat_set
cmdstat_hgetall
cmdstat_eval
```

Ví dụ số liệu **minh họa**:

```text
cmdstat_get:calls=100000,usec=500000,usec_per_call=5.00
cmdstat_set:calls=25000,usec=300000,usec_per_call=12.00
```

Từ đó có thể biết Redis đã xử lý bao nhiêu commands của từng loại và thời gian execution trung bình. Không cần xem tên key hay payload.

### 9.1. Những giới hạn cần biết

- Metrics ở server thường là aggregate theo command type, không biết business operation nào tạo lệnh.
- `usec_per_call` là thời gian trung bình xử lý ở Redis, **không phải p99 client round-trip**.
- Counter có thể reset sau restart.
- Một primary Redis Cluster chỉ cho biết tải của node đó.
- Thống kê command còn có thể bao gồm traffic của service khác trên instance dùng chung.
- Redis commands/s không trực tiếp bằng HTTP RPS.

Để phân tích một endpoint, cần kết hợp metrics từ ứng dụng hoặc tracing.

### 9.2. Phân tích bằng delta thay vì MONITOR

Ghi `calls` tại thời điểm đầu và cuối một khoảng quan sát:

```text
t0: cmdstat_get calls = 1.000.000
t1: cmdstat_get calls = 1.060.000
t1 - t0 = 60 giây
```

Tốc độ `GET` trung bình trong khoảng được xác định từ chênh lệch count/chênh lệch thời gian. Cần ghi rõ nếu Redis restart hoặc có những workload xen vào.

Cách này nhẹ và ít tiếp xúc nội dung nhạy cảm hơn MONITOR.

---

## 10. SLOWLOG cũng có rủi ro dữ liệu

Redis lưu một số command thực thi chậm trong slow log khi vượt ngưỡng cấu hình.

Các lệnh:

```redis
SLOWLOG LEN
SLOWLOG GET 10
CONFIG GET slowlog-log-slower-than
```

`SLOWLOG` hữu ích để tìm command execution chậm, nhưng entries có thể chứa:

- Command name.
- Redis key names.
- Một phần command arguments/payload.
- Timestamp và thời gian thực thi.
- Metadata client như địa chỉ/name tùy version.

Một số phiên bản giới hạn độ dài arguments hoặc che một số nội dung nhạy cảm, nhưng **truncation không đồng nghĩa anonymization**. Chỉ 20 ký tự đầu của token hoặc số định danh cũng có thể là dữ liệu nhạy cảm.

### 10.1. Không gửi raw SLOWLOG vào ticket công khai

Sai:

```text
Paste nguyên kết quả SLOWLOG GET 128
vào issue tracker mà nhiều người cùng truy cập.
```

Trong entries có thể có `HSET` chứa hồ sơ khách hàng hoặc `SET` chứa token.

Hướng xử lý an toàn hơn:

1. Xác định thông tin cần thiết: command type, duration, approximate argument size.
2. Dùng quy trình được phê duyệt để truy cập entries.
3. Redact key/payload **trước khi chia sẻ**.
4. Chỉ lưu bản gốc trong kênh giới hạn quyền nếu thực sự cần.
5. Dọn bản gốc theo retention/runbook.
6. Không upload raw log lên công cụ bên thứ ba không được chấp thuận.

### 10.2. SLOWLOG không đo network latency

Một `GET` có thể có server execution time rất nhỏ nhưng client latency lớn do network, queue hoặc JVM. Không thấy entry trong SLOWLOG không chứng minh client p99 thấp.

Do đó SLOWLOG là công cụ bổ sung, không phải thay thế instrumentation của Spring Data Redis.

---

## 11. LATENCY, CLIENT LIST và ACL LOG: ít payload hơn không có nghĩa không nhạy cảm

### 11.1. Redis LATENCY

Redis hỗ trợ những command như:

```redis
LATENCY LATEST
LATENCY DOCTOR
```

Các event phụ thuộc Redis version và cấu hình monitor. Chúng chủ yếu giúp quan sát một số nhóm latency spikes ở server mà không cần stream toàn bộ command arguments.

Nếu hệ latency monitor chưa được bật, một kết quả rỗng không chứng minh không có latency spike.

### 11.2. CLIENT LIST

```redis
CLIENT LIST
```

có thể chứa địa chỉ IP, tên client, DB index, trạng thái, command gần đây hoặc thông tin vận hành khác theo version.

Địa chỉ IP và client name đôi khi là thông tin cần hạn chế chia sẻ. Nếu client name chứa hostname nội bộ, customer ID hoặc môi trường nhạy cảm, log metadata cũng có thể là đường rò rỉ.

Không tự chèn token, email hay tên người dùng vào Redis client name để “debug cho dễ”.

### 11.3. ACL LOG

```redis
ACL LOG
```

hỗ trợ quan sát một số sự kiện liên quan authorization/authentication của Redis theo cơ chế ACL. Nó có thể chứa username, địa chỉ nguồn và chi tiết command denied.

Đây là dữ liệu security telemetry, nên có phân quyền đọc, retention và kênh xử lý sự cố phù hợp. Không coi ACL LOG là một tập dữ liệu được phép công khai vì không chứa full application payload.

### 11.4. MEMORY và SCAN

```redis
INFO memory
MEMORY STATS
SCAN 0 MATCH product:* COUNT 100
MEMORY USAGE product:42
```

Giúp phân tích RAM và keyspace. Tuy nhiên, `SCAN` vẫn trả **tên key**, có thể chứa PII. Nếu muốn thống kê kích thước, nên tổng hợp theo key family bằng một công cụ nội bộ được kiểm soát và chỉ xuất histogram thay vì danh sách raw keys.

Trên Redis Cluster, cần xem từng node/primary theo topology; một lần SCAN trên một node không nhất thiết bao phủ toàn bộ Cluster.

---

## 12. Bề mặt ghi log trong ứng dụng Spring Data Redis

Dữ liệu Redis có thể bị ghi log **mà không cần gọi MONITOR**.

Hình dung:

```text
Spring HTTP request
       |
       +--> Controller request logging
       |
       +--> Service logging
       |
       +--> Spring Cache key logging
       |
       +--> RedisTemplate serialization
       |
       +--> Lettuce driver / Netty transport logging
       |
       +--> Exception stack trace
       |
       +--> Metrics / tracing attributes
       |
       +--> Centralized log collector
```

Chỉ cần một tầng log raw payload, dữ liệu có thể đi xa hơn Redis.

### 12.1. Controller logging

Ví dụ không nên dùng cho request có thông tin nhạy cảm:

```java
log.info("CreateSession request={}", requestDto);
```

Nếu Lombok `@Data` hoặc record `toString()` biểu diễn mọi field, `requestDto` có thể mang access token, password, email, địa chỉ.

Cách viết an toàn hơn:

```java
log.info(
    "Session creation requested operation={} traceId={}",
    "session-create",
    traceId
);
```

Nếu cần `userId`, chỉ ghi định danh được phép sử dụng cho observability theo policy; không tự động ghi raw email hoặc token.

### 12.2. Service logging

Không nên:

```java
log.debug("Redis SET key={} value={}", key, value);
```

Ngay cả khi DEBUG bình thường tắt, ai đó có thể bật nó trong incident và làm lộ secrets.

Tốt hơn:

```java
log.debug(
    "Redis write operation={} keyFamily={} bytes={}",
    "session-update",
    "session",
    serializedPayloadBytes
);
```

Đo độ dài payload vẫn có thể tiết lộ thông tin gián tiếp ở một số ngữ cảnh; cần xem xét sensitivity và không ghi kích thước quá chi tiết nếu policy không cho phép.

### 12.3. Exception logging

Một lỗi low-level có thể bao gồm command/key/arguments trong message tùy connector và tình huống. Không mặc định mọi exception của Lettuce/Spring Data Redis đã được redact.

Ví dụ không lý tưởng:

```java
catch (Exception e) {
    log.error("Redis failed: {}", e.getMessage());
    throw e;
}
```

Nếu exception message chứa key nhạy cảm hoặc serialized arguments, nội dung ấy có thể bị xuất lên log.

Có thể ghi metadata an toàn:

```java
catch (DataAccessException ex) {
    log.warn(
        "Redis operation failed operation={} errorType={}",
        "session-load",
        ex.getClass().getSimpleName()
    );
    throw ex;
}
```

Đối với troubleshooting cần stack trace, nên dùng kênh **hạn chế truy cập, đã kiểm soát/redact theo policy**, thay vì cho phép mọi raw exception message tự động vào centralized logs công khai.

### 12.4. Spring Cache

Với `@Cacheable`:

```java
@Cacheable(
    cacheNames = "userProfiles",
    key = "#email"
)
public ProfileDto getByEmail(String email) {
    // ...
}
```

Nếu raw email được dùng làm key, có thể xuất hiện trong Redis key, MONITOR và các traces. Thay đổi tốt hơn là dùng internal surrogate key phù hợp, hoặc thiết kế `KeyGenerator` với policy riêng.

Đừng chỉ che `value` trong log mà vẫn sinh cache key từ dữ liệu cá nhân.

### 12.5. Redis Repository

Spring Data Redis Repository có thể dùng keyspace, entity IDs, index names và secondary index values.

Các tên key/index có thể chứa thuộc tính nghiệp vụ hoặc giá trị field. Vì vậy, trước khi bật debug logging cho repository operations, cần hiểu mapping và index representation, không suy “Repository chỉ ghi class name”.

---

## 13. Lettuce và Netty: cẩn trọng với DEBUG, TRACE và wire logging

Spring Data Redis thường dùng **Lettuce** làm Redis driver. Lettuce dựa trên Netty trong nhiều đường giao tiếp.

Một số nhóm logging có thể được cấu hình trong Spring Boot:

```yaml
logging:
  level:
    org.springframework.data.redis: INFO
    io.lettuce.core: INFO
    io.netty: WARN
```

Đây chỉ là ví dụ cấu hình hạn chế độ chi tiết. Không có nghĩa mọi version phải dùng đúng các mức đó, hoặc INFO tự bảo đảm mọi logging không chứa data.

Rủi ro xuất hiện khi bật:

```text
DEBUG / TRACE trên thư viện Redis
Detailed protocol/command logging
Netty wire-level debugging
HTTP request/response body logging
APM instrumentation tự gắn arguments
```

Chính xác những trường nào được ghi phụ thuộc thư viện, phiên bản, encoder, logger configuration và instrumentation.

**Không khẳng định cứ bật `io.lettuce.core=DEBUG` là chắc chắn lộ mọi Redis value.** Nhưng cũng không được mặc định DEBUG/TRACE vô hại mà chưa kiểm tra với dữ liệu giả.

### 13.1. Wire logs khác metrics

**Metrics:**

```text
redis_command_duration_seconds{command="GET",outcome="success"} ...
```

**Wire/command logs:**

```text
SET session:<token> <serialized-session>
```

Metrics được thiết kế tốt không cần chứa arguments. Wire logging có thể chụp dữ liệu thô ở mức protocol và phải được quản lý như dữ liệu nhạy cảm.

### 13.2. Không bật debug toàn package trên production một cách tùy tiện

Tránh quyết định:

```text
Redis timeout khó hiểu
    -> logging.level.root=TRACE
```

Điều này có thể kích hoạt logging ở nhiều subsystem ngoài Redis: HTTP body, SQL parameters, authorization headers, message payloads và framework internals.

Tốt hơn:

1. Xác định một thành phần cụ thể cần quan sát.
2. Chọn metric/trace trước.
3. Nếu buộc bật log chi tiết, đánh giá trước payload/metadata bị ghi.
4. Bật trong thời hạn ngắn và phạm vi hạn chế.
5. Có cơ chế tự thu hồi cấu hình và dọn dữ liệu.
6. Kiểm tra lại sau khi kết thúc.

### 13.3. Log level thay đổi runtime cũng cần audit

Một operator có quyền thay đổi logging level qua management endpoint hoặc config server có thể khiến ứng dụng bắt đầu ghi dữ liệu nhạy cảm.

Vì vậy quyền đổi log level production cần kiểm soát tương tự một thao tác vận hành nhạy cảm: authorization, auditing, timebox và review.

---

## 14. Một chính sách logging an toàn: allowlist, không phải blacklist

**Blacklist** nghĩa là log mọi dữ liệu trừ những field có tên `password`, `token`, `secret`. Cách này dễ bỏ sót:

```text
sessionKey
authHeader
refresh
credential
apiKey
authorization
otpCode
clientSecret
profileData
paymentInstrument
```

Hoặc trường có tên vô hại nhưng value là secret:

```json
{
  "value": "<access-token>"
}
```

**Allowlist** nghĩa là chỉ ghi những trường đã được xác định an toàn cho mục tiêu chẩn đoán.

Ví dụ danh sách trường được cho phép:

```text
operationName
commandFamily
outcome
elapsedMs
retryAttempt
payloadByteBucket
cacheName
serviceName
environment
traceId (nếu được phê duyệt)
errorClassName
```

Không có raw:

```text
Redis key
Redis value
Full command
Full HTTP request body
Authorization header
Session token
User email
Customer phone number
Serialized DTO
Request fingerprint có thể khôi phục nội dung nhạy cảm
```

### 14.1. Phân tầng mức nhạy cảm

Có thể áp dụng mô hình:

| Mức | Ví dụ | Cách xử lý log |
|---|---|---|
| Public/technical aggregate | `command=GET`, `outcome=timeout` | Có thể ghi theo policy |
| Internal metadata | Service name, bounded operation name | Giới hạn truy cập khi cần |
| Personal/sensitive metadata | Client IP, user ID, tenant ID | Phê duyệt mục đích, minimization |
| Secret/credential | Token, password, API key | Không ghi raw |
| Business payload | JSON hồ sơ/đơn hàng | Không ghi raw mặc định; hạn chế đặc biệt nếu có ngoại lệ |
| Regulated/high impact data | Thông tin tài chính, định danh, sức khỏe | Tuân theo policy/luật áp dụng, hạn chế nghiêm ngặt |

Phân loại phải xuất phát từ ngữ cảnh nghiệp vụ và quy định của tổ chức. Một field kỹ thuật cũng có thể nhạy cảm nếu kết hợp với những dữ liệu khác.

### 14.2. Structured logging giúp enforce schema

Thay vì log chuỗi tự do:

```text
"Redis called with " + key + " " + payload
```

dùng sự kiện có schema:

```json
{
  "event": "redis.operation",
  "operation": "product-cache-get",
  "command": "GET",
  "outcome": "success",
  "durationMs": 2.4,
  "cache": "product",
  "traceId": "<approved-correlation-id>"
}
```

Một logging wrapper có thể chỉ cho phép các field này, giúp review và tự động phát hiện việc thêm field nguy hiểm.

### 14.3. Không đẩy raw payload vào MDC

MDC hữu ích cho trace correlation:

```text
traceId
spanId
requestId kỹ thuật nếu policy cho phép
```

Không dùng:

```text
MDC["userEmail"]
MDC["accessToken"]
MDC["redisKey"]
MDC["requestBody"]
```

vì MDC có thể được tự động thêm vào **mọi log line**, khuếch đại mức lộ thông tin.

---

## 15. Ví dụ Spring Data Redis: metrics có ích nhưng không log key/value

Service sau đo thời gian `GET`, số lần hit/miss và failure mà không ghi key hoặc value vào metrics/logs.

```java
package com.example.observability;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SafeProductCacheReader {

    private static final Logger log =
        LoggerFactory.getLogger(SafeProductCacheReader.class);

    private final StringRedisTemplate redis;
    private final MeterRegistry registry;

    public SafeProductCacheReader(
            StringRedisTemplate redis,
            MeterRegistry registry) {
        this.redis = redis;
        this.registry = registry;
    }

    public String get(String productId) {
        // Key được xây dựng cho Redis nhưng không ghi vào log.
        String key = "product:" + productId;

        long started = System.nanoTime();
        String outcome = "success";

        try {
            String value = redis.opsForValue().get(key);

            registry.counter(
                "app.redis.cache.lookup",
                "cache", "product",
                "result", value == null ? "miss" : "hit"
            ).increment();

            return value;
        } catch (DataAccessException ex) {
            outcome = "error";

            // Không log ex.getMessage() hoặc raw command.
            log.warn(
                "Redis GET failed operation={} errorType={}",
                "product-cache-read",
                ex.getClass().getSimpleName()
            );

            throw ex;
        } finally {
            long elapsed = System.nanoTime() - started;

            Timer.builder("app.redis.operation.duration")
                .tag("operation", "product-cache-read")
                .tag("command", "GET")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
```

Điểm đáng chú ý:

- `productId` và `key` **không** được đưa vào log hoặc metric tags.
- `value` chỉ dùng để trả về cho ứng dụng và nhận biết cache hit/miss.
- `errorType` là class name có cardinality giới hạn hơn exception message.
- Timer ghi elapsed time mà không biết payload.
- `cache` và `operation` là tập tên được kiểm soát bởi code.
- `outcome` phân biệt lỗi kỹ thuật với cache miss thông thường.
- Exception vẫn được ném lên caller, nhưng tầng tiếp theo cũng phải tuân thủ redaction policy.
- Nếu cần đo latency riêng theo cache hit/miss, có thể thêm metrics hoặc spans khác với low-cardinality labels.

Đây là ví dụ instrumentation **ở ranh giới service**, không thay cho việc cấu hình security của logger, actuator và telemetry backend.

### 15.1. Cẩn trọng với dữ liệu trong exception ở tầng cao hơn

Đoạn code không log raw exception message, nhưng controller hoặc global exception handler có thể làm:

```java
log.error("Request failed", ex);
```

Khi đó stack trace và nested exception message vẫn được ghi.

Vì vậy, policy logging phải được áp dụng **end-to-end**, không chỉ ở gateway Redis.

### 15.2. Tại sao không log hash của productId một cách mặc định?

Một hash thông thường của định danh ít entropy như email, số điện thoại hoặc số tài khoản có thể bị dò bằng dictionary attack.

Nếu thật sự cần pseudonymous correlation, cân nhắc:

- Correlation ID ngẫu nhiên không gắn trực tiếp PII.
- HMAC với secret được quản lý và policy rotation.
- Scoped identifier theo tenant/operation.
- Truy vấn identity mapping trong một hệ thống được kiểm soát quyền.
- Retention ngắn và audit truy cập.

**Hash thuần không mặc nhiên biến PII thành dữ liệu công khai.**

---

## 16. Ví dụ đo payload bytes mà không ghi payload

Đôi khi cần biết Redis đang lưu payload quá lớn. Không nhất thiết phải log JSON.

```java
package com.example.observability;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SafeRedisValueWriter {

    private final StringRedisTemplate redis;
    private final DistributionSummary payloadSize;

    public SafeRedisValueWriter(
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;

        this.payloadSize =
            DistributionSummary.builder("app.redis.value.bytes")
                .baseUnit("bytes")
                .tag("operation", "product-cache-write")
                .register(registry);
    }

    public void put(String productId, String json) {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        payloadSize.record(bytes.length);

        redis.opsForValue().set(
            "product:" + productId,
            json,
            Duration.ofMinutes(10)
        );
    }
}
```

Đoạn này chỉ xuất số bytes vào metric, không lưu JSON trong log.

Tuy vậy:

- `String.getBytes(...)` tạo thêm allocation, có thể ảnh hưởng throughput nếu payload lớn.
- Nếu serializer không phải UTF-8 String, phải đo bytes từ serializer thực.
- Trong ngữ cảnh đặc biệt, kích thước payload có thể tiết lộ thông tin gián tiếp, nên có thể ghi theo bucket thay vì từng kích thước.
- Nếu JSON có secret, nó vẫn đang nằm trong biến ứng dụng/Redis; điều này là vấn đề data handling, không được giải quyết chỉ bằng tránh log.
- `DistributionSummary` phải cấu hình histogram/buckets theo nhu cầu thống kê thực tế.

### 16.1. Đo bytes theo bucket

Có thể phân loại:

```text
0-256 B
257 B-1 KiB
1-4 KiB
4-16 KiB
>16 KiB
```

Việc bucket hóa giúp đánh giá payload distribution mà ít tạo thông tin chi tiết hơn. Trong metrics backend, tránh label có giá trị bằng từng payload length nếu không cần thiết.

### 16.2. Đo bộ nhớ Redis không cần xem value

Nếu cần biết key family nào nặng, một job nội bộ có thể đo `MEMORY USAGE` trên **mẫu keys được kiểm soát**, chỉ xuất aggregate size/histogram. Không đưa danh sách raw keys vào dashboard/ticket rộng quyền.

Nếu key names chứa thông tin nhạy cảm, ngay cả bước lấy mẫu cũng cần quyền phù hợp.

---

## 17. Với Reactive Redis, không log toàn bộ Flux message

Trong WebFlux:

```java
Flux<Message> events = listener.receive(...);
```

hoặc Redis Streams:

```java
Flux<MapRecord<...>> events = receiver.receive(...);
```

Các operator như `doOnNext` rất thuận tiện để debug:

```java
events.doOnNext(event ->
    log.debug("Redis event={}", event)
);
```

Nhưng `event.toString()` có thể bao gồm channel, Stream fields, payload, IDs hoặc values. Trong hệ thống xử lý giao dịch, những dữ liệu đó có thể nhạy cảm.

Cách quan sát an toàn hơn:

```java
events
    .doOnNext(event ->
        registry.counter(
            "app.redis.events.received",
            "stream", "order-events"
        ).increment()
    )
    .flatMap(this::handleEvent);
```

Nếu cần log một lỗi xử lý:

```java
.doOnError(error ->
    log.warn(
        "Redis event consumer failed consumer={} errorType={}",
        "order-worker",
        error.getClass().getSimpleName()
    )
)
```

Không dùng một logger tổng quát serialize mọi event vào log.

### 17.1. Reactive `log()` operator cũng cần review

Reactor có một operator `.log()` để quan sát signals của Publisher. Nó có thể đưa `onNext` data vào logging tùy cách sử dụng và đối tượng dữ liệu.

Ví dụ rủi ro:

```java
redisStream
    .log()
    .flatMap(this::process);
```

Nếu `onNext` chứa record với payload cá nhân, output có thể làm lộ dữ liệu.

Khi điều tra reactive pipeline, cân nhắc:

- Metrics về item count và processing duration.
- `doOnError` ghi error category, không raw record.
- Sampling đã redact.
- Trace spans không có event body.
- Correlation ID được cấp và quản lý phù hợp.
- Reactor Context cho trace propagation mà không đưa PII vào log.

### 17.2. Cancellation và retry

Một `Flux` có thể `retryWhen`, phát lại một command hoặc nhận message nhiều lần tùy nguồn. Nếu debug bằng raw log từng message, một lỗi reconnect có thể làm volume log tăng đột biến.

Do đó, observability cần có **rate limit và sampling**, không chỉ redaction.

---

## 18. Micrometer tags: cardinality và bảo mật đi cùng nhau

Một metric có nhãn là:

```text
app.redis.operation.duration{
    operation="session-load",
    command="GET",
    outcome="success"
}
```

sẽ có một số tổ hợp nhãn hữu hạn.

Nếu thêm:

```text
key="session:<random-token>"
```

mỗi session có thể tạo một series khác. Kết quả:

1. Tăng cardinality và chi phí monitoring.
2. Có thể gây áp lực memory/CPU ở metrics collector.
3. Ghi token/identifier vào hệ thống metrics.
4. Khi metric được chia sẻ, nhiều người có thể xem key names.
5. Data retention metrics có thể dài hơn TTL session trên Redis.

Nên dùng:

```text
operation
commandFamily
cacheName
outcome
service
bounded_environment
```

và tránh:

```text
redisKey
rawValue
userEmail
sessionId
accessToken
requestBody
arbitraryTenantId nếu không có policy riêng
```

### 18.1. Bounded tenant label có luôn an toàn không?

Nếu hệ thống chỉ có vài tenant và operator cần nhìn theo tenant, vẫn phải đánh giá **quyền truy cập và khả năng suy ra doanh thu/hoạt động của từng khách hàng**. Không mặc định tenant ID được phép hiển thị chỉ vì số lượng nhỏ.

Với multi-tenant SaaS, nhiều khi dashboard toàn hệ thống chỉ cần số liệu aggregate; chi tiết theo tenant nên ở một dashboard riêng có RBAC.

### 18.2. URL tags

Ở HTTP metrics/tracing, dùng route template:

```text
/api/users/{id}
```

thay vì URL đã điền ID thật:

```text
/api/users/<sensitive-id>
```

Tương tự, với Redis, dùng `keyFamily=profile` thay vì raw key.

---

## 19. Distributed tracing: thu metadata hữu ích, không thu payload mặc định

Tracing có thể kết nối các spans:

```text
HTTP request
    |
    v
Controller
    |
    v
Service
    |
    v
Redis GET/SET span
    |
    v
Response
```

Một Redis span hữu ích có thể có:

```text
db.system = redis
db.operation.name = GET
server.address = <approved-host-label>
duration
status = error/success
```

Tên attributes thực tế phụ thuộc OpenTelemetry semantic conventions và instrumentation version. Không suy rằng mọi instrumentation tạo những field giống nhau.

### 19.1. Tránh command text chứa arguments

Một span có:

```text
db.statement = "SET session:<token> <serialized-secret>"
```

có thể biến tracing backend thành kho chứa secret. Nếu muốn lưu command statement, chỉ sử dụng một dạng sanitized/normalized:

```text
"SET <key> <value>"
```

hoặc đơn giản:

```text
operation = "SET"
keyFamily = "session"
```

Không bảo đảm một regular expression duy nhất loại bỏ mọi secret trong nested JSON, binary payload, Lua ARGV hoặc key naming tùy ý.

### 19.2. Sampling không giải quyết phân quyền

Giảm trace sampling từ 100% xuống 1% vẫn có thể giữ lại một số request chứa token hoặc PII. Sampling giảm volume, **không biến dữ liệu nhạy cảm thành an toàn**.

Thứ tự nên là:

```text
Data minimization / allowlist
    -> redaction
    -> access controls
    -> sampling
    -> retention
```

Không đảo ngược thành “cứ thu mọi thứ rồi sample ít đi”.

### 19.3. Trace baggage và context propagation

Trace baggage có thể lan truyền qua nhiều services. Không đưa thông tin nhạy cảm vào baggage chỉ để debug Redis, vì nó có thể được forward sang các hệ thống ngoài phạm vi mong muốn.

Dùng correlation IDs ngẫu nhiên hoặc opaque IDs có scope được kiểm soát.

---

## 20. Masking và redaction: phải thực hiện trước khi dữ liệu được ghi ra ngoài

Có ba mức xử lý phổ biến:

1. **Không thu thập:** tốt nhất, ví dụ chỉ ghi `command=SET`.
2. **Thay thế bằng metadata:** ghi `keyFamily=session`, `payloadBucket=1-4KiB`.
3. **Redact/pseudonymize:** dùng khi thật sự cần correlation, theo policy rõ ràng.

Ưu tiên thứ nhất, sau đó thứ hai. Trường hợp thứ ba đòi hỏi thiết kế và kiểm thử nghiêm túc.

### 20.1. Vì sao regex blacklist không đủ?

Một bộ lọc:

```text
replace("password=...", "password=[REDACTED]")
```

có thể không che:

```json
{"auth":{"secret":"..."}}
```

hoặc:

```text
Authorization: Bearer ...
api_key=...
credentialBlob=<binary>
```

Nó cũng không che token nằm trong tên key:

```text
session:<token>
```

Vì vậy **không khuyến nghị ghi toàn bộ raw Redis command rồi mới cố xóa các chuỗi trông giống secret**.

### 20.2. Structured allowlist

Một diagnostic event nên được tạo từ các field đã chọn:

```java
log.info(
    "Redis diag operation={} command={} outcome={} durationMs={}",
    "cart-save",
    "HSET",
    "success",
    elapsedMillis
);
```

Đây là cách loại bỏ hẳn khả năng vô tình gửi `KEYS`/`ARGV` vào log line này.

### 20.3. Log hashed identifiers khi nào?

Nếu cần liên kết nhiều log lines theo một user mà không hiển thị user ID trực tiếp, có thể dùng định danh giả danh được tạo bằng HMAC:

```text
HMAC(secret-key, tenantId + ":" + userId)
```

Tuy nhiên:

- Secret HMAC cần được bảo vệ, xoay vòng.
- Hash output vẫn là pseudonymous data có thể liên kết hành vi.
- Không dùng raw SHA-256 của email/phone ít entropy như phép “ẩn danh tuyệt đối”.
- Cần có policy về ai được phép truy ngược danh tính.
- Không ghi HMAC secret vào logs.
- Nếu không cần phân tích theo user, **không tạo identifier ấy**.

### 20.4. Redaction ở nhiều lớp

Cơ chế phòng vệ nhiều lớp có thể gồm:

```text
Application:
    Safe structured log schema
          |
          v
Logging framework:
    Filters/sanitizers theo policy
          |
          v
Telemetry collector:
    Attribute allowlist + drop sensitive fields
          |
          v
Central log/trace backend:
    RBAC + retention + audit
```

Cơ chế lọc ở collector là **lưới an toàn**, không phải lý do để ứng dụng gửi plaintext secrets qua pipeline telemetry.

---

## 21. Quyền truy cập MONITOR và nguyên tắc least privilege

Quyền xem MONITOR cần được xem là một quyền nhạy cảm. Redis ACL hỗ trợ quản lý user/command permissions tùy phiên bản.

Ví dụ về định hướng phân quyền:

```text
Application Redis user:
    Chỉ các data commands cần cho service
    Không được MONITOR
    Không có quyền admin không cần thiết

Observability user:
    Chỉ được đọc metrics/metadata cần thiết
    Không mặc định được MONITOR

Emergency operator:
    Quyền chẩn đoán tạm thời theo phê duyệt
    Có audit, timebox và thu hồi
```

Có thể kiểm tra ACL user trong môi trường được phép bằng các lệnh quản trị như `ACL GETUSER`, nhưng không nên tự thay đổi ACL production ngoài quy trình cấp quyền.

### 21.1. Không chia sẻ Redis admin credentials cho mọi developer

Nếu tất cả developer đều dùng một Redis password có quyền admin, rất khó:

- Xác định ai đã MONITOR.
- Thu hồi quyền cho một người.
- Giới hạn node/command.
- Audit thao tác chẩn đoán.
- Tách quyền ứng dụng khỏi quyền vận hành.

Nên dùng danh tính riêng theo service/operator, secret management và quyền tối thiểu.

### 21.2. Hạn chế truy cập metadata cũng quan trọng

Không chỉ MONITOR, những lệnh như `SLOWLOG GET`, `CLIENT LIST`, `ACL LOG`, `SCAN` và một số interface performance insights cũng có thể lộ metadata.

Quyền truy cập cần được thiết kế theo **mức nhạy cảm của nội dung thực tế**, không chỉ tên lệnh có vẻ read-only.

### 21.3. Không đưa Redis password lên command line công khai

Một lệnh shell có password thô trong tham số có thể bị ghi vào terminal history, process listings hoặc tooling.

Trong môi trường có authentication, dùng cơ chế secret management hoặc cách nhập credentials được tổ chức chấp thuận. Không chép password Redis vào ticket, screenshot, shell script công khai hoặc MONITOR transcript.

Các ví dụ `redis-cli` trong bài này sử dụng Redis lab local không có dữ liệu thật; không phải hướng dẫn bypass xác thực production.

---

## 22. Chỉ dùng MONITOR theo một runbook được phê duyệt

Nếu metrics, commandstats và tracing chưa đủ, một phiên MONITOR production có thể được cân nhắc **chỉ khi có mục đích rõ ràng, người có thẩm quyền cho phép và kiểm soát rủi ro**.

Một runbook có thể gồm những bước sau.

### Bước 1 — Định nghĩa câu hỏi chính xác

Ví dụ:

> “Một instance API có đang gửi `HGETALL` thay vì `HGET` và gây tải lên Redis primary X không?”

Không dùng câu hỏi quá rộng:

> “Muốn xem mọi dữ liệu Redis đang làm gì.”

### Bước 2 — Thử công cụ ít xâm lấn

Lấy:

```redis
INFO commandstats
INFO stats
SLOWLOG LEN
LATENCY LATEST
```

và metrics của Spring service. Nếu đủ trả lời, dừng ở đây.

### Bước 3 — Đánh giá sensitivity

Trước khi MONITOR, xác định:

- Redis có session/token, PII hoặc business payload không?
- Service nào chia sẻ Redis instance?
- Có Redis Cluster nhiều node không?
- Command đang điều tra có mang value/ARGV nhạy cảm không?
- Ai sẽ nhìn output và lưu ở đâu?
- Có thể tái hiện trên staging bằng dữ liệu giả không?
- Có cách bật một log statement **đã redact ở service** thay thế không?

Nếu câu trả lời cho thấy rủi ro quá cao, nên chọn phương án khác.

### Bước 4 — Phê duyệt và cấp quyền tạm

Ghi nhận:

```text
Incident ID
Người đề nghị
Người phê duyệt
Node/instance
Mục đích
Thời gian dự kiến
Giới hạn dữ liệu được thu
Nơi lưu output
Người có quyền truy cập
Kế hoạch thu hồi và xóa dữ liệu
```

Không dùng một tài khoản admin chia sẻ vô thời hạn.

### Bước 5 — Thu hẹp thời gian

Nếu được chấp thuận, giữ phiên quan sát **ngắn nhất có thể**, ví dụ một khoảng ngắn để xác minh hành vi. Không để MONITOR chạy suốt ngày hoặc chạy làm background job liên tục.

Một phiên MONITOR không nên được cấu hình để tự chạy lại vô hạn sau disconnect mà không có kiểm soát.

### Bước 6 — Không ghi raw output ra centralized log mặc định

Hãy cẩn trọng với:

```text
Terminal session recording
CI/CD console output
Shell transcript
kubectl logs
Log agents tự thu stdout/stderr
Remote desktop recording
Screen sharing
Chat attachments
Issue tracker
Personal computer downloads
```

Một lệnh MONITOR xuất ra terminal có thể đã đủ tạo rủi ro, ngay cả khi người vận hành không chủ động `tee` vào file.

Không mặc định lưu raw MONITOR output để “phân tích sau”. Nếu ngoại lệ cho phép capture, phải có storage được kiểm soát, mã hóa, retention ngắn, auditing và xử lý redaction trước khi chia sẻ rộng hơn.

### Bước 7 — Dừng và xác nhận kết thúc

Dừng MONITOR session bằng cách đóng kết nối/`Ctrl+C` ở CLI lab hoặc phương thức phù hợp với công cụ.

Kiểm tra:

- Không còn session MONITOR không cần thiết.
- Quyền tạm đã được thu hồi.
- Không còn debug/wire logging vượt policy.
- Các bản ghi tạm được xử lý theo retention.
- Incident report chỉ chứa metadata/anonymized findings.

### Bước 8 — Ghi lại điều đã xác minh

Ví dụ báo cáo an toàn:

```text
Incident: INC-2026-0428

Observation:
  - Redis primary X nhận HGETALL rate cao hơn baseline.
  - Service order-reader là nguồn được xác định qua
    app metrics/tracing.
  - Một endpoint đã gọi HGETALL cho Hash quá lớn.

Action:
  - Chuyển sang HMGET cho fields cần thiết.
  - Thêm service-level timing metrics.

No Redis payload or full key names included.
```

Không cần paste raw commands chứa PII vào báo cáo nếu kết luận chỉ liên quan command type và access pattern.

---

## 23. Khi sự cố cần xác định key nào đang bị spam

Đây là một tình huống thực tế: `INFO commandstats` cho biết `HGETALL` nhiều, nhưng không biết key family nào.

Trước khi MONITOR, có thể thử:

1. Bật **service-level operation tags**: `cart-read`, `profile-read`, `order-read`.
2. Lấy traces cho endpoint có liên quan, không ghi Redis key.
3. Đếm lệnh theo code path ở gateway `RedisTemplate`.
4. Đo số lời gọi method trên một business request.
5. Kiểm tra cache key generator bằng unit/integration test.
6. Dùng một **feature-flagged diagnostic counter** theo key family, không theo raw key.
7. Nếu cần điều tra đúng một request, dùng correlation ID và logging metadata đã allowlist.

Ví dụ:

```java
registry.counter(
    "app.redis.operation.count",
    "operation", "cart-load",
    "command", "HGETALL"
).increment();
```

Nếu tag `operation` chỉ có một tập tên cố định trong code, bạn có thể đo chính xác traffic theo code path mà không lộ cart ID.

### 23.1. Nếu cần tìm một key cực nóng?

Một key cực nóng đôi khi cần điều tra sâu, nhưng không phải mọi quan sát đều cần log raw key. Có thể:

- Đo theo key family/aggregate partition.
- Dùng instrumentation tại ứng dụng đếm hash/HMAC identifier theo scope được phê duyệt.
- Tạo metrics tạm có số nhóm hạn chế, không đẩy mọi key vào labels.
- Sử dụng Redis tooling/managed service hỗ trợ hot-key analysis theo quy trình bảo mật.
- Lấy mẫu ở staging bằng dữ liệu giả.

Nếu bắt buộc xác định key cụ thể trong production, kết quả nên được lưu/hiển thị chỉ trong kênh giới hạn quyền, không đưa vào dashboard chung.

### 23.2. Phân biệt tìm lỗi key format với xem data value

Nếu nghi ngờ một service build key sai, thường chỉ cần test:

```text
Expected key format:
    order:{aggregate-id}:status

Observed family:
    order:<unexpected-format>
```

Không cần truy xuất bản ghi thật. Một unit test với ID giả có thể xác định lỗi ở `KeyFactory` nhanh hơn MONITOR.

---

## 24. Ứng dụng Spring Cache: chẩn đoán hit/miss mà không lộ dữ liệu

Trong Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto loadProduct(String productId) {
    // ...
}
```

Một request có thể:

```text
Cache hit:
    GET -> response

Cache miss:
    GET -> database load -> SET -> response
```

Metrics cần có:

```text
cacheName
hit/miss
cache lookup duration
load duration
load failure
payload size distribution
```

Không cần log:

```text
"Cache missed for user email=..."
"Cache SET value=<whole DTO>"
```

### 24.1. Cache key prefix có thể tiết lộ namespace

Spring Redis Cache có thể thêm prefix cho key theo cache name và các quy tắc cấu hình. Nếu cache name chứa tenant hoặc thông tin đặc thù nhạy cảm, tên Redis key có thể lộ qua MONITOR/SLOWLOG.

Nên dùng cache names kỹ thuật có giới hạn và thiết kế key generation nhất quán.

### 24.2. TTL là metric, không phải dữ liệu phải log

Nếu đang điều tra vì sao cache miss nhiều, có thể đo:

```text
Average remaining TTL
Expired/evicted keys
Cache miss rate
Cache writes/s
```

mà không ghi serialized value.

Nếu cần kiểm tra TTL một key đại diện, chỉ dùng key giả trong lab hoặc có sự cho phép rõ cho key production cụ thể.

---

## 25. Redis Repository: index và metadata cũng có thể nhạy cảm

Một Redis Repository có thể lưu entity Hash và secondary index.

Ví dụ ở mức khái niệm:

```text
Entity key:
    users:<entity-id>

Index key:
    users:email:<indexed-value>
```

Format thực tế phụ thuộc mapping/version. Nếu secondary index dựa trên email hoặc thuộc tính cá nhân, **tên key/index member** có thể lộ thông tin nhạy cảm.

Nếu MONITOR thấy `SADD`, `SREM`, `HSET` và các key chỉ mục, operator có thể suy ra hoạt động của user và các thay đổi nghiệp vụ.

Do đó:

- Review các field đánh dấu index.
- Không tự log index value.
- Giới hạn quyền xem raw keys.
- Đo `Repository.save` latency và command count bằng instrumentation cấp service.
- Không xem toàn bộ Redis keyspace như một danh sách public.
- Có chính sách cleanup và retention cho index keys.

### 25.1. Expiration/shadow copy

Một số cấu hình Redis Repository liên quan TTL có thể tạo metadata hoặc shadow copies để phục vụ expiration events. Việc chỉ nhìn một entity chính có thể không phản ánh toàn bộ dữ liệu Redis đang lưu.

MONITOR không phải công cụ thay cho phân tích data model và memory footprint. Có thể dùng keyspace/memory sampling theo quy trình có kiểm soát để đánh giá overhead.

---

## 26. Data privacy trong multi-tenant Redis

Nếu nhiều tenant dùng chung Redis:

```text
Service A -> Redis
Service B -> Redis
Service C -> Redis
```

một operator MONITOR vào Redis có thể xem các commands của nhiều workload trong phạm vi node được quan sát, không nhất thiết chỉ tenant mà họ được giao chẩn đoán.

Các rủi ro:

- Lộ key naming scheme của tenant khác.
- Lộ nội dung payload của service khác.
- Suy ra traffic/hoạt động kinh doanh.
- Truy cập dữ liệu không thuộc phạm vi authorization.
- Đưa dữ liệu nhiều tenant vào cùng file log.
- Không thể tách retention/consent/legal basis cho từng tenant.

### 26.1. Phân quyền application không tự áp dụng cho MONITOR

Một endpoint HTTP có thể kiểm tra authorization tenant rất chặt. Nhưng một user Redis có quyền MONITOR là quyền ở tầng Redis, không phải đi qua controller của application.

**RBAC của web app không tự giới hạn nội dung MONITOR mà operator được xem.**

Do đó, quyền Redis diagnostic phải được đánh giá độc lập.

### 26.2. Segmentation giúp giảm blast radius

Một số kiến trúc cần tách:

- Redis instances cho workload nhạy cảm.
- Secrets/session storage khỏi cache public.
- Tenant groups theo yêu cầu tuân thủ.
- Observability roles và data access boundaries.
- Data retention khác nhau theo loại hệ thống.

Không phải mọi ứng dụng đều cần một Redis instance riêng cho mỗi tenant. Đây là trade-off vận hành và chi phí, nhưng khi dữ liệu rất nhạy cảm, **mức blast radius của MONITOR** nên là một yếu tố trong đánh giá.

---

## 27. Quyền truy cập và thời gian lưu log

Ngay cả khi log đã được giảm thiểu payload, cần quản lý vòng đời dữ liệu.

### 27.1. Log retention có thể dài hơn Redis TTL

Một session key có TTL 15 phút:

```text
Redis session expires after 15 minutes.
```

Nhưng một raw MONITOR transcript ghi session token vào log có thể tồn tại 30 hoặc 90 ngày.

Khi đó dữ liệu vốn được thiết kế tạm thời lại tồn tại lâu trong hệ thống log, có thể vi phạm kỳ vọng bảo mật/riêng tư và tăng khả năng bị lộ.

TTL trên Redis **không xóa bản sao đã được ghi vào logs, traces, metrics hoặc backups**.

### 27.2. Chính sách retention nên theo data classification

Ví dụ một khung chính sách:

| Loại telemetry | Mục đích | Retention |
|---|---|---|
| Aggregate Redis command metrics | Capacity/SLO | Theo chính sách metrics |
| Service operation logs đã redact | Sự cố vận hành | Theo chính sách logs |
| Security audit events | Phân tích truy cập | Theo nghĩa vụ và chính sách riêng |
| Raw diagnostic capture ngoại lệ | Incident đặc biệt | Ngắn, có phê duyệt và xóa xác nhận |
| Payload chứa secret | Không phải telemetry mặc định | Không thu raw |

Không có một số ngày chung đúng cho mọi hệ thống. Retention cần dựa trên quy định, hợp đồng, yêu cầu kỹ thuật và mục đích sử dụng.

### 27.3. Encryption at rest và RBAC

Những kênh telemetry có dữ liệu nội bộ nên có:

- Encryption in transit và at rest.
- Access control theo vai trò.
- Audit việc xem/xuất logs.
- Thời hạn lưu rõ ràng.
- Kiểm soát tải xuống/copy.
- Cơ chế xóa và backup retention.
- Quy trình phản ứng khi credential hoặc PII bị lộ.

Một file log trên máy cá nhân của operator có thể phá vỡ những kiểm soát của central log backend. Vì vậy runbook cần quản lý cả **nơi output được hiển thị và lưu tạm**.

---

## 28. Pipeline xử lý telemetry: nơi dữ liệu có thể bị nhân bản

Khi bật debug Redis, dữ liệu không chỉ nằm trong terminal:

```text
Redis / Spring App
      |
      +--> stdout/stderr
             |
             v
       Docker/Kubernetes logs
             |
             v
       Log agent / collector
             |
             v
       Message queue / telemetry gateway
             |
             v
       Central log storage
             |
             +--> Dashboard
             +--> Alerting
             +--> Export API
             +--> Archive/backup
```

Một lệnh ghi value nhạy cảm có thể được nhân bản qua các bước. Xóa file local **không chắc đã xóa bản sao ở collector, queue, archive hoặc dashboard cache**.

### 28.1. Vì sao “sẽ xóa log sau khi debug” chưa đủ?

Sau khi raw secret đã được gửi tới nhiều hệ thống, việc xóa đầy đủ rất khó kiểm chứng.

Do đó, **phòng ngừa trước khi ghi** quan trọng hơn việc hứa sẽ cleanup sau.

### 28.2. Nếu đã lộ dữ liệu thì sao?

Không tiếp tục dùng log như một công cụ chia sẻ tự do. Hãy kích hoạt quy trình incident của tổ chức:

1. Dừng capture và thu hồi các debug modes.
2. Hạn chế quyền truy cập dữ liệu đã thu.
3. Xác định phạm vi thời gian, loại dữ liệu, người có quyền truy cập và nơi lưu bản sao.
4. Rotate/revoke credentials hoặc tokens bị ảnh hưởng khi cần.
5. Xử lý xóa/quarantine theo policy và khả năng của từng hệ thống.
6. Ghi nhận/audit incident và thông báo theo nghĩa vụ áp dụng.
7. Khắc phục nguyên nhân: logging config, ACL, app code, data classification.
8. Thêm kiểm thử và guardrails để không lặp lại.

Không paste lại secret vào ticket incident chỉ để chứng minh nó đã bị lộ; dùng mô tả loại secret và identifier đã redact.

---

## 29. Debug logging và stack traces: tránh vô tình chứa command arguments

Một số framework/driver có thể đưa command metadata vào exception, span hoặc log theo cấu hình. Một lệnh sai hoặc script thất bại có thể tạo message liên quan key names/arguments.

Ví dụ:

```java
try {
    redis.opsForValue().set(key, value);
} catch (RuntimeException ex) {
    log.error("Redis failed with exception={}", ex);
}
```

Tùy logger và `toString()` của exception, nội dung có thể chứa nhiều dữ liệu hơn dự định.

An toàn hơn là log có cấu trúc:

```java
catch (RuntimeException ex) {
    log.warn(
        "Redis operation failed op={} category={}",
        "cart-write",
        ex.getClass().getSimpleName()
    );
    throw ex;
}
```

Nếu cần stack trace để điều tra bug, chỉ mở qua kênh hạn chế hoặc bảo đảm message được sanitize theo policy, không ghi raw full command vô điều kiện.

### 29.1. Tránh logging DTO bằng `toString()`

Java record/Lombok có thể in toàn bộ fields:

```java
record SessionData(
    String userId,
    String accessToken,
    String refreshToken
) {}
```

Một câu:

```java
log.debug("session={}", sessionData);
```

có thể đưa tokens vào log.

Tốt hơn là viết một `toSafeLogFields()` hoặc event log riêng chỉ chứa các trường được cho phép. Không nên sửa `toString()` của DTO thành cơ chế bảo vệ duy nhất, vì serializer, tracing và debugger vẫn có những đường truy cập dữ liệu khác.

### 29.2. Bật request body logging có thể lộ Redis payload từ nguồn HTTP

Nếu endpoint HTTP nhận JSON chứa dữ liệu cá nhân và lưu vào Redis, một request-body logger ở WebFlux/MVC có thể lộ nội dung **trước khi Redis được gọi**.

Do đó chính sách “Redis logger không ghi value” không đủ nếu tầng HTTP vẫn ghi toàn bộ request body.

---

## 30. Lựa chọn công cụ quan sát theo tình huống sự cố

### Tình huống A — Redis có vẻ chậm

Bước đầu:

```text
Spring HTTP p95/p99
Lettuce/Redis operation timing
INFO commandstats
SLOWLOG (có kiểm soát)
LATENCY
CPU/network/GC
```

Không bắt đầu bằng MONITOR chỉ vì người dùng báo ứng dụng chậm.

### Tình huống B — Cache hit rate thấp

Đo:

```text
Spring Cache hit/miss
Key family
TTL distributions
Eviction count
Cache writes/s
Database load
```

Chỉ xem key names thực khi có lý do và quyền phù hợp; có thể kiểm tra KeyGenerator trong test.

### Tình huống C — Một service đang gửi sai lệnh

Nếu nghi ngờ service dùng `HGETALL` thay vì `HMGET`, trước tiên kiểm tra:

- Source code và integration test.
- Metrics per operation.
- Tracing operation names.
- INFO commandstats delta trước/sau một test có kiểm soát.

MONITOR trong staging với dữ liệu giả có thể giúp xác nhận command protocol nếu thật sự cần.

### Tình huống D — Redis Streams bị backlog

Ưu tiên:

```redis
XINFO GROUPS orders:events
XINFO CONSUMERS orders:events order-workers
XPENDING orders:events order-workers
XLEN orders:events
```

Sau đó đo handler rate, ACK rate, retry/DLQ. Không cần đọc raw event fields bằng MONITOR.

### Tình huống E — Redis Cluster primary quá tải

Đo theo primary:

```text
CPU
ops/s
command mix
memory
network
client timeout
hot slots
```

Một MONITOR connection tới một primary không cho toàn bộ picture. Khi cần tìm hot key, dùng công cụ hot-key analysis có quyền và dữ liệu tối thiểu.

### Tình huống F — Lỗi xác thực Redis

Ưu tiên authentication error classes, ACL/connection metadata và security audit phù hợp. Không bật raw AUTH logging hoặc chia sẻ password chỉ để giải thích một lỗi kết nối.

---

## 31. Công cụ client-side có thể hữu ích hơn MONITOR

Đôi khi mục tiêu là xem **Spring service A gọi Redis như thế nào**, chứ không phải toàn Redis server.

Trong trường hợp đó, instrumentation ngay tại service A có lợi thế:

- Phân biệt business operation.
- Chỉ log phạm vi service A.
- Có HTTP traceId.
- Có thể chọn allowlist fields.
- Không phải xem payload của service B/C.
- Dễ bật/tắt bằng feature flag.
- Có thể rate limit và sample.
- Không buộc Redis format mọi command cho MONITOR.

### 31.1. Một RedisGateway có diagnostics giới hạn

Kiến trúc:

```text
Service
   |
   v
SafeRedisGateway
   |
   +--> Timer(command family, outcome)
   +--> Counter(cache hit/miss)
   +--> Diagnostic event đã allowlist
   |
   v
StringRedisTemplate / ReactiveRedisTemplate
   |
   v
Redis
```

Một gateway như vậy có thể giúp nhóm ứng dụng debug command mix mà không cần MONITOR.

### 31.2. Cẩn trọng với proxy/interceptor tổng quát

Một AOP interceptor ghi mọi arguments của method:

```java
log.debug("method={} args={}", methodName, Arrays.toString(args));
```

rất nguy hiểm khi intercept RedisTemplate hoặc service chứa DTO nhạy cảm.

Thay vì log arbitrary arguments, hãy map method -> operation name và chỉ ghi số liệu được phê duyệt.

### 31.3. Instrumentation phải giữ nguyên semantics

Không để logging làm:

- Gọi `toString()` tốn CPU trên payload lớn.
- Serialize DTO thêm lần nữa.
- Thay đổi thời điểm subscribe Reactive `Mono`.
- Consume một `Flux` chỉ để in dữ liệu.
- Thêm command Redis mới trong hot path.
- Làm exception bị nuốt.
- Tăng p99 đáng kể.

Observability tốt phải có overhead được hiểu và đo, đặc biệt trong hệ thống throughput cao.

---

## 32. Ví dụ logging khi Redis call lỗi nhưng không tiết lộ command

Giả sử cần phân biệt timeout và lỗi khác.

```java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class SafeSessionCache {

    private static final Logger log =
        LoggerFactory.getLogger(SafeSessionCache.class);

    private final StringRedisTemplate redis;

    public SafeSessionCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String load(String sessionKey) {
        try {
            return redis.opsForValue().get(sessionKey);
        } catch (DataAccessException ex) {
            log.warn(
                "Session Redis lookup failed operation={} " +
                "errorType={} retryPolicy={}",
                "session-read",
                ex.getClass().getSimpleName(),
                "bounded-at-service-boundary"
            );
            throw ex;
        }
    }
}
```

Ở đây `sessionKey` không được log.

**Chú ý:** phân loại timeout bằng class hierarchy hoặc cause chain cần được thiết kế theo version Spring Data Redis/Lettuce thực tế. Không phân loại dựa vào việc in raw exception message rồi tìm substring `"timeout"`.

### 32.1. Correlation ID không phải Redis key

Nếu cần điều tra một HTTP request, cấp `traceId`/`requestId` riêng cho telemetry:

```text
traceId = 7f8d...
operation = session-read
outcome = timeout
```

Không cần thay bằng session token. Nếu một request chứa idempotency key nghiệp vụ, nó cũng có thể là metadata nhạy cảm và nên được quản lý theo policy.

---

## 33. Thử nghiệm an toàn với MONITOR trong môi trường lab

Mục tiêu là hiểu công cụ mà **không tiếp xúc dữ liệu thật**.

### Chuẩn bị

Dùng một Redis instance test riêng, ví dụ ở:

```text
localhost:6379
```

Chỉ lưu những dữ liệu giả trong namespace `lab:`. Không sử dụng Redis production hay instance dùng chung với session thực.

### Terminal A: mở MONITOR

```bash
redis-cli -h 127.0.0.1 -p 6379 MONITOR
```

### Terminal B: tạo dữ liệu giả

```bash
redis-cli -h 127.0.0.1 -p 6379 SET lab:product:42 demo
redis-cli -h 127.0.0.1 -p 6379 GET lab:product:42
redis-cli -h 127.0.0.1 -p 6379 HSET lab:profile:42 tier DEMO
redis-cli -h 127.0.0.1 -p 6379 XADD lab:events '*' type DemoCreated
```

Trong một số shells, cú pháp escape `*` cần phù hợp; ví dụ trên dùng dấu nháy đơn cho môi trường shell hỗ trợ. Trên Windows PowerShell/cmd có thể cần điều chỉnh quoting theo công cụ. Không sử dụng output này để làm dữ liệu thật.

### Quan sát

Ghi nhận:

- Command name có xuất hiện không?
- Tên key được hiển thị thế nào?
- Arguments được biểu diễn ra sao?
- Khi gọi `GET`, MONITOR có trả value của GET không?
- Khi gọi `SET`, value là argument nên có xuất hiện không?
- Output có timestamp/client metadata nào?
- Nếu dùng Redis Cluster, một kết nối MONITOR tới một node quan sát được phạm vi nào?

### Kết thúc

Dừng MONITOR session bằng `Ctrl+C` hoặc đóng kết nối.

**Không upload raw output chứa dữ liệu production vào repo, issue hoặc chat.** Trong bài lab chỉ sử dụng giá trị giả như `DEMO`.

---

## 34. Bài thực hành 1 — Phân loại dữ liệu có thể lộ

Cho các command **giả định**:

```redis
GET session:<opaque-token>
SET user:42:profile '{"email":"<redacted>"}'
HSET user:42 phone "<redacted>"
XADD orders:events * eventId evt-42 customerId "<redacted>"
PUBLISH notifications:user '{"message":"<redacted>"}'
DEL password-reset:<token>
```

Hãy lập bảng:

1. Lệnh nào có dữ liệu nhạy cảm trong **key name**?
2. Lệnh nào có dữ liệu nhạy cảm trong **value/arguments**?
3. Lệnh nào MONITOR có thể không hiển thị business result dù command xuất hiện?
4. Có thể ghi loại metadata nào để debug mà không lộ value?
5. Nếu phải điều tra vì sao Redis chậm, công cụ nào tốt hơn MONITOR?

Mục đích là học cách phân loại, không khôi phục hay xử lý secret thật.

## 35. Bài thực hành 2 — Chẩn đoán qua commandstats

Trên Redis test:

```redis
INFO commandstats
```

Ghi `cmdstat_get` và `cmdstat_set` counts. Gọi một số `GET`/`SET` bằng ứng dụng Spring Data Redis với các giá trị giả.

Sau đó đọc `INFO commandstats` lần nữa. Tính delta.

Giải thích tại sao có thể biết command rate mà không cần MONITOR full arguments.

## 36. Bài thực hành 3 — Micrometer có tags an toàn

Tạo `SafeProductCacheReader` như ví dụ phần 15.

Yêu cầu:

1. Ghi duration của Redis GET.
2. Đếm hit và miss.
3. Đếm errors theo class name hoặc nhóm lỗi.
4. Không ghi `productId`, Redis key hay raw value.
5. Không dùng user email làm metric tag.
6. Kiểm tra Actuator metrics trong môi trường test.
7. Mô tả cách aggregate p95/p99 mà không suy từ mean.

Thảo luận sự khác biệt giữa **observability hữu ích** và **thu dữ liệu nghiệp vụ ngoài mục đích**.

## 37. Bài thực hành 4 — Redact logs theo allowlist

Cho một log raw giả:

```text
Redis SET session:<token> {"userId":"<id>","accessToken":"<token>"}
```

Hãy thiết kế log event thay thế:

```json
{
  "event": "redis.operation",
  "operation": "session-write",
  "command": "SET",
  "outcome": "success",
  "durationMs": 1.2,
  "payloadBucket": "1-4KiB"
}
```

Không dùng raw key/payload.

Giải thích vì sao cách này an toàn hơn việc đưa toàn bộ raw command vào log rồi dùng regex xóa chữ `password`.

## 38. Bài thực hành 5 — Lỗi do log DTO

Tạo một DTO giả:

```java
record DemoSession(
    String internalUserId,
    String accessToken
) {}
```

Thử gọi `toString()` trong test với token giả. Quan sát nó có thể in mọi field.

Sau đó tạo `SafeSessionLogEvent` chỉ gồm:

```text
operationName
outcome
elapsedMs
traceId được phê duyệt
```

Giải thích vì sao không nên log DTO trực tiếp trong controller hoặc handler Redis.

## 39. Bài thực hành 6 — WebFlux Reactor log()

Trong WebFlux test, tạo một `Flux<DemoEvent>` chứa value giả. Quan sát `.log()` trong test có thể hiển thị tín hiệu `onNext` theo cấu hình.

Thay bằng:

```java
.doOnNext(event ->
    metrics.counter(
        "app.redis.events",
        "type", "demo"
    ).increment()
)
```

Đề xuất cách ghi error category mà không serialize cả event.

Thảo luận:

- Bật operator `.log()` trên production khi nào có rủi ro?
- Một reconnect gây repeated event logs có làm tăng volume không?
- Tại sao sampling không loại bỏ yêu cầu redaction?

## 40. Bài thực hành 7 — Multi-tenant và phân quyền

Giả sử một Redis instance phục vụ:

```text
Tenant A sessions
Tenant B carts
Tenant C product cache
```

Một operator chỉ được phụ trách Tenant B muốn chạy MONITOR.

Hãy xác định:

1. Tại sao MONITOR có thể vượt ranh giới tenant trong node?
2. Quyền application RBAC có giới hạn MONITOR được không?
3. Có thể dùng service-level metrics để xem cart operations không?
4. Khi nào phải xin phê duyệt riêng?
5. Nếu thu raw data, retention/RBAC/audit phải thế nào?
6. Khi nào nên cân nhắc tách Redis instance/workload nhạy cảm?

## 41. Bài thực hành 8 — Điều tra HGETALL chậm mà không dùng MONITOR

Một endpoint có p99 tăng. Redis `INFO commandstats` báo `HGETALL usec_per_call` tăng; HTTP tracing cho thấy route `GET /api/cart/{id}`.

Hãy:

1. Đo app service timer cho cart reads.
2. Đếm số lần `HGETALL` mỗi request.
3. Đo kích thước Hash đại diện trong test.
4. Xem `SLOWLOG` qua quyền phù hợp nếu cần.
5. Đề xuất thay bằng `HMGET` chỉ lấy fields cần thiết.
6. Chạy lại load test.
7. Báo kết quả không đính kèm raw cart IDs hoặc contents.

Giải thích vì sao cách này cho thông tin hành động được mà ít rủi ro dữ liệu hơn MONITOR.

## 42. Bài thực hành 9 — Cluster và phạm vi MONITOR

Trong Redis Cluster test:

1. Chọn hai keys giả được định tuyến tới hai slots thuộc hai primary khác nhau.
2. Mở MONITOR trên một node.
3. Gửi commands tới cả hai keys.
4. Quan sát commands xuất hiện trong phạm vi node đang theo dõi.
5. Dùng `INFO commandstats` trên các primary để đối chiếu.
6. Giải thích vì sao không được dùng một MONITOR session làm bằng chứng mọi cluster traffic.

Chỉ dùng lab có quyền và dữ liệu giả.

## 43. Bài thực hành 10 — Runbook MONITOR khẩn cấp

Viết một runbook một trang với:

```text
Incident question
Approval
Scope of node(s)
Data classification
Least-privilege operator
Alternative metrics already tried
Timebox and stop condition
Output handling
Redaction/access restrictions
Audit and cleanup
Post-incident finding
```

Đưa ra điều kiện rõ ràng để **không chạy MONITOR** khi có token/PII và không có nơi xử lý dữ liệu chẩn đoán thích hợp.

## 44. Bài thực hành 11 — Retention và log leaks

Giả sử Redis session có TTL 30 phút, nhưng raw debugging log chứa session token được giữ 90 ngày trong hệ thống tập trung.

Hãy trả lời:

1. TTL Redis có xóa token khỏi hệ log không?
2. Ai có thể nhìn thấy token trong 90 ngày?
3. Cần chính sách phân quyền và retention nào?
4. Nếu token còn hợp lệ, cần phản ứng sự cố thế nào?
5. Làm sao ngăn lặp bằng logging allowlist và không bật wire logs?
6. Những bản sao nào có thể tồn tại trong collector, archive, ticket, screenshot?

## 45. Bài thực hành 12 — Tracing an toàn

Tạo một trace giả:

```text
HTTP GET /api/products/{id}
  -> service product-load
  -> Redis GET
  -> response
```

Chỉ cho phép những attributes:

```text
http.route=/api/products/{id}
db.system=redis
db.operation.name=GET
operation=product-cache-read
outcome=success
```

Không ghi raw Redis key, JSON, email, token.

Thảo luận cách tracing giúp phân biệt Redis latency và application latency mà không cần xem payload.

---

## 46. Checklist trước khi bật một chế độ debug Redis

- [ ] Có câu hỏi chẩn đoán cụ thể, không chỉ “xem mọi command”?
- [ ] Đã thử `INFO commandstats`, client timing, HTTP metrics và traces?
- [ ] Có thể tái hiện trên staging với dữ liệu giả không?
- [ ] Đã xác định Redis node/Cluster scope?
- [ ] Biết dữ liệu key names/arguments có chứa token, PII, payment, session không?
- [ ] Có đánh giá quyền operator và least privilege?
- [ ] Đã phân biệt command timing với server execution và HTTP latency?
- [ ] MONITOR hoặc debug mode có thể làm tăng CPU/network/tail latency không?
- [ ] Đã xác định nơi stdout/stderr/terminal session được lưu?
- [ ] Có cơ chế timebox, stop condition và thu hồi quyền?
- [ ] Có chính sách không ghi raw key/value vào shared ticket/log?
- [ ] Metrics tags có cardinality thấp và không chứa secrets?
- [ ] Logging framework, tracing collector và APM đã có allowlist/redaction?
- [ ] Có quy trình xóa/retention và audit?
- [ ] Có runbook xử lý nếu phát hiện token/PII đã được ghi?
- [ ] Có cách báo cáo kết luận bằng metadata mà không đính kèm raw data?

Nếu những điều kiện cốt lõi chưa đáp ứng, **không nên dùng MONITOR trên dữ liệu production nhạy cảm**.

## 47. Câu hỏi tự đánh giá

1. MONITOR cho biết gì về Redis command?
2. Tại sao MONITOR có thể làm Redis chậm dưới workload lớn?
3. MONITOR có cho biết toàn bộ response value của `GET` không?
4. Vì sao lệnh `SET` có rủi ro lộ dữ liệu ngay cả khi không log response?
5. Lệnh `GET` có thể lộ PII theo cách nào?
6. Tại sao không nên đưa token, email vào Redis key name?
7. Redis Cluster hash tag có thể làm lộ định danh nhạy cảm không?
8. TLS Redis có ngăn operator MONITOR xem command arguments không?
9. Một Redis Cluster có thể được quan sát đầy đủ chỉ bằng một MONITOR session trên một node không?
10. Vì sao pipe MONITOR output qua grep không phải cách lọc dữ liệu server-side?
11. `INFO commandstats` có ưu thế gì so với MONITOR khi đo số lệnh GET?
12. `SLOWLOG GET` có thể lộ key names/arguments không?
13. Vì sao SLOWLOG không phản ánh toàn bộ client round-trip latency?
14. `CLIENT LIST` và `ACL LOG` có hoàn toàn không nhạy cảm không?
15. Vì sao `logging.level.root=TRACE` trong production nguy hiểm?
16. Một `toString()` của Java DTO có thể làm lộ token như thế nào?
17. Vì sao metrics tags không nên chứa Redis key hoặc requestId tùy ý?
18. Tại sao sampling 1% không giải quyết hoàn toàn PII leakage?
19. Allowlist logging an toàn hơn blacklist regex ở điểm nào?
20. Vì sao `StringRedisTemplate` service instrumentation có thể thay MONITOR trong nhiều tình huống?
21. Reactor `.log()` có thể làm lộ dữ liệu của `onNext` không?
22. Redis session TTL hết hạn có tự xóa bản sao token trong centralized logs không?
23. Trong multi-tenant Redis, ai có thể xem dữ liệu tenant khác nếu được MONITOR?
24. Làm sao kiểm soát log level runtime và quyền cấp MONITOR?
25. Khi phát hiện secrets trong log, các bước khắc phục chính là gì?
26. Vì sao kết quả `MONITOR` quan sát command không chứng minh command đã được fsync/replicate?
27. Khi điều tra Redis timeout, nên lấy nguồn telemetry nào trước?
28. Nếu Redis `HGETALL` chậm, công cụ nào cho biết server execution time?
29. Một runbook MONITOR khẩn cấp phải có những trường thông tin nào?
30. Làm sao ghi incident report đủ hành động được mà không paste raw payload?

## 48. Ghi nhớ

- **Redis `MONITOR` là công cụ quan sát command ở mức server**, không phải cơ chế mặc định để thu thập log production.
- MONITOR có **overhead CPU/network/output buffers**, đặc biệt với nhiều commands, payload lớn hoặc nhiều monitor clients. Có thể làm thay đổi chính hiệu năng đang đo.
- **Command arguments có thể chứa secret/PII**: không chỉ `SET` values mà cả `HSET`, `XADD`, `PUBLISH`, `EVAL` và **tên key** của cả những lệnh đọc/xóa.
- Một số Redis versions có cơ chế che một số lệnh nhạy cảm, nhưng **không được giả định mọi business payload được redacted tự động**.
- **Một MONITOR connection trên một node Redis Cluster không phải view toàn cluster**; cũng không cho biết response value, HTTP p99 hoặc business completion.
- **Ưu tiên `INFO stats`, `INFO commandstats`, `LATENCY`, Micrometer/Lettuce timing và application tracing**. Dùng `SLOWLOG` có kiểm soát vì nó cũng có thể chứa arguments.
- Trong Spring Data Redis, không log raw Redis key/value, DTO `toString()`, whole exception message hoặc HTTP body chỉ để debug. Cẩn trọng với Lettuce/Netty DEBUG/TRACE và Reactor `.log()`.
- **Logging allowlist** theo `operation`, `command`, `outcome`, `duration` và các low-cardinality tags tốt hơn ghi toàn bộ command rồi cố redact bằng regex.
- **Metrics/tracing cũng cần data minimization**, không dùng userId/email/session token/Redis key làm labels hoặc baggage tùy tiện.
- Nếu cần correlation, dùng traceId kỹ thuật hoặc HMAC/pseudonymous identifier có policy, không coi hash thuần là ẩn danh tuyệt đối.
- **TTL Redis không xóa dữ liệu đã lọt vào logs/traces/backups**. Kiểm soát retention, encryption, RBAC, auditing và đường nhân bản telemetry.
- Quyền MONITOR phải theo **least privilege**, có phê duyệt, thời gian giới hạn, thu hồi và xử lý output an toàn.
- Nếu thực sự cần MONITOR, ưu tiên **lab/staging với dữ liệu giả**. Trên production, đó chỉ nên là ngoại lệ theo runbook và security policy.
- Mục tiêu quan sát tốt là **biết hệ thống đang vận hành ra sao mà không sao chép thông tin người dùng vào một kho dữ liệu mới**.

### Tài liệu tham khảo chính thức

- [Redis — MONITOR](https://redis.io/docs/latest/commands/monitor/)
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — LATENCY](https://redis.io/docs/latest/commands/latency/)
- [Redis — CLIENT LIST](https://redis.io/docs/latest/commands/client-list/)
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/)
- [Redis — ACL GETUSER](https://redis.io/docs/latest/commands/acl-getuser/)
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Reference Documentation](https://docs.micrometer.io/micrometer/reference/)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [OpenTelemetry — Documentation](https://opentelemetry.io/docs/)
