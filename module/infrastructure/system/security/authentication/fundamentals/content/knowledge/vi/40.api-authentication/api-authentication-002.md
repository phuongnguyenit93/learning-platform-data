# Header credential

> **Chương:** Authentication trong API  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Truyền credential trong HTTP request header đúng chuẩn, bảo vệ bí mật trên đường truyền và tại proxy, phân biệt token với API key, đồng thời tránh giả mạo header và lỗi diễn giải giữa các thành phần.

## 1. Header credential là gì?

**Header credential** là thông tin xác thực được client gửi trong header của HTTP request để server hoặc gateway kiểm tra quyền truy cập. Credential có thể là access token trong header Authorization, API key trong một header được quy định, thông tin Basic authentication hoặc chữ ký request theo một giao thức đã thống nhất.

Ví dụ, một ứng dụng gọi API đơn hàng bằng access token:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Server đọc Authorization, xác minh token theo issuer, chữ ký hoặc introspection, audience, thời hạn và quyền. Nếu token hợp lệ, server tiếp tục kiểm tra principal có quyền xem các đơn hàng cụ thể hay không.

Header chỉ là vị trí truyền dữ liệu trong HTTP. Việc đặt một chuỗi vào header không làm nó trở thành credential đáng tin cậy. Server phải biết scheme nào được hỗ trợ, ai phát hành credential, credential đại diện cho chủ thể nào và request được phép làm gì.

### Kết quả học tập

Sau bài này, người học có thể:

- Giải thích vai trò của HTTP Authorization và các loại credential thường gặp.
- Phân biệt Bearer token, API key, Basic authentication, request signature và mTLS.
- Chọn header phù hợp theo giao thức và threat model.
- Xác minh token và quyền thay vì chỉ kiểm tra header có tồn tại.
- Bảo vệ credential khỏi log, proxy, browser, cache và lỗi cấu hình.
- Nhận diện header spoofing, duplicate header, parser disagreement và request smuggling.
- Thiết kế rotation, thu hồi, kiểm thử và quan sát an toàn cho API authentication.

## 2. Header không đồng nghĩa với authentication

HTTP request có nhiều header mô tả nội dung, ngữ cảnh và cách xử lý. Một số header mang dữ liệu nhạy cảm, nhưng không phải header nào cũng xác thực người gửi.

| Header | Mục đích | Có phải credential không? |
|---|---|---|
| Authorization | Mang credential theo authentication scheme | Có, tùy scheme và cách server xác minh |
| Proxy-Authorization | Xác thực với proxy | Có, dành cho proxy hop |
| Cookie | Gửi cookie, có thể chứa session identifier | Có thể mang bearer session credential |
| X-API-Key hoặc header API key được tài liệu hóa | Mang API key theo hợp đồng API | Có, nếu server xác minh key |
| Content-Type | Mô tả định dạng body | Không |
| Accept | Mô tả định dạng response client chấp nhận | Không |
| User-Agent | Mô tả client tự khai | Không |
| Origin | Nêu origin của request trong một số ngữ cảnh | Không phải bằng chứng danh tính |
| Forwarded / X-Forwarded-For | Thông tin proxy về đường đi hoặc địa chỉ client | Không tự xác thực client |
| X-Authenticated-User | Identity context nội bộ do proxy tạo | Chỉ đáng tin nếu có ranh giới và xác thực nguồn rõ ràng |

Server không được suy ra danh tính từ User-Agent, Origin, Referer hoặc X-Forwarded-For. Các giá trị này có thể bị client tự đặt hoặc bị thay đổi trên đường đi.

### Authentication và authorization là hai bước

Authentication trả lời: credential có hợp lệ và đại diện cho principal nào?

Authorization trả lời: principal đó có được phép thực hiện action trên resource cụ thể không?

Một API key hợp lệ có thể nhận diện ứng dụng tích hợp nhưng không tự chứng minh người dùng cuối là ai. Một access token hợp lệ có thể xác định subject và scope, nhưng API vẫn phải kiểm tra quyền truy cập bản ghi hoặc tenant cụ thể.

## 3. Authorization header và authentication scheme

HTTP dùng header Authorization để mang credential theo scheme. Cú pháp tổng quát:

~~~http
Authorization: <scheme> <credentials>
~~~

Scheme xác định cách diễn giải credentials. Server chỉ nên chấp nhận các scheme đã cấu hình và xử lý theo đúng chuẩn tương ứng.

### Bearer

Bearer token cho phép bên đang sở hữu token sử dụng nó. Với OAuth 2.0, cách gửi phổ biến là:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

Ưu điểm:

- Được hỗ trợ rộng trong hệ sinh thái HTTP/OAuth.
- Có thể giới hạn theo issuer, audience, scope và thời hạn.
- Phù hợp với API access token và token ngắn hạn.

Rủi ro:

- Ai lấy được bearer token có thể dùng token trong phạm vi và thời hạn của nó.
- Token có thể bị lộ qua log, trace, crash dump, browser extension hoặc proxy.
- Nếu token có audience/scope rộng, một lần lộ có thể ảnh hưởng nhiều API.

Biện pháp:

- Chỉ truyền qua HTTPS.
- Không đưa token vào URL, query string hoặc tên file.
- Dùng audience và scope tối thiểu.
- Đặt lifetime phù hợp và có cơ chế thu hồi/introspection khi cần.
- Không ghi giá trị token vào log hoặc telemetry.
- Với rủi ro replay cao, cân nhắc sender-constrained token như mTLS-bound access token hoặc DPoP theo profile hỗ trợ.

### Basic

Basic authentication gửi username và password được mã hóa Base64:

~~~http
Authorization: Basic <BASE64_USER_COLON_PASSWORD>
~~~

Base64 chỉ là encoding, không phải encryption. Bất kỳ ai đọc được request đều có thể khôi phục username và password. Basic chỉ được dùng qua TLS và trong trường hợp có lý do tương thích rõ ràng; không dùng nó để gửi mật khẩu qua HTTP thuần.

Với API hiện đại, thường nên ưu tiên cơ chế token hoặc phương thức xác thực mạnh phù hợp thay vì gửi password ở mọi request.

### Custom authentication scheme

Một API có thể định nghĩa scheme riêng, nhưng phải có tài liệu chính xác về định dạng, cách xác minh, lỗi, lifetime, rotation và tương thích proxy. Không tự tạo scheme sơ sài nếu OAuth, HTTP authentication hoặc một chuẩn chữ ký request đã đáp ứng nhu cầu.

## 4. API key trong header

API key là credential thường dùng để nhận diện ứng dụng, tích hợp hoặc consumer của một API. API key có thể được gửi trong header riêng theo hợp đồng của API:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.test
X-API-Key: <API_KEY>
Accept: application/json
~~~

Tên header có thể khác nhau giữa các API. Điều quan trọng là client và server phải thống nhất một vị trí duy nhất, không cho phép nhiều nguồn credential gây mơ hồ.

### API key thường chứng minh điều gì?

API key thường chứng minh request có một secret được cấp cho ứng dụng hoặc integration. Nó không mặc nhiên xác thực một con người. Nếu nhiều người cùng dùng một key, server chỉ có thể quy request cho key hoặc integration đó, không thể khẳng định chính xác người đã bấm nút.

### API key và access token

| Đặc điểm | API key | OAuth access token |
|---|---|---|
| Chủ thể thường đại diện | Ứng dụng/integration | User, client hoặc workload theo grant |
| Quyền | Thường gắn với key/config phía server | Có thể biểu diễn scope/claims hoặc quyền qua introspection |
| Thời hạn | Có thể dài hoặc không có expiry tùy thiết kế | Thường có lifetime được xác định |
| Audience | Có thể giới hạn bằng cấu hình API | Có thể được ràng buộc rõ qua aud/resource |
| Thu hồi | Thường qua key registry | Qua expiry, revocation, introspection hoặc grant management |
| Phân quyền người dùng | Không tự cung cấp | Có thể mang delegated user context |

Không chọn API key chỉ vì dễ triển khai. Nếu cần quyền thay mặt user, scope theo resource hoặc delegation, access token phù hợp thường rõ ràng hơn.

### API key không nên là secret phía browser

Nếu nhúng API key bí mật vào JavaScript, mobile bundle hoặc ứng dụng desktop phân phối cho người dùng, attacker có thể trích xuất key. CORS không che giấu API key và không biến client public thành môi trường giữ secret.

