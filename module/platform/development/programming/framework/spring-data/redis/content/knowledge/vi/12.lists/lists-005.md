# Chuyển phần tử giữa các danh sách

Trong Redis, **List** là cấu trúc dữ liệu có thứ tự, cho phép thêm và lấy phần tử ở **đầu (LEFT)** hoặc **cuối (RIGHT)**. Với Spring Data Redis, nhiều ứng dụng dùng List để lưu công việc chờ xử lý, danh sách nhiệm vụ tạm, hoặc các bước trong một luồng xử lý. Khi chuyển một phần tử từ List này sang List khác, thao tác đó phải được thiết kế sao cho không làm mất phần tử hoặc để hai consumer cùng lấy một công việc ngoài ý muốn.

Redis cung cấp hai lệnh chính cho nhu cầu này:

- **`LMOVE`**: lấy một phần tử ở một đầu của List nguồn và đẩy sang một đầu của List đích bằng **một lệnh nguyên tử**.
- **`BLMOVE`**: thao tác tương tự nhưng **chờ** khi List nguồn đang trống, đến khi có dữ liệu hoặc hết thời gian chờ.

Spring Data Redis cung cấp những thao tác tương ứng trong `ListOperations`, đặc biệt là `move(...)`. Ngoài ra, có thể gặp `rightPopAndLeftPush(...)`, API liên quan đến cặp lệnh Redis cũ `RPOPLPUSH`/`BRPOPLPUSH`.

Bài học tập trung vào **ý nghĩa của việc chuyển phần tử**, các lựa chọn đầu nguồn/đầu đích, tính nguyên tử, chuyển có chờ, mẫu hàng đợi `pending → processing`, giới hạn khi phục hồi công việc, và cách sử dụng đúng trong ứng dụng Spring Boot.

## 1. Vì sao cần chuyển phần tử giữa hai Redis List?

Giả sử ứng dụng có các công việc chờ xử lý:

~~~text
jobs:pending
LEFT                         RIGHT
[job-101, job-102, job-103]
~~~

Một worker muốn lấy `job-101` để xử lý. Cách đơn giản là:

~~~text
LPOP jobs:pending
-> job-101
~~~

Sau lệnh này, `job-101` không còn trong List nguồn. Nếu worker bị dừng ngay sau khi nhận công việc, nhưng trước khi xử lý xong, Redis không còn một dấu vết rõ ràng trong danh sách nào cho biết công việc đó đã được nhận.

Có thể dùng **List thứ hai**:

~~~text
jobs:pending                   jobs:processing

[job-101, job-102, job-103]   []
             |
             | LMOVE source destination LEFT RIGHT
             v

[job-102, job-103]             [job-101]
~~~

Một thao tác Redis vừa lấy `job-101` ra khỏi `pending`, vừa đưa nó vào `processing`. Nếu worker dừng sau khi chuyển, công việc vẫn còn trong `processing` để hệ thống có cơ hội phát hiện và xử lý lại.

Điều này hữu ích khi ứng dụng cần theo dõi các công việc đã được **nhận nhưng chưa xác nhận hoàn tất**. Tuy nhiên, **List thứ hai tự nó chưa tạo thành một hàng đợi đáng tin cậy đầy đủ**; phần xử lý thất bại, timeout, xác nhận và phục hồi cần thêm cơ chế.

## 2. Redis List có hai đầu: LEFT và RIGHT

Một List có thể hình dung như sau:

~~~text
Key: queue:pending

LEFT                                RIGHT
[A, B, C, D]
 ^                                    ^
 phần tử đầu                       phần tử cuối
~~~

Những thao tác cơ bản:

| Redis command | Tác dụng | Kết quả với `[A, B, C, D]` |
|---|---|---|
| `LPUSH key X` | Thêm X vào LEFT | `[X, A, B, C, D]` |
| `RPUSH key X` | Thêm X vào RIGHT | `[A, B, C, D, X]` |
| `LPOP key` | Lấy và xóa phần tử LEFT | Trả A; List còn `[B, C, D]` |
| `RPOP key` | Lấy và xóa phần tử RIGHT | Trả D; List còn `[A, B, C]` |
| `LRANGE key 0 -1` | Đọc các phần tử theo thứ tự | `[A, B, C, D]` |
| `LLEN key` | Trả số phần tử trong List | 4 |

Trong ứng dụng queue, quan trọng nhất là **quy ước chiều thêm và chiều lấy**:

- **FIFO**: phần tử vào trước được lấy trước. Ví dụ producer dùng `RPUSH`, consumer lấy `LPOP`.
- **LIFO**: phần tử vào sau được lấy trước. Ví dụ producer dùng `RPUSH`, consumer lấy `RPOP`.
- Khi chuyển giữa List, còn phải quyết định **đầu nào của List đích** sẽ nhận phần tử.

Một lựa chọn sai hướng có thể làm đảo thứ tự xử lý mà code vẫn chạy bình thường.

## 3. LMOVE: lệnh chuyển phần tử nguyên tử

Cú pháp Redis:

~~~text
LMOVE source destination LEFT|RIGHT LEFT|RIGHT
~~~

Bốn thành phần:

1. `source`: key của List nguồn.
2. `destination`: key của List đích.
3. `LEFT` hoặc `RIGHT` thứ nhất: **lấy** phần tử từ đầu nào của nguồn.
4. `LEFT` hoặc `RIGHT` thứ hai: **đưa** phần tử vào đầu nào của đích.

Lệnh trả về **giá trị phần tử đã chuyển**, hoặc `nil` nếu List nguồn trống. Khi source/destination không phải kiểu dữ liệu có thể thao tác như List, Redis có thể trả lỗi `WRONGTYPE`.

### 3.1. Ví dụ cơ bản bằng Redis CLI

Tạo hai danh sách (các ví dụ trong bài giả định key demo chưa tồn tại):

~~~bash
redis-cli RPUSH demo:pending A B C
redis-cli RPUSH demo:processing X Y

redis-cli LRANGE demo:pending 0 -1
# 1) A
# 2) B
# 3) C

redis-cli LRANGE demo:processing 0 -1
# 1) X
# 2) Y
~~~

Chuyển phần tử từ LEFT của nguồn sang RIGHT của đích:

