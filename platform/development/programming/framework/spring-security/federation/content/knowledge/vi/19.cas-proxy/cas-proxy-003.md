# Endpoint proxy callback và điều kiện HTTPS, chứng thư

> **Chủ đề:** Spring Security – federation. **Nhóm:** CAS Proxy. Bài Knowledge hướng dẫn cách ứng dụng Spring Security làm **CAS proxying service** nhận **Proxy-Granting Ticket (PGT)** qua endpoint callback, cấu hình đúng `pgtUrl`/`proxyCallbackUrl`/`proxyReceptorUrl`, đáp ứng điều kiện **HTTPS và xác minh chứng thư TLS/PKIX** của CAS Server, rồi dùng PGT để xin **Proxy Ticket (PT)** truy cập một back-end service. Phạm vi là CAS protocol 2.0/3.0, Java 17+ và Spring Security Servlet CAS client; ví dụ tích hợp dựa trên Spring Security 6.5.x, có đối chiếu API khi dùng phiên bản khác.

## 1. Mục tiêu học tập và điều kiện tiên quyết

Sau bài học, bạn có thể:

1. Phân biệt `Service Ticket (ST)`, `Proxy-Granting Ticket (PGT)`, `Proxy-Granting Ticket IOU (PGTIOU)`, `Proxy Ticket (PT)`, `Ticket-Granting Ticket (TGT)` và session ứng dụng.
2. Giải thích vì sao CAS Server **chủ động kết nối từ server đến server** tới `pgtUrl`, không chỉ redirect trình duyệt về ứng dụng.
3. Định nghĩa đúng hai địa chỉ khác nhau: `ServiceProperties.service` là endpoint nhận ST, còn `proxyCallbackUrl` là endpoint CAS gọi để giao PGT.
4. Cấu hình **`Cas20ProxyTicketValidator` và `CasAuthenticationFilter` dùng cùng một `ProxyGrantingTicketStorage`**; hiểu quan hệ giữa URL callback tuyệt đối và local filter matcher.
5. Hiểu chính xác điều kiện của CAS protocol: `pgtUrl` phải là **HTTPS**, CAS Server phải thiết lập trust đối với peer bằng kiểm tra chứng thư/PKIX, và callback phải trả HTTP **200 OK** thì việc phát PGTIOU mới hoàn tất.
6. Chẩn đoán lỗi hostname/SAN, certificate expiry, trust chain, root CA, reverse proxy, redirect, ingress, firewall/WAF và đường dẫn sai.
7. Vận hành storage/tương quan `pgtId ↔ pgtIou` an toàn, có TTL, phân vùng tenant, đồng bộ node, ngăn mất PGT do callback đến node khác.
8. Biết kiểm `proxy chain` ở downstream, không dùng `acceptAnyProxy=true` tùy tiện.
9. Viết cấu hình Spring Security CAS minh họa có các bean đúng và ví dụ Java 17 standalone để kiểm tra ý nghĩa correlation, URL và failure modes.
10. Xây test matrix đủ positive/negative để xác nhận PGT issuance, callback HTTPS, chứng thư, proxy ticket scope và không rò secret.

**Giới hạn của bài:** Nếu ứng dụng chỉ cần CAS SSO và local HttpSession, **không cần PGT callback**. Cơ chế proxy chỉ bật khi **ứng dụng A cần thay mặt user truy cập ứng dụng B** đã được CAS bảo vệ. Không mở endpoint mới hoặc cấp proxying privilege khi không có use case được phê duyệt.

## 2. Vì sao CAS Proxy cần một callback khác với CAS login?

Kịch bản: người dùng đăng nhập vào App A qua CAS. App A cần lấy dữ liệu tại API B, nhưng B không thấy browser cookie/TGT và không nên tin một username tự gửi trong HTTP header.

```text
                   [ CAS SERVER ]
                   /cas/login
                   /cas/serviceValidate
                   /cas/proxy
                   /cas/proxyValidate
                         |
               HTTPS GET pgtUrl callback
                         |
                         v
[ Browser ] ---> [ APP A / CAS CLIENT ] ----PT----> [ BACKEND SERVICE B ]
                   /login/cas                      /data, /proxyValidate
                   /login/cas/proxyreceptor
```

App A đã xác thực user bằng ST, nhưng ST **chỉ dùng một lần cho App A** và không được sao chép sang B. Để A đại diện user, CAS phát một **PGT** cho A. App A dùng PGT yêu cầu CAS phát một **PT dành riêng cho service B**. B phải kiểm PT bằng CAS `/proxyValidate` và đánh giá **proxy chain** mà policy B chấp nhận.

Điểm kiểm soát tạo PGT nằm ở **proxy callback endpoint**. CAS không đơn thuần tin một app có ST hợp lệ rồi cấp PGT qua kênh HTTP bất kỳ; nó phải xác minh rằng callback HTTPS thật sự thuộc về service được cho phép proxy.

### 2.1. Bảng phân biệt các ticket

| Thành phần | Được dùng ở đâu? | Phạm vi/đặc tính | Có được dùng làm gì? |
| --- | --- | --- | --- |
| `ST-...` / Service Ticket | Browser đưa về App A, App A validate tại CAS | Một lần và ràng buộc `service` | Chứng minh login vào A, **không** dùng để gọi B |
| `PGT-...` / Proxy-Granting Ticket | CAS cấp riêng cho App A qua callback HTTPS | Credential nhạy cảm được A giữ ở server; có thể xin nhiều PT đến khi bị hết hạn/thu hồi | Xin PT mới tại CAS `/proxy` |
| `PGTIOU-...` | CAS trả trong kết quả `/serviceValidate`/`/proxyValidate` | Mã tương quan để A tìm PGT đã lưu qua callback | **Không** thay PGT để gọi `/proxy` |
| `PT-...` / Proxy Ticket | App A gọi service B; B validate tại CAS | Gắn với `targetService`, dùng một lần khi validate, có proxy chain | Đại diện user đến đúng B |
| `TGT`/`TGC` | CAS Server và browser tại CAS origin | SSO session của CAS Server | Giúp CAS phát ST mới; không phải PGT |
| `JSESSIONID` / local session | Browser và App A | Phiên ứng dụng A | Không phải PT, PGT, PGTIOU |

**Lưu ý:** PGT không phải OAuth2 refresh token và PT không phải OIDC access token; mô hình CAS proxy có endpoints/verification riêng. Không đưa PGT cho browser hay lưu vào `localStorage`/cookie. Nếu dịch vụ B chỉ hỗ trợ OAuth2, cần broker/token exchange có policy riêng, **không** gửi PT CAS như Bearer JWT.

### 2.2. Hai loại “callback” trong một ứng dụng

| URL | Ai gọi? | Dữ liệu gửi | Nhiệm vụ |
| --- | --- | --- | --- |
| `https://app.example.org/login/cas` | **Browser** sau CAS login | `?ticket=ST-...` | `CasAuthenticationFilter` nhận ST để tạo local Authentication |
| `https://app.example.org/login/cas/proxyreceptor` | **CAS Server** (HTTP client) | `?pgtId=PGT-...&pgtIou=PGTIOU-...` | CAS client lưu PGT với IOU, trả HTTP 200 |
| `https://sso.example.org/cas/serviceValidate` | **Backend App A** | `ticket=ST`, `service=...`, `pgtUrl=...` | CAS kiểm ST và bắt đầu cấp PGT nếu callback đạt yêu cầu |
| `https://sso.example.org/cas/proxy` | **Backend App A** | `pgt=PGT`, `targetService=B` | CAS cấp PT dành cho B |
| `https://sso.example.org/cas/proxyValidate` | **Backend B** | `ticket=PT`, `service=B` | CAS xác minh PT và proxy chain |
| `https://app.example.org/logout` | Browser | Request logout local | Không phải PGT callback và không tự thu hồi mọi PGT/TGT |

**Hai callback là hai endpoint khác nhau.** CAS `/login` redirect browser về `/login/cas`; còn CAS `/serviceValidate` mở một kết nối server-to-server tới `/login/cas/proxyreceptor`. Nhầm hai endpoint làm một có thể khiến CAS không nhận HTTP 200, bị redirect về login hoặc xử lý PGT như ST.

## 3. Luồng cấp PGT chi tiết theo CAS Protocol

Giả sử ba hệ thống thật trong môi trường thử nghiệm:

```text
CAS Server base:       https://sso.example.org/cas
App A service URL:     https://app.example.org/login/cas
App A proxy callback:  https://app.example.org/login/cas/proxyreceptor
Target service B:      https://api.example.org/reports
```

Trình tự chuẩn:

1. Browser chưa có local session A vào trang `/reports` của A.
2. App A chuyển browser đến `https://sso.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas`.
3. CAS xác thực user (hoặc tái dùng TGT/TGC hợp lệ) và **phát ST cho service A**.
4. Browser GET `https://app.example.org/login/cas?ticket=ST-...`. Spring Security `CasAuthenticationFilter` nhận ST.
5. App A backend gọi `/cas/serviceValidate` kèm **`ticket`, `service` và `pgtUrl`**, trong đó `pgtUrl` là absolute HTTPS URL callback.
6. CAS kiểm ST/service và policy App A được proxy; trước khi giao PGT, CAS **kết nối HTTPS tới `pgtUrl` và xác minh peer certificate theo PKIX/trust policy**.
7. CAS gửi **HTTP GET** tới `pgtUrl?pgtId=PGT-...&pgtIou=PGTIOU-...`. Giá trị thật là credential nhạy cảm; ví dụ này chỉ là ký hiệu.
8. Endpoint proxy receptor trên A lưu cặp `(PGTIOU, PGT)` vào `ProxyGrantingTicketStorage`. Phản hồi HTTP **200 OK**, không redirect sang IdP/login.
9. Nếu callback thành công, CAS trả kết quả `serviceValidate` với `<cas:authenticationSuccess>` và `<cas:proxyGrantingTicket>PGTIOU-...</cas:proxyGrantingTicket>`.
10. Client A tra PGT tương ứng với PGTIOU trong storage. Đây là **bước correlation**, không đọc PGT từ XML validation response.
11. App A dùng PGT để gọi CAS `/proxy?pgt=PGT-...&targetService=https%3A%2F%2Fapi.example.org%2Freports`. CAS cấp PT.
12. App A gọi API B kèm PT theo CAS client/protocol; B gọi CAS `/proxyValidate`, kiểm PT đúng target service, còn hiệu lực và chuỗi proxy được cho phép.
13. B trả kết quả cho A nếu **CAS validation + authorization nghiệp vụ B** đều đạt. A không được coi việc đã có PT là quyền đọc mọi API/tenant.

