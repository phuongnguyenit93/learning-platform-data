# Lỗi mixed content, sai base URL và chuyển hướng lặp

Khi triển khai Spring Boot và springdoc-openapi sau reverse proxy, Swagger UI có thể tải được nhưng không lấy được OpenAPI document, hoặc trang tài liệu hiển thị endpoint với URL sai. Ba nhóm lỗi thường gặp là mixed content, base URL/path prefix không chính xác và redirect loop.

Các lỗi này thường xuất hiện khi proxy kết thúc TLS ở bên ngoài, thay đổi host hoặc thêm/bỏ một path prefix trước khi chuyển request đến ứng dụng. Spring Boot nhìn thấy request nội bộ khác với URL công khai mà trình duyệt đang sử dụng. Nếu forwarded header hoặc cấu hình OpenAPI không nhất quán, springdoc và Swagger UI có thể tạo ra liên kết sai.

## 1. Phân biệt các URL trong luồng Swagger UI

Một ứng dụng thường có ít nhất ba URL khác nhau:

| URL | Vai trò | Cấu hình liên quan |
|---|---|---|
| Public URL của Swagger UI | Địa chỉ người dùng mở trên trình duyệt | `springdoc.swagger-ui.path`, context path và reverse proxy |
| URL của OpenAPI document | Địa chỉ Swagger UI tải JSON/YAML | `springdoc.api-docs.path`, `springdoc.swagger-ui.url` |
| API server URL | Base URL dùng để tạo request khi nhấn Try it out | `servers` trong OpenAPI |

Ví dụ triển khai:

- Swagger UI: `https://docs.example.com/catalog/swagger-ui/index.html`
- OpenAPI JSON: `https://docs.example.com/catalog/v3/api-docs`
- API: `https://api.example.com/catalog/api/orders`

Ba URL có thể cùng host hoặc khác host. Không nên dùng `springdoc.swagger-ui.url` để sửa base URL của các operation; thuộc tính này chỉ định tài liệu mà giao diện cần tải. Base URL của API được mô tả trong trường `servers` của OpenAPI.

Nếu Swagger UI mở đúng nhưng Try it out gửi đến sai host, hãy kiểm tra `servers`. Nếu giao diện không tải được đặc tả, kiểm tra URL tài liệu. Nếu trình duyệt chuyển hướng liên tục trước khi trang hiển thị, hãy kiểm tra forwarded headers và redirect ở proxy/app.

## 2. Mixed content là gì?

Mixed content xảy ra khi một trang được tải qua HTTPS nhưng trình duyệt phải tải tài nguyên hoặc gọi endpoint qua HTTP không mã hóa. Các request chủ động như `fetch`, XHR và API call thường bị browser chặn khi trang HTTPS gọi URL HTTP.

Ví dụ:

- Swagger UI: `https://docs.example.com/swagger-ui/index.html`
- OpenAPI document: `http://api.example.com/v3/api-docs`
- API server trong OpenAPI: `http://api.example.com`

Trang Swagger UI được bảo vệ bằng HTTPS nhưng tài liệu hoặc API lại dùng HTTP. Kết quả có thể là:
- Swagger UI không tải được OpenAPI document.
- Try it out báo lỗi mixed content và không gửi request.
- OAuth2 authorize/token endpoint dùng HTTP bị browser chặn.
- Một request HTTPS bị redirect sang URL HTTP rồi bị chặn ở bước tiếp theo.

Cần kiểm tra toàn bộ URL mà trình duyệt sử dụng, không chỉ URL của trang Swagger UI. Bao gồm OpenAPI JSON/YAML, API server, OAuth2 authorization/token endpoint và các URL callback nếu có.

## 3. Cách nhận biết mixed content

Mở Developer Tools của trình duyệt:

1. Chọn tab **Console** và tìm thông báo `Mixed Content`.
2. Chọn tab **Network**, lọc Fetch/XHR.
3. Xem request nào đang dùng `http://` trong khi trang chính dùng `https://`.
4. Kiểm tra request bị chặn là OpenAPI document, API operation hay OAuth2 endpoint.
5. Mở response hoặc redirect chain của URL liên quan nếu browser cho phép.

