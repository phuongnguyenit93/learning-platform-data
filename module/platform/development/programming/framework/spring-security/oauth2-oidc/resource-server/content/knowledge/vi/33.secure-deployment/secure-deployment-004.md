# Không tin header do gateway hoặc proxy chuyển tiếp nếu chưa bảo vệ nguồn

Khi một ứng dụng Spring Security Resource Server chạy phía sau load balancer, ingress controller, API gateway hoặc reverse proxy, request mà ứng dụng nhận được có thể khác request mà client gửi ban đầu. Proxy có thể kết thúc TLS, đổi host/port, rewrite path và thay đổi địa chỉ remote. Để ứng dụng biết thông tin công khai ban đầu, proxy thường thêm các header như **Forwarded**, **X-Forwarded-For**, **X-Forwarded-Host**, **X-Forwarded-Proto**, **X-Forwarded-Port** hoặc **X-Forwarded-Prefix**.

Những header này hữu ích cho việc tạo redirect, dựng absolute URL, ghi nhận client IP và khôi phục public request URI. Nhưng chúng vẫn là **HTTP headers**. Nếu client có thể tự gửi giá trị và proxy chuyển tiếp nguyên vẹn, attacker có thể khiến ứng dụng tin một host, scheme, IP hoặc path giả.

Nguyên tắc an toàn là: **chỉ tin forwarded metadata được ghi đè hoặc tạo bởi proxy thuộc trust boundary của hệ thống, trên một kết nối backend chỉ proxy được phép sử dụng**. Spring Framework có thể đọc và áp dụng các header này, nhưng bản thân ForwardedHeaderFilter hoặc ForwardedHeaderTransformer không xác minh ai đã gửi chúng.

Bài học trình bày trust boundary giữa client, proxy và Resource Server; cách cấu hình proxy để xóa/ghi đè header đầu vào; cách giới hạn nguồn kết nối; hỗ trợ trong Spring Boot, Servlet và WebFlux; các rủi ro khi dùng sai host/proto/client IP/path; và cách kiểm thử qua ingress thật.

## 1. Forwarded headers là gì?

Khi request đi qua proxy, server phía sau thường chỉ nhìn thấy kết nối từ proxy. Ví dụ:

~~~text
Client
  |
  | HTTPS https://api.example.com/orders
  v
Load balancer / API gateway
  |
  | HTTP http://orders-service:8080/orders
  v
Spring Resource Server
~~~

Ứng dụng phía sau nhìn thấy remote peer là load balancer, scheme có thể là HTTP và host có thể là hostname nội bộ. Proxy có thể chuyển tiếp thông tin ban đầu bằng headers.

Hai nhóm phổ biến:

| Header | Ý nghĩa |
|---|---|
| **Forwarded** | Header chuẩn hóa theo RFC 7239, có thể chứa for, by, host, proto |
| **X-Forwarded-For** | Địa chỉ client và/hoặc chuỗi proxy theo quy ước triển khai |
| **X-Forwarded-Host** | Host công khai ban đầu |
| **X-Forwarded-Proto** | Scheme ban đầu, thường http hoặc https |
| **X-Forwarded-Port** | Port công khai ban đầu |
| **X-Forwarded-Prefix** | Prefix path công khai khi proxy rewrite path |
| **X-Forwarded-Ssl** | Một quy ước cũ biểu diễn trạng thái TLS |

Ví dụ RFC 7239:

~~~http
Forwarded: for=192.0.2.60;proto=https;host=api.example.com
~~~

Ví dụ X-Forwarded:

~~~http
X-Forwarded-For: 192.0.2.60
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

Các header này giúp ứng dụng dựng lại request từ góc nhìn client. Chúng không tự chứng minh địa chỉ IP hoặc host được ghi trong đó là thật.

### 1.1. Header có thể đến từ client

Một client có thể gửi trực tiếp:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Forwarded: for=127.0.0.1;proto=https;host=admin.internal
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: admin.internal
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /admin
~~~

Nếu gateway chỉ chuyển tiếp các header này, ứng dụng phía sau có thể hiểu sai:

- Client IP là 127.0.0.1.
- Public host là admin.internal.
- Request ban đầu dùng HTTPS.
- Public path có prefix /admin.

Kẻ tấn công không cần chiếm gateway. Chỉ cần gateway không xóa hoặc ghi đè các header do client gửi là đủ để đưa dữ liệu giả vào hệ thống.

### 1.2. Nhiều proxy tạo thành một chuỗi

Một hệ thống có thể có:

~~~text
Client -> CDN -> Load balancer -> Ingress -> Application
~~~

Mỗi proxy có thể thêm hoặc cập nhật forwarded metadata. Chuỗi IP có thể chứa nhiều phần tử. Không được mặc định phần tử đầu tiên hoặc cuối cùng luôn là client thật; phải hiểu chính xác proxy nào được tin và proxy nào ghi thêm phần tử nào.

RFC 7239 cảnh báo nội dung Forwarded có thể bị sửa bởi mọi node trên đường tới server, kể cả client. Danh sách proxy đáng tin chỉ giúp xác định những hop do hệ thống kiểm soát; các phần tử trước proxy tin cậy vẫn có thể không đáng tin.

## 2. Trust boundary phải nằm ở đâu?

Một kiến trúc an toàn có thể biểu diễn:

~~~mermaid
flowchart LR
    C[Internet client<br/>headers không tin cậy] --> E[Edge proxy<br/>xóa và ghi đè headers]
    E -->|TLS/mTLS + network allowlist| A[Application ingress]
    A --> S[Spring Resource Server]
    S --> V[SecurityContext và authorization]
