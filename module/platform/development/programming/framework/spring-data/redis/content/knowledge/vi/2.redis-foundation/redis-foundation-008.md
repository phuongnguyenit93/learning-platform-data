# Các nhóm lệnh cần biết để theo dõi ví dụ bằng redis-cli

## 1. Vì sao cần biết redis-cli khi học Spring Data Redis?

Khi ứng dụng Spring Boot gọi **StringRedisTemplate**, **RedisTemplate**, Spring Cache hoặc Redis Repository, các thao tác cuối cùng tác động tới **Redis Server**. Công cụ **redis-cli** cho phép gửi lệnh trực tiếp tới Redis và kiểm chứng trạng thái trên server.

Nhờ đó, bạn có thể trả lời những câu hỏi thực hành: ứng dụng vừa ghi khóa nào, lưu kiểu dữ liệu gì, giá trị là bao nhiêu, TTL còn lại thế nào, cache đã bị xóa chưa, một lần tăng bộ đếm có thực sự xảy ra, và tại sao một khóa đọc được từ Java nhưng lại không tìm thấy khi gõ lệnh trong CLI?

Mục tiêu bài học là nắm **những nhóm lệnh đủ để theo dõi ví dụ Spring Data Redis**, không phải học thuộc toàn bộ Redis command reference.

### Redis có nhiều kiểu giá trị khác nhau

| Kiểu Redis | Dữ liệu được lưu | Nhóm lệnh quen thuộc | API Spring Data Redis |
| --- | --- | --- | --- |
| String | Chuỗi bytes, gồm cả số nguyên biểu diễn dạng chuỗi | SET, GET, INCR | opsForValue() |
| Hash | Nhiều cặp field–value trong một key | HSET, HGET, HGETALL | opsForHash() |
| List | Danh sách có thứ tự, hỗ trợ thao tác đầu/cuối | LPUSH, RPUSH, LRANGE | opsForList() |
| Set | Thành viên duy nhất, không có thứ tự cố định | SADD, SISMEMBER, SMEMBERS | opsForSet() |
| Sorted Set | Thành viên duy nhất kèm score để xếp hạng | ZADD, ZRANGE, ZSCORE | opsForZSet() |
| Stream | Các bản ghi sự kiện có ID | XADD, XRANGE, XREAD | opsForStream() |

**EXISTS, TYPE, TTL, EXPIRE, DEL, SCAN** là các lệnh làm việc với key ở nhiều kiểu dữ liệu. Nên học chúng trước khi đi vào từng cấu trúc.

## 2. Kết nối và đọc đầu ra redis-cli

### 2.1. Khởi động

Giả sử Redis Server đã chạy trên máy local ở cổng 6379. Từ terminal hệ điều hành:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Sau khi vào CLI, gõ:

~~~text
PING
~~~

Phản hồi mong đợi:

~~~text
PONG
~~~

Nếu Redis đang chạy trong container có tên **redis**:

~~~bash
docker exec -it redis redis-cli
~~~

Tên container trong lệnh là ví dụ; hãy dùng đúng tên ở môi trường của bạn. Đối với Redis ở xa, có ACL hoặc TLS, cần cấu hình kết nối tương ứng. Không đặt mật khẩu thật trong tài liệu hoặc lệnh dễ bị lưu vào lịch sử terminal.

**Phân biệt hai cách chạy lệnh:**

~~~bash
# Cách 1: từ terminal hệ điều hành, chạy một lệnh rồi thoát
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

~~~text
# Cách 2: gõ trong chế độ tương tác, sau khi đã mở redis-cli
PING
SET lesson:cli:hello "Xin chao"
GET lesson:cli:hello
~~~

Trong các ví dụ tiếp theo, mỗi dòng lệnh Redis được thực thi **trong chế độ tương tác**. Dòng bắt đầu bằng dấu thăng trong khối minh họa chỉ dùng để giải thích và không cần nhập vào Redis.

### 2.2. Ý nghĩa đầu ra

| Đầu ra thường gặp | Cách hiểu |
| --- | --- |
| PONG | Redis đã phản hồi PING. |
| OK | Lệnh thực hiện thành công, thường gặp ở SET. |
| (integer) 1 | Giá trị số nguyên; ý nghĩa tùy lệnh, chẳng hạn số key tồn tại hoặc số phần tử thêm được. |
| "value" | Giá trị chuỗi ở dạng hiển thị mặc định. |
| (nil) | Không có giá trị, ví dụ GET một key không tồn tại. |
| (empty array) | Không có phần tử trong kết quả trả về. |
| (error) WRONGTYPE ... | Lệnh không phù hợp với kiểu dữ liệu của key. |

