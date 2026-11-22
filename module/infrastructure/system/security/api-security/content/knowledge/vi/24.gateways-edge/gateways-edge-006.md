# Không tin header do client tự gửi

## 1. Vì sao header từ client không phải bằng chứng tin cậy?

HTTP header là dữ liệu do bên gửi request cung cấp. Client có thể tự thêm, sửa, lặp hoặc bỏ header theo ý muốn. Một số header mang tên giống thông tin nội bộ như X-User-ID, X-Tenant-ID, X-Forwarded-For, X-Forwarded-Proto hoặc X-Authenticated-User, nhưng tên gọi không biến giá trị thành sự thật đã được xác minh.

Nếu API tin các header này mà không xác định ai đã tạo chúng, người gọi có thể:

- Giả mạo địa chỉ IP để vượt rate limit, allowlist hoặc audit.
- Tự nhận mình là user khác bằng X-User-ID hoặc X-Authenticated-User.
- Chọn tenant khác bằng X-Tenant-ID.
- Giả mạo scheme HTTPS bằng X-Forwarded-Proto: https, làm sai logic redirect hoặc cookie.
- Đưa Host giả vào X-Forwarded-Host để tạo password-reset link, callback URL hoặc cache key trỏ tới domain của attacker.
- Dùng X-Original-URL, X-Rewrite-URL hoặc method override để đi vòng qua route policy.
- Gây khác biệt cách parse giữa proxy và upstream bằng header lặp hoặc framing mơ hồ.

Một header chỉ đáng tin khi hệ thống xác định được thành phần nào đã tạo nó, đường truyền tới thành phần đó được bảo vệ, các hop trước đã loại bỏ dữ liệu giả mạo, và consumer chỉ chấp nhận giá trị từ đúng trust boundary.

Nguyên tắc: **mọi header đến từ kết nối client đều là untrusted input; chỉ tin header do proxy/gateway đã xác thực tạo hoặc ghi đè theo một hợp đồng rõ ràng.**

## 2. Phân biệt dữ liệu client gửi và assertion của hạ tầng

Header có thể thuộc các nhóm khác nhau:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Client preference/input | Accept-Language, Prefer, filter header | Validate cú pháp, giới hạn độ dài và chỉ dùng cho mục đích đã định |
| Credential | Authorization, API key, cookie session | Xác minh chữ ký/secret/session; không tin chỉ vì header tồn tại |
| Forwarding metadata | Forwarded, X-Forwarded-For, X-Forwarded-Proto | Chỉ tin từ proxy được cấu hình; proxy biên phải ghi đè hoặc chuẩn hóa |
| Identity assertion | X-User-ID, X-Roles, X-Authenticated-User | Chỉ nhận từ gateway/identity layer đã xác thực; ưu tiên token hoặc service identity |
| Tenant selector/context | X-Tenant-ID | Xem là lựa chọn tenant; kiểm tra membership và quyền ở server |
| Routing override | X-Original-URL, X-Rewrite-URL, X-HTTP-Method-Override | Tắt hoặc strip nếu không có use case được phê duyệt |
| Protocol/framing | Host, Content-Length, Transfer-Encoding, Connection | Để HTTP parser/proxy chuẩn xử lý; từ chối request mơ hồ |
| Observability | X-Request-ID, traceparent, baggage | Validate/giới hạn; không dùng làm danh tính hoặc quyền |

Một số header có thể hợp lệ khi client gửi, nhưng giá trị của chúng vẫn không phải assertion bảo mật. Ví dụ X-Tenant-ID có thể giúp user chọn tổ chức đang làm việc; server phải xác minh user có membership trong tenant đó trước khi truy cập dữ liệu.

## 3. Xác định trust boundary của proxy và gateway

Một request thường đi qua nhiều hop:

~~~text
Browser / Mobile / Partner
          |
          v
Internet edge / CDN / WAF
          |
          v
Load balancer / API Gateway
          |
          v
Ingress / Service mesh
          |
          v
Application service
~~~

Mỗi hop có thể thêm hoặc thay đổi header. Cần lập bản đồ:

- Hop nào kết thúc TLS?
- Hop nào xác định địa chỉ peer của client?
- Hop nào xác thực token và tạo principal context?
- Hop nào được phép thêm Forwarded hoặc X-Forwarded-*?
- Backend có thể bị gọi trực tiếp từ Internet hoặc từ workload khác không?
- Có proxy nào không thuộc quyền quản trị nhưng vẫn được phép kết nối tới service không?

