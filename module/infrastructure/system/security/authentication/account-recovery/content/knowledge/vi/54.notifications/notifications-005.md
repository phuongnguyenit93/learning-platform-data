# Security contact notification — Thông báo tới liên hệ bảo mật

## 1. Liên hệ bảo mật là ai trong luồng khôi phục?

**Security contact notification** là thông báo về sự kiện bảo mật được gửi tới một liên hệ đã được thiết lập để nhận cảnh báo liên quan đến tài khoản. Trong khôi phục tài khoản, thông báo giúp chủ tài khoản hoặc người được chỉ định nhận biết hoạt động khi mật khẩu, MFA, passkey hoặc thiết bị xác thực có thể không còn trong tầm kiểm soát.

Trong bài này, **liên hệ bảo mật** được hiểu là một quan hệ nhận cảnh báo đã được đăng ký và có phạm vi xác định. Đó có thể là địa chỉ phụ của chính chủ tài khoản hoặc một người được chỉ định, nếu sản phẩm hỗ trợ. Một nhóm an ninh của tổ chức chỉ thuộc phạm vi này khi có chính sách và quyền nhận thông tin tương ứng; không mặc định gửi dữ liệu tài khoản cá nhân tới quản trị viên bất kỳ.

Cần phân biệt vai trò nhận cảnh báo với những vai trò khác:

| Vai trò | Mục đích | Điều không tự có |
| --- | --- | --- |
| Notification contact | Nhận thông tin về sự kiện trong phạm vi được cho phép | Quyền khôi phục hoặc thay yếu tố xác thực |
| Recovery contact | Tham gia một phương thức khôi phục đã được thiết kế riêng | Quyền phê duyệt mọi loại tác vụ |
| Recovery approver | Ra quyết định trong một quy trình có thẩm quyền cụ thể | Quyền truy cập toàn bộ dữ liệu tài khoản |
| Kênh liên hệ mới khai báo trong request | Nhận trao đổi theo bước xử lý được cho phép | Tư cách liên hệ bảo mật đã đăng ký |
| Bộ phận hỗ trợ | Hỗ trợ theo quy trình và quyền công việc | Quyền bỏ qua bằng chứng chỉ vì nhận được email |

Cùng một người có thể giữ nhiều vai trò, nhưng từng vai trò phải được thiết lập riêng. Việc người đó nhận một cảnh báo không tự kích hoạt quyền của vai trò khác.

