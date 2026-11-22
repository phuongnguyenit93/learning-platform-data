# Kiểm tra từng nhóm, profile và cấu hình bảo mật tài liệu

Một ứng dụng Spring Boot có thể tạo nhiều OpenAPI document bằng `GroupedOpenApi`, bật/tắt tài liệu theo profile và bảo vệ từng URL bằng Spring Security. Các lớp cấu hình này tác động đồng thời đến việc sinh đặc tả và khả năng tải tài liệu. Vì vậy, một test chỉ gọi `/v3/api-docs` trong profile mặc định chưa đủ để chứng minh các nhóm, môi trường và chính sách truy cập đều đúng.

Kiểm thử hợp đồng cần xác nhận ba điều riêng biệt: mỗi group chứa đúng operation, profile tạo đúng cấu hình và endpoint tài liệu chỉ cho đúng người dùng truy cập. Cần kiểm tra JSON, YAML và `swagger-config` theo đúng chính sách triển khai; đồng thời phân biệt security requirement mô tả trong OpenAPI với quyền truy cập endpoint phân phối tài liệu.

## 1. Xác định ma trận group, profile và quyền truy cập

Trước khi viết test, lập ma trận hành vi mong đợi. Ví dụ ứng dụng có tài liệu public và internal:

| Profile | Group | JSON/YAML | Người ẩn danh | Người có quyền docs |
| --- | --- | --- | --- | --- |
| `local` | `public-v1` | Bật | Được tải | Được tải |
| `local` | `internal-v1` | Bật | Bị từ chối | Được tải |
| `staging` | `public-v1` | Bật | Được tải | Được tải |
| `staging` | `internal-v1` | Bật | Bị từ chối | Được tải |
| `prod` | `public-v1` | Bật theo chính sách công bố | Được tải nếu public | Được tải |
| `prod` | `internal-v1` | Bật nhưng được bảo vệ, hoặc tắt theo chính sách | Bị từ chối | Được tải nếu được giữ lại |

Đây là ma trận ví dụ; hệ thống có thể chọn chính sách khác. Điều quan trọng là ghi rõ kỳ vọng cho từng tổ hợp. Nếu production tắt hoàn toàn API docs, test cần xác nhận hành vi tắt đó thay vì cố tải tài liệu như profile staging.

Các câu hỏi cần trả lời trước khi triển khai test:

- Group id nào tồn tại trong từng profile?
- Mỗi group được phép chứa những path và HTTP method nào?
- Endpoint JSON và YAML nào được bật?
- Ai được tải từng document?
- `swagger-config` có công bố danh sách group nào và ai được đọc nó?
- Swagger UI có bật trong profile đó không?

## 2. Cấu hình hai nhóm tài liệu

