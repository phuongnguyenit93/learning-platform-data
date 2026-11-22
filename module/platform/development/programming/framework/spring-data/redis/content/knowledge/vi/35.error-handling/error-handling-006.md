# Retry theo tính lũy đẳng của từng lệnh trong Spring Data Redis

## 1. Vấn đề: lỗi kết nối không cho biết lệnh đã chạy hay chưa

Ứng dụng Spring Data Redis có thể gặp timeout, kết nối bị ngắt, primary failover hoặc lỗi mạng ngay khi đang gửi một lệnh Redis. Điều khó nhất không phải lúc nào cũng là **kết nối lại**, mà là xác định lệnh trước đó **đã tác động tới dữ liệu hay chưa**.

Ví dụ một yêu cầu tăng bộ đếm:

```text
Ứng dụng                  Redis primary
    |                           |
    |---- INCR order:count ---->|
    |                           |  count: 7 -> 8
    |<--- phản hồi bị mất -------X
    |
    |---- INCR order:count ---->|  Retry
    |                           |  count: 8 -> 9
    |<----------- 9 ------------|
```

Ứng dụng chỉ muốn tăng một lần nhưng kết quả là tăng **hai lần**. Cả hai lệnh `INCR` trên Redis đều hợp lệ, vì thế hệ thống không nhất thiết có lỗi Redis nào sau lượt retry.

Đây là lý do không thể áp dụng một quy tắc đơn giản như “hễ `RedisConnectionFailureException` thì retry toàn bộ command”. Trước tiên phải đánh giá **tính lũy đẳng (idempotency)** của từng lệnh, cách xác định kết quả khi response bị mất, và tác dụng phụ nghiệp vụ đi kèm.

Bài học này tập trung vào:

1. Phân biệt retry an toàn và retry có thể nhân đôi tác dụng phụ.
2. Nhận diện tính lũy đẳng của các nhóm lệnh Redis thường dùng qua Spring Data Redis.
3. Thiết kế retry theo **command + tham số + điều kiện cạnh tranh + yêu cầu kết quả**.
4. Áp dụng chính sách khác nhau cho `RedisTemplate` và `ReactiveRedisTemplate`.
5. Sử dụng idempotency key, lệnh nguyên tử hoặc Lua khi command vốn không lũy đẳng.
6. Giới hạn số lần retry, xử lý tình huống kết quả không xác định và đo tác động vận hành.

## 2. Tính lũy đẳng là gì?

Một phép cập nhật được gọi là **lũy đẳng đối với trạng thái được xét** khi thực hiện nó nhiều lần với cùng tham số tạo cùng kết quả trạng thái như thực hiện một lần.

Đối với phép biến đổi trạng thái `f`:

```text
f(f(state)) = f(state)
```

Ví dụ:

```redis
SET profile:42:status ACTIVE
SET profile:42:status ACTIVE
```

Nếu không có thay đổi xen giữa, không gắn TTL và chỉ xét giá trị của key, sau một hay hai lần `SET` thì value cuối đều là `ACTIVE`. Đây là một thao tác có tính lũy đẳng **trong phạm vi kết quả trạng thái đó**.

Ngược lại:

```redis
INCR profile:42:loginCount
INCR profile:42:loginCount
```

Một lần tăng khác hai lần tăng. `INCR` **không lũy đẳng**.

### Lũy đẳng có nhiều cấp độ

Cần phân biệt:

| Cấp độ | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Trạng thái Redis cuối cùng | Lặp lệnh có tạo cùng state không? | `SET key X` lặp lại thường vẫn là X. |
| Thời hạn/metadata | TTL, version, timestamp hoặc thứ tự có đổi không? | `SET key X EX 600` lặp lại sẽ làm mới TTL. |
| Kết quả trả về | Hai lần gọi có trả cùng mã/giá trị không? | `DEL key` lần đầu có thể trả 1, lần sau 0. |
| Tác dụng phụ | Có phát event, audit hoặc tăng counter thêm không? | `PUBLISH` lặp lại phát hai thông điệp. |
| Nghiệp vụ end-to-end | Một đơn hàng hoặc thanh toán có bị xử lý lặp không? | Một `SET` lũy đẳng không đồng nghĩa lời gọi email phía sau cũng vậy. |

Một command có thể lũy đẳng về **trạng thái key** nhưng **không lũy đẳng về TTL, output hoặc tác dụng phụ quan sát được**.

Bởi vậy, câu hỏi đúng không chỉ là “lệnh này có idempotent không?”, mà là:

> Retry cùng lệnh, cùng key, cùng payload trong khoảng thời gian có client khác ghi/xóa, có đáp ứng đúng hợp đồng nghiệp vụ không?

## 3. Phân biệt ba trường hợp lỗi

Khi Redis command gặp sự cố, ứng dụng có thể rơi vào ba trạng thái.

### 3.1. Chắc chắn chưa gửi lệnh

Ví dụ validate input ngay tại Java thất bại trước khi tạo command, hoặc ứng dụng quyết định không gọi Redis. Trong trường hợp này, không có tác dụng phụ Redis cần lo.

Nhưng lỗi connection exception ở client **không mặc nhiên chứng minh** lệnh chưa được gửi. Dữ liệu có thể đã rời khỏi client trước khi connection bị đóng.

### 3.2. Chắc chắn lệnh thất bại trước khi thay đổi

Ví dụ Redis trả lỗi cú pháp hoặc loại dữ liệu không hợp lệ đối với một command đơn lẻ chưa thực hiện thay đổi. Các lỗi xác định như `WRONGTYPE`, `NOPERM` và đối số không hợp lệ thường cần sửa dữ liệu/cấu hình, **không phải retry cùng lệnh nhiều lần**.

Tuy nhiên với **script Lua hoặc quy trình nhiều lệnh**, lỗi ở lệnh sau có thể xảy ra sau khi lệnh trước đã cập nhật dữ liệu. Không suy luận toàn bộ script được rollback khi có exception.

### 3.3. Không rõ lệnh đã áp dụng chưa

Đây là trường hợp khó:

```text
Client gửi SET/INCR/XADD
Redis có thể đã thực thi
Phản hồi bị mất do timeout hoặc mất kết nối
Client không có kết quả chắc chắn
```

Một connection failure hoặc client-side timeout thường **không phân biệt được** “Redis chưa thực thi” và “Redis đã thực thi nhưng response bị mất”.

Đối với command lũy đẳng, retry với cùng tham số có thể là cách khôi phục an toàn nếu không vi phạm điều kiện cạnh tranh. Đối với command không lũy đẳng, phải có thêm cơ chế phát hiện lần thực hiện trước.

## 4. Bảng phân loại các lệnh Redis thường dùng

Bảng dưới đây xét trường hợp **retry cùng tham số** và chỉ tập trung vào tính lũy đẳng của thao tác Redis; tính đúng đắn khi có nhiều writer cần được đánh giá riêng.

