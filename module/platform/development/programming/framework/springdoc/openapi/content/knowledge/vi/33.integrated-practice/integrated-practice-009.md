# Triển khai sau reverse proxy và kiểm tra đường dẫn gọi thử

Khi ứng dụng Spring Boot chạy phía sau Nginx, ingress controller, API gateway hoặc load balancer, người dùng truy cập API qua địa chỉ công khai như `https://api.example.com/shop`, trong khi ứng dụng có thể chỉ nhận request tại `http://127.0.0.1:8080`. Nếu proxy thay scheme, host, port hoặc loại bỏ một path prefix trước khi chuyển request vào Spring, springdoc có thể sinh URL nội bộ hoặc Swagger UI có thể gửi lệnh Try it out đến sai địa chỉ.

Để triển khai đúng, cần đồng bộ ba phần: proxy phải truyền thông tin request gốc, Spring Boot phải tin và xử lý forwarded headers từ proxy được phép, và OpenAPI document phải chứa server base URL mà consumer thực sự truy cập được. Sau đó kiểm tra cả Swagger UI, swagger-config, OpenAPI JSON và URL cuối cùng được gọi khi nhấn Try it out.

## 1. Luồng request qua reverse proxy

Một request công khai thường đi qua các bước:

1. Trình duyệt gửi request đến domain HTTPS công khai.
2. Reverse proxy kết thúc TLS, nhận host/path công khai và áp dụng route rewrite.
3. Proxy chuyển request đến Spring Boot bằng HTTP nội bộ hoặc HTTPS nội bộ.
4. Spring xử lý controller, springdoc hoặc Swagger UI.
5. Response đi ngược qua proxy và được trình duyệt hiển thị.

Ví dụ:

~~~text
Browser
  https://api.example.com/shop/catalog/swagger-ui.html
             |
             v
Reverse proxy
  TLS termination
  strips /shop before forwarding
  adds X-Forwarded-* headers
             |
             v
Spring Boot
  http://127.0.0.1:8080/catalog/swagger-ui.html
  server.servlet.context-path=/catalog
             |
             v
springdoc
  /catalog/openapi
  /catalog/openapi/swagger-config
  Swagger UI and OpenAPI document
~~~

Nếu ứng dụng không biết request ban đầu dùng HTTPS và domain công khai nào, nó có thể sinh redirect hoặc server URL dựa trên `http://127.0.0.1:8080`. Nếu ứng dụng không biết proxy đã bỏ `/shop`, link được sinh ra có thể thiếu prefix. Kết quả là trang Swagger UI tải được nhưng tài liệu hoặc lệnh Try it out không hoạt động.

## 2. Phân biệt các thành phần của URL

Một URL công khai có thể gồm nhiều phần do các lớp khác nhau quản lý:

| Thành phần | Ví dụ | Nơi cấu hình |
| --- | --- | --- |
| Scheme công khai | `https` | TLS proxy và `X-Forwarded-Proto` hoặc `Forwarded` |
| Host công khai | `api.example.com` | DNS, proxy và `X-Forwarded-Host` |
| Port công khai | `443` | Listener của proxy và `X-Forwarded-Port` nếu cần |
| Proxy prefix | `/shop` | Route/rewrite của proxy và `X-Forwarded-Prefix` |
| Servlet context path | `/catalog` | `server.servlet.context-path` |
| Controller mapping | `/api/orders` | `@RequestMapping`, `@GetMapping`, `@PostMapping` |
| OpenAPI JSON path | `/openapi` | `springdoc.api-docs.path` |
| Swagger UI path | `/docs` | `springdoc.swagger-ui.path` |

Các thành phần này không thể thay thế lẫn nhau. `server.servlet.context-path` là context path của ứng dụng; `X-Forwarded-Prefix` mô tả prefix công khai mà proxy đã thêm hoặc loại bỏ; `springdoc.api-docs.path` là route của tài liệu OpenAPI; mapping của controller là path của API nghiệp vụ.

Không cộng cùng một prefix ở nhiều nơi. Nếu proxy giữ nguyên `/shop` khi forward, ứng dụng có thể nhận path đã có prefix và không cần xử lý như trường hợp proxy strip prefix. Nếu proxy strip `/shop`, ứng dụng cần biết prefix công khai đó để sinh lại link.

## 3. Chọn đúng forwarded header

Hai nhóm header phổ biến:

| Header | Ý nghĩa |
| --- | --- |
| `Forwarded` | Header theo RFC 7239, có thể mang `proto`, `host` và thông tin client |
| `X-Forwarded-For` | Địa chỉ client gốc theo quy ước phổ biến |
| `X-Forwarded-Host` | Host mà client đã truy cập |
| `X-Forwarded-Port` | Port công khai |
| `X-Forwarded-Proto` | Scheme gốc, thường là `https` hoặc `http` |
| `X-Forwarded-Ssl` | Một số proxy dùng để biểu thị trạng thái TLS |
| `X-Forwarded-Prefix` | Path prefix công khai mà proxy đã thêm, thay thế hoặc strip khi chuyển request |

`Forwarded` là chuẩn RFC 7239. Nhóm `X-Forwarded-*` là quy ước được nhiều proxy và cloud platform sử dụng. Hãy kiểm tra đúng header mà proxy của hệ thống đang gửi; không bật một cơ chế xử lý header khác với header thực tế.

Đối với springdoc sau reverse proxy, `X-Forwarded-Prefix` thường là phần dễ bị bỏ sót nhất. Ví dụ trình duyệt gọi `/shop/catalog/docs`, nhưng proxy chuyển đến ứng dụng tại `/catalog/docs`. Ứng dụng cần biết prefix `/shop` để tạo đường dẫn công khai chính xác.

## 4. Cấu hình reverse proxy với Nginx

Ví dụ Nginx nhận request dưới prefix `/shop/`, loại bỏ prefix đó khi chuyển đến ứng dụng tại cổng 8080, đồng thời truyền thông tin request công khai:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /shop/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Prefix /shop;
    }
}
~~~

Trong cấu hình này, dấu slash cuối của `location /shop/` và `proxy_pass .../` làm cho phần prefix khớp được thay bằng slash khi forward. Request công khai:

~~~text
https://api.example.com/shop/catalog/docs
~~~

được chuyển đến ứng dụng:

~~~text
http://127.0.0.1:8080/catalog/docs
~~~

Header `X-Forwarded-Prefix: /shop` giúp Spring dựng lại phần path công khai. Ví dụ dùng `$remote_addr` để proxy biên tự ghi địa chỉ client đã quan sát. Nếu hệ thống có nhiều proxy tin cậy, hãy thiết kế chuỗi client IP theo topology thực tế và chỉ nhận giá trị do các hop tin cậy ghi nhận.

Đây là ví dụ minh họa. Nếu một load balancer đứng trước Nginx và đã kết thúc TLS, `$scheme` hoặc `$server_port` tại Nginx có thể phản ánh kết nối nội bộ thay vì kết nối công khai. Khi đó, Nginx phải lấy giá trị public scheme/port từ upstream tin cậy theo cấu hình triển khai. Không sao chép header do client gửi thẳng vào mà không kiểm tra.

Nếu proxy giữ nguyên prefix `/shop` khi forward, không áp dụng cùng quy tắc strip prefix này. Hãy xác định path mà Spring thực sự nhận và cấu hình header sao cho prefix không bị cộng hai lần.

## 5. Cấu hình Spring Boot 3 và Spring Framework 6

Với Spring Boot 3.x, property điều khiển xử lý forwarded headers là `server.forward-headers-strategy`. Các giá trị chính:

| Giá trị | Hành vi |
| --- | --- |
| `none` | Không diễn giải forwarded headers |
| `native` | Dùng khả năng xử lý của embedded web server |
| `framework` | Dùng `ForwardedHeaderFilter` cho Servlet hoặc `ForwardedHeaderTransformer` cho WebFlux |

Nếu proxy chỉ gửi `X-Forwarded-For` và `X-Forwarded-Proto`, `native` có thể đủ tùy embedded server. Nếu cần hỗ trợ `X-Forwarded-Prefix` để khôi phục prefix bị strip, hãy kiểm tra khả năng của server và cân nhắc `framework`.

Ví dụ Spring Boot 3 với Spring MVC:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Với Tomcat và TLS kết thúc ở proxy, Spring Boot 3 có thêm lưu ý về redirect context root:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Chỉ thêm cấu hình Tomcat này khi đúng tình huống triển khai có TLS termination tại proxy. Nếu đang dùng Jetty hoặc Reactor Netty, kiểm tra thuộc tính tương ứng của embedded server thay vì sao chép cấu hình Tomcat.

