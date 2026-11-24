# Session timeout: giới hạn thời gian phiên, kiểm soát truy cập tồn dư và thực thi trong IAM

**Session timeout (hết hạn phiên)** là cơ chế giới hạn **khoảng thời gian một phiên xác thực/truy cập còn được hệ thống chấp nhận**. Khi vượt điều kiện thời gian được quy định, hệ thống phải yêu cầu xác thực lại, kết thúc phiên hoặc từ chối những hành động không còn được phép theo chính sách. Timeout giúp giảm thời gian kẻ tấn công có thể lợi dụng một phiên bị chiếm, hạn chế phiên bị bỏ quên trên thiết bị và bảo đảm quyền không tồn tại lâu hơn nhu cầu.

**Điểm cốt lõi:** Timeout **không chỉ là tự động chuyển giao diện về màn hình đăng nhập**. Phải biết **server, IdP, ứng dụng, API, token, kết nối và quyền tại tài nguyên** còn chấp nhận phiên hay không. Một cửa sổ trình duyệt bị ẩn hoặc cookie đã hết hạn ở client chưa chứng minh các session/token khác bị thu hồi.

Bài này thuộc chương **Session management** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tìm hiểu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo account và cấp quyền, rà soát, thu hồi khi đổi vai trò hoặc rời tổ chức. Nội dung kết nối **IdP, SSO, SCIM, RBAC/ABAC, PAM/PIM, tài khoản dịch vụ, kiểm toán** và mục tiêu **giảm quyền truy cập tồn dư**.

**Nguyên tắc:** Quy định timeout phải gắn với **rủi ro của phiên, dữ liệu, hành động và loại chủ thể**. Cơ chế **idle timeout, absolute timeout, token expiration, credential lifetime và event-driven revocation** giải quyết những vấn đề khác nhau; không được coi chúng là một đồng hồ duy nhất.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **session timeout** và phân biệt **idle/inactivity timeout, absolute/session lifetime, reauthentication, token expiry, cookie expiry và logout**.
2. Giải thích **sliding expiration** và vì sao hoạt động tự động hoặc request nền không nên tùy tiện gia hạn phiên của người.
3. Nhận diện các lớp session: **IdP/SSO, ứng dụng, backend server, API, access token, refresh token, PAM session, database connection, WebSocket**.
4. Hiểu vì sao **JWT hết hạn** không đồng nghĩa mọi phiên SSO bị kết thúc, và **logout ứng dụng** không luôn kết thúc session tại IdP.
5. Thiết kế kiểm tra thời hạn **ở phía server/Resource Server**, xử lý đồng hồ, đa thiết bị, concurrency và quyền truy cập hiện hành.
6. Cấu hình timeout khác nhau theo **rủi ro, môi trường, loại tài khoản và mức xác thực**, không dùng một con số tùy tiện cho mọi người.
7. Phân biệt timeout của người dùng với **credential/token lifetime của workload**, job dài hạn và service account.
8. Liên kết timeout với **Joiner, Mover, Leaver, access review, PAM/PIM, SCIM và event-driven revocation**.
9. Thiết kế logging/monitoring và negative tests để chứng minh **phiên thật sự không còn sử dụng quyền**.
10. Phân tích các lỗi điển hình: **session fixation, không ràng buộc TTL, auto-refresh mãi, stale authorization, token còn hạn và client-side-only timeout**.

## 2. “Session” trong ngữ cảnh IAM là gì?

Một **session (phiên)** là ngữ cảnh liên tục mà hệ thống dùng để nhận biết một chủ thể đã xác thực và áp dụng trạng thái, quyền hoặc chính sách cho các tương tác tiếp theo.

Phiên có thể hiện diện dưới nhiều hình thức:

- **Application web session:** Browser gửi session cookie, server tra trạng thái phiên.
- **Identity Provider session:** IdP ghi nhận người dùng đã xác thực để hỗ trợ SSO tới nhiều ứng dụng.
- **API authentication context:** Client gửi bearer access token; API dựa vào token và policy để quyết định.
- **Mobile app session:** Ứng dụng dùng access/refresh token và trạng thái đăng nhập cục bộ.
- **Privileged session:** Phiên SSH/RDP/DB/cloud console dùng quyền quản trị, có thể qua PAM.
- **Machine-to-machine context:** Workload dùng access token/client credential để gọi API, không có “người dùng ngồi trước màn hình” tương đương.
- **Long-lived connection:** WebSocket, SSH, VPN hoặc database connection có thể sống vượt thời gian của một HTTP request.

Một người có thể đăng nhập qua IdP một lần, sau đó đồng thời có **nhiều session tại nhiều ứng dụng**. Các session đó không nhất thiết cùng thời điểm bắt đầu, cùng timeout hay cùng cơ chế thu hồi.

### 2.1. Session khác authentication và authorization

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication** | Ai đang yêu cầu, đã chứng minh danh tính ra sao? | MFA tại IdP |
| **Session** | Ngữ cảnh đã được duy trì từ lần xác thực nào? | Session cookie của CRM |
| **Authorization** | Hành động trên resource này hiện được phép không? | `invoice.read@project-A` |
| **Timeout** | Ngữ cảnh còn hợp lệ đến khi nào? | Idle quá giới hạn thì reauthenticate |
| **Revocation** | Có cần làm mất hiệu lực trước hạn vì biến cố? | Nhân viên Leaver |
| **Reauthentication** | Có cần chứng minh lại danh tính/mức bảo đảm? | Step-up trước thao tác admin |

**Session còn hợp lệ không có nghĩa authorization không đổi.** Người dùng Mover có thể giữ session, nhưng quyền dự án cũ phải được kiểm lại và từ chối tại API.

## 3. Năm mốc thời gian thường bị nhầm

| Thuật ngữ | Bắt đầu tính | Điều kiện kết thúc | Không tự có nghĩa |
|---|---|---|---|
| **Idle timeout** | Hoạt động hợp lệ cuối cùng | Không có hoạt động được tính trong khoảng quy định | Token khác đã bị thu hồi |
| **Absolute timeout** | Mốc mở phiên/reauthentication nền tảng theo policy | Đến hạn cứng, kể cả đang hoạt động | Account phải bị xóa |
| **Authentication freshness** | Lần xác thực có giá trị gần nhất | Cần xác thực lại/step-up theo mức đảm bảo | Xóa mọi session ở ứng dụng khác |
| **Access token lifetime** | Token được phát/`nbf` | `exp` hoặc chính sách kiểm tra bổ sung | IdP SSO session kết thúc |
| **Refresh token/credential lifetime** | Phát refresh token hoặc credential | Hết hạn/rotation/revocation | Access token đã phát mất hiệu lực ngay |

Còn có **cookie lifetime**, **PAM session TTL**, **JIT role TTL**, **network connection timeout** và **account/engagement validity**. Không nên dùng chung tên biến `timeout` cho những thời hạn có ý nghĩa khác nhau.

### 3.1. Ví dụ minh họa

~~~text
08:00  Người dùng xác thực qua IdP
08:02  CRM tạo application session
08:10  Người dùng thao tác trong CRM
08:12  API cấp access token dùng 10 phút
08:20  Không có tương tác hợp lệ tiếp theo
08:25  CRM idle timeout 15 phút tính từ 08:10
10:00  IdP session có thể vẫn hợp lệ theo policy riêng

Kết quả:
  CRM session đã timeout ≠ IdP đã logout.
  Người dùng có thể được SSO vào lại CRM nếu IdP còn phiên,
  trừ khi CRM yêu cầu reauthentication tươi hơn.
~~~

Các mốc **10 phút, 15 phút** chỉ để mô tả quan hệ thời gian, **không phải khuyến nghị bảo mật chung**.

## 4. Idle timeout: hết hạn khi không hoạt động

**Idle timeout** giới hạn thời gian từ **hoạt động được hệ thống công nhận gần nhất** cho đến request hiện tại. Nếu khoảng này vượt ngưỡng, session phải bị coi là không hợp lệ theo policy.

Ví dụ:

~~~text
idleLimit = 15 phút (ví dụ)
lastEligibleActivity = 14:00
14:10: thao tác thật -> lastEligibleActivity = 14:10
14:25:01: request tiếp theo -> phiên hết hạn nếu policy
           quy định kiểm tra vượt 15 phút
~~~

### 4.1. “Activity” phải được định nghĩa

Không phải mọi request HTTP đều thể hiện một người còn hiện diện:

- Click, nhập dữ liệu, submit form hoặc điều hướng có chủ đích **có thể** được tính là activity khi được backend xác nhận.
- Auto-save, polling dashboard, analytics beacon, health check hoặc browser heartbeat **không nên mặc định** gia hạn phiên người dùng.
- Một script gọi API tự động trên nền bằng cookie của người có thể giữ session sống mãi nếu backend cập nhật `lastActivityAt` cho mọi request.
- Tab khác của cùng ứng dụng có thể dùng chung cookie; chính sách phải xác định activity của tab nào được tính.
- WebSocket ping/pong là dấu hiệu **kết nối còn sống**, không phải bằng chứng người dùng tương tác.

### 4.2. Server phải thực thi idle timeout

Một bộ đếm JavaScript hiển thị modal “Bạn sắp hết phiên” giúp trải nghiệm, nhưng **không được là nơi quyết định cuối**. Nếu người dùng xóa JavaScript, chỉnh thời gian trình duyệt hoặc gửi request trực tiếp, backend vẫn phải từ chối phiên đã idle timeout.

### 4.3. Idle timer và input chưa lưu

