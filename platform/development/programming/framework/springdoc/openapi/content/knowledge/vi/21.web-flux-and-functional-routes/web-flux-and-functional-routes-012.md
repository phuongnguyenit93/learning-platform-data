# Kiểm tra tài liệu Reactive với WebTestClient hoặc công cụ tương đương

Trong ứng dụng Spring WebFlux, kiểm thử API cần xác minh cả hành vi reactive khi request chạy và tài liệu OpenAPI mà springdoc-openapi sinh ra. Một controller có thể trả Mono hoặc Flux đúng kiểu Java nhưng tài liệu lại mô tả sai schema, media type hoặc status code. Ngược lại, OpenAPI JSON có thể hợp lệ về cấu trúc nhưng endpoint thực tế trả body hoặc header khác với hợp đồng.

WebTestClient là công cụ phù hợp để gửi request và kiểm tra response của WebFlux mà không cần viết client HTTP riêng. Có thể dùng nó để kiểm tra controller, RouterFunction, OpenAPI JSON/YAML, grouped documents và Swagger UI config. Bài này trình bày cách tổ chức các lớp test, viết assertion cho schema và media type, kiểm tra luồng reactive và đưa xác minh hợp đồng vào CI.

## 1. Hai mục tiêu kiểm thử cần tách biệt

Một bộ test tốt cần xác minh hai kết quả khác nhau:

- **Tài liệu được sinh ra:** operation, parameters, request body, responses, schema, security và media type trong OpenAPI.
- **Hành vi runtime:** status code, headers, body và cách publisher reactive phát dữ liệu khi client gửi request.

Ví dụ, controller trả Flux<OrderSummary> với application/json. OpenAPI cần mô tả một JSON array có items là OrderSummary. Test tài liệu kiểm tra schema array; test runtime gửi request và kiểm tra body thực sự là danh sách JSON.

Hai nhóm test bổ sung cho nhau:

| Nhóm test | Câu hỏi cần trả lời |
|---|---|
| OpenAPI document test | springdoc có sinh đúng path, operation, schema, response và security không? |
| Runtime API test | WebFlux có trả đúng status, Content-Type, header và body không? |
| Streaming test | SSE/NDJSON có đúng media type, framing và dữ liệu được phát không? |
| UI configuration test | Swagger UI có tải đúng spec URL và cấu hình không? |
| Contract validation | Tài liệu có hợp lệ và các tham chiếu có giải quyết được không? |

Không nên dùng một test duy nhất để kết luận toàn bộ hợp đồng đúng. Việc spec có response 404 không chứng minh controller thật sự trả 404; việc controller trả 404 không chứng minh OpenAPI đã mô tả response đó.

## 2. Vì sao dùng WebTestClient?

WebTestClient được thiết kế cho Spring WebFlux và có API fluent tương tự WebClient. Nó hỗ trợ:

- Gửi GET, POST, PUT, PATCH, DELETE và các method HTTP khác.
- Thiết lập path, query parameter, header, cookie và request body.
- Kiểm tra status, response header và body.
- Decode JSON thành DTO hoặc danh sách.
- Kiểm tra JSONPath.
- Tiêu thụ response reactive và kiểm tra stream.
- Chạy với mock WebHandler hoặc kết nối tới server đang chạy.

WebTestClient có thể được cấu hình theo nhiều cách:

| Cách tạo client | Phạm vi kiểm thử |
|---|---|
| bindToController | Một hoặc một số controller được chọn |
| bindToRouterFunction | RouterFunction độc lập |
| bindToApplicationContext | Web application context và các thành phần được nạp |
| bindToServer | Server HTTP đang chạy |
| Spring Boot test với RANDOM_PORT | Ứng dụng Spring Boot đầy đủ qua embedded server |

Nếu mục tiêu là xác minh springdoc quét controller, RouterFunction, customizer, group và security configuration, nên ưu tiên integration test với application context đầy đủ. Slice test hữu ích cho handler riêng nhưng có thể không nạp toàn bộ cấu hình springdoc.

## 3. Dependency cần thiết cho test

Trong dự án Spring Boot, starter test thường cung cấp JUnit Jupiter, AssertJ, Mockito và Spring Test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ứng dụng WebFlux cần dependency runtime tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>YOUR_COMPATIBLE_SPRINGDOC_VERSION</version>
</dependency>
~~~

