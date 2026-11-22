# Mask dữ liệu trong log của Spring Batch

## 1. Vì sao masking log là một yêu cầu bảo mật của batch?

Trong Spring Batch, một job thường đọc hàng nghìn đến hàng triệu bản ghi từ file, database, message broker hoặc API; xử lý bằng \`ItemReader\`, \`ItemProcessor\`, \`ItemWriter\`; sau đó ghi log để theo dõi tiến độ, skip, retry và lỗi. Dữ liệu đi qua job có thể chứa email, số điện thoại, tên khách hàng, địa chỉ, số tài khoản, mã định danh, số thẻ thanh toán, token truy cập và nhiều thông tin nội bộ.

Nếu code ghi nguyên đối tượng vào log, dữ liệu nhạy cảm có thể được sao chép tới console, file log, hệ thống giám sát, nền tảng thu thập log tập trung hoặc bản báo lỗi trong CI. Log thường có vòng đời lưu trữ, người truy cập và phạm vi sao chép **khác** với database nghiệp vụ ban đầu.

Ví dụ log không an toàn:

~~~text
INFO  Processing order: Order(id=O17, email=linh@example.test,
      cardNumber=4111111111111111, accessToken=eyJhbGci...)
WARN  Skip invalid row: 2026-11-16,Nguyen Van A,0900000000,4111111111111111
ERROR API call failed: Authorization: Bearer secret-token-value
~~~

Khi các dòng này đã đi vào log aggregation, việc xóa bản ghi nguồn **không làm log đã sao chép tự biến mất**. Vì vậy, mục tiêu của bài học không phải chỉ thay vài ký tự bằng dấu \`*\`, mà là kiểm soát **thông tin nào được phép xuất hiện ở mọi đường ghi log**.

Một log phù hợp hơn:

~~~text
INFO  event=order.processing jobExecutionId=801 orderRef=r_7af3c8d1
WARN  event=order.skipped jobExecutionId=801
      stepName=importOrdersStep phase=PROCESS
      orderRef=r_7af3c8d1 reasonCode=INVALID_AMOUNT
ERROR event=external.request.failed jobExecutionId=801
      dependency=risk-api failureClass=AUTHENTICATION_FAILURE
      httpStatus=401
~~~

Ở đây, các giá trị \`orderRef\` là **định danh giả lập minh họa**, không phải HMAC thực được tính từ dữ liệu trên. Log giữ lại các trường đủ để truy vết sự cố mà không lặp lại email, PAN hoặc token.

Trong bối cảnh **Spring Batch Core Processing → Security**, cần nắm ba nguyên tắc:

1. **Không log dữ liệu nhạy cảm nếu không cần.** Loại bỏ trường thường an toàn hơn che một phần.
2. **Mask trước khi log rời khỏi ứng dụng.** Filter ở collector chỉ là tuyến phòng thủ bổ sung, không thay thế bảo vệ tại nơi phát sinh.
3. **Giữ khả năng vận hành có kiểm soát.** Dùng execution ID, Step, event, reason code, counter và mã tham chiếu không tiết lộ thông tin gốc.

## 2. Masking, redaction, pseudonymization và encryption khác nhau thế nào?

| Cách xử lý | Mục tiêu | Ví dụ hình thức | Lưu ý |
|---|---|---|---|
| **Omit** | Không đưa giá trị vào log | Chỉ ghi \`hasEmail=true\` nếu thực sự cần | Thường là lựa chọn ưu tiên |
| **Redact** | Thay toàn bộ bằng giá trị cố định | \`email=[REDACTED]\` | Không hỗ trợ tìm theo giá trị gốc |
| **Mask** | Che một phần, giữ lại phần được phép | \`phone=********42\` | Phần còn lại vẫn có thể nhận diện người |
| **Pseudonymize** | Đổi sang mã tham chiếu có thể liên kết có kiểm soát | \`customerRef=r_a7c2...\` | Vẫn có thể là dữ liệu cá nhân tùy ngữ cảnh |
| **HMAC** | Sinh dấu tham chiếu có khóa bí mật để so khớp | \`HMAC(key, customerId)\` rút gọn | Khác plain hash; phải bảo vệ khóa |
| **Hash không khóa** | Dấu băm một chiều về mặt toán học | \`SHA-256(email)\` | Có thể bị đoán bằng từ điển đối với giá trị ít khả năng |
| **Encryption** | Giữ khả năng giải mã bởi người/hệ thống có khóa | Ciphertext | Không đồng nghĩa dữ liệu an toàn để log; khóa và quyền truy cập vẫn quan trọng |

**Masking không nhất thiết làm dữ liệu trở thành ẩn danh.** Email còn domain, số điện thoại còn vài chữ số hoặc mã khách hàng bị băm nhưng ổn định vẫn có thể liên kết với một cá nhân trong một số bối cảnh. Nếu không có yêu cầu nghiệp vụ rõ ràng, dùng \`[REDACTED]\` hoặc bỏ hẳn field khỏi log.

Ví dụ cùng một sự kiện:

~~~text
Không an toàn:
  event=order.failed email=linh@example.test token=secret123

Redact:
  event=order.failed email=[REDACTED] token=[REDACTED]

Tối thiểu hóa:
  event=order.failed reasonCode=INVALID_AMOUNT
  jobExecutionId=801 stepName=validateOrdersStep

Cần tương quan theo khách hàng, đã có phê duyệt:
  event=order.failed customerRef=h_74b9f2ce...
  reasonCode=INVALID_AMOUNT jobExecutionId=801
~~~

Lựa chọn cuối phải theo chính sách nội bộ về phân loại dữ liệu, thời gian lưu log, mục đích truy vết và quyền truy cập. Không mặc nhiên coi việc giữ bốn số cuối của thẻ hoặc một phần số tài khoản là được phép.

## 3. Phân loại dữ liệu trước khi xây logging policy

Nên xác định chính sách cho **từng nhóm trường**, thay vì cố tạo một regex chung để đoán đâu là dữ liệu nhạy cảm.

| Nhóm dữ liệu | Ví dụ | Chính sách log khởi điểm |
|---|---|---|
| **Secrets** | Password, API key, access token, cookie phiên, private key | Không log giá trị; không giữ tiền tố/hậu tố |
| **Payment data** | Số thẻ đầy đủ, CVV/CVC, thông tin xác thực giao dịch | Không log; tuân thủ quy trình bảo mật thanh toán áp dụng |
| **PII trực tiếp** | Email, số điện thoại, giấy tờ tùy thân, địa chỉ | Bỏ hoặc redact; chỉ mask một phần khi có lý do và chính sách |
| **PII gián tiếp** | Mã khách hàng, order ID có thể tra về chủ thể | Dùng opaque reference hoặc HMAC có khóa nếu cần liên kết |
| **Dữ liệu tài chính** | Số dư, chi tiết thu nhập, payload giao dịch | Không log toàn bộ; chỉ số tổng hợp hoặc nhóm giá trị được phép |
| **Metadata batch** | jobName, jobExecutionId, stepName, stepExecutionId, BatchStatus | Thường hữu ích, nhưng kiểm tra cả tên/file/path |
| **Thống kê** | readCount, writeCount, skipCount, duration, reason code | Phù hợp nếu không rò rỉ thông tin qua nhãn quá chi tiết |
| **System details** | Host, internal URL, query SQL, stack trace | Chỉ ghi mức cần thiết; có thể chứa secret và dữ liệu nguồn |

Đây là chính sách gợi ý theo hướng hạn chế. Quy định chính thức phải được thống nhất với bộ phận bảo mật, pháp chế và yêu cầu ngành nếu dữ liệu có tính điều chỉnh.

### Thiết lập allowlist thay vì blacklist

**Allowlist** là danh sách các trường được phép xuất log. Ví dụ sự kiện \`order.skipped\` chỉ được phép có:

~~~text
event
jobExecutionId
stepExecutionId
stepName
phase
reasonCode
safeRecordRef (nếu được cấp phép)
~~~

Nếu record nghiệp vụ có thêm trường \`nationalId\` trong phiên bản sau, nó **không tự xuất hiện** ở log vì không thuộc allowlist. Đây là ưu điểm so với log cả object rồi tìm cách xóa những field “quen thuộc” bằng blacklist.

Không dùng tên field làm bằng chứng duy nhất. Một field tên \`id\`, \`message\`, \`path\`, \`details\` hoặc \`reason\` vẫn có thể chứa token, email hay dữ liệu nhạy cảm.

## 4. Những đường rò rỉ đặc thù của Spring Batch

Một job có thể có nhiều nơi sinh log ngoài các lệnh \`log.info\` do ứng dụng viết.

| Vị trí | Nguy cơ | Biện pháp chính |
|---|---|---|
| \`ItemReader\` | Raw line CSV, JSON payload, câu SQL/bind parameter | Không log raw input; cấu hình logger thư viện và lỗi parse |
| \`ItemProcessor\` | \`toString()\` của object, field nhạy cảm trong validation message | Log event + reasonCode + opaque reference |
| \`ItemWriter\` | SQL parameters, request/response API, nội dung file | Chỉ log số lượng, kết quả và mã lỗi an toàn |
| \`SkipListener.onSkipInRead\` | Exception parse chứa cả dòng input | Không in \`FlatFileParseException.getInput()\` |
| \`SkipListener.onSkipInProcess\` | Object item đầy đủ và exception message | Không log item trực tiếp; chỉ trường an toàn |
| \`SkipListener.onSkipInWrite\` | Cả chunk hoặc payload lỗi ghi | Kiểm soát key và throwable được log |
| \`JobExecutionListener\` | Dump toàn bộ JobParameters | Chọn allowlist; không log raw parameters |
| \`StepExecutionListener\` | ExecutionContext chứa state tùy biến | Không serialize/dump nguyên context |
| Retry/rollback logging | Throwable từ HTTP/DB có request body | Phân loại lỗi, không in message thô nếu không kiểm soát |
| MDC | Giá trị nhạy cảm tự gắn vào mọi log trên thread | Chỉ lưu ID kỹ thuật an toàn; cleanup/restore |
| JDBC/ORM/HTTP debug | SQL bind values, header Authorization, body | Tắt payload tracing/DEBUG nhạy cảm ở production |
| APM/traces/metrics | Span attributes, baggage, metric label chứa PII | Thiết lập allowlist như log |
| Exception in job metadata | \`ExitStatus.exitDescription\`, failure exceptions | Tránh message chứa dữ liệu; kiểm tra quyền truy cập metadata |

Đặc biệt, **Spring Batch JobRepository là một nguồn lưu trữ metadata**, không phải log thuần văn bản. Nếu ứng dụng ném exception có raw input trong message, nội dung đó có thể xuất hiện trong failure detail hoặc các công cụ hiển thị execution. Việc chỉ cấu hình Logback masking **không bảo vệ các giá trị đã lưu ở nơi khác**.

### \`FlatFileParseException\` có thể chứa input nguyên dòng

Với \`FlatFileItemReader\`, lỗi ở tokenizer hoặc field mapper có thể được bọc trong \`FlatFileParseException\`. Object exception có thông tin số dòng và **input** của dòng bị lỗi. Ví dụ:

~~~csv
orderId,email,amount
O101,linh@example.test,not-a-number
~~~

Không nên làm:

~~~java
catch (FlatFileParseException ex) {
    log.error("Could not parse {}", ex.getInput(), ex);
}
~~~

Ở đây cả \`ex.getInput()\` và stack trace có thể chứa thông tin nguồn. Chuyển sang log có cấu trúc:

~~~java
catch (FlatFileParseException ex) {
    log.warn(
        "event=input.parse.failed lineNumber={} reasonCode={}",
        ex.getLineNumber(), "INVALID_NUMBER");
    throw ex;
}
~~~

Đoạn mã chỉ minh họa cách log an toàn hơn; **ném lại exception vẫn có thể làm framework hoặc listener khác ghi exception thô ở cấp khác**. Cần rà soát các logger thực tế, không mặc định việc bắt và rethrow đã làm toàn bộ luồng log an toàn.

## 5. Cấu trúc một sự kiện log an toàn

Thay vì log object:

~~~java
log.info("Processing order={}", order);
~~~

Hãy xác định sự kiện có đủ dữ liệu để điều tra nhưng không chứa field nhạy cảm:

~~~java
log.info(
        "event=order.processing jobExecutionId={} stepName={} recordRef={}",
        jobExecutionId,
        "validateOrdersStep",
        safeRecordRef);
~~~

Nếu \`safeRecordRef\` chỉ là \`orderId\` có thể tra được tên khách hàng, nó vẫn phải được kiểm tra theo policy. Có thể dùng opaque ID được sinh riêng cho vận hành hoặc HMAC theo cách được phê duyệt.

Ví dụ record nghiệp vụ:

~~~java
import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String customerEmail,
        String phoneNumber,
        String accessToken,
        BigDecimal amount) {
}
~~~

Java record mặc định sinh \`toString()\` chứa **giá trị của các component**. Việc ghi \`log.debug("{}", rawOrder)\` có thể làm email, phone và access token xuất hiện trực tiếp. Không nên dựa vào tên class hoặc việc dùng DTO để kết luận rằng \`toString()\` an toàn.

Một DTO chuyên dụng cho log:

~~~java
public record SafeOrderLogEvent(
        String event,
        long jobExecutionId,
        String stepName,
        String recordRef,
        String reasonCode) {
}
~~~

Chỉ tạo object này từ các giá trị **đã được phân loại an toàn**, không map toàn bộ record nghiệp vụ bằng reflection. Dù là DTO log, nếu \`recordRef\` hoặc \`reasonCode\` lấy trực tiếp từ input không đáng tin, nó vẫn có thể bị lợi dụng để đưa dữ liệu hoặc ký tự xuống dòng vào log.

### Sử dụng reason code cố định

Thay vì:

~~~text
reason=Invalid phone 0900000000 for customer linh@example.test
~~~

Sử dụng:

~~~text
reasonCode=INVALID_PHONE_FORMAT
field=phoneNumber
phase=PROCESS
jobExecutionId=801
~~~

Tên field, phase và reasonCode nên lấy từ **enum/constant đã kiểm soát**, không truyền nguyên message từ exception hoặc input người dùng. Khi cần chi tiết để sửa record, lưu vào kho xử lý lỗi có phân quyền thích hợp và chính sách retention riêng, không tận dụng log chung làm kho chứa dữ liệu nhạy cảm.

## 6. Xây một lớp redaction đơn giản cho giá trị có nhãn

Với dữ liệu mà policy chỉ cho phép ghi trạng thái che hoàn toàn, một API rõ ràng tốt hơn việc truyền chuỗi nhạy cảm vào logger rồi hy vọng appender sửa lại.

~~~java
public final class SensitiveValues {

    private SensitiveValues() {
    }

    public static String redactedEmail(String email) {
        return email == null ? "[ABSENT]" : "[REDACTED_EMAIL]";
    }

    public static String redactedPhone(String phone) {
        return phone == null ? "[ABSENT]" : "[REDACTED_PHONE]";
    }

    public static String redactedToken(String token) {
        return token == null ? "[ABSENT]" : "[REDACTED_SECRET]";
    }

    public static String redactedPaymentCard(String pan) {
        return pan == null ? "[ABSENT]" : "[REDACTED_PAN]";
    }
}
~~~

Ví dụ:

~~~java
log.info("event=order.validation.failed email={} reasonCode={}",
        SensitiveValues.redactedEmail(order.customerEmail()),
        "INVALID_EMAIL_FORMAT");
~~~

Thiết kế trên cố ý **không giữ lại phần nào của email, token hay PAN**. Việc phân biệt \`[ABSENT]\` với \`[REDACTED_EMAIL]\` đôi khi cũng có thể tiết lộ trường có dữ liệu hay không; nếu sự tồn tại của trường nhạy cảm là thông tin cần bảo vệ, dùng một marker cố định hoặc bỏ field hoàn toàn.

### Khi thực sự được phép mask một phần

Với trường ít nhạy cảm hơn và policy cho phép hiển thị hai ký tự cuối, có thể làm theo allowlist riêng:

~~~java
public final class ApprovedPartialMask {

    private ApprovedPartialMask() {
    }

    public static String lastTwoOnly(String value) {
        if (value == null) {
            return "[ABSENT]";
        }
        if (value.length() < 3) {
            return "[REDACTED]";
        }
        return "*".repeat(value.length() - 2)
                + value.substring(value.length() - 2);
    }
}
~~~

Ví dụ này minh họa **cơ chế partial masking**, không phải khuyến nghị áp dụng cho số thẻ, tài khoản ngân hàng, email hay giấy tờ tùy thân. Việc giữ hai ký tự cuối vẫn có thể là PII. Logic trên đếm theo đơn vị UTF-16 của Java; không dùng nguyên xi cho chuỗi Unicode có ký tự ghép hoặc cho văn bản tự do có yêu cầu xử lý grapheme.

Trong Spring Batch, lựa chọn bảo mật ổn định nhất thường là log **ID kỹ thuật, trạng thái và reason code**, không log giá trị được mask trừ khi nhu cầu điều tra chứng minh cần thiết.

## 7. HMAC cho mã tham chiếu có thể liên kết giữa các log

Khi cần xác định các lỗi thuộc **cùng một khách hàng hoặc cùng một khóa nguồn** mà không log giá trị gốc, có thể dùng **HMAC** với secret key. So với SHA-256(email) không khóa, HMAC khó bị lập bảng tra cứu nếu secret được bảo vệ.

Ví dụ Java 17+:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class LogReferenceGenerator {

    private final byte[] secretKey;

    public LogReferenceGenerator(byte[] secretKey) {
        if (secretKey == null || secretKey.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC key must be provisioned securely");
        }
        this.secretKey = secretKey.clone();
    }

    public String refForCustomer(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            return "customer_absent";
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));

            byte[] digest = mac.doFinal(
                    ("customer:" + customerId)
                            .getBytes(StandardCharsets.UTF_8));

            // Cắt còn 16 byte (128 bit) làm mã tương quan.
            byte[] shortened = Arrays.copyOf(digest, 16);
            return "c_" + HexFormat.of().formatHex(shortened);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(
                    "Cannot calculate log reference", e);
        }
    }
}
~~~

Đoạn ví dụ giả định khóa bí mật **được cấp qua secret manager hoặc cơ chế bảo mật tương đương**; không hardcode vào source, job parameters, log hay file cấu hình được commit. Trên thực tế cần chính sách version/rotation của khóa, phân quyền sử dụng và làm sạch reference trong thời gian lưu trữ thích hợp.

\`Mac\` được tạo mới mỗi lần gọi, tránh chia sẻ một instance không thread-safe giữa các chunk song song. Tiền tố \`customer:\` giúp tách namespace khi cùng khóa HMAC được dùng cho nhiều loại định danh.

**HMAC không khiến dữ liệu tự động trở thành dữ liệu phi cá nhân.** Nếu một người có quyền tính HMAC cho mọi customerId thì họ vẫn có thể tra cứu; reference ổn định cũng cho phép nối các sự kiện. Cần hạn chế mục đích sử dụng, quyền truy cập và thời gian giữ reference. Nếu bài toán không cần liên kết theo khách hàng, nên bỏ hoàn toàn \`customerRef\`.

### Không băm bằng thuật toán không khóa các giá trị dễ đoán

Số điện thoại, email và mã khách hàng theo quy luật thường có không gian giá trị có thể đoán. Việc ghi:

~~~java
// Không nên coi đây là ẩn danh mạnh:
sha256(email);
~~~

không đủ để bảo vệ trước kẻ tấn công có thể thử hàng loạt giá trị từ từ điển. HMAC với secret được quản lý thích hợp giảm rủi ro này nhưng vẫn cần đánh giá chính sách dữ liệu.

## 8. Mask dữ liệu trong ItemProcessor và ItemWriter

Giả sử Step nhập đơn cần kiểm tra số tiền và gửi yêu cầu đến dịch vụ định giá. Processor nên ném **exception an toàn**, có reason code, thay vì đưa cả record nhạy cảm vào message.

~~~java
public enum BatchErrorCode {
    INVALID_AMOUNT,
    INVALID_CURRENCY,
    EXTERNAL_SERVICE_TIMEOUT,
    OUTPUT_WRITE_FAILED,
    UNKNOWN_INPUT_FORMAT
}

public class SafeBatchItemException extends RuntimeException {

    private final BatchErrorCode code;

    public SafeBatchItemException(BatchErrorCode code) {
        super(code.name());
        this.code = code;
    }

    public BatchErrorCode code() {
        return code;
    }
}
~~~

Processor:

~~~java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class ValidatingOrderProcessor
        implements ItemProcessor<RawOrder, RawOrder> {

    @Override
    public RawOrder process(RawOrder order) {
        if (order.amount() == null
                || order.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new SafeBatchItemException(
                    BatchErrorCode.INVALID_AMOUNT);
        }
        return order;
    }
}
~~~

Không nên viết:

~~~java
throw new IllegalArgumentException(
        "Invalid order: " + order); // record.toString() có PII/secret
~~~

Vì exception message có thể được log bởi framework, listener hoặc hiển thị trong Batch metadata, việc đặt dữ liệu gốc vào message gây rủi ro dù ứng dụng không chủ động gọi \`log.error\`.

Trong writer, chỉ log các trường tổng hợp:

~~~java
log.info(
        "event=orders.chunk.written jobExecutionId={} itemCount={}",
        executionId,
        chunk.size());
~~~

Không log cả \`chunk\`, SQL bind values hoặc request body. Nếu writer xử lý nhiều record và có lỗi, dùng **mã tham chiếu item đã được duyệt** cùng loại lỗi, thay vì in đầy đủ payload để “dễ debug”.

### Dữ liệu thô vẫn cần được xử lý để sửa lỗi

Mask log không có nghĩa phải xóa thông tin cần sửa khỏi mọi hệ thống. Nếu batch cần lưu record lỗi để vận hành xử lý lại, hãy dùng **quarantine store** riêng có mã hóa, RBAC, retention, audit truy cập và key tham chiếu. Log chỉ chứa ID kỹ thuật hoặc safe reference để mở bản ghi qua giao diện được phân quyền.

## 9. Viết SkipListener không rò rỉ item và raw line

Trong fault-tolerant Step, \`SkipListener<T, S>\` nhận thông tin lỗi để ghi audit. Đây là vị trí dễ vô tình log dữ liệu nhạy cảm nhất.

Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public class SecureOrderSkipListener
        implements SkipListener<RawOrder, RawOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(SecureOrderSkipListener.class);

    private final LogReferenceGenerator referenceGenerator;

    public SecureOrderSkipListener(
            LogReferenceGenerator referenceGenerator) {
        this.referenceGenerator = referenceGenerator;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        Integer lineNumber = error instanceof FlatFileParseException ex
                ? ex.getLineNumber()
                : null;

        log.warn(
                "event=batch.item.skipped phase=READ "
                + "reasonCode=UNKNOWN_INPUT_FORMAT lineNumber={}",
                lineNumber);
        // KHÔNG log error.getMessage() hoặc FlatFileParseException.getInput().
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        String reasonCode = error instanceof SafeBatchItemException safe
                ? safe.code().name()
                : "PROCESSING_ERROR";

        log.warn(
                "event=batch.item.skipped phase=PROCESS "
                + "recordRef={} reasonCode={}",
                referenceGenerator.refForCustomer(item.orderId()),
                reasonCode);
    }

    @Override
    public void onSkipInWrite(RawOrder item, Throwable error) {
        log.warn(
                "event=batch.item.skipped phase=WRITE "
                + "recordRef={} reasonCode=OUTPUT_WRITE_FAILED",
                referenceGenerator.refForCustomer(item.orderId()));
    }
}
~~~

Trong ví dụ, method \`refForCustomer\` được dùng với \`orderId\` chỉ để tái sử dụng cách sinh reference; dự án thật nên định nghĩa hàm **\`refForOrder\`** và namespace HMAC riêng cho order ID. Phần log giữ \`lineNumber\` nếu có, không giữ raw CSV. Line number là metadata, nhưng khi file chứa ít record hoặc có mapping công khai tới dữ liệu, mức độ nhạy cảm vẫn cần đánh giá.

Đăng ký listener vào fault-tolerant Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, RawOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(SafeBatchItemException.class)
        .skipLimit(5)
        .listener(secureOrderSkipListener)
        .build();
~~~

Trong đoạn này \`reader\`, \`processor\`, \`writer\`, \`transactionManager\`, \`jobRepository\` là các bean đã có. Tên exception thực tế phải khớp với lỗi do reader/processor phát ra; skip policy không nên rộng đến \`Exception.class\` chỉ để có log đẹp.

**SkipListener không phải chốt chặn cuối cùng cho leak.** Nếu reader hoặc JDBC/HTTP client đã log payload trước khi ném exception, listener an toàn không thể xóa bản log cũ. Cần bảo vệ từ reader/adapter, xử lý exception cho đến logger bên thứ ba.

## 10. Gắn JobExecution ID an toàn bằng MDC

SLF4J **Mapped Diagnostic Context (MDC)** cho phép mọi log trên thread hiện tại có thêm thông tin như \`jobExecutionId\` và \`stepExecutionId\`. Chỉ nên gắn metadata an toàn; **không đưa email, token, raw JobParameters hoặc payload vào MDC**.

Ví dụ một Step listener:

~~~java
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class SafeMdcStepListener
        implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        MDC.put("jobExecutionId",
                String.valueOf(stepExecution.getJobExecutionId()));
        MDC.put("stepExecutionId",
                String.valueOf(stepExecution.getId()));
        MDC.put("stepName", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        try {
            // Các log cuối Step ở đây nếu cần.
        } finally {
            MDC.remove("stepName");
            MDC.remove("stepExecutionId");
            MDC.remove("jobExecutionId");
        }
        return null;
    }
}
~~~

Đoạn này minh họa Step chạy tuần tự trên cùng thread. Với các thread pool hoặc partition, cần thiết lập **MDC tại đúng điểm vào worker** hoặc sao chép context qua TaskDecorator và khôi phục context cũ trong \`finally\`. Nếu chỉ đặt MDC ở thread điều khiển Job, các worker thread không mặc nhiên nhận được giá trị đó.

MDC có thể được giữ lại khi thread được tái sử dụng, vì vậy cần cleanup. Tránh \`MDC.clear()\` tùy tiện nếu thư viện tracing đang dùng cùng MDC cho \`traceId\`/\`spanId\`; hãy chỉ xóa key thuộc sở hữu của listener hoặc restore snapshot trước đó.

### Không đưa raw JobParameters vào log

Spring Batch cho phép JobParameters chứa các tham số như \`inputFile\`, \`batchId\`, \`tenantId\`, \`accessToken\`. Đừng làm:

~~~java
log.info("Starting with parameters={}",
        jobExecution.getJobParameters());
~~~

Thay vào đó, xây allowlist rõ:

~~~java
log.info(
        "event=batch.started jobExecutionId={} jobName={} "
        + "inputType={} sourceVersion={}",
        jobExecution.getId(),
        jobExecution.getJobInstance().getJobName(),
        "CSV",
        safeSourceVersion);
~~~

Nếu đường dẫn file chứa username, mã khách hàng hoặc thông tin kinh doanh, **không log full path**. Có thể log loại nguồn, đuôi file hoặc opaque fileId tùy contract. Những tham số là secret không nên được truyền như JobParameters thông thường nếu chúng còn có thể bị lưu trong JobRepository; hãy dùng secret manager/credential provider ở lớp infrastructure.

## 11. Cấu hình Logback để không làm mất ngữ cảnh an toàn

Sau khi code đặt các key MDC được duyệt, cần cấu hình backend ghi các trường đó ra output. Ví dụ \`logback-spring.xml\` với pattern text:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>
                %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
                %-5level
                [jobExecutionId=%X{jobExecutionId:-none}]
                [stepExecutionId=%X{stepExecutionId:-none}]
                [stepName=%X{stepName:-none}]
                %logger{36} - %msg%n
            </pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Pattern dùng MDC \`jobExecutionId\`, \`stepExecutionId\` và \`stepName\` đã được phân loại tương đối an toàn. **\`%msg\` vẫn có thể chứa dữ liệu nhạy cảm** nếu code hoặc thư viện ghi message thô. Vì vậy, Logback pattern là bước giữ ngữ cảnh, không phải cơ chế tự động redact mọi dữ liệu.

### Structured JSON log

Với log aggregation, structured JSON thuận tiện hơn chuỗi tự ghép:

~~~json
{
  "timestamp": "2026-11-16T09:00:00+07:00",
  "level": "WARN",
  "event": "batch.item.skipped",
  "jobExecutionId": "801",
  "stepExecutionId": "3401",
  "stepName": "importOrdersStep",
  "phase": "PROCESS",
  "recordRef": "c_74b9f2ce",
  "reasonCode": "INVALID_AMOUNT"
}
~~~

Đây là format mong muốn, không phải output mặc định của mọi phiên bản Spring Boot/Logback. Dự án có thể dùng structured logging do Spring Boot cung cấp hoặc JSON encoder tương thích và cấu hình **field allowlist**. Không bật chế độ “export all MDC” nếu ứng dụng còn các key chứa thông tin nhạy cảm.

### Regex-based masking tại appender chỉ là phòng tuyến bổ sung

Một số hệ thống dùng filter hoặc custom layout để thay \`password=...\`, \`Bearer ...\` hoặc chuỗi giống số thẻ bằng \`[REDACTED]\`. Đây là cách **defense in depth** hữu ích với các pattern đã biết, nhưng có giới hạn:

- JSON escaping, line break, Unicode, dạng encoding khác và key đổi tên có thể né pattern.
- Secret có thể nằm trong exception stack trace, \`toString()\`, structured argument hoặc trường MDC mà regex chỉ xử lý \`%msg\` không nhìn thấy.
- Regex quá rộng có thể phá dữ liệu vận hành hoặc gây tốn CPU khi log lượng lớn.
- Regex quá hẹp có thể bỏ sót token được định dạng khác.
- Log có thể đã bị ghi tới appender/collector khác trước khi filter cuối hoạt động.

Do đó, không xem cấu hình regex như bảo đảm tuyệt đối rằng log sẽ không chứa dữ liệu nhạy cảm. **Ngăn từ nguồn** bằng allowlist và exception an toàn vẫn là hướng chính.

## 12. Exception, stack trace và thông điệp lỗi từ thư viện

Trong batch, exception có thể chứa dữ liệu nhạy cảm theo nhiều cách:

~~~text
FlatFileParseException: failed to parse line:
  O101,linh@example.test,4111111111111111

HttpClientErrorException:
  401 Unauthorized: {"token":"secret-..."}

SQL exception:
  duplicate key value violates unique constraint ...
  Detail: Key (email)=(linh@example.test) already exists.
~~~

Khi gọi:

~~~java
log.error("Batch operation failed", exception);
~~~

logger thường ghi message và stack trace của exception; **nội dung exception chain có thể chứa payload**. Tránh log throwable thô tại các ranh giới xử lý dữ liệu không đáng tin nếu chưa biết exception message an toàn.

Một cách tiếp cận:

~~~java
public enum FailureCategory {
    INPUT_PARSE_ERROR,
    VALIDATION_ERROR,
    EXTERNAL_TIMEOUT,
    OUTPUT_CONSTRAINT_ERROR,
    UNKNOWN_FAILURE
}

public static FailureCategory classify(Throwable error) {
    if (error instanceof org.springframework.batch.item.file
            .FlatFileParseException) {
        return FailureCategory.INPUT_PARSE_ERROR;
    }
    if (error instanceof SafeBatchItemException) {
        return FailureCategory.VALIDATION_ERROR;
    }
    return FailureCategory.UNKNOWN_FAILURE;
}
~~~

Sau đó log:

~~~java
log.error(
        "event=batch.operation.failed failureCategory={} "
        + "jobExecutionId={}",
        classify(error),
        jobExecutionId);
~~~

Đây là ví dụ phân loại lỗi tối thiểu; production nên có một bộ mapping exception được xem xét theo adapter, database và dịch vụ ngoài. **Không dùng \`error.getMessage()\` hoặc \`error.toString()\` như một safe reason code**.

### Cần stack trace để debug thì làm gì?

Stack trace có ích nhưng không phải lúc nào cũng an toàn. Có thể thiết kế **diagnostic channel** với quyền truy cập hạn chế, redaction theo nguồn lỗi và retention ngắn hơn; hoặc tạo incident ID liên kết đến bản ghi lỗi được bảo vệ ở kho riêng. Khi cho phép stack trace, kiểm thử toàn bộ exception chain với dữ liệu giả nhạy cảm để biết backend thực sự ghi những gì.

Không nên bắt mọi exception rồi im lặng: job vẫn phải phản ánh đúng \`FAILED\`, \`skip\` hoặc \`retry\` theo chính sách Spring Batch. **Che dữ liệu trong log khác hoàn toàn với che giấu lỗi vận hành**.

## 13. SQL, HTTP và thư viện bên thứ ba

Ngay cả khi logger ứng dụng an toàn, thư viện vẫn có thể in raw values khi bật debug/tracing.

### JDBC/ORM

Hãy xem xét:

- Log câu SQL có thể chứa literal thay vì parameter placeholder.
- SQL bind value logging của JDBC proxy, Hibernate hoặc driver có thể in email/ID và số tiền.
- Database error message có thể chứa giá trị vi phạm constraint.
- Query monitoring hoặc slow query log ở **database server** là một kênh riêng, không chịu Logback filter của ứng dụng.

Không bật các logger in bind values ở production nếu dữ liệu nhạy cảm. Khi cần phân tích truy vấn, ưu tiên query template, execution plan và timing không chứa bind values; sử dụng môi trường test với dữ liệu tổng hợp cho debug chi tiết.

### HTTP và SDK

Không log đầy đủ request/response của HTTP client khi có \`Authorization\`, cookie, PII hoặc body giao dịch. Nếu cần request correlation, giữ endpoint **template** và HTTP status:

~~~text
event=api.failed
dependency=customer-risk
method=POST
route=/risk/evaluate
status=503
durationMs=1260
jobExecutionId=801
~~~

Không log URL thực chứa query parameter chứa email/token. Nếu HTTP client hỗ trợ request/response logging interceptor, cấu hình **header và body redaction** ở interceptor đó, đồng thời thử với redirect/error path để không sót nhánh bất thường.

### Tracing và metrics

Traces có thể lưu \`span attributes\`, \`baggage\`, HTTP URL, SQL statement và exception message. Metrics có thể dùng label như customerId hoặc fileName. Cần áp dụng nguyên tắc allowlist tương tự log:

- Không đưa email, token, PAN vào span attribute hoặc metric label.
- Dùng \`jobName\`, \`stepName\`, \`status\`, \`failureCategory\` ở metrics nếu số lượng giá trị được kiểm soát.
- Đặt \`jobExecutionId\` trong log/trace hoặc audit truy vấn theo ID, không dùng làm nhãn Prometheus mặc định vì **high cardinality**.
- Khi trace được xuất qua collector, cấu hình redaction/scrubbing như phòng tuyến bổ sung.

## 14. File lỗi, quarantine và ExecutionContext

Một số job tạo **reject file** chứa các dòng không parse được hoặc record lỗi:

~~~text
input.csv
    |
    +--> valid rows --> writer --> output
    |
    +--> invalid rows --> reject file / quarantine store
~~~

Reject file không phải log và có thể cần chứa dữ liệu gốc để phục hồi. Nếu cần giữ, hãy:

1. Dùng storage riêng có encryption at rest và quyền truy cập hẹp.
2. Không đặt tên file chứa email, số điện thoại hoặc mã bí mật.
3. Không ghi raw line vào log chỉ để báo đường dẫn tới reject file.
4. Gắn batchId, source version, reason code và opaque reference cho từng record.
5. Xác định retention, quy trình xóa, audit truy cập và quyền xuất file.
6. Không để file lỗi trên thư mục tạm hoặc volume có quyền truy cập rộng.

**ExecutionContext** của Spring Batch lưu state để restart và thường được persist trong JobRepository. Không dùng ExecutionContext làm nơi chứa access token, số thẻ hoặc raw item chỉ để “có dữ liệu debug”; các trường này có thể bị lưu lâu hơn dữ liệu nghiệp vụ, và không chịu masking của logger.

Tương tự, \`ExitStatus.exitDescription\`, message do listener tạo và exception được giữ trong \`JobExecution\` có thể xuất hiện ở giao diện quản trị. Cần ngăn dữ liệu nhạy cảm vào exception message ngay từ nguồn.

## 15. Bảo vệ thread pool, partition và remote worker

Khi một Step dùng \`TaskExecutor\`, parallel flow, partitioning hoặc remote chunking, logging context có thể di chuyển giữa nhiều thread/process.

~~~text
JobExecution 801
   |
   +-- main thread: MDC(jobExecutionId=801)
   |
   +-- worker thread A
   |      MDC phải được set cho execution/partition tương ứng
   |
   +-- worker thread B
   |      không được giữ ID/field của task trước
   |
   +-- remote worker
          nhận correlation metadata an toàn qua message
~~~

Một \`TaskDecorator\` có thể copy MDC từ thread submit task rồi khôi phục snapshot trước đó trong \`finally\`; tuy nhiên **đừng chuyển toàn bộ MDC nếu nguồn đã có PII**, vì nó nhân rộng cùng dữ liệu qua nhiều task.

Với message tới remote worker, nên có envelope chỉ gồm:

~~~json
{
  "headers": {
    "jobExecutionId": "801",
    "stepExecutionId": "3401",
    "correlationId": "req-27",
    "partitionId": "part-02"
  },
  "payload": {
    "reference": "object-key-authorized-for-worker"
  }
}
~~~

Nếu payload chứa dữ liệu thực, đó là kênh nghiệp vụ riêng với yêu cầu bảo vệ của nó; ví dụ chỉ nhằm minh họa **không cần đưa dữ liệu nhạy cảm vào logging metadata**. Khi remote worker nhận ID, cần xác thực mối liên hệ với job được phân công, không tin mù quáng một header từ nguồn không đáng tin.

Thread pool tái sử dụng có thể gây hai lỗi đồng thời: log của job A mang \`jobExecutionId\` B, hoặc MDC nhạy cảm từ task trước bị giữ lại. Do đó cleanup/restore context là một phần của bảo mật, không chỉ là tính tiện dụng của logging.

## 16. Kiểm thử masking và chống rò rỉ bằng dữ liệu giả

Một cơ chế masking tốt cần có test ở **nơi dữ liệu rời ứng dụng**, không chỉ kiểm tra một hàm \`maskEmail()\` trả chuỗi dự kiến. Dùng chuỗi sentinel tổng hợp, ví dụ:

~~~text
email:       private.user@example.test
phone:       0901234567
token:       test_secret_DO_NOT_LOG_7f2a
paymentPan:  4111111111111111  (chỉ là dữ liệu giả kiểm thử)
~~~

Test không nên chứa credential production hoặc dữ liệu thật của khách hàng. Các sentinel có thể được chọn để tìm kiếm chính xác trong output log.

### Unit test cho redaction và HMAC

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class SafeLoggingValuesTest {

    @Test
    void redactsEmailWithoutLeakingLocalPartOrDomain() {
        assertEquals("[REDACTED_EMAIL]",
                SensitiveValues.redactedEmail(
                        "private.user@example.test"));
    }

    @Test
    void hmacReferenceIsDeterministicButDoesNotReturnRawId() {
        byte[] testKey =
                "this-is-a-synthetic-test-key-32plus-bytes"
                        .getBytes(StandardCharsets.UTF_8);

        LogReferenceGenerator generator =
                new LogReferenceGenerator(testKey);

        String first = generator.refForCustomer("customer-test-001");
        String second = generator.refForCustomer("customer-test-001");
        String other = generator.refForCustomer("customer-test-002");

        assertEquals(first, second);
        assertNotEquals(first, other);
        assertNotEquals("customer-test-001", first);
    }
}
~~~

Test kiểm tra tính xác định và việc không in giá trị gốc, **không chứng minh HMAC tự đủ để tuân thủ chính sách quyền riêng tư**. Secret trong ví dụ là chuỗi tổng hợp chỉ dùng cho unit test; production phải dùng cơ chế cấp khóa an toàn.

### Capture log từ Logback

Khi muốn biết log thực sự chứa gì, có thể dùng \`ListAppender<ILoggingEvent>\` của Logback trong test:

~~~java
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.slf4j.LoggerFactory;

Logger logger = (Logger) LoggerFactory.getLogger(
        ValidatingOrderProcessor.class);

ListAppender<ILoggingEvent> appender = new ListAppender<>();
appender.start();
logger.addAppender(appender);

try {
    // Chạy processor/Step với các sentinel giả.
    // Sau đó kiểm tra toàn bộ formatted message và MDC
    // của từng logging event được capture.
} finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

Đoạn trên là **khung test**, cần bổ sung cách chạy Step và các assertion của dự án. Nếu backend dùng async appender hoặc JSON encoder, nên kiểm tra **bytes đã encode hoặc output collector giả** để phát hiện các trường nằm ngoài \`formattedMessage\` (MDC, structured arguments, throwable và marker).

Một test kiểu “log không chứa token” phải kiểm tra cả:

- Formatted message.
- Throwable message và stack trace đã được encoder xuất.
- MDC map.
- Structured JSON fields.
- Output của logging HTTP/JDBC adapter nếu được bật.
- Failure/ExitStatus metadata nếu giao diện quản trị cũng hiển thị chúng.

### Ví dụ assertion dạng sentinel

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

String logText = capturedEncodedLog;

assertFalse(logText.contains("private.user@example.test"));
assertFalse(logText.contains("0901234567"));
assertFalse(logText.contains("test_secret_DO_NOT_LOG_7f2a"));
assertFalse(logText.contains("4111111111111111"));

assertTrue(logText.contains("jobExecutionId"));
assertTrue(logText.contains("reasonCode"));
~~~

\`capturedEncodedLog\` là biến minh họa chứa toàn bộ output đã encode của test, không phải API của Spring Batch. Kiểm tra sentinel cần giữ nguyên xác suất phát hiện: nếu dữ liệu có thể được escape, encode hoặc cắt thành nhiều đoạn, test nên kiểm tra những dạng xuất mà logger thực tế hỗ trợ.

## 17. Ma trận test theo luồng Spring Batch

| Tình huống | Dữ liệu giả đưa vào | Điều cần xác nhận |
|---|---|---|
| Item hợp lệ | Email, phone, token trong DTO | Log tiến độ không chứa raw fields |
| Validate lỗi | Amount âm, DTO có email | Exception message chỉ có reason code |
| Read skip | CSV lỗi số + cột có PII | Không log raw line hoặc \`getInput()\` |
| Process skip | \`SafeBatchItemException\` | Log reason code và safe reference |
| Write skip | Unique constraint trả lỗi có key | Không xuất raw exception detail |
| Retry API | HTTP client thấy Authorization header | Không log Authorization hoặc body |
| JobParameters | inputFile chứa username, secret được cấu hình sai | Không dump nguyên parameters |
| MDC | Hai execution chạy tuần tự trên cùng thread | ID không rò sang execution kế |
| Parallel Step | Hai worker thread và partition | Context đúng từng execution; không mang field nhạy cảm |
| Remote worker | Message có correlation metadata | Chỉ propagate allowlisted keys |
| Job FAILED | Listener và backend xuất stack trace | Không xuất PII trong error chain |
| Restart | Cùng JobInstance, hai JobExecution | Trace đúng từng attempt, không log payload cũ |
| Debug JDBC | Bật logging ở môi trường test | Không xuất bind values nhạy cảm |
| HTTP adapter | 4xx/5xx có response body chứa token | Không xuất raw response ở log |
| JSON logging | Encoder có MDC và structured args | Các field xuất ra đúng allowlist |
| Quarantine | Record lỗi chứa secret | Log chỉ có safe reference; storage bảo vệ riêng |
| Crash | Không chạy afterJob/afterStep | Không phụ thuộc vào log completion để kết luận kết quả |

Đặc biệt nên có test **job integration** bằng \`spring-batch-test\`: chạy job nhỏ qua \`JobLauncherTestUtils\`, tiêm các sentinel tại reader, processor, writer và lỗi skip, rồi capture log thực tế. Sau đó assert rằng JobExecution/StepExecution vẫn phản ánh đúng status, read/skip/write counters trong khi log không rò dữ liệu.

Không đánh giá masking chỉ bằng output đẹp trên console local: production có thể sử dụng appender, exporter hoặc logger library khác.

## 18. Defense in depth tại log pipeline và vận hành

Ngay cả khi code đã áp dụng allowlist, hạ tầng thu thập log cũng cần chính sách:

~~~text
Spring Batch application
     |
     +-- Safe event + safe exception + safe MDC
     |
     v
Logging backend / appender
     |
     +-- Structured schema, filter bổ sung
     v
Collector / forwarder
     |
     +-- Redaction bổ sung, TLS, access policy
     v
Central log storage
     |
     +-- RBAC, audit truy cập, retention, deletion workflow
     v
Alert / dashboard / incident workflow
~~~

Các điểm vận hành nên được thiết kế rõ:

**Quyền truy cập.** Người vận hành batch có thể cần xem status và reason code nhưng không cần quyền đọc toàn bộ dữ liệu nghiệp vụ. Phân quyền cho log store, quarantine store và JobRepository có thể khác nhau.

**Retention.** Log chỉ nên giữ trong khoảng thời gian phục vụ mục đích vận hành và yêu cầu quy định. Dữ liệu đã bị mask một phần không mặc nhiên được phép giữ vô hạn.

**Incident response.** Nếu phát hiện secret/PII đã lọt vào log: chặn nguồn rò rỉ, xác định hệ thống nhận log và phạm vi dữ liệu, xử lý rotation/revocation của secret, hạn chế truy cập, xóa/scrub theo quy trình được phép và ghi nhận sự cố. Việc đơn giản thay source code không xóa bản đã xuất.

**Kiểm soát thay đổi.** Mỗi khi thêm field vào DTO, JobParameter, exception, adapter HTTP/JDBC hoặc thay encoder, cần xem nó có thể xuất hiện trong log/trace/metadata không. Đây là một phần của quản lý thay đổi, không chỉ kiểm tra lúc đầu triển khai.

**Giới hạn debug.** Không mở logging \`TRACE\` toàn bộ batch hoặc HTTP body trên production để điều tra một lỗi cá biệt. Nếu buộc phải có chẩn đoán sâu, sử dụng môi trường kiểm thử, dữ liệu tổng hợp, thời hạn ngắn và phê duyệt phù hợp.

## 19. Những sai lầm thường gặp

**Log cả object rồi che bằng regex.** \`toString()\`, JSON field, throwable và MDC có thể lọt qua filter. Hãy dùng allowlist và safe event trước khi gọi logger.

**Mask số cuối và coi là an toàn tuyệt đối.** Một phần giá trị vẫn có thể nhận diện chủ thể hoặc vi phạm chính sách. Ưu tiên redact hoàn toàn hoặc omit.

**Dùng SHA-256 không khóa với email/số điện thoại.** Các giá trị này dễ đoán bằng từ điển. Nếu cần correlation, dùng HMAC có secret được bảo vệ và vẫn đánh giá nguy cơ nhận diện.

**Ghi exception thô trong read skip.** \`FlatFileParseException\` có thể mang raw input và exception chain. Log line number, error category và safe reference thay vì payload.

**Giữ secret trong JobParameters hoặc ExecutionContext.** Các giá trị có thể được lưu trong JobRepository, không chịu masking của Logback. Dùng secret manager thay vì truyền secret qua metadata.

**Đặt email hoặc token trong MDC.** MDC được đính kèm vào nhiều log liên tiếp; nếu quên cleanup, còn rò sang task khác.

**Chỉ bảo vệ code của mình.** JDBC, Hibernate, HTTP interceptor, SDK, database slow query log và tracing exporter có thể có log riêng.

**Log message từ exception rồi xem là reasonCode.** Message có thể chứa dữ liệu do thư viện hoặc input tạo. Dùng enum/constant đã kiểm soát.

**Xóa \`MDC.clear()\` tùy ý.** Có thể loại mất trace context của observability library. Restore snapshot hoặc remove key do ứng dụng đặt.

**Giả định JSON logging luôn xuất an toàn.** Encoder có thể tự include mọi MDC và structured argument. Kiểm tra bytes/fields được xuất.

**Đưa ID động chứa PII vào metric labels.** Tạo high-cardinality và nhân rộng thông tin nhạy cảm. Dùng log/traces/audit cho correlation chi tiết.

**Chỉ kiểm tra happy path.** Lỗi parse, rollback, API timeout, Job FAILED, retry và restart thường là lúc framework ghi nhiều thông tin nhất.

**Coi log redaction là thay thế kiểm soát truy cập.** Log đã giảm dữ liệu nhạy cảm vẫn cần TLS, RBAC, audit và retention.

**Không xử lý bản log đã bị lộ.** Sửa application chỉ chặn leak tiếp theo; cần quy trình incident response đối với các bản log đã được lưu hoặc chuyển tiếp.

## 20. Quy trình triển khai masking trong dự án Spring Batch

Một cách triển khai có thể chia thành các bước sau:

1. **Lập bản đồ luồng dữ liệu:** liệt kê reader, processor, writer, skip/retry/listener, các dependency và các log sink.
2. **Phân loại trường:** secrets, payment data, PII, business ID, metadata kỹ thuật, counter; xác định trường nào được phép ghi.
3. **Định nghĩa event schema allowlist:** \`event\`, \`jobExecutionId\`, \`stepExecutionId\`, \`phase\`, \`reasonCode\` và opaque reference khi thật sự cần.
4. **Làm exception an toàn:** chuyển lỗi của ứng dụng thành reason code không chứa payload; kiểm tra message và stack trace từ adapter.
5. **Bảo vệ fault-tolerance hooks:** \`SkipListener\`, retry logging, item/Chunk listener không dump raw input hay object.
6. **Chuẩn hóa MDC và JSON encoder:** chỉ thêm metadata được phép, dọn context sau xử lý, truyền context đúng qua thread và remote worker.
7. **Tắt payload debug ở production:** JDBC bind parameters, HTTP body/header và trace attributes nhạy cảm.
8. **Tách quarantine store khỏi log:** dữ liệu gốc cần phục hồi phải được lưu ở kho có phân quyền và retention riêng.
9. **Kiểm thử cả pipeline:** unit test redaction/HMAC, capture encoded log và integration test Job với sentinel ở các đường lỗi.
10. **Bảo vệ log backend:** collector redaction bổ sung, mã hóa truyền tải, RBAC, audit và quy trình xóa/incident.
11. **Đưa vào vòng đời thay đổi:** thêm field/adapter/logger mới phải được xem xét nguy cơ leak.

Nguyên tắc xuyên suốt là **không đưa dữ liệu nhạy cảm vào log ngay từ đầu**, thay vì trông chờ một bộ lọc cuối cùng tìm ra và che mọi biến thể. Trong Spring Batch, việc này càng quan trọng vì raw item, \`FlatFileParseException\`, JobParameters, ExecutionContext, retry/skip listener và log của thư viện có nhiều cơ hội để sao chép dữ liệu. Khi áp dụng allowlist, safe error code, MDC chỉ chứa metadata phù hợp, cùng kiểm thử cả đường lỗi và log pipeline, hệ thống vừa giữ được khả năng điều tra theo job execution ID vừa hạn chế rủi ro rò rỉ thông tin.
