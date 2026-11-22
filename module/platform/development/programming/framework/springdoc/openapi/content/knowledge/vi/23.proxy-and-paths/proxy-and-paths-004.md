# Reverse proxy, gateway và đường dẫn bên ngoài khác đường dẫn nội bộ

Trong môi trường triển khai, client thường không gọi trực tiếp Spring Boot service. Request đi qua reverse proxy, ingress hoặc API gateway trước khi đến ứng dụng. Lớp trung gian có thể kết thúc TLS, đổi host, thêm prefix công khai hoặc viết lại path trước khi chuyển tiếp request. Vì vậy, URL mà client nhìn thấy có thể khác URL mà Spring MVC nhận được.

Sự khác biệt này ảnh hưởng trực tiếp đến tài liệu OpenAPI và Swagger UI. Nếu ứng dụng chỉ nhận biết địa chỉ nội bộ, OpenAPI có thể sinh `servers` với host hoặc scheme sai; link trong response có thể trỏ đến service nội bộ; Swagger UI có thể gọi thiếu prefix hoặc gọi nhầm endpoint `swagger-config`. Cần cấu hình proxy và ứng dụng để chúng thống nhất cách nhận diện URL công khai.

## 1. Phân biệt URL công khai và URL nội bộ

Giả sử client truy cập API qua gateway:

```text
Client
  https://api.example.com/catalog/api/orders/42
             |
             v
Reverse proxy / API gateway
  host công khai: api.example.com
  prefix công khai: /catalog
  TLS: HTTPS
             |
             v
Spring Boot service
  http://catalog-service:8080/api/orders/42
```

Client nhìn thấy URL `https://api.example.com/catalog/api/orders/42`. Gateway chuyển tiếp đến ứng dụng qua mạng nội bộ bằng HTTP và có thể bỏ prefix `/catalog`. Spring Boot chỉ nhìn thấy `http://catalog-service:8080/api/orders/42` nếu proxy không chuyển tiếp metadata của request gốc.

| Thành phần | Giá trị công khai | Giá trị nội bộ |
| --- | --- | --- |
| Scheme | `https` | `http` sau TLS termination |
| Host | `api.example.com` | `catalog-service` |
| Port | `443` | `8080` |
| Prefix | `/catalog` | Có thể đã bị gateway loại bỏ |
| Path của controller | `/api/orders/42` | `/api/orders/42` |

Đây là hai góc nhìn hợp lệ của cùng một request. Ứng dụng cần biết metadata công khai khi tạo redirect, absolute URL, hypermedia link hoặc OpenAPI `servers`, nhưng vẫn định tuyến đến controller theo path nội bộ mà nó thực sự nhận.

## 2. Hai kiểu rewrite prefix thường gặp

Gateway có thể giữ nguyên prefix khi chuyển tiếp hoặc loại bỏ prefix trước khi gửi request đến ứng dụng. Hai cách này cần cấu hình khác nhau.

**Giữ nguyên prefix:**

```text
Public:  https://api.example.com/catalog/api/orders
Internal: http://catalog-service:8080/catalog/api/orders
```

Ứng dụng phải có context path hoặc route tương ứng với `/catalog`. Ví dụ `server.servlet.context-path=/catalog` khiến controller mapping `/api/orders` được truy cập dưới `/catalog/api/orders`.

**Loại bỏ prefix ở gateway:**

```text
Public:  https://api.example.com/catalog/api/orders
Internal: http://catalog-service:8080/api/orders
```

Gateway loại bỏ `/catalog` trước khi chuyển tiếp. Trong trường hợp này, ứng dụng vẫn xử lý path `/api/orders`; proxy cần chuyển metadata cho biết prefix công khai là `/catalog`, thường bằng `X-Forwarded-Prefix`.

Không cấu hình `server.servlet.context-path=/catalog` đồng thời với việc proxy đã giữ `/catalog` trong path mà không kiểm tra luồng thực tế. Nếu cả hai lớp cùng thêm prefix, request có thể thành `/catalog/catalog/api/orders` hoặc OpenAPI tạo URL lặp prefix.

## 3. Forwarded headers cho biết thông tin request gốc

Reverse proxy thường gửi các header mô tả request công khai:

| Header | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Forwarded` | Header chuẩn RFC 7239 mô tả thông tin proxy như host và proto | `for=192.0.2.10;host=api.example.com;proto=https` |
| `X-Forwarded-Host` | Host mà client dùng ở phía ngoài | `api.example.com` |
| `X-Forwarded-Proto` | Scheme công khai | `https` |
| `X-Forwarded-Port` | Port công khai | `443` |
| `X-Forwarded-For` | Địa chỉ IP client và các proxy trong chuỗi | `198.51.100.20` |
| `X-Forwarded-Prefix` | Prefix công khai đã bị proxy loại bỏ trước khi chuyển tiếp | `/catalog` |

`Forwarded` là header tiêu chuẩn; các header `X-Forwarded-*` là quy ước mở rộng được nhiều proxy và framework hỗ trợ. Không phải proxy nào cũng gửi mọi header. Cấu hình cần nhất quán với sản phẩm đang dùng và số lớp proxy trong đường đi.

Ứng dụng chỉ nên tin forwarded headers do reverse proxy đáng tin cậy tạo ra. Nếu client có thể gửi trực tiếp `X-Forwarded-Host: attacker.example` đến Spring Boot và ứng dụng tin header đó, URL được sinh ra có thể bị giả mạo. Proxy biên cần xóa hoặc ghi đè forwarded headers do client tự gửi, sau đó tạo giá trị mới dựa trên request thực tế.

## 4. Bật xử lý forwarded headers trong Spring Boot

Spring Boot có property `server.forward-headers-strategy` để chọn cách ứng dụng xử lý thông tin proxy:

```yaml
server:
  forward-headers-strategy: framework
```

Các giá trị thường dùng:

| Giá trị | Hành vi |
| --- | --- |
| `none` | Không áp dụng forwarded headers. Ứng dụng dùng thông tin request mà container nhận được. |
| `native` | Dùng khả năng xử lý forwarded headers của web server/container, nếu container hỗ trợ. |
| `framework` | Dùng cơ chế của Spring Framework; trong MVC là `ForwardedHeaderFilter`, còn WebFlux dùng `ForwardedHeaderTransformer`. |

Chọn `framework` khi muốn Spring Framework xử lý forwarded metadata nhất quán giữa các container được hỗ trợ. Chọn `native` khi hạ tầng và container đã được cấu hình để xử lý forwarded headers. Không bật nhiều cơ chế xử lý cùng lúc nếu chúng có thể áp dụng prefix hoặc host hai lần.

Khi proxy đã loại bỏ prefix công khai, hãy xác nhận framework nhận được `X-Forwarded-Prefix` và tái dựng context path công khai như mong muốn. Khi proxy giữ nguyên prefix trong request nội bộ, thường không cần thêm cùng prefix lần nữa bằng forwarded header.

`server.forward-headers-strategy=framework` không làm cho mọi forwarded header từ mọi nguồn trở nên an toàn. Chỉ bật khi ứng dụng nằm sau proxy tin cậy và đường truy cập trực tiếp đến ứng dụng được kiểm soát.

## 5. Cấu hình reverse proxy với Nginx

Ví dụ Nginx công bố service dưới prefix `/catalog`, đồng thời loại prefix này trước khi chuyển tiếp đến Spring Boot:

```nginx
location /catalog/ {
    proxy_pass http://catalog-service:8080/;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /catalog;
}
```

Với `location /catalog/` và `proxy_pass` có URI kết thúc bằng `/`, Nginx thay phần URI khớp location bằng URI trong `proxy_pass`; ví dụ `/catalog/api/orders` được chuyển thành `/api/orders`. `X-Forwarded-Prefix` cho ứng dụng biết prefix `/catalog` đã bị loại bỏ.

Trong ứng dụng:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
```

Đây là cấu hình minh họa cho topology prefix bị strip. Nếu Nginx giữ nguyên URI hoặc ứng dụng đã có context path, hãy điều chỉnh `proxy_pass`, `X-Forwarded-Prefix` và cấu hình server để không lặp prefix.

Không sao chép nguyên cấu hình này cho mọi gateway. Nginx, Kubernetes Ingress, Traefik, Envoy và Spring Cloud Gateway có cú pháp rewrite và cách tạo forwarded headers khác nhau. Điều cần giữ là thông tin host, scheme, port và prefix công khai phải phản ánh request mà client thực sự gửi.

## 6. Ảnh hưởng đến OpenAPI `servers`

OpenAPI dùng `servers` để mô tả base URL mà client dùng khi gọi các path trong document. Ví dụ:

```yaml
servers:
  - url: https://api.example.com/catalog
    description: Gateway công khai
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: Danh sách đơn hàng
```

Swagger UI kết hợp server URL với path của operation để tạo request. Với ví dụ trên, request sẽ đi đến `https://api.example.com/catalog/api/orders`.

