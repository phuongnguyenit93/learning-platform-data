# Xuất số đo qua bộ đếm, hàng đợi sự kiện hoặc JFR Event tùy mục tiêu

> **Mục tiêu:** Thiết kế đường đi của dữ liệu quan sát sau khi Java instrumentation đã đo được một sự kiện. Biết chọn **counter** khi cần số liệu tổng hợp, **hàng đợi sự kiện có giới hạn** khi cần xử lý bản ghi chi tiết bất đồng bộ, hoặc **Java Flight Recorder (JFR) Event** khi cần dữ liệu chẩn đoán/timeline gắn với JVM. Hiểu chi phí trên hot path, mất sự kiện, backpressure, cardinality, quyền riêng tư, điều kiện thu thập, và cách kiểm chứng từng lựa chọn bằng Java 17+.

Bài này thuộc nhóm **Thiết kế điểm đo**. “Điểm đo” (*probe*) là nơi trong chương trình ta ghi nhận một hiện tượng, chẳng hạn một method hoàn tất, một lời gọi RPC thất bại hoặc một thao tác chạy quá chậm. **Xuất số đo** là quyết định khác: đưa thông tin từ điểm đo sang cơ chế lưu/tiêu thụ phù hợp. Một điểm đo có thể tạo counter, một sự kiện queue hoặc một JFR Event, nhưng không nên nhân ba tín hiệu một cách tùy tiện rồi đếm chúng như ba sự kiện nghiệp vụ.

## 1. Bắt đầu từ câu hỏi cần trả lời, không bắt đầu từ API

Giả sử một agent chèn điểm quan sát quanh `OrderService.checkout()`. Ở cuối method, agent biết:

```text
operation = checkout
status    = success hoặc failure
duration  = thời gian đã trôi qua
thread    = luồng hiện tại
```

Người vận hành có thể muốn những đầu ra rất khác nhau:

1. **“Trong phút qua có bao nhiêu giao dịch checkout lỗi?”** → Cần **counter** và phép tính tốc độ trên một cửa sổ thời gian.
2. **“Giao dịch nào lỗi, được xử lý bằng consumer nào, gửi tới đâu?”** → Cần **bản ghi sự kiện chi tiết** và một sink có khả năng tiếp nhận chúng.
3. **“Thao tác chậm xảy ra trên thread nào, gần thời điểm GC/lock/I/O nào?”** → Cần **timeline chẩn đoán**, nơi JFR có lợi thế vì cùng hệ dữ liệu JVM.

Nếu biến mọi lần gọi method thành một dòng log hoặc một bản ghi remote được gửi đồng bộ, instrumentation có thể làm chậm chính ứng dụng đang quan sát. Nếu chỉ giữ một bộ đếm, ta có thể đánh mất ngữ cảnh cần điều tra một lần thất bại cụ thể. Do đó trước khi chọn API hãy viết rõ: **mục tiêu, độ phân giải cần giữ, lượng dữ liệu, ngân sách overhead, mức mất dữ liệu chấp nhận được và người tiêu thụ dữ liệu**.

```text
Method execution
      |
      v
  Điểm đo cực ngắn
      |
      +--> LongAdder/AtomicLong --> snapshot/exporter --> metrics backend
      |
      +--> bounded queue --> consumer/batch/exporter --> event backend
      |
      +--> jdk.jfr.Event.commit() --> JFR recording/stream --> JMC/.jfr
```

Mũi tên đầu **không có nghĩa counter tự phát HTTP metrics**. Mũi tên thứ hai **không có nghĩa đưa vào queue đã giao hàng thành công**. Mũi tên thứ ba **không có nghĩa JFR tự gửi dữ liệu lên dịch vụ bên ngoài**. Cần phân biệt **ghi nhận nội bộ**, **xuất khỏi JVM** và **đến nơi nhận cuối cùng**.

## 2. Bảng quyết định nhanh

| Tiêu chí | Bộ đếm (`LongAdder`, `AtomicLong`) | Queue sự kiện (`BlockingQueue`/ring buffer) | JFR Event (`jdk.jfr.Event`) |
| --- | --- | --- | --- |
| Đơn vị dữ liệu | Số đếm/tổng/giá trị tổng hợp | Bản ghi của từng lần quan sát | Sự kiện có thời điểm, duration, field, thread metadata |
| Phù hợp nhất | Throughput, lỗi, số lần retry, tổng thời gian | Gửi bản ghi chi tiết, batch, tích hợp consumer | Profiling, latency, liên hệ với GC/lock/thread/JVM |
| Chi phí trên điểm đo | Thường thấp; tăng khi nhiều nhãn/bộ đếm | Tạo object và enqueue; có thể tốn bộ nhớ và mất sự kiện | Phụ thuộc enabled/threshold/stack trace/payload |
| Giới hạn bộ nhớ | Số lượng counter và cardinality của dimensions | Phải **bounded**; capacity định trước | Buffer/recording size/age phụ thuộc cấu hình |
| Khi consumer chậm | Scrape/chụp giá trị cũ; update counter vẫn chạy | Queue đầy → drop, chặn producer hoặc chính sách khác | Recording/stream/buffer chịu áp lực; phải cấu hình giới hạn |
| Có giữ từng sự kiện? | **Không** | Có nếu enqueue/consume thành công; không mặc nhiên bền vững | Có khi event được ghi nhận và dữ liệu còn lưu |
| Truy vấn theo thời gian | Dựa vào snapshot định kỳ và delta | Dựa vào timestamp + backend | Timeline native JFR và công cụ phân tích |
| Đảm bảo delivery | Không phải cơ chế message delivery | Tùy consumer/sink; queue trong RAM không phải audit log | Không phải message queue/durable audit |
| Điểm cần cảnh giác | Counter cardinality, snapshot không nguyên tử | Backpressure, quá tải, shutdown, trùng/mất | Recording config, threshold, dữ liệu nhạy cảm, version |
| Khi tắt đo | Có thể không tăng counters chọn lọc | Không enqueue | JFR Event có `isEnabled()`/`shouldCommit()` |

**Nguyên tắc thực tế:** Chọn phương án rẻ nhất vẫn trả lời được câu hỏi. Nếu chỉ muốn đếm tần suất, đừng giữ toàn bộ request object; nếu cần chẩn đoán phương thức chậm trong JVM, đừng tự tạo hệ thống queue phức tạp khi một JFR Event được bật có điều kiện là đủ.

## 3. Thiết kế dữ liệu chung trước khi chọn sink

Dữ liệu ở điểm đo thường nên có một **schema logic tối thiểu**:

| Trường | Ý nghĩa | Có nên giữ mọi lần không? |
| --- | --- | --- |
| `name` | Tên phép đo, ví dụ `checkout.completed` | Có, nhưng dùng danh sách tên ổn định |
| `outcome` | Thành công, thất bại, timeout | Có nếu cần phân tích |
| `elapsedNanos` | Duration đo bằng `System.nanoTime()` | Có thể tổng hợp, dùng histogram hoặc event |
| `timestamp` | Thời điểm sự kiện xảy ra | Cần với queue/event; counter thường lấy theo thời điểm scrape |
| `component` | Tên thành phần, endpoint mẫu hoặc operation | Có giới hạn cardinality |
| `traceId`/`spanId` | Liên hệ với trace khi thực sự cần | Không đưa vào nhãn counter; có thể nhạy cảm |
| `thread` | Ngữ cảnh luồng | Có ích trong JFR/chẩn đoán, ít dùng cho counter |
| `errorKind` | Nhóm lỗi được phân loại | Ưu tiên loại ổn định hơn message thô |

Từng sink có cách biểu diễn khác nhau. Counter cho `checkout.completed` có thể có hai `LongAdder`: success và error. Queue có thể chứa record `Observation(operation, outcome, elapsedNanos, timestamp)`. JFR Event có thể lưu `operation`, `outcome` và dùng duration của `Event.begin()`/`end()` thay vì tự tạo field không cần thiết.

**Không đưa thông tin người dùng, URL có định danh riêng, SQL đầy đủ, exception message chứa dữ liệu nội bộ hoặc request body vào tất cả các kênh theo mặc định.** Việc một trường có thể ghi được về mặt kỹ thuật không có nghĩa nên ghi. Hãy phân loại PII/secrets, giới hạn nhãn và xác định chính sách lưu giữ/xóa.

### Một lỗi ngữ nghĩa thường gặp: đếm ở cả enter và exit

Nếu điểm đo tăng counter khi vào method và tăng tiếp khi rời method nhưng cả hai đều đặt tên `requests_total`, dashboard có thể đếm **hai** cho một request. Xác định rõ đơn vị:

- `requests_started_total`: tăng khi bắt đầu.
- `requests_completed_total`: tăng khi hoàn tất, kể cả error nếu định nghĩa như vậy.
- `requests_failed_total`: tăng đúng một lần cho thất bại thực sự.

Cũng phải xác định lời gọi bị retry có tính là một lần **attempt** hay một lần **business transaction**. Sink không thể tự sửa định nghĩa phép đo sai.

## 4. Lựa chọn A — bộ đếm cho số liệu tổng hợp

### 4.1. `LongAdder` và `AtomicLong`

Trong Java 17+, hai lớp thường dùng:

```java
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

LongAdder completed = new LongAdder();
LongAdder failed = new LongAdder();
AtomicLong active = new AtomicLong();

completed.increment();
failed.increment();
active.incrementAndGet(); // Khi bắt đầu.
active.decrementAndGet(); // Khi kết thúc, kể cả khi ném exception.
```

Đây là **minh họa các API**, không phải chương trình độc lập. `AtomicLong` cung cấp phép cập nhật/đọc biến đơn với semantics nguyên tử; nó hữu ích cho gauge như số request đang chạy hoặc các trường hợp cần giá trị cập nhật có trật tự tuyến tính rõ. `LongAdder` phân tán cạnh tranh ghi để tăng thông lượng khi nhiều thread đồng thời increment, thích hợp cho **counter tần suất cao**.

`LongAdder.sum()` **không phải atomic snapshot** khi các thread còn cập nhật. Trong lúc đọc, một vài lần increment đang diễn ra có thể chưa được cộng vào giá trị trả về. Điều này thường chấp nhận được với telemetry tổng hợp; **không phù hợp làm sổ cái giao dịch chính xác tại từng thời điểm**.

Tương tự, `LongAdder.sumThenReset()` **không an toàn như phép chốt cửa sổ nguyên tử** khi nhiều producer vẫn ghi. Việc reset trong lúc có update có thể làm kết quả khó diễn giải. Với metrics, nhiều hệ thống giữ counter **tăng dần** rồi tính chênh lệch giữa hai lần scrape, đồng thời xử lý trường hợp process restart/reset.

### 4.2. Từ tổng đếm sang rate

Counter `orders_completed_total` sau 30 giây là 12.000, sau 60 giây là 15.000. Nếu không reset giữa hai mốc:

```text
delta count = 15.000 - 12.000 = 3.000
elapsed     = 60 - 30 = 30 giây
rate        = 3.000 / 30 = 100 lần/giây
```

Trong thực tế dùng thời điểm đo (không giả định scrape luôn chính xác từng giây), xử lý restart và phân biệt đơn vị. **Counter đơn lẻ không trả lời latency phân vị p95/p99**. Muốn phân bố độ trễ cần histogram/buckets hoặc dạng dữ liệu khác; chỉ cộng tổng duration rồi chia số lần là **mean**, không phải p99.

### 4.3. Nhãn và cardinality

Counter có thể được tách theo các chiều ổn định:

```text
method_calls_total{operation="checkout", outcome="success"}
method_calls_total{operation="checkout", outcome="error"}
method_calls_total{operation="refund", outcome="success"}
```

Đây là **ví dụ định dạng metrics**, không phải cú pháp Java. Đừng dùng `requestId`, raw URL, user ID hoặc exception message làm label. Một triệu requestId có thể tạo một triệu time series, tiêu tốn bộ nhớ và làm hỏng hệ thống thu thập. Với agent, thiết kế bảng ánh xạ class/method sang operation name **có giới hạn**, thay vì tạo counter mới cho mọi tổ hợp động.

### 4.4. Counter không có exporter “miễn phí”

`LongAdder` chỉ lưu số trong tiến trình. Muốn có dashboard, cần collector/scraper/exporter. Nếu chọn HTTP endpoint, OpenTelemetry SDK hoặc metrics backend thì đó là **phần triển khai bổ sung**. Không nên viết:

```text
completed.increment()  → dữ liệu đã có trong Prometheus
```

trừ khi đã thật sự kết nối exporter và xác nhận backend thu được số liệu.

## 5. Lựa chọn B — hàng đợi sự kiện khi cần từng bản ghi

### 5.1. Vì sao queue xuất hiện trong instrumentation?

Một sự kiện chi tiết có thể cần serialize JSON, batch, nén, ghi file hoặc gửi mạng. Nếu agent làm tất cả ngay trong method đang phục vụ request, latency thực tế sẽ tăng và exporter lỗi có thể lây sang nghiệp vụ.

