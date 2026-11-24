# Support agent privacy

## 1. Ranh giới quyền riêng tư của nhân viên hỗ trợ

Trong luồng khôi phục tài khoản, nhân viên hỗ trợ có thể cần xem trạng thái hồ sơ, hướng dẫn xác minh và xử lý tình huống người dùng mất mật khẩu, MFA, passkey hoặc thiết bị. Công việc đó không mặc nhiên đòi hỏi quyền đọc toàn bộ dữ liệu cá nhân hoặc quyền thay thế mọi phương thức xác thực.

Support agent privacy trong bài này tập trung vào cách giới hạn dữ liệu mà nhân viên hỗ trợ được tiếp cận, cách họ sử dụng dữ liệu và cách ngăn thông tin đi qua các kênh không phù hợp. Một phần liên quan cũng là bảo vệ thông tin cá nhân của chính nhân viên khi tương tác với người yêu cầu.

Thiết kế cần trả lời rõ:

- Nhân viên nào được mở hồ sơ nào?
- Họ cần xem những trường nào cho bước công việc hiện tại?
- Trường hợp nào được mở rộng quyền, trong bao lâu và vì mục đích gì?
- Quyền đọc hồ sơ khác quyền phê duyệt hoặc thay credential như thế nào?
- Những dữ liệu nào không được đưa vào giao diện hỗ trợ, hội thoại hoặc log?

Ví dụ, để biết người dùng cần làm bước gì tiếp theo, nhân viên có thể chỉ cần trạng thái “chưa hoàn tất bằng chứng bổ sung”. Họ không cần thấy OTP, liên kết reset đang có hiệu lực hoặc toàn bộ ảnh giấy tờ của người dùng.

**Phạm vi minh họa:** ma trận quyền, tên permission, API và mã Java dưới đây là thiết kế học tập. Phân quyền, thời hạn truy cập và quy trình mở rộng quyền cần được xác định theo dịch vụ thực tế.

## 2. Vì sao hỗ trợ phục hồi là một ranh giới nhạy cảm?

Người yêu cầu thường đang ở trạng thái thiếu một hoặc nhiều phương tiện xác thực. Nhân viên phải hỗ trợ họ mà không biến sự thông cảm, áp lực thời gian hoặc thông tin cá nhân thành đường bỏ qua bảo vệ.

Các nguy cơ chính gồm:

| Nguy cơ | Ví dụ | Ranh giới cần bảo vệ |
| --- | --- | --- |
| Social engineering | Người gọi biết tên, ngày sinh và mã ticket nên yêu cầu gỡ MFA | Biết thông tin không đồng nghĩa đã đủ bằng chứng |
| Truy cập vì tò mò | Nhân viên tìm hồ sơ của người quen | Quyền truy cập phải gắn với công việc được giao |
| Tài khoản nhân viên bị chiếm quyền | Kẻ khác dùng phiên hỗ trợ để đọc hồ sơ | Xác thực mạnh, quyền hẹp và thu hồi kịp thời |
| Nhầm hồ sơ | Nhân viên gửi thông tin của người A cho người B | Gắn thao tác và dữ liệu với đúng đối tượng |
| Sao chép ngoài hệ thống | Tải giấy tờ về máy cá nhân để xử lý nhanh | Hạn chế xuất dữ liệu và kênh lưu trữ |
| Công cụ hỗ trợ ghi quá nhiều | Chatbot, session replay hoặc log thu cả mã xác thực | Loại bỏ bí mật khỏi luồng quan sát |
| Quyền tồn tại quá lâu | Người đổi đội vẫn xem được hồ sơ cũ | Kiểm tra quyền hiện tại theo mỗi thao tác |

NIST SP 800-63B-4 lưu ý rằng phục hồi authenticator có sự hỗ trợ của con người cũng chịu nguy cơ social engineering. Vì vậy, quy trình hỗ trợ cần được thiết kế như một phần của cơ chế bảo vệ tài khoản. [NIST SP 800-63B-4, Authenticator Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html)

Không thể chỉ dựa vào cam kết “nhân viên sẽ không xem dữ liệu không cần thiết”. Hệ thống cần hạn chế việc đọc dữ liệu ngay từ backend và duy trì khả năng truy xuất hành vi truy cập.

