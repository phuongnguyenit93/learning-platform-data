# Tìm log theo correlation ID trong Java: từ file log đến hệ thống tập trung

Khi một người dùng báo giao dịch thất bại, hệ thống Java có thể đã phát hàng nghìn log từ nhiều request, thread và service. Nếu chỉ tìm từ khóa `ERROR` hoặc `timeout`, kết quả thường quá rộng. **Tìm log theo correlation ID** giúp truy lại những sự kiện thuộc **cùng một yêu cầu hoặc hoạt động**, theo một khóa ổn định đã được gắn vào từng log event.

Ví dụ:

```text
2026-11-09T10:00:00Z INFO  correlationId=corr-42 event=request_started
2026-11-09T10:00:02Z WARN  correlationId=corr-42 event=dependency_retry
2026-11-09T10:00:03Z ERROR correlationId=corr-42 event=payment_failed
2026-11-09T10:00:04Z INFO  correlationId=corr-77 event=other_request
```

Với `correlationId=corr-42`, người điều tra muốn lấy **ba event đầu**, không phải toàn bộ log của service hay những event tình cờ chứa chuỗi `corr-42` trong message. Dữ liệu trên là minh họa, không phải kết quả của một backend cụ thể.

Bài học thuộc nhóm **Correlation ID**. Trọng tâm là các **phương pháp tra cứu** trên text log, JSONL, PowerShell, hệ thống log tập trung và Java 17; cách giữ stack trace của event khớp; tìm trong file đã rotation; kiểm tra sự thiếu ID do MDC, executor hoặc service boundary; và những quy tắc bảo mật khi khai thác log.

## 1. Correlation ID, request ID và trace ID

**Correlation ID** là định danh được tổ chức dùng để liên kết nhiều event trong phạm vi một hoạt động. Java và SLF4J **không bắt buộc** phải dùng tên field `correlationId`. Ứng dụng có thể đặt `requestId`, `correlation_id` hoặc tên khác theo logging contract.

Một structured event ví dụ:

```json
{
  "timestamp": "2026-11-09T10:00:03.000Z",
  "level": "ERROR",
  "service": "payment-service",
  "correlationId": "corr-42",
  "logger": "com.example.PaymentService",
  "event": "payment_failed",
  "errorCode": "UPSTREAM_TIMEOUT",
  "message": "Payment dependency timed out"
}
```

| Trường | Ý nghĩa thường gặp | Chú ý |
| --- | --- | --- |
| `correlationId` | Liên kết event trong chuỗi nghiệp vụ/request do dự án định nghĩa | Không có format bắt buộc chung |
| `requestId` | Định danh một request HTTP/API | Có thể thay đổi giữa các hop nếu không propagation |
| `traceId` | Định danh toàn bộ trace phân tán | Không mặc nhiên bằng correlation ID |
| `spanId` | Định danh một span thuộc trace | Không nên dùng riêng để đại diện toàn trace |
| `thread` | Thread Java phát event | Một worker có thể chạy nhiều request |
| `errorCode` | Phân loại lỗi | Nhiều request khác nhau có cùng error code |
| `timestamp` | Thời điểm ghi nhận event | Phải biết timezone, độ chính xác và trường thời gian của index |

**Một correlation ID không nhất thiết là trace ID.** Trong W3C Trace Context, trace ID thường được biểu diễn bằng 32 ký tự hex hợp lệ và span ID bằng 16 ký tự hex hợp lệ. ID nghiệp vụ có thể theo một convention khác, ví dụ `corr-42`. Không suy từ chữ “ID” rằng mọi loại ID có thể dùng thay nhau.

Trường nên được ghi **tách khỏi message** để các công cụ tìm kiếm so sánh theo **giá trị field** thay vì tìm chuỗi con.

## 2. Quy trình tìm kiếm trước khi mở file lớn

Một quy trình điều tra có cấu trúc:

1. **Lấy ID chính xác** từ phản hồi lỗi, API response header, trace UI hoặc log ban đầu có thể tin cậy. Không đoán ID chỉ từ tên người dùng hay thời gian.
2. **Biết tên field thực tế:** `correlationId`, `requestId`, `traceId`, `mdc.correlationId` hoặc tên đã qua mapping của collector.
3. **Giới hạn thời gian** theo mốc sự cố và timezone, để tránh quét toàn bộ retention.
4. **Giới hạn nguồn** theo environment, service, deployment, pod hoặc tenant được phép truy cập.
5. **Tìm khớp chính xác**, giữ cả event đầu/cuối và các event không phải ERROR.
6. **Mở rộng theo luồng xử lý:** gateway → service → worker/queue → downstream.
7. **Đọc log đầy đủ**, gồm message, exception/`Throwable`, stack trace và cause chain.
8. **Đối chiếu metrics/tracing** trước khi kết luận nguyên nhân.

Điểm cần nhớ là **ID được tìm trong một scope**. Một giá trị hợp lệ ở service A nhưng không xuất hiện ở service B có thể do không truyền metadata qua HTTP hoặc executor, chứ không chứng minh service B chưa từng nhận công việc.

### Nguy cơ tìm theo tiền tố

```text
INFO requestId=req-42 event=start
INFO requestId=req-420 event=unrelated
WARN requestId=req-42 event=retry
```

Lệnh tìm literal `requestId=req-42` sẽ khớp **cả `req-420`** vì chuỗi đầu là tiền tố của chuỗi sau. Với hệ thống tìm kiếm, phải phân biệt **substring match** và **exact field match**. Đây là một trong những nguồn false positive phổ biến nhất khi điều tra.

## 3. Tìm trong file text bằng Linux/macOS

Giả sử đã xác định file `logs/application.log` thuộc service cần kiểm tra.

### Tìm nhanh theo literal

```bash
grep -n -F 'correlationId=corr-42' logs/application.log
```

`grep -F` xem pattern là chuỗi literal, `-n` thêm số dòng vật lý. Cách này nhanh nhưng vẫn có thể khớp `corr-420` hoặc một thông điệp nói “related to corr-42”. **Không xem đây là exact field match.**

### Tìm với ranh giới field

Nếu quy ước text log là các field cách nhau bằng khoảng trắng:

```bash
grep -n -E '(^|[[:space:]])correlationId=corr-42([[:space:]]|$)' logs/application.log
```

Trong format giả định, regex yêu cầu có khoảng trắng/đầu dòng trước field và khoảng trắng/cuối dòng sau ID. Nó tránh match `corr-420`. Nhưng nếu message cũng có `correlationId=corr-42`, grep vẫn có thể lấy nhầm; đây **không phải parser cấu trúc**. Đừng nối raw input chứa ký tự regex/shell từ người dùng vào lệnh một cách tùy tiện.

### Xem dòng xung quanh

```bash
grep -n -C 5 -F 'correlationId=corr-42' logs/application.log
```

Với GNU grep, `-C 5` hiển thị năm dòng trước và sau mỗi kết quả. Điều này giúp thấy một phần exception, nhưng không đảm bảo trọn stack trace dài và có thể kéo thêm những event không cùng ID.

### Theo dõi log đang ghi

```bash
tail -n 50 -F logs/application.log
```

Trên GNU coreutils, `-F` theo **tên file** và hữu ích khi file được rename/recreate trong quá trình rotation. Nó không phải công cụ tìm lịch sử dài hạn: record đã bị rotate trước đó có thể ở file archive, còn event chưa được appender flush chưa hiện trên disk.

### File đã rotation hoặc nén

Ví dụ:

```text
logs/application.log
logs/application.log.1
logs/application.2026-11-08.log.gz
```

Tìm trong archive `.gz` khi còn có quyền truy cập:

```bash
gzip -dc logs/application.2026-11-08.log.gz | grep -n -F 'correlationId=corr-42'
```

`gzip -dc` giải nén ra stdout mà không ghi đè file archive. Nếu cần bảo toàn chứng cứ hoặc tái lập kết quả, ghi rõ **tên file nguồn**, thời điểm truy vấn và phạm vi được đọc. `grep -n` ở ví dụ này đánh số dòng trong luồng giải nén, không phải trong file nén nhị phân.

File text có stack trace nhiều dòng sẽ khiến `wc -l` hoặc số match của grep **khác số log event**. Phải biết formatter thực tế để phân nhóm đúng.

## 4. Tìm chính xác trong JSON Lines bằng jq

Với **JSONL/NDJSON**, mỗi dòng vật lý phải chứa một JSON object hoàn chỉnh. Ví dụ file `logs/application.jsonl`:

```json
{"timestamp":"2026-11-09T10:00:00Z","level":"INFO","correlationId":"corr-42","event":"start"}
{"timestamp":"2026-11-09T10:00:01Z","level":"INFO","correlationId":"corr-420","event":"unrelated"}
{"timestamp":"2026-11-09T10:00:02Z","level":"WARN","correlationId":"corr-42","event":"retry"}
```

Nếu đã cài `jq` (không thuộc JDK):

```bash
jq -c --arg id 'corr-42' 'select(.correlationId == $id)' logs/application.jsonl
```

`--arg` chuyển ID thành một biến chuỗi trong jq; `==` so sánh **giá trị property**. Event `corr-420` không được chọn. Nếu schema dùng `requestId`, sửa đường dẫn property theo field thật. Một encoder khác có thể lưu:

```json
{"context":{"correlationId":"corr-42"},"event":"start"}
```

Khi đó query tương ứng:

```bash
jq -c --arg id 'corr-42' 'select(.context.correlationId == $id)' logs/application.jsonl
```

Tìm thêm theo severity:

```bash
jq -c --arg id 'corr-42' 'select(.correlationId == $id and .level == "ERROR")' logs/application.jsonl
```

Đếm số event match mà không dùng `jq -s` (*slurp*) để nạp toàn bộ file vào mảng:

```bash
jq -c --arg id 'corr-42' 'select(.correlationId == $id)' logs/application.jsonl | wc -l
```

Cách đếm này dựa vào hợp đồng mỗi output match là một JSON object trên một dòng, và giả định không có record hỏng. Khi dữ liệu lớn, truy vấn trên log platform có index sẽ hữu ích hơn tải file xuống máy trạm. Không tự dùng `String.split(",")` hoặc regex tổng quát để phân tích JSON: message có thể chứa dấu phẩy, nháy kép, JSON lồng nhau hoặc newline đã escape.

## 5. Tìm trên Windows PowerShell

Với file text:

```powershell
Select-String -LiteralPath 'C:\logs\application.log' -SimpleMatch -Pattern 'correlationId=corr-42'
```

Tương tự `grep -F`, nó tìm chuỗi con, không phân tích field. Với format cách nhau bằng whitespace:

```powershell
Select-String -LiteralPath 'C:\logs\application.log' -Pattern '(^|\s)correlationId=corr-42(\s|$)'
```

Với JSONL đúng một object/dòng, có thể parse rồi so sánh:

```powershell
Get-Content -LiteralPath 'C:\logs\application.jsonl' | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.correlationId -ceq 'corr-42' } | ConvertTo-Json -Compress
```

`-ceq` so sánh phân biệt hoa/thường; `-eq` thông thường không phân biệt hoa/thường cho chuỗi. Phải dùng phép so sánh phù hợp contract ID, nhất là khi ID có chữ hoa.

Ví dụ giả định toàn bộ các dòng parse được. Nếu có dòng hỏng, `ConvertFrom-Json` có thể báo lỗi; đừng coi record bị bỏ qua như bằng chứng “không có ID”. Với file rất lớn, pipeline PowerShell có thể chậm, cần xem lựa chọn đọc streaming, time filter hoặc dùng central logging.

## 6. Truy vấn trên hệ thống log tập trung

### Elasticsearch/Kibana

Nếu index có field `correlationId` kiểu `keyword`, một Query DSL có thể là:

```json
{
  "query": {
    "bool": {
      "filter": [
        {"term": {"correlationId": "corr-42"}},
        {"range": {"@timestamp": {
          "gte": "2026-11-09T09:55:00Z",
          "lte": "2026-11-09T10:05:00Z"
        }}}
      ]
    }
  }
}
```

`term` tìm exact indexed term theo mapping. Nếu field là analyzed text, kết quả có thể khác so sánh chuỗi gốc. Một số index có subfield `correlationId.keyword` và khi đó có thể dùng nó; **không giả định subfield tồn tại**. Hãy kiểm tra mapping trước.

Một minh họa KQL nếu index đã có subfield đó:

```text
correlationId.keyword : "corr-42" and service.name : "payment-service"
```

Không coi KQL/full-text search là exact match một cách mặc định nếu field chưa được mapping thành keyword.

### Grafana Loki (LogQL)

