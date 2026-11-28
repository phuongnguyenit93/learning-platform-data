# Just-in-time access

**Just-in-time access (JIT access)** là mô hình cấp quyền truy cập trong thời gian ngắn, đúng phạm vi và đúng mục đích khi một người dùng hoặc workload thực sự cần thực hiện một thao tác. Khi công việc kết thúc hoặc thời hạn được cấp hết, quyền tạm thời được thu hồi hoặc tự hết hiệu lực.

Trong quản lý khóa mật mã, JIT access giúp giảm quyền thường trực đối với các thao tác nhạy cảm như giải mã, ký số, tạo khóa, thay đổi policy hoặc quản trị HSM/KMS. Một kỹ sư vận hành có thể không có quyền giải mã dữ liệu sản xuất mỗi ngày; khi cần xử lý sự cố được phê duyệt, họ yêu cầu quyền giải mã cho một key cụ thể, trong một khoảng thời gian ngắn và có audit.

JIT access kiểm soát **ai được phép yêu cầu thao tác nào, trên khóa nào, trong điều kiện nào và trong bao lâu**. Nó không làm cho khóa tự hết hạn, không thay thế việc bảo vệ vật liệu khóa và không bảo đảm thao tác đang chạy sẽ bị dừng ngay khi quyền hết hạn. Cần kết hợp JIT với danh tính mạnh, least privilege, kiểm soát phê duyệt, KMS/HSM và kiểm toán.

## 1. Vì sao cần Just-in-time access?

Quyền truy cập thường trực (standing access) khiến một danh tính giữ quyền trong cả những khoảng thời gian không cần sử dụng. Nếu tài khoản bị chiếm, token bị lộ hoặc máy trạm bị kiểm soát, kẻ tấn công có thể khai thác quyền đó cho tới khi phát hiện và thu hồi.

Rủi ro đặc biệt cao với quyền trên khóa:

- Quyền giải mã có thể làm lộ dữ liệu được bảo vệ.
- Quyền ký có thể tạo chữ ký được hệ thống khác tin cậy.
- Quyền tạo hoặc nhập khóa có thể đưa vật liệu khóa không được kiểm soát vào hệ thống.
- Quyền sửa policy có thể cấp thêm quyền cho một danh tính khác.
- Quyền xóa hoặc vô hiệu hóa khóa có thể làm gián đoạn dịch vụ hoặc khiến dữ liệu không thể giải mã.

JIT giảm khoảng thời gian mà quyền nhạy cảm tồn tại. Thay vì cấp quyền quản trị KMS lâu dài, hệ thống chỉ cấp một grant ngắn hạn sau khi kiểm tra danh tính, lý do, tài nguyên và điều kiện phê duyệt.

JIT không tự ngăn mọi cuộc tấn công. Nếu kẻ tấn công chiếm được phiên đang có quyền JIT, họ có thể sử dụng quyền trong cửa sổ hiệu lực. Vì vậy, cần giới hạn thao tác, key scope, TTL, số lần sử dụng nếu nền tảng hỗ trợ và theo dõi hành vi trong suốt phiên.

## 2. JIT access khác standing access và just-enough access

Ba khái niệm liên quan nhưng giải quyết các chiều khác nhau:

| Mô hình | Câu hỏi được giải quyết | Đặc điểm |
|---|---|---|
| Standing access | Ai có quyền thường trực? | Quyền được giữ liên tục, kể cả khi không cần dùng |
| Just-in-time access | Khi nào quyền được cấp và hết hiệu lực? | Quyền được cấp theo nhu cầu, trong thời gian giới hạn |
| Just-enough access (JEA) | Quyền được cấp rộng đến đâu? | Chỉ cấp đúng thao tác và tài nguyên cần thiết |

JIT và JEA nên được kết hợp. Một grant có TTL 15 phút nhưng cho phép quản trị mọi khóa trong toàn tổ chức vẫn quá rộng. Grant tốt cần đồng thời giới hạn thời gian, danh tính, key ID, thao tác, môi trường và ngữ cảnh.