Trust boundary phải dựa trên danh tính và đường kết nối, không dựa vào việc request đến từ một IP private bất kỳ. Trong cloud hoặc Kubernetes, nhiều workload cùng nằm trong private network; một workload bị xâm nhập có thể gửi header giả tới service khác.

Các cách xác thực proxy/upstream:

- Network policy hoặc firewall chỉ cho gateway được kết nối tới listener upstream.
- mTLS với certificate identity riêng cho gateway.
- Service mesh identity và authorization policy.
- Private listener kết hợp xác thực caller ở application.

Không dùng một shared secret tĩnh trong header làm bằng chứng duy nhất nếu có thể dùng mTLS hoặc identity token có audience và thời hạn. Nếu dùng signed assertion, phải xác minh chữ ký, issuer, audience, expiry, key ID và chống replay theo thiết kế.

## 4. Strip rồi tạo lại header tại biên

Mẫu an toàn thường là:

1. Nhận request từ client.
2. Loại bỏ các header nội bộ mà client không được phép tự đặt.
3. Xác định thông tin từ kết nối thực tế và credential đã xác minh.
4. Tạo lại header chuẩn theo contract giữa gateway và upstream.
5. Chỉ forward các header cần thiết.
6. Upstream chỉ chấp nhận assertion từ gateway đã xác thực.

Ví dụ, gateway biên có thể xóa các header sau trước khi tạo giá trị mới:

~~~text
X-User-ID
X-Authenticated-User
X-Authenticated-Roles
X-Tenant-ID
X-Forwarded-For
X-Forwarded-Host
X-Forwarded-Proto
X-Real-IP
X-Original-URL
X-Rewrite-URL
~~~

Danh sách cụ thể phải theo kiến trúc. Không xóa mù mọi header X-*: một số có thể là contract nghiệp vụ hợp lệ. X-Tenant-ID trong ví dụ chỉ được strip khi gateway sẽ thay bằng tenant context đã xác minh; nếu ứng dụng cần giá trị tenant do client chọn, hãy giữ nó như input chưa tin cậy để service kiểm tra membership, không nâng nó thành assertion. Hãy duy trì allowlist header được phép đi qua và danh sách header do gateway sở hữu.

Nếu có nhiều proxy tin cậy, từng proxy phải có quy tắc append/overwrite rõ ràng. Proxy biên đầu tiên phải loại bỏ giá trị forwarding do Internet client gửi. Các proxy sau chỉ thêm thông tin về hop mà chúng thực sự quan sát được.

## 5. Forwarded và X-Forwarded-For

### 5.1 Không lấy IP từ header đầu tiên một cách mù quáng

X-Forwarded-For thường chứa danh sách địa chỉ được thêm qua nhiều proxy:

~~~http
X-Forwarded-For: 198.51.100.25, 203.0.113.18
~~~

Client có thể tự gửi một giá trị giả trước khi request tới proxy. Nếu proxy chỉ append IP của nó, danh sách có thể chứa cả dữ liệu do attacker kiểm soát. Vì vậy, không mặc định phần tử đầu tiên là client IP thật.

Hai cách thiết kế phổ biến:

- **Overwrite ở edge:** proxy đầu tiên xóa X-Forwarded-For từ client rồi ghi địa chỉ peer mà nó quan sát được. Đây là cách đơn giản khi chỉ cần một địa chỉ client đã được xác định.
- **Trusted proxy chain:** mỗi proxy tin cậy thêm địa chỉ peer của hop trước; ứng dụng duyệt chuỗi từ phải sang trái, bỏ qua các proxy nằm trong danh sách trusted proxy và dừng ở địa chỉ đầu tiên không thuộc proxy tin cậy.

Không dùng số hop cố định nếu đường đi có thể thay đổi mà không kiểm soát. Cấu hình trusted proxy phải liệt kê chính xác subnet hoặc identity của proxy. Nếu attacker có thể kết nối trực tiếp tới ứng dụng, ứng dụng không được tin X-Forwarded-For từ kết nối đó.

### 5.2 RFC 7239 Forwarded

Header chuẩn Forwarded có thể chứa các tham số như for, by, host và proto. Giá trị có thể được quote, có IPv6, port hoặc obfuscated identifier. Không parse bằng cách split dấu phẩy/semicolon đơn giản vì cú pháp có quy tắc quote và escaping.

Chỉ tin Forwarded từ proxy đã xác thực. Proxy biên cần xóa giá trị client gửi rồi tạo lại hoặc append theo một quy tắc đã được các hop thống nhất. Nếu cả Forwarded và X-Forwarded-* cùng tồn tại, định nghĩa rõ nguồn nào là authoritative; không để các thành phần chọn header khác nhau.

