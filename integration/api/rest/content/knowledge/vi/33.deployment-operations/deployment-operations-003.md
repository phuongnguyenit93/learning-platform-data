# Forwarded header, địa chỉ công khai và ranh giới proxy tin cậy

## 1. Bài toán: backend nhìn thấy HTTP nhưng người dùng truy cập HTTPS

Một Orders REST API được triển khai phía sau reverse proxy:

~~~text
Browser                       Reverse proxy                 Spring Boot
https://api.example.com       TLS :443                      HTTP :8080 (private)
          |---------------------->|------------------------------>|
          |  POST /api/orders     |   POST /api/orders             |
          |                       |   Host: api.example.com        |
          |                       |   X-Forwarded-Proto: https    |
          |<----------------------|<------------------------------|
~~~

Nếu Spring chỉ nhìn socket nội bộ, nó có thể hiểu scheme là **http**, port là **8080** và host là địa chỉ nội bộ, rồi sinh:

~~~http
HTTP/1.1 201 Created
Location: http://orders-service:8080/api/orders/42
~~~

Link này sai đối với client bên ngoài. Cách sửa ngây thơ là luôn tin bất cứ header **X-Forwarded-Host** hoặc **Forwarded** nào của request. Nhưng attacker có thể tự gửi:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
X-Forwarded-Host: attacker.example.net
X-Forwarded-Proto: https
~~~

Nếu header ấy đi xuyên proxy vào backend mà không được kiểm soát, server có thể tạo **Location** tới domain của attacker, tạo link khôi phục tài khoản sai, nhầm **Origin** khi kiểm CSRF, phân loại IP của client sai hoặc ảnh hưởng redirect OAuth/OIDC. Đây là **host/forwarded-header spoofing**; không chỉ là lỗi trình bày URL.

Bài thuộc chương **Triển khai và vận hành** của module **INTEGRATION_API_REST**: thiết kế REST theo resource/URI/method/status HTTP, contract dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử trong Java/Spring. Trọng tâm là **đưa thông tin public origin vào backend an toàn qua các proxy thực sự tin cậy**, không phải tin mọi header vì ứng dụng nằm sau gateway.

**Mục tiêu:** phân biệt Host, Forwarded và X-Forwarded-*; định nghĩa trust boundary; cấu hình ingress và Spring Boot nhất quán; tạo URL/redirect/cookie đúng public origin; xử lý nhiều proxy; kiểm thử giả mạo header, HTTPS, tenant/security và vận hành khi cấu hình sai.

## 2. Phân biệt địa chỉ mạng, authority và public origin

Một request đi qua proxy có ít nhất bốn khái niệm:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Public origin** | https://api.example.com | Scheme + host + port mà client bên ngoài dùng; cần cho absolute links, redirect và một số security checks. |
| **HTTP Host / :authority** | api.example.com | Authority được client gửi trong HTTP/1.1 hoặc HTTP/2; **không tự động là giá trị đáng tin**. |
| **Remote peer address** | IP của ingress/sidecar | Địa chỉ TCP peer trực tiếp mà backend thấy, không nhất thiết là client IP. |
| **Internal upstream** | http://orders-service:8080 | Địa chỉ mạng backend nội bộ; không nên rò vào URL công khai. |

**Forwarded headers là metadata do proxy mô tả**, không chứng minh danh tính người dùng. AuthN/AuthZ phải dựa credential được xác minh, scopes và quyền từng order, không dựa một mình vào client IP hoặc giá trị host do caller khai báo.

### 2.1. Hai hướng request

- **Inbound**: bên ngoài gọi một URI công khai → proxy định tuyến tới service, có thể đổi scheme/host/prefix.
- **Outbound response**: service phải tạo **Location**, links, callback URL hoặc cookie với ngữ cảnh công khai **đã xác minh**. Những chỗ không cần absolute URL nên ưu tiên **relative references** theo contract để giảm lệ thuộc vào hạ tầng.

Nếu proxy thay đường dẫn, ví dụ ngoài **/shop/api/orders** nhưng backend chỉ thấy **/api/orders**, còn cần quản lý **external path prefix**; không thể sửa scheme/host rồi mặc định path đúng. Tốt nhất thống nhất routing, hoặc cấu hình path prefix chính xác tại ingress được tin cậy và kiểm thử xây URI.

## 3. Header chuẩn Forwarded và các header X-Forwarded-*

### 3.1. Forwarded theo RFC 7239

Header **Forwarded** có các tham số thường gặp:

~~~http
Forwarded: for=203.0.113.10;by=192.0.2.7;proto=https;host=api.example.com
~~~

- **for**: địa chỉ hoặc định danh node bên gửi trước proxy.
- **by**: định danh giao diện proxy nhận request.
- **proto**: scheme phía ngoài mà proxy biết, ví dụ https.
- **host**: authority mà proxy quan sát, ví dụ api.example.com:443.

Một request qua nhiều proxy có thể có danh sách phần tử **ngăn bởi dấu phẩy**:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com,
           for=192.0.2.7;proto=http;host=orders-gateway.internal
~~~

Đây là ví dụ logic hai hop, không khẳng định **mọi proxy đều điền đầy đủ**. Tham số có thể được quote, IPv6 có cú pháp dấu ngoặc kép và ngoặc vuông, phần tử có thể mang định danh ẩn danh/unknown. **Không split tùy tiện theo dấu phẩy/dấu chấm phẩy rồi lấy giá trị đầu tiên**: cú pháp quoted-string cần parser chuẩn, và **header hợp cú pháp vẫn có thể là giả mạo**.

### 3.2. Họ X-Forwarded-* thông dụng