[NIST SP 800-63B-4, mục Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#notification) mô tả thông báo độc lập tới người dùng hoặc người được chỉ định để hỗ trợ phát hiện gian lận. Tiêu chuẩn cũng phân biệt recovery contacts với địa chỉ nhận thông báo. Bài này dùng sự phân biệt đó để xây dựng mô hình minh họa; các trường dữ liệu và chính sách ví dụ không phải tuyên bố đáp ứng toàn bộ tiêu chuẩn.

## 2. Mục tiêu và ranh giới tin cậy

Một liên hệ bổ sung có thể giúp chủ tài khoản biết sự kiện khi thiết bị chính bị mất hoặc hộp thư chính không còn tiếp cận được. Tuy nhiên, liên hệ bổ sung cũng tạo thêm nơi nhận dữ liệu và có thể đã lỗi thời, bị chiếm quyền hoặc không còn phù hợp.

Thiết kế cần giữ ba ranh giới:

1. **Ranh giới lựa chọn người nhận:** người nhận đến từ quan hệ đã được thiết lập bằng quy trình có thẩm quyền, không từ địa chỉ tùy ý trong request khôi phục.
2. **Ranh giới tiết lộ:** mỗi người nhận chỉ thấy dữ liệu cần cho vai trò của họ.
3. **Ranh giới hành động:** đọc, xác nhận đã xem hoặc báo cáo một cảnh báo không đồng nghĩa với cho phép khôi phục.

Ví dụ, người yêu cầu có thể nhập email của nạn nhân rồi cung cấp “email của người thân để xác nhận”. Địa chỉ mới đó chưa có tư cách liên hệ bảo mật. Nếu hệ thống tự gửi hồ sơ khôi phục hoặc nút phê duyệt tới đó, người yêu cầu đang tự chọn người xác nhận cho chính mình.

Một thiết kế an toàn cần biểu diễn rõ nguồn gốc quan hệ liên hệ, quyền đã được cấp và phiên bản còn hiệu lực. Kiểm tra cú pháp email chỉ xác nhận định dạng; việc xác nhận kiểm soát hộp thư ở một thời điểm cũng chưa chứng minh người đó là chủ tài khoản hoặc được phép phê duyệt thay MFA.

## 3. Thiết lập liên hệ trước khi xảy ra sự cố

Quan hệ nhận cảnh báo nên được thiết lập trong một luồng quản lý tài khoản có kiểm tra quyền phù hợp. Đối với tài khoản tổ chức, có thể dùng quy trình quản trị đã được phê duyệt. Không coi việc đang có một session là đủ cho mọi thay đổi nhạy cảm đối với kênh bảo mật.

Một vòng đời minh họa:

~~~text
PROPOSED
   |
   v
PENDING_VERIFICATION
   |
   v
PENDING_ACCEPTANCE
   |
   v
ACTIVE
   |
   +--> REVOKED
   +--> SUSPENDED
   +--> EXPIRED
~~~

Ý nghĩa từng bước cần được quy định:

- Chủ thể có thẩm quyền đề xuất người nhận và phạm vi nhận.
- Hệ thống xác nhận kênh theo cơ chế phù hợp.
- Nếu người nhận là một người khác, sản phẩm có thể yêu cầu họ chấp nhận vai trò và biết loại thông tin sẽ nhận.
- Chỉ quan hệ đủ điều kiện mới chuyển sang ACTIVE.
- Việc thu hồi, hết hạn hoặc tạm dừng phải có hiệu lực đối với những công việc gửi chưa hoàn tất theo policy.

Các bước xác minh và chấp nhận có thể được kết hợp trong một trải nghiệm, nhưng về dữ liệu vẫn cần biết điều gì đã được chứng minh. Một email xác nhận không nên đồng thời tạo quyền phê duyệt khôi phục nếu người nhận chỉ đồng ý nhận cảnh báo.

Thư mời trước khi quan hệ có hiệu lực cần tiết lộ ít thông tin. Nó không được chứa dữ liệu recovery request, mã xác thực của chủ tài khoản hoặc lịch sử bảo mật. Chức năng mời cũng cần chống gửi rác tới một địa chỉ chưa đồng ý nhận.

Trong giao diện quản lý, chủ tài khoản cần xem được những liên hệ đang có hiệu lực và phạm vi nhận. Với người nhận là người khác, cần có cách từ chối hoặc rút khỏi quan hệ của chính họ. Hành động này không được biến thành quyền đóng tài khoản của người đã chỉ định.

## 4. Những sự kiện nào nên được gửi?

Không phải mọi lần nhập sai email hoặc mọi lần thử mã đều cần gửi cho mọi liên hệ. Sự kiện phải có ý nghĩa rõ và được ánh xạ vào policy phù hợp.

| Sự kiện | Nội dung có thể thông báo | Điều cần phân biệt |
| --- | --- | --- |
| Yêu cầu khôi phục được chấp nhận | Có một giao dịch đã bắt đầu, với thời điểm và loại tác vụ | Chưa chứng minh người yêu cầu là chủ tài khoản |
| Nhánh xem xét được mở | Có một quy trình cần được chủ tài khoản lưu ý | Không tự cấp quyền cho liên hệ xem hồ sơ |
| Quyền thực hiện tác vụ được cấp | Một bước cho phép cụ thể đã xảy ra, nếu policy yêu cầu cảnh báo | Tác vụ chưa nhất thiết hoàn tất |
| Mật khẩu hoặc yếu tố xác thực được thay | Thay đổi cụ thể đã commit thành công | Không mô tả thành sự kiện chỉ mới bắt đầu |
| Liên hệ bảo mật được thêm, thay hoặc thu hồi | Cấu hình nhận cảnh báo đã thay đổi | Người nhận mới không phải nguồn duy nhất để xác nhận thay đổi |
| Phát hiện chuỗi yêu cầu bất thường | Một tín hiệu cần xem xét theo policy | Không khẳng định chắc chắn ai là kẻ tấn công |

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors) khuyến nghị thông báo qua kênh khác khi yếu tố MFA thay đổi. Với bài này, điểm áp dụng là giữ cảnh báo về thay đổi đã hoàn tất như một sự kiện có ý nghĩa riêng, thay vì coi thư khởi tạo là bằng chứng thay thế.