Dùng phiên bản springdoc tương thích với Spring Boot đang chạy. Không lấy version tùy ý từ ví dụ nếu dự án có BOM hoặc dependency management riêng.

Nếu test endpoint được bảo vệ bởi Spring Security, bổ sung test support:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Không cần thêm WebTestClient dependency riêng khi Spring Boot WebFlux và starter test đã cung cấp các thành phần cần thiết theo cấu hình dự án.

## 4. Integration test với ứng dụng Spring Boot đầy đủ

Để kiểm tra tài liệu được springdoc tạo trong đúng application context, có thể khởi động embedded server trên cổng ngẫu nhiên:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiDocumentIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void exposesOpenApiDocument() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.info.title").exists()
            .jsonPath("$.paths").exists();
    }
}
~~~

RANDOM_PORT giúp test gửi request tới server thật trong tiến trình test. Điều này kiểm tra thêm routing, filter chain và HTTP serialization so với việc chỉ gọi method controller.

Nếu ứng dụng cần database, message broker hoặc identity provider, hãy dùng profile test, container hoặc mock service phù hợp. Không để test phụ thuộc vào dữ liệu production hay dịch vụ bên ngoài không ổn định.

Tên annotation và khả năng auto-configure WebTestClient có thể phụ thuộc phiên bản Spring Boot. Nếu dự án không tạo được bean WebTestClient, kiểm tra phiên bản starter test và cấu hình WebFlux test tương ứng.

## 5. Kiểm tra metadata cơ bản của OpenAPI JSON

Endpoint mặc định thường là /v3/api-docs. Test nên kiểm tra các trường nền tảng:

~~~java
@Test
void exposesBasicOpenApiMetadata() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.openapi").exists()
        .jsonPath("$.info.title").isNotEmpty()
        .jsonPath("$.info.version").isNotEmpty()
        .jsonPath("$.paths").exists();
}
~~~

Không nên hard-code OpenAPI version nếu dự án có thể nâng springdoc hoặc thay cấu hình giữa các nhánh. Nếu hợp đồng của nhóm yêu cầu một major OpenAPI version cụ thể, hãy kiểm tra bằng assertion có chủ đích.

Có thể kiểm tra title, version, description và server URL nếu đó là metadata được cam kết. Nếu title/version lấy từ cấu hình môi trường, test nên chạy với cấu hình test rõ ràng để kết quả ổn định.

## 6. Kiểm tra path và HTTP operation

Giả sử controller có endpoint:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Có thể kiểm tra path và method trong tài liệu:

~~~java
@Test
void documentsGetOrderOperation() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths['/api/orders/{id}'].get").exists()
        .jsonPath("$.paths['/api/orders/{id}'].get.operationId")
            .isNotEmpty()
        .jsonPath("$.paths['/api/orders/{id}'].get.responses['200']")
            .exists();
}
~~~

Dùng bracket notation cho path có dấu slash và dấu ngoặc nhọn. Dùng chuỗi status code như '200' khi truy vấn JSONPath vì khóa responses trong JSON là string.

Nếu operationId là một phần hợp đồng client generator, nên kiểm tra giá trị cụ thể và tính duy nhất. Nếu operationId được sinh tự động, một thay đổi tên method hoặc mapping có thể làm thay đổi client code; cân nhắc khai báo operationId ổn định bằng @Operation.

## 7. Kiểm tra schema của Mono response

Với Mono<OrderResponse>, response JSON thường là một object OrderResponse. Ví dụ tài liệu cần có response 200 và schema tương ứng.

~~~java
@Test
void documentsSingleOrderResponse() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['200'].content['application/json'].schema"
        ).exists();
}
~~~

Nếu nhóm quản lý tên component ổn định, có thể kiểm tra $ref:

~~~java
.jsonPath(
    "$.paths['/api/orders/{id}'].get.responses['200'].content['application/json'].schema.$ref"
).value("#/components/schemas/OrderResponse")
~~~

