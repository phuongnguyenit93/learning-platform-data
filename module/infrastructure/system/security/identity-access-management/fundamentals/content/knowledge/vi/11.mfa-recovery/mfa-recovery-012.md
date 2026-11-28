# Audit thay đổi MFA

## 1. Vì sao thay đổi MFA cần một dấu vết kiểm toán riêng?

Một tài khoản quản trị đang sử dụng TOTP. Sau khi một phiên trình duyệt bị chiếm, bên khác yêu cầu thay phương thức MFA và bổ sung khóa xác thực mới. Nếu hệ thống chỉ lưu dòng “cập nhật thành công”, đội vận hành khó trả lời ai thực hiện, thay đổi yếu tố nào, đã xác minh bằng chứng gì và chủ tài khoản có được thông báo hay chưa.

**Audit thay đổi MFA** là quá trình tạo, bảo vệ và khai thác bằng chứng về những hành động làm thay đổi khả năng xác thực nhiều yếu tố của tài khoản. Đối tượng không chỉ là lần đăng nhập: thêm authenticator, thay thiết bị, thu hồi yếu tố, cấp lại recovery code hoặc cho phép ngoại lệ MFA đều có thể ảnh hưởng quyền kiểm soát danh tính.

Trong nền tảng IAM, audit hỗ trợ quản lý vòng đời credential, xử lý khôi phục, quản lý đặc quyền và điều tra sự cố. Nó kết nối xác thực với trách nhiệm của người dùng, quản trị viên, helpdesk, dịch vụ tự động và identity provider. Audit không tự cấp hay thu hồi quyền; quyết định truy cập vẫn phải được thực thi bằng trạng thái tài khoản, chính sách và các cơ chế RBAC/ABAC liên quan.

Sau bài học, người học có thể:

- Xác định những thay đổi MFA cần ghi nhận và phân biệt từng giai đoạn của hành động.
- Thiết kế sự kiện trả lời được ai, làm gì, với tài khoản nào, khi nào và theo căn cứ nào.
- Loại bí mật xác thực khỏi dữ liệu audit.
- Giữ audit nhất quán với thay đổi credential và xử lý việc chuyển tiếp bị lỗi.
- Phân quyền truy cập bằng chứng, phát hiện can thiệp và xây dựng cảnh báo có ngữ cảnh.
- Dùng một chuỗi sự kiện để điều tra thay đổi MFA bị chủ tài khoản phủ nhận.

## 2. Xác định phạm vi sự kiện

### 2.1. Thay đổi MFA không chỉ là bật hoặc tắt

| Nhóm hành động | Ví dụ cần ghi nhận | Thông tin thay đổi hữu ích |
|---|---|---|
| Đăng ký | Bắt đầu liên kết TOTP, xác nhận khóa WebAuthn mới | Loại yếu tố, định danh nội bộ, giai đoạn xác nhận. |
| Thay thế | Đổi điện thoại TOTP, thay khóa đã mất | Yếu tố cũ và mới, trạng thái, flow và căn cứ thay thế. |
| Thu hồi | Xóa một khóa, vô hiệu yếu tố bị lộ | Phạm vi thu hồi và lý do được kiểm soát. |
| Chính sách tài khoản | Bật yêu cầu MFA, tạm miễn hoặc tắt yêu cầu | Phạm vi, thời hạn ngoại lệ, chính sách và người phê duyệt nếu có. |
| Recovery code | Cấp bộ mới, thu hồi bộ cũ, sử dụng một mã | Generation, định danh mã nội bộ, kết quả và mục đích. |
| Khôi phục | Helpdesk reset MFA, hoàn tất đăng ký lại | Actor, tài khoản đích, hồ sơ hỗ trợ và bằng chứng quyết định. |
| Kênh nhận mã | Đổi số hoặc địa chỉ dùng cho phương thức liên quan | Tham chiếu đối tượng và trạng thái xác minh đã được lọc. |

Các sự kiện thay đổi chính sách cấp tổ chức cũng cần được xem xét. Một quản trị viên bỏ yêu cầu MFA cho cả nhóm có thể ảnh hưởng nhiều tài khoản dù không sửa trực tiếp bản ghi authenticator của từng người.

Với chính sách nhóm, ghi sự kiện tại đối tượng chính sách và phạm vi áp dụng. Không tự tạo hàng nghìn sự kiện “người dùng tự tắt MFA” khi người dùng không thực hiện hành động đó.

### 2.2. Phân biệt yêu cầu, xác nhận và trạng thái có hiệu lực

```text
REQUESTED -> CHALLENGED -> VERIFIED -> COMMITTED
                 |            |
                 +-> REJECTED  +-> CANCELLED hoặc EXPIRED

Sau COMMITTED:
NOTIFICATION_QUEUED -> DELIVERED hoặc DELIVERY_FAILED
```

Đây là mô hình giai đoạn minh họa, không phải yêu cầu dùng đúng các tên trên. Điều quan trọng là ý nghĩa được xác định và nhất quán giữa các thành phần.