~~~

Edge proxy là điểm đầu tiên thuộc quyền kiểm soát của tổ chức. Tại đây, hệ thống phải:

1. Nhận request từ client.
2. Loại bỏ forwarded headers do client tự gửi.
3. Kiểm tra Host/public domain theo danh sách được phép.
4. Tạo forwarded metadata từ kết nối thực tế và cấu hình proxy.
5. Gửi request tới backend qua một đường kết nối được bảo vệ.

Backend chỉ nhận traffic từ proxy được tin cậy. Nếu attacker có thể gọi thẳng port của ứng dụng, họ có thể bỏ qua edge và gửi forwarded headers giả trực tiếp.

### 2.1. Chỉ dùng private subnet chưa đủ

Đặt application server trong private subnet giúp giảm bề mặt truy cập, nhưng cần kiểm tra:

- Security group/firewall chỉ cho phép ingress từ gateway.
- Kubernetes NetworkPolicy hoặc service mesh policy giới hạn nguồn.
- Không publish trực tiếp NodePort/host port ngoài ý muốn.
- Internal load balancer không mở cho workload không tin cậy.
- Backend không có một đường public thứ hai.
- Quyền truy cập mạng giữa các services được phân tách.

Một workload khác trong cùng VPC hoặc cluster vẫn có thể gửi request nếu network policy cho phép. Trust boundary phải được định nghĩa bằng source identity/network policy cụ thể.

### 2.2. Bảo vệ kết nối proxy tới backend

Nếu môi trường yêu cầu mức bảo vệ cao, dùng TLS hoặc mutual TLS giữa proxy và application:

- TLS bảo vệ confidentiality/integrity trên đường truyền.
- mTLS giúp application xác thực certificate của proxy.
- Network ACL/security groups giới hạn nguồn kết nối.
- Certificate rotation và trust store phải được quản lý.

TLS thông thường chỉ mã hóa kết nối. Nếu backend nhận kết nối TLS từ bất kỳ client nào có thể truy cập, điều đó chưa chứng minh client là proxy được phép. mTLS hoặc network identity giúp ràng buộc nguồn.

### 2.3. Forwarded header không phải danh tính người dùng

Các header như:

~~~http
X-Authenticated-User: alice
X-Tenant-ID: tenant-a
X-User-Roles: ADMIN
~~~

không tự trở thành Authentication. Nếu ứng dụng dùng chúng làm identity, phải có một trust contract riêng:

- Edge xóa các header cùng tên do client gửi.
- Proxy xác thực user bằng một cơ chế được tin cậy.
- Assertion được ký hoặc được bảo vệ bằng mTLS/trust boundary.
- Backend xác minh nguồn và tính toàn vẹn của assertion.
- Claims được kiểm issuer, audience, thời hạn và quyền.
- Không trộn assertion từ proxy với Bearer token không liên quan.

Với OAuth2 Resource Server, nên để Spring Security xác minh access token theo issuer/audience và lấy principal từ token/introspection đã xác minh. Forwarded headers chỉ mô tả request/proxy context.

## 3. Xóa và ghi đè forwarded headers tại edge

Đây là bước quan trọng nhất. **Không chỉ xóa header Forwarded hoặc chỉ xóa X-Forwarded-For.** Spring và các web server có thể đọc cả hai họ header.

Spring Framework khuyến nghị proxy tại trust boundary reset cả:

- Header chuẩn **Forwarded**.
- Các header **X-Forwarded-***.

Nếu hệ thống dùng header khác như X-Real-IP, X-Original-Host, X-Original-URL hoặc X-Authenticated-User, cũng phải xác định và kiểm soát chúng theo cùng nguyên tắc.

### 3.1. Ví dụ Nginx với một public hostname cố định

Ví dụ minh họa cho edge proxy terminate TLS trên host api.example.com và forward tới một backend nội bộ:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://orders-service:8080;

        # Dùng public host đã được cấu hình cho virtual host này.
        proxy_set_header Host api.example.com;

        # Xóa chuẩn Forwarded do client gửi.
        proxy_set_header Forwarded "";

        # Ghi đè toàn bộ X-Forwarded metadata từ client.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Chỉ gửi prefix nếu deployment thực sự có public prefix.
        proxy_set_header X-Forwarded-Prefix "";
    }
}
~~~

Đây là ví dụ cho một host và một edge proxy. Cần điều chỉnh theo cấu hình TLS, upstream và đường đi thực tế.

Điểm cần chú ý:

- **Forwarded** được xóa để backend không nhận một chuỗi giả từ client.
- **X-Forwarded-For** được ghi đè từ địa chỉ peer mà edge quan sát.
- Host được đặt theo virtual host đã cấu hình, không lấy từ một giá trị tùy ý.
- Proto/port phản ánh listener công khai.
- Prefix chỉ được đặt khi proxy có rewrite path thực sự.

### 3.2. Cẩn thận với X-Forwarded-For và proxy_add_x_forwarded_for

Một cấu hình thường gặp:

~~~nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
~~~

Biến này nối địa chỉ peer hiện tại vào chuỗi X-Forwarded-For đang có. Nếu edge không xóa header đầu vào trước, client có thể tự thêm một IP giả ở đầu chuỗi.

Ví dụ client gửi:

~~~http
X-Forwarded-For: 127.0.0.1
~~~

Edge append địa chỉ client thực:

~~~http
X-Forwarded-For: 127.0.0.1, 198.51.100.25
~~~

