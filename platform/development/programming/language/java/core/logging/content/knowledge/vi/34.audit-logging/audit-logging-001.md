# Audit log là gì? — Java Core Logging

## 1. Khái niệm và mục đích

**Audit log** (nhật ký kiểm toán hoặc nhật ký truy vết hành động) là tập hợp các bản ghi có cấu trúc, cho biết **ai hoặc thành phần nào đã thực hiện hay cố gắng thực hiện hành động gì, lên đối tượng nào, khi nào, trong ngữ cảnh nào và kết quả ra sao**. Audit log giúp giải trình các hành động có ý nghĩa đối với bảo mật, phân quyền, nghiệp vụ và quản trị hệ thống.

Ví dụ cần được ghi nhận: một quản trị viên cấp quyền truy cập, người dùng đăng nhập thất bại, dịch vụ thay đổi cấu hình có ảnh hưởng đến khách hàng, hoặc một bản ghi quan trọng bị xóa. Đó không chỉ là câu chuyện “ứng dụng đang chạy tốt hay không”, mà là **lịch sử hành động để có thể đối chiếu về sau**.

Một audit event đơn giản:

~~~text
time=2026-01-15T10:00:00Z
actor=operator-1
action=VIEW_REPORT
target=report-42
outcome=ALLOWED
request=req-001
~~~

Các mã ở đây là ví dụ giả. `actor` và `target` vẫn có thể liên kết đến người thật hay tài sản nhạy cảm, vì vậy cần kiểm soát quyền truy cập và thời hạn lưu.

Audit logging thường hỗ trợ:

- **Accountability:** giải thích ai thực hiện một hành động, kể cả hành động thất bại hoặc bị từ chối.
- **Security investigation:** tái dựng chuỗi hành động khi có nghi vấn lạm dụng quyền, đăng nhập bất thường hoặc thay đổi cấu hình.
- **Change history:** tìm thay đổi nào xảy ra trước một sự cố.
- **Operational review:** hỗ trợ đối soát hành động quan trọng giữa các hệ thống.
- **Compliance và governance:** cung cấp bằng chứng theo chính sách và nghĩa vụ áp dụng. Audit log chỉ là **một phần** của quy trình tuân thủ, không tự động chứng minh rằng hệ thống đã tuân thủ mọi quy định.

**Audit log không phải bản sao của toàn bộ dữ liệu nghiệp vụ.** Nhiệm vụ của nó là ghi đủ thông tin để nhận biết và kiểm chứng một hành động, không phải lưu nguyên password, token, HTTP body hay mọi giá trị trước/sau của đối tượng.

## 2. Phân biệt audit log, application log, access log, trace và event nghiệp vụ

| Loại dữ liệu | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Audit log** | Ai đã làm/cố làm gì, tác động đến đối tượng nào, kết quả thế nào? | `ROLE_GRANTED`, `LOGIN_DENIED`, `CONFIG_CHANGED` |
| **Application/diagnostic log** | Chương trình đã chạy thế nào, lỗi ở đâu? | `Database timeout after 2 retries` |
| **Access log** | Một HTTP request đã đi qua server/proxy ra sao? | Method, path, response status, latency |
| **Distributed trace** | Một yêu cầu đi qua những service/span nào và mất thời gian bao lâu? | Trace ID, span, duration |
| **Business event** | Điều gì xảy ra trong nghiệp vụ để hệ thống khác xử lý? | `OrderPlaced` trên message broker |
| **Metric** | Số lượng/tỷ lệ/độ trễ tổng hợp là bao nhiêu? | `login_failures_total` |

Một hành động có thể tạo **nhiều loại tín hiệu**, nhưng chúng không thay thế nhau.

Ví dụ, khi quản trị viên cấp một vai trò:

- Application log có thể ghi “role service completed in 23 ms”.
- Audit log ghi “actor A cấp vai trò R cho đối tượng B, kết quả SUCCESS, theo yêu cầu X”.
- Business event có thể yêu cầu hệ thống khác cập nhật quyền hoặc gửi thông báo.
- Trace cho thấy đường gọi từ API đến database.

Chỉ thấy HTTP `200` trong access log không bảo đảm thay đổi quyền đã hoàn tất; chỉ thấy thông điệp `INFO` cũng không chứng minh bản ghi audit đã được lưu đáng tin cậy.