| Lệnh / Spring Data Redis | Trạng thái khi thực hiện lặp | Kết luận thực hành |
| --- | --- | --- |
| `GET key` / `opsForValue().get` | Không sửa key | Có thể retry với lỗi tạm thời; kết quả có thể đổi nếu writer khác cập nhật. |
| `MGET` / đọc Hash, Set, ZSet | Chỉ đọc | Thường retry được, nhưng không đảm bảo snapshot bất biến. |
| `EXISTS key` / `hasKey` | Không sửa key | Retry được cho mục tiêu quan sát; kết quả có thể đổi theo thời gian. |
| `TTL key` / `getExpire` | Chỉ đọc metadata | Retry được, nhưng thời gian còn lại sẽ giảm. |
| `SET key fixedValue` không expiration | Ghi đè cùng value | Thường lũy đẳng về value cuối; không an toàn nếu ghi cũ có thể đè thay đổi mới. |
| `SET key value EX 60` | Value như cũ nhưng deadline được làm mới | Không lũy đẳng về TTL; retry có thể kéo dài hạn sống. |
| `HSET hash field fixedValue` | Cùng field nhận cùng value | Thường lũy đẳng về field value; return count có thể khác. |
| `SADD set member` | Member sau cùng vẫn tồn tại | Lũy đẳng về membership; số phần tử thêm trả về khác. |
| `SREM set member` | Member sau cùng không còn | Lũy đẳng về membership; return count có thể khác. |
| `DEL key` | Key sau cùng vắng mặt | Lũy đẳng về trạng thái vắng mặt, nhưng return count khác và có rủi ro key được tái tạo giữa hai lần. |
| `EXPIRE key seconds` | Đặt deadline dựa trên thời điểm mỗi lượt gọi | Không lũy đẳng về deadline tuyệt đối. |
| `PEXPIREAT key absoluteTimestamp` | Cùng thời điểm hết hạn tuyệt đối | Có tính lũy đẳng về deadline nếu key không bị thay thế; return có thể khác. |
| `INCR`, `DECR`, `INCRBY` | Mỗi lượt thay đổi counter | Không lũy đẳng. |
| `APPEND` | Mỗi lượt nối thêm dữ liệu | Không lũy đẳng. |
| `LPUSH` / `RPUSH` | Mỗi lượt thêm phần tử | Không lũy đẳng. |
| `LPOP` / `RPOP` / `BRPOP` | Mỗi lượt lấy/xóa một phần tử | Không lũy đẳng; retry có thể lấy phần tử tiếp theo. |
| `XADD stream * ...` | Mỗi lượt sinh record ID mới | Không lũy đẳng. |
| `PUBLISH channel msg` | Mỗi lượt phát message tới subscribers hiện có | Không lũy đẳng về delivery; không có ACK nghiệp vụ. |
| `GETDEL key` | Lần đầu lấy và xóa; lần sau thường nil | Không lũy đẳng về kết quả/truyền dữ liệu. |
| `SET NX` / `setIfAbsent` | Chỉ lượt đầu có thể tạo | Không tạo trùng state, nhưng retry trả `false` không chứng minh lần đầu không thành công. |
| `XACK stream group id` | Pending entry sau cùng không còn | Có thể retry để bảo đảm trạng thái ACK; số entry ACK trả về có thể từ 1 thành 0. |

**Không dùng bảng như danh sách “lệnh nào retry vô điều kiện”.** Đọc lại dữ liệu có thể khác vì concurrency, và một lệnh vốn lũy đẳng với key cũ có thể trở nên nguy hiểm khi key đã bị một request khác dùng lại.

## 5. Retry lệnh đọc: thường an toàn về side effect, nhưng không miễn phí

Ví dụ Spring Data Redis:

```java
String value = stringRedisTemplate.opsForValue()
        .get("catalog:sku-42");
```

`GET` không sửa state Redis. Nếu lỗi kết nối tạm thời, retry có thể đọc được dữ liệu mà không làm thay đổi key.

Tuy nhiên:

- Dữ liệu có thể thay đổi từ lượt đọc đầu tới lượt retry.
- Key có thể hết TTL hoặc bị eviction.
- Với Redis Cluster, sau failover có thể đọc từ primary/replica có tiến độ khác nhau.
- Một đường đọc bên ngoài Redis có thể cần snapshot/version nhất quán; retry `GET` không tự tạo bảo đảm đó.
- Retry quá nhiều làm tăng tải khi Redis đang suy yếu.

Nếu ứng dụng cần kiểm tra một trạng thái ổn định trong toàn request, nên định nghĩa version/transaction hoặc cơ chế optimistic concurrency, thay vì kỳ vọng đọc lặp sẽ trả cùng value.

### Lệnh đọc có side effect

Không phải lệnh có chữ “get” đều là read-only. Ví dụ:

```redis
GETEX session:42 EX 600
```

`GETEX` vừa đọc vừa đặt lại thời hạn. Retry có thể kéo dài TTL thêm một lần. Tương tự `GETDEL` vừa lấy vừa xóa. **Phân loại theo tác dụng thật của command**, không theo tên method Java.

## 6. Retry `SET`: giá trị lũy đẳng, TTL và lost update

### 6.1. Ghi lại cùng giá trị

```redis
SET profile:42:status ACTIVE
SET profile:42:status ACTIVE
```

Nếu cùng key, cùng value, không có writer khác, việc lặp có cùng kết quả trạng thái `ACTIVE`.

Spring Data Redis:

```java
stringRedisTemplate.opsForValue()
        .set("profile:42:status", "ACTIVE");
```

Có thể retry thao tác này sau lỗi tạm thời **khi nghiệp vụ cho phép ghi đè cùng value**.

### 6.2. Có writer khác thì retry có thể làm sai thứ tự nghiệp vụ

```text
Request A: SET status ACTIVE -> server thực hiện, response mất
Request B: SET status SUSPENDED -> server thực hiện
Request A: retry SET status ACTIVE -> đè thay đổi mới của B
```

Dù `SET key ACTIVE` lũy đẳng khi chạy riêng, retry A **không an toàn về tính đúng đắn khi có concurrency**.

Nếu cần “chỉ cập nhật khi version còn là v3”, sử dụng cơ chế compare-and-set bằng Lua hoặc transaction `WATCH/MULTI/EXEC`, và xác minh business version thay vì ghi đè vô điều kiện.

### 6.3. `SET EX` không lũy đẳng về TTL

```redis
SET session:42 ACTIVE EX 600
```

Lượt đầu chạy lúc 10:00, deadline khoảng 10:10. Nếu retry đúng lệnh lúc 10:02, deadline chuyển sang khoảng 10:12. Value cuối giống nhau nhưng **session sống lâu hơn**.

Nếu nghiệp vụ yêu cầu hết hạn ở **một mốc cố định**, có thể thiết kế expiration theo timestamp tuyệt đối nhất quán từ lần đầu, ví dụ sử dụng cú pháp Redis hỗ trợ `EXAT`/`PXAT`, hoặc ghi có điều kiện phù hợp.

```redis
SET session:42 ACTIVE EXAT 1790000000
```

Timestamp chỉ minh họa; trong code thật phải tính và giữ nguyên deadline trước các lượt retry, không tạo deadline mới mỗi lần gọi.

### 6.4. `SET NX` không trả cùng kết quả khi retry

```redis
SET lease:resource:42 token-A NX EX 60
```

Lượt đầu có thể tạo key thành công, nhưng response mất. Lượt retry trả nil/false do key đã tồn tại. Nếu application hiểu false là “một owner khác đã chiếm lease”, nó có thể kết luận sai về chính request của mình.

Muốn biết lease có thuộc request hay không, có thể đọc token để kiểm tra, nhưng **đọc kiểm tra riêng** vẫn chịu race do TTL/owner khác. Một thiết kế lease đúng cần token đủ độc nhất, hành vi compare-and-set/compare-and-delete nguyên tử và khả năng xử lý kết quả không rõ ràng. Đối với lock quan trọng, cần fencing token khi tương tác với nguồn dữ liệu bên ngoài Redis.

## 7. Retry `DEL`: nhìn trạng thái và xem xét việc tạo lại key

```redis
DEL temp:job:42
DEL temp:job:42
```

Nếu không có ai tạo lại key, cả hai lần đều làm key vắng mặt sau cùng. Nhưng return count khác:

```text
Lần đầu: 1
Lần sau: 0
```

Trong Spring Data Redis:

```java
Boolean deleted = stringRedisTemplate.delete("temp:job:42");
```

Một response `false` ở lượt retry **không chứng minh** lượt xóa đầu không thành công. Có thể lượt đầu đã xóa xong.

Nguy hiểm hơn:

```text
t0: Request A DEL session:42, response mất
t1: Request B tạo lại session:42 cho một chủ sở hữu mới
t2: Request A retry DEL session:42
t3: Session mới bị xóa
```

Nếu key có thể được tái tạo trong khoảng retry, `DEL` không an toàn với nghiệp vụ “xóa đúng đối tượng cũ”. Hãy dùng định danh có generation/version trong key, hoặc Lua kiểm tra token/version rồi xóa nguyên tử.

**Quy tắc:** lũy đẳng theo “key cuối cùng vắng mặt” không đủ khi tính đúng đắn đòi hỏi bảo vệ một thế hệ key mới.

## 8. Nhóm thao tác tập hợp: lũy đẳng về membership, không nhất thiết về output

### Set

```redis
SADD members:active user-42
SADD members:active user-42
```

Sau cùng, member `user-42` vẫn chỉ xuất hiện một lần. Lệnh `SADD` có tính lũy đẳng về membership với tham số không đổi.

Tuy nhiên return count có thể là 1 ở lượt đầu và 0 ở lượt sau. Nếu ứng dụng dựa vào “trả 1 nghĩa là lần này mới thêm” để gửi email, retry có thể làm mất ngữ nghĩa ban đầu hoặc tạo side effect không nhất quán.

```java
Long added = stringRedisTemplate.opsForSet()
        .add("members:active", "user-42");
```

Tương tự, `SREM` lặp không giữ member trong set nhưng số phần tử xóa được có thể khác. Lũy đẳng về trạng thái không đồng nghĩa lũy đẳng về kết quả trả về.

### Hash

```redis
HSET profile:42 name Linh
HSET profile:42 name Linh
```

Ghi cùng field/value thường cho cùng state. Nhưng nếu writer khác vừa cập nhật name thành một giá trị mới, lượt retry có thể ghi đè. Phải xét ownership, concurrency và version của Hash.

### Sorted Set

```redis
ZADD leaderboard 125 user-42
ZADD leaderboard 125 user-42
```

Một lần và hai lần có thể cho cùng score cuối nếu không có ghi xen giữa; nhưng `ZINCRBY` làm tăng score mỗi lượt, **không lũy đẳng**.

Cần phân loại theo cách cập nhật score: đặt score tuyệt đối khác tăng score tương đối.

## 9. Các lệnh không lũy đẳng: bộ đếm, danh sách, stream và Pub/Sub

### 9.1. Bộ đếm

```java
Long next = stringRedisTemplate.opsForValue()
        .increment("orders:sequence");
```

Lượt retry có thể tăng tiếp, tạo gap không mong muốn hoặc làm sai tổng đếm. Với sequence đôi khi gap được chấp nhận nhưng **mỗi request nhận hai số** vẫn phải có hợp đồng xử lý rõ.

### 9.2. List push/pop

```java
stringRedisTemplate.opsForList()
        .rightPush("jobs:pending", "job-42");
```

Retry `RPUSH` có thể đưa hai bản `job-42` vào list. Retry `LPOP` sau khi response mất có thể lấy **job khác**, làm thất lạc job thứ nhất với ứng dụng.

Nếu cần queue với trạng thái pending/ACK/retry, không dùng List pop đơn giản rồi retry mù. Cân nhắc Redis Streams consumer group hoặc hệ thống queue bền vững phù hợp.

### 9.3. Redis Streams

```redis
XADD jobs:events * type created id 42
```

Dấu `*` sinh một stream ID mới mỗi lượt. Retry tạo **hai record riêng** nếu lần đầu thực sự thành công nhưng phản hồi mất.

Nếu cần đảm bảo một business event được ghi một lần, dùng event ID ổn định và cơ chế deduplication/transactional outbox. Tự tính stream ID có điều kiện phải xét quy tắc ID tăng dần, race và semantics của Redis; không tự thay dấu `*` bằng một ID bất kỳ mà cho rằng retry luôn thành công.

### 9.4. Redis Pub/Sub

```java
stringRedisTemplate.convertAndSend(
        "orders.created", "{\"orderId\":\"42\"}");
```

Retry có thể phát cùng thông điệp lần nữa. Subscriber không nhận metadata ACK nghiệp vụ từ giá trị trả về của `PUBLISH`, vì thế không thể dùng một retry count để bảo đảm exactly-once delivery.

Nếu nghiệp vụ chấp nhận nhận trùng, đặt `eventId` ổn định trong payload và làm handler idempotent. Nếu cần replay khi subscriber offline, Pub/Sub không đáp ứng; chọn cơ chế event log/queue bền vững.

### 9.5. Lua script

Một script Lua có thể vừa có command lũy đẳng vừa có command không lũy đẳng. **Bản thân `EVAL`/`EVALSHA` không lũy đẳng**; tính chất phụ thuộc logic trong script.

Ví dụ script gọi `INCRBY` mỗi lần sẽ tăng mỗi retry. Script kiểm tra idempotency key trước khi cập nhật thì có thể giảm nguy cơ trùng, nhưng phải hiểu atomicity, lỗi từng lệnh và giới hạn persistence/failover.

## 10. Đừng biến lỗi nghiệp vụ thành lỗi có thể retry

Không nên retry mọi `DataAccessException` hoặc mọi exception.

Các nhóm thường cần phân biệt:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Kết nối/timeout tạm thời | Mất kết nối, timeout do mạng, Redis failover | Có thể retry **nếu command phù hợp**, giới hạn số lần. |
| Cấu hình/quyền | `NOAUTH`, `NOPERM`, sai host hoặc không cấp quyền lệnh | Sửa cấu hình/ACL; retry cùng lệnh không giải quyết. |
| Dữ liệu/kiểu | `WRONGTYPE`, numeric value không hợp lệ cho `INCR` | Sửa dữ liệu hoặc logic; không retry mù. |
| Tài nguyên | Redis hết bộ nhớ, lỗi AOF/RDB/disk | Có thể cần cảnh báo và giảm tải; retry vô hạn gây quá tải thêm. |
| Business conflict | `SET NX` không tạo vì key đã có, optimistic lock không đạt | Đây thường là kết quả hợp lệ, không phải sự cố kết nối. |
| Topology | `MOVED`/`ASK`, failover Redis Cluster | Ưu tiên driver cluster-aware/refresh topology; phân biệt lỗi còn tồn tại với việc cần lặp tác vụ. |

Spring Data Redis chuyển nhiều lỗi từ driver thành hệ exception của Spring, thường là `DataAccessException` hoặc các subtype như `RedisConnectionFailureException`. Timeout có thể xuất hiện dưới các kiểu khác nhau tùy driver, phiên bản và call path.

Cần **phân loại exception thực tế** của dự án, thay vì giả định mọi timeout luôn là đúng một class. Đồng thời nếu command đã có side effect, ngay cả một lỗi tạm thời được phép retry về mặt kỹ thuật cũng phải được xét qua idempotency.

## 11. Chính sách retry nên thuộc từng operation, không chỉ theo exception

Một chính sách tốt gồm bốn trục:

1. **Loại command:** read-only, set trạng thái, tăng/append/pop, publish, script...
2. **Tham số và điều kiện:** value có cố định không, TTL có được giữ nguyên không, có writer cạnh tranh không?
3. **Lỗi:** transient network/timeout hay lỗi logic/cấu hình?
4. **Ngân sách:** bao nhiêu lượt, tổng thời gian, backoff, jitter và số request đồng thời?

