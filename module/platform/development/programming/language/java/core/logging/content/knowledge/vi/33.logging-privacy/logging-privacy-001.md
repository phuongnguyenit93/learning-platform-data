# Dữ liệu cá nhân trong log — Java Core Logging

## 1. Vấn đề cốt lõi: log hữu ích nhưng có thể tạo ra một bản sao dữ liệu nhạy cảm

Logging giúp điều tra lỗi, đo hoạt động hệ thống và truy vết một request. Tuy nhiên, log cũng có thể trở thành **một kho dữ liệu cá nhân ngoài ý muốn**. Thông tin từ request, đối tượng Java, exception hoặc HTTP client có thể đi vào console, file, hệ thống tổng hợp log, dashboard, bản sao lưu và kênh cảnh báo. Mỗi nơi lại có người được truy cập và thời hạn lưu giữ riêng.

**Dữ liệu cá nhân** không chỉ là họ tên hay số điện thoại. Dữ liệu có thể nhận diện một người **trực tiếp hoặc khi kết hợp với nguồn khác**. Ví dụ cần đánh giá theo ngữ cảnh:

- Họ tên, email, số điện thoại, địa chỉ, ngày sinh, mã định danh, số tài khoản hoặc thông tin thanh toán.
- Địa chỉ IP, vị trí, định danh thiết bị, cookie, session ID, user ID và các mã có thể liên kết với hồ sơ cá nhân.
- Nội dung tin nhắn, biểu mẫu, yêu cầu hỗ trợ, hồ sơ sức khỏe hoặc thông tin tài chính.
- Access token, API key, mật khẩu, mã khôi phục: đây còn là **bí mật xác thực**; rò rỉ chúng có thể dẫn đến chiếm quyền truy cập.
- Định danh giả hoặc giá trị đã băm: chưa chắc đã ẩn danh nếu vẫn liên kết được với một cá nhân.

**Nguyên tắc nền tảng:** chỉ log những gì cần thiết cho mục đích vận hành đã xác định. Cách an toàn nhất thường là **không đưa dữ liệu cá nhân vào log ngay từ đầu**; masking, redaction và quyền truy cập là các lớp bảo vệ bổ sung, không thay thế tối thiểu hóa dữ liệu.

Bài này tập trung vào cách thiết kế và vận hành logging trong Java Core; chính sách pháp lý cụ thể phụ thuộc quốc gia, ngành, loại dữ liệu và tổ chức. Không nên suy diễn rằng một biện pháp kỹ thuật đơn lẻ tự động đáp ứng mọi nghĩa vụ bảo vệ dữ liệu.

## 2. Dữ liệu lọt vào log qua những đường nào?

| Đường rò rỉ | Ví dụ hay gặp | Rủi ro |
| --- | --- | --- |
| Nối chuỗi trực tiếp | `logger.info("email=" + email)` | Định danh được sao chép sang nhiều đích log |
| Log nguyên DTO/record | `logger.info("request=" + request)` | `toString()` có thể in toàn bộ field |
| HTTP request/response | Log URL có query string, header hoặc body | Token, cookie, địa chỉ và thông tin biểu mẫu bị lộ |
| Exception | `logger.log(Level.WARNING, "failed", exception)` | Message hoặc stack trace có thể chứa dữ liệu đầu vào |
| SQL và tham số | In nguyên query cùng parameter | Giá trị khách hàng xuất hiện trong log |
| MDC / ThreadContext | Đưa email, số điện thoại vào context | Mọi event trong cùng scope có thể lặp lại PII |
| Log collector/APM | Forward event đến dịch vụ thứ ba | Tăng số bản sao, quyền truy cập và vị trí lưu |
| Công cụ debug | Dump object, heap hoặc payload khi lỗi | Dữ liệu nằm trong file tạm, ticket hoặc chat hỗ trợ |

Một lỗi đặc biệt phổ biến trong Java là **`record.toString()` tự sinh**. Với:

~~~java
record SignUpRequest(String fullName, String email, String phone) {}
~~~