Với tùy chọn **--raw**, cách in đầu ra có thể thay đổi. Redis lưu dữ liệu dưới dạng bytes; hình thức hiển thị trong terminal không nhất thiết chính là nội dung gốc.

### 2.3. Chọn database và quy ước key

~~~text
SELECT 0
DBSIZE
~~~

Trong Redis standalone, SELECT chọn database logic; DBSIZE trả về số key của database hiện tại. **Redis Cluster chỉ dùng database 0 và không hỗ trợ SELECT để đổi database**; một số môi trường quản lý cũng giới hạn thao tác này.

Các ví dụ trong bài dùng tiền tố **lesson:cli:** để không trùng với key của ứng dụng khác. Chỉ thực hành trên môi trường học tập hoặc Redis mà bạn có quyền sửa dữ liệu.

## 3. Quản lý key: EXISTS, TYPE, TTL, EXPIRE, DEL và SCAN

### 3.1. Key có tồn tại và còn hạn sử dụng không?

~~~text
SET lesson:cli:welcome "Hello Redis" EX 120
EXISTS lesson:cli:welcome
TYPE lesson:cli:welcome
GET lesson:cli:welcome
TTL lesson:cli:welcome
PTTL lesson:cli:welcome
~~~

- **EXISTS key** trả 1 nếu key có tồn tại và 0 nếu không. Nếu truyền nhiều key, lệnh trả số key tồn tại.
- **TYPE key** cho biết string, hash, list, set, zset, stream hoặc none nếu không có key.
- **TTL key** trả số giây còn lại; **PTTL key** trả số mili giây còn lại.
- **SET ... EX 120** đặt TTL 120 giây ngay trong lệnh ghi.

Giá trị TTL đặc biệt:

| Giá trị | Ý nghĩa |
| --- | --- |
| -2 | Key không tồn tại hoặc đã hết hạn. |
| -1 | Key tồn tại nhưng không có TTL. |
| Số không âm | Khoảng thời gian còn lại; đơn vị phụ thuộc TTL hoặc PTTL. |

Khi đọc liên tiếp, TTL giảm theo thời gian; không phải lúc nào cũng thấy đúng 120 sau SET.

### 3.2. Đặt, gỡ TTL và xóa key

~~~text
SET lesson:cli:notice "short-lived"
TTL lesson:cli:notice
EXPIRE lesson:cli:notice 30
TTL lesson:cli:notice
PERSIST lesson:cli:notice
TTL lesson:cli:notice
DEL lesson:cli:notice
EXISTS lesson:cli:notice
~~~

**EXPIRE key seconds** đặt thời gian hết hạn cho key đang có. **PERSIST key** gỡ TTL. **DEL key** xóa key và trả số key đã xóa. **UNLINK key** cũng xóa key khỏi không gian tên, nhưng sử dụng cơ chế giải phóng bộ nhớ bất đồng bộ, hữu ích với dữ liệu lớn.

Một điều dễ bỏ qua: **SET key newValue** ghi đè String thường làm mất TTL cũ nếu không chỉ định tùy chọn giữ TTL. Vì vậy sau khi ghi cập nhật cache, nên kiểm tra lại TTL.

### 3.3. Tìm key khi chưa biết tên chính xác

~~~text
SCAN 0 MATCH lesson:cli:* COUNT 20
~~~

SCAN trả một **cursor cho lần gọi tiếp** và một danh sách key. Nếu cursor khác 0, chạy lại SCAN với cursor vừa nhận cho đến khi cursor trở về 0. COUNT là gợi ý về công việc mỗi lượt, không bảo đảm mỗi lượt trả đủ 20 phần tử. Một lượt có thể trả danh sách rỗng dù cursor chưa về 0.

Nếu gọi từ terminal hệ điều hành, lệnh tiện dụng là:

~~~bash
redis-cli --scan --pattern 'lesson:cli:*'
~~~

