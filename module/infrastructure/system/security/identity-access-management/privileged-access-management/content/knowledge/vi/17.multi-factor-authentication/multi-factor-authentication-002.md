# MFA cho privileged session trong PAM

## 1. Mục tiêu của MFA ở cấp phiên đặc quyền

**Privileged session** là phiên tương tác có khả năng thực hiện tác vụ quản trị trên hệ thống, ứng dụng, cơ sở dữ liệu hoặc hạ tầng nhạy cảm. Một phiên có thể bắt đầu từ cổng PAM rồi đi qua gateway tới tài nguyên bằng một tài khoản kỹ thuật khác với danh tính đăng nhập của con người.

**Multi-factor authentication — MFA** yêu cầu kết hợp các yếu tố xác thực khác loại, chẳng hạn yếu tố biết và yếu tố sở hữu. Đối với phiên đặc quyền, mục tiêu không chỉ là bảo vệ lúc đăng nhập cổng PAM, mà còn bảo đảm việc mở hoặc tiếp tục sử dụng phiên đáp ứng yêu cầu xác thực của công việc đó.

Ví dụ, kỹ sư An đã đăng nhập cổng PAM vào buổi sáng. Đến chiều, An yêu cầu mở phiên quản trị production. Cờ “đã đăng nhập” không tự cho biết bằng chứng MFA trước đó còn đủ mới, dùng phương thức phù hợp hoặc có được policy cho phép dùng lại cho hành động này hay không.

Thiết kế cần trả lời:

- Ai được xác thực và bằng phương thức nào?
- Bằng chứng xác thực được kiểm tra ở đâu?
- Bằng chứng đó còn hiệu lực cho việc mở phiên cụ thể không?
- Người đã xác thực được cấp quyền gì, tới target nào và trong bao lâu?
- Khi phiên mất kết nối, được mở lại hoặc bị thu hồi, điều gì xảy ra?
- Có bằng chứng nào liên kết danh tính, MFA, grant, phiên và hoạt động tại đích?

MFA là một lớp của PAM. Nó cần đi cùng least privilege, JIT/JEA, quản lý credential, hạn chế đường truy cập, giám sát và thu hồi.

## 2. Phân biệt các lớp kiểm soát

| Lớp | Câu hỏi chính | Điều không thể suy ra chỉ từ lớp đó |
|---|---|---|
| Xác thực | Chủ thể là ai? | Chủ thể được quyền quản trị mọi tài nguyên |
| MFA | Quá trình xác thực đáp ứng tổ hợp yếu tố nào? | Thiết bị đầu cuối hoặc phiên sau đó không thể bị chiếm |
| Ủy quyền | Chủ thể được làm gì trên target nào? | Đường mạng và quyền tại đích đã được giới hạn đúng |
| Cấp quyền JIT | Quyền được kích hoạt khi nào và bao lâu? | Mọi phiên đang mở tự dừng khi grant hết hạn |
| JEA | Những tác vụ nào thực sự được phép? | Mọi hành động đều có đủ bằng chứng |
| Credential | Danh tính tại đích được xác thực bằng gì? | Người dùng không còn cách dùng credential ngoài PAM |
| Quản lý phiên | Phiên được mở, tiếp tục, giám sát và kết thúc ra sao? | Mọi tác vụ nền tại đích đã dừng khi gateway ngắt |

Hai bước nhập thông tin chưa chắc tạo thành MFA. Mật khẩu và câu hỏi bí mật đều thuộc nhóm thông tin biết. Ngược lại, một thiết bị xác thực có thể kết hợp nhiều yếu tố trong cùng một lần tương tác nếu thiết kế và kết quả xác minh đáp ứng yêu cầu đó.

Cũng cần phân biệt **xác thực người yêu cầu** với **xác thực tài khoản tại đích**. Người dùng có thể làm MFA với nguồn danh tính, còn gateway dùng credential từ vault để đăng nhập target. Liên kết giữa hai danh tính phải được giữ trong bằng chứng của phiên.

## 3. Mô hình tham chiếu