Tách producer/consumer:

```text
Thread xử lý nghiệp vụ
    │
    ├─ tạo event nhỏ, không chứa object đồ sộ
    ├─ queue.offer(event) (không chặn)
    └─ trả quyền điều khiển về ứng dụng
                  |
                  ▼
           Bounded queue
                  |
                  ▼
      Worker chuyên dụng / batch
                  |
                  ▼
      file / gateway / telemetry backend
```

**Queue nhận sự kiện** không đồng nghĩa **sink đã nhận**. Cần theo dõi ít nhất `accepted`, `dropped`, `exported` và `exportFailed` (với định nghĩa rõ ràng), tránh chỉ đếm `offer` thành công rồi tự tuyên bố delivery 100%.

### 5.2. Hàng đợi phải có giới hạn

`ArrayBlockingQueue<T>(capacity)` là hàng đợi dạng mảng cố định. Với `offer(e)`:

- Trả `true` nếu đưa vào được ngay.
- Trả `false` nếu đầy, **không chờ** để có chỗ.

Với `put(e)`, producer sẽ **chặn** khi hàng đợi đầy. Điều này đôi khi đúng với pipeline dữ liệu mà backpressure được phép làm chậm upstream, nhưng trong hot path của JVM instrumentation thường rất nguy hiểm: một exporter chậm có thể làm cả request thread đứng lại.

```java
// Mã minh họa bên trong lớp quản lý queue:
if (!queue.offer(observation)) {
    droppedCounter.increment();
}
```

Ở đây `queue`, `observation`, `droppedCounter` phải được khai báo và quản lý ở lớp sở hữu sink. Cũng có thể dùng `offer(e, timeout, unit)` khi có **ngân sách chờ cụ thể**, nhưng phải hiểu rằng producer có thể block tới thời hạn đó. `LinkedBlockingQueue` nếu tạo không truyền capacity có giới hạn mặc định rất lớn (`Integer.MAX_VALUE`), dễ trở thành queue gần như **không giới hạn thực tế** khi consumer ngừng hoạt động.

### 5.3. Chọn chính sách khi đầy

| Chính sách | Tình huống phù hợp | Rủi ro |
| --- | --- | --- |
| **Drop newest** (`offer` false) | Telemetry thường, ưu tiên bảo vệ nghiệp vụ | Mất các event mới; phải tăng drop metric |
| **Drop oldest** | Muốn giữ trạng thái mới nhất | Mất lịch sử trước đó; cần cấu trúc/đồng bộ phù hợp |
| **Block** (`put`) | Producer vốn chịu backpressure, không phải hot path | Tăng latency, có thể deadlock hay làm nghẽn ứng dụng |
| **Sample** | Sự kiện rất nhiều nhưng chọn mẫu đủ thống kê | Không còn đầy đủ từng request; cần báo tỷ lệ sampling |
| **Batch hoặc coalesce** | Nhiều sự kiện cùng loại, có thể gộp | Mất chi tiết/timing và thứ tự từng event |
| **Spill to disk** | Cần hạn chế mất khi spike | Phức tạp I/O, recovery, quota và latency |

Không có một chính sách đúng cho mọi loại dữ liệu. **Telemetry phục vụ quan sát không phải audit/payment ledger.** Nếu cần bảo đảm không mất và có thể đối soát từng giao dịch, phải thiết kế transaction log/durable messaging/ack/replay phù hợp; một `BlockingQueue` trong heap không đủ.

### 5.4. Consumer và vòng đời

Consumer thường chạy trên một worker thread, drain batch, retry khi exporter lỗi và dừng có kiểm soát. Cần kiểm tra:

- `close()` có ngừng nhận sự kiện mới trước khi drain không?
- Khi JVM dừng đột ngột, những event trong queue **không được đảm bảo** đã ghi ra đĩa.
- Retry có thể tạo **duplicate** nếu sink nhận thành công nhưng acknowledgment tới muộn.
- Queue nội bộ giữ thứ tự các phần tử đã enqueue, nhưng **thứ tự giữa các producer concurrent** phụ thuộc interleaving; không dùng nó như thứ tự sự kiện nghiệp vụ tuyệt đối.
- Nếu consumer throw exception rồi chết, queue có thể đầy dần; cần health signal và lifecycle supervision.
- Đếm `queue.size()` giúp quan sát áp lực tương đối, không phải một snapshot giao dịch nguyên tử khi queue đang đổi liên tục.

Trong sản phẩm thật, hãy quyết định consumer thread có daemon hay không, thời hạn flush lúc shutdown, thời hạn retry, chính sách quarantine và tốc độ gửi tối đa; đừng để shutdown treo mãi vì chờ exporter mất kết nối.

## 6. Lựa chọn C — JFR Event cho chẩn đoán gắn với JVM

**Java Flight Recorder** (`jdk.jfr`) thu thập sự kiện bên trong JVM, có thể liên hệ với hoạt động thread, allocation, GC, synchronization, I/O và các sự kiện JVM khác trong cùng mốc thời gian. Java 17+ có API định nghĩa sự kiện tùy biến:

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.CheckoutFinished")
@Label("Checkout Finished")
@Category({"Application", "Checkout"})
public final class CheckoutFinishedEvent extends Event {
    @Label("Operation")
    public String operation;

