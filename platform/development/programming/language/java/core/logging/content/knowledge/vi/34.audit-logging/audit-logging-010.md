# Phân biệt audit và debug trong Java Logging

## 1. Hai loại log phục vụ hai câu hỏi khác nhau

Trong hệ thống Java, **audit logging** lưu lại những sự kiện có ý nghĩa về hành động, quyết định và kết quả để có thể **truy vết, đối chiếu và giải trình** sau này. **Debug logging** ghi thông tin kỹ thuật giúp lập trình viên hoặc người vận hành tìm nguyên nhân khi chương trình chạy không như dự kiến.

Sự khác biệt cốt lõi:

- **Audit trả lời:** *Ai hoặc hệ thống nào đã làm/cố làm điều gì, lên đối tượng nào, khi nào, kết quả ra sao, theo chính sách/quyết định nào?*
- **Debug trả lời:** *Code đã đi qua nhánh nào, tham số/cấu hình kỹ thuật nào liên quan, vì sao có lỗi hoặc độ trễ?*

Một người dùng bị từ chối xuất báo cáo có thể tạo **hai event khác nhau**: audit ghi `actor=usr-42 action=EXPORT resource=rpt-7 outcome=DENIED reason=NO_PERMISSION`; debug ghi `branch=export-policy policyVersion=v3`. Event audit phải có giá trị khi không bật debug; event debug có thể bị tắt, giảm chi tiết hoặc xóa sớm theo chính sách vận hành.

Không suy diễn rằng “audit log” chỉ là `logger.info(...)`, hay “debug log” chỉ là `logger.debug(...)`. **Loại log được xác định bằng mục đích, schema, chính sách và hệ thống lưu giữ**, không chỉ bởi tên method hoặc mức `INFO/DEBUG`.

### Phạm vi của bài

Bài này so sánh audit và debug trong Java Core Logging, hướng dẫn chọn sự kiện, đặt vị trí ghi, cấu trúc trường, tách kênh và kiểm chứng. Ví dụ chạy độc lập dùng `java.util.logging` (JUL, Java 17); cấu hình SLF4J/Logback và Log4j 2 được đánh dấu rõ là ví dụ cần dependency bên ngoài.

## 2. Bảng so sánh nhanh

| Tiêu chí | Audit logging | Debug logging |
| --- | --- | --- |
| Mục tiêu | Truy vết hành động/quyết định, trách nhiệm và lịch sử sự kiện đáng kiểm tra | Chẩn đoán code, trạng thái thuật toán, tương tác dịch vụ |
| Câu hỏi chính | Who, what, when, target, outcome, reason | Where, how, why, intermediate state |
| Sự kiện điển hình | Đăng nhập thành công/thất bại; sửa quyền; thay đổi dữ liệu; export; thay đổi cấu hình quan trọng | Cache hit/miss; nhánh `if`; retries; payload size; timing chi tiết |
| Mức log thông thường | Có thể định tuyến qua INFO hoặc API audit chuyên biệt; không lệ thuộc ngưỡng DEBUG | DEBUG/FINE/TRACE/FINER hoặc tương đương |
| Trường quan trọng | `eventId`, actor, action, resource, outcome, timestamps, correlation | Class/method, operation step, trace/span ID, stack trace, timing |
| Tần suất | Theo mỗi hành động có yêu cầu truy vết; không được sampling tùy tiện nếu bắt buộc | Có thể nhiều và bị giới hạn, sampling, bật theo thời hạn |
| Kiểu dữ liệu | Schema tương đối ổn định, code sự kiện chuẩn hóa | Có thể thay đổi khi triển khai, nhưng vẫn phải kiểm soát dữ liệu |
| Độ bền | Tùy mục đích audit; sự kiện bắt buộc có thể yêu cầu giao nhận/lưu trữ bền vững | Thường chấp nhận mất một phần khi crash, giảm tải |
| Bảo vệ sửa/xóa | Có thể cần integrity, hạn chế chỉnh sửa, phát hiện thiếu hoặc giả mạo | Có thể không cần cùng cấp bảo vệ, nhưng vẫn cần kiểm soát truy cập |
| Quyền truy cập | Vai trò kiểm toán, bảo mật và người được ủy quyền | Dev/Ops/SRE theo phạm vi và chính sách |
| Thời gian lưu | Theo chính sách audit, rủi ro, hợp đồng/pháp luật áp dụng | Thường ngắn hơn, đủ phục vụ điều tra |
| Tắt khi vận hành | Không được tự ý tắt các event audit bắt buộc bằng debug switch | Có thể tắt/tăng giảm level theo quy trình |
| Rủi ro | Thiếu sự kiện, sai người thực hiện, sửa lịch sử, thất bại lưu, lộ PII | Log ồn, tốn CPU/I/O, lộ secret, làm khó phân tích |
| Giá trị pháp lý | Chỉ có khi đáp ứng yêu cầu áp dụng và độ tin cậy phù hợp; bản ghi không tự chứng minh không thể chối bỏ | Chủ yếu hỗ trợ kỹ thuật, không tự thành bằng chứng kiểm toán |

Đây là mô hình thiết kế, **không phải** quy định thời hạn lưu hay yêu cầu pháp lý đồng nhất cho mọi công ty. Các lĩnh vực có yêu cầu kiểm toán khác nhau; cần tham chiếu chính sách nội bộ và tiêu chuẩn/quy định thực sự áp dụng.

## 3. Audit, security event, business event và transaction log không hoàn toàn giống nhau

Trong thực tế các thuật ngữ giao nhau nhưng không đồng nghĩa:

**Business audit trail:** ghi thay đổi nghiệp vụ có ý nghĩa, chẳng hạn ai duyệt đơn, đổi hạn mức, sửa thuộc tính hợp đồng, tải báo cáo. Nội dung ưu tiên kết quả và ngữ cảnh nghiệp vụ.

**Security audit trail:** ghi xác thực, ủy quyền, thay đổi quyền, quản trị, truy cập dữ liệu nhạy cảm, hành động có khả năng rủi ro. Một số bản ghi có thể cần giữ cả **ý định thực hiện không thành công** (`DENIED`) để điều tra.

