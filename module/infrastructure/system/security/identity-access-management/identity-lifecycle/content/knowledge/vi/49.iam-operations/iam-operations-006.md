# Xử lý credential bị lộ trong IAM: phát hiện, cô lập, thu hồi và phục hồi an toàn

## 1. Tại sao lộ credential là sự cố IAM nghiêm trọng?

**Credential** là thông tin hoặc vật liệu giúp một chủ thể chứng minh danh tính hay lấy quyền truy cập: mật khẩu, API key, access/refresh token, private key, client secret, thông tin xác thực của service account, chứng chỉ khóa riêng, recovery code hoặc phương thức MFA có thể bị chiếm đoạt. **Credential bị lộ** là tình huống có căn cứ cho rằng vật liệu đó đã xuất hiện ở vị trí không được phép, bị truy cập bởi người không có thẩm quyền hoặc có khả năng đã được sao chép.

Lộ credential không đồng nghĩa chắc chắn đã có người sử dụng trái phép; tuy nhiên **không thấy log lạm dụng cũng không chứng minh credential còn an toàn**. Một số dạng khóa/token cho phép truy cập qua đường khác IdP, và log có thể chưa đầy đủ. Mục tiêu vận hành là **vô hiệu hóa khả năng sử dụng credential nghi lộ theo mức rủi ro**, tìm phạm vi bị ảnh hưởng, giữ bằng chứng, khôi phục truy cập hợp lệ và ngăn tái diễn.

Trong chương **IAM operations** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, runbook này gắn trực tiếp với mô hình **Joiner–Mover–Leaver (JML)**: danh tính mới phải được xác minh trước khi cấp credential, thay đổi vai trò cần thu hồi credential/quyền cũ, và người rời tổ chức phải mất quyền truy cập dù còn phiên hay khóa cũ. Các bước liên kết **Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, tài khoản dịch vụ, PAM, audit** và mục tiêu giảm **quyền truy cập tồn dư**.

**Sau bài học, bạn có thể:**

1. Phân loại credential nghi lộ và tìm hệ thống quyết định quyền, phạm vi, thời gian phơi lộ.
2. Thiết kế phản ứng sự cố theo thứ tự phù hợp: cô lập, vô hiệu hóa/rotate, điều tra hoạt động bất thường, phục hồi và xác minh.
3. Xử lý khác nhau giữa mật khẩu, session/token, API key, OAuth client secret, SSH key, certificate/private key, MFA factor và workload identity.
4. Giữ an toàn cho Joiner, Mover, Leaver trong thời gian credential compromise, kể cả khi IdP hoặc connector lỗi.
5. Lập hồ sơ kiểm toán có chứng cứ nhưng không để credential xuất hiện thêm trong log/ticket.

> **Phạm vi và nguyên tắc:** Đây là mẫu runbook cho vận hành phòng thủ. Sự cố thật phải theo quyền hạn của SOC/IAM và chính sách ứng phó của tổ chức. Mức ưu tiên, thời gian mục tiêu, API revoke/rotation và khả năng hủy phiên phụ thuộc nền tảng. Không có thao tác “đổi mật khẩu” duy nhất có thể vô hiệu hóa mọi phiên, token hoặc khóa độc lập.

## 2. Credential, entitlement và identity khác nhau thế nào?

| Thành phần | Chức năng | Ví dụ và rủi ro khi bị lộ |
|---|---|---|
| **Identity** | Đại diện chủ thể người hoặc workload | Nhân viên, nhà thầu, service identity; cần xác minh bằng ID bền vững |
| **Account** | Bản ghi đăng nhập ở IdP, directory hoặc ứng dụng | User SaaS còn active dù HR báo Leaver |
| **Password / passphrase** | Yếu tố bí mật dùng xác thực | Password reuse dẫn tới truy cập nhiều hệ thống |
| **API key / personal access token (PAT)** | Credential truy cập API hoặc tài nguyên | Có thể hoạt động độc lập với SSO và tiếp tục sau khi logout |
| **Access token** | Bằng chứng ủy quyền thường có thời hạn | Bearer token có thể được sử dụng đến expiry hoặc khi bên nhận chủ động chặn |
| **Refresh token** | Có thể đổi lấy access token mới theo điều kiện của issuer | Cần xử lý riêng nếu cơ chế revoke hoặc rotation hỗ trợ |
| **OAuth client secret** | Xác thực một client/confidential application | Lộ có thể cho phép client giả mạo trong grant flow phù hợp |
| **Private key / SSH key** | Chứng minh sở hữu khóa, ký hoặc xác thực | Cần thu hồi trust/authorized keys và cấp khóa thay thế |
| **Certificate và khóa ký** | Ràng buộc danh tính/khóa công khai trong hệ tin cậy | Lộ private key có thể ảnh hưởng ký, mTLS hoặc federation; xử lý theo phạm vi trust |
| **MFA seed / recovery code** | Yếu tố hoặc đường khôi phục xác thực | Có thể làm giảm hiệu quả của MFA, cần re-enrollment/rotation |
| **Entitlement** | Quyền được phép làm sau xác thực | Role admin hoặc access policy không tự mất chỉ vì đổi password |
| **Session** | Trạng thái đăng nhập đang có tại một hệ thống | Cookie/phiên có thể còn hiệu lực sau password reset |

**Một credential có thể gắn với nhiều quyền**, và một danh tính có thể sở hữu nhiều credential. Ví dụ, nhân viên có password SSO, một PAT trên nền tảng mã nguồn, SSH key và API token SaaS. Khi password IdP bị lộ, phải điều tra xem các credential khác có bị ảnh hưởng, nhưng không tự kết luận mọi khóa đều đã lộ. Khi PAT bị lộ, đổi mật khẩu IdP chưa chắc vô hiệu hóa PAT; phải revoke đúng token tại nền tảng đích.

### 2.1. Ba trạng thái cần phân biệt

- **Exposure (phơi lộ):** credential xuất hiện trong repository, log, screenshot, chat, tài liệu công khai hoặc nơi không có quyền hạn phù hợp.
- **Compromise nghi ngờ:** bằng chứng cho thấy bên không được phép có khả năng truy cập hoặc sao chép credential, chưa xác nhận sử dụng.
- **Confirmed misuse (lạm dụng xác nhận):** có dấu vết đáng tin cậy về hành động trái phép được thực hiện bằng credential hoặc phiên/tài khoản liên quan.

Các mức không phải chuỗi tuyến tính bắt buộc. Có khi phát hiện hành vi lạm dụng trước khi tìm thấy vị trí credential rò rỉ; cũng có khi credential bị phơi lộ nhưng chưa từng được sử dụng. Quyết định ứng phó dựa vào **khả năng bị khai thác, phạm vi quyền và hậu quả**, không chỉ nhãn trạng thái.

## 3. Vị trí credential có thể lưu trú trong kiến trúc IAM

~~~mermaid
flowchart LR
    HR[HRIS / Nguồn nhà thầu] --> JML[Điều phối JML]
    JML --> IDP[IdP / Directory]
    JML --> PROV[SCIM / Provisioning]
    IDP -->|OIDC / SAML SSO| APP[Ứng dụng]
    PROV --> APP
    IDP --> MFA[MFA / Risk / Policy]
    APP --> LOCAL[Phiên / PAT / Local credential]
    DEV[CI/CD / Workload] --> VAULT[Secret Manager]
    VAULT --> CLOUD[Cloud / Service API]
    PAM[PAM / JIT / Admin] --> CLOUD
    IDP --> LOG[Audit / SIEM]
    APP --> LOG
    VAULT --> LOG
    CLOUD --> LOG
    PAM --> LOG
~~~

Các đường lộ quan trọng trong một môi trường thực tế:

1. **Người dùng:** nhập credential vào trang phishing, mất thiết bị, gửi screenshot chứa recovery code, lưu password trong nơi chia sẻ sai.
2. **Ứng dụng:** log HTTP header hoặc token, file cấu hình chứa client secret, debug dump, crash report, backup có quyền đọc quá rộng.
3. **Repository/CI/CD:** secret hardcode trong source, commit Git, image/container layer, artifact build, variable bị in ra console, pipeline log.
4. **Dịch vụ hạ tầng:** API key hay private key trong secret store cấu hình sai, snapshot/backup, cấu hình máy chủ, script automation, SSH authorized keys.
5. **Federation:** SAML signing private key, OIDC client secret, workload federation trust hoặc chứng chỉ mTLS được quản lý không an toàn.
6. **Quản trị đặc quyền:** session PAM, break-glass credential hoặc tài khoản admin dùng chung không có owner rõ ràng.