### 5.3 Dùng IP cho rate limit và audit

IP client thường không phải danh tính ổn định. Nhiều user có thể dùng chung NAT; một user có thể đổi mạng; proxy di động có thể làm IP thay đổi. Dùng IP như tín hiệu bổ sung cho abuse detection, không thay thế user ID, API key hoặc tenant quota.

Trước khi đưa IP vào allowlist hoặc quyết định quyền, xác định rõ địa chỉ được quan sát từ socket peer hay từ trusted proxy chain. Audit nên ghi nguồn IP và trust method để điều tra có thể hiểu được giá trị đó đến từ đâu.

## 6. Forwarded host và scheme

Host (HTTP/1.1), :authority (HTTP/2/HTTP/3), X-Forwarded-Host và X-Forwarded-Proto có thể ảnh hưởng routing, absolute URL, redirect, cookie và cache.

### 6.1 Host và :authority

Không dùng Host tùy ý để tạo:

- Password reset link.
- Email verification link.
- OAuth callback hoặc redirect URI.
- Canonical URL trong response.
- Cache namespace hoặc tenant routing.

Chỉ chấp nhận host nằm trong danh sách domain đã cấu hình cho ứng dụng. Với HTTP/2/HTTP/3, kiểm tra :authority theo quy tắc của protocol và gateway; không giả định mọi request đều có header Host giống HTTP/1.1.

Nếu có nhiều virtual host, ánh xạ host đã xác minh tới đúng API/service và exposure level. Xử lý rõ trường hợp Host trùng lặp, host không khớp listener hoặc SNI/authority không phù hợp với cấu hình. Không dùng string suffix đơn giản để kiểm tra domain: example.com.attacker.test không thuộc example.com.

### 6.2 X-Forwarded-Host

Chỉ tin X-Forwarded-Host nếu proxy đáng tin đã xóa giá trị client gửi và ghi lại host public mà nó nhận được. Backend không nên chọn giữa Host và X-Forwarded-Host tùy tiện; định nghĩa một nguồn canonical cho từng deployment.

Nếu không cần giữ host gốc, hãy dùng cấu hình domain cố định trong ứng dụng để tạo link. Cách này giảm phụ thuộc vào forwarding header.

### 6.3 X-Forwarded-Proto

X-Forwarded-Proto: https do client tự gửi không chứng minh kết nối bên ngoài dùng HTTPS. Chỉ proxy kết thúc TLS mới có thể khẳng định scheme mà nó quan sát được, và proxy phải ghi đè giá trị đầu vào.

Scheme sai có thể làm:

- Tạo redirect HTTP thay vì HTTPS hoặc ngược lại.
- Đặt cookie thiếu Secure.
- Sinh callback URL không đúng.
- Tạo cache key hoặc absolute link sai origin.

Backend chỉ nên tin scheme từ đúng proxy hop. Nếu TLS kết thúc ngay tại ứng dụng, dùng thông tin kết nối TLS thực tế thay vì forwarding header.

## 7. Không tin header danh tính do client tự gửi

Các header như:

~~~http
X-User-ID: admin
X-Authenticated-User: alice
X-Roles: ADMIN
X-Scopes: payments:write
~~~

không có giá trị xác thực nếu client có thể gửi trực tiếp. Một API không được lấy user, role hoặc scope từ các header này rồi bỏ qua việc xác minh token/session.

Luồng phù hợp:

1. Gateway hoặc application nhận credential trong Authorization/cookie theo contract.
2. Xác minh token/session: chữ ký, issuer, audience, expiry, not-before và các claim cần thiết.
3. Tạo principal context từ kết quả xác minh.
4. Nếu cần chuyển identity tới upstream, dùng token nội bộ có audience riêng, mTLS identity hoặc header do gateway ghi đè sau xác thực.
5. Upstream xác minh nguồn gateway và assertion; không chấp nhận cùng header từ caller khác.
6. Service vẫn thực hiện authorization trên object, property và business action.

Không chuyển nguyên token của user sang mọi upstream nếu không cần. Token forwarding cần audience, scope và lifetime phù hợp với service nhận. Một gateway đã xác thực user không có nghĩa service được phép tin mọi header do gateway chuyển tiếp mà không có trust contract.

## 8. Tenant header là selector, không phải quyền truy cập

X-Tenant-ID có thể giúp client chọn tổ chức đang làm việc:

~~~http
X-Tenant-ID: tenant-42
~~~

