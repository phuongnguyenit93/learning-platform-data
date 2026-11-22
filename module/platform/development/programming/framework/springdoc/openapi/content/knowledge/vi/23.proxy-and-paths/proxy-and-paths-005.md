# Forwarded, X-Forwarded-* và thông tin về scheme, host, prefix

Khi ứng dụng Spring Boot chạy sau load balancer, ingress hoặc reverse proxy, backend thường không nhìn thấy URL mà người dùng đã truy cập. Client có thể gọi HTTPS tại api.example.com/gateway, trong khi proxy kết nối đến backend bằng HTTP tại 10.0.0.12:8080 và bỏ prefix /gateway trước khi chuyển tiếp. Nếu backend chỉ dựa vào request nội bộ, redirect và URL trong tài liệu OpenAPI có thể dùng sai scheme, host, port hoặc path prefix.

Các header Forwarded và X-Forwarded-* truyền metadata của request gốc qua proxy. Spring Boot có thể xử lý những header này để ứng dụng nhìn thấy thông tin public phù hợp hơn. Cần hiểu từng header, quy tắc khi có nhiều proxy và ranh giới tin cậy để cấu hình đúng mà không mở đường cho header giả mạo.

## 1. Vì sao backend cần biết URL public?

Giả sử người dùng mở:

~~~text
https://api.example.com/gateway/docs
~~~

Reverse proxy chuyển request đến backend:

~~~text
http://10.0.0.12:8080/docs
~~~

Backend nhìn thấy HTTP, hostname nội bộ và path không còn prefix. Nếu ứng dụng tạo redirect hoặc URL tuyệt đối từ request nội bộ, kết quả có thể là:

~~~text
http://10.0.0.12:8080/swagger-ui/index.html
~~~

Địa chỉ đó không thể dùng từ trình duyệt bên ngoài. Ứng dụng cần biết metadata của request public:

| Thuộc tính | Giá trị public mong đợi |
| --- | --- |
| Scheme | https |
| Host | api.example.com |
| Port | 443 |
| Prefix | /gateway |
| URL của Swagger UI | https://api.example.com/gateway/docs |

Forwarded headers cho proxy biết những thuộc tính nào cần được giữ lại khi request đi qua các lớp mạng.

## 2. Header Forwarded theo RFC 7239

RFC 7239 định nghĩa header chuẩn có tên Forwarded. Một proxy có thể thêm các thuộc tính như:

~~~http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com
~~~

Các tham số thường gặp:

| Tham số | Ý nghĩa |
| --- | --- |
| for | Địa chỉ client hoặc node đứng trước proxy |
| by | Địa chỉ node proxy đang thêm phần tử Forwarded |
| proto | Scheme của request phía client, ví dụ http hoặc https |
| host | Host header mà client dùng khi gửi request đến proxy |

Forwarded có thể chứa nhiều phần tử, phân tách bằng dấu phẩy. Mỗi phần tử mô tả một hop trong chuỗi proxy. Ví dụ:

~~~http
Forwarded: for=203.0.113.25;proto=https;host=api.example.com, for=10.0.1.8;proto=http;host=service.internal
~~~

Giá trị có thể cần dấu ngoặc kép khi chứa ký tự đặc biệt. IPv6, port và quoted-string cũng cần được xử lý theo cú pháp RFC thay vì tự tách chuỗi bằng dấu phẩy hoặc dấu chấm phẩy trong mã ứng dụng.

Forwarded không có tham số chuẩn để biểu diễn path prefix. Thông tin prefix thường được truyền bằng header mở rộng X-Forwarded-Prefix.

## 3. Các header X-Forwarded-* phổ biến

Nhóm X-Forwarded-* là quy ước phổ biến giữa reverse proxy và ứng dụng:

| Header | Thông tin | Ví dụ |
| --- | --- | --- |
| X-Forwarded-For | Danh sách IP client và proxy đã đi qua | 203.0.113.25, 10.0.1.8 |
| X-Forwarded-Host | Host public mà client truy cập | api.example.com |
| X-Forwarded-Proto | Scheme public | https |
| X-Forwarded-Port | Port public | 443 |
| X-Forwarded-Prefix | Prefix mà proxy đã thêm hoặc loại bỏ khi chuyển request | /gateway |