**Điểm cần kiểm tra:** credential được dùng để gọi **issuer/IdP**, **ứng dụng đích**, **cloud resource** hay **secret exchange service**? Người vận hành phải xác định đúng nơi có khả năng **revoke/disable/deny**. Một thao tác ở IdP không đồng nghĩa vô hiệu hóa toàn bộ credential được ứng dụng khác phát hành.

## 4. Mô hình phản ứng sự cố: từ phát hiện tới đóng hồ sơ

~~~mermaid
flowchart TD
    A[Phát hiện credential nghi lộ] --> B[Ghi nhận, bảo vệ chứng cứ tối thiểu]
    B --> C[Phân loại loại credential, owner, phạm vi]
    C --> D{Có thể sử dụng và rủi ro cao?}
    D -->|Có| E[Contain ngay theo quyền được phê duyệt]
    D -->|Chưa rõ| F[Xác minh khẩn, áp hạn chế phù hợp]
    D -->|Không còn hiệu lực có bằng chứng| G[Xác nhận trạng thái và điều tra phơi lộ]
    F --> E
    E --> H[Revoke / Disable / Rotate đúng nguồn]
    G --> I[Đánh giá đã từng bị dùng trái phép?]
    H --> I
    I --> J[Kiểm tra session, token, grants, persistence]
    J --> K[Phục hồi truy cập hợp lệ theo policy JML]
    K --> L[Đối soát actual và desired, kiểm thử an toàn]
    L --> M{Đủ điều kiện đóng?}
    M -->|Không| N[Exception, owner, deadline, giám sát]
    N --> L
    M -->|Có| O[Audit, RCA, sửa nguồn rò rỉ]
~~~

**Hai luồng diễn ra song song:** bảo vệ bằng chứng và **giảm khả năng lạm dụng**. Không trì hoãn vô hiệu hóa một khóa đang được dùng bởi kẻ không có thẩm quyền chỉ vì muốn thu thập thêm log; đồng thời không xóa dữ liệu cần điều tra mà không tuân thủ quy trình bảo quản.

### 4.1. Trách nhiệm khi xảy ra sự cố

| Vai trò | Trách nhiệm |
|---|---|
| **Người phát hiện / Service Desk** | Báo ngay qua kênh quy định, mô tả vị trí phơi lộ bằng tham chiếu; không sao chép credential |
| **SOC / Incident Commander** | Phân loại mức độ, chỉ đạo containment, điều tra dấu hiệu lạm dụng, giữ bằng chứng |
| **IAM Operations** | Xác định identity/credential, revoke session/token, khóa quyền truy cập, cập nhật IdP và audit |
| **Application/Resource Owner** | Thu hồi API key, PAT, phiên local, role và policy trong hệ thống đích |
| **Platform/DevOps** | Rotate secret của workload, sửa pipeline, vault, cấu hình ứng dụng và phụ thuộc |
| **HR / Sponsor** | Xác thực trạng thái JML, người sở hữu/chủ thể, nhà thầu và thời điểm có quyền |
| **PAM/PKI Owner** | Xử lý khóa ký, certificate, SSH, admin/break-glass credential và hậu kiểm |
| **Legal/Privacy/Compliance** | Đánh giá nghĩa vụ báo cáo và bảo vệ dữ liệu khi phạm vi sự cố yêu cầu |

Không một người tự xác nhận giữ quyền admin bị lộ của chính mình. Mọi emergency access, exception hoặc credential thay thế phải có owner, phạm vi và thời hạn.

## 5. SOP-CL01 — Tiếp nhận tín hiệu và bảo vệ thông tin

**Trigger:** phát hiện secret trong repository, cảnh báo secret scanner, log/token bị lộ, user báo phishing, alert về đăng nhập bất thường, vault audit bất thường hoặc người phụ trách nghi rò rỉ credential.

1. **Tạo incident/ticket** và gắn `incident_id`, thời điểm phát hiện, người phát hiện, hệ thống liên quan, nguồn tín hiệu và sơ bộ mức nghiêm trọng.
2. **Ngăn lộ thêm trong quy trình phản hồi:** không paste password, token, private key hoặc recovery code vào ticket, chat, email hay ảnh chụp. Chỉ dùng đường dẫn/ID của artifact cần kiểm tra ở nơi được phân quyền; hạn chế hiển thị preview secret.
3. **Xác định loại credential** và issuer/owner nếu biết: mật khẩu IdP, API key SaaS, PAT, OAuth client secret, private key, MFA recovery, service identity…
4. **Xác định vị trí phơi lộ:** public/private repository, log, thiết bị, artifact, vault, trang web, tài liệu chia sẻ. Đánh giá ai có thể đọc và khoảng thời gian có thể bị truy cập.
5. **Xác minh tính hiện hành bằng metadata an toàn:** key ID, fingerprint, secret version, trạng thái active, resource gắn với credential. Tránh thực hiện một lần đăng nhập thử bằng credential nghi lộ nếu không có quy trình kiểm thử được phê duyệt.
6. **Bảo vệ chứng cứ:** giữ đường dẫn commit/version, timestamp, audit event ID, cấu hình ACL, log truy cập và bản ghi phơi lộ bằng kênh điều tra có kiểm soát; không xóa cả log/commit trước khi nhóm điều tra thu được thông tin cần thiết.
7. **Thông báo SOC/IAM và owner ngay khi mức rủi ro yêu cầu**, kể cả khi chưa rõ credential đã bị sử dụng hay chưa. Nếu credential còn có thể hoạt động ở phạm vi nhạy cảm, kích hoạt containment song song.

**Đầu ra:** hồ sơ có ID, bằng chứng tham chiếu, loại credential, chủ sở hữu hoặc owner tạm thời, phạm vi dự đoán, quyết định containment và nhóm chịu trách nhiệm.

### 5.1. Không phát tán thêm bí mật khi làm bằng chứng

| Việc cần làm | Lý do |
|---|---|
| Dùng secret ID, key fingerprint hoặc tên biến an toàn | Đối chiếu đúng đối tượng mà không lộ giá trị |
| Giữ log/phơi lộ trong kho chứng cứ có ACL và retention | Phục vụ điều tra mà kiểm soát người đọc |
| Che `Authorization` header, cookie, private key, query token | Tránh tạo thêm bản sao credential còn hiệu lực |
| Ghi thời điểm và múi giờ rõ ràng | Tính cửa sổ exposure và nối sự kiện |
| Giới hạn người xem ticket và file đính kèm | Giảm phạm vi phơi lộ thứ cấp |
| Báo nhóm Security khi dữ liệu nhạy cảm có khả năng bị truy cập | Đánh giá nghĩa vụ và mức ảnh hưởng đúng quy trình |

## 6. SOP-CL02 — Xác định phạm vi, mức rủi ro và thứ tự xử lý

### 6.1. Các câu hỏi xác định blast radius

1. Credential **thuộc về ai/cái gì**? Person ID, service principal, nhà thầu, workload, tài khoản dùng chung, signing authority hay tenant.
2. Credential **xác thực ở đâu**? IdP, VPN, cloud, SaaS, Git hosting, database, SSH, CI/CD hoặc service-to-service.
3. Nó có quyền gì theo **RBAC/ABAC, scope, resource policy** và nhóm kế thừa? Có khả năng đọc PII, sửa dữ liệu, triển khai production, cấp quyền mới hay truy cập secret khác?
4. Credential **được thấy ở đâu**, ai có khả năng truy cập, thời điểm phơi lộ sớm nhất và thời điểm ghi nhận?
5. Credential còn **active** hay đã hết hạn/thu hồi? Có khả năng tái cấp token hoặc tạo phiên mới không?
6. Có **credential khác phụ thuộc** hoặc được sinh từ credential này không? Ví dụ refresh token, credential chain, temporary cloud credential hoặc service secret?
7. Có **sử dụng bất thường**, thay đổi quyền, tạo key mới, đăng ký MFA mới, data export hoặc hoạt động từ thiết bị/địa điểm lạ?
8. Có ràng buộc vận hành nào với việc revoke ngay, và đường giảm rủi ro an toàn tạm thời là gì?

