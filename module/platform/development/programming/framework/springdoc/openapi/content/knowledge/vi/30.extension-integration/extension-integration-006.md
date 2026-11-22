# Điều kiện phụ thuộc và cơ chế bật tường minh của tích hợp MCP

Springdoc-openapi có thể chuyển các operation REST đã được mô tả trong OpenAPI thành MCP tools để AI agent khám phá và gọi. Tuy nhiên, việc thêm dependency MCP vào classpath không đồng nghĩa endpoint MCP được công bố ngay. Tích hợp này dùng cơ chế opt-in: ứng dụng phải bật property `springdoc.ai.mcp.enabled=true`.

Điều kiện này giúp tách riêng ba quyết định: thư viện MCP có mặt trong dependency graph, ứng dụng có chủ động bật MCP hay không, và dashboard quản trị có được mở hay không. Hiểu đúng từng điều kiện giúp tránh vô tình mở thêm bề mặt tích hợp, đồng thời giúp kiểm tra vì sao một bean hoặc endpoint không được đăng ký.

Bài học tập trung vào dependency đúng theo WebMVC/WebFlux, property bật MCP, điều kiện auto-configuration, profile theo môi trường, dashboard, security, kiểm thử trạng thái bật/tắt và chẩn đoán condition report.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt sự hiện diện của MCP starter với việc MCP integration được bật.
- Chọn đúng starter cho Spring MVC hoặc Spring WebFlux.
- Cấu hình `springdoc.ai.mcp.enabled` một cách tường minh.
- Hiểu giá trị mặc định `false` từ Springdoc 3.1.1.
- Tách điều kiện bật MCP server khỏi điều kiện bật Developer Dashboard.
- Dùng profile và environment variable để bật tích hợp theo môi trường.
- Hiểu vai trò của `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean`.
- Kiểm tra startup preloading và timeout khi MCP được bật.
- Bảo vệ các endpoint MCP bằng Spring Security.
- Kiểm thử các trường hợp dependency thiếu, property thiếu, `false` và `true`.
- Chẩn đoán auto-configuration bằng `--debug` và Actuator conditions.

## 1. MCP integration của Springdoc làm gì?

Springdoc MCP integration kết nối OpenAPI với Model Context Protocol. Nó đọc các operation đã được mô tả từ `@RestController`, chuyển metadata OpenAPI thành tool definitions và cung cấp MCP endpoint để client tương thích khám phá, gọi công cụ.

Thông tin từ OpenAPI được dùng để tạo tool:

- `operationId` trở thành tên tool mặc định, được chuẩn hóa để phù hợp với tên tool.
- `summary` và `description` cung cấp nội dung giải thích cho AI agent.
- Parameters và request body được chuyển thành JSON Schema đầu vào.
- Tag đầu tiên của controller được dùng để nhóm tool trong dashboard.
- `@McpToolDescription` có thể cung cấp mô tả tối ưu riêng cho agent.

Tích hợp này sử dụng các endpoint REST đã có trong ứng dụng. Bật MCP không tạo ra nghiệp vụ mới trong controller; nó tạo một giao diện để MCP client khám phá và gọi những operation được đưa vào tool registry.

## 2. Chọn dependency theo web stack

Springdoc cung cấp starter riêng cho Spring MVC và Spring WebFlux. Chỉ thêm starter phù hợp với web stack của ứng dụng.

### 2.1. Spring MVC / Servlet

Với ứng dụng dùng `spring-boot-starter-web`, thêm:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
    <version>SPRINGDOC_VERSION</version>
</dependency>
~~~

### 2.2. Spring WebFlux / Reactive

Với ứng dụng dùng `spring-boot-starter-webflux`, thêm:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-mcp</artifactId>
    <version>SPRINGDOC_VERSION</version>
</dependency>
~~~

`SPRINGDOC_VERSION` là placeholder trong ví dụ Maven; thay bằng version do dự án quản lý hoặc dùng Springdoc BOM nếu dự án đã import BOM.

Không thêm cả hai starter chỉ để thử. Chọn module theo runtime web thực tế, tránh đưa đồng thời Servlet và Reactive integration vào cùng một ứng dụng nếu kiến trúc không yêu cầu.

