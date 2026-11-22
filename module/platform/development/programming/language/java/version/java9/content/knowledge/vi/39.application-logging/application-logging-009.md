# Tránh dựng thông điệp tốn kém hoặc ghi dữ liệu nhạy cảm

## 1. Hai mục tiêu của logging an toàn

Logging phải giúp vận hành, gỡ lỗi và điều tra sự cố. Tuy nhiên, một câu lệnh log có thể tạo thêm chi phí CPU, cấp phát bộ nhớ, I/O và còn làm lộ dữ liệu nếu thông điệp chứa nội dung không phù hợp.

Khi thiết kế logging, cần giải quyết đồng thời hai vấn đề:

- **Hiệu quả:** chỉ thu thập và định dạng dữ liệu chẩn đoán khi mức log cần thiết đang được bật.
- **Bảo mật và riêng tư:** chỉ ghi những trường cần thiết cho mục đích đã xác định; loại bỏ hoặc biến đổi credential, secret và dữ liệu cá nhân nhạy cảm trước khi dữ liệu rời khỏi vùng xử lý.

Java có các API hỗ trợ tạo thông điệp lazy như \`Logger.log(Level, Supplier<String>)\`, \`Logger.fine(Supplier<String>)\` và \`Logger.isLoggable(Level)\`. Các overload Supplier của \`java.util.logging.Logger\` đã có từ Java 8; Java 9 tiếp tục hỗ trợ chúng. Java 9 cũng bổ sung \`System.Logger\`, có overload Supplier để tạo thông điệp lazy qua logging facade chuẩn.

Supplier chỉ giải quyết thời điểm tạo message. Nó không tự động loại bỏ secret, xác thực dữ liệu đầu vào, mã hóa output hay giới hạn quyền đọc log. Hai mục tiêu trên phải được thiết kế riêng và kết hợp.

## 2. Vì sao dựng thông điệp có thể tốn kém?

Một message log không phải lúc nào cũng chỉ là phép nối hai chuỗi. Việc tạo message có thể kéo theo:

- Duyệt collection lớn hoặc xây snapshot của object graph.
- Gọi \`toString()\` trên object phức tạp.
- Đọc trạng thái cache, queue, thread hoặc connection pool.
- Chuyển object thành JSON/XML hoặc serialize dữ liệu.
- Tính toán checksum, thống kê hoặc truy vấn chẩn đoán.
- Cấp phát nhiều chuỗi và object tạm.
- Đọc request/response body hoặc dữ liệu có kích thước không giới hạn.

Ví dụ eager:

~~~java
logger.fine("cache snapshot = " + buildCacheSnapshot());
~~~

Java đánh giá \`buildCacheSnapshot()\` và tạo chuỗi trước khi gọi \`fine(String)\`. Nếu mức FINE đang tắt, logger có thể loại bản ghi, nhưng phần công việc đã hoàn tất.

Dùng Supplier để trì hoãn:

~~~java
logger.fine(() -> "cache snapshot = " + buildCacheSnapshot());
~~~

Khi logger không bật FINE, Supplier không được gọi. Phép tính và phép nối chuỗi nằm bên trong lambda sẽ không chạy.

## 3. Supplier và isLoggable trong java.util.logging

Dạng tổng quát:

~~~java
logger.log(Level.FINE, () -> buildDiagnosticMessage());
~~~

Các convenience method cũng có overload Supplier:

~~~java
logger.fine(() -> buildDiagnosticMessage());
logger.finer(() -> buildDetailedDiagnosticMessage());
logger.finest(() -> buildTraceMessage());
~~~

Logger chỉ gọi Supplier khi effective level của logger chấp nhận mức được yêu cầu. Nếu level riêng của logger là \`null\`, nó kế thừa effective level từ logger cha gần nhất có level cụ thể.

Với một message, Supplier thường là đủ. Khi cần nhiều bước tốn kém, dùng \`isLoggable\` để bỏ qua toàn bộ khối:

~~~java
if (logger.isLoggable(Level.FINE)) {
    DiagnosticSnapshot snapshot = collectDiagnostics();
    String queueState = inspectQueue();
    logger.fine(() -> format(snapshot, queueState));
}
~~~

Trong ví dụ này, \`collectDiagnostics()\` và \`inspectQueue()\` chỉ chạy khi FINE đang bật. Supplier tiếp tục trì hoãn bước format message.

Không nên lặp kiểm tra mà không có lý do:

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine(() -> buildDiagnosticMessage());
}
~~~

Nếu chỉ cần một message lazy, gọi Supplier trực tiếp đã đủ. Dùng \`isLoggable\` khi phải chặn nhiều phép tính hoặc nhiều thao tác trước khi gọi logger.

## 4. Phân biệt Supplier với parameterized logging

Parameterized logging giúp tránh tự nối chuỗi:

~~~java
logger.log(Level.FINE, "Order {0} has status {1}",
        new Object[] { orderId, status });
~~~

Tuy nhiên, Java vẫn đánh giá các biểu thức tạo đối số trước khi gọi phương thức:

~~~java
logger.log(Level.FINE, "Snapshot: {0}",
        buildExpensiveSnapshot(order));
~~~

\`buildExpensiveSnapshot(order)\` vẫn chạy khi FINE tắt. Parameterized logging thường giúp trì hoãn việc định dạng chuỗi cuối cùng, nhưng không trì hoãn biểu thức tạo đối số.

Nếu việc tạo dữ liệu cũng tốn kém, dùng Supplier:

~~~java
logger.log(Level.FINE, () ->
        "Snapshot: " + buildExpensiveSnapshot(order));
~~~

Với SLF4J, Log4j hoặc framework khác, cú pháp placeholder và cơ chế lazy có thể khác nhau. Không giả định rằng mọi API đều có cùng overload Supplier. Dù dùng framework nào, biểu thức đối số Java vẫn được đánh giá trước lời gọi; hãy kiểm tra API cụ thể và đo hiệu năng trong cấu hình thực tế.

Parameterized logging cũng không tự ngăn log injection hoặc rò rỉ secret. Placeholder giữ template ổn định, nhưng giá trị truyền vào vẫn cần được xác thực, giới hạn và encode đúng định dạng output.

## 5. Chỉ ghi các trường cần thiết cho một sự kiện

Trước khi ghi log, xác định mục đích của event: debugging, vận hành, kiểm toán hay phát hiện sự cố bảo mật. Một event hữu ích thường có một tập trường nhỏ, ổn định:

| Nhóm | Trường có thể cần |
|---|---|
| Khi nào | Timestamp, timezone/UTC, event time |
| Ở đâu | Tên service, phiên bản ứng dụng, môi trường |
| Ai | Opaque account reference hoặc service identity nếu cần |
| Điều gì | Event name, action, outcome, reason code |
| Tương quan | Request ID, interaction ID hoặc trace ID |
| Mức độ | Severity và security-event classification |

Không phải mọi log đều cần tất cả các trường. Chỉ giữ trường phục vụ mục đích đã xác định. Tránh log toàn bộ object, toàn bộ request hoặc toàn bộ context chỉ vì chúng đang có sẵn.

Một event có cấu trúc ổn định sẽ dễ tìm kiếm và phân tích hơn một chuỗi tự do:

~~~text
event=auth.login_failed
account_ref=acct-42
reason=INVALID_PASSWORD
request_id=req-7f31
outcome=DENIED
~~~

Trong production, ưu tiên structured logging với schema rõ ràng và encoder JSON/format phù hợp. Dùng tên field cố định, giới hạn kiểu dữ liệu và độ dài. Không tự nối chuỗi thành JSON bằng tay; encoder cần escape giá trị đúng quy tắc JSON.

## 6. Những dữ liệu không nên ghi trực tiếp

Không ghi trực tiếp dữ liệu nếu mục đích, căn cứ pháp lý, quyền truy cập hoặc thời hạn lưu giữ chưa được xác định. Các nhóm sau thường phải được loại bỏ, mask, sanitize, pseudonymize, hash hoặc mã hóa trước khi ghi:

- Password, password reset token và mã xác thực một lần.
- Access token, refresh token, API key, session cookie và session ID.
- Private key, encryption key, signing key và secret cấu hình.
- Database connection string có username/password hoặc credential.
- Số thẻ thanh toán, thông tin tài khoản ngân hàng.
- Dữ liệu sức khỏe, định danh chính phủ và PII nhạy cảm.
- Request/response body, header \`Authorization\` hoặc \`Cookie\` nếu chứa credential.
- Dữ liệu thương mại hoặc dữ liệu có phân loại cao hơn hệ thống log được phép lưu.
- Thông tin người dùng không cần thiết cho mục đích vận hành hoặc điều tra.

Tên, email, số điện thoại, địa chỉ IP và file path cũng có thể là dữ liệu cá nhân hoặc thông tin nội bộ tùy bối cảnh. Không mặc định rằng một trường là an toàn chỉ vì nó không phải password.

Một quy tắc hữu ích: **ghi trạng thái và mã lý do, không ghi bí mật đã gây ra trạng thái đó**.

Ví dụ:

~~~java
// Không an toàn: có thể lộ password và token.
logger.warning("Login failed: username=" + username
        + ", password=" + password
        + ", accessToken=" + accessToken);

// Tốt hơn: chỉ ghi thông tin đã được cho phép.
logger.log(Level.WARNING, () ->
        "auth.login_failed accountRef=" + safeAccountRef
        + " reason=INVALID_PASSWORD");
~~~

Không truyền secret vào Supplier rồi cho rằng lazy evaluation khiến dữ liệu an toàn. Khi level bật, Supplier vẫn tạo message và secret có thể được ghi ra sink.

## 7. Masking, pseudonymization và correlation ID

Đôi khi cần liên kết nhiều event của cùng một session hoặc account mà không ghi định danh gốc.

Các lựa chọn:

- **Deletion:** bỏ trường nếu không cần correlation.
- **Masking:** chỉ giữ phần không nhạy cảm, ví dụ một phần mã tham chiếu theo policy.
- **Pseudonymization:** thay định danh trực tiếp bằng mã thay thế.
- **Keyed HMAC:** tạo fingerprint ổn định trong phạm vi key để correlation mà không lưu giá trị gốc.

Không dùng hash không khóa của giá trị có entropy thấp như email, số điện thoại hoặc mã tài khoản rồi coi đó là ẩn danh; người có danh sách ứng viên có thể dò ngược bằng dictionary. Nếu cần correlation, cân nhắc HMAC với key bí mật được quản lý ngoài log system:

~~~java
static String sessionFingerprint(
        String sessionId, SecretKey key)
        throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(key);

    byte[] digest = mac.doFinal(
            sessionId.getBytes(StandardCharsets.UTF_8));

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
}
~~~

Key phải đến từ secret manager hoặc cơ chế quản lý khóa phù hợp; không hard-code key trong source code, không ghi key vào log và giới hạn ai có thể dùng key. Cân nhắc version key và quy trình rotation để việc correlation không kéo dài quá mức cần thiết.

HMAC fingerprint vẫn là dữ liệu pseudonymous có thể liên kết hoạt động. Nó không tự động trở thành dữ liệu vô danh; vẫn phải áp dụng kiểm soát truy cập, mục đích sử dụng và thời hạn lưu giữ.

## 8. Ngăn log injection từ dữ liệu không tin cậy

Dữ liệu từ request, header, tên file, tên người dùng hoặc hệ thống bên ngoài phải được xem là untrusted. Ký tự CR (\`\\r\`) và LF (\`\\n\`) có thể làm một giá trị tạo thêm dòng log giả nếu output format là plain text.

Ví dụ đầu vào độc hại:

~~~text
acct-42
WARNING: admin login succeeded
~~~

Nếu ghi nguyên văn vào một dòng log, người đọc có thể hiểu nhầm dòng thứ hai là event thật do ứng dụng tạo.

Biện pháp phòng vệ:

1. Dùng structured logging và encoder đúng format.
2. Validate theo allowlist cho các trường có miền giá trị rõ ràng như event type, reason code, account reference.
3. Escape hoặc loại CR, LF, delimiter và control character trước khi ghi plain text.
4. Giới hạn độ dài từng trường và tổng kích thước event.
5. Không dùng dữ liệu đầu vào làm message template hoặc tên field.
6. Giữ template cố định và đưa dữ liệu vào field đã định nghĩa.

Ví dụ allowlist cho một opaque account reference:

~~~java
static String safeAccountRef(String value) {
    if (value == null || value.length() == 0 || value.length() > 32) {
        return "unknown";
    }

    for (int i = 0; i < value.length(); i++) {
        char ch = value.charAt(i);
        boolean allowed = (ch >= 'a' && ch <= 'z')
                || (ch >= 'A' && ch <= 'Z')
                || (ch >= '0' && ch <= '9')
                || ch == '_' || ch == '-';

        if (!allowed) {
            return "unknown";
        }
    }
    return value;
}
~~~

Allowlist này từ chối CR/LF, dấu cách và ký tự ngoài tập đã định nghĩa. Đây chỉ là policy cho một loại ID cụ thể; không áp dụng cùng regex cho mọi trường dữ liệu.

Sanitization không phải redaction. Thay CR/LF bằng dấu cách không loại bỏ password hoặc token. Cần xác định trường nào được phép xuất hiện trước, sau đó mới encode/sanitize theo output format.

## 9. Exception, toString và dữ liệu ẩn trong object

Không gọi \`toString()\` tùy tiện trên request, entity, credential holder hoặc object chứa nhiều field. \`toString()\` có thể:

- In toàn bộ field nhạy cảm.
- Gọi code tốn kém hoặc truy cập lazy-loaded data.
- Ném exception.
- Tạo chuỗi rất lớn.
- Bao gồm CR/LF hoặc nội dung do người dùng kiểm soát.

Hãy tạo event từ các field đã allowlist thay vì ghi nguyên object:

~~~java
logger.log(Level.FINE, () ->
        "payment.validation result=" + resultCode
        + " paymentRef=" + safePaymentReference);
~~~

Exception cũng có thể chứa dữ liệu nhạy cảm trong message, cause hoặc stack trace. Trước khi ghi throwable, kiểm tra nội dung và chính sách log của ứng dụng. Có thể ghi exception class, mã lỗi nội bộ và correlation ID; chỉ đính kèm stack trace khi sink được phép lưu và người đọc được kiểm soát.

~~~java
logger.log(Level.WARNING,
        "payment.gateway_failed code=" + safeErrorCode,
        sanitizedException);
~~~

Không tạo một exception mới chỉ để che nội dung rồi vô tình làm mất cause cần thiết. Hãy quyết định rõ exception nào được phép ghi, thông tin nào phải redact và nơi lưu stack trace.

## 10. Lazy logging không được làm mất security event

Supplier chỉ chạy khi logger bật mức tương ứng. Vì vậy, không đặt audit event bắt buộc hoặc security event cần giám sát ở mức debug có thể bị tắt trong production.

Ví dụ, debug snapshot có thể ở FINE:

~~~java
logger.fine(() -> buildDetailedDiagnostics());
~~~

Sự kiện đăng nhập thất bại theo policy ứng dụng có thể cần được ghi ở WARNING hoặc một audit channel riêng:

~~~java
logger.log(Level.WARNING, () ->
        "auth.login_failed accountRef=" + safeAccountRef
        + " reason=INVALID_PASSWORD");
~~~

Mức cụ thể phải theo phân loại event và chính sách vận hành. Không nâng mọi event lên WARNING để tránh bị tắt; điều đó tạo noise và làm mất ý nghĩa severity.

\`isLoggable\` kiểm tra effective level của Logger. Nó không bảo đảm Handler sẽ xuất bản record; Handler có level và Filter riêng. Nếu Logger chấp nhận message, Supplier có thể đã chạy trước khi Handler loại record. Điều này vừa ảnh hưởng chi phí, vừa có nghĩa là không thể dựa vào Handler filter như lớp bảo vệ duy nhất chống lộ secret.

Cấu hình logging cũng có thể thay đổi runtime. Kết quả \`isLoggable\` là snapshot tại thời điểm kiểm tra, không phải lock hoặc transaction bảo đảm lần log kế tiếp sẽ được xuất bản.

## 11. Kiểm soát khối lượng, quyền truy cập và thời hạn lưu giữ

Ngay cả log không chứa secret vẫn có thể tạo rủi ro nếu ghi quá nhiều hoặc bảo vệ kém.

- **Giới hạn kích thước:** cap độ dài field, message, stack trace và event tổng thể.
- **Rate limiting:** chống request gây log flood và cạn dung lượng.
- **Sampling:** dùng cho telemetry khối lượng lớn; không sampling tùy tiện security/audit event bắt buộc.
- **Access control:** chỉ cấp quyền đọc log cho nhóm cần thiết; review định kỳ.
- **Integrity:** phát hiện sửa/xóa trái phép nếu use case cần audit tin cậy.
- **Transport:** dùng kênh bảo mật khi chuyển log qua mạng không tin cậy.
- **Retention:** lưu đúng thời hạn theo mục đích, pháp luật và hợp đồng; không giữ vô thời hạn.
- **Failure handling:** lỗi của log sink không được làm lộ dữ liệu hoặc gây hỏng nghiệp vụ; quyết định fail-open/fail-closed theo loại event và yêu cầu audit.
- **Monitoring:** phát hiện logging dừng, lỗi ghi, dung lượng gần đầy hoặc quyền truy cập bất thường.

Không ghi log vào vị trí public web-accessible. Log và backup của log cũng cần cùng mức kiểm soát vì bản sao thường bị bỏ quên.

## 12. Ví dụ Java hoàn chỉnh: lazy diagnostics và event an toàn

Chương trình dùng \`java.util.logging\`. Nó chứng minh Supplier không chạy khi FINE tắt, chạy đúng một lần khi FINE bật và tạo security event từ các field được allowlist. Giá trị account reference chứa CR/LF bị từ chối thành \`unknown\`; chương trình không ghi password, session ID hay token.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeEfficientLoggingDemo {
    private static String safeAccountRef(String value) {
        if (value == null || value.length() == 0 || value.length() > 32) {
            return "unknown";
        }
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            boolean allowed = (ch >= 'a' && ch <= 'z')
                    || (ch >= 'A' && ch <= 'Z')
                    || (ch >= '0' && ch <= '9')
                    || ch == '_' || ch == '-';
            if (!allowed) {
                return "unknown";
            }
        }
        return value;
    }

    private static String safeReason(String value) {
        if ("INVALID_PASSWORD".equals(value)
                || "ACCOUNT_LOCKED".equals(value)
                || "MFA_REQUIRED".equals(value)) {
            return value;
        }
        return "OTHER";
    }

    private static String collectDiagnostics() {
        return "cacheEntries=12;queueDepth=3";
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger(
                "demo.safe.logging." + System.nanoTime());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + ": " + record.getMessage());
                }
            }

            @Override
            public void flush() { }

            @Override
            public void close() { }
        };
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger supplierCalls = new AtomicInteger();
        try {
            System.out.println("FINE enabled initially = "
                    + logger.isLoggable(Level.FINE));
            logger.log(Level.FINE, () -> {
                supplierCalls.incrementAndGet();
                return collectDiagnostics();
            });
            System.out.println("supplier calls while disabled = "
                    + supplierCalls.get());

            logger.setLevel(Level.FINE);
            System.out.println("FINE enabled after level change = "
                    + logger.isLoggable(Level.FINE));
            logger.log(Level.FINE, () -> {
                supplierCalls.incrementAndGet();
                return collectDiagnostics();
            });
            System.out.println("supplier calls after enabled = "
                    + supplierCalls.get());

            String untrustedAccountRef =
                    "acct-42\\r\\nWARNING: admin=true";
            String reason = "INVALID_PASSWORD";
            logger.log(Level.WARNING, () ->
                    "auth.login_failed accountRef="
                    + safeAccountRef(untrustedAccountRef)
                    + " reason=" + safeReason(reason));
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Lưu mã nguồn thành \`SafeEfficientLoggingDemo.java\`, biên dịch và chạy:

~~~bash
javac --release 17 -Xlint:all SafeEfficientLoggingDemo.java
java SafeEfficientLoggingDemo
~~~

Kết quả chính xác:

~~~text
FINE enabled initially = false
supplier calls while disabled = 0
FINE enabled after level change = true
FINE: cacheEntries=12;queueDepth=3
supplier calls after enabled = 1
WARNING: auth.login_failed accountRef=unknown reason=INVALID_PASSWORD
~~~

Mã nguồn tương thích với Java 9 và cũng có thể kiểm tra bằng:

~~~bash
javac --release 9 -Xlint:all SafeEfficientLoggingDemo.java
java SafeEfficientLoggingDemo
~~~

Ví dụ dùng một Handler tối giản để output ổn định. Trong production, Handler/Formatter/encoder phải được cấu hình theo định dạng, quyền truy cập, retention và quy trình thu thập log của ứng dụng. Allowlist trong ví dụ là policy cho account reference và reason code cụ thể; không thay thế kiểm soát dữ liệu cho các field khác.

## 13. Những lỗi thường gặp

- **Nối chuỗi trước khi gọi logger:** message và phép tính đã chạy dù level tắt; chuyển công việc vào Supplier.
- **Tính toán đắt đỏ trước lambda:** Supplier không thể trì hoãn một giá trị đã được tính; đưa phép tính vào lambda hoặc sau \`isLoggable\`.
- **Cho rằng parameterized logging trì hoãn đối số:** biểu thức đối số Java vẫn chạy trước lời gọi.
- **Dùng debug level cho audit event bắt buộc:** khi FINE/FINEST bị tắt, Supplier không chạy và event có thể mất.
- **Cho rằng Handler filter bảo vệ secret:** Supplier có thể đã được gọi trước khi Handler loại record.
- **Ghi toàn bộ request hoặc object:** có thể lộ password, token, cookie, PII và dữ liệu lớn.
- **Tin rằng placeholder chống log injection:** CR/LF vẫn có thể nằm trong giá trị; phải encode theo output format.
- **Chỉ sanitize mà không redact:** thay newline không loại bỏ secret hoặc PII.
- **Dùng hash không khóa cho định danh dễ đoán:** dữ liệu có thể bị dò ngược; cân nhắc HMAC với key quản lý an toàn.
- **Ghi exception message không kiểm tra:** message/cause/stack trace có thể chứa dữ liệu đầu vào hoặc credential.
- **Đặt side effect trong Supplier:** hành vi ứng dụng thay đổi theo logging level.
- **Không giới hạn độ dài và tần suất:** log flood có thể làm chậm ứng dụng hoặc cạn dung lượng.
- **Không bảo vệ backup và log sink:** dữ liệu đã redact một phần vẫn có thể nhạy cảm.
- **Coi isLoggable là synchronization:** kiểm tra level không khóa state và có thể khác trạng thái ở lần log sau.

## 14. Checklist khi review logging

1. Mỗi event có mục đích vận hành, bảo mật hoặc kiểm toán rõ ràng không?
2. Message có đang được tạo eager khi level tắt không?
3. Supplier có chứa toàn bộ phép tính tốn kém cần trì hoãn không?
4. Có dùng \`isLoggable\` cho nhiều bước tốn kém và tránh kiểm tra dư thừa không?
5. Security/audit event bắt buộc có bị đặt ở debug-only level không?
6. Các field đã được allowlist và giới hạn độ dài chưa?
7. Password, token, session ID, key, payment data và PII nhạy cảm đã được loại bỏ hoặc biến đổi chưa?
8. Untrusted data đã được validate và encode để ngăn CR/LF hoặc delimiter injection chưa?
9. Structured encoder có đúng output format không?
10. Exception, \`toString()\`, request body và header có thể làm lộ dữ liệu không?
11. Log volume, retention, access control, transport và backup đã được kiểm soát chưa?
12. Có test logging disabled, logging enabled, input chứa CR/LF, field quá dài, secret và log sink failure không?

## 15. Tài liệu tham khảo

- [Logger — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/util/logging/Logger.html)
- [Logger — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.logging/java/util/logging/Logger.html)
- [System.Logger — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/System.Logger.html)
- [System.Logger — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.Logger.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [CWE-117: Improper Output Neutralization for Logs](https://cwe.mitre.org/data/definitions/117.html)