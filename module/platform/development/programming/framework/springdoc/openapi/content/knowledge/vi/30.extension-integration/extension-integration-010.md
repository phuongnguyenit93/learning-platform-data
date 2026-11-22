# Giới hạn tương thích giữa Springdoc, Spring AI và phiên bản giao thức

Khi đưa AI agent vào một ứng dụng Spring Boot, nhóm phát triển có thể muốn vừa công bố REST API bằng OpenAPI, vừa cho agent gọi các chức năng đó qua Model Context Protocol (MCP). springdoc-openapi và Spring AI có thể phối hợp trong kiến trúc này, nhưng mỗi thành phần giải quyết một lớp khác nhau. Nếu chỉ chọn các dependency có số phiên bản mới nhất mà không kiểm tra nền tảng Spring Boot, MCP Java SDK và revision giao thức, ứng dụng có thể không khởi động, không đăng ký được tool hoặc client không thể bắt tay với server.

Điều quan trọng là phân biệt năm trục:

1. **Spring Boot / Spring Framework:** nền tảng runtime và auto-configuration mà thư viện phải tương thích.
2. **springdoc-openapi:** đọc controller và metadata Spring để sinh OpenAPI Description, Swagger UI hoặc tích hợp MCP tùy module.
3. **Spring AI:** cung cấp abstraction cho model, tool calling và MCP client/server trong Spring.
4. **MCP Java SDK:** triển khai API Java cho client, server, transport và message của MCP.
5. **MCP protocol revision:** quy định định dạng và vòng đời giao tiếp trên wire giữa MCP client và server.

Phiên bản OpenAPI trong field openapi của tài liệu cũng là một trục riêng. OpenAPI version không phải Spring AI version và cũng không phải MCP protocol version.

## 1. Phân biệt REST/OpenAPI với MCP

OpenAPI mô tả HTTP API: path, method, parameter, request body, response, schema và security requirement. springdoc đọc metadata của ứng dụng Spring rồi tạo tài liệu OpenAPI để con người, API gateway, validator hoặc client generator sử dụng.

MCP là giao thức để một AI application khám phá và gọi tools, đọc resources, lấy prompts và trao đổi capability với MCP server. MCP sử dụng JSON-RPC và có các transport như STDIO, HTTP với SSE hoặc Streamable HTTP.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["REST controllers and DTOs"]
    B --> C["springdoc-openapi"]
    C --> D["OpenAPI Description"]
    D --> E["Swagger UI / API clients"]
    D --> F["springdoc MCP bridge"]
    G["Spring AI native tools"] --> H["MCP Java SDK"]
    F --> H
    H --> I["MCP transport and protocol"]
    I --> J["AI agent / MCP client"]
~~~

Hai hướng tích hợp phổ biến:

| Hướng | Cách hoạt động | Khi phù hợp |
|---|---|---|
| REST API được chuyển thành MCP tools | springdoc đọc OpenAPI operation rồi tạo tool definition để MCP client khám phá và gọi | Đã có REST controller và muốn tái sử dụng hợp đồng hiện có |
| MCP tools được khai báo trực tiếp trong Spring AI | Dùng annotation như @McpTool, @McpResource hoặc ToolCallback để đăng ký capability | Tool có nghiệp vụ riêng, không phải mọi REST endpoint đều nên mở cho agent |

Có thể dùng cả hai hướng trong cùng ứng dụng. Tuy nhiên, cần kiểm soát tên tool, schema đầu vào, quyền truy cập và phạm vi endpoint được công bố.

## 2. Trách nhiệm của từng thành phần

| Thành phần | Trách nhiệm | Không quyết định điều gì? |
|---|---|---|
| Spring Boot | Tạo application context, web stack, configuration và security filter | Không quyết định MCP protocol revision |
| springdoc-openapi | Sinh OpenAPI từ controller, annotation, validation và cấu hình; có module MCP bridge | Không thay thế MCP Java SDK hoặc Spring AI |
| Spring AI | Cung cấp tích hợp AI model, tool calling, MCP client/server và Boot starter | Không quyết định OpenAPI schema version của REST document |
| MCP Java SDK | Cung cấp client/server, JSON-RPC message, session và transport implementation | Không tự chọn phiên bản Spring Boot hoặc springdoc |
| MCP specification | Định nghĩa wire protocol, capability, method, negotiation và transport behavior | Không quy định dependency version của Spring Boot |

