# Rà soát nguy cơ giả mạo danh tính khi có nhiều lớp reverse proxy

**Module:** Spring Security – federation  
**Chủ đề cha:** Xác thực qua proxy  
**Phạm vi:** ứng dụng Spring Boot 3.x/Spring Security 6.x sau CDN, WAF, ingress, authentication gateway, service mesh và reverse proxy nội bộ; Java 17+. Tập trung vào **giả mạo identity** và **trust boundary nhiều hop**, không đồng nhất với tối ưu cấu hình proxy hoặc bảo mật mạng tổng quát.

## 1. Vấn đề trung tâm

Trong nhiều hệ thống, ứng dụng Spring không tự xác thực người dùng bằng mật khẩu/OIDC/SAML tại mọi request. Một **authentication proxy** đã xác thực user rồi chuyển identity vào một HTTP header, ví dụ **X-Verified-Subject: employee-42**. Ứng dụng có thể dùng **RequestHeaderAuthenticationFilter** để tạo Spring Security Authentication từ header đó.

Cơ chế này an toàn **chỉ khi header thật sự do một thành phần được tin cậy tạo ra, sau khi xác thực đúng user**, và kẻ tấn công **không có bất kỳ đường nào** gửi giá trị tùy ý đến Spring hoặc làm một hop trung gian tin một header chưa được chứng thực.

Ví dụ kiến trúc:

~~~text
Internet browser / attacker
       |
       v
P0: CDN / WAF / public edge
       |
       v
P1: Login / OIDC / SAML / mTLS authentication gateway
       |
       v
P2: Kubernetes ingress / internal reverse proxy
       |
       v
Spring Boot application
       |
       v
Business authorization + database
~~~

Trong kiến trúc này, một request có thể chứa hàng chục headers, nhưng các nhóm quan trọng phải phân biệt:

1. **Routing/origin headers**: Forwarded, X-Forwarded-For, X-Forwarded-Host, X-Forwarded-Proto, X-Forwarded-Port, X-Forwarded-Prefix. Chúng mô tả chuỗi proxy, IP, host và scheme của request.
2. **Authentication identity headers**: X-Verified-Subject, X-Remote-User, Remote-User, X-Forwarded-User, SM_USER hoặc header riêng do gateway tạo. Đây là các phát biểu về user identity, **không phải chuẩn Forwarded**.
3. **Authorization/role claims**: X-Roles, X-Groups, X-Tenant, X-Email, X-Admin, hoặc identity context có chữ ký. Những giá trị này có thể trực tiếp thay đổi quyền nếu app tin chúng.
4. **Transport attestations**: xác thực mTLS giữa từng hop, network policy, service identity, API gateway access rules. Đây mới là bằng chứng để ứng dụng tin **ai đã đưa header tới nó**; bản thân header không tạo bằng chứng.

**Rủi ro chính:** Client gửi trước **X-Verified-Subject: administrator**. Một proxy không xóa header đó rồi chuyển tiếp. Nếu Spring đọc header và tạo principal administrator, đó là **authentication bypass** dù WAF/ingress/TLS đều đang hoạt động.

**Quy tắc tối thiểu:** **Untrusted client input phải dừng tại trust boundary.** Edge bỏ/ghi đè mọi header có khả năng quyết định identity hoặc origin; authentication gateway tạo một assertion đã kiểm chứng; hop nội bộ chỉ chuyển assertion qua kênh được kiểm soát; Spring từ chối khi provenance không đủ.

## 2. Trước khi kiểm tra: xác định rõ ai tin ai

Không thể audit chỉ bằng cách liệt kê các IP address. Cần mô tả mỗi hop:

| Hop | Có được nhận request từ ai? | Có được xác thực người dùng? | Header nào được phép tạo/thay đổi? |
| --- | --- | --- | --- |
| Browser/client | Internet hoặc thiết bị nội bộ | Không đáng tin chỉ từ HTTP headers | Có thể gửi header tùy ý, bao gồm header giả mạo |
| **P0 public edge** | Internet, CDN hoặc gateway trước nó | Thường không chứng thực user đầy đủ | **Bỏ các header identity đi vào từ ngoài**, set origin metadata theo policy |
| **P1 auth gateway** | Chỉ P0 hoặc upstream đã xác thực | **Có**: xác minh session/OIDC/SAML/mTLS | Xóa identity cũ, **tạo identity mới từ kết quả auth đáng tin** |
| **P2 internal ingress** | Chỉ P1 | Không nên tự suy ra user từ IP | Chỉ nhận/forward identity theo allowlist, giữ nguyên semantics và bảo vệ transport |
| **Spring app** | Chỉ P2 hoặc mesh sidecar đã được phê duyệt | Dùng trusted identity hoặc tự xác minh signed claim | Không chấp nhận trực tiếp header từ internet để login |

Những câu hỏi bắt buộc:

- P1 thực sự **xác thực** hay chỉ tin header do P0 chuyển tới?
- P0 có xóa **cả các biến thể** của header identity, kể cả dấu gạch ngang/gạch dưới, tên khác và header lặp?
- P2 có nhận request từ một pod khác ngoài P1 không? Nếu có, pod đó có thể giả header không?
- App có service nội bộ, debug port, NodePort, LoadBalancer, localhost port-forward hoặc endpoint khác đi thẳng tới backend không?
- Các hop có được xác thực **hai chiều** bằng mTLS/service identity hay chỉ dựa vào địa chỉ private 10.x?
- X-Forwarded-For được dùng để **rate limit**, IP allowlist, admin bypass hay chỉ logging?
- Identity từ P1 có được ràng buộc vào đúng **tenant, issuer, subject, session, audience**?
- Cấu hình có dùng **X-Forwarded-User** như một shortcut bỏ qua Spring Security không?
- Có ingress mới/CDN thứ hai được thêm mà không cập nhật danh sách trusted proxies không?
- Khi một proxy fail-open, fail-closed hay bỏ qua xác thực để giữ availability?

**Đầu ra của audit** nên gồm sơ đồ hop-by-hop, cấu hình sanitization, đường kết nối thực tế, danh sách identity claims/owners, chính sách allowlist/mTLS, integration tests và khả năng phát hiện bypass.

## 3. Trust boundary và nguyên tắc “không nâng cấp dữ liệu thành quyền”

Một HTTP header là **dữ liệu**. Nó chỉ trở thành **claim có quyền** khi receiver biết chắc:

1. **Source authenticated**: kết nối thật sự đến từ đúng gateway được phép.
2. **Source authorized**: gateway ấy được phép đưa ra danh tính người dùng, không chỉ là một ingress truyền tải.
3. **Header integrity**: client và các hop trước không sửa được giá trị sau khi gateway xác thực.
4. **Correct binding**: identity tương ứng đúng request/tenant/audience, không bị lấy từ request cũ hoặc user khác.
5. **Freshness/revocation**: session hoặc identity assertion còn hiệu lực theo chính sách.
6. **Backend authorization**: user này được phép làm hành động yêu cầu trên tài nguyên cụ thể.

Một địa chỉ nguồn từ mạng private không tự là source authenticated. IP có thể bị tái sử dụng, NAT, lộ NodePort, chạy pod lạ trong cùng VPC hay bị chuyển tuyến sai.

**Dòng dữ liệu phải theo một chiều:** client có thể đề nghị host, path và credentials; gateway tự xác minh, **xóa mọi identity do client khai**; gateway phát một identity có provenance; ứng dụng chỉ sử dụng kết quả gateway đã được xác minh hoặc một signed identity token tự kiểm tra.

## 4. Tấn công 1: giả mạo identity header ở lớp ngoài

Client gửi một request thử nghiệm:

~~~http
GET /admin/reports HTTP/1.1
Host: portal.example.org
X-Verified-Subject: administrator
X-Forwarded-User: administrator
X-Groups: ADMINS
~~~

