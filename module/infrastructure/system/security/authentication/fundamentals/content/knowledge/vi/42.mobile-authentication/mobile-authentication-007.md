# Token refresh

**Token refresh** là quy trình ứng dụng dùng refresh token để yêu cầu authorization server cấp access token mới mà người dùng không phải nhập lại thông tin đăng nhập trong mỗi lần access token hết hạn. Trong ứng dụng mobile, refresh token thường có vòng đời dài hơn access token và được lưu trên thiết bị, vì vậy nó là credential có giá trị cao: nếu bị đánh cắp, kẻ tấn công có thể tiếp tục xin access token mới cho tới khi token bị hết hạn, thu hồi hoặc bị ràng buộc bởi một cơ chế sender-constraining.

Một thiết kế an toàn cần quản lý toàn bộ vòng đời refresh token: phát hành sau luồng đăng nhập đúng chuẩn, lưu trữ bằng cơ chế bảo vệ của hệ điều hành, gửi token chỉ tới authorization server qua TLS, xử lý rotation và phát hiện replay, đồng bộ các request refresh, phản ứng với lỗi mạng và thu hồi khi logout hoặc thiết bị bị mất. Ứng dụng native là public client; không thể bảo vệ một client secret được nhúng trong binary như bí mật phía server.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập. Trong chương **Authentication trong mobile**, bài này tập trung vào cách làm mới token an toàn trên iOS và Android.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt access token, refresh token, ID token và session của ứng dụng.
2. Mô tả Authorization Code Flow với PKCE trong ứng dụng native và vai trò của refresh token.
3. Gửi refresh request đúng OAuth 2.0, đúng issuer, đúng client và đúng scope.
4. Giải thích vì sao mobile app là public client và không được dựa vào client secret nhúng trong ứng dụng.
5. Lưu refresh token trong vùng lưu trữ được bảo vệ bởi hệ điều hành, tách token khỏi log, backup và dữ liệu ứng dụng thông thường.
6. Phân tích refresh token rotation, token family, reuse detection và nguy cơ replay.
7. Xử lý nhiều request đồng thời để tránh dùng lại refresh token cũ.
8. Xây dựng state machine cho refresh, timeout, retry, logout và yêu cầu đăng nhập lại.
9. Đánh giá sender-constrained token bằng DPoP và giới hạn của ràng buộc thiết bị.
10. Thiết kế kiểm thử cho token hết hạn, refresh thất bại, crash giữa rotation, thiết bị mất và logout.

## 2. Phân biệt các loại token và session

| Thành phần | Mục đích | Nơi được gửi |
| --- | --- | --- |
| Access token | Cho phép gọi resource server trong phạm vi audience/scope và thời hạn được cấp. | Resource server/API tương ứng. |
| Refresh token | Xin access token mới từ authorization server. | Chỉ authorization server tại token endpoint. |
| ID token | Assertion của OpenID Connect về sự kiện xác thực và subject cho client. | Client OIDC nhận và xác minh; không dùng thay access token để gọi API. |
| App session | Trạng thái UI và đăng nhập nội bộ của ứng dụng mobile. | Được quản lý trong ứng dụng; có thể phụ thuộc token/session server. |
| Authorization grant | Sự cho phép mà authorization server đã cấp cho client. | Được quản lý tại authorization server. |

Refresh token không phải access token có thời hạn dài. Nó có quyền xin credential mới nên thường có mức độ nhạy cảm cao hơn. Không gửi refresh token tới Course API, analytics, crash reporting hoặc một backend tùy ý. Chỉ gửi tới token endpoint của issuer đã được cấu hình và xác minh.

ID token cũng không phải refresh token. ID token mô tả kết quả xác thực theo OIDC; access token là credential dành cho resource server. Nếu OIDC token response khi refresh có trả ID token mới, client phải xử lý theo quy tắc OIDC và không dùng ID token làm bearer credential cho API.

### 2.1. Vòng đời khái quát

1. Ứng dụng mở trình duyệt hệ thống để người dùng xác thực với authorization server.
2. Ứng dụng nhận authorization code qua redirect URI đã đăng ký.
3. Ứng dụng đổi code lấy access token và có thể nhận refresh token.
4. Ứng dụng lưu refresh token trong secure storage; access token thường giữ trong memory hoặc cache có thời hạn ngắn.
5. Khi access token hết hạn hoặc sắp hết hạn, ứng dụng gửi refresh token tới token endpoint.
6. Authorization server xác minh client, grant, trạng thái refresh token, rotation và các ràng buộc liên quan.
7. Server trả access token mới và có thể trả refresh token mới.
8. Ứng dụng thay thế refresh token cũ theo semantics của issuer, cập nhật cache access token và tiếp tục request.
9. Khi logout, compromise hoặc thu hồi grant, ứng dụng dừng dùng token và thực hiện revoke theo policy.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant M as Mobile App
    participant AS as Authorization Server
    participant RS as Resource API
    participant K as Secure Storage
    U->>M: Đăng nhập
    M->>AS: Authorization Code + PKCE qua browser hệ thống
    AS-->>M: Authorization code qua redirect URI
    M->>AS: Đổi code + code_verifier
    AS-->>M: Access token + Refresh token
    M->>K: Lưu refresh token an toàn
    M->>RS: API request với access token
    RS-->>M: Resource response
    Note over M: Access token hết hạn hoặc sắp hết hạn
    M->>K: Đọc refresh token
    M->>AS: POST token endpoint, grant_type=refresh_token
    AS-->>M: Access token mới và refresh token mới (nếu rotation)
    M->>K: Thay thế refresh token cũ
    M->>RS: Request tiếp theo với access token mới
~~~

## 3. Nền tảng xác thực cho mobile app

### 3.1. Mobile app là public client

