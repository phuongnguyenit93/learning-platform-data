# Login notification — Thông báo đăng nhập an toàn và hữu ích

Một người dùng đang làm việc thì nhận được thông báo: tài khoản của họ vừa đăng nhập từ một thiết bị mới. Nếu đó là chính họ, thông báo giúp họ nhận biết một phiên mới đã được tạo. Nếu họ không thực hiện đăng nhập, thông báo có thể là tín hiệu sớm về việc mật khẩu, passkey, token hoặc thiết bị đã bị chiếm. Tuy nhiên, một thông báo sai thời điểm, chứa quá nhiều dữ liệu hoặc dẫn tới một trang giả mạo có thể tạo thêm rủi ro. Vì vậy, thông báo đăng nhập phải được thiết kế như một phần của hệ thống bảo mật tài khoản: sự kiện cần chính xác, nội dung cần an toàn, kênh gửi cần đáng tin và hành động phản ứng cần được bảo vệ.

**Login notification (thông báo đăng nhập)** là thông báo gửi tới chủ tài khoản hoặc nhóm vận hành khi có một sự kiện đăng nhập đáng quan tâm, chẳng hạn đăng nhập thành công từ thiết bị mới, thay đổi ngữ cảnh bất thường, đăng nhập thất bại theo ngưỡng hoặc thay đổi trạng thái xác thực. Thông báo giúp người dùng nhận biết và phản ứng với hoạt động tài khoản; nó không phải yếu tố xác thực, không chứng minh người nhận là người đã đăng nhập và không tự quyết định quyền truy cập.

Bài học thuộc chương **Đăng nhập** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối thông báo đăng nhập với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống giả mạo thông báo, replay và lạm dụng notification; đồng thời thiết kế cách cảnh báo và phản ứng phù hợp với rủi ro.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích mục đích của login notification và phân biệt nó với OTP, MFA challenge, login confirmation và audit log.
- Xác định sự kiện nào nên tạo thông báo: đăng nhập mới, đăng nhập rủi ro, đăng nhập thất bại theo ngưỡng, thay đổi credential hoặc thu hồi phiên.
- Thiết kế event schema có định danh, thời gian, trạng thái, phương thức xác thực và ngữ cảnh tối thiểu.
- Chọn kênh gửi phù hợp như in-app inbox, email, push hoặc SMS theo mức độ nhạy cảm và độ tin cậy.
- Viết nội dung thông báo hữu ích nhưng không làm lộ mật khẩu, OTP, token, session ID hoặc dữ liệu vị trí quá chi tiết.
- Phòng chống phishing, spoofing, notification fatigue, SMS bombing và lạm dụng chức năng “không phải tôi”.
- Thiết kế đường phản ứng an toàn để người dùng xem phiên, thu hồi truy cập, đổi credential hoặc khôi phục tài khoản.
- Xử lý giao nhận bất đồng bộ, retry, deduplication, idempotency, rate limit và lỗi nhà cung cấp.
- Bảo vệ quyền riêng tư, khả năng tiếp cận, ngôn ngữ và tùy chọn thông báo.
- Viết tiêu chí kiểm thử cho event giả, event trùng, thông báo trễ, kênh bị chiếm và phản ứng sau account takeover.

## 2. Login notification giải quyết vấn đề gì?

Sau khi người dùng đăng nhập, họ thường không biết phiên mới được tạo ở đâu, bằng phương thức nào hoặc có phải chính họ vừa thực hiện hay không. Một thông báo kịp thời giúp:

- **Nhận biết hoạt động:** người dùng biết tài khoản vừa được truy cập hoặc có thay đổi xác thực.
- **Phát hiện sớm:** người dùng nhận ra lần đăng nhập lạ trước khi attacker tiếp tục thao tác.
- **Hỗ trợ phản ứng:** thông báo đưa người dùng tới trang quản lý phiên, bảo mật tài khoản hoặc quy trình hỗ trợ chính thức.
- **Tăng khả năng kiểm toán:** sự kiện có thể được liên kết với audit record và incident investigation.
- **Tạo minh bạch:** người dùng hiểu tài khoản đang có phiên hoặc credential nào hoạt động.

Thông báo chỉ có giá trị khi hệ thống tạo nó từ sự kiện đáng tin cậy và người dùng có thể nhận biết thông báo thật. Nếu notification service tự suy ra đăng nhập từ một request chưa được xác minh, hoặc email chứa liên kết giả, lớp cảnh báo có thể trở thành một con đường tấn công mới.

### 2.1. Thông báo không phải xác thực

Một email nói “Bạn vừa đăng nhập” không chứng minh người nhận đã đăng nhập; email có thể được chuyển tiếp, gửi nhầm hoặc bị chiếm. Việc bấm “Đó là tôi” trong email cũng không nên được xem là bằng chứng đủ để xác nhận danh tính hoặc bỏ qua MFA.

Login notification là kênh thông tin một chiều hoặc tương tác có kiểm soát. Việc xác thực vẫn dựa trên password, passkey, MFA, certificate, token hoặc phương thức được thiết kế. Quyền truy cập vẫn do authorization policy quyết định.

