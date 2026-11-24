# Thông báo enrollment trong quản lý vòng đời danh tính IAM

## 1. Thông báo enrollment là gì?

Trong **Identity and Access Management (IAM)**, **enrollment** là quá trình một chủ thể được ghi danh vào hệ thống danh tính, liên kết hồ sơ với tài khoản và đăng ký những thành phần cần thiết để sử dụng hệ thống: phương thức xác thực, MFA/passkey, thiết bị hoặc những bước xác minh còn thiếu. **Thông báo enrollment** là thông điệp gửi cho người đăng ký, người bảo trợ, quản trị viên hay hệ thống liên quan khi quy trình phát sinh sự kiện cần biết hoặc cần hành động.

Ví dụ, trước ngày làm việc đầu tiên, nhân viên có thể nhận lời mời kích hoạt qua kênh liên hệ được kiểm tra. Sau khi mở cổng chính thức, người đó hoàn thành bước xác minh, đăng ký MFA và nhận xác nhận. Khi lời mời hết hạn, bị thu hồi hoặc phát sinh lỗi, hệ thống tiếp tục thông báo để các bên biết cách xử lý.

Thông báo không chỉ là email giới thiệu. Nó còn giúp **đưa đúng yêu cầu tới đúng chủ thể, hạn chế enrollment trái phép, theo dõi tiến độ và tạo bằng chứng kiểm toán**.

Bài này thuộc chương **Identity enrollment** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, trong phạm vi quản lý vòng đời theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính và cấp quyền đến rà soát, thay đổi vai trò và thu hồi. Do đó, thông báo cần nhất quán với **HRIS, IAM/IGA, IdP, SSO, SCIM, RBAC/ABAC, hệ thống kiểm toán và các tài khoản phi con người**.

### Cần phân biệt các trạng thái

| Hoạt động | Kết quả nó xác nhận | Điều không thể tự suy ra |
|---|---|---|
| **Invitation issued** | Một lời mời hợp lệ đã được phát hành | Người được mời đã nhận hoặc đọc |
| **Notification dispatched** | Đã chuyển yêu cầu đến nhà cung cấp email/SMS/push | Người nhận đã mở hoặc chấp nhận |
| **Invitation accepted** | Một thao tác sử dụng lời mời đã được hệ thống tiếp nhận | Người sử dụng đúng danh tính pháp lý đã khai |
| **Identity proofing completed** | Đã xác minh danh tính theo chính sách tương ứng | Người đó đã có toàn bộ quyền ứng dụng |
| **Authenticator enrolled** | Phương thức xác thực đã đăng ký theo quy định | Ứng dụng đích đã cấp quyền |
| **Provisioning confirmed** | Hệ thống đích xác nhận trạng thái tài khoản/quyền | Các phiên/quyền cũ khác đã được thu hồi |
| **Account activated** | Trạng thái tài khoản cho phép hoạt động theo chính sách | Chủ thể được làm mọi thao tác nghiệp vụ |

**Đã gửi thư mời không đồng nghĩa enrollment hoàn tất; enrollment hoàn tất không tự động đồng nghĩa đã cấp quyền hợp lệ.**

## 2. Mục đích của thông báo theo từng giai đoạn

Thông báo cần phục vụ một mục tiêu rõ ràng trong quy trình:

1. **Thông báo khởi tạo:** cho chủ thể biết tổ chức đã chuẩn bị một quy trình enrollment hợp lệ, vì sao và để làm gì.
2. **Mời hành động:** hướng dẫn truy cập cổng danh tính, xác minh hoặc đăng ký authenticator bằng kênh an toàn.
3. **Thông báo chờ điều kiện:** cho biết hồ sơ đang thiếu tài liệu, chờ phê duyệt, chờ đồng bộ hoặc cần sự hỗ trợ của bộ phận quản lý.
4. **Nhắc trước hạn:** tránh ảnh hưởng ngày gia nhập hoặc thời hạn truy cập, có giới hạn tần suất.
5. **Xác nhận kết quả:** chỉ nói hoàn tất những bước hệ thống thực sự đã kiểm chứng.
6. **Báo lỗi/hết hạn/thu hồi:** giải thích cách xử lý an toàn, không tiếp tục sử dụng lời mời không hợp lệ.
7. **Cảnh báo bảo mật:** giúp phát hiện lời mời bất ngờ, liên kết sai người, yêu cầu enrollment đáng ngờ hoặc hành vi gian lận.
8. **Gửi sự kiện máy–máy:** đồng bộ trạng thái cho IAM orchestrator, IdP, ticket system và công cụ kiểm toán.

Có thể có những bước **không cần thông báo trực tiếp cho người dùng**, chẳng hạn một kết quả retry SCIM nội bộ chưa ảnh hưởng thao tác của họ. Ngược lại, thay đổi authenticator hoặc lời mời bất ngờ thường cần thông báo dễ nhận ra để chủ tài khoản tự phát hiện.

## 3. Ai là người nhận thông báo?

