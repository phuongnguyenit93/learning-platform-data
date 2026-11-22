# Thiết kế đăng xuất, làm mới và thu hồi theo kịch bản rủi ro

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Thực hành tổng hợp  
> **Loại bài:** Hands-on exercise — phân tích tình huống, thiết kế luồng, mô hình trạng thái, API contract và kế hoạch kiểm thử.  
> **Phạm vi:** JWT/OAuth và quản lý vòng đời phiên ở mức giao thức, kiến trúc và vận hành; không phụ thuộc Java, Spring hay framework cụ thể.

## 1. Mục tiêu bài thực hành

Bạn được giao thiết kế cơ chế **đăng xuất, làm mới token và thu hồi quyền truy cập** cho một dịch vụ SaaS có người dùng đăng nhập từ nhiều thiết bị. Hệ thống dùng access token JWT để gọi API và refresh token để duy trì phiên. Một số API xác minh JWT offline, một số luồng nhạy cảm cần kiểm tra trạng thái phiên tập trung.

Thiết kế phải trả lời được các câu hỏi:

- Khi người dùng logout trên một thiết bị, thiết bị khác có tiếp tục hoạt động không?
- Khi người dùng chọn logout mọi nơi, làm sao chặn cả refresh token và access token đang còn hạn?
- Khi refresh token bị phát lại sau rotation, hệ thống nhận diện và xử lý thế nào?
- Khi có dấu hiệu tài khoản bị chiếm, mức thu hồi cần mạnh đến đâu?
- Khi tài khoản bị khóa, mật khẩu đổi hoặc quyền quản trị thay đổi, các phiên đang hoạt động bị ảnh hưởng ra sao?
- Khi cache hoặc dịch vụ trạng thái bị lỗi, hệ thống có vô tình tiếp tục chấp nhận credential đã thu hồi không?

Sau bài này, người học phải tạo được một thiết kế có thể review, triển khai và kiểm thử. Chỉ mô tả “xóa token ở client” hoặc “đợi JWT hết hạn” là chưa đủ.

## 2. Bối cảnh hệ thống

### 2.1. Sản phẩm giả định

Một nền tảng SaaS quản lý đơn hàng có:

- Ứng dụng web cho nhân viên vận hành.
- Ứng dụng mobile cho người quản lý.
- API cho tích hợp service-to-service.
- Authorization Server phát hành access token và refresh token.
- Nhiều Resource Server xử lý đơn hàng, khách hàng và thanh toán.
- API Gateway nằm trước các Resource Server.
- Người dùng có thể đăng nhập đồng thời trên nhiều thiết bị.

Access token là JWT ký bất đối xứng. Resource Server xác minh chữ ký, issuer, audience, thời hạn và scope. Một số endpoint nhạy cảm tra cứu session/grant status tập trung. Refresh token là credential ngẫu nhiên có entropy cao và được quản lý trạng thái ở phía server.

Đây là lựa chọn kiến trúc cho bài tập, không phải yêu cầu mọi hệ thống phải dùng refresh token opaque. Nếu dùng JWT refresh token, vẫn cần trạng thái phía server hoặc cơ chế tương đương để rotation, reuse detection và thu hồi có hiệu lực.

### 2.2. Các giả định ban đầu

| Thành phần | Giả định |
|---|---|
| Access token | JWT, thời hạn ngắn, có iss, aud, sub, exp, iat, jti và sid/session reference |
| Refresh token | Opaque random token, chỉ dùng tại Authorization Server |
| Session | Một phiên đăng nhập gắn với một thiết bị/app installation |
| Refresh rotation | Mỗi lần refresh thành công phát hành refresh token mới và vô hiệu hóa token cũ |
| Resource Server | Có thể xác minh JWT offline; endpoint rủi ro cao tra cứu trạng thái online |
| Client | Web, mobile và service integration có đặc tính lưu trữ khác nhau |
| Đồng bộ trạng thái | Có event để phát tán revoke/session changes tới gateway và Resource Server |
| Thời gian | Đồng hồ được đồng bộ; leeway nhỏ và thống nhất theo token profile |

### 2.3. Ranh giới tin cậy

Authorization Server là nơi quyết định phát hành, làm mới và thu hồi grant/session. Resource Server chỉ chấp nhận token theo contract đã cấu hình. Client không được tự khai báo rằng phiên đã logout hoặc token đã bị thu hồi.

Gateway có thể thực hiện kiểm tra sớm, nhưng không được trở thành nguồn tin duy nhất nếu backend có thể bị gọi trực tiếp. Các thành phần cần cùng hiểu session ID, token profile, revocation semantics và thời gian hiệu lực của cache.

## 3. Kịch bản rủi ro

Hãy thiết kế một chính sách áp dụng cho ít nhất năm tình huống dưới đây.

### Kịch bản A — Logout một thiết bị

Người dùng đăng nhập trên laptop và điện thoại. Người dùng logout trên laptop vì chuẩn bị bàn giao máy. Điện thoại cần tiếp tục hoạt động.

Yêu cầu:

- Vô hiệu hóa session và refresh token family của laptop.
- Xóa cookie/session state ở laptop.
- Không thu hồi session điện thoại nếu không có dấu hiệu compromise rộng hơn.
- Xác định cách xử lý access token JWT của laptop vẫn còn hạn.