Một lỗi mixed content thường xuất hiện trước khi request tới backend. Vì vậy log Spring Boot có thể không ghi nhận request mà browser đã chặn.

Không nên chỉ dựa vào `curl` để kết luận mixed content đã được sửa. `curl` không thực thi chính sách mixed content của browser. Hãy xác minh lại bằng browser Console và Network sau khi sửa URL.

## 4. Sửa mixed content bằng HTTPS URL công khai

Nếu Swagger UI và API ở cùng host, ưu tiên URL tương đối hoặc URL HTTPS công khai nhất quán. Nếu API ở host riêng, khai báo server HTTPS rõ ràng.

Ví dụ OpenAPI server:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "https://api.example.com/catalog",
            description = "Public API"
        )
    }
)
class OpenApiConfiguration {
}
~~~

Trong ví dụ, operation path có thể là `/api/orders`, vì vậy URL cuối cùng được gọi là:

~~~text
https://api.example.com/catalog/api/orders
~~~

Nếu tài liệu và API cùng origin, có thể dùng server URL tương đối:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;

@OpenAPIDefinition(
    servers = @Server(
        url = "/catalog",
        description = "API qua public gateway"
    )
)
class OpenApiConfiguration {
}
~~~

Đây là cách thay thế cho ví dụ server URL tuyệt đối phía trên; chọn một cấu hình phù hợp thay vì khai báo hai class cùng tên. URL tương đối được browser phân giải dựa trên origin hiện tại của tài liệu. Chỉ dùng cách này khi public path của API thực sự nằm dưới prefix `/catalog`. Nếu API có host riêng, khai báo URL HTTPS đầy đủ.

Nếu cấu hình URL của OpenAPI document bằng `springdoc.swagger-ui.url`, hãy bảo đảm URL đó cũng dùng HTTPS hoặc là URL tương đối hợp lệ:

~~~yaml
springdoc:
  swagger-ui:
    url: https://api.example.com/catalog/v3/api-docs
~~~

Không cấu hình URL HTTP rồi trông chờ browser tự nâng cấp an toàn. Một số chính sách browser hoặc proxy có thể thay đổi cách xử lý, nhưng cấu hình đúng ngay từ đầu vẫn là cách đáng tin cậy.

## 5. Vì sao Spring Boot tạo sai scheme hoặc host sau TLS termination?

Trong kiến trúc phổ biến, TLS được kết thúc ở reverse proxy hoặc load balancer:

~~~text
Browser -- HTTPS --> Reverse proxy -- HTTP --> Spring Boot
~~~

Trình duyệt gửi HTTPS đến proxy. Proxy giải mã TLS rồi chuyển tiếp request nội bộ bằng HTTP. Nếu proxy không truyền thông tin scheme/host công khai, Spring Boot chỉ nhìn thấy kết nối HTTP nội bộ và có thể tạo URL như:

`http://internal-app:8080/v3/api-docs`

hoặc tạo redirect về HTTP.

Để ứng dụng biết URL gốc, proxy cần gửi forwarded headers. Những header thường gặp:

| Header | Ý nghĩa |
|---|---|
| `Forwarded` | Header chuẩn RFC 7239 mô tả thông tin proxy như `proto` và `host` |
| `X-Forwarded-Proto` | Scheme bên ngoài, ví dụ `https` |
| `X-Forwarded-Host` | Host công khai mà client truy cập |
| `X-Forwarded-Port` | Port công khai |
| `X-Forwarded-For` | Địa chỉ IP client qua chuỗi proxy |
| `X-Forwarded-Prefix` | Prefix công khai mà proxy thêm hoặc dùng khi rewrite path |

Proxy phải thiết lập các giá trị này dựa trên request đã nhận. Ở edge proxy, hãy xóa hoặc ghi đè forwarded header do client bên ngoài tự gửi rồi đặt lại giá trị đáng tin cậy. Đồng thời giới hạn kết nối trực tiếp đến backend để client không thể bỏ qua proxy và tự cung cấp các header giả mạo.

