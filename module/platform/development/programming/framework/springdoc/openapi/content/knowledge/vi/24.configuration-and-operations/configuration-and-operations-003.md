# Thuộc tính bật hoặc tắt endpoint đặc tả

Springdoc tự động tạo endpoint HTTP để cung cấp OpenAPI document từ controller, request mapping và Swagger annotations của ứng dụng Spring Boot. Thuộc tính `springdoc.api-docs.enabled` điều khiển việc Springdoc có công bố các endpoint đặc tả này hay không. Giá trị mặc định là `true`; đặt thành `false` để tắt endpoint API Docs trong môi trường không cần công bố tài liệu.

Đây là một cấu hình ở cấp ứng dụng, thường được đặt trong `application.yml`, `application.properties`, file cấu hình theo profile hoặc environment variable. Cần phân biệt nó với `springdoc.swagger-ui.enabled`, vốn điều khiển giao diện Swagger UI. API Docs và UI là hai phần có thể được bật/tắt riêng.

## 1. `springdoc.api-docs.enabled` làm gì?

Thuộc tính có kiểu Boolean:

| Giá trị | Hành vi |
|---|---|
| `true` | Springdoc bật endpoint OpenAPI theo cấu hình hiện tại. Đây là giá trị mặc định. |
| `false` | Springdoc tắt các endpoint API Docs do nó cung cấp. |

Ví dụ YAML:

```yaml
springdoc:
  api-docs:
    enabled: false
```

Ví dụ `application.properties`:

```properties
springdoc.api-docs.enabled=false
```

Thuộc tính này điều khiển endpoint tài liệu ở phía Springdoc. Nó không thay đổi các mapping nghiệp vụ như `/api/orders`, không xóa controller, không sửa OpenAPI annotations và không thay đổi quy tắc authorization của API.

Springdoc v2 ghi nhận giá trị mặc định `true` trong bảng configuration properties và FAQ chính thức hướng dẫn dùng `springdoc.api-docs.enabled=false` để vô hiệu hóa endpoint `/v3/api-docs` cùng các endpoint đặc tả liên quan. <https://springdoc.org/v2/core-properties.html>

## 2. Endpoint nào bị ảnh hưởng?

Với cấu hình mặc định, ứng dụng thường cung cấp các URL sau:

| Endpoint | Mục đích |
|---|---|
| `/v3/api-docs` | OpenAPI document dạng JSON |
| `/v3/api-docs.yaml` | OpenAPI document dạng YAML |
| `/v3/api-docs/{group}` | OpenAPI document của một `GroupedOpenApi` |
| `/v3/api-docs/swagger-config` | Cấu hình mà Swagger UI dùng để tìm document |

Khi `springdoc.api-docs.enabled=false`, các endpoint API Docs do Springdoc đăng ký không còn được cung cấp theo cấu hình thông thường. Nếu đã đổi `springdoc.api-docs.path`, hãy kiểm tra path tùy chỉnh thay vì chỉ gọi `/v3/api-docs`.

Ví dụ khi path được đổi:

```yaml
springdoc:
  api-docs:
    path: /openapi
    enabled: true
```

Các URL tương ứng thường là:

```text
/openapi
/openapi.yaml
/openapi/{group}
/openapi/swagger-config
```

`springdoc.api-docs.path` chỉ đổi base path; nó không bật hoặc tắt endpoint. Nếu muốn tắt endpoint, dùng `enabled: false`.

## 3. Bật endpoint đặc tả tường minh

Trong môi trường local hoặc integration test, có thể khai báo rõ endpoint được bật:

```yaml
springdoc:
  api-docs:
    enabled: true
```

Sau khi ứng dụng khởi động, tải JSON:

```bash
curl -i http://localhost:8080/v3/api-docs
```

Hoặc tải YAML:

```bash
curl -i http://localhost:8080/v3/api-docs.yaml
```