### 2.2. Phân biệt các loại thông điệp

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Login notification | Báo một sự kiện đăng nhập đã xảy ra | “Tài khoản vừa đăng nhập trên trình duyệt mới” |
| MFA challenge | Yêu cầu người dùng cung cấp bằng chứng để hoàn tất xác thực | Prompt passkey, security key hoặc OTP |
| Login approval | Yêu cầu phê duyệt một lần đăng nhập đang chờ | “Bạn có đang cố đăng nhập không?” |
| Security alert | Báo sự kiện bảo mật hoặc thay đổi credential | “Phương thức khôi phục vừa được thay đổi” |
| Audit log | Ghi nhận sự kiện cho quản trị/điều tra | Event ID, actor, timestamp, policy decision |
| Marketing notification | Thông tin sản phẩm hoặc quảng bá | Không được trộn với cảnh báo bảo mật thiết yếu |

Không biến thông báo sau đăng nhập thành một approval challenge ngầm. Nếu hệ thống yêu cầu phê duyệt trước khi cấp phiên, đó là một luồng xác thực riêng, có transaction binding, timeout, chống replay và xử lý từ chối rõ ràng.

## 3. Những sự kiện nào nên gửi thông báo?

Không phải mọi request tới trang đăng nhập đều cần một email. Hệ thống cần phân biệt attempt, authentication success, session creation và thay đổi bảo mật.

| Sự kiện | Thời điểm tạo | Thông báo thường phù hợp |
| --- | --- | --- |
| Đăng nhập thành công trên thiết bị mới | Sau khi authentication thành công và phiên được tạo | Có, thường ưu tiên |
| Đăng nhập thành công từ ngữ cảnh rủi ro cao | Sau quyết định cho phép/step-up và tạo phiên | Có, theo policy |
| Đăng nhập thành công thông thường | Theo tùy chọn và rủi ro; có thể gộp hoặc chỉ hiển thị in-app | Tùy sản phẩm |
| Nhiều lần đăng nhập thất bại | Khi vượt ngưỡng hoặc có mẫu đáng ngờ | Có thể gửi cảnh báo có giới hạn |
| Tài khoản bị khóa do đăng nhập thất bại | Sau khi trạng thái khóa được commit | Có |
| MFA/passkey mới được thêm hoặc xóa | Sau khi thay đổi credential được xác nhận | Có, ưu tiên cao |
| Mật khẩu hoặc recovery method được đổi | Sau khi thay đổi hoàn tất | Có, ưu tiên cao |
| Phiên/thiết bị bị thu hồi | Sau khi server ghi nhận revoke | Có thể gửi xác nhận |
| Refresh token reuse hoặc dấu hiệu session hijacking | Khi hệ thống xác định sự kiện theo policy | Cảnh báo và kích hoạt incident response |
| Yêu cầu đăng nhập bị từ chối | Khi có giá trị cảnh báo và không tạo notification flood | Có thể gửi theo ngưỡng |

### 3.1. Chỉ báo thành công sau khi thành công thực sự

Sự kiện “login succeeded” chỉ nên được phát sau khi các bước bắt buộc đã hoàn tất: credential được xác minh, policy cho phép, session/token được tạo và trạng thái được ghi nhận nhất quán. Không gửi thông báo thành công chỉ vì người dùng đã nhập đúng mật khẩu nếu MFA còn chưa hoàn tất hoặc policy vẫn đang hold.

Nếu hệ thống dùng bước phê duyệt trước khi cấp phiên, hãy gửi thông báo dạng “Có yêu cầu đăng nhập đang chờ” chứ không ghi “Đăng nhập thành công”. Trạng thái phải phản ánh chính xác điều đã xảy ra.

### 3.2. Phân biệt login attempt và login success

Một attacker có thể thử hàng nghìn mật khẩu sai. Nếu gửi email cho từng attempt, hệ thống có thể bị dùng để spam hoặc làm người dùng bỏ qua cảnh báo thật. Nên nhóm theo account, nguồn, cửa sổ thời gian và mức rủi ro; vẫn ghi audit event đầy đủ để điều tra.

Không gửi thông báo chứa thông tin giúp attacker xác định tài khoản có tồn tại, chẳng hạn phản hồi khác nhau cho email đã đăng ký và email chưa đăng ký trong luồng công khai. Cần cân bằng thông báo hữu ích với chống account enumeration.

## 4. Mô hình sự kiện đăng nhập

Thông báo nên được tạo từ một event có cấu trúc, phát hành bởi authentication/session service đáng tin cậy. Notification service không nên tự suy ra trạng thái xác thực từ dữ liệu trình duyệt hoặc log không xác minh.

Một event khái niệm:

~~~json
{
  "event_id": "evt_01J...",
  "event_type": "LOGIN_SUCCEEDED",
  "occurred_at": "2026-11-22T06:00:00Z",
  "principal_id": "usr_...",
  "session_ref": "sess_ref_...",
  "client_type": "WEB",
  "auth_methods": ["PASSKEY"],
  "device_label": "Chrome on Windows",
  "network_context": {
    "country": "VN",
    "network_type": "CORPORATE",
    "location_precision": "COUNTRY"
  },
  "risk_band": "LOW",
  "policy_version": "login-policy-v4"
}
~~~