Nhưng giá trị này chỉ là yêu cầu chọn tenant. Server phải xác minh principal có membership hoặc delegated grant còn hiệu lực với tenant đó, tenant đang hoạt động và thao tác được phép. Sau bước xác minh mới tạo tenant context nội bộ.

Không dùng trực tiếp X-Tenant-ID để:

- Gắn tenant vào query database mà không kiểm tra membership.
- Tạo cache key như thể tenant đã được xác minh.
- Đặt RLS context chỉ vì header có giá trị.
- Ghi event/job dưới danh nghĩa tenant đó.
- Quyết định quota hoặc billing plan do client gửi.

Nếu gateway chịu trách nhiệm xác minh membership và tạo tenant assertion, upstream phải chỉ tin assertion từ gateway đã xác thực và cần có hợp đồng về issuer, audience, expiry, tenant và principal. Nếu không, để application service xác minh membership là ranh giới rõ ràng hơn.

## 9. Authorization, API key và cookie

### 9.1 Authorization

Authorization là nơi thường mang bearer token hoặc credential theo scheme. Đây là input nhạy cảm cần parse theo đúng grammar:

- Từ chối nhiều Authorization header nếu framework/proxy có thể chọn giá trị khác nhau.
- Không tự nối nhiều giá trị thành một token.
- Xác minh đúng scheme, token format và credential source.
- Không chấp nhận token qua query parameter trừ khi protocol chuyên biệt yêu cầu.
- Không ghi token vào log, trace hoặc error message.
- Không forward credential tới host/upstream ngoài audience.

### 9.2 API key

Nếu API dùng API key trong header, key phải được xác minh với registry server-side, có trạng thái revoke/rotate và scope/quota rõ. Header name không làm key trở nên đáng tin; secret vẫn là bearer credential và có thể bị đánh cắp.

Không đặt API key vào X-User-ID hoặc header mô tả danh tính. Phân biệt credential với identity: API key có thể xác định client application, nhưng chưa chắc xác định user cuối hoặc quyền trên object.

### 9.3 Cookie

Cookie là input từ user agent và có thể bị người dùng chỉnh sửa nếu không được bảo vệ bằng session mechanism. Chỉ tin session ID được tạo ngẫu nhiên và tra cứu server-side hoặc cookie được ký/mã hóa theo thiết kế. Cấu hình Secure, HttpOnly, SameSite, domain và path phù hợp.

Không dùng một cookie tùy ý như role=admin làm authorization. Với browser session, kiểm tra CSRF cho thao tác thay đổi trạng thái theo mô hình xác thực.

## 10. Content-Type, Content-Length và Transfer-Encoding

Các header điều khiển cách đọc body có tác động trực tiếp tới parser và ranh giới request. Nếu reverse proxy và backend hiểu khác nhau, có thể phát sinh request smuggling hoặc validation bypass.

### 10.1 Content-Type

Content-Type khai báo media type của body; không chứng minh nội dung thực sự đúng schema. API cần:

- Allowlist media type theo operation.
- Parse media type theo chuẩn, không so sánh chuỗi tùy tiện.
- Xử lý rõ parameter như charset và boundary.
- Từ chối content type không hỗ trợ.
- Validate body sau khi parse và áp dụng giới hạn kích thước/decompression.

Không để client gửi Content-Type: application/json nhưng parser lại xử lý như form hoặc XML theo một nhánh khác.

### 10.2 Content-Length và Transfer-Encoding

Content-Length và Transfer-Encoding ảnh hưởng framing của HTTP/1.1. Request có giá trị mâu thuẫn, header lặp khác nhau hoặc đồng thời có framing không rõ ràng có thể khiến proxy và backend xác định ranh giới body khác nhau.

Biện pháp:

- Dùng HTTP parser và proxy được duy trì; không tự parse raw request bằng code ứng dụng.
- Từ chối request có Content-Length mâu thuẫn hoặc framing không hợp lệ.
- Áp dụng chính sách nghiêm ngặt với request có cả Transfer-Encoding và Content-Length; cách an toàn ở edge thường là từ chối và đóng kết nối thay vì chuyển tiếp một request mơ hồ.
- Nếu chấp nhận các Content-Length lặp giống nhau theo parser/protocol, phải normalize thành một giá trị duy nhất trước upstream; không để các hop diễn giải khác nhau.
- Chỉ chấp nhận transfer coding được hỗ trợ; không tự xử lý chuỗi encoding tùy ý.
- Giới hạn body size, chunk count và thời gian nhận body.

HTTP/2 và HTTP/3 dùng framing khác HTTP/1.1. Khi gateway chuyển giao thức giữa các hop, phải bảo đảm request được parse rồi serialize lại theo một representation duy nhất, không chuyển tiếp mơ hồ giữa các phiên bản.