### 2.3. Kiểm tra tương thích Spring Boot

MCP starter được giới thiệu trong dòng Springdoc 3.x. Tài liệu hiện hành của Springdoc 3.2.0 trình bày starter cho Spring Boot 4. Nếu ứng dụng đang dùng Spring Boot 3 với Springdoc 2.x, không nâng riêng MCP starter lên 3.x để lấy tính năng này; major Springdoc và major Spring Boot phải tương thích theo compatibility matrix.

Trước khi thêm dependency, kiểm tra:

- Phiên bản Spring Boot và Spring Framework đang dùng.
- Phiên bản Springdoc được hỗ trợ cho Spring Boot đó.
- Starter tương ứng với WebMVC hoặc WebFlux.
- Spring AI/MCP dependency được resolve từ dependency management của starter.

Không tự ép một phiên bản Spring AI hoặc Springdoc khác major vào classpath nếu chưa kiểm tra dependency tree.

## 3. Dependency có mặt không đồng nghĩa MCP đã bật

Từ Springdoc 3.1.1, MCP integration là opt-in. Property `springdoc.ai.mcp.enabled` có giá trị mặc định `false`. Khi chỉ thêm starter mà không bật property:

- MCP tool integration không được đăng ký.
- MCP endpoint mặc định `/mcp` không được mở.
- Dashboard MCP không được tạo.
- Các REST endpoint và tài liệu OpenAPI hiện tại vẫn hoạt động theo cấu hình riêng.

Bật integration trong `application.yml`:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

Hoặc trong `application.properties`:

~~~properties
springdoc.ai.mcp.enabled=true
~~~

Khi property là `true`, Springdoc tạo tool registry từ OpenAPI và đăng ký MCP surface theo module web tương ứng. Nếu property không tồn tại hoặc bằng `false`, MCP integration không được đăng ký.

Đây là điểm khác biệt quan trọng giữa:

| Điều kiện | Ý nghĩa |
|---|---|
| MCP starter có trong dependency graph | Các class và auto-configuration MCP có thể được nạp |
| `springdoc.ai.mcp.enabled=true` | Ứng dụng cho phép Springdoc đăng ký MCP integration |
| `springdoc.ai.mcp.dashboard-enabled=true` | Ứng dụng bật thêm Developer Dashboard |

## 4. Hiểu các điều kiện auto-configuration

Spring Boot auto-configuration sử dụng các điều kiện để quyết định bean nào được đăng ký. MCP integration cần có các lớp phù hợp trong classpath và property bật tính năng.

### 4.1. Điều kiện classpath

`@ConditionalOnClass` kiểm tra một class có tồn tại trên classpath hay không. Đây là cách thư viện giữ cho integration tùy chọn: nếu ứng dụng không có module MCP, cấu hình phụ thuộc MCP không nên được nạp.

Ví dụ tổng quát:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(OptionalMcpApi.class)
class OptionalMcpConfiguration {
    // Beans chỉ hợp lệ khi API tùy chọn có trên classpath
}
~~~

`OptionalMcpApi` là tên minh họa cho class thuộc integration tùy chọn. Khi viết auto-configuration của riêng mình, có thể dùng `name = "fully.qualified.OptionalMcpApi"` để tránh JVM phải nạp trực tiếp type tùy chọn trong một số cấu trúc cấu hình.

### 4.2. Điều kiện property

`@ConditionalOnProperty` kiểm tra giá trị trong Spring `Environment`. Với một extension chỉ chạy khi MCP được bật, có thể viết:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "springdoc.ai.mcp",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class MyMcpExtensionConfiguration {

    @Bean
    PropertyConditionMarker propertyConditionMarker() {
        return new PropertyConditionMarker();
    }
}

record PropertyConditionMarker() {
}
~~~

`matchIfMissing = false` làm rõ rằng property thiếu thì extension không được đăng ký. Đây cũng là hành vi mặc định của `@ConditionalOnProperty`, nhưng khai báo tường minh giúp người đọc thấy đây là opt-in feature.

### 4.3. Điều kiện bean

`@ConditionalOnBean` và `@ConditionalOnMissingBean` kiểm tra bean đã được đăng ký trong context. Chúng thường dùng để cho phép ứng dụng thay thế bean mặc định bằng bean tùy chỉnh.

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean
MyMcpExtensionMarker myMcpExtensionMarker() {
    return new MyMcpExtensionMarker();
}
~~~