Nếu ứng dụng lấy phần tử đầu tiên làm client IP, nó sẽ tin giá trị giả.

Ở điểm edge đầu tiên, thường nên **khởi tạo lại chuỗi từ peer address mà proxy thực sự quan sát**. Nếu có một load balancer đáng tin cậy đứng trước edge, cấu hình real-IP của proxy phải chỉ tin đúng source addresses của load balancer đó trước khi dùng địa chỉ đã khôi phục.

Không dùng $proxy_add_x_forwarded_for như một cách tự động an toàn trong mọi topology.

### 3.3. Khi có nhiều proxy được quản lý

Ví dụ:

~~~text
Client -> CDN -> Load balancer -> Nginx -> Application
~~~

Một thiết kế có thể:

1. CDN loại bỏ forwarded headers do client gửi và tạo metadata mới.
2. Load balancer chỉ tin source CDN được allowlist, sau đó cập nhật chuỗi theo policy.
3. Nginx chỉ tin load balancer được xác định.
4. Application chỉ nhận traffic từ Nginx hoặc ingress đã xác thực.
5. Backend phân tích chuỗi theo danh sách trusted proxy/hop đã cấu hình.

Nếu không cần giữ toàn bộ proxy chain, có thể chuẩn hóa thành một giá trị client IP đã được edge xác minh và chỉ truyền giá trị đó. Giữ ít metadata hơn thường giúp giảm lỗi parse và rò rỉ cấu trúc nội bộ.

## 4. Host header và X-Forwarded-Host

Host ảnh hưởng tới cách ứng dụng dựng absolute URL, redirect, link tự tham chiếu và một số luồng xác thực.

Ví dụ attacker gửi:

~~~http
GET /password/reset HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

Nếu ứng dụng tạo link reset password bằng host mà nó tin từ request, email có thể chứa:

~~~text
https://attacker.example/reset?token=...
~~~

Điều này có thể dẫn tới host-header poisoning, password-reset link poisoning hoặc redirect tới domain không mong muốn.

### 4.1. Host phải được allowlist

Tại edge:

- Khai báo server_name/virtual hosts rõ ràng.
- Từ chối host không hợp lệ hoặc không được cấu hình.
- Với một public domain cố định, ghi đè Host/X-Forwarded-Host bằng domain đó.
- Với custom domains, map domain qua tenant/domain registry đã được xác minh.
- Không dùng Host header tùy ý để tạo tenant hoặc issuer URL.

Tại ứng dụng, các URL nhạy cảm như OAuth redirect URI, callback URI và password reset base URL nên lấy từ cấu hình đã đăng ký, hoặc từ một public origin đã được kiểm soát.

### 4.2. Host không phải tenant authorization

Nếu hệ thống chọn tenant bằng hostname, hostname chỉ là routing input. Sau khi access token được xác minh, phải kiểm issuer, audience và tenant claim phù hợp với tenant được chọn.

~~~text
Host đã được allowlist -> route tenant-a
Token đã verify -> tenant_id=tenant-b

=> từ chối request
~~~

Không cho một hostname hợp lệ khiến token của tenant khác được chấp nhận.

## 5. X-Forwarded-Proto và scheme

Khi TLS terminate ở proxy, kết nối proxy tới application có thể là HTTP. Application nếu chỉ nhìn socket sẽ nghĩ request ban đầu dùng HTTP.

Proxy có thể gửi:

~~~http
X-Forwarded-Proto: https
~~~

Ứng dụng dùng giá trị này để dựng public URL, redirect và xác định secure request.

Nếu attacker có thể giả mạo proto, họ có thể khiến ứng dụng:

- Tạo URL HTTPS giả hoặc HTTP không an toàn.
- Redirect sai scheme.
- Đưa callback/redirect URI về domain/scheme không mong muốn.
- Đánh lừa logic dựa trên request.isSecure().
- Làm sai cấu hình cookie hoặc các security decisions phụ thuộc scheme.

### 5.1. Không dùng forwarded proto để thay thế TLS policy

TLS phải được kết thúc tại một proxy tin cậy hoặc application server. Forwarded proto chỉ là metadata nói về kết nối bên ngoài, không mã hóa kết nối backend và không tự bật TLS.

Nếu edge nhận HTTPS nhưng backend dùng HTTP, hãy bảo vệ đoạn backend bằng network boundary phù hợp hoặc TLS/mTLS. Nếu backend được truy cập trực tiếp, attacker có thể gửi X-Forwarded-Proto: https dù kết nối thực là HTTP.

### 5.2. Redirect và cookie

Scheme/host sai có thể ảnh hưởng:

- Redirect sau login/logout.
- Absolute Location header.
- Cookie Secure flag khi framework dựa trên request scheme.
- Link được render trong HTML/JSON.
- OIDC/OAuth callback URL được dựng từ request context.

Với cookie và OAuth redirect, nên dùng public base URL được cấu hình cố định khi có thể. Nếu cần request-derived URL, chỉ sử dụng sau khi forwarded metadata đã được xác lập bởi proxy tin cậy.

## 6. X-Forwarded-For và địa chỉ client

X-Forwarded-For thường được dùng cho:

- Access logs.
- Rate limiting.
- Abuse detection.
- IP allowlists.
- Geolocation hoặc fraud signals.
- Audit trail.

Nếu lấy IP từ header do client tự gửi, attacker có thể giả mạo địa chỉ và né policy.

### 6.1. Không lấy phần tử đầu tiên một cách mù quáng

Ví dụ:

~~~http
X-Forwarded-For: 203.0.113.10, 10.0.0.12, 10.0.0.18
~~~

Chuỗi có thể đại diện cho client và các proxy, nhưng semantics phụ thuộc cách từng proxy append/reset header.

Không có một quy tắc universal rằng phần tử đầu tiên hoặc cuối cùng luôn là IP client. Cần:

1. Xác định peer socket thực tế đang kết nối tới application.
2. Có danh sách trusted proxy ranges/hops.
3. Duyệt chuỗi từ phía server về phía client theo trust policy.
4. Bỏ qua các hop thuộc trusted proxies.
5. Dừng ở địa chỉ đầu tiên không thuộc trusted set theo đúng parser/implementation.
6. Không tin các phần tử nằm trước proxy đầu tiên không đáng tin.

Tránh tự split chuỗi bằng dấu phẩy rồi chọn index 0. IPv6, whitespace, quoted values và nhiều header lines có thể làm parser tự viết sai.

### 6.2. IP client không phải danh tính

Ngay cả khi X-Forwarded-For được xử lý đúng, IP vẫn chỉ là một network signal. Nó không chứng minh người dùng là ai.

Không dùng client IP thay thế OAuth2 Authentication. IP allowlist có thể là một lớp kiểm soát bổ sung, nhưng access token vẫn cần được xác minh.

### 6.3. Log peer và client address riêng

Để điều tra sự cố, có thể ghi:

- Peer address trực tiếp kết nối tới application.
- Client address được suy ra từ trusted proxy chain.
- Proxy identity/source.
- Request ID/correlation ID.
- Kết quả xác thực và policy decision.

Ghi rõ trường nào là peer và trường nào là derived client IP. Không ghi một địa chỉ lấy từ header chưa xác minh như “client IP thật”.

## 7. X-Forwarded-Prefix và path rewriting

Proxy có thể expose:

~~~text
https://api.example.com/public/orders/42
~~~

nhưng forward tới backend:

~~~text
http://orders-service:8080/orders/42
~~~

Proxy có thể gửi:

~~~http
X-Forwarded-Prefix: /public
~~~

Spring Framework có thể dùng prefix này để khôi phục public context path và tạo URL phù hợp.

Nếu attacker kiểm soát prefix, họ có thể ảnh hưởng link, redirect, route reconstruction hoặc một số logic so khớp path.

### 7.1. Prefix phải do proxy xác lập

- Xóa prefix do client gửi.
- Chỉ ghi prefix đã được cấu hình cho route.
- Không nối prefix tùy ý từ query hoặc header.
- Kiểm thử path normalization và encoded path.
- Đồng bộ path rewrite giữa gateway và application.

### 7.2. Path rewrite có thể tạo khác biệt authorization

Giả sử gateway expose:

~~~text
/api/admin/users
~~~

nhưng rewrite tới backend:

~~~text
/users
~~~

Nếu một filter hoặc security matcher nhìn public path còn controller nhìn backend path, cần xác định chính xác layer nào áp dụng authorization và path mà policy kiểm tra.

Không để gateway bỏ prefix bảo vệ như /admin trong khi backend route được xử lý như endpoint public. Kiểm thử cả URL bên ngoài và path backend sau rewrite.

## 8. Spring Framework: ForwardedHeaderFilter và ForwardedHeaderTransformer

Spring Framework hỗ trợ hai thành phần khác nhau theo server stack.

| Thành phần | Stack | Vai trò |
|---|---|---|
| **ForwardedHeaderFilter** | Servlet / Spring MVC | Wrap Servlet request/response và áp dụng forwarded metadata |
| **ForwardedHeaderTransformer** | Reactive / WebFlux | Điều chỉnh ServerHttpRequest trước khi ServerWebExchange được tạo |

Chúng có thể cập nhật scheme, host, port, remote address hoặc path-related metadata tùy header và implementation; đồng thời loại forwarded headers khỏi request view để tránh các tầng sau tiếp tục sử dụng chúng.

**Chúng không xác thực proxy.** Nếu client gửi header giả và edge không xóa, filter/transformer có thể áp dụng dữ liệu giả đó.

### 8.1. Servlet: ForwardedHeaderFilter

ForwardedHeaderFilter là Servlet Filter trong module spring-web. Nó wrap request để các thành phần downstream nhìn thấy request đã được điều chỉnh theo Forwarded/X-Forwarded headers.

Spring Framework yêu cầu filter được đặt đủ sớm để các thành phần khác như RequestContextFilter nhìn thấy request đã chỉnh sửa. Nếu đăng ký thủ công qua FilterRegistrationBean hoặc web.xml, cần chú ý các dispatcher types phù hợp như REQUEST, ASYNC và ERROR theo tài liệu framework.

Ở chế độ **removeOnly**, filter chỉ loại forwarded headers và không áp dụng giá trị của chúng. Chế độ này hữu ích khi ứng dụng không muốn tin bất kỳ forwarded metadata nào.

### 8.2. WebFlux: ForwardedHeaderTransformer

WebFlux dùng ForwardedHeaderTransformer. Transformer được áp dụng trước khi ServerWebExchange được tạo, để request reactive có scheme/host/port/path view đã được cập nhật.

Có thể khai báo transformer theo cơ chế Spring Framework hoặc dùng cấu hình Spring Boot. Transformer cũng hỗ trợ **removeOnly**, nghĩa là xóa header nhưng không dùng chúng để thay đổi request.