~~~bash
redis-cli LMOVE demo:pending demo:processing LEFT RIGHT
# "A"
~~~

Sau lệnh:

~~~text
demo:pending      = [B, C]
demo:processing   = [X, Y, A]
~~~

Redis thực hiện thao tác lấy và đưa trong **một lệnh nguyên tử**: client khác không thể quan sát trạng thái trung gian “A đã bị lấy khỏi pending nhưng chưa được đưa vào processing”.

**Nguyên tử của LMOVE chỉ bao phủ việc chuyển giữa hai List.** Nó không bao phủ việc worker xử lý file, gọi API bên ngoài, ghi database hoặc gửi email sau đó.

### 3.2. Bốn kiểu chuyển của LMOVE

Giả sử mỗi trường hợp bắt đầu với:

~~~text
source      = [A, B, C]
destination = [X, Y]
~~~

| Lệnh | Phần tử chuyển | Source sau lệnh | Destination sau lệnh |
|---|---|---|---|
| `LMOVE source destination LEFT LEFT` | A | `[B, C]` | `[A, X, Y]` |
| `LMOVE source destination LEFT RIGHT` | A | `[B, C]` | `[X, Y, A]` |
| `LMOVE source destination RIGHT LEFT` | C | `[A, B]` | `[C, X, Y]` |
| `LMOVE source destination RIGHT RIGHT` | C | `[A, B]` | `[X, Y, C]` |

Cả hai hướng đều quan trọng:

- Hướng **lấy** quyết định phần tử nào được chọn trước.
- Hướng **đưa** quyết định thứ tự phần tử trong List đích.

Ví dụ `RIGHT LEFT` thường xuất hiện trong tài liệu về mô hình `LPUSH + RPOPLPUSH`: producer thêm job mới ở LEFT, consumer lấy job cũ nhất ở RIGHT và đưa sang LEFT của processing.

Nếu producer đã chọn `RPUSH` theo FIFO, worker thường dùng `LEFT RIGHT` khi chuyển sang processing để lấy job cũ nhất.

## 4. LMOVE cũng có thể xoay vòng phần tử trong cùng List

Hai key `source` và `destination` có thể là **cùng một key**.

~~~text
queue:round-robin = [A, B, C]
~~~

Gọi:

~~~bash
redis-cli LMOVE queue:round-robin queue:round-robin RIGHT LEFT
# C
~~~

Sau lệnh:

~~~text
queue:round-robin = [C, A, B]
~~~

Đây là thao tác **rotate**: phần tử cuối được đưa lên đầu. Ngược lại:

~~~bash
redis-cli LMOVE queue:round-robin queue:round-robin LEFT RIGHT
~~~

sẽ xoay phần tử đầu xuống cuối.

Các trường hợp có thể dùng:

- Danh sách tài nguyên cần quay vòng theo lượt.
- Tập tác vụ thử lại theo chính sách xoay vòng đơn giản.
- Chuỗi bước luân phiên trong một tiến trình nhỏ.

Tuy nhiên, xoay vòng trong một List **không tự bảo đảm fairness** nếu nhiều consumer cùng tranh chấp, hoặc một worker giữ tài nguyên lâu hơn worker khác. Nên xác định rõ khi nào cần queue, khi nào cần cơ chế điều phối khác.

## 5. Chuyển List bằng Spring Data Redis

Trong Spring Data Redis, nhóm API chính là `ListOperations<K, V>`:

~~~java
ListOperations<String, String> listOps =
        stringRedisTemplate.opsForList();
~~~

Với Spring Data Redis có hỗ trợ `LMOVE`, có thể gọi:

~~~java
listOps.move(
        "demo:pending",
        Direction.LEFT,
        "demo:processing",
        Direction.RIGHT
);
~~~

`Direction` là enum tương ứng hai đầu Redis List. Trong nhánh Spring Data Redis 3.x sử dụng:

~~~java
import org.springframework.data.redis.connection.RedisListCommands.Direction;
~~~

### 5.1. Ví dụ service chuyển job không blocking

~~~java
import org.springframework.data.redis.connection.RedisListCommands.Direction;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobTransferService {

    private static final String PENDING = "jobs:pending";
    private static final String PROCESSING = "jobs:processing";

    private final StringRedisTemplate redis;

    public JobTransferService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long enqueue(String jobId) {
        // Producer thêm vào cuối danh sách.
        return redis.opsForList().rightPush(PENDING, jobId);
    }

    public String claimNext() {
        // Lấy phần tử đầu và thêm vào cuối processing.
        return redis.opsForList().move(
                PENDING,
                Direction.LEFT,
                PROCESSING,
                Direction.RIGHT
        );
    }
}
~~~

Giả sử:

~~~text
RPUSH jobs:pending job-101 job-102 job-103
~~~

thì ba lần `claimNext()` lần lượt có thể trả về:

~~~text
job-101
job-102
job-103
~~~

với điều kiện không có consumer khác đồng thời và không có producer thay đổi thứ tự. Nếu nhiều worker cùng gọi `claimNext()`, mỗi lần chuyển được Redis xử lý như một lệnh nguyên tử, nên **một phần tử cụ thể ở đầu nguồn không bị cả hai lời gọi lấy cùng lúc**.

Lưu ý: điều này **không có nghĩa** một mã job không bao giờ xuất hiện hai lần. Nếu producer ghi hai phần tử cùng giá trị `job-101`, cả hai bản sao đều có thể được chuyển và xử lý.

### 5.2. Khi List nguồn trống

Với `LMOVE` không blocking:

~~~java
String jobId = redis.opsForList().move(
        PENDING, Direction.LEFT,
        PROCESSING, Direction.RIGHT
);

if (jobId == null) {
    // Không có công việc ở thời điểm gọi.
}
~~~

Redis trả `nil` khi List nguồn trống; Spring Data Redis thường ánh xạ thành `null` trong lời gọi trực tiếp. Một số API cũng có thể trả `null` ở ngữ cảnh transaction/pipeline trước khi kết quả được trả ra ngoài; do đó không nên dùng cùng giả định cho mọi chế độ thực thi.

Nếu cần đợi công việc mới thay vì liên tục hỏi Redis, dùng lệnh blocking phù hợp.

