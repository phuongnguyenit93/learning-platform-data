# Kết nối đứt sau khi gửi lệnh và rủi ro ghi trùng trong Spring Data Redis

## 1. Tình huống: lệnh đã chạy hay chưa?

Một ứng dụng Spring Boot dùng `StringRedisTemplate` để tăng bộ đếm số lượt đặt hàng:

```java
Long newValue = redis.opsForValue()
    .increment("orders:submitted");
```

Bình thường, Redis thực hiện `INCR orders:submitted` rồi trả về số mới. Nhưng hãy xét dòng thời gian:

```text
Ứng dụng Spring            Mạng                    Redis
       |                     |                       |
 t0    |--- INCR key ------->|---------------------->|
       |                     |                       |
 t1    |                     |               Redis tăng 100 -> 101
       |                     |                       |
 t2    |                     |<------ response 101 --|
       |            kết nối đứt, response bị mất      |
       |                     X                       |
 t3    |<-- timeout/error ---|                       |
       |                                             |
 t4    |---- retry INCR ---------------------------->|
       |                                     101 -> 102
       |<------------------------------------------ 102
```

Ứng dụng nhận một exception hoặc timeout tại `t3`. Điều đó **không chứng minh Redis chưa thực hiện lệnh**. Nếu ứng dụng retry `INCR` mà không có cơ chế nhận diện yêu cầu cũ, bộ đếm có thể tăng **hai lần** cho một thao tác nghiệp vụ.

Đây là lỗi **kết quả thực thi không xác định** (*ambiguous outcome* hoặc *unknown commit outcome*): client không biết lần đầu đã được áp dụng hay chưa.

Vấn đề xuất hiện không chỉ với `INCR`:

- `LPUSH` hoặc `RPUSH` có thể thêm cùng phần tử hai lần.
- `XADD ... *` có thể tạo hai Redis Stream entries khác ID chứa cùng event.
- `PUBLISH` có thể gửi thông báo hai lần cho những subscriber đang online.
- Một Lua script cập nhật tồn kho có thể bị gọi lại sau timeout.
- Một transaction `EXEC` có thể đã thực thi dù client không nhận response.
- Một request thanh toán có thể bị lặp side effect nếu Redis chỉ giữ cờ kiểm tra ở thời điểm không chắc chắn.

Điểm cốt lõi của bài học:

> **Sau khi lệnh có khả năng đã được gửi, lỗi kết nối/timeout có thể chỉ làm mất phản hồi. Retry mù quáng một lệnh không idempotent có thể gây ghi trùng.**

Trong Spring Data Redis, lựa chọn đúng không chỉ là tăng `timeout` hoặc thêm `@Retryable`. Cần hiểu **ngữ nghĩa lệnh**, **tình trạng thực thi không xác định**, **idempotency**, **tính nguyên tử**, và **mức độ bền vững sau restart/failover**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi xảy ra trước khi gửi, trong khi gửi, sau khi Redis thực thi và sau khi Redis phản hồi.
2. Giải thích tại sao TCP write thành công hay timeout không đủ chứng minh kết quả lệnh.
3. Phân loại các lệnh Redis theo tác dụng phụ khi chạy lại.
4. Hiểu retry/reconnect của Spring Data Redis và Lettuce cần được quản lý theo ngữ nghĩa ứng dụng.
5. Thiết kế request ID, Redis idempotency key và Lua script để chống double increment.
6. Nhận biết giới hạn của `SET NX`, lock, transaction, pipeline, Redis Streams và Pub/Sub.
7. Thiết kế idempotency mạnh hơn cho tác vụ qua Redis và database/HTTP bên ngoài.
8. Hiểu failover, replication lag, RDB/AOF và trường hợp bản ghi chống trùng cũng bị mất.
9. Xây dựng retry policy, logging, metrics và kiểm thử fault injection thực tế.
10. Tránh nhầm “at-least-once delivery” với “exactly-once business effect”.

## 2. Đường đi của một Redis command

Một lệnh Redis qua client thường trải qua nhiều giai đoạn:

```text
Application                       Redis client                  Redis server

1. Tạo command
       |
2. Serialize key / args
       |
3. Queue vào connection
       |
4. Encode RESP + ghi socket -----------> Bytes qua mạng
                                               |
5.                                        Redis nhận đầy đủ command
                                               |
6.                                        Redis thực thi command
                                               |
7.                                        Redis ghi response
       |<------------------------------ Response qua mạng
8. Decode reply
       |
9. Java method / Mono trả kết quả
```

Tùy connector, lệnh có thể được xếp hàng trong lúc connection chưa sẵn sàng, được gửi theo pipeline, hoặc nằm trong một chuỗi lệnh/transaction.

Lỗi ở mỗi điểm có ý nghĩa khác nhau:

| Vị trí sự cố | Điều có thể xảy ra | Client có chắc lệnh được thực thi không? |
|---|---|---|
| Trước khi ứng dụng gọi Redis | Chưa tạo lệnh | Biết chưa có lệnh từ lời gọi ấy |
| Trước khi queue/transport gửi bất kỳ dữ liệu nào, có bằng chứng rõ ràng | Lệnh chưa tới server qua lần gửi đó | Có thể biết trong một số tình huống |
| Đang gửi bytes | Redis có thể chưa nhận đủ hoặc đã nhận đủ | Thường không thể kết luận chỉ từ exception |
| Sau khi Redis nhận, trước khi server thực thi | Lệnh có thể được thực thi hoặc mất theo lỗi server | Không chắc |
| Sau khi Redis đã thực thi, trước khi client nhận reply | Side effect đã xảy ra nhưng reply mất | Không chắc nếu chỉ nhìn client |
| Sau khi client nhận reply thành công | Có kết quả ở mức Redis command | Không mặc nhiên có durability xuyên failover |

Một lỗi mạng chung chung không tiết lộ chính xác giai đoạn nào đã xảy ra. **Không suy rằng exception luôn có nghĩa “chưa chạy”.**

### 2.1. TCP ACK không phải Redis application ACK

Ở mức mạng, việc bytes đã được OS chấp nhận để gửi hoặc có TCP acknowledgment không có nghĩa Redis đã xử lý trọn vẹn command và tạo kết quả nghiệp vụ.

Ngược lại, Redis có thể đã thực hiện lệnh và trả response, nhưng response bị mất ở mạng hoặc bị client bỏ qua do timeout.

Do đó:

```text
socket write completed != Redis command committed
socket timeout         != Redis command not committed
HTTP 500 from service  != Redis command not committed
```

### 2.2. Timeout là giới hạn chờ ở client

Một command timeout thường có nghĩa **client không nhận được kết quả trong khoảng chờ**. Nó không nhất thiết là yêu cầu hủy thực thi trên Redis.

Nếu Redis đã chạy command, việc caller hủy future/reactive subscription hoặc nhận timeout không tự đảo ngược thay đổi.

Ví dụ:

```java
Mono<Long> result = reactiveRedisTemplate
    .opsForValue()
    .increment("orders:submitted")
    .timeout(Duration.ofSeconds(2));
```

Nếu `.timeout(...)` phát lỗi, không được suy rằng `INCR` chắc chắn chưa chạy. Timeout ở Reactor chỉ quản lý kỳ vọng chờ của Publisher, không phải một Redis transaction rollback.

### 2.3. Redis trả OK cũng có giới hạn

Ngay cả khi client nhận một response thành công, kết quả đó không tự bảo đảm:

- Mọi replica đã nhận write.
- AOF đã được fsync theo mức durability mong muốn.
- RDB snapshot mới đã chứa write.
- Một cơ sở dữ liệu khác đã commit cùng write.
- Message Pub/Sub đã được subscriber xử lý nghiệp vụ.
- Khi failover, primary mới chắc chắn giữ write.

Bài học này tập trung vào **ghi trùng do retry**. Nhưng khi chọn cơ chế chống trùng phải xét đồng thời trường hợp **ghi bị mất sau failover**, bởi hai vấn đề thường liên quan.

## 3. Những kết quả có thể xuất hiện sau một timeout

Giả sử lệnh là:

```redis
INCR orders:submitted
```

Một lần gọi nhận timeout có thể tương ứng với một trong các trạng thái:

**Kịch bản A — chưa thực thi:**

```text
Client chưa gửi được command.
Redis không thay đổi counter.
Retry là cần thiết nếu business operation vẫn phải được thực hiện.
```

**Kịch bản B — đã thực thi, response mất:**

```text
Redis tăng counter.
Client không biết kết quả.
Retry trực tiếp INCR sẽ tăng lần thứ hai.
```

**Kịch bản C — đã thực thi, response đến muộn:**

```text
Ứng dụng đã coi request là timeout.
Redis trả response, nhưng future không còn đợi.
Một retry application có thể được khởi động trong lúc command cũ vẫn còn in-flight.
```

**Kịch bản D — đã thực thi trên primary cũ, sau đó failover mất write:**

```text
Primary cũ chấp nhận write.
Write chưa sao chép/bền vững đủ theo kiến trúc.
Primary mới không có kết quả.
```

Ở D, dù client có thể đã nhận OK hoặc không, trạng thái sau failover có thể khác.

Chính vì có nhiều kịch bản, một retry policy tốt thường theo quy tắc:

```text
Đã có request ID ổn định?
    |
    +-- Có --> Thử lại bằng cùng request ID qua cơ chế idempotency.
    |
    +-- Không --> Không tự động retry lệnh ghi không idempotent;
                 xem trạng thái nghiệp vụ hoặc dùng reconciliation.
```

Không nên dựa vào phỏng đoán “lỗi này có vẻ là network” để quyết định tăng bộ đếm thêm lần nữa.

## 4. Idempotency: lệnh chạy lại nhưng không đổi kết quả nghiệp vụ

Một thao tác được gọi là **idempotent** nếu áp dụng cùng thao tác nhiều lần không tạo thêm thay đổi về trạng thái đích so với áp dụng một lần, trong các điều kiện và ranh giới được xác định.

Ví dụ đơn giản:

```redis
SET config:banner "on"
SET config:banner "on"
```

Nếu không có ghi xen kẽ và không xét các metadata/tác động phụ khác, kết quả cuối của key vẫn là `"on"`.

Ngược lại:

```redis
INCR sales:count
INCR sales:count
```

sẽ tăng thêm hai đơn vị. `INCR` **không idempotent**.

### 4.1. Idempotent theo trạng thái cuối không đồng nghĩa reply giống nhau

Ví dụ:

```redis
SADD members user-7
```

Lần đầu có thể trả `1` (thêm mới), lần sau trả `0` (đã tồn tại). Trạng thái tập hợp cuối giống nhau, nhưng reply khác.

Tương tự:

```redis
DEL temp:key
```

Lần đầu có thể trả `1`, lần sau `0`. Xóa lặp thường idempotent theo trạng thái, **không phải theo giá trị trả về**.

Khi client timeout sau lần đầu, thấy `0` ở lần retry không nhất thiết là thao tác trước chưa thành công; có thể nó **đã thành công**.

### 4.2. Idempotent không được xem xét tách rời concurrency

Ví dụ:

```text
Request A: SET order:101:status PAID
Request B: SET order:101:status CANCELLED
Request A timeout và retry SET PAID
```

Dòng thời gian:

```text
t1: A -> PAID
t2: B -> CANCELLED
t3: A retry -> PAID
```

Retry `SET` đã ghi đè trạng thái mới của B. Dù `SET key sameValue` có vẻ idempotent khi chạy độc lập, retry muộn vẫn có thể gây **lost update** khi có thao tác xen kẽ.

Vì vậy, phân biệt:

- **Idempotent operation:** thực hiện cùng yêu cầu lặp lại không tạo tác dụng phụ mới.
- **Concurrency correctness:** retry không được ghi đè thay đổi hợp lệ mới hơn.
- **Durability:** kết quả được giữ qua crash/failover.
- **Exactly-once business effect:** thao tác nghiệp vụ không tạo side effect trùng theo yêu cầu.

Bốn tính chất không tự có chỉ vì lệnh Redis là `SET`.

## 5. Bảng phân loại các lệnh Redis khi retry

