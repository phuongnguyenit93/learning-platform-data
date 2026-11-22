# Giới hạn của hàng đợi có trì hoãn khi dùng Sorted Set

## 1. Bài toán và ranh giới của Redis Sorted Set

Một **delayed queue** (hàng đợi có trì hoãn) chứa những công việc được tạo trước nhưng chỉ **đủ điều kiện xử lý sau một thời điểm xác định**. Ví dụ: gửi email nhắc thanh toán sau 15 phút, thử lại webhook sau 30 giây, hết hạn giữ chỗ sau 10 phút hoặc kích hoạt một tác vụ theo lịch người dùng.

Redis **Sorted Set** (ZSET) thường được chọn làm nền tảng vì mỗi phần tử (*member*) có một **score**, và Redis duy trì thứ tự tăng dần theo score. Trong delayed queue, ta có thể lưu **job ID** làm member và **thời điểm được phép chạy** làm score.

~~~text
ZSET: dq:{email}:scheduled

score (Unix milliseconds)    member
--------------------------------------
1800000000000                mail:101
1800000003000                mail:102
1800000030000                mail:103

score nhỏ hơn → đủ điều kiện chạy sớm hơn
~~~

Nếu **nowMillis = 1800000005000**, job **mail:101** và **mail:102** đã đến hạn, còn **mail:103** chưa đến hạn.

Điều quan trọng:

> Sorted Set chỉ cung cấp thứ tự theo score cùng các phép truy vấn/cập nhật member. Nó không tự trở thành một message queue có bộ hẹn giờ, xác nhận xử lý, visibility timeout, retry, dead-letter hay exactly-once processing.

Một delayed queue đáng tin cậy phải quyết định chuyện gì xảy ra nếu hai worker cùng nhận một job, worker chết sau khi lấy job, API bên ngoài đã thực thi nhưng Redis chưa nhận ack, Redis failover, hoặc một đợt lớn job cùng đến hạn.

## 2. Redis Sorted Set thực sự hỗ trợ những thao tác nào?

| Lệnh | Dùng trong delayed queue | Giới hạn |
|---|---|---|
| **ZADD** | Đưa job ID vào hàng đợi với score thời điểm chạy | Không tự thông báo đúng giờ |
| **ZRANGE ... BYSCORE** | Tìm job có score ≤ thời gian hiện tại | Chỉ đọc, chưa claim |
| **ZRANGEBYSCORE** | Cú pháp truy vấn theo score ở các phiên bản cũ | Không tự claim job |
| **ZRANGE key 0 0 WITHSCORES** | Xem job sớm nhất và hạn của nó | Không ngủ đến đúng thời điểm |
| **ZREM** | Loại job khỏi ZSET | Không biết tác vụ bên ngoài thành công chưa |
| **ZCARD** | Đếm tổng job đang có trong ZSET | Không phân biệt đã đến hạn |
| **ZCOUNT key -inf now** | Đếm số job có score đến hạn | Không biểu diễn job đang xử lý |
| **ZSCORE** | Kiểm tra thời điểm chạy của một job | Không cho biết kết quả thực thi |
| **ZPOPMIN** | Lấy và xóa member có score thấp nhất | Có thể lấy job chưa đến hạn |
| **BZPOPMIN** | Chờ khi ZSET trống, rồi pop member có score nhỏ nhất | Không chờ đến khi score ≤ now |

Từ Redis 6.2, **ZRANGE ... BYSCORE** có thể thay thế dạng truy vấn **ZRANGEBYSCORE**. Ví dụ trong bài sử dụng cú pháp mới khi phù hợp.

### 2.1. Một dòng thời gian

~~~text
Giờ hiện tại              Job A         Job B        Job C
     |                      |             |            |
     v                      v             v            v
-----+----------------------+-------------+------------+----> thời gian
  09:00                  09:05         09:10        09:30
     |
     +-- Producer ghi ZADD A, B, C

  09:04:59 -> chưa có job nào đến hạn
  09:05:00 -> A đủ điều kiện được nhận
  09:10:00 -> B đủ điều kiện được nhận
  09:30:00 -> C đủ điều kiện được nhận
~~~

Redis không tạo callback hay luồng xử lý riêng cho từng member. Một worker hoặc scheduler phải quan sát thời gian, phát hiện score đến hạn và tiến hành claim job.

### 2.2. Độ phức tạp

**ZADD** có độ phức tạp khoảng **O(log N)** cho mỗi phần tử; truy vấn khoảng score giới hạn kết quả bằng **ZRANGE ... BYSCORE LIMIT** thường có độ phức tạp **O(log N + M)**, trong đó **M** là số phần tử trả về. Đây là lợi ích lớn khi cần tìm vài job gần hạn trong hàng triệu member.

Tuy vậy, khi một triệu job cùng đến hạn, tổng công việc xử lý vẫn tương ứng với một triệu job. Sorted Set giúp **tìm thứ tự**, không xóa bỏ chi phí xử lý thật.

## 3. Thiết kế dữ liệu và biểu diễn thời gian

Một cách tổ chức có thể sử dụng:

~~~text
dq:{email}:scheduled     ZSET  jobId -> runAtMillis
dq:{email}:processing    ZSET  jobId -> leaseUntilMillis
dq:{email}:leaseTokens   HASH  jobId -> claimToken

job:mail:101             Payload và trạng thái của job
job:mail:102             Payload và trạng thái của job
~~~

Các key **dq:{email}:...** dùng chung hash tag **{email}** để hỗ trợ script nhiều key trên cùng Redis Cluster hash slot. Không nên đưa mọi job của hệ thống vào một hash tag duy nhất nếu điều đó gây nóng một node; ở quy mô lớn có thể phải chia partition.

Nên lưu **ID công việc duy nhất** ở member và đặt payload ở nguồn dữ liệu có quản lý riêng. Nếu nhét JSON dài trực tiếp vào member, việc thay payload có thể khiến Redis xem đó là member mới, gây khó khăn khi hủy, retry, deduplicate và đối chiếu trạng thái.

### 3.1. Score dùng Unix timestamp theo mili giây

~~~java
import java.time.Duration;
import java.time.Instant;

Instant runAt = Instant.now().plus(Duration.ofMinutes(15));
long runAtMillis = runAt.toEpochMilli();
~~~

Redis lưu ZSET score bằng số dấu phẩy động 64 bit; số nguyên trong khoảng **±2^53** được biểu diễn chính xác. Unix timestamp tính bằng mili giây hiện nay nằm trong khoảng đó. Không dùng Unix nanoseconds rất lớn rồi giả định score vẫn giữ được độ chính xác đến từng nanosecond.

Phải thống nhất đơn vị **milliseconds** giữa producer, Redis và worker. Nếu một bên truyền **epoch seconds**, một bên so sánh **epoch milliseconds**, job có thể bị xử lý quá sớm hoặc treo nhiều năm.

Nếu người dùng chọn giờ địa phương như 08:00 ở một vùng có daylight saving time, application cần giải quyết timezone và quy tắc đổi giờ trước, rồi chuyển thành **Instant**. Redis không tự hiểu timezone từ score.

### 3.2. Hai job có cùng score không được xếp theo FIFO

Redis sắp member có cùng score theo thứ tự từ điển nhị phân của chính member:

~~~redis
ZADD dq:{demo}:scheduled 1800000000000 job:b
ZADD dq:{demo}:scheduled 1800000000000 job:a
ZRANGE dq:{demo}:scheduled 0 -1
~~~

Thứ tự có thể là **job:a**, rồi **job:b** dù job:b được thêm trước. Nếu cần FIFO chính xác cho job cùng hạn, phải thiết kế quy tắc sequence/tie breaker và cách cấp sequence nguyên tử; chỉ dùng timestamp không tạo FIFO theo thời điểm enqueue.

Một member chỉ tồn tại một lần trong ZSET. Gọi **ZADD** hai lần cùng job ID với score khác nhau sẽ **đổi lịch job**, không tạo hai bản sao để chạy hai lần. Với công việc lặp lại nhiều lượt, cần ID riêng cho mỗi lượt chạy hoặc một mô hình recurrence rõ ràng.

## 4. Cách xây dựng hàng đợi đơn giản

### 4.1. Producer thêm job

~~~redis
ZADD dq:{email}:scheduled 1800000000000 mail:101
ZADD dq:{email}:scheduled 1800000003000 mail:102
ZADD dq:{email}:scheduled 1800000030000 mail:103
~~~

Score có thể được cập nhật bằng ZADD, ví dụ đổi thời điểm chạy mail:103. Trong một hệ thống có worker đồng thời, cần xác định liệu job đã ở trạng thái processing trước khi đổi lịch hay chưa; ZADD vào scheduled không tự thu hồi công việc đang chạy.

### 4.2. Worker đọc danh sách job đến hạn

Với **nowMillis = 1800000005000**:

~~~redis
ZRANGE dq:{email}:scheduled -inf 1800000005000 BYSCORE LIMIT 0 10
~~~

Hoặc dùng cú pháp:

~~~redis
ZRANGEBYSCORE dq:{email}:scheduled -inf 1800000005000 LIMIT 0 10
~~~

Redis trả tối đa mười member có score nằm trong khoảng chỉ định, theo thứ tự score. Nhưng lệnh chỉ **đọc**, không đánh dấu xử lý và không cấp quyền sở hữu. Hai worker khác nhau hoàn toàn có thể cùng nhận **mail:101** từ phép đọc này.

Nếu muốn xem job sớm nhất để tính thời gian ngủ:

~~~redis
ZRANGE dq:{email}:scheduled 0 0 WITHSCORES
~~~

Khi producer chèn job mới có score sớm hơn, worker đang ngủ không tự được Redis đánh thức. Đây là một trong những giới hạn đầu tiên của thiết kế.

## 5. Giới hạn thứ nhất: polling gây trễ hoặc tạo tải nền

Worker có thể chạy:

~~~text
while running:
    now = currentTimeMillis()
    due = ZRANGE scheduled -inf now BYSCORE LIMIT 0 batchSize
    claim và xử lý due
    sleep(pollInterval)
~~~

### 5.1. Poll interval quyết định một phần scheduling latency

Nếu poll mỗi **5 giây**, một job đến hạn ngay sau lượt poll có thể phải đợi gần 5 giây mới được phát hiện, chưa kể queue backlog và thời gian thực thi:

~~~text
09:00:00  worker poll, chưa có job
09:00:01  job A đến hạn
09:00:05  worker poll, nhận thấy A
          -> trễ phát hiện khoảng 4 giây
~~~

Giảm interval xuống 100 ms có thể giảm trễ trong điều kiện bình thường, nhưng làm tăng số lần truy vấn Redis cả khi không có việc.

Giả sử **50 worker** poll **10 lần/giây**:

\[
50 \times 10 = 500\ \text{truy vấn/giây}
\]

Đây là 500 lần kiểm tra mỗi giây ngay cả khi queue rỗng. Nếu mỗi nhóm nghiệp vụ có một queue riêng, lượng polling tổng cộng còn tăng.

### 5.2. Poll thích nghi và tín hiệu thức dậy

Một hướng triển khai là:

- Khi còn job đến hạn, tiếp tục claim các batch trong giới hạn concurrency.
- Khi chưa có việc đến hạn, đọc score nhỏ nhất rồi ngủ tới gần hạn kế tiếp, nhưng đặt **giới hạn ngủ tối đa**.
- Khi producer thêm job có hạn sớm hơn, có thể phát **Pub/Sub notification** hoặc tín hiệu khác để gợi ý worker thức dậy.
- Vẫn có polling dự phòng vì Redis Pub/Sub không phải cơ chế thông báo bền vững; subscriber ngắt kết nối có thể bỏ lỡ tín hiệu.

Nếu yêu cầu job phải bắt đầu chính xác trong vài mili giây, cần tính cả độ trễ đồng hồ, mạng, scheduling của JVM, failover và tải hệ thống. Sorted Set cộng polling không tự cam kết độ chính xác thời gian cứng.

## 6. Giới hạn thứ hai: hai worker có thể cùng nhìn thấy một job

Đoạn code sau dễ viết:

~~~java
Set<String> due = zsets.rangeByScore(
    queueKey,
    Double.NEGATIVE_INFINITY,
    (double) System.currentTimeMillis(),
    0,
    1
);

if (due != null && !due.isEmpty()) {
    String jobId = due.iterator().next();
    zsets.remove(queueKey, jobId);
    process(jobId);
}
~~~

Nhưng **rangeByScore → remove → process** là nhiều thao tác riêng:

| Thời điểm | Worker A | Worker B |
|---|---|---|
| 1 | ZRANGE thấy mail:101 | |
| 2 | | ZRANGE cũng thấy mail:101 |
| 3 | ZREM mail:101 trả 1 | |
| 4 | | ZREM mail:101 trả 0 |
| 5 | Xử lý mail:101 | Nếu không kiểm tra kết quả ZREM vẫn có thể xử lý |

Kiểm tra **ZREM == 1** có thể giúp tránh hai worker cùng xử lý trong tình huống này, nhưng thao tác đọc và xóa vẫn rời rạc, tạo lượt gọi dư và đòi hỏi nhiều logic tranh chấp. Quan trọng hơn, **xóa job trước khi xử lý sẽ làm mất job nếu worker chết**.

### 6.1. Vì sao ZPOPMIN và BZPOPMIN không đủ?

**ZPOPMIN** lấy và xóa member có score thấp nhất trong một lệnh nguyên tử. Nhưng nó **không kiểm tra score đã đến hạn**:

~~~redis
ZADD dq:{demo}:scheduled 1800000030000 future:job
ZPOPMIN dq:{demo}:scheduled 1
~~~

Lệnh vẫn có thể lấy **future:job** ngay lúc ZSET chỉ chứa job tương lai.

**BZPOPMIN** chờ khi ZSET *không có member*. Ngay khi ZSET có một member dù score ở ngày mai, nó cũng có thể trả job đó. Chữ **blocking** ở đây không có nghĩa chờ đến khi **score <= now**.

Tương tự, các lệnh pop-min khác xử lý phần tử nhỏ nhất, không tự hiểu semantics “not before timestamp” của delayed queue.

## 7. Claim nguyên tử bằng Lua script

Một Lua script giúp kiểm tra score đến hạn rồi xóa job trong **cùng một lần thực thi server**:

~~~lua
-- KEYS[1] = ZSET scheduled
-- ARGV[1] = nowMillis
local due = redis.call(
    'ZRANGE', KEYS[1], '-inf', ARGV[1],
    'BYSCORE', 'LIMIT', 0, 1
)