Thông báo cần dựa trên sự kiện đã được xác nhận, không dựa vào việc trình duyệt đã mở một màn hình. Một giao dịch bị rollback không được tạo ra cảnh báo rằng yếu tố xác thực đã thay thành công.

Không công khai danh sách liên hệ bảo mật qua endpoint khôi phục chưa xác thực. Câu trả lời như “đã gửi tới người thân có email a***@...” có thể làm lộ quan hệ cá nhân hoặc giúp dò tài khoản.

## 5. Chọn người nhận và kiểm tra quyền tiết lộ

Có thể xem quyết định gửi là kết quả của một hàm chính sách:

~~~text
resolveRecipients(
    trustedAccountContext,
    committedSecurityEvent,
    contactDesignationVersion,
    disclosurePolicy
)
~~~

Đầu vào phải đến từ ngữ cảnh server tin cậy. Một account ID hoặc tenant ID do client gửi không tự chứng minh quyền truy cập.

Quy trình lựa chọn minh họa:

1. Xác nhận sự kiện thuộc đúng tài khoản và tenant.
2. Nạp các quan hệ nhận cảnh báo phù hợp với loại sự kiện.
3. Kiểm tra vai trò, trạng thái, phiên bản và phạm vi tiết lộ.
4. Lưu quyết định người nhận cùng phiên bản policy.
5. Tạo một ý định gửi riêng cho từng người nhận và kênh cần thiết.
6. Kiểm tra lại điều kiện còn áp dụng trước khi gọi nhà cung cấp.

Chọn người nhận tại thời điểm sự kiện giúp giải thích ai đáng lẽ được thông báo. Kiểm tra lại trước khi gửi giúp xử lý trường hợp người nhận đã bị thu hồi hoặc mất quyền trong lúc công việc chờ.

Không giải quyết thay đổi này bằng cách tự thay địa chỉ trong job cũ bằng địa chỉ mới nhất của tài khoản. Đó là thay người nhận của một quyết định đã có. Nếu policy yêu cầu chọn lại, cần ghi nhận quyết định mới và lý do.

Nếu áp dụng một tiêu chuẩn có yêu cầu cụ thể về tập địa chỉ phải được thông báo, policy lựa chọn phải đáp ứng đúng yêu cầu đó. Không lấy ví dụ “chọn một liên hệ phù hợp” làm lý do bỏ các đích gửi bắt buộc.

## 6. Khi thêm hoặc thay liên hệ bảo mật

Thay liên hệ nhận cảnh báo là một thao tác nhạy cảm: người chiếm session có thể cố chuyển cảnh báo sang địa chỉ của họ trước khi mở khôi phục hoặc thay MFA.

Một mô hình cập nhật có thể tách:

- Quan hệ cũ đã có hiệu lực.
- Quan hệ mới đang chờ xác minh hoặc chấp nhận.
- Sự kiện yêu cầu thay đổi.
- Sự kiện thay đổi thực sự có hiệu lực.
- Các thông báo về thay đổi gửi theo policy.

Việc xác nhận địa chỉ mới không tự chứng minh rằng người khởi xướng có quyền thay liên hệ cũ. Hai câu hỏi này cần hai kiểm tra tương ứng.

Đối với thay đổi nhạy cảm, policy có thể yêu cầu cảnh báo qua kênh đã được thiết lập trước đó và qua kênh mới sau khi đủ điều kiện. Mục đích là tránh để người nhận mới trở thành nơi duy nhất biết việc thay đổi. Không áp dụng quy tắc gửi tới địa chỉ cũ một cách mù quáng nếu địa chỉ đó đã được xác định là bị thu hồi hoặc có nguy cơ tiết lộ dữ liệu; ngoại lệ cần có phạm vi và nội dung tối thiểu rõ ràng.