## 3. Tách quyền xem, quyền xử lý và quyền thay đổi tài khoản

Một vai trò SUPPORT_AGENT quá rộng dễ gom nhiều quyền khác nhau vào cùng một nhóm. Nên xác định permission theo thao tác và tài nguyên.

| Permission minh họa | Cho phép | Không tự cho phép |
| --- | --- | --- |
| READ_CASE_SUMMARY | Xem bản tóm tắt của hồ sơ được giao | Xem mọi hồ sơ hoặc dữ liệu thô |
| READ_VERIFICATION_RESULT | Xem kết quả kiểm tra và yêu cầu còn thiếu | Đọc bí mật dùng để xác minh |
| VIEW_RESTRICTED_EVIDENCE | Xem loại bằng chứng được cấp riêng | Tải hàng loạt hoặc chia sẻ ra ngoài |
| REQUEST_RECOVERY_REVIEW | Gửi đề nghị xem xét theo quy trình | Tự phê duyệt đề nghị đó |
| APPROVE_SPECIFIC_RECOVERY_ACTION | Phê duyệt thao tác xác định nếu đủ điều kiện | Bỏ qua bằng chứng hoặc sửa mọi credential |
| SEND_APPROVED_NOTIFICATION | Gửi mẫu thông báo qua kênh được phép | Tự đổi người nhận hoặc đọc token trong thông báo |

Quyền phê duyệt cũng phải gắn với phạm vi cụ thể. Phê duyệt đặt lại mật khẩu không đồng nghĩa cho phép xóa MFA, thêm passkey mới hoặc thay email phục hồi.

OWASP khuyến nghị áp dụng đặc quyền tối thiểu, từ chối mặc định và kiểm tra quyền trên từng request. Các nguyên tắc này áp dụng cả cho ứng dụng nội bộ đã yêu cầu nhân viên đăng nhập. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

### 3.1. Đăng nhập đúng vẫn có thể truy cập sai

Nhân viên đang có phiên hợp lệ không có nghĩa họ được xem mọi tài khoản. Backend cần xét thêm quan hệ với hồ sơ:

~~~text
cho phép thao tác khi:
    tài khoản nhân viên còn hoạt động
    + phiên làm việc đáp ứng yêu cầu hiện tại
    + đúng tổ chức hoặc tenant
    + hồ sơ nằm trong phạm vi được phân công
    + permission phù hợp với thao tác và loại dữ liệu
    + quyền cấp thêm còn hiệu lực, nếu cần
    + trạng thái hồ sơ cho phép thao tác
~~~

Biết caseId hoặc thay một ID trong URL không được làm mở được hồ sơ khác. Tương tự, quyền xem một loại hồ sơ không tự mở quyền xem tất cả hồ sơ cùng loại.

## 4. Nhân viên thực sự cần thấy dữ liệu nào?

Bắt đầu bằng mục đích công việc và giảm dữ liệu theo từng màn hình.

| Dữ liệu | Mức hiển thị mặc định gợi ý | Khi cần xem thêm |
| --- | --- | --- |
| Trạng thái hồ sơ | Được xem trong hồ sơ được giao | Không cần mở rộng dữ liệu cá nhân |
| Bước tiếp theo | Hướng dẫn nghiệp vụ đã được phép | Chỉ hiển thị phương án thực sự khả dụng |
| Kênh liên hệ | Trạng thái hoặc nhãn đã che phù hợp | Có quyền riêng nếu cần thao tác đặc biệt |
| Kết quả xác minh | Đạt, chưa đạt, cần xem xét và phạm vi bằng chứng | Nhân viên chuyên trách có thể xem phần căn cứ cần thiết |
| Ảnh giấy tờ hoặc video xác minh | Không hiện trong màn hình hỗ trợ thông thường | Quy trình bằng chứng hạn chế, đúng mục đích |
| Lịch sử thiết bị và vị trí | Tóm tắt phục vụ xử lý | Nhóm điều tra được phân quyền khi cần |
| Điểm và lý do rủi ro | Lý do nghiệp vụ phù hợp | Chi tiết phát hiện chỉ cho nhóm có nhiệm vụ tương ứng |
| OTP, recovery code, reset token, session token | Không hiển thị cho nhân viên hỗ trợ | Không dùng nút mở khóa để tiết lộ bí mật |