Ví dụ một request được proxy chuyển tiếp:

~~~http
GET /docs HTTP/1.1
Host: app.internal
X-Forwarded-For: 203.0.113.25
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

Backend nhận request path /docs nhưng có thể tái dựng URL public là https://api.example.com/gateway/docs nếu proxy và framework được cấu hình nhất quán.

X-Forwarded-Prefix không phải header chuẩn trong RFC 7239; đây là quy ước được nhiều proxy/framework hỗ trợ. Hãy xác minh proxy thực tế gửi header nào và framework đang chạy có hiểu header đó hay không.

## 4. Phân biệt Forwarded với X-Forwarded-*

Forwarded là header chuẩn hóa trong RFC 7239. X-Forwarded-* là nhóm header theo quy ước triển khai đã tồn tại rộng rãi từ trước.

| Tiêu chí | Forwarded | X-Forwarded-* |
| --- | --- | --- |
| Chuẩn | RFC 7239 | Quy ước phổ biến, không có một RFC thống nhất cho toàn bộ nhóm |
| Host | host=... | X-Forwarded-Host |
| Scheme | proto=... | X-Forwarded-Proto |
| Client IP | for=... | X-Forwarded-For |
| Port | Có thể nằm trong host theo cú pháp URI authority | X-Forwarded-Port |
| Prefix | Không có thuộc tính chuẩn riêng | X-Forwarded-Prefix |

Một số proxy gửi cả Forwarded và X-Forwarded-*. Không nên để hai bộ header chứa giá trị mâu thuẫn. Chọn một chính sách chuẩn hóa tại edge proxy và kiểm tra cách container/framework xử lý khi cả hai cùng xuất hiện.

Không tự viết parser đơn giản cho Forwarded nếu ứng dụng chỉ cần framework xử lý. Cú pháp có quoted-string, nhiều hop và IPv6; parser không đầy đủ có thể diễn giải sai host hoặc client address.

## 5. Scheme, host, port và prefix tác động đến điều gì?

Các thuộc tính forwarded không chỉ phục vụ log. Chúng có thể ảnh hưởng đến URL được framework tạo ra:

- Scheme quyết định URL bắt đầu bằng http hay https, trạng thái secure request và một số redirect.
- Host quyết định hostname trong URL tuyệt đối, liên kết callback hoặc server URL.
- Port quyết định cổng public khi URL không dùng port mặc định.
- Prefix giúp tái dựng path public khi proxy loại bỏ tiền tố trước khi chuyển request đến backend.
- Client IP có thể được dùng cho log, audit, rate limit hoặc chính sách mạng, nhưng chỉ an toàn khi biết hop nào đáng tin cậy.

Trong tích hợp Springdoc, thông tin này quan trọng khi Swagger UI redirect đến trang tĩnh, tải swagger-config, tải OpenAPI JSON/YAML hoặc khi OpenAPI document có server URL được suy ra từ request. Hãy xác minh đặc tả được sinh ra thay vì giả định mọi URL đều tự động đúng.

## 6. Cấu hình Spring Boot xử lý forwarded headers

Spring Boot cung cấp thuộc tính server.forward-headers-strategy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các giá trị thường gặp:

| Giá trị | Cách xử lý |
| --- | --- |
| none | Không bật xử lý forwarded headers tự động |
| native | Dùng hỗ trợ forwarded header của web server/container |
| framework | Dùng cơ chế xử lý forwarded headers của Spring Framework |

Với servlet stack, chiến lược framework sử dụng ForwardedHeaderFilter. Với WebFlux, Spring sử dụng cơ chế chuyển đổi request tương ứng, thường là ForwardedHeaderTransformer. Chi tiết hỗ trợ còn phụ thuộc phiên bản Spring Boot, web server và cấu hình ứng dụng.