Nếu P0/P1/P2 chỉ chạy logic **“nếu header đã tồn tại thì giữ lại”**, app đọc username/roles giả và có thể tạo Authentication.

**Chỉ cần một hop quên xóa header là nguy hiểm.** Một số hệ thống dùng nhiều cách viết cùng nghĩa: X-Auth-User, X-Authenticated-User, X-Forwarded-User, X-Remote-User, Remote-User, X-User-Email, X-Email, SM_USER. Tất cả các tên có ảnh hưởng tới identity và roles phải được kiểm kê; không chỉ chặn một tên trong khi code khác tin một alias khác.

**Biện pháp:**

- Bên ngoài **không thể đưa** bất kỳ identity header nào vào app với quyền pre-authentication.
- Gateway xóa identity header **trước khi xác thực** và tự đặt giá trị **từ kết quả đã validate**.
- Spring chỉ tin **một schema/issuer rõ ràng**; không thử lần lượt 5 headers cho đến khi có user.
- Không lấy roles từ X-Groups/X-Admin do caller khai. Tải quyền từ DB/LDAP/policy engine hoặc xác minh signed claims có audience/issuer/expiry.
- Nếu một header identity xuất hiện trên đường không được phép, reject và audit thay vì tiếp tục.
- Không dùng email trần như khóa user toàn cục khi nhiều IdP/tenant; dùng issuer + subject và local account mapping theo hợp đồng identity.

**Bài học:** **RequestHeaderAuthenticationFilter không xác minh header được ký hay có nguồn đáng tin.** Nó giả định external authentication đã hoàn tất. Nếu proxy tạo ra identity chưa được xác minh, Spring Security không sửa được sai lầm đó bằng tên class “AuthenticationFilter”.

## 5. Tấn công 2: đường bypass đi thẳng tới backend

Ngay cả khi P0 và P1 sanitization hoàn hảo, backend có thể có thêm đường:

~~~text
Internet -> P0 -> P1 -> P2 -> Spring   (đường dự định)

Attacker -> exposed NodePort -> Spring (bypass P0/P1/P2)
Developer VPN -> 10.x backend:8080    (bypass P1)
Compromised pod -> Kubernetes Service -> Spring
Public LoadBalancer -> internal ingress -> Spring
~~~

Nếu Spring đọc **X-Verified-Subject** mà không xác minh provenance, kẻ gọi trực tiếp có thể tự chọn user. Đây là bypass hoàn toàn qua proxy identity assertion.

**Phòng vệ theo nhiều lớp:**

- Backend **không public** và không truy cập được từ những network segments/pods không được phép.
- Ingress/network ACL, security groups, Kubernetes NetworkPolicy chỉ cho backend nhận từ **đúng P2/service identity**; kiểm tra default-deny thực tế.
- Bật **mTLS giữa workload và trusted gateway** nếu mô hình bảo mật đòi hỏi; receiver kiểm tra identity certificate/service account của peer, không chỉ “có TLS”.
- Hạn chế service-to-service và developer port-forward, không để một pod bất kỳ trong cluster có thể gửi header identity tới backend.
- Ưu tiên **identity assertion có chữ ký với audience và thời hạn ngắn** để app tự verify nếu khó bảo đảm đường truyền kín tuyệt đối.
- Negative test: thử truy cập backend qua mọi địa chỉ công khai/nội bộ có thể có bằng một fake identity header; tất cả đường không được tin phải bị chặn **trước khi có business response**.

**Không kết luận “an toàn vì app chỉ bind 0.0.0.0 trong VPC”.** Bind 0.0.0.0 còn có thể mở thêm interface; VPC và cluster network không tự là security boundary cho identity.

## 6. Tấn công 3: X-Forwarded-For và chuỗi IP giả

**X-Forwarded-For (XFF)** là thông tin về đường đi, **không phải xác thực người dùng**. Nó thường chứa danh sách IP được ngăn cách bằng dấu phẩy:

~~~http
X-Forwarded-For: 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

Trong mô hình minh họa:

~~~text
Browser client     198.51.100.23
P0 edge            10.0.0.10
P1 auth gateway    10.0.0.11
P2 ingress         10.0.0.12  (TCP peer của app)
~~~

Nếu P0 không xóa XFF do browser tự đưa vào, attacker có thể gửi:

~~~http
X-Forwarded-For: 203.0.113.77
~~~

Và các proxies chỉ append, khiến app thấy:

~~~http
X-Forwarded-For: 203.0.113.77, 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

**Lấy phần tử đầu tiên bên trái là nguy hiểm.** Attacker đã chèn **203.0.113.77** để vượt rate limit, IP allowlist hay logging quy trách nhiệm.

### 6.1. Quy tắc xác định IP từ right-to-left

Theo một topology trusted proxies **được chứng minh**, receiver có thể:

1. Xác minh TCP peer trực tiếp là P2 **được phép**, bằng network/transport identity.
2. Duyệt danh sách XFF **từ phải sang trái** qua các hops mà mình biết chắc là trusted proxies.
3. Chọn **hop đầu tiên không nằm trong trusted proxies** làm nguồn quan sát gần nhất ngoài trust boundary.
4. Không tin các IP nằm **bên trái** của hop này: chúng có thể do client hoặc proxy chưa tin khai ra.
5. Nếu peer trực tiếp không trusted, **bỏ qua toàn bộ XFF**; dùng peer thực cho mục đích network logging hoặc từ chối kết nối tùy policy.

Đây là **mô hình khái niệm**, không phải bộ parser production. Trusted CIDR phải chính xác theo topology thực tế, có hỗ trợ IPv4/IPv6, NAT, IPv6 port notation, nhiều header values và số hop. Cũng không thể dùng kết quả XFF làm bằng chứng user identity.

**An toàn hơn khi kiểm soát được edge:** P0 **reset XFF bằng remote_addr thật mà P0 nhận**, rồi các proxies được tin chỉ append thông tin của hop của mình. Như thế attacker không đưa được IP giả từ đầu danh sách đi vào.

### 6.2. Lỗ hổng phổ biến

- Chọn **XFF[0]** trực tiếp để cho phép /admin nếu IP là IP văn phòng.
- Dùng XFF như nguồn duy nhất của rate limit mà client có thể thay đổi mỗi request.
- Tin tất cả IP private 10.0.0.0/8 khi trong VPC có workloads không được tin.
- Để client trực tiếp tới origin và tự chèn XFF hợp lệ.
- Thay danh sách proxy nhưng quên cập nhật trusted hops.
- Parse IPv6 hoặc repeated XFF headers khác nhau giữa WAF và app, dẫn đến policy mismatch.
- Dùng XFF/Forwarded để xây callback URL cho OIDC/SAML mà không xác minh host/scheme.
- Gán người dùng dựa trên IP của một NAT dùng chung nhiều user.

**IP có thể hỗ trợ chống gian lận hoặc rate limiting**, nhưng muốn phân quyền người dùng vẫn cần identity từ authentication provider/gateway tin cậy.

## 7. RFC 7239 Forwarded và họ X-Forwarded-*

RFC 7239 định nghĩa **Forwarded**, ví dụ:

~~~http
Forwarded: for=198.51.100.23;proto=https;host=portal.example.org
Forwarded: for=198.51.100.23;proto=https;host=portal.example.org, for=10.0.0.10;by=10.0.0.11
~~~

- **for**: node gửi request tới proxy.
- **by**: interface phía client của proxy.
- **proto**: scheme bên ngoài đã được quan sát.
- **host**: host header ở một hop đã chọn.
- Các pairs được phân cách bằng dấu chấm phẩy, nhiều hops phân cách bằng dấu phẩy. Có thể có quoted values, IPv6 và biến thể do từng proxy tạo.

Bên cạnh đó, hệ sinh thái proxy dùng:

~~~http
X-Forwarded-For: 198.51.100.23, 10.0.0.10
X-Forwarded-Host: portal.example.org
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /app
~~~