Ứng dụng native được phân phối tới thiết bị của người dùng. Người dùng hoặc attacker có thể phân tích binary, kiểm tra cấu hình, hook runtime hoặc trích xuất chuỗi. Vì vậy, một giá trị client secret được đóng gói trong app không thể được coi là bí mật lâu dài.

Ứng dụng native thường là **public client**:
- Có client ID để xác định ứng dụng; client ID không phải secret.
- Không nhúng client secret để xác thực như confidential client.
- Dùng Authorization Code Flow với PKCE, theo hướng dẫn cho native apps.
- Mở trang đăng nhập bằng external user-agent (browser hệ thống hoặc session trình duyệt được hệ điều hành hỗ trợ), không tự dựng form mật khẩu giả dạng authorization server.
- Đăng ký redirect URI phù hợp, xác minh state và dùng PKCE S256.
- Không dùng implicit flow cho ứng dụng mới.

Nếu ứng dụng cần một thành phần giữ secret, thành phần đó phải chạy ở backend được kiểm soát. Backend có thể là confidential client; mobile app vẫn không trở thành confidential client chỉ vì có obfuscation, certificate pinning hay anti-tamper.

### 3.2. Authorization Code Flow với PKCE

PKCE tạo một cặp code verifier và code challenge cho từng authorization transaction. Ứng dụng tạo verifier ngẫu nhiên, gửi challenge trong authorization request và gửi verifier khi đổi authorization code. Authorization server kiểm tra chúng khớp nhau, giảm nguy cơ attacker chặn authorization code rồi tự đổi code đó.

PKCE bảo vệ authorization code exchange; nó không tự bảo vệ refresh token đã lưu trên thiết bị. Hai giai đoạn cần biện pháp riêng:
- Authorization code: redirect URI, state, PKCE và browser/system user-agent.
- Refresh token: secure storage, rotation/reuse detection, sender-constraining khi phù hợp, expiry và revocation.

### 3.3. Redirect URI và issuer

Ứng dụng cần dùng redirect URI đã đăng ký và xác minh response thuộc đúng transaction. Custom URL scheme có thể bị ứng dụng khác đăng ký trùng trên một số nền tảng; ưu tiên claimed HTTPS app links/universal links khi hệ sinh thái hỗ trợ, hoặc áp dụng hướng dẫn nền tảng và nhà cung cấp. Kiểm tra state, issuer và transaction correlation; không chấp nhận callback chỉ vì URI có cùng scheme.

Không nhận issuer/token endpoint từ dữ liệu deep link không tin cậy. Cấu hình issuer phải được pin theo môi trường hoặc lấy từ discovery document đã xác minh theo cấu hình tin cậy.

## 4. Refresh token request

OAuth 2.0 định nghĩa refresh token grant tại token endpoint. Request thường dùng HTTPS POST với content type application/x-www-form-urlencoded.

Ví dụ cho public native client:

~~~http
POST /oauth/token HTTP/1.1
Host: auth.studyhub.example
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=REFRESH_TOKEN_VALUE&
client_id=studyhub-mobile
~~~

Các điểm cần lưu ý:

- Gửi request tới token endpoint của issuer đã cấu hình và xác minh; không gửi tới resource API.
- Dùng TLS và không ghi body chứa token vào log.
- Public client gửi client ID theo cấu hình issuer yêu cầu; không gửi một client secret được nhúng trong app.
- Confidential client có thể phải xác thực client theo phương thức đã đăng ký, nhưng đó là vai trò của backend.
- Scope yêu cầu khi refresh không được mở rộng quyền vượt quá grant ban đầu. Nếu không gửi scope, server áp dụng quy tắc của grant ban đầu theo OAuth.
- Authorization server có thể áp dụng audience/resource restriction và policy riêng.
- Refresh token có thể opaque hoặc có cấu trúc; client không nên tự suy ra tính hợp lệ chỉ bằng cách đọc chuỗi.

Ví dụ response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "profile courses.read"
}
~~~

Response thực tế phụ thuộc authorization server và policy. Trường refresh_token có thể được trả lại khi server rotation; một số issuer không rotation mỗi lần. Nếu server trả refresh token mới, client phải lưu token mới và ngừng dùng token cũ theo quy tắc của issuer. Nếu response không có refresh token mới, client chỉ tiếp tục dùng token hiện có khi semantics của issuer cho phép.

### 4.1. Scope và least privilege

Refresh token không nên làm tăng quyền của người dùng hoặc ứng dụng. Token mới chỉ nên đại diện grant đã được cấp, với scope và resource phù hợp. Nếu ứng dụng cần quyền mới, phải đi qua authorization flow/consent hoặc cơ chế step-up được issuer hỗ trợ; không tự thêm scope vào refresh request để nâng quyền.

Mobile app nên yêu cầu scope tối thiểu:
- Chỉ xin quyền API mà tính năng đang cần.
- Không yêu cầu quyền quản trị cho toàn bộ app nếu chỉ một màn hình cần.
- Tách audience cho các API nếu issuer hỗ trợ.
- Không chia sẻ refresh token giữa app khác, tenant khác hoặc account khác.

## 5. Lưu refresh token trên iOS và Android

Refresh token có thể tồn tại lâu và cho phép xin credential mới. Lưu nó trong vùng lưu trữ có bảo vệ của hệ điều hành, không lưu cùng dữ liệu cấu hình thông thường.

### 5.1. iOS Keychain

