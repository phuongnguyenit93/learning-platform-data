# Lỗi Device Flow, PAR, Token Exchange và token binding

Spring Authorization Server có thể xử lý nhiều luồng OAuth 2.0 và cơ chế bảo vệ token, nhưng mỗi luồng có endpoint, tham số, trạng thái và điều kiện xác thực riêng. Khi Device Flow bị treo ở trạng thái chờ, PAR trả invalid_request_uri, Token Exchange từ chối subject_token hoặc resource server báo token binding không hợp lệ, cần xác định lỗi ở đúng ranh giới giao thức trước khi thay đổi cấu hình.

Bài này trình bày cách chẩn đoán theo triệu chứng, OAuth error code, dữ liệu authorization và cấu hình của Spring Authorization Server. Mức hỗ trợ trực tiếp của từng extension phụ thuộc phiên bản thư viện và cách ứng dụng tích hợp. Hãy xác nhận phiên bản đang chạy, endpoint thực tế và converter/provider đã được cấu hình trước khi áp dụng hướng xử lý.

## 1. Thu thập bằng chứng trước khi sửa

Bắt đầu bằng cách xác định request thất bại ở đâu. Các luồng dưới đây có thể đi qua nhiều endpoint; một lỗi tại bước đầu không nhất thiết là lỗi token endpoint.

| Luồng | Điểm bắt đầu thường gặp | Điểm hoàn tất hoặc kiểm tra tiếp |
|---|---|---|
| Device Authorization Grant | Device authorization endpoint | Verification URI, sau đó token endpoint |
| Pushed Authorization Requests (PAR) | PAR endpoint | Authorization endpoint nhận request_uri |
| Token Exchange | Token endpoint với grant type exchange | Token mới, introspection hoặc resource server |
| DPoP token binding | Token endpoint với DPoP proof | Resource request kèm DPoP proof và access token |
| mTLS certificate-bound token | Token endpoint qua TLS client certificate | Resource request qua kết nối có certificate phù hợp |

Thu thập các thông tin sau cho một request lỗi:

- Thời điểm UTC, correlation ID, instance ID và endpoint đã gọi.
- HTTP status, OAuth error và error_description nếu có.
- Client ID, grant type, token type và audience/resource đã yêu cầu.
- Phiên bản Spring Authorization Server, Spring Security và cấu hình endpoint đang triển khai.
- Trạng thái authorization liên quan: pending, approved, denied, expired, consumed hoặc invalidated.
- Kết quả xác minh chữ ký, issuer, audience, thời hạn và key ID khi token là JWT.
- Trạng thái kết nối database, cache dùng chung, KMS/HSM và proxy TLS tại thời điểm xảy ra lỗi.

Không ghi raw device_code, user_code, authorization code, request_uri, subject_token, access token, refresh token, DPoP proof, private key hoặc client secret vào log. Nếu cần đối chiếu hai request, dùng mã tham chiếu nội bộ hoặc fingerprint HMAC được quản lý riêng. Không đưa token vào ticket, ảnh chụp màn hình hoặc lệnh shell được lưu trong lịch sử.

Một quy trình chẩn đoán ngắn:

1. Xác định endpoint và grant type thực tế.
2. Đọc OAuth error code trước khi suy đoán từ HTTP status.
3. Kiểm tra client registration và phương thức xác thực client.
4. Kiểm tra dữ liệu authorization, thời hạn và trạng thái dùng một lần.
5. Kiểm tra issuer, key, clock, proxy và cache khi request đi qua nhiều instance.
6. Tái hiện bằng client kiểm thử và dữ liệu mới, sau đó kiểm tra lại trên instance khác.

## 2. Xác nhận tính năng và cấu hình của phiên bản đang chạy

Không phải mọi phiên bản Spring Authorization Server đều có cùng tập grant type, endpoint hoặc extension. Một dự án cũng có thể triển khai Device Flow, PAR, Token Exchange hoặc token binding bằng module riêng. Trước khi debug, xác định:

- Dependency thực tế được đóng gói và phiên bản Spring Authorization Server.
- Grant type được khai báo trong RegisteredClient.
- Endpoint đã được bật và đường dẫn sau khi áp dụng cấu hình tùy chỉnh.
- AuthenticationConverter và AuthenticationProvider nào xử lý request.
- OAuth2AuthorizationService và OAuth2AuthorizationConsentService nào lưu trạng thái.
- Token generator, JWK source hoặc tích hợp KMS/HSM nào ký token.
- Resource server có xác minh cơ chế binding tương ứng hay chỉ xác minh JWT bearer thông thường.

Nếu request gửi đúng tham số nhưng không có converter/provider tương ứng, server có thể trả unsupported_grant_type, invalid_request hoặc lỗi xác thực tùy điểm request bị dừng. Kiểm tra log khởi động và cấu hình thực tế để xác định extension đã được đăng ký. Đừng chỉ dựa vào việc dependency có mặt trong build file.

## 3. Chẩn đoán Device Authorization Grant

Device Flow phù hợp với thiết bị có hạn chế về bàn phím hoặc trình duyệt. Thiết bị khởi tạo yêu cầu cấp quyền, nhận device_code và user_code, hướng dẫn người dùng mở verification_uri trên thiết bị khác, rồi polling token endpoint cho đến khi người dùng hoàn tất hoặc yêu cầu hết hạn.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant D as Device / Client
    participant AS as Authorization Server
    participant U as User Browser
    D->>AS: POST device authorization
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D->>U: Hiển thị mã và URL
    U->>AS: Mở verification URI, nhập user_code
    AS-->>U: Yêu cầu đăng nhập và xác nhận
    U->>AS: Approve hoặc deny
    loop Theo interval
        D->>AS: POST token với device_code
        AS-->>D: authorization_pending hoặc token/error cuối cùng
    end
~~~

### 3.1 Không nhận được device code

Kiểm tra theo thứ tự:

- Client có được đăng ký với Device Authorization Grant theo cách mà phiên bản và extension của ứng dụng yêu cầu không?
- Device authorization endpoint có được bật và URL client gọi có đúng với discovery/configuration không?
- Client authentication có phù hợp với loại client không? Nếu là confidential client, xác minh client ID, secret hoặc phương thức xác thực đã đăng ký.
- Request có gửi tham số bắt buộc, content type và scope hợp lệ không?
- Database/cache lưu device authorization có sẵn sàng không?
- Server có tạo được device_code, user_code, verification_uri và thời hạn không?

Nếu nhận unauthorized_client, thường cần kiểm tra grant type được phép cho client. Nếu nhận invalid_client, kiểm tra xác thực client. Nếu nhận invalid_scope, so sánh scope yêu cầu với scope được đăng ký và chính sách cấp quyền. Nếu server trả 404, kiểm tra endpoint có thực sự được cấu hình hay request đang đi nhầm service/proxy.

### 3.2 Người dùng nhập user code nhưng thiết bị vẫn pending

authorization_pending là trạng thái chờ hợp lệ: thiết bị chưa được phép nhận token vì người dùng chưa hoàn tất phê duyệt hoặc thay đổi trạng thái chưa được nhìn thấy. Hãy kiểm tra:

- Người dùng đã đăng nhập đúng tài khoản và hoàn tất thao tác approve chưa?
- user_code nhập vào có khớp với yêu cầu đang chờ, còn hạn và chưa bị sử dụng không?
- Verification UI có cập nhật đúng authorization record không?
- Instance nhận thao tác approve có ghi vào kho dùng chung mà token endpoint đang đọc không?
- Có replica lag hoặc cache cục bộ khiến node polling nhìn thấy trạng thái cũ không?
- Client có đang polling nhầm device_code từ một phiên yêu cầu khác không?

Nếu người dùng đã approve nhưng trạng thái vẫn pending, truy vết cùng authorization ID nội bộ từ bước tạo code tới bước approve và polling. Kiểm tra transaction commit và việc các node đọc cùng một nguồn dữ liệu. Không sửa bằng cách giảm interval polling; điều đó chỉ làm tăng tải.

