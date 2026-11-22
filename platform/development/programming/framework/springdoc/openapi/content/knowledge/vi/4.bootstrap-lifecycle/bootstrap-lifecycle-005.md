# Điều kiện để Springdoc nhận diện Controller và handler

Springdoc tạo tài liệu từ các endpoint mà Spring đã đăng ký trong ứng dụng. Vì vậy, để một operation xuất hiện trong OpenAPI, controller phải được tạo thành bean trong `ApplicationContext`, phương thức xử lý phải được Spring MVC hoặc Spring WebFlux nhận diện là handler, và endpoint phải nằm trong phạm vi tài liệu đang được tạo.

Một lớp có tên `Controller` hoặc một phương thức có tên `getUsers()` chưa đủ để Springdoc nhận diện. Điều quyết định là quá trình khởi động của Spring có đăng ký lớp đó và ánh xạ HTTP cho phương thức hay không. Sau đó, các bộ lọc của springdoc và annotation ẩn mới quyết định operation có được đưa vào tài liệu cụ thể hay không.

## 1. Luồng nhận diện từ lúc ứng dụng khởi động

Trong một ứng dụng Spring Boot dùng Spring MVC hoặc WebFlux, quá trình có thể hình dung qua các bước:

1. **Spring Boot tạo ApplicationContext**: cấu hình ứng dụng, component scan, profile và các điều kiện auto-configuration quyết định bean nào được đăng ký.
2. **Controller trở thành bean**: các lớp được phát hiện qua component scan, import hoặc cấu hình bean được khởi tạo theo vòng đời Spring.
3. **Web framework đăng ký handler**: Spring MVC hoặc WebFlux đọc các mapping trên controller và đăng ký chúng vào hệ thống handler mapping.
4. **Springdoc đọc metadata handler**: springdoc thu thập các mapping, tham số, kiểu dữ liệu và annotation liên quan để tạo OpenAPI operation.
5. **Tài liệu được lọc và xuất ra**: cấu hình package/path, group và annotation ẩn quyết định operation nào thuộc tài liệu đang xem.

Do đó, cần phân biệt ba câu hỏi khi endpoint không xuất hiện:

- Controller có thực sự là bean trong ứng dụng đang chạy không?
- Spring có đăng ký mapping cho phương thức đó không?
- Mapping đã đăng ký có bị loại khỏi tài liệu bởi bộ lọc hoặc annotation không?

Swagger UI chỉ hiển thị tài liệu OpenAPI được tạo ra. Nếu controller chưa được Spring đăng ký hoặc mapping không tồn tại, việc mở Swagger UI không thể tự làm endpoint xuất hiện.

## 2. Điều kiện để Controller trở thành bean

### 2.1. Dùng annotation stereotype phù hợp

Springdoc làm việc với controller đã được Spring quản lý. Với API REST, cách phổ biến nhất là dùng `@RestController`:

```java
package com.example.shop.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> findAll() {
        return productService.findAll();
    }
}
```

`@RestController` là annotation kết hợp giữa `@Controller` và `@ResponseBody`. Nó đánh dấu lớp là controller của Spring và cho biết kết quả phương thức được ghi vào response body, thường qua bộ chuyển đổi JSON.

`@Controller` cũng có thể được Spring nhận diện là controller. Tuy nhiên, nếu phương thức trả về dữ liệu API thay vì tên view, cần dùng `@ResponseBody` ở phương thức hoặc cấp lớp:

```java
@Controller
@ResponseBody
@RequestMapping("/api/v1/products")
class ProductController {

    @GetMapping
    List<ProductResponse> findAll() {
        return productService.findAll();
    }
}
```

Springdoc có thể đọc các handler được đăng ký từ `@Controller` hoặc `@RestController`. Việc chọn `@RestController` chủ yếu giúp thể hiện rõ mục đích xây dựng API và cách trả response body.

### 2.2. Controller phải nằm trong phạm vi component scan

Theo mặc định, `@SpringBootApplication` kích hoạt component scan từ package chứa lớp ứng dụng và các package con. Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── web
│   └── ProductController.java
├── service
│   └── ProductService.java
└── repository
    └── ProductRepository.java
