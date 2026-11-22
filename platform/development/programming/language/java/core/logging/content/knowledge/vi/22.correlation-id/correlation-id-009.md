# Correlation ID và batch trong Java Logging

## 1. Vì sao batch cần Correlation ID?

**Correlation ID** là mã định danh giúp liên kết những log event thuộc **cùng một luồng xử lý có ý nghĩa**, ngay cả khi chúng được phát ra ở nhiều lớp Java, nhiều worker thread, nhiều lần retry hoặc nhiều dịch vụ. Đối với xử lý **batch** (xử lý hàng loạt), correlation ID đặc biệt hữu ích vì một công việc có thể kéo dài nhiều phút hoặc nhiều giờ, chia thành các chunk, thực thi song song và được khởi động lại sau lỗi.

Một batch nhập 10.000 bản ghi có thể có hàng nghìn dòng log:

~~~text
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 event=batch.started
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-001 event=item.started
WARN  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-002 attempt=1 event=item.retry_scheduled
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-002 attempt=2 event=item.succeeded
INFO  correlationId=corr-42 batchId=batch-42 batchRunId=run-1 event=batch.completed
~~~

Các dòng trên là **dữ liệu minh họa**. Correlation ID giúp xem toàn bộ luồng, trong khi `batchId`, `batchRunId`, `itemId` và `attempt` cho biết phạm vi chính xác hơn.

**Điểm cốt lõi:** Correlation ID phục vụ **quan sát và truy vết**; nó **không tự ngăn một item xử lý hai lần, không tự tạo transaction, không bảo đảm exactly-once delivery và không thay thế checkpoint hay khóa idempotency**. Muốn xử lý batch an toàn phải kết hợp định danh, trạng thái bền vững và chính sách retry/commit.

Một mô hình dễ hiểu:

~~~text
Correlation ID: corr-42       Một luồng nghiệp vụ cần truy vết
   |
   +-- Batch ID: batch-42     Tập công việc logic
          |
          +-- Run ID: run-1  Lần chạy đầu: xử lý một phần, có lỗi
          |      +-- item-A attempt=1 -> succeeded
          |      +-- item-B attempt=1 -> failed
          |
          +-- Run ID: run-2  Lần chạy lại/resume
                 +-- item-B attempt=2 -> succeeded
~~~

Trong mô hình **được chọn cho bài học**, correlation ID và batch ID vẫn ổn định qua hai lần thực thi, còn run ID đổi. Đó là một **quy ước thiết kế hợp lệ**, không phải luật bắt buộc của Java hoặc mọi batch framework. Một tổ chức có thể gán correlation ID mới cho mỗi yêu cầu kích hoạt hoặc dùng một ID cha cho toàn workflow; điều quan trọng là định nghĩa rõ và nhất quán.

## 2. Phân biệt các loại ID trong batch

| Field | Trả lời câu hỏi | Phạm vi và vòng đời gợi ý |
| --- | --- | --- |
| `correlationId` | Các log này thuộc cùng chuỗi xử lý/ngữ cảnh điều tra nào? | Giữ ổn định trong phạm vi workflow đã định nghĩa |
| `batchId` | Đây là tập công việc logic nào? | Giữ qua retry/resume của **cùng một batch logic** |
| `batchRunId` | Đây là lần thực thi cụ thể nào của batch? | Mới cho mỗi lần start/restart được xem là execution mới |
| `jobName` | Loại batch/job nào đang chạy? | Giá trị hữu hạn như `nightly-import` |
| `itemId` / `recordId` | Bản ghi/đơn vị công việc nào? | ID bền vững để đối chiếu item |
| `chunkId` / `partitionId` | Nhóm/partition nào đang xử lý? | Phạm vi chunk hoặc partition do hệ thống quản lý |
| `attempt` | Đây là lần thử thứ mấy của đơn vị công việc? | Tăng khi retry theo hợp đồng đã xác định |
| `requestId` | Request HTTP/API nào đã kích hoạt thao tác? | Thường đổi theo request; có thể kết thúc trước khi batch chạy xong |
| `traceId` / `spanId` | Sự kiện nằm trong distributed trace/span nào? | Được tracing system tạo/duy trì |
| `idempotencyKey` | Hệ thống dùng khóa gì để chống thực hiện tác động trùng? | Định nghĩa theo **tác động nghiệp vụ cần chống trùng** |

**Không gộp các trường này thành một chuỗi duy nhất.** Ví dụ `corr-42|batch-42|run-2|item-B|attempt-2` có thể đọc được, nhưng để tìm kiếm có cấu trúc nên tách thành các field rõ nghĩa. Các ID động khác nhau về **cardinality** và vòng đời.

### 2.1. Correlation ID khác batch ID

Correlation ID có thể bao trùm **nhiều batch** được kích hoạt bởi một workflow. Ví dụ một quy trình cuối ngày có batch nhập đơn hàng, batch đối soát và batch gửi báo cáo; cả ba có thể cùng `correlationId` nhưng `batchId` khác nhau.

Ngược lại, cùng một batch có thể được khởi động từ request mới sau vài giờ; tùy hợp đồng, request đó có correlation ID riêng, còn batch ID logic được giữ. Không thể suy ra chúng luôn giống nhau.

### 2.2. Batch ID khác run ID

`batchId=batch-42` nhận diện **công việc logic**; `batchRunId=run-1` và `run-2` chỉ ra hai lần thực thi. Nếu có checkpoint/resume, giữ batchId ổn định giúp xem toàn bộ tiến trình; thay runId giúp khoanh vùng những log chỉ thuộc lần chạy cụ thể.

Trong **Spring Batch**, `JobInstance` và `JobExecution` là các khái niệm framework có ngữ nghĩa riêng; có thể ánh xạ ID nội bộ tương ứng sang field ứng dụng sau khi hiểu chính sách identifying job parameters và restart. **Không mặc định `JobInstance.id == correlationId` hoặc `JobExecution.id == batchRunId`** khi chưa thiết kế mapping.

### 2.3. Item ID khác attempt

Một item bị retry ba lần vẫn là **cùng item**, ví dụ `itemId=item-B` và `attempt=1/2/3`. Việc đổi itemId mỗi lần thử làm khó tổng hợp số item thực tế, và dễ che vấn đề một item thất bại nhiều lần.

Attempt cũng có thể được đếm theo **run** hoặc toàn bộ vòng đời **item**; phải ghi rõ hợp đồng. Bài học dùng attempt tăng **qua các run của cùng item**, nên `item-B attempt=2` trong `run-2` có nghĩa đó là lần thử thứ hai của item-B xét trên toàn batch logic.

### 2.4. Correlation ID khác idempotency key

**Correlation ID** giúp liên kết log; **idempotency key** giúp kiểm soát việc cùng một yêu cầu/tác động có bị áp dụng lặp hay không. Một batch có thể phát lại message sau crash, kể cả khi correlation ID không đổi. Nếu xử lý chuyển tiền, cập nhật số dư hoặc gửi email quan trọng, cần transaction, deduplication store, unique constraint hoặc cơ chế idempotent consumer phù hợp.

**Không dùng correlation ID như khóa idempotency một cách mặc định**: một correlation ID có thể bao trùm nhiều item hợp lệ khác nhau. Khóa idempotency thường cần gắn với tác động cụ thể, ví dụ `batchId + itemId + operation`, sau khi đã chứng minh phạm vi định danh phù hợp.