Không tự đăng ký cả transformer và một cơ chế container khác cùng xử lý forwarded headers nếu chưa xác định rõ thứ tự và semantics. Tránh áp dụng hai lần, dẫn tới host/path/remote address bị thay đổi không nhất quán.

### 8.3. Header selection theo phiên bản Spring Framework

Spring Framework hỗ trợ cả RFC 7239 Forwarded và họ X-Forwarded. Trong các release mới, nên cấu hình rõ loại header mà deployment thực sự sử dụng thay vì dựa vào hành vi legacy tự đọc cả hai.

Nếu proxy gửi X-Forwarded-*, hãy chọn chế độ tương ứng. Nếu proxy gửi Forwarded, cấu hình standard header. Dù chọn loại nào, edge vẫn phải xóa cả hai họ header từ bên ngoài vì một tầng khác có thể đọc họ còn lại.

## 9. Spring Boot: server.forward-headers-strategy

Spring Boot cung cấp:

~~~yaml
server:
  forward-headers-strategy: FRAMEWORK
~~~

Các lựa chọn:

| Giá trị | Hành vi |
|---|---|
| **NONE** | Bỏ qua forwarded headers |
| **NATIVE** | Dùng hỗ trợ forwarded headers của web server/container |
| **FRAMEWORK** | Dùng Spring Framework ForwardedHeaderFilter hoặc ForwardedHeaderTransformer |

Ví dụ cấu hình:

~~~yaml
server:
  forward-headers-strategy: FRAMEWORK
~~~

### 9.1. Khi nào dùng NONE?

Dùng NONE khi:

- Ứng dụng không nằm sau proxy.
- Không cần khôi phục public request metadata.
- Hệ thống không có một forwarded-header trust contract được bảo vệ.
- Muốn tránh application tự áp dụng các header không tin cậy.

Nếu proxy có terminate TLS và ứng dụng cần tạo redirect/public URLs, NONE có thể làm application nhìn thấy scheme/host nội bộ. Khi đó cần cấu hình proxy trust đúng trước khi bật forwarded handling.

### 9.2. Khi nào dùng NATIVE?

NATIVE dùng khả năng của embedded server/container. Ví dụ Tomcat có RemoteIpValve; Jetty có ForwardedRequestCustomizer. Mỗi container có cách cấu hình trusted proxies riêng.

Không giả định mọi container có cùng default hoặc cùng cách phân tích chuỗi proxy. Đọc tài liệu đúng server đang chạy và chỉ trust source ranges được kiểm soát.

### 9.3. Khi nào dùng FRAMEWORK?

FRAMEWORK dùng Spring Framework:

- Servlet: ForwardedHeaderFilter.
- Reactive: ForwardedHeaderTransformer.

Lựa chọn này hữu ích khi muốn xử lý forwarded metadata nhất quán ở framework layer. Nhưng nó không thay thế cấu hình edge, network ACL hoặc proxy authentication.

### 9.4. Defaults có thể phụ thuộc môi trường

Spring Boot có thể đặt default strategy khác nhau theo môi trường deployment. Trong tài liệu hiện hành, supported cloud platforms có thể mặc định NATIVE, trong khi các môi trường khác mặc định NONE.

Không dựa vào default. Khai báo rõ strategy trong cấu hình deployment và xác nhận hành vi trên container thực tế.

## 10. Tomcat và trusted proxy configuration

Nếu dùng Tomcat, RemoteIpValve có thể diễn giải các forwarded headers và cập nhật remote address/scheme. Spring Boot cho phép cấu hình header names và internal proxy pattern.

Ví dụ minh họa:

~~~yaml
server:
  forward-headers-strategy: NATIVE
  tomcat:
    remoteip:
      internal-proxies: "10\\.20\\.0\\.\\d{1,3}"
~~~

Regex trên chỉ là ví dụ cho một dải địa chỉ nội bộ cụ thể. Thay bằng địa chỉ/CIDR thực tế của proxy đã được kiểm soát.

Không cấu hình trust all proxies trong production. Không đặt internal-proxies rỗng để chấp nhận mọi nguồn. Nếu container tin một proxy range quá rộng, một workload không liên quan có thể giả mạo forwarded metadata.

### 10.1. Network policy vẫn cần thiết

Tomcat trusted proxy regex là một lớp kiểm soát khi diễn giải remote IP. Nó không thay thế firewall/security group hoặc mTLS.

Backend nên chỉ nhận kết nối từ proxy được phép. Nếu có một đường gọi trực tiếp không bị chặn, cần bảo đảm container không áp dụng forwarded headers cho request từ nguồn không tin cậy.

## 11. Forwarded headers và Spring Security Resource Server

Spring Security xác minh Bearer token dựa trên credential và trust configuration. Forwarded headers không tự thay đổi nội dung JWT, nhưng chúng có thể ảnh hưởng request context mà ứng dụng dùng trong các quyết định khác.

### 11.1. Không dùng X-Forwarded-Host để chọn issuer tùy ý

Issuer/JWKS URI nên đến từ cấu hình tin cậy hoặc tenant registry đã được quản trị.

Không làm:

~~~java
String issuer = request.getHeader("X-Forwarded-Host");
ReactiveJwtDecoder decoder =
    ReactiveJwtDecoders.fromIssuerLocation(issuer);
~~~

Cách này biến một header request thành nguồn tạo trust endpoint và có thể gây SSRF hoặc xác minh token theo issuer do attacker chọn.

Nếu host dùng để route tenant, chỉ map host đã allowlist tới tenant config; sau khi token được xác minh, kiểm issuer, audience và tenant claim khớp với route.