SCAN duyệt tăng dần, phù hợp hơn lệnh **KEYS** khi không gian key lớn. Kết quả SCAN không phải một snapshot nhất quán nếu dữ liệu thay đổi đồng thời; có thể gặp key trùng. **KEYS lesson:cli:* có thể chặn Redis khi số lượng key lớn**, nên tránh dùng để dò trên môi trường có tải cao.

**Không dùng FLUSHDB hoặc FLUSHALL trong bài học:** hai lệnh này xóa cả database hoặc toàn bộ các database, khác với DEL một key thử nghiệm.

## 4. Nhóm String: SET, GET, MGET và bộ đếm

String có thể chứa văn bản, JSON, bytes hoặc số nguyên biểu diễn dạng chuỗi.

~~~text
SET lesson:cli:siteName "Spring Data Redis"
GET lesson:cli:siteName
SET lesson:cli:color blue EX 60
GET lesson:cli:color
MGET lesson:cli:siteName lesson:cli:color lesson:cli:missing
~~~

**MGET** đọc nhiều key theo đúng thứ tự yêu cầu; key không tồn tại trả nil.

### Ghi có điều kiện

~~~text
SET lesson:cli:lock:42 owner-A NX EX 30
SET lesson:cli:lock:42 owner-B NX EX 30
GET lesson:cli:lock:42
~~~

**NX** chỉ cho phép SET khi key chưa tồn tại; lần ghi thứ hai sẽ không thay đổi giá trị nếu key vẫn còn. **XX** chỉ ghi khi key đã tồn tại. **EX** đặt hạn theo giây, **PX** theo mili giây. Đây mới là minh họa về ghi có điều kiện, chưa phải một hệ thống distributed lock an toàn đầy đủ: lock cần cơ chế nhận diện chủ sở hữu, giải phóng và xử lý lỗi.

### Tăng và giảm số nguyên

~~~text
SET lesson:cli:views:42 0
INCR lesson:cli:views:42
INCRBY lesson:cli:views:42 5
DECR lesson:cli:views:42
GET lesson:cli:views:42
~~~

Kết quả cuối là chuỗi **"5"**, tính từ 0 + 1 + 5 - 1. **INCR**, **INCRBY**, **DECR** là thao tác nguyên tử ở cấp từng lệnh và hữu ích cho bộ đếm. Nếu value chứa chữ không biểu diễn số nguyên hợp lệ, INCR báo lỗi. Một chuỗi gồm nhiều lệnh, ví dụ INCR rồi EXPIRE để làm rate limit, **không tự nguyên tử** chỉ vì INCR nguyên tử.

Liên hệ Java:

~~~java
stringRedisTemplate.opsForValue()
    .set("lesson:cli:color", "blue", Duration.ofSeconds(60));

String color = stringRedisTemplate.opsForValue()
    .get("lesson:cli:color");

Long views = stringRedisTemplate.opsForValue()
    .increment("lesson:cli:views:42");
~~~

Đoạn mã giả định có bean **StringRedisTemplate** được inject và import **java.time.Duration**. Lệnh kiểm tra phù hợp là GET, TYPE và TTL.

## 5. Nhóm Hash: HSET, HGET, HGETALL

Hash lưu các field bên trong một key. Ví dụ, **lesson:cli:product:42** là một key có các field name, stock, category. Mỗi field không phải một Redis key riêng.

~~~text
HSET lesson:cli:product:42 name "Redis Handbook" stock 8 category books
TYPE lesson:cli:product:42
HGET lesson:cli:product:42 name
HMGET lesson:cli:product:42 name stock missing
HGETALL lesson:cli:product:42
HEXISTS lesson:cli:product:42 stock
HLEN lesson:cli:product:42
HINCRBY lesson:cli:product:42 stock -2
HGET lesson:cli:product:42 stock
~~~

| Lệnh | Công dụng |
| --- | --- |
| HSET key field value | Thêm hoặc cập nhật field; có thể ghi nhiều cặp field–value. |
| HGET key field | Lấy một giá trị theo field. |
| HMGET key field ... | Lấy nhiều field; field thiếu trả nil. |
| HGETALL key | Lấy toàn bộ field–value. |
| HEXISTS key field | Kiểm tra field. |
| HINCRBY key field n | Tăng/giảm một field số nguyên. |
| HDEL key field ... | Xóa field. |
| HLEN key | Đếm field. |
| HSCAN key cursor ... | Duyệt field theo từng phần. |

