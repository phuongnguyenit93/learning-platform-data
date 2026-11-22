# Ranh giới tin cậy đối với header do proxy chuyển tiếp

## 1. Vì sao header do proxy chuyển tiếp cần có ranh giới tin cậy?

Một ứng dụng Spring Boot thường chạy phía sau reverse proxy, ingress controller, load balancer hoặc API gateway. Client kết nối tới proxy; proxy chuyển request vào ứng dụng qua mạng nội bộ. Vì vậy, địa chỉ, scheme và host mà ứng dụng nhìn thấy có thể khác với thông tin mà client thực sự dùng ở bên ngoài.

Ví dụ, client gọi:

~~~http
https://api.example.com/gateway/v3/api-docs
~~~

Proxy kết thúc TLS và chuyển tiếp tới Spring Boot bằng HTTP nội bộ:

~~~text
http://spring-app:8080/v3/api-docs
~~~

Nếu ứng dụng chỉ nhìn request nội bộ, nó có thể cho rằng request dùng HTTP và host là spring-app:8080. Các URL được tạo ra cho redirect, link hoặc OpenAPI document vì thế có thể sai. Proxy thường gửi thêm các header như `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Prefix` để ứng dụng biết thông tin bên ngoài.

Những header này chỉ đáng tin khi chúng đến từ proxy được kiểm soát. Client có thể tự gửi header cùng tên và giả mạo IP, host, scheme hoặc prefix nếu proxy không xóa và ghi đè chúng. Nếu ứng dụng tin mọi giá trị nhận được, kẻ tấn công có thể làm sai URL được tạo, đánh lừa audit log, tác động redirect hoặc gây hiểu nhầm về nguồn request.

Với Springdoc OpenAPI, thông tin proxy còn ảnh hưởng đến URL server và đường dẫn mà Swagger UI dùng để tải tài liệu hoặc gọi API. Do đó, cần thiết lập ranh giới tin cậy rõ giữa client, proxy và ứng dụng trước khi cấu hình forwarded headers.

## 2. Forwarded và X-Forwarded-* là gì?

Có hai nhóm header thường gặp:

- **Forwarded**: header chuẩn hóa theo RFC 7239, có thể truyền thông tin client/proxy, host và protocol.
- **X-Forwarded-***: nhóm header theo quy ước phổ biến, được nhiều reverse proxy và framework hỗ trợ.

Một request có thể chứa:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

Các header có ý nghĩa khác nhau:

| Header | Thông tin được chuyển tiếp | Ảnh hưởng có thể có |
|---|---|---|
| Forwarded | for, by, host, proto | Địa chỉ client/proxy, host và scheme |
| X-Forwarded-For | Địa chỉ IP client và các proxy trong chuỗi | Audit log, giới hạn tốc độ, chính sách theo IP |
| X-Forwarded-Proto | Scheme bên ngoài như http hoặc https | Secure request, redirect và URL được tạo |
| X-Forwarded-Host | Host mà client dùng ở phía ngoài | Absolute URL, redirect và OpenAPI server |
| X-Forwarded-Port | Port bên ngoài | URL tuyệt đối và redirect |
| X-Forwarded-Prefix | Prefix mà proxy thêm hoặc giữ ở bên ngoài | Context path và link tới API/Swagger UI |

Không phải proxy nào cũng gửi tất cả các header. Một số hệ thống chỉ gửi Forwarded; một số dùng X-Forwarded-*; một số có cả hai. Cần xác định proxy thực tế đang gửi gì và cấu hình Spring Boot nhất quán với nguồn đó.

## 3. Proxy là ranh giới tin cậy, không phải tên header

Tên header không chứng minh nguồn gốc của giá trị. Client có thể gửi một request trực tiếp như:

~~~http
GET /v3/api-docs HTTP/1.1
Host: api.example.com
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-For: 127.0.0.1
~~~

Nếu proxy chuyển nguyên các header này vào ứng dụng và Spring tin chúng, ứng dụng có thể ghi nhận sai IP client hoặc tạo URL với host do client kiểm soát.

Ranh giới tin cậy phải được thiết lập tại hạ tầng:

1. Chỉ proxy/load balancer được phép kết nối tới cổng ứng dụng.
2. Proxy ở ranh giới bên ngoài phải loại bỏ các forwarded header do client gửi.
3. Proxy phải ghi lại các giá trị mà nó tự xác định.
4. Các proxy nội bộ tiếp theo chỉ được tin khi chúng nằm trong chuỗi hạ tầng đã kiểm soát.
5. Ứng dụng chỉ diễn giải forwarded headers từ đường kết nối tin cậy.

