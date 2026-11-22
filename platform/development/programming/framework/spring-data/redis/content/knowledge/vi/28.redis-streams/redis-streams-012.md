# Điều tiết nhu cầu, tạm dừng tiêu thụ và rủi ro lệch offset

**Redis Streams** cho phép ứng dụng lưu sự kiện dưới dạng các entry có ID và đọc chúng về sau. Với **Spring Data Redis**, có thể tiêu thụ stream qua `StreamOperations`, `StreamMessageListenerContainer` hoặc `StreamReceiver` (reactive). Tuy nhiên, việc Redis lưu được nhiều thông điệp không có nghĩa ứng dụng có thể nhận và xử lý không giới hạn.

Khi producer ghi nhanh hơn consumer xử lý, ứng dụng cần **điều tiết nhu cầu (backpressure)**: giới hạn batch, giới hạn tác vụ đang chạy, tạm dừng poll khi nguồn xử lý quá tải và tiếp tục khi có năng lực. Trong lúc đó xuất hiện rủi ro nghiêm trọng: **lệch offset**, tức vị trí được coi là đã đọc hoặc đã tiêu thụ tiến xa hơn phần công việc đã thực sự hoàn thành.

Bài học tập trung vào sự khác nhau giữa **đã ghi vào stream**, **đã giao cho consumer** và **đã xử lý thành công**; cách pause/resume an toàn; những điểm dễ mất hoặc lặp sự kiện; và quy trình phục hồi bằng consumer group và Pending Entries List (PEL).

## 1. Vì sao phải điều tiết nhu cầu?

Giả sử producer ghi 2.000 sự kiện đơn hàng/giây vào một Redis Stream, trong khi một consumer chỉ hoàn tất 200 sự kiện/giây vì mỗi sự kiện cần cập nhật database.

```text
Producer: 2000 events/s
         |
         v
   Redis Stream
   [1][2][3][4][5]......................
         |
         v
Consumer: 200 events/s
         |
         v
   Business handler
         |
         v
       Database
```

Nếu consumer cố đọc liên tục rồi đưa mọi event vào một executor không giới hạn, nó có thể tạo hàng chục nghìn task đang chờ, làm cạn bộ nhớ, connection pool hoặc thread pool. Khi tiến trình crash, một số task đã được nhận nhưng chưa xử lý xong.

Biện pháp không phải là đánh dấu message đã hoàn thành để giảm backlog, mà là **giới hạn số lượng entry được giao vào ứng dụng theo khả năng xử lý thật**. Nếu handler chậm, giảm hoặc tạm ngừng việc bắt đầu lô mới; những entry chưa được giao tiếp tục nằm trong stream nếu chính sách lưu giữ cho phép.

Backpressure có giới hạn: consumer tạm dừng nhưng producer vẫn ghi thì backlog trên Redis tăng. Nếu tốc độ tạo sự kiện luôn cao hơn tổng tốc độ xử lý, backlog sẽ không tự giảm, kể cả sau khi resume.

## 2. Các khái niệm phải phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| **Stream ID** | ID có thứ tự gắn với một entry do `XADD` tạo |
| **Read offset** | Vị trí hoặc quy tắc xác định các entry cần lấy khi đọc |
| **Consumer group** | Nhóm các consumer chia sẻ tiến độ phân phối và trạng thái pending |
| **Last-delivered ID** | Mốc Redis đã giao đến trong group, không chứng minh đã xử lý thành công |
| **Pending Entries List (PEL)** | Tập entry đã giao cho group nhưng chưa được `XACK` |
| **ACK** | Xác nhận entry đã xử lý theo hợp đồng nghiệp vụ của consumer |
| **Demand** | Số lượng phần tử downstream sẵn sàng nhận, đặc biệt trong Reactive Streams |
| **Pause** | Tạm ngừng bắt đầu các lần đọc/lô nhận mới |
| **Resume** | Tiếp tục đọc từ trạng thái phù hợp, không tự bỏ qua công việc chưa hoàn tất |
| **Retention** | Chính sách giữ entry trong stream, bao gồm trim/xóa khi hết giới hạn |

Một event trong consumer group đi qua luồng:

```text
XADD thành công
    |
    v
Entry được lưu trong stream
    |
    v
XREADGROUP phân phối cho consumer
    |
    +------------------> PEL ghi nhận đã giao, chưa ACK
    |
    v
Business handler thực thi
    |
    +-- lỗi/crash ------> vẫn cần recovery PEL
    |
    v
Side effect thành công
    |
    v
XACK
    |
    v
PEL không còn entry đó
```

**XACK không xóa entry khỏi stream.** Nó xác nhận hoàn tất đối với một consumer group. Stream entry vẫn tồn tại cho tới khi bị xóa hoặc trim theo chính sách.

Nếu pause diễn ra **trước khi đọc**, event mới có thể nằm trong stream nhưng chưa được phân phối cho group. Nếu pause/crash diễn ra **sau khi nhận nhưng trước ACK**, event thường đã nằm trong PEL. Hai nhóm dữ liệu này cần hai đường tiếp tục khác nhau.

## 3. XREAD và XREADGROUP sử dụng offset khác nhau

### 3.1. Đọc trực tiếp bằng XREAD