Giá trị đã che vẫn có thể là dữ liệu cá nhân. Một phần email, vài số cuối điện thoại và thời điểm đăng nhập có thể giúp nhận diện hoặc suy ra thông tin khi ghép với dữ liệu khác.

Không hỏi “bạn hãy đọc bốn số cuối đang hiển thị trên hồ sơ” rồi coi đó là xác minh mạnh. Nếu nhân viên vừa tiết lộ giá trị đó, người yêu cầu chỉ đang lặp lại dữ liệu đã được cung cấp.

### 4.1. Giữ bí mật xác thực ngoài quy trình trao đổi với nhân viên

Người dùng nên nhập OTP hoặc recovery code vào giao diện xác minh chính thức do server kiểm tra. Nhân viên chỉ thấy kết quả và phạm vi bằng chứng, không cần nghe hoặc đọc bí mật đó.

Không yêu cầu người dùng gửi:

- Mật khẩu hiện tại hoặc mật khẩu mới.
- Seed TOTP, mã QR dùng để đăng ký authenticator hoặc toàn bộ bộ recovery code.
- Khóa riêng passkey, mã PIN mở khóa thiết bị hoặc dữ liệu sinh trắc.
- Cookie, access token, refresh token hoặc liên kết reset còn hiệu lực.

Nếu người dùng tự gửi bí mật vào chat, không trích dẫn hoặc chuyển tiếp lại để “xác nhận”. Áp dụng quy trình xử lý dữ liệu bị lộ, hạn chế quyền xem và thu hồi hoặc thay thế bí mật khi phù hợp. Xóa một tin nhắn hiển thị không bảo đảm dữ liệu đã biến mất khỏi mọi bản sao.

## 5. Giảm dữ liệu ngay từ backend

Che bằng CSS hoặc ẩn một trường trên giao diện không tạo ra ranh giới bảo mật nếu API vẫn trả đầy đủ giá trị.

Một thiết kế phù hợp có thể tách:

~~~mermaid
flowchart LR
    A[Nhân viên hỗ trợ] --> B[API kiểm tra quyền theo hồ sơ]
    B --> C[Truy vấn dữ liệu tóm tắt]
    C --> D[DTO tối thiểu cho hỗ trợ]
    B --> E[Kho bằng chứng hạn chế]
    E --> F[Luồng xem chuyên trách có cấp quyền riêng]
    B --> G[Dấu vết truy cập]
~~~

Màn hình hỗ trợ thông thường không cần nhận đối tượng tài khoản đầy đủ rồi tự chọn trường hiển thị. Repository hoặc lớp truy vấn nên lấy đúng projection cần thiết.

Ví dụ response tối thiểu:

~~~json
{
  "caseRef": "case-example",
  "status": "WAITING_FOR_ADDITIONAL_PROOF",
  "verificationState": "REQUIRED_PROOF_NOT_COMPLETE",
  "nextStepKey": "recovery.choose.approved.method.or.support",
  "policyVersion": "support-recovery-v3"
}
~~~

Không đưa vào response này ảnh giấy tờ, thông tin nhà mạng thô hoặc resetUrl có token.

Một số thao tác thậm chí không cần tiết lộ địa chỉ đích. Ví dụ, backend có thể gửi thông báo qua kênh đủ điều kiện đang được liên kết với hồ sơ, trong khi nhân viên chỉ nhận kết quả đã tiếp nhận lệnh gửi.

### 5.1. Bảo vệ cả những nơi dữ liệu dễ bị bỏ quên

Quyền và giới hạn dữ liệu cần áp dụng cho:

- Endpoint xem một hồ sơ, tìm kiếm, phân trang và autocomplete.
- Endpoint tải file, ảnh preview và tài nguyên tĩnh.
- Export, in, clipboard và attachment của ticket.
- Cache, thông báo trên trình duyệt và dữ liệu lưu cục bộ.
- Công cụ theo dõi lỗi, analytics, session replay và dịch vụ bên thứ ba.