### 3.3 Polling quá nhanh hoặc trả slow_down

Client phải tôn trọng interval mà server trả về. Nếu response không có interval, client dùng mặc định 5 giây theo Device Authorization Grant. Khi nhận slow_down, client tăng interval thêm 5 giây cho các lần polling tiếp theo, thay vì tiếp tục polling với tốc độ cũ.

Các lỗi thường gặp:

- Nhiều thread hoặc nhiều process cùng polling một device code.
- Retry HTTP tự động làm tăng tần suất request ngoài ý muốn.
- Client bỏ qua interval trả về từ device authorization endpoint.
- Client không tăng thời gian chờ sau slow_down.
- Clock hoặc scheduler của thiết bị gây nhịp polling không ổn định.

Phân biệt authorization_pending, slow_down, access_denied và expired_token:

| OAuth error | Ý nghĩa | Hành vi client |
|---|---|---|
| authorization_pending | Người dùng chưa hoàn tất | Chờ theo interval rồi thử lại |
| slow_down | Polling nhanh hơn mức cho phép | Tăng interval theo giao thức |
| access_denied | Người dùng từ chối | Dừng polling và báo kết quả |
| expired_token | Device code đã hết hạn | Dừng yêu cầu cũ và bắt đầu luồng mới |

Client không nên polling mãi sau lỗi cuối cùng. Khi người dùng từ chối hoặc code hết hạn, xóa trạng thái tạm tương ứng và yêu cầu người dùng bắt đầu phiên cấp quyền mới.

### 3.4 User code không hợp lệ hoặc bị nhầm phiên

Kiểm tra cách hiển thị và nhập mã: chữ hoa/thường, ký tự dễ nhầm, dấu phân cách, khoảng trắng đầu/cuối và quy tắc chuẩn hóa. Mã cần đủ entropy và không để lộ thông tin nhận diện người dùng. Không tự thay đổi user_code sau khi đã hiển thị nếu không cập nhật bản ghi tương ứng.

Nếu một user code được nhập nhiều lần, server phải áp dụng chính sách hết hạn, giới hạn lần thử và chống dò mã. Verification UI nên hiển thị kết quả chung, tránh tiết lộ một mã có thuộc về tài khoản cụ thể hay không. Sau khi approve hoặc deny, kiểm tra code không thể được dùng để thay đổi quyết định lần nữa.

## 4. Chẩn đoán Pushed Authorization Requests (PAR)

PAR cho phép client gửi authorization parameters trực tiếp tới PAR endpoint trước. Authorization Server lưu request và trả về một request_uri ngắn hạn. Client chuyển trình duyệt tới authorization endpoint bằng client_id và request_uri, thay vì đưa toàn bộ tham số authorization lên URL của trình duyệt.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant B as User Browser
    C->>AS: POST PAR với authorization parameters
    AS-->>C: request_uri, expires_in
    C->>B: Authorization endpoint với client_id và request_uri
    B->>AS: GET authorization request
    AS->>AS: Tra cứu và xác minh request đã push
    AS-->>B: Tiếp tục login / consent
~~~

### 4.1 PAR endpoint trả 404 hoặc unsupported request

- Kiểm tra phiên bản thư viện và việc PAR endpoint đã được hỗ trợ/bật trong cấu hình.
- Đối chiếu URL thực tế với endpoint đã cấu hình; không mặc định đường dẫn của mọi phiên bản hoặc ứng dụng đều giống nhau.
- Kiểm tra reverse proxy có route đúng method POST và path không.
- Kiểm tra cấu hình issuer, base URL, context path và forwarded headers.
- Xác minh request đang đến Authorization Server, không phải resource server hoặc gateway khác.

Nếu extension PAR được triển khai riêng, xác minh filter/endpoint đã được gắn vào filter chain đúng và không bị một security chain khác bắt request trước.

### 4.2 PAR trả invalid_client hoặc unauthorized_client