Không giả định thứ tự field của HGETALL là cố định. Với Hash lớn, đọc một field bằng HGET hoặc một nhóm field bằng HMGET thường phù hợp hơn lấy toàn bộ.

Trong Spring Data Redis, các thao tác này được cung cấp qua **redisTemplate.opsForHash()**: put, get, multiGet, entries, increment... Dữ liệu hiển thị bằng CLI phụ thuộc serializer của Hash key và Hash value.

## 6. Nhóm List: LPUSH, RPUSH, LRANGE, LPOP

Redis List có thứ tự. **LPUSH** thêm ở đầu, **RPUSH** thêm ở cuối; **LPOP** và **RPOP** vừa đọc vừa loại bỏ phần tử.

~~~text
RPUSH lesson:cli:jobs job-A job-B job-C
TYPE lesson:cli:jobs
LLEN lesson:cli:jobs
LRANGE lesson:cli:jobs 0 -1
LPUSH lesson:cli:jobs urgent-job
LRANGE lesson:cli:jobs 0 -1
LPOP lesson:cli:jobs
RPOP lesson:cli:jobs
LRANGE lesson:cli:jobs 0 -1
~~~

Sau RPUSH, List gồm **job-A, job-B, job-C** theo thứ tự. LPUSH thêm **urgent-job** ở đầu. LRANGE với chỉ số **0 -1** trả toàn bộ phần tử; chỉ số **-1** đại diện phần tử cuối. **LLEN** trả độ dài. **LTRIM key start stop** giữ lại một đoạn List và bỏ phần còn lại.

Redis có thao tác blocking, ví dụ:

~~~text
BLPOP lesson:cli:emptyQueue 2
~~~

Lệnh chờ phần tử ở đầu List trong tối đa **2 giây** rồi trả về nếu không có dữ liệu. Khi học, nên dùng timeout hữu hạn để CLI không đứng chờ mãi. List phù hợp cho một số trường hợp hàng đợi đơn giản nhưng không tự mang cơ chế xử lý tin cậy, xác nhận và retry như một queue chuyên dụng.

Liên hệ Java: **opsForList().leftPush**, **rightPush**, **range**, **leftPop**, **rightPop**.

## 7. Nhóm Set: SADD, SMEMBERS, SISMEMBER

Set chứa các phần tử **duy nhất** và **không có thứ tự cố định**.

~~~text
SADD lesson:cli:tags java spring redis java
TYPE lesson:cli:tags
SMEMBERS lesson:cli:tags
SCARD lesson:cli:tags
SISMEMBER lesson:cli:tags redis
SISMEMBER lesson:cli:tags python
SREM lesson:cli:tags spring
SMEMBERS lesson:cli:tags
~~~

Trong SADD đầu tiên, **java** được truyền hai lần nhưng chỉ xuất hiện một lần trong Set. **SISMEMBER** trả 1 nếu member có mặt, 0 nếu không. **SCARD** trả số phần tử. **SREM** loại member.

Các phép tập hợp:

~~~text
SADD lesson:cli:team:A alice bob
SADD lesson:cli:team:B bob carol
SINTER lesson:cli:team:A lesson:cli:team:B
SUNION lesson:cli:team:A lesson:cli:team:B
SDIFF lesson:cli:team:A lesson:cli:team:B
~~~

**SINTER** là giao (ở đây có bob), **SUNION** là hợp, **SDIFF** là hiệu. Không dựa vào thứ tự hiển thị SMEMBERS khi so sánh kết quả. Có thể dùng **SSCAN** để duyệt Set lớn theo từng lượt.

Liên hệ Java: **opsForSet().add**, **isMember**, **members**, **intersect**, **union**.

## 8. Nhóm Sorted Set: ZADD, ZRANGE, ZSCORE

**Sorted Set** (ZSet) lưu mỗi member duy nhất kèm một score dạng số. Thứ tự được xác định chủ yếu theo score; khi bằng score, Redis áp dụng quy tắc so sánh member. Dạng này rất hợp với bảng xếp hạng.

~~~text
ZADD lesson:cli:leaderboard 150 user:1 230 user:2 200 user:3
TYPE lesson:cli:leaderboard
ZRANGE lesson:cli:leaderboard 0 -1 WITHSCORES
ZRANGE lesson:cli:leaderboard 0 1 REV WITHSCORES
ZSCORE lesson:cli:leaderboard user:2
ZREVRANK lesson:cli:leaderboard user:2
ZINCRBY lesson:cli:leaderboard 25 user:1
ZCARD lesson:cli:leaderboard
~~~

