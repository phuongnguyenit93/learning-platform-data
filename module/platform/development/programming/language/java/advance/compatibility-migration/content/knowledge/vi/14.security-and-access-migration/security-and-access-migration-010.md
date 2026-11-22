# Kiểm thử xác thực, phân quyền và kết nối bảo mật sau chuyển đổi

## 1. Bối cảnh: nâng JDK không chỉ là thay phiên bản runtime

Trong quá trình **Java Advance Compatibility Migration**, ứng dụng có thể đã nâng JDK, framework bảo mật, HTTP client, application server, bộ thư viện OAuth/OIDC, thư viện ký số, JDBC driver hoặc cấu hình container. Dù các API nghiệp vụ vẫn biên dịch thành công, các thay đổi này có thể tác động trực tiếp đến **xác thực (authentication)**, **phân quyền (authorization)** và **kết nối bảo mật (secure connectivity)**.

Một số tình huống thường gặp:

- Người dùng đăng nhập thành công ở JDK cũ nhưng không thể đăng nhập sau khi nâng framework.
- Access token hợp lệ bị từ chối vì cấu hình issuer, audience, chữ ký hoặc đồng hồ giữa các máy khác nhau.
- API yêu cầu quyền quản trị vô tình trả dữ liệu cho tài khoản thường sau khi đổi security filter hoặc route.
- Client HTTPS thất bại vì chứng chỉ không còn được tin cậy, hostname không khớp, thuật toán ký cũ bị hạn chế hoặc giao thức TLS lỗi thời bị vô hiệu hóa.
- Kết nối mTLS tới hệ thống đối tác thất bại vì runtime mới không nạp đúng client certificate.
- Thay store type, security provider hoặc secret configuration khiến ứng dụng tìm sai private key hoặc trust anchor.
- Test tích hợp xanh vì mock bỏ qua TLS/token, nhưng production lại lỗi handshake hoặc phân quyền.

Những lỗi này có hai chiều rủi ro: **không thể truy cập hợp lệ** (availability) và **cho phép truy cập không hợp lệ** (confidentiality/integrity). Do đó, kiểm thử sau migration phải xác nhận cả trường hợp được phép và trường hợp bị từ chối, không chỉ thử một tài khoản quản trị hoặc một kết nối HTTPS thành công.

Mục tiêu của bài:

1. Xây dựng baseline hợp đồng bảo mật trước migration.
2. Kiểm thử các đường xác thực: mật khẩu, phiên đăng nhập, token, OIDC/OAuth2, SAML hoặc service credentials tùy hệ thống.
3. Kiểm thử phân quyền theo vai trò, thuộc tính, tenant, resource ownership và nguyên tắc deny-by-default.
4. Kiểm thử HTTPS/TLS/mTLS, certificate chain, hostname verification, truststore và keystore trên JDK mục tiêu.
5. Phát hiện các khác biệt về JSSE, security provider, thuật toán, cookie, proxy và runtime configuration.
6. Tổ chức regression/security tests trong CI và phát hành bằng bằng chứng có thể tái tạo.

## 2. Phân biệt ba lớp kiểm tra bảo mật

| Lớp | Câu hỏi cần trả lời | Ví dụ test |
|---|---|---|
| Xác thực | Đối tượng truy cập có đúng danh tính đã được chứng minh hay không? | Credential hợp lệ đăng nhập thành công, token giả hoặc hết hạn bị từ chối. |
| Phân quyền | Danh tính đã xác thực có được phép thực hiện hành động này trên tài nguyên này không? | User không được đọc hồ sơ của tenant khác; admin được truy cập trang quản trị đúng phạm vi. |
| Kênh bảo mật | Dữ liệu được truyền đến đúng đối tác, qua giao thức, chứng chỉ và cấu hình được tin cậy không? | TLS kiểm tra certificate chain + hostname; mTLS xác nhận certificate hai phía. |

Ba lớp tương tác nhưng không thay thế nhau:

- TLS bảo mật kênh truyền không chứng minh người dùng cuối có quyền truy cập một tài nguyên.
- Đăng nhập thành công không bảo đảm người dùng được phép gọi mọi endpoint.
- Có quyền trong database không bảo đảm JWT hợp lệ, chưa hết hạn hoặc token được phát hành cho API đang gọi.
- Client certificate hợp lệ không tự đồng nghĩa với quyền nghiệp vụ, trừ khi hệ thống có chính sách ánh xạ certificate identity sang quyền.

Kiểm thử cần xác định trách nhiệm của từng lớp. Chẳng hạn một API gateway có thể xác thực JWT nhưng service nội bộ vẫn phải kiểm soát quyền truy cập từng đối tượng và không mặc nhiên tin tất cả header do request gửi đến.

## 3. Thiết lập baseline trước khi nâng cấp

Trước khi chạy trên JDK mới, nên lưu một baseline về hành vi bảo mật của phiên bản đang vận hành.

### 3.1. Kiểm kê luồng truy cập

| Luồng | Thành phần liên quan | Điểm cần lưu |
|---|---|---|
| Đăng nhập tương tác | Browser, frontend, IdP, ứng dụng, session store | Redirect URI, callback, cookie, timeout, MFA, logout. |
| API với bearer token | Client, resource server, IdP/JWKS | Issuer, audience, scope, thuật toán ký, hạn token, clock skew. |
| Service-to-service | Máy gọi, service đích, secret manager | Client credentials, mTLS, rotation, service identity. |
| Truy cập dữ liệu | App, DB, JDBC driver, database | Authentication mode, TLS, certificate, role DB, quyền truy cập. |
| Message broker | Producer/consumer, Kafka/AMQP, broker | SASL, TLS, ACL topic/queue, client identity. |
| Quản trị vận hành | Operator, reverse proxy, admin API | RBAC, privilege escalation, audit trail, network boundary. |

Cần ghi phiên bản JDK và security providers đang được sử dụng, phiên bản framework, proxy/gateway, IdP và cách phân phối certificate/secret. Một hệ thống có thể dùng JDK mới ở máy phát triển nhưng vẫn dùng JDK cũ trong test worker hoặc production image, nên baseline phải thu thập ở đúng runtime.

### 3.2. Lưu chính sách truy cập hiện hành

Tài liệu hóa:

- Những endpoint nào công khai và endpoint nào phải xác thực.
- Các loại token/credential được chấp nhận.
- Các role, permission, scope và nguồn dữ liệu quyết định quyền.
- Quy tắc quản trị tenant, tổ chức, ownership hoặc nhóm người dùng.
- Hành vi khi token thiếu, sai, hết hạn, bị thu hồi.
- Chính sách session timeout, logout, CSRF và cookie.
- Chứng chỉ và CA được tin cậy, yêu cầu hostname, TLS version và cipher policy.
- Quá trình rotation secret/certificate và phản ứng khi hết hạn.

Không đưa mật khẩu, private key, raw token hoặc secret vào báo cáo baseline. Lưu **metadata không nhạy cảm** như issuer, key ID công khai, thời hạn, cấu hình policy và tham chiếu đến vị trí secret an toàn.

### 3.3. Chọn test fixtures có thể tái tạo

Tạo danh tính thử nghiệm với quyền tối thiểu:

~~~text
anonymous             : chưa xác thực
user-a / tenant-a     : chỉ đọc tài nguyên thuộc tenant-a
user-b / tenant-b     : chỉ đọc tài nguyên thuộc tenant-b
manager-a / tenant-a  : sửa tài nguyên được phân quyền trong tenant-a
admin-test            : quản trị có phạm vi được định nghĩa
service-client-test   : kết nối machine-to-machine, scope hạn chế
~~~