| Người nhận | Cần biết | Không nên nhận |
|---|---|---|
| **Người được enrollment** | Mục đích, cách thực hiện, thời hạn, trạng thái và kênh hỗ trợ | Mật khẩu, recovery code, khóa bí mật và dữ liệu của người khác |
| **HR/người bảo trợ** | Nhân viên đã đủ điều kiện bắt đầu hay chưa; lỗi cần HR xử lý | Token kích hoạt có thể dùng thay nhân viên |
| **Manager** | Những việc bị chậm ảnh hưởng tới công việc hoặc phê duyệt của nhóm | Bản sao chứng từ định danh hoặc bí mật xác thực |
| **IT/helpdesk** | Mã yêu cầu, bước gặp lỗi, trạng thái gửi/đăng ký, thao tác khắc phục được phép | Toàn bộ dữ liệu cá nhân nếu không cần |
| **Chủ ứng dụng/chủ quyền** | Quyền nhạy cảm cần duyệt, điều kiện cấp quyền, kết quả liên quan | Liên kết enrollment riêng của user |
| **Security/SOC** | Dấu hiệu truy cập trái phép, gửi nhầm, lạm dụng lời mời | Thư chứa credential thô |
| **Hệ thống orchestration** | Event có cấu trúc, ID tương quan và trạng thái được tin cậy | Bản sao tràn lan của PII/bí mật |

Một mẫu email gửi cho **người mới gia nhập** không nên được chuyển tiếp nguyên trạng đến **manager**. Người quản lý có thể nhận trạng thái “chưa hoàn thành MFA trước ngày bắt đầu” nhưng không được sử dụng lời mời thay chủ thể.

Với **thiết bị, service account, bot và workload identity**, người nhận thường là **owner kỹ thuật** hoặc hệ thống điều phối. Không có lý do gửi private key hay secret của workload qua email chỉ vì nó được gọi là enrollment.

## 4. Những loại thông báo và điều kiện kích hoạt

| Loại thông báo | Sự kiện sinh ra | Hành động mong đợi |
|---|---|---|
| **Enrollment invitation** | Đã kiểm tra điều kiện và tạo lời mời | Người dùng truy cập cổng chính thức |
| **Proofing action required** | Thiếu bước xác minh danh tính được yêu cầu | Hoàn tất hoặc được hỗ trợ theo quy trình |
| **Authenticator setup required** | Chưa đăng ký MFA/passkey bắt buộc | Đăng ký phương thức qua IdP |
| **Pending approval** | Quyền hoặc enrollment chờ người có thẩm quyền | Người duyệt đánh giá yêu cầu |
| **Reminder** | Chưa hoàn tất và đến mốc nhắc | Tiếp tục quy trình còn hợp lệ |
| **Delivery failure** | Địa chỉ/kênh không nhận được | HR/helpdesk kiểm tra thông tin liên hệ |
| **Enrollment completed** | Các bước enrollment theo chính sách đã đạt | Người dùng biết bước tiếp theo |
| **Activation confirmed** | Đã kiểm tra trạng thái cho phép truy cập đúng phạm vi | Người dùng truy cập ứng dụng qua cổng chính thức |
| **Invitation expiring/expired** | Sắp hết hạn hoặc hết hạn | Hoàn tất trước hạn hoặc yêu cầu cấp lại |
| **Invitation revoked/canceled** | Lời mời bị hủy do thay đổi nguồn hoặc rủi ro | Không dùng lời mời cũ |
| **Suspicious enrollment alert** | Có tín hiệu bất thường | Xác minh qua kênh độc lập, xử lý an ninh |
| **Deprovisioning exception** | Lỗi thu hồi liên quan tới Leaver | Chủ hệ thống/IAM xử lý quyền còn tồn dư |

Cần định nghĩa **điều kiện phát** dưới dạng trạng thái được xác minh. Ví dụ, IAM đã tạo tài khoản trong IdP nhưng MFA bắt buộc chưa enroll thì thông báo đúng là **“cần hoàn tất bước bảo vệ tài khoản”**; không phải **“tài khoản đã sẵn sàng với mọi quyền”**.

## 5. Luồng thông báo điển hình cho Joiner

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM / IGA
    participant N as Notification Service
    participant U as Người dùng
    participant P as IdP / Proofing
    participant A as Ứng dụng đích
    H->>I: Joiner event + personId + effectiveAt
    I->>I: Kiểm tra nguồn, định danh và kênh liên hệ
    I->>N: InvitationIssued(enrollmentId)
    N-->>U: Gửi lời mời đến kênh đã được kiểm tra
    N-->>I: Trạng thái gửi
    U->>P: Mở cổng chính thức, thực hiện enrollment
    P-->>I: Proofing + authenticator enrollment result
    I->>A: Provisioning theo chính sách RBAC/ABAC
    A-->>I: Quyền thực tế / lỗi
    I->>N: Completed hoặc ActionRequired
    N-->>U: Thông báo đúng trạng thái
~~~

Đây là luồng tham khảo. Trong một hệ thống thực tế, **tài khoản IdP có thể đã được tạo trước ngày bắt đầu**, nhưng bị giới hạn quyền hoặc chưa được kích hoạt. Việc provisioning đến ứng dụng có thể bất đồng bộ, và không có giao dịch nguyên tử xuyên mọi hệ thống đích.

**Mốc cần theo dõi riêng:** sự kiện HRIS hợp lệ, điều kiện enrollment đạt, lời mời phát hành, thông báo đã gửi, kết quả giao nhận, lời mời được sử dụng, proofing/MFA hoàn tất, trạng thái tài khoản kích hoạt và quyền được xác nhận ở ứng dụng đích.

### Phân biệt thông báo và hành động thật

Nếu email gửi thất bại nhưng user đã vào cổng hợp lệ và hoàn tất enrollment, hệ thống phải phản ánh **enrollment completed** dù một delivery attempt lỗi. Ngược lại, nếu email báo gửi thành công nhưng chưa có hành động đăng ký, trạng thái vẫn là **pending**. Tránh dùng thuộc tính opened/clicked của email làm bằng chứng danh tính hay căn cứ cấp quyền.

## 6. Cấu trúc nội dung thông báo rõ ràng và an toàn

