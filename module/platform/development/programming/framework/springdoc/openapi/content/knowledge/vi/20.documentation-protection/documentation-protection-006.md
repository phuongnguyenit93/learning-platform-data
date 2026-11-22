# Tắt riêng Swagger UI hoặc endpoint OpenAPI theo môi trường

Springdoc có thể công bố tài liệu API dưới dạng JSON/YAML và đồng thời cung cấp Swagger UI để xem, tìm kiếm hoặc thử gọi operation. Hai phần này là hai khả năng độc lập: tắt giao diện Swagger UI không tự động tắt endpoint OpenAPI, và tắt endpoint OpenAPI không đồng nghĩa với việc đã bảo vệ API nghiệp vụ.

Spring Boot cho phép bật/tắt từng phần bằng cấu hình `springdoc.swagger-ui.enabled` và `springdoc.api-docs.enabled`. Có thể đặt giá trị khác nhau theo profile như `dev`, `test`, `staging` và `prod`, hoặc truyền qua biến môi trường khi triển khai. Nhờ vậy, môi trường phát triển có thể bật đầy đủ tài liệu trong khi production chỉ công bố những gì chính sách vận hành cho phép.

## 1. Phân biệt Swagger UI và endpoint OpenAPI

Springdoc thường cung cấp hai nhóm endpoint:

| Thành phần | Đường dẫn mặc định | Chức năng |
|---|---|---|
| OpenAPI JSON | `/v3/api-docs` | Trả về OpenAPI document dạng JSON |
| OpenAPI YAML | `/v3/api-docs.yaml` | Trả về OpenAPI document dạng YAML |
| OpenAPI theo group | `/v3/api-docs/{group}` | Trả về document của một `GroupedOpenApi` |
| Swagger UI entry | `/swagger-ui.html` | Đường dẫn mở giao diện, thường chuyển hướng đến UI resource |
| Swagger UI resources | `/swagger-ui/**` | HTML, JavaScript, CSS và tài nguyên giao diện |

Swagger UI là ứng dụng web đọc OpenAPI document rồi hiển thị các operation. Endpoint `/v3/api-docs` cung cấp dữ liệu hợp đồng cho Swagger UI và cho các công cụ khác như client generator, contract test hoặc pipeline tích hợp.

Do đó, tắt một thành phần không mặc nhiên tắt thành phần còn lại:

- Tắt Swagger UI nhưng giữ API Docs: người dùng không mở giao diện tại ứng dụng, nhưng công cụ vẫn có thể tải JSON/YAML.
- Giữ Swagger UI nhưng tắt API Docs: giao diện có thể vẫn được phục vụ, nhưng không tải được document mặc định nếu không cấu hình một nguồn OpenAPI khác.
- Tắt cả hai: ứng dụng không công bố giao diện hoặc endpoint tài liệu Springdoc theo các đường dẫn đó.

Các thuộc tính Springdoc thường dùng:

```yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
```

Mặc định hai tính năng thường được bật khi starter Springdoc được thêm vào ứng dụng. Hãy cấu hình tường minh để hành vi giữa các môi trường dễ kiểm soát.

## 2. Tắt riêng Swagger UI, vẫn giữ OpenAPI JSON/YAML

Trường hợp này phù hợp khi production không cần giao diện tương tác nhưng pipeline hoặc hệ thống tích hợp vẫn cần tải OpenAPI document.

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
```

Kết quả mong đợi:

- `/swagger-ui.html` và giao diện Swagger UI không còn được cung cấp theo cấu hình Springdoc.
- `/v3/api-docs` vẫn trả về OpenAPI JSON.
- `/v3/api-docs.yaml` vẫn trả về OpenAPI YAML.
- Các URL `/v3/api-docs/{group}` vẫn có thể truy cập nếu ứng dụng khai báo group và API Docs được bật.

Ví dụ, một pipeline có thể lấy document để sinh client:

```bash
curl -fsS https://api.example.com/v3/api-docs -o openapi.json
```

Tắt UI không phải là biện pháp bảo vệ nội dung tài liệu. Nếu OpenAPI document có thông tin nội bộ, cần giới hạn quyền truy cập endpoint API Docs bằng Spring Security, gateway hoặc chỉ công bố document qua một kênh riêng.

## 3. Tắt endpoint OpenAPI, giữ Swagger UI

Trường hợp này ít phổ biến hơn. Nó có thể phù hợp khi Swagger UI được cấu hình để tải một OpenAPI file tĩnh hoặc một document từ server khác.

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: true
    url: /contracts/orders-openapi.yaml
```

