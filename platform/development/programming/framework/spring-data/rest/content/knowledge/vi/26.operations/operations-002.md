# Triển khai Spring Data REST sau reverse proxy với context path và base path

## Mục tiêu

Khi Spring Data REST chạy sau Nginx, Apache HTTP Server, load balancer hoặc ingress controller, ứng dụng thường nhìn thấy request đến từ một địa chỉ nội bộ như `http://127.0.0.1:8080`. Client bên ngoài lại truy cập bằng HTTPS, hostname công khai và có thể có một URL prefix như `https://api.example.com/api`.

Nếu proxy chuyển tiếp request nhưng Spring không nhận được thông tin về địa chỉ ban đầu, các URL được sinh trong response có thể sai: HAL `href` trỏ về host nội bộ, dùng `http` thay vì `https`, thiếu path prefix hoặc lặp context path. Các lỗi này ảnh hưởng đến liên kết `self`, collection, item, association, profile, phân trang và header `Location`.

Bài này trình bày cách phân biệt ba loại path, cấu hình proxy gửi forwarded headers, bật xử lý forwarded headers trong Spring Boot và kiểm tra các liên kết được Spring Data REST sinh ra.

## 1. Phân biệt context path, Spring Data REST base path và proxy prefix

Ba cấu hình có mục đích khác nhau:

| Thành phần | Cấu hình | Phạm vi |
|---|---|---|
| Servlet context path | `server.servlet.context-path` | Prefix của toàn bộ ứng dụng Servlet |
| Spring Data REST base path | `spring.data.rest.base-path` | Prefix riêng của repository resources được Spring Data REST export |
| Public proxy prefix | Header `X-Forwarded-Prefix` hoặc cấu hình tương đương | Prefix client dùng để truy cập qua proxy |

Ví dụ:

- Servlet context path nội bộ: `/app`.
- Spring Data REST base path: `/rest`.
- Proxy công khai API dưới prefix: `/api`.

Khi các prefix được ghép theo thiết kế này, collection resource có thể được truy cập công khai tại `https://api.example.com/api/rest/categories`, trong khi proxy chuyển tiếp request đến path nội bộ `/app/rest/categories`.

Không nên đặt cùng một prefix ở nhiều lớp mà không xác định lớp nào sở hữu prefix đó. Nếu cả proxy, servlet context và Spring Data REST đều thêm `/api`, URL có thể thành `/api/api/api`. Ngược lại, nếu proxy bỏ prefix nhưng ứng dụng không nhận `X-Forwarded-Prefix`, các link sinh ra có thể thiếu phần path công khai.

### 1.1. Servlet context path

Trong Spring Boot Servlet application, cấu hình:

```properties
server.servlet.context-path=/app
```

Context path áp dụng cho toàn bộ ứng dụng được triển khai trên servlet container. Nó ảnh hưởng cả Spring MVC controllers, Spring Data REST và các servlet endpoints khác.

### 1.2. Spring Data REST base path

Có thể đặt riêng root URI của repository resources:

```properties
spring.data.rest.base-path=/rest
```

Khi đó, nếu ứng dụng không có servlet context path, một repository có collection path `/categories` sẽ được export dưới `/rest/categories`. Cấu hình này không tự đổi context path của các controller khác.

Với Spring Boot, `spring.data.rest.base-path` là property tương ứng với cấu hình base path của Spring Data REST. Ở các ví dụ API cũ, tài liệu có thể ghi dạng camel case `basePath` trong `application.properties`; relaxed binding của Spring Boot cho phép dùng dạng kebab case hiện hành.

### 1.3. Public prefix của reverse proxy

Giả sử proxy nhận request ở `/api/...` nhưng chuyển request đến ứng dụng với prefix nội bộ `/app/...`. Proxy có thể gửi:

```http
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /api
```

`X-Forwarded-Prefix` mô tả prefix công khai mà client nhìn thấy. Spring Framework hỗ trợ các header `Forwarded` theo RFC 7239 và các header `X-Forwarded-*` thông dụng. Cách proxy thêm, thay thế hoặc loại bỏ prefix phải khớp với cách proxy rewrite request path.

## 2. Luồng request khi có reverse proxy

Ví dụ triển khai:

```text
Client
  https://api.example.com/api/rest/categories
       |
       v
Reverse proxy (Nginx)
  public prefix: /api
  forwards to:   http://127.0.0.1:8080/app/rest/categories
  adds forwarded host/proto/port/prefix headers
       |
       v
Spring Boot application
  servlet context path: /app
  Spring Data REST base path: /rest
  repository collection: /categories
       |
       v
HAL response with public links
  https://api.example.com/api/rest/categories/...
```