Không nên bật xử lý forwarded headers trên ứng dụng có thể truy cập trực tiếp từ Internet nếu không có lớp proxy lọc header. Spring Framework có thể đọc header, nhưng không thể tự xác minh proxy gửi nó có đáng tin hay không.

## 4. Quy tắc quan trọng: xóa giá trị do client tự gửi rồi ghi lại

Ở proxy đầu tiên nhận kết nối từ client, cần loại bỏ forwarded headers mà client có thể tự đặt, sau đó thiết lập giá trị dựa trên request thực tế mà proxy quan sát được.

Với Nginx làm proxy biên trực tiếp nhận kết nối từ client, cấu hình minh họa:

~~~nginx
location / {
    proxy_pass http://spring-app:8080;

    proxy_set_header Host $host;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
}
~~~

Trong ví dụ, Nginx bỏ header Forwarded nhận từ client và tự tạo các X-Forwarded-* dựa trên request mà proxy xử lý. Cấu hình này giả định Nginx là proxy biên trực tiếp; nếu phía trước còn load balancer, $remote_addr có thể là địa chỉ của load balancer chứ không phải client cuối.

Cũng cần xác thực Host mà proxy chấp nhận. Không nên chuyển tiếp một Host tùy ý do client gửi thành X-Forwarded-Host đáng tin. Hãy dùng danh sách hostname hợp lệ, virtual host và cấu hình default server phù hợp.

Nếu dùng cấu hình:

~~~nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
~~~

Nginx sẽ nối địa chỉ peer hiện tại vào chuỗi X-Forwarded-For nhận được. Điều này chỉ an toàn khi các giá trị đã có trong chuỗi được tạo bởi proxy đáng tin phía trước. Ở proxy biên, không được mặc nhiên giữ nguyên chuỗi do client cung cấp.

## 5. Chuỗi nhiều proxy và cách xác định client IP

Trong kiến trúc nhiều lớp, request có thể đi qua:

~~~text
Browser
  -> CDN
  -> Load Balancer
  -> Ingress Controller
  -> Spring Boot
~~~

Mỗi proxy có thể thêm địa chỉ của nó vào X-Forwarded-For. Kết quả có thể là một danh sách IP phân tách bằng dấu phẩy. Không nên luôn lấy phần tử đầu tiên rồi xem đó là client IP thật, vì phần đầu có thể do client tự chèn nếu proxy biên không xóa header ban đầu.

Một quy tắc vận hành an toàn:

- Xác định chính xác proxy nào được phép kết nối tới lớp kế tiếp.
- Xác định proxy nào xóa header đầu vào và proxy nào chỉ append.
- Chỉ tin các hop thuộc dải mạng hoặc danh sách proxy đã kiểm soát.
- Tính client IP từ chuỗi sau khi loại các hop tin cậy theo đúng thứ tự.
- Không dùng X-Forwarded-For làm căn cứ authorization nếu chưa có quy trình xác minh nguồn.

Ví dụ, nếu ingress chỉ nhận request từ load balancer có IP cố định, ingress có thể tin thông tin được load balancer đã chuẩn hóa. Nếu ingress cũng nhận request từ Pod hoặc mạng khác, cần giới hạn network policy và cấu hình trusted proxy tương ứng.

Đừng giải quyết chuỗi nhiều proxy bằng cách tin mọi địa chỉ hoặc mọi header. Số hop tin cậy và danh sách proxy phải phản ánh topology thực tế.

## 6. Các rủi ro khi tin forwarded headers tùy ý

| Giá trị bị giả mạo | Hệ quả có thể xảy ra |
|---|---|
| X-Forwarded-For | Sai audit log, bypass rate limit theo IP hoặc chính sách allowlist |
| X-Forwarded-Proto | Ứng dụng nghĩ request là HTTPS dù client kết nối HTTP; redirect/cookie URL có thể sai |
| X-Forwarded-Host | Tạo absolute URL hoặc redirect tới host do attacker kiểm soát |
| X-Forwarded-Port | URL được tạo chứa port không đúng |
| X-Forwarded-Prefix | Link, redirect hoặc URL OpenAPI chứa path prefix giả |
| Forwarded | Có thể tác động đồng thời host, proto và địa chỉ client |