**Security monitoring log:** bổ sung thông tin để phát hiện bất thường (ví dụ tần suất login failure, nguồn yêu cầu bất thường). Có thể chia sẻ nguồn event với audit nhưng chính sách cảnh báo và xử lý khác.

**Diagnostic/debug log:** ghi dữ liệu triển khai nội bộ để tìm lỗi. Nó có thể chứa trace ID hoặc stack trace, nhưng không đủ để thay thế bản ghi audit có schema và tính toàn vẹn.

**Database transaction log/WAL:** phục vụ phục hồi, đồng bộ hoặc nhất quán của cơ sở dữ liệu; bản thân nó không nhất thiết mô tả `actor/action/outcome` ở cấp nghiệp vụ và **không tự** là application audit trail.

Một hệ thống có thể tạo audit và debug từ cùng một request. Điều quan trọng là **không dùng một event text tuỳ ý để gánh mọi mục đích**.

## 4. Quy tắc chọn sự kiện: khi nào cần audit, khi nào chỉ debug?

Hỏi trước khi viết log:

1. **Sự kiện có làm/cố làm thay đổi quyền, dữ liệu, cấu hình quan trọng hoặc truy cập tài nguyên nhạy cảm không?** Nếu có, thường cần xem xét audit.
2. **Sau nhiều tuần/tháng, có cần tái dựng ai đã hành động và kết quả của hành động không?** Nếu có, cần audit có cấu trúc.
3. **Sự kiện chỉ là trạng thái nội bộ có thể thay đổi theo phiên bản code không?** Thường là debug.
4. **Nếu tắt DEBUG, việc thiếu sự kiện có phá hủy nghĩa vụ kiểm toán không?** Nếu có, event không được phụ thuộc DEBUG.
5. **Sự kiện có cần cả lịch sử hành động và thông tin nguyên nhân kỹ thuật không?** Tạo hai event liên kết bằng `requestId`/`traceId` hoặc `eventId`; mỗi kênh giữ đúng các trường cần thiết.

Ví dụ:

| Tình huống | Audit | Debug |
| --- | --- | --- |
| Đăng nhập thất bại | `LOGIN_ATTEMPT outcome=DENIED reason=INVALID_CREDENTIALS` theo policy | Kết quả tra cứu identity provider, timeout, nhánh xử lý |
| Người quản trị cấp quyền | `ROLE_GRANTED actor=... target=... outcome=SUCCESS` sau commit | Cache invalidation, đường đi service, retry |
| User tải/export dữ liệu nhạy cảm | `REPORT_EXPORTED`/`EXPORT_DENIED` theo policy | Query plan, số batch và thời gian tạo file |
| Request đọc tài nguyên thường không nhạy cảm | Tùy yêu cầu nghiệp vụ và chính sách; không audit mọi GET vô điều kiện | Có thể log timing/route khi cần |
| Thực thi một nhánh `if` | Không, trừ khi nhánh chính là quyết định nghiệp vụ cần audit | Có |
| Cache miss | Thường không | Có, nếu cần điều tra hiệu năng |
| Thay đổi cấu hình bảo mật | Thường có: ai, trước/sau được mô tả an toàn, kết quả | Reload sequence và lỗi kỹ thuật |
| Tạo object nội bộ tạm thời | Thường không | Có thể, khi debug |
| Job gửi email quan trọng | Audit nếu cần ghi nhận kết quả giao tiếp/ủy quyền | Debug SMTP retry, queue timing |
| Ứng dụng khởi động hoặc logging bị tắt | Có thể là sự kiện bảo mật/vận hành cần ghi ở kênh kiểm soát | Debug quá trình parse cấu hình |

**Không nên audit mọi lời gọi method.** Audit quá nhiều vừa tăng chi phí vừa làm chìm các sự kiện quan trọng. Thiết kế danh sách event theo mục đích, rủi ro và yêu cầu nghiệp vụ.

## 5. Một audit event đáng tin cần chứa gì?

Một event có giá trị truy vết cần định nghĩa **schema**, ý nghĩa từng trường và thời điểm phát. Tùy trường hợp, tối thiểu có:

| Field | Mục đích | Lưu ý |
| --- | --- | --- |
| `schemaVersion` | Cho phép tiến hóa định dạng | Không âm thầm thay nghĩa trường |
| `eventId` | Định danh duy nhất cho sự kiện để đối chiếu/tránh trùng | Sinh khi tạo event, giữ khi retry |
| `eventType` hoặc `action` | Mã hành động chuẩn hóa, ví dụ `REPORT_EXPORT` | Dùng enum/danh mục ổn định |
| `occurredAt` | Thời điểm hành động/decision diễn ra, ưu tiên UTC | Đồng bộ thời gian, ghi rõ nguồn clock khi cần |
| `recordedAt` hoặc `ingestedAt` | Thời điểm hệ thống nhận/lưu | Đừng nhầm với `occurredAt` |
| `actorType`, `actorId` | Người dùng, service account, hệ thống, hoặc anonymous | Actor có thể chưa xác thực; tránh giả định userID thật |
| `resourceType`, `resourceId` | Đối tượng bị tác động | Kiểm soát dữ liệu cá nhân/nhạy cảm |
| `outcome` | `SUCCESS`, `DENIED`, `FAILED` theo taxonomy | Phải rõ success tại mốc nào |
| `reasonCode` | Mã nguyên nhân allowlist như `NO_PERMISSION` | Không đưa raw exception/secret |
| `requestId`/`traceId` | Liên kết audit với debug/trace | Không là bằng chứng nhận diện độc lập |
| `service`, `environment` | Nguồn phát, vùng triển khai | Hỗ trợ truy xuất, so sánh giữa replica |

Trường bổ sung như tenant, delegated actor, approver, source IP hoặc địa điểm **chỉ thêm khi có mục đích và quyền ghi phù hợp**. Thông tin cá nhân hoặc địa chỉ IP có thể nhạy cảm; không copy request/response, password, token, cookies hay payload gốc để “đủ bằng chứng”.