| Header | Ví dụ | Công dụng / cảnh báo |
| --- | --- | --- |
| **X-Forwarded-For** | 203.0.113.10, 192.0.2.7 | Danh sách IP qua proxy; leftmost không nhất thiết đáng tin. |
| **X-Forwarded-Proto** | https | Scheme nhìn từ bên ngoài, quan trọng khi TLS kết thúc ở proxy. |
| **X-Forwarded-Host** | api.example.com | Host gốc; có thể gây host poisoning nếu client kiểm soát. |
| **X-Forwarded-Port** | 443 | Cổng công khai; tránh tạo :8080 trong URL. |
| **X-Forwarded-Prefix** | /shop | Tiền tố URI bên ngoài nếu proxy rewrite path; không phải header chuẩn phổ quát, phụ thuộc framework/proxy. |
| **X-Real-IP** | 203.0.113.10 | Quy ước của một số proxy cho client IP, không có bảo đảm nếu không do trusted hop ghi. |

**Forwarded và X-Forwarded-* có thể cùng tồn tại.** Nếu chúng mâu thuẫn, đừng đoán header nào “đúng hơn” từ request. Chọn **một hợp đồng chuẩn giữa ingress và ứng dụng**, xóa các biến thể không dùng hoặc chuẩn hóa cùng một nguồn trước khi backend nhìn thấy. Framework có thể ưu tiên một họ header khác kỳ vọng; đây phải là kịch bản kiểm thử.

### 3.3. Ví dụ nội bộ HTTPS bị mất dấu khi tới backend

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.10
~~~

Nếu app **chỉ được phép nhận traffic từ ingress đã kiểm soát** và ingress vừa xây lại các header này từ dữ liệu tin cậy, Spring có thể dùng chúng để nhận public origin. Nếu backend còn nhận trực tiếp từ internet, request trên **không đủ đáng tin**, dù các giá trị trông hợp lý.

## 4. Ranh giới tin cậy nằm ở proxy, không nằm trong tên header

~~~mermaid
flowchart LR
    U["Internet / untrusted client"] --> E["Edge proxy: xác minh Host, TLS"]
    E -->|"Overwrite forwarding metadata"| I["Ingress nội bộ: trusted hop"]
    I -->|"Private network / mTLS"| S["Spring Orders API"]
    X["Kẻ tấn công"] -.->|"Không được vào thẳng :8080"| S
~~~

**Nguyên tắc thiết kế:** chỉ các proxy nằm trong danh sách trusted, trên mạng/đường kết nối được bảo vệ, mới được gắn metadata mà app tin. **Trước khi trust, proxy phải xóa hoặc ghi đè header client có thể giả mạo.** Chỉ cấu hình Spring đọc header không tạo được ranh giới này.

### 4.1. Các bước chốt trust boundary

1. **Chặn đường trực tiếp** từ Internet đến backend (firewall, security group, Kubernetes NetworkPolicy/Service exposure, mTLS hoặc cơ chế network tương đương). Không cho request đi vòng qua ingress đã kiểm.
2. Edge kiểm **TLS/SNI và Host/:authority** trên một allowlist domain/route; domain không khớp bị từ chối, không phản chiếu vào absolute links.
3. Tại **hop đầu tiên được tin cậy**, xóa các header Forwarded/X-Forwarded-* nhận từ client, sau đó **ghi đè** bằng dữ liệu mà proxy đã kiểm chứng; nhiều hop nội bộ phải có quy tắc append/normalize thống nhất.
4. Chỉ backend thuộc vùng bảo vệ mới đọc các header chuẩn hóa; app còn có allowlist public origin/redirect destinations cho các tác vụ nhạy cảm.
5. Kiểm thử gửi header giả ngay từ ngoài edge; xác nhận proxy không cho giá trị giả tới backend hoặc không làm thay đổi hành vi.

**Không thể xác định proxy tin cậy chỉ bằng việc request có header Forwarded.** IP của remote peer có thể giúp đánh giá trong mạng được bảo vệ nhưng cũng cần kiểm network boundary, cấu hình thực tế của LB/sidecar và đường đi bất thường.

### 4.2. Chain nhiều proxy và X-Forwarded-For

Ví dụ client **203.0.113.10** tự gửi **X-Forwarded-For: 198.51.100.66**, edge proxy nối thêm IP nó thực sự thấy, rồi ingress tiếp tục nối:

~~~text
Attacker đưa:          198.51.100.66
Edge có thể append:    198.51.100.66, 203.0.113.10
Ingress append:        198.51.100.66, 203.0.113.10, 192.0.2.7
Ứng dụng nhận TCP từ:  192.0.2.8
~~~

Nếu tin **leftmost IP**, ứng dụng có thể tin IP giả **198.51.100.66**. Một cách phân tích dành cho hệ có trust list đúng là bắt đầu từ **peer TCP trực tiếp**, bước ngược qua các hop đã được xác nhận thuộc trusted proxies và lấy **địa chỉ không tin cậy gần nhất** ở bên trái. Độ dài chain, cú pháp IPv6/port và danh sách CIDR phải phù hợp implementation. **Đơn giản hơn và an toàn hơn**: edge đầu tiên loại header client cung cấp và tạo lại chain, các hop sau chỉ append từ peer đã tin.

**Client IP không phải identity:** NAT, VPN, CGNAT, thiết bị di động và load balancer có thể khiến nhiều user chung IP. Rate limiting có thể kết hợp verified user/API key với network signal; không dùng X-Forwarded-For raw làm khóa duy nhất cho phân quyền, audit hoặc bypass MFA.

### 4.3. Sự khác nhau giữa “biết proxy” và “trust mọi proxy”

| Cách cấu hình | Rủi ro |
| --- | --- |
| Backend công khai và bật ForwardedHeaderFilter | Client tự quyết định scheme/host/prefix khi server xây URL. |
| Ingress append vào X-Forwarded-For từ client | Leftmost IP có thể bị attacker gán tùy ý. |
| X-Forwarded-Host lấy nguyên Host bất kỳ | Dễ sinh Location/callback URL trỏ domain lạ. |
| Chỉ trust IP **của proxy trực tiếp**, kiểm CIDR hop phía trước | Có thể suy client IP đúng nếu chain và parser được cấu hình nhất quán. |
| Edge xóa/ghi đè + network deny direct backend + app canonical host | Thu hẹp bề mặt, rõ nguồn dữ liệu tin cậy. |