Ví dụ bảng quyết định:

| Operation nghiệp vụ | Redis command | Có auto-retry không? | Điều kiện |
| --- | --- | --- | --- |
| Xem giá trị cache | `GET` | Thường có | Chỉ retry lỗi tạm thời, giới hạn deadline request. |
| Ghi cấu hình cố định | `SET key fixedValue` | Có điều kiện | Có quyền ghi đè, không vi phạm version/concurrency, không reset TTL trái ý. |
| Đặt trạng thái với deadline cố định | `SET ... EXAT/PXAT` | Có điều kiện | Giữ nguyên deadline qua retry, xử lý writer khác. |
| Gỡ một member | `SREM` | Có điều kiện | Return count không được hiểu là kết quả duy nhất cần giữ. |
| Giải phóng lock | `DEL` | Không dùng mù | Phải so sánh owner token atomically. |
| Tăng số dư/counter | `INCRBY` | Không tự động | Dùng idempotency operation ID hoặc thiết kế chấp nhận lặp. |
| Thêm job vào List | `RPUSH` | Không tự động | Có thể tạo job trùng; chuyển queue có dedup nếu cần. |
| Tạo stream entry | `XADD *` | Không tự động | Cần event ID/dedup và chính sách ghi bền vững. |
| Phát notification | `PUBLISH` | Không auto-retry nếu không chấp nhận trùng | Subscriber phải xử lý duplicate; Pub/Sub không replay. |
| ACK stream message | `XACK` | Có điều kiện | Có thể retry theo mục tiêu “không còn pending”; response count có thể khác. |

Nên ghi policy ở **method service** theo nghiệp vụ, không đặt một interceptor toàn cục retry mọi lệnh Redis.

## 12. Ví dụ với imperative `StringRedisTemplate` và Spring Retry

### 12.1. Dependency và phạm vi

Nếu dự án dùng Spring Retry, thường cần thư viện `spring-retry` và tích hợp AOP phù hợp. Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Tùy Spring Boot/dependency management, phiên bản thư viện và cách tạo bean có thể khác. Bài này dùng `RetryTemplate` để minh họa policy tường minh theo operation; tránh đặt retry toàn cục ngay tại Redis driver nếu chưa đánh giá idempotency.

### 12.2. Bean retry giới hạn cho lỗi kết nối

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class RedisRetryConfiguration {

    @Bean
    public RetryTemplate redisReadRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(RedisConnectionFailureException.class)
                .build();
    }
}
```

Ý nghĩa:

- Tổng tối đa **3 lần thực hiện**, gồm lần đầu và các lượt retry; không phải 3 retry sau lần đầu.
- Exponential backoff giúp không dồn request vào Redis khi mới bị lỗi.
- Policy minh họa chỉ bắt lỗi kết nối đã chỉ định. Timeout có thể được biểu diễn khác tùy driver; ứng dụng cần bổ sung phân loại có kiểm soát sau khi quan sát exception thực tế.

Trong môi trường production, thêm jitter/backoff budget và circuit breaker khi cần; không phải mọi version của RetryTemplate builder đều cung cấp cùng một API cấu hình jitter, nên xác nhận dependency được sử dụng.

### 12.3. Áp dụng cho `GET`

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;
    private final RetryTemplate redisReadRetryTemplate;

    public ProductCacheReader(
            StringRedisTemplate redis,
            RetryTemplate redisReadRetryTemplate) {
        this.redis = redis;
        this.redisReadRetryTemplate = redisReadRetryTemplate;
    }

    public String findStatus(String productId) {
        String key = "product:" + productId + ":status";

        return redisReadRetryTemplate.execute(
                context -> redis.opsForValue().get(key));
    }
}
```

Ở đây retry chỉ bao quanh **một command GET**. Không có thao tác phát email hoặc thay đổi database trong callback retry, nên mỗi lượt lặp không nhân đôi side effect ngoài Redis.

Nếu key không tồn tại, `get(key)` trả `null` theo API imperative. Đó thường là kết quả hợp lệ, **không phải exception để retry**. Chỉ vì giá trị không có không nên tự tạo một vòng retry nhiều lần.

### 12.4. Tách policy cho ghi lũy đẳng

Giả sử API cho phép ghi một cấu hình tuyệt đối mà không có TTL:

```java
public void setMaintenanceMode(String value) {
    if (!"ON".equals(value) && !"OFF".equals(value)) {
        throw new IllegalArgumentException("Giá trị không hợp lệ");
    }

    redisReadRetryTemplate.execute(context -> {
        redis.opsForValue().set("config:maintenance", value);
        return null;
    });
}
```

Đây chỉ là ví dụ về retry lệnh `SET` cùng tham số. Dùng chung tên biến `redisReadRetryTemplate` có thể gây hiểu nhầm; trong ứng dụng thật hãy đặt tên policy theo phạm vi, như `redisIdempotentWriteRetryTemplate`, và xác định rõ nghiệp vụ có chấp nhận overwrite khi writer khác đổi giá trị trong lúc retry hay không.

Nếu chế độ bảo trì chỉ được cập nhật bằng version có kiểm soát, không dùng SET unconditional ở ví dụ này; phải nâng lên cơ chế compare-and-set/version.

### 12.5. Không đặt `INCR` vào cùng retry template chỉ vì exception giống nhau

```java
// KHÔNG NÊN:
return redisReadRetryTemplate.execute(context ->
        redis.opsForValue().increment("metrics:orders"));
```

Nếu lần đầu tăng thành công nhưng response mất, retry có thể tăng thêm lần nữa. Việc dùng RetryTemplate không biến một command không lũy đẳng thành lũy đẳng.

## 13. Retry trong reactive Redis: `retryWhen` là resubscription

Với `ReactiveStringRedisTemplate`, mỗi operation trả một Reactor publisher. Lặp bằng `retryWhen` có nghĩa là **subscribe lại vào upstream** sau lỗi, thường phát Redis command lần nữa.

### 13.1. Retry có giới hạn cho `GET`

```java
import java.time.Duration;

import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class ReactiveProductReader {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> findStatus(String id) {
        return redis.opsForValue()
                .get("product:" + id + ":status")
                .retryWhen(
                        Retry.backoff(2, Duration.ofMillis(100))
                                .maxBackoff(Duration.ofSeconds(1))
                                .jitter(0.3)
                                .filter(ex ->
                                        ex instanceof RedisConnectionFailureException));
    }
}
```

Trong Reactor, `Retry.backoff(2, ...)` nghĩa là **tối đa 2 lần retry sau lượt gọi đầu**, khác với `maxAttempts(3)` của RetryTemplate ở ví dụ trước.

Nếu Redis key không tồn tại, publisher `Mono.empty()` hoàn tất bình thường; operator `retryWhen` không tự retry chỉ vì không có value.

### 13.2. Thận trọng với `INCR` và `retryWhen`

```java
// NGUY HIỂM NẾU KHÔNG CHỊU ĐƯỢC TĂNG TRÙNG:
return redis.opsForValue()
        .increment("counter:orders")
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
```

Một timeout hoặc mất connection sau khi Redis đã tăng counter có thể khiến lần subscribe tiếp theo gửi lại `INCR`.

### 13.3. Retry đúng phạm vi pipeline

```java
return redis.opsForValue()
        .get(key)
        .retryWhen(readRetryPolicy)
        .flatMap(value -> externalService.process(value));
```

