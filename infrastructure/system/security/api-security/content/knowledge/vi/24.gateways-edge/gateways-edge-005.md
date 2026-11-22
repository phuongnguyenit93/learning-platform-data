# Preserve identity context qua proxy an toàn

Reverse proxy, ingress và API gateway thường đứng trước ứng dụng để kết thúc TLS, định tuyến request, cân bằng tải hoặc áp dụng policy ở lớp edge. Sau khi proxy chuyển request tới backend, một số thông tin của kết nối ban đầu có thể đã thay đổi: địa chỉ peer mà backend nhìn thấy là địa chỉ proxy, scheme có thể chuyển từ HTTPS thành HTTP trên chặng nội bộ, hostname có thể được rewrite và path có thể bị thêm hoặc bỏ prefix.

Để ứng dụng tạo URL, ghi audit, áp dụng cookie và xử lý policy đúng, proxy thường truyền thêm identity/context metadata qua các HTTP header như `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto` hoặc `X-Forwarded-Host`. Các header này rất hữu ích nhưng cũng nguy hiểm: client có thể tự gửi header giả mạo, proxy có thể nối chuỗi sai, backend có thể tin nhầm một hop không đáng tin, hoặc identity của người dùng có thể bị biến thành một header tự khai báo.

**Preserve identity context qua proxy an toàn** nghĩa là giữ được ngữ cảnh cần thiết của request gốc trong suốt chuỗi proxy, đồng thời xác minh nguồn tạo ra từng thông tin. Backend chỉ được tin metadata do proxy thuộc trust boundary đã cấu hình cung cấp; danh tính người dùng và quyền truy cập vẫn phải được xác minh bằng credential hoặc cơ chế delegation có tính toàn vẹn.

## 1. Vì sao proxy làm thay đổi request context?

Giả sử client gọi API qua hai lớp proxy:

```text
Client
  | HTTPS api.example.com
  v
Edge Load Balancer
  | HTTP hoặc mTLS nội bộ
  v
API Gateway
  | HTTP hoặc mTLS nội bộ
  v
Spring Boot Service
```

Ứng dụng có thể chỉ nhìn thấy:

```text
remote address = 10.20.4.15 (gateway)
scheme         = http
server name    = orders-service
server port    = 8080
request path   = /internal/orders/123
```

Trong khi request bên ngoài ban đầu là:

```text
https://api.example.com/api/v1/orders/123
```

Nếu ứng dụng dùng trực tiếp thông tin socket hiện tại để tạo redirect, callback URL, link trong email hoặc cookie, kết quả có thể sai scheme/host. Nếu dùng `remoteAddr` làm client IP, log và rate limit sẽ ghi địa chỉ gateway thay vì địa chỉ client. Nếu backend tin header tùy ý để khôi phục user identity, attacker có thể tự đặt `X-User-Id` hoặc `X-Role`.

Vì vậy, cần phân biệt ba loại thông tin:

| Loại context | Ví dụ | Nguồn đáng tin cậy cần có |
|---|---|---|
| Kết nối gốc | Client IP, scheme, host, port | Proxy đã xác minh kết nối gốc và ghi đè metadata đầu vào |
| Định tuyến | Public path, upstream path, prefix | Gateway/ingress có cấu hình route rõ ràng |
| Danh tính và quyền | User, service principal, tenant, scope | Token/session/certificate đã xác minh và policy của ứng dụng |

Một header có tên `X-Forwarded-*` không tự trở nên đáng tin chỉ vì request đến từ private network. Phải xác minh peer proxy và quy tắc header trước khi sử dụng.

## 2. Phân biệt client IP với user identity

Client IP là thông tin về điểm mạng mà proxy quan sát được. Nó không phải danh tính người dùng. Một IP có thể được dùng chung bởi nhiều người qua NAT, VPN, corporate proxy hoặc mobile carrier; một người dùng cũng có thể thay đổi IP trong cùng phiên.

User identity thường được xác định từ session hoặc access token đã xác minh. Service identity được xác định từ mTLS, workload identity hoặc client credential. Không suy ra user từ IP và không suy ra quyền từ một header do client tự gửi.

Ví dụ các header sau không phải credential đáng tin nếu không có cơ chế bảo vệ nguồn gốc:

```http
X-User-Id: user-42
X-Role: ADMIN
X-Tenant-Id: tenant-a
X-Authenticated: true
```

Nếu backend nhận trực tiếp các giá trị trên từ client, caller có thể thay đổi chúng để giả danh user khác hoặc tự cấp role. Nếu gateway xác thực user rồi chuyển context xuống backend, gateway phải xóa giá trị cùng tên do client gửi, tạo metadata mới từ identity đã xác minh và bảo vệ chặng gateway-to-backend. Backend cần xác minh gateway hoặc token đã ký trước khi sử dụng context.

## 3. Các header forwarding thường gặp

### `Forwarded` theo RFC 7239

`Forwarded` là header chuẩn hóa trong RFC 7239, có thể mang các tham số như:

- `for`: địa chỉ client/proxy trước đó.
- `by`: proxy thêm thông tin này.
- `host`: host nhận ở phía trước proxy.
- `proto`: scheme nhận ở phía trước proxy.

Ví dụ:

```http
Forwarded: for=198.51.100.24;proto=https;host=api.example.com
```

Header có thể chứa nhiều phần tử, được phân tách bằng dấu phẩy, và giá trị có thể cần dấu ngoặc kép. IPv6, port và quoted-string khiến việc parse bằng cách tách chuỗi đơn giản rất dễ sai. Dùng parser tuân theo RFC thay vì tự xử lý bằng regex.

### Các header `X-Forwarded-*`

Các header `X-Forwarded-*` là quy ước phổ biến trong hệ sinh thái proxy:

| Header | Ý nghĩa thường dùng |
|---|---|
| `X-Forwarded-For` | Danh sách địa chỉ IP trong chuỗi proxy |
| `X-Forwarded-Proto` | Scheme client dùng khi kết nối tới proxy đầu tiên, thường `http` hoặc `https` |
| `X-Forwarded-Host` | Host mà client gửi tới proxy phía trước |
| `X-Forwarded-Port` | Port công khai mà client kết nối |
| `X-Forwarded-Prefix` | Prefix public đã bị proxy loại bỏ hoặc rewrite |

Đây là các header theo convention, không phải một bằng chứng xác thực tự thân. Tên, cách nối giá trị và thứ tự chuỗi có thể khác nhau giữa proxy. Tổ chức cần định nghĩa một contract thống nhất cho từng hop.

### Header đặc thù của proxy

Một số proxy dùng header riêng như `X-Real-IP`, `X-Original-URL`, `X-Rewrite-URL` hoặc `X-Forwarded-Client-Cert` (XFCC). Không nên tin header chỉ vì nó quen thuộc. Cần biết proxy nào tạo ra, proxy có xóa giá trị client gửi không, backend có thể bị truy cập trực tiếp không và giá trị có được ký/xác minh hay chỉ dựa vào mạng.

## 4. Nguyên tắc quan trọng: xóa header không đáng tin ở trust boundary đầu tiên

Client có thể gửi bất kỳ header nào mà giao thức cho phép. Ví dụ attacker gọi trực tiếp:

```http
GET /api/v1/profile HTTP/1.1
Host: api.example.com
X-Forwarded-For: 127.0.0.1
X-Forwarded-Proto: https
X-Forwarded-Host: admin.internal.example
X-User-Id: admin
X-Role: SUPER_ADMIN
```

Nếu edge proxy giữ nguyên các header này và backend tin chúng, attacker có thể giả mạo IP, host, scheme hoặc user context.

Tại proxy đầu tiên được tổ chức tin cậy, hãy:

1. Xác định địa chỉ peer thực tế từ socket hoặc metadata do load balancer được tin cậy cung cấp.
2. Xóa các forwarding header do client gửi vào nếu chúng chưa đến từ một proxy tin cậy đã được xác định.
3. Tạo lại hoặc ghi đè header theo thông tin kết nối mà proxy thực sự quan sát được.
4. Với nhiều hop, quy định rõ proxy nào được phép append và proxy nào phải preserve/normalize.
5. Không cho client tự đặt header danh tính như `X-User-Id`, `X-Role`, `X-Tenant-Id` hoặc `X-Authenticated`.
6. Chỉ chuyển context đã xác minh tới backend qua kết nối được bảo vệ và giới hạn nguồn truy cập.