## 11. Hop-by-hop header và Connection

Một số header chỉ có ý nghĩa trên một kết nối, không được chuyển nguyên vẹn qua proxy sang hop kế tiếp. Các header hop-by-hop phổ biến gồm:

- Connection.
- Keep-Alive.
- Proxy-Authenticate.
- Proxy-Authorization.
- TE (ngoại lệ TE: trailers theo semantics của HTTP/1.1).
- Trailer.
- Transfer-Encoding.
- Upgrade.

Header Connection còn có thể liệt kê tên header bổ sung cần được coi là hop-by-hop. Proxy phải parse danh sách token đó và loại bỏ các header được chỉ định trước khi forward. Không chỉ xóa một danh sách cố định mà bỏ qua các header do Connection nominate.

HTTP/2 và HTTP/3 không cho phép nhiều connection-specific header của HTTP/1.1; gateway phải xử lý đúng khi chuyển đổi protocol. Proxy-Connection là header không chuẩn cũ và không nên được dùng làm cơ chế điều khiển.

## 12. Method override và header thay đổi routing

Một số framework hoặc proxy hỗ trợ header/query để override method hoặc path:

~~~http
X-HTTP-Method-Override: DELETE
X-Original-URL: /admin/users
X-Rewrite-URL: /internal/report
X-Forwarded-Prefix: /legacy
~~~

Nếu gateway kiểm tra POST /profile nhưng upstream plugin đổi thành DELETE /admin/users, route policy có thể bị đi vòng.

Hãy:

- Tắt method override nếu không cần.
- Strip X-HTTP-Method-Override, X-Method-Override và biến thể tương ứng ở edge nếu không được contract cho phép.
- Không tin X-Original-URL, X-Rewrite-URL hoặc header tương tự từ client.
- Nếu rewrite là chức năng hợp lệ, chỉ gateway được tạo header sau khi route đã match và policy đã chạy.
- Test route trước/sau rewrite, method thực tế ở upstream và authorization tương ứng.

Không để upstream tự chọn route dựa trên header do client có thể đặt mà gateway không kiểm tra.

## 13. Origin, Referer và CORS

Origin và Referer là header có thể hữu ích cho browser security và audit, nhưng không phải danh tính người dùng:

- Client không phải browser có thể tự đặt hoặc bỏ các header này.
- CORS là cơ chế browser kiểm soát việc JavaScript đọc response; nó không ngăn mọi client gọi API.
- Origin hợp lệ không chứng minh request đã được xác thực hoặc user có quyền.
- Referer có thể bị lược bỏ bởi privacy policy hoặc referrer policy.

Với browser session, dùng CSRF token và cookie policy phù hợp. CORS allowlist phải so sánh origin theo scheme, host và port, không dùng wildcard hoặc suffix match tùy tiện. Với API machine-to-machine, không dựa vào Origin để authorize client.

## 14. Trace, request ID và header observability

Các header như X-Request-ID, traceparent và baggage giúp nối log/trace qua nhiều service. Chúng vẫn có thể do client tạo.

Quy tắc:

- Sinh request ID nội bộ nếu thiếu hoặc không hợp lệ.
- Có thể lưu client correlation ID riêng, nhưng giới hạn length/charset và không dùng nó làm khóa bảo mật.
- Parse traceparent theo W3C Trace Context; từ chối format sai và áp dụng sampling policy để tránh trace flood.
- Giới hạn kích thước baggage; không đưa secret, PII hoặc authorization claim vào đó.
- Không dùng trace ID/request ID để xác định user, tenant, role hoặc quyền.
- Không cho client quyết định mức sampling vô hạn hoặc buộc hệ thống giữ trace đắt tiền.

Khi forward qua service, giữ correlation context đã được kiểm tra và ghi lại nguồn của giá trị. Không log toàn bộ header map vì có thể chứa token, cookie và dữ liệu cá nhân.

## 15. Header trùng lặp, case và parsing

Tên HTTP header không phân biệt hoa/thường, nên X-User-ID và x-user-id là cùng một tên theo semantics HTTP. Một số thư viện lưu nhiều giá trị, một số nối bằng dấu phẩy, một số lấy giá trị đầu/cuối. Nếu proxy và application không đồng thuận, attacker có thể khai thác parser differential.

Với header nhạy cảm:

- Định nghĩa rõ header có được lặp không.
- Từ chối duplicate cho header scalar như Authorization, Host, Content-Length hoặc identity assertion nếu contract không yêu cầu lặp.
- Không giả định mọi header có thể nối bằng dấu phẩy; semantics phụ thuộc từng header.
- Dùng parser chuẩn của HTTP framework, không tự tách chuỗi theo dấu phẩy nếu grammar có quote hoặc escaping.
- Chuẩn hóa tên header theo quy tắc HTTP, nhưng không lowercase giá trị trừ khi grammar của header cho phép.
- Từ chối whitespace/control character bất hợp lệ theo parser/protocol.

Một số header như Set-Cookie có semantics nhiều field riêng và không thể gộp giống header list thông thường. Proxy cần giữ đúng semantics thay vì áp dụng một quy tắc nối chung.

## 16. Header injection và giới hạn kích thước

Nếu ứng dụng đưa dữ liệu từ header vào response header, redirect, log hoặc upstream header mà không validate, ký tự CR/LF có thể gây header injection hoặc log forging trong những API/stack xử lý không an toàn.

Biện pháp:

- Dùng API response/header builder của framework.
- Từ chối CR, LF, NUL và ký tự control không được phép.
- Không ghép chuỗi user input vào raw HTTP response.
- Validate redirect target và response header value theo grammar.
- Giới hạn tổng header bytes, số header và độ dài từng value tại gateway và server.
- Không cho phép client gửi hàng nghìn header nhỏ để tiêu thụ memory/CPU.
- Giới hạn cookie count và cookie size.

Giới hạn header phải nhất quán giữa CDN, gateway, ingress và application. Nếu edge chấp nhận header lớn hơn upstream, request có thể bị từ chối muộn hoặc tạo khác biệt xử lý. Nếu upstream nhận được request qua một đường khác, nó vẫn cần giới hạn riêng.

## 17. Ví dụ cấu hình trust proxy trong ứng dụng

Ví dụ pseudo-configuration:

~~~yaml
server:
  forward-headers-strategy: framework

security:
  trusted-proxies:
    - 10.20.0.0/24
    - 2001:db8:100::/48
  client-supplied-identity-headers:
    - X-User-ID
    - X-Authenticated-User
    - X-Authenticated-Roles
    - X-Tenant-ID
~~~

Đây là cấu trúc minh họa, không phải key cấu hình Spring Boot phổ quát. Tên property và hành vi phụ thuộc framework, phiên bản, servlet container và proxy. Không copy cấu hình nếu chưa kiểm tra tài liệu runtime.

Các điểm cần xác minh khi bật forwarded-header support:

1. Chỉ trust đúng proxy CIDR/identity; không bật trust tất cả proxy.
2. Proxy biên xóa forwarding header client gửi rồi tạo giá trị mới.
3. Ứng dụng không thể bị truy cập trực tiếp từ nguồn không tin cậy.
4. Host và scheme canonical được kiểm tra theo allowlist.
5. Các header identity do client gửi bị strip; upstream chỉ nhận assertion từ gateway.
6. Có integration test qua đúng CDN/gateway/ingress và test direct-to-service.

Nếu framework tự xử lý Forwarded hoặc X-Forwarded-*, hiểu rõ thứ tự precedence khi cả hai cùng tồn tại. Không để một middleware tin Forwarded còn middleware khác tin X-Forwarded-For.

## 18. Ví dụ gateway: strip và set lại header

Pseudocode ở edge:

~~~text
on request from untrusted client:
    remove X-User-ID
    remove X-Authenticated-User
    remove X-Authenticated-Roles
    remove X-Tenant-ID
    remove X-Forwarded-For
    remove X-Forwarded-Host
    remove X-Forwarded-Proto
    remove X-Original-URL
    remove X-Rewrite-URL

    client_ip = observed_peer_address()
    public_host = validate_listener_authority()
    public_scheme = observed_external_tls_scheme()

    set X-Forwarded-For = client_ip
    set X-Forwarded-Host = public_host
    set X-Forwarded-Proto = public_scheme

    principal = validate_credential(Authorization or session)
    if principal is valid:
        create trusted identity context for upstream

    forward only allowlisted headers to authenticated upstream
~~~

Nếu gateway không xác minh user/tenant, không được tự tạo X-User-ID hoặc X-Tenant-ID dựa trên request. Gateway có thể chuyển tiếp credential đã được xác minh theo contract để service tự tạo principal context.

Upstream phải xác thực gateway bằng mTLS/network identity và từ chối header identity nếu request đến từ nguồn khác. Nếu upstream vẫn reachable trực tiếp, strip ở gateway không đủ.

## 19. Kiểm thử header trust boundary

