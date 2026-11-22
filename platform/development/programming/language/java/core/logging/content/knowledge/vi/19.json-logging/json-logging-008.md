# Field context trong JSON Logging: gắn ngữ cảnh để hiểu và truy vết sự kiện

Trong **JSON logging**, **field context** là các trường có cấu trúc giúp trả lời **sự kiện xảy ra trong hoàn cảnh nào**: ở service nào, thuộc request/job nào, trace nào, tenant hoặc môi trường nào, và những thuộc tính vận hành nào cần thiết để kết nối các sự kiện liên quan. Nếu chỉ ghi `"Payment failed"`, người trực hệ thống biết có lỗi nhưng chưa biết nó thuộc transaction hay request nào. Khi thêm context có chọn lọc, các log có thể được lọc, liên kết và phân tích theo các khóa ổn định.

Ví dụ một bản ghi JSON:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "ERROR",
  "service": "checkout-service",
  "eventName": "payment.failed",
  "requestId": "req-17",
  "traceId": "0123456789abcdef0123456789abcdef",
  "paymentId": "pay-42",
  "errorCode": "UPSTREAM_TIMEOUT",
  "outcome": "failure"
}
```

`eventName` và `errorCode` cho biết **điều gì xảy ra**; `requestId`, `traceId`, `service` cho biết **sự kiện gắn với ngữ cảnh nào**. Những giá trị này chỉ là ví dụ minh họa, không phải danh sách field bắt buộc của mọi hệ thống.

**Nguyên tắc cốt lõi:** field context phải có **tên, kiểu dữ liệu, nguồn phát sinh và vòng đời rõ ràng**. Không cần đẩy mọi thông tin đang có vào log. Chỉ thêm những field thực sự hỗ trợ vận hành, tuân thủ chính sách dữ liệu và không khiến event bị rối hoặc khó duy trì.

## 1. Phân biệt field context với field mô tả sự kiện

Một logging event thường có nhiều nhóm thuộc tính:

| Nhóm field | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Thông tin event** | Điều gì đã xảy ra? | `eventName`, `outcome`, `errorCode` |
| **Severity và thời điểm** | Khi nào, nghiêm trọng đến đâu? | `timestamp`, `level` |
| **Resource/service context** | Sự kiện đến từ service/instance/môi trường nào? | `service`, `environment`, `instanceId` |
| **Request/operation context** | Thuộc request, job, transaction hoặc thao tác nào? | `requestId`, `jobId`, `correlationId` |
| **Distributed tracing context** | Thuộc trace/span nào xuyên các service? | `traceId`, `spanId` |
| **Đối tượng nghiệp vụ** | Bản ghi/tác vụ nói về đối tượng nào? | `orderId`, `paymentId`, `customerType` |
| **Chẩn đoán và hiệu năng** | Kết quả mất bao lâu, lỗi kỹ thuật nào? | `durationMs`, `exceptionType`, `retryAttempt` |
| **Thông điệp cho người đọc** | Diễn giải ngắn gọn ra sao? | `message` |

**Context không hoàn toàn tách rời event data.** Một `orderId` vừa cho biết đối tượng của event, vừa là khóa liên kết những event trong cùng quy trình. Việc xếp nhóm nhằm giúp thiết kế schema dễ hiểu; hệ thống có thể lưu field ở cấp gốc hoặc dưới object lồng nhau.

So sánh ba cách ghi:

```text
Payment failed
Payment failed requestId=req-17 traceId=0123456789abcdef0123456789abcdef
```

và:

```json
{"eventName":"payment.failed","requestId":"req-17","traceId":"0123456789abcdef0123456789abcdef","errorCode":"UPSTREAM_TIMEOUT"}
```

Bản JSON cuối chứa những **khóa riêng** cho `requestId` và `traceId`, nếu thực sự được encoder tạo thành JSON fields, nên công cụ có thể lọc hoặc phân nhóm mà không cần parse toàn bộ message. **Chỉ đặt chuỗi `requestId=...` bên trong `message` chưa phải field context có cấu trúc.**

## 2. Field context được dùng để làm gì?

### 2.1. Correlation: nối các log của cùng một request

Một request qua nhiều lớp có thể phát log ở controller, service, repository và gọi đến dependency ngoài. Với cùng một `requestId`, ta có thể tìm:

```text
requestId=req-17
  12:00:00.001 API received
  12:00:00.010 inventory reserved
  12:00:00.029 payment call started
  12:00:00.305 payment timed out
  12:00:00.308 API returned failure