Mã tham chiếu khó đoán hỗ trợ giảm việc dò tìm nhưng không thay thế phân quyền. URL tải file ngắn hạn có thể là một bearer capability; người có URL vẫn có thể dùng nó trong thời gian hiệu lực nếu hệ thống không kiểm tra thêm. Không đặt URL như vậy vào log hoặc hội thoại chung.

Các biện pháp hạn chế sao chép và watermark giúp giảm rủi ro, nhưng không thể bảo đảm một người đã nhìn thấy dữ liệu không chụp lại bằng thiết bị khác. Do đó, giảm dữ liệu được cấp vẫn là lớp bảo vệ quan trọng.

## 6. Ví dụ Java: dịch vụ chỉ trả bản tóm tắt

Đoạn mã dưới đây minh họa một đường đọc dữ liệu hỗ trợ. Nó không thay đổi tài khoản, không xác minh danh tính và không triển khai đầy đủ hệ thống cấp quyền. Record yêu cầu Java 16 trở lên.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class SupportCasePrivacy {
    public enum Permission {
        READ_CASE_SUMMARY
    }

    public record AgentSession(
            UUID agentId,
            String tenantId) {
        public AgentSession {
            Objects.requireNonNull(agentId);
            Objects.requireNonNull(tenantId);
        }
    }

    public record SummaryView(
            UUID caseId,
            String status,
            String verificationState,
            String nextStepKey) {}

    public interface Authorization {
        // Checks current employment, session, tenant, assignment and policy.
        void require(
                AgentSession session,
                UUID caseId,
                Permission permission,
                Instant now);
    }

    public interface SummaryRepository {
        // Returns only summary fields; the query is scoped by tenant.
        SummaryView findAuthorizedSummary(
                String tenantId,
                UUID caseId);
    }

    public interface Audit {
        // Must not include credentials, OTPs or raw identity evidence.
        void summaryRead(
                UUID agentId,
                UUID caseId,
                Instant at);
    }

    private final Authorization authorization;
    private final SummaryRepository summaries;
    private final Audit audit;

    public SupportCasePrivacy(
            Authorization authorization,
            SummaryRepository summaries,
            Audit audit) {
        this.authorization = Objects.requireNonNull(authorization);
        this.summaries = Objects.requireNonNull(summaries);
        this.audit = Objects.requireNonNull(audit);
    }

    public SummaryView readSummary(
            AgentSession session,
            UUID caseId,
            Instant now) {
        Objects.requireNonNull(session);
        Objects.requireNonNull(caseId);
        Objects.requireNonNull(now);

        authorization.require(
                session, caseId, Permission.READ_CASE_SUMMARY, now);

        SummaryView view = summaries.findAuthorizedSummary(
                session.tenantId(), caseId);

        audit.summaryRead(session.agentId(), caseId, now);
        return view;
    }
}
~~~

AgentSession phải được tạo từ ngữ cảnh xác thực phía máy chủ, không nhận agentId hoặc tenantId từ body rồi coi là đã được xác thực. now cũng lấy từ đồng hồ phía server.

Tên findAuthorizedSummary không tự bảo đảm truy vấn có kiểm soát. Implementation phải thực thi phạm vi tenant và trả đúng hồ sơ. Khi cần bảo vệ khỏi thay đổi phân công giữa kiểm tra quyền và đọc dữ liệu, ràng buộc điều kiện phân quyền vào truy vấn hoặc dùng transaction và revision phù hợp.

Authorization.require phải kiểm tra trạng thái hiện tại. Một session chứa permission cũ không được giữ nguyên khả năng đọc sau khi nhân viên bị thu hồi quyền hoặc hồ sơ đã chuyển cho nhóm khác.

Audit trong ví dụ chạy trước khi trả dữ liệu, nhưng cách xử lý lỗi ghi audit cần được xác định rõ theo yêu cầu của hệ thống. Không bắt mọi exception rồi vẫn trả dữ liệu nhạy cảm. Với luồng bắt buộc ghi nhận truy cập trước khi tiết lộ, cần cơ chế ghi nhận bền vững hoặc từ chối an toàn theo chính sách.

Ví dụ không có permission xem bí mật hoặc thay credential. Các thao tác đó phải có contract và đường kiểm tra riêng, không thêm trường nhạy cảm vào SummaryView để tiện dùng chung.

## 7. Cấp quyền bổ sung theo nhu cầu thực tế