Với browser/mobile public client, dùng backend-for-frontend hoặc flow OAuth phù hợp, public-client security và token có scope/audience giới hạn. Nếu API key chỉ là public identifier có quota thấp, phải thiết kế và công bố rõ rằng nó không phải bí mật xác thực.

## 5. Proxy-Authorization và các hop HTTP

Authorization và Proxy-Authorization có mục đích khác nhau:

- Authorization gửi credential tới origin server hoặc API.
- Proxy-Authorization gửi credential để xác thực với proxy.

Proxy-Authorization thuộc một hop proxy và không nên bị chuyển tiếp như credential của origin server. Proxy có thể xóa header này sau khi xác thực với chính nó.

### Ranh giới proxy

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant P as Forward Proxy
    participant G as API Gateway
    participant A as API Service
    C->>P: Request + Proxy-Authorization
    P->>P: Xác thực client với proxy
    P->>G: Request qua TLS, bỏ credential proxy
    G->>G: Xác minh Authorization của API
    G->>A: Request + context đã xác minh
    A->>A: Authorization cho resource
~~~

Không để proxy ghi log toàn bộ header nhạy cảm. Không giả định TLS từ client tới proxy bảo vệ tiếp đoạn proxy tới gateway; cần xác định rõ từng TLS hop và trust boundary.

## 6. HMAC request signing

Một số API dùng chữ ký request thay cho hoặc bổ sung API key bearer. Client và server chia sẻ secret hoặc dùng cơ chế khóa công khai để xác minh chữ ký. Chữ ký ràng buộc request với một số thành phần như method, path, timestamp, nonce và digest body.

### Mục đích

- Phát hiện request bị sửa đổi sau khi ký.
- Gắn proof với nội dung và ngữ cảnh request.
- Hạn chế replay khi có timestamp/nonce và server theo dõi việc sử dụng.
- Có thể xác minh caller sở hữu key đã đăng ký.

### Thành phần thường cần ràng buộc

- HTTP method.
- Canonical request target/path và query theo quy tắc đã chuẩn hóa.
- Host hoặc authority nếu profile yêu cầu.
- Một tập header được ký rõ ràng.
- Digest của body.
- Timestamp có giới hạn tuổi.
- Nonce hoặc request identifier dùng một lần.
- Key ID để chọn public key/secret tương ứng.

### Ví dụ header minh họa

~~~http
POST /v1/transfers HTTP/1.1
Host: api.example.test
X-Key-Id: client-42
X-Request-Date: 2026-11-22T06:00:00Z
X-Request-Nonce: <RANDOM_NONCE>
X-Content-Digest: <BODY_DIGEST>
Authorization: Signature <REQUEST_SIGNATURE>
Content-Type: application/json
~~~

Đây chỉ là ví dụ cấu trúc, không phải một chuẩn chữ ký hoàn chỉnh. Triển khai thật cần dùng một profile đã được chuẩn hóa hoặc tài liệu giao thức thống nhất; không tự ký một chuỗi tùy ý rồi giả định mọi proxy và server tạo ra cùng canonical representation.

### Canonicalization là phần khó

Hai thành phần có thể diễn giải khác nhau về:

- Thứ tự hoặc cách viết header.
- Header lặp và dấu phẩy trong giá trị.
- Percent-encoding của path/query.
- Dấu gạch chéo, dấu chấm và path normalization.
- Khoảng trắng và line ending.
- Body đã được giải nén hay còn ở dạng wire.
- Host/authority khi qua proxy.

Nếu client ký một representation nhưng server xác minh representation khác, request hợp lệ có thể bị từ chối. Nguy hiểm hơn, nếu gateway và backend chuẩn hóa khác nhau, attacker có thể khai thác parser differential.

### Chống replay

Chữ ký hợp lệ không tự chống replay. Một request đã ký có thể bị gửi lại nếu server không kiểm tra freshness và tính duy nhất.

- Timestamp phải nằm trong cửa sổ cho phép.
- Nonce/request ID phải được ghi nhận trong thời gian phù hợp.
- Request nhạy cảm cần idempotency key hoặc transaction identifier.
- Server cần xử lý race condition khi cùng nonce đến đồng thời.
- Đồng hồ giữa các bên phải được đồng bộ trong giới hạn.