- **ZADD key score member** thêm hoặc cập nhật score.
- **ZRANGE ... WITHSCORES** đọc phần tử theo score tăng dần.
- **ZRANGE ... REV WITHSCORES** đọc theo chiều giảm dần để xem top cao nhất (cú pháp REV cần Redis phiên bản hỗ trợ).
- **ZSCORE** lấy score; **ZINCRBY** cộng thêm vào score thay vì đặt mới.
- **ZRANK** lấy vị trí tăng dần; **ZREVRANK** lấy vị trí giảm dần.
- **ZCARD** trả số member.

Chỉ số rank bắt đầu từ **0**, nên phần tử đứng đầu có ZREVRANK bằng 0, dù giao diện người dùng thường hiển thị hạng 1.

Liên hệ Java: **opsForZSet().add**, **reverseRangeWithScores**, **score**, **incrementScore**.

## 9. Nhóm Stream: XADD, XRANGE, XREAD

Redis Streams lưu các **entry có ID** cùng một số cặp field–value. Không nhầm Stream với List hoặc Pub/Sub: Stream cho phép đọc lại bản ghi theo ID và hỗ trợ consumer group.

### 9.1. Thêm và xem bản ghi

~~~text
XADD lesson:cli:events * type created productId 42
XADD lesson:cli:events * type updated productId 42
TYPE lesson:cli:events
XLEN lesson:cli:events
XRANGE lesson:cli:events - +
XREVRANGE lesson:cli:events + - COUNT 1
XREAD COUNT 10 STREAMS lesson:cli:events 0-0
~~~

Ký tự **\*** trong XADD yêu cầu Redis tự sinh ID. ID thường có dạng thời gian–số thứ tự, thay đổi theo lúc ghi. **XRANGE key - +** trả các entry từ ID nhỏ nhất đến lớn nhất; **XREVRANGE ... COUNT 1** xem entry mới nhất. **XLEN** là số entry hiện có. **XREAD ... 0-0** đọc những entry có ID lớn hơn 0-0, với giới hạn COUNT 10 trong ví dụ.

### 9.2. Xem consumer group

~~~text
XGROUP CREATE lesson:cli:events lesson-workers 0
XREADGROUP GROUP lesson-workers worker-1 COUNT 10 STREAMS lesson:cli:events >
XPENDING lesson:cli:events lesson-workers
XINFO GROUPS lesson:cli:events
~~~

- **XGROUP CREATE** tạo group. Dùng ID 0 để nhóm có thể bắt đầu từ các entry cũ.
- Trong **XREADGROUP**, ký tự **>** yêu cầu entry mới chưa được giao cho consumer nào trong group.
- **XPENDING** cho biết trạng thái các entry đã giao mà chưa được xác nhận.
- **XINFO GROUPS** xem thông tin các group trên stream.

Sau khi xử lý thành công, consumer xác nhận bằng **XACK** kèm đúng ID thực tế đã đọc:

~~~text
XACK lesson:cli:events lesson-workers 1730000000000-0
~~~

ID trong lệnh trên **chỉ để minh họa định dạng**; cần thay bằng ID từ kết quả XREADGROUP trên Redis của bạn. XACK đánh dấu đã xử lý trong group, **không xóa entry khỏi Stream**. Muốn xóa hoặc giới hạn retention phải chủ động dùng các cơ chế như XDEL hoặc XTRIM tùy thiết kế.

Liên hệ Java: **opsForStream()** cung cấp API thêm, đọc, quản lý group và acknowledge message.

## 10. Nhóm Pub/Sub: SUBSCRIBE và PUBLISH

Pub/Sub gửi thông điệp tới các subscriber **đang đăng ký**. Channel không phải key dữ liệu, vì vậy không dùng GET hoặc TTL để đọc channel.

Mở hai cửa sổ terminal kết nối cùng một Redis Server.

**Terminal A:**

~~~text
SUBSCRIBE lesson:cli:notifications
~~~

**Terminal B:**

~~~text
PUBLISH lesson:cli:notifications "product-updated:42"
~~~