Keychain là nơi lưu credential và secret trên iOS. Ứng dụng nên:
- Lưu refresh token dưới service/account identifier rõ ràng, tách theo issuer, client và user account.
- Chọn accessibility class phù hợp với yêu cầu mở khóa và background behavior.
- Cân nhắc yêu cầu user presence/biometric cho key hoặc item khi UX và threat model phù hợp.
- Tắt đồng bộ iCloud Keychain cho credential cần gắn với thiết bị nếu policy yêu cầu; chọn accessibility/synchronization attributes có chủ đích.
- Xóa item khi logout, account removal hoặc credential compromise.
- Không giả định gỡ ứng dụng luôn xóa mọi Keychain item; hành vi có thể khác với app container.

Biometric prompt chỉ là lớp kiểm soát truy cập cục bộ vào item/key. Nó không tự chứng minh với authorization server rằng request refresh hiện tại được một người dùng hợp lệ thực hiện. Nếu cần ràng buộc mật mã, dùng private key gắn với thiết bị và giao thức sender-constraining phù hợp.

### 5.2. Android Keystore và vùng lưu trữ ứng dụng

Android Keystore bảo vệ key material và có thể cung cấp key hardware-backed trên thiết bị hỗ trợ. Keystore thường giữ khóa mã hóa, còn token được lưu trong storage riêng của ứng dụng dưới dạng ciphertext:
- Sinh khóa mã hóa bằng Android Keystore; ưu tiên hardware-backed nếu thiết bị hỗ trợ và policy cần.
- Mã hóa refresh token trước khi lưu vào file/database riêng tư của app.
- Hạn chế backup/migration của dữ liệu token và khóa; kiểm tra chính sách Android backup/data extraction.
- Dùng cơ chế đồng bộ và ghi file an toàn để tránh mất token khi process bị kill.
- Xóa ciphertext và key alias khi logout hoặc thu hồi credential.
- Không dựa vào IMEI, Android ID hoặc advertising ID làm bí mật xác thực.

Keystore bảo vệ khóa; nó không có nghĩa toàn bộ token tự động được lưu trong phần cứng bảo mật. Khi app process đang chạy và có quyền giải mã, malware có khả năng điều khiển process có thể cố gọi chức năng sử dụng key hoặc đọc plaintext trong memory. Hardware-backed key giúp giảm một số kiểu trích xuất key, không bảo vệ tuyệt đối trước thiết bị đã bị compromise.

### 5.3. Access token và refresh token nên lưu khác nhau

| Dữ liệu | Nơi lưu gợi ý | Lý do |
| --- | --- | --- |
| Access token | Memory hoặc cache ngắn hạn có kiểm soát | Hạn sử dụng ngắn; giảm thời gian tồn tại trên disk. |
| Refresh token | iOS Keychain hoặc encrypted app storage với key từ Android Keystore | Credential dài hạn, cần bảo vệ mạnh và tồn tại qua app restart. |
| Client ID | App configuration | Không phải secret. |
| Client secret | Không nhúng trong native app | Có thể bị trích xuất từ binary/runtime. |
| PKCE verifier | Memory/transaction store bảo vệ trong thời gian flow | Chỉ cần trong một authorization transaction. |
| DPoP private key | Keystore/Keychain hoặc hardware-backed key nếu hỗ trợ | Dùng để chứng minh possession của key tương ứng. |

Không lưu token trong source code, plist/manifest, preferences dạng rõ, clipboard, screenshot, notification, URL, analytics hoặc crash dump. Không gửi token qua query string.

## 6. Refresh token rotation và token family

Refresh token rotation là cơ chế authorization server cấp refresh token mới khi token hiện tại được sử dụng, đồng thời vô hiệu hóa token cũ. Các token kế tiếp có thể thuộc cùng một **token family** hoặc grant lineage để server phát hiện reuse.

Ví dụ:

1. App giữ refresh token R1.
2. App gửi R1 tới token endpoint.
3. Server xác minh R1, cấp access token A2 và refresh token R2.
4. Server đánh dấu R1 đã dùng/không còn hợp lệ.
5. App lưu R2 và chỉ dùng R2 trong lần refresh sau.
6. Nếu attacker hoặc một client khác gửi lại R1, server có thể phát hiện replay/reuse và thu hồi token family theo policy.

~~~mermaid
stateDiagram-v2
    [*] --> ActiveR1
    ActiveR1 --> RotatedR2: Refresh R1 accepted
    RotatedR2 --> RotatedR3: Refresh R2 accepted
    RotatedR3 --> Revoked: Reuse old R1 detected
    ActiveR1 --> Revoked: Expiry, logout or compromise
    RotatedR2 --> Revoked: Logout or compromise
    Revoked --> [*]
~~~

Rotation giảm cửa sổ sử dụng của token cũ và tạo tín hiệu phát hiện token bị sao chép. Nhưng rotation chỉ hiệu quả nếu:
- Server ghi nhận trạng thái token cũ đã dùng.
- Server có thể liên kết token trong family/grant.
- Reuse detection được triển khai và có policy rõ ràng.
- Client thay thế token mới an toàn và tránh gửi token cũ đồng thời.
- Hệ thống vận hành xử lý đúng retry, timeout và response bị mất.

Không phải mọi authorization server đều triển khai rotation hoặc reuse detection giống nhau. Cần kiểm tra semantics của issuer và cấu hình cụ thể.

### 6.1. Reuse detection

Nếu một refresh token đã bị rotation mà vẫn xuất hiện lần nữa, server có thể coi đây là dấu hiệu token bị sao chép hoặc replay. Vì server thường không biết request nào là thiết bị hợp lệ, một policy phổ biến là revoke toàn bộ token family liên quan và yêu cầu người dùng xác thực lại.

Điều này có thể khiến người dùng bị logout nếu app gửi refresh token cũ do race condition hoặc retry không đúng. Vì vậy, client concurrency control là một phần của bảo mật, không chỉ là tối ưu hiệu năng.

### 6.2. Khi server không rotation