if #due == 0 then
    return nil
end

local jobId = due[1]
if redis.call('ZREM', KEYS[1], jobId) ~= 1 then
    return nil
end

return jobId
~~~

Trong lúc script chạy, command của worker khác không thể chen giữa bước tìm job và ZREM. Khi gọi qua Spring Data Redis, kết quả **null** báo không có job đến hạn; kết quả String là job ID đã được loại khỏi scheduled.

**Nhưng đây vẫn chưa phải hàng đợi đáng tin cậy.** Script chỉ làm cho bước giành job nguyên tử. Một lỗi sau khi claim vẫn có thể làm mất job:

~~~text
ZSET scheduled
    |
    | atomic claim, ZREM
    v
Worker A nhận job ID trong RAM
    |
    +-- thành công ---------> kết thúc
    |
    +-- worker crash -------> job đã bị xóa khỏi scheduled
                               không còn dữ liệu nào tự đẩy job chạy lại
~~~

Vì thế một thiết kế **at-most-once attempt** có thể chấp nhận được nếu công việc không quan trọng; nhưng với thanh toán, đồng bộ dữ liệu hoặc workflow không được bỏ sót, cần một trạng thái processing và cơ chế phục hồi.

## 8. Giới hạn thứ ba: cần processing state, lease và acknowledgement

Một mô hình có thể giữ hai Sorted Set:

~~~text
scheduled:  jobId -> runAtMillis
processing: jobId -> leaseUntilMillis
~~~

**Lease** là thời hạn quyền sở hữu job của một lần claim. Worker chuyển job từ scheduled sang processing; khi hoàn thành phải **ack**. Nếu worker chết và lease hết hạn, một tiến trình khác có thể phát hiện job còn dang dở và lập lịch thử lại.

### 8.1. Claim chuyển trạng thái nguyên tử

Một script minh họa:

~~~lua
-- KEYS[1] = dq:{email}:scheduled
-- KEYS[2] = dq:{email}:processing
-- KEYS[3] = dq:{email}:leaseTokens
-- ARGV[1] = nowMillis
-- ARGV[2] = leaseUntilMillis
-- ARGV[3] = token duy nhất cho lần claim

local due = redis.call(
    'ZRANGE', KEYS[1], '-inf', ARGV[1],
    'BYSCORE', 'LIMIT', 0, 1
)

if #due == 0 then
    return nil
end

local jobId = due[1]
redis.call('ZREM', KEYS[1], jobId)
redis.call('ZADD', KEYS[2], ARGV[2], jobId)
redis.call('HSET', KEYS[3], jobId, ARGV[3])
return jobId
~~~

Script trên giả định các key nằm cùng một instance/hash slot và chỉ có những thành phần theo đúng state machine được phép sửa trạng thái. Đây mới là **một phần của cơ chế queue**: chưa có heartbeat, ack, reclaimer, retry, cancel hoặc đồng bộ với payload.

~~~text
scheduled --[claim]--> processing (leaseUntil)
                           |
                     worker thực thi
                           |
                +----------+-----------+
                |                      |
             thành công             thất bại/crash
                |                      |
            ack(token)              lease hết hạn
                |                      |
          xóa processing           reclaimer
                                       |
                                 retry / DLQ
~~~

### 8.2. Ack phải xác nhận đúng chủ sở hữu

Giả sử worker A nhận job, xử lý lâu hơn lease. Reclaimer cho B nhận lại cùng job. Nếu A hoàn thành muộn và gọi **ZREM processing jobId**, nó có thể xóa trạng thái processing mới do B sở hữu.

Một token duy nhất theo **lần claim** giúp từ chối stale ack:

~~~lua
-- KEYS[1] = processing ZSET
-- KEYS[2] = leaseTokens HASH
-- ARGV[1] = jobId
-- ARGV[2] = claimToken

local token = redis.call('HGET', KEYS[2], ARGV[1])
if token ~= ARGV[2] then
    return 0
end

redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
return 1
~~~

Việc kiểm tra token và ack trong cùng Lua script tránh khoảng hở giữa so sánh chủ sở hữu và xóa trạng thái. Tuy nhiên token **chỉ bảo vệ trạng thái ở Redis**; worker A vẫn có thể đã gọi API ngoài sau khi mất lease. Để bảo vệ tác dụng phụ cần idempotency hoặc fencing/version được **hệ thống đích** kiểm tra.

### 8.3. Chọn lease duration

Lease quá ngắn khiến công việc hợp lệ chưa xong đã bị reclaim và thực thi trùng. Lease quá dài khiến job sau crash phải đợi lâu mới có người xử lý lại.

Có thể dùng:

- Lease dựa trên thời gian xử lý p95/p99 và giới hạn nghiệp vụ.
- **Heartbeat/renew lease** với điều kiện token hiện tại còn hợp lệ cho job dài.
- Timeout thực thi rõ ràng; worker không được giữ job vô hạn.
- Giới hạn attempts, retry delay và dead-letter sau số lần thất bại.

Tất cả thao tác gia hạn lease cần bảo đảm chỉ chủ sở hữu hiện tại được gia hạn.

## 9. Reclaimer và state machine: cứu job chưa hoàn thành

Một **reclaimer** kiểm tra những job trong ZSET **processing** có **leaseUntilMillis <= nowMillis**:

~~~redis
ZRANGE dq:{email}:processing -inf 1800000005000 BYSCORE LIMIT 0 100
~~~

Đây chỉ là bước **tìm kiếm**. Một reclaimer đầy đủ còn phải thực hiện atomically các việc:

1. Kiểm tra lease vẫn hết hạn vào thời điểm claim lại; tránh đè lên worker vừa gia hạn.
2. Xác định job còn thuộc trạng thái có thể retry, chưa bị hủy hoặc hoàn thành.
3. Tăng attempt count theo quy tắc và chọn thời điểm retry.
4. Xóa thông tin chủ sở hữu/token cũ.
5. Chuyển job từ processing về scheduled, hoặc sang nơi lưu **dead-letter** nếu vượt giới hạn thử.
6. Ghi trạng thái/lý do lỗi để có thể quan sát và điều tra.

Nếu hai reclaimer cùng chạy **ZRANGE → ZREM → ZADD** trong nhiều command, chúng có thể tranh chấp. Việc worker gia hạn lease đúng lúc reclaimer đang đọc cũng cần được giải quyết. Các chuyển trạng thái phải dựa trên điều kiện được kiểm tra **cùng lúc với thao tác ghi**, thường qua Lua/Redis Function hoặc cơ chế phù hợp.

### 9.1. Mô hình trạng thái

~~~text
CREATED
   |
   v
SCHEDULED ----[cancel]-------------------------> CANCELLED
   |
   | runAt <= now, claim
   v
PROCESSING ----[success + ack]-----------------> COMPLETED
   |
   +----[lỗi có thể retry]------> SCHEDULED
   |
   +----[hết lease]-------------> SCHEDULED
   |
   +----[quá giới hạn retry]-----> DEAD_LETTER
~~~

State machine là **một quy ước nghiệp vụ**, không phải tính năng Redis Sorted Set tự cung cấp. Khi hệ thống có producer, worker, reclaimer và API hủy/đổi lịch, các bên phải tuân thủ cùng trạng thái, version và quyền cập nhật.