Terminal A thấy nội dung được phát. Giá trị số từ PUBLISH cho biết số subscriber nhận được theo cách Redis đếm ở thời điểm đó; nếu chưa có ai đăng ký, thường là 0.

Pub/Sub **không lưu thông điệp để subscriber đến muộn đọc lại**. Với yêu cầu cần lưu và xử lý sau khi client offline, hãy cân nhắc Stream hoặc message broker phù hợp.

Trong Spring Data Redis có thể phát sự kiện qua **convertAndSend(...)** và nhận qua **RedisMessageListenerContainer**.

## 11. Nhóm transaction: MULTI, EXEC, WATCH

Khi gặp ví dụ Redis cần kết hợp nhiều lệnh, hãy nhận biết cú pháp:

~~~text
MULTI
SET lesson:cli:txn:state ready
INCR lesson:cli:txn:count
EXEC
GET lesson:cli:txn:state
GET lesson:cli:txn:count
~~~

- **MULTI** bắt đầu xếp các lệnh vào hàng đợi.
- Phản hồi **QUEUED** nghĩa là lệnh chưa thực thi ngay.
- **EXEC** thực thi các lệnh theo thứ tự; **DISCARD** hủy hàng đợi trước khi thực thi.
- **WATCH key** theo dõi key để kiểm soát xung đột theo optimistic concurrency trước EXEC.

Redis không cho client khác chen lệnh vào giữa chuỗi lệnh của một EXEC, nhưng **không tự rollback toàn bộ các thao tác đã thực thi** khi phát sinh lỗi ở thời điểm thực thi. Đây cũng không phải transaction chung với database quan hệ ở Spring Boot. Nếu một quy tắc cần nhiều thao tác Redis nguyên tử, có thể cần Lua script hoặc thiết kế lệnh chuyên biệt.

## 12. Nhóm kiểm tra sức khỏe và trạng thái server

| Lệnh | Quan sát | Lưu ý |
| --- | --- | --- |
| PING | Server có phản hồi | Chỉ chứng minh khả năng phản hồi ở thời điểm gọi. |
| DBSIZE | Số key trong DB hiện tại | Bao gồm cả key của ứng dụng khác cùng DB. |
| INFO keyspace | Thống kê số key và expiration theo DB | Không trả giá trị của key. |
| INFO memory | Bộ nhớ Redis sử dụng | Hữu ích khi nghiên cứu áp lực bộ nhớ. |
| INFO stats | Bộ đếm lệnh, hit/miss và chỉ số tổng | Thường là số liệu tích lũy, cần đo chênh lệch theo thời gian. |
| CLIENT LIST | Kết nối client | Có thể yêu cầu quyền ACL. |
| SLOWLOG GET 10 | Các lệnh được ghi nhận chậm | Có thể chứa đối số nhạy cảm, chỉ dùng khi được phép. |

Các lệnh đơn giản trong môi trường học:

~~~text
PING
DBSIZE
INFO keyspace
INFO memory
~~~

**MONITOR** có thể phát trực tiếp luồng lệnh Redis, nhưng tạo thêm tải và có thể phơi bày thông tin nhạy cảm. Không bật MONITOR trong production chỉ để theo dõi một bài học.

## 13. Đối chiếu RedisTemplate với redis-cli

Nếu ứng dụng dùng serializer dạng chuỗi, bạn có thể bắt đầu kiểm tra theo bảng sau:

| Thao tác Spring Data Redis | Ý nghĩa tương ứng trong Redis | Kiểm chứng bằng CLI |
| --- | --- | --- |
| opsForValue().set(key, value) | SET | GET key, TYPE key |
| opsForValue().set(key, value, timeout) | SET kèm TTL | GET key, TTL key |
| opsForValue().increment(key) | INCR | GET key |
| opsForHash().put(key, field, value) | HSET | HGET key field, HGETALL key |
| opsForList().rightPush(key, value) | RPUSH | LRANGE key 0 -1 |
| opsForSet().add(key, member) | SADD | SMEMBERS key |
| opsForZSet().add(key, member, score) | ZADD | ZRANGE key 0 -1 WITHSCORES |
| opsForStream().add(...) | XADD | XRANGE key - + |
| delete(key) | Xóa key | EXISTS key |
| expire(key, duration) | Gán expiration | TTL key, PTTL key |