### 11.2. Không dùng forwarded client IP thay Authentication

X-Forwarded-For có thể hỗ trợ rate limiting hoặc risk signals sau khi trust chain được xác lập. Nó không thay thế:

- JWT signature validation.
- Issuer/audience validation.
- Opaque token introspection.
- Scope/role authorization.
- Tenant/owner checks.

Không cấp quyền admin hoặc bỏ qua authentication chỉ vì client IP nằm trong một dải IP, trừ khi đó là một policy bổ sung được thiết kế và kiểm soát độc lập.

### 11.3. Forwarded scheme ảnh hưởng redirect và OAuth/OIDC flow

Nếu Spring Security hoặc OAuth2 client tạo redirect URI dựa trên request, scheme/host sai có thể tạo callback URL không khớp hoặc hướng người dùng tới domain không mong muốn.

OAuth2 redirect URI nên được đăng ký chính xác tại Authorization Server. Không cho forwarded Host tùy ý làm thay đổi redirect URI đã đăng ký.

Với reverse proxy, kiểm tra:

- Public scheme là HTTPS.
- Public host/port đúng.
- Redirect Location đúng domain.
- Callback URI khớp client registration.
- HTTP nội bộ không làm cookie/redirect bị tạo sai.
- Không có direct backend route bỏ qua proxy policy.

### 11.4. DPoP htu cũng phụ thuộc public URI

DPoP proof chứa htm và htu. htu phản ánh target URI công khai mà client gọi, còn backend có thể nhìn thấy internal host/scheme/path sau proxy rewrite.

Nếu application so htu với request URI nội bộ, proof hợp lệ có thể bị từ chối. Nếu application tin forwarded headers giả, attacker có thể tác động URI mà server dùng để kiểm proof.

Cần dựng public URI từ proxy metadata đã được xác thực nguồn, rồi áp dụng URI normalization theo RFC 3986 và DPoP policy. Đây là lý do trust boundary của forwarded headers ảnh hưởng trực tiếp tới token-bound request validation.

## 12. Gateway identity headers và mô hình delegation

Một số gateway xác thực token trước application rồi thêm headers:

~~~http
X-Authenticated-User: alice
X-Authenticated-Tenant: tenant-a
X-Authenticated-Scopes: orders.read
~~~

Có hai mô hình khác nhau:

**Mô hình A — Application tự xác minh access token.** Gateway chuyển tiếp Authorization Bearer; Spring Security Resource Server xác minh token. Identity headers từ gateway không cần thiết cho authentication.

**Mô hình B — Gateway xác minh token và phát assertion cho backend.** Backend tin gateway như một identity provider nội bộ. Khi đó assertion phải được bảo vệ bằng cơ chế có thể xác minh, chẳng hạn signed token với issuer/audience/expiry, hoặc kết nối mTLS kết hợp network policy và contract header rõ ràng.

Không trộn hai mô hình một cách mơ hồ. Nếu backend tin X-Authenticated-User nhưng vẫn nhận request trực tiếp từ Internet, attacker có thể giả mạo identity header.

### 12.1. Nếu dùng signed gateway assertion

Một assertion nội bộ có thể mang:

~~~json
{
  "iss": "https://gateway.internal.example",
  "aud": ["orders-service"],
  "sub": "alice",
  "tenant_id": "tenant-a",
  "scope": "orders.read",
  "iat": 1893452400,
  "exp": 1893452460
}
~~~

Backend phải xác minh chữ ký, issuer, audience, exp, key lifecycle và policy. Không dùng một header plain-text làm assertion có thẩm quyền chỉ vì nó mang tên X-Authenticated-User.

### 12.2. Không chuyển tiếp Authorization header không giới hạn

Gateway cần policy rõ về việc giữ, xóa hoặc thay Authorization. Nếu backend cần token gốc, forward đúng token tới đúng service. Nếu backend cần gateway assertion, không vô tình cho phép cả hai identity sources mâu thuẫn.

## 13. Cấu hình trust theo từng loại deployment

| Deployment | Kiểm soát nguồn | Forwarded handling |
|---|---|---|
| App public trực tiếp, không proxy | Client là peer trực tiếp | NONE hoặc bỏ qua forwarded headers |
| Một reverse proxy trong private subnet | Chỉ proxy được kết nối tới app; strip/overwrite tại edge | NATIVE hoặc FRAMEWORK |
| CDN + load balancer + ingress | Allowlist từng hop, chuẩn hóa chuỗi tại edge | Trust chain theo từng proxy |
| Kubernetes ingress | NetworkPolicy và ingress-only service exposure | Chọn NATIVE/FRAMEWORK, test ingress |
| Service mesh | mTLS workload identity và policy | Chỉ dùng metadata do sidecar/gateway được trust |
| Multi-tenant custom domains | Domain registry và host allowlist | Host mapping có kiểm soát, kiểm tenant claim |

Không có một cấu hình Spring Boot duy nhất phù hợp mọi topology. Trust proxy ranges, edge sanitization và đường kết nối backend là phần quyết định an toàn.

## 14. Kiểm thử forwarded-header trust boundary

Unit test của controller có thể kiểm logic sử dụng request scheme/host, nhưng không chứng minh proxy đã xóa header do client gửi. Cần kết hợp test ở nhiều lớp.

### 14.1. Test trực tiếp application

Gửi các request với header giả:

~~~http
Forwarded: for=127.0.0.1;host=attacker.example;proto=https
X-Forwarded-For: 127.0.0.1
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /admin
~~~