**Phân biệt audit log với transaction ledger:** trong nghiệp vụ tài chính, một sổ cái là dữ liệu nghiệp vụ có quy tắc cân đối và giao dịch riêng. Audit log có thể chứng minh ai phê duyệt giao dịch hoặc ai sửa cài đặt, nhưng không tự thay thế dữ liệu giao dịch, sổ cái hay cơ chế kiểm toán tài chính.

## 3. Những hành động nào nên có audit event?

Thiết kế tập sự kiện theo rủi ro và yêu cầu nghiệp vụ, không theo thói quen “ghi tất cả”. Các nhóm điển hình:

1. **Đăng nhập và xác thực:** thành công, thất bại, yêu cầu khôi phục tài khoản, thay đổi yếu tố xác thực.
2. **Phân quyền:** cấp/thu hồi vai trò, thay đổi quyền truy cập, thay đổi chính sách xác thực.
3. **Thao tác dữ liệu quan trọng:** tạo/sửa/xóa bản ghi có tác động pháp lý hoặc vận hành; xuất dữ liệu số lượng lớn.
4. **Quản trị hệ thống:** sửa cấu hình bảo mật, khóa tài khoản, tạo/thu hồi thông tin truy cập kỹ thuật.
5. **Truy cập tài nguyên nhạy cảm:** mở báo cáo riêng tư, truy cập dữ liệu có giới hạn, hành động bị chính sách từ chối.
6. **Vận hành audit:** thay đổi cấu hình thu thập audit, phát hiện không ghi được audit, thay đổi retention hoặc quyền đọc log.

Không phải mọi event đều cần mức chi tiết như nhau. Truy cập một nút giao diện thông thường có thể không phù hợp để đưa vào audit trail dài hạn; truy xuất một hồ sơ đặc biệt nhạy cảm có thể cần bằng chứng rõ hơn. **Cần đặc tả loại sự kiện nào phải ghi cả thành công lẫn thất bại.**

Ví dụ một lần đăng nhập bị từ chối vẫn có giá trị audit. Nếu chỉ ghi khi thao tác thành công, việc điều tra hành vi dò quyền hoặc truy cập trái phép sẽ thiếu dữ kiện.

## 4. Một audit event nên chứa những trường nào?

Một schema thực tế thường gồm các nhóm thông tin sau:

| Nhóm | Trường gợi ý | Mục đích |
| --- | --- | --- |
| **Thời gian** | `occurredAt` (UTC), thời gian nhận/ghi khi cần | Xác định khi nào hành động xảy ra |
| **Chủ thể** | `actorId`, loại chủ thể (user/service), tenant nếu phù hợp | Ai thực hiện/cố thực hiện |
| **Hành động** | `action` mã hóa theo enum hoặc vocabulary chuẩn | Hành động gì |
| **Đối tượng** | `resourceType`, `targetId` | Tác động đến đâu |
| **Kết quả** | `outcome`, `reasonCode` có kiểm soát | Thành công, thất bại hay bị từ chối |
| **Tương quan** | `requestId`, `traceId` khi thích hợp | Nối các event thuộc cùng một yêu cầu |
| **Nguồn phát** | `service`, `component`, `environment`, `schemaVersion` | Ai ghi, theo định dạng nào |
| **Bối cảnh bổ sung** | Mức ủy quyền, phạm vi thay đổi được chuẩn hóa | Giải thích quyết định khi cần |

Các trường này **không phải checklist bắt buộc cho mọi hệ thống**. Một hành động thực hiện bởi batch job có thể không có user ID; khi đó `actorType=SERVICE` và mã service phù hợp có giá trị hơn việc giả tạo “user”. Cũng cần xác định trường nào là dữ liệu cá nhân và ai được phép nhìn thấy.

Một cách đặt tên event ổn định:

~~~text
LOGIN_SUCCEEDED
LOGIN_DENIED
ROLE_GRANTED
ROLE_REVOKED
REPORT_VIEWED
CONFIG_CHANGED
EXPORT_REQUESTED
AUDIT_DELIVERY_FAILED
~~~

Tên event nên mô tả sự kiện đã xảy ra, nhất quán về thì và nghĩa. Dùng `action` và `outcome` riêng nếu muốn thống kê cả hành động được cho phép và bị từ chối mà không phải phát triển nhiều tên gần trùng nhau.

**Đối với hành động tạo ra thay đổi:** có thể cần `oldValue/newValue` hoặc tập trường thay đổi, nhưng không nên dump toàn bộ object. Để giảm rủi ro riêng tư, nhiều hệ thống chỉ ghi `changedFields` (danh sách tên trường), mã thay đổi hoặc ID phiên bản và lưu chi tiết ở kho nghiệp vụ được phân quyền riêng.