Ví dụ, thay springdoc từ 2.x lên 3.x có thể cần nâng Spring Boot từ 3.x lên 4.x. Nhưng điều đó không tự động có nghĩa client MCP đã chuyển từ revision 2025-11-25 sang 2026-07-28. Revision giao thức phụ thuộc MCP server/client implementation và cấu hình tương thích của chúng.

## 3. Ma trận tương thích Spring Boot, springdoc và Spring AI

Các nhánh chính thức hiện phân chia theo Spring Boot major:

| Spring Boot | Spring Framework | springdoc-openapi | Spring AI |
|---|---|---|---|
| 3.5.x | 6.2.x | 2.8.x–2.10.x | 1.1.x |
| 4.0.x | 7.x | 3.0.x | 2.0.x |
| 4.1.x | 7.x | 3.1.x–3.2.x | 2.0.x |
| 4.2.0-RC2 | 7.x prerelease | Chưa có ma trận springdoc xác nhận trong tài liệu hiện hành | 2.1.0-RC2 |

Đây là các nhánh tương thích đã được dự án công bố, không phải bảo đảm mọi bản vá bất kỳ trong các nhánh đều có thể ghép tùy ý. Luôn kiểm tra release cụ thể, dependency management và yêu cầu Java của Spring Boot đang chọn.

Một số mốc quan trọng:

- springdoc 2.x dành cho Spring Boot 3.x; springdoc 3.x dành cho Spring Boot 4.x.
- Spring AI 1.1.x hiện nhắm tới Spring Boot 3.5.x.
- Spring AI 2.0.x được thiết kế cho Spring Boot 4.0.x và 4.1.x, dựa trên Spring Framework 7.
- Spring AI 2.0 chuyển sang nền tảng Jackson 3 cùng các thay đổi API và package tương ứng.

Không nên đưa Spring AI 2.x vào ứng dụng Spring Boot 3 chỉ vì cả hai đều có dependency Maven Central. Việc resolve được dependency không chứng minh auto-configuration, Spring Framework API và serialization stack tương thích.

### Phiên bản ổn định và prerelease

Tại ngày 20-11-2026, Spring AI 2.0.2 là bản stable mới được công bố; Spring AI 2.1.0-RC2 đã có nhưng vẫn là release candidate. Khi xây dựng production, ưu tiên bản stable trừ khi có lý do cụ thể để thử tính năng chỉ xuất hiện trong prerelease.

Spring AI 2.1.0-RC2 có hỗ trợ revision MCP 2026-07-28, dựa trên MCP Java SDK 2.2.0-M2 và được build với Spring Boot 4.2.0-RC2. Đây là điểm cần chú ý khi muốn dùng giao thức MODERN. Vì cả Spring AI 2.1.0-RC2 và Boot 4.2.0-RC2 đều là prerelease, không suy ra rằng Spring AI 2.0.2 hoặc springdoc 3.2.0 có cùng baseline đã kiểm thử.

## 4. Phân biệt các lớp phiên bản MCP

MCP có nhiều revision giao thức. Những revision handshake như 2025-11-25 và các revision cũ hơn dùng phương thức initialize để thương lượng phiên bản và capability. Revision 2026-07-28 đưa ra lifecycle MODERN với cách giao tiếp stateless theo từng request.

| Trục | Ví dụ | Ý nghĩa |
|---|---|---|
| Spring AI | 2.0.2 hoặc 2.1.0-RC2 | Phiên bản framework Spring AI |
| MCP Java SDK | 2.0.0 hoặc 2.2.0 | Phiên bản thư viện Java triển khai MCP |
| MCP protocol revision | 2025-11-25 hoặc 2026-07-28 | Quy tắc giao tiếp giữa client và server |
| Transport | STDIO, SSE, Streamable HTTP | Cách message được truyền |
| Server execution model | SYNC hoặc ASYNC | Kiểu handler đồng bộ hoặc reactive |
| Spring AI server protocol setting | SSE, STREAMABLE, STATELESS hoặc MODERN | Lựa chọn server implementation/transport behavior trong Spring AI |

Không đồng nhất transport với protocol revision. Streamable HTTP là một transport; MODERN là revision/lifecycle giao thức. Một ứng dụng có thể dùng cùng họ transport nhưng phải tuân thủ lifecycle và message format của revision đã chọn.