~~~mermaid
sequenceDiagram
    participant U as Quản trị viên
    participant P as PAM
    participant I as Nguồn xác thực
    participant G as Gateway phiên
    participant V as Vault hoặc broker
    participant T as Target
    U->>P: Yêu cầu phiên với target và role
    P->>P: Kiểm tra entitlement và policy
    P->>I: Yêu cầu xác thực hoặc step-up nếu cần
    I->>U: Tương tác xác thực theo phương thức
    U->>I: Hoàn thành tương tác
    I-->>P: Kết quả có thể xác minh
    P->>P: Kiểm tra danh tính, phương thức, độ mới và yêu cầu
    P->>G: Quyền mở phiên có phạm vi và thời hạn
    G->>V: Lấy credential theo quyền được cấp
    V-->>G: Credential hoặc khả năng xác thực tới đích
    G->>T: Kết nối tới target đã xác minh
    G-->>P: Kết quả mở phiên và định danh liên quan
~~~

Đây là mô hình logic, không yêu cầu mọi triển khai có cùng luồng. PAM có thể tự thực hiện MFA, liên kết với nguồn danh tính hoặc dùng một dịch vụ xác thực chuyên biệt.

Trình tự cần giữ được các ranh giới:

1. Yêu cầu phiên có chủ thể, target và role rõ ràng.
2. Chỉ chấp nhận bằng chứng xác thực từ nguồn tin cậy theo policy.
3. MFA thành công không bỏ qua kiểm tra quyền.
4. Gateway nhận quyền mở đúng phiên, thay vì được phép tự chọn mọi đích.
5. Credential chỉ được cấp theo luồng đã được ủy quyền.
6. Log giữ liên kết từ danh tính con người tới tài khoản hiệu lực tại đích.

Nếu kiến trúc cấp một credential trung gian trước khi MFA hoàn tất, phải bảo đảm credential đó chưa thể dùng để vượt cổng kiểm soát. Không để thứ tự xử lý tạo ra một đường sử dụng quyền trước khi điều kiện bắt buộc đạt.

## 4. Những thời điểm cần đánh giá MFA

### 4.1. Đăng nhập cổng PAM

MFA tại điểm vào bảo vệ khả năng truy cập cổng và tài khoản PAM. Đây có thể là điều kiện nền, nhưng policy vẫn cần quyết định mức xác thực này dùng được cho những thao tác nào.

Một phiên SSO dài hạn không tự tương đương với xác thực mới cho một thao tác đặc quyền nhạy cảm.

### 4.2. Mở một phiên tới target

Tại thời điểm mở, PAM cần xác minh bằng chứng MFA phù hợp với chủ thể, hành động và rủi ro theo policy.

Hệ thống có thể yêu cầu xác thực mới hoặc dùng lại bằng chứng đủ mới, đủ mạnh và được phép tái sử dụng. Không phải mọi phiên đều bắt buộc có một lần nhắc MFA riêng; điều đó phụ thuộc yêu cầu đã xác định.

### 4.3. Nâng quyền hoặc mở chức năng nhạy cảm

Một phiên chẩn đoán chuyển sang thay đổi cấu hình, mở quyền quản trị khác hoặc xuất credential có thể làm thay đổi yêu cầu xác thực và phê duyệt.

Step-up chỉ tăng mức xác thực. Nó không tự cấp thêm quyền, không tự thay role tại đích và không thay phê duyệt bắt buộc.

Nếu gateway không thể kiểm soát thao tác bên trong giao thức, không nên tuyên bố đã buộc MFA cho từng lệnh chỉ từ khả năng yêu cầu MFA trước khi mở phiên.

### 4.4. Tiếp tục phiên

Reconnect, resume, mở lại tab và chuyển thiết bị có thể có semantics khác nhau:

- Một kết nối truyền tải mới có thể quay lại cùng phiên tại đích.
- Một phiên gateway mới có thể gắn lại desktop cũ.
- Một tab mới có thể dùng lại cookie hoặc quyền mở phiên đang tồn tại.
- Một đường reconnect có thể sử dụng token riêng.

Cần đánh giá liệu hành động tiếp tục có đáp ứng policy hiện tại, còn cùng chủ thể và có cần xác thực lại không. Không dùng nhãn “resume” để mặc định bỏ qua mọi kiểm tra.

## 5. Chọn phương thức theo đặc tính thực tế

### 5.1. Yếu tố và phương thức không phải một khái niệm

Các nhóm yếu tố thường được diễn giải là thông tin biết, vật sở hữu và đặc điểm sinh học. Phương thức cụ thể sử dụng các yếu tố đó theo một giao thức và mô hình tin cậy.

Ví dụ:

| Phương thức | Điều cần xem xét cho phiên đặc quyền |
|---|---|
| Mật khẩu kết hợp mã OTP | Khả năng bị lừa cung cấp mã và sử dụng mã trong thời gian còn hiệu lực |
| Push xác nhận | Rủi ro xác nhận nhầm, yêu cầu không mong đợi và thông tin ngữ cảnh |
| Thiết bị hoặc cơ chế khóa công khai gắn với bên xác minh | Ràng buộc giao thức, user verification và vòng đời khóa |
| Cơ chế sinh trắc học cục bộ | Cách nó kích hoạt authenticator và bằng chứng bên xác minh thực sự nhận được |

Không suy từ một nhãn giao diện như “biometric”, “passkey” hoặc “security key” rằng mọi triển khai đều có cùng mức bảo đảm.

### 5.2. OTP và push cần nhìn đúng giới hạn

OTP có thể giúp giảm việc chỉ cần biết mật khẩu, nhưng một luồng OTP thông thường có thể bị lừa chuyển mã tới bên khác. Push có thể bị lợi dụng bằng việc gửi nhiều yêu cầu hoặc tạo ngữ cảnh khiến người dùng xác nhận nhầm.

Thông tin rõ về yêu cầu và các biện pháp như đối chiếu số có thể giảm một số rủi ro xác nhận nhầm. Chúng không tự biến mọi luồng push thành phương thức chống phishing theo giao thức.

Người dùng cần có cách từ chối và báo cáo yêu cầu không do mình khởi tạo. Hệ thống cũng cần giới hạn tần suất và phát hiện mẫu bất thường theo khả năng.

### 5.3. Phương thức chống phishing và xác minh người dùng

Một số giao thức khóa công khai ràng buộc phản hồi với bên xác minh hợp lệ, giúp chống việc chuyển tiếp bằng chứng xác thực sang một bên giả mạo. Cần xác minh cấu hình và thuộc tính mà nền tảng thực sự kiểm tra.

Cũng cần phân biệt sự hiện diện với xác minh người dùng. Một thao tác chạm để chứng minh người dùng đang tương tác không mặc nhiên chứng minh đã có PIN hoặc sinh trắc học theo yêu cầu.

Với passkey hoặc khóa có thể đồng bộ, cần đánh giá bảo vệ tài khoản đồng bộ, thiết bị được thêm, quy trình phục hồi và điều kiện sử dụng. Với khóa gắn thiết bị, cần quản lý cấp phát, mất thiết bị và khóa dự phòng.

Mục tiêu là chọn đặc tính đáp ứng policy, không chỉ chọn tên một công nghệ.

### 5.4. MFA không sửa mọi vấn đề của endpoint

Thiết bị đầu cuối đã bị kiểm soát có thể làm lộ dữ liệu, thay đổi tương tác hoặc chiếm phiên sau khi người dùng hoàn tất MFA.

Do đó, kiểm soát endpoint, hạn chế dữ liệu, phiên ngắn và quyền hẹp vẫn có vai trò. MFA mạnh không tự làm thiết bị người dùng trở thành môi trường quản trị an toàn.

## 6. Bằng chứng MFA phải được kiểm tra từ nguồn tin cậy

### 6.1. Không nhận cờ do client tự khai

Một tham số do trình duyệt gửi như “mfa_passed=true” không phải bằng chứng đủ. PAM cần dùng kết quả từ cơ chế có thể xác minh theo giao thức và cấu hình tin cậy.

Tùy tích hợp, các kiểm tra có thể gồm:

- Nguồn phát hành và bên nhận dự kiến.
- Tính xác thực, tính toàn vẹn và thời hạn của thông điệp.
- Chủ thể được xác thực.
- Liên kết với yêu cầu xác thực đã khởi tạo.
- Phương thức hoặc mức xác thực được báo cáo.
- Thời điểm thực hiện xác thực phù hợp.
- Điều kiện chống dùng lại và các ràng buộc của giao thức.

Không tự triển khai một bộ xác minh rút gọn chỉ từ danh sách này. Cần dùng khả năng tích hợp được hỗ trợ và cấu hình theo giao thức cụ thể.

### 6.2. Thời điểm cấp token không luôn là thời điểm MFA

Một token mới có thể được tạo từ một phiên SSO cũ. Việc token vừa được phát hành không tự chứng minh người dùng vừa thực hiện MFA.

PAM cần hiểu semantics của dữ liệu thời gian và phương thức do nguồn xác thực cung cấp. Nếu không xác minh được bằng chứng đủ mới, không tự đổi “không biết” thành “đã đạt”.

### 6.3. Nhãn mức xác thực cần có thỏa thuận

Hai hệ thống có thể dùng nhãn hoặc mã phương thức khác nhau. Cần xác định chính xác bằng chứng nào được chấp nhận cho từng loại phiên và kiểm tra cách nguồn danh tính tạo bằng chứng đó.