Đặc biệt, X-Forwarded-Host có thể dẫn tới host-header poisoning. Nếu ứng dụng tạo link xác nhận, redirect, URL reset mật khẩu hoặc OpenAPI server dựa trên host giả, client có thể bị dẫn tới domain ngoài dự kiến.

X-Forwarded-Proto giả mạo cũng có thể khiến ứng dụng hiểu sai trạng thái HTTPS. Điều này ảnh hưởng redirect, cookie Secure và cách xây dựng URL. Chỉ bật xử lý forwarded headers khi proxy có trách nhiệm thiết lập giá trị đó.

## 7. Cấu hình Spring Boot với server.forward-headers-strategy

Spring Boot cung cấp thuộc tính:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các lựa chọn chính:

| Giá trị | Hành vi |
|---|---|
| NONE | Không dùng forwarded headers để thay đổi thông tin request |
| NATIVE | Dùng hỗ trợ của web server/container |
| FRAMEWORK | Dùng cơ chế xử lý forwarded headers của Spring Framework |

**FRAMEWORK** sử dụng cơ chế của Spring Framework. Với Servlet stack, cơ chế thường là ForwardedHeaderFilter; với WebFlux, Spring dùng ForwardedHeaderTransformer để điều chỉnh request reactive.

**NATIVE** giao việc xử lý cho container hoặc server tích hợp. Ví dụ, Tomcat có cơ chế xử lý thông tin proxy qua RemoteIpValve. Cách cấu hình chi tiết phụ thuộc container.

Không nên bật đồng thời nhiều cơ chế xử lý forwarded headers mà không hiểu thứ tự và phạm vi của chúng. Chọn một strategy phù hợp với stack và kiểm tra giá trị request sau khi đi qua proxy.

Tên thuộc tính và hành vi cụ thể cần đối chiếu với phiên bản Spring Boot đang dùng. Không nên sao chép cấu hình từ dự án khác mà không xác minh container và topology mạng.

## 8. ForwardedHeaderFilter trong Servlet

Với ứng dụng Spring MVC/Servlet, Spring Framework có ForwardedHeaderFilter để diễn giải các header chuyển tiếp. Filter có thể điều chỉnh thông tin request mà ứng dụng nhìn thấy, như scheme, host, port và prefix.

Trong Spring Boot, khi chọn:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Boot có thể cấu hình cơ chế filter tương ứng. Nếu ứng dụng tự đăng ký ForwardedHeaderFilter bằng bean hoặc FilterRegistrationBean, cần kiểm tra xem Boot đã đăng ký filter tương tự chưa để tránh xử lý trùng.

Điều quan trọng là filter không xác thực nguồn header. Spring Framework cảnh báo rằng ứng dụng không thể biết một forwarded header do proxy đáng tin hay do client độc hại gửi. Proxy biên phải xóa header không tin cậy trước khi request tới ứng dụng.

Nếu không thể bảo đảm proxy đã làm sạch header, không nên để ứng dụng diễn giải chúng như dữ liệu đáng tin. Có thể dùng chế độ chỉ loại bỏ forwarded headers trong cấu hình filter phù hợp, hoặc chọn strategy NONE, tùy kiến trúc và phiên bản.

## 9. Forwarded headers trong WebFlux

Ứng dụng WebFlux không dùng Servlet Filter chain. Spring Framework cung cấp ForwardedHeaderTransformer để điều chỉnh ServerHttpRequest theo forwarded headers.

Trong Spring Boot, strategy FRAMEWORK có thể cấu hình transformer cho reactive stack. Không tự thêm ForwardedHeaderFilter của Servlet vào ứng dụng WebFlux.

Các nguyên tắc bảo mật vẫn giống Servlet:

- Chỉ tin forwarded headers từ proxy đã kiểm soát.
- Proxy biên phải loại bỏ header do client gửi.
- Không để ứng dụng có đường truy cập trực tiếp bỏ qua proxy.
- Kiểm tra host, scheme, port và prefix mà WebFlux nhìn thấy.
- Không dùng header giả mạo làm căn cứ authorization.

Nếu cùng một hệ thống có cả Servlet và Reactive service, mỗi service cần cấu hình đúng theo web stack của nó. Không sao chép bean filter giữa hai loại ứng dụng.

## 10. Xử lý X-Forwarded-Proto khi TLS kết thúc ở proxy

Một kiến trúc phổ biến là TLS kết thúc tại ingress hoặc load balancer. Kết nối từ client tới proxy dùng HTTPS, còn kết nối nội bộ tới Spring Boot dùng HTTP.

Ví dụ:

~~~text
Client --HTTPS--> Reverse Proxy --HTTP--> Spring Boot
~~~

Ứng dụng có thể nhìn thấy request HTTP nội bộ. Proxy cần gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Port: 443
~~~

Sau khi Spring xử lý forwarded headers từ proxy đáng tin, request có thể được nhận diện là HTTPS ở phía ngoài. Điều này giúp redirect và absolute URL được tạo với scheme đúng.

Không nên đặt X-Forwarded-Proto thành https một cách cố định nếu proxy cũng phục vụ HTTP hoặc có nhiều virtual host với chính sách khác nhau. Giá trị cần phản ánh scheme client thực sự sử dụng, sau khi proxy đã hoàn tất TLS termination và xác thực host.

Ứng dụng vẫn nên dùng HTTPS ở ranh giới công khai. Forwarded header không mã hóa kết nối và không thay thế TLS.

## 11. X-Forwarded-Host và chống host-header poisoning

Khi proxy chuyển tiếp host bên ngoài, Spring có thể dùng giá trị đó để tạo absolute URL. Nếu X-Forwarded-Host không được kiểm soát, attacker có thể gửi host giả và khiến ứng dụng tạo URL trỏ tới domain khác.

Ví dụ OpenAPI document có thể bị tạo với:

~~~yaml
servers:
  - url: https://attacker.example/api
~~~

Nếu client tin server URL này và gửi credential khi thử API, rủi ro có thể vượt khỏi việc hiển thị sai tài liệu.

Các biện pháp cần có:

1. Proxy chỉ chấp nhận hostname nằm trong allowlist.
2. Proxy ghi lại X-Forwarded-Host theo virtual host đã xác thực.
3. Ứng dụng chỉ tin forwarded headers từ proxy.
4. Không dùng giá trị host tùy ý để tạo link nhạy cảm.
5. Với API có hostname cố định, cân nhắc cấu hình OpenAPI server tĩnh hoặc theo môi trường.
6. Kiểm thử request có Host/X-Forwarded-Host giả mạo.

Không coi header Host hoặc X-Forwarded-Host là danh tính người dùng. Chúng chỉ mô tả đích/host của request và cần được kiểm soát tại proxy.

## 12. X-Forwarded-Prefix và context path

Một proxy có thể công bố ứng dụng dưới prefix bên ngoài, ví dụ:

~~~text
https://example.com/platform/shop/
~~~

nhưng chuyển request vào Spring Boot bằng path nội bộ:

~~~text
http://spring-app:8080/
~~~

Proxy có thể gửi:

~~~http
X-Forwarded-Prefix: /platform/shop
~~~

Spring xử lý forwarded prefix có thể dùng thông tin này khi tạo URL bên ngoài. Tuy nhiên, cần phân biệt:

- **Context path**: path prefix mà chính ứng dụng Spring Boot được cấu hình để phục vụ.
- **Forwarded prefix**: prefix bên ngoài do proxy thêm hoặc giữ khi chuyển tiếp.
- **Path rewriting**: proxy có thể giữ nguyên prefix hoặc loại nó trước khi forward.

Nếu proxy giữ prefix trong request path và đồng thời gửi X-Forwarded-Prefix giống hệt, ứng dụng có thể tạo URL lặp prefix. Nếu proxy loại prefix nhưng không gửi forwarded prefix, URL được tạo có thể thiếu phần path bên ngoài.

Hãy chọn một mô hình rõ ràng và kiểm tra request path nội bộ, prefix được forward và URL công khai trong cùng một lần thử.

## 13. Ảnh hưởng tới OpenAPI server URL

OpenAPI document có thể chứa mảng `servers` để chỉ định base URL của API. Khi Springdoc suy luận URL từ request hoặc Spring MVC cung cấp thông tin server, forwarded headers có thể ảnh hưởng tới host, scheme, port và prefix được nhận diện.

Ví dụ tài liệu đúng khi API được công bố qua proxy:

~~~yaml
servers:
  - url: https://api.example.com/gateway
    description: Public API
~~~

Nếu request đến Spring Boot qua HTTP nội bộ nhưng OpenAPI document lại có server URL là http://spring-app:8080, Swagger UI có thể gọi sai địa chỉ hoặc browser chặn do mixed content.

Có hai hướng cấu hình:

- Dùng forwarded headers đã được proxy đáng tin làm sạch và để ứng dụng nhận diện URL bên ngoài.
- Khai báo Server Object tường minh theo môi trường nếu hostname/path công khai cố định.