**Không đồng nhất Forwarded với X-Forwarded-For.** RFC 7239 mang bộ parameters gắn với từng hop, còn chuỗi X-Forwarded-* tách thành nhiều headers, dễ không biết các giá trị từ cùng một hop hay không. Các proxies có thể hỗ trợ một hoặc cả hai và xử lý precedence khác nhau.

**Điều tuyệt đối không được làm:** tin RFC Forwarded vì nó có tên theo chuẩn và coi X-Forwarded-* là không an toàn hơn. **Cả hai đều có thể do client tạo.** RFC 7239 phần Security Considerations nêu rõ giá trị có thể bị sửa bởi bất kỳ node nào, gồm cả client.

**Thiết kế khuyến nghị:**

- Quy định **một mô hình canonical forwarded metadata** trong ingress contract, tránh tự suy đoán giữa hai nhóm header xung đột.
- **P0 xóa cả Forwarded và X-Forwarded-* đi vào từ ngoài**, không chỉ loại đang dùng.
- P0 hoặc trusted edge tạo lại host/proto/client-origin metadata bằng dữ liệu do nó quan sát và allowlist.
- Các trusted hops tiếp theo chỉ chuyển/append theo policy đã được audit.
- Backend phải dùng cơ chế forwarded header parsing của framework/container thay vì một split(",") tự viết cho HTTP parsing thực tế.
- Nếu forwarded headers không cần cho app, nên **bỏ qua hoặc removeOnly** để giảm attack surface.

## 8. Tấn công 4: Host/Proto/Prefix poisoning

Giả sử browser truy cập HTTPS:

~~~text
https://portal.example.org/login
~~~

nhưng backend Spring chạy HTTP nội bộ:

~~~text
http://app-service:8080/login
~~~

Ứng dụng có thể cần public host/scheme để tạo redirect OIDC, ACS URL SAML, absolute links, cookie flags hoặc URL reset password. Một attacker gửi:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
X-Forwarded-Prefix: /unexpected
Forwarded: proto=http;host=attacker.example
~~~

Nếu app tin headers chưa được sanitization, hậu quả có thể gồm:

- **Password-reset link poisoning**: email phục hồi mật khẩu chứa host do attacker kiểm soát.
- **SSO/OIDC redirect_uri poisoning** hoặc callback URL mismatch, gây login failure hay redirect leakage.
- **SAML ACS/entityID URL mismatch** do public URL sai.
- **Open redirect/phishing** qua Location header được tạo từ Host/Forwarded.
- **Secure cookie/HTTPS redirect sai**, nhất là TLS termination ở proxy.
- **Tenant routing confusion** nếu tenant được chọn chỉ từ X-Forwarded-Host do client tự đặt.
- **Absolute URL validation bypass** khi WAF, gateway và app dùng các host/proto khác nhau.
- **Path traversal/routing policy mismatch** nếu X-Forwarded-Prefix được xử lý khác nhau qua các hop.

**Phòng vệ:** public hostnames được allowlist ở edge/gateway và app. Khi SSO/đăng nhập nhạy cảm, ưu tiên **external baseUrl cấu hình server-side** thay vì tự ghép URL từ untrusted headers. Nếu cần Forwarded/Host, chỉ dùng giá trị do trusted proxy tạo và nhất quán trên tất cả hops. Spring Boot’s forward-header strategy không thay một host allowlist hoặc một ranh giới tin cậy thực tế.

## 9. Tấn công 5: nhiều tên header, duplicated headers và HTTP parsing

Một request có thể có cùng header hai lần:

~~~http
X-Verified-Subject: employee-42
X-Verified-Subject: administrator
~~~

Hoặc biến thể casing/normalization:

~~~http
x-verified-subject: employee-42
X-Verified_Subject: administrator
~~~

**Header names trong HTTP là case-insensitive**, nhưng cách Nginx, Envoy, Tomcat, gateway hoặc security module xử lý duplicate values, underscores, commas và invalid header bytes có thể khác nhau. Một hop có thể kiểm tra giá trị đầu, hop kế tiếp dùng giá trị cuối; một proxy chặn tên dấu gạch ngang nhưng backend map tên dấu gạch dưới sang cùng biến.

Ngoài ra, các tấn công **HTTP request smuggling / message framing desynchronization** có thể khiến P0/P1 và backend hiểu ranh giới request khác nhau. Khi ấy một request mà gateway đã xác thực có thể bị ghép với body/header của request khác. Rủi ro này không được giải quyết chỉ bằng một allowlist identity header.

**Các kiểm soát nên có:**

1. Tại public edge, remove **tất cả** identity-related headers, gồm aliases và canonical/legacy names.
2. Tại authentication gateway, reject requests có **identity header lặp/mâu thuẫn**; sau khi xác minh, emit **chính xác một giá trị** theo schema.
3. Cấu hình proxy/Servlet reject headers không hợp lệ, ambiguity quanh underscores/hyphens và framing.
4. Không gửi đồng thời hai identity schemes (ví dụ X-User và X-Verified-Subject) cho app tự chọn một.
5. Không nhận các identity claims ở query parameters, cookies hoặc request body như một fallback khi header bị thiếu.
6. Harden edge/origin với HTTP parser compatibility tests, content-length/transfer-encoding policy và upstream keep-alive/protocol upgrade settings.
7. Không biến raw proxy header thành SQL string/role enum mà thiếu canonical mapping và authorization.

**Quan trọng:** RequestHeaderAuthenticationFilter đọc header principal, **không bảo đảm tự phát hiện các trường hợp trùng header hoặc parser ambiguity**. Những checks này phải được thực thi ở trust boundary/gateway và bằng thiết kế hạ tầng.

## 10. Tấn công 6: một proxy được tin truyền identity của một proxy khác chưa được tin

Mô hình nhiều hop thường có “trusted tunnel fallacy”:

~~~text
Untrusted workload U
      |
      | sends X-Verified-Subject: admin
      v
P2 ingress (được app tin)
      |
      | forwards header nguyên trạng
      v
Spring app
~~~

Spring nhìn thấy kết nối từ đúng P2 với mTLS/tên service identity hợp lệ, nhưng **P2 không hề xác minh user**. P2 là trusted **transport hop**, không phải trusted **identity issuer**. Nếu P2 chấp nhận nguồn U, app vẫn bị bypass.

**Nhiệm vụ audit phải hỏi ở từng hop:**

- Ai được gửi request đến hop này? Mặc định deny hay allow toàn namespace?
- Hop này có xác thực người dùng, hay chỉ chuyển thông tin về người dùng?
- Hop này có **xóa và tự tạo lại** header identity, hay chỉ preserve một chuỗi từ request?
- Hop tiếp theo có xác minh hop này là **đúng issuer quyền phát identity** không?
- Có proxy nào re-route tới upstream khác, skip auth hoặc thêm cấu hình “auth optional” theo path không?
- Có đường URL/route health/metrics/admin ở cùng backend đi qua filter identity mà chưa qua auth không?
- Nếu P1 bị outage, traffic có fail-open không?
- Khi thêm proxy mới, ai cập nhật mTLS policy và service-to-service allowlist?

**Tách hai trust roles:** “được phép chuyển tiếp byte” **khác** “được phép xác nhận Alice là người dùng”. Nếu chỉ P1 có chức năng authentication, một backend nên tin identity có thể kiểm tra provenance **từ P1** qua chuỗi transport được bảo vệ, không mặc nhiên từ bất kỳ proxy ở cuối.

## 11. Kiến trúc phòng vệ: strip → authenticate → attest → authorize

Một thiết kế thực hành:

~~~text
Browser
  |
  | untrusted request, arbitrary headers
  v
P0 public edge
  - Allowlisted public host/scheme
  - Remove incoming Forwarded, X-Forwarded-* and identity headers
  - Reconstruct canonical routing info from observed connection
  |
  v