### 9.2. Khôi phục không đồng nghĩa job thật sự chưa chạy

Một worker có thể xử lý tác vụ thành công ở hệ thống ngoài nhưng không kịp gửi ack tới Redis. Reclaimer chỉ nhìn thấy lease đã hết, không biết side effect đã thành công hay chưa. Nếu retry, job có thể thực thi hai lần. Điều này dẫn tới giới hạn quan trọng tiếp theo.

## 10. Giới hạn thứ tư: không có exactly-once end-to-end

| Bảo đảm | Ý nghĩa | Với ZSET tự xây |
|---|---|---|
| **At-most-once** | Có thể mất job sau khi nhận, ít nguy cơ phát lại có chủ đích | Xóa khỏi scheduled rồi xử lý; dễ mất job khi crash |
| **At-least-once** | Cố gắng không bỏ sót, chấp nhận job được xử lý lại | Cần processing, lease, ack, retry và recovery |
| **Exactly-once effect** | Tác dụng nghiệp vụ ở nơi nhận diễn ra đúng một lần | Không đạt được chỉ bằng các lệnh Redis |

Ví dụ:

~~~text
Worker A claim job:payment:42
      |
      v
Gọi cổng thanh toán -> trả thành công
      |
      v
Worker chết trước khi ack Redis
      |
      v
Lease hết hạn, reclaimer đưa job về scheduled
      |
      v
Worker B nhận job và gọi cổng thanh toán lần nữa
~~~

Từ góc nhìn Redis, job chưa ack nên đáng được retry. Nhưng từ góc nhìn cổng thanh toán, yêu cầu đã được thực hiện. **Redis không có transaction nguyên tử với HTTP API bên ngoài**, và một claim token ở Redis không tự ngăn double charge.

Các phương án thường cần phối hợp:

- **Idempotency key** ổn định theo nghiệp vụ, ví dụ **payment:order-42**, được chính hệ thống đích dùng để chống xử lý trùng.
- Database lưu kết quả công việc có unique constraint và transaction phù hợp.
- **Outbox/inbox pattern** khi cần đồng bộ giữa ghi dữ liệu nghiệp vụ và xuất event.
- **Fencing token/version** được tài nguyên đích kiểm tra để từ chối tác vụ của worker đã mất quyền sở hữu.
- Compensation hoặc đối soát nếu thao tác ngoài không thể cung cấp exactly-once effect.

Một cách diễn đạt thực tế thường là: **at-least-once processing + idempotent handler**. Hãy định nghĩa “thành công” ở tầng nghiệp vụ: chỉ ack Redis sau khi có đủ bằng chứng tác dụng phụ đã được ghi nhận, nhưng vẫn chuẩn bị trường hợp ack thất bại.

## 11. Giới hạn thứ năm: thời gian, đồng hồ và key TTL

### 11.1. Lệch đồng hồ giữa producer và worker

Producer tạo hạn bằng:

~~~java
long runAtMillis = Instant.now()
    .plusSeconds(30)
    .toEpochMilli();
~~~

Worker truyền **System.currentTimeMillis()** vào Lua claim. Nếu đồng hồ máy worker nhanh hơn máy producer 15 giây, job có thể được claim sớm hơn thời điểm thực theo nguồn đồng hồ đã dùng để lên lịch.

Nên thống nhất nguồn thời gian, đồng bộ đồng hồ của các instance và dùng cùng quy ước UTC/Unix milliseconds. Một thiết kế có thể lấy thời gian từ Redis server qua **TIME** khi cần so sánh với một nguồn thời gian gần dữ liệu hơn, nhưng phải thực hiện phù hợp với Redis server/driver và contract của script đang dùng.

### 11.2. “Đến hạn” khác “bắt đầu chạy” và “hoàn tất”

**runAtMillis = T** chỉ thể hiện *thời điểm sớm nhất có thể nhận việc*. Nó không hứa worker còn sống tại T, có CPU trống tại T hoặc side effect hoàn thành ngay ở T.

~~~text
runAt       actualStart            actualFinish
  |              |                       |
  v              v                       v
--+--------------+-----------------------+----> time
      queue lag       execution time
~~~

Một delayed queue cần định nghĩa SLA dựa trên **start lag**, **completion lag** hoặc deadline nghiệp vụ thực sự. Chỉ lưu score không đo được các độ trễ này.

### 11.3. Không dùng EXPIRE của ZSET làm bộ hẹn giờ từng job

~~~redis
EXPIRE dq:{email}:scheduled 3600
~~~

Lệnh trên khiến **cả Redis key** có thể bị xóa sau một giờ, bao gồm mọi member sẽ chạy ngày mai. **Score của một member không phải TTL** và Redis không tự pop member khi score trôi qua.

Tương tự, nếu payload riêng của job có TTL 30 phút nhưng runAt sau hai giờ, worker có thể nhận job ID mà payload đã hết hạn. Retention của payload phải tính đến **thời điểm chạy, thời gian retry, thời gian lease, DLQ và nhu cầu điều tra**.

### 11.4. Tác vụ chậm và đổi giờ

Một job được tạo theo “8 giờ sáng ngày hôm sau” phụ thuộc vào **múi giờ người dùng** và đôi khi có thời điểm địa phương không tồn tại hoặc lặp lại do daylight saving time. Hãy giải quyết logic lịch ở application, lưu mốc **Instant** cụ thể làm score, và lưu thêm timezone/schedule definition khi cần tính những lần lặp tiếp theo.

Không tính lịch định kỳ bằng cách luôn cộng đúng **24 giờ** nếu yêu cầu nghiệp vụ là “8 giờ địa phương mỗi ngày” ở vùng đổi giờ.

## 12. Giới hạn thứ sáu: backlog, fairness và starvation

### 12.1. Job đến hạn có thể phải đợi rất lâu

Giả sử một worker pool xử lý tối đa **50 job/giây**, nhưng có **10.000 job** cùng đủ điều kiện chạy lúc 10:00.

\[
\frac{10000}{50} = 200\ \text{giây}
\]

Ngay cả khi không có overhead, phải mất tối thiểu khoảng 200 giây để xử lý hết lượng việc đó. Redis sắp đúng score nhưng không tạo thêm năng lực xử lý.

Đo **scheduling lag**:

\[
\text{lagMillis} = \text{actualStartMillis} - \text{runAtMillis}
\]

và quan sát p50/p95/p99 của lag theo loại job. Nếu chỉ đo Redis command latency, có thể bỏ sót việc job chờ nhiều phút dù Redis luôn phản hồi trong vài mili giây.

### 12.2. Một queue chung có thể thiếu fairness

~~~text
scheduled queue:
  5.000 webhook đã đến hạn
  20 email nhắc thanh toán đã đến hạn
  100 báo cáo định kỳ đã đến hạn
~~~

Nếu worker luôn ưu tiên score sớm nhất và webhook chiếm toàn bộ slot, email có thể bị trễ lâu. Sorted Set không tự quản lý fairness theo tenant, priority, loại job hay chi phí xử lý.

Có thể cân nhắc:

- Queue/partition riêng cho workload cần SLA khác nhau.
- Worker pool và concurrency riêng cho job nặng/nhẹ.
- Rate limit theo tenant hoặc hệ thống đích.
- Trọng số ưu tiên và lịch phân phối giữa nhiều queue.
- Giới hạn batch claim để tránh một worker giữ quá nhiều job.

