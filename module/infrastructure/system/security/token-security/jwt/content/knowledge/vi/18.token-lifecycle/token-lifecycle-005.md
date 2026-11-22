# Đăng xuất trên thiết bị và ý nghĩa đối với JWT đã phát hành

Đăng xuất trên một thiết bị thường bao gồm hai việc khác nhau: ứng dụng ngừng sử dụng credential đang giữ và hệ thống phía máy chủ vô hiệu hóa phiên hoặc quyền cấp token tương ứng. Với JWT access token được xác minh offline, xóa token khỏi thiết bị **không tự làm token đã phát hành mất hiệu lực**. Nếu resource server không kiểm tra trạng thái thu hồi, bản sao token vẫn có thể được chấp nhận cho tới khi hết hạn.

Bài học thuộc chương **Vòng đời token** của module **Security – JSON Web Token (JWT)**. Nội dung giải thích đăng xuất cục bộ, đăng xuất một thiết bị, đăng xuất mọi thiết bị, thu hồi refresh/access token và đồng bộ trạng thái giữa các ứng dụng. Phạm vi áp dụng cho browser, ứng dụng native, backend và API trên mọi nền tảng; không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Đăng xuất thực sự có nghĩa là gì?

Trong một hệ thống dùng OAuth/OIDC, một lần đăng nhập có thể tạo ra nhiều loại trạng thái:

- Phiên đăng nhập tại Identity Provider (IdP) hoặc Authorization Server.
- Phiên của ứng dụng client hoặc relying party (RP).
- Access token đang được dùng để gọi resource server.
- Refresh token dùng để xin access token mới.
- Phiên riêng của từng thiết bị hoặc từng lần đăng nhập.
- Cookie, khóa hoặc credential được lưu trên thiết bị.

Nút **Đăng xuất** trên giao diện có thể chỉ xóa trạng thái ở client, hoặc có thể kích hoạt một quy trình thu hồi ở máy chủ. Hai hành vi này không giống nhau.

| Hành động | Phạm vi | Điều xảy ra |
| --- | --- | --- |
| Local logout | Ứng dụng trên thiết bị hiện tại | Xóa token/session cục bộ và chuyển giao diện về trạng thái chưa đăng nhập |
| Device logout | Một phiên đăng nhập trên một thiết bị | Kết thúc phiên thiết bị đó và ngăn refresh token/credential của phiên tiếp tục được dùng |
| Logout from application | Phiên tại một ứng dụng/RP | Ứng dụng kết thúc phiên của chính nó; phiên IdP hoặc ứng dụng khác có thể vẫn tồn tại |
| Identity Provider logout | Phiên SSO tại IdP | Kết thúc phiên đăng nhập tại IdP theo chính sách; các RP có thể cần nhận sự kiện logout |
| Global logout | Tất cả phiên/thiết bị của một tài khoản | Vô hiệu hóa các phiên hoặc grants thuộc tài khoản trên phạm vi hệ thống được chỉ định |
| Token revocation | Một token hoặc nhóm token liên quan | Authorization Server ghi nhận token không còn được sử dụng theo cơ chế thu hồi của hệ thống |

Một hệ thống cần nói rõ nút đăng xuất đang thực hiện hành động nào. Nếu giao diện thông báo “đăng xuất khỏi tất cả thiết bị” nhưng backend chỉ xóa token ở browser hiện tại, thông báo và hành vi bảo mật không khớp nhau.

## 2. Vì sao xóa JWT trên thiết bị không thu hồi JWT đã phát hành?

JWT có chữ ký thường chứa claims như issuer, subject, audience và thời hạn. Resource server có thể xác minh chữ ký bằng khóa công khai và kiểm tra claims mà không cần hỏi Authorization Server ở mỗi request.

Điều này giúp giảm độ trễ và phụ thuộc mạng, nhưng resource server không tự biết client đã xóa token hoặc người dùng vừa nhấn nút logout.

### 2.1. Ví dụ access token vẫn còn hiệu lực

Giả sử:

- 09:00: Authorization Server cấp access JWT có exp lúc 10:00.
- 09:15: Người dùng nhấn Logout trên điện thoại A.
- Ứng dụng xóa access token khỏi bộ nhớ và refresh token khỏi secure storage.
- 09:20: Kẻ tấn công sử dụng bản sao access JWT đã lấy trước đó để gọi API.

Nếu API chỉ xác minh chữ ký, issuer, audience và exp, token vẫn có thể được chấp nhận lúc 09:20. API không biết điện thoại A đã xóa token.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant D as Thiết bị A
    participant API as Resource Server
    participant X as Bên giữ bản sao token
    AS->>D: Cấp access JWT, exp = 10:00
    D->>X: Token bị sao chép trước khi logout
    D->>D: Người dùng nhấn Logout, xóa token cục bộ
    X->>API: Gửi bản sao JWT lúc 09:20
    API->>API: Xác minh chữ ký và exp
    API-->>X: Có thể vẫn chấp nhận
    Note over D,API: Xóa token tại client không thay đổi bản sao ở nơi khác
~~~