Assertion $ref chỉ phù hợp khi dự án cam kết schema được tham chiếu theo component đó. springdoc có thể inline schema hoặc sinh tên component khác khi dùng generic, wrapper hay custom converter. Khi đó hãy kiểm tra cấu trúc schema thay vì áp đặt tên không ổn định.

Kiểm tra thêm components.schemas.OrderResponse để bảo đảm các field quan trọng có kiểu và required flag đúng.

## 8. Kiểm tra schema của Flux JSON array

Với Flux<OrderSummary> và media type application/json, tài liệu thường mô tả một array:

~~~java
@Test
void documentsFluxAsJsonArray() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath(
            "$.paths['/api/orders'].get.responses['200'].content['application/json'].schema.type"
        ).isEqualTo("array")
        .jsonPath(
            "$.paths['/api/orders'].get.responses['200'].content['application/json'].schema.items"
        ).exists();
}
~~~

Test này xác minh hình dạng tổng quát của response. Nếu dùng $ref cho items, có thể kiểm tra tham chiếu đó và component schema đích.

Đừng chỉ kiểm tra operation tồn tại. Một operation có thể được sinh nhưng response schema lại là object đơn thay vì array. Đây là lỗi dễ ảnh hưởng client generator.

## 9. Kiểm tra status và body runtime cho Mono

Test runtime cần xác minh phản hồi thực tế:

~~~java
@Test
void returnsOneOrderAsJson() {
    webTestClient.get()
        .uri("/api/orders/{id}", "ORD-1001")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(OrderResponse.class)
        .value(order -> {
            assertThat(order.id()).isEqualTo("ORD-1001");
            assertThat(order.status()).isEqualTo("PAID");
        });
}
~~~

Đoạn ví dụ giả định OrderResponse là record có id và status. Nếu DTO dùng getter, hãy thay assertion tương ứng.

Kiểm tra Content-Type rất quan trọng. Body có thể chứa JSON đúng nhưng header sai, khiến client chọn decoder không phù hợp. Nếu endpoint hỗ trợ nhiều media type, test từng nhánh Accept header cần thiết.

## 10. Kiểm tra Flux JSON array runtime

WebTestClient có thể decode một response JSON array thành danh sách DTO:

~~~java
@Test
void returnsOrderListAsJsonArray() {
    webTestClient.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBodyList(OrderSummary.class)
        .hasSize(2)
        .contains(
            new OrderSummary("ORD-1001", "PAID"),
            new OrderSummary("ORD-1002", "PENDING")
        );
}
~~~

Ví dụ này giả định OrderSummary có equality phù hợp, chẳng hạn record. Nếu DTO không triển khai equals/hashCode, hãy dùng consumeWith hoặc assertion từng field.

Nếu danh sách có thể lớn, không cần kiểm tra toàn bộ payload trong mọi test. Có thể kiểm tra số phần tử, một số field đại diện và thứ tự sort. Dữ liệu test nên nhỏ, xác định trước để tránh test phụ thuộc trạng thái database.

## 11. Kiểm tra response không body và Mono<Void>

Với endpoint xóa trả 204:

~~~java
@Test
void deleteOrderReturnsNoContent() {
    webTestClient.delete()
        .uri("/api/orders/{id}", "ORD-1001")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
}
~~~

Test này xác minh cả status và body rỗng. Không nên chỉ kiểm tra 204 vì một response sai có thể vẫn có body do cấu hình hoặc implementation không đúng.

Trong OpenAPI, response 204 tương ứng không nên có content. Có thể kiểm tra tài liệu riêng:

~~~java
@Test
void documentsDeleteWithoutResponseBody() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath(
            "$.paths['/api/orders/{id}'].delete.responses['204'].description"
        ).exists()
        .jsonPath(
            "$.paths['/api/orders/{id}'].delete.responses['204'].content"
        ).doesNotExist();
}
~~~

Nếu endpoint có thể trả 404 hoặc 409, hãy kiểm tra các response đó trong spec và tạo runtime test cho từng nhánh.

## 12. Kiểm tra Mono.empty() và response lỗi

Mono.empty() không tự động đồng nghĩa với 404. Nếu controller chuyển empty publisher thành ResponseEntity.notFound(), hãy kiểm tra status:

~~~java
@Test
void missingOrderReturns404() {
    webTestClient.get()
        .uri("/api/orders/{id}", "missing")
        .exchange()
        .expectStatus().isNotFound();
}
~~~

Nếu API trả ApiError body, kiểm tra Content-Type và field:

~~~java
@Test
void missingOrderReturnsDocumentedErrorBody() {
    webTestClient.get()
        .uri("/api/orders/{id}", "missing")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND")
        .jsonPath("$.message").isNotEmpty();
}
~~~

Nên kiểm tra đồng thời:

- Runtime test xác minh controller/advice thật sự trả 404.
- OpenAPI test xác minh operation có response 404.
- Schema test xác minh body lỗi được mô tả bằng đúng ApiError.
- Contract validator kiểm tra tham chiếu và cấu trúc schema.

## 13. Kiểm tra SSE bằng WebTestClient

Với endpoint SSE hữu hạn trong test, có thể xác minh media type và nội dung event:

~~~java
@Test
void streamsOrderEventsAsSse() {
    webTestClient.get()
        .uri("/api/orders/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
        .expectBody()
        .consumeWith(result -> {
            String body = new String(
                result.getResponseBody(),
                StandardCharsets.UTF_8
            );
            assertThat(body).contains("event: order-update");
            assertThat(body).contains("data:");
            assertThat(body).contains("ORD-1001");
        });
}
~~~

Để test kết thúc, service mock nên phát một số event hữu hạn rồi hoàn tất. Với stream vô hạn, không dùng expectBody để đợi toàn bộ response. Hãy lấy Flux response và kiểm tra một số event rồi cancel subscription.

Ví dụ lấy response stream:

~~~java
FluxExchangeResult<String> result = webTestClient.get()
    .uri("/api/orders/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Ví dụ này kiểm tra dữ liệu được phát và hủy subscription có timeout. Tùy decoder và cách chia chunk, một event SSE có thể được biểu diễn thành nhiều phần tử String; nếu cần đếm event chính xác, decode SSE frame hoặc dùng client chuyên biệt cho event stream.

Không để test stream vô hạn chạy mãi. Luôn đặt timeout và hủy subscription.

## 14. Kiểm tra NDJSON hoặc streaming JSON

Với NDJSON, test cần xác minh media type và cách mỗi record được phân tách. Ví dụ endpoint trả Flux<OrderEvent>:

~~~java
@Test
void streamsOrdersAsNdjson() {
    webTestClient.get()
        .uri("/api/orders/stream")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(
            MediaType.parseMediaType("application/x-ndjson")
        )
        .expectBody(String.class)
        .value(body -> {
            assertThat(body).contains("\"id\":\"ORD-1001\"");
            assertThat(body).contains("\"id\":\"ORD-1002\"");
        });
}
~~~

Test này dùng publisher hữu hạn. Với stream vô hạn, áp dụng cách tiêu thụ giới hạn và cancel như SSE.

Nếu client kỳ vọng từng JSON record trên một dòng, cần xác minh newline framing chứ không chỉ tìm chuỗi JSON bất kỳ. Có thể tách body theo newline, bỏ dòng trống và parse từng dòng bằng ObjectMapper.

## 15. Kiểm tra OpenAPI YAML

springdoc thường hỗ trợ endpoint YAML mặc định /v3/api-docs.yaml. Có thể kiểm tra:

~~~java
@Test
void exposesOpenApiYaml() {
    webTestClient.get()
        .uri("/v3/api-docs.yaml")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .value(yaml -> {
            assertThat(yaml).contains("openapi:");
            assertThat(yaml).contains("paths:");
            assertThat(yaml).contains("/api/orders:");
        });
}
~~~

Assertion này xác minh endpoint trả nội dung YAML có cấu trúc cơ bản. Để kiểm tra sâu, parse YAML bằng parser đã có trong dự án hoặc lưu thành artifact rồi chạy OpenAPI validator.

Không nên kiểm tra chỉ bằng chuỗi nếu cần xác minh nested schema, $ref hoặc security. String assertion phù hợp cho smoke test; parser/validator phù hợp cho contract test.

## 16. Kiểm tra grouped OpenAPI documents

Nếu dùng GroupedOpenApi, mỗi group tạo một tài liệu riêng. Ví dụ group public và internal:

~~~java
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
~~~

Các endpoint tài liệu thường có dạng:

~~~text
/v3/api-docs/public
/v3/api-docs/internal
~~~

Test từng group:

~~~java
@Test
void exposesPublicGroup() {
    webTestClient.get()
        .uri("/v3/api-docs/public")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths['/api/public/catalog'].get").exists()
        .jsonPath("$.paths['/api/internal/reports'].get").doesNotExist();
}

@Test
void exposesInternalGroup() {
    webTestClient.get()
        .uri("/v3/api-docs/internal")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths['/api/internal/reports'].get").exists();
}
~~~

Tên group và path phải khớp cấu hình thật. Mỗi group có thể có customizer, security hoặc component riêng; test default document không thay thế test group.

## 17. Kiểm tra Swagger UI config endpoint

Swagger UI thường tải cấu hình qua /v3/api-docs/swagger-config. Endpoint này có thể chứa URL tài liệu, danh sách group, OAuth redirect URL và các tùy chọn UI.

Smoke test:

~~~java
@Test
void exposesSwaggerUiConfiguration() {
    webTestClient.get()
        .uri("/v3/api-docs/swagger-config")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.url").exists();
}
~~~

Nếu ứng dụng dùng nhiều group, cấu hình có thể sử dụng urls thay cho một url đơn. Khi đó hãy kiểm tra đúng cấu trúc mà phiên bản springdoc tạo ra.

Không hard-code toàn bộ JSON config nếu nhiều trường được springdoc tự sinh và có thể thay đổi giữa các phiên bản. Chỉ kiểm tra các trường mà ứng dụng cam kết, chẳng hạn URL spec hoặc danh sách group cần hiển thị.

## 18. Kiểm tra Swagger UI assets và redirect

Đường dẫn Swagger UI mặc định thường gồm /swagger-ui.html và /swagger-ui/index.html. URL đầu có thể redirect tới trang tài nguyên giao diện.

Có thể kiểm tra redirect:

~~~java
@Test
void redirectsSwaggerUiEntryPoint() {
    webTestClient.get()
        .uri("/swagger-ui.html")
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectHeader().exists(HttpHeaders.LOCATION);
}
~~~

Và kiểm tra trang UI:

~~~java
@Test
void servesSwaggerUiIndex() {
    webTestClient.get()
        .uri("/swagger-ui/index.html")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.TEXT_HTML);
}
~~~

Đường dẫn, redirect và Content-Type có thể thay đổi khi cấu hình springdoc.swagger-ui.path, context path hoặc reverse proxy. Nếu chỉ cần xác minh OpenAPI contract, không nhất thiết phải test toàn bộ JavaScript/CSS; có thể dùng browser smoke test ở pipeline UI riêng.

## 19. Kiểm tra functional routes với RouterFunction

Spring WebFlux hỗ trợ functional endpoints thông qua RouterFunction và HandlerFunction. springdoc có thể mô tả route bằng @RouterOperation hoặc @RouterOperations.

Ví dụ route:

~~~java
@Bean
@RouterOperation(
    path = "/api/health",
    method = RequestMethod.GET,
    beanClass = HealthHandler.class,
    beanMethod = "health",
    operation = @Operation(
        operationId = "getHealth",
        summary = "Kiểm tra trạng thái dịch vụ"
    )
)
RouterFunction<ServerResponse> healthRoutes(HealthHandler handler) {
    return RouterFunctions.route()
        .GET("/api/health", handler::health)
        .build();
}
~~~

Handler:

~~~java
@Component
class HealthHandler {

    Mono<ServerResponse> health(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("status", "UP"));
    }
}
~~~