Không tự thiết kế thuật toán mật mã hoặc cách ghép chuỗi nếu có chuẩn phù hợp. Quản lý secret/key, rotation và compromise response cũng quan trọng như việc tính chữ ký.

## 7. mTLS và credential ở tầng kết nối

Mutual TLS (mTLS) xác thực cả server lẫn client trong TLS handshake bằng chứng chỉ. Danh tính client được suy ra từ chứng chỉ và trust policy của server.

mTLS khác với Authorization header:

- Chứng chỉ client được trình ở tầng TLS, trước khi HTTP request được xử lý.
- Authorization header là dữ liệu thuộc HTTP request.
- mTLS có thể xác thực workload/service hoặc client được cấp certificate.
- Access token vẫn có thể cần để biểu diễn user, scope hoặc delegation.

Một API nội bộ có thể dùng mTLS để xác thực service identity và access token để biểu diễn user context. Hai lớp này bổ sung cho nhau.

### TLS termination tại gateway

Nếu TLS kết thúc ở gateway, backend không tự nhìn thấy TLS client certificate gốc trừ khi gateway chuyển thông tin đã xác minh qua một kênh tin cậy và có cơ chế bảo vệ. Backend không được tin header chứa subject của certificate nếu client Internet có thể gửi header đó trực tiếp.

Thiết kế cần:

- Chỉ gateway được phép kết nối backend theo network policy/mTLS.
- Gateway xóa header certificate identity do client tự gửi.
- Gateway xác minh certificate chain, validity, EKU và identity mapping.
- Backend chỉ tin context do gateway phát hành theo cơ chế đã thống nhất.
- Có rotation và thu hồi certificate ở cả gateway lẫn backend.

## 8. Xác minh credential ở API server

Một quy trình xác minh cần tách kiểm tra định dạng khỏi kiểm tra tính hợp lệ và authorization.

### Với Bearer access token

1. Đọc đúng Authorization scheme; từ chối scheme không hỗ trợ.
2. Xác minh chữ ký theo issuer, key và thuật toán được cho phép, hoặc gọi introspection cho opaque token.
3. Kiểm tra issuer và audience.
4. Kiểm tra thời hạn và các claim thời gian được profile sử dụng.
5. Kiểm tra scope/permission và client/actor context nếu có.
6. Xác định principal theo issuer và subject ổn định.
7. Kiểm tra authorization trên resource, tenant và action cụ thể.
8. Ghi audit tối thiểu, không ghi token.

Không chỉ decode JWT rồi tin nội dung. Decode không phải verify. Không chấp nhận thuật toán tùy ý do token tự khai; thuật toán phải đến từ cấu hình tin cậy.

### Với API key

1. Kiểm tra header đúng tên và chỉ có một giá trị theo quy ước.
2. Tra key ID hoặc verifier trong registry.
3. So sánh secret theo cách an toàn, tránh timing leak nếu tự xác minh.
4. Kiểm tra trạng thái active, expiry và revocation.
5. Xác định owner, application và scope.
6. Kiểm tra quota, rate limit và resource authorization.
7. Ghi key ID đã che/mã hóa một chiều phù hợp, không ghi key thô.

Nếu key là giá trị ngẫu nhiên dài, server có thể lưu verifier/HMAC thay vì secret thô. Cần bảo vệ pepper/HMAC key trong secret manager và có kế hoạch xoay vòng.

### Trả lỗi đúng nghĩa

| Tình huống | Phản hồi thường dùng |
|---|---|
| Thiếu hoặc credential không hợp lệ | 401 Unauthorized, kèm challenge phù hợp khi cần |
| Credential hợp lệ nhưng không đủ quyền | 403 Forbidden |
| Request sai cú pháp/thiếu header bắt buộc theo hợp đồng | 400 Bad Request hoặc lỗi xác thực theo profile |
| Quá giới hạn request | 429 Too Many Requests |

Không trả thông tin chi tiết giúp attacker biết key ID nào tồn tại, token sai ở claim nào hoặc principal nào có quyền. Log nội bộ có thể lưu reason code an toàn hơn để vận hành.