Một thông báo tốt phải trả lời: **Ai gửi? Vì sao tôi nhận được? Tôi cần làm gì? Bao giờ hết hạn? Nếu có vấn đề thì liên hệ ở đâu?**

| Thành phần | Khuyến nghị |
|---|---|
| Đơn vị phát hành | Tên tổ chức/dịch vụ và kênh đã công bố chính thức |
| Mục đích | Nói rõ đăng ký tài khoản, MFA, thiết bị hay hoàn tất xác minh |
| Bối cảnh | Nêu đủ để người nhận nhận ra yêu cầu; tránh lộ bộ phận/đặc quyền nhạy cảm nếu chưa xác minh kênh |
| Hành động | Dẫn tới cổng danh tính chính thức hoặc hướng dẫn nhập mã theo quy trình |
| Thời hạn | Ghi thời gian cụ thể và múi giờ |
| Tham chiếu | Request/enrollment ID không bí mật để tra cứu |
| Chống phishing | Hướng dẫn không chia sẻ mã/password và cách kiểm chứng độc lập |
| Hỗ trợ | Kênh helpdesk được công bố độc lập với thư mời |

### Mẫu mời enrollment

> **Chủ đề:** Hoàn tất đăng ký tài khoản làm việc
>
> Chào bạn,
>
> Tổ chức đã tạo yêu cầu đăng ký tài khoản làm việc gắn với hồ sơ của bạn. Vui lòng truy cập cổng danh tính chính thức của tổ chức để thực hiện các bước được hiển thị, gồm xác minh cần thiết và đăng ký phương thức xác thực.
>
> Hạn hoàn tất: **17:00 ngày 30/11/2026 (GMT+7)**.
>
> Nếu bạn không mong đợi yêu cầu này, hãy liên hệ bộ phận hỗ trợ CNTT theo kênh chính thức. Không chia sẻ mật khẩu, mã xác minh, mã khôi phục hoặc liên kết kích hoạt.
>
> **Mã tham chiếu:** ENR-1042.

Mẫu minh họa **không tự tạo một URL cụ thể**. Trong triển khai thật, URL/cổng cần được cấu hình, phê duyệt và kiểm tra trước khi gửi. Có thể cho người dùng vào cổng bằng địa chỉ đã biết rồi xem lời mời, giảm việc phụ thuộc vào link lạ trong email.

### Mẫu nhắc hoàn tất MFA

> **Chủ đề:** Cần hoàn tất bước bảo vệ tài khoản
>
> Quy trình ghi danh của bạn đang chờ đăng ký phương thức xác thực bắt buộc. Vui lòng vào cổng danh tính chính thức để kiểm tra trạng thái và hoàn tất bước còn thiếu. Tài khoản có thể bị hạn chế truy cập cho đến khi đáp ứng chính sách.
>
> Nếu bạn đã thực hiện hoặc không nhận ra yêu cầu, hãy kiểm tra trực tiếp trên cổng và liên hệ hỗ trợ theo kênh đã công bố.

Nội dung **không gửi OTP, recovery code, mật khẩu khởi tạo hoặc bí mật của authenticator**. Với dữ liệu nhạy cảm, thông báo nên cung cấp cách đăng nhập vào cổng an toàn để xem trạng thái chi tiết, thay vì nhồi thông tin vào email.

## 7. Chọn kênh gửi và xác minh người nhận

| Kênh | Phù hợp | Giới hạn |
|---|---|---|
| **Email đã xác minh** | Lời mời, hướng dẫn, nhắc và xác nhận | Email có thể bị chuyển tiếp, lộ, lọc spam hoặc bị quét link |
| **SMS** | Nhắc ngắn hoặc kênh bổ sung theo chính sách | SIM swap, đổi số, mất thiết bị, không bảo đảm danh tính pháp lý |
| **Portal có xác thực** | Trạng thái chi tiết và thao tác nhạy cảm | Joiner có thể chưa có account để truy cập |
| **Push** | Thông báo trên thiết bị đã liên kết đáng tin cậy | Cần bảo đảm ràng buộc đúng user/thiết bị |
| **Helpdesk/HR** | Ngoại lệ, hỗ trợ người chưa có kênh điện tử | Cần xác minh danh tính trước khi cấp lại lời mời |
| **Ticket/webhook/event bus** | Điều phối hệ thống, audit, chủ ứng dụng | Cần bảo vệ API, chống phát lại và kiểm soát quyền |

### Joiner chưa có email công ty

Một lỗi triển khai phổ biến là gửi lời mời kích hoạt **chỉ tới email doanh nghiệp vốn chưa truy cập được vì tài khoản chưa kích hoạt**. Nguồn HR hoặc đơn vị tiếp nhận phải xác lập **kênh liên hệ ban đầu đã kiểm tra**; với các trường hợp nhạy cảm, có thể yêu cầu tiếp nhận trực tiếp hoặc qua quy trình đã được phê duyệt.

Không nên gửi lời mời nhạy cảm tới địa chỉ cá nhân chỉ vì người dùng tự nhập. Cần đánh giá khả năng địa chỉ đó cũ, bị chuyển giao hoặc thuộc người khác. Việc xác nhận quyền kiểm soát hộp thư chỉ kiểm tra **kênh liên hệ**, không thay thế identity proofing ở mức assurance cần thiết.

### Chọn kênh theo mục đích

Thông báo thường có thể đi qua email/SMS; nhưng thao tác **đăng ký authenticator, chuyển đổi phương thức khôi phục, phát hành credential hoặc cấp quyền đặc quyền** phải qua một luồng được bảo vệ. Nếu người dùng đổi email/điện thoại nhận lời mời, cần xác minh sự thay đổi theo chính sách thay vì cập nhật theo yêu cầu không xác thực.

