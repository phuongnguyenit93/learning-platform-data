# Ghi nhật ký thay đổi nghiệp vụ mà không lộ thông tin riêng tư

Ứng dụng dùng Spring Data LDAP thường phải ghi nhận ai đã thay đổi entry nào, thay đổi loại dữ liệu gì, thời điểm nào và thao tác thành công hay thất bại. Nhật ký này giúp điều tra sự cố, truy vết thay đổi tài khoản và đáp ứng yêu cầu kiểm toán. Tuy nhiên, LDAP entry có thể chứa tên, email, số điện thoại, mã nhân viên, thông tin xác thực và dữ liệu nhạy cảm khác. Ghi nguyên DN, filter tìm kiếm, entity hoặc toàn bộ giá trị trước và sau khi sửa vào log có thể tạo thêm một kho dữ liệu cá nhân khó kiểm soát.

Giải pháp là thiết kế business audit event chỉ chứa thông tin cần thiết để giải thích hành động. Nhật ký vận hành kỹ thuật được quản lý riêng, có mức chi tiết và thời hạn lưu phù hợp. Cả hai loại log đều phải tránh ghi bí mật và dữ liệu cá nhân không cần thiết.

## Phân biệt business audit và technical log

Hai loại nhật ký phục vụ mục đích khác nhau:

| Loại nhật ký | Câu hỏi cần trả lời | Ví dụ dữ liệu phù hợp |
|---|---|---|
| Business audit | Ai thực hiện hành động nghiệp vụ nào trên đối tượng nào, khi nào và kết quả ra sao? | Mã actor đã giả danh, mã đối tượng đã giả danh, loại thao tác, tên thuộc tính thay đổi, kết quả, mã tương quan. |
| Technical log | Hệ thống xử lý request thế nào và vì sao lỗi? | Tên LDAP server logic, thời gian xử lý, loại exception, LDAP result code đã lọc, request ID. |
| Metric | Hệ thống đang hoạt động ở mức nào? | Số thao tác theo loại/kết quả, latency, timeout, lỗi bind, số connection đang dùng. |

Business audit không cần chứa toàn bộ dữ liệu của entry. Technical log cũng không nên ghi nội dung request LDAP thô chỉ để giúp debug. Khi cần điều tra sâu, hãy dùng event ID hoặc correlation ID để liên kết các nguồn log có quyền truy cập riêng.

## Xác định dữ liệu được phép ghi

Trước khi triển khai audit, phân loại dữ liệu LDAP theo mục đích sử dụng và mức nhạy cảm. Một danh sách allowlist theo nghiệp vụ dễ kiểm soát hơn quy tắc ghi mọi thứ rồi cố gắng che một số trường.

| Dữ liệu | Cách xử lý trong audit |
|---|---|
| Loại thao tác như tạo, sửa, xóa, đổi DN, thay đổi thành viên nhóm | Ghi mã thao tác đã chuẩn hóa. |
| Tên thuộc tính thay đổi như `mail`, `telephoneNumber`, `memberOf` | Chỉ ghi tên thuộc tính nếu tên đó không làm lộ phân loại nhạy cảm; dùng danh mục cho phép. |
| Actor và đối tượng bị tác động | Dùng mã nội bộ không mang ý nghĩa cá nhân hoặc token giả danh có khóa. |
| DN đầy đủ | Không ghi trực tiếp nếu RDN có thể chứa username, email hoặc mã định danh cá nhân. |
| Giá trị cũ và mới | Mặc định không ghi. Chỉ ghi khi có căn cứ nghiệp vụ rõ ràng và giá trị đã được phân loại, giảm thiểu hoặc che phù hợp. |
| Password, credential, access token, private key, bind secret | Tuyệt đối không ghi. |
| LDAP filter, query string, toàn bộ `Attributes`, entity hoặc object `toString()` | Không ghi trực tiếp; các nội dung này có thể chứa dữ liệu cá nhân và bí mật. |
| Nội dung exception | Không đưa nguyên văn vào audit; chỉ ánh xạ sang mã lỗi an toàn. |