Nếu một nguồn phát hành có nhiều luồng đăng nhập hoặc fallback, phải bảo đảm không có luồng yếu hơn vẫn được báo cáo như đã đáp ứng cùng một yêu cầu bảo mật.

Không ánh xạ mọi kết quả xác thực thành “MFA mạnh” chỉ vì kết quả có một trường mang tên liên quan tới MFA.

## 7. Độ mới, phạm vi sử dụng và step-up

### 7.1. Tách các loại thời gian

Một thiết kế có thể có nhiều giới hạn độc lập:

| Giới hạn | Ý nghĩa |
|---|---|
| Tuổi tối đa của bằng chứng MFA | Bằng chứng xác thực cũ đến đâu còn được dùng cho hành động |
| Hạn của quyền mở phiên | Khoảng mà người dùng được phép khởi tạo phiên |
| Cửa sổ truy cập | Thời gian công việc được phép diễn ra |
| Thời lượng tuyệt đối của phiên | Giới hạn tổng thời gian phiên theo policy |
| Idle timeout | Giới hạn không hoạt động theo định nghĩa của nền tảng |
| Hạn của token hoặc cookie | Vòng đời một đối tượng kỹ thuật |

Các giới hạn này không thay thế nhau. Token chưa hết hạn có thể chứa bằng chứng xác thực quá cũ cho thao tác nhạy cảm. Phiên còn hoạt động cũng có thể đã vượt cửa sổ công việc nếu các lớp không phối hợp.

### 7.2. Ví dụ về policy độ mới

Giả sử tổ chức quy định, riêng cho một nhóm phiên production:

- Bằng chứng MFA dùng để mở phiên phải không quá 5 phút.
- Quyền mở phiên chỉ dùng một lần trong 2 phút.
- Phiên có thời lượng tối đa 30 phút và không vượt cửa sổ đã duyệt.
- Resume sau một số điều kiện nhất định phải được đánh giá lại.

Đây là số liệu minh họa, không phải giá trị chuẩn cho mọi môi trường.

Nếu bằng chứng đã 20 phút, PAM yêu cầu step-up theo phương thức được chấp nhận. Nếu người dùng vừa đáp ứng điều kiện 1 phút trước và policy cho dùng lại, hệ thống có thể không cần nhắc lại.

Thời điểm hết hiệu lực thực tế phải kết hợp các giới hạn áp dụng. Không đặt lại thời lượng tuyệt đối của phiên mỗi lần reconnect nếu policy không cho phép kéo dài như vậy.

### 7.3. Ràng buộc kết quả với đúng yêu cầu

Khi có step-up cho một lần mở phiên, kết quả cần được liên kết với đúng chủ thể và yêu cầu theo cơ chế của hệ thống.

Sau xác thực, người dùng không được tự đổi target, role hoặc account bằng cách sửa tham số rồi dùng kết quả cho một yêu cầu ngoài phạm vi.

Việc hiển thị target giúp người dùng nhận biết ngữ cảnh, nhưng không tự chứng minh thiết bị xác thực đã ký xác nhận nội dung giao dịch. Cần phân biệt thông tin hiển thị với ràng buộc được giao thức thực sự bảo vệ.

## 8. Policy minh họa cho phiên production

~~~yaml
# Mã giả mô tả ý định, không phải cấu hình sản phẩm.
policy:
  id: privileged-production-session-example
  applies_to:
    subject_type: human
    target_group: approved-production-targets
    action: open_privileged_session

  authorization:
    require_current_entitlement: true
    require_approvals_if_applicable: true
    role: approved_task_role

  authentication:
    accepted_profile: verified_privileged_mfa_profile
    max_evidence_age_seconds: 300
    require_trusted_issuer: true
    bind_to_current_subject: true
    step_up_when_insufficient: true

  launch_permission:
    lifetime_seconds: 120
    uses: 1
    bind_target_and_role: true

  session:
    max_duration_seconds: 1800
    cannot_outlive_approved_window: true
    resume_requires_policy_check: true

  credential:
    source: approved_vault_or_broker
    export_allowed: false

  evidence:
    link_authentication_grant_and_session: true
~~~

Các trường trên chỉ mô tả ý định cần được chuyển sang khả năng thực tế của PAM, nguồn xác thực, gateway và target.