Test runtime:

~~~java
@Test
void functionalHealthRouteReturnsJson() {
    webTestClient.get()
        .uri("/api/health")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.status").isEqualTo("UP");
}
~~~

Test tài liệu:

~~~java
@Test
void documentsFunctionalHealthRoute() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.paths['/api/health'].get").exists();
}
~~~

Hai test kiểm tra hai kết quả khác nhau. Nếu route runtime hoạt động nhưng OpenAPI không có path, hãy kiểm tra @RouterOperation, beanClass, beanMethod và metadata operation. Nếu tài liệu có path nhưng request 404, kiểm tra RouterFunction thực tế và path mapping.

## 20. Dùng WebTestClient bindToRouterFunction cho test cô lập

Khi chỉ muốn kiểm tra một RouterFunction, có thể bind WebTestClient trực tiếp:

~~~java
@Test
void testsRouterFunctionWithoutStartingServer() {
    RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
            .GET("/api/health", request ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of("status", "UP"))
            )
            .build();

    WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

    client.get()
        .uri("/api/health")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("UP");
}
~~~

Cách này nhanh và hữu ích cho route logic độc lập. Tuy nhiên, nó không kiểm tra springdoc quét toàn application context, không kiểm tra SecurityFilterChain đầy đủ và không xác minh tài liệu OpenAPI được tạo từ cấu hình toàn ứng dụng.