Đây là schema minh họa. Không đưa raw access token, refresh token, OTP, password, cookie, private key hoặc session ID có thể sử dụng trực tiếp vào event. session_ref nên là reference nội bộ không có quyền bearer và chỉ dùng để tra cứu trong hệ thống có kiểm soát.

### 4.1. Trường dữ liệu nên có

- **Event ID:** định danh duy nhất để deduplicate và truy vết.
- **Event type:** login success, login failure threshold, credential changed, session revoked...
- **Occurred at:** thời điểm sự kiện thực sự xảy ra, chuẩn UTC.
- **Principal reference:** tài khoản nội bộ đã được xác định; không lấy user ID do client tự khai.
- **Session reference:** tham chiếu phiên nếu sự kiện tạo hoặc thay đổi phiên.
- **Authentication context:** phương thức đã dùng, mức bảo đảm/độ mới theo policy.
- **Device/network context:** mô tả khái quát, chỉ gồm dữ liệu cần thiết.
- **Risk decision:** risk band hoặc reason code phù hợp; tránh gửi score nội bộ chi tiết cho người dùng.
- **Policy/version:** giúp điều tra vì sao sự kiện được thông báo.

### 4.2. Nguồn sự kiện phải đáng tin

Notification service chỉ nhận event từ producer được xác thực bằng service identity, message broker ACL, mTLS hoặc cơ chế ký/xác minh phù hợp. Event phải gắn với transaction/session đã commit. Nếu dùng webhook từ bên ngoài, cần xác minh chữ ký, timestamp, event ID, audience và chống replay.

Không tin một request frontend như POST /notify-login có body “user vừa đăng nhập” rồi gửi email. Client không có thẩm quyền tự tuyên bố authentication success.

## 5. Kiến trúc phát thông báo

Một kiến trúc điển hình tách authentication khỏi delivery:

~~~mermaid
flowchart LR
    A[Authentication service] -->|Login/session event| O[(Transactional outbox)]
    O --> Q[Event broker]
    Q --> N[Notification policy service]
    N --> P[Preference and contact resolver]
    N --> T[Template and localization]
    P --> D[Delivery dispatcher]
    T --> D
    D --> E[Email provider]
    D --> U[Push provider]
    D --> I[In-app inbox]
    D --> S[SMS provider]
    E --> R[Delivery result]
    U --> R
    I --> R
    S --> R
    R --> L[(Delivery/audit status)]
~~~

### 5.1. Transactional outbox

Nếu authentication service commit session thành công nhưng gửi event thất bại, người dùng có thể không nhận được cảnh báo. Ngược lại, nếu gửi notification trước khi transaction tạo session commit, người dùng có thể nhận thông báo thành công dù login đã rollback.

Transactional outbox giảm sự không nhất quán:

1. Trong cùng transaction database, tạo session và ghi một outbox event LOGIN_SUCCEEDED.
2. Sau commit, worker đọc outbox và publish event.
3. Notification service xử lý event, kiểm tra policy và tạo delivery job.
4. Worker gửi qua provider; lưu trạng thái queued/sent/delivered/failed nếu provider hỗ trợ.
5. Retry lỗi tạm thời theo backoff; dùng event ID và idempotency key để tránh gửi trùng ngoài ý muốn.

Outbox không bảo đảm email/push được giao tới thiết bị; nó giúp event không bị mất giữa commit nghiệp vụ và publish. Delivery status cũng cần phân biệt “provider accepted” với “người dùng đã đọc”.

### 5.2. Asynchronous delivery

Không nên chờ email/SMS provider trả lời trong đường xử lý login nếu việc đó không cần thiết. Notification delivery thường chạy bất đồng bộ để tránh làm chậm authentication và giảm phụ thuộc vào nhà cung cấp. Nếu provider lỗi, login vẫn theo quyết định authentication; hệ thống ghi nhận lỗi và retry theo policy.

Với thông báo bắt buộc trước khi cấp phiên (login approval), đó là một authentication workflow khác: request phải ở trạng thái pending, có challenge/transaction ID, timeout và quy tắc deny/approve rõ. Không dùng delivery email thông thường làm bước phê duyệt mặc định.

## 6. Chọn kênh gửi và quản lý contact

| Kênh | Ưu điểm | Rủi ro/giới hạn | Cách dùng |
| --- | --- | --- | --- |
| In-app security inbox | Gắn với tài khoản đang đăng nhập; có thể hiển thị lịch sử | Attacker đang chiếm phiên cũng có thể đọc; không hữu ích nếu người dùng không mở app | Lịch sử và chi tiết sự kiện trong phiên đã xác thực |
| Email | Phổ biến, có thể gửi khi người dùng offline | Email có thể bị chiếm, spoofing, forwarding và phishing | Cảnh báo ngoài băng; nội dung tối thiểu, link an toàn |
| Push notification | Nhanh, thuận tiện trên thiết bị | Lock screen có thể lộ thông tin; push provider/device token có vòng đời riêng | Cảnh báo ngắn; mở app chính thức để xem chi tiết |
| SMS | Có thể tới điện thoại không cần app | SIM swap, SS7/interception, số đổi chủ, SMS bombing | Kênh dự phòng theo policy, không coi là kênh mạnh mặc định |
| Voice call | Có thể hỗ trợ một số nhóm người dùng | Caller ID spoofing, voicemail, chi phí và khả năng bị làm phiền | Chỉ dùng khi có lý do/accessibility và kiểm soát phù hợp |

