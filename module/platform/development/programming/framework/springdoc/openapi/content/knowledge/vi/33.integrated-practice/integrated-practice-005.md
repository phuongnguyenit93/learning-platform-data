# Phân nhóm API công khai, nội bộ và quản trị

Một ứng dụng Spring Boot có thể phục vụ nhiều nhóm người dùng: khách hàng bên ngoài, service nội bộ và nhân viên quản trị. Mỗi nhóm chỉ nên nhìn thấy các operation cần thiết. Springdoc-openapi hỗ trợ tạo tài liệu riêng cho từng nhóm bằng GroupedOpenApi; Spring Security bảo vệ tài liệu và endpoint theo quyền truy cập.

Bài thực hành xây dựng ba nhóm:

- **Public API**: operation công khai để khách hàng hoặc đối tác tích hợp.
- **Internal API**: operation dành cho service-to-service.
- **Admin API**: operation quản trị cần quyền của nhân viên quản trị.

Kết quả mong muốn là mỗi nhóm có OpenAPI document riêng, Swagger UI có thể liệt kê các document, và quyền tải tài liệu khớp với chính sách bảo mật của API runtime.

## 1. Thiết kế ranh giới API trước khi cấu hình

Giả sử một Catalog application có các endpoint:

| Nhóm | Path | Người dùng |
|---|---|---|
| Public | /api/public/products/** | Khách hàng và đối tác. |
| Internal | /api/internal/inventory/** | Service nội bộ có scope phù hợp. |
| Admin | /api/admin/products/** | Nhân viên có quyền quản trị. |

Các endpoint cần được đặt path có quy ước nhất quán. Nhờ đó, Springdoc có thể chọn operation theo path và Spring Security có thể áp dụng authorization theo cùng ranh giới.

Ví dụ controller skeleton:

~~~java
@RestController
@RequestMapping("/api/public/products")
class PublicProductController {

    @GetMapping
    List<ProductSummary> listProducts() {
        // Trả dữ liệu được phép công bố.
        return List.of();
    }
}

@RestController
@RequestMapping("/api/internal/inventory")
class InternalInventoryController {

    @PostMapping("/reservations")
    ReservationResponse reserve(@RequestBody ReservationRequest request) {
        // Được gọi bởi service nội bộ.
        return new ReservationResponse();
    }
}

@RestController
@RequestMapping("/api/admin/products")
class AdminProductController {

    @PostMapping
    ProductResponse create(@RequestBody CreateProductRequest request) {
        // Thao tác quản trị.
        return new ProductResponse();
    }
}
~~~

Đây là ví dụ về cách phân tách path. Trong ứng dụng thật, controller cần gọi service và trả DTO tương ứng; không trả entity persistence trực tiếp chỉ vì endpoint nằm trong một group riêng.

## 2. Tạo ba OpenAPI group

Dùng GroupedOpenApi để mỗi nhóm sinh một tài liệu độc lập:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiDocumentationGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/public/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/api/internal/**")
                .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
                .group("admin")
                .pathsToMatch("/api/admin/**")
                .build();
    }
}
~~~

Ứng dụng sẽ cung cấp ba OpenAPI document:

| Group | URL |
|---|---|
| public | /v3/api-docs/public |
| internal | /v3/api-docs/internal |
| admin | /v3/api-docs/admin |

Mỗi group cũng có thể được tải ở dạng YAML bằng cách thêm hậu tố .yaml, ví dụ /v3/api-docs/admin.yaml. Nếu phát hành cả JSON và YAML, phải bảo vệ cả hai URL bằng cùng chính sách.

Mỗi group chỉ chứa operation khớp path filter của nó. Nếu một path khớp nhiều group, operation có thể xuất hiện trong nhiều tài liệu. Vì vậy, review các pattern để tránh vô tình đưa endpoint nội bộ vào tài liệu public.

### 2.1. Tắt document mặc định không phân nhóm

Springdoc có thể tạo document mặc định tại /v3/api-docs bên cạnh các group. Document mặc định có thể bao gồm tất cả controller được phát hiện. Nếu mục tiêu là chỉ công bố ba tài liệu đã phân nhóm, tắt document mặc định:

~~~yaml
springdoc:
  enable-default-api-docs: false
~~~

Sau khi tắt, kiểm tra các URL group vẫn hoạt động. Không dựa vào việc Swagger UI chỉ hiển thị một group để bảo đảm các operation khác không xuất hiện ở document mặc định.

## 3. Liệt kê các group trong Swagger UI

Một Swagger UI có thể cho người xem chọn giữa các OpenAPI document:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Internal API
        url: /v3/api-docs/internal
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
    doc-expansion: none
    operations-sorter: alpha
    tags-sorter: alpha
~~~

Khi mở /docs, người dùng có thể chọn tài liệu theo group. urls-primary-name chọn document mặc định. Đây chỉ là danh sách tài liệu mà UI có thể tải; nó không gộp paths và không bảo vệ endpoint.

### 3.1. Chọn audience cho Swagger UI

Ví dụ trên phù hợp với một developer portal nội bộ dành cho người có quyền xem tài liệu. Không nên công khai một Swagger UI có dropdown chứa cả Internal API và Admin API cho khách hàng bên ngoài.

Có hai cách triển khai:

1. **Internal documentation portal**: bảo vệ toàn bộ Swagger UI, swagger-config và các group docs; portal liệt kê cả public, internal và admin.
2. **Public documentation portal riêng**: chỉ cấu hình UI với URL /v3/api-docs/public; không đưa internal/admin URL vào config của portal public.

Nếu chỉ cần cung cấp public contract cho đối tác, họ có thể tải trực tiếp /v3/api-docs/public hoặc dùng một UI public chỉ chứa tài liệu đó. Tài liệu nội bộ được cung cấp qua portal hoặc pipeline riêng.

## 4. Bảo vệ tài liệu theo từng audience

Group filter không phải security boundary. Bất kỳ ai truy cập được URL document đều có thể đọc operation, schema, parameter và security metadata trong đó. Hãy áp dụng authorization cho cả tài liệu và API runtime.

Chính sách mẫu:

| Tài nguyên | Quyền |
|---|---|
| /v3/api-docs/public | Public |
| /v3/api-docs/internal | Authority SCOPE_internal.docs |
| /v3/api-docs/admin | Role DOCS_ADMIN |
| /docs, /swagger-ui.html, /swagger-ui/** | Role DOCS_VIEWER |
| /v3/api-docs/swagger-config | Role DOCS_VIEWER |
| /api/public/** | Public |
| /api/internal/** | Authority SCOPE_internal |
| /api/admin/** | Role ADMIN |

Ví dụ SecurityFilterChain với Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/v3/api-docs/swagger-config")
                            .hasRole("DOCS_VIEWER")
                        .requestMatchers(
                                "/v3/api-docs/public",
                                "/v3/api-docs/public.yaml"
                        )
                            .permitAll()
                        .requestMatchers(
                                "/v3/api-docs/internal",
                                "/v3/api-docs/internal.yaml"
                        )
                            .hasAuthority("SCOPE_internal.docs")
                        .requestMatchers(
                                "/v3/api-docs/admin",
                                "/v3/api-docs/admin.yaml"
                        )
                            .hasRole("DOCS_ADMIN")
                        .requestMatchers("/v3/api-docs/**")
                            .denyAll()
                        .requestMatchers(
                                "/docs",
                                "/swagger-ui.html",
                                "/swagger-ui/**"
                        ).hasRole("DOCS_VIEWER")
                        .requestMatchers("/api/public/**")
                            .permitAll()
                        .requestMatchers("/api/internal/**")
                            .hasAuthority("SCOPE_internal")
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .anyRequest()
                            .authenticated()
                )
                .build();
    }
}
~~~

Đây là phần authorization rule; ứng dụng vẫn cần cấu hình authentication phù hợp như OAuth2 Resource Server, JWT, session hoặc cơ chế đăng nhập đã chọn. Thứ tự matcher rất quan trọng: các group docs và swagger-config được khai báo trước matcher tổng quát /v3/api-docs/**.

### 4.1. Tách quyền xem tài liệu khỏi quyền thao tác API

DOCS_VIEWER cho phép mở developer portal; DOCS_ADMIN cho phép tải tài liệu quản trị; ADMIN cho phép gọi thao tác quản trị. Các quyền này có thể được cấp cho nhóm người khác nhau.

Không nên cấp quyền ADMIN chỉ để một developer xem tài liệu. Ngược lại, có quyền DOCS_ADMIN không có nghĩa người dùng được tạo hoặc xóa sản phẩm.

### 4.2. Không để document mặc định làm lộ các group

Nếu đã tắt enable-default-api-docs, route /v3/api-docs mặc định không còn được công bố. Nếu giữ document mặc định, phải bảo vệ nó bằng authorization đủ chặt vì nó có thể tổng hợp các operation public, internal và admin.

Không chỉ bảo vệ Swagger UI. Người dùng có thể gọi trực tiếp /v3/api-docs/{group} bằng curl hoặc HTTP client.

## 5. Mô tả security trong OpenAPI

SecurityFilterChain enforce quyền ở runtime. OpenAPI security scheme mô tả cơ chế xác thực để client hiểu cách gọi API.

Ví dụ khai báo Bearer scheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition
@SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
)
class OpenApiSecuritySchemeConfiguration {
}
~~~

Controller nội bộ hoặc quản trị có thể tham chiếu scheme:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@Operation(
        summary = "Tạo sản phẩm",
        security = @SecurityRequirement(name = "bearerAuth")
)
~~~

HTTP Bearer scheme mô tả token được gửi trong Authorization header. Nếu API dùng OAuth2 scopes và cần mô tả scope, khai báo OAuth2 SecurityScheme với flow/scopes tương ứng. Role hoặc authority cụ thể vẫn cần được enforce bằng Spring Security.

## 6. Kiểm thử nội dung từng group

Dùng MockMvc để xác minh document chỉ chứa operation thuộc audience:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiDocumentationGroupsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicDocumentContainsOnlyPublicPaths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/public/products']").exists())
                .andExpect(jsonPath("$.paths['/api/internal/inventory/reservations']").doesNotExist())
                .andExpect(jsonPath("$.paths['/api/admin/products']").doesNotExist());
    }
}
~~~

Test này kiểm tra nội dung tài liệu. Cần thêm security tests để xác minh người dùng không đủ quyền không thể tải internal/admin document.

## 7. Kiểm thử quyền truy cập tài liệu

Ví dụ với user chỉ có DOCS_VIEWER:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiDocumentationAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void docsViewerCannotReadAdminDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin")
                        .with(user("reader").roles("DOCS_VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void docsAdminCanReadAdminDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs/admin")
                        .with(user("docs-admin")
                                .roles("DOCS_VIEWER", "DOCS_ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

Nếu ứng dụng dùng JWT scopes cho internal API, dùng JWT test postprocessor và cấp authority SCOPE_internal.docs. Không thay bằng user role nếu SecurityFilterChain yêu cầu authority scope.

### 7.1. Kiểm tra public/internal/admin API runtime

Ngoài tài liệu, cần test endpoint thật:

- Public endpoint truy cập được theo chính sách public.
- Internal endpoint từ chối request không có SCOPE_internal.
- Admin endpoint từ chối user không có ADMIN.
- User có DOCS_ADMIN nhưng không có ADMIN không được phép gọi thao tác quản trị.

Các test này chứng minh quyền truy cập API runtime được enforce độc lập với tài liệu.

## 8. Kiểm tra Swagger UI config

Khi Swagger UI liệt kê ba group, endpoint swagger-config cần chứa đúng URL:

~~~bash
curl -fsS -u docs-viewer:password \
  http://localhost:8080/v3/api-docs/swagger-config
~~~

Kiểm tra:

- urls có đúng public, internal và admin document.
- urlsPrimaryName trỏ tới entry mong muốn.
- Tài liệu internal/admin vẫn yêu cầu credential khi được tải.
- Public document không chứa path nội bộ.

Không ghi credential thật vào script hoặc log CI. Dùng test identity và secret quản lý bởi pipeline.

Nếu cần public Swagger UI, tạo cấu hình UI riêng chỉ chứa /v3/api-docs/public. Không tái sử dụng danh sách URL nội bộ cho trang public.

## 9. Kiểm tra document mặc định và group endpoint

Với springdoc.enable-default-api-docs=false:

- Các endpoint group vẫn phải được kiểm tra riêng.
- Default ungrouped document không được công bố.
- swagger-config vẫn cần trỏ tới các group document.

Nếu không tắt document mặc định, thêm test xác nhận nó được bảo vệ bằng role phù hợp và không bị public.

Không dựa vào UI dropdown để xác nhận group đã bị ẩn. Luôn gọi trực tiếp các URL OpenAPI document trong test.

## 10. Các lỗi thường gặp

- **Chỉ dùng GroupedOpenApi mà không cấu hình Security**: group không bảo vệ document hoặc endpoint runtime.
- **Để default /v3/api-docs công khai**: document tổng hợp có thể chứa internal/admin operations.
- **Đưa internal/admin URL vào public Swagger UI**: tên group và đường dẫn có thể bị lộ; endpoint vẫn cần được bảo vệ.
- **Bảo vệ UI nhưng bỏ quên JSON endpoint**: client có thể gọi trực tiếp /v3/api-docs/{group}.
- **Dùng DOCS_ADMIN như quyền ADMIN**: quyền đọc tài liệu không nên tự động cho phép thao tác quản trị.
- **Dùng paths-to-match quá rộng**: operation nội bộ có thể lọt vào public group.
- **Để path overlap giữa các group**: một operation có thể xuất hiện trong nhiều document.
- **Chỉ test tài liệu, không test endpoint**: tài liệu đúng không chứng minh authorization runtime đúng.
- **Mô tả Bearer scheme nhưng không enforce Spring Security**: OpenAPI security requirement chỉ là hợp đồng, không phải bộ lọc request.
- **Bảo vệ swagger-config nhưng không bảo vệ Swagger UI assets**: người dùng có thể tải trang nhưng không tải được cấu hình hoặc ngược lại.
- **Dùng một Swagger UI public cho tất cả audience**: cấu hình urls là tĩnh, không tự lọc document theo người dùng.

## 11. Quy trình triển khai cho ba audience

1. **Thiết kế path convention**: public, internal và admin có prefix rõ ràng.
2. **Tạo group**: mỗi audience có một GroupedOpenApi và group name riêng.
3. **Tắt default document nếu không cần**: tránh endpoint tổng hợp làm lộ operation.
4. **Tạo Swagger UI config**: chỉ liệt kê các document phù hợp với portal.
5. **Mô tả security**: thêm security scheme và requirement cho operation cần token.
6. **Bảo vệ document endpoints**: public permitAll, internal theo scope, admin theo role.
7. **Bảo vệ API runtime**: áp dụng authorization độc lập cho controller.
8. **Test nội dung group**: xác nhận mỗi document chỉ chứa paths được phép.
9. **Test quyền truy cập**: user không đủ quyền không tải được document hoặc gọi API.
10. **Kiểm tra browser portal**: Swagger UI tải đúng config và group document.
11. **Review deployment**: bảo đảm reverse proxy, CORS và network policy không mở đường truy cập ngoài dự kiến.

## 12. Checklist review

- [ ] Public, internal và admin có path convention rõ ràng.
- [ ] Mỗi group có tên duy nhất.
- [ ] Path filters không chồng lấn ngoài chủ đích.
- [ ] Public document không chứa internal/admin operation.
- [ ] Default document được tắt hoặc bảo vệ.
- [ ] Swagger UI urls được cấu hình theo audience.
- [ ] Swagger UI config endpoint được bảo vệ phù hợp.
- [ ] Internal document yêu cầu scope/authority phù hợp.
- [ ] Admin document yêu cầu role tài liệu quản trị.
- [ ] API runtime có authorization riêng.
- [ ] OpenAPI security schemes mô tả đúng cách gửi credential.
- [ ] Có test nội dung từng group.
- [ ] Có test quyền tải document và gọi endpoint.
- [ ] Browser portal tải đúng document và static resources.
- [ ] Reverse proxy/CORS/network policy giữ đúng ranh giới truy cập.

## 13. Tài liệu tham khảo

- [springdoc-openapi – Multiple OpenAPI definitions and GroupedOpenApi](https://springdoc.org/index.html#how-can-i-define-multiple-openapi-definitions-in-one-spring-boot-project)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Security support](https://springdoc.org/#how-can-i-add-authorization-header-in-requests)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)

GroupedOpenApi chia document theo audience; Spring Security kiểm soát ai được tải document và gọi endpoint; Swagger UI chỉ là giao diện tiêu thụ các document đó. Hãy giữ ba lớp tách biệt, tắt hoặc bảo vệ document mặc định, rồi kiểm thử cả nội dung từng group lẫn quyền truy cập runtime. Khi public, internal và admin được phân nhóm và bảo vệ nhất quán, đội phát triển có thể phân phối tài liệu đúng người mà không làm lộ operation nội bộ.