    @Label("Success")
    public boolean success;
}
```

Đoạn trên là class Java độc lập cần lưu trong file tên `CheckoutFinishedEvent.java` nếu sử dụng riêng. Trong phần thực hành có event class lồng để chỉ cần một file.

### 6.1. Bật recording mới có dữ liệu JFR được tiêu thụ

`Event.commit()` ghi event vào hệ thống Flight Recorder **khi event đang được bật và thỏa cấu hình**; nó không phải lời gọi POST/HTTP. Bạn cần recording/stream để lấy dữ liệu: dùng `Recording`, `RecordingStream`, `jcmd JFR.start/JFR.dump` hoặc công cụ JDK Mission Control (JMC) tùy nhu cầu và môi trường.

Một event class được định nghĩa **không đồng nghĩa luôn có `.jfr` file**. Phải có một recording đang chạy và sự kiện enabled. `Event.isEnabled()` cho biết có recording đang chạy đang bật loại event đó; `Event.shouldCommit()` còn xét **threshold duration** để tránh thu payload đắt tiền cho event sẽ bị loại.

### 6.2. `isEnabled()`, `begin()`, `end()`, `shouldCommit()`, `commit()`

Chu trình điển hình:

```java
// Mã minh họa cho một biến WorkEvent event và logic nghiệp vụ ở nơi khác:
if (event.isEnabled()) {
    event.begin();
    // Thực hiện đoạn xử lý cần đo, đảm bảo end() ở finally khi cần.
    event.end();
    if (event.shouldCommit()) {
        event.operation = "checkout";
        event.success = true;
        event.commit();
    }
}
```

Đoạn minh họa **không phải** wrapper đầy đủ cho nghiệp vụ có exception. Với wrapper thực, **không được bỏ qua logic nghiệp vụ khi JFR tắt**: tác vụ luôn phải được thực thi, chỉ có nhánh quan sát được bật/tắt. `end()` nên chạy trong `finally` để kể cả khi code ứng dụng throw, duration được kết thúc và outcome được ghi theo chính sách.

Lưu ý: JFR `Event` có trường **duration nội tại** khi dùng `begin()`/`end()`; không cần tự tạo field duration thứ hai trừ khi muốn đo một khoảng khác. Field của custom event nên là primitive, `String`, `Class` hoặc `Thread` theo API JFR; các kiểu phức tạp như object tùy ý, array, enum không tự động trở thành payload sự kiện.

### 6.3. Threshold và stack trace

Ví dụ recording chỉ giữ sự kiện chậm hơn 20 ms:

```java
// Trong nơi cấu hình Recording recording:
recording.enable(CheckoutFinishedEvent.class)
        .withThreshold(java.time.Duration.ofMillis(20))
        .withoutStackTrace();
```

Đoạn code là cấu hình trong một chương trình có sẵn `Recording` và class event. **Threshold không làm thay đổi runtime của method nghiệp vụ**, nó lọc việc lưu event. Trong instrumentation đo nhiều method cực nhanh, nên xét threshold/sampling để không tạo quá nhiều event. Stack trace giúp điều tra nhưng có chi phí; nếu không cần call stack, tắt stack trace cho event đang phát tần suất cao.

### 6.4. `RecordingFile` và `RecordingStream`

- `jdk.jfr.Recording`: quản lý recording trong JVM, cho phép cấu hình, start, stop, dump ra file.
- `jdk.jfr.consumer.RecordingFile`: đọc file `.jfr`; `readAllEvents(Path)` phù hợp **file nhỏ**, không nên dùng để load toàn bộ recording production rất lớn.
- `jdk.jfr.consumer.RecordingStream`: tiêu thụ JFR events của JVM đang chạy qua callbacks; cần quản lý retention/flush/callback lifecycle.
- `jdk.jfr.consumer.EventStream`: API dành cho các nguồn stream theo hình thức tương ứng.

Cả recording và streaming đều cần tính đến tần suất, tuổi dữ liệu, kích thước dữ liệu, khả năng mất sự kiện khi quá tải và quyền truy cập vào recording. JFR phù hợp **diagnostic telemetry**; không tự coi là audit ledger bảo đảm lưu từng sự kiện vô hạn.

## 7. So sánh overhead trên hot path

Điểm instrument thường nằm ngay trong critical path của ứng dụng. Hãy phân biệt các chi phí:

```text
Tổng overhead tại probe
    ≈ đọc clock/context
    + xây payload
    + cập nhật counter / enqueue / ghi JFR event
    + lock/atomic contention
    + allocation/GC do probe
    + (nếu có) đồng bộ I/O hoặc block
```

Đây là mô hình định tính, không phải công thức đo đã được hiệu chuẩn. Một số điểm cần kiểm:

**Counter:** `LongAdder.increment()` tránh lưu từng record, chi phí thường thấp nếu số lượng counters ổn định. Nhưng việc tra key từ một map nhãn động hoặc stringify URL vẫn có thể đắt hơn cả increment.

**Queue:** `offer` không block vì đầy, nhưng vẫn có chi phí tạo record, đồng bộ hàng đợi, cache misses và áp lực GC. Nếu serialize JSON trước khi `offer`, sự kiện bị drop vẫn đã trả giá serialize; nên enqueue một cấu trúc **nhỏ, bất biến**, xử lý nặng trong consumer khi an toàn.

**JFR:** Khi event chưa bật, đường kiểm tra enabled có thể giúp tránh chuẩn bị payload. Khi bật, chi phí liên quan commit, field, stack trace, threshold, buffer và recording. Với event nhiều triệu lần/giây, cần đo thật trên JDK và workload mục tiêu.

### Timing đúng cách

Trong Java, dùng `System.nanoTime()` để đo **khoảng thời gian**:

```java
long started = System.nanoTime();
try {
    return performWork();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordElapsed(elapsedNanos);
}
```

Đây là **đoạn minh họa**, thiếu định nghĩa `performWork()`/`recordElapsed()`. Nó không dùng `System.currentTimeMillis()` để đo duration, vì đồng hồ wall clock có thể thay đổi do đồng bộ thời gian. Với JFR `Event.begin()/end()`, JFR tự lưu duration của event. Khi dùng queue, timestamp để xâu chuỗi sự kiện có thể là `Instant.now()` nhưng cần biết thời điểm **quan sát**, thời điểm **enqueue** và thời điểm **export** không giống nhau.

**Bảo toàn ngoại lệ:** Nếu method ứng dụng ném exception, phép đo trong `finally` không được thay exception nghiệp vụ bằng lỗi exporter. Nếu chính sách cho phép mất telemetry, xử lý lỗi quan sát bên ngoài đường ném lỗi của nghiệp vụ. Nếu metrics là tính năng bắt buộc về pháp lý/giao dịch, thiết kế theo ràng buộc nghiệp vụ riêng, không ẩn lỗi.

## 8. Ví dụ Java 17+ độc lập: ba cách xuất với cùng dữ liệu mẫu

Thí nghiệm sau minh họa **ba sink độc lập**. Nó không chèn bytecode, không có Java agent và không cần thư viện bên ngoài; mục đích là hiểu vòng đời, dung lượng và đầu ra. Phần queue được cố tình **đổ đầy trước khi drain** để kết quả drop là xác định. Trong production, consumer nên chạy bất đồng bộ; vì vậy việc một queue được drain ngay trong chương trình này **không mô phỏng đầy đủ** concurrent production.

### 8.1. Tệp `OutputModesDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.LongAdder;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordingFile;

public final class OutputModesDemo {

    private record Observation(int id, String operation) {
    }