Bảng trên là **ánh xạ ý nghĩa**, không khẳng định mọi lời gọi Java luôn phát ra đúng một Redis command. Chi tiết có thể thay đổi theo serializer, pipeline, transaction, cache manager và phiên bản client.

### Vì sao CLI có thể không đọc được key Java đã ghi?

**Serialization** là nguyên nhân rất phổ biến. Redis lưu bytes; ứng dụng có thể chuyển đổi đối tượng Java thành JSON, String hoặc dữ liệu nhị phân trước khi ghi.

- **StringRedisTemplate** thuận tiện khi cả key/value đều là chuỗi.
- **RedisTemplate** có thể dùng serializer khác nhau cho key, value, hash key và hash value. Dữ liệu nhị phân trông như ký tự lạ trong CLI.
- **Spring Cache** có thể thêm prefix cache name vào tên key, ví dụ một dạng phổ biến là **products::42**; tên cụ thể phụ thuộc cấu hình RedisCacheManager.
- Nếu key Java đã được serialize thành bytes nhị phân, lệnh GET theo một key chuỗi tưởng tượng có thể không tìm thấy key thực.

Cách điều tra: xác nhận ứng dụng và CLI đang kết nối đúng **host, port, database và ACL/TLS**; dùng SCAN theo prefix; kiểm tra TYPE; kiểm tra cấu hình serializer; sau đó chọn đúng lệnh đọc theo kiểu dữ liệu. Không nên đổi serializer chỉ để CLI hiển thị đẹp hơn khi Redis đang có dữ liệu từ định dạng cũ, vì có thể mất khả năng đọc tương thích.

Ví dụ nếu service khai báo **@Cacheable(cacheNames = "products", key = "#id")**, có thể xuất hiện khóa mang prefix products:

~~~text
SCAN 0 MATCH products* COUNT 20
TYPE products::42
TTL products::42
~~~

Đây chỉ là **minh họa cách đặt tên phổ biến**, không bảo đảm key của mọi ứng dụng có dạng đó. Khi đối chiếu cache, hãy xem cache có được tạo sau lần đọc đầu, có tồn tại trong TTL và bị evict sau thay đổi dữ liệu hay không.

## 14. Các lỗi hay gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| GET trả nil | Key không tồn tại, hết hạn, sai DB hoặc tên key | EXISTS, TTL, SCAN, cấu hình kết nối |
| WRONGTYPE | Dùng lệnh của String trên Hash/List hoặc ngược lại | TYPE rồi dùng HGETALL, LRANGE, SMEMBERS... |
| TTL bằng -1 | Có key nhưng không gán expiration | Kiểm tra SET/EXPIRE/PERSIST |
| TTL bằng -2 | Không có key | Kiểm tra key và thời điểm hết hạn |
| SET ... NX không ghi được | Key đã tồn tại | GET, EXISTS, TTL |
| SMEMBERS trả thứ tự khác | Set không bảo đảm thứ tự | So sánh membership, không dựa vào thứ tự |
| HGETALL trông như chuỗi rời rạc | CLI hiển thị các cặp field/value thành danh sách | Dùng HGET một field để xác nhận |
| Stream có entry nhưng worker không nhận | Group bắt đầu từ ID khác, entry đang pending... | XINFO GROUPS, XPENDING, ID đọc |
| SELECT 1 báo lỗi | Redis Cluster hoặc môi trường không hỗ trợ | Kiểm tra topology và cấu hình app |
| GET hiện ký tự không đọc được | Serializer ghi dữ liệu nhị phân | Kiểm tra serializer/value format |
| PUBLISH trả 0 | Không có subscriber tại thời điểm gửi | SUBSCRIBE trước rồi mới PUBLISH |

Lỗi phổ biến nhất là nhầm **Hash key** với **String key**. Một key được tạo bằng HSET sẽ không đọc được bằng GET; cần TYPE rồi HGET hoặc HGETALL.

## 15. Bài thực hành tổng hợp: cache và thống kê sản phẩm

Mô phỏng một service có thông tin sản phẩm, cache tên và bộ đếm lượt xem. Trong thực tế, nguồn dữ liệu chính có thể nằm ở database quan hệ; ở đây Hash chỉ dùng để trình diễn những gì quan sát được trong Redis.

### Bước 1: Lưu dữ liệu và tạo cache