## 6. Cấu hình forwarded headers trong Spring Boot

Spring Boot cung cấp thuộc tính `server.forward-headers-strategy` để quyết định cách ứng dụng xử lý forwarded headers.

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các lựa chọn thường gặp:

| Giá trị | Cách xử lý | Khi dùng |
|---|---|---|
| `none` | Không xử lý forwarded headers | Ứng dụng không nằm sau proxy hoặc không muốn dùng thông tin proxy |
| `native` | Dùng cơ chế của web server/container | Khi container hỗ trợ và cấu hình native phù hợp |
| `framework` | Dùng Spring Framework forwarded-header support | Khi cần xử lý `Forwarded`/`X-Forwarded-*`, đặc biệt khi có prefix |

Với `framework`, Spring sử dụng `ForwardedHeaderFilter` trong Servlet stack hoặc `ForwardedHeaderTransformer` trong WebFlux để điều chỉnh scheme, host, port và các thông tin request dựa trên forwarded headers. Điều này giúp các thành phần tạo URL hoặc redirect nhìn thấy thông tin public thay vì thông tin kết nối nội bộ.

Với Tomcat, `native` có thể dùng `RemoteIpValve` cho các forwarded header mà container hỗ trợ. Khả năng xử lý prefix và chi tiết phụ thuộc container/version. Nếu kiến trúc cần `X-Forwarded-Prefix`, hãy xác minh strategy đang dùng thực sự xử lý prefix; `framework` thường là lựa chọn phù hợp cho trường hợp cần hỗ trợ forwarded header ở tầng Spring.

Không bật xử lý forwarded headers nếu backend có thể được truy cập trực tiếp từ mạng không tin cậy và proxy không loại bỏ header giả mạo. Forwarded header ảnh hưởng đến thông tin request mà ứng dụng tin là public.

## 7. Cấu hình reverse proxy truyền đúng thông tin public

Ví dụ Nginx kết thúc HTTPS, nhận public path `/catalog/`, sau đó bỏ prefix `/catalog/` trước khi chuyển request đến Spring Boot tại root:

~~~nginx
server {
    listen 443 ssl;
    server_name docs.example.com;

    location /catalog/ {
        proxy_pass http://127.0.0.1:8080/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Prefix /catalog;
    }
}
~~~

Trong cấu hình này, dấu `/` cuối của `proxy_pass` khiến Nginx thay phần URI khớp với location bằng `/` khi chuyển tiếp. Vì vậy request:

~~~text
/catalog/v3/api-docs
~~~

được chuyển đến backend dưới dạng:

~~~text
/v3/api-docs
~~~

`X-Forwarded-Prefix: /catalog` cho Spring biết public URL có prefix `/catalog`. Kết hợp với `server.forward-headers-strategy: framework`, ứng dụng có thể tạo liên kết phản ánh URL công khai.

Nếu proxy giữ nguyên prefix và chuyển `/catalog/...` đến backend, cấu hình backend phải được thiết kế để xử lý prefix đó. Không vừa giữ prefix trong path backend, vừa thêm `X-Forwarded-Prefix` theo cách làm path bị lặp.

Chỉ chọn một chiến lược rewrite rõ ràng:
- Proxy bỏ prefix: backend xử lý path nội bộ, forwarded prefix mô tả prefix public.
- Proxy giữ prefix: backend phải nhận diện prefix theo cấu hình ứng dụng; tránh thêm lại cùng prefix lần thứ hai.

## 8. Phân biệt context path, proxy prefix và springdoc path