Ở ví dụ này, Swagger UI vẫn được phục vụ nhưng nguồn document được chuyển sang file `/contracts/orders-openapi.yaml`. File đó phải thực sự tồn tại và được web server hoặc ứng dụng phục vụ tại URL tương ứng. Nếu không cấu hình `url` hoặc `urls` trỏ đến một nguồn OpenAPI khác, UI có thể mở được nhưng hiển thị lỗi tải specification vì endpoint Springdoc mặc định đã bị tắt.

Nếu có nhiều tài liệu tĩnh, có thể cấu hình danh sách:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: true
    urls:
      - name: Orders API
        url: /contracts/orders-openapi.yaml
      - name: Customers API
        url: /contracts/customers-openapi.yaml
    urls-primary-name: Orders API
```

Swagger UI chỉ là giao diện hiển thị. Việc tắt API Docs do Springdoc sinh ra không ngăn Swagger UI tải một tài liệu tĩnh hoặc một URL OpenAPI bên ngoài.

## 4. Tắt cả Swagger UI và API Docs

Nếu production không cần công bố tài liệu từ ứng dụng, có thể tắt cả hai:

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
```

Sau khi ứng dụng khởi động với cấu hình này:

- Swagger UI không được cung cấp.
- Các endpoint OpenAPI do Springdoc tạo không được đăng ký/phục vụ như bình thường.
- API nghiệp vụ vẫn hoạt động theo controller và cấu hình runtime.
- Annotation như `@Operation`, `@Schema` hoặc `@ApiResponse` vẫn nằm trong mã nguồn; chỉ việc công bố tài liệu HTTP bị tắt.

Khi endpoint tài liệu không còn được phục vụ, request thường nhận 404, nhưng status thực tế có thể khác nếu Spring Security, reverse proxy, gateway hoặc error handler chặn request trước. Hãy xác minh trên môi trường triển khai thay vì dựa vào một status duy nhất.

## 5. Cấu hình theo Spring Profile

Spring Profiles là cách rõ ràng để mỗi môi trường có một chính sách tài liệu riêng. Ví dụ, bật tài liệu trong local và staging, tắt trong production.

### Cấu hình mặc định trong `application.yml`

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

### Cấu hình production trong `application-prod.yml`

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Khi chạy production, kích hoạt profile `prod`:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Hoặc đặt biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Khi profile `prod` được kích hoạt, các giá trị trong `application-prod.yml` ghi đè cấu hình mặc định tương ứng. Trong local, không kích hoạt profile production thì hai tính năng vẫn được bật theo `application.yml`.

### Dùng một profile trung gian cho staging

Staging thường cần tài liệu để QA hoặc đối tác kiểm thử, nhưng nên giới hạn người truy cập:

```yaml
# application-staging.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

Sau đó bảo vệ Swagger UI và API Docs bằng cơ chế xác thực phù hợp. Không nên xem staging là môi trường an toàn mặc định; nó có thể chứa dữ liệu gần production hoặc kết nối đến dịch vụ thật.

## 6. Cấu hình theo profile trong một file YAML

Nếu muốn giữ cấu hình trong một file, có thể dùng nhiều YAML document và `spring.config.activate.on-profile`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
---
spring:
  config:
    activate:
      on-profile: prod
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Document đầu tiên áp dụng mặc định. Document thứ hai chỉ áp dụng khi profile `prod` hoạt động. Cách tách `application-prod.yml` thường dễ quản lý hơn khi cấu hình môi trường dài hoặc do đội triển khai sở hữu.

Không đặt `spring.profiles.active` trong một file cấu hình chỉ được kích hoạt theo profile khác. Hãy chọn profile từ command line, biến môi trường hoặc cấu hình triển khai.

## 7. Điều khiển bằng biến môi trường

Trong container hoặc nền tảng triển khai, có thể truyền trực tiếp các property Springdoc qua environment variable:

| Spring property | Environment variable | Ý nghĩa |
|---|---|---|
| `springdoc.swagger-ui.enabled` | `SPRINGDOC_SWAGGER_UI_ENABLED` | Bật/tắt Swagger UI |
| `springdoc.api-docs.enabled` | `SPRINGDOC_API_DOCS_ENABLED` | Bật/tắt endpoint OpenAPI |
| `springdoc.swagger-ui.path` | `SPRINGDOC_SWAGGER_UI_PATH` | Đổi đường dẫn UI entry |
| `springdoc.api-docs.path` | `SPRINGDOC_API_DOCS_PATH` | Đổi đường dẫn API Docs |

Ví dụ chạy production:

```bash
SPRINGDOC_SWAGGER_UI_ENABLED=false \
SPRINGDOC_API_DOCS_ENABLED=false \
java -jar app.jar
```

Trên Windows PowerShell:

```powershell
$env:SPRINGDOC_SWAGGER_UI_ENABLED = "false"
$env:SPRINGDOC_API_DOCS_ENABLED = "false"
java -jar app.jar
```

Environment variable là override cấu hình ứng dụng theo thứ tự ưu tiên property source của Spring Boot. Nếu YAML nói `enabled: false` nhưng môi trường triển khai đặt biến thành `true`, giá trị có hiệu lực có thể là `true`. Khi chẩn đoán, kiểm tra profile đang hoạt động và nguồn cấu hình thực tế.

## 8. Thay đổi URL tài liệu không đồng nghĩa tắt tài liệu

Có thể đổi đường dẫn mặc định:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /api-reference
```

Khi đó endpoint JSON được phục vụ tại path API Docs đã cấu hình và Swagger UI có entry path mới. Việc đổi path chỉ thay URL; nó không tắt endpoint hoặc giới hạn người truy cập. Người dùng vẫn có thể tải document nếu biết URL và được phép qua các lớp mạng/bảo mật.

Với group, endpoint vẫn được đặt dưới API Docs path tùy chỉnh theo quy tắc Springdoc, kèm tên group. Khi thay đổi path, phải cập nhật đồng bộ:

- `requestMatchers` trong Spring Security.
- Rule của reverse proxy hoặc API gateway.
- URL mà pipeline hoặc client dùng để tải OpenAPI.
- `swagger-ui.url` hoặc `swagger-ui.urls` nếu UI tải document qua endpoint tùy chỉnh.
- Health check hoặc contract test có phụ thuộc đường dẫn cũ.

Không dùng một URL khó đoán như biện pháp bảo mật duy nhất. URL không phải credentials và có thể xuất hiện trong log, cấu hình client hoặc lịch sử trình duyệt.

## 9. Bảo vệ endpoint tài liệu bằng Spring Security

Nếu muốn giữ Swagger UI và API Docs cho một nhóm người dùng, có thể bảo vệ các endpoint bằng Spring Security. Ví dụ dưới đây yêu cầu authority `DOCS_READ` cho cả giao diện và document:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain documentationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/swagger-ui.html",
                    "/swagger-ui/**",
                    "/v3/api-docs/**"
                ).hasAuthority("DOCS_READ")
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

Đây là ví dụ matcher cho đường dẫn mặc định. Nếu đã đổi `springdoc.swagger-ui.path` hoặc `springdoc.api-docs.path`, cập nhật matcher cho khớp. Nếu có nhiều `SecurityFilterChain`, kiểm tra thứ tự và `securityMatcher` để chắc chắn request tài liệu đi qua chain mong muốn.

Với OAuth2 Resource Server, `DOCS_READ` có thể được ánh xạ từ scope như `SCOPE_docs:read`. Với form login hoặc session, authority có thể đến từ user role. Chọn quy tắc phù hợp với cơ chế xác thực thực tế.

Swagger UI tải HTML, JavaScript, CSS và OpenAPI document. Nếu chỉ bảo vệ JSON mà để UI public, người không có quyền vẫn có thể mở giao diện nhưng không tải được tài liệu. Nếu chỉ bảo vệ UI mà JSON public, người dùng có thể bỏ qua giao diện và gọi thẳng API Docs. Hãy bảo vệ cả hai nhóm nếu chính sách yêu cầu.