Nếu TLS kết thúc ở **CDN** còn NGINX tiếp theo chỉ nhận HTTP, dùng **$scheme** của NGINX làm X-Forwarded-Proto sẽ thành **http** dù public site là HTTPS. Phải xác thực nguồn CDN và giữ/thay thế scheme từ nguồn đã xác minh; **không được lấy nguyên header https do bất kỳ client gửi**. Quy tắc này áp dụng tương tự với port, prefix, IP và Host.

## 5. Cấu hình reverse proxy: ghi đè từ một nguồn đã xác minh

### 5.1. Ví dụ NGINX là TLS edge duy nhất

Giả định NGINX **trực tiếp nhận TLS công khai** cho duy nhất domain **api.example.com**, proxy sang Spring tại **orders-service:8080** trên mạng riêng, không có CDN đứng trước. Cấu hình minh họa:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;
    ssl_certificate     /etc/nginx/tls/api.crt;
    ssl_certificate_key /etc/nginx/tls/api.key;

    location / {
        proxy_pass http://orders-service:8080;
        proxy_http_version 1.1;

        # Không dùng giá trị Forwarded do client tự gửi.
        proxy_set_header Forwarded "";
        proxy_set_header Host api.example.com;
        proxy_set_header X-Forwarded-Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Chỉ đúng khi NGINX là edge đầu tiên, TCP peer là client.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Prefix "";
    }
}
~~~

**Phải bổ sung ở hạ tầng thực tế:** certificate/TLS policy, default virtual host **từ chối Host/SNI lạ**, HTTP-to-HTTPS redirect an toàn trên host được phép, giới hạn request size/timeouts, upstream health checks và network deny truy cập trực tiếp backend. **server_name** trong một server block không tự thay thế kiểm tra default host. NGINX bỏ header có giá trị rỗng khi gửi upstream; câu lệnh **Forwarded ""** và **X-Forwarded-Prefix ""** nhằm loại bản do client cung cấp.

Tại edge duy nhất này, **$remote_addr** là peer ngoài mà NGINX trực tiếp nhìn thấy. Nếu có CDN/LB ở trước, giá trị sẽ thường là **IP CDN/LB**, không phải IP người dùng. Không sửa bằng cách tin thẳng X-Forwarded-For của caller; phải cấu hình trusted upstream IP ranges, giải mã chain được kiểm chứng hoặc yêu cầu CDN **ghi đè** header, sau đó chuyển tiếp metadata đã chuẩn hóa.

### 5.2. Trường hợp CDN → load balancer → ingress → app

Trước khi mở tính năng forwarded-header cho Spring, trả lời:

| Câu hỏi triển khai | Điều cần kiểm chứng |
| --- | --- |
| Ai là **TLS terminator công khai**? | Tại CDN, LB hay ingress; **public scheme** lấy từ hop tin cậy nào? |
| Hop nào có quyền ghi **Host/Forwarded/X-Forwarded-***? | Có xóa header do client tự đưa ở trust boundary đầu tiên không? |
| Backend có thể được gọi trực tiếp? | VPC firewall, NetworkPolicy, security group, mTLS hoặc mesh policy. |
| Ai quản lý **trusted proxy IP ranges**? | Quy trình cập nhật khi autoscale/CDN thay ranges, kiểm chéo với địa chỉ thực tế. |
| Có rewrite **prefix** hoặc port? | Mapping public path/port về internal path/port và cách khôi phục. |
| Có nhiều **public host**/tenant? | Domain allowlist/mapping đáng tin, không phản chiếu host tùy ý từ request. |

**X-Forwarded-Proto=https** phải thể hiện scheme mà browser đã dùng trên endpoint công khai, **không phải** chỉ scheme của kết nối LB→NGINX. TLS giữa các hop nội bộ vẫn nên bật khi có yêu cầu bảo vệ mạng và chính sách tổ chức; “đã có TLS tại edge” không tự bảo vệ đoạn bên trong VPC.

### 5.3. Tránh cấu hình vừa dùng Forwarded vừa dùng X-Forwarded-*

Ingress đôi khi gửi cả:

~~~http
Forwarded: proto=http;host=attacker.example.net
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
~~~

Nếu một filter ưu tiên **Forwarded** còn dashboard/người vận hành xem **X-Forwarded-***, hành vi có thể lệch với kỳ vọng. Hãy **xóa Forwarded không dùng**, hoặc chuẩn hóa cả hai họ từ cùng nguồn đã xác minh. Thử trường hợp hai họ mâu thuẫn ở bài test; không thể lấy một response đúng trên happy path làm bằng chứng trust boundary vững.

## 6. Spring Boot: NATIVE, FRAMEWORK và NONE

Spring Boot cung cấp thuộc tính **server.forward-headers-strategy**. Trên stack và container tương thích, ba lựa chọn diễn giải:

| Giá trị | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| **none** | Không tự khôi phục public origin từ forwarded headers. | Hợp lý nếu app nhận TLS trực tiếp hoặc tuyệt đối không muốn trust các header. |
| **native** | Dùng khả năng của servlet container/server (ví dụ Tomcat RemoteIpValve). | Các tùy chọn **trusted/internal proxies, protocol header** phụ thuộc container và phải kiểm thử. |
| **framework** | Dùng khả năng của Spring Framework như **ForwardedHeaderFilter** (Servlet) hoặc transformer tương đương (reactive). | Không tự kiểm proxy đáng tin qua mạng; **phải sanitize ở ingress**. |

Ví dụ Spring Boot 3 / Spring MVC phía sau ingress đã thiết lập ở phần 5:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

app:
  public-base-url: https://api.example.com/
~~~

**framework không có nghĩa “Spring đã xác thực IP của mọi proxy”.** Nó giúp biến các header đã được tin cậy thành những giá trị như **request scheme, server name/port, request.isSecure và link builders**. Bật thuộc tính này khi client còn truy cập được backend và tự đặt header là một rủi ro bảo mật. App container nên chỉ mở port nội bộ.

Với **native**, kiểm tài liệu của server đang dùng và cấu hình trust list thực tế thay vì mặc định mọi proxy trong private network đều đáng tin. Với **none**, các header có thể vẫn xuất hiện trong raw request headers, nhưng Spring không nên dùng chúng để tạo origin một cách tự động; custom code tự đọc header vẫn có thể gây lỗi nếu không kiểm nguồn.