    @Name("demo.MeasurementFinished")
    @Label("Measurement Finished")
    @Category({"Demo", "Instrumentation"})
    @StackTrace(false)
    public static final class MeasurementFinished extends Event {
        @Label("Operation")
        public String operation;

        @Label("Success")
        public boolean success;
    }

    public static void main(String[] args) throws Exception {
        // A. Counter: giữ tổng số, không giữ từng sự kiện.
        LongAdder counter = new LongAdder();
        for (int i = 0; i < 3; i++) {
            counter.increment();
        }
        System.out.println("counter-total=" + counter.sum());

        // B. Queue có giới hạn: tạo tải trước khi consumer xuất hiện.
        ArrayBlockingQueue<Observation> queue =
                new ArrayBlockingQueue<>(2);
        LongAdder dropped = new LongAdder();

        for (int id = 1; id <= 3; id++) {
            Observation observation = new Observation(id, "checkout");
            if (!queue.offer(observation)) {
                dropped.increment();
            }
        }

        int drained = 0;
        while (queue.poll() != null) {
            drained++;
        }
        System.out.println("queue-drained=" + drained);
        System.out.println("queue-dropped=" + dropped.sum());

        // C. JFR: chỉ chạy khi JVM thực sự hỗ trợ Flight Recorder.
        if (!FlightRecorder.isAvailable()) {
            System.out.println("jfr=unavailable");
            return;
        }

        Path recordingFile =
                Files.createTempFile("output-modes-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.enable(MeasurementFinished.class)
                        .withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();

                for (int i = 0; i < 2; i++) {
                    MeasurementFinished event =
                            new MeasurementFinished();
                    if (event.isEnabled()) {
                        event.begin();
                        event.operation = "checkout";
                        event.success = true;
                        event.end();
                        if (event.shouldCommit()) {
                            event.commit();
                        }
                    }
                }

                recording.stop();
                recording.dump(recordingFile);
            }

            long matched = RecordingFile
                    .readAllEvents(recordingFile)
                    .stream()
                    .filter(e -> "demo.MeasurementFinished".equals(
                            e.getEventType().getName()))
                    .count();

            System.out.println("jfr-events=" + matched);
        } finally {
            Files.deleteIfExists(recordingFile);
        }
    }
}
```

**Tập trung vào hành vi đã được cố định:**

- Counter increment **ba lần**, sau đó không còn thread nào cập nhật, nên `sum()` chính xác bằng 3.
- Queue có capacity 2; ba lần `offer` nối tiếp **trước khi drain** làm sự kiện thứ ba bị từ chối. Hai sự kiện đầu được lấy ra bằng `poll()`.
- Khi JFR khả dụng và recording được tạo thành công, custom event type `demo.MeasurementFinished` được bật với threshold 0 và không có stack trace. Chương trình commit hai event, stop/dump recording rồi chỉ đếm custom events đúng tên đó.
- File `.jfr` tạm được xóa trong `finally` để dọn bài lab; muốn tự mở bằng JDK Mission Control, hãy tạm bỏ bước xóa và in đường dẫn file.
- `RecordingFile.readAllEvents(...)` đọc toàn bộ file vào bộ nhớ; chỉ dùng ở đây vì recording rất nhỏ.

### 8.2. Biên dịch và chạy

Yêu cầu **JDK 17 hoặc mới hơn**, có module `jdk.jfr` và quyền ghi vào thư mục tạm.

```bash
javac --add-modules jdk.jfr -encoding UTF-8 OutputModesDemo.java
java --add-modules jdk.jfr OutputModesDemo
```

Lệnh tương tự sử dụng được trong PowerShell. `--add-modules jdk.jfr` làm rõ module được yêu cầu; trên nhiều bản phân phối JDK, module có thể đã được resolve tự động.

**Stdout kỳ vọng khi JFR được hỗ trợ và không có lỗi môi trường:**

```text
counter-total=3
queue-drained=2
queue-dropped=1
jfr-events=2
```

Nếu JFR không khả dụng, ba dòng đầu vẫn như trên và dòng cuối trở thành:

```text
jfr=unavailable
```

Trong môi trường không thể tạo recording hoặc ghi file, các thao tác JFR/I/O có thể ném exception; khi đó **không được** giả vờ output là `jfr-events=2`. Hãy kiểm tra quyền filesystem, repository JFR, `java -version` và việc module `jdk.jfr` có trong runtime image hay không.

### 8.3. Đọc từng phần theo mục tiêu

**Counter:** Chúng ta biết tổng là 3 nhưng **không biết** id nào xuất hiện. Điều đó phù hợp nếu mục tiêu chỉ là số lần hoàn thành.

**Queue:** Chúng ta biết đã drain 2 bản ghi và drop 1. Nếu chỉ đọc `queue-drained=2` mà không có `queue-dropped=1`, có thể nhầm hệ thống chỉ nhận đúng hai sự kiện. Do đó **drop counter là một phần của thiết kế queue**, không phải chỉ số phụ.

**JFR:** Có hai event trong recording nhưng số event này **không được suy ra** bằng counter hay queue. Thí nghiệm chủ động tạo hai JFR event riêng. Nếu thêm `recording.enable(...)` với threshold lớn, số event thu được có thể khác dù code đã tạo event object.

### 8.4. Xem JFR bằng công cụ ngoài chương trình

Để giữ file tạm sau khi chạy, trong mã bài lab có thể tạm thay `Files.deleteIfExists(recordingFile)` bằng việc in ra `recordingFile` và không xóa. Sau đó:

```bash
jfr print --events demo.MeasurementFinished /path/to/recording.jfr
```

Thay `/path/to/recording.jfr` bằng **đường dẫn có thật** vừa in; không phải giá trị cố định. Lệnh `jfr print` xem event và field được lưu. Với môi trường JFR đang chạy khác, có thể dùng `jcmd <pid> JFR.check` hoặc `JFR.dump` nếu đã có quyền vận hành thích hợp. Không tự attach JVM khác hoặc bật recording của ứng dụng production khi chưa được cho phép.

## 9. Từ bài lab tới điểm đo được chèn bằng Java agent

Bài thực hành ở mục 8 gọi API trực tiếp. Khi chuyển sang instrumentation, cần giải quyết thêm:

1. **Chọn lớp và method:** sử dụng class name, class loader và module đúng; tránh instrument helper của chính agent.
2. **Chọn một thời điểm ghi nhận chuẩn:** thường một lần ở exit path và xử lý cả return/throw.
3. **Không chặn hot path:** metric update, nonblocking `offer`, JFR enabled guard có thể phù hợp; network I/O đồng bộ thì không.
4. **Không tạo vòng lặp:** nếu instrumentation bọc serializer, logger, exporter hoặc `LongAdder`, chính bộ đo có thể tự gọi lại dẫn tới recursion.
5. **Bảo toàn method semantics:** giá trị trả về, exception, `finally`, synchronization, thread context và class initialization phải giữ đúng.
6. **Có nguồn thời gian chuẩn:** dùng monotonic `nanoTime` cho duration; không trộn wall clock và `nanoTime` rồi so trực tiếp.
7. **Giảm dữ liệu quan sát:** chỉ giữ stable operation/outcome và nhóm lỗi; không stringify cả object đầu vào.
8. **Có đường tắt khi disabled:** nếu JFR/event sink không bật, bỏ qua tạo payload đắt tiền.

### 9.1. Wrapper minh họa về outcome, không phải transformer hoàn chỉnh

```java
// Pseudocode Java ở lớp ứng dụng có các helper đã được định nghĩa.
// Không phải một chương trình độc lập và không phải bytecode injection.
long started = System.nanoTime();
boolean success = false;