~~~text
HSET lesson:cli:demo:product:42 name "Spring Data Redis" stock 10
SET lesson:cli:demo:cache:productName:42 "Spring Data Redis" EX 90
HGETALL lesson:cli:demo:product:42
GET lesson:cli:demo:cache:productName:42
TTL lesson:cli:demo:cache:productName:42
~~~

### Bước 2: Tăng lượt xem và tạo bảng xếp hạng

~~~text
INCR lesson:cli:demo:productViews:42
INCR lesson:cli:demo:productViews:42
GET lesson:cli:demo:productViews:42
ZINCRBY lesson:cli:demo:popularProducts 2 product:42
ZRANGE lesson:cli:demo:popularProducts 0 -1 REV WITHSCORES
~~~

INCR trên key chưa tồn tại xem giá trị ban đầu là 0 và tạo giá trị mới từ 1. Sau hai lần INCR, bộ đếm là 2. ZINCRBY thêm hoặc cập nhật score của member product:42 và trả score mới.

### Bước 3: Sửa dữ liệu rồi quan sát cache cũ

~~~text
HSET lesson:cli:demo:product:42 name "Spring Data Redis - New"
HGET lesson:cli:demo:product:42 name
GET lesson:cli:demo:cache:productName:42
DEL lesson:cli:demo:cache:productName:42
EXISTS lesson:cli:demo:cache:productName:42
SET lesson:cli:demo:cache:productName:42 "Spring Data Redis - New" EX 90
GET lesson:cli:demo:cache:productName:42
~~~

Khi Hash đã đổi tên, cache String **vẫn có thể giữ tên cũ** đến khi TTL kết thúc hoặc key được chủ động cập nhật/xóa. Đây chính là lý do logic **cache invalidation** cần được thiết kế cẩn thận trong Spring Data Redis.

### Bước 4: Kiểm tra kiểu và TTL

~~~text
TYPE lesson:cli:demo:product:42
TYPE lesson:cli:demo:cache:productName:42
TYPE lesson:cli:demo:productViews:42
TYPE lesson:cli:demo:popularProducts
TTL lesson:cli:demo:cache:productName:42
SCAN 0 MATCH lesson:cli:demo:* COUNT 20
~~~

Kiểu dữ liệu lần lượt là **hash**, **string**, **string**, **zset**. Chỉ cache name được gán TTL trong các lệnh này. Nếu SCAN trả cursor khác 0, tiếp tục duyệt đến khi hết.

### Bước 5: Chỉ dọn key của bài thực hành

~~~text
DEL lesson:cli:demo:product:42
DEL lesson:cli:demo:cache:productName:42
DEL lesson:cli:demo:productViews:42
DEL lesson:cli:demo:popularProducts
~~~

DEL nhận tên key chính xác; **DEL lesson:cli:demo:\*** không có ý nghĩa xóa theo wildcard. Không dùng lệnh xóa toàn database để dọn ví dụ.

## 16. Quy trình đọc bất kỳ ví dụ Spring Data Redis nào

1. **Xác định Redis instance** mà ứng dụng dùng, gồm host, port, database, quyền truy cập và các prefix key.
2. **Tìm đúng key** theo tên hoặc SCAN theo namespace nếu chưa biết tên.
3. **Xác định kiểu** bằng TYPE trước khi đọc dữ liệu.
4. **Chọn lệnh đọc tương ứng**: String → GET; Hash → HGET/HGETALL; List → LRANGE; Set → SMEMBERS; Sorted Set → ZRANGE WITHSCORES; Stream → XRANGE.
5. **Kiểm tra vòng đời** bằng EXISTS, TTL, PTTL trước và sau thao tác để quan sát expire và evict.
6. **Đối chiếu với Java**: kiểm tra serializer, lệnh dự kiến, thay đổi dữ liệu nguồn, cache hit/miss và tác dụng của chính sách hết hạn.

**Ghi nhớ:** redis-cli giúp trả lời Redis đang chứa gì và một lệnh đã thay đổi trạng thái ra sao. Các lệnh quan trọng nhất khi mới đọc ví dụ là **PING, SCAN, TYPE, GET, TTL, HGETALL, LRANGE, SMEMBERS, ZRANGE, XRANGE**. Nắm đúng nhóm lệnh cho từng kiểu dữ liệu sẽ giúp bạn hiểu code Spring Data Redis và phát hiện nguyên nhân những kết quả ngoài mong đợi.