### Kịch bản B — Logout mọi thiết bị

Người dùng chọn “Đăng xuất khỏi tất cả thiết bị” sau khi sử dụng máy tính công cộng.

Yêu cầu:

- Thu hồi tất cả session và refresh token family đang hoạt động của subject.
- Chặn access token hiện hành theo mức bảo đảm đã chọn.
- Gửi sự kiện revoke tới mọi region/resource server liên quan.
- Hiển thị danh sách session đã kết thúc và thời điểm thực hiện.

### Kịch bản C — Phát hiện refresh token reuse

Một refresh token đã được rotation và đánh dấu consumed lại xuất hiện trong một request mới. Có khả năng token đã bị sao chép.

Yêu cầu:

- Phân biệt retry hợp lệ do timeout với reuse đáng ngờ.
- Không tạo hai nhánh refresh token family hoạt động từ cùng một parent token.
- Có quyết định thu hồi family hoặc session theo risk policy.
- Ghi audit event không chứa raw refresh token.

### Kịch bản D — Đăng nhập từ vị trí/thiết bị bất thường

Risk engine phát hiện một phiên mới có tín hiệu bất thường: thiết bị lạ, hành vi truy cập khác thường hoặc nhiều lần xác thực thất bại.

Yêu cầu:

- Có thể yêu cầu step-up authentication.
- Giới hạn hoặc tạm dừng refresh.
- Chặn hành động nhạy cảm cho đến khi xác minh thêm.
- Tránh tự động khóa toàn bộ tài khoản chỉ dựa vào một tín hiệu yếu như IP thay đổi.

### Kịch bản E — Tài khoản bị chiếm hoặc nhân viên nghỉ việc

Tổ chức xác nhận credential bị lộ hoặc quản trị viên vô hiệu hóa tài khoản nhân viên.

Yêu cầu:

- Thu hồi mọi session, refresh token family và grant liên quan.
- Chặn access token còn hạn trên toàn bộ Resource Server theo SLA khẩn cấp.
- Ngăn cấp token mới cho subject/client bị khóa.
- Xác minh trạng thái revoke đã lan tới mọi region.
- Có audit trail và khả năng điều tra các hành động trước thời điểm thu hồi.

### Kịch bản F — Mật khẩu/MFA/quyền thay đổi

Người dùng đổi mật khẩu, reset MFA hoặc được gỡ quyền quản trị.

Yêu cầu:

- Xác định sự kiện nào cần logout phiên hiện tại, phiên khác hoặc tất cả phiên.
- Thu hồi token có quyền cũ khi thay đổi privilege.
- Không giữ quyền quản trị trong access token cũ quá lâu nếu policy yêu cầu thu hồi nhanh.

## 4. Phân loại rủi ro và chính sách phản ứng

Thiết kế bảng policy trước khi viết API. Mức độ có thể điều chỉnh theo tổ chức, nhưng phải có trigger và hành động rõ ràng.

| Mức | Tình huống điển hình | Hành động phiên/token | Hành động người dùng |
|---|---|---|---|
| R0 — Bình thường | Logout chủ động một thiết bị | Revoke session và refresh family của thiết bị đó; xử lý access token theo contract | Thông báo logout thành công |
| R1 — Bất thường nhẹ | Thiết bị mới hoặc IP thay đổi nhưng chưa có bằng chứng compromise | Step-up khi cần; giảm lifetime; giới hạn thao tác nhạy cảm | Yêu cầu xác minh bổ sung |
| R2 — Nghi ngờ compromise | Refresh reuse, malware signal, hành vi truy cập bất thường mạnh | Revoke refresh family liên quan; có thể revoke session hoặc toàn bộ phiên tùy phạm vi; chặn access token theo SLA | Buộc xác thực lại, thông báo bảo mật |
| R3 — Compromise xác nhận | Tài khoản bị chiếm, thiết bị mất có credential, nhân viên bị vô hiệu hóa | Revoke mọi session/grant/family; block access token; ngăn cấp mới | Khóa hoặc recovery tài khoản theo quy trình |

### 4.1. Không đồng nhất tín hiệu rủi ro

- IP thay đổi đơn lẻ không đủ kết luận tài khoản bị chiếm.
- Refresh token reuse là tín hiệu mạnh hơn, nhưng cần xét race condition và retry hợp lệ.
- Thiết bị bị mất cùng với thông báo của người dùng có thể yêu cầu revoke thiết bị cụ thể ngay.
- Tài khoản bị vô hiệu hóa bởi quản trị viên là quyết định chính sách; phải chặn cấp token mới và thu hồi phiên hiện hành.
- Thay đổi role/privilege có thể cần thu hồi token mang quyền cũ dù không có dấu hiệu credential theft.

### 4.2. Đặt SLA cho thu hồi

Định nghĩa rõ:

- Logout một thiết bị: phiên đó không thể refresh ngay sau khi thao tác được xác nhận.
- Logout mọi thiết bị: mọi refresh family bị revoke và access token bị chặn trong SLA đã công bố.
- R2/R3: có thời gian lan truyền tối đa ngắn hơn R0/R1.
- Nếu trạng thái tập trung không khả dụng, endpoint nhạy cảm áp dụng fail-closed theo policy.