Đây là giới hạn quan trọng của access token tự chứa được xác minh offline. Chữ ký chứng minh token không bị sửa sau khi ký; nó không chứng minh token chưa bị thu hồi ở một hệ thống trạng thái khác.

### 2.2. Access token và refresh token có vai trò khác nhau

| Credential | Vai trò | Khi logout |
| --- | --- | --- |
| Access token | Truy cập resource server | Xóa bản cục bộ; cần cơ chế phía server nếu muốn chặn bản sao trước exp |
| Refresh token | Xin access token mới | Thu hồi tại Authorization Server để ngăn cấp token mới từ credential đó |
| Session cookie của ứng dụng | Duy trì phiên với ứng dụng/BFF | Hủy session phía server và xóa cookie ở browser |
| IdP session cookie | Duy trì phiên SSO tại IdP | Kết thúc qua cơ chế logout của IdP |
| Device/session record | Theo dõi một lần đăng nhập trên thiết bị | Đánh dấu revoked/ended và chặn refresh hoặc request theo chính sách |

Thu hồi refresh token không mặc nhiên khiến mọi access JWT đã phát hành biến mất hoặc bị mọi API từ chối ngay lập tức. Nếu API xác minh offline, cần cơ chế bổ sung để nhận biết trạng thái mới.

## 3. Local logout trên một thiết bị

Local logout là hành động phía ứng dụng. Nó cần xóa các credential và trạng thái nhạy cảm mà ứng dụng đang quản lý trên thiết bị.

### 3.1. Những việc client cần thực hiện

1. Ngừng gửi request mới bằng access token hiện tại.
2. Xóa access token khỏi bộ nhớ ứng dụng.
3. Xóa refresh token khỏi secure storage hoặc nơi lưu phù hợp.
4. Xóa thông tin phiên và dữ liệu cache nhạy cảm gắn với tài khoản.
5. Hủy các tác vụ nền có thể tiếp tục sử dụng credential cũ.
6. Đưa UI về trạng thái chưa đăng nhập và yêu cầu xác thực lại trước khi truy cập dữ liệu bảo vệ.
7. Đồng bộ trạng thái logout giữa các tab/window của cùng ứng dụng nếu cần.

Việc xóa token nên được thực hiện ngay cả khi server logout endpoint không truy cập được. Tuy nhiên, ứng dụng phải thể hiện rõ nếu chưa thể xác nhận việc thu hồi phía server.

### 3.2. Giới hạn của local logout

Local logout chỉ kiểm soát bản credential mà ứng dụng trên thiết bị đang giữ. Nó không thể:

- Xóa bản sao token đã được gửi tới thiết bị khác.
- Xóa token đã bị ghi vào log, crash report hoặc backup.
- Làm access JWT hết hạn sớm hơn exp nếu API không kiểm tra trạng thái.
- Kết thúc phiên IdP hoặc phiên của ứng dụng khác.
- Thu hồi refresh token tại Authorization Server nếu client không gửi yêu cầu thu hồi thành công.

Vì vậy, local logout là cần thiết để bảo vệ thiết bị hiện tại nhưng không đủ khi cần xử lý token bị mất, bị đánh cắp hoặc tài khoản bị xâm nhập.

### 3.3. Browser, SPA và BFF

Với SPA lưu access token trong bộ nhớ hoặc browser storage:

- Xóa token khỏi bộ nhớ và các storage do ứng dụng quản lý.
- Xóa dữ liệu cache chứa thông tin nhạy cảm.
- Gửi yêu cầu logout/revocation tới backend nếu kiến trúc hỗ trợ.
- Đồng bộ logout giữa các tab, ví dụ thông qua cơ chế thông báo cùng origin.
- Không coi việc xóa localStorage là thu hồi token phía server.

Với mô hình Backend-for-Frontend (BFF), browser thường giữ cookie session còn access/refresh token được giữ ở backend. Logout nên hủy session phía BFF, xóa cookie phía browser và yêu cầu backend thu hồi hoặc vô hiệu hóa credential upstream theo chính sách.

Cookie có thể được xóa ở browser nhưng session server vẫn còn nếu backend không hủy session. Ngược lại, backend hủy session nhưng browser vẫn giữ cookie cũ; request tiếp theo phải bị từ chối vì session identifier không còn hợp lệ.

### 3.4. Ứng dụng native/mobile

Ứng dụng native nên xóa access token khỏi bộ nhớ và refresh token khỏi vùng lưu trữ an toàn do hệ điều hành cung cấp. Cần xem xét:

- Dữ liệu token có còn trong backup hoặc bản sao ứng dụng không.
- Có tác vụ nền, widget hoặc extension nào vẫn giữ credential không.
- Có nhiều tài khoản hoặc nhiều phiên trong cùng ứng dụng không.
- Logout một tài khoản có vô tình xóa credential của tài khoản khác không.
- Ứng dụng có gửi revocation request trước khi xóa refresh token hay không.

Nếu cần gọi endpoint thu hồi, client có thể giữ credential trong bộ nhớ tạm trong lúc gửi request; sau đó xóa credential kể cả khi request thất bại. Không giữ refresh token lâu hơn chỉ để chờ mạng khôi phục.