Một client có thể đọc các entry có ID lớn hơn ID được chỉ định:

```redis
XREAD COUNT 10 STREAMS stream:orders:v1 0-0
```

Nếu client lưu checkpoint là ID cuối **đã xử lý xong**, nó có thể đọc tiếp sau restart:

```redis
XREAD COUNT 10 STREAMS stream:orders:v1 1780000000000-0
```

Nhưng `XREAD` không có PEL, không có Redis-managed ACK cho business handler. Ứng dụng phải tự lưu checkpoint và quyết định khi nào mốc được phép tăng.

Ví dụ sai:

```text
Đọc batch: 101, 102, 103, 104, 105
    |
    v
Lưu checkpoint = 105 ngay sau khi nhận
    |
    v
Handler hoàn thành 101, 102
    |
    v
JVM crash trước 103
    |
    v
Restart đọc sau 105
    |
    v
103, 104, 105 bị bỏ qua
```

Với xử lý tuần tự, checkpoint nên tiến theo ID **cuối cùng đã hoàn thành**. Với xử lý song song, checkpoint an toàn là mốc **liên tiếp đã hoàn thành**, không nhất thiết bằng ID lớn nhất đã xử lý. Nếu 105 xong nhưng 103 chưa xong, checkpoint vượt 103 có thể gây mất message sau restart.

### 3.2. Đọc bằng consumer group

Tạo nhóm:

```redis
XGROUP CREATE stream:orders:v1 order-workers 0 MKSTREAM
```

`0` cho phép nhóm đọc từ các entry đã tồn tại; nếu tạo nhóm với `$`, các entry cũ trước mốc đó có thể bị bỏ qua trong luồng đọc message mới. Sau khi tạo group:

```redis
XREADGROUP GROUP order-workers worker-a COUNT 10 BLOCK 2000 STREAMS stream:orders:v1 >
```

Ký hiệu `>` yêu cầu các entry mới chưa được group phân phối theo quy tắc của consumer group. Những entry được giao sẽ nằm trong PEL cho đến khi có ACK:

```redis
XACK stream:orders:v1 order-workers 1780000000000-0
```

Nhờ PEL, một entry đã phân phối nhưng chưa ACK còn có khả năng phục hồi sau crash, miễn payload stream chưa bị xóa/trim. Tuy nhiên, **đọc `>` sau khi restart không tự đọc lại PEL cũ**. Một consumer cần quy trình recovery pending riêng, thay vì coi luồng new messages là toàn bộ công việc còn thiếu.

## 4. Rủi ro ReadOffset.latest(): bỏ qua dữ liệu trong khoảng không poll

Trong Spring Data Redis, `ReadOffset` giúp chỉ định cách xác định mốc đọc. Một lựa chọn dễ gây sai khi tạm dừng là `ReadOffset.latest()`.

Giả sử consumer đọc từ “latest” ở mỗi lần poll:

```text
T0: Stream đã có entry 100-0.
T1: Poll từ latest và nhận entry 101-0.
T2: Downstream demand = 0; consumer ngừng poll.
T3: Producer ghi entry 102-0 và 103-0.
T4: Downstream có demand; poll mới lại bắt đầu từ latest.
T5: Producer ghi entry 104-0.
```

Nếu tại T4 latest tương ứng với 103-0, consumer có thể chỉ nhận 104-0 và **bỏ qua 102-0, 103-0** trong luồng đã đăng ký. Những entry này có thể vẫn còn trên Redis nhưng đã bị mốc đọc mới nhảy qua.

| Kiểu offset | Ý nghĩa điển hình | Điểm cần chú ý |
|---|---|---|
| `ReadOffset.latest()` | Theo dõi những entry đến sau mốc latest | Dễ bỏ qua entry giữa các lần polling hoặc khi demand ngừng |
| `ReadOffset.from(id)` | Lấy các entry có ID lớn hơn một mốc đã biết | Mốc phải dựa trên tiến độ thực sự được chấp nhận |
| `ReadOffset.from("0-0")` | Đọc từ đầu phần stream còn lưu trong mô hình đọc trực tiếp | Có thể đọc lại lịch sử nếu không có checkpoint |
| `ReadOffset.lastConsumed()` trong consumer group | Sử dụng tiến độ phân phối của group để nhận message mới | Không tự giải quyết PEL đã phân phối chưa ACK |
| `ReadOffset.lastConsumed()` trong đọc trực tiếp | Dùng mốc đã tiêu thụ theo cơ chế receiver | Phải hiểu mốc cập nhật khi nhận hay khi handler đã xử lý |

**Không sử dụng latest như đồng nghĩa với “resume từ đúng chỗ đã dừng”** khi sự kiện không được phép mất. Với luồng quan trọng, dùng consumer group cùng recovery hoặc checkpoint bền dựa trên tiến độ xử lý.

## 5. Reactive demand không tự giải quyết độ tin cậy

Trong Reactor, downstream có thể yêu cầu một số lượng phần tử nhất định. Khi không còn demand, `StreamReceiver` có thể tạm dừng polling. Tuy nhiên, hai câu hỏi khác nhau cần được trả lời:

1. **Khi nào downstream sẵn sàng nhận thêm?**
2. **Sau khi sẵn sàng, Redis sẽ đọc lại từ offset nào?**