Không dùng từ “ngay lập tức” nếu kiến trúc chỉ có JWT offline và không có trạng thái trung tâm. Khi đó token có thể còn được chấp nhận tới exp cộng leeway.

## 5. Thiết kế mô hình dữ liệu

Bạn cần mô hình hóa ít nhất ba thực thể: Session, Refresh Token Family và Token Revocation/Status.

### 5.1. Session

Ví dụ trường dữ liệu:

| Trường | Ý nghĩa |
|---|---|
| session_id | Định danh phiên duy nhất, không phải secret |
| subject_id | Người dùng/chủ thể của phiên |
| client_id | Ứng dụng hoặc OAuth client |
| device_ref | Tham chiếu thiết bị đã pseudonymize nếu cần |
| status | active, revoked, expired, locked |
| created_at | Thời điểm tạo |
| last_seen_at | Hoạt động gần nhất |
| absolute_expires_at | Hết hạn tuyệt đối |
| idle_expires_at | Hết hạn do không hoạt động |
| risk_level | Mức rủi ro hiện tại |
| revoked_at | Thời điểm thu hồi |
| revoke_reason | Mã lý do, không chứa bí mật |
| version | Phiên bản trạng thái để đồng bộ/cache invalidation |

Không lưu raw access token hoặc refresh token trong bản ghi session.

### 5.2. Refresh Token Family

Một family đại diện chuỗi token được rotation từ cùng một lần cấp grant/session.

| Trường | Ý nghĩa |
|---|---|
| family_id | Định danh chuỗi refresh |
| session_id | Session sở hữu family |
| subject_id/client_id | Chủ thể và client |
| status | active, revoked, compromised, expired |
| created_at | Thời điểm cấp family |
| absolute_expires_at | Hạn tuyệt đối |
| last_rotated_at | Lần rotation gần nhất |
| reuse_detected_at | Thời điểm phát hiện reuse |
| version | Phiên bản cập nhật |

### 5.3. Refresh Token Record

| Trường | Ý nghĩa |
|---|---|
| token_id | Định danh nội bộ |
| token_hash | Hash/HMAC của token, không lưu raw token |
| family_id | Family chứa token |
| parent_token_id | Token trước trong chuỗi |
| status | active, consumed, revoked, expired |
| issued_at | Thời điểm cấp |
| expires_at | Hết hạn |
| consumed_at | Thời điểm sử dụng thành công |
| replaced_by | Token successor |
| request_id | Tương quan refresh request đã được xác minh |

Refresh token cần có entropy mật mã cao. Có thể lưu keyed HMAC hoặc hash phù hợp để tra cứu mà không lưu raw token. Nếu dùng HMAC, khóa dùng cho token lookup phải tách biệt với issuer signing key, encryption key và logging key; có quy trình rotate.

### 5.4. Access Token Status

Access token JWT có thể được xác minh offline. Để revoke trước exp, thiết kế cần ít nhất một trong các cách:

- Denylist theo issuer + jti, với record sống tới exp + leeway.
- Session lookup qua sid/session_id.
- Session version hoặc subject credential version.
- Introspection/central status lookup.
- Sender/key identity block trong tình huống key hoặc client bị compromise.

Không có cách nào tự động thu hồi JWT offline chỉ bằng cách xóa token ở client. Chọn cơ chế dựa trên SLA, tải và mức rủi ro.

## 6. Vòng đời session và token

### 6.1. State machine của session

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Đăng nhập thành công
    ACTIVE --> STEP_UP_REQUIRED: Risk tăng
    STEP_UP_REQUIRED --> ACTIVE: Xác minh bổ sung đạt
    STEP_UP_REQUIRED --> LOCKED: Xác minh thất bại/quá hạn
    ACTIVE --> REVOKED: Logout/revoke
    ACTIVE --> EXPIRED: Idle/absolute expiry
    LOCKED --> REVOKED: Chính sách thu hồi
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Trạng thái revoked và expired là trạng thái kết thúc của session. Nếu người dùng đăng nhập lại, tạo session mới; không “hồi sinh” session đã thu hồi.

### 6.2. State machine của refresh token

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Issue
    ACTIVE --> CONSUMED: Refresh thành công
    CONSUMED --> REPLACED: Successor đã được cấp
    ACTIVE --> REVOKED: Logout/revoke
    CONSUMED --> COMPROMISED: Reuse đáng ngờ
    REPLACED --> COMPROMISED: Ancestor bị phát lại
    COMPROMISED --> REVOKED: Revoke family
    ACTIVE --> EXPIRED: Hết hạn
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Mỗi refresh token chỉ có một lần chuyển từ active sang consumed thành công. Việc tạo successor và cập nhật parent phải nằm trong một transaction hoặc thao tác nguyên tử tương đương.

## 7. Thiết kế luồng đăng nhập và cấp token

Khi xác thực thành công:

1. Xác định subject, client và authentication context.
2. Đánh giá risk trước khi tạo session.
3. Tạo session mới với absolute/idle expiry.
4. Tạo refresh token family gắn với session.
5. Sinh refresh token ngẫu nhiên đủ entropy; chỉ lưu hash/HMAC.
6. Phát access token JWT với audience và scope tối thiểu.
7. Đưa session reference vào access token nếu Resource Server cần tra cứu trạng thái.
8. Ghi audit event chỉ chứa định danh và metadata cần thiết.