## 8. Bảo vệ liên kết kích hoạt, mã mời và token

Nhiều hệ thống dùng một **invitation token**. Nếu chỉ cần có token là có thể kích hoạt tài khoản hoặc đăng ký phương thức xác thực, token là một bí mật có khả năng cấp quyền; ai có nó có thể mạo danh trong phạm vi nhất định.

Các kiểm soát cần quan tâm:

1. **Khó đoán:** sinh token bằng bộ sinh số ngẫu nhiên an toàn mật mã với entropy đủ lớn cho mô hình đe dọa; ví dụ token ngẫu nhiên ít nhất 128 bit khi phù hợp.
2. **Phạm vi hẹp:** ràng buộc token với enrollment ID, mục đích, người được mời, thời hạn và trạng thái được phép.
3. **Hạn sử dụng:** token có ngày/giờ hết hiệu lực; cấp mới phải vô hiệu phiên bản cũ theo chính sách.
4. **Dùng một lần khi cần:** redeem thực hiện nguyên tử, chống hai yêu cầu đồng thời cùng kích hoạt.
5. **Lưu an toàn:** không ghi token thô vào log, analytics, ticket hay event bus; có thể lưu giá trị dẫn xuất thích hợp để so sánh, cùng trạng thái phía server.
6. **Tránh rò rỉ qua URL:** ngăn lộ token qua referrer, redirect sang miền ngoài, nhật ký gateway, screenshot, lịch sử và telemetry không cần thiết.
7. **Không kích hoạt qua GET:** hệ thống quét link của email có thể mở URL trước người nhận. Trang có thể hiển thị thông tin tối thiểu khi GET; thao tác đổi trạng thái phải đòi hành động có chủ ý và kiểm tra phù hợp.
8. **Không phụ thuộc duy nhất vào possession của link** nếu rủi ro cao: có thể yêu cầu xác thực, proofing, kiểm tra kênh và/hoặc phiên đã liên kết đúng người.
9. **Thu hồi được:** Leaver, thay đổi thông tin liên hệ, phát hiện gian lận hoặc hủy onboarding phải hủy token còn hiệu lực.
10. **Chống dò và spam:** rate limit, giám sát yêu cầu bất thường, phản hồi lỗi không tiết lộ tài khoản tồn tại hay không.

**Ví dụ:** lời mời bị gửi nhầm cho người khác rồi được gửi lại cho nhân viên thật. Chỉ gửi lần hai chưa đủ; phải **thu hồi lời mời thứ nhất**, kiểm tra xem đã bị sử dụng chưa, đánh giá rủi ro và xử lý theo chính sách.

### Lưu ý về token và quyền

Link mời được dùng để **bắt đầu hoặc tiếp tục enrollment**. Không nên thiết kế nó thành lối tắt cấp quyền quản trị mà bỏ qua proofing, phê duyệt, RBAC/ABAC hoặc điều kiện xác thực. Đặc biệt, việc thay đổi email khôi phục hoặc đăng ký authenticator mới cho tài khoản hiện hữu cần quy trình kiểm chứng riêng.

## 9. Trạng thái enrollment và trạng thái notification là hai đối tượng khác nhau

Một thiết kế dễ kiểm soát nên có **state machine cho enrollment** và **kết quả giao nhận riêng cho từng notification**.

~~~mermaid
stateDiagram-v2
    [*] --> Draft: Tạo yêu cầu
    Draft --> Issued: Đủ điều kiện mời
    Issued --> Accepted: Lời mời được dùng hợp lệ
    Issued --> Expired: Quá hạn
    Issued --> Revoked: Hủy / Leaver / rủi ro
    Accepted --> Processing: Proofing / MFA
    Processing --> ActionRequired: Cần bổ sung
    ActionRequired --> Processing: Hoàn tất bước bổ sung
    Processing --> Completed: Điều kiện enrollment đạt
    Processing --> Revoked: Thu hồi giữa chừng
    ActionRequired --> Revoked: Thu hồi
    Expired --> [*]
    Revoked --> [*]
    Completed --> [*]
~~~

**Notification attempt** có thể có những trạng thái khác như **QUEUED, SENT_TO_PROVIDER, DELIVERED, BOUNCED, FAILED, RETRYING**. Chúng không tự động chuyển enrollment từ Issued sang Completed. “Delivered” do nhà cung cấp báo không bảo đảm người nhận đã đọc.

### Sự kiện minh họa

~~~json
{
  "eventId": "evt-enr-00871",
  "eventType": "ENROLLMENT_INVITATION_ISSUED",
  "occurredAt": "2026-11-23T08:15:00+07:00",
  "enrollmentId": "enr-1042",
  "subjectRef": "person-P-1042",
  "source": "IAM_ORCHESTRATOR",
  "version": 5,
  "notification": {
    "templateKey": "identity-enrollment-invitation",
    "templateVersion": "v3",
    "locale": "vi-VN",
    "channel": "EMAIL",
    "recipientContactRef": "contact-ref-77",
    "deliveryCorrelationId": "delivery-991"
  },
  "expiresAt": "2026-11-30T17:00:00+07:00"
}
~~~

Ví dụ này là **JSON sự kiện nội bộ giả định**, không phải schema chuẩn SCIM hay OIDC. **recipientContactRef** là tham chiếu tới dữ liệu liên hệ được bảo vệ; nếu không cần thì không sao chép địa chỉ email đầy đủ vào mọi event.