### 6.1. Chỉ gửi tới contact đã xác minh

Thông báo bảo mật cần gửi tới địa chỉ/kênh đã được xác minh và có liên hệ với tài khoản trước sự kiện. Nếu người dùng vừa đổi email recovery, không nên lập tức coi địa chỉ mới là kênh đáng tin duy nhất để báo việc thay đổi. Có thể gửi cảnh báo tới kênh cũ trong khoảng thời gian phù hợp, theo policy và quyền riêng tư.

Khi contact bị bounce, số điện thoại đổi chủ hoặc push token hết hiệu lực, hệ thống cần cập nhật trạng thái contact. Không suy ra rằng người dùng đã nhận được thông báo chỉ vì provider trả accepted.

### 6.2. Phân biệt thông báo bảo mật thiết yếu và tùy chọn

Người dùng có thể tùy chỉnh một số thông báo thường lệ, nhưng không nên có tùy chọn tắt mọi cảnh báo quan trọng như thay đổi mật khẩu, thêm/xóa passkey, thay đổi recovery method hoặc sự kiện compromise đã xác nhận nếu chính sách yêu cầu gửi. Cần phân loại notification:

- **Security-critical:** thay đổi credential, revoke, recovery, sự cố xác nhận.
- **Risk alert:** đăng nhập mới/bất thường, nhiều lần thất bại theo ngưỡng.
- **Informational:** phiên thông thường, thiết bị mới đã được xác nhận.
- **Marketing/product:** thông tin sản phẩm, không trộn với security channel.

Tùy chọn người dùng phải được áp dụng theo loại thông báo và yêu cầu pháp lý, không được làm mất audit event.

## 7. Nội dung thông báo an toàn

Thông báo cần trả lời những câu hỏi cơ bản:

- Điều gì đã xảy ra?
- Xảy ra khi nào?
- Tài khoản hoặc phiên nào liên quan?
- Thiết bị/kênh nào đã được quan sát ở mức đủ hữu ích?
- Người dùng nên làm gì nếu không nhận ra sự kiện?

Ví dụ nội dung:

~~~text
Chủ đề: Có đăng nhập mới vào tài khoản của bạn

Tài khoản của bạn vừa đăng nhập thành công.
Thời gian: 22:00, 22/11/2026 (UTC+7)
Thiết bị: Chrome trên Windows
Khu vực mạng ước lượng: Việt Nam
Phương thức: Passkey

Nếu bạn thực hiện đăng nhập này, không cần làm gì thêm.
Nếu bạn không nhận ra hoạt động trên, hãy mở ứng dụng chính thức,
xem các phiên đang hoạt động và thu hồi phiên lạ. Nếu nghi ngờ
credential bị lộ, hãy làm theo hướng dẫn bảo vệ tài khoản.

Chúng tôi không bao giờ yêu cầu bạn gửi mật khẩu, OTP hoặc recovery code
qua email, SMS hay điện thoại.
~~~

Đây là ví dụ minh họa. Múi giờ cần được trình bày rõ; vị trí mạng chỉ nên ghi ở độ chính xác phù hợp với nguồn. Nếu IP geolocation chỉ cho biết quốc gia, không hiển thị thành phố hoặc tọa độ chính xác giả tạo.

### 7.1. Không đưa bí mật vào thông báo

Không bao giờ đưa các dữ liệu sau vào email, SMS, push hoặc notification title/body:

- Mật khẩu hiện tại/mới, OTP, recovery code hoặc câu trả lời bảo mật.
- Access token, refresh token, authorization code, cookie hoặc session ID có thể sử dụng.
- Private key, secret, seed hoặc QR enrollment secret.
- Toàn bộ số định danh, dữ liệu tài chính hoặc hồ sơ nhạy cảm nếu không cần.
- Tọa độ GPS chính xác hoặc lịch sử vị trí dài hạn.

Có thể dùng device label đã được giảm định danh và khu vực ước lượng. Với push trên lock screen, chỉ nên hiển thị nội dung ngắn như “Có hoạt động bảo mật mới; mở ứng dụng để xem”, vì người khác có thể nhìn thấy màn hình khóa.

### 7.2. Nội dung không được tạo cảm giác khẩn cấp giả

Tránh câu chữ như “Tài khoản sẽ bị xóa trong 5 phút, bấm ngay” hoặc đe dọa người dùng phải cung cấp OTP để giữ tài khoản. Cảnh báo nên rõ, bình tĩnh và hướng người dùng tới ứng dụng/trang chính thức. Không dùng nút hoặc liên kết gây áp lực, rút gọn URL hoặc domain không minh bạch.

## 8. Chống phishing và giả mạo thông báo

Login notification có thể bị attacker bắt chước để dụ người dùng nhập password, OTP hoặc recovery code. Một thông báo thật cũng có thể trở thành công cụ phishing nếu chứa liên kết không an toàn.

### Nguyên tắc thiết kế