Token/certificate thử nghiệm phải được phát hành riêng cho môi trường test, với hạn sử dụng và các trường claim được kiểm soát. Không sao chép token production vào fixture hoặc commit private key production vào repository.

## 4. Kiểm thử xác thực người dùng

### 4.1. Kiểm thử đường thành công

Với mỗi cơ chế đăng nhập mà sản phẩm hỗ trợ, xác nhận:

1. Credential hợp lệ được nhận đúng cách.
2. Danh tính được ánh xạ đúng user ID và tenant.
3. Session/token chỉ được tạo sau khi xác thực thành công.
4. MFA hoặc bước xác minh bổ sung được kích hoạt theo chính sách.
5. Redirect hoặc callback đưa người dùng về đúng domain và đường dẫn cho phép.
6. Các thông tin danh tính hiển thị đúng mà không làm lộ dữ liệu nhạy cảm.
7. Sau logout, phiên/token chịu đúng chính sách vô hiệu hóa đã công bố.

Test đăng nhập thành công có thể phát hiện các thay đổi ở password encoder, user store, cookie parser hoặc thư viện xác thực, nhưng chưa đủ để khẳng định hệ thống an toàn.

### 4.2. Các trường hợp bị từ chối

Nhóm tình huống âm tính cần có:

| Tình huống | Hành vi mong đợi |
|---|---|
| Không gửi credential | Từ chối với trạng thái/challenge theo giao thức; không tạo session hợp lệ. |
| Mật khẩu sai | Không cấp session/token; áp dụng chính sách rate limit/lockout nếu có. |
| Tài khoản bị vô hiệu hóa | Không cho truy cập dù mật khẩu đúng. |
| Credential đã hết hạn hoặc bị thu hồi | Từ chối và không cho truy cập protected resource. |
| MFA chưa hoàn tất | Không coi trạng thái đăng nhập là fully authenticated. |
| Session ID không hợp lệ | Không truy cập được tài nguyên cần xác thực. |
| Redirect URI không được phép | Từ chối hoặc áp dụng allowlist; không chuyển token tới domain tùy ý. |
| Token giả mạo hoặc chữ ký sai | Từ chối; không fallback sang anonymous có quyền cao hơn. |

Với HTTP API, lỗi thiếu hoặc sai credential thường liên quan **401 Unauthorized** và cơ chế challenge, còn **403 Forbidden** thường thể hiện đã xác định request nhưng không đủ quyền. Chi tiết có thể phụ thuộc framework và giao thức, nên hãy kiểm tra contract cụ thể thay vì chỉ assert một status cho mọi hệ thống.

### 4.3. Password storage và migration

Khi nâng framework, thay đổi password hashing hoặc encoder dễ làm tài khoản cũ không đăng nhập được. Bản nâng cấp phải xử lý đúng các hash đã lưu, ví dụ thuật toán/version prefix được dùng bởi framework.

Nguyên tắc:

- Không chuyển về lưu plaintext hoặc hash không có salt để xử lý nhanh lỗi migration.
- Khi thay thuật toán, có thể hỗ trợ xác minh hash cũ rồi rehash theo chính sách mới **sau một lần xác thực thành công**, nếu thiết kế và yêu cầu bảo mật cho phép.
- Không coi việc “đăng nhập được” là đủ nếu hệ thống vô tình chấp nhận thuật toán/cấu hình yếu không được phép.
- Kiểm tra tài khoản được tạo ở bản cũ, tài khoản mới và tài khoản chuyển đổi dở dang.

Nếu framework thay mặc định của password encoder, cần cấu hình chủ đích, dữ liệu test đủ các đời hash và kế hoạch chuyển đổi tương thích.

## 5. Kiểm thử token OAuth2/OIDC và JWT

Trong hệ thống phân tán, xác thực có thể diễn ra qua OpenID Connect và OAuth2, với access token được resource server xác minh.

### 5.1. Các thuộc tính token cần kiểm tra

| Thuộc tính | Ý nghĩa | Điều cần test |
|---|---|---|
| iss (issuer) | Tổ chức phát hành token | Chỉ chấp nhận issuer đã cấu hình. |
| aud (audience) | Đối tượng nhận token | Token dành cho API khác bị từ chối. |
| exp (expiration) | Thời điểm hết hạn | Token quá hạn bị từ chối theo chính sách clock skew. |
| nbf (not before) | Thời điểm token bắt đầu hợp lệ | Token dùng quá sớm bị từ chối. |
| iat (issued at) | Thời điểm phát hành | Kiểm tra khi chính sách cần giới hạn độ tuổi token. |
| sub (subject) | Danh tính của chủ thể | Ánh xạ user/service đúng, tránh nhầm tenant. |
| scope/scp | Phạm vi quyền token | Chỉ cấp những quyền đã gán trong policy. |
| roles/groups | Claim về role/nhóm nếu IdP dùng | Mapping và prefix role không bị thay đổi khi nâng framework. |
| kid | Mã nhận diện khóa ký | Chọn đúng public key trong JWKS; xử lý rotation. |
| alg | Thuật toán chữ ký | Chỉ chấp nhận các thuật toán được allowlist rõ ràng. |

Không tự tin tưởng claim chỉ vì có thể decode Base64 của JWT. Việc parse và đọc payload không chứng minh chữ ký hợp lệ.

### 5.2. Bộ test tối thiểu cho JWT

Tạo token giả lập bằng **test signing keys**, bao gồm:

1. Token hợp lệ với issuer, audience, chữ ký, scope đúng.
2. Token hết hạn.
3. Token chưa đến nbf.
4. Token có issuer sai.
5. Token dùng audience của service khác.
6. Token thiếu scope hoặc role cần thiết.
7. Token có chữ ký không khớp, bị thay đổi payload hoặc sử dụng thuật toán không được phép.
8. Token có kid không tồn tại hoặc JWKS chưa cập nhật.
9. Token được ký bằng khóa mới sau rotation.
10. Token bị thu hồi, nếu hệ thống có cơ chế revocation hoặc token introspection.

Không nên thiết kế test nhằm chấp nhận token bất kỳ để pipeline dễ chạy. Trong môi trường test, resource server vẫn cần thực hiện cùng chính sách xác thực, chỉ thay nguồn issuer/key thành nguồn do test kiểm soát.

### 5.3. JWKS và rotation

Khi đổi JDK/HTTP client, việc gọi JWKS endpoint có thể lỗi TLS, proxy, DNS hoặc timeout. Khi nâng thư viện bảo mật, cơ chế cache và refresh JWKS cũng có thể thay đổi.

Kiểm thử:

- Khởi động với JWKS hợp lệ và xác minh token.
- Khóa ký được thay trong phạm vi chính sách, cache được refresh đúng.
- Key ID không nhận diện được bị xử lý an toàn.
- JWKS endpoint tạm không sẵn sàng: hệ thống có ứng xử dự kiến, không tự bỏ qua kiểm tra chữ ký.
- Không có dependency hoặc truststore nào vô hiệu hóa hostname/certificate validation.

Nếu môi trường yêu cầu Internet hoặc mạng nội bộ để lấy JWKS, CI nên dùng IdP/JWKS test endpoint ổn định hoặc test server phù hợp, đồng thời có integration test với môi trường gần production.

### 5.4. Authorization Code/PKCE, OIDC login và logout

Với browser login, kiểm tra end-to-end:

~~~text
Browser ──> Application ──> Identity Provider
   ▲             │               │
   │             └─ callback <───┘
   │                   │
   └── authenticated session / user identity