Số queue quá lớn lại tăng lượng polling và chi phí vận hành. Phải chọn partition dựa trên tải và yêu cầu fairness thật, thay vì chia nhỏ máy móc.

### 12.3. Thứ tự theo score chưa đủ cho strict priority

Nếu hai job có cùng score, Redis dùng thứ tự từ điển nhị phân của member, không có FIFO theo lúc enqueue. Nếu cần ưu tiên theo **priority rồi tới thời điểm**, phải thiết kế score/member hoặc cấu trúc dữ liệu riêng, đồng thời xác định điều kiện starvation khi liên tục có công việc ưu tiên cao.

## 13. Giới hạn thứ bảy: độ bền dữ liệu và failover

### 13.1. ZADD thành công không tự có nghĩa đã được lưu bền vững

Một lệnh được Redis master xử lý thành công không mặc nhiên nghĩa là mọi replica đã nhận được lệnh hoặc dữ liệu chắc chắn tồn tại sau sự cố. Cần xem **AOF/RDB**, chính sách fsync, replication, failover, backup và thời gian phục hồi.

Khi failover diễn ra gần thời điểm **schedule/claim/ack**, ứng dụng có thể quan sát trạng thái không khớp với điều nó nghĩ đã hoàn thành trước đó. Thiết kế recovery và idempotency phải xét những cửa sổ lỗi này.

### 13.2. Eviction có thể làm mất queue

Nếu Redis dùng như cache và có chính sách **maxmemory eviction**, key queue có thể bị loại bỏ tùy chính sách khi cạn bộ nhớ. Một công việc không thể mất không nên dựa vào việc một ZSET sẽ tồn tại mãi trong cache mà không kiểm soát retention, eviction và recovery.

Ở hệ thống yêu cầu độ bền cao, database có thể là nguồn sự thật của job, còn Redis Sorted Set là **chỉ mục lịch chạy có thể tái tạo**. Khi Redis mất dữ liệu, cần job reconciliation/rebuild từ nguồn dữ liệu bền vững.

### 13.3. Metadata không nhất quán

Ví dụ:

~~~text
dq:{email}:scheduled   chứa mail:101
job:mail:101            payload email đã hết hạn hoặc bị xóa
~~~

Worker nhận ID nhưng không thể xử lý. Đây là một lỗi mô hình dữ liệu, không phải lỗi của ZRANGE. Phải xác định vòng đời payload và trạng thái theo **runAt**, retry và hoàn tất, tránh xóa payload trước khi job được xử lý/điều tra.

## 14. Giới hạn thứ tám: đồng bộ payload, job status và lịch

Giả sử producer ghi job vào PostgreSQL rồi thêm lịch Redis:

~~~text
INSERT job trong PostgreSQL
           |
           v
ZADD scheduled trong Redis
~~~

Nếu tiến trình crash giữa hai bước, SQL có job nhưng Redis không có lịch. Đảo thứ tự lại có thể khiến Redis chứa ID chưa có payload ở SQL.

**Redis transaction/Lua không bao trùm database ngoài Redis**, nên đây là bài toán **dual write**.

### 14.1. Outbox và reconcile

Khi database là nguồn dữ liệu chính, một hướng triển khai:

1. Ghi **job** và **outbox record** trong cùng một transaction database.
2. Dispatcher đọc outbox và lập lịch Redis với job ID ổn định.
3. Dispatcher đánh dấu đã phát sau khi xác nhận; cho phép retry nếu gặp lỗi.
4. Áp dụng quy tắc deduplicate/phiên bản lịch để không tạo thêm lượt chạy ngoài ý muốn.
5. Có quá trình **reconcile** khi Redis thiếu lịch, job đã hủy hoặc hệ thống trải qua failover.

Ví dụ này không tự giải quyết mọi race condition. Cần chính sách đối với job đổi hạn giữa lúc outbox chưa phát, và job đã hoàn thành trước khi dispatcher bị retry.

### 14.2. Đổi hạn bằng ZADD có thể tạo bản scheduled khi job đã processing

~~~redis
ZADD dq:{email}:scheduled 1800000600000 mail:101
~~~

Nếu **mail:101** đã được claim sang processing, lệnh này có thể lại tạo member mail:101 ở scheduled, trong khi worker cũ vẫn đang chạy. Hệ thống có nguy cơ có hai đường thực thi cho cùng job ID.

Tương tự:

~~~redis
ZREM dq:{email}:scheduled mail:101
~~~

chỉ xóa nếu job còn ở scheduled; nó **không thu hồi** tác dụng phụ của worker đã bắt đầu chạy. Cancel/reschedule cần được định nghĩa theo state machine, version/attempt và race với claim, heartbeat, ack.

## 15. Giới hạn thứ chín: retry, backoff và dead-letter phải tự xây

| Loại lỗi | Hướng xử lý thường gặp |
|---|---|
| Mất kết nối tạm thời | Retry có giới hạn, backoff và jitter |
| API ngoài trả HTTP 429 | Tôn trọng Retry-After/rate limit nếu có |
| Payload sai cấu trúc hoặc thiếu trường | Permanent failure; không retry vô hạn |
| Worker crash | Hết lease rồi reclaim |
| API ngoài thành công nhưng ack Redis thất bại | Có thể retry; handler phải idempotent |
| Lỗi code lặp lại ở cùng một job | Dead-letter và điều tra |

### 15.1. Exponential backoff

Một lịch ví dụ:

~~~text
attempt 1 -> đợi khoảng 1 giây
attempt 2 -> đợi khoảng 2 giây
attempt 3 -> đợi khoảng 4 giây
attempt 4 -> đợi khoảng 8 giây
...
~~~

Score cho lần retry có thể tính:

\[
\text{nextRunAt} = \text{now} +
\min(\text{baseDelay} \times 2^{\text{attempt}-1},\ \text{maxDelay})
+ \text{jitter}
\]

**Jitter** tránh hàng nghìn job cùng thức dậy sau một đợt lỗi. Phải giới hạn số lần thử, thời gian sống tổng thể và có chính sách khi deadline nghiệp vụ đã qua.

### 15.2. Dead-letter storage

ZSET không tự cung cấp dead-letter queue, attempt history, exception tracking hay dashboard điều tra. Application phải quyết định ghi:

- Lỗi cuối cùng và thời điểm thất bại.
- Số lần thử, worker/trace ID, phiên bản job.
- Payload reference (không log bí mật không cần thiết).
- Cách replay hoặc bỏ hẳn sau điều tra.
- Retention và quyền truy cập dữ liệu lỗi.

Nếu các tính năng này là yêu cầu cốt lõi, một queue/workflow engine chuyên dụng có thể giảm đáng kể phần hạ tầng tự viết.

## 16. Spring Data Redis: đặt lịch và quan sát bằng ZSetOperations

Với Spring Boot sử dụng Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ kết nối Redis local:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Đối với job ID dạng chuỗi, **StringRedisTemplate** giúp thống nhất serializer và dễ quan sát trong redis-cli. Một adapter chỉ chịu trách nhiệm **lập lịch, xem job đến hạn và thống kê**:

~~~java
package com.example.jobs;

import java.time.Instant;
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ZSetOperations;
import org.springframework.stereotype.Repository;