- Dùng tên miền gửi và sender identity nhất quán; cấu hình SPF, DKIM và DMARC cho email theo hạ tầng thực tế.
- Không yêu cầu người dùng trả lời email/SMS bằng password, OTP hoặc recovery code.
- Hạn chế liên kết trong thông báo; hướng người dùng tự mở ứng dụng hoặc gõ domain chính thức.
- Nếu có link, chỉ dùng HTTPS trên domain chính thức, URL ngắn gọn, không redirect mở và không có tham số nhạy cảm.
- Không dùng link tracking bên thứ ba có thể làm lộ token/session hoặc dữ liệu cá nhân.
- Không đính kèm file thực thi hoặc yêu cầu cài ứng dụng để “bảo vệ tài khoản”.
- Duy trì trang hướng dẫn chính thức về cách nhận biết thông báo thật.
- Cảnh báo trong app nên dùng session đã xác thực và hiển thị nguồn sự kiện.

SPF/DKIM/DMARC giúp kiểm soát một số dạng giả mạo email domain nhưng không bảo đảm người dùng luôn nhận diện đúng email thật. Tài khoản email bị chiếm hoặc domain lookalike vẫn có thể được dùng trong phishing. Cần kết hợp nội dung an toàn và thói quen người dùng.

### 8.1. Không dùng link đăng nhập một chạm thiếu ràng buộc

Không đưa một URL có bearer token vào email rồi cho phép người mở link đăng nhập hoặc thu hồi toàn bộ phiên ngay lập tức. Email có thể được chuyển tiếp, scan bởi security gateway hoặc mở trên thiết bị khác. Nếu cần action link, token phải có mục đích hẹp, thời hạn ngắn, một lần, gắn đúng transaction và vẫn yêu cầu xác thực phù hợp trước hành động nhạy cảm.

### 8.2. “Không phải tôi” phải dẫn tới luồng đáng tin

Nút “Không phải tôi” nên đưa người dùng tới ứng dụng chính thức hoặc một luồng incident response được thiết kế riêng. Không nên thực hiện reset password, disable MFA hoặc xóa mọi phiên chỉ vì bất kỳ ai mở được link trong email. Với thao tác ảnh hưởng tài khoản, yêu cầu xác thực lại bằng credential tin cậy hoặc recovery có bảo đảm tương xứng.

## 9. Notification fatigue và lạm dụng

Nếu hệ thống gửi thông báo cho mọi lần nhập sai mật khẩu hoặc mọi request, attacker có thể dùng chức năng đó để spam, quấy rối hoặc làm người dùng bỏ qua cảnh báo quan trọng.

### Các kiểu lạm dụng

- **Notification flooding:** tạo nhiều login failure để gửi hàng trăm email/push.
- **SMS bombing:** lặp yêu cầu OTP hoặc cảnh báo SMS làm tăng chi phí và gây phiền.
- **Alert fatigue:** gửi quá nhiều cảnh báo ít giá trị khiến người dùng không chú ý sự cố thật.
- **Targeted harassment:** cố tình tạo đăng nhập/khôi phục liên tục để làm phiền một người.
- **Enumeration:** quan sát sự khác nhau của notification hoặc thời gian gửi để suy ra tài khoản có tồn tại.
- **Channel exhaustion:** làm đầy inbox, quota provider hoặc hàng đợi delivery.
- **Fake approval fatigue:** liên tục gửi login approval prompt để người dùng vô tình chấp thuận.

### 9.1. Rate limit và aggregation

- Gộp các lần thất bại tương tự trong một cửa sổ thời gian.
- Giới hạn tần suất theo account, contact, device, IP/ASN và loại event.
- Áp dụng cooldown cho notification ít nghiêm trọng; không trì hoãn cảnh báo compromise đã xác nhận ngoài SLA.
- Deduplicate theo event/incident và không gửi lại vô hạn khi provider lỗi.
- Có quota và circuit breaker theo nhà cung cấp.
- Giữ audit event riêng ngay cả khi notification bị gộp hoặc suppression.
- Phát hiện push approval fatigue; không coi số lần bấm “approve” là bằng chứng hợp lệ nếu transaction không được ràng buộc.

### 9.2. Không để rate limit làm mất cảnh báo quan trọng

Rate limit cần phân biệt loại sự kiện. Một đợt password guessing có thể được gộp thành một cảnh báo tổng hợp; một sự kiện passkey mới được thêm hoặc refresh token reuse đã xác nhận cần được ưu tiên. Nếu channel bị flood, có thể chuyển sang in-app inbox hoặc kênh khác, nhưng phải bảo toàn khả năng người dùng nhận biết sự cố.

## 10. Xử lý khi người dùng không nhận ra đăng nhập

Thông báo có ích khi nó đưa tới hành động an toàn, theo thứ tự phù hợp:

1. Người dùng mở ứng dụng hoặc website chính thức từ bookmark/app đã cài, không dựa vào URL lạ trong thông báo.
2. Xem chi tiết sự kiện và danh sách session/device đang hoạt động.
3. Nếu phiên lạ còn active, thu hồi phiên đó; nếu có dấu hiệu compromise rộng, thu hồi tất cả phiên theo lựa chọn/policy.
4. Đổi password nếu password có thể bị lộ; không chỉ đổi mật khẩu nếu attacker đã có passkey/token khác.
5. Kiểm tra và thu hồi passkey, security key, certificate, API key hoặc recovery method lạ.
6. Thu hồi refresh token/token family và xử lý access token đã cấp theo cơ chế revoke/TTL.
7. Kiểm tra thay đổi tài khoản, email/phone recovery, MFA, thiết bị tin cậy và hoạt động nghiệp vụ gần đây.
8. Liên hệ hỗ trợ qua kênh chính thức nếu mất quyền kiểm soát hoặc không thể hoàn tất recovery.

### 10.1. Không chỉ đổi mật khẩu

Nếu attacker đã thêm passkey hoặc lấy refresh token, đổi password có thể không kết thúc quyền truy cập. Quy trình response phải xem xét mọi authenticator, session, token và recovery channel liên quan. Tài khoản có thể cần tạm dừng thao tác nhạy cảm trong khi điều tra.

### 10.2. Không xác thực bằng chính kênh có thể đã bị chiếm

Nếu thông báo được gửi tới email đang bị nghi compromise, không dùng chính email đó làm bằng chứng duy nhất để reset password hoặc xác nhận “không phải tôi”. Cần phương thức độc lập đã đăng ký, passkey/security key còn tin cậy hoặc recovery flow có proofing phù hợp.

## 11. Liên kết với session, token và authentication context

Login notification cần liên kết được với session event nhưng không tiết lộ credential.

### Session

- Thông báo nên phản ánh session đã được tạo hoặc trạng thái đã commit.
- Device label và thời điểm có thể giúp người dùng nhận ra phiên.
- Session reference trong event phải là ID nội bộ không thể dùng để truy cập.
- Hành động revoke cần thực hiện tại server, có authorization và audit.
- Nếu session đã hết hạn hoặc bị revoke trước khi người dùng bấm xem, giao diện phải hiển thị trạng thái hiện tại.

### Access token và refresh token

- Không đưa token vào notification hoặc link.
- Refresh token reuse có thể là tín hiệu compromise cần alert và revoke token family theo policy.
- Access token JWT tự xác minh có thể còn hiệu lực đến exp nếu API không kiểm tra revoke state; thông báo không thay thế cơ chế thu hồi.
- Với sender-constrained token (DPoP/mTLS), vẫn cần bảo vệ khóa và xác minh proof/certificate.

### Authentication context

Thông báo có thể tóm tắt phương thức như “Passkey” hoặc “Password + MFA” nếu dữ liệu xác thực đáng tin cậy. Không tự suy ra mức AAL/ACR từ địa chỉ IP hoặc thiết bị quen thuộc. Nếu có risk signal, hiển thị ở mức khái quát và tránh tiết lộ toàn bộ logic phát hiện cho attacker.

## 12. Quyền riêng tư và khả năng tiếp cận

Thông báo đăng nhập có thể để lộ thói quen, thiết bị, vị trí hoặc hoạt động tài khoản cho người đang xem email, lock screen hoặc thiết bị dùng chung. Cần áp dụng data minimization:

- Chỉ hiển thị dữ liệu cần để người dùng nhận biết sự kiện.
- Ưu tiên quốc gia/khu vực ước lượng thay cho địa chỉ IP đầy đủ hoặc GPS.
- Dùng device label khái quát; tránh hiển thị serial number hoặc định danh thiết bị nhạy cảm.
- Không đưa dữ liệu y tế, tài chính hoặc nội dung nghiệp vụ vào push lock screen.
- Giới hạn retention của notification history và delivery metadata.
- Phân quyền truy cập in-app security inbox và audit việc xem/xuất dữ liệu.
- Tách thông báo bảo mật khỏi marketing và không dùng event bảo mật cho quảng cáo.

### Accessibility và localization

- Nội dung ngắn, rõ, không chỉ dựa vào màu sắc hoặc biểu tượng.
- Hỗ trợ screen reader, text scaling và ngôn ngữ phù hợp.
- Hiển thị thời gian kèm múi giờ hoặc cho phép đổi sang múi giờ địa phương.
- Có phương thức thay thế nếu người dùng không nhận push/SMS.
- Không dùng câu chữ đổ lỗi hoặc gây hoảng sợ khi hệ thống chưa xác nhận compromise.

## 13. Vòng đời notification và trạng thái delivery

Một event có thể đi qua các trạng thái:

~~~text
CREATED -> POLICY_EVALUATED -> QUEUED -> SENT -> PROVIDER_ACCEPTED
                                      \-> FAILED_RETRYABLE
                                      \-> FAILED_PERMANENT

PROVIDER_ACCEPTED != DELIVERED != READ != ACKNOWLEDGED
~~~

Ý nghĩa:

- **CREATED:** authentication service phát event hợp lệ.
- **POLICY_EVALUATED:** xác định có gửi, gửi kênh nào, có gộp hay trì hoãn không.
- **QUEUED:** delivery job được tạo.
- **SENT:** worker đã gửi request tới provider.
- **PROVIDER_ACCEPTED:** provider chấp nhận request; chưa chắc thiết bị nhận.
- **DELIVERED:** provider báo đã giao nếu kênh hỗ trợ receipt.
- **READ:** có tín hiệu người dùng mở/xem, không phải bằng chứng họ hiểu nội dung.
- **ACKNOWLEDGED:** người dùng thực hiện hành động xác nhận qua luồng đã xác thực.
- **FAILED_RETRYABLE/PERMANENT:** lỗi tạm thời hoặc lỗi không thể tự khắc phục.