Ví dụ payload access token:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-482",
  "aud": "orders-api",
  "iat": 1794800000,
  "exp": 1794800600,
  "jti": "access-7f1c",
  "sid": "session-a82d",
  "scope": "orders:read orders:update"
}
~~~

Đây là payload minh họa. sid là private claim theo contract của hệ thống; nó không phải registered claim bắt buộc của JWT. Không đưa dữ liệu nhạy cảm hoặc quyền vượt nhu cầu vào payload.

## 8. Thiết kế refresh rotation và reuse detection

### 8.1. Luồng refresh bình thường

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant DB as Session/Token Store
    C->>AS: Refresh token RT-1
    AS->>DB: Tìm hash, kiểm tra family/session/status
    DB-->>AS: RT-1 active
    AS->>DB: Consume RT-1 + tạo RT-2 atomically
    DB-->>AS: Commit
    AS-->>C: Access token mới + RT-2
    C->>C: Thay RT-1 bằng RT-2 an toàn
~~~

Trình tự bắt buộc:

1. Xác minh client/grant và token format.
2. Tìm token record bằng hash/HMAC.
3. Kiểm tra token active, family active, session active và chưa hết hạn.
4. Kiểm tra sender constraint nếu profile yêu cầu.
5. Trong transaction, consume token cũ và tạo successor.
6. Phát access token mới theo quyền hiện hành.
7. Commit trước khi trả credential mới.
8. Client thay token cũ bằng token mới và không giữ bản cũ trong storage/log.

Không phát access token mới nếu transaction rotation thất bại hoặc trạng thái session/family đã bị revoke.

### 8.2. Refresh token reuse

Nếu token đã consumed/replaced xuất hiện lại:

- Đây có thể là attacker dùng bản sao token cũ.
- Cũng có thể là client retry sau timeout hoặc hai request refresh chạy đồng thời.
- Server phải có policy phân biệt và không được tạo nhiều successor độc lập.

Phản ứng mặc định khi reuse được xác nhận là đáng ngờ: đánh dấu family compromised/revoked, revoke session liên quan theo risk policy, chặn refresh tiếp theo và phát security event.

### 8.3. Race condition và retry

Hai request đồng thời có thể cùng gửi một refresh token. Nếu cả hai đọc trạng thái active trước khi cập nhật, cả hai có thể phát successor khác nhau.

Biện pháp:

- Atomic compare-and-swap hoặc transaction có khóa/serialization phù hợp.
- Chỉ một request consume thành công.
- Client thực hiện single-flight refresh để tránh nhiều request đồng thời.
- Dùng request/idempotency identifier được ràng buộc với client/session nếu cần retry an toàn.
- Không tạo nhánh token family mới khi parent đã consumed.

Nếu hỗ trợ retry idempotent, cần định nghĩa rõ request nào được coi là cùng một lần refresh và cách trả lại kết quả mà không mở khả năng attacker dùng token cũ để xin successor mới. Grace window rộng hoặc chấp nhận mọi lần dùng lại token cũ sẽ làm yếu reuse detection.

### 8.4. Xử lý khi response bị mất

Một tình huống khó: server đã commit rotation nhưng response bị mất trên mạng. Client chỉ còn refresh token cũ trong khi server đánh dấu token đó consumed.

Các lựa chọn thiết kế:

- Client gửi retry với cùng request ID và server trả kết quả idempotent đã được ràng buộc, trong một cửa sổ ngắn.
- Client phải xác thực lại nếu không thể chứng minh retry thuộc cùng request.
- Với public client, dùng sender constraint khi phù hợp để giảm khả năng token bị sao chép.

Không lưu raw refresh token mới dưới dạng plaintext chỉ để tiện retry. Nếu cần trả lại cùng credential, phải có thiết kế bảo vệ dữ liệu kết quả và kiểm soát truy cập chặt chẽ.

## 9. Thiết kế logout theo phạm vi

### 9.1. Logout session hiện tại

API khái niệm:

~~~http
POST /sessions/current/logout HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
~~~

Hoặc với BFF/cookie session, endpoint nhận session cookie qua kênh bảo vệ và có CSRF defense phù hợp.

Hành vi:

1. Xác định session hiện tại từ credential đã xác minh.
2. Revoke session.
3. Revoke refresh token family gắn với session.
4. Ghi revoke event vào transactional outbox.
5. Phát sự kiện tới gateway/resource status cache.
6. Xóa cookie/session state ở client.
7. Trả kết quả idempotent; gọi logout lặp lại không làm sống lại session.

Nếu access token chỉ được xác minh offline và không có session lookup/denylist, nó có thể còn hiệu lực tới exp. Contract phải nói rõ điều này hoặc dùng cơ chế chặn trước exp.

### 9.2. Logout mọi session

API khái niệm:

~~~http
POST /sessions/logout-all HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "reason": "user_requested"
}
~~~

Hành vi:

- Xác thực người dùng và yêu cầu step-up nếu rủi ro cao.
- Revoke mọi session active của subject trong phạm vi tenant/client theo contract.
- Revoke mọi refresh token family liên quan.
- Tăng subject/session version nếu dùng version check.
- Phát event invalidation.
- Thu hồi access token theo sid/jti/version/introspection policy.
- Gửi thông báo bảo mật và lưu audit event.