### 3.1. Sequence diagram

```text
Browser         App A (Spring CAS)              CAS Server                Service B
  |                    |                            |                         |
  |-- GET /reports --->|                            |                         |
  |<-- CAS login 302 --|                            |                         |
  |------------------------------ CAS login -------->|                         |
  |<----------------------------- service ST --------|                         |
  |-- /login/cas?ticket=ST ----->|                    |                         |
  |                    |-- /serviceValidate -------->|                         |
  |                    |   ticket=ST, service=A      |                         |
  |                    |   pgtUrl=https://A/receptor |                         |
  |                    |                            |-- TLS PKIX to A ----->  |
  |                    |<--- GET /receptor ----------|                         |
  |                    |    pgtId + pgtIou           |                         |
  |                    |--- 200 OK ----------------->|                         |
  |                    |<-- success + PGTIOU --------|                         |
  |                    |-- lookup PGT by PGTIOU      |                         |
  |<-- App A session --|                            |                         |
  |                    |-- /proxy?pgt&targetService ->|                         |
  |                    |<--------------- PT --------|                         |
  |                    |-------------------------------- PT ------------------>|
  |                    |                            |<-- /proxyValidate PT ----|
  |                    |                            |---- valid + proxies ---->|
  |                    |<----------------------------------- authorized data --|
  |<-- page/data ------|                            |                         |
```

Trong sơ đồ, mũi tên “TLS PKIX to A” tượng trưng cho **CAS Server** thiết lập kết nối tới public HTTPS callback của A; không phải service B. Callback có thể diễn ra song song với việc ứng dụng A đang chờ kết quả validation. **Vì vậy PGT storage cần an toàn trong môi trường nhiều luồng/nhiều node**.

### 3.2. Dạng request minh họa

Bước validate ST từ App A đến CAS:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-EXAMPLE&pgtUrl=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas%2Fproxyreceptor HTTP/1.1
Host: sso.example.org
```

Bước CAS gọi callback (từ CAS Server đến App A, **không phải browser**):

```http
GET /login/cas/proxyreceptor?pgtId=PGT-EXAMPLE&pgtIou=PGTIOU-EXAMPLE HTTP/1.1
Host: app.example.org
```

Bước CAS trả cho App A sau callback 200:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-EXAMPLE</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

**Không hiểu nhầm:** XML trả về **PGTIOU**, không trả nguyên `PGT-EXAMPLE`. PGT đến App A qua **HTTPS callback** rồi được lưu server-side. Các ví dụ trên không phải ST/PGT có giá trị thật; không thể dùng chúng để gọi CAS Server production.

## 4. `pgtUrl` là định danh nhạy cảm, và HTTPS là yêu cầu giao thức

Theo CAS Protocol 3.0, `pgtUrl` được gửi lúc validate ST/PT và **MUST dùng HTTPS**. CAS Server phải đánh giá endpoint để thiết lập tin cậy; mức tối thiểu là sử dụng **PKIX** và certificate trust của môi trường chạy để xác minh:

- Chữ ký chứng thư và certificate chain tới một trust anchor được CAS chấp nhận.
- Khoảng hiệu lực của certificate (`notBefore`, `notAfter`), không expired/not-yet-valid.
- Danh tính hostname của callback theo TLS hostname verification, thường dựa trên Subject Alternative Name (SAN), với chính sách tương thích triển khai.
- Thuật toán/độ dài khóa, key usage/EKU, CA constraints và chính sách vận hành nếu CAS/TLS client có kiểm tra.
- Đường HTTPS thực tế truy cập được, handshake hoàn tất, callback path trả **HTTP 200**.

**Câu chuyện hai chiều:** CAS Server đóng vai **TLS client** khi nó gọi callback của App A; reverse proxy/ingress của A đóng vai **TLS server** và phải trình certificate hợp lệ. Đây là **chứng thư TLS của A**, không phải public certificate SAML signing của IdP hay SP private key dùng ký SAML AuthnRequest.

### 4.1. Ai tin certificate của ai?

| Kết nối | TLS client | TLS server | Certificate nào được kiểm? | Trust store ở đâu? |
| --- | --- | --- | --- | --- |
| Browser → App A `/login/cas` | Browser | App A/ingress | TLS server cert của App A | Browser/OS trust |
| Browser → CAS `/cas/login` | Browser | CAS Server | TLS server cert của CAS | Browser/OS trust |
| **App A → CAS `/cas/serviceValidate`** | **App A JVM** | **CAS Server** | **TLS server cert của CAS** | JVM/app truststore |
| **CAS → App A `pgtUrl` callback** | **CAS HTTP client** | **App A ingress** | **TLS server cert của App A** | CAS HTTP client/JVM/local truststore |
| App A → CAS `/cas/proxy` | App A JVM | CAS Server | TLS cert của CAS | App A JVM truststore |
| App B → CAS `/cas/proxyValidate` | App B JVM | CAS Server | TLS cert của CAS | App B JVM truststore |
| App A → Service B | App A | Service B | TLS cert B | App A truststore |

**Bất đối xứng dễ mắc lỗi:** Thêm root CA của CAS Server vào truststore **App A** không có nghĩa CAS Server đã tin callback của App A. Nếu CAS phải gọi A và gặp `PKIX path building failed`, cần xử lý trust/certificate chain **ở phía CAS** hoặc reverse proxy certificate **của A**. Hai kết nối TLS có người kiểm và truststore khác nhau.

### 4.2. Kiểm tra certificate chain

Giả sử App A được publish ở `https://app.example.org/login/cas/proxyreceptor`, certificate do CA hợp lệ phát. CAS nhận certificate chain từ TLS endpoint. Các lỗi thường gặp:

| Lỗi | Hành vi | Hướng khắc phục |
| --- | --- | --- |
| Certificate **hết hạn** | CAS TLS handshake/PKIX fail | Renew certificate và deploy đúng chain trước cutover |
| Certificate **chưa tới NotBefore** | Cert chưa có hiệu lực | Sửa thời gian/đổi cert đúng mốc, đồng bộ UTC/NTP |
| Thiếu **intermediate CA** | CAS không dựng được đường tin cậy | Cấu hình full chain ở TLS terminator |
| Root CA nội bộ không được CAS trust | `PKIX path building failed` | Import CA/cert tin cậy theo quy trình vào CAS truststore, không bật trust-all |
| SAN không khớp `app.example.org` | Hostname verification fail | Cấp certificate có SAN đúng public callback host |
| Callback dùng IP nhưng cert chỉ có DNS SAN | Hostname mismatch | Dùng FQDN đúng cert thay vì IP thô |
| Certificate của **default virtual host** | SNI/LB route đưa cert của domain khác | Kiểm SNI/ingress virtual host configuration |
| Reverse proxy gửi cert khác giữa các node | Một số callback thành công, một số thất bại | Đồng bộ cert/chain trên mọi node/LB listener |
| TLS protocol/cipher không có điểm chung | Handshake fail | Dùng phiên bản TLS/cipher được hai bên cho phép, không hạ bảo mật tùy tiện |
| Revocation/status policy từ chối | CRL/OCSP hoặc policy khác fail nếu được bật | Xác định chính sách CAS/JVM cụ thể, sửa certificate/chain |
| Certificate self-signed không được cấu hình tin cậy | CAS không thể verify chain theo default | Dùng CA tin cậy hoặc import trust anchor có phê duyệt; không bypass PKIX |

**Lưu ý:** CAS Protocol đòi PKIX và hiệu lực chứng thư; việc check SAN/hostname, EKU, revocation, OCSP/CRL và mức thuật toán còn chịu ảnh hưởng cấu hình HTTPS client/JDK và chính sách deployment. Hãy **thực nghiệm trên CAS Server thật** thay vì chỉ dựa vào thông tin browser “có ổ khóa HTTPS”.

### 4.3. “Certificate hợp lệ với browser” chưa chắc hợp lệ với CAS

Trình duyệt có thể có OS trust store khác JVM trên CAS Server. Container CAS có thể dùng truststore thu gọn hoặc local truststore riêng. Một internal CA được cài ở laptop nhưng **chưa có trên CAS host** sẽ làm callback fail.

Ngược lại, việc người vận hành thêm certificate vào truststore CAS theo cơ chế `trust-all` sẽ tăng rủi ro: CAS không còn đánh giá được đúng identity của callback, cho phép mạng trung gian/attacker endpoint nhận PGT. **Không tắt hostname verification hoặc dùng TrustManager chấp nhận mọi chứng thư** để làm thử nghiệm “thành công”.

### 4.4. HTTPS termination ở reverse proxy

```text
CAS Server -- HTTPS --> Load Balancer/Ingress :443
                                 |
                                 | HTTP nội bộ tới app:8080
                                 v
                         Spring CAS Client
                         proxyReceptorUrl=/login/cas/proxyreceptor
```

CAS chỉ thấy TLS certificate ở **load balancer/ingress**, không phải certificate nội bộ của port 8080, nếu TLS terminate ở đó. Do vậy:

- Cert/SAN/chain trên ingress phải đúng `pgtUrl` external FQDN.
- Ingress phải forward đúng request path và query `pgtId`, `pgtIou` tới app; không thay bằng login redirect hoặc auth portal.
- Có thể dùng HTTP giữa ingress và backend **chỉ khi** topology/policy cho phép và nội mạng được bảo vệ; CAS→ingress vẫn **bắt buộc HTTPS**. Với zero-trust/mạng nhạy cảm, cân nhắc TLS/mTLS tiếp tới backend.
- Không đổi `pgtUrl` thành `http://app-internal:8080/...` vì server-side HTTP nhanh hơn: trái CAS protocol và bỏ bảo vệ PGT.
- Chỉ tin `Forwarded`/`X-Forwarded-*` từ proxy đã kiểm soát; xóa headers do browser/client tự đặt. Không động dựng `pgtUrl` từ raw Host.
- Nếu LB làm WAF, đừng đặt challenge/captcha/login trên callback CAS; CAS HTTP client không có browser session.