## 10. Chống gửi lặp và gửi thông báo đã lỗi thời

Khi gửi qua queue, nhà cung cấp email/SMS hoặc event bus, sự kiện có thể đến trễ, bị phát lại hoặc nhận sai thứ tự. Một thiết kế đáng tin cậy phải có các đặc tính sau:

- **Idempotency:** dùng khóa theo enrollment, loại thông báo, người nhận, phiên bản sự kiện và đợt gửi để tránh gửi lặp do retry.
- **Version/order:** sự kiện Mover cũ không được mở lại lời mời của người đã chuyển sang trạng thái Leaver.
- **Kiểm tra ngay trước dispatch:** khi lấy một job từ queue, đọc trạng thái hiện tại của enrollment và token để bảo đảm vẫn được phép gửi.
- **Thu hồi đồng thời nhiều tầng:** hủy job đang chờ, vô hiệu token và cập nhật trạng thái account khi có sự kiện quan trọng.
- **Retry có giới hạn:** dùng backoff và phân biệt lỗi tạm thời/vĩnh viễn; lỗi địa chỉ sai không nên dẫn tới gửi vô hạn.
- **Sự kiện đến muộn:** callback “delivery failed” xuất hiện sau khi enrollment hoàn tất không được tự mở lại quy trình.
- **Correlation ID:** nối được sự kiện nguồn, notification request, nhà cung cấp và kết quả ở IdP/hệ thống đích.
- **Transactional outbox hoặc cơ chế nhất quán phù hợp:** giữ quan hệ tin cậy giữa thay đổi trạng thái và yêu cầu phát thông báo khi hệ thống có nhiều bước bất đồng bộ.

### Giả mã kiểm tra trước khi gửi

~~~text
function dispatchEnrollmentNotice(job):
    enrollment = loadCurrentEnrollment(job.enrollmentId)

    if enrollment.version < job.requiredMinVersion:
        return RETRY_LATER

    if enrollment.state in {REVOKED, EXPIRED, CANCELED}:
        return SUPPRESSED

    if job.kind == INVITATION and enrollment.state != ISSUED:
        return SUPPRESSED

    if alreadySent(job.idempotencyKey):
        return DUPLICATE_SKIPPED

    contact = getApprovedContact(enrollment.subjectId, job.channel)
    if contact is not valid:
        return ESCALATE_TO_HELPDESK

    delivery = sendApprovedTemplate(job.template, contact)
    recordOutcome(job, delivery)
    return delivery.status
~~~

Đây là **giả mã**, chưa bao gồm xử lý giao dịch, race condition hoặc quản lý bí mật. Triển khai thật cần bảo đảm việc kiểm tra trạng thái và ghi idempotency an toàn trong tình huống nhiều worker xử lý cùng lúc.

## 11. Nhắc trước hạn, xử lý thất bại và escalation

Lịch nhắc nên bám vào **mốc nghiệp vụ** và chỉ gửi khi còn hành động hợp lệ cần thực hiện.

| Mốc | Điều kiện | Hành động |
|---|---|---|
| Lời mời được phát hành | Kênh đã được xác minh và chủ thể đủ điều kiện | Gửi lời mời |
| Trước ngày bắt đầu | Chưa hoàn tất, còn thời gian phù hợp | Gửi nhắc theo chính sách |
| Gần hết hạn | Chưa sử dụng và lời mời còn hợp lệ | Nhắc thời hạn cụ thể |
| Đã hết hạn | Thời hạn token đã qua | Khóa token, hướng dẫn xin cấp lại |
| Bounce/lỗi kênh kéo dài | Không có địa chỉ liên hệ hợp lệ | Mở ticket cho HR/helpdesk xác minh |
| Quá hạn nghiệp vụ | Enrollment vẫn chưa hoàn tất | Báo manager hoặc owner theo thẩm quyền |
| Rủi ro bảo mật | Hành động bất thường, chiếm đoạt có khả năng | Thu hồi, chặn truy cập, cảnh báo Security |

Các ngày/giờ và SLA là **chính sách của từng tổ chức**, không nên tự coi một chu kỳ nhắc cố định là bắt buộc cho mọi loại nhân viên.

Người dùng không nên nhận thư “bạn chưa đăng ký MFA” sau khi họ đã hoàn tất. Trước khi nhắc, cần xác minh **trạng thái IdP mới nhất** và cân nhắc độ trễ đồng bộ. Nếu người dùng đã hoàn tất nhưng một hệ thống chưa cập nhật, thông điệp nên đưa tới cổng hiển thị trạng thái thực tế và đường hỗ trợ, thay vì khẳng định sai.

### Escalation có người chịu trách nhiệm

Không nên gửi ticket tới một hộp thư chung mà không có owner, deadline hoặc cách xử lý. Escalation cần xác định vấn đề thuộc về **HR, người dùng, helpdesk, quản trị IdP, nhà cung cấp notification hay chủ ứng dụng**. Đồng thời, không chuyển tiếp token của người dùng đến manager để “làm giúp”.

## 12. IdP, SSO, SCIM và quy tắc quyền ảnh hưởng thế nào?