API phải xác định logout-all có bao gồm service token, delegated grant, thiết bị tin cậy và phiên của ứng dụng bên thứ ba hay không. Không được để từ “all” mơ hồ.

### 9.3. Logout một thiết bị khác từ trang quản lý session

Người dùng có thể xem danh sách thiết bị/session và revoke một session khác. Yêu cầu:

- Chỉ cho phép subject hoặc administrator có quyền phù hợp.
- Session ID không phải bằng chứng quyền sở hữu; vẫn phải xác minh principal.
- Hiển thị metadata đủ để nhận diện nhưng tránh fingerprint quá mức.
- Có step-up cho revoke thiết bị quan trọng hoặc tài khoản quản trị.
- Revoke session/family và chặn access token gắn sid đó.

### 9.4. Logout không đồng nghĩa xóa lịch sử

Giữ audit record về session đã kết thúc để điều tra. Xóa credential khỏi client và đánh dấu trạng thái revoke không có nghĩa xóa lịch sử đăng nhập, request hoặc sự kiện bảo mật theo retention policy.

## 10. Thu hồi access token JWT trước exp

### 10.1. Vấn đề JWT offline

Một Resource Server chỉ xác minh chữ ký và claims có thể tiếp tục chấp nhận JWT đã được phát hành cho tới exp + leeway. Authorization Server revoke session không tự thay đổi bytes JWT đã phát hành.

Do đó, phải chọn một trong các mức:

| Mô hình | Cách hoạt động | Độ trễ thu hồi |
|---|---|---|
| Short-lived access token | Không tra cứu status; chờ exp | Tối đa thời gian còn lại + leeway |
| Denylist jti | Tra cứu token ID bị revoke | Phụ thuộc cập nhật/cache |
| Session lookup | Kiểm tra sid/session active | Phụ thuộc cache/consistency |
| Version check | So token version với version hiện tại | Phụ thuộc lookup/cache |
| Introspection | Hỏi Authorization Server/status service | Gần thời gian thực nếu online |
| Hybrid | Verify JWT offline rồi kiểm tra status theo rủi ro | Theo SLA từng endpoint |

### 10.2. Denylist theo jti

Khi revoke một access token:

- Lấy jti từ token đã xác minh hoặc từ record phát hành tin cậy.
- Namespace theo issuer và token profile.
- Ghi revoked-until theo exp + leeway.
- Resource Server từ chối nếu jti nằm trong denylist.
- Xóa record sau khi token không còn được chấp nhận ở bất kỳ verifier nào.

jti chỉ là định danh. Nó không tự thu hồi token nếu verifier không tra cứu trạng thái.

### 10.3. Session reference hoặc version

Access token có thể chứa sid. Resource Server tra cứu session status để xác định phiên còn active hay không.

Một lựa chọn khác là token chứa session_version/credential_version. Khi logout-all hoặc sự kiện compromise xảy ra, server tăng version; token có version cũ bị từ chối.

Trade-off:

- Lookup online tăng độ trễ và phụ thuộc trạng thái.
- Cache giảm tải nhưng tạo cửa sổ stale.
- Version theo subject có thể thu hồi nhiều phiên cùng lúc.
- Version theo session cho phép thu hồi hẹp hơn nhưng cần nhiều record.

### 10.4. Introspection

Opaque access token thường được kiểm tra qua introspection. JWT cũng có thể dùng introspection nếu kiến trúc yêu cầu trạng thái tập trung, dù khi đó một phần lợi ích offline của JWT giảm đi.

Introspection response phải được bảo vệ và cache theo policy. Khi token bị revoke, status service cần phản ánh trạng thái mới và consumer phải giới hạn cache active theo ngân sách thu hồi.

## 11. Event propagation và nhiều region

### 11.1. Transactional outbox

Thay đổi session/family và event revoke phải được ghi nguyên tử hoặc có cơ chế bảo đảm không mất sự kiện:

~~~mermaid
flowchart LR
    A[Logout / Risk event] --> B[Transaction]
    B --> C[Update session and token family]
    B --> D[Write outbox event]
    D --> E[Outbox publisher]
    E --> F[Event bus]
    F --> G[Gateway cache]
    F --> H[Resource Server cache]
    F --> I[Audit / Security monitoring]
~~~

Nếu database commit thành công nhưng publish event thất bại, outbox worker phải phát lại. Consumer phải idempotent để event trùng không làm hỏng trạng thái.

### 11.2. Event schema

Ví dụ:

~~~json
{
  "event_id": "evt-91ac",
  "event_type": "session.revoked",
  "subject_ref": "user-482",
  "session_id": "session-a82d",
  "family_id": "family-42",
  "version": 18,
  "reason_code": "user_logout",
  "occurred_at": 1794800200
}
~~~

Event không chứa raw access token, refresh token hoặc secret. Event cần có event_id, version/sequence, subject/session reference và reason code để consumer xử lý idempotent và đúng thứ tự.

### 11.3. Cache invalidation

Consumer cần:

- Xử lý event trùng.
- Phát hiện version cũ hoặc event đến sai thứ tự.
- Invalidate cache active khi nhận revoke.
- Không để event active cũ ghi đè trạng thái revoked mới hơn.
- Có TTL tối đa cho cache active.
- Có reconciliation định kỳ với nguồn trạng thái chính.