Không nên giả định một thuộc tính ít nhạy cảm chỉ vì tên của nó không giống `password`. Ví dụ, giá trị `memberOf` có thể tiết lộ quan hệ công việc; `mail` và `telephoneNumber` là thông tin liên hệ; `userCertificate` có thể chứa dữ liệu định danh. Quyết định ghi phải dựa trên mục đích và phân loại dữ liệu của hệ thống.

## Thiết kế audit event tối thiểu

Một event thường cần các trường sau:

- `eventId`: định danh duy nhất để chống ghi trùng và đối soát.
- `occurredAt`: thời điểm hành động xảy ra, dùng định dạng thời gian có múi giờ như ISO-8601 UTC.
- `actorRef`: tham chiếu giả danh tới người hoặc dịch vụ khởi tạo thao tác.
- `targetRef`: tham chiếu giả danh tới entry hoặc đối tượng nghiệp vụ bị tác động.
- `directory`: tên logic của nguồn LDAP, ví dụ `employee-directory`; không cần ghi URL hoặc bind DN.
- `operation`: mã thao tác đã chuẩn hóa như `ENTRY_CREATED`, `ATTRIBUTE_CHANGED`, `ENTRY_DELETED` hoặc `DN_RENAMED`.
- `changedAttributes`: danh sách thuộc tính được phép ghi, không chứa giá trị thuộc tính.
- `outcome`: trạng thái như `ATTEMPTED`, `SUCCEEDED`, `FAILED` hoặc `UNKNOWN`.
- `correlationId`: mã tương quan không chứa username, email hoặc thông tin do client tùy ý cung cấp.
- `failureCode`: mã lỗi đã ánh xạ, chỉ có khi thao tác thất bại.

Ví dụ một event không chứa giá trị email hay DN gốc:

```json
{
  "eventId": "0e57e8a5-0e85-4f2a-aad4-85f04d3c9911",
  "occurredAt": "2026-11-26T14:30:00Z",
  "actorRef": "hmac:v2:8b2d...",
  "targetRef": "hmac:v2:0f41...",
  "directory": "employee-directory",
  "operation": "ATTRIBUTE_CHANGED",
  "changedAttributes": ["mail"],
  "outcome": "SUCCEEDED",
  "correlationId": "req-4dca7a2e",
  "failureCode": null
}
```

Event chỉ cho biết thuộc tính `mail` đã thay đổi. Người đọc audit không thể suy ra địa chỉ email cũ hoặc mới từ bản ghi này. Nếu nghiệp vụ cần biết chính xác nội dung đã thay đổi, hãy đánh giá riêng quyền truy cập, thời hạn lưu, mã hóa và cơ sở xử lý trước khi thêm giá trị vào một kho audit hạn chế.

## Giả danh actor và DN

Nếu log cần liên kết nhiều thay đổi của cùng một actor hoặc entry, dùng một mã nội bộ ngẫu nhiên không mang ý nghĩa cá nhân là lựa chọn tốt. Khi không có mã như vậy, có thể tạo token HMAC bằng khóa bí mật chuyên dụng. Không dùng SHA-256 thuần trên email, username hoặc DN: không gian giá trị dễ đoán có thể bị dò ngược bằng từ điển.

HMAC cần khóa riêng cho mục đích audit, được quản lý trong secret manager hoặc KMS, có mã phiên bản khóa để hỗ trợ luân chuyển. Không ghi khóa vào log hoặc cấu hình commit cùng mã nguồn. Nếu token được tạo từ DN, cần chuẩn hóa DN theo quy tắc matching của schema LDAP trước khi ký; chỉ chuyển chuỗi thành chữ thường không phải cách chuẩn hóa DN an toàn cho mọi directory. Khi có thể, hãy dùng opaque target ID của miền nghiệp vụ thay cho DN.

Token giả danh vẫn có thể được xem là dữ liệu cá nhân nếu hệ thống có khả năng liên kết nó với một người. Vì vậy, cần giới hạn quyền đọc, thời hạn lưu, mã hóa khi truyền và khi lưu, và ghi nhận việc truy cập audit. Không cung cấp endpoint tra token ngược cho người dùng thông thường.

## Ghi audit ở ranh giới nghiệp vụ