~~~

Các kiểm thử nên xác minh:

- state và nonce được dùng và kiểm tra theo yêu cầu luồng.
- Redirect URI khớp allowlist.
- PKCE được sử dụng khi phù hợp với loại client/flow.
- Authorization code không bị dùng lại ngoài chính sách.
- ID token được kiểm tra issuer, audience, signature, lifetime và nonce phù hợp.
- Access token và ID token không bị sử dụng thay thế cho nhau trái mục đích.
- Logout và session invalidation hoạt động theo contract.
- Cookie và proxy headers không làm mất scheme/host chính xác sau khi nâng gateway.

Không nên đánh đồng “IdP trả về HTTP 200” với “login flow bảo mật đúng”.

## 6. Kiểm thử phân quyền theo vai trò và tài nguyên

### 6.1. Authentication không đồng nghĩa với authorization

Một user đã đăng nhập có thể không được đọc tất cả đơn hàng; một service có token hợp lệ có thể chỉ được gọi endpoint đọc; một administrator có thể chỉ quản trị tenant cụ thể.

Sau migration, các rủi ro thường gặp:

- Thứ tự security filter hoặc request matcher thay đổi, làm một route không còn được bảo vệ.
- Cấu hình method security bị mất hiệu lực hoặc annotation bị thay đổi.
- Role prefix hoặc claim mapping khác trước, cấp sai quyền.
- API mới bỏ qua kiểm tra ownership ở tầng service.
- Endpoint được đổi path nhưng rule cũ không còn khớp.
- Tầng gateway xác thực token nhưng backend tin header do client có thể tự gửi.

### 6.2. Ma trận role × action × resource

Không chỉ test “user thường” và “admin”. Hãy mô hình hóa yêu cầu chi tiết:

| Principal | Đọc đơn của chính mình | Đọc đơn người khác cùng tenant | Đọc đơn tenant khác | Sửa cấu hình admin |
|---|---|---|---|---|
| Anonymous | Không | Không | Không | Không |
| User A / tenant A | Có, theo chính sách | Không, nếu không được cấp quyền | Không | Không |
| Manager A / tenant A | Có | Có, theo quyền quản lý | Không | Không, trừ khi được cấp riêng |
| Admin tenant A | Theo chính sách | Theo chính sách | Không, nếu không có quyền liên tenant | Theo phạm vi tenant A |
| Global admin test | Theo quyền đặc biệt đã phê duyệt | Theo quyền đặc biệt | Theo quyền đặc biệt | Theo chính sách toàn cục |

Đây là ví dụ minh họa, không phải mô hình quyền mặc định của mọi ứng dụng. Các ô “Có” phải xuất phát từ policy thực tế.

### 6.3. Kiểm thử IDOR và cross-tenant

Một API dạng:

~~~http
GET /api/orders/123
Authorization: Bearer <test-token>
~~~

có thể an toàn khi user A truy cập đơn 123 thuộc user A, nhưng không an toàn nếu user A đổi ID sang đơn 124 thuộc tenant B và vẫn nhận dữ liệu.

Bộ test nên tạo resource thuộc nhiều owner/tenant rồi xác minh:

- Token hợp lệ của tenant A không đọc, sửa hoặc xóa resource của tenant B.
- Tăng giảm ID hoặc thay route không làm bypass authorization.
- Filter truy vấn database có giữ tenant boundary và ownership check.
- Các endpoint bulk/export/search không bỏ qua scope chỉ vì trả nhiều resource.
- Cache không trả dữ liệu khác tenant do key thiếu tenant/subject.
- Background job/async flow vẫn áp dụng context quyền đúng, không lấy quyền của request trước đó.

Kiểm thử này quan trọng khi migration thay ORM, repository, framework security hoặc cache vì lỗi phân quyền ở tầng dữ liệu không nhất thiết thể hiện trong test controller đơn giản.

### 6.4. Kiểm thử cả route-level và method-level security

Một rule bảo vệ URL không thay thế kiểm tra tại business service nếu cùng service được gọi từ batch, messaging, scheduled job hoặc interface khác. Ngược lại, một annotation quyền ở method không bảo đảm mọi endpoint công khai đều được map đúng.

Khi nâng Spring Security hoặc framework tương tự, cần xác minh:

1. Request matcher và security filter chain áp dụng cho mọi route dự kiến.
2. HTTP method khác nhau trên cùng path có quyền khác nhau nếu cần.
3. Method security thực sự được bật và proxy/interceptor được áp dụng.
4. Các method nội bộ/self-invocation không vô tình bypass proxy khi thiết kế dựa vào proxy.
5. Các đường async/scheduled/message không mang nhầm security context.
6. Quy tắc deny-by-default hoạt động với endpoint mới chưa được khai báo.

Không nên chỉ kiểm tra rằng annotation xuất hiện trong source; cần test request hoặc lời gọi thực tế xem quyền có được cưỡng chế hay không.

## 7. Session, cookie và CSRF sau migration

### 7.1. Session lifecycle

Với ứng dụng sử dụng session:

- Sau login, session gắn với principal đúng.
- Session ID được đổi khi cần để giảm nguy cơ session fixation.
- Session hết hạn theo idle timeout hoặc absolute lifetime như chính sách.
- Logout hủy phiên theo phạm vi đã công bố.
- Session store phân tán hoạt động trên nhiều replica.
- Key serialization hoặc framework session schema không phá các phiên đang tồn tại nếu hệ thống cần rolling upgrade.
- Cookie không chứa thông tin đăng nhập ở dạng dễ lộ.

Trong rolling deployment, các instance chạy phiên bản cũ và mới có thể cùng đọc session store. Nếu object session được serialize bằng Java, thay class, serialVersionUID hoặc framework version có thể làm một node không đọc được session của node kia. Cần có chính sách compatibility hoặc chấp nhận logout có kiểm soát nếu đó là điều được công bố.

### 7.2. Cookie security flags

Kiểm tra cookie được phát hành với các thuộc tính phù hợp:

| Thuộc tính | Vai trò | Tình huống cần test |
|---|---|---|
| Secure | Hạn chế gửi cookie qua kết nối không bảo mật. | Proxy TLS termination có cấu hình forwarded headers đúng để ứng dụng phát cookie Secure. |
| HttpOnly | Giảm khả năng JavaScript phía trang đọc session cookie. | Session cookie không bị framework mới bỏ flag. |
| SameSite | Kiểm soát gửi cookie trong bối cảnh cross-site. | Login redirect và form flow vẫn hoạt động với mức bảo vệ dự kiến. |
| Domain | Giới hạn domain nhận cookie. | Không mở rộng nhầm sang subdomain không tin cậy. |
| Path | Giới hạn đường dẫn áp dụng. | Context path sau migration không tạo cookie phạm vi sai. |
| Max-Age/Expires | Quy định lifetime phía client. | Không vô tình biến cookie phiên thành cookie tồn tại lâu. |

Cookie flags cần được chọn theo kiến trúc ứng dụng và trình duyệt được hỗ trợ; không nên gắn SameSite một cách tùy tiện khiến luồng OIDC hoặc cross-site hợp lệ bị lỗi.

### 7.3. CSRF, CORS và reverse proxy

CSRF liên quan tới request từ trình duyệt có credential được gửi tự động (đặc biệt cookie-based session). Nâng security framework có thể thay các mặc định về CSRF hoặc matcher bỏ qua CSRF.

Kiểm thử:

- Các thao tác làm thay đổi trạng thái qua browser bị từ chối khi thiếu CSRF token nếu chính sách yêu cầu.
- CSRF token hợp lệ được chấp nhận, token sai hoặc hết hạn bị từ chối.
- API dùng bearer token theo mô hình không dựa trên cookie có cấu hình phù hợp, không tắt CSRF đại trà cho mọi đường.
- CORS allowlist không mở rộng thành cho phép origin tùy ý với credential.
- Forwarded headers được chỉ tin từ proxy có kiểm soát; không tin bừa header X-Forwarded-* do Internet client gửi.

Migration có thể thay HTTPS termination từ app server sang gateway, làm thay đổi cách ứng dụng xác định scheme, host và secure cookie. Test phải đi qua topology proxy gần production, không chỉ gọi trực tiếp localhost.

## 8. HTTPS/TLS: kết nối được chưa đủ, phải xác minh đúng bên nhận

TLS bảo vệ tính bí mật, toàn vẹn và xác thực endpoint theo trust model. Một kết nối HTTPS “thành công” chỉ có giá trị bảo mật khi client thực hiện xác minh certificate chain và danh tính server theo chính sách.

### 8.1. Những thay đổi thường gặp khi nâng JDK

Trong JDK mới, cấu hình JSSE, danh sách giao thức và cipher suites được hỗ trợ, truststore mặc định, security provider và các thuật toán bị hạn chế có thể khác JDK cũ.

Ảnh hưởng có thể gồm:

- Server cũ chỉ hỗ trợ TLS version hoặc cipher yếu không còn được JDK mục tiêu cho phép mặc định.
- Certificate chain dùng thuật toán ký hoặc key size không còn được chấp nhận.
- Root/intermediate CA không nằm trong truststore của runtime mới.
- Server không gửi đầy đủ intermediate certificate.
- SAN không chứa hostname của endpoint, dù Common Name cũ trông đúng.
- Client đang dựa vào trust-all TrustManager hoặc hostname verifier không an toàn.
- Proxy TLS termination hoặc SNI/ALPN thay đổi khi nâng HTTP client.
- Certificate/key store được chuyển từ JKS sang PKCS12 hoặc thay password/alias mà chưa cập nhật cấu hình.

Khi gặp handshake failure, **không** dùng việc tắt certificate verification như giải pháp migration. Đó là thay đổi làm mất bảo đảm xác thực endpoint và có thể tạo lỗ hổng man-in-the-middle.

### 8.2. Thành phần chính của TLS

~~~text
Java HTTPS Client
  │
  ├─ TrustStore: các CA/chứng chỉ được phép tin cậy
  ├─ TrustManager: kiểm tra chuỗi chứng chỉ
  ├─ Hostname verification: khớp danh tính endpoint
  ├─ Protocol/cipher policy: thuật toán được chấp nhận
  └─ (Nếu mTLS) KeyStore/KeyManager: chứng chỉ và private key client
  │
  ▼
TLS handshake
  │
  ▼
Server Certificate + Chain + Protocol/Cipher
  │
  ▼
Kênh đã được xác thực theo chính sách
~~~

Truststore và keystore có vai trò khác nhau: truststore thường chứa trust anchors, còn keystore của client mTLS chứa certificate/private key mà client sử dụng để chứng minh danh tính. Một file có thể chứa nhiều loại entry, nhưng cấu hình cần phân biệt mục đích sử dụng.

### 8.3. TLS positive tests

Nên kiểm tra:

1. Kết nối đến endpoint có certificate chain hợp lệ và SAN đúng.
2. Giao thức TLS và cipher suite được thương lượng thuộc allowlist chính sách.
3. SNI được gửi đúng khi server có nhiều virtual hosts.
4. Proxy, load balancer và service mesh không làm thay đổi danh tính endpoint ngoài thiết kế.
5. Retry/timeout và connection pooling hoạt động sau khi nâng HTTP client.
6. Certificate rotation được xử lý mà không yêu cầu bỏ xác minh chứng chỉ.
7. TLS hoạt động trong container/runtime thực tế, không chỉ trên máy phát triển.

Nên ghi nhận TLS version/cipher suite dưới dạng metadata nếu phù hợp chính sách quan sát, nhưng tránh log key material hoặc nội dung nhạy cảm của session.

### 8.4. TLS negative tests

Các trường hợp bị từ chối quan trọng:

| Tình huống | Mong đợi |
|---|---|
| Self-signed certificate không được trust | Kết nối thất bại theo chain validation. |
| Certificate đã hết hạn/chưa đến hạn | Bị từ chối theo quy tắc xác minh hiệu lực. |
| Certificate chain không hoàn chỉnh và không thể xây dựng path hợp lệ | Kết nối thất bại; ghi rõ nguyên nhân. |
| Hostname/SAN không khớp | Bị từ chối, không fallback sang ignore hostname. |
| Server chỉ dùng protocol/cipher không được phép | Không thương lượng kết nối. |
| Chứng chỉ được ký bằng thuật toán bị cấm theo policy | Bị từ chối; không hạ tiêu chuẩn toàn hệ thống để bỏ lỗi. |
| Truststore sai hoặc thiếu CA | Không chấp nhận server không nằm trong trust policy. |
| Client certificate sai với môi trường mTLS | Server từ chối theo chính sách xác thực client. |

Các test này cần đặt trong môi trường kiểm soát, sử dụng CA/chứng chỉ test và endpoint do nhóm sở hữu. Không cần vô hiệu hóa kiểm tra TLS của ứng dụng để mô phỏng trường hợp âm tính.

## 9. Kiểm thử mTLS và danh tính service

Trong mutual TLS, ngoài client xác minh server, server cũng yêu cầu client xuất trình chứng chỉ hợp lệ.

### 9.1. Những thứ phải kiểm tra

- Client nạp đúng alias chứa private key và certificate chain.
- Chứng chỉ client còn hiệu lực, có mục đích sử dụng và danh tính phù hợp.
- Server tin CA cấp cho client certificate theo đúng chính sách.
- Chứng chỉ thuộc service A không thể được sử dụng như service B nếu hệ thống phân biệt service identity.
- Mapping identity từ SAN, SPIFFE ID, DN hoặc thuộc tính khác được cấu hình rõ.
- Rotation client certificate có thể diễn ra mà không gây downtime ngoài mức chấp nhận được.
- Kết nối bị từ chối nếu client thiếu certificate hoặc certificate không được phép.

Một handshake mTLS thành công chứng minh các ràng buộc chứng chỉ của hai phía trong kết nối. Nó không tự xác định quyền nghiệp vụ; nếu API có authorization theo service identity, cần test quyền trên resource/service operations riêng.

### 9.2. Kiểm thử với các certificate fixtures

Một bộ chứng chỉ thử nghiệm nên có:

~~~text
test-root-ca
  ├─ valid-server.example.test (SAN đúng)
  ├─ wrong-host.example.test (SAN không khớp endpoint)
  ├─ valid-client-a (định danh service A)
  ├─ valid-client-b (định danh service B)
  └─ untrusted-client (được CA khác ký)
~~~

Có thể chuẩn bị fixture phục vụ CI, nhưng private key test vẫn cần được quản lý phù hợp. Không sử dụng production certificate để tái hiện môi trường staging.

Nếu test cần mô phỏng expired certificate hoặc incomplete chain, hãy dùng fixture chuyên biệt và server TLS kiểm soát được; không sửa ngày/đồng hồ của runner toàn cục nếu làm ảnh hưởng các test khác.

### 9.3. TLS termination và service mesh