Đối với R2/R3, cần đường truyền revoke ưu tiên và cơ chế xác nhận các region đã nhận event. Nếu một region không xác nhận, phải có phương án chặn traffic hoặc bắt buộc status lookup online.

### 11.4. Fail-open hay fail-closed

Chính sách phải theo mức rủi ro:

- Endpoint đọc dữ liệu ít nhạy cảm có thể chấp nhận một cửa sổ cache rất ngắn nếu threat model cho phép.
- Endpoint thanh toán, thay đổi quyền hoặc quản trị nên fail-closed khi không thể xác minh trạng thái bắt buộc.
- Khi nhận tín hiệu R3, không dùng stale active cache để tiếp tục cấp quyền.
- Nếu Authorization Server không khả dụng, không được tự động phát refresh token mới dựa trên dữ liệu client gửi.

Fail-closed có thể ảnh hưởng availability. Hãy định nghĩa fallback, alert và runbook thay vì âm thầm bỏ qua status check.

## 12. API contract đề xuất

Các endpoint dưới đây là hợp đồng khái niệm. Tên và response cần được điều chỉnh theo OAuth/OIDC profile và API convention của hệ thống.

| Endpoint | Mục đích | Hành vi bảo mật |
|---|---|---|
| POST /oauth/token | Refresh token grant | Rotation, kiểm tra family/session, reuse detection |
| POST /oauth/revoke | Thu hồi token theo RFC 7009 | Xác định token/grant và revoke trạng thái |
| POST /sessions/current/logout | Logout session hiện tại | Revoke session + family |
| POST /sessions/logout-all | Logout mọi session trong phạm vi | Revoke toàn bộ family/session theo contract |
| GET /sessions | Liệt kê session của subject | Chỉ trả metadata an toàn |
| DELETE /sessions/{id} | Revoke một session được chọn | Xác minh quyền sở hữu và revoke |
| GET /sessions/{id}/status | Nội bộ, kiểm tra status | Chỉ service được tin cậy truy cập |

### 12.1. Refresh response

Ví dụ response thành công:

~~~json
{
  "token_type": "Bearer",
  "access_token": "<new-access-token>",
  "expires_in": 600,
  "refresh_token": "<rotated-refresh-token>"
}
~~~

Không log response body. Client phải thay refresh token cũ bằng token mới một cách nguyên tử trong storage phù hợp. Nếu lưu token mới thất bại, client cần xử lý recovery theo contract thay vì tiếp tục dùng token cũ.

### 12.2. Revoke response

RFC 7009 định nghĩa endpoint revocation và yêu cầu phản hồi thành công kể cả khi token được gửi tới không tồn tại hoặc đã bị revoke, nhằm tránh lộ trạng thái token. Hệ thống vẫn cần audit nội bộ với reason code phù hợp, nhưng không trả thông tin nhạy cảm về token.

### 12.3. Idempotency

Logout và revoke nên idempotent:

- Gọi lại cùng yêu cầu không kích hoạt trạng thái active.
- Không tạo session/family mới.
- Có thể trả cùng trạng thái hoàn tất.
- Audit event có thể ghi nhận retry riêng nhưng không nhân đôi tác động.

Refresh rotation không giống logout idempotent: một refresh token đã consume không được dùng tùy tiện lần nữa. Nếu hỗ trợ retry, phải có request binding và quy tắc replay rõ.

## 13. Kịch bản thực hành theo từng bước

Hãy thực hiện các bước sau trên giấy, sơ đồ hoặc một prototype cô lập. Không dùng token, tài khoản hoặc khóa production.

### Bước 1 — Vẽ inventory credential

Liệt kê:

- Access token của web/mobile/service.
- Refresh token family.
- Session cookie/BFF session nếu có.
- DPoP key hoặc client certificate nếu dùng sender constraint.
- OAuth grant và client credentials.

Với mỗi credential, ghi issuer/owner, nơi lưu, audience, lifetime, khả năng revoke và nơi có thể bị lộ.

### Bước 2 — Chọn phạm vi logout

Thiết kế ba thao tác:

1. Logout current session.
2. Logout selected session/device.
3. Logout all sessions/grants.

Với mỗi thao tác, xác định record nào chuyển trạng thái, event nào được phát và access token còn hạn bị chặn bằng cách nào.

### Bước 3 — Vẽ refresh rotation

Vẽ sequence từ client tới Authorization Server và token store. Chỉ rõ điểm atomic commit, trạng thái parent/successor và hành vi khi:

- Refresh thành công.
- Token hết hạn.
- Session đã revoke.
- Family đã compromised.
- Token cũ bị reuse.
- Response bị mất sau commit.
- Hai request refresh chạy đồng thời.

### Bước 4 — Viết risk policy

Ánh xạ R0–R3 vào:

- Có cho phép refresh không?
- Có yêu cầu step-up không?
- Revoke một session, một family hay mọi session?
- Access token bị chặn trong bao lâu?
- Endpoint nào fail-closed?
- Người dùng nhận thông báo gì?

### Bước 5 — Thiết kế revoke propagation

Chỉ rõ:

- Transaction state update và outbox event.
- Event schema/version.
- Consumer ở mỗi region.
- Cache TTL và invalidation.
- Reconciliation khi mất event.
- Cách xác nhận SLA R2/R3 đã đạt.

