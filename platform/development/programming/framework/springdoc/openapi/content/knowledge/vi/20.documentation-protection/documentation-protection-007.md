# Ẩn operation không thay thế xác thực hoặc phân quyền

Springdoc-openapi cho phép ẩn controller hoặc operation khỏi tài liệu OpenAPI bằng `@Hidden`, `@Operation(hidden = true)` và bộ lọc của `GroupedOpenApi`. Những cách này chỉ điều khiển nội dung được công bố trong tài liệu và Swagger UI. Chúng không xóa mapping Spring MVC, không chặn HTTP request và không cấp hay thu hồi quyền truy cập.

Một endpoint bị ẩn khỏi Swagger UI vẫn có thể được gọi trực tiếp bằng curl, Postman, một ứng dụng khác hoặc một URL đã biết. Vì vậy, bảo vệ API phải được thực hiện ở runtime bằng Spring Security, method security và kiểm tra quyền trên từng tài nguyên. Tài liệu OpenAPI và giao diện Swagger UI cũng là các bề mặt cần kiểm soát riêng, vì chúng có thể tiết lộ đường dẫn, schema, ví dụ và khả năng của hệ thống.

## 1. Ẩn operation có tác dụng gì?

Ẩn operation có thể giúp:

- Loại endpoint nội bộ khỏi tài liệu dành cho đối tác.
- Không đưa endpoint thử nghiệm hoặc endpoint vận hành vào tài liệu public.
- Giảm nhiễu trong Swagger UI để người dùng tập trung vào API họ được hướng dẫn sử dụng.
- Tách tài liệu theo audience bằng các nhóm OpenAPI khác nhau.

Ví dụ, controller có endpoint nội bộ:

```java
@RestController
@RequestMapping("/internal/cache")
class CacheMaintenanceController {

    @PostMapping("/clear")
    void clearCache() {
        cacheService.clear();
    }
}
```

Nếu operation không xuất hiện trong Swagger UI, mapping `/internal/cache/clear` vẫn tồn tại trong Spring MVC. Bất kỳ client nào gửi request đến URL này vẫn có thể chạm tới controller. Kết quả truy cập phụ thuộc cấu hình bảo mật runtime.

Ẩn là một quyết định về công bố tài liệu. Xác thực và phân quyền là quyết định về việc ai được phép thực hiện thao tác.

## 2. Ẩn controller bằng `@Hidden`

Có thể đặt `@Hidden` ở cấp controller để springdoc không đưa các operation của controller đó vào OpenAPI document:

```java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/cache")
class CacheMaintenanceController {

    @PostMapping("/clear")
    void clearCache() {
        cacheService.clear();
    }
}
```

`@Hidden` làm controller không xuất hiện trong tài liệu được springdoc tạo. Spring vẫn đăng ký controller và mapping như bình thường. Nếu endpoint cần giới hạn cho quản trị viên hoặc service nội bộ, phải có quy tắc authorization riêng.

Không dùng `@Hidden` như một biện pháp bảo mật cho endpoint có tác động lớn như xóa cache, chạy tác vụ nền, thay đổi cấu hình hoặc quản lý dữ liệu.

## 3. Ẩn một operation bằng `@Operation(hidden = true)`

Nếu chỉ muốn ẩn một method trong controller nhưng vẫn công bố các method khác, dùng thuộc tính `hidden` của `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/reports")
    List<ReportResponse> listReports() {
        return reportService.list();
    }

    @Operation(hidden = true)
    @PostMapping("/internal/reports/rebuild-index")
    void rebuildIndex() {
        reportService.rebuildIndex();
    }
}
```

Trong ví dụ, operation `GET /api/reports` vẫn xuất hiện trong tài liệu; operation `POST /internal/reports/rebuild-index` bị ẩn. Cả hai mapping vẫn được Spring MVC đăng ký.

Chọn `@Hidden` khi muốn ẩn toàn bộ controller hoặc phần tử được annotation hỗ trợ; chọn `@Operation(hidden = true)` khi muốn ẩn một operation cụ thể. Sau khi thêm annotation, kiểm tra OpenAPI JSON/YAML để xác nhận đúng operation đã biến mất khỏi document.

## 4. Lọc operation khỏi một nhóm bằng `GroupedOpenApi`