Response JSON hợp lệ thường có trường `openapi`, `info` và `paths`. Ví dụ phần đầu document:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "version": "1.0.0"
  },
  "paths": {
    "/api/orders": {
      "get": {
        "summary": "Liệt kê đơn hàng"
      }
    }
  }
}
```

Phiên bản OpenAPI và nội dung thực tế phụ thuộc cấu hình, annotations và các endpoint được Springdoc phát hiện. Đoạn JSON chỉ minh họa cấu trúc.

## 4. Tắt endpoint đặc tả

Để tắt API Docs trong một môi trường, đặt:

```yaml
springdoc:
  api-docs:
    enabled: false
```

Sau khi khởi động lại ứng dụng, kiểm tra URL đã cấu hình:

```bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/v3/api-docs/swagger-config
```

Endpoint không còn được phục vụ bởi Springdoc. Thông thường request sẽ nhận 404 nếu không có route khác xử lý cùng path. Nếu Spring Security, gateway hoặc reverse proxy chặn request trước, status có thể là 401, 403 hoặc response khác. Vì vậy, hãy kiểm tra status, response body và lớp đang trả response.

Việc tắt endpoint không xóa metadata khỏi source code. Các annotation như `@Operation`, `@Schema`, `@ApiResponse` vẫn có thể được giữ nguyên để bật lại tài liệu ở môi trường khác hoặc dùng trong bước build tạo artifact.

## 5. Phân biệt API Docs với Swagger UI

Springdoc có hai thuộc tính độc lập:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

| `api-docs.enabled` | `swagger-ui.enabled` | Kết quả dự kiến |
|---:|---:|---|
| `true` | `true` | Có OpenAPI JSON/YAML và Swagger UI |
| `true` | `false` | Có API Docs, không có giao diện Swagger UI |
| `false` | `true` | API Docs Springdoc bị tắt; UI entry/resources có thể vẫn được bật nhưng không tải được document mặc định từ swagger-config/API Docs đã tắt |
| `false` | `false` | Tắt cả API Docs và Swagger UI do Springdoc cung cấp |

Nếu `api-docs.enabled=false` nhưng vẫn bật Swagger UI, giao diện mặc định không thể lấy OpenAPI document từ endpoint Springdoc đã bị tắt. Trường hợp UI cần hiển thị một file OpenAPI tĩnh hoặc document bên ngoài là cấu hình nâng cao; phải cấu hình nguồn document và kiểm tra `swagger-config` cùng URL nguồn theo phiên bản Springdoc đang dùng.

Nếu chỉ muốn cung cấp JSON/YAML cho pipeline, không cần Swagger UI, có thể dùng starter API tương ứng. Với Spring MVC và Springdoc v2, artifact thường dùng là:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Với ứng dụng WebFlux, chọn `springdoc-openapi-starter-webflux-api`. Nếu muốn có cả giao diện, dùng starter `*-ui` phù hợp với stack. Dependency lựa chọn quyết định thành phần nào được đưa vào ứng dụng; `api-docs.enabled` vẫn là công tắc cấu hình endpoint đặc tả.

## 6. Đặt giá trị theo Spring Profile

Thông thường local và test cần API Docs, còn production có thể tắt endpoint công bố trực tiếp.

`application.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
```

`application-prod.yml`:

```yaml
springdoc:
  api-docs:
    enabled: false
```

Chạy production với profile `prod`:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Hoặc dùng environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Khi profile `prod` hoạt động, giá trị `false` trong `application-prod.yml` ghi đè giá trị mặc định `true` từ `application.yml`. Nếu không kích hoạt profile `prod`, cấu hình mặc định vẫn bật API Docs.

Một cấu hình khác là bật API Docs ở staging nhưng tắt ở production:

```yaml
# application-staging.yml
springdoc:
  api-docs:
    enabled: true
```

```yaml
# application-prod.yml
springdoc:
  api-docs:
    enabled: false
