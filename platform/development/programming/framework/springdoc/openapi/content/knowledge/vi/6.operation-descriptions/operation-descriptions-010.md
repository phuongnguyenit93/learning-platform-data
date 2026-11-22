# Ẩn một chi tiết tài liệu khác với vô hiệu hóa endpoint thực

Trong một ứng dụng Spring Boot, có lúc bạn muốn ẩn một endpoint nội bộ khỏi Swagger UI, không hiển thị một tham số kỹ thuật trong tài liệu hoặc bỏ một thuộc tính khỏi schema OpenAPI. springdoc-openapi hỗ trợ những thao tác này để tài liệu phù hợp với đối tượng sử dụng. Tuy nhiên, **ẩn thông tin khỏi đặc tả OpenAPI không làm thay đổi cách Spring đăng ký và xử lý endpoint**.

Một controller được đánh dấu ẩn vẫn có thể nhận request HTTP. Một thuộc tính bị ẩn trong schema vẫn có thể xuất hiện trong JSON thực tế. Một đường dẫn bị loại khỏi tài liệu vẫn có thể được gọi trực tiếp nếu ứng dụng cho phép. Muốn giới hạn quyền truy cập hoặc ngừng cung cấp endpoint, cần cấu hình bảo mật hay vòng đời bean/route ở tầng ứng dụng.

Bài học này trình bày cách ẩn operation, parameter và schema bằng annotation hoặc cấu hình springdoc-openapi; đồng thời phân biệt rõ các thao tác tài liệu với bảo mật và vô hiệu hóa endpoint trong Spring Boot.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt việc ẩn nội dung OpenAPI với việc chặn truy cập hoặc ngừng đăng ký endpoint.
- Dùng `@Hidden` và `@Operation(hidden = true)` để ẩn operation hoặc controller khỏi tài liệu.
- Ẩn parameter hay thuộc tính schema và hiểu ảnh hưởng của lựa chọn đó với người tích hợp.
- Lọc path hoặc package khỏi tài liệu mặc định và từng nhóm API.
- Tắt OpenAPI JSON/YAML hoặc Swagger UI theo môi trường.
- Dùng Spring Security, profile hoặc điều kiện cấu hình để bảo vệ hay vô hiệu hóa endpoint thực.
- Viết kiểm thử xác nhận cả tài liệu được sinh ra lẫn hành vi HTTP.

## 1. Ba lớp hành vi cần phân biệt

Khi nói một API “không hiển thị”, hãy xác định chính xác lớp nào đang được thay đổi:

| Lớp | Thay đổi | Ví dụ | Request HTTP trực tiếp |
|---|---|---|---|
| Tài liệu | Không sinh một operation, parameter hoặc schema vào OpenAPI | `@Hidden`, `@Parameter(hidden = true)` | Vẫn có thể hoạt động |
| Truy cập | Ứng dụng từ chối người gọi không đáp ứng chính sách | Spring Security yêu cầu role hoặc scope | Route vẫn tồn tại, request có thể nhận 401/403 |
| Đăng ký endpoint | Controller/handler không được đăng ký hoặc mapping bị gỡ | `@ConditionalOnProperty`, profile, bỏ mapping | Thường không còn handler và có thể nhận 404/405 |

Ba lớp này có thể được kết hợp. Chẳng hạn, endpoint quản trị có thể được ẩn khỏi tài liệu public, chỉ cho phép người có quyền ADMIN truy cập và chỉ đăng ký trong một môi trường nhất định. Mỗi lớp phục vụ một mục đích riêng nên cần được cấu hình và kiểm thử riêng.

Hãy nhớ: Swagger UI là giao diện đọc đặc tả. Nó không phải cổng kiểm soát truy cập của controller và cũng không phải nguồn xác định route nào đang hoạt động.

## 2. Ẩn toàn bộ controller bằng @Hidden

Annotation `@Hidden` của Swagger Annotations có thể đặt trên controller để springdoc-openapi bỏ các operation của controller đó khỏi tài liệu được sinh:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/diagnostics")
public class DiagnosticsController {

    @GetMapping
    public DiagnosticStatus status() {
        return diagnosticsService.currentStatus();
    }
}
~~~