Không áp dụng mù quáng quy tắc “xóa mọi header có chữ `X-Forwarded`” ở mọi hop: proxy nội bộ cần chuyển metadata đã xác minh cho hop tiếp theo. Quy tắc đúng là xóa dữ liệu không đáng tin ở ranh giới đầu vào và chỉ preserve/append theo contract giữa các proxy thuộc trust chain.

## 5. Đọc `X-Forwarded-For` đúng cách

Một chuỗi ví dụ:

```http
X-Forwarded-For: 198.51.100.24, 203.0.113.10, 10.20.4.15
```

Có thể biểu diễn client và các proxy theo một thứ tự, nhưng thứ tự và cách append phụ thuộc cấu hình. Một lỗi phổ biến là luôn lấy phần tử đầu tiên làm client IP. Nếu proxy không xóa header client gửi trước đó, attacker có thể đặt phần tử đầu tiên thành `127.0.0.1` hoặc một IP được allowlist.

### Dựa vào peer thực tế và danh sách proxy tin cậy

Backend phải biết peer socket hiện tại có thuộc proxy tin cậy không. Nếu request đến trực tiếp từ một địa chỉ không nằm trong danh sách trusted proxy, hãy bỏ qua forwarding header và dùng địa chỉ peer thực tế.

Khi chuỗi proxy được append đúng quy ước, có thể đi từ phía phải của danh sách về bên trái, bỏ qua các hop thuộc dải proxy tin cậy đã cấu hình, rồi xác định địa chỉ không tin cậy đầu tiên. Cách cụ thể phụ thuộc proxy chain và thuật toán của server/framework; không chỉ dựa vào số lượng phần tử hoặc chọn một vị trí cố định khi topology thay đổi.

Ví dụ minh họa:

```text
X-Forwarded-For: client, public-proxy, internal-gateway
                                      ^ socket peer

1. Xác minh socket peer là internal-gateway đáng tin cậy.
2. Đi ngược chuỗi theo đúng quy ước append.
3. Bỏ qua các proxy có địa chỉ nằm trong trusted-proxy configuration.
4. Lấy hop đầu tiên không thuộc trust list làm địa chỉ client quan sát được.
```

Nếu edge proxy luôn ghi đè `X-Forwarded-For` bằng peer IP mà nó quan sát được, rồi các proxy nội bộ append địa chỉ peer của mình, chuỗi sẽ dễ kiểm soát hơn. Hãy cấu hình và kiểm thử hành vi thực tế của từng proxy.

### Trusted proxy list phải cụ thể

Không cấu hình tin cậy toàn bộ private ranges chỉ vì proxy chạy trong mạng nội bộ. Một workload bị chiếm quyền trong cùng VPC có thể gửi header giả mạo nếu backend tin mọi IP private. Chỉ đưa subnet hoặc identity của proxy thực sự vào trust list; giữ danh sách này đồng bộ với hạ tầng và kiểm thử khi autoscaling hoặc thay đổi network.

IPv6, IPv4-mapped IPv6, port, khoảng trắng và biểu diễn địa chỉ bất thường cũng cần được parser xử lý đúng. Không dùng chuỗi IP chưa chuẩn hóa làm khóa rate limit hoặc bằng chứng bảo mật.

## 6. Preserve scheme và host an toàn

Sau khi TLS kết thúc ở edge, chặng từ proxy tới backend có thể dùng HTTP nội bộ. Backend nhìn thấy scheme `http` dù client đã dùng HTTPS. `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https` giúp ứng dụng khôi phục scheme gốc.

Scheme và host ảnh hưởng tới:

- Redirect và URL tuyệt đối trong response.
- Link xác minh email, callback OAuth/OIDC và webhook URL.
- Cookie `Secure`, URL canonical và HSTS behavior.
- CORS origin validation và absolute link trong tài liệu.
- Audit/log hiển thị địa chỉ request.

`X-Forwarded-Host` cũng có thể bị lợi dụng trong Host Header Injection nếu ứng dụng dùng nó để tạo link hoặc reset-password URL mà không xác minh host. Hãy cấu hình allowlist host công khai; không dùng host tùy ý từ request để tạo URL nhạy cảm.