Hiển thị QR TOTP không có nghĩa TOTP đã được xác nhận hoạt động. Một request HTTP trả về 200 có thể chỉ có nghĩa giao diện khởi tạo thành công. Sự kiện `COMMITTED` phải phản ánh thay đổi đã có hiệu lực tại nguồn dữ liệu có thẩm quyền.

Tương tự, đã tạo tác vụ thông báo khác với dịch vụ gửi đã nhận, đã giao thành công hoặc người dùng thực sự đã đọc. Không gộp những trạng thái này vào một cờ `notified=true` không có định nghĩa.

### 2.3. Ghi cả hành động không thành công

Yêu cầu thay MFA bị từ chối do thiếu bằng chứng, sai quyền hoặc vượt giới hạn thử có thể giúp phát hiện hành vi đáng ngờ. Chúng cần được phân biệt với thay đổi thành công để không gây hiểu nhầm khi điều tra.

Không cần sao chép mọi request kỹ thuật vào audit nghiệp vụ. Hãy chọn các điểm có ý nghĩa đối với quyết định bảo mật, đồng thời dùng log vận hành và trace để bổ sung chẩn đoán theo phạm vi đã được kiểm soát.

## 3. Sự kiện cần trả lời những câu hỏi nào?

### 3.1. Các trường cốt lõi

| Câu hỏi | Trường minh họa | Lưu ý |
|---|---|---|
| Sự kiện nào? | `event_id`, `event_type`, `schema_version` | ID chống trùng không nhất thiết biểu diễn thứ tự. |
| Xảy ra lúc nào? | `occurred_at`, `recorded_at` | Phân biệt thời điểm nghiệp vụ và thời điểm tiếp nhận. |
| Ở đâu? | `producer`, `tenant_ref`, `environment` | Giữ đúng ranh giới tenant và môi trường. |
| Ai thực hiện? | `actor_type`, `actor_ref` | Người dùng, hỗ trợ, quản trị viên và dịch vụ có vai trò khác nhau. |
| Tác động ai? | `subject_ref` | Có thể khác actor. |
| Tác động cái gì? | `factor_ref`, `factor_type`, `policy_ref` | Dùng định danh nội bộ, không dùng bí mật làm khóa truy vết. |
| Thay đổi ra sao? | Trạng thái trước/sau hoặc danh sách tham chiếu bị ảnh hưởng | Chỉ lưu phần được phép tiết lộ. |
| Theo căn cứ nào? | `authorization_ref`, `policy_version`, `reason_code` | Liên kết quyết định đã kiểm chứng phía server. |
| Trong flow nào? | `flow_ref`, `request_ref`, `case_ref` | Hỗ trợ nối sự kiện mà không cần raw session token. |
| Kết quả là gì? | `phase`, `outcome`, `security_version` | Phân biệt thất bại, chờ và đã commit. |

Theo [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-attributes), dữ liệu sự kiện cần đủ để xác định thời gian, nguồn, chủ thể và hành động. Với audit MFA, các trường cụ thể phải được chọn theo câu hỏi điều tra và kiến trúc, không phải chỉ dựa vào những gì framework có thể ghi ra.

### 3.2. Actor và tài khoản bị tác động là hai đối tượng

Nếu nhân viên hỗ trợ thu hồi TOTP cho một người dùng, `actor_ref` là nhân viên hoặc danh tính dịch vụ thực thi, còn `subject_ref` là người dùng bị thay đổi. Ghi actor bằng tài khoản đích sẽ làm mất trách nhiệm của người can thiệp.

Trong luồng có phê duyệt hoặc ủy quyền, có thể cần thêm tham chiếu người đề nghị, người phê duyệt và thực thể thực thi. Không suy diễn rằng người có token dịch vụ trực tiếp là người đã ra quyết định nghiệp vụ.

Actor phải được xác định từ danh tính và ngữ cảnh đã xác thực. Không nhận trường `changedBy` trong JSON của client rồi dùng làm bằng chứng duy nhất. Một ID nằm trong payload chỉ là dữ liệu khai báo cho đến khi máy chủ xác minh quan hệ và quyền tương ứng.

### 3.3. Ví dụ một sự kiện đã commit

Các giá trị dưới đây là dữ liệu giả lập:

```json
{
  "schema_version": 1,
  "event_id": "ccfd2b0e-fb97-4c4a-8509-27f22eebd343",
  "event_type": "MFA_FACTOR_REVOKED",
  "occurred_at": "2026-01-15T03:04:05Z",
  "producer": "identity-service",
  "tenant_ref": "tenant-demo",
  "actor_type": "SUPPORT",
  "actor_ref": "support-demo",
  "subject_ref": "subject-demo",
  "factor_ref": "factor-demo",
  "factor_type": "TOTP",
  "phase": "COMMITTED",
  "outcome": "SUCCESS",
  "change": {"from": "ACTIVE", "to": "REVOKED"},
  "reason_code": "VERIFIED_DEVICE_LOSS",
  "authorization_ref": "decision-demo",
  "flow_ref": "flow-demo",
  "case_ref": "case-demo",
  "policy_version": "mfa-change-v4",
  "security_version": 18
}
```