Một số hồ sơ cần nhân viên chuyên trách xem thêm bằng chứng. Quyền mở rộng nên gắn với tài nguyên, loại dữ liệu, mục đích và thời hạn cụ thể.

Ví dụ một grant nội bộ:

~~~text
grantId
agentId
caseId
allowedDataClass
allowedAction
purposeCode
approvedBy
issuedAt
expiresAt
assignmentRevision
~~~

Trước mỗi lần truy cập, kiểm tra grant còn hiệu lực, đúng người, đúng hồ sơ và đúng thao tác. Một grant xem ảnh bằng chứng không cho phép export mọi hồ sơ hoặc thay email.

### 7.1. Có phê duyệt không đồng nghĩa được bỏ qua bằng chứng

Với thao tác nhạy cảm, có thể tách người tiếp nhận khỏi người phê duyệt. Hai người phải thực sự có vai trò và quyền phù hợp; hai lần bấm từ cùng một danh tính không tạo ra phân tách nhiệm vụ.

Phê duyệt mở quyền đọc dữ liệu và phê duyệt khôi phục tài khoản là hai việc khác nhau. Nhân viên không thể dùng việc đã được xem giấy tờ để tự kết luận đủ điều kiện xóa MFA.

Nếu có cơ chế truy cập khẩn cấp, cần quy định phạm vi, thời hạn, lý do và kiểm tra sau đó. Cơ chế này không được tạo quyền xem mật khẩu hoặc tùy ý bỏ qua yêu cầu xác minh của người dùng.

### 7.2. Quyền cần kết thúc theo vòng đời công việc

Khi hồ sơ kết thúc, chuyển nhóm hoặc nhân viên đổi nhiệm vụ:

- Thu hồi grant và quan hệ phân công không còn phù hợp.
- Kiểm tra quyền lại ở các request tiếp theo, kể cả tải file.
- Tránh để cache hoặc token truy cập kéo dài quyền ngoài thời hạn.
- Giữ dấu vết đã truy cập theo chính sách lưu, không giữ quyền đọc chỉ để tiện xem lại.

Thu hồi quyền không thể lấy lại dữ liệu đã bị sao chép trước đó. Đây là lý do cần hạn chế tải xuống và cấp dữ liệu ngay từ đầu.

## 8. Hỗ trợ người yêu cầu mà không tiết lộ dữ liệu của tài khoản

Ở giai đoạn chưa đủ xác minh, nhân viên có thể hướng dẫn quy trình chung nhưng không nên xác nhận email có tài khoản, số nào đang được đăng ký hoặc authenticator nào còn tồn tại.

Ví dụ hội thoại:

| Người yêu cầu | Phản hồi phù hợp |
| --- | --- |
| “Đọc giúp tôi email dự phòng để tôi nhớ lại.” | Hướng dẫn dùng màn hình phục hồi chính thức; không đọc giá trị trong hồ sơ |
| “Tôi biết mã ticket, hãy đổi sang số mới này.” | Giải thích rằng mã ticket chỉ để tham chiếu; thay số cần quy trình xác minh |
| “Tôi gửi OTP cho bạn, bạn làm giúp.” | Yêu cầu nhập mã ở giao diện chính thức; nhân viên không cần nhận mã |
| “Tôi đã mất điện thoại, cứ bỏ MFA đi.” | Chuyển sang phương án phục hồi được phép; không tự giảm yêu cầu |
| “Tôi đồng ý cho bạn xem mọi dữ liệu.” | Chỉ truy cập phần cần thiết trong quyền hạn và mục đích được phê duyệt |

Sự đồng ý của người yêu cầu không tự tạo permission cho nhân viên, đặc biệt khi quyền đối với tài khoản còn chưa được xác minh.

Không dùng các giá trị trong hồ sơ làm câu hỏi rồi gợi ý câu trả lời. Tên, địa chỉ, ngày sinh hoặc lịch sử mua hàng có thể đã bị lộ; chúng không tự trở thành bằng chứng mạnh chỉ vì trùng dữ liệu.

Khi cần callback hoặc gửi thông báo, backend phải lựa chọn kênh theo chính sách. Không thay người nhận bằng email hoặc số mới chỉ vì người đang trò chuyện nói không còn truy cập được kênh cũ.