Một cấu hình có tên “require_mfa” chưa đủ để chứng minh tất cả hành vi trên. Cần xác định thuộc tính nào được kiểm tra, ở đâu, với semantics gì và xử lý thế nào khi thiếu bằng chứng.

Policy về độ mới cũng cần hiểu thời gian, độ lệch đồng hồ được chấp nhận và cách xử lý dữ liệu bất hợp lý theo hệ thống. Không âm thầm chấp nhận thời điểm ở tương lai hoặc dữ liệu không xác định như bằng chứng luôn mới.

## 9. Luồng xử lý an toàn ở thời điểm mở phiên

Một luồng logic có thể được diễn giải như sau:

~~~text
Nhận yêu cầu mở phiên với danh tính đã được thiết lập.

1. Kiểm tra target và role thuộc phạm vi được yêu cầu.
2. Kiểm tra entitlement, phê duyệt và cửa sổ theo policy.
3. Đánh giá bằng chứng xác thực hiện có.
4. Nếu thiếu điều kiện, yêu cầu step-up được hỗ trợ.
5. Xác minh kết quả và liên kết với đúng yêu cầu.
6. Kiểm tra lại các điều kiện có thể đã thay đổi.
7. Phát quyền mở phiên có phạm vi và thời hạn.
8. Gateway xác minh quyền, target và điều kiện liên quan.
9. Lấy credential, xác minh đích và mở phiên.
10. Ghi kết quả cùng các ID để đối chiếu.
~~~

Đây không phải mã triển khai. Cơ chế thật cần xử lý giao dịch, thay đổi đồng thời, retry và lỗi từng chặng.

Ví dụ, một yêu cầu bị hủy trong lúc người dùng thực hiện MFA không được tự quay lại trạng thái được cấp chỉ vì MFA sau đó thành công. Tương tự, entitlement bị thu hồi giữa step-up và mở phiên phải được xử lý theo policy hiện hành.

Các phản hồi trùng lặp cần có cách nhận diện. Retry không được tạo thêm phiên hoặc grant ngoài phạm vi dự kiến. Một quyền mở phiên đã dùng cần được quản lý đúng semantics, đồng thời không làm mất khả năng xác định kết quả nếu thao tác mở gặp lỗi.

## 10. Áp dụng với SSH, RDP và web quản trị

### 10.1. SSH qua gateway

PAM có thể yêu cầu MFA trước khi cấp quyền dùng gateway. Gateway dùng credential hoặc chứng thư theo thiết kế để xác thực tới target.

Cần kiểm tra các đường:

- SSH trực tiếp ngoài gateway.
- Kết nối lại bằng credential hoặc chứng thư đã được cấp.
- Kênh forwarding, truyền file và các chức năng bổ sung.
- Phiên ở target còn tồn tại sau khi kết nối bị ngắt.

Không cần buộc người dùng nhập OTP vào mọi nơi nếu kiến trúc đã có một điểm MFA phù hợp và được thực thi. Nhưng cũng không được coi MFA tại gateway bao phủ kết nối trực tiếp mà gateway không nhìn thấy.

### 10.2. RDP hoặc desktop đặc quyền

Một desktop có thể bị disconnect mà chưa logoff. Người dùng quay lại có thể được gắn vào cùng phiên hệ điều hành.

Cần xác định vai trò của MFA tại cổng, gateway, reconnect và cơ chế khóa của desktop. Khóa màn hình hoặc xác thực cục bộ có thể bảo vệ một lớp, nhưng không mặc nhiên là bằng chứng MFA mà PAM có thể chấp nhận cho việc mở lại phiên.

Không truyền quyền resume chỉ bằng một liên kết có thể dùng lại không được kiểm soát. Khả năng tiếp tục cần gắn với danh tính và điều kiện policy phù hợp.

### 10.3. Web quản trị

Web proxy hoặc remote browser có thể giúp quản lý đường vào và credential. Tuy nhiên, cookie hoặc phiên của ứng dụng đích vẫn có vòng đời riêng.

Đóng tab PAM không tự chứng minh cookie tại đích đã bị thu hồi. Nếu cookie hoặc token bị lấy ra ngoài đường proxy, cần hiểu nó còn có thể sử dụng ở đâu.

MFA cho cổng PAM không tự thay MFA hoặc ủy quyền của ứng dụng đích nếu kiến trúc yêu cầu thêm các lớp đó. Cần thiết kế luồng phối hợp thay vì bỏ một lớp chỉ để giảm số lần nhắc người dùng.

## 11. Credential checkout khác với phiên được môi giới