Trong kiến trúc có ingress, API gateway hoặc service mesh, TLS có thể được kết thúc hoặc thiết lập lại ở nhiều hop:

~~~text
Browser ── TLS ── Ingress ── mTLS ── Service A ── mTLS ── Service B
~~~

Với mỗi hop, cần xác định:

1. Ai là TLS client và ai là TLS server?
2. Thành phần nào xác minh certificate của phía còn lại?
3. Nơi nào giữ private key và trust anchors?
4. Danh tính người dùng cuối được chuyển tiếp bằng cơ chế nào?
5. Ranh giới nào kiểm tra role/tenant/resource?
6. Chính sách network và identity nào vẫn bảo vệ traffic nội bộ?

Test đơn lẻ service A qua localhost có thể bỏ qua ingress và mTLS; vì vậy cần test qua đường đi triển khai chính thức.

## 10. Java JSSE, certificate store và security provider

### 10.1. Kiểm tra JDK và cấu hình TLS thực tế

Trong môi trường test/CI:

~~~bash
java -version
java -XshowSettings:security -version
~~~

Tùy phiên bản JDK, tùy chọn XshowSettings liên quan security có thể không tồn tại hoặc khác nhau; hãy kiểm tra java -XshowSettings:help của chính JDK. Có thể dùng keytool để kiểm tra các keystore/truststore do dự án kiểm soát.

Ví dụ liệt kê metadata của test truststore:

~~~bash
keytool -list -v -keystore test-truststore.p12 -storetype PKCS12
~~~

Lệnh có thể hỏi mật khẩu. Trong CI, không đưa mật khẩu vào command line hoặc log không được bảo vệ. Secret phải lấy từ secret manager hoặc cơ chế input an toàn được nền tảng hỗ trợ.

### 10.2. JKS, PKCS12 và các tham số JSSE

Một ứng dụng có thể từng sử dụng JKS, trong khi cấu hình hoặc keytool trên JDK mới ưu tiên PKCS12. Khi migration phải xác định:

- Định dạng thực tế của file store.
- Alias của key/certificate cần nạp.
- Password của store và key, nếu có.
- Cách nạp truststore trong app server, Java HttpClient, Spring hoặc HTTP client khác.
- Security provider hỗ trợ các thuật toán/key format đang được sử dụng.
- Quy tắc rotation/reload certificate mà runtime thực hiện.

Ví dụ các thuộc tính JVM có thể gặp:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType
~~~

Không nên dùng một truststore toàn cục tùy tiện cho mọi outbound request nếu các đối tác cần trust policy khác nhau. Trong hệ thống đa tenant hoặc nhiều integration, có thể cần SSLContext/HTTP client riêng theo trust boundary.

### 10.3. Cấu hình thuật toán bị hạn chế

Một số security properties điều khiển các thuật toán/certificate không được chấp nhận, ví dụ:

~~~text
jdk.tls.disabledAlgorithms
jdk.certpath.disabledAlgorithms
~~~

Các giá trị mặc định và hành vi cụ thể phụ thuộc JDK distribution/update. Khi endpoint cũ không bắt tay được, hãy tìm nguyên nhân và nâng cấu hình/thuật toán phía server hoặc certificate chain.

**Không nên xóa các hạn chế thuật toán trên toàn JVM chỉ để một endpoint legacy kết nối được**, vì điều đó làm yếu chính sách TLS/certificate cho những kết nối khác. Nếu có ngoại lệ bảo mật bắt buộc, phải được đánh giá riêng với thời hạn, phạm vi và biện pháp giảm thiểu rõ ràng.

### 10.4. Security provider và crypto API

Ứng dụng có thể dùng JCA/JCE, PKCS#11, HSM, hardware token hoặc provider của bên thứ ba. Nâng JDK hoặc provider có thể làm thay đổi:

- Tên/alias thuật toán.
- KeyStore type và cách mở private key.
- Provider order.
- Supported signature/cipher algorithms và key sizes.
- Behavior khi ký/xác minh hoặc đọc certificate.
- Tương thích với thư viện native, driver/HSM.

Kiểm thử nên thực thi thật các nghiệp vụ mã hóa/ký/xác minh được hỗ trợ trên môi trường test có provider tương ứng, thay vì chỉ kiểm tra class khởi tạo thành công.

## 11. Chẩn đoán TLS an toàn

### 11.1. Phân biệt handshake, trust path và hostname

Khi kết nối HTTPS thất bại, nên thu thập:

- Endpoint host/port và tên DNS thực tế.
- JDK version, runtime image và client library version.
- Certificate metadata công khai: subject, issuer, SAN, validity, chain.
- Error category và stack trace đã loại bỏ secrets.
- TLS version/cipher được thương lượng hoặc từ chối, nếu có.
- Proxy/gateway/service mesh hop liên quan.

Những lỗi thường gặp:

| Lỗi hoặc tín hiệu | Hướng kiểm tra |
|---|---|
| PKIX path building failed | Truststore, CA/intermediate chain, certificate path policy. |
| No subject alternative DNS name matching | Hostname/SAN không khớp endpoint thực. |
| handshake_failure | Giao thức/cipher mismatch, client auth, policy hoặc certificate. |
| certificate_unknown | Phía đối tác không chấp nhận certificate chain/danh tính. |
| bad_certificate | Certificate hoặc xác minh certificate không đáp ứng chính sách. |
| No appropriate protocol | TLS version/cipher policy không có tập giao nhau. |
| Keystore file/alias not found | Đường dẫn, store type, alias, packaging, secret injection. |

Cùng thông báo lỗi có thể có nhiều nguyên nhân. Không kết luận bằng việc đọc duy nhất dòng đầu stack trace.

### 11.2. Dùng keytool và openssl để quan sát test endpoint

Kiểm tra metadata certificate trong test keystore:

~~~bash
keytool -list -v -keystore test-truststore.p12 -storetype PKCS12
~~~

Quan sát handshake của endpoint do nhóm kiểm soát:

~~~bash
openssl s_client -connect api.example.test:443 -servername api.example.test -showcerts
~~~

openssl s_client hiển thị thông tin handshake và certificate chain để điều tra, nhưng kết nối “CONNECTED” không đồng nghĩa hostname/trust đã được client Java xác minh đúng. Cần kiểm tra kết quả verify và chạy Java client thực tế với policy của ứng dụng.

Nếu dùng curl:

~~~bash
curl -v https://api.example.test/health
~~~

Tránh dùng tùy chọn bỏ xác minh chứng chỉ để tuyên bố kết nối bảo mật đã đạt. Một số curl build dùng truststore khác JDK, do đó curl thành công cũng không chứng minh JSSE của ứng dụng Java sẽ thành công.

### 11.3. Debug handshake của JSSE

Trong môi trường test có kiểm soát, có thể bật:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar application.jar
~~~

Debug TLS có thể làm log rất lớn và có thể lộ metadata nhạy cảm hoặc chi tiết phiên giao tiếp. Chỉ dùng trong môi trường an toàn, giới hạn thời gian, xử lý log theo chính sách bảo mật và **không** bật mặc định lâu dài ở production.

Không ghi secret, private key, full bearer token hoặc password vào log chỉ để sửa handshake. Ưu tiên log category, correlation ID, endpoint logical name và certificate fingerprint khi được cho phép.

## 12. Kiểm thử kết nối database, broker và các dịch vụ ngoài

Nâng Java hoặc driver ảnh hưởng đến nhiều kênh ngoài HTTPS của ứng dụng.

### 12.1. JDBC / database

Kiểm tra:

- Authentication: username/password, Kerberos, cloud IAM hoặc certificate nếu được dùng.
- TLS thực sự được bật và certificate/hostname được kiểm tra theo driver.
- JDBC driver tương thích JDK mục tiêu.
- Quyền của database principal có đúng mức tối thiểu?
- Connection pool có khởi tạo, reconnect và rotation secret đúng?
- Server không yêu cầu cipher/protocol bị policy Java mới từ chối.
- Test query và transaction không sử dụng tài khoản có quyền vượt quá production role.

Một kết nối JDBC thành công không chứng minh database đang mã hóa kênh truyền; cần kiểm tra cấu hình driver và khả năng xác thực server trong đường triển khai thực.

### 12.2. Kafka/AMQP/message broker

Các môi trường có thể sử dụng TLS, SASL, mTLS và ACL. Test nên bao gồm:

- Producer/consumer đúng principal kết nối và đọc/ghi resource được cấp.
- Principal chỉ-read không thể ghi nếu policy không cho phép.
- Access tới topic/queue của tenant khác bị từ chối.
- Certificate/secret rotation, reconnect và failover đúng cách.
- Không vô tình tắt TLS hoặc chọn listener plaintext sau khi thay config.

Nếu producer gửi cùng dữ liệu qua nhiều kênh khi migration, cần kiểm soát idempotency và không tạo tác dụng nghiệp vụ lặp lại.

### 12.3. Dịch vụ bên ngoài và API gateway

Với đối tác, có thể yêu cầu OAuth2 client credentials, mTLS, request signing hoặc API key. Hãy xác định từng lớp auth riêng và test token refresh, secret rotation, certificate identity cùng chính sách retry/timeout.

Không gọi endpoint production bằng fixture không được phép. Test integration cần môi trường sandbox hợp lệ hoặc mock có hợp đồng được xác nhận.

## 13. Ma trận kiểm thử end-to-end

Một ma trận tốt phải kết hợp danh tính, quyền và kênh kết nối:

| Kịch bản | Xác thực | Phân quyền | Kênh bảo mật | Mong đợi |
|---|---|---|---|---|
| User đúng role gọi API sở hữu | Token/session hợp lệ | Có quyền resource | HTTPS hợp lệ | Thành công theo contract. |
| Anonymous gọi API cần login | Không có token | Không có quyền | HTTPS hợp lệ | Bị từ chối, không lộ dữ liệu. |
| Token hết hạn | Không hợp lệ | Không được xét như hợp lệ | HTTPS hợp lệ | Bị từ chối. |
| Token đúng nhưng thiếu scope | Hợp lệ | Thiếu quyền | HTTPS hợp lệ | Bị từ chối. |
| User A đọc resource tenant B | Hợp lệ | Sai tenant/ownership | HTTPS hợp lệ | Bị từ chối. |
| Token giả có claim admin | Chữ ký sai | Không được cấp admin | HTTPS hợp lệ | Bị từ chối. |
| Admin gọi qua hostname certificate sai | Credential hợp lệ | Có quyền | TLS identity sai | Kết nối bị từ chối trước khi chấp nhận response. |
| Service A dùng client certificate B | Có thể chứng minh certificate khác | Không đúng service identity | mTLS | Từ chối theo policy. |
| Rotate JWKS/certificate hợp lệ | Token/cert mới hợp lệ | Giữ quyền | TLS/mTLS hợp lệ | Chuyển đổi không làm mở rộng quyền. |
| Secrets thiếu hoặc sai | Không thể xác thực | Không được nâng quyền | Tùy kênh | Fail closed, log an toàn. |

Ma trận ví dụ phải được điều chỉnh theo policy thật. Một hệ thống có thể dùng 401, 403, redirect hoặc giao thức khác nhau; không nên coi mọi lỗi authorization là cùng HTTP status.

## 14. Viết integration test và negative test

### 14.1. Tổ chức các lớp test

Để tăng khả năng phát hiện regression, có thể chia:

1. **Unit test security mapping:** chuyển claim/role/scope, policy evaluator, xử lý null/missing claim.
2. **Component test:** resource server với test issuer/JWKS hoặc identity provider giả lập có chữ ký thật.
3. **Integration test:** ứng dụng khởi động với security filter/method interceptor, database/broker và test TLS endpoint.
4. **End-to-end test:** browser login/OIDC/mTLS/gateway qua topology gần production.
5. **Post-deploy smoke test:** kiểm tra những đường truy cập ít rủi ro, không dùng dữ liệu production nhạy cảm.

Test mức dưới nhanh hơn nhưng không thay thế test luồng thật. Ví dụ mock Authentication trong controller test có thể bỏ qua toàn bộ xác minh JWT hoặc cookie; cần test một số luồng qua security filter thực.

### 14.2. Ví dụ test authorization bằng JUnit và MockMvc

