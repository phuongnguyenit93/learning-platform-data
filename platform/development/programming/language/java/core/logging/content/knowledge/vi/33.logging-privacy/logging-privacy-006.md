# Redaction trong Java Logging: bảo vệ dữ liệu riêng tư khi ghi log

## 1. Redaction là gì và tại sao cần thiết?

**Redaction** là quá trình **loại bỏ, thay thế hoặc che nội dung nhạy cảm trước khi bản ghi được cung cấp cho nơi không được phép nhìn thấy dữ liệu gốc**. Trong logging Java, mục tiêu là giúp hệ thống vẫn có thông tin điều tra sự cố mà không đưa mật khẩu, access token, thông tin thanh toán, dữ liệu cá nhân hoặc nội dung nghiệp vụ bí mật vào console, file, collector, dashboard hay kho lưu trữ.

Ví dụ đầu vào có thể là:

~~~text
event=login_rejected email=alice@example.test authorization=Bearer sample-token
~~~

Bản ghi được phép xuất trong một chính sách giả định:

~~~text
event=login_rejected email=[REDACTED] authorization=[REDACTED]
~~~

Một số hệ thống chọn **không ghi hai trường nhạy cảm** ngay từ đầu; điều đó thường tốt hơn việc lấy nguyên văn rồi che lại, vì dữ liệu gốc không phải đi qua pipeline logging. Trong trường hợp vẫn cần biết trường có mặt hay không, có thể ghi cờ boolean hoặc giá trị trạng thái được phê duyệt thay cho raw value.

Redaction không đơn thuần là thay ký tự bằng dấu sao. Nó đòi hỏi hiểu **trường nào nhạy cảm, ai được phép xem, giá trị có thể xuất hiện ở đâu, lớp nào chịu trách nhiệm xử lý, và cách kiểm chứng rằng dữ liệu gốc không lọt vào sink**.

Cần lưu ý rằng mức log **INFO/WARN/ERROR** không phân biệt dữ liệu an toàn hay nhạy cảm. Một log ERROR chứa exception message có mật khẩu vẫn có thể làm lộ bí mật. Khi sản phẩm được mở rộng sang nhiều instance, các bản sao của cùng một sự kiện có thể đi tới nhiều hệ thống, khiến tác động rò rỉ lớn hơn.

## 2. Phân biệt redaction, masking, suppression, pseudonymization và encryption

Các kỹ thuật này liên quan nhưng **không có cùng tính chất bảo vệ**:

| Kỹ thuật | Cách xử lý | Ví dụ | Điều cần hiểu |
| --- | --- | --- | --- |
| **Suppression / omission** | Không xuất trường | Không ghi Authorization header | Ưu tiên nếu trường không cần thiết cho vận hành |
| **Full redaction** | Thay toàn bộ nội dung bằng marker cố định | email=[REDACTED] | Không thể phục hồi giá trị từ chính marker |
| **Masking** | Chỉ che một phần | phone=******1234 | Phần còn lại vẫn có thể nhận diện người dùng |
| **Pseudonymization** | Thay định danh bằng giá trị thay thế | accountRef=acct-token-27 | Có thể liên kết các sự kiện; thường vẫn là dữ liệu có thể tái nhận diện |
| **Tokenization** | Dùng token liên kết tới giá trị ở vault riêng | customerToken=tkn-... | Khả năng đảo ngược phụ thuộc vault và quyền truy cập |
| **Hashing** | Tạo digest từ giá trị | emailHash=... | Giá trị có miền nhỏ dễ bị đoán bằng dictionary attack |
| **Keyed HMAC** | Tính digest bằng khóa bí mật | subjectRef=HMAC(key, identifier) | Hữu ích cho correlation có kiểm soát, nhưng cần bảo vệ khóa |
| **Encryption** | Mã hóa có thể giải mã bởi người giữ khóa | encryptedPayload=... | Không tương đương redaction; plaintext có thể bị khôi phục |

**Ẩn bớt một vài ký tự chưa chắc đủ an toàn.** Ví dụ mã bưu chính, ngày sinh hoặc bốn chữ số cuối của số thẻ đôi khi có thể kết hợp với nguồn khác để nhận diện. Với yêu cầu giảm thiểu dữ liệu, thường nên **bỏ trường hoặc dùng marker** hơn là giữ những phần còn lại không cần thiết.

**Hash không mặc định ẩn danh.** Email, số điện thoại hoặc mã khách hàng có thể bị tấn công vét cạn/tra cứu từ điển nếu dùng hash không khóa. HMAC với khóa riêng giúp giảm một số nguy cơ, nhưng ID dẫn xuất vẫn có thể là dữ liệu cá nhân theo ngữ cảnh, vẫn cần retention và kiểm soát truy cập. Đừng đặt HMAC key hoặc khóa mã hóa trong log.

