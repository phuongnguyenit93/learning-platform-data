# Giới hạn package, path, media type và header được đưa vào tài liệu

Trong một ứng dụng Spring Boot, không phải controller nào cũng thuộc phạm vi công bố API cho cùng một nhóm người dùng. Ứng dụng có thể chứa endpoint công khai, endpoint quản trị, API nội bộ, endpoint phục vụ giao diện web và các route chỉ dùng cho health check. Nếu để springdoc quét toàn bộ endpoint theo mặc định, tài liệu OpenAPI có thể chứa nhiều operation không dành cho consumer đang xem tài liệu.

springdoc-openapi cung cấp các bộ lọc để giới hạn operation được đưa vào đặc tả theo package Java, URL path, media type request/response và điều kiện header của mapping. Các bộ lọc này tác động đến **tài liệu được sinh**, không thay đổi route thực tế và không thay thế Spring Security. Cần hiểu rõ ranh giới đó để tránh dùng việc ẩn endpoint trong Swagger UI như một biện pháp bảo mật.

## 1. Bộ lọc được áp dụng ở giai đoạn nào?

Luồng đơn giản hóa khi sinh tài liệu:

1. Spring Boot khởi tạo các Spring-managed controller và request mapping.
2. springdoc thu thập các endpoint có thể mô tả.
3. Bộ lọc kiểm tra package, path, consumes, produces và header condition.
4. Những operation thỏa điều kiện được đưa vào OpenAPI document.
5. Swagger UI hoặc consumer khác đọc document được sinh.

Ví dụ, một ứng dụng có các controller sau:

| Controller | Package | Path | Mục đích |
|---|---|---|---|
| `PublicOrderController` | `com.acme.api.publicapi` | `/api/v1/orders/**` | API cho đối tác |
| `AdminOrderController` | `com.acme.api.admin` | `/admin/orders/**` | API quản trị |
| `InternalHealthController` | `com.acme.internal.health` | `/internal/health` | Kiểm tra nội bộ |
| `WebPageController` | `com.acme.web` | `/pages/**` | Trang HTML, không phải REST API công khai |

Tài liệu dành cho đối tác chỉ nên chứa nhóm endpoint thứ nhất. Có thể giới hạn package và path để tránh đưa các controller còn lại vào document. Nếu ứng dụng cần nhiều tài liệu độc lập, hãy tạo các group thay vì cố gắng dùng một cấu hình toàn cục cho mọi consumer.

## 2. Các thuộc tính lọc phổ biến

Các thuộc tính cốt lõi dùng prefix `springdoc`:

| Thuộc tính | Mục đích | Giá trị mặc định được tài liệu springdoc công bố |
|---|---|---|
| `springdoc.packages-to-scan` | Chỉ định package được quét | `*` |
| `springdoc.packages-to-exclude` | Loại package khỏi phạm vi quét | Không đặt |
| `springdoc.paths-to-match` | Chỉ định path cần đưa vào document | `/*` |
| `springdoc.paths-to-exclude` | Loại path khỏi document | Không đặt |
| `springdoc.consumes-to-match` | Lọc theo media type request được mapping chấp nhận | `/*` |
| `springdoc.produces-to-match` | Lọc theo media type response được mapping công bố | `/*` |
| `springdoc.headers-to-match` | Lọc theo header condition của request mapping | `/*` |

Các bộ lọc tương tự cũng có thể cấu hình riêng cho từng API group dưới `springdoc.group-configs`. Trong cùng một nhóm, nhiều giá trị trong một danh sách cho phép khai báo nhiều package, path hoặc media type cần khớp. Khi kết hợp nhiều loại điều kiện, endpoint cần thỏa phạm vi package/path và các điều kiện mapping tương ứng.

Lưu ý: `springdoc.default-consumes-media-type` và `springdoc.default-produces-media-type` là thuộc tính đặt media type mặc định cho mô tả, không phải thuộc tính chọn endpoint. Không nhầm chúng với `consumes-to-match` và `produces-to-match`.

## 3. Giới hạn controller theo package

`packages-to-scan` giới hạn package chứa các controller Spring được springdoc xem xét. Cách này hữu ích khi tổ chức source code theo bounded context hoặc theo nhóm API.

Ví dụ chỉ lấy controller thuộc package API công khai:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.publicapi
    - com.acme.api.shared