## 4. Đăng xuất một thiết bị cần trạng thái phía máy chủ

Muốn logout có hiệu lực với bản sao refresh token hoặc các request cần kiểm tra trạng thái, hệ thống cần nhận diện được phiên đăng nhập tương ứng.

### 4.1. Mô hình một tài khoản, nhiều phiên thiết bị

Một tài khoản có thể có nhiều phiên:

| Session | Thiết bị | Trạng thái |
| --- | --- | --- |
| S-101 | Laptop cá nhân | Active |
| S-102 | Điện thoại A | Active |
| S-103 | Tablet B | Active |

Khi người dùng logout trên điện thoại A, hệ thống chỉ nên kết thúc S-102 nếu mục tiêu là logout thiết bị hiện tại. S-101 và S-103 vẫn hoạt động.

Để làm được điều này, Authorization Server hoặc hệ thống phiên cần có bản ghi server-side gắn credential với từng phiên/grant. Ví dụ:

~~~json
{
  "session_id": "S-102",
  "subject": "user-42",
  "client_id": "mobile-app",
  "device_label": "Phone A",
  "created_at": "2026-11-16T08:00:00Z",
  "last_seen_at": "2026-11-16T09:15:00Z",
  "status": "active"
}
~~~

Đây là dữ liệu phiên minh họa, không phải claim JWT bắt buộc. Device label chỉ giúp người dùng nhận diện; không phải bằng chứng mật mã rằng request đến từ thiết bị đó.

### 4.2. Gắn refresh token với phiên hoặc token family

Nếu một refresh token được chia sẻ cho nhiều thiết bị, server khó thu hồi riêng một thiết bị mà không ảnh hưởng thiết bị còn lại. Thiết kế tốt hơn là mỗi lần đăng nhập/thiết bị có một phiên hoặc refresh-token family riêng:

- Mỗi phiên có định danh server-side.
- Refresh token được gắn với phiên/grant và client phù hợp.
- Rotation refresh token được quản lý trong phạm vi family.
- Logout một phiên đánh dấu phiên/family đó revoked.
- Refresh token của phiên đã revoked không thể cấp access token mới.
- Logout toàn bộ tài khoản có thể thu hồi tất cả phiên/family.

Không chỉ dựa vào một device ID do client gửi lên. Client có thể sửa hoặc giả mạo giá trị này. Hãy dùng session identifier ngẫu nhiên do server cấp, ràng buộc với credential và kiểm tra quyền sở hữu phiên trước khi cho phép logout.

### 4.3. Logout thiết bị đang dùng

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Ứng dụng trên thiết bị A
    participant AS as Authorization Server
    participant DB as Session/Token Store
    U->>C: Chọn Logout thiết bị hiện tại
    C->>AS: Gửi yêu cầu logout/revoke phiên
    AS->>DB: Xác thực chủ phiên và đánh dấu session revoked
    AS->>DB: Thu hồi refresh-token family tương ứng
    DB-->>AS: Cập nhật thành công
    AS-->>C: Xác nhận logout phía server
    C->>C: Xóa access/refresh token và cache cục bộ
    C-->>U: Hiển thị trạng thái đã đăng xuất
~~~

Trong thực tế, client cũng nên xóa credential cục bộ ngay cả khi server trả lỗi. Nếu server không xác nhận được việc thu hồi, giao diện có thể thông báo “đã đăng xuất khỏi thiết bị này; chưa xác nhận thu hồi phía máy chủ” thay vì khẳng định mọi bản token đã mất hiệu lực.

## 5. Thu hồi refresh token và access JWT khi logout

### 5.1. Revocation endpoint

OAuth 2.0 Token Revocation (RFC 7009) định nghĩa endpoint để client yêu cầu Authorization Server thu hồi token. Client gửi token qua HTTPS theo cơ chế xác thực client phù hợp với loại client và cấu hình server.

Ví dụ request minh họa:

~~~http
POST /oauth/revoke HTTP/1.1
Host: identity.example.org
Content-Type: application/x-www-form-urlencoded

token=<refresh-token>&token_type_hint=refresh_token
~~~

Các điểm cần hiểu:

- Client nên thu hồi refresh token khi logout để ngăn dùng token đó xin access token mới.
- Nếu hệ thống hỗ trợ thu hồi access token, client hoặc backend có thể gửi yêu cầu riêng theo chính sách.
- Authorization Server quản lý trạng thái thu hồi; resource server phải có cách nhận biết trạng thái đó nếu cần chặn access JWT trước exp.
- Theo RFC 7009, response thành công không giúp client phân biệt token hợp lệ với token đã không còn hiệu lực; client không nên dựa vào response để suy ra token từng active.
- Revocation endpoint không phải endpoint để gửi token trong URL; dùng POST qua TLS.

RFC 7009 khuyến nghị Authorization Server thu hồi các token liên quan trong cùng grant khi phù hợp, nhưng cách resource server áp dụng trạng thái thu hồi vẫn phụ thuộc kiến trúc.