## 5. Các đặc tính quan trọng của audit logging đáng tin

Một dòng chữ trong `app.log` chưa đủ để trở thành audit trail đáng tin cậy. Cần cân nhắc các thuộc tính:

### 5.1. Completeness — không bỏ sót sự kiện quan trọng

Nếu audit event bị mất trong lúc hệ thống đổi cấu hình, queue đầy, file không ghi được hoặc collector ngắt kết nối, lịch sử có thể không đầy đủ. Thiết kế cần định rõ:

- Sự kiện nào phải được ghi chắc chắn trước khi cho phép nghiệp vụ tiếp tục?
- Có được chấp nhận mất audit event của những thao tác ít rủi ro không?
- Nếu kho audit không khả dụng, ứng dụng **từ chối thao tác (fail closed)**, lưu bền vào hàng đợi/outbox, hay chấp nhận tiếp tục kèm cảnh báo?
- Có đo số lượng, tuổi và độ trễ của event đang chờ, cùng số lần gửi lỗi không?

Không có một lựa chọn áp dụng cho tất cả. Với thao tác đặc biệt nhạy cảm, tiếp tục thành công nhưng âm thầm bỏ qua lỗi ghi audit có thể vi phạm yêu cầu thiết kế.

### 5.2. Integrity — phát hiện sửa/xóa trái phép

Audit trail thường cần chống giả mạo, xóa hoặc sửa không được phép. Các biện pháp có thể bao gồm:

- Cấp **quyền chỉ append** cho thành phần ghi; người dùng ứng dụng không được tự sửa bản ghi.
- Phân tách người quản trị ứng dụng và người quản trị kho audit.
- Gửi tới dịch vụ tập trung hoặc kho lưu giữ bất biến/WORM nếu có yêu cầu.
- Dùng hash chain, chữ ký số hoặc cơ chế chứng thực phù hợp để **phát hiện** việc thay đổi; bảo vệ và neo giá trị đối chiếu ở nơi khác.
- Kiểm tra integrity định kỳ và cảnh báo khi có thay đổi bất thường.

**Lưu ý:** ghi vào file với `APPEND` không khiến file tự động bất biến. Người có quyền phù hợp vẫn có thể sửa hoặc xóa. Một hash nằm cùng file với dữ liệu cũng có thể bị sửa đồng thời nếu không có cơ chế tin cậy để kiểm chứng.

### 5.3. Availability, retention và khả năng tìm kiếm

Bản ghi phải được tra cứu được trong thời gian cần thiết; nhưng **giữ quá lâu** làm tăng rủi ro dữ liệu, chi phí và trách nhiệm vận hành. Cần chính sách retention theo mục đích, yêu cầu ngành và quy định áp dụng; bao gồm backup, bản sao, chỉ mục tìm kiếm và log được xuất sang hệ thống khác.

### 5.4. Thời gian và thứ tự sự kiện

Lưu thời gian theo chuẩn dễ so sánh, ví dụ `Instant` UTC dạng ISO-8601, nhưng **timestamp không đủ để chứng minh thứ tự tuyệt đối trong hệ thống phân tán**. Đồng hồ giữa máy có thể lệch; hai sự kiện có thể có timestamp giống nhau hoặc được nhận sai thứ tự.

Khi cần, bổ sung sequence number, event ID, vị trí trên event stream, thời điểm nhận từ collector hoặc định danh giao dịch. Đồng bộ giờ máy chủ giúp giảm sai lệch; không nên sử dụng thời gian do client tùy ý gửi làm nguồn tin cậy duy nhất.

### 5.5. Không giả định “exactly once”

Mạng, retry và queue có thể khiến một audit event được **gửi nhiều lần** hoặc hiển thị lặp. Nếu collector/consumer dùng at-least-once delivery, hãy thiết kế `eventId` duy nhất và xử lý trùng phù hợp. “Ghi đúng một lần” xuyên nhiều hệ thống là bài toán riêng, không tự sinh ra từ việc gọi API logger đúng một lần.

## 6. Ví dụ Java 17 chạy độc lập: ghi audit event theo schema cố định

Ví dụ sử dụng **JDK 17 thuần**, không cần Maven/Gradle hay thư viện ngoài. Ta tạo một writer nhỏ chuyên ghi audit event vào tệp riêng, không lẫn với log chẩn đoán. Mỗi event chỉ mang trường đã được quyết định trước, thay vì `toString()` toàn bộ request.