Một số workflow cho người dùng nhận secret để dùng bằng công cụ riêng. MFA trước checkout giúp kiểm soát thời điểm nhận secret, nhưng sau đó credential có thể được dùng ngoài phiên PAM nếu các lớp khác cho phép.

Do đó, cần phân biệt:

| Mô hình | Phạm vi cần đánh giá |
|---|---|
| Gateway giữ secret và môi giới phiên | Quyền dùng secret của gateway, đường tới target, quan sát phiên |
| Người dùng nhận secret | Thời gian sử dụng, nơi sử dụng, khả năng sao chép và rotation |
| Credential hoặc chứng thư ngắn hạn | Phạm vi, hạn dùng, cơ chế thu hồi và phiên đã mở |
| Danh tính liên kết tới target | Quyền hiệu lực, vòng đời token và khả năng ràng buộc phiên |

Không thể dùng log “MFA trước checkout thành công” để khẳng định mọi lần sử dụng credential sau đó đều có MFA mới.

Rotation, hết hạn credential và kết thúc phiên là các cơ chế riêng. Credential hết hiệu lực có thể ngăn xác thực mới nhưng không nhất thiết làm phiên đang mở dừng ngay.

## 12. Chiếm phiên và giới hạn của MFA

### 12.1. MFA mạnh vẫn cần bảo vệ session artifact

Sau xác thực, hệ thống thường có cookie, token, quyền mở phiên hoặc đối tượng tương đương. Một số đối tượng có thể cho phép người sở hữu tiếp tục thao tác mà không cần thực hiện lại các yếu tố ban đầu.

Cần bảo vệ chúng theo khả năng nền tảng:

- Không đưa secret hoặc quyền mở phiên vào log không cần thiết.
- Hạn chế phạm vi và thời hạn.
- Kiểm soát việc dùng lại hoặc chuyển sang thiết bị khác theo thiết kế.
- Bảo vệ truyền tải và nơi lưu trữ.
- Thu hồi hoặc vô hiệu theo sự kiện liên quan.
- Phát hiện hoạt động bất thường và lưu bằng chứng.

Không mặc định mọi token đều có thể ràng buộc mạnh với thiết bị hoặc kênh. Nếu nền tảng không hỗ trợ, phải ghi đúng giới hạn.

### 12.2. Xác thực lại không khôi phục trạng thái an toàn đã mất

Nếu endpoint đang bị kiểm soát, một lần MFA mới có thể vẫn diễn ra trong môi trường bị ảnh hưởng. Nếu target đã bị sửa cấu hình, MFA mới không đảo ngược thay đổi đó.

Khi có dấu hiệu chiếm phiên, cần xem xét danh tính, endpoint, session artifact, quyền, credential và target theo quy trình ứng phó. Không chỉ yêu cầu người dùng nhập MFA lại rồi kết luận sự cố đã được xử lý.

### 12.3. Thu hồi nhiều lớp

Khi cần dừng truy cập, có thể phải phối hợp:

1. Chặn cấp phiên mới.
2. Thu hồi entitlement hoặc grant liên quan.
3. Vô hiệu quyền mở phiên chưa dùng.
4. Kết thúc tương tác ở gateway.
5. Xử lý phiên hoặc tác vụ tại đích theo khả năng.
6. Xử lý credential, token hoặc cookie đã phát hành.
7. Kiểm tra kết quả và phần còn chờ xác nhận.

Đánh dấu một tài khoản “MFA reset” không tự thực hiện mọi bước trên.

## 13. Đăng ký, thay thiết bị và phục hồi MFA

Chất lượng MFA phụ thuộc cả vòng đời authenticator. Một quy trình đăng ký hoặc phục hồi yếu có thể làm suy giảm bảo vệ của phương thức đăng nhập chính.

Cần xác định:

- Ai được thêm, thay hoặc xóa phương thức xác thực.
- Cách xác minh danh tính khi thực hiện thay đổi.
- Điều kiện dùng phương thức dự phòng.
- Cách thông báo và phát hiện thay đổi không mong đợi.
- Cách xử lý thiết bị bị mất.
- Liên hệ giữa thay đổi authenticator và các phiên đang hoạt động.

Phục hồi tài khoản là một workflow đặc quyền, không chỉ một tác vụ hỗ trợ thông thường. Nếu người hỗ trợ có thể bỏ yêu cầu MFA hoặc thêm phương thức mới, quyền đó cần có phạm vi, thẩm quyền và bằng chứng phù hợp.