Ví dụ với Swagger Core model:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    return new OpenAPI()
        .servers(List.of(
            new Server()
                .url("https://api.example.com/gateway")
                .description("Public API")
        ));
}
~~~

Không nên vừa khai báo server tĩnh vừa kỳ vọng Springdoc tự suy luận một server khác nếu chưa xác định rõ cơ chế hợp nhất. Hãy kiểm tra mảng servers trong OpenAPI JSON cuối cùng.

## 14. Swagger UI và OpenAPI document sau reverse proxy

Swagger UI tải nhiều tài nguyên: trang HTML, JavaScript/CSS, swagger-config và OpenAPI document. Sau đó, Try it out gửi request tới server URL được mô tả trong OpenAPI.

Khi chạy sau proxy, cần kiểm tra:

- Entry point Swagger UI có redirect tới URL công khai đúng scheme/host/prefix không.
- Tài nguyên JS/CSS có được tải dưới prefix công khai không.
- swagger-config có trả URL tài liệu phù hợp không.
- OpenAPI JSON/YAML có server URL đúng không.
- Các group document có URL chính xác không.
- Try it out gọi đúng public API base URL.
- Không có mixed content khi trang dùng HTTPS nhưng server URL dùng HTTP.

Nếu ứng dụng được công bố dưới prefix /gateway, tất cả link do Swagger UI và Springdoc tạo cần nhất quán với prefix đó. Không chỉ sửa URL của Swagger UI mà quên URL của OpenAPI document hoặc server URL trong tài liệu.

Nếu cần tùy chỉnh springdoc.api-docs.path hoặc springdoc.swagger-ui.path, hãy đồng bộ với reverse proxy route và security matcher. Các đường dẫn nội bộ mà proxy chuyển tới ứng dụng có thể khác đường dẫn công khai mà browser nhìn thấy.

## 15. Ví dụ cấu hình Nginx với prefix công khai

Giả sử client truy cập:

~~~text
https://api.example.com/gateway/swagger-ui.html
~~~

Nginx loại prefix trước khi chuyển tới ứng dụng, đồng thời gửi thông tin prefix:

~~~nginx
location /gateway/ {
    proxy_pass http://spring-app:8080/;

    proxy_set_header Host $host;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-Prefix /gateway;
}
~~~

Ví dụ giả định Nginx là proxy biên trực tiếp và host đã được xác thực qua cấu hình virtual host. Dấu slash cuối của location và proxy_pass ảnh hưởng cách Nginx rewrite URI; cần kiểm tra URL mà ứng dụng thực sự nhận.

Nếu có load balancer phía trước Nginx, không dùng cấu hình này nguyên trạng để xác định client IP. Hãy cấu hình trusted real IP từ các dải mạng của load balancer trước, sau đó mới dùng địa chỉ đã xác minh. Không append chuỗi X-Forwarded-For chưa được làm sạch từ client.

## 16. Không dùng forwarded headers làm cơ chế authorization

Forwarded headers là metadata về đường đi của request. Chúng không phải credential.

Không nên viết rule kiểu:

~~~java
if ("127.0.0.1".equals(request.getRemoteAddr())) {
    allowAdminAccess();
}
~~~

nếu giá trị remote address đã bị thay đổi từ header mà client có thể giả mạo. Tương tự, không cho phép admin chỉ vì X-Forwarded-For chứa một IP nội bộ.

Nếu cần giới hạn truy cập theo network, hãy thực thi tại firewall, ingress hoặc tầng mạng tin cậy; nếu kiểm tra ở ứng dụng, phải dựa trên remote peer/proxy đã xác minh và cấu hình trust chain rõ ràng. Với quyền người dùng, dùng authentication và authorization thực sự như OAuth2/JWT, session hoặc API key.

Forwarded headers cũng không chứng minh request đến từ browser, người dùng hay dịch vụ cụ thể. Chúng chỉ cung cấp dữ liệu định tuyến được proxy chuyển tiếp.

## 17. Kiểm thử ranh giới tin cậy

Cần kiểm tra cả luồng hợp lệ và luồng giả mạo.