| Thành phần | Trách nhiệm liên quan | Điều thông báo cần phản ánh |
|---|---|---|
| **HRIS** | Hồ sơ và ngày hiệu lực Joiner/Mover/Leaver | Lời mời còn đúng người, đúng thời điểm |
| **IAM/IGA** | Điều phối enrollment, phê duyệt, ghi nhận và thu hồi | Loại thông báo, người nhận, trạng thái được phép |
| **IdP** | Tài khoản, phương thức đăng nhập, MFA/passkey, phiên | Kết quả authenticator enrollment đã được xác minh |
| **SSO/SAML/OIDC** | Liên kết xác thực đến ứng dụng | Đăng nhập thành công không chứng minh đầy đủ quyền đích |
| **SCIM hoặc API** | Cấp/sửa/thu hồi user và nhóm ở ứng dụng | Kết quả provisioning cần đối soát |
| **RBAC/ABAC** | Quyền theo vai trò, thuộc tính và điều kiện | Không xác nhận quyền nếu chưa đạt chính sách |
| **Audit/reconciliation** | Phát hiện chênh lệch và quyền còn tồn dư | Cảnh báo lỗi cấp/thu hồi sau enrollment |

**SCIM không phải giao thức gửi notification**; nó hỗ trợ provisioning đối tượng theo khả năng của nhà cung cấp. Việc có SCIM không bảo đảm có thông báo sẵn cho người dùng. **SSO cũng không tự đồng bộ mọi quyền hoặc thu hồi phiên ứng dụng.**

Một trường hợp rất thực tế: người dùng đã enroll MFA và đăng nhập IdP, nhưng SCIM lỗi khi thêm vào nhóm ứng dụng. Hệ thống có thể thông báo **“bạn đã hoàn tất enrollment xác thực; quyền ứng dụng đang được xử lý”** thay vì **“bạn có thể sử dụng mọi ứng dụng”**.

## 13. Thông báo trong Joiner–Mover–Leaver

### Joiner: phát hành đúng kênh và đúng thời điểm

- Đọc dữ liệu nhân sự từ nguồn có thẩm quyền, chống trùng và xác định kênh ban đầu hợp lệ.
- Phát lời mời trước ngày bắt đầu khi được chính sách cho phép; account có thể ở trạng thái chưa kích hoạt.
- Hướng dẫn proofing, thiết lập MFA/passkey và chuẩn bị quyền baseline.
- Chỉ xác nhận sẵn sàng khi các điều kiện bắt buộc và trạng thái hệ thống đích đạt.
- Báo người quản lý khi chậm có ảnh hưởng công việc, không tiết lộ bí mật/chi tiết định danh không cần thiết.

### Mover: bổ sung bước enrollment khi chính sách thay đổi

Người đổi vai trò có thể cần **enroll authenticator mạnh hơn**, đăng ký thiết bị mới, xác minh danh tính tăng cường hoặc chấp thuận thêm điều kiện bảo mật. Khi đó, thông báo nên giải thích **bước mới cần làm**, thời hạn và cách truy cập cổng. Không tự khẳng định người đó đã nhận quyền quản trị chỉ vì một lời mời setup MFA vừa được phát hành.

Quan trọng hơn, Mover phải đồng thời **thu hồi quyền không còn phù hợp của vai trò cũ**. Thư thông báo vai trò mới không chứng minh quyền CRM, API token hoặc phiên cũ đã bị thu hồi.

### Leaver: dừng mọi lời mời không còn hiệu lực

Khi quan hệ công việc chấm dứt:

1. Đánh dấu lời mời còn mở là không hợp lệ theo chính sách.
2. Thu hồi token, hủy job nhắc và chặn dispatch từ sự kiện queue cũ.
3. Vô hiệu hóa đăng nhập, thu hồi phiên/token và quyền ứng dụng theo khả năng, kiểm tra hệ thống đích.
4. Báo IT/owner về ngoại lệ chưa thu hồi xong, có deadline xử lý.
5. Bảo quản hoặc xóa audit notification theo chính sách lưu trữ và nghĩa vụ áp dụng.

**Hủy thư mời không đồng nghĩa thu hồi truy cập.** Một người đã có account, session, khóa API hoặc quyền local vẫn cần được deprovision qua quy trình Leaver riêng.

### Rejoiner: không hồi sinh enrollment cũ

Nếu người từng nghỉ quay lại, hệ thống phải xác minh lại mối quan hệ hiện tại, nguồn liên hệ, trạng thái authenticator và điều kiện cấp quyền. Không nên tự tái dùng token mời cũ hoặc khôi phục tất cả quyền của lần làm việc trước.

## 14. Thông báo enrollment cho thiết bị và service account

**Device account** và **service/workload identity** cũng có vòng đời enrollment nhưng không giống lời mời cho con người.

- **Thiết bị:** owner/IT được thông báo khi thiết bị enroll vào IdP/MDM, chính sách compliance chưa đạt, credential sắp hết hạn hoặc thiết bị bị thu hồi. Đăng ký thiết bị không thay thế kiểm tra quyền của người dùng đang sử dụng.
- **Service account:** owner kỹ thuật biết khi yêu cầu account được duyệt, quyền bị đổi, credential gần hết hạn, quy trình luân chuyển thất bại hoặc account bị deprovision.
- **Workload identity:** có thể dùng chứng chỉ và token ngắn hạn do hệ thống cấp tự động; thông báo chủ yếu là event vận hành tới pipeline, monitoring và owner.
- **Leaver của owner:** chuyển giao trách nhiệm service identity/bot; đánh giá quyền và xoay vòng credential mà người rời đi có thể từng biết, thay vì xóa nhầm bot đang phục vụ sản xuất.

**Không gửi private key, API key, password hoặc token workload trong email/push.** Credential cần được tạo và trao đổi qua cơ chế quản lý bí mật, liên kết danh tính máy hoặc kênh bảo vệ được thiết kế cho trường hợp đó.

## 15. Phòng phishing, bảo vệ PII và khả năng tiếp cận