try {
    Result result = businessOperation();
    success = true;
    return result;
} finally {
    long elapsedNanos = System.nanoTime() - started;
    safeObserve("checkout", success, elapsedNanos);
}
```

`Result`, `businessOperation()` và `safeObserve(...)` ở đây là **ký hiệu kiến trúc**. Đoạn này cần được gắn đúng control-flow nếu method có checked exceptions, nhiều return path hoặc yêu cầu cập nhật trạng thái phức tạp. Với bytecode transformer, dùng thư viện/CodeBuilder tạo CFG và stack frames hợp lệ, không sao chép nguyên mẫu này như một method đầy đủ.

### 9.2. Vị trí an toàn của `safeObserve`

Trong một ứng dụng cần ưu tiên thành công của nghiệp vụ, phần quan sát nên có chính sách xử lý lỗi được xác định từ trước:

```java
// Mã minh họa bên trong một helper có queue và dropCounter đã khai báo.
static void offerSafely(Observation event) {
    if (!queue.offer(event)) {
        dropCounter.increment();
    }
}
```

Đây không phải class Java độc lập. Trong production cần xác định liệu `Observation` được tạo khi disabled hay không, xử lý lỗi bất ngờ từ sink, và ai có trách nhiệm xử lý shutdown. Đừng để `Throwable` được nuốt vô điều kiện khiến `OutOfMemoryError` hay lỗi VM nghiêm trọng bị che giấu; chính sách fail-open/fail-closed phải được đội vận hành và nghiệp vụ đồng ý.

## 10. Counter, queue và JFR có thể kết hợp nhưng phải có trách nhiệm rõ

Ví dụ yêu cầu:

- Dashboard hiển thị throughput/errors mỗi phút.
- Lúc bất thường cần chi tiết vài request representative.
- Khi độ trễ tăng cần tương quan với GC/lock theo timeline JVM.

Thiết kế hợp lý có thể là:

```text
Một checkout hoàn tất
   │
   ├─ completed_total.increment()         (luôn bật)
   ├─ failed_total.increment()            (chỉ failure)
   ├─ queue.offer(error summary)          (chỉ failure hoặc sample)
   └─ JFR duration event                  (chỉ khi recording enabled
                                          và vượt threshold)