```

Dữ liệu trên chỉ minh họa. Log thực tế có thể đến collector không theo thứ tự tuyệt đối: thời gian giữa các máy, buffering, async appender và độ trễ mạng có thể khiến thứ tự nhận khác thứ tự phát. Context giúp **lọc và ghép bằng khóa**, nhưng không thay thế distributed tracing khi cần quan hệ cha–con chính xác.

### 2.2. Tìm nguồn gây lỗi giữa nhiều instance

Khi production có nhiều replica, chỉ đọc message `"Connection timeout"` chưa đủ. Các field như `service`, `environment`, `region`, `instanceId` có thể cho biết lỗi tập trung ở một instance/zone hay lan rộng toàn hệ thống.

### 2.3. Phân tích retry, batch và background job

Không phải mọi công việc đều bắt đầu từ HTTP request. Batch và message consumer có thể gắn `jobId`, `messageId` hoặc `attempt`. Tránh tạo `requestId` giả nếu thực tế không có request; dùng context phản ánh đúng vòng đời của thao tác.

### 2.4. Dashboard, alert và điều tra sự cố

Những field context ổn định giúp các truy vấn có thể làm được:

- Tìm log lỗi của một `traceId` hoặc `requestId` cụ thể.
- So sánh số timeout theo `service` và `environment`.
- Phân biệt retry ở các `attempt` khi một thao tác đã thất bại cuối cùng.
- Liên kết log với metric, trace hoặc mã lỗi vận hành, với điều kiện những hệ thống đó dùng định danh tương thích.

**Không nên mặc định rằng field nào cũng phải được đưa vào nhãn metric**. Những giá trị cardinality cao như requestId/traceId phù hợp để tra cứu log hoặc trace nhưng thường không phù hợp làm label cho mọi time-series metric vì có thể tạo rất nhiều chuỗi dữ liệu.

## 3. Các loại context và vòng đời của chúng

### 3.1. Context cấp resource hoặc service

Ví dụ:

```json
{"service":"checkout-service","environment":"production","region":"ap-southeast-1","instanceId":"checkout-7"}
```

Những field này thường **ổn định trong vòng đời của một tiến trình hoặc một lần triển khai**, không phải dữ liệu của từng request. Có thể được đưa vào log bởi cấu hình backend/encoder hoặc được collector bổ sung từ metadata hạ tầng.

**Không hardcode `environment=production` trong từng method nghiệp vụ.** Resource attributes nên được cấu hình tập trung và xác nhận rằng giá trị của collector và giá trị app không xung đột.

### 3.2. Context cấp request

Ví dụ:

```json
{"requestId":"req-17","route":"/checkout","httpMethod":"POST"}
```

Những field này thường có từ khi request vào ứng dụng đến khi trả response, có thể được đặt bằng middleware/filter/interceptor rồi xóa khi kết thúc request. Với `route`, nên ưu tiên **route template** như `/orders/{id}` nếu được hạ tầng hỗ trợ, tránh dùng đường dẫn chứa dữ liệu cá nhân hay ID động làm giá trị phân nhóm quá lớn.

### 3.3. Context cấp distributed trace

Ví dụ:

```json
{"traceId":"0123456789abcdef0123456789abcdef","spanId":"0123456789abcdef"}
```

Trong hệ tracing kiểu W3C/OpenTelemetry, trace ID thường được biểu diễn bằng **32 ký tự hex** và span ID bằng **16 ký tự hex**, với các quy tắc hợp lệ cụ thể. Những chuỗi trong ví dụ có hình dạng minh họa đúng độ dài; ứng dụng thực tế phải lấy từ **tracing context đang hoạt động**, không tự đặt bừa.

**Phân biệt:**

- `requestId`: định danh request do ứng dụng/hạ tầng định nghĩa, có thể khác traceId.
- `traceId`: định danh trace xuyên dịch vụ khi tracing được kích hoạt.
- `spanId`: định danh một span cụ thể trong trace.
- `correlationId`: nhãn tổng quát do tổ chức quy định, đôi khi bao trùm nhiều request.

Không tùy ý sao chép requestId thành traceId; nếu tracing chưa kích hoạt thì nên để context trace thiếu theo schema hoặc sử dụng cơ chế khởi tạo trace chính thức, không dựng một ID giả khiến người điều tra tìm sai trace.

### 3.4. Context cấp event hoặc thao tác

Ví dụ:

```json
{"eventName":"payment.retry","paymentId":"pay-42","attempt":2,"maxAttempts":3}
```

`attempt` chỉ có ý nghĩa trong lần retry hiện tại, không nên để trong context của toàn bộ thread nếu các thao tác khác không liên quan. Nhiều framework hỗ trợ **per-event key–value fields**; đó thường là vị trí tốt hơn cho các thuộc tính chỉ thuộc về một lần ghi.

## 4. Tổ chức context trong JSON: flat hay nested?

Hai cách biểu diễn thường gặp.

### Flat fields

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "checkout-service",
  "requestId": "req-17",
  "traceId": "0123456789abcdef0123456789abcdef",
  "eventName": "checkout.started",
  "orderId": "ord-42"
}
```

Ưu điểm: truy vấn đơn giản khi index/collector mong các field cấp gốc. Nhược điểm: tên có thể xung đột giữa resource metadata, request context và event payload; khó nhóm các thuộc tính có cùng phạm vi.

### Context object lồng nhau

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "eventName": "checkout.started",
  "context": {
    "service": "checkout-service",
    "environment": "demo",
    "requestId": "req-17",
    "traceId": "0123456789abcdef0123456789abcdef"
  },
  "orderId": "ord-42"
}
```

Ưu điểm: ranh giới context rõ ràng, giúp tránh ghi đè các field cấp gốc. Nhược điểm: truy vấn phải biết đường dẫn như `context.requestId` và tùy backend, nested object và dotted field có thể được lập index khác nhau.

**Không coi hai dạng là tự động tương đương.** JSON:

```json
{"context.requestId":"req-17"}
```

có một **khóa chứa dấu chấm**, khác về cấu trúc JSON so với:

```json
{"context":{"requestId":"req-17"}}
```

Một số collector/search engine có thể chuẩn hóa hoặc diễn giải tên có dấu chấm, nhưng hành vi phải được kiểm chứng theo pipeline thực tế.

**Chọn theo schema đã thống nhất**. Nếu công ty dùng OpenTelemetry Semantic Conventions, Elastic Common Schema (ECS) hoặc một log schema chính thức, hãy tuân thủ tên và vị trí field tương ứng; không áp đặt object `context` nếu nó không phù hợp với chuẩn. Bài này dùng nested context để làm rõ khái niệm, không tuyên bố mọi backend phải xuất giống vậy.

## 5. Field context phải có kiểu dữ liệu và ý nghĩa ổn định

| Field minh họa | Type JSON | Ý nghĩa | Phạm vi/vòng đời |
| --- | --- | --- | --- |
| `service` | string | Tên service logic. | Triển khai hoặc ứng dụng |
| `environment` | string | Môi trường chạy. | Triển khai |
| `instanceId` | string | Instance/pod phát sự kiện. | Instance |
| `requestId` | string hoặc absent/null theo schema | Request hiện tại. | Request |
| `traceId` | string hoặc absent/null | Trace hiện tại nếu có. | Trace |
| `spanId` | string hoặc absent/null | Span hiện tại nếu có. | Span |
| `jobId` | string hoặc absent/null | Job đang xử lý. | Background job |
| `orderId` | string | Định danh đơn hàng được phép ghi. | Event/operation |
| `attempt` | number (integer) | Thứ tự lần thử; quy ước bắt đầu từ 1 hay 0 phải rõ. | Retry event |
| `durationMs` | number | Thời lượng tính bằng mili-giây. | Event đo độ trễ |
| `eventName` | string | Mã sự kiện ổn định. | Event |
| `errorCode` | string hoặc null | Mã lỗi có kiểm soát. | Failure event |

Giữ nhất quán cả **tên, type, đơn vị, semantic và enum**. Ví dụ `attempt` không nên lúc là số `2`, lúc là chuỗi `"retry-2"`; `durationMs` phải tính bằng mili-giây, không âm thầm đổi sang microsecond; `outcome` nên dùng một bộ giá trị thống nhất.

**Missing, null và chuỗi rỗng khác nhau:**

- **Không có field**: có thể có nghĩa thuộc tính không áp dụng, ví dụ background job không có requestId.
- **`null`**: field tồn tại nhưng không có giá trị; chỉ dùng khi schema cho phép và consumer hiểu đúng.
- **`""`**: một string rỗng, không tự tương đương null/absent.
- **`"unknown"`**: một giá trị có ý nghĩa đặc biệt; nếu dùng phải được đưa vào contract, không dùng tùy tiện.

Nếu collector yêu cầu một field cho mọi record, có thể xác định chính sách null hoặc absent, nhưng không tự tạo ID giả hoặc lấy ID từ một request trước đó để lấp chỗ trống.

## 6. Gắn context tại đúng ranh giới xử lý

Thiết kế chuẩn cho HTTP request:

```text
HTTP request đến
  |
  +-- Middleware tạo/đọc requestId hợp lệ
  +-- Lấy tracing context từ tracer
  +-- Đặt context cho scope hiện tại
  |
  v