Đặt audit tại service thực hiện hành động nghiệp vụ. Đây là nơi biết actor, mục đích, target và ý nghĩa thay đổi. Không nên chỉ bật log chi tiết ở tầng LDAP client hoặc repository, vì tầng đó thường chỉ biết thao tác kỹ thuật và có thể nhìn thấy dữ liệu thô.

Ví dụ sau minh họa một service đổi email nhân viên. Event chỉ ghi tham chiếu actor/target và tên thuộc tính. `ActorReferenceProvider`, `TargetReferenceEncoder` và `AuditRecorder` là các thành phần ứng dụng cần triển khai theo chính sách của hệ thống:

```java
import java.time.Instant;
import java.util.Set;
import java.util.UUID;
import javax.naming.Name;

import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

enum AuditOutcome {
    ATTEMPTED, SUCCEEDED, FAILED
}

record DirectoryChangeEvent(
        UUID eventId,
        Instant occurredAt,
        String actorRef,
        String targetRef,
        String directory,
        String operation,
        Set<String> changedAttributes,
        AuditOutcome outcome,
        String correlationId,
        String failureCode) {}

interface AuditRecorder {
    void append(DirectoryChangeEvent event);
}

interface ActorReferenceProvider {
    String currentActorRef();
}

interface TargetReferenceEncoder {
    String encode(Name distinguishedName);
}

interface CorrelationIdProvider {
    String currentCorrelationId();
}

interface SafeFailureCodeMapper {
    String map(DataAccessException exception);
}

@Service
public class EmployeeDirectoryService {

    private final EmployeeRepository repository;
    private final AuditRecorder audit;
    private final ActorReferenceProvider actors;
    private final TargetReferenceEncoder targets;
    private final CorrelationIdProvider correlations;
    private final SafeFailureCodeMapper failureCodes;

    public EmployeeDirectoryService(
            EmployeeRepository repository,
            AuditRecorder audit,
            ActorReferenceProvider actors,
            TargetReferenceEncoder targets,
            CorrelationIdProvider correlations,
            SafeFailureCodeMapper failureCodes) {
        this.repository = repository;
        this.audit = audit;
        this.actors = actors;
        this.targets = targets;
        this.correlations = correlations;
        this.failureCodes = failureCodes;
    }

    public void changeEmail(Name employeeDn, String newEmail) {
        Employee employee = repository.findById(employeeDn)
                .orElseThrow(() -> new IllegalArgumentException("Employee not found"));
        employee.setEmail(newEmail);

        UUID eventId = UUID.randomUUID();
        String actorRef = actors.currentActorRef();
        String targetRef = targets.encode(employeeDn);
        String correlationId = correlations.currentCorrelationId();

        audit.append(event(eventId, actorRef, targetRef, correlationId,
                AuditOutcome.ATTEMPTED, null));

        try {
            repository.save(employee);
        } catch (DataAccessException operationFailure) {
            try {
                audit.append(event(eventId, actorRef, targetRef, correlationId,
                        AuditOutcome.FAILED, failureCodes.map(operationFailure)));
            } catch (RuntimeException auditFailure) {
                operationFailure.addSuppressed(auditFailure);
            }
            throw operationFailure;
        }

        // Nếu ghi event SUCCEEDED thất bại, thao tác LDAP có thể đã thành công.
        // Cần báo lỗi audit riêng và đưa eventId vào hàng đợi đối soát.
        try {
            audit.append(event(eventId, actorRef, targetRef, correlationId,
                    AuditOutcome.SUCCEEDED, null));
        } catch (RuntimeException auditFailure) {
            throw new AuditOutcomePendingException(eventId, auditFailure);
        }
    }

    private DirectoryChangeEvent event(
            UUID eventId,
            String actorRef,
            String targetRef,
            String correlationId,
            AuditOutcome outcome,
            String failureCode) {
        return new DirectoryChangeEvent(
                eventId,
                Instant.now(),
                actorRef,
                targetRef,
                "employee-directory",
                "ATTRIBUTE_CHANGED",
                Set.of("mail"),
                outcome,
                correlationId,
                failureCode);
    }
}

final class AuditOutcomePendingException extends RuntimeException {
    AuditOutcomePendingException(UUID eventId, Throwable cause) {
        super("LDAP change completed but audit outcome is pending; eventId=" + eventId, cause);
    }
}
```