## 3. Chọn vòng đời Correlation ID cho một batch

Trước khi viết code, trả lời: *"Tập log nào phải tìm thấy chỉ bằng một ID?"*

Một số mô hình:

| Tình huống | Correlation ID nên đại diện cho |
| --- | --- |
| Một HTTP request chạy batch đồng bộ | Request hoặc workflow xử lý request đó |
| API kích hoạt batch bất đồng bộ chạy nhiều giờ | Workflow/job được tạo, không chỉ lifetime của HTTP request |
| Batch được resume sau restart | Có thể giữ correlation ID logic ban đầu; thêm run ID mới |
| Parent batch tạo nhiều child batch | Một correlation ID cha và child batch ID; có thể thêm parentId |
| Một item được đẩy qua nhiều service | Correlation ID xuyên service nếu hợp đồng cho phép; itemId riêng |
| Nhiều batch độc lập chạy đồng thời | ID khác nhau, tránh gán một ID chung cho mọi job cùng tên |
| Một batch lớn chia partition | Correlation ID/batchId chung; partitionId/chunkId phân biệt nhánh |

### 3.1. Sinh ID tại ranh giới đáng tin

Nếu API nhận header `X-Correlation-ID` từ upstream, **đừng coi mọi input là đáng tin**. Có thể dùng ID từ gateway/tracing infrastructure tin cậy; nếu không có hoặc sai policy, server tự tạo. Cần giới hạn độ dài, whitelist ký tự và bảo vệ khỏi CR/LF log injection.

Ví dụ **snippet Java 17**, không phải quy tắc bắt buộc cho mọi sản phẩm:

~~~java
// rawCorrelationId có thể null hoặc đến từ header bên ngoài.
String correlationId =
        rawCorrelationId != null
        && rawCorrelationId.matches("[A-Za-z0-9_-]{1,64}")
        ? rawCorrelationId
        : java.util.UUID.randomUUID().toString();
~~~

Phép kiểm này chặn chuỗi rỗng, chuỗi quá dài và ký tự không mong muốn; nó **không chứng minh nguồn ID đáng tin hoặc toàn cục duy nhất**. Nếu ID có vai trò đặc biệt trong bảo mật/đối soát, cần cơ chế cấp/kiểm chứng riêng.

### 3.2. Không đặt ID bằng dữ liệu nhạy cảm

Không dùng email, số điện thoại, access token, JWT, số thẻ hoặc payload làm correlation ID/batch ID. Các ID thường đi qua nhiều log, collector, dashboard, URL quản trị và hệ thống hỗ trợ. Chọn **opaque IDs** không tiết lộ thông tin nghiệp vụ, được phép lưu theo chính sách dữ liệu.

### 3.3. Ghi mapping ở bước tạo batch

Một API có thể trả về sớm:

~~~json
{
  "status": "accepted",
  "batchId": "batch-42",
  "correlationId": "corr-42"
}
~~~

Đây là response **minh họa**, không phải quy tắc Java. Ở thời điểm tạo batch, lưu ánh xạ `batchId → correlationId` trong record/job metadata bền vững nếu các worker sẽ chạy sau khi request thread đã kết thúc. **Đừng dựa vào ThreadLocal/MDC của request thread để nhớ correlation ID trong nhiều giờ.**

## 4. Luồng xử lý batch: từ trigger đến hoàn thành

Một pipeline thông thường:

~~~text
HTTP / Scheduler / Message Consumer
    |
    |  Tạo/chọn correlationId + batchId
    v
Persist batch metadata / enqueue command
    |
    v
Batch coordinator (batchRunId=run-1)
    |
    +----> Partition P-1 ----> Worker item-A
    |                             |
    |                             +--> item event
    |
    +----> Partition P-2 ----> Worker item-B
                                  |
                                  +--> retry / failure
    |
    v
Batch summary, checkpoint, status
    |
    v
Resume/restart (batchRunId=run-2) khi cần
~~~

Ở mỗi **ranh giới bất đồng bộ**, context cần được đưa vào task/message/metadata một cách rõ ràng. Không được giả định một `ThreadLocal` tồn tại xuyên process, thread, container hoặc sau khi job được lưu vào database.

### 4.1. Các event batch nên có

| Event name (minh họa) | Khi nào phát | Trường nên có |
| --- | --- | --- |
| `batch.accepted` | Yêu cầu tạo batch được chấp nhận | correlationId, batchId, jobName |
| `batch.started` | Một batch execution bắt đầu | correlationId, batchId, batchRunId, attempt/run number |
| `batch.item.started` | Một item bắt đầu xử lý (nếu cần chi tiết) | itemId, attempt, chunkId |
| `batch.item.retry_scheduled` | Item lỗi tạm thời và sẽ thử lại | itemId, attempt, reasonCode, nextRetryAt |
| `batch.item.succeeded` | Item hoàn tất tác động theo hợp đồng | itemId, attempt, durationMs |
| `batch.item.failed` | Một attempt/item thất bại | itemId, attempt, error.type, retryable |
| `batch.checkpoint.saved` | Tiến độ được lưu bền vững | checkpointId, processedCount |
| `batch.finished` | Một run kết thúc với outcome rõ | batchRunId, outcome, succeeded/failed/skipped counts |
| `batch.completed` | **Batch logic** đạt trạng thái thành công cuối cùng | batchId, totalCount, durationMs |

Các tên trên là **quy ước minh họa**, không phải event names do JUL/SLF4J/Spring Batch yêu cầu. Danh mục sự kiện production phải phân biệt event **theo run** và event **theo batch logic**. Ví dụ `batch.finished outcome=partial` của run-1 không được dashboard hiểu là “batch logic đã thành công”.

### 4.2. Không log từng item nếu volume không cho phép

Batch có hàng triệu item; mỗi item phát năm log INFO có thể tạo hàng triệu bản ghi, tiêu tốn CPU, disk/network và chi phí index. Có thể chọn:

- INFO cho mốc batch started/finished và checkpoint quan trọng.
- WARN/ERROR cho thất bại cần hành động; tránh ghi cùng exception đầy đủ ở mọi tầng.
- DEBUG/TRACE hoặc sampling có kiểm soát cho log per-item trong điều tra.
- Metrics/counters cho processed/succeeded/failed/retried và duration.
- Bảng trạng thái bền vững cho kết quả **từng item** nếu nghiệp vụ yêu cầu kiểm toán chính xác.

Correlation ID giúp liên kết những gì đã được ghi, nhưng **không khôi phục những event chưa từng phát hoặc bị queue/collector bỏ**. Tổng số item thực tế nên dựa trên nguồn trạng thái đáng tin và metric được thiết kế phù hợp, không chỉ đếm log line.

## 5. Structured logging schema cho batch

Một record JSON có cấu trúc:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "WARN",
  "service": "import-worker",
  "eventCode": "BATCH-RETRY-001",
  "eventName": "batch.item.retry_scheduled",
  "correlationId": "corr-42",
  "batchId": "batch-42",
  "batchRunId": "run-1",
  "jobName": "nightly-import",
  "partitionId": "part-2",
  "chunkId": "chunk-07",
  "itemId": "item-B",
  "attempt": 1,
  "outcome": "retryable",
  "reasonCode": "DEPENDENCY_TIMEOUT",
  "retryDelayMs": 1000,
  "message": "Retry scheduled after dependency timeout"
}
~~~