Controller --> Service --> Repository --> Dependency
  |             |            |
  |             |            +--> log cùng requestId/traceId
  |             +--> log cùng requestId/traceId
  +--> log kết quả cuối
  |
  v
Finally / scope close --> xóa/khôi phục context
```

Nguyên tắc quan trọng:

1. **Một nguồn sự thật:** middleware hoặc tracing instrumentation định nghĩa requestId/traceId. Các lớp bên dưới đọc từ context hoặc nhận tham số chứ không tự tái tạo ID.
2. **Chỉ truyền giá trị tin cậy:** nếu lấy correlation ID từ header bên ngoài, cần validation, giới hạn độ dài, chống ký tự điều khiển và chính sách khi header bị giả mạo.
3. **Scope rõ ràng:** đặt context khi bắt đầu request hoặc job, xóa/khôi phục khi xử lý kết thúc.
4. **Không tràn sang request khác:** pooled worker thread có thể được tái sử dụng, nên thiếu cleanup làm rò context từ request trước.
5. **Không làm mờ dữ liệu nghiệp vụ:** context như requestId không thay cho event-specific orderId/outcome/errorCode.

Đối với hệ thống có nhiều API, middleware là nơi thích hợp để thống nhất field name. Không nên sao chép lệnh đặt `requestId` thủ công tại mọi service method.

## 7. MDC trong SLF4J: context theo luồng thực thi

Với SLF4J, **Mapped Diagnostic Context (MDC)** thường được dùng để gắn các string key–value vào scope xử lý. Ví dụ **mã minh họa** bên trong một method của ứng dụng dùng SLF4J + backend hỗ trợ MDC:

```java
import org.slf4j.MDC;

// Giả sử LOG, requestId và traceId đã tồn tại.
MDC.put("requestId", requestId);
MDC.put("traceId", traceId);
try {
    LOG.info("event=checkout.started");
    processCheckout();
} finally {
    MDC.remove("traceId");
    MDC.remove("requestId");
}
```

Đoạn này **không phải class chạy độc lập**: trong source thực tế, `import` nằm đầu file, `processCheckout()` là method ứng dụng, và các biến phải được khai báo. Giả sử `requestId` và `traceId` đã được validation và có giá trị phù hợp.

MDC không tự tạo JSON. Nó chỉ giúp backend nhận thông tin context; **encoder/layout phải được cấu hình để xuất field**. Với text pattern Logback, ví dụ `%X{requestId}` hoặc `%X{traceId}` có thể in giá trị vào dòng text. Muốn JSON field riêng, cần structured encoder và mapping tương ứng.

### Scope an toàn hơn: khôi phục giá trị cũ khi lồng nhau

Nếu tầng bên trong ghi đè một key đã tồn tại, chỉ gọi `remove()` có thể làm mất context của tầng ngoài. Khi có nested scope, nên **lưu và khôi phục** context trước đó. Ví dụ SLF4J có `MDC.getCopyOfContextMap()` và `MDC.setContextMap(...)`; một helper scope thích hợp có thể giữ bản sao rồi restore trong `finally`.

Đối với một key, nhiều phiên bản SLF4J có `MDC.putCloseable(key, value)` trả về đối tượng đóng được để xóa key; tuy nhiên muốn khôi phục **giá trị cũ đã bị ghi đè** thì phải kiểm tra semantics của helper và tự xây scope đúng. Đừng coi “close” đồng nghĩa với restore toàn bộ map trước đó.

### MDC có thể chỉ giữ string

MDC thường lưu các giá trị `String`. Vì vậy `durationMs` hoặc `attempt` được đặt vào MDC có thể xuất thành chuỗi JSON nếu encoder không chuyển type. Những số cần aggregation nên được phát bằng per-event typed fields khi backend/API hỗ trợ, hoặc áp dụng schema mapping có kiểm chứng.

## 8. ThreadContext của Log4j2

Log4j2 API có `org.apache.logging.log4j.ThreadContext` để quản lý key–value context theo execution thread, thường dùng cùng Log4j2 Core:

```java
// Đoạn minh họa trong method; LOG/requestId/traceId đã tồn tại.
org.apache.logging.log4j.ThreadContext.put("requestId", requestId);
org.apache.logging.log4j.ThreadContext.put("traceId", traceId);
try {
    LOG.info("event=checkout.started");
} finally {
    org.apache.logging.log4j.ThreadContext.remove("traceId");
    org.apache.logging.log4j.ThreadContext.remove("requestId");
}
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. Cũng như MDC, ThreadContext không tự bảo đảm JSON output. `PatternLayout` có thể dùng `%X{requestId}` trong text; với structured output, cần layout/encoder và dependency phù hợp.