### Quy tắc thực tế

- Chỉ tin `proto` và `host` từ proxy đã xác minh.
- Chỉ chấp nhận scheme dự kiến, thường `https` cho public API.
- Kiểm tra host theo danh sách domain hợp lệ; không chấp nhận host lạ chỉ vì proxy forward.
- Không tạo link reset password/OAuth callback từ host header chưa xác minh.
- Cookie session cần cấu hình `Secure`, `HttpOnly` và `SameSite` phù hợp; forwarded proto không thay thế việc cấu hình cookie.
- HSTS nên được phát hành ở ranh giới TLS công khai hoặc theo kiến trúc đã kiểm thử.

## 7. Preserve path và prefix khi gateway rewrite

Gateway có thể expose `/public/api/orders/123` rồi bỏ prefix `/public` trước khi chuyển tới backend `/api/orders/123`. Một số hệ thống dùng `X-Forwarded-Prefix` hoặc `Forwarded` extension để cho ứng dụng biết public prefix.

Path context ảnh hưởng tới:

- URL tạo ra trong response và OpenAPI server URL.
- Redirect login/logout và callback.
- Cookie `Path`.
- Route matching, authorization và audit.
- Canonicalization và chống path traversal.

Không tin `X-Original-URL`, `X-Rewrite-URL` hoặc `X-Forwarded-Prefix` do client gửi. Proxy phải xóa giá trị đầu vào và tạo giá trị mới theo route rule. Backend và gateway phải thống nhất path canonical mà authorization layer kiểm tra.

Đặc biệt chú ý encoded slash (`%2F`), dot segment (`..`), repeated slash, percent encoding kép và khác biệt chuẩn hóa giữa gateway với framework. Nếu gateway authorize `/users/123` nhưng backend giải mã hoặc chuẩn hóa thành `/users/admin`, có thể phát sinh authorization bypass. Nên canonicalize nhất quán, từ chối biểu diễn mơ hồ và kiểm thử cả hai lớp.

## 8. Không truyền user identity bằng header tự khai báo

Gateway có thể xác thực access token của người dùng rồi cần chuyển user context tới backend. Không nên chỉ thêm:

```http
X-User-Id: user-42
X-Tenant-Id: tenant-a
X-Role: ADMIN
```

và giả định backend sẽ tin các giá trị này. Nếu backend bị truy cập trực tiếp, một service khác gọi tới hoặc header bị giả mạo, caller có thể nâng quyền.

Các lựa chọn an toàn hơn:

### Backend tự xác minh access token

Gateway chuyển tiếp bearer token gốc khi kiến trúc cho phép và backend tự xác minh chữ ký/introspection, issuer, audience, thời hạn và scope. Token phải được phát hành cho resource server đích. Không chuyển tiếp token chỉ vì nó hợp lệ ở gateway; `aud` có thể chỉ dành cho gateway.

### Token exchange hoặc delegated token

Gateway hoặc backend đổi token đầu vào lấy token mới dành riêng cho downstream service. Token mới có audience, scope và thời hạn tối thiểu cần thiết, đồng thời thể hiện ngữ cảnh delegation theo authorization server. Đây là lựa chọn phù hợp khi mỗi service cần một trust boundary và quyền khác nhau.

### Signed identity assertion

Trong một kiến trúc đã định nghĩa rõ, gateway có thể tạo assertion có chữ ký chứa subject, issuer, audience, thời hạn và các claim cần thiết. Backend phải xác minh chữ ký, issuer, audience, expiry và replay policy. Không dùng header JSON tự khai báo không có chữ ký làm identity assertion.

Không tự phát minh giao thức identity header nếu có thể dùng OAuth/OIDC token hoặc cơ chế delegation đã được hỗ trợ. Cơ chế tùy chỉnh cần canonicalization, key management, rotation, replay protection và kiểm thử tương đương.

## 9. Phân biệt service identity, user identity và actor

Trong request xuyên nhiều service, có thể có nhiều danh tính cùng lúc:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Client/user subject | Người dùng khởi tạo hành động | `user-42` |
| Calling service | Workload đang gọi backend | `orders-service` |
| Gateway/proxy | Hạ tầng trung gian chuyển tiếp | `edge-gateway` |
| Delegated actor | Người dùng mà service đang hành động thay mặt | `user-42` với delegation đã xác minh |
| Resource owner/tenant | Chủ sở hữu dữ liệu đang truy cập | `tenant-a` |