### 5.2. Vì sao access JWT có thể tiếp tục hoạt động sau revocation?

Giả sử Authorization Server đánh dấu access JWT đã revoked. Một API chỉ xác minh chữ ký offline không truy vấn trạng thái thu hồi thì không thể biết bản ghi đó vừa thay đổi.

Các lựa chọn để API nhận biết:

1. **Introspection:** API hỏi Authorization Server hoặc dịch vụ trạng thái xem token còn active không.
2. **Denylist:** API kiểm tra token ID hoặc fingerprint đã bị thu hồi.
3. **Session/version check:** API so sánh session ID, token version hoặc trạng thái subject với dữ liệu hiện hành.
4. **Revocation event:** hệ thống phân phối sự kiện thu hồi tới resource server/cache để chúng cập nhật trạng thái.
5. **Short-lived access token:** giảm cửa sổ sử dụng token cũ trong khi chờ hết hạn.

Nếu không có một trong các cơ chế trạng thái này, JWT được xác minh offline thường vẫn có thể được chấp nhận tới exp.

### 5.3. Access token TTL ngắn

TTL ngắn giới hạn khoảng thời gian token còn sử dụng được sau logout, nhưng không làm nó mất hiệu lực ngay.

Ví dụ:

| Access token TTL | Trường hợp logout lúc 09:15 | Giới hạn nếu chỉ xác minh offline |
| --- | --- | --- |
| 60 phút, phát hành lúc 09:00 | Token còn hạn tới 10:00 | Có thể còn được chấp nhận tối đa khoảng 45 phút |
| 10 phút, phát hành lúc 09:10 | Token còn hạn tới 09:20 | Có thể còn được chấp nhận tối đa khoảng 5 phút |
| 2 phút, phát hành lúc 09:14 | Token còn hạn tới 09:16 | Cửa sổ còn lại ngắn hơn, nhưng vẫn không bằng thu hồi tức thời |

Thời gian thực tế còn phụ thuộc clock skew, cache, thời điểm phát hành và chính sách kiểm tra. Chọn TTL theo SLA và mức độ nhạy cảm; TTL ngắn cũng làm tăng tải refresh.

## 6. Logout một thiết bị và logout tất cả thiết bị

Hai thao tác cần có ngữ nghĩa rõ ràng và phạm vi server-side tương ứng.

### 6.1. Logout thiết bị hiện tại

Mục tiêu là kết thúc phiên đang được sử dụng:

- Xác định session/grant hiện tại từ credential đã xác thực.
- Thu hồi refresh token family của phiên đó.
- Đánh dấu session revoked/ended.
- Xóa cookie hoặc token phía client.
- API có yêu cầu thu hồi nhanh phải kiểm tra trạng thái session/token.
- Giữ nguyên các phiên khác của cùng tài khoản.

### 6.2. Logout một thiết bị khác từ trang quản lý phiên

Người dùng có thể xem danh sách phiên và chọn “Đăng xuất thiết bị này” cho một thiết bị đã mất hoặc không còn sử dụng.

Backend cần:

1. Xác thực người dùng hiện tại.
2. Kiểm tra phiên đích thuộc đúng subject/tenant và người dùng có quyền quản lý phiên đó.
3. Thu hồi refresh token family/grant tương ứng.
4. Đánh dấu phiên đích revoked.
5. Phát sự kiện tới các resource server hoặc session store nếu cần hiệu lực nhanh.
6. Ghi audit event, không ghi raw token.

Không cho phép người dùng chỉ cần đoán session ID của người khác rồi kết thúc phiên đó.

### 6.3. Logout tất cả thiết bị

Logout all thường cần thu hồi tất cả phiên hoặc grants của tài khoản trong phạm vi được chọn:

- Liệt kê các phiên active thuộc subject.
- Thu hồi refresh token/token family liên quan.
- Hủy session tại BFF và các ứng dụng thuộc phạm vi.
- Tăng token/session version hoặc phát sự kiện để API nhận biết trạng thái mới.
- Thông báo cho các RP/ứng dụng tích hợp nếu có cơ chế SSO logout.
- Giữ lại một phiên hiện tại nếu sản phẩm có lựa chọn “đăng xuất các thiết bị khác”; phải thể hiện rõ trong UI.

Chỉ xóa tất cả token trên thiết bị hiện tại không phải logout all.

### 6.4. Bảng so sánh

| Tiêu chí | Logout thiết bị hiện tại | Logout thiết bị khác | Logout tất cả |
| --- | --- | --- | --- |
| Phạm vi | Phiên hiện tại | Một phiên được chọn | Tất cả phiên trong phạm vi |
| Refresh token | Thu hồi family hiện tại | Thu hồi family của phiên đích | Thu hồi mọi family/grant liên quan |
| Access JWT đã phát hành | Có thể cần trạng thái thu hồi/introspection | Tương tự, theo phiên đích | Có thể cần trạng thái trung tâm hoặc sự kiện toàn cục |
| Cookie/session ứng dụng | Hủy phiên hiện tại | Hủy session ở thiết bị đích khi có trạng thái server-side | Hủy mọi session thuộc phạm vi |
| Phiên khác | Giữ nguyên | Giữ nguyên | Kết thúc |
| Audit | Ghi sự kiện logout | Ghi subject, phiên đích và người thực hiện | Ghi phạm vi và kết quả thu hồi |