Nếu có thời gian chờ trước khi liên hệ mới có thể tham gia khôi phục, hãy phân biệt thời gian đó với quyền nhận thông báo. Một địa chỉ vừa được xác minh có thể đủ điều kiện nhận xác nhận thiết lập, nhưng chưa chắc đủ điều kiện nhận dữ liệu giao dịch hoặc cung cấp bằng chứng khôi phục.

Khi hệ thống đã có dấu hiệu bị chiếm đoạt, không để việc thay liên hệ trong cùng luồng trở thành cách xóa mọi kênh cảnh báo cũ mà không có kiểm soát. Nhánh xử lý khẩn cấp phải xác định ai có quyền ra quyết định, căn cứ nào được dùng và cách lưu lịch sử.

## 7. Nội dung phải phù hợp với từng vai trò

Chủ tài khoản và một người chỉ được chỉ định nhận cảnh báo không nhất thiết cần thấy cùng nội dung. Việc gửi cùng một template đầy đủ cho tất cả người nhận có thể làm lộ thông tin không cần thiết.

Một mẫu cho người được chỉ định nhận cảnh báo có thể là:

~~~text
Tiêu đề: Có sự kiện bảo mật cần được lưu ý

Một yêu cầu khôi phục quyền truy cập đã được ghi nhận
đối với tài khoản mà bạn đã đồng ý nhận cảnh báo bảo mật.

Thời điểm sự kiện: 24/11/2026, 16:10 (UTC+07:00)
Loại sự kiện: Bắt đầu khôi phục quyền truy cập

Thông báo này không yêu cầu bạn cung cấp mã xác thực
và không trao quyền thay đổi tài khoản.

Nếu cần xem thông tin trong phạm vi được cho phép,
hãy tự mở ứng dụng hoặc trang web chính thức
và truy cập mục liên hệ bảo mật.

Nếu bạn không còn muốn giữ vai trò này,
hãy quản lý quan hệ nhận cảnh báo của mình
qua kênh chính thức.
~~~

Mẫu trên chỉ phù hợp với một quan hệ đã ACTIVE và được phép biết loại sự kiện này. Không gửi nó như thư mời tới một địa chỉ chưa được chấp nhận.

Nếu một người nhận cảnh báo cho nhiều tài khoản, có thể cần nhãn phân biệt đã được thống nhất trước. Nhãn phải nằm trong phạm vi được phép chia sẻ; không mặc định dùng tên pháp lý, email đầy đủ hoặc tên doanh nghiệp nhạy cảm. Tránh đưa chi tiết tài khoản vào tiêu đề và push trên màn hình khóa.

Dữ liệu không nên có trong thông báo cảnh báo thuần túy:

- Token khôi phục, OTP, mã dự phòng, cookie hoặc liên kết tạo session.
- Hồ sơ giấy tờ, ảnh xác minh, câu trả lời kiểm tra danh tính.
- Điểm rủi ro chi tiết hoặc tiêu chí có thể giúp vượt kiểm soát.
- Danh sách toàn bộ yếu tố xác thực và các liên hệ khác.
- Nội dung do người khởi xướng tự nhập nhưng được trình bày như sự thật đã xác minh.

Nếu cùng một người còn là recovery contact theo một phương thức khác, thông điệp chứa mã khôi phục phải thuộc hợp đồng và luồng tương ứng. Không thêm mã vào template cảnh báo chỉ vì người nhận “đáng tin”.

## 8. Phản hồi của liên hệ có giá trị gì?

Một số sản phẩm cho liên hệ báo “không nhận ra hoạt động này”, xác nhận đã xem hoặc đề nghị chủ tài khoản kiểm tra. Cần biểu diễn đúng giá trị của từng phản hồi.