```text
Reactive downstream yêu cầu N entry
                  |
                  v
      StreamReceiver poll Redis
                  |
                  v
       Phát entry xuống Flux
                  |
                  v
             Demand = 0
                  |
      Receiver có thể ngừng poll
                  |
             Producer XADD thêm
                  |
                  v
         Demand tăng trở lại
                  |
                  v
      Poll tiếp từ offset được cấu hình
           |
           +-- latest: có thể skip entry giữa hai poll
           |
           +-- checkpoint/group phù hợp:
               có đường tiếp tục đọc những entry còn giữ
```

Hơn nữa, **một entry đã được phát vào Flux chưa chắc đã được nghiệp vụ xử lý thành công**. Nếu downstream dùng async handler rồi cancel subscription khi handler còn chạy, mốc “đã phát” không đủ làm checkpoint an toàn.

### 5.1. Concurrency phải có giới hạn

Với Reactor, có thể tổ chức luồng theo ý tưởng:

```java
source.concatMap(record ->
        handleBusiness(record)
                .then(acknowledgeAfterSuccess(record)));
```

Đây là **mẫu minh họa luồng xử lý**, không phải lời gọi API Spring Data Redis hoàn chỉnh: `handleBusiness` và `acknowledgeAfterSuccess` là các hàm reactive do ứng dụng định nghĩa.

`concatMap` xử lý phần tử theo thứ tự đầu vào, giảm nguy cơ nhiều side effect đồng thời. `flatMap` có thể tăng throughput khi dùng concurrency giới hạn, nhưng message có thể hoàn tất và ACK không theo thứ tự. Nếu nghiệp vụ yêu cầu xử lý đúng thứ tự theo đơn hàng, cần thêm cơ chế serialize theo aggregate hoặc cách phân vùng công việc tương ứng.

### 5.2. Auto-ACK không giống commit side effect

Spring Data Redis có biến thể hỗ trợ ACK tự động trong reactive receiver. Khi dùng auto-ACK, phải hiểu đúng thời điểm ACK theo hợp đồng API, không tự giả định rằng nó chờ tất cả thao tác bất đồng bộ của business handler đã commit. Nếu crash sau khi message được ACK nhưng trước khi lưu kết quả nghiệp vụ, PEL không còn entry để retry.

**Với workflow không được mất event, ưu tiên ACK tường minh sau khi handler thành công**, đồng thời chuẩn bị idempotency cho trường hợp commit thành công nhưng chưa kịp ACK.

## 6. Backpressure cần điều khiển số lượng in-flight

Sự cố phổ biến không chỉ đến từ `ReadOffset` mà còn từ cách consumer dùng thread pool.

Sai về mặt ý tưởng:

```java
for (MapRecord<String, Object, Object> record : records) {
    executor.submit(() -> handler.handle(record.getValue()));

    // Nguy hiểm: chỉ mới đưa task vào queue.
    redis.opsForStream().acknowledge(
            STREAM, GROUP, record.getId());
}
```

Nếu crash sau ACK nhưng trước khi worker thực thi task, event đã bị group xác nhận hoàn tất. Sau restart, đường đọc `>` bình thường sẽ không phát lại event đó.

Luồng phù hợp hơn:

```text
Có slot xử lý trống?
         |
         v
XREADGROUP COUNT <= availableSlots
         |
         v
Giao message cho handler
         |
         v
Handler xử lý và commit thành công
         |
         v
XACK entry tương ứng
         |
         v
Giải phóng slot in-flight
```

Ví dụ thiết kế:

```text
MAX_IN_FLIGHT = 100
POLL_BATCH_SIZE = 20
PAUSE_THRESHOLD = 80
RESUME_THRESHOLD = 40
```

Đây là tham số minh họa, không phải cấu hình mặc định của Redis. Khi số in-flight >= 80, consumer có thể dừng lấy lô mới. Khi số in-flight giảm xuống <= 40, tiếp tục poll. Hai ngưỡng khác nhau giúp tránh bật/tắt liên tục.

Khi chỉ còn 5 slot, không nên gọi `XREADGROUP COUNT 20` rồi mới tìm chỗ xử lý: Redis có thể đã giao 20 entry và tạo pending không cần thiết. Hãy điều chỉnh `COUNT` theo số slot thật hoặc chờ có đủ năng lực.

Nếu producer vẫn ghi nhanh hơn tổng throughput của consumer, cần scale-out, tăng hiệu quả handler, giảm tốc độ producer hoặc chọn retention/backlog đủ lớn. Pause không làm tải hệ thống biến mất.

## 7. Tạm dừng đúng cách: ngừng fetch, không ngụy tạo hoàn thành

Trong imperative poll loop, pause có thể đơn giản là **không gọi XREADGROUP thêm**. Với listener container hoặc reactive receiver, có thể cần dừng subscription hoặc điều chỉnh demand; nhưng cancellation hay stop không mặc nhiên chờ tất cả handler hoàn tất.

Một pause có kiểm soát cần:

1. Ngừng bắt đầu những lần đọc mới.
2. Ngừng nhận thêm task vào executor khi đã đầy.
3. Chờ hoặc quản lý các handler đang thực thi.
4. Chỉ ACK những entry đã hoàn tất side effect.
5. Giữ entry chưa ACK để phục hồi qua PEL.
6. Đảm bảo retention đủ dài cho thời gian pause.
7. Khi resume, xử lý cả message mới lẫn pending cũ.