## 10. Tắt API Docs không thay thế authorization của API nghiệp vụ

`springdoc.api-docs.enabled=false` chỉ điều khiển endpoint tài liệu Springdoc. Nó không làm các controller nghiệp vụ trở nên riêng tư hơn và không thay đổi rule xác thực của `/api/**`.

Ví dụ:

- `/v3/api-docs` bị tắt nhưng `/api/admin/users` vẫn có thể truy cập nếu Spring Security cấu hình `permitAll()`.
- Swagger UI bị tắt nhưng `/v3/api-docs` vẫn có thể công khai toàn bộ path, schema và security metadata.
- API Docs được bảo vệ bằng login nhưng API nghiệp vụ vẫn cần authorization riêng theo resource và operation.

Hãy dùng Spring Security, gateway, network policy hoặc cơ chế phân quyền tương ứng để bảo vệ API thật. Tắt tài liệu chỉ giảm bề mặt công bố tài liệu qua các endpoint Springdoc.

## 11. Ảnh hưởng đến OpenAPI generation trong pipeline build

Một số pipeline dùng Springdoc OpenAPI Maven Plugin để gọi ứng dụng đang chạy, tải `/v3/api-docs` rồi lưu document thành artifact. Nếu profile mà pipeline khởi chạy đặt:

```yaml
springdoc:
  api-docs:
    enabled: false
```

plugin có thể không tải được document vì endpoint đã bị tắt. Điều này không có nghĩa OpenAPI annotations bị mất; endpoint chỉ không được công bố trong lần chạy đó.

Các cách tổ chức thường gặp:

1. Dùng profile riêng cho bước sinh tài liệu, trong đó `springdoc.api-docs.enabled=true`.
2. Chạy ứng dụng với profile build/test, xuất JSON/YAML thành artifact rồi triển khai production với profile tắt API Docs.
3. Lưu document đã xuất trong artifact hoặc static hosting riêng và cấp quyền truy cập theo chính sách.

Không nên vô tình dùng profile production tắt API Docs cho bước build cần tải `/v3/api-docs`. Hãy tách cấu hình build-time khỏi cấu hình runtime và xác minh URL mà plugin gọi.

## 12. Kiểm tra cấu hình sau khi triển khai

Sau khi thay đổi profile hoặc environment variable, khởi động lại ứng dụng theo quy trình triển khai rồi kiểm tra từng endpoint.

Ví dụ khi mong muốn tắt cả hai:

```bash
curl -i https://api.example.com/swagger-ui.html
curl -i https://api.example.com/v3/api-docs
curl -i https://api.example.com/v3/api-docs.yaml
```

Kết quả mong đợi là các endpoint tài liệu không còn được cung cấp. Status có thể là 404 hoặc phản hồi do security gateway tạo ra, tùy kiến trúc.

Nếu muốn tắt UI nhưng giữ API Docs:

```bash
curl -i https://api.example.com/swagger-ui.html
curl -i https://api.example.com/v3/api-docs
```

Kỳ vọng UI không được cung cấp còn API Docs vẫn trả JSON. Nếu muốn giữ UI nhưng dùng file tĩnh, xác minh cả URL giao diện và URL file YAML mà UI tải.

Có thể kiểm tra tài liệu group:

```bash
curl -i https://api.example.com/v3/api-docs/admin
```

Nếu API Docs bị tắt, kiểm tra cả URL mặc định, YAML và group. Không chỉ kiểm tra `/v3/api-docs` rồi kết luận mọi endpoint tài liệu đều đã tắt.

## 13. Ma trận cấu hình theo nhu cầu