Backend cần biết service caller nào kết nối và, nếu nghiệp vụ yêu cầu, hành động đang được thực hiện thay mặt user nào. Một service có thể được quyền gọi endpoint nhưng không có quyền truy cập mọi tenant. User có thể được phép đọc object nhưng service caller lại không có scope cần thiết. Quyết định cuối cùng phải xét cả hai theo policy.

Không gộp `sub`, `client_id`, `azp`, `act` hoặc tenant claim thành một trường `userId` chung mà không hiểu ngữ nghĩa token profile. Tên claim và ý nghĩa phụ thuộc authorization server/protocol; cần công bố contract và xác minh ở resource server.

## 10. Bảo vệ client certificate context qua TLS termination

Một số kiến trúc kết thúc mTLS tại edge proxy rồi chuyển thông tin certificate của client tới backend bằng header như `X-Forwarded-Client-Cert`. Đây là dữ liệu nhạy cảm vì backend có thể dùng nó để nhận diện workload hoặc đối tác.

Nếu dùng cơ chế này:

1. Edge proxy phải thực sự xác minh client certificate trong TLS handshake theo CA, expiry, EKU và trust policy.
2. Proxy phải xóa mọi XFCC/client-certificate header do client gửi trước khi tạo metadata mới.
3. Proxy phải cấu hình rõ mức thông tin được forward, ví dụ subject/SAN/fingerprint, tránh gửi toàn bộ certificate hoặc thông tin không cần thiết.
4. Backend chỉ nhận kết nối từ proxy được xác minh, tốt nhất có mTLS trên chặng proxy-to-backend.
5. Backend chỉ tin XFCC từ peer proxy được phép và xác minh format/issuer context theo contract.
6. Không xem header certificate là bằng chứng độc lập nếu bất kỳ caller nào cũng có thể kết nối trực tiếp backend.

Nếu backend cần xác thực certificate độc lập, hãy triển khai mTLS end-to-end hoặc dùng workload identity. Forwarded certificate metadata không tương đương với backend tự thực hiện TLS client authentication.

## 11. Hop-by-hop headers và chuẩn hóa header

Không phải header nào cũng được phép chuyển tiếp qua proxy. HTTP có các hop-by-hop header như `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding` và `Upgrade` (theo ngữ cảnh giao thức). Proxy phải xử lý đúng các header này thay vì chuyển tiếp nguyên trạng như end-to-end metadata.

Header `Connection` có thể liệt kê thêm header tùy chỉnh chỉ có ý nghĩa ở một hop; proxy cần loại bỏ cả những header được liệt kê đó trước khi forward. Nếu không, metadata hoặc control header dành riêng cho một hop có thể lọt sang backend.

### Header duplicate và request smuggling

Các proxy có thể diễn giải header trùng, tên header khác chữ hoa/thường, khoảng trắng hoặc xung đột `Content-Length`/`Transfer-Encoding` khác nhau. Sự không thống nhất giữa edge và backend có thể tạo request smuggling hoặc khiến hai lớp áp dụng policy trên hai request khác nhau.

Hãy:

- Chuẩn hóa header ở edge theo HTTP parser được hỗ trợ.
- Từ chối request có framing mơ hồ hoặc header quan trọng bị lặp không hợp lệ.
- Không tự nối các giá trị header nhạy cảm theo cách không được contract quy định.
- Giới hạn tổng kích thước và số lượng header.
- Cập nhật proxy/server để xử lý đúng HTTP/1.1, HTTP/2 và chuyển đổi giao thức.
- Kiểm thử behavior khi gateway chuyển HTTP/2 xuống HTTP/1.1 hoặc ngược lại.

Đối với identity/forwarding header, nên có một nguồn chuẩn duy nhất và một quy tắc duplicate rõ ràng. Nếu nhận nhiều giá trị không mong đợi, từ chối hoặc chuẩn hóa tại trust boundary; không để từng tầng tự chọn giá trị khác nhau.