## 9. Header spoofing và trust boundary

Header là input từ bên gửi. Một client có thể tự thêm các header như:

~~~http
X-Authenticated-User: admin
X-User-Role: superuser
X-Tenant-ID: tenant-other
X-Forwarded-For: 10.0.0.5
~~~

Nếu gateway chuyển nguyên các header này tới backend và backend tin chúng, attacker có thể giả mạo danh tính, role, tenant hoặc địa chỉ nguồn.

### Quy tắc xử lý

1. Ở edge, xóa các header identity/trust do client gửi.
2. Chỉ tạo header nội bộ sau khi xác thực request.
3. Chặn truy cập trực tiếp vào backend từ Internet nếu backend chỉ tin gateway.
4. Xác thực gateway bằng mTLS, network policy hoặc cơ chế workload identity.
5. Backend xác minh token/assertion hoặc nguồn context theo hợp đồng.
6. Không dùng X-Forwarded-For làm credential hoặc bằng chứng user identity.
7. Xác định chính xác proxy nào được phép thêm Forwarded/X-Forwarded-*.

### Header forwarding phải có allowlist

Không chuyển tiếp mọi header không phân biệt. Chỉ forward những header cần thiết cho downstream, loại bỏ credential dành cho hop trước và các header không tin cậy. Tài liệu hóa header nào do client, gateway hay service tạo.

## 10. Duplicate headers và parser disagreement

HTTP có thể cho phép một số header xuất hiện nhiều lần hoặc gộp giá trị theo quy tắc riêng. Với credential header, nhiều giá trị có thể tạo ra cách hiểu khác nhau giữa CDN, load balancer, proxy, framework và ứng dụng.

Ví dụ:

~~~http
Authorization: Bearer <TOKEN_A>
Authorization: Bearer <TOKEN_B>
~~~

Một thành phần có thể chọn giá trị đầu, thành phần khác chọn giá trị cuối hoặc gộp thành một chuỗi. Nếu các tầng không thống nhất, request có thể vượt qua một lớp kiểm tra rồi được xử lý khác ở lớp sau.

### Biện pháp

- Quy định một Authorization header duy nhất.
- Từ chối request có credential header trùng hoặc mơ hồ.
- Chuẩn hóa và kiểm tra tại edge trước khi chuyển tiếp.
- Đảm bảo proxy và backend dùng cùng quy tắc parsing.
- Kiểm thử header casing, whitespace, comma folding và HTTP/2-to-HTTP/1 translation.
- Cập nhật parser/proxy để xử lý theo chuẩn HTTP hiện hành.

### Liên hệ với request smuggling

Request smuggling thường xuất phát từ việc các thành phần diễn giải framing hoặc header khác nhau, chẳng hạn Content-Length và Transfer-Encoding. Credential header không phải nguyên nhân duy nhất, nhưng parser disagreement có thể làm request được xác thực ở một thành phần và diễn giải khác ở thành phần kế tiếp. Cần giữ parser nhất quán, cập nhật proxy và kiểm thử các ranh giới HTTP version.

## 11. Bảo vệ credential trên đường truyền và trong hệ thống

### TLS bắt buộc

- Chỉ gửi credential qua HTTPS/TLS.
- Dùng cấu hình TLS hiện đại và chứng chỉ server hợp lệ.
- Không cho phép downgrade sang HTTP cho endpoint xác thực.
- Với service-to-service, xác minh hostname/certificate và cân nhắc mTLS.
- Xác định rõ TLS termination và bảo vệ mọi hop phía sau.

### Không đưa credential vào URL

Query string có thể xuất hiện trong browser history, proxy log, analytics, referrer, monitoring và screenshot. Không dùng dạng:

~~~http
GET /v1/orders?api_key=<SECRET>
~~~

Đặt credential trong header theo giao thức đã thống nhất. Với form đăng nhập, gửi password qua body trên HTTPS và xử lý như secret; không đưa password vào URL.

### Redaction trong log và tracing

Các header cần được che hoặc loại bỏ khỏi log mặc định:

- Authorization.
- Proxy-Authorization.
- Cookie và Set-Cookie.
- X-API-Key hoặc header secret tương đương.
- Signature, nonce hoặc dữ liệu xác thực nhạy cảm theo profile.