Một số issuer giữ refresh token ổn định trong nhiều lần refresh hoặc rotation theo chu kỳ. Client phải tuân theo contract của issuer:
- Nếu response có refresh token mới, thay thế token cũ.
- Nếu response không có token mới, chỉ giữ token cũ khi issuer xác nhận đó là behavior hợp lệ.
- Không tự suy diễn rằng refresh token luôn bất biến hoặc luôn đổi sau mỗi lần gọi.
- Không tiếp tục dùng token đã nhận response invalid/revoked.
- Không cố thử refresh liên tục sau lỗi invalid_grant.

## 7. Chống refresh đồng thời và race condition

Mobile app có thể có nhiều API request cùng nhận 401 khi access token hết hạn. Nếu mỗi request tự gọi refresh, nhiều request có thể cùng gửi một refresh token cũ. Với rotation, request đầu tiên có thể thành công và vô hiệu hóa token; request thứ hai bị xem là reuse, dẫn tới revoke family.

### 7.1. Single-flight refresh

Dùng một refresh coordinator cho mỗi account/issuer/client:
1. Request đầu tiên phát hiện access token cần refresh và lấy quyền refresh lock.
2. Các request khác chờ cùng một refresh operation.
3. Coordinator đọc refresh token hiện tại từ secure storage.
4. Gửi đúng một refresh request.
5. Lưu access token mới và refresh token mới (nếu có) một cách nhất quán.
6. Cập nhật generation/version của token state.
7. Đánh thức các request đang chờ để chúng dùng access token mới.

Không dùng một global token store cho nhiều account nếu app hỗ trợ nhiều tài khoản. Khóa phải gắn đúng account, issuer và client; thao tác đổi account cần tách state để không gửi token của tài khoản A trong request của tài khoản B.

### 7.2. Cập nhật token nguyên tử

Nếu server đã rotate R1 thành R2 nhưng app crash trước khi lưu R2, app có thể chỉ còn R1 đã bị vô hiệu. Khi mở lại, refresh R1 có thể bị từ chối hoặc kích hoạt reuse detection. Do đó:
- Cập nhật record token theo một thao tác nhất quán trong storage.
- Gắn generation/version để request cũ không ghi đè token mới.
- Không để hai refresh response tới muộn ghi đè lẫn nhau.
- Lưu refresh token mới trước khi đánh dấu refresh operation hoàn tất.
- Nếu có thể, dùng transaction hoặc atomic replace cho cặp token state.
- Xử lý trường hợp server đã commit rotation nhưng response không đến app như một trạng thái không chắc chắn.

### 7.3. Race giữa logout và refresh

Nếu người dùng logout trong khi refresh đang chạy, refresh response đến muộn không được khôi phục phiên đã logout. Coordinator cần có generation/state check:
- Logout chuyển session state sang Revoking/LoggedOut và chặn request mới.
- Refresh response chỉ được commit nếu session generation vẫn khớp và chưa logout.
- Token mới nhận muộn phải được revoke nếu có thể và xóa khỏi storage.
- Không ghi đè trạng thái LoggedOut bằng Active chỉ vì refresh request trước đó thành công.

## 8. Xử lý timeout, retry và lỗi

Refresh request có thể thất bại vì mất mạng, authorization server tạm thời unavailable, token hết hạn, token bị revoke, client config sai hoặc reuse detection. Mỗi loại lỗi cần một hành vi khác nhau.

| Tình huống | Hành vi khuyến nghị |
| --- | --- |
| Access token hết hạn | Dùng coordinator để refresh một lần; nếu thành công, retry API request phù hợp một lần. |
| Mất mạng trước khi gửi request | Giữ trạng thái token hiện tại; chờ kết nối và thử lại theo policy. |
| Timeout không biết server đã xử lý hay chưa | Trạng thái mơ hồ; không blind-retry refresh token cũ khi rotation/reuse detection có thể bật. |
| HTTP 429 | Tôn trọng Retry-After nếu có; backoff có jitter và giới hạn retry. |
| HTTP 5xx | Retry có giới hạn chỉ khi semantics của issuer cho phép; response lỗi có thể xảy ra sau khi server đã xử lý rotation. |
| invalid_grant | Token có thể hết hạn, revoked, đã dùng hoặc không hợp lệ; dừng refresh loop, xóa/đánh dấu credential và yêu cầu đăng nhập lại. |
| invalid_client / unauthorized_client | Lỗi cấu hình hoặc client authentication; không lặp vô hạn, báo lỗi vận hành an toàn. |
| insufficient_scope từ resource API | Refresh không tự cấp thêm quyền; xử lý authorization/consent theo flow thích hợp. |
| Tài khoản disabled hoặc grant revoked | Dừng truy cập và yêu cầu người dùng xử lý tài khoản theo policy. |

### 8.1. Timeout mơ hồ sau rotation

Một tình huống quan trọng:
1. App gửi R1.
2. Authorization server đã xử lý R1, vô hiệu hóa R1 và tạo R2.
3. Response chứa R2 bị mất trên mạng.
4. App chỉ còn R1.
5. App retry R1; server có thể coi đó là reuse và revoke family.

Client không thể luôn biết server đã commit hay chưa chỉ từ một timeout. Không có một cách retry phổ quát an toàn cho mọi issuer. Cần:
- Ưu tiên semantics retry/idempotency được issuer tài liệu hóa.
- Nếu issuer hỗ trợ grace period hoặc recovery mechanism, hiểu rõ trade-off và giới hạn của nó.
- Không tự giả định retry cùng refresh token luôn idempotent.
- Khi không thể khôi phục an toàn, yêu cầu người dùng đăng nhập lại thay vì thử token cũ vô hạn.
- Ghi telemetry không chứa token để phân tích timeout/reuse.

### 8.2. Retry API request sau refresh