### 6.2. Phân loại mức ưu tiên tham khảo

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| **P0** | Private key cấp token/SSO bị nghi chiếm; admin credential hoạt động bị dùng trái phép; Leaver còn credential sản xuất đang bị lạm dụng | Kích hoạt incident khẩn với SOC/IAM/PAM, hạn chế lối vào, phối hợp xử lý toàn trust chain |
| **P1** | API key còn hiệu lực tới dữ liệu nhạy cảm xuất hiện công khai; PAT có quyền ghi production; refresh token nghi lộ | Thu hồi nhanh theo owner, điều tra phiên/key liên quan và phạm vi truy cập |
| **P2** | Credential có quyền hạn chế xuất hiện ở nơi chia sẻ không đúng, chưa thấy lạm dụng | Xác định scope, revoke/rotate có kiểm chứng và sửa nơi lưu |
| **P3** | Chuỗi giống secret nhưng có bằng chứng là dummy, hoặc credential đã thu hồi trước khi xuất hiện | Xác nhận bằng nguồn đáng tin, xử lý hygiene, lưu kết quả phân loại |

Những mức này là **ví dụ**, không phải SLA cố định. Mức rủi ro còn phụ thuộc data classification, mạng truy cập, thời hạn token, trust, khả năng vô hiệu hóa, số tài nguyên liên quan và dấu hiệu xâm nhập.

### 6.3. Sai lầm cần tránh khi định mức

- “Repo private nên không sao”: một repository riêng tư vẫn có người/công cụ vượt nhu cầu được đọc, hoặc đã fork/mirror.
- “Token sắp hết hạn nên không cần revoke”: còn thời gian hoạt động dù ngắn có thể đủ để lạm dụng; cần đánh giá phạm vi và khả năng tạo token mới.
- “Không thấy login lạ nên chắc chưa bị dùng”: có thể dùng API mà không phát sinh IdP login, hoặc log chưa đủ.
- “Đổi password là xong”: PAT, refresh token, cookie, SSH key và application-local credential cần xử lý riêng theo khả năng hệ thống.
- “Service account không có người dùng nên ít rủi ro”: workload thường có quyền rộng và chạy ngoài giờ hành chính.

## 7. SOP-CL03 — Containment: chặn khả năng lạm dụng trước khi quay lại bình thường

**Containment** nhằm giảm khả năng credential nghi lộ tiếp tục được sử dụng hoặc tạo quyền mới. Hành động cần đúng phạm vi, có owner và được kiểm chứng; trong trường hợp tấn công đang diễn ra, SOC có thể triển khai nhiều bước đồng thời.

### 7.1. Trình tự quyết định

1. Xác nhận credential và **hệ thống có quyền thu hồi**. Với token của SaaS, cần revoke ở SaaS; với private key mTLS, cần xử lý trust/certificate; với mật khẩu IdP, kiểm soát ở IdP/directory.
2. Kiểm tra có **dấu hiệu bị lạm dụng hiện tại** hoặc quyền đặc quyền/dữ liệu nhạy cảm không. Nếu có, ưu tiên khóa đường sử dụng, hạn chế session/token và chặn mọi quyền phát sinh mới.
3. Xác định phụ thuộc sản xuất. Với service credential, phối hợp owner để kích hoạt credential thay thế an toàn nhưng không kéo dài thời gian credential lộ còn hợp lệ ngoài mức được chấp nhận.
4. Thực hiện **disable/revoke** hoặc thay đổi policy deny theo khả năng nền tảng; nếu chưa thể revoke, áp biện pháp giảm thiểu được Security duyệt như chặn endpoint/nguồn, thu hẹp scope hoặc cô lập workload.
5. Điều tra và thu hồi **session/token/role liên quan** khi credential có thể đã bị dùng để tạo chúng.
6. Chặn tự động **re-provision/regrant** từ job JML, script hoặc connector cũ nếu chúng có thể kích hoạt lại quyền trái chính sách.
7. Ghi thời điểm và kết quả kiểm chứng containment; đánh dấu mục nào vẫn còn khả năng truy cập là **ngoại lệ đang mở** với owner và deadline.

### 7.2. Containment không đồng nghĩa với hoàn tất

| Hành động | Đã giảm rủi ro gì? | Rủi ro còn cần kiểm tra |
|---|---|---|
| Reset password IdP | Giảm khả năng dùng mật khẩu cũ đăng nhập mới | Session cũ, refresh token, PAT, tài khoản local |
| Disable user ở IdP | Chặn một số đường đăng nhập mới qua IdP | App session độc lập, API key và local login |
| Revoke một API key | Chặn API key đó theo semantics của đích | Key khác, token mới đã phát, cache/propagation |
| Gỡ role admin | Giảm quyền tương lai theo policy | Token/session cũ chứa quyền, direct grant khác |
| Thay signing key | Chặn sử dụng key cũ khi trust được cập nhật | Token cũ, hệ thống dùng trust cũ, tác động availability |
| Xóa secret khỏi repository hiện tại | Giảm khả năng nhìn thấy ở phiên bản mới | Credential vẫn hoạt động; commit history/fork/cache còn tồn tại |

Với **sự kiện Leaver**, chặn truy cập phải ưu tiên ngay theo thời điểm có hiệu lực và chính sách. Nếu IdP/SCIM chưa khả dụng, dùng đường thu hồi tại ứng dụng/PAM/VPN còn kiểm soát được; không chờ connector sửa xong mới giảm rủi ro.

## 8. SOP-CL04 — Mật khẩu người dùng, phishing và account takeover

Khi password người dùng bị nghi lộ qua phishing, thiết bị hoặc log, cần xem **toàn bộ tài khoản**, không chỉ đổi chuỗi mật khẩu.

### 8.1. Quy trình xử lý

1. **Xác minh đúng chủ thể:** dùng subject ID bất biến, trạng thái HR/JML, thiết bị/kênh đã đăng ký và quy trình identity proofing phù hợp. Không chỉ dựa vào email nếu hộp thư có thể bị chiếm.
2. **Chặn rủi ro hiện tại:** theo điều phối SOC, có thể disable sign-in tạm, ép reset password, revoke session/refresh token, tăng yêu cầu xác thực hoặc cách ly thiết bị.
3. **Thực hiện password reset qua IdP/directory có thẩm quyền**. Không yêu cầu người dùng gửi mật khẩu mới cho Service Desk; không cấp mật khẩu tạm qua kênh công khai.
4. **Đánh giá password reuse** và ứng dụng dùng local login; người dùng đổi tại từng hệ thống liên quan theo hướng dẫn, tránh dùng lại mật khẩu cũ.
5. **Kiểm tra tài khoản đã bị chỉnh sửa**: MFA methods, recovery options, email forwarding/delegation, app consent, OAuth grants, PAT, API tokens, group/role và account owner.
6. **Thu hồi phiên và token theo khả năng ứng dụng**. Password reset không luôn chấm dứt session đã có; kiểm tra cả IdP và SaaS quan trọng.
7. **Điều tra login và hành động đáng ngờ**: sign-in success, source/client, thay đổi mật khẩu/MFA, truy cập dữ liệu, tạo key hoặc elevation theo cửa sổ rủi ro.
8. **Khôi phục hợp lệ:** chỉ cho phép đăng nhập lại sau điều kiện SOC/owner, xác minh MFA và quyền RBAC/ABAC theo desired state.
9. **Giám sát sau khôi phục**: sign-in bất thường, password reset lặp, MFA enrollment mới, API activity và account lockout.

### 8.2. Nếu lộ yếu tố MFA hoặc recovery code

Credential compromise có thể bao gồm **MFA seed, backup/recovery code, thiết bị xác thực hoặc quyền truy cập email khôi phục**. Trong trường hợp đó cần **vô hiệu hóa hoặc đăng ký lại yếu tố bị lộ theo chính sách**, xác minh người yêu cầu ở mức đủ mạnh, kiểm tra có yếu tố lạ được thêm và rà lịch sử đăng nhập. Việc reset password mà giữ nguyên recovery code đã lộ có thể chưa giải quyết nguy cơ.