Ví dụ:

- Quyền thường trực: nhóm vận hành có thể giải mã bằng mọi khóa production.
- Chỉ JIT: thành viên nhóm vận hành có quyền giải mã mọi khóa trong 30 phút sau khi yêu cầu.
- JIT kết hợp JEA: kỹ sư được phê duyệt quyền gọi thao tác giải mã trên một key cụ thể, cho một ticket cụ thể, trong 15 phút.

Phương án thứ ba thu hẹp cả thời gian lẫn phạm vi tác động.

## 3. JIT áp dụng ở những lớp nào?

JIT có thể được áp dụng ở nhiều lớp trong kiến trúc quản lý khóa:

1. **Danh tính:** kích hoạt vai trò đặc quyền hoặc cấp phiên đăng nhập quản trị trong thời gian ngắn.
2. **Credential:** phát hành access token hoặc credential tạm thời cho workload hay người vận hành.
3. **Policy/grant:** thêm quyền tạm thời cho một key, thao tác và principal cụ thể.
4. **Phiên HSM/KMS:** mở phiên hoặc cho phép gọi API mật mã trong thời hạn đã cấp.
5. **Thao tác nghiệp vụ:** yêu cầu phê duyệt bổ sung trước các hành động nhạy cảm như giải mã hàng loạt, ký phát hành hoặc xóa khóa.

Các lớp này không nhất thiết cùng có một TTL. Ví dụ, token đăng nhập có thể còn hiệu lực 30 phút, nhưng key grant chỉ cho phép ký trong 5 phút. Khi thiết kế, phải xác định lớp nào thực sự quyết định quyền cuối cùng và cách thu hồi ở từng lớp.

JIT cũng có thể áp dụng cho người và workload. Người vận hành thường cần ticket, MFA và phê duyệt; workload thường cần workload identity, policy theo môi trường và credential ngắn hạn tự động.

## 4. Các thành phần của một quy trình JIT

Một quy trình JIT thường có các thành phần:

- **Requester:** người dùng hoặc workload yêu cầu quyền.
- **Identity provider:** xác thực danh tính và cung cấp thông tin về nhóm, vai trò, thiết bị hoặc workload.
- **Policy engine:** đánh giá quyền được yêu cầu, ngữ cảnh và điều kiện.
- **Approval workflow:** yêu cầu người có thẩm quyền phê duyệt khi chính sách quy định.
- **Access broker:** phát hành credential hoặc grant tạm thời.
- **KMS/HSM:** thực hiện thao tác bằng khóa theo quyền được cấp.
- **Audit system:** ghi nhận yêu cầu, quyết định, thao tác và kết quả.

Policy engine phải kiểm tra ít nhất danh tính, trạng thái xác thực, key identifier, thao tác, môi trường, lý do và thời lượng yêu cầu. Có thể bổ sung trạng thái thiết bị, vị trí mạng, mức rủi ro, ticket hoặc cửa sổ bảo trì.

Access broker không nên tự quyết định dựa trên một trường do requester tùy ý gửi. Nó cần xác minh dữ liệu từ nguồn tin cậy và kiểm tra rằng approval gắn với đúng principal, key, operation và thời hạn.

## 5. Quy trình cấp quyền JIT

Một luồng điển hình gồm các bước:

1. **Xác định nhu cầu:** người dùng hoặc workload nêu rõ key, thao tác, lý do, ticket và thời lượng cần thiết.
2. **Xác thực mạnh:** xác minh identity bằng SSO, MFA hoặc workload identity phù hợp.
3. **Đánh giá policy:** kiểm tra principal có được yêu cầu quyền này không, thao tác có hợp lệ với key usage không và phạm vi có vượt giới hạn không.
4. **Phê duyệt:** yêu cầu người phê duyệt độc lập khi thao tác hoặc mức rủi ro yêu cầu.
5. **Cấp grant:** phát hành quyền hoặc credential tạm thời với TTL, scope và điều kiện rõ ràng.
6. **Thực hiện:** gọi KMS/HSM bằng grant đã cấp. Ưu tiên thao tác bên trong KMS/HSM, không xuất khóa thô ra ứng dụng.
7. **Theo dõi:** ghi lại thao tác, kết quả, lỗi và hành vi bất thường.
8. **Kết thúc:** thu hồi grant khi hoàn thành hoặc để grant hết hạn; đóng phiên và xóa credential tạm khỏi bộ nhớ.