| Phản hồi | Ý nghĩa có thể ghi nhận | Không được tự suy ra |
| --- | --- | --- |
| Đã xem | Có một tín hiệu tương tác theo cơ chế được thiết kế | Chủ tài khoản đã đọc hoặc đồng ý |
| Báo hoạt động đáng ngờ | Có một báo cáo cần xem xét | Danh tính kẻ tấn công đã được xác định |
| Không phản hồi | Chưa có phản hồi được hệ thống ghi nhận | Sự kiện được chấp thuận |
| Từ chối tiếp tục vai trò | Người nhận rút khỏi quan hệ nhận cảnh báo tương ứng | Người đó có quyền hủy tài khoản |
| Phê duyệt trong luồng riêng | Một quyết định hợp lệ nếu vai trò và bằng chứng đáp ứng | Mọi điều kiện khôi phục khác đã hoàn tất |

Một email đã phát thành công không phải bằng chứng đồng thuận. Việc nhà cung cấp báo có lượt mở cũng không đáng được coi là xác minh danh tính; trình xem trước hoặc phần mềm bảo vệ thư có thể tương tác với nội dung.

Nếu có liên kết báo cáo, liên kết phải có phạm vi hẹp. Nó không được trực tiếp thay mật khẩu, thu hồi mọi session hoặc hủy mọi phương thức xác thực chỉ bằng một GET. Trang xác nhận và hành động tiếp theo cần kiểm tra quyền hoặc capability đúng mục đích.

Chức năng báo cáo cũng cần chống lạm dụng. Một kẻ biết hoặc lấy được liên kết cảnh báo không được dùng nó để khóa tài khoản vô thời hạn. Tín hiệu từ liên hệ có thể đưa giao dịch vào xem xét theo policy; tác động cụ thể phải được thiết kế riêng.

Không coi im lặng sau một khoảng thời gian là phê duyệt mặc định chỉ vì thông báo đã được gửi. Nếu quy trình có bước chờ, điều kiện kết thúc bước đó phải được nêu rõ và không thay thế bằng chứng cần thiết.

## 9. Mô hình dữ liệu liên hệ và thông báo

Cần tách quan hệ người nhận khỏi từng lần gửi. Quan hệ trả lời “ai được nhận gì”; công việc gửi trả lời “sự kiện này đã được thông báo tới đâu”.

Một cấu trúc quan hệ minh họa:

~~~text
SecurityContactDesignation
  id
  tenantId
  subjectAccountId
  recipientPrincipalRef
  endpointRef
  version
  role = NOTIFICATION_ONLY
  allowedEventTypes
  disclosureProfile
  status
  endpointVerifiedAt
  acceptedAt
  activatedAt
  revokedAt
  establishedBy
  establishmentPolicyVersion
~~~

Trong đó:

- endpointRef trỏ tới kênh nhận được quản lý; không phải địa chỉ lấy từ request khôi phục hiện tại.
- version phân biệt các lần thay đổi quan hệ hoặc đích gửi.
- role và disclosureProfile giới hạn quyền nhận thông tin.
- establishedBy và policy version giúp giải thích nguồn gốc việc chỉ định.
- acceptedAt chỉ có ý nghĩa theo quy trình chấp nhận của sản phẩm; nó không phải thời điểm phê duyệt recovery request.

Một công việc gửi có thể chứa:

~~~json
{
  "notificationId": "f31d678f-c151-43dd-8143-6cb8de6e6521",
  "sourceEventId": "49b89e80-d09b-4bdd-a8cc-06cbdb23b07d",
  "notificationType": "SECURITY_CONTACT_RECOVERY_NOTICE",
  "designationId": "a952dd64-2466-4fd7-84f1-5b0a28112098",
  "designationVersion": 4,
  "channel": "EMAIL",
  "disclosureProfile": "DELEGATE_MINIMAL",
  "templateVersion": "security-contact-notice-v1",
  "policyVersion": "contact-notification-v2",
  "eventOccurredAt": "2026-11-24T09:10:00Z"
}
~~~

Các định danh trên chỉ là dữ liệu minh họa và không phải bearer token. Quyền đọc notification phải được kiểm tra độc lập với việc biết ID.

Có thể dùng khóa logic gồm source event, designation, designation version, channel và notification type để nhận biết cùng một ý định gửi. Việc đổi bản dịch hoặc template trong một lần retry không nên tự tạo thêm một thông báo nghiệp vụ mới.