Đây là ví dụ cấu trúc; `Employee`, `EmployeeRepository` và các provider là thành phần của ứng dụng. `TargetReferenceEncoder` cần tạo token an toàn, không trả lại DN nguyên bản. `SafeFailureCodeMapper` chỉ ánh xạ exception sang danh mục mã lỗi đã duyệt, không trả về `exception.getMessage()`.

Ví dụ dùng `record` của Java 16 trở lên; dự án dùng Java phiên bản thấp hơn có thể thay event record bằng POJO bất biến. Các import và kiểu `Employee` cần được thay bằng model thực tế của ứng dụng.

Ví dụ ghi `ATTEMPTED` trước khi thay đổi và `SUCCEEDED` sau khi repository hoàn tất. Nếu thao tác LDAP thất bại, service ghi `FAILED`. Nếu lần ghi `SUCCEEDED` vào audit store thất bại sau khi LDAP đã thay đổi, trạng thái thực tế là chưa đối soát; không được ghi nhận nhầm là LDAP thất bại. Hệ thống nên cảnh báo và dùng `eventId` để tìm event đang thiếu kết quả cuối cùng.

## Không ghi dữ liệu thô qua logging framework

Các lệnh log dưới đây dễ làm lộ dữ liệu và cần tránh:

```java
// Không an toàn: DN có thể chứa uid hoặc email.
log.info("Updating LDAP entry {}", employeeDn);

// Không an toàn: entity có thể in tất cả thuộc tính.
log.debug("Employee before update: {}", employee);

// Không an toàn: filter có thể chứa giá trị tìm kiếm do người dùng nhập.
log.debug("LDAP filter: {}", filter.encode());

// Không an toàn: exception message có thể chứa DN, URL hoặc filter.
log.error("LDAP update failed: {}", exception.getMessage());
```

Thay bằng log có cấu trúc, chỉ đưa vào các trường đã duyệt:

```java
log.info("LDAP operation completed: directory={}, operation={}, "
        + "outcome={}, durationMs={}, correlationId={}",
        "employee-directory",
        "ATTRIBUTE_CHANGED",
        "SUCCEEDED",
        duration.toMillis(),
        correlationId);
```

Nếu cần ghi lỗi kỹ thuật, log loại exception hoặc LDAP result code đã ánh xạ. Không tự động ghi stack trace vào kênh có phạm vi người đọc rộng nếu message của exception có thể chứa dữ liệu nhạy cảm. Kênh điều tra lỗi chi tiết phải có quyền truy cập hạn chế và chính sách lọc dữ liệu riêng.

Với dữ liệu đi qua MDC, chỉ đưa correlation ID đã được tạo hoặc kiểm tra định dạng, giới hạn độ dài và loại bỏ ký tự xuống dòng. Không đưa email, username, DN hoặc dữ liệu request tùy ý vào MDC vì chúng có thể xuất hiện trong mọi log thuộc request đó.

Kiểm soát phải áp dụng trên toàn đường đi của log: application logger, APM agent, distributed tracing, reverse proxy, message broker, dead-letter queue, SIEM và bản sao lưu. Redaction chỉ ở một appender không bảo vệ được dữ liệu nếu trace hoặc agent khác vẫn thu thập request/exception thô. Tắt hoặc cấu hình lại capture body, query và header nhạy cảm ở những thành phần đó.

## Đảm bảo audit đáng tin cậy

Một event đúng định dạng vẫn không có giá trị nếu có thể bị mất, sửa hoặc xóa mà không phát hiện. Hãy áp dụng các biện pháp sau:

- Ghi event vào kho audit có quyền append-only hoặc kiểm soát sửa/xóa ở cấp lưu trữ.
- Giới hạn quyền đọc audit theo vai trò; quản trị directory không mặc nhiên cần quyền đọc mọi audit event.
- Mã hóa khi truyền và khi lưu; quản lý khóa tách khỏi dữ liệu audit.
- Gắn `eventId`, `correlationId`, thời điểm và trạng thái để hỗ trợ chống ghi trùng, tìm kiếm và đối soát.
- Đồng bộ thời gian máy chủ và lưu timestamp ở định dạng rõ múi giờ.
- Quy định retention và quy trình xóa theo chính sách; không lưu vô thời hạn chỉ vì log có ích cho điều tra.
- Theo dõi số event thất bại khi ghi, event đang ở trạng thái chưa kết thúc và độ trễ chuyển event tới kho lưu trữ.
- Kiểm tra quyền truy cập và thử khôi phục audit store trong quy trình vận hành.