Không tắt MFA toàn tenant, không gửi recovery code qua kênh hỗ trợ và không coi “người dùng trả lời đúng tên/đơn vị” là đủ để tái cấp một yếu tố bảo mật nhạy cảm.

### 8.3. Nếu thấy dấu hiệu chiếm quyền tài khoản

Nếu có sign-in thành công bất thường, thay đổi MFA/forwarding, cấp quyền admin, consent OAuth đáng ngờ hoặc hoạt động xuất dữ liệu, chuyển sang quy trình **incident response của SOC**, mở rộng điều tra sang thiết bị, ứng dụng và tài khoản liên quan. Không đóng sau khi người dùng đăng nhập lại được.

## 9. SOP-CL05 — API key, PAT, access token và refresh token

Đây là nhóm credential thường hoạt động **ngoài phiên SSO trên trình duyệt**. Khi bị lộ, reset password IdP có thể không đủ.

### 9.1. Phân biệt tác động

| Credential | Khả năng thường gặp | Kiểm soát cần xác minh |
|---|---|---|
| **API key** | Truy cập API theo scope của tài khoản/dự án | Revoke/disable key tại issuer, tìm key còn tồn tại, request log |
| **Personal access token** | Dùng thay password cho API/repository | Revoke PAT, kiểm tra scope/repo, hoạt động clone/push/permission |
| **Access token bearer** | Được resource server chấp nhận tới expiry hoặc điều kiện chặn | Có revoke/introspection/denylist không, token cache, resource policy |
| **Refresh token** | Đổi lấy access token mới theo grant/policy | Revoke refresh token hoặc token family nơi hỗ trợ, kiểm tra token mới |
| **Session cookie** | Duy trì phiên trong ứng dụng | Invalidate session ở app, kiểm tra session store và TTL |
| **OAuth consent/grant** | Cho phép ứng dụng lấy quyền thay người dùng | Rà/thu hồi grants đáng ngờ, điều tra app registration và scope |

### 9.2. Runbook xử lý token/key

1. Xác định issuer, owner, client ID, token/key ID/fingerprint và phạm vi truy cập; không lưu giá trị bí mật.
2. Đánh giá token còn hiệu lực hay có thể refresh, scope và resource truy cập được, nguồn phơi lộ.
3. Theo quyền được phê duyệt, **revoke** token/key hoặc disable client; với incident đang diễn ra ưu tiên chặn đường API ngay.
4. Thu hồi refresh token, token family hoặc session liên quan **nếu nền tảng hỗ trợ và đánh giá rủi ro yêu cầu**. Với self-contained JWT, việc revoke ở issuer có thể không khiến resource server ngừng chấp nhận token lập tức; cần kiểm tra cơ chế deny ở đích hoặc chờ expiry với biện pháp giảm thiểu.
5. Rà xem token có từng dùng để tạo **token/key khác, app consent, quyền admin hoặc tài khoản mới**; thu hồi những thứ được tạo trái phép theo kết quả điều tra.
6. Nếu nghiệp vụ cần tiếp tục, cấp token mới với **scope tối thiểu, thời hạn ngắn phù hợp và owner rõ ràng** qua secret manager/kênh an toàn.
7. Cập nhật client/automation để sử dụng phiên bản mới, loại bỏ key cũ khỏi runtime/config, kiểm tra retries và quyền hiệu lực.
8. Xác minh credential cũ bị từ chối ở nơi có thể kiểm tra an toàn; kiểm tra credential mới hoạt động **chỉ** trong phạm vi được duyệt.

**Cảnh báo:** không thử “kiểm chứng” bằng cách dùng token nghi lộ truy cập dữ liệu thật ngoài phạm vi được phép. Ưu tiên audit/metadata, test account hoặc phép thử hạn chế đã được chủ ứng dụng duyệt.

### 9.3. Ví dụ giả lập về kết quả xác minh

~~~yaml
credential_ref: api-key-id-42
issuer: billing-saas
owner_ref: billing-integration-owner
revocation_requested_at: "2026-11-23T15:05:00+07:00"
issuer_revocation_status: CONFIRMED
resource_access_after_revocation: DENIED
related_token_review: COMPLETED
new_credential_ref: api-key-id-43
new_scope: billing-invoice-read
production_health_check: PASS
~~~

Mẫu **không chứa giá trị credential**. Trên hệ thống thật, trạng thái của resource server, thời gian propagation và API log phải được thu thập theo khả năng của nền tảng.

## 10. SOP-CL06 — Service account, client secret và secret rotation

Credential của **service account, service principal, workload identity hoặc CI/CD** thường được nhiều instance sử dụng, có thể chạy liên tục và có các dependency khó thấy. Một secret lộ có thể cho phép truy cập dữ liệu, triển khai sản phẩm hoặc sinh credential mới nếu quyền cấp quá rộng.

### 10.1. Danh mục phụ thuộc trước rotation

Thu thập thông tin bằng tham chiếu an toàn:

- **Service/workload ID** và owner nghiệp vụ + owner kỹ thuật.
- **Môi trường**: dev, staging, production; tenant/project, region và hệ thống đích.
- **Ứng dụng sử dụng**: job theo lịch, worker, container, VM, CI pipeline, serverless, agent hoặc integration SaaS.
- **Secret location/version** trong vault và cơ chế phân phối tới workload; tránh đọc/in secret thô.
- **Scope/quyền** của service identity, đặc quyền cloud IAM, role trong dữ liệu và trust relation.
- **Tính sẵn sàng**: việc revoke tức thì có làm dừng chức năng trọng yếu không, có credential thay thế/rollover đã được thiết kế không?

### 10.2. Thứ tự rotate có kiểm soát

1. Khi có bằng chứng lạm dụng hoặc quyền rất nhạy cảm, SOC/owner có thể yêu cầu **disable/revoke ngay** kèm phương án continuity được phê duyệt.
2. Với workload cần duy trì dịch vụ và cho phép rollover, cấp credential mới qua secret manager với **phạm vi tối thiểu**, ghi version/owner/expiry.
3. Cập nhật workload instances, CI/CD và cấu hình tích hợp **qua công cụ phân phối secret an toàn**; không commit giá trị vào source hay log pipeline.
4. Kiểm tra workload hoạt động với credential mới, tại đúng môi trường và quyền tối thiểu; giám sát API auth failure.
5. **Thu hồi credential cũ ngay khi điều kiện thay thế đạt** theo mức rủi ro. Nếu có thời gian chồng lấp, thời hạn phải được owner Security phê duyệt, giám sát và càng ngắn càng phù hợp.
6. Đọc lại trạng thái issuer/vault và kiểm chứng credential cũ không thể sử dụng trong phạm vi cần thiết; rà token/session sinh ra trước khi revoke.
7. Loại bỏ bản sao secret cũ khỏi cấu hình, image/artifact, backup/log đang truy cập công khai theo quy trình bảo quản chứng cứ và retention.
8. Ghi lại nguyên nhân exposure, cập nhật guardrail ngăn hardcode, CI log leak, quyền vault quá rộng và rotation thiếu nhất quán.

### 10.3. Các bẫy cần tránh

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Rotate trong vault nhưng instance chưa reload | Ứng dụng vẫn dùng key cũ hoặc ngừng chạy | Inventory dependency, rollout và xác minh từng instance |
| Giữ secret cũ vô thời hạn “phòng lỗi” | Credential nghi lộ vẫn sử dụng được | Chồng lấp có hạn và owner, revoke có kiểm chứng |
| Dùng token admin cá nhân thay service secret | Mất truy vết, vượt quyền, phụ thuộc vòng đời nhân viên | Dùng service identity phù hợp và audit |
| Xóa service account ngay khi owner nghỉ việc | Có thể làm ngừng production | Chuyển owner, rà quyền, rotate credential và xử lý dependency |
| Rotate secret nhưng giữ scope admin rộng | Quyền tiếp tục vượt nhu cầu | Kết hợp least privilege và review RBAC/ABAC |
| Không tìm container image/artifact chứa secret | Credential vẫn phơi lộ qua image/cache | Xác định artifact, thu hồi access và xử lý bản sao theo policy |