| Lệnh | Retry nguyên lệnh có thể gây gì? | Nhận xét |
|---|---|---|
| `GET key` | Đọc lại giá trị khác do writer khác cập nhật | Read-only, không double write |
| `EXISTS key` | Giá trị trả về thay đổi theo thời điểm | Read-only |
| `TTL` / `PTTL` | TTL giảm tự nhiên | Read-only, reply không ổn định |
| `SET key fixedValue` | Có thể ghi đè bản ghi mới hơn | Cần xét concurrency và TTL |
| `SET key value EX 60` | Có thể **gia hạn TTL** ở lần retry | Không idempotent theo deadline |
| `SET key value NX` | Lần retry có thể trả false sau lần đầu thành công | Phải phân biệt owner/request |
| `SET key value XX` | Có thể sửa lại giá trị vừa được thay đổi bởi request khác | Không tự bảo vệ concurrency |
| `DEL key` | Kết quả final thường giống nhau nếu không có recreate | Reply khác; key mới cùng tên có thể bị xóa nhầm |
| `HSET hash field fixedValue` | Có thể ghi đè giá trị mới hơn | Final-state idempotent chỉ trong điều kiện phù hợp |
| `HINCRBY hash field 1` | Tăng hai lần | Không idempotent |
| `INCR` / `INCRBY` | Tăng hai lần | Không idempotent |
| `DECR` / `DECRBY` | Giảm hai lần | Không idempotent |
| `LPUSH` / `RPUSH` | Thêm phần tử hai lần | Không idempotent |
| `LPOP` / `RPOP` | Lấy hai phần tử khác nhau | Retry có thể tiêu thụ thêm work item |
| `SADD set member` | Cùng member thường không bị thêm trùng | Reply khác; cần xét remove xen kẽ |
| `SREM set member` | Xóa lại không đổi nếu chưa có re-add | Cần xét concurrency |
| `ZADD zset score member` | Có thể ghi đè score mới hơn | Cần xét option NX/XX/GT/LT và concurrency |
| `XADD stream * ...` | Tạo thêm entry với Redis Stream ID mới | Dễ ghi event trùng |
| `XACK stream group id` | Lần sau có thể trả `0` | Thường an toàn về xóa PEL, không chứng minh business side effect |
| `PUBLISH channel payload` | Có thể phát thông báo lần nữa | Subscriber có thể nhận trùng |
| `EVAL script ...` | Tùy logic script | Atomic execution không đồng nghĩa idempotent |
| `EXEC` | Transaction có thể chạy lại toàn bộ | Reply mất không biết đã commit hay chưa |
| `RENAME old new` | Lần retry có thể thất bại hoặc đè dữ liệu khác | Không retry mù |

Bảng giúp đặt câu hỏi, không phải quy định “cứ đọc là retry vô hạn” hay “mọi `SET` đều an toàn”. Mỗi ứng dụng cần định nghĩa **ngữ nghĩa nghiệp vụ** của một request.

### 5.1. TTL là side effect dễ bị bỏ sót

Giả sử:

```redis
SET otp:123 "123456" EX 60
```

Lần đầu đã thực thi ở `t0`. Client timeout, retry ở `t0 + 10s`:

```redis
SET otp:123 "123456" EX 60
```

TTL mới bắt đầu lại từ `t0 + 10s`, khiến OTP có thể sống lâu hơn dự kiến 10 giây. Nếu security policy yêu cầu deadline cố định, đây là lỗi logic.

Một hướng xử lý là lưu deadline tuyệt đối hoặc dùng idempotency record chứa deadline của yêu cầu đầu tiên, thay vì mỗi retry tự tạo lại thời hạn từ `now`.

### 5.2. Retry SET NX có thể nhầm thành thất bại

Ví dụ:

```redis
SET payment:claim:evt-1 worker-A NX EX 300
```

Lần đầu thành công, reply mất. Retry trả `nil` vì key đã tồn tại. Nếu ứng dụng diễn giải `nil` là “worker khác đã claim”, nó có thể bỏ dở công việc mà chính mình đang sở hữu.

Phải dùng token/request ID riêng:

```text
payment:claim:evt-1 -> requestId = req-42
```

Sau lỗi, kiểm tra owner hiện tại có đúng request ID của mình không. Nhưng chỉ đọc `GET` và thấy giống nhau **vẫn chưa đủ** bảo đảm side effect bên ngoài đã hoàn tất. Cần trạng thái xử lý `IN_PROGRESS`/`SUCCEEDED` và cơ chế recovery phù hợp.

## 6. Các kiểu lỗi trong Spring Data Redis

Spring Data Redis thường chuyển lỗi của connector thành hệ thống exception thuộc Spring DataAccess API. Tên exception chính xác và mức được wrap phụ thuộc vào lệnh, phiên bản thư viện và connector như Lettuce.

Các nhóm có thể gặp:

```text
RedisConnectionFailureException
QueryTimeoutException hoặc timeout được translate
RedisSystemException
DataAccessException
Lettuce RedisCommandTimeoutException (underlying cause)
Lettuce RedisConnectionException (underlying cause)
```

Không nên viết logic nghiệp vụ dựa vào một string error message cố định như `"Connection closed"` hoặc `"Command timed out"`; các wrapper/message có thể đổi giữa phiên bản.

### 6.1. Exception nào có nghĩa chắc chắn chưa commit?

Trong trường hợp lỗi **được chứng minh phát sinh trước khi tạo/gửi lệnh** (ví dụ validation Java từ chối input trước khi gọi Redis), ứng dụng có thể biết thao tác chưa được gửi.

Nhưng với lỗi **network, timeout hoặc connection reset sau khi attempt bắt đầu**, nên coi kết quả write là **không xác định** nếu không có bằng chứng khác.

Ngay cả khi một connector thông báo “connection was closed”, điều đó không luôn phân biệt:

```text
- Chưa gửi command
- Đã gửi một phần
- Redis đã thực thi nhưng response bị mất
```

Retry policy dựa trên exception type cần kết hợp **loại command** và **một cơ chế idempotency**, không chỉ danh sách “transient exceptions”.

### 6.2. Không catch Exception rồi gọi lệnh lần nữa

Mẫu nguy hiểm:

```java
public Long increment() {
    try {
        return redis.opsForValue().increment("sales:count");
    } catch (Exception ex) {
        return redis.opsForValue().increment("sales:count");
    }
}
```

Nếu lần đầu đã tăng nhưng response bị mất, đoạn code tăng hai lần.

Tăng số lần thử không làm vấn đề biến mất:

```java
for (int attempt = 0; attempt < 5; attempt++) {
    try {
        return redis.opsForValue().increment("sales:count");
    } catch (Exception ignored) {
    }
}
```

Với một sự cố kéo dài, có thể thực hiện cùng business operation nhiều lần.

### 6.3. Backoff giúp giảm tải, không sửa được duplicate

Chờ giữa những lần retry:

```text
100 ms -> 200 ms -> 400 ms -> 800 ms
```

giúp tránh retry storm, giảm áp lực network/Redis sau outage. Nhưng nếu command đầu đã chạy, **đợi 800 ms rồi gọi `INCR` lại vẫn làm nó chạy lần hai**.

Cơ chế backoff và idempotency giải quyết **hai vấn đề khác nhau**:

```text
Backoff       -> bao giờ thử lại?
Idempotency   -> thử lại có tạo thêm tác dụng phụ không?
```

Một retry strategy tốt cần cả hai khi phải thực hiện lại non-idempotent work.

## 7. Lettuce: autoReconnect và những lệnh đang in-flight

Spring Data Redis thường dùng **Lettuce** làm Redis driver. Lettuce có những cơ chế kết nối, auto-reconnect, command queue và completion bất đồng bộ.

Cần phân biệt:

- **Reconnect connection:** cố gắng có kết nối Redis mới sau khi connection cũ hỏng.
- **Retry gửi command:** gửi lại một yêu cầu đã có từ trước.
- **Application retry:** business service gọi lại method sau exception/timeout.
- **Idempotency:** cùng request không được tạo side effect lần hai.

Đây không phải bốn khái niệm đồng nhất.

### 7.1. Tại sao reconnect không bảo đảm exactly-once?

Giả sử một command được gửi trên socket cũ và Redis đã thực thi. Client mất kết nối trước khi reply tới. Sau reconnect, nếu command hoặc lời gọi nghiệp vụ được đưa vào đường gửi lại theo cơ chế client/application, Redis có thể thực thi cùng yêu cầu thêm lần nữa.

Không nên tuyên bố chung rằng “driver chắc chắn luôn gửi lại mọi command” hoặc “driver chắc chắn không bao giờ gửi lại command” khi chưa xem phiên bản/configuration và trạng thái của từng command.

**Kết luận an toàn ở tầng nghiệp vụ:** cả cơ chế retry của driver lẫn retry của application đều không được dùng làm lý do để bỏ qua idempotency đối với mutation không idempotent.

### 7.2. Command queue khi mất kết nối

Một client có thể cho phép một số command chờ để gửi sau khi connection hồi phục, tùy option và loại connection. Điều này có trade-off:

- Tăng khả năng lệnh tiếp tục sau outage ngắn.
- Tăng latency của request.
- Có thể làm request đã timeout ở tầng HTTP nhưng vẫn thực thi muộn.
- Tăng số command chờ và memory nếu outage dài.
- Tạo nguy cơ request cũ ghi đè trạng thái mới khi reconnect.
- Khó phân biệt người dùng đã hủy request với command vẫn còn trong queue.

Không nên mặc định “request HTTP đã timeout” là tất cả command Redis của request ấy đã biến mất khỏi mọi hàng đợi/transport.

### 7.3. Các option cần xem theo phiên bản

Khi đánh giá Lettuce, nhóm vận hành nên biết:

- Chính sách auto reconnect.
- Hành vi command queue khi connection disconnected.
- Command timeout.
- Socket connect timeout.
- Số lượng in-flight requests.
- Cluster topology refresh/redirect handling.
- Retry policy ở tầng service/framework.
- Thư viện có bị bọc bởi Spring Retry, Resilience4j hoặc custom interceptor không.

Không tự tạo cấu hình client “an toàn exactly-once” chỉ bằng cách tăng timeout hoặc tắt reconnect. **Đổi connection behavior có thể giảm một số trường hợp, nhưng không loại trừ tình trạng response mất sau execution.**

## 8. Spring Retry và `@Retryable`: đặt đúng phạm vi

Một service có thể được trang bị retry tự động:

```java
@Retryable(
    maxAttempts = 3
)
public void submitOrder(String orderId) {
    redis.opsForValue().increment("orders:submitted");
}
```

Nếu một attempt đã thực thi `INCR` nhưng method ném exception do response mất, proxy retry có thể gọi lại method và tăng thêm lần nữa.

`@Retryable` không biết:

- Business operation có thực hiện xong không.
- Redis reply có bị mất không.
- Side effect có thể lặp hay không.
- Attempt trước đã ghi event hay gửi email chưa.
- Cần dùng cùng idempotency token nào.

### 8.1. Dùng retry ở tầng đã bảo vệ idempotency

Kiến trúc đúng hơn:

```text
HTTP request có requestId ổn định
     |
     v
Service gọi command idempotent theo requestId
     |
     +-- Thành công --> trả receipt/result
     |
     +-- Network timeout
              |
              +-- Backoff
              +-- Retry cùng requestId
              +-- Lấy lại receipt hoặc thực thi một lần nếu chưa có
```

Spring Retry vẫn có thể hữu ích sau khi lệnh đã có khả năng xử lý duplicate an toàn.

### 8.2. Không sinh requestId mới trong mỗi attempt

Sai:

```java
@Retryable
public Result execute() {
    String requestId = UUID.randomUUID().toString();
    return performOnce(requestId);
}
```

Mỗi lần retry có ID khác nhau; server sẽ coi đó là những yêu cầu độc lập và không thể chống trùng giữa các attempt.

Đúng hơn:

```java
public Result execute(String stableRequestId) {
    return performOnce(stableRequestId);
}
```

Request ID được tạo **trước vùng có thể retry**, hoặc nhận từ client/giao kèo API, rồi được giữ nguyên qua mọi attempt của cùng một business operation.

Nếu caller gọi lại HTTP sau timeout, client cũng cần gửi lại **cùng idempotency key**, không phát sinh một key mới cho mỗi HTTP retry.

## 9. Idempotency key: danh tính của một yêu cầu nghiệp vụ

Một **idempotency key** là token định danh một thao tác logic. Ví dụ:

```text
requestId = 0d50b92d-32aa-4e7e-8d0b-330f7a6bd3af
```

Trong HTTP, client có thể gửi:

```http
POST /api/orders/o-101/reserve
Idempotency-Key: 0d50b92d-32aa-4e7e-8d0b-330f7a6bd3af
Content-Type: application/json

{"sku":"sku-42","quantity":3}
```

