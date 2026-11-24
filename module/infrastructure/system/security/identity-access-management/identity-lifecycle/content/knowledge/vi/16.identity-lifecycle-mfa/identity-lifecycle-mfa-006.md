# Push authentication trong MFA và vòng đời danh tính IAM

> **Chương: MFA.** **Push authentication** là phương thức xác thực ngoài băng (out-of-band) trong đó hệ thống gửi một yêu cầu phê duyệt tới ứng dụng xác thực đã được đăng ký trên thiết bị của người dùng. Người dùng xem ngữ cảnh đăng nhập và chủ động xác nhận hoặc từ chối. Trong Identity and Access Management (IAM), push authentication chỉ an toàn khi thiết bị được liên kết đúng danh tính, yêu cầu xác thực gắn với đúng phiên, có biện pháp chống lạm dụng và được quản lý xuyên suốt **Joiner–Mover–Leaver**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả luồng **push MFA** từ ứng dụng đăng nhập qua IdP đến ứng dụng xác thực trên thiết bị và trở lại phiên đăng nhập.
2. Phân biệt **thông báo push**, **yêu cầu xác thực**, **bằng chứng kiểm soát authenticator** và **quyết định cấp quyền truy cập**.
3. Giải thích các nguy cơ **MFA fatigue/push bombing**, phishing, đánh cắp phiên, đăng ký thiết bị trái phép, giả mạo ngữ cảnh và chấp thuận nhầm.
4. Áp dụng các kiểm soát như number matching, ngữ cảnh đăng nhập, challenge ngắn hạn, chống replay, giới hạn yêu cầu và ràng buộc phiên.
5. Quản trị vòng đời thiết bị push MFA khi nhân viên gia nhập, thay đổi vai trò, mất điện thoại hoặc nghỉ việc; kết nối IdP, SSO, SCIM và chính sách RBAC/ABAC.
6. Xây dựng checklist triển khai, kịch bản kiểm thử, bằng chứng audit và phương án recovery an toàn.

## 1. Push authentication là gì?

Khi một người dùng nhập mật khẩu để vào ứng dụng doanh nghiệp, IdP có thể gửi **push challenge** tới điện thoại đã đăng ký. Ứng dụng xác thực hiển thị thông tin yêu cầu; người dùng xác nhận nếu chính mình đang đăng nhập. Phương thức này thường được dùng như **yếu tố thứ hai** bên cạnh mật khẩu, hoặc là một phần của cơ chế xác thực mạnh hơn tùy kiến trúc và cách bảo vệ authenticator.

Điểm cần phân biệt:

- **Push notification** là tín hiệu thông báo trên thiết bị: “Có yêu cầu đăng nhập”. Nó có thể được vận chuyển qua hệ thống thông báo của hệ điều hành, nhưng **bản thân thông báo không phải bằng chứng xác thực**.
- **Push challenge** là yêu cầu do IdP tạo, có định danh duy nhất, thời hạn và liên kết với một giao dịch đăng nhập.
- **Authenticator app** là ứng dụng đã được đăng ký với danh tính cụ thể, có khả năng chứng minh quyền kiểm soát thiết bị hoặc credential theo thiết kế sản phẩm.
- **Approval/denial** là quyết định của người dùng đối với giao dịch xác thực cụ thể. IdP phải kiểm chứng tính hợp lệ của phản hồi trước khi cấp phiên.
- **Authentication result** cho biết quy trình xác thực có được hoàn tất hay không; nó **không tự quyết định** người dùng được phép thực hiện nghiệp vụ nào sau đăng nhập.

### So sánh với các phương thức phổ biến

| Phương thức | Trải nghiệm | Rủi ro/đặc điểm quan trọng |
| --- | --- | --- |
| Mật khẩu đơn lẻ | Nhập bí mật đã biết. | Bị đoán, lộ, tái sử dụng hoặc phishing; không đủ cho nhiều tài nguyên nhạy cảm. |
| TOTP trong authenticator | Đọc mã thay đổi theo thời gian rồi nhập. | Có thể bị phishing và chuyển tiếp mã; cần bảo vệ seed và chống thử đoán. |
| SMS OTP | Nhận mã qua số điện thoại. | Phụ thuộc kênh viễn thông; có rủi ro chuyển số, chặn SMS, phishing. |
| **Push approve/deny** | Nhận thông báo rồi bấm xác nhận. | Tiện lợi nhưng dễ bị nhấn nhầm hoặc **push fatigue** nếu không có kiểm soát. |
| **Push + number matching** | So khớp mã hiển thị trong phiên đăng nhập với ứng dụng xác thực. | Giảm phê duyệt vô ý; **không mặc nhiên chống phishing** hoặc tấn công chuyển tiếp thời gian thực. |
| **Passkey/WebAuthn/FIDO2** | Xác thực bằng credential khóa công khai gắn với relying party; có thể yêu cầu xác minh người dùng cục bộ. | Khi triển khai và kiểm tra đúng RP ID/origin, cung cấp cơ chế chống phishing mạnh hơn push chấp thuận thông thường. |

**Đừng đồng nhất mọi sản phẩm có từ “push” với cùng mức bảo đảm.** Một sản phẩm có thể chỉ gửi nút Approve/Deny; sản phẩm khác có chữ ký challenge bằng khóa riêng trên thiết bị, kiểm tra tính toàn vẹn ứng dụng, number matching và xác minh người dùng cục bộ. Chính sách phải đánh giá **cơ chế thực tế**, không chỉ tên thương mại.

## 2. Push MFA gồm những thành phần nào?

### Kiến trúc khái niệm

~~~mermaid
flowchart LR
    U["Người dùng"] --> APP["Ứng dụng / trình duyệt"]
    APP --> IDP["Identity Provider (IdP)"]
    IDP --> POLICY["Chính sách authentication<br/>MFA, trạng thái User, rủi ro"]
    POLICY --> CH["Push challenge<br/>ID, phiên, hạn hiệu lực"]
    CH --> PUSH["Dịch vụ chuyển thông báo<br/>của nền tảng di động"]
    PUSH --> AUTH["Authenticator app<br/>trên thiết bị đã đăng ký"]
    U --> AUTH
    AUTH --> IDP
    IDP --> APP
    HR["Nguồn HR/JML"] --> IAM["IAM/IGA<br/>lifecycle & enrollment"]
    IAM --> IDP
    IAM --> AUD["Audit / monitoring"]
    IDP --> AUD
~~~

**IdP** tạo challenge và là nơi kiểm chứng phản hồi. **Dịch vụ push của hệ điều hành** thường chỉ giúp báo cho ứng dụng biết có một yêu cầu chờ; **không nên được coi là bên phê duyệt truy cập**. Thiết kế an toàn không phụ thuộc vào việc nội dung thông báo hiển thị được bí mật hoặc không thể bị giả mạo.