```

Nếu `ShopApplication` nằm trong `com.example.shop`, `ProductController` trong `com.example.shop.web` được phát hiện theo cấu hình mặc định.

Trường hợp controller nằm ngoài package gốc, chẳng hạn `com.example.catalog.web`, component scan mặc định có thể không đi tới package đó. Hãy cấu hình phạm vi scan rõ ràng:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Một lựa chọn khác là import cấu hình hoặc bean cần thiết bằng `@Import` khi kiến trúc module yêu cầu. Chỉ mở rộng phạm vi scan tới những package thuộc ứng dụng; quét quá rộng có thể khiến Spring đăng ký các bean không mong muốn hoặc tạo xung đột tên bean.

Với ứng dụng nhiều module, cần bảo đảm module chứa controller được khai báo là dependency runtime và package của nó được component scan hoặc import. Chỉ có source code trong repository không có nghĩa lớp đó đã được đưa vào ứng dụng đang chạy.

### 2.3. Điều kiện và profile có thể làm controller không được tạo

Controller có thể được điều khiển bởi các cấu hình như:

- `@Profile`: bean chỉ tồn tại khi profile tương ứng đang hoạt động.
- `@ConditionalOnProperty`: bean chỉ được tạo khi property thỏa điều kiện.
- `@ConditionalOnClass` hoặc `@ConditionalOnMissingBean`: bean phụ thuộc vào classpath hoặc sự tồn tại của bean khác.
- Cấu hình `@ComponentScan` có include/exclude filter.

Ví dụ:

```java
@RestController
@RequestMapping("/api/internal/reports")
@Profile("internal")
class InternalReportController {

    @GetMapping
    List<ReportResponse> findAll() {
        return reportService.findAll();
    }
}
```

Controller trên chỉ được tạo khi profile `internal` đang hoạt động. Nếu ứng dụng chạy với profile `dev` mà không bật `internal`, mapping không được đăng ký và springdoc không có operation để mô tả.

Khi tài liệu khác nhau giữa môi trường local, staging và production, hãy so sánh profile, property và điều kiện tạo bean của từng môi trường.

## 3. Điều kiện để phương thức trở thành handler

### 3.1. Phương thức phải có request mapping được Spring hỗ trợ

Trong Spring MVC và WebFlux, các annotation như `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping` và `@DeleteMapping` dùng để đăng ký handler method.

Ví dụ:

```java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        return orderService.findById(id);
    }

    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }

    @PutMapping("/{id}")
    OrderResponse replace(
            @PathVariable UUID id,
            @RequestBody UpdateOrderRequest request) {
        return orderService.replace(id, request);
    }
}
```

Spring kết hợp mapping cấp lớp `/api/v1/orders` với mapping cấp phương thức. Vì vậy, các handler có đường dẫn cuối cùng là:

| Phương thức Java | HTTP method | Đường dẫn |
|---|---|---|
| `findById` | `GET` | `/api/v1/orders/{id}` |
| `create` | `POST` | `/api/v1/orders` |
| `replace` | `PUT` | `/api/v1/orders/{id}` |

Một phương thức Java thông thường không có mapping sẽ không tự trở thành endpoint HTTP chỉ vì nó nằm trong `@RestController`:

```java
@RestController
class OrderController {

    // Đây là phương thức hỗ trợ nội bộ, không phải HTTP handler.
    OrderResponse mapToResponse(Order order) {
        return new OrderResponse(order.getId(), order.getCode());
    }
}
```

### 3.2. Mapping phải được Spring đăng ký thành công

Spring MVC sử dụng `RequestMappingHandlerMapping` để tìm và đăng ký handler method. WebFlux có cơ chế handler mapping tương ứng. Nếu ứng dụng khởi động thất bại do hai handler xung đột mapping, tài liệu cũng không thể phản ánh một trạng thái ứng dụng hợp lệ.

Các điều kiện mapping có thể bao gồm:

- HTTP method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`.
- Path và path variable.
- `params` và `headers`.
- `consumes` và `produces`.
- Các điều kiện mapping tùy biến do ứng dụng bổ sung.

Ví dụ:

```java
@GetMapping(
        path = "/search",
        params = "status",
        produces = MediaType.APPLICATION_JSON_VALUE
)
List<OrderResponse> search(@RequestParam String status) {
    return orderService.search(status);
}
```

Springdoc đọc metadata mapping mà Spring đã đăng ký. Hãy kiểm tra điều kiện `params`, `headers`, media type và path khi operation có vẻ bị thiếu hoặc không giống endpoint mà bạn mong đợi.

