# Chọn log level trong Java Core Logging: thiết kế chiến lược ghi log có ý nghĩa

## 1. Tại sao phải chọn log level?

**Log level** (mức độ log) là thuộc tính dùng để phân loại **ý nghĩa vận hành và mức độ cần chú ý** của một sự kiện, đồng thời cho phép logger/backend lọc những record phù hợp trước khi ghi ra console, file, mạng hoặc hệ thống quan sát tập trung. Chọn level tốt giúp nhóm phát triển và vận hành tìm đúng thông tin khi điều tra sự cố, giảm log nhiễu, hạn chế chi phí và tránh biến mọi sự kiện bình thường thành cảnh báo.

Ví dụ Java service xử lý một request có thể có các sự kiện:

```text
INFO  event=order.accepted order_id=42
DEBUG event=payment.request.prepared dependency=payment
WARN  event=payment.retry attempt=1 reason=TIMEOUT
INFO  event=order.completed outcome=SUCCESS duration_ms=112
```

Một lần timeout ở attempt đầu **không đồng nghĩa** request cuối cùng thất bại. Nếu retry thành công, việc ghi WARN cho dấu hiệu suy giảm và INFO cho kết quả hoàn tất có thể phù hợp hơn việc ghi ERROR ngay khi có exception rồi để dashboard báo “request lỗi”. Ngược lại, sau khi hết lượt retry và operation thất bại, event kết thúc có thể được ghi ở ERROR.

**Câu hỏi cốt lõi không phải “đây là dòng code nào?” mà là “sự kiện này nói gì về trạng thái thực tế và cần ai hành động?”**

Chọn level cần đồng thời cân nhắc:

- **Mức độ nghiêm trọng thực sự:** bình thường, chẩn đoán, bất thường có hồi phục, thất bại cuối cùng.
- **Người đọc:** lập trình viên debug, on-call, vận hành hạ tầng, security, audit hoặc business owner.
- **Khả năng hành động:** event báo điều cần điều tra/can thiệp hay chỉ là một bước kỹ thuật.
- **Tần suất và chi phí:** một event mỗi lần deploy khác một event mỗi message trong queue.
- **Điều kiện lưu giữ:** có phải event cần audit đầy đủ, hay được phép filter/sampling?
- **Mức độ nhạy cảm:** dữ liệu trong message/exception/context có được phép đưa vào log không?

Một level không tự cho biết request nào bị ảnh hưởng, nguyên nhân gì hoặc business outcome ra sao. Vì vậy chọn level phải đi cùng **event name, error code, outcome, correlation ID và schema** phù hợp.

## 2. Các level trong SLF4J/Logback/Log4j2 và JUL

### A. Cách hiểu thường dùng trong logging backend Java

| Level thông dụng | Ý nghĩa thực dụng | Ví dụ nên cân nhắc |
| --- | --- | --- |
| **TRACE** | Chi tiết rất nhỏ, thường phục vụ điều tra một đường thực thi cụ thể | State transition nội bộ, nhánh parser, thao tác lặp có kiểm soát |
| **DEBUG** | Thông tin chẩn đoán giúp lập trình viên hiểu quyết định của code | Chọn nhánh xử lý, rule match, lý do cache hit/miss được làm sạch |
| **INFO** | Mốc hoạt động bình thường đáng giữ trong môi trường đang vận hành | Service ready, job completed, business milestone, HTTP completion theo policy |
| **WARN** | Dấu hiệu bất thường, suy giảm hoặc rủi ro **chưa chắc dẫn tới thất bại cuối** | Retry sau timeout, gần vượt quota, fallback được kích hoạt |
| **ERROR** | Một operation/request quan trọng đã thất bại hoặc dịch vụ không thể thực hiện chức năng cần thiết | Không commit được giao dịch, request kết thúc 5xx vì lỗi phía server |
| **FATAL** (nếu backend hỗ trợ) | Lỗi đặc biệt nghiêm trọng, thường khiến thành phần không thể tiếp tục vận hành | Lỗi khởi động không thể khôi phục; mức này không thuộc API SLF4J chuẩn |

Đây là **quy ước thiết kế gợi ý**, không phải luật tuyệt đối: một hệ thống có thể dùng WARN cho validation 4xx đáng ngờ hoặc ERROR cho lỗi bảo mật nghiêm trọng tùy threat model. Quan trọng là **cùng một loại event phải có ngữ nghĩa ổn định qua các service**.

### B. `java.util.logging` (JUL) không có đúng các tên trên

JDK cung cấp `java.util.logging.Level` với các mức phổ biến:

```text
SEVERE   (1000)
WARNING   (900)
INFO      (800)
CONFIG    (700)
FINE      (500)
FINER     (400)
FINEST    (300)
```

Ngoài ra có `Level.OFF` để vô hiệu hóa log và `Level.ALL` để cho phép mọi level ở bước lọc tương ứng. Các giá trị số được nêu ở trên là của **các mức chuẩn trong JUL**; chương trình có thể định nghĩa `Level` riêng, vì vậy đừng coi chúng là một taxonomy bảo mật hoàn chỉnh.

Quy ước gần đúng khi chuyển stack:

| Ý nghĩa | SLF4J | JUL gần tương ứng |
| --- | --- | --- |
| Chi tiết sâu | TRACE | `FINER` / `FINEST` |
| Chẩn đoán | DEBUG | `FINE` |
| Thông tin vận hành | INFO | `INFO` |
| Cảnh báo | WARN | `WARNING` |
| Lỗi | ERROR | `SEVERE` |
| Thông tin cấu hình | Không có level riêng tương ứng | `CONFIG` |

**Không có ánh xạ một-một mặc định được đảm bảo** cho mọi bridge/provider. Ví dụ, `CONFIG` của JUL là mức riêng phục vụ cấu hình, không thể mặc định coi bằng DEBUG. Khi dùng bridge JUL-to-SLF4J hoặc provider khác, kiểm mapping mà bản triển khai đang áp dụng.

### C. Level là ngưỡng lọc, không phải thứ tự ưu tiên nghiệp vụ

Thông thường khi ngưỡng được đặt ở `INFO`, hệ thống giữ các log có severity **INFO và nghiêm trọng hơn**, loại `DEBUG`/`TRACE` (hoặc các mức JUL thấp hơn). Đặt ngưỡng `WARN` sẽ bỏ INFO. Nhưng log có thực sự xuất ra hay không còn phụ thuộc **logger, handler/appender, filter, sampling và output pipeline**.