## 12. Không nhầm trace context với identity context

`traceparent`, `tracestate`, `X-Request-Id` hoặc correlation ID giúp nối request qua nhiều service. Chúng không chứng minh ai đang gọi và không cấp quyền.

Client có thể tự gửi trace ID hoặc request ID. Hệ thống có thể chấp nhận chúng sau khi validate định dạng/độ dài hoặc tạo ID mới tại edge. Không dùng trace ID làm session ID, authorization token hoặc khóa để truy cập log nhạy cảm.

Khi chuyển tiếp trace context:

- Tuân theo W3C Trace Context hoặc contract tracing đã chọn.
- Giới hạn kích thước và loại bỏ giá trị malformed.
- Không đưa user email, token hoặc dữ liệu cá nhân vào `tracestate`/baggage.
- Có thể tạo trace mới hoặc đánh dấu context không tin cậy theo chính sách khi nhận từ internet.
- Ghi identity đã xác minh vào log/tracing attributes riêng, không lấy từ trace header.

## 13. Cấu hình Spring Boot để xử lý forwarded headers

Spring Boot hỗ trợ các chiến lược xử lý forwarded headers qua `server.forward-headers-strategy`. Ví dụ:

```yaml
server:
  forward-headers-strategy: framework
```

Các giá trị phổ biến gồm `none`, `native` và `framework`:

- `none`: không bật cơ chế xử lý forwarded headers tự động.
- `native`: dùng khả năng của web server/container, ví dụ Tomcat RemoteIpValve khi được cấu hình.
- `framework`: dùng cơ chế xử lý forwarded headers của Spring Framework.

Chọn chiến lược phù hợp với proxy/container và xác minh behavior bằng integration test. Không bật đồng thời nhiều lớp xử lý mà không hiểu thứ tự, vì header có thể bị xử lý hai lần hoặc tạo kết quả khác dự kiến.

### Ranh giới tin cậy quan trọng hơn property

Property trên không tự xác định proxy nào đáng tin trong mọi deployment. Nếu ứng dụng có thể được truy cập trực tiếp từ internet hoặc từ workload không tin cậy, attacker có thể gửi `X-Forwarded-For`, `X-Forwarded-Proto` hoặc `Forwarded` giả. Hãy:

- Chỉ expose backend qua proxy/gateway được quản lý; chặn direct access bằng network policy/firewall/security group.
- Cấu hình proxy đầu tiên xóa header giả mạo và tạo lại giá trị tin cậy.
- Cấu hình trusted proxy ranges/hops tại container nếu cơ chế native hỗ trợ.
- Không dùng forwarded metadata để xác thực user hoặc cấp role.
- Kiểm tra `request.getRemoteAddr()`, `getScheme()`, `isSecure()`, `getServerName()` và URL được tạo trong môi trường có proxy thật.

Với Tomcat, `RemoteIpValve` có thể dùng `internalProxies`, `remoteIpHeader` và `protocolHeader`. Cần giới hạn `internalProxies` theo topology thực tế; không dùng pattern quá rộng. Chi tiết property phụ thuộc phiên bản Spring Boot/Tomcat và cần đối chiếu cấu hình đang dùng.

## 14. Ví dụ cấu hình gateway theo nguyên tắc

Pseudo configuration sau mô tả logic cần có, không phải cú pháp dành cho một sản phẩm gateway cụ thể:

```text
on request from client:
    peer = socket.remoteAddress

    # Không nhận forwarding context tự khai báo từ internet.
    remove request headers:
        Forwarded
        X-Forwarded-For
        X-Forwarded-Proto
        X-Forwarded-Host
        X-Forwarded-Port
        X-Forwarded-Prefix
        X-User-Id
        X-Role
        X-Tenant-Id
        X-Forwarded-Client-Cert

    verifiedClientIp = peer
    verifiedScheme = tls.handshake ? "https" : "http"
    verifiedHost = validateAllowedHost(request.host)

    set Forwarded/X-Forwarded metadata from verified values
    authenticate user or client credential
    authorize edge-level route policy
    connect to backend over protected network/mTLS
```