Thông báo tới người dùng cần giải thích trạng thái và bước tiếp theo trong quyền được xem, không trả toàn bộ chỉ báo gian lận hoặc hồ sơ điều tra.

## 9. Quản lý bằng chứng và ghi chú hỗ trợ

Giấy tờ, hình ảnh hoặc bản ghi cuộc gọi có thể chứa nhiều thông tin hơn mục tiêu phục hồi. Trước khi thu thập, cần xác định phương thức đó thực sự được hỗ trợ và cần những dữ liệu nào.

Một quy trình quản lý bằng chứng có thể gồm:

1. Người dùng tải lên qua kênh chính thức của hồ sơ.
2. Dữ liệu đi vào kho hạn chế, có kiểm tra an toàn file phù hợp.
3. Hệ thống hoặc người có nhiệm vụ xác minh đánh giá phần cần thiết.
4. Nhân viên hỗ trợ thông thường nhận kết quả và yêu cầu tiếp theo.
5. Bằng chứng được lưu hoặc xóa theo chính sách của từng loại dữ liệu.

Không yêu cầu gửi giấy tờ qua email cá nhân của nhân viên. Không tải về thư mục chung để “đồng nghiệp xem hộ”. Một attachment trong hệ thống ticket có thể có tập người xem lớn hơn kho xác minh.

### 9.1. Ghi chú phải ghi việc đã làm, không chép dữ liệu thô

Ghi chú phù hợp:

~~~text
Đã hướng dẫn người yêu cầu thực hiện bước xác minh tại giao diện chính thức.
Hệ thống ghi nhận bằng chứng chưa đủ cho thao tác thay MFA.
Đã chuyển hồ sơ tới nhóm xem xét theo quy trình.
~~~

Ghi chú không phù hợp:

~~~text
Mật khẩu mới của khách là ...
Recovery code khách đọc qua điện thoại là ...
Đã chép toàn bộ số giấy tờ và thông tin gia đình để dùng cho lần sau.
~~~

Không ghi kết luận “đã xác minh danh tính” khi mới chỉ xác minh khả năng truy cập email. Ghi rõ loại kiểm tra, kết quả và phạm vi được công nhận để nhóm sau không sử dụng quá mức.

Nội dung do người dùng nhập, tên file và ghi chú cần được xử lý như dữ liệu không tin cậy khi hiển thị. Không để attachment hoặc nội dung chat thực thi mã trong giao diện hỗ trợ.

## 10. Audit đủ dùng mà không tạo một kho rò rỉ mới

Bản ghi truy cập nên trả lời được ai xem gì, theo hồ sơ nào, lúc nào và dựa trên quyền nào.

~~~text
eventId
agentRef
caseRef
tenantRef
action
dataClass
purposeCode
grantRef
policyVersion
decision
occurredAt
~~~

Với hành động bị từ chối, ghi mã lý do phù hợp mà không trả chi tiết đó cho người không có quyền. Với mở quyền đặc biệt, cần liên kết được đề nghị, phê duyệt và lần truy cập thực tế.

OWASP khuyến nghị hạn chế ghi trực tiếp mật khẩu, access token và session identifier, đồng thời bảo vệ và giới hạn quyền đọc log. Audit cũng có thể chứa dữ liệu nhạy cảm nên cần có ranh giới riêng. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

Các biện pháp vận hành có thể gồm:

- Phát hiện nhân viên mở nhiều hồ sơ không liên quan đến phân công.
- Theo dõi export, truy cập bằng chứng và thay đổi quyền bất thường.
- Bảo vệ tính toàn vẹn của log và kiểm soát quyền đọc dữ liệu audit.
- Dùng định danh tham chiếu khi đủ, thay vì đưa email hoặc số giấy tờ vào mọi sự kiện.
- Không ghi toàn bộ request hoặc response của luồng xác minh vào log chung.
- Theo dõi việc dữ liệu bị sao chép sang công cụ analytics hoặc hệ thống hỗ trợ khác.

Một chuỗi hash hoặc chữ ký không tự chứng minh toàn bộ hành vi ngoài hệ thống. Nó chỉ hỗ trợ bảo vệ hoặc kiểm tra phần dữ liệu đã được ghi theo thiết kế.