Kiểm tra client authentication tại PAR endpoint. Đối chiếu client_id, phương thức xác thực được đăng ký và credential đang dùng. Một client có thể xác thực được ở token endpoint nhưng thất bại ở PAR nếu cấu hình endpoint hoặc filter chain áp dụng quy tắc khác.

Không giả định mọi loại client đều được dùng PAR theo cùng chính sách. Kiểm tra yêu cầu của giao thức, chính sách triển khai và cấu hình client cụ thể. Với private key JWT hoặc mTLS, xác minh audience của client assertion, thời hạn assertion, certificate chain và thông tin client được ánh xạ đúng.

### 4.3 Authorization endpoint trả invalid_request_uri

Các nguyên nhân thường gặp:

- request_uri bị cắt, encode sai hoặc client gửi nhầm giá trị.
- Request URI đã hết hạn trước khi người dùng mở trang authorization.
- URI được tạo bởi issuer hoặc môi trường khác.
- PAR record không được lưu bền vững hoặc instance khác không đọc được.
- Request URI không còn hợp lệ theo chính sách sử dụng/replay của server.
- client_id trong authorization request không khớp client gắn với pushed request.
- Client gửi thêm authorization parameters xung đột với nội dung đã push.

Kiểm tra thời điểm PAR được tạo, expires_in, thời điểm authorization request đến và client ID gắn với bản ghi. Dùng correlation ID hoặc request reference nội bộ để đối chiếu; không ghi toàn bộ request URI ra log vì URI có thể cho phép truy cập dữ liệu authorization đang chờ.

### 4.4 PAR được tạo thành công nhưng tham số authorization bị sai

So sánh các tham số client gửi tới PAR endpoint với dữ liệu mà Authorization Server lưu và dùng khi xử lý authorization request. Các trường cần kiểm tra gồm response_type, redirect_uri, scope, state, nonce, code_challenge, code_challenge_method, resource, prompt và max_age nếu được hỗ trợ.

Một số lỗi điển hình:

- redirect_uri không khớp chính xác giá trị đã đăng ký.
- PKCE challenge bị mất hoặc method không được phép.
- scope vượt quyền client được cấp.
- response_type không được client hỗ trợ.
- Authorization request truyền đồng thời request_uri và tham số trùng lặp không được phép.
- request_uri được tạo cho client A nhưng authorization request lại khai báo client B.

Nếu PAR được lưu trong database, kiểm tra TTL và cơ chế dọn bản ghi hết hạn. Nếu dùng cache, mọi instance phải tra cứu được cùng request URI trong thời gian hiệu lực. Kiểm thử cả trường hợp client gửi URI hết hạn và URI đã bị sử dụng theo chính sách server.

## 5. Chẩn đoán OAuth 2.0 Token Exchange

Token Exchange cho phép một client yêu cầu Authorization Server đổi một token đầu vào thành token khác có phạm vi, audience hoặc ngữ cảnh đại diện khác. Grant type chuẩn là:

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

Một request thường có subject_token, subject_token_type và có thể có actor_token, actor_token_type, requested_token_type, audience, resource hoặc scope, tùy chính sách server.

Ví dụ dạng request minh họa:

~~~http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<input-token>
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=https%3A%2F%2Fapi.example.test
&scope=orders.read
~~~

Không dùng token thật trong tài liệu, log hoặc shell history. Request trên chỉ mô tả cấu trúc tham số.

### 5.1 unsupported_grant_type hoặc unauthorized_client

unsupported_grant_type cho biết token endpoint không nhận grant type được gửi hoặc extension chưa được đăng ký đúng. unauthorized_client thường cho biết client đã xác thực nhưng không được phép sử dụng grant type đó.

Kiểm tra:

- RegisteredClient có grant type token exchange theo cách ứng dụng đăng ký không?
- Phiên bản Spring Authorization Server đang chạy có hỗ trợ tích hợp trực tiếp không, hay ứng dụng cần extension riêng?
- Authentication converter có nhận diện đúng grant type?
- Authentication provider tương ứng đã được đăng ký trong token endpoint chưa?
- Provider có được gọi sau khi client authentication thành công không?
- Client có được phép exchange token cho audience/resource và scope đang yêu cầu không?