Chỉ ghi key ID, scheme, kết quả và reason code an toàn khi cần. Không ghi token thô để tiện debug.

### Cache và response

Không để response chứa dữ liệu nhạy cảm được cache dùng chung ngoài ý muốn. Dùng Cache-Control phù hợp, phân vùng cache theo principal khi có lý do và không đưa credential vào cache key hoặc log. CDN/gateway phải được cấu hình rõ header nào được forward, cache hay loại bỏ.

## 12. CORS và browser client

CORS kiểm soát việc browser cho phép JavaScript ở origin nào đọc response cross-origin. CORS không phải authentication và không bảo vệ API key bí mật đã nhúng trong JavaScript.

### Authorization header và preflight

Khi browser gửi Authorization hoặc custom header không thuộc nhóm simple request, nó thường thực hiện CORS preflight bằng OPTIONS. Server cần cấu hình:

- Allow-Origin chỉ cho origin được phép.
- Allow-Methods chỉ cho method cần thiết.
- Allow-Headers bao gồm Authorization hoặc header tùy chỉnh cần thiết.
- Allow-Credentials chỉ bật khi thật sự cần cookie credential.
- Không dùng wildcard origin cùng credentialed request.

### Đừng nhầm CORS với quyền truy cập

Một client ngoài browser có thể gọi API mà không bị CORS chặn. CORS không ngăn curl, script server-side hoặc malware. API vẫn phải xác thực credential và authorization cho từng request.

### Tránh lưu secret trong frontend

Không nhúng API key dùng chung trong bundle JavaScript, source map, mobile package hoặc cấu hình tải công khai. Mọi secret phía client có thể bị trích xuất. Dùng backend giữ secret hoặc flow public client được thiết kế đúng.

## 13. Rotation và thu hồi header credential

Header chỉ là cách vận chuyển. Credential bên trong vẫn cần vòng đời riêng.

### API key rotation

1. Xác định key ID, owner, consumer và quyền hiện tại.
2. Tạo key mới với scope tối thiểu.
3. Đăng ký key mới ở server và phân phối qua secret manager.
4. Cập nhật consumer theo từng đợt.
5. Theo dõi traffic theo key ID để xác nhận migration.
6. Thu hồi key cũ sau cửa sổ overlap có deadline.
7. Kiểm thử key cũ bị từ chối.

Nếu key cũ bị lộ, ưu tiên revoke khẩn cấp; không chờ overlap bình thường chỉ để tránh downtime.

### Access token

Access token thường được thay mới qua authorization server. Khi token bị lộ, cần đánh giá lifetime, refresh token/grant, introspection, denylist và session liên quan. Thu hồi refresh token không nhất thiết vô hiệu hóa ngay một JWT access token đã phát hành nếu resource server không kiểm tra trạng thái.

### Request-signing key

Với HMAC hoặc asymmetric signing key, cần:

- Key ID/version rõ ràng.
- Hỗ trợ key mới trước khi dừng key cũ trong overlap.
- Giới hạn thời gian chấp nhận key cũ.
- Xoay key xác minh và signing theo quy trình được kiểm thử.
- Thu hồi khẩn cấp và điều tra request đã ký nếu nghi compromise.

## 14. Ví dụ gọi API an toàn

Ví dụ client dùng access token đã nhận qua OAuth flow phù hợp:

~~~bash
curl --fail-with-body \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  --header "Accept: application/json" \
  https://api.example.test/v1/orders
~~~

ACCESS_TOKEN ở đây là placeholder lấy từ cơ chế cấp token được bảo vệ; không hardcode token vào source code hoặc shell history. Trong CI/CD, lấy secret từ secret manager hoặc workload identity.

Ví dụ API key theo hợp đồng API:

~~~bash
curl --fail-with-body \
  --header "X-API-Key: $API_KEY" \
  --header "Accept: application/json" \
  https://api.example.test/v1/reports
~~~

Không dùng API key trong frontend public. Nếu chạy lệnh trên máy dùng chung, shell history hoặc process inspection có thể làm lộ giá trị tùy môi trường; dùng cơ chế secret injection phù hợp.