Đặt `retryWhen` **trước** bước gọi service bên ngoài giúp giới hạn retry vào phần đọc Redis. Nếu đặt retry sau cả pipeline, lỗi từ `externalService.process` có thể làm upstream chạy lại, gây lặp những thao tác trước đó.

Ngược lại, nếu `externalService.process` có side effect nhưng caller cần retry nó, phải thiết kế policy idempotency riêng cho service ấy.

## 14. Tạo idempotency key cho nghiệp vụ không lũy đẳng

Để retry một thao tác như `INCRBY` mà không làm tăng hai lần, request cần có một **operation ID ổn định qua mọi lần retry**.

Ví dụ:

```text
Business request: điều chỉnh bộ đếm tồn kho
operationId = inventory-adjust-req-9f3a
counterKey  = stock:{sku42}:reserved
markerKey   = op:{sku42}:inventory-adjust-req-9f3a
delta       = +3
```

Ý tưởng:

1. Redis kiểm tra marker của operation ID.
2. Nếu marker đã tồn tại, trả lại kết quả đã ghi, không áp dụng thay đổi nữa.
3. Nếu marker chưa có, thực hiện thay đổi và ghi marker/kết quả **trong cùng một thao tác nguyên tử**.

Quan trọng: nếu Java thực hiện:

```java
if (!redis.hasKey(markerKey)) {
    redis.opsForValue().increment(counterKey, delta);
    redis.opsForValue().set(markerKey, "done");
}
```

thì đây là **ba lệnh riêng**. Hai request hoặc một retry có thể cùng thấy marker chưa tồn tại và đều increment trước khi marker được ghi. Ngoài ra một lỗi giữa increment và ghi marker có thể làm mất thông tin deduplication.

Cần dùng Lua script hoặc cơ chế đồng bộ nguyên tử phía Redis phù hợp.

## 15. Ví dụ Lua: `INCRBY` có kiểm tra request ID

Ví dụ script minh họa một counter và một marker cùng hash slot. Script nhận:

```text
KEYS[1] = stock:{sku42}:reserved
KEYS[2] = op:{sku42}:inventory-adjust-req-9f3a
ARGV[1] = "3"       -- delta
ARGV[2] = "86400"   -- thời hạn giữ marker, giây
```

Mã Lua:

```lua
-- KEYS[1]: counter key
-- KEYS[2]: idempotency marker có thể lưu kết quả
-- ARGV[1]: delta theo cú pháp số nguyên Redis
-- ARGV[2]: marker TTL tính bằng giây

local prior = redis.call('GET', KEYS[2])
if prior then
    return tonumber(prior)
end

local ttl = tonumber(ARGV[2])
if ttl == nil or ttl <= 0 or ttl % 1 ~= 0 then
    return redis.error_reply('ERR invalid marker TTL')
end

-- Kiểm tra dữ liệu cơ bản trước khi ghi.
if string.match(ARGV[1], '^%-?%d+$') == nil then
    return redis.error_reply('ERR invalid delta')
end

local counterType = redis.call('TYPE', KEYS[1]).ok
local markerType = redis.call('TYPE', KEYS[2]).ok
if counterType ~= 'none' and counterType ~= 'string' then
    return redis.error_reply('ERR counter wrong type')
end
if markerType ~= 'none' and markerType ~= 'string' then
    return redis.error_reply('ERR marker wrong type')
end

-- Redis tự kiểm tra overflow của INCRBY.
local value = redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], tostring(value), 'EX', ttl)
return value
```

Khi script được thực hiện liên tục trên cùng primary, không có command từ client khác xen vào giữa các bước của script. Nếu Redis trả kết quả thành công nhưng response mất, lượt gọi lại với cùng marker thường sẽ thấy `prior` và trả cùng giá trị thay vì tăng tiếp.

### Giới hạn của ví dụ

Đây là **mẫu tư duy idempotency trong Redis**, không phải cam kết exactly-once tuyệt đối:

- Marker có TTL: sau khi marker hết hạn, retry quá muộn có thể thực hiện lại operation.
- Redis Cluster yêu cầu các key liên quan cùng hash slot; ví dụ dùng cùng tag `{sku42}`.
- Nếu script có lỗi sau lệnh `INCRBY` nhưng trước lúc marker được lưu, Redis Lua **không tự rollback** lệnh đã hoàn tất. Cần prevalidate kỹ dữ liệu, phân quyền/lỗi tài nguyên, và có quy trình khôi phục cho trường hợp thất bại một phần.
- Redis replication/failover bất đồng bộ có thể mất cả thay đổi counter hoặc marker chưa được replica nhận; script atomically trên primary không thay thế durability.
- Nếu request mới dùng lại `operationId` cũ cho delta khác, kết quả bị hiểu sai. ID phải duy nhất theo **logical operation**; mọi lần retry của cùng operation dùng đúng payload.
- Sử dụng `tonumber(prior)` để trả integer qua Lua cần chú ý độ chính xác với số rất lớn; với dữ liệu ngoài giới hạn số nguyên chính xác của Lua, cần thiết kế kết quả theo chuỗi hoặc cách biểu diễn khác.
- Nếu giữ marker cho hàng triệu request, cần dự toán RAM, TTL và thời gian retry/duplicate-delivery tối đa.

### Spring Data Redis gọi script

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

public class StockCounterService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> incrementOnceScript;

    public StockCounterService(
            StringRedisTemplate redis,
            RedisScript<Long> incrementOnceScript) {
        this.redis = redis;
        this.incrementOnceScript = incrementOnceScript;
    }

    public Long incrementOnce(
            String sku,
            String operationId,
            long delta) {

        String tag = "{" + sku + "}";
        String counterKey = "stock:" + tag + ":reserved";
        String markerKey = "op:" + tag + ":" + operationId;

        return redis.execute(
                incrementOnceScript,
                List.of(counterKey, markerKey),
                Long.toString(delta),
                "86400"
        );
    }
}
```

`incrementOnceScript` là bean `RedisScript<Long>` nạp script Lua trên, ví dụ từ `ClassPathResource` và đặt `setResultType(Long.class)`.

Trước khi gọi, phải validate `sku` và `operationId` để không cho client tùy ý chọn namespace/hash tag hoặc truyền chuỗi bất thường, và phải bảo đảm operation ID được tạo **một lần khi bắt đầu nghiệp vụ**, không tạo UUID mới trong mỗi lượt retry.

Nếu retry sau một lỗi có thể chứng minh marker vẫn còn, script mới là thành phần giúp giảm trùng; **chỉ gắn `RetryTemplate` vào `INCRBY` thông thường không có hiệu quả bảo vệ như vậy**.

## 16. Idempotency key cần lưu những thông tin nào?

Một marker tốt không chỉ có chuỗi `done` nếu caller còn cần biết kết quả của lần thực hiện đầu.

Hợp đồng có thể gồm:

| Field hoặc dữ liệu | Mục đích |
| --- | --- |
| `operationId` | Định danh bất biến của logical operation. |
| `requestHash` hoặc payload fingerprint | Ngăn tái sử dụng cùng ID với tham số khác. |
| `status` | `PROCESSING`, `COMPLETED` hoặc trạng thái tương đương nếu có workflow nhiều bước. |
| `result` | Trả kết quả nhất quán khi caller retry sau mất response. |
| `createdAt`/`expiresAt` | Quản lý thời hạn idempotency. |
| `owner/version` nếu cần | Phục vụ kiểm soát tranh chấp và cập nhật có điều kiện. |

Nếu dùng một Redis script cập nhật counter ngay và lưu marker, có thể đơn giản hơn workflow nhiều bước. Nhưng với nghiệp vụ gọi SQL hoặc HTTP trong lúc xử lý, **không thể dùng một Lua script để atomically commit Redis cùng hệ thống bên ngoài**.

Khi cần xử lý end-to-end:

- Chọn một nguồn sự thật giao dịch, ví dụ database có unique constraint theo operation ID.
- Dùng transactional outbox để phát sự kiện sau khi business transaction được commit.
- Thiết kế consumer idempotent theo event ID.
- Chỉ ACK khi kết quả nghiệp vụ đã được ghi bền vững.
- Tách retry của Redis cache khỏi retry business transaction để không nhân đôi side effect ngoài Redis.

## 17. Timeout, failover và độ bền: biết giới hạn của idempotency

Ngay cả khi dùng marker:

```text
Primary Redis:
  INCRBY counter thành công
  SET marker thành công
  client nhận lỗi mạng