Chỉ retry API request sau khi refresh thành công và xác định lỗi trước đó thực sự do access token hết hạn. Không refresh vô hạn cho mọi 401. Không refresh khi API trả 403/insufficient_scope hoặc user không có quyền.

Nếu request nghiệp vụ là POST tạo giao dịch, gửi email hoặc thanh toán, retry có thể tạo tác dụng phụ lặp. Chỉ retry request không idempotent khi API có idempotency key và server hỗ trợ semantics tương ứng; nếu không, trả kết quả lỗi/uncertain để ứng dụng xử lý an toàn.

### 8.3. Clock skew

Client có thể dùng expires_in hoặc exp như tín hiệu để refresh trước khi token hết hạn một khoảng đệm nhỏ, tránh request thất bại đúng thời điểm expiry. Nhưng đồng hồ thiết bị có thể sai. Server vẫn là nguồn quyết định token có hợp lệ hay không. Nếu token opaque, client không cần và không thể tự đọc claim. Nếu JWT, không coi việc parse payload chưa xác minh là bằng chứng token hợp lệ hoặc quyền được phép.

## 9. Sender-constrained refresh token và DPoP

Bearer refresh token có thể bị replay nếu attacker lấy được giá trị. Sender-constraining gắn việc sử dụng token với bằng chứng sở hữu một private key hoặc credential khác, làm cho chỉ có token thôi chưa đủ.

### 9.1. DPoP

Demonstrating Proof of Possession (DPoP) là cơ chế chuẩn hóa để client chứng minh sở hữu private key khi gọi token endpoint hoặc resource server trong các flow hỗ trợ. App tạo key pair; private key được giữ trong Keychain/Keystore nếu nền tảng hỗ trợ. Request mang DPoP proof ký bằng private key, chứa thông tin ràng buộc request như method, URI, thời điểm và unique identifier. Authorization server/resource server xác minh proof và ràng buộc token với public key tương ứng.

DPoP có thể giảm giá trị của một refresh token bị sao chép đơn lẻ vì attacker còn cần private key tương ứng. Tuy nhiên:
- Authorization server và resource server phải hỗ trợ DPoP.
- Key phải được quản lý, xoay và thu hồi theo lifecycle của app/device.
- Private key có thể không export được nhưng malware có thể cố gọi chức năng ký nếu chiếm được app process.
- DPoP không thay thế TLS, PKCE, secure storage, authorization hoặc bảo vệ thiết bị.
- DPoP không có nghĩa token không thể bị đánh cắp hoặc sử dụng trong mọi kịch bản.

### 9.2. Ràng buộc theo thiết bị

Nếu dùng key pair riêng cho mỗi installation/device, token có thể gắn với public key đó. Khi thiết bị bị mất, server có thể thu hồi grant/token family gắn với key hoặc device session tương ứng. Đây là cơ chế ràng buộc bằng khóa mật mã; một device ID dạng chuỗi không bí mật không tạo ra sender-constraining.

Không dùng IMEI, advertising ID hoặc fingerprint phần cứng làm yếu tố xác thực. Chúng có thể bị thay đổi, bị hạn chế bởi hệ điều hành, xâm phạm quyền riêng tư và không chứng minh possession của private key.

### 9.3. Khi nào dùng mTLS?

Mutual TLS có thể ràng buộc token với client certificate nhưng thường đòi hỏi quản lý certificate/private key và TLS stack phù hợp. Với app consumer phân phối rộng, quản lý client certificate có thể phức tạp. Nó có thể phù hợp hơn trong môi trường enterprise/managed device có provisioning và lifecycle certificate rõ ràng. DPoP thường là lựa chọn sender-constraining được cân nhắc cho public client khi issuer hỗ trợ.

## 10. Sinh trắc học và khóa thiết bị

Biometric authentication trên mobile có thể giúp bảo vệ việc truy cập local credential hoặc sử dụng private key:
- Yêu cầu Face ID/Touch ID hoặc Android BiometricPrompt trước khi app dùng key/token theo policy.
- Nếu dùng key yêu cầu user authentication, cấu hình thời hạn xác thực và invalidation khi biometric enrollment thay đổi theo threat model.
- Xử lý fallback bằng device passcode theo policy hệ điều hành.
- Không tự thu thập hoặc lưu mẫu sinh trắc học; để hệ điều hành quản lý.
- Không coi kết quả mở khóa local là bằng chứng server đã xác minh người dùng vừa thực hiện một MFA mới, trừ khi giao thức xác thực có cách chứng minh phù hợp.

Sinh trắc học có thể nâng bảo vệ dữ liệu tại thiết bị, nhưng app vẫn cần xử lý token expiry, revoke, refresh rotation và session state ở server.

## 11. State machine cho refresh

Một state machine giúp tránh logic rời rạc giữa API client, UI, background task và logout.

~~~mermaid
stateDiagram-v2
    [*] --> NoSession
    NoSession --> Active: Sign-in succeeds
    Active --> Refreshing: Access token near expiry / expired
    Refreshing --> Active: Refresh succeeds and token state committed
    Refreshing --> RetryPending: Transient failure with safe retry semantics
    RetryPending --> Refreshing: Retry allowed
    Refreshing --> ReauthRequired: invalid_grant / reuse / revoked
    Active --> Revoking: Logout or compromise
    Refreshing --> Revoking: Logout wins
    RetryPending --> Revoking: Logout
    Revoking --> LoggedOut: Local credentials cleared
    ReauthRequired --> NoSession: Credentials cleared
    LoggedOut --> NoSession
~~~