## 7. Logout trong hệ thống OAuth và OpenID Connect

OAuth 2.0 tập trung vào ủy quyền và access token; OAuth không định nghĩa một thao tác logout chung tự động kết thúc mọi phiên của mọi ứng dụng. OpenID Connect bổ sung các cơ chế logout để phối hợp giữa OP (OpenID Provider) và RP (Relying Party).

### 7.1. RP-Initiated Logout

OpenID Connect RP-Initiated Logout cho phép RP yêu cầu OP kết thúc phiên người dùng. Metadata của OP có thể công bố endpoint logout; RP điều hướng browser tới endpoint đó theo quy tắc của đặc tả.

Các tham số có thể gồm:

- **id_token_hint:** ID Token trước đó để OP nhận diện phiên/subject liên quan.
- **post_logout_redirect_uri:** URI được đăng ký để điều hướng sau logout.
- **state:** giá trị liên kết request và response theo luồng.

Các lưu ý:

- ID token hint không phải access token.
- Redirect URI phải được kiểm tra theo danh sách đã đăng ký; không chấp nhận URL tùy ý.
- RP nên kết thúc phiên local của mình, không chỉ chờ OP điều hướng.
- Logout tại OP không đảm bảo mọi resource server đã từ chối access JWT offline.

### 7.2. Front-Channel Logout

OIDC Front-Channel Logout cho phép OP thông báo logout tới các RP thông qua browser/front-channel. Cách này có thể giúp các ứng dụng kết thúc session local khi người dùng logout khỏi OP.

Tuy nhiên, front-channel phụ thuộc browser, cookie policy, iframe và các hạn chế theo dõi cross-site. Một RP có thể không nhận được thông báo do browser chặn cookie hoặc nội dung nhúng.

Không nên coi front-channel notification là bảo đảm duy nhất để thu hồi access JWT. Cần có session timeout, token expiry hoặc cơ chế trạng thái server-side bổ sung.

### 7.3. Back-Channel Logout

OIDC Back-Channel Logout cho phép OP gửi Logout Token trực tiếp tới endpoint của RP qua kênh server-to-server. RP xác minh Logout Token theo đặc tả, sau đó kết thúc session liên quan.

Logout Token là JWT có profile riêng, không phải access token dùng để gọi API nghiệp vụ. RP cần xác minh issuer, audience, chữ ký, thời gian, loại token và các claims/event bắt buộc; đồng thời chống xử lý lặp dựa trên định danh sự kiện phù hợp.

Back-channel có ưu điểm không phụ thuộc browser đang mở. Tuy nhiên, RP vẫn phải xử lý endpoint, xác minh token và cập nhật session state. Việc RP kết thúc session local không tự động làm mọi access JWT bị từ chối nếu resource server không kiểm tra trạng thái.

### 7.4. Phân biệt các lớp logout

| Cơ chế | Ai khởi tạo/nhận? | Mục tiêu | Có tự thu hồi access JWT offline? |
| --- | --- | --- | --- |
| Local logout | Client | Xóa credential và trạng thái local | Không |
| OAuth token revocation | Client/backend → Authorization Server | Thu hồi token tại Authorization Server | Không, nếu API không nhận trạng thái |
| RP-Initiated Logout | RP → OP | Kết thúc phiên SSO tại OP | Không |
| Front-Channel Logout | OP → RP qua browser | Thông báo RP kết thúc session | Không |
| Back-Channel Logout | OP → RP server-to-server | Thông báo RP kết thúc session | Không, trừ khi resource server được đồng bộ trạng thái |

## 8. Thiết kế logout endpoint an toàn

Một logout endpoint cần xác định rõ credential nào bị thu hồi, phiên nào bị kết thúc và client phải xóa dữ liệu gì.

### 8.1. Luồng logout cho một phiên

~~~http
POST /sessions/current/logout HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "revoke_refresh_token": true
}
~~~

Ví dụ minh họa một API nội bộ; tên endpoint và body không phải chuẩn OAuth bắt buộc. Backend cần suy ra phiên hiện tại từ credential đã xác minh hoặc một session handle được bảo vệ, không tin session ID tùy ý trong body.

### 8.2. Các yêu cầu bảo mật

- Chỉ cho phép chủ phiên hoặc principal có quyền quản trị phiên thực hiện logout.
- Không cho phép logout một session ID không thuộc subject hiện tại.
- Dùng POST hoặc phương thức thay đổi trạng thái phù hợp; không dùng GET để logout.
- Nếu dùng cookie tự động được browser gửi, bảo vệ endpoint khỏi CSRF bằng token CSRF, kiểm tra Origin/Fetch Metadata hoặc biện pháp phù hợp.
- Không đặt refresh token hoặc access token trong URL.
- Xác thực và giới hạn redirect URI nếu logout có điều hướng.
- Xử lý request lặp theo hướng idempotent: logout một phiên đã revoked vẫn có thể trả kết quả thành công an toàn.
- Ghi audit event nhưng không ghi raw token.
- Có timeout và retry có kiểm soát; không giữ token lâu dài chỉ vì server chưa phản hồi.