Đừng hiểu level như một “flag để gửi email/pager tự động”. Alerting nên dựa vào triệu chứng, tỷ lệ lỗi, SLO và điều kiện được thiết kế rõ, thay vì chỉ thấy một dòng ERROR là lập tức gọi người trực.

## 3. Quy tắc quyết định level theo ngữ nghĩa sự kiện

Một cây quyết định đơn giản:

```text
Sự kiện cần ghi nhận?
 |
 +-- Chỉ dùng để theo dõi bước nội bộ/giá trị debug?
 |      -> DEBUG hoặc TRACE, có giới hạn và không chứa secrets
 |
 +-- Hoạt động bình thường, là milestone/summary quan trọng?
 |      -> INFO
 |
 +-- Có dấu hiệu sai lệch, retry/fallback/degradation,
 |   nhưng nghiệp vụ vẫn có thể hoàn thành?
 |      -> WARN, với mã nguyên nhân và scope rõ
 |
 +-- Hành động đã thất bại cuối cùng hoặc hệ thống không
 |   thể thực hiện điều bắt buộc theo hợp đồng?
 |      -> ERROR / JUL SEVERE
 |
 +-- Là security/audit event bắt buộc được lưu bền?
        -> Thiết kế kênh audit riêng và chọn severity theo
           ý nghĩa, không chỉ dựa vào INFO/ERROR.
```

Đây là **hướng dẫn phân tích**, không phải thuật toán máy móc. Chẳng hạn một đợt retry liên tục có thể khiến system degraded nghiêm trọng dù cuối cùng vẫn trả 200; ngược lại một HTTP 404 do người dùng nhập sai path có thể hoàn toàn bình thường và không cần WARN cho từng request.

Khi phân vân, lần lượt trả lời:

1. Nếu record bị tắt trong production, liệu có mất dấu mốc vận hành mà on-call phải biết không?
2. Đây là **kết quả cuối** hay chỉ là lỗi tạm ở một attempt?
3. Có ai cần hành động ngay, cần phân tích xu hướng, hay chỉ cần đọc khi bật chẩn đoán?
4. Sự kiện xảy ra bao nhiêu lần/giây; giữ hết có chịu được không?
5. Có thể thay bằng metric/tracing hoặc summary event mà vẫn đạt mục tiêu không?
6. Event có nghĩa bảo mật, tuân thủ hay trách nhiệm pháp lý phải tách khỏi log lọc theo level không?

## 4. Bảng lựa chọn level theo từng loại sự kiện

| Tình huống | Level thường phù hợp | Giải thích |
| --- | --- | --- |
| Service start, ready, graceful shutdown | INFO | Milestone quan trọng, tần suất thấp |
| Nạp cấu hình hợp lệ | INFO hoặc `CONFIG` (JUL) | Không log secret, chỉ các chi tiết thực sự cần |
| Controller gọi service nào | DEBUG/TRACE hoặc trace span | Chi tiết internal, thường rất nhiều |
| Điều kiện validation thành công | DEBUG nếu cần | Thường không cần ghi mỗi nhánh |
| HTTP 200 bình thường | INFO access completion theo policy hoặc metric | Một event chuẩn hóa tốt hơn nhiều entry/exit logs |
| HTTP 400 do input không hợp lệ | INFO; đôi khi WARN nếu rủi ro rõ | Không mặc định coi client error là server exception |
| HTTP 401/403 | INFO/WARN hoặc security audit riêng | Phụ thuộc threat model, không log token |
| HTTP 404 do route không tồn tại | INFO access log hoặc metric | Tránh WARN/ERROR cho từng scanner request vô nghĩa |
| HTTP 429 rate-limit | INFO/WARN + metric | Đây có thể là policy hoạt động bình thường, hoặc dấu hiệu lạm dụng |
| Một downstream timeout rồi retry thành công | WARN cho attempt bất thường, INFO final completion nếu cần | Không gắn final request là ERROR |
| Retry hết lượt, request cuối 503 | ERROR tại final boundary | Có user impact; đếm final failure riêng |
| Fallback hoạt động nhưng giảm chất lượng | WARN/INFO theo mức ảnh hưởng | Thêm degradation/fallback metric |
| Không thể kết nối DB trong lúc startup | ERROR/SEVERE; FATAL nếu backend có và policy phù hợp | Hậu quả có thể là không sẵn sàng phục vụ |
| Một job batch xử lý xong | INFO summary | Dùng count/duration thay vì INFO từng item |
| Job chạy dài và checkpoint nội bộ | DEBUG hoặc periodic INFO có giới hạn | Chọn cadence rõ, không mỗi record |
| Business invariant bị vi phạm và rollback | ERROR nếu operation thật sự không hoàn tất | Có error code, actor/resource được làm sạch |
| Exception bị catch rồi xử lý bình thường | DEBUG/WARN tùy tác động | Throwable không tự quyết định level |
| Đọc secret, rotate credential, đổi quyền | Audit/security route theo policy | Có thể có INFO/WARN bản sao nhưng không thay thế audit |
| Heartbeat định kỳ của worker | Metric/healthcheck, INFO thưa theo mục đích | Không spam từng giây nếu không có ích |
| Hệ thống log shipper mất kết nối | WARN/ERROR theo mức độ ảnh hưởng + self-metrics | Cần biết logging pipeline có blind spot |

Một API public có lượng request cực lớn **có thể cần access log mỗi request** theo policy; đây không nhất thiết là anti-pattern nếu volume và retention được thiết kế. Ngược lại, “một INFO cho từng item trong vòng lặp” thường là sự nhầm lẫn giữa chi tiết debug và sự kiện vận hành.

## 5. Level của exception: xem kết quả cuối, không chỉ loại Throwable

### A. Cùng một exception nhưng severity khác nhau

Xét `SocketTimeoutException` khi gọi dịch vụ thanh toán:

```text
Attempt 1 timeout, retry còn cơ hội:
  WARN event=payment.attempt.failed outcome=RETRY attempt=1

Attempt 2 thành công:
  INFO event=payment.completed outcome=SUCCESS retries=1

Attempt cuối vẫn timeout, payment request thất bại:
  ERROR event=payment.completed outcome=FAILED
        error_code=DOWNSTREAM_TIMEOUT
```