@Repository
public class RedisDelayedSchedule {

    private static final String SCHEDULED_KEY =
        "dq:{email}:scheduled";

    private final ZSetOperations<String, String> zsets;

    public RedisDelayedSchedule(StringRedisTemplate redis) {
        this.zsets = redis.opsForZSet();
    }

    public boolean schedule(String jobId, Instant runAt) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is required");
        }
        if (runAt == null) {
            throw new IllegalArgumentException("runAt is required");
        }

        return Boolean.TRUE.equals(zsets.add(
            SCHEDULED_KEY,
            jobId,
            (double) runAt.toEpochMilli()
        ));
    }

    public Set<String> peekDue(Instant now, long batchSize) {
        if (now == null || batchSize <= 0) {
            throw new IllegalArgumentException("Invalid arguments");
        }

        return zsets.rangeByScore(
            SCHEDULED_KEY,
            Double.NEGATIVE_INFINITY,
            (double) now.toEpochMilli(),
            0,
            batchSize
        );
    }

    public Long scheduledCount() {
        return zsets.size(SCHEDULED_KEY);
    }

    public Long dueCount(Instant now) {
        return zsets.count(
            SCHEDULED_KEY,
            Double.NEGATIVE_INFINITY,
            (double) now.toEpochMilli()
        );
    }
}
~~~

Giải thích:

- **opsForZSet().add(...)** tương ứng ZADD. Boolean trả về thường cho biết member **mới** có được thêm hay không; nếu member đã tồn tại và chỉ **đổi score**, kết quả có thể là **false** mặc dù lần cập nhật lịch đã xảy ra. Vì vậy không dùng duy nhất Boolean ấy để kết luận cập nhật thất bại.
- **rangeByScore(...)** lấy danh sách **đến hạn** nhưng **chưa giành quyền xử lý**. Tên **peekDue** thể hiện rõ điểm này.
- **size(...)** tương ứng ZCARD, bao gồm cả job chưa đến hạn.
- **count(...)** tương ứng ZCOUNT theo khoảng score, hữu ích để xem backlog đang đến hạn.

Code mẫu dành cho lời gọi đồng bộ bình thường. Một số API Spring Data Redis trả **null** khi command đang được queue trong pipeline/transaction; không nên mặc nhiên áp dụng kết quả bên trên cho mọi ngữ cảnh Redis.

**Không gọi process(jobId) ngay sau peekDue()** khi có nhiều worker. Job phải được claim theo một cơ chế có điều kiện nguyên tử và xử lý vòng đời tiếp theo.

## 17. Spring Data Redis: nhận job bằng Lua script

Một adapter claim job theo mô hình **scheduled → processing** ở phần trước:

~~~java
package com.example.jobs;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Repository;

@Repository
public class RedisJobClaimer {

    private static final String SCHEDULED =
        "dq:{email}:scheduled";
    private static final String PROCESSING =
        "dq:{email}:processing";
    private static final String TOKENS =
        "dq:{email}:leaseTokens";

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<String> claimScript;

    public RedisJobClaimer(StringRedisTemplate redis) {
        this.redis = redis;
        this.claimScript = new DefaultRedisScript<>();
        this.claimScript.setResultType(String.class);
        this.claimScript.setScriptText("""
            local due = redis.call(
                'ZRANGE', KEYS[1], '-inf', ARGV[1],
                'BYSCORE', 'LIMIT', 0, 1
            )
            if #due == 0 then
                return nil
            end
            local jobId = due[1]
            redis.call('ZREM', KEYS[1], jobId)
            redis.call('ZADD', KEYS[2], ARGV[2], jobId)
            redis.call('HSET', KEYS[3], jobId, ARGV[3])
            return jobId
            """);
    }

    public Optional<ClaimedJob> claim(
            Instant now,
            Duration leaseDuration) {

        if (now == null || leaseDuration == null ||
                leaseDuration.isZero() || leaseDuration.isNegative()) {
            throw new IllegalArgumentException("Invalid claim arguments");
        }

        String token = UUID.randomUUID().toString();
        long nowMs = now.toEpochMilli();
        long leaseUntilMs = now.plus(leaseDuration).toEpochMilli();

        String jobId = redis.execute(
            claimScript,
            List.of(SCHEDULED, PROCESSING, TOKENS),
            Long.toString(nowMs),
            Long.toString(leaseUntilMs),
            token
        );

        return Optional.ofNullable(jobId)
            .map(id -> new ClaimedJob(id, token));
    }

    public record ClaimedJob(String jobId, String leaseToken) {}
}
~~~

Các thành phần có vai trò rõ ràng:

1. **DefaultRedisScript** lưu Lua script để Spring Data Redis thực thi phía Redis; adapter tạo một lần và dùng lại.
2. **KEYS[1]** là ZSET scheduled; script tìm một member có score ≤ nowMillis.
3. **KEYS[2]** là ZSET processing; script đặt thời điểm hết lease.
4. **KEYS[3]** lưu token riêng của lần claim.
5. **Optional.empty()** nghĩa là không có job đến hạn trong lượt claim này.

Vì cả ba Redis key thuộc cùng hash slot **{email}**, script có thể được dùng theo ràng buộc nhiều key trên Redis Cluster khi topology và client hỗ trợ. Những key payload/metadata liên quan nếu cũng được script truy cập cần được đưa vào **KEYS** và tuân thủ cùng quy tắc.

**Giới hạn của ví dụ:** adapter mới minh họa claim. Hệ thống vẫn thiếu ack, heartbeat, reclaimer, cancel/reschedule, attempt limits, DLQ, outbox và idempotent handler. Ngoài ra, đồng hồ được truyền từ Java, nên cần kiểm soát lệch giờ giữa nhiều worker.

### 17.1. Vì sao không chỉ dùng @Transactional?

Đặt **@Transactional** lên service không tự làm toàn bộ thao tác với Redis, PostgreSQL và HTTP API thành một distributed transaction nguyên tử. Redis transaction còn cần cấu hình/connection semantics thích hợp.

Ngay cả khi dùng **MULTI/EXEC**, một lệnh đọc đã queue không thể được Java sử dụng ngay trước EXEC để quyết định nên ghi gì trong cùng transaction ấy. Với bài toán **chọn job có score đến hạn rồi chuyển trạng thái**, Lua hoặc Redis Function đưa điều kiện và cập nhật vào cùng ranh giới thực thi phía server.

Lua cũng không có rollback tự động với các thay đổi đã được ghi thành công trước một lỗi runtime trong script. Do đó script cần có điều kiện đầu vào rõ ràng và giữ logic ngắn.

## 18. Reactive Redis cũng không tự bổ sung queue semantics

Trong ứng dụng WebFlux, **ReactiveRedisTemplate** hoặc **ReactiveStringRedisTemplate** cho phép thao tác Redis qua **Mono/Flux**, giảm nhu cầu chặn thread khi chờ network I/O.

Tuy nhiên:

- Một chuỗi **rangeByScore → remove** qua **flatMap** vẫn là hai Redis command riêng nếu không gói chúng trong cơ chế nguyên tử phù hợp.
- **Non-blocking** không đồng nghĩa **exactly-once**, không tạo visibility timeout và không đảm bảo worker không nhận trùng.
- **Flux** và backpressure không tự giải quyết retry, lease hoặc payload thất lạc.
- Gọi **block()** trên event loop WebFlux có thể làm mất lợi ích reactive và gây lỗi blocking.