Spring Data REST mặc định dùng HAL để biểu diễn tài nguyên và phát hiện liên kết. Root resource chứa các relation như collection và profile; item resource có thể chứa link đến association. Vì thế, Spring cần biết host, scheme, port và prefix công khai để tạo các URL có thể dùng trực tiếp từ client.

## 3. Cấu hình Spring Boot xử lý forwarded headers

Spring Boot cung cấp property:

```properties
server.forward-headers-strategy=FRAMEWORK
```

Với Servlet stack, giá trị `FRAMEWORK` sử dụng `ForwardedHeaderFilter` của Spring Framework. Filter bọc request để ứng dụng nhìn thấy thông tin gốc được proxy chuyển tiếp. Nó phải chạy trước các filter cần đọc request đã được điều chỉnh.

Hai strategy chính cần phân biệt:

- `NATIVE`: giao việc xử lý forwarded headers cho web server/container. Chọn khi container hỗ trợ đầy đủ các header cần dùng trong deployment.
- `FRAMEWORK`: dùng cơ chế của Spring Framework. Với Spring MVC Servlet application, cơ chế này là `ForwardedHeaderFilter`.

Không nên mặc định rằng mọi container hỗ trợ cùng tập header. Đặc biệt, cần kiểm tra hỗ trợ cho `X-Forwarded-Prefix` khi public path và internal context path khác nhau.

Ví dụ cấu hình YAML cho ứng dụng dùng context path và Spring Data REST base path:

```yaml
server:
  servlet:
    context-path: /app
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false

spring:
  data:
    rest:
      base-path: /rest
```

Trong ví dụ này:

- `context-path` là `/app`.
- repository resources bắt đầu dưới `/rest`.
- `forward-headers-strategy` bật xử lý thông tin do proxy gửi.
- `server.tomcat.redirect-context-root=false` là thiết lập cần xem xét khi dùng Tomcat và proxy kết thúc TLS, để `X-Forwarded-Proto` được tôn trọng trước redirect ở context root.

Không sao chép nguyên cấu hình này vào mọi hệ thống. Nếu proxy giữ nguyên path và container đã xử lý đúng các header cần thiết, strategy `NATIVE` có thể phù hợp. Nếu ứng dụng dùng Jetty hoặc Tomcat, hãy xem phần hỗ trợ header riêng của container và phiên bản Spring Boot.

## 4. Cấu hình Nginx làm reverse proxy

Ví dụ sau giả định:

- Client gọi `https://api.example.com/api/rest/categories`.
- Nginx nhận request dưới `/api/`.
- Spring Boot chạy tại `127.0.0.1:8080` với context path `/app`.
- Nginx thay prefix `/api` bằng `/app` khi chuyển request đến upstream.

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8080/app/;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /api;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

Dấu slash cuối trong `location /api/` và URI của `proxy_pass` có ý nghĩa khi Nginx thay phần URI khớp với location bằng URI được khai báo trong `proxy_pass`. Kiểm tra quy tắc rewrite thực tế trước khi áp dụng vào cấu hình đang chạy.

Nếu proxy không thay `/api` bằng `/app`, hãy điều chỉnh `proxy_pass` và forwarded prefix tương ứng. Không gửi một prefix mô tả URL công khai nhưng lại không khớp với đường dẫn mà proxy thực sự phục vụ.

Các header ví dụ có ý nghĩa:

- `Host` và `X-Forwarded-Host`: hostname client sử dụng.
- `X-Forwarded-Proto`: scheme công khai, thường là `https` khi TLS kết thúc tại proxy.
- `X-Forwarded-Port`: port công khai.
- `X-Forwarded-Prefix`: path prefix công khai.
- `X-Forwarded-For`: địa chỉ client theo chuỗi proxy đã tin cậy.

Nếu có nhiều proxy nối tiếp, hãy thiết kế rõ proxy nào được phép thêm và giữ từng phần của forwarded chain. Cấu hình ở proxy biên phải ghi đè hoặc loại bỏ forwarded headers do client bên ngoài tự gửi, sau đó tạo lại giá trị tin cậy. Ví dụ dùng `$remote_addr` ở trên phù hợp cho một proxy biên đơn giản; với nhiều hop, điều chỉnh theo topology và danh sách proxy tin cậy.

## 5. Khi nào cần X-Forwarded-Prefix?

Spring Framework mô tả ba tình huống phổ biến:

| Tình huống | Public URL | Internal URL | X-Forwarded-Prefix |
|---|---|---|---|
| Thay prefix | `/api/{path}` | `/app1/{path}` | `/api` |
| Loại bỏ prefix nội bộ | `{path}` | `/app1/{path}` | prefix rỗng |
| Thêm prefix công khai | `/api/app1/{path}` | `/app1/{path}` | `/api/app1` |