Thông báo enrollment dễ bị lợi dụng để lừa người mới, vì họ chưa quen domain, mẫu email hay bộ phận IT của tổ chức.

### Kiểm soát kỹ thuật

- Dùng miền gửi và template được tổ chức phê duyệt; với email có thể áp dụng SPF, DKIM và DMARC phù hợp.
- Xác thực và phân quyền nguồn yêu cầu gửi; tránh để người dùng bất kỳ tự tạo lời mời cho địa chỉ người khác.
- Giới hạn tần suất và chống dò xem một email/tài khoản có tồn tại hay không.
- Không đưa mật khẩu, OTP, mã khôi phục, ảnh giấy tờ, dữ liệu sinh trắc học hay token thô vào log, ticket, email hoặc analytics.
- Kiểm tra link đích, hostname HTTPS, redirect và nội dung động của template để tránh link giả hoặc injection.
- Có kênh báo cáo lời mời bất ngờ, gửi nhầm hoặc nghi mạo danh; thu hồi token nếu phát hiện nguy cơ.
- Có cơ chế bảo vệ thông tin liên hệ và retention phù hợp, phân quyền đọc dữ liệu notification.

### Hướng dẫn cho người nhận

Nếu nhận lời mời không mong đợi, người dùng nên **truy cập cổng IAM từ địa chỉ đã biết hoặc liên hệ helpdesk theo kênh chính thức đã công bố**, không chỉ tin đường dẫn/số liên hệ bên trong email. Không chia sẻ OTP, mật khẩu hoặc recovery code cho bất kỳ người gọi tự nhận là nhân viên IT.

### Khả năng tiếp cận và ngôn ngữ

Thông báo cần dùng ngôn từ dễ hiểu, rõ thời hạn và múi giờ, không chỉ dựa vào màu sắc, tương thích thiết bị di động và trình đọc màn hình. Với người không nhận được email/SMS hoặc không thể hoàn thành bước mặc định, phải có **quy trình hỗ trợ thay thế được phê duyệt**. Tránh gửi thông báo như “HTTP 409” không giải thích người dùng cần làm gì.

## 16. Kiểm toán và đo lường hiệu quả

| Chỉ số | Ý nghĩa | Không nên suy diễn |
|---|---|---|
| **Dispatch success rate** | Tỷ lệ lệnh gửi được nhà cung cấp chấp nhận | Không đồng nghĩa người nhận đã đọc |
| **Delivery failure rate** | Bounce, số liên hệ không đúng, lỗi provider | Không nhất thiết lỗi IAM chính |
| **Enrollment completion rate** | Quy trình đạt điều kiện enrollment | Không thể thay bằng tỷ lệ click email |
| **Time to enroll** | Thời gian từ mốc bắt đầu đến hoàn tất | Cần tách thời gian chờ người dùng/phê duyệt |
| **Unused expired invitations** | Số lời mời hết hạn chưa dùng | Có thể do địa chỉ sai hoặc chính sách quá gấp |
| **Reminders per enrollment** | Mức độ nhắc một yêu cầu | Giá trị quá cao có thể là spam hoặc trạng thái lỗi |
| **Stale notification count** | Thư gửi sau khi yêu cầu bị hủy/hoàn tất | Rất quan trọng cho Leaver |
| **Wrong-recipient incidents** | Gửi sai người/địa chỉ | Cần điều tra khả năng token đã bị dùng |
| **Provisioning residual issues** | Enrollment đạt nhưng quyền đích chưa đúng | Cần đối soát SCIM/API và quyền thực tế |

Bằng chứng kiểm toán nên có **eventId, enrollmentId, loại thông báo, nguồn sự kiện, phiên bản template, kênh, tham chiếu người nhận, timestamp, delivery correlation ID, trạng thái, quyết định resend/revoke và người xử lý ngoại lệ**.

Không lưu token kích hoạt thô trong audit log. Nếu cần lưu nội dung thông báo đã gửi để chứng minh tuân thủ, phải bảo vệ, giới hạn người xem, hạn chế PII và đặt thời hạn lưu giữ theo chính sách.

## 17. Tình huống lỗi thường gặp

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Email Joiner được HR nhập sai | Link tới người không đúng | Thu hồi token, xác minh kênh và đánh giá lời mời có bị sử dụng chưa |
| Hộp thư chặn email | Người mới không thấy lời mời | Kiểm tra trạng thái gửi, hướng dẫn qua cổng chính thức, không gửi lặp vô hạn |
| Email security scanner mở link trước | Token một lần bị tiêu thụ ngoài ý muốn | Không kích hoạt trạng thái nhạy cảm bằng GET |
| Lời mời hết hạn | Không thể hoàn tất onboarding | Thu hồi token cũ, cấp lại theo quy trình đã xác minh |
| Nhận nhiều lời mời liên tiếp | Người dùng không biết link hợp lệ | Quản lý version và trạng thái, hủy lời mời cũ |
| Hai request redeem cùng lúc | Có thể kích hoạt trùng | Xử lý nguyên tử và idempotency |
| HR hủy onboarding | Lời mời vẫn còn hiệu lực | Hủy queue, revoke token, kiểm tra tài khoản và quyền đích |
| MFA đã enroll nhưng SCIM lỗi | Báo nhầm tài khoản sẵn sàng | Phân biệt enrollment completed với provisioning pending |
| Mover cần MFA mới | Ngỡ đã có quyền vai trò mới | Nêu điều kiện bảo mật và chờ duyệt/quyền thực tế |
| Leaver rồi nhưng vẫn có thư nhắc | Lộ quy trình hoặc có khả năng truy cập cũ | Chặn send-time, thu hồi token và đối soát quyền |
| Bot hết hạn credential | Dịch vụ ngừng | Thông báo owner và luân chuyển qua kênh bảo mật |
| Người dùng báo thư đáng ngờ | Nguy cơ phishing | Xác minh event từ nguồn, thu hồi nếu cần và chuyển Security |