Giả sử stream có label `service` và log body là JSON:

```logql
{service="payment-service"} | json | correlationId="corr-42"
```

Pipeline chọn stream, parse JSON và lọc field. Với text log chưa parse:

```logql
{service="payment-service"} |= "correlationId=corr-42"
```

Dạng `|=` tìm substring, có thể khớp `corr-420`. Loki stream labels cần cân nhắc cardinality: **correlation ID có cardinality cao và thường không nên dùng làm stream label riêng cho từng request**. Nên thu hẹp stream bằng service/environment/time và lọc ID trong body/structured metadata.

### Vì sao dashboard có thể không trả kết quả?

- Field bị collector **rename** thành `request.id` hoặc `mdc.correlationId`.
- Index không có kiểu exact-match; query dùng sai field path.
- `@timestamp` được map từ ingestion time thay vì event time, hoặc dashboard đang ở timezone/cửa sổ sai.
- Backend đã lọc DEBUG/INFO trước khi ghi; log không hề được tạo.
- Event đang ở một instance/service khác hoặc trong archive.
- Collector bị chậm, drop, truncate hoặc không parse record JSON.
- Quyền người truy vấn không bao phủ mọi service hoặc tenant.
- Retention đã hết.

Vì thế **“không tìm thấy” không tự chứng minh request chưa chạy**. Hãy kiểm tra từng tầng trước khi kết luận.

## 7. Ví dụ Java 17 độc lập: tìm đúng requestId và giữ stack trace

Trong file text, `Throwable`/stack trace thường được viết thành nhiều dòng. Những dòng `at ...` hoặc `Caused by: ...` không chứa ID, nên lệnh tìm một dòng sẽ làm mất ngữ cảnh exception. Ví dụ này dùng một parser nhỏ theo **format mẫu rõ ràng**, đọc file theo luồng và in **toàn bộ event khớp**, bao gồm các dòng continuation.

Không cần Maven hay thư viện ngoài JDK. Chương trình tạo **thư mục và file tạm**, ghi dữ liệu mẫu, đọc và xóa **chỉ những tài nguyên do chính demo tạo**. Nó không đọc, ghi hoặc xóa log production.