Ví dụ thay prefix:

```text
https://example.com/api/categories
             |
             | proxy maps /api to /app1
             v
http://localhost:8080/app1/categories
```

Proxy gửi `X-Forwarded-Prefix: /api` để request được nhận diện dưới prefix công khai `/api`. Trường hợp loại bỏ prefix nội bộ có thể gửi giá trị rỗng để ghi đè `/app1`. Trường hợp thêm prefix công khai có thể gửi `/api/app1`.

Không thêm `X-Forwarded-Prefix` một cách máy móc. Trước tiên xác định proxy đang giữ, thay hay xóa prefix nào. Nếu cấu hình prefix sai, request có thể vẫn đến được controller nhưng link HAL lại dẫn đến URL không thể truy cập.

## 6. Kiểm tra HAL links sau triển khai

Sau khi ứng dụng khởi động và proxy đã reload, gọi public URL:

```bash
curl -i   -H "Accept: application/hal+json"   https://api.example.com/api/rest
```

Kiểm tra response có `200 OK` và `Content-Type: application/hal+json`. Trong JSON, các link phải dùng hostname công khai, scheme công khai và path prefix đúng.

Ví dụ root representation mong muốn:

```json
{
  "_links": {
    "categories": {
      "href": "https://api.example.com/api/rest/categories"
    },
    "profile": {
      "href": "https://api.example.com/api/rest/profile"
    }
  }
}
```

Tên relation và link thực tế phụ thuộc repository đã export. Ví dụ chỉ minh họa cách kiểm tra URL được sinh.

Kiểm tra thêm collection resource:

```bash
curl -i   -H "Accept: application/hal+json"   "https://api.example.com/api/rest/categories?page=0&size=5"
```

Đọc các relation `self`, `next`, `prev` và `profile` nếu có. Mỗi `href` phải có thể truy cập qua public proxy. Không chỉ kiểm tra URL request ban đầu: một GET thành công vẫn có thể trả HAL document với link trỏ về địa chỉ nội bộ.

Với thao tác tạo mới, kiểm tra cả header `Location`:

```bash
curl -i -X POST https://api.example.com/api/rest/categories   -H "Content-Type: application/json"   -H "Accept: application/hal+json"   --data '{"code":"BOOKS","name":"Books"}'
```

Nếu response trả `201 Created`, `Location` nên là URI công khai có thể dùng để GET resource vừa tạo. Status/body cụ thể còn phụ thuộc cấu hình Spring Data REST và repository.

## 7. Kiểm thử và chẩn đoán

Nên kiểm tra qua hai đường:

1. **Backend trực tiếp:** xác nhận ứng dụng phản hồi ở địa chỉ và path nội bộ dự kiến.
2. **Public proxy URL:** xác nhận routing, forwarded headers, HTTPS và HAL links đều đúng khi client đi qua proxy.

Các dấu hiệu thường gặp:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Request public URL trả 404 | Nginx `location`, `proxy_pass`, context path hoặc Spring Data REST base path không khớp |
| Response 200 nhưng link có `localhost:8080` | Chưa xử lý forwarded host/port hoặc proxy không gửi header |
| HAL link dùng `http` trong khi client dùng HTTPS | `X-Forwarded-Proto` thiếu/sai hoặc strategy chưa xử lý |
| Link bị thiếu `/api` | `X-Forwarded-Prefix` thiếu hoặc không được xử lý |
| Link lặp `/api` hay `/app` | Prefix được thêm ở nhiều lớp hoặc proxy rewrite không đúng |
| Redirect từ HTTPS về HTTP | Kiểm tra forwarded proto và cấu hình redirect của container |
| Link collection đúng nhưng link association sai | Kiểm tra association path, forwarded request context và custom resource mapping |

Một số kiểm tra cụ thể:

- Kiểm tra log proxy để biết path ban đầu và path được gửi đến upstream.
- Kiểm tra `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port` và `X-Forwarded-Prefix` tại upstream.
- Xác minh Spring Boot đang dùng đúng `server.forward-headers-strategy`.
- Nếu dùng Tomcat, xác minh proxy thuộc tập internal proxies được tin cậy; không đặt danh sách internal proxies rỗng trong production.
- Kiểm tra cả URL trong HAL và `Location` của POST/PUT.
- Kiểm tra link phân trang khi có query parameters và khi theo link `next` sang trang tiếp theo.
- Xác nhận các endpoint controller ngoài Spring Data REST vẫn được truy cập dưới path mong đợi.