## 15. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng vệ |
|---|---|---|
| API key trong query string | Lộ qua URL, history, log và referrer | Dùng header theo hợp đồng |
| Basic auth qua HTTP | Lộ username/password | Chỉ qua TLS; ưu tiên cơ chế token phù hợp |
| Tin header X-User từ client | Giả mạo principal | Strip header tại edge và xác minh nguồn |
| Chỉ kiểm tra Authorization có tồn tại | Credential giả hoặc hết hạn vẫn qua | Xác minh scheme, issuer, chữ ký, audience, expiry |
| Dùng ID token gọi API | Nhầm mục đích token | Dùng access token đúng audience |
| API key dùng chung cho người dùng | Không quy được trách nhiệm, khó thu hồi riêng | Key riêng theo app/workload; delegated token cho user |
| API key nhúng trong JavaScript | Người dùng/attacker trích xuất được | Backend giữ secret hoặc public-client flow |
| Log toàn bộ header | Lộ bearer token, cookie và key | Redaction và allowlist |
| Tin X-Forwarded-For | Giả mạo nguồn hoặc bypass policy | Chỉ tin proxy đã cấu hình |
| Chấp nhận duplicate Authorization | Parser disagreement | Từ chối header trùng |
| Chữ ký không có nonce/timestamp | Replay request | Freshness, nonce store và idempotency |
| HMAC canonicalization tùy tiện | Proxy/client/server diễn giải khác | Dùng profile chuẩn và test interoperability |
| CORS được xem là authentication | API vẫn bị gọi từ client khác | Xác thực/authorization server-side |
| Thu hồi key nhưng cache vẫn chấp nhận | Credential cũ tiếp tục hoạt động | Kiểm tra propagation, cache và mọi consumer |

## 16. Tình huống thực hành: API gateway và backend

**Bối cảnh:** Một ứng dụng đối tác gọi Public API qua API Gateway. Gateway xác minh API key của đối tác và chuyển request tới Report Service. Report Service cần biết ứng dụng nào gọi, tenant nào được phép truy cập và người dùng cuối có được phép xem báo cáo hay không.

### Thiết kế

1. Gateway nhận đúng một header API key theo hợp đồng.
2. Gateway tra key registry, kiểm tra trạng thái, owner, expiry, scope và quota.
3. Gateway xóa các header identity/tenant do đối tác tự gửi.
4. Gateway xác thực với Report Service bằng service identity riêng.
5. Gateway tạo context tin cậy có partner principal và tenant được tra từ registry.
6. Report Service xác minh nguồn gateway/context và kiểm tra quyền trên resource.
7. Nếu cần user context, đối tác phải dùng flow delegated identity được hỗ trợ; API key không giả làm user.
8. Audit ghi partner/client, service actor, tenant, report resource và kết quả.

### Nếu đối tác gửi X-Tenant-ID của tenant khác?

Gateway không tin giá trị đó. Tenant được lấy từ mapping đã xác minh của key hoặc grant; nếu đối tác có nhiều tenant, request phải dùng cơ chế chọn tenant có kiểm tra membership và policy.

### Nếu API key bị lộ?

- Thu hồi key trong registry.
- Kiểm tra request theo key ID và thời điểm lộ.
- Cấp key mới cho đối tác qua kênh bảo vệ.
- Kiểm tra cache và mọi gateway/region đã nhận trạng thái revoke.
- Đánh giá dữ liệu đã truy cập và thông báo theo incident policy.

## 17. Kiểm thử header credential