Ý nghĩa các trạng thái:
- **NoSession:** chưa đăng nhập hoặc không còn credential hợp lệ.
- **Active:** có access token usable và refresh token theo policy.
- **Refreshing:** một refresh operation duy nhất đang chạy cho account/issuer.
- **RetryPending:** lỗi tạm thời và issuer cho phép retry an toàn.
- **ReauthRequired:** refresh token hết hạn, revoked, reuse detected hoặc grant không còn hiệu lực.
- **Revoking:** logout/compromise đang chặn request và thu hồi credential.
- **LoggedOut:** token local đã được xóa và phiên ứng dụng đã kết thúc.

Không cho phép response refresh đến muộn chuyển ReauthRequired, Revoking hoặc LoggedOut trở lại Active.

## 12. Logout, revoke và thiết bị bị mất

Logout ở mobile có thể gồm:
1. Chặn API request mới và đánh dấu app session đang kết thúc.
2. Nếu có mạng, gửi refresh token tới revocation endpoint theo RFC 7009 và contract của issuer.
3. Xóa access token cache và refresh token khỏi secure storage.
4. Xóa state tài khoản và dữ liệu nhạy cảm trong memory/cache theo policy.
5. Xóa hoặc vô hiệu hóa device key nếu key chỉ dùng cho session đó.
6. Điều hướng về trạng thái signed-out.
7. Không tuyên bố token đã bị revoke upstream nếu server chưa xác nhận.

Nếu thiết bị offline, app có thể xóa local credential để ngăn app tiếp tục sử dụng. Nhưng token đã bị sao chép hoặc token vẫn tồn tại ở authorization server có thể còn hiệu lực cho tới khi hết hạn/revoke. Nếu cần retry revocation khi có mạng, phải có thiết kế lưu tác vụ an toàn, thời hạn ngắn và quyền truy cập hạn chế; không lưu raw token trong log hoặc queue không bảo vệ.

Khi người dùng báo mất thiết bị:
- Cung cấp khả năng revoke session/token family theo từng thiết bị từ một phiên đã xác thực khác hoặc qua account recovery.
- Thu hồi DPoP key/device binding nếu có.
- Xem xét revoke tất cả session nếu có dấu hiệu account compromise.
- Gửi thông báo qua kênh liên hệ đã xác minh.
- Không phụ thuộc vào việc app được gỡ khỏi thiết bị để kết thúc phiên.

## 13. Pseudocode refresh coordinator

Pseudocode dưới đây thể hiện nguyên tắc. Triển khai thật nên dùng OAuth/OIDC SDK đã được kiểm chứng, secure storage API của nền tảng và contract cụ thể của issuer.

~~~text
getValidAccessToken(accountKey):
    state = loadTokenState(accountKey)

    if state is missing or state.status in [LoggedOut, ReauthRequired]:
        requireSignIn()
    
    if accessTokenIsUsable(state.accessToken, clockSkewAllowance):
        return state.accessToken

    acquireSingleFlightLock(accountKey)
    try:
        latest = reloadTokenState(accountKey)

        if latest.generation != state.generation:
            return latest.accessToken

        if accessTokenIsUsable(latest.accessToken, clockSkewAllowance):
            return latest.accessToken

        markRefreshing(accountKey, latest.generation)

        response = tokenEndpoint.refresh(
            refreshToken=latest.refreshToken,
            clientId=registeredPublicClientId
        )

        if response contains new refresh token:
            nextRefreshToken = response.refreshToken
        else:
            nextRefreshToken = latest.refreshToken

        atomicallyCommitIfGenerationMatches(
            accountKey,
            expectedGeneration=latest.generation,
            accessToken=response.accessToken,
            refreshToken=nextRefreshToken,
            generation=latest.generation + 1,
            status=Active
        )

        return response.accessToken

    catch invalid_grant or reuseDetected:
        markReauthRequired(accountKey)
        clearLocalTokenMaterial(accountKey)
        requireSignIn()

    catch ambiguousNetworkTimeout:
        markRefreshOutcomeUnknown(accountKey)
        followIssuerSpecificRecoveryPolicy()
        doNotBlindlyReplayOldRefreshToken()

    finally:
        releaseSingleFlightLock(accountKey)
~~~

Các yêu cầu quan trọng:
- Lock phải được quản lý cho từng account/issuer, không chỉ theo từng màn hình.
- Token state phải có generation để response cũ không ghi đè response mới.
- Commit access/refresh token phải nhất quán.
- Không log request body, token response hoặc exception có chứa token.
- Không dùng refresh token mới trước khi lưu bền vững thành công.
- Logout phải có quyền ưu tiên cao hơn refresh response đang chạy.

## 14. Bài thực hành: thiết kế Token refresh cho StudyHub Mobile

**Bối cảnh:** StudyHub có app iOS và Android. Người dùng đăng nhập bằng Authorization Code Flow với PKCE qua browser hệ thống. App gọi Course API và Profile API. Access token có thời hạn 10 phút. Authorization server rotation refresh token và phát hiện reuse. Người dùng có thể đăng nhập nhiều tài khoản trên cùng thiết bị và đăng nhập cùng tài khoản trên nhiều thiết bị. App hỗ trợ biometric unlock cho một số người dùng.

Hãy thiết kế token refresh đáp ứng các yêu cầu:

1. Mobile app được đăng ký là public client và không nhúng client secret.
2. Refresh token chỉ được gửi tới token endpoint đã cấu hình qua TLS.
3. Refresh token được lưu trong Keychain hoặc encrypted app storage với key từ Android Keystore.
4. Access token được giữ trong memory/cache ngắn hạn.
5. Refresh coordinator đảm bảo chỉ một refresh request chạy cho mỗi account/issuer.
6. Token rotation được lưu nguyên tử và refresh token cũ không bị dùng lại sau khi đã thay thế.
7. App xử lý timeout mơ hồ mà không blind-retry refresh token cũ.
8. Logout chặn refresh response đến muộn khôi phục session.
9. App có thể revoke token family của một thiết bị khi thiết bị bị mất.
10. API request không bị retry vô hạn hoặc gây tác dụng phụ trùng lặp.
11. Có thể cân nhắc DPoP khi authorization server hỗ trợ.
12. Audit/telemetry không chứa raw token, client secret hoặc private key.