biểu thức `request.toString()` chứa tên field và giá trị tương ứng. Trong ứng dụng thật, có thể còn password hoặc token. Vì vậy, không dùng nguyên `request`, `response`, `headers` hay `context` làm đối số log nếu chưa có chính sách phân loại trường.

**MDC không phải vùng an toàn:** nó giúp gắn metadata với log event, nhưng nếu chứa email hoặc ID cá nhân, dữ liệu có thể được đưa vào tất cả appender/layout có pattern đọc MDC. Context cũng có nguy cơ bị truyền sai giữa các thread nếu không được khôi phục/xóa đúng cách.

## 3. Thiết kế trước khi chọn thư viện: mục đích, tập trường và mức độ

Trước khi viết `LOGGER.info(...)`, hãy xác định log sẽ trả lời câu hỏi vận hành nào.

| Câu hỏi vận hành | Trường nên cân nhắc ghi | Trường thường không cần |
| --- | --- | --- |
| Request có hoàn thành không? | Request ID, trạng thái, duration, mã lỗi ổn định | Họ tên, email, toàn bộ body |
| Thành phần nào lỗi? | Service, logger, error code, operation | Token, password, dữ liệu biểu mẫu |
| Tỷ lệ lỗi đăng ký? | Số lượng thành công/thất bại, mã nguyên nhân chuẩn hóa | Danh sách người đăng ký |
| Có retry hoặc timeout không? | Operation, attempt, timeout category, trace ID | URL chứa query nhạy cảm, request headers |
| Có hành vi bảo mật cần kiểm toán? | Actor ID theo chính sách, action, timestamp, outcome | Bí mật xác thực, toàn bộ payload |

Đây là **gợi ý kỹ thuật**, không phải danh sách luôn an toàn trong mọi tình huống. Một request ID hoặc user ID cũng có thể là dữ liệu cá nhân khi liên kết với account hoặc hồ sơ. Cần phân loại, giới hạn nơi dùng và thời gian lưu ngay cả với ID dạng opaque.

Nên xây dựng **schema sự kiện allowlist** cho log quan trọng:

~~~text
event=registration_completed
requestId=<opaque request identifier>
outcome=SUCCESS
durationMs=<number>
errorCode=<stable code, if applicable>
~~~

Đối với log thông thường, không thêm `email`, `phone`, `address`, `authorization`, `cookie`, `rawRequest` hay `exceptionMessage` chỉ vì chúng dễ lấy. Đối với audit event bắt buộc có định danh chủ thể, hãy thiết kế **luồng lưu riêng** với chính sách truy cập, retention, integrity và xử lý yêu cầu dữ liệu riêng.

## 4. Ví dụ Java 17 chạy độc lập: chỉ ghi những trường được cho phép

Chương trình dưới đây dùng `java.util.logging` (JUL), không cần thư viện ngoài. Dữ liệu đăng ký giả có tên, email và số điện thoại; ứng dụng sử dụng email để quyết định kết quả, nhưng log chỉ phát **mã yêu cầu của bản demo** và **trạng thái theo enum**.

