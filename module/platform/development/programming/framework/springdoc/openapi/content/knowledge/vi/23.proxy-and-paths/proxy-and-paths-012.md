# Đối chiếu đường dẫn trên local, môi trường thử nghiệm và production

Một API Spring Boot có thể chạy ở `http://localhost:8080/api/orders` trên máy lập trình, ở `https://test.example.com/order-service/api/orders` trong môi trường thử nghiệm và ở `https://api.example.com/api/orders` trong production. Controller có thể dùng cùng một mapping, nhưng host, scheme, port, context path và prefix do reverse proxy quản lý lại khác nhau.

Khi tích hợp springdoc-openapi, sự khác biệt này ảnh hưởng cả URL gọi API lẫn các endpoint tài liệu như `/v3/api-docs`, `/v3/api-docs.yaml` và Swagger UI. Nếu cấu hình proxy hoặc forwarded headers sai, Swagger UI có thể tải được trang nhưng không lấy được OpenAPI document, hoặc tài liệu sinh ra `servers` trỏ đến hostname nội bộ, HTTP thay vì HTTPS hay một prefix bị lặp.

## 1. Phân biệt các phần tạo nên URL

Một URL mà client gọi thường có cấu trúc:

```text
scheme://host:port/public-prefix/context-path/servlet-path/controller-mapping
```

Các thành phần có ý nghĩa khác nhau:

| Thành phần | Ví dụ | Nơi thường được cấu hình |
|---|---|---|
| Scheme | `https` | TLS termination tại proxy/load balancer hoặc ứng dụng |
| Host | `api.example.com` | DNS, reverse proxy, forwarded host |
| Port | `443` | Listener công khai hoặc forwarded port |
| Public prefix | `/order-service` | Gateway/Ingress/reverse proxy |
| Servlet context path | `/app` | `server.servlet.context-path` với Spring MVC |
| WebFlux base path | `/app` | `spring.webflux.base-path` với Spring WebFlux |
| Servlet path | `/api` | Servlet mapping trong ứng dụng MVC nếu được cấu hình |
| Controller mapping | `/orders` | `@RequestMapping`, `@GetMapping`... |

Không phải ứng dụng nào cũng dùng tất cả các phần trên. Một project đơn giản có thể chỉ có host, port và controller mapping. Một ứng dụng phía sau gateway có thể có thêm public prefix do proxy xử lý.

Trong Spring MVC, `server.servlet.context-path` đặt context path cho ứng dụng servlet. Trong Spring WebFlux, `spring.webflux.base-path` đặt base path cho các handler reactive. Hai thuộc tính này thuộc hai web stack khác nhau; không cấu hình cả hai chỉ để xử lý cùng một prefix.

## 2. Đường dẫn public và đường dẫn upstream

Reverse proxy thường nhận URL công khai rồi chuyển request đến địa chỉ nội bộ của Spring Boot. Đường dẫn mà client nhìn thấy có thể khác đường dẫn mà ứng dụng nhận.

Ví dụ public URL:

```text
https://test.example.com/order-service/api/orders
```

Proxy có thể chuyển tiếp theo một trong hai cách:

| Kiểu proxy | Request path ứng dụng nhận | Prefix public |
|---|---|---|
| Giữ nguyên prefix | `/order-service/api/orders` | Ứng dụng phải phục vụ path có prefix này hoặc có context/base path tương ứng |
| Gỡ prefix trước khi proxy | `/api/orders` | Proxy cần chuyển thông tin prefix đã gỡ bằng forwarded header nếu ứng dụng cần dựng lại URL public |

Điều quan trọng là thống nhất nơi chịu trách nhiệm cho prefix. Nếu proxy đã gỡ `/order-service`, không nên đồng thời cấu hình ứng dụng tự thêm lại cùng prefix vào route runtime mà không có chủ đích. Ngược lại, nếu proxy giữ nguyên prefix thì ứng dụng phải có mapping phù hợp.

## 3. Ví dụ cùng một controller chạy ở ba môi trường