**Cải tiến dài hạn:** cân nhắc managed identity, workload federation hoặc short-lived credentials thay secret tĩnh nếu hạ tầng hỗ trợ. Nhưng credential ngắn hạn **không tự bảo đảm** least privilege; role, trust và quyền tài nguyên vẫn cần rà soát.

## 11. SOP-CL07 — SSH key, certificate, signing key và trust

Khóa riêng và chứng chỉ có nhiều ngữ nghĩa khác nhau. **Không thể áp dụng cùng một thao tác reset password cho SSH key, mTLS private key, application signing key và SAML signing key.**

### 11.1. SSH key bị lộ

1. Xác định owner, fingerprint, nơi public key được chấp nhận, host, user, authorized keys, SSH certificate authority nếu có và thời điểm sử dụng.
2. Theo incident policy, gỡ public key khỏi các target hoặc thu hồi SSH certificate/trust tương ứng; kiểm tra account local, agent forwarding và session/connection đang hoạt động.
3. Cấp key pair mới qua quy trình an toàn, ràng buộc đúng owner và tài nguyên; không sao chép private key vào ticket.
4. Đọc auth logs và hoạt động trên host, rà persistence/privilege escalation khi nghi đã dùng trái phép; phối hợp SOC.
5. Kiểm chứng khóa cũ không còn được chấp nhận, khóa mới chỉ hoạt động trong phạm vi cho phép.

### 11.2. mTLS/private key chứng chỉ bị lộ

Xác định private key tương ứng certificate nào, endpoint/client nào dùng, CA/trust store, thời hạn và revocation mechanism. Phương án có thể bao gồm cấp lại key pair/certificate, revoke theo cơ chế CA, cập nhật trust, triển khai thay thế theo thứ tự đã kiểm thử và theo dõi TLS lỗi. Một số hệ thống kiểm tra CRL/OCSP, hệ thống khác không; phải **xác minh cơ chế tin cậy và mức lan truyền thực tế** thay vì giả định revoke tại CA tự chặn mọi kết nối.

### 11.3. Signing key dùng cho SSO/token

Nếu private key ký SAML assertion, OIDC/JWT hoặc token nội bộ bị nghi lộ, phạm vi có thể rất lớn vì key liên quan tới **niềm tin của nhiều relying party/resource server**.

- Kích hoạt điều phối IAM/SOC/PKI ở mức ưu tiên cao tương ứng.
- Xác định issuer, key ID/certificate, tập ứng dụng tin cậy, thời hạn token và khả năng dùng key bị lộ.
- Lập kế hoạch rotate/revoke trust theo thiết kế: cập nhật JWKS/metadata, relying party cache và hệ thống kiểm tra chữ ký.
- Đánh giá token đã phát hành, cơ chế deny/revocation, khả năng phát hiện token giả mạo, giám sát signing events.
- Canh chừng availability: thay key thiếu phối hợp có thể làm mọi ứng dụng SSO thất bại; nhưng giữ key nghi lộ được trust cũng có rủi ro cao.
- **Không tắt xác minh chữ ký, issuer, audience, expiration hoặc nonce** để “khôi phục” đăng nhập.

### 11.4. Phân biệt certificate hết hạn và private key bị lộ

Chứng chỉ **hết hạn** gây lỗi tin cậy/availability, trong khi **private key bị lộ** là nguy cơ danh tính giả mạo. Hai tình huống có thể cùng gây gián đoạn khi rotate nhưng cần hướng điều tra bảo mật khác nhau.

## 12. SOP-CL08 — Repository, pipeline, log, thiết bị và nơi phơi lộ

Việc xử lý credential nghi lộ thường có **hai đường công việc riêng nhưng liên quan**: **vô hiệu hóa credential** để ngăn sử dụng và **xử lý nơi lộ** để ngăn đọc tiếp. Xóa một dòng source code không vô hiệu hóa token đang hoạt động.

### 12.1. Secret xuất hiện trong Git/repository

1. Báo SOC/owner qua tham chiếu commit/file/branch, không sao chép secret.
2. Đánh giá repo public/private, fork, mirror, clone, CI artifacts và những người có quyền đọc.
3. **Revoke/rotate secret trước hoặc đồng thời với xử lý code**, theo mức nguy cấp; không chờ làm sạch toàn bộ lịch sử mới vô hiệu hóa.
4. Sửa ứng dụng dùng secret bằng cách lấy từ vault/secret manager, loại bỏ hardcode và kiểm thử.
5. Theo quy trình được owner và Security duyệt, xử lý nơi lộ hiện tại, các artifact và lịch sử chứa secret khi khả thi. Lưu ý rebase/rewrite history có thể ảnh hưởng cộng tác và **không bảo đảm xóa bản sao đã clone/fork**.
6. Bổ sung secret scanning ở pre-commit/CI, policy review, quyền repository/artifact và cảnh báo để ngăn tái diễn.

### 12.2. Token được ghi vào log/telemetry

Định vị logger, tracer, middleware, reverse proxy hoặc error reporting đã ghi credential; tắt/che trường nhạy cảm qua change được phê duyệt. Xác định phạm vi người xem log, export, retention, backup và các công cụ thứ ba nhận telemetry. Revoke/rotate credential liên quan; giữ log điều tra ở kho giới hạn quyền rồi xử lý bản sao theo chính sách.

Không dùng một regex “che secret” làm bằng chứng đã an toàn nếu credential vẫn còn ở log cũ hoặc chỉ bị che ở giao diện nhưng vẫn có thể truy xuất qua API.

### 12.3. Thiết bị mất hoặc nghi bị xâm nhập

Khi credential lưu trên thiết bị mất hoặc malware có thể đọc key/token, phối hợp Endpoint/SOC cô lập thiết bị, revoke phiên và credential có khả năng bị đánh cắp, kiểm tra tài khoản/MFA, sau đó phục hồi trên thiết bị tin cậy. Không chỉ đổi password trên chính thiết bị đang nghi nhiễm nếu chưa có kiểm soát phù hợp.

### 12.4. Chia sẻ nhầm qua email/chat/tài liệu

Thu hẹp ACL, thu hồi quyền xem tài liệu nếu có, xác định người nhận và lịch sử truy cập, sau đó revoke/rotate credential. Thu hồi/xóa thông điệp có thể hạn chế phơi lộ bổ sung nhưng không bảo đảm người nhận chưa sao chép nội dung.

## 13. Điều tra dấu hiệu lạm dụng và mở rộng phạm vi

Thu hồi credential là bước giảm rủi ro trước mắt. Để biết có cần ứng phó sự cố rộng hơn, cần điều tra **credential đã được dùng thế nào trong cửa sổ phơi lộ**.

### 13.1. Thiết lập timeline

Các mốc thường cần xác định:

- **T0 – Có khả năng bắt đầu phơi lộ:** commit đầu tiên, thời điểm file/log được công khai hoặc thiết bị mất.
- **T1 – Lần sử dụng hợp lệ đã biết** trước và trong khoảng rủi ro.
- **T2 – Dấu hiệu truy cập bất thường đầu tiên** nếu có.
- **T3 – Thời điểm phát hiện và mở incident**.
- **T4 – Thời điểm containment và revoke được xác nhận** ở issuer/đích.
- **T5 – Thời điểm xác minh credential cũ không còn khả năng truy cập** theo cơ chế hệ thống.

Timeline phải nêu múi giờ, độ trễ thu thập log và **điểm không chắc chắn**. Nếu T0 không xác định được, phải mô tả cửa sổ điều tra đã lựa chọn và giới hạn của dữ liệu.

### 13.2. Các dấu hiệu nên rà soát

| Nhóm | Dấu hiệu |
|---|---|
| **Đăng nhập/IdP** | Sign-in success lạ, client/IP/device chưa từng thấy, tăng MFA enroll/reset, đăng nhập thất bại bất thường |
| **API/resource** | Tăng API calls, truy cập dataset mới, bulk export/download, gọi endpoint admin |
| **Quyền** | New role grants, group membership, thêm user, permission escalation, đổi policy/SoD exception |
| **Credential** | Tạo PAT/API key mới, rotate trái phép, thêm SSH authorized key, đổi secret vault, token grants mới |
| **Tính bền vững** | OAuth consent/app registration, cron/job, webhook, automation identity hoặc local account được tạo bất thường |
| **Chuyển dữ liệu** | Object storage reads, database dumps, repository clone, file download và các kênh xuất dữ liệu |
| **Service workloads** | CI run lạ, deployment không dự kiến, secret read từ vault, cloud role assumption |

