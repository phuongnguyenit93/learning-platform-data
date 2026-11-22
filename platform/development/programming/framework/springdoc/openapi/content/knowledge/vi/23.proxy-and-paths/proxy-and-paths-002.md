# Cấu hình springdoc.api-docs.path và đường dẫn giao diện

Springdoc cung cấp hai nhóm đường dẫn quan trọng: đường dẫn phục vụ đặc tả OpenAPI JSON/YAML và đường dẫn mở giao diện Swagger UI. Trong ứng dụng chạy trực tiếp, các URL này thường hoạt động ngay với cấu hình mặc định. Khi đổi path, thêm context path hoặc đặt ứng dụng sau reverse proxy, cần bảo đảm browser, Swagger UI, swagger-config và backend cùng nhìn thấy một địa chỉ nhất quán.

Ba lớp đường dẫn thường cần phân biệt:

1. **OpenAPI path:** nơi tải JSON/YAML, ví dụ /v3/api-docs.
2. **Swagger UI path:** URL người dùng mở giao diện, ví dụ /swagger-ui.html.
3. **Context path hoặc proxy prefix:** tiền tố của ứng dụng hoặc đường dẫn công khai do gateway thêm vào, ví dụ /catalog hoặc /gateway.

Đổi một lớp không tự động có nghĩa là hai lớp còn lại cũng đổi theo. Hãy kiểm tra URL cuối cùng mà trình duyệt gọi, đặc biệt là swagger-config và OpenAPI document.

## 1. Đường dẫn mặc định của Springdoc

Với cấu hình Springdoc 2.x phổ biến, các URL mặc định thường gồm:

| Tài nguyên | Đường dẫn mặc định | Mục đích |
| --- | --- | --- |
| OpenAPI JSON | /v3/api-docs | Đặc tả OpenAPI ở dạng JSON |
| OpenAPI YAML | /v3/api-docs.yaml | Đặc tả OpenAPI ở dạng YAML |
| Swagger config | /v3/api-docs/swagger-config | Cấu hình mà Swagger UI dùng để tải tài liệu |
| Swagger UI entry | /swagger-ui.html | URL mở giao diện, thường chuyển hướng đến tài nguyên UI |
| Swagger UI static resources | /swagger-ui/** | HTML, JavaScript, CSS và tài nguyên giao diện |
| OpenAPI của group | /v3/api-docs/{group} | Đặc tả của một GroupedOpenApi |

Các đường dẫn thực tế có thể thay đổi theo phiên bản Springdoc, cấu hình ứng dụng và cách reverse proxy chuyển tiếp request. Bảng trên là điểm bắt đầu để kiểm tra, không thay thế việc xem Network tab hoặc endpoint mapping của ứng dụng.

## 2. Đổi đường dẫn OpenAPI bằng springdoc.api-docs.path

Thuộc tính springdoc.api-docs.path thay đổi base path của endpoint OpenAPI. Ví dụ chuyển từ /v3/api-docs sang /openapi:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

Hoặc dùng application.properties:

~~~properties
springdoc.api-docs.path=/openapi
~~~

Sau khi cấu hình, các URL thường có dạng:

| Tài nguyên | URL |
| --- | --- |
| JSON mặc định | /openapi |
| YAML | /openapi.yaml |
| Swagger config | /openapi/swagger-config |
| Group partner | /openapi/partner |
| YAML của group partner | /openapi/partner.yaml |

Đường dẫn group cụ thể phụ thuộc tên group đã đăng ký. Nếu group tên internal, URL tài liệu sẽ dựa trên base path mới và tên group đó.

Đổi path không thay đổi nội dung schema, operation, tag hoặc response trong OpenAPI. Nó chỉ thay đổi nơi tài liệu được phục vụ. Client, gateway, security matcher và pipeline tải đặc tả cần được cập nhật theo URL mới.

## 3. Đổi đường dẫn giao diện bằng springdoc.swagger-ui.path

Thuộc tính springdoc.swagger-ui.path thay đổi URL entry mà người dùng mở để vào Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
~~~

Hoặc:

~~~properties
springdoc.swagger-ui.path=/docs
~~~

Người dùng truy cập:

~~~text
http://localhost:8080/docs
~~~

Đường dẫn entry có thể redirect đến trang Swagger UI thực tế. Tài nguyên tĩnh vẫn được phục vụ qua các URL resource của Swagger UI, thường nằm dưới /swagger-ui/**. Vì vậy, khi đổi path entry, đừng giả định mọi request giao diện đều chuyển sang /docs/**.

Nếu Spring Security đang bảo vệ Swagger UI, cần cập nhật cả entry path mới và static resource path. Nếu ứng dụng chạy sau proxy có prefix, cần kiểm tra redirect Location có giữ đúng prefix công khai hay không.

## 4. Kết hợp path OpenAPI và path Swagger UI

Có thể đổi cả hai path cùng lúc:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Trong môi trường local, người dùng có thể mở /docs. Swagger UI tải swagger-config từ path dựa trên cấu hình API docs và sau đó tải đặc tả tại /openapi.

Khi cấu hình URL hoặc config-url thủ công trong Swagger UI, cần kiểm tra chúng có ghi đè URL mặc định mà Springdoc tạo hay không. Không cấu hình URL trỏ về /v3/api-docs cũ sau khi đã đổi api-docs.path sang /openapi.

Đừng nhầm springdoc.swagger-ui.url với springdoc.swagger-ui.path:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| springdoc.swagger-ui.path | URL mở trang Swagger UI |
| springdoc.swagger-ui.url | URL của một OpenAPI document mà UI tải |
| springdoc.swagger-ui.config-url | URL của swagger-config mà UI tải |
| springdoc.api-docs.path | Base path nơi Springdoc phục vụ OpenAPI documents |

Chỉ đặt url hoặc config-url khi cần một nguồn tài liệu riêng, tài liệu host ở nơi khác hoặc cấu hình UI tùy chỉnh. Với cấu hình thông thường, để Springdoc tạo swagger-config sẽ giảm nguy cơ hai URL bị lệch nhau.

## 5. Phân biệt path Springdoc với context path của ứng dụng

Ứng dụng servlet có thể chạy dưới context path, ví dụ:

~~~yaml
server:
  servlet:
    context-path: /catalog

springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Khi đó, URL bên ngoài của ứng dụng thường có dạng:

~~~text
http://localhost:8080/catalog/openapi
http://localhost:8080/catalog/openapi.yaml
http://localhost:8080/catalog/docs
~~~

Trong cấu hình này, /catalog là context path của toàn ứng dụng; /openapi và /docs là path do Springdoc khai báo bên trong context.

Đối với ứng dụng WebFlux, base path của ứng dụng có thể được cấu hình bằng spring.webflux.base-path. Không dùng server.servlet.context-path cho ứng dụng WebFlux thuần. Hãy chọn đúng thuộc tính theo web stack mà ứng dụng thực sự chạy.

Context path ảnh hưởng đến các route của ứng dụng, không chỉ tài liệu. Khi thêm hoặc thay đổi context path, cập nhật các URL API, redirect, callback, security matcher và cấu hình proxy liên quan.

## 6. Ứng dụng sau reverse proxy có path prefix

Trong production, reverse proxy hoặc API gateway thường công bố ứng dụng dưới một prefix, ví dụ:

~~~text
https://api.example.com/gateway/
~~~

Backend có thể chạy tại http://127.0.0.1:8080 và chỉ nhìn thấy path đã được proxy rewrite. Cần xác định proxy đang:

- Giữ nguyên prefix /gateway khi chuyển request vào backend; hay
- Bỏ prefix /gateway rồi chuyển request đến path nội bộ như /docs hoặc /openapi.

Hai cách này tạo ra request URI khác nhau ở backend. Nếu không đồng bộ, Springdoc có thể sinh redirect hoặc URL swagger-config trỏ về đường dẫn nội bộ, khiến browser gọi sai endpoint.

Một hợp đồng proxy đơn giản cần xác định rõ:

| Thành phần | Ví dụ |
| --- | --- |
| URL public | https://api.example.com/gateway |
| Backend origin | http://127.0.0.1:8080 |
| Prefix public | /gateway |
| OpenAPI path nội bộ | /openapi |
| Swagger UI path nội bộ | /docs |
| OpenAPI URL public mong đợi | https://api.example.com/gateway/openapi |
| Swagger UI URL public mong đợi | https://api.example.com/gateway/docs |

Không nên chỉ kiểm tra backend bằng localhost. Hãy mở URL public qua proxy vì đây mới là URL mà client và browser thực sự sử dụng.

## 7. Forwarded headers giúp ứng dụng nhận diện URL public

Khi proxy kết thúc TLS hoặc thay đổi host/port/prefix, backend có thể chỉ nhìn thấy HTTP nội bộ. Reverse proxy nên gửi thông tin gốc qua Forwarded hoặc các header X-Forwarded-* phù hợp, thường gồm:

- X-Forwarded-Host: hostname public mà client truy cập.
- X-Forwarded-Proto: scheme public, thường là https.
- X-Forwarded-Port: port public nếu khác port mặc định.
- X-Forwarded-Prefix: prefix public mà proxy đã loại bỏ trước khi chuyển request, ví dụ /gateway.

Spring Boot có thể cấu hình cách xử lý forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Chiến lược framework sử dụng cơ chế xử lý forwarded headers của Spring. Tùy web server và môi trường, chiến lược native cũng có thể phù hợp. Hãy chọn một cách xử lý nhất quán, tránh để nhiều lớp cùng diễn giải header và tạo URL sai.

Ví dụ Nginx khi bỏ prefix /gateway trước khi gửi request đến backend:

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

Trong cấu hình trên, dấu slash cuối của proxy_pass khiến Nginx thay phần URI khớp location bằng URI được chỉ định; request /gateway/docs được chuyển đến backend dưới path /docs. X-Forwarded-Prefix cho ứng dụng biết prefix public cần được giữ trong URL được tạo ra.

Nếu proxy giữ nguyên prefix và backend cũng được cấu hình để phục vụ dưới prefix đó, không được đồng thời yêu cầu framework thêm prefix lần nữa. Hãy xác định rõ ai chịu trách nhiệm xử lý prefix để tránh URL dạng /gateway/gateway/docs.

## 8. Chỉ tin forwarded headers từ proxy đáng tin cậy

Forwarded headers có thể bị client gửi trực tiếp nếu proxy không xóa hoặc ghi đè chúng. Nếu ứng dụng tin header giả mạo, URL redirect hoặc URL tài liệu có thể trỏ sang host, scheme hoặc prefix do attacker kiểm soát.

Ở edge proxy:

1. Ghi đè các header forwarded do client gửi bằng giá trị proxy tự xác định.
2. Không chuyển tiếp nguyên trạng X-Forwarded-Host hoặc X-Forwarded-Proto do client tự cung cấp.
3. Chỉ cho backend nhận request từ proxy hoặc network được phép.
4. Cấu hình trust boundary rõ ràng nếu có nhiều proxy nối tiếp.
5. Kiểm tra URL được sinh ra ở môi trường thật, không chỉ dựa trên giá trị header cấu hình.

Không bật xử lý forwarded headers một cách tùy tiện khi ứng dụng có thể được truy cập trực tiếp từ Internet. Header cần được tin cậy chỉ khi request đi qua proxy đã được kiểm soát.

## 9. Path rewrite và redirect của Swagger UI

Một lỗi phổ biến là URL entry mở được nhưng redirect đến path thiếu prefix. Ví dụ:

~~~text
Public URL:       https://api.example.com/gateway/docs
Redirect Location: https://api.example.com/swagger-ui/index.html
Expected:         https://api.example.com/gateway/swagger-ui/index.html
~~~

Nguyên nhân thường là backend không nhận diện prefix public hoặc proxy không chuyển forwarded headers đúng. Kiểm tra:

- Response header Location của request /docs.
- Request HTML, JavaScript và CSS trong Network tab.
- URL swagger-config mà Swagger UI tải.
- URL OpenAPI document bên trong swagger-config.
- X-Forwarded-Prefix, X-Forwarded-Proto và X-Forwarded-Host ở request đến backend.

Nếu UI entry redirect đúng nhưng swagger-config trỏ đến /v3/api-docs cũ, kiểm tra springdoc.api-docs.path và springdoc.swagger-ui.config-url. Nếu config đúng nhưng tài nguyên static bị 404, kiểm tra proxy có chuyển tiếp /swagger-ui/** hay không.

## 10. Cấu hình custom path trong ứng dụng sau proxy

Ví dụ ứng dụng Spring MVC chạy ở backend root, proxy công bố dưới /gateway và bỏ prefix trước khi forward:

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

Proxy công bố:

~~~text
https://api.example.com/gateway/docs
https://api.example.com/gateway/openapi
~~~

Backend nhận request dưới /docs và /openapi, còn forwarded prefix giúp framework xây dựng URL công khai đúng khi tạo redirect hoặc liên kết tuyệt đối. Cấu hình thực tế còn phụ thuộc proxy có chuyển tiếp header đúng và Springdoc/Swagger UI tạo URL tương đối hay tuyệt đối trong phiên bản đang dùng.

Nếu ứng dụng có context path riêng, ví dụ /catalog, cần tính cả context path và proxy prefix. Tránh cấu hình cùng một prefix ở server.servlet.context-path, spring.webflux.base-path và proxy rewrite nếu chúng không cùng một mục đích.

## 11. Tùy chỉnh swagger-config và URL tài liệu

Swagger UI thường tải cấu hình từ swagger-config. Cấu hình này chỉ ra OpenAPI document URL, danh sách group, OAuth settings và các tùy chọn giao diện liên quan.

Nếu cần trỏ UI đến tài liệu được host riêng, có thể cấu hình springdoc.swagger-ui.url hoặc danh sách springdoc.swagger-ui.urls tùy trường hợp. Khi đó:

- URL phải truy cập được từ browser, không chỉ từ backend.
- Nếu UI và document khác origin, cần cấu hình CORS trên server phục vụ document.
- Nếu tài liệu cần xác thực, browser phải có cách gửi credential phù hợp.
- Không trỏ browser đến hostname nội bộ như localhost hoặc tên service trong Docker network.
- Nếu dùng nhiều group, mỗi URL cần có tên hiển thị và path public hợp lệ.

Khi đổi springdoc.api-docs.path, kiểm tra swagger-config được tạo tự động có dùng path mới. Nếu đã override config-url hoặc url thủ công, cập nhật chúng cùng lúc để tránh UI vẫn gọi endpoint cũ.

## 12. Kết hợp custom path với Spring Security

Khi thay đổi path, matcher bảo mật cũng phải thay đổi. Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/docs",
        "/swagger-ui/**",
        "/openapi",
        "/openapi.yaml",
        "/openapi/**"
    ).hasRole("API_DOCS")
    .anyRequest().authenticated()
);
~~~

Ví dụ trên dùng Spring Security 6 và path nội bộ của ứng dụng. Nếu có context path, servlet container thường loại context path khỏi path mà Spring Security matcher xử lý; xác minh theo web stack và cấu hình triển khai. Nếu proxy thêm prefix nhưng bỏ nó trước khi chuyển tiếp, matcher thường dùng path nội bộ sau rewrite.

Đừng chỉ bảo vệ /docs. JSON/YAML và swagger-config có thể được tải trực tiếp. Cũng đừng quên static assets /swagger-ui/**. Khi dùng config-url hoặc tài liệu group ở path khác, thêm đúng URL đó vào chính sách truy cập.

## 13. Kiểm tra URL sau khi đổi cấu hình

Sau khi khởi động ứng dụng, kiểm tra các endpoint nội bộ:

~~~bash
curl -i http://localhost:8080/docs
curl -i http://localhost:8080/openapi
curl -i http://localhost:8080/openapi.yaml
curl -i http://localhost:8080/openapi/swagger-config
curl -i http://localhost:8080/swagger-ui/index.html
~~~

Sau đó kiểm tra URL public qua reverse proxy:

~~~bash
curl -i https://api.example.com/gateway/docs
curl -i https://api.example.com/gateway/openapi
curl -i https://api.example.com/gateway/openapi.yaml
curl -i https://api.example.com/gateway/openapi/swagger-config
~~~

Các URL trong ví dụ cần thay theo host, prefix và path của môi trường. Kiểm tra response status, Location, Content-Type và body. Với swagger-config, đọc URL document mà UI sẽ tải; với UI, mở Network tab để kiểm tra request assets và OpenAPI document.

Kết quả mong đợi:

| Kiểm tra | Dấu hiệu đúng |
| --- | --- |
| Swagger UI entry | Trả trang hoặc redirect đến URL có prefix public đúng |
| OpenAPI JSON | Trả JSON OpenAPI |
| OpenAPI YAML | Trả YAML OpenAPI |
| Swagger config | URL tài liệu trỏ đến path public có thể truy cập từ browser |
| Static assets | JavaScript/CSS không bị 404 |
| Group document | URL group dùng base path mới và đúng group name |

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| /openapi trả 404 | Chỉ đổi URL client hoặc proxy, chưa đổi springdoc.api-docs.path | Cấu hình property và kiểm tra endpoint backend |
| Swagger UI vẫn gọi /v3/api-docs | swagger-config hoặc swagger-ui.url bị override bằng path cũ | Kiểm tra config-url, url và swagger-config |
| /docs mở được nhưng UI trắng | Static assets hoặc swagger-config bị proxy/security chặn | Kiểm tra /swagger-ui/** và request Network |
| Redirect mất /gateway | Forwarded prefix không được chuyển hoặc xử lý | Cấu hình X-Forwarded-Prefix và forward-headers-strategy |
| URL sinh ra dùng http thay vì https | Backend không nhận X-Forwarded-Proto hoặc không xử lý forwarded headers | Cấu hình proxy ghi đè proto và Spring forwarded header strategy |
| URL dùng hostname nội bộ | Host header hoặc X-Forwarded-Host sai | Proxy truyền hostname public và ghi đè header client gửi |
| URL có /gateway/gateway | Prefix được thêm ở nhiều lớp | Chỉ định một nơi xử lý prefix và bỏ cấu hình lặp |
| /openapi.yaml trả 404 | Matcher hoặc proxy chỉ cho phép base JSON path | Thêm route và security matcher riêng cho YAML |
| Group docs bị lỗi sau khi đổi path | Client hoặc UI vẫn dùng group URL cũ | Cập nhật base path và kiểm tra /openapi/{group} |
| Security chặn UI sau khi đổi path | Matcher vẫn dùng path mặc định | Cập nhật matcher entry, assets, config và document |
| Swagger UI tải tài liệu từ localhost | UI URL bị cấu hình cứng hoặc swagger-config sinh sai origin | Dùng URL public hoặc forwarded headers đúng |

## 15. Checklist trước khi triển khai

- [ ] Đã xác định path OpenAPI nội bộ và public.
- [ ] Đã xác định path Swagger UI entry và static resources.
- [ ] springdoc.api-docs.path khớp với route mà backend phục vụ.
- [ ] springdoc.swagger-ui.path khớp URL người dùng mở.
- [ ] URL JSON, YAML, swagger-config và group đều được kiểm tra.
- [ ] Đã phân biệt Springdoc path với servlet context path hoặc WebFlux base path.
- [ ] Đã xác định reverse proxy giữ hay bỏ path prefix.
- [ ] Proxy ghi đè forwarded headers từ client và gửi host/proto/prefix chính xác.
- [ ] server.forward-headers-strategy được chọn phù hợp với hạ tầng.
- [ ] Redirect Location và URL trong swagger-config giữ đúng host, scheme và prefix public.
- [ ] Static assets /swagger-ui/** được proxy chuyển tiếp.
- [ ] Spring Security matcher được cập nhật theo path nội bộ sau rewrite.
- [ ] CORS được cấu hình nếu Swagger UI và OpenAPI document khác origin.
- [ ] Không có URL localhost hoặc hostname nội bộ trong cấu hình mà browser nhìn thấy.
- [ ] Đã thử trực tiếp qua URL public, không chỉ gọi backend localhost.

springdoc.api-docs.path quyết định nơi OpenAPI JSON/YAML được phục vụ; springdoc.swagger-ui.path quyết định URL mở giao diện. Context path và reverse proxy có thể thêm hoặc bỏ prefix, vì vậy cần đồng bộ path rewrite, forwarded headers, redirect, swagger-config và security matcher. Kiểm tra toàn bộ request qua URL public giúp bảo đảm người dùng tải được giao diện và đúng tài liệu OpenAPI sau khi triển khai.