Một operation có thể không cần ẩn toàn cục. Ví dụ endpoint nội bộ cần xuất hiện trong tài liệu dành cho nhân viên nhưng không được đưa vào tài liệu public. Khi đó, lọc theo path hoặc package ở từng group là lựa chọn phù hợp.

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/internal/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/api/internal/**", "/internal/**")
                .build();
    }
}
```

Với cấu hình này, endpoint nội bộ bị loại khỏi document `public` nhưng có thể xuất hiện trong document `internal`. Bộ lọc chỉ tác động tài liệu tương ứng; nó không thay đổi request mapping hoặc security filter chain.

Có thể lọc theo package bằng `packagesToScan(...)` và `packagesToExclude(...)`. Dù dùng path hay package, không coi việc một endpoint vắng mặt trong group public là bằng chứng endpoint đã được bảo vệ.

## 5. Phân biệt ẩn toàn cục và ẩn theo group

| Cách làm | Ảnh hưởng tài liệu | Ảnh hưởng endpoint runtime |
|---|---|---|
| `@Hidden` trên controller | Ẩn controller khỏi tài liệu được springdoc tạo | Không |
| `@Operation(hidden = true)` | Ẩn operation khỏi tài liệu | Không |
| `pathsToExclude(...)` | Loại path khỏi group được cấu hình | Không |
| `packagesToExclude(...)` | Loại controller package khỏi group được cấu hình | Không |
| Không đăng ký Swagger UI | Không cung cấp giao diện UI tại cấu hình đó | Không |
| Tắt `springdoc.api-docs.enabled` | Không cung cấp endpoint OpenAPI theo cấu hình đó | Không |
| Spring Security authorization rule | Có thể từ chối request runtime | Có |
| Method security và kiểm tra quyền tài nguyên | Có thể từ chối lời gọi phương thức/dữ liệu không được phép | Có |

Ẩn operation và bảo vệ operation có thể được áp dụng đồng thời. Ví dụ, endpoint nội bộ có thể không xuất hiện trong tài liệu public và vẫn yêu cầu role `OPS_ADMIN` ở runtime.

## 6. Vì sao ẩn operation không phải là security boundary?

OpenAPI document là mô tả các operation. Swagger UI là một giao diện đọc tài liệu và gửi request thử nghiệm. Cả hai đều không nằm trên đường thực thi bắt buộc của mọi HTTP client.

Client có thể gọi API bằng:

- `curl` hoặc HTTPie.
- Postman hoặc Insomnia.
- Một service backend khác.
- SDK đã được generate trước đó.
- Script hoặc công cụ tự viết.
- URL được ghi nhận từ log, browser history hoặc tài liệu cũ.

Các client này không cần mở Swagger UI và cũng không cần operation xuất hiện trong OpenAPI. Nếu server cho phép request, controller vẫn thực thi.

Ví dụ, dù `/internal/cache/clear` đã bị ẩn, request sau vẫn đến server:

```bash
curl -i -X POST \
  https://api.example.com/internal/cache/clear
```

Nếu Spring Security không chặn request và controller không kiểm tra quyền, thao tác có thể được thực hiện. Việc người dùng không nhìn thấy endpoint trong giao diện không ngăn được request này.

## 7. Bảo vệ endpoint runtime bằng Spring Security

Các quy tắc authorization cần dựa trên path, HTTP method, role, authority hoặc policy phù hợp. Ví dụ endpoint quản trị chỉ dành cho người có role `OPS_ADMIN`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/internal/**")
                            .hasRole("OPS_ADMIN")
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/api/**")
                            .authenticated()
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Đây là ví dụ cấu hình Basic để minh họa quy tắc phân quyền; ứng dụng thực tế có thể dùng JWT Resource Server, session hoặc cơ chế xác thực khác. Cần có `AuthenticationProvider`/user store phù hợp để xác minh danh tính. Không dùng tài khoản mẫu hoặc mật khẩu hard-code trong production.

Thứ tự matcher có ý nghĩa. Quy tắc cụ thể `/internal/**` và `/api/admin/**` phải đứng trước quy tắc tổng quát `/api/**`. Nếu đặt `.anyRequest().authenticated()` trước, các matcher phía sau sẽ không còn cơ hội áp dụng.

Các URL thực tế có thể chịu ảnh hưởng của context path, servlet path hoặc reverse proxy. Hãy kiểm tra matcher với đường dẫn mà Spring Security nhận được.

## 8. Bảo vệ Swagger UI và endpoint OpenAPI riêng biệt

Ngay cả khi API runtime đã được bảo vệ, tài liệu OpenAPI có thể vẫn công khai. Tài liệu có thể tiết lộ:

- Tên path và operation nội bộ.
- Schema request/response và các trường dữ liệu.
- Mã lỗi, ví dụ và quy trình nghiệp vụ.
- Tên service, server URL, version hoặc extension.
- Các cơ chế xác thực và scope được sử dụng.

Nếu tài liệu chỉ dành cho nhân viên, cần bảo vệ cả Swagger UI và endpoint JSON/YAML. Ví dụ:

Thêm các matcher của tài liệu vào filter chain bảo vệ ứng dụng:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs.yaml",
                "/v3/api-docs/**",
                "/v3/api-docs/*.yaml"
        ).hasRole("API_DOCS")
        .requestMatchers("/internal/**").hasRole("OPS_ADMIN")
        .anyRequest().authenticated()
)
```

Đoạn code chỉ minh họa quy tắc cho bề mặt tài liệu. Nếu ứng dụng có nhiều `SecurityFilterChain`, cần đặt `securityMatcher` và `@Order` phù hợp để filter chain này không vô tình cho phép các request API khác. Trong một filter chain duy nhất, tích hợp matcher tài liệu vào cùng tập quy tắc API và đặt chúng trước các matcher tổng quát.

Swagger UI tải OpenAPI document từ endpoint JSON/YAML. Nếu UI được phép mở nhưng endpoint docs yêu cầu role mà người dùng không có, giao diện có thể tải trang nhưng hiển thị lỗi khi nạp spec. Cần cấp quyền nhất quán cho cả hai bề mặt hoặc không công bố UI cho nhóm người dùng đó.

Nếu đã đổi `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, group name hoặc context path, cập nhật request matcher tương ứng. Với group docs, kiểm tra các URL group và YAML thực tế được sinh ra.

## 9. Ẩn Swagger UI không có nghĩa là ẩn OpenAPI document

Hai thành phần có URL và cấu hình riêng:

| Thành phần | URL mặc định thường gặp | Cấu hình springdoc |
|---|---|---|
| Swagger UI | `/swagger-ui.html`, `/swagger-ui/index.html` | `springdoc.swagger-ui.enabled`, `springdoc.swagger-ui.path` |
| OpenAPI JSON | `/v3/api-docs` | `springdoc.api-docs.enabled`, `springdoc.api-docs.path` |
| OpenAPI YAML | `/v3/api-docs.yaml` | Cùng cấu hình api-docs |
| OpenAPI theo group | `/v3/api-docs/{group}` và dạng YAML tương ứng | `GroupedOpenApi` hoặc `springdoc.group-configs` |

Tắt Swagger UI không tự tắt endpoint JSON/YAML. Ngược lại, tắt API docs có thể khiến Swagger UI không còn tài liệu để tải. Cần quyết định riêng có cung cấp UI hay spec hay không.

Ví dụ tắt cả hai trong môi trường production:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Việc tắt springdoc chỉ ngừng công bố tài liệu theo cấu hình; nó không vô hiệu hóa các controller API. Các endpoint nghiệp vụ vẫn phải có security rule riêng. Sau khi thay đổi cấu hình, kiểm tra trực tiếp các URL UI và JSON/YAML để xác nhận chúng không còn được phục vụ.

## 10. Tách tài liệu public và internal

Một ứng dụng có thể tạo các group theo audience:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/internal/**", "/api/admin/**")
            .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
            .group("internal")
            .pathsToMatch("/api/internal/**", "/api/admin/**")
            .build();
}
```

Group public chỉ là tài liệu dành cho đối tác hoặc người tiêu dùng bên ngoài. Group internal có thể chứa operation quản trị hoặc tích hợp nội bộ. Cần xác định ai được truy cập `/v3/api-docs/internal` và `/swagger-ui` hiển thị group đó.

Nếu một endpoint không nên được công bố trong bất kỳ tài liệu nào, dùng `@Hidden` hoặc loại khỏi tất cả group liên quan. Nếu endpoint cần bảo vệ, thêm authorization runtime bất kể tài liệu có hiển thị hay không.

Đối với API public, nên kiểm tra cả schema và ví dụ. Ngay cả khi operation nội bộ bị loại khỏi group, một schema được dùng chung hoặc extension có thể vô tình tiết lộ tên thuộc tính, enum, cấu trúc hoặc thông tin nội bộ.

## 11. Phân quyền ở cấp method

Path-based authorization là lớp bảo vệ đầu tiên. Với quy tắc nghiệp vụ phức tạp, có thể dùng method security để kiểm tra authority tại service hoặc method cần bảo vệ.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class CacheAdministrationService {

    @PreAuthorize("hasAuthority('CACHE_CLEAR')")
    public void clearCache() {
        // Thực hiện thao tác xóa cache.
    }
}
```

Kích hoạt method security:


```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

## 12. Phân quyền theo từng tài nguyên, không chỉ theo URL

Chỉ kiểm tra role chung có thể chưa đủ. Ví dụ, người dùng có role `USER` được phép đọc đơn hàng nhưng chỉ được đọc đơn hàng thuộc tài khoản của mình. Nếu API chỉ xác thực người dùng rồi cho phép `GET /api/orders/{id}` với mọi ID, kẻ tấn công có thể thay ID để truy cập dữ liệu của người khác.

Đây là lỗi phân quyền cấp đối tượng thường được gọi là Broken Object Level Authorization (BOLA) hoặc IDOR. Cần kiểm tra quyền trên chính tài nguyên được yêu cầu:

```java
@Service
class OrderQueryService {

    @PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
    public Order getOrder(UUID orderId) {
        return orderRepository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
```

`orderAccess.canRead(...)` là bean policy của ứng dụng, chịu trách nhiệm kiểm tra người gọi có quyền đọc đơn hàng đó hay không. Có thể kiểm tra owner ID, tenant, quan hệ tổ chức hoặc quyền chia sẻ. Không dựa vào việc endpoint bị ẩn hay ID khó đoán để thay thế authorization.

Nếu cần che giấu sự tồn tại của tài nguyên, ứng dụng có thể chọn trả `404` thay cho `403` theo chính sách nhất quán. Đây là quyết định runtime; OpenAPI cần mô tả response mà client thực sự có thể nhận.

## 13. Authentication, authorization và ẩn tài liệu

Ba khái niệm giải quyết ba vấn đề riêng:

| Khái niệm | Câu hỏi | Cơ chế thường dùng |
|---|---|---|
| Ẩn/công bố tài liệu | Operation nào xuất hiện trong spec và Swagger UI? | `@Hidden`, `hidden = true`, group filters |
| Authentication | Client là ai và credential có hợp lệ không? | HTTP Basic, Bearer/JWT, OAuth2, session |
| Authorization | Client đã xác thực có được thực hiện hành động trên tài nguyên này không? | Request matcher, role/authority, method security, domain policy |

Một operation có thể bị ẩn nhưng vẫn yêu cầu authentication và authorization. Một operation có thể hiển thị công khai trong tài liệu nhưng runtime vẫn yêu cầu token. Tài liệu nên mô tả security requirement đúng với hành vi thực tế.

## 14. Tránh dùng các cách che giấu không có tác dụng bảo vệ

Các cách sau không đủ để bảo vệ API:

- Đổi URL endpoint thành một chuỗi khó đoán.
- Không ghi endpoint vào README hoặc Swagger UI.
- Xóa operation khỏi OpenAPI nhưng để route truy cập công khai.
- Chỉ kiểm tra nút hoặc menu ở frontend.
- Dùng JavaScript để ẩn nút thao tác.
- Dựa vào CORS để ngăn mọi client gọi API.
- Dùng HTTP method ít phổ biến với kỳ vọng người ngoài không đoán được.

CORS là chính sách trình duyệt kiểm soát việc trang web khác origin đọc response; nó không ngăn curl, Postman hoặc backend client gửi request. URL bí mật cũng có thể bị lộ qua log, lịch sử, telemetry hoặc traffic. Security phải được thực thi ở server cho mọi request.

## 15. Quản lý tài liệu theo môi trường

Không phải môi trường nào cũng cần công bố Swagger UI và OpenAPI document giống nhau. Có thể dùng profile riêng:

`application-dev.yml`:

```yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

`application-prod.yml`:

```yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
```

Nếu đội vận hành cần tài liệu trong production, có thể giữ docs bật nhưng giới hạn bằng Spring Security, mạng nội bộ, gateway hoặc identity-aware proxy. Không nên dựa duy nhất vào profile nếu cấu hình môi trường có thể bị ghi đè ngoài dự kiến; kiểm tra effective configuration khi triển khai.

Một lựa chọn khác là tạo và lưu OpenAPI artifact trong pipeline CI/CD rồi phân phối tài liệu qua developer portal có kiểm soát. Cách này cho phép tách việc công bố spec khỏi runtime service. Dù phân phối theo cách nào, cần rà soát nội dung trước khi public.

## 16. Kiểm thử rằng operation ẩn vẫn được bảo vệ

Sau khi dùng `@Hidden` hoặc filter group, cần kiểm thử hai điều riêng: operation có biến mất khỏi tài liệu hay không và request trực tiếp có bị kiểm soát đúng hay không.

Ma trận kiểm thử mẫu:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Tìm operation ẩn trong `/v3/api-docs` | Không xuất hiện trong document đã chọn |
| Mở Swagger UI và tìm operation ẩn | Không hiển thị operation đó |
| Gọi endpoint bảo vệ mà không xác thực | `401` hoặc challenge phù hợp |
| Gọi bằng user đã xác thực nhưng thiếu role | `403` hoặc response che giấu tài nguyên theo policy |
| Gọi bằng user có role/quyền phù hợp | Thành công theo nghiệp vụ |
| Gọi bằng user hợp lệ nhưng không sở hữu resource | Bị từ chối theo object-level policy |
| Truy cập trực tiếp `/v3/api-docs/internal` không đủ quyền | Bị từ chối nếu tài liệu nội bộ được bảo vệ |
| Truy cập Swagger UI không đủ quyền | Bị từ chối nếu UI được giới hạn |

Có thể kiểm tra endpoint runtime bằng curl:

```bash
# Không gửi credential: phải bị từ chối nếu endpoint yêu cầu xác thực
curl -i -X POST https://api.example.com/internal/cache/clear

# Gửi credential thử nghiệm có quyền phù hợp
curl -i -X POST \
  -H "Authorization: Bearer <access-token>" \
  https://api.example.com/internal/cache/clear
```

Chỉ dùng token thử nghiệm được cấp trong môi trường phù hợp. Không đưa token thật vào shell history hoặc log chia sẻ.

## 17. Kiểm tra tài liệu không tiết lộ thông tin ngoài ý muốn

Ẩn operation không phải lúc nào cũng đủ để tạo tài liệu public an toàn. Trước khi công bố spec, hãy rà soát:

- Server URL có chứa hostname nội bộ, IP private hoặc base path không dành cho người ngoài không?
- Description có nhắc tên hệ thống nội bộ, quy trình vận hành hoặc thông tin triển khai nhạy cảm không?
- Example có chứa email, ID, dữ liệu cá nhân, token hoặc credential thật không?
- Schema có tiết lộ thuộc tính nội bộ hoặc trường không nên công bố không?
- Enum có liệt kê trạng thái hoặc mã vận hành nhạy cảm không?
- Extension `x-*` có chứa thông tin nội bộ không?
- Security scheme có mô tả đúng flow và không chứa secret không?
- Các group có vô tình bao gồm endpoint nội bộ do path filter quá rộng không?

Đối với tài liệu public, nên có bước kiểm tra artifact OpenAPI trước khi phát hành. Với tài liệu nội bộ, vẫn cần kiểm soát quyền truy cập và lưu vết truy cập theo chính sách tổ chức.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Endpoint bị ẩn nhưng vẫn gọi được | `@Hidden` chỉ ảnh hưởng tài liệu | Thêm authorization runtime bằng Spring Security/method security |
| Swagger UI không hiển thị operation nhưng `/v3/api-docs` vẫn có | Chỉ ẩn ở UI hoặc đang xem group document khác | Kiểm tra OpenAPI JSON/YAML và annotation/filter đúng phạm vi |
| Tắt Swagger UI nhưng JSON vẫn truy cập được | UI và API docs có cấu hình riêng | Tắt hoặc bảo vệ `springdoc.api-docs` endpoint |
| Bảo vệ `/v3/api-docs` nhưng UI báo lỗi tải spec | Người dùng có quyền UI nhưng không có quyền docs endpoint | Cấp quyền nhất quán cho UI và spec hoặc bỏ UI |
| User thường gọi được endpoint nội bộ | Chỉ ẩn operation, thiếu matcher hoặc matcher đặt sai thứ tự | Bổ sung rule cụ thể trước rule tổng quát và kiểm thử |
| User có role vẫn đọc được dữ liệu người khác | Chỉ kiểm tra role, thiếu object-level authorization | Kiểm tra owner, tenant và policy trên từng resource |
| Public group vẫn lộ endpoint admin | Path filter chồng lấn hoặc exclude thiếu | Rà soát toàn bộ path trong document public |
| CORS được cấu hình nhưng curl vẫn gọi được endpoint | Nhầm CORS với authorization | Bảo vệ request tại server bằng authentication/authorization |
| Tài liệu production bị công khai ngoài ý muốn | Profile hoặc security rule không được áp dụng như dự kiến | Kiểm tra effective configuration và truy cập trực tiếp docs URLs |

## 19. Quy trình triển khai an toàn

1. Phân loại operation theo audience: public, authenticated, admin hoặc internal.
2. Dùng `@Hidden`, `@Operation(hidden = true)` hoặc group filters để chọn nội dung công bố.
3. Thiết kế Spring Security rules cho tất cả endpoint runtime, kể cả endpoint không xuất hiện trong tài liệu.
4. Dùng method security cho hành động nhạy cảm và policy kiểm tra quyền trên từng tài nguyên.
5. Quyết định Swagger UI và JSON/YAML docs có được bật trong từng môi trường hay không.
6. Nếu tài liệu nội bộ được bật, bảo vệ cả UI lẫn endpoint spec, bao gồm các group và định dạng YAML.
7. Rà soát schema, example, server URL, extension và metadata trước khi phát hành tài liệu public.
8. Kiểm thử request trực tiếp với người chưa xác thực, người thiếu quyền và người có quyền.
9. Kiểm tra lại sau khi đổi path, group name, context path hoặc reverse proxy.
10. Theo dõi log authorization và truy cập tài liệu, đồng thời loại bỏ token/credential khỏi log.

## 20. Nguyên tắc thiết kế

- Xem `@Hidden`, `hidden = true` và group filters là công cụ kiểm soát nội dung tài liệu.
- Không giả định operation bị ẩn thì endpoint không thể được gọi.
- Bảo vệ API runtime bằng Spring Security và kiểm tra quyền ở tầng nghiệp vụ.
- Dùng method security cho hành động nhạy cảm và object-level authorization cho dữ liệu theo người sở hữu/tenant.
- Bảo vệ Swagger UI và endpoint OpenAPI JSON/YAML như hai bề mặt riêng.
- Nếu dùng group, bảo vệ URL của từng group và định dạng YAML tương ứng.
- Tắt Swagger UI không đồng nghĩa tắt OpenAPI endpoint; tắt tài liệu không đồng nghĩa tắt API.
- Rà soát tài liệu public để tránh lộ schema, example, server URL hoặc extension nội bộ.
- Không dựa vào CORS, URL khó đoán hoặc frontend hiding làm biện pháp authorization.
- Kiểm thử bằng request HTTP trực tiếp, không chỉ kiểm tra giao diện Swagger UI.

## Kết luận

Ẩn operation bằng `@Hidden`, `@Operation(hidden = true)` hoặc bộ lọc `GroupedOpenApi` chỉ làm operation biến mất khỏi tài liệu OpenAPI tương ứng. Spring MVC vẫn giữ endpoint và client vẫn có thể gọi URL trực tiếp. Vì vậy, mọi endpoint cần được bảo vệ bằng authentication và authorization ở runtime; thao tác nhạy cảm cần kiểm tra quyền ở method và trên từng tài nguyên. Đồng thời, Swagger UI và endpoint JSON/YAML cần được bảo vệ riêng nếu tài liệu không dành cho công chúng. Hãy xem việc ẩn là quản lý phạm vi công bố tài liệu, còn Spring Security và policy nghiệp vụ là nơi thực thi quyền truy cập.