P1 authentication gateway
  - Validate user session/OIDC/SAML/mTLS according to policy
  - Map verified issuer+subject to a stable internal subject
  - Drop client-influenced identity again
  - Create ONE X-Verified-Subject (or signed identity assertion)
  |
  | authenticated P1 -> P2 connection (mTLS/ACL)
  v
P2 internal ingress
  - Accept only trusted P1 workload identity
  - Never overwrite trusted subject from untrusted inputs
  - Forward subject only to explicitly authorized backend
  |
  | authenticated P2 -> app connection (mTLS/ACL)
  v
Spring Security
  - Trust source only under configured boundary; preferably verify signed token
  - Pre-authentication from verified subject, not from XFF
  - Load local account and roles; tenant/resource checks
  |
  v
Business service and DB
~~~

**Defense in depth:**

- Có thể dùng **signed JWT/OIDC ID assertion** từ authentication gateway tới backend nếu cần chứng minh provenance **end-to-end**. Backend phải xác minh chữ ký qua JWKS/certificate đáng tin, **issuer, audience, expiry, not-before, key id/rotation**, thuật toán được allowlist và claims phù hợp. JWT không tự ngăn replay nếu không có ràng buộc session/request/nonce hoặc hạn ngắn/anti-replay theo threat model.
- Có thể dùng mTLS giữa mỗi proxy + chặn mọi đường bypass. Nhưng mTLS **chỉ bảo đảm peer**, chưa chứng minh header được peer tạo sau user authentication; vẫn cần strip-and-overwrite contract.
- Proxy-side identity từ SAML/OIDC phải lưu **issuer + subject**, không đơn thuần email/username trong multi-IdP.
- Mọi backend service phải có **authorization** độc lập: principal đã xác thực chưa đủ để đọc một document không thuộc tenant.

## 12. Ví dụ Nginx public edge: bỏ header từ client và set origin chuẩn

**Đoạn sau minh họa một location trên P0 Nginx, không phải cấu hình Nginx hoàn chỉnh để triển khai trực tiếp.** Việc cấu hình TLS listener/certificates, upstream resolution, limits, service mesh và các routes khác cần được hoàn thành riêng.

~~~nginx
server {
    listen 443 ssl;
    server_name portal.example.org;

    # ssl_certificate /etc/nginx/tls/fullchain.pem;
    # ssl_certificate_key /etc/nginx/tls/private.key;

    location / {
        # Loại các Forwarded headers do client gửi.
        # proxy_set_header với value rỗng -> không gửi upstream.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host portal.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix "";

        # Không cho client tự khai identity/roles.
        proxy_set_header X-Verified-Subject "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Remote-User "";
        proxy_set_header X-Groups "";
        proxy_set_header X-Tenant "";
        proxy_set_header SM_USER "";

        proxy_set_header Host portal.example.org;
        proxy_pass http://authentication-gateway.internal:8080;
    }
}
~~~

**Giải thích cấu hình:**

1. P0 nhận TLS và một hostname đã được cấu hình; nếu có virtual hosts khác, cần có **default server reject/allowlist** để không trả nhầm host.
2. X-Forwarded-For được **reset về $remote_addr mà P0 thực sự nhận**, không dùng **$proxy_add_x_forwarded_for** ngay tại public edge với client input chưa được xóa.
3. Forwarded header chuẩn của RFC 7239 bị loại; nếu downstream muốn dùng Forwarded, trusted edge phải **tạo lại** đúng policy và chọn **một chuẩn**.
4. Host/Proto được đặt thành canonical giá trị đã phê duyệt. Nếu CDN ở trước Nginx và đây **không phải edge đầu tiên**, $remote_addr là IP CDN; P0 phải có quy trình xác minh CDN và lấy client IP theo trusted CDN contract, **không thể tự coi nó là browser IP**.
5. Identity và role headers từ client bị xóa; P0 **không** tự phát X-Verified-Subject vì P0 không làm xác thực.
6. **auth gateway P1** cần xác minh user rồi **tạo lại** duy nhất identity header. Không được chỉ preserve header từ client hay bỏ qua auth khi header đã có.
7. Đường P0→P1 trong snippet là **HTTP nội bộ để minh họa cấu trúc**, **chưa bảo đảm bảo mật transport**. Production dùng mTLS/HTTPS hoặc mạng bảo vệ phù hợp, chặn đường bypass; không copy nguyên snippet và gọi đó là đủ an toàn.

**Vấn đề thực tế:** Cấu hình chỉ trong một Nginx location không bao phủ toàn bộ ingress routes nếu có location khác, auth bypass path, protocol upgrade hoặc proxy riêng. Rà soát tất cả routes/virtual hosts, kể cả health/admin endpoints và alternate domain.

## 13. Authentication gateway phải phát subject từ kết quả đã xác thực

P1 là nơi triển khai một authentication flow thật, ví dụ:

- OIDC Authorization Code + PKCE với provider đã được cấu hình, xác minh session/callback/ID Token tương ứng.
- SAML Web Browser SSO với signed assertion đã kiểm chứng Issuer/Audience/Recipient/time/response correlation.
- mTLS client certificate với truststore và mapping identity rõ.
- Kerberos/SPNEGO validation thực sự, không chỉ header Authorization có tiền tố Negotiate.

Pseudocode **không phải cấu hình Nginx có thể copy chạy**:

~~~text
handle(incomingRequest):
    reject if connection is not from an approved P0 identity
    remove all incoming identity/authorization-claim aliases
    authenticatedUser = authenticationEngine.verify(incomingRequest)
    if authenticatedUser is absent:
        return 401 or redirect to login, never synthesize a user

    stableSubject = map(verifiedIssuer, verifiedSubject, tenant)
    if mapping is unapproved or account disabled:
        deny

    forward only one canonical identity:
        X-Verified-Subject = stableSubject

    drop any other X-Role/X-User/X-Admin client input
    send request to P2 over authenticated transport
~~~

**Nguồn dữ liệu quan trọng:** Verified issuer/subject phải đến từ kết quả SAML/OIDC/Kerberos đã được kiểm tra; không dùng query param **user**, cookie tự khai, email attribute chưa được xác minh hoặc IP/client user-agent làm subject.

Nếu P1 cần gửi roles, phải phát các grants theo **một schema có kiểm chứng và tính đến revocation**, hoặc backend tự tra quyền local. Nếu hệ thống dùng nhiều IdP, thêm issuer/tenant scope vào khóa liên kết người dùng để không trùng identity.

### Khi nào nên dùng signed identity assertion?

**Đặc biệt nên cân nhắc** khi:

- Có nhiều hop/phạm vi quản trị độc lập.
- App có thể được gọi từ nhiều namespaces hoặc service mesh.
- Không thể bảo đảm P2 chỉ nhận request từ P1.
- Cần chứng minh issuer/audience và thời hạn ngay tại backend.
- Có nghiệp vụ nhạy cảm, yêu cầu audit/revocation/freshness nghiêm.

Ở dạng này, **app dùng Spring Security OAuth2 Resource Server/JWT validation** để kiểm chứng token của gateway (nếu schema phù hợp), thay vì tin tên user trần. Có thể vẫn cần network/mTLS controls để bảo vệ riêng backend. Không tự chế header **X-Signature=SHA256(username)**; checksum không phải authentication, còn HMAC không có replay/issuer/audience policy đầy đủ dễ tạo lỗi.

## 14. Spring Boot 3: ForwardedHeaderFilter và forward-header strategy

**Forwarded headers cho URL/IP không phải pre-authentication identity.** Spring Boot hỗ trợ:

~~~yaml
server:
  forward-headers-strategy: none
~~~

Tùy Spring Boot 3.x, các mode chính:

| Strategy | Cách xử lý | Ý nghĩa bảo mật |
| --- | --- | --- |
| **NONE** | Không dùng forwarded headers để hiệu chỉnh request | Phù hợp nếu app không cần external URL auto-generation hoặc có canonical baseUrl riêng |
| **NATIVE** | Servlet container xử lý, ví dụ Tomcat RemoteIpValve | Phải cấu hình **trusted proxy/internal-proxies** và header policy đúng |
| **FRAMEWORK** | Spring Framework **ForwardedHeaderFilter** | Dựa vào forwarded headers đã được trusted edge **sanitize**; filter **không xác minh source proxy** |

Ví dụ sau **chỉ phù hợp khi edge/ingress đã bảo đảm forwarded headers được tạo lại an toàn**:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Framework **ForwardedHeaderFilter** dùng Forwarded/X-Forwarded-* để làm request.getScheme/getServerName/getServerPort/redirects phản ánh URL bên ngoài. Nó cũng loại các forwarded headers sau khi sử dụng để tránh thành phần phía sau đọc trực tiếp, nhưng **việc dùng rồi xóa header không tự chứng minh header ban đầu là đúng**.

Nếu không muốn dùng headers ấy nhưng muốn loại chúng khỏi request, Spring cung cấp **ForwardedHeaderFilter.setRemoveOnly(true)**. Cần đăng ký filter đúng thứ tự/phạm vi và tránh đăng ký đôi với Boot auto-configuration. Không vừa bật FRAMEWORK vừa tự thêm một ForwardedHeaderFilter khác không được kiểm soát.

### 14.1. Tomcat Native và trusted proxy list

Với **NATIVE** trên embedded Tomcat, RemoteIpValve có cấu hình internal/trusted proxy matching; mặc định có thể tin các private ranges tùy version. Đừng để trusted proxy list rộng hơn các network thật sự được phép gửi header vào app.

**Không đặt internal-proxies rỗng để tin mọi host trong production.** Trong hạ tầng Kubernetes, phải hiểu pod IP, load balancer source IP, SNAT, node IP và mesh sidecar trước khi quyết định CIDR/regex. Nếu đặt sai, app có thể coi X-Forwarded-For do attacker tự khai là remoteAddr hợp pháp.

### 14.2. Security Headers không giải quyết Identity Header Spoofing

Spring Security có header writers (HSTS, cache, X-Content-Type-Options, CSP...). Chúng bảo vệ **HTTP response**, nhưng không xác thực **request header identity**. Một app bật HSTS/CSP vẫn có thể bị chiếm tài khoản nếu nó tin X-Verified-Subject do client gửi.

**Kết luận của mục này:** Cấu hình forwarded headers giải quyết **metadata của request**, còn pre-authentication header giải quyết **user identity**; hai quyết định phải được kiểm tra độc lập và chỉ dựa trên trusted boundary.

## 15. Spring Security RequestHeaderAuthenticationFilter: cực kỳ phụ thuộc proxy

Theo tài liệu Spring Security pre-authentication, **RequestHeaderAuthenticationFilter** trích username từ một header và **không tự thực hiện xác thực bên ngoài**. Mặc định tên header của class là **SM_USER** (lịch sử Siteminder), nhưng ứng dụng có thể cấu hình header riêng.

Luồng:

~~~text
trusted gateway:
  verifies human / machine identity
  emits X-Verified-Subject: employee-42
        |
        v
Spring Security
  RequestHeaderAuthenticationFilter:
     reads employee-42 from header
        |
        v
PreAuthenticatedAuthenticationProvider
  UserDetailsByNameServiceWrapper / UserDetailsService
     verifies local account enabled, loads authorities
        |
        v
AuthorizationFilter / method security / business policy
     checks resource/tenant/action permissions
~~~

**Lỗ hổng nếu thiếu boundary:** Attacker gọi thẳng app với header **X-Verified-Subject: employee-42**, filter có thể xác thực như employee-42. Vì vậy **đúng class, đúng Java API, đúng role mapping vẫn không có giá trị nếu network/auth gateway cho phép forge header**.

**Không nên kết hợp bừa với fallback formLogin/BasicAuth** trên cùng các endpoints nếu việc bypass authentication gateway qua cơ chế khác là trái chính sách. Nếu cần nhiều authentication mechanisms, tách chains/routes và trust contracts rõ.

## 16. Ví dụ Spring Boot 3 / Security 6.x / Java 17: pre-auth với header chỉ từ gateway

**Mô hình chạy thử:** App phải được triển khai sau một **auth gateway thật**; backend không được truy cập trực tiếp. Trước khi cấp quyền, gateway phải xác minh user và overwrite header X-Verified-Subject. Code **KHÔNG** chứa logic để xác minh nguồn header độc lập; không dùng riêng code này trên một public backend.

### 16.1. Maven dependencies

Trong pom.xml có Spring Boot parent/BOM tương thích Security 6.x:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
</dependencies>
~~~

Các Java classes dưới đây là một project minh họa **Spring MVC Servlet**. Không cần Spring Security SAML2/OIDC dependency cho **pre-auth header**; nếu gateway phát JWT để app tự verify thì cần cấu hình resource server khác, không tự nhầm hai thiết kế.

### 16.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  forward-headers-strategy: none
  servlet:
    session:
      timeout: 20m
~~~

Ví dụ cố ý đặt **none** để app không tự diễn giải forwarded origin headers. Nếu production phải tạo absolute redirects từ external host, dùng canonical URL cấu hình server-side hoặc chỉ bật FRAMEWORK/NATIVE sau khi đã kiểm tra edge sanitization và trusted proxy configuration.

### 16.3. Main class

**src/main/java/com/example/proxyauth/ProxyIdentityApplication.java**

~~~java
package com.example.proxyauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyIdentityApplication.class, args);
    }
}
~~~

### 16.4. SecurityConfig

**src/main/java/com/example/proxyauth/ProxySecurityConfig.java**

~~~java
package com.example.proxyauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class ProxySecurityConfig {

    @Bean
    UserDetailsService approvedUsers() {
        // Chỉ dành cho demo. Production cần database/IdP
        // identity-link mapping + tenant/account state.
        return username -> {
            if (!"employee-42".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Unapproved identity");
            }
            return User.withUsername(username)
                .password("{noop}unused-for-proxy")
                .roles("READER")
                .build();
        };
    }

    @Bean
    PreAuthenticatedAuthenticationProvider preauthProvider(
            UserDetailsService approvedUsers) {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            wrapper = new UserDetailsByNameServiceWrapper<>();
        wrapper.setUserDetailsService(approvedUsers);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(wrapper);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            PreAuthenticatedAuthenticationProvider provider)
            throws Exception {

        // Cơ chế stateless trong ví dụ:
        // gateway xác minh và set header mỗi request.
        NullSecurityContextRepository noSession =
            new NullSecurityContextRepository();

        // Chỉ tồn tại trong Spring Security chain, không
        // khai báo @Bean Filter rồi auto-register ở Servlet.
        RequestHeaderAuthenticationFilter preauth =
            new RequestHeaderAuthenticationFilter();
        preauth.setPrincipalRequestHeader("X-Verified-Subject");
        preauth.setExceptionIfHeaderMissing(false);
        preauth.setAuthenticationManager(
            new ProviderManager(provider));
        preauth.setSecurityContextRepository(noSession);

        http
            .securityContext(sc -> sc
                .securityContextRepository(noSession))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new Http403ForbiddenEntryPoint()))
            .addFilterBefore(
                preauth, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Đọc đúng code:**

- **RequestHeaderAuthenticationFilter** chỉ đọc X-Verified-Subject. Nó **không verify signature, session, mTLS hoặc gateway identity**.
- **PreAuthenticatedAuthenticationProvider** tải UserDetails qua wrapper; UserDetailsService trong ví dụ chỉ cho đúng **employee-42** và vai trò **ROLE_READER**.
- **NullSecurityContextRepository + STATELESS** khiến ví dụ không lưu Authentication qua HttpSession. Mỗi request được **trusted gateway** xác minh và đưa đúng header mới. Ở mô hình stateful khác, dùng HttpSessionSecurityContextRepository và thiết kế logout/revocation/principal-change checking riêng.
- **Http403ForbiddenEntryPoint** là cách xử lý thiếu Authentication cho endpoint đã chọn; không tự sửa được việc attacker có thể forged header.
- Không bật formLogin/BasicAuth và không thêm nhánh cho mọi X-User header. Tất cả endpoints được bảo vệ theo cùng mô hình pre-auth trong ví dụ.
- **Không khai báo filter thành một Servlet Filter bean độc lập**; chỉ add vào chain.
- Các thay đổi trạng thái dựa trên browser cookie nếu có phải tiếp tục giữ CSRF protection theo đúng threat model. Ví dụ dùng request header và stateless, nhưng **stateless không tự bảo đảm mọi browser CSRF risk đã biến mất** nếu gateway còn cookie session hoặc tự động gắn identity header khi browser gửi request cross-site.
- Production cần kiểm tra authorization theo tenant/resource, chứ không coi ROLE_READER là quyền đọc mọi object.

### 16.5. Controller

**src/main/java/com/example/proxyauth/IdentityController.java**

~~~java
package com.example.proxyauth;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/me")
    public Map<String, String> me(Principal principal) {
        return Map.of(
            "subject", principal.getName(),
            "source", "trusted-gateway-preauth-demo");
    }
}
~~~