Ví dụ event JSON **minh họa schema**, không phải output mặc định của JUL:

~~~json
{
  "schemaVersion": 1,
  "eventId": "EVT-100",
  "eventType": "REPORT_EXPORT",
  "occurredAt": "2026-11-10T02:00:00Z",
  "actorType": "USER",
  "actorId": "usr-42",
  "resourceType": "REPORT",
  "resourceId": "rpt-7",
  "outcome": "DENIED",
  "reasonCode": "NO_PERMISSION",
  "requestId": "req-a71",
  "service": "report-service"
}
~~~

Thời gian và ID ở ví dụ là dữ liệu giả. Trong hệ thống thật, không dùng timestamp cố định; hãy tạo thời gian thực với `Instant.now()` và xác định rõ event xảy ra trước/sau kết quả nghiệp vụ.

## 6. Debug event nên chứa gì?

Debug giúp hiểu đường thực thi:

- Tên operation, nhánh thuật toán, trạng thái tùy chọn đã **phân loại an toàn**.
- Mã lỗi và ngoại lệ/stack trace nếu chính sách kênh debug cho phép.
- Duration, cache hit/miss, queue depth, retry count, version cấu hình.
- Trace/span ID và request ID để nối sự kiện với audit mà không copy dữ liệu nhạy cảm.
- Với hot path, message template và arguments thay vì dựng chuỗi không cần thiết.

Ví dụ debug (SLF4J, cần logger đã khai báo):

~~~java
log.debug("policy branch={} version={} cacheHit={} requestId={}",
        "EXPORT_CHECK", "v3", false, requestId);
~~~

Khi DEBUG tắt, event này có thể hoàn toàn không có ở sink. Đó là hành vi mong muốn của logging chẩn đoán; **không** được dùng nó làm chứng cứ duy nhất rằng quyền đã được kiểm tra.

Tránh `log.debug("request={}", request)` nếu object chứa token, cookie, PII hoặc nội dung chưa phân loại. Một ngày ai đó bật DEBUG ở production, secret có thể xuất hiện trong file, exception hoặc collector. “Chỉ log ở DEBUG” **không phải biện pháp bảo mật**.

## 7. Java 17: ví dụ chạy độc lập tách audit và debug

Ví dụ này sử dụng JUL có sẵn trong JDK, **hai logger riêng**:

- `AUDIT` cố định mức `INFO`, xuất hai sự kiện biểu diễn quyết định quyền đã được xác định.
- `DEBUG` ghi ở `FINE`, mặc định bị tắt; tham số `--debug` cho phép bật.
- Cả hai dùng `ConsoleHandler` riêng và được gắn nhãn `AUDIT`/`DEBUG` để phân biệt.
- Để có đầu ra có thể kiểm tra chính xác, formatter chỉ in channel, level và message; chương trình demo **không thay thế schema audit và sink bền vững ở production**.