Sự kiện này không nói mọi phiên đã bị thu hồi, mọi thông báo đã giao hoặc tài khoản đã hoàn tất khôi phục. Những kết quả đó cần sự kiện hoặc bằng chứng riêng nếu nằm trong phạm vi của quy trình.

## 4. Ghi đủ bằng chứng và giữ bí mật ngoài audit

### 4.1. Không ghi dữ liệu có thể trở thành credential

| Dữ liệu | Cách xử lý trong audit |
|---|---|
| TOTP seed, URI `otpauth`, QR chứa seed | Không ghi. Dùng `factor_ref` và trạng thái. |
| OTP người dùng nhập | Không ghi giá trị; chỉ ghi kết quả xác minh và mã lý do. |
| Recovery code hoặc verifier của mã | Dùng `code_id`, generation và kết quả. |
| Mật khẩu hoặc reset token | Không ghi vào sự kiện. |
| Cookie, access token, refresh token | Dùng định danh tương quan nội bộ không cấp quyền truy cập. |
| Số điện thoại hoặc email | Chỉ giữ phần cần thiết đã che hoặc tham chiếu an toàn. |
| Tên thiết bị và user-agent tự khai | Giới hạn độ dài, lọc và mã hóa đúng nơi hiển thị. |

Audit không cần lưu bí mật trước và sau để chứng minh thay đổi. Ví dụ, bằng chứng “TOTP A đã thu hồi, TOTP B đã xác nhận” không đòi hỏi giữ seed của A hay B trong lịch sử.

Khóa công khai cũng không mặc nhiên nên được sao chép đầy đủ vào mọi kho audit. Dùng tham chiếu credential nội bộ nếu đã đủ mục đích, và xem xét khả năng liên kết danh tính giữa hệ thống khi quyết định lưu thêm dữ liệu.

### 4.2. Trạng thái trước/sau cần được chọn lọc

Nên ghi những thay đổi có ý nghĩa bảo mật: từ `PENDING` sang `ACTIVE`, từ `ACTIVE` sang `REVOKED`, số yếu tố còn dùng được, generation recovery code hoặc thời hạn ngoại lệ.

Không serialize toàn bộ entity `User` hoặc `MfaCredential` để lấy diff rồi hy vọng bộ lọc tự loại được mọi bí mật. Một field mới thêm vào entity có thể bị xuất hiện trong audit mà không ai điều chỉnh bộ che dữ liệu.

Thiết kế theo danh sách trường được phép ghi giúp giảm rủi ro này. Nếu cần bổ sung trường, thay đổi schema và kiểm tra người tiêu thụ theo phiên bản rõ ràng.

### 4.3. Nguồn thời gian, IP và tương quan

Thời điểm nghiệp vụ nên đến từ máy chủ hoặc nguồn có thẩm quyền; timestamp của client có thể được giữ như dữ liệu khai báo nếu cần, nhưng không thay cho thời điểm đã xác minh. Lưu mốc thời gian có múi giờ hoặc UTC, đồng bộ đồng hồ và theo dõi độ lệch.

IP lấy từ proxy cần tuân theo cấu hình proxy đáng tin. Không coi mọi giá trị `X-Forwarded-For` do caller gửi là địa chỉ gốc đã được xác minh. Vị trí suy ra từ IP chỉ là tín hiệu, không phải kết luận chắc chắn về người thực hiện.

Một `request_ref` hoặc `flow_ref` do server quản lý giúp liên kết nhiều sự kiện. Phân biệt tham chiếu này với bearer token: người có ID tương quan không được nhờ đó truy cập phiên hoặc tiếp tục khôi phục.

## 5. Audit nhất quán với thay đổi MFA

### 5.1. Hai thứ tự ghi đều có thể sai

```text
Ghi log thành công -> cập nhật MFA thất bại
    => có bằng chứng thành công cho một thay đổi chưa xảy ra

Cập nhật MFA thành công -> ghi audit thất bại
    => trạng thái đã đổi nhưng thiếu bằng chứng tương ứng
```

Một dòng log trước khi gọi repository không chứng minh transaction đã commit. Ngược lại, một lời gọi logger sau commit có thể bị mất khi tiến trình dừng ở giữa hai thao tác.

### 5.2. Lưu thay đổi và audit bằng cùng giao dịch

Mã giả cho một thay đổi có yêu cầu audit bền vững:

```text
xác minh phiên, bằng chứng bổ sung và quyền thay MFA
kiểm tra giới hạn thử và trạng thái flow

bắt đầu transaction
    khóa hoặc kiểm tra version tài khoản/credential liên quan
    xác nhận điều kiện thay đổi vẫn còn hợp lệ
    thực hiện thay đổi MFA
    tăng security_version theo thiết kế
    tạo sự kiện audit COMMITTED từ trạng thái thực tế
    lưu sự kiện audit và bản ghi outbox trong cùng transaction
commit

sau commit:
    chuyển tiếp sự kiện đến kho audit trung tâm
    tạo hoặc thực thi thông báo theo quy trình
    theo dõi kết quả từng tác vụ
```

Nếu bản ghi audit là điều kiện bắt buộc cho loại thay đổi này và không thể lưu trong transaction, thay đổi không được báo thành công. Đây là quyết định thiết kế cho đường thay đổi nhạy cảm, không có nghĩa mọi lỗi log chẩn đoán phải dừng toàn bộ ứng dụng.

Nếu kho audit trung tâm chưa nhận được nhưng outbox bền vững đã ghi cùng thay đổi, hệ thống có thể chuyển tiếp lại theo chính sách. Cần giới hạn thời gian tồn đọng và có phương án khi bộ đệm không còn đáp ứng khả năng bảo đảm đã đặt ra.

### 5.3. Chống trùng và sự kiện đến sai thứ tự

Consumer có thể nhận một sự kiện nhiều lần. Dùng `event_id` và cơ chế xử lý lặp an toàn để không nhân đôi số lần thay đổi, số thông báo hoặc cảnh báo. Retry chuyển tiếp một sự kiện không phải một thay đổi MFA mới.

`security_version` hoặc thứ tự trong phạm vi một tài khoản có thể giúp phát hiện thiếu sự kiện và nối diễn biến. UUID ngẫu nhiên không thể được dùng làm thứ tự commit. Timestamp cũng có thể trùng hoặc lệch giữa máy chủ.

Không yêu cầu một thứ tự tổng duy nhất cho mọi tenant nếu nghiệp vụ không cần. Xác định rõ phạm vi mà version có ý nghĩa và cách xử lý việc backfill hoặc nhận trễ; một bước nhảy version chỉ có ý nghĩa khi biết những loại thay đổi nào cùng dùng bộ đếm đó.

## 6. Ví dụ Java: mô hình audit theo danh sách trường cho phép

Ví dụ Java 17 dưới đây minh họa một DTO dành cho thay đổi đã thành công. Các field tham chiếu phải được lấy từ ngữ cảnh và entity phía server sau khi đã kiểm chứng. DTO không chứa seed, OTP, token hay payload yêu cầu.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