### 8.3. Logout request bị lỗi mạng

Client có thể không biết server đã xử lý logout hay chưa nếu kết nối bị ngắt sau khi server cập nhật trạng thái nhưng trước khi response tới client.

Thiết kế nên:

1. Client xóa credential cục bộ ngay để không tiếp tục dùng.
2. Backend xử lý logout idempotent để client có thể retry bằng một cơ chế an toàn nếu còn session handle.
3. Server lưu trạng thái revoked một cách bền vững trước khi trả xác nhận.
4. Client không diễn giải timeout là server chắc chắn chưa xử lý.
5. Giao diện phân biệt logout local hoàn tất và xác nhận thu hồi phía server nếu sản phẩm cần thông tin này.

## 9. Đồng bộ trạng thái logout giữa các API và ứng dụng

Trong kiến trúc nhiều service, một phiên có thể tạo token được dùng ở nhiều resource server. Logout chỉ có hiệu lực tức thời nếu các thành phần cần thiết nhận biết trạng thái thu hồi.

### 9.1. Introspection

Resource server gọi OAuth Token Introspection để kiểm tra token có còn active không. Nếu Authorization Server đã ghi nhận token hoặc grant bị thu hồi, introspection có thể trả trạng thái inactive.

Ưu điểm là có một nguồn trạng thái tập trung. Nhược điểm là thêm network dependency, độ trễ và tải. Cache kết quả active có thể kéo dài thời gian token bị chấp nhận sau logout; cache TTL phải phù hợp SLA thu hồi.

### 9.2. Denylist hoặc session registry

API có thể kiểm tra jti, sid, session ID hoặc token version với một kho trạng thái. Cần xác định:

- Khóa định danh có namespace theo issuer/tenant hay không.
- Bản ghi tồn tại tới khi nào.
- Các API có đọc cùng nguồn trạng thái hay cache riêng.
- Đồng bộ sự kiện mất bao lâu.
- Khi kho trạng thái không truy cập được, API fail-open hay fail-closed theo mức rủi ro.

Claim **sid** có thể được dùng trong một profile OIDC/session để liên kết token với phiên, nhưng không phải mọi JWT access token đều có **sid**. Không tự giả định claim này tồn tại hoặc có ý nghĩa giống nhau giữa các issuer.

### 9.3. Sự kiện thu hồi

Hệ thống có thể phát sự kiện khi session hoặc token family bị thu hồi:

~~~json
{
  "event": "session.revoked",
  "issuer": "https://identity.example.org",
  "subject": "user-42",
  "session_id": "S-102",
  "reason": "user_logout",
  "occurred_at": "2026-11-16T09:15:00Z"
}
~~~

Đây là event nội bộ minh họa, không phải định dạng bắt buộc. Sự kiện phải được xác thực nguồn, bảo vệ khỏi giả mạo, xử lý lặp an toàn và có cơ chế retry/đối soát khi consumer mất kết nối.

### 9.4. Token/session version

Một số hệ thống lưu phiên bản trạng thái cho subject hoặc session. Token mang version lúc phát hành; resource server so sánh với version hiện tại. Logout all hoặc thay đổi bảo mật có thể tăng version để làm token cũ không còn phù hợp.

Cách này cần trạng thái tra cứu hoặc cache tại resource server. Nếu API chỉ xác minh JWT offline mà không có version mới, việc tăng version trong database không ảnh hưởng token cũ.

## 10. Refresh token rotation và logout

Refresh token rotation cấp refresh token mới mỗi khi token cũ được sử dụng thành công. Nếu một refresh token cũ đã bị dùng lại sau rotation, Authorization Server có thể nhận diện dấu hiệu token bị sao chép và thu hồi token family theo chính sách.

Khi logout:

- Thu hồi refresh token hiện tại hoặc token family của phiên.
- Không tiếp tục refresh khi session đã revoked.
- Xóa refresh token mới nhất khỏi thiết bị.
- Nếu rotation xảy ra đồng thời với logout, server cần xử lý race condition để token vừa được cấp không làm sống lại phiên.
- Nếu phát hiện reuse bất thường, đánh giá thu hồi toàn bộ family và yêu cầu xác thực lại.

Không chỉ xóa refresh token ở client. Nếu bản sao refresh token ở nơi khác vẫn active tại Authorization Server, bên giữ bản sao có thể tiếp tục xin access token.

## 11. Rủi ro đặc biệt: thiết bị bị mất hoặc bị đánh cắp

Khi thiết bị mất, người dùng có thể không còn khả năng mở ứng dụng để thực hiện logout. Cần hỗ trợ quản lý phiên từ một thiết bị khác:

1. Người dùng đăng nhập lại bằng phương thức xác thực đủ mạnh.
2. Mở danh sách phiên/thiết bị đã đăng nhập.
3. Chọn phiên tương ứng với thiết bị bị mất.
4. Backend thu hồi refresh token family và đánh dấu session revoked.
5. Phân phối trạng thái thu hồi tới các API cần kiểm tra.
6. Cân nhắc đổi mật khẩu hoặc thực hiện bước bảo vệ tài khoản bổ sung nếu có dấu hiệu xâm nhập.
7. Nếu nền tảng hỗ trợ, yêu cầu remote wipe hoặc xóa dữ liệu doanh nghiệp; không coi remote wipe là bảo đảm duy nhất.

Tên thiết bị, model, IP, vị trí gần đúng và thời điểm hoạt động có thể hỗ trợ người dùng nhận diện phiên, nhưng không phải bằng chứng tuyệt đối. Không dùng địa chỉ IP hoặc device label làm yếu tố duy nhất để quyết định quyền thu hồi.

## 12. Tình huống thực tế

### Tình huống A — Người dùng nhấn logout nhưng bản sao JWT vẫn hoạt động

Ứng dụng xóa token khỏi local storage. Một bản sao đã bị lấy trước đó vẫn được gửi tới API. API xác minh offline và chấp nhận vì exp chưa tới.

**Bài học:** local logout chỉ xóa bản local. Muốn chặn bản sao cần revocation state/introspection/denylist hoặc TTL ngắn theo SLA.

### Tình huống B — Logout điện thoại A nhưng điện thoại B cũng bị đăng xuất

Hai thiết bị dùng chung một refresh token family. Khi logout trên A, server thu hồi family đó và B mất khả năng refresh.

**Bài học:** nếu cần logout riêng từng thiết bị, cấp session/grant hoặc token family riêng cho mỗi lần đăng nhập.

### Tình huống C — Thu hồi refresh token nhưng access JWT vẫn gọi API

Authorization Server thu hồi refresh token nhưng API chỉ xác minh chữ ký access JWT. Token đã cấp trước đó vẫn còn hạn.

**Bài học:** refresh-token revocation ngăn cấp token mới; API cần kiểm tra trạng thái nếu muốn chặn access token cũ trước exp.

### Tình huống D — Người dùng logout khỏi IdP nhưng ứng dụng vẫn mở

Người dùng kết thúc phiên SSO tại IdP. Một RP không nhận được front-channel/back-channel notification nên session local vẫn còn.

**Bài học:** SSO logout cần cơ chế phối hợp RP/OP và session state; không mặc định logout ở một bên tự kết thúc mọi bên.

### Tình huống E — Logout request timeout

Server đã thu hồi session nhưng response bị mất. Client nghĩ request thất bại và gửi lại. Nếu endpoint không idempotent, có thể phát sinh lỗi hoặc trạng thái không nhất quán.

**Bài học:** logout nên idempotent; client xóa credential local và server ghi trạng thái revoked bền vững.

### Tình huống F — Thiết bị bị mất

Người dùng không còn thiết bị A để nhấn logout. Từ laptop B, họ mở trang quản lý phiên và thu hồi phiên A. Refresh token bị chặn nhưng API chưa có kiểm tra trạng thái nên access JWT cũ vẫn dùng được trong một khoảng thời gian.

**Bài học:** quản lý phiên tập trung phải kết hợp cơ chế thu hồi access token phù hợp với SLA, không chỉ thu hồi refresh token.

## 13. Checklist thiết kế logout

### Ngữ nghĩa và phạm vi

- [ ] Phân biệt local logout, device logout, RP logout, IdP logout và global logout.
- [ ] Giao diện nói rõ đăng xuất thiết bị hiện tại, thiết bị khác hay tất cả thiết bị.
- [ ] Mỗi phiên/thiết bị có định danh server-side khi cần thu hồi riêng.
- [ ] Không dựa duy nhất vào device ID do client gửi.
- [ ] Xác định logout có kết thúc phiên SSO hay chỉ phiên ứng dụng.

### Credential và trạng thái

- [ ] Xóa access token và refresh token khỏi thiết bị.
- [ ] Thu hồi refresh token/token family phía Authorization Server.
- [ ] Hủy BFF/application session và cookie phía server/client khi áp dụng.
- [ ] Xác định access JWT còn hiệu lực sau logout trong bao lâu.
- [ ] Dùng introspection, denylist, session/version check hoặc sự kiện nếu cần thu hồi nhanh.
- [ ] Cache và độ trễ đồng bộ đáp ứng SLA thu hồi.
- [ ] Xử lý refresh token rotation và race condition với logout.

### SSO và ứng dụng

- [ ] Triển khai RP-Initiated Logout khi cần kết thúc phiên OP.
- [ ] Kiểm tra redirect URI sau logout theo danh sách đăng ký.
- [ ] Xử lý front-channel/back-channel notification theo profile OIDC nếu hỗ trợ.
- [ ] Không coi logout notification là bằng chứng access JWT offline đã mất hiệu lực.
- [ ] Đồng bộ logout giữa tab/window hoặc ứng dụng theo yêu cầu.