## 5. Phân biệt ba URL trong Spring Security CAS Proxy

Giả sử ứng dụng A chạy tại public host `app.example.org`:

| Cấu hình | Giá trị minh họa | Đúng vai trò |
| --- | --- | --- |
| `ServiceProperties.service` | `https://app.example.org/login/cas` | CAS ST được cấp cho URL này |
| `CasAuthenticationFilter.filterProcessesUrl` | `/login/cas` | Filter theo dõi ST callback từ browser |
| `Cas20ProxyTicketValidator.proxyCallbackUrl` | `https://app.example.org/login/cas/proxyreceptor` | CAS Server nhận giá trị này trong `pgtUrl` |
| `CasAuthenticationFilter.proxyReceptorUrl` | `/login/cas/proxyreceptor` | Filter theo dõi CAS GET callback nội bộ |
| CAS Server base | `https://sso.example.org/cas` | Base để `Cas20ProxyTicketValidator` gọi CAS validate/proxy |
| Downstream target service | `https://api.example.org/reports` | CAS PT chỉ được cấp/validate cho service B |

**Ràng buộc 1:** Giá trị `ServiceProperties.service` phải khớp service ID trong `/cas/login` và `/cas/serviceValidate`; nó **không** phải pgtUrl.

**Ràng buộc 2:** Đường dẫn local `proxyReceptorUrl` phải tương ứng với path public của `proxyCallbackUrl` (có tính context path/proxy prefix). Nó không phải URL tuyệt đối; CAS Validator cần **URL tuyệt đối HTTPS**, Filter cần **đường dẫn local**.

**Ràng buộc 3:** `Cas20ProxyTicketValidator` và `CasAuthenticationFilter` phải dùng **cùng một instance hoặc cùng logical distributed storage**. Nếu mỗi nơi dùng một map/Redis namespace khác nhau, callback đã lưu PGT nhưng logic authentication không tìm được nó từ PGTIOU.

### 5.1. Có context path không?

Ví dụ ứng dụng Java Servlet có `server.servlet.context-path=/portal`:

```text
service URL public:
  https://app.example.org/portal/login/cas

pgtUrl tuyệt đối:
  https://app.example.org/portal/login/cas/proxyreceptor

local filterProcessesUrl:
  /login/cas

local proxyReceptorUrl:
  /login/cas/proxyreceptor
```

Path local **thường** bỏ context path servlet; tuy nhiên nếu ingress tự thêm/bỏ prefix hoặc thay servlet path, phải kiểm tra matcher thật ở Spring Security. Không tự đoán rằng `proxyReceptorUrl` phải viết `/portal/login/cas/proxyreceptor` khi servlet đã cấu hình context path `/portal`.

Với Spring Security 7.x, API matching của `CasAuthenticationFilter` có thay đổi về `RequestMatcher`; dùng đúng reference/migration guide của version và viết test callback endpoint. Không bê nguyên cấu hình 6.x qua 7.x khi các matching semantics thay đổi.

### 5.2. Vì sao callback không được redirect?

CAS Protocol cho phép CAS **có thể** đi theo HTTP 3xx khi truy cập `pgtUrl`, nhưng việc cấp PGT thành công đòi CAS nhìn thấy phản hồi HTTP **200** từ endpoint phù hợp. Thiết kế triển khai nên để callback trả 200 **trực tiếp**, không dựa vào 301/302/307 vì:

- Redirect HTTP→HTTPS có thể làm lộ PGT qua HTTP ở hop đầu; `pgtUrl` ban đầu bắt buộc HTTPS.
- Redirect sang trang login có thể dẫn CAS HTTP client tới HTML 200 không xử lý PGT, tạo sai chẩn đoán.
- Redirect khác hostname/path có thể đi vào service registry/hostname validation khác, phá correlation và mở khả năng SSRF.
- Redirect 302 có thể bị load balancer, WAF hoặc policy CAS chặn/giới hạn.
- Browser cookies/SSO session của user **không** được gửi trong callback server-to-server từ CAS.

Vì vậy `GET /login/cas/proxyreceptor?pgtId=...&pgtIou=...` phải được filter nhận và đáp **200 OK** sau khi xử lý đúng. Không trả trang HTML login, không trả 401/403 vì thiếu browser cookie, không trả 404 do thiếu MVC controller và không trả 302 về CAS login.

## 6. Spring Security: những bean nào cần cấu hình?

Tham khảo Spring Security CAS Servlet, có năm nhóm chính:

1. `ServiceProperties`: service callback nhận ST, `sendRenew`/protocol parameters. Giữ `authenticateAllArtifacts=false` nếu A chỉ nhận ST từ browser; không tự bật proxy-ticket authentication cho mọi URL.
2. `CasAuthenticationEntryPoint`: chuyển browser chưa xác thực sang CAS `/login` cùng `service`.
3. `CasAuthenticationFilter`: nhận ST tại `filterProcessesUrl` và PGT callback tại `proxyReceptorUrl`; gọi authentication manager và lưu context cho web session.
4. `CasAuthenticationProvider` với `Cas20ProxyTicketValidator`: xác minh ST (và khi cấu hình riêng có thể xác minh PT) và cấu hình `proxyCallbackUrl` + `ProxyGrantingTicketStorage`.
5. `ProxyGrantingTicketStorage`: lưu `PGTIOU → PGT` cho callback và kết quả validator cùng tra. Chọn implementation production có TTL, distributed state, cleanup, khóa truy cập và lưu secret an toàn.

**Lưu ý:** Có `Cas20ProxyTicketValidator` không có nghĩa app đã bật nhận PT trên mọi API. Nếu app A **chỉ xin PGT để gọi B**, có thể giữ đường nhận ST browser tại `/login/cas`. Nếu A còn cần **nhận incoming PT từ clients khác**, đó là mục đích thứ hai, phải thiết kế `authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource` và stateless cache/proxy-chain allowlist riêng; không trộn để giảm số bean.

### 6.1. Không tự viết controller bắt `pgtId` rồi lưu plaintext

`CasAuthenticationFilter` có sẵn hỗ trợ proxy receptor nếu thiết lập cả `proxyReceptorUrl` và `proxyGrantingTicketStorage`. Một controller `@GetMapping("/proxyreceptor")` tự lấy ``pgtId` rồi ghi database có thể:

- Truy xuất ticket từ nguồn không tin và nhận PGT giả.
- Ghi PGT vào access logs/tracing.
- Lưu PGTIOU không gắn đúng validator/store.
- Bỏ qua cleanup/TTL/concurrency.
- Trả status sai hoặc redirect ngoài ý muốn.

Nếu sản phẩm CAS Client đã có filter, **ưu tiên dùng filter chính thức**. Nếu cần custom receptor, phải giữ tương đương về HTTP semantics, atomic correlation, secret handling, input validation, timeouts và audit; kiểm thử với CAS Server thật.

## 7. Cấu hình Spring Boot 3.x + Spring Security 6.5.x, Java 17+

### 7.1. Dependencies

Trong Spring Boot project có parent/BOM và Java 17, Maven dependencies tối thiểu cho Servlet CAS web:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
```

`spring-security-cas` có dependency Apereo Java CAS Client phù hợp; nếu project tự override version, kiểm `./mvnw dependency:tree` và Javadoc của phiên bản thực. Đây là **đoạn `pom.xml`**, không phải POM độc lập.

CAS Server staging phải sẵn, có registered service cho App A, policy cho phép **proxy authentication**, HTTPS certificate tin cậy và backend target B cũng đăng ký với CAS. Các URL `example.org` dưới đây là placeholders dành cho lab, **không phải service hoạt động ngoài internet**.

### 7.2. `application.yml` — public URLs và local filter paths

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  cas:
    server-base-url: "https://sso.example.org/cas"
    login-url: "https://sso.example.org/cas/login"
    service-url: "https://app.example.org/login/cas"
    proxy-callback-url: "https://app.example.org/login/cas/proxyreceptor"
    proxy-receptor-path: "/login/cas/proxyreceptor"
```

Trong deployment minh họa, ingress/TLS terminator nhận HTTPS public và forward tới Spring backend port 8080. Nếu chạy trực tiếp ở dev, phải thiết lập HTTPS/context path/cert đúng, hoặc dùng staging reverse proxy tương tự production; không thay `proxy-callback-url` thành HTTP.

**Bảo vệ cấu hình:** Những URLs này phải được quản lý qua config/secret management có review. Không cho browser tự tạo `pgtUrl` từ `?callback=...`, `Host` hoặc `X-Forwarded-Host`. Nếu user có khả năng chọn callback URL tùy ý, CAS Server có thể bị ép mở kết nối/SSRF hoặc trao PGT đến host sai.

### 7.3. Cấu hình filter/provider/validator và storage dùng chung

File `src/main/java/com/example/casproxy/CasProxySecurityConfig.java`:

```java
package com.example.casproxy;