Replica:
  chưa nhận phần cập nhật mới nhất

Primary lỗi:
  replica được promote, thiếu counter/marker cuối
```

Sau failover, retry có thể chạy lại vì marker không có trên primary mới. Điều này cho thấy **tính nguyên tử trong một Redis primary không tự bảo đảm tính bền vững trên toàn topology**.

Các cơ chế như AOF, RDB, replication, `WAIT` hay sự lựa chọn Redis deployment giúp thay đổi mức rủi ro mất dữ liệu, nhưng không tự tạo distributed exactly-once giữa Redis và một hệ thống khác.

### Khi nào dùng `WAIT`?

`WAIT` có thể cho caller chờ một số replica xác nhận tiến độ replication cho những ghi trước đó trên **cùng connection** theo semantics của Redis. Nhưng:

- Không bảo đảm zero data loss trong mọi failover.
- Không chứng minh fsync bền vững trên replica.
- Khi Spring template dùng connection pool/transaction, không được giả định một `WAIT` tách riêng sẽ luôn gắn đúng lịch sử ghi của connection trước đó.

Vì vậy `WAIT` là một lựa chọn giảm rủi ro trong kiến trúc có thiết kế riêng, không phải thuốc chữa cho retry không lũy đẳng.

## 18. Retry theo ngân sách: số lần, backoff, jitter và deadline

Retry vô hạn gây ba vấn đề:

1. Redis đang lỗi lại nhận thêm nhiều lệnh, khiến phục hồi chậm hơn.
2. API/request vượt deadline, giữ nhiều luồng hoặc pipeline chờ.
3. Non-idempotent operation có nguy cơ thực hiện nhiều lần hơn.

Một policy giới hạn điển hình:

```text
Lượt 1: gọi ngay
Lỗi transient:
  đợi 100 ms + jitter
Lượt 2: gọi lại
Lỗi transient:
  đợi 200 ms + jitter
Lượt 3: gọi lại
Nếu vẫn lỗi -> trả lỗi hoặc fallback theo hợp đồng
```

Nên chọn:

- **Max attempts** nhỏ và xác định theo thao tác.
- **Exponential backoff** để hạn chế retry storm.
- **Jitter** để tránh nhiều client retry đồng thời.
- **Timeout/deadline tổng** cho toàn request, không chỉ từng command.
- **Circuit breaker/bulkhead** nếu Redis suy yếu kéo dài.
- **Concurrency limits** để nhiều request không nhân tải lên Redis.
- **Metrics** phân biệt lần gọi đầu và số lần retry.

Với một API HTTP có deadline 500 ms, cấu hình ba lần timeout 1 giây cộng backoff là vô nghĩa: request có thể hết thời gian từ lâu trước khi policy hoàn tất.

Không tự retry ở cả tầng driver, service và gateway mà không kiểm soát tổng ngân sách. **Retry lồng nhau** có thể khiến một request gửi rất nhiều command dù từng tầng chỉ retry 2–3 lần.

## 19. Retry đúng transaction boundary

Ví dụ dễ mắc lỗi:

```java
@Retryable
@Transactional
public void createOrderAndUpdateCounter(Order order) {
    orderRepository.save(order);
    redis.opsForValue().increment("orders:count");
    emailSender.sendConfirmation(order);
}
```

Nếu lỗi Redis xảy ra sau khi database đã commit một phần ở workflow thực tế, hoặc lỗi email xảy ra sau khi Redis tăng, retry toàn bộ method có thể dẫn tới:

- Lưu đơn hàng trùng hoặc gặp unique constraint.
- Tăng bộ đếm nhiều lần.
- Gửi nhiều email.
- Trạng thái giữa database và Redis không nhất quán.

Ví dụ chỉ minh họa rủi ro phạm vi; thứ tự commit/rollback cụ thể phụ thuộc cách transaction proxy và các lời gọi ngoài transaction hoạt động.

Không coi `@Transactional` là giải pháp tự động làm SQL + Redis + email thành một transaction phân tán.

Thay vào đó:

- Giới hạn retry quanh lệnh phù hợp về idempotency.
- Với tác dụng phụ quan trọng, thiết kế business operation có ID cố định.
- Dùng database unique constraint/outbox để tách commit nghiệp vụ và chuyển sự kiện.
- Dùng consumer idempotent và ACK/retry theo contract.
- Với Redis cache, có thể chấp nhận miss/fallback, không nên làm mất transaction nghiệp vụ chỉ vì cache tạm thời không truy cập được nếu không cần thiết.

## 20. Kiểm thử retry phải mô phỏng “đã chạy nhưng mất response”

Một test chỉ giả lập “Redis báo lỗi trước khi chạy command” **không kiểm tra được rủi ro quan trọng nhất**. Cần thử trường hợp command đã thực thi nhưng response bị mất.

### 20.1. Test lệnh đọc

Một mock cho lượt GET đầu ném `RedisConnectionFailureException`, lượt sau trả value:

```text
GET lần 1 -> lỗi transient
GET lần 2 -> "ACTIVE"
Kỳ vọng:
  trả "ACTIVE"
  tổng số GET đúng bằng policy
  không có command ghi ngoài ý muốn
```

### 20.2. Test SET với state cố định

```text
SET status ACTIVE lần 1 -> Redis đã ghi nhưng client nhận lỗi
SET status ACTIVE lần 2 -> Redis nhận lệnh lại
Kỳ vọng:
  value cuối = ACTIVE
  nếu có TTL thì deadline theo hợp đồng đã chọn
```

Nếu một writer khác cập nhật state trong lúc retry, test phải thể hiện chính sách version/compare-and-set của ứng dụng, không chỉ kiểm tra value cuối với single writer.

### 20.3. Test INCR không có idempotency

```text
counter ban đầu = 7
INCR lần 1 thực thi -> 8, response bị mất
INCR lần 2 thực thi -> 9

Kỳ vọng test phát hiện:
  logical operation đã tăng hai lần
```

Đây là test minh họa **điều không được làm**.

### 20.4. Test INCR có operation marker

```text
counter ban đầu = 7
operationId = "req-42"

Script lần 1:
  counter -> 8
  marker req-42 -> result 8
  response bị mất

Script lần 2, cùng operationId:
  đọc marker -> 8
  không INCR
  trả 8

Kỳ vọng:
  counter cuối = 8
  hai lượt có cùng logical result
```

Bổ sung test:

- Cùng operation ID nhưng payload khác phải bị từ chối theo contract.
- Marker hết hạn rồi có retry muộn: phải biết hệ thống chấp nhận rủi ro nào.
- Song song hai request cùng ID: chỉ một được thực hiện theo cơ chế nguyên tử.
- Redis Cluster: counter và marker nằm cùng hash slot.
- Failover trong khoảng thực thi: đánh giá khả năng mất marker và dữ liệu.
- Lỗi script xảy ra sau một thay đổi: có kế hoạch recovery/đối soát.

### 20.5. Test trong Spring với `StepVerifier`

Đối với reactive GET retry, có thể dùng Reactor Test:

```java
StepVerifier.create(reader.findStatus("42"))
        .expectNext("ACTIVE")
        .verifyComplete();