Nếu client timeout và gửi lại cùng yêu cầu, nó dùng lại key này.

### 9.1. Một idempotency key phải gắn với cùng payload

Nếu cùng `requestId` được dùng cho hai thao tác khác nhau:

```text
requestId = req-1, reserve quantity = 3
requestId = req-1, reserve quantity = 7
```

và service chỉ trả receipt cũ cho lần thứ hai, client có thể hiểu nhầm quantity 7 đã được áp dụng.

Nên lưu hoặc kiểm tra **request fingerprint** cùng idempotency key:

```text
requestId
operationName
tenantId
resourceId
canonicalPayloadHash
result/status
createdAt
expiresAt
```

Khi một key được tái sử dụng với payload khác, trả lỗi xung đột, không áp dụng lần thứ hai.

### 9.2. Phạm vi uniqueness cần rõ

Một request ID có thể cần unique trong:

```text
tenant + operation + requestId
```

Ví dụ:

```text
tenant=t-7
operation=reserve-stock
requestId=req-123
```

Nếu chỉ dùng `requestId` mà các tenant được phép sử dụng cùng giá trị, có thể xảy ra cross-tenant collision. Nếu dùng chung receipt namespace nhưng không kiểm tra operation, một request ở API này có thể vô tình ảnh hưởng API khác.

Định nghĩa scope từ đầu giúp tránh lỗi khi hệ thống mở rộng.

### 9.3. Request ID không thay thế business invariant

Có thể cùng một business order được submit bằng **hai request IDs khác nhau** do lỗi client hoặc hai process khác. Idempotency theo request ID chỉ chống **lặp cùng một yêu cầu**, không tự chống hai yêu cầu độc lập cùng cố gắng thực hiện một thay đổi không hợp lệ.

Vẫn cần kiểm tra trạng thái như:

```text
Order chỉ được PAID một lần.
Reservation chỉ được chuyển CONFIRMED khi còn PENDING.
Một payment provider charge ID không được ghi hai lần.
```

Đó là lý do idempotency thường đi cùng compare-and-set, unique constraints, versioning hoặc state machine.

## 10. Vì sao chỉ dùng `SET NX` rồi thực thi việc khác vẫn có lỗ hổng?

Một phương án ban đầu:

```redis
SET dedupe:req-123 "processing" NX EX 3600
```

Sau đó Java thực hiện:

```redis
INCR inventory:reserved
```

Vấn đề là hai bước độc lập.

**Trường hợp 1 — ghi guard thành công, nhưng chưa thực hiện nghiệp vụ:**

```text
t1: SET dedupe:req-123 processing NX EX 3600 -> OK
t2: Process crash trước INCR
t3: Retry thấy dedupe key, bỏ qua
```

Business operation không xảy ra, nhưng hệ thống tưởng đã xử lý.

**Trường hợp 2 — thực hiện nghiệp vụ trước guard:**

```text
t1: INCR inventory:reserved -> thành công
t2: Process crash trước SET dedupe
t3: Retry không thấy guard
t4: INCR thêm lần nữa
```

Business operation xảy ra hai lần.

Kết luận:

> **Một guard riêng lẻ ở Redis không bảo đảm exactly-once nếu nó không được cập nhật nguyên tử cùng side effect cần bảo vệ.**

`SET NX` hữu ích cho claim/lock khi có lifecycle phù hợp, nhưng không tự là một transaction băng qua các command hoặc băng qua Redis và database bên ngoài.

### 10.1. TTL của guard là trade-off

Nếu guard có TTL 1 giờ:

- Retry trong vòng 1 giờ có thể được nhận diện.
- Retry sau 1 giờ có thể tạo tác dụng phụ lại.
- Nếu guard chỉ ghi `PROCESSING` nhưng worker crash, một giờ có thể là thời gian bị kẹt.
- Nếu Redis eviction loại guard trước hạn, việc chống trùng có thể mất hiệu lực sớm.
- Nếu Redis restore snapshot cũ, guard và state có thể rollback.

TTL phải xuất phát từ **retry horizon và nghĩa vụ lưu receipt của nghiệp vụ**, không chỉ từ một hằng số tùy tiện.

## 11. Chống double increment bằng một Lua script

Khi side effect và idempotency receipt đều nằm trong **cùng Redis instance/hash slot**, có thể gộp kiểm tra request ID, mutation và lưu kết quả trong một Lua script.

Ví dụ: tăng một counter **tối đa một lần cho mỗi request ID**, ngay cả khi client timeout rồi retry.

Chọn hai key:

```text
Counter:
    counter:{sku-42}:reserved

Receipt của request:
    counter:{sku-42}:request:req-123
```

Hai key cùng hash tag `{sku-42}`, quan trọng trên Redis Cluster.

Script lưu tại `src/main/resources/lua/increment-once.lua`:

```lua
-- KEYS[1] = counter key
-- KEYS[2] = receipt key cua request
-- ARGV[1] = increment amount, positive integer string
-- ARGV[2] = receipt TTL milliseconds, positive integer string

if #KEYS ~= 2 or #ARGV ~= 2 then
    return redis.error_reply('INVALID_ARGUMENT_COUNT')
end

local amount = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])

if not amount or amount <= 0 or amount % 1 ~= 0 then
    return redis.error_reply('INVALID_INCREMENT')
end

if not ttl or ttl <= 0 or ttl % 1 ~= 0 then
    return redis.error_reply('INVALID_RECEIPT_TTL')
end

local existingResult = redis.call('GET', KEYS[2])

if existingResult then
    return tonumber(existingResult)
end

local updated = redis.call(
    'INCRBY',
    KEYS[1],
    amount
)

redis.call(
    'PSETEX',
    KEYS[2],
    ttl,
    tostring(updated)
)

return updated
```

### 11.1. Mô hình khi command đầu thành công nhưng reply bị mất

```text
Attempt 1: EVAL script, request req-123
    |
    +--> receipt chưa có
    +--> INCRBY counter 3
    +--> PSETEX receipt:req-123 -> result 103
    +--> Redis trả 103
    +--> mạng mất reply

Attempt 2: EVAL script, vẫn request req-123
    |
    +--> receipt đã có (103)
    +--> return 103
    +--> KHÔNG INCRBY lần hai
```

Vì các command trong Lua script được thực thi không bị lệnh Redis khác xen vào, hai caller gửi cùng request ID không thể cùng đi qua nhánh “receipt chưa có” theo cùng trạng thái live Redis.

**Lưu ý:** Redis Lua script là atomic về khả năng không bị các command khác xen vào, **không có rollback tự động nếu script gặp runtime error sau khi đã ghi**. Do đó, trong production nên validate mọi input, data types, overflow và điều kiện fail trước khi thực hiện các ghi; cân nhắc dùng status/receipt trả về hợp đồng rõ ràng.

### 11.2. Ví dụ service Spring Data Redis

Cấu hình script:

```java
package com.example.counter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class IdempotentCounterScriptConfig {

    @Bean
    RedisScript<Long> incrementOnceScript() {
        return RedisScript.of(
            new ClassPathResource("lua/increment-once.lua"),
            Long.class
        );
    }
}
```

Service:

```java
package com.example.counter;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class ReservationCounterService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> incrementOnceScript;

    public ReservationCounterService(
            StringRedisTemplate redis,
            RedisScript<Long> incrementOnceScript) {

        this.redis = redis;
        this.incrementOnceScript = incrementOnceScript;
    }

    public long reserveOnce(
            String sku,
            String requestId,
            long amount) {

        if (amount <= 0) {
            throw new IllegalArgumentException(
                "amount must be positive"
            );
        }

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                "requestId is required"
            );
        }

        // Trong production: encode/validate sku, requestId
        // để không chen ky tu {} lam sai hash tag.
        String tag = "{" + sku + "}";
        String counterKey = "counter:" + tag + ":reserved";
        String receiptKey =
            "counter:" + tag + ":request:" + requestId;

        long receiptTtlMs =
            Duration.ofDays(1).toMillis();

        Long result = redis.execute(
            incrementOnceScript,
            List.of(counterKey, receiptKey),
            Long.toString(amount),
            Long.toString(receiptTtlMs)
        );

        if (result == null) {
            throw new IllegalStateException(
                "Redis script returned no result"
            );
        }

        return result;
    }
}
```

Các quyết định quan trọng:

- **Cùng requestId** được truyền lại khi retry.
- `counterKey` và `receiptKey` có **cùng hash tag**.
- Dùng `StringRedisTemplate` để key/ARGV có format chuỗi mà Lua hiểu.
- `RedisScript<Long>` map Redis integer reply sang `Long`.
- Receipt lưu **kết quả lần thực thi đầu**, để lần retry trả lại giá trị tương tự.
- TTL receipt có nghĩa giới hạn lịch sử chống trùng, không phải TTL counter.
- Đoạn mã dùng `sku` và `requestId` minh họa; production phải chuẩn hóa/escape để không để ký tự `{}` phá vỡ hash tag hoặc đụng namespace.

### 11.3. Cần gắn request ID với payload không đổi

Script đơn giản phía trên dùng key receipt để nhận diện request, nhưng **không so sánh amount mới với amount cũ**. Nếu caller dùng lại request ID với lượng tăng khác, script sẽ trả receipt cũ và bỏ qua thay đổi.

Với API công khai, phải mở rộng receipt để lưu fingerprint:

```text
receipt:req-123:
  requestHash = SHA256(canonicalPayload)
  status      = SUCCEEDED
  result      = 103
```

Khi retry:

- Hash trùng: trả receipt.
- Hash khác: trả lỗi idempotency-key reuse.
- Receipt thiếu: thực hiện theo quy trình.
- Receipt ở trạng thái `PROCESSING`: xử lý theo lease/recovery chính sách.

Có thể lưu receipt dạng Hash và điều khiển atomically trong Lua, hoặc dùng một hệ thống idempotency có transaction phù hợp.

### 11.4. Validate loại dữ liệu trước khi ghi

Ví dụ nếu `counterKey` chứa String không phải số, `INCRBY` sẽ lỗi trước khi lưu receipt. Nếu `INCRBY` thành công nhưng việc ghi receipt thất bại (ví dụ out-of-memory/command runtime error), script có thể đã tạo side effect mà không có receipt.

Vì vậy, mẫu Lua được dùng để giải thích **nguyên tắc atomic deduplication khi các bước thực thi thành công**; không được coi nó là một bảo đảm exactly-once tuyệt đối dưới mọi lỗi Redis/storage/command.

Một thiết kế nghiêm ngặt hơn cần validate types, giới hạn số nguyên, write policy, OOM, `noeviction`, receipt retention và khôi phục sau failover.

### 11.5. Vẫn có giới hạn durability

Giả sử attempt 1 đã `INCRBY` và tạo receipt, rồi primary crash trước khi dữ liệu được giữ bền vững hoặc replicate tới primary mới. Tùy persistence/failover, counter và receipt có thể cùng biến mất.

Nếu một hệ thống bên ngoài đã dựa vào kết quả 103, lần retry có thể lại thực hiện một mutation trên state mới; tính nhất quán end-to-end không tự được bảo đảm chỉ bằng Lua.

Lua giải quyết **race trong Redis live trên cùng slot**. Nó không giải quyết mọi tình huống mất dữ liệu do RDB/AOF/failover, và không tạo transaction chung với database ngoài Redis.

## 12. Cách xử lý `SET NX` với request token

Đối với một tác vụ chỉ cần claim tạm thời, có thể dùng:

```redis
SET processing:{job-101} req-123 NX PX 30000
```

Phản hồi:

- `OK`: key chưa tồn tại, claim được tạo.
- `nil`: key đã tồn tại, claim không được tạo.

Nhưng nếu reply `OK` mất, lần retry có thể nhận `nil`. Ứng dụng cần đọc owner:

```redis
GET processing:{job-101}
```

Nếu giá trị là `req-123`, có thể đó là claim do chính request trước tạo. Nếu là token khác, một claimant khác đang sở hữu.

### 12.1. Đừng chỉ so sánh token rồi tự ý chạy side effect

Ngay cả khi key đang chứa token của mình, có hai trường hợp:

```text
- Request trước mới claim, chưa xử lý gì.
- Request trước đã xử lý một phần/hoàn tất, nhưng chưa đánh dấu SUCCEEDED.
```

Do vậy, với business task nghiêm trọng, cần trạng thái:

```text
NEW -> PROCESSING -> SUCCEEDED
                   -> FAILED_RETRYABLE
                   -> FAILED_FINAL
```