Để kiểm tra tài liệu của functional routes, dùng integration test với application context và gọi /v3/api-docs.

## 21. Phân biệt @WebFluxTest và @SpringBootTest

Hai annotation phục vụ phạm vi test khác nhau:

| Annotation | Phạm vi | Phù hợp |
|---|---|---|
| @WebFluxTest | Slice tập trung vào WebFlux controller và thành phần web được chọn | Kiểm tra binding, validation, response của controller |
| @SpringBootTest | Nạp application context theo cấu hình ứng dụng | Kiểm tra springdoc, group, customizer, security và tích hợp |
| WebTestClient.bindToRouterFunction | Một RouterFunction cụ thể | Kiểm tra route hàm độc lập |
| RANDOM_PORT | Embedded server thật trên cổng ngẫu nhiên | Kiểm tra HTTP stack gần runtime hơn |

@WebFluxTest thường không nạp mọi bean nghiệp vụ và mọi cấu hình OpenAPI. Có thể dùng @Import để thêm cấu hình cần thiết, nhưng nếu mục tiêu là kiểm tra tài liệu sinh ra từ toàn bộ ứng dụng thì @SpringBootTest thường rõ ràng hơn.

Không dùng full context cho mọi test nhỏ. Chọn phạm vi nhỏ để kiểm tra logic nhanh, sau đó có một số integration test tập trung xác minh tài liệu và cấu hình cuối cùng.

## 22. Kiểm tra response header và content negotiation

WebFlux có thể chọn representation dựa trên Accept header và produces. Test cần xác minh Content-Type đúng:

~~~java
@Test
void returnsJsonWhenClientAcceptsJson() {
    webTestClient.get()
        .uri("/api/orders")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
}
~~~

Nếu endpoint hỗ trợ nhiều media type, test từng lựa chọn:

- application/json.
- text/event-stream.
- application/x-ndjson.
- application/pdf hoặc media type khác nếu endpoint có.

Kiểm tra thêm header như Cache-Control, ETag, Location hoặc Retry-After khi chúng là một phần hợp đồng. Trong OpenAPI, header cần được mô tả ở response tương ứng; trong runtime, test cần xác minh nó thực sự có mặt.

Không chỉ kiểm tra body. Một body đúng nhưng Content-Type hoặc header sai vẫn có thể khiến client không xử lý được.

## 23. Kiểm tra security cho tài liệu và API

Nếu OpenAPI document được bảo vệ, test cần xác minh quyền truy cập riêng:

~~~java
@Test
void deniesAnonymousOpenApiRequest() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

Nếu người có quyền DOCS_READER được phép tải spec, test với credential tương ứng:

~~~java
@Test
void allowsDocsReaderToFetchOpenApi() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .headers(headers -> headers.setBasicAuth(
            "docs-reader",
            "test-password"
        ))
        .exchange()
        .expectStatus().isOk();
}
~~~

API runtime cần test độc lập với bearer token và scope. Có thể dùng Spring Security Test để tạo JWT authentication trong test hoặc chạy integration test với token do test identity provider cấp.

