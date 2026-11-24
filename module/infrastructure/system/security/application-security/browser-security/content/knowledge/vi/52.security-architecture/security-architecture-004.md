# API gateway

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vị trí của API gateway trong kiến trúc ứng dụng web và các trust boundary mà gateway kiểm soát.
- Phân biệt API gateway, reverse proxy, load balancer, ingress controller, service mesh và Backend for Frontend (BFF).
- Thiết kế routing theo host, path, method và phiên bản API với allowlist rõ ràng.
- Xác định trách nhiệm của gateway trong TLS, xác thực, phân quyền, CORS, CSRF, rate limiting và kiểm soát request.
- Hiểu cách truyền danh tính và header qua nhiều proxy mà không tin dữ liệu do client tự gửi.
- Thiết kế timeout, retry, circuit breaker, giới hạn body, cache và xử lý lỗi phù hợp.
- Bảo vệ gateway trước path confusion, request smuggling, SSRF, header injection và lộ dữ liệu.
- Thiết lập logging, tracing, metrics và quy trình kiểm thử bảo mật cho gateway.

## 1. API gateway là gì?

API gateway là điểm vào được quản lý cho các API của một hệ thống. Client gửi request đến gateway; gateway kiểm tra chính sách chung, chọn dịch vụ đích, chuyển tiếp request và trả response. Gateway thường nằm trước một hoặc nhiều dịch vụ backend.

Trong ứng dụng web, trình duyệt có thể gọi một hostname API công khai, ví dụ https://api.example.test. Gateway nhận request đó và định tuyến đến dịch vụ phù hợp:

- /api/v1/accounts/* đến Account Service.
- /api/v1/orders/* đến Order Service.
- /api/v1/catalog/* đến Catalog Service.

Gateway giúp tập trung các chính sách ở ranh giới API như TLS, xác thực token, giới hạn tốc độ, giới hạn kích thước request, CORS, ghi nhận request ID và routing. Nó cũng có thể tổng hợp response hoặc chuyển đổi giao thức khi kiến trúc có nhu cầu rõ ràng.

Gateway không tự động làm cho backend an toàn. Nếu dịch vụ phía sau tin mọi request đến từ mạng nội bộ, kẻ tấn công có thể bỏ qua gateway khi tìm được đường truy cập trực tiếp. Mỗi dịch vụ vẫn cần xác thực danh tính dịch vụ, kiểm tra quyền nghiệp vụ, xác thực dữ liệu và xử lý lỗi an toàn.

### 1.1. Vị trí trong kiến trúc

~~~mermaid
flowchart LR
    B["Browser / Mobile Client"] -->|HTTPS| E["Edge / CDN / WAF"]
    E --> G["API Gateway"]
    G -->|mTLS / service identity| A["Account Service"]
    G -->|mTLS / service identity| O["Order Service"]
    G -->|mTLS / service identity| C["Catalog Service"]
    A --> D[("Account DB")]
    O --> D2[("Order DB")]
    C --> D3[("Catalog DB")]
    G --> M["Logs / Metrics / Traces"]
~~~

Luồng điển hình:

1. Client kết nối đến hostname công khai qua HTTPS.
2. Edge hoặc CDN tiếp nhận kết nối, áp dụng các chính sách ở lớp biên nếu có.
3. API gateway kiểm tra host, route, method, giới hạn request và chính sách xác thực phù hợp.
4. Gateway chuyển request đến backend qua mạng nội bộ được kiểm soát, thường dùng TLS hoặc mTLS.
5. Backend xác minh danh tính và quyền trên tài nguyên, thực hiện nghiệp vụ.
6. Gateway trả response và ghi telemetry đã loại bỏ dữ liệu nhạy cảm.

Edge, WAF và gateway có thể được triển khai trong cùng một nền tảng, nhưng cần phân định rõ thành phần nào sở hữu từng chính sách. Một header CORS bị thêm ở cả CDN và gateway có thể tạo response không hợp lệ; hai lớp rate limit không phối hợp có thể khóa nhầm client.

### 1.2. Trust boundary

Mỗi chặng của request có một mức tin cậy khác nhau:

| Ranh giới | Dữ liệu cần coi là không tin cậy | Kiểm soát cần có |
|---|---|---|
| Browser → Edge | URL, method, body, cookie, Authorization, Origin, forwarding headers | TLS, kiểm tra request, giới hạn kích thước, chống lạm dụng |
| Edge → Gateway | Header được proxy thêm hoặc giữ lại, IP nguồn, protocol | Chỉ tin proxy đã xác thực; chuẩn hóa forwarding headers |
| Gateway → Service | Danh tính người gọi, token/claim, path và header đã chuyển tiếp | TLS/mTLS, service identity, allowlist route |
| Service → Database | ID đối tượng, tenant, filter, dữ liệu nghiệp vụ | Authorization, parameterized query, transaction |
| Gateway → Telemetry | URL, body, header, lỗi và định danh người dùng | Redaction, kiểm soát truy cập, thời hạn lưu |

Không coi một request là đáng tin chỉ vì nó đi qua gateway. Gateway là một lớp thực thi policy; backend vẫn phải bảo vệ tài nguyên của mình.

## 2. Phân biệt các thành phần ở lớp API

| Thành phần | Trách nhiệm chính | Câu hỏi cần trả lời |
|---|---|---|
| Reverse proxy | Nhận request và chuyển tiếp đến upstream | Request đi đến máy chủ nào? |
| Load balancer | Phân phối request giữa các instance | Instance nào còn khả dụng? |
| API gateway | Quản lý điểm vào API, policy, routing và telemetry | Ai được gọi API nào, theo giới hạn nào? |
| Ingress controller | Công bố route từ bên ngoài vào cluster | Host/path nào đi vào service nào? |
| Service mesh | Quản lý giao tiếp service-to-service | Các service xác thực và quan sát nhau thế nào? |
| BFF | API được thiết kế riêng cho một loại client hoặc trải nghiệm | Browser cần dữ liệu nào và theo hình dạng nào? |

Một sản phẩm có thể thực hiện nhiều vai trò. Điều quan trọng là sơ đồ triển khai phải chỉ ra nơi TLS kết thúc, nơi token được xác minh, nơi CORS được thêm, nơi rate limit được tính và nơi log được ghi.

### 2.1. API gateway và BFF

API gateway thường cung cấp policy và routing dùng chung cho nhiều client. BFF là lớp backend được thiết kế riêng cho một frontend hoặc nhóm client, có thể tổng hợp dữ liệu từ nhiều service và định hình response cho giao diện.

Ví dụ:

- Web BFF tổng hợp profile, quyền hiển thị và số lượng đơn hàng cho dashboard.
- Mobile BFF trả payload gọn hơn và có thể hỗ trợ phiên bản ứng dụng cũ.
- API gateway thực thi TLS, xác thực chung, giới hạn request và chuyển request đến BFF hoặc service.

Không nên biến gateway thành nơi chứa toàn bộ nghiệp vụ. Nếu gateway thực hiện quá nhiều phép biến đổi, logic có thể bị phân tán khỏi service sở hữu dữ liệu và khó kiểm thử.

## 3. Thiết kế routing và quản lý phiên bản API

### 3.1. Route theo allowlist

Route nên được khai báo rõ ràng theo host, path, method và upstream. Tránh nhận URL upstream tùy ý từ query, header hoặc body của client.

Một bảng route mẫu:

| Public route | Method | Upstream | Yêu cầu |
|---|---|---|---|
| /api/v1/accounts/me | GET | Account Service | User session hoặc access token |
| /api/v1/orders | GET, POST | Order Service | Authentication và quyền tương ứng |
| /api/v1/orders/{id} | GET | Order Service | Kiểm tra quyền trên order cụ thể |
| /api/v1/catalog | GET | Catalog Service | Có thể công khai, rate limit |
| /health/ready | GET nội bộ | Gateway/health handler | Chỉ mạng giám sát được phép |

Route public không nên tự động ánh xạ đến mọi path của backend. Cần định nghĩa method được phép và từ chối method ngoài danh sách. Nếu backend có endpoint quản trị, debug hoặc health nội bộ, không công bố endpoint đó chỉ vì nó nằm dưới cùng một prefix.

### 3.2. Chuẩn hóa path

Các thành phần proxy và backend có thể xử lý path khác nhau. Những khác biệt như dấu gạch chéo kép, dấu chấm trong path, percent-encoding, dấu backslash, Unicode normalization hoặc decode nhiều lần có thể dẫn đến route bypass.

Nguyên tắc:

- Chuẩn hóa path theo một quy tắc thống nhất trước khi route.
- Không decode percent-encoding nhiều lần qua các lớp.
- Từ chối path mơ hồ hoặc encoding không hợp lệ nếu ứng dụng không cần.
- Không dùng so khớp prefix lỏng lẻo khi route cần segment boundary.
- Kiểm tra method và path trên cùng một policy.
- Backend cần áp dụng quy tắc tương thích với gateway; không để gateway và backend diễn giải cùng URL thành hai tài nguyên khác nhau.

Ví dụ, route /api/v1/admin không nên vô tình cho phép /api/v1/administrator chỉ vì kiểm tra chuỗi bắt đầu bằng prefix. Hãy so khớp path segment hoặc dùng route template có cấu trúc.

### 3.3. Quản lý phiên bản

Có thể version API trong path (/v1, /v2) hoặc qua media type/header. Dù chọn cách nào, cần có quy trình:

1. Công bố contract và thời gian hỗ trợ phiên bản.
2. Triển khai backend tương thích trước khi chuyển traffic.
3. Cho phép client cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.
4. Theo dõi request theo phiên bản và client release.
5. Ngừng phiên bản cũ sau khi có thông báo và đo được mức sử dụng còn lại.

Gateway có thể route /v1 và /v2 đến các service hoặc handler khác nhau, nhưng không nên tự ý thay đổi ý nghĩa nghiệp vụ của request để che một thay đổi breaking.

## 4. TLS, proxy và danh tính kết nối

### 4.1. TLS ở edge và gateway

TLS bảo vệ dữ liệu trên đường truyền. Nhiều hệ thống kết thúc TLS tại CDN hoặc load balancer, sau đó chuyển request qua mạng nội bộ đến gateway. Nếu đoạn sau dùng HTTP không mã hóa, request có thể bị đọc hoặc sửa bởi thành phần trên mạng đó.

Các lựa chọn:

- TLS từ client đến edge và tiếp tục TLS từ edge đến gateway.
- TLS từ gateway đến từng service.
- mTLS giữa gateway và service để xác minh cả hai đầu kết nối.
- Giữ TLS end-to-end khi kiến trúc yêu cầu backend tự kết thúc TLS.

TLS termination ở edge không có nghĩa request phía sau tự nhiên đáng tin. Cần kiểm soát network path, xác thực proxy và bảo vệ header được chuyển tiếp.

### 4.2. X-Forwarded-* và Forwarded

Các header như Forwarded, X-Forwarded-For, X-Forwarded-Proto và X-Forwarded-Host thường mô tả thông tin kết nối gốc. Client có thể tự gửi các header này.

Gateway chỉ nên tin giá trị được thêm bởi proxy nằm trong danh sách trusted proxy đã cấu hình. Khi nhận request từ Internet:

- Xóa hoặc ghi đè forwarding headers do client tự gửi.
- Edge đã tin cậy phải ghi địa chỉ nguồn và scheme theo cách thống nhất.
- Gateway chỉ đọc forwarding header từ hop đã xác thực.
- Backend không tự suy ra client IP từ một header tùy ý.
- Không dùng X-Forwarded-Host làm căn cứ tạo URL tuyệt đối hoặc reset password link nếu chưa kiểm tra host allowlist.

Nếu không làm vậy, attacker có thể giả IP để né rate limit, giả scheme để tạo redirect không an toàn hoặc làm sai log và audit.

### 4.3. Host và authority validation

Chỉ chấp nhận host được công bố. Từ chối host không nằm trong allowlist thay vì tạo redirect hoặc URL callback dựa trên giá trị Host tùy ý.

Kiểm tra host ở edge/gateway và tại ứng dụng khi host ảnh hưởng đến tenant, URL tuyệt đối, callback hoặc cookie domain. Không tin Host, :authority hay forwarded host chỉ vì request đã đến backend.

## 5. Authentication và authorization

### 5.1. Gateway xác thực danh tính

Gateway có thể xác minh access token hoặc session trước khi chuyển request. Với JWT, tối thiểu cần kiểm tra:

- Chữ ký bằng khóa tin cậy và thuật toán nằm trong allowlist.
- iss khớp issuer được cấu hình.
- aud khớp API nhận token.
- exp và nbf (nếu token có claim này) theo clock policy có kiểm soát.
- kid ánh xạ đến khóa phù hợp trong JWKS tin cậy.
- Loại token và claim bắt buộc phù hợp với luồng sử dụng.

Không chỉ decode JWT rồi tin payload. Base64 decode không xác minh chữ ký. Không chấp nhận thuật toán do token tự chọn ngoài policy; không dùng khóa từ URL hoặc jku tùy ý do token cung cấp.

Khi xoay khóa, gateway cần hỗ trợ nhiều khóa hợp lệ trong thời gian chuyển tiếp, cache JWKS có thời hạn và xử lý key rotation có kiểm soát. Nếu không lấy được khóa mới, policy cần xác định rõ khi nào từ chối request thay vì âm thầm bỏ qua xác minh.

### 5.2. Authentication không phải authorization

Gateway có thể xác nhận request mang token hợp lệ và có scope như orders:read. Điều đó chưa đủ để kết luận người dùng được xem mọi đơn hàng.

Backend sở hữu dữ liệu phải kiểm tra quyền ở cấp đối tượng và tenant:

- Người dùng có thuộc tenant chứa đơn hàng không?
- Người dùng có vai trò xem đơn hàng này không?
- Đơn hàng có ở trạng thái cho phép thao tác không?
- Trường dữ liệu trả về có được phép hiển thị cho vai trò đó không?

Gateway có thể thực thi coarse-grained policy như yêu cầu scope hoặc role để giảm tải, nhưng backend vẫn phải thực thi authorization nghiệp vụ. Không dùng một header X-User-Role do client tự gửi làm bằng chứng quyền.

### 5.3. Chuyển danh tính đến backend

Nếu gateway đã xác minh token, có thể chuyển tiếp token gốc hoặc tạo identity assertion nội bộ. Mỗi cách cần ranh giới tin cậy rõ ràng.

Nếu dùng header nội bộ như X-Authenticated-User:

- Gateway phải xóa mọi giá trị cùng tên do client gửi.
- Chỉ gateway được phép tạo header đó.
- Backend chỉ nhận traffic từ gateway hoặc workload identity được phép.
- Header phải có integrity protection qua TLS/mTLS.
- Không đưa claim nhạy cảm hoặc dữ liệu cá nhân không cần thiết vào header.

Một phương án khác là backend tự xác minh access token. Cách này tăng tính độc lập của service và giảm nguy cơ tin một gateway duy nhất, nhưng đòi hỏi quản lý khóa và policy nhất quán. Chọn mô hình theo threat model, không trộn hai cách một cách tùy tiện.

## 6. Browser session, cookie và CSRF

### 6.1. Gateway với cookie phiên

Với ứng dụng browser, mô hình BFF thường giữ access token ở backend và dùng cookie phiên cho trình duyệt. Cookie nên được thiết kế với các thuộc tính phù hợp:

~~~http
Set-Cookie: __Host-session=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính:

- Secure: chỉ gửi cookie qua HTTPS.
- HttpOnly: JavaScript không đọc cookie qua document.cookie.
- SameSite: giảm việc cookie được gửi trong một số ngữ cảnh cross-site.
- Prefix __Host-: yêu cầu Secure, Path=/ và không có Domain attribute theo quy tắc cookie prefix của trình duyệt hỗ trợ.

Cookie phiên nên là opaque identifier có entropy cao, được quản lý ở server, có thời hạn và cơ chế thu hồi. Không nhét thông tin xác thực dài hạn hoặc quyền nghiệp vụ trực tiếp vào cookie nếu chưa có thiết kế ký, xoay vòng và thu hồi phù hợp.

### 6.2. CSRF vẫn là trách nhiệm của ứng dụng

Cookie được trình duyệt tự động gửi theo quy tắc cookie. Một website khác có thể kích hoạt một số request đến API dù JavaScript của website đó không đọc được response. Vì vậy, CORS không thay thế CSRF protection.

Với endpoint thay đổi trạng thái dùng cookie phiên:

- Dùng CSRF token gắn với phiên hoặc cơ chế tương đương đã được đánh giá.
- Kiểm tra Origin và/hoặc Referer theo policy phù hợp cho request unsafe.
- Có thể dùng Fetch Metadata như Sec-Fetch-Site làm tín hiệu bổ sung.
- Cấu hình SameSite phù hợp nhưng không xem đây là lớp bảo vệ duy nhất.
- Không thay đổi dữ liệu qua GET, HEAD hoặc OPTIONS.
- Yêu cầu xác nhận bổ sung cho thao tác nhạy cảm như đổi email, thay quyền hoặc thanh toán.

Gateway có thể kiểm tra token/header CSRF chung nếu kiến trúc sở hữu session và token ở đó. Nếu backend sở hữu session hoặc nghiệp vụ, backend cần kiểm tra token và quyền. Phải có một contract rõ ràng giữa gateway và service để không bỏ qua hoặc kiểm tra trùng theo cách mâu thuẫn.

### 6.3. BFF và token trong browser

Nếu dùng BFF, browser gọi BFF bằng cookie phiên và BFF gọi API nội bộ bằng token service hoặc user delegation phù hợp. Cần chống CSRF ở BFF vì cookie tự động được gửi. Không lưu refresh token hoặc access token dài hạn trong localStorage chỉ để đơn giản hóa gateway.

## 7. CORS tại API gateway

### 7.1. Chọn một nơi sở hữu policy

CORS được browser thực thi dựa trên response header. Có thể cấu hình ở gateway, edge hoặc ứng dụng; điều quan trọng là chỉ có một lớp chịu trách nhiệm cuối cùng cho mỗi route.

Nếu CDN và gateway cùng thêm Access-Control-Allow-Origin, response có thể chứa nhiều giá trị ACAO không hợp lệ. Nếu gateway trả CORS header cho OPTIONS nhưng backend trả response thực tế thiếu header, browser vẫn chặn JavaScript đọc response.

Đối với mỗi route, ghi rõ:

- Danh sách origin được phép.
- Method và request header được phép.
- Có cần credentials không.
- Response header nào được expose.
- Cách xử lý OPTIONS.
- CORS header có xuất hiện trên response lỗi không.

### 7.2. Allowlist origin chính xác

So sánh origin gồm scheme, host và port. Không dùng so khớp chuỗi con như endsWith("example.test") mà không parse và kiểm tra hostname boundary. Không phản chiếu mọi Origin request.

Ví dụ policy:

| Origin | Quyết định |
|---|---|
| https://app.example.test | Cho phép nếu nằm trong allowlist |
| https://admin.example.test | Chỉ cho phép trên route admin nếu có yêu cầu |
| http://app.example.test | Từ chối nếu môi trường chỉ dùng HTTPS |
| https://app.example.test.evil.test | Từ chối |
| https://app.example.test:8443 | Từ chối nếu port không được cấu hình |
| null | Từ chối trừ khi có use case opaque origin được đánh giá riêng |

Nếu response thay đổi theo Origin, trả Vary: Origin để cache phân biệt response. Nếu route công khai thực sự không dùng credentials, wildcard có thể phù hợp. Nếu dùng credentials, ACAO phải là origin cụ thể và Access-Control-Allow-Credentials: true.

### 7.3. Preflight và request thực tế

Gateway phải xử lý OPTIONS preflight theo cùng route policy với request thực tế. Ví dụ browser muốn gửi JSON và header tùy chỉnh:

~~~http
OPTIONS /api/v1/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response ví dụ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 300
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Không yêu cầu cookie đăng nhập để xử lý preflight; preflight request không mang credentials của request thực tế. Request thực tế vẫn phải xác thực và authorization bình thường.

### 7.4. CORS không bảo vệ API khỏi client ngoài browser

curl, ứng dụng mobile hoặc script server-to-server không bị browser CORS enforcement. Người gọi có thể tự đặt Origin. Vì vậy:

- CORS chỉ kiểm soát việc browser cho JavaScript đọc response.
- Authentication xác định danh tính caller.
- Authorization quyết định caller được làm gì.
- CSRF bảo vệ request đã xác thực bằng cookie tự động gửi.
- Rate limit và abuse protection giới hạn sử dụng API.

## 8. Security headers và nội dung web

Gateway có thể thêm hoặc chuẩn hóa một số security header, nhưng cần xác định loại response và ứng dụng sở hữu chính sách.

| Header | Vai trò | Lưu ý |
|---|---|---|
| Strict-Transport-Security | Yêu cầu browser dùng HTTPS trong thời hạn policy | Chỉ bật sau khi HTTPS ổn định trên host/subdomain liên quan |
| X-Content-Type-Options: nosniff | Ngăn MIME sniffing trong các ngữ cảnh áp dụng | Backend cần trả Content-Type chính xác |
| Referrer-Policy | Kiểm soát thông tin referrer được gửi | Chọn theo yêu cầu quyền riêng tư |
| Content-Security-Policy | Giới hạn nguồn nội dung và script của document | Thường do ứng dụng HTML sở hữu; không áp một policy chung cho mọi API |
| frame-ancestors | Kiểm soát website nào được nhúng document | Phù hợp response HTML; không thay authorization |
| Cache-Control | Kiểm soát cache HTTP | Response cá nhân thường cần private hoặc no-store tùy dữ liệu |

CSP, Trusted Types và output encoding giúp ứng dụng phòng XSS. API gateway không thể sửa một DOM sink không an toàn trong frontend. Gateway có thể chuyển tiếp hoặc thêm header, nhưng policy CSP phải phù hợp với script, style, worker, frame và tài nguyên thật của ứng dụng.

Với API JSON, không nên gắn CSP phức tạp một cách máy móc rồi coi XSS đã được giải quyết. Cần tập trung vào Content-Type, nosniff, CORS, cache và xác thực. Với HTML do gateway/BFF trả, policy CSP cần được kiểm thử trên đúng trang và có nonce/hash phù hợp.

HSTS includeSubDomains hoặc preload có tác động rộng. Chỉ dùng khi mọi subdomain thuộc phạm vi đều hỗ trợ HTTPS và quy trình rollback đã được đánh giá.

## 9. Kiểm soát request ở gateway

### 9.1. Giới hạn kích thước và kiểu nội dung

Giới hạn request body, header size, số header và thời gian đọc request. Mỗi route có thể có giới hạn riêng:

- JSON API: body nhỏ, schema rõ.
- Upload: kích thước, loại file, thời gian và storage riêng.
- Webhook: giới hạn body và xác minh chữ ký nhà cung cấp.
- GraphQL: giới hạn depth, complexity, batch size và thời gian thực thi.
- Search: giới hạn query length và số kết quả.

Không tin Content-Type do client khai báo là bằng chứng nội dung hợp lệ. Backend phải parse và validate body theo schema. Với upload, không chỉ dựa vào phần mở rộng file; kiểm tra loại dữ liệu, tên file, vị trí lưu và quyền tải xuống.

### 9.2. HTTP method và header

Chỉ cho phép method cần thiết trên từng route. Từ chối method không hỗ trợ và tránh method lạ rơi xuống handler mặc định.

Loại bỏ hoặc xử lý đúng hop-by-hop header như Connection, Keep-Alive, Transfer-Encoding, TE, Trailer, Upgrade và các header được liệt kê trong Connection. Không forward header nội bộ do client tự gửi nếu backend có thể diễn giải chúng như danh tính hoặc policy.

Không tin X-User, X-Role, X-Tenant, X-Forwarded-For hoặc header tương tự từ Internet. Gateway phải xóa giá trị client gửi và chỉ thêm dữ liệu đã xác minh khi contract nội bộ cho phép.

### 9.3. Request smuggling

Request smuggling xảy ra khi các proxy hoặc server diễn giải ranh giới HTTP request không giống nhau. Trường hợp đáng chú ý là cách xử lý không nhất quán giữa Content-Length và Transfer-Encoding, hoặc giữa nhiều hop có parser khác nhau.

Phòng vệ:

- Dùng phiên bản proxy và server còn được hỗ trợ, cập nhật bản vá.
- Chuẩn hóa và từ chối request có framing mơ hồ.
- Không forward nguyên trạng hop-by-hop header.
- Giữ HTTP parser và protocol translation nhất quán giữa các hop.
- Kiểm thử chuỗi edge → gateway → backend, không chỉ từng thành phần riêng.
- Không tự viết HTTP parser hoặc tự ghép request bằng chuỗi.

## 10. Rate limiting và chống lạm dụng

### 10.1. Phân loại giới hạn

Rate limit có thể dựa trên:

- IP nguồn đã được xác minh qua trusted proxy.
- User ID hoặc tenant sau authentication.
- API key hoặc client identity.
- Route và method.
- Chi phí request, ví dụ search hoặc export.
- Tổng lưu lượng của một tenant hoặc toàn hệ thống.

Không dùng IP làm khóa duy nhất cho mọi API. Nhiều người dùng có thể chung NAT; attacker có thể thay IP; header IP do client gửi có thể giả mạo nếu proxy không chuẩn hóa.

### 10.2. Token bucket

Token bucket là một cách triển khai phổ biến. Bucket có dung lượng tối đa B, được bổ sung token với tốc độ r mỗi giây. Request tiêu thụ token theo chi phí. Khi không đủ token, gateway từ chối hoặc trì hoãn request theo policy.

Ví dụ policy:

| Route | Giới hạn minh họa | Khóa |
|---|---|---|
| GET catalog | 120 request/phút | IP hoặc client identity |
| POST login | 5 lần/phút | IP kết hợp account identifier đã chuẩn hóa |
| POST order | 20 request/phút | User + tenant |
| Export report | 2 request/5 phút | User + tenant |
| Health check nội bộ | Theo hệ thống giám sát | Service identity |

Đây là giá trị minh họa, không phải khuyến nghị áp dụng nguyên trạng. Cần dựa vào traffic baseline, SLA và chi phí backend.

Khi bị giới hạn, trả 429 Too Many Requests và Retry-After nếu có thể xác định thời điểm thử lại. Không tiết lộ thông tin về người dùng khác trong body lỗi.

### 10.3. Distributed rate limit

Nếu gateway chạy nhiều instance, bộ đếm trong bộ nhớ từng instance không tạo ra giới hạn toàn cục. Một client có thể gửi request qua nhiều instance và vượt tổng hạn mức.

Các lựa chọn:

- Shared store hoặc distributed rate limiter.
- Phân bổ quota theo instance với giới hạn toàn cục rõ ràng.
- Token bucket ở edge kết hợp policy theo user tại gateway.
- Hạn mức theo tenant và chi phí backend.

Cần xác định hành vi khi shared store lỗi: từ chối, dùng quota cục bộ giảm mức, hay tạm cho qua với route rủi ro thấp. Không dùng một chế độ fail-open chung cho login, thanh toán và endpoint công khai.

## 11. Timeout, retry và circuit breaker

### 11.1. Timeout theo từng chặng

Request đi qua nhiều thành phần; tổng thời gian cần nằm trong deadline của client. Đặt timeout riêng cho kết nối upstream, gửi request, đọc response và tổng thời gian xử lý.

Ví dụ:

- Gateway có deadline tổng 8 giây cho một API đọc.
- Kết nối đến upstream tối đa 1 giây.
- Backend có deadline xử lý nhỏ hơn deadline gateway.
- Gateway trả lỗi có kiểm soát khi upstream vượt deadline.

Giá trị cần dựa trên latency thực tế và SLA. Timeout quá dài giữ connection và tài nguyên; quá ngắn gây lỗi giả khi backend có tải cao.

### 11.2. Retry

Retry có thể khuếch đại tải khi backend đang lỗi. Chỉ retry khi:

- Request có thể lặp an toàn hoặc có idempotency key.
- Lỗi là transient và nằm trong danh sách được phép retry.
- Còn thời gian trong deadline.
- Số lần retry nhỏ, có backoff và jitter.
- Không retry khi lỗi xác thực, phân quyền hoặc validation.

Không retry POST tạo đơn hàng một cách mù quáng. Nếu client không biết request đầu đã được xử lý hay chưa, retry có thể tạo giao dịch trùng. Dùng idempotency key được backend lưu và xác minh.

### 11.3. Circuit breaker

Circuit breaker theo dõi lỗi của upstream và tạm ngừng gửi request khi service vượt ngưỡng lỗi. Sau một khoảng chờ, một số request thử nghiệm được gửi để kiểm tra service đã phục hồi chưa.

Các trạng thái thường gặp:

- Closed: request được chuyển tiếp bình thường.
- Open: chặn request đến upstream đang lỗi và trả lỗi nhanh.
- Half-open: cho một số request thử nghiệm đi qua để xác minh phục hồi.

Circuit breaker cần phân biệt lỗi do caller (4xx) với lỗi upstream (5xx/timeout). Không mở circuit chỉ vì người dùng gửi dữ liệu sai. Cũng cần tránh circuit quá nhạy khiến service khỏe bị cô lập bởi một đợt lỗi ngắn.

## 12. Cache và dữ liệu nhạy cảm

Gateway có thể cache response công khai để giảm tải backend, nhưng cache phải hiểu đúng danh tính và biến thể response.

Không cache chung response phụ thuộc:

- Cookie phiên hoặc Authorization.
- User ID, tenant hoặc quyền truy cập.
- Header cá nhân hóa.
- Dữ liệu thanh toán, hồ sơ hoặc thông tin nhạy cảm.

Với response cá nhân, cân nhắc Cache-Control: private hoặc no-store theo yêu cầu. private ngăn shared cache lưu response, nhưng vẫn cho phép private cache của trình duyệt; no-store yêu cầu cache không lưu response. Cần xác định chính sách phù hợp với dữ liệu và yêu cầu pháp lý.

Nếu response công khai thay đổi theo Accept, Accept-Language hoặc Origin, header Vary phải phản ánh các yếu tố ảnh hưởng đến response. Không cấu hình cache key dựa trên header tùy ý mà không giới hạn, vì có thể gây cache poisoning hoặc phân mảnh cache.

Cache key cần loại bỏ query/header không có ý nghĩa hoặc chuẩn hóa chúng có chủ đích. Không bỏ tham số có thể thay đổi nội dung hoặc quyền truy cập. Không dùng cache để thay thế authorization.

## 13. SSRF, redirect và outbound request

Một gateway đôi khi gọi upstream theo URL cấu hình hoặc theo tham số client. Nếu client có thể điều khiển URL đích, gateway có thể trở thành điểm SSRF.

Phòng vệ:

- Dùng route map tĩnh hoặc service discovery có kiểm soát.
- Không cho client truyền upstream URL tùy ý.
- Nếu cần gọi URL ngoài, allowlist scheme, hostname và port.
- Chặn địa chỉ loopback, link-local, private và metadata endpoint theo threat model.
- Kiểm tra DNS resolution và chống DNS rebinding trong luồng outbound.
- Xử lý redirect có giới hạn; không tự động theo redirect đến host không được phép.
- Áp dụng egress firewall và service identity.

Redirect từ upstream cũng cần được đánh giá. Không để response chứa Location trỏ đến hostname nội bộ hoặc host không được phép rồi chuyển thẳng cho browser nếu điều đó tiết lộ topology hoặc tạo open redirect.

## 14. WebSocket, streaming và upload

Không phải mọi API đều là request/response JSON thông thường.

### 14.1. WebSocket

Nếu gateway hỗ trợ WebSocket:

- Chỉ cho phép route và origin cần thiết.
- Xác thực khi handshake và xác minh quyền của channel/topic.
- Kiểm soát thời gian sống, số connection và số message.
- Giới hạn kích thước frame và tốc độ message.
- Xử lý revoke session và đóng connection khi danh tính hết hạn.
- Không coi Origin header là xác thực; nó chỉ là một tín hiệu policy cho browser client.

Cookie phiên có thể được gửi trong handshake theo quy tắc cookie; vì vậy cần xem xét CSRF-like cross-site WebSocket hijacking và kiểm tra Origin/authorization phù hợp.

### 14.2. Streaming và upload

Với streaming, SSE hoặc upload lớn, gateway cần giới hạn thời gian idle, tổng thời gian, kích thước và số kết nối đồng thời. Không buffer toàn bộ file lớn trong bộ nhớ gateway nếu kiến trúc hỗ trợ streaming hoặc upload trực tiếp đến storage an toàn.

Nếu dùng signed upload URL, backend phải tạo URL có scope, object key, content length/type và thời hạn phù hợp. Gateway không nên biến thành proxy upload mở đến mọi URL.

## 15. Observability và xử lý lỗi

### 15.1. Request ID và distributed tracing

Mỗi request cần một correlation ID hoặc trace context để nối log giữa edge, gateway và backend.

- Nếu nhận request ID từ client, không dùng nó làm định danh tin cậy; có thể tạo ID nội bộ mới hoặc validate định dạng và ghi nhận riêng.
- Propagate trace context theo chuẩn đã chọn.
- Không đưa token, cookie hoặc dữ liệu cá nhân vào trace baggage.
- Giới hạn độ dài và ký tự của request ID để tránh log injection.
- Ghi nhận route template thay vì raw URL chứa ID hoặc query nhạy cảm khi không cần.

### 15.2. Metrics

| Metric | Ý nghĩa |
|---|---|
| Request count | Lưu lượng theo route, method, status |
| Latency p50/p95/p99 | Thời gian phản hồi theo upstream |
| Upstream error rate | Tỷ lệ 5xx và timeout từ backend |
| 4xx rate | Lỗi caller, auth, validation hoặc route |
| Rate-limit count | Request bị giới hạn |
| Auth failure | Token/session không hợp lệ hoặc hết hạn |
| Preflight count/failure | OPTIONS và lỗi CORS |
| Connection pool | Kết nối đang dùng và chờ |
| Circuit state | Upstream đang closed/open/half-open |
| Payload size | Phân bố kích thước request/response |

Metrics cần label có cardinality giới hạn. Không dùng raw user ID, email hoặc URL đầy đủ làm label vì có thể làm tăng chi phí và lộ dữ liệu.

### 15.3. Log an toàn

Không ghi mặc định:

- Authorization header.
- Cookie hoặc Set-Cookie.
- Access/refresh token.
- CSRF token.
- Password, OTP hoặc nội dung biểu mẫu.
- Body upload hoặc response chứa dữ liệu cá nhân.
- Query string có secret hoặc thông tin nhận dạng.

Ghi route template, status, latency, upstream name, release ID, request ID và kết quả policy. Khi cần điều tra payload, dùng quy trình truy cập có kiểm soát, redaction và thời hạn lưu ngắn.

### 15.4. Error response

Gateway nên trả lỗi nhất quán, không lộ stack trace, hostname nội bộ, địa chỉ IP private, tên database hoặc cấu hình upstream.

Ví dụ response lỗi:

~~~http
HTTP/1.1 502 Bad Gateway
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: 8b4d0c2a
~~~

~~~json
{
  "type": "about:blank",
  "title": "Upstream service unavailable",
  "status": 502,
  "requestId": "8b4d0c2a"
}
~~~

Phân biệt lỗi:

- 400: request không hợp lệ.
- 401: thiếu hoặc không hợp lệ thông tin xác thực.
- 403: đã xác thực nhưng không được phép.
- 404: route hoặc tài nguyên không tồn tại theo policy.
- 405: method không được hỗ trợ.
- 413: request body quá lớn.
- 429: vượt giới hạn.
- 502: upstream trả response không hợp lệ hoặc lỗi gateway-upstream.
- 503: gateway hoặc upstream tạm thời không sẵn sàng.
- 504: upstream vượt timeout.

Không chuyển nguyên status backend một cách máy móc nếu status đó làm lộ thông tin hoặc gây hiểu nhầm. Tuy nhiên, cần giữ contract đủ rõ để client có thể xử lý retry và xác thực.

## 16. Ví dụ cấu hình reverse proxy có giới hạn

Đoạn cấu hình Nginx sau minh họa route cố định đến Order Service, giới hạn body, timeout và header chuyển tiếp. Đây là cấu hình nền để học cách tổ chức policy; cần điều chỉnh theo topology, phiên bản Nginx, module và policy thực tế trước khi dùng.

~~~nginx
http {
    limit_req_zone $binary_remote_addr zone=api_per_ip:10m rate=10r/s;

    upstream order_service {
        server 10.20.0.15:8080;
        keepalive 32;
    }

    server {
        listen 443 ssl;
        server_name api.example.test;

        client_max_body_size 1m;
        client_header_timeout 10s;
        client_body_timeout 10s;
        send_timeout 15s;

        location = /api/v1/orders {
            limit_req zone=api_per_ip burst=20 nodelay;

            if ($request_method !~ ^(GET|POST)$) {
                return 405;
            }

            proxy_pass http://order_service;
            proxy_http_version 1.1;

            proxy_set_header Host order-service.internal;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto https;

            proxy_set_header Connection "";
            proxy_connect_timeout 1s;
            proxy_send_timeout 5s;
            proxy_read_timeout 5s;

            add_header X-Content-Type-Options nosniff always;
            add_header Referrer-Policy strict-origin-when-cross-origin always;
        }
    }
}
~~~

Lưu ý khi áp dụng:

- Ví dụ không cấu hình TLS certificate/key; thêm cấu hình certificate, protocol và cipher theo baseline của tổ chức.
- Upstream dùng HTTP để minh họa. Môi trường có yêu cầu bảo mật mạng cần dùng TLS/mTLS đến upstream.
- $remote_addr chỉ đáng tin nếu Nginx nhận kết nối trực tiếp từ client hoặc real IP module được cấu hình đúng với trusted proxy.
- Rate limit ở đây theo IP và chỉ là một lớp. API theo user/tenant cần khóa giới hạn khác sau authentication.
- if trong Nginx có các giới hạn theo ngữ cảnh; với hệ thống lớn, nên dùng route tách biệt hoặc policy layer đã được kiểm thử.
- Cấu hình chưa xử lý CORS, JWT, CSRF, authorization nghiệp vụ, request smuggling và WebSocket.
- Không dùng add_header chung cho mọi response nếu chưa hiểu inheritance và response status; kiểm thử header trên cả lỗi và preflight.
- Nginx reverse proxy không tự biến thành API gateway đầy đủ nếu thiếu policy, identity, telemetry và vận hành.

## 17. Kiểm thử API gateway

### 17.1. Kiểm thử routing

- Route hợp lệ đến đúng upstream.
- Host không được phép bị từ chối.
- Path gần giống route hợp lệ không được route nhầm.
- Method ngoài allowlist trả 405.
- Path percent-encoded, dấu chấm, slash kép và Unicode được xử lý nhất quán.
- Route quản trị và health nội bộ không công khai.

### 17.2. Kiểm thử authentication và authorization

- Token thiếu, sai chữ ký, sai issuer hoặc audience bị từ chối.
- Token hết hạn hoặc chưa đến thời điểm hiệu lực bị từ chối.
- kid không tồn tại và JWKS lỗi được xử lý an toàn.
- Role/scope không đủ bị từ chối.
- Người dùng hợp lệ nhưng không sở hữu object vẫn không đọc hoặc sửa được object đó.
- Header giả X-User, X-Role và X-Tenant từ client không thay đổi danh tính.
- Backend không thể bị gọi trực tiếp để bỏ qua policy của gateway.

### 17.3. Kiểm thử CORS và CSRF

- Origin trong allowlist được xử lý đúng.
- Origin lạ, sai scheme, sai port, suffix giả và null bị từ chối theo policy.
- Preflight cho method/header hợp lệ trả đúng ACAO, ACAM, ACAH và ACAC.
- Credentialed request dùng origin cụ thể; không kết hợp wildcard với credentials.
- Response lỗi cũng có CORS header phù hợp nếu frontend cần đọc lỗi.
- Request thay đổi trạng thái dùng cookie phải có CSRF protection.
- Simple request cross-origin không được xem là đã bị ngăn chỉ vì CORS response bị chặn.

### 17.4. Kiểm thử giới hạn và resilience

- Body quá lớn bị từ chối trước khi chiếm nhiều tài nguyên.
- Header quá dài hoặc quá nhiều bị từ chối.
- Timeout upstream trả lỗi gateway nhất quán.
- Retry không tạo giao dịch trùng.
- Circuit breaker mở khi upstream lỗi và phục hồi theo policy.
- Rate limit hoạt động qua nhiều gateway instance.
- Upload, streaming và WebSocket có giới hạn connection/frame phù hợp.
- Khi Redis/JWKS/identity provider lỗi, gateway thực hiện fail-open/fail-closed đúng policy đã định.

### 17.5. Kiểm thử logging và thông tin lỗi

- Không ghi token, cookie, password, OTP hoặc CSRF token.
- Request ID được nối giữa gateway và backend.
- Raw query chứa dữ liệu nhạy cảm không xuất hiện trong log mặc định.
- Error response không chứa stack trace, hostname nội bộ hoặc upstream detail.
- Metrics không tạo cardinality cao do user ID hoặc URL động.

## 18. Ma trận kiểm thử tham khảo

| ID | Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|---|
| GW-01 | Routing | Route hợp lệ | Đến đúng upstream |
| GW-02 | Routing | Host lạ | Từ chối |
| GW-03 | Routing | Method không cho phép | 405 |
| GW-04 | Routing | Path encoding mơ hồ | Từ chối hoặc chuẩn hóa thống nhất |
| GW-05 | Identity | Token thiếu/sai chữ ký | 401 |
| GW-06 | Identity | Token sai aud/iss/exp | 401 |
| GW-07 | Authorization | User không sở hữu object | 403 hoặc 404 theo policy |
| GW-08 | Header | Client giả X-User/X-Role | Giá trị giả bị loại bỏ |
| GW-09 | Proxy | Client giả X-Forwarded-For | Không ảnh hưởng trusted client IP |
| GW-10 | CORS | Origin hợp lệ | Header đúng policy |
| GW-11 | CORS | Origin ngoài allowlist | Không được đọc response |
| GW-12 | CORS | OPTIONS hợp lệ | Preflight thành công |
| GW-13 | CSRF | Cookie request thiếu token | Bị từ chối |
| GW-14 | Limits | Body quá lớn | 413 |
| GW-15 | Rate limit | Vượt quota | 429 và Retry-After nếu có |
| GW-16 | Resilience | Upstream timeout | 504 |
| GW-17 | Resilience | Upstream lỗi | Circuit breaker theo policy |
| GW-18 | Cache | Response cá nhân | Không vào shared cache |
| GW-19 | SSRF | Client yêu cầu URL upstream tùy ý | Bị từ chối |
| GW-20 | Logging | Request có token/cookie | Secret được redact |
| GW-21 | Error | Upstream lỗi nội bộ | Response không lộ topology |
| GW-22 | Direct access | Gọi backend bỏ qua gateway | Network/service identity từ chối |

### 18.1. Tiêu chí PASS

Một ca chỉ PASS khi request được định tuyến đúng, policy được thực thi tại đúng lớp, backend không thể bị bỏ qua, response không rò rỉ dữ liệu và telemetry đủ để truy vết mà không lưu secret. Ghi lại route, method, status, upstream, browser/client, request ID và phiên bản gateway.

Không đánh dấu PASS chỉ vì một request hợp lệ trả 200. Cần thử cả negative case, nhiều tab/client, request trực tiếp đến backend và lỗi phụ thuộc mạng.

## 19. Checklist thiết kế và vận hành

### Thiết kế

- [ ] Sơ đồ rõ edge, gateway, service và trust boundary.
- [ ] Route allowlist theo host, path, method và version.
- [ ] Không có upstream URL do client điều khiển.
- [ ] Quy định TLS/mTLS ở từng hop.
- [ ] Quy định trusted proxy và forwarding headers.
- [ ] Quy định nơi xác minh token, session và CSRF.
- [ ] Quy định nơi sở hữu CORS và security headers.
- [ ] Backend vẫn thực thi authorization nghiệp vụ.
- [ ] Có giới hạn body, header, timeout và connection.

### Triển khai

- [ ] Gateway và proxy được cập nhật bản vá.
- [ ] Secret và khóa được quản lý ngoài cấu hình công khai.
- [ ] JWKS/key rotation có thời hạn và xử lý lỗi.
- [ ] Rate limit dùng khóa đã xác minh và hỗ trợ nhiều instance.
- [ ] Cache không lưu dữ liệu riêng tư ngoài chủ đích.
- [ ] Error response không lộ stack trace hoặc topology.
- [ ] Log redact cookie, token, password và body nhạy cảm.
- [ ] Backend chỉ nhận traffic từ nguồn/service identity được phép.

### Vận hành

- [ ] Theo dõi latency, error rate, 429, auth failure và upstream health.
- [ ] Theo dõi circuit breaker và connection pool.
- [ ] Kiểm thử failover, timeout, retry và key rotation.
- [ ] Có quy trình thu hồi credential và khóa.
- [ ] Có rollback gateway config và route version.
- [ ] Có runbook khi identity provider, JWKS hoặc rate-limit store lỗi.
- [ ] Rà soát quyền truy cập log, trace và dashboard.

## 20. Những lỗi thiết kế thường gặp

**Tin mọi header từ client.** Header X-Forwarded-For, X-User hoặc X-Tenant có thể bị giả mạo. Chỉ tin dữ liệu do proxy hoặc gateway đã xác minh tạo ra.

**Chỉ xác thực ở gateway.** Gateway xác minh token không chứng minh người dùng được truy cập object cụ thể. Backend vẫn phải kiểm tra quyền nghiệp vụ.

**Dùng CORS làm authorization.** Client ngoài browser không bị CORS enforcement. API vẫn cần authentication và authorization.

**Dùng SameSite làm CSRF defense duy nhất.** SameSite hữu ích nhưng không thay thế CSRF token, kiểm tra Origin và xác nhận thao tác nhạy cảm.

**Cho phép mọi route backend.** Route nội bộ, debug và admin có thể bị công bố ngoài ý muốn. Dùng allowlist và kiểm thử direct access.

**Retry mọi request.** Retry POST không có idempotency có thể tạo thao tác trùng. Retry cần policy theo method, lỗi và deadline.

**Cache response có Authorization.** Shared cache có thể trả dữ liệu của người này cho người khác nếu cache key hoặc policy sai. Không cache response cá nhân theo mặc định.

**Dùng IP client làm danh tính.** IP có thể chung NAT hoặc bị giả qua forwarding header. Rate limit nên kết hợp user, tenant và client identity đã xác minh.

**Gateway chứa toàn bộ nghiệp vụ.** Logic nghiệp vụ bị phân tán, khó kiểm thử và khó đảm bảo nhất quán. Giữ policy cross-cutting ở gateway; để service sở hữu nghiệp vụ.

**Không kiểm thử chuỗi proxy.** Mỗi proxy có thể đúng riêng nhưng kết hợp lại tạo lỗi parsing, forwarding, cache hoặc header. Kiểm thử toàn bộ request path.

## 21. Câu hỏi tự kiểm tra

### Câu 1

Vai trò chính của API gateway là gì?

A. Thay thế toàn bộ authorization trong backend.  
B. Cung cấp điểm vào API được quản lý, routing và thực thi policy chung.  
C. Lưu toàn bộ dữ liệu nghiệp vụ.  
D. Thay thế TLS.

**Đáp án: B.** Gateway tập trung routing và policy ở ranh giới API; service vẫn phải bảo vệ tài nguyên.

### Câu 2

Gateway xác minh JWT có scope orders:read. Điều gì vẫn cần xảy ra ở Order Service?

A. Không cần kiểm tra gì nữa.  
B. Kiểm tra người dùng có quyền xem order cụ thể và thuộc tenant tương ứng.  
C. Tin mọi X-User-Role từ client.  
D. Cho phép truy cập mọi order.

**Đáp án: B.** Scope thường là quyền tổng quát; authorization đối tượng thuộc service sở hữu dữ liệu.

### Câu 3

Khi nào có thể tin X-Forwarded-For?

A. Luôn tin vì là header chuẩn.  
B. Khi header được tạo/chuẩn hóa bởi proxy tin cậy đã cấu hình và request đến từ hop đó.  
C. Khi client gửi qua HTTPS.  
D. Khi giá trị có định dạng IPv4.

**Đáp án: B.** Client có thể tự gửi header này; phải xác định trusted proxy.

### Câu 4

Vì sao CORS không thay thế authentication?

A. CORS chỉ hoạt động trên HTTP.  
B. Client ngoài browser không bị browser CORS enforcement.  
C. CORS luôn yêu cầu cookie.  
D. CORS mã hóa response.

**Đáp án: B.** CORS điều khiển việc browser cho JavaScript đọc response, không xác định danh tính caller.

### Câu 5

Browser gọi API bằng cookie phiên và POST thay đổi dữ liệu. Biện pháp nào phù hợp?

A. Chỉ bật wildcard CORS.  
B. CSRF token và kiểm tra Origin/Fetch Metadata phù hợp, cùng cookie policy.  
C. Chuyển POST thành GET.  
D. Chỉ kiểm tra Content-Type.

**Đáp án: B.** Cookie tự động được gửi theo quy tắc trình duyệt; cần bảo vệ request thay đổi trạng thái.

### Câu 6

Response có credentials nên dùng Access-Control-Allow-Origin thế nào?

A. Luôn dùng *.  
B. Trả origin cụ thể đã kiểm tra trong allowlist và Access-Control-Allow-Credentials true.  
C. Trả nhiều origin trong một chuỗi phân tách bằng dấu phẩy.  
D. Bỏ Origin request.

**Đáp án: B.** Wildcard không hợp lệ cho credentialed CORS response.

### Câu 7

Vì sao backend vẫn cần xác thực dù chỉ nhận request từ gateway?

A. Vì gateway không thể route.  
B. Đường truy cập trực tiếp hoặc lỗi cấu hình có thể bỏ qua gateway; service cần xác minh service identity và quyền.  
C. Vì TLS không hoạt động trong mạng nội bộ.  
D. Vì rate limit không áp dụng cho backend.

**Đáp án: B.** Network location không phải bằng chứng danh tính đủ mạnh.

### Câu 8

Retry POST tạo đơn hàng có rủi ro gì?

A. Tự động giảm latency.  
B. Có thể tạo đơn trùng nếu request đầu đã được xử lý nhưng response bị mất.  
C. Luôn bị CORS chặn.  
D. Làm JWT đổi chữ ký.

**Đáp án: B.** Dùng idempotency key và xử lý lặp an toàn.

### Câu 9

Khi gateway trả 429, header nào có thể hướng dẫn client thử lại?

A. Retry-After.  
B. Content-Security-Policy.  
C. Access-Control-Expose-Headers.  
D. X-Frame-Options.

**Đáp án: A.** Retry-After có thể chỉ ra thời điểm hoặc khoảng thời gian thử lại.

### Câu 10

Request smuggling thường liên quan đến vấn đề gì?

A. Browser không lưu cookie.  
B. Các hop diễn giải ranh giới HTTP request không nhất quán.  
C. JWT thiếu scope.  
D. CSP thiếu nonce.

**Đáp án: B.** Cần chuẩn hóa framing và kiểm thử toàn bộ chuỗi proxy.

### Câu 11

Một response API phụ thuộc cookie phiên nên được cache thế nào?

A. Public, max-age=86400.  
B. Dùng chính sách private/no-store phù hợp và không đưa vào shared cache.  
C. Cache theo IP.  
D. Bỏ Vary và bỏ Authorization.

**Đáp án: B.** Cache chung có thể làm lộ response cá nhân nếu key/policy không đúng.

### Câu 12

Gateway nhận URL upstream tùy ý từ query parameter. Rủi ro chính là gì?

A. SSRF đến dịch vụ nội bộ hoặc endpoint metadata.  
B. Tăng khả năng CORS.  
C. Giảm request smuggling.  
D. Tự động bật mTLS.

**Đáp án: A.** Upstream nên được chọn từ route map hoặc service discovery có kiểm soát.

## 22. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| API gateway | Điểm vào API quản lý routing và policy chung |
| Reverse proxy | Proxy nhận request và chuyển tiếp đến upstream |
| Upstream | Service hoặc server đích mà gateway gọi |
| BFF | Backend được thiết kế riêng cho một frontend/client |
| Trust boundary | Ranh giới nơi dữ liệu hoặc danh tính cần được xác minh |
| Authentication | Xác định danh tính caller |
| Authorization | Quyết định caller được truy cập tài nguyên/thao tác nào |
| JWT | Token có cấu trúc claim; phải xác minh chữ ký và claim |
| JWKS | Tập khóa công khai dùng để xác minh token |
| mTLS | TLS xác thực cả client và server bằng certificate |
| CORS | Chính sách browser cho phép JavaScript đọc response cross-origin |
| CSRF | Giả mạo request đã được xác thực từ browser |
| Rate limiting | Giới hạn tần suất hoặc chi phí request |
| Circuit breaker | Cơ chế ngắt tạm request đến upstream đang lỗi |
| Idempotency key | Khóa giúp xử lý an toàn request có thể được gửi lặp |
| Request smuggling | Khai thác khác biệt parsing request giữa các hop |
| SSRF | Khiến server gửi request đến đích không mong muốn |
| Trusted proxy | Proxy được cấu hình để cung cấp thông tin kết nối gốc |
| Correlation ID | Định danh dùng nối log và trace qua nhiều service |

## Tài liệu tham khảo

- OWASP — [API Security Top 10](https://owasp.org/API-Security/): các nhóm rủi ro thường gặp khi xây dựng và vận hành API.
- OWASP — [REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): xác thực, authorization, method và bảo vệ REST API.
- OWASP — [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): nguyên tắc kiểm tra quyền ở cấp tài nguyên.
- OWASP — [Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): phòng vệ CSRF cho ứng dụng dùng cookie.
- OWASP — [HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): các HTTP security header và cách triển khai.
- OWASP — [Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): kiểm soát outbound request và SSRF.
- IETF — [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics của method, header và response HTTP.
- IETF — [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): framing và parsing HTTP/1.1.
- IETF — [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện đại.
- MDN — [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): cơ chế CORS ở browser.
- MDN — [HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies): thuộc tính cookie và cách trình duyệt xử lý.
- NGINX — [Reverse proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/): cấu hình proxy đến upstream.

API gateway là một lớp thực thi policy quan trọng ở ranh giới API. Thiết kế tốt phải phối hợp gateway với edge, browser, identity provider và backend; xác minh danh tính ở mỗi ranh giới, giữ authorization nghiệp vụ tại service sở hữu dữ liệu và kiểm thử cả luồng hợp lệ lẫn trường hợp bị từ chối.