## 6. BLMOVE: chuyển và đợi khi chưa có phần tử

Cú pháp:

~~~text
BLMOVE source destination LEFT|RIGHT LEFT|RIGHT timeout
~~~

`BLMOVE` có cùng ý nghĩa chuyển phần tử như `LMOVE` nhưng khi nguồn trống, Redis **chờ** dữ liệu xuất hiện:

- Có phần tử trước thời hạn: chuyển phần tử và trả về giá trị.
- Hết thời gian chờ mà vẫn trống: trả `nil`.
- `timeout = 0` ở giao thức Redis có nghĩa là chờ vô thời hạn.
- Timeout của Redis dùng giây và có thể hỗ trợ giá trị thập phân; mức tương thích cụ thể phụ thuộc phiên bản Redis/driver.

Ví dụ:

~~~bash
# Terminal của consumer, chờ tối đa 5 giây
redis-cli BLMOVE jobs:pending jobs:processing LEFT RIGHT 5
~~~

Nếu terminal khác thêm một job:

~~~bash
redis-cli RPUSH jobs:pending job-202
~~~

consumer đang chờ có thể nhận:

~~~text
job-202
~~~

và `job-202` đã được chuyển sang `jobs:processing`.

### 6.1. Spring Data Redis dùng Duration cho thao tác blocking

~~~java
import java.time.Duration;