### Dữ liệu của một yêu cầu

Một push challenge thường cần các nhóm trường sau:

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| Định danh giao dịch | challengeId, authTransactionId | Nối phản hồi với **một** yêu cầu xác thực cụ thể. |
| Chủ thể | identityId, IdP User ID | Đảm bảo challenge thuộc đúng danh tính. |
| Thiết bị đã đăng ký | authenticatorId, deviceBindingId | Chỉ chấp nhận phản hồi từ authenticator còn hợp lệ. |
| Bối cảnh đăng nhập | clientId, ứng dụng, thời điểm, thông tin phiên | Giúp người dùng và IdP kiểm tra đúng giao dịch. |
| Mức yêu cầu | MFA, step-up, trạng thái risk | Quyết định có cần yếu tố bổ sung, sinh trắc học cục bộ hoặc từ chối. |
| Thời hạn | createdAt, expiresAt | Ngăn dùng lại yêu cầu quá hạn. |
| Kết quả | pending, approved, denied, expired, cancelled | Tránh race condition và cấp phiên hai lần. |
| Liên kết audit | eventId, correlationId | Truy vết đầu-cuối mà không ghi secret. |

Đây là **mô hình khái niệm**. Mỗi nhà cung cấp IdP/authenticator có thể dùng các tên trường, giao thức và kiểu liên kết khác nhau.

## 3. Luồng xác thực push từ đầu đến cuối

Ví dụ người dùng **Lan** đăng nhập CRM qua SSO:

1. Lan mở CRM; ứng dụng chuyển hướng tới IdP hoặc bắt đầu luồng đăng nhập theo giao thức phù hợp.
2. IdP xác định danh tính, kiểm tra trạng thái User, phiên hiện tại và chính sách yêu cầu MFA.
3. Sau yếu tố đầu tiên hoặc kiểm tra điều kiện theo thiết kế, IdP tạo một **push challenge** dành cho giao dịch đăng nhập hiện tại.
4. IdP gửi tín hiệu tới ứng dụng xác thực của Lan trên thiết bị đã đăng ký.
5. Ứng dụng xác thực lấy hoặc hiển thị chi tiết yêu cầu qua kênh được bảo vệ; Lan kiểm tra có phải mình đang đăng nhập, đúng dịch vụ và đúng thông tin đối chiếu hay không.
6. Lan chấp thuận hoặc từ chối; ứng dụng gửi phản hồi bằng cơ chế được IdP hỗ trợ, có ràng buộc với thiết bị và challenge.
7. IdP xác minh phản hồi, thời hạn, trạng thái challenge, thiết bị, danh tính, trạng thái vòng đời và chính sách.
8. Nếu tất cả điều kiện đạt, IdP hoàn tất giao dịch xác thực và tiếp tục luồng SSO; ứng dụng vẫn phải kiểm tra **authorization** theo RBAC/ABAC.

~~~mermaid
sequenceDiagram
    actor User as Lan
    participant Web as CRM / Browser
    participant IdP as IdP
    participant Push as Push transport
    participant Auth as Authenticator app
    User->>Web: Mở CRM và bắt đầu đăng nhập
    Web->>IdP: Authorization/authentication request
    IdP->>IdP: Kiểm tra User, lifecycle, MFA policy
    IdP->>IdP: Tạo challenge gắn với phiên
    IdP->>Push: Gửi tín hiệu có yêu cầu chờ
    Push->>Auth: Thông báo trên thiết bị
    Auth->>IdP: Nhận chi tiết challenge qua kênh an toàn
    Auth->>User: Hiện ngữ cảnh / number matching
    User->>Auth: Xác nhận hoặc từ chối
    Auth->>IdP: Phản hồi có ràng buộc challenge
    IdP->>IdP: Validate thiết bị, trạng thái, hạn, chính sách
    IdP-->>Web: Hoàn tất hoặc từ chối xác thực
    Web-->>User: Truy cập theo quyền hoặc báo lỗi
~~~

*Đây là sơ đồ logic, không phải đặc tả gói tin của một sản phẩm. Với một số giải pháp, ứng dụng xác thực dùng mật mã khóa công khai hoặc dịch vụ riêng; với giải pháp khác, cách chứng minh kiểm soát thiết bị khác nhau. Cần đánh giá hợp đồng giao thức và kiểm soát thực tế.*

### Phản hồi nào được xem là hợp lệ?

Để chống phản hồi giả hoặc phát lại, hệ thống thường cần đảm bảo:

- Challenge được **IdP tạo cho đúng User và phiên đăng nhập**, không phải yêu cầu trôi nổi.
- Phản hồi đến từ **authenticator đã liên kết hợp lệ**, theo cơ chế kiểm chứng của giải pháp.
- Chỉ một phản hồi cuối cùng được áp dụng; một challenge đã chấp thuận/từ chối/hết hạn không thể dùng tiếp.
- Challenge còn hạn và chưa bị hủy vì logout, đóng luồng hoặc sự kiện rủi ro.
- Giao dịch đăng nhập vẫn hợp lệ: account chưa bị khóa, Leaver chưa có hiệu lực, không có thay đổi chính sách làm kết quả cũ mất giá trị.
- IdP chỉ cấp kết quả xác thực cho **giao dịch đang chờ tương ứng**, không cho bất kỳ session nào tình cờ đăng nhập cùng username.

Một thông báo push đến được điện thoại **không chứng minh** các điều kiện trên đã đạt.

## 4. Đăng ký thiết bị push MFA: bước quyết định độ tin cậy

Push MFA chỉ đáng tin nếu **thiết bị nhận yêu cầu được đăng ký cho đúng User**. Lỗi trong enrollment có thể khiến kẻ tấn công thêm thiết bị của họ rồi chấp thuận đăng nhập, ngay cả khi luồng approve/deny sau đó vận hành đúng.

### Quy trình enrollment an toàn

1. Kiểm tra **identity source**, trạng thái Joiner và kết quả identity proofing phù hợp với mức rủi ro.
2. Yêu cầu người dùng xác thực bằng phương thức đủ mạnh đang có; tài khoản chưa có authenticator cần một quy trình khởi tạo riêng được kiểm soát.
3. Bắt đầu một **enrollment transaction** gắn với đúng identity, phiên, thiết bị và thời hạn.
4. Liên kết authenticator theo cơ chế của IdP; khi sản phẩm hỗ trợ, tạo khóa riêng trên thiết bị và lưu thông tin khóa công khai cùng metadata cần thiết ở phía máy chủ.
5. Xác minh người dùng kiểm soát thiết bị đang đăng ký; không chỉ tin rằng số điện thoại hoặc email khớp.
6. Ghi thiết bị vào inventory: authenticatorId, identityId, thời điểm đăng ký, trạng thái, loại phương thức và nguồn phê duyệt.
7. Thông báo đăng ký thiết bị mới qua kênh phù hợp, để chủ tài khoản phát hiện nếu không phải mình thực hiện.
8. Đặt quyền, số lượng thiết bị và quy trình thay thế theo chính sách; thử challenge trên thiết bị vừa đăng ký trước khi coi là hoạt động.