Không nên dùng trạng thái READ làm bằng chứng rằng người dùng đã xác nhận đăng nhập. Việc bấm nút trong email/push cần transaction riêng và xác minh đúng người/thiết bị.

### Retry và idempotency

- Event ID duy nhất cho một sự kiện nghiệp vụ.
- Notification job có idempotency key theo event, recipient, channel và template/version.
- Retry lỗi tạm thời với exponential backoff và jitter.
- Không retry lỗi permanent như contact invalid hoặc provider từ chối vĩnh viễn.
- Giới hạn số lần thử và có dead-letter queue để điều tra.
- Provider callback phải xác minh chữ ký và chống replay.
- Khi người dùng thay đổi contact, không gửi lại event cũ sang địa chỉ mới nếu điều đó làm lộ dữ liệu.

## 14. Pseudocode: phát thông báo sau khi tạo phiên

Ví dụ khái niệm dùng transactional outbox và notification policy:

~~~ts
async function completeLogin(transaction, verifiedPrincipal) {
  const result = await database.transaction(async (tx) => {
    const session = await tx.createSession({
      principalId: verifiedPrincipal.id,
      authContext: transaction.authContext
    });

    await tx.insertOutboxEvent({
      eventId: secureEventId(),
      type: "LOGIN_SUCCEEDED",
      principalId: verifiedPrincipal.id,
      sessionRef: session.safeReference,
      occurredAt: now(),
      authMethods: transaction.authContext.methods,
      deviceSummary: transaction.safeDeviceSummary
    });

    return session;
  });

  return result;
}

async function processLoginNotification(event) {
  if (!await verifyTrustedEventProducer(event)) return rejectEvent();
  if (await processedEventStore.exists(event.eventId)) return acknowledgeDuplicate();

  const policy = await notificationPolicy.evaluate(event);
  if (!policy.send) {
    await processedEventStore.markHandled(event.eventId, policy.reason);
    return;
  }

  const contacts = await verifiedContactStore.getAllowedChannels(event.principalId);
  const safePayload = buildMinimalSecurityMessage(event, {
    includeApproximateLocation: policy.includeLocation,
    includeDeviceLabel: policy.includeDevice
  });

  await deliveryQueue.enqueueIdempotently({
    eventId: event.eventId,
    recipientRef: event.principalId,
    channels: selectChannels(contacts, policy),
    payload: safePayload
  });
  await processedEventStore.markHandled(event.eventId, "QUEUED");
}
~~~

Đây là pseudocode, không phải API thư viện. Trong triển khai thực tế:

- Chỉ tạo LOGIN_SUCCEEDED sau khi transaction session commit.
- Producer/event channel phải được xác thực; không nhận event success do browser tự khai.
- safeReference không phải session cookie hoặc bearer token.
- buildMinimalSecurityMessage phải loại bỏ secret, PII không cần thiết và dữ liệu vị trí quá chi tiết.
- enqueueIdempotently cần bảo đảm retry không tạo notification trùng ngoài ý muốn.
- Nếu notification service lỗi, không tự thay đổi quyết định authentication đã commit; ghi lỗi và xử lý theo SLA.

## 15. Tình huống thực tế: người dùng nhận cảnh báo đăng nhập lạ

Một người dùng có tài khoản lưu dữ liệu cá nhân. Họ đăng nhập bằng passkey trên laptop quen thuộc. Một giờ sau, họ nhận email báo có đăng nhập thành công từ một thiết bị Android mới. Người dùng không nhận ra thiết bị đó.

### Luồng phản ứng

1. Người dùng tự mở ứng dụng chính thức từ bookmark hoặc app đã cài.
2. In-app security inbox hiển thị sự kiện với thời gian, thiết bị khái quát, khu vực mạng ước lượng và phương thức xác thực.
3. Người dùng mở danh sách phiên; backend kiểm tra trạng thái hiện tại và cho phép revoke phiên lạ.
4. Nếu phiên lạ dùng password/MFA hoặc token bị nghi lộ, hệ thống yêu cầu xác thực lại bằng passkey còn tin cậy.
5. Người dùng kiểm tra passkey, MFA, recovery email/phone và các thay đổi gần đây.
6. Nếu có dấu hiệu compromise, revoke refresh token family và các session liên quan; xử lý access token theo cơ chế revoke/TTL.
7. Hệ thống ghi incident/audit event, gửi xác nhận qua kênh đã xác minh và cung cấp recovery nếu người dùng mất quyền kiểm soát.

### Những điều hệ thống không nên làm

- Không yêu cầu người dùng reply email bằng OTP.
- Không gửi link rút gọn yêu cầu nhập lại password ngay lập tức.
- Không tự động disable mọi credential chỉ vì một IP ở quốc gia mới.
- Không cho phép link “không phải tôi” thu hồi tài khoản chỉ dựa vào việc mở email.
- Không tuyên bố mọi phiên đã bị thu hồi nếu JWT/API chưa có cơ chế kiểm tra trạng thái.