Trong tài liệu OpenAPI, nhóm operation của controller này sẽ không được đưa vào danh sách path do springdoc tạo. Tuy vậy, Spring vẫn phát hiện bean controller, đăng ký mapping và gọi phương thức khi có request phù hợp. Nếu không có cơ chế bảo vệ khác, người biết URL vẫn có thể gọi endpoint.

`@Hidden` phù hợp khi controller phục vụ nội bộ, công cụ vận hành hoặc một API không dành cho người đọc tài liệu public. Trước khi ẩn, hãy xác định endpoint có thực sự cần tồn tại ở môi trường đang chạy hay không. Nếu endpoint không nên hoạt động trong production, cần thêm điều kiện đăng ký hoặc biện pháp bảo vệ phù hợp.

## 3. Ẩn một operation bằng @Hidden hoặc @Operation

Nếu chỉ một phương thức trong controller cần ẩn, đặt `@Hidden` trên phương thức:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    @GetMapping("/api/products")
    public List<ProductResponse> list() {
        return productService.findAll();
    }

    @Hidden
    @GetMapping("/internal/products/reindex")
    public ReindexResult reindex() {
        return productService.reindexSearchIndex();
    }
}
~~~

Bạn cũng có thể dùng thuộc tính `hidden` của `@Operation`:

~~~java
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Tái lập chỉ mục tìm kiếm",
    hidden = true
)
@PostMapping("/internal/products/reindex")
public ReindexResult reindex() {
    return productService.reindexSearchIndex();
}
~~~

Hai cách trên hướng đến cùng mục đích: không đưa operation đó vào đặc tả OpenAPI. Chọn một cách nhất quán trong dự án. `@Hidden` là annotation tổng quát, có thể dùng trên lớp hoặc phương thức; `@Operation(hidden = true)` đặt ý định ẩn ngay trong phần mô tả operation.

Đừng dùng việc ẩn operation để che giấu một API nhạy cảm với kỳ vọng người ngoài không thể gọi được. URL có thể bị phát hiện từ log, mã client cũ, lịch sử truy cập, proxy, tài liệu trước đây hoặc bằng cách dò route. Quyền truy cập vẫn phải được thực thi ở server.

## 4. Ẩn một parameter khỏi tài liệu

`@Parameter(hidden = true)` cho phép loại một tham số khỏi mô tả OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InternalReportController {

    @GetMapping("/internal/reports")
    public ReportResponse getReport(
        @Parameter(hidden = true)
        @RequestHeader("X-Internal-Context") String internalContext
    ) {
        return reportService.getReport(internalContext);
    }
}
~~~

Spring vẫn bind header `X-Internal-Context` vào tham số phương thức. Annotation ẩn chỉ điều khiển cách mô tả tham số trong tài liệu. Nếu server vẫn yêu cầu header đó, client phải biết cách gửi nó qua một hợp đồng khác hoặc qua tài liệu nội bộ được kiểm soát. Nếu header là thông tin xác thực, hãy xem xét mô hình security scheme thay vì coi nó là một tham số nghiệp vụ bình thường.

Ẩn một tham số bắt buộc khỏi tài liệu public có thể khiến người tích hợp không thể gọi API thành công. Chỉ làm điều này khi tham số thực sự thuộc chi tiết triển khai được cung cấp qua một kênh khác, hoặc khi endpoint không dành cho nhóm người đọc tài liệu đó. Với API public, nên mô tả đầy đủ mọi tham số mà client phải cung cấp.

### Phân biệt tham số ẩn với security scheme

Không nên ẩn header Authorization rồi yêu cầu client tự đoán cách xác thực. Hãy khai báo `securitySchemes` và `security` để Swagger UI cùng client generator biết endpoint cần bearer token, API key hay OAuth2. Security scheme mô tả cơ chế xác thực; Spring Security mới thực thi cơ chế đó.

## 5. Ẩn một thuộc tính trong schema

`@Schema(hidden = true)` có thể loại một thuộc tính khỏi schema OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record ProductResponse(
    Long id,
    String name,

    @Schema(hidden = true)
    String internalSearchKey
) {}
~~~

Thuộc tính `internalSearchKey` không được mô tả như một property thông thường trong schema do springdoc sinh. Tuy nhiên, annotation OpenAPI này không điều khiển quá trình serialize JSON của Jackson. Nếu record vẫn được trả trực tiếp và Jackson vẫn serialize thuộc tính đó, dữ liệu có thể xuất hiện trong response thật dù Swagger UI không hiển thị.