Nếu dùng custom grant, kiểm tra thứ tự converter/provider và việc extension có vô tình chặn các grant type khác hay không. Một provider chỉ nên nhận loại Authentication mà nó hỗ trợ; request không thuộc phạm vi phải được chuyển cho provider phù hợp hoặc trả lỗi OAuth2 rõ ràng.

### 5.2 invalid_grant khi subject_token không được chấp nhận

Kiểm tra token đầu vào theo đúng loại subject_token_type:

- Token có đúng issuer và chữ ký hợp lệ không?
- Token còn hạn và chưa bị revoke không?
- Audience có phù hợp với mục đích exchange không?
- Token có đúng loại và đúng mục đích sử dụng không?
- Token có bị nhầm với authorization code, refresh token hoặc ID Token không?
- Nếu token opaque, server có thể introspect hoặc tra cứu trạng thái ở nguồn tin cậy không?
- Nếu token được phát hành bởi issuer khác, trust relationship có cho phép issuer đó không?

Không chấp nhận JWT chỉ vì parse được header và payload. Phải xác minh chữ ký, issuer, audience, thời hạn và các claim cần thiết. Với opaque token, không thể kiểm tra claim bằng cách decode; cần introspection hoặc cơ chế tra cứu tin cậy.

invalid_grant cũng có thể xuất hiện khi subject token đã hết hạn, không còn active, không thuộc chủ thể được phép hoặc không đáp ứng chính sách delegation. Ghi reason code nội bộ để phân biệt các trường hợp này mà không tiết lộ chi tiết nhạy cảm cho client.

### 5.3 Token được cấp nhưng audience hoặc scope sai

Token exchange cần thực thi chính sách downscoping và delegation. Kiểm tra audience/resource mà client yêu cầu, quyền của subject token, quyền của actor (nếu có), scope được client cho phép và chính sách của resource server đích.

Không cho phép client tự chọn tùy ý audience hoặc nâng scope vượt quyền của subject. Nếu yêu cầu orders.read nhưng token nguồn chỉ có profile, server cần từ chối hoặc cấp token bị giới hạn theo chính sách; không tự động cấp quyền cao hơn chỉ vì client đã xác thực.

Khi token response thành công nhưng resource server trả 401/403, kiểm tra:

- aud của token mới có khớp resource server không?
- scope hoặc authority có được map đúng sang quyền endpoint không?
- iss, kid, chữ ký và thời hạn có hợp lệ không?
- Token có phải loại mà resource server chấp nhận không?
- Resource server có đang nhận token nguồn thay vì token đã exchange không?

### 5.4 Actor token và delegation chain

Nếu request có actor_token, kiểm tra token actor, actor type, issuer, audience và quyền đại diện. Phải xác định actor đang hành động thay mặt subject theo quan hệ nào, có được phép delegate hay không và có giới hạn chiều sâu delegation chain không.

Không chỉ xác minh chữ ký actor token rồi mặc định actor được quyền đại diện cho subject. Cần chính sách liên kết subject, actor, client và resource. Token mới nên mang thông tin delegation phù hợp, chẳng hạn claim actor theo profile được triển khai, và resource server phải hiểu đúng ý nghĩa claim đó.

## 6. Chẩn đoán DPoP token binding

DPoP (Demonstrating Proof of Possession) ràng buộc access token với một cặp khóa của client. Client gửi DPoP proof JWT trong header DPoP; access token có thể chứa confirmation claim cnf với thumbprint khóa công khai. Khi gọi resource server, client phải chứng minh đang sở hữu private key tương ứng.

Các thành phần thường được kiểm tra trong DPoP proof:

- Header typ có giá trị dpop+jwt.
- alg là thuật toán bất đối xứng được server cho phép; không chấp nhận none hoặc thuật toán đối xứng không phù hợp.
- Header jwk chứa public key, không chứa private key.
- Claim htm khớp HTTP method.
- Claim htu khớp URI đích theo quy tắc chuẩn hóa của DPoP; query và fragment không thuộc giá trị htu.
- Claim iat nằm trong cửa sổ thời gian cho phép.
- Claim jti duy nhất và chưa bị replay.
- Claim nonce đúng nếu server yêu cầu nonce.
- Khi truy cập resource bằng access token, claim ath ràng buộc proof với chính access token đó.