**Redaction không sửa được bản log đã bị phát tán.** Nếu một token đã tới collector, xóa nó khỏi màn hình dashboard không đồng nghĩa các bản sao trong index, archive, export và backup đều đã được xử lý.

## 3. Phân loại dữ liệu trước khi viết chính sách logging

Không thể redact chính xác nếu không biết trường nào thuộc loại nào. Nên định nghĩa data classification gắn với source và mục đích của log:

| Loại dữ liệu | Ví dụ | Chính sách logging thường phù hợp |
| --- | --- | --- |
| Metadata vận hành ít nhạy cảm | eventCode, service, module, outcome | Ghi nếu có ích và được chuẩn hóa |
| Technical correlation ID | requestId, traceId, jobId | Có thể giữ khi được cấp an toàn và có policy truy cập |
| Định danh cá nhân | email, phone, userId, IP address | Hạn chế, redact, tokenization hoặc pseudonymization tùy mục đích |
| Nội dung tự do do user cung cấp | search text, comment, filename, request body | Mặc định không log raw; chỉ lấy trường cần thiết và đã kiểm soát |
| Authentication/session data | password, cookie, Authorization header, access/refresh token | Không log giá trị gốc |
| Dữ liệu tài chính | PAN, CVV/CVC, thông tin tài khoản | Không ghi raw; tuân thủ chính sách chuyên biệt |
| Business secrets | API key, private key, connection password, signed URL | Không ghi gốc |
| Error/exception data | exception message, SQL statement, stack trace | Kiểm tra khả năng chứa giá trị nhạy cảm trước khi phát |
| Audit metadata | loại hành động, principal reference được phê duyệt | Ghi theo chính sách audit riêng, tối thiểu hóa dữ liệu |

**Không coi dữ liệu từ database hoặc dependency là đáng tin cậy tuyệt đối.** Một tên hiển thị đã được user lưu vào cơ sở dữ liệu vẫn là dữ liệu do user kiểm soát. Một exception message của HTTP client có thể chứa URL kèm query token, dù exception không được tạo trực tiếp từ request.

Cũng cần kiểm tra các field thường phát sinh ngoài ý muốn: **toString() của DTO/entity**, serialized request body, ORM SQL parameters, HTTP client debug logs, access log, security filter, message payload và MDC context.

Đừng xây một “danh sách secret toàn cầu” rồi mặc định mọi nơi đều an toàn. Ngoài các giá trị cố định, còn có trường động do dịch vụ mới hoặc thư viện bên thứ ba tạo; nên phối hợp **schema allowlist** với kiểm soát các nguồn ít tin cậy.

## 4. Ưu tiên data minimization và allowlist ở nguồn

Thứ tự thiết kế nên là:

1. **Không tạo log chứa dữ liệu không cần thiết.**
2. Chỉ đưa vào log **những trường đã được cho phép** bằng schema hoặc API kiểu hóa.
3. **Redact/mask** trường nhạy cảm nếu cần ghi thông tin về sự hiện diện/trạng thái.
4. Dùng **encoder có cấu trúc** để bảo toàn ranh giới field.
5. Thêm **lọc/redaction ở collector** như lớp bảo vệ bổ sung, không làm tuyến duy nhất.
6. Áp dụng **quyền truy cập, retention, audit và kiểm thử** trên mọi nơi nhận.

Ví dụ tránh:

~~~java
logger.info("Incoming user={}", userDto);
logger.debug("Request body: {}", requestBody);
logger.error("Authentication failed, token={}", authorizationHeader);
~~~

Đây là **đoạn minh họa tích hợp**, không phải chương trình hoàn chỉnh. Nếu userDto.toString() hoặc requestBody chứa PII/secret, một lệnh logger có thể phát toàn bộ dữ liệu. Với dòng debug, dữ liệu vẫn có thể được tính toán hoặc chuẩn bị trước khi logger lọc event; và DEBUG có thể được bật tạm thời ở production.

Thay vào đó, chọn các event code và trường ít nhạy cảm, ví dụ:

~~~java
logger.warn("event={} requestId={} reason={}",
        "login_rejected", validatedRequestId, "invalid_credentials");
~~~

**validatedRequestId** trong ví dụ phải thực sự được tạo hoặc kiểm tra trước khi ghi; tên biến không tự làm dữ liệu an toàn. Với các trường thuộc danh mục cố định như event/reason, nên dùng enum hoặc tập giá trị cho phép, tránh đưa nguyên thông điệp do người dùng cung cấp vào nơi dùng để phân loại cảnh báo.

## 5. Redaction ở đâu trong pipeline?

~~~text
User input / message / dependency
       |
       v