**Không kết luận lạm dụng chỉ vì IP khác**; cần xét VPN, NAT, công tác, automation hợp lệ và ngữ cảnh. Ngược lại, một IP quen cũng có thể bị sử dụng bởi thiết bị hoặc tác nhân không được phép.

### 13.3. Scope creep của sự cố

Credential ban đầu có thể đã được dùng để **tạo credential mới hoặc thay đổi quyền**. Vì thế, sau khi revoke, phải kiểm tra quyền và credential phát sinh. Nếu một tài khoản bị chiếm đã thêm admin vào nhóm, reset password của tài khoản đó không tự gỡ grant đã cấp cho tài khoản khác.

SOC quyết định khi nào cần chuyển sang điều tra sâu, forensic trên endpoint/server, bảo toàn chứng cứ pháp lý và thông báo theo nghĩa vụ tổ chức. IAM Operations cung cấp metadata quyền/trạng thái mà không tự ý truy cập nội dung dữ liệu cá nhân ngoài phạm vi được ủy quyền.

## 14. Mối liên hệ với vòng đời Joiner–Mover–Leaver

### 14.1. Joiner: cấp credential mới đúng người, đúng thời điểm

Quy trình Joiner phải xác minh danh tính trước khi cấp account và phương thức đăng nhập. Nếu một mật khẩu tạm hoặc liên kết kích hoạt bị lộ trước ngày bắt đầu:

1. Xác minh nguồn HR/sponsor, subject ID, thời điểm hiệu lực và phương thức đã giao thông tin.
2. Thu hồi credential/link bị lộ, đánh giá xem có đăng nhập/tạo MFA/khôi phục tài khoản trái phép chưa.
3. Cấp lại thông tin qua kênh an toàn với identity proofing; không kích hoạt sớm hoặc tự cấp quyền rộng.
4. Đối chiếu IdP, SSO, SCIM và entitlement RBAC/ABAC của các ứng dụng bắt buộc sau khi credential mới hoạt động.

**Ví dụ:** link kích hoạt account Joiner được chuyển nhầm vào nhóm chat công khai. Dù link có thể hết hạn nhanh, IAM vẫn phải xác định còn hiệu lực không, thu hồi nếu cần, kiểm tra đăng ký MFA/phiên đã tạo và cấp lại link theo người được xác minh.

### 14.2. Mover: credential cũ và quyền cũ có thể tồn tại song song

Một người chuyển từ Support sang Finance có thể giữ PAT cấp từ ứng dụng Support, SSH key vào môi trường cũ hoặc access token có claim/role cũ dù nhóm IdP đã thay. Khi credential bị nghi lộ trong giai đoạn Mover:

1. Đọc **latest lifecycle state** và danh sách role/quyền đã được duyệt ở vai trò mới.
2. Thu hồi credential nghi lộ và quyền cũ không còn cần; kiểm tra API token, local grants, nested groups, PAM và SSO session.
3. Cấp credential mới với scope/role **theo công việc hiện tại**, không sao chép toàn bộ quyền cũ.
4. Kiểm tra SoD, tính hiệu lực của ABAC và độ trễ SCIM/group claim.
5. Xác minh cả thao tác mới được phép và thao tác cũ đã bị từ chối.

Không tái cấp quyền Support chỉ để khôi phục PAT cũ; đó có thể tạo **residual access**.

### 14.3. Leaver: credential còn tồn tại là vấn đề ưu tiên

Leaver có hiệu lực phải bị chặn đăng nhập và thu hồi quyền theo chính sách. Một nhân viên/nhà thầu đã nghỉ vẫn có thể sở hữu:

- API key, PAT, token và session được ứng dụng phát riêng.
- SSH key, VPN credential, local account, shared secret hoặc quyền ủy quyền.
- Quyền admin tại cloud/PAM hoặc owner của ứng dụng/secret.
- Credential gắn với workflow mà trước đây chỉ họ biết, nhưng workload production vẫn cần vận hành.

Khi phát hiện credential của Leaver bị lộ, xử lý ngay theo rủi ro: **thu hồi credential, chặn account, xử lý session/role độc lập, đối soát app và lưu evidence**. Nếu SCIM/IdP lỗi, phối hợp owner để disable/revoke tại ứng dụng còn kiểm soát được và giữ ngoại lệ có hạn chót. Không phục hồi account Leaver để tải dữ liệu; dùng quy trình bàn giao/ủy quyền.

### 14.4. Tái tuyển dụng, reactivation và sửa danh tính

Một người quay lại tổ chức không tự động được sử dụng credential/token cũ. Cần xác minh sự kiện JML mới, role hiện hành, MFA và policy; cấp lại phương thức truy cập phù hợp. Nếu username/email được tái sử dụng, đối chiếu theo **immutable subject ID** để tránh gán credential của người trước cho người mới.

## 15. RBAC/ABAC, SCIM và việc giảm quyền truy cập tồn dư

### 15.1. Thu hồi credential khác với thu hồi quyền

Đổi secret làm giảm khả năng dùng **secret cũ**, nhưng không tự động xóa role hoặc grant của một danh tính. Nếu identity bị chiếm đã cấp quyền cho principal khác, **credential rotation không gỡ quyền đó**. Phải đối soát actual–desired ở tất cả target liên quan.

### 15.2. RBAC và ABAC sau credential compromise

- **RBAC:** rà group, role trực tiếp/kế thừa, đặc quyền tạm thời và vai trò được tự gán.
- **ABAC:** rà thuộc tính department/project/location, điều kiện thiết bị/time/risk và rule cho resource bị tác động.
- **SoD:** kiểm tra quyền tạo và phê duyệt đồng thời, đặc biệt khi có grant mới bất thường.
- **PAM/JIT:** rà phiên nâng quyền, standing privilege, key/token admin, break-glass và audit session.
- **Ứng dụng:** xem local user, permission, token scope và tài nguyên nằm ngoài catalog IdP.

**Điểm kiểm chứng:** trạng thái quyền hiệu lực (*effective access*) phải phù hợp với **desired state** từ lifecycle, role hiện hành, approval và policy, không chỉ nhìn thấy nhóm IdP đã thay.

### 15.3. SCIM và deprovisioning

SCIM có thể đồng bộ user/group và đặt user inactive (ví dụ `active=false`) tại ứng dụng hỗ trợ. Nhưng **SCIM deactivation không mặc nhiên revoke toàn bộ session/API key**. Với target không hỗ trợ API thu hồi quyền, cần nhiệm vụ thủ công được quản lý.

Nếu đã disable tại ứng dụng nhưng provisioning job cũ vẫn giữ `desired = active`, connector có thể kích hoạt lại user sau đó. Phải sửa authoritative state, version guard và chạy reconciliation sau khi connector phục hồi.

### 15.4. Thu hồi từ nhiều đường grant

| Đường còn mở | Ví dụ | Kiểm tra sau xử lý |
|---|---|---|
| IdP group | Role cũ qua nested group | Group membership/authorization thực tế |
| App-local role | Gán quyền admin trực tiếp | App permission và test deny hợp lệ |
| Session/token | Token cũ còn scope admin | Revoke/deny, expiry và resource-side validation |
| PAT/API key | API độc lập với SSO | Issuer status và API access sau revoke |
| Cloud IAM | Assume-role hoặc service principal | IAM policy/trust và audit tại cloud resource |
| SSH/VPN | Key hoặc certificate còn được chấp nhận | Endpoint auth state và kết nối liên quan |
| Service identity | Credential workload, role rộng | Workload account, secret vault và quyền resource |

## 16. Credential compromise khi IdP, vault hoặc connector lỗi

Trong sự cố, hệ thống thu hồi credential cũng có thể không khả dụng. Runbook phải nêu **đường hạn chế truy cập thay thế theo khả năng và quyền được phép**, đồng thời tránh kết luận giả rằng tất cả credential đã bị chặn.