### 16.6. Các bước chạy đúng

Trong project Java 17+ với Maven:

~~~bash
mvn spring-boot:run
~~~

**Đây là pre-auth demo, không phải xác thực gateway end-to-end.** Nếu developer chạy trực tiếp HTTP localhost:8080 rồi gửi X-Verified-Subject: employee-42, app **có thể chấp nhận giả mạo** vì code cố ý giả định upstream đã xác thực. Dùng điều này làm **negative/security education test**, tuyệt đối không triển khai backend public với cấu hình ấy.

Ở môi trường tích hợp thật:

1. Backend chỉ nhận kết nối từ auth gateway/ingress được phép; kiểm tra ACL/mTLS.
2. Gateway bỏ mọi inbound identity header.
3. Gateway xác minh user thật, phát X-Verified-Subject từ verified issuer+subject mapping.
4. Gửi GET /me qua **public gateway** và xác minh subject đúng.
5. Thử đưa fake X-Verified-Subject: administrator từ browser qua gateway; gateway phải overwrite/drop và app không thấy administrator.
6. Thử kết nối thẳng backend với fake identity: phải bị chặn bởi network/transport policy trước khi đến app.
7. Đổi/thu hồi quyền user tại DB; request mới phải được từ chối hoặc phản ánh policy cập nhật theo SLA.
8. Kiểm tra host/proto/header poisoning, duplicate headers, multi-tenant và request tracing.

**Không có stdout “SSO thành công” cố định**, vì auth gateway và danh tính người dùng thật phụ thuộc môi trường. Endpoint /me trả JSON chỉ sau khi pre-auth đã hoàn thành theo contract.

## 17. Java 17 chạy độc lập: mô hình trusted hops và identity boundary

Chương trình sau có thể chạy **độc lập bằng JDK 17**; không cần Spring, Nginx hoặc Kubernetes. Nó minh họa cách lựa chọn **first untrusted hop từ phải sang trái** của một chuỗi X-Forwarded-For và cách một policy chỉ nhận identity khi có **trusted immediate peer và xác thực transport**.

Đây là **mô phỏng logic**, không phải trình parse IP/CIDR/IPv6/HTTP headers production, và boolean mTLS trong demo là **dữ liệu mô phỏng từ hạ tầng đáng tin**, không phải một HTTP header attacker có thể gửi.

**Tệp: ProxyTrustBoundaryDemo.java**

~~~java
import java.util.List;
import java.util.Set;

public final class ProxyTrustBoundaryDemo {

    private static final Set<String> TRUSTED_PROXIES =
        Set.of("10.0.0.10", "10.0.0.11", "10.0.0.12");

    enum Decision {
        ELIGIBLE_FOR_ACCOUNT_LOOKUP,
        REJECT_UNTRUSTED_PEER,
        REJECT_NO_AUTHENTICATED_TRANSPORT,
        REJECT_NO_IDENTITY,
        REJECT_ORIGIN_MISMATCH
    }

    record GatewayRequest(
        String tcpPeer,
        boolean peerTransportAuthenticated,
        String verifiedSubject,
        String publicHost,
        String publicScheme) { }

    static String observedClientHop(
            String tcpPeer, List<String> xForwardedFor) {

        // Nếu TCP peer không được tin, bỏ qua header tự khai.
        if (!TRUSTED_PROXIES.contains(tcpPeer)) {
            return tcpPeer;
        }

        // Chỉ tin các hops được biết từ phải sang trái.
        for (int i = xForwardedFor.size() - 1; i >= 0; i--) {
            String hop = xForwardedFor.get(i).trim();
            if (!TRUSTED_PROXIES.contains(hop)) {
                return hop;
            }
        }
        return "UNKNOWN";
    }

    static Decision evaluate(GatewayRequest request) {
        if (!"10.0.0.12".equals(request.tcpPeer())) {
            return Decision.REJECT_UNTRUSTED_PEER;
        }
        if (!request.peerTransportAuthenticated()) {
            return Decision.REJECT_NO_AUTHENTICATED_TRANSPORT;
        }
        if (request.verifiedSubject() == null
                || request.verifiedSubject().isBlank()) {
            return Decision.REJECT_NO_IDENTITY;
        }
        if (!"portal.example.org".equals(request.publicHost())
                || !"https".equals(request.publicScheme())) {
            return Decision.REJECT_ORIGIN_MISMATCH;
        }
        return Decision.ELIGIBLE_FOR_ACCOUNT_LOOKUP;
    }

    public static void main(String[] args) {
        List<String> cleanChain = List.of(
            "198.51.100.23", "10.0.0.10", "10.0.0.11");
        List<String> spoofedLeftmost = List.of(
            "203.0.113.77", "198.51.100.23",
            "10.0.0.10", "10.0.0.11");

        System.out.println("cleanClient=" +
            observedClientHop("10.0.0.12", cleanChain));
        System.out.println("spoofedClient=" +
            observedClientHop("10.0.0.12", spoofedLeftmost));
        System.out.println("directBypass=" +
            observedClientHop("203.0.113.77", cleanChain));

        GatewayRequest good = new GatewayRequest(
            "10.0.0.12", true,
            "employee-42", "portal.example.org", "https");
        GatewayRequest wrongPeer = new GatewayRequest(
            "203.0.113.77", true,
            "administrator", "portal.example.org", "https");
        GatewayRequest noMtls = new GatewayRequest(
            "10.0.0.12", false,
            "administrator", "portal.example.org", "https");
        GatewayRequest noSubject = new GatewayRequest(
            "10.0.0.12", true,
            null, "portal.example.org", "https");
        GatewayRequest wrongHost = new GatewayRequest(
            "10.0.0.12", true,
            "employee-42", "attacker.example", "http");

        System.out.println("good=" + evaluate(good));
        System.out.println("wrongPeer=" + evaluate(wrongPeer));
        System.out.println("noMtls=" + evaluate(noMtls));
        System.out.println("noSubject=" + evaluate(noSubject));
        System.out.println("wrongHost=" + evaluate(wrongHost));
    }
}
~~~

Chạy:

~~~bash
javac ProxyTrustBoundaryDemo.java
java ProxyTrustBoundaryDemo
~~~

**Stdout chính xác theo Java 17:**