Chọn một chiến lược phù hợp với kiến trúc proxy. Không bật nhiều cơ chế xử lý chồng lấn nếu chúng cùng sửa scheme, host, port hoặc prefix. Xử lý hai lần có thể tạo URL sai hoặc thêm prefix lặp.

Ví dụ dùng framework strategy khi backend chạy sau proxy:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Nếu ứng dụng cần xử lý forwarded headers thủ công hoặc container đã được cấu hình native, kiểm tra cấu hình tương ứng và đảm bảo chỉ có một lớp chịu trách nhiệm chuyển metadata.

## 7. Servlet MVC: ForwardedHeaderFilter

Trong Spring MVC, ForwardedHeaderFilter bọc request để các API servlet nhìn thấy thông tin đã được proxy chuyển tiếp. Những API như getScheme(), isSecure(), getServerName(), getServerPort() và URI/context path có thể phản ánh giá trị public sau khi filter xử lý.

Spring Boot có thể tự cấu hình filter theo server.forward-headers-strategy=framework. Khi dùng cơ chế tự động này, không đăng ký thêm một ForwardedHeaderFilter thứ hai nếu không có lý do cụ thể.

Nếu tự đăng ký filter, cần đặt thứ tự filter phù hợp để các thành phần tạo redirect hoặc URL chạy sau khi request đã được chuyển đổi. Cách đăng ký và thứ tự filter cần khớp với Spring Security và các filter khác trong ứng dụng.

## 8. WebFlux: ForwardedHeaderTransformer

Với WebFlux, request là reactive server request, không dùng servlet filter. Spring Framework cung cấp ForwardedHeaderTransformer để điều chỉnh thông tin request dựa trên forwarded headers.

Trong Spring Boot, server.forward-headers-strategy=framework yêu cầu framework xử lý forwarded metadata cho web stack phù hợp. Không dùng ForwardedHeaderFilter trong ứng dụng WebFlux thuần.

Nếu tự cấu hình transformer, tránh đăng ký thêm một transformer thứ hai hoặc kết hợp transformer với một cơ chế native đang xử lý cùng header. Kiểm tra URL được tạo bởi WebFlux handler, redirect và Springdoc sau khi bật cấu hình.

## 9. Proxy kết thúc TLS: giữ scheme https

Một mô hình phổ biến:

~~~text
Browser --HTTPS--> Reverse proxy --HTTP--> Spring Boot
~~~

Browser kết nối HTTPS đến proxy, nhưng proxy chuyển tiếp bằng HTTP đến backend. Nếu backend không nhận metadata, request có thể được nhìn như HTTP. Khi đó ứng dụng có thể tạo redirect về http, làm sai absolute URL hoặc gây lỗi khi dùng cookie Secure.

Proxy cần gửi scheme gốc, ví dụ:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

Với RFC 7239:

~~~http
Forwarded: proto=https;host=api.example.com
~~~

Giá trị proto phải mô tả scheme phía client kết nối đến proxy, không phải scheme mà proxy dùng để kết nối backend. Nếu có nhiều lớp load balancer, lớp đầu tiên kết thúc TLS cần truyền metadata tin cậy để lớp sau không ghi đè thành http một cách sai lệch.

## 10. Host và port phải là host public được phép

Khi proxy chuyển tiếp request, Host header backend có thể là hostname nội bộ. X-Forwarded-Host giúp ứng dụng biết hostname public mà client sử dụng.

Ví dụ:

~~~http
Host: spring-app.service.local:8080
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

Ứng dụng có thể dùng thông tin này để tạo URL public nếu forwarded headers được tin cậy và xử lý đúng.

Host header là đầu vào cần kiểm soát. Proxy nên chỉ nhận hostname đã được cấu hình trong virtual host/server_name hoặc allowlist tương ứng. Không dùng bất kỳ giá trị X-Forwarded-Host nào do client gửi trực tiếp để tạo URL quan trọng, email link, redirect hoặc nội dung tài liệu.

Nếu public host có port không mặc định, bảo đảm proxy gửi port chính xác. Nếu host đã chứa port, không tạo URL với port bị lặp. Hãy kiểm tra URL tuyệt đối cuối cùng trong response và OpenAPI document.