### 16.1. IdP outage

Nếu IdP không cho reset password/revoke token, kiểm tra các đường còn điều khiển được: resource policy, ứng dụng local, VPN, PAM, proxy/gateway và account SaaS. Với thông tin đăng nhập bị nghi chiếm quyền, Security có thể áp biện pháp chặn tạm có kiểm soát; **không tự tạo SSO bypass thiếu audit/MFA**.

### 16.2. Vault hoặc secret service outage

Nếu không đọc/cấp secret mới, phối hợp Platform/owner theo quy trình khẩn cấp đã chuẩn bị; ưu tiên containment ở issuer/target nếu còn khả năng. Không copy secret sang file/chat hoặc tạo bản lưu không kiểm soát để “vượt vault”. Khi service khôi phục, đối soát secret version, owner và mọi instance đang dùng.

### 16.3. API revoke bị timeout hoặc trả lỗi

| Tín hiệu | Quyết định |
|---|---|
| `401/403` | Xác minh quyền connector/quản trị; không mở rộng scope tùy tiện |
| `404` | Đối chiếu key/user ID và trạng thái thực; có thể đã bị xóa |
| `409/412` | Xem conflict/version; đọc lại và xử lý đúng đối tượng |
| `429` | Tôn trọng `Retry-After`, backoff có jitter, ưu tiên credential rủi ro |
| `5xx/timeouts` | Đặt `UNKNOWN` và đọc trạng thái đích trước retry |
| `2xx` | Đã được API chấp nhận theo semantics, cần verify resource-side |

Với credential có quyền rủi ro cao còn có thể sử dụng, không chờ retry vô thời hạn. Mở `EXCEPTION_OPEN` có owner, deadline, biện pháp containment thay thế và escalation SOC.

## 17. Quản lý bằng chứng, audit và truyền thông sự cố

### 17.1. Hồ sơ vận hành mẫu

~~~yaml
incident_id: IAM-CRED-EXAMPLE-061
classification: EXPOSED_CREDENTIAL
credential_type: SERVICE_API_KEY
credential_ref: key-id-42
issuer: billing-saas
subject_ref: svc-billing-sync
owner_ref: billing-platform-team
detected_at: "2026-11-23T14:35:00+07:00"
exposure_source_ref: repository-commit-ref-102
exposure_window:
  earliest_known: "2026-11-22T08:00:00+07:00"
  latest_possible: "2026-11-23T14:40:00+07:00"
  certainty: ESTIMATED
decision_refs:
  - soc-triage-061
  - change-approval-061
containment:
  action: revoke-key-and-restrict-resource
  at: "2026-11-23T14:45:00+07:00"
  evidence_ref: issuer-audit-771
rotation:
  new_credential_ref: key-id-43
  distributed_via: approved-secret-manager
  workload_verification: PASS
investigation:
  access_review_ref: billing-api-audit-090
  suspicious_usage: NOT_CONFIRMED
  visibility_limit: limited-logs-before-2026-11-22
verification:
  old_credential: DENIED
  new_credential_scope: VERIFIED_MINIMUM
  access_review: COMPLETED
exceptions: []
case_status: CLOSED
~~~

**Tất cả ID và thời điểm trên là giả lập.** Không đưa password, token, private key, cookie hay mã khôi phục vào audit. Nếu cần lưu nội dung phơi lộ nguyên gốc vì điều tra, phải lưu trong kho bằng chứng được bảo vệ theo quy trình; ticket chỉ dẫn tới mã tham chiếu.

### 17.2. Những bằng chứng cần nối được

1. **Nguồn phát hiện:** alert, user report, audit event, repository/asset reference.
2. **Phạm vi credential:** issuer, ID, owner, resource, quyền và thời gian có thể đã lộ.
3. **Quyết định:** phân loại rủi ro, người phê duyệt, biện pháp containment và thay đổi theo incident policy.
4. **Hành động:** revoke/rotate/disable, session/token/role changes, người thực hiện, thời điểm và kết quả hệ thống.
5. **Điều tra:** sign-in/API activity, quyền phát sinh, sự kiện truy cập nhạy cảm, giới hạn visibility.
6. **Kiểm chứng:** credential cũ bị từ chối; credential mới quyền tối thiểu; ứng dụng và JML hoạt động đúng.
7. **Đóng hồ sơ:** root cause, thay đổi chống tái diễn, ngoại lệ còn mở và lịch follow-up.

### 17.3. Truyền thông với người dùng và chủ ứng dụng

Thông điệp hỗ trợ cần nêu rõ **hành động cần thực hiện theo kênh an toàn**, ví dụ reset password qua portal IdP chính thức, kiểm tra MFA, ngừng dùng token cũ và cập nhật integration. Không yêu cầu người dùng trả lời email chứa password/OTP hoặc mở một URL không được xác minh.

Nếu phát hiện có khả năng dữ liệu cá nhân đã bị truy cập, chuyển Legal/Privacy/Compliance theo quy trình tổ chức để xác định nghĩa vụ và nội dung thông báo. IAM không tự công bố kết luận vượt bằng chứng có được.

## 18. Giám sát, chỉ số và điều kiện phục hồi

### 18.1. Các chỉ số nên có

| Metric | Ý nghĩa |
|---|---|
| **Time to detect** | Từ thời điểm có khả năng bắt đầu phơi lộ đến lúc hệ thống/người vận hành phát hiện; ghi độ không chắc chắn |
| **Time to containment** | Từ phát hiện/triage đến khi hạn chế được đường sử dụng theo tiêu chí đã xác định |
| **Time to verified revocation** | Từ incident tới lúc issuer/đích xác nhận credential cũ không còn sử dụng được |
| **Active exposed credentials** | Số credential nghi lộ còn active, phân loại theo mức quyền và tuổi |
| **Rotation coverage** | Tỉ lệ workload/instance đã nhận secret version mới |
| **Compromised session/token backlog** | Số session/token/key cần xử lý nhưng chưa verified |
| **Residual privilege count** | Quyền từ credential/tài khoản bị ảnh hưởng vẫn lệch desired state |
| **Repeat exposure rate** | Số lỗi lộ secret lặp lại cùng root cause hoặc source |
| **Secret scanner signal quality** | Tỉ lệ cảnh báo đúng, bỏ sót được phát hiện, thời gian phân loại |
| **Leaver credential residue** | Credential của tài khoản Leaver vẫn hoạt động sau thời điểm hiệu lực |
| **Exceptions overdue** | Các target/credential chưa thu hồi có owner/deadline nhưng quá hạn |

Các chỉ số không có SLA cố định áp dụng cho mọi tổ chức. Đối với credential đặc quyền hoặc khả năng truy cập dữ liệu nhạy cảm đang hoạt động, thường cần phản ứng ưu tiên cao theo chính sách; đồng thời phân biệt **đã gửi yêu cầu revoke**, **đã áp dụng**, và **đã xác minh bị từ chối**.

### 18.2. Tiêu chí đóng incident

| Câu hỏi kiểm tra | Yêu cầu nghiệm thu |
|---|---|
| Credential bị lộ đã nhận diện đúng? | ID/fingerprint, issuer, owner, loại và scope đã xác nhận |
| Khả năng dùng credential cũ đã bị chặn? | Có readback/revocation evidence, hoặc ngoại lệ rủi ro được quản lý rõ ràng |
| Session/token/credential dẫn xuất đã xử lý? | Điều tra đủ phạm vi và thu hồi khi cần |
| Quyền và danh tính vẫn đúng JML? | Desired–actual reconciliation qua IdP, SCIM/app, RBAC/ABAC |
| Không phát sinh tài khoản/quyền lạ? | Đã kiểm tra sign-in, admin grants, MFA recovery, OAuth consent, key creation |
| Credential mới an toàn và tối thiểu? | Secret manager, owner, expiry/rotation, scope đúng và kiểm thử nghiệp vụ |
| Nơi phơi lộ đã được khắc phục? | Source/log/artifact/ACL được xử lý theo retention và evidence policy |
| Audit và ngoại lệ đầy đủ? | Ticket, quyết định, timeline, evidence, owner và deadline rõ ràng |
| Đã giám sát sau phục hồi? | Khoảng quan sát bao phủ traffic/job chu kỳ cần thiết, không thấy tái lộ hoặc regrant |