### Vận hành và kiểm thử

- [ ] Logout endpoint yêu cầu xác thực và quyền trên phiên đích.
- [ ] Bảo vệ CSRF nếu dùng cookie tự động gửi.
- [ ] Logout request xử lý idempotent.
- [ ] Audit sự kiện logout/revocation mà không ghi raw token.
- [ ] Có quy trình thu hồi phiên khi thiết bị mất hoặc tài khoản bị xâm nhập.
- [ ] Kiểm thử token cũ, refresh token cũ, phiên thiết bị khác và trạng thái cache.

## 14. Kiểm thử các trường hợp logout

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Logout local khi server đang hoạt động | Credential local bị xóa; server thu hồi phiên/refresh token theo hợp đồng |
| Logout local khi mất mạng | Client ngừng sử dụng và xóa credential local; không tuyên bố server đã xác nhận thu hồi |
| Dùng refresh token sau logout | Authorization Server từ chối |
| Dùng access JWT cũ sau logout | Bị từ chối theo cơ chế trạng thái/SLA; nếu API offline-only thì cửa sổ tới exp phải được ghi nhận |
| Logout một thiết bị | Phiên đó bị thu hồi; thiết bị khác vẫn hoạt động |
| Logout tất cả thiết bị | Tất cả session/token family thuộc phạm vi bị thu hồi |
| Gửi lại logout request | Kết quả idempotent, không làm sống lại phiên |
| Logout session ID của người khác | Bị từ chối |
| Refresh rotation đồng thời logout | Không phát sinh refresh token mới còn active sau khi phiên đã kết thúc |
| Logout tại OP | RP session được kết thúc theo cơ chế SLO đã triển khai |
| Back-channel Logout Token sai issuer/audience/chữ ký | RP từ chối event |
| Back-channel logout event bị phát lại | Được xử lý an toàn, không gây side effect không kiểm soát |
| Cache trạng thái thu hồi bị trễ | Độ trễ nằm trong SLA và được giám sát |
| Token bị ghi trong audit log | Không có raw access/refresh token |

## 15. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Xóa JWT khỏi local storage có thu hồi bản sao ở nơi khác không? | **Không.** Chỉ xóa bản lưu tại client hiện tại. |
| Logout có tự làm access JWT xác minh offline mất hiệu lực ngay không? | **Không.** API cần kiểm tra trạng thái thu hồi hoặc chờ token hết hạn. |
| Thu hồi refresh token có đồng nghĩa mọi access JWT đã cấp đều bị từ chối ngay không? | **Không mặc nhiên.** Resource server offline có thể tiếp tục chấp nhận access token cũ. |
| Muốn logout riêng một thiết bị cần gì? | Phiên/grant hoặc refresh-token family có thể nhận diện và thu hồi riêng ở server. |
| Logout khỏi IdP có tự kết thúc session ở mọi RP không? | **Không.** Cần cơ chế phối hợp logout như front-channel hoặc back-channel và xử lý session tại RP. |
| Có nên dùng device label hoặc IP làm bằng chứng duy nhất để thu hồi phiên không? | **Không.** Chúng chỉ là dữ liệu hỗ trợ nhận diện, không phải bằng chứng mật mã. |
| Logout endpoint có nên xử lý request lặp an toàn không? | **Có.** Idempotency giúp xử lý timeout và retry. |
| Nếu API chỉ xác minh chữ ký và exp, cửa sổ sử dụng token sau logout phụ thuộc điều gì? | Thời gian còn lại tới exp, cùng clock skew và chính sách xác minh. |
| Logout all có phải chỉ xóa token trên thiết bị đang dùng không? | **Không.** Phải thu hồi mọi phiên/grant thuộc phạm vi được công bố. |

## 16. Ghi nhớ

- Logout có nhiều phạm vi: local, một thiết bị, một ứng dụng/RP, IdP/SSO và tất cả thiết bị.
- Xóa token khỏi thiết bị chỉ xóa bản local; bản sao đã bị đánh cắp vẫn có thể sử dụng.
- Thu hồi refresh token ngăn cấp access token mới từ credential đó, nhưng không tự đảm bảo mọi API từ chối access JWT đã phát hành.
- JWT access token xác minh offline thường còn được chấp nhận tới exp nếu resource server không kiểm tra trạng thái.
- Muốn logout riêng từng thiết bị, cần session/grant hoặc refresh-token family riêng và trạng thái server-side.
- Muốn thu hồi access JWT nhanh, cần introspection, denylist, session/version check, revocation event hoặc cơ chế tương đương; phải tính cache và độ trễ.
- OIDC logout phối hợp phiên OP/RP; nó không tự thay thế cơ chế thu hồi access token ở resource server.
- Logout endpoint nên xác thực chủ phiên, bảo vệ CSRF khi cần, xử lý idempotent và không ghi raw token.
- Cần kiểm thử riêng local deletion, refresh revocation, access JWT cũ, device logout, global logout và SSO logout.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [RFC 8417 – Security Event Token (SET)](https://www.rfc-editor.org/rfc/rfc8417)
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