### Bước 6 — Viết test matrix

Tạo test cho happy path, boundary, replay, concurrency, partial failure, multi-region và permission change. Mỗi test cần có trạng thái ban đầu, hành động, kết quả mong đợi ở Authorization Server, Resource Server, client và audit.

## 14. Bài tập yêu cầu nộp

Hãy nộp một thiết kế gồm các deliverable sau:

| Deliverable | Nội dung tối thiểu |
|---|---|
| D1 — Architecture | Sơ đồ Client, Authorization Server, token/session store, gateway, Resource Server và event bus |
| D2 — Risk matrix | R0–R3, trigger, revoke scope, step-up, SLA và fail policy |
| D3 — State model | Session, refresh family, refresh token record và trạng thái chuyển tiếp |
| D4 — API contract | Refresh, logout current, logout-all, revoke và session management |
| D5 — Sequence diagrams | Login, refresh rotation, refresh reuse, logout current, logout-all và emergency revoke |
| D6 — Access token strategy | Chọn short-lived, jti denylist, sid lookup, version, introspection hoặc hybrid; giải thích trade-off |
| D7 — Failure handling | DB/event bus/status service/cache outage, race condition và lost response |
| D8 — Test plan | Positive, negative, boundary, concurrency, replay, multi-region và audit tests |
| D9 — Operations | Metrics, alert, audit, runbook, recovery và owner |

### 14.1. Các câu hỏi bắt buộc phải trả lời

1. Logout một thiết bị có làm mất hiệu lực token ở thiết bị khác không? Vì sao?
2. Nếu Resource Server chỉ verify JWT offline, access token sau logout còn dùng được tối đa bao lâu?
3. Khi refresh token cũ bị reuse, điều kiện nào khiến bạn revoke family và điều kiện nào yêu cầu revoke toàn bộ subject?
4. Làm sao phân biệt retry hợp lệ sau timeout với attacker replay?
5. Nếu event revoke bị mất ở một region, làm sao phát hiện và khắc phục?
6. Cache active có thể tồn tại tối đa bao lâu sau revoke?
7. Đổi role từ administrator xuống user có cần revoke access token cũ không?
8. Logout-all có thu hồi delegated grant/service token không?
9. Nếu refresh rotation đã commit nhưng response mất, client recovery ra sao?
10. Bạn chứng minh SLA revoke bằng telemetry và test nào?

## 15. Ma trận kiểm thử chấp nhận

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| H01 | Đăng nhập thiết bị A và B | Tạo hai session riêng, cùng subject |
| H02 | Logout thiết bị A | Session/family A bị revoke; B tiếp tục hoạt động |
| H03 | Refresh bằng family A sau logout | Từ chối |
| H04 | Access token A còn hạn sau logout | Bị chặn theo cơ chế/SLA đã thiết kế; nếu offline-only thì cửa sổ còn lại được công bố rõ |
| H05 | Logout-all | Mọi session/family trong phạm vi bị revoke |
| H06 | Refresh token active được dùng lần đầu | Consume parent, tạo đúng một successor |
| H07 | Refresh token consumed bị dùng lại | Phát hiện reuse và xử lý family theo policy |
| H08 | Hai refresh request đồng thời cùng token | Chỉ một rotation thành công; không có hai successor active |
| H09 | Response refresh mất sau commit | Recovery theo idempotency/re-auth policy; không mở nhánh family |
| H10 | Refresh token đã hết hạn | Từ chối |
| H11 | Session bị revoke nhưng refresh token còn hạn | Từ chối refresh |
| H12 | Family bị revoke nhưng token con còn tồn tại | Từ chối toàn family |
| H13 | Subject bị disable | Không cấp token mới; session hiện hành bị chặn theo SLA |
| H14 | Password đổi | Áp dụng revoke scope theo policy đã công bố |
| H15 | MFA reset | Yêu cầu step-up/revoke theo risk policy |
| H16 | Role quản trị bị gỡ | Token chứa quyền cũ bị chặn hoặc quyền được tra cứu lại theo SLA |
| H17 | Logout endpoint được gọi lặp lại | Idempotent; session không active trở lại |
| H18 | Event revoke được phát hai lần | Consumer xử lý idempotent |
| H19 | Event đến sai thứ tự | Version ngăn trạng thái cũ ghi đè revoked |
| H20 | Outbox publish lỗi sau DB commit | Worker phát lại; không mất revoke event |
| H21 | Một region mất kết nối event bus | Alert/reconciliation hoặc fail-closed đạt SLA |
| H22 | Cache active chưa nhận revoke | TTL/online check giới hạn cửa sổ stale |
| H23 | Status service không khả dụng ở API thanh toán | Fail-closed theo policy |
| H24 | Status service không khả dụng ở endpoint ít rủi ro | Fallback đúng risk policy, không bỏ qua ngoài contract |
| H25 | jti denylist được cập nhật | Token bị từ chối tới exp + leeway |
| H26 | Logout một session trong cùng subject | Session khác không bị revoke ngoài phạm vi |
| H27 | Refresh reuse có sender constraint hợp lệ | Vẫn phát hiện reuse của token đã consumed; sender constraint không thay rotation |
| H28 | IP thay đổi đơn lẻ | Không tự động revoke toàn tài khoản nếu policy không yêu cầu |
| H29 | R3 compromise xác nhận | Revoke toàn bộ session/grant/family và block access token theo SLA |
| H30 | Audit sau revoke | Có subject/session/action/reason/time; không có raw token |