Log4j2 còn có các cơ chế context data và scoped context hỗ trợ một số kiểu cấu hình; behavior phụ thuộc version. Trong ứng dụng thật, ưu tiên cơ chế scope do framework/instrumentation cung cấp, và kiểm tra dữ liệu nào được backend ghi khi xử lý bất đồng bộ.

**Tránh hai nguồn khác nhau cho một field:** nếu application code dùng SLF4J MDC, còn một component khác lại đặt trực tiếp Log4j2 ThreadContext nhưng runtime có backend khác, context có thể không đến cùng pipeline. Phải xác nhận provider, bridge và việc tích hợp đang hoạt động.

## 9. Context qua ExecutorService, CompletableFuture và async task

MDC/ThreadContext thường gắn với thread hiện tại. **Không mặc định** một task được gửi đến executor sẽ thấy cùng context của thread submit. Worker thread có thể là thread khác hoặc được dùng lại cho nhiều request. Vì thế các biểu hiện thường gặp là:

- Log của task con **thiếu requestId**.
- Log của request B mang **requestId từ request A** do không clear context trên thread pool.
- Log của một retry hoặc callback có traceId sai.
- Query theo requestId không thể nối phần xử lý bất đồng bộ.

### Minh họa truyền snapshot MDC qua executor

Đoạn minh họa sau nằm trong method có `executor` và `LOG` của SLF4J:

```java
// Đoạn minh họa với imports java.util.Map và org.slf4j.MDC.
java.util.Map<String, String> captured =
        org.slf4j.MDC.getCopyOfContextMap();

executor.submit(() -> {
    java.util.Map<String, String> previous =
            org.slf4j.MDC.getCopyOfContextMap();

    try {
        if (captured == null) {
            org.slf4j.MDC.clear();
        } else {
            org.slf4j.MDC.setContextMap(captured);
        }

        LOG.info("event=checkout.async_step");
    } finally {
        if (previous == null) {
            org.slf4j.MDC.clear();
        } else {
            org.slf4j.MDC.setContextMap(previous);
        }
    }
});
```

Đây là **mã minh họa không độc lập**, vì `executor` và `LOG` phải do ứng dụng tạo, quản lý shutdown/lifecycle và exception của task theo hợp đồng. Ý tưởng chính là **chụp snapshot lúc submit, thiết lập trước khi chạy, khôi phục context của worker thread trong `finally`**.

Không dùng chung một map mutable giữa nhiều request. Nếu framework/tracing library đã có context propagation chính thức, dùng nó thay vì tự viết wrapper ở mọi nơi. Trong reactive systems hoặc virtual threads, ngữ cảnh có thể gắn với scope khác nhau; cần kiểm tra đúng API/instrumentation.

### AsyncAppender không tự giải quyết propagation

Phân biệt **chuyển context qua các bước xử lý ứng dụng** với **async appender/async logger ghi event**. Appender bất đồng bộ có thể chụp một số dữ liệu context tại thời điểm event được tạo, nhưng không làm cho một task `CompletableFuture` chưa được truyền context bỗng có requestId. Nguồn sự thật vẫn nằm ở execution scope của ứng dụng.

## 10. Per-event key–value fields và context bền theo request

Không phải thuộc tính nào cũng nên nằm trong MDC. Phân biệt:

| Thuộc tính | Scope phù hợp | Lý do |
| --- | --- | --- |
| `requestId` | Request context | Được dùng ở nhiều event trong cùng request. |
| `traceId` / `spanId` | Tracing context | Gắn với trace/span do tracing subsystem quản lý. |
| `service` / `environment` | Resource attributes | Ít thay đổi, có thể cấu hình ở backend/collector. |
| `orderId` | Operation hoặc event | Có thể thay đổi nếu request xử lý nhiều đơn hàng. |
| `attempt` | Retry event | Chỉ đúng trong một lần thử; không “rò” sang log khác. |
| `durationMs` | Event cụ thể | Được đo tại thời điểm kết thúc thao tác, nên có type number. |
| `errorCode` | Failure event | Chỉ có ý nghĩa khi lỗi/từ chối; không để tồn tại sai sau khi recovery. |
| `userRole` | Request context nếu thực sự cần | Phải xét quyền riêng tư và tính ổn định của giá trị. |

Nếu một request xử lý 100 đơn hàng, đặt `orderId` vào MDC rồi quên thay/xóa sẽ khiến log của các đơn sau mang ID sai. Trong trường hợp này, giữ `requestId` trong MDC và truyền `orderId` ở từng event có thể an toàn hơn.

### SLF4J 2.x fluent key–value API

SLF4J 2.x có thể gắn per-event key–value theo cách rõ ràng:

```java
// Đoạn minh họa cần SLF4J 2.x, LOG, orderId và durationMs.
LOG.atInfo()
   .addKeyValue("eventName", "checkout.completed")
   .addKeyValue("orderId", orderId)
   .addKeyValue("durationMs", durationMs)
   .log("Checkout completed");
```

Đây là **per-event attributes**, không tự tạo request-scoped MDC. Những field này có thể mang kiểu dữ liệu của giá trị ban đầu, nhưng **backend và encoder phải thực sự xuất chúng thành JSON fields**; một pattern chỉ chứa `%msg` có thể bỏ qua key–value pairs.

Dùng chung helper/schema constant cho tên trường để tránh module A dùng `request_id` còn module B dùng `requestId`. Tuy nhiên, chỉ đặt hằng số cho key không đủ: phải giữ semantic, đơn vị, enum và type nhất quán.

## 11. Ví dụ Java 17 chạy độc lập: context object trong JSON log

Chương trình dưới đây sử dụng **JUL (`java.util.logging`) có sẵn trong JDK 17**, không cần Maven hay thư viện ngoài. Nó trình bày ý tưởng **context được chụp theo từng event** dưới dạng immutable record và xuất thành object `context` trong JSON.