Các thuộc tính sau giải quyết những vấn đề khác nhau:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `server.servlet.context-path` | Context path của ứng dụng Spring MVC/Servlet | `/app` |
| `spring.webflux.base-path` | Base path của ứng dụng WebFlux | `/app` |
| `springdoc.api-docs.path` | Đường dẫn endpoint cung cấp OpenAPI document | `/v3/api-docs` |
| `springdoc.swagger-ui.path` | Đường dẫn mở Swagger UI | `/swagger-ui.html` |
| `springdoc.swagger-ui.url` | URL tài liệu mà Swagger UI tải | `/app/v3/api-docs` hoặc URL HTTPS |
| OpenAPI `servers` | Base URL dùng để gọi API operations | `/catalog` hoặc `https://api.example.com/catalog` |

Không dùng `springdoc.api-docs.path` để sửa base path của API nghiệp vụ. Ví dụ đổi endpoint tài liệu sang `/openapi` không có nghĩa endpoint `/api/orders` cũng chuyển thành `/openapi/orders`.

Tương tự, `springdoc.swagger-ui.path` chỉ đổi đường dẫn vào giao diện. Nó không tự đổi public base URL của API.

Ví dụ cấu hình:

~~~yaml
server:
  servlet:
    context-path: /app
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
~~~

Khi có context path `/app`, endpoint nội bộ có thể là `/app/v3/api-docs`. Nếu proxy còn thêm public prefix `/catalog`, URL bên ngoài có thể là `/catalog/app/v3/api-docs`, tùy cách proxy rewrite. Hãy xác định rõ từng lớp path trước khi cấu hình URL tài liệu.

## 9. Sai base URL trong OpenAPI servers

Khi nhấn Try it out, Swagger UI kết hợp URL trong `servers` với path của operation.

Ví dụ:

~~~yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /api/orders:
    get:
      responses:
        "200":
          description: OK
~~~

Request URL kết quả:

~~~text
https://api.example.com/catalog/api/orders
~~~

Nếu `servers.url` đã chứa `/catalog/api` nhưng operation path cũng bắt đầu bằng `/api`, URL cuối cùng có thể thành:

~~~text
https://api.example.com/catalog/api/api/orders
~~~

Đây là lỗi lặp prefix. Hãy quyết định prefix thuộc `servers` hay thuộc operation path và chỉ khai báo một lần.

Nếu `servers` bị sinh thành `http://localhost:8080`, kiểm tra:
1. Proxy có gửi `X-Forwarded-Proto` và `X-Forwarded-Host` không?
2. Spring Boot có xử lý forwarded headers không?
3. Proxy có gửi `X-Forwarded-Prefix` khi rewrite path không?
4. Có `@OpenAPIDefinition(servers = ...)` hoặc OpenAPI bean đang ghi đè server URL không?
5. Có cấu hình theo profile hoặc customizer tạo URL nội bộ không?

Một cấu hình `servers` tĩnh có thể hữu ích khi public API URL cố định. Với nhiều môi trường, cân nhắc server URL tương đối hoặc cấu hình theo profile/environment để tránh dùng nhầm host staging và production.

## 10. Cấu hình nhiều môi trường mà không hard-code nhầm URL

Có thể quản lý URL công khai qua cấu hình theo môi trường. Ví dụ:

~~~yaml
# application-dev.yml
app:
  public-api-url: http://localhost:8080

# application-prod.yml
app:
  public-api-url: https://api.example.com/catalog
~~~

Một cấu hình OpenAPI có thể dùng property này:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiServerConfig {

    @Bean
    OpenAPI publicServerOpenApi(
            @Value("${app.public-api-url}") String publicApiUrl) {
        return new OpenAPI()
            .addServersItem(new Server().url(publicApiUrl));
    }
}
~~~

Đây là một cách khai báo server URL tường minh. Nếu ứng dụng đã có bean `OpenAPI` khác, hãy hợp nhất cấu hình thay vì tạo nhiều bean cạnh tranh. Với môi trường mà UI và API cùng origin, server URL tương đối có thể đơn giản hơn và giảm phụ thuộc hostname.

Không để cấu hình production trỏ về `localhost`, hostname container hoặc HTTP nội bộ. Các địa chỉ đó có thể hợp lệ trong mạng backend nhưng không thể được browser của người dùng truy cập.