Vì vậy, trước khi ẩn một property, hãy xác định ý định:

- Nếu property vẫn được gửi qua HTTP và client cần biết nó tồn tại, hãy mô tả nó trong schema.
- Nếu property chỉ dành cho nội bộ và không được gửi cho client, dùng DTO response phù hợp hoặc cấu hình serialization như `@JsonIgnore` theo đúng yêu cầu.
- Nếu property chỉ đọc hoặc chỉ ghi, cân nhắc `@Schema(accessMode = Schema.AccessMode.READ_ONLY)` hoặc `WRITE_ONLY` thay vì ẩn hoàn toàn.

Ví dụ một trường do server tạo ra chỉ đọc đối với client:

~~~java
@Schema(accessMode = Schema.AccessMode.READ_ONLY,
        description = "Mã định danh do máy chủ cấp")
private Long id;
~~~

`READ_ONLY` cho biết trường có trong response nhưng không được gửi trong request theo hợp đồng. `WRITE_ONLY` diễn đạt chiều ngược lại. Các chế độ này giúp schema rõ hơn khi cùng một DTO hoặc schema được dùng ở nhiều chiều, nhưng DTO request và response riêng vẫn thường dễ kiểm soát hơn.

### @JsonIgnore khác @Schema(hidden = true)

| Annotation | Tác động chính | Có làm biến mất route? |
|---|---|---|
| `@Schema(hidden = true)` | Ẩn property trong đặc tả OpenAPI | Không |
| `@JsonIgnore` | Bỏ qua property theo quy tắc Jackson serialization/deserialization | Không |
| `@Schema(accessMode = READ_ONLY)` | Mô tả property chỉ xuất hiện ở chiều response | Không |
| `@Hidden` trên controller/method | Ẩn operation trong OpenAPI | Không |

Đừng dùng annotation ẩn tài liệu như biện pháp bảo vệ dữ liệu. Nếu dữ liệu không được phép gửi cho client, phải kiểm soát DTO hoặc serialization và kiểm thử body HTTP thực tế.

## 6. Ẩn schema hoặc nhóm operation khỏi tài liệu

Ngoài cách đánh dấu từng controller, method hoặc property, springdoc-openapi có thể lọc package và path. Cách này hữu ích khi một nhóm API nội bộ có quy ước package hoặc URL riêng.

Ví dụ cấu hình loại trừ trong `application.yml`:

~~~yaml
springdoc:
  packages-to-exclude:
    - com.example.application.internal
  paths-to-exclude:
    - /internal/**
    - /management/**
~~~

Các thuộc tính loại trừ giúp springdoc bỏ các controller hoặc path khớp điều kiện khỏi tài liệu được sinh. Chúng không xóa Spring bean và không gỡ request mapping. Endpoint vẫn có thể hoạt động bình thường.

Có thể kết hợp bộ lọc bao gồm và loại trừ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.application.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

Khi dùng bộ lọc, hãy kiểm tra đặc tả sau khi khởi động vì phạm vi quét phụ thuộc cấu trúc package, mapping thực tế và cấu hình của ứng dụng. Không suy luận rằng mọi path không xuất hiện trong OpenAPI đều đã bị vô hiệu hóa.

### Lọc riêng cho một GroupedOpenApi

Nếu ứng dụng chia tài liệu thành nhóm public và internal, có thể cấu hình phạm vi path cho từng nhóm:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApiGroupsConfiguration {

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
~~~

Đặc tả nhóm thường được truy cập tại `/v3/api-docs/{group}`, ví dụ `/v3/api-docs/public`. Nếu internal group chỉ dành cho đội vận hành, cần bảo vệ chính endpoint tài liệu nhóm đó bằng Spring Security hoặc cấu hình môi trường. Việc đặt tên group là internal hay không hiển thị group trên một trang Swagger UI không tự tạo quyền riêng tư.

Tên package `org.springdoc.core.models.GroupedOpenApi` áp dụng cho các phiên bản springdoc hiện đại; dự án dùng major version khác có thể có import hoặc API cấu hình khác. Hãy dùng đúng API của dependency trong dự án.

## 7. Ẩn toàn bộ OpenAPI hoặc Swagger UI

Có trường hợp không muốn cung cấp endpoint đặc tả hay giao diện Swagger UI ở một môi trường, ví dụ production. Có thể cấu hình:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

`springdoc.api-docs.enabled` điều khiển việc cung cấp endpoint đặc tả OpenAPI, thường là `/v3/api-docs` và các biến thể liên quan. `springdoc.swagger-ui.enabled` điều khiển Swagger UI. Khi tắt cả hai, các endpoint nghiệp vụ trong controller vẫn có thể hoạt động.

Có thể đặt cấu hình theo profile:

~~~yaml
# application-dev.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true

---
# application-prod.yml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Ví dụ này thể hiện ý tưởng cấu hình theo môi trường; cần bảo đảm Spring Boot kích hoạt đúng profile khi triển khai. Nếu tài liệu vẫn cần cho hệ thống CI hoặc cổng tài liệu bên ngoài, hãy cân nhắc sinh và lưu artifact OpenAPI trong pipeline build, sau đó tắt endpoint tài liệu công khai ở runtime.

Tắt Swagger UI không đồng nghĩa tắt OpenAPI JSON. Tắt OpenAPI JSON cũng không đồng nghĩa tắt endpoint ứng dụng. Hãy xác minh từng URL sau khi thay đổi cấu hình.

## 8. Bảo vệ endpoint thật bằng Spring Security

Nếu endpoint vẫn cần hoạt động nhưng chỉ một số người dùng được phép gọi, hãy dùng xác thực và phân quyền. Ví dụ Spring Security yêu cầu vai trò ADMIN cho nhóm endpoint quản trị:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/internal/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ minh họa cho ứng dụng dùng HTTP Basic; hệ thống JWT hoặc OAuth2 Resource Server cần cấu hình cơ chế xác thực tương ứng. Khi người gọi chưa xác thực, server thường trả `401`; khi đã xác thực nhưng thiếu quyền, server thường trả `403`. Quy tắc cụ thể còn phụ thuộc entry point, access denied handler và chính sách che giấu tài nguyên của ứng dụng.

Việc bảo vệ endpoint không tự động ẩn operation khỏi OpenAPI. Nếu tài liệu public không nên liệt kê endpoint quản trị, có thể kết hợp `@Hidden` hoặc bộ lọc path với Spring Security. Nếu cần cung cấp tài liệu quản trị cho người có quyền, hãy tạo nhóm tài liệu riêng và bảo vệ endpoint tài liệu đó.

Không nên chỉ dựa vào CORS, ẩn URL, tên path khó đoán hoặc việc không đưa endpoint vào Swagger UI để bảo vệ API. CORS chủ yếu là chính sách trình duyệt; nó không thay thế xác thực và phân quyền phía server.

## 9. Vô hiệu hóa endpoint thực bằng điều kiện đăng ký controller

Nếu một endpoint không nên tồn tại trong môi trường nhất định, có thể ngăn controller được tạo thành Spring bean. Một cách linh hoạt là dùng `@ConditionalOnProperty`:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/diagnostics")
@ConditionalOnProperty(
    prefix = "features.internal-diagnostics",
    name = "enabled",
    havingValue = "true"
)
public class DiagnosticsController {

    @GetMapping
    public DiagnosticStatus status() {
        return diagnosticsService.currentStatus();
    }
}
~~~

Trong cấu hình mặc định:

~~~yaml
features:
  internal-diagnostics:
    enabled: false
~~~

Với cấu hình trên, controller chỉ được đăng ký khi property có giá trị `true`. Mặc định `matchIfMissing` là `false`, nên nếu property không được khai báo thì controller cũng không được đăng ký. Khi bean không tồn tại, mapping tương ứng không được tạo và request thường nhận `404 Not Found` nếu không có handler khác cho URL đó. Khi bật property, route hoạt động trở lại và springdoc có thể phát hiện nó, trừ khi operation được ẩn riêng.

Đây là cơ chế phù hợp với endpoint công cụ chỉ dùng trong môi trường phát triển hoặc vận hành. Hãy kiểm soát property theo cấu hình triển khai và tránh bật endpoint chẩn đoán nhạy cảm ngoài ý muốn.

### Dùng @Profile cho controller theo môi trường

Một lựa chọn khác là chỉ đăng ký controller khi profile cụ thể đang hoạt động:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("internal-tools")
@RestController
@RequestMapping("/internal/tools")
public class InternalToolsController {
    // Các endpoint chỉ có trong profile internal-tools.
}
~~~

Khi profile `internal-tools` không được kích hoạt, controller không được tạo trong application context. Profile phù hợp khi phạm vi endpoint gắn với môi trường; `@ConditionalOnProperty` linh hoạt hơn khi muốn bật/tắt tính năng bằng một cờ cấu hình độc lập.

## 10. Chọn cách làm theo mục đích

| Nhu cầu | Cách phù hợp | Endpoint HTTP có còn hoạt động? |
|---|---|---|
| Ẩn một operation khỏi OpenAPI | `@Hidden` hoặc `@Operation(hidden = true)` | Có |
| Ẩn một parameter khỏi tài liệu | `@Parameter(hidden = true)` | Có |
| Ẩn một property khỏi schema | `@Schema(hidden = true)` | Có; JSON thực tế không đổi chỉ vì annotation này |
| Loại path/package khỏi tài liệu | `paths-to-exclude`, `packages-to-exclude` | Có |
| Tắt giao diện Swagger UI | `springdoc.swagger-ui.enabled=false` | Có |
| Tắt endpoint OpenAPI JSON/YAML | `springdoc.api-docs.enabled=false` | Có |
| Chỉ cho người có quyền truy cập | Spring Security | Có, nhưng request không đủ quyền bị từ chối |
| Không đăng ký controller theo cấu hình | `@ConditionalOnProperty` hoặc `@Profile` | Không có mapping khi controller không được đăng ký |
| Loại bỏ API hoàn toàn | Gỡ mapping/controller và triển khai phiên bản mới | Không còn mapping sau khi triển khai |

Hãy chọn cơ chế theo mục đích. Nếu chỉ cần tài liệu public gọn hơn, annotation hoặc bộ lọc springdoc thường là đủ. Nếu endpoint chứa thao tác nhạy cảm, cần bảo vệ bằng Spring Security. Nếu endpoint không được phép tồn tại ở production, hãy kiểm soát việc đăng ký controller hoặc loại bỏ route.

## 11. Kiểm thử để chứng minh sự khác biệt

Một bài kiểm thử hữu ích nên xác nhận đồng thời hai kết quả:

1. Operation bị ẩn không xuất hiện trong đặc tả OpenAPI.
2. Endpoint vẫn trả response nếu chỉ áp dụng cơ chế ẩn tài liệu và request đáp ứng các điều kiện truy cập.

Ví dụ với MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HiddenOperationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void hiddenOperationIsAbsentFromDocsButRouteStillWorks() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/internal/diagnostics']").doesNotExist());

        mockMvc.perform(get("/internal/diagnostics"))
            .andExpect(status().isOk());
    }
}
~~~

Test này giả định endpoint chẩn đoán không yêu cầu xác thực trong test context và response thành công. Nếu Spring Security đang bật, hãy cấu hình user/authority phù hợp hoặc dùng test security support để kiểm tra đúng chính sách.

Với controller được điều kiện hóa bằng property, hãy chạy một context test có property tắt và xác nhận mapping không tồn tại:

~~~java
@SpringBootTest(properties = "features.internal-diagnostics.enabled=false")
@AutoConfigureMockMvc
class DisabledDiagnosticsControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void disabledControllerHasNoRoute() throws Exception {
        mockMvc.perform(get("/internal/diagnostics"))
            .andExpect(status().isNotFound());
    }
}
~~~

Trong một số hệ thống, fallback route hoặc security filter có thể làm kết quả khác `404`; khi đó hãy kiểm tra application context và mapping registry để xác nhận controller có thực sự không được đăng ký. Test cũng cần chạy với cùng cấu hình profile/property như môi trường mục tiêu.

### Danh sách kiểm tra trước khi phát hành

- [ ] Xác định rõ mục tiêu là ẩn tài liệu, bảo vệ quyền truy cập hay vô hiệu hóa route.
- [ ] Operation bị ẩn không còn trong OpenAPI JSON của đúng group.
- [ ] Parameter và schema bị ẩn không làm người tích hợp thiếu thông tin bắt buộc.
- [ ] Dữ liệu nhạy cảm không xuất hiện trong JSON thực tế.
- [ ] Endpoint nhạy cảm có chính sách Spring Security phù hợp.
- [ ] Controller chỉ dành cho môi trường cụ thể được điều kiện hóa đúng.
- [ ] Swagger UI và endpoint OpenAPI được bật/tắt đúng theo môi trường.
- [ ] Kiểm thử xác nhận cả nội dung tài liệu lẫn hành vi HTTP.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đã dùng `@Hidden` nhưng gọi URL vẫn được | Annotation chỉ ảnh hưởng OpenAPI | Thêm Spring Security hoặc ngừng đăng ký controller |
| Endpoint biến mất khỏi Swagger UI nhưng vẫn có trong group khác | Bộ lọc chỉ áp dụng cho một tài liệu/nhóm | Kiểm tra từng endpoint `/v3/api-docs/{group}` |
| Property ẩn trong schema nhưng vẫn có trong JSON | `@Schema(hidden = true)` không điều khiển Jackson | Dùng DTO phù hợp hoặc cấu hình serialization |
| Header bắt buộc bị ẩn khiến client không gọi được | Tài liệu thiếu thông tin cần thiết | Công bố cơ chế hợp lệ hoặc thiết kế lại hợp đồng |
| Tắt Swagger UI nhưng `/v3/api-docs` vẫn truy cập được | Chỉ tắt giao diện | Tắt thêm `springdoc.api-docs.enabled` nếu cần |
| Tắt OpenAPI nhưng controller vẫn hoạt động | Endpoint nghiệp vụ độc lập với endpoint tài liệu | Đây là hành vi bình thường; dùng bảo mật hoặc điều kiện bean nếu cần |
| Controller được bật ngoài ý muốn | Property hoặc profile triển khai không đúng | Kiểm tra cấu hình hiệu lực và kiểm thử startup |

Một nguyên tắc quan trọng: đừng xác nhận endpoint đã vô hiệu hóa chỉ bằng cách nhìn Swagger UI. Hãy gửi request HTTP hoặc kiểm tra mapping trong application context.

## 13. Bài thực hành

Tạo một controller có hai operation: endpoint public lấy danh sách sản phẩm và endpoint nội bộ kích hoạt tái lập chỉ mục tìm kiếm. Thực hiện:

1. Dùng `@Hidden` để ẩn controller hoặc operation nội bộ khỏi OpenAPI.
2. Kiểm tra operation public vẫn xuất hiện trong `/v3/api-docs`.
3. Gọi URL nội bộ trực tiếp để chứng minh route vẫn hoạt động khi chỉ ẩn tài liệu.
4. Thêm Spring Security để chỉ ADMIN được gọi endpoint nội bộ.
5. Kiểm tra request không xác thực và request thiếu quyền nhận status phù hợp.
6. Chuyển controller nội bộ sang `@ConditionalOnProperty` và tắt property trong cấu hình production.
7. Khởi động ứng dụng với property tắt, xác nhận mapping nội bộ không còn.
8. Dùng `@Parameter(hidden = true)` cho một tham số kỹ thuật và đánh giá liệu client có còn đủ thông tin gọi API.
9. Dùng `@Schema(hidden = true)` cho một property thử nghiệm; so sánh schema OpenAPI với JSON thực tế.
10. Chọn DTO hoặc Jackson annotation phù hợp nếu property không được phép xuất hiện trong response.

### Tiêu chí hoàn thành

- [ ] Phân biệt chính xác ba lớp: tài liệu, truy cập và đăng ký endpoint.
- [ ] Ẩn operation bằng annotation và xác nhận nó không xuất hiện trong OpenAPI.
- [ ] Chứng minh request HTTP vẫn có thể gọi operation nếu route còn tồn tại và được phép truy cập.
- [ ] Bảo vệ endpoint nội bộ bằng Spring Security.
- [ ] Vô hiệu hóa controller bằng property hoặc profile và xác nhận route không còn.
- [ ] Phân biệt `@Schema(hidden = true)` với `@JsonIgnore` bằng cách kiểm tra response thực tế.
- [ ] Tắt Swagger UI và OpenAPI JSON/YAML độc lập theo cấu hình môi trường.

## Tiếp tục học

Sau bài này, hãy kết hợp ẩn operation với GroupedOpenApi, security requirement và cấu hình theo môi trường. Khi thiết kế tài liệu public/internal, hãy kiểm tra đồng thời OpenAPI JSON, Swagger UI, Spring Security và mapping thực tế. Chỉ khi bốn góc nhìn nhất quán, nhóm phát triển mới biết rõ API nào được công bố, ai được phép gọi và endpoint nào thực sự tồn tại trong môi trường triển khai.