import org.apereo.cas.client.proxy.ProxyGrantingTicketStorage;
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasProxySecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String serviceUrl) {

        ServiceProperties props = new ServiceProperties();
        props.setService(serviceUrl);
        props.setSendRenew(false);
        // Không bật authenticateAllArtifacts nếu chỉ nhận ST browser
        // và làm proxy OUTBOUND đến service B.
        props.setAuthenticateAllArtifacts(false);
        return props;
    }

    @Bean
    ProxyGrantingTicketStorage pgtStorage() {
        // LAB ONLY: dữ liệu trong RAM, không HA/replication.
        // Production: storage phân tán có TTL/cleanup/secret controls.
        return new ProxyGrantingTicketStorageImpl();
    }

    @Bean
    Cas20ProxyTicketValidator ticketValidator(
            @Value("${app.cas.server-base-url}") String casBase,
            @Value("${app.cas.proxy-callback-url}") String callback,
            ProxyGrantingTicketStorage storage) {

        Cas20ProxyTicketValidator validator =
            new Cas20ProxyTicketValidator(casBase);
        validator.setProxyCallbackUrl(callback);
        validator.setProxyGrantingTicketStorage(storage);
        return validator;
    }

    // Lab giả định CAS Server có user alice.
    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties props,
            Cas20ProxyTicketValidator validator,
            UserDetailsService users) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(props);
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        provider.setKey("cas-proxy-demo-provider");
        return provider;
    }

    @Bean
    SecurityContextRepository contextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            ServiceProperties props,
            CasAuthenticationProvider provider,
            ProxyGrantingTicketStorage storage,
            SecurityContextRepository repo,
            @Value("${app.cas.login-url}") String loginUrl,
            @Value("${app.cas.proxy-receptor-path}") String receptor)
            throws Exception {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(loginUrl);
        entryPoint.setServiceProperties(props);

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setServiceProperties(props);
        filter.setFilterProcessesUrl("/login/cas");
        filter.setProxyReceptorUrl(receptor);
        filter.setProxyGrantingTicketStorage(storage);
        filter.setAuthenticationManager(new ProviderManager(provider));
        filter.setSecurityContextRepository(repo);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/cas-error",
                    "/signed-out").permitAll()
                // CAS Server phải GET receptor mà KHÔNG có web session.
                .requestMatchers("/login/cas/proxyreceptor")
                    .permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(sec -> sec
                .securityContextRepository(repo))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // Đưa CAS filter vào SecurityFilterChain một lần duy nhất.
        // KHÔNG để @Bean CasAuthenticationFilter tự đăng ký Servlet Filter khác.
        http.addFilterAt(filter, CasAuthenticationFilter.class);
        return http.build();
    }
}
```

**Điểm chính của mã Spring:**

- `setProxyCallbackUrl(callback)` cấu hình **HTTPS absolute URL**, sẽ được validator gửi tới CAS như `pgtUrl`.
- `setProxyReceptorUrl(receptor)` cấu hình **local relative path** mà `CasAuthenticationFilter` bắt.
- **Cùng biến `storage`** được truyền vào cả `Cas20ProxyTicketValidator` và `CasAuthenticationFilter`; nếu khác instance, client không tìm PGT theo PGTIOU.
- `ServiceProperties.service` vẫn là `https://app.example.org/login/cas`. Nó không bị đổi thành URL receptor.
- `setFilterProcessesUrl("/login/cas")` vẫn giữ chỗ nhận ST browser.
- Đặt `permitAll` cho receptor để CAS có thể gọi **không cần login cookie**. CAS filter phải thực sự khớp URL này và trả **200**; `permitAll` một mình **không tạo endpoint**.
- PGT được CAS gửi qua GET query, vì vậy endpoint phải tránh **cache, log, analytics, request tracing chi tiết** và không trả HTML chứa dữ liệu bí mật.
- `new ProxyGrantingTicketStorageImpl()` chỉ phù hợp lab; tài liệu Spring Security cảnh báo **không dùng in-memory storage cho production**, cần cleanup expired tickets.
- `UserDetailsService` demo trả user `alice` với role local, mật khẩu `{noop}unused-by-cas` không dùng làm credential CAS. Đây là fixture kiểm thử, không được dùng như kho người dùng production.
- `http.addFilterAt(...)` thêm filter **trong Spring Security chain**, không đăng ký một `@Bean` Filter độc lập dễ bị Boot auto-register thêm lần thứ hai.
- `setAuthenticateAllArtifacts(false)` là hướng an toàn khi App A **chỉ nhận ST** và cần **xin PT outbound**. Nếu App A **cũng nhận PT inbound**, cần thiết kế auth all artifacts và `ServiceAuthenticationDetailsSource` theo docs, với proxy chain allowlist và stateless ticket cache phù hợp.
- Đoạn này là Spring configuration **trong project đã có dependencies**, không phải chương trình Java 17 độc lập chạy bằng `javac` thuần.

**Giới hạn cần kiểm thử theo version:** API `CasAuthenticationFilter.setProxyReceptorUrl(String)` và `setProxyGrantingTicketStorage(...)` có mặt trong Javadoc Spring Security 6.5.x; khi nâng 7.x, cách chuyển string path sang RequestMatcher được thay đổi. Hãy dùng migration guide/version Javadoc và integration test, không giả định nguồn source này compile nguyên xi với mọi major version.

### 7.4. Spring Boot application và controller tối thiểu

File `src/main/java/com/example/casproxy/CasProxyDemoApplication.java`:

```java
package com.example.casproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasProxyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasProxyDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/casproxy/DemoController.java`:

```java
package com.example.casproxy;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "CAS Proxy lab");
    }

    @GetMapping("/reports")
    public Map<String, String> reports(Authentication authentication) {
        return Map.of(
            "message", "Authenticated with CAS",
            "user", authentication.getName());
    }

    @GetMapping("/cas-error")
    public Map<String, String> casError() {
        return Map.of("status", "CAS authentication failed");
    }

    @GetMapping("/signed-out")
    public Map<String, String> signedOut() {
        return Map.of("status", "Local session ended");
    }
}
```

**Không tạo `@GetMapping("/login/cas/proxyreceptor")`** trong controller này. Endpoint receptor phải được `CasAuthenticationFilter` xử lý bằng built-in proxy receptor logic, không tạo thêm MVC route phản hồi 200 giả mà không lưu PGT. Nếu receptor filter chưa khớp, CAS callback cần **fail** để đội tích hợp sửa đúng đường dẫn, không che bằng fallback controller.

### 7.5. Đọc và dùng PGT ở service A: không tự lấy từ callback

Sau khi ST validation thành công, `CasAuthenticationToken` mang CAS assertion tương ứng. Spring CAS sample thể hiện việc ứng dụng lấy PT thông qua CAS assertion principal của authenticated token:

```java
// Đây là đoạn tích hợp TRONG ứng dụng CAS đã xác thực,
// không phải REST controller độc lập hoặc lớp Java thuần.
CasAuthenticationToken token =
    (CasAuthenticationToken) authentication;

String targetService = "https://api.example.org/reports";
String proxyTicket =
    token.getAssertion().getPrincipal()
        .getProxyTicketFor(targetService);
```

**Chỉ chạy khi** caller thực sự authenticated bằng CAS, assertion/PGT được liên kết đúng, target service B được phép, CAS proxy facility đã hoàn tất PGT issuance và phiên bản CAS client cung cấp API này. Nếu PGT không có, method có thể thất bại/không trả PT theo implementation; ứng dụng phải **từ chối gọi B hoặc trả lỗi kiểm soát**, không fallback sang username HTTP header hay copy ST cũ.

PT mới gắn với `targetService`. Service B phải dùng `/cas/proxyValidate` để kiểm PT và **whitelist proxy chain của A**, chứ không tin chỉ vì chuỗi bắt đầu bằng `PT-`. Nếu B nhận ticket stateless nhiều lần, cần thiết kế đúng single-use validation/cache theo Spring; không mặc nhiên cho replay PT vô hạn.

**Lưu ý về quyền:** Một CAS ST/PT đã verify không cho phép A đọc dữ liệu của mọi user/tenant. B vẫn phải map principal, kiểm scopes/entitlements/record ownership theo chính sách nghiệp vụ.

## 8. Chứng thư: kiểm tra đường TLS từ góc nhìn của CAS Server

Kỹ sư thường debug trên laptop rồi báo `curl OK`, nhưng máy laptop có truststore/DNS/network khác CAS Server. Cần kiểm tra **từ nơi CAS HTTP client thực sự chạy** (container/pod/VM CAS), với quyền phù hợp.

### 8.1. Lệnh kiểm certificate, hostname và chain

**Kiểm trên máy có OpenSSL**:

```bash
openssl s_client \
  -connect app.example.org:443 \
  -servername app.example.org \
  -showcerts \
  -verify_return_error </dev/null
```

Kiểm output `Verify return code: 0 (ok)` theo truststore OpenSSL hiện có; kiểm cert Subject Alternative Name, chain và dates. **Lưu ý:** OpenSSL trust bundle trên máy này có thể khác CAS JVM truststore; kết quả `openssl OK` **không đủ** để chứng minh CAS Java client OK.

**Đọc certificate từ file chính thức của HTTPS terminator**:

```bash
keytool -printcert -file app-tls-server.crt
```

Kiểm `Owner/Issuer`, `Valid from...until`, SHA-256 fingerprint và SAN. `keytool -printcert` chỉ đọc cert, **không tự kiểm CAS truststore có đúng root/intermediate hoặc callback reachable**.

**Kiểm HTTP callback từ phía CAS**:

```bash
curl -i --max-time 10 https://app.example.org/login/cas/proxyreceptor
```

GET không mang `pgtId`/`pgtIou` có thể trả lỗi hợp lệ do thiếu tham số, vì receptor chỉ phục vụ CAS callback thật. **Không dùng curl nhận 200 thiếu hai tham số như điều kiện đủ**; phải kiểm callback thật khi CAS phát PGT. Không tự thêm `-k`/`--insecure` để “chữa” certificate validation, vì lệnh sẽ bỏ đi điều kiện then chốt.

### 8.2. Truststore của CAS JVM

Nếu callback TLS certificate do private enterprise CA phát, đội CAS có thể cần nhập CA certificate/chains được phê duyệt vào truststore CAS. Ví dụ cách tạo **truststore riêng** trong môi trường test:

```bash
keytool -importcert \
  -alias corp-proxy-callback-root \
  -file corp-root-ca.crt \
  -keystore cas-proxy-truststore.p12 \
  -storetype PKCS12
```

Nhập root CA **chỉ sau khi kiểm fingerprint và quyền sở hữu qua kênh độc lập**. Các giá trị alias/file là ví dụ. Lệnh có thể nhắc mật khẩu truststore, không ghi mật khẩu plaintext vào shell history hoặc repository. **Không tự khai báo rằng tạo truststore này làm CAS sử dụng nó**: phải cấu hình CAS HTTP client/JVM trust settings theo đúng phiên bản triển khai, restart/reload nếu cần và test callback.