## 5. Legacy handshake và MODERN protocol

### Handshake era: đến 2025-11-25

Các revision handshake bắt đầu bằng:

1. Client gửi initialize cùng protocol version và capability.
2. Server trả protocol version được chọn và capability của server.
3. Client gửi notifications/initialized.
4. Client và server tiếp tục trao đổi request/response trong session.

Với HTTP transport, server có thể dùng session identifier và các notification hoặc stream theo quy tắc của revision. Client và server cần thống nhất revision mà cả hai hỗ trợ.

### MODERN: 2026-07-28

Revision MODERN thay đổi lifecycle:

- Không còn initialize handshake và session theo kiểu cũ.
- Client khám phá server qua server/discover.
- Mỗi request mang protocol version và client capability trong metadata.
- HTTP server dùng POST; response có thể là JSON hoặc text/event-stream ngắn hạn khi cần gửi progress.
- Server-initiated input như elicitation, sampling và roots được xử lý theo multi-round-trip request thay vì gọi ngược qua session cũ.
- List-changed và resource-updated notification được cung cấp qua subscriptions/listen.

Vì vậy, client cũ chỉ biết initialize không thể được coi là tương thích MODERN. Server hỗ trợ MODERN cũng không nên giả định mọi client handshake đều tự động sử dụng lifecycle mới.

## 6. STATELESS không đồng nghĩa MODERN

Một nguồn nhầm lẫn phổ biến là thuộc tính Spring AI:

~~~yaml
spring:
  ai:
    mcp:
      server:
        protocol: STATELESS
~~~

STATELESS là chế độ server trong Spring AI dành cho xử lý không duy trì session giữa các request. Nó thuộc mô hình server/transport mà Spring AI cung cấp.

MODERN là lựa chọn giao thức tương ứng revision MCP 2026-07-28:

~~~yaml
spring:
  ai:
    mcp:
      server:
        protocol: MODERN
~~~

Cả hai đều có tính chất giảm hoặc bỏ stateful session, nhưng không phải hai tên khác nhau cho cùng một chế độ. MODERN có quy tắc riêng về server/discover, metadata trên mỗi request, multi-round-trip và subscriptions/listen. Tài liệu Spring AI mô tả STATELESS là server không duy trì session state giữa các request và không hỗ trợ các message request từ server về client như elicitation, sampling hoặc ping. Hãy xác định protocol revision riêng từ khả năng của MCP Java SDK và client; không suy ra revision chỉ từ tên STATELESS.

Khi đọc cấu hình, hãy xác định chính xác:

- Đang chọn transport nào?
- Server đang chạy kiểu SYNC hay ASYNC?
- Có bật STATELESS server mode không?
- Có thực sự triển khai MODERN protocol revision không?
- Client có hỗ trợ cùng revision không?

Không dùng từ “stateless” trong kiến trúc để kết luận client và server đã tương thích revision MODERN.

## 7. Tương thích MCP Java SDK theo Spring AI

Spring AI quản lý MCP Java SDK thông qua dependency management. Các mốc nâng cấp có thay đổi đáng kể:

| Spring AI line | MCP Java SDK line | Ghi chú |
|---|---|---|
| Spring AI 1.1.8 | 0.18.3 | Mốc dependency được công bố cho release 1.1.8 trên Boot 3.5.x |
| Spring AI 2.0.x | 2.0.x | Nâng SDK lớn; các transport Spring được chuyển vào project Spring AI |
| Spring AI 2.1.0-RC2 | 2.2.0-M2 | Hỗ trợ MODERN revision 2026-07-28 trong prerelease |

Đây là các mốc theo release được công bố. Nếu dự án khai báo MCP SDK trực tiếp thay vì dùng Spring AI BOM, cần kiểm tra dependency tree để chắc chắn không ép một version khác với version mà Spring AI starter đã kiểm thử.

### Thay đổi package và artifact từ Spring AI 2.0

Trước Spring AI 2.0, một số transport Spring được phát hành từ group của MCP Java SDK:

~~~xml
<dependency>
    <groupId>io.modelcontextprotocol.sdk</groupId>
    <artifactId>mcp-spring-webmvc</artifactId>
</dependency>
~~~