Tại attempt đầu, WARN thể hiện việc cần theo dõi nhưng chưa chắc người dùng bị ảnh hưởng. ERROR được dùng ở **ranh giới kết quả cuối cùng** khi operation thật sự thất bại. Nếu mỗi tầng log ERROR cùng stack rồi rethrow, on-call sẽ thấy nhiều “lỗi” cho một request, làm sai ước lượng ảnh hưởng.

### B. Exception được bắt và hồi phục

```java
try {
    return remoteClient.fetch();
} catch (TimeoutException ex) {
    // Chỉ là code minh họa; cần remoteClient, fallbackValue và imports.
    logger.warn("event=remote.fallback code=TIMEOUT", ex);
    return fallbackValue;
}
```

Fragment này **không chạy độc lập**; với SLF4J cần logger và dependency. Nếu fallback đáp ứng đúng yêu cầu nghiệp vụ, final outcome có thể là SUCCESS nhưng vẫn nên có metric fallback để thấy dependency degraded. Nếu fallback chỉ trả dữ liệu cũ gây ảnh hưởng chất lượng, WARN + degradation indicator hữu ích.

### C. Lỗi bị chuyển thành HTTP response

Trong Spring MVC, exception handler có thể chuyển `IllegalArgumentException` thành HTTP 400. Việc tồn tại Throwable không có nghĩa server trả 500. Nên phân biệt:

- `http.status_code`: final status mà framework ghi nhận;
- `business.outcome`: thành công/thất bại theo nghiệp vụ;
- `exception.type`: loại lỗi kỹ thuật;
- `error.code`: mã lý do ổn định để tìm log và đo metric.

Không lấy `exception.getMessage()` làm metric label vì cardinality cao và có thể lộ dữ liệu nhạy cảm.

### D. Lỗi rơi vào async worker

Nếu HTTP trả 202 Accepted rồi job nền thất bại sau đó, event ERROR có thể thuộc **job** chứ không phải request HTTP đã hoàn tất. Đừng thay ngược outcome HTTP hoặc gộp hai đơn vị đo. Ghi job ID/correlation và metric job failure tại worker boundary.

### E. Không ghi stack trace ở mọi tầng

Một pattern tốt là **log tại nơi có đủ ngữ cảnh, sau khi đã rõ cách xử lý**. Tầng DAO có thể bọc exception với cause và propagate; service có thể retry/fallback; controller hoặc job worker ghi final failure. Nếu cần event ở nhiều tầng, dùng event names khác nhau và phân biệt `attempt` với `operation`.

## 6. INFO là gì khi triển khai chiến lược log?

INFO phù hợp với những sự kiện:

- Hiếm hoặc có tần suất dự toán được, chẳng hạn service boot, deployment, job summary.
- Hữu ích khi điều tra mà không bật DEBUG, như request completion với route, status, duration và correlation.
- Mô tả **kết quả có nghĩa** thay vì bước kỹ thuật.
- Dễ truy vấn theo event name, outcome, error code; ít phụ thuộc vào câu chữ message.
- Không chứa secret/PII không cần thiết, không log toàn bộ payload thô.

So sánh:

```text
Nhiều INFO rời rạc:
INFO Enter OrderController.create()
INFO Validating...
INFO Calling repository...
INFO Repository returned...
INFO Exiting OrderController.create()

Một sự kiện có cấu trúc:
INFO event=order.created order_id=42 outcome=SUCCESS request_id=req-7 duration_ms=34
```

Với tần suất cao, có thể dùng metric cho số lượng, duration histogram cho latency và trace để mô tả flow. **Không ép INFO thay thế DEBUG/traces**, nhưng cũng không tắt mất sự kiện quan trọng chỉ để giảm chi phí.

Khi chọn INFO cho access log một request, phải xác định ai phát completion event, khi nào request thực sự hoàn tất (kể cả async, exception/404/401), và có tránh duplicate khi gateway + application cùng ghi event không. Không tự coi HTTP 200 là thành công nghiệp vụ nếu API có quy ước error code trong response body.

## 7. WARN: bất thường hoặc suy giảm, chưa chắc đã thất bại

`WARN` / JUL `WARNING` thường nói rằng “đang có điều gì đó không như mong muốn, có khả năng ảnh hưởng hoặc đáng theo dõi, nhưng hành động vẫn có thể hoàn tất”.

Ví dụ hợp lý:

- Retry do network timeout, với attempt và dependency.
- Circuit breaker chuyển OPEN hoặc pool connection gần ngưỡng cạn.
- Fallback được kích hoạt, dữ liệu không còn fresh.
- Lỗi parse record ở một số ít dữ liệu có thể bỏ theo policy, nhưng nên có count/ratio.
- Cache hit ratio giảm hoặc queue backlog tăng **khi vượt ngưỡng có ý nghĩa**.

Cẩn thận với WARN mỗi request cho những tình huống bình thường được dự đoán: client nhập sai email, HTTP 404 do bot quét web, cache miss bình thường, scheduled retry của một hệ thống eventual consistency. Những event này có thể cần metric/INFO/debug hoặc security signal riêng thay vì WARN spam.

Một WARN nên có context cho triage: `event.name`, `reason_code`, `dependency`, `attempt`/`retryable`, `request_id` khi phù hợp. Nếu có thể phát hàng nghìn WARN liên tiếp, cân nhắc aggregation, suppression và metric count, không chỉ đổi chúng sang INFO để tránh alert.

## 8. ERROR: thất bại có ý nghĩa và có owner xử lý

`ERROR` / JUL `SEVERE` thường phù hợp với:

- Request hoặc operation quan trọng **không hoàn thành** theo hợp đồng.
- Service không khởi động, readiness fail hoặc thành phần cốt lõi không thể hoạt động.
- Dữ liệu nghiệp vụ bị rollback do điều kiện lỗi không mong đợi.
- Tác vụ bắt buộc thất bại cuối cùng sau retry và cần điều tra/can thiệp.

Nhưng **ERROR không đồng nghĩa paged incident** và **không đồng nghĩa mọi `Throwable`**. Một request 400 hợp lệ có thể không cần ERROR; một queue batch gặp một record poison có thể được cô lập và xử lý theo policy, WARN nếu chưa ảnh hưởng SLA; một authz denied có thể cần event security dù không phải server error.

Nếu cần ERROR tại cả nguồn dependency và boundary cuối, hãy làm rõ:

- Event ở dependency là `dependency.attempt.failed` hoặc `dependency.call.failed`, đếm theo attempt/call.
- Event ở request là `http.request.completed` với final outcome, đếm theo request.
- Tránh cùng một event name và cùng một metric semantics ở nhiều tầng.
- Ghi stack một lần ở nơi có ngữ cảnh cần điều tra; có thể giữ cause chain mà không nhân bản toàn bộ message khắp nơi.

Với các sự cố lặp nhanh, ERROR flood có thể tự làm logging pipeline quá tải. Cần metrics error rate, suppressed count và cơ chế rate limit/sampling theo policy; **không bỏ các audit records bắt buộc**.

## 9. TRACE và DEBUG: chẩn đoán có mục đích

DEBUG và TRACE giúp hiểu cách code đưa ra quyết định, nhưng thường bị tắt hoặc chỉ bật ở phạm vi hẹp trong production. Ví dụ:

- DEBUG: chọn rule xử lý, kết quả validation ở dạng mã, cache strategy đã chọn.
- TRACE: parser state transitions, chi tiết protocol frames (đã loại secret), các bước cực nhỏ của thuật toán.
- Metric phù hợp hơn: số lần cache hit/miss, latency, retries, queue depth.
- Trace/span phù hợp hơn: một request đi qua nhiều dependency và thời gian của từng bước.

**DEBUG không phải vùng “được phép lộ dữ liệu”**: khi incident, nó có thể được bật và thu thập bởi cùng một pipeline. Không dump request body, auth headers, token hoặc toàn bộ entity chỉ vì đặt level thấp.

Nếu cần bật DEBUG ở production, phải chọn package/service/instance có vấn đề, có quyền phê duyệt, giới hạn thời gian và quan sát log volume. Tránh `root=DEBUG` vĩnh viễn khi service có nhiều thư viện phát log.

## 10. Kỹ thuật lọc: logger level, handler/appender level và filter

### A. Với JUL, có ít nhất hai tầng lọc

Ví dụ logger cấu hình:

```java
Logger log = Logger.getLogger("com.example.payment");
log.setLevel(Level.INFO);
```

Khi đó record `FINE` thường bị bỏ ngay ở logger. Nhưng **để được xuất thật**, record còn phải qua `Handler` với level/filter phù hợp. Nếu logger cho INFO nhưng handler đặt WARNING, INFO vẫn có thể bị loại tại handler.

Một số chi tiết quan trọng:

- `Logger.getLevel()` có thể trả `null`, tức **kế thừa level** từ parent; level hiệu lực không đơn giản là `getLevel()` của logger hiện tại.
- `Handler.setLevel(Level.ALL)` chỉ cho phép handler nhận nhiều mức; nó **không buộc logger phải tạo record đã bị logger level chặn**.
- Logger có thể gửi record tới parent handlers khi `useParentHandlers=true`, gây output nhiều đường hoặc bị lọc khác nhau theo handler.
- Một `Filter` tại logger hoặc handler có thể áp rule bổ sung ngoài level.
- `Level.OFF` tắt ở cấp tương ứng; `Level.ALL` mở rộng, nhưng không thể vượt qua filter/handler/đường output không hoạt động.
- Hành vi phụ thuộc cấu hình `LogManager`, handler hiện có, formatters và runtime.

Dùng level để lọc những events có chủ đích; với audit bắt buộc, không chọn logger INFO chung rồi kỳ vọng mọi môi trường luôn giữ nguyên.

### B. SLF4J và backend

SLF4J là **API facade**, không tự quyết định cách ghi bền, format JSON, async hay retention. Trong các hệ thống phổ biến, Logback hoặc Log4j2 là provider/backend, nơi cấu hình logger levels, appenders, thresholds, additivity và layout.

Đoạn SLF4J minh họa:

```java
logger.trace("event=parser.transition state={}", state);
logger.debug("event=policy.evaluated rule={}", rule);
logger.info("event=payment.completed status={}", status);
logger.warn("event=payment.retry attempt={}", attempt);
logger.error("event=payment.failed error_code={}", code, exception);
```

Đoạn này **không phải file Java độc lập**, cần logger/biến/dependencies. Lời gọi `logger.error` không tự đồng nghĩa throw exception; truyền `Throwable` giúp backend in stack/cause nếu layout cho phép. Kiểm method overload để exception không vô tình trở thành đối số text.

### C. Logback XML: cấu hình level theo package

```xml
<configuration>
  <appender name="STDOUT"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="com.example.payment" level="DEBUG"/>

  <root level="INFO">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
```

Đây là **cấu hình Logback minh họa**, không phải Java thuần; cần dependency, đường dẫn config và backend phiên bản phù hợp. Logger `com.example.payment` có ngưỡng DEBUG, các logger còn lại kế thừa root INFO theo quy tắc Logback. Appender/Filter còn có thể bỏ record; additivity có thể khiến record được xuất qua nhiều appenders nếu cấu hình trùng.

Không nhầm Logback với Log4j2: mỗi backend có schema XML/YAML, tên class và default khác nhau. Với Log4j2, threshold, logger configuration, additivity và appender refs cần được cấu hình theo tài liệu của phiên bản đang chạy.

### D. Spring Boot properties

Nếu Spring Boot sử dụng backend phù hợp:

```properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
logging.level.org.springframework.web=WARN
```

Đây là **mảnh `application.properties`**, không phải ứng dụng Boot đầy đủ. Nó thể hiện ý định: INFO cho ứng dụng nói chung, DEBUG tạm cho một package cụ thể, WARN cho một số framework logs. Cần tránh tắt WARN/ERROR hữu ích của dependencies chỉ vì muốn giảm noise; điều chỉnh dựa vào hành vi quan sát thực tế.

Nếu tổ chức cho đổi level runtime qua actuator/admin endpoint, phải dùng authentication/authorization, giới hạn exposure, ghi change audit và có cách tự phục hồi về cấu hình an toàn. Không khẳng định mọi bản Boot hỗ trợ cùng endpoint hoặc cho đổi level không cần cấu hình.

## 11. Ví dụ Java 17 chạy độc lập: lựa chọn level và hai tầng lọc JUL

Ví dụ sau **chỉ dùng JDK 17**. Nó cho thấy:

1. `INFO`, `WARNING`, `SEVERE` phát khi logger đặt INFO.
2. Message chẩn đoán `FINE` bị tắt, và cách truyền tham số quyết định chi phí tính toán khi level tắt.
3. Bật logger FINE cho phép diagnostic message có supplier xuất hiện.
4. Handler có thể **lọc INFO** ngay cả khi logger đã cho phép nó.
5. Chương trình in stdout cố định để kiểm theo từng bước.

Lưu thành **`LogLevelSelectionDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogLevelSelectionDemo {
    private static final Logger LOG =
            Logger.getLogger("example.level.selection");

    private static String makeDetails(AtomicInteger calls) {
        int n = calls.incrementAndGet();
        return "detail-" + n;
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        LOG.addHandler(sink);

        AtomicInteger eager = new AtomicInteger();
        AtomicInteger lazy = new AtomicInteger();

        try {
            // FINE tắt. Biểu thức nối chuỗi vẫn gọi makeDetails.
            LOG.fine("event=diagnostic " + makeDetails(eager));

            // FINE tắt. Supplier không phải tạo message.
            LOG.log(Level.FINE, () ->
                    "event=diagnostic " + makeDetails(lazy));

            LOG.info("event=service.started outcome=SUCCESS");
            LOG.warning("event=payment.retry attempt=1 reason=TIMEOUT");
            LOG.severe("event=payment.failed outcome=FAILED");

            // Mở DEBUG tương đương cho logger đang xét.
            LOG.setLevel(Level.FINE);
            LOG.log(Level.FINE, () ->
                    "event=diagnostic " + makeDetails(lazy));

            // Logger cho phép INFO, nhưng Handler chặn INFO.
            sink.setLevel(Level.WARNING);
            LOG.info("event=hidden.by.handler");
            LOG.warning("event=handler.warning.only");

            System.out.printf(
                    "COUNTS eager_calls=%d lazy_calls=%d%n",
                    eager.get(), lazy.get());
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LogLevelSelectionDemo.java
java LogLevelSelectionDemo
```

**Stdout chính xác:**

```text
INFO event=service.started outcome=SUCCESS
WARNING event=payment.retry attempt=1 reason=TIMEOUT
SEVERE event=payment.failed outcome=FAILED
FINE event=diagnostic detail-1
WARNING event=handler.warning.only
COUNTS eager_calls=1 lazy_calls=1
```

Giải thích:

- Khi logger INFO, hai `FINE` đầu không được publish. Tuy nhiên ở lời gọi nối chuỗi, Java vẫn đánh giá `makeDetails(eager)` **trước khi** logger kiểm level: `eager_calls=1`.
- JUL `log(Level, Supplier<String>)` cho phép hoãn tạo message nếu logger level đang tắt, nên `lazy` còn 0 ở lần đầu.
- INFO là milestone bình thường, WARNING cho retry và SEVERE cho thất bại cuối. Ví dụ giả định retry và failure có ý nghĩa thuộc operation minh họa; ứng dụng thật cần bảo đảm không ghi ERROR nếu retry đã thành công.
- Sau `LOG.setLevel(Level.FINE)`, supplier được gọi một lần để tạo `detail-1`, record được handler ALL chấp nhận.
- Sau `sink.setLevel(Level.WARNING)`, logger vẫn cho INFO nhưng handler chặn. Vì vậy `event=hidden.by.handler` **không** xuất; WARNING vẫn xuất.
- `setUseParentHandlers(false)` ngăn parent handler in bản sao (thường ra stderr), và Handler tự viết không thêm timestamp/formatter nên output xác định.
- `AtomicInteger` chỉ phục vụ minh họa số lần đánh giá tham số; không phải benchmark CPU, heap hoặc log bytes.

**Giới hạn:** ví dụ có một logger, một handler và chạy tuần tự; không có Logback, SLF4J, MDC, structured JSON, HTTP server, async logging, log shipping hay audit guarantee. Thay đổi level động trong process có nhiều thread có thể ảnh hưởng tất cả request đang chạy; ở production nên dùng quy trình quản trị phù hợp thay vì toggle level tùy ý.

## 12. Đánh giá tham số và chi phí khi chọn level

Level thấp giúp giảm log volume khi bị filter, nhưng **không luôn giúp tránh chi phí tính toán đối số**.

### A. Ghép chuỗi trước lời gọi logger

```java
logger.fine("userState=" + expensiveSnapshot());
```

Ngay cả khi FINE disabled, Java đánh giá `expensiveSnapshot()` trước khi gọi method. Nếu snapshot phải serialize một đối tượng lớn, lộ secret hoặc gọi IO, việc chuyển message sang DEBUG không giải quyết chi phí.

### B. Supplier của JUL

```java
logger.log(Level.FINE, () -> "userState=" + expensiveSnapshot());
```

Khi FINE bị logger loại, supplier không bị đánh giá để tạo message. Nhưng một khi được bật, tạo snapshot vẫn tốn tài nguyên. Bản thân việc **khởi tạo supplier/lambda** có thể có chi phí khác nhau theo capture/JIT; không tự tuyên bố chi phí bằng 0.

### C. Parameterized logging của SLF4J

```java
logger.debug("result={}", expensiveResult());
```

Parameterized logging tránh nối string pattern trực tiếp ở call site, nhưng **`expensiveResult()` vẫn chạy** trước khi gọi `debug`. Với biểu thức đắt, guard có thể cần:

```java
if (logger.isDebugEnabled()) {
    logger.debug("result={}", expensiveResult());
}
```

Các đoạn SLF4J này cần dependency và logger; không phải chương trình độc lập. Trong SLF4J 2.x, fluent API cũng có supplier-based methods phù hợp (tùy overload) để hoãn argument:

```java
logger.atDebug()
      .addArgument(() -> expensiveResult())
      .log("result={}");
```

Phải kiểm phiên bản SLF4J và provider, không nhầm với API khác. Đừng sử dụng supplier như lý do để dump data nhạy cảm: khi DEBUG được bật, dữ liệu có thể vẫn được xuất và lưu.

### D. Tối ưu thế nào?

- Tránh tạo chuỗi lớn và `toString()` của entity nhạy cảm nếu không cần.
- Không serialize toàn bộ request/response object ở INFO mặc định.
- Chọn event nhỏ, có schema, ghi mã lỗi và ID có kiểm soát.
- Đo allocations/op, CPU, p95/p99 latency và throughput khi logging bật/tắt bằng benchmark đại diện (có thể dùng JMH).
- Kiểm chi phí encoder, disk/network I/O, async queue và Collector, không chỉ thời gian tạo message.