Nếu server trả use_dpop_nonce, client cần lấy nonce theo cơ chế của server và tạo proof mới. Không tái sử dụng proof cũ vì jti, thời gian hoặc nonce có thể không còn hợp lệ.

### 6.1 invalid_dpop_proof

Kiểm tra từng thành phần của proof:

| Thành phần | Lỗi thường gặp | Cách kiểm tra |
|---|---|---|
| typ | Không phải dpop+jwt | Kiểm tra protected header |
| alg | Thuật toán bị từ chối | So sánh với allowlist |
| jwk | Thiếu public key hoặc chứa private material | Chỉ công bố thành phần public |
| htm | Sai method, ví dụ proof tạo cho GET nhưng request là POST | So sánh method thực tế |
| htu | Khác scheme/host/path hoặc chuẩn hóa sai | Kiểm tra URI đích nhìn từ server |
| iat | Proof quá cũ hoặc clock lệch | Đồng bộ NTP và kiểm tra time window |
| jti | Trùng hoặc đã dùng | Kiểm tra replay cache |
| nonce | Thiếu hoặc không khớp nonce server | Lấy nonce mới và ký proof mới |
| ath | Không ràng buộc đúng access token | Tính hash theo chuẩn và token đang gửi |

Sau TLS termination ở reverse proxy, server có thể nhìn thấy scheme/host nội bộ thay vì URI public. Khi đó việc so sánh htu có thể thất bại. Cấu hình forwarded headers và trusted proxy phải chính xác; chỉ tin header do proxy đáng tin cậy ghi. Không chấp nhận X-Forwarded-Host hoặc X-Forwarded-Proto do client bên ngoài tự gửi nếu chúng chưa được proxy kiểm soát.

### 6.2 Token DPoP bị resource server từ chối

Kiểm tra token response có token type DPoP theo cấu hình hay không và access token có chứa cnf.jkt tương ứng với public key trong proof không. Resource request phải gửi đúng authorization scheme và DPoP proof header theo profile DPoP. Nếu gửi token DPoP như Bearer hoặc thiếu proof, resource server có thể từ chối.

Với mỗi request tới resource server, proof cần khớp method và URI đích. Khi có access token, proof phải ràng buộc với token đó bằng ath. Nếu client đổi khóa nhưng vẫn dùng access token đã ràng buộc với khóa cũ, thumbprint không khớp và token phải bị từ chối; client cần lấy token mới bằng khóa phù hợp.

### 6.3 Replay cache không dùng chung giữa các instance

DPoP proof sử dụng jti để nhận diện proof. Nếu mỗi node có replay cache riêng, cùng một proof có thể được gửi tới A rồi B mà cả hai node đều chưa thấy jti. Với triển khai nhiều instance, cần cơ chế replay detection có tính nhất quán phù hợp, thường dùng kho cache dùng chung với TTL theo cửa sổ chấp nhận proof.

Kiểm thử bằng cách gửi cùng một proof tới hai instance trong khoảng thời gian hợp lệ. Kết quả mong đợi là proof chỉ được chấp nhận một lần theo chính sách replay. Cũng kiểm tra cache outage: nếu không thể xác minh replay an toàn, hệ thống cần áp dụng fail-closed hoặc chính sách đã được đánh giá rủi ro, không âm thầm bỏ qua kiểm tra.

## 7. Chẩn đoán mTLS certificate-bound access token

mTLS-bound access token gắn token với chứng thư client. Resource server kiểm tra certificate được dùng trên kết nối TLS có thumbprint khớp claim cnf.x5t#S256 trong token hay không.

Kiểm tra các điểm sau:

- Client có gửi certificate đúng trong TLS handshake không?
- Certificate có hợp lệ, còn hạn và được chain tới CA tin cậy không?
- Authorization Server có nhận diện đúng certificate và ánh xạ nó tới client không?
- Token có chứa thumbprint certificate dự kiến không?
- Resource server có nhận được certificate của cùng client trên request không?
- Reverse proxy/load balancer có kết thúc TLS và chuyển thông tin certificate theo kênh được bảo vệ không?
- Certificate có bị đổi mới hoặc thay thế sau khi token được cấp không?

Một lỗi thường gặp là TLS kết thúc tại load balancer, khiến Authorization Server hoặc resource server không nhìn thấy client certificate ban đầu. Nếu proxy chuyển certificate qua header, phải xóa header do client tự gửi ở biên tin cậy và chỉ chấp nhận giá trị được proxy xác thực, ký hoặc truyền qua kênh nội bộ được bảo vệ. Không tin trực tiếp header như X-Client-Cert từ Internet.

Khi certificate được gia hạn và thumbprint thay đổi, token cũ vẫn gắn với thumbprint cũ. Client cần được cấp token mới gắn với certificate mới theo chính sách. Không sửa claim token cũ hoặc bỏ qua certificate check để khắc phục nhanh.

DPoP và mTLS là hai cơ chế proof-of-possession khác nhau. DPoP chứng minh quyền sở hữu khóa bằng proof JWT ở tầng HTTP; mTLS dựa trên client certificate ở tầng TLS. Không dùng cấu hình hoặc kiểm thử của một cơ chế để kết luận cơ chế kia đã hoạt động.

## 8. Các lỗi cấu hình xuyên suốt nhiều luồng

Một số lỗi xuất hiện ở nhiều grant type và extension:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| invalid_client | Client secret, assertion, certificate hoặc auth method không đúng | Đối chiếu RegisteredClient và phương thức xác thực |
| unauthorized_client | Client không được phép dùng grant/endpoint | Kiểm tra grant type và policy |
| unsupported_grant_type | Grant chưa được hỗ trợ hoặc provider chưa đăng ký | Kiểm tra version, converter/provider và token endpoint |
| invalid_scope | Scope không được client/resource cho phép | So sánh requested scope với policy |
| invalid_request | Thiếu tham số, tham số trùng hoặc sai định dạng | Kiểm tra form/body và quy tắc endpoint |
| invalid_grant | Credential hết hạn, đã dùng, bị revoke hoặc không hợp lệ | Kiểm tra authorization state và token validation |
| invalid_token | Chữ ký, issuer, audience, thời hạn hoặc binding không hợp lệ | Kiểm tra token và resource server |
| 401/403 ở resource server | Thiếu authority, audience hoặc proof-of-possession | Kiểm tra claim và cơ chế xác minh |

Kiểm tra thêm các yếu tố sau:

- **Issuer và discovery**: issuer phải thống nhất giữa token, metadata, PAR request, resource server và các node.
- **Clock skew**: đồng bộ thời gian giữa client, Authorization Server, KMS và resource server; kiểm tra iat, exp, nbf và nonce TTL.
- **JWKS cache**: public key mới cần được công bố và resource server cần làm mới cache theo chính sách.
- **Client configuration**: grant type, authentication method, redirect URI, scope và token settings phải giống nhau giữa các môi trường.
- **Reverse proxy**: scheme, host, port, path và client certificate forwarding phải phản ánh đúng kết nối public.
- **Shared state**: device authorization, PAR request URI, replay cache, authorization và consent phải có nguồn lưu trữ dùng chung nếu request có thể tới nhiều instance.
- **Transaction boundary**: trạng thái phải được commit trước khi server trả kết quả thành công; lỗi lưu trữ không được biến thành token response thành công giả.

## 9. Ma trận tái hiện lỗi và xác nhận bản sửa

Sau khi xác định nguyên nhân, tạo một test có thể tái hiện trước khi thay đổi cấu hình. Mỗi test nên dùng client và token riêng, thời gian được kiểm soát và một correlation ID.