Nếu ứng dụng không có proxy tin cậy hoặc đang dùng removeOnly/NONE, các header này không được làm thay đổi public origin/remote address mà ứng dụng tin cậy.

Nếu application được thiết kế chỉ nhận request từ proxy, test direct access phải bị network policy từ chối ở tầng hạ tầng.

### 14.2. Test qua edge proxy thật

Một integration test nên:

1. Gửi request từ test client tới public ingress.
2. Gửi kèm Forwarded và tất cả X-Forwarded-* giả.
3. Xác nhận proxy xóa/ghi đè chúng.
4. Xác nhận backend nhìn thấy đúng public scheme/host/path theo cấu hình.
5. Xác nhận client IP được suy ra từ trusted chain.
6. Xác nhận forwarded headers không được phản chiếu nguyên trạng vào response.
7. Gọi trực tiếp backend từ một nguồn không được phép và xác nhận bị chặn.

Đây là test quan trọng nhất cho trust boundary. MockMvc hoặc WebTestClient bind trực tiếp application không mô phỏng network source identity của ingress.

### 14.3. Test Host và redirect

- Host hợp lệ tạo public URL đúng.
- Host lạ bị từ chối.
- X-Forwarded-Host giả không thay đổi reset URL.
- Redirect HTTPS dùng đúng domain.
- OAuth callback không đổi theo header do client gửi.
- Cookie Secure và Domain attributes đúng theo deployment.

### 14.4. Test client IP và rate limiting

- Client gửi X-Forwarded-For giả.
- Edge reset giá trị đầu vào.
- Trusted proxy chain được parse đúng.
- Nhiều proxy không làm chọn nhầm IP.
- Direct backend access bị chặn.
- Rate limit không thể bị né bằng cách thay header.

### 14.5. Test path prefix và DPoP

- Proxy rewrite public path đúng.
- X-Forwarded-Prefix giả bị xóa.
- Public URL được dựng đúng sau rewrite.
- DPoP htu so với public URI đã xác minh nguồn.
- Path mismatch bị từ chối.
- Không có route admin bị lộ do path normalization khác nhau.

## 15. Observability và audit

Forwarded metadata hữu ích cho vận hành, nhưng cần phân biệt dữ liệu quan sát với dữ liệu tin cậy.

Nên ghi:

- Direct peer address.
- Derived client address sau trusted-proxy parsing.
- Logical proxy/ingress identity.
- Host/scheme đã được chuẩn hóa.
- Request ID.
- Tenant đã xác minh từ principal.
- Authentication/authorization result.

Không log raw Authorization token. Hạn chế lưu toàn bộ proxy chain nếu không cần vì RFC 7239 lưu ý dữ liệu này có thể tiết lộ cấu trúc mạng và thông tin riêng tư.

Không đưa forwarded host tùy ý, client IP tùy ý hoặc raw headers vào metric labels có cardinality không giới hạn.

## 16. Những anti-pattern cần tránh

**Tin Forwarded vì đây là header chuẩn RFC.** RFC 7239 định nghĩa format, không xác thực người gửi.

**Chỉ xóa Forwarded nhưng giữ X-Forwarded-*.** Một thư viện khác có thể đọc họ header còn lại.

**Chỉ xóa X-Forwarded-For.** X-Forwarded-Host/Proto/Port/Prefix vẫn có thể bị giả mạo.

**Dùng $proxy_add_x_forwarded_for ở edge mà không reset đầu vào.** Client có thể chèn địa chỉ giả vào đầu chuỗi.

**Để application backend truy cập trực tiếp từ Internet.** Attacker có thể bỏ qua edge và gửi header giả.

**Tin mọi proxy trong private subnet.** Private address không tự chứng minh workload là proxy được phép.

**Dùng X-Forwarded-Host để tạo issuer/JWKS URL.** Có thể mở SSRF và trust endpoint tùy ý.

**Dùng X-Forwarded-For như danh tính user.** IP không thay thế Authentication.

**Dùng X-Authenticated-User plain-text làm principal.** Header không có chữ ký/trust contract có thể bị giả mạo.

**Bật FRAMEWORK rồi nghĩ Spring đã xác thực proxy.** Filter/transformer chỉ áp dụng metadata; trust source phải được bảo vệ ở edge/network.

**Cấu hình NATIVE mà không kiểm trusted proxy của container.** Container có thể chấp nhận forwarded values từ nguồn quá rộng.

**Tin X-Forwarded-Prefix tùy ý.** Có thể làm sai public path và authorization/routing.

**Tin forwarded proto để khẳng định kết nối backend đã mã hóa.** TLS termination và backend transport là hai kết nối khác nhau.

**Kiểm thử chỉ bằng MockMvc.** Không chứng minh edge strip headers hoặc network ACL hoạt động.

**Không kiểm direct backend access.** Trust boundary có thể bị bypass.

## 17. Quy trình triển khai an toàn

**Bước 1 — Vẽ proxy chain.** Ghi client, CDN, load balancer, ingress, service mesh và application.

**Bước 2 — Chọn nguồn sự thật cho từng trường.** Client IP, public host, scheme, port và path prefix phải có nguồn rõ ràng.

**Bước 3 — Strip header đầu vào tại edge.** Xóa Forwarded và toàn bộ X-Forwarded-* trước khi tạo giá trị mới. Xử lý cả các header vendor-specific có liên quan.

**Bước 4 — Allowlist host/domain.** Không dùng Host do client gửi để tạo tenant hoặc absolute URL tùy ý.

**Bước 5 — Ghi đè metadata.** Tạo Forwarded hoặc X-Forwarded theo một contract nhất quán; tránh giữ chuỗi client-controlled.