Ứng dụng Java: validate, chọn field, omit/redact ở nguồn
       |
       v
SLF4J/JUL/Log4j 2: tạo event, gắn MDC, Throwable
       |
       v
Encoder/Appender: serialize field và kiểm soát output
       |
       v
stdout / file / network
       |
       v
Collector: parse, filter, redact bổ sung, route
       |
       v
Storage / SIEM / dashboard / export / archive
~~~

Các vị trí có ưu và nhược điểm:

| Vị trí | Lợi thế | Hạn chế |
| --- | --- | --- |
| **Business/service code** | Biết ý nghĩa field, có thể không tạo secret trong log | Đòi hỏi kỷ luật code review, khó bao phủ thư viện khác |
| **Logging wrapper / structured event API** | Chính sách chung, testable, thống nhất schema | Có thể bị bypass nếu code gọi logger khác |
| **Encoder / formatter / appender** | Che ở đầu ra của provider dùng chung | Có thể không thấy cấu trúc gốc nếu tất cả đã gộp thành String |
| **Collector / processor** | Bổ sung bảo vệ với nhiều service, quản lý tập trung | Secret đã rời ứng dụng, có thể có raw copy trên stdout/file/queue |
| **Dashboard / query view** | Giới hạn dữ liệu hiển thị cho nhóm người xem | Không xóa secret khỏi backend hoặc bản sao trước đó |

Nguyên tắc: **redact càng gần nguồn càng tốt**. Nếu một HTTP token raw đã được ghi vào console rồi collector mới che, token vẫn có thể còn trong runtime log, container log, file tạm, network buffer hoặc pipeline debug. Collector hữu ích để phòng vệ nhiều lớp, không thay thế việc hạn chế log raw từ Java application.

Khi có nhiều sink, phải kiểm thử **từng sink**: console, rolling file, async appender, collector, tracing exporter và hệ thống báo lỗi bên thứ ba có thể đi theo các tuyến khác nhau.

## 6. Java 17 chạy độc lập: allowlist và redaction trước khi xuất log

Ví dụ sau chỉ dùng Java SE 17 để minh họa cách **xây bản ghi an toàn từ dữ liệu đầu vào**, không đưa trực tiếp raw map vào output. Chương trình lấy event và requestId theo một contract hữu hạn, còn email/Authorization nếu xuất hiện chỉ được biểu diễn bằng marker cố định.