### 14.1. Quyết định thiết kế cần ghi lại

- Issuer, client ID, redirect URI và token endpoint được tin cậy.
- PKCE method, state handling và external user-agent.
- Storage strategy cho iOS/Android, accessibility và backup policy.
- Token state schema: account, issuer, access expiry, refresh token, generation, device key reference.
- Rotation/reuse semantics và hành vi khi issuer không trả refresh token mới.
- Single-flight lock, atomic commit và crash recovery.
- Clock skew allowance và refresh threshold.
- Error classification, retry budget và behavior cho ambiguous timeout.
- Logout/revocation scope: account, device, grant, token family.
- DPoP/device key lifecycle nếu triển khai.
- Log redaction và các metric vận hành.

### 14.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Đăng nhập Authorization Code + PKCE thành công | App nhận token theo redirect transaction đúng; verifier/state được kiểm tra. |
| Client secret bị thêm vào binary | Security review thất bại; native app không dùng secret nhúng. |
| Refresh token gửi tới Course API | Test phát hiện sai đích; API không chấp nhận refresh token. |
| Access token còn hiệu lực | Không refresh không cần thiết. |
| Access token hết hạn | Một refresh operation chạy và request dùng token mới. |
| Nhiều API request đồng thời gặp 401 expiry | Chỉ một refresh request chạy cho account; các request còn lại chờ. |
| Server trả refresh token mới | App lưu token mới nguyên tử và không dùng token cũ. |
| Server không trả refresh token mới | App chỉ giữ token hiện tại nếu issuer contract cho phép. |
| Refresh token cũ bị replay | Server reuse detection áp dụng policy; app chuyển sang re-authentication. |
| Hai account trên cùng thiết bị | Token store và lock tách biệt; không dùng nhầm refresh token. |
| Hai thiết bị cùng account | Revoke một device session không ảnh hưởng thiết bị khác trừ khi policy yêu cầu. |
| Crash trước khi gửi refresh request | Token state cũ vẫn nguyên vẹn và có thể tiếp tục theo policy. |
| Crash sau khi server rotate nhưng trước khi lưu response | App nhận biết outcome không chắc chắn; không blind-retry token cũ. |
| Logout trong lúc refresh | Logout thắng; response tới muộn không khôi phục session. |
| HTTP 429 | Tôn trọng Retry-After và retry có giới hạn. |
| HTTP 5xx sau khi server có thể đã xử lý | Áp dụng semantics retry của issuer; không giả định request chưa commit. |
| invalid_grant | Dừng retry, xóa/đánh dấu token và yêu cầu đăng nhập lại. |
| 403 insufficient_scope | Không refresh lặp để cố lấy thêm quyền. |
| POST nghiệp vụ bị 401 rồi refresh | Chỉ retry khi request semantics/idempotency cho phép. |
| Thiết bị offline khi logout | Local session bị chặn; trạng thái remote revoke không bị tuyên bố thành công nếu chưa xác nhận. |
| Thiết bị bị mất | Phiên/token family hoặc device key được revoke từ kênh quản lý tài khoản. |
| Token trong crash log/analytics | Test bảo mật thất bại; dữ liệu nhạy cảm phải được redact. |
| Refresh token lưu plaintext trong preferences | Security test thất bại. |
| Android backup chứa refresh token | Backup policy phải loại trừ hoặc bảo vệ dữ liệu theo threat model. |
| iOS Keychain sync ngoài policy | Cấu hình phải bị phát hiện và sửa. |
| DPoP key bị thiếu hoặc không khớp | Sender-constrained token request bị từ chối; app yêu cầu recovery/re-auth phù hợp. |
| App bị root/jailbreak | Risk policy được áp dụng; không giả định một tín hiệu duy nhất chứng minh compromise. |
| Token endpoint issuer bị thay đổi qua deep link | App từ chối endpoint không thuộc cấu hình tin cậy. |

### 14.3. Câu hỏi tự đánh giá

1. Vì sao refresh token nhạy cảm hơn access token trong nhiều kiến trúc?
2. Tại sao native app là public client dù binary có obfuscation?
3. PKCE bảo vệ giai đoạn nào và không bảo vệ giai đoạn nào?
4. Refresh token được gửi tới server nào? Vì sao không gửi nó tới resource API?
5. Rotation và reuse detection phối hợp để phát hiện replay ra sao?
6. Vì sao nhiều request refresh đồng thời có thể khiến token family bị revoke?
7. Điều gì xảy ra nếu server đã rotate token nhưng response bị mất?
8. Vì sao không thể blind-retry refresh token cũ sau mọi timeout?
9. Keychain và Android Keystore bảo vệ những phần nào của credential?
10. Biometric unlock local khác với xác thực mới tại authorization server thế nào?
11. DPoP ràng buộc token với key ra sao và giới hạn của nó là gì?
12. Vì sao logout phải thắng refresh response đến muộn?
13. Vì sao 403 insufficient_scope không nên kích hoạt refresh loop?
14. Khi thiết bị bị mất, cần revoke phạm vi nào để không làm ảnh hưởng phiên khác không cần thiết?

**Tiêu chí hoàn thành:** Người học có thể mô tả refresh flow từ mobile app tới authorization server, bảo vệ refresh token trong secure storage, giải thích rotation/reuse detection, xử lý concurrency và timeout mơ hồ, thiết kế logout/revocation theo thiết bị và chứng minh bằng test rằng token cũ không được replay sau khi đã rotate hoặc revoke.