**Bước 6 — Khóa đường backend.** Chỉ proxy được phép kết nối; dùng firewall/network policy và TLS/mTLS khi phù hợp.

**Bước 7 — Cấu hình Spring Boot rõ ràng.** Chọn NONE, NATIVE hoặc FRAMEWORK theo topology và container.

**Bước 8 — Giới hạn trusted proxy ranges.** Không trust all proxies; cấu hình đúng Tomcat/Jetty/Reactor Netty hoặc ingress behavior.

**Bước 9 — Giữ Authentication độc lập.** Xác minh JWT/opaque token, issuer, audience, scope và tenant từ nguồn tin cậy.

**Bước 10 — Kiểm URL/redirect.** Test public origin, OAuth callback, cookie, DPoP htu và path rewrite.

**Bước 11 — Test spoofing qua ingress.** Gửi cả Forwarded và X-Forwarded-* giả; xác nhận edge ghi đè.

**Bước 12 — Test bypass và vận hành.** Chặn direct backend, quan sát peer/client IP riêng, theo dõi thay đổi proxy configuration.

## 18. Câu hỏi tự kiểm tra

**1. Forwarded và X-Forwarded-* có tự đáng tin vì do proxy sử dụng không?**

Không. Client cũng có thể gửi các header đó. Proxy ở trust boundary phải xóa/ghi đè giá trị đầu vào.

**2. Có cần xóa cả Forwarded và X-Forwarded-* không?**

Có. Một thành phần có thể đọc chuẩn này, thành phần khác đọc chuẩn kia.

**3. ForwardedHeaderFilter có xác thực proxy không?**

Không. Nó áp dụng forwarded metadata vào Servlet request và loại headers khỏi request view.

**4. ForwardedHeaderTransformer dùng cho stack nào?**

WebFlux/reactive stack; nó điều chỉnh ServerHttpRequest trước khi ServerWebExchange được tạo.

**5. Spring Boot FRAMEWORK có thay thế edge sanitization không?**

Không. Proxy vẫn phải loại bỏ dữ liệu do client gửi và backend phải chỉ nhận nguồn proxy được phép.

**6. Có nên lấy issuer URL từ X-Forwarded-Host không?**

Không. Issuer/JWKS phải đến từ trusted configuration hoặc tenant registry.

**7. Có nên lấy phần tử đầu tiên của X-Forwarded-For làm client IP?**

Không mặc định. Phải parse chuỗi theo trusted proxy chain đã cấu hình.

**8. Vì sao direct backend access nguy hiểm?**

Attacker có thể bỏ qua edge và gửi forwarded headers giả trực tiếp.

**9. NATIVE và FRAMEWORK khác nhau thế nào?**

NATIVE dùng hỗ trợ của web server/container; FRAMEWORK dùng ForwardedHeaderFilter hoặc ForwardedHeaderTransformer.

**10. Forwarded proto=https có chứng minh backend connection dùng TLS không?**

Không. Nó chỉ mô tả scheme công khai mà proxy ghi nhận.

**11. DPoP htu có thể bị ảnh hưởng bởi forwarded headers không?**

Có. Resource Server cần dựng public URI đáng tin để so với htu của proof.

**12. Test MockMvc có chứng minh proxy xóa header giả không?**

Không. Cần integration test qua ingress/proxy thật và kiểm direct backend access.

## Kết luận

Forwarded headers giúp Spring ứng dụng hiểu request công khai sau khi đi qua proxy, nhưng **chúng chỉ đáng tin khi nguồn gửi được xác định và bảo vệ**. Client có thể tự gửi Forwarded, X-Forwarded-For, X-Forwarded-Host, X-Forwarded-Proto và X-Forwarded-Prefix. Nếu edge proxy chuyển tiếp nguyên vẹn, attacker có thể giả mạo client IP, host, scheme hoặc path.

Bảo vệ phải bắt đầu tại trust boundary: xóa/ghi đè cả hai họ header, kiểm tra host, tạo metadata từ kết nối thực tế và chỉ cho proxy được quản lý kết nối tới backend. Nếu cần, dùng network ACL và mTLS để xác thực proxy. Trong Spring Boot, chọn rõ NONE, NATIVE hoặc FRAMEWORK; ForwardedHeaderFilter và ForwardedHeaderTransformer chỉ xử lý request metadata, không xác minh nguồn.

Với Spring Security Resource Server, không dùng forwarded headers làm identity, issuer hoặc authorization claims. Xác minh access token độc lập, kiểm audience/tenant và dùng public URI đã được khôi phục an toàn cho redirect hoặc DPoP. **Một triển khai chỉ được coi là an toàn khi test qua ingress chứng minh header giả bị loại bỏ và backend không thể bị gọi vòng qua proxy.**

### Tài liệu tham khảo

- [Spring Security — HTTP Proxy Server Configuration](https://docs.spring.io/spring-security/reference/features/exploits/http.html)
- [Spring Framework — Forwarded Headers in Servlet Applications](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Framework — Forwarded Headers in Reactive Applications](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework API — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/api/java/org/springframework/web/filter/ForwardedHeaderFilter.html)
- [Spring Framework API — ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/api/java/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html)
- [RFC 7239 — Forwarded HTTP Extension, Section 8 Security Considerations](https://www.rfc-editor.org/rfc/rfc7239.html#section-8)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [OWASP — Host Header Injection](https://owasp.org/www-project-web-security-testing-guide/)
- [OWASP — TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