### Những kiểm soát đặc biệt quan trọng

| Rủi ro | Tình huống | Kiểm soát |
| --- | --- | --- |
| **Unauthorized enrollment** | Kẻ khác dùng session bị đánh cắp để thêm điện thoại. | Step-up, xác minh quyền sở hữu và thông báo độc lập; hạn chế enrollment từ session rủi ro. |
| **Wrong identity binding** | Điện thoại của User A bị gắn vào User B. | Dùng identityId và transaction ID ổn định; không đối sánh chỉ bằng email. |
| **Device reuse** | Điện thoại bàn giao cho nhân viên mới nhưng credential cũ còn tồn. | Thu hồi binding cũ, xóa cấu hình an toàn rồi enrollment mới. |
| **Lost/stolen device** | Người lạ kiểm soát điện thoại đã đăng ký. | Thu hồi authenticator nhanh, đánh giá phiên và dùng recovery có kiểm soát. |
| **Untrusted enrollment link** | Link hoặc QR bị phát tán, tái sử dụng. | Hạn ngắn, dùng một lần, ràng buộc giao dịch, tránh lộ token trong log/URL. |
| **Orphan authenticator** | Nhân viên nghỉ việc, thiết bị còn gắn vào IdP User. | Thu hồi trong Leaver; kiểm kê và đối soát binding. |

**Số điện thoại không đồng nghĩa với thiết bị đã được xác minh.** Việc đổi SIM hoặc tái cấp số không nên tự trao quyền thêm authenticator mới vào account.

## 5. Push bombing và MFA fatigue

**MFA fatigue** xảy ra khi người dùng nhận quá nhiều yêu cầu push, có thể khiến họ chấp thuận theo thói quen, bực bội hoặc bị gây áp lực. **Push bombing** là cách kẻ tấn công cố ý tạo hàng loạt yêu cầu như vậy, thường sau khi đã biết mật khẩu hoặc đã chạm được bước xác thực đầu tiên.

### Kịch bản

1. Kẻ tấn công có được mật khẩu của Lan từ một vụ lộ thông tin.
2. Họ liên tục thực hiện đăng nhập và kích hoạt thông báo MFA.
3. Lan nhìn thấy nhiều push vào thời điểm không đăng nhập.
4. Một cuộc gọi giả danh bộ phận hỗ trợ yêu cầu “bấm Approve để thông báo biến mất”.
5. Nếu Lan chấp thuận, yêu cầu của kẻ tấn công có thể hoàn tất xác thực.

Rủi ro ở đây là **social engineering kết hợp với thiết kế approve quá dễ**, không phải chỉ là vấn đề điện thoại kêu nhiều.

### Biện pháp giảm rủi ro

- **Giới hạn tần suất:** đặt rate limit theo User, thiết bị, nguồn yêu cầu và tín hiệu rủi ro; chống việc một kẻ tấn công dùng lượng request lớn gây phiền.
- **Cooldown và ngưỡng điều tra:** khi có chuỗi bị từ chối/hết hạn hoặc nhiều yêu cầu bất thường, tăng kiểm soát, tạm dừng kênh không phù hợp và cảnh báo.
- **Number matching:** yêu cầu người dùng đối chiếu một số/mã hiển thị trên màn hình đăng nhập với ứng dụng xác thực, thay vì chỉ bấm Approve vô điều kiện.
- **Hiển thị ngữ cảnh:** dịch vụ đăng nhập, thời gian, thiết bị hoặc thông tin vị trí được phép và có độ tin cậy đủ; hỗ trợ nhận biết yêu cầu bất ngờ.
- **Thao tác từ chối rõ ràng:** có lựa chọn Deny/Report suspicious activity dễ tìm và cơ chế báo sự cố.
- **Challenge ngắn hạn và một lần:** giảm cửa sổ có thể bị phê duyệt nhầm hoặc replay.
- **Phản ứng rủi ro:** đánh giá mật khẩu có thể đã lộ, phiên đang tồn tại và khả năng nâng mức xác thực hoặc yêu cầu credential mạnh hơn.

**Number matching làm giảm lỗi chấp thuận vô tình nhưng không tạo bảo vệ chống phishing tuyệt đối.** Trang giả mạo có thể chuyển tiếp thử thách hoặc mã trong thời gian thực, và người dùng vẫn có thể bị thuyết phục nhập mã. Với quyền đặc quyền hoặc giao dịch nhạy cảm, có thể cần phương thức **phishing-resistant** được thiết kế đúng như WebAuthn/FIDO2 hoặc kiểm soát bổ sung theo chính sách.

### Hướng dẫn người dùng khi nhận push lạ

Nếu đang **không đăng nhập**, người dùng cần **không chấp thuận**, dùng chức năng từ chối/báo đáng ngờ nếu có và thông báo theo kênh hỗ trợ nội bộ chính thức. Nếu nhận nhiều yêu cầu liên tiếp, có thể là dấu hiệu credential đã bị lộ; tổ chức cần điều tra và xử lý phiên/tài khoản theo quy trình.

Đừng yêu cầu người dùng tự bấm Approve để “kiểm tra hệ thống” hoặc “tắt cảnh báo”. Bộ phận hỗ trợ thực sự không nên yêu cầu xác nhận một push mà người dùng không chủ động khởi tạo.

## 6. Number matching, ngữ cảnh và chống phishing

### Number matching hoạt động thế nào?

Ở một triển khai phổ biến, màn hình đăng nhập hiển thị một số ngắn. Ứng dụng xác thực yêu cầu người dùng chọn hoặc nhập **đúng số đó** trước khi phê duyệt. IdP phải xác minh số được chọn thuộc **challenge đang chờ của phiên hiện tại**.

Ví dụ:

~~~text
Browser:
  Sign-in request: CRM
  Match this number: 47

Authenticator app:
  Did you start a sign-in to CRM?
  Choose the number shown in your browser: [12] [47] [81]

IdP:
  Verify device + challengeId + selected number + expiry + policy
~~~

Đây là sơ đồ trải nghiệm minh họa. Không nên dựa duy nhất vào số ngắn như một **bí mật** hoặc bằng chứng mật mã; cơ chế xác thực thiết bị và ràng buộc giao dịch vẫn cần được IdP thực thi.