**Giới hạn của ví dụ:** writer dùng `Files.writeString` để minh họa cách tạo event và append; đây **không phải** triển khai production đáp ứng yêu cầu chống sửa đổi, giao dịch, chống trùng, khả năng ghi của nhiều JVM hay độ bền sau mất điện. Phần sau sẽ chỉ ra cách mở rộng.

Tạo file **`AuditLogDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class AuditLogDemo {

    enum Action { VIEW_REPORT }
    enum Outcome { ALLOWED, DENIED }

    record AuditEvent(
            Instant occurredAt,
            String actorId,
            Action action,
            String targetId,
            Outcome outcome,
            String requestId) {}

    static final class AuditWriter {
        private final Path file;

        AuditWriter(Path file) {
            this.file = Objects.requireNonNull(file);
        }

        private static String validatedId(String field, String value) {
            if (value == null
                    || !value.matches("[A-Za-z0-9._-]{1,64}")) {
                throw new IllegalArgumentException("Invalid " + field);
            }
            return value;
        }

        synchronized void append(AuditEvent event) throws IOException {
            Objects.requireNonNull(event, "event");

            String entry =
                    "time=" + Objects.requireNonNull(event.occurredAt())
                    + " actor=" + validatedId("actorId", event.actorId())
                    + " action=" + Objects.requireNonNull(event.action())
                    + " target=" + validatedId("targetId", event.targetId())
                    + " outcome=" + Objects.requireNonNull(event.outcome())
                    + " request=" + validatedId("requestId", event.requestId());

            Files.writeString(
                    file,
                    entry + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Path.of("logs");
        Files.createDirectories(directory);

        // Tao file demo moi moi lan chay, khong xoa audit file cu.
        Path file = Files.createTempFile(
                directory, "audit-demo-", ".log");

        // Dong ho co dinh chi de output minh hoa khong thay doi.
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-15T10:00:00Z"),
                ZoneOffset.UTC);

        AuditWriter writer = new AuditWriter(file);
        writer.append(new AuditEvent(
                Instant.now(clock),
                "operator-1",
                Action.VIEW_REPORT,
                "report-42",
                Outcome.ALLOWED,
                "req-001"));

        writer.append(new AuditEvent(
                Instant.now(clock),
                "operator-2",
                Action.VIEW_REPORT,
                "report-99",
                Outcome.DENIED,
                "req-002"));

        System.out.println("eventsWritten=2");
        Files.readAllLines(file, StandardCharsets.UTF_8)
                .forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy trong thư mục có quyền tạo thư mục/file:

~~~bash
javac AuditLogDemo.java
java AuditLogDemo
~~~

**Stdout chính xác** (với JDK 17+ và không có lỗi I/O):

~~~text
eventsWritten=2
time=2026-01-15T10:00:00Z actor=operator-1 action=VIEW_REPORT target=report-42 outcome=ALLOWED request=req-001
time=2026-01-15T10:00:00Z actor=operator-2 action=VIEW_REPORT target=report-99 outcome=DENIED request=req-002
~~~

**Stderr:** không có nội dung trong trường hợp thành công. File thực tế được tạo trong thư mục `logs`, có tên bắt đầu bằng `audit-demo-` và kết thúc `.log`; phần tên giữa hai đoạn được tạo tự động nên không cố định. Chương trình đọc lại file và in hai audit event ra stdout để có thể kiểm tra. Trong ứng dụng thực tế, không nên tự động in toàn bộ audit trail ra console như vậy; đây chỉ là phần xác minh của bài học.

### Giải thích code và ranh giới an toàn

- `AuditEvent` là **record có cấu trúc**. `Action` và `Outcome` dùng enum để ngăn các mô tả tùy ý khó tổng hợp.
- `Instant` biểu diễn thời điểm ở dạng UTC; `Clock.fixed` chỉ dùng để có output xác định trong demo. Trong runtime thật, lấy thời gian từ đồng hồ hệ thống được quản lý và kiểm tra đồng bộ.
- `validatedId` giới hạn độ dài và tập ký tự cho các mã. Điều này giảm khả năng log injection bằng newline và tránh ghi nguyên văn dữ liệu không rõ nguồn; **không biến actor ID thành dữ liệu vô danh**.
- `Files.writeString(... CREATE, WRITE, APPEND)` thêm dòng vào file đã có. `synchronized` chỉ tuần tự hóa lời gọi trên **cùng một đối tượng `AuditWriter`**, không khóa mọi writer/process khác.
- Khi I/O lỗi, phương thức ném `IOException` để caller biết thao tác audit thất bại; nó **không âm thầm bỏ qua sự kiện**. Trong dịch vụ thật cần quyết định nghiệp vụ xử lý lỗi ấy ra sao.
- Chương trình không ghi họ tên, email, password, token hay HTTP body vào audit event; chỉ dùng mã định danh giả cho mục đích minh họa.
- `Files.createTempFile` tạo file mới mỗi lần chạy để không ghi đè bài thử trước. Không nên dùng tệp tạm với quyền, cấu trúc lưu trữ và vòng đời như vậy làm kho audit sản xuất.

**Quan trọng:** chương trình giả lập hai quyết định truy cập, **không thực sự kiểm tra quyền trên tài nguyên**. Nó giải thích schema, không chứng minh một thao tác nghiệp vụ đã thành công hay đã được commit. Trong hệ thống thật, `outcome` phải lấy từ kết quả đã xác thực của cơ chế phân quyền/nghiệp vụ.

## 7. Làm sao để audit log phản ánh đúng kết quả nghiệp vụ?

Giả sử một API đổi quyền người dùng. Nếu ứng dụng ghi “ROLE_GRANTED” **trước** khi database commit, nhưng transaction sau đó rollback, audit event có thể sai. Nếu chỉ ghi **sau** commit nhưng tiến trình chết trước khi gửi audit, thay đổi đã có mà audit lại thiếu.

~~~text
Option A:
ghi audit -> commit nghiep vu
                |
         commit fail -> log "thanh cong" sai

Option B:
commit nghiep vu -> ghi audit
                         |
               app crash -> thieu audit

Option C (khi co yeu cau ket hop giao dich):
transaction nghiep vu + ghi ban ghi outbox
                |
              commit
                |
          worker doc outbox
                |
         audit store / collector
~~~

**Transactional outbox** là một phương án khi nghiệp vụ và outbox dùng cùng một cơ sở dữ liệu hỗ trợ transaction. Lúc commit, thay đổi nghiệp vụ và một bản ghi “cần phát audit event” có thể được lưu nguyên tử trong phạm vi database đó. Worker sau đó chuyển bản ghi sang kho audit với retry và cơ chế xử lý trùng. Phương án này tăng độ tin cậy về **việc ghi nhận ý định phát event**, nhưng vẫn cần xử lý mất kết nối, backlog, bản ghi trùng, việc xóa outbox và khả năng xác nhận phía đích.

Không được kết luận “có outbox là audit exactly once”. Khi worker gửi thành công rồi chết trước khi đánh dấu đã gửi, cùng event có thể được gửi lại. Vì vậy nên dùng event ID ổn định để deduplicate ở nơi nhận theo chính sách rõ ràng.

Một số thao tác (như **truy cập bị từ chối**) không tạo transaction nghiệp vụ thành công nhưng vẫn cần audit. Trong trường hợp đó, cần một cơ chế ghi event độc lập cho kết quả DENIED, không đặt tất cả audit sau nhánh commit thành công.

## 8. Audit log và các logging backend Java

### 8.1. Java Util Logging (JUL)

`java.util.logging.Logger` và `Handler` có thể gửi event đến file hoặc một đích riêng. Ví dụ mã tích hợp:

~~~java
// Doan tich hop; AUDIT_LOGGER da duoc cau hinh handler rieng.
AUDIT_LOGGER.info("action=VIEW_REPORT outcome=DENIED request=req-002");
~~~

Đây chỉ là đoạn tích hợp, không phải ứng dụng chạy độc lập. Nếu dùng JUL làm kênh audit, cần bảo đảm:

- Logger có level và filter thích hợp, không vô tình bỏ sự kiện vì thay đổi level chung.
- Handler/đích nhận audit được cấu hình riêng nếu chính sách khác log chẩn đoán.
- Lỗi ghi handler được quan sát: một số logging API có cơ chế báo lỗi không giống việc ném exception lên caller.
- Rotation, retention và shutdown không làm mất lịch sử bắt buộc.

**Không mặc định rằng `Logger.info` trả về bình thường nghĩa audit event đã được ghi bền vững.** Với yêu cầu bắt buộc thành công hay thất bại rõ ràng, cần API/writer hoặc hạ tầng audit có hợp đồng xác nhận cụ thể.

### 8.2. SLF4J với Logback hoặc Log4j 2

SLF4J là facade. Logback/Log4j 2 thường cung cấp appender, encoder, filter, async queue, routing và cơ chế tách nguồn log. Một cấu hình audit có thể phân luồng theo tên logger hoặc marker, ví dụ:

~~~java
// Doan minh hoa can SLF4J va backend duoc cau hinh.
// Khong co tac dung audit dac biet neu backend khong route rieng.
org.slf4j.Logger auditLogger =
        org.slf4j.LoggerFactory.getLogger("audit.events");
auditLogger.info("action={} target={} outcome={}",
        "VIEW_REPORT", "report-42", "ALLOWED");
~~~

**Đặt tên logger là `audit.events` không tự tạo audit trail đáng tin.** Phải cấu hình backend, đảm bảo đường truyền, quyền ghi, sự kiện đầy đủ, thông báo lỗi và retention.

Một appender ghi cùng sự kiện cả ra console và remote collector có thể dẫn đến bản sao trùng nếu collector cũng thu thập console. Mỗi đường gửi cần có mục đích rõ; audit quan trọng thường cần kho riêng với quyền và chính sách phù hợp hơn log chẩn đoán.

## 9. Bảo mật và quyền riêng tư của audit trail

Audit event có giá trị điều tra cao nên thường chứa actor ID, target ID, thời gian và ngữ cảnh. Những dữ kiện này có thể **liên kết đến người thật**, ngay cả khi không ghi tên/email.

### Trường nên tránh

- Password, access token, refresh token, cookie, secret, khóa mã hóa.
- Raw request/response body, toàn bộ DTO hoặc header xác thực.
- Các trường định danh/tài chính/sức khỏe không cần cho mục đích kiểm toán.
- Exception message chưa được xem xét, vì đôi khi chứa đường dẫn, query parameter hoặc dữ liệu người dùng.
- Giá trị “before/after” toàn bộ của tài liệu nhạy cảm khi chỉ cần ghi tên trường đã đổi hoặc mã phiên bản.

### Bảo vệ hệ thống lưu

1. **Tối thiểu hóa tại nguồn:** chỉ ghi các trường đã được phê duyệt theo schema.
2. **Phân quyền:** tách người ghi audit, người đọc và người quản trị kho.
3. **Bảo vệ khi truyền và lưu:** dùng các cơ chế mã hóa/kiểm soát khóa phù hợp với hệ thống.
4. **Chống sửa trái phép:** append-only permissions, kho bất biến và kiểm chứng integrity khi yêu cầu.
5. **Retention và deletion:** xác định nơi lưu, bản sao, backup, mục đích, hạn lưu và nghĩa vụ áp dụng.
6. **Bảo vệ correlation:** request/trace ID có thể nối dữ liệu qua nhiều nguồn; không dùng token xác thực làm ID.

Masking hoặc hashing một field không tự khiến nó trở thành “không phải dữ liệu cá nhân”. Nếu token/pseudonym còn liên kết được với danh tính qua một hệ thống khác, vẫn cần quản lý theo rủi ro và quy tắc áp dụng.

## 10. Kiến trúc triển khai: file, queue và kho tập trung

Ba mô hình thường gặp:

| Mô hình | Điểm mạnh | Giới hạn cần xử lý |
| --- | --- | --- |
| **File audit riêng trên máy** | Dễ triển khai, dễ kiểm tra cục bộ | Quyền sửa/xóa, rotation, disk full, multi-process, backup |
| **Queue hoặc outbox + worker** | Tách độ trễ nghiệp vụ khỏi exporter, có thể retry | Queue/backlog, xử lý trùng, xác nhận và shutdown |
| **Dịch vụ/kho audit tập trung** | Tìm kiếm, phân quyền, lưu trữ và tổng hợp đa service | Phụ thuộc mạng, availability, chi phí, chính sách truy cập |

Ở hệ thống có nhiều replica hoặc microservices, ghi file cục bộ ở mỗi container thường làm việc truy vết phân tán khó hơn nếu thiếu collector và lưu trữ bền vững. Nhưng **đẩy log lên stdout rồi để collector thu thập** cũng không mặc định cung cấp bảo đảm delivery hoặc integrity phù hợp audit nhạy cảm.

Một pipeline audit cần theo dõi được:

~~~text
Producer (Java service)
        |
        v
Validate schema / generate event ID
        |
        v
Durable handoff (when required)
        |
        v
Transport / worker / retry
        |
        v
Audit store with access + integrity controls
        |
        v
Search / investigation / retention / verification
~~~

Những chỗ có queue/worker nên đo `pending_count`, tuổi event cũ nhất, số event gửi lỗi, số lần retry, tỷ lệ discard và sự chênh lệch giữa số sự kiện nghiệp vụ với số audit event dự kiến.

## 11. Failure modes và cách ứng dụng phản ứng

| Tình huống | Hậu quả | Biện pháp cân nhắc |
| --- | --- | --- |
| Disk full hoặc permission denied | Audit append thất bại | Không nuốt lỗi; chính sách fail closed/outbox rõ ràng |
| Collector down hoặc timeout | Event chưa đến đích | Retry có kiểm soát, lưu bền tạm và cảnh báo backlog |
| Async queue đầy | Event có thể bị drop hoặc block | Định nghĩa chính sách cho audit event quan trọng |
| Process bị `SIGKILL`/mất điện | Buffer/queue bộ nhớ có thể mất | Ghi nhận bền trước khi trả thành công khi thật sự cần |
| Event gửi lại sau timeout | Có thể tạo bản trùng | Event ID ổn định và idempotent consumer |
| Đồng hồ máy lệch | Thứ tự sự kiện khó đối chiếu | Đồng bộ giờ, thời gian nhận, sequence/correlation |
| Người có quyền sửa file | Audit trail không còn đáng tin | Tách quyền, kho bất biến/chứng thực integrity |
| Retention quá ngắn | Thiếu bằng chứng khi điều tra | Chính sách theo nhu cầu và nghĩa vụ |
| Retention quá dài | Rủi ro riêng tư và chi phí tăng | Giới hạn lưu, phân loại và quản lý bản sao |
| Audit chỉ ghi SUCCESS | Không thấy hành vi bị từ chối | Ghi cả DENIED/FAILED theo phạm vi thiết kế |
| Log có thông tin nhạy cảm | Rò rỉ qua file, dashboard, backup | Allowlist field, không log secret, kiểm thử đường xuất |

**Chú ý về shutdown hook:** hook có thể giúp drain queue, flush và close khi JVM shutdown có trật tự, nhưng không cứu được log khi tiến trình bị kill cưỡng bức hoặc host gặp sự cố. Với audit event bắt buộc phải có, thiết kế durability phải được thực hiện **trong thời gian chạy**, không chỉ ở thời điểm shutdown.

## 12. Kiểm thử audit logging đúng mục đích

Ngoài unit test xem logger đã được gọi, cần kiểm tra **khả năng tra cứu và tính nhất quán với hành động thực tế**:

1. Một action thành công tạo đúng loại event, đúng actor, target, outcome và request ID.
2. Một action bị DENIED/FAILED cũng có event khi chính sách yêu cầu.
3. Business transaction rollback không sinh event “SUCCESS” sai; nếu cần log attempt thì outcome phải phản ánh đúng sự kiện thực.
4. File/queue/collector không ghi được: ứng dụng phản ứng theo chính sách đã định, có metric/cảnh báo.
5. Worker gửi lại cùng event ID: nơi nhận có nhận biết và xử lý bản trùng như thiết kế không?
6. Có hàng nghìn request đồng thời: ordering, idempotency và writer có còn đúng không?
7. Kiểm thử downtime, reconnect, restart và shutdown; đo số event dự kiến so với event đã xác nhận.
8. Mã định danh hoặc message có ký tự xuống dòng/đầu vào bất thường: schema validator/encoder có ngăn làm giả dòng log không?
9. Không xuất hiện secret/PII ngoài allowlist trong mọi đích, kể cả exception và backup được kiểm thử.
10. Thử quyền đọc/ghi/sửa/xóa theo từng vai trò; kiểm chứng cơ chế phát hiện can thiệp trái phép nếu đã triển khai.
11. Kiểm tra retention, truy vấn theo actor/action/target và theo event ID khi điều tra.
12. Khi schema nâng phiên bản, consumer cũ có đọc được hay chuyển đổi an toàn không?

**Một kiểm thử hữu ích** là đối soát số thao tác có liên quan đến audit với số bản ghi audit theo event ID, phân biệt event chưa gửi, bị từ chối, gửi trùng và đã xác nhận lưu. Số dòng text trong file đơn lẻ không đủ để chứng minh completeness khi có nhiều appender hoặc collector.

## 13. Những hiểu nhầm phổ biến

**“Ứng dụng có log INFO là có audit log.”** Sai. Log chẩn đoán có thể thiếu actor/target/outcome, bị thay đổi level hoặc chỉ sống trong file tạm.

**“Ghi append vào file là không thể sửa/xóa.”** Sai. Chế độ append của API không đồng nghĩa immutability ở cấp quyền truy cập/hệ thống lưu trữ.

**“Càng ghi nhiều dữ liệu càng kiểm toán tốt.”** Sai. Log quá chi tiết tăng rủi ro riêng tư, làm nhiễu tìm kiếm và tạo nhiều bản sao không cần thiết.

**“Không cần ghi các lần bị từ chối.”** Sai với những trường hợp chính sách cần điều tra việc truy cập trái phép. Các lần DENIED có thể là bằng chứng quan trọng.

**“Timestamp UTC luôn phản ánh đúng thứ tự toàn hệ thống.”** Sai. Cần tính đến lệch đồng hồ, retry, network và xử lý bất đồng bộ.

**“Đã gọi `auditLogger.info()` nên event chắc chắn đã được lưu.”** Sai. Cần xem delivery, failover, queue, write acknowledgment và khả năng phát hiện lỗi của backend.

**“Chỉ cần audit log là đủ đáp ứng mọi quy định.”** Sai. Còn có vấn đề phân quyền, dữ liệu cá nhân, quy trình điều tra, lưu trữ và yêu cầu theo bối cảnh pháp lý cụ thể.

## 14. Checklist thiết kế audit log trong dự án Java

- [ ] Định nghĩa rõ mục đích và tập action có ý nghĩa audit, kể cả FAILED/DENIED khi cần.
- [ ] Tạo schema có version; trường actor, action, target, occurredAt, outcome và correlation phù hợp.
- [ ] Không log toàn bộ object, request payload hoặc secret; phân loại PII và tối thiểu hóa ở nguồn.
- [ ] Phân biệt audit event với log chẩn đoán, access log và event nghiệp vụ.
- [ ] Xác định thời điểm ghi event so với thay đổi nghiệp vụ, commit và rollback.
- [ ] Quy định xử lý thất bại của audit pipeline: báo lỗi, dừng thao tác, outbox/retry hoặc phương án khác được duyệt.
- [ ] Thiết kế chống gửi trùng bằng event ID và quy tắc idempotency khi có retry.
- [ ] Xác định yêu cầu append-only, kiểm chứng integrity và quyền truy cập vào kho audit.
- [ ] Đồng bộ thời gian, bổ sung timestamp/sequence phù hợp với hệ thống phân tán.
- [ ] Bảo đảm retention, backup và khả năng tìm kiếm theo chính sách áp dụng.
- [ ] Quan sát backlog, drop, timeout và lượng event đã ghi nhận.
- [ ] Kiểm thử failure modes, phân quyền, dữ liệu nhạy cảm và tính chính xác của outcome.

### Câu hỏi tự kiểm tra

**1. Audit log trả lời câu hỏi gì?**  
Ai/cái gì thực hiện hoặc cố thực hiện hành động nào, trên tài nguyên nào, khi nào, kết quả thế nào và liên quan đến yêu cầu nào.

**2. Vì sao không chỉ dùng `logger.info("Role changed")`?**  
Vì câu này thiếu actor, target, outcome, correlation và bảo đảm ghi/lưu mà audit trail có thể yêu cầu.

**3. Nếu database rollback sau khi đã log “ROLE_GRANTED SUCCESS”, điều gì sai?**  
Audit event thể hiện một thay đổi đã hoàn tất trong khi nghiệp vụ thực tế không commit; cần thiết kế thời điểm ghi hoặc outbox phù hợp.

**4. Chế độ `APPEND` trong Java có làm file bất biến không?**  
Không. Nó chỉ điều khiển cách mở/ghi file trong thao tác ấy, không chống người có quyền sửa hoặc xóa.

**5. Tại sao cần ghi một số lần truy cập bị từ chối?**  
Vì các lần DENIED có thể giúp phát hiện và truy vết hành vi thử quyền không hợp lệ.

**6. Có nên ghi access token vào audit event để nhận diện actor không?**  
Không. Dùng định danh chủ thể hoặc correlation ID phù hợp; token là bí mật cần tránh đưa vào log.

**Ghi nhớ:** Audit log là **dấu vết hành động có thể kiểm chứng**, chứ không chỉ là thông điệp chẩn đoán. Một audit trail có giá trị cần schema rõ ràng, kết quả nghiệp vụ chính xác, kiểm soát truy cập, dữ liệu tối thiểu, thiết kế chống mất/giả mạo, xử lý trùng và retention phù hợp. Trong Java, việc gọi logger là bước tạo tín hiệu; độ tin cậy cuối cùng đến từ toàn bộ pipeline ghi nhận và quản lý audit event.