### 6.1. ForwardedHeaderFilter trên Servlet: đặt đúng thứ tự

Nếu ứng dụng tự đăng ký filter thay vì dùng Boot auto configuration, Spring MVC có **ForwardedHeaderFilter**:

~~~java
import org.springframework.web.filter.ForwardedHeaderFilter;

ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
// Khi được đăng ký ở pipeline, filter điều chỉnh request/response
// dựa trên Forwarded / X-Forwarded-*.
~~~

Đây là đoạn minh họa API chứ **không yêu cầu tạo bean thứ hai** khi Boot đã tự cấu hình. Filter phải chạy đủ sớm trước thành phần cần scheme/host, gồm redirect/URL building và các security decisions phụ thuộc request context. **Không cấu hình cả native và framework processing đồng thời tùy tiện**, tránh xử lý hai lần hoặc chọn header precedence khó đoán.

Nếu app **không tin forwarded headers**, filter có tùy chọn **removeOnly** để **loại header** mà không sử dụng nó dựng URL:

~~~java
ForwardedHeaderFilter removeUntrusted = new ForwardedHeaderFilter();
removeUntrusted.setRemoveOnly(true);
~~~

Biện pháp remove-only có ích khi ứng dụng không cần tái tạo public origin từ request; **không thay thế ingress security**. Phải lựa chọn rõ: **trust/sanitize từ proxy**, hoặc **strip/ignore** và dùng canonical URL cấu hình sẵn. Dùng framework filter cùng raw header application code là hai đường xử lý khác nhau; audit cả hai.

### 6.2. Spring WebFlux và reactive server

Với WebFlux, khái niệm tương đương là **ForwardedHeaderTransformer** tại server adapter. Boot strategy **framework** có thể cấu hình xử lý phù hợp stack. Dù Servlet hay WebFlux, **security boundary vẫn là ingress và network**, không phải class transformer. Nếu có gateway/sidecar rewrite path, kiểm router/prefix và generated URLs trên transport đang chạy, không dựa vào unit test của một class.

### 6.3. Không suy diễn client IP từ Servlet API khi chưa rõ filter

**HttpServletRequest.getRemoteAddr()** ban đầu là peer trực tiếp. Sau một số xử lý native/proxy-aware, API có thể được thay đổi theo container; đừng trộn nó với việc tự lấy **X-Forwarded-For** từ request. Quy ước một nguồn **verified client IP** ở ingress và log/chuyển tiếp có kiểm soát. Nếu rate limit theo IP, phải test cả XFF giả, IPv6, nhiều hop, NAT và proxy ranges.

## 7. Public URL: canonical config hay request-derived URL?

### 7.1. Chọn URI tương đối khi hợp đồng cho phép

Với **201 Created**, header **Location** có thể là relative reference:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json

{"itemId":"sku-42"}

HTTP/1.1 201 Created
Location: /api/orders/42
Content-Type: application/json

{"id":"42","status":"CREATED"}
~~~

Ví dụ đặt **request và response liên tiếp** để mô tả contract, không phải một HTTP message duy nhất. Client giải quyết Location tương đối theo URI request. Nó tránh nhúng **http**, **:8080** hoặc host nội bộ vào response, đồng thời không phản chiếu host do caller tự đặt. Cần kiểm client/SDK/OpenAPI có xử lý relative Location và public path prefix có được bảo toàn. Nếu contract yêu cầu absolute URI, chọn nguồn public origin có bảo đảm rõ ràng.

### 7.2. Java/Spring tạo Location không phụ thuộc header raw

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record NewOrder(UUID id, String status) {}

interface OrderCreateService {
    NewOrder createAuthorized();
}

@RestController
@RequestMapping("/api/orders")
class OrderCreateController {
    private final OrderCreateService service;