Không nên chỉ dựa vào log ứng dụng dạng file có quyền ghi chung cho mọi process. Với yêu cầu kiểm toán cao, cân nhắc kho audit riêng, quyền ghi một chiều, lưu trữ chống sửa đổi hoặc cơ chế phát hiện thay đổi như chữ ký/hash chain được quản lý khóa đúng cách. Hash chain không thay thế kiểm soát truy cập và bản sao lưu.

## Ranh giới nhất quán giữa LDAP và audit store

LDAP directory và audit database thường là hai hệ thống độc lập. Một lần `repository.save()` thành công không có nghĩa thao tác ghi audit kế tiếp cũng thành công. Ngược lại, event `ATTEMPTED` có thể tồn tại dù thao tác LDAP chưa xảy ra. Không nên giả định `@Transactional` thông thường tạo giao dịch nguyên tử giữa LDAP và một cơ sở dữ liệu audit.

Với hệ thống cần độ tin cậy cao, có thể dùng quy trình hai giai đoạn:

1. Tạo event `ATTEMPTED` bền vững với `eventId` duy nhất trước khi gọi LDAP. Nếu không thể ghi ý định, dừng thao tác thay đổi.
2. Thực hiện thay đổi LDAP và giữ lại thông tin kết quả ở dạng mã an toàn.
3. Ghi event kết thúc `SUCCEEDED` hoặc `FAILED` với cùng `eventId`.
4. Nếu không ghi được kết quả cuối, đánh dấu event cần đối soát và cảnh báo. Worker đối soát kiểm tra trạng thái LDAP bằng truy vấn được kiểm soát, sau đó bổ sung kết quả hoặc chuyển sang xử lý thủ công.

Nếu audit event được lưu trong database cùng giao dịch với một outbox, outbox giúp chuyển event bền vững tới hệ thống log. Tuy nhiên, khi LDAP là hệ thống bên ngoài giao dịch database, outbox không tự làm thay đổi LDAP và audit trở thành một giao dịch nguyên tử. Cần thiết kế trạng thái pending, retry idempotent và đối soát khi process dừng giữa hai bước.

Nếu chọn ghi audit sau thao tác LDAP để giảm độ trễ, cần chấp nhận một cửa sổ mà thay đổi đã thành công nhưng audit chưa được lưu. Hãy có cơ chế phát hiện khoảng trống đó và không âm thầm bỏ qua lỗi audit. Nếu chọn ghi ý định trước, event chưa có kết quả cuối phải được xem là trạng thái chưa xác định, không phải thành công.

## Kiểm thử bảo vệ dữ liệu trong log

Kiểm thử audit cần xác minh cả thông tin được ghi và thông tin không được ghi. Dùng dữ liệu sentinel dễ nhận diện như email giả `private-sentinel@example.test` hoặc chuỗi `SECRET-SENTINEL` trong fixture. Sau khi thực hiện thay đổi, kiểm tra audit event và technical log để chắc chắn sentinel không xuất hiện.

Các trường hợp nên có trong test:

1. Thay đổi một thuộc tính được phép ghi: audit có actorRef, targetRef, operation, tên thuộc tính, eventId và outcome.
2. Thay đổi thuộc tính nhạy cảm: audit chỉ ghi mã thao tác hoặc phân loại được duyệt, không ghi giá trị.
3. Thao tác thất bại: ghi failureCode đã ánh xạ; không ghi raw filter, DN hoặc exception message.
4. Audit store không khả dụng trước khi ghi `ATTEMPTED`: thao tác LDAP bị chặn theo chính sách fail-closed.
5. Audit store lỗi khi ghi kết quả cuối: hệ thống ghi nhận trạng thái cần đối soát, không báo nhầm rằng LDAP chưa thay đổi.
6. Log injection: correlation ID chứa ký tự xuống dòng hoặc quá dài bị từ chối hoặc chuẩn hóa.
7. Phân quyền: người dùng không có quyền không thể đọc event chứa tham chiếu giả danh hoặc dữ liệu audit hạn chế.
8. Retention: event hết hạn được xử lý theo chính sách đã định và không còn trong truy vấn thông thường.