Nếu còn mục không kiểm chứng được, không báo “credential đã an toàn hoàn toàn”. Có thể tách trạng thái **khả năng sử dụng credential đã bị chặn** khỏi các hoạt động điều tra dài hơn, nhưng mọi ngoại lệ phải có owner và thời hạn.

## 19. Tình huống thực hành và hướng giải

### Tình huống A — PAT bị commit vào repository

Một kỹ sư vô tình commit PAT có quyền ghi repository. Secret scanner phát hiện sau khi branch đã được chia sẻ cho nhiều người.

**Hướng xử lý:** tạo incident và xác định PAT ID, scope/repo, quyền đọc branch và thời gian phơi lộ. Revoke PAT tại issuer, rà hoạt động Git/API và key/role phát sinh, cấp PAT mới giới hạn quyền nếu nghiệp vụ cần. Sửa code dùng secret manager, xử lý commit/artifact theo policy và xác minh PAT cũ không hoạt động. Không chỉ xóa dòng chứa PAT rồi đóng ticket.

### Tình huống B — Nhân viên bị phishing và có dấu hiệu MFA bị thay

Một người dùng nhập password vào trang giả và sau đó IdP ghi nhận đăng ký phương thức MFA mới. Nhân viên thông báo vẫn đăng nhập được.

**Hướng xử lý:** SOC coi là nghi account takeover, kiểm tra sign-in lạ, session, OAuth consent và MFA methods. Khóa đường truy cập rủi ro, reset password/thu hồi phiên theo chính sách, vô hiệu phương thức MFA trái phép, re-enroll qua identity proofing và rà role/grants. Không dựa vào một lần login thành công để kết luận an toàn.

### Tình huống C — API key nhà thầu đã nghỉ vẫn dùng được

HR xác nhận nhà thầu kết thúc hợp đồng, IdP disabled nhưng ứng dụng SaaS còn API key được tạo trước đó.

**Hướng xử lý:** ưu tiên revoke key tại SaaS, kiểm tra local user/session và role, rà mọi credential khác của nhà thầu. Tạo evidence về API bị từ chối sau revoke, sửa quy trình Leaver để inventory API key thay vì chỉ disable IdP; cập nhật exception nếu target không thể kiểm chứng ngay.

### Tình huống D — Service account secret lộ trong log production

Một ứng dụng ghi `Authorization` header vào central logs trong hai ngày. Secret dùng bởi nhiều worker.

**Hướng xử lý:** giới hạn quyền đọc log và che trường gây lộ, giữ bằng chứng cần thiết, xác định scope/owner của secret. Rotate qua vault, cập nhật các worker, revoke secret cũ sau kiểm thử phù hợp với rủi ro, rà API audit trong thời gian lộ và xử lý log cũ theo retention. Không paste giá trị secret vào ticket để “đối chiếu”.

### Tình huống E — Private key SAML signing nghi bị sao chép

Hệ thống cảnh báo người không có thẩm quyền truy cập kho chứa private key được IdP sử dụng để ký assertion cho nhiều ứng dụng.

**Hướng xử lý:** kích hoạt SOC/IAM/PKI với phạm vi trust toàn bộ relying parties, bảo vệ chứng cứ, lập kế hoạch rotate key/metadata, đánh giá khả năng giả mạo assertion và token đã phát hành, xác minh chữ ký/issuer/audience ở từng ứng dụng. Không tắt signature verification để tránh gián đoạn.

### Tình huống F — Credential bị lộ khi IdP outage

Mật khẩu admin có dấu hiệu bị lộ, nhưng API IdP dùng để reset đang timeout; một số hệ thống cloud vẫn nhận session/token hiện có.

**Hướng xử lý:** kích hoạt SOC/PAM, dùng đường kiểm soát còn hoạt động để hạn chế quyền tại resource, revoke session/token ở hệ thống hỗ trợ, giám sát hoạt động admin. Đánh dấu các thao tác IdP chưa thực hiện và xử lý ngay khi phục hồi; không báo sự cố đã chặn chỉ vì user không thể mở màn hình SSO.

### Tình huống G — Mover có token cũ vượt vai trò mới

Một nhân viên chuyển sang vai trò chỉ đọc nhưng vẫn giữ PAT có scope ghi dữ liệu dự án cũ.

**Hướng xử lý:** đối chiếu sự kiện Mover và desired access, revoke PAT cũ, kiểm tra token khác, role trực tiếp/kế thừa và hoạt động trên tài nguyên cũ; cấp credential mới nếu cần với scope read-only. Kiểm chứng vừa có quyền mới hợp lệ, vừa không còn ghi được dự án cũ.

### Tình huống H — Credential đã hết hạn từ trước khi bị lộ

Secret scanner phát hiện một chuỗi trông như API key trong commit cũ. Metadata issuer xác nhận key đã bị thu hồi **trước ngày commit** và không liên kết tài khoản nào còn active.

**Hướng xử lý:** ghi bằng chứng trạng thái vô hiệu và thời điểm, đánh giá xem có bản sao/credential liên quan khác còn hiệu lực không. Xử lý code hygiene và rule scanner; không kết luận có compromise nếu thiếu bằng chứng, nhưng cũng không bỏ qua việc đánh giá source và mẫu lỗi.

## 20. Checklist thao tác nhanh và các nguyên tắc phải nhớ

### 20.1. Checklist cho IAM Operations và SOC

| Giai đoạn | Câu hỏi phải trả lời |
|---|---|
| **Intake** | Có incident ID, nguồn phát hiện, thời điểm, owner và evidence reference chưa? |
| **Classify** | Credential là password, token, PAT, service secret, SSH, certificate, MFA hay signing key? |
| **Scope** | Credential còn active? Issuer nào? Có quyền gì, truy cập tài nguyên nào? |
| **JML** | Chủ thể là Joiner, Mover, Leaver hay workload với owner hợp lệ? |
| **Containment** | Đã chặn đường sử dụng và credential dẫn xuất theo mức rủi ro chưa? |
| **Rotation** | Secret mới được cấp an toàn, đúng scope, owner và phụ thuộc sản xuất? |
| **Investigation** | Đã rà sign-in/API, key/token creation, grant thay đổi, truy cập dữ liệu và giới hạn log? |
| **Authorization** | IdP/SCIM/RBAC/ABAC/PAM/app grants đã được đối soát actual–desired? |
| **Verification** | Credential cũ bị từ chối; credential mới và quyền hợp lệ hoạt động? |
| **Hygiene** | Đã xử lý nơi lộ, log/CI/repository/vault ACL và guardrail? |
| **Closure** | Có audit, RCA, monitoring, owner và deadline cho ngoại lệ? |

### 20.2. Sáu nguyên tắc cốt lõi

1. **Đừng phát tán secret khi điều tra:** dùng ID/fingerprint và kho bằng chứng có kiểm soát.
2. **Thu hồi ở đúng issuer/đích:** password reset, SSO logout, SCIM disable và revoke API key/session là các thao tác khác nhau.
3. **Contain trước khi rủi ro lan rộng:** vừa bảo toàn bằng chứng vừa chặn đường sử dụng credential còn hiệu lực.
4. **Điều tra credential dẫn xuất và quyền phát sinh:** token khác, MFA method, app consent, IAM role và account lạ không tự biến mất sau rotate.
5. **Tôn trọng vòng đời và least privilege:** không cấp lại quyền cũ của Mover hoặc kích hoạt lại Leaver; workload có owner và scope rõ ràng.
6. **Đóng bằng kết quả kiểm chứng:** credential cũ không còn được chấp nhận, quyền thực tế phù hợp desired state, nguồn rò rỉ đã được xử lý và audit đủ bằng chứng.

Một quy trình **xử lý credential bị lộ** hiệu quả cần bảo vệ cả **tính bí mật của credential** lẫn **tính đúng đắn của quyền truy cập sau sự cố**. Phục hồi chỉ đáng tin cậy khi người và workload hợp lệ vẫn vận hành với quyền tối thiểu, trong khi mọi credential, session và quyền truy cập tồn dư không còn hợp lệ đều đã được thu hồi hoặc được quản lý như ngoại lệ có kiểm soát.
