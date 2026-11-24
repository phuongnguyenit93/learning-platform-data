# Credential trong Authentication: bằng chứng xác thực và quản lý vòng đời an toàn

Một tài khoản IAM có thể được tạo từ hồ sơ nhân sự, liên kết với đúng nhân viên và được cấp đúng quyền. Nhưng để sử dụng tài khoản, người dùng hoặc ứng dụng phải **chứng minh mình đang kiểm soát danh tính được khai báo**. Bằng chứng và cơ chế dùng để chứng minh điều đó được gọi là **credential** (thông tin xác thực). Credential có thể là mật khẩu, khóa mật mã, passkey, chứng chỉ, API key hoặc token, tùy chủ thể và giao thức.

Credential nằm ở trung tâm của **Authentication (xác thực)** nhưng có vòng đời khác với hồ sơ danh tính, tài khoản và quyền truy cập. Một nhân viên nghỉ việc có thể đã bị khóa SSO nhưng vẫn sở hữu Personal Access Token (PAT) còn hoạt động ở ứng dụng bên ngoài. Ngược lại, thay đổi mật khẩu không nhất thiết làm những phiên truy cập đã phát hành hết hiệu lực. Vì vậy, IAM cần quản lý credential từ **đăng ký, phát hành, bảo vệ, sử dụng, thay thế, khôi phục đến thu hồi**.

Bài học thuộc chương **Authentication** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nghiên cứu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp và rà soát quyền đến thu hồi khi thay đổi vai trò. Nội dung liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và cách giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt **credential**, **authenticator**, **identity**, **account**, **authentication factor**, **session** và **entitlement**.
- Giải thích cách các loại credential chứng minh quyền kiểm soát danh tính, cùng rủi ro lộ lọt hoặc bị giả mạo.
- So sánh password, OTP, push, passkey/WebAuthn, chứng chỉ và credential cho máy ở mức thiết kế IAM.
- Mô tả cách phát hành, ràng buộc, thay thế, khôi phục và thu hồi credential theo các sự kiện Joiner–Mover–Leaver.
- Thiết kế nguyên tắc lưu trữ bí mật, MFA, chống phishing, xử lý phiên/token còn sống và lưu bằng chứng kiểm toán.

## 1. Credential là gì?

Trong xác thực, **credential** là đối tượng hoặc thông tin được một bên sử dụng để cung cấp bằng chứng về quyền kiểm soát một danh tính hoặc để tham gia giao thức xác thực. Ý nghĩa chính xác có thể khác theo giao thức: có hệ thống dùng thuật ngữ credential cho khóa bí mật, có hệ thống dùng cho cặp khóa, chứng chỉ hoặc một đối tượng được đăng ký với nhà cung cấp danh tính.

Để hiểu rõ, hãy tách ba vai trò:

1. **Claimant**: người dùng hoặc workload đang tuyên bố mình là một danh tính.
2. **Verifier**: thành phần kiểm tra bằng chứng xác thực, thường ở IdP hoặc dịch vụ xác thực.
3. **Authenticator**: phương tiện mà claimant kiểm soát để tạo hoặc cung cấp bằng chứng, chẳng hạn khóa bảo mật, ứng dụng tạo OTP hoặc thiết bị giữ private key.

Ví dụ, nhân viên Lan dùng một passkey để đăng nhập. Trình xác thực trên thiết bị giữ **private key** và tạo chữ ký cho thử thách do dịch vụ phát. Máy chủ có **public key** đã đăng ký để kiểm tra chữ ký. Dịch vụ không cần biết private key và không xác thực Lan chỉ vì email của Lan xuất hiện trên màn hình.

**Có credential hợp lệ không có nghĩa được phép truy cập mọi tài nguyên.** Sau bước xác thực, hệ thống vẫn phải kiểm tra trạng thái tài khoản, vai trò, thuộc tính, chính sách và quyền ở tài nguyên đích.

### Những thuật ngữ không nên đánh đồng