Nếu springdoc suy ra server URL từ request nhưng ứng dụng chỉ nhìn thấy `http://catalog-service:8080`, Swagger UI có thể gọi nhầm host nội bộ hoặc dùng HTTP thay vì HTTPS. Xử lý forwarded headers giúp Spring nhận biết thông tin request gốc; sau đó phải kiểm tra `servers` trong document được sinh ra.

Khi URL công khai cố định và không thể suy ra đáng tin cậy từ request, có thể khai báo rõ server:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = @Server(
        url = "https://api.example.com/catalog",
        description = "Gateway công khai"
    )
)
class OpenApiServerConfiguration {}
```

Hoặc cấu hình bằng model `OpenAPI`:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Bean
OpenAPI storeOpenAPI() {
    return new OpenAPI()
        .addServersItem(new Server()
            .url("https://api.example.com/catalog")
            .description("Gateway công khai"));
}
```

Chỉ dùng URL tĩnh khi nó phù hợp với môi trường triển khai. Nếu local, staging và production có host khác nhau, hãy quản lý server URL theo profile hoặc cấu hình triển khai. Tránh ghi cố định host production vào tài liệu được dùng trong môi trường local.

## 7. Tránh thêm prefix hai lần

Một lỗi phổ biến là prefix xuất hiện đồng thời trong `servers.url` và `paths`:

```yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /catalog/api/orders:
    get:
      responses:
        '200':
          description: OK
```

Swagger UI sẽ ghép thành `/catalog/catalog/api/orders`. Nếu prefix `/catalog` đã nằm trong `servers.url`, path operation nên là `/api/orders` trong topology ví dụ.

Hãy áp dụng một quy tắc rõ ràng:

- `servers.url` chứa scheme, host, port và base prefix công khai.
- `paths` chứa path của operation tương đối với server base URL.
- Không lặp lại cùng prefix trong cả hai nơi.

Nếu gateway rewrite cả prefix lẫn path con, hãy mô tả URL công khai cuối cùng bằng cách kiểm tra request Swagger UI tạo ra, không suy luận chỉ từ mapping nội bộ.

## 8. Swagger UI và endpoint tài liệu cũng đi qua proxy

Khi Swagger UI được công bố dưới prefix `/catalog`, không chỉ API nghiệp vụ cần hoạt động. Gateway phải định tuyến được cả các endpoint tài liệu:

| URL công khai | URL nội bộ minh họa |
| --- | --- |
| `/catalog/swagger-ui.html` | `/swagger-ui.html` |
| `/catalog/swagger-ui/**` | `/swagger-ui/**` |
| `/catalog/v3/api-docs/swagger-config` | `/v3/api-docs/swagger-config` |
| `/catalog/v3/api-docs` | `/v3/api-docs` |
| `/catalog/v3/api-docs/{group}` | `/v3/api-docs/{group}` |

Nếu UI tải được HTML nhưng không tải được CSS/JavaScript, kiểm tra route `/swagger-ui/**`. Nếu trang hiển thị nhưng báo lỗi tải cấu hình, kiểm tra `swagger-config`. Nếu cấu hình tải được nhưng OpenAPI document trả `404`, kiểm tra URL `url`/`urls` và route của `/v3/api-docs`.

Nếu cấu hình `springdoc.api-docs.path` hoặc `springdoc.swagger-ui.path` khác mặc định, gateway và Spring Security phải dùng path đã tùy chỉnh. Với nhiều group, cần kiểm tra route có hỗ trợ cả URL JSON và YAML của từng group.

## 9. Context path khác với forwarded prefix

`server.servlet.context-path` đặt context path của ứng dụng Servlet. Ví dụ:

```yaml
server:
  servlet:
    context-path: /catalog
```

Controller mapping `/api/orders` sẽ được truy cập trong ứng dụng dưới `/catalog/api/orders`.

`X-Forwarded-Prefix` mô tả prefix công khai mà proxy đã loại bỏ hoặc thay đổi trước khi chuyển tiếp request. Ví dụ public path là `/catalog/api/orders`, nhưng ứng dụng nhận `/api/orders` và proxy gửi `X-Forwarded-Prefix: /catalog`.

Hai cách này không tương đương:

| Cơ chế | Ai áp dụng prefix? | Request path đến controller |
| --- | --- | --- |
| `server.servlet.context-path=/catalog` | Ứng dụng Servlet | Context path được container xử lý trước mapping controller. |
| `X-Forwarded-Prefix=/catalog` | Proxy cung cấp metadata; Spring xử lý forwarded headers | Ứng dụng có thể tái dựng URL công khai trong khi mapping nội bộ không chứa prefix. |