Nếu cần gửi lại theo yêu cầu hợp lệ, hãy biểu diễn thành hành động gửi lại có căn cứ và giới hạn riêng. Không xóa dấu vết lần trước để biến mọi lần retry thành “lần gửi đầu tiên”.

## 10. Chuyển phát và thay đổi quyền trong lúc chờ

Có thể lưu sự kiện và ý định gửi trong một giao dịch cơ sở dữ liệu, rồi để worker chuyển phát sau commit. Mục đích là giữ được công việc cần làm nếu tiến trình dừng, đồng thời tránh gửi cho sự kiện đã rollback.

Một luồng minh họa:

~~~mermaid
sequenceDiagram
    participant R as Recovery Service
    participant D as Cơ sở dữ liệu
    participant W as Notification Worker
    participant P as Nhà cung cấp
    participant C as Liên hệ bảo mật
    R->>D: Commit sự kiện và quyết định người nhận
    W->>D: Nhận ý định gửi đã commit
    W->>D: Kiểm tra phiên bản quan hệ và phạm vi còn hiệu lực
    alt Người nhận còn đủ điều kiện
        W->>P: Gửi nội dung theo disclosure profile
        P-->>C: Chuyển phát
        P-->>W: Kết quả theo hợp đồng nhà cung cấp
        W->>D: Lưu trạng thái và tham chiếu chuyển phát
    else Quan hệ không còn đủ điều kiện
        W->>D: Ghi quyết định không gửi hoặc đánh giá lại
    end
~~~

Sơ đồ không bảo đảm nhà cung cấp chỉ gửi một lần. Nếu timeout xảy ra sau khi họ đã nhận yêu cầu, worker có thể chưa biết kết quả. Cần dùng định danh chuyển phát ổn định và cơ chế loại trùng của nhà cung cấp nếu có; nếu không, chính sách phải xử lý khả năng gửi trùng với số lần thử lại hữu hạn.

Nếu quan hệ bị thu hồi trong lúc job chờ, worker không được tiếp tục gửi hồ sơ nhạy cảm chỉ vì người nhận từng hợp lệ. Một thông báo tối thiểu về chính việc thu hồi, nếu policy yêu cầu, cần là loại thông báo và quyết định riêng.

Đối với nhóm bảo mật của tổ chức, thành viên nhóm có thể thay đổi. Cần xác định notification gửi tới một endpoint được tổ chức quản lý hay tới từng người có quyền tại một phiên bản cụ thể. Không để một người mới gia nhập nhóm tự nhận toàn bộ thông báo lịch sử đang chờ mà chưa kiểm tra phạm vi.

Ngay cả sau kiểm tra trước khi gửi vẫn có thể xảy ra thay đổi đồng thời. Vì vậy, nội dung nên ít dữ liệu, còn trang xem chi tiết phải kiểm tra lại quyền tại thời điểm mở. Dữ liệu đã gửi ra ngoài không thể được bảo vệ chỉ bằng việc thu hồi quyền trong cơ sở dữ liệu sau đó.

## 11. Chống lạm dụng và xử lý liên hệ không khả dụng

Một liên hệ bảo mật có thể nhận cảnh báo cho nhiều tài khoản. Nếu chỉ giới hạn theo account ID, kẻ tấn công vẫn có thể làm đầy cùng một hộp thư qua nhiều tài khoản khác nhau hoặc lạm dụng chức năng mời liên hệ.

Có thể phối hợp ngân sách theo nguồn, tài khoản, người nhận, tenant và loại sự kiện. Việc loại trùng cùng một job cần tách khỏi quyết định giảm tần suất nhiều sự kiện khác nhau.

Các lựa chọn cần được định nghĩa rõ:

- Giới hạn thư mời trước khi quan hệ được chấp nhận.
- Gộp cảnh báo khởi tạo có cùng tính chất khi phù hợp.
- Giữ chính sách riêng cho thay đổi yếu tố đã hoàn tất hoặc thay liên hệ bảo mật.
- Không để lưu lượng khởi tạo rác dùng hết ngân sách và che mọi cảnh báo quan trọng.
- Ghi nhận quyết định hạn chế gửi mà không làm lộ danh sách người nhận cho người khởi xướng.