~~~

Có thể loại package nội bộ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api
  packages-to-exclude:
    - com.acme.api.internal
    - com.acme.api.maintenance
~~~

### Chọn package đủ rộng nhưng không quá rộng

Giả sử cấu trúc source:

~~~text
com.acme
├── api
│   ├── publicapi
│   │   ├── order
│   │   └── customer
│   ├── admin
│   └── internal
├── web
└── infrastructure
~~~

Nếu muốn quét cả `order` và `customer`, có thể chọn package cha `com.acme.api.publicapi`. Nếu chọn `com.acme`, phạm vi quá rộng và có thể đưa cả controller quản trị, nội bộ hoặc web vào tài liệu. Nên chọn package ở ranh giới API mà consumer thực sự cần.

`packages-to-exclude` hữu ích khi package gốc có nhiều controller nhưng chỉ một vài nhánh không được công bố. Tuy nhiên, cấu trúc package rõ ràng thường dễ bảo trì hơn một danh sách loại trừ dài.

## 4. Giới hạn endpoint theo path

`paths-to-match` lọc theo URL path được khai báo trên request mapping. Ví dụ chỉ công bố API phiên bản 1:

~~~yaml
springdoc:
  paths-to-match:
    - /api/v1/**
~~~

Có thể chỉ định nhiều vùng path:

~~~yaml
springdoc:
  paths-to-match:
    - /api/v1/orders/**
    - /api/v1/customers/**
  paths-to-exclude:
    - /api/v1/orders/internal/**
    - /api/v1/customers/debug/**
~~~

Các mẫu như `/api/v1/**` giúp bao gồm endpoint ở nhiều cấp con; `/api/v1/orders/*` thường chỉ phù hợp với một cấp path con. Khi thiết kế mẫu, hãy dùng một path đại diện ở cấp sâu nhất của ứng dụng và xác minh kết quả trong `/v3/api-docs`.

### Kết hợp package và path

Package và path giải quyết hai câu hỏi khác nhau:

- Package: controller thuộc vùng mã nguồn nào?
- Path: operation công bố URL nào?

Ví dụ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.publicapi
  paths-to-match:
    - /api/v1/**
  paths-to-exclude:
    - /api/v1/internal/**
~~~

Một controller chỉ nằm trong package được quét nhưng khai báo path ngoài `/api/v1/**` sẽ không được đưa vào document. Tương tự, một path phù hợp nhưng controller nằm ngoài package được chọn cũng không thuộc phạm vi. Đây là cách kết hợp hữu ích để giới hạn tài liệu theo cả cấu trúc mã nguồn và hợp đồng URL.

## 5. Lọc theo media type request: consumes

`consumes` mô tả loại nội dung client gửi lên mà endpoint chấp nhận, thường tương ứng với `Content-Type` của request. Trong Spring MVC/WebFlux, có thể khai báo điều kiện này ngay trên mapping:

~~~java
@PostMapping(
    path = "/api/v1/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Nếu chỉ muốn đưa các endpoint nhận JSON hoặc multipart vào tài liệu:

~~~yaml
springdoc:
  consumes-to-match:
    - application/json
    - multipart/form-data
~~~

Ví dụ endpoint upload:

~~~java
@PostMapping(
    path = "/api/v1/files",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public FileResponse upload(@RequestPart("file") MultipartFile file) {
    return fileService.upload(file);
}
~~~

Khi consumer cần tài liệu upload, `multipart/form-data` phải được giữ trong bộ lọc. Nếu chỉ đặt `application/json`, endpoint upload có thể bị loại khỏi document theo điều kiện consumes.

Không khai báo `consumes-to-match` quá hẹp nếu hệ thống có endpoint nhận XML, form data, binary hoặc nhiều định dạng request khác nhau. Nếu không có nhu cầu lọc theo Content-Type, giữ mặc định để tránh vô tình bỏ sót operation.

## 6. Lọc theo media type response: produces

`produces` mô tả loại nội dung response mà endpoint có thể trả về, thường liên quan đến content negotiation qua header `Accept`.

Ví dụ endpoint REST trả JSON:

~~~java
@GetMapping(
    path = "/api/v1/orders/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse getOrder(@PathVariable UUID id) {
    return orderService.findById(id);
}
~~~

Ví dụ endpoint phát sự kiện theo Server-Sent Events:

~~~java
@GetMapping(
    path = "/api/v1/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<OrderEvent> streamEvents() {
    return orderService.streamEvents();
}
~~~

Nếu chỉ muốn document cho response JSON:

~~~yaml
springdoc:
  produces-to-match:
    - application/json
    - application/problem+json
~~~

Nếu muốn thêm API streaming, hãy đưa media type tương ứng vào danh sách:

~~~yaml
springdoc:
  produces-to-match:
    - application/json
    - application/problem+json
    - text/event-stream
~~~

`consumes` và `produces` không thể thay thế cho nhau. Một endpoint có thể nhận JSON nhưng trả PDF, hoặc nhận multipart nhưng trả JSON. Hãy chọn media type theo chiều request và response thực tế.

## 7. Lọc theo điều kiện header của request mapping

Spring hỗ trợ điều kiện header trên `@RequestMapping`, `@GetMapping`, `@PostMapping` và các annotation mapping liên quan. Ví dụ:

~~~java
@GetMapping(
    path = "/api/v1/legacy/orders",
    headers = "X-API-Version=v1",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public List<OrderResponse> legacyOrders() {
    return orderService.findLegacyOrders();
}
~~~

Điều kiện `headers` ở đây yêu cầu request có header `X-API-Version` với giá trị `v1`. Có thể lọc những mapping có điều kiện header tương ứng:

~~~yaml
springdoc:
  headers-to-match:
    - X-API-Version=v1
~~~

`headers-to-match` phục vụ việc chọn request mapping có khai báo điều kiện header. Nó không có nghĩa springdoc tự thêm một header parameter cho mọi operation, cũng không có nghĩa mọi request runtime đều bị ép phải có header này.

### Phân biệt header condition và header parameter

Hai cách khai báo sau có mục đích khác nhau:

~~~java
// Header là điều kiện để Spring chọn handler method
@GetMapping(path = "/api/v1/orders", headers = "X-API-Version=v1")
public List<OrderResponse> listV1() {
    return orderService.findAll();
}

// Header là dữ liệu đầu vào của operation
@GetMapping(path = "/api/v1/orders/search")
public List<OrderResponse> search(
        @RequestHeader("X-Correlation-Id") String correlationId) {
    return orderService.search(correlationId);
}
~~~

Nếu cần thể hiện header đầu vào trong OpenAPI, dùng `@RequestHeader` hoặc annotation `@Parameter(in = ParameterIn.HEADER)`. Nếu cần bảo vệ endpoint bằng Bearer token/API key, nên mô tả security scheme của OpenAPI thay vì coi header xác thực như một điều kiện lọc tài liệu.

Đối với `Accept` và `Content-Type`, ưu tiên dùng `produces` và `consumes` thay vì viết điều kiện trong thuộc tính `headers`, vì hai thuộc tính chuyên biệt này thể hiện đúng ý nghĩa content negotiation.

## 8. Ví dụ cấu hình toàn cục trong application.yml

Ví dụ dưới đây tạo một document chỉ chứa API công khai phiên bản 1, loại các path nội bộ và giữ các định dạng JSON/multipart:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.publicapi
  packages-to-exclude:
    - com.acme.api.publicapi.internal
  paths-to-match:
    - /api/v1/**
  paths-to-exclude:
    - /api/v1/internal/**
    - /api/v1/debug/**
  consumes-to-match:
    - application/json
    - multipart/form-data
  produces-to-match:
    - application/json
    - application/problem+json
~~~

Không thêm `headers-to-match` vào ví dụ này vì các API công khai thông thường không nhất thiết khai báo header condition trên request mapping. Nếu thêm `headers-to-match` mà các controller không có điều kiện header phù hợp, document có thể không còn operation như mong muốn. Chỉ cấu hình bộ lọc này khi thực sự phân nhánh route theo header.

Ví dụ cấu hình riêng header condition:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.versioned
  paths-to-match:
    - /api/**
  headers-to-match:
    - X-API-Version=v2
~~~

Các thuộc tính toàn cục tác động đến document mặc định. Nếu một ứng dụng cần tài liệu cho nhiều consumer có phạm vi khác nhau, hãy dùng group-specific filters ở phần tiếp theo.

## 9. Tạo nhiều OpenAPI group với bộ lọc riêng

Một ứng dụng có thể công bố nhiều OpenAPI document. Ví dụ:

- `partner-v1`: API đối tác, chỉ có path phiên bản 1.
- `admin`: API quản trị, chỉ có controller trong package admin.
- `partner-v2`: API phiên bản 2, chỉ nhận các route có header version tương ứng.

Mỗi group có tên duy nhất và mặc định được truy cập qua `/v3/api-docs/{groupName}`. Có thể cấu hình bằng `GroupedOpenApi` trong Java:

~~~java
@Configuration
public class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi partnerV1Api() {
        return GroupedOpenApi.builder()
            .group("partner-v1")
            .packagesToScan("com.acme.api.partner")
            .pathsToMatch("/api/v1/**")
            .pathsToExclude("/api/v1/internal/**")
            .producesToMatch(
                MediaType.APPLICATION_JSON_VALUE,
                "application/problem+json"
            )
            .consumesToMatch(
                MediaType.APPLICATION_JSON_VALUE,
                MediaType.MULTIPART_FORM_DATA_VALUE
            )
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .packagesToScan("com.acme.api.admin")
            .pathsToMatch("/admin/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerV2Api() {
        return GroupedOpenApi.builder()
            .group("partner-v2")
            .packagesToScan("com.acme.api.versioned")
            .pathsToMatch("/api/**")
            .headersToMatch("X-API-Version=v2")
            .build();
    }
}
~~~

Các method `packagesToScan`, `packagesToExclude`, `pathsToMatch`, `pathsToExclude`, `consumesToMatch`, `producesToMatch` và `headersToMatch` tương ứng với các bộ lọc đã trình bày. Hãy dùng package/path thực tế của dự án và bảo đảm mapping có điều kiện header nếu group dùng `headersToMatch`.

### Cấu hình group bằng application.yml

Nếu không muốn khai báo bean cho từng group, có thể dùng `springdoc.group-configs`:

~~~yaml
springdoc:
  group-configs:
    - group: partner-v1
      display-name: Partner API v1
      packages-to-scan:
        - com.acme.api.partner
      paths-to-match:
        - /api/v1/**
      paths-to-exclude:
        - /api/v1/internal/**
      consumes-to-match:
        - application/json
        - multipart/form-data
      produces-to-match:
        - application/json
        - application/problem+json

    - group: admin
      display-name: Admin API
      packages-to-scan:
        - com.acme.api.admin
      paths-to-match:
        - /admin/**

    - group: partner-v2
      display-name: Partner API v2
      packages-to-scan:
        - com.acme.api.versioned
      paths-to-match:
        - /api/**
      headers-to-match:
        - X-API-Version=v2
~~~

Các document có thể được tải riêng:

| Group | URL mặc định |
|---|---|
| `partner-v1` | `/v3/api-docs/partner-v1` |
| `admin` | `/v3/api-docs/admin` |
| `partner-v2` | `/v3/api-docs/partner-v2` |

Chọn một cách quản lý group nhất quán. Không tạo cùng một group name bằng nhiều cấu hình không cần thiết, vì việc trộn bean `GroupedOpenApi` với group cấu hình từ property có thể khiến người bảo trì khó xác định nguồn của từng document.

## 10. Lọc tài liệu không phải là bảo vệ endpoint

Đây là nguyên tắc quan trọng nhất khi vận hành:

- `packages-to-scan`, `paths-to-match` và các bộ lọc khác chỉ quyết định operation nào xuất hiện trong OpenAPI.
- Chúng không xóa controller khỏi Spring application context.
- Chúng không ngăn người dùng gọi URL trực tiếp.
- Chúng không cấp quyền hoặc thu hồi quyền truy cập.
- Chúng không thay thế Spring Security, API gateway policy, network policy hay kiểm tra quyền trong service.

Ví dụ, nếu `/admin/users` bị loại khỏi tài liệu public nhưng không được bảo vệ bằng Spring Security, người dùng vẫn có thể gọi URL đó nếu biết địa chỉ và endpoint cho phép truy cập.

Để bảo vệ endpoint, cấu hình authorization riêng:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/v1/**").authenticated()
            .anyRequest().permitAll()
        )
        .build();
}
~~~

Đây là ví dụ cho ứng dụng Servlet/Spring MVC; ứng dụng WebFlux cần cấu hình reactive security tương ứng. Chính sách bảo mật phải được kiểm thử độc lập với kết quả OpenAPI.

Nếu chỉ muốn ẩn một controller hoặc operation khỏi tài liệu, có thể dùng `@Hidden` trên controller/method hoặc `@Operation(hidden = true)` trên operation. Cách này cũng chỉ tác động đến mô tả OpenAPI, không làm endpoint biến mất khỏi runtime.

## 11. Kiểm tra kết quả lọc trong OpenAPI document

Sau khi cấu hình, không nên chỉ nhìn Swagger UI. Hãy kiểm tra trực tiếp JSON OpenAPI để biết operation nào được sinh.

Lấy document mặc định:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Lấy document của group:

~~~bash
curl -s http://localhost:8080/v3/api-docs/partner-v1
~~~

Nếu có `jq`, có thể liệt kê các path:

~~~bash
curl -s http://localhost:8080/v3/api-docs/partner-v1 | jq -r '.paths | keys[]'
~~~

Kết quả mong muốn với group `partner-v1` có thể chỉ gồm:

~~~text
/api/v1/orders
/api/v1/orders/{id}
/api/v1/files
~~~

Các path `/admin/**`, `/api/v1/internal/**` hoặc `/internal/health` không nên xuất hiện trong document public nếu đã nằm ngoài phạm vi lọc.

### Kiểm thử bằng MockMvc

Có thể tự động kiểm tra contract bằng integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiFilteringTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void partnerDocumentContainsOnlyPartnerPaths() throws Exception {
        mockMvc.perform(get("/v3/api-docs/partner-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/v1/orders']").exists())
            .andExpect(jsonPath("$.paths['/admin/users']").doesNotExist())
            .andExpect(jsonPath("$.paths['/api/v1/internal/debug']").doesNotExist());
    }
}
~~~

Đây là ví dụ minh họa; thay path và group theo cấu hình thực tế. Với ứng dụng WebFlux, có thể dùng `WebTestClient` để kiểm tra cùng các assertion trên.

Ngoài việc kiểm tra path tồn tại/không tồn tại, nên xác minh:

1. Operation có đúng HTTP method không?
2. `requestBody.content` có đúng media type không?
3. `responses.*.content` có đúng media type không?
4. Header parameter cần thiết có được mô tả không?
5. `operationId` có duy nhất và đúng quy ước không?
6. Schema được tham chiếu trong `components.schemas` có còn đầy đủ không?

## 12. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Document không có endpoint nào | `packages-to-scan` hoặc `paths-to-match` quá hẹp; package/path không khớp controller thực tế | Kiểm tra package khai báo, mapping path và tạm bỏ từng bộ lọc để khoanh vùng |
| Một số endpoint biến mất sau khi thêm media filter | `consumes-to-match` hoặc `produces-to-match` không bao gồm media type của mapping | Thêm đúng media type như JSON, XML, multipart hoặc SSE |
| API upload biến mất | Chỉ lọc `application/json` nhưng endpoint nhận `multipart/form-data` | Bổ sung multipart vào `consumes-to-match` |
| API SSE biến mất | `produces-to-match` không bao gồm `text/event-stream` | Bổ sung media type streaming nếu cần công bố |
| Group theo header bị rỗng | Mapping không khai báo điều kiện `headers` tương ứng hoặc biểu thức header không khớp | Kiểm tra `@RequestMapping(headers = ...)` và `headers-to-match` |
| Header không xuất hiện thành parameter trong Swagger UI | Nhầm `headers-to-match` với khai báo header parameter | Dùng `@RequestHeader` hoặc `@Parameter(in = HEADER)` để mô tả input |
| Endpoint bị ẩn nhưng vẫn gọi được | Bộ lọc chỉ tác động tài liệu, không phải authorization | Bảo vệ endpoint bằng Spring Security/API gateway |
| Swagger UI hiển thị sai group | Dùng nhầm URL document hoặc group name | Kiểm tra `/v3/api-docs/{group}` và cấu hình Swagger UI |
| Path mới không xuất hiện sau khi đổi cấu hình | Nhầm path của controller với context path/proxy prefix hoặc document cache | Kiểm tra path mapping thực tế, URL public và trạng thái cache |
| Hai method cùng path và HTTP method chỉ tạo một operation | OpenAPI biểu diễn một operation cho mỗi cặp path + HTTP method; overload theo consumes không tạo hai operation độc lập | Mô tả các media type trong cùng operation hoặc tách thành group/URL phù hợp |
| Cấu hình global ảnh hưởng cả tài liệu khác | Bộ lọc được đặt ở cấp `springdoc` thay vì trong group | Chuyển điều kiện riêng vào `springdoc.group-configs` hoặc `GroupedOpenApi` |

## 13. Quy trình thiết kế bộ lọc có thể bảo trì

Khi thiết lập phạm vi OpenAPI cho một dự án lớn, thực hiện theo trình tự:

1. Liệt kê consumer của tài liệu: public client, partner, admin, internal service hay developer portal.
2. Chọn ranh giới package phản ánh nhóm controller cần công bố.
3. Chọn path theo version hoặc domain API; thêm exclude cho debug/internal path nếu cần.
4. Chỉ đặt `consumes-to-match` và `produces-to-match` khi có yêu cầu lọc media type rõ ràng.
5. Chỉ đặt `headers-to-match` khi request mapping thực sự phân nhánh theo header.
6. Tạo group riêng nếu các consumer cần phạm vi endpoint khác nhau.
7. Kiểm tra JSON OpenAPI trực tiếp và viết integration test cho path được giữ/loại.
8. Kiểm tra Spring Security riêng để bảo đảm endpoint nội bộ không bị truy cập trái phép.
9. Đưa thay đổi bộ lọc vào review như một thay đổi contract API, vì operation biến mất khỏi document có thể ảnh hưởng code generator và consumer.

Một cấu hình tốt nên rõ ràng, ngắn gọn và phản ánh ranh giới API thực tế. Không nên thêm tất cả bộ lọc chỉ vì chúng tồn tại; bộ lọc càng nhiều thì càng dễ loại nhầm operation khi controller hoặc media type thay đổi.

## 14. Checklist trước khi phát hành

- [ ] `packages-to-scan` chỉ bao gồm package controller thuộc tài liệu cần công bố.
- [ ] `packages-to-exclude` loại các package không phù hợp nếu cần.
- [ ] `paths-to-match` bao phủ đúng API version và domain path.
- [ ] `paths-to-exclude` loại đúng internal/debug path.
- [ ] `consumes-to-match` giữ đủ media type request mà consumer cần.
- [ ] `produces-to-match` giữ đủ media type response, bao gồm streaming nếu có.
- [ ] `headers-to-match` chỉ được dùng khi mapping có header condition tương ứng.
- [ ] Header parameter cần gửi được mô tả riêng bằng `@RequestHeader`/`@Parameter`.
- [ ] Group name duy nhất và URL document đã được kiểm tra.
- [ ] JSON OpenAPI đã được kiểm tra tự động, không chỉ dựa vào Swagger UI.
- [ ] Spring Security/API gateway bảo vệ endpoint độc lập với bộ lọc tài liệu.
- [ ] Consumer hoặc pipeline code generation đã được kiểm tra sau khi operation bị thêm/bớt.

## 15. Tài liệu tham khảo chính thức

- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — danh sách thuộc tính core, giá trị mặc định và bộ lọc package/path/media type/header.
- [springdoc-openapi Core Properties Reference](https://springdoc.org/core-properties.html) — tham chiếu chi tiết cho các thuộc tính cấu hình hiện hành.
- [springdoc-openapi FAQ](https://springdoc.org/faq.html) — ví dụ `packagesToScan`, `pathsToMatch`, API groups và cách ẩn operation.
- [springdoc-openapi v2 Properties](https://springdoc.org/v2/properties.html) — thuộc tính cấu hình cho dòng Spring Boot 3.
- [Spring Framework — Mapping Requests (MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — điều kiện path, consumes, produces và headers trên request mapping.
- [Spring Framework — Mapping Requests (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html) — request mapping conditions trong reactive stack.

Giới hạn package, path, media type và header giúp tạo ra OpenAPI document đúng phạm vi của từng consumer. Hãy xem chúng là bộ lọc hợp đồng tài liệu, kết hợp với group khi cần nhiều góc nhìn API, và luôn giữ authorization ở lớp bảo mật runtime thay vì dựa vào việc endpoint có xuất hiện trong Swagger UI hay không.