Giả sử controller có mapping:

```java
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    List<OrderResponse> listOrders() {
        return orderService.findAll();
    }
}
```

Nếu ứng dụng không có context path hoặc WebFlux base path, đường dẫn upstream là `/api/orders`. Ba môi trường có thể được bố trí như sau:

| Môi trường | URL public | URL upstream |
|---|---|---|
| Local | `http://localhost:8080/api/orders` | `http://localhost:8080/api/orders` |
| Test | `https://test.example.com/order-service/api/orders` | `http://order-app:8080/api/orders` |
| Production | `https://api.example.com/api/orders` | `http://order-app:8080/api/orders` |

Trong test, gateway gỡ prefix `/order-service` trước khi gửi đến app. Production không có prefix riêng nên public path trùng với path upstream. Controller không cần đổi mapping giữa các môi trường.

Đây là mô hình minh họa. Cấu hình thực tế phụ thuộc gateway, ingress, context path và servlet/base path mà hệ thống chọn.

## 4. Hai kiểu cấu hình reverse proxy phổ biến

### Giữ nguyên prefix khi chuyển tiếp

Nếu proxy giữ nguyên toàn bộ path, request đến `/order-service/api/orders` sẽ được chuyển đến ứng dụng với cùng path. Khi đó ứng dụng cần phục vụ prefix `/order-service`, chẳng hạn bằng context path hoặc route prefix phù hợp.

Ví dụ Nginx chuyển tiếp nguyên URI:

```nginx
location /order-service/ {
    proxy_pass http://order_app;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Với `proxy_pass` không có URI phía sau upstream trong cấu hình trên, Nginx chuyển tiếp URI hiện tại theo quy tắc proxy_pass không kèm phần URI. Hãy xác nhận hành vi rewrite của cấu hình Nginx thực tế, đặc biệt nếu có thêm `rewrite` hoặc location lồng nhau.

### Gỡ prefix trước khi chuyển tiếp

Nếu ứng dụng chỉ phục vụ `/api/**`, proxy có thể gỡ `/order-service` khỏi public path và gửi phần còn lại đến app:

```nginx
location /order-service/ {
    proxy_pass http://order_app/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /order-service;
}
```

Trong cấu hình này, dấu `/` ở cuối `proxy_pass http://order_app/` khiến phần URI khớp với location `/order-service/` được thay bằng `/` khi chuyển tiếp. Ví dụ `/order-service/api/orders` được gửi đến upstream dưới dạng `/api/orders`. `X-Forwarded-Prefix` cho ứng dụng biết prefix công khai đã được proxy gỡ.

Không sao chép nguyên xi cấu hình này nếu gateway của bạn giữ prefix hoặc có nhiều lớp proxy. Cần kiểm tra path trước và sau từng lớp rewrite.

## 5. Forwarded headers mang thông tin URL bên ngoài

Khi TLS kết thúc tại load balancer, ứng dụng có thể chỉ nhận HTTP từ proxy. Nếu ứng dụng nhìn request nội bộ mà không biết thông tin public, nó có thể dựng URL sai như `http://order-app:8080/...`.

Các header thường dùng để chuyển thông tin public:

| Header | Ý nghĩa |
|---|---|
| `Forwarded` | Header chuẩn hóa theo RFC 7239, có thể chứa `proto`, `host` và `for` |
| `X-Forwarded-Host` | Host mà client sử dụng ở phía ngoài |
| `X-Forwarded-Proto` | Scheme bên ngoài, thường là `https` |
| `X-Forwarded-Port` | Port public |
| `X-Forwarded-For` | Chuỗi địa chỉ client/proxy qua các hop |
| `X-Forwarded-Prefix` | Prefix public mà proxy có thể đã gỡ khỏi request path |

Ví dụ request nội bộ có thể mang:

```http
Host: order-app:8080
X-Forwarded-Host: test.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /order-service
```

Ứng dụng có thể dùng các thông tin này để dựng URL bên ngoài chính xác, bao gồm link, redirect và server URL của tài liệu OpenAPI, nếu forwarded header support được bật và proxy gửi đúng giá trị.

## 6. Cấu hình `server.forward-headers-strategy`

Spring Boot cung cấp `server.forward-headers-strategy` để quyết định cách ứng dụng xử lý forwarded headers.

| Giá trị | Cách xử lý |
|---|---|
| `none` | Không áp dụng forwarded headers cho request |
| `native` | Dùng hỗ trợ forwarded header của web server/container nếu container có hỗ trợ |
| `framework` | Dùng cơ chế của Spring Framework để xử lý forwarded headers |

Ví dụ cấu hình khi chạy sau reverse proxy và cần Spring xử lý các header forwarded:

```yaml
server:
  forward-headers-strategy: framework
```

Với Spring MVC chạy trên Tomcat, Jetty hoặc Undertow, chiến lược `native` có thể phù hợp nếu container xử lý đúng các header mà topology của bạn cần. Khi cần xử lý `X-Forwarded-Prefix` nhất quán qua Spring Framework, kiểm tra lựa chọn `framework` và hành vi của phiên bản Spring Boot/Spring Framework đang dùng.

Không chọn chiến lược chỉ dựa vào tên môi trường. Hãy chọn theo container và cách proxy gửi header, rồi xác minh request URL mà ứng dụng nhìn thấy. Nếu ứng dụng chạy trực tiếp local không qua proxy, `none` thường dễ hiểu hơn.

## 7. Cấu hình riêng cho Spring MVC và WebFlux

### Spring MVC

Spring MVC có thể đặt context path trong cấu hình:

```yaml
server:
  port: 8080
  servlet:
    context-path: /order-app
```

Controller mapping `/api/orders` khi đó được phục vụ dưới context path `/order-app`.

### Spring WebFlux

Spring WebFlux có thể đặt base path:

```yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /order-app
```

Route/controller mapping `/api/orders` sẽ được gắn với base path của ứng dụng theo cấu hình WebFlux.

Không dùng `server.servlet.context-path` để cấu hình ứng dụng WebFlux thuần, và không dùng `spring.webflux.base-path` như cách thay thế context path của Spring MVC. Hãy xác nhận project đang chạy web stack nào, nhất là khi classpath có cả MVC và WebFlux starter.

## 8. Cấu hình theo profile local, test và production

Có thể tách các giá trị thay đổi theo môi trường bằng Spring Profiles.

`application-local.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: none

springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
```

`application-test.yml`:

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

`application-prod.yml`:

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

Trong ví dụ, ứng dụng không tự thêm context path; proxy chịu trách nhiệm public prefix. Local gọi trực tiếp ứng dụng, còn test và production nhận request qua proxy. Nếu production dùng prefix khác, hãy cấu hình gateway và forwarded headers tương ứng hoặc đặt base path ở ứng dụng theo một thiết kế thống nhất.

Kích hoạt profile qua biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=local
```

Trong pipeline test hoặc deployment, nền tảng có thể đặt `SPRING_PROFILES_ACTIVE=test` hoặc `prod`. Không đóng gói hostname production cố định vào source code nếu cùng artifact được triển khai qua nhiều môi trường.

## 9. Các endpoint springdoc cũng chịu ảnh hưởng của base path

Các URL mặc định thường gặp:

| Thành phần | Path mặc định |
|---|---|
| OpenAPI JSON | `/v3/api-docs` |
| OpenAPI YAML | `/v3/api-docs.yaml` |
| Swagger UI entry | `/swagger-ui.html` |
| Swagger UI assets | `/swagger-ui/**` |
| Swagger config | `/v3/api-docs/swagger-config` |
| OpenAPI group | `/v3/api-docs/{group}` |

Nếu Spring MVC có context path `/order-app`, các URL này được gọi dưới context path đó. Nếu proxy gỡ prefix `/order-service` và gửi `X-Forwarded-Prefix`, URL public có thể là `/order-service/v3/api-docs` hoặc `/order-service/swagger-ui.html`, tùy cách proxy và ứng dụng được cấu hình.

Có thể đổi path tài liệu:

```yaml
springdoc:
  api-docs:
    path: /openapi/spec
  swagger-ui:
    path: /docs
```

Sau khi đổi, cập nhật proxy route, security matcher, health/availability check và link được chia sẻ cho người dùng. Đừng chỉ đổi URL Swagger UI mà quên endpoint JSON/YAML mà UI cần tải.

## 10. Đối chiếu `servers` và `paths` trong OpenAPI

OpenAPI tách base URL trong `servers` khỏi path của từng operation. Ví dụ:

```yaml
servers:
  - url: https://test.example.com/order-service
paths:
  /api/orders:
    get:
      operationId: listOrders
```

Client kết hợp hai phần để gọi:

```text
https://test.example.com/order-service/api/orders
```

Nếu khai báo `servers.url` đã có `/order-service`, không lặp lại prefix đó trong path `/api/orders`. Nếu `servers.url` là `https://test.example.com/order-service` và path lại là `/order-service/api/orders`, URL cuối cùng bị lặp prefix.

Tương tự, không để `servers.url` chứa `/api` nếu mỗi path đã bắt đầu bằng `/api`, trừ khi API thực sự có hai lớp prefix như vậy.

## 11. Để springdoc nhận biết URL public qua proxy

Khi OpenAPI document được tạo từ request hiện tại, springdoc có thể sử dụng thông tin request để tạo server URL. Nếu ứng dụng chỉ nhìn thấy host nội bộ, scheme HTTP và port upstream, phần `servers` có thể phản ánh các giá trị đó.

Để tài liệu phản ánh URL public:

1. Reverse proxy phải đặt đúng `Host` hoặc `X-Forwarded-Host`.
2. Proxy phải đặt `X-Forwarded-Proto` thành scheme bên ngoài.
3. Nếu cần, proxy phải đặt `X-Forwarded-Port` và `X-Forwarded-Prefix`.
4. Spring Boot phải xử lý forwarded headers theo chiến lược phù hợp.
5. Không có proxy trung gian ghi đè hoặc làm mất các header cần thiết.
6. Kiểm tra `servers` trong JSON/YAML được sinh từ chính URL public.

Nếu hệ thống có một public base URL cố định, có thể khai báo server URL tường minh bằng `@OpenAPIDefinition(servers = ...)` hoặc một `OpenAPI` bean. Tuy nhiên, giá trị cố định phải phù hợp môi trường. Nếu cùng một artifact chạy ở local, test và production, dùng cấu hình theo môi trường hoặc forwarded request information thay vì hard-code một hostname.

Ví dụ cấu hình server URL qua property:

```java
import java.util.List;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI openAPI(@Value("${app.public-api-url}") String publicApiUrl) {
        return new OpenAPI()
                .info(new Info()
                        .title("Order API")
                        .version("1.0.0"))
                .servers(List.of(new Server().url(publicApiUrl)));
    }
}
```

`app.public-api-url` có thể được đặt trong từng profile. Khi dùng cách khai báo tường minh này, cần bảo đảm nó không xung đột với cách springdoc dựng server từ request hoặc các customizer khác.

## 12. Ví dụ giá trị server URL theo từng môi trường

`application-local.yml`:

```yaml
app:
  public-api-url: http://localhost:8080
```

`application-test.yml`:

```yaml
app:
  public-api-url: https://test.example.com/order-service
```

`application-prod.yml`:

```yaml
app:
  public-api-url: https://api.example.com
```

Với controller mapping `/api/orders`, OpenAPI document sẽ kết hợp server URL với path để tạo endpoint đầy đủ. Nếu production có prefix `/v1`, đặt prefix đó trong server URL hoặc trong path theo một quy ước duy nhất.

Không dùng URL test trong production. Không dùng hostname nội bộ như `order-app:8080` trong tài liệu dành cho client bên ngoài nếu client không thể phân giải hoặc truy cập hostname đó.

## 13. Cấu hình Swagger UI URL và group

Swagger UI cần tải OpenAPI config và spec. Nếu cấu hình URL tĩnh, hãy cân nhắc base path public:

```yaml
springdoc:
  swagger-ui:
    path: /docs
    url: /v3/api-docs
```

Đường dẫn bắt đầu bằng `/` là path từ root của origin. Khi ứng dụng được public dưới prefix `/order-service`, một URL root-relative `/v3/api-docs` có thể bỏ qua prefix và gọi nhầm endpoint ở root domain. Hãy xác minh URL mà browser thực sự request sau khi triển khai.

Với nhiều group, có thể khai báo danh sách URL:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: orders
        url: /v3/api-docs/orders
      - name: billing
        url: /v3/api-docs/billing
    urls-primary-name: orders
```

Nếu public prefix do proxy thêm/gỡ, các URL group cũng cần truy cập được từ browser qua prefix đó. Tránh hard-code `http://localhost:8080` hoặc hostname nội bộ trong `url`, `configUrl` hay danh sách group được gửi đến client.

## 14. Tránh prefix bị thiếu hoặc bị lặp

Hai lỗi thường gặp:

**Thiếu prefix:** client mở `https://test.example.com/order-service/swagger-ui.html`, nhưng Swagger UI tải spec từ `https://test.example.com/v3/api-docs`. Proxy chỉ định tuyến `/order-service/**`, nên request spec nhận `404`.

**Lặp prefix:** proxy đã gỡ `/order-service`, ứng dụng cũng đặt context path `/order-service`, hoặc `servers.url` và `paths` cùng chứa prefix. Kết quả có thể thành `/order-service/order-service/api/orders`.

Để tìm nguyên nhân, kiểm tra ba giá trị:

1. URL mà browser gọi.
2. Request path mà proxy gửi đến upstream.
3. Request URI/context path mà Spring nhận được.

Sau đó so sánh với `servers` và `paths` trong OpenAPI. Không sửa bằng cách thêm prefix ngẫu nhiên vào nhiều chỗ; xác định một nơi chịu trách nhiệm cho mỗi phần đường dẫn.

## 15. Kiểm tra endpoint từ local, test và production

Lập ma trận URL trước khi triển khai:

| Thành phần | Local | Test | Production |
|---|---|---|---|
| API | `http://localhost:8080/api/orders` | `https://test.example.com/order-service/api/orders` | `https://api.example.com/api/orders` |
| OpenAPI JSON | `http://localhost:8080/v3/api-docs` | `https://test.example.com/order-service/v3/api-docs` | `https://api.example.com/v3/api-docs` |
| Swagger UI | `http://localhost:8080/swagger-ui.html` | `https://test.example.com/order-service/swagger-ui.html` | `https://api.example.com/swagger-ui.html` |
| Public server URL | `http://localhost:8080` | `https://test.example.com/order-service` | `https://api.example.com` |

Các URL trên giả định test proxy gỡ prefix và production không có prefix. Nếu topology khác, điều chỉnh ma trận theo cấu hình thật.

Kiểm tra API:

```bash
curl -i https://test.example.com/order-service/api/orders
```

Kiểm tra OpenAPI:

```bash
curl -fS \
  https://test.example.com/order-service/v3/api-docs \
  -o openapi-test.json
```

Kiểm tra `servers` và path:

```bash
jq '.servers' openapi-test.json
jq '.paths | keys' openapi-test.json
```

Không chỉ xác nhận HTTP status 200. Cần kiểm tra server URL và path kết hợp thành URL có thể truy cập từ mạng client.

## 16. Dùng browser Network để kiểm tra Swagger UI

Khi Swagger UI mở được nhưng không hiển thị API, mở Developer Tools của browser và xem tab Network:

- Request đến `/swagger-ui/swagger-ui.css` và JavaScript assets có tải thành công không?
- Request đến `/v3/api-docs/swagger-config` có đúng public prefix không?
- Request đến `/v3/api-docs` hoặc URL group có bị thiếu prefix không?
- Response là `200`, `301/302`, `401/403` hay `404`?
- Header `Location` của redirect có đổi sang hostname nội bộ hoặc HTTP không?
- Console có báo mixed content khi trang HTTPS gọi spec HTTP không?

Nếu assets trả `404`, kiểm tra proxy rewrite cho `/swagger-ui/**`. Nếu config trả `401/403`, kiểm tra security rule cho tài liệu. Nếu spec trả `404`, kiểm tra path và prefix. Nếu redirect tạo URL sai scheme/host, kiểm tra forwarded headers và trusted proxy.

## 17. Tin cậy forwarded headers và tránh giả mạo

Forwarded headers có thể ảnh hưởng URL redirect, link và server URL trong OpenAPI. Nếu ứng dụng chấp nhận forwarded headers từ mọi nguồn, client bên ngoài có thể tự gửi header giả như `X-Forwarded-Host` hoặc `X-Forwarded-Proto` để tác động URL được tạo.

Thiết kế an toàn cần:

- Chỉ tin forwarded headers từ proxy/load balancer nằm trong mạng hoặc danh sách tin cậy.
- Cấu hình proxy xóa header forwarded do client tự gửi trước khi thêm giá trị do proxy xác định.
- Không để ứng dụng được truy cập trực tiếp từ Internet nếu giả định rằng mọi request đều qua proxy tin cậy.
- Giới hạn chuỗi proxy và cách diễn giải `X-Forwarded-For` theo topology.
- Kiểm tra `Host` hợp lệ và tránh tạo link dựa trên hostname tùy ý do client cung cấp.
- Kiểm thử cả request qua proxy và request truy cập trực tiếp upstream trong môi trường được kiểm soát.

Không bật xử lý forwarded headers chỉ để sửa một URL Swagger UI nếu chưa xác định nguồn header đáng tin cậy. Đây là cấu hình ảnh hưởng toàn bộ request, không chỉ riêng springdoc.

## 18. Security matcher và CORS khi có prefix

Nếu bảo vệ `/v3/api-docs` hoặc `/swagger-ui/**` bằng Spring Security, hãy xác định path mà Spring Security nhìn thấy sau khi proxy rewrite và sau khi áp dụng context path. Matcher phải phù hợp với path trong ứng dụng, không mặc định là URL public đầy đủ.

Ví dụ, proxy gỡ `/order-service` rồi chuyển `/v3/api-docs` đến app. Security matcher thường cần khớp `/v3/api-docs/**`, không phải `/order-service/v3/api-docs/**`. Nếu proxy giữ nguyên prefix và ứng dụng có context path tương ứng, quy tắc sẽ khác.

Nếu browser gọi API từ một origin khác, CORS cần cho phép origin, method và header tương ứng. CORS không sửa path rewrite, không thêm prefix vào OpenAPI và không thay thế authorization. Cấu hình CORS đúng vẫn có thể đi cùng lỗi `404` nếu URL spec sai.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Local chạy nhưng test trả `404` | Proxy gỡ hoặc giữ prefix khác dự kiến | Kiểm tra request path trước/sau rewrite và mapping upstream |
| Swagger UI tải trang nhưng không có API | Config URL/spec URL thiếu public prefix | Kiểm tra Network và URL `/v3/api-docs/swagger-config` |
| OpenAPI `servers` trỏ đến `http://service:8080` | Ứng dụng không nhận hoặc không xử lý forwarded host/proto | Cấu hình proxy headers và `server.forward-headers-strategy` |
| OpenAPI URL bị lặp prefix | Prefix xuất hiện ở proxy, context/base path và `servers`/`paths` cùng lúc | Chọn một nơi chịu trách nhiệm cho mỗi prefix |
| Redirect từ HTTPS sang HTTP | Scheme bên ngoài không được chuyển tiếp hoặc không được xử lý | Đặt `X-Forwarded-Proto: https` và cấu hình forwarded headers |
| Test hoạt động nhưng production sai | Hostname, path prefix hoặc ingress rule khác nhau | Duy trì ma trận URL và kiểm thử artifact ở từng môi trường |
| `/v3/api-docs.yaml` trả 404 | Proxy chỉ route JSON endpoint hoặc rewrite thiếu suffix `.yaml` | Bổ sung route cho YAML và kiểm tra URL thực tế |
| Group docs trả 404 | Chưa route `/v3/api-docs/{group}` qua proxy | Bổ sung pattern group và xác minh group name |
| Swagger UI assets trả 404 | Proxy không chuyển `/swagger-ui/**` | Bổ sung route static assets và kiểm tra trailing slash |
| Redirect tạo hostname lạ | Tin forwarded host không đáng tin hoặc proxy không ghi đè header | Chỉ tin proxy đã xác thực và ghi đè header đầu vào |
| Security matcher không khớp | Dùng public path trong khi app chỉ nhận upstream path | Viết matcher theo path Spring thực sự nhận |
| Browser báo mixed content | HTTPS UI gọi OpenAPI URL HTTP | Sửa server URL/config URL và forwarded scheme |

## 20. Quy trình đối chiếu trước khi phát hành

1. Ghi lại public base URL của local, test và production.
2. Ghi rõ proxy giữ prefix hay gỡ prefix; xác định request path upstream.
3. Xác định app dùng Spring MVC context path, WebFlux base path hay không có base path.
4. Kiểm tra controller mapping và endpoint tài liệu springdoc.
5. Cấu hình proxy gửi `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, port và prefix phù hợp.
6. Cấu hình `server.forward-headers-strategy` theo container và mức tin cậy của proxy.
7. Kiểm tra `servers` và `paths` trong OpenAPI JSON/YAML.
8. Kiểm tra Swagger UI config, spec URL, group URL và static assets.
9. Kiểm tra security matcher và CORS theo path/origin thực tế.
10. Chạy curl và browser Network từ góc nhìn client ở từng môi trường.
11. Kiểm tra redirect, scheme, host, port, prefix và trailing slash.
12. Lưu ma trận URL làm tiêu chí kiểm tra sau mỗi lần đổi gateway, ingress hoặc base path.

## 21. Nguyên tắc thiết kế

- Tách rõ public URL, upstream URL, context/base path, servlet path và controller mapping.
- Chọn một nơi chịu trách nhiệm cho từng prefix; tránh thêm cùng prefix ở proxy và ứng dụng mà không có chủ đích.
- Khi proxy gỡ prefix, chuyển thông tin public bằng forwarded headers nếu ứng dụng cần dựng URL bên ngoài.
- Cấu hình `server.forward-headers-strategy` theo loại container và proxy thực tế.
- Chỉ tin forwarded headers từ proxy được kiểm soát; xóa giá trị do client gửi trước khi proxy đặt giá trị tin cậy.
- Giữ `servers.url` và `paths` không lặp prefix.
- Kiểm tra cả JSON, YAML, Swagger UI, group endpoint và static assets.
- Không hard-code localhost hoặc hostname nội bộ vào tài liệu dành cho client bên ngoài.
- Dùng profile hoặc cấu hình ngoài artifact để cung cấp URL theo môi trường.
- Kiểm thử URL từ phía client, không chỉ gọi trực tiếp upstream.

## Kết luận

Đường dẫn API trên local, test và production có thể khác nhau do host, scheme, port, proxy prefix, context path, WebFlux base path và controller mapping. Muốn springdoc-openapi sinh tài liệu đúng, cần xác định proxy giữ hay gỡ prefix, cấu hình forwarded headers phù hợp, rồi đối chiếu `servers` với `paths`. Swagger UI, OpenAPI JSON/YAML, group endpoint và static assets đều phải đi qua proxy đúng đường dẫn. Hãy duy trì ma trận URL cho từng môi trường, kiểm tra request từ góc nhìn client và chỉ tin forwarded headers do proxy được kiểm soát tạo ra.