## 11. Prefix khi proxy strip path

Giả sử client truy cập:

~~~text
https://api.example.com/gateway/openapi
~~~

Proxy loại bỏ /gateway trước khi chuyển request:

~~~text
Backend nhận: /openapi
X-Forwarded-Prefix: /gateway
~~~

Backend cần nhận biết prefix public để tạo redirect hoặc URL tương ứng. Ví dụ Nginx:

~~~nginx
location /gateway/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /gateway;
}
~~~

Với location /gateway/ và proxy_pass có URI kết thúc bằng dấu slash, Nginx thay phần URI khớp location bằng URI được chỉ định. Do đó /gateway/openapi được chuyển thành /openapi ở backend. X-Forwarded-Prefix truyền lại prefix public đã bị loại bỏ.

Nếu proxy không strip prefix, backend phải được cấu hình để nhận path có prefix hoặc route rewrite tương ứng. Không gửi X-Forwarded-Prefix để thêm một prefix mà backend đã xử lý qua context path, nếu điều đó làm prefix bị nhân đôi.

## 12. Xử lý chuỗi nhiều proxy

Một request có thể đi qua nhiều lớp:

~~~text
Browser -> CDN -> Load balancer -> Ingress -> Nginx -> Spring Boot
~~~

Mỗi proxy có thể thêm hoặc ghi đè forwarded metadata. Vì vậy cần quy định:

1. Proxy nào là điểm tin cậy đầu tiên và biết scheme/host public.
2. Proxy nào được phép nối thêm địa chỉ vào X-Forwarded-For.
3. Proxy nào chịu trách nhiệm chuẩn hóa X-Forwarded-Host, Proto, Port và Prefix.
4. Backend chỉ nhận traffic từ các proxy được phép hay có thể bị gọi trực tiếp.
5. Framework được cấu hình để xử lý chuỗi forwarded theo đúng trust boundary.

X-Forwarded-For thường là danh sách IP phân tách bằng dấu phẩy. Khi có nhiều hop, không thể tùy tiện lấy phần tử đầu hoặc cuối mà kết luận đó là client thật. Cần biết proxy nào đã thêm từng phần tử và cấu hình trusted proxy tương ứng.

Forwarded cũng có thể chứa nhiều phần tử theo thứ tự các proxy. Cách diễn giải chuỗi phải theo chuẩn và chính sách tin cậy, không chỉ theo vị trí chuỗi mà ứng dụng mong muốn.

## 13. Ranh giới tin cậy và nguy cơ giả mạo

Nếu backend có thể được truy cập trực tiếp, attacker có thể gửi:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /trusted
~~~

Nếu ứng dụng tin các header này, nó có thể tạo redirect hoặc URL tài liệu trỏ sang domain attacker. X-Forwarded-For giả mạo còn có thể ảnh hưởng log, audit hoặc giới hạn truy cập nếu ứng dụng dùng sai làm client IP.

Biện pháp bảo vệ:

- Chỉ cho backend nhận traffic từ reverse proxy hoặc network được phép.
- Proxy tại edge phải xóa hoặc ghi đè forwarded headers do client cung cấp.
- Dùng allowlist host public tại proxy và ứng dụng nếu có.
- Không dùng forwarded IP làm cơ sở xác thực người dùng.
- Cấu hình trusted proxy chain rõ ràng ở hạ tầng và ứng dụng.
- Kiểm tra hành vi khi request đi trực tiếp đến backend, nếu đường truy cập đó tồn tại.

ForwardedHeaderFilter và ForwardedHeaderTransformer có thể biến header thành thông tin request mà ứng dụng sử dụng. Chúng không tự xác minh proxy gửi header có đáng tin cậy hay không. Trust boundary phải được thiết lập ở network/proxy.

## 14. Tác động đến Springdoc và OpenAPI servers