Đây là **schema do ứng dụng minh họa**, không phải output mặc định của `Logger.warn(...)`. Trên pipeline thật, JSON layout/encoder phải thực sự xuất những key này thành **field có thể truy vấn**, với kiểu dữ liệu được giữ đúng: `attempt` và `retryDelayMs` là number, không phải string.

### 5.1. Quy ước field và kiểu dữ liệu

| Field | Kiểu gợi ý | Quy tắc |
| --- | --- | --- |
| `timestamp` | timestamp / ISO-8601 UTC string | Timezone rõ |
| `level` | string | Theo backend và mapping thống nhất |
| `eventCode` / `eventName` | string ổn định | Không chứa itemId/requestId động |
| `correlationId` | opaque string | Được cấp ở trusted boundary |
| `batchId` / `batchRunId` | opaque string | Mapping rõ logic-vs-execution |
| `itemId` / `partitionId` / `chunkId` | string | Chỉ khi event có phạm vi tương ứng |
| `attempt` | integer | Tăng đúng theo quy tắc retry đã định nghĩa |
| `outcome` | enum string | Ví dụ started/succeeded/failed/partial |
| `durationMs` | number | Đơn vị millisecond, không đổi thành text có "ms" |
| `error.type` / `error.code` | string | Cho các event lỗi |
| `traceId` / `spanId` | string | Chỉ khi có tracing context thật |
| `schemaVersion` | integer/string | Khi pipeline cần quản trị hợp đồng |

Chọn tên field nhất quán. `batchRunId`, `batch_run_id` và `jobExecutionId` có thể chỉ cùng một khái niệm trong ba hệ thống, nhưng **không được tự coi là cùng field** nếu chưa có mapping. Nơi thu thập cần một contract chung và test.

### 5.2. JSON Lines thay vì các message khó parse

Khi dùng NDJSON, mỗi event được serialize thành một JSON object trên một dòng vật lý; dấu xuống dòng trong exception message/stack trace phải được escape trong JSON string. Sự kiện batch có thể có Throwable với nhiều frame, nhưng toàn bộ exception nên nằm trong một trường đúng định dạng nếu collector mong mỗi dòng là một event.

Không nối dữ liệu người dùng trực tiếp thành `{"itemId":"..."}`: key hoặc value không escape có thể phá JSON và tạo log injection. Sử dụng encoder đáng tin và giới hạn dữ liệu nhạy cảm.

## 6. Correlation ID và MDC: cách đưa ID tới mọi log của worker

**Mapped Diagnostic Context (MDC)** là cơ chế lưu cặp key/value cho log event, thường gắn với thread/context. Trong hệ thống **SLF4J + Logback**, có thể đặt:

~~~java
// Snippet trong scope xử lý batch, có các ID đã được xác thực.
org.slf4j.MDC.put("correlationId", correlationId);
org.slf4j.MDC.put("batchId", batchId);
org.slf4j.MDC.put("batchRunId", batchRunId);
try {
    LOG.info("event=batch.started");
    executeBatch();
} finally {
    org.slf4j.MDC.remove("batchRunId");
    org.slf4j.MDC.remove("batchId");
    org.slf4j.MDC.remove("correlationId");
}
~~~

Snippet cần có SLF4J Logger và hàm `executeBatch` tương ứng; **không phải chương trình chạy độc lập**. Cách remove ba key phù hợp khi scope này **sở hữu** chúng và không cần phục hồi giá trị cũ.

Nếu một logger nằm trong service sâu, nó có thể tự nhận các trường MDC ở cùng thread mà không cần truyền tham số vào từng method. Nhưng nếu layout không in MDC, bạn vẫn không thấy chúng trên console.

### 6.1. PatternLogback cho batch

~~~xml
<!-- Đoạn trong logback.xml, với ConsoleAppender. -->
<appender name="CONSOLE"
          class="ch.qos.logback.core.ConsoleAppender">
    <target>System.out</target>
    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level correlationId=%X{correlationId:-none} batchId=%X{batchId:-none} batchRunId=%X{batchRunId:-none} itemId=%X{itemId:-none} %logger{36} - %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

`%X{key:-none}` là cách Logback PatternLayout hiển thị MDC key với giá trị fallback nếu thiếu. Đoạn này chỉ là **định nghĩa appender**; cần gắn appender vào `<root>` hoặc `<logger>` của cấu hình hoàn chỉnh. Bản production nên cân nhắc JSON encoder để các ID trở thành field rõ ràng thay vì chỉ là text.

### 6.2. Không để MDC sống lâu hơn scope

Một worker thread của thread pool có thể xử lý hàng trăm batch khác nhau trong vòng đời JVM. Nếu có code:

~~~java
// SAI: exception trước dòng remove sẽ giữ context trên thread.
MDC.put("batchId", batchId);
processItem();
MDC.remove("batchId");
~~~

và `processItem()` ném exception, `remove` không chạy. Item từ batch khác trên cùng worker có thể mang **batchId cũ**, khiến điều tra sai và gây rủi ro lẫn dữ liệu.

Dùng `try/finally`. Với nested scope hoặc framework đã đặt MDC trước đó, nên **snapshot và restore toàn map** để không xóa context của caller.

### 6.3. Chụp và phục hồi context với SLF4J

~~~java
// Snippet: yêu cầu import java.util.Map và org.slf4j.MDC.
Map<String, String> previous = MDC.getCopyOfContextMap();

try {
    MDC.clear();
    MDC.put("correlationId", correlationId);
    MDC.put("batchId", batchId);
    MDC.put("batchRunId", batchRunId);
    LOG.info("event=batch.started");
} finally {
    if (previous == null || previous.isEmpty()) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

`MDC.getCopyOfContextMap()` trả **bản sao** map hiện tại, có thể null. `MDC.setContextMap(...)` thay map ở **thread hiện tại**. Đoạn này cố ý tạo ngữ cảnh mới sạch; nếu cần giữ `traceId` được framework cung cấp thì phải thiết kế merge/allowlist thay vì xóa nó không chủ đích.

**Không hiểu nhầm:** `MDC.putCloseable(key, value)` của SLF4J phù hợp với `try-with-resources` và tự remove key, nhưng đóng scope đó **không nhất thiết khôi phục giá trị cũ** của key khi có nested scopes. Snapshot/restore rõ ràng vẫn cần khi có caller context.

## 7. Truyền correlation context qua worker thread và process

### 7.1. Vì sao không tự đi qua ExecutorService?

Thread pool dùng những thread đã tồn tại trước lúc batch bắt đầu. MDC/ThreadLocal trên thread submit không tự xuất hiện ở worker thread. Có khi worker thấy **trống**, có khi (nếu cleanup sai) thấy giá trị **cũ** từ task trước.

Đúng quy trình trong phạm vi một JVM:

1. **Capture** context trên thread submit **ngay trước khi enqueue task**.
2. Truyền snapshot cùng task.
3. Trên worker, **save** context có sẵn của worker.
4. **Install** snapshot của task trên worker trước khi log và chạy logic.
5. Trong `finally`, **restore** context worker đã có trước đó, kể cả khi task lỗi.

Mẫu wrapper SLF4J (snippet Java, yêu cầu các import tương ứng):

~~~java
static Runnable withMdc(Runnable task) {
    java.util.Map<String, String> captured =
            org.slf4j.MDC.getCopyOfContextMap();

    return () -> {
        java.util.Map<String, String> before =
                org.slf4j.MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (before == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(before);
            }
        }
    };
}
~~~