Yêu cầu JIT nên mang thông tin đủ để truy vết và đánh giá. Một lý do chung chung như “cần quyền admin” không đủ để phê duyệt quyền giải mã dữ liệu production.

## 6. Giới hạn phạm vi grant

Một grant JIT nên giới hạn càng cụ thể càng tốt:

| Thuộc tính | Ví dụ giới hạn |
|---|---|
| Principal | Một user hoặc workload identity cụ thể |
| Key | Một key ID hoặc một nhóm khóa được định nghĩa rõ |
| Operation | Sign, decrypt hoặc generate data key |
| Environment | Production hoặc một tenant cụ thể |
| Resource context | Một ứng dụng, dịch vụ hoặc tài nguyên cụ thể |
| Duration | 5–30 phút theo mức rủi ro |
| Request context | Ticket, lý do, incident hoặc change request |
| Usage limit | Số lần gọi hoặc hạn mức nếu nền tảng hỗ trợ |

Không cấp quyền quản trị key policy chỉ vì requester cần giải mã một bản ghi. Không cấp quyền export key nếu mục tiêu chỉ là ký dữ liệu. Không dùng một role rộng cho nhiều mục đích khác nhau.

Cần phân biệt quyền trên key với quyền trên dữ liệu. Ví dụ, một thao tác decrypt trên key có thể cho phép giải mã nhiều ciphertext đã được mã hóa bằng key đó. Nếu ứng dụng cần giải mã một tập dữ liệu cụ thể, có thể phải giới hạn thêm ở lớp dịch vụ hoặc policy context, thay vì chỉ dựa vào key permission.

## 7. JIT với KMS và HSM

KMS thường cung cấp policy hoặc grant để kiểm soát principal được phép gọi thao tác trên key. JIT có thể được triển khai bằng cách:

- Cấp credential ngắn hạn cho workload hoặc người vận hành.
- Tạo grant tạm thời cho key và thao tác được phê duyệt.
- Sử dụng role session có TTL giới hạn.
- Yêu cầu broker kiểm tra policy rồi gọi KMS thay cho requester.
- Thu hồi grant hoặc credential sau khi công việc kết thúc.

HSM thường có mô hình user, role, partition, session hoặc quyền thao tác riêng tùy thiết bị. JIT có thể kích hoạt quyền quản trị hoặc cấp phiên thao tác trong thời gian giới hạn. Cần kiểm tra semantics thực tế của HSM: việc hết phiên có đóng mọi session hay không, lệnh đang chạy có hoàn tất hay không và credential có bị thu hồi ở thiết bị hay chỉ ở lớp quản lý bên ngoài.

Không phải KMS hoặc HSM nào cũng có JIT grant tích hợp. Một số môi trường cần access broker hoặc workflow bên ngoài để cấp quyền tạm thời. Không được giả định rằng việc đặt TTL cho token đăng nhập sẽ tự động giới hạn quyền trên mọi key; policy của KMS/HSM vẫn phải kiểm tra principal và operation.

## 8. Phân tách nhiệm vụ và phê duyệt độc lập

Các thao tác nhạy cảm không nên do một người tự yêu cầu, tự phê duyệt và tự thực hiện nếu chính sách yêu cầu kiểm soát kép.

**Separation of duties** có thể phân vai:

- Người yêu cầu mô tả công việc và tài nguyên cần truy cập.
- Người phê duyệt xác nhận nhu cầu và phạm vi.
- Hệ thống tự động phát hành grant sau khi policy và approval hợp lệ.
- Người vận hành hoặc workload thực hiện thao tác.
- Bộ phận giám sát kiểm tra audit và xử lý ngoại lệ.

Người phê duyệt không nên chỉ bấm đồng ý dựa trên tên ticket. Giao diện phê duyệt cần hiển thị principal, key ID, operation, environment, TTL, lý do và tác động có thể xảy ra.

Với một số thao tác có rủi ro cao như xóa khóa gốc, thay đổi policy quản trị hoặc export khóa, có thể cần hai người phê duyệt độc lập, MFA và quy trình change management riêng. JIT không loại bỏ yêu cầu kiểm soát kép.

## 9. TTL, hết hạn và thu hồi quyền

TTL xác định khoảng thời gian grant hoặc credential tạm thời còn hiệu lực. TTL cần đủ cho công việc nhưng không dài hơn mức cần thiết.

Các nguyên tắc:

- Đặt TTL ngắn theo mức rủi ro và độ dài thao tác.
- Không cho phép requester tự đặt TTL vượt maximum TTL.
- Không tự động gia hạn vô hạn.
- Cấp grant mới nếu công việc kéo dài và policy vẫn cho phép.
- Thu hồi sớm khi công việc kết thúc, requester mất quyền hoặc có dấu hiệu bị xâm phạm.
- Kiểm tra hành vi của hệ thống đích khi grant hết hạn hoặc bị thu hồi.

Hết hạn một access token không chắc chắn đóng phiên KMS đã mở trước đó. Thu hồi một grant cũng không nhất thiết dừng thao tác mật mã đã được chấp nhận và đang thực thi. Vì vậy, cần biết rõ thời điểm hệ thống kiểm tra quyền: lúc thiết lập phiên, lúc gửi từng request hay trong suốt thao tác.

Với thao tác dài hoặc batch, cần thiết kế checkpoint và giới hạn số lượng bản ghi. Nếu quyền bị thu hồi giữa chừng, hệ thống phải dừng an toàn, ghi nhận phần việc đã hoàn tất và không để trạng thái dữ liệu ở trạng thái không nhất quán.

## 10. JIT cho các thao tác khóa khác nhau

Không phải thao tác nào cũng có mức rủi ro giống nhau:

| Operation | Rủi ro | Kiểm soát JIT phù hợp |
|---|---|---|
| Describe metadata | Thường thấp hơn, nhưng có thể tiết lộ cấu trúc hệ thống | Read scope hẹp, audit |
| Encrypt hoặc generate data key | Có thể tạo dữ liệu mới phụ thuộc key | Giới hạn workload, key và quota |
| Decrypt | Có thể làm lộ dữ liệu rõ | Phạm vi dữ liệu, approval khi nhạy cảm, giám sát số lượng |
| Sign | Có thể tạo chữ ký được hệ thống khác tin cậy | Ràng buộc key, purpose, caller và payload context nếu hỗ trợ |
| Rotate | Có thể ảnh hưởng nhiều consumer và dữ liệu | Change approval, rollout và rollback plan |
| Change policy hoặc grant | Có thể mở rộng quyền cho principal khác | Approval độc lập, kiểm tra diff và audit |
| Disable hoặc delete | Có thể gây gián đoạn hoặc mất khả năng truy cập dữ liệu | Kiểm soát kép, kiểm tra dependency và recovery plan |
| Export key material | Có thể làm mất ranh giới bảo vệ KMS/HSM | Mặc định cấm hoặc yêu cầu kiểm soát đặc biệt |

JIT chỉ cấp quyền thực hiện thao tác mà key policy cho phép. Nếu key được tạo với usage chỉ cho phép verify, không thể dùng grant JIT để biến nó thành khóa ký. Quyền truy cập và thuộc tính mật mã của key phải được kiểm tra đồng thời.

## 11. Ví dụ thiết kế JIT access trong Java