Springdoc tạo tài liệu dựa trên request mapping, cấu hình và request context. Trong môi trường sau proxy, forwarded metadata có thể ảnh hưởng đến redirect và URL được tạo ra từ request. Nếu OpenAPI document chứa servers URL được suy ra từ request, cần kiểm tra host, scheme, port và prefix có đúng địa chỉ public hay không.

Ví dụ server URL mong đợi:

~~~yaml
servers:
  - url: https://api.example.com/gateway
~~~

Nếu document lại sinh:

~~~yaml
servers:
  - url: http://spring-app.service.local:8080
~~~

thì client generator hoặc Swagger UI có thể gọi nhầm backend nội bộ. Kiểm tra /v3/api-docs hoặc custom api-docs path để xem giá trị servers. Nếu dự án khai báo servers tường minh bằng @OpenAPIDefinition hoặc OpenApiCustomizer, cấu hình tường minh có thể quyết định URL thay vì request metadata.

Với Swagger UI, kiểm tra lần lượt:

1. URL entry và redirect Location.
2. URL swagger-config.
3. URL OpenAPI JSON/YAML trong swagger-config.
4. Server URL trong OpenAPI document.
5. URL mà Try it out thực sự gọi.

Nếu UI hiển thị đúng nhưng Try it out gọi hostname nội bộ, lỗi có thể nằm ở servers URL hoặc config tài liệu, không nhất thiết ở static resource path.

## 15. Spring Security, redirect và cookie

Scheme public đúng có thể ảnh hưởng đến redirect trong quá trình xác thực. Ví dụ ứng dụng chạy sau TLS-terminating proxy nhưng không nhận X-Forwarded-Proto có thể tạo redirect http thay vì https.

Điều này đặc biệt quan trọng với:

- OAuth2/OIDC login redirect URI.
- Redirect từ trang đăng nhập về URL ban đầu.
- Cookie có thuộc tính Secure.
- Link tuyệt đối do ứng dụng tạo.
- Swagger UI redirect đến tài nguyên static.

Forwarded headers không thay thế cấu hình OAuth client. Redirect URI vẫn phải được đăng ký chính xác tại identity provider và phải khớp URL public thực tế. Đồng thời, CORS không sửa được scheme hoặc host sai; CORS là chính sách truy cập giữa các origin, không phải cơ chế tái dựng URL.

## 16. Ví dụ cấu hình Nginx đầy đủ hơn

Ví dụ dưới đây giả định Nginx là proxy public trực tiếp, kết thúc TLS và bỏ prefix /gateway:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /gateway/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /gateway;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Spring Boot:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

URL public mong đợi:

~~~text
https://api.example.com/gateway/docs
https://api.example.com/gateway/openapi
https://api.example.com/gateway/openapi.yaml
~~~

Ví dụ này giả định Nginx là proxy public trực tiếp nên X-Forwarded-For được ghi đè bằng địa chỉ peer thực tế. Nếu Nginx đứng sau một load balancer đáng tin cậy, cần thiết kế riêng cách giữ chuỗi IP của các hop đã xác minh; không nối nguyên trạng X-Forwarded-For do client gửi. Nếu load balancer đã kết thúc TLS, biến $scheme tại Nginx có thể là http. Khi đó không được dùng mù quáng $scheme làm scheme public; phải lấy giá trị từ metadata do load balancer đáng tin cậy gửi và bảo đảm Nginx xóa/ghi đè header từ client trước khi chuyển tiếp.

Ví dụ trên chỉ phù hợp khi Nginx là điểm tin cậy được kiểm soát. Nếu có nhiều proxy, hãy thiết kế lại chuỗi header và allowlist network thay vì sao chép cấu hình một cách máy móc.

## 17. Kiểm tra forwarded headers trong môi trường local

Có thể mô phỏng header bằng curl khi gọi backend local:

~~~bash
curl -i http://localhost:8080/docs \
  -H "X-Forwarded-Host: api.example.com" \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Port: 443" \
  -H "X-Forwarded-Prefix: /gateway"
~~~

Đây chỉ là phép thử mô phỏng trong môi trường local có kiểm soát. Không dùng request giả mạo này để kết luận hệ thống production đã thiết lập trust boundary an toàn.