Với WebFlux, context path được cấu hình theo server reactive tương ứng; không giả định mọi property Servlet đều áp dụng cho WebFlux. Khi đổi stack hoặc container, kiểm tra property và cơ chế forwarded header đúng với runtime đang dùng.

## 10. Redirect, absolute link và TLS termination

Proxy thường kết thúc TLS ở biên rồi chuyển request HTTP vào mạng nội bộ. Nếu ứng dụng không biết scheme bên ngoài là HTTPS, nó có thể:

- Sinh redirect `Location: http://api.example.com/...` thay vì HTTPS.
- Tạo hypermedia link dùng `http://`.
- Công bố OpenAPI server URL dùng HTTP.
- Sinh callback hoặc URL tuyệt đối sai scheme.

Proxy cần gửi `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https`; ứng dụng cần xử lý forwarded headers. Nếu proxy chuyển tiếp sai scheme, sửa ở proxy trước khi thêm workaround trong controller.

Không tự tạo absolute URL bằng cách nối chuỗi `request.getScheme()`, `getServerName()` và path khi ứng dụng chưa xử lý forwarded headers. Ưu tiên các API xây dựng URI của Spring và link builder phù hợp; chúng có thể dùng request đã được điều chỉnh bởi forwarded metadata.

## 11. Nhiều proxy và ranh giới tin cậy

Một request có thể đi qua CDN, load balancer, ingress và gateway trước khi đến Spring Boot. Khi đó forwarded headers có thể chứa danh sách nhiều địa chỉ hoặc proxy có thể ghi đè một số header.

Hãy xác định proxy nào chịu trách nhiệm thiết lập từng giá trị:

1. Proxy biên loại bỏ forwarded headers do client gửi trực tiếp.
2. Proxy biên ghi lại host và proto công khai.
3. Các proxy nội bộ nối tiếp hoặc chuẩn hóa thông tin theo chính sách hạ tầng.
4. Ứng dụng chỉ nhận request từ proxy được tin cậy hoặc mạng nội bộ đã kiểm soát.

Không mở cổng service nội bộ trực tiếp ra Internet nếu ứng dụng tin forwarded headers mà không có lớp proxy đáng tin cậy. Nếu kẻ tấn công có thể gọi thẳng service và tự đặt `X-Forwarded-Host`, họ có thể tác động đến URL tuyệt đối được ứng dụng sinh ra.

Đặc biệt, không dùng forwarded host để xây dựng liên kết chứa dữ liệu nhạy cảm hoặc redirect đến domain bất kỳ mà không kiểm tra allowlist host công khai. Forwarded headers là metadata định tuyến, không phải nguồn dữ liệu người dùng được tin cậy.

## 12. Kiểm tra OpenAPI và Swagger UI sau proxy

Sau khi triển khai qua gateway, kiểm tra từ góc nhìn client bên ngoài, không chỉ gọi service nội bộ:

1. Gọi URL public của endpoint nghiệp vụ và xác nhận gateway chuyển đúng request đến controller.
2. Mở URL public của `/v3/api-docs` hoặc base path tùy chỉnh.
3. Kiểm tra `servers` có đúng HTTPS, host và prefix công khai.
4. Kiểm tra `paths` không lặp prefix và path ghép lại tạo đúng URL public.
5. Mở URL public của `/swagger-ui.html` và kiểm tra tài nguyên `/swagger-ui/**`.
6. Kiểm tra `swagger-config` trỏ đến URL tài liệu có thể truy cập từ trình duyệt.
7. Dùng Swagger UI **Try it out** và xem Request URL trong Network tab.
8. Kiểm tra response `Location`, hypermedia links và redirect có dùng scheme/host công khai.
9. Lặp lại với từng group document nếu ứng dụng có `GroupedOpenApi`.

Ví dụ gọi document qua gateway:

```bash
curl -i https://api.example.com/catalog/v3/api-docs
```

Kiểm tra riêng cấu hình Swagger UI:

```bash
curl -i https://api.example.com/catalog/v3/api-docs/swagger-config
```

Khi kiểm thử forwarded headers trực tiếp ở môi trường local, chỉ thực hiện trong mạng tin cậy:

```bash
curl -i http://localhost:8080/api/orders \
  -H 'Host: catalog-service:8080' \
  -H 'X-Forwarded-Host: api.example.com' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /catalog'
```