Nếu có load balancer phía trước gateway, `peer` mà gateway nhìn thấy có thể là load balancer. Khi đó chỉ nhận context từ load balancer nếu gateway xác minh được nguồn kết nối và load balancer đã xóa/ghi đè header đầu vào. Trust chain phải được cấu hình rõ từ edge tới backend, không chỉ dựa vào tên header.

Gateway có thể chuyển token đã xác minh hoặc delegated token tới backend theo contract. Nếu chuyển identity context bằng header riêng, cần chữ ký hoặc một cơ chế bảo vệ tính toàn vẹn và backend phải xác minh nguồn trước khi sử dụng.

## 15. Bảo vệ chặng proxy-to-backend

Ngay cả khi edge đã tạo header đúng, chặng tới backend vẫn cần được bảo vệ. Nếu bất kỳ workload nào trong mạng có thể gọi backend và tự đặt `X-User-Id`, `X-Forwarded-For` hoặc XFCC, trust boundary đã bị phá vỡ.

Các kiểm soát nên kết hợp:

- Network policy/firewall chỉ cho phép proxy/gateway cần thiết kết nối backend.
- mTLS hoặc workload identity để backend xác minh caller là gateway/service được phép.
- Backend xác minh token/audience/scope hoặc signed assertion nếu cần user context.
- Gateway xóa header client-supplied và chuẩn hóa metadata trước khi forward.
- Backend không có listener public/direct path bỏ qua gateway nếu policy dựa vào edge.
- Mỗi service vẫn thực hiện authorization theo endpoint, object, tenant và nghiệp vụ.

Không coi mTLS là thay thế authorization. Certificate của gateway chứng minh caller kỹ thuật; nó không tự chứng minh user cuối có quyền đọc một object cụ thể.

## 16. Ảnh hưởng tới cookie, redirect và URL sinh ra

Ứng dụng có thể tạo absolute URL dựa trên scheme/host/path mà nó nhìn thấy. Nếu forwarded context sai, các lỗi có thể gồm:

- Redirect từ HTTPS về HTTP, làm giảm bảo vệ hoặc tạo vòng redirect.
- Link xác minh tài khoản/reset password trỏ tới domain attacker kiểm soát nếu host header bị tin.
- OAuth/OIDC redirect URI hoặc callback không khớp allowlist.
- Cookie thiếu `Secure` vì backend nghĩ request dùng HTTP.
- Cookie có `Path` sai sau khi gateway rewrite prefix.
- CORS hoặc origin validation dựa trên host/proto giả mạo.

Không dùng forwarded host để tự động mở rộng danh sách allowed origin hoặc callback. Cấu hình public base URL rõ ràng cho các luồng nhạy cảm. Với cookie, thiết lập thuộc tính bảo mật trực tiếp và kiểm thử qua HTTPS termination thật.

## 17. Kiểm thử preserve identity context

Kiểm thử cần chạy qua toàn bộ chuỗi proxy, không chỉ gọi controller bằng MockMvc. Các tình huống quan trọng:

| Nhóm | Ca kiểm thử |
|---|---|
| Spoofing | Client gửi `X-Forwarded-For: 127.0.0.1`, `X-Role: ADMIN` hoặc `X-User-Id` giả |
| Direct access | Gọi backend không qua gateway; forwarded headers phải bị bỏ qua hoặc kết nối bị chặn |
| Proxy chain | Một, hai và nhiều hop; xác định đúng client IP theo trusted proxy list |
| Untrusted peer | Request từ IP không thuộc trusted proxy nhưng có forwarding header |
| Duplicate header | Lặp `Forwarded`, `X-Forwarded-For`, `Host` hoặc identity header |
| Host/scheme | Host lạ, HTTPS termination, HTTP nội bộ, redirect và secure cookie |
| Path rewrite | Prefix bị strip, encoded slash, dot segment và double encoding |
| Credential forwarding | Authorization/cookie không bị gửi sang origin khác hoặc audience sai |
| Client certificate | XFCC giả từ client bị xóa; chỉ certificate metadata từ proxy tin cậy được nhận |
| Header parsing | IPv6, quoted string, comma chain, khoảng trắng và giá trị malformed |
| HTTP protocol | HTTP/2-to-HTTP/1.1, hop-by-hop header và framing bất thường |
| Trace context | Trace ID giả không tạo quyền; baggage không chứa secret |
| Audit/rate limit | Client IP và actor được ghi đúng nguồn; không thể bypass limit bằng header giả |