Tạo file `PrivacySafeLoggingDemo.java`:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PrivacySafeLoggingDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.privacy.registration");

    record SignUpRequest(String fullName, String email, String phone) {}

    enum Outcome {
        ACCEPTED, REJECTED
    }

    private static void configureLogging() {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOGGER.addHandler(handler);
    }

    private static void logRegistration(String requestId, Outcome outcome) {
        if (requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,40}")) {
            throw new IllegalArgumentException("Invalid request ID");
        }

        LOGGER.log(Level.INFO,
                "registration requestId={0} outcome={1}",
                new Object[] {requestId, outcome});
    }

    public static void main(String[] args) {
        // Du lieu gia: khong in SignUpRequest hay tung field PII.
        SignUpRequest request = new SignUpRequest(
                "Example Person", "person@example.test", "+00-000-000-000");

        configureLogging();
        try {
            Outcome outcome = request.email() != null
                    && request.email().contains("@")
                    ? Outcome.ACCEPTED : Outcome.REJECTED;

            // Hang so chi phuc vu demo; request ID thuc can duoc cap
            // theo luong request va quan ly nhu metadata co the lien ket.
            logRegistration("req-demo-001", outcome);
        } finally {
            for (Handler handler : LOGGER.getHandlers()) {
                handler.flush();
                LOGGER.removeHandler(handler);
                handler.close();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac PrivacySafeLoggingDemo.java
java PrivacySafeLoggingDemo
~~~

**Stdout:** trống.

**Stderr chính xác** khi chạy chương trình demo:

~~~text
INFO: registration requestId=req-demo-001 outcome=ACCEPTED
~~~

Trong JUL, `ConsoleHandler` mặc định ghi vào **stderr**. Formatter tùy chỉnh dùng `formatMessage(record)` để thay `{0}`, `{1}` bằng các tham số, do đó thông điệp đầu ra có định dạng ổn định và không chứa họ tên/email/số điện thoại giả.

### Vì sao ví dụ hạn chế rò rỉ?

1. Dữ liệu cá nhân có trong `SignUpRequest` nhưng **không được đưa vào message hoặc parameter** của lời gọi log.
2. Event chỉ chứa `requestId` và `Outcome`, đều có kiểu/phạm vi được kiểm soát. ID mẫu chỉ để minh họa, **không được dùng cố định cho mọi request trong production**.
3. `requestId` có kiểm tra ký tự và độ dài để tránh giá trị tùy ý chen newline hoặc chuỗi quá lớn vào log. Kiểm tra này không biến ID thành “phi cá nhân”.
4. `LOGGER.setUseParentHandlers(false)` tránh đưa event ra handler của logger cha trong demo; không mặc định rằng tắt kế thừa handler là chính sách phù hợp cho mọi ứng dụng.
5. `try/finally` đóng các handler demo để bảo đảm vòng đời tài nguyên. Trong ứng dụng lớn, nên để logging backend/framework quản lý handler.

**Giới hạn:** bài chỉ chứng minh cách **không đưa dữ liệu cá nhân vào một log event được phát từ code trên**. Nó không tự chứng minh toàn bộ ứng dụng, thư viện, reverse proxy hoặc log collector đều không ghi dữ liệu cá nhân. Request ID cũng cần phân loại và quản lý đúng mục đích.

## 5. Đối chiếu: cách viết không nên dùng và cách viết nên ưu tiên

### Không nên ghi nguyên object hoặc dữ liệu đầu vào

~~~java
// Doan minh hoa KHONG AN TOAN; khong nen dung trong production.
LOGGER.info("signup=" + request);
LOGGER.info("email=" + request.email());
LOGGER.info("phone=" + request.phone());
~~~

Đây là đoạn tích hợp minh họa **để nhận diện lỗi**, không phải chương trình độc lập. Biểu thức `request` có thể gọi `toString()` tự sinh của Java record; nội dung sẽ không chỉ dừng ở mã lỗi vận hành.

### Ưu tiên event theo tập trường cho phép

~~~java
// Doan tich hop minh hoa: requestId va outcome da duoc tao,
// kiem tra va phan loai theo chinh sach log cua ung dung.
LOGGER.log(Level.INFO,
        "signup requestId={0} outcome={1}",
        new Object[] {requestId, outcome});
~~~

Không có trường email/phone trong thông điệp. Nếu cần số lượng sự kiện, latency hoặc error category, hãy bổ sung **trường được chuẩn hóa**, thay vì đưa toàn bộ DTO vào.

### Tránh exception làm lộ dữ liệu

Lệnh sau có thể hữu ích trong một số tình huống nhưng phải đánh giá nguồn exception:

~~~java
// Can review truoc khi dung voi input nhay cam.
LOGGER.log(Level.WARNING, "Request failed", exception);
~~~

Một số exception chứa raw URL, query parameter, dữ liệu gửi lên, đoạn SQL hoặc tên file cá nhân trong `getMessage()`; stack trace có thể đưa thêm context. Có thể thay bằng `errorCode` ổn định và log stack trace chi tiết trong một **kênh chẩn đoán giới hạn quyền**, khi thật sự cần và đã kiểm tra dữ liệu.

Không được coi việc đổi tên message từ `email` sang `user`, hoặc chỉ loại đi một số ký tự, là đã bảo đảm quyền riêng tư.

## 6. Redaction, masking, tokenization và pseudonymization

Nếu có yêu cầu nghiệp vụ chính đáng phải đưa một dạng dữ liệu vào log, cần phân biệt biện pháp:

| Biện pháp | Ý tưởng | Giới hạn |
| --- | --- | --- |
| **Data minimization** | Không ghi field không cần thiết | Cần thiết kế schema từ đầu; là biện pháp ưu tiên |
| **Redaction** | Xóa hoặc thay hoàn toàn một trường trước khi xuất | Phải chắc mọi đường ghi đều áp dụng; dễ bỏ sót dữ liệu không cấu trúc |
| **Masking** | Chỉ giữ một phần giá trị, ví dụ vài ký tự cuối | Giá trị còn lại vẫn có thể nhận diện hoặc liên kết |
| **Tokenization** | Thay bằng token; bảng ánh xạ lưu riêng | Token và kho ánh xạ cũng cần bảo vệ |
| **Pseudonymization** | Dùng định danh thay thế để giảm việc nhận diện trực tiếp | Dữ liệu vẫn có thể liên kết với người thật |
| **Aggregation** | Ghi số lượng/tỷ lệ thay vì từng người | Nhóm nhỏ hoặc metadata kết hợp vẫn có thể tiết lộ |
| **Encryption** | Bảo vệ dữ liệu khi truyền/lưu trữ | Người có quyền giải mã vẫn có thể thấy; không giảm dữ liệu đã thu thập |

**Một bẫy phổ biến là băm email:**

~~~text
hash(email) -> ma co dinh
~~~

Một hash thuần của email hoặc số điện thoại **không tự trở thành dữ liệu vô danh**. Các giá trị đầu vào có không gian đoán được và hash cố định có thể cho phép đối chiếu từ điển hoặc theo dõi lâu dài giữa các sự kiện. Khi thật sự cần ID giả có tính ổn định, có thể cân nhắc **HMAC với khóa được quản lý riêng**, giới hạn mục đích, vòng đời/rotation của khóa và quyền truy cập. Ngay cả khi có HMAC, kết quả có thể vẫn là dữ liệu cá nhân theo ngữ cảnh vì còn khả năng liên kết.

Masking từng phần, ví dụ số điện thoại dạng `******1234`, cũng không mặc nhiên an toàn nếu kết hợp timestamp, vị trí, thiết bị và các nguồn khác. Lựa chọn tốt nhất vẫn là **không ghi trường đó** khi mục đích vận hành không cần.

### Đặt redaction ở lớp nào?

Nên áp dụng nhiều lớp, có thứ tự ưu tiên:

1. **Ở caller/schema log:** chỉ chọn trường đã được phép; nguồn không đưa PII vào event.
2. **Ở logging backend:** filter/layout/encoder có thể che những pattern đã biết như lớp bảo vệ thứ hai.
3. **Ở collector:** kiểm tra, loại/redact lại trước lưu dài hạn hoặc gửi sang hệ thống khác.
4. **Ở downstream:** phân quyền, retention, cảnh báo và cơ chế xóa đối với dữ liệu đã được ghi.

Dùng một regex toàn cục “che mọi email/số điện thoại” thường **không đủ**: giá trị có thể phân mảnh, encode, nằm trong JSON, exception, query URL hoặc theo định dạng địa phương không được regex bắt. Regex cũng có thể che nhầm thông tin phục vụ điều tra. Hãy ưu tiên schema rõ ràng và test theo tình huống thực tế.

## 7. Structured logging: hữu ích nếu schema đúng, rủi ro nếu schema rộng

Một sự kiện có cấu trúc có thể được lưu dưới dạng JSON tương tự:

~~~json
{
  "event": "registration_completed",
  "requestId": "req-demo-001",
  "outcome": "ACCEPTED",
  "durationMs": 31,
  "errorCode": null
}
~~~

Dữ liệu ở trên là ví dụ JSON minh họa, không phải output của chương trình JUL ở mục 4. Các field được đưa vào có kiểm soát.

Những lợi ích chính:

- Có thể lọc, đếm, dựng biểu đồ theo `event`, `outcome`, `errorCode` mà không cần parse văn bản tùy ý.
- Từng field có thể được phân loại và áp chính sách masking, retention hoặc quyền truy cập.
- Tránh việc kỹ sư dùng `toString()` của object tùy ý để lấy nhanh “mọi thứ”.

Tuy nhiên, **structured logging không tự động làm log an toàn**. Nếu serialize toàn bộ `request` sang JSON, ta chỉ chuyển sự rò rỉ sang định dạng có cấu trúc. Cần cấu hình **allowlist schema** và kiểm tra thư viện/encoder có tự thêm header, MDC, exception hoặc thông tin thiết bị hay không.

Với SLF4J, lời gọi như sau vẫn có nguy cơ:

~~~java
// Doan tich hop: can SLF4J va backend.
logger.info("Signup request={}", request);
~~~

Placeholder tránh nối chuỗi sớm, **không ngăn object bị chuyển thành chuỗi** khi log được format. Cũng không nên nghĩ rằng logger ở `DEBUG` nên mọi thông tin nhạy cảm sẽ mãi vô hình; level có thể được đổi khi điều tra sự cố.

## 8. Request ID, trace ID, user ID và MDC

**Correlation ID** có ích để nối các event thuộc cùng một request mà không log payload. Nhưng cách sử dụng cần cẩn trọng:

- **Request ID/trace ID:** thường là mã ngẫu nhiên/opaque cho một luồng xử lý; không nên nhúng email, phone hoặc thông tin có thể đoán được vào chính mã.
- **User ID:** dù không phải tên/email, vẫn có thể xác định cá nhân qua hệ thống nội bộ. Phải phân loại và bảo vệ như một định danh có thể liên kết.
- **Session ID/cookie/access token:** là thông tin xác thực hoặc truy cập; **không** dùng làm correlation ID và không log nguyên văn.
- **MDC:** là kho context thường gắn với thread và được layout truy xuất; cần chỉ đưa dữ liệu đã được phê duyệt và dọn context ở cuối scope.

Ví dụ mã tích hợp với SLF4J MDC:

~~~java
// Doan tich hop; can org.slf4j.MDC va backend tuong thich.
// requestId la ID opaque da duoc tao/kiem tra cho request nay.
try {
    org.slf4j.MDC.put("requestId", requestId);
    // Xu ly request; log theo schema da duoc phe duyet.
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Trong thread pool, thread có thể được tái sử dụng. Thiếu `finally` có thể làm context request trước xuất hiện ở log của request sau. Khi xử lý async, propagation phải do ứng dụng/framework quản lý; không giả định context tự chuyển an toàn giữa các thread.

### Log injection cũng là vấn đề liên quan

Nếu buộc phải in một chuỗi do người dùng cung cấp, các ký tự `\r`, `\n` hoặc control character có thể khiến một message trông giống **nhiều log event** hoặc làm hỏng cấu trúc parser. Phải dùng encoder/escaping và giới hạn độ dài phù hợp. Nhưng **escape newline không loại bỏ PII**; hai yêu cầu bảo mật này độc lập. Nếu chuỗi không cần cho chẩn đoán, **không đưa nó vào log** vẫn tốt hơn.

## 9. Log đi qua nhiều hệ thống: kiểm soát cả pipeline

Một ứng dụng không nhất thiết là nơi duy nhất lưu event:

~~~text
Java code
    |
    v
Logger -> Handler/Appender
    |
    +--> Console / stdout / stderr
    |        |
    |        +--> Container runtime / agent -> Collector
    |
    +--> Local files -> Backup / log shipper
    |
    +--> Remote exporter -> Search / Dashboard / Alerts
~~~

Vì vậy, đánh giá rủi ro phải bao gồm **nơi dữ liệu đến**, không chỉ code Java.

**Các câu hỏi cần trả lời:**

1. Ai có thể xem log ở terminal, server, collector, dashboard, ticket hoặc alert chat?
2. Log có được mã hóa trong lúc truyền và lưu không? Khóa do ai quản lý?
3. Mỗi loại log có thời hạn lưu trữ và cơ chế xóa nào? Rotation file chỉ là quản lý dung lượng, **không tự đáp ứng chính sách xóa trên backup và collector**.
4. Khi có yêu cầu xóa/giới hạn dữ liệu, có biết log đang nằm ở những hệ thống và bản sao nào không?
5. Có giới hạn dữ liệu log đưa vào hệ thống thứ ba hay vùng lưu trữ khác không?
6. Ai được phép bật `DEBUG`/`TRACE`, trong bao lâu, và có audit cho lần thay đổi đó không?
7. Nếu event bị gửi qua nhiều appender, có phát sinh bản sao ở hơn một kho mà chưa có kế hoạch kiểm soát không?

Cần tách vai trò: **người phát log**, **đội vận hành log pipeline** và **người đọc dữ liệu** có quyền khác nhau. Quyền đọc rộng cho mọi thành viên dự án là rủi ro, kể cả khi file chỉ chứa “một ít thông tin”.

## 10. Chính sách logging theo môi trường và vòng đời

Môi trường phát triển không miễn trừ trách nhiệm dữ liệu. Ví dụ dữ liệu production copy sang staging để debug có thể khiến PII xuất hiện ở một hệ thống với quyền truy cập khác. Khi thử nghiệm, ưu tiên **dữ liệu tổng hợp hoặc dữ liệu giả** thay vì đưa bản ghi thật vào file log.

Các thực hành quan trọng:

- **Default an toàn:** level, schema và appender mặc định không log payload hay secret.
- **Điều tra sự cố có kiểm soát:** khi cần tăng verbosity, xác định phạm vi, thời lượng và người duyệt, rồi hoàn nguyên.
- **Retention theo mục đích:** log để giám sát thời gian thực và audit trail có thể cần chính sách lưu trữ khác nhau.
- **Separation of duties:** người thay đổi pipeline không nhất thiết được xem tất cả dữ liệu log.
- **Sao lưu và xuất dữ liệu:** giới hạn quyền, theo dõi hoạt động tải log, tránh tự động gửi event có PII qua email/ticket.
- **Theo dõi cả log lỗi:** exception và error handler thường chứa nhiều context nhạy cảm hơn log ở đường thành công.

Trong trường hợp cần ghi một số định danh, hãy ghi lại **quyết định thiết kế**: mục đích, field được phép, hệ thống nhận, retention, kiểm soát truy cập và cách xử lý xóa/chỉnh sửa theo quy định áp dụng.

## 11. Kiểm thử: đừng chỉ kiểm tra rằng log “có chạy”

Kiểm thử bảo mật logging nên xem **sự vắng mặt của thông tin không được phép** là yêu cầu thực tế.

### 11.1. Bài kiểm tra với dữ liệu giả có marker

Trong môi trường test, tạo bộ dữ liệu giả với các chuỗi sentinel dễ nhận biết, ví dụ:

~~~text
name=Example Person
email=person@example.test
phone=+00-000-000-000
secret=TEST_ONLY_SECRET_SENTINEL
~~~

Đây là chuỗi giả dành cho kiểm thử, **không phải thông tin thật hay bí mật production**. Chạy các luồng tạo log và kiểm tra output từ mọi đích được kiểm thử **không chứa** các chuỗi cấm. Cần kiểm tra cả error path, retry, exception, timeout, validation failure và HTTP logging filter.

Một kiểm tra đơn giản đối với chuỗi log đã thu được trong test:

~~~java
// Doan tich hop vao test, khong phai chuong trinh doc lap.
// capturedLog la chuoi event thu duoc tu appender test.
if (capturedLog.contains("person@example.test")
        || capturedLog.contains("TEST_ONLY_SECRET_SENTINEL")) {
    throw new AssertionError("Sensitive test marker appeared in logs");
}
~~~

Kỹ thuật này có tác dụng phát hiện **một số đường rò cụ thể**, không chứng minh rằng mọi kiểu dữ liệu cá nhân đều được ngăn chặn. Kết hợp với kiểm tra schema, review code và kiểm thử cả downstream collector.

### 11.2. Test schema và các trường cấm

Có thể coi từng event là một record có các key cho phép. Ví dụ `registration_completed` chỉ được mang `event`, `requestId`, `outcome`, `durationMs`. Nếu backend ghi thêm `email`, `password`, `authorization`, `cookie` hoặc một object lồng chưa duyệt, test phải fail.

Nên kiểm thử thêm:

- `toString()` từ record/DTO có field mới sau khi model thay đổi.
- Exception message chứa parameter, URL, tên file hoặc thông tin nhận diện.
- MDC tồn dư giữa hai request liên tiếp trên cùng worker thread.
- Event được ghi vào nhiều appender có encoder/layout khác nhau.
- Debug level được bật trong test, vì nhiều rò rỉ bị ẩn khi chạy `INFO`.
- Đầu vào có newline/control character và chuỗi quá dài để kiểm tra log injection/DoS.

## 12. Khi phát hiện PII trong log, cần xử lý thế nào?

Không chỉ xóa một lời gọi logger rồi coi sự cố đã kết thúc. Một quy trình xử lý thực tế gồm:

1. **Ngăn log mới chứa dữ liệu:** sửa caller/schema, disable đường dump không cần thiết hoặc điều chỉnh cấu hình trong phạm vi được phép.
2. **Xác định phạm vi:** event nào, khoảng thời gian nào, logger/appender nào, file/collector/backup nào nhận dữ liệu.
3. **Hạn chế truy cập:** tạm giảm quyền đọc hoặc chia sẻ thông tin sự cố qua kênh có kiểm soát, tránh paste lại PII vào issue.
4. **Đánh giá mức độ ảnh hưởng** theo chính sách bảo mật và nghĩa vụ áp dụng; phối hợp với người phụ trách bảo mật/quyền riêng tư.
5. **Xử lý bản sao đã có:** thực hiện quy trình loại bỏ/giới hạn lưu trữ nếu được phép, cân nhắc backup, snapshot, index và bản xuất.
6. **Nếu bí mật xác thực bị lộ:** đánh giá nhu cầu thu hồi/rotate token, key hoặc credential theo quy trình an toàn.
7. **Chặn tái diễn:** bổ sung regression test, allowlist schema, review logging và giám sát biến đổi level/config.

Không dùng một câu trả lời chung rằng “đã mask dữ liệu trong dashboard” để kết luận nguồn log ban đầu hay backup đã sạch. Mỗi tầng cần được xác minh theo khả năng truy cập và chính sách của nó.

## 13. Những lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách tránh |
| --- | --- | --- |
| `logger.debug("request=" + request)` | DTO chứa nhiều field hơn người viết nghĩ | Chỉ log event theo allowlist |
| Tin rằng `DEBUG` hiện đang tắt là an toàn | Level có thể bật, đối số Java có thể được tính trước lời gọi | Không đưa secret/PII vào event dù ở mức thấp |
| Ghi email vào MDC | Một giá trị lan ra nhiều dòng log và nhiều appender | Dùng correlation ID phù hợp, dọn context |
| Hash email rồi coi là ẩn danh | Có thể đoán hoặc đối chiếu, vẫn liên kết được | Tối thiểu hóa; nếu cần pseudonym, thiết kế có kiểm soát |
| Chỉ dựa vào regex redaction | Bỏ sót định dạng, lỗi exception, URL hoặc dữ liệu lồng | Filter tại nguồn + schema + lớp dự phòng |
| Ghi raw exception mà không review | Message/stack trace chứa input, header, query hoặc chi tiết cá nhân | Error code chuẩn; stack trace theo kênh kiểm soát |
| Bỏ qua stdout/stderr của container | Collector tự động chuyển tiếp log lên kho khác | Kiểm soát toàn bộ pipeline |
| Xóa file local rồi coi là đã xóa log | Có bản sao ở collector, backup hoặc alert | Quản lý retention và deletion đa tầng |
| Lưu token để tiện correlation | Token có thể cấp quyền truy cập | Dùng ID riêng, không log token |
| Log mọi request body lúc có sự cố | Nhân bản dữ liệu của nhiều người không liên quan | Giới hạn phạm vi; dùng dữ liệu giả hoặc metric |
| Log ID người dùng “vô hại” | Có thể nối sang hồ sơ thật | Phân loại ID, giảm trường và giới hạn retention |

## 14. Checklist áp dụng cho dự án Java

- [ ] Xác định rõ mục đích của từng loại log và ai sẽ dùng.
- [ ] Liệt kê field được phép ghi cho từng event; không log toàn bộ DTO hoặc HTTP payload.
- [ ] Kiểm tra các lời gọi `toString()`, string concatenation, exception, header và SQL parameter.
- [ ] Dùng request/trace ID phù hợp; không dùng session token/cookie làm ID.
- [ ] Kiểm tra MDC/ThreadContext và việc cleanup khi dùng thread pool/async.
- [ ] Kiểm tra formatters/encoders và mọi appender, kể cả đường lỗi.
- [ ] Ưu tiên tối thiểu hóa từ caller; masking/redaction chỉ là lớp bổ sung.
- [ ] Quy định quyền truy cập, mã hóa, retention và kiểm soát bản sao trong collector/backup.
- [ ] Viết test với sentinel giả để phát hiện PII/secret lọt vào log.
- [ ] Kiểm thử khi bật level chi tiết và khi xảy ra exception.
- [ ] Có quy trình xử lý nếu phát hiện dữ liệu nhạy cảm đã bị ghi.

### Tự kiểm tra

**Câu 1.** `logger.info("request=" + signUpRequest)` có an toàn nếu record chỉ gồm các trường nghiệp vụ?  
**Đáp:** Không mặc định. Record có thể chứa email, số điện thoại hoặc field mới; `toString()` làm lộ chúng.

**Câu 2.** Thay email bằng `SHA-256(email)` có đương nhiên làm dữ liệu thành vô danh?  
**Đáp:** Không. Giá trị đầu vào có thể đoán và kết quả vẫn cho phép liên kết bản ghi.

**Câu 3.** Đã cấu hình appender xóa chuỗi trông giống email, có thể bỏ kiểm soát tại caller không?  
**Đáp:** Không. Regex có thể bỏ sót và một appender/đường xuất khác có thể không dùng filter đó.

**Câu 4.** Có thể log access token để nối các dòng thuộc cùng request không?  
**Đáp:** Không. Dùng correlation ID riêng; token là bí mật xác thực và không nên nằm trong log.

**Câu 5.** Vì sao một field request ID vẫn phải được quản lý theo chính sách?  
**Đáp:** Vì nó có thể liên kết đến người dùng, phiên làm việc hoặc hệ thống khác qua các dữ liệu bổ sung.

**Ghi nhớ:** Logging an toàn với dữ liệu cá nhân bắt đầu từ **thiết kế event không chứa dữ liệu không cần thiết**. Mỗi log event, formatter, handler/appender và collector là một cơ hội nhân bản dữ liệu. Hãy dùng schema allowlist, metadata tối thiểu, kiểm soát MDC, kiểm thử rò rỉ và quản lý quyền truy cập/retention trên toàn bộ pipeline; không dựa vào level, hash hay regex như một bảo đảm tuyệt đối.