~~~text
cleanClient=198.51.100.23
spoofedClient=198.51.100.23
directBypass=203.0.113.77
good=ELIGIBLE_FOR_ACCOUNT_LOOKUP
wrongPeer=REJECT_UNTRUSTED_PEER
noMtls=REJECT_NO_AUTHENTICATED_TRANSPORT
noSubject=REJECT_NO_IDENTITY
wrongHost=REJECT_ORIGIN_MISMATCH
~~~

**Giải thích:**

- Chuỗi bị chèn **203.0.113.77** bên trái không làm thay đổi first untrusted hop nếu P2, P1, P0 thật sự trusted và danh sách hops chính xác.
- Một TCP peer trực tiếp **không trusted** làm mọi XFF của nó vô giá trị cho quyết định trusted client IP.
- Mô hình request chỉ đủ điều kiện cho **local account lookup** nếu peer đúng, transport đã được hạ tầng xác thực, subject hiện diện và public origin nằm trong allowlist.
- **ELIGIBLE_FOR_ACCOUNT_LOOKUP không có nghĩa user đã được authenticated**. Ứng dụng còn phải chứng minh identity header **thực sự được P1 tạo sau authentication**, chứ không chỉ được một P2 có mTLS forward từ attacker; phải resolve account/permissions.

**Không copy hàm observedClientHop làm bảo vệ production:** Code dùng exact IP strings, không xử lý IPv6/brackets, RFC 7239, duplicated headers, CIDR, NAT/mesh hoặc parser ambiguity. Dùng cơ chế trusted proxies của server/ingress/framework và đặt edge reset policy đúng.

## 18. Bảng nguy cơ và kiểm soát khi có nhiều reverse proxies

| Tình huống | Lỗi tin cậy | Hậu quả có thể xảy ra | Kiểm soát |
| --- | --- | --- | --- |
| Browser gửi X-Verified-Subject | Gateway preserve header client | Đăng nhập nhầm admin | Strip/overwrite sau auth |
| Browser gửi X-Groups/ROLE_ADMIN | Backend gán quyền từ header | Privilege escalation | Local authorization hoặc signed claims |
| Direct HTTP to backend | Bypass trusted edge/auth gateway | User spoofing | ACL/NetworkPolicy/mTLS + route review |
| Pod nội bộ giả P1 | Trust mọi private IP | User spoofing ngang cluster | Service identity authorization |
| P0 quên reset XFF | App dùng leftmost IP | Rate limit/IP allowlist bypass | Reset edge, trusted-hop policy |
| P2 append identity từ U | Transport proxy bị nhầm là identity issuer | Header spoof qua trusted hop | P1 signed provenance, P2 ingress allowlist |
| Forwarded + XFH xung đột | Gateway/app dùng precedence khác | Host/redirect spoof | Canonical one-format policy |
| X-Forwarded-Proto=http giả | App tin scheme sai | Insecure redirects/cookies | Trusted edge overwrite |
| X-Forwarded-Host ác ý | App sinh absolute links | Password reset/SSO redirect poisoning | Host allowlist, configured public URL |
| X-Forwarded-Prefix ác ý | Prefix rewrite không nhất quán | Routing/policy bypass | Path allowlist và proxy normalization |
| Duplicated X-Auth-User | Hai hops chọn giá trị khác | Identity confusion | Reject duplicates; one canonical header |
| X_Auth_User alias | Proxy/app normalize khác | Bypass header denylist | Strict header schema/normalization |
| HTTP request smuggling | Khác biệt framing qua hops | Ghép sai request/identity | HTTP parser alignment/hardening |
| P1 auth disabled cho một path | Gateway fail-open | Bypass auth | Fail-closed, path coverage tests |
| P1 session hết nhưng header vẫn cached | Stale identity | Revocation delay | No shared caching; TTL/freshness |
| Signed JWT không kiểm aud/iss | Token từ service khác được tái dùng | Cross-service impersonation | Verify signature, aud, iss, exp |
| Tenant dựa trên untrusted Host | Mix identity giữa tenants | Cross-tenant data access | Tenant source binding/allowlist |
| P2 bị compromise | Gateway identity bị thay | Impersonation | Defense in depth, signed assertion to app |
| Backend logs raw identity tokens | Secret/PII leakage | Session replay/privacy risk | Structured redacted logs |
| Một service có cả header auth và Basic | Alternative auth bypass proxy | Policy bypass | Distinct routes/chains and deny defaults |

## 19. Kế hoạch kiểm thử âm end-to-end

Những test quan trọng nên được triển khai trong **môi trường staging được phép kiểm thử**, dùng một account không nhạy cảm và IDs giả. Không thử trực tiếp vào người dùng khác hoặc production khi chưa có quy trình phê duyệt.

1. **Public forged identity header:** từ client gửi X-Verified-Subject: administrator qua P0; gateway phải bỏ/overwrite, không đăng nhập admin.
2. **Header aliases:** thử X-Authenticated-User, X-Forwarded-User, Remote-User, SM_USER; không header nào tự cấp quyền.
3. **Duplicate identity:** gửi hai X-Verified-Subject khác nhau; policy reject hoặc chỉ nhận giá trị do gateway phát duy nhất.
4. **Header name normalization:** thử khác casing và underscore/hyphen; không vượt sanitization.
5. **Forged roles:** gửi X-Groups: ADMINS hoặc X-Admin:true; backend không tự tăng roles.
6. **Direct origin bypass:** gọi backend/NodePort/LoadBalancer bằng fake header; không được đến app hoặc bị từ chối.
7. **Lateral pod:** từ một test pod không thuộc trusted identity gửi đến backend; NetworkPolicy/mTLS từ chối.
8. **Untrusted P2 upstream:** một workload chưa qua P1 gửi request tới P2 có identity header; P2 không chuyển thành user hợp lệ.
9. **XFF leftmost spoof:** gửi IP admin giả ở đầu danh sách; trusted client-IP policy không chọn nó.
10. **XFF malformed/IPv6:** repeated headers, IPv6 literal, brackets, ports; parser nhất quán và fail-safe.
11. **Forwarded precedence:** gửi Forwarded và X-Forwarded-* xung đột; edge canonicalize/reject, app không chọn tùy tiện.
12. **Host poisoning:** X-Forwarded-Host: attacker.example; Location/link/password reset callback không dùng host attacker.
13. **Proto poisoning:** X-Forwarded-Proto: http; app không tạo insecure absolute redirects khi public endpoint HTTPS.
14. **Prefix poisoning:** X-Forwarded-Prefix:/admin; path matching/authz không bị bypass.
15. **Real gateway authentication:** gửi request thiếu session OIDC/SAML; P1 từ chối và không emit X-Verified-Subject.
16. **Revoked session:** revoke auth gateway session, request mới không giữ identity cũ quá hạn policy.
17. **User disabled locally:** gateway xác thực hợp lệ nhưng local user disabled; app không có business access.
18. **Wrong tenant:** user hợp lệ ở tenant A dùng host/claims của tenant B; app deny cross-tenant.
19. **Signed identity wrong aud/iss/exp:** app tự verify JWT/token và reject đúng nguyên nhân.
20. **P1 outage:** ingress không fail-open, không tự tạo anonymous/admin identity.
21. **Authentication filter mismatch:** X-Verified-Subject có trong request đã xác minh nhưng endpoint chọn sai Spring SecurityFilterChain; phát hiện và sửa chain matching.
22. **Mixed auth schemes:** thử Basic/form/cookie fallback nếu policy chỉ cho proxy auth; không bypass gateway.
23. **Cookies/CSRF:** gateway dùng session cookie phải chặn unsafe cross-site changes, ngay cả backend pre-auth stateless.
24. **Request smuggling regression:** kiểm tra các giao thức h1/h2/transfer encoding trong test setup hợp lệ với WAF/proxy/backend.
25. **Audit consistency:** một request qua tất cả hops có trace ID, sanitized identity provenance và decision; không log raw credentials.

### Minh họa kiểm thử thủ công

Một lệnh chỉ dùng cho **test/staging domain được sở hữu**:

~~~bash
curl -i \
  -H "X-Verified-Subject: administrator" \
  -H "X-Forwarded-For: 203.0.113.77" \
  -H "X-Forwarded-Host: attacker.example" \
  https://portal.staging.example.org/me
~~~

**Kết quả mong muốn:** không xuất hiện principal administrator dựa trên các headers giả. Request có thể bị từ chối, yêu cầu đăng nhập hoặc trả principal thực do auth gateway đã xác minh. Nếu đã vào một session staging hợp lệ, gateway vẫn phải overwrite identity, không lấy value từ curl.

Đừng suy từ một HTTP 200 rằng bypass thành công: endpoint có thể là public hoặc trả dữ liệu ẩn danh. Cần xác minh **SecurityContext principal, local account ID, tenant/role decision và resource response** đã được ghi log an toàn.

## 20. Logging, phát hiện và điều tra

Một request đi qua nhiều hops nên có **trace/correlation ID** do trusted edge tạo hoặc được chuẩn hóa. Tuy nhiên, trace header cũng có thể bị client giả; phải reset/sanitize ở edge nếu nó dùng để gắn identity/audit.

**Nên log (theo chính sách dữ liệu):**

- Trusted ingress/hop identity thực tế, client IP đã được chuẩn hóa một cách có kiểm soát.
- Decision điểm nào xác thực user: P1 issuer, session/authentication method ở dạng được phép ghi.
- User internal ID hoặc pseudonymous hash thay vì email/raw token.
- Chosen tenant, route, HTTP method, security rule và allow/deny reason.
- X-Forwarded origin metadata đã được chuẩn hóa; nếu mâu thuẫn, ghi cờ lỗi thay vì raw injection.
- Proxy config version, mTLS service identity, authentication gateway policy version.
- Count anomalies: identity header xuất hiện ở public edge, duplicate headers, direct-backend attempts, wrong audience, host spoof, 403 spikes.

**Không log** raw Authorization header, OIDC/SAML tokens, cookies, mTLS private keys, session IDs, password reset tokens hoặc toàn bộ untrusted Forwarded values kèm PII không cần thiết.

**Cảnh báo cần có:** backend request đến từ IP/service identity không nằm trong allowlist, missing trusted authentication assertion trên protected route, invalid signed-claim audience, gateway fail-open, direct NodePort access, auth user đổi giữa hops, X-Forwarded-Host ngoài allowlist, duplicate X-Verified-Subject, hoặc tăng đột biến rate limit exemptions.

Audit trail phải chống bị header giả ghi đè: không lấy username/trace ID do browser tự khai làm nguồn duy nhất cho sự kiện.

## 21. Checklist review sản xuất

- [ ] Có sơ đồ tất cả hops P0/P1/P2/sidecar đến app; cập nhật khi thêm CDN, WAF, ingress hoặc network route.
- [ ] Chỉ rõ **identity issuer thật** (P1), khác với **transport proxy** (P0/P2).
- [ ] Public edge xóa **Forwarded và toàn bộ X-Forwarded-*** đi vào từ client, tạo lại metadata an toàn.
- [ ] Public edge xóa **mọi identity/role/tenant header aliases**, không chỉ một tên.
- [ ] Authentication gateway **verify** user thật trước khi phát một X-Verified-Subject hoặc signed assertion.
- [ ] Backend chỉ nhận traffic từ đúng trusted gateway/ingress; cấm direct NodePort/LoadBalancer/debug path.
- [ ] Dùng ACL/NetworkPolicy và, khi phù hợp, **mTLS service identity** trên hops; private IP một mình không đủ.
- [ ] Nếu P2 nhận traffic từ nhiều nguồn, chỉ P1 được phép gửi identity assertion; không preserve header từ workload khác.
- [ ] XFF trusted-hop policy biết chính xác TCP peer/hops, không chọn leftmost IP chưa được tin.
- [ ] Host/Proto/Port/Prefix được canonicalize; public domain allowlist, callback URL/redirect an toàn.
- [ ] Có chính sách một chuẩn Forwarded/X-Forwarded-* và cách xử lý header mâu thuẫn.
- [ ] Reject/normalize duplicate identity headers, underscore/hyphen alias và invalid HTTP framing theo proxy contract.
- [ ] Spring Boot forwarded strategy NONE/NATIVE/FRAMEWORK được lựa chọn có lý do; ForwardedHeaderFilter không bị coi là bộ xác thực.
- [ ] Nếu dùng RequestHeaderAuthenticationFilter, có tài liệu rõ **nó không tự xác minh identity**.
- [ ] Local account/tenant/roles/resource permissions được kiểm tra riêng, không tin X-Groups/X-Admin tự khai.
- [ ] Nếu dùng signed identity token, backend kiểm issuer/audience/signature/exp/nbf/key rotation và replay policy.
- [ ] Không có đường fallback form/Basic/API không mong muốn bypass proxy auth.
- [ ] Backend session/cookie/CSRF, proxy auth session, logout/revocation lifecycle được kiểm thử độc lập.
- [ ] Header identity phải được phát lại theo policy mỗi request hoặc có session binding/absolute lifetime rõ.
- [ ] Có tests từ public edge, internal network, untrusted pod, ingress alternate route và multi-tenant.
- [ ] Có tests sai XFF, Forwarded, Host, Proto, Prefix, repeated headers, forged roles và request smuggling.
- [ ] Logging/tracing redaction không tiết lộ credentials/PII hoặc cho phép client giả audit identity.
- [ ] Có alert trên direct backend access, forged identity headers, gateway fail-open, issuer mismatch và proxy topology drift.
- [ ] Khi đổi proxy config, chạy regression tests cho authentication, authorization, callbacks và redirects trước rollout.

**Ghi nhớ:** Trong nhiều lớp reverse proxy, **header identity chỉ an toàn bằng hop yếu nhất trong chuỗi tin cậy**. Hãy xử lý nó như một **assertion có nguồn phát**: strip dữ liệu từ client → authentication gateway xác minh → tạo lại identity → bảo vệ và xác nhận provenance qua mọi hop → Spring kiểm tra local account và quyền. **X-Forwarded-For, Forwarded, mTLS peer và X-Verified-Subject giải quyết các câu hỏi khác nhau**; không nên lấy một thông tin làm bằng chứng cho điều mà nó không chứng minh.

## 22. Tài liệu tham khảo

- [RFC 7239 – Forwarded HTTP Extension, Section 8 Security Considerations](https://www.rfc-editor.org/rfc/rfc7239.html): Forwarded có thể bị chỉnh sửa bởi cả client và proxies; tin cậy phụ thuộc trusted hops và transport.
- [Spring Framework 6.2 – Forwarded Headers và ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): reset ở edge, ForwardedHeaderFilter, removeOnly và thứ tự filter.
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): NONE/NATIVE/FRAMEWORK, Tomcat RemoteIpValve, internal-proxies và forwarded header support.
- [Spring Security 6.5 – Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): RequestHeaderAuthenticationFilter chỉ trích principal; external auth phải bảo vệ header.
- [Spring Security 6.5 – RequestHeaderAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): principalRequestHeader, exceptionIfHeaderMissing.
- [Spring Security 6.5 – AbstractPreAuthenticatedProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): AuthenticationManager, SecurityContextRepository, principal-change.
- [MDN – X-Forwarded-For Security and Privacy Concerns](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): trusted proxy selection, direct origin reachability và risk for IP-based security policies.
- [MDN – Forwarded HTTP Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Forwarded): syntax for/by/host/proto, multiple proxies và privacy.
- [OWASP – HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): phân loại và policy cho HTTP response/request headers.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, resource-level authorization.
- [OWASP – HTTP Request Smuggling](https://owasp.org/www-community/attacks/HTTP_Request_Smuggling): chênh lệch parser/proxy có thể tạo trust boundary desynchronization.