public record MfaCommittedEvent(
        UUID eventId,
        Instant occurredAt,
        String tenantRef,
        Actor actor,
        String subjectRef,
        Action action,
        FactorType factorType,
        String factorRef,
        UUID flowRef,
        String authorizationRef,
        String policyVersion,
        long securityVersion) {

    private static final Pattern INTERNAL_REF =
            Pattern.compile("[A-Za-z0-9._:-]{1,80}");

    public enum ActorType {
        SELF_SERVICE, ADMIN, SUPPORT, SYSTEM
    }

    public enum Action {
        FACTOR_BOUND, FACTOR_REVOKED, FACTOR_REPLACED
    }

    public enum FactorType {
        TOTP, WEBAUTHN, RECOVERY_CODES, SMS
    }

    public record Actor(ActorType type, String ref) {
        public Actor {
            Objects.requireNonNull(type);
            requireInternalRef(ref);
        }
    }

    public MfaCommittedEvent {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(actor);
        Objects.requireNonNull(action);
        Objects.requireNonNull(factorType);
        Objects.requireNonNull(flowRef);
        requireInternalRef(tenantRef);
        requireInternalRef(subjectRef);
        requireInternalRef(factorRef);
        requireInternalRef(authorizationRef);
        requireInternalRef(policyVersion);

        if (securityVersion < 0) {
            throw new IllegalArgumentException("Invalid security version");
        }
    }

    private static void requireInternalRef(String value) {
        if (value == null || !INTERNAL_REF.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid audit reference");
        }
    }
}
```

### 6.1. Điều mô hình này bảo vệ và điều còn phải triển khai

Enum giúp giảm số chuỗi tự do. Kiểm tra định dạng và độ dài hạn chế ký tự điều khiển trong các tham chiếu theo quy ước minh họa. Thông báo lỗi không ghép lại giá trị người gọi đưa vào, tránh tạo thêm đường ghi dữ liệu nhạy cảm.

Regex không phải công cụ phát hiện bí mật: một token có thể tình cờ phù hợp mẫu. Vì vậy nguồn tạo DTO phải chủ động chọn định danh nội bộ và không truyền bí mật vào các field có tên `ref`.

Mô hình này chỉ bao phủ một số thay đổi authenticator. Sự kiện thất bại, thay chính sách, thay bộ recovery code hoặc thay nhiều yếu tố cần kiểu dữ liệu phù hợp khác. Không nhồi tất cả vào một field ghi chú tự do chỉ để giữ nguyên DTO.

Serializer cần tạo cấu trúc đúng định dạng, chẳng hạn JSON, thay vì ghép chuỗi thủ công. Khi hiển thị trên trang audit, dữ liệu phải được mã hóa theo ngữ cảnh đầu ra. Dùng logging có cấu trúc không tự loại bỏ khả năng log injection hoặc XSS trong trang xem log.

### 6.2. Tạo đối tượng từ trạng thái thực tế

Sự kiện được tạo sau khi service đã xác định chuyển trạng thái thành công và được lưu cùng giao dịch thay đổi. Đặt tên class là `CommittedEvent` không tự làm transaction đã commit: chỉ phát hành ra bên ngoài sau khi nguồn dữ liệu xác nhận commit, chẳng hạn qua outbox.

`authorizationRef` trỏ tới quyết định được kiểm chứng; nó không phải mã chấp thuận do client tự khai. Nếu không có bằng chứng phù hợp, tạo sự kiện từ chối riêng và không sửa trạng thái MFA.

Trong trường hợp thay TOTP cũ bằng yếu tố mới, có thể ghi một sự kiện tổng của thao tác và các sự kiện con dùng chung `flowRef`. Phải nêu rõ yếu tố nào được kích hoạt, yếu tố nào được thu hồi và liệu việc đó có nằm trong một giao dịch nguyên tử hay nhiều bước được kiểm soát.

## 7. Bảo vệ tính toàn vẹn và quyền truy cập audit

### 7.1. Giảm khả năng tự sửa bằng chứng

Ứng dụng thay MFA thường chỉ cần quyền thêm sự kiện, không cần quyền sửa hoặc xóa mọi lịch sử. Người có quyền hỗ trợ reset MFA cũng không mặc nhiên được quyền xóa bằng chứng của thao tác đó.

| Vai trò | Quyền phù hợp theo nhu cầu |
|---|---|
| Dịch vụ phát sinh thay đổi | Ghi sự kiện trong phạm vi đã xác định. |
| Bộ chuyển tiếp | Đọc hàng đợi, chuyển sự kiện và ghi kết quả giao nhận. |
| Nhân viên hỗ trợ | Xem phần lịch sử cần thiết cho tài khoản được phép hỗ trợ. |
| Nhóm an ninh | Tra cứu và liên kết sự kiện trong phạm vi điều tra. |
| Người quản lý lưu trữ | Thực hiện chính sách giữ/xóa với quyền và kiểm soát riêng. |
| Người dùng cuối | Xem lịch sử đã lọc của chính tài khoản, nếu sản phẩm hỗ trợ. |

Các quyền này cần được thực thi tại API và kho dữ liệu, có ranh giới tenant. Ẩn nút trên giao diện không ngăn một truy vấn trực tiếp đọc lịch sử của tài khoản khác.

### 7.2. Append-only không đồng nghĩa bất biến tuyệt đối

Bảng chỉ cho ứng dụng `INSERT` giảm khả năng sửa nhầm, nhưng người có quyền quản trị cơ sở dữ liệu vẫn có thể vượt qua giới hạn đó. Nếu yêu cầu bảo vệ bao gồm quản trị viên bị chiếm, cần xem xét bản sao độc lập, lưu trữ có khóa giữ dữ liệu, phân tách quyền và cơ chế kiểm tra toàn vẹn.

Một chuỗi hash có thể hỗ trợ phát hiện thay đổi bản ghi khi có điểm kiểm chứng đáng tin. Nếu bên tấn công được sửa toàn bộ chuỗi và cả điểm kiểm chứng, họ có thể tính lại chuỗi. Việc xóa phần đuôi cũng khó phát hiện nếu không có thông tin cuối chuỗi được giữ độc lập.

Chữ ký, HMAC hoặc dấu kiểm tra toàn vẹn chỉ có ý nghĩa khi khóa, phạm vi ký, cách chuẩn hóa dữ liệu và nơi giữ mốc kiểm chứng được bảo vệ. Không tuyên bố “không thể sửa” chỉ vì mỗi dòng có thêm một cột hash.

### 7.3. Audit cũng là dữ liệu cần bảo vệ

Lịch sử MFA có thể cho thấy người dùng đang ở giai đoạn khôi phục, sử dụng loại authenticator nào và thời điểm có can thiệp hỗ trợ. Các thông tin đó có thể hỗ trợ nhắm mục tiêu nếu bị đọc rộng rãi.

Mã hóa đường truyền, bảo vệ dữ liệu lưu và kiểm soát người đọc. Theo dõi truy vấn, xuất dữ liệu và hoạt động quản trị của chính kho audit. Một bản export hoặc bản sao dự phòng cần chịu chính sách tương ứng, không trở thành bản sao ít được bảo vệ hơn.

Không ghi đè sự kiện cũ để “sửa lịch sử”. Nếu phát hiện phân loại hoặc thông tin tham chiếu sai, thêm sự kiện hiệu chỉnh chỉ rõ bản ghi liên quan và lý do, theo quy trình kiểm soát. Việc xóa theo chính sách lưu trữ là một quy trình khác, cần được thực hiện và chứng minh đúng phạm vi.

## 8. Thông báo thay đổi và bằng chứng giao nhận

### 8.1. Thông báo hỗ trợ người dùng phát hiện sự kiện trái phép

[NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html) yêu cầu thông báo độc lập với giao dịch khi liên kết authenticator mới và quy định thông báo đối với các sự kiện tài khoản liên quan. Với audit, cần giữ được liên hệ giữa thay đổi và quá trình thông báo, thay vì coi việc trả thông báo trên cùng màn hình là toàn bộ bằng chứng.

Thông báo có thể nêu loại thay đổi, thời gian, tài khoản đã che phù hợp và cách báo lại nếu không nhận ra hành động. Nó không cần chứa seed, recovery code hoặc liên kết cho phép tự tắt MFA.

Nếu kênh thông báo vừa được thay đổi trong cùng flow, cần xem xét kênh đã thiết lập còn đáng tin theo chính sách. Chỉ thông báo vào địa chỉ mới do bên thực hiện cung cấp có thể làm người chủ hợp lệ không biết mình vừa mất kiểm soát.

### 8.2. Theo dõi trạng thái riêng

```text
MFA_CHANGE_COMMITTED
    |
    +-> MFA_NOTIFICATION_QUEUED
            |
            +-> MFA_NOTIFICATION_PROVIDER_ACCEPTED
                    |
                    +-> MFA_NOTIFICATION_DELIVERED
                    hoặc MFA_NOTIFICATION_FAILED