Khi email bị trả lại, số điện thoại không còn hoạt động hoặc push endpoint hết hiệu lực, hệ thống cần phản ánh được độ tin cậy của kênh. Không tự chuyển sang địa chỉ mới do người đang khôi phục đưa ra.

Nếu có nhiều kênh đã được đăng ký phù hợp, policy có thể chọn cách chuyển tiếp hoặc leo thang đã định trước. Không có kênh khả dụng không đồng nghĩa với “không cần cảnh báo nữa”, cũng không tự cho phép bỏ điều kiện xác minh của luồng khôi phục.

Nếu quy trình bắt buộc phải có một bước thông báo hoặc xem xét trước khi tiếp tục, cần xác định rõ trạng thái chặn và cách xử lý ngoại lệ. Không dùng một lỗi nhà cung cấp để ngầm biến việc khôi phục thành đã được phê duyệt.

## 12. Lịch sử, quyền riêng tư và khả năng giải thích

Lịch sử cần đủ để trả lời:

- Sự kiện nào tạo ra thông báo?
- Người nhận được chọn theo quan hệ và phiên bản nào?
- Policy nào cho phép tiết lộ loại dữ liệu đó?
- Ý định gửi đã được lưu, nhà cung cấp đã chấp nhận hay có báo cáo chuyển phát?
- Có quyết định không gửi, thay thế hoặc hạn chế nào?
- Phản hồi nào đã được nhận và tác động nào thực sự được cho phép?

Tránh một cờ chung “notified = true” cho cả tài khoản nếu thực tế có nhiều người nhận. Nó không thể hiện được người nào bị lỗi, người nào đã mất quyền và ý nghĩa của trạng thái thành công.

Không cần sao chép nguyên nội dung thư, địa chỉ đầy đủ và mọi biến template vào tất cả log. Có thể giữ tham chiếu, phiên bản template, kết quả chuyển phát và dữ liệu tối thiểu theo chính sách lưu giữ. Nếu cần lưu nội dung để giải quyết tranh chấp, phải kiểm soát quyền đọc và thời hạn tương ứng.

Nhân viên hỗ trợ không mặc nhiên có quyền xem mọi liên hệ hoặc mở hồ sơ của người nhận. Quyền truy cập cần gắn với nhiệm vụ, tài khoản và tenant phù hợp. Lịch sử quan hệ cũng có thể tiết lộ quan hệ cá nhân nên cần được bảo vệ.

## 13. Tình huống vận dụng

Một người dùng mất điện thoại chứa MFA và passkey. Tài khoản đã có một email bảo mật phụ của chính họ và một người thân chỉ được nhận cảnh báo tối thiểu. Trong yêu cầu khôi phục, người dùng khai báo thêm một email mới để trao đổi.

Mô hình xử lý phù hợp cần thể hiện:

1. Email mới chưa tự thay thế hai quan hệ nhận cảnh báo đã được thiết lập.
2. Người thân nhận nội dung theo phạm vi NOTIFICATION_ONLY; thư không chứa OTP, hồ sơ xác minh hay nút thay MFA.
3. Chủ tài khoản có thể nhận thông tin chi tiết hơn nếu kênh và policy cho phép; nội dung vẫn không tiết lộ bí mật.
4. Người thân báo không nhận ra hoạt động là một tín hiệu xem xét, không tự trở thành lệnh khóa tài khoản.
5. Nếu người thân rút khỏi vai trò trước khi một job đang chờ được gửi, hệ thống đánh giá lại job và ghi rõ quyết định.
6. Khi thay MFA thực sự hoàn tất, cảnh báo dựa trên sự kiện hoàn tất tương ứng, không dựa vào việc đã gửi thư khởi tạo.
7. Dù các thông báo đều được nhà cung cấp chấp nhận, quyền khôi phục và việc tạo session vẫn phụ thuộc vào bằng chứng và policy của luồng chính.

Trong mô hình dữ liệu và xử lý, **quyền nhận thông tin**, **quyền đưa ra quyết định** và **quyền thực hiện tác vụ** phải được kiểm tra riêng. Một liên hệ bảo mật chỉ có quyền mà quan hệ đã thiết lập thực sự cấp cho họ.