Java application thường không tự quản lý policy IAM hoặc quyền HSM ở mức thấp. Nên đặt một abstraction trước KMS adapter hoặc access broker. Broker xác thực yêu cầu, kiểm tra approval và trả về grant ngắn hạn. KMS adapter sử dụng grant để gọi thao tác bằng key reference; private key không được trả về ứng dụng.

Ví dụ dưới đây mô tả hợp đồng ở cấp ứng dụng, không gắn với một nhà cung cấp KMS cụ thể:

~~~java
import java.time.Instant;

public final class JitKeyAccess {
    private JitKeyAccess() {
    }

    public enum KeyOperation {
        SIGN,
        DECRYPT,
        GENERATE_DATA_KEY
    }

    public static final class AccessRequest {
        private final String keyId;
        private final KeyOperation operation;
        private final String reason;
        private final String ticketId;

        public AccessRequest(
                String keyId,
                KeyOperation operation,
                String reason,
                String ticketId) {
            this.keyId = keyId;
            this.operation = operation;
            this.reason = reason;
            this.ticketId = ticketId;
        }

        public String keyId() {
            return keyId;
        }

        public KeyOperation operation() {
            return operation;
        }

        public String reason() {
            return reason;
        }

        public String ticketId() {
            return ticketId;
        }

    }

    public interface AccessBroker {
        AccessGrant request(AccessRequest request) throws Exception;

        void revoke(String grantId) throws Exception;
    }

    public interface KeyService {
        byte[] sign(String keyId, byte[] message, AccessGrant grant)
                throws Exception;
    }

    public static final class AccessGrant implements AutoCloseable {
        private final String grantId;
        private final String keyId;
        private final KeyOperation operation;
        private final Instant expiresAt;
        private final AccessBroker broker;
        private boolean closed;

        AccessGrant(
                String grantId,
                String keyId,
                KeyOperation operation,
                Instant expiresAt,
                AccessBroker broker) {
            this.grantId = grantId;
            this.keyId = keyId;
            this.operation = operation;
            this.expiresAt = expiresAt;
            this.broker = broker;
        }

        public void require(
                String requestedKeyId,
                KeyOperation requestedOperation) {
            if (closed || !Instant.now().isBefore(expiresAt)) {
                throw new IllegalStateException("JIT grant không còn hiệu lực");
            }
            if (!keyId.equals(requestedKeyId)
                    || operation != requestedOperation) {
                throw new SecurityException("Grant không đúng phạm vi thao tác");
            }
        }

        public String grantId() {
            return grantId;
        }

        @Override
        public void close() throws Exception {
            if (!closed) {
                broker.revoke(grantId);
                closed = true;
            }
        }
    }
}
~~~

Ví dụ sử dụng grant cho một thao tác ký:

~~~java
public final class SigningJob {
    private SigningJob() {
    }

    public static byte[] sign(
            JitKeyAccess.AccessBroker broker,
            JitKeyAccess.KeyService keyService,
            byte[] payload) throws Exception {

        JitKeyAccess.AccessRequest request =
            new JitKeyAccess.AccessRequest(
                "prod/orders-signing-key",
                JitKeyAccess.KeyOperation.SIGN,
                "Ký manifest phát hành",
                "CHANGE-4821"
            );

        try (JitKeyAccess.AccessGrant grant = broker.request(request)) {
            grant.require(
                "prod/orders-signing-key",
                JitKeyAccess.KeyOperation.SIGN
            );

            return keyService.sign(
                "prod/orders-signing-key",
                payload,
                grant
            );
        }
    }
}
~~~

Ví dụ thể hiện ba ranh giới:

- Request chỉ định key, operation, lý do và ticket.
- Grant giới hạn key, operation và thời điểm hết hạn.
- KeyService thực hiện ký bằng key reference trong KMS/HSM; ứng dụng chỉ nhận chữ ký.