### 7.1. Kiểm thử với forwarded headers

Có thể viết integration test dùng Spring Boot và MockMvc để gửi các forwarded headers, sau đó xác minh link được sinh. Test cần chạy với cấu hình forwarded header filter tương ứng:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ForwardedLinksIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void rendersLinksUsingPublicRequestInformation() throws Exception {
        mockMvc.perform(get("/app/rest/categories")
                .header("X-Forwarded-Host", "api.example.com")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/api")
                .accept(MediaType.parseMediaType("application/hal+json")))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/hal+json")));
    }
}
```

Ví dụ trên minh họa request context và response media type; để xác nhận chính xác URL, hãy parse JSON response và assert các giá trị `_links.*.href` theo topology thực tế. MockMvc không thay thế kiểm thử Nginx hoặc load balancer: nó không xác nhận rewrite rule, TLS termination hay việc proxy đã ghi đè header không tin cậy.

## 8. Bảo mật forwarded headers

Forwarded headers chỉ đáng tin khi được thêm bởi proxy thuộc phạm vi quản lý. Client có thể tự gửi `Forwarded` hoặc `X-Forwarded-*`; nếu ứng dụng tin trực tiếp các giá trị này, client có thể làm thay đổi hostname, scheme, port hoặc prefix mà ứng dụng dùng để tạo URL.

Thực hiện các nguyên tắc sau:

1. Chỉ cho phép truy cập backend từ proxy/load balancer được tin cậy khi kiến trúc yêu cầu đi qua proxy.
2. Ở proxy biên, xóa hoặc ghi đè forwarded headers do client gửi từ Internet trước khi tạo header nội bộ.
3. Chọn `NATIVE` hoặc `FRAMEWORK` theo container và tập header cần hỗ trợ.
4. Với Tomcat, cấu hình đúng danh sách proxy nội bộ. Không tin tất cả proxy trong production.
5. Nếu cần loại bỏ forwarded headers nhưng không dùng chúng, Spring `ForwardedHeaderFilter` có chế độ `removeOnly`.
6. Không cho phép một client truy cập trực tiếp backend và tự khai báo host/proto/prefix nếu backend đang tin forwarded headers từ proxy.

Spring Framework nhấn mạnh proxy ở ranh giới tin cậy phải loại bỏ các forwarded headers không đáng tin. Đây là điều kiện quan trọng để tránh tạo absolute links hoặc redirect dựa trên host do client giả mạo.

## 9. Checklist trước khi đưa vào production

- [ ] Đã xác định rõ public URL và upstream URL.
- [ ] Đã phân biệt servlet context path, Spring Data REST base path và proxy prefix.
- [ ] Proxy rewrite request path đúng một lần.
- [ ] Proxy gửi đúng host, proto, port và prefix công khai.
- [ ] Proxy biên ghi đè hoặc loại bỏ forwarded headers từ client.
- [ ] Spring Boot bật strategy phù hợp với web server và forwarded headers cần dùng.
- [ ] Với Tomcat kết thúc TLS ở proxy, đã xem xét `server.tomcat.redirect-context-root=false`.
- [ ] Root HAL links trỏ đến public hostname và HTTPS.
- [ ] Collection, item, association, profile và pagination links đều truy cập được.
- [ ] Header `Location` sau khi tạo resource là URL công khai.
- [ ] Đã thử request qua proxy thật, không chỉ dùng MockMvc.
- [ ] Đã kiểm tra backend không bị truy cập trực tiếp ngoài dự kiến.

## Tài liệu chính thức

1. [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server): forwarded headers, `server.forward-headers-strategy`, `NATIVE`, `FRAMEWORK` và cấu hình Tomcat.
2. [Spring Framework — Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers): ý nghĩa của `Forwarded`, các header `X-Forwarded-*`, các trường hợp `X-Forwarded-Prefix` và lưu ý bảo mật.
3. [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): tra cứu `server.servlet.context-path`, `server.forward-headers-strategy` và `spring.data.rest.base-path` theo phiên bản.
4. [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): thay đổi base URI bằng `spring.data.rest.basePath` hoặc `RepositoryRestConfigurer`.
5. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): root resource, collection/item resources, association links và HTTP methods.
6. [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): URI templates và liên kết phân trang `self`, `next`, `prev`.
7. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): chuẩn hóa header `Forwarded`.

*Các URL và property cần được đối chiếu với phiên bản Spring Boot, Spring Framework và Spring Data REST đang được ứng dụng sử dụng. Ví dụ proxy trong bài là cấu hình minh họa; phải điều chỉnh upstream path và header theo topology thực tế.*