OpenAPI chỉ định nghĩa một operation cho mỗi cặp path và HTTP method. Nếu ứng dụng có nhiều handler cùng path và method nhưng phân biệt bằng `params` hoặc `headers`, cần thiết kế tài liệu sao cho biểu diễn được một hợp đồng thống nhất, ví dụ mô hình hóa tham số tùy chọn hoặc các giá trị media type trong cùng operation. Không nên kỳ vọng Swagger UI luôn thể hiện mỗi biến thể mapping như một operation độc lập.

### 3.3. Kiểu trả về không quyết định việc đăng ký handler

Một handler có thể trả về DTO, `ResponseEntity<T>`, `List<T>`, kiểu reactive hoặc response body khác tùy stack. Kiểu trả về ảnh hưởng đến schema mà springdoc suy ra, nhưng điều kiện để phương thức được nhận diện trước hết vẫn là bean controller và request mapping hợp lệ.

Nếu method đã được đăng ký nhưng schema không đầy đủ, hãy kiểm tra kiểu trả về, generic, annotation Jackson và metadata OpenAPI. Đây là vấn đề mô tả response, khác với việc Spring có nhận diện handler hay không.

## 4. Spring MVC, WebFlux và functional endpoints

### 4.1. Chọn đúng starter theo web stack

Springdoc cần starter phù hợp với ứng dụng:

| Web stack | Có Swagger UI | Chỉ cần OpenAPI endpoint |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

Với Spring MVC, các handler thường được khai báo bằng controller và `@RequestMapping`. Với WebFlux, controller annotation cũng được hỗ trợ; cần bảo đảm ứng dụng thực sự chạy WebFlux và dùng starter WebFlux tương ứng.

Nếu chọn sai starter, springdoc có thể không đọc đúng hệ thống handler mapping của ứng dụng hoặc thiếu phần UI/API cần thiết. Kiểm tra dependency runtime trước khi điều tra annotation của controller.

### 4.2. Functional endpoints dùng RouterFunction

Spring WebFlux và Spring MVC hỗ trợ khai báo route theo kiểu functional thông qua `RouterFunction`. Các route này không phải controller method được khai báo bằng `@GetMapping`, nên cần mô tả theo cơ chế dành cho router operation của springdoc.

Ví dụ cấu trúc:

```java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/v1/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "findAllProducts",
            summary = "Lấy danh sách sản phẩm"
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route(
            RequestPredicates.GET("/api/v1/products"),
            handler::findAll
    );
}
```

`@RouterOperation` hoặc `@RouterOperations` cung cấp metadata OpenAPI cho route functional. Hãy đối chiếu cách khai báo và kiểu handler với phiên bản springdoc đang dùng, vì một số thuộc tính có thể khác giữa các major và giữa MVC với WebFlux.

Nếu dùng route functional mà không có metadata mô tả tương ứng, không nên kết luận rằng mọi route đã được mô tả đầy đủ chỉ vì ứng dụng vẫn nhận request thành công.

### 4.3. Endpoint không phải controller handler

Không phải mọi URL mà ứng dụng phục vụ đều là `@RequestMapping` handler. Ví dụ: tài nguyên tĩnh, servlet tùy biến, filter, WebSocket, route của gateway hoặc endpoint do một framework khác đăng ký có thể đi qua cơ chế riêng.

Springdoc tập trung vào các handler và integration mà nó hỗ trợ. Với endpoint thuộc cơ chế khác, hãy kiểm tra tài liệu tích hợp tương ứng hoặc mô tả hợp đồng OpenAPI bằng cấu hình/annotation thích hợp. Không nên thêm một controller giả chỉ để làm cho đường dẫn xuất hiện trong tài liệu nếu nó không đại diện cho hành vi runtime thực tế.

## 5. Các bộ lọc quyết định handler nào xuất hiện trong tài liệu

Sau khi Spring đăng ký handler, springdoc có thể giới hạn phạm vi tài liệu bằng package, path hoặc group. Vì thế, một endpoint có thể hoạt động bình thường nhưng không xuất hiện trong một tài liệu OpenAPI cụ thể.

### 5.1. Lọc theo package và path

Cấu hình toàn cục trong `application.yml` có thể giới hạn các controller và path cần đưa vào tài liệu:

```yaml
springdoc:
  packages-to-scan:
    - com.example.shop.web
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
```

- `packages-to-scan` giới hạn package controller được quét.
- `paths-to-match` chỉ giữ các path khớp mẫu.
- `paths-to-exclude` loại các path khớp mẫu khỏi tài liệu.

Các bộ lọc này ảnh hưởng đến tài liệu springdoc tạo ra. Chúng không thay đổi component scan của Spring và cũng không xóa mapping khỏi ứng dụng.