## 16. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Login thành công và session commit | Tạo event success đúng một lần theo event ID |
| Password đúng nhưng MFA chưa hoàn tất | Không gửi thông báo “đăng nhập thành công” |
| Login thất bại lặp lại | Gộp/giới hạn notification theo policy; audit event vẫn được giữ |
| Event do frontend tự gửi | Notification service từ chối vì producer không tin cậy |
| Event bị phát lại | Deduplication/idempotency ngăn gửi lặp không cần thiết |
| Event tới trước khi session commit | Không gửi success; outbox chỉ publish sau commit |
| Email provider lỗi tạm thời | Retry có backoff; không làm login thất bại |
| Contact chưa xác minh hoặc đã bị thu hồi | Không gửi dữ liệu bảo mật tới contact đó |
| Push trên lock screen | Không hiển thị token, OTP, session ID hoặc dữ liệu nhạy cảm |
| Email giả yêu cầu cung cấp OTP | Nội dung sản phẩm không tạo yêu cầu đó; hướng dẫn người dùng chỉ dùng app chính thức |
| Link notification trỏ domain ngoài | Bị loại bỏ hoặc từ chối; không open redirect |
| Người dùng bấm “không phải tôi” từ email | Đưa tới luồng chính thức và yêu cầu xác minh phù hợp trước thao tác nhạy cảm |
| Attacker kích hoạt notification flood | Rate limit/aggregation/cooldown; cảnh báo compromise quan trọng vẫn được ưu tiên |
| Refresh token reuse đã xác nhận | Kích hoạt incident policy, revoke token family/session và thông báo theo kênh tin cậy |
| Người dùng đổi email recovery | Cảnh báo tới kênh cũ đã xác minh theo policy; không tin địa chỉ mới ngay lập tức |
| Provider callback giả mạo | Chữ ký/audience/timestamp/event ID không hợp lệ thì từ chối |
| Provider accepted nhưng thiết bị offline | Không báo “người dùng đã đọc”; trạng thái delivery phản ánh đúng |
| Người dùng tắt thông báo thường lệ | Vẫn giữ audit; security-critical notification tuân theo policy thiết yếu |
| Người dùng đổi múi giờ | Thời điểm event vẫn chuẩn UTC và hiển thị đúng múi giờ đã chọn |
| Một session đã revoke trước khi mở notification | Giao diện hiển thị trạng thái revoked hiện tại, không báo phiên còn active |

### Chỉ số vận hành

Theo dõi tỷ lệ event được publish, delivery success/failure theo channel, độ trễ từ login commit tới provider acceptance, duplicate rate, notification flood, tỷ lệ người dùng nhận diện hoạt động lạ, tỷ lệ false alert, thời gian từ cảnh báo tới revoke và số event bị loại do producer không tin cậy. Không dùng open/read rate làm bằng chứng duy nhất về hiệu quả bảo mật.

## 17. Bài tập tự kiểm tra

Một dịch vụ quản lý tài khoản có web app, mobile app và API. Người dùng đăng nhập bằng password + MFA hoặc passkey. Họ có thể xem danh sách phiên, thêm/xóa passkey và thay đổi email khôi phục. Nhóm sản phẩm muốn gửi email/push khi có đăng nhập mới.

Hãy:

1. Xác định các event cần thông báo và thời điểm phát event chính xác.
2. Thiết kế event schema tối thiểu để tạo notification mà không chứa token/session secret.
3. Chọn kênh cho login mới, credential change, login failure burst và confirmed compromise.
4. Viết nội dung email/push hữu ích nhưng không tiết lộ dữ liệu nhạy cảm hoặc tạo phishing affordance.
5. Thiết kế “không phải tôi” sao cho người nhận không thể thu hồi tài khoản chỉ bằng cách mở một link trong email.
6. Mô tả cách xử lý notification flooding, provider outage, duplicate event và contact bị đổi.
7. Giải thích cách thông báo liên kết với session/token revoke và vì sao thông báo không tự chứng minh người dùng đã đọc.
8. Viết test case cho event giả, callback giả, login chưa hoàn tất MFA và refresh token reuse.

**Gợi ý đánh giá:** lời giải tốt phải phát event sau commit, xác thực producer, dùng outbox/idempotency, chọn contact đã xác minh, redact secret, chống phishing và cung cấp phản ứng server-side. Cần phân biệt notification delivery với authentication/approval và không khẳng định phiên đã bị thu hồi nếu API vẫn chấp nhận token cũ.

---

**Ghi nhớ:** login notification giúp chủ tài khoản nhận biết hoạt động và phản ứng sớm, nhưng nó không phải yếu tố xác thực. Hãy tạo thông báo từ **sự kiện đăng nhập đã xác minh và commit**, gửi qua kênh đã xác minh, chỉ tiết lộ dữ liệu tối thiểu, chống giả mạo/flooding và hướng người dùng tới luồng bảo mật chính thức. Khi người dùng không nhận ra đăng nhập, xử lý ở server bằng kiểm tra phiên, thu hồi token/credential liên quan và recovery có bảo đảm; không dựa vào một cú bấm trong email để xác nhận danh tính.