Khi sắp hết hạn, ứng dụng có thể hiển thị cảnh báo, cho phép gia hạn bằng tương tác hợp lệ hoặc lưu nháp an toàn. Không vì lo mất dữ liệu mà cho phiên tồn tại mãi. **Gia hạn cần xảy ra trước khi phiên đã hết hạn**, và nếu đã hết hạn phải xác thực lại theo policy, không hồi sinh session bằng một request đến muộn.

## 5. Absolute timeout: giới hạn thời gian cứng

**Absolute timeout** ấn định **mốc kết thúc tối đa** cho một phiên hoặc ngữ cảnh xác thực, **kể cả người dùng vẫn liên tục thao tác**. Khác với idle timeout, việc click hoặc gọi API không tự kéo dài mốc absolute.

Ví dụ minh họa:

~~~text
Session issuedAt   = 08:00
Idle limit          = 15 phút
Absolute limit      = 8 giờ
Absolute expiresAt  = 16:00

15:59: người dùng thao tác -> có thể gia hạn idle timer
16:00: absolute expiry -> session vẫn phải kết thúc
                          hoặc cần reauthenticate theo policy
~~~

### 5.1. Vì sao phải có absolute limit?

Nếu chỉ có idle timeout, một tab polling liên tục hoặc phiên bị kẻ tấn công chủ động sử dụng có thể không bao giờ idle. Absolute timeout tạo **giới hạn trên** cho khoảng thời gian một authentication context được duy trì mà không cần tái xác thực.

Tùy nền tảng, hệ thống có thể coi việc **reauthentication thành công** là điểm bắt đầu một authorization/session lifetime mới. Việc có tạo session ID mới hay làm mới mốc phụ thuộc kiến trúc, nhưng phải **quy định và kiểm toán rõ**, không âm thầm kéo dài vô hạn.

### 5.2. Absolute timeout không phải tuổi tối đa của account

Nhân viên vẫn có account ACTIVE sau khi một session hết hạn và có thể đăng nhập lại đúng quy trình. Account lifecycle, hợp đồng và policy phân quyền là một tầng riêng.

## 6. Sliding expiration: gia hạn có giới hạn

**Sliding expiration** là cơ chế dời mốc idle expiry khi có activity hợp lệ, ví dụ:

~~~text
effectiveIdleExpiry = lastEligibleActivity + idleLimit
effectiveExpiry = min(effectiveIdleExpiry, absoluteExpiresAt)
~~~

Công thức trên chỉ là **mô hình đơn giản**; môi trường thực tế có trạng thái thu hồi, authentication freshness, privilege TTL, phiên cha và policy bổ sung.

### 6.1. Ba rủi ro phổ biến

1. **Gia hạn vì request nền:** Polling/keep-alive giúp một session bỏ quên không bao giờ hết hạn.
2. **Gia hạn sau khi đã hết hạn:** Request đến muộn nhưng ghi đè `lastActivityAt` trước khi kiểm expiry.
3. **Làm mới absolute lifetime:** Mỗi lần refresh cookie lại đặt `issuedAt=now` mà không có reauthentication thực sự.

### 6.2. Cách kiểm soát

- Backend kiểm **idle và absolute expiry trước khi cập nhật activity**.
- Chỉ hoạt động được policy chấp nhận mới cập nhật last activity.
- Giữ **absoluteExpiresAt bất biến** trong lifetime của phiên tương ứng.
- Ràng buộc quyền/reauthentication nếu hoạt động nhạy cảm.
- Dùng concurrency controls để nhiều request song song không hồi sinh phiên.

## 7. Timeout, logout, revocation và account disable

Bốn khái niệm này không đồng nghĩa:

| Hoạt động | Kích hoạt bởi | Kỳ vọng | Vẫn cần kiểm |
|---|---|---|---|
| **Timeout** | Hết idle/absolute/auth freshness | Session không còn được dùng như trước | Các token/session khác |
| **Logout** | Người dùng hoặc ứng dụng chủ động | Phiên cụ thể kết thúc | IdP session và các ứng dụng khác |
| **Session revocation** | Quản trị/security/JML | Phiên bị mất hiệu lực trước hạn | Propagation, cache và đường target khác |
| **Account disable** | IAM/HR/VMS/security | Chặn authentication/authorization theo policy | Token đã cấp, local accounts, service credentials |
| **Permission revoke** | Mover/review/expiry | Action không còn được phép | Role khác, ACL, token, session |
| **Credential rotation** | Bảo mật/đổi key | Credential cũ không còn dùng được tại target khi revoke | Access token cũ và credential khác |

**Timeout là kiểm soát bổ sung, không phải chiến lược duy nhất để giải quyết Leaver hay tài khoản bị xâm phạm.** Một nhân viên nghỉ việc không nên được phép tiếp tục sử dụng quyền cho đến hết “8 giờ phiên tuyệt đối” nếu chính sách buộc thu hồi tại mốc Leaver.

## 8. Kiến trúc các tầng session và timeout

~~~mermaid
flowchart TD
    U["Human user<br/>Browser / Mobile"] --> IDP["IdP / SSO session<br/>Auth time + reauth policy"]
    IDP --> APP["Application session<br/>Idle + absolute timeout"]
    APP --> API["API / Resource Server<br/>Token + current authorization"]
    API --> RES["Resource / Tenant / Data"]
    AS["Authorization Server<br/>Access/refresh token lifecycle"] --> API
    IDP --> AS
    HR["HR / VMS<br/>Joiner–Mover–Leaver"] --> IAM["IAM / IGA<br/>Desired access + JML events"]
    IAM --> IDP
    IAM --> APP
    IAM --> P["PAM / PIM<br/>Privileged role + session TTL"]
    P --> API
    IAM --> RECON["Reconciliation<br/>Session + token + grant readback"]
    API --> RECON
    APP --> RECON
    IDP --> RECON
    P --> RECON
    RECON --> AUD["Audit + Security monitoring"]
~~~

Sơ đồ là **mô hình logic**, không yêu cầu mọi hệ thống phải dùng cùng sản phẩm hoặc cookie/token. Chức năng quan trọng là mỗi lớp phải biết **trách nhiệm thực thi timeout và thu hồi của mình**, cùng cơ chế chuyển tín hiệu giữa các lớp.

### 8.1. Vì sao IdP timeout không đủ?

IdP có thể kết thúc SSO session nhưng một ứng dụng đã tạo session nội bộ hoặc access token vẫn hoạt động. Nếu ứng dụng **không kiểm trạng thái hiện hành** hoặc không nhận logout/revocation event, việc IdP hết phiên không tự làm ứng dụng mất quyền.

### 8.2. Vì sao ứng dụng timeout không đủ?

Một browser app có thể chuyển về login nhưng **API chấp nhận token khác**, hoặc một tab/mobile app còn refresh token riêng. Cần xác định chính xác **đường truy cập nào phải bị chặn** sau timeout.

## 9. IdP/SSO session và Application session

**SSO (Single Sign-On)** giúp người dùng xác thực một lần với IdP rồi sử dụng nhiều ứng dụng. Nhưng IdP session và từng ứng dụng có **cookie/session và policy riêng**.

### 9.1. Kịch bản “timeout nhưng đăng nhập lại ngay”

1. Người dùng đăng nhập IdP lúc 08:00.
2. CRM tạo session lúc 08:02.
3. CRM hết idle timeout lúc 08:30.
4. Người dùng truy cập CRM và bị chuyển đến IdP.
5. IdP vẫn có SSO session, không yêu cầu nhập mật khẩu/MFA.
6. CRM tạo session mới sau khi nhận authentication response hợp lệ.

Đây có thể là **SSO hoạt động đúng chính sách**, nhưng nếu thao tác cần **authentication freshness** cao hơn, ứng dụng phải yêu cầu **reauthentication phù hợp**, không chỉ chuyển qua một redirect.

### 9.2. Cần xác định phạm vi logout

- **Local logout:** Chấm dứt session của một ứng dụng.
- **IdP logout:** Chấm dứt session tại IdP theo cơ chế sản phẩm.
- **Single Logout (SLO) / OIDC logout integration:** Có thể cố gắng thông báo hoặc kết thúc nhiều session liên quan, phụ thuộc chuẩn/cấu hình và khả năng từng RP.
- **Global security revoke:** Có thể cần hủy mọi session/device/token của subject theo chính sách, không chỉ local logout.

**Không hứa “đăng xuất khỏi tất cả ứng dụng” nếu chỉ xóa cookie của một RP.** Cần thử thực tế ở những ứng dụng trong phạm vi.

## 10. OIDC: `auth_time`, `max_age` và session freshness

Trong **OpenID Connect (OIDC)**, ứng dụng có thể cần biết người dùng đã xác thực **gần đây** hay chưa.

- **`auth_time`**: Thời điểm authentication của người dùng, khi được cung cấp theo flow/điều kiện thích hợp.
- **`max_age`** trong authentication request: Cho biết giới hạn tuổi xác thực tối đa ứng dụng yêu cầu trước khi cần xác thực lại; phải được IdP xử lý theo OIDC.
- **`prompt=login`**: Yêu cầu IdP xác thực lại người dùng theo semantics của OIDC.
- **`acr`/`amr`**: Có thể mô tả ngữ cảnh/phương pháp xác thực, tùy IdP và policy.
- **ID Token `exp`**: Thời hạn của **ID token**, không tự là session TTL của ứng dụng hoặc của IdP.

### 10.1. Một ID Token mới không tự chứng minh MFA mới

Ứng dụng không nên suy rằng “ID Token vừa được phát vài giây trước” đồng nghĩa người dùng vừa hoàn tất MFA. IdP có thể phát token mới dựa trên **SSO session sẵn có**. Để đánh giá freshness, cần dùng **các claim và policy có ngữ nghĩa phù hợp**, cùng cách IdP xử lý request.

### 10.2. Step-up cho hành động nhạy cảm