Lệnh này giúp quan sát cách ứng dụng xử lý forwarded metadata trong môi trường kiểm thử. Nó không thay thế việc xác nhận proxy thực tế xóa/ghi đè header từ client và bảo vệ đường truy cập trực tiếp đến service.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| OpenAPI `servers` trỏ đến hostname nội bộ | Ứng dụng không nhận `X-Forwarded-Host` hoặc chưa bật forwarded header strategy | Cấu hình proxy và `server.forward-headers-strategy`, rồi kiểm tra document. |
| `servers` dùng HTTP dù client truy cập HTTPS | Thiếu hoặc bỏ qua `X-Forwarded-Proto` | Proxy gửi proto công khai và Spring xử lý forwarded headers. |
| Swagger UI gọi thiếu prefix `/catalog` | Proxy strip prefix nhưng không gửi `X-Forwarded-Prefix`, hoặc `servers` thiếu base prefix | Đồng bộ rewrite, forwarded prefix và OpenAPI server URL. |
| URL có `/catalog/catalog` | Prefix được thêm ở context path, forwarded prefix và/hoặc `servers` nhiều lần | Chọn một mô hình prefix và kiểm tra path sau khi ghép server với operation. |
| Controller trả `404` sau khi đổi proxy | Proxy giữ prefix nhưng ứng dụng không có context path tương ứng, hoặc rewrite sai | Kiểm tra request URI thực tế đến ứng dụng và mapping controller. |
| Redirect `Location` trỏ về HTTP | Ứng dụng không nhận scheme HTTPS bên ngoài | Chuyển tiếp `X-Forwarded-Proto` và bật xử lý forwarded headers. |
| Hypermedia link dùng host nội bộ | Link builder dùng request chưa được điều chỉnh hoặc link bị hard-code | Kiểm tra forwarded host, request context và cách tạo link. |
| Swagger UI tải được nhưng document `404` | Gateway chưa route `/v3/api-docs` hoặc `swagger-config` trỏ URL nội bộ | Thêm route cho docs/config và dùng URL public hoặc relative phù hợp. |
| Group docs hoạt động ở local nhưng lỗi qua gateway | Chưa route path group hoặc YAML suffix | Kiểm tra JSON, `.yaml` và từng `/v3/api-docs/{group}`. |
| Host trong link có thể bị giả mạo | Ứng dụng tin forwarded headers từ nguồn không đáng tin | Chỉ cho phép traffic qua proxy tin cậy; proxy xóa và ghi lại header. |
| Port hoặc scheme không khớp sau nhiều proxy | Các lớp proxy ghi đè metadata không nhất quán | Xác định proxy có thẩm quyền và chuẩn hóa forwarded headers ở biên. |

## 14. Nguyên tắc áp dụng

- Ghi lại topology public-to-internal trước khi cấu hình proxy và springdoc.
- Quyết định gateway giữ prefix hay loại bỏ prefix; không áp dụng cả hai cách đồng thời.
- Chuyển tiếp host, scheme, port và prefix công khai bằng forwarded headers phù hợp.
- Chọn `server.forward-headers-strategy` đúng với container và kiến trúc proxy.
- Chỉ tin forwarded headers từ proxy được kiểm soát; loại bỏ header giả mạo do client gửi.
- Giữ `servers.url` làm base URL công khai và `paths` làm path operation tương đối, tránh lặp prefix.
- Chỉ khai báo server URL tĩnh khi phù hợp môi trường; quản lý host theo profile/deployment nếu cần.
- Route cả Swagger UI, tài nguyên tĩnh, `swagger-config` và OpenAPI JSON/YAML qua gateway.
- Kiểm tra redirect, `Location`, hypermedia link và Request URL của Swagger UI từ bên ngoài.
- Xác minh từng group document và cả endpoint JSON/YAML sau mỗi thay đổi proxy.

Reverse proxy và gateway tạo ra ranh giới giữa địa chỉ mà client sử dụng và địa chỉ mà Spring Boot nhận được. Khi proxy rewrite path, ứng dụng cần forwarded metadata đáng tin cậy để nhận diện host, scheme và prefix công khai; OpenAPI `servers` phải mô tả đúng base URL mà client gọi. Kiểm tra URL public từ bên ngoài cùng với request nội bộ giúp phát hiện sớm lỗi sai host, sai scheme, thiếu prefix hoặc prefix bị lặp trong Swagger UI và các liên kết response.

## Tài liệu tham khảo

- [Spring Boot – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/howto/webserver.html)
- [Spring Framework – Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object)
- [Nginx – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