### Thông tin ngữ cảnh cần hiển thị

| Thông tin | Lợi ích | Hạn chế |
| --- | --- | --- |
| Tên ứng dụng/đích | Giúp phát hiện yêu cầu khác ứng dụng đang dùng. | Cần lấy từ client đã đăng ký, không tin nhãn do bên ngoài tùy ý gửi. |
| Thời điểm | Nhận biết yêu cầu bất ngờ. | Đồng hồ và timezone cần diễn giải phù hợp. |
| Thiết bị/trình duyệt | Cung cấp dấu hiệu bổ sung. | User-Agent có thể thiếu chính xác hoặc bị giả mạo. |
| Vị trí/IP gần đúng | Có thể giúp phát hiện đăng nhập từ bối cảnh lạ. | VPN, mạng di động, proxy làm geolocation không chính xác; không dùng như bằng chứng quyết định duy nhất. |
| Number matching | Buộc đối chiếu giữa hai màn hình. | Vẫn có thể bị chuyển tiếp/phishing thời gian thực. |
| Loại hành động | Phân biệt login thường, enrollment, reset MFA, step-up. | Không chấp nhận metadata hành động chưa được server xác minh. |

### Transaction binding khác với chấp thuận đăng nhập chung

Đối với hành động nhạy cảm như thanh toán hoặc cấp quyền admin, một push MFA thông thường có thể xác thực **người dùng đang có mặt**, nhưng chưa chứng minh họ chấp thuận **đúng nội dung giao dịch**. Nếu chính sách yêu cầu xác nhận giao dịch, cần ràng buộc những chi tiết quan trọng vào challenge/approval và hiển thị rõ cho người dùng.

Ví dụ, “Approve login” không có nghĩa “Approve chuyển khoản 100 triệu đồng”. Cơ chế ký giao dịch, xác nhận ngoài băng có chi tiết được bảo vệ hoặc step-up theo resource phải được thiết kế độc lập và kiểm thử riêng.

## 7. State machine của push challenge

Một triển khai an toàn cần mô hình hóa yêu cầu xác thực bằng trạng thái rõ ràng, tránh việc hai thiết bị hoặc hai callback khiến cùng một challenge được phê duyệt nhiều lần.

| Trạng thái | Ý nghĩa | Chuyển tiếp phù hợp |
| --- | --- | --- |
| **CREATED** | IdP đã tạo yêu cầu gắn với giao dịch. | SENT hoặc CANCELLED. |
| **SENT/PENDING** | Đã gửi tín hiệu hoặc đang chờ người dùng. | APPROVED, DENIED, EXPIRED, CANCELLED. |
| **APPROVED** | Phản hồi đã được xác minh theo policy. | Hoàn tất giao dịch đăng nhập **tương ứng** một lần. |
| **DENIED** | Người dùng từ chối hoặc báo đáng ngờ. | Không tạo phiên từ challenge này; audit/cảnh báo. |
| **EXPIRED** | Hết thời hạn hợp lệ. | Không thể chấp thuận muộn. |
| **CANCELLED** | Giao dịch bị hủy, User bị khóa hoặc phiên không còn hợp lệ. | Không dùng lại challenge, dù push đến trễ. |

Trạng thái này là **mô hình nội bộ minh họa**, không phải tên trạng thái chuẩn của mọi nhà cung cấp.

### Logic xác minh phía IdP

~~~text
handlePushResponse(response):
    challenge = loadChallenge(response.challengeId)
    if challenge is absent:
        return DENY
    if challenge.state != PENDING:
        return DENY
    if now() >= challenge.expiresAt:
        markExpiredAtomically(challenge)
        return DENY

    identity = loadIdentity(challenge.identityId)
    if identity.lifecycleState disallows access:
        cancelChallengeAtomically(challenge)
        return DENY

    if not registeredAuthenticatorValid(
        identity,
        response.authenticatorId,
        response.deviceProof
    ):
        return DENY

    if not responseBoundToTransaction(
        response,
        challenge.authTransactionId,
        challenge.context,
        challenge.numberMatchingRule
    ):
        return DENY

    if not currentPolicyAllowsAuthentication(identity, challenge.context):
        cancelChallengeAtomically(challenge)
        return DENY

    if not compareAndSet(challenge.state, PENDING, APPROVED):
        return DENY

    completeOnlyBoundAuthTransaction(challenge.authTransactionId)
    auditWithoutSecrets(challenge, APPROVED)
    return APPROVED
~~~

Đây là pseudocode minh họa, không phải mã bảo mật hoàn chỉnh. Triển khai thực phải có cơ chế xác thực phản hồi phù hợp nhà cung cấp, bảo vệ kênh truyền, kiểm soát replay/race, phiên bản policy, xử lý timeout và cách phát token an toàn.

### Những lỗi logic cần tránh

- Chấp thuận một challenge bằng **username + cờ approved**, không có transaction ID.
- Đánh dấu APPROVED trước khi kiểm tra thiết bị, thời hạn hoặc trạng thái User.
- Nhận approval sau khi User đã bị Leaver hoặc account đã disabled.
- Cho approval của yêu cầu A hoàn tất đăng nhập B vì hai request dùng cùng User.
- Để challenge hết hạn được tái sử dụng sau retry.
- Gửi nhiều push và tự chấp nhận phản hồi đến từ một thiết bị đã bị xóa enrollment.
- Log toàn bộ token, mã recovery, khóa thiết bị hoặc dữ liệu nhạy cảm chỉ để debug.

## 8. Push authentication trong Joiner–Mover–Leaver

Quản lý vòng đời không chỉ tác động tới tài khoản ở IdP mà còn tới **authenticator gắn với account** và những challenge/phiên đang tồn tại.

### Joiner: kích hoạt và đăng ký thiết bị

Giả sử nhân viên Lan bắt đầu làm việc ngày 01/12:

1. HR hoặc nguồn có thẩm quyền phát Joiner, có mã nhân sự và ngày hiệu lực.
2. IAM xác minh nguồn, tạo/liên kết identity và kiểm tra proofing theo chính sách.
3. IdP User có thể được **pre-provision** trước ngày bắt đầu nhưng không mặc nhiên được đăng nhập vào các tài nguyên nghiệp vụ.
4. Lan thực hiện enrollment push authenticator bằng luồng được kiểm soát. Nếu được phép làm trước ngày đi làm, đó phải là quyền onboarding giới hạn, không phải quyền truy cập dữ liệu doanh nghiệp.
5. Đến ngày kích hoạt, IAM/IdP kiểm tra lại trạng thái và yêu cầu MFA; account chỉ được dùng trong phạm vi có hiệu lực.
6. Đối soát identityId, IdP User, authenticator đăng ký và các ứng dụng đích; lưu bằng chứng.