| Nhóm | Tái hiện lỗi | Tiêu chí đạt sau khi sửa |
|---|---|---|
| Device Flow | Poll trước interval, nhập user code sai, approve sau khi code hết hạn | Client tôn trọng interval; trạng thái pending/denied/expired chính xác |
| Device Flow multi-node | Tạo code ở A, approve ở B, poll ở A | Các node thấy cùng trạng thái authorization |
| PAR | Dùng request URI hết hạn, sai client ID hoặc URI bị sửa | Request không hợp lệ bị từ chối đúng OAuth error |
| PAR multi-node | Tạo PAR ở A, mở authorization endpoint ở B | B đọc được pushed request còn hiệu lực |
| Token Exchange | Dùng subject token sai issuer/audience/expiry hoặc scope vượt quyền | Server từ chối hoặc downscope theo policy |
| Token Exchange delegation | Actor không có quyền đại diện subject | Exchange bị từ chối và không phát hành token vượt quyền |
| DPoP | Sai htm, htu, ath, nonce hoặc replay jti | Proof không hợp lệ bị từ chối |
| DPoP multi-node | Gửi cùng proof tới A và B | Replay bị phát hiện xuyên node |
| mTLS | Thiếu certificate, certificate sai hoặc certificate đã đổi | Token binding được kiểm tra theo thumbprint |
| JWKS rotation | Token dùng key mới nhưng resource server giữ cache cũ | Key được làm mới theo cơ chế đã cấu hình và token hợp lệ được xác minh |

Một bản sửa chỉ hoàn thành khi kiểm thử cả đường thành công lẫn đường thất bại. Không chỉ xác nhận request lỗi đã chuyển từ 400 sang 200; phải kiểm tra token được cấp có đúng subject, audience, scope, thời hạn và binding hay không. Với lỗi replay hoặc dùng một lần, cần chạy lại test đồng thời và xuyên instance.

## 10. Quy trình xử lý sự cố trong production

Khi xảy ra sự cố thực tế:

1. Xác định luồng, endpoint, client và instance gây lỗi; ghi lại thời điểm và correlation ID.
2. Lấy OAuth error code và HTTP status; so sánh với log của endpoint liên quan.
3. Kiểm tra client authentication, RegisteredClient, grant type và policy.
4. Kiểm tra authorization state, TTL, consent, request URI hoặc token metadata bằng ID nội bộ.
5. Kiểm tra database, cache dùng chung, clock, JWKS, KMS/HSM và reverse proxy.
6. Tái hiện trên môi trường kiểm thử với dữ liệu mới; không dùng credential của người dùng thật.
7. Triển khai bản sửa có phạm vi nhỏ, xác minh các grant type khác không bị ảnh hưởng.
8. Theo dõi tỷ lệ lỗi, token exchange thành công, device polling, PAR expiry, DPoP rejection và mTLS binding failure sau khi sửa.

Nếu có dấu hiệu token hoặc khóa bị lộ, chuyển sang quy trình incident response tương ứng. Không bật log toàn bộ request body hoặc tắt xác minh chữ ký, audience, nonce, replay, certificate hay token binding để làm cho request đi qua. Các biện pháp đó có thể che lỗi nhưng làm mất ranh giới bảo mật mà luồng đang cần bảo vệ.

Một báo cáo sự cố hữu ích cần nêu triệu chứng, OAuth error, phạm vi client/instance bị ảnh hưởng, nguyên nhân gốc, thay đổi đã áp dụng, test tái hiện trước/sau và giới hạn còn lại. Chỉ dùng fingerprint hoặc ID nội bộ để liên kết token và authorization; không đính kèm giá trị credential.

Khi chẩn đoán theo endpoint, error code, trạng thái lưu trữ và cơ chế xác minh tương ứng, đội phát triển có thể phân biệt lỗi giao thức với lỗi tích hợp Spring, lỗi đồng bộ nhiều instance và lỗi cấu hình proxy/khóa. Điều này giúp sửa đúng điểm gây lỗi mà vẫn giữ nguyên các kiểm tra bảo mật của OAuth 2.0/OpenID Connect.