- `service` và `environment` là metadata cấp ứng dụng.
- `requestId` là context của request.
- `traceId` là thông tin truy vết nếu có; event thứ hai minh họa trường hợp không có trace bằng `null`.
- `orderId` và `outcome` là dữ liệu của từng event, đặt ngoài object context.
- Logger và handler dùng level rõ ràng; formatter nhận context từ chính `LogRecord`, không dựa vào ThreadLocal trong lúc format.
- Time được cố định để **stdout dự đoán được**.

**Lưu thành `ContextFieldsDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ContextFieldsDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    private record Context(
            String service,
            String environment,
            String requestId,
            String traceId
    ) {}

    private record Event(
            String eventName,
            String orderId,
            String outcome,
            Context context
    ) {}

    private static String jsonString(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u")
                           .append("0".repeat(4 - hex.length()))
                           .append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Event event = (Event) record.getParameters()[0];
            Context ctx = event.context();

            return "{"
                    + "\"timestamp\":"
                    + jsonString(record.getInstant().toString())
                    + ",\"level\":"
                    + jsonString(record.getLevel().getName())
                    + ",\"logger\":"
                    + jsonString(record.getLoggerName())
                    + ",\"eventName\":"
                    + jsonString(event.eventName())
                    + ",\"context\":{"
                    + "\"service\":" + jsonString(ctx.service())
                    + ",\"environment\":" + jsonString(ctx.environment())
                    + ",\"requestId\":" + jsonString(ctx.requestId())
                    + ",\"traceId\":" + jsonString(ctx.traceId())
                    + "}"
                    + ",\"orderId\":" + jsonString(event.orderId())
                    + ",\"outcome\":" + jsonString(event.outcome())
                    + "}\n";
        }
    }

    private static void emit(
            Level level,
            Instant timestamp,
            Event event
    ) {
        LogRecord record = new LogRecord(level, event.eventName());
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[]{event});
        LOG.log(record);
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Handler handler = new StreamHandler(bytes, new JsonFormatter());
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        try {
            Instant time = Instant.parse("2026-11-09T12:00:00Z");

            Context requestOne = new Context(
                    "checkout-service",
                    "demo",
                    "req-17",
                    "0123456789abcdef0123456789abcdef"
            );
            emit(
                    Level.INFO,
                    time,
                    new Event(
                            "checkout.started",
                            "ord-42",
                            "started",
                            requestOne
                    )
            );

            Context requestTwo = new Context(
                    "checkout-service",
                    "demo",
                    "req-18",
                    null
            );
            emit(
                    Level.WARNING,
                    time,
                    new Event(
                            "checkout.rejected",
                            "ord-43",
                            "rejected",
                            requestTwo
                    )
            );
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(bytes.toString(StandardCharsets.UTF_8));
    }
}
```

### Biên dịch và chạy

Cần JDK 17 trở lên:

```bash
javac ContextFieldsDemo.java
java ContextFieldsDemo
```

**Standard output chính xác của chương trình (hai dòng JSON):**

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","logger":"demo.checkout","eventName":"checkout.started","context":{"service":"checkout-service","environment":"demo","requestId":"req-17","traceId":"0123456789abcdef0123456789abcdef"},"orderId":"ord-42","outcome":"started"}
{"timestamp":"2026-11-09T12:00:00Z","level":"WARNING","logger":"demo.checkout","eventName":"checkout.rejected","context":{"service":"checkout-service","environment":"demo","requestId":"req-18","traceId":null},"orderId":"ord-43","outcome":"rejected"}
```

### Vì sao ví dụ chứng minh đúng khái niệm?

1. `Context` là record **bất biến**, chỉ chứa những thuộc tính có cùng phạm vi ngữ nghĩa; mỗi request có một snapshot riêng. Không sửa một map dùng chung rồi khiến event cũ bị ảnh hưởng khi formatter chạy sau đó.
2. `Event` tách `eventName`, `orderId` và `outcome` khỏi context; không để thông tin chỉ thuộc event tràn sang những log khác.
3. `emit` tạo `LogRecord` với timestamp, level, logger name và parameters gồm `Event`; `JsonFormatter` lấy lại đúng bản snapshot.
4. `logger.setUseParentHandlers(false)` tránh record đồng thời đi đến console handler của logger cha; dữ liệu chỉ được đưa vào `StreamHandler` đặt trong chương trình.
5. `handler.close()` flush record trước khi chương trình đọc `ByteArrayOutputStream`, nên stdout chứa chính hai JSON event vừa phát.
6. `JsonFormatter` xuất các key cố định. Event hai đặt `traceId:null` thay vì tạo một trace ID giả; cách xử lý null/absent phải được định nghĩa theo schema thực tế.
7. `jsonString` escape dấu ngoặc kép, backslash, một số dấu xuống dòng và control characters. Đây là **serializer giản lược để học**, không thay thế thư viện JSON hoặc encoder structured logging đã được kiểm chứng trong production, nhất là với Unicode bất thường và dữ liệu không tin cậy.
8. Ví dụ không chứng minh rằng JUL có JSON logging tích hợp sẵn. Ta đã tự cài đặt một `Formatter` chỉ để minh họa **cách một context snapshot trở thành object JSON**.

**Lưu ý:** đặt traceId dạng hex trong demo không tạo ra trace thực. Trong hệ thống phân tán, lấy trace/span ID từ tracer hoặc instrumentation đang hoạt động; không đoán dựa trên requestId.

## 12. Đưa context vào JSON output với Logback hoặc Log4j2

### 12.1. Logback

Với Logback Classic làm backend của SLF4J, có thể xuất MDC dưới dạng text pattern:

```xml
<!-- Đoạn minh họa trong <encoder> của Logback. -->
<pattern>%level requestId=%X{requestId} traceId=%X{traceId} %logger - %msg%n</pattern>
```

Kết quả là **text**, không phải JSON object chỉ vì có key bằng dấu `=`. Muốn JSON thực sự:

- Chọn encoder/layout JSON tương thích với phiên bản Logback đang chạy.
- Cấu hình trường MDC hoặc SLF4J key–value xuất thành các JSON key rõ ràng.
- Thử event có và không có context, có exception và các ký tự cần escaping.
- Đảm bảo schema field tương thích collector và không bị đè bởi metadata do pipeline thêm vào.

**Không ghép JSON thủ công bằng một pattern như `{"requestId":"%X{requestId}"}`** nếu giá trị không được JSON-escape đúng; có thể tạo JSON không hợp lệ hoặc log injection khi dữ liệu chứa dấu ngoặc kép, backslash hay xuống dòng.

### 12.2. Log4j2

Log4j2 `PatternLayout` có thể đọc ThreadContext qua `%X{requestId}`. Với JSON structured output, Log4j2 có các layout chuyên dụng, ví dụ `JsonTemplateLayout` ở những phiên bản có module thích hợp. Cần thêm dependency/layout template tương ứng và xác nhận key mapping trong template.

Không mặc định rằng mọi giá trị context đều phải được serialize. Chọn **allowlist các key cần thiết** để tránh đưa dữ liệu nội bộ/sensitive context vào log. Khi backend có tính năng tự động gắn exception, logger name, timestamps hoặc trace attributes, kiểm tra tên trường và thứ tự ưu tiên để tránh key bị ghi đè.

### 12.3. JUL

JUL có `LogRecord` và `Formatter`, nhưng không cung cấp API MDC chuẩn tương đương SLF4J MDC. Với code JUL thuần có thể:

- Truyền context cần thiết trong các tham số/event wrapper (như demo).
- Dùng một context propagation mechanism riêng của ứng dụng được kiểm thử, không để static mutable map dùng chung.
- Sử dụng bridge JUL → SLF4J nếu hệ thống đã thiết kế backend thống nhất, có thể map level/context phù hợp.

**Bridge không tự phát minh ra requestId/traceId.** Nếu code JUL không chứa context và không có instrumentation truyền, việc chuyển log sang Logback cũng không biến mọi event thành correlated JSON.

## 13. Giữ context chính xác khi có nested scope và transaction

Một request có thể mở nhiều thao tác con:

```text
requestId=req-17
  |
  +-- checkout.start
  |
  +-- inventory.reserve
  |     +-- inventoryOperationId=inv-9
  |
  +-- payment.authorize
  |     +-- paymentId=pay-42
  |
  +-- checkout.completed
