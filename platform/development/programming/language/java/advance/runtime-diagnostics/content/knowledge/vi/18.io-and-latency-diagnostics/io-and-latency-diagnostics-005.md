# 18.5 Thu thời điểm nhận, bắt đầu, kết thúc và kết quả bằng log hoặc custom event

## 1. Mục tiêu: dựng lại một hành trình I/O thay vì chỉ biết “request chậm”

Trong ứng dụng Java có HTTP handler, message consumer, worker pool, tác vụ ghi file, gọi database hoặc gọi HTTP downstream, một thao tác có thể trải qua **chờ trước khi được xử lý** và **thời gian thực hiện công việc**. Chỉ ghi “bắt đầu xử lý” và “xử lý xong” thường bỏ qua phần queue/dispatch; chỉ ghi một tổng thời gian lại không cho biết chậm ở đâu.

Để truy vấn và chẩn đoán **I/O và độ trễ**, hãy thu bốn thành phần thống nhất cho mỗi operation/attempt:

1. **RECEIVED (nhận):** thời điểm ứng dụng nhận/tiếp nhận công việc tại ranh giới đã định nghĩa.
2. **STARTED (bắt đầu):** thời điểm worker thực sự bắt đầu xử lý công việc đó.
3. **ENDED (kết thúc):** thời điểm thao tác được coi là hoàn thành theo ranh giới đo, kể cả nhánh lỗi.
4. **RESULT (kết quả):** trạng thái thành công/thất bại/timeout/huỷ/từ chối và thông tin lỗi an toàn để quan sát.

Có thể ghi ba mốc thời gian cộng kết quả vào **structured logs**, **custom JFR event**, hoặc kết hợp cả hai. Việc chọn phương án phụ thuộc nhu cầu truy vấn online, overhead, độ chi tiết, thời gian lưu trữ và dữ liệu cần liên kết giữa hệ thống.

Sau bài này, bạn có thể thiết kế schema, tính queue-to-start/work/end-to-end latency, gắn correlation ID, đo chính xác bằng `System.nanoTime()`, ghi đủ các nhánh kết quả trong `try/finally`, tạo custom JFR event Java 17+, và đọc lại event để kiểm tra bằng chứng.

**Điều đầu tiên phải định nghĩa:** “nhận” là lúc service tiếp nhận request/message hay lúc job được enqueue? “kết thúc” là lúc I/O callback hoàn tất hay lúc response được flush? Nếu các service hoặc đoạn code dùng ranh giới khác nhau, phép so sánh số liệu có thể vô nghĩa dù timestamp hợp lệ.

## 2. Bốn mốc và ranh giới đo

```text
Client / upstream
       |
       v
  [RECEIVED] t_recv     Service đã nhận/accept công việc
       |
       | chờ dispatch / queue / permit / worker
       |
  [STARTED] t_start     Worker bắt đầu công việc cần đo
       |
       | thực hiện I/O, compute, retry nội bộ theo phạm vi
       |
  [ENDED]   t_end       Kết quả thao tác đã được xác định
       |
       +---- RESULT     SUCCESS / ERROR / TIMEOUT / CANCELLED / REJECTED ...
       |
       v
     response / ack / downstream outcome (tuỳ ranh giới)
```

### 2.1. RECEIVED: nhận ở ranh giới nào?

Ví dụ:

- **HTTP server:** khi handler hoặc middleware đầu vào nhận request sau khi container đã dispatch; đây không phải thời điểm packet đầu tiên đến NIC.
- **Message consumer:** khi callback nhận message, hoặc khi hệ thống enqueue job để xử lý.
- **Worker queue:** khi job được nhận tại producer và chuẩn bị submit, có thể trước lúc thực sự đặt vào queue.
- **File I/O:** khi ứng dụng chấp nhận yêu cầu ghi/đọc, không nhất thiết khi syscall bắt đầu.

Gắn `requestId` / `operationId` và chụp timestamp **ngay khi nhận**. Với job retry, cần thêm `attempt` hoặc `attemptId` để không ghép nhầm hai lần chạy có cùng business ID.

Nếu mục tiêu là đo **thời gian đợi trong queue thuần túy**, nên có thêm `enqueuedAt` và `dequeuedAt`. Trong bài, `t_start - t_recv` được gọi là **wait-to-start** vì nó có thể bao gồm xác thực, dựng context, dispatch và chờ queue; không được mặc nhiên gọi là “queue time” chính xác.

### 2.2. STARTED: bắt đầu xử lý thật sự

`t_start` phải lấy khi công việc **được worker chạy**, không phải khi gọi `executor.submit(...)`. Hai mốc này khác nhau dưới tải nặng. Với async API, thời điểm khởi tạo `CompletableFuture` cũng không bảo đảm I/O đã bắt đầu.

Trường hợp có semaphore hoặc rate limiter, xác định rõ STARTED trước hay sau bước acquire; nếu trước, thời gian chờ permit sẽ nằm trong work duration, còn nếu sau, nó nằm trong wait-to-start. Điều này không sai nếu được ghi rõ và nhất quán.

### 2.3. ENDED: đúng định nghĩa hoàn tất

Với I/O đồng bộ, ENDED có thể là lúc method đọc/ghi trả về hoặc throw. Với I/O bất đồng bộ, ENDED là khi callback/completion báo xong **toàn bộ thao tác bạn định đo**, không phải lúc đăng ký callback hoặc lúc trả một future chưa hoàn thành.

Nếu phần “ghi file” chỉ được đưa vào OS page cache, method hoàn thành **không đồng nghĩa dữ liệu đã fsync xuống thiết bị lưu trữ bền vững**. Nếu mục tiêu là durability, phải thiết kế mốc theo API đảm bảo durability tương ứng. Tương tự, một response đã tạo xong chưa hẳn đã được gửi hết đến client.

### 2.4. RESULT: trạng thái phải ghép với ENDED

`result` nên có từ vựng rõ ràng, ví dụ:

| Result | Ý nghĩa | Thông tin bổ sung có ích |
| --- | --- | --- |
| `SUCCESS` | Công việc thành công theo hợp đồng | status/code, số byte/rows, downstream status |
| `ERROR` | Công việc kết thúc thất bại | loại exception, error code đã chuẩn hoá |
| `TIMEOUT` | Vượt deadline được thiết kế | deadline, loại timeout, caller/downstream |
| `CANCELLED` | Bị huỷ có chủ đích hoặc bị interrupt | lý do, bên phát lệnh huỷ |
| `REJECTED` | Bị từ chối trước khi bắt đầu | queue full, overload, rate limit |
| `UNKNOWN` | Chưa xác định kết quả cuối | Không tự chuyển sang SUCCESS/ERROR |