```

Staging có thể được dùng bởi QA, đối tác hoặc pipeline contract test. Nếu tài liệu chỉ dành cho người có quyền, vẫn cần bảo vệ endpoint bằng Spring Security hoặc gateway.

## 7. Điều khiển bằng environment variable hoặc command line

Spring Boot relaxed binding ánh xạ property:

```text
springdoc.api-docs.enabled
```

sang environment variable:

```text
SPRINGDOC_API_DOCS_ENABLED
```

Ví dụ Linux/container:

```bash
SPRINGDOC_API_DOCS_ENABLED=false java -jar app.jar
```

Ví dụ Docker Compose:

```yaml
services:
  orders-api:
    image: example/orders-api:latest
    environment:
      SPRINGDOC_API_DOCS_ENABLED: "false"
```

Ví dụ PowerShell:

```powershell
$env:SPRINGDOC_API_DOCS_ENABLED = "false"
java -jar app.jar
```

Có thể truyền qua command line:

```bash
java -jar app.jar --springdoc.api-docs.enabled=false
```

Environment variable hoặc command-line argument có thể ghi đè giá trị trong YAML theo thứ tự ưu tiên property source của Spring Boot. Nếu file production đặt `false` nhưng endpoint vẫn hoạt động, hãy kiểm tra biến môi trường, command line, config server và profile thực tế.

## 8. Đổi path không giống tắt endpoint

Hai cấu hình sau có ý nghĩa khác nhau:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
    enabled: true
```

Endpoint vẫn được bật, chỉ chuyển từ `/v3/api-docs` sang `/internal/openapi`.

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
    enabled: false