## 11. Redirect loop thường xảy ra như thế nào?

Redirect loop là chuỗi redirect lặp giữa proxy và ứng dụng, hoặc giữa hai URL canonical. Một trường hợp điển hình:

1. Browser gọi `https://docs.example.com/swagger-ui.html`.
2. Proxy kết thúc TLS rồi chuyển request nội bộ bằng HTTP.
3. Spring Security hoặc ứng dụng thấy request là HTTP và redirect sang HTTPS.
4. Browser đã dùng HTTPS, nhưng proxy lại chuyển tiếp request nội bộ bằng HTTP.
5. Ứng dụng tiếp tục cho rằng request chưa an toàn và redirect lần nữa.

Chuỗi có thể lặp cho đến khi browser báo `ERR_TOO_MANY_REDIRECTS`.

Một dạng khác là prefix bị thêm hai lần:
- Proxy chuyển `/catalog/swagger-ui.html` thành `/swagger-ui.html`.
- Ứng dụng redirect đến `/catalog/swagger-ui/index.html`.
- Proxy hoặc filter lại thêm `/catalog`, tạo thành `/catalog/catalog/...`.
- URL bị rewrite hoặc redirect qua lại giữa hai dạng.

Redirect cũng có thể lặp khi proxy ép host canonical trong khi ứng dụng lại redirect về host khác, hoặc khi dấu slash cuối path bị xử lý không thống nhất.

## 12. Sửa redirect loop do HTTPS termination

Nếu proxy là nơi kết thúc TLS và backend kết nối HTTP, cần truyền scheme công khai:

~~~nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
~~~

Đồng thời cấu hình Spring Boot xử lý forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Sau đó kiểm tra:
- Ứng dụng có nhận scheme `https` sau khi forwarded header được xử lý không.
- Spring Security có đang ép HTTPS dù request đã được nhận diện là HTTPS không.
- Proxy có redirect HTTP sang HTTPS ở đúng public boundary không.
- Backend có đang tự redirect dựa trên thông tin scheme nội bộ không.

Nên có một nơi chịu trách nhiệm chính cho redirect HTTP → HTTPS, thường là edge proxy/load balancer. Nếu ứng dụng cũng thực hiện redirect, nó phải nhận đúng forwarded scheme để không redirect lại request đã HTTPS.

Không tắt HTTPS enforcement một cách tùy tiện để che lỗi. Hãy sửa thông tin forwarded và bảo đảm backend chỉ tin header đến từ proxy đáng tin cậy.

## 13. Sửa redirect loop do path prefix

Trước tiên, ghi lại từng URL trong redirect chain:
- URL browser yêu cầu đầu tiên.
- Status `301`, `302`, `307` hoặc `308`.
- Header `Location` của mỗi response.
- Path mà proxy gửi đến backend.
- Path mà ứng dụng tạo ra trong redirect.

Nếu proxy strip prefix, cấu hình forwarded prefix phù hợp. Nếu proxy giữ prefix, đừng thêm lại prefix bằng một lớp khác. Đối chiếu `server.servlet.context-path` hoặc `spring.webflux.base-path` với path rewrite thực tế.

Với Swagger UI, cũng kiểm tra redirect từ `/swagger-ui.html` sang tài nguyên `/swagger-ui/**`. Nếu cấu hình `springdoc.swagger-ui.path` là path tùy chỉnh, hãy kiểm tra URL redirect cuối cùng có chứa public prefix đúng một lần hay không.

## 14. Quy trình chẩn đoán theo triệu chứng