**Không pause bằng cách chuyển group offset đến cuối stream hoặc ACK hàng loạt để “giảm lag”.** Những hành động đó thay đổi semantics xử lý thay vì điều tiết nhu cầu.

### Pause trước khi đọc và pause sau khi đọc

```text
Trường hợp A:
    Producer XADD 101, 102, 103
    Consumer đang pause, chưa XREADGROUP
    -> 101, 102, 103 có thể còn là backlog chưa phân phối

Trường hợp B:
    Consumer XREADGROUP nhận 101, 102, 103
    Handler mới hoàn tất 101
    Consumer dừng
    -> 102, 103 có thể nằm trong PEL, chưa ACK
```

Để resume an toàn, A cần đọc tiếp new entries; B còn cần cơ chế khôi phục các ID đã giao nhưng chưa xử lý.

## 8. Thử pause và resume bằng Redis CLI

Tạo stream/group test:

```bash
redis-cli XGROUP CREATE stream:orders:demo order-workers 0 MKSTREAM
```

Producer ghi ba event:

```bash
redis-cli XADD stream:orders:demo '*' eventId evt-1 type CREATED
redis-cli XADD stream:orders:demo '*' eventId evt-2 type PAID
redis-cli XADD stream:orders:demo '*' eventId evt-3 type PACKED
```

Consumer nhận tối đa hai event:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 2 STREAMS stream:orders:demo '>'
```

Sau khi xử lý thành công, ACK các ID thực nhận. Không thay placeholder trong ví dụ thành ký tự so sánh khi chạy Redis:

```text
XACK stream:orders:demo order-workers <ID-thuc-cua-evt-1> <ID-thuc-cua-evt-2>
```

Bây giờ **tạm dừng** bằng cách không gọi `XREADGROUP`. Producer vẫn gửi:

```bash
redis-cli XADD stream:orders:demo '*' eventId evt-4 type SHIPPED
redis-cli XADD stream:orders:demo '*' eventId evt-5 type DELIVERED
```

Khi tiếp tục:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 10 STREAMS stream:orders:demo '>'
```

Những message chưa được group phân phối vẫn có thể được đọc nếu chưa bị xóa/trim. Nhưng nếu consumer đã nhận event rồi crash trước ACK, cần thêm luồng recovery PEL, không chỉ gọi `>`.

## 9. Ví dụ Java: poll theo lô và pause/resume với Spring Data Redis

Một cách dễ kiểm soát là dùng `StringRedisTemplate.opsForStream().read(...)` để đọc mỗi batch tối đa một số entry, xử lý đồng bộ và ACK sau thành công.

Ví dụ giả định consumer group `order-workers` đã được tạo trước bằng lệnh triển khai/hạ tầng. Tách phần tạo group khỏi vòng đọc tránh việc nhiều replica cạnh tranh tạo một group không tồn tại.

### 9.1. Bật scheduler

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class OrderStreamSchedulingConfig {
}
```

### 9.2. Handler nghiệp vụ

```java
import java.util.Map;

public interface OrderEventHandler {
    // Trả về thành công khi side effect đã hoàn tất.
    // Ném exception nếu không thể xác nhận đã xử lý.
    void handle(Map<Object, Object> event);
}
```

### 9.3. Consumer có pause flag

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamPoller {

    private static final Logger log =
            LoggerFactory.getLogger(OrderStreamPoller.class);

    private static final String STREAM = "stream:orders:v1";
    private static final String GROUP = "order-workers";
    private static final String CONSUMER = "order-worker-a";

    private final AtomicBoolean paused = new AtomicBoolean(false);
    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamPoller(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public void pauseNewReads() {
        paused.set(true);
    }

    public void resumeNewReads() {
        paused.set(false);
    }

    public boolean isPaused() {
        return paused.get();
    }

    @Scheduled(fixedDelayString = "${app.orders.poll-delay-ms:200}")
    public void pollOnce() {
        if (paused.get()) {
            return; // Không nhận batch mới khi đã pause.
        }

        List<MapRecord<String, Object, Object>> records;

        try {
            records = redis.opsForStream().read(
                    Consumer.from(GROUP, CONSUMER),
                    StreamReadOptions.empty()
                            .count(10)
                            .block(Duration.ofMillis(200)),
                    StreamOffset.create(
                            STREAM, ReadOffset.lastConsumed()));
        } catch (RuntimeException error) {
            log.warn("Unable to poll Redis Stream", error);
            return;
        }

        if (records == null || records.isEmpty()) {
            return;
        }

        for (MapRecord<String, Object, Object> record : records) {
            try {
                handler.handle(record.getValue());

                // Chỉ ACK sau khi nghiệp vụ đã hoàn tất.
                redis.opsForStream().acknowledge(
                        STREAM, GROUP, record.getId());
            } catch (RuntimeException error) {
                log.error(
                        "Event not acknowledged: {}",
                        record.getId(), error);

                // Event lỗi vẫn cần đường retry/recovery PEL.
                break;
            }
        }
    }
}
```

Cách này có đặc tính:

- `count(10)` giới hạn số entry được nhận một lần.
- `block(200ms)` chờ ngắn khi chưa có entry mới, tránh poll liên tục không cần thiết.
- `fixedDelay` tạo nhịp đọc sau khi lần gọi trước hoàn thành.
- Khi `paused = true`, không đọc batch tiếp theo. Nếu bật pause **trong lúc đang xử lý batch**, ví dụ vẫn hoàn tất batch đó; đây là kiểu *drain in-flight* đơn giản.
- Handler ném exception thì message lỗi và các entry chưa ACK cần được phục hồi sau.
- Không tăng checkpoint thủ công sang latest khi resume; group vẫn quản lý trạng thái phân phối.
- **Ví dụ chưa triển khai recovery PEL** và chỉ dùng một instance để minh họa. Production cần thêm quy trình khởi động lại/claim pending.

Với nhiều replica, không đặt tất cả consumer cùng một tên `order-worker-a` mà không có quy tắc ownership. Mỗi instance/slot thường có tên consumer riêng; worker mới cần claim pending của worker cũ sau thời gian idle thích hợp.

Đây là một ví dụ **đọc đồng bộ** để dễ thấy ranh giới ACK. Nếu handler chuyển sang async executor, phải giới hạn in-flight và ACK ở callback hoàn tất, không ACK khi vừa submit.

## 10. Không ACK khi chỉ mới enqueue task

Sai lầm:

```java
for (MapRecord<String, Object, Object> record : records) {
    executor.submit(() -> handler.handle(record.getValue()));

    redis.opsForStream().acknowledge(
            STREAM, GROUP, record.getId()); // Quá sớm!
}
```

Nếu crash sau ACK nhưng trước khi task bắt đầu, event sẽ không còn pending; consumer group không có căn cứ tự phát lại.

Thay vào đó:

```text
XREADGROUP
    |
    v
Kiểm tra slot trong bounded executor
    |
    v
Submit task
    |
    v
Task xử lý và commit thành công
    |
    v
XACK entry tương ứng
```

Khi xử lý song song, ACK có thể xảy ra không theo thứ tự ID. Điều đó được phép đối với mô hình consumer group nếu nghiệp vụ không yêu cầu hoàn tất tuyệt đối theo thứ tự. Nếu cập nhật cùng một aggregate mà thứ tự quan trọng, cần serialize theo aggregate, version-check hoặc chia phân vùng xử lý thích hợp.

**ACK là xác nhận nghiệp vụ**, không phải tín hiệu “message đã đưa vào queue nội bộ”.

## 11. Pending Entries List: phục hồi sau crash

PEL cho biết message đã được giao nhưng chưa ACK. Kiểm tra:

```bash
redis-cli XPENDING stream:orders:v1 order-workers
```

Muốn xem chi tiết một số entry:

```bash
redis-cli XPENDING stream:orders:v1 order-workers - + 20
```

Có thể thấy ID, consumer sở hữu, idle time và số lần giao. Đây là cách nhận ra tình trạng có message chưa hoàn tất dù chương trình vẫn đang đọc được event mới.

### 11.1. Đọc pending do chính consumer đã nhận

Trong consumer group, dùng ID cụ thể như `0` thay vì `>` để đọc pending của **chính consumer đó**:

```bash
redis-cli XREADGROUP GROUP order-workers worker-a \
    COUNT 10 STREAMS stream:orders:v1 0
```

Đường này không tự lấy pending do một consumer khác sở hữu.

### 11.2. Claim pending của consumer bị chết

Worker B có thể nhận lại pending idle của worker A bằng `XAUTOCLAIM`:

```bash
redis-cli XAUTOCLAIM stream:orders:v1 order-workers worker-b \
    60000 0-0 COUNT 50
```

Ở đây `60000` là idle time tối thiểu tính bằng milliseconds. Lệnh có thể trả scan cursor; cần tiếp tục từ cursor trả về nếu phạm vi chưa duyệt hết. Sau khi claim, worker B xử lý và chỉ ACK khi side effect thực sự hoàn thành.

**Không claim quá sớm** một message mà worker A vẫn đang xử lý: hai worker có thể cùng thực hiện tác dụng phụ. Chọn min idle theo thời gian xử lý/lease của workflow, theo dõi worker và triển khai idempotency.

### 11.3. PEL không giữ bản sao payload độc lập

PEL theo dõi trạng thái phân phối và ACK; nó không phải kho nội dung bền thứ hai. Nếu stream entry đã bị `XDEL` hoặc trim, payload có thể không còn để replay dù còn thông tin pending. Vì vậy, retention là điều kiện thiết yếu của phục hồi.

## 12. Tại sao pause lâu có thể gây mất dữ liệu?

Giả sử:

```text
Producer: 5.000 entries/s
Stream giữ khoảng 100.000 entries
Consumer pause trong 60 giây
```

Trong 60 giây, producer tạo khoảng 300.000 entry. Với chính sách trim theo số lượng, những entry cũ có thể bị loại bỏ trước khi consumer đọc. Khi resume, group không thể khôi phục payload đã bị xóa.

Ví dụ producer có giới hạn stream:

```redis
XADD stream:orders:v1 MAXLEN ~ 100000 '*' eventId evt-300 type PAID
```