Nếu xây delayed queue reactive, vẫn phải giữ cùng state machine và các bất biến claim/ack/reclaim. Thay đổi API bất đồng bộ không thay đổi giới hạn cơ bản của Sorted Set.

## 19. Monitoring: đếm queue chưa đủ

Chỉ đo **ZCARD scheduled** rất dễ đánh giá sai. Một queue có 100.000 job cho tuần sau có thể hoàn toàn khỏe mạnh, trong khi một queue chỉ còn 15 job nhưng tất cả đã quá hạn 30 phút có thể đang gặp sự cố.

| Metric | Ý nghĩa |
|---|---|
| **scheduled_count** | Tổng job đang có trong scheduled ZSET |
| **due_count** | Job đã đến hạn theo ZCOUNT |
| **processing_count** | Job đã claim nhưng chưa ack |
| **expired_lease_count** | Job đang processing nhưng lease đã quá hạn |
| **scheduling_lag_ms** | Thời gian từ runAt đến actualStart |
| **execution_duration_ms** | Thời gian thực thi của worker |
| **success/failure_rate** | Tỷ lệ thành công/thất bại |
| **retry_count** | Số lần job được thử lại |
| **dead_letter_count** | Số job rơi vào trạng thái lỗi cuối |
| **claim_errors** | Lỗi command, Lua, timeout, key type hoặc kết nối |
| **outbox_backlog** | Job ở nguồn bền vững nhưng chưa có lịch Redis |

Ví dụ xem job sớm nhất:

~~~redis
ZRANGE dq:{email}:scheduled 0 0 WITHSCORES
~~~

So score với thời gian hiện tại để xem nó đã quá hạn bao lâu. Nếu scheduled rỗng nhưng processing có hàng nghìn lease hết hạn, job vẫn có thể bị tắc nghẽn. Cần nhìn cả hai trạng thái.

Theo dõi các metric theo loại job và tenant phù hợp với SLA, nhưng tránh tạo time-series label theo từng **job ID** vì cardinality sẽ tăng rất lớn.

Để kiểm tra queue key, không dùng **KEYS dq:\*** trong đường request hoặc vòng poll trên database Redis lớn. Quản lý danh sách queue một cách có chủ đích, hoặc dùng SCAN có kiểm soát cho công việc quản trị.

## 20. Redis Cluster: cùng slot để claim, nhưng dễ tạo hotspot

Các Redis key trong Lua script minh họa:

~~~text
dq:{email}:scheduled
dq:{email}:processing
dq:{email}:leaseTokens
~~~

đều chia sẻ hash tag **{email}**. Với Redis Cluster, key trong một script nhiều key cần nằm trong cùng hash slot; Redis không biến nhiều master thành một giao dịch nguyên tử xuyên cụm.

Nếu tất cả job đều dồn vào một ZSET lớn trên một slot, một node có thể thành hotspot. Khi tải tăng, cần cân nhắc phân vùng:

~~~text
dq:{email-0}:scheduled / processing / leaseTokens
dq:{email-1}:scheduled / processing / leaseTokens
dq:{email-2}:scheduled / processing / leaseTokens
...
~~~

Mỗi nhóm **scheduled/processing/tokens** trong cùng partition giữ tính nguyên tử của claim cục bộ. Nhưng hệ thống phải tự quản lý công bằng giữa partition, phân công worker, retry/cancel và việc job thuộc partition nào. Không thể giả định một lệnh ZRANGE hoặc một script trên partition 0 thấy mọi job của partition 1.

## 21. Khi nào Sorted Set phù hợp, khi nào cần nền tảng khác?

Sorted Set có thể là lựa chọn hợp lý nếu:

- Số lượng job/worker phù hợp năng lực vận hành hiện tại.
- Độ trễ polling là chấp nhận được.
- Job có thể retry an toàn hoặc handler được thiết kế idempotent.
- Đội phát triển sẵn sàng quản lý lease, ack, reclaimer, retry, DLQ, metrics và state machine.
- Hệ thống có cách tái tạo lịch/payload từ nguồn bền vững khi cần.

Đối với workflow quan trọng hoặc yêu cầu delivery mạnh, nên so sánh với các lựa chọn khác:

| Cách tiếp cận | Điểm mạnh | Lưu ý cho delayed queue |
|---|---|---|
| **Redis Sorted Set tự dựng** | Dễ lưu score là thời điểm chạy; tìm job đến hạn nhanh | Tự làm phần lớn queue semantics |
| **Redis Streams + consumer groups** | Có cơ chế pending/ack/claim consumer group | Message trong Stream không tự được phát chỉ khi tới timestamp; vẫn cần lớp scheduling |
| **Database jobs table** | Có thể gắn việc tạo job với transaction dữ liệu nghiệp vụ | Cần query/index/locking và polling worker phù hợp |
| **Message broker hỗ trợ delayed delivery** | Một số sản phẩm hỗ trợ delay, ack, retry, DLQ | Giới hạn delay, thứ tự và mức bảo đảm tùy sản phẩm/cấu hình |
| **Job scheduler/workflow engine** | Quản lý lifecycle, dependency, retry và history | Tăng yêu cầu vận hành nhưng giảm phần tự dựng |

Nếu Redis chỉ được dùng như cache nhưng job có liên quan thanh toán, huỷ đơn hoặc dữ liệu không thể mất, cần cân nhắc rất kỹ trước khi lấy ZSET làm nguồn sự thật duy nhất.

## 22. Những nhầm lẫn thường gặp

### Nhầm lẫn 1: BZPOPMIN chờ tới lúc score đến hạn

Không. **BZPOPMIN** chỉ chờ ZSET có member. Một member hẹn ngày mai vẫn có thể bị pop ngay khi queue không rỗng.

### Nhầm lẫn 2: Lua claim nguyên tử đồng nghĩa job không thể mất

Không. Nếu claim chỉ **ZREM rồi trả ID**, worker chết sau claim sẽ khiến job mất khỏi scheduled. Atomic claim chỉ giải quyết tranh chấp giữa các worker trong Redis.

### Nhầm lẫn 3: Có lease thì job không bao giờ chạy hai lần

Không. Worker cũ có thể thực hiện side effect thành công trước khi ack, rồi job được cấp lại sau lease timeout. Cần idempotency ở hệ thống đích.

### Nhầm lẫn 4: Cùng score thì FIFO

Không. Redis sắp các member cùng score theo thứ tự nhị phân của member, không theo thứ tự ZADD.

### Nhầm lẫn 5: Đặt EXPIRE cho queue là đủ tạo delayed message

Không. **EXPIRE** xóa cả key queue; score không phải TTL riêng cho member.

### Nhầm lẫn 6: Retry mọi command bị timeout là an toàn

Không. Command hoặc side effect có thể đã thành công, còn client chưa nhận được response. Retry không có idempotency có thể tạo tác dụng phụ trùng.

### Nhầm lẫn 7: ZCARD nhỏ nghĩa là queue không bị backlog

Không. Job có thể đang mắc kẹt trong processing hoặc vài job bị quá hạn rất lâu. Cần đo **due_count**, **expired leases** và **lag**.

### Nhầm lẫn 8: ZADD đổi lịch có thể thu hồi job đã claim