| Thuật ngữ | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Identity / subject** | Ai là chủ thể? | \`subjectId=person-1042\`. |
| **Account** | Chủ thể có đối tượng truy cập nào trong hệ thống? | Tài khoản IdP hoặc tài khoản SaaS. |
| **Authenticator** | Phương tiện nào tạo bằng chứng xác thực? | Security key, điện thoại giữ passkey, ứng dụng TOTP. |
| **Credential** | Thông tin/khóa/chứng chỉ nào được dùng trong giao thức? | Mật khẩu, khóa riêng, API key, chứng chỉ client. |
| **Authentication** | Bằng chứng có chứng minh quyền kiểm soát danh tính được khai báo không? | Kiểm tra mật khẩu và yếu tố thứ hai; kiểm tra chữ ký WebAuthn. |
| **Authorization** | Chủ thể đã xác thực được phép làm gì? | Cho phép đọc báo cáo theo role hoặc thuộc tính. |
| **Session / access token** | Trạng thái hoặc vật mang quyền sử dụng sau một lần xác thực/cấp phép? | Cookie phiên, OAuth access token. |
| **Entitlement** | Quyền được cấp là gì? | Quyền xem báo cáo, thành viên nhóm quản trị. |

Một **session cookie** hay access token là credential mang tính **bearer** khi chỉ cần trình ra là có thể sử dụng; nhưng việc cấp nó thường xảy ra *sau* một quá trình xác thực. Vì vậy cần quản lý cả credential dùng để đăng nhập **và** các token/phiên có thể tiếp tục truy cập sau đăng nhập.

## 2. Các yếu tố xác thực và loại credential

Các yếu tố xác thực thường được mô tả theo:

- **Something you know**: thông tin cần ghi nhớ, chẳng hạn mật khẩu hoặc PIN.
- **Something you have**: vật hoặc thiết bị nắm giữ khóa/chứng cứ, như security key, ứng dụng xác thực hoặc thiết bị giữ passkey.
- **Something you are**: đặc điểm sinh trắc dùng để xác minh người sử dụng thiết bị, như vân tay hoặc khuôn mặt.

**MFA (Multi-Factor Authentication)** yêu cầu bằng chứng từ những yếu tố độc lập thích hợp theo chính sách. Hai mật khẩu khác nhau không tự trở thành MFA chỉ vì phải nhập hai lần. Mã TOTP thường là yếu tố sở hữu, nhưng nếu seed bị đánh cắp và sao chép, kẻ tấn công có thể tạo mã như người dùng.

### So sánh các phương thức thường gặp

| Phương thức | Cách chứng minh | Điểm mạnh | Rủi ro và lưu ý |
| --- | --- | --- | --- |
| **Mật khẩu** | Chứng minh biết một bí mật dùng chung. | Phổ biến, dễ triển khai trong nhiều hệ thống. | Phishing, reuse, credential stuffing, dò đoán và lộ verifier. |
| **TOTP** | Mã một lần tính từ seed bí mật và thời gian. | Dùng được khi thiết bị không có kết nối Internet. | Seed có thể sao chép; mã có thể bị phishing theo thời gian thực; cần bảo vệ đồng hồ và seed. |
| **SMS/voice OTP** | Mã gửi qua số điện thoại. | Dễ tiếp cận. | SIM swap, chuyển hướng, lộ qua mạng viễn thông hoặc phishing; thường kém an toàn hơn phương thức chống phishing. |
| **Push approval** | Người dùng xác nhận một thử thách trên ứng dụng. | Thuận tiện; có thể bổ sung thông tin ngữ cảnh, number matching. | Fatigue/bombing và phê duyệt nhầm; tùy thiết kế có thể vẫn bị phishing. |
| **Passkey/WebAuthn** | Authenticator dùng private key ký thử thách gắn với relying party/origin. | Chống phishing theo cơ chế ràng buộc miền, không chia sẻ bí mật cho website. | Cần xử lý mất thiết bị, đồng bộ/khôi phục passkey và chính sách thiết bị phù hợp. |
| **Chứng chỉ client / mTLS** | Chứng minh sở hữu private key gắn với chứng chỉ. | Phù hợp máy, ứng dụng hoặc người dùng trong môi trường quản lý. | Vòng đời PKI, private key, hết hạn, trust và cơ chế thu hồi phải được kiểm soát. |
| **API key/PAT** | Trình một chuỗi bí mật hoặc token cho API. | Phổ biến với tích hợp và công cụ tự động. | Dễ bị sao chép/lộ, scope quá rộng, khó quản lý owner và hết hạn. |
| **Workload identity token** | Credential phát theo danh tính và ngữ cảnh workload. | Có thể giảm bí mật dài hạn, tăng khả năng xoay vòng tự động. | Phải kiểm soát issuer, audience, trust, thời gian sống và quyền workload. |

**Sinh trắc học không nhất thiết là credential được gửi tới máy chủ.** Trong nhiều triển khai passkey, Face ID/vân tay chỉ mở khóa việc sử dụng private key **cục bộ trên thiết bị**; máy chủ nhận chữ ký mật mã, không nhận mẫu vân tay/khuôn mặt. Sự phân biệt này quan trọng cho cả bảo mật và quyền riêng tư.

## 3. Credential được dùng để xác thực như thế nào?

### 3.1. Đăng nhập bằng mật khẩu

Luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Ứng dụng / trình duyệt
    participant I as IdP / verifier
    U->>C: Cung cấp danh tính và mật khẩu
    C->>I: Gửi dữ liệu xác thực qua kênh bảo vệ
    I->>I: Kiểm tra với password verifier được lưu an toàn
    alt Hợp lệ và chính sách yêu cầu MFA
        I-->>C: Yêu cầu yếu tố bổ sung
        C->>I: Phản hồi thử thách MFA
    end
    I-->>C: Kết quả xác thực hoặc từ chối
~~~

Máy chủ **không nên lưu mật khẩu dạng rõ** để so sánh trực tiếp. Hệ thống được thiết kế để lưu **password verifier** bằng thuật toán băm mật khẩu chậm, có salt riêng và tham số chi phí phù hợp, ví dụ Argon2id hoặc cơ chế được tiêu chuẩn và nền tảng hiện hành khuyến nghị. Mật khẩu cũng không nên bị ghi vào access log, APM trace, message queue hoặc bản sao debug.

Các biện pháp bổ sung: chặn mật khẩu phổ biến/đã lộ theo chính sách, rate limiting, phát hiện đăng nhập bất thường, MFA thích hợp, kênh TLS và quy trình khôi phục an toàn. Không nên chỉ dựa vào việc bắt đổi mật khẩu định kỳ như một biện pháp bảo vệ, đặc biệt khi không có bằng chứng bị lộ hoặc chính sách rủi ro tương ứng.

### 3.2. Đăng nhập bằng passkey/WebAuthn

WebAuthn sử dụng **mật mã khóa công khai**, không yêu cầu website nhận private key.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / client
    participant A as Authenticator
    participant I as IdP / relying party
    I-->>B: Challenge + RP ID + tùy chọn
    B->>A: Yêu cầu xác thực cho RP
    A->>U: Xác minh hiện diện / người dùng nếu chính sách yêu cầu
    A->>A: Ký challenge và dữ liệu được ràng buộc
    A-->>B: Assertion + credential ID + chữ ký
    B->>I: Gửi kết quả WebAuthn
    I->>I: Kiểm RP/origin, challenge, chữ ký, chính sách
    I-->>B: Xác thực thành công hoặc từ chối
~~~

Đặc điểm quan trọng:

1. Khi **đăng ký**, authenticator tạo hoặc dùng cặp khóa thích hợp; relying party lưu **public key** và metadata cần thiết.
2. Khi **xác thực**, relying party phát thử thách mới; authenticator ký dữ liệu có ràng buộc với RP/origin, giúp chống việc nhập credential vào website phishing.
3. Nếu chính sách yêu cầu **user verification**, authenticator kiểm tra PIN/sinh trắc hoặc cơ chế cục bộ tương đương trước khi dùng khóa.
4. Có **passkey gắn thiết bị** và **passkey được đồng bộ** bởi nhà cung cấp hệ sinh thái; chính sách rủi ro phải xem xét cơ chế đồng bộ, khôi phục và quản lý thiết bị.
5. Khi mất thiết bị, hệ thống cần quy trình phục hồi hoặc thêm authenticator khác với mức xác minh phù hợp; **đường recovery yếu có thể làm suy yếu xác thực mạnh**.

Passkey thường có khả năng chống phishing tốt hơn mật khẩu + mã OTP nhập tay. Tuy nhiên, không phải mọi deployment passkey đều đáp ứng cùng một yêu cầu quản trị: khóa được đồng bộ, thiết bị do công ty quản lý, user verification và thủ tục recovery phải được đánh giá theo chính sách.

## 4. Vòng đời của một credential

Credential không tồn tại mãi ở trạng thái “được cấp”. Nó có chuỗi chuyển trạng thái và các sự kiện cần kiểm soát.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Yêu cầu đăng ký
    PENDING --> ACTIVE: Xác minh và đăng ký thành công
    ACTIVE --> SUSPENDED: Nghi ngờ rủi ro / tạm ngưng
    SUSPENDED --> ACTIVE: Xác minh lại + phê duyệt
    ACTIVE --> REPLACED: Rotation / thay thiết bị
    ACTIVE --> REVOKED: Leaver / mất quyền / lộ bí mật
    SUSPENDED --> REVOKED: Xác nhận phải thu hồi
    REPLACED --> REVOKED: Vô hiệu credential cũ
    ACTIVE --> EXPIRED: Đến hạn
    EXPIRED --> [*]
    REVOKED --> [*]
~~~

Các trạng thái và chuyển đổi là **mô hình minh họa**; sản phẩm cụ thể có thể dùng tên khác. Mỗi lần kích hoạt lại phải dựa trên **điều kiện xác minh và chính sách hiện tại**, tránh một sự kiện cũ tự mở lại credential đã thu hồi.

### Quy trình theo pha

| Pha | Hoạt động | Điểm kiểm soát |
| --- | --- | --- |
| **Enrollment** | Xác minh danh tính và mối liên kết tài khoản; xác định phương thức sẽ đăng ký. | Chặn gắn credential của người A vào danh tính người B. |
| **Issuance / registration** | Tạo hoặc đăng ký credential; ràng buộc với subject/account và issuer. | Chủ thể được xác minh, phương thức phát hành bảo vệ khỏi chiếm đoạt. |
| **Activation** | Cho phép credential tham gia xác thực theo ngày/điều kiện. | Chờ Start date, trạng thái HRIS và phê duyệt cần thiết. |
| **Use** | Kiểm tra challenge, chữ ký, secret hoặc token; thiết lập session nếu hợp lệ. | Rate limiting, chống replay, chính sách MFA/reauthentication. |
| **Maintenance** | Rà soát, cập nhật metadata, thêm authenticator dự phòng, rotate khi cần. | Phát hiện key cũ, thiết bị không còn sở hữu, owner đã đổi. |
| **Recovery / replacement** | Thay password/passkey/thiết bị hoặc khôi phục sau mất credential. | Xác minh đủ mạnh, hạn chế social engineering và giữ audit trail. |
| **Suspension / revocation** | Khóa hoặc vô hiệu hóa credential do rủi ro, Mover, Leaver. | Xác minh trên IdP và các API/ứng dụng có đường truy cập riêng. |
| **Disposal** | Hủy bí mật, xóa bản sao còn hoạt động, giữ metadata audit theo lịch. | Không lưu credential dùng được chỉ để phục vụ điều tra. |

**Ghi nhớ:** mất quyền sử dụng **một credential** chưa chắc đã khóa **mọi credential** cùng tài khoản; ngược lại, khóa tài khoản **không phải lúc nào** làm mọi phiên/token cũ dừng tức thì. IAM phải xác định rõ phạm vi hiệu lực của từng thao tác.

## 5. Ràng buộc credential với đúng danh tính và tài khoản

Trước khi đăng ký một credential, IAM cần có chuỗi liên kết tin cậy:

~~~text
HRIS / nguồn có thẩm quyền
    -> Hồ sơ con người hoặc workload được xác minh
    -> subjectId ổn định
    -> Tài khoản IdP / ứng dụng được gắn với subjectId
    -> Authenticator / credential được đăng ký cho đúng tài khoản
    -> Chính sách xác thực và quyền hiện hành
~~~

Ví dụ dữ liệu quản lý **metadata** của một credential, không chứa bí mật:

~~~json
{
  "credentialId": "cred-8f21",
  "credentialType": "PASSKEY",
  "issuer": "corporate-idp",
  "subjectId": "person-1042",
  "accountId": "idp-account-721",
  "state": "ACTIVE",
  "createdAt": "2026-11-20T09:20:00Z",
  "lastVerifiedAt": "2026-11-23T02:00:00Z",
  "policyId": "workforce-authentication",
  "policyVersion": "5"
}
~~~

Đây là **schema quản trị minh họa**, không phải chuẩn chung cho mọi IdP. Với WebAuthn, lưu thêm thông tin đăng ký như credential ID và public key theo giao thức; metadata về authenticator, khả năng user verification hoặc trạng thái thiết bị chỉ dùng khi thực sự được hệ thống cung cấp và cần thiết.

Không dùng **họ tên hoặc email** làm khóa duy nhất liên kết credential. Email có thể bị đổi hoặc tái cấp; cần dùng ID ổn định, có namespace của issuer. Với tài khoản OIDC, ứng dụng thường nhận diện người dùng từ **cặp \`iss\` + \`sub\`**, không suy luận \`sub\` là ID chung giữa mọi nhà cung cấp danh tính.

### Một người nhiều credential là bình thường

Một Employee có thể đăng ký nhiều passkey trên thiết bị khác nhau, sử dụng MFA dự phòng và có tài khoản quản trị tách biệt. Mỗi credential cần được quản lý riêng về thiết bị/đích đăng ký, lần sử dụng, thời hạn hoặc trạng thái. Khi thay thiết bị, không xóa nhầm các credential vẫn được phép; khi Leaver, phải xử lý **toàn bộ credential và tài khoản liên quan**, kể cả tài khoản quản trị phụ.

## 6. Đăng ký credential an toàn cho Joiner

Khi HRIS xác nhận nhân viên mới, IAM có thể chuẩn bị danh tính và tài khoản trước Start date nhưng không nhất thiết cho đăng nhập ngay. **Credential enrollment** là bước dễ bị tấn công nếu người lạ có thể nhận link kích hoạt hoặc đăng ký authenticator thay nhân viên.

Một luồng Joiner tham khảo:

1. **Xác minh thông tin nguồn:** HRIS cung cấp đúng ID nhân sự, trạng thái quan hệ, Start date, người quản lý và nguồn có thẩm quyền.
2. **Giải quyết danh tính:** đối chiếu với person/engagement hiện có, tránh trùng tên, tái tuyển dụng bị gắn nhầm hoặc tài khoản cũ được cấp lại.
3. **Tạo tài khoản IdP ở trạng thái phù hợp:** có thể pre-provision và chờ tới ngày có hiệu lực; quyền preboarding, nếu có, cần giới hạn rõ.
4. **Xác minh người đăng ký:** sử dụng kênh đã kiểm chứng và bước identity proofing phù hợp mức rủi ro trước khi cho gắn authenticator.
5. **Đăng ký phương thức chính và dự phòng:** ưu tiên phương thức chống phishing cho quyền nhạy cảm khi có khả năng; thiết lập chính sách số lượng/loại authenticator dự phòng.
6. **Kích hoạt đúng thời điểm:** kiểm tra lại trạng thái HRIS, quy tắc MFA, chính sách điều kiện truy cập và các phê duyệt.
7. **Truy vết:** ghi sự kiện tạo tài khoản, credential đăng ký, người/hệ thống thực hiện, trạng thái xác minh và kết quả tại IdP.

### Tránh một số đường tấn công khi enrollment

| Rủi ro | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Link kích hoạt bị chuyển tiếp** | Người khác nhận email hướng dẫn đăng ký credential. | Kênh giao nhận đã xác minh, link sống ngắn, có ràng buộc người nhận và bước kiểm tra bổ sung. |
| **Gắn nhầm tài khoản** | Hai nhân viên cùng họ tên được cấp chung tài khoản. | Đối sánh bằng ID nguồn ổn định; trường hợp mơ hồ kiểm tra thủ công. |
| **Đăng ký authenticator lạ** | Attacker đã đăng nhập một phiên cũ và thêm passkey của mình. | Yêu cầu xác thực gần đây/step-up, thông báo và giám sát thao tác thêm authenticator. |
| **Mật khẩu ban đầu bị lộ** | Mật khẩu tạm gửi qua nhiều kênh hoặc còn hiệu lực lâu. | Cấp phát qua quy trình bảo vệ, hạn chế thời gian/sử dụng, buộc thiết lập credential do người dùng kiểm soát. |
| **MFA mạnh nhưng recovery yếu** | Helpdesk đổi authenticator chỉ qua cuộc gọi không đủ kiểm chứng. | Quy trình khôi phục có xác minh nhiều tín hiệu, phê duyệt và kiểm toán theo rủi ro. |

## 7. Credential trong Mover: thay đổi vai trò và mức rủi ro

**Mover** xảy ra khi một người đổi bộ phận, vị trí, người quản lý, trách nhiệm hoặc loại quan hệ với tổ chức. Credential cá nhân không nhất thiết phải thay mỗi khi đổi manager. Tuy nhiên, IAM phải đánh giá lại **quyền và yêu cầu xác thực** gắn với công việc mới.

Ví dụ kỹ sư Lan chuyển từ nhóm vận hành production sang nhóm kiểm thử:

- Tài khoản IdP chính và passkey cá nhân có thể tiếp tục được dùng nếu quan hệ lao động và thiết bị còn hợp lệ.
- Quyền production và PAT dùng cho triển khai cũ phải được rà soát/thu hồi theo chính sách.
- Quyền vào môi trường kiểm thử được cấp sau phê duyệt; quyền nhạy cảm có thể yêu cầu step-up authentication.
- Tài khoản quản trị, service account và secret Lan từng quản lý phải được kiểm tra riêng; một key dùng chung có thể cần rotate.
- Các phiên/token mang quyền cũ cần được đánh giá khả năng tiếp tục sử dụng trong thời gian chưa hết hạn.

### Phân biệt thay đổi thông tin và tăng cường xác thực

| Sự kiện Mover | Tác động hợp lý |
| --- | --- |
| Đổi manager nhưng giữ vai trò và thiết bị. | Cập nhật tuyến phê duyệt; credential chính có thể giữ, miễn còn hợp lệ. |
| Được cấp quyền quản trị sản xuất. | Có thể yêu cầu authenticator chống phishing, step-up hoặc tài khoản/phiên đặc quyền tách biệt. |
| Rời nhóm có quyền API nhạy cảm. | Thu hồi PAT/API key và quyền trực tiếp liên quan vai trò cũ. |
| Chuyển từ Contractor sang Employee. | Xác minh quan hệ mới, đánh giá lại credential/tài khoản và cấp quyền từ nguồn mới; không tự phục hồi quyền cũ. |
| Thiết bị bị mất hoặc không còn tuân thủ chính sách. | Vô hiệu credential liên quan, khôi phục/đăng ký lại có xác minh. |

**Không nên xoay mọi mật khẩu một cách máy móc chỉ vì đổi phòng ban**, nhưng cần thu hồi nhanh credential đã mất chủ thể hợp lệ, bí mật từng được chia sẻ ngoài phạm vi hoặc quyền mà vai trò mới không còn yêu cầu.

## 8. Credential trong Leaver: ngăn mọi đường xác thực còn hiệu lực

Khi Employee/Contractor rời tổ chức, **Leaver lifecycle** phải kết thúc quyền truy cập dựa trên thời điểm nguồn có thẩm quyền xác nhận. Tác vụ không chỉ là đặt \`disabled=true\` trong IdP.

### Các bước cần phối hợp

1. **Nhận sự kiện Leaver đáng tin cậy** từ HRIS/hợp đồng, kèm subject ID, engagement ID và thời điểm hiệu lực.
2. **Khóa đăng nhập IdP/Directory** theo chính sách; đánh dấu quan hệ không còn hợp lệ để ngăn cấp credential mới.
3. **Vô hiệu hoặc thu hồi authenticator/credential cá nhân** theo cơ chế IdP và ứng dụng, bao gồm passkey, password verifier, chứng chỉ hoặc thiết bị xác thực được quản lý trong phạm vi.
4. **Thu hồi phiên và refresh token** khi được hỗ trợ; đánh giá OAuth access token, cookie ứng dụng và token tự chứa đã phát hành còn sống.
5. **Dùng SCIM/API hoặc phương thức quản trị riêng** để disable tài khoản đích và thu hồi PAT, API key, khóa cloud, token của ứng dụng không liên kết đầy đủ với IdP.
6. **Xử lý tài khoản quản trị phụ, ủy quyền và credential dùng chung**, gồm bí mật Leaver từng biết hoặc có thể sao chép.
7. **Chuyển owner service account/workload** hoặc ngừng dịch vụ theo chính sách, xoay credential cần thiết mà không làm ngắt hệ thống hợp lệ ngoài kế hoạch.
8. **Đọc lại trạng thái và đối soát** trên từng hệ thống; ghi nhận đường truy cập còn hiệu lực và ngoại lệ chưa khép kín.

### Vì sao khóa SSO chưa đủ?

SSO giúp các ứng dụng dựa vào quá trình xác thực tại **IdP**, nhưng ứng dụng có thể:

- Có tài khoản đăng nhập cục bộ, không dùng SSO.
- Giữ phiên ứng dụng hoặc cookie đã phát hành.
- Chấp nhận API key/PAT được cấp độc lập.
- Chấp nhận JWT còn trong hạn mà không kiểm tra trạng thái revocation tại thời điểm gọi.
- Dùng certificate, SSH key hoặc credential máy gắn với quyền không được quản lý bởi IdP.

**SCIM chủ yếu giúp cấp phát và quản lý User/Group**, không phải giao thức tổng quát thu hồi mọi passkey, API key, refresh token hoặc session. Vì vậy cần ma trận **hệ thống đích × loại credential/phiên × phương pháp thu hồi × kết quả xác minh**.

### Token và phiên còn hoạt động

| Đối tượng | Vấn đề | Kiểm soát có thể dùng |
| --- | --- | --- |
| **IdP session** | Phiên đăng nhập tập trung còn trong hạn. | Thu hồi phiên/session theo tính năng IdP. |
| **Application session** | Ứng dụng duy trì cookie riêng. | Hủy session ở ứng dụng, thay policy hoặc yêu cầu xác thực lại. |
| **Refresh token** | Có thể xin access token mới. | Thu hồi grant/token family theo cơ chế authorization server. |
| **Opaque access token** | Resource server hỏi trạng thái token. | Introspection hoặc kiểm tra trạng thái hiện tại, xử lý cache. |
| **Self-contained JWT access token** | Có thể được chấp nhận tới \`exp\` nếu chỉ kiểm chữ ký và hạn. | Token TTL ngắn, denylist, kiểm quyền trực tuyến hoặc token version khi hỗ trợ. |
| **PAT/API key** | Provider riêng vẫn có thể chấp nhận. | Thu hồi trực tiếp ở provider, kiểm tra API đích và log. |

Không tuyên bố “đã thu hồi toàn bộ quyền ngay lập tức” khi một resource server chưa hỗ trợ vô hiệu token đã phát hành trước hạn. Cần nêu rõ **cửa sổ truy cập tồn dư có thể xảy ra** và biện pháp giảm rủi ro.

## 9. Credential của tài khoản dịch vụ và workload

Không phải credential nào cũng do con người trực tiếp sử dụng. **Service account**, application identity, CI/CD job, máy chủ và workload có thể giữ private key, client secret, API key hoặc credential ngắn hạn để truy cập máy với máy.

### Phân biệt principal và owner

- **Principal kỹ thuật**: tài khoản hoặc workload mà API thực sự xác thực.
- **Owner**: nhóm hoặc người chịu trách nhiệm cho mục đích, scope, bí mật và vòng đời credential.
- **Operator**: con người/hệ thống triển khai hay sử dụng dịch vụ, có thể khác owner.

Ví dụ một pipeline sử dụng \`service-principal-deploy-prod\`, owner là đội Platform. Khi developer từng tạo secret nghỉ việc, principal có thể vẫn cần tồn tại; tổ chức phải chuyển trách nhiệm nếu cần, đánh giá rủi ro việc secret đã biết, rotate và kiểm chứng pipeline tiếp tục chạy với quyền tối thiểu.

### Nguyên tắc quản lý credential máy

1. **Ưu tiên danh tính workload và credential ngắn hạn** khi có hỗ trợ, tránh API key không hết hạn lưu rải rác trong file cấu hình.
2. **Không để bí mật trong source code, log hoặc image/container**; quản lý trong secrets manager phù hợp và kiểm soát truy cập.
3. **Định nghĩa issuer, owner, workload, environment và scope** cho mỗi credential; giới hạn quyền theo tài nguyên cần thiết.
4. **Xoay bí mật có kiểm soát** khi lộ, mất owner, đổi trust hoặc theo vòng đời quy định; kiểm tra dịch vụ dùng credential mới rồi thu hồi credential cũ.
5. **Ràng buộc danh tính kỹ thuật với workload thực tế**: hạn chế client/role bị giả danh bởi job hoặc môi trường khác.
6. **Theo dõi chứng chỉ và khóa**: ngày hết hạn, người phát hành, key protection, revoke/renewal và khả năng hệ thống đích thực sự kiểm tra thu hồi.
7. **Decommission**: khi dịch vụ ngừng hoạt động, thu hồi credential và quyền tại API/resource server, giữ audit metadata theo lịch hợp lệ.

### Ví dụ metadata của workload

~~~json
{
  "credentialId": "workload-cred-902",
  "principalId": "svc-deploy-production",
  "ownerTeamId": "platform-engineering",
  "workloadId": "release-pipeline",
  "environment": "production",
  "issuer": "corporate-workload-identity",
  "credentialType": "SHORT_LIVED_TOKEN",
  "scope": ["deploy:approved-service"],
  "maxLifetimeSeconds": 900,
  "state": "ACTIVE",
  "policyVersion": "4"
}
~~~

Các giá trị chỉ minh họa, không phải mặc định an toàn cho mọi hệ thống. Giá trị **900 giây** là ví dụ TTL, cần chọn theo khả năng kỹ thuật, hiệu năng và đánh giá rủi ro thực tế.

## 10. Credential, IdP, SSO, SCIM và quyền truy cập

~~~mermaid
flowchart TD
    HR["HRIS / nguồn có thẩm quyền<br/>JML + trạng thái quan hệ"] --> IGA["IAM / IGA<br/>Điều phối vòng đời"]
    IGA -->|"Tạo/disable tài khoản"| IDP["IdP / verifier<br/>Đăng ký credential, MFA, xác thực"]
    U["Người dùng / workload<br/>Authenticator, private key, token"] -->|"Chứng minh quyền kiểm soát"| IDP
    IDP -->|"SSO: OIDC/SAML"| APP["Ứng dụng"]
    IGA -->|"SCIM / API provisioning"| APP
    APP -->|"Quyết định quyền"| POLICY["RBAC / ABAC<br/>Policy + entitlements"]
    IGA -->|"Revoke/rotate credential theo provider"| API["API / secrets / cloud provider"]
    IDP --> AUD["Audit và đối soát"]
    APP --> AUD
    API --> AUD
    POLICY --> AUD
~~~

**Phân tách trách nhiệm**:

- **HRIS/hệ thống hợp đồng**: xác nhận chủ thể có quan hệ hợp lệ và thời điểm thay đổi.
- **IAM/IGA**: điều phối đăng ký, cấp tài khoản, đánh giá quyền và thu hồi theo vòng đời.
- **IdP/verifier**: đăng ký phương thức xác thực, kiểm chứng bằng chứng và có thể phát hành phiên hoặc token cho ứng dụng.
- **SSO/OIDC/SAML**: chuyển kết quả xác thực tin cậy tới ứng dụng; không tự quyết định tất cả entitlement nghiệp vụ.
- **SCIM**: cấp phát/cập nhật/disable User và Group ở ứng dụng hỗ trợ; không đồng nghĩa thu hồi mọi token hoặc API credential độc lập.
- **RBAC/ABAC**: ra quyết định quyền dựa trên vai trò, thuộc tính chủ thể, tài nguyên và bối cảnh; có thể yêu cầu phương thức xác thực mạnh hơn cho hành động nhạy cảm.
- **Audit/reconciliation**: truy lại sự kiện nguồn, credential đăng ký/thu hồi, phiên, chính sách và kết quả tại hệ thống đích.

**Authentication và authorization là hai kiểm soát bổ sung.** Có passkey hợp lệ chứng minh quyền kiểm soát tài khoản tại bước xác thực; muốn đọc dữ liệu nhạy cảm vẫn cần role/attribute được phép. Ngược lại, role đã bị thu hồi phải khiến API từ chối truy cập dù phiên hoặc token cũ vẫn tồn tại, nếu kiến trúc ứng dụng hỗ trợ kiểm tra quyền hiện tại.

## 11. Lưu trữ và bảo vệ credential

### 11.1. Mật khẩu và bí mật dùng chung

Đối với mật khẩu người dùng:

- Chỉ gửi qua kênh bảo vệ và không hiển thị/log lại mật khẩu.
- Lưu **password verifier** bằng phương pháp băm mật khẩu có salt và tham số chi phí thích hợp; bảo vệ cơ sở dữ liệu xác thực và khóa bổ sung nếu có.
- Ngăn dò đoán và credential stuffing bằng rate limit, phát hiện rủi ro, chính sách mật khẩu phù hợp và MFA.
- Hỗ trợ thay/khôi phục mật khẩu bằng quy trình xác minh an toàn, không gửi lại mật khẩu gốc.

Đối với API key, refresh token, client secret, private key:

- Lưu trong secrets manager hoặc kho bảo vệ thích hợp; giới hạn người/workload có thể đọc.
- Phân quyền theo môi trường và ứng dụng; tách nhiệm vụ phát hành, sử dụng và thu hồi khi cần.
- Tránh truyền bí mật qua ticket, chat, email hay tham số URL có thể xuất hiện trong log.
- Ưu tiên khóa được bảo vệ bằng phần cứng hoặc cơ chế do nền tảng quản lý khi mức rủi ro yêu cầu.
- Có chính sách rotation/revocation, đo thời hạn sống và theo dõi key bị dùng sau khi đã mất hiệu lực.

**Không lưu tất cả loại credential giống mật khẩu.** Mật khẩu có thể được kiểm tra bằng verifier băm; một số key/token cần được dịch vụ dùng để gọi API, nên yêu cầu hệ thống quản lý bí mật hoặc cơ chế ký/đối chiếu phù hợp. Public key của WebAuthn là dữ liệu để xác minh chữ ký, không phải bí mật cần được “băm mật khẩu”.

### 11.2. Chống lộ trong log và telemetry

Không ghi password, OTP, recovery code, private key, API key, bearer token, refresh token, cookie phiên hoặc toàn bộ assertion chứa dữ liệu nhạy cảm vào log/trace. Hệ thống có thể lưu **credential ID, loại, issuer, principal, thời điểm, kết quả, mã lý do và tham chiếu bằng chứng** nếu cần cho kiểm toán.

Một ví dụ record an toàn:

~~~json
{
  "eventId": "auth-evt-20261123-015",
  "eventType": "AUTHENTICATOR_REGISTERED",
  "subjectId": "person-1042",
  "accountId": "idp-account-721",
  "credentialId": "cred-8f21",
  "authenticatorType": "PASSKEY",
  "issuer": "corporate-idp",
  "outcome": "SUCCESS",
  "occurredAt": "2026-11-23T02:00:00Z",
  "verificationPolicyVersion": "5"
}
~~~

Không cần giữ raw credential để giải trình sự kiện đăng ký hoặc thu hồi.

## 12. Khôi phục credential: điểm có thể làm suy yếu toàn bộ MFA

Một phương thức chống phishing tốt vẫn có thể bị vượt qua nếu attacker gọi helpdesk và giả mạo người dùng để đăng ký thiết bị khác. **Account recovery** phải được quản trị như một luồng xác thực nhạy cảm, không như thao tác hành chính đơn giản.

### Các bước quản trị recovery

1. Xác nhận chủ thể và tình trạng quan hệ hiện tại từ nguồn tin cậy; **không khôi phục tài khoản Leaver** do yêu cầu cá nhân.
2. Kiểm tra mức rủi ro, quyền đang có, các lần recovery gần đây và dấu hiệu chiếm đoạt.
3. Thực hiện identity proofing phù hợp; không chỉ tin email/số điện thoại được cung cấp trong yêu cầu nếu có thể đã bị chiếm.
4. Thu hồi hoặc tạm ngưng authenticator bị mất/lộ theo chính sách.
5. Đăng ký authenticator mới qua kênh tin cậy, kiểm soát step-up và hoạt động rủi ro cao trong thời gian chuyển tiếp.
6. Thông báo cho chủ tài khoản qua kênh đã xác minh, lưu audit trail và cảnh báo thao tác bất thường.

Ví dụ: người dùng bị mất điện thoại có passkey. Recovery có thể dựa vào khóa bảo mật dự phòng, tài khoản đồng bộ có cơ chế khôi phục đáng tin cậy hoặc quy trình xác minh của tổ chức. **Không có một cách khôi phục duy nhất phù hợp mọi loại passkey**, đặc biệt giữa thiết bị cá nhân và thiết bị doanh nghiệp quản lý.

### Các nguy cơ cần theo dõi

| Tình huống | Rủi ro |
| --- | --- |
| Helpdesk đặt lại MFA chỉ sau khi nghe tên nhân viên và ngày sinh. | Thông tin dễ thu thập, nguy cơ social engineering. |
| Người dùng đã nghỉ việc gửi yêu cầu khôi phục tài khoản cũ. | Truy cập trái phép sau Leaver. |
| Authenticator mới được thêm từ một phiên cũ đã bị chiếm. | Kẻ tấn công giành quyền đăng nhập bền vững. |
| Passkey bị mất nhưng không có phương thức phục hồi đã kiểm chứng. | Khó phục hồi hoạt động; dễ tạo ngoại lệ kém an toàn. |
| Recovery code được gửi qua email không bảo vệ hoặc lưu trong log. | Mất tính bí mật của kênh phục hồi. |

## 13. Các lỗi triển khai phổ biến

| Lỗi | Hệ quả | Biện pháp |
| --- | --- | --- |
| Gắn credential chỉ dựa vào email. | Email đổi/tái cấp có thể dẫn tới gắn sai danh tính. | ID ổn định, source mapping và xác minh người đăng ký. |
| Coi hai mã OTP là MFA mạnh. | Các yếu tố có thể không độc lập và cùng bị phishing. | Hiểu đúng yếu tố, ưu tiên authenticator chống phishing khi phù hợp. |
| Cho phép đăng ký MFA mới từ phiên rủi ro mà không xác minh lại. | Attacker thêm authenticator của mình. | Reauthentication/step-up, thông báo và giám sát. |
| Lưu mật khẩu rõ hoặc băm nhanh không có chính sách phù hợp. | Tăng hậu quả khi database lộ. | Password hashing có salt, tham số chi phí và kiểm soát nguồn. |
| Thay mật khẩu nhưng giữ tất cả refresh token/phiên cũ. | Phiên bị đánh cắp có thể vẫn hoạt động. | Quy tắc thu hồi phiên/token theo loại sự kiện và khả năng IdP. |
| Disable IdP nhưng không xử lý PAT/API key SaaS. | Người nghỉ tiếp tục gọi API. | Inventory theo provider, revoke và kiểm tra kết quả API đích. |
| Xoay client secret và tưởng token cũ đã vô hiệu. | Access token còn sống tới khi hết hạn hoặc được chặn theo cơ chế khác. | Đánh giá token TTL, resource server, grant và cache. |
| Dùng PAT nhân viên cho job production lâu dài. | Gián đoạn khi Leaver hoặc giữ key quá hạn. | Chuyển sang workload identity/service principal có owner. |
| Credential thiếu owner hoặc hết hạn không được theo dõi. | Key mồ côi, truy cập tồn dư và sự cố gián đoạn. | Inventory, cảnh báo, rotation và trách nhiệm quản trị. |
| Kết luận revoke hoàn tất chỉ từ HTTP success. | Provider hoặc API đích có thể chưa ngừng chấp nhận. | Đối soát trạng thái, giới hạn hiệu lực và kiểm tra đường truy cập. |
| Sao chép bí mật vào ticket để điều tra. | Bí mật bị lộ rộng hơn. | Chỉ ghi credential ID, kết quả, metadata và tham chiếu an toàn. |

## 14. Ví dụ thực tế: nhân viên đã nghỉ vẫn gọi được API

**Bối cảnh:** Huy là kỹ sư vận hành, có passkey đăng nhập IdP, tài khoản quản trị cloud và PAT dùng trong script báo cáo. Huy nghỉ việc lúc 17:00 ngày 30/11. Tài khoản IdP bị khóa, nhưng lúc 17:20 hệ thống API ghi một lệnh thành công qua PAT của Huy.

| Mốc giả định | Bằng chứng | Cách hiểu |
| --- | --- | --- |
| **16:45** | HRIS/IGA ghi nhận Leaver có hiệu lực 17:00. | Có căn cứ khởi động xử lý đúng hạn. |
| **17:00** | IdP disable tài khoản và ngăn đăng nhập mới. | Kiểm soát đường xác thực tập trung. |
| **17:02** | IGA yêu cầu thu hồi phiên IdP và các quyền quản trị được quản lý. | Đang xử lý, cần kiểm tra kết quả ở từng provider. |
| **17:20** | API gateway ghi nhận request thành công từ credential ID PAT cũ. | Có đường truy cập API còn tồn tại ngoài kiểm soát ban đầu. |
| **17:24** | Owner ứng dụng xác định PAT, phạm vi quyền và workload đang giữ nó. | Có đủ căn cứ xử lý credential và tác động dịch vụ. |
| **17:27** | PAT bị revoke tại issuer, trạng thái được xác minh ở API đích. | Có bằng chứng thu hồi trong phạm vi kiểm tra. |
| **Sau xử lý** | Script báo cáo được chuyển sang service principal với owner/TTL phù hợp. | Giảm nguy cơ lặp lại phụ thuộc credential cá nhân. |

### Cách xử lý

1. Bắt đầu từ log API với **credential ID hoặc tham chiếu an toàn**, xác định issuer, principal, thời điểm và API bị truy cập.
2. Đối chiếu tới \`subjectId\` và sự kiện Leaver; kiểm tra có key cá nhân, key dùng chung hoặc key máy bị ảnh hưởng.
3. Thu hồi credential ở issuer, rà soát role/scope, khóa các đường truy cập còn lại theo chính sách.
4. Xem có access token, phiên, cache hoặc ứng dụng khác còn sử dụng credential được cấp từ cùng grant hay không.
5. Chuyển tác vụ hợp lệ sang principal không phụ thuộc vào người nghỉ; giới hạn scope và kiểm tra hoạt động.
6. Ghi đầy đủ sự kiện, xác minh kết quả, lỗi chưa khép kín và nguyên nhân inventory bỏ sót PAT.

**Kết luận nghiệp vụ của ví dụ:** việc IdP có sự kiện “đăng nhập bị khóa” chưa chứng minh các API đã ngừng chấp nhận credential độc lập. Luồng Leaver phải kết nối **tài khoản, authenticator, phiên, token, API credential và quyền thực tế**.

## 15. Đo lường và kiểm toán vòng đời credential

Các chỉ số nên phản ánh cả độ bao phủ và kết quả, không chỉ số lệnh đã gửi:

| Chỉ số | Cách đo gợi ý | Mục tiêu |
| --- | --- | --- |
| **Tỷ lệ credential có owner/principal hợp lệ** | Credential đang hoạt động được nối tới subject/workload và owner rõ ràng ÷ tổng credential kiểm kê. | Phát hiện credential mồ côi. |
| **Tỷ lệ nhân viên có phương thức MFA phù hợp chính sách** | Tài khoản Employee có authenticator đáp ứng yêu cầu ÷ tài khoản cần áp dụng. | Giảm rủi ro chiếm tài khoản. |
| **Tỷ lệ đăng nhập đặc quyền dùng phương thức chống phishing** | Lượt đăng nhập đặc quyền đáp ứng chính sách tương ứng ÷ tổng lượt trong phạm vi. | Tăng bảo vệ đường truy cập nhạy cảm. |
| **Tỷ lệ enrollment/recovery có bằng chứng xác minh** | Hoạt động đăng ký/khôi phục có nguồn, người thực hiện, chính sách và kết quả ÷ tổng hoạt động. | Giảm đăng ký giả mạo. |
| **Độ trễ thu hồi credential khi Leaver** | Từ thời điểm quan hệ hết hiệu lực đến khi xác minh credential không còn được chấp nhận tại hệ thống đích. | Đo truy cập tồn dư. |
| **Credential của Leaver vẫn hoạt động** | Key/token/credential của chủ thể terminated còn được chấp nhận sau thời điểm phải thu hồi. | Phát hiện bỏ sót provider hoặc token cũ. |
| **Tỷ lệ service credential có TTL/rotation phù hợp** | Credential máy đáp ứng chính sách vòng đời ÷ credential máy thuộc phạm vi. | Giảm bí mật dài hạn. |
| **Tỷ lệ tác vụ revoke được xác minh** | Tác vụ có bằng chứng ở issuer/API/resource server phù hợp ÷ tổng tác vụ đến hạn. | Phân biệt đã yêu cầu và đã hoàn tất. |
| **Tỷ lệ ngoại lệ quá hạn** | Tác vụ đăng ký, revoke, recovery hoặc decommission chưa giải quyết đúng hạn ÷ tổng tác vụ cần xử lý. | Giảm nợ bảo mật. |

**Không có tỷ lệ “100% đã thu hồi” có ý nghĩa nếu một nhóm SaaS/API key nằm ngoài inventory**. Báo cáo cần nêu rõ phạm vi provider, cách kiểm chứng, thời hạn token, khả năng cache và các ngoại lệ chưa xác nhận.

### Bằng chứng audit cần có

Đối với sự kiện credential quan trọng, lưu:

- **Nguồn:** sự kiện HRIS/JML hoặc yêu cầu truy cập, ID chủ thể và tài khoản.
- **Quyết định:** chính sách xác thực, vai trò phê duyệt, lý do đăng ký/thay/thu hồi.
- **Thao tác:** credential ID, issuer, loại, actor thực hiện và thời điểm.
- **Kết quả:** phản hồi IdP/provider và kết quả xác minh trên ứng dụng/API đích.
- **Ngoại lệ:** những provider chưa thể kiểm tra, owner, thời hạn xử lý và kết quả đóng.

Giữ log theo thời hạn và quyền truy cập được phê duyệt; bảo vệ tính toàn vẹn, che dữ liệu cá nhân nhạy cảm và tuyệt đối không lưu raw secret vào dấu vết kiểm toán.

## 16. Checklist tự đánh giá

1. Phân biệt rõ **identity, account, credential, authenticator, session/token và entitlement** chưa?
2. Mỗi credential có liên kết đúng subject/account, issuer, owner và trạng thái vòng đời không?
3. Enrollment có kiểm chứng đúng người và ngăn attacker đăng ký authenticator của mình không?
4. Đã xác định phương thức nào chống phishing, loại nào chỉ là OTP/push và mức bảo vệ cần cho quyền đặc quyền chưa?
5. Mật khẩu, private key, token và API key có được lưu bằng cơ chế phù hợp, tránh xuất hiện trong log/source code không?
6. Quy trình reset/recovery có mức xác minh tương xứng với credential ban đầu và có audit trail không?
7. Mover có đánh giá thay đổi quyền, mức xác thực, PAT/key và tài khoản quản trị ngoài IdP không?
8. Leaver có ngăn phát credential mới, thu hồi credential, phiên/refresh token và xử lý các ứng dụng không dùng SSO không?
9. Hiểu rõ SCIM có thể disable User nhưng **không tự thu hồi mọi API key hoặc token** của ứng dụng chưa?
10. Với JWT/access token còn sống, đã biết resource server kiểm tra trạng thái và giới hạn revocation như thế nào chưa?
11. Tài khoản dịch vụ/workload có principal và owner riêng, credential ngắn hạn/rotation, kế hoạch chuyển giao và decommission không?
12. Có kiểm tra trạng thái thực tế ở IdP, provider và API đích trước khi đánh dấu thu hồi hoàn tất không?
13. Có chỉ số và cảnh báo cho credential mồ côi, đăng ký MFA bất thường, key quá hạn và quyền tồn dư không?

**Ghi nhớ:** Credential là **bằng chứng kiểm soát danh tính trong quá trình xác thực**, nhưng **quyền được truy cập** còn phụ thuộc tài khoản, trạng thái vòng đời và chính sách authorization. Một thiết kế IAM tốt đăng ký credential cho **đúng chủ thể**, bảo vệ và kiểm chứng theo phương thức phù hợp, hỗ trợ thay/khôi phục an toàn, đồng thời thu hồi **credential, token, phiên và quyền liên quan** khi Joiner–Mover–Leaver yêu cầu. Chỉ khi kết quả ở hệ thống đích được xác minh, tổ chức mới có cơ sở giảm và giải trình được quyền truy cập tồn dư.