## 11. Thời hạn lưu và quyền riêng tư của cả hai phía

Hồ sơ hỗ trợ, bằng chứng xác minh, audit và bản ghi cuộc gọi có thể có mục đích và thời hạn lưu khác nhau. Không giữ tất cả vô thời hạn chỉ vì một hồ sơ từng cần kiểm tra.

Cần quy định thời hạn cho cả bản chính, attachment, export, cache, bản sao trong ticket và backup. Xóa ở một giao diện không tự xóa mọi bản sao. Quy trình khôi phục từ backup cũng cần xử lý các yêu cầu xóa hoặc hạn chế sử dụng đã được ghi nhận theo chính sách.

NIST SP 800-63B-4 trình bày việc đánh giá rủi ro quyền riêng tư đối với lưu giữ hồ sơ và rủi ro của việc dùng thuộc tính cho mục đích ngoài mục đích thu thập. Điều này hỗ trợ thiết kế dữ liệu phục hồi theo mục đích cụ thể và khả năng kiểm soát việc sử dụng. [NIST SP 800-63B-4, Privacy Considerations](https://pages.nist.gov/800-63-4/sp800-63b.html)

Không tái sử dụng bằng chứng phục hồi cho tiếp thị, huấn luyện công cụ hoặc phân tích ngoài mục đích được xác định mà không qua quy trình đánh giá phù hợp.

Đối với nhân viên, tương tác nên đi qua danh tính công việc và kênh hỗ trợ chính thức. Không yêu cầu họ dùng số cá nhân, tài khoản mạng xã hội hoặc email riêng để liên hệ khách hàng. Cách hiển thị tên hoặc mã nhân viên cho người dùng cần phù hợp quy trình công việc, trong khi nội bộ vẫn truy xuất được đúng người thực hiện.

Việc giám sát nhân viên cũng cần mục đích và phạm vi rõ ràng. Ghi nhận truy cập phục vụ bảo vệ hồ sơ không có nghĩa thu thập mọi hoạt động cá nhân ngoài công việc.

## 12. Những lỗi thường làm mất ranh giới quyền riêng tư

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Mọi nhân viên hỗ trợ xem được mọi tài khoản | Tăng nguy cơ truy cập sai mục đích | Ràng buộc tenant, phân công và thao tác |
| Chỉ che trên giao diện | Dữ liệu thô vẫn có trong response | Trả projection tối thiểu từ backend |
| Nhân viên xem hoặc nhận OTP | Có thêm người và nơi giữ bí mật | Xác minh qua kênh chính thức, chỉ hiện kết quả |
| Mã ticket được coi là bằng chứng sở hữu | Người biết mã có thể chiếm quyền | Tách tham chiếu hồ sơ khỏi xác minh |
| Quyền xem bằng chứng kéo theo quyền reset MFA | Mở rộng quyền ngoài mục đích | Tách đọc, đề nghị, duyệt và thực thi |
| Grant không hết hạn | Dữ liệu tiếp tục bị truy cập sau khi nhiệm vụ kết thúc | Quyền có thời hạn và thu hồi theo vòng đời |
| Ghi toàn bộ dữ liệu vào chat hoặc log | Tạo nhiều bản sao nhạy cảm | Ghi tham chiếu và kết quả cần thiết |
| Quy trình khẩn cấp bỏ qua mọi kiểm tra | Trở thành cửa hậu của recovery | Giới hạn phạm vi và giữ cổng bằng chứng |
| Chỉ bảo vệ API hồ sơ chính | File, search hoặc export làm lộ dữ liệu | Áp dụng quyền cho toàn bộ đường truy cập |
| Dùng kênh cá nhân của nhân viên | Mất kiểm soát và ảnh hưởng riêng tư hai phía | Duy trì kênh công việc chính thức |

Nhân viên hỗ trợ cần đủ thông tin để hướng dẫn và xử lý hồ sơ, với quyền gắn vào nhiệm vụ cụ thể. Luồng khôi phục an toàn giữ riêng bí mật xác thực, giới hạn dữ liệu được cấp và kiểm tra lại quyền trước mỗi lần đọc hoặc thực hiện thay đổi nhạy cảm.