```

Không để `paymentId` trong MDC trên toàn bộ thread nếu sau `payment.authorize` những event inventory khác không liên quan. Các cách tiếp cận:

- **Request scope:** giữ `requestId`, `traceId` ở scope lớn.
- **Operation scope:** dùng scoped context nếu một nhánh xử lý cần cùng `paymentId` cho nhiều log; nhớ khôi phục giá trị cũ sau khi kết thúc.
- **Event fields:** ghi `paymentId`, `attempt`, `durationMs` trực tiếp trên event nếu chúng chỉ có nghĩa tại thời điểm đó.
- **Resource fields:** giữ `service`, `environment` ổn định ở encoder/collector, không làm thay đổi theo từng request.

Nếu một request xử lý nhiều đơn hàng, `orderId` có thể thay đổi theo nhánh; đừng gắn một `orderId` duy nhất vào mọi log rồi tưởng mọi thao tác đều thuộc cùng một đơn.

### Khi rollback hoặc retry

Context chỉ giúp liên kết. Nó **không tự chứng minh một transaction đã commit**. Với retry, một timeout ở lần thử 1 có thể được phục hồi ở lần 2. Log nên có `attempt`, `maxAttempts` và `outcome` đúng mức; chỉ ghi `ERROR` cho thất bại cuối khi điều đó phản ánh hành vi nghiệp vụ.

Không gắn `outcome=failure` ở request scope quá sớm rồi quên sửa sau khi fallback thành công. Outcome của mỗi event phải được phát tại điểm có đủ thông tin.

## 14. Context và exception: thông tin bổ trợ, không thay nhau

Ví dụ:

```json
{
  "level": "ERROR",
  "eventName": "payment.failed",
  "context": {
    "service": "checkout-service",
    "requestId": "req-17",
    "traceId": "0123456789abcdef0123456789abcdef"
  },
  "paymentId": "pay-42",
  "errorCode": "UPSTREAM_TIMEOUT",
  "exceptionType": "java.net.SocketTimeoutException"
}
```

Các field context giải thích **đang xử lý request nào**. `errorCode` và exception/stack trace giải thích **lỗi gì và nguyên nhân ở đâu**. Một context đầy đủ không thể thay thế việc **truyền `Throwable` đúng API** khi cần stack trace, cause và suppressed exceptions.

Ví dụ SLF4J trong `catch`:

```java
// Đoạn minh họa, LOG và paymentId tồn tại, MDC đã có requestId.
catch (RuntimeException ex) {
    LOG.error("event=payment.failed paymentId={}", paymentId, ex);
    throw ex;
}
```

Đây không phải mã standalone. Tên `paymentId` trong message vẫn là text; nếu muốn field JSON riêng, dùng structured event API/encoder phù hợp. Nếu tầng phía trên đã chịu trách nhiệm ghi stack trace, tránh ghi trùng rồi rethrow ở nhiều tầng.

**Nguyên tắc an toàn:** không đưa toàn bộ exception message vào `requestId` hay `traceId` để “giữ thông tin”, vì như vậy làm hỏng semantic của context và có thể lộ dữ liệu. Hãy giữ context và error detail ở đúng trường.

## 15. Bảo mật và quyền riêng tư của context

Context rất dễ bị lạm dụng vì trông như metadata “vô hại”. Trong thực tế nhiều giá trị có thể nhận diện cá nhân hoặc tiết lộ hạ tầng.

| Field | Rủi ro có thể có | Cách giảm thiểu |
| --- | --- | --- |
| `userId` / `customerId` | Liên kết hoạt động với cá nhân. | Chỉ ghi khi thực sự cần, hạn chế quyền truy cập/retention, pseudonymize theo chính sách. |
| `email` / `phone` | Thông tin cá nhân trực tiếp. | Tránh ghi hoặc mask trước nguồn khi có thể. |
| `sessionId` | Có thể hỗ trợ chiếm phiên hoặc liên kết hành vi. | Không đưa session token/cookie vào log; dùng ID vô hại được phép nếu cần. |
| `authorization` / `apiKey` | Bí mật xác thực. | Tuyệt đối tránh ghi token/secret. |
| `clientIp` | Dữ liệu có thể mang tính cá nhân theo bối cảnh. | Cân nhắc chính sách, giảm chi tiết và retention. |
| `tenantId` | Có thể tiết lộ cấu trúc khách hàng. | Chỉ phát khi được phép, kiểm soát cross-tenant access. |
| `requestId` / `traceId` | Có thể giúp liên kết nhiều thao tác và hệ thống. | Chỉ dùng định danh được cấp, tránh embed thông tin bí mật vào ID. |
| `httpPath` / `query` | Có thể chứa dữ liệu nhạy cảm, token trong URL. | Ưu tiên route template, loại query nhạy cảm. |

**Không đặt nguyên request headers hoặc toàn bộ request body vào MDC**: framework có thể xuất mọi field MDC vào nhiều log, làm dữ liệu nhạy cảm lan rộng hơn nhiều so với một event có kiểm soát.

### Bảo vệ khỏi log injection

Nếu requestId đến từ header không đáng tin cậy, kẻ tấn công có thể gửi ký tự xuống dòng hoặc chuỗi rất dài. Mã cần validate chiều dài/ký tự và có chính sách tạo ID mới khi không hợp lệ. Structured JSON encoder chuẩn sẽ escape ký tự trong value, nhưng không thay thế validation và giới hạn kích thước.

### Hạn chế cardinality và kích thước record

`requestId` và `traceId` thường có cardinality cao — đó là đặc tính hữu ích cho truy vết, nhưng có thể gây chi phí indexing. Tránh biến chúng thành **tên field động** hoặc label của mọi metric. Áp dụng chiến lược index/retention/sampling có chủ đích theo công cụ vận hành.

## 16. Quản lý schema và tương thích giữa service

Field context là một phần của hợp đồng log schema. Ví dụ, nếu mọi service dùng `requestId` hôm nay nhưng service mới đổi thành `req_id` trong khi pipeline không map, truy vấn xuyên service sẽ bỏ sót log.

Cần quy định:

1. **Canonical names:** `service`, `environment`, `requestId`, `traceId`, `eventName` và các key chung.
2. **Type và encoding:** context string; các số như `durationMs` được xuất dạng number nếu dùng cho aggregation.
3. **Semantic:** traceId phải là tracing ID thật; không dùng ID request thay thế.
4. **Presence rules:** request nào có thể thiếu traceId, job nào không có requestId, thể hiện null/absent ra sao.
5. **Privacy classification:** field nào được phép phát, field nào cần mask hoặc không log.
6. **Schema ownership:** nhóm nào duyệt việc thêm/đổi tên và versioning khi breaking change.
7. **Mapping:** nếu nhiều framework/standard có tên field khác nhau, chọn bộ canonical hoặc chuẩn hóa tại collector có kiểm soát.

### Migration khi đổi key context

Đổi `requestId` thành `request_id` không chỉ là đổi biến Java. Dashboard, alert, tracing link và dữ liệu lịch sử có thể phụ thuộc tên cũ. Một kế hoạch phù hợp có thể là:

- Kiểm kê những consumer đang đọc key cũ.
- Định nghĩa schema mới và ngày/vòng phiên bản chuyển đổi.
- Cập nhật encoder/collector trước hoặc hỗ trợ cả hai key tạm thời nếu cần.
- Kiểm thử cả log của phiên bản cũ và mới trong giai đoạn rolling deploy.
- Ngừng dual-write khi các consumer đã chuyển hoàn toàn; tránh giữ alias mãi gây tăng dung lượng.

**Không trộn type hoặc semantic trong quá trình đổi tên.** Nếu chuyển từ `durationMs` sang `durationNs`, consumer cần được cập nhật cả tên lẫn đơn vị; không âm thầm đổi đơn vị mà giữ tên cũ.

## 17. Testing field context trong JSON logging

Một bộ kiểm thử tốt không chỉ kiểm tra method `logger.info(...)` đã được gọi, mà phải quan sát **event sau serializer/encoder**.

### Các kiểm thử nên có

| Test | Điều cần xác nhận |
| --- | --- |
| JSON parsing | Mỗi dòng là một object JSON hợp lệ khi pipeline dùng NDJSON. |
| Required fields | Các field `timestamp`, `level`, `service`, `eventName` xuất hiện đúng contract. |
| Request scope | Hai request liên tiếp có hai requestId riêng, không lẫn nhau. |
| Missing trace | Event không có trace hợp lệ dùng absent/null theo schema, không lấy trace cũ. |
| Async propagation | Log trong executor/callback giữ đúng correlation ID sau khi truyền scope. |
| Cleanup | Request kết thúc không để MDC/ThreadContext rò sang thread pool task sau. |
| Type | `durationMs` là number khi schema yêu cầu; context ID vẫn là string. |
| Escaping | Dấu ngoặc kép, backslash, tiếng Việt, newline và control characters không làm hỏng JSON. |
| Throwable | Event lỗi có exception/cause theo chính sách, không vô tình bỏ stack trace. |
| Privacy | Field bí mật không có mặt; request headers/body không bị log tự động. |
| Multiple backend | Runtime thực sự dùng đúng provider, layout/encoder và field mapping cần thiết. |
| Collector compatibility | Field từ app, agent và log index không đè nhau hoặc đổi tên ngoài dự kiến. |

### Tình huống kiểm thử rò context

```text
Request A -> requestId=req-A -> log A
Request A ends -> context cleared
Thread is reused
Request B -> requestId=req-B -> log B