Fallback yếu hơn không nên âm thầm được báo cáo là đáp ứng cùng một profile bảo mật nếu thực tế không đạt yêu cầu đó. Nếu policy cho ngoại lệ, cần ghi đúng ngoại lệ và thời hạn.

Không dùng một tài khoản con người với mã OTP chia sẻ cho cả đội để vận hành automation. Workload cần danh tính và cơ chế xác thực phù hợp vòng đời máy; việc không dùng MFA tương tác cho workload không phải lý do bỏ kiểm soát truy cập đặc quyền của nó.

## 14. Sự cố nguồn MFA và truy cập khẩn cấp

Khi nguồn MFA không hoạt động, cần có hành vi đã được xác định cho:

- Yêu cầu mở phiên mới.
- Quyền mở phiên đã cấp nhưng chưa dùng.
- Phiên đang hoạt động.
- Reconnect hoặc step-up.
- Truy cập khẩn cấp.

Không mặc định mọi phiên phải dừng ngay, cũng không mặc định mọi yêu cầu mới được bỏ MFA. Hành vi phụ thuộc kiến trúc, loại bằng chứng còn hiệu lực và policy của từng luồng.

Nếu có break-glass, cần danh tính chịu trách nhiệm, phạm vi tối thiểu, thời gian, credential được bảo vệ và bằng chứng phù hợp với điều kiện sự cố. Sau sử dụng cần rà soát hoạt động, đóng quyền tạm và xử lý credential theo thiết kế.

Một phiên được mở theo ngoại lệ khẩn cấp phải được ghi nhận đúng. Không gắn nhãn “MFA đạt” nếu không thực sự có bằng chứng tương ứng.

## 15. Ví dụ xuyên suốt: mở phiên chẩn đoán production

### 15.1. Bối cảnh

An cần chẩn đoán máy chủ app-prod-a trong cửa sổ hỗ trợ đã duyệt. Role chỉ cho tác vụ chẩn đoán đã kiểm chứng. Gateway dùng credential từ vault và không xuất secret cho An.

Policy minh họa yêu cầu profile MFA được chấp nhận, bằng chứng không quá 5 phút tại thời điểm mở, phiên tối đa 30 phút và không vượt cửa sổ công việc.

### 15.2. Bằng chứng cũ

An đang có phiên SSO từ buổi sáng. Nguồn danh tính có thể cấp phản hồi mới mà không yêu cầu An tương tác lại.

PAM kiểm tra dữ liệu xác thực và nhận thấy chưa có bằng chứng đủ mới cho hành động mở phiên production. Hệ thống thực hiện step-up được hỗ trợ thay vì chỉ nhìn thời điểm phản hồi được tạo.

### 15.3. Hoàn thành step-up

An xác thực bằng phương thức được policy chấp nhận. PAM kiểm tra kết quả từ nguồn tin cậy, đúng chủ thể và đúng yêu cầu.

Trong lúc đó, target và role vẫn phải khớp yêu cầu. Nếu An đổi sang app-prod-b hoặc yêu cầu role toàn quyền, quyết định cấp cần được đánh giá lại theo phạm vi mới; MFA thành công không tự cho phép thay đổi đó.

### 15.4. Mở và tiếp tục phiên

Gateway nhận quyền mở app-prod-a với role đã định, lấy credential và xác minh target trước khi kết nối. Log liên kết request, sự kiện xác thực, grant, gateway session và tài khoản tại đích.

Nếu đường truyền mất sau 10 phút, thao tác resume được kiểm tra theo policy. Reconnect không tự kéo thời lượng tối đa thêm 30 phút.

Nếu An đã mất quyền hoặc yêu cầu bị thu hồi, việc còn một desktop hay shell tại đích không được dùng làm lý do bỏ qua điều kiện tiếp tục.

### 15.5. Kết thúc

Hết cửa sổ, hệ thống xử lý grant và phiên theo thiết kế. Nếu gateway đã ngắt tương tác nhưng trạng thái tại đích chưa xác nhận được, hồ sơ phải giữ rõ phần đó.

Credential và các token liên quan được xử lý theo vòng đời riêng. Không suy rằng hoàn thành MFA và đóng tab đã chứng minh toàn bộ truy cập đặc quyền kết thúc.

## 16. Bằng chứng và chỉ số vận hành

### 16.1. Bằng chứng cần liên kết

Một hồ sơ phiên nên có khả năng đối chiếu:

~~~text
Danh tính con người
  → yêu cầu mở phiên
  → nguồn và kết quả xác thực
  → profile được chấp nhận, độ mới và quyết định policy
  → grant hoặc quyền mở phiên
  → gateway session và target
  → tài khoản hiệu lực tại đích
  → hoạt động quan sát được
  → reconnect, hết hạn và thu hồi.
~~~

Không lưu mã OTP, private key, recovery code hoặc token đầy đủ vào log để làm bằng chứng. Ghi các định danh sự kiện và thuộc tính cần thiết với quyền truy cập phù hợp.

Cần ghi rõ “không xác định” nếu thiếu dữ liệu. Không dùng một cờ “MFA=true” làm bằng chứng duy nhất cho phương thức, thời điểm và phạm vi áp dụng.

### 16.2. Chỉ số có ý nghĩa

Có thể theo dõi:

- Phiên đặc quyền có liên kết được tới bằng chứng xác thực phù hợp.
- Phiên mở với bằng chứng quá cũ hoặc profile không đúng.
- Đường trực tiếp chưa thuộc phạm vi MFA của PAM.
- Số yêu cầu step-up bất thường hoặc bị người dùng từ chối.
- Reconnect không đáp ứng điều kiện policy.
- Ngoại lệ và truy cập khẩn cấp chưa được xử lý sau sử dụng.
- Thay đổi authenticator gắn với dấu hiệu truy cập bất thường.
- Khoảng cách giữa thu hồi và kết quả thực thi tại các lớp.

Tỷ lệ MFA thành công cao không tự chứng minh các phiên đều an toàn. Cần xem đúng mẫu số và phạm vi: nhóm phiên qua gateway khác với toàn bộ đường quản trị trong hạ tầng.

## 17. Kiểm chứng và xử lý lỗi

| Tình huống | Điều cần quan sát |
|---|---|
| Chỉ có mật khẩu khi policy yêu cầu MFA | Không mở phiên bằng bằng chứng chưa đủ |
| Client tự gửi cờ đã MFA | Không được chấp nhận như bằng chứng tin cậy |
| Token mới nhưng MFA cũ | Đánh giá theo semantics thời gian xác thực |
| Phương thức fallback không đạt profile | Không âm thầm coi là tương đương |
| Kết quả thuộc chủ thể khác | Không cấp cho yêu cầu hiện tại |
| Đổi target hoặc role sau step-up | Không vượt phạm vi bằng tham số đã sửa |
| Yêu cầu bị hủy trong lúc MFA | Không mở lại quyền chỉ vì phản hồi đến muộn |
| Phản hồi hoặc yêu cầu được retry | Không cấp trùng ngoài ý định |
| Quyền mở phiên hết hạn hoặc đã dùng | Xử lý đúng vòng đời đã định |
| Reconnect sau thu hồi | Không tiếp tục chỉ nhờ phiên cũ còn ở target |
| Đường SSH, RDP hoặc web trực tiếp | Không bị bỏ sót khỏi phạm vi kiểm soát |
| Nguồn MFA không hoạt động | Hành vi đúng policy và đường khẩn cấp đã thiết kế |
| Thay authenticator | Có bằng chứng và xử lý rủi ro liên quan |
| Gateway ngắt nhưng tác vụ nền còn chạy | Báo đúng kết quả từng lớp |

Khi mở phiên thất bại, cần tách lỗi xác thực, thiếu quyền, hết hạn phê duyệt, đường mạng, credential và xác minh target. Không tắt MFA chỉ vì thông báo kết nối chung chưa được phân loại.

Thử nghiệm cần dùng tài khoản và target trong phạm vi được phép. Không dùng OTP hoặc token thực trong tài liệu và log minh họa.

## 18. Những điểm cần áp dụng

MFA cho privileged session cần được thiết kế quanh hành động mở và tiếp tục phiên, thay vì chỉ quanh màn hình đăng nhập cổng PAM.

Một thiết kế có thể giải thích được phải chỉ ra bằng chứng nào được tin cậy, phương thức và độ mới nào được chấp nhận, quyết định gắn với phạm vi nào và lớp nào thực thi. Sau xác thực, quyền hẹp, vòng đời credential, bảo vệ session artifact và thu hồi vẫn phải hoạt động.

Để tự kiểm tra một thiết kế, hãy lần theo một yêu cầu từ danh tính con người tới tài khoản ở đích, rồi thử giải thích điều gì xảy ra khi bằng chứng cũ, target thay đổi, phiên reconnect hoặc chủ thể bị thu hồi. Phần nào chưa có cơ chế và bằng chứng thì cần được giữ rõ như một giới hạn cần xử lý.