Trong triển khai thật, không nên chỉ tin vào kiểm tra ở lớp Java. KMS/HSM hoặc access broker phải kiểm tra grant ở phía server cho từng request. Grant ID không phải bằng chứng quyền nếu không được backend xác thực. Đồng hồ ứng dụng chỉ hỗ trợ kiểm tra sớm; quyết định hết hạn cuối cùng phải do hệ thống cấp quyền hoặc dịch vụ đích thực hiện.

Đoạn code là hợp đồng minh họa. Cần xử lý trường hợp revoke thất bại trong close(), tránh che mất exception chính, và có cơ chế thu hồi phía server khi tiến trình crash. Không lưu access token dài hạn trong AccessGrant nếu có thể dùng handle do provider quản lý.

## 12. JIT cho người vận hành và workload

JIT cho người vận hành và JIT cho workload có thể dùng chung nguyên tắc nhưng khác luồng cấp quyền.

**Đối với người vận hành:**

- Xác thực SSO và MFA.
- Yêu cầu có lý do, ticket hoặc incident.
- Phê duyệt độc lập với người yêu cầu khi policy quy định.
- Cấp role hoặc grant có TTL ngắn.
- Ghi audit gắn với danh tính cá nhân.
- Tự động thu hồi và kiểm tra sau phiên.

**Đối với workload:**

- Xác thực bằng workload identity hoặc federation.
- Cấp quyền dựa trên service account, môi trường và thuộc tính workload.
- Dùng credential ngắn hạn hoặc grant riêng cho key/operation.
- Không nhúng access key dài hạn vào image hoặc biến cấu hình tĩnh.
- Giới hạn quyền theo instance, service hoặc tenant.
- Thu hồi khi workload bị xóa, thay thế hoặc mất trạng thái tin cậy.

Không nên dùng tài khoản dịch vụ dùng chung cho cả nhóm kỹ sư và ứng dụng. Điều đó làm mất khả năng quy trách nhiệm và khiến quyền JIT khó giới hạn theo principal thực tế.

## 13. Break-glass và tình huống khẩn cấp

Có những tình huống hệ thống phê duyệt thông thường không hoạt động nhưng cần quyền đặc biệt để khôi phục dịch vụ. **Break-glass access** là quy trình cấp quyền khẩn cấp có kiểm soát.

Break-glass không phải tài khoản admin dùng hằng ngày. Nó cần:

- Credential hoặc cơ chế kích hoạt được bảo vệ riêng.
- Danh tính cá nhân được xác minh mạnh.
- Lý do khẩn cấp và phạm vi thao tác rõ ràng.
- TTL rất ngắn và cảnh báo ngay khi sử dụng.
- Ghi audit độc lập, không phụ thuộc hoàn toàn vào hệ thống đang gặp sự cố.
- Hậu kiểm bắt buộc, đánh giá thao tác và thu hồi credential sau sự kiện.

Nếu hệ thống approval chính bị lỗi, có thể cần hai người giữ vai trò độc lập để kích hoạt quyền khẩn cấp. Không nên bỏ qua audit hoặc giữ quyền break-glass luôn mở để tiện vận hành.

## 14. Audit và giám sát JIT

Một hệ thống JIT cần ghi nhận cả quyết định cấp quyền và thao tác thực tế. Các trường hữu ích gồm:

- Principal yêu cầu và identity provider đã xác thực.
- Key ID, operation, environment và scope.
- Lý do, ticket, approval và người phê duyệt.
- Thời điểm yêu cầu, cấp grant, bắt đầu thao tác và hết hạn.
- Grant ID hoặc correlation ID đã được bảo vệ.
- Kết quả cấp quyền, renew, revoke và thao tác KMS/HSM.
- Lỗi policy, thao tác bị từ chối và hoạt động ngoài dự kiến.

Không ghi private key, secret value, plaintext nhạy cảm, token hoặc nội dung dữ liệu được giải mã vào audit log. Log cần được bảo vệ khỏi sửa đổi, có đồng bộ thời gian và được gửi tới hệ thống giám sát độc lập.