Dấu `~` nghĩa là trim xấp xỉ để giảm chi phí, không phải cam kết giữ chính xác 100.000 entry trong mọi thời điểm.

### Thiết kế retention theo thời gian cần phục hồi

- Ước lượng khoảng offline/pause tối đa.
- Tính cả thời gian retry, recovery và thời gian xử lý pending.
- Dùng tốc độ ghi lúc cao điểm, không chỉ trung bình.
- Theo dõi ID đầu tiên còn trong stream, không chỉ tổng số entry.
- Với nhiều group, tính tới group chậm nhất còn cần event.
- Nếu chính sách giữ stream không đáp ứng thời gian outage dự kiến, cần thay retention, quản lý tốc độ producer hoặc chuyển sang nền tảng log/broker phù hợp.

**Backpressure giữ cho consumer không quá tải, nhưng backlog vẫn tiêu thụ dung lượng Redis.** Tạm dừng không thể an toàn vô thời hạn trên một stream có retention hữu hạn.

## 13. Quan sát offset: group lag không phải số event chưa xử lý

Các ID Redis Stream có phần millisecond và sequence, ví dụ `1780000000000-0`. Không thể lấy chênh lệch hai timestamp ID rồi kết luận chính xác số message:

```text
last stream ID   = 1780000000500-0
group delivered  = 1780000000400-0

Chênh 100 ms KHÔNG có nghĩa lag 100 messages.
```

Dùng Redis để quan sát:

```bash
redis-cli XINFO STREAM stream:orders:v1
redis-cli XINFO GROUPS stream:orders:v1
redis-cli XINFO CONSUMERS stream:orders:v1 order-workers
redis-cli XPENDING stream:orders:v1 order-workers
redis-cli XLEN stream:orders:v1
```

`XINFO GROUPS` có thể cho biết `last-delivered-id`, số pending, và trên phiên bản Redis phù hợp, số `lag`. Cần hiểu:

- Lag theo group chủ yếu mô tả tiến độ **phân phối**, không phải tất cả side effect đã hoàn tất.
- Group có lag bằng 0 vẫn có thể có nhiều pending chưa ACK.
- Một số tình huống xóa/trim, ID không liên tục hoặc chỉnh group có thể khiến lag không tính được hoặc không phản ánh đầy đủ thực trạng.
- `XPENDING` cho biết việc đã giao nhưng chưa hoàn tất; phải theo dõi tuổi pending, không chỉ số lượng.
- Không tính chính xác backlog chỉ bằng cách trừ hai stream IDs.

Các metric ứng dụng cần bổ sung:

| Metric | Câu hỏi |
|---|---|
| Producer append rate | Bao nhiêu event mới mỗi giây? |
| Delivery rate | Group đang nhận được bao nhiêu event? |
| Business success rate | Bao nhiêu event được xử lý thành công? |
| ACK rate | Có bao nhiêu event được xác nhận? |
| In-flight count | Bao nhiêu tác vụ đang thực thi? |
| Executor queue depth | Có tồn đọng trong JVM không? |
| Pending count/oldest age | Event đã giao đang bị kẹt bao lâu? |
| Pause duration | Consumer đã dừng poll bao lâu? |
| Recovery throughput | Đang giải quyết pending nhanh tới đâu? |
| Retention head ID | Event chưa xử lý có nguy cơ bị trim không? |
| Handler p50/p95/p99 | Có đủ năng lực để theo kịp producer không? |
| Retry/duplicate rate | Replay có gây side effect lặp không? |

Một health check chỉ xác nhận Redis TCP connection còn hoạt động **không đủ** để chứng minh consumer xử lý hết backlog.

## 14. Xử lý pending và message mới cùng lúc

Một hệ thống production thường cần hai trách nhiệm:

```text
Redis Stream
      |
      +--> New-message lane: XREADGROUP ... >
      |
      +--> Recovery lane: XPENDING / XAUTOCLAIM
                                |
                                v
                         Shared capacity limit
                                |
                                v
                       Idempotent handler
                                |
                                v
                              XACK
```

Nếu recovery và new-message lane mỗi bên đều mở concurrency không giới hạn, tổng tải database vẫn vượt mức. Dùng một budget xử lý chung hoặc quota phân chia hợp lý.

Đối với sự kiện thay đổi trạng thái cùng một entity, thứ tự giữa hai lane cũng quan trọng. Ví dụ recovery event `ORDER_CREATED` sau khi new-message lane đã xử lý `ORDER_PAID`: nếu handler ghi đè trạng thái một cách mù quáng, trạng thái cuối có thể bị lùi. Có thể dùng version kiểm soát cập nhật, serialize theo aggregate hoặc xử lý recovery trước message mới theo quy tắc nghiệp vụ.

Không có một chính sách ordering chung đúng cho mọi luồng: một hệ thống cập nhật snapshot có version và một hệ thống cộng dồn số tiền có yêu cầu hoàn toàn khác nhau.

## 15. Idempotency: xử lý lại là tình huống bình thường

Consumer group và PEL giúp khôi phục, nhưng không đảm bảo side effect chỉ xảy ra một lần.

```text
1. Worker A nhận event e-101.
2. A cập nhật database thành công.
3. A crash trước khi XACK.
4. Worker B reclaim e-101.
5. B nhận cùng event e-101 lần nữa.
```