**Quy tắc tối thiểu:**

- Ưu tiên certificate do CA phù hợp CAS trust chain đã tin; tránh trust anchor không cần thiết.
- Nếu dùng private CA, giới hạn scope và quản trị vòng đời CA/cert có audit.
- Không nhập private key của App A vào CAS Server; CAS chỉ cần **public trust anchors** để verify TLS.
- Không disable chain validation/hostname verification hoặc set `trustAll=true` để tạo PGT.
- Nếu certificate đã hết hạn hoặc SAN sai, **sửa certificate/hostname**, không sửa đồng hồ hay giả mạo DNS.
- Phân biệt truststore **CAS tin A callback** với truststore **A tin CAS validation endpoint**.

### 8.3. Khi certificate bị luân chuyển

Certificate HTTPS callback phải được gia hạn **trước hạn**, bảo đảm CAS trusts chain mới:

```text
T0: CAS tin CA chain cũ; callback dùng cert C_old
T1: CAS đã tin chain/CA cần thiết cho C_new (nếu có CA thay)
T2: Ingress deploy C_new, SNI/SAN đúng
T3: CAS callback HTTPS GET 200, PGTIOU correlation PASS
T4: Loại root/chain trust cũ không còn cần thiết theo policy
```

Đây là **TLS certificate rotation**, không phải rollover IdP SAML signing certificate. Không áp dụng logic “chấp nhận hai SAML signing keys” để bỏ qua HTTPS PKIX.

Nếu root CA trust ở CAS chưa cập nhật mà ingress đã chuyển cert, PGT issuance có thể dừng đột ngột mặc dù browser SSO vào App A vẫn chạy. **Sự khác nhau giữa “ST login OK” và “PGT callback FAIL” là tín hiệu xác định lớp lỗi.**

## 9. Endpoint từ mạng CAS đi tới App A: network, DNS và ingress

CAS HTTP client phải truy cập được `pgtUrl` từ chính pod/VM của CAS:

- DNS của `app.example.org` phải resolve đúng IP/load balancer mà CAS có route đến.
- Firewall, network policy, egress proxy và service mesh phải cho phép CAS → A TCP 443.
- Ingress listener phải trình đúng TLS cert cho SNI `app.example.org`.
- Path `/login/cas/proxyreceptor` phải route đến ứng dụng có `CasAuthenticationFilter` xử lý receptor.
- Query parameters `pgtId` và `pgtIou` phải được giữ nguyên, không strip, mutate, truncate hoặc thay tên.
- WAF không được chặn các prefix/ticket patterns hợp lệ hoặc phát challenge captcha.
- Request từ CAS **không có session cookie browser**, nên không được redirect sang CAS login.
- Response tốt phải có HTTP 200; ưu tiên `Cache-Control: no-store` và không log raw query.
- Timeout/connect/read limits phải phù hợp, không để chờ vô hạn; failure cần fail closed, không tự lấy PGT từ nơi khác.

### 9.1. SameSite/CSRF có liên quan nhưng không phải nguyên nhân chính

Callback CAS→App A là **server-to-server GET**, không phụ thuộc cookie SameSite của browser. CSRF filter mặc định thường bảo vệ các phương thức unsafe như POST/PUT/DELETE; GET callback không nên phải nộp CSRF token của browser. Tuy nhiên:

- Nếu ứng dụng có custom middleware chặn mọi GET không có CSRF hoặc user session, callback sẽ fail.
- Nếu ingress áp form login/OIDC auth trước Spring, CAS Server sẽ nhận 302/401 thay vì 200.
- Nếu WAF chặn query chứa `pgtId`/`pgtIou`, hãy cấu hình exception **narrow** cho endpoint và source CAS theo policy, không disable toàn bộ WAF/CSRF.
- Dù method là GET, việc nó **lưu PGT** là state change do giao thức CAS quy định; điều này đòi hỏi chống cache, kiểm nguồn/correlation và rate-limit thích hợp, không lấy “GET là safe” làm căn cứ bảo mật.

### 9.2. mTLS và IP allowlist: lớp bảo vệ bổ sung, không thay PKIX

CAS Protocol tối thiểu yêu cầu CAS verify TLS **server certificate của callback**. Có thể tăng bảo vệ bằng:

- mTLS giữa CAS Server và App A ingress, nếu CAS HTTP client hỗ trợ cấu hình client certificate.
- Source IP allowlist hoặc private network/mesh authentication gắn với CAS egress đã quản lý.
- Rate limiting và network policies trên receptor.
- Giám sát bất thường: callback thiếu IOU, IOU đã có, storage miss, nguồn gọi khác CAS.

Nhưng **không nên tuyên bố CAS protocol luôn có mTLS mặc định**: xác thực client của callback là chính sách tùy deployment. IP allowlist đơn thuần cũng không phải bằng chứng mạnh nếu IP NAT/sharing thay đổi. Dù có mTLS, vẫn phải so `PGTIOU` trong validation response với giá trị trong storage và kiểm ticket/service/issuer theo CAS protocol.

## 10. PGT storage, thứ tự callback và correlation

Một đặc điểm bất ngờ là CAS callback mang **PGT** đến trước hoặc trong lúc `/serviceValidate` trả kết quả **PGTIOU** cho App A. CAS client cần một storage dùng chung để ghép:

```text
CAS --> GET A /proxyreceptor?pgtId=PGT-123&pgtIou=PGTIOU-abc
        storage.put("PGTIOU-abc", "PGT-123")

CAS --> /serviceValidate response:
        <cas:proxyGrantingTicket>PGTIOU-abc</cas:proxyGrantingTicket>

App A:
        storage.get("PGTIOU-abc") -> "PGT-123"
        sử dụng PGT-123 để gọi CAS /proxy
```

PGTIOU không thể đảo ra PGT theo thuật toán hợp lý; đó là giá trị tương quan tách biệt. **Không bao giờ gán `PGTIOU` thành credential `pgt` khi gọi CAS `/proxy`.**

### 10.1. Một storage dùng chung ở mọi nơi

Spring Security nêu rõ `CasAuthenticationFilter` và `Cas20ProxyTicketValidator` phải tham chiếu **cùng `ProxyGrantingTicketStorage`**. Trong một JVM lab có thể dùng instance in-memory. Nhưng khi chạy 3 pods:

```text
            HTTPS Load Balancer
                   |
           +-------+-------+
           |               |
       Pod A             Pod B
    /serviceValidate     /proxyreceptor?pgtIou=...
           |               |
       Local Map A       Local Map B
        [empty]         [PGTIOU -> PGT]
           |
           +-- PGT lookup MISS!
```

**Production phải giải quyết HA:** một distributed PGT store an toàn (hoặc session routing/callback affinity được thiết kế và kiểm thử, nhưng sticky session đơn thuần có thể không điều khiển được CAS server-side callback). Cache/store nên:

- Có TTL theo PGT validity và policy, cleanup expired entries, capacity cap.
- Mã hóa/giới hạn truy cập storage; PGT là bearer credential nhạy cảm.
- Dùng namespace theo CAS Server/issuer và application/tenant để tránh collision/cross-tenant.
- Chống race conditions/callback duplicate, không ghi đè IOU đang dùng trái phép.
- Có thao tác atomic correlate/consume hoặc bounded retrieval theo semantics thư viện.
- Xử lý callback đến trước/sau response, retry/backoff ở service layer nếu theo API có độ trễ, không tự bịa PGT.
- Chịu được rolling deploy, node restart và cache eviction đúng policy.
- Revoke/clear ticket state khi user/logout/incident theo CAS protocol và mức rủi ro, không giữ PGT vô hạn.
- Có audit thông qua request ID, storage hit/miss counters, **không log PGT/ST/PT/raw IOU**.

**Cảnh báo version:** Implementations `ProxyGrantingTicketStorageImpl` có thể là map in-memory. Tài liệu Spring Security ghi rõ production không nên dùng implementation memory cho cluster và cần `cleanup()` để dọn PGT hết hạn. Chọn distributed implementation theo phiên bản Apereo CAS Client đang chạy, không tự trỏ bean cùng một type nhưng mỗi pod tự khởi tạo map riêng.

### 10.2. Callback không phải “proof of user login”

CAS callback chỉ chứng minh một bước giao PGT giữa CAS và App A; **không thay** việc ứng dụng A xác minh ST đúng service và gắn principal/session. Bản thân request có query `pgtId`/`pgtIou` không nên tạo local Authentication của một user hoặc gán role từ chuỗi PGT.

Kết quả cuối cùng cần đủ:

1. ST/PT đã được CAS validate hợp lệ cho service đúng.
2. CAS callback HTTPS/PKIX thành công và nhận được PGTIOU.
3. PGTIOU có đúng PGT trong storage của application/service context.
4. App A được CAS service registry cho phép proxy.
5. App B chấp nhận chain và PT riêng cho target service.
6. Authorization của B kiểm quyền trên resource/tenant mà user yêu cầu.

## 11. Java 17 độc lập: mô hình ghép PGTIOU và bảo vệ target service

Ví dụ này **chỉ mô phỏng correlation và policy**, không gọi CAS, không parse XML, không tạo TLS hoặc PGT thật. Nó giúp người học thấy **IOU không phải PGT**, vì sao callback HTTPS/target allowlist quan trọng và vì sao một IOU giả/đã tiêu thụ phải bị từ chối.

File `PgtCallbackPolicyDemo.java`:

```java
import java.net.URI;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class PgtCallbackPolicyDemo {

    static final String EXPECTED_CALLBACK =
        "https://app.example.org/login/cas/proxyreceptor";

    static final Set<String> ALLOWED_TARGETS = Set.of(
        "https://api.example.org/reports");

    private final Map<String, String> tickets = new HashMap<>();

    static boolean approvedCallback(String url) {
        try {
            URI uri = URI.create(url);
            return "https".equals(uri.getScheme())
                && EXPECTED_CALLBACK.equals(uri.toString())
                && uri.getUserInfo() == null
                && uri.getFragment() == null;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    // Mô phỏng CAS callback được giao qua kết nối đã xác minh.
    // KHÔNG dùng method này như HTTP endpoint thật.
    void storeFromVerifiedCallback(
            String pgtIou, String pgt, boolean trustedTransport) {
        if (!trustedTransport || pgtIou == null || pgt == null
                || !pgtIou.startsWith("PGTIOU-")
                || !pgt.startsWith("PGT-")
                || pgtIou.isBlank() || pgt.isBlank()) {
            return;
        }
        tickets.putIfAbsent(pgtIou, pgt);
    }

    String takePgt(String validatedIou, String targetService) {
        if (validatedIou == null
                || !ALLOWED_TARGETS.contains(targetService)) {
            return "DENIED";
        }
        String pgt = tickets.remove(validatedIou);
        return pgt == null ? "MISSING" : "READY";
    }

    public static void main(String[] args) {
        PgtCallbackPolicyDemo demo = new PgtCallbackPolicyDemo();

        System.out.println("httpsCallback=" +
            approvedCallback(EXPECTED_CALLBACK));
        System.out.println("httpCallback=" +
            approvedCallback(
                "http://app.example.org/login/cas/proxyreceptor"));
        System.out.println("wrongHost=" +
            approvedCallback(
                "https://evil.example.org/login/cas/proxyreceptor"));

        demo.storeFromVerifiedCallback(
            "PGTIOU-one", "PGT-one", true);

        System.out.println("allowedLookup=" +
            demo.takePgt(
                "PGTIOU-one", "https://api.example.org/reports"));
        System.out.println("replayedIou=" +
            demo.takePgt(
                "PGTIOU-one", "https://api.example.org/reports"));

        demo.storeFromVerifiedCallback(
            "PGTIOU-two", "PGT-two", true);
        System.out.println("wrongTarget=" +
            demo.takePgt(
                "PGTIOU-two", "https://evil.example.org/data"));
        System.out.println("correctTargetAfterDenied=" +
            demo.takePgt(
                "PGTIOU-two", "https://api.example.org/reports"));

        demo.storeFromVerifiedCallback(
            "PGTIOU-three", "PGT-three", false);
        System.out.println("untrustedCallback=" +
            demo.takePgt(
                "PGTIOU-three", "https://api.example.org/reports"));
    }
}
```

Biên dịch/chạy JDK 17+:

```bash
javac --release 17 PgtCallbackPolicyDemo.java
java PgtCallbackPolicyDemo
```

Stdout cố định:

```text
httpsCallback=true
httpCallback=false
wrongHost=false
allowedLookup=READY
replayedIou=MISSING
wrongTarget=DENIED
correctTargetAfterDenied=READY
untrustedCallback=MISSING
```

**Giải thích từng phép thử:**

- `httpsCallback=true`: URL expected có scheme HTTPS và khớp exact approved callback.
- `httpCallback=false`: HTTP không được dùng làm `pgtUrl`.
- `wrongHost=false`: một host có path giống nhau không được tự coi là callback đã phê duyệt.
- `allowedLookup=READY`: PGTIOU đã được giao qua **giả định callback tin cậy**, có PGT lưu trong map và target service nằm trong allowlist.
- `replayedIou=MISSING`: demo tiêu thụ mapping một lần để minh họa correlation; trong CAS Client thật, PGT có thể dùng để xin **nhiều PT**, nên không suy `PGT single use`.
- `wrongTarget=DENIED`: PGT không có nghĩa được gọi bất kỳ target service nào.
- `correctTargetAfterDenied=READY`: request sai target không ăn mất mapping trong demo.
- `untrustedCallback=MISSING`: dữ liệu từ nguồn không được xác minh không được đưa vào storage.

**Giới hạn rõ ràng:** `approvedCallback` chỉ kiểm string/URI theo allowlist, **không thực hiện TLS/PKIX**, không kiểm issuer hay certificate. `trustedTransport` là biến **giả lập**, không được lấy từ header do client tự khai. `storeFromVerifiedCallback` không có distributed TTL/expiry/cleanup/race protection; không dùng nó làm implementation production. Trong thực tế Spring CAS filter/validator đảm nhiệm ticket protocol, CAS Server kiểm HTTPS PKIX; chính sách target/proxy-chain nằm ở server/client theo hợp đồng.

## 12. PT cho Service B: callback thành công chưa phải kết thúc

Sau khi App A có PGT, nó gọi:

```http
GET /cas/proxy?pgt=PGT-EXAMPLE&targetService=https%3A%2F%2Fapi.example.org%2Freports HTTP/1.1
Host: sso.example.org
```

CAS trả một PT nếu PGT hợp lệ và service B được cho phép. A chuyển PT tới B theo protocol; B phải kiểm:

- `PT` chưa dùng, chưa hết hạn và do đúng CAS Server cấp.
- `service` lúc validate PT **khớp targetService lúc phát PT**.
- Proxy chain trong response liệt kê các proxy đã tham gia; B chỉ chấp nhận chain đã phê duyệt.
- User principal/attributes được CAS verify; B map vào local account và tenant/permission.
- TLS giữa A và B đáng tin; không log PT/PGT.
- Không tự chấp nhận `PT` chỉ vì App A tự khai `X-User: alice` hoặc vì callback A đã trả 200.

### 12.1. Allowed proxy chains, không dùng `acceptAnyProxy` tùy tiện

CAS `/proxyValidate` có thể trả `<cas:proxies>`. Đội vận hành B phải giới hạn **những proxying services** được đại diện user:

```text
Allowed proxy:
  https://app.example.org/login/cas/proxyreceptor

Not allowed:
  https://attacker.example.org/callback
  https://other-tenant.example.org/callback
  * (mọi proxy)
```

Spring CAS sample có minh họa `Cas20ProxyTicketValidator` với `acceptAnyProxy=true` để demo, nhưng điều này **không phải cấu hình khuyến nghị cho production**. Hãy cấu hình allowed proxy chains chính xác theo CAS client version và kiểm test thứ tự proxy chain khi có nhiều hop. Với protocol CAS 2/3, danh sách proxy được trả theo thứ tự gần nhất trước; khi viết matcher hãy đọc đúng semantics của CAS client đang dùng.

### 12.2. Vì sao PGT không nên sống mãi trong storage?

CAS protocol định nghĩa PGT có thể dùng để phát **nhiều PT**, nhưng phải hết hạn/được thu hồi theo chính sách, đặc biệt khi CAS SSO session của user kết thúc. Ứng dụng cũng cần local logout/session revocation và storage cleanup phù hợp. Đừng dùng PGT như một secret vĩnh viễn, và đừng đưa PGT trong job queue/URL/log có retention dài.

**Trường hợp người dùng logout local A:** Điều đó không mặc nhiên logout TGT/TGC CAS hoặc tất cả PGT/PT. Nếu use case bảo mật cao, thiết kế revocation đối với proxy credentials và các access sessions theo CAS Server/ứng dụng, không suy từ `HttpSession.invalidate()` là PGT đã bị thu hồi ở CAS.

## 13. Điều kiện xuất bản endpoint proxy callback an toàn

Vì CAS Server phải gọi đến App A, callback phải **reachable**; nhưng “reachable” không có nghĩa “mở trống toàn internet không kiểm soát”.

Thiết kế production nên có:

1. **HTTPS public/riêng được CAS truy cập** với FQDN cố định và certificate chain tin cậy.
2. **Canonical URL** được cấu hình server-side, không dựa vào Host/Forwarded headers không tin cậy.
3. **CAS service registry** cho phép App A thực hiện proxy authentication và cho phép `pgtUrl` theo policy.
4. **GET callback** có hai query parameters `pgtId`/`pgtIou`, được filter chính thức xử lý, trả 200.
5. **Không đòi browser authentication**/form login trên receptor; có thể thêm xác thực network mTLS hoặc IP policy nếu hệ thống hỗ trợ.
6. **Không có open redirect/302** ở receptor; không render PGT vào response.
7. **Không log** raw query, ticket, IOU hay response body chứa bí mật; dùng `Cache-Control: no-store`/Referrer-Policy khi phù hợp.
8. **Quy trình xử lý PGT secret** trong storage: encrypted at rest/in transit, TTL, cleanup, namespace, replication, access control.
9. **Hạn chế request size và tần suất** để tránh DoS hoặc storage poisoning.
10. **Chống correlation giả mạo**: không coi GET có `pgtId` là bằng chứng user đã xác thực; phải gắn với pending ST/PT validation và CAS response PGTIOU.
11. **Egress/ingress allowlist**; chỉ CAS Server có thẩm quyền được truy cập khi khả thi và đã test HA.
12. **Monitoring** TLS expiry, 200 callback rate, PGT issuance rate, storage misses và proxy ticket failures.
13. **Tenant isolation:** không dùng chung namespace PGT theo tenant/issuer nếu multi-tenant có trust boundaries độc lập.
14. **Change approval** cho callback URL, cert, DNS, load balancer, proxy policies và CAS server truststore.
15. **Integration tests** thực sự gọi từ CAS Server, không chỉ curl trên laptop.

**Không nên dùng `robots.txt` hoặc ẩn đường dẫn làm biện pháp bảo mật**. Đây là endpoint giao thức server-to-server, phải dùng xác minh chứng cứ và các kiểm soát mạng đúng bản chất.

## 14. Ma trận kiểm thử bắt buộc cho HTTPS/PGT callback

Mỗi ca cần **Service Ticket hợp lệ mới từ CAS test**, tránh reuse ST đã bị tiêu thụ làm sai lệch kết quả. Khi có test TLS lỗi, dùng môi trường staging riêng và certificate test, **không sửa truststore production** để kích hoạt lỗi.