Một kiểm thử đơn giản có thể kiểm tra serialized event không chứa sentinel:

```java
// Test sketch: objectMapper và auditFixtureForChange dùng cùng encoder
// với production; AssertJ cung cấp assertThat.
@Test
void auditEventDoesNotContainRawEmailOrDn() throws Exception {
    String rawEmail = "private-sentinel@example.test";
    String rawDn = "uid=private-sentinel,ou=employees,dc=example,dc=test";

    DirectoryChangeEvent event = auditFixtureForChange(rawDn, rawEmail);
    String serialized = objectMapper.writeValueAsString(event);

    assertThat(serialized).doesNotContain(rawEmail);
    assertThat(serialized).doesNotContain(rawDn);
    assertThat(serialized).contains("ATTRIBUTE_CHANGED");
}
```

`auditFixtureForChange` trong ví dụ test phải gọi cùng mapper và encoder được dùng ở production. Test không nên tự tạo event giả danh bằng cách thay chuỗi trực tiếp, vì như vậy không xác minh được implementation thực tế.

## Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Ghi toàn bộ entity hoặc `Attributes` | Log chứa nhiều trường cá nhân và có thể cả credential | Chỉ tạo audit DTO với allowlist trường. |
| Ghi DN nguyên bản | Lộ username, email hoặc cấu trúc tổ chức | Dùng opaque ID hoặc HMAC có khóa. |
| Hash email bằng SHA-256 thuần | Giá trị dễ bị dò bằng từ điển | Dùng HMAC với khóa bí mật chuyên dụng hoặc ID ngẫu nhiên. |
| Ghi exception message và raw filter | Có thể lộ DN, dữ liệu tìm kiếm và thông tin server | Ánh xạ lỗi sang mã an toàn; log server logic và correlation ID. |
| Chỉ ghi `SUCCEEDED` sau thao tác nhưng bỏ qua lỗi audit | Thay đổi LDAP không có bản ghi kiểm toán | Theo dõi event chưa kết thúc, cảnh báo và đối soát. |
| Dùng `@Transactional` để giả định LDAP và audit cùng commit | Tạo cảm giác nhất quán không có thật | Thiết kế event attempt/outcome, retry và reconciliation. |
| Lưu audit vô thời hạn hoặc mở quyền đọc rộng | Tăng rủi ro rò rỉ và lạm dụng dữ liệu | Áp dụng retention, phân quyền, mã hóa và audit truy cập. |

## Checklist trước khi phát hành

- [ ] Mục đích và trường dữ liệu của từng audit event đã được xác định.
- [ ] Actor và target dùng mã opaque hoặc token giả danh an toàn.
- [ ] Không ghi password, token, raw DN, raw filter, entity hoặc toàn bộ attribute.
- [ ] Giá trị cũ/mới bị loại bỏ mặc định và chỉ được thêm khi có phê duyệt rõ ràng.
- [ ] Technical log và business audit có schema, quyền truy cập và retention riêng.
- [ ] Event có ID, timestamp, correlation ID và outcome để đối soát.
- [ ] Lỗi LDAP được ánh xạ sang failure code, không phát tán exception message.
- [ ] Kho audit có kiểm soát sửa/xóa, mã hóa, phân quyền và giám sát.
- [ ] Có quy trình xử lý event thiếu outcome hoặc audit store không khả dụng.
- [ ] Test xác nhận sentinel PII và secret không xuất hiện trong audit hoặc log.

Nhật ký thay đổi tốt phải giúp người có thẩm quyền hiểu hành động đã diễn ra mà không biến log thành bản sao của LDAP directory. Hãy ghi vừa đủ để trả lời ai, làm gì, trên đối tượng nào, khi nào và kết quả ra sao; mọi giá trị cá nhân khác cần được loại bỏ hoặc bảo vệ theo một quyết định riêng.