Test phải chứng minh header giả mạo không ảnh hưởng principal, tenant, routing hoặc quyết định policy:

| Nhóm test | Đầu vào/tình huống | Kết quả mong đợi |
|---|---|---|
| Identity spoofing | Gửi X-User-ID: admin | Principal vẫn lấy từ credential đã xác minh |
| Role spoofing | Gửi X-Roles: ADMIN | Không được tăng quyền |
| Tenant spoofing | Gửi X-Tenant-ID của tenant khác | Membership được xác minh; không có truy cập chéo tenant |
| Forwarded IP | Gửi XFF giả với IP allowlisted | IP được lấy từ peer/trusted chain |
| XFF chain | Client gửi nhiều IP trước proxy | Proxy biên xóa hoặc chain parser bỏ qua phần không tin |
| Forwarded conflict | Gửi cả Forwarded và X-Forwarded-* khác nhau | Một nguồn canonical được chọn; request không thể đổi policy |
| Scheme spoofing | Gửi X-Forwarded-Proto=https qua HTTP | Backend không coi kết nối là HTTPS |
| Host spoofing | Gửi Host/X-Forwarded-Host ngoài allowlist | Request bị từ chối hoặc dùng host cấu hình |
| Duplicate auth | Gửi nhiều Authorization header | Bị từ chối nhất quán |
| Duplicate host | Gửi Host lặp hoặc :authority mismatch | Parser/edge từ chối |
| Request smuggling | CL/TE mâu thuẫn, duplicate CL | Edge từ chối/normalize theo một quy tắc duy nhất |
| Hop-by-hop | Connection nominate một header identity | Proxy loại bỏ header được nominate |
| Method override | Gửi X-HTTP-Method-Override: DELETE | Không đổi method nếu contract không cho phép |
| Path override | Gửi X-Original-URL hoặc X-Rewrite-URL | Không đổi route |
| Direct upstream | Gọi service bỏ qua gateway kèm identity header giả | Network/mTLS/service auth từ chối |
| Trace abuse | traceparent/baggage quá dài hoặc sai | Bị validate/giới hạn; không ảnh hưởng quyền |
| Header flood | Quá nhiều header hoặc tổng bytes lớn | Từ chối sớm tại edge/server |

### 19.1 Kiểm thử qua tất cả HTTP hop

Chạy test qua CDN, WAF, gateway, ingress và upstream trong môi trường staging. Kiểm tra HTTP/1.1, HTTP/2 và đường downgrade nếu có. Ghi lại principal, peer IP, route và header đã chuẩn hóa tại upstream để xác nhận không có giá trị client giả mạo đi qua.

Không chỉ unit test một filter. Một middleware đúng vẫn có thể bị proxy phía trước ghi đè hoặc middleware sau đọc header khác.

## 20. Logging, monitoring và incident response

Theo dõi:

- Request chứa identity/forwarding header do client tự gửi.
- Sự khác biệt giữa peer IP và IP được suy ra từ forwarding chain.
- Host/authority không nằm trong allowlist hoặc SNI mismatch theo policy.
- Duplicate Authorization/Host/Content-Length và framing bất thường.
- Request có method/path override header.
- Direct-to-upstream request không có gateway identity.
- Header size/count vượt ngưỡng.
- Authentication/authorization deny tăng sau thay đổi proxy.

Log nên ghi request ID nội bộ, route ID, peer identity, trust proxy result, principal/tenant đã xác minh, policy decision và upstream service. Không ghi raw Authorization, cookie, API key hoặc toàn bộ baggage. Nếu cần điều tra header giả mạo, lưu tên header và kết quả strip/deny; chỉ lưu giá trị đã redact hoặc fingerprint có kiểm soát.

Khi phát hiện spoofing:

1. Xác định hop nào đã nhận header và hop nào đã tin giá trị đó.
2. Kiểm tra cấu hình proxy trust và khả năng truy cập trực tiếp upstream.
3. Xác định request/tenant/object bị ảnh hưởng từ audit log.
4. Thu hồi session/token nếu credential bị lộ hoặc principal bị giả mạo qua một trust mechanism bị xâm phạm.
5. Sửa strip/overwrite policy và upstream authentication.
6. Thêm regression test cho đường đi thực tế.
7. Theo dõi lại direct traffic, identity mismatch và authorization decision.

## 21. Các lỗi thiết kế thường gặp