Một logger “disabled” chưa đồng nghĩa mọi tham số rẻ; một async appender cũng chưa đồng nghĩa sẽ không block/drop khi quá tải.

## 13. Gắn level với structured event, không chỉ văn bản

Một completion event có cấu trúc:

```json
{
  "timestamp": "2026-01-01T00:00:01Z",
  "severity": "INFO",
  "event.name": "http.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "http.method": "POST",
  "http.route": "/api/orders",
  "http.status_code": 201,
  "duration_ms": 34.5,
  "outcome": "SUCCESS",
  "request_id": "req-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây là **schema minh họa do ứng dụng thiết kế**, không phải output mà mọi Java logger hoặc OpenTelemetry SDK tự sinh. Cấu trúc thực tế có thể có log record attributes, resource attributes và schema khác nhau theo backend/phiên bản.

Để chọn level và truy vấn nhất quán, nên có:

- **`event.name`**: định danh sự kiện có ý nghĩa ổn định.
- **`severity`**: mức ưu tiên diễn giải; tách với HTTP status.
- **`outcome`**: SUCCESS, FAILED, RETRY, DENIED, DEGRADED... theo contract.
- **`error.code`/`exception.type`**: lý do/loại lỗi có thể lọc, không phụ thuộc exact message.
- **`service.name`**, environment, version: biết ở đâu/phiên bản nào phát sinh.
- **`request_id`/`trace_id`**: liên kết log và trace của cùng request/operation.
- **`duration_ms`/`attempt`**: số đo có đơn vị và phạm vi rõ.
- **Trường nhạy cảm được loại**: không log token/password, PII quá mức, raw URL/query chứa secret.

Với metrics, tag/label phải có số giá trị hữu hạn: service, route template, outcome, error code. Không đưa request ID, trace ID, order ID hoặc exception message thành metric label.

### Correlation không sửa được lựa chọn level sai

Có `trace_id` giúp mở đúng request nhưng không làm một dòng INFO trong từng vòng lặp trở nên hữu ích. Ngược lại, một WARN/ERROR không có reason code, operation và scope sẽ khó điều tra. Cần **chọn đúng event và severity**, sau đó mới bổ sung correlation.

## 14. Chiến lược chọn level theo môi trường

| Môi trường/mục tiêu | Thường cân nhắc | Điều không nên giả định |
| --- | --- | --- |
| Local development | DEBUG/TRACE cho code đang phát triển | DEBUG ở mọi thư viện luôn an toàn/nhanh |
| Automated test | INFO/WARN mặc định; DEBUG theo test thất bại | Mức log quyết định pass/fail của test |
| Staging | INFO + DEBUG tạm ở một số component | Traffic thấp sẽ phản ánh chi phí production |
| Production bình thường | INFO milestones, WARN/ERROR có ý nghĩa, DEBUG/TRACE lọc | Mọi INFO đều đáng giữ hoặc mọi WARN phải page |
| Production incident | Bật DEBUG có giới hạn/TTL/owner | Đổi root DEBUG vĩnh viễn là cách duy nhất |
| Audit/security bắt buộc | Kênh/sink riêng theo hợp đồng lưu bền | INFO logger luôn đầy đủ hoặc không bị sampling |

Một policy điển hình:

```text
Root logging: INFO
Dependency/framework noisy packages: WARN khi có căn cứ
Ứng dụng:
  - INFO: readiness, business/HTTP completion theo policy
  - WARN: recoverable degradation, retry/suppression summary
  - ERROR: final failure tại operation boundary
  - DEBUG/TRACE: disabled mặc định, bật phạm vi hẹp khi cần

Audit:
  - không phụ thuộc root INFO sampling/filters
  - durability, retention, access control theo yêu cầu riêng
```

Không có một cấu hình tối ưu cho mọi ứng dụng. Service nhận hàng triệu requests/giây và job batch chạy một lần/ngày có volume profile khác nhau. Chọn policy dựa trên SLO, giá trị điều tra, traffic, backend quota, yêu cầu pháp lý và ngân sách.

### Đổi level động an toàn

Cần có:

1. Quyền phê duyệt hoặc kiểm soát người đổi level.
2. Scope chính xác (package, class, instance, pod, trace scope nếu stack hỗ trợ).
3. TTL/rollback để không giữ DEBUG mãi.
4. Giới hạn log volume, queue, disk, ingest rate.
5. Redaction và field allowlist **áp dụng cho mọi level**.
6. Tracking thay đổi cấu hình để điều tra ai bật logging chi tiết.
7. Quan sát metrics trước/sau: bytes/s, events/s, dropped count, latency impact.

Khi tăng mức chi tiết trong production, có thể thay đổi hiệu năng và privacy; không làm thử nghiệm trên toàn cluster mà không có đánh giá rủi ro.

## 15. Log level không thay thế log sampling và retention policy

Severity và sampling giải quyết hai vấn đề khác nhau:

- **Level filtering:** bỏ những event thuộc mức thấp hơn ngưỡng tại logger/handler/backend.
- **Sampling:** giữ một tỷ lệ event theo policy, có thể theo request, event type hoặc trace.
- **Rate limiting/suppression:** giới hạn số log tương tự trong một cửa sổ, có count bị ẩn.
- **Aggregation:** thay nhiều event chi tiết bằng summary/counters.
- **Retention:** quyết định record đã ingest được giữ bao lâu.
- **Audit durability:** quyết định record quan trọng được lưu bền như thế nào, không chỉ giữ ở một level.

Ví dụ có 50.000 retry warnings/phút do một dependency lỗi có thể gây quá tải. Nếu tổ chức cho phép, có thể giữ một số event mẫu, gom thành summary và dùng counter `retry_attempts_total` để vẫn đo chính xác quy mô. Nhưng **không áp sampling tùy tiện lên event bắt buộc theo audit** hoặc dùng log sampled để suy ra tỷ lệ chính xác khi chưa có phương pháp thống kê phù hợp.

Khi giảm verbosity, phải bảo đảm còn tín hiệu quan trọng: HTTP failures, queue drops, dependency health, outage, audit, log pipeline errors và request metrics. Chỉ thấy “ERROR logs giảm” không đủ kết luận service khỏe; nó có thể do logger tắt hoặc agent không gửi được.

## 16. Chọn level trong hệ thống web và microservices

Một request đi qua gateway → auth filter → controller → service → repository → downstream client. Mỗi tầng đều có thể log, nhưng không nên mỗi tầng phát một `INFO request started` rồi một `INFO request completed` không phân biệt.

Thiết kế có thể gồm:

1. **Gateway:** access event ở edge, method/route/status/duration/trace context.
2. **Application HTTP boundary:** completion event theo policy, final outcome và correlation.
3. **Service nghiệp vụ:** event chuyển trạng thái quan trọng, ví dụ `payment.authorized` hoặc `order.cancelled`.
4. **Dependency call wrapper:** WARN cho retry/fallback bất thường; metric dependency attempts/errors.
5. **Exception handler:** ERROR cho request/operation thất bại cuối khi appropriate; tránh cùng exception bị log ở mọi layer.
6. **Audit/security path:** event xác thực/đổi quyền có actor đã xác minh, không dựa vào level chung.

**Một request có thể tạo nhiều log đúng nghĩa.** Mục tiêu là tránh bản ghi trùng vô ích và phân biệt rõ event names/measurement units. Nên dùng route template thay vì raw URI chứa ID động; giữ request ID/trace ID trong logs/traces, không gắn vào metric label.

Với Servlet/Spring MVC, error 404 hoặc auth rejection có thể xảy ra trước controller; nếu chỉ ghi log trong controller sẽ bỏ sót. Với request async/WebFlux, completion có thể xảy ra sau lúc handler trả control; chọn hook phù hợp để không log sai outcome/latency hoặc ghi trùng khi dispatch.

## 17. Chi phí và tác động của mức log tới sản xuất

Một ứng dụng tạo 2.000 requests/giây, mỗi request sinh 5 INFO events, mỗi event ~400 bytes:

```text
events/s = 2.000 × 5 = 10.000
bytes/s  = 10.000 × 400 = 4.000.000
bytes/day = 4.000.000 × 86.400
          = 345.600.000.000 bytes
          ≈ 345,6 GB/day (đơn vị thập phân)