```

Endpoint API Docs bị tắt; đổi path không làm endpoint xuất hiện trở lại.

Không dùng path khó đoán như một biện pháp bảo mật. URL có thể xuất hiện trong log, cấu hình frontend, browser history hoặc tài liệu tích hợp. Nếu tài liệu cần được bảo vệ, dùng authentication/authorization và chính sách mạng phù hợp.

## 9. Phân biệt tắt endpoint, lọc operation và ẩn operation

Các cấu hình dưới đây giải quyết những nhu cầu khác nhau:

| Cơ chế | Tác dụng | Endpoint API Docs còn tồn tại? |
|---|---|---:|
| `springdoc.api-docs.enabled=false` | Tắt endpoint tài liệu do Springdoc cung cấp | Không, theo cấu hình Springdoc thông thường |
| `springdoc.paths-to-match` | Chỉ đưa các path khớp điều kiện vào document | Có |
| `springdoc.packages-to-scan` | Chỉ quét controller trong package được chọn | Có |
| `@Hidden` | Ẩn operation hoặc controller khỏi document | Có |
| Spring Security `denyAll()` | Từ chối request đến endpoint theo authorization rule | Có nhưng không truy cập được qua security chain |
| `springdoc.api-docs.path` | Đổi URL endpoint tài liệu | Có |

Nếu chỉ muốn loại một controller quản trị khỏi tài liệu public, không cần tắt toàn bộ API Docs. Dùng `@Hidden`, package/path filter hoặc `GroupedOpenApi` theo mục tiêu. Nếu muốn endpoint tài liệu không được công bố ở một môi trường, dùng `api-docs.enabled=false`.

Ví dụ lọc path:

```yaml
springdoc:
  paths-to-match:
    - /api/public/**
```

Ví dụ ẩn controller:

```java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/api/internal")
class InternalController {
}
```

Trong cả hai ví dụ, endpoint `/v3/api-docs` vẫn có thể trả document nhưng không chứa các operation bị lọc hoặc ẩn.

## 10. Tắt API Docs không bảo vệ API nghiệp vụ

`springdoc.api-docs.enabled=false` không thay thế Spring Security. Nó không làm cho `/api/admin/**` tự động yêu cầu đăng nhập và không ngăn client gọi controller nếu route nghiệp vụ vẫn được phép truy cập.

Ví dụ:

- `/v3/api-docs` đã tắt nhưng `/api/orders` vẫn trả dữ liệu theo authorization rule hiện tại.
- `/v3/api-docs` vẫn bật nhưng Spring Security có thể giới hạn người được tải tài liệu.
- Swagger UI bị tắt nhưng JSON/YAML vẫn có thể được tải nếu API Docs đang bật.

Nếu muốn endpoint API Docs vẫn tồn tại nhưng chỉ một nhóm người dùng được truy cập, bảo vệ path tài liệu bằng Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/v3/api-docs/**").hasAuthority("DOCS_READ")
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

Đây là lựa chọn khác với tắt endpoint. Rule cần khớp `springdoc.api-docs.path` nếu path đã được tùy chỉnh. Nếu có nhiều `SecurityFilterChain`, hãy kiểm tra matcher và thứ tự chain để bảo đảm request tài liệu đi qua đúng policy.

## 11. Ảnh hưởng đến Swagger UI và tài liệu tĩnh

Swagger UI mặc định lấy config từ endpoint `swagger-config`, sau đó tải OpenAPI JSON/YAML. Khi API Docs bị tắt, URL config hoặc document mặc định không còn được cung cấp theo cấu hình thông thường. Do đó, giao diện có thể mở được nhưng báo lỗi tải definition.

Nếu muốn UI đọc file tĩnh hoặc URL bên ngoài trong khi API Docs Springdoc bị tắt, hãy xác minh cấu hình riêng cho phiên bản Springdoc đang dùng. Springdoc FAQ có một hướng dẫn nâng cao cho trường hợp dùng spec file riêng: khi tắt `springdoc.api-docs.enabled`, auto-configuration thông thường bị ảnh hưởng và cần cấu hình tối thiểu các bean liên quan trước khi trỏ Swagger UI đến file spec. Không giả định chỉ thêm `springdoc.swagger-ui.url` là đủ trong mọi phiên bản.

Nếu mục tiêu chỉ là ẩn giao diện nhưng vẫn giữ document cho pipeline, dùng:

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
```

Nếu mục tiêu là tắt cả tài liệu lẫn UI:

```yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
```

## 12. Ảnh hưởng đến build và pipeline sinh tài liệu

Một số pipeline khởi động ứng dụng rồi gọi `/v3/api-docs` để lưu OpenAPI JSON/YAML thành artifact, kiểm tra contract hoặc sinh SDK. Nếu profile của bước đó đặt `springdoc.api-docs.enabled=false`, lệnh tải tài liệu sẽ thất bại vì endpoint không được cung cấp.

Có thể tách profile:

```yaml
# application-openapi-build.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
```

Pipeline kích hoạt profile `openapi-build`, tải document và lưu thành artifact. Production dùng profile riêng có `api-docs.enabled=false`.

Ví dụ:

```bash
java -jar app.jar --spring.profiles.active=openapi-build
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
```

Hãy bảo đảm bước tải document chạy khi ứng dụng đã sẵn sàng và đúng profile. Không dùng profile production tắt API Docs cho bước sinh artifact cần endpoint này.

## 13. Kiểm thử cấu hình bật/tắt

Nên kiểm thử hai trạng thái trong hai application context hoặc profile riêng. Với trạng thái bật, xác nhận endpoint trả OpenAPI JSON:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "springdoc.api-docs.enabled=true")
@AutoConfigureMockMvc
class ApiDocsEnabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.paths").exists());
    }
}
```

Với trạng thái tắt:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "springdoc.api-docs.enabled=false")
@AutoConfigureMockMvc
class ApiDocsDisabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void doesNotExposeOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isNotFound());
    }
}
```

Test 404 giả định không có controller, proxy mock hoặc security rule khác xử lý path này. Nếu Spring Security chặn trước, request có thể nhận 401/403; hãy cấu hình test security để kiểm tra chính hành vi endpoint hoặc điều chỉnh assertion theo lớp đang được kiểm thử.

Nếu đã đổi `springdoc.api-docs.path`, thay URL trong test bằng path tùy chỉnh. Nếu dùng group, kiểm tra thêm `/v3/api-docs/{group}` khi bật và xác nhận các endpoint tương ứng không còn được phục vụ khi tắt.

## 14. Chẩn đoán khi property không có hiệu lực

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Đặt `false` nhưng `/v3/api-docs` vẫn trả 200 | Profile chưa active hoặc property source khác ghi đè | Kiểm tra `SPRING_PROFILES_ACTIVE`, environment và command line |
| Đã đổi `api-docs.path` nhưng vẫn gọi URL cũ | Client/proxy/test chưa cập nhật path | Kiểm tra cấu hình hiệu lực và gọi URL mới |
| Swagger UI mở nhưng không tải API | API Docs hoặc swagger-config đã tắt | Kiểm tra Network tab và endpoint config/document |
| API Docs trả 401/403 thay vì 404 | Spring Security hoặc gateway chặn trước | Kiểm tra filter chain, matcher và proxy |
| Pipeline không tải được OpenAPI | Build profile đang tắt API Docs | Dùng profile build có `api-docs.enabled=true` |
| Một operation biến mất nhưng endpoint vẫn trả 200 | Path/package filter hoặc `@Hidden` loại operation | Kiểm tra `paths` trong JSON thay vì chỉ kiểm tra status |
| Tắt API Docs nhưng API nghiệp vụ vẫn chạy | Hai nhóm endpoint độc lập | Kiểm tra authorization của route nghiệp vụ riêng |
| Swagger UI dùng spec tĩnh không hoạt động | Cấu hình nguồn document chưa đủ khi auto-configuration bị tắt | Đối chiếu FAQ và cấu hình bean của phiên bản đang dùng |

## 15. Checklist vận hành

- [ ] Đã xác định môi trường có cần công bố OpenAPI JSON/YAML hay không.
- [ ] Đã đặt `springdoc.api-docs.enabled` tường minh theo profile.
- [ ] Đã kiểm tra giá trị mặc định là `true` nếu không có cấu hình ghi đè.
- [ ] Đã phân biệt `api-docs.enabled` với `swagger-ui.enabled`.
- [ ] Đã cập nhật endpoint tùy chỉnh nếu `springdoc.api-docs.path` khác mặc định.
- [ ] Đã kiểm tra JSON, YAML, swagger-config và từng group endpoint.
- [ ] Đã phân biệt tắt endpoint với lọc path/package hoặc `@Hidden`.
- [ ] Đã bảo vệ API nghiệp vụ bằng authorization độc lập.
- [ ] Nếu giữ UI nhưng tắt API Docs, đã cấu hình và kiểm tra nguồn OpenAPI khác.
- [ ] Pipeline sinh tài liệu chạy với profile bật API Docs.
- [ ] Đã kiểm thử trạng thái bật và tắt trong application context tương ứng.
- [ ] Đã kiểm tra environment variable hoặc command line không ghi đè ngoài ý muốn.

`springdoc.api-docs.enabled` là công tắc bật/tắt endpoint đặc tả do Springdoc cung cấp và mặc định là `true`. Đặt `false` khi môi trường không cần công bố OpenAPI JSON/YAML; dùng Spring Profile hoặc environment variable để điều khiển theo môi trường. Thuộc tính này độc lập với Swagger UI, path filter, `@Hidden` và authorization của API nghiệp vụ. Sau khi thay đổi, hãy xác minh các URL JSON/YAML/group thực tế và bảo đảm pipeline build vẫn dùng cấu hình bật tài liệu khi cần sinh artifact.

## Tài liệu tham khảo

- [Springdoc OpenAPI v2 – Core properties](https://springdoc.org/v2/core-properties.html)
- [Springdoc OpenAPI v2 – Features: Disabling API Docs and Swagger UI](https://springdoc.org/v2/features.html)
- [Springdoc OpenAPI v2 – FAQ](https://springdoc.org/v2/faq.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