Một nguy cơ nghiêm trọng là **gửi link/QR enrollment tới nhầm người**. Luồng phải có hạn, liên kết đúng source identity và xác minh người sở hữu, không chỉ suy ra từ email.

### Mover: thay đổi vai trò hoặc mức bảo đảm

Lan chuyển từ bộ phận hỗ trợ sang quản trị hệ thống. Identity thường vẫn là một người, nhưng chính sách truy cập và mức xác thực cần đánh giá lại:

- Vai trò mới có yêu cầu **phishing-resistant MFA**, PAM hoặc step-up không?
- Push MFA hiện tại còn đủ cho quyền mới không, hay phải đăng ký phương thức mạnh hơn?
- Các role cũ và quyền ABAC theo department đã bị thu hồi đúng không?
- Phiên đăng nhập trước Mover có thể sử dụng quyền admin mới mà chưa thực hiện step-up hay không?
- Thiết bị push MFA đang dùng có còn tuân thủ chính sách quản lý thiết bị và rủi ro?

**Mover không mặc nhiên đòi đăng ký lại push MFA** nếu identity, thiết bị và chính sách vẫn hợp lệ. Nhưng Mover có thể kích hoạt **access review và authentication assurance review** khi chuyển sang tài nguyên nhạy cảm hơn.

### Leaver: vô hiệu hóa authenticator và chặn truy cập

Khi Lan nghỉ việc:

1. Nguồn HR phát Leaver có **effectiveAt** và phiên bản sự kiện đáng tin cậy.
2. IAM/IdP chặn đăng nhập mới và xử lý account theo chính sách.
3. Các **pending push challenges** thuộc account phải bị hủy hoặc trở nên vô hiệu, tránh approval đến trễ.
4. Authenticator binding của thiết bị bị thu hồi khỏi account hoặc không còn được chấp nhận.
5. Phiên đã đăng nhập, refresh token, access token, phiên cục bộ tại SaaS và credential riêng được xử lý theo khả năng thực tế của từng hệ thống.
6. Kiểm tra lại trạng thái ở IdP và ứng dụng; ghi những đường chưa thể thu hồi tức thời thành rủi ro còn lại có owner.
7. Retry của Joiner/Mover cũ không được phép kích hoạt lại User hoặc khôi phục binding MFA trái lifecycle state hiện tại.

**SCIM User với active=false không chứng minh toàn bộ push enrollment, session/token và quyền cục bộ đã bị thu hồi.** Mỗi cơ chế có thể cần thao tác và bằng chứng riêng.

### Ma trận tác động vòng đời

| Sự kiện | Trạng thái push authenticator mong muốn | Điều phải xác minh |
| --- | --- | --- |
| Joiner chưa kích hoạt | Enrollment chỉ theo policy onboarding; chưa dùng để mở quyền nghiệp vụ sớm. | IdP/app không cho truy cập trái mốc. |
| Joiner đã kích hoạt | Thiết bị hợp lệ và thuộc đúng User. | MFA thành công chỉ với challenge đúng phiên. |
| Mover thông thường | Có thể giữ authenticator đang hợp lệ. | Role/ABAC cập nhật, phiên cũ không giữ quyền trái chính sách. |
| Mover sang đặc quyền | Có thể phải nâng phương thức hoặc step-up. | Push đơn thuần không bypass yêu cầu phishing-resistant MFA/PAM. |
| Suspend | Không được xác thực trái chính sách. | Challenge đang chờ và session được xử lý theo phạm vi đình chỉ. |
| Leaver | Binding không còn được dùng cho đăng nhập; challenge cũ vô hiệu. | Không tạo phiên mới; session/credential tại đích được đối soát. |
| Rehire | Không tự khôi phục binding/thiết bị cũ. | Xác minh đúng người và enrollment theo chính sách hiện tại. |

## 9. Tích hợp IdP, SSO, SCIM, RBAC/ABAC và PAM

Push authentication là **một phương thức trong lớp xác thực**. Nó phối hợp với các thành phần quản lý danh tính, nhưng không thay thế các trách nhiệm khác.

| Thành phần | Vai trò liên quan | Điều push MFA không tự giải quyết |
| --- | --- | --- |
| **HR/nguồn danh tính** | Xác định quan hệ công việc, ngày kích hoạt, Mover, Leaver. | Chỉ vì push approve không có nghĩa hợp đồng còn hiệu lực. |
| **IAM/IGA** | Liên kết identity, owner, enrollment, policy và bằng chứng. | Một thiết bị đã đăng ký không chứng minh mọi tài khoản đích đúng quyền. |
| **IdP** | Tạo/kiểm chứng push challenge; áp chính sách xác thực. | Không tự kiểm soát mọi local session và role trong SaaS. |
| **SSO OIDC/SAML** | Truyền kết quả xác thực tới ứng dụng tin cậy. | Assertion/token hợp lệ không tự cấp quyền đọc mọi tài nguyên. |
| **SCIM/connector** | Tạo, cập nhật, vô hiệu hóa User và nhóm tại ứng dụng. | Không tự triển khai push MFA, không đảm bảo revoke mọi token/session. |
| **RBAC/ABAC** | Cho phép hành động theo role, thuộc tính, tenant và ngữ cảnh. | MFA đạt chưa đảm bảo quyền đúng chức năng/phạm vi. |
| **PAM/JIT** | Quản lý quyền đặc quyền theo thời gian và kiểm soát phiên. | Push approve có thể chưa đáp ứng yêu cầu chống phishing hoặc ký giao dịch. |
| **Audit/monitoring** | Phát hiện spam push, bất thường enrollment và sai lệch Leaver. | Không nên ghi secret hoặc dựa duy nhất vào thông báo delivered. |

### Push MFA và OIDC/SAML

Ứng dụng liên kết thường **không trực tiếp kiểm tra nút Approve**. IdP xác thực người dùng rồi hoàn thành giao thức SSO. Ứng dụng nên kiểm tra issuer, audience, chữ ký/thời hạn và những claim bảo đảm liên quan theo hợp đồng đã thỏa thuận; có thể xét **authentication context/assurance** nếu sản phẩm cung cấp và chính sách yêu cầu.

Không suy ra từ tên claim hoặc một cờ **mfa=true** rằng xác thực đã là phishing-resistant: còn phụ thuộc phương thức, thiết bị, quá trình enrollment, cách kiểm tra claim và ngữ cảnh thực tế.

### Push MFA và RBAC/ABAC

Ví dụ pseudo-policy:

~~~text
ALLOW report.read KHI
    identity.lifecycleState = ACTIVE
    AND identity.tenantId = report.tenantId
    AND roleAllows(identity, "report.read")
    AND session.authenticationAssurance >= requiredAssurance(report)
    AND session.isWithinAllowedTime