```

`StepVerifier` subscribe vào publisher nên command thật sự được kích hoạt. Dùng mock hoặc Redis thử nghiệm riêng để kiểm tra số lần subscription và lỗi transient. Không kết luận rằng policy idempotent đã đúng chỉ từ một happy-path test.

Với integration test Redis, không cố ý cắt mạng hoặc kill primary trên môi trường production. Dùng Testcontainers/lab để mô phỏng mất kết nối và một proxy có thể chặn response sau khi command đã đi tới Redis, nếu cần đánh giá failure mode chính xác.

## 21. Khi mất kết quả của command, có nên đọc lại để xác minh?

Có thể, nhưng cần hiểu hạn chế.

Ví dụ `SET key ACTIVE` timeout. Sau đó `GET key` trả `ACTIVE`. Điều này xác nhận **tại thời điểm GET**, state là ACTIVE; nó không chứng minh command timeout ban đầu là lệnh duy nhất đã ghi state, nhất là khi có nhiều writer.

Ví dụ `INCR` timeout. Nếu đọc counter mới là 9, ứng dụng không thể suy ra mình đã tăng hay request khác tăng, trừ khi có operation ID/marker, version hoặc nguồn dữ liệu đối soát.

Với `SET NX`, đọc token để xác minh có thể giúp xác định owner tạm thời, nhưng TTL/failover và owner rotation vẫn làm việc xác minh đơn giản không đủ cho lock có mức tin cậy cao.

**Read-after-error là một quan sát mới**, không phải một rollback hay xác nhận chính xác của lệnh trước đó.

## 22. Mối liên hệ với Redis Streams consumer group

Redis Streams quản lý pending/ACK để hỗ trợ xử lý công việc khi consumer crash:

```text
XREADGROUP -> message được giao, thêm PEL
worker xử lý nghiệp vụ
XACK -> gỡ message khỏi PEL
```

Nếu handler đã hoàn thành nhưng `XACK` timeout, một lượt `XACK` nữa có thể trả 0 vì record đã ACK. Điều này có thể **phù hợp với mục tiêu cuối là không còn pending**, nhưng không bảo đảm handler chỉ chạy một lần nếu message được claim và xử lý lại trước đó.

Phải tách:

- Retry **XACK** cho cùng stream/group/record ID.
- Retry **xử lý nghiệp vụ** khi message chưa ACK.
- Tính idempotent của tác dụng phụ bên ngoài như ghi SQL hoặc gửi email.

Consumer group không tự cung cấp exactly-once ở cấp ứng dụng. Cần event ID, unique constraint hoặc idempotency table nếu tác vụ có tác dụng phụ quan trọng.

## 23. Quan sát và cảnh báo retry trong vận hành

Các metric nên có:

| Metric | Ý nghĩa |
| --- | --- |
| `redis_command_attempts_total{operation}` | Bao nhiêu lần gọi, gồm retry. |
| `redis_command_retries_total{operation,reason}` | Những operation nào đang retry nhiều. |
| `redis_command_failed_total{operation,reason}` | Số operation thất bại sau policy. |
| `redis_retry_delay_seconds` | Tổng thời gian backoff và ảnh hưởng tới latency. |
| `redis_ambiguous_write_total{operation}` | Số trường hợp client không biết lệnh ghi đã chạy chưa. |
| `idempotency_marker_hit_total{operation}` | Số lần retry/dedup đọc thấy marker trước đó. |
| `idempotency_conflict_total` | Cùng operation ID nhưng tham số khác, cần điều tra. |
| `redis_connection_failure_total` | Kết nối bất ổn, cần phân tích nguyên nhân gốc. |
| `redis_failover_total` | Thay đổi primary/topology liên quan đến retry. |
| `business_duplicate_suppressed_total` | Số tác dụng phụ trùng bị chặn ở business layer. |

Đây là những tên metric đề xuất, không phải metric Spring Data Redis tự sinh đầy đủ. Cần triển khai instrumentation phù hợp và giới hạn label cardinality; **không gắn raw operation ID hoặc Redis key vào metric label** vì số lượng giá trị có thể tăng vô hạn và làm lộ thông tin nhạy cảm.

Một ngưỡng cảnh báo retry tăng mạnh thường có ích hơn việc chỉ nhìn tỷ lệ request HTTP 500: hệ thống có thể trả thành công sau ba lượt Redis command nhưng đang chịu tải gấp nhiều lần.

Khi retry tăng bất thường, điều tra theo thứ tự: Redis latency, kết nối, CPU, memory, persistence/I/O, replication/failover, topology, số request và chính sách retry các tầng.

## 24. Checklist thiết kế một thao tác Redis có retry

Trước khi đưa retry vào một method service, trả lời:

1. Lệnh Redis thực tế là gì? Có script, side effect hoặc command ngầm nào không?
2. Nếu lệnh chạy **hai lần với tham số y hệt**, state cuối có khác không?
3. TTL, expiration, version hoặc return value có khác không?
4. Nếu client khác ghi/xóa giữa hai lượt, retry có đè hoặc xóa dữ liệu mới không?
5. Khi response mất, có cách nào xác định operation đã hoàn tất mà không tạo side effect thêm không?
6. Operation ID có ổn định qua mọi lượt retry không?
7. Có cần lưu result/fingerprint và TTL của idempotency marker không?
8. Nếu script lỗi giữa các lệnh, có thao tác đã ghi mà không có rollback không?
9. Có cần Redis Cluster same-slot cho các key phối hợp không?
10. Redis failover có thể làm mất marker hoặc ghi cuối chưa replicate không?
11. Exception nào thực sự transient? Exception nào là lỗi logic/cấu hình?
12. Max attempts, backoff, jitter và tổng request deadline là bao nhiêu?
13. Có tầng khác đang retry cùng operation không?
14. Người dùng có bấm lại request hoặc gateway có replay POST không?
15. Cần metric, log, alert và reconciliation nào để phát hiện duplicate?
16. Nếu nghiệp vụ thất bại sau khi một Redis operation thành công, có cần transaction/outbox ở nguồn dữ liệu khác không?

Chỉ khi trả lời được các câu hỏi cốt lõi mới nên bật automatic retry.

## 25. Các lỗi tư duy thường gặp

**“Lỗi timeout nghĩa là lệnh chưa chạy.”**  
Không. Redis có thể đã thực thi nhưng response bị mất.

**“`SET` luôn idempotent.”**  
Không ở mọi ngữ cảnh: TTL có thể bị reset, writer khác có thể bị ghi đè, và output/side effect cấp ứng dụng có thể khác.

**“`DEL` idempotent nên retry bao nhiêu lần cũng được.”**  
Không. Key có thể được tạo lại giữa các lượt và bị xóa nhầm.

**“Lệnh đọc retry không thể gây sai.”**  
Lệnh đọc không sửa Redis, nhưng kết quả retry có thể đến từ trạng thái mới, replica trễ hoặc ảnh chụp không nhất quán. Timeout/retry còn tăng tải.

**“`SET NX` trả false nghĩa là request đầu chưa tạo key.”**  
Không. Request đầu có thể đã tạo key nhưng mất response; retry thấy key đã tồn tại.

**“`XADD *` retry chỉ gửi lại cùng record.”**  
Không. Thường mỗi lượt sinh stream ID mới và tạo record mới.

**“Redis transaction hoặc Lua tự rollback khi có lỗi.”**  
Không như SQL transaction. Redis không tự hoàn tác mọi lệnh đã thực hiện trong một script nếu lệnh sau lỗi.

**“Spring Retry làm mọi thao tác Redis an toàn.”**  
Không. RetryTemplate/@Retryable chỉ lặp lời gọi; idempotency vẫn do operation và nghiệp vụ quyết định.

**“Reactive `retryWhen` chỉ lấy lại response cũ.”**  
Không. Nó subscribe lại upstream và thường thực hiện Redis command một lần nữa.

**“Có idempotency marker thì đã đạt exactly-once trên mọi hệ thống.”**  
Không. Marker có TTL, có thể mất do failover, script có rủi ro lỗi từng bước và các hệ thống ngoài Redis không được commit nguyên tử.

**“Retry nhiều sẽ tăng độ tin cậy vô hạn.”**  
Không. Retry storm có thể khiến Redis suy yếu thêm và làm tăng rủi ro side effect trùng.

## 26. Bài thực hành theo từng command

Chỉ dùng Redis thử nghiệm và namespace `demo:retry:*`. Không thực hiện test gây duplicate trên dữ liệu nghiệp vụ thật.

### Bài A — So sánh `SET` và `INCR`

```redis
SET demo:retry:state ACTIVE
SET demo:retry:state ACTIVE
GET demo:retry:state