Kiểm thử phải xác nhận cả giá trị ứng dụng nhìn thấy và quyết định authorization. Ví dụ, request spoof `X-Role: ADMIN` không được trả dữ liệu admin; request direct-to-backend không được tự tạo user context; host lạ không được xuất hiện trong reset link.

## 18. Giám sát và điều tra

Log có thể ghi các trường đã chuẩn hóa:

- Socket peer/proxy identity và nguồn forwarding context.
- Client IP đã tính theo trusted proxy chain, kèm độ tin cậy/nguồn.
- Scheme, host và public path đã được xác minh.
- Caller service identity, user subject và tenant lấy từ credential đã xác minh.
- Route template, method, status, policy decision và request/trace ID.
- Số hop proxy hoặc trạng thái forwarding header malformed/duplicate.

Không ghi raw access token, cookie, API key, private key hoặc toàn bộ XFCC nếu không cần. Không dùng IP/header chưa xác minh làm dữ liệu duy nhất để điều tra hoặc ra quyết định khóa tài khoản.

Nên cảnh báo khi backend nhận request từ peer ngoài trust list, có forwarding header bất thường, host ngoài allowlist, direct access bypass gateway, user context không khớp token hoặc số lượng request bị từ chối do malformed header tăng đột biến. Log phải phân biệt rõ `observed client IP` với `authenticated subject`.

## 19. Checklist preserve identity context qua proxy an toàn

- [ ] Xác định rõ trust boundary và danh sách proxy/gateway được phép tạo forwarding metadata.
- [ ] Edge proxy xóa hoặc ghi đè forwarding header do client gửi vào.
- [ ] Backend chỉ đọc forwarded metadata khi peer là proxy đã xác minh.
- [ ] `X-Forwarded-For` được xử lý theo trust chain; không mặc định lấy phần tử đầu tiên.
- [ ] Trusted proxy ranges/hops cụ thể, không tin toàn bộ private network.
- [ ] Scheme và host được kiểm tra; không tạo URL nhạy cảm từ host tùy ý.
- [ ] Path/prefix rewrite được chuẩn hóa nhất quán giữa gateway và authorization layer.
- [ ] User identity không được tin từ `X-User-Id`, `X-Role` hoặc `X-Tenant-Id` tự khai báo.
- [ ] Token được xác minh tại resource server hoặc được exchange thành token đúng audience/scope.
- [ ] Service identity và user identity được phân biệt; delegation có tính toàn vẹn.
- [ ] XFCC/client certificate header chỉ được tin từ proxy đã xác minh và đã xóa giá trị client gửi.
- [ ] Hop-by-hop và duplicate headers được xử lý đúng; request framing mơ hồ bị từ chối.
- [ ] Trace/correlation ID không được dùng làm credential hoặc authorization input.
- [ ] Backend được bảo vệ khỏi direct access; proxy-to-backend dùng network control và mTLS/workload identity khi phù hợp.
- [ ] Spring/container forwarded-header strategy được cấu hình một lần và kiểm thử theo topology thực tế.
- [ ] Có test spoofing, multi-hop, IPv6, host injection, path rewrite và direct backend access.
- [ ] Log phân biệt proxy peer, client IP quan sát được, service principal và user subject.

## Kết luận

Proxy làm thay đổi địa chỉ peer, scheme, host và đôi khi cả path mà backend nhìn thấy. Forwarded headers giúp khôi phục context của request gốc, nhưng chỉ an toàn khi được tạo và chuyển tiếp qua một trust chain rõ ràng. Hãy xóa metadata do client tự khai báo tại edge, xác minh từng proxy, xử lý `X-Forwarded-For` theo danh sách trusted proxy, kiểm tra host/scheme/path và bảo vệ chặng proxy-to-backend. User identity phải đến từ token/session hoặc assertion có thể xác minh; client IP, trace ID và header tùy chỉnh không phải credential. Khi các lớp gateway, container và ứng dụng dùng cùng một contract và được kiểm thử xuyên suốt, hệ thống có thể giữ context chính xác mà không biến proxy thành đường giả mạo danh tính.