Sử dụng:

~~~java
// Snippet trong scope đã đặt MDC của batch.
executor.submit(withMdc(() -> {
    LOG.info("event=batch.item.started");
    processItem();
}));
~~~

Lưu ý: wrapper phải được tạo lúc **submit**; nếu capture sau khi thread gọi đã dọn MDC, worker sẽ nhận thiếu ID. Đừng dùng một map mutable chia sẻ giữa các task rồi sửa nó trong lúc task đang chạy.

### 7.2. CompletableFuture, scheduler và callback

`CompletableFuture.supplyAsync(...)`, `thenApplyAsync(...)` và callback trong nhiều framework có thể chạy trên thread khác nhau. Truyền context cho stage đầu **không bảo đảm** stage tiếp theo có cùng MDC. Mỗi ranh giới thực thi cần wrapper cho `Runnable`/`Supplier`/`Function` hoặc một facility context-propagation của framework.

Không ép mọi batch thành xử lý đồng bộ chỉ để MDC xuất hiện đúng; việc chờ `Future.get()` ở ví dụ thực hành sau chỉ nhằm có **stdout xác định**, không phải kiến trúc batch throughput cao.

### 7.3. Khi worker ở process/JVM khác

`ThreadLocal`/MDC chỉ tồn tại trong process và ngữ cảnh của adapter. Nếu batch coordinator gửi message qua Kafka/RabbitMQ/SQS hoặc ghi job vào database để worker khác lấy, cần **đưa correlationId/batchId/batchRunId/itemId vào envelope/headers hoặc metadata bền vững** theo hợp đồng.

~~~json
{
  "commandType": "ProcessBatchItem",
  "correlationId": "corr-42",
  "batchId": "batch-42",
  "batchRunId": "run-1",
  "itemId": "item-B",
  "attempt": 1
}
~~~

Đây là envelope minh họa. Worker đọc ID đã được xác thực, cài logging scope, xử lý, ghi trạng thái, rồi cleanup. Nếu message bị phát lại, cần idempotency/dedup riêng; việc giữ correlationId không tự chống xử lý trùng.

### 7.4. Async logging khác async business execution

`AsyncAppender` hoặc async logger có worker phục vụ **ghi log**, không phải worker chạy business logic. Logging backend có thể chụp MDC/context của log event trước khi enqueue để in đúng ID. Điều đó **không truyền MDC sang ExecutorService, Kafka consumer hoặc CompletableFuture** đang chạy nghiệp vụ.

Với async logging, vẫn cần xem queue full, drop, flush và shutdown để tránh tin rằng mọi log bắt buộc đều đã được lưu.

## 8. Ví dụ Java 17 độc lập: batch resume, retry và context isolation

Ví dụ sau dùng **chỉ JDK 17**, không cần Maven và không yêu cầu backend bên ngoài. Vì **JUL không có MDC chuẩn trong JDK**, ta tự tạo một `ThreadLocal<CorrelationContext>` để minh họa quy tắc **capture/install/restore**; `LogRecord` chụp context tại thời điểm phát event. Đây là **demo về correlation context**, không được gọi nhầm là API MDC của JUL.

Kịch bản:

- Batch logic `batch-42` có correlation ID `corr-42`.
- Run `run-1`: `item-A` thành công lần đầu; `item-B` thất bại tạm thời ở attempt 1. Run có outcome `partial`.
- Run `run-2`: tiếp tục đúng `item-B` ở attempt 2, thành công. Run có outcome `succeeded`.
- Hai run được xử lý qua **cùng một single-thread executor**, nhờ đó có thể phát hiện context leakage.
- Cuối cùng phát một event trên worker và một event trên main thread **ngoài scope batch**; cả hai phải có ID `none`.

### 8.1. Mã hoàn chỉnh: BatchCorrelationDemo.java