SET demo:retry:count 0
INCR demo:retry:count
INCR demo:retry:count
GET demo:retry:count
```

Kết quả: state vẫn ACTIVE, counter bằng 2. Từ đó phân biệt thao tác gán trạng thái và thao tác tăng tương đối.

### Bài B — Quan sát TTL được làm mới

```redis
SET demo:retry:ttl ACTIVE EX 60
TTL demo:retry:ttl
```

Sau một khoảng thời gian, thực hiện lại:

```redis
SET demo:retry:ttl ACTIVE EX 60
TTL demo:retry:ttl
```

TTL được làm mới gần 60 giây. Đây là lý do retry cùng value vẫn có thể thay đổi semantics của session/lease.

### Bài C — Kết quả `DEL` lần đầu và lần sau

```redis
SET demo:retry:del VALUE
DEL demo:retry:del
DEL demo:retry:del
```

Return lần đầu thường là 1, lần sau 0. Hai lần cho cùng state vắng mặt nhưng output không giống nhau.

### Bài D — `SET NX` và kết quả không rõ ràng

```redis
SET demo:retry:nx request-42 NX EX 60
SET demo:retry:nx request-42 NX EX 60
GET demo:retry:nx
```

Lượt đầu có thể trả OK, lượt sau nil; GET vẫn trả request-42. Trong thực tế, nếu response lượt đầu mất, không nên hiểu nil lượt hai là “request chưa ghi thành công”.

### Bài E — Gửi lại event Pub/Sub

Dùng một terminal subscribe `demo:retry:events` và một terminal khác thực hiện:

```redis
PUBLISH demo:retry:events event-42
PUBLISH demo:retry:events event-42
```

Subscriber đang online có thể nhận hai message. Redis không tự deduplication payload chỉ vì chuỗi message trùng nhau.

### Bài F — Mô phỏng phản hồi không đến

Tại môi trường lab, dùng một proxy test hoặc mock driver để:

1. Cho Redis thực hiện `INCR`.
2. Làm mất response tới client.
3. Kích hoạt retry không có marker và quan sát counter tăng hai lần.
4. Thay bằng script có idempotency marker cùng operation ID.
5. Lặp thử để quan sát marker ngăn cập nhật trùng trong cửa sổ TTL.
6. Kiểm tra khi marker hết hạn hoặc retry với operation ID khác.

Bài này không yêu cầu phá Redis process hay mất dữ liệu thật. Không tạo tình huống failover/cắt mạng trên production để kiểm thử.

## 27. Câu hỏi tự kiểm tra

1. Nếu `INCR` timeout, tại sao chạy lại cùng lệnh có thể làm sai counter?
2. Vì sao `SET key value` có thể lũy đẳng về value nhưng không lũy đẳng về TTL?
3. Một lệnh `DEL` đã thực hiện nhưng response mất; tại sao lượt retry có thể trả 0 mà vẫn đạt mục tiêu xóa?
4. Khi key bị tạo lại giữa hai lượt `DEL`, kết quả có thể sai thế nào?
5. `HSET`, `SADD` và `ZADD` đặt score cố định giống và khác nhau ra sao về trạng thái cuối và output?
6. Vì sao `SET NX` trả false ở lượt retry không chứng minh request đầu thất bại?
7. Khi nào nên tự động retry `GET` và vì sao vẫn cần giới hạn retry?
8. Redis command `GETEX` có thật sự read-only không?
9. Vì sao `XADD stream * ...` và `PUBLISH` không thể được retry mù?
10. Reactor `retryWhen` có tác động thế nào tới upstream Redis operation?
11. Tại sao nên đặt retry ở quanh lệnh `GET` thay vì quanh toàn bộ pipeline gọi external service?
12. Cần những key nào để dùng Lua giảm trùng `INCRBY`, và vì sao trong Redis Cluster chúng phải cùng hash slot?
13. Vì sao idempotency marker cần TTL đủ dài và operation ID bất biến qua retry?
14. Lua script có bảo đảm rollback nếu lệnh cuối lỗi không?
15. Tại sao replication/failover có thể khiến marker biến mất dù script đã trả thành công ở primary cũ?
16. Vì sao `WAIT` không phải đảm bảo exactly-once?
17. Khi gọi Redis trong một method `@Transactional`, vì sao retry toàn method có thể nhân đôi tác dụng phụ?
18. Một retry policy tốt cần phân loại lỗi và giới hạn tổng thời gian theo những yếu tố nào?
19. Vì sao cần test failure mode “server đã thực thi nhưng client không nhận response”?
20. Tại sao trạng thái Redis cuối cùng giống nhau không đủ để kết luận một business operation đã xử lý đúng một lần?

**Ghi nhớ:** Trong Spring Data Redis, quyết định retry phải dựa vào **tính lũy đẳng thực tế của từng Redis command trong ngữ cảnh nghiệp vụ**, không chỉ vào loại exception. Lệnh đọc thường có thể retry; lệnh gán trạng thái có thể retry có điều kiện; lệnh tăng, push/pop, stream append và publish có nguy cơ nhân đôi hiệu ứng. Với command không lũy đẳng, hãy dùng **operation ID ổn định, kiểm tra/dedup nguyên tử, retry có giới hạn và cơ chế khôi phục phù hợp**. Đừng nhầm atomicity của Lua, Redis replication hay Spring Retry với bảo đảm exactly-once end-to-end.

## Tài liệu tham khảo

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): cách gọi Redis operations và xử lý kết quả.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): chạy Lua script nguyên tử tại Redis.
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): Reactor Mono/Flux và reactive Redis operations.
- [Spring Retry — Reference](https://docs.spring.io/spring-retry/docs/current/reference/html/): chính sách retry, backoff và giới hạn lượt thử.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): retry/retryWhen và tác động subscribe lại upstream.
- [Redis — SET](https://redis.io/docs/latest/commands/set/): NX/XX, TTL và thao tác ghi theo điều kiện.
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): lệnh tăng bộ đếm nguyên tử.
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/): tạo stream entry và ID.
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/): cơ chế phát thông điệp Pub/Sub.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): truyền KEYS/ARGV và thực thi script.
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/): giới hạn dữ liệu khi failover bất đồng bộ.