Expected:
- Log A chỉ mang req-A.
- Log B chỉ mang req-B.
- Không có record nào của B mang req-A.
```

Một test có thể chạy hai tác vụ tuần tự trên cùng một single-thread executor, cố ý đặt/xóa context để phát hiện rò rỉ. Test chỉ assert message text là chưa đủ: phải parse field `requestId` thực sự trong JSON output.

### Test ngữ cảnh nhiều service

Gửi request có tracing context qua service A → B. Kiểm tra A và B xuất cùng `traceId` nếu cùng trace và các `spanId` đúng span hiện tại. Nếu B không có trace, xác định rõ đó là lỗi propagation, sampling/tracing configuration hoặc do span không được tạo; không gán ngẫu nhiên traceId trong log để làm test qua.

## 18. Các lỗi thường gặp và hướng sửa

| Hiện tượng | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| JSON có `message:"requestId=..."` nhưng không có field requestId | Chỉ dùng text placeholder. | Dùng MDC/ThreadContext hoặc typed key–value + encoder JSON thực sự. |
| RequestId trống ở async task | Context chưa được truyền từ thread submit. | Propagate snapshot/scope qua executor hoặc dùng instrumentation chính thức. |
| Log request B mang requestId của A | Không clear/restore MDC trên pooled thread. | Cleanup trong `finally`, kiểm thử reused thread. |
| `traceId` giống `requestId` nhưng không tìm thấy trace | Tự copy hoặc tạo trace ID giả. | Lấy traceId/spanId từ tracer hoạt động. |
| Thông tin user/token xuất ở mọi log | Gắn quá nhiều dữ liệu vào MDC. | Allowlist key, loại secrets và giới hạn scope. |
| `durationMs` xuất dạng string | Lưu số dưới dạng MDC String hoặc encoder ép kiểu. | Ghi typed per-event field hoặc mapping type có kiểm thử. |
| Hai service dùng `requestId`/`request_id` khác nhau | Không có schema chung. | Quy ước canonical name và migration/collector mapping. |
| Dùng key `user_123` hoặc `req_17` | Đưa dữ liệu biến động vào tên field. | Giữ key cố định, đặt giá trị vào field. |
| Context được cấu hình ở Logback nhưng runtime chọn Log4j2 | Backend khác active, config không nạp. | Xác nhận provider/bridge và cấu hình thực tế. |
| JSON parse lỗi khi context chứa dấu ngoặc kép | Dùng text pattern để ghép JSON, thiếu escaping. | Sử dụng JSON encoder/layout đã kiểm chứng. |
| JSON có cả `context.requestId` và object `context` | Hai cách biểu diễn/collector mapping xung đột. | Chọn một schema và normalize có chủ đích. |
| Log ít nhưng storage/index tốn chi phí lớn | Index mọi high-cardinality field hoặc số lượng key quá nhiều. | Đánh giá mapping/index retention/sampling. |
| Appender async vẫn thiếu requestId ở task con | Nhầm async logging với context propagation ứng dụng. | Truyền scope trước khi task phát log. |
| Error event thiếu stack trace dù có context | Chỉ ghi error text, không đính Throwable. | Dùng API log exception và kiểm tra encoder/collector. |
| Context thiếu ở background job | Code mặc định chỉ HTTP request có context. | Định nghĩa jobId/workflowId và bootstrap context theo job. |

## 19. Checklist review Field context trước khi đưa lên production

- [ ] Context field nào thật sự cần: resource, request, tracing, operation?
- [ ] Tên key, kiểu JSON, ý nghĩa và điều kiện xuất hiện đã nằm trong schema chưa?
- [ ] Có tránh nhầm requestId, traceId, spanId và correlationId không?
- [ ] Giá trị ID được validate, giới hạn độ dài và lấy từ nguồn đúng không?
- [ ] Resource metadata (service, environment, instance) được gắn tập trung ở một nguồn sự thật chưa?
- [ ] MDC/ThreadContext có scope rõ, được dọn/khôi phục kể cả khi exception không?
- [ ] Executor, callback, reactive chain và virtual thread có truyền context phù hợp không?
- [ ] Per-event fields như durationMs, errorCode và attempt có bị đặt sai vào request scope không?
- [ ] JSON encoder có thực sự xuất context thành field thay vì chỉ nối message không?
- [ ] Pipeline dùng flat hay nested, trường chứa dấu chấm được xử lý thế nào?
- [ ] Không có mật khẩu, token, session cookie, header nhạy cảm và payload cá nhân không cần thiết?
- [ ] Collector/index có parse JSON, giữ schema, ánh xạ type và kiểm soát cardinality không?
- [ ] Test đã kiểm tra hai request trên cùng thread pool không lẫn context chưa?
- [ ] Event lỗi có Throwable/cause và context hữu ích, không ghi trùng ở nhiều tầng không?
- [ ] Khi đổi tên key, có kế hoạch migration để dashboard và alert không đứt đoạn không?

## 20. Câu hỏi tự kiểm tra

1. Vì sao `requestId` trong text `message` chưa chắc được coi là JSON context field?
2. `service`, `requestId` và `orderId` thuộc những vòng đời khác nhau thế nào?
3. Khi request qua `CompletableFuture`, vì sao MDC ở thread caller có thể không xuất hiện ở task con?
4. Vì sao context cần được clear hoặc restore khi thread pool được dùng lại?
5. `traceId` khác `requestId` ở điểm nào và lấy trace ID từ đâu?
6. Cách chọn flat fields so với nested `context` ảnh hưởng truy vấn/collector thế nào?
7. Vì sao field `durationMs` nên là number thay vì một chuỗi từ MDC?
8. Khi nào `orderId` phù hợp ở per-event fields hơn là request-wide MDC?
9. Vì sao không nên đặt token hay toàn bộ request body vào context?
10. Trong demo JUL, việc truyền immutable `Context` trong `LogRecord` có lợi gì so với dùng static mutable map?
11. AsyncAppender có tự làm context propagation cho Java executor không?
12. Vì sao một service chỉ đổi `requestId` thành `req_id` có thể phá vỡ dashboard dù JSON vẫn hợp lệ?

**Kết luận:** **Field context biến từng bản ghi JSON thành một phần của bức tranh vận hành có thể liên kết**. Muốn context hữu ích, hãy xác định đúng **nguồn và vòng đời**, giữ **tên/type/semantic ổn định**, truyền context qua ranh giới đồng bộ và bất đồng bộ, dọn sạch sau scope, **chỉ xuất những field được phép**, và kiểm thử dữ liệu **sau encoder/collector**. Context giúp giải thích *sự kiện thuộc request, trace và service nào*; nó không thay cho event fields, exception details hay những đảm bảo về độ bền của pipeline logging.