### 7.1. Lưu file `ReadLogByCorrelationId.java`

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ReadLogByCorrelationId {
    // Chỉ nhận header của format mẫu: timestamp, level, requestId.
    private static final Pattern HEADER = Pattern.compile(
            "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z "
            + "(?:TRACE|DEBUG|INFO|WARN|ERROR) "
            + "requestId=([A-Za-z0-9_-]+)(?:\\s|$)");

    private ReadLogByCorrelationId() {
    }

    public static void main(String[] args) throws IOException {
        String targetId = "req-42";

        Path dir = Files.createTempDirectory("correlation-demo-");
        Path file = dir.resolve("application.log");

        try {
            String sample = String.join("\n",
                    "2026-11-09T10:00:00Z INFO requestId=req-42 event=request_started",
                    "2026-11-09T10:00:01Z INFO requestId=req-420 event=other_request",
                    "2026-11-09T10:00:02Z WARN requestId=req-42 event=dependency_retry",
                    "2026-11-09T10:00:03Z ERROR requestId=req-42 event=payment_failed",
                    "java.lang.IllegalStateException: timeout",
                    "    at com.example.PaymentGateway.call(PaymentGateway.java:42)",
                    "Caused by: java.net.SocketTimeoutException: read timed out",
                    "2026-11-09T10:00:04Z INFO requestId=req-77 event=unrelated"
            ) + "\n";

            Files.writeString(
                    file, sample, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            int matchedEvents = 0;
            int continuationLines = 0;
            boolean matchedCurrentEvent = false;

            System.out.println("query=requestId=" + targetId);

            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    Matcher m = HEADER.matcher(line);

                    if (m.find()) {
                        // Header mới: kiểm tra ID chính xác.
                        matchedCurrentEvent = targetId.equals(m.group(1));
                        if (matchedCurrentEvent) {
                            matchedEvents++;
                            System.out.println(line);
                        }
                    } else if (matchedCurrentEvent) {
                        // Giữ các dòng Throwable/stack trace tiếp nối.
                        continuationLines++;
                        System.out.println(line);
                    }
                }
            }

            System.out.println("matchedEvents=" + matchedEvents);
            System.out.println("continuationLines=" + continuationLines);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

### 7.2. Chạy bằng JDK 17+

```bash
javac -encoding UTF-8 ReadLogByCorrelationId.java
java ReadLogByCorrelationId
```

**Stdout chính xác khi chạy thành công:**

```text
query=requestId=req-42
2026-11-09T10:00:00Z INFO requestId=req-42 event=request_started
2026-11-09T10:00:02Z WARN requestId=req-42 event=dependency_retry
2026-11-09T10:00:03Z ERROR requestId=req-42 event=payment_failed
java.lang.IllegalStateException: timeout
    at com.example.PaymentGateway.call(PaymentGateway.java:42)
Caused by: java.net.SocketTimeoutException: read timed out
matchedEvents=3
continuationLines=3
```

**Stderr:** chương trình không chủ động ghi stderr khi thành công. Nếu thiếu quyền tạo/xóa file tạm hoặc có lỗi I/O, chương trình có thể dừng với exception.

### 7.3. Phân tích output

- `req-42` có **3 event**: `request_started`, `dependency_retry`, `payment_failed`.
- `req-420` là ID khác dù cùng tiền tố; so sánh bằng `String.equals` nên **không bị lấy nhầm**.
- `req-77` không được lấy.
- Ba dòng sau event ERROR (exception, frame, `Caused by`) được giữ làm **3 continuation lines**.
- Khi gặp header mới, parser reset biến `matchedCurrentEvent` để không kéo những dòng của request khác vào.
- `BufferedReader` giúp không nạp cả file vào bộ nhớ; `Files.deleteIfExists` chỉ dọn file demo đã tạo.

**Giới hạn cố ý:** regex chỉ khớp timestamp dạng `yyyy-MM-ddTHH:mm:ssZ`, level và `requestId` ở vị trí cụ thể. Nó không hỗ trợ log có milliseconds, offset khác UTC, logger/thread chen giữa hay JSON. Nếu một header mới không khớp regex, chương trình có thể coi nó là continuation của event trước. Nếu message chứa text giả giống header, parser có thể reset nhầm. Đừng coi đây là parser production cho mọi định dạng.

Ngoài ra, một **dòng cực dài** vẫn có thể khiến `readLine()` dùng nhiều bộ nhớ; file live có thể đổi trong lúc đọc; file rotation hoặc nhiều writer có thể phá ranh giới event. Với production, ưu tiên compact JSONL/structured encoder và log collector có schema hoặc multiline rules đã được kiểm chứng.

## 8. Tìm trong container và Kubernetes

Ứng dụng container có thể chỉ ghi stdout/stderr. Với một pod và container cụ thể:

```bash
kubectl logs pod/payment-service-abc123 -c app --since=30m
```

Tên pod/container chỉ là minh họa. Nếu container restart và runtime còn giữ log instance trước:

```bash
kubectl logs pod/payment-service-abc123 -c app --previous
```

`--previous` không phải cơ chế lưu trữ dài hạn. Rotation, retention và việc pod bị thay thế có thể khiến log cũ không còn. Một request có thể đi qua nhiều instance; không được giả định log từ một pod đã bao phủ toàn bộ hoạt động.

Trong production, dùng central log platform để tìm toàn bộ service liên quan theo ID, time window và quyền cho phép. Một lệnh xem log deployment có thể không tự động gộp đủ mọi replica theo kỳ vọng.

## 9. Vì sao correlation ID bị mất khi chuyển thread hoặc service?

Muốn tìm, trước hết log phải **được gắn đúng ID**.

Với SLF4J + backend có MDC:

```java
// Fragment: LOG, correlationId và handleRequest() đã tồn tại.
org.slf4j.MDC.put("correlationId", correlationId);
try {
    LOG.info("event=request_received");
    handleRequest();
} finally {
    org.slf4j.MDC.remove("correlationId");
}
```

Đoạn trên minh họa một request scope. Nếu một scope bên ngoài đã có key cùng tên, `remove` không phục hồi giá trị trước đó; cần snapshot/restore đúng phạm vi. SLF4J `MDC.getCopyOfContextMap()` hỗ trợ lấy snapshot map trong thread hiện tại.

Trong Logback, pattern có thể dùng:

```xml
<!-- Fragment trong <encoder> của Logback -->
<pattern>%d{HH:mm:ss.SSS} %-5level correlationId=%X{correlationId} %logger - %msg%n</pattern>
```

Nhưng **pattern không tự tạo ID**. Nếu chưa `MDC.put` thì trường có thể trống. Nếu JSON encoder đưa MDC dưới `mdc`, câu query phải theo đường dẫn `mdc.correlationId`, không đoán `correlationId` ở root.

Ranh giới dễ làm mất ID:

- **HTTP ingress:** validate ID từ header như `X-Correlation-ID` hoặc sinh ID server-side khi cần. Không tin ID do client gửi một cách tuyệt đối.
- **HTTP egress:** truyền metadata qua service khác theo hợp đồng, không nhầm correlation ID với authorization token.
- **Executor/CompletableFuture:** MDC thường gắn với thread. Cần capture tại nơi submit, install trên worker, restore map trước đó trong `finally`. Thread pool tái sử dụng worker nên không được để ID cũ rò sang request sau.
- **Message broker/background job:** truyền metadata phù hợp trong message, gắn vào consumer scope, dọn sau khi xử lý.
- **Distributed tracing:** dùng `traceparent`/OpenTelemetry instrumentation để tìm `traceId` khi có; không tự cho rằng trace ID và correlation ID bằng nhau.

**Dữ liệu MDC là metadata quan sát**, không phải security context hay cơ chế phân quyền. Biết correlation ID không cho phép một bên xem hoặc thao tác bất kỳ request nào.

## 10. Lập timeline và đọc kết quả

Giả sử một query tìm được:

```text
10:00:00.000 gateway       INFO  corr-42 request_received
10:00:00.031 checkout      INFO  corr-42 price_validated
10:00:00.073 payment       INFO  corr-42 payment_started
10:00:01.204 payment       WARN  corr-42 upstream_retry attempt=1
10:00:02.480 payment       ERROR corr-42 upstream_timeout
10:00:02.510 gateway       ERROR corr-42 response_failed status=503
```

Đây là timeline minh họa. Nó gợi ý dependency bị chậm và gateway đã trả lỗi, nhưng **không tự chứng minh quan hệ nhân quả** nếu chưa đối chiếu tracing, stack trace, errorCode và metrics.

Nên điều tra theo thứ tự: tìm đầu vào request → tìm bước bắt đầu xử lý → xem WARN/retry → tìm exception cuối và cause chain → xác định response/outcome → đối chiếu các service, queue và trace. Lưu ý:

- **Timestamp có thể lệch giữa node** do clock skew hoặc timezone.
- **Ingestion time** có thể muộn hơn event time khi backend/collector async.
- Một sự kiện có thể bị filter theo level hoặc drop do queue/retention.
- Log cùng correlation ID cần được xem theo **service, instance, attempt và event type**, không đơn thuần sắp xếp chuỗi text.

## 11. Lỗi tìm log theo ID và cách điều tra

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Tìm `req-42` ra cả `req-420` | Dùng substring | Exact field match, keyword query hoặc regex có boundary |
| Query `correlationId` trống | Schema dùng `requestId` hoặc `mdc.correlationId` | Kiểm tra JSON nguồn và mapping |
| ID chỉ có ở gateway | Downstream không propagate header | Kiểm tra HTTP ingress/egress |
| Worker thiếu ID | MDC không truyền qua executor | Capture/install/restore theo task |
| Request B mang ID của A | Context không dọn ở reused thread | Restore trong `finally`, test isolation |
| `traceId` khác correlation ID | Hai loại ID khác ngữ nghĩa | Tìm mapping đã định nghĩa |
| Dashboard không thấy log trong file | Parser/collector rename hoặc indexing sai | Kiểm tra field path và type |
| Stack trace bị mất | Continuation lines không có ID | Multiline parser hoặc structured JSONL |
| Sự kiện cũ không còn file hiện tại | Rotation, archive gzip, retention | Kiểm tra file đã rotate và central storage |
| Pod restart không tìm được log | Runtime không giữ previous log | Kiểm tra `--previous` nếu có |
| DEBUG/INFO không xuất | Logger/appender threshold lọc | Kiểm tra cấu hình tại nguồn |
| Log đến muộn | Queue/ingest delay, query sai time field | Xem event time và observed time |
| ID bị trùng giữa request | Generator client/server thiếu uniqueness | Rà cách tạo ID và scope |
| JSONL parse lỗi | Record bị cắt, output không phải JSONL | Kiểm tra encoder/serializer |
| Tìm sai service | Request đi qua nhiều instance | Mở rộng scope có kiểm soát |
| Thiếu quyền xem log | Policy phân quyền | Yêu cầu access đúng quy trình |

Một chuỗi kiểm tra hữu ích:

```text
Ứng dụng có ID khi nhận request?
        |
        v
MDC/event có field ID?
        |
        v
Encoder ghi field đúng JSON/text?
        |
        v
File/stdout/collector có giữ event?
        |
        v
Index có map field đúng kiểu?
        |
        v
Query đúng ID, time, service và access scope?
        |
        v
Đã tìm đủ các service/instance?
```

Nếu file gốc có ID nhưng index không có, vấn đề nằm ở parser/ingestion. Nếu log gốc của worker thiếu ID, vấn đề ở propagation. **Không sửa câu query để che lỗi instrumentation.**

## 12. Bảo mật khi tìm theo correlation ID

- **ID không cấp quyền:** ai biết `corr-42` không có quyền xem mọi event liên quan.
- **Không chứa bí mật trong ID:** tránh token, mật khẩu, cookie phiên, số thẻ, email và dữ liệu nhạy cảm.
- **Validate ID từ client:** giới hạn chiều dài, tập ký tự, CRLF, khả năng giả mạo/reuse.
- **Giới hạn truy vấn:** service, time window, tenant được phép và số bản ghi.
- **Không gửi raw logs ngoài phạm vi:** redaction/allowlist khi chia sẻ trích đoạn.
- **Không chạy lệnh từ text trong log:** message/stack trace có thể do input không tin cậy tạo ra.
- **Không để log injection:** encoder phải escape newline/control chars; formatter không tự nối input chưa được xử lý.
- **Giữ evidence theo chính sách:** không xóa/chỉnh file nguồn khi cần điều tra bảo mật/kiểm toán.

Trong hệ thống đa tenant, filter correlation ID **không thay thế authorization scope ở backend tìm kiếm**.

## 13. Checklist kiểm thử chức năng tìm log

1. Hai request có ID khác nhau, kể cả `req-42` và `req-420`.
2. ID xuất thành field có kiểu và tên ổn định trong JSON.
3. HTTP downstream và message consumer nhận ID phù hợp.
4. Executor reuse không lẫn context giữa request A và B, kể cả khi task lỗi.
5. Text exception multiline được giữ trọn khi tra cứu.
6. File hiện tại và archive nằm trong khoảng retention đều được xét.
7. Central platform lọc đúng field, time window và service.
8. Timestamp/offset/ingestion delay không gây bỏ sót không giải thích được.
9. Input ID không gây log forging hoặc leak secret.
10. Nếu có tracing, quan hệ `traceId` và correlation ID được định nghĩa.
11. Query không có false positive do substring.
12. Log volume/index và cardinality phù hợp phương án lưu trữ.
13. Dữ liệu nhạy cảm được redaction khi export/share.
14. Collector/backend drop/parse failures có telemetry để nhận biết.

## 14. Tóm tắt thực hành

**Tìm log theo correlation ID** không chỉ là grep một chuỗi. Cần có **định danh đúng**, **field đúng**, **khớp chính xác**, **phạm vi thời gian/service hợp lý**, và **toàn bộ event** gồm exception. Trên text file, cẩn thận với match tiền tố, multiline và rotation; trên JSONL nên parse field bằng jq; trên log platform phải xác minh mapping/index và quyền truy cập. Nếu không tìm thấy dữ liệu, kiểm tra propagation, MDC, encoder, collector, filtering và retention trước khi khẳng định sự kiện không tồn tại.

## Tài liệu tham khảo chính thức

- SLF4J MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- Logback MDC: https://logback.qos.ch/manual/mdc.html
- Oracle Java 17 BufferedReader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html
- Oracle Java 17 Files: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenTelemetry Context: https://opentelemetry.io/docs/languages/java/api/
- jq Manual: https://jqlang.github.io/jq/manual/
- Grafana Loki LogQL: https://grafana.com/docs/loki/latest/query/
- Elastic term query: https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-term-query