Kiểm tra thêm:

~~~bash
curl -i https://api.example.com/gateway/docs
curl -i https://api.example.com/gateway/openapi
curl -i https://api.example.com/gateway/openapi.yaml
~~~

Quan sát response Location, Content-Type và URL trong swagger-config. Mở browser Developer Tools để xem request thực tế đến swagger-config, static assets và OpenAPI document.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Redirect dùng http dù client truy cập https | X-Forwarded-Proto thiếu hoặc sai | Proxy truyền proto public và Spring xử lý forwarded headers |
| URL dùng hostname nội bộ | Host/X-Forwarded-Host không phản ánh hostname public | Proxy chuẩn hóa host và chỉ chấp nhận domain được phép |
| Port bị sai hoặc lặp | X-Forwarded-Port và host authority không nhất quán | Chuẩn hóa host/port tại proxy, kiểm tra URL cuối |
| Prefix /gateway biến mất | Proxy strip prefix nhưng không gửi X-Forwarded-Prefix | Gửi prefix và bật xử lý forwarded headers phù hợp |
| Prefix xuất hiện hai lần | Prefix đã được giữ trong backend path nhưng lại được thêm lần nữa | Chọn một lớp chịu trách nhiệm xử lý prefix |
| X-Forwarded-For chứa nhiều IP | Request đi qua nhiều proxy | Xác định trusted proxy chain và cách chọn client IP |
| Client tự đặt X-Forwarded-Host | Proxy không xóa/ghi đè header từ client | Chuẩn hóa header tại edge và chặn truy cập backend trực tiếp |
| MVC hoạt động nhưng WebFlux không xử lý đúng | Dùng servlet filter trong reactive stack hoặc cấu hình sai | Dùng cơ chế forwarded header tương ứng với WebFlux |
| Swagger UI tải được nhưng Try it out gọi sai host | servers URL hoặc swagger-config chứa URL nội bộ | Kiểm tra OpenAPI servers và document URL trong config |
| OAuth redirect URI không khớp | Scheme/host/prefix public được tái dựng sai hoặc client registration cũ | Đồng bộ forwarded metadata và redirect URI tại identity provider |

## 19. Checklist triển khai

- [ ] Đã xác định URL public gồm scheme, host, port và prefix.
- [ ] Đã xác định từng proxy hop và nơi kết thúc TLS.
- [ ] Đã chọn Forwarded hoặc X-Forwarded-* làm nguồn metadata nhất quán.
- [ ] Proxy edge xóa hoặc ghi đè forwarded headers do client gửi.
- [ ] X-Forwarded-Host chỉ chứa hostname public được phép.
- [ ] X-Forwarded-Proto phản ánh scheme phía client, không phải kết nối nội bộ đến backend.
- [ ] X-Forwarded-Port khớp port public.
- [ ] X-Forwarded-Prefix chỉ dùng khi proxy đã thay đổi prefix theo đúng quy ước.
- [ ] Backend chỉ nhận request từ proxy đáng tin cậy nếu đang tin forwarded headers.
- [ ] server.forward-headers-strategy được chọn phù hợp với servlet hoặc reactive stack.
- [ ] Không đăng ký filter/transformer trùng lặp.
- [ ] Đã kiểm tra redirect Location và URL OpenAPI servers.
- [ ] Đã kiểm tra swagger-config, Swagger UI assets và Try it out.
- [ ] Đã xác minh OAuth redirect URI và cookie Secure nếu có đăng nhập.
- [ ] Đã thử qua URL public và kiểm tra trường hợp gọi trực tiếp backend.

Forwarded và X-Forwarded-* giúp Spring Boot tái dựng scheme, host, port và prefix public khi request đi qua proxy. Để Springdoc tạo redirect và URL tài liệu đúng, proxy phải truyền metadata chính xác, Spring phải xử lý theo web stack phù hợp và backend chỉ tin header từ proxy được kiểm soát. Khi có nhiều proxy, hãy quản lý trust chain rõ ràng và xác minh URL cuối cùng bằng response thực tế cùng OpenAPI document.