Nếu handler chỉ gọi `UPDATE total = total + amount`, side effect có thể bị áp dụng hai lần. Cần business event ID và quy tắc idempotency.

Ví dụ payload:

```json
{
  "eventId": "evt-101",
  "orderId": "order-9",
  "version": 42,
  "type": "ORDER_PAID",
  "totalInCents": 350000
}
```

Một handler có thể trong cùng transaction database:

1. Kiểm tra event ID hoặc version đã xử lý.
2. Nếu chưa, cập nhật projection.
3. Ghi dấu event ID đã xử lý hoặc version mới.
4. Commit transaction.
5. Sau commit, gọi `XACK`.

Nếu crash giữa bước 4 và 5, replay thấy event đã xử lý và ACK mà không tạo side effect mới.

**Đừng ACK trước commit** chỉ để PEL nhỏ. Và cũng đừng kỳ vọng transaction database tự bao gồm Redis `XACK`; chúng là các tài nguyên khác nhau, trừ khi hệ thống có giao thức phối hợp cụ thể.

## 16. Poison message và dead-letter flow

Một message luôn lỗi do payload sai hoặc dữ liệu nguồn không hợp lệ có thể bị retry vô hạn:

```text
Message 101
  -> handler lỗi
  -> claim lại
  -> handler lỗi
  -> claim lại
  -> ...
```

Để tránh kẹt:

- Phân biệt lỗi tạm thời với payload không thể xử lý.
- Giới hạn số lần retry và dùng backoff có jitter.
- Theo dõi delivery count và thời gian pending.
- Chuyển bản ghi lỗi sang một dead-letter stream hoặc kho lưu bền với đủ metadata để điều tra.
- Chỉ ACK ở nguồn sau khi chính sách xử lý lỗi đã hoàn tất, chẳng hạn lưu DLQ thành công.
- Có công cụ sửa dữ liệu và redrive có kiểm soát.
- Áp dụng idempotency vì ghi DLQ rồi ACK source là hai thao tác có thể gặp lỗi ở giữa.

Không “sửa” poison message bằng cách chuyển offset của cả group tới cuối stream; thao tác đó có thể bỏ luôn nhiều event hợp lệ khác.

## 17. Tạm dừng theo kế hoạch khi deploy

Một quy trình shutdown thực dụng:

```text
Bắt đầu deploy
     |
     v
Đánh dấu instance draining
     |
     v
Ngừng polling batch mới
     |
     v
Đợi in-flight hoàn thành tới deadline
     |
     +-- Thành công: ACK đúng entry
     |
     +-- Chưa hoàn thành: giữ pending
     |
     v
Đóng kết nối và dừng instance
     |
     v
Instance mới khởi động
     |
     v
Recover pending cũ khi đủ điều kiện
     |
     v
Tiếp tục đọc new messages
```

Không giả định gọi `container.stop()` hoặc cancel reactive subscription sẽ tự đợi mọi callback, drain thread pool, ACK chính xác và khôi phục tất cả pending. Phạm vi của các API lifecycle tùy phiên bản và cấu hình; ứng dụng phải tự định nghĩa trách nhiệm in-flight.

Nếu stop container có nhiều subscription cùng dùng một container, việc dừng container có thể tác động nhiều stream hơn một nguồn đang muốn pause. Do đó, tách cấu hình container hoặc điều khiển poller theo workload khi cần pause độc lập.

Trong deploy nhiều replica, cần tránh tình huống replica mới lập tức claim những pending mà replica cũ **đang draining hợp lệ**. Idle threshold nên tương thích thời gian xử lý tối đa và chính sách shutdown.

## 18. Kịch bản sự cố: backlog lớn, lag nhỏ nhưng pending kẹt

Giả sử một group xử lý đơn hàng:

```text
Stream đã ghi 50.000 entry.
Group đã phân phối gần hết 50.000 entry.
Có 8.000 entry pending chưa ACK.
Consumer vẫn đọc và xử lý event mới.
```

Nếu chỉ nhìn last-delivered ID sát cuối stream hoặc lag thấp, người vận hành có thể nghĩ hệ thống “đã bắt kịp”. Thực tế 8.000 event đã giao vẫn chưa hoàn tất, có thể là do worker crash, ACK lỗi hoặc handler bị kẹt.

Giải pháp điều tra:

1. Chạy `XINFO GROUPS` và `XPENDING` để xem số pending.
2. Xem consumer nào giữ pending và tuổi entry.
3. Kiểm tra log lỗi handler, ACK failures, thời gian xử lý và trạng thái process.
4. Không chỉnh group offset để che số pending.
5. Nếu worker cũ đã chết, reclaim entry idle qua `XAUTOCLAIM`.
6. Xử lý lại với idempotency; ACK sau thành công.
7. Đối chiếu với retention head để xác định payload còn đọc được hay đã bị trim.
8. Điều chỉnh `COUNT`, concurrency, queue và timeout theo tải nguồn.

Đây là ví dụ **lệch tiến độ phân phối so với tiến độ nghiệp vụ**, không thể phát hiện đầy đủ chỉ từ một biểu đồ “stream lag”.

## 19. Đánh giá bằng thử nghiệm trước khi triển khai production