    OrderCreateController(OrderCreateService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<NewOrder> create() {
        NewOrder order = service.createAuthorized();
        URI location = URI.create("/api/orders/" + order.id());
        return ResponseEntity.created(location).body(order);
    }
}
~~~

Mẫu chỉ minh họa Location; **createAuthorized** trong production phải kiểm authentication, tenant/object authorization, input và idempotency/transaction theo contract. Một số lớp servlet, gateway hoặc proxy có thể xử lý lại Location; **kiểm response cuối cùng từ bên ngoài edge**, không chỉ response ở MockMvc.

### 7.3. Absolute URL nhạy cảm nên dùng cấu hình public base URL

**OAuth/OIDC redirect_uri**, callback thanh toán, link email verification, password reset và signed URL thường cần absolute URL. **Không dựng chúng từ Host hoặc X-Forwarded-Host do request tùy ý khai báo**. Ví dụ Spring Boot:

~~~yaml
app:
  public-base-url: https://api.example.com/
~~~

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class PublicOrderLinks {
    private final URI publicBase;

    PublicOrderLinks(
            @Value("${app.public-base-url}") URI publicBase) {
        if (!"https".equalsIgnoreCase(publicBase.getScheme())
                || publicBase.getHost() == null
                || publicBase.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Public base URL must be an approved HTTPS origin");
        }
        this.publicBase = publicBase;
    }

    URI order(UUID id) {
        return publicBase.resolve("api/orders/" + id);
    }
}
~~~

**Trong production**, host của publicBase phải nằm trong **allowlist/registry cấu hình đáng tin**, không chỉ kiểm HTTPS như code tối giản; URI cần có dấu **/** cuối khi dùng **resolve** với path tương đối. Mẫu giả định API ở root domain, không có public prefix. Với multi-tenant, ánh xạ tenant → allowed origin từ **registry đã xác minh**, không từ Host/query tùy ý. OAuth **redirect_uri phải khớp URI đã đăng ký** ở Authorization Server; không tạo một callback tùy ý dựa trên header.

### 7.4. Khi nào request-derived URL phù hợp?

Spring **ServletUriComponentsBuilder** và API tương tự có thể tạo absolute URI từ request đã được xử lý ForwardedHeaderFilter. Chỉ dùng nếu **backend không thể bị gọi trực tiếp**, ingress đã sanitize/overwrite headers, public hosts có allowlist, và đã kiểm đủ scheme/port/prefix. Với link nhạy cảm có một canonical domain rõ ràng, cấu hình tường minh thường an toàn, dễ kiểm tra và ít phụ thuộc nhiều hop hơn.

## 8. Những điểm bảo mật bị ảnh hưởng bởi public origin sai

| Thành phần | Khi forwarded metadata bị giả/sai | Kiểm soát đúng |
| --- | --- | --- |
| **Location/Link** | Sinh URL http/:8080 hoặc host attacker. | Relative URI/canonical public base, Host allowlist. |
| **OAuth/OIDC callback** | Tạo redirect_uri sai host/port hoặc dẫn tới domain khác. | Redirect URI đăng ký chính xác; không lấy raw Host. |
| **Password reset/email link** | Link nhạy cảm trỏ domain do attacker chọn. | Cấu hình canonical origin, không phản chiếu header. |
| **Secure cookie** | request.isSecure sai có thể khiến code tùy biến chọn sai cookie flag. | Đặt Secure/HttpOnly/SameSite tường minh, TLS edge đúng. |
| **HSTS/redirect** | Vòng lặp HTTPS redirect hoặc URL bị downgrade. | TLS/redirect policy tại trusted edge, HSTS trên domain đủ điều kiện. |
| **CSRF Origin checking** | Server so Origin với base URL dựng từ Host giả. | Allowlist external origins đã đăng ký; proxy normalize. |
| **CORS** | CORS allowlist tự phản chiếu Origin/Host, mở nhầm quyền. | Danh sách origin rõ ràng, không wildcard với credentials. |
| **IP rate limit/audit** | Attacker tự chọn IP qua X-Forwarded-For. | Verified peer/client IP theo chain có trust list. |
| **Tenant routing** | Host tùy ý làm app chọn tenant/branding khác. | Registry domain → tenant, xác thực quyền trên resource. |
| **HTTP cache/CDN** | Cache poisoning qua Host, variant/scheme/prefix sai. | Cache key/Host allowlist/Vary/tenant scope; bảo vệ dữ liệu riêng. |

### 8.1. OAuth callback và redirect không được dùng request Host như nguồn tin cậy

Ví dụ lỗi cần tránh: client gửi Host giả, app tạo password-reset link hoặc **redirect_uri** bằng cách nối request.getScheme(), request.getServerName() rồi email cho người dùng. Dù proxy có thể giúp tái dựng đúng URL, đường dữ liệu đó vẫn cần **trusted ingress**. Nếu hệ thống chỉ có một domain công khai, dùng **app.public-base-url** đã phê duyệt cho các link này sẽ giảm đáng kể nguy cơ host header poisoning.

Nếu có endpoint redirect có tham số **returnUrl/next**, phải kiểm redirect destination riêng (allowlist, path nội bộ, không open redirect); forwarded metadata hợp lệ không tự biến tham số next thành an toàn. Với **301/302/307/308**, chú ý semantics HTTP method khi client follow redirect: chuyển POST sang URL khác có thể gây lộ body/credential hoặc lặp side effect. Không dùng redirect để né việc sửa public origin và không chuyển Bearer token sang host ngoài trust boundary.

### 8.2. Cookie/session, CSRF và HTTPS offload

Proxy có thể kết thúc HTTPS, backend vẫn nhận HTTP nội bộ. Để bảo vệ browser session, cấu hình cookie **Secure**, **HttpOnly**, **SameSite** theo luồng và chỉ phục vụ public origin qua HTTPS. Khi TLS offload, **server.servlet.session.cookie.secure=true** có thể cần thiết để không phụ thuộc vào suy luận request.isSecure từ socket nội bộ:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

**SameSite không thay CSRF token** khi browser tự gửi cookie. Cookie flags không chữa open redirect/host poisoning. Nếu ứng dụng sử dụng Spring Security resource server **Bearer-only**, không tự động đổi thiết kế authentication sang cookie chỉ vì proxy thêm X-Forwarded-Proto; hai cơ chế có rủi ro khác nhau.

### 8.3. HTTP cache, canonical origin và private data

Public origin sai có thể làm cache key, Location/Link hoặc HATEOAS navigation sai; với API theo tenant, dữ liệu nhạy cảm không được cache chung chỉ dựa vào path nếu quyền/host khác nhau. HTTP **ETag/Cache-Control/Vary** và CDN rules phải được cấu hình nhất quán với allowed host, Authorization, cookie và tenant. Không dùng Host như một bằng chứng sở hữu tenant khi chưa kiểm registry; đừng trả **304 Not Modified** cho representation của tenant khác.

### 8.4. Ghi log đúng nhưng không để lộ dữ liệu

Ở edge nên có **request ID, virtual host đã xác minh, peer IP, verified client IP theo policy, TLS protocol, upstream, duration và status**. Ứng dụng ghi **route template**, status, trace ID, latency; chỉ ghi client IP khi được lấy từ nguồn đã xác minh và theo chính sách riêng tư. **Không ghi trọn Authorization, cookie, tokens, payload cá nhân hoặc nguyên chuỗi Forwarded không đáng tin** vào logs/metrics.

Header có thể dài, chứa newline/quote bất thường hoặc nhiều hop; limit kích thước header ở ingress, dùng structured logging và tránh injection vào log. Với metrics, **không dùng URL/Host raw/địa chỉ IP làm high-cardinality labels**.

## 9. Kiểm thử Spring: nhận đúng forwarded metadata nhưng không nhầm đó là trust

### 9.1. MockMvc chỉ kiểm parser/filter, không xác minh proxy ngoài mạng

Mục tiêu của unit/MockMvc test là chứng minh **ForwardedHeaderFilter** dùng metadata để khôi phục public scheme/host/port theo contract. Ví dụ test-only controller:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
class PublicUrlProbeController {
    // Chỉ dùng trong test fixture; không công bố endpoint debug ở production.
    @GetMapping("/_test/public-link")
    String publicLink(HttpServletRequest request) {
        return ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/orders/42")
                .build()
                .toUriString();
    }
}
~~~

Với Spring MVC Test, đăng ký filter một cách **tường minh**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.filter.ForwardedHeaderFilter;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class ForwardedHeaderFilterTest {
    private final PublicUrlProbeController controller =
            new PublicUrlProbeController();

    @Test
    void trustedFixtureReconstructsHttpsPublicOrigin() throws Exception {
        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(controller)
                .addFilters(new ForwardedHeaderFilter())
                .build();

        mvc.perform(get("/_test/public-link")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "api.example.com")
                .header("X-Forwarded-Port", "443"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "https://api.example.com/api/orders/42"));
    }

    @Test
    void withoutFilterDoesNotUseUntrustedHeaders() throws Exception {
        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(controller)
                .build();

        mvc.perform(get("/_test/public-link")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "attacker.example.net"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    "http://localhost/api/orders/42"));
    }
}
~~~

Đây là test **chức năng xử lý header**, không phải test chống spoofing. Ở test thứ nhất, nếu gọi trực tiếp MockMvc và đưa **host của attacker**, filter cũng có thể dựng URL attacker: vì bản thân filter **không tự chứng minh người gửi header là trusted proxy**. Chỉ có test **qua edge/network thật** (phần 10) mới chứng minh request bên ngoài không điều khiển được giá trị.

Với **server.forward-headers-strategy=framework** ở Boot integration test, filter có thể được Boot đăng ký tự động, nên **không thêm thủ công thêm một filter** rồi tạo double processing; khẳng định đường cấu hình thực tế và thứ tự filter bằng test context riêng. Nếu dùng strategy **native**, cần test với container/remote-IP configuration thật, vì standalone MockMvc không mô phỏng Tomcat RemoteIpValve.

### 9.2. Kiểm tra Location được tạo độc lập với host tùy ý

Với **OrderCreateController** phần 7, mock một order UUID cố định và thử hai request:

~~~text
POST /api/orders, Host: api.example.com
POST /api/orders, Host: attacker.example.net, X-Forwarded-Host: attacker.example.net

Mong đợi ở controller tạo relative Location:
  201 Created
  Location: /api/orders/<same-order-id>
~~~

Lưu ý mã Java **service fixture phải trả đúng cùng ID** và test cần đăng ký authentication/CSRF theo security chain nếu endpoint được bảo vệ. Test này chứng minh controller **không tự phụ thuộc Host**, nhưng **không thay** test ingress từ chối Host lạ. Khi Spring/proxy thực tế rewrite Location thành absolute, test cuối qua edge phải kiểm kết quả đó nữa.

## 10. Kiểm thử tích hợp qua proxy: chống giả mạo thực sự

### 10.1. Ma trận kiểm thử ở HTTP boundary

| ID | Request/giao thức | Kỳ vọng có thể kiểm |
| --- | --- | --- |
| P01 | Gọi HTTPS public host chuẩn | Không redirect sang http, host nội bộ hoặc port 8080. |
| P02 | Client gắn **Forwarded: host=attacker.example.net;proto=http** | Ingress loại/ghi đè; Location/callback/cookie vẫn theo chính sách. |
| P03 | Client gắn **X-Forwarded-Host/Proto/Port** tùy ý | Không tạo link attacker; backend chỉ nhận metadata ingress đã xác minh. |
| P04 | Client giả **X-Forwarded-For: 127.0.0.1** | Không được xem là request localhost, không bypass quota/allowlist. |
| P05 | **Host/:authority lạ** hoặc mismatch TLS SNI | Từ chối ở edge hoặc trả lỗi host theo policy (ví dụ 400/421); không xử lý nghiệp vụ. |
| P06 | Truy cập thẳng **orders-service:8080** từ mạng ngoài | Không kết nối được do network boundary, không chỉ 403 ở controller. |
| P07 | Hai họ **Forwarded** và **X-Forwarded-*** xung đột | Chỉ nguồn canonical đã chọn ảnh hưởng app; không có ambiguity. |
| P08 | Chain nhiều proxy, IPv4/IPv6, đổi node/CDN ranges | Verified client IP không lấy entry giả mạo, không rò host/port nội bộ. |
| P09 | External prefix **/shop** rewrite thành path nội bộ | Absolute Link/Location và routing vẫn đúng public prefix. |
| P10 | TLS edge đang HTTPS, hop vào app HTTP | Secure cookies, HSTS/redirect policy, scheme và Location công khai vẫn HTTPS. |
| P11 | OAuth/OIDC callback hoặc password-reset link | Đúng URI đã đăng ký/canonical, không lấy host raw từ request. |
| P12 | Host/tenant khác được phép và Host lạ | Chỉ domain có mapping trusted được phục vụ; không rò data tenant. |
| P13 | Error handler 401/403/404/500 và CORS preflight | Không sinh absolute Location/Link sai, không nới CORS vì proxy header. |

**Quan trọng:** đừng chỉ test response của backend qua localhost:8080. Hệ thống có thể **đúng ở MVC nhưng sai sau LB hoặc CDN**, và ngược lại. Dùng URL/port/TLS/path mà client thực dùng, ghi lại topology và các header đã qua ingress bằng logging hạn chế trên staging.

### 10.2. Ví dụ curl tạo header giả trên staging được phép

~~~bash
curl -i 'https://api.example.com/api/orders/42' \
  -H 'Forwarded: for=127.0.0.1;proto=http;host=attacker.example.net' \
  -H 'X-Forwarded-Host: attacker.example.net' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Port: 8080' \
  -H 'X-Forwarded-For: 127.0.0.1'
~~~

Tùy endpoint, request không có Bearer có thể trả **401**, không nhất thiết 200. Kiểm cả **header HTTP, audit trace/verified host và không có side effect**. Không dùng curl -k bỏ TLS verification làm phương pháp kiểm chứng TLS. Không gửi token production vào log/terminal history; kịch bản chỉ chạy với dữ liệu/đường dẫn môi trường kiểm thử được phép.

Một phép thử khác là gọi domain **không nằm trong allowlist** với Host/:authority lạ. Kết quả cần phụ thuộc hạ tầng và certificate/SNI; không được “pass” chỉ vì service trả 200 nhưng Location đã chứa host tùy ý. Kiểm soát **Host tại edge** và **origin tại app** là hai kiểm soát bổ sung.

### 10.3. Kiểm tra hành vi khi client IP đi qua nhiều hop

Trong staging, tạo cả request:

- Không có X-Forwarded-For từ client, qua edge bình thường.
- Có X-Forwarded-For giả từ client nhưng vẫn qua edge; verified IP phải không đổi.
- Qua CDN/LB/ingress theo topology thật; IP nhận diện phải nằm đúng vị trí trong trusted chain.
- Qua route không được phép bypass CDN hoặc trực tiếp service; phải bị chặn.

Nếu công cụ load test tạo nhiều kết nối từ cùng NAT, **không suy ra user identity chỉ từ IP**. Đặt rate limit ưu tiên principal/API key đã xác minh và dùng IP đã chuẩn hóa như tín hiệu phụ theo policy.

## 11. Chẩn đoán sự cố triển khai

| Triệu chứng | Giả thuyết cần kiểm | Hướng xác minh |
| --- | --- | --- |
| Redirect từ HTTPS sang HTTP | TLS offload, X-Forwarded-Proto sai hoặc Boot không xử lý header. | Theo trace qua edge → backend; đối chiếu public URL và request.getScheme. |
| Redirect loop HTTP ↔ HTTPS | Edge và app cùng redirect nhưng hiểu scheme khác nhau. | Kiểm 301/302/307/308, forwarded strategy, HSTS và hop TLS. |
| Location chứa :8080 hoặc host nội bộ | Host/port upstream bị dùng thay public authority. | Kiểm header overwrite, Boot strategy, URI builder/absolute URL. |
| OAuth login báo redirect_uri mismatch | Public scheme/host/prefix sai hoặc callback URI khác config của AS. | So chính xác callback được gửi với registered redirect URI. |
| Cookie session không gửi sau login | Secure/SameSite/Domain/Path, HTTPS, cross-site/third-party restrictions. | Browser DevTools + Set-Cookie (giữ bí mật session); kiểm Origin/CORS riêng. |
| CORS hoặc CSRF sai bất thường sau proxy mới | Origin so với scheme/host bị tái dựng sai, CORS allowlist không khớp. | Preflight + actual từ browser, proxy trust/header handling, cookie path. |
| Tất cả clients bị ghi thành IP gateway | Proxy chưa chuyển IP đúng hoặc app chỉ thấy immediate peer. | Kiểm ingress logs, trusted proxy config, XFF normalization. |
| Có client được xem như 127.0.0.1 | App tin raw XFF/Forwarded từ người ngoài. | Thử spoof trên staging và rà allowlist/remote-IP parser. |
| Link mất prefix /shop | Proxy rewrite path, thiếu X-Forwarded-Prefix hoặc builder không biết external context. | So URL qua edge và internal route, tránh tin prefix từ client. |

### 11.1. Quy trình điều tra không làm lộ secrets

1. **Ghi topology** và công khai rõ điểm TLS termination, IP của từng hop và đường internal/external.
2. Đối chiếu **public request URL** với URL backend thực nhận; dùng request ID/trace ID thay vì trích toàn bộ cookie/Authorization.
3. Kiểm **proxy header policy**: xóa/ghi đè/append, Host allowlist, chain và network exposure.
4. Kiểm **Spring forwarding strategy**, phiên bản container/filter, cùng cách ứng dụng tự tạo absolute URI.
5. Làm **negative test** từ phía client giả Forwarded/Host/XFF, không chỉ positive test public HTTPS.
6. Thử lại sau thay đổi với OAuth callback, Set-Cookie flags, CORS/CSRF và Location; giám sát 3xx/4xx tăng đột biến.

Đừng “chữa redirect loop” bằng cách tắt HTTPS/HSTS hoặc tin mọi Forwarded headers. Đó là thay lỗi vận hành bằng lỗ hổng bảo mật. Giữ cách rollback cấu hình ingress nếu thay đổi ảnh hưởng nhiều API cùng lúc.

## 12. Public server URL trong OpenAPI và quy trình rollout

Hợp đồng API cũng phải công bố **địa chỉ công khai**, không phải upstream port nội bộ:

~~~yaml
openapi: 3.1.0
info:
  title: Orders REST API
  version: 1.0.0
servers:
  - url: https://api.example.com
    description: Public production origin
paths:
  /api/orders:
    post:
      operationId: createOrder
      responses:
        '201':
          description: Đơn đã được tạo
          headers:
            Location:
              description: URI tới order mới
              schema:
                type: string
                format: uri-reference
        '400':
          description: Yêu cầu không hợp lệ
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
~~~

Đây là **mảnh hợp đồng minh họa**, cần schema/security scheme/requestBody trong OpenAPI production đầy đủ. **servers.url** nên lấy từ cấu hình release đã phê duyệt, không sinh từ Host/X-Forwarded-Host tùy ý tại request. Với staging, công bố URL staging riêng. Nếu API được mount tại external prefix, OpenAPI servers/path phải thống nhất để SDK không ghép path hai lần hoặc bỏ prefix. **format: uri-reference** cho phép Location là relative reference; không ép mọi Location phải absolute.

### 12.1. Rollout thay đổi forwarding không được chỉ dựa vào unit test

Một quy trình triển khai an toàn:

1. **Inventory các proxy**: edge/CDN/LB/ingress/mesh, TLS termination, cách từng hop xử lý Host, Forwarded và XFF.
2. **Chốt policy**: allowed public hosts/schemes/ports, canonical base URI, trusted proxy ranges, header duy nhất được truyền tới backend.
3. **Khóa đường bypass**: bảo vệ trực tiếp port backend; kiểm network policy bằng thử truy cập từ vùng ngoài thay vì chỉ xem cấu hình YAML.
4. **Triển khai ingress sanitation trước**: xóa header do client gửi, normalize từ dữ liệu đã xác minh; không bật app trust khi edge chưa sẵn sàng.
5. **Bật Spring strategy** thích hợp với servlet/reactive runtime, bảo đảm không double-process; kiểm response cuối qua edge.
6. **Canary/so sánh**: kiểm HTTPS/Location, OAuth callbacks, cookie/CORS/CSRF, redirects 3xx, error rates 4xx/5xx, tracing; có cách rollback.

Nếu một service chỉ nhận traffic nội bộ từ **nhiều** ingress khác nhau, mỗi ingress phải tuân thủ cùng policy. Một ingress “tạm thời” nhận header client raw có thể mở lại lỗ hổng cho cả application dù các ingress chính đã cấu hình đúng.

## 13. Bài tập: CDN, NGINX và link khôi phục mật khẩu sai domain

**Tình huống:** người dùng gọi **https://api.example.com** qua CDN TLS edge, sau đó đến NGINX qua HTTP nội bộ rồi đến Spring Boot :8080. NGINX đang dùng:

~~~nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $http_x_forwarded_host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
~~~

Spring Boot bật **server.forward-headers-strategy=framework**. Đội web nhận thấy redirect URI có **http://**, và một email reset mật khẩu từng chứa link tới domain lạ. Một rule rate limit lấy **phần tử đầu tiên** của X-Forwarded-For làm client IP. Admin muốn cho phép gọi trực tiếp port 8080 “để dễ debug”.

**Yêu cầu:** (1) Chỉ ra ít nhất năm vấn đề/rủi ro. (2) Vẽ trust boundary và nêu hop nào được quyền xây forwarded metadata. (3) Chọn cách xác định public proto, host và client IP khi CDN đứng trước NGINX. (4) Sửa cách sinh reset link và Location. (5) Nêu bốn negative tests có thể tự động hóa tại staging. (6) Quyết định có mở port 8080 ra Internet không, và vì sao.

**Hướng giải:**

- **$scheme ở NGINX** là http vì nhận từ CDN nội bộ; nó **không phải public scheme**. Lấy HTTPS từ CDN tin cậy theo policy chặt hoặc cấu hình canonical scheme được bảo đảm.
- **$http_x_forwarded_host** phản chiếu header gửi tới NGINX, có thể do client kiểm soát nếu CDN không sanitize. Chỉ dùng host **đã allowlist và chuẩn hóa**, ưu tiên cấu hình api.example.com khi chỉ có một domain.
- **$proxy_add_x_forwarded_for** có thể nối vào XFF giả do client đưa; lấy leftmost làm IP có thể bị spoof. Bắt đầu trust boundary ở CDN và định nghĩa cách CDN overwrite, NGINX xác minh nguồn CDN, app chỉ nhận metadata sạch.
- Email reset **không** dựng link từ raw Host/Forwarded: dùng **canonical public-base-url** hoặc tenant-domain registry đáng tin. Với **201 Location**, dùng relative URI khi phù hợp; với absolute Link, kiểm HTTPS, port, prefix.
- **Không** mở port 8080 công khai: sẽ bypass edge Host/TLS/header sanitation và khiến framework trust dữ liệu do client tự đặt.
- Negative tests: giả **Forwarded/XFH** để kiểm Location/link; giả **XFF=127.0.0.1** để kiểm rate limit; gọi Host/SNI lạ; thử truy cập thẳng backend; kiểm HTTPS callback qua toàn chuỗi; thử mâu thuẫn Forwarded và X-Forwarded-*.

**Bài tập mở rộng:** giả sử public API được phục vụ ở **https://api.example.com/shop** nhưng Spring chỉ thấy **/api/orders**. Hãy thiết kế mapping prefix và test Location, OAuth callback, OpenAPI servers/path để tránh tạo **/shop/shop/api/orders** hoặc bỏ **/shop**. Không cho phép client tự định nghĩa X-Forwarded-Prefix.

## 14. Checklist phát hành và kết luận

- [ ] Đã vẽ chính xác **client → CDN/LB → ingress/mesh → Spring**, biết TLS kết thúc ở đâu.
- [ ] **Backend không truy cập trực tiếp** từ vùng không tin cậy; kiểm firewall/NetworkPolicy/mTLS thực tế.
- [ ] Edge **xóa hoặc ghi đè** Forwarded/X-Forwarded-*, không nhận raw client values làm metadata tin cậy.
- [ ] **Host/:authority, SNI, scheme, port và prefix** có policy allowlist/mapping rõ.
- [ ] Nhiều proxy có **trusted hop/CIDR policy**, không mặc định tin XFF leftmost hoặc X-Real-IP raw.
- [ ] Spring Boot chọn **none/native/framework** có chủ đích; test filter order, tránh double processing.
- [ ] **201 Location, 3xx redirect, Link, OpenAPI servers** phản ánh public URL, không rò http/:8080.
- [ ] OAuth/OIDC callback, reset link, signed URL lấy từ **canonical origin** đáng tin và kiểm exact destination.
- [ ] Cookie session được **Secure/HttpOnly/SameSite**, CSRF/CORS không lấy Host giả làm căn cứ.
- [ ] Rate limit/audit dùng **verified client IP và identity**, không tin client-supplied XFF.
- [ ] Negative tests giả Forwarded/XFH/XFP/XFF, Host/SNI lạ, multi-hop, path rewrite và backend bypass.
- [ ] Canary/rollback theo dõi redirect loops, 401/403, lỗi login, host poisoning và cross-tenant data.

**Kết luận:** Forwarded headers giải quyết khoảng cách giữa **URI công khai** và **kết nối nội bộ của ứng dụng**, nhưng **header không mang sẵn độ tin cậy**. Ranh giới an toàn bắt đầu từ **edge xác minh Host/TLS và ghi đè metadata**, tiếp tục bằng **network isolation**, rồi mới đến **Spring xử lý forwarding** và cách ứng dụng sinh URI. Khi cần link tuyệt đối nhạy cảm, cấu hình canonical origin đáng tin thường rõ hơn việc suy ra từ request. Kiểm thử phải đi **qua proxy thật và với header giả mạo**, không chỉ nhìn một URL HTTPS đúng trong unit test.