và có thể cần:

- Lưu result/receipt.
- Lease ownership/expiry.
- Heartbeat hoặc requeue.
- Retry sau timeout theo cùng request ID.
- Kiểm tra nghiệp vụ khi trạng thái `PROCESSING` bị bỏ dở.
- Bảo đảm không side effect trùng khi worker cũ vẫn đang chạy.

Lock không thay thế idempotency record.

### 12.2. Xóa lock bằng token

Không làm:

```redis
DEL processing:{job-101}
```

trong `finally` mà không kiểm tra owner. Lock có thể đã hết TTL và được process khác claim lại. Lệnh `DEL` trễ của process cũ sẽ xóa lock mới.

Cần compare-and-delete atomically, ví dụ Lua:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end

return 0
```

Đây là kiến thức an toàn lock liên quan trực tiếp tới retry sau mất kết nối. Nó vẫn chưa làm cho tác vụ bên ngoài Redis có exactly-once effect.

## 13. Một lệnh SET với request ID và trạng thái nghiệp vụ

Một hướng tốt hơn việc “SET rồi retry nguyên SET” là biến thao tác thành **chuyển trạng thái có điều kiện**.

Ví dụ:

```text
Order o-101:
    PENDING -> PAID
```

Nếu HTTP request `markPaid` timeout, lần retry không được tự động ghi trạng thái `PAID` nếu order đã được một flow khác chuyển sang `CANCELLED`.

Một state transition cần xem cả:

```text
current status
expected status
new status
request ID
version
result/receipt
```

Có thể triển khai bằng Lua trên các key cùng slot, hoặc bằng một Redis Hash với các field liên quan. Sơ đồ:

```text
Lua:
  receipt đã tồn tại?
      |
      +-- Có -> trả result cũ nếu payload hash khớp
      |
      +-- Không:
            status hiện tại có expected không?
                |
                +-- Không -> trả lỗi trạng thái hợp lệ
                |
                +-- Có:
                     set nextStatus
                     record receipt
                     return success
```

Nhờ đó, retry cùng request nhận lại kết quả đã ghi và không overwrite state mới một cách mù quáng.

### 13.1. Idempotent transition khác blind SET

Nếu chỉ dùng:

```redis
SET order:101:status PAID
```

thì retry trễ có thể ghi đè các transition mới hơn.

Nếu dùng atomic check:

```text
PENDING -> PAID nếu current == PENDING
```

lần retry thấy `PAID` cần phân biệt:

- Chính request này đã làm nó thành `PAID`.
- Một request khác đã làm nó thành `PAID`.
- Có conflict/new version cần xử lý.

Vì vậy, **request ID/result receipt** vẫn có giá trị ngay cả khi transition đã có `expectedState`.

## 14. Vấn đề khi retry Redis Streams XADD

Một producer ghi event:

```redis
XADD orders:events * eventId evt-1001 type CREATED orderId o-101
```

Redis cấp ID mới, ví dụ:

```text
1763000000123-0
```

Nếu Redis đã ghi entry nhưng reply mang ID bị mất, producer có thể retry:

```redis
XADD orders:events * eventId evt-1001 type CREATED orderId o-101
```

Redis cấp một ID **khác**:

```text
1763000000200-0
```

Stream có hai entry:

```text
ID1 -> eventId evt-1001
ID2 -> eventId evt-1001
```

Đây là **hai Redis records**, dù cùng một business event.

### 14.1. Redis Stream ID và business eventId khác nhau

- **Stream ID** là ID của entry trong log Redis.
- **Business eventId** nhận diện thao tác nghiệp vụ cần thực hiện một lần.

Cùng một eventId có thể xuất hiện trong nhiều Stream entries nếu producer retry `XADD *` sau ambiguous outcome.

Do đó, consumer cần idempotency theo **eventId** nếu xử lý side effect quan trọng, không chỉ theo Stream ID.

### 14.2. Có nên tự gán Stream ID cố định để chống trùng?

Redis `XADD` cho phép chỉ định ID theo ngữ nghĩa Stream, nhưng ID chịu quy tắc tăng đơn điệu và không được tùy tiện dùng như một idempotency key chung.

Nếu retry với cùng ID đã có, Redis có thể báo lỗi về ID không lớn hơn ID mới nhất. Nếu entry đã bị trim hoặc có những write xen kẽ, việc diễn giải lỗi cũng không đơn giản như “event của tôi đã được ghi”.

Vì vậy, dùng một Redis Stream ID tự chọn **không thay thế** thiết kế requestId/business eventId, dedupe receipt và reconciliation.

### 14.3. Producer idempotent XADD với cùng slot

Có thể dùng Lua, trong đó:

```text
KEYS[1] = orders:{partition-7}:events   (Stream)
KEYS[2] = orders:{partition-7}:receipt:evt-1001
```

Pseudo logic:

```text
Nếu receipt đã có:
    trả lại Stream ID đã lưu.

Nếu receipt chưa có:
    XADD vào Stream.
    Lưu Stream ID vào receipt.
    Trả Stream ID.
```

Hai key phải cùng hash slot nếu chạy script trong Redis Cluster. Cần thiết kế TTL/retention phù hợp và nhớ rằng script runtime errors, eviction và persistence rollback vẫn là những rủi ro khác.

### 14.4. Producer ghi DB và XADD không tự atomic

Nếu một request:

```text
1. COMMIT order vào PostgreSQL.
2. XADD OrderCreated vào Redis Streams.
```

mất connection sau bước 2, client không biết event đã được ghi chưa. Retry `XADD` có thể tạo trùng. Không retry có thể bỏ sót nếu lần đầu chưa chạy.

**Transactional outbox** thường phù hợp khi event bắt buộc phản ánh một commit database:

```text
Trong một SQL transaction:
    INSERT/UPDATE order
    INSERT outbox_event(eventId, payload)

Worker:
    đọc outbox
    XADD vào Redis Stream
    đánh dấu published (có thể retry)
```

Ngay cả với outbox, một event có thể được publish hai lần nếu publish thành công nhưng đánh dấu `published` thất bại. Vì vậy, consumer hoặc producer vẫn cần idempotency theo eventId.

## 15. Consumer group: đọc xong nhưng response XREADGROUP bị mất

Một trường hợp ít được chú ý:

```text
worker-A gọi XREADGROUP GROUP g worker-A STREAMS stream >
Redis chọn entry E, đưa E vào PEL của group.
Redis gửi reply có E.
Kết nối đứt trước khi worker nhận payload.
```

Redis đã đánh dấu E là **pending** thuộc `worker-A`, nhưng ứng dụng chưa từng xử lý payload.

Khi worker nối lại và chỉ tiếp tục:

```redis
XREADGROUP GROUP g worker-A STREAMS stream >
```

ký hiệu `>` đọc **entry mới**, nên E có thể không tự được phát lại trong luồng ấy.

### 15.1. PEL giúp phục hồi

Cần theo dõi:

```redis
XPENDING stream g
XPENDING stream g - + 10
```

Và xử lý:

- Đọc pending history của **cùng consumer name** bằng `XREADGROUP ... 0`.
- Claim pending idle lâu của consumer khác qua `XCLAIM` hoặc `XAUTOCLAIM`.
- Chỉ `XACK` khi xử lý theo chính sách đã hoàn tất.
- Với payload lỗi, dùng retry/DLQ và không bỏ qua PEL.

Như vậy, network failure sau `XREADGROUP` có thể gây **message bị pending dù application chưa từng nhìn thấy nó**, không chỉ double process.

### 15.2. XACK timeout và ACK lặp

Sau khi xử lý thành công:

```redis
XACK stream g 1763000000123-0
```

Nếu reply mất, worker không biết pending ID đã bị loại chưa.

Gọi `XACK` lần nữa với cùng ID thường không gây side effect nghiệp vụ mới: có thể trả `0` vì đã ACK trước đó. Nhưng **nếu handler chạy lại business operation trước khi gọi XACK**, tác dụng phụ có thể bị lặp.

Quy tắc:

```text
Retry ACK theo cùng Stream ID
    khác với