ELSE DENY
~~~

Trong chính sách này, push MFA có thể là **một đầu vào về mức bảo đảm phiên**, nhưng **không thay** điều kiện về tenant, vai trò, tài nguyên và trạng thái vòng đời.

### Step-up cho thao tác nhạy cảm

Một người đã đăng nhập vào dashboard bằng push MFA nhưng muốn vào chức năng quản trị production. Hệ thống có thể yêu cầu xác thực tăng cường. Nếu chính sách quy định **phishing-resistant authenticator**, không được tự xem chấp thuận push thường là đủ.

Việc lựa chọn MFA phù hợp cần gắn với rủi ro từng hành động, chứ không chỉ gắn một cờ chung cho toàn bộ tài khoản.

## 10. Mất thiết bị, thay thiết bị và khôi phục tài khoản

Điện thoại có thể mất, hỏng, hết pin, đổi số hoặc người dùng không còn truy cập ứng dụng xác thực. Đây là bài toán thiết kế recovery, không nên giải bằng cách **tắt MFA tạm thời không có kiểm soát**.

### Quy trình thay thiết bị

1. Người dùng báo mất/đổi thiết bị qua kênh hỗ trợ được xác định; kiểm tra danh tính và mức rủi ro yêu cầu.
2. Xem xét có phiên đáng ngờ, yêu cầu push bị từ chối hoặc dấu hiệu account takeover không.
3. Thu hồi authenticator binding bị mất hoặc không còn sử dụng; quản lý session/token liên quan theo chính sách.
4. Đăng ký thiết bị mới bằng **recovery/enrollment workflow** đủ mức tin cậy, có step-up hoặc re-proofing khi cần.
5. Thử thách thiết bị mới; xác nhận đúng identityId, không liên kết nhầm người chỉ vì dùng lại số điện thoại.
6. Thông báo thay đổi, ghi audit, xem xét giới hạn tạm thời đối với quyền nhạy cảm.

### Các phương án recovery

| Phương án | Khi nào có thể phù hợp | Điều kiện |
| --- | --- | --- |
| Authenticator dự phòng đã đăng ký | Người dùng còn một thiết bị hợp lệ. | Dùng đúng chính sách đa thiết bị, bảo vệ việc xóa/thêm thiết bị. |
| Recovery code được phát trước | User có mã dự phòng được bảo quản an toàn. | Mã một lần, lưu phía server an toàn, không dùng lại; cảnh báo sử dụng. |
| Phương thức mạnh khác (ví dụ passkey) | IdP hỗ trợ nhiều phương thức. | Đảm bảo phương thức đáp ứng mức bảo đảm của hành động recovery. |
| Hỗ trợ thủ công / identity proofing lại | Không còn authenticator hợp lệ hoặc có dấu hiệu gian lận. | Kiểm tra có thẩm quyền, bằng chứng, phê duyệt và giới hạn đặc quyền. |

**Recovery là một phần của authentication security.** Kẻ tấn công có thể không vượt được push MFA trực tiếp nhưng tìm cách reset thiết bị xác thực qua helpdesk. Vì vậy phải kiểm thử cả các đường thay thiết bị, đăng ký lại và hủy thiết bị.

### Chế độ offline, mất mạng và thông báo đến trễ

- Nếu điện thoại không có mạng, push có thể không đến. IdP nên xử lý **timeout/expired**, không tự coi là được chấp thuận.
- Nếu push đến trễ sau khi challenge đã hết hạn, nút Approve không được tạo phiên hợp lệ.
- Có thể hỗ trợ phương thức xác thực khác đã đăng ký và được chính sách chấp nhận, nhưng không chuyển tự động sang kênh yếu hơn chỉ vì không nhận được push.
- Nếu thiết bị có nhiều yêu cầu đồng thời, ứng dụng phải hiển thị và phản hồi **đúng challenge**; không dùng kết quả A cho giao dịch B.
- Trạng thái delivery của push service không đủ làm bằng chứng authenticator đã thực hiện xác thực.

## 11. Kiểm thử push authentication

Kiểm thử cần bao phủ **luồng bình thường, luồng bị từ chối, lỗi phân tán và sự kiện JML**. Dùng tài khoản và thiết bị thử nghiệm được phép trong môi trường cô lập; không gửi hàng loạt push vào thiết bị của người dùng thật.

### Ma trận test

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| PUSH-01 | User ACTIVE, đúng password, push hợp lệ, user xác nhận đúng challenge. | Hoàn tất **đúng phiên** theo MFA policy. |
| PUSH-02 | User bấm Deny. | Không phát phiên; có bản ghi từ chối và đường báo nghi vấn khi hỗ trợ. |
| PUSH-03 | User không phản hồi cho đến timeout. | Challenge hết hạn; callback đến trễ không được chấp thuận. |
| PUSH-04 | Một challenge được Approve hai lần hoặc callback lặp. | Chỉ một transition có hiệu lực; không cấp thêm session ngoài thiết kế. |
| PUSH-05 | Thiết bị khác chưa enrollment gửi phản hồi. | Bị từ chối; không ánh xạ nhầm identity. |
| PUSH-06 | Number matching sai. | Không hoàn tất MFA cho giao dịch. |
| PUSH-07 | Push đến sai User/tenant hoặc sai authTransactionId. | Không chấp thuận, ghi cảnh báo và điều tra binding. |
| PUSH-08 | User nhận nhiều push bất ngờ. | Giới hạn tần suất/đánh giá rủi ro; không tự unlock hoặc bypass. |
| PUSH-09 | Thiết bị bị thu hồi sau khi challenge được gửi. | Phản hồi từ binding đã thu hồi không còn hợp lệ. |
| PUSH-10 | Joiner chưa kích hoạt cố dùng push đã enroll. | Không vào được tài nguyên nghiệp vụ trước thời điểm cho phép. |
| PUSH-11 | Mover nâng đặc quyền nhưng policy yêu cầu phương thức mạnh hơn. | Push thông thường không vượt qua step-up cần thiết. |
| PUSH-12 | Leaver trong lúc challenge đang chờ. | Pending challenge bị vô hiệu; không tạo phiên mới. |
| PUSH-13 | Leaver xong nhưng job Joiner cũ được retry. | Không đăng ký lại/bật lại authenticator trái nguồn hiện hành. |
| PUSH-14 | Push transport mất mạng hoặc lỗi service. | Timeout/pending có giới hạn; fallback được kiểm soát. |
| PUSH-15 | Hai tab cùng đăng nhập và gửi hai push. | Approval chỉ mở đúng tab/giao dịch tương ứng. |
| PUSH-16 | Enrollment thiết bị mới từ session rủi ro. | Step-up/identity verification theo chính sách; không thêm thiết bị trái phép. |
| PUSH-17 | Recovery code đã dùng được gửi lại. | Bị từ chối; không tạo binding mới. |
| PUSH-18 | SSO thành công nhưng không có role tài nguyên. | Ứng dụng vẫn từ chối thao tác nghiệp vụ theo RBAC/ABAC. |