Khi chọn `framework`, Spring Boot tự cấu hình cơ chế forwarded header phù hợp. Không đăng ký thêm một `ForwardedHeaderFilter` thứ hai nếu ứng dụng đã có filter do Boot tạo. Nếu ứng dụng không dùng Spring Boot auto-configuration, phải tự đăng ký filter một lần và bảo đảm thứ tự chạy trước các thành phần cần request URL đã được khôi phục.

## 6. Cấu hình Spring Boot 4 và Spring Framework 7

Spring Boot 4 sử dụng nhóm property mới cho forwarded header:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
        use-prefix: true
~~~

`strategy: web-server` giao việc diễn giải header cho embedded server nếu server hỗ trợ. `use-prefix: true` bật hỗ trợ `X-Forwarded-Prefix` ở cơ chế web-server. Spring Boot khuyến nghị dùng khả năng native của web server khi nó hỗ trợ đầy đủ header mà proxy đang gửi.

Nếu embedded server không hỗ trợ nhóm header cần thiết, có thể dùng cơ chế của Spring Framework:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
~~~

Với Servlet stack, Spring Framework dùng `ForwardedHeaderFilter`. Với reactive stack, Spring Framework dùng `ForwardedHeaderTransformer`. Spring Framework có tùy chọn riêng để bật xử lý `X-Forwarded-Prefix` trên forwarded-header component. Nếu tự đăng ký filter/transformer ngoài auto-configuration, bật tùy chọn prefix tương ứng trước khi đưa component vào chain. Nếu dùng Spring Boot, kiểm tra cách minor version đang dùng ánh xạ property prefix vào strategy `framework`; đừng giả định chỉ đổi strategy là mọi prefix đều được áp dụng.

Không chép nguyên `server.forward-headers-strategy` của Boot 3 sang Boot 4 mà không xác minh version. Hai thế hệ cấu hình có tên property khác nhau.

## 7. Phân biệt Servlet và WebFlux

Forwarded header support phụ thuộc web stack:

| Web stack | Cơ chế Spring Framework |
| --- | --- |
| Spring MVC / Servlet | `ForwardedHeaderFilter` |
| Spring WebFlux / Reactive | `ForwardedHeaderTransformer` |

Với Spring MVC, filter bọc request để các thành phần phía sau nhìn thấy scheme, host, port và path đã được khôi phục. Với WebFlux, transformer thực hiện vai trò tương tự trên reactive request.

Không đăng ký `ForwardedHeaderFilter` cho ứng dụng WebFlux. Cũng không thêm `ForwardedHeaderTransformer` vào Servlet stack. Nếu dùng Spring Boot, chọn strategy tương ứng và để Boot cấu hình thành phần đúng loại.

## 8. Bảo vệ forwarded headers tại ranh giới tin cậy

Forwarded headers có thể làm thay đổi cách ứng dụng nhận diện host, scheme, port, client IP và prefix. Chỉ proxy được tin cậy mới được quyền ghi các header này.

Tại proxy biên:

- Xóa hoặc ghi đè `Forwarded` và toàn bộ `X-Forwarded-*` do client bên ngoài tự gửi.
- Tạo lại các header từ thông tin request mà proxy thực sự quan sát.
- Chỉ tin các hop nội bộ đã được định nghĩa trong topology.
- Chặn truy cập trực tiếp từ Internet đến cổng ứng dụng nếu thiết kế yêu cầu mọi request phải qua proxy.
- Không đặt Tomcat trusted-proxy pattern thành cho phép mọi địa chỉ trong production.

Nếu ứng dụng tin một `X-Forwarded-Host` do người dùng tự gửi, họ có thể làm server sinh URL mang host giả. Điều này có thể gây link độc hại, redirect sai hoặc OpenAPI document chứa server URL không đáng tin.

Spring Framework khuyến nghị proxy tại edge phải reset cả `Forwarded` và `X-Forwarded-*`, kể cả khi chỉ sử dụng một trong hai nhóm. Cấu hình Spring cũng cần chọn đúng loại header mà proxy được phép gửi.

## 9. Phân biệt context path, proxy prefix và API path

Giả sử hệ thống có cấu hình:

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

Proxy công khai nhận prefix `/shop` rồi strip prefix trước khi forward. Các URL tương ứng:

| Mục tiêu | Path trong ứng dụng | Path công khai |
| --- | --- | --- |
| Swagger UI | `/catalog/docs` | `/shop/catalog/docs` |
| OpenAPI JSON | `/catalog/openapi` | `/shop/catalog/openapi` |
| Swagger config | `/catalog/openapi/swagger-config` | `/shop/catalog/openapi/swagger-config` |
| API controller | `/catalog/api/orders` | `/shop/catalog/api/orders` |