Retry toàn bộ business handler + ACK
```

Với business handler idempotent theo eventId, redelivery vẫn có thể được xử lý an toàn.

## 16. Pub/Sub: retry PUBLISH gây gửi thông báo trùng

Giả sử:

```redis
PUBLISH notifications.order '{"eventId":"evt-42","status":"PAID"}'
```

Redis phát thông điệp tới các subscriber đang đăng ký, nhưng connection của publisher mất trước khi nhận số subscriber trả về.

Nếu publisher retry:

```redis
PUBLISH notifications.order '{"eventId":"evt-42","status":"PAID"}'
```

những subscriber còn online có thể nhận **hai thông báo** cho cùng business event.

Không có cơ chế xác nhận processing hoặc backlog trong Redis Pub/Sub thông thường. Vì vậy:

- Không dùng `PUBLISH` return count làm ACK nghiệp vụ.
- Không coi retry PUBLISH là bảo đảm exactly-once.
- Consumer có thể bỏ duplicate nhờ eventId nếu cần.
- Nếu event cần xử lý chắc chắn, cân nhắc Redis Streams hoặc message broker có durability và consumer recovery.
- UI realtime có thể chỉ refresh state hiện tại, tránh dùng mỗi Pub/Sub message để thực hiện một side effect không thể đảo ngược.

### 16.1. Consumer dedupe chỉ có hiệu lực trong giới hạn lưu state

Nếu browser dùng Set trong bộ nhớ để bỏ eventId trùng, việc refresh trang làm mất Set. Nếu cần chống trùng xuyên restart, phải dùng nơi lưu receipt đủ bền vững với retention phù hợp.

Không phải mọi notification đều cần dedupe mạnh; đôi khi “cập nhật trạng thái mới nhất” là thiết kế tốt hơn “cộng một lần cho mỗi notification”.

## 17. MULTI/EXEC và response bị mất

Redis transaction dùng:

```redis
MULTI
INCR orders:count
LPUSH orders:recent o-101
EXEC
```

Nếu Redis đã thực thi `EXEC` nhưng response bị mất, client không thể chỉ nhìn timeout để biết transaction đã chạy hay chưa.

Gọi lại toàn bộ:

```redis
MULTI
INCR orders:count
LPUSH orders:recent o-101
EXEC
```

có thể tăng count và thêm item lần nữa.

**Atomicity của transaction** chỉ bảo đảm các command bên trong được xử lý theo ngữ nghĩa transaction Redis, **không làm transaction idempotent đối với replay**.

### 17.1. Redis transaction không có request ID built-in

Nếu cần chống replay, phải tổ chức transaction hoặc Lua script để kiểm tra một receipt/request ID được lưu trong cùng phạm vi atomicity.

Trong Redis Cluster, các key liên quan phải tuân theo ràng buộc same-slot cho transaction/script nhiều key.

### 17.2. Runtime error cũng cần phân biệt

Redis `MULTI/EXEC` không có rollback SQL-style cho mọi lỗi phát sinh trong khi thực thi từng command. Một số command đã chạy thành công có thể giữ tác dụng phụ ngay cả khi command khác báo lỗi trong transaction.

Idempotency cũng cần được thiết kế cho trường hợp **partial business effect do lỗi command**, không chỉ mất kết nối.

## 18. Pipeline và batch: nhiều lệnh có thể ở trạng thái không xác định

Pipeline gửi nhiều command với mục tiêu giảm network round trips:

```text
SET key:A valueA
INCR count:B
LPUSH queue:C itemC
```

Nếu connection đứt sau khi Redis xử lý một số command, client có thể không nhận đủ replies và không biết command nào đã chạy.

Pipeline không biến toàn bộ batch thành một transaction và không tự bảo đảm all-or-nothing.

### 18.1. Một timeout không cho phép retry nguyên batch

Giả sử:

```text
Command 1 SET key:A -> đã chạy
Command 2 INCR count:B -> đã chạy
Command 3 LPUSH queue:C -> chưa chạy
Connection đứt.
```

Nếu retry nguyên batch:

```text
SET key:A lại
INCR count:B lại
LPUSH queue:C lần đầu
```

`count:B` bị tăng trùng.

Những command trong một pipeline cần được xem xét độc lập theo ID/kết quả và thiết kế sao cho batch có thể được replay an toàn, hoặc sử dụng transaction/script trong một phạm vi atomic phù hợp.

### 18.2. Batch ACK không đồng nghĩa business commit

Dù `executePipelined` trả một danh sách kết quả, ứng dụng cần hiểu từng entry phản ánh command nào và các lệnh có phụ thuộc nhau không. Không suy rằng một loạt Redis commands atomic chỉ vì chúng cùng được thực thi trong một method Java.

## 19. Redis Cluster và failover: ghi có thể mất hoặc bị lặp

Redis Cluster phân tán key theo hash slot và thường dùng asynchronous replication giữa primary và replica. Các tình huống kết nối đứt có thể liên quan đến:

- Redis client gửi tới node không còn sở hữu slot.
- Redirect `MOVED`/`ASK`.
- Primary restart/failover.
- Replica được promote nhưng chưa kịp nhận write.
- Network partition giữa application và node.
- Retry từ client khi topology thay đổi.

### 19.1. Lệnh đã chạy trên primary cũ nhưng primary mới không có

Ví dụ:

```text
t1: Primary A xử lý INCR count -> 101.
t2: Response bị mất.
t3: A chết trước khi replica R nhận write.
t4: R được promote, counter vẫn 100.
t5: Application retry INCR -> 101.
```

Ở đây application retry có thể đưa counter về 101 chứ không phải 102. Nhưng không được lấy ví dụ này để kết luận “retry luôn an toàn sau failover” vì còn các tình huống write trước được replica nhận, hoặc response cũ đến muộn và lệnh bị gửi lại.

Điểm trọng tâm là **kết quả không xác định phụ thuộc vào trạng thái Redis thực tế sau failover**, không chỉ exception.

### 19.2. Receipt chống trùng cũng có thể rollback

Nếu receipt và mutation cùng nằm trong Redis:

```text
counter:{sku-42}:reserved
counter:{sku-42}:request:req-123
```

một Lua script có thể cập nhật cả hai atomically khi primary còn sống. Nhưng nếu cả hai chưa được ghi bền vững/replicate trước khi failover, primary mới có thể không thấy receipt.

Ở trường hợp này, lần retry có thể thực thi lại side effect trên dữ liệu đang được khôi phục. Hệ thống bên ngoài từng nhìn thấy kết quả cũ vẫn có thể cần reconciliation.

Nếu require strict financial semantics, phải có **source-of-truth durability** phù hợp và idempotency lưu bền vững, không dựa duy nhất vào Redis volatile state.

### 19.3. Same-slot là điều kiện cần cho Lua nhiều key

Ví dụ:

```text
inventory:{sku-42}:available
inventory:{sku-42}:receipt:req-123
```

Hai key cùng hash tag `{sku-42}`, nên có thể dùng trong một Redis Cluster script theo điều kiện same-slot.

Nếu receipt key lại là:

```text
idempotency:req-123
```

nó có thể nằm slot khác, khiến script gặp `CROSSSLOT` hoặc bị từ chối theo ràng buộc Cluster.

Đừng sửa vấn đề bằng cách gom **mọi receipt toàn hệ thống** vào một hash tag `{global}`. Điều đó dễ tạo hot slot; nên đặt receipt theo aggregate/partition có nghiệp vụ liên quan.

### 19.4. WAIT và WAITAOF không tự tạo exactly-once

Redis có thể hỗ trợ:

```redis
WAIT ...
WAITAOF ...
```

tùy phiên bản và cấu hình, để chờ mức độ replication/persistence nào đó. Các lệnh này có thể cải thiện hiểu biết về durability trong phạm vi hỗ trợ, nhưng:

- Không phải transaction phân tán giữa Redis và database ngoài.
- Không làm `INCR` tự idempotent khi retry.
- Không loại bỏ mọi nguy cơ failover/partition.
- Phải hiểu connection/session ordering của write và lệnh WAIT/WAITAOF.
- Chỉ phản ánh contract cụ thể của version/deployment.

Chọn persistence, replication, fencing và idempotency vẫn là quyết định kiến trúc riêng.

## 20. RDB/AOF và khả năng ghi trùng sau restore

Giả sử application đã nhận kết quả từ Redis, nhưng server dùng RDB snapshots định kỳ. Redis crash và khôi phục từ snapshot cũ hơn:

```text
10:00 snapshot: counter = 100
10:02 INCR counter -> 101, client có hoặc không có reply
10:03 Redis crash, khôi phục snapshot counter = 100
```

Lần retry cùng request có thể tăng counter từ 100 lên 101 một lần nữa.

Nếu kết quả ban đầu đã được hệ thống ngoài Redis ghi nhận, chúng ta có một vấn đề đối chiếu end-to-end. Redis state tại primary mới không nhớ rằng request từng xảy ra.

AOF với chính sách fsync phù hợp có thể giảm cửa sổ mất dữ liệu, nhưng không tự biến lệnh ghi thành exactly-once across all failures. Nếu Redis là cache có thể rebuild, thường chấp nhận trạng thái rollback từ nguồn bền vững. Nếu là nguồn duy nhất của business effect, cần đánh giá lại dữ liệu và SLA.

### 20.1. Cùng một yêu cầu có thể vừa mất vừa trùng theo các hệ thống khác nhau

Ví dụ:

```text
t1: Redis INCR stock:reserved -> 101.
t2: HTTP response ghi kết quả 101 vào database.
t3: Redis crash, phục hồi counter về 100.
t4: Caller retry yêu cầu.
t5: Redis INCR stock:reserved -> 101.
```

Từ góc nhìn Redis hiện tại, counter đã tăng một lần. Từ góc nhìn database nghiệp vụ, event có thể đã được ghi nhận hai lần ở các bước khác nhau.

Đây là lý do cần xác định **hệ thống nào là source of truth**, receipt ở đâu và transaction boundary ở đâu.

## 21. Chống side effect trùng khi có database bên ngoài

Nếu một tác vụ ghi vào PostgreSQL/MySQL và Redis, không thể dùng một Lua script để tạo transaction nguyên tử cho cả hai.

Mẫu:

```text
HTTP request
    |
    +--> Redis SET dedupe:request
    |
    +--> SQL INSERT/UPDATE