| Nhu cầu | `swagger-ui.enabled` | `api-docs.enabled` | Ghi chú |
|---|---:|---:|---|
| Local developer đầy đủ | `true` | `true` | UI và JSON/YAML đều hoạt động |
| Pipeline cần document, không cần UI | `false` | `true` | Có thể tải `/v3/api-docs` để sinh client |
| UI dùng OpenAPI file tĩnh | `true` | `false` | Phải cấu hình `swagger-ui.url` hoặc `urls` |
| Production không công bố tài liệu | `false` | `false` | API nghiệp vụ vẫn cần security riêng |
| Staging cho QA/đối tác | `true` | `true` | Nên bảo vệ cả UI và API Docs |

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tắt Swagger UI nhưng `/v3/api-docs` vẫn truy cập được | Chỉ đặt `swagger-ui.enabled=false` | Đặt thêm `api-docs.enabled=false` nếu muốn tắt document |
| Swagger UI mở được nhưng báo lỗi tải definition | API Docs đã tắt hoặc URL nguồn sai | Cấu hình `swagger-ui.url`/`urls` đến document khác hoặc bật API Docs |
| Đã đặt YAML production nhưng UI vẫn bật | Profile `prod` chưa active hoặc biến môi trường override | Kiểm tra `SPRING_PROFILES_ACTIVE` và property source |
| Endpoint tài liệu vẫn truy cập sau khi đổi path | Chỉ đổi URL, chưa tắt endpoint hoặc cập nhật proxy | Kiểm tra `api-docs.enabled`, path và route gateway |
| `/v3/api-docs` bị chặn nhưng Swagger UI vẫn tải trang | Chỉ bảo vệ API Docs hoặc chỉ bảo vệ UI | Kiểm tra cả `/swagger-ui.html`, `/swagger-ui/**` và `/v3/api-docs/**` |
| Maven plugin không lấy được OpenAPI | Build profile tắt API Docs | Dùng profile build có `api-docs.enabled=true` |
| Production tắt docs nhưng API nghiệp vụ vẫn mở | Nhầm tắt docs với tắt API | Cấu hình authorization cho route nghiệp vụ |
| Group docs vẫn lộ thông tin | Chỉ kiểm tra URL document mặc định | Kiểm tra `/v3/api-docs/{group}` và gateway rule tương ứng |
| Cấu hình có hiệu lực khác dự kiến | Biến môi trường hoặc config server ghi đè YAML | Kiểm tra giá trị hiệu lực và profile đang chạy |

## 15. Checklist triển khai theo môi trường

- [ ] Đã quyết định riêng Swagger UI có được phép hiển thị ở môi trường này không.
- [ ] Đã quyết định riêng endpoint OpenAPI JSON/YAML có được phép truy cập không.
- [ ] Đã cấu hình `springdoc.swagger-ui.enabled` và `springdoc.api-docs.enabled` tường minh.
- [ ] Profile tương ứng được kích hoạt đúng khi chạy ứng dụng.
- [ ] Environment variable không vô tình ghi đè cấu hình profile.
- [ ] Nếu UI vẫn bật trong khi API Docs tắt, đã cấu hình nguồn OpenAPI khác.
- [ ] Nếu đổi path, đã cập nhật Spring Security, gateway, pipeline và UI URLs.
- [ ] Đã bảo vệ cả UI resources và API Docs nếu tài liệu chỉ dành cho người dùng được cấp quyền.
- [ ] Không xem việc tắt docs là thay thế cho bảo vệ API nghiệp vụ.
- [ ] Pipeline sinh tài liệu dùng profile có API Docs bật.
- [ ] Đã kiểm tra JSON, YAML và mọi group endpoint sau triển khai.
- [ ] Đã xác minh kết quả từ bên ngoài môi trường, qua đúng gateway/proxy production.

`springdoc.swagger-ui.enabled` điều khiển giao diện; `springdoc.api-docs.enabled` điều khiển các endpoint tài liệu OpenAPI. Có thể bật/tắt độc lập và đặt giá trị theo Spring Profile hoặc environment variable. Nếu cần bảo vệ tài liệu, dùng Spring Security hoặc gateway cho cả UI lẫn JSON/YAML; nếu pipeline cần sinh artifact, chạy bước đó với cấu hình API Docs được bật. Cách tách này giúp mỗi môi trường công bố đúng mức tài liệu cần thiết mà không làm thay đổi hành vi của API nghiệp vụ.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
- [Springdoc OpenAPI – Properties and configuration](https://springdoc.org/properties.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