Không. Nếu worker đã chuyển ID sang processing, ZADD vào scheduled có thể tạo một bản lịch mới trong khi job cũ vẫn chạy.

### Nhầm lẫn 9: Một Lua script chạy qua mọi Redis Cluster slot

Không. Script nhiều key phải tuân thủ ràng buộc cùng hash slot. Gom tất cả vào một slot giúp cùng script hoạt động nhưng có thể tạo hotspot.

### Nhầm lẫn 10: @Transactional bảo đảm Redis và API ngoài cùng commit

Không. Một transaction manager cục bộ không làm Redis, SQL và HTTP side effect trở thành distributed transaction nguyên tử.

## 23. Bài tập suy luận

### Bài 1 — Hai worker đọc cùng job

Hai worker cùng gọi **ZRANGE ... BYSCORE LIMIT 0 1** và nhận **mail:101**. Tại sao?

**Giải thích:** ZRANGE chỉ đọc. Muốn một worker nhận quyền xử lý, phải có thao tác claim có điều kiện nguyên tử và quản lý trạng thái sau claim.

### Bài 2 — Pop job chưa đến hạn

ZSET chỉ có job với score **now + 10 phút**. Worker gọi **BZPOPMIN**. Có thể nhận job ngay không?

**Giải thích:** Có. ZSET đã có member nên BZPOPMIN có thể trả về member dù score chưa tới hạn.

### Bài 3 — Crash sau claim

Worker dùng Lua **ZRANGE rồi ZREM**, sau đó chết trước khi gửi email. Queue có tự phục hồi không?

**Giải thích:** Không. Job đã bị xóa. Cần processing, lease, reclaimer và chính sách retry nếu yêu cầu không bỏ sót.

### Bài 4 — Polling

Có **20 worker**, mỗi worker poll **5 lần/giây**. Khi queue rỗng, hệ thống tạo bao nhiêu lượt kiểm tra mỗi giây?

**Giải thích:** Khoảng **100 lượt/giây**. Có thể giảm tải bằng nhịp poll phù hợp, polling thích nghi và tín hiệu thức dậy bổ sung.

### Bài 5 — ID trùng

Gọi **ZADD** hai lần với cùng member **mail:101**, score lần đầu là 1000, lần sau là 2000. Trong ZSET có bao nhiêu member?

**Giải thích:** Một member. Lần sau cập nhật score, không tạo thêm một lượt chạy độc lập.

### Bài 6 — Đồng hồ worker nhanh 15 giây

Producer dùng clock chuẩn, worker nhanh hơn 15 giây và truyền giờ local vào Lua. Rủi ro là gì?

**Giải thích:** Worker có thể claim trước thời điểm nghiệp vụ mong muốn. Cần nguồn thời gian và quy ước thống nhất.

### Bài 7 — Ack của worker cũ

Worker A hết lease; B claim lại cùng job. A gửi **ZREM processing** chỉ theo job ID. Rủi ro?

**Giải thích:** A có thể xóa trạng thái mà B đang sở hữu. Ack phải kiểm tra claim token/version hiện hành trong cùng thao tác nguyên tử.

### Bài 8 — Tác dụng phụ thành công nhưng job bị retry

Worker gọi payment API thành công rồi chết trước ack; reclaimer đưa job vào scheduled. Điều gì có thể xảy ra?

**Giải thích:** Payment API có thể bị gọi lần hai. Cần idempotency key hoặc kiểm soát tác dụng phụ tại nơi nhận.

### Bài 9 — Backlog

8.000 job cùng đến hạn, hệ thống chỉ xử lý được 100 job/giây. Mốc thời gian tối thiểu để chạy hết?

**Giải thích:** Ít nhất khoảng **80 giây**, chưa kể overhead và lỗi. Đến hạn không có nghĩa bắt đầu hoặc hoàn tất ngay.

### Bài 10 — TTL queue

Queue có job chạy ngày mai, nhưng code gọi **EXPIRE scheduled 3600**. Kết quả?

**Giải thích:** Sau một giờ, cả ZSET có thể bị xóa, làm mất mọi job trong key, bao gồm job ngày mai.

## 24. Những quyết định cần chốt trước khi triển khai

1. **Độ trễ:** chấp nhận scheduling lag tối đa bao nhiêu và polling interval nào phù hợp?
2. **Durability:** Redis là nguồn sự thật hay có database/outbox để phục hồi?
3. **Claim:** nhiều worker có thể tranh job không; bước claim có nguyên tử không?
4. **Lease:** thời hạn bao lâu, có heartbeat không, ai có quyền gia hạn?
5. **Ack:** token/version nào xác nhận đúng lần claim hiện tại?
6. **Recovery:** worker chết hoặc Redis failover thì job được phát hiện và retry ra sao?
7. **Idempotency:** nếu job chạy lại, hệ thống đích bảo vệ tác dụng phụ thế nào?
8. **Retry/DLQ:** giới hạn attempts, backoff, jitter và cách điều tra lỗi?
9. **Cancel/reschedule:** xử lý ra sao khi job đã processing?
10. **Backpressure/fairness:** khi nhiều job tới hạn cùng lúc, phân phối worker thế nào?
11. **Cluster:** script có cùng slot không; partition có tạo hotspot không?
12. **Monitoring:** có đo due_count, expired leases và scheduling lag không?

Nếu các quyết định này chưa được giải đáp, **ZADD + ZRANGE + ZREM** mới chỉ là một bảng lịch hẹn tối thiểu, chưa phải một delayed queue đủ bảo đảm để vận hành nghiệp vụ quan trọng.

## 25. Tài liệu tham khảo

- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/)
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/)
- [Redis — ZRANGE](https://redis.io/docs/latest/commands/zrange/)
- [Redis — ZPOPMIN](https://redis.io/docs/latest/commands/zpopmin/)
- [Redis — BZPOPMIN](https://redis.io/docs/latest/commands/bzpopmin/)
- [Redis — Lua scripting](https://redis.io/docs/latest/develop/interact/programmability/eval-intro/)
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Spring Data Redis — ZSetOperations](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ZSetOperations.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)

## 26. Tổng kết

**Redis Sorted Set** cung cấp một cách gọn để lưu **thời điểm sớm nhất được xử lý** theo score, truy vấn các job đến hạn và cập nhật lịch. **ZSetOperations** của Spring Data Redis giúp thao tác với score và member; **RedisScript** có thể gộp bước kiểm tra score và claim thành một lần thực thi nguyên tử.

Những giới hạn chính nằm ở **vòng đời xử lý công việc**: polling gây độ trễ và tải nền; các lệnh pop không tự chờ score đến hạn; nhiều worker có thể cùng nhìn thấy một job; xóa trước khi xử lý có thể làm mất job; lease/retry có thể khiến job được thực thi nhiều lần. Sorted Set cũng không cung cấp transaction với database hay API bên ngoài, không tự quản lý dead-letter, và không bảo đảm bắt đầu công việc chính xác tại thời điểm score.

Với công việc đơn giản và có thể chấp nhận sai lệch nhỏ, ZSET là nền tảng thực dụng. Với công việc quan trọng, cần thiết kế **processing state, lease, ack có token, reclaimer, retry, DLQ, monitoring, idempotency và cơ chế phục hồi bền vững**, hoặc sử dụng một nền tảng queue/workflow chuyên dụng có những bảo đảm tương ứng.