```

có lỗ hổng nếu crash giữa hai bước.

### 21.1. Unique constraint theo eventId trong SQL transaction

Ví dụ bảng:

```sql
CREATE TABLE processed_requests (
    request_id VARCHAR(100) PRIMARY KEY,
    payload_hash VARCHAR(128) NOT NULL,
    result_code VARCHAR(40) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

Trong **cùng database transaction** với business update:

```text
BEGIN
    INSERT processed_requests(requestId, payloadHash, ...)
    nếu conflict:
        xác minh cùng payload, đọc kết quả đã lưu
        không áp dụng business update lần hai
    nếu insert mới:
        cập nhật bảng nghiệp vụ
COMMIT
```

Nếu Redis/HTTP response mất sau SQL commit, lần retry gặp unique constraint và đọc receipt/result cũ, không thực hiện side effect hai lần.

Chi tiết SQL như `INSERT ... ON CONFLICT` hay `INSERT IGNORE` phụ thuộc database. Cần thiết kế transaction isolation và xử lý race cho các request đồng thời.

### 21.2. Tại sao Redis cache của idempotency record chưa đủ?

Có thể cache receipt trong Redis để trả kết quả nhanh, nhưng nếu authoritative receipt nằm trong SQL, cache miss hoặc Redis failover không được phép đồng nghĩa “request chưa từng chạy”.

Luồng:

```text
Check Redis receipt
    |
    +--> Found: có thể trả nhanh nếu receipt hợp lệ
    |
    +--> Missing: tra authoritative SQL receipt
          |
          +--> Found: repopulate cache, trả kết quả
          |
          +--> Not found: tạo/áp dụng nghiệp vụ trong SQL transaction
```

Redis hoạt động như tầng tăng tốc; **quyết định duy nhất** phải dựa trên nơi lưu receipt có durability và atomicity tương ứng với business data.

### 21.3. External side effect vẫn cần hợp đồng riêng

Gửi email, gọi payment gateway, xuất hóa đơn qua API ngoài DB không nằm trong transaction SQL của ứng dụng.

Phương án:

- Transactional outbox cho yêu cầu gửi ra ngoài.
- Idempotency key được provider hỗ trợ.
- Lưu request/response receipt và trạng thái gửi.
- Reconciliation/compensation khi timeout với outcome không xác định.
- Không tạo request ID mới khi retry cùng thao tác.

Ví dụ charge payment:

```text
requestId = charge-evt-1001

Attempt 1:
  paymentProvider.charge(idempotencyKey=charge-evt-1001)
  -> provider xử lý nhưng response timeout

Attempt 2:
  paymentProvider.charge(idempotencyKey=charge-evt-1001)
  -> provider trả kết quả cũ
```

Điều này chỉ đúng nếu provider **thực sự có contract idempotency** với retention/scope được hiểu rõ. Nếu provider không hỗ trợ, phải dùng lookup/reconciliation trước khi thử charge lần nữa.

## 22. Tạo một HTTP API có idempotency rõ ràng

Ví dụ controller nhận request ID:

```java
package com.example.inventory;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final ReservationCounterService reservations;

    public InventoryController(
            ReservationCounterService reservations) {
        this.reservations = reservations;
    }

    @PostMapping("/{sku}/reserve")
    public ReserveResponse reserve(
            @PathVariable String sku,
            @RequestHeader("Idempotency-Key") String requestId) {

        if (requestId.isBlank() || requestId.length() > 128) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid idempotency key"
            );
        }

        long totalReserved =
            reservations.reserveOnce(sku, requestId, 1L);

        return new ReserveResponse(
            sku,
            requestId,
            totalReserved
        );
    }

    public record ReserveResponse(
        String sku,
        String requestId,
        long totalReserved
    ) {}
}
```

Ví dụ chỉ minh họa đường API nối requestId tới Redis script ở phần 11. Trong production cần:

- Xác thực/ủy quyền và scope requestId theo tenant.
- Validate SKU để không phá cấu trúc Redis keys.
- Request fingerprint cho body/query.
- Phân biệt Redis timeout với business conflict.
- Chính sách result receipt TTL.
- Business invariant về available stock, không chỉ tăng `reserved`.
- Giới hạn throughput/abuse.
- Cơ chế receipt durability phù hợp yêu cầu.

Không nên tạo `UUID.randomUUID()` trong controller để thay thế header của **một retry từ client** nếu client cần giữ nguyên token qua các HTTP attempts. Server có thể cấp token từ một bước khởi tạo riêng nếu contract API được thiết kế như vậy.

### 22.1. Response HTTP khi outcome chưa rõ

Nếu Redis write timeout sau khi có thể đã thực thi, trả một lỗi “chưa thực hiện” là thông tin sai.

Tùy nghiệp vụ, có thể:

- Trả mã lỗi tạm thời và yêu cầu client retry **cùng idempotency key**.
- Trả trạng thái `PROCESSING`/`UNKNOWN` với operation ID để client query.
- Dùng `202 Accepted` khi đã nhận trách nhiệm xử lý bền vững trong một queue/DB thích hợp.
- Sau retry, trả receipt cũ nếu đã hoàn tất.
- Không trả `200 SUCCESS` cho business operation nếu hệ thống không có bằng chứng đủ.

HTTP status là một phần contract nghiệp vụ. `202 Accepted` không tự chứng minh công việc đã được lưu bền vững; chỉ dùng khi kiến trúc đáp ứng mức cam kết mà response biểu đạt.

## 23. Reactive Redis và cancellation

Một ứng dụng WebFlux:

```java
Mono<Long> result = reactiveRedisTemplate
    .opsForValue()
    .increment("orders:submitted");
```

Khi client HTTP disconnect hoặc `timeout` operator phát lỗi, có thể xảy ra Reactor cancellation. Nhưng nếu command đã được gửi tới Redis, cancellation **không nhất thiết hủy được side effect**.

Sai về tư duy:

```text
Client đóng browser
    -> Reactor cancel
    -> Chắc chắn Redis chưa INCR
```

Đúng hơn:

```text
Client đóng browser
    -> application downstream không chờ nữa
    -> Redis command có thể đã:
         chưa gửi / đang queue / đã chạy / đang trả response
```

Đối với write quan trọng, không nên gắn hoàn toàn business completion với kết nối HTTP còn mở hay không. Có thể dùng một persisted command/operation record rồi worker xử lý độc lập, kèm idempotency.

### 23.1. Không `.subscribe()` tùy tiện để “chắc chạy”

Ví dụ nguy hiểm:

```java
public Mono<Void> submit() {
    redis.opsForValue()
        .increment("orders:submitted")
        .subscribe();

    return Mono.empty();
}
```

Hệ thống trả HTTP response trước khi biết Redis thành công hay lỗi; exception của lệnh nằm ngoài request flow, retry và monitoring khó kiểm soát.

Nên trả Publisher:

```java
public Mono<Long> submit() {
    return redis.opsForValue()
        .increment("orders:submitted");
}
```

Nhưng nếu request có thể retry, vẫn cần thay `INCR` trực tiếp bằng một thao tác idempotent theo requestId. Reactive composition **không tự cung cấp exactly-once**.

### 23.2. Reactor retryWhen không tự idempotent

Ví dụ:

```java
return redis.opsForValue()
    .increment("orders:submitted")
    .retryWhen(
        Retry.backoff(
            3,
            Duration.ofMillis(200)
        )
    );
```

Một `Mono` lỗi sau lệnh `INCR` có thể được subscribe lại, làm thực thi lại side effect. `retryWhen` chỉ là cơ chế subscription retry, không biết một phép tăng đã được Redis áp dụng.

Khi bắt buộc retry, hãy retry **publisher đại diện cho một operation có requestId và receipt atomic**, không retry thẳng một lệnh `INCR` không bảo vệ.

## 24. Đọc lại trạng thái sau timeout có đủ để quyết định không?

Một giải pháp hay được đề xuất:

```text
INCR bị timeout.
GET counter.
Nếu value đã tăng, coi như INCR thành công.
```

Cách này thường **không đủ** khi có concurrency.

Ví dụ:

```text
Counter ban đầu 100.
Request A gửi INCR, response mất.
Request B cũng INCR.
A đọc GET -> 102.
```

Từ giá trị 102, A không biết:

- A và B đều tăng mỗi người một lần.
- Chỉ B tăng một lần và một request C khác tăng.
- A bị retry rồi tăng hai lần.
- Có writer khác đặt lại counter.

Một giá trị tổng hợp không thể gắn chắc với một operation ID nếu hệ thống không ghi thêm metadata tương quan.

### 24.1. Khi nào read-after-timeout hữu ích?

Có thể hữu ích nếu:

- Thao tác có ID/receipt riêng.
- Không có writer cạnh tranh hoặc có version/CAS.
- Có business invariant cho phép xác minh.
- Đọc từ source-of-truth phù hợp.
- Hệ thống hiểu failover/replica staleness.

Ví dụ `GET receipt:req-123` sau timeout là câu hỏi chính xác hơn `GET counter` vì receipt gắn trực tiếp với yêu cầu.

Tuy vậy, **receipt missing** không chứng minh request chưa chạy nếu receipt có thể bị mất do TTL, eviction, persistence rollback hoặc lỗi thực thi giữa mutation và ghi receipt.

## 25. Lựa chọn retry theo loại operation

Một policy hợp lý có thể được diễn đạt:

| Loại operation | Retry khi connection timeout? | Điều kiện |
|---|---|---|
| `GET` cache | Có thể | Giới hạn attempts/time budget, tránh load storm |
| `EXISTS`/`TTL` | Có thể | Chấp nhận state thay đổi giữa các lần đọc |
| `SET fixed value` vào cache tái tạo được | Có thể | Không overwrite newer version hoặc kéo dài TTL sai |
| `DEL` cache key | Có thể | Không xóa một incarnation mới cùng tên ngoài ý định |
| `INCR` counter nghiệp vụ | Không retry mù | Lua receipt/unique request ID hoặc transaction bền vững |
| `LPUSH` job | Không retry mù | Dedupe/enqueue receipt hoặc queue semantics |
| `XADD event` | Không retry mù | EventId + outbox/dedupe |
| `PUBLISH` telemetry | Tùy chấp nhận duplicate | Consumer có thể dedupe hoặc bỏ qua trùng |
| `PUBLISH` nghiệp vụ bắt buộc | Không nên dùng làm cơ chế duy nhất | Stream/broker với ACK/recovery |
| `XACK id` | Thường có thể gọi lại cùng ID | Không chạy lại handler trừ khi idempotent |
| Lua script idempotent theo requestId | Có thể | Receipt còn hiệu lực, cùng slot, trạng thái bền vững theo yêu cầu |
| SQL transaction có unique request ID | Có thể | Chính sách retry dựa trên transaction/result lookup |
| Payment API | Chỉ theo contract provider | Idempotency key, status lookup và reconciliation |

### 25.1. Cân bằng retry và deadline

Không chỉ chọn số attempts. Cần chọn:

```text
Total request deadline
Per-attempt command timeout
Backoff + jitter
Max concurrency
Retryable exception categories
Circuit breaker / bulkhead
Idempotency retention horizon
```

Nếu HTTP client timeout sau 2 giây, nhưng backend cứ retry write trong 30 giây và có thể tiếp tục sau khi client bỏ cuộc, hệ thống cần ghi nhận operation ID và có cơ chế cho client truy vấn kết quả sau đó.

### 25.2. Tránh retry storm

Khi một Redis primary gặp sự cố, hàng nghìn application instances có thể cùng nhận timeout. Nếu tất cả retry ngay lập tức, Redis mới phục hồi sẽ bị dội thêm tải.

Sử dụng:

- Exponential backoff.
- Random jitter.
- Retry budget.
- Bounded concurrency.
- Circuit breaker khi lỗi kéo dài.
- Queue có giới hạn nếu cần trì hoãn.
- Deadline và khả năng hủy những việc chưa chắc đã được chấp nhận.
- Quan sát load Redis, không chỉ success rate.

Những biện pháp này bảo vệ availability, **không thay thế idempotency**.

## 26. `@Transactional` và Redis write

Một service Java có thể có:

```java
@Transactional
public void payOrder(...) {
    orderRepository.save(...);
    redis.opsForValue().increment("payments:count");
}
```

Nếu `@Transactional` quản lý transaction của database SQL, nó **không mặc định** biến lệnh Redis thành một phần của cùng một ACID transaction.

Nếu Redis `INCR` thành công nhưng SQL transaction rollback, hai hệ thống có thể không nhất quán. Nếu SQL commit thành công nhưng Redis timeout, không biết counter đã tăng chưa.

Ngay cả khi dùng Redis transaction support của Spring Data Redis, Redis `MULTI/EXEC` không tự kết hợp với database transaction bên ngoài thành distributed two-phase commit.

### 26.1. Outbox để nối commit SQL với gửi event

Một cấu trúc thông dụng:

```text
SQL transaction:
    UPDATE order
    INSERT outbox_event(eventId, payload)
    COMMIT

Background publisher:
    đọc outbox_event
    XADD Redis Stream
    lưu published status sau success
    retry khi timeout

Consumer:
    process idempotent theo eventId
    ACK sau khi thành công
```

Outbox bảo đảm **ý định publish** không biến mất khi app crash sau SQL commit. Nhưng publish từ outbox vẫn có thể tạo duplicate entry nếu `XADD` thành công và confirmation thất lạc.

Vì vậy consumer vẫn cần inbox/processed-event uniqueness hoặc producer idempotent enqueue.

## 27. Idempotency key có TTL, nhưng nghiệp vụ có thể retry rất muộn

Giả sử receipt được lưu:

```redis
SET receipt:req-123 SUCCESS EX 3600
```

Một giờ sau, key hết hạn. Nếu hệ thống có retry từ dead-letter queue sau hai ngày với cùng request ID, lần retry có thể được coi như request mới và side effect xảy ra thêm lần nữa.

Chọn TTL receipt phải trả lời:

- Tối đa sau bao lâu client có thể retry?
- Một message có thể nằm trong queue bao lâu?
- DLQ có thể được replay sau bao lâu?
- Có quy trình manual retry sau nhiều tuần?
- Business contract cần duy trì result receipts trong bao lâu?
- Cần lưu audit/legal record không?
- Memory Redis có đủ để giữ receipt tương ứng không?
- Eviction policy có thể xóa receipt trước TTL không?

Nếu retry horizon rất dài, receipt nên nằm trong nơi có durability/retention phù hợp, có thể là database.

### 27.1. Không dùng keyspace expiration event để xóa receipt nghiệp vụ bắt buộc

Redis keyspace notifications là Pub/Sub best-effort. Không dựa vào event `expired` để đảm bảo sau TTL đã có một workflow archive/cleanup bền vững.

Nếu idempotency record cần được lưu lâu cho compliance hoặc audit, hãy lưu trong storage phù hợp và có job retention riêng.

### 27.2. Mục tiêu: một request ID không được tái sử dụng

Ngay cả sau khi TTL Redis hết hạn, nếu client vô tình tái sử dụng cùng key cho nghiệp vụ mới, ứng dụng khó phân biệt retry cũ với thao tác mới.

Nên quy định request ID unique theo scope và không tái sử dụng trong horizon mà hệ thống cam kết.

## 28. Dữ liệu mới ghi có thể bị xóa bởi một retry DEL trễ

Một vấn đề tinh vi:

```text
t1: Request A xóa session:123 bằng DEL.
t2: Response DEL của A bị mất.
t3: Một request B tạo session mới cùng tên session:123.
t4: A retry DEL session:123.
```

Lần retry của A có thể xóa **session mới của B**.

Đây là lý do `DEL` không phải lúc nào cũng an toàn chỉ vì xóa một key hai lần không thay đổi trạng thái khi **không có recreate xen kẽ**.

### 28.1. Giải pháp theo generation/version

Thay vì dùng cùng tên key cho nhiều phiên bản:

```text
session:123
```

có thể dùng:

```text
session:123:generation:7
session:123:generation:8
```

Hoặc lưu owner/version trong value và chỉ xóa nếu version phù hợp bằng Lua compare-and-delete.

Ví dụ:

```lua
-- KEYS[1]: key
-- ARGV[1]: expected token/version
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Cơ chế version cho phép retry xóa phiên cũ mà không xóa nhầm phiên vừa được tạo.

### 28.2. Delete và recreate còn ảnh hưởng Spring Cache

Một cache invalidation:

```java
redis.delete("product:101");
```

có thể bị retry muộn sau khi một request khác đã repopulate cache. Nếu mục tiêu chỉ là “cache eventual reload”, việc xóa lại có thể chấp nhận. Nhưng nếu xóa key làm kích hoạt tải database tốn kém hoặc dữ liệu mới đã có version, cần cân nhắc side effect đó.

Idempotency phải được đánh giá theo **hệ thống và nghiệp vụ**, không chỉ trạng thái cuối của một key.

## 29. Dedupe bằng Redis Set: có đủ không?

Một phương án:

```redis
SADD processed-events evt-1001
```

SADD cùng member thường là idempotent về membership, nhưng nếu ứng dụng thực hiện:

```text
SADD processed-events evt-1001
nếu trả 1:
    gọi payment API
```

vẫn có lỗ hổng:

```text
SADD thành công, reply mất.
Client retry, SADD trả 0.
Payment API có thể chưa từng được gọi.
```

Hoặc:

```text
Payment API gọi thành công.
Ứng dụng crash trước khi SADD.
Retry -> payment API chạy lần hai.
```

Đưa eventId vào Redis Set giúp biết một yêu cầu **đã được đăng ký** theo một ý nghĩa nào đó, nhưng không tự chứng minh side effect ngoài Redis đã hoàn tất.

### 29.1. Khi side effect nằm trong Redis

Nếu toàn bộ logic cập nhật cả business state và dedupe Set nằm trong cùng một Lua script, cùng hash slot, thì có thể đạt atomicity tại Redis live (với caveat runtime error/failover đã nêu).

### 29.2. Khi side effect nằm ngoài Redis

Cần một transaction/contract bên hệ thống sở hữu side effect, hoặc một workflow có persisted state và reconciliation. Không có một Redis command đơn lẻ nào tạo ACID transaction chung với email gateway hay SQL database độc lập.

## 30. Phân biệt một lệnh đã thực thi với một operation đã hoàn tất

Một operation nghiệp vụ có thể gồm:

```text
1. Validate request.
2. Reserve stock.
3. Charge payment.
4. Update order status.
5. Publish event.
6. Return HTTP response.
```

Nếu Redis connection mất ở bước 2, không thể đánh đồng việc retry **toàn operation** với retry một command. Có thể:

- Stock đã reserve.
- Payment chưa charge.
- Order chưa update.
- Event chưa publish.

Nếu retry toàn flow không có state machine, có thể reserve stock thêm lần nữa.

### 30.1. Dùng operation state machine

Ví dụ:

```text
NEW
  |
  v
RESERVING
  |
  +--> RESERVE_CONFIRMED
           |
           v
       CHARGING
           |
           +--> PAYMENT_CONFIRMED
                       |
                       v
                     DONE
```

Mỗi bước cần idempotency token riêng hoặc một token được provider hiểu theo phạm vi step, và cần lưu trạng thái bền vững.

Khi timeout, điều phối viên hỏi **step nào đã hoàn tất** trước khi retry. Nếu kết quả không xác định và không có lookup phù hợp, chuyển trạng thái `UNKNOWN`/manual reconciliation thay vì tự lặp side effect nguy hiểm.

### 30.2. Saga và compensation không phải rollback tự động

Nếu bước reserve đã thực hiện nhưng charge không thành công, có thể cần release reservation bằng một thao tác bù.

Nhưng compensation cũng có thể timeout, được gửi lại và tạo duplicate nếu không idempotent. Do vậy mỗi step và compensation cần token/state riêng.

## 31. Không thể có exactly-once end-to-end chỉ bằng retry

Để có hiệu ứng “xử lý đúng một lần”, hệ thống thường dùng một trong các mô hình:

- Lưu idempotency receipt **trong cùng transaction** với business mutation.
- Dùng unique constraint theo eventId/requestId ở nguồn dữ liệu có thẩm quyền.
- Dùng transaction/outbox/inbox để ghi dấu và triển khai side effect.
- Dùng external provider idempotency key với hợp đồng rõ ràng.
- Thiết kế deterministic/idempotent state transition.
- Reconciliation khi outcome unknown.
- Kiểm soát duplicate delivery và ordering.

**Exactly-once message delivery** và **exactly-once business effect** không đồng nghĩa. Một broker có thể redeliver nhiều lần nhưng consumer vẫn tạo một effect nhờ inbox dedupe. Ngược lại, một lệnh được giao một lần vẫn có thể tạo side effect hai lần do application retry không kiểm soát.

### 31.1. Bảng về guarantee

| Khái niệm | Có nghĩa gì? | Có ngăn double side effect không? |
|---|---|---|
| TCP transport | Vận chuyển bytes | Không |
| Redis response OK | Lệnh được báo thành công ở mức command | Không ngăn retry muộn |
| Redis command atomic | Một command không bị lệnh khác xen vào | Không nếu command được thực thi lần hai |
| Lua atomic script | Một chuỗi logic Redis không bị lệnh khác xen vào | Chỉ nếu logic script có dedupe |
| Redis transaction | Nhóm command theo ngữ nghĩa MULTI/EXEC | Không nếu replay nguyên transaction |
| Redis PEL/XACK | Theo dõi delivery trong consumer group | Không tự chống business duplicate |
| Idempotency receipt | Nhận diện request đã áp dụng | Có trong phạm vi durability/retention/atomicity của receipt |
| SQL unique constraint + transaction | Chặn ghi trùng theo constraint trong cùng transaction | Mạnh hơn cho business state thuộc SQL |
| Outbox/inbox | Theo dõi publish/process qua restart | Giảm mất/trùng khi kết hợp idempotency |
| AOF/replication | Giảm rủi ro mất state | Không tự làm command idempotent |

## 32. Quan sát và logging khi Redis connection bị đứt

Để điều tra một incident double write, log cần đủ tương quan.

Ví dụ một log có cấu trúc:

```json
{
  "operationId": "reserve-evt-1001",
  "requestId": "req-123",
  "commandFamily": "redis-lua-reserve-once",
  "aggregateId": "sku-42",
  "attempt": 2,
  "outcome": "TIMEOUT_UNKNOWN",
  "elapsedMs": 2150,
  "redisNode": "primary-2",
  "traceId": "trace-abc"
}
```

Không log password Redis, secret token hoặc payload chứa PII không cần thiết. Khi hash key chứa dữ liệu nhạy cảm, dùng mã định danh an toàn hoặc hash trong logs.

### 32.1. Metric nên có

| Metric | Mục tiêu |
|---|---|
| Redis command timeout count | Phát hiện lỗi chưa nhận reply |
| Connection disconnect/reconnect | Xác định sự cố network |
| Retry attempt count | Theo dõi retry storm |
| Unknown-outcome operations | Số operation không xác định kết quả |
| Idempotency hit count | Số lần retry lấy lại receipt |
| Idempotency key conflict | Phát hiện key bị dùng lại với payload khác |
| Receipt missing/expired count | Rủi ro hết retention |
| Lua business error rate | Tách lỗi validation/condition khỏi timeout |
| Event duplicate rate | Đo duplicate eventId |
| PEL pending/oldest idle | Phát hiện Stream messages cần recovery |
| SQL unique-conflict count | Theo dõi event đã xử lý |
| Replication lag/failover | Liên hệ mất state sau failover |
| RDB/AOF persistence health | Đánh giá durability receipt/business state |
| Handler latency p95/p99 | Chọn timeout và retry budget |

Không nên coi mọi `RedisConnectionFailureException` là lỗi khiến business operation chắc chắn thất bại. Phải gắn outcome ở mức `UNKNOWN` khi cần.

### 32.2. Trace từ HTTP tới Redis

Một request ID nên đi qua:

```text
HTTP Idempotency-Key
       |
       v
Business operation
       |
       +--> Redis key receipt
       |
       +--> Logs và tracing
       |
       +--> Event envelope trong Stream
       |
       +--> SQL processed_requests
```

Khi điều tra, người vận hành có thể hỏi:

```text
Request req-123 có receipt không?
Receipt result là gì?
EventId đã vào Stream mấy lần?
Consumer đã apply business effect chưa?
Cơ sở dữ liệu có unique record không?
Có failover/backup rollback trong khoảng đó không?
```

Nếu không có ID xuyên suốt, khó chứng minh thao tác đã chạy hay chưa sau khi reply bị mất.

## 33. Kiểm thử lỗi bằng fault injection

Các bài thử thông thường chỉ kiểm tra Redis hoạt động và trả OK. Chúng không kiểm thử tình huống **command đã thực thi nhưng response không tới client**.

Một bộ test chất lượng cần ít nhất hai kịch bản độc lập:

**A. Request chưa tới Redis:**

```text
Network bị chặn trước khi command được gửi.
Client timeout.
Retry cùng requestId.
Kỳ vọng mutation được áp dụng đúng một lần.
```

**B. Redis đã thực thi nhưng reply mất:**

```text
Command vào Redis.
Redis áp dụng mutation và lưu receipt.
Network làm mất/chặn response.
Client timeout.
Retry cùng requestId.
Kỳ vọng result được lấy từ receipt, không tăng lần hai.
```

Kịch bản B rất quan trọng. Chỉ tắt Redis trước khi gửi lệnh thường chỉ kiểm thử A.

### 33.1. Công cụ và cách tổ chức lab

Trong môi trường local, có thể dùng:

- Toxiproxy hoặc network proxy kiểm thử.
- Network namespace/firewall rule trong môi trường test.
- Testcontainers kết hợp proxy.
- Mock/fake ở tầng adapter để cố ý ném timeout **sau khi đã gọi Redis thành công**.
- Integration test thực tế với Redis standalone/Cluster test.
- Chaos testing có kiểm soát trên môi trường thử nghiệm.

Không thử ngắt network/kill Redis trên hệ thống production để kiểm tra bài học khi chưa có quyền và runbook rollback.

### 33.2. Mô phỏng response lost ở tầng service

Một ví dụ test adapter ý tưởng:

```java
public final class FailAfterWriteAdapter {

    private final ReservationCounterService delegate;
    private boolean firstCall = true;

    public FailAfterWriteAdapter(
            ReservationCounterService delegate) {
        this.delegate = delegate;
    }

    public long reserveOnce(
            String sku,
            String requestId,
            long amount) {

        long applied = delegate.reserveOnce(
            sku, requestId, amount
        );

        if (firstCall) {
            firstCall = false;

            // Giả lập: Redis đã chạy xong, client không biết.
            throw new IllegalStateException(
                "Simulated reply loss after successful write"
            );
        }

        return applied;
    }
}
```

Đây là **mô phỏng ở tầng application**, không phải tái tạo chính xác failure của TCP hay Lettuce. Nó giúp xác minh thuộc tính quan trọng: retry cùng requestId sau một attempt đã thực thi **không tăng counter lần hai**.

### 33.3. Assertions hữu ích

```text
Cho counter ban đầu = 100.
Attempt 1 có requestId=req-123, amount=3:
    Redis thực thi, kết quả thực là 103
    test cố tình làm client thấy timeout

Attempt 2 với requestId=req-123, amount=3:
    trả 103
    counter vẫn 103

Attempt 3 với requestId=req-456, amount=3:
    trả 106
    counter trở thành 106
```

Bài test này kiểm tra chống retry trùng theo request ID ở một Redis live, trong phạm vi TTL receipt. Cần thêm test crash/failover và retention nếu nghiệp vụ yêu cầu durability mạnh.

## 34. Kiểm thử race giữa hai request cùng idempotency key

Một lỗi xảy ra khi hai HTTP requests cùng `Idempotency-Key` được gửi đồng thời:

```text
Client retry rất nhanh hoặc gateway gửi duplicate.
Request A và B tới hai instance Spring khác nhau.
```

Nếu code dùng:

```text
GET receipt
if missing:
    INCR
    SET receipt
```

hai request có thể cùng thấy receipt missing rồi tăng hai lần.

Dùng Lua script cập nhật receipt và mutation trong một lần thực thi trên cùng slot sẽ giảm race này.

Bài test:

```text
100 requests đồng thời:
    same SKU = sku-42
    same request ID = req-same
    amount = 1

Kỳ vọng:
    Counter tăng đúng 1.
    Các response thành công tương ứng cùng business result.
```

Sau đó thử:

```text
100 requests đồng thời:
    same SKU
    request ID khác nhau

Kỳ vọng:
    Counter tăng 100, nếu không có lỗi khác và mỗi request
    được chấp nhận thành công đúng một lần.
```

Đây là bài test correctness trong phạm vi Redis live. Không dùng một lần thành công làm bằng chứng hệ thống chống mọi lỗi failover hoặc retention.

## 35. Kiểm thử concurrency với SET và phiên bản dữ liệu

Một hướng khác là kiểm thử lost update:

```text
Order status ban đầu = PENDING
Request A định chuyển -> PAID
Request B định chuyển -> CANCELLED
A nhận timeout và retry muộn
```

Nếu dùng blind SET:

```redis
SET order:101:status PAID
```

sau khi B đã ghi `CANCELLED`, A có thể ghi đè.

Thay bằng version-aware transition:

```text
State:
   status = PENDING
   version = 10

A:
   expectedVersion = 10
   target = PAID

B:
   expectedVersion = 10
   target = CANCELLED
```

Một script kiểm tra `version == 10` và tăng version khi chuyển trạng thái có thể chỉ cho một request thành công. Retry còn phải kiểm tra receipt của cùng request ID để không hiểu nhầm thành business conflict.

**Version/CAS chống lost update; receipt/request ID chống replay của cùng operation.** Hai thứ bổ sung cho nhau.

## 36. Bài thực hành 1 — Tại sao INCR bị tăng trùng?

Tạo counter trong Redis thử nghiệm:

```redis
SET lab:counter 100
INCR lab:counter
INCR lab:counter
GET lab:counter
```

Giải thích tại sao việc gọi lại `INCR` sau timeout có thể đưa counter lên `102` dù nghiệp vụ chỉ muốn tăng một lần.

Viết hai chuỗi thời gian: request chưa tới Redis và request đã chạy nhưng reply mất. Từ góc nhìn client nhận timeout, những trường hợp nào phân biệt được?

## 37. Bài thực hành 2 — Retry SET và TTL

Tạo:

```redis
SET lab:otp "123456" EX 30
```

Đợi một khoảng thời gian rồi lặp lại cùng câu lệnh. So sánh `PTTL` trước và sau retry.

Trả lời:

- Vì sao final value vẫn giống nhau nhưng deadline thay đổi?
- Nếu OTP phải hết hạn đúng 30 giây từ lúc phát hành lần đầu, nên lưu thông tin nào?
- `SET ... KEEPTTL` có phải giải pháp chung cho mọi yêu cầu tạo OTP mới không?

## 38. Bài thực hành 3 — Lua idempotency

Sử dụng `increment-once.lua` ở phần 11.

Khởi tạo:

```redis
SET counter:{sku-42}:reserved 100
```

Gọi service:

```java
reserveOnce("sku-42", "req-123", 3);
```

Sau đó gọi lại **cùng request ID**:

```java
reserveOnce("sku-42", "req-123", 3);
```

Kỳ vọng:

```text
Lần 1 trả 103.
Lần 2 trả 103.
Counter cuối = 103.
```

Tiếp tục gọi:

```java
reserveOnce("sku-42", "req-456", 3);
```

Kỳ vọng counter thành `106`.

Thảo luận những gì cần bổ sung nếu cùng `req-123` lần hai gửi amount 7.

## 39. Bài thực hành 4 — Mô phỏng mất response

Dùng một test adapter hoặc fault proxy để khiến attempt đầu **thực thi Redis rồi ném timeout** về phía caller. Retry cùng requestId.

So sánh hai phiên bản:

```text
Version A: trực tiếp INCR
Version B: Lua receipt + INCR
```

Đo counter trước/sau và giải thích vì sao Version B có khả năng chống double increment trong Redis live.

Không cần phá hỏng Redis production để tạo case response lost.

## 40. Bài thực hành 5 — Redis Streams XADD *

Trong lab:

```redis
XADD lab:events * eventId evt-1 type CREATED
XADD lab:events * eventId evt-1 type CREATED
XRANGE lab:events - +
```

Quan sát hai entry có ID Redis khác nhau dù eventId giống nhau.

Thảo luận:

- Vì sao business eventId và Stream ID phải tách biệt?
- Consumer có thể dedupe theo eventId ở đâu?
- Nếu publisher commit SQL rồi XADD nhưng timeout, outbox giúp gì?
- Nếu receipt dedupe được đặt trong Redis, retention/failover tác động thế nào?

## 41. Bài thực hành 6 — PEL khi XREADGROUP reply mất

Tạo:

```redis
XGROUP CREATE lab:jobs lab-workers 0 MKSTREAM
XADD lab:jobs * jobId job-1
```

Cho `worker-A` đọc entry nhưng trong test adapter không chuyển response đến handler. Quan sát:

```redis
XPENDING lab:jobs lab-workers
```

Sau đó dùng:

```redis
XREADGROUP GROUP lab-workers worker-A STREAMS lab:jobs 0
```

hoặc recovery `XAUTOCLAIM` từ worker khác sau ngưỡng idle.

Giải thích vì sao chỉ gọi `XREADGROUP ... >` không tự xử lý entry đã pending từ lần đọc trước.

## 42. Bài thực hành 7 — Delete và recreate

Trong môi trường thử:

```redis
SET lab:session:1 old-token
DEL lab:session:1
SET lab:session:1 new-token
```

Giả lập một retry muộn của lệnh `DEL`. Quan sát session mới bị mất.

Thiết kế một compare-and-delete Lua script nhận expected token hoặc version để chỉ xóa incarnation cũ.

## 43. Bài thực hành 8 — Redis failover và receipt rollback

Dùng một môi trường test có replication/persistence được cấu hình và có thể mô phỏng failover an toàn.

Các bước tư duy:

1. Counter và receipt ban đầu chưa có.
2. Attempt cập nhật counter/receipt thành công.
3. Trước khi replica hoặc storage lưu trạng thái mới, primary lỗi.
4. Primary mới không thấy receipt.
5. Client retry cùng requestId.

Hãy phân tích:

- Trường hợp nào mutation trước vẫn còn?
- Trường hợp nào receipt có thể mất?
- Vì sao một Lua script không giải quyết transaction với source-of-truth ngoài Redis?
- AOF/replication cải thiện điều gì và không cải thiện điều gì?
- Khi nào phải dựa vào SQL unique constraint/outbox/reconciliation?

## 44. Bài thực hành 9 — Thiết kế API idempotent

Định nghĩa:

```http
POST /api/inventory/sku-42/reserve
Idempotency-Key: req-777
Content-Type: application/json

{"quantity":2}
```

Yêu cầu:

1. Có request ID ổn định qua retries.
2. Có payload fingerprint.
3. Một receipt trả lại response của attempt đầu.
4. Hai payload khác nhau cùng key phải bị từ chối.
5. Có deadline/retention rõ ràng.
6. Xác định source-of-truth khi Redis mất state.
7. Khi kết quả unknown, client có thể query trạng thái theo requestId.
8. Không dùng `200 OK` nếu không chứng minh business operation hoàn tất.

Vẽ sequence diagram cho request thành công và request mất Redis reply.

## 45. Bài thực hành 10 — Xây dựng retry policy

Đưa ra policy cho:

```text
GET product cache
SET cache key, TTL 60s
INCR inventory counter
XADD OrderCreated
XACK Stream entry
PUBLISH dashboard refresh
Charge payment provider
```

Với mỗi loại:

- Có retry khi timeout không?
- Có thể tạo duplicate effect không?
- Dựa vào idempotency token nào?
- Có cần read-after-timeout/result lookup không?
- Có cần giới hạn attempts và backoff?
- Khi không biết outcome, API nên trả trạng thái gì?
- Receipt/backup cần bền vững bao lâu?

Giải thích vì sao không thể dùng **một RetryTemplate duy nhất** cho mọi command và kỳ vọng đúng nghiệp vụ.

## 46. Những ngộ nhận thường gặp

### “Redis timeout nghĩa là Redis chưa chạy lệnh”

Sai. Lệnh có thể đã chạy và response bị mất.

### “Lettuce auto-reconnect bảo đảm exactly-once”

Sai. Reconnect là phục hồi kết nối; retry/replay và side effect cần được đánh giá riêng.

### “Thêm @Retryable là sửa được lỗi network”

Chỉ có thể giúp khả năng phục hồi, nhưng có thể gây double write nếu method không idempotent.

### “INCR là atomic nên retry an toàn”

Mỗi lần `INCR` atomic, nhưng **hai lần INCR vẫn tăng hai lần**.

### “MULTI/EXEC là transaction nên không thể có duplicate”

Một transaction được replay là một transaction khác; Redis không tự nhận biết cùng business request.

### “SET luôn idempotent”

Không trong mọi tình huống: retry có thể refresh TTL, ghi đè update mới hoặc sửa state không đúng version.

### “DEL hai lần chẳng thay đổi gì”

Không đúng khi một key cùng tên được tạo lại giữa hai lần xóa.

### “SET NX đủ bảo vệ mọi side effect”

Không nếu guard và business operation ở hai hệ thống hoặc nhiều command không atomic.

### “Lua đảm bảo exactly-once trong mọi sự cố”

Lua có thể bảo vệ atomic dedupe trên Redis live cùng slot, nhưng không tự rollback runtime errors hay loại bỏ persistence/failover loss và transaction với external systems.

### “XADD retry cùng eventId tự động bị Redis bỏ qua”

Không. `XADD *` có thể tạo nhiều entry khác ID với cùng eventId.

### “XACK thành công nghĩa business operation chỉ chạy một lần”

Không. XACK chỉ quản lý PEL của consumer group; business effect có thể đã trùng trước đó.

### “Retry PUBLISH bảo đảm subscriber nhận đúng một lần”

Không. Pub/Sub có thể bị mất message hoặc phát duplicate nếu retry.

### “Đọc counter sau timeout là biết request của tôi đã tăng chưa”

Không đáng tin cậy khi có concurrent writers và không có operation receipt.

### “Bật AOF/replica là không thể ghi trùng”

Persistence và replication giảm mất dữ liệu, **không đổi tính idempotent của command**.

### “Reactive timeout hủy side effect Redis”

Không được bảo đảm nếu command đã gửi đến Redis.

## 47. Câu hỏi tự đánh giá

1. Những thời điểm nào trong đường đi của một Redis command có thể làm response mất sau execution?
2. Vì sao một exception kết nối không đủ chứng minh lệnh chưa chạy?
3. Khác biệt giữa command atomic và command idempotent là gì?
4. Vì sao `INCR` vẫn có thể tăng hai lần dù Redis thực thi từng lệnh nguyên tử?
5. `SET key value EX 60` retry muộn có thể thay đổi điều gì?
6. `SADD` lần hai trả `0` có chứng minh attempt đầu thất bại không?
7. Vì sao `DEL` có thể xóa nhầm key mới khi retry?
8. Lettuce auto-reconnect có vai trò gì và không bảo đảm điều gì?
9. Vì sao `@Retryable` phải đặt sau khi thiết kế idempotency?
10. Request ID phải được tạo ở đâu để ổn định qua HTTP/service retries?
11. Vì sao cùng idempotency key nhưng payload khác phải bị từ chối?
12. `SET NX` rồi `INCR` trong hai lệnh riêng có lỗ hổng nào?
13. Lua script cùng slot giúp gì cho counter và receipt?
14. Vì sao runtime error bên trong Lua vẫn có thể để lại write một phần?
15. Vì sao idempotency receipt TTL phải theo retry horizon?
16. Nếu receipt bị eviction hoặc mất sau failover, rủi ro gì?
17. `XADD *` retry có thể tạo bao nhiêu Stream IDs?
18. Vì sao cần business eventId ngoài Redis Stream ID?
19. Connection mất sau `XREADGROUP` có thể ảnh hưởng PEL như thế nào?
20. `XACK` retry khác retry cả handler + XACK ra sao?
21. Vì sao `PUBLISH` response count không là ACK nghiệp vụ?
22. Tại sao `EXEC` timeout có thể dẫn tới retry nguyên transaction sai?
23. Pipeline có all-or-nothing không?
24. `WAIT`/`WAITAOF` có làm `INCR` idempotent không?
25. Vì sao SQL unique constraint trong cùng transaction có thể mạnh hơn Redis cache receipt khi side effect ở SQL?
26. Transactional outbox vẫn có thể publish duplicate ở trường hợp nào?
27. Thế nào là `UNKNOWN` outcome trong API và làm sao client kiểm tra tiếp?
28. Khi nào nên dùng `concatMap`/giới hạn concurrency để tránh retry xen kẽ với update mới?
29. Vì sao distributed lock không thay thế request idempotency?
30. Một kịch bản fault injection nào chứng minh xử lý được response lost sau khi Redis đã execute?

## 48. Ghi nhớ

- **Kết nối đứt sau khi gửi lệnh làm kết quả thực thi có thể không xác định.** Redis có thể đã áp dụng write nhưng response chưa tới Spring Data Redis client.
- **Timeout không đồng nghĩa rollback.** Reactor cancellation, HTTP timeout hay reconnect không tự đảo ngược command đã thực thi.
- Phân biệt **atomicity**, **idempotency**, **concurrency correctness** và **durability**; mỗi tính chất giải quyết một vấn đề khác nhau.
- Retry mù `INCR`, `HINCRBY`, `LPUSH`, `XADD *`, `PUBLISH`, `EVAL` hoặc `EXEC` có thể gây double write/double side effect.
- `SET`/`DEL` chỉ an toàn trong những điều kiện xác định; TTL refresh, recreate và lost update khiến chúng có thể không an toàn khi replay.
- **Backoff giúp giảm tải, idempotency giúp chống ghi trùng.** Cần cả hai khi retry mutation quan trọng.
- Dùng **request ID ổn định** qua mọi retry, scope theo tenant/operation, ràng buộc với payload hash và lưu result receipt.
- Khi mutation và receipt đều ở Redis cùng hash slot, **Lua script** có thể kiểm tra request ID và cập nhật atomically trong trạng thái live; cần lưu ý runtime error, TTL, eviction và failover.
- **Redis Streams có thể nhận duplicate XADD entries**, còn consumer group có thể có pending message khi `XREADGROUP` response mất. Consumer cần eventId, PEL recovery và idempotency.
- **XACK là xác nhận delivery state**, không phải xác nhận business effect đúng một lần.
- Khi side effect nằm ở SQL/payment provider, cần transaction/unique key, outbox/inbox, provider idempotency hoặc reconciliation. Redis guard riêng không tạo transaction xuyên hệ thống.
- Replication/RDB/AOF giảm rủi ro mất state theo mức cấu hình, nhưng không tự bảo đảm exactly-once end-to-end.
- Với operation outcome không xác định, **không báo chắc “chưa thực hiện” hoặc gửi lại bằng request ID mới**; cho phép kiểm tra receipt và retry bằng cùng identity.
- Kiểm thử hai tình huống **chưa gửi được command** và **Redis đã thực thi nhưng reply bị mất**. Chỉ test disconnect trước khi gửi chưa phát hiện lỗi double write.

### Tài liệu tham khảo chính thức

- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/)
- [Redis — SET](https://redis.io/docs/latest/commands/set/)
- [Redis — SADD](https://redis.io/docs/latest/commands/sadd/)
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