Ví dụ một người dùng có phiên đọc báo cáo bình thường nhưng muốn **thay chính sách IAM hoặc export dữ liệu nhạy cảm**. Có thể yêu cầu reauthentication/step-up rồi kiểm authorization tại API, thay vì bắt mọi người đăng nhập lại cho mỗi request.

**Step-up xác thực không tự cấp role admin.** Nó chỉ tăng độ tin cậy vào authentication context; quyền cần được RBAC/ABAC/PBAC kiểm riêng.

## 11. Cookie expiration khác session expiration

Với ứng dụng web, browser có thể lưu **session cookie** chứa session ID hoặc token. Cookie có các thuộc tính bảo mật và lifetime riêng.

| Thành phần | Vai trò | Cần lưu ý |
|---|---|---|
| **Cookie `Max-Age`/`Expires`** | Khi browser ngừng gửi cookie theo quy tắc cookie | Client có thể bị chỉnh sửa; không là điểm kiểm server |
| **Session ID** | Tham chiếu tới phiên server-side | Phải đủ ngẫu nhiên, không tiết lộ trạng thái |
| **Server session record** | Owner, trạng thái, issuedAt, lastActivity, expiry | Server phải kiểm mỗi request cần bảo vệ |
| **`Secure` cookie flag** | Chỉ gửi cookie qua kênh bảo mật theo semantics browser | Không thay TLS và session validation |
| **`HttpOnly`** | Hạn chế JavaScript đọc cookie | Không tự chống CSRF, XSS hoặc session theft mọi dạng |
| **`SameSite`** | Giảm rủi ro gửi cookie cross-site theo chính sách browser | Không thay CSRF controls đầy đủ |
| **Cookie path/domain** | Giới hạn phạm vi cookie được gửi | Tránh phạm vi rộng ngoài nhu cầu |
| **Server invalidation** | Đánh dấu phiên không còn hiệu lực | Cần xem replica/cache và token khác |

### 11.1. Browser “session cookie” không phải security lifetime

Cookie không có `Expires`/`Max-Age` thường được xem là session cookie của browser, nhưng browser có thể **khôi phục phiên trình duyệt**. Vì vậy không dựa vào “đóng tab/browser” làm ranh giới bảo mật duy nhất.

### 11.2. Xóa cookie khác vô hiệu session ID

Nếu server vẫn chấp nhận session ID đã bị đánh cắp, việc browser hợp lệ xóa cookie không đủ. Logout/timeout cần **đánh dấu session invalid bên server hoặc đảm bảo token không còn được chấp nhận theo cơ chế tương ứng**.

## 12. Access token expiry và Refresh token lifecycle

Một kiến trúc phổ biến sử dụng:

- **Access token:** Được gửi tới API và có thời hạn giới hạn.
- **Refresh token:** Nếu flow hỗ trợ và phát refresh token, client có thể dùng nó để xin access token mới theo policy.
- **Authorization Server session/grant:** Có thể quyết định refresh token còn được dùng hay không.
- **Resource Server:** Có trách nhiệm xác minh access token và authorization trên resource.

### 12.1. Access token ngắn hạn không đảm bảo “đã timeout người dùng”

Nếu access token hết hạn sau 10 phút nhưng refresh token vẫn có thể xin token mới mà không kiểm idle/absolute policy của ứng dụng, người dùng có thể tiếp tục truy cập rất lâu.

### 12.2. Refresh token rotation khác gia hạn session

Rotation giảm rủi ro tái sử dụng refresh token bằng cách thay token trong những trường hợp thích hợp. Nhưng **không phải mọi lần refresh đều nên được tính như hoạt động người dùng** và không nhất thiết reset mốc session absolute.

### 12.3. JWT và thu hồi ngay

JWT access token tự chứa thường được Resource Server kiểm dựa trên chữ ký, issuer, audience và expiry. Nếu API **không tra trạng thái cập nhật** hoặc không dùng cơ chế revocation riêng, token có thể còn được chấp nhận cho đến `exp` dù người dùng Mover/Leaver hoặc đã logout.

**Cần chọn token TTL, introspection/status checks, denylist/token version hoặc event-driven enforcement** theo rủi ro và khả năng nền tảng. Không giả định một cơ chế duy nhất áp dụng cho mọi hệ thống.

## 13. Server-side session: mô hình dữ liệu có thời hạn

Một session record có thể gồm:

~~~json
{
  "sessionId": "SES-example-8f2",
  "subjectId": "P-2048",
  "accountId": "crm-user-2048",
  "applicationId": "crm",
  "tenantId": "tenant-A",
  "issuedAt": "2026-12-01T08:00:00+07:00",
  "authenticatedAt": "2026-12-01T08:00:00+07:00",
  "lastEligibleActivityAt": "2026-12-01T08:40:00+07:00",
  "idleLimitSeconds": 900,
  "absoluteExpiresAt": "2026-12-01T16:00:00+07:00",
  "authenticationContextRef": "AUTHCTX-11",
  "credentialVersion": 4,
  "authorizationStateVersion": 19,
  "status": "ACTIVE",
  "revokedAt": null
}
~~~

Đây là **ví dụ học tập**, không phải schema chuẩn hay record thực. Giá trị `sessionId` là placeholder; session ID thực cần được tạo bằng nguồn ngẫu nhiên mật mã đủ mạnh và được bảo vệ như credential.

### 13.1. Phân biệt những timestamp

- `issuedAt`: Thời điểm phiên được tạo.
- `authenticatedAt`: Thời điểm authentication hoặc reauthentication có ý nghĩa.
- `lastEligibleActivityAt`: Lần cuối có hoạt động được phép gia hạn idle timer.
- `absoluteExpiresAt`: Mốc cứng không tự kéo dài.
- `revokedAt`: Biến cố thu hồi trước hạn.
- `verifiedAt`: Thời điểm hệ thống chứng minh quyền đã mất theo tiêu chí; không đồng nhất với `revokedAt`.

### 13.2. Tên trạng thái cần có ý nghĩa

~~~text
CREATED
  └─ ACTIVE
       ├─ IDLE_EXPIRED
       ├─ ABSOLUTE_EXPIRED
       ├─ REAUTH_REQUIRED
       ├─ REVOKED_BY_USER
       ├─ REVOKED_BY_SECURITY
       └─ REVOKED_BY_JML
            ↓
       TERMINATED / NOT_ACCEPTED
            ↓
       AUDITED / CLEANED_UP
~~~

Một số hệ thống không lưu state “expired” mà tính động theo timestamp, điều này vẫn có thể an toàn nếu **mọi đường kiểm quyền dùng chung logic đúng**.

## 14. Thuật toán timeout phía server (mã giả)

Ví dụ Python dưới đây chỉ minh họa thứ tự kiểm; **không phải thư viện session production**.

~~~python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass
class Session:
    subject_id: str
    issued_at: datetime
    last_activity_at: datetime
    absolute_expires_at: datetime
    revoked: bool
    state_version: int

def validate_session(session, now, subject_state, activity_is_eligible):
    # Timestamp phải được chuẩn hóa UTC/offset và lấy từ server.
    if session is None or session.revoked:
        return {"allow": False, "reason": "REVOKED_OR_MISSING"}

    # Trạng thái JML/incident hoặc policy deny có thể vô hiệu
    # session trước cả timeout thời gian.
    if not subject_state.currently_eligible:
        return {"allow": False, "reason": "SUBJECT_INELIGIBLE"}

    if now >= session.absolute_expires_at:
        return {"allow": False, "reason": "ABSOLUTE_EXPIRED"}

    idle_limit = timedelta(minutes=15)  # Chỉ minh họa.
    if now >= session.last_activity_at + idle_limit:
        return {"allow": False, "reason": "IDLE_EXPIRED"}

    # Re-authentication freshness và authorization tại resource
    # cần được xử lý riêng theo policy.

    if activity_is_eligible:
        # Production cần atomic compare-and-update và versioning.
        session.last_activity_at = now

    return {"allow": True, "reason": "SESSION_VALID"}
~~~

**Giới hạn rất quan trọng:** Ví dụ không xác thực cookie/token, không kiểm session fixation, device binding, concurrency, negative cache, thời gian token, multi-region consistency, policy combining hay atomic read-modify-write. **Không dùng trực tiếp để bảo vệ API production.**

### 14.1. Thứ tự quan trọng

1. Xác minh session ID/token **hợp lệ và đáng tin**.
2. Kiểm revoke/JML/security state nếu cần.
3. Kiểm absolute expiry.
4. Kiểm idle expiry dựa trên timestamp server đã xác minh.
5. Kiểm authentication freshness theo hành động.
6. Kiểm authorization hiện hành trên **action/resource/tenant**.
7. Chỉ khi phù hợp mới cập nhật last activity theo policy.

Nếu cập nhật activity **trước khi xét expired**, một request đến sau deadline có thể tự kéo dài session.

## 15. Dùng đồng hồ server và tính đúng tại ranh giới

Một policy timeout phải quy định rõ dùng **UTC/offset và mốc so sánh**.

~~~text
idleLimit = 900 giây
lastEligibleActivity = 10:00:00 UTC

10:14:59 UTC -> Chưa đủ 900 giây
10:15:00 UTC -> Đã đạt 900 giây, expire nếu policy dùng now >= deadline
10:15:01 UTC -> Expired
~~~

### 15.1. Không tin giờ của client

Client có thể lệch giờ hoặc tự đổi đồng hồ; countdown UI chỉ là **thông tin cho người dùng**. Server phải quyết định dựa trên timestamp đáng tin và chính sách hiện hành.

### 15.2. Multi-node và clock skew

Trong cụm nhiều node, một request có thể đến server A rồi server B. Cần:

- Cơ chế đồng bộ đồng hồ và giám sát sai lệch.
- Nguồn session state nhất quán đủ mức rủi ro.
- Atomic update `lastActivityAt` hoặc monotonic max update.
- Không để một replica đọc state cũ và **hồi sinh phiên revoked/expired**.
- Chú ý TTL cache/replication và tính nhất quán khu vực.
- Ghi timestamp, server/region, policy version vào audit.

Không tự thêm khoảng “grace” lớn cho phiên đã hết hạn chỉ để che lỗi đồng hồ; mọi tolerance phải nằm trong thiết kế chính sách và threat model.

## 16. Race condition và nhiều request đồng thời

Giả sử hai request cùng đến:

~~~text
lastActivityAt=10:00; idleLimit=15 phút.

Request A: đến 10:14:59; hợp lệ.
Request B: đến 10:15:01; thấy bản ghi cũ.

Nếu DB write từ A đến trễ:
  B có thể xem expired.
Nếu server B update trước khi check:
  session bị hồi sinh sai.
~~~

Cần quy tắc nhất quán:

- **Hợp thức hóa hoạt động** trước khi cập nhật.
- Atomic state transition hoặc compare-and-set theo version.
- Không cho request stale ghi đè `REVOKED` hoặc `EXPIRED`.
- Cập nhật `lastActivityAt = max(old, trustedActivityTime)` nếu chính sách phù hợp và record còn active.
- Khi kết thúc phiên, hủy/đánh dấu invalid sao cho mọi node sẽ từ chối theo consistency requirement.
- Xác định hành vi tại ranh giới deadline và test song song.

### 16.1. Hết hạn giữa request dài

Nếu request được xác thực trước deadline nhưng xử lý đến sau deadline, hệ thống phải định nghĩa **quyền có cần tái kiểm trước commit/hành động nhạy cảm hay không**. Với giao dịch rủi ro cao hoặc streaming, có thể cần kiểm lại ở **bước thực thi** chứ không chỉ lúc request bắt đầu.

## 17. Idle timeout của người dùng và background traffic

Ứng dụng hiện đại có request nền liên tục:

- Polling dashboard.
- Auto-refresh access token.
- WebSocket heartbeat.
- Autosave và background sync.
- Service worker hoặc mobile push.
- Analytics/telemetry.

Nếu mọi request cập nhật idle timestamp, một tab bỏ quên có thể tiếp tục giữ session.

### 17.1. Phân loại hoạt động

| Hoạt động | Có nên gia hạn idle timer người? | Lý do |
|---|---|---|
| Người dùng chủ động xem, tìm kiếm, submit | Thường có thể, theo policy | Thể hiện tương tác cần được bảo vệ |
| Mouse move mỗi giây | Không nên mặc định | Dễ giả lập, không bảo đảm hiện diện |
| Polling API định kỳ | Không mặc định | Hoạt động của app, không phải con người |
| Refresh token tự động | Không mặc định | Chỉ duy trì token, không xác thực lại người |
| WebSocket ping/pong | Không | Chỉ chứng minh kết nối |
| Auto-save nháp | Theo policy; không tự động | Có thể chạy không cần người |
| API call do script dùng cookie | Không mặc định | Không chứng minh người hiện diện |
| Reauthentication có kiểm soát | Có thể khởi tạo ngữ cảnh mới | Phải thực sự xác thực theo yêu cầu |

### 17.2. Người dùng có nhiều tab

Nếu các tab dùng chung session, một thao tác hợp lệ ở tab A có thể gia hạn session phục vụ tab B **theo thiết kế**. Cần truyền thông rõ điều này và ngăn tab B tiếp tục hành động nhạy cảm dựa trên dữ liệu/quyền cũ mà không kiểm backend.

## 18. Cảnh báo trước timeout và trải nghiệm người dùng

Timeout ảnh hưởng usability: mất dữ liệu form, người dùng phải đăng nhập lại khi đang làm việc, hoặc job dài bị ngắt.

Các biện pháp thực tế:

1. Hiển thị cảnh báo trước hạn với **thời gian lấy từ server**.
2. Nêu rõ điều kiện: “Không hoạt động” hay “Phiên sẽ hết hạn theo giới hạn tối đa”.
3. Cho người dùng lưu nháp hoặc hoàn thành bước hiện tại an toàn.
4. Không gia hạn chỉ vì modal đang hiển thị.
5. Nút “Tiếp tục” chỉ gia hạn nếu server xác nhận session còn hợp lệ và hành động được chấp nhận.
6. Sau khi expired, yêu cầu reauthentication trước khi gửi hành động nhạy cảm.
7. Đảm bảo trợ năng: keyboard/screen reader, thông báo dễ hiểu.
8. Không lộ dữ liệu nhạy cảm trên trang bị bỏ quên lâu sau timeout; cân nhắc che nội dung khi khóa.
9. Không xóa dữ liệu người dùng một cách bất ngờ nếu có cơ chế lưu nháp được bảo vệ.
10. Không biến UX tiện lợi thành bypass absolute timeout hoặc JML revoke.

### 18.1. UI countdown bị sai lệch

Countdown có thể hiển thị còn 2 phút khi server đã revoke phiên vì Leaver/security incident. Hệ thống phải **ưu tiên quyết định backend**; UI có thể cập nhật thông báo nhưng không được cho phép hành động dựa trên timer local.

## 19. Timeout theo mức rủi ro

Không nên lấy một con số cố định áp cho mọi ngữ cảnh. Xây chính sách theo:

- **Mức nhạy cảm tài nguyên:** Dashboard nội bộ, dữ liệu khách hàng, key management.
- **Đặc quyền:** User thường, admin, PIM eligible/active, break-glass.
- **Authentication assurance:** MFA/phishing-resistant mechanism, thời điểm xác thực mới nhất.
- **Thiết bị/kênh:** Thiết bị được quản lý, máy dùng chung, mạng không tin cậy.
- **Action:** Read, edit, export, delete, policy change.
- **Loại session:** Browser, mobile, API, SSH/RDP, service workload.
- **Business continuity:** Tác vụ thao tác dài, on-call, phục hồi sự cố.
- **Yêu cầu pháp lý/tổ chức:** Nếu có, policy phải kiểm chứng với văn bản hiện hành.
- **JML/security signals:** Engagement ended, account suspended, suspicious activity.
- **Khả năng revoke:** Target hỗ trợ kill session, token introspection, event propagation hay không.

### 19.1. Ma trận ví dụ, không phải tiêu chuẩn bắt buộc

| Ngữ cảnh | Idle giới hạn (chỉ minh họa) | Absolute giới hạn (chỉ minh họa) | Kiểm soát bổ sung |
|---|---:|---:|---|
| Web app nghiệp vụ thông thường | 30 phút | 8 giờ | Server-side validation |
| Console quản trị production | 10 phút | 1 giờ | Step-up, PAM/PIM, action audit |
| Máy kiosk dùng chung | 5 phút | 30 phút | Privacy screen, local logout |
| Giao diện xem dữ liệu nhạy cảm | 10–15 phút | 2 giờ | Scope/reauth cho export |
| Emergency admin session | Theo sự cố, ngắn và kiểm soát | Theo activation/policy | Monitoring, break-glass hậu kiểm |
| Machine-to-machine API | Không áp “user idle” y nguyên | Token TTL theo policy | Credential/identity lifecycle riêng |

**Các số trong bảng chỉ dùng để minh họa sự khác biệt về chính sách**; không suy ra mức chuẩn hay SLA. Tổ chức phải thiết kế thông số dựa trên rủi ro, khả năng nền tảng và yêu cầu hiện hành, rồi đo hiệu quả thực tế.

## 20. Privileged session timeout và PAM/PIM

**Đặc quyền** có thể cho phép thay quyền người khác, đọc secret, sửa production hoặc tắt giám sát. Vì vậy cần tách ba đồng hồ:

1. **PIM/JIT eligibility/activation TTL:** Khi nào subject được phép có đặc quyền.
2. **PAM/brokered session TTL:** Phiên SSH/RDP/DB được duy trì bao lâu.
3. **Target session/credential/token TTL:** Hệ thống đích còn cho dùng quyền đến khi nào.

### 20.1. Ví dụ grant hết hạn nhưng session còn quyền

~~~text
20:00  PIM kích hoạt production_admin tới 20:30
20:10  PAM mở database session
20:30  PIM báo role expired
20:45  Database session vẫn cho DDL vì target không recheck

Vấn đề:
  Activation TTL ≠ guaranteed effective access TTL.
~~~

Cần xác định policy yêu cầu **terminate session, giảm quyền, re-evaluate tại target, revoke credential** hoặc áp cơ chế phù hợp. Không tự kết luận an toàn từ dashboard PIM.

### 20.2. Idle timeout không thay SoD

Một người có role admin nhưng thiếu căn cứ theo Mover vẫn phải bị revoke. Timeout ngắn chỉ giới hạn **một phiên**; không giải quyết **khả năng kích hoạt lại quyền** nếu eligibility còn tồn tại.

### 20.3. Break-glass không nên hoạt động vô hạn

Session khẩn cấp có thể cần survivability khi IdP/PAM lỗi. Cần **đường phục hồi có điều kiện, monitoring/fallback, giới hạn thời gian, hậu kiểm và thu hồi**. Nếu timeout quá cứng sẽ cản trở recovery, nếu vô hạn sẽ tăng rủi ro. Chính sách phải quyết định rõ điều kiện khẩn cấp và phương án hỗ trợ.

## 21. Session timeout trong Joiner lifecycle

**Joiner** gồm onboarding danh tính và cấp quyền ban đầu. Với session management:

- Account được tạo trước mốc bắt đầu không tự được phép sử dụng quyền công việc trước `effectiveAt`.
- Người mới đăng ký authenticator/MFA; session sau đăng nhập cần gắn đúng canonical identity.
- Role baseline được cấp theo nhiệm vụ, nhưng session không được phép vượt scope.
- Các account admin riêng hoặc profile elevated cần timeout/reauth theo rủi ro.
- Không sao chép session/token/credential của người tiền nhiệm vào account mới.
- Khi kích hoạt account, có thể cần hủy session thử nghiệm hoặc token cấp khi onboarding trước đó.
- Audit ghi ai đăng nhập, app nào, authentication context, timeout/revoke outcomes.

**Một session hợp lệ của Joiner không biến role chưa approved thành quyền đã cấp.** API phải kiểm role và trạng thái theo chính sách hiện hành.

## 22. Session timeout trong Mover lifecycle

**Mover** là khi nhân viên đổi phòng ban, dự án, địa điểm, chức năng hoặc engagement, nhưng account và session có thể vẫn tồn tại.

Ví dụ:

~~~text
Trước Mover:
  Person P-2048 thuộc Sales Project-A
  Quyền: crm.export@A

Sau Mover:
  Person P-2048 thuộc Finance Project-B
  Quyền mong muốn: invoice.read@B

Vấn đề:
  Browser CRM session vẫn ACTIVE;
  token cũ có scope crm.export.
~~~

### 22.1. Không đợi idle timeout mới thu hồi quyền cũ

Cần:

1. HR/VMS phát event Mover có canonical identity và effective time.
2. IAM/IGA tính lại **desired entitlements** cho nhiệm vụ mới.
3. Thu hồi role/group/direct ACL và eligibility không còn căn cứ.
4. Đánh giá có cần **revoke hoặc refresh authorization state của session/token**.
5. API/PEP kiểm tenant/resource/action bằng dữ liệu đủ mới.
6. Target readback xác minh CRM export không còn được phép.
7. Giữ quyền engagement B còn hợp lệ nếu người đó có nhiều engagement.

**Một phiên có thể được phép tiếp tục sử dụng quyền không nhạy cảm mới**, nếu kiến trúc hỗ trợ **authorization re-evaluation**, nhưng không được tiếp tục thực thi quyền cũ trái policy chỉ vì session chưa hết hạn.

### 22.2. Session phải có thông tin quy chiếu quyền hiện hành

Nếu role được cache trong session nhiều ngày, một Mover có thể giữ claim cũ. Có thể dùng **authorization state version, short cache TTL, event invalidation hoặc server-side policy lookup** theo risk. Thời gian hội tụ cần được xác định và đo.

## 23. Session timeout trong Leaver lifecycle

**Leaver** là sự kiện người dùng hoặc engagement không còn đủ căn cứ truy cập. Đây là trường hợp **thu hồi theo sự kiện**, không phải chờ timeout thông thường.

~~~mermaid
flowchart TD
    HR["HR/VMS<br/>Leaver effective event"] --> IAM["IAM/IGA<br/>Canonical identity + targets"]
    IAM --> IDP["IdP/SSO<br/>Disable authentication + revoke sessions"]
    IAM --> APP["Application sessions<br/>Invalidate subject sessions"]
    IAM --> TOK["Authorization Server<br/>Refresh grants/token revocation"]
    IAM --> PAM["PIM/PAM<br/>Eligibility + active sessions"]
    IAM --> TAR["Target accounts / SCIM / ACL<br/>Remove rights"]
    IDP --> V["Readback + authorized negative tests"]
    APP --> V
    TOK --> V
    PAM --> V
    TAR --> V
    V --> Q{"Effective access<br/>meets required state?"}
    Q -->|Có| C["Close with audit evidence"]
    Q -->|Không/Unknown| E["Exception + owner + mitigation<br/>Escalate until verified"]
~~~

### 23.1. Vì sao chỉ disable IdP chưa đủ?

- CRM có **local session cookie** không cần hỏi IdP mỗi request.
- Resource Server chấp nhận **JWT access token chưa hết hạn**.
- Client có **refresh token/authorization grant** chưa revoke.
- Account local của database/VPN vẫn active.
- PAM session hoặc PIM eligible role còn.
- API key/PAT/SSH key không gắn vòng đời nhân viên.
- Cache role còn quyền cũ sau disable.
- Một contractor có nhiều engagement, cần thu hồi đúng phần kết thúc.

### 23.2. Quy tắc ưu tiên

Nếu policy yêu cầu Leaver không còn quyền từ 17:00, **absolute timeout 8 giờ của phiên khởi tạo lúc 15:00 không được dùng để cho truy cập đến 23:00**. Cần có sự kiện revoke/deny hiện hành hoặc kiến trúc enforcement đủ đáp ứng mốc cần chặn.

### 23.3. Kiểm chứng thu hồi

Không chỉ đọc `session.status=REVOKED` ở IAM; cần xem target/Resource Server có **từ chối các hành động** sau thời điểm phải thu hồi hay không. Sử dụng negative tests an toàn và dữ liệu readback, ghi rõ đường truy cập nào chưa kiểm.

## 24. Tài khoản dịch vụ và workload có “session timeout” không?

**Có thời hạn xác thực/ủy quyền**, nhưng **không nên áp cơ học idle timeout kiểu người ngồi trước máy** cho mọi non-human identity.

Một job chạy suốt 6 giờ có thể liên tục gọi API và phải đảm bảo:

- Workload identity được xác thực đúng.
- Token ngắn hạn được cấp/đổi theo policy.
- Resource Server kiểm `aud`, `exp`, scope và resource.
- Workload/owner còn ACTIVE và permission còn căn cứ.
- Credential rotation/revocation có cơ chế không làm job “mượn” token cũ mãi.
- Deployment retire không để lại principal, key hoặc role.
- Session/connection dài có kiểm tra khi quyền thay đổi hoặc khi bắt đầu action rủi ro.

### 24.1. OAuth Client Credentials không phải phiên người

Client Credentials thường biểu diễn **quyền của client/workload**, không phải phiên đăng nhập tương tác của nhân viên. Dùng `idleSinceLastMouseClick` để chặn service principal là sai mô hình. Cần **token lifetime, workload eligibility, owner/purpose và API permission** riêng.

### 24.2. Human owner Mover/Leaver

Nếu kỹ sư tạo service principal đã Leaver, workload có thể vẫn cần chạy. Phải:

- Chuyển technical owner.
- Thu hồi quyền human quản trị principal/vault/CI/CD.
- Đánh giá secret đã biết và rotation theo rủi ro.
- Giữ workload hợp lệ với quyền tối thiểu hoặc decommission nếu hết mục đích.
- Không nhầm disable account người với revoke mọi token workload.
- Audit và readback cả đường người lẫn đường máy.

## 25. WebSocket, SSE và kết nối dài

Session timeout thường được thiết kế cho request HTTP ngắn, nhưng **WebSocket, Server-Sent Events (SSE), streaming API, SSH, VPN và DB connection** có thể sống lâu.

### 25.1. Vấn đề WebSocket

WebSocket handshake được xác thực lúc mở kết nối. Nếu authorization thay đổi sau đó, server có thể vẫn tiếp tục gửi dữ liệu nếu **không revalidate**.

Cần xác định:

- Khi nào token/session được kiểm trong handshake?
- Có recheck expiry/authorization khi nhận message quan trọng?
- Có chấm dứt socket khi session bị revoke/Mover/Leaver?
- Heartbeat có được tính là human activity không? Thường **không nên**.
- Cơ chế reconnect có yêu cầu token/session mới hợp lệ không?
- Nếu resource/tenant subscription thay đổi, socket có gỡ subscription cũ không?
- Có log open/close, reason và permission denial không?

### 25.2. Streaming và giao dịch dài

Một long-running export có thể bắt đầu khi session hợp lệ nhưng kết thúc sau expiration. Tùy rủi ro, policy có thể cần **ủy quyền lại trước khi xuất dữ liệu, trước commit hoặc tại checkpoint**. Không dùng “đã kiểm lúc bắt đầu” để mặc nhiên hợp thức mọi thao tác sau Leaver.

### 25.3. Connection idle timeout khác user idle timeout

Một load balancer cắt kết nối TCP vì không có traffic chỉ là **network timeout**. Nó không nhất thiết invalidate session ID, token hoặc quyền người dùng ở ứng dụng. Các timer cần tên và trách nhiệm riêng.

## 26. Session fixation, hijacking và timeout

Timeout giảm thời gian lạm dụng nhưng không đủ ngăn:

- **Session fixation:** Kẻ tấn công khiến nạn nhân dùng session ID đã biết rồi đăng nhập.
- **Session hijacking:** Đánh cắp cookie/token hoặc lợi dụng thiết bị không khóa.
- **Credential stuffing/phishing:** Chiếm account rồi tự tạo session mới.
- **Replay:** Dùng lại bearer token còn hợp lệ.
- **CSRF/XSS:** Gửi hành động dưới session của người dùng nếu kiểm soát khác không đủ.
- **Concurrent account takeover:** Kẻ tấn công mở session khác sau khi nạn nhân logout.

### 26.1. Kiểm soát bổ sung

- Tạo session ID bằng nguồn ngẫu nhiên an toàn và **rotate/regenerate sau authentication hoặc thay đổi đặc quyền quan trọng** theo kiến trúc.
- Bảo vệ cookie bằng TLS, `Secure`, `HttpOnly`, `SameSite` phù hợp và CSRF controls.
- Không đưa session ID/token vào URL, analytics log hoặc repo.
- Giới hạn phạm vi token, audience và TTL.
- Cho phép revoke session theo device/all sessions khi phù hợp.
- Giám sát đăng nhập bất thường, token reuse hoặc phiên đồng thời không mong đợi.
- Reauthentication/step-up cho thao tác rủi ro cao.