Tạo file **AuditVsDebugDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AuditVsDebugDemo {
    private static final Logger AUDIT = Logger.getLogger("example.audit");
    private static final Logger DEBUG = Logger.getLogger("example.debug");

    record Decision(String eventId, String actorId, String action,
                    String resourceId, String outcome, String reasonCode) {}

    private static Handler console(String channel) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return channel + " " + record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        return handler;
    }

    private static void audit(Decision decision) {
        AUDIT.log(Level.INFO,
                "eventId={0} actor={1} action={2} resource={3} outcome={4} reason={5}",
                new Object[]{decision.eventId(), decision.actorId(),
                        decision.action(), decision.resourceId(),
                        decision.outcome(), decision.reasonCode()});
    }

    public static void main(String[] args) {
        if (args.length > 1 || (args.length == 1 && !args[0].equals("--debug"))) {
            System.err.println("Usage: java AuditVsDebugDemo [--debug]");
            System.exit(2);
        }
        boolean debugEnabled = args.length == 1;
        Handler auditHandler = console("AUDIT");
        Handler debugHandler = console("DEBUG");
        AUDIT.setUseParentHandlers(false);
        DEBUG.setUseParentHandlers(false);
        AUDIT.setLevel(Level.INFO);
        DEBUG.setLevel(debugEnabled ? Level.FINE : Level.INFO);
        AUDIT.addHandler(auditHandler);
        DEBUG.addHandler(debugHandler);
        try {
            audit(new Decision("EVT-100", "usr-42", "EXPORT", "rpt-7",
                    "DENIED", "NO_PERMISSION"));
            DEBUG.fine(() -> "branch=export-policy policyVersion=v3");

            audit(new Decision("EVT-101", "usr-42", "READ", "rpt-7",
                    "SUCCESS", "ALLOWED"));
            DEBUG.fine(() -> "branch=read-policy cacheHit=true");
        } finally {
            AUDIT.removeHandler(auditHandler);
            DEBUG.removeHandler(debugHandler);
            auditHandler.flush();
            debugHandler.flush();
            auditHandler.close();
            debugHandler.close();
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 AuditVsDebugDemo.java
java AuditVsDebugDemo
~~~

**Standard error (stderr) khi không bật debug, chính xác:**

~~~text
AUDIT INFO eventId=EVT-100 actor=usr-42 action=EXPORT resource=rpt-7 outcome=DENIED reason=NO_PERMISSION
AUDIT INFO eventId=EVT-101 actor=usr-42 action=READ resource=rpt-7 outcome=SUCCESS reason=ALLOWED
~~~

**Standard output (stdout):** trống; exit code `0`. `ConsoleHandler` của JUL mặc định ghi ra stderr.

Chạy thêm:

~~~bash
java AuditVsDebugDemo --debug
~~~

**Standard error (stderr) khi bật debug, chính xác:**

~~~text
AUDIT INFO eventId=EVT-100 actor=usr-42 action=EXPORT resource=rpt-7 outcome=DENIED reason=NO_PERMISSION
DEBUG FINE branch=export-policy policyVersion=v3
AUDIT INFO eventId=EVT-101 actor=usr-42 action=READ resource=rpt-7 outcome=SUCCESS reason=ALLOWED
DEBUG FINE branch=read-policy cacheHit=true
~~~

**Standard output:** trống; exit code `0`.

### Những điều ví dụ đã chứng minh

1. JUL dùng mức `FINE` cho mục đích giống DEBUG; nó **không** có constant `Level.DEBUG` như một số thư viện khác.
2. Đặt `DEBUG.setLevel(Level.INFO)` khiến `DEBUG.fine(...)` không được xuất; hai event trên `AUDIT` vẫn có.
3. `Formatter.formatMessage(record)` xử lý `{0}`, `{1}`… theo quy tắc JUL/`MessageFormat`, không dùng mẫu `{}` của SLF4J.
4. `setUseParentHandlers(false)` tránh truyền event lên handler của logger cha dẫn tới trùng log trong demo.
5. `Handler.setLevel(Level.ALL)` đảm bảo không có ngưỡng handler chặn riêng các event `FINE` trong chế độ `--debug`.

### Những điều ví dụ **không** chứng minh

- Hai `ConsoleHandler` đều ghi stderr; **chưa** có phân quyền, file riêng, mã hóa, xác nhận ghi bền vững hoặc kiểm soát chỉnh sửa.
- `Logger.log(...)` trả về không có nghĩa audit event đã được xác nhận lưu ở kho độc lập, và một tiến trình bị kill vẫn có thể mất dữ liệu.
- Dữ liệu `Decision` trong demo đã giả định outcome được xác định trước; không có transaction nghiệp vụ hoặc cơ chế chống ghi trùng.
- Thời gian và event source chưa được xuất trong formatter đơn giản; audit production cần schema đầy đủ.
- Người có quyền điều khiển JVM/config vẫn có thể sửa logger/handler; tách tên logger **không** tạo ranh giới bảo mật độc lập.

Vì vậy, code này chỉ minh họa **sự độc lập của mức log và mục đích sự kiện**, không dùng nguyên trạng để đáp ứng yêu cầu kiểm toán hoặc pháp lý.

## 8. Đúng thời điểm: ghi audit khi nào?

Thời điểm ghi quan trọng không kém nội dung.

**Hành động bị từ chối:** khi hệ thống đưa ra quyết định `DENIED`, ghi một sự kiện xác nhận **nỗ lực và lý do** nếu chính sách yêu cầu. Actor chưa đăng nhập có thể được ghi là `ANONYMOUS` hoặc một identity chưa xác thực với mức tin cậy riêng. Không bịa `actorId` khi chưa có chứng cứ.

**Hành động thành công:** sự kiện `SUCCESS` nên phản ánh **mốc kết quả đã thật sự hoàn tất**. Nếu thay đổi dữ liệu trong database, phát audit `SUCCESS` trước commit có thể tạo lịch sử giả: transaction bị rollback nhưng log vẫn nói thành công.

**Hành động thất bại:** cần phân biệt `DENIED` (policy/access-control không cho phép) với `FAILED` (đã cố thực hiện nhưng I/O, timeout, validation hoặc lỗi hệ thống khiến không hoàn thành). Giữ mã nguyên nhân chuẩn hóa; không đưa raw stack trace vào audit thông thường.

~~~text
Yêu cầu
  ├── Xác thực/ủy quyền thất bại
  │     └── Audit ATTEMPT + outcome=DENIED
  └── Được phép
        ├── Thực thi nghiệp vụ
        │     ├── Commit thành công -> Audit COMPLETED/SUCCESS theo hợp đồng
        │     └── Thất bại/rollback -> Audit FAILED hoặc ATTEMPT theo policy
        └── Debug các bước tính toán kỹ thuật khi cần
~~~

Khi hệ thống bất đồng bộ, có thể cần hai event: `ACTION_REQUESTED` và `ACTION_COMPLETED/FAILED`. Không gán `SUCCESS` ngay lúc job mới được đưa vào queue nếu nghiệp vụ định nghĩa “thành công” là đã xử lý xong.

## 9. Mối quan hệ giữa audit event và transaction nghiệp vụ

Một vấn đề khó là **dual-write**: ứng dụng vừa cập nhật dữ liệu nghiệp vụ, vừa gửi một audit event tới kho khác.

~~~text
UPDATE business DB -> COMMIT thành công
                   -> gửi audit tới hệ thống khác: lỗi mạng!
~~~

Khi ấy dữ liệu thay đổi nhưng lịch sử audit thiếu, mặc dù một dòng `logger.info(...)` đã được gọi.

Nếu nghiệp vụ có yêu cầu kiểm toán cao, một cách thiết kế phổ biến là **transactional outbox**:

~~~text
BEGIN database transaction
   UPDATE business state
   INSERT audit_outbox(eventId, eventType, safePayload, status)
COMMIT
   │
   ▼
Delivery worker: đọc outbox -> gửi đến audit store
   │                           ├── ACK thành công: mark delivered
   │                           └── timeout/lỗi: retry/backoff/DLQ
   ▼
Audit store: kiểm tra eventId, chống trùng, lưu theo policy
~~~

Điểm quan trọng:

- Cùng transaction bảo đảm thay đổi nghiệp vụ và bản ghi **outbox** được commit hoặc rollback cùng nhau **nếu** chúng cùng nằm trong ranh giới transaction có hỗ trợ.
- Điều đó chưa có nghĩa audit đã có ở kho đích ngay lúc commit. Cần theo dõi backlog, thời gian giao nhận và retry.
- Retry có thể gửi cùng event nhiều lần: dùng `eventId` ổn định và xử lý idempotent/dedup ở bên nhận. Đừng tuyên bố “exactly once end-to-end” chỉ vì có outbox.
- Với hành động **bị từ chối** không có business commit, cần cơ chế ghi nhận attempt/denial phù hợp riêng nếu policy bắt buộc.
- Nếu yêu cầu “không trả thành công trước khi audit bền vững”, thiết kế phải có xác nhận lưu phù hợp hoặc quyết định rõ cơ chế fail-closed. Không dùng file logger async thông thường thay cho transaction/audit store.
- Bản ghi outbox cũng chứa dữ liệu: phải kiểm soát schema, encryption, retention, retry và quyền truy cập.

Với ứng dụng chỉ cần audit mức thông thường, không phải mọi event đều cần outbox. Chọn mức bảo đảm theo rủi ro thay vì áp một kiến trúc đắt đỏ cho mọi debug line.

## 10. Audit có được dùng INFO/DEBUG không?

**Có thể dùng INFO làm mức kỹ thuật để định tuyến audit**, nhưng **không** được đồng nhất `INFO` với audit.

Trong JUL, method `Logger.info(...)` chỉ phát record tại `Level.INFO`. Nếu người vận hành nâng level thành `WARNING`, record INFO có thể bị lọc. Vì vậy nếu dùng `INFO` cho audit, cấu hình, test và quyền thay đổi phải bảo đảm những audit event **bắt buộc** không biến mất khi tối ưu log vận hành.

Trong SLF4J/Logback hoặc Log4j 2, có thể dùng **logger tên riêng** (ví dụ `app.audit`) trỏ tới appender/sink khác và không kế thừa thay đổi level của root. Trong hệ thống có yêu cầu mạnh hơn, tạo `AuditRecorder`/audit service API chuyên biệt và chính sách giao nhận riêng; điều này rõ ràng hơn việc rải `log.info("AUDIT ...")` khắp code.

Ngược lại, debug có thể:

- Dùng `LOG.debug(...)` của SLF4J/Log4j 2, hoặc `LOG.fine(...)` của JUL.
- Bật trong một khoảng thời gian phục vụ điều tra, có kiểm soát và thông báo.
- Giảm sampling/chi tiết theo nhu cầu nếu không phá hủy mục đích chính.
- Gỡ các field nhạy cảm, kể cả trong môi trường development.

**Tắt root DEBUG không được vô hiệu hóa audit** theo policy; cũng không dùng bật TRACE để “khôi phục” một lịch sử audit mà trước đó chưa hề được ghi.

## 11. Cấu hình Logback: tách tuyến audit và log kỹ thuật

Ví dụ **logback.xml** sau dùng hai appender và một logger audit riêng. Đây là cấu hình cho dự án đã có **SLF4J + Logback Classic**, không phải một file Java độc lập:

~~~xml
<configuration>
    <appender name="AUDIT_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/audit.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="APP_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="app.audit" level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>

    <logger name="app.technical" level="DEBUG" additivity="false">
        <appender-ref ref="APP_CONSOLE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APP_CONSOLE"/>
    </root>
</configuration>
~~~

Trong code (ví dụ SLF4J):

~~~java
org.slf4j.Logger audit =
        org.slf4j.LoggerFactory.getLogger("app.audit");
org.slf4j.Logger diagnostic =
        org.slf4j.LoggerFactory.getLogger("app.technical");

// Chỉ minh họa routing, không bảo đảm storage hoặc schema.
audit.info("eventId={} action={} outcome={}",
        eventId, "ROLE_GRANTED", "SUCCESS");
diagnostic.debug("cacheVersion={} invalidationQueued={}",
        cacheVersion, true);
~~~

Các biến `eventId` và `cacheVersion` cần được định nghĩa. `additivity=false` giúp audit event không tự động truyền lên root console; đồng thời giảm khả năng trùng. Việc `app.technical` ở DEBUG không có nghĩa root INFO phải bật DEBUG cho mọi logger.

**Giới hạn quan trọng:** `FileAppender`, `append=true` và PatternLayout **không tạo append-only bảo mật, tamper evidence hay durable commit**. Một tiến trình có quyền ghi file có thể sửa/ghi đè hoặc xóa nó. Muốn audit được kiểm chứng cần chọn storage và quyền truy cập, cơ chế phát hiện chỉnh sửa và truyền dữ liệu phù hợp. Ngoài ra cấu hình file path có thể hỏng vì quyền ghi, disk full hoặc rotation.

Đặc biệt không tùy tiện đặt audit sau `AsyncAppender` có queue discard mà không đánh giá khả năng mất event khi đầy queue, shutdown hoặc crash. `immediateFlush` chỉ xả buffer của appender đã nhận event, không tự bảo đảm một bản ghi tồn tại sau mất điện.

## 12. Với Log4j 2 và SLF4J: phân biệt API, provider và output

SLF4J là facade, không phải sink. Mẫu `logger.info("...")` sử dụng provider/backend tương ứng (Logback, bridge tới Log4j 2, v.v.). Log4j 2 có API và Core, với `Logger`/`Appender`/`Layout` riêng. Cần xác định **backend thực tế** trước khi thiết kế routing.

Ví dụ **log4j2.xml** tối thiểu tách logger audit khỏi console app:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="AUDIT" fileName="logs/audit.log">
            <PatternLayout pattern="%d{ISO8601} %m%n"/>
        </File>
        <Console name="APP" target="SYSTEM_ERR">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="app.audit" level="info" additivity="false">
            <AppenderRef ref="AUDIT"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="APP"/>
        </Root>
    </Loggers>
</Configuration>
~~~

File này cần `log4j-api`/`log4j-core` tương thích và cơ chế nạp cấu hình đúng. Logback XML và Log4j 2 XML **không hoán đổi** được. Cả hai ví dụ ở đây minh họa **tách tuyến**, không phải một hệ thống audit đạt yêu cầu bất biến hoặc xác nhận bền vững.

Với event có schema, ưu tiên encoder JSON hoặc message template có trường được định nghĩa rõ. Pattern `%m` và `%msg` chỉ tạo thông điệp text; chúng không tự bảo đảm `actorId`, `action`, `outcome` được lưu thành các field có thể query độc lập.

## 13. Độ tin cậy: debug chấp nhận mất, audit phải có hợp đồng rõ

Một backend logging có thể giảm tải bằng async queue. Điều này hữu ích với debug nhưng cần xem xét với audit.

**Debug:** có thể chấp nhận drop do sampling, throttling hoặc thay đổi level. Nếu mất vài dòng khi JVM crash, thường vẫn còn metric, trace hoặc log khác để điều tra, tùy hệ thống.

**Audit:** với event có yêu cầu bảo toàn, “đã enqueue” không đồng nghĩa “đã ghi”. Một số failure mode:

- Queue async đầy và tự discard record.
- Worker đã dequeue nhưng chưa ghi sink.
- Buffer đã flush tới OS nhưng chưa bền vững trên thiết bị.
- Mạng gửi tới collector mất ACK hoặc retry gây trùng.
- Process bị SIGKILL trước shutdown hook; dữ liệu trong RAM mất.
- Sink báo lỗi I/O nhưng framework chỉ ghi cảnh báo nội bộ.

Mức độ bảo đảm nên được đặc tả:

| Mức | Điều có thể khẳng định | Không thể suy ra |
| --- | --- | --- |
| Event method đã được gọi | Code đi đến nhánh ghi log | Event được sink chấp nhận |
| Event vào queue | Queue/buffer nhận event | Consumer xử lý, không drop, không mất khi crash |
| Appender đã flush | Java buffers đẩy xuống tầng tiếp theo | Đã fsync hoặc remote commit |
| Audit store xác nhận bền vững | Được lưu theo hợp đồng ACK cụ thể | Không thể bị người có quyền cao xóa/sửa nếu thiếu kiểm soát khác |
| Tamper-evident store + kiểm soát độc lập | Có cơ chế kiểm tra sửa/xóa theo mô hình đe dọa | Mọi nội dung event đều chính xác về nghiệp vụ |

Một hệ thống có thể yêu cầu **fail closed** nếu không lưu được audit bắt buộc, nhưng đó là **quyết định nghiệp vụ có tác động availability**. Nếu audit sink tạm lỗi và mọi request đều bị từ chối, cần có phương án khôi phục, giới hạn backlog, cảnh báo và quy trình vận hành rõ ràng; không tự bật chế độ này mà chưa đánh giá.

## 14. Tính toàn vẹn, khả năng kiểm chứng và quyền truy cập audit

Audit thường cần nhiều hơn text file:

1. **Quyền tối thiểu:** ứng dụng chỉ được ghi qua API được kiểm soát, không có quyền tùy tiện xóa/sửa toàn kho audit nếu có thể tách biệt.
2. **Truyền an toàn:** TLS hoặc đường kết nối xác thực khi đưa log qua hệ thống khác; phân biệt endpoint tiếp nhận và storage commit.
3. **Tính toàn vẹn:** cân nhắc lưu bản ghi với hash/signature, hash chain, phân đoạn, timestamp và anchor độc lập để phát hiện sửa đổi.
4. **Phát hiện thiếu event:** dùng event ID, sequence theo phạm vi thích hợp, reconciliation, gap detection và metric backlog.
5. **Thời gian đáng tin:** lưu UTC, đồng bộ clock; cần phân biệt lúc xảy ra và lúc hệ thống nhận khi mạng chậm/đổi thứ tự.
6. **Quyền đọc/tra cứu:** audit access tới log audit, phân quyền RBAC, giới hạn export và thông tin cá nhân.
7. **Retention/delete:** theo lịch bảo quản, mục đích sử dụng, hợp đồng/pháp luật; có cả backup và bản export.
8. **Khả năng khôi phục:** kiểm tra restore dữ liệu và replay; không chỉ xem dashboard đang hiển thị.

Hash chain không phải “thêm SHA-256 là chống mọi sửa đổi”. Nếu kẻ tấn công có thể sửa cả dữ liệu lẫn các hash tiếp theo, chain không được anchor độc lập có thể bị tính lại. Chữ ký số, secure anchoring, replication, kiểm soát khóa và bất biến lưu trữ phải phù hợp với threat model.

**Không khẳng định một log tự đạt non-repudiation.** Một hệ thống bị xâm nhập có thể ghi event sai hoặc giả actor nếu nguồn phát không đáng tin. Chứng cứ audit phụ thuộc cả danh tính, xác thực, quyền, thời gian, luồng ứng dụng và kho lưu.

## 15. Riêng tư và bảo vệ dữ liệu ở cả hai kênh

Audit cần biết **ai và cái gì** nhưng không có nghĩa được phép thu thập mọi dữ liệu về người dùng. Debug phục vụ lập trình viên cũng **không** được tự do ghi raw payload.

Không nên ghi:

- Password, PIN, OTP, bearer/access/refresh token, session cookie, API key, private key.
- Toàn bộ request/response body nếu chứa dữ liệu cá nhân, thanh toán hoặc bí mật.
- Chuỗi kết nối database kèm credential, header Authorization, raw SQL bind parameters nhạy cảm.
- Raw exception message/stack trace vào kênh truy cập rộng khi có thể chứa secret.

Tùy mục tiêu, dùng actor ID nội bộ có kiểm soát, pseudonym hoặc mã tham chiếu; `actorId` cũng có thể là dữ liệu cá nhân nếu có khả năng liên kết. Dùng mã `reasonCode=NO_PERMISSION` thay vì ghi toàn bộ lý do nội bộ hoặc thông tin bí mật.

**Log injection:** field do client cung cấp có thể chứa newline hoặc chuỗi giả mạo mức log. Chọn enum/allowlist cho action/outcome, sanitize/encode đúng định dạng, giới hạn độ dài và dùng JSON encoder có escaping. Không dùng `String.replace("\\n","")` làm biện pháp duy nhất cho mọi đầu vào.

**Scope:** nếu audit được gửi sang một hệ thống tập trung và debug ở file khác, mỗi sink cần policy riêng về bảo mật, retention và người được đọc. Mask ở dashboard không xóa dữ liệu gốc đã lưu trong index/archive.

## 16. Correlation: nối audit với debug mà không trộn mục đích

Ví dụ một yêu cầu tải báo cáo có mã `requestId=req-a71` và trace `traceId=tr-9a`:

~~~text
AUDIT: eventId=EVT-100 action=REPORT_EXPORT outcome=DENIED
       actor=usr-42 resource=rpt-7 requestId=req-a71

DEBUG: requestId=req-a71 traceId=tr-9a
       branch=export-policy rule=classification-check
~~~

Với cùng `requestId`, người vận hành tìm debug để hiểu đường đi dẫn tới quyết định audit; không cần nhét `policy stack trace` vào audit. Khi debug đã hết retention, audit vẫn phải đủ ý nghĩa để giải thích sự kiện ở mức nghiệp vụ.

Trong SLF4J dùng MDC và Log4j 2 dùng ThreadContext để truyền metadata qua log event. Nhưng:

- MDC/ThreadContext là dữ liệu có thể được in vào mọi event do layout; không bỏ raw token/email vào context.
- Với thread pool và async, phải propagate/clear context chính xác để tránh lẫn request.
- Correlation ID là công cụ liên kết, không tự chứng minh actor đã được xác thực.
- Nếu debug có sampling, cần xác định không có debug event cho audit event nào là **bình thường** chứ không phải lỗi mất audit.
- Event ID duy nhất và request ID có phạm vi khác nhau: một request có thể sinh nhiều audit events.

## 17. Một tình huống end-to-end: thay đổi quyền

Giả sử người quản trị muốn cấp quyền đọc tài liệu.

**Bước A — nhận yêu cầu:** xác định actor đã xác thực, resource và quyền cần thay đổi. Debug có thể ghi `operation=GRANT_ROLE stage=VALIDATE`. Audit có thể ghi `ATTEMPT` nếu policy yêu cầu theo dõi mọi nỗ lực.

**Bước B — kiểm tra policy:** nếu bị từ chối, audit ghi `outcome=DENIED reasonCode=NO_PERMISSION`. Debug có thể ghi tên rule và phiên bản policy, tránh raw token/quy tắc bí mật.

**Bước C — commit:** nếu được phép và transaction database commit thành công, audit ghi `outcome=SUCCESS` theo hợp đồng. Nếu transaction rollback, không ghi success. Hệ thống có thể ghi `FAILED` với mã lỗi chuẩn nếu policy yêu cầu.

**Bước D — gửi và lưu:** audit event đi qua audit recorder/outbox và được xác nhận ở audit sink. Ghi metric cho backlog/retry; debug event có thể chỉ đến console và bị xóa sau một thời gian ngắn.

**Bước E — điều tra:** kiểm toán viên truy vấn theo event ID/actor/resource/time; kỹ sư dùng request ID để xem debug, trace và metric liên quan. Quyền xem audit và debug có thể khác nhau.

Điều quan trọng là **quyết định audit dựa trên kết quả thực**, không phụ thuộc số log DEBUG, cấu hình root logger hay việc người lập trình nhớ ghi một dòng text rời rạc.

## 18. Kiểm thử: không chỉ assert rằng method logger đã được gọi

Cần kiểm thử cả schema, routing, độ tin cậy và quyền truy cập:

| Test | Kỳ vọng audit | Kỳ vọng debug |
| --- | --- | --- |
| DEBUG tắt | Event bắt buộc vẫn có mặt | Event FINE/DEBUG không xuất |
| DEBUG bật | Audit không đổi nội dung, không bị ghi trùng | Thêm chi tiết kỹ thuật |
| Thao tác được cho phép và commit | `SUCCESS` đúng resource, actor, eventId | Có thể có trace/nhánh kỹ thuật |
| Thao tác bị từ chối | `DENIED` hoặc attempt theo policy | Có thể có chi tiết policy |
| Transaction rollback | Không có audit `SUCCESS` sai; có FAILED nếu policy yêu cầu | Stack trace/mã lỗi được kiểm soát |
| Queue/sink audit lỗi | Có retry/alert/fail policy rõ; không báo thành công giả | Không được ảnh hưởng quyết định audit |
| Retry/duplicate delivery | `eventId` dùng để nhận diện trùng | Có thể thấy nhiều lần retry debug |
| Đổi level của root logger | Audit routing bắt buộc không mất | Debug thay đổi đúng cấu hình |
| Kill cưỡng bức tiến trình | Khả năng mất/phục hồi khớp hợp đồng đã công bố | Có thể mất dữ liệu đang đệm |
| Log injection/secret test | Không chứa token, CR/LF giả và raw PII | Cũng không rò bí mật |
| Storage tamper test | Phát hiện sửa/xóa theo cơ chế độc lập (nếu yêu cầu) | Không mặc định cùng cơ chế |
| Retention/access test | Đọc/xóa/xuất theo role và policy | Quyền, thời gian lưu theo kênh debug |

Đối với Logback/Log4j 2, dùng test appender/encoder và assert **output ở sink đích**, không chỉ `isInfoEnabled()` hoặc mock `logger.info(...)`. Với audit nghiêm ngặt, kiểm thử cả sự cố mạng, restart, outbox replay và xác nhận remote durability theo hợp đồng.

Trong ví dụ Java 17 ở phần 7, chính hai lần chạy mặc định và `--debug` minh họa case đầu tiên: audit giữ nguyên, debug chỉ xuất khi được bật.

## 19. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Coi audit là một dòng DEBUG có chữ “AUDIT” | Khi DEBUG tắt thì lịch sử mất | Dùng API/logger/channel audit độc lập |
| Mọi INFO đều được xem là audit | Event không có actor/action/outcome, không kiểm chứng được | Schema audit rõ ràng |
| Ghi `SUCCESS` trước database commit | Transaction rollback nhưng lịch sử nói thành công | Ghi đúng mốc kết quả, dùng transaction/outbox nếu cần |
| Chỉ ghi hành động thành công | Mất dấu vết nỗ lực bị từ chối hoặc bất thường | Xác định danh mục attempt/denied theo policy |
| Ghi mọi GET, mọi method call làm audit | Tăng noise, storage, PII và giảm khả năng điều tra | Danh mục event theo rủi ro và mục đích |
| Dùng chung queue có discard cho audit và debug | Audit mất khi tải cao | Phân tuyến/QoS/bảo đảm giao nhận riêng |
| Chỉ dựa vào `immediateFlush=true` | Crash hoặc disk failure vẫn có thể mất event | Chọn durability phù hợp và xác nhận ở đích |
| Chỉ nhìn `queue.isEmpty()` | Worker có thể đang xử lý event đã dequeue | Chờ mốc xử lý xong/ACK của sink |
| Dùng hash record nhưng không anchor | Kẻ có quyền có thể sửa dữ liệu và tính lại hash | Kiểm soát độc lập, chain/anchor/signature theo threat model |
| Trộn raw exception và HTTP body vào audit | Lộ PII, secret; schema khó dùng | Event code, reason code, field allowlist |
| Gửi debug tới sink audit có retention dài | Tăng rò rỉ, chi phí, áp lực lưu giữ | Separation và retention độc lập |
| Dùng `requestId` như proof of identity | Dễ gán nhầm người thực hiện | Actor cần đến từ ngữ cảnh xác thực đáng tin |
| Không theo dõi lỗi audit sink | Ứng dụng chạy nhưng thiếu history | Metrics/alert/reconciliation và chính sách fail |
| Retention audit “vĩnh viễn” mặc định | Xung đột quyền riêng tư và chi phí | Lưu theo yêu cầu áp dụng, có xóa có kiểm soát |

## 20. Checklist triển khai cho dự án Java

1. Có danh sách sự kiện **bắt buộc audit** dựa trên nhu cầu nghiệp vụ, bảo mật và rủi ro chưa?
2. Schema audit có `eventId, actor, action, target, outcome, occurredAt` và ngữ cảnh phù hợp không?
3. `SUCCESS` có ý nghĩa chính xác, được ghi sau mốc hoàn thành đúng hợp đồng không?
4. Audit event bắt buộc có còn được tạo khi DEBUG/TRACE tắt hoặc root level đổi không?
5. Có API/recorder/logger và sink audit riêng, tránh cùng policy discard với debug không?
6. Có phân định trách nhiệm khi audit sink lỗi: retry, backpressure, fail closed hay báo degraded không?
7. Nếu cần coupling với transaction, có outbox hoặc cơ chế lưu bền vững phù hợp và idempotency không?
8. Có đồng bộ thời gian, phân biệt `occurredAt`/`ingestedAt` và kiểm tra event order khi async không?
9. Có bảo vệ truy cập, truyền an toàn, phát hiện chỉnh sửa và theo dõi việc truy cập audit không?
10. Có kiểm soát dữ liệu cá nhân/secret cả trong audit, debug, exception và MDC không?
11. Có retention/backup/export/delete theo chính sách từng loại log không?
12. Có test lúc DEBUG tắt, rollback, denial, retry, crash, sink failure và tamper không?
13. Có metric cho audit backlog, lost/duplicate events, latency và alert khi pipeline bị nghẽn không?
14. Có hướng dẫn điều tra dùng `requestId/traceId/eventId` nhưng không biến debug thành nguồn sự thật audit không?

## 21. Câu hỏi tự kiểm tra

1. “`log.info("AUDIT user=...")`” có tự trở thành audit đáng tin không? Vì sao?
2. Tại sao một dòng `DEBUG` ghi “check permission passed” không chứng minh quyền đã được thực thi?
3. Nếu một request được cho phép nhưng transaction rollback, audit `SUCCESS` nên được ghi ở đâu?
4. Trường nào giúp phân biệt các audit event khi retry gửi tới collector?
5. Vì sao `requestId` không thay thế được `actorId`?
6. Dùng JUL, mức nào thường tương đương mục đích DEBUG? Vì sao ví dụ dùng `Level.FINE`?
7. Tại sao `AsyncAppender` và `flush` không đủ bảo đảm audit tồn tại sau mất điện?
8. Audit có thể lưu đầy đủ raw request body vì “để điều tra” hay không?
9. Logback `additivity=false` giải quyết vấn đề gì? Nó có biến file audit thành immutable store không?
10. Hash chain không có anchor/chữ ký/khóa được bảo vệ có ngăn người có quyền sửa toàn bộ lịch sử không?
11. Vì sao có thể cần cả `ACTION_REQUESTED` và `ACTION_COMPLETED` với job bất đồng bộ?
12. Nếu audit sink không sẵn sàng, hệ thống bắt buộc fail closed trong mọi trường hợp không?
13. Tại sao tắt DEBUG không được ảnh hưởng sự kiện audit bắt buộc?
14. Cách liên kết audit và debug mà vẫn giữ retention và quyền truy cập độc lập là gì?

**Gợi ý:** (1) không, còn thiếu schema, outcome, durability và integrity; (2) debug là quan sát nhánh code, có thể thiếu/đổi; (3) không ghi SUCCESS trước commit; (4) `eventId` ổn định; (5) request không chứng minh danh tính; (6) `FINE`; (7) còn queue/OS/remote và crash; (8) chỉ dữ liệu được phép, cần minimization; (9) chặn propagation, không tạo integrity; (10) không; (11) request và hoàn tất là hai mốc; (12) tùy chính sách; (13) mục đích độc lập; (14) correlation ID và routing/sink độc lập.

## 22. Tài liệu tham khảo chính thức

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): mục tiêu security/operational logging, audit trails, dữ liệu phải loại bỏ hoặc mask, độ tin cậy, kiểm soát thay đổi level, bảo vệ log và retention.
- [OWASP Developer Guide — Security Logging and Monitoring](https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/): những sự kiện bảo mật cần ghi và tránh để lọt dữ liệu nhạy cảm.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): kế hoạch thu thập, lưu trữ, truy cập và bảo vệ log; đây là tài liệu hướng dẫn nền tảng năm 2006, không thay thế yêu cầu pháp lý cập nhật.
- [NIST SP 800-92 Rev. 1 — Initial Public Draft](https://csrc.nist.gov/pubs/sp/800/92/r1/ipd): tài liệu **dự thảo** về lập kế hoạch quản lý security logs, không phải tiêu chuẩn cuối cùng.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): level, handler, lọc, `log(Level, String, Object[])` và Supplier.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message, timestamp, level, thread, parameters và Throwable.
- [Java SE 17 — ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): output stderr của handler trong ví dụ.
- [SLF4J Manual](https://www.slf4j.org/manual.html): API tham số hóa, các level và Fluent API.
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html): định nghĩa logger, appender, level và `additivity`.
- [Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): routing logger/appender, config và tính năng thay đổi cấu hình.