Không log exception stack trace đầy đủ ở mọi event nếu tần suất rất cao; có thể lưu `errorType` và error code dạng chuẩn, còn stack chi tiết ở nơi thích hợp. Đặc biệt không ghi token, password, request body hoặc PII vào log/JFR.

Thông thường, **ENDED + RESULT nằm chung một structured-log record hoặc một custom event được commit sau khi kết thúc**. Không bắt buộc phải có dòng log thứ tư mang tên RESULT nếu outcome đã gắn với ENDED. Nhưng phải đảm bảo result là giá trị cuối, không phải `PENDING` còn sót.

## 3. Ba khoảng thời gian cần tính

Khi ba mốc thuộc **cùng một process/JVM** và lấy từ đồng hồ monotonic:

- `waitToStart = t_start - t_recv`
- `work = t_end - t_start`
- `endToEnd = t_end - t_recv`
- Bất biến kiểm tra: **`endToEnd = waitToStart + work`** nếu các mốc dùng cùng clock/cùng đơn vị và không bị xử lý sai.

Ví dụ giả định, các mốc sau đều tính theo **milli giây trên một đồng hồ monotonic chung**, chỉ dùng để tính tay:

| Operation | `t_recv` | `t_start` | `t_end` | Wait-to-start | Work | End-to-end | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `r-101` | 1.000 | 1.012 | 1.060 | 12 ms | 48 ms | **60 ms** | SUCCESS |
| `r-102` | 2.000 | 2.080 | 2.110 | 80 ms | 30 ms | **110 ms** | ERROR |

Diễn giải:

- `r-101` có tổng 60 ms, chủ yếu ở execution (48 ms).
- `r-102` có tổng 110 ms dù work chỉ 30 ms; phần lớn nằm trước khi worker bắt đầu (80 ms).
- Một kết quả `ERROR` có thể trả rất nhanh; không được tự biến “lỗi” thành “chậm”, hay “thành công” thành “nhanh”.
- Hai request có thể chạy chồng lấp, không thể cộng end-to-end của chúng để suy ra thời gian đồng hồ của cả hệ thống.

Khi có retry, phải phân biệt **latency của một attempt** với **latency của logical request**. Ba attempt 30 ms, 40 ms, 50 ms với backoff 100 ms giữa các lần không tạo ra tổng end-to-end 120 ms; thời gian chờ retry thuộc hành trình request dù không nằm trong work của từng attempt.

## 4. Chọn đúng đồng hồ: timestamp để ghép log, nanoTime để đo duration

### 4.1. Wall clock: `Instant.now()` / `System.currentTimeMillis()`

Wall clock gắn với UTC/Unix epoch. Nó phục vụ:

- đặt một mốc trên trục thời gian, đối chiếu với HTTP access log, tracing, GC/JFR;
- tìm lúc nào sự cố xảy ra;
- diễn đạt thời gian cho người vận hành.

Ví dụ `2026-01-01T10:00:00.000Z` là một thời điểm UTC; có thể hiển thị sang `Asia/Ho_Chi_Minh` khi cần. Tuy nhiên, wall clock có thể bị điều chỉnh vì NTP, môi trường ảo hóa hoặc thay đổi clock system. `currentTimeMillis()` còn có độ phân giải mili giây. **Không lấy hiệu hai wall-clock timestamps làm nguồn chuẩn duy nhất để đo latency ngắn**.

### 4.2. Monotonic elapsed clock: `System.nanoTime()`

`nanoTime()` trả clock tick đơn điệu phục vụ **đo thời gian trôi qua**, không phải epoch time. Giá trị tuyệt đối không có ý nghĩa lịch, có thể âm, nhưng hiệu hai lần gọi trong **cùng JVM/process** có ý nghĩa duration:

```java
// Fragment minh họa, không phải chương trình độc lập.
long receivedNano = System.nanoTime();
// ... sau khi worker thật sự bắt đầu:
long startedNano = System.nanoTime();
// ... khi thao tác hoàn thành:
long endedNano = System.nanoTime();

long waitNanos = startedNano - receivedNano;
long workNanos = endedNano - startedNano;
long totalNanos = endedNano - receivedNano;

double totalMillis = totalNanos / 1_000_000.0;
```

Cách này tránh lỗi đồng hồ tường bị chỉnh làm duration âm hoặc bị nhảy bất thường. Độ phân giải của giá trị tính theo nano giây **không đồng nghĩa phần cứng có độ chính xác một nano giây**. Đừng đối chiếu các số `nanoTime` tuyệt đối giữa **hai JVM khác nhau hoặc hai máy khác nhau**; chỉ tính hiệu các mốc thuộc cùng process/clock domain.

Nếu request đi từ gateway sang service khác, hãy mang **traceId/spanId**, ghi timestamps UTC có đồng bộ clock và dùng distributed tracing để kết nối các span. Với mỗi service, đo duration bằng monotonic clock cục bộ. Không trừ `nanoTime` của service A cho `nanoTime` của service B.

### 4.3. Ghi hai loại clock mà không nhầm

Mỗi mốc quan trọng có thể chụp một cặp:

```text
receivedAtEpochMs     = System.currentTimeMillis()
receivedAtMonotonicNs  = System.nanoTime()     (chỉ dùng nội bộ JVM)
```

Hai lệnh gọi không xảy ra đúng một tích tắc; khoảng lệch nhỏ là bình thường. Cần thống nhất thứ tự lấy mốc và tránh suy luận rằng hiệu timestamp wall **phải bằng chính xác** hiệu nanoTime. Có thể log UTC time và giá trị duration đã tính, nhưng không cần ghi `nanoTime` tuyệt đối lâu dài nếu không có trường hợp dùng.

**Đơn vị:** `1 ms = 1.000.000 ns`; dùng `long` để lưu `...Nanos` và đổi sang `double millis = nanos / 1_000_000.0` khi hiển thị. Không đặt tên field `latencyMs` nhưng lại lưu nano giây.

## 5. Thiết kế structured-log schema tối thiểu