**Không dùng timeout ngắn như cách duy nhất để bù cho cơ chế token/session dễ bị đánh cắp.**

## 27. Timeout policy: định nghĩa có cấu trúc

Một policy nên tách **human session, privileged session, workload token** và độ mới của authentication.

~~~yaml
# Ví dụ học tập; không phải cấu hình chuẩn cho sản phẩm cụ thể.
policyId: session-timeout-policy-v1
timezone: UTC
humanWeb:
  idleTimeoutSeconds: 900
  absoluteTimeoutSeconds: 28800
  activityDefinition: TRUSTED_INTERACTIVE_ACTIONS
  idleEnforcedOnServer: true
  absoluteExpiresAtImmutableWithoutReauth: true
  backgroundPollingRefreshesIdle: false
  revokeOnLeaverEvent: true
  reevaluateAuthorizationOnMover: true
privileged:
  idleTimeoutSeconds: 600
  absoluteTimeoutSeconds: 3600
  reauthenticationForSensitiveActions: true
  requireJitGrantValidity: true
  terminateTargetSessionWhenGrantEnds: POLICY_DEFINED
workloadApi:
  useHumanIdleTimeout: false
  requireTokenAudienceAndExpiry: true
  requireCurrentWorkloadAuthorization: true
  credentialLifetimePolicy: MANAGED_SEPARATELY
verification:
  readbackRequiredForJmlRevoke: true
  sessionAndTokenCoverageTracked: true
  missingEvidenceState: PENDING_VERIFICATION
~~~

Các số **900/28800/600/3600 giây chỉ minh họa** và không phải khuyến nghị chung. Policy thật phải giải quyết **thời gian hiệu lực, logic activity, exception, phân loại rủi ro và target capabilities**.

### 27.1. Không đặt `timeoutMinutes=15` cho mọi thứ

Một field duy nhất không chỉ rõ **idle, absolute, access token, refresh token, IdP session hay PAM connection**. Lỗi cấu hình có thể khiến frontend nghĩ phiên đã hết nhưng API vẫn cho quyền, hoặc khiến production job đột ngột bị cắt vì bị áp “idle của nhân viên”.

## 28. Tác động khi thay chính sách timeout

Thay timeout production có thể ảnh hưởng nhiều người dùng và ứng dụng:

1. **Inventory:** Những ứng dụng/session nào chịu policy?
2. **Compatibility:** SSO, mobile, WebSocket, API client có giả định lifetime cũ không?
3. **Session migration:** Session hiện hữu giữ expiry cũ hay bị rút ngắn ngay?
4. **Rollout:** Canary/feature flag và kế hoạch rollback nếu gây outage.
5. **Communication:** Người dùng có được cảnh báo về thao tác dài mất phiên?
6. **Security review:** Không nới TTL mà bỏ qua MFA/SoD/JML risk.
7. **Metrics:** Theo dõi timeout errors, login loops, user abandonment và residual sessions.
8. **Evidence:** Xác minh expiry ở server/API sau thay đổi.
9. **Cache consistency:** Các node có sử dụng cùng policy version?
10. **Exception handling:** Người có nhiệm vụ dài cần thiết kế task/credential riêng, không dùng bypass toàn cục.

### 28.1. Gia hạn cho một tác vụ không nên gia hạn mọi quyền

Một người cần thao tác nhập dữ liệu lâu có thể được hỗ trợ **draft saving** hoặc cơ chế xác thực lại trước submit; không cần làm cho **admin session** cũng tồn tại lâu hơn. Phân loại theo session/action thay vì tăng toàn bộ timeout.

## 29. Session timeout và SCIM

**SCIM** có thể được dùng để provision/deprovision user/group ở ứng dụng hỗ trợ. Khi Mover/Leaver, IAM có thể gửi thay đổi qua SCIM. Nhưng SCIM **không phải cơ chế session timeout hoặc token revocation chung**.

Ví dụ:

~~~text
HR: Employee Leaver
IAM: Disable user, remove group
SCIM: PATCH user.active=false hoặc nhóm bị gỡ theo target contract
Application:
  Account status cập nhật
  Nhưng local web session và token có thể cần xử lý riêng
Resource Server:
  Phải từ chối action theo policy hiện hành
~~~

**Một SCIM response thành công chỉ phản ánh thao tác theo contract của target.** Cần kiểm ứng dụng có terminate session, invalid refresh token hoặc thực thi account state mỗi request hay không.

### 29.1. Chậm đồng bộ không được hợp thức thời hạn quyền

Nếu policy yêu cầu revoke tức thời tại Leaver nhưng SCIM connector chạy theo batch định kỳ, phải thiết kế cơ chế bù trừ hoặc lộ trình hội tụ đủ đáp ứng yêu cầu. Không dùng idle timeout để che cửa sổ truy cập sai.

## 30. Timeout và RBAC/ABAC/PBAC

Timeout trả lời câu hỏi **“session còn được dùng không?”**, còn authorization trả lời **“hành động này trên tài nguyên này có được phép không?”**.

Ví dụ:

~~~text
Session:
  subject = P-2048
  status = ACTIVE
  absoluteExpiresAt > now

Authorization:
  action = invoice.export
  resource.tenant = tenant-B
  subject.allowedTenant = tenant-A

Result:
  DENY mặc dù session chưa timeout.
~~~

### 30.1. Policy theo trạng thái mới

Với ABAC/PBAC, một số thuộc tính có thể đổi ngay khi Mover/Leaver: department, project, accountStatus, riskState, groupMembership. Nếu API chỉ dùng bản chụp attributes lúc login, chính sách có thể sai sau event.

Cần xem:

- Attribute được tải lúc đăng nhập hay tra ở request?
- Cache TTL và cơ chế invalidation?
- Deny policy có được áp khi JML state mất hiệu lực?
- Direct grant khác có làm quyền tồn tại?
- Token claim cũ có thể bị dùng vượt mốc chính sách không?

**Không buộc mọi API lúc nào cũng gọi HR**, nhưng phải xác định **độ mới và cơ chế thu hồi** đủ mức rủi ro.

## 31. Timeout và access review/recertification

Trong access review, reviewer có thể quyết định **REVOKE** role của một subject. Nhưng nếu session/token vẫn đang cho action, remediation chưa hoàn tất.

| Bằng chứng | Cho thấy | Không tự chứng minh |
|---|---|---|
| Reviewer chọn REVOKE | Quyết định nghiệp vụ | Target đã gỡ quyền |
| IAM/IGA cập nhật desired state | Quyền mong muốn đã đổi | Ứng dụng đồng bộ |
| IdP session terminated | IdP không còn phiên được chỉ định | Local app session hết |
| App session record revoked | Record bị đánh dấu | Token khác/replica đã dừng |
| SCIM role removal | Target xử lý role update | Phiên/API còn quyền hay không |
| Access token `exp` passed | Token đó hết hạn theo RS validation | Refresh token/session khác hết |
| Target permission negative test | Action trong scope bị từ chối tại thời điểm kiểm | Mọi đường ngoài scope đã được kiểm |
| PIM grant expired | Role activation hết hạn | PAM/target session đã kết thúc |

### 31.1. Review không thay event-driven revocation

Reviewer có thể xác nhận quyền mỗi quý, nhưng Mover/Leaver cần trigger ngay theo sự kiện. Session timeout là **lớp giới hạn bổ sung**, không phải cơ chế duy nhất để chặn quyền sai đến kỳ review tiếp theo.

## 32. Monitoring và audit của Session timeout

Các sự kiện đáng ghi:

| Sự kiện | Thuộc tính cần thiết | Lưu ý |
|---|---|---|
| **SESSION_CREATED** | Subject, app, session ref, auth context, time | Không log session secret |
| **SESSION_ACTIVITY_ACCEPTED** | Session ref, trusted timestamp, type | Giảm noise, không log dữ liệu thừa |
| **IDLE_EXPIRED** | Last activity, idle limit, detection time | Phân biệt expiry time và log time |
| **ABSOLUTE_EXPIRED** | issuedAt, expiresAt, policy version | Không lẫn với logout |
| **REAUTH_REQUIRED/PASSED** | Reason, context, time | Không log OTP/password |
| **SESSION_REVOKED** | Actor/reason, subject, scope, time | JML/security/user logout |
| **TOKEN_REVOKED** | Token/grant reference, effect | Không ghi token raw |
| **PRIVILEGED_SESSION_TERMINATED** | PAM/session ID, target, outcome | Kiểm target session riêng |
| **AUTHORIZATION_DENIED** | Action, resource, decision reason | Giảm lộ dữ liệu và cardinality |
| **RECONCILIATION_RESULT** | Target, scope, verified/unknown | Không tự nói complete nếu thiếu bằng chứng |

### 32.1. Không ghi session ID/cookie/token nguyên văn

Session ID là **bearer credential** ở nhiều ứng dụng. Nếu log chứa session ID, người có quyền đọc log có thể chiếm phiên. Thay bằng **opaque reference/hash an toàn theo thiết kế** hoặc correlation ID, cùng kiểm soát quyền xem và retention.

### 32.2. Các chỉ số cần theo dõi

- **Idle/absolute timeout rate** theo ứng dụng và role.
- **Time to detected expiry** so với mốc lẽ ra hết hạn.
- **Sessions surviving JML event** và thời gian cho đến khi bị từ chối.
- **Stale role/authorization cache exposure**.
- **Access token accepted after required revoke**, nếu có bằng chứng.
- **Reauthentication/step-up success/failure** theo risk.
- **Logout/revocation propagation latency** qua IdP/app/RS.
- **Privileged target sessions active after JIT expiry**.
- **Background refresh keeping human sessions alive**.
- **WebSocket/long-lived connection cleanup**.
- **Mobile login loop và trải nghiệm mất dữ liệu do timeout**.
- **Unverified session paths** khi inventory không đủ.