Tạo file **RedactionDemo.java**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public class RedactionDemo {
    private static final Set<String> EVENTS =
            Set.of("login_rejected", "payment_failed");
    private static final Pattern REQUEST_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static String safeEvent(String candidate) {
        return EVENTS.contains(candidate) ? candidate : "unknown";
    }

    private static String safeRequestId(String candidate) {
        return candidate != null && REQUEST_ID.matcher(candidate).matches()
                ? candidate : "invalid";
    }

    private static String redactedPresence(
            Map<String, String> input, String key) {
        return input.containsKey(key) ? "[REDACTED]" : "[ABSENT]";
    }

    private static String safeRecord(Map<String, String> input) {
        return "event=" + safeEvent(input.get("event"))
                + " requestId=" + safeRequestId(input.get("requestId"))
                + " email=" + redactedPresence(input, "email")
                + " authorization="
                + redactedPresence(input, "authorization");
    }

    public static void main(String[] args) {
        Map<String, String> received = Map.of(
                "event", "login_rejected",
                "requestId", "req-42",
                "email", "alice@example.test",
                "authorization", "Bearer sample-token");

        String record = safeRecord(received);
        System.out.println(record);
        System.out.println("secretAbsent="
                + (!record.contains("alice@example.test")
                && !record.contains("sample-token")));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac RedactionDemo.java
java RedactionDemo
~~~

Stdout chính xác:

~~~text
event=login_rejected requestId=req-42 email=[REDACTED] authorization=[REDACTED]
secretAbsent=true
~~~

Giải thích:

1. **Map.of** chỉ tạo dữ liệu giả lập cho chương trình minh họa, không tương đương một request object hay logging provider.
2. **safeEvent** cho phép đúng hai event code cố định; các giá trị khác trở thành unknown.
3. **safeRequestId** chỉ chấp nhận chữ/số, dấu gạch dưới và gạch ngang, dài tối đa 64 ký tự. Đây là grammar minh họa; ứng dụng thật cần hợp đồng ID phù hợp.
4. **redactedPresence** không đọc giá trị email/authorization; nó chỉ xem key có tồn tại rồi xuất marker. Bằng cách này, raw secret không được nối vào message.
5. **secretAbsent=true** kiểm tra bản ghi không chứa hai giá trị thử nghiệm. Nó **không chứng minh mọi dữ liệu bí mật ngoài đời đều được phát hiện**; chương trình chủ động chọn trường và phải được mở rộng khi schema thay đổi.
6. Output dùng **System.out.println** để học nguyên lý; trong ứng dụng thật, nên dùng logging framework với structured fields và một schema redaction rõ ràng, thay vì tự xây nhiều chuỗi key=value.

**Lưu ý bảo mật:** bản ghi vẫn tiết lộ rằng trường email và authorization có mặt. Nếu ngay cả sự hiện diện của trường cũng nhạy cảm hoặc không cần thiết, hãy bỏ hẳn chúng khỏi log. Đừng thay marker bằng vài ký tự đầu/cuối của token chỉ để tiện debug.

Hàm ví dụ không cố xử lý mọi định dạng PII bằng regex. Cách làm đó dễ bỏ sót encoding, cấu trúc lồng nhau, secret mới hoặc message không theo mẫu cũ. **Allowlist field** theo contract là phòng vệ dễ kiểm chứng hơn, dù vẫn cần giám sát các tuyến log khác.

## 7. Structured logging thay vì tự ghép message nhạy cảm

Một log event có cấu trúc thường tách metadata và field:

~~~json
{
  "timestamp": "2026-11-10T02:41:59Z",
  "level": "WARN",
  "service": "auth-service",
  "event": "login_rejected",
  "requestId": "req-42",
  "reasonCode": "invalid_credentials",
  "email": "[REDACTED]"
}
~~~

Đây là **JSON minh họa**, không tự sinh từ Java SE hoặc pattern text. Muốn xuất JSON, sử dụng encoder/serializer đúng chuẩn của stack đang dùng. Trong log text, một giá trị tự do chứa dấu cách, xuống dòng hoặc dấu bằng có thể đánh lừa parser; structured field và escaping phù hợp giúp giảm rủi ro này nhưng không thay thế redaction.

Những quy tắc nên dùng:

- Các **field key** đến từ schema đã phê duyệt, không dùng key do người dùng tạo tùy ý.
- **Event code** là giá trị ổn định, không phải nguyên exception message.
- Các trường nhạy cảm được **omit/redact trước serialization**; không nhờ JSON encoder tự đoán đâu là password.
- Các trường metadata như service/version/environment nếu tĩnh có thể bổ sung ở encoder/collector, tránh đặt lại vào MDC trên mọi request.
- Dùng **field presence**, errorCode hoặc outcome thay vì raw payload khi đủ đáp ứng điều tra.
- Nếu cần correlation, sử dụng **opaque ID** được tạo/validate ở ứng dụng, không dùng email/phone làm khóa truy vết mặc định.

JSON escaping giải quyết tính hợp lệ của format, **không ẩn dữ liệu**. Một JSON encoder có thể escape dấu ngoặc kép và newline hoàn hảo trong khi vẫn ghi nguyên token: event đó hợp lệ về cú pháp nhưng sai chính sách riêng tư.

## 8. SLF4J, MDC và Logback: những chỗ dễ lọt dữ liệu

Trong ứng dụng Java dùng SLF4J/Logback, MDC thường chứa request/trace context. Cần nhớ:

- **MDC.put("email", rawEmail)** có thể khiến email xuất hiện trên mọi dòng log được encoder cấu hình xuất toàn MDC.
- **%X{someKey}** hoặc JSON encoder lấy MDC chỉ đọc giá trị hiện có; nó **không tự redact**.
- Khi dùng **AsyncAppender**, event có thể snapshot context trên producer thread; thay đổi MDC sau đó không nhất thiết sửa được event đã enqueue.
- MDC từ HTTP header do client gửi phải được validate; một requestId chứa token hoặc newline có thể làm ô nhiễm nhiều event.
- Khi thread pool được tái sử dụng, MDC không được dọn trong finally có thể làm lộ context của request A sang log của request B.

Ví dụ dùng một ID do server đã xác nhận để gắn MDC trong scope:

~~~java
import org.slf4j.MDC;

void processRequest(String validatedRequestId, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", validatedRequestId);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Đây là **đoạn tích hợp**, yêu cầu SLF4J và logger implementation hỗ trợ MDC. Phải kiểm tra validatedRequestId trước khi gọi. Một thư viện chỉ sở hữu key requestId nên khôi phục **đúng key** thay vì gọi MDC.clear() và xóa mọi key do caller/tracer sở hữu.

**Không tạo MDC chứa raw user object hoặc toàn bộ request body.** Thay vào đó, chỉ giữ traceId/requestId/jobId và metadata đã được cho phép. Với async executor, cần capture/activate/restore context phù hợp; redaction và propagation là hai trách nhiệm khác nhau.

### Redaction ở Logback hoặc appender: dùng để phòng vệ bổ sung

Logback có thể hỗ trợ các cơ chế layout/encoder/filter tùy phiên bản và dependency. Một số hệ thống dùng converter hoặc regex replacement trên message. Tuy nhiên cần hiểu giới hạn:

- Nếu pattern chỉ redact **%msg**, các giá trị ở **%X{...}**, marker, argument field, throwable hoặc dữ liệu được encoder tự thêm có thể không qua cùng quy tắc.
- Regex theo text không luôn nhận ra token được tách chuỗi, encode, viết hoa khác hoặc nằm trong JSON lồng nhau.
- Bộ lọc sau khi sự kiện đã đi vào async queue có thể hoạt động **muộn hơn** nơi raw data được snapshot.
- Khi thêm appender mới, phải áp lại chính sách; đừng giả định cấu hình của appender cũ bảo vệ toàn bộ các sink.

**Đặt redaction theo field ở source/structured event builder** thường rõ nghĩa hơn regex thay thế message tổng hợp. Vẫn có thể dùng sink-side redaction như hàng rào bổ sung nếu test được phạm vi bao phủ.

## 9. Exception message, stack trace và lỗi thường bị bỏ sót

Một lời gọi phổ biến:

~~~java
logger.error("Payment failed for requestId={}", requestId, exception);
~~~

Trong SLF4J, khi Throwable được truyền đúng cách, provider có thể ghi stack trace. Tuy nhiên **Throwable.getMessage()** hoặc stack trace details do thư viện tạo có thể chứa URL, SQL, query parameter, user input hoặc cấu hình nhạy cảm. Redact chỉ parameter **requestId** không đảm bảo cả event an toàn.

Phải phân biệt:

1. **Exception type/stack location** phục vụ điều tra kỹ thuật, thường có giá trị.
2. **Exception message** có thể chứa giá trị từ bên ngoài hoặc chi tiết hệ thống; không mặc nhiên an toàn.
3. **Nested cause/suppressed exceptions** có thể mang thêm nội dung nhạy cảm.
4. **Framework error handler** hoặc HTTP client interceptor có thể tự log request/response dù app code đã được sửa.

Giải pháp thực tế là không đưa secret vào exception message ngay từ nguồn khi kiểm soát được; ghi **errorCode/exceptionType/operation/correlationId** an toàn; cấu hình thư viện để tránh dump payload; và có chính sách lọc/formatter đối với Throwable nếu thật sự cần. **Không xóa stack trace bằng mọi giá**: có thể giữ thông tin vị trí lỗi trong một sink bảo vệ phù hợp hoặc sử dụng formatter không đưa message nhạy cảm ra log đại trà.

Ví dụ định dạng an toàn ở boundary, chỉ ghi loại lỗi và mã sự kiện:

~~~java
logger.error("event={} requestId={} exceptionType={}",
        "payment_failed",
        validatedRequestId,
        exception.getClass().getSimpleName());
~~~

Đây là **đoạn tích hợp**. Việc không truyền Throwable có thể làm mất stack trace cần thiết; nếu stack trace được yêu cầu, phải kiểm soát nội dung ngoại lệ và sink phù hợp thay vì luôn bỏ nó. Đừng làm mất khả năng xử lý lỗi: redaction không thay thế retry, rollback hay error response đúng.

## 10. HTTP headers, body, URL và access logs

Redaction chỉ trong service logger vẫn chưa đủ khi framework, reverse proxy hoặc access log ghi dữ liệu từ HTTP.

**Authorization/Cookie/Set-Cookie:** mặc định không ghi raw. Một header khác có token như X-Api-Key cũng cần policy tương tự. Không chuyển credential thành vài ký tự cuối trừ khi có yêu cầu và phê duyệt cụ thể.

**URL/query string:** URL có thể chứa signed URL, email, session ID hoặc access token. Không log nguyên query string nếu không thật sự cần. Có thể log **route template** như /orders/{id} và status code thay vì một full URL chứa ID cá nhân và query.

**Request/response body:** body có thể là JSON lồng nhau, multipart, binary hoặc văn bản tự do. Redaction bằng regex chung trên serialized body dễ sai và tốn chi phí. Mặc định không dump body; nếu một endpoint thực sự cần diagnostic fields, xây allowlist riêng và giới hạn độ dài.

**Access logs ở proxy/ingress:** nằm ngoài code Java, nên kiểm tra cả hạ tầng. Một ứng dụng có thể không log token nhưng ingress vẫn log query; phải áp dụng chính sách liên tục qua toàn hệ thống.

**Client HTTP logs:** khi bật DEBUG hoặc wire logging của HTTP client, header/body có thể bị ghi tự động. Xem lại cấu hình thư viện ở staging và production; không tự bật verbose logging trong incident mà chưa đánh giá privacy.

## 11. ORM, database, messaging và background jobs

**ORM/SQL:** Hibernate/JDBC debug logs hoặc interceptors có thể chứa SQL với bind parameters, bao gồm dữ liệu cá nhân. Nếu cần performance diagnostics, ưu tiên thời gian query, query identifier, template hoặc statement fingerprint thay vì giá trị bind raw. Đừng tự giả định tất cả SQL logs đều là metadata an toàn.

**Message brokers:** Kafka/RabbitMQ consumers có thể log header, key, payload khi retry/dead-letter. Message ID hoặc jobId có thể dùng correlation; message payload cần policy dữ liệu riêng. Một exception phát sinh trong deserialization có thể chứa đoạn payload lỗi.

**Batch jobs:** thường có cám dỗ log từng record thất bại. Nên ghi taskId, errorCode, attemptNo và tổng số thất bại; nếu một record cần điều tra, lưu bằng chứng trong hệ thống có kiểm soát thay vì để raw PII trên general log.

**Third-party SDK:** payment, auth, email, cloud client và monitoring agent có thể xuất log mà app không trực tiếp gọi. Khi nâng cấp dependency cần kiểm tra mặc định logging, đặc biệt ở chế độ DEBUG/TRACE.

**Background retry:** một giá trị nhạy cảm có thể lặp lại qua nhiều attempt, tạo nhiều bản sao trên backend. Redaction trước event giúp tránh nhân số lần lộ theo số retry.

## 12. Redaction có quan hệ gì với log forging?

Hai vấn đề khác nhau:

- **Redaction** nhằm giảm lộ thông tin nhạy cảm.
- **Log forging/injection** nhằm ngăn dữ liệu không đáng tin bị hiểu như cú pháp của bản ghi log.

Một giá trị không có secret nhưng chứa CR/LF vẫn có thể giả mạo log. Ngược lại, một JSON encoder escape CR/LF hoàn hảo vẫn có thể ghi raw password. Vì vậy cần **cả output encoding/framing đúng lẫn redaction**.

Ví dụ sau là string giả lập, không phải bí mật thật:

~~~text
requestId=req-42\r\nINFO event=admin_authenticated
~~~

Nếu requestId do client tạo mà không được validate, formatter text line-oriented có thể tạo dòng giả. Với ID kỹ thuật, nên validate grammar/độ dài. Với trường văn bản tự do, output encoder phải escape theo format đích. Không dùng một regex tìm secret để thay thế kiểm soát delimiter/newline.

## 13. Hash, HMAC và tokenization cho correlation

Có những bài toán cần ghép log của nhiều hoạt động mà không muốn lưu raw email/account ID. Các lựa chọn phải được đánh giá theo privacy policy:

**Random opaque ID:** cấp một ID ngẫu nhiên cho request/session nghiệp vụ đã được xác thực. ID dùng trong log không nhất thiết suy ra trực tiếp danh tính thật. Cần lưu mapping ở hệ thống bảo vệ khi thực sự cần.

**Tokenization:** tạo token và lưu mapping có kiểm soát. Người có quyền truy cập vault có thể tra ngược, nên token không phải dữ liệu vô hại. Cần quản lý vòng đời mapping và retention.

**Hash:** giá trị có miền nhỏ như email/phone có thể bị suy ra bằng tra cứu từ điển. Không khuyến nghị dùng hash không khóa để tuyên bố dữ liệu đã được ẩn danh.

**HMAC:** dùng khóa bí mật riêng và thuật toán chuẩn để tạo mã so khớp ổn định trong phạm vi cần thiết. Cần có key rotation, phân tách khóa theo mục đích, giới hạn quyền xem và quy tắc expiration. Các token/HMAC có thể vẫn cho phép liên kết hoạt động của một người qua thời gian, vì vậy cần đánh giá rủi ro tái nhận diện và chính sách bảo vệ dữ liệu.

**Mã hóa:** dữ liệu được mã hóa vẫn có thể phục hồi bằng khóa; đây là bảo vệ dữ liệu khi lưu/chuyển, **không thay redaction**. Nếu không có nhu cầu truy ngược, đừng giữ thêm mapping hoặc ciphertext chỉ để debug.

Không triển khai thuật toán crypto tự chế để che ID trong log. Dùng thư viện chuẩn, quản lý khóa đúng và review với đội bảo mật khi nhu cầu thật sự đòi hỏi correlation có thể đảo ngược.

## 14. Chính sách riêng tư và retention trong production

Một bản ghi đã được redact ở một trường chưa chắc an toàn hoàn toàn. Kết hợp nhiều trường vô hại riêng lẻ có thể tái nhận diện. Ví dụ timestamp chính xác, IP, địa điểm và route hiếm có thể cho biết người dùng hoặc hoạt động cụ thể.

Thiết kế policy cần trả lời:

- Ai được xem log tổng hợp, log security, log audit và bản ghi lỗi?
- Các trường nào được xem ở dashboard thông thường, trường nào chỉ ở kênh bảo vệ?
- Dữ liệu tồn tại bao lâu trên host, collector, backend, archive, backup và bản xuất báo cáo?
- Có cơ chế xóa hoặc vô hiệu hóa bản sao khi dữ liệu đã bị ghi sai không?
- Khi bật DEBUG trong production, có thêm những trường nào được xuất ra?
- Các vendor/processor bên ngoài có nhận dữ liệu được định danh hay không?

**Retention** không thay thế redaction: một bản ghi chỉ lưu 24 giờ vẫn có thể bị xem hoặc chuyển tiếp trong khoảng đó. **Redaction** cũng không thay thế RBAC/ABAC: các bản ghi vẫn có thể chứa thông tin nội bộ hoặc correlation ID cần phân quyền.

Nếu có yêu cầu về quyền riêng tư/pháp lý, tuân thủ chính sách của tổ chức và quy định áp dụng tại nơi vận hành. Không khẳng định một kỹ thuật redaction cụ thể tự động đáp ứng mọi tiêu chuẩn hoặc luật bảo vệ dữ liệu.

## 15. Unit tests và integration tests cho redaction

Một bộ kiểm thử hiệu quả cần thử các trường có nguy cơ cao, không chỉ một payload định trước.

### 15.1. Unit tests

- Với field email/authorization, giá trị output phải là marker đã định nghĩa hoặc không có field.
- Với requestId không đúng regex/độ dài, log dùng marker an toàn; không dùng raw input.
- Với eventCode không thuộc allowlist, event phải được chuẩn hóa, không cho user quyết định level/name.
- Null hoặc field thiếu không gây exception và không làm xuất chuỗi dữ liệu nhạy cảm.
- Không dùng toString() của object thô khi tạo event; kiểm tra bằng DTO có giá trị mồi.
- Các bản ghi cho Unicode tiếng Việt vẫn parse đúng; không vô tình làm hỏng dữ liệu an toàn.

### 15.2. Integration tests

- Phát event chứa password/token giả, email giả và dữ liệu thanh toán giả; thu thập output từ **console, file, async queue, collector và backend** theo pipeline có sẵn.
- Kiểm tra raw secret **không xuất hiện** trong tất cả sink được cho phép truy cập; không chỉ kiểm tra UI.
- Test Throwable có nested cause chứa secret giả; xác minh policy đối với stack trace và exception message.
- Test MDC chứa input bị lỗi và context thread pool được tái sử dụng; giá trị không rò sang request sau.
- Test khi DEBUG/TRACE được bật tạm thời ở staging; không phát raw request body, headers hay bind parameters.
- Test log JSON được parser đọc thành field hợp lệ, không bị log forging bởi newline/delimiter.
- Test giá trị nhạy cảm xuất hiện qua encoding khác nhau hoặc key case biến thể; không tự tin một regex thay thế có bao phủ tuyệt đối.
- Test khi collector unavailable, queue đầy hoặc log rẽ nhiều destination; phải biết giá trị thô có thể lưu ở buffer nào.
- Test cấu hình mới khi thêm logger, appender, message consumer hoặc SDK bên thứ ba.

Có thể dùng **canary secrets** chỉ phục vụ kiểm thử trong staging để kiểm tra pipeline thực tế. Không gửi secret production hoặc thông tin cá nhân thật vào log test.

### 15.3. Kiểm thử chương trình Java 17 ở mục 6

Bản ghi dự kiến phải đúng:

~~~text
event=login_rejected requestId=req-42 email=[REDACTED] authorization=[REDACTED]
~~~

Test cần khẳng định chuỗi **alice@example.test** và **sample-token** không có trong output, còn eventCode và requestId hợp lệ vẫn hiển thị. Thay requestId bằng một chuỗi có CR/LF phải cho **requestId=invalid**; đây là yêu cầu dựa trên regex của ví dụ.

## 16. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Chỉ giảm log level từ DEBUG sang INFO | INFO/ERROR vẫn có thể chứa secret | Ngăn raw data đi vào mọi log event |
| Chỉ dùng regex thay các token đã biết | Secret có định dạng mới, bị encode hoặc nằm trong nested JSON | Allowlist field + serializer + test nhiều nguồn |
| Tin rằng parameterized logging tự che dữ liệu | Placeholder chỉ là cơ chế format | Chọn field an toàn trước khi gọi logger |
| Chỉ redact ở dashboard | Raw data còn trong file/index/queue/archive | Redact gần nguồn và kiểm tra mọi sink |
| Che bốn chữ số đầu/cuối của credential | Phần giữ lại có thể giúp khai thác hoặc đối chiếu | Omit hoặc full redaction theo policy |
| Hash email bằng SHA-256 không khóa rồi gọi là anonymous | Dễ dictionary attack, vẫn linkable | Xem xét opaque ID/HMAC + policy |
| Log nguyên Throwable cho mọi ERROR | Nested messages có thể chứa URL/query/secret | Review exception data và formatter |
| Đưa user email vào MDC | Rò vào nhiều event, khó dọn | Dùng validated opaque ID; scope cleanup |
| Dùng DTO.toString trong log | ToString có thể chứa toàn bộ field nhạy cảm | Structured allowlist |
| Tạo JSON thủ công | JSON có thể sai cú pháp hoặc không escape | JSON encoder/serializer chuẩn |
| Đặt redaction ở một appender | Appender khác có thể bypass | Chính sách nguồn + kiểm tra từng output |
| Dùng tokenization không quản lý vault/retention | Token còn liên kết hoặc giải ngược được | Phân quyền và quản lý mapping/key |
| Chỉ chạy unit test | Không chứng minh collector/agent không lưu secret | Thêm end-to-end tests |

## 17. Ứng phó khi phát hiện dữ liệu nhạy cảm trong log

Khi một token hoặc thông tin riêng tư xuất hiện trong log production, đây là một **sự cố xử lý dữ liệu** chứ không chỉ là lỗi hiển thị.

Các bước cần cân nhắc theo quy trình incident response:

1. **Ngăn phát sinh thêm:** tắt tuyến verbose hoặc chỉnh logger/encoder và triển khai bản sửa có kiểm tra.
2. **Xác định phạm vi:** loại dữ liệu, service, timestamp, sink, collector, index, archive, export và bên thứ ba có thể đã nhận.
3. **Thu hồi/rotate credential** nếu có token, API key, password hoặc secret có thể sử dụng; hạn chế quyền truy cập dữ liệu bị lộ.
4. **Kiểm soát bản sao:** thực hiện xóa, hạn chế truy cập, reindex hoặc data retention theo khả năng và yêu cầu của hệ thống, không tuyên bố đã xóa hết nếu còn backup/archive chưa xử lý.
5. **Giữ dữ kiện phục vụ điều tra** ở nơi được bảo vệ; tránh chụp màn hình hoặc đưa lại secret vào ticket/chat khác.
6. **Đánh giá nghĩa vụ thông báo** với đội bảo mật/pháp chế theo chính sách và quy định áp dụng.
7. **Thêm regression test** và kiểm tra dữ liệu mồi trên toàn logging pipeline trước khi đóng sự cố.

Không tự xử lý bằng việc “đổi log level” rồi bỏ qua dữ liệu đã được ghi. Nếu một token có hiệu lực đã lộ, thay đổi cấu hình logging không làm token đó hết tác dụng.

## 18. Checklist thiết kế redaction cho Java Logging

| Kiểm tra | Tiêu chí hoàn thành |
| --- | --- |
| Data classification | Xác định secret, PII, operational metadata, audit fields |
| Data minimization | Không log raw header, body, DTO hoặc user object khi không cần |
| Field allowlist | Chỉ chọn trường được phê duyệt trong structured event |
| Validation | requestId/eventCode và các ID kỹ thuật có grammar rõ |
| Redaction | Sensitive fields được omit hoặc thay marker trước log emission |
| Logging API | SLF4J/JUL/provider không làm rò qua toString hoặc Throwable |
| MDC | Không chứa secret, có scope cleanup và propagation đúng |
| Encoder | JSON/text được escape đúng; redaction khác output encoding |
| Collector | Lớp lọc bổ sung và kiểm soát parse error |
| Sink coverage | Console, file, async, storage, dashboard, export đều được kiểm thử |
| Access & retention | Quyền truy cập, retention, archive và backup có policy |
| Correlation | Opaque ID/HMAC nếu thật sự cần, không coi hash là anonymous |
| QA | Unit + integration + canary secrets trong staging |
| Incident process | Có quy trình phát hiện, thu hồi key, xóa/giới hạn và thông báo |

**Ghi nhớ:** redaction hiệu quả bắt đầu bằng **không đưa dữ liệu không cần thiết vào log**. Trong Java, hãy xây event theo schema allowlist, validate ID, xử lý riêng Throwable/MDC, dùng encoder đúng định dạng và kiểm thử tất cả các nơi nhận. Thay thế raw secret bằng marker chỉ là một phần; mục tiêu cuối cùng là **giữ khả năng điều tra mà không làm lộ thông tin riêng tư trong toàn bộ vòng đời của log**.