Trong ví dụ, `/shop` là proxy prefix, `/catalog` là context path, `/api/orders` là controller mapping. Nếu thay đổi một phần, cập nhật proxy route, forwarded header và URL được công bố tương ứng.

Nếu ứng dụng dùng context path `/catalog` nhưng controller mapping đã bắt đầu bằng `/catalog`, có thể bạn đang lặp prefix. Kiểm tra URL backend thực tế trước khi thêm path vào OpenAPI servers.

Với Spring WebFlux, base path của ứng dụng được cấu hình bằng `spring.webflux.base-path` thay vì `server.servlet.context-path`. Không dùng thuộc tính Servlet cho ứng dụng reactive.

## 10. Đặt path cho OpenAPI và Swagger UI

springdoc mặc định cung cấp OpenAPI JSON tại `/v3/api-docs` và Swagger UI tại `/swagger-ui.html` (thường redirect sang tài nguyên giao diện). Có thể đổi path:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Nếu ứng dụng có context path `/catalog` và proxy prefix `/shop`, URL công khai tương ứng là:

~~~text
https://api.example.com/shop/catalog/docs
https://api.example.com/shop/catalog/openapi
https://api.example.com/shop/catalog/openapi/swagger-config
~~~

`springdoc.swagger-ui.path` thay đổi route HTML của Swagger UI. `springdoc.api-docs.path` thay đổi endpoint OpenAPI. Chúng không thay đổi mapping của controller nghiệp vụ.

Nếu Swagger UI được cấu hình dùng một OpenAPI file tĩnh, `springdoc.swagger-ui.url` phải trỏ đến file mà trình duyệt truy cập được. Nếu dùng `springdoc.swagger-ui.config-url`, endpoint cấu hình cũng phải đi qua public route và prefix đúng. Đừng cấu hình một URL nội bộ như `http://127.0.0.1:8080/openapi` cho trình duyệt người dùng.

## 11. Cách springdoc tạo server URL

Khi không khai báo server tĩnh, springdoc có thể tự tạo server URL từ request. Vì vậy, thông tin request mà Spring nhìn thấy sau reverse proxy ảnh hưởng đến trường `servers` trong OpenAPI document.

Ví dụ OpenAPI JSON có thể chứa:

~~~json
{
  "servers": [
    {
      "url": "http://127.0.0.1:8080/catalog"
    }
  ],
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "Liệt kê đơn hàng"
      }
    }
  }
}
~~~

Nếu đây là document công khai, server URL trên không phù hợp. Trình duyệt sẽ cố gọi loopback của chính máy người dùng thay vì API công khai.

Sau khi xử lý forwarded headers đúng, server URL nên phản ánh địa chỉ public, ví dụ:

~~~json
{
  "servers": [
    {
      "url": "https://api.example.com/shop/catalog"
    }
  ],
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "Liệt kê đơn hàng"
      }
    }
  }
}
~~~

Trong ví dụ này, server base URL kết hợp với path `/api/orders` tạo thành `https://api.example.com/shop/catalog/api/orders`.

## 12. Khai báo server URL tĩnh khi domain công khai cố định

Nếu API luôn được công bố tại một domain và base path cố định, có thể khai báo server trong OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;

@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/shop/catalog",
            description = "Public API"
        )
    }
)
class OpenApiDefinitionConfiguration {
}
~~~

Khi server annotation hiện diện, springdoc sử dụng server được khai báo thay vì tự sinh URL từ request. Cách này phù hợp khi có một base URL công khai ổn định, ví dụ production domain duy nhất.

Không hard-code production URL nếu cùng artifact cần chạy ở nhiều môi trường có domain khác nhau. Có thể dùng cấu hình theo profile hoặc OpenAPI bean để đưa server URL theo môi trường. Bảo đảm server URL chứa đúng proxy prefix/context path và không lặp path đã có trong paths.

## 13. Dùng ServerBaseUrlCustomizer khi cần điều chỉnh URL sinh tự động

springdoc cung cấp `ServerBaseUrlCustomizer` để điều chỉnh server base URL được tạo tự động. Ví dụ tài liệu springdoc dùng nó để loại bỏ port không mong muốn hoặc chuẩn hóa URL hiển thị trong Swagger UI.

Trước khi viết customizer, kiểm tra:

1. Forwarded headers đã được xử lý đúng chưa?
2. Proxy đã gửi `X-Forwarded-Prefix` chưa?
3. Server URL hiện tại sai ở scheme, host, port hay path?
4. URL sai có phải do `@OpenAPIDefinition(servers = ...)` đang ghi đè URL tự sinh không?
5. Version springdoc đang dùng có chữ ký `ServerBaseUrlCustomizer` nào?

Customizer chỉ nên sửa phần sai đã xác định. Không dùng một chuỗi replace chung để thay mọi host/path nếu ứng dụng phục vụ nhiều môi trường. Nếu cùng ứng dụng có nhiều public host, cần kiểm tra cache và hành vi đồng thời trước khi tạo server URL phụ thuộc request.

## 14. Xử lý cache khi có nhiều proxy hoặc nhiều host công khai

springdoc mặc định tính toán OpenAPI document rồi cache kết quả. Đây là hành vi có lợi cho hiệu năng.

Tuy nhiên, một ứng dụng có thể được truy cập qua nhiều host hoặc nhiều proxy, ví dụ:

- Internal portal: `https://internal.example.net/catalog`
- Public portal: `https://api.example.com/shop/catalog`

Nếu server URL được sinh theo request đầu tiên và document được cache dùng chung, người dùng truy cập qua host khác có thể nhìn thấy server URL của host đầu tiên.

FAQ springdoc cung cấp property:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Tắt cache khiến OpenAPI document được tính lại theo request. Chỉ bật khi cần URL thay đổi theo host/proxy và đã đánh giá chi phí xử lý. Nếu domain công khai cố định hoặc dùng server annotation tĩnh, thường không cần tắt cache.

Đối với nhiều group, kiểm tra document của từng group. Mỗi group có endpoint riêng và có thể được cấu hình server/paths khác nhau.

## 15. Hiểu server base URL và paths trong Try it out

Swagger UI không tự suy ra địa chỉ API từ URL của trang HTML. Khi người dùng bấm Try it out, Swagger UI đọc OpenAPI document:

1. Chọn một entry trong `servers`.
2. Lấy path và method của operation.
3. Thay path parameter bằng giá trị người dùng nhập.
4. Thêm query parameter, header, body và authorization theo khai báo.
5. Gửi request đến URL kết hợp.

Ví dụ:

~~~yaml
servers:
  - url: https://api.example.com/shop/catalog
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
~~~

Khi người dùng nhập `orderId=ORD-100`, URL được gọi là:

~~~text
https://api.example.com/shop/catalog/api/orders/ORD-100
~~~

Nếu `servers[0].url` thiếu `/shop`, request sẽ bỏ qua proxy route. Nếu server URL đã có `/shop/catalog` nhưng path operation cũng chứa `/shop/catalog`, prefix bị lặp. Hãy đọc cả `servers` và `paths` để xác định URL cuối cùng.

## 16. Kiểm tra OpenAPI JSON qua domain công khai

Đừng chỉ gọi endpoint bằng localhost. Hãy kiểm tra qua domain và prefix mà người dùng thật sẽ truy cập:

~~~bash
curl -i \
  -H "Accept: application/json" \
  https://api.example.com/shop/catalog/openapi
~~~

Kiểm tra swagger-config:

~~~bash
curl -i \
  -H "Accept: application/json" \
  https://api.example.com/shop/catalog/openapi/swagger-config
~~~

Nếu dùng default path, thay `/openapi` bằng `/v3/api-docs`. Nếu đã cấu hình group, thử thêm tên group vào sau path API docs theo route group mà ứng dụng sinh.

Response OpenAPI phải có status thành công và JSON hợp lệ. Không chấp nhận một response 200 nhưng body là trang login HTML, trang lỗi của proxy hoặc trang welcome page.

## 17. Dùng jq kiểm tra server và paths

Có thể tải document về file rồi kiểm tra `servers` và `paths`:

~~~bash
curl --fail --silent --show-error \
  https://api.example.com/shop/catalog/openapi \
  -o openapi-public.json

jq '{servers: .servers, paths: (.paths | keys)}' openapi-public.json
~~~

Kiểm tra nhanh server URL:

~~~bash
jq -r '.servers[]?.url' openapi-public.json
~~~

Kiểm tra các path có prefix nội bộ hoặc prefix bị lặp:

~~~bash
jq -r '.paths | keys[]' openapi-public.json
~~~