### Một test Leaver có tính quyết định

~~~text
test("Leaver cancels pending push"):
    user = createSyntheticActiveIdentity()
    device = enrollSyntheticAuthenticator(user)
    challenge = startLoginAndTriggerPush(user, device)
    assert challenge.state == PENDING

    event = emitAuthoritativeLeaver(
        user.sourceKey,
        effectiveAt = controlledClock.now,
        sourceVersion = 18
    )

    awaitLifecycleConvergenceWithDeadline(event)
    attempt = approveChallengeFromTestDevice(challenge, device)
    assert attempt.denied
    assert noNewSessionWasCreatedFor(challenge.authTransactionId)

    retryStaleJoinerJob(sourceVersion = 16)
    assert user.lifecycleState == TERMINATED
    assert newLoginIsDenied(user)
    assert auditShowsChallengeCancelled(challenge.id)
~~~

Pseudocode chỉ minh họa test contract. Trong hệ thống thật cần định nghĩa rõ độ trễ thu hồi theo chính sách; một test phải **fail** khi vượt mức chấp nhận, không mặc định mọi nhà cung cấp xử lý tức thời.

### Điều cần đo thay vì chỉ PASS/FAIL

- Từ lúc tạo challenge đến lúc thông báo được nhận và phản hồi được IdP kiểm chứng.
- Tỷ lệ challenge bị từ chối, hết hạn, gửi trùng hoặc có tín hiệu nguy cơ.
- Số lần một User nhận push bất ngờ trong khoảng thời gian xác định.
- Thời gian thu hồi authenticator sau yêu cầu khóa hoặc Leaver.
- Số tài khoản không có phương thức recovery hợp lệ và số binding không owner.
- Sự chênh lệch giữa trạng thái tại IdP với quyền sử dụng thực tế ở ứng dụng.

## 12. Kiểm toán, quyền riêng tư và giám sát

Một log cho push authentication nên hỗ trợ điều tra mà không trở thành kho chứa bí mật.

| Thuộc tính log | Ý nghĩa |
| --- | --- |
| identityId / IdP User ID | Xác định đúng chủ thể và namespace. |
| challengeId, authTransactionId, correlationId | Truy vết phản hồi đến đúng giao dịch. |
| authenticatorId hoặc device reference có bảo vệ | Biết thiết bị nào tham gia mà không lộ secret. |
| method, policy version, assurance context | Chứng minh phương thức đáp ứng chính sách nào. |
| createdAt, respondedAt, expiresAt | Đo thời gian và phát hiện callback trễ. |
| result: APPROVED/DENIED/EXPIRED/CANCELLED | Phân biệt hành vi và phát hiện bất thường. |
| reason/risk flags | Phát hiện push fatigue, enrollment lạ, Leaver hoặc thiết bị bị thu hồi. |
| JML event/version/effectiveAt | Liên hệ đăng nhập với trạng thái vòng đời đúng thời điểm. |
| target application/clientId | Đánh giá ngữ cảnh và tác động của xác thực. |

### Ví dụ bản ghi nội bộ

~~~json
{
  "eventType": "PUSH_MFA_CHALLENGE",
  "identityId": "ID-LAN-2041",
  "authTransactionId": "auth-tx-518",
  "challengeId": "push-993",
  "authenticatorRef": "device-binding-17",
  "clientId": "crm-web",
  "method": "PUSH_NUMBER_MATCHING",
  "policyVersion": "auth-policy-v8",
  "createdAt": "2026-12-01T09:10:00+07:00",
  "respondedAt": "2026-12-01T09:10:12+07:00",
  "result": "DENIED",
  "reason": "USER_REPORTED_UNEXPECTED_REQUEST",
  "correlationId": "corr-7211"
}
~~~

Đây là dữ liệu minh họa, không phải schema chuẩn của OIDC, SAML, SCIM hay push service. **Không ghi mật khẩu, seed OTP, private key, mã recovery, cookie hoặc access/refresh token nguyên vẹn**. Vị trí và thông tin thiết bị là dữ liệu có thể liên quan quyền riêng tư; chỉ thu thập theo mục đích bảo mật đã xác định, giới hạn quyền đọc và thời gian lưu giữ.

### Cảnh báo có giá trị vận hành

- Nhiều push được tạo cho một User trong thời gian ngắn nhưng User liên tục không chấp thuận.
- Liên tiếp Deny/Report rồi xuất hiện Approve trong bối cảnh khác thường.
- Enrollment thiết bị mới sau một chuỗi đăng nhập thất bại hoặc recovery.
- Authenticator đã bị thu hồi vẫn có callback hoặc dấu hiệu sử dụng.
- Challenge được tạo sau Leaver hoặc tài khoản bị suspension.
- Tỷ lệ callback trễ, lỗi delivery hoặc trạng thái không khớp tăng đột ngột.
- Các User đặc quyền chỉ có phương thức push thường dù chính sách yêu cầu phishing-resistant MFA.

Không tự kết luận người dùng gian lận chỉ vì vị trí IP lạ, push bị từ chối hoặc điện thoại mất kết nối. Cần kết hợp bằng chứng, phân loại rủi ro và quy trình phản hồi có người chịu trách nhiệm.

## 13. Các tình huống thực hành

### Tình huống A — Người dùng liên tục nhận push không rõ nguồn

**Bối cảnh:** Lan đang ăn trưa, không đăng nhập hệ thống nào nhưng điện thoại nhận 20 yêu cầu Approve CRM. Một cuộc gọi tự xưng IT bảo Lan bấm Approve để “đồng bộ tài khoản”.

**Câu hỏi:** Đây là loại nguy cơ gì và cách xử lý phù hợp?

**Gợi ý:** Có dấu hiệu **MFA fatigue/push bombing kết hợp social engineering**. Không approve. Từ chối/báo nghi vấn, liên hệ bộ phận hỗ trợ qua kênh đã biết; IAM/Security kiểm tra login attempts, credential, phiên hiện hữu và áp hạn chế rủi ro. Dùng rate limit, number matching và chính sách xác thực mạnh theo mức nhạy cảm.

### Tình huống B — Number matching đúng nhưng trang đăng nhập giả

**Bối cảnh:** Lan nhập mật khẩu vào một trang giống IdP thật. Trang đó chuyển tiếp giao dịch xác thực đến IdP và hiện số trùng với push trong authenticator app.