## 16. Tiêu chí đánh giá bài làm

| Hạng mục | Trọng số |
|---|---:|
| Phân loại rủi ro và chọn đúng phạm vi revoke | 20% |
| Refresh rotation, reuse detection và concurrency | 20% |
| Access token revocation và giới hạn JWT offline | 15% |
| Mô hình session/family và API contract | 15% |
| Event propagation, cache và multi-region | 15% |
| Test matrix, audit và incident response | 15% |

### 16.1. Lỗi nghiêm trọng làm bài không đạt

- Chỉ xóa token phía client rồi kết luận đã logout an toàn.
- Cho refresh token đã consumed tạo successor mới mà không có kiểm soát replay.
- Không xử lý race condition khi refresh đồng thời.
- Tuyên bố JWT offline bị revoke ngay mà không có status check hoặc cơ chế chặn tương đương.
- Không giới hạn stale cache sau revoke.
- Không phân biệt logout một thiết bị và logout toàn bộ.
- Log raw access/refresh token trong audit hoặc debug.
- Cho phép event active cũ ghi đè trạng thái revoked mới.

## 17. Mẫu cấu hình policy tham khảo

~~~yaml
session_policy:
  idle_timeout_seconds: 1800
  absolute_lifetime_seconds: 2592000
  revoke_on_password_change: true
  revoke_on_account_disable: true
  revoke_on_privilege_reduction: true

refresh_policy:
  rotation: required
  reuse_detection: required
  family_absolute_lifetime_seconds: 2592000
  concurrent_refresh: atomic_single_successor
  sender_constraint:
    required_for_public_clients: according_to_client_risk

access_token_policy:
  lifetime_seconds: 600
  audience: resource_specific
  revocation:
    default: short_lived_plus_session_status_for_sensitive_routes
    emergency: denylist_or_version_block
  status_cache_max_seconds: 15

risk_policy:
  R0:
    action: revoke_current_session_and_family
  R1:
    action: step_up_and_limit_sensitive_actions
  R2:
    action: revoke_related_family_and_assess_subject_wide_scope
  R3:
    action: revoke_all_sessions_grants_and_block_access

event_policy:
  transactional_outbox: required
  consumers_idempotent: true
  monotonic_version: required
  reconciliation: required
~~~

Đây là cấu hình minh họa cho bài tập, không phải schema chuẩn hay giá trị mặc định áp dụng cho mọi tổ chức. Thời hạn, cache TTL, risk trigger và fail policy phải được chọn từ threat model, SLA và tải thực tế.

## 18. Checklist hoàn thành thiết kế

**Session và logout**

- [ ] Mỗi lần đăng nhập tạo session identity riêng.
- [ ] Logout current chỉ revoke đúng session/family.
- [ ] Logout selected device xác minh quyền sở hữu session.
- [ ] Logout-all định nghĩa rõ phạm vi subject/client/grant.
- [ ] Cookie/session state được xóa an toàn ở client.
- [ ] Access token còn hạn được xử lý theo contract, không dựa vào xóa local token.

**Refresh**

- [ ] Refresh token có entropy cao và không lưu raw value.
- [ ] Rotation atomic, parent chỉ consume một lần.
- [ ] Reuse detection có policy và audit.
- [ ] Xử lý retry/lost response và concurrency.
- [ ] Refresh family bị revoke thì mọi token con đều bị từ chối.
- [ ] Refresh không cấp token mới khi session/subject/grant đã bị revoke.

**Access token và revoke**

- [ ] Chọn rõ jti denylist, sid lookup, version, introspection hoặc hybrid.
- [ ] Công bố revocation window cho JWT offline.
- [ ] Cache TTL không vượt ngân sách thu hồi.
- [ ] R2/R3 có emergency block và xác nhận mọi region.
- [ ] Role/credential/account changes kích hoạt đúng phạm vi revoke.

**Vận hành**

- [ ] State update và event revoke không mất đồng bộ.
- [ ] Consumer idempotent và chống event cũ ghi đè.
- [ ] Có reconciliation, alert và runbook.
- [ ] Audit không ghi raw token.
- [ ] Có test concurrency, retry, outage và multi-region.

**Điều cần nhớ:** Logout, refresh rotation và revocation là ba thao tác liên quan nhưng có semantics khác nhau. Logout kết thúc một hoặc nhiều session; rotation thay refresh credential và phát hiện token cũ bị dùng lại; revocation làm cho credential đã phát hành không còn được chấp nhận. Thiết kế tốt phải xác định phạm vi theo rủi ro, xử lý nguyên tử, truyền trạng thái thu hồi tới mọi verifier và công bố rõ cửa sổ mà JWT offline còn có thể được chấp nhận.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Access token, refresh token và grant.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Token revocation endpoint và semantics.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Kiểm tra trạng thái token tập trung.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Refresh token rotation, reuse detection và sender-constrained token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, exp, iat, jti.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Profile access token JWT.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): Sender-constrained token bằng DPoP.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): Certificate-bound access token.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): Vòng đời session và logout.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): Các thực hành bảo vệ OAuth.