```

Nếu giảm còn một completion event/request cùng kích thước giả định:

```text
events/s = 2.000
bytes/day = 2.000 × 400 × 86.400
          = 69.120.000.000 bytes
          ≈ 69,12 GB/day
```

Đây là **ước lượng bytes thô**, chưa tính metadata/index/replication/compression/network retries và retention. Không lấy ví dụ làm cam kết tiết kiệm tiền. Chi phí thực cần đo từ sink và backend.

Quan trọng hơn, log flood có thể khiến queue đầy hoặc disk full đúng lúc xảy ra sự cố, làm **WARN/ERROR bị chậm hoặc mất**. Vì vậy độ lớn của INFO không chỉ là chuyện chi phí mà còn là năng lực giữ tín hiệu quan trọng.

Để đánh giá, theo dõi:

- `log_events_total` theo event name/severity/service.
- `log_bytes_total` hoặc throughput encode/ingest.
- `logs_dropped_total`, queue depth, exporter errors, oldest event age.
- CPU, allocations, GC pauses, throughput, p95/p99 latency khi thay level.
- Chi phí ingest/index/storage và thời hạn retention.
- Tỷ lệ ERROR/WARN có thể tìm theo error code và gắn với request/trace.
- Mức độ hữu ích cho incident: có bao nhiêu query/triage thực sự cần dòng đó?

Tên metrics trên là gợi ý, không có sẵn trong mọi logging stack.

## 18. Bảo mật và audit khi chọn level

**Không coi DEBUG/TRACE là an toàn để ghi secret.** Một dòng log chứa mật khẩu hoặc token là rủi ro dù ở level nào. Nó có thể được bật khi incident, giữ ở file local, queue, Collector, cloud backend hoặc backup.

Không đưa những dữ liệu sau vào log nếu không có mục đích và chính sách xử lý cụ thể:

- Plaintext password, API key, access token, refresh token, session cookie, private key.
- Request body chứa thông tin cá nhân/thanh toán hoặc dữ liệu nhạy cảm.
- Raw URL/query string có signed token/email; raw path có bí mật trong segment.
- Exception message/stack có thể chứa SQL, payload hoặc credential.
- Thông tin người dùng/tenant quá chi tiết khi event chỉ cần error code/route.

Dùng structured encoder có escaping để phòng log injection; validate field do client cung cấp để không giả mạo level, actor hoặc outcome. Áp dụng least-privilege permissions cho quyền đọc/search/export và retention phù hợp từng lớp log.

**Audit** có mục tiêu khác operational log: cần truy trách nhiệm ai làm gì với đối tượng nào và kết quả ra sao. Có thể phải ghi cả thao tác thành công và denied, với mức lưu bền/retention đặc biệt. Đặt `logger.info("role changed")` không bảo đảm event còn tồn tại nếu root INFO bị tắt, async queue drop hoặc service crash. Nếu bắt buộc, sử dụng audit writer/outbox hoặc lưu trữ có hợp đồng bền/atomicity thích hợp.

## 19. Thử nghiệm lựa chọn level trong unit/integration test

| Kịch bản | Kỳ vọng |
| --- | --- |
| INFO logger nhận INFO/WARNING/SEVERE | Những event được cấu hình output xuất |
| FINE/DEBUG ở ngưỡng INFO | Diagnostic record không xuất |
| Lazy Supplier khi FINE disabled | Không tạo payload đắt |
| Eager concatenation khi FINE disabled | Biểu thức tính trước lời gọi vẫn chạy |
| Handler đặt WARNING dù logger cho INFO | INFO bị handler lọc |
| Retry thành công | WARN/metric retry, không có final request ERROR giả |
| Hết retry và final failure | ERROR đúng một lần ở boundary, đủ error code/context |
| HTTP 400 validation bình thường | Không mặc định log server ERROR |
| HTTP 500 do exception | ERROR có request ID/trace ID và exception context khi cần |
| 404 hoặc 401/403 trước controller | Log/security event xuất theo policy phù hợp |
| Job nền lỗi sau HTTP 202 | Job failure log riêng, không thay outcome HTTP đã trả |
| Backend async queue đầy | Drop/block/backpressure có metric và cảnh báo |
| Logger parent/additivity | Không phát duplicate records ngoài ý muốn |
| Dynamic level chỉ bật package cần điều tra | Không mở DEBUG toàn root bất ngờ |
| Log chứa newline/secret | Encoder/validation đúng, không lộ token ở bất kỳ level nào |
| Audit event qua filter/sampling | Vẫn có cơ chế bền và xác minh theo hợp đồng riêng |
| Multi-instance và thread pool | Correlation không lẫn, logger settings vận hành nhất quán |

Có thể kiểm bằng in-memory/test appender hoặc JUL Handler tùy biến để assert level và số event; integration test phải xác nhận encoder, Collector và backend nhận đúng field. Với async logger, dùng điều kiện chờ/flush có timeout phù hợp, không chỉ `Thread.sleep(1000)` rồi coi như đã ingest.

### Cách đánh giá một event mới trong code review

Khi thấy một lời gọi `logger.info/warn/error` mới, hỏi:

1. Sự kiện này là **final outcome** hay một bước trong chuỗi xử lý?
2. Level có khớp mức độ ảnh hưởng và conventions của hệ thống?
3. Nếu được ghi trên mỗi request/item, dự kiến volume bao nhiêu?
4. Message có mã ổn định và correlation để tìm lại không?
5. Có trùng log ở layer khác hoặc metric/trace đã đủ thông tin chưa?
6. Khi level bị tắt, code có vẫn tạo payload đắt/secret không?
7. Có thuộc security/audit phải ghi độc lập với root logger không?
8. Khi thay đổi cấu hình level, có nguy cơ mất sự kiện cần thiết không?

## 20. Sai lầm phổ biến khi chọn log level

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Log mọi thứ ở INFO | Nhiễu, tốn storage, che tín hiệu | INFO cho milestone/completion/summary có ý nghĩa |
| Dùng ERROR cho mọi exception đã catch | Retry/fallback thành lỗi giả | Chọn level theo final outcome |
| Dùng WARN cho mọi 404 hoặc cache miss | Alert fatigue, metric méo | Access log/metric; WARN khi thật sự bất thường |
| In toàn bộ stack ở mọi tầng | Duplicate logs và chi phí cao | Ghi stack ở boundary có ngữ cảnh |
| DEBUG nhưng nối chuỗi có `expensiveCall()` | Tốn CPU ngay cả khi level tắt | Supplier/guard đúng API |
| Coi handler ALL sẽ in cả FINE | Logger vẫn có thể lọc FINE | Kiểm cả logger lẫn handler |
| Chỉ đọc `getLevel()` và cho rằng là effective level | Có thể null/kế thừa | Kiểm parent config và handler chain |
| Đổi root DEBUG toàn production | Bùng nổ volume/PII | Scope hẹp, TTL, quyền và rollback |
| Dùng severity làm SLO duy nhất | Log volume không là tỷ lệ lỗi request | Metrics tại measurement boundary |
| Dùng request/trace ID làm metric labels | High-cardinality series | IDs trong log/trace; labels bounded |
| Coi WARN/ERROR tự tạo pager đúng | Nhiều cảnh báo không actionable | Alert theo tỷ lệ, impact, SLO, dedup |
| Dùng INFO thay audit storage | Mất log khi filter/drop/crash | Audit path có durability riêng |
| Ghi secret ở DEBUG vì “bình thường tắt” | Lộ khi bật hoặc ở sink khác | Redaction/data minimization mọi level |
| Quên appender additivity/filter | Missing hoặc duplicate events | Test pipeline thực |
| Bỏ INFO access completion cần thiết | Mất khả năng điều tra request | Giữ event có mục đích, cân nhắc throughput |
| Không kiểm khi collector mất mạng | Log im lặng nhưng service vẫn chạy | Self-metrics và end-to-end canary |

## 21. Checklist áp dụng vào chiến lược logging Java

- [ ] Team đã định nghĩa rõ TRACE/DEBUG/INFO/WARN/ERROR và trường hợp ngoại lệ theo nghiệp vụ?
- [ ] INFO dành cho mốc/summary/completion có giá trị thay vì từng bước code?
- [ ] WARN thể hiện bất thường/retry/degradation còn ERROR gắn với final failure thực?
- [ ] Có phân biệt lỗi cấp attempt, operation, HTTP request và async job?
- [ ] Mỗi loại event có owner, event name, error code và dữ liệu đủ cho triage?
- [ ] Có tránh log rồi rethrow ở nhiều tầng dẫn tới stack trùng?
- [ ] Có chọn level theo request outcome/status thực tế thay vì chỉ dựa `Throwable`?
- [ ] Biết mapping JUL `FINE/INFO/WARNING/SEVERE` với stack logging và bridge đang dùng?
- [ ] Đã kiểm logger, handler/appender, filter, additivity và inheritance để level thực sự hoạt động?
- [ ] Các tham số đắt khi level disabled dùng Supplier/guard phù hợp, không chỉ nối String?
- [ ] DEBUG/TRACE mặc định được giới hạn và có cơ chế bật tạm theo package với TTL/rollback?
- [ ] Có dự toán bytes/s, log volume, queue/backpressure, retention và chi phí ingest?
- [ ] Không ghi password/token/PII quá mức trong bất kỳ level nào?
- [ ] Có structured logging với service/environment, outcome, route, request/trace ID để tìm kiếm?
- [ ] Metric labels tránh ID động; request/error SLIs được đo riêng với log line counts?
- [ ] Security/audit records bắt buộc có tuyến lưu giữ không phụ thuộc sampling/level chung?
- [ ] Đã test INFO/DEBUG/WARN/ERROR, exception retry, async, handler filtering và logging pipeline failure?
- [ ] Có canary/self-metrics để phát hiện log mất hoặc không search được?

**Kết luận:** lựa chọn log level không chỉ là chọn method `info()`, `warn()` hay `error()`. Nó là một phần của **chiến lược quan sát**: xác định **sự kiện có ý nghĩa gì, ai cần chú ý và khi nào**, rồi chọn severity, schema, frequency, sampling và retention phù hợp. Trong Java, hãy nhớ cả logger và handler/appender đều có thể lọc; exception cần được phân loại theo **outcome cuối cùng**; DEBUG/TRACE không được chứa secret; INFO chỉ giữ mốc đáng quan sát; WARN/ERROR phải giúp điều tra chứ không tạo nhiễu. Khi conventions nhất quán, log sẽ tìm kiếm được, đáng tin và hỗ trợ metrics/traces hiệu quả.