**Câu hỏi:** Vì sao number matching chưa đủ để bảo đảm chống phishing?

**Gợi ý:** Kẻ tấn công có thể chuyển tiếp challenge trong thời gian thực. Number matching giảm nhấn nhầm nhưng không tự gắn credential với **origin/RP** như WebAuthn/FIDO2. Với ứng dụng rủi ro cao, cân nhắc phishing-resistant MFA và kiểm soát luồng đăng nhập.

### Tình huống C — Push approve của phiên cũ đến sau Leaver

**Bối cảnh:** HR phát Leaver hiệu lực ngay trong khi người dùng còn một push đang chờ. Sau khi IdP nhận sự kiện Leaver, người dùng nhấn Approve.

**Câu hỏi:** IdP cần xử lý thế nào?

**Gợi ý:** Không cho phép approval tạo phiên mới. Phải kiểm tra lifecycle state hiện hành, hủy hoặc từ chối challenge đang chờ, thu hồi binding/phiên phù hợp và ghi audit. Đồng thời xác minh ứng dụng đích không còn đường truy cập trái chính sách.

### Tình huống D — Đổi điện thoại nhưng giữ số điện thoại

**Bối cảnh:** Nhân viên mua điện thoại mới, số SIM không đổi. Helpdesk tự đăng ký thiết bị mới chỉ dựa trên việc người gọi đọc đúng số điện thoại.

**Câu hỏi:** Lỗ hổng nằm ở đâu?

**Gợi ý:** Số điện thoại không chứng minh người gọi là chủ identity và không chứng minh sở hữu authenticator cũ. Cần luồng recovery, step-up/re-proofing theo rủi ro, thu hồi binding cũ và audit; không đăng ký chỉ vì số SIM trùng.

### Tình huống E — Mover sang tài khoản quản trị

**Bối cảnh:** Lan được điều sang vai trò quản trị cloud. Lan đã có push MFA approve/deny nhưng chính sách yêu cầu phishing-resistant MFA cho quyền admin.

**Câu hỏi:** Có nên giữ nguyên push MFA làm điều kiện duy nhất để vào admin console?

**Gợi ý:** Không nếu phương thức hiện tại không đáp ứng chính sách. Cần đăng ký phương thức phishing-resistant được chấp nhận, thực hiện step-up/PAM/JIT khi cần và kiểm tra thu hồi role cũ trong Mover.

### Tình huống F — Push đến đúng thiết bị nhưng hoàn tất sai phiên

**Bối cảnh:** Lan mở hai tab đăng nhập cùng lúc. Push thuộc tab A được phê duyệt, nhưng tab B cũng báo đã hoàn tất MFA.

**Câu hỏi:** Sai ở lớp nào?

**Gợi ý:** IdP hoặc client đã thiếu **transaction binding**. Approval phải được gắn với challengeId và authTransactionId cụ thể; kết quả A không được mở B. Kiểm tra state machine, compare-and-set, callback và SSO state/nonce nếu có.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao một push notification được giao thành công không đủ chứng minh người dùng đã xác thực?**

Vì delivery chỉ chứng minh tín hiệu đến kênh thông báo, không xác minh User đã chấp thuận bằng authenticator hợp lệ hoặc challenge có được ràng buộc đúng phiên.

**2. Number matching có biến mọi phương thức push thành phishing-resistant MFA không?**

Không. Nó giảm việc approve nhầm, nhưng có thể bị chuyển tiếp thời gian thực; mức chống phishing phụ thuộc cơ chế mật mã, nguồn gốc, RP binding và triển khai.

**3. Nếu người dùng mất điện thoại nhưng vẫn giữ số SIM, có nên tự cấp lại push MFA không?**

Không. Phải xác minh chủ thể theo quy trình recovery/enrollment, không dùng số điện thoại làm bằng chứng duy nhất.

**4. MFA thành công qua IdP có chứng minh User được truy cập toàn bộ dữ liệu CRM không?**

Không. Ứng dụng phải kiểm tra authorization RBAC/ABAC, tenant, vai trò, tài nguyên và trạng thái hiện hành.

**5. Trong Leaver, chỉ đổi SCIM active=false có bảo đảm các push đang chờ đều không thể hoàn tất không?**

Không mặc định. IdP cần hủy/không chấp nhận challenge; kiểm tra session, authenticator binding và đường truy cập ở ứng dụng.

**6. Mover có nhất thiết phải xóa toàn bộ thiết bị MFA và đăng ký lại không?**

Không. Phải đánh giá thay đổi mức bảo đảm, rủi ro và quyền; nếu binding vẫn đáng tin, có thể giữ. Quyền nhạy cảm hơn có thể yêu cầu phương thức mạnh hơn.

**7. Có thể ghi toàn bộ access token hoặc secret của thiết bị vào log để debug push failure không?**

Không. Log tối thiểu với correlation ID và trạng thái, che/loại bỏ bí mật và bảo vệ quyền đọc.

**8. Khi không nhận push vì điện thoại offline, hệ thống nên làm gì?**

Cho challenge hết hạn hoặc xử lý lỗi theo chính sách; chỉ dùng fallback đã được phê duyệt và bảo vệ, không tự coi timeout là approved.

## Ghi nhớ

- **Push authentication** dùng ứng dụng xác thực trên thiết bị đã đăng ký để phê duyệt một **challenge gắn với đúng phiên**, thường là yếu tố bổ sung trong MFA. Thông báo push **không phải** bằng chứng xác thực.
- **Enrollment an toàn**, ràng buộc identity–thiết bị–challenge và xác minh phản hồi tại IdP là nền tảng; không liên kết account chỉ bằng email hoặc số điện thoại.
- **MFA fatigue/push bombing**, phishing, callback đến trễ, device loss và recovery yếu là các rủi ro trọng tâm. Number matching và hiển thị ngữ cảnh giúp giảm rủi ro nhưng **không mặc nhiên chống phishing**.
- **Joiner** đăng ký authenticator đúng người và kích hoạt đúng thời điểm; **Mover** đánh giá lại mức bảo đảm và quyền; **Leaver** chặn đăng nhập, hủy challenge chờ và thu hồi binding/đường truy cập liên quan.
- **IdP/SSO** xác thực liên thông, **SCIM** hỗ trợ provisioning, **RBAC/ABAC/PAM** thực thi quyền. Push approve không tự cho phép mọi hành động và không bảo đảm session/token tại mọi ứng dụng đã được thu hồi.
- Thiết kế **rate limit, challenge dùng một lần, transaction binding, kiểm thử âm, readback, audit và phương án recovery an toàn** để tăng khả năng chống lạm dụng và giảm quyền truy cập tồn dư trong toàn bộ vòng đời danh tính.