Một log record phục vụ điều tra không nên chỉ là chuỗi “started processing...”. Cần tên field ổn định và có khả năng lọc:

| Field | Kiểu gợi ý | Ý nghĩa |
| --- | --- | --- |
| `timestamp` hoặc `epochMs` | ISO-8601 UTC / epoch milliseconds | Wall-clock khi phát log |
| `phase` | Enum-like string | `RECEIVED`, `STARTED`, `ENDED` |
| `requestId` | String | Correlation ID cho logical request |
| `attemptId` / `attemptNo` | String / integer | Phân biệt retries |
| `operation` | String | Tên thao tác giới hạn cardinality, ví dụ `file.write` |
| `result` | String | `PENDING`, `RUNNING`, `SUCCESS`, `ERROR`, ... |
| `errorType` / `errorCode` | String optional | Loại lỗi, không chứa secret/message nhạy cảm |
| `waitToStartNanos` | long, khi có STARTED/ENDED | Thời gian từ nhận tới start |
| `workNanos` | long, khi ENDED | Thời gian start đến end |
| `totalNanos` | long, khi ENDED | End-to-end theo ranh giới đã chọn |
| `threadName` | String optional | Hữu ích khi điều tra executor |
| `traceId` / `spanId` | String optional | Liên kết telemetry giữa service |
| `bytes` / `status` | long / int optional | Kết quả I/O có ý nghĩa nghiệp vụ |

Ví dụ log JSON **minh họa**, mốc thời gian giả định, không phải stdout của chương trình:

```json
{"timestamp":"2026-01-01T10:00:00.000Z","phase":"RECEIVED","requestId":"r-101","attemptNo":1,"operation":"file.write","result":"PENDING"}
{"timestamp":"2026-01-01T10:00:00.012Z","phase":"STARTED","requestId":"r-101","attemptNo":1,"operation":"file.write","result":"RUNNING","waitToStartNanos":12000000}
{"timestamp":"2026-01-01T10:00:00.060Z","phase":"ENDED","requestId":"r-101","attemptNo":1,"operation":"file.write","result":"SUCCESS","waitToStartNanos":12000000,"workNanos":48000000,"totalNanos":60000000,"bytes":4096}
```

Không tự tin hoàn toàn vào việc ghép ba dòng bằng **thread name**: request có thể chuyển thread, các thread được tái sử dụng, cùng tên có thể xuất hiện ở nhiều JVM. Dùng correlation ID nhất quán, và nếu có retry thì ghép trên `requestId + attemptNo` hoặc một `attemptId` duy nhất.

### 5.1. Log ở đâu để đủ cả nhánh lỗi?

Một flow đồng bộ lý tưởng:

```text
ingress:
    capture received
    log RECEIVED
    enqueue/dispatch

worker:
    capture started
    log STARTED
    result = UNKNOWN
    try:
        thực hiện I/O
        result = SUCCESS
    catch timeout:
        result = TIMEOUT
        rethrow/hoàn tất thất bại theo hợp đồng
    catch other error:
        result = ERROR
        rethrow/hoàn tất thất bại theo hợp đồng
    finally:
        capture ended
        compute wait/work/total
        log ENDED với result cuối cùng
```

Đây là **pseudocode**, không phải Java runnable. Với async, đặt ENDED trong callback kết thúc của `CompletionStage` hoặc API tương ứng, không đặt ngay sau lời gọi trả `Future`. Trong luồng cancel/timeout/race, cần bảo đảm chỉ một nơi commit kết quả cuối cho một attempt; một `AtomicBoolean.compareAndSet(false, true)` hoặc state machine có thể giúp tránh ghi hai ENDED khi timeout và completion cùng đến.

### 5.2. Thread pools, MDC và context propagation

Log framework như SLF4J/Logback có thể dùng **MDC** đưa `requestId`, `traceId` vào mỗi dòng. Nhưng MDC thường dựa vào context gắn với thread, nên không được giả định nó tự động đi từ thread nhận request sang worker của `ExecutorService`. Hãy truyền một context object, hoặc cấu hình context propagation có chủ đích.

Trong worker, cần dọn MDC bằng `try/finally` để không rò `requestId` của request trước sang task sau. Với virtual threads hay reactive code, chọn cơ chế propagation tương ứng; không dựa vào ThreadLocal thiếu kiểm soát.

### 5.3. Ưu tiên logs hay custom JFR event?

| Phương án | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| Structured logs ở từng phase | Dễ stream, index, alert, điều tra xuyên service bằng trace ID | Nhiều dòng/event, logging backend có thể chịu tải lớn; clock bị lệch |
| Một custom JFR event khi hoàn tất | Gom bốn mốc, duration và outcome vào một bản ghi nhị phân; thuận tiện đối chiếu JVM events | Cần bật recording, thu/dump file, không phải kho truy vấn online tự động |
| Kết hợp log + custom JFR | Log cho kiểm soát online; JFR cho phiên chẩn đoán sâu và correlation trong JVM | Phải nhất quán schema/ID; tránh ghi trùng payload nhạy cảm |

Không có lựa chọn bắt buộc dùng cả hai. Với service đang có tracing/metrics, thường chỉ cần mức log phù hợp và phát JFR custom events khi điều tra sâu.

## 6. Custom JFR event: lưu cả timeline và kết quả trong một record

Một event subclass của `jdk.jfr.Event` có thể chứa những field do ứng dụng định nghĩa. Dùng các annotation:

- `@Name("demo.IoRequest")`: tên event kỹ thuật ổn định để lọc khi đọc file.
- `@Label`: tên hiển thị thân thiện.
- `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)`: nói rõ long field đó là timestamp epoch milliseconds.
- `@Timespan(Timespan.NANOSECONDS)`: nói rõ long field đó lưu duration nano giây.
- `@StackTrace(false)`: tắt ghi stack mặc định để giảm overhead khi chưa cần call site; có thể override trong recording.

**Lựa chọn quan trọng về event duration:** Trong ví dụ, `event.begin()` xảy ra **khi worker bắt đầu** và `event.end()` ngay khi work kết thúc. Vì vậy duration nội tại của event JFR chủ yếu đại diện **thời gian xử lý trong worker**, không bao gồm chờ từ nhận đến start. Ta lưu thêm `receivedEpochMs`, `startedEpochMs`, `endedEpochMs`, `waitToStartNanos`, `workNanos`, `totalNanos` để không mất thông tin trước start.