Một bộ thử nghiệm có kiểm soát nên mô phỏng cả throughput và lỗi:

| Tình huống | Điều cần xác nhận |
|---|---|
| Producer ghi nhanh hơn consumer | In-flight bị giới hạn, không tạo queue vô hạn |
| Pause 30 giây rồi resume | Message mới trong thời gian pause vẫn được đọc nếu còn trong retention |
| Crash sau XREADGROUP trước handler | Entry nằm trong PEL và có thể recovery |
| Crash sau DB commit trước XACK | Handler idempotent ngăn side effect trùng |
| Hủy reactive subscription khi demand=0 | Offset không nhảy đến latest làm bỏ qua entry cần xử lý |
| Consumer A chết, B còn chạy | B có thể claim pending A sau idle threshold phù hợp |
| Handler luôn lỗi | Retry không vô hạn, có DLQ và quan sát |
| Stream bị trim khi offline lâu | Có cảnh báo và quy trình phát hiện payload đã mất |
| Group được tạo với `$` | Hệ thống không vô tình bỏ qua lịch sử cần xử lý |
| Group lag giảm nhưng pending tăng | Monitoring vẫn báo backlog nghiệp vụ |
| Xử lý song song event cùng order | Version/order logic tránh ghi đè sai trạng thái |
| Redis restart/failover | Consumer phục hồi group, pending và kết nối theo yêu cầu độ bền |

Trong thử nghiệm, đo **số event đã xử lý nghiệp vụ**, không chỉ số event được nhận từ Redis. Một hệ thống có ACK rate cao nhưng handler không commit đúng không đạt yêu cầu tin cậy.

## 20. Lựa chọn cơ chế theo mục tiêu

| Mục tiêu | Cơ chế khuyến nghị |
|---|---|
| Giảm số entry nhận khi downstream chậm | `COUNT` nhỏ, bounded executor, giới hạn in-flight |
| Tạm dừng nhận lô mới | Pause poll hoặc điều khiển demand/lifecycle có kiểm soát |
| Đọc tiếp từ vị trí cuối với XREAD | Checkpoint dựa trên tiến độ xử lý hoàn tất |
| Xử lý không mất event với consumer group | `ReadOffset.lastConsumed()` cho message mới + recovery PEL |
| Tránh skip entry giữa các poll | Không chọn `ReadOffset.latest()` khi cần coverage đầy đủ |
| Phục hồi pending thuộc consumer hiện tại | `XREADGROUP` với ID cụ thể theo cơ chế pending |
| Phục hồi pending của worker chết | `XAUTOCLAIM` với min idle và cursor |
| Tránh mất event sau crash | ACK sau commit và retention đủ dài |
| Chịu được phát lại sau crash | Idempotent handler theo event ID/version |
| Tránh pending độc hại | Retry policy, backoff, DLQ bền |
| Tăng throughput mà không quá tải | Scale worker có giới hạn, quan sát database và ordering |

## 21. Quy trình ra quyết định

```text
Consumer Redis Streams cần xử lý bao nhiêu sự kiện?
                        |
                        v
          Event có được phép bị bỏ lỡ không?
                  +-----+-----+
                  |           |
                 Có          Không
                  |           |
                  v           v
           Notification     Consumer group,
           nhẹ có thể       ACK, PEL recovery
           chọn latest            |
                  |               v
                  |         Giới hạn in-flight
                  |               |
                  +-------+-------+
                          |
                          v
                   Downstream quá tải?
                          |
                    +-----+-----+
                    |           |
                   Không        Có
                    |           |
                    v           v
              Poll tiếp      Pause nhận mới,
              có giới hạn    drain in-flight
                    |           |
                    +-----+-----+
                          |
                          v
                  Resume đúng offset
                          |
                          v
                Xử lý pending và mới
                          |
                          v
              Check retention, ACK,
              idempotency và metrics
```

## 22. Kết luận

**Điều tiết nhu cầu** trong Spring Data Redis Streams không chỉ là giảm tốc độ gọi `XREAD`/`XREADGROUP`. Một thiết kế đúng phải kiểm soát số entry đã giao nhưng chưa xử lý, dừng nhận thêm khi đã đầy, và tiếp tục đúng vị trí sau pause hoặc restart.

**Lệch offset** có thể xảy ra khi dùng `ReadOffset.latest()` sau khoảng ngừng polling, khi lưu checkpoint bằng ID mới nhận thay vì đã xử lý, khi group được tạo hoặc chỉnh mốc sai, hoặc khi chỉ đọc `>` mà bỏ quên PEL cũ. Redis Streams cung cấp group, `XACK` và `XAUTOCLAIM` để quản lý tiến độ, nhưng không tự bảo vệ những entry đã bị trim và không đảm bảo exactly-once side effect.

Một hệ thống có thể tin cậy khi cùng thỏa bốn điều kiện: **không fetch quá năng lực, không ACK sớm, không bỏ quên pending và không trim dữ liệu trước khi có thể khôi phục**. Khi producer luôn nhanh hơn consumer, cần tăng năng lực xử lý, giảm lượng sự kiện sinh ra hoặc chọn nền tảng lưu backlog phù hợp — chỉ pause và resume không giải quyết được chênh lệch throughput lâu dài.