Đừng dùng một assertion cho /v3/api-docs để kết luận /api/** đã được bảo vệ. Tài liệu và API là hai phạm vi request riêng.

Nếu test dùng jwt() post-processor, lưu ý helper tạo Authentication giả lập; nó không xác minh chữ ký JWT thật, issuer hoặc khóa ký. Những phần đó cần test decoder/resource server riêng.

## 24. Kiểm tra tham chiếu schema và response

Một OpenAPI document có thể chứa nhiều $ref. Test nên kiểm tra component mà operation dùng tới tồn tại:

~~~java
@Test
void exposesSharedErrorSchema() {
    webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.components.schemas.ApiError").exists()
        .jsonPath(
            "$.paths['/api/orders/{id}'].get.responses['404']"
        ).exists();
}
~~~

Nếu response 404 tham chiếu ApiError, kiểm tra schema ref theo cấu trúc spec thực tế. Không bắt buộc mọi schema phải dùng $ref; inline schema cũng hợp lệ.

Với component dùng chung, nên kiểm tra:

- Component có tồn tại.
- $ref trỏ đúng nhóm và tên.
- Response có đúng content type.
- Schema có field bắt buộc.
- Enum và format đúng.
- Không có component bị ghi đè ngoài ý muốn.

Dùng OpenAPI validator để phát hiện tham chiếu hỏng và lỗi cấu trúc. Test JSONPath phù hợp với assertion nghiệp vụ cụ thể; validator phù hợp với kiểm tra toàn tài liệu.

## 25. Dùng ObjectMapper để kiểm tra OpenAPI JSON sâu hơn

Khi nhiều assertion cần đọc cùng một tài liệu, có thể nhận body thành String hoặc JsonNode:

~~~java
@Test
void inspectsOpenApiDocumentAsJsonTree() throws Exception {
    EntityExchangeResult<byte[]> result = webTestClient.get()
        .uri("/v3/api-docs")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .returnResult();

    JsonNode document = objectMapper.readTree(result.getResponseBody());

    assertThat(document.path("openapi").asText()).startsWith("3.");
    assertThat(document.path("paths")
        .path("/api/orders")
        .path("get")
        .path("responses")
        .path("200")
        .isMissingNode()).isFalse();
}
~~~

Cách này hữu ích khi cần kiểm tra nhiều nhánh hoặc duyệt toàn bộ components. Dùng JsonNode giúp tránh viết JSONPath quá dài lặp lại.

Nếu muốn kiểm tra tất cả $ref, có thể duyệt cây JSON và thu thập trường có tên $ref, sau đó kiểm tra từng JSON Pointer. Một OpenAPI validator chuyên dụng thường đáng tin cậy hơn việc tự viết parser đầy đủ cho mọi dạng reference.

## 26. Kiểm tra OpenAPI bằng validator trong CI

Ngoài test ứng dụng, có thể xuất OpenAPI JSON thành artifact rồi chạy validator:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o build/openapi.json
openapi-generator-cli validate -i build/openapi.json
~~~

Hoặc dùng công cụ lint OpenAPI đã được nhóm chuẩn hóa. Validator có thể phát hiện:

- Cấu trúc OpenAPI không hợp lệ.
- $ref không giải quyết được.
- Response thiếu description.
- Parameter sai vị trí hoặc schema.
- Security scheme được tham chiếu nhưng chưa khai báo.
- Schema composition hoặc media type sai cấu trúc.

Lint rule có thể bổ sung quy ước của nhóm như operationId bắt buộc, error response chuẩn, tag naming và version policy.

Validator không thể tự chứng minh runtime response khớp schema. Vẫn cần WebTestClient test các endpoint quan trọng và có thể bổ sung contract test so sánh payload thực với schema.

## 27. Lưu snapshot và review diff của tài liệu

Với API quan trọng, có thể lưu OpenAPI JSON được sinh ra làm build artifact hoặc snapshot. Khi thay đổi controller, DTO, annotation, customizer hoặc security configuration, tạo tài liệu mới và review diff.

Các thay đổi cần chú ý:

- Path hoặc HTTP method bị xóa.
- operationId thay đổi.
- Request parameter hoặc required flag thay đổi.
- Response status bị xóa hoặc đổi.
- Schema field đổi type, format, enum hoặc nullable.
- Security requirement thay đổi.
- Media type thay đổi.
- Component bị đổi tên hoặc $ref thay đổi.

Không phải mọi diff đều là breaking change, nhưng mỗi thay đổi cần được xem xét trong bối cảnh client sử dụng. Có thể tích hợp công cụ so sánh OpenAPI để phân loại breaking changes trong CI.

## 28. Tránh test không ổn định

Một số nguyên nhân làm test WebFlux/OpenAPI chập chờn:

- Dữ liệu test phụ thuộc database dùng chung.
- Flux phát dữ liệu vô hạn nhưng test đợi hoàn tất.
- Timeout quá ngắn khi khởi động application context.
- Test phụ thuộc identity provider hoặc network bên ngoài.
- Group hoặc bean discovery khác nhau giữa profile.
- Swagger UI config thay đổi theo môi trường.
- Assertion dựa vào thứ tự property JSON không được bảo đảm.
- Assertion dựa vào tên component tự sinh không ổn định.

Cách giảm flakiness:

- Dùng dữ liệu xác định và cô lập.
- Dùng publisher hữu hạn trong test body thông thường.
- Với stream vô hạn, đặt timeout và cancel.
- Dùng test profile và mock service ngoài.
- Chỉ assert các field hợp đồng cần ổn định.
- Dùng @Schema(name = "...") hoặc cấu hình rõ nếu tên component là hợp đồng.
- Tách smoke test UI khỏi test schema nếu không cần tải toàn bộ assets.

## 29. Quy trình test gợi ý cho một thay đổi API Reactive

Khi thêm hoặc sửa một endpoint:

1. Viết unit/slice test cho handler hoặc controller.
2. Kiểm tra status, body và Content-Type bằng WebTestClient.
3. Kiểm tra Mono, Flux, empty publisher hoặc error path phù hợp.
4. Kiểm tra OpenAPI JSON có path, operation và response schema.
5. Nếu endpoint là functional route, kiểm tra cả runtime route và metadata @RouterOperation.
6. Nếu có SSE/NDJSON, xác minh media type và framing.
7. Nếu dùng grouped docs, kiểm tra đúng group.
8. Chạy OpenAPI validator/linter.
9. Review diff của spec nếu hợp đồng đã phát hành.
10. Lưu test result và OpenAPI artifact trong CI.

Không cần tạo test cho mọi tổ hợp lý thuyết. Ưu tiên nhánh nghiệp vụ có ý nghĩa với client và những phần hợp đồng vừa thay đổi.

## 30. Checklist kiểm tra tài liệu Reactive

- [ ] WebTestClient được cấu hình đúng với WebFlux test context.
- [ ] Có integration test gọi /v3/api-docs.
- [ ] OpenAPI metadata và paths được công bố.
- [ ] OperationId ổn định nếu client generator phụ thuộc vào nó.
- [ ] Mono response được mô tả bằng schema của payload.
- [ ] Flux JSON được mô tả bằng array schema.
- [ ] SSE dùng text/event-stream.
- [ ] NDJSON dùng media type và framing đã thống nhất.
- [ ] Mono<Void> và response 204 không có body.
- [ ] Mono.empty() được ánh xạ status theo nghiệp vụ.
- [ ] Error response và schema lỗi khớp runtime.
- [ ] Status, headers và Content-Type được test.
- [ ] YAML endpoint và grouped documents được kiểm tra nếu dùng.
- [ ] Swagger UI config được kiểm tra khi cấu hình UI là một phần triển khai.
- [ ] RouterFunction được test cả runtime lẫn OpenAPI metadata.
- [ ] Security của docs và API được test độc lập.
- [ ] Stream test có timeout và cancel.
- [ ] OpenAPI validator chạy trong CI.
- [ ] Snapshot/diff spec được review khi có thay đổi hợp đồng.

## 31. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework – WebFlux functional endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Project Reactor – StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [OpenAPI Generator – Validate](https://openapi-generator.tech/docs/usage/)

WebTestClient giúp kiểm tra HTTP response của WebFlux, còn test /v3/api-docs xác minh tài liệu springdoc sinh ra. Hãy kiểm tra cả hai: publisher reactive phải được serialize đúng theo media type, và OpenAPI phải mô tả đúng path, schema, status, security cùng response. Với RouterFunction, grouped docs và stream SSE/NDJSON, hãy tạo test riêng cho đúng phạm vi để phát hiện sai lệch trước khi phát hành.