Nếu thay vì thế bạn muốn duration JFR đại diện toàn bộ end-to-end, phải đặt `begin()` ở ranh giới nhận và `end()` ở ranh giới hoàn tất với thiết kế vòng đời event an toàn, kể cả chuyển thread và nhánh timeout. Đừng đổi nghĩa duration mà không cập nhật tên/metadata của event.

**Threshold trap:** JFR `threshold` áp dụng cho **duration nội tại event**. Nếu event `begin/end` chỉ bao work, đặt threshold 50 ms có thể làm **mất một request chờ queue 800 ms nhưng xử lý chỉ 2 ms**. Trong ví dụ, đặt `withThreshold(Duration.ZERO)` để giữ cả hai event thử nghiệm; nếu điều tra production, cân nhắc sampling/overhead và chọn threshold phù hợp ranh giới thực sự.

## 7. Thực hành Java 17+: ghi logs và custom JFR, rồi đọc lại

Ví dụ dưới đây tạo hai request giả lập. Cả hai được nhận trước khi submit vào **một worker duy nhất**; worker xử lý lần lượt để thể hiện rõ sự chờ đợi giữa RECEIVED và STARTED. Một request `SUCCESS` và một request ném lỗi I/O giả lập, được phân loại là `ERROR`.

Chương trình **không thực hiện ghi file thực**: `Thread.sleep` mô phỏng thời gian thao tác để tập trung vào kỹ thuật instrument. Thời gian và mức wait-to-start thực tế thay đổi theo máy.

Tạo file **`IoMilestonesDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.*;
import jdk.jfr.*;
import jdk.jfr.consumer.*;

public final class IoMilestonesDemo {
    @Name("demo.IoRequest")
    @Label("I/O request timeline")
    @StackTrace(false)
    public static class IoRequestEvent extends Event {
        public String requestId;
        public String operation;
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) public long receivedEpochMs;
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) public long startedEpochMs;
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH) public long endedEpochMs;
        @Timespan(Timespan.NANOSECONDS) public long waitToStartNanos;
        @Timespan(Timespan.NANOSECONDS) public long workNanos;
        @Timespan(Timespan.NANOSECONDS) public long totalNanos;
        public String outcome;
        public String errorType;
    }
    private record Request(String id, String operation,
                           long receivedEpochMs, long receivedNano,
                           boolean fail) {}
    private static void log(String phase, String id, long epochMs, String result) {
        System.out.printf("phase=%s id=%s epochMs=%d result=%s%n",
                phase, id, epochMs, result);
    }
    private static Request receive(String id, boolean fail) {
        long receivedNano = System.nanoTime();
        long receivedEpochMs = System.currentTimeMillis();
        log("RECEIVED", id, receivedEpochMs, "PENDING");
        return new Request(id, "simulated-file-write",
                receivedEpochMs, receivedNano, fail);
    }
    private static void process(Request request) {
        long startedNano = System.nanoTime();
        long startedEpochMs = System.currentTimeMillis();
        log("STARTED", request.id(), startedEpochMs, "RUNNING");
        IoRequestEvent event = new IoRequestEvent();
        event.begin();
        String result = "SUCCESS";
        String errorType = "";
        try {
            Thread.sleep(25);
            if (request.fail()) throw new IOException("simulated write failure");
        } catch (IOException failure) {
            result = "ERROR";
            errorType = failure.getClass().getSimpleName();
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            result = "CANCELLED";
            errorType = failure.getClass().getSimpleName();
        } finally {
            event.end();
            long endedNano = System.nanoTime();
            long endedEpochMs = System.currentTimeMillis();
            event.requestId = request.id();
            event.operation = request.operation();
            event.receivedEpochMs = request.receivedEpochMs();
            event.startedEpochMs = startedEpochMs;
            event.endedEpochMs = endedEpochMs;
            event.waitToStartNanos = startedNano - request.receivedNano();
            event.workNanos = endedNano - startedNano;
            event.totalNanos = endedNano - request.receivedNano();
            event.outcome = result;
            event.errorType = errorType;
            event.commit();
            log("ENDED", request.id(), endedEpochMs, result);
        }
    }
    private static void verify(Path path) throws IOException {
        int total = 0, success = 0, error = 0;
        try (RecordingFile file = new RecordingFile(path)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!"demo.IoRequest".equals(event.getEventType().getName())) continue;
                total++;
                String outcome = event.getString("outcome");
                if ("SUCCESS".equals(outcome)) success++;
                if ("ERROR".equals(outcome)) error++;
                long wait = event.getLong("waitToStartNanos");
                long work = event.getLong("workNanos");
                long endToEnd = event.getLong("totalNanos");
                if (endToEnd != wait + work || wait < 0 || work < 0) {
                    throw new IllegalStateException("Invalid timeline");
                }
            }
        }
        System.out.printf("verified=%d success=%d error=%d%n", total, success, error);
    }
    public static void main(String[] args) throws Exception {
        Path file = Path.of("io-milestones.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(IoRequestEvent.class)
                    .withThreshold(Duration.ZERO).withoutStackTrace();
            recording.start();
            Request a = receive("req-001", false);
            Request b = receive("req-002", true);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> first = executor.submit(() -> process(a));
                Future<?> second = executor.submit(() -> process(b));
                first.get();
                second.get();
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) executor.shutdownNow();
            }
            recording.stop();
            recording.dump(file);
        }
        verify(file);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên. Flag `--release 17` kiểm tra mã tương thích Java 17:

```bash
javac --release 17 IoMilestonesDemo.java
java IoMilestonesDemo
jfr summary io-milestones.jfr
jfr print --events demo.IoRequest io-milestones.jfr
```

Lệnh `java IoMilestonesDemo` in **sáu dòng phase log với epoch milliseconds thay đổi**, rồi một dòng summary. Ví dụ kết quả từ một lần chạy JDK 24:

```text
phase=RECEIVED id=req-001 epochMs=1793271670097 result=PENDING
phase=RECEIVED id=req-002 epochMs=1793271670107 result=PENDING
phase=STARTED id=req-001 epochMs=1793271670110 result=RUNNING
phase=ENDED id=req-001 epochMs=1793271670164 result=SUCCESS
phase=STARTED id=req-002 epochMs=1793271670164 result=RUNNING
phase=ENDED id=req-002 epochMs=1793271670190 result=ERROR
verified=2 success=1 error=1
```

**Cần phân biệt:** Các số `epochMs` ở trên là số của *một lần chạy thực*, không phải giá trị phải tái tạo. Thời điểm và khoảng chờ thay đổi trên mỗi máy/chạy. Với chương trình này, khi thực hiện thành công, **dòng cuối được kỳ vọng ổn định**:

```text
verified=2 success=1 error=1
```

Hai dòng `RECEIVED` luôn xuất hiện trước các dòng `STARTED` vì ví dụ nhận cả hai request rồi mới submit. Single-thread executor xử lý `req-001` và `req-002` theo thứ tự; work của request thứ hai chứa lỗi giả lập. `jfr summary` báo event type `demo.IoRequest` có **2 instances** trong lần kiểm thử; metadata/bytes và format output của công cụ JFR có thể khác theo JDK.

### 7.1. Tại sao dùng Request record?

`Request` lưu `id`, `operation`, timestamp tường và `receivedNano`. Nó đi theo task đến worker, không phụ thuộc vào ThreadLocal hay MDC tự truyền qua executor. Đây là mẫu tối thiểu để **không đánh rơi ranh giới nhận** khi có queue.

Trong hệ thống thật, context còn có `traceId`, `spanId`, `attemptNo`, deadline và metadata không nhạy cảm. Không nên truyền mọi HTTP headers, body hoặc secrets vào JFR payload chỉ để debugging.

### 7.2. Tại sao ghi ENDED ở finally?

Một thao tác hoàn tất theo cả nhánh thành công và lỗi. Nếu chỉ log sau `try`, exception khiến không có ENDED, khiến bạn tưởng request vẫn còn chạy. `finally` thực hiện capture mốc kết thúc, tính ba duration, commit custom JFR event và in log chung với outcome.

Trong demo, lỗi `IOException` được **chuyển thành result=ERROR** chứ không được rethrow để chương trình có kết quả kiểm thử ổn định. **Ứng dụng thật không nên nuốt lỗi ngoài ý muốn**: sau khi ghi telemetry, phải propagate exception hoặc hoàn thành response/future thất bại theo hợp đồng. Có thể lưu failure rồi rethrow sau khi đã thu mốc; tránh vô tình báo SUCCESS cho caller.

Với `InterruptedException`, demo restore interrupt flag và ghi `CANCELLED`. Trong ứng dụng có cancellation protocol, cần chuyển thông tin huỷ cho caller và đảm bảo resource cleanup; không phải mọi interrupt đều tương đương HTTP client cancellation.

### 7.3. Bất biến tổng thời gian

Demo lấy `receivedNano` trước submit, `startedNano` khi worker chạy và `endedNano` trong finally. Từ đó:

```text
waitToStartNanos = startedNano - receivedNano
workNanos        = endedNano - startedNano
totalNanos       = endedNano - receivedNano