| Triệu chứng | Nơi kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Swagger UI báo Mixed Content | Browser Console/Network | Thay URL HTTP bằng HTTPS hoặc URL tương đối đúng |
| UI mở được nhưng không tải spec | Request OpenAPI JSON/YAML | Kiểm tra `springdoc.swagger-ui.url`, docs path, context path và CORS nếu khác origin |
| Try it out gọi `localhost` hoặc host nội bộ | `servers` trong OpenAPI | Sửa forwarded headers hoặc server URL |
| URL có prefix lặp hai lần | Request URL và proxy rewrite | Chỉ thêm prefix ở một lớp |
| URL sinh ra dùng HTTP dù public là HTTPS | `X-Forwarded-Proto`, `server.forward-headers-strategy` | Truyền và xử lý forwarded scheme |
| Browser báo `ERR_TOO_MANY_REDIRECTS` | Redirect chain và `Location` | Tìm hai lớp đang redirect qua lại |
| Swagger UI redirect sai path | `springdoc.swagger-ui.path`, context path và forwarded prefix | Đồng bộ public path với backend path |
| OpenAPI JSON tải được nhưng operation URL sai | `servers` | Sửa base URL của API, không đổi docs path |

## 15. Các lệnh kiểm tra hữu ích

Kiểm tra response header của Swagger UI hoặc OpenAPI document:

~~~bash
curl -sS -D - -o /dev/null https://docs.example.com/catalog/v3/api-docs
~~~

Theo dõi redirect chain và giới hạn số lần redirect:

~~~bash
curl -sS -D - -o /dev/null -L --max-redirs 10 \
  https://docs.example.com/catalog/swagger-ui.html
~~~

Nếu lệnh kết thúc với lỗi vượt giới hạn redirect, kiểm tra các header `Location` được in ra để tìm vòng lặp.

Tải OpenAPI document và tìm `servers`:

~~~bash
curl -sS https://docs.example.com/catalog/v3/api-docs
~~~

Kiểm tra:
- URL trong phần tử đầu tiên của mảng `servers` có phải public URL mà browser truy cập được không.
- Scheme có phải HTTPS khi UI chạy HTTPS không.
- Prefix có xuất hiện đúng một lần không.
- Path của operation có bị lặp base path không.

Các lệnh trên kiểm tra response từ server; mixed content vẫn cần được xác minh trong browser. Nếu API cần xác thực, hãy dùng credential thử nghiệm an toàn và không đưa token vào log hoặc lệnh được chia sẻ.

## 16. Checklist cấu hình proxy và Springdoc

- [ ] Swagger UI được mở bằng HTTPS trong môi trường public.
- [ ] OpenAPI document URL dùng HTTPS hoặc URL tương đối đúng.
- [ ] Mọi API server URL trong `servers` đều truy cập được từ browser.
- [ ] OAuth2 authorization/token URL không dùng HTTP trên trang HTTPS.
- [ ] Proxy truyền `X-Forwarded-Proto`, `X-Forwarded-Host` và port phù hợp.
- [ ] `server.forward-headers-strategy` được chọn theo container và nhu cầu prefix.
- [ ] Proxy loại bỏ hoặc ghi đè forwarded header do client tự gửi.
- [ ] `X-Forwarded-Prefix` chỉ được dùng khi phù hợp với cách proxy rewrite.
- [ ] Context path, WebFlux base path, docs path và UI path được phân biệt rõ.
- [ ] Base path không bị thêm hai lần giữa `servers` và operation path.
- [ ] Chỉ một lớp chịu trách nhiệm chính cho redirect HTTP → HTTPS.
- [ ] Redirect chain không lặp host, scheme hoặc prefix.
- [ ] Đã kiểm tra `/v3/api-docs` và `servers` sau khi triển khai.
- [ ] Đã xác minh Console và Network trên browser thực tế.

## Tài liệu tham khảo

- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/howto/webserver.html#howto.webserver.use-behind-a-proxy-server): cấu hình forwarded headers khi chạy sau reverse proxy.
- [Spring Framework – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers): cách Spring xử lý forwarded headers và thông tin request gốc.
- [springdoc-openapi – Properties](https://springdoc.org/properties.html): cấu hình API docs path, Swagger UI path và URL tài liệu.
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object): ý nghĩa và cách phân giải server URL.
- [MDN – Mixed Content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content): cách browser xử lý tài nguyên HTTP trên trang HTTPS.
- [MDN – HTTP Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Redirections): status redirect và header Location.