Ví dụ minh họa cho ứng dụng Spring MVC có security filter được bật trong test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationTest {

    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadProtectedOrder() throws Exception {
        mvc.perform(get("/api/orders/100"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "user-a", roles = "USER")
    void userCannotReadAnotherTenantsOrder() throws Exception {
        mvc.perform(get("/api/orders/200"))
           .andExpect(status().isForbidden());
    }
}
~~~

Đây là đoạn minh họa, cần thêm import/dependency test và chuẩn bị dữ liệu đơn hàng/tenant phù hợp. Status thực tế còn phụ thuộc cách ứng dụng che giấu tồn tại resource (có hệ thống chủ động trả 404 thay vì 403). Điều quan trọng là user không được nhận dữ liệu ngoài quyền của mình.

WithMockUser giúp kiểm tra mapping authorization trong một số trường hợp, nhưng không tự kiểm tra JWT signature, issuer hoặc token parsing. Vì thế phải có integration test gửi bearer token do test IdP cấp và chạy qua security filter thực tế.

### 14.3. Ví dụ test token với client HTTP

Một test ở mức cao có thể:

~~~text
1. Khởi động test issuer/JWKS với signing key thử nghiệm.
2. Tạo token đúng issuer, audience, scope và exp.
3. Gọi API qua HTTPS test endpoint với bearer token.
4. Xác nhận mã phản hồi và dữ liệu đúng tenant.
5. Tạo token có signature sai hoặc scope thiếu.
6. Gọi lại API; xác nhận bị từ chối và không lộ dữ liệu.
~~~

Những fixture token dùng khóa thử nghiệm, không dùng token truy cập thật. Nếu tích hợp trực tiếp IdP ngoài, cần môi trường sandbox và tài khoản test với permission tối thiểu.

### 14.4. Test certificate và TLS không dùng trust-all

Một integration test TLS có thể sử dụng một HTTPS server test tạo từ certificate do test CA cấp:

- Client tin test CA và kết nối đúng hostname thành công.
- Client không tin test CA bị từ chối.
- Client kết nối hostname khác SAN bị từ chối.
- Client có/không có certificate khi server yêu cầu mTLS được xử lý theo policy.

Đây là cách kiểm tra end-to-end cơ chế xác minh. Nếu test cần chứng minh fail-closed, không tạo TrustManager nhận tất cả certificate hoặc HostnameVerifier luôn trả true.

## 15. Java version, framework upgrade và nguy cơ thay đổi default

Một đợt migration có thể nâng đồng thời:

~~~text
JDK 8/11 ──> JDK 17/21
Spring Security / framework cũ ──> framework mới
HTTP client cũ ──> HttpClient mới
TLS/Keystore/Provider ──> cấu hình mới
Application Server / Container Image ──> runtime mới
~~~

Khi các biến đổi đồng thời, lỗi có thể xuất phát từ code config chứ không trực tiếp từ JDK.

### 15.1. Những mặc định cần kiểm tra

| Nhóm mặc định | Ví dụ khác biệt có thể xuất hiện |
|---|---|
| TLS protocol/ciphers | Tập được phép và ưu tiên thương lượng thay đổi. |
| Disabled algorithms | Certificate hoặc chữ ký cũ không còn được chấp nhận. |
| Truststore | Root CA hoặc truststore được nạp khác môi trường cũ. |
| Keystore | Store type/alias/provider khác, không nạp được private key. |
| HTTP redirects | Client/library có chính sách redirect và auth header khác nhau. |
| Proxy/forwarded headers | Scheme/host nhận diện khác, ảnh hưởng cookie và redirect URI. |
| Security filter order | Rule/route hoặc exception mapping khác. |
| Token claim mapping | Prefix ROLE_, scope mapping hoặc authorities khác. |
| Session serialization | Các phiên từ phiên bản cũ không tương thích rolling upgrade. |
| Timeouts/retries | Dễ lộ race condition khi token refresh hoặc certificate reload. |

Không nên khẳng định mọi JDK cùng version đều có security defaults giống hệt nhau: distribution, bản vá và file security properties có thể khác. CI và production cần công bố tập JDK được hỗ trợ và lưu thông tin build/runtime đủ để truy vết.

### 15.2. Phân biệt lỗi do JDK và lỗi do cấu hình

Quy trình điều tra nên tách:

1. Chạy artifact cũ trên JDK mới nếu tương thích để quan sát tác động runtime.
2. Chạy artifact mới trên JDK mục tiêu, ghi dependency/framework versions.
3. So sánh security settings, truststore, certificate và proxy path.
4. Dùng cùng fixture token/certificate và cùng policy test khi có thể.
5. Truy vết lỗi đến filter, token validator, TLS handshake, authorization policy hoặc provider.

Không cần chạy mọi tổ hợp nếu công nghệ không hỗ trợ; ghi rõ những tổ hợp không khả thi và kết luận có phạm vi.

## 16. CI pipeline và quản lý dữ liệu test nhạy cảm

### 16.1. Những kiểm tra nên tự động

Một pipeline bảo mật sau migration có thể gồm:

~~~text
Compile + unit tests
        │
        ▼
Authentication/authorization component tests
        │
        ▼
TLS/mTLS tests với test certificates
        │
        ▼
Integration tests với IdP/DB/broker test
        │
        ▼
Artifact/image verification
        │
        ▼
Staging E2E và security smoke tests
        │
        ▼
Release gate + evidence
~~~

Kiểm thử nên chạy trên JDK mục tiêu và runtime deployment thực tế. Nếu sản phẩm công bố hỗ trợ nhiều Java versions, CI nên bao gồm matrix tương ứng hoặc tối thiểu có bằng chứng xác nhận các môi trường được tuyên bố hỗ trợ.

### 16.2. Secret hygiene

Không đưa dữ liệu sau vào repository hoặc log build:

- Password thực, API key, bearer token còn hiệu lực.
- Private key của production/staging không dành cho CI test.
- Kết quả dump toàn bộ keystore hoặc nội dung secret manager.
- Refresh token và cookie phiên của người dùng thật.
- Thông tin định danh nhạy cảm không cần thiết trong debug trace.

Với test integration cần credential, dùng secret manager/CI secret có quyền hạn nhỏ nhất, cô lập môi trường và có quy trình rotation. Bản ghi kết quả test chỉ nên lưu metadata/correlation ID và chứng cứ không nhạy cảm.

### 16.3. Fail closed, không làm pipeline “xanh” giả

Không nên:

- Tắt tất cả security filter trong test rồi kết luận auth hoạt động.
- Mock một user luôn có quyền admin cho mọi endpoint.
- Bỏ qua xác minh JWT signature hoặc audience.
- Dùng trust-all certificate manager/hostname verifier để vượt lỗi TLS.
- Cho phép unknown role/scope được mặc định cấp quyền.
- Bỏ qua test bị lỗi vì môi trường IdP/TLS không ổn định mà không ghi nhận thiếu bằng chứng.

Nếu test environment thiếu service hoặc certificate cần thiết, nên báo rõ **test chưa được thực hiện** thay vì báo tất cả test thành công.

## 17. Quan sát production và an toàn khi rollout

Sau khi nâng JDK/security stack, cần theo dõi cả lỗi bị từ chối không mong muốn và truy cập được cho phép sai.

### 17.1. Chỉ số nên theo dõi

- Tỷ lệ đăng nhập thất bại theo loại nguyên nhân không nhạy cảm.
- Số phản hồi 401, 403 và tỷ lệ thay đổi so với baseline.
- Số sự kiện token hết hạn, issuer/audience mismatch hoặc JWKS refresh failure.
- TLS handshake failures và nhóm nguyên nhân certificate/trust/protocol.
- mTLS client authentication failures theo service identity đã chuẩn hóa.
- Số cảnh báo truy cập cross-tenant hoặc policy deny bất thường.
- Độ trễ của token verification, IdP redirect và outbound HTTPS.
- Tỷ lệ refresh token thất bại hoặc session reset khi rolling deployment.

Không coi tăng 403 đơn thuần là lỗi; có thể đó là việc chặn đúng các request trái phép. Cần đối chiếu hành vi trước/sau, principal và policy để phân biệt false positive/false negative.

### 17.2. Rollout và rollback

Một kế hoạch an toàn có thể gồm:

1. Triển khai staging theo topology mạng, proxy, certificate và IdP gần production.
2. Chạy regression matrix với positive/negative test trước release.
3. Canary một nhóm request/consumer có kiểm soát.
4. Quan sát 401/403, token validation, handshake và hoạt động backend.
5. Có tiêu chí rollback nếu truy cập hợp lệ bị chặn hàng loạt hoặc xuất hiện dấu hiệu vượt quyền.
6. Xác nhận rollback artifact, certificate, truststore, session schema và dependency vẫn khả thi.

Không chỉ rollback JDK nếu dữ liệu session, certificate trust, key rotation hoặc schema đã được chuyển đổi một chiều. Cần biết tổ hợp JDK + artifact + security configuration nào tương thích lẫn nhau trong giai đoạn chuyển tiếp.

### 17.3. Rotation certificate và signing key

Migration JDK có thể trùng thời điểm rotation khóa/chứng chỉ. Nếu cả hai thay đổi cùng lúc, lỗi khó truy vết.

Nên lập kế hoạch:

- Tách mốc cập nhật runtime và mốc rotation nếu có thể.
- Ghi thời điểm hiệu lực và thời hạn của khóa/chứng chỉ.
- Duy trì khoảng overlap theo chính sách để tránh gián đoạn khi consumer cache JWKS hoặc CA bundle.
- Kiểm tra token ký bằng khóa cũ và mới trong giai đoạn cho phép.
- Thu hồi/loại bỏ trust cũ đúng lịch sau khi consumer đã chuyển đổi.

Không mở rộng thời gian chấp nhận certificate/token quá hạn chỉ để kéo dài migration mà không có đánh giá bảo mật.

## 18. Mẫu báo cáo kiểm thử bảo mật sau chuyển đổi

Một báo cáo kết quả nên ghi:

| Trường | Nội dung |
|---|---|
| Artifact và commit | Tên service/library, version, build ID, checksum. |
| Java runtime | Version đầy đủ, distribution, OS/container image. |
| Framework/security libraries | Phiên bản Spring Security/OIDC client/JWT library/HTTP driver. |
| Identity provider | Loại IdP, môi trường test, issuer cấu hình (không chứa secret). |
| Authorization policy | Version rule/role/tenant matrix được kiểm tra. |
| TLS/mTLS topology | Endpoint logical names, truststore/keystore reference, proxy hops. |
| Certificate metadata | Validity, issuer/SAN/fingerprint khi được phép; không lưu private key. |
| Test cases | Positive/negative, expected result, actual result, pass/fail. |
| Gaps | Test chưa chạy, dependency môi trường thiếu, khác biệt staging/production. |
| Risk/owner | Lỗi tồn tại, người phụ trách, hạn xử lý hoặc ngoại lệ đã phê duyệt. |
| Release decision | Chấp nhận, chặn phát hành, cần kiểm tra bổ sung hoặc rollback plan. |

Ví dụ một ma trận ghi kết quả:

| Test ID | Mục tiêu | Expected | Evidence | Status |
|---|---|---|---|---|
| AUTH-01 | JWT đúng issuer/audience/signature được chấp nhận | 2xx cho resource hợp lệ | Integration test run ID | PASS/FAIL |
| AUTH-02 | JWT sai signature bị từ chối | 401/challenge theo contract | Security filter test log | PASS/FAIL |
| AUTHZ-01 | User A không đọc dữ liệu tenant B | Deny hoặc 404 theo policy | Data fixture + response | PASS/FAIL |
| TLS-01 | HTTPS certificate chain và SAN hợp lệ | Kết nối thành công | TLS test report | PASS/FAIL |
| TLS-02 | Certificate không được trust | Handshake bị từ chối | TLS test report | PASS/FAIL |
| MTLS-01 | Client thiếu cert trong endpoint yêu cầu mTLS | Kết nối bị từ chối | Mutual TLS test run | PASS/FAIL |
| SESSION-01 | Logout vô hiệu hóa session theo contract | Không thể dùng phiên cũ | Browser E2E run | PASS/FAIL |

Các giá trị PASS/FAIL chỉ được điền sau khi test thực sự chạy; bảng trên là mẫu cấu trúc, không phải kết quả của hệ thống cụ thể.

## 19. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
| Chỉ test đăng nhập thành công. | Không phát hiện lỗi cho phép credential/token giả. | Test cả expired, wrong signature, wrong audience, disabled user. |
| Test chỉ với admin. | Bỏ qua lỗi over-permission của user/tenant thường. | Ma trận role × action × resource. |
| Chỉ kiểm tra route, không kiểm tra resource ownership. | IDOR/cross-tenant data leak. | Dùng fixture nhiều tenant và negative resource tests. |
| Mock security filter ở mọi integration test. | Không phát hiện lỗi cấu hình framework. | Có test qua filter, token parser và IdP test. |
| Dùng trust-all SSL để chữa handshake. | Mất endpoint authentication, rủi ro MITM. | Sửa CA/truststore/certificate/SAN/protocol đúng chuẩn. |
| Chỉ kiểm tra certificate server bằng tên CN. | SAN/hostname mismatch có thể bị bỏ qua. | Giữ hostname verification chuẩn của HTTP client. |
| Cho JWT sai issuer/audience vẫn hợp lệ. | Token dành cho hệ thống khác có thể dùng sai mục đích. | Validate issuer/audience/signature/expiry theo allowlist. |
| Cho unknown role được phép mặc định. | Privilege escalation khi mapping đổi. | Deny-by-default và test role mapping. |
| Chỉ test trực tiếp localhost. | Bỏ qua ingress, mTLS, proxy, secure cookie. | Test đường đi triển khai thực. |
| Lưu raw token/key trong log. | Rò rỉ credential. | Log metadata tối thiểu và redaction. |
| Nhầm 401/403 thành mọi lỗi runtime. | Chẩn đoán sai, bỏ qua TLS hoặc policy failure. | Phân loại theo authn/authz/TLS và stack trace. |
| Chỉ nâng JDK không kiểm tra dependency. | Security provider/driver/framework không tương thích. | Ghi dependency graph và test trên artifact chạy thực. |
| Test xanh nhưng một nhóm test bị skip. | Bằng chứng thiếu vẫn bị xem là đạt. | Hiển thị test gaps và release gate. |

## 20. Quy trình thực hiện sau migration

Khi triển khai một lần nâng JDK/framework có liên quan bảo mật, có thể tiến hành:

**Bước 1 — Thu thập baseline.** Xác định auth flows, security rules, IdP, TLS endpoints, secrets, certificate stores, runtime và dependency versions.

**Bước 2 — Xây dựng danh sách rủi ro.** Phân nhóm token/credential, login/session, RBAC/ABAC/tenant, HTTPS/TLS/mTLS, database/broker và security provider.

**Bước 3 — Chuẩn bị fixtures.** Tạo tài khoản, token, resource nhiều tenant và certificate test; không dùng secret production.

**Bước 4 — Test tích cực.** Đăng nhập, API access, service-to-service và secure connection hợp lệ hoạt động theo contract.

**Bước 5 — Test bị từ chối.** Sai token, thiếu quyền, tài nguyên tenant khác, chứng chỉ sai/không tin cậy và các trường hợp session/CSRF bị từ chối đúng policy.

**Bước 6 — Test topology thật.** Thử qua gateway/ingress, load balancer, app server, container và IdP/DB/broker tương đương môi trường đích.

**Bước 7 — Phân tích khác biệt.** Tách nguyên nhân do JDK, JSSE/provider, framework security, cấu hình, secret/certificate và môi trường.

**Bước 8 — Chuẩn hóa cấu hình.** Sửa truststore, certificate, role mapping, security matcher hoặc token validation. Không dùng bypass auth/TLS để che regression.

**Bước 9 — Kiểm thử lại và lưu bằng chứng.** Chạy toàn bộ positive/negative matrix, lưu artifact identity, JDK, test result và gaps.

**Bước 10 — Rollout và quan sát.** Canary/staging trước, giám sát 401/403, handshake, JWT/JWKS, mTLS và cross-tenant anomalies, với rollback được chuẩn bị.

## 21. Kết luận

Kiểm thử bảo mật sau chuyển đổi Java phải xác nhận đồng thời **ai đang truy cập**, **được phép làm gì trên tài nguyên nào** và **kết nối có thực sự xác thực đúng đối tác qua kênh được bảo vệ hay không**. Nâng JDK có thể thay JSSE/TLS/security providers và ràng buộc certificate; nâng framework có thể thay filter, token claim mapping, cookie/CSRF hoặc cơ chế method security. Vì vậy, việc ứng dụng compile và trả HTTP 200 không đủ để khẳng định migration an toàn.

Một chiến lược đúng cần có baseline, ma trận positive/negative tests, fixture token và certificate an toàn, test qua topology runtime thực, validation theo issuer/audience/signature/scope, kiểm soát tenant/resource ownership, TLS hostname/certificate chain và mTLS identity. Kết quả phải có bằng chứng có thể tái tạo, nêu rõ phần chưa kiểm thử, và tránh mọi cách “sửa nhanh” bằng việc bỏ xác minh token, bỏ phân quyền hoặc tắt TLS verification.

Khi các kiểm thử này được đưa vào CI và kết hợp với quan sát sau triển khai, nhóm có thể nâng cấp JDK, framework và dependency mà vẫn duy trì hợp đồng truy cập hợp lệ, chặn truy cập trái phép và bảo vệ dữ liệu trên các kết nối cần thiết.