| Tình huống | Kỳ vọng |
|---|---|
| Request qua proxy hợp lệ với HTTPS | Ứng dụng nhận scheme https |
| Request qua proxy với host được allowlist | URL được tạo dùng đúng host công khai |
| Request qua proxy có prefix | Link và OpenAPI server chứa prefix đúng một lần |
| Client gửi X-Forwarded-Host giả | Proxy xóa/ghi đè; giá trị giả không ảnh hưởng ứng dụng |
| Client gửi X-Forwarded-Proto giả | Proxy ghi lại theo kết nối thực tế |
| Client gửi X-Forwarded-For giả | IP giả không được coi là client IP đáng tin |
| Truy cập trực tiếp vào cổng ứng dụng | Bị chặn ở network hoặc forwarded headers không được tin |
| Chuỗi nhiều proxy | Chỉ các hop đã cấu hình mới được tin |
| OpenAPI document tải qua proxy | servers và paths khớp URL công khai |
| Swagger UI Try it out | Request tới đúng host, scheme và prefix |

Có thể dùng integration test qua ingress/reverse proxy để kiểm tra hành vi thực tế. MockMvc đơn lẻ thường không chứng minh được proxy đã làm sạch header hoặc firewall đã chặn đường truy cập trực tiếp.

Khi kiểm tra OpenAPI, tải /v3/api-docs thông qua URL công khai và xem trường servers. Đồng thời kiểm tra redirect và các request swagger-config/tài nguyên UI trong Browser Network tab.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| OpenAPI servers chứa hostname container | Ứng dụng chưa xử lý forwarded host hoặc proxy không gửi header |
| Swagger UI tạo URL HTTP dù bên ngoài dùng HTTPS | X-Forwarded-Proto thiếu, sai hoặc không được tin đúng cách |
| Redirect trỏ tới domain lạ | Host/X-Forwarded-Host không được allowlist và làm sạch |
| Prefix /gateway bị lặp | Proxy giữ prefix và đồng thời gửi X-Forwarded-Prefix trùng |
| Link Swagger UI thiếu prefix | Proxy rewrite path nhưng không chuyển tiếp prefix hoặc framework không xử lý |
| Client IP luôn là IP proxy | Chưa cấu hình X-Forwarded-For hoặc native remote IP support |
| Client có thể giả IP qua header | Proxy biên giữ nguyên X-Forwarded-For do client gửi |
| Cùng request cho URL khác nhau | Nhiều cơ chế xử lý forwarded headers cùng hoạt động |
| Servlet hoạt động nhưng WebFlux sai | Dùng sai filter/transformer hoặc cấu hình web stack không phù hợp |
| Chỉ YAML hoặc group docs sai URL | Matcher, path rewrite hoặc cấu hình endpoint chưa đồng bộ |
| Ứng dụng tin header khi gọi trực tiếp | Cổng backend không bị giới hạn truy cập hoặc strategy tin mọi request |
| Try it out gọi host nội bộ | Server URL trong OpenAPI chưa phản ánh public URL |

Khi điều tra, so sánh request bên ngoài, header proxy gửi vào, request mà Spring nhìn thấy và OpenAPI JSON được sinh. Không chỉ nhìn log ứng dụng vì log có thể đã dùng giá trị forwarded đã được diễn giải.

## 19. Checklist cấu hình an toàn

Trước khi bật forwarded header processing trong Spring Boot:

1. Xác định toàn bộ proxy/load balancer/ingress trong đường đi.
2. Xác định proxy biên nào xóa forwarded headers do client gửi.
3. Bảo đảm proxy ghi lại host, proto, port và client IP theo nguồn đã xác minh.
4. Giới hạn network để ứng dụng chỉ nhận traffic từ proxy được phép.
5. Chọn server.forward-headers-strategy phù hợp: NONE, NATIVE hoặc FRAMEWORK.
6. Không đăng ký filter/transformer trùng với cơ chế Boot đã cấu hình.
7. Kiểm tra X-Forwarded-Prefix và path rewriting.
8. Allowlist hostname công khai và tránh host-header poisoning.
9. Không dùng forwarded headers làm credential hoặc authorization rule.
10. Kiểm tra OpenAPI servers, swagger-config, UI resources và Try it out qua URL công khai.
11. Thử request có forwarded header giả mạo và xác nhận proxy loại bỏ/ghi đè.
12. Kiểm tra cả Servlet và Reactive theo đúng web stack.

Ranh giới tin cậy nằm ở proxy đã được kiểm soát và đường mạng từ proxy tới ứng dụng. Spring Boot chỉ nên diễn giải forwarded headers sau khi hạ tầng bảo đảm nguồn của chúng. Khi host, scheme, client IP và prefix được chuyển tiếp đúng cách, Springdoc có thể tạo OpenAPI document và Swagger UI với URL phù hợp môi trường công khai mà không tin dữ liệu do client tùy ý cung cấp.