import org.springframework.data.redis.connection.RedisListCommands.Direction;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BlockingJobReceiver {

    private static final String PENDING = "jobs:pending";
    private static final String PROCESSING = "jobs:processing";

    private final StringRedisTemplate redis;

    public BlockingJobReceiver(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String receive() {
        return redis.opsForList().move(
                PENDING,
                Direction.LEFT,
                PROCESSING,
                Direction.RIGHT,
                Duration.ofSeconds(5)
        );
    }
}
~~~

`receive()` có thể giữ thread đang gọi trong thời gian đợi. Nếu 5 giây trôi qua mà nguồn vẫn trống, giá trị trả về thường là `null`.

**Lệnh blocking không nên được gọi tùy tiện từ HTTP request thread hoặc một scheduler chỉ có một thread.** Một consumer chuyên dụng, executor giới hạn số worker, hoặc một kiến trúc xử lý nền thích hợp sẽ dễ kiểm soát thời gian đợi và dừng ứng dụng hơn.

### 6.2. Redis timeout và client timeout phải tương thích

Giả sử `BLMOVE` chờ tối đa 30 giây nhưng Redis client được cấu hình command timeout 2 giây. Client có thể timeout sau 2 giây trước khi Redis kết thúc thời gian chờ.

Với Lettuce, Spring Data Redis có thể dùng kết nối chuyên biệt cho **blocking operations**, nhưng vẫn cần xét:

- Timeout của bản thân lệnh `BLMOVE`.
- Command/socket timeout phía client.
- Số kết nối đang chờ đồng thời và giới hạn pool.
- Cơ chế reconnect, cancellation và shutdown.
- Thời điểm Redis đã chuyển phần tử nhưng client không nhận được response vì đứt kết nối.

Không xem `BLMOVE` như phép đọc chắc chắn “chỉ thực hiện hoặc không thực hiện” từ góc nhìn client. Trường hợp timeout sau khi Redis đã chuyển phần tử cần được xử lý bằng khả năng kiểm tra/truy vết trong `processing`.

## 7. RPOPLPUSH và BRPOPLPUSH: cách làm lịch sử

Trước khi Redis hỗ trợ `LMOVE`/`BLMOVE`, hai lệnh phổ biến là:

~~~text
RPOPLPUSH source destination
BRPOPLPUSH source destination timeout
~~~

Chúng tương đương với hướng cố định:

~~~text
RPOPLPUSH source destination
≈ LMOVE source destination RIGHT LEFT

BRPOPLPUSH source destination timeout
≈ BLMOVE source destination RIGHT LEFT timeout
~~~

Redis 6.2 đưa vào `LMOVE` và `BLMOVE`, đồng thời đánh dấu cặp lệnh cũ là **deprecated** để hướng tới API linh hoạt hơn. Các lệnh cũ vẫn thường có trong hệ thống và tutorial cũ, nên cần hiểu ý nghĩa để đọc code legacy.

Trong Spring Data Redis, có thể gặp:

~~~java
String jobId = redis.opsForList()
        .rightPopAndLeftPush("jobs:pending", "jobs:processing");
~~~

Hoặc bản blocking có thời hạn:

~~~java
String jobId = redis.opsForList()
        .rightPopAndLeftPush(
                "jobs:pending",
                "jobs:processing",
                Duration.ofSeconds(5)
        );
~~~

Các phương thức này mang ý nghĩa **RIGHT → LEFT**, nên không thay trực tiếp cho một luồng `RPUSH + LEFT → RIGHT` nếu cần giữ FIFO. Khi dùng code mới và Redis hỗ trợ, `move(...)` giúp diễn tả rõ cả hai hướng.

### 7.1. Đừng nhầm các lệnh có tên gần giống

| Lệnh | Ý nghĩa |
|---|---|
| `LMOVE` | Chuyển **một phần tử List** từ một key List sang key List khác |
| `BLMOVE` | LMOVE có khả năng blocking khi List nguồn trống |
| `RPOPLPUSH` | Chuyển phần tử RIGHT của nguồn sang LEFT của đích (cũ) |
| `BRPOPLPUSH` | Phiên bản blocking của RPOPLPUSH (cũ) |
| `LPOP`/`RPOP` | Lấy/xóa phần tử khỏi một List; không chuyển nguyên tử sang List khác |
| `MOVE key db` | Chuyển **toàn bộ key** sang logical database khác trong phạm vi được hỗ trợ; không phải chuyển List element |
| `RENAME` | Đổi tên nguyên một key và dữ liệu của nó; không phải LMOVE |

`LMOVE` không có nghĩa là chuyển key sang một Redis server khác. Nó vẫn là lệnh Redis List trong cùng hệ thống Redis đang phục vụ các key tham gia.

## 8. Tính nguyên tử: vì sao không dùng LPOP rồi RPUSH?

Một đoạn code dễ viết:

~~~java
String job = redis.opsForList().leftPop("jobs:pending");
if (job != null) {
    redis.opsForList().rightPush("jobs:processing", job);
}
~~~

Hai lệnh Redis riêng có một khoảng trống:

~~~text
Consumer                   Redis
   |                         |
   +---- LPOP pending ------>|
   |<--- job-101 ------------+
   |
   X Ứng dụng crash trước RPUSH
   |
   |               job-101 không còn trong pending
   |               và chưa có trong processing
~~~

`LMOVE` giải quyết chính xác khoảng trống này:

~~~text
Consumer                   Redis
   |                         |
   +---- LMOVE ------------->|
   |       (pop + push nguyên tử trên server)
   |<--- job-101 ------------+
   |
   X Crash sau khi nhận
             |
             +-- job-101 vẫn nằm trong processing
~~~

**Giới hạn quan trọng:** nếu Redis primary đã thực thi `LMOVE` nhưng xảy ra failover trước khi bản sao nhận thay đổi, một số kết quả vẫn có thể bị mất theo đặc tính replication bất đồng bộ. Nguyên tử của lệnh không phải cam kết không bao giờ mất dữ liệu khi toàn hệ thống gặp sự cố.

### 8.1. Transaction MULTI/EXEC có thay được không?

Có thể nhóm lệnh Redis bằng transaction, nhưng để chuyển **chính phần tử vừa pop** từ nguồn sang đích, client cần biết giá trị đó. Hai lệnh `LPOP` rồi `RPUSH` thực hiện qua Java vẫn có thời điểm dừng giữa chúng. Chỉ bọc logic sai trong một transaction thông thường không tạo ra một lệnh “lấy giá trị trả về rồi đưa vào destination” một cách thuận tiện.

`LMOVE` đã thể hiện thao tác đúng bằng một lệnh ngắn. Nếu yêu cầu chuyển phần tử có điều kiện nghiệp vụ phức tạp hơn, Lua script trên các key thích hợp có thể là lựa chọn, nhưng cần xử lý lỗi và ràng buộc Redis Cluster.

## 9. Thiết kế queue pending → processing → acknowledged

Mẫu thường gặp:

~~~text
                     Producer
                        |
                    RPUSH jobId
                        |
                        v
                 jobs:pending
                        |
                BLMOVE LEFT RIGHT
                        |
                        v
                jobs:processing
                        |
                 Worker xử lý job
                   /          \
              Thành công      Thất bại/crash
                  |               |
             LREM theo ID       Giữ lại để
             (acknowledge)      phục hồi/retry
                  |
                  v
              Hoàn tất
~~~

Đây là một **reliable queue pattern ở mức cơ bản**, nơi mỗi job được nhận từ pending vẫn có dấu vết trong processing cho đến khi được xác nhận.

### 9.1. Producer nên đưa ID ổn định, không nhồi payload quá lớn

Ví dụ:

~~~bash
redis-cli RPUSH jobs:pending job-101 job-102 job-103
~~~

Mỗi phần tử là **job ID duy nhất**; payload có thể lưu ở database hoặc Hash riêng, tùy yêu cầu. Lợi ích của dùng ID:

- List gọn hơn.
- Có thể truy vết một công việc bằng ID.
- `LREM` khi hoàn tất dễ định vị chính xác.
- Dễ thực hiện idempotency trong xử lý nghiệp vụ.
- Không phải serialize/deserialize payload lớn trong mỗi lần chuyển.

Nếu cần payload gắn với ID trong Redis, phải quyết định TTL và quy tắc xóa payload khi job hoàn thành. Tránh trường hợp đã xóa item khỏi List nhưng payload tồn tại vĩnh viễn.

### 9.2. Consumer lấy job một cách nguyên tử

~~~java
String jobId = redis.opsForList().move(
        "jobs:pending",
        Direction.LEFT,
        "jobs:processing",
        Direction.RIGHT,
        Duration.ofSeconds(5)
);
~~~

Consumer lấy được ID và bắt đầu xử lý. Có thể có nhiều worker cùng chạy; Redis xử lý từng lần chuyển nguyên tử nên mỗi **phần tử** tại pending chỉ được chuyển bởi một lệnh tại một thời điểm.

**Tính duy nhất của ID là hợp đồng riêng**. Nếu producer vô tình đẩy `job-101` hai lần, hai worker vẫn có thể nhận hai bản sao cùng giá trị.

### 9.3. Acknowledge sau khi xử lý thành công

Sau khi nghiệp vụ thành công, xóa **một phần tử khớp với job ID** khỏi `processing`:

~~~java
Long removed = redis.opsForList()
        .remove("jobs:processing", 1, jobId);
~~~

Tương ứng Redis:

~~~bash
redis-cli LREM jobs:processing 1 job-101
~~~

`count = 1` xóa phần tử đầu tiên khớp khi duyệt từ LEFT sang RIGHT. Nếu job ID duy nhất trong processing, đó là một dạng acknowledge đơn giản.

Lưu ý:

- `LREM` có độ phức tạp phụ thuộc chiều dài List; processing rất lớn có thể khiến ACK tốn chi phí đáng kể.
- Nếu trùng job ID, xóa phần tử đầu tiên có thể không tương ứng đúng lượt xử lý muốn xác nhận.
- Nếu kết quả trả về là `0`, phần tử không còn trong processing; cần kiểm tra liệu đã ACK, đã reclaim hay có vấn đề đồng bộ.
- Không ACK trước khi nghiệp vụ hoàn tất; nếu worker crash sau ACK nhưng trước xử lý thành công thì job không còn được theo dõi.

### 9.4. Worker bị crash thì sao?

Nếu worker dừng khi job còn ở `processing`, Redis List không có sẵn khái niệm **“job này thuộc worker nào, đã chạy bao lâu, có hết lease chưa”**. Nếu không bổ sung metadata hoặc cơ chế giám sát, job có thể nằm mãi ở processing.

Một thiết kế phục hồi thường cần:

1. Theo dõi trạng thái `IN_PROGRESS`, thời điểm nhận và thời hạn xử lý của từng job.
2. Một reclaimer định kỳ tìm những job không có heartbeat hoặc đã quá deadline.
3. Kiểm tra job đã thực sự hoàn tất hay chưa.
4. Đưa job quay lại pending hoặc chuyển sang dead-letter theo số lần retry.
5. Bảo đảm thao tác reclaim phối hợp an toàn với worker đang xử lý và ACK.

Có thể dùng Hash/ZSet riêng để lưu deadline hoặc trạng thái, nhưng việc cập nhật nhiều key cần tính đến **atomicity** và các ràng buộc về hash slot khi dùng Redis Cluster.

**Không thể dùng `LMOVE processing pending ...` để tùy ý chuyển một job ID ở giữa processing**. `LMOVE` luôn lấy phần tử ở **đầu List** đã chỉ định; muốn reclaim một job cụ thể cần cơ chế tìm/xóa theo ID và đưa lại một cách nhất quán, ví dụ một script được thiết kế cho workload đó.

### 9.5. Mẫu worker Java đơn giản

~~~java
import java.time.Duration;

import org.springframework.data.redis.connection.RedisListCommands.Direction;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisJobWorker {

    private static final String PENDING = "jobs:pending";
    private static final String PROCESSING = "jobs:processing";

    private final StringRedisTemplate redis;
    private final JobHandler handler;

    public RedisJobWorker(
            StringRedisTemplate redis,
            JobHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public boolean processOne() {
        String jobId = redis.opsForList().move(
                PENDING, Direction.LEFT,
                PROCESSING, Direction.RIGHT,
                Duration.ofSeconds(5)
        );

        if (jobId == null) {
            return false; // Hết thời gian chờ mà không có job.
        }

        try {
            handler.handle(jobId);

            Long removed = redis.opsForList()
                    .remove(PROCESSING, 1, jobId);

            if (!Long.valueOf(1L).equals(removed)) {
                // Cần ghi nhận và điều tra: đã ACK/reclaim?
                throw new IllegalStateException(
                        "Job is no longer in processing: " + jobId
                );
            }

            return true;
        } catch (Exception failure) {
            // Không xóa mù job khỏi processing.
            // Reclaimer hoặc chính sách retry sẽ xử lý sau.
            throw failure;
        }
    }

    public interface JobHandler {
        void handle(String jobId);
    }
}
~~~

Đây là **khung minh họa** cho quá trình claim–process–ack, chưa chứa reclaimer, giới hạn retry, idempotency, shutdown và xử lý transaction với database. Lời gọi `processOne()` là blocking, nên chạy từ worker thread có kiểm soát thay vì gọi trực tiếp trên HTTP endpoint.

Nếu `handler.handle(jobId)` ghi thành công dữ liệu nguồn rồi ứng dụng crash trước `LREM`, job vẫn ở processing và có thể bị retry. Handler cần **idempotent** hoặc dùng cơ chế đánh dấu/đối soát với dữ liệu chuẩn, vì hệ thống có thể xử lý lặp.

## 10. Exactly-once hay at-least-once?

Việc chuyển phần tử nguyên tử giải quyết **lost job trong khoảng giữa pop và push**. Nó không bảo đảm exactly-once trong toàn bộ vòng đời công việc.

### 10.1. Trường hợp có thể xử lý trùng

~~~text
Worker A nhận job-101 bằng BLMOVE
Worker A ghi DB thành công
Worker A crash trước LREM ACK

Reclaimer thấy job-101 chưa ACK
Reclaimer đưa job-101 về pending

Worker B nhận job-101
Worker B gọi xử lý lần nữa
~~~

Nếu xử lý nghiệp vụ không idempotent (chẳng hạn trừ tiền hai lần), lần chạy lại có thể gây lỗi nghiêm trọng.

Cần:

- Định danh job/event ổn định và duy nhất.
- Kiểm tra trạng thái nghiệp vụ trước khi thực hiện side effect.
- Sử dụng transaction/idempotency key ở kho dữ liệu chuẩn khi cần.
- Có chính sách retry, backoff và dead-letter.
- Phân biệt **job được nhận**, **job xử lý thành công**, **job được ACK**.

Redis List với pending/processing có thể hỗ trợ mô hình **at-least-once** khi có reclaimer; không tự động tạo exactly-once.

### 10.2. Timeout sau LMOVE/BLMOVE

Nếu server đã chuyển `job-101` sang processing nhưng kết nối mất trước khi trả response, worker có thể nhận exception/timeout và không biết ID nào đã được chuyển.

Retry `BLMOVE` một lần nữa có thể lấy **job khác**. Vì vậy, không tự động xem timeout là “chưa có job nào bị chuyển”. Hệ thống cần cơ chế quan sát processing, định danh worker/claim hoặc phục hồi job không xác nhận.

Một thiết kế đòi hỏi truy vết nghiêm ngặt thường cần cơ chế lease/owner rõ hơn List thuần.

## 11. Khi nào Redis List đủ, khi nào cân nhắc Redis Streams?

Chuyển giữa List thích hợp cho một số queue nhỏ và vừa, đặc biệt khi muốn đơn giản:

- Producer thêm ID; worker nhận bằng `BLMOVE`.
- Có ít consumer, chính sách xử lý và retry không quá phức tạp.
- Có thể tự xây và vận hành reclaimer/ACK theo yêu cầu.
- Không cần đọc lại lịch sử sự kiện, consumer group phức tạp hoặc tracking pending theo nhóm.

Khi nhu cầu lớn hơn, **Redis Streams** thường đáng cân nhắc:

| Nhu cầu | List + LMOVE/BLMOVE | Redis Streams + consumer group |
|---|---|---|
| Nhận phần tử và chờ khi trống | Có, qua `BLMOVE` | Có, qua `XREADGROUP BLOCK` |
| Phân chia công việc cho nhiều consumer | Có thể | Có thể, theo consumer group |
| Theo dõi pending delivery/owner | Phải tự thiết kế | Pending Entries List của consumer group |
| ACK message | Tự dùng `LREM` và metadata | `XACK` |
| Claim message lâu không ACK | Tự thiết kế reclaimer | `XCLAIM`/`XAUTOCLAIM` tùy phiên bản |
| Đọc lại lịch sử message | List không tự giữ event sau khi lấy/ACK | Stream giữ entry đến khi trim/delete |
| Độ phức tạp | Đơn giản ban đầu | Nhiều khái niệm, hỗ trợ workflow rõ hơn |
| Exactly-once processing | Không tự có | Cũng không tự có cho side effect ngoài Redis |

**Streams không tự đảm bảo exactly-once** cho thao tác ở database hoặc hệ thống bên ngoài. Consumer vẫn cần idempotency và thiết kế ACK đúng.

Nếu yêu cầu là delayed jobs, lịch chạy, số lần thử, nhiều consumer group hoặc khả năng audit, cũng cần xem xét queue/broker chuyên dụng. Mô hình dữ liệu nên được chọn từ yêu cầu nghiệp vụ, không chỉ từ việc Redis List có ít lệnh.

## 12. Tương tác với Redis Cluster và nhiều key

`LMOVE`/`BLMOVE` là lệnh đụng đến **hai key**. Trong Redis Cluster, hai key trong cùng một lệnh multi-key phải nằm ở **cùng hash slot**.

Không nên dùng tùy tiện:

~~~text
jobs:pending
jobs:processing
~~~

trong Redis Cluster mà mặc định chúng cùng slot. Nếu khác slot, có thể gặp lỗi:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

### 12.1. Hash tag cho List nguồn và đích

Dùng hash tag giống nhau:

~~~text
jobs:{email}:pending
jobs:{email}:processing
~~~

Redis Cluster tính slot từ phần `email` trong cặp ngoặc nhọn hợp lệ, nên cả hai key nằm cùng slot:

~~~bash
redis-cli -c LMOVE \
  'jobs:{email}:pending' \
  'jobs:{email}:processing' \
  LEFT RIGHT
~~~

Khi hệ thống có nhiều queue độc lập, có thể dùng hash tag khác nhau:

~~~text
jobs:{email}:pending
jobs:{email}:processing

jobs:{invoice}:pending
jobs:{invoice}:processing
~~~

Như vậy mỗi cặp có thể nằm trên các slot khác nhau, cho phép phân bố tải tốt hơn.

**Không dùng một hash tag chung cho mọi queue**, ví dụ `{all-jobs}`, nếu không muốn dồn tất cả thao tác lên một slot. Cũng cần nhớ một queue rất nóng vẫn là một điểm tải tập trung, cho dù có nhiều Redis Cluster primary.

### 12.2. LMOVE không chuyển dữ liệu giữa hai Redis deployment

Nếu nguồn và đích thuộc hai Redis server độc lập không nằm trong cùng một Redis keyspace/command context, `LMOVE` không thể thực hiện nguyên tử giữa chúng. Khi đó cần một quy trình chuyển dữ liệu khác với cơ chế retry, xác nhận và xử lý lỗi. Không suy luận rằng tên key khác nhau nghĩa là có thể vượt ranh giới Redis instance hoặc Cluster.

## 13. Serialization của phần tử List trong Spring Data Redis

Redis List lưu các **byte value** theo thứ tự. `ListOperations` dùng serializer của template đối với member và key.

Với `StringRedisTemplate`:

~~~java
StringRedisTemplate redis = /* bean do Spring quản lý */;

redis.opsForList().rightPush("jobs:pending", "job-101");

String moved = redis.opsForList().move(
        "jobs:pending",
        Direction.LEFT,
        "jobs:processing",
        Direction.RIGHT
);
~~~

Key và phần tử sử dụng quy ước chuỗi, dễ quan sát trong Redis CLI. Khi `LMOVE` chuyển phần tử, Redis **không deserialize và serialize lại value**. Nó chuyển byte của phần tử giữa hai List tại server.

Hệ quả:

- List nguồn và List đích nên cùng một **hợp đồng về định dạng phần tử**.
- Nếu một template ghi JSON object vào nguồn còn consumer dùng String serializer để đọc đích, kết quả có thể là chuỗi JSON hoặc xảy ra lỗi chuyển đổi, tùy API và serializer.
- Nếu nguồn chứa byte JDK serialization, dùng Redis CLI đọc như text có thể khó hiểu.
- Không thay serializer khi hệ thống còn message cũ mà chưa có kế hoạch xử lý tương thích.

### 13.1. Phần tử là ID hay toàn bộ payload?

Hai hướng phổ biến:

**Chỉ lưu ID:**

~~~text
jobs:pending = [job-101, job-102, job-103]
~~~

Payload nằm ở nơi lưu khác hoặc một Hash theo ID. Dễ ACK theo ID, rẻ băng thông và tránh truyền payload lớn qua mỗi lần chuyển.

**Lưu JSON payload:**

~~~text
jobs:pending = [
  {"jobId":"job-101","type":"EMAIL","recipientId":"u-1"},
  {"jobId":"job-102","type":"REPORT","reportId":"r-7"}
]
~~~

Đơn giản khi job nhỏ và tự chứa, nhưng cần quản lý schema JSON, uniqueness, kích thước message và độ tương thích khi deploy. `LREM` so khớp **giá trị phần tử**; nếu tạo lại JSON khác byte, việc ACK theo JSON có thể thất bại.

Trong queue cần retry/reclaim rõ ràng, một **ID ổn định** thường giúp thiết kế đơn giản hơn.

### 13.2. TTL thuộc về key List, không phải từng phần tử

Ví dụ:

~~~bash
redis-cli EXPIRE jobs:pending 600
redis-cli TTL jobs:pending
~~~

TTL áp dụng cho **toàn bộ List key**. Chuyển một phần tử sang `jobs:processing` không mang theo một “TTL của phần tử”, vì Redis List không có TTL độc lập cho từng member theo mô hình này.

Không đặt TTL quá ngắn cho `processing` nếu những job đang chạy chưa được xác nhận; khi List key hết hạn, các phần tử còn bên trong cũng biến mất. Ngược lại, nếu không có TTL và không có reclaimer, `processing` có thể chứa job bị bỏ quên vô thời hạn.

Nếu cần thời hạn từng job, hãy lưu deadline/metadata riêng và có cơ chế cleanup phù hợp.

## 14. Phạm vi nguyên tử và ranh giới của thao tác nhiều key

Những tính chất cần phân biệt:

| Thuộc tính | LMOVE/BLMOVE cung cấp? | Giải thích |
|---|---|---|
| Lấy một phần tử và đưa sang List khác trong một lệnh | **Có** | Không có khoảng trống giữa pop và push ở Redis server |
| Hai consumer cùng lấy chính một phần tử ở nguồn | **Không**, mỗi lệnh nhận một phần tử đang có | Nhưng có thể có **hai phần tử trùng giá trị** do producer thêm trùng |
| Chờ đến khi nguồn có dữ liệu | `BLMOVE` có; `LMOVE` không | Cần cấu hình timeout thích hợp |
| Xác nhận job đã xử lý xong | **Không** | Phải ACK sau khi business handler thành công |
| Chọn và chuyển một job bất kỳ theo ID | **Không** | LMOVE chỉ lấy ở một đầu List |
| Xử lý giao dịch database và ACK cùng lúc | **Không** | Cần thiết kế consistency và idempotency riêng |
| Tự phục hồi job của worker đã chết | **Không** | Cần reclaimer/lease/metadata |
| Chịu được failover mà không thể mất một ghi nào | **Không tự bảo đảm** | Redis replication/persistence có đặc tính riêng |
| Chuyển giữa các hash slot khác nhau trong Cluster | **Không** | Các key phải cùng slot cho lệnh multi-key |

Bảng này giúp tránh nhầm giữa **atomic transfer**, **reliable delivery** và **exactly-once business execution**.

## 15. Các lỗi thường gặp

### Lỗi 1 — Dùng LPOP rồi RPUSH và cho rằng đã an toàn

Đó là hai lệnh; worker có thể crash giữa chừng. Khi mục đích là chuyển nguyên tử, dùng `LMOVE` hoặc `BLMOVE`.

### Lỗi 2 — Chọn sai hướng dẫn tới đảo thứ tự FIFO

Producer `RPUSH` theo thứ tự cũ → mới, consumer lại `LMOVE RIGHT LEFT` sẽ lấy phần tử **mới nhất** trước. Nếu muốn FIFO với `RPUSH`, hãy lấy `LEFT`.

### Lỗi 3 — Coi giá trị null là lỗi trong mọi trường hợp

`LMOVE` có thể trả nil khi nguồn trống; `BLMOVE` trả nil khi hết thời gian chờ. Spring thường trả null cho các trường hợp này. Cần phân biệt với exception do timeout phía client, ngắt mạng hoặc command lỗi.

### Lỗi 4 — Để BLMOVE chờ vô hạn trong web request

Blocking không có giới hạn có thể giữ thread và connection, làm nghẽn ứng dụng. Dùng worker executor, timeout hữu hạn và cơ chế shutdown thích hợp.

### Lỗi 5 — Dùng processing List nhưng không bao giờ ACK

Công việc đã xử lý thành công vẫn nằm trong `processing`, khiến bộ nhớ tăng và reclaimer có thể chạy lại job. Chỉ ACK khi xử lý thành công, và theo dõi số job chưa ACK.

### Lỗi 6 — ACK bằng LREM với giá trị có thể trùng

Nếu List chứa hai phần tử đều bằng `"job-101"`, `LREM ... 1 job-101` không biết lượt xử lý nào đang được xác nhận. Dùng job ID duy nhất hoặc mô hình có claim ID/lease.

### Lỗi 7 — Tưởng LMOVE có thể lấy một phần tử ở giữa List

`LMOVE` chỉ lấy LEFT hoặc RIGHT. Để reclaim một job cụ thể, cần thao tác theo ID và cơ chế đồng bộ tương ứng; không tự `LMOVE` phần tử đầu của processing với hy vọng nó chính là job lỗi.

### Lỗi 8 — Đưa List nguồn và đích vào hai hash slot khác nhau

Trong Redis Cluster, `LMOVE source destination ...` chạm hai key, cần cùng slot. Dùng hash tag theo **cặp queue/partition**, không dùng cùng một tag cho toàn hệ thống.

### Lỗi 9 — Tưởng atomic transfer nghĩa là exactly-once

Job có thể được xử lý xong nhưng chưa ACK khi crash. Reclaimer đưa job về pending sẽ gây xử lý lại. Hãy thiết kế handler idempotent và đối soát dữ liệu chuẩn.

### Lỗi 10 — Dùng serializer khác nhau khi đọc nguồn và đích

Redis chuyển byte phần tử nguyên vẹn, không tự chuyển JSON sang Java object hay đổi encoding. Consumer phải hiểu cùng định dạng.

### Lỗi 11 — Dùng một List processing vô hạn

`LREM` có thể tốn thời gian khi List lớn; theo dõi `LLEN processing`, giới hạn workload và cân nhắc phân vùng hoặc Redis Streams khi yêu cầu ACK/claim phức tạp.

### Lỗi 12 — Đóng socket hoặc tùy tiện retry khi timeout

Nếu lệnh đã được Redis xử lý nhưng response mất, retry có thể claim job tiếp theo. Không coi timeout đồng nghĩa với lệnh chưa chạy; cần mô hình recover rõ ràng.

## 16. Quan sát và vận hành với Redis CLI

Kiểm tra các List:

~~~bash
redis-cli TYPE jobs:pending
redis-cli TYPE jobs:processing

redis-cli LLEN jobs:pending
redis-cli LLEN jobs:processing

redis-cli LRANGE jobs:pending 0 9
redis-cli LRANGE jobs:processing 0 9
~~~

`LRANGE 0 9` chỉ đọc tối đa 10 phần tử đầu tiên, hữu ích để quan sát. Tránh `LRANGE key 0 -1` trên List có thể rất lớn trong những công cụ kiểm tra chạy thường xuyên.

Kiểm tra TTL và bộ nhớ:

~~~bash
redis-cli TTL jobs:pending
redis-cli TTL jobs:processing

redis-cli MEMORY USAGE jobs:pending
redis-cli MEMORY USAGE jobs:processing

redis-cli INFO memory
redis-cli INFO stats
~~~

Ý nghĩa:

- `LLEN`: số phần tử hiện có.
- `TYPE`: bảo đảm key là List trước khi thực hiện List operation.
- `TTL = -1`: key tồn tại nhưng không có expiration; `TTL = -2`: key không tồn tại.
- `MEMORY USAGE`: mức RAM Redis ước lượng cho key/value.
- `INFO`: tình trạng tài nguyên và thống kê Redis.

Một số chỉ số cần giám sát ở phía ứng dụng:

| Chỉ số | Ý nghĩa |
|---|---|
| `pending_length` | Công việc đang chờ tăng hay giảm |
| `processing_length` | Công việc đã claim nhưng chưa ACK |
| Thời gian chờ `BLMOVE` | Queue thiếu dữ liệu hay worker thường xuyên phải đợi |
| Thời gian xử lý p50/p95/p99 | Có job chậm khiến backlog tăng không |
| Số ACK thành công/thất bại | Luồng hoàn tất có hoạt động đúng không |
| Số job được reclaim/retry | Worker crash hoặc timeout thường xuyên đến mức nào |
| Số duplicate business events | Handler có thật sự idempotent không |
| Redis command timeout/connection errors | Có rủi ro claim thành công nhưng client không biết không |
| Redis memory/evicted keys | Có nguy cơ mất queue hoặc payload do cấu hình tài nguyên không |

Không chỉ quan sát `pending`. Một queue có `pending = 0` nhưng `processing` tăng liên tục không nhất thiết là hệ thống khỏe; có thể job bị kẹt sau claim.

## 17. Bài tập thực hành

### Bài tập 1 — FIFO với RPUSH

Cho:

~~~text
source      = [job-A, job-B, job-C]
destination = []
~~~

Producer dùng `RPUSH` để thêm theo thứ tự A, B, C. Lệnh nào lấy A đầu tiên và đưa vào cuối destination?

**Đáp án:**

~~~text
LMOVE source destination LEFT RIGHT
~~~

Sau lệnh:

~~~text
source      = [job-B, job-C]
destination = [job-A]
~~~

### Bài tập 2 — Hiểu chiều của RPOPLPUSH

Cho:

~~~text
source      = [A, B, C]
destination = [X, Y]
~~~

Lệnh:

~~~text
RPOPLPUSH source destination
~~~

tương đương:

~~~text
LMOVE source destination RIGHT LEFT
~~~

Kết quả:

~~~text
source      = [A, B]
destination = [C, X, Y]
Giá trị trả về = C
~~~

### Bài tập 3 — Blocking timeout

Một worker gọi:

~~~text
BLMOVE jobs:pending jobs:processing LEFT RIGHT 5
~~~

và không có producer thêm job trong 5 giây.

**Kết quả:** Redis trả nil khi timeout; trong lời gọi Spring Data Redis trực tiếp thường nhận null. Nếu application nhận exception timeout phía client sau 2 giây, đó là lỗi cấu hình/thời gian chờ phía client khác với kết quả nil hợp lệ.

### Bài tập 4 — Worker crash sau claim

Worker nhận `job-42` bằng `LMOVE`, ghi database thành công rồi crash trước khi `LREM`.

**Điều có thể xảy ra:** `job-42` vẫn nằm trong processing; reclaimer có thể gửi job trở lại pending; worker khác chạy lại cùng job. Cần đảm bảo cập nhật database hoặc side effect có idempotency.

### Bài tập 5 — Redis Cluster báo CROSSSLOT

Hai key:

~~~text
queue:pending
queue:processing
~~~

được phân về hai slot khác nhau. `LMOVE` không thể thực thi qua hai slot.

**Cách điều chỉnh ví dụ:**

~~~text
queue:{orders}:pending
queue:{orders}:processing
~~~

Cùng hash tag giúp cả hai key nằm cùng slot. Đối với các queue độc lập, chọn tag riêng để có thể phân tải.

### Bài tập 6 — Chọn cấu trúc cho queue có nhiều worker

Yêu cầu: hàng nghìn job/giây, nhiều consumer, cần biết job thuộc worker nào, reclaim job vượt deadline, lịch sử message, retry nhiều lần và dead-letter.

**Hướng quyết định:** `LMOVE`/`BLMOVE` có thể làm thao tác claim, nhưng một List processing đơn giản chưa có toàn bộ metadata. Cần bổ sung cấu trúc quản lý đáng kể hoặc cân nhắc Redis Streams consumer groups/broker chuyên dụng.

## 18. Quy trình chọn thao tác chuyển List

~~~text
                  Cần chuyển phần tử giữa hai List
                                  |
                    Phải lấy theo thứ tự nào?
                        /                  \
               Lấy phần tử đầu         Lấy phần tử cuối
                    LEFT                    RIGHT
                        \                    /
                         +--------+---------+
                                  |
                     Đưa vào đầu hay cuối đích?
                           LEFT / RIGHT
                                  |
                    Cần chờ khi nguồn trống?
                          /            \
                         Có            Không
                          |              |
                        BLMOVE         LMOVE
                          \              /
                           +------------+
                                  |
                     Dùng Redis Cluster không?
                          /           \
                         Có           Không
                          |
                   Source/dest cùng slot
                          |
                     Claim job để xử lý?
                          /           \
                         Có           Không
                          |              |
               Processing + ACK          Hoàn tất
               + Retry/Reclaimer
                          |
               Idempotency + giám sát
~~~

Có thể ghi nhớ:

- **`LMOVE source destination from to`**: chuyển ngay một phần tử bằng một lệnh nguyên tử, trả nil nếu nguồn trống.
- **`BLMOVE source destination from to timeout`**: tương tự nhưng chờ khi nguồn trống.
- **`ListOperations.move(...)`**: API Spring Data Redis thể hiện rõ cả hai hướng và có phiên bản blocking dùng `Duration`.
- **`rightPopAndLeftPush(...)`**: API cũ hữu ích khi đọc hệ thống legacy, tương ứng `RIGHT → LEFT`.
- **`pending → processing`**: giải quyết khoảng trống giữa pop và push, nhưng cần ACK, idempotency và recovery để tạo workflow xử lý công việc đáng tin cậy.

Chuyển phần tử giữa hai List là một thao tác nhỏ ở Redis nhưng có ý nghĩa lớn đối với thiết kế queue. Hãy xác định đúng thứ tự LEFT/RIGHT, dùng chuyển nguyên tử, hiểu rõ thời gian chờ của worker và bổ sung cơ chế xác nhận/phục hồi khi công việc thực sự cần được xử lý tin cậy.