Ví dụ cấu hình group theo path:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/public/**")
            .build();
    }
}
```

Với base path mặc định, các endpoint tương ứng là:

| Nội dung | URL |
| --- | --- |
| Public JSON | `/v3/api-docs/public-v1` |
| Public YAML | `/v3/api-docs/public-v1.yaml` |
| Internal JSON | `/v3/api-docs/internal-v1` |
| Internal YAML | `/v3/api-docs/internal-v1.yaml` |
| Swagger UI config | `/v3/api-docs/swagger-config` |

Nếu `springdoc.api-docs.path` đã được tùy chỉnh, thay base path trong test. Nếu ứng dụng có context path hoặc reverse proxy prefix, test nội bộ thường gọi path trong ứng dụng; smoke test sau triển khai cần gọi URL public thực tế.

`GroupedOpenApi` lọc nội dung document. Nó không tự bảo vệ endpoint JSON/YAML. Quyền truy cập được kiểm soát riêng bởi Spring Security hoặc gateway.

## 3. Bảo vệ từng group bằng Spring Security

Ví dụ chính sách: tài liệu public cho phép tải ẩn danh; tài liệu internal cần authority `docs.internal.read`; các document khác bị từ chối:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain documentationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET,
                    "/v3/api-docs/public-v1",
                    "/v3/api-docs/public-v1.yaml")
                    .permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/v3/api-docs/internal-v1",
                    "/v3/api-docs/internal-v1.yaml")
                    .hasAuthority("docs.internal.read")
                .requestMatchers(HttpMethod.GET, "/v3/api-docs/swagger-config")
                    .hasAuthority("docs.internal.read")
                .requestMatchers("/v3/api-docs/**").denyAll()
                .anyRequest().authenticated()
            )
            .httpBasic(basic -> {})
            .build();
    }
}
```

Trong ví dụ, `httpBasic` giúp minh họa một entry point trả `401` khi chưa xác thực. Ứng dụng thực tế có thể dùng session, bearer JWT hoặc gateway SSO; khi đó status cho request ẩn danh có thể khác, chẳng hạn redirect `302` đến trang đăng nhập. Hãy kiểm tra theo entry point mà ứng dụng thật cấu hình.

Rule `swagger-config` được đặt riêng vì endpoint này có thể tiết lộ URL hoặc tên các group. Nếu Swagger UI public chỉ được phép xem `public-v1`, có thể công bố một danh sách URL riêng cho UI public và dùng security matcher tương ứng. Ẩn group khỏi giao diện không thay thế việc bảo vệ URL document.

Nếu `swagger-config` cần cho UI public, hãy cấu hình nó chỉ liệt kê tài liệu public và xác nhận response không chứa group nội bộ. Trường hợp cần cả UI nội bộ và public, có thể triển khai cấu hình giao diện riêng hoặc dùng gateway/SSO; không nên mở một config chung nếu nó tiết lộ tài liệu nội bộ ngoài chính sách.

## 4. Kiểm tra chính xác tập operation của từng group

Test chỉ kiểm tra một path quan trọng có thể bỏ sót operation thừa. Để xác nhận group có đúng toàn bộ endpoint, đọc OpenAPI JSON thành `JsonNode`, lấy mọi cặp HTTP method/path rồi so sánh với allowlist.

Ví dụ helper dùng Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;

class OpenApiOperationAssertions {

    private static final Set<String> HTTP_METHODS = Set.of(
        "get", "put", "post", "delete", "patch", "options", "head", "trace"
    );

    static Set<String> operations(JsonNode document) {
        Set<String> result = new HashSet<>();
        JsonNode paths = document.path("paths");
        Iterator<String> pathNames = paths.fieldNames();

        while (pathNames.hasNext()) {
            String path = pathNames.next();
            JsonNode pathItem = paths.path(path);
            Iterator<String> keys = pathItem.fieldNames();

            while (keys.hasNext()) {
                String method = keys.next().toLowerCase(Locale.ROOT);
                if (HTTP_METHODS.contains(method)) {
                    result.add(method.toUpperCase(Locale.ROOT) + " " + path);
                }
            }
        }
        return result;
    }
}
```

Helper chỉ lấy các khóa operation HTTP; nó bỏ qua `parameters`, `servers`, `summary`, `description` và `$ref` ở Path Item. So sánh cả method lẫn path giúp phân biệt `GET /api/orders` với `POST /api/orders`.

## 5. Kiểm thử group bằng MockMvc

Với ứng dụng Spring MVC, `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` khởi tạo context gần với ứng dụng thật, bao gồm cấu hình springdoc và security:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class DocumentationGroupContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void publicGroupContainsOnlyPublicOperations() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs/public-v1"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(OpenApiOperationAssertions.operations(document))
            .containsExactlyInAnyOrder(
                "GET /api/public/catalog",
                "GET /api/public/products/{id}",
                "POST /api/public/orders"
            );
    }

    @Test
    @WithMockUser(authorities = "docs.internal.read")
    void internalGroupContainsOnlyInternalOperations() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(OpenApiOperationAssertions.operations(document))
            .containsExactlyInAnyOrder(
                "GET /api/internal/health",
                "GET /api/admin/audit-events",
                "DELETE /api/admin/orders/{id}"
            );
    }
}
```

`containsExactlyInAnyOrder` phát hiện cả endpoint thiếu lẫn endpoint thừa. Các path trong ví dụ là allowlist minh họa; thay bằng hợp đồng thực tế của ứng dụng. Nếu test profile không cần xác thực cho docs, có thể dùng security test configuration riêng, nhưng đừng vô tình vô hiệu hóa security trong test duy nhất rồi kết luận policy production đã đúng.

## 6. Kiểm thử JSON, YAML và `swagger-config`

Không chỉ kiểm tra JSON. YAML là artifact riêng có thể bị route sai hoặc bị security matcher bỏ sót:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

@Test
void publicYamlIsAvailable() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-v1.yaml"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("openapi:")))
        .andExpect(content().string(containsString("/api/public/catalog")));
}

@Test
void anonymousCannotReadInternalYaml() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
        .andExpect(status().isUnauthorized());
}
```

Test `401` giả định security entry point trả Unauthorized cho anonymous như cấu hình Basic Auth ở ví dụ trước. Nếu ứng dụng redirect đến login, đổi assertion sang hành vi thực tế hoặc cấu hình entry point thống nhất cho endpoint docs.

`swagger-config` cần được kiểm tra theo chính sách công bố. Nếu config public, xác nhận nó chỉ liệt kê group public; nếu config nội bộ, xác nhận người ẩn danh bị từ chối và người có quyền tải được. Không khẳng định mọi phiên bản springdoc luôn trả cùng cấu trúc `urls`; hãy kiểm tra JSON theo cấu hình UI đang dùng.

Ví dụ kiểm tra response config bằng Jackson:

Đây là method bổ sung cho DocumentationGroupContractTest ở mục trước; nó dùng lại mockMvc, objectMapper và các static import của lớp đó.

Test anonymous chỉ phù hợp khi rule matcher cho phép đọc swagger-config và cấu hình Swagger UI chỉ công bố group public. Cấu hình security ở ví dụ trước đang bảo vệ endpoint này bằng docs.internal.read; muốn chạy test anonymous, cần thay rule đó thành permitAll và giới hạn danh sách group được công bố.

```java
@Test
void publicSwaggerConfigDoesNotExposeInternalGroup() throws Exception {
    String body = mockMvc.perform(get("/v3/api-docs/swagger-config"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString();

    JsonNode config = objectMapper.readTree(body);
    String json = config.toString();

    assertThat(json).contains("public-v1");
    assertThat(json).doesNotContain("internal-v1");
}
```

Test này chỉ phù hợp khi chủ đích cho phép anonymous đọc `swagger-config` và cấu hình chỉ công bố `public-v1`. Nếu config được bảo vệ, thay bằng test quyền truy cập tương ứng.

## 7. Kiểm thử quyền truy cập JSON và YAML

Tách test theo vai trò giúp policy dễ đọc:

Các method dưới đây cũng được đặt trong DocumentationGroupContractTest để dùng chung mockMvc.

```java
@Test
void anonymousCanReadPublicJson() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-v1"))
        .andExpect(status().isOk());
}

@Test
void anonymousCannotReadInternalJson() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1"))
        .andExpect(status().isUnauthorized());
}

@Test
@WithMockUser
void authenticatedUserWithoutDocsAuthorityIsForbidden() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1"))
        .andExpect(status().isForbidden());
}

@Test
@WithMockUser(authorities = "docs.internal.read")
void docsReaderCanReadInternalJson() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1"))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "docs.internal.read")
void docsReaderCanReadInternalYaml() throws Exception {
    mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
        .andExpect(status().isOk());
}
```

Các test trên giả định matcher dùng `hasAuthority("docs.internal.read")`. Nếu dùng `hasRole("DOCS_READER")`, `@WithMockUser(roles = "DOCS_READER")` sẽ tạo authority `ROLE_DOCS_READER`. Tên authority trong test phải khớp cấu hình security thật.

`@WithMockUser` đặt một Authentication giả vào SecurityContext. Nó kiểm tra authorization rule nhưng không xác minh chữ ký JWT, issuer, audience, expiry hoặc mapping claim từ token thật. Nếu ứng dụng dùng OAuth2 Resource Server, bổ sung test với JWT request post-processor và integration test cho decoder/issuer theo mục tiêu kiểm thử.

## 8. Kiểm tra cấu hình theo profile

Profile có thể thay đổi trạng thái API docs, Swagger UI, group bean hoặc security policy. Dùng `@ActiveProfiles` để tạo một Spring test context với profile cụ thể:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("prod")
class ProductionDocumentationProfileTest {

    @Autowired
    Environment environment;

    @Test
    void disablesSwaggerUiButKeepsProtectedOpenApiExport() {
        assertThat(environment.getProperty(
            "springdoc.swagger-ui.enabled", Boolean.class
        )).isFalse();

        assertThat(environment.getProperty(
            "springdoc.api-docs.enabled", Boolean.class
        )).isTrue();
    }
}
```

Ví dụ giả định `application-prod.yml` tắt UI nhưng giữ OpenAPI endpoint để pipeline nội bộ export. Nếu production tắt cả hai, đổi assertion theo chính sách. Test `Environment` xác nhận giá trị được phân giải trong context; nó chưa chứng minh endpoint có thể tải qua gateway hoặc security.

Không dùng `@SpringBootTest(properties = "springdoc.swagger-ui.enabled=true")` trong test này vì thuộc tính test sẽ ghi đè giá trị profile cần kiểm tra. Chỉ thêm test property khi chủ đích kiểm tra override đó.

## 9. Kiểm tra group bean chỉ tồn tại trong profile phù hợp

Nếu một group chỉ nên được đăng ký ở staging hoặc production, có thể đặt cấu hình group dưới `@Profile`:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("staging")
class PartnerDocumentationConfiguration {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-v1")
            .pathsToMatch("/api/partner/**")
            .build();
    }
}
```

Kiểm tra bean theo profile:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("staging")
class StagingDocumentationGroupsTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersPartnerDocumentationGroup() {
        assertThat(context.getBeansOfType(GroupedOpenApi.class))
            .containsKey("partnerApi");
    }
}
```

Có thể tạo test context khác với `@ActiveProfiles("prod")` để xác nhận bean không tồn tại trong production. Mỗi test class có profile riêng; Spring TestContext sẽ quản lý context cache theo cấu hình và profile. Không cố thay active profile của một context đang chạy bằng cách sửa biến môi trường giữa các test method.

Nếu group luôn tồn tại nhưng nội dung thay đổi theo profile, kiểm tra endpoint document trong từng profile thay vì chỉ kiểm tra bean. Bean tồn tại không đảm bảo filter tạo ra đúng tập operation.

## 10. Kết hợp profile và security trong cùng ma trận test

Profile test và security test có thể tách class để mỗi test có một mục tiêu rõ ràng. Với ứng dụng có nhiều cấu hình phức tạp, tạo một số test tích hợp theo các tổ hợp quan trọng:

| Test context | Điều cần xác nhận |
| --- | --- |
| `local` + anonymous | UI/docs được bật theo chính sách phát triển; group public và internal có thể tải theo rule local. |
| `staging` + docs reader | Các group cần QA tồn tại, JSON/YAML tải được và operation set chính xác. |
| `prod` + anonymous | UI tắt; public docs chỉ tải nếu chính sách cho phép; internal docs bị từ chối. |
| `prod` + docs reader | Tài liệu nội bộ được tải nếu production giữ endpoint export; không có group ngoài allowlist. |

Không nhất thiết phải nhân toàn bộ test cho mọi tổ hợp nếu nhiều profile dùng chung cấu hình. Chọn các tổ hợp có khác biệt thực sự: profile làm thay đổi property, bean group hoặc authorization rule. Các test nhỏ cho từng trách nhiệm giúp xác định lỗi nhanh hơn một test khổng lồ kiểm tra mọi thứ cùng lúc.

## 11. Chọn MockMvc hay WebTestClient

Chọn công cụ theo web stack của ứng dụng:

| Công cụ | Phù hợp | Lưu ý |
| --- | --- | --- |
| `MockMvc` | Spring MVC/Servlet | Gửi request qua `DispatcherServlet` trong test context mà không cần server thật. |
| `WebTestClient` | Spring WebFlux | Kiểm tra reactive handler; có thể bind với application context hoặc gọi server đang chạy. |
| HTTP client như `RestClient`/`WebClient` | Smoke test sau triển khai | Kiểm tra network, reverse proxy, TLS, authentication và URL public thực tế. |

`@WebMvcTest` là test slice, thường không nạp toàn bộ auto-configuration của ứng dụng và springdoc. Nếu mục tiêu là kiểm tra endpoint `/v3/api-docs` cùng `GroupedOpenApi`, `@SpringBootTest` thường phù hợp hơn. Nếu dùng slice test, phải import cấu hình cần thiết và xác minh springdoc thực sự được khởi tạo.

Với WebFlux, có thể dùng `@SpringBootTest` cùng `WebTestClient`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveDocumentationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void internalGroupRequiresDocumentationAuthority() {
        webTestClient.get()
            .uri("/v3/api-docs/internal-v1")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Ví dụ giả định WebFlux security dùng entry point trả `401` và chưa cung cấp Authentication. Nếu ứng dụng dùng login redirect hoặc test security khác, điều chỉnh kỳ vọng. Đối với WebFlux, dùng security test support tương ứng và xác nhận group document trong cùng test context.

## 12. Dependency kiểm thử cần thiết

Thông thường `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và MockMvc test support cho ứng dụng MVC. Khi kiểm tra Spring Security bằng `@WithMockUser`, thêm `spring-security-test` nếu dependency management của dự án chưa cung cấp:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ứng dụng WebFlux dùng `WebTestClient` từ Spring test support. Chọn test support đúng stack và giữ phiên bản theo Spring Boot dependency management. Không tự thêm phiên bản Spring Security khác với phiên bản mà Spring Boot đang quản lý.

## 13. Kiểm tra nội dung bảo mật trong OpenAPI khác với bảo vệ URL docs

Có hai loại bảo mật cần test riêng:

1. **Bảo mật operation:** `components.securitySchemes` và `security` mô tả client cần cung cấp credential nào khi gọi API nghiệp vụ.
2. **Bảo mật tài liệu:** Spring Security/gateway quyết định ai được tải `/v3/api-docs/{group}`, file YAML và `swagger-config`.

Một endpoint internal có thể được mô tả trong OpenAPI với bearer requirement, nhưng điều đó không tự bảo vệ URL `/v3/api-docs/internal-v1`. Ngược lại, URL tải document có thể được bảo vệ bằng session/Basic Auth dù operation bên trong document dùng OAuth2 bearer token.

Test nên xác nhận cả hai:

- JSON document có security scheme và requirement đúng cho operation cần bảo vệ.
- Người ẩn danh không tải được document nội bộ.
- Người có authority phù hợp tải được document.
- Group public không chứa operation nội bộ hoặc security metadata sai.

## 14. Smoke test sau triển khai

Test trong Spring context không kiểm tra được toàn bộ gateway, TLS, DNS, proxy rewrite hoặc secret được cấp bởi nền tảng. Sau khi deploy staging/production, chạy smoke test từ mạng mà client hoặc pipeline thực sự sử dụng:

```bash
curl --fail --silent --show-error \
  https://api.example.com/v3/api-docs/public-v1 \
  -o public-v1.json

curl --fail --silent --show-error \
  https://api.example.com/v3/api-docs/public-v1.yaml \
  -o public-v1.yaml
```

Với group nội bộ, dùng token được cấp từ secret store của pipeline và không bật shell tracing. Kiểm tra response `401`/`403` khi không có quyền, sau đó kiểm tra `200` với service account được phép. Không ghi token ra log hoặc commit vào script.

Smoke test cũng cần kiểm tra:

- URL có đúng context path/reverse proxy prefix không.
- JSON/YAML có đúng group id và build version không.
- `servers` trong document có host/scheme/prefix public đúng không.
- `swagger-config` chỉ công bố group được phép.
- Tập operation đúng manifest đã review.
- Swagger UI được bật/tắt theo profile và tải được tài liệu mà người dùng có quyền xem.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test chỉ qua ở profile mặc định | Chưa dùng `@ActiveProfiles` hoặc file profile-specific không được nạp | Tạo test context riêng cho `local`, `staging`, `prod`. |
| Public group chứa endpoint internal | `pathsToMatch` quá rộng hoặc thiếu `pathsToExclude` | So sánh toàn bộ operation set và sửa filter. |
| Internal JSON bị chặn nhưng YAML vẫn tải được | Security matcher quên hậu tố `.yaml` | Test riêng cả hai URL và thêm matcher tương ứng. |
| Anonymous test nhận `302` thay vì `401` | Entry point chuyển hướng đến form login | Khẳng định chính sách mong muốn và điều chỉnh entry point/assertion. |
| `@WithMockUser` vẫn bị từ chối | Authority trong test không khớp `hasAuthority`/`hasRole` | Đồng bộ tên authority và role prefix. |
| Test profile báo UI tắt nhưng endpoint vẫn hoạt động | Chỉ tắt `springdoc.swagger-ui.enabled`, chưa tắt `springdoc.api-docs.enabled` | Assert hai property độc lập và kiểm tra URL thực tế. |
| Test group trả `404` | Group bean không tồn tại trong profile hoặc group id sai | Kiểm tra `GroupedOpenApi` bean và profile activation. |
| JSON test qua nhưng Swagger UI không tải được | `swagger-config`, static assets, CORS hoặc auth của browser khác | Kiểm tra từng request UI bằng Network tab. |
| `@WebMvcTest` không có `/v3/api-docs` | Slice test không nạp springdoc auto-configuration | Dùng `@SpringBootTest` hoặc import đầy đủ cấu hình cần thiết. |
| Test `@WithMockUser` qua nhưng JWT thật lỗi | Test không xác minh token decoder và claim mapping | Bổ sung JWT/resource-server integration test. |
| Test context dùng property khác production | `@SpringBootTest(properties=...)` ghi đè profile | Bỏ override không cần thiết và kiểm tra cấu hình triển khai bằng smoke test. |

## 16. Checklist triển khai test

Trước khi xem contract test là hoàn chỉnh, xác nhận:

1. Có ma trận group/profile/quyền truy cập được review.
2. Mỗi group có allowlist HTTP method và path rõ ràng.
3. Test xác nhận operation set chính xác, phát hiện cả thiếu lẫn thừa.
4. JSON và YAML được kiểm tra riêng.
5. `swagger-config` không tiết lộ group ngoài chính sách.
6. Anonymous, authenticated-without-authority và authorized user được kiểm tra.
7. Profile test dùng `@ActiveProfiles` và không bị test property ghi đè ngoài ý muốn.
8. Group bean theo profile được kiểm tra tồn tại/không tồn tại đúng môi trường.
9. Security metadata trong OpenAPI được kiểm tra riêng với security của endpoint docs.
10. Dùng MockMvc cho MVC, WebTestClient cho WebFlux và HTTP smoke test sau triển khai.
11. Token CI lấy từ secret store; Actuator và endpoint docs được bảo vệ đúng.
12. Artifact được export từ đúng instance/build và lưu theo quyền của từng nhóm.

## 17. Nguyên tắc áp dụng

- Xác định ma trận group, profile và quyền truy cập trước khi viết test.
- Dùng `@SpringBootTest` khi cần kiểm tra đầy đủ springdoc, group bean và Spring Security.
- Dùng `@ActiveProfiles` để kiểm tra cấu hình profile trong các Spring context riêng.
- So sánh toàn bộ cặp HTTP method/path của mỗi group với allowlist.
- Kiểm tra riêng JSON, YAML và `swagger-config`.
- Kiểm tra anonymous, người đăng nhập thiếu quyền và người có authority phù hợp.
- Phân biệt security requirement của operation với quyền tải OpenAPI document.
- Không dùng `@WithMockUser` như bằng chứng xác minh JWT hoặc OAuth2 token thật.
- Chọn MockMvc cho MVC, WebTestClient cho WebFlux và HTTP client cho smoke test qua gateway.
- Giữ test profile gần với chính sách thực tế; tránh override property đang cần kiểm tra.
- Kiểm tra lại URL public, artifact và quyền truy cập sau mỗi lần triển khai.

Kiểm thử từng nhóm, profile và cấu hình bảo mật giúp xác nhận tài liệu OpenAPI phản ánh đúng phạm vi API trong từng môi trường và chỉ được phân phối cho đúng đối tượng. Test group xác nhận tập operation; test profile xác nhận cấu hình được nạp; test security xác nhận ai được tải JSON, YAML và `swagger-config`. Kết hợp kiểm thử trong Spring context với smoke test sau triển khai sẽ phát hiện cả sai lệch hợp đồng lẫn vấn đề do gateway, proxy hoặc cấu hình runtime.

## Tài liệu tham khảo

- [Springdoc OpenAPI – Multiple OpenAPI Definitions và GroupedOpenApi](https://springdoc.org/faq.html)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