| Ca thử | Tình huống | Kết quả đúng |
| --- | --- | --- |
| **Happy path** | App A validate ST với `pgtUrl` HTTPS hợp lệ, CAS GET receptor 200, store nhận PGT | CAS trả PGTIOU, client lấy đúng PGT và có thể xin PT cho B |
| **Không gửi `pgtUrl`** | App A chỉ validate ST thông thường | Không có PGTIOU/PGT; login ST có thể vẫn thành công nếu CAS policy cho phép |
| **`pgtUrl` HTTP** | `http://app.example.org/...` | CAS từ chối proxy callback, không cấp PGT |
| **Certificate expired** | TLS server cert App A quá hạn | PKIX/handshake fail, không cấp PGT |
| **Certificate not yet valid** | NotBefore tương lai | PKIX/handshake fail |
| **Self-signed cert không được tin** | CAS truststore không có trust anchor | Từ chối |
| **Missing intermediate** | Ingress không gửi đủ chain | PKIX path building fail hoặc bị từ chối |
| **SAN hostname mismatch** | URL app.example.org nhưng certificate cho other.example.org | Hostname validation fail |
| **Wrong SNI cert** | LB trả default cert của host khác | TLS fail theo hostname |
| **CAS custom CA chưa import** | Browser local trust nhưng CAS JVM không trust | CAS callback fail |
| **WAF chặn GET** | Query `pgtId/pgtIou` bị block | CAS không nhận 200, PGT issuance fail |
| **302 tới login page** | Receptor bị browser auth gateway bảo vệ | CAS không nhận receptor 200 hợp lệ; fail hoặc redirect không hợp lệ |
| **404 sai path** | `proxyCallbackUrl` khác `proxyReceptorUrl`/context | Không lưu PGT, không cấp PGT |
| **401/403 không có cookie** | Security filter yêu cầu local user session | CAS callback fail; receptor cần route giao thức độc lập |
| **Timeout** | CAS không kết nối được đến A | Không cấp PGT, alert CAS→A network |
| **Trả 200 giả không lưu PGT** | MVC fallback controller thay filter | CAS có thể phát PGTIOU nhưng app storage miss; không xin PT được |
| **Hai PGT stores khác nhau** | Validator và Filter dùng hai instances không share | Correlation PGTIOU miss |
| **Cluster node A/B** | Callback vào pod B; ST validation xử lý ở pod A | Phải tìm được PGT trong distributed store hoặc routing đã thiết kế |
| **Callback duplicate** | CAS retry/duplicate query | Không nhân nhiều record hoặc đổi mapping sai |
| **PGTIOU lạ** | Client nhận IOU không tồn tại trong store | Không gọi `/proxy` bằng IOU, fail closed |
| **PGT leaked** | Query raw bị ghi ở ingress access log | Test chính sách redaction/no-store, kích hoạt incident nếu thật |
| **Target B ngoài allowlist** | Xin PT cho service lạ | Từ chối theo CAS service policy/app allowlist |
| **PT đưa sang target C** | PT phát cho B, C đem validate | CAS từ chối do target service mismatch |
| **Proxy chain không được phép** | B nhận PT từ proxy A lạ | B từ chối dù CAS PT cryptographic/protocol check thành công |
| **TGT bị logout** | User logout CAS làm PGT hết hiệu lực theo protocol | PGT không thể xin PT mới sau revocation |
| **Local logout A** | Chỉ HttpSession A invalidated | Không tự suy PGT/TGT đã bị CAS revoke; xử lý theo policy |
| **CA rotation** | Đổi cert/CA App A trước khi CAS cập nhật trust | Fail có kiểm soát; sau đúng trust chain thì hồi phục |
| **IdP SAML cert đổi** | Chỉ đổi certificate ký SAML ở hệ thống khác | Không tự ảnh hưởng PKIX TLS callback CAS nếu TLS cert A không đổi |

Một test PASS chỉ khi **PGTIOU trong CAS validation response khớp PGT đã lưu**, không phải chỉ khi browser cuối cùng thấy trang App A 200. Login ST bình thường có thể thành công ngay cả khi việc cấp PGT thất bại ở một cấu hình/phiên bản cụ thể; vì vậy phải có assertion riêng “PGT received, PT issued and B accepted”.

### 14.1. Cách thu bằng chứng mà không lộ ticket

Trong log/staging test chỉ lưu:

```text
eventId
utcTimestamp
casServerId
registeredServiceId
callbackHostAndPath  (không raw query)
tlsValidationResult
tlsPeerCertificateFingerprintSHA256
callbackHttpStatus
pgtIssuanceStatus
storageCorrelationStatus
targetServiceId
proxyChainPolicyDecision
podOrRegion
testCaseId
```

Không log:

```text
?ticket=ST-...
?pgtId=PGT-...&pgtIou=PGTIOU-...
/cas/proxy?pgt=PGT-...
PT-...
Session cookie/JSESSIONID
CAS TGT/TGC
Java truststore password hoặc TLS private key
```

Nếu cần tương quan các sự kiện giữa CAS/app, dùng request/trace ID đã qua kiểm soát hoặc hash HMAC/ticket pseudonym được xử lý theo policy, không lưu token raw. Việc PGT đi qua URL query GET **không** có nghĩa query được phép đẩy vào hệ thống analytics.

## 15. Chẩn đoán lỗi theo thứ tự bằng chứng

### 15.1. ST login đã thành công nhưng không có PGT

```text
1. App A có thực sự dùng Cas20ProxyTicketValidator?
       |
       +-- Không --> chỉ ST login; cấu hình proxy validator đúng.

2. Validator có set proxyCallbackUrl (pgtUrl) HTTPS đúng?
       |
       +-- Không --> sửa URL canonical, không lấy từ user header.

3. CAS Server đã cho phép service A proxy, callback URL được duyệt?
       |
       +-- Không --> cập nhật service registry có phê duyệt.

4. CAS có resolve DNS và mở kết nối TCP 443 đến callback?
       |
       +-- Không --> network/DNS/egress/ingress.

5. TLS handshake CAS -> A có qua PKIX/cert/SAN/time không?
       |
       +-- Không --> sửa chain, CA trust, hostname, expiry.

6. GET /proxyreceptor?pgtId&pgtIou có tới Spring không?
       |
       +-- Không --> LB, WAF, path rewrite, timeout.

7. CAS có thấy HTTP 200 trực tiếp từ receptor filter không?
       |
       +-- Không --> 302 login, 401/403, 404, wrong matcher.

8. Validator và receptor dùng đúng shared PGT store không?
       |
       +-- Không --> bean/HA/namespace/TTL.

9. CAS validation response có PGTIOU? Store có PGT tương ứng?
       |
       +-- Không --> inspect CAS proxy issuance/IOU correlation.

10. App A gọi /proxy lấy PT rồi B chấp nhận không?
       |
       +-- Không --> PGT validity, targetService, proxy chain, authz.
```

### 15.2. Bảng lỗi thường gặp

| Lỗi vận hành | Dấu hiệu | Khắc phục |
| --- | --- | --- |
| `INVALID_PROXY_CALLBACK` | CAS báo pgtUrl/certificate/endpoint không đạt | Kiểm HTTPS, PKIX, callback URL, reachability và status |
| `UNAUTHORIZED_SERVICE_PROXY` | Service không được phép proxy | Chỉnh CAS service registry có approval; không thay tên URL để bypass |
| `INVALID_SERVICE` | ST/PT service không khớp | So `ServiceProperties.service` và targetService/validator |
| `INVALID_TICKET` | ST/PT giả, hết hạn, đã dùng | Phát ticket mới, kiểm lại service; không retry cùng ticket |
| `SSLHandshakeException` | TLS cert/trust/cipher lỗi | Kiểm CA, chain, hostname, protocol từ CAS runtime |
| `SunCertPathBuilderException` | CAS không dựng được PKIX chain | Bổ sung đúng intermediate/CA trust, không trust-all |
| Callback 302 CAS login | Filter chain/gateway đòi local session | Cho phép server-to-server receptor theo policy, filter xử lý 200 |
| Callback 401/403 | Auth policy WAF/SecurityFilterChain chặn | Rà soát matcher và ingress ACL; không disable global security |
| Callback 404 | Path/context prefix/route sai | So proxyCallbackUrl absolute và proxyReceptorUrl local |
| HTTP 200 nhưng không có PGT | MVC placeholder controller trả 200, filter không lưu | Bỏ controller giả, cấu hình CasAuthenticationFilter/storage |
| Có PGTIOU, không tìm PGT | Stores khác instance, pod khác, TTL ngắn, race | Shared distributed store và cleanup/replication phù hợp |
| PGT có nhưng xin PT thất bại | PGT expired/revoked, CAS target policy | Kiểm /proxy response, authorized target service |
| PT B từ chối | PT scope/target/chain không được phép | /proxyValidate đúng service, proxy allowlist và authz |
| Lỗi sau cert deploy | Ingress cert/SNI/chain không đồng nhất | Kiểm mọi backend LB từ CAS Server |
| Lỗi chỉ khi từ CAS pod | CAS DNS/egress/truststore khác laptop | Test từ CAS runtime/namespace |
| Rò PGT trong access log | Reverse proxy log raw query | Redact ngay, revoke nếu incident; cập nhật log pipeline |
| Callback bị client tự GET với PGT giả | Endpoint reachable public | Dựa trên CAS validation+IOU, thêm network/mTLS controls khi khả thi |
| Rollback làm proxy lỗi | Config mismatch giữa callback URLs/versions | Triển khai đồng bộ và regression test PGT end-to-end |

**Đừng thử sửa lỗi bằng các cách nguy hiểm:** bật HTTP pgtUrl, vô hiệu hóa certificate verification, cho mọi proxy chain, lưu PGT trên browser, trả 200 giả, dùng ST cho B, hoặc hạ policy target service. Tất cả đều bỏ qua mục tiêu bảo mật của CAS Proxy.

## 16. Câu hỏi ôn tập và đáp án

**Câu 1.** App A nhận ST tại `https://app.example.org/login/cas`. Để CAS cấp PGT qua receptor, nên cấu hình `ServiceProperties.service` và `proxyCallbackUrl` thế nào?

**Đáp án:** `ServiceProperties.service=https://app.example.org/login/cas`; `proxyCallbackUrl=https://app.example.org/login/cas/proxyreceptor`. Hai URL khác chức năng; local `proxyReceptorUrl=/login/cas/proxyreceptor`.