Kiểm thử trong môi trường được phép với key/token giả lập:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Request thiếu Authorization | 401 hoặc challenge theo API contract |
| Bearer token sai chữ ký | Bị từ chối |
| Token có issuer không được tin cậy | Bị từ chối |
| Token có audience khác API | Bị từ chối |
| Token hết hạn | Bị từ chối |
| Token hợp lệ nhưng thiếu scope | 403 hoặc lỗi policy tương ứng |
| ID token được gửi tới resource API | Bị từ chối theo profile |
| API key không tồn tại | Bị từ chối, không tiết lộ key nào hợp lệ |
| API key đã revoked/expired | Bị từ chối ở mọi gateway/region |
| API key gửi qua query string | Không được chấp nhận |
| Duplicate Authorization header | Request bị từ chối nhất quán ở mọi hop |
| Header casing/whitespace bất thường | Parser xử lý nhất quán hoặc từ chối |
| Client tự gửi X-Authenticated-User: admin | Gateway strip/overwrite; backend không nâng quyền |
| Client tự gửi X-Tenant-ID khác | Không thể truy cập tenant khác |
| X-Forwarded-For giả | Không được dùng như bằng chứng identity |
| Proxy-Authorization tới origin | Không bị forward như API credential |
| Credential qua HTTP | Redirect/chặn theo policy; không xử lý secret trên plaintext |
| Token xuất hiện trong access log | Redaction ngăn lưu giá trị |
| HMAC request bị sửa body/path | Chữ ký không hợp lệ |
| HMAC request replay cùng nonce | Request lặp bị từ chối hoặc idempotent theo policy |
| Clock lệch ngoài cửa sổ | Chữ ký bị từ chối và có reason code an toàn |
| CORS preflight không được phép | Browser không được phép đọc response; server vẫn xác thực độc lập |
| Secret trong frontend bundle | Secret scanning/build review phát hiện |
| Credential cũ sau rotation | Bị từ chối sau deadline revoke |

### Chỉ số vận hành

- Tỷ lệ request theo authentication scheme.
- Tỷ lệ 401/403 theo reason code an toàn.
- Số API key active không có owner hoặc scope rõ.
- Thời gian từ revoke đến khi mọi region từ chối credential.
- Số lần header spoofing/duplicate bị chặn.
- Số secret bị phát hiện trong log, trace hoặc frontend artifact.
- Tỷ lệ token exchange/introspection lỗi và độ trễ.
- Số request ký số bị từ chối do replay hoặc canonicalization.

## 18. Checklist thiết kế header credential

- [ ] Chọn một authentication scheme được tài liệu hóa cho API.
- [ ] Dùng Authorization cho Bearer token theo chuẩn.
- [ ] Phân biệt API key của application với access token đại diện user/delegation.
- [ ] Không dùng Basic nếu không có lý do; nếu dùng phải bắt buộc TLS.
- [ ] Không gửi credential trong URL/query string.
- [ ] Xác minh issuer, audience, signature/introspection, expiry và scope.
- [ ] API key có owner, key ID, scope, expiry/rotation policy và revocation.
- [ ] Không nhúng secret vào JavaScript hoặc public client bundle.
- [ ] Dùng HMAC/request signing theo profile chuẩn; có nonce, timestamp và body/path binding.
- [ ] Xử lý Proxy-Authorization đúng phạm vi proxy hop.
- [ ] TLS bảo vệ mọi hop và trust boundary được tài liệu hóa.
- [ ] Gateway xóa identity header do client tự gửi.
- [ ] Chỉ tin Forwarded/X-Forwarded-* từ proxy đã xác thực.
- [ ] Từ chối duplicate hoặc credential header mơ hồ.
- [ ] Proxy, gateway và backend thống nhất parsing/canonicalization.
- [ ] Redact Authorization, Cookie, API key và signature khỏi log/trace.
- [ ] CORS không được xem là authentication hoặc giữ bí mật client-side.
- [ ] Rotation có overlap giới hạn và xác minh key cũ bị từ chối.
- [ ] Kiểm thử spoofing, replay, parser disagreement, expiry và revocation.
- [ ] Authorization luôn được kiểm tra trên action, resource và tenant.

## Ghi nhớ

Header credential là cách vận chuyển credential trong HTTP, không phải bằng chứng tin cậy tự thân. Authorization Bearer thường mang access token; API key thường nhận diện application/integration; Basic mang username/password được Base64 encoding; HMAC signing ràng buộc request; mTLS xác thực client ở tầng TLS. Mỗi cơ chế có semantics và giới hạn riêng.

Chỉ chấp nhận scheme được tài liệu hóa, xác minh credential và authorization ở server, bảo vệ TLS trên mọi hop, loại bỏ identity header do client tự khai, từ chối header trùng/mơ hồ và redaction secret khỏi log. Credential phải có owner, scope, thời hạn, rotation và thu hồi; không để gateway hoặc CORS thay thế việc kiểm tra quyền tại API.