## 18. Ví dụ xuyên suốt Joiner–Mover–Leaver

Giả sử **Mai** bắt đầu làm nhân viên hỗ trợ khách hàng ngày **01/12/2026**.

**Joiner — 25/11/2026:** HRIS đã xác minh hồ sơ, gửi sự kiện gồm ID ổn định, ngày bắt đầu và kênh liên hệ. IAM kiểm tra trùng, tạo lời mời có thời hạn, bảo vệ token và gửi thông báo. Account IdP có thể được chuẩn bị sẵn, nhưng chưa tự cho phép toàn bộ quyền trước thời điểm hợp lệ. Hệ thống lưu riêng trạng thái lời mời và trạng thái giao nhận.

**Enrollment — 26/11/2026:** Mai vào cổng chính thức, hoàn tất các bước proofing còn thiếu và đăng ký MFA. IdP xác nhận điều kiện enrollment đạt; IAM tính quyền nền theo vai trò Support Agent và đồng bộ sang ứng dụng helpdesk. Nếu connector bị lỗi, chỉ thông báo bước đăng ký hoàn tất và trạng thái quyền đang xử lý.

**Kích hoạt — 01/12/2026:** Đến ngày có hiệu lực, account được kích hoạt theo chính sách, đăng nhập SSO và quyền đích được kiểm tra. Thông báo xác nhận hướng dẫn Mai đăng nhập từ cổng chính thức, không gửi mật khẩu ban đầu qua email.

**Mover — 01/03/2027:** Mai chuyển sang vị trí trưởng nhóm cần đăng ký phương thức xác thực mạnh hơn và phê duyệt quyền mới. IAM gửi lời nhắc enrollment thêm authenticator, thu hồi quyền cũ không còn phù hợp và chỉ kích hoạt quyền mới khi đủ điều kiện. Không gửi “đã có quyền quản trị” khi chưa xác minh.

**Leaver — 30/06/2027:** HRIS phát sự kiện kết thúc quan hệ. IAM thu hồi lời mời, hủy job nhắc đang chờ, vô hiệu tài khoản, thu hồi phiên/token và quyền hệ thống đích rồi đối soát. Nếu có email từ queue cũ, send-time check phải ngăn phát hành. Việc chặn thông báo phải diễn ra cùng **quy trình deprovision thực tế**, không thay cho deprovision.

Tình huống cho thấy thông báo cần phản ánh **trạng thái được kiểm chứng ngay tại thời điểm phát**, đồng thời tôn trọng các quyết định danh tính, xác thực và phân quyền độc lập.

## 19. Checklist triển khai thông báo enrollment

1. **Nguồn đáng tin:** sự kiện gửi có được phát từ HRIS/IAM/IdP đã xác thực và kiểm tra trạng thái chưa?
2. **Đúng người nhận:** lời mời gắn với identity ID bền vững, kênh liên hệ đã được kiểm tra đúng mức chưa?
3. **Đúng thông điệp:** đã nêu mục đích, hành động, thời hạn, múi giờ và kênh hỗ trợ mà không để lộ PII không cần thiết chưa?
4. **Kênh phù hợp:** Joiner có thực sự dùng được email/portal được chọn chưa? Có phương án hỗ trợ an toàn không?
5. **Token an toàn:** khó đoán, giới hạn phạm vi, hết hạn, thu hồi, dùng một lần theo chính sách và không lộ qua log/GET tự động chưa?
6. **Trạng thái chính xác:** hệ thống có phân biệt đã mời, đã gửi, đã dùng, MFA hoàn tất, provisioning xác nhận và account kích hoạt chưa?
7. **Chống gửi nhầm/cũ:** queue có idempotency, version, giới hạn retry và kiểm tra trạng thái trước khi gửi chưa?
8. **Nhắc có kiểm soát:** lịch nhắc, escalation, owner và deadline có được xác định để không spam không?
9. **Tôn trọng JML:** Joiner được hướng dẫn đúng thời điểm; Mover nhận yêu cầu bổ sung; Leaver thu hồi mọi lời mời cũ chưa?
10. **Phi con người:** thông báo service/device gửi đúng owner, secret được quản lý bằng kênh chuyên dụng chưa?
11. **Có kiểm toán:** lưu sự kiện, tham chiếu người nhận, trạng thái và kết quả mà không lưu token thô chưa?
12. **Có đối soát:** sau enrollment có kiểm tra quyền thực tế ở IdP, SCIM/ứng dụng và các đường truy cập tồn dư không?

### Ghi nhớ

**Thông báo enrollment là lớp giao tiếp và kiểm soát trạng thái trong quy trình ghi danh danh tính.** Nó phải được gửi đúng người, đúng thời điểm, diễn đạt rõ việc cần làm và có khả năng chống phishing, gửi nhầm hoặc phát lại sự kiện cũ. Trong IAM lifecycle, thông báo giúp **Joiner** bắt đầu an toàn, **Mover** hoàn tất điều kiện bảo mật mới và **Leaver** chấm dứt lời mời không còn hợp lệ. **Trạng thái đã gửi thông báo không thể thay thế bằng chứng xác minh danh tính, hoàn tất enrollment, cấp quyền hay thu hồi quyền trên hệ thống đích.**
