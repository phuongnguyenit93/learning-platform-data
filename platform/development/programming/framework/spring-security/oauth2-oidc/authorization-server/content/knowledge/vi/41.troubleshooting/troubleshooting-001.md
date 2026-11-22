# invalid_client: secret, authentication method, assertion và chứng thư

Lỗi invalid_client xuất hiện khi Authorization Server không xác thực được OAuth2 client tại endpoint đang xử lý request. Nguyên nhân có thể là client ID không tồn tại, client secret sai hoặc hết hạn, phương thức xác thực không khớp với cấu hình đăng ký, JWT client assertion không hợp lệ, hoặc chứng thư TLS không được tin cậy. Các nguyên nhân này có cách kiểm tra khác nhau; thay secret liên tục hoặc chuyển mọi client sang một authentication method khác thường làm che khuất lỗi gốc.

Với Spring Authorization Server, việc xác thực client gắn với RegisteredClient, ClientAuthenticationMethod và các AuthenticationConverter/AuthenticationProvider xử lý endpoint. Bài này hướng dẫn xác định phương thức client đang dùng, kiểm tra credential và cấu hình tương ứng, sau đó xác minh lại bằng request kiểm thử an toàn.

## 1. Hiểu đúng invalid_client

OAuth2 client authentication xác minh ứng dụng đang gọi Authorization Server. Đây là danh tính của client, tách biệt với danh tính người dùng cuối. Ví dụ, người dùng có thể đăng nhập thành công nhưng token request vẫn bị từ chối vì client gửi secret sai.

Phân biệt các lỗi thường gặp:

| Lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| invalid_client | Client không được xác thực bằng phương thức đã gửi | Client ID, secret, assertion, certificate và RegisteredClient |
| unauthorized_client | Client đã xác thực nhưng không được phép dùng grant hoặc thao tác | Grant type và policy của client |
| unsupported_grant_type | Token endpoint không hỗ trợ grant type được gửi | Phiên bản, extension và cấu hình provider |
| invalid_grant | Authorization code, refresh token hoặc grant liên quan không hợp lệ | Trạng thái authorization và token |
| invalid_scope | Scope yêu cầu không được phép | Scope đăng ký và policy cấp quyền |
| invalid_request | Request thiếu hoặc sai tham số giao thức | Content-Type, tham số và encoding |

Tại token endpoint, nếu client gửi HTTP authentication scheme như Basic và xác thực thất bại, response thường là HTTP 401 kèm WWW-Authenticate. Với các phương thức khác, status và cách biểu diễn lỗi phụ thuộc endpoint và implementation. Hãy đọc cả HTTP status lẫn OAuth error body; không kết luận chỉ từ status code.

Một số dấu hiệu giúp định vị nhanh:

- Lỗi xảy ra trước khi Authorization Server xử lý grant: tập trung vào client authentication.
- Client đăng nhập được nhưng không được dùng grant: kiểm tra unauthorized_client và RegisteredClient grant types.
- Client xác thực được nhưng authorization code không hợp lệ: kiểm tra invalid_grant và authorization state.
- Chỉ một node bị lỗi: kiểm tra cấu hình client, secret version, cache và key material giữa các instance.
- Chỉ xảy ra sau khi rotate secret hoặc certificate: kiểm tra thời điểm chuyển đổi và trạng thái credential cũ/mới.

## 2. Xác định authentication method đã đăng ký

Spring Authorization Server biểu diễn phương thức xác thực client bằng ClientAuthenticationMethod trong RegisteredClient. Những giá trị thường gặp gồm:

| Method | Credential được gửi | Cơ chế xác minh |
|---|---|---|
| client_secret_basic | client ID và secret trong HTTP Basic Authorization header | So sánh secret với giá trị đã lưu |
| client_secret_post | client ID và secret trong form body | So sánh secret với giá trị đã lưu |
| client_secret_jwt | JWT assertion ký bằng shared secret | Xác minh chữ ký HMAC và claim assertion |
| private_key_jwt | JWT assertion ký bằng private key của client | Xác minh chữ ký bằng public key đã đăng ký |
| tls_client_auth | Client certificate trong TLS handshake | Xác minh chain và thuộc tính certificate đã đăng ký |
| self_signed_tls_client_auth | Certificate tự ký trong TLS handshake | Đối chiếu certificate/thumbprint đã đăng ký |
| none | Không có client secret, thường dành cho public client | Áp dụng PKCE và các ràng buộc dành cho public client |