1. **Tin X-User-ID từ client:** cho phép giả mạo principal.
2. **Tin X-Tenant-ID không kiểm tra membership:** mở đường truy cập dữ liệu tenant khác.
3. **Tin X-Forwarded-For đầu tiên:** attacker tự chọn IP dùng cho rate limit hoặc audit.
4. **Bật trust proxy cho mọi nguồn:** client kết nối trực tiếp vẫn có thể giả forwarding header.
5. **Chỉ append mà không strip ở edge:** giá trị giả của client tồn tại trong chuỗi.
6. **Tin X-Forwarded-Proto:** client giả HTTPS và ảnh hưởng cookie/redirect.
7. **Dùng Host tùy ý tạo link:** password reset hoặc cache poisoning.
8. **Chọn Forwarded và X-Forwarded-* không nhất quán:** middleware đánh giá hai origin khác nhau.
9. **Không xử lý duplicate header:** proxy và application lấy giá trị khác nhau.
10. **Bỏ qua request framing:** mở đường request smuggling.
11. **Forward hop-by-hop header:** kết nối nội bộ bị điều khiển sai.
12. **Cho phép method/path override ngoài policy:** đi vòng gateway route.
13. **Tin Origin/Referer là authentication:** machine client có thể tự đặt header.
14. **Tin private network:** workload khác có thể gọi upstream trực tiếp.
15. **Log toàn bộ header:** làm lộ token, cookie và API key.

## 22. Quy trình thiết kế header trust policy

Với mỗi API và đường đi qua gateway:

1. Liệt kê header client có thể gửi và header hạ tầng có thể thêm.
2. Phân loại từng header: input, credential, forwarding, identity, tenant, routing, protocol hoặc observability.
3. Xác định trust boundary và identity của từng proxy hop.
4. Đặt allowlist header được forward; strip header nội bộ do client có thể giả mạo.
5. Xác định proxy nào overwrite/append Forwarded và X-Forwarded-*.
6. Xác minh Host/:authority, scheme và port theo listener/domain allowlist.
7. Xác minh credential; tạo principal context từ token/session đã kiểm tra.
8. Xác minh tenant membership; không coi tenant header là quyền.
9. Chuẩn hóa duplicate/header parsing và request framing tại edge.
10. Loại hop-by-hop header và header override không được phép.
11. Xác thực gateway-to-upstream bằng mTLS/service identity; chặn direct access.
12. Giới hạn header size/count và redact secret trong log.
13. Viết integration test qua toàn bộ proxy chain, gồm direct upstream và HTTP version.
14. Theo dõi drift sau khi đổi CDN, gateway, ingress hoặc framework.

## 23. Checklist rà soát

- [ ] Mọi header do client gửi được coi là untrusted input cho tới khi xác minh.
- [ ] Có sơ đồ trust boundary và danh sách proxy hop được tin cậy.
- [ ] Proxy biên strip/overwrite forwarding header do client gửi.
- [ ] Trusted proxy list giới hạn đúng subnet hoặc service identity; không trust mọi nguồn.
- [ ] IP client lấy từ peer/trusted chain có quy tắc rõ, không chọn mù phần tử đầu.
- [ ] Host/:authority được kiểm tra với domain/listener allowlist.
- [ ] X-Forwarded-Host và X-Forwarded-Proto chỉ được tin từ proxy đã xác thực.
- [ ] Identity header không thể được client tự đặt; principal lấy từ credential đã xác minh.
- [ ] Tenant header chỉ là selector; membership và object authorization được kiểm tra.
- [ ] Authorization/API key/cookie được parse và bảo vệ đúng contract.
- [ ] Content-Type, Content-Length và Transfer-Encoding được parser/proxy xử lý nhất quán.
- [ ] Hop-by-hop và Connection-nominated header được loại bỏ đúng.
- [ ] Method/path override bị tắt hoặc kiểm soát bằng policy rõ ràng.
- [ ] Origin/Referer không được dùng thay authentication.
- [ ] Duplicate header, case, whitespace và header size có chính sách cụ thể.
- [ ] Trace/request ID được validate và không dùng làm identity.
- [ ] Upstream chỉ chấp nhận request từ gateway/service identity được xác thực.
- [ ] Có test spoofing, request smuggling, direct upstream và HTTP/1.1–HTTP/2.
- [ ] Log không chứa token, cookie, API key hoặc header secret.

Header chỉ là dữ liệu truyền tải; độ tin cậy đến từ thành phần đã tạo ra nó và trust boundary được xác minh. Khi edge loại bỏ giá trị giả mạo, proxy ghi lại forwarding metadata, application tạo principal từ credential đã xác minh và upstream chỉ tin gateway identity hợp lệ, các header không còn là đường tắt để giả mạo user, tenant, IP hoặc route.