Đặt bean condition trên auto-configuration được nạp sau bean do người dùng khai báo. Thứ tự đăng ký bean definitions có thể ảnh hưởng kết quả điều kiện.

Không nhầm `@ConditionalOnMissingBean` với cơ chế bật MCP. Nó chỉ quyết định có tạo bean mặc định hay không; property `springdoc.ai.mcp.enabled` mới là lựa chọn bật/tắt MCP integration của Springdoc.

## 5. Bật MCP theo profile

Không phải môi trường nào cũng nên mở MCP. Có thể để mặc định tắt và chỉ bật ở profile dành cho môi trường cần AI agent.

`application.yml`:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: false
~~~

`application-mcp.yml`:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
~~~

Chạy với profile:

~~~bash
SPRING_PROFILES_ACTIVE=mcp java -jar app.jar
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "mcp"
java -jar app.jar
~~~

Spring Boot sẽ nạp `application-mcp.yml` khi profile `mcp` được kích hoạt. Trong môi trường container, có thể đặt environment variable trực tiếp:

~~~text
SPRINGDOC_AI_MCP_ENABLED=true
~~~

Quyết định bật MCP nên nằm trong cấu hình triển khai có kiểm soát. Không bật trong mọi môi trường chỉ vì dependency đã có trong image.

## 6. Bật dashboard độc lập với MCP server

MCP server và Developer Dashboard là hai phần riêng. Khi MCP integration được bật, dashboard vẫn mặc định tắt. Muốn bật giao diện quản trị, cấu hình:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
      dashboard-path: /mcp-ui
~~~

Các endpoint mặc định:

| Thành phần | Path mặc định |
|---|---|
| MCP server | `/mcp` |
| Developer Dashboard | `/mcp-ui` |
| Dashboard REST API | `/api/mcp-admin/**` |

Nếu chỉ cần MCP client kết nối từ xa, không nhất thiết bật dashboard. Nếu bật dashboard, hãy bảo vệ cả trang giao diện và REST API của nó.

Có thể đổi MCP endpoint bằng `springdoc.ai.mcp.mcp-endpoint` và dashboard path bằng `springdoc.ai.mcp.dashboard-path`. Khi thay đổi, cập nhật cấu hình MCP client và security matcher cùng lúc.

## 7. Preloading và điều kiện khởi tạo lúc startup

MCP tool registry được xây dựng từ OpenAPI specification. Vì vậy, khi MCP được bật, Springdoc tự động ép `springdoc.pre-loading-enabled=true` để tài liệu OpenAPI sẵn sàng lúc khởi động.

Một số property liên quan:

| Property | Mặc định | Vai trò |
|---|---:|---|
| `springdoc.ai.mcp.enabled` | `false` | Bật MCP integration |
| `springdoc.ai.mcp.init-timeout-seconds` | `30` | Thời gian chờ OpenAPI spec khi khởi tạo |
| `springdoc.ai.mcp.base-url` | `http://localhost:8080` | Base URL dùng cho HTTP call thực thi tool |
| `springdoc.ai.mcp.mcp-endpoint` | `/mcp` | Đường dẫn MCP server |
| `springdoc.ai.mcp.paths-to-exclude` | rỗng | Path pattern loại khỏi tool generation |
| `springdoc.ai.mcp.dashboard-enabled` | `false` | Bật dashboard |

Nếu ứng dụng có nhiều controller, customizer hoặc OpenAPI generation chậm, startup có thể tăng khi bật MCP do tài liệu cần được tạo sớm. Theo dõi thời gian startup và điều chỉnh `init-timeout-seconds` khi có căn cứ từ môi trường thực tế.

`springdoc.ai.mcp.base-url` là địa chỉ dùng khi MCP tool gọi lại REST API. Nếu ứng dụng chạy sau reverse proxy hoặc trong container, hãy xác định địa chỉ mà tiến trình MCP có thể truy cập; không mặc định dùng public URL nếu internal service URL phù hợp hơn.

## 8. Loại path khỏi MCP tool generation