Từ Spring AI 2.0, transport Spring được chuyển sang group org.springframework.ai:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>mcp-spring-webmvc</artifactId>
</dependency>
~~~

Các package Java của transport cũng chuyển từ io.modelcontextprotocol sang org.springframework.ai.mcp. Nếu code trực tiếp khởi tạo transport provider, phải cập nhật import. Nếu chỉ dùng Spring Boot starter và auto-configuration, phần lớn việc đổi package được xử lý bên trong starter.

Spring AI 2.0 cũng nâng MCP Java SDK từ 1.1.x lên 2.0.0. Thay đổi này ảnh hưởng code tham chiếu trực tiếp các type MCP, nên cần đọc upgrade notes nếu ứng dụng có custom client/server builder.

## 8. Springdoc MCP bridge hoạt động như thế nào?

springdoc có module MCP tùy chọn để biến các REST endpoint đã được mô tả bằng OpenAPI thành MCP tools. Ý tưởng là tái sử dụng metadata đã có:

1. Springdoc scan controller và tạo OpenAPI document.
2. Mỗi OpenAPI operation được chuyển thành tool definition.
3. Tool name thường lấy từ operationId.
4. Tool description lấy từ summary/description.
5. JSON Schema đầu vào được tạo từ parameter và request body.
6. MCP client khám phá tool và gọi nó qua MCP server.

Ví dụ, controller:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products")
class ProductController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo mã"
    )
    ProductResponse getById(@PathVariable String id) {
        // ...
    }
}
~~~

Operation này vẫn có REST contract qua GET /api/products/{id}. Khi bridge được bật, nó có thể xuất hiện như một MCP tool với tên được suy ra từ operationId và input schema chứa id.

MCP tool không phải REST route mới. Nó là cách agent gọi operation đã có thông qua giao thức MCP.

Bridge thường chuyển operationId thành tên tool dạng snake_case, ví dụ getProductById thành get_product_by_id; lấy description từ summary/description và gom tool theo tag của controller. Có thể dùng @McpToolDescription để cung cấp tên hoặc mô tả được viết riêng cho AI agent, hoặc McpToolCustomizer để đổi tên, chỉnh description/schema hay loại endpoint khỏi danh sách tool.

## 9. Chọn đúng starter của springdoc MCP

Tài liệu MCP hiện hành của springdoc mô tả starter riêng cho từng web stack:

| Web stack | Dependency |
|---|---|
| Spring MVC / Servlet | springdoc-openapi-starter-webmvc-mcp |
| Spring WebFlux | springdoc-openapi-starter-webflux-mcp |

Ví dụ dependency được tài liệu hiện hành minh họa ở version 3.2.0:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Starter WebFlux tương ứng dùng artifact springdoc-openapi-starter-webflux-mcp. Chọn đúng starter với web stack của ứng dụng. Không thêm đồng thời MVC và WebFlux MCP starter chỉ để thử; hai stack có cách cấu hình server và resource khác nhau.

Hướng dẫn MCP hiện hành minh họa dòng springdoc 3.2.0, thuộc nhánh Boot 4.x. Không sao chép dependency 3.2.0 vào ứng dụng Boot 3.x đang dùng springdoc 2.x. Với ứng dụng Boot 3, hãy dùng nhánh springdoc 2.x phù hợp cho OpenAPI và Spring AI 1.1.x phù hợp cho MCP; nếu cần bridge REST-to-MCP, xác minh artifact/version cụ thể đã được phát hành cho nhánh đó trước khi triển khai.

## 10. Bật bridge một cách tường minh

Từ springdoc 3.1.1, MCP integration mặc định tắt. Việc thêm starter không đồng nghĩa ứng dụng tự mở endpoint MCP. Bật tính năng bằng:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

Nếu cần dashboard quản trị tool, cấu hình dashboard riêng:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
~~~

Bridge yêu cầu OpenAPI specification có sẵn khi khởi tạo tool. Tài liệu springdoc ghi nhận khi MCP được bật, pre-loading OpenAPI được bật tự động để đăng ký tool.

Không bật bridge chỉ vì ứng dụng có Swagger UI. Hãy xác định operation nào thực sự phù hợp để agent gọi, vì một REST endpoint được công bố thành tool có thể thực hiện hành động thay mặt người dùng.

## 11. Giới hạn tương thích được tài liệu hóa giữa springdoc và Spring AI