Đối chiếu `servers[0].url` với URL công khai và `paths` với mapping controller. Không chỉ nhìn trang Swagger UI vì UI có thể tải được ngay cả khi server URL trong document sai.

## 18. Kiểm tra swagger-config

Swagger UI thường tải một tài liệu cấu hình riêng trước khi tải OpenAPI JSON. Với default path, endpoint là:

~~~text
/v3/api-docs/swagger-config
~~~

Nếu dùng custom path `/openapi`, kiểm tra:

~~~text
/openapi/swagger-config
~~~

Trong response, kiểm tra các trường URL hoặc danh sách URLs mà Swagger UI sẽ dùng. Với nhiều group, xác minh từng group URL có cùng public prefix và context path.

Nếu `swagger-config` trả 404 nhưng OpenAPI JSON hoạt động, kiểm tra `springdoc.swagger-ui.config-url`, custom API docs path và proxy rewrite. Nếu config URL trỏ đến domain nội bộ, Swagger UI sẽ gọi sai host ngay cả khi trang HTML đã được tải từ domain công khai.

## 19. Kiểm tra URL thực tế của Try it out trong trình duyệt

Sau khi mở Swagger UI qua public URL:

1. Mở Developer Tools của trình duyệt.
2. Chọn tab Network và bật Preserve log.
3. Tải lại Swagger UI.
4. Tìm request swagger-config.
5. Tìm request OpenAPI JSON.
6. Mở một operation và nhấn Try it out.
7. Nhập path/query parameter hợp lệ và thực thi request.
8. Xem Request URL, Request Method, Request Headers, Status Code và Response.

Request URL là bằng chứng quyết định. Nó phải dùng đúng HTTPS, domain công khai, proxy prefix, context path và controller path.

Nếu URL sai, kiểm tra `servers` trong OpenAPI JSON trước. Nếu `servers` đúng nhưng browser vẫn gọi sai, kiểm tra cấu hình Swagger UI, custom spec URL, group URL hoặc request interceptor.

## 20. Kiểm tra redirect và HTTPS termination

Nhiều hệ thống kết thúc TLS tại reverse proxy rồi chuyển HTTP nội bộ đến Spring Boot:

~~~text
Browser -- HTTPS --> Proxy -- HTTP --> Spring Boot
~~~

Nếu Spring chỉ nhìn thấy kết nối nội bộ, nó có thể tạo redirect `http://...` thay vì `https://...`. Trình duyệt có thể chặn request vì mixed content hoặc bị chuyển đến host/port nội bộ.

Kiểm tra:

- `X-Forwarded-Proto` hoặc `Forwarded: proto=https` có được proxy gửi không.
- Spring Boot có xử lý đúng header không.
- Tomcat có cần `server.tomcat.redirect-context-root=false` khi TLS termination không.
- Redirect Location có giữ public host, HTTPS và prefix không.
- Swagger UI OAuth redirect URL có dùng public HTTPS path không.

Không sửa bằng cách cho phép trình duyệt gọi HTTP nếu production bắt buộc HTTPS. Hãy sửa thông tin forwarded và redirect ở đúng lớp.

## 21. CORS khi Swagger UI và API khác origin

Nếu Swagger UI và API dùng cùng origin, ví dụ cùng `https://api.example.com` và chỉ khác path, browser thường không cần CORS chỉ vì path khác nhau.

Nếu UI ở `https://docs.example.com` còn API ở `https://api.example.com`, đây là hai origin khác nhau. Browser có thể gửi preflight OPTIONS trước request thật, đặc biệt khi có Authorization header hoặc method không đơn giản.

Kiểm tra:

- Origin của trang Swagger UI.
- Server URL trong OpenAPI.
- CORS allowlist của API.
- Allowed methods và headers, bao gồm Authorization và Content-Type khi cần.
- Credentials nếu dùng cookie/session.
- Proxy có forward OPTIONS đến ứng dụng hoặc trả preflight đúng không.

Không dùng wildcard origin cùng credentialed requests. Nếu API cần cookie/session, cấu hình origin cụ thể và chính sách credentials tương ứng.

## 22. Kiểm tra authentication và OAuth redirect

Một request Try it out trả 401 hoặc 403 có thể đã đi đúng URL nhưng thiếu quyền truy cập. Hãy tách lỗi định tuyến khỏi lỗi xác thực:

| Dấu hiệu | Kiểm tra |
| --- | --- |
| 404 | Proxy rewrite, context path, controller mapping |
| 401 | Token/session không có hoặc hết hạn |
| 403 | Principal đã xác thực nhưng thiếu quyền, CSRF hoặc policy gateway |
| CORS error | Preflight hoặc response thiếu CORS headers |
| 502/504 | Proxy không kết nối được backend hoặc backend timeout |

Với OAuth2, redirect URL phải khớp địa chỉ public mà browser dùng. Nếu Swagger UI được phục vụ dưới `/shop/catalog/docs`, OAuth redirect page cũng cần có prefix tương ứng. Cấu hình `springdoc.swagger-ui.oauth2-redirect-url` khi auto-detection không tạo đúng public URL.

Không đưa client secret production vào cấu hình Swagger UI công khai. Token chỉ nên được nhập qua cơ chế Authorize phù hợp và có thời hạn/quyền tối thiểu.

## 23. Kiểm tra nhiều OpenAPI group

Nếu ứng dụng có nhiều group, mỗi group có endpoint tài liệu riêng. Ví dụ group `public` và `partner`:

~~~yaml
springdoc:
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: partner
      paths-to-match:
        - /api/partner/**
~~~

Với API docs path mặc định, các document group thường được truy cập qua:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Nếu custom `springdoc.api-docs.path`, hãy kiểm tra route thực tế do ứng dụng sinh. Proxy phải forward cả default document lẫn group document, và Swagger UI Topbar phải trỏ đúng public URL của từng group.

Không chỉ kiểm tra group đầu tiên. Một group có thể có server URL hoặc path filter khác, khiến Try it out chỉ lỗi trên một phần tài liệu.

## 24. Ma trận kiểm tra trước khi công bố

| Lớp kiểm tra | Bằng chứng đạt |
| --- | --- |
| Proxy route | Request public được chuyển đúng path backend |
| Forwarded headers | Scheme, host, port và prefix phản ánh request công khai |
| Spring Boot | Strategy phù hợp với version và embedded server |
| Swagger UI HTML | Trả 200 hoặc redirect hợp lệ tại public URL |
| swagger-config | JSON hợp lệ, URL không trỏ vào host nội bộ |
| OpenAPI JSON | `servers` và `paths` ghép thành endpoint công khai |
| Try it out | Request URL dùng HTTPS, host và prefix chính xác |
| Security | Token, role, CSRF và CORS được xử lý đúng |
| Group | Mọi group URL đều truy cập được qua proxy |
| Trust boundary | Proxy xóa/ghi đè forwarded headers từ client không tin cậy |

## 25. Các lỗi thường gặp

**Swagger UI tải được nhưng Try it out gọi localhost.** Server URL trong OpenAPI được sinh từ request nội bộ. Cấu hình forwarded host/proto và kiểm tra `servers`.

**URL có http thay vì https.** Proxy kết thúc TLS nhưng không gửi `X-Forwarded-Proto` hoặc Spring không xử lý header đó.

**Thiếu prefix `/shop`.** Proxy strip prefix nhưng không gửi `X-Forwarded-Prefix`, hoặc ứng dụng chưa bật hỗ trợ prefix.

**Prefix xuất hiện hai lần.** Proxy giữ prefix trong path nhưng ứng dụng vẫn thêm forwarded prefix, hoặc server URL và operation path đều chứa cùng prefix.

**Swagger UI trả 404 sau khi đổi context path.** Kiểm tra `server.servlet.context-path`, `springdoc.swagger-ui.path`, `springdoc.api-docs.path` và proxy rewrite.

**swagger-config trả 404.** Cấu hình `config-url` chưa theo custom API docs path hoặc proxy chưa forward endpoint config.

**OpenAPI JSON đúng nhưng Try it out sai host.** Kiểm tra `servers`, server annotation và cấu hình `springdoc.swagger-ui.url`/`urls`.

**Một request đầu tiên làm server URL bị giữ cho host khác.** Kiểm tra springdoc cache khi cùng ứng dụng phục vụ nhiều host/proxy.

**Request bị browser chặn dù curl thành công.** Kiểm tra CORS, preflight, mixed content và redirect.

**Ứng dụng tin header do client tự gửi.** Cấu hình proxy biên xóa và ghi lại forwarded headers; không để client giả mạo host/proto/prefix.

**Đăng ký ForwardedHeaderFilter nhiều lần.** Nếu Spring Boot đã tự cấu hình theo strategy, không thêm một filter trùng lặp.

**Dùng property Boot 3 trong Boot 4.** Đối chiếu đúng version vì forwarded header property đã đổi tên.

## 26. Quy trình điều tra khi Try it out gọi sai URL

1. Ghi lại URL Swagger UI mà người dùng mở.
2. Gọi swagger-config qua public domain và xác định URL OpenAPI mà UI sẽ tải.
3. Tải OpenAPI JSON qua public domain.
4. Đọc `servers` và `paths` trong document.
5. Ghép server base URL với operation path để dự đoán URL cuối cùng.
6. Nhấn Try it out và so sánh dự đoán với Request URL trong Network tab.
7. Nếu sai scheme/host/port, kiểm tra `Forwarded` hoặc `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`.
8. Nếu sai prefix, kiểm tra `X-Forwarded-Prefix`, proxy rewrite và `use-prefix`.
9. Nếu sai context path, kiểm tra `server.servlet.context-path`.
10. Nếu document server đúng nhưng UI gọi sai, kiểm tra Swagger UI config URL, custom spec URL và group.
11. Nếu URL đúng nhưng status 401/403, điều tra authentication/authorization/CSRF.
12. Nếu URL đúng nhưng browser chặn, điều tra CORS, TLS và redirect.
13. Lặp lại với từng group và từng môi trường được công bố.

## 27. Checklist triển khai

- [ ] Xác định proxy strip prefix hay giữ nguyên prefix.
- [ ] Xác định scheme, host và port công khai.
- [ ] Ghi rõ proxy prefix, context path, controller mapping và springdoc paths.
- [ ] Cấu hình proxy gửi forwarded headers đúng.
- [ ] Proxy biên xóa hoặc ghi đè forwarded headers do client gửi.
- [ ] Chọn `server.forward-headers-strategy` cho Spring Boot 3.
- [ ] Chọn `server.request.header.forwarded.strategy` và `use-prefix` cho Spring Boot 4.
- [ ] Chọn Servlet filter hoặc Reactive transformer đúng stack.
- [ ] Không đăng ký forwarded filter trùng lặp.
- [ ] Kiểm tra server URL được sinh trong OpenAPI JSON.
- [ ] Nếu khai báo server tĩnh, bảo đảm URL đúng từng môi trường.
- [ ] Kiểm tra cache khi cùng service phục vụ nhiều public host.
- [ ] Kiểm tra Swagger UI, swagger-config và mọi group.
- [ ] Kiểm tra Try it out bằng Browser Network tab.
- [ ] Kiểm tra CORS, authentication, OAuth redirect và HTTPS.
- [ ] Chạy smoke test qua public domain, không chỉ qua localhost.

## 28. Kết luận

Triển khai springdoc sau reverse proxy cần khôi phục chính xác thông tin request công khai và path prefix mà proxy đã thay đổi. Hãy cấu hình proxy ghi forwarded headers, bật strategy phù hợp với Spring Boot version, phân biệt proxy prefix với servlet context path và controller mapping, rồi kiểm tra `servers` trong OpenAPI document. Try it out chỉ gọi đúng khi server base URL kết hợp với operation path tạo ra đúng public endpoint. Kiểm tra swagger-config, OpenAPI JSON và Request URL trong trình duyệt là cách xác nhận cuối cùng trước khi công bố tài liệu.

## 29. Nguồn tham khảo

- [springdoc-openapi FAQ — Deploy behind a reverse proxy](https://springdoc.org/faq.html): forwarded headers, `X-Forwarded-Prefix`, `ForwardedHeaderFilter`, `ServerBaseUrlCustomizer` và cache.
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`, native support và Framework filter.
- [Spring Boot 4.2 — Embedded Web Servers](https://docs.spring.io/spring-boot/4.2/how-to/webserver.html): `server.request.header.forwarded.strategy`, `use-prefix` và chiến lược xử lý forwarded headers.
- [Spring Framework 7 — Forwarded Headers](https://docs.spring.io/spring/reference/web/webmvc/filters.html#filters-forwarded-headers): `Forwarded`, `X-Forwarded-*`, `X-Forwarded-Prefix` và security considerations.
- [OpenAPI Specification 3.1 — Server Object](https://spec.openapis.org/oas/v3.1.1.html#server-object): server base URL và cách khai báo server cho API.
- [springdoc-openapi — Swagger UI properties](https://springdoc.org/v2/faq.html): path, config URL, OpenAPI URL, group URL và OAuth redirect properties.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): định dạng header Forwarded.