Tên method và khả năng hỗ trợ cụ thể cần đối chiếu với phiên bản Spring Authorization Server và extension của ứng dụng. Không mặc định mọi endpoint hoặc mọi phiên bản đều bật tất cả các method trong bảng.

Trước khi kiểm tra credential, xác định client ID nào đang gọi, endpoint nào nhận request và method client thực sự gửi. Một client đăng ký client_secret_basic nhưng gửi client_secret_post sẽ không được xác thực chỉ vì secret có giá trị đúng. Các method không thể hoán đổi tùy ý.

Ví dụ đăng ký confidential client dùng client_secret_basic:

~~~java
PasswordEncoder passwordEncoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String encodedSecret = passwordEncoder.encode(rawClientSecret);

RegisteredClient client = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientSecret(encodedSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.test/callback")
        .scope("openid")
        .scope("profile")
        .build();
~~~

Ví dụ trên minh họa cách lưu secret đã encode bằng PasswordEncoder. Trong ứng dụng thực tế, lấy rawClientSecret từ secret manager tại thời điểm tạo/cấp credential; không lưu raw secret trong source code, file cấu hình công khai hoặc log. Nếu dùng JDBC, xác minh bản ghi RegisteredClient được lưu và đọc lại đúng giá trị encoded.

Có thể cho một client hỗ trợ nhiều authentication method nếu policy và implementation cho phép, nhưng cần kiểm tra method được dùng ở mỗi request. Không thêm hàng loạt method chỉ để làm lỗi biến mất; điều đó có thể mở rộng bề mặt xác thực ngoài dự kiến.

## 3. Chẩn đoán client_secret_basic

Với client_secret_basic, client gửi client ID và secret trong Authorization header theo HTTP Basic. Các lỗi thường gặp đến từ encoding, header bị proxy thay đổi, secret không khớp hoặc server đang đăng ký method khác.

### 3.1 Kiểm tra request

Request token endpoint thường có dạng:

~~~http
POST /oauth2/token
Authorization: Basic <base64-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&scope=orders.read
~~~

Trong Basic authentication theo OAuth 2.0, client ID và client secret cần được form-url-encode riêng trước khi ghép thành cặp username/password và mã hóa Base64 theo quy tắc giao thức. Các thư viện OAuth client thường xử lý việc này. Nếu tự tạo header, ký tự đặc biệt như dấu hai chấm, dấu cộng, dấu phần trăm hoặc ký tự Unicode có thể khiến server giải mã khác với giá trị dự kiến.

Kiểm tra:

- Client ID có đúng chính xác, kể cả chữ hoa/thường không?
- Secret được lấy từ đúng môi trường và đúng phiên bản credential không?
- Thư viện client có tự tạo Basic header hay ứng dụng tự ghép chuỗi?
- Client ID/secret có được encode theo đúng quy tắc trước khi Base64 không?
- Header Authorization có bị reverse proxy, API gateway hoặc filter xóa/thay thế không?
- Request có gửi đồng thời Basic header và client_id/client_secret trong body gây xung đột không?
- Content-Type của token request có phải application/x-www-form-urlencoded không?

Không giải mã và in Basic header ra log để debug. Nếu cần so sánh, xác minh fingerprint của secret trong secret manager hoặc dùng một thao tác xác thực có kiểm soát.

### 3.2 Kiểm tra secret đã lưu

Với PasswordEncoder, RegisteredClient thường lưu secret đã encode thay vì plaintext. Xác minh:

- Giá trị lưu có prefix phù hợp với DelegatingPasswordEncoder nếu đang dùng encoder này.
- Encoder được dùng khi tạo client tương thích với encoder lúc xác thực.
- Secret chưa hết hạn theo clientSecretExpiresAt hoặc policy riêng.
- Secret không bị ghi đè bởi migration, seed data hoặc deployment script.
- Tất cả instance đọc cùng RegisteredClient record và cùng encoder configuration.

Nếu secret được tạo bởi BCrypt nhưng server lại so sánh theo một encoder khác, xác thực sẽ thất bại dù người vận hành đang dùng đúng raw secret. Không so sánh trực tiếp raw secret với chuỗi encoded trong database và không chuyển sang plaintext chỉ để xử lý lỗi.

### 3.3 Lỗi do secret có ký tự đặc biệt

Trường hợp secret chứa ký tự đặc biệt thường lỗi khi client tự tạo Basic header. Dùng OAuth client library đã được kiểm thử thay vì tự nối clientId + ":" + secret. Nếu bắt buộc tự triển khai, viết unit test cho các giá trị chứa colon, plus, percent, spaces và Unicode, rồi đối chiếu kết quả với implementation server.

Không gửi secret trong URL query string. Query string thường xuất hiện trong access log, proxy log, browser history và hệ thống tracing.

## 4. Chẩn đoán client_secret_post

Với client_secret_post, client gửi client_id và client_secret trong form body của token request. Đây là method riêng; server phải cho phép method này trong cấu hình client. OAuth 2.0 khuyến nghị HTTP Basic khi có thể sử dụng, bởi credential trong body dễ bị ghi lại bởi middleware hoặc request logging.

Ví dụ cấu trúc request:

~~~http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=service-worker
&client_secret=<secret>
&scope=jobs.read
~~~

Kiểm tra:

- RegisteredClient có đăng ký CLIENT_SECRET_POST không?
- Client có đang gửi body dưới dạng form-urlencoded thay vì JSON không?
- client_id và client_secret có xuất hiện đúng một lần không?
- Framework HTTP client có encode các giá trị form đúng cách không?
- Reverse proxy, WAF hoặc request wrapper có loại bỏ trường secret không?
- Có filter nào đọc request body trước token endpoint và không cho phép đọc lại không?
- Server có vô tình nhận cả Basic header lẫn body credentials không?

Nếu ứng dụng dùng request logging, phải che client_secret trước khi ghi body. Không bật log body toàn cục ở token endpoint trong production.

Nếu client dùng Basic trong khi RegisteredClient chỉ cho phép POST, hãy sửa method tại một đầu theo policy đã thống nhất. Không nên cho phép cả hai chỉ vì một client gửi sai cấu hình.

## 5. Chẩn đoán client_secret_jwt và private_key_jwt

Hai phương thức này dùng JWT client assertion để xác thực client tại token endpoint. Request thường có hai tham số:

- client_assertion_type với giá trị urn:ietf:params:oauth:client-assertion-type:jwt-bearer.
- client_assertion chứa JWT assertion được ký bởi client.

Client ID thường được gửi cùng request để xác định client. Không gửi client_secret_basic đồng thời với assertion trừ khi profile và implementation có quy định riêng.

### 5.1 Kiểm tra cấu trúc assertion

JWT client assertion thường có các claim:

| Claim | Ý nghĩa cần xác minh |
|---|---|
| iss | Client hoặc issuer được profile xác định |
| sub | Thường là client_id của client đang xác thực |
| aud | Authorization Server hoặc token endpoint theo audience policy của server |
| exp | Thời điểm hết hạn ngắn trong tương lai |
| iat | Thời điểm phát hành phù hợp với clock và policy |
| jti | Mã assertion duy nhất nếu policy yêu cầu chống replay |
| kid | Key ID để chọn đúng public key khi dùng JWKS |

Header cần có thuật toán được phép và thông tin key phù hợp. Không chấp nhận alg=none. Với private_key_jwt, assertion được ký bằng private key của client và server xác minh bằng public key tương ứng. Với client_secret_jwt, assertion được ký bằng shared secret và server xác minh chữ ký HMAC theo cấu hình.

Một JWT parse thành công không có nghĩa assertion hợp lệ. Phải kiểm tra chữ ký, issuer/subject, audience, thời hạn, thuật toán, key ID và replay policy.

### 5.2 Chẩn đoán client_assertion_type và tham số assertion

Nếu nhận invalid_request, kiểm tra:

- client_assertion_type có đúng URI chuẩn không?
- client_assertion có bị thiếu, rỗng hoặc gửi lặp không?
- JWT có đủ ba phần header.payload.signature không?
- Form body có được encode đúng không?
- Request có gửi nhầm assertion vào trường client_secret không?
- Có gửi nhiều phương thức client authentication cùng lúc không?

Nếu nhận invalid_client, kiểm tra tiếp chữ ký, key và claim. Đừng nhầm assertion hết hạn với grant hết hạn; assertion dùng để xác thực client, còn authorization code/refresh token là credential của grant.

### 5.3 Chẩn đoán private_key_jwt

Kiểm tra theo thứ tự:

1. RegisteredClient có cho phép PRIVATE_KEY_JWT không?
2. JWK Set URI hoặc public key đã đăng ký có truy cập được từ Authorization Server không?
3. JWK Set có chứa public key tương ứng private key client đã dùng để ký không?
4. JWT header có kid đúng và alg thuộc allowlist không?
5. Chữ ký có được tạo bằng private key tương ứng không?
6. iss và sub có khớp client ID theo profile đang triển khai không?
7. aud có khớp audience mà Authorization Server mong đợi không?
8. exp/iat có nằm trong cửa sổ thời gian cho phép không?
9. jti có bị replay hoặc assertion đã được sử dụng trước đó không?

Các lỗi thường gặp:

- Client rotate key nhưng JWKS URI vẫn công bố key cũ.
- Client gửi kid không tồn tại hoặc trùng kid với key khác.
- Server không truy cập được JWKS do DNS, TLS, firewall hoặc timeout.
- JWKS cache của một instance chưa được làm mới.
- Client ký RS256 nhưng server chỉ cho phép thuật toán khác.
- Audience dùng issuer URI trong khi implementation đang yêu cầu token endpoint URI, hoặc ngược lại.
- Clock lệch khiến assertion bị coi là chưa có hiệu lực hoặc đã hết hạn.
- Assertion bị tái sử dụng vì client retry nguyên JWT cũ.

Audience của client assertion phải theo đúng profile và validator mà server cấu hình. Không tự ý thay audience chỉ dựa trên suy đoán. Kiểm tra giá trị server mong đợi trong cấu hình và log chẩn đoán đã được làm sạch.

### 5.4 Chẩn đoán client_secret_jwt

Với client_secret_jwt, server cần xác minh HMAC bằng shared secret. Kiểm tra:

- RegisteredClient có cho phép CLIENT_SECRET_JWT không?
- Client và server có cùng raw shared secret và cùng thuật toán HMAC không?
- Secret có bị rotate ở một bên mà chưa cập nhật bên kia không?
- Secret có đủ độ dài và entropy cho thuật toán được chọn không?
- JWT header alg có khớp policy không?
- Claim iss, sub, aud, exp, iat và jti có hợp lệ không?

Một điểm quan trọng khi thiết kế lưu trữ: HMAC cần key gốc để xác minh chữ ký. Giá trị hash một chiều của client secret không thể dùng trực tiếp như HMAC key. Nếu hệ thống lưu secret theo dạng hash không thể khôi phục, việc hỗ trợ client_secret_jwt cần một cơ chế quản lý shared key phù hợp, ví dụ secret store mã hóa có kiểm soát hoặc thiết kế credential khác. Không lưu plaintext secret trong database chỉ để làm cho assertion hoạt động.

Nếu không có yêu cầu bắt buộc dùng client_secret_jwt, private_key_jwt thường giúp tránh việc chia sẻ một secret HMAC giữa hai bên, nhưng vẫn cần quản lý private key client, public key registration và rotation an toàn.

## 6. Chẩn đoán TLS client authentication

TLS client authentication xác thực client bằng certificate trong TLS handshake. Hai method thường gặp là tls_client_auth và self_signed_tls_client_auth. Khả năng cấu hình và mức hỗ trợ phụ thuộc phiên bản Spring Authorization Server, Spring Security, servlet container và hạ tầng TLS/proxy.

Phân biệt hai lớp:

- TLS server authentication: client xác minh certificate của Authorization Server.
- TLS client authentication: Authorization Server hoặc TLS terminator xác minh certificate của client.

Một client tin certificate server không có nghĩa server đã xác thực certificate client.

### 6.1 Kiểm tra TLS handshake

Nếu lỗi xảy ra trước khi HTTP request tới Spring, hãy kiểm tra TLS terminator, ingress, load balancer hoặc servlet container:

- Listener có yêu cầu hoặc chấp nhận client certificate không?
- Client có gửi certificate trong handshake không?
- Certificate có còn hạn và nằm trong chuỗi tin cậy không?
- Certificate có Extended Key Usage phù hợp cho client authentication không?
- Certificate chain có đầy đủ intermediate certificate không?
- Truststore có chứa CA cần thiết không?
- TLS version và cipher suite có tương thích không?
- Certificate bị thu hồi hoặc không còn được policy chấp nhận không?

Nếu TLS handshake thất bại, ứng dụng có thể không tạo được OAuth error response vì request chưa tới token endpoint. Khi đó log cần xem nằm ở ingress/TLS terminator thay vì chỉ ở Spring Authorization Server.

### 6.2 Kiểm tra ánh xạ certificate với client

Với tls_client_auth, server cần đối chiếu certificate client với thông tin đăng ký theo profile, chẳng hạn subject DN hoặc SAN DNS/URI/IP/email phù hợp. Với self_signed_tls_client_auth, certificate/thumbprint phải khớp giá trị đã đăng ký cho client.

Kiểm tra:

- Certificate được gửi có đúng client ID đang dùng không?
- Subject DN hoặc SAN có khớp metadata đăng ký không?
- Thumbprint SHA-256 có được tính trên đúng certificate DER không?
- Client có dùng certificate mới trong khi RegisteredClient vẫn giữ thông tin certificate cũ không?
- Có nhiều certificate cùng ánh xạ vào một client theo policy không?
- Certificate có được gửi từ đúng kết nối TLS tới đúng endpoint không?

Không ánh xạ certificate chỉ bằng Common Name nếu policy yêu cầu SAN hoặc định danh mạnh hơn. Không chấp nhận một certificate chỉ vì nó được ký bởi CA tin cậy; certificate đó còn phải được gắn với đúng client.

### 6.3 TLS termination tại reverse proxy

Nếu TLS kết thúc tại load balancer, Spring Authorization Server có thể không nhìn thấy certificate client trong TLS connection. Một số kiến trúc chuyển thông tin certificate qua header nội bộ. Khi đó:

- Proxy phải xác minh certificate trước khi chuyển tiếp.
- Proxy phải xóa mọi header certificate do client bên ngoài tự gửi.
- Header nội bộ chỉ được truyền qua kênh proxy-to-application được bảo vệ.
- Ứng dụng chỉ tin header từ proxy được xác định rõ.
- Không để client gọi trực tiếp application endpoint và giả mạo header certificate.
- Log cần phân biệt certificate lấy từ TLS handshake thật với metadata được proxy chuyển tiếp.

Nếu proxy không thể truyền danh tính certificate một cách tin cậy, dùng TLS passthrough hoặc cấu hình mTLS trực tiếp giữa client và thành phần chịu trách nhiệm xác thực.

### 6.4 Certificate rotation

Khi client thay certificate, có thể có giai đoạn chuyển đổi:

1. Đăng ký certificate mới và xác minh certificate chain/thumbprint.
2. Cấu hình server chấp nhận certificate mới theo policy đã duyệt.
3. Chuyển client sang sử dụng certificate mới.
4. Theo dõi xác thực thành công trên mọi instance.
5. Gỡ certificate cũ sau khi hoàn tất chuyển đổi và hết thời gian tương thích.

Không gỡ certificate cũ trước khi client đã chuyển xong nếu cần thời gian overlap. Ngược lại, không giữ certificate bị compromise chỉ để tránh gián đoạn; cần kích hoạt quy trình incident response.

## 7. Kiểm tra RegisteredClient và trạng thái lưu trữ

Khi client authentication chỉ thất bại ở một môi trường hoặc một instance, so sánh dữ liệu RegisteredClient mà từng node thực sự đọc được. Kiểm tra:

- client ID có tồn tại và duy nhất không?
- Client authentication method có đúng với request không?
- Client secret đã encode đúng và có cùng encoder configuration không?
- clientSecretExpiresAt có hết hạn không?
- JWK Set URI có đúng và truy cập được không?
- Certificate subject/SAN/thumbprint có khớp không?
- Grant type và client settings có được triển khai đồng nhất không?
- Cache RegisteredClient có stale sau khi rotate secret hoặc key không?

Với JDBC repository, kiểm tra dữ liệu đã commit và schema đúng phiên bản. Với custom repository hoặc cache, xác minh invalidate/update propagation tới mọi node. Tránh sửa trực tiếp database production để “thử” secret; dùng luồng quản trị credential có audit.

Một lỗi phổ biến là seed client mới chỉ chạy ở một môi trường, trong khi instance khác dùng database hoặc cache khác. Cũng có thể một node vẫn chạy cấu hình cũ sau deployment rolling. Ghi instance ID và client ID trong log đã làm sạch để xác định node xử lý request.

## 8. Phân biệt lỗi client authentication với lỗi grant và resource

Không nên đổi client secret khi lỗi thực sự nằm ở authorization grant hoặc Resource Server.

| Triệu chứng | Có phải invalid_client? | Kiểm tra |
|---|---|---|
| Secret sai ở token endpoint | Có | Secret, encoder, method |
| client assertion hết hạn | Có | exp, iat, clock |
| Certificate client không được tin cậy | Có thể có; hoặc TLS handshake fail trước HTTP | TLS trust, mapping, proxy |
| Client xác thực được nhưng grant không được phép | Không, thường là unauthorized_client | RegisteredClient grant types |
| Authorization code hết hạn/đã dùng | Không, thường là invalid_grant | Authorization state |
| Token hợp lệ nhưng API trả 403 | Không | Scope/authority/audience ở Resource Server |
| Scope không được phép | Không, thường là invalid_scope | Client scope và authorization policy |
| Request thiếu assertion type | Thường là invalid_request | Tham số request |

Nếu token endpoint trả invalid_client, hãy xác minh client authentication trước khi điều tra subject hoặc authorization code. Nếu client authentication thành công nhưng grant thất bại, chuyển sang kiểm tra trạng thái authorization.

## 9. Log và quan sát an toàn

Log đủ dữ liệu để phân loại nguyên nhân nhưng không ghi credential. Trường gợi ý:

| Trường | Ghi nhận |
|---|---|
| event_type | CLIENT_AUTHENTICATION_FAILED |
| client_id | Client ID nếu đã xác định được |
| authentication_method | client_secret_basic, private_key_jwt, tls_client_auth... |
| endpoint | Token endpoint hoặc endpoint đang xử lý |
| failure_category | SECRET_MISMATCH, ASSERTION_INVALID, CERTIFICATE_UNTRUSTED... |
| instance_id | Node xử lý request |
| correlation_id | ID liên kết request |
| occurred_at | Timestamp UTC |
| source | IP/proxy identity nếu policy cho phép |

Không ghi:

- client_secret hoặc Basic Authorization header.
- Raw client_assertion, signature hoặc toàn bộ JWT.
- Private key, shared key, keystore password.
- Toàn bộ certificate chain nếu log không được kiểm soát; nếu cần đối chiếu, ghi thumbprint và metadata không nhạy cảm.
- Request body đầy đủ tại token endpoint.

Có thể tạo metric đếm lỗi theo authentication method, failure category và client group đã chuẩn hóa. Không dùng raw client ID nếu số lượng client lớn hoặc dữ liệu có tính nhạy cảm làm nhãn metric. Theo dõi tỷ lệ invalid_client theo instance để phát hiện lệch cấu hình sau deployment hoặc rotation.

## 10. Ma trận kiểm thử và xác nhận bản sửa

Sau khi xác định nguyên nhân, tái hiện bằng client kiểm thử riêng. Mỗi test chỉ thay đổi một yếu tố và kiểm tra cả response lẫn việc không phát hành token.

| Test ID | Đầu vào | Kết quả mong đợi |
|---|---|---|
| BASIC-01 | Client ID không tồn tại | invalid_client |
| BASIC-02 | Secret sai | invalid_client |
| BASIC-03 | Secret đúng nhưng method không khớp | invalid_client |
| BASIC-04 | Secret hết hạn theo policy | Từ chối xác thực client |
| POST-01 | client_secret_post không được đăng ký | Từ chối |
| POST-02 | Thiếu client_secret hoặc sai form encoding | Từ chối |
| JWT-01 | client_assertion_type sai | invalid_request hoặc lỗi assertion tương ứng |
| JWT-02 | Assertion có chữ ký sai | invalid_client |
| JWT-03 | Assertion hết hạn hoặc iat quá lệch | invalid_client |
| JWT-04 | Audience không khớp | invalid_client |
| JWT-05 | kid không có trong JWKS | invalid_client |
| JWT-06 | Assertion bị replay | Từ chối theo replay policy |
| MTLS-01 | Không gửi client certificate | TLS/client authentication thất bại |
| MTLS-02 | Certificate chain không tin cậy | Từ chối |
| MTLS-03 | Certificate hợp lệ nhưng không khớp client | invalid_client hoặc lỗi TLS mapping |
| MTLS-04 | Certificate cũ sau khi bị thu hồi | Từ chối |
| NODE-01 | Cùng request tới hai instance sau khi rotate credential | Kết quả nhất quán |

Sau mỗi bản sửa, kiểm tra:

1. Client dùng đúng method được đăng ký có thể xác thực.
2. Secret/assertion/certificate sai vẫn bị từ chối.
3. Grant type không được phép vẫn trả unauthorized_client.
4. Authorization code hoặc refresh token sai vẫn bị từ chối độc lập với client authentication.
5. Không có access token/refresh token được phát hành từ request client authentication thất bại.
6. Mọi instance áp dụng cùng credential version, key set và trust configuration.
7. Log không chứa raw secret, assertion, token hoặc private key.

Với secret hoặc certificate rotation, kiểm thử cả giai đoạn chuyển đổi và trạng thái sau khi credential cũ bị gỡ. Với private_key_jwt, kiểm tra JWKS cache và key ID trên mọi instance. Với mTLS, kiểm tra handshake tại đúng điểm TLS termination.

## 11. Quy trình xử lý production

Khi có sự cố invalid_client trong production:

1. Ghi lại thời điểm, correlation ID, endpoint, client ID và instance; không lưu credential.
2. Xác định client đang dùng Basic, POST, JWT assertion hay mTLS.
3. Đối chiếu method gửi với method trong RegisteredClient.
4. Kiểm tra secret expiry/encoder, assertion claims/signature/JWKS hoặc certificate chain/mapping tùy method.
5. So sánh cấu hình và dữ liệu RegisteredClient giữa các instance.
6. Kiểm tra proxy, TLS termination, clock, cache và kết nối JWKS/KMS nếu có.
7. Tái hiện bằng client test, xác nhận lỗi trước khi thay đổi credential.
8. Áp dụng rotation hoặc sửa cấu hình theo quy trình quản lý credential; theo dõi tỷ lệ xác thực sau thay đổi.

Nếu nghi ngờ secret, private key hoặc certificate bị lộ, coi đó là sự cố credential compromise: thu hồi hoặc rotate credential, kiểm tra audit access, xác định client và token bị ảnh hưởng, và thông báo theo quy trình nội bộ. Không đưa credential vào ticket để người khác thử lại.

Một báo cáo xử lý tốt nêu rõ authentication method, nguyên nhân gốc, phạm vi client/instance, thay đổi credential/configuration, test âm tính đã chạy và bằng chứng không còn token được cấp sai. Điều này giúp phân biệt lỗi tích hợp thông thường với sự cố có nguy cơ lộ credential.

Khi xác định đúng authentication method và kiểm tra credential tại ranh giới xác thực client, lỗi invalid_client có thể được khoanh vùng mà không làm suy yếu chính sách OAuth2. RegisteredClient, secret encoder, JWT assertion validator và TLS trust cần được đồng bộ giữa các instance để xác thực client hoạt động ổn định trong toàn bộ vòng đời triển khai.