Tài liệu MCP của springdoc nêu rõ bridge đăng ký tool qua McpSyncServer; từ springdoc 3.2.0, nó cũng hỗ trợ McpStatelessSyncServer của Spring AI STATELESS protocol.

Đây là ranh giới cần chú ý khi so với Spring AI 2.1.0-RC2:

- Spring AI 2.1.0-RC2 có hỗ trợ MODERN server protocol và yêu cầu MCP Java SDK 2.2.0 line.
- Springdoc MCP guide hiện mô tả hỗ trợ SYNC server và STATELESS server, nhưng không xác nhận rõ bridge REST-to-MCP với MODERN server protocol.
- Do đó, không được kết luận rằng springdoc 3.2.0 bridge đã tương thích MODERN chỉ vì Spring AI 2.1 có thể chạy MODERN.

Nếu cần MODERN, hãy xác minh bằng integration test với đúng phiên bản springdoc, Spring AI, MCP Java SDK và client. Nếu bridge không nằm trong phạm vi được hỗ trợ, có thể expose tool bằng Spring AI native annotations/ToolCallback và vẫn dùng springdoc cho REST/OpenAPI documentation.

Một tính năng của Spring AI không tự động trở thành tính năng được springdoc bridge hỗ trợ. Tương thích phải được kiểm tra ở ranh giới giữa hai integration.

## 12. Spring AI native MCP tools

Khi tool không phải là một REST operation hoặc cần input/output riêng cho AI agent, có thể dùng MCP annotations của Spring AI:

~~~java
@Component
class CatalogTools {

    @McpTool(name = "find_product", description = "Tìm sản phẩm theo mã")
    ProductResult findProduct(
            @McpToolParam(description = "Mã sản phẩm", required = true)
            String productId) {
        // ...
    }
}
~~~

Spring AI cũng cung cấp annotation cho resources và prompts:

- @McpTool: hành động có thể được MCP client gọi.
- @McpResource: dữ liệu được truy cập theo URI hoặc URI template.
- @McpPrompt: prompt template có cấu trúc.
- @McpComplete: gợi ý hoàn thành giá trị cho prompt hoặc resource URI.

Các native tools và OpenAPI-backed tools có thể cùng tồn tại. Hãy tránh đặt hai tool khác tên nhưng cùng thực hiện một hành động, vì agent có thể chọn nhầm hoặc tạo hành động lặp.

## 13. Security là một phần của tương thích tích hợp

MCP HTTP endpoint không tự cung cấp authentication/authorization chỉ vì đã thêm Spring AI starter hoặc springdoc MCP starter. Theo tài liệu Spring AI, HTTP transports có thể mặc định cho phép truy cập endpoint; Spring Security hoặc security proxy phải thiết lập ranh giới truy cập.

Các endpoint có thể xuất hiện trong tích hợp springdoc MCP gồm:

- /mcp: MCP protocol endpoint.
- /mcp-ui: developer dashboard nếu bật.
- /api/mcp-admin/*: dashboard REST API.

Ví dụ policy minh họa:

~~~java
@Bean
SecurityFilterChain mcpSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/mcp", "/mcp-ui/**", "/api/mcp-admin/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/mcp").hasAuthority("SCOPE_mcp.invoke")
            .requestMatchers("/mcp-ui/**", "/api/mcp-admin/**")
                .hasRole("MCP_ADMIN")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

Đây là ví dụ policy; điều kiện authority và cách cấu hình JWT phải khớp hệ thống identity thực tế. Không copy nguyên snippet nếu ứng dụng dùng session login, API key hoặc một security chain khác.

### Không xem HITL là authorization

Bridge mặc định yêu cầu approval cho mutating tools thông qua require-approval-for-mutating-tools. Đây là guardrail giúp người dùng xem lại hành động. Nó không xác thực người gọi và không thay thế authorization. Người có thể gọi MCP endpoint vẫn có thể thử gửi lại request hoặc thao tác qua endpoint quản trị nếu các endpoint đó không được bảo vệ.

Luôn bảo vệ MCP endpoint bằng Spring Security hoặc security gateway, kể cả khi bật require-approval-for-mutating-tools.

Với HTTP transport, tài liệu Spring AI cũng lưu ý transport mặc định không tự xác thực Origin header. Nếu MCP server nghe trên localhost hoặc mạng nội bộ, một trang web độc hại vẫn có thể thử gọi tới địa chỉ đó qua browser và DNS rebinding. Hãy dùng security layer hoặc reverse proxy có kiểm tra Origin theo yêu cầu MCP. STDIO không mở endpoint mạng nên có ranh giới triển khai khác.

### Phân loại tool theo tác động

Springdoc MCP bridge mặc định phân loại GET, HEAD và OPTIONS là safe; POST, PUT, PATCH và DELETE là mutating. Có thể tùy chỉnh bằng McpToolCustomizer.

Không phải mọi GET đều an toàn về nghiệp vụ. Ví dụ GET /cache/invalidate có thể thay đổi state. Cũng có POST chỉ tạo báo cáo đọc dữ liệu. Hãy review từng operation theo tác động thực tế, không chỉ dựa vào HTTP method.

## 14. WebMVC và WebFlux phải khớp nhau

Một ứng dụng Spring MVC dùng Servlet stack cần starter WebMVC. Ứng dụng reactive dùng WebFlux cần starter WebFlux. Sự khác nhau ảnh hưởng:

- Loại server transport provider.
- Kiểu handler đồng bộ hay reactive.
- Cách xử lý streaming và backpressure.
- Security filter chain.
- Dependency kéo theo trong runtime.

Spring AI có client starter WebFlux riêng khi cần reactive transport. Không trộn transport WebMVC và WebFlux trong cùng một cấu hình chỉ để giải quyết lỗi dependency. Xác định web application type và chọn starter theo stack thực tế.

Server type SYNC và ASYNC cũng cần phù hợp với tool handler. Server SYNC đăng ký handler đồng bộ; server ASYNC dùng handler reactive. Nếu annotation scanner không tìm thấy method, kiểm tra loại server và loại handler trước khi kết luận MCP SDK không tương thích.

## 15. Ví dụ cấu hình nền tảng Boot 4

Ví dụ này minh họa một ứng dụng Spring Boot 4.1.x, Spring AI 2.0.2 và springdoc 3.2.0. Đây là bộ phiên bản cùng nhánh tương thích theo ma trận công bố; vẫn phải kiểm tra release note và dependency resolution của dự án.

Maven dependency management:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>2.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
        <version>3.2.0</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-mcp-server-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

Configuration:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true

spring:
  ai:
    mcp:
      server:
        protocol: STATELESS
~~~

Ví dụ chọn STATELESS server mode được tài liệu springdoc 3.2.0 ghi nhận. Nó không phải ví dụ bật MODERN protocol 2026-07-28. Nếu muốn thử MODERN với Spring AI 2.1 prerelease, hãy dùng đúng dependency line và test riêng bridge compatibility trước khi đưa vào production.

Nếu ứng dụng chỉ cần native Spring AI tools, có thể bỏ springdoc MCP starter, giữ springdoc webmvc-api hoặc webmvc-ui cho REST docs và chỉ dùng Spring AI MCP server starter cho tool endpoint.

## 16. Kiểm tra dependency tree trước khi chạy

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,org.springframework.ai,io.modelcontextprotocol
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-ai --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mcp --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
~~~

Kiểm tra:

- Có đúng một version springdoc starter phù hợp web stack không?
- Spring AI BOM có quản lý toàn bộ Spring AI modules không?
- MCP Java SDK có bị override bởi dependency trực tiếp hoặc một starter khác không?
- Có còn artifact cũ io.modelcontextprotocol.sdk:mcp-spring-webmvc/webflux trong khi dùng Spring AI 2.x không?
- Các import transport có thuộc package org.springframework.ai.mcp tương ứng không?
- Jackson 2 và Jackson 3 có bị kéo vào theo cách gây xung đột không?

Không ép version MCP SDK bằng resolutionStrategy chỉ để xử lý một lỗi compile. Trước tiên tìm dependency nào đưa version không tương thích vào graph.

## 17. Kiểm tra protocol negotiation

Với handshake-era, test initialize để xác nhận client và server chọn được revision chung. Ghi lại protocolVersion trong InitializeResult và xác nhận capability cần dùng có được quảng bá.

Với MODERN, kiểm tra:

- Client gửi server/discover và nhận identity/capabilities.
- Request có protocol version và client capabilities trong metadata.
- Server xử lý POST và trả JSON hoặc stream theo quy tắc.
- Client/server hiểu multi-round-trip input nếu tool dùng elicitation hoặc sampling.
- Change notification được nhận qua subscriptions/listen nếu bật capability tương ứng.

Không chỉ kiểm tra TCP port mở hoặc HTTP 200. Một endpoint có thể trả HTTP response nhưng không hiểu JSON-RPC method, revision hoặc capability mà client yêu cầu.

## 18. Kiểm thử OpenAPI bridge riêng với MCP protocol

Một bộ integration test nên xác minh hai lớp:

### REST/OpenAPI

- /v3/api-docs trả document hợp lệ.
- OperationId ổn định và không trùng.
- Request parameter và body schema chính xác.
- Security requirement và response code phản ánh API.
- Group hoặc path filter không làm lộ endpoint nội bộ.

### MCP

- MCP endpoint chỉ đăng ký tool được cho phép.
- Tool name và description phù hợp với agent.
- JSON Schema đầu vào phản ánh parameter/body.
- Tool call chuyển đúng tới REST operation hoặc handler.
- Mutating tool yêu cầu approval theo policy.
- Authentication/authorization được thực thi.
- Protocol revision và transport được client/server hỗ trợ chung.

Nếu REST API chạy nhưng tool không xuất hiện, kiểm tra bridge registration, pre-loading, operationId, customizer và server type. Nếu tool xuất hiện nhưng call thất bại, kiểm tra schema đầu vào, security header, transport và protocol revision.

## 19. Những lỗi tương thích thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Spring AI 2.x không khởi động trên Boot 3.x | Không khớp baseline Boot 4 | Dùng Spring AI 1.1.x với Boot 3.5.x hoặc nâng nền tảng |
| springdoc 3.x lỗi với Boot 3.x | Nhánh springdoc 3.x dành cho Boot 4 | Dùng springdoc 2.x tương ứng |
| Không resolve artifact springdoc MCP | Dùng sai nhánh/version hoặc artifact chưa được phát hành cho stack | Kiểm tra đúng MCP guide và Plugin/Maven Central coordinates |
| ClassNotFoundException ở MCP transport | Dùng import cũ từ MCP SDK trong Spring AI 2.x | Chuyển sang package org.springframework.ai.mcp |
| NoSuchMethodError trong MCP SDK | SDK bị override khỏi version Spring AI quản lý | Dùng BOM và kiểm tra dependency tree |
| Client báo unsupported protocol version | Client và server không có revision giao nhau | Chọn revision chung hoặc nâng SDK |
| Client gửi initialize tới server MODERN | Khác lifecycle handshake và modern | Dùng client hỗ trợ server/discover hoặc cấu hình handshake server |
| springdoc bridge không đăng ký tool | Chưa bật springdoc.ai.mcp.enabled hoặc OpenAPI chưa preload | Kiểm tra property, starter và startup logs |
| REST route có nhưng MCP tool bị thiếu | Operation bị filter hoặc customizer loại bỏ | Kiểm tra path group, operationId và McpToolCustomizer |
| MCP endpoint mở nhưng bị gọi trái phép | Transport không tự enforce authorization | Bảo vệ endpoint bằng Spring Security/gateway |
| Tool call bị schema validation từ chối | JSON Schema hoặc input không hợp lệ | Đồng bộ schema với handler và client arguments |
| WebFlux handler không được đăng ký | Chọn sai SYNC/ASYNC server type | Dùng đúng programming model và starter |
| Swagger UI chạy nhưng MCP không chạy | OpenAPI UI và MCP là hai integration surface | Test MCP endpoint/protocol riêng |

## 20. Quy trình chọn phiên bản

Khi bắt đầu dự án hoặc nâng cấp:

1. Chốt Spring Boot major/minor và Java baseline.
2. Chọn springdoc branch phù hợp với Spring Boot.
3. Chọn Spring AI branch tương thích cùng Spring Boot.
4. Chọn MCP Java SDK thông qua Spring AI BOM, trừ khi có lý do cần quản lý trực tiếp.
5. Xác định client MCP phải hỗ trợ handshake revision nào hoặc MODERN.
6. Chọn transport phù hợp: STDIO, Streamable HTTP hoặc mode được triển khai.
7. Xác minh springdoc MCP bridge hỗ trợ đúng loại Spring AI server mà dự án định dùng.
8. Kiểm tra dependency tree và package import.
9. Chạy integration test cho OpenAPI, tool discovery, tool call và security.
10. Chỉ nâng protocol revision khi cả client và server cùng hỗ trợ và các feature cần dùng không bị loại bỏ.

Nếu dự án đang ổn định trên Boot 3.5, không cần nâng cả stack chỉ để dùng Swagger UI. Có thể tiếp tục springdoc 2.x cho REST documentation và Spring AI 1.1.x cho các MCP capability tương ứng. Nếu cần tính năng chỉ có ở Spring AI 2.x hoặc MODERN revision, hãy lập kế hoạch nâng Boot 4, springdoc 3 và SDK đồng bộ.

## 21. Checklist tương thích trước khi phát hành

- [ ] Spring Boot, Spring Framework và Java version nằm trong baseline hỗ trợ.
- [ ] springdoc branch phù hợp với Spring Boot major/minor.
- [ ] Spring AI branch phù hợp với Spring Boot.
- [ ] MCP Java SDK được quản lý theo BOM hoặc đã xác minh dependency tree.
- [ ] Không trộn transport artifact/package cũ với Spring AI 2.x.
- [ ] MVC/WebFlux starter khớp web stack.
- [ ] SYNC/ASYNC handler khớp server type.
- [ ] Transport và MCP protocol revision được xác định riêng.
- [ ] Client và server thương lượng được revision chung.
- [ ] Không nhầm STATELESS server mode với MODERN protocol revision.
- [ ] springdoc MCP bridge đã được bật tường minh nếu dùng.
- [ ] Đã xác minh bridge hỗ trợ loại MCP server đang chạy.
- [ ] Operation được expose thành tool đã được review.
- [ ] MCP endpoint, dashboard và admin API có authentication/authorization.
- [ ] Mutating tools có policy approval và authorization riêng.
- [ ] Integration tests bao phủ OpenAPI, tool discovery, invocation và protocol negotiation.
- [ ] Đã kiểm tra release notes khi nâng springdoc, Spring AI hoặc MCP SDK.

## 22. Tài liệu tham khảo chính thức

- [springdoc-openapi Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): ma trận springdoc với Spring Boot.
- [springdoc-openapi MCP Support](https://springdoc.org/mcp.html): MCP bridge, module WebMVC/WebFlux, opt-in property, tool conversion, guardrails và server integration.
- [springdoc-openapi v2 Documentation](https://springdoc.org/v2/): cấu hình cho Spring Boot 3.x.
- [Spring AI Getting Started](https://docs.spring.io/spring-ai/reference/getting-started.html): Spring AI line và Spring Boot compatibility.
- [Spring AI MCP Overview](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html): MCP starter, client/server integration và transport.
- [Spring AI MCP Server Starter](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html): protocol, transport, SYNC/ASYNC và bảo mật.
- [Spring AI MCP Modern Server](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-modern-server-boot-starter-docs.html): revision 2026-07-28, yêu cầu SDK 2.2.0 line và MODERN configuration.
- [Spring AI Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): thay đổi MCP SDK và package khi nâng Spring AI 2.0.
- [Spring AI 2.1.0-RC2 announcement](https://spring.io/blog/2026/11/09/spring-ai-2-1-0-RC2-available-now/): trạng thái prerelease và tính năng MCP MODERN.
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25): protocol revision handshake.
- [MCP Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28): revision MODERN với server/discover và request metadata.

## Kết luận

Tương thích giữa springdoc, Spring AI và MCP không thể quyết định bằng một số version duy nhất. Hãy chọn springdoc theo Spring Boot, Spring AI theo cùng baseline Boot, để Spring AI BOM quản lý MCP Java SDK và xác định revision MCP mà client/server cùng hỗ trợ. OpenAPI mô tả REST contract; MCP định nghĩa cách agent khám phá và gọi tools. Springdoc MCP bridge có thể chuyển operation đã được mô tả thành tools, còn Spring AI native annotations phù hợp với capability dành riêng cho agent. Đặc biệt, phân biệt STATELESS server mode với MODERN revision 2026-07-28, kiểm tra giới hạn bridge đã được tài liệu hóa và bảo vệ mọi MCP endpoint bằng authorization thực sự. Chỉ phát hành khi dependency graph, protocol negotiation, tool schema và security integration đều đã được kiểm thử.