### 5.2. Tạo tài liệu riêng bằng GroupedOpenApi

Một ứng dụng có thể có tài liệu công khai và nội bộ. Mỗi group có thể áp dụng phạm vi package/path riêng:

```java
@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .packagesToScan("com.example.shop.web.publicapi")
                .pathsToMatch("/api/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .packagesToScan("com.example.shop.web.internal")
                .pathsToMatch("/internal/**")
                .build();
    }
}
```

Khi kiểm tra endpoint bị thiếu, cần xem đúng tài liệu mặc định hay group đang mở. Endpoint có thể không thuộc group `public` nhưng vẫn xuất hiện trong group `internal`.

### 5.3. Annotation ẩn loại operation khỏi OpenAPI

Springdoc hỗ trợ annotation ẩn của OpenAPI:

```java
@Hidden
@RestController
@RequestMapping("/api/internal/maintenance")
class MaintenanceController {
    // Các handler của controller này bị ẩn khỏi tài liệu.
}
```

Hoặc ẩn một phương thức:

```java
@Operation(hidden = true)
@DeleteMapping("/{id}/purge")
void purge(@PathVariable UUID id) {
    maintenanceService.purge(id);
}
```

`@Hidden` có thể áp dụng ở cấp controller hoặc handler; `@Operation(hidden = true)` ẩn operation cụ thể. Các annotation này chỉ ảnh hưởng tài liệu OpenAPI, không tự vô hiệu hóa route hay thay thế cơ chế phân quyền.

Ngoài ra, `@Parameter(hidden = true)` và `@Schema(hidden = true)` dùng để ẩn tham số hoặc thuộc tính schema tương ứng. Chúng không có nghĩa là ẩn toàn bộ controller.

## 6. Phân biệt nhận diện endpoint với xác thực và phân quyền

Spring Security có thể chặn request nếu người gọi chưa đăng nhập hoặc thiếu quyền. Điều đó không đồng nghĩa handler không được Spring đăng ký.

Ví dụ, một method có `@PreAuthorize("hasAuthority('ORDER_READ')")` vẫn có thể xuất hiện trong OpenAPI nếu controller và mapping hợp lệ. Khi đó, tài liệu cần mô tả security scheme và yêu cầu bảo mật phù hợp để người tích hợp biết cách gọi endpoint.

Tương tự, cấu hình CORS, CSRF, servlet filter hoặc interceptor có thể ảnh hưởng đến request runtime nhưng thường không quyết định Springdoc có nhận diện handler mapping hay không. Khi operation xuất hiện nhưng gọi thử bị `401`, `403` hoặc lỗi CORS, hãy điều tra lớp bảo mật và cấu hình HTTP riêng.

## 7. Quy trình chẩn đoán endpoint không xuất hiện

Thực hiện các bước theo thứ tự sau để tìm đúng tầng gây ra vấn đề:

1. **Kiểm tra ứng dụng đã khởi động đúng profile**: xem active profile, property và điều kiện tạo bean của controller.
2. **Kiểm tra controller có trong ApplicationContext**: xác minh package scan, module runtime, `@Import` và các điều kiện như `@Profile`/`@ConditionalOnProperty`.
3. **Kiểm tra mapping Spring đã đăng ký**: nếu có Spring Boot Actuator và endpoint mappings được expose, xem `/actuator/mappings`; tìm path, HTTP method và handler method mong muốn.
4. **Kiểm tra starter springdoc**: xác nhận MVC hay WebFlux và dependency `*-api` hoặc `*-ui` phù hợp.
5. **Kiểm tra OpenAPI trực tiếp**: gọi `/v3/api-docs` hoặc đường dẫn đã cấu hình qua `springdoc.api-docs.path`; tìm path và method trong JSON.
6. **Kiểm tra filter/group**: đối chiếu `packages-to-scan`, `paths-to-match`, `paths-to-exclude` và cấu hình `GroupedOpenApi`.
7. **Kiểm tra annotation ẩn**: tìm `@Hidden`, `@Operation(hidden = true)` ở controller hoặc method.
8. **Kiểm tra loại endpoint**: nếu route là `RouterFunction` hoặc custom handler mapping, xác minh springdoc có hỗ trợ và đã được cung cấp metadata phù hợp.

Bảng dưới đây giúp định hướng kết quả:

| Kết quả kiểm tra | Vị trí nên điều tra |
|---|---|
| Không thấy controller bean | Component scan, `@Import`, profile, conditional bean, dependency module |
| Có bean nhưng không có mapping trong Actuator | `@RequestMapping`, cấu hình web stack, mapping conflict hoặc loại handler |
| Có mapping trong Actuator nhưng không có trong OpenAPI | Starter, package/path filter, group, annotation ẩn, loại mapping chưa được hỗ trợ |
| Có operation trong `/v3/api-docs` nhưng không thấy trong Swagger UI | Đường dẫn UI, group đang chọn, cache trình duyệt hoặc tài liệu UI đang tải |
| Có operation nhưng gọi API bị từ chối | Authentication, authorization, CSRF, CORS hoặc filter runtime |

Nếu không sử dụng Actuator, có thể kiểm tra log khởi động hoặc viết kiểm tra integration test để xác nhận mapping. Chỉ expose endpoint Actuator cần thiết trong môi trường kiểm tra; không mở rộng quyền truy cập production chỉ để chẩn đoán.

## 8. Kiểm thử điều kiện nhận diện bằng integration test

Một kiểm thử tích hợp có thể xác nhận controller đã được đăng ký và OpenAPI chứa operation mong đợi. Ví dụ với Spring Boot Test và MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiControllerRegistrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void productEndpointIsPublishedInOpenApi() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.paths['/api/v1/products'].get"
                ).exists());
    }
}
```

Ví dụ giả định ứng dụng dùng starter WebMVC, endpoint tài liệu mặc định và `ProductController` được đăng ký trong test context. Nếu dùng WebFlux, hãy sử dụng `WebTestClient` và cấu hình test tương ứng.

Kiểm thử này kiểm tra kết quả OpenAPI mà ứng dụng thực sự xuất ra. Nên bổ sung assertion cho các method, schema hoặc response quan trọng nếu hợp đồng API cần được bảo vệ qua các lần refactor.

## 9. Những hiểu nhầm thường gặp

- **Đặt tên lớp là `ProductController` là đủ**: Spring cần tạo bean và đăng ký handler mapping. Tên lớp không thay thế annotation hoặc cấu hình bean.
- **Có `@RestController` là mọi method đều thành endpoint**: method cần mapping HTTP được Spring hỗ trợ.
- **Endpoint chạy được thì chắc chắn có trong mọi OpenAPI group**: bộ lọc package/path và group có thể loại endpoint khỏi tài liệu đang xem.
- **Bị 401/403 nghĩa là Springdoc không nhận diện handler**: bảo mật ảnh hưởng quyền gọi request; nó không đồng nghĩa mapping không tồn tại.
- **`@Hidden` vô hiệu hóa endpoint**: annotation chỉ ẩn operation khỏi tài liệu, không xóa route runtime.
- **Mọi URL đều là controller handler**: static resource, servlet, WebSocket, gateway route và functional endpoint có cơ chế đăng ký riêng.
- **Swagger UI không hiện nghĩa là controller không tồn tại**: cần kiểm tra `/v3/api-docs` trước để phân biệt lỗi tạo tài liệu với lỗi giao diện hoặc group.

## 10. Checklist khi thêm Controller mới

- [ ] Controller dùng `@RestController` hoặc `@Controller` phù hợp và được Spring quản lý.
- [ ] Package controller nằm trong component scan hoặc được import rõ ràng.
- [ ] Module chứa controller có trong runtime classpath.
- [ ] Profile và điều kiện tạo bean đúng với môi trường đang chạy.
- [ ] Mỗi endpoint có `@RequestMapping` hoặc annotation mapping tương ứng.
- [ ] Mapping không xung đột và đúng path, HTTP method, params, headers, consumes, produces.
- [ ] Starter springdoc khớp với Spring MVC hoặc WebFlux.
- [ ] Package/path filter và group bao gồm endpoint mong muốn.
- [ ] Không có `@Hidden` hoặc `@Operation(hidden = true)` ngoài ý định.
- [ ] Functional endpoint có metadata `@RouterOperation`/`@RouterOperations` phù hợp.
- [ ] Endpoint xuất hiện trong `/v3/api-docs` và được kiểm thử nếu là hợp đồng quan trọng.

Springdoc chỉ có thể mô tả chính xác những handler mà ứng dụng đã đăng ký và nằm trong phạm vi tài liệu. Khi nắm được thứ tự từ component scan, bean registration, handler mapping đến bộ lọc OpenAPI, việc tìm nguyên nhân endpoint bị thiếu sẽ rõ ràng và có thể kiểm chứng ở từng tầng.