**Câu 2.** CAS gọi `pgtUrl` qua HTTPS nhưng certificate App A do CA nội bộ chưa có trong CAS truststore. Browser login vào A vẫn thành công. PGT được cấp không?

**Đáp án:** Theo yêu cầu PKIX của CAS Proxy, CAS không thể thiết lập tin cậy với callback nên phải **không cấp PGT**; test CAS client/Server có thể cho kết quả ST login riêng tùy implementation. Cần cấu hình truststore **phía CAS** sau khi xác minh CA/cert theo chính sách.

**Câu 3.** CAS gửi `GET /proxyreceptor?pgtId=...&pgtIou=...`, server trả 302 về `/login` vì không có cookie. Có thể coi callback thành công không?

**Đáp án:** Không. CAS Server là HTTP client không có browser session; endpoint protocol phải được filter xử lý và phản hồi 200. Sửa filter chain/gateway, không bỏ TLS validation.

**Câu 4.** App A thấy `<cas:proxyGrantingTicket>PGTIOU-xyz</...>`. Có thể dùng chuỗi PGTIOU-xyz làm tham số `pgt` của CAS `/proxy` không?

**Đáp án:** Không. Phải tra `ProxyGrantingTicketStorage` theo IOU để lấy **PGT thực** đã được CAS giao qua callback.

**Câu 5.** Trong cluster, CAS callback tới pod B nhưng App A đang chờ `/serviceValidate` ở pod A. Mỗi pod dùng `ProxyGrantingTicketStorageImpl` in-memory riêng. Kết quả?

**Đáp án:** Pod A có thể không tìm được IOU/PGT dù CAS callback tới B trả 200. Production nên dùng shared/distributed ticket storage, tenant namespace/TTL đúng và test cross-node.

**Câu 6.** Chứng thư nào CAS Server kiểm khi gọi callback PGT: signing certificate của SAML IdP, certificate của CAS Server hay TLS certificate của App A?

**Đáp án:** **TLS server certificate của App A** do ingress/callback endpoint trình ra, được CAS TLS client kiểm chain/PKIX/hostname/validity. App A lại kiểm TLS certificate CAS Server trên kết nối `/serviceValidate` — đó là chiều ngược lại.

**Câu 7.** App A có PGT và muốn đọc API B. Có thể tự gửi `X-User: alice` thay PT không?

**Đáp án:** Không. A dùng PGT xin PT cho đúng `targetService=B` từ CAS; B kiểm PT bằng `/proxyValidate`, proxy chain và quyền nghiệp vụ.

**Câu 8.** CAS có thể theo HTTP 302 khi callback, vậy có nên để receptor chỉ trả 302 sang login rồi sau đó có trang 200?

**Đáp án:** Không. 200 ở trang login không chứng minh PGT đã được lưu. Hãy để receptor trả 200 trực tiếp khi xử lý đúng `pgtId/pgtIou`; không phụ thuộc browser session/redirect.

**Câu 9.** Một người có thể mở endpoint callback từ internet và tự gửi `pgtId`/`pgtIou`. Có nên coi đó là CAS user authenticated không?

**Đáp án:** Không. Callback là bước giao PGT; chỉ có ý nghĩa khi CAS Server đã xác minh ST/PT, kết quả validation chứa đúng IOU và app có ticket mapping, cùng network/trust controls thích hợp. Không tạo user session từ raw callback query.

**Câu 10.** Có nên bật `ServiceProperties.authenticateAllArtifacts=true` để chữa việc CAS callback trả 404?

**Đáp án:** Không. `authenticateAllArtifacts` phục vụ luồng nhận Proxy Ticket ở nhiều URL/stateless clients; callback 404 cần sửa `proxyReceptorUrl`/filter match/ingress và PGT storage. Bật rộng có thể tăng bề mặt tấn công.

## 17. Checklist triển khai trước khi bàn giao production

- [ ] Use case CAS proxy được phê duyệt; App A thật sự cần xin PT để gọi Service B.
- [ ] Phân biệt rõ ST/PGT/PGTIOU/PT/TGT và session; không lưu hoặc gửi PGT vào browser.
- [ ] `ServiceProperties.service` = callback ST public, còn `proxyCallbackUrl` = **HTTPS absolute URL** proxy receptor.
- [ ] `CasAuthenticationFilter.proxyReceptorUrl` = local matcher của proxy receptor, tách khỏi `filterProcessesUrl` nhận ST.
- [ ] CAS `/serviceValidate` nhận đúng `ticket`, `service` và `pgtUrl`; callback CAS GET có `pgtId`/`pgtIou`.
- [ ] CAS Server yêu cầu HTTPS và verify PKIX/trust/hostname/expiry certificate của callback; TLS root/intermediate chain đầy đủ.
- [ ] Truststore **CAS→App A** khác với truststore **App A→CAS**; đã kiểm hai chiều từ đúng runtime.
- [ ] CAS service registry cho phép App A proxy; pgtUrl/target B được phê duyệt, không có allow-all.
- [ ] Callback nhận từ CAS không cần browser cookie, không redirect login, không CAPTCHA; trả 200 sau xử lý.
- [ ] Không có MVC fallback trả 200 giả thay CAS filter; không đăng ký filter hai lần.
- [ ] `Cas20ProxyTicketValidator` và `CasAuthenticationFilter` dùng chung `ProxyGrantingTicketStorage` logic, có TTL/cleanup và quyền truy cập.
- [ ] Multi-pod/region dùng shared/distributed PGT storage phù hợp; không dựa vào in-memory demo.
- [ ] IOU↔PGT correlation chính xác và bị giới hạn theo CAS source/tenant, chống duplicate/poisoning.
- [ ] Callback HTTPS certificate có SAN đúng FQDN, valid dates, accepted algorithms và CA chain trong CAS trust; không tắt verification.
- [ ] DNS/firewall/ingress/WAF/forwarded headers và path rewrite đã kiểm thử từ CAS Server runtime.
- [ ] TLS certificate rotation trên ingress có runbook cập nhật CAS trust/PGT integration test.
- [ ] App A xin PT cho đúng targetService; B dùng CAS `/proxyValidate` và strict allowed proxy chains.
- [ ] Không dùng `acceptAnyProxy=true` production trừ policy ngoại lệ đã đánh giá và giám sát.
- [ ] Không log query chứa PGT/PT/ST/IOU, cookie, private keys hoặc truststore password; request/callback response có no-store phù hợp.
- [ ] Có alert cho HTTP status callback khác 200, PKIX failures, PGTIOU storage miss, CAS `INVALID_PROXY_CALLBACK`/`UNAUTHORIZED_SERVICE_PROXY`, PT failures.
- [ ] Đã thử ma trận lỗi TLS, cert expiry/SAN/intermediate, 302 login, 404, storage khác node và proxy chain lạ.
- [ ] Local logout/CAS logout/deprovision có chính sách thu hồi credential/session rõ, không suy một bước tự thu hồi tất cả.
- [ ] Toàn bộ endpoint/proxy URLs do backend config tin cậy tạo, không nhận host hoặc pgtUrl tùy ý từ client.
- [ ] Version thực của Spring Security/Apereo CAS Client được khóa và integration test sau mỗi lần nâng cấp.

**Kết luận:** Endpoint proxy callback là **kênh server-to-server mà CAS giao PGT cho ứng dụng**, không phải callback login browser. Khi App A gửi `pgtUrl` trong lúc validate ST, CAS **phải** thiết lập HTTPS với kiểm tra PKIX/chứng thư của callback, GET đến receptor với `pgtId` và `pgtIou`, nhận HTTP 200 và trả **PGTIOU** trong kết quả ticket validation. Spring Security kết nối hai chặng bằng **`Cas20ProxyTicketValidator.proxyCallbackUrl` + `CasAuthenticationFilter.proxyReceptorUrl` + cùng `ProxyGrantingTicketStorage`**. Chỉ sau khi correlation thành công App A mới có PGT để xin PT cho Service B, và B vẫn phải tự xác minh PT, proxy chain và quyền dữ liệu. Bỏ qua HTTPS/PKIX, lưu PGT sai node hoặc nhầm callback URL đều có thể làm proxy thất bại hoặc tạo lỗ hổng nghiêm trọng.

## 18. Tài liệu tham khảo

1. [CAS Protocol 3.0 Specification – `/serviceValidate`, `pgtUrl` và `2.5.4 Proxy Callback](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): quy tắc HTTPS MUST, PKIX/trust chain, GET `pgtId/pgtIou`, 200 OK, PGTIOU correlation, PGT/PT lifecycle.
2. [Spring Security – CAS Authentication, Proxy Ticket Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `Cas20ProxyTicketValidator`, `proxyCallbackUrl`, `ProxyGrantingTicketStorage`, `proxyReceptorUrl`, proxy chain và stateless ticket cache.
3. [Spring Security 6.5 Javadoc – CasAuthenticationFilter](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): default ST callback `/login/cas`, proxy receptor và storage API.
4. [Spring Security 6.5 Javadoc – CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): provider/validator và local user details.
5. [Apereo CAS – Proxy Authentication](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html): PGT/PT flow, callback authorization trong CAS service registry, CAS HTTP client truststore và SSL.
6. [Apereo Java CAS Client README – Proxy Callback and Distributed Storage](https://github.com/apereo/java-cas-client/blob/master/README.md): `proxyReceptorUrl`, `proxyCallbackUrl`, `allowedProxyChains`, clustered PGT storage.
7. [Spring Security – Migration: CAS Proxy Receptor Matching](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/migration-7/web.html): khác biệt `RequestMatcher` khi chuyển từ Spring Security 6 sang 7.
8. [Oracle Java 17 – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS trust managers, X.509 certificate validation và truststore.
9. [Oracle Java 17 – keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): xem và import public certificate/CA trust anchors.
10. [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS configuration, hostname/certificate validation và bảo vệ kênh.
11. [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): hạn chế URL/service callback ngoài danh sách tin cậy.
12. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): quản lý credentials trong URL/query, cookie, cache/log và session.