```

Điểm quan trọng là **các sink giữ mức chi tiết khác nhau**. Không được cộng counter `completed_total` với số queue messages và số JFR events rồi xem là tổng request. Những giá trị đó có thể khác nhau **theo thiết kế** vì filtering, sampling, drop và threshold.

Đặt tên và ghi tài liệu về mẫu số: chẳng hạn `queue_drop_total / queue_attempted_total` là tỷ lệ từ chối queue, **không phải tỷ lệ checkout thất bại**. `jfr-events` là số event đã được lưu/đọc trong một recording, không nhất thiết bằng số method invocations.

## 11. Đồng bộ hóa, độ trễ và chi phí GC

### 11.1. Chi phí tạo object

Mỗi queue event thường là một object hoặc một slot trên ring buffer; event JFR cũng có object tương ứng khi code tạo instance. Ở hot path, nên tránh:

```java
// Ví dụ KHÔNG nên làm khi bị drop thường xuyên:
String details = expensiveSerializeEntireRequest(request);
queue.offer(new FullEvent(details));
```

`expensiveSerializeEntireRequest` và `FullEvent` là tên minh họa. Nếu queue đã đầy, serialization phí công; nếu request có thông tin nhạy cảm, còn tạo thêm bản sao dữ liệu trong heap.

Thay vào đó, giữ field nhỏ, ID được chấp thuận và một enum-like status cố định; nếu cần thao tác đắt tiền, thực hiện bên consumer **sau khi đã nhận** bản ghi, nhưng không chuyển tham chiếu tới object mutable sẽ bị ứng dụng thay đổi sau đó. Chụp snapshot nhỏ bất biến rồi enqueue.

### 11.2. Chi phí điều phối thread

Đừng tạo **một thread mới cho mỗi observation**. Dùng một hoặc một số worker được giới hạn, batch và flush. Một queue có một consumer giúp giữ thứ tự dequeue của chính queue; nhiều worker tăng throughput nhưng thứ tự hoàn tất export có thể đổi.

### 11.3. Chi phí JFR

Đừng bật stack traces cho mọi micro-event theo mặc định. Sử dụng `isEnabled` trước payload đắt, `shouldCommit` sau khi đã biết duration để xét threshold. Khi đổi cấu hình JFR lúc runtime, sự kiện có thể bị bật/tắt giữa các lần gọi; instrumentation phải đúng nghiệp vụ dù thu thập thay đổi.

### 11.4. Cách benchmark

Hãy đo với 2 phiên bản cùng workload:

```text
baseline: không có instrumentation
probe-only: chỉ đo và counter
probe+queue: đo và enqueue/consumer
probe+JFR: đo và Recording bật ở cấu hình mục tiêu
```

So p50/p95/p99 latency, throughput, CPU, allocation rate, GC pauses, drop rate và export delay. Chạy warm-up đủ và tránh kết luận từ một lần benchmark ngắn trên laptop. Một queue quá nhỏ trong bài lab là **để tạo tình huống drop có thể lặp lại**, không phải khuyến nghị capacity 2 cho production.

## 12. Giới hạn và mức tin cậy của mỗi sink

### Counter

- Khi tiến trình còn sống, update được giữ trong bộ nhớ theo kiểu đã chọn.
- Sau khi crash, snapshot chưa scrape có thể mất.
- `LongAdder.sum()` không atomic snapshot khi producer còn chạy; `AtomicLong.get()` có tính nguyên tử trên biến đơn, nhưng nhiều counter đọc lần lượt vẫn không phải snapshot xuyên nhiều metric.
- Một counter không thể chứng minh event nào đã xảy ra nếu cần đối soát từng giao dịch.

### Hàng đợi sự kiện

- `offer(true)` chỉ xác nhận event đã vào queue tại thời điểm đó.
- Worker lấy event khỏi queue chưa chắc backend đã nhận.
- Backend ack chưa chắc tương đương downstream đã xử lý bền vững.
- Retry có thể gây duplicate; crash có thể làm mất record trong RAM.
- Muốn at-least-once/dedup/exactly-once theo business semantics cần cơ chế giao nhận bền vững phù hợp, không suy ra từ Java queue.

### JFR Event

- Event được commit theo cấu hình enabled/threshold và giới hạn recording.
- Dữ liệu JFR có retention, buffer, disk repository và lifecycle riêng.
- JFR thu được context JVM tốt hơn một counter, nhưng không phải transaction log bảo đảm vô hạn.
- Một JFR event không tự trở thành metric alert; cần consumer/aggregation nếu muốn dashboard/rate.
- Dùng field `String` không đồng nghĩa payload đã được redacted; phải kiểm soát dữ liệu từ khi tạo event.

**Điểm chung:** Cơ chế xuất số đo **không thay thế** kiểm tra tính đúng đắn của điểm đo. Một counter tăng sai chỗ vẫn là counter sai; một queue giao đủ event sai vẫn là dữ liệu sai; một JFR file hoàn chỉnh không sửa được probe chèn nhầm method.

## 13. Những lỗi thường gặp và cách đọc đúng

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Counter tăng nhưng dashboard trống | Chưa có exporter/scraper hoặc backend không nhận | Kiểm tra pipeline xuất metrics và scrape interval |
| Counter lúc scrape thấp hơn kỳ vọng tức thời | `LongAdder.sum()` không atomic snapshot khi cập nhật | Đánh giá tốc độ theo cửa sổ, không dùng làm ledger |
| Số time series tăng liên tục | Labels chứa request/user IDs hoặc URL thô | Giới hạn cardinality, chuẩn hóa operation |
| Queue đầy, response time tăng | Dùng `put` hoặc serialize đồng bộ trước enqueue | Xem lại drop/sampling/batching và ngân sách latency |
| Queue không đầy nhưng export thiếu | Worker lỗi, batch thất bại hoặc sink trả lỗi | Theo dõi accepted/exported/failed, ack và retry |
| Drop = 0 nhưng mất dữ liệu sau crash | In-memory queue không bền vững | Thiết kế durable sink nếu bắt buộc |
| Dữ liệu xuất trùng | Retry sau timeout hoặc nhiều probe cho cùng event | Gắn event identity/dedup phù hợp và tránh instrument hai lần |
| JFR Event không xuất hiện | Recording chưa start, event disabled, threshold quá cao | Kiểm tra `isEnabled`, `shouldCommit`, cấu hình recording |
| JFR có event nhưng không tìm thấy trong parser | Lọc nhầm event name hoặc đọc sai `.jfr` file | Kiểm tra `@Name`, file path, thời gian start/stop |
| JFR gây overhead cao | Event quá thường xuyên, payload/stack trace nặng | Threshold, sampling, tắt stack trace và benchmark |
| Không thấy field của event | JFR chỉ hỗ trợ một số kiểu field | Dùng primitive/String/Class/Thread, kiểm tra annotations |
| Agent gây recursion hoặc `StackOverflowError` | Instrument chính helper/exporter hoặc logger | Loại trừ class của agent, guard reentrancy, kiểm tra classloader |
| Agent làm mất exception nghiệp vụ | Lỗi đo/export thoát khỏi `finally` | Tách chính sách lỗi telemetry khỏi luồng nghiệp vụ |
| JFR unavailable | Runtime image/JVM không có JFR hoặc chính sách chặn | Kiểm tra JDK, module, quyền repository |
| Method latency tăng khi bật đo | Producer làm việc nặng, block hoặc allocation nhiều | Giảm payload, chuyển việc khỏi hot path và đo thực tế |

## 14. Checklist triển khai trước production

1. **Định nghĩa câu hỏi:** rate, distribution, event-by-event hay JVM timeline? Có cần forensic/audit không?
2. **Xác định đơn vị đếm:** request, attempt, retry, method call, transaction hay exception?
3. **Chọn thời điểm ghi:** entry/exit/throw, có cần duration cả failed call?
4. **Chọn sink chính:** counter cho aggregate, queue cho event pipeline, JFR cho diagnostic runtime.
5. **Thiết kế schema:** tên ổn định, field tối thiểu, units, timestamp/duration rõ ràng.
6. **Giới hạn cardinality:** tránh user ID, raw URL, full exception message trong labels.
7. **Đặt ngân sách overhead:** bao nhiêu nanosecond/microsecond, allocation, CPU và tần suất event?
8. **Chọn overflow:** `offer` + drop metric, sampling, batch hoặc blocking có kiểm soát.
9. **Định nghĩa retention/durability:** dữ liệu cần giữ bao lâu, crash/restart có thể mất gì?
10. **Định nghĩa lỗi và retry:** khi sink lỗi, ứng dụng phải tiếp tục hay thất bại? Ai quyết định?
11. **Định nghĩa shutdown:** dừng producer, drain có thời hạn, flush/close consumer và recording.
12. **Kiểm soát privacy:** redaction, access control và vòng đời dữ liệu ở mỗi backend.
13. **Bảo vệ agent:** không instrument bản thân, tránh class-loader recursion và quá tải heap.
14. **Theo dõi chính công cụ:** accepted, dropped, consumer failures, exporter latency và queue depth.
15. **Test có chủ đích:** bình thường, burst, full queue, disabled JFR, threshold, crash và slow sink.
16. **So sánh có/không agent:** semantics nghiệp vụ, latency p95/p99, CPU, GC, log volume và cỡ recording.

## 15. Tình huống chọn công cụ

**Tình huống A — API gateway cần QPS và error rate.**  
Chọn counters phân theo operation/outcome ổn định; scrape định kỳ và tính rate trên cửa sổ. Nếu cần latency distribution, thêm histogram có buckets hợp lý, không tạo event record cho mọi request chỉ để đếm.

**Tình huống B — cần gửi thông tin rút gọn của 1% request lỗi đến một collector.**  
Có thể sample có kiểm soát rồi `offer` vào bounded queue. Ghi nhận số attempted/sampled/accepted/dropped; worker batch và retry theo chính sách. Hãy công bố sampling rate khi phân tích.

**Tình huống C — Java server thỉnh thoảng chậm khi GC hoặc lock contention.**  
Custom JFR Event có duration và operation ít cardinality phù hợp. Bật recording theo đợt hoặc cấu hình threshold để liên hệ cùng timeline với GC/lock/JVM events. Tránh tự gửi network từ method đang chậm.

**Tình huống D — audit mọi lần chuyển tiền và phải đối soát chính xác.**  
Không nên dùng counter, queue trong RAM hoặc JFR làm **nguồn sự thật duy nhất**. Cần lưu giao dịch bền vững/transactional outbox và cơ chế giao nhận đủ bảo đảm; telemetry chỉ hỗ trợ quan sát.

**Tình huống E — muốn debug một lần lỗi hiếm khi backend mạng không sẵn sàng.**  
Counter vẫn cho error rate, JFR recording trên JVM có thể giữ context phục vụ chẩn đoán nếu đã bật, còn queue remote có thể drop khi network outage. Cần biết data retention và không hứa rằng tất cả event đều tồn tại.

**Tình huống F — một phương thức được gọi hàng triệu lần/giây.**  
Chọn counter hoặc sampling/threshold trước; tránh allocation và string formatting cho mỗi lời gọi. Nếu bật JFR, benchmark với cấu hình thực; nếu dùng queue, phải có capacity và admission/drop policy.

## 16. Câu hỏi tự luyện

**1. Cần biết tổng số lỗi trong 5 phút, có phải queue tốt hơn counter?**  
Không nhất thiết. Counter phù hợp hơn khi chỉ cần aggregate; cần exporter và cách tính chênh lệch theo thời gian.

**2. `LongAdder.sum()` có phải snapshot nguyên tử trong lúc nhiều thread tăng số?**  
Không. Giá trị chính xác nếu không có update đồng thời; với update concurrent, kết quả có thể không bao gồm một số thay đổi đang diễn ra.

**3. `queue.offer(event)` trả `false` nghĩa là sao?**  
Không thể thêm ngay vì queue không còn chỗ; với `ArrayBlockingQueue` bounded, `offer` không block và phải có chính sách dropped/sampled khác.

**4. `queue.offer(event)` trả `true` có nghĩa backend đã lưu event?**  
Không. Nó mới vào queue nội bộ, consumer/export có thể lỗi hoặc tiến trình có thể crash.

**5. Có nên dùng `put` trong method instrumented đang phục vụ request?**  
Cần rất thận trọng. `put` có thể block vô thời hạn khi đầy, gây tăng latency hoặc deadlock theo bối cảnh hệ thống.

**6. `Event.isEnabled()` khác `Event.shouldCommit()` ở đâu?**  
`isEnabled()` cho biết event đang bật trong ít nhất một recording; `shouldCommit()` còn xét threshold dựa trên duration để quyết định event có được ghi hay không.

**7. Gọi `Event.commit()` thì event đã gửi lên hệ thống tracing từ xa chưa?**  
Chưa. Nó gửi dữ liệu cho JFR trong JVM; recording/stream/collector là phần riêng.

**8. JFR có trường Java object tùy ý hoặc array không?**  
Không theo cách tự động như POJO serialization; các field type hỗ trợ được JDK giới hạn. Hãy dùng kiểu được hỗ trợ và tránh thông tin nhạy cảm.

**9. Một method được tính một lần trong counter nhưng không có JFR Event: có phải hỏng?**  
Không nhất thiết. JFR có thể disabled, có threshold hoặc sample; các sink có semantics khác nhau.

**10. Có thể dùng JFR làm audit log duy nhất không?**  
Không nên. JFR là diagnostic recording với buffer/retention và khả năng không thu đủ sự kiện trong một số điều kiện; audit cần thiết kế độ bền khác.

**11. Đo duration bằng `System.currentTimeMillis()` hay `System.nanoTime()`?**  
Dùng `nanoTime()` để tính khoảng thời gian đã trôi qua; wall clock dùng để gắn timestamp khi cần.

**12. Vì sao queue demo luôn drop một sự kiện?**  
Vì queue có capacity 2 và ba lần `offer` xảy ra **trước khi** drain; producer và consumer không chạy song song trong bài lab.

**13. Vì sao `RecordingFile.readAllEvents` không nên dùng để đọc file JFR production rất lớn?**  
Vì nó nạp toàn bộ events vào list; có thể tăng mạnh sử dụng bộ nhớ. Với file lớn, dùng cách đọc streaming/iterator và giới hạn tài nguyên.

**14. Nếu muốn p99 latency, lấy `sum(duration)/count` được không?**  
Không. Đó là trung bình; cần phân bố/histogram hoặc raw duration events với phương pháp tính percentile phù hợp.

**15. Cách tránh instrumentation làm biến đổi exception của method?**  
Thiết kế probe ở `finally` và quản lý lỗi của sink theo policy, tránh ném exception telemetry đè lên exception nghiệp vụ.

## 17. Tài liệu tham khảo chính thức

- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): increment/sum và cảnh báo sum không phải atomic snapshot.
- [JDK 17 — `AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): thao tác số nguyên nguyên tử.
- [JDK 17 — `ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded buffer, `offer`, `put` và khác biệt blocking.
- [JDK 17 — `Event`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html): custom JFR event, `isEnabled`, `begin`, `end`, `shouldCommit`, `commit`.
- [JDK 17 — `Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): bật recording, giới hạn, stop và dump ra file.
- [JDK 17 — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc event từ `.jfr` và giới hạn `readAllEvents`.
- [JDK 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): streaming custom/JVM events.
- [JDK 17 — `java.lang.instrument.Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): môi trường phát triển Java agent.
- [JDK 17 — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf): mô hình tạo và tiêu thụ event.

**Ghi nhớ:** Khi chỉ cần **số lượng**, dùng bộ đếm và một exporter phù hợp. Khi cần **bản ghi chi tiết có pipeline riêng**, dùng **bounded queue** cùng drop/backpressure/delivery policy. Khi cần **timeline chẩn đoán đồng bộ với hoạt động JVM**, dùng **JFR Event** với enabled/threshold/recording được cấu hình. Cả ba đều phải bảo toàn hành vi nghiệp vụ, kiểm soát overhead và làm rõ những dữ liệu **không được bảo đảm** sẽ tồn tại.