~~~java
import java.io.IOException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class BatchCorrelationDemo {
    private static final Logger LOG =
            Logger.getLogger(BatchCorrelationDemo.class.getName());

    // Context của demo: không phải MDC API có sẵn trong JUL.
    private static final ThreadLocal<CorrelationContext> CONTEXT =
            new ThreadLocal<>();

    private record CorrelationContext(
            String correlationId,
            String batchId,
            String batchRunId,
            String itemId,
            int attempt) {

        CorrelationContext item(String nextItemId, int nextAttempt) {
            return new CorrelationContext(
                    correlationId, batchId, batchRunId,
                    nextItemId, nextAttempt);
        }
    }

    private BatchCorrelationDemo() {
    }

    private static void restore(CorrelationContext previous) {
        if (previous == null) {
            CONTEXT.remove();
        } else {
            CONTEXT.set(previous);
        }
    }

    private static Runnable withContext(
            CorrelationContext captured, Runnable task) {
        return () -> {
            CorrelationContext workerBefore = CONTEXT.get();
            try {
                CONTEXT.set(captured);
                task.run();
            } finally {
                restore(workerBefore);
            }
        };
    }

    private static final class EventFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] values = record.getParameters();
            CorrelationContext context =
                    (CorrelationContext) values[0];
            String outcome = (String) values[1];

            StringBuilder out = new StringBuilder();
            out.append(record.getLevel().getName());
            out.append(" correlationId=").append(context.correlationId());
            out.append(" batchId=").append(context.batchId());
            out.append(" batchRunId=").append(context.batchRunId());
            out.append(" itemId=").append(context.itemId());
            out.append(" attempt=").append(context.attempt());
            out.append(" event=").append(record.getMessage());
            out.append(" outcome=").append(outcome);

            if (record.getThrown() != null) {
                out.append(" errorType=").append(
                        record.getThrown().getClass().getSimpleName());
            }
            return out.append("\n").toString();
        }
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler stdout =
                new StreamHandler(System.out, new EventFormatter()) {
                    @Override
                    public synchronized void publish(LogRecord record) {
                        super.publish(record);
                        flush();
                    }
                };
        stdout.setLevel(Level.ALL);
        LOG.addHandler(stdout);
    }

    private static void emit(
            Level level, String event, String outcome,
            Throwable error) {
        CorrelationContext captured = CONTEXT.get();
        if (captured == null) {
            captured = new CorrelationContext(
                    "none", "none", "none", "-", 0);
        }

        LogRecord record = new LogRecord(level, event);
        record.setParameters(new Object[] {captured, outcome});
        record.setThrown(error);
        LOG.log(record);
    }

    private static void submitAndAwait(
            ExecutorService executor,
            CorrelationContext context,
            Level level, String event,
            String outcome, Throwable error)
            throws InterruptedException, ExecutionException {

        Runnable task = withContext(context,
                () -> emit(level, event, outcome, error));

        Future<?> completed = executor.submit(task);
        completed.get();
    }

    private static void runBatch(
            ExecutorService executor, String runId,
            boolean firstRun)
            throws InterruptedException, ExecutionException {

        CorrelationContext before = CONTEXT.get();
        try {
            CorrelationContext batch = new CorrelationContext(
                    "corr-42", "batch-42", runId, "-", 0);

            CONTEXT.set(batch);
            emit(Level.INFO, "batch.started", "started", null);

            if (firstRun) {
                submitAndAwait(
                        executor, batch.item("item-A", 1),
                        Level.INFO, "batch.item.succeeded",
                        "succeeded", null);

                submitAndAwait(
                        executor, batch.item("item-B", 1),
                        Level.WARNING, "batch.item.failed",
                        "retryable", new IOException("temporary timeout"));

                emit(Level.WARNING, "batch.finished", "partial", null);
            } else {
                submitAndAwait(
                        executor, batch.item("item-B", 2),
                        Level.INFO, "batch.item.succeeded",
                        "succeeded", null);

                emit(Level.INFO, "batch.finished", "succeeded", null);
            }
        } finally {
            restore(before);
        }
    }

    public static void main(String[] args) throws Exception {
        configureLogger();

        ExecutorService executor =
                Executors.newSingleThreadExecutor();
        try {
            runBatch(executor, "run-1", true);
            runBatch(executor, "run-2", false);

            // Chạy trên cùng worker, nhưng không còn context của batch.
            executor.submit(
                    () -> emit(Level.INFO, "worker.idle", "idle", null))
                    .get();

            // Main thread cũng đã được restore.
            emit(Level.INFO, "main.idle", "idle", null);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### 8.2. Biên dịch và chạy

Lưu tên **BatchCorrelationDemo.java**, rồi chạy:

~~~bash
javac -encoding UTF-8 BatchCorrelationDemo.java
java BatchCorrelationDemo
~~~

**Chín dòng stdout của ứng dụng theo EventFormatter:**

~~~text
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=- attempt=0 event=batch.started outcome=started
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-A attempt=1 event=batch.item.succeeded outcome=succeeded
WARNING correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=item-B attempt=1 event=batch.item.failed outcome=retryable errorType=IOException
WARNING correlationId=corr-42 batchId=batch-42 batchRunId=run-1 itemId=- attempt=0 event=batch.finished outcome=partial
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-2 itemId=- attempt=0 event=batch.started outcome=started
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-2 itemId=item-B attempt=2 event=batch.item.succeeded outcome=succeeded
INFO correlationId=corr-42 batchId=batch-42 batchRunId=run-2 itemId=- attempt=0 event=batch.finished outcome=succeeded
INFO correlationId=none batchId=none batchRunId=none itemId=- attempt=0 event=worker.idle outcome=idle
INFO correlationId=none batchId=none batchRunId=none itemId=- attempt=0 event=main.idle outcome=idle
~~~

**Tại sao có thể dự đoán output?**

1. Chỉ một worker thread được cấp bởi `newSingleThreadExecutor()`, và mỗi `Future.get()` chờ task trước hoàn thành, nên các item event có thứ tự đúng theo mã Java.
2. Batch `run-1` và `run-2` dùng cùng `correlationId`/`batchId` nhưng run ID khác; `item-B` giữ itemId khi retry và tăng attempt từ 1 lên 2.
3. `withContext(...)` chụp context đã được xây từ thread submit, cài lên worker trước khi gọi `emit` và **restore workerBefore ở finally**.
4. `emit(...)` chụp **CorrelationContext bất biến** vào `LogRecord` trước khi backend format; formatter **không đọc ThreadLocal** lúc format. Đây là lựa chọn an toàn về mặt ví dụ nếu cách ghi log sau này chuyển sang backend có worker riêng.
5. `record.setThrown(...)` giữ đối tượng `IOException` cho event failed; formatter minh họa chỉ in tên `errorType` để stdout xác định, **không in full stack trace**. Logging production cần layout thể hiện nguyên nhân/cause khi điều tra.
6. `runBatch(...)` khôi phục context main thread trong `finally`. Hai dòng cuối chứng minh cả main và worker không còn ID của batch khi ngoài scope.

**Lưu ý nghiệp vụ:** demo chỉ **phát event mô phỏng**, không thực hiện I/O nghiệp vụ, transaction, checkpoint hoặc idempotency; vì thế `batch.finished outcome=succeeded` ở run-2 là kết quả của kịch bản học tập, không phải bằng chứng một batch production thực sự đã commit đúng mọi item.

**Lưu ý concurrency:** `Future.get()` chỉ tạo thứ tự xác định để học. Trong batch xử lý song song thật, thứ tự log giữa các worker **không được bảo đảm**, và không nên xây logic nghiệp vụ dựa trên việc log xuất theo thứ tự tăng của itemId. Dùng các ID/sequence/counters đúng phạm vi khi cần tái dựng tiến trình.

### 8.3. Những thử nghiệm quan trọng

1. Đổi `run-2` thành `run-3`: chỉ `batchRunId` của run sau đổi, `correlationId` và `batchId` giữ nguyên.
2. Sửa `batch.item.failed` thành `batch.item.retry_scheduled` và thử thêm `nextRetryAt` vào structured event: điều này làm rõ **đã quyết định retry**, không chỉ phát hiện lỗi.
3. Bỏ `restore(workerBefore)` trong `withContext(...)` **chỉ trên bản học tập**: event `worker.idle` có thể mang `item-B`/`run-2` cũ, chứng minh rò context trong thread pool.
4. Bỏ `CONTEXT.set(captured)`: worker không còn nhận đúng ID của batch; item log có thể thiếu ID hoặc mang context cũ.
5. Gửi item bằng hai worker và không chờ từng task: thứ tự log có thể thay đổi nhưng mỗi event vẫn phải có đúng correlationId/batchId/itemId.
6. Cho task ném exception thật trước khi hoàn thành: thử xác minh `finally` vẫn restore context; xử lý `ExecutionException` ở coordinator thay vì coi nó là batch success.

## 9. Khi retry, restart và resume: nên giữ ID nào?

### 9.1. Retry trong cùng một run

Ví dụ:

~~~text
correlationId=corr-42 batchId=batch-42 runId=run-1 itemId=item-B attempt=1 outcome=retryable
correlationId=corr-42 batchId=batch-42 runId=run-1 itemId=item-B attempt=2 outcome=succeeded
~~~

Nếu đây là **cùng logical item** và retry trong cùng execution, giữ correlationId/batchId/runId/itemId, tăng attempt. Có thể ghi thêm `reasonCode`, `retryDelayMs`, `retryPolicy`, `error.type` để điều tra.

### 9.2. Restart/resume sang run khác

Ví dụ:

~~~text
correlationId=corr-42 batchId=batch-42 runId=run-1 itemId=item-B attempt=1 outcome=failed
correlationId=corr-42 batchId=batch-42 runId=run-2 itemId=item-B attempt=2 outcome=succeeded
~~~

Trong quy ước bài này, retry sau restart tăng attempt toàn vòng đời item. Một hệ thống khác có thể reset attempt per-run và dùng thêm `overallAttempt` hoặc `retryCount`. **Không đổi nghĩa của field âm thầm theo nhánh code**.

### 9.3. Replay message do at-least-once delivery

Kafka/RabbitMQ hoặc một queue có thể chuyển lại cùng message nếu consumer crash trước khi ack. Message được phát lại có thể mang cùng correlationId/batchId/itemId, nhưng **không đủ để kết luận đã xử lý đúng một lần**.

Thiết kế cần:

- ID/khóa nghiệp vụ bền vững cho tác động cần dedup.
- Kiểm tra trạng thái commit/idempotency trước khi áp dụng lại tác động.
- Chính sách ack/transaction/outbox phù hợp với hệ thống.
- Log `redelivered`, `duplicateDetected` hoặc `skippedAsAlreadyProcessed` khi có ý nghĩa.
- Counters phân biệt **số attempt** với **số item duy nhất** và **số commit thành công**.

Ví dụ một item được retry hai lần: hệ thống có thể có ba attempt logs nhưng chỉ **một item thành công**. Dashboard không được đếm ba event attempt như ba giao dịch đã xử lý.

### 9.4. Batch bị hủy hoặc quá hạn

Nếu run bị cancel, timeout hoặc dead-lettered, cần log kết quả chính xác: `cancelled`, `timed_out` hoặc `dead_lettered`, không tự gộp mọi thứ thành `failed` nếu quy trình điều tra/alert cần phân biệt. Với quy định ghi log bắt buộc, lưu trạng thái bền vững trước hoặc phối hợp với event phát ra để giảm sự không nhất quán khi crash.

## 10. Chia chunk, partition và fan-out/fan-in

### 10.1. Fan-out giữ ID cha, thêm ID nhánh

Một batch được chia thành ba partition:

~~~text
correlationId=corr-42 batchId=batch-42 runId=run-1 partitionId=P-0
correlationId=corr-42 batchId=batch-42 runId=run-1 partitionId=P-1
correlationId=corr-42 batchId=batch-42 runId=run-1 partitionId=P-2
~~~

Các worker có cùng ID liên kết nhưng partitionId khác. Khi nhiều item xử lý đồng thời, thêm `itemId` và `attempt` giúp không nhầm failure của item này với item khác.

Nếu một partition phải chạy lại, tùy thiết kế có thể giữ partitionId và tăng `partitionAttempt`, hoặc tạo ID execution riêng cho partition. Nên tách **partition logic** với **lần thực thi của partition**, tương tự batchId và batchRunId.

### 10.2. Fan-in tổng hợp kết quả

Khi các worker hoàn thành, coordinator có thể phát một event summary:

~~~json
{
  "eventName": "batch.finished",
  "correlationId": "corr-42",
  "batchId": "batch-42",
  "batchRunId": "run-1",
  "outcome": "partial",
  "itemsPlanned": 10000,
  "itemsSucceeded": 9700,
  "itemsFailed": 250,
  "itemsSkipped": 50,
  "durationMs": 124000
}
~~~

**Tính đúng của counters là trách nhiệm batch engine/trạng thái nghiệp vụ**, không đến từ việc chỉ đếm text lines. Nếu một item có nhiều attempt, count `itemsFailed` phải dùng đúng định nghĩa: số item còn thất bại khi run kết thúc, hay số attempt lỗi? Nên có `attemptsFailed` riêng khi cần.

### 10.3. Checkpoint và tiến độ

Với batch lâu, log checkpoint nên có:

- correlationId/batchId/batchRunId.
- checkpointId hoặc offset đã commit.
- processed/succeeded/failed/skipped counters tại thời điểm checkpoint.
- thời lượng và throughput được đo nhất quán.
- cursor/range **an toàn để log**, không chứa dữ liệu cá nhân hoặc secret.

Không coi việc in `checkpoint.saved` là tương đương checkpoint đã được commit vào storage. Event log nên được phát **sau** khi bước lưu checkpoint thành công hoặc theo transaction/event design có thể kiểm chứng; nếu log trước rồi crash, nó có thể phản ánh một trạng thái chưa bền vững.

## 11. Correlation ID với Spring Batch, scheduler và message consumer

### 11.1. Spring Batch

Spring Batch cung cấp các khái niệm như `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và job parameters. Có thể thiết kế:

- `batchId` ↔ ID logic nghiệp vụ hoặc một job instance key bền vững.
- `batchRunId` ↔ ID của một job execution.
- `stepId`/`stepName` ↔ step execution/step name khi cần.
- `correlationId` ↔ workflow ID do boundary của ứng dụng cấp.

**Đây là mapping gợi ý, không phải tên field mặc định của Spring Batch.** Cần xem cấu hình identifying job parameters, restart policy và cách framework ghi execution metadata. Đừng cho rằng mọi `JobExecution` là một batch logic mới.

`ExecutionContext`/job metadata phù hợp hơn ThreadLocal để **lưu định danh bền vững phục vụ restart**. MDC chỉ để tạo log có ngữ cảnh trên thread đang thực thi.

### 11.2. Scheduler

Một tác vụ chạy theo lịch có thể có `jobName=nightly-reconcile` và `scheduleTime`, nhưng mỗi lần kích hoạt cần một `batchRunId` khác nhau. Nếu một lịch chạy chồng lấn hai execution, chỉ dùng jobName là không đủ để phân biệt.

Mốc `scheduledAt`, `startedAt` và `finishedAt` khác nhau; nếu muốn tính queue delay hoặc duration, ghi rõ mốc và đơn vị, không lấy timestamp của log làm proxy cho mọi giai đoạn.

### 11.3. Message consumer

Khi worker nhận message, cần:

1. Đọc các ID từ message envelope/headers theo schema.
2. Kiểm tra ID hợp lệ và quyết định nguồn đáng tin.
3. Lưu snapshot context hiện tại của consumer thread.
4. Cài MDC/context của message, xử lý, log outcome/Throwable.
5. Cleanup/restore ở `finally` trước khi nhận message khác trên cùng thread.
6. Chuyển ID cần thiết tới downstream messages theo hợp đồng, không copy toàn bộ headers không tin cậy.

Nếu một message không có correlationId, policy có thể tạo ID mới, đánh dấu thiếu upstream ID và lưu parent mapping nếu còn cách liên kết. Không âm thầm dùng mã của một message cũ còn trong MDC.

### 11.4. Dịch vụ con và tracing

Nếu một batch gọi HTTP/gRPC downstream, có thể truyền correlation ID qua header đáng tin cậy hoặc field của request theo hợp đồng. Đồng thời, hệ thống tracing truyền **trace context** bằng cơ chế riêng. **Không chỉ copy `correlationId` vào `traceId`**: trace ID phải tuân theo tracing system và ngữ nghĩa trace/span thật.

Một batch chạy lâu có thể gồm nhiều traces, và một trace có thể bao gồm nhiều spans trong cùng batch. `correlationId` có thể là khóa điều tra dài hạn nối các traces với batch logic, trong khi traceId giúp xem một đường gọi cụ thể.

## 12. Tránh nhầm log level, event code và trạng thái batch

**Correlation ID không nói event nghiêm trọng hay thành công.** Cần kết hợp:

| Field | Nhiệm vụ |
| --- | --- |
| `correlationId` | Liên kết các event cùng workflow |
| `eventCode`/`eventName` | Mô tả loại sự kiện đã đăng ký |
| `level` | Độ nghiêm trọng của event |
| `outcome` | Kết quả của item/run/batch tại thời điểm ghi |
| `batchStatus` | Trạng thái bền vững theo business engine (nếu có) |
| `error.type`/`error.code` | Phân loại failure để điều tra |

Ví dụ một attempt timeout có thể là WARN và `outcome=retryable`; batch cuối cùng vẫn `succeeded`. Nếu dùng chung một `eventCode=BATCH_FAILED` cho mọi timeout retry, dashboard có thể hiểu nhầm batch thất bại nhiều lần.

**Đừng chỉ đếm số ERROR theo correlationId** để kết luận số item thất bại: có thể một lỗi được ghi ở service, worker và coordinator, hoặc một item lỗi nhiều attempt. Cần quy định rõ event duy nhất cho kết quả cuối, event cho attempt và metric tương ứng.

## 13. Truy vấn và dashboard theo correlationId

Giả sử hệ thống đã ingest JSON có các field độc lập. Các câu truy vấn sau là **pseudocode**, không phải cú pháp chung cho Elasticsearch, Loki, Splunk hay SQL:

~~~text
-- Xem mọi log thuộc workflow:
FILTER correlationId = "corr-42"
SORT timestamp ASC

-- Xem riêng lần chạy gặp sự cố:
FILTER batchId = "batch-42"
  AND batchRunId = "run-1"
SORT timestamp ASC

-- Xem item bị retry qua nhiều run:
FILTER batchId = "batch-42"
  AND itemId = "item-B"
SORT timestamp ASC

-- Đếm số lần item được thử (không phải số item duy nhất):
FILTER eventName IN ("batch.item.started", "batch.item.failed")
GROUP BY batchId, itemId
~~~

Những câu truy vấn trên giả định field names đã được chuẩn hóa, dữ liệu nằm trong phạm vi retention và collector không bỏ event. Mỗi hệ thống query có cú pháp/timezone và chế độ index khác nhau.

### 13.1. Câu hỏi điều tra batch tốt

- Batch logic nào có outcome `partial` rồi được resume?
- Run nào chứa failure đầu tiên? Partition/chunk/item nào?
- Một item bị retry bao nhiêu lần? Vì nguyên nhân kỹ thuật gì?
- Tổng số item **duy nhất** thành công đã được commit là bao nhiêu?
- Độ trễ giữa enqueue và start batch là bao lâu?
- Correlation ID này xuất hiện ở những service/queue nào?
- Có dấu hiệu xử lý trùng/idempotent skip không?
- Có log thiếu correlationId vì boundary không áp dụng context không?

### 13.2. Cardinality và metrics

`correlationId`, `batchId`, `batchRunId` và `itemId` có thể có rất nhiều giá trị. Chúng hữu ích làm **search fields của logs**, nhưng không nên mặc định đưa tất cả làm **labels của metrics time series**. Một metric như:

~~~text
batch_items_processed_total{jobName="nightly-import",outcome="succeeded"}
~~~

có tập label hữu hạn hơn so với metric gắn mỗi `batchId`/`itemId`. Nên dùng metric với label kiểm soát cardinality, còn correlation ID để điều tra trong logs/traces.

### 13.3. Dùng dữ liệu nào làm nguồn sự thật?

- **Logs**: giải thích diễn biến, các lỗi và context.
- **Metrics**: tổng hợp throughput, latency, retry/failure rates.
- **Tracing**: quan hệ lời gọi/span khi có instrumentation.
- **Batch metadata/database**: trạng thái bền vững và kết quả commit/item nếu nghiệp vụ yêu cầu chính xác.

Số liệu batch chính xác thường cần đối chiếu với metadata/DB, đặc biệt khi có retry, crash, duplicate delivery, log sampling hoặc queue bị drop.

## 14. Logging failure và bảo toàn nguyên nhân

Một item có thể gặp `IOException` hoặc lỗi từ dependency. Khi cần chẩn đoán, hãy ghi `Throwable` đầy đủ **tại ranh giới xử lý lỗi có trách nhiệm**, đồng thời kèm correlationId/batchId/runId/itemId và attempt.

Với SLF4J:

~~~java
// Snippet trong catch; MDC đã được cài đúng trên worker.
catch (java.io.IOException e) {
    LOG.warn("event=batch.item.retry_scheduled reason=dependency-timeout", e);
    scheduleRetry();
}
~~~

Snippet chỉ minh họa trong method có `scheduleRetry` và logging backend, không phải Java source độc lập. Với một batch có hàng nghìn retry, có thể chọn log ngắn/metric cho retry dự kiến và full trace khi failure cuối hoặc mẫu đại diện, **nhưng không làm mất thông tin cần điều tra và không bỏ các event audit bắt buộc**.

Khi wrap exception giữa các tầng, giữ cause:

~~~java
// Snippet trong catch IOException.
throw new IllegalStateException("Cannot process batch item", e);
~~~

Không chỉ lấy `e.getMessage()` rồi tạo exception mới bỏ cause. Khi có try-with-resources, suppressed exceptions cũng có thể quan trọng; chọn formatter/JSON encoder thể hiện cause/suppressed theo policy.

Một bản ghi ERROR có correlation ID sai còn gây hại hơn một bản ghi thiếu ID: nó có thể đẩy nhóm vận hành sang **sự cố hoặc khách hàng khác**. Do đó test isolation quan trọng ngang với test truyền context.

## 15. Bảo mật và tính toàn vẹn của ID

### 15.1. Correlation ID không phải token xác thực

Biết `correlationId=corr-42` không cho phép chứng minh người gọi sở hữu batch hay có quyền đọc dữ liệu. API tra cứu trạng thái batch vẫn phải kiểm tra **authentication/authorization** theo tài khoản, tenant và quyền nghiệp vụ.

Nếu public response trả correlationId để hỗ trợ, đừng biến ID đó thành “mật khẩu truy cập log”. Không dùng nó thay permission check.

### 15.2. Không rò dữ liệu qua field ID

- Đặt ID opaque, không chứa email/số điện thoại/token.
- Hạn chế độ dài, ký tự điều khiển và input spoofing từ headers.
- Không log toàn bộ queue envelope nếu nó chứa secret.
- Phân quyền truy cập log, file archive, collector và runbook.
- Định nghĩa retention phù hợp cho metadata liên kết batch và dữ liệu cá nhân.
- Dùng JSON encoder có escaping đúng với chuỗi không tin cậy; **escaping không xóa PII**.
- Nếu có tenant ID, kiểm tra việc định tuyến và tìm kiếm không cho phép xem chéo tenant.

### 15.3. Context leak là rủi ro về độ đúng và quyền riêng tư

Nếu worker thread còn `tenantId` hoặc `batchId` từ task trước, log của task sau có thể gắn nhầm tenant/batch. Đây không chỉ là vấn đề khó debug mà còn có thể làm sai pipeline cảnh báo, hệ thống điều tra hoặc đường phân quyền của collector. Cần `try/finally`, snapshot/restore và kiểm thử thread reuse.

## 16. Các lỗi phổ biến với Correlation ID và batch

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng một `jobName` làm correlation ID cho mọi lần chạy | Không phân biệt nhiều run đồng thời | ID riêng cho workflow/batch/run |
| Tạo correlation ID mới cho mỗi item mà không giữ parent ID | Khó xem toàn bộ batch | Giữ correlationId/batchId, thêm itemId |
| Dùng cùng ID cho batch logic và run mà không định nghĩa | Không tách được restart/resume | Hai field có vòng đời rõ |
| Đổi itemId mỗi lần retry | Đếm nhầm item duy nhất | Giữ itemId, tăng attempt |
| Đếm attempt failure như batch failure cuối | Dashboard/phân tích sai | Tách event per-attempt, per-run, per-batch |
| Dùng correlationId làm idempotency key tùy tiện | Có thể chặn nhầm nhiều item hợp lệ | Khóa idempotency theo tác động cụ thể |
| Chỉ giữ ID trong MDC, không persist vào metadata | Mất liên kết sau restart/process handoff | Lưu và truyền ID bền vững |
| Quên context propagation vào executor | Worker không có ID | Capture tại submit, install tại execute |
| Quên restore MDC trên worker | Task sau mang ID cũ | `finally` restore snapshot |
| Dùng `MDC.clear()` sâu trong service | Mất traceId/key do caller quản lý | Scope/ownership rõ và restore |
| Tin AsyncAppender truyền MDC cho business executor | Worker nghiệp vụ vẫn thiếu ID | Phân biệt async logging và async task |
| Ghi request header raw làm ID | CRLF log injection, input giả mạo, quá dài | Trusted boundary + validation |
| Nhúng token/email vào correlationId | Rò thông tin qua nhiều hệ thống | Dùng opaque ID được phê duyệt |
| Biến requestId thành metric label | Bùng nổ time series | Labels hữu hạn, ID để tìm logs |
| Dùng một batchId làm tên file per item | Quá nhiều file hoặc định tuyến sai | File chung/structured logging theo field |
| Không ghi completion summary | Khó phân biệt partial/cancelled/succeeded | Event kết quả có counters và outcome |
| Ghi completion trước khi commit checkpoint | Log báo hoàn tất sai | Phối hợp event với trạng thái bền vững |
| Tưởng có correlationId là đủ để trace | Không biết lời gọi/span cụ thể | Thêm tracing thật khi cần |
| Log Throwable ở mọi tầng | Trùng sự cố và tăng dung lượng | Chọn ranh giới log có trách nhiệm |
| Không test item chạy lại qua nhiều run | Sai attempt, run ID hoặc liên kết | Test retry/restart/resume có trạng thái |

## 17. Checklist triển khai vào batch production

1. **Định nghĩa phạm vi:** correlation ID liên kết một HTTP trigger, một workflow hay một batch logic qua nhiều run?
2. **Quy ước các ID:** batchId, batchRunId, itemId, chunkId/partitionId, attempt và correlationId khác nhau thế nào?
3. **Nguồn ID đáng tin:** kiểm tra header/input, tạo ID khi thiếu, không dùng giá trị chứa secret.
4. **Persist:** lưu correlationId/batchId với job metadata/message để restart vẫn tìm được.
5. **Schema:** event fields có type và tên thống nhất trong JSON/collector.
6. **Boundary:** cài logging context cho coordinator và từng worker/task/message.
7. **Propagation:** capture context trước submit; truyền sang executor, callbacks và process khác đúng hợp đồng.
8. **Cleanup:** restore ở `finally`, test thread pool tái sử dụng.
9. **Error handling:** giữ Throwable/cause ở sự kiện cần điều tra; không double-log mỗi failure.
10. **Retry semantics:** cùng item giữ ID, attempt tăng theo contract, không đếm trùng.
11. **Idempotency:** thiết kế khóa và trạng thái bền vững riêng cho tác động nghiệp vụ.
12. **Checkpoint:** log outcome đúng sau khi có trạng thái commit được xác nhận.
13. **Metrics:** counters per-item/per-run/per-batch có định nghĩa rõ, labels kiểm soát cardinality.
14. **Security:** ID không cho phép truy cập trái phép; log và metadata có quyền/retention.
15. **Operational tests:** concurrency, restart, cancel, duplicate delivery, async exception, collector drop.
16. **Monitoring:** event thiếu ID, lệch ID, stalled batch, retry spikes, duration, queue lag và disk/ingest pressure.

## 18. Bài tập thực hành

1. **Phân biệt:** một batch `B-42` chạy hai lần `R-1` và `R-2`. Những trường nào giữ nguyên, những trường nào thay đổi trong quy ước của bài?
2. **Java 17:** tạo `BatchCorrelationDemo.java`, chạy `javac`/`java`, đối chiếu chín dòng stdout. Vì sao `worker.idle` và `main.idle` có `correlationId=none`?
3. **Retry:** item-B thất bại ở run-1 và thành công ở run-2. Vì sao `itemId` không đổi nhưng `attempt` từ 1 thành 2?
4. **Context leak:** bỏ `restore(workerBefore)` trong bản học tập. Dự đoán log worker idle sẽ sai thế nào và nêu tác hại khi các job khác dùng chung thread pool.
5. **SLF4J MDC:** viết wrapper `withMdc(Runnable)` capture tại submit và restore tại worker; so sánh với việc chỉ `MDC.put` ở coordinator.
6. **Distributed worker:** coordinator tạo message cho Kafka consumer ở JVM khác. Những ID nào nên nằm trong envelope để consumer có thể phát log và resume đúng?
7. **Idempotency:** hai messages giống nhau của một item được giao lại. Vì sao cùng correlationId không ngăn ghi dữ liệu trùng? Đề xuất khóa và cơ chế commit/dedup.
8. **Structured schema:** viết một NDJSON event `batch.item.retry_scheduled` có attempt là number, reasonCode và retryDelayMs, đảm bảo không chứa token hoặc raw payload.
9. **Fan-out:** batch có ba partition và 100 item. Phân biệt batchId, partitionId, itemId, attempt, và cách tổng hợp summary mà không đếm một item hai lần.
10. **Spring Batch:** giải thích khác nhau giữa JobInstance và JobExecution, rồi đề xuất mapping tới batchId/batchRunId (không đồng nhất mặc định).
11. **Metrics:** thiết kế metric processed/succeeded/failed/retried và lý do không đặt itemId/correlationId làm labels mặc định.
12. **An toàn:** một client gửi correlation header chứa CRLF và email. Viết policy xử lý rồi giải thích vì sao không xem ID là quyền truy cập.
13. **Monitoring:** tạo kịch bản một batch `partial` rồi `succeeded` sau restart. Viết truy vấn giả để xem tất cả log theo correlationId và một truy vấn khác để chỉ xem run-1.
14. **Kết quả cuối:** thiết kế event `batch.completed` có counters từ trạng thái bền vững; nó khác gì với `batch.finished outcome=partial` của một run?

## 19. Tài liệu tham khảo để tra cứu

- Logback Manual — Mapped Diagnostic Context: https://logback.qos.ch/manual/mdc.html
- SLF4J — MDC API: https://www.slf4j.org/api/org/slf4j/MDC.html
- Java SE 17 — `ExecutorService`, `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Spring Batch — Domain Language of Batch: https://docs.spring.io/spring-batch/reference/domain.html
- OpenTelemetry — Context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

**Ghi nhớ:** **Correlation ID nối các log của một workflow; batchId, runId, itemId và attempt cho biết phần nào của workflow đang được xử lý.** Chọn phạm vi ID một cách rõ ràng, lưu/truyền ID qua mọi ranh giới thread/process, dọn MDC bằng `finally`, và phân biệt kết quả **attempt**, **run** với **batch logic**. Correlation ID là công cụ quan sát, không thay thế idempotency, checkpoint, transaction hay quyền truy cập. Một thiết kế tốt cho phép điều tra lỗi xuyên retry/restart mà vẫn đo đúng số item thành công và không lẫn log giữa các batch đồng thời.