Không phải mọi REST operation đều phù hợp để đưa cho AI agent. Có thể dùng:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      paths-to-exclude:
        - /internal/**
        - /admin/**
        - /actuator/**
~~~

`paths-to-exclude` dùng ant-style path patterns và chỉ lọc các operation khỏi MCP tool generation. Nó không xóa endpoint khỏi OpenAPI mặc định, không chặn HTTP request và không thay thế Spring Security hoặc gateway policy.

Nếu một path bị loại khỏi MCP, người dùng vẫn có thể gọi route đó qua REST nếu route được expose và caller có quyền. Hãy quản lý quyền ở tầng API riêng.

## 9. Bảo vệ MCP endpoint

Các MCP endpoint là bề mặt tích hợp có thể khám phá và gọi API. Springdoc không cung cấp authentication/authorization riêng cho chúng; ứng dụng phải áp dụng Spring Security hoặc kiểm soát tương đương.

Các path cần được xem xét cùng nhau:

- `/mcp`: MCP server endpoint.
- `/mcp-ui/**`: Developer Dashboard.
- `/api/mcp-admin/**`: Dashboard REST API.

Ví dụ filter chain riêng cho MCP:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class McpSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain mcpSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(
                "/mcp",
                "/mcp-ui/**",
                "/api/mcp-admin/**"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("MCP_ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ minh họa authority. Trong ứng dụng thực tế, tích hợp matcher vào chiến lược authentication hiện có, chọn role/scope phù hợp với MCP client và kiểm tra thứ tự các `SecurityFilterChain`. Nếu transport dùng POST, đánh giá CSRF theo cơ chế xác thực và cách client gửi token; không tắt CSRF toàn ứng dụng chỉ để làm MCP hoạt động.

Human-in-the-Loop (HITL) của MCP guardrails là bước xác nhận trước khi thực thi operation có thể thay đổi dữ liệu. Nó không phải authentication, không phải authorization và không thay thế security filter.

## 10. Guardrails khi công cụ có thể thay đổi dữ liệu

Springdoc MCP phân loại tool theo HTTP method:

| Phân loại mặc định | HTTP method |
|---|---|
| Safe/read-only | GET, HEAD, OPTIONS |
| Mutating | POST, PUT, DELETE, PATCH và method khác |

Mặc định, `springdoc.ai.mcp.guardrails.require-approval-for-mutating-tools=true`. Khi agent gọi tool mutating, server trả phản hồi yêu cầu phê duyệt thay vì thực thi HTTP call ngay.

Có thể cấu hình:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: true
        safe-methods: GET,HEAD,OPTIONS
~~~

Nếu tắt yêu cầu phê duyệt:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: false
~~~

Chỉ cân nhắc cấu hình này khi môi trường đã có kiểm soát truy cập và vận hành phù hợp. Một endpoint GET vẫn có thể làm thay đổi trạng thái nếu API thiết kế sai; có thể override phân loại trong `McpToolCustomizer` theo policy đã review.

Không coi guardrails là ranh giới bảo mật. Người có thể truy cập MCP endpoint cũng có thể gọi API phê duyệt theo cơ chế được cung cấp; quyền truy cập vẫn phải được kiểm tra ở application security.

## 11. Điều kiện cho extension bean của ứng dụng

Nếu ứng dụng tự thêm `McpToolCustomizer`, tool metadata hoặc bean hỗ trợ MCP, hãy đặt chúng sau cùng điều kiện bật MCP. Nếu không, extension có thể được tạo khi MCP integration đang tắt hoặc làm ứng dụng lỗi khi MCP starter không có trên classpath.

Ví dụ với một bean mở rộng do ứng dụng sở hữu:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "springdoc.ai.mcp",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class MyMcpExtensionConfiguration {

    @Bean
    MyMcpExtensionMarker myMcpExtensionMarker() {
        return new MyMcpExtensionMarker();
    }
}
~~~

Nếu extension tham chiếu trực tiếp class của MCP starter, đặt thêm `@ConditionalOnClass` trên một configuration class riêng. Điều đó giúp ứng dụng không cần module MCP vẫn khởi động được.

Springdoc cung cấp các extension point như `McpToolCustomizer` để đổi tên, mô tả, schema đầu vào hoặc loại một tool khỏi registry. Có thể dùng `@McpToolDescription` trên controller method để cung cấp mô tả dành cho AI agent. Những extension này chỉ có ý nghĩa khi MCP integration đã được bật.

### Tool grouping phụ thuộc OpenAPI metadata

Springdoc dùng `operationId` làm tên tool mặc định và dùng tag đầu tiên của controller để nhóm tool. Vì vậy, nếu một operation không có operationId hoặc tag rõ ràng, tên và nhóm trong MCP dashboard có thể khó hiểu.

Trước khi bật MCP, kiểm tra:

- Mọi operation dự kiến expose đều có operationId rõ ràng.
- Summary/description giải thích mục đích và giới hạn của tool.
- Request parameters và request body mô tả được bằng schema.
- Controller có tag phù hợp để dashboard nhóm tool.
- Operation nội bộ hoặc nhạy cảm đã được lọc khỏi tool generation.

## 12. Các MCP property cần biết

Các property MCP nằm dưới prefix `springdoc.ai.mcp` và chỉ có tác dụng khi ứng dụng thêm MCP starter phù hợp.

| Property | Mặc định | Mục đích |
|---|---|---|
| `springdoc.ai.mcp.enabled` | `false` | Bật/tắt MCP tool integration |
| `springdoc.ai.mcp.base-url` | `http://localhost:8080` | Base URL cho HTTP call thực thi tool; nếu không đặt sẽ dùng localhost cùng server port |
| `springdoc.ai.mcp.init-timeout-seconds` | `30` | Timeout chờ OpenAPI spec lúc startup |
| `springdoc.ai.mcp.paths-to-exclude` | rỗng | Danh sách path pattern không chuyển thành MCP tools |
| `springdoc.ai.mcp.mcp-endpoint` | `/mcp` | Path của MCP server |
| `springdoc.ai.mcp.dashboard-enabled` | `false` | Bật Developer Dashboard |
| `springdoc.ai.mcp.dashboard-path` | `/mcp-ui` | Path của dashboard |
| `springdoc.ai.mcp.guardrails.require-approval-for-mutating-tools` | `true` | Yêu cầu xác nhận trước tool mutating |
| `springdoc.ai.mcp.guardrails.safe-methods` | `GET,HEAD,OPTIONS` | Các HTTP method mặc định được xem là read-only |
| `springdoc.ai.mcp.audit.redact` | `true` | Mask giá trị có tên giống secret trong audit event |

Nếu dashboard bật, audit event được hiển thị trong dashboard và log qua logger dành cho MCP audit. Giữ redaction bật trừ khi audit sink là kho tin cậy có kiểm soát truy cập. Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào tool description hay ví dụ.

## 13. Kiểm thử điều kiện bật/tắt của extension

`ApplicationContextRunner` phù hợp để kiểm tra cấu hình tùy chọn do ứng dụng sở hữu trên JVM. Ví dụ tạo một marker bean chỉ tồn tại khi MCP được bật:

~~~java
@Configuration(proxyBeanMethods = false)
class OptionalMcpExtensionConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "springdoc.ai.mcp",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    McpExtensionMarker mcpExtensionMarker() {
        return new McpExtensionMarker();
    }
}

record McpExtensionMarker() {
}
~~~

Test các trường hợp thiếu property, `false` và `true`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalMcpExtensionConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(
                OptionalMcpExtensionConfiguration.class
            );

    @Test
    void missingPropertyKeepsExtensionDisabled() {
        runner.run(context ->
            assertThat(context)
                .doesNotHaveBean(McpExtensionMarker.class)
        );
    }

    @Test
    void falseKeepsExtensionDisabled() {
        runner.withPropertyValues(
            "springdoc.ai.mcp.enabled=false"
        ).run(context ->
            assertThat(context)
                .doesNotHaveBean(McpExtensionMarker.class)
        );
    }

    @Test
    void trueRegistersExtension() {
        runner.withPropertyValues(
            "springdoc.ai.mcp.enabled=true"
        ).run(context ->
            assertThat(context)
                .hasSingleBean(McpExtensionMarker.class)
        );
    }
}
~~~

Đây là test cho extension configuration của ứng dụng, không thay thế integration test cho Springdoc MCP starter. `ApplicationContextRunner` là công cụ test auto-configuration trên JVM; không dùng nó làm native-image integration test.

### Ma trận kiểm thử MCP integration

Ngoài extension bean, kiểm tra starter thực tế theo ma trận:

| MCP starter | Property | Dashboard | Kết quả mong đợi |
|---|---|---|---|
| Không có | Bất kỳ | Bất kỳ | Không có MCP integration |
| Có | Không khai báo | Không bật | MCP tắt theo mặc định |
| Có | `false` | Không bật | Không đăng ký MCP server |
| Có | `true` | Không bật | MCP server và tool registry được đăng ký |
| Có | `true` | `true` | MCP server và dashboard được đăng ký |

Với trường hợp bật, dùng MCP client/test harness tương thích để gửi `initialize`, sau đó gọi `tools/list` và xác minh operation dự kiến xuất hiện. Không chỉ gọi GET vào `/mcp` rồi kết luận server hoạt động; Streamable HTTP transport có quy tắc request/response riêng.

## 14. Chẩn đoán auto-configuration

Khi property đã bật nhưng MCP bean hoặc endpoint không xuất hiện, kiểm tra điều kiện auto-configuration trước khi viết thêm bean thủ công.

Chạy ứng dụng với `--debug`:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot sẽ ghi condition evaluation report, cho biết auto-configuration nào được áp dụng hoặc bị loại và lý do. Nếu có Actuator, có thể expose endpoint conditions:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Sau đó xem `/actuator/conditions`. Endpoint này chứa thông tin cấu hình nhạy cảm về cấu trúc ứng dụng; bảo vệ bằng Spring Security và chỉ expose ở môi trường vận hành phù hợp.

Kiểm tra theo thứ tự:

1. Dependency tree có đúng MCP starter không?
2. Starter có khớp WebMVC hay WebFlux không?
3. Springdoc major có tương thích với Spring Boot major không?
4. Environment thực tế có `springdoc.ai.mcp.enabled=true` không?
5. Profile nào đang active và file cấu hình nào ghi đè property?
6. Condition report có cho biết class hoặc property condition không khớp không?
7. OpenAPI có được preload và hoàn tất trước init timeout không?
8. Security matcher có chặn MCP endpoint hoặc dashboard không?

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đã thêm MCP starter nhưng không thấy `/mcp` | `springdoc.ai.mcp.enabled` chưa được đặt thành `true` | Bật property trong đúng profile |
| Property `springdoc.mcp.enabled` không có tác dụng | Sai prefix | Dùng `springdoc.ai.mcp.enabled` |
| Dashboard không xuất hiện dù MCP chạy | `dashboard-enabled` mặc định `false` | Bật dashboard riêng nếu thực sự cần |
| Ứng dụng không khởi động với class MCP | Thêm nhầm starter hoặc dependency version không tương thích | Chọn WebMVC/WebFlux starter và version theo compatibility matrix |
| Tool list trống | Controller chưa được mô tả/scan hoặc OpenAPI chưa có operation phù hợp | Kiểm tra `/v3/api-docs`, package/path scan và operation metadata |
| Tool name khó hiểu | `operationId` thiếu hoặc không ổn định | Đặt operationId rõ ràng |
| Tool group rơi vào Other | Controller thiếu tag | Thêm `@Tag` phù hợp |
| Tool nội bộ vẫn xuất hiện | Chưa cấu hình `paths-to-exclude` hoặc filter custom | Lọc tool và bảo vệ route runtime |
| MCP startup timeout | OpenAPI generation chậm hoặc base configuration chưa sẵn sàng | Xem log preload và điều chỉnh timeout có căn cứ |
| Dashboard trả 401/403 | Security chain yêu cầu quyền | Cấp role/scope phù hợp cho người vận hành |
| MCP endpoint truy cập được không cần đăng nhập | Chưa bảo vệ endpoint trong Spring Security | Bảo vệ `/mcp`, `/mcp-ui/**` và `/api/mcp-admin/**` |
| Mutating tool yêu cầu approval nhưng vẫn không an toàn | HITL bị hiểu nhầm là authorization | Kiểm tra identity và quyền ở application layer |

## 16. Quy trình triển khai theo môi trường

Một quy trình triển khai có kiểm soát:

1. Xác nhận Spring Boot và Springdoc version tương thích.
2. Chọn MCP starter theo web stack.
3. Để `springdoc.ai.mcp.enabled=false` ở cấu hình mặc định.
4. Chỉ bật `true` trong profile hoặc environment đã được duyệt.
5. Bắt đầu với dashboard tắt; chỉ bật khi có nhu cầu vận hành.
6. Xác định base URL mà tool execution có thể truy cập.
7. Loại path nội bộ/nhạy cảm khỏi tool registry.
8. Đặt authentication/authorization cho MCP và dashboard endpoints.
9. Giữ guardrails mutating approval bật nếu chưa có policy khác.
10. Kiểm thử `initialize` và `tools/list` bằng MCP client.
11. Kiểm tra log startup, condition report và audit redaction.
12. Theo dõi startup time và lỗi gọi tool sau khi phát hành.

Không bật MCP trong production chỉ để thử dashboard. Dùng profile thử nghiệm hoặc môi trường tích hợp có quyền truy cập giới hạn.

## 17. Bài thực hành tổng hợp

Tạo một ứng dụng Spring Boot có `ProductController` và MCP integration:

1. Xác định ứng dụng dùng Spring MVC hay WebFlux.
2. Thêm đúng `springdoc-openapi-starter-webmvc-mcp` hoặc `springdoc-openapi-starter-webflux-mcp`.
3. Xác nhận dependency version tương thích với Spring Boot.
4. Khởi động khi `springdoc.ai.mcp.enabled` không được khai báo và xác minh MCP không đăng ký.
5. Đặt `springdoc.ai.mcp.enabled=false` và xác minh trạng thái vẫn tắt.
6. Bật property thành `true` trong profile `mcp`.
7. Gọi MCP `initialize` và `tools/list` để kiểm tra tool được tạo từ controller.
8. Bật dashboard bằng `dashboard-enabled=true` và kiểm tra path `/mcp-ui`.
9. Cấu hình `paths-to-exclude` để loại `/admin/**`.
10. Thêm Spring Security rule cho `/mcp`, `/mcp-ui/**` và `/api/mcp-admin/**`.
11. Kiểm tra mutating tool trả yêu cầu approval theo guardrail mặc định.
12. Chạy ứng dụng với `--debug` và đọc condition report.
13. Viết `ApplicationContextRunner` test cho extension bean khi property thiếu, false và true.
14. Đưa dependency, property và security configuration vào pipeline CI.

### Tiêu chí hoàn thành

- [ ] Chọn đúng MCP starter theo WebMVC/WebFlux.
- [ ] Biết MCP starter có trong classpath không tự động bật MCP integration.
- [ ] Cấu hình `springdoc.ai.mcp.enabled=true` tường minh.
- [ ] Hiểu mặc định `false` từ Springdoc 3.1.1.
- [ ] Tách dashboard khỏi MCP server bằng `dashboard-enabled`.
- [ ] Hiểu preloading được bật khi MCP integration được bật.
- [ ] Biết dùng `@ConditionalOnProperty` cho extension bean.
- [ ] Kiểm tra dependency và property condition trong condition report.
- [ ] MCP tools chỉ chứa operation dự kiến.
- [ ] `/mcp`, `/mcp-ui/**` và `/api/mcp-admin/**` được bảo vệ.
- [ ] Không dùng HITL thay cho authorization.
- [ ] Có test cho các trạng thái property thiếu, false và true.

## Tiếp tục học

Sau bài này, hãy kết hợp MCP enablement với `McpToolCustomizer`, `@McpToolDescription`, tool grouping, schema conversion và audit logging. Việc thêm dependency chỉ cung cấp khả năng tích hợp; quyết định expose MCP tools phải được thể hiện trong cấu hình, kiểm tra bằng condition tests và bảo vệ ở tầng ứng dụng.

## Tài liệu tham khảo

- [Springdoc MCP Support](https://springdoc.org/#mcp-support)
- [Springdoc MCP properties](https://springdoc.org/#springdoc-openapi-mcp-properties)
- [Springdoc releases – MCP integration](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot – ConditionalOnProperty API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot – Troubleshooting Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html)