```

Các trạng thái trên chỉ là ví dụ. Nhà cung cấp không hỗ trợ xác nhận giao thì không tự tạo sự kiện `DELIVERED`. Webhook giao nhận phải được xác minh nguồn và liên kết đúng thông điệp; dữ liệu client tự khai không đủ xác nhận đã gửi.

Việc thông báo thất bại không làm bản ghi thay đổi đã commit biến thành chưa xảy ra. Giữ hai sự thật riêng và xử lý retry, cảnh báo hoặc hạn chế tiếp theo theo chính sách. Không tự phục hồi authenticator cũ chỉ vì một email không gửi được.

## 9. Phát hiện chuỗi thay đổi đáng ngờ

### 9.1. Cảnh báo cần ngữ cảnh

| Chuỗi hoặc tín hiệu | Câu hỏi cần điều tra |
|---|---|
| Reset MFA rồi thêm yếu tố mới ngay sau đó | Quy trình khôi phục có đủ bằng chứng và đúng actor không? |
| Đổi kênh khôi phục, cấp lại mã, rồi tắt MFA | Có chuỗi chiếm quyền kiểm soát danh tính không? |
| Một actor hỗ trợ reset nhiều tài khoản trong thời gian ngắn | Có đợt hỗ trợ hợp lệ, lỗi tự động hóa hay lạm dụng quyền? |
| Bỏ MFA cho tài khoản đặc quyền rồi tạo token mới | Ai phê duyệt ngoại lệ và quyền đã được sử dụng thế nào? |
| Nhiều thay đổi đã commit nhưng không có thông báo | Có lỗi pipeline hoặc can thiệp đường thông báo không? |
| Trạng thái credential thay đổi nhưng không tìm thấy audit tương ứng | Có đường ghi bỏ qua service hoặc thiếu bằng chứng do lỗi xử lý không? |

Không kết luận xâm nhập chỉ từ một IP mới hoặc thời điểm ngoài giờ. Có thể có hỗ trợ theo ca, chuyển thiết bị hoặc tác vụ đã được phê duyệt. Cảnh báo nên đưa ra bằng chứng, độ tin cậy và quy trình xem xét, không chỉ một nhãn nguy hiểm.

### 9.2. Đối chiếu với trạng thái nguồn

Một công việc đối chiếu có thể so các version thay đổi đã commit với event ledger và trạng thái tiếp nhận của kho audit. Cần có mốc hoặc dấu vết nguồn để biết điều gì được kỳ vọng; đếm số dòng ở SIEM không tự chứng minh đã đủ mọi thay đổi.

Nếu một migration hoặc thao tác quản trị trực tiếp được phép, nó cũng cần tạo bằng chứng tương ứng theo quy trình. Đường admin API, batch job và công cụ hỗ trợ không được trở thành ngoại lệ không quan sát được.

Phân biệt sự kiện đang trên đường chuyển tiếp với sự kiện đã bị mất. Độ trễ vượt ngưỡng cần được cảnh báo, nhưng không tự bổ sung một sự kiện thành công giả chỉ để làm số liệu khớp.

### 9.3. Phản ứng có kiểm soát

Một cảnh báo có thể tạo case, yêu cầu xác minh bổ sung hoặc kích hoạt quy trình khoanh vùng đã được phê duyệt. Audit là đầu vào cho quyết định; không nên để một chuỗi do caller tự tạo dẫn đến tự khóa mọi tài khoản bất kỳ.

Nếu phải thu hồi phiên, authenticator hoặc ngoại lệ quyền, ghi sự kiện mới cho quyết định và kết quả đó. Đội điều tra cần thấy cả thay đổi ban đầu lẫn hành động xử lý, không chỉ phiên bản cuối cùng của tài khoản.

## 10. Tình huống điều tra: người dùng phủ nhận thay MFA

Một người dùng báo khóa xác thực mới không thuộc về họ. Lịch sử có các mốc tương đối sau:

| Mốc | Bằng chứng đã quan sát |
|---|---|
| T0 | Một yêu cầu reset MFA được tạo qua cổng hỗ trợ. |
| T1 | Quyết định hỗ trợ được phê duyệt và tham chiếu tới một flow cụ thể. |
| T2 | TOTP cũ bị thu hồi với actor là dịch vụ hỗ trợ, subject là người dùng. |
| T3 | Một khóa WebAuthn mới được xác nhận và liên kết. |
| T4 | Tác vụ thông báo được tạo nhưng giao nhận thất bại. |
| T5 | Một phiên mới truy cập API cấp token cho tích hợp. |

Các câu hỏi cần giải quyết gồm ai đã yêu cầu, ai phê duyệt, service thực thi thay mặt ai, bằng chứng hỗ trợ có phù hợp và khóa mới được liên kết trong flow nào. Không suy ra T0 đã làm MFA thay đổi; bằng chứng có hiệu lực nằm ở T2 và T3.

T4 giải thích vì sao người dùng có thể không nhận được thông báo, nhưng không tự chứng minh họ không chấp thuận thay đổi. T5 cần liên kết với audit phiên và token để đánh giá tác động; audit thay MFA một mình không mô tả toàn bộ hoạt động nghiệp vụ.

Nếu xác định khóa mới trái phép, hành động thu hồi phải tạo sự kiện riêng và xử lý các phiên, token liên quan theo phạm vi sự cố. Không xóa T3 để làm lịch sử trông như khóa chưa từng tồn tại.

Trong điều tra, luôn ghi rõ khoảng thời gian đã kiểm tra, hệ thống có dữ liệu, độ trễ tiếp nhận và phần bằng chứng còn thiếu. Không coi “không tìm thấy” là “chắc chắn không xảy ra” khi một nguồn log chưa được thu thập.

## 11. Quản lý lưu trữ và hệ thống liên kết

### 11.1. Thời gian lưu theo mục đích

Thời hạn giữ sự kiện cần dựa trên nhu cầu điều tra, yêu cầu tổ chức và quy định áp dụng đã được xác định. Không có một số ngày chung phù hợp với mọi loại hệ thống. Có thể phân biệt dữ liệu tra cứu thường xuyên, dữ liệu lưu trữ dài hạn và dữ liệu bị giữ lại cho một vụ việc cụ thể.

Khi hết hạn, xử lý cả bản sao, export và backup theo chính sách tương ứng. Nếu cần giữ dữ liệu cho điều tra đang diễn ra, quyền quyết định và phạm vi giữ phải được ghi nhận. Không tự giữ mọi dữ liệu mãi mãi chỉ vì nó có nhãn audit.

### 11.2. SSO và nguồn sự kiện bên ngoài

Nếu IdP sở hữu MFA, việc liên kết hoặc thu hồi yếu tố diễn ra tại IdP. Ứng dụng có thể cần thu thập audit qua API, webhook hoặc hệ thống tập trung được cung cấp. Nó không thể tự chứng minh mọi thay đổi MFA chỉ bằng log đăng nhập OIDC của mình.

Khi nhập sự kiện, giữ tham chiếu sự kiện gốc, nguồn, thời điểm nguồn và thời điểm tiếp nhận. Xác minh nguồn gửi, ánh xạ subject theo issuer và namespace, đồng thời tránh nhân đôi nếu webhook và công việc đồng bộ cùng nhận một sự kiện.

Nếu nguồn ngoài chỉ cung cấp “MFA reset” mà không có actor chi tiết, ghi nhận giới hạn đó. Không tự điền actor là người dùng cuối hoặc trạng thái đã thông báo chỉ để hoàn thành schema nội bộ.

### 11.3. Audit có phạm vi và phân loại

Thay đổi MFA người dùng khác với luân chuyển client secret hoặc chứng thư của workload. Có thể dùng chung hạ tầng audit, nhưng cần loại sự kiện và chính sách phù hợp với từng loại danh tính.

Lịch sử liên kết identity, đổi quyền hoặc sửa chính sách ABAC cũng có thể liên quan một sự cố. Dùng định danh tương quan để nối bằng chứng, tránh sao chép tất cả dữ liệu vào một bản ghi MFA quá lớn và khó kiểm soát.

## 12. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
|---|---|
| Khởi tạo TOTP nhưng không xác nhận | Không có sự kiện khẳng định yếu tố đã hoạt động. |
| Bằng chứng thay MFA không hợp lệ | Có kết quả từ chối phù hợp; credential không bị thay đổi. |
| Transaction thay đổi bị rollback | Không phát hành audit thành công cho thay đổi đó. |
| Không lưu được audit bắt buộc trong transaction | Không báo thay đổi thành công theo chính sách đã chọn. |
| Kho audit trung tâm gián đoạn | Bằng chứng bền vững được giữ và chuyển tiếp lại; tồn đọng được theo dõi. |
| Consumer nhận cùng event nhiều lần | Không nhân đôi thay đổi hoặc cảnh báo ngoài thiết kế. |
| Sự kiện đến sai thứ tự hoặc nhận trễ | Có thể nối đúng phạm vi version và phân biệt thời điểm nguồn/tiếp nhận. |
| Client tự khai actor, tenant hoặc timestamp | Không thay thế ngữ cảnh đã xác minh phía server. |
| Hai thay đổi chạy đồng thời | Audit phản ánh đúng kết quả và thứ tự được nguồn trạng thái xác nhận. |
| Tên thiết bị có ký tự điều khiển hoặc HTML | Không tạo log giả hoặc mã thực thi trên trang xem audit. |
| Log request, trace và lỗi được bật | Không thu thập seed, OTP, recovery code hay bearer token. |
| Người hỗ trợ xem tài khoản ngoài phạm vi | Bị chặn và truy cập audit được theo dõi phù hợp. |
| Nhà cung cấp chỉ xác nhận đã nhận thông báo | Không tự ghi thành đã giao hoặc người dùng đã đọc. |
| Thao tác qua admin API hoặc batch | Có bằng chứng tương ứng và đúng loại actor. |
| Sửa một trường trong kho audit hoặc xóa một phần lịch sử | Cơ chế bảo vệ và phát hiện hoạt động theo mô hình rủi ro đã chọn. |

Những tình huống này là tiêu chí cho phần triển khai. Có thể dùng tài khoản, authenticator và sự kiện giả lập; không cần đưa bí mật thật của người dùng vào báo cáo kiểm thử.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ ghi “MFA updated” | Không biết actor, phạm vi hay trạng thái có hiệu lực | Định nghĩa schema và ý nghĩa sự kiện. |
| Ghi entity trước/sau nguyên vẹn | Có thể lộ seed hoặc token qua lịch sử | Chọn rõ các field được phép. |
| Ghi thành công trước commit | Bằng chứng sai khi giao dịch thất bại | Lưu audit cùng thay đổi và phát hành sau commit. |
| Gửi sự kiện rồi không theo dõi giao nhận | Không phát hiện mất hoặc tồn đọng bằng chứng | Có outbox, chống trùng và chỉ số độ trễ. |
| Để nhân viên reset MFA sửa lịch sử của mình | Khó xác định trách nhiệm khi lạm dụng | Phân tách quyền và giữ bản sao phù hợp. |
| Gọi bảng có hash là bất biến tuyệt đối | Đánh giá quá mức khả năng chống can thiệp | Bảo vệ điểm kiểm chứng, khóa và quyền quản trị. |
| Tự coi gửi email là người dùng đã được thông báo | Che khuất lỗi giao nhận | Phân biệt hàng đợi, nhà cung cấp nhận và giao thực tế. |
| Chỉ audit luồng giao diện chính | Bỏ sót mobile, hỗ trợ và automation | Xác định điểm ghi tại nơi thay đổi có thẩm quyền. |
| Không tìm thấy log rồi kết luận không có sự kiện | Có thể bỏ sót dữ liệu chậm hoặc thiếu nguồn | Nêu giới hạn và đối chiếu bằng chứng nguồn. |

## 14. Bài tập thiết kế

Một nền tảng có ba đường thay MFA: người dùng tự phục vụ, helpdesk reset theo hồ sơ hỗ trợ và đồng bộ sự kiện từ IdP. Dữ liệu được chuyển qua outbox tới kho audit trung tâm; thông báo người dùng do dịch vụ khác thực hiện.

Hãy thiết kế sự kiện cho việc thay TOTP bằng khóa WebAuthn. Làm rõ actor và subject, trạng thái có hiệu lực, bằng chứng cấp quyền, dữ liệu trước/sau được giữ, ranh giới transaction và cách liên kết thông báo.

Sau đó xét trường hợp giao dịch rollback, consumer nhận trùng, webhook IdP tới trễ và người dùng phủ nhận thao tác khi thông báo giao thất bại. Thiết kế cần cho biết có thể khẳng định điều gì từ mỗi sự kiện, còn thiếu bằng chứng gì và ai được phép đọc hoặc hiệu chỉnh lịch sử.