## 15. Vận hành, telemetry và ứng phó sự cố

Theo dõi các chỉ số không chứa secret:
- Tỷ lệ refresh thành công/thất bại theo issuer, app version và platform.
- Tỷ lệ invalid_grant, reuse detection, revoked grant và re-authentication.
- Số refresh operation đồng thời bị chặn bởi coordinator.
- Thời gian từ access token expiry tới refresh completion.
- Số timeout mơ hồ và kết quả recovery.
- Tỷ lệ refresh response có token rotation.
- Tỷ lệ crash hoặc app background/kill giữa refresh và commit storage.
- Tỷ lệ logout local thành công và remote revoke được xác nhận.
- Tỷ lệ request 401/403 sau refresh và số lần retry API.

Audit có thể ghi account reference, issuer, client ID, device/session reference, token family reference không nhạy cảm, thời điểm, app version, platform, error code và kết quả. Không ghi access token, refresh token, ID token, authorization code, PKCE verifier, DPoP private key, cookie hay Authorization header. Nếu cần correlation, dùng identifier nội bộ không thể đổi ngược thành credential.

Khi phát hiện reuse:
1. Xác định token family/device/account reference từ audit an toàn.
2. Revoke family/grant theo policy của authorization server.
3. Thu hồi session liên quan và yêu cầu đăng nhập lại.
4. Đánh giá thiết bị có malware, app tampering hoặc credential exposure không.
5. Kiểm tra API activity trong khoảng token có thể đã bị sử dụng.
6. Thông báo người dùng qua kênh đã xác minh và hướng dẫn bảo vệ tài khoản.
7. Xem xét revoke toàn bộ account session nếu có bằng chứng compromise lan rộng.

Không tự động khóa toàn bộ tài khoản chỉ vì một refresh lỗi mạng. Phân biệt reuse signal đã được issuer xác nhận với timeout hoặc race do client; nhưng cũng không bỏ qua reuse detection vì muốn giảm số lần người dùng phải đăng nhập lại.

## 16. Các lỗi thiết kế phổ biến

- **Nhúng client secret trong app:** secret có thể bị trích xuất; native app phải được xử lý như public client.
- **Lưu refresh token dạng rõ:** tăng khả năng lộ khi backup, file extraction, log hoặc thiết bị bị compromise.
- **Gửi refresh token tới resource API:** mở rộng bề mặt lộ credential và sai mục đích token.
- **Dùng access token như refresh token:** nhầm chức năng, có thể dẫn tới flow không hợp lệ.
- **Refresh mỗi request:** tạo tải không cần thiết và làm tăng nguy cơ rotation race.
- **Không dùng single-flight:** nhiều request cùng refresh token cũ có thể kích hoạt reuse detection.
- **Không lưu token mới nguyên tử:** crash hoặc response đến muộn có thể làm mất token mới hoặc ghi đè state.
- **Blind-retry sau timeout:** server có thể đã rotate token dù response bị mất.
- **Retry mọi 401/403:** tạo loop và không xử lý đúng lỗi authorization.
- **Dùng biometric như bằng chứng server-side:** local unlock không tự tạo một lần xác thực mới với issuer.
- **Dựa vào device ID làm secret:** identifier không chứng minh possession của key.
- **Cho rằng Keystore bảo vệ toàn bộ plaintext:** app process vẫn có thể sử dụng credential khi được cấp quyền.
- **Không revoke khi logout/thiết bị mất:** token bị sao chép có thể tiếp tục được dùng.
- **Log token để debug:** biến log/telemetry thành kho bearer credential.
- **Dùng ID token gọi API:** nhầm assertion OIDC với access token.
- **Không phân tách account/issuer:** có thể gửi token nhầm tenant hoặc nhầm tài khoản.
- **Giả định mọi issuer rotation giống nhau:** client có thể vô tình làm mất token hoặc kích hoạt revoke family.

## 17. Tài liệu tham khảo và hướng đọc tiếp

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** refresh token grant và token endpoint.
- **RFC 8252 — OAuth 2.0 for Native Apps:** public native clients, external user-agent và Authorization Code + PKCE.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh token cho public client, rotation và sender-constrained tokens.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với khóa.
- **OpenID Connect Core:** phân biệt ID token, access token và refresh response.
- **OWASP MASVS:** lưu trữ an toàn, bảo vệ dữ liệu và kiểm thử ứng dụng mobile.
- **OWASP Mobile Application Security Testing Guide:** kiểm thử credential storage, runtime và network behavior.
- **Apple Keychain Services documentation:** lưu trữ credential và accessibility.
- **Android Keystore documentation:** bảo vệ key material và hardware-backed key.

Khi triển khai, cần đọc tài liệu của authorization server và SDK cụ thể vì rotation, reuse detection, grace period, refresh token expiry, DPoP và revocation có thể khác nhau giữa các issuer. Kiểm thử trên thiết bị thật và các phiên bản hệ điều hành được hỗ trợ, bao gồm tình huống app bị background, process bị kill, mất mạng và khôi phục sau crash.

**Kết luận:** Token refresh giúp mobile app duy trì trải nghiệm đăng nhập nhưng refresh token là credential dài hạn có giá trị cao. Thiết kế an toàn cần public-client flow với PKCE, secure storage, rotation/reuse detection, single-flight coordinator, cập nhật token nguyên tử, xử lý timeout mơ hồ, sender-constraining khi phù hợp và revoke đúng phạm vi. Ứng dụng chỉ nên tiếp tục phiên khi trạng thái token được xác minh và lưu bền vững; lỗi refresh không được biến thành vòng lặp retry vô hạn hoặc khôi phục session đã logout.