totalNanos == waitToStartNanos + workNanos
```

Đây là bất biến đại số của **ba mốc trên cùng clock**. Đoạn `verify` đọc lại file `.jfr` và ném lỗi nếu các field duration âm hoặc không khớp tổng. Bất biến này giúp phát hiện code ghi sai đơn vị hoặc trộn hai loại clock.

Lưu ý: `workNanos` bắt đầu khi lấy `startedNano`, còn duration nội tại của JFR bắt đầu khi gọi `event.begin()` (sau khi log STARTED và tạo object event). Do đó hai duration rất gần nhau nhưng **không nhất thiết bằng chính xác**. Không dùng chênh lệch nhỏ này để kết luận JFR đo sai.

### 7.4. Dùng RecordingFile để kiểm tra schema và outcome

Khi đọc file JFR:

- `RecordingFile` mở file; vòng `hasMoreEvents()` / `readEvent()` lần lượt duyệt các event.
- `getEventType().getName()` lọc chính xác `demo.IoRequest`; event JVM khác không lẫn vào.
- `getString("outcome")` lấy SUCCESS/ERROR; `getLong("waitToStartNanos")`, `getLong("workNanos")`, `getLong("totalNanos")` lấy các giá trị `long`.
- `@Timestamp` và `@Timespan` là metadata giúp công cụ hiểu **đơn vị**. Khi cần, có thể dùng các API chuyển sang `Instant`/`Duration` tương ứng trên `RecordedEvent` theo field annotation.
- `errorType` trong demo có thể là `"IOException"`; không nên log nội dung message có secrets.
- `try-with-resources` đóng file parser và recording sau khi xong.

**Không nhầm:** File `io-milestones.jfr` chứa telemetry của chương trình; nó không chứa mọi I/O của OS, và trong demo không có I/O thật ngoài cơ chế JFR ghi file. Các dòng log chỉ chứng minh ranh giới mà code tự đánh dấu.

## 8. Logs hay JFR: áp dụng theo môi trường

### 8.1. Khi ưu tiên logs

Structured logs phù hợp nếu cần:

- tìm request bằng ID trên log aggregator;
- biết request nào bị từ chối trước khi worker start;
- phát cảnh báo dựa vào trạng thái hoặc time-to-result;
- liên kết nhiều service bằng traceId và timestamps UTC;
- điều tra lỗi không có recording JFR.

Dùng logging framework với JSON encoder có cấu hình, tránh `System.out.printf` ở production. Ví dụ chương trình dùng stdout để chạy độc lập không cần thư viện ngoài, **không phải khuyến nghị cách logging production**.

Nếu log mọi RECEIVED/STARTED/ENDED cho hàng triệu request/giây, lượng dữ liệu có thể lớn. Có thể dùng metrics cho phân phối/traffic, logs chi tiết có sampling, và JFR cho các đợt chẩn đoán. Nhưng nếu sampling, phải giữ logic nhất quán: tránh ghi chỉ RECEIVED mà mất ENDED do lấy mẫu độc lập, khiến tỷ lệ unfinished bị thổi phồng.

### 8.2. Khi ưu tiên custom JFR events

Custom JFR event phù hợp cho điều tra JVM:

- thu duration với overhead thấp tương đối khi cấu hình phù hợp;
- đối chiếu operation với GC, CPU, allocation, monitor contention, file/socket events;
- chỉ bật event trong giai đoạn cần quan sát;
- tích hợp JMC/JFR parser để nhóm event theo duration/outcome.

JFR chỉ ghi event **được enable và thỏa threshold/sampling/cấu hình thu**. Nếu thấy 0 event, không được suy luận ứng dụng không chạy thao tác ấy: có thể event bị tắt, threshold loại bỏ, recording không đúng thời gian, hoặc chưa dump file.

Đối với custom event có nhiều thuộc tính, khởi tạo/ghi một object per operation vẫn có chi phí. Trong hot path, có thể kiểm tra `event.isEnabled()`/`event.shouldCommit()` để tránh tính payload đắt tiền, nhưng cần đảm bảo **durations/metrics/logs độc lập vẫn được đo** nếu JFR bị tắt. Đừng chỉ ghi outcome trong JFR nếu operations quan trọng cần phản ánh qua monitoring luôn bật.

### 8.3. Ngưỡng và kết quả: tránh mất request chậm vì queue

Nhắc lại một trường hợp rất dễ đánh giá sai:

```text
RECEIVED ---- waitToStart=800 ms ---- STARTED --- work=2 ms --- ENDED
```

Nếu `Event.begin()` ở STARTED và `Event.end()` ở ENDED, đặt `threshold=50 ms` sẽ **không ghi event** (duration nội tại xấp xỉ 2 ms), dù end-to-end hơn 800 ms. Một schema chứa `totalNanos` không khiến `threshold` tự chuyển sang lọc theo field đó.

Nếu mục tiêu là tìm request bị chậm **vì queue**, cân nhắc `threshold=0` rồi tự lọc theo `totalNanos`, hoặc thiết kế một loại event duration bao toàn bộ lifecycle với vòng đời an toàn. Nếu khối lượng quá lớn, cần sampling/tail-based strategy hoặc metrics có giới hạn; đừng vô thức bật chi tiết vô hạn.

## 9. Các tình huống bất đồng bộ đặc biệt

### 9.1. CompletionStage và callback

Sai:

```java
// Minh họa sai: kết thúc ngay sau khi đăng ký async operation.
long start = System.nanoTime();
java.util.concurrent.CompletableFuture<String> future = startAsyncIo();
long end = System.nanoTime(); // Chỉ đo thời gian tạo Future!
```

Đây là **fragment minh họa**, `startAsyncIo()` chưa được định nghĩa nên không phải chương trình độc lập. Bản đúng về nguyên tắc cần lấy ENDED **trong completion path**:

```java
// Fragment nguyên tắc, không phải chương trình độc lập.
// 'future', 'context', 'completeOnce' do ứng dụng cung cấp.
future.whenComplete((value, failure) -> {
    long endedNano = System.nanoTime();
    String outcome = (failure == null) ? "SUCCESS" : "ERROR";
    completeOnce(context, endedNano, outcome, failure);
});
```

Callback có thể chạy trên thread khác; cần **truyền context và monotonic timestamp đúng phạm vi JVM**. Nếu timeout và callback cùng xảy ra, `completeOnce` nên là cơ chế atomic/terminal-state một lần để không ghi hai ENDED. Cũng phải làm rõ ranh giới: timeout của caller chưa chắc huỷ tác vụ I/O dưới tầng dưới; nếu request kết thúc với TIMEOUT nhưng downstream vẫn chạy, có thể cần hai spans/events riêng.

### 9.2. Request không bao giờ có ENDED

Một số trường hợp không thể thực hiện finally: process crash, `kill -9`, mất máy, shutdown bất thường hoặc log pipeline đánh rơi dữ liệu. Có RECEIVED mà không có ENDED **chỉ là tín hiệu missing terminal record**, không chứng minh tác vụ treo vĩnh viễn.

Để phân biệt:

- có heartbeat/process restart và time window;
- kiểm tra deadline/timeout ở nguồn và nơi nhận;
- dùng metric `in_flight`, hàng đợi và trạng thái executor;
- ghi `attemptId` để xác định retries;
- theo dõi log-drop và retention của hệ thống telemetry.

Một event JFR commit ở cuối cũng **không xuất hiện** nếu JVM chết trước commit hoặc recording chưa flush/dump được. Khi cần phát hiện hung jobs từ xa, logs ở RECEIVED/STARTED và metric live có thể đáng tin hơn một event chỉ phát lúc hoàn tất.

### 9.3. Rejected tasks, timeouts, retries

- **REJECTED:** nếu executor không nhận task, có thể không có STARTED. Ghi terminal result tại ingress/dispatch với t_end tại lúc từ chối; cấu trúc time có thể không có `workNanos`. Không giả tạo STARTED bằng t_received.
- **TIMEOUT:** đánh dấu theo deadline thích hợp. Nếu operation thực sự còn chạy ở background, ghi riêng trạng thái caller kết thúc và background completion để không nhầm.
- **CANCELLED:** chỉ đánh dấu khi có thông tin huỷ; “thiếu log ENDED” không có nghĩa cancelled.
- **RETRY:** một logical request nên có nhiều `attemptId` với cùng `requestId`, mỗi attempt có received/start/end riêng hoặc dùng attempt-start riêng theo contract.
- **Partial result:** thao tác ghi 1 MB thành công 900 KB rồi lỗi cần trạng thái rõ ràng `PARTIAL_FAILURE` hoặc trường `bytesWritten`/`errorCode`, không chỉ có boolean.

### 9.4. Clock domain qua nhiều JVM

Với một request từ gateway → service A → service B, các đồng hồ monotonic của từng JVM không chia sẻ origin. Chỉ thực hiện phép trừ thời gian trong cùng domain. Để dựng timeline xuyên service, cần wall-clock đã đồng bộ tương đối và distributed trace với span boundaries; vẫn có thể lệch do NTP/scheduling/network. Nếu cần đo network round trip chính xác, dùng send/receive trên cùng process để tạo duration cục bộ.

## 10. Từ dữ liệu đến giả thuyết về độ trễ I/O

| Dấu hiệu | Giải thích khả dĩ | Bước kiểm tra tiếp |
| --- | --- | --- |
| `waitToStart` tăng, `work` ổn định | Queue backlog, worker pool saturation, rate limiter, scheduler/dispatch | Queue depth, pool size, active workers, rejected counts |
| `work` tăng, `waitToStart` ổn định | I/O downstream, file system, contention hoặc CPU trong worker | File/socket events, JFR thread stack, downstream latency |
| `total` tăng nhưng cả hai số thấp | Ranh giới đo không bao trùm phần phát sinh độ trễ, thiếu bước sau ENDED | So sánh ingress/server response time, tracing spans |
| `ERROR`/`TIMEOUT` tăng mà duration không lớn | Fast-fail, validation, circuit breaker hoặc deadline sớm | Error codes, downstream status, retry policy |
| Có RECEIVED nhưng không có STARTED | Rejected, queue backlog, shutdown hoặc missing logs | Dispatcher metrics, queue acceptance, log health |
| Có STARTED nhưng không có ENDED | Hang, process crash hoặc missing telemetry | Thread dump/JFR, in-flight metric, process restarts |
| `work` cao chỉ ở một path | Phụ thuộc I/O hoặc payload khác nhau | Group theo operation, endpoint template, payload size |
| JFR không có event nhưng logs có ENDED | JFR disabled, threshold/sampling, recording sai thời gian | `jfr summary`, event settings, recording window |

Các dòng trên là **giả thuyết**, không phải kết luận duy nhất. Work duration có thể gồm CPU, locks, network và scheduling chứ không nhất thiết thuần I/O. Kết hợp JFR `jdk.FileRead`, `jdk.SocketRead`, `jdk.JavaMonitorEnter`, execution samples, metrics của downstream và traces để kiểm tra nguyên nhân.

### 10.1. Đừng dùng trung bình thay cho tail latency

Đối với sự cố p99, một số request có wait-to-start hàng giây có thể biến mất trong average vài chục mili giây. Nên lưu histograms/phân vị cho **wait-to-start**, **work**, **end-to-end**, phân tách theo operation và outcome. Đừng cộng p99 của hai giai đoạn để suy ra p99 end-to-end: percentile không có tính cộng đơn giản. Tính phân vị trên distribution end-to-end quan sát trực tiếp.

Dùng nhãn metrics có cardinality thấp (`operation`, `result`, service name). Đừng gắn từng `requestId` làm nhãn Prometheus metric — cardinality sẽ bùng nổ; request ID phù hợp hơn trong logs/traces/JFR payload được lấy mẫu.

### 10.2. Giải thích số liệu khi có sampling

Nếu JFR ghi chỉ những event vượt threshold theo **work duration**, không được tính median của mẫu ấy rồi tuyên bố đó là median của mọi request. Mẫu bị chọn lọc. Tương tự, nếu logs được sampling độc lập theo phase, việc “thiếu ENDED” có thể do sampling chứ không phản ánh job in-flight.

Cấu hình thu phải là một phần của báo cáo: event name, threshold, sampling rate, thời gian ghi, JDK version và dữ liệu được lọc. Phân biệt **telemetry gap** với **application failure**.

## 11. Giảm overhead và bảo vệ dữ liệu

Thu telemetry vẫn tiêu thụ CPU, allocation, queue và I/O. Một chiến lược thực tế:

1. Dùng metrics/histograms luôn bật cho count, status và end-to-end duration tổng quan.
2. Ghi structured log ở ranh giới phù hợp, có thể lấy mẫu có chủ đích khi volume cao.
3. Dùng custom JFR event trong recording chẩn đoán hoặc cấu hình được kiểm thử overhead; không bật mọi event/stack vô hạn.
4. Đo số log lines/s, bytes/s, kích thước `.jfr` và chi phí logging sink; không để log synchronous trên hot I/O path trở thành bottleneck mới.
5. Phân biệt **kết quả nghiệp vụ** với việc ghi telemetry thành công. Logging backend lỗi không nên làm nghiệp vụ SUCCESS thành ERROR trừ khi hợp đồng yêu cầu.
6. Tránh PII và secrets. `requestId` không nên có thông tin nhận diện trực tiếp; không ghi raw Authorization header, token, SQL bind values, body nhạy cảm.
7. Áp retention và quyền file JFR: recording có thể chứa tên class, thread, stack, file path và payload custom do bạn ghi.
8. Với log JSON, dùng thư viện encoder escape đúng ký tự đặc biệt/newline; ví dụ stdout trong demo chỉ có ID/trạng thái cố định nên không xử lý arbitrary input.

Nếu log các field `requestId`, `operation` từ user input, phải validate/normalize/escape. Không ghép dữ liệu chưa tin cậy vào log line không có escaping vì có nguy cơ log injection.

## 12. Lỗi thường gặp

**Lỗi 1 — Lấy STARTED lúc enqueue thay vì lúc worker chạy.** Mọi request có vẻ wait-to-start gần 0 dù queue rất dài. Phải đặt STARTED tại ranh giới worker thực bắt đầu.

**Lỗi 2 — Gọi ENDED ngay sau khi nhận được Future.** Bạn mới đo thời gian submit bất đồng bộ, không đo I/O completion. Chuyển ENDED vào completion callback.

**Lỗi 3 — Dùng `Instant.now()` hai lần rồi trừ để ra duration chuẩn.** Wall clock có thể điều chỉnh; đo duration cùng JVM bằng `System.nanoTime()` và dùng Instant/epoch millis để liên kết timeline.

**Lỗi 4 — Trừ `nanoTime` của hai process.** Origin của monotonic clock không bảo đảm tương thích giữa các JVM. Dùng distributed tracing/UTC timestamps cho liên kết cross-service, không trừ ticks.

**Lỗi 5 — Chỉ ghi END khi SUCCESS.** Exception/timeout/cancel khiến request không có kết thúc, tạo thống kê sai. Ghi terminal outcome trong finally/callback một lần.

**Lỗi 6 — Ghi một result cố định mặc dù đã có lỗi.** `result=SUCCESS` phải gắn với việc công việc thực sự đáp ứng hợp đồng, không chỉ vì phương thức đã quay về. Lưu error type/status rõ ràng.

**Lỗi 7 — Ghi timestamp nhưng không có request ID/attempt ID.** Không thể ghép chắc ba phase khi nhiều request chạy cùng thread hoặc liên tiếp. Cần context propagation và khóa tương quan.

**Lỗi 8 — Dùng `event.getDuration()` của JFR làm end-to-end dù begin() ở STARTED.** Event intrinsic duration chỉ bao phần được begin/end. Muốn tổng, dùng field `totalNanos` hoặc đổi định nghĩa event.

**Lỗi 9 — Đặt threshold theo work khiến mất request chậm vì queue.** Request wait 800 ms nhưng work 2 ms có thể bị lọc bởi threshold 50 ms. Xác định boundary của event và mục tiêu sampling.

**Lỗi 10 — Hiểu `REJECTED` như đã được worker xử lý.** Request bị từ chối trước start có kết quả terminal nhưng không có khoảng work hợp lệ. Schema nên cho phép trường không áp dụng.

**Lỗi 11 — Tính `queue + work` từ log của hai attempts khác nhau.** Kiểm tra `requestId + attemptId` và mốc thứ tự trước khi tính; log có thể đến aggregator không theo thứ tự thời gian.

**Lỗi 12 — Dùng requestId làm metric label.** Cardinality bùng nổ; request ID dành cho logs/traces, metrics dùng nhãn phân loại.

**Lỗi 13 — Không xem xét retry/backoff.** Tổng một logical request có thể dài do khoảng chờ retry nằm ngoài work mỗi attempt; đo logical request và attempt riêng.

**Lỗi 14 — Nhầm “không có JFR event” là “không có request”.** Recording có thể chưa start, event disabled, threshold cao hoặc bị ghi thiếu. Đối chiếu logs, metrics, `jfr summary`.

## 13. Bài tự kiểm tra

**Câu 1.** Các mốc monotonic (cùng JVM) là `t_recv=1000 ms`, `t_start=1060 ms`, `t_end=1100 ms`. Tính wait-to-start, work, end-to-end.

*Đáp án:* 60 ms, 40 ms và 100 ms. Tổng 60+40=100 ms.

**Câu 2.** Một request có wait-to-start 800 ms, work 2 ms. Custom JFR event gọi `begin` ở STARTED và có `threshold=50 ms`. Nó có chắc được ghi không?

*Đáp án:* Không. Threshold áp trên intrinsic duration (xấp xỉ work 2 ms), nên có thể bị loại dù end-to-end khoảng 802 ms. Để điều tra queue latency, cần giữ những event này hoặc thay boundary/sampling.

**Câu 3.** Một async method trả `CompletableFuture` sau 1 ms, nhưng operation I/O xong sau 300 ms. Nên lấy ENDED lúc nào?

*Đáp án:* Khi future hoàn thành thật sự theo contract, không phải khi method trả future.

**Câu 4.** Có ba attempt của cùng `requestId`: ERROR, TIMEOUT, SUCCESS. Làm sao tránh ghép sai thời gian?

*Đáp án:* Ghi `attemptNo` hoặc `attemptId` cho từng attempt, đo ranh giới attempt riêng; thêm logical end-to-end span/request outcome cho cả quá trình và backoff.

**Câu 5.** Vì sao log không có ENDED không tự chứng minh deadlock?

*Đáp án:* Có thể bị lỗi log ingestion, sampling, process crash, reject/abort, mất completion callback hoặc chưa vượt deadline. Cần process/thread/queue/in-flight metrics và dữ liệu bổ sung.

**Câu 6.** Từ nhiều request, p99 wait-to-start = 100 ms và p99 work = 300 ms. P99 end-to-end có chắc = 400 ms không?

*Đáp án:* Không. Percentile của tổng không đơn giản bằng tổng percentiles. Cần tính end-to-end duration cho từng request rồi xây distribution riêng.

**Câu 7.** Ghi `ERROR` có bắt buộc phải ghi full exception message không?

*Đáp án:* Không. Nên lưu error type/code chuẩn hóa, stack/traces có kiểm soát và loại bỏ nội dung nhạy cảm. Full message có thể chứa secrets.

## 14. Checklist trước khi xem là đủ bằng chứng

- [ ] Đã định nghĩa rõ RECEIVED, STARTED, ENDED và RESULT theo business boundary.
- [ ] Có `requestId`/`operationId`, `attemptId` và `traceId` khi cần.
- [ ] Đo duration bằng `System.nanoTime()` trong cùng clock domain; timestamp UTC để ghép logs.
- [ ] Có trường `waitToStartNanos`, `workNanos`, `totalNanos` và thống nhất đơn vị.
- [ ] Đã kiểm tra `total = wait + work` và các mốc có thứ tự hợp lệ.
- [ ] Ghi terminal result cả SUCCESS, ERROR, TIMEOUT, CANCELLED, REJECTED khi áp dụng.
- [ ] Với async I/O, ENDED được ghi ở completion callback, không phải lúc submit.
- [ ] Không nhầm wait-to-start với queue thuần túy nếu chưa có enqueue/dequeue markers.
- [ ] Với custom JFR, hiểu rõ `Event.begin/end`, `threshold`, `commit` và nội tại duration.
- [ ] Nếu JFR có 0 event, đã kiểm tra event enable, threshold, recording và workload.
- [ ] Đã đo log/JFR overhead, giới hạn field nhạy cảm, kiểm soát retention.
- [ ] Đã đối chiếu duration và outcome với hệ metrics, traces và JFR JVM events.
- [ ] Không dùng request IDs làm metric labels có cardinality cao.
- [ ] Có cách phân biệt operation in-flight, telemetry bị thiếu và thật sự timeout.

**Ghi nhớ:** Để chẩn đoán I/O latency, một mốc “xong” là không đủ. Ghi **nhận → bắt đầu → kết thúc + kết quả** trên **cùng attempt**; dùng **monotonic time** cho duration, **UTC wall-clock** cho correlation; tách **wait-to-start** khỏi **work**; và bảo đảm event/log terminal được ghi cả khi lỗi. Structured logs thuận tiện cho điều tra online, còn custom JFR event gom timeline và kết quả để đối chiếu với bằng chứng JVM.

## Tài liệu tham khảo

- Oracle JDK 21 — [`Event` API: `begin`, `end`, `commit`, `shouldCommit`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html).
- Oracle JDK 21 — [`jdk.jfr` package, event fields and settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- Oracle JDK 21 — [`@Timestamp` annotation, `MILLISECONDS_SINCE_EPOCH`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Timestamp.html).
- Oracle JDK 21 — [`@Timespan` annotation, `NANOSECONDS`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Timespan.html).
- Oracle JDK 21 — [`Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html) và [`RecordingFile` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- Oracle — [JFR Event Threshold / `shouldCommit`](https://docs.oracle.com/en/java/javase/21/jfapi/event-threshold.html).
- Oracle JDK 21 — [`jfr` command: `summary`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- SLF4J — [MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html): quản lý diagnostic context trên thread.
- Oracle Java 17 — [`System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement, origin không có ý nghĩa UTC.