**Không tối ưu bằng cách tăng timeout vô hạn để giảm lỗi đăng nhập.** Đánh giá đồng thời an toàn, usability và tác động vận hành.

## 33. Kiểm thử Session timeout

Một bộ test tối thiểu cần cả trường hợp thành công lẫn thất bại:

| Test | Kỳ vọng |
|---|---|
| Request trước idle deadline | Được xét theo policy/authorization |
| Request đúng idle deadline | Xử lý nhất quán theo quy tắc biên |
| Request sau idle deadline | Bị từ chối và không hồi sinh session |
| Activity hợp lệ trước idle deadline | Gia hạn idle, không đổi absolute |
| Polling/heartbeat liên tục, không có người | Không tự giữ session người mãi |
| Tương tác liên tục tới absolute deadline | Session hết hạn/reauth dù đang active |
| Frontend timer bị vô hiệu | Backend vẫn chặn session hết hạn |
| Cookie còn nhưng server session revoked | Backend từ chối |
| Server session còn nhưng cookie bị xóa | Client phải xác thực lại; session server cần cleanup |
| IdP session còn, app session timeout | Có thể SSO lại theo policy |
| App session còn, IdP session logout | Xác định integration và expected behavior thực tế |
| JWT hết hạn | Resource Server từ chối token đó |
| Refresh token bị revoke | Không thể mint token mới qua grant đã revoke |
| Mover gỡ role khi session đang active | Action cũ bị từ chối theo policy |
| Leaver trước absolute deadline | Thu hồi theo JML, không chờ timer |
| PAM JIT hết hạn trong DB session | Target không còn quyền trái policy |
| WebSocket nối khi token hết hạn | Revalidate/close theo thiết kế |
| Hai requests đồng thời quanh deadline | Không hồi sinh session hoặc stale update |
| Multi-region có cache chậm | Tuân consistency/revocation requirement |
| Workload token hết hạn | Job xử lý credential theo policy, không dùng token cũ |
| Policy thay đổi khi có session cũ | Có hành vi migration được định nghĩa |
| User có hai engagement | Chặn quyền hết căn cứ mà không xóa quyền khác hợp lệ |

### 33.1. Negative test an toàn

Để chứng minh revoke, không cần thực hiện hành động phá hoại ở production. Có thể dùng **authorization-check endpoint đáng tin, request chỉ đọc trong phạm vi được phép, kiểm trạng thái quyền tại target, môi trường thử nghiệm hoặc phép thử dự kiến bị từ chối** được security duyệt. Ghi lại **scope, thời điểm, token/session context, kết quả và giới hạn bằng chứng**.

## 34. Tình huống A: polling khiến session không bao giờ idle

**Bối cảnh:** Dashboard tài chính gửi `GET /notifications` mỗi 30 giây. Backend cập nhật `lastActivityAt` trên mọi request. Người dùng đóng laptop không tắt trình duyệt; sáng hôm sau phiên vẫn active.

**Nguyên nhân:** Background polling bị coi là activity của người.

**Hướng xử lý:**

1. Định nghĩa `eligible activity` rõ trong policy.
2. Tách request nền khỏi hành động tương tác hợp lệ.
3. Kiểm absolute timeout không bị refresh.
4. Thực thi timeout tại server.
5. Thử kịch bản tab bị bỏ quên trong khi polling tiếp tục.
6. Đối soát phiên thực sự bị từ chối sau mốc.
7. Kiểm tác động tới các tab/app dùng chung session.

**Bài học:** **Traffic còn chạy không chứng minh người dùng còn hoạt động**.

## 35. Tình huống B: CRM timeout nhưng SSO tự đăng nhập lại

**Bối cảnh:** CRM idle timeout 20 phút. Sau 20 phút, CRM redirect tới IdP, IdP vẫn có SSO session và trả kết quả xác thực hợp lệ, nên CRM lập tức vào lại không cần MFA.

**Nhận định:** CRM đã timeout đúng, IdP session vẫn còn; đây có thể là hành vi mong muốn. Nhưng nếu thao tác nhạy cảm đòi xác thực mới, chỉ redirect không đủ.

**Hướng xử lý:**

- Xác định requirement **session termination** hay **reauthentication freshness**.
- Cấu hình OIDC `max_age`/`prompt` và kiểm `auth_time` theo ứng dụng.
- Kiểm IdP có hỗ trợ reauthentication đúng mức bảo đảm.
- Giữ authorization riêng tại API.
- Test login lại sau idle và khi bắt đầu hành động admin.

**Bài học:** **SSO session và app session là hai phạm vi khác nhau**.

## 36. Tình huống C: Leaver còn access token JWT

**Bối cảnh:** Nhân viên nghỉ lúc 17:00. IdP disabled account ngay, nhưng Reporting API dùng JWT tự chứa phát lúc 16:50 với `exp` là 17:50. API không kiểm account-state và tiếp tục cho `report.export`.

**Rủi ro:** Quyền trái chính sách có thể tồn tại thêm 50 phút dù quy trình nhân sự đã kết thúc.

**Hướng xử lý:**

1. Xác định Leaver effectiveAt và yêu cầu thời điểm chặn truy cập.
2. Đánh giá token validation/denylist/introspection/status checks của API.
3. Thu hồi refresh grants và sessions liên quan.
4. Gỡ role/direct ACL tại target.
5. Giới hạn token lifetime và áp biện pháp bù trừ nếu cần.
6. Kiểm API từ chối export sau mốc bằng test an toàn.
7. Lưu readback và độ trễ thực tế, không chỉ event disable IdP.

**Bài học:** **Account disable không đồng nghĩa token đã phát bị vô hiệu ngay**.

## 37. Tình huống D: PIM role hết hạn, DB session vẫn admin

**Bối cảnh:** Kỹ sư được JIT DBA 30 phút. PIM ghi role hết hạn nhưng kết nối DB mở từ đầu phiên vẫn thực thi thao tác đặc quyền.

**Vấn đề:** Target kiểm đặc quyền tại kết nối hoặc cache session; activation TTL không đồng bộ với target-session control.

**Hướng xử lý:**

- Xác định yêu cầu policy về hiệu lực sau JIT expiry.
- Dùng PAM/DB session termination hoặc re-evaluation phù hợp.
- Kiểm quyền dựa trên action, không chỉ role activation status.
- Cân nhắc thiết kế grant hẹp và thời lượng thực tế.
- Theo dõi các phiên chưa chấm dứt, có owner và escalation.
- Readback quyền không còn tại DB target.

**Bài học:** **Session timeout của PAM/PIM phải gắn với phiên và quyền thực tế tại target**.

## 38. Tình huống E: WebSocket tiếp tục gửi dữ liệu sau Mover

**Bối cảnh:** Người dùng đang mở trang live customer feed. Sau khi chuyển từ dự án A sang B, IAM gỡ group A nhưng WebSocket được mở trước đó vẫn gửi sự kiện khách hàng A.

**Vấn đề:** Authentication/authorization chỉ kiểm lúc handshake, thiếu recheck theo resource hoặc revoke event.

**Hướng xử lý:**

1. Liên kết WebSocket subscription với subject, tenant và resource scope.
2. Khi Mover xảy ra, invalidation hoặc re-evaluate permission.
3. Close connection hoặc unsubscribe dữ liệu A theo policy.
4. Kiểm reconnect không dùng token/role cũ.
5. Audit thời điểm cập nhật policy và thời điểm ngừng gửi dữ liệu.
6. Test giữ B hợp lệ nếu có engagement khác.

**Bài học:** **Kết nối còn sống không được tự duy trì authorization đã bị thay đổi**.

## 39. Tình huống F: một service principal bị áp timeout của người

**Bối cảnh:** Workload xử lý hóa đơn chạy không tương tác. Nhóm kỹ thuật dùng shared middleware áp idle timeout “15 phút không có click” cho cả OAuth Client Credentials. Job ban đêm thỉnh thoảng dừng vì phải mở browser SSO.

**Nguyên nhân:** Nhầm **machine-to-machine token lifetime** với **human interactive session**.

**Hướng xử lý:**

- Phân loại subject `WORKLOAD` và client authentication phù hợp.
- Cấp access token theo policy, refresh/reissue theo flow được hỗ trợ.
- Dùng managed identity/workload federation khi phù hợp.
- Giới hạn audience, scope và môi trường; không cần giả lập mouse click.
- Giữ owner, audit, rotation và decommission lifecycle.
- Kiểm service liên tục hoạt động **đúng quyền**, nhưng token cũ bị từ chối khi hết hạn.

**Bài học:** **Không dùng trải nghiệm đăng nhập người làm mô hình chung cho tài khoản dịch vụ**.

## 40. Tình huống G: mobile refresh token duy trì “phiên” vô hạn

**Bối cảnh:** Mobile app đặt access token TTL ngắn nhưng refresh token không có kiểm idle/absolute/revocation. Người dùng đăng xuất trên giao diện, refresh token vẫn được lưu và có thể mint token mới.

**Hướng xử lý:**

1. Xác định phạm vi logout và trạng thái refresh grant.
2. Revoke refresh token/grant hoặc đánh dấu session không hợp lệ theo khả năng sản phẩm.
3. Bảo vệ token trong secure storage.
4. Xác định absolute/idle policy cho ứng dụng di động và tương tác có ý nghĩa.
5. Xem refresh token rotation, reuse detection khi hỗ trợ.
6. Test không thể lấy access token mới sau logout/revoke.
7. Xem access token đã phát có còn được chấp nhận bao lâu.

**Bài học:** **Token expiry ngắn không bù được cơ chế gia hạn không giới hạn**.

## 41. Tình huống H: browser timer hết nhưng API vẫn cho truy cập

**Bối cảnh:** JavaScript ẩn giao diện sau 10 phút; session cookie vẫn được gửi và API tiếp tục xử lý request ghi dữ liệu vì backend không kiểm `lastActivityAt`.

**Vấn đề:** Timeout chỉ nằm ở frontend, không có security enforcement.

**Hướng xử lý:**

- Đưa session validation vào backend/PEP.
- Kiểm idle và absolute expiry trước xử lý action.
- Invalidate session khi expired.
- Thử API trực tiếp bằng cùng cookie sau timeout.
- Xem cookie flags, CSRF và session fixation controls.
- Không báo PASS chỉ vì màn hình login hiển thị.

**Bài học:** **Frontend countdown là UX, không phải ranh giới authorization**.

## 42. Tình huống I: timeout làm mất dữ liệu form dài

**Bối cảnh:** Nhân viên đang soạn báo cáo dài. Absolute timeout kết thúc đúng chính sách khi họ nhấn Submit, làm mất dữ liệu; đội vận hành định tắt timeout toàn tổ chức.

**Giải pháp thích hợp:**

- Xác định phiên đã hết hạn thật và yêu cầu xác thực lại.
- Dùng autosave nháp **không gia hạn sai phiên**.
- Lưu dữ liệu có kiểm soát quyền/retention, không lưu secret tùy tiện.
- Cảnh báo trước absolute deadline.
- Sau reauthentication, kiểm quyền lại trước khi cho submit.
- Không kéo dài admin/production session chỉ vì một form.

**Bài học:** **Cải thiện trải nghiệm không cần vô hiệu hóa kiểm soát thời gian cho mọi quyền**.

## 43. Câu hỏi tự kiểm tra

**Câu 1.** Idle timeout khác absolute timeout như thế nào?

**Gợi ý:** Idle tính từ hoạt động đủ điều kiện cuối cùng; absolute là giới hạn cứng cho lifetime phiên dù vẫn hoạt động.

**Câu 2.** Một API polling 30 giây có nên tự gia hạn phiên người dùng?

**Gợi ý:** Không mặc định; polling không chứng minh user đang tương tác.

**Câu 3.** IdP SSO session còn hợp lệ nhưng app session đã timeout. Điều gì có thể xảy ra?

**Gợi ý:** App có thể đăng nhập SSO lại; nếu cần reauthentication mới, phải yêu cầu/kiểm freshness theo policy.

**Câu 4.** `exp` của ID Token có phải absolute timeout của ứng dụng không?

**Gợi ý:** Không. ID Token expiration và session lifetime là khái niệm khác nhau.

**Câu 5.** Vì sao `HttpOnly`/`Secure` không tự tạo session timeout?

**Gợi ý:** Cookie flags bảo vệ cách gửi/truy cập cookie, không thay validation time/state tại backend.

**Câu 6.** Leaver lúc 17:00 nhưng JWT còn hạn tới 17:50. Có thể chờ `exp` nếu policy yêu cầu chặn lúc 17:00 không?

**Gợi ý:** Không. Cần enforcement/revocation bổ sung phù hợp hệ thống.

**Câu 7.** PIM JIT role hết hạn, target DB session vẫn admin. Thu hồi đã hoàn tất chưa?

**Gợi ý:** Chưa nếu quyền thực tế còn được thực thi trái policy.

**Câu 8.** Có nên dùng idle timeout của browser cho OAuth Client Credentials workload?

**Gợi ý:** Không theo mô hình người; dùng token/credential/identity lifecycle và authorization của workload.

**Câu 9.** Vì sao phải kiểm server trước khi cập nhật `lastActivityAt`?

**Gợi ý:** Tránh request đến sau expiry tự hồi sinh session.

**Câu 10.** Một WebSocket đang mở khi quyền resource bị gỡ. Cần xem gì?

**Gợi ý:** Revalidation, subscription scope, close event, token expiry, Mover/Leaver triggers.

**Câu 11.** Logout ở một ứng dụng có mặc nhiên logout mọi app khác dùng SSO không?

**Gợi ý:** Không; phụ thuộc SLO/logout integration, cần xác minh từng phạm vi.

**Câu 12.** Một nhân viên còn làm việc nhưng đổi dự án; session có thể tiếp tục không?

**Gợi ý:** Có thể theo policy, nhưng action trên dự án cũ phải bị từ chối khi quyền mất căn cứ.

**Câu 13.** Session record ở IAM đã REVOKED, API vẫn cho phép request. Bước tiếp theo?

**Gợi ý:** Kiểm target/session/token/cache và thực thi readback/negative test, không đóng sớm.

**Câu 14.** Vì sao không thể coi “đã đóng trình duyệt” là đảm bảo logout bảo mật?

**Gợi ý:** Browser restore và server session/token có thể còn; cần server-side lifecycle.

## 44. Checklist thiết kế Session timeout

- [ ] **Phạm vi:** Phân biệt IdP, app, API, cookie, access token, refresh token, PAM, workload và kết nối dài?
- [ ] **Idle:** Có định nghĩa trusted eligible activity, không để polling/heartbeat gia hạn sai?
- [ ] **Absolute:** Có mốc cứng và không tự reset khi refresh cookie/token?
- [ ] **Reauthentication:** Có xác định khi nào cần freshness/step-up cho action nhạy cảm?
- [ ] **Server enforcement:** Mọi action bảo vệ đều kiểm session/token và state ở backend?
- [ ] **Cookie:** Có Secure/HttpOnly/SameSite, scope và CSRF controls phù hợp?
- [ ] **Session ID:** Đủ an toàn, rotate khi thay authentication/privilege theo policy?
- [ ] **Token:** Issuer, audience, expiry, scope và client identity được kiểm?
- [ ] **Refresh grants:** Có expiration/revocation/rotation phù hợp và test logout?
- [ ] **SSO:** Có hiểu local vs IdP logout/SLO và authentication freshness?
- [ ] **Clock:** Dùng server time, UTC/offset, kiểm skew và boundary?
- [ ] **Concurrency:** Không có request stale hồi sinh session; thao tác revoke atomic?
- [ ] **Multi-node:** Replication/cache consistency đủ với yêu cầu thu hồi?
- [ ] **User experience:** Warning, secure draft saving, reauth trước submit khi expired?
- [ ] **Risk policy:** Timer theo tài nguyên, action, assurance, device và privileged context?
- [ ] **PAM/PIM:** JIT TTL, broker session và target permission có xử lý tách biệt?
- [ ] **WebSocket/streaming:** Có recheck hoặc close khi token/session/quyền đổi?
- [ ] **Joiner:** Account và session có đúng effectiveAt, role và identity mapping?
- [ ] **Mover:** Có gỡ quyền cũ và invalidate/re-evaluate session/token theo policy?
- [ ] **Leaver:** Không chờ idle/absolute TTL để thu hồi quyền bắt buộc?
- [ ] **Service account:** Không áp human idle vào M2M; credential lifecycle và owner rõ?
- [ ] **SCIM:** Không coi user.active=false là bằng chứng mọi session/token đã mất?
- [ ] **RBAC/ABAC:** API kiểm action/resource/tenant hiện hành, không chỉ role từ login?
- [ ] **Revocation:** User/logout/security/JML events có tuyến tới mọi target cần thiết?
- [ ] **Readback:** Có target permission checks/negative tests an toàn sau revoke?
- [ ] **Coverage:** Không báo 100% nếu còn app local, JWT, PAT, DB session chưa kiểm?
- [ ] **Audit:** Ghi event timeout, revoke, failed authorization và policy version mà không lộ token?
- [ ] **Monitoring:** Có đo residual access latency, stale cache, privileged sessions sau expiry?
- [ ] **Testing:** Boundary, background traffic, multi-tab, concurrency, multi-region, mobile và JML?
- [ ] **Exceptions:** Phần chưa thu hồi có owner, mức rủi ro, biện pháp bù trừ và hạn xử lý?
- [ ] **Change control:** Timeout config thay đổi có rollout/rollback và kiểm tác động?
- [ ] **Kết luận:** Phiên hết hạn đúng ngữ cảnh và **quyền hiệu dụng** thực sự không còn khi policy yêu cầu?

## 45. Kết luận

**Session timeout là kiểm soát giới hạn thời gian sử dụng phiên, không chỉ là bộ đếm đăng xuất trên trình duyệt.** Để đúng về bảo mật, cần phân biệt **idle timeout, absolute timeout, authentication freshness, cookie lifetime, access/refresh token lifetime và session revocation**. **IdP/SSO, ứng dụng, API, PAM/PIM và workload** có thể duy trì các ngữ cảnh khác nhau; mỗi lớp phải thực thi đúng chính sách của mình.

Thiết kế tốt cần **server-side enforcement, trusted activity, absolute bound, token audience/expiry checks, authorization theo resource, chống race condition, giám sát và kiểm chứng**. Với quyền nhạy cảm phải kết hợp **MFA/reauthentication, JIT, PAM session management và xử lý credential**, thay vì tăng timeout tùy ý.

Trong vòng đời **Joiner–Mover–Leaver**, timeout **không thay thế event-driven revocation**: người mới chỉ dùng quyền đúng mốc, người chuyển vai trò mất quyền cũ, người rời tổ chức phải bị chặn đúng thời điểm chính sách quy định. **SCIM, RBAC/ABAC, IdP/SSO và quản trị tài khoản dịch vụ** phải phối hợp để giảm **quyền truy cập tồn dư**, kể cả token, phiên cũ và direct grants. **Một phiên chỉ được coi là kết thúc an toàn khi các đường truy cập trong phạm vi bắt buộc không còn được chấp nhận, và kết quả đó có bằng chứng kiểm chứng.**