Các cảnh báo nên bao gồm:

- Yêu cầu JIT bất thường theo principal, key hoặc thời gian.
- Nhiều yêu cầu bị từ chối liên tiếp.
- Grant có TTL hoặc scope vượt chính sách.
- Thao tác giải mã hoặc ký vượt mức thông thường.
- Grant không được revoke khi workload kết thúc.
- Quyền quản trị hoặc policy bị thay đổi trong phiên JIT.

Audit cần cho phép nối yêu cầu ban đầu với grant, API call và kết quả để điều tra được toàn bộ chuỗi sự kiện.

## 15. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Cấp JIT role quá rộng | Quyền tạm thời vẫn có blast radius lớn | Kết hợp JIT với JEA và key scope |
| TTL quá dài | Quyền đặc biệt tồn tại lâu hơn nhu cầu | Đặt maximum TTL theo operation |
| Chỉ hết hạn token mà không thu hồi grant | Quyền ở KMS/HSM có thể còn hiệu lực | Kiểm tra và thu hồi ở đúng lớp cấp quyền |
| Tin dữ liệu requester tự khai | Có thể giả ticket, key hoặc lý do | Xác minh từ identity, ticket và policy source |
| Người yêu cầu tự phê duyệt | Mất phân tách nhiệm vụ | Approval độc lập cho thao tác rủi ro |
| Dùng một role cho mọi operation | Quyền ký, giải mã, quản trị bị trộn lẫn | Tách role theo key usage và thao tác |
| Nghĩ revoke sẽ dừng lệnh đang chạy | Thao tác đã được chấp nhận có thể vẫn hoàn tất | Hiểu semantics backend và thiết kế checkpoint |
| Không audit quyết định bị từ chối | Mất tín hiệu phát hiện dò quyền | Ghi nhận cả allow và deny |
| JIT cho người và workload dùng chung identity | Không truy vết được chủ thể thực hiện | Dùng identity riêng và policy theo principal |
| Không có break-glass được kiểm soát | Khó khôi phục khi hệ thống phê duyệt lỗi | Thiết kế quy trình khẩn cấp và hậu kiểm |

## 16. Nguyên tắc triển khai an toàn

- Loại bỏ standing privilege không cần thiết đối với thao tác khóa có rủi ro cao.
- Kết hợp JIT với least privilege, key scope và operation-specific policy.
- Xác thực mạnh requester bằng MFA hoặc workload identity.
- Yêu cầu ticket, lý do và approval độc lập theo mức rủi ro.
- Cấp grant có TTL ngắn, maximum TTL và giới hạn thao tác.
- Kiểm tra quyền ở phía KMS/HSM hoặc access broker cho từng request.
- Thu hồi sớm khi công việc kết thúc; giám sát cả grant hết hạn và revoke thất bại.
- Không xuất key material nếu thao tác có thể thực hiện trực tiếp trong KMS/HSM.
- Tách quyền ký, giải mã, xoay vòng và quản trị policy.
- Ghi audit đầy đủ từ request đến kết quả, đồng thời bảo vệ log khỏi sửa đổi.
- Có quy trình break-glass độc lập và hậu kiểm.
- Kiểm thử trường hợp token hết hạn, grant bị revoke, workload crash, approval bị hủy và thao tác đang chạy.

JIT access thu hẹp thời gian và phạm vi của quyền sử dụng khóa bằng cách chỉ cấp quyền khi có nhu cầu cụ thể. Hiệu quả của nó phụ thuộc vào danh tính đáng tin cậy, policy đủ hẹp, phê duyệt độc lập khi cần, cơ chế hết hạn và thu hồi đúng ở KMS/HSM, cùng audit có thể kiểm chứng. Khi kết hợp JIT với JEA và key lifecycle management, hệ thống giảm quyền thường trực và giới hạn tác động khi một danh tính hoặc phiên làm việc bị xâm phạm.
