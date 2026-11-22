# Quan hệ giữa mã Spring, siêu dữ liệu và hợp đồng API được sinh

Springdoc-openapi tạo đặc tả OpenAPI từ ứng dụng Spring bằng cách kết hợp thông tin mà Spring đã đăng ký cho các endpoint với metadata trong mã Java. Mapping của controller cho biết endpoint nào tồn tại; kiểu tham số và kiểu trả về gợi ý cấu trúc request/response; annotation của Swagger bổ sung mô tả có chủ đích; Bean Validation cung cấp ràng buộc dữ liệu; Jackson cho biết dữ liệu được serialize và deserialize như thế nào. Springdoc tổng hợp các thông tin đó thành OpenAPI document để ứng dụng có thể xuất JSON/YAML và hiển thị qua Swagger UI.

Hiểu mối quan hệ này giúp giải thích vì sao sửa một annotation có thể làm schema thay đổi, vì sao một route chạy được nhưng không xuất hiện trong tài liệu, hoặc vì sao JSON response thực tế khác với schema mà người phát triển kỳ vọng. OpenAPI không phải bản sao nguyên văn của source code. Nó là hợp đồng được suy ra từ nhiều nguồn metadata, sau đó có thể được tùy biến và kiểm chứng.

## 1. Nhìn toàn cảnh: từ mã nguồn đến hợp đồng API

Một controller Spring thường chứa nhiều loại thông tin khác nhau:

- Annotation của Spring mô tả URL, HTTP method, query parameter, header, request body và cách xử lý request.
- Chữ ký Java mô tả kiểu dữ liệu của tham số và giá trị trả về.
- Annotation OpenAPI mô tả tên operation, summary, description, ví dụ, response và security requirement.
- Bean Validation mô tả ràng buộc dữ liệu như bắt buộc, độ dài và giới hạn số.
- Jackson annotations và cấu hình serializer ảnh hưởng tới JSON được đọc hoặc ghi.
- Cấu hình ứng dụng quyết định controller nào được tạo, package nào được quét và document nào được công bố.

Springdoc đọc những thông tin phù hợp từ runtime Spring application context, kết hợp chúng thành các đối tượng OpenAPI rồi serialize thành JSON hoặc YAML. Swagger UI đọc document đó để hiển thị giao diện tương tác.

~~~mermaid
flowchart TD
    A["Spring Controller và Request Mapping"] --> E["Spring Handler Mapping"]
    B["Chữ ký Java và DTO"] --> G["Springdoc: phân tích endpoint và kiểu dữ liệu"]
    C["Swagger/OpenAPI annotations"] --> G
    D["Bean Validation và Jackson metadata"] --> G
    E --> G
    F["Cấu hình scan, group, filter"] --> G
    G --> H["OpenAPI model"]
    I["OpenApiCustomizer / OperationCustomizer"] --> H
    H --> J["OpenAPI JSON"]
    H --> K["OpenAPI YAML"]
    J --> L["Swagger UI"]
    K --> M["Validator, code generator và CI"]
~~~

Sơ đồ mô tả quan hệ khái niệm. Chi tiết nội bộ có thể khác theo phiên bản Springdoc và web stack, nhưng các nguồn metadata và đầu ra chính vẫn có cùng vai trò.

## 2. Phân biệt ba lớp: runtime, metadata và document

Khi đọc code Springdoc, cần phân biệt ba lớp:

| Lớp | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Runtime endpoint | Request HTTP có được Spring nhận và xử lý không? | **@GetMapping("/products/{id}")** |
| Metadata mô tả | Endpoint và dữ liệu được mô tả như thế nào? | **@Operation**, **@Schema**, **@NotBlank** |
| OpenAPI document | Hợp đồng công bố cho client có nội dung gì? | **paths**, **parameters**, **requestBody**, **responses** |

Một endpoint có thể tồn tại ở runtime nhưng bị ẩn khỏi document bằng **@Hidden**, **@Operation(hidden = true)**, package/path filter hoặc customizer. Ngược lại, nếu controller không được tạo thành bean hoặc mapping không được Spring đăng ký, Springdoc thường không có handler chuẩn để mô tả.

OpenAPI document cũng có thể được bổ sung hoặc sửa bởi customizer. Vì vậy, document cuối cùng không nhất thiết chỉ chứa đúng những gì có thể suy ra từ một method Java.

## 3. Spring đăng ký endpoint trước khi Springdoc mô tả

Với Spring MVC, **@RestController** đánh dấu class là controller có response body mặc định. **@RequestMapping** và các composed annotation như **@GetMapping**, **@PostMapping**, **@PutMapping**, **@DeleteMapping** khai báo điều kiện ánh xạ request.

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{id}")
    public ProductResponse findById(@PathVariable UUID id) {
        return productService.findById(id);
    }
}
~~~

Spring MVC phát hiện bean controller và đăng ký method cùng RequestMappingInfo vào handler mapping. Thông tin này gồm path, HTTP method và các điều kiện liên quan như params, headers, consumes hoặc produces.

Springdoc sử dụng thông tin endpoint mà Spring quản lý để xây dựng operation. Do đó, việc controller được component scan, bean khởi tạo thành công và mapping được đăng ký là điều kiện nền tảng.

Nếu class nằm ngoài component scan, bị loại bởi **@Profile** hoặc **@Conditional**, hoặc module không nằm trong runtime classpath, annotation OpenAPI trên class không tự làm endpoint xuất hiện.

## 4. Annotation Spring mô tả cách request được định tuyến

Các annotation mapping có ý nghĩa trực tiếp với hợp đồng HTTP:

| Annotation | Ý nghĩa trong runtime | Thông tin thường thể hiện trong OpenAPI |
|---|---|---|
| **@RequestMapping** | Mapping tổng quát theo path và điều kiện | Path, method và điều kiện tương ứng |
| **@GetMapping** | Nhận GET | Operation GET |
| **@PostMapping** | Nhận POST | Operation POST |
| **@PutMapping** | Nhận PUT | Operation PUT |
| **@PatchMapping** | Nhận PATCH | Operation PATCH |
| **@DeleteMapping** | Nhận DELETE | Operation DELETE |
| **@PathVariable** | Lấy giá trị từ path segment | Path parameter |
| **@RequestParam** | Lấy query/form parameter | Query parameter |
| **@RequestHeader** | Lấy giá trị từ header | Header parameter khi phù hợp |
| **@RequestBody** | Đọc body của request | Request body schema |

Spring annotations xác định hành vi định tuyến và binding. Chúng không thay thế phần mô tả nghiệp vụ. Một method có **@GetMapping** cho biết HTTP method và path, nhưng chưa giải thích operation dùng để làm gì, quyền truy cập ra sao hoặc response lỗi nào có thể xảy ra.

## 5. Chữ ký Java cung cấp kiểu dữ liệu để suy luận schema

Kiểu tham số và kiểu trả về giúp Springdoc suy luận cấu trúc cơ bản:

~~~java
@GetMapping("/{id}")
public ProductResponse findById(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

Từ method này, Springdoc có thể xác định:

- Path là /api/products/{id} khi kết hợp class mapping.
- HTTP method là GET.
- id là path parameter.
- Kiểu Java UUID được biểu diễn thành kiểu string với format UUID trong OpenAPI.
- Kiểu trả về ProductResponse được phân tích thành schema response.

Nếu method trả về **List<ProductResponse>**, document có thể biểu diễn response là array của schema ProductResponse. Nếu trả về **Page<ProductResponse>** hoặc một wrapper tùy biến, schema phụ thuộc vào kiểu cụ thể, cấu hình và cách thư viện phân tích model.

Kiểu dữ liệu càng cụ thể thì hợp đồng càng rõ. Các kiểu như Object, raw Map, raw ResponseEntity hoặc ResponseEntity<?> thường khiến schema kém chính xác và có thể cần **@ApiResponse**/**@Schema** tường minh.

## 6. Spring annotations và OpenAPI annotations bổ sung cho nhau

Spring annotation chủ yếu điều khiển runtime. OpenAPI annotation bổ sung thông tin dành cho người tiêu thụ hợp đồng.

~~~java
@GetMapping("/{id}")
@Operation(
    operationId = "getProductById",
    summary = "Xem chi tiết sản phẩm",
    description = "Trả thông tin của một sản phẩm theo UUID."
)
public ProductResponse findById(
        @Parameter(description = "UUID của sản phẩm", example = "4d7f1e0a-3e0d-4d58-9a2f-8d5f2d0c1001")
        @PathVariable UUID id) {
    return productService.findById(id);
}
~~~

Trong ví dụ:

- **@GetMapping** định tuyến request.
- **@PathVariable** liên kết path segment với tham số Java.
- **@Operation** bổ sung operationId, summary và description.
- **@Parameter** bổ sung mô tả và ví dụ cho path parameter.
- **ProductResponse** cung cấp kiểu response để suy luận schema.

Springdoc kết hợp các nguồn đó thành một operation duy nhất. Không cần lặp lại path và HTTP method trong **@Operation**; hãy để mapping của Spring là nguồn chính cho định tuyến và dùng OpenAPI annotations để bổ sung thông tin mô tả.

## 7. @Operation mô tả mục đích của một endpoint

**@Operation** thường được đặt trên method controller. Các thuộc tính hay dùng:

| Thuộc tính | Mục đích |
|---|---|
| operationId | Định danh ổn định cho operation |
| summary | Tiêu đề ngắn |
| description | Giải thích hành vi, điều kiện và lưu ý |
| tags | Nhóm operation |
| deprecated | Đánh dấu operation đã lỗi thời |
| hidden | Loại operation khỏi tài liệu |
| security | Khai báo security requirement ở operation |

operationId quan trọng với code generator và công cụ tạo client. Nên dùng tên rõ ràng, duy nhất trong document và ổn định qua các lần refactor.

summary nên đủ ngắn để hiển thị trong danh sách operation. description có thể giải thích side effect, quy tắc nghiệp vụ, pagination, idempotency hoặc điều kiện sử dụng.

Không dùng deprecated = true như cách ẩn operation. Deprecated báo client rằng operation không nên được dùng cho tích hợp mới; operation vẫn có thể xuất hiện trong document.

## 8. @Tag tổ chức các operation theo nhóm nghiệp vụ

**@Tag** thường được đặt ở cấp controller hoặc trên operation:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(
    name = "Products",
    description = "Tạo, tra cứu, cập nhật và xóa sản phẩm"
)
public class ProductController {
}
~~~

Tag giúp Swagger UI nhóm endpoint theo chức năng. Tên tag nên phản ánh khái niệm nghiệp vụ mà client hiểu, ví dụ Products, Orders hoặc Customers, thay vì tên package hoặc tên kỹ thuật của class.

Một controller có thể chứa nhiều nhóm operation nếu ứng dụng tổ chức theo use case. Trong trường hợp đó, gán tag ở method để phân nhóm rõ hơn.

## 9. @Parameter mô tả đầu vào không nằm trong body

Path, query, header và cookie parameter có thể được suy luận từ Spring method signature. **@Parameter** bổ sung description, example, schema hoặc metadata khác:

~~~java
@GetMapping
public ProductPageResponse list(
        @Parameter(
            description = "Lọc theo danh mục",
            example = "Accessories"
        )
        @RequestParam(required = false) String category,
        @Parameter(
            description = "Trang bắt đầu từ 0",
            example = "0"
        )
        @RequestParam(defaultValue = "0") int page) {
    return productService.findAll(category, page);
}
~~~

required = false và defaultValue là metadata Spring có ảnh hưởng tới cách binding request. **@Parameter** giúp mô tả ý nghĩa cho client. Khi kiểm tra OpenAPI output, xác nhận required, in, schema và example phản ánh đúng hành vi thực tế.

Path parameter luôn cần thiết để tạo thành path hoàn chỉnh. Nếu mapping có {id} nhưng method không bind hoặc mô tả đúng parameter, cần kiểm tra cấu trúc handler và output.

## 10. @RequestBody và schema của request

Với request body, Spring dùng **@RequestBody** để đọc payload qua HttpMessageConverter, thường là Jackson cho JSON. Springdoc dùng kiểu DTO và metadata của DTO để mô tả request body trong OpenAPI.

~~~java
@PostMapping
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm"
)
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    ProductResponse created = productService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Trong OpenAPI, request body thường gồm:

- required: body có bắt buộc không.
- content: media type, ví dụ application/json.
- schema: cấu trúc dữ liệu.
- example hoặc examples: dữ liệu mẫu.

Nếu endpoint nhận nhiều media type như JSON và multipart/form-data, mô tả và kiểm tra từng content type. Không giả định mọi request body đều là JSON.

## 11. DTO là ranh giới hợp đồng giữa API và domain

DTO giúp tách cấu trúc HTTP khỏi entity persistence:

~~~java
public class CreateProductRequest {

    @NotBlank
    @Size(max = 100)
    @Schema(description = "Tên sản phẩm", example = "Mechanical Keyboard K8")
    private String name;

    @NotBlank
    @Size(max = 40)
    @Schema(description = "Mã SKU duy nhất", example = "KB-K8-BLK")
    private String sku;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Schema(description = "Giá bán", example = "129.90")
    private BigDecimal price;

    // getters and setters
}
~~~

DTO nói cho Springdoc biết các trường client có thể gửi. Entity có thể chứa audit columns, trạng thái nội bộ, quan hệ lazy hoặc dữ liệu không nên công bố. Nếu dùng entity trực tiếp làm request/response, một thay đổi database có thể vô tình trở thành thay đổi API.

Nên cân nhắc DTO riêng cho create, update và response khi các thao tác có yêu cầu khác nhau. Create request thường không nhận id do server tạo; response có thể chứa id và timestamp.

## 12. Bean Validation bổ sung ràng buộc dữ liệu

Các annotation Bean Validation như **@NotNull**, **@NotBlank**, **@Size**, **@Min**, **@Max**, **@DecimalMin**, **@Pattern** có thể được dùng để:

1. Kiểm tra dữ liệu ở runtime khi request được validate.
2. Cung cấp metadata cho schema OpenAPI nếu phiên bản và cấu hình hỗ trợ.

Ví dụ:

~~~java
public class CreateProductRequest {

    @NotBlank
    @Size(min = 2, max = 100)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal price;
}
~~~

Schema có thể thể hiện name là required, giới hạn minLength/maxLength và price có minimum tương ứng. Tuy nhiên, hãy kiểm tra document được sinh ra; đừng mặc định mọi custom validator đều được chuyển thành JSON Schema constraint.

Một custom validation rule như SKU duy nhất thường phụ thuộc database hoặc service. OpenAPI có thể mô tả quy tắc bằng description, nhưng không thể tự thực thi kiểm tra uniqueness trên client.

## 13. Jackson quyết định hình dạng JSON thực tế

Jackson annotations ảnh hưởng tới serialization/deserialization và vì vậy có liên quan tới schema:

| Annotation | Ảnh hưởng thường gặp |
|---|---|
| **@JsonProperty** | Tên property trong JSON |
| **@JsonIgnore** | Bỏ qua property trong quá trình đọc/ghi tùy cấu hình |
| **@JsonProperty(access = WRITE_ONLY)** | Chỉ nhận khi ghi vào object, không serialize ra response |
| **@JsonProperty(access = READ_ONLY)** | Chỉ xuất trong response, không nhận như input |
| **@JsonInclude** | Quyết định điều kiện property được serialize |
| **@JsonFormat** | Định dạng ngày giờ hoặc giá trị |
| **@JsonView** | Chọn nhóm property theo view |

Ví dụ:

~~~java
public class AccountResponse {

    private UUID id;

    @JsonProperty("display_name")
    private String displayName;

    @JsonIgnore
    private String internalNote;
}
~~~

JSON thực tế có thể dùng display_name và không có internalNote. Khi tạo schema, cần bảo đảm document phản ánh cùng quy tắc JSON. Đặc biệt, không đưa password hoặc secret vào response DTO rồi chỉ trông chờ UI ẩn trường đó.

Nếu cùng một DTO được dùng cho cả request và response, READ_ONLY, WRITE_ONLY, JsonView hoặc custom serializer có thể làm schema khác nhau theo chiều dữ liệu. DTO tách biệt thường dễ hiểu và ít bất ngờ hơn.

## 14. Kiểu trả về Java góp phần mô tả response

Kiểu trả về của controller là nguồn metadata quan trọng:

~~~java
@GetMapping("/{id}")
public ProductResponse get(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

~~~java
@GetMapping
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

Trường hợp đầu mô tả một ProductResponse; trường hợp sau mô tả mảng ProductResponse.

Với **ResponseEntity<ProductResponse>**, generic type vẫn cung cấp thông tin response body, còn ResponseEntity cho phép điều khiển status và header ở runtime. Nếu dùng **ResponseEntity<Void>**, response thành công không có body. Nếu dùng **ResponseEntity<?>**, Object hoặc kiểu raw, có thể cần khai báo response schema bằng **@ApiResponse**.

Không nhầm ResponseEntity với schema body. ResponseEntity là wrapper điều khiển HTTP response; kiểu generic bên trong mới thường là body.

## 15. @ApiResponse mô tả từng kết quả HTTP

Một operation có thể có nhiều response:

~~~java
@GetMapping("/{id}")
@Operation(operationId = "getProductById", summary = "Xem chi tiết sản phẩm")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ProductResponse get(@PathVariable UUID id) {
    return productService.findById(id);
}
~~~

responseCode là status HTTP. description giải thích trường hợp. content mô tả media type và schema body. Với response 204, thường không có content body.

Springdoc có thể suy luận response thành công từ kiểu trả về, nhưng các lỗi nghiệp vụ như 400, 404 hoặc 409 thường cần mô tả rõ. Một response được ghi trong OpenAPI không tự khiến controller trả status đó; runtime code vẫn phải thực thi đúng hành vi.

## 16. Response mặc định và response tường minh

Có thể kết hợp suy luận từ method signature với annotation:

- Method trả ProductResponse gợi ý schema response thành công.
- ResponseEntity cho phép điều khiển status/header.
- **@ApiResponse** ghi rõ status và schema cho các kết quả quan trọng.
- **@Content** xác định media type.
- **@Schema(implementation = ...)** chỉ rõ model nếu kiểu trả về không đủ rõ.

Khi đã khai báo tường minh, hãy kiểm tra document cuối cùng để tránh response trùng, status không khớp hoặc schema bị thiếu. Annotation không thay thế việc đọc output.

## 17. @Schema mô tả model và property

**@Schema** có thể được đặt trên class hoặc field:

~~~java
@Schema(
    name = "ProductResponse",
    description = "Thông tin sản phẩm do hệ thống trả về"
)
public class ProductResponse {

    @Schema(description = "Mã định danh", format = "uuid")
    private UUID id;

    @Schema(description = "Tên sản phẩm", example = "Mechanical Keyboard K8")
    private String name;

    @Schema(description = "Giá bán", minimum = "0", example = "129.90")
    private BigDecimal price;
}
~~~

@Schema bổ sung tên, mô tả, ví dụ, format, giới hạn, required hoặc cách biểu diễn model. Chỉ khai báo constraint ở đây khi nó phản ánh hợp đồng thực tế. Nếu schema nói price không âm nhưng runtime cho phép số âm, tài liệu và API đã mâu thuẫn.

## 18. components/schemas giúp tái sử dụng model

OpenAPI thường đưa schema được dùng nhiều lần vào components/schemas và tham chiếu bằng $ref:

~~~yaml
components:
  schemas:
    ProductResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
        price:
          type: number
          minimum: 0
~~~

Một operation có thể tham chiếu:

~~~yaml
responses:
  "200":
    description: Tìm thấy sản phẩm
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/ProductResponse"
~~~

Việc tái sử dụng schema giúp tránh lặp cấu trúc và làm document gọn hơn. Khi đọc OpenAPI JSON, cần theo $ref để xem model thực tế thay vì chỉ nhìn path operation.

## 19. Tên property JSON và tên schema không nhất thiết giống tên Java

Tên field Java có thể khác tên JSON do Jackson naming strategy hoặc **@JsonProperty**. Tên schema cũng có thể được tùy chỉnh bằng **@Schema(name = ...)**.

Ví dụ:

~~~java
public class CustomerResponse {

    @JsonProperty("customer_code")
    @Schema(description = "Mã khách hàng", example = "CUS-1001")
    private String customerCode;
}
~~~

Client gửi và nhận customer_code nếu cấu hình Jackson áp dụng annotation đó. Không nên giả định client sẽ nhìn thấy tên field Java customerCode.

Khi schema bị trùng tên hoặc hai class khác package cùng được đặt một schema name, hãy xem components/schemas và điều chỉnh tên cho rõ ràng.

## 20. Security metadata mô tả cách client xác thực

OpenAPI security scheme có thể mô tả HTTP Bearer:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

Operation có thể yêu cầu scheme:

~~~java
@SecurityRequirement(name = "bearerAuth")
@GetMapping("/me")
public ProfileResponse profile() {
    return profileService.current();
}
~~~

Security metadata giúp Swagger UI hiển thị nút Authorize và giúp client hiểu cách truyền credential. Nó không xác minh token và không cấp quyền. Spring Security, OAuth2 Resource Server hoặc cơ chế xác thực thực tế mới thực thi bảo mật.

Nếu operation public, không áp dụng security requirement toàn cục một cách máy móc. Hãy mô tả đúng phạm vi bảo vệ.

## 21. Cấu hình toàn cục và thông tin API

Thông tin chung của document có thể khai báo bằng **@OpenAPIDefinition**:

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product Catalog API",
        version = "1.0.0",
        description = "API quản lý danh mục sản phẩm"
    )
)
public class OpenApiConfiguration {
}
~~~

info.title, info.version và info.description mô tả document API. Version ở đây là version của hợp đồng công bố; nó không nhất thiết giống version artifact Maven hoặc version Spring Boot.

Thông tin server, contact, license, externalDocs và security có thể được khai báo ở cấp document khi cần. Những metadata này giúp client hiểu môi trường và chính sách sử dụng API.

## 22. Cấu hình package và path quyết định phạm vi scan

Springdoc có thể giới hạn endpoint theo package hoặc path. Ví dụ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.catalog.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

Nếu controller nằm ngoài package hoặc path không khớp filter, operation có thể không xuất hiện trong document dù Spring vẫn đăng ký handler.

Các filter này là chính sách phạm vi tài liệu. Trước khi bỏ filter để xử lý operation thiếu, hãy xác định endpoint có được phép công bố không. Việc đưa toàn bộ internal endpoint vào Swagger UI có thể tiết lộ bề mặt API không dành cho client.

## 23. GroupedOpenApi tạo nhiều hợp đồng theo nhóm

Một ứng dụng có thể cung cấp nhiều document:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .packagesToScan("com.acme.catalog.api.public")
        .pathsToMatch("/api/**")
        .build();
}
~~~

Document group thường được truy cập theo dạng /v3/api-docs/{groupName}, ví dụ /v3/api-docs/public.

Một operation có thể xuất hiện trong default document nhưng không có trong public group do filter. Khi kiểm tra Swagger UI, xác nhận group đang chọn và endpoint JSON tương ứng.

Group hữu ích khi có public API, partner API và internal API với phạm vi khác nhau. Mỗi group cần được xem là một hợp đồng riêng và được kiểm tra độc lập.

## 24. Customizer thay đổi OpenAPI sau khi phân tích endpoint

Springdoc cung cấp các extension point như:

- OpenApiCustomizer: tùy biến OpenAPI document.
- GlobalOpenApiCustomizer: tùy biến áp dụng toàn cục theo phạm vi được cấu hình.
- OperationCustomizer: tùy biến operation trong quá trình tạo document.
- Customizer gắn với GroupedOpenApi: điều chỉnh riêng document group.

Ví dụ thêm mô tả chung:

~~~java
@Bean
OpenApiCustomizer addDocumentExtension() {
    return openApi -> {
        openApi.addExtension("x-owner-team", "catalog-platform");
    };
}
~~~

Customizer có thể thêm tag, extension, security, server hoặc loại path/operation. Vì thế, OpenAPI output cuối cùng là kết quả của quá trình scan cộng với các tùy biến đã đăng ký.

Khi một operation biến mất hoặc metadata khác kỳ vọng, tìm các customizer liên quan và kiểm tra điều kiện của chúng. Không giả định document chỉ phản ánh annotation tại controller.

## 25. Springdoc tạo document, Swagger UI chỉ hiển thị document

Hai phần này có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Springdoc runtime | Phân tích endpoint và tạo OpenAPI document |
| /v3/api-docs | Endpoint cung cấp OpenAPI JSON mặc định |
| /v3/api-docs.yaml | Endpoint cung cấp OpenAPI YAML nếu được hỗ trợ/cấu hình |
| Swagger UI | Giao diện đọc document và cho phép thử request |

Swagger UI không phải nơi định nghĩa contract chính. Nếu UI không hiển thị operation, hãy gọi JSON endpoint trực tiếp để xác định document có operation hay không. Nếu JSON đúng nhưng UI sai, kiểm tra URL document, group selection, UI configuration hoặc cache.

Tương tự, tắt Swagger UI không nhất thiết tắt API docs. Hai tính năng có cấu hình riêng.

## 26. Đọc một OpenAPI operation đã được sinh

Ví dụ rút gọn:

~~~yaml
paths:
  /api/products/{id}:
    get:
      tags:
        - Products
      operationId: getProductById
      summary: Xem chi tiết sản phẩm
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "404":
          description: Không tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
~~~

Đọc operation theo trình tự:

1. paths cho biết URL template.
2. get/post/put/delete cho biết HTTP method.
3. tags, operationId, summary, description cho biết metadata.
4. parameters mô tả đầu vào ngoài body.
5. requestBody mô tả payload đầu vào nếu có.
6. responses mô tả các kết quả HTTP.
7. $ref dẫn tới schema dùng chung trong components.

Đây là cấu trúc client generator và contract validator đọc; không cần biết class Java ban đầu mới có thể tiêu thụ document.

## 27. Lần theo một field từ Java tới OpenAPI

Giả sử DTO có field:

~~~java
@NotBlank
@Size(max = 80)
@Schema(description = "Tên hiển thị", example = "Keyboard K8")
private String name;
~~~

Các nguồn thông tin đóng góp:

| Nguồn | Ý nghĩa |
|---|---|
| String | Kiểu dữ liệu là string |
| @NotBlank | Không được null/rỗng/chỉ có whitespace ở runtime |
| @Size(max = 80) | Giới hạn độ dài |
| @Schema(description = ...) | Mô tả dành cho người dùng API |
| @Schema(example = ...) | Giá trị mẫu |
| Jackson metadata | Tên và quy tắc serialize property |

OpenAPI schema có thể biểu diễn property là string, required và maxLength 80 cùng description/example. Chi tiết chính xác phụ thuộc version và cách model được introspect.

Điểm quan trọng là không có một annotation duy nhất cung cấp tất cả thông tin. Hợp đồng được tổng hợp từ kiểu Java, validation, OpenAPI metadata và serialization metadata.

## 28. Lần theo một operation từ controller tới document

Ví dụ:

~~~java
@PostMapping
@Operation(
    operationId = "createProduct",
    summary = "Tạo sản phẩm",
    description = "Tạo sản phẩm mới và trả về tài nguyên vừa tạo."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Sản phẩm được tạo",
        content = @Content(
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request không hợp lệ",
        content = @Content(
            schema = @Schema(implementation = ErrorResponse.class)
        )
    )
})
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {
    ProductResponse created = productService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Spring mapping cung cấp POST và path được kết hợp từ class/method. Kiểu tham số cùng @RequestBody cung cấp request body. @Valid và constraint trên DTO mô tả ràng buộc. @Operation bổ sung ý nghĩa operation. @ApiResponse khai báo 201 và 400. Kiểu generic của ResponseEntity cho biết body thành công là ProductResponse.

Document kết quả sẽ có operation POST, requestBody schema CreateProductRequest, response 201 với ProductResponse và response 400 với ErrorResponse. Runtime vẫn phải thực thi đúng status và body đã mô tả.

## 29. Thứ tự suy luận và metadata tường minh

Có thể để Springdoc suy luận nhiều phần từ code:

- Mapping từ Spring handler.
- Parameter từ method signature.
- Schema từ DTO và kiểu trả về.
- Constraint từ Bean Validation.
- Metadata bổ sung từ Swagger annotations.

Khi kiểu Java không diễn tả đủ hợp đồng, hãy dùng annotation tường minh. Ví dụ:

- ResponseEntity<?> cần @ApiResponse chỉ rõ schema.
- Một error code nghiệp vụ cần @ApiResponse tương ứng.
- Một field cần description/example cần @Schema.
- Một query parameter khó hiểu cần @Parameter.

Không nên thêm annotation cho mọi thứ chỉ vì có thể. Metadata trùng lặp làm tăng khả năng mâu thuẫn và khiến việc bảo trì khó hơn. Bổ sung ở nơi thông tin không thể suy ra hoặc cần được cam kết rõ ràng.

## 30. Một thay đổi trong source có thể ảnh hưởng nhiều phần document

Thay đổi code có thể tác động tới hợp đồng theo nhiều cách:

| Thay đổi source | Phần OpenAPI có thể thay đổi |
|---|---|
| Đổi @GetMapping thành @PostMapping | HTTP method |
| Đổi class-level @RequestMapping | Path của nhiều operation |
| Đổi kiểu String thành UUID | Parameter schema và format |
| Thêm @NotBlank | Required/constraint nếu được hỗ trợ |
| Đổi @JsonProperty | Tên property JSON/schema |
| Thêm @Schema(example=...) | Example |
| Đổi return type | Response schema |
| Thêm @Hidden | Operation có thể biến mất |
| Đổi package/path filter | Phạm vi document |
| Thêm customizer | Nội dung cuối cùng của document |

Vì thế, thay đổi controller hoặc DTO có thể là breaking change với client ngay cả khi ứng dụng vẫn compile và test nội bộ vẫn chạy.

## 31. OpenAPI document là artifact cần được kiểm soát

Document có thể được lưu thành JSON/YAML để:

- Review trong pull request.
- Validate cấu trúc.
- Sinh client SDK hoặc server stub.
- So sánh với version đã phát hành.
- Phát hiện breaking change.
- Phân phối cho đối tác và developer portal.

Không nên coi /v3/api-docs chỉ là một trang debug. Với API có client bên ngoài, OpenAPI document là một artifact phát hành có giá trị tương tự schema hoặc contract file.

## 32. Phân biệt document runtime với file export

OpenAPI document có thể được lấy trực tiếp từ ứng dụng đang chạy hoặc được export trong quá trình build. Hai cách có mục đích khác nhau:

| Cách lấy | Ưu điểm | Cần lưu ý |
|---|---|---|
| Runtime endpoint | Phản ánh profile và cấu hình đang chạy | Phải gọi đúng instance và group |
| Build-time export | Dễ lưu artifact trong CI | Cần cấu hình runtime phù hợp để khởi tạo app |
| File đã commit | Dễ review và phân phối | Có thể lỗi thời nếu không được regenerate |

Nếu so sánh hai document, phải bảo đảm chúng đến từ cùng commit, profile, feature flags và document group. Nếu không, khác biệt có thể do môi trường thay vì source.

## 33. Kiểm tra document thay vì chỉ nhìn annotation

Một quy trình kiểm tra cơ bản:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

Liệt kê path:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Xem response của một operation:

~~~bash
jq '.paths["/api/products/{id}"].get.responses' target/openapi.json
~~~

Kiểm tra schema:

~~~bash
jq '.components.schemas.ProductResponse' target/openapi.json
~~~

Các lệnh này xác minh output thực tế mà client sẽ nhận. Nếu annotation đúng trong source nhưng JSON không đúng, hãy điều tra runtime profile, dependency version, mapping scan, filter và customizer.

## 34. Kiểm tra handler mapping và OpenAPI để phân biệt nguyên nhân

Spring Boot Actuator có endpoint mappings để quan sát handler được đăng ký. Trong môi trường phát triển được bảo vệ, có thể expose endpoint mappings rồi kiểm tra /actuator/mappings.

Kết hợp hai kết quả:

| Có trong Spring handler mapping | Có trong OpenAPI | Diễn giải |
|---|---|---|
| Có | Có | Handler đã được Spring đăng ký và document có operation |
| Có | Không | Kiểm tra @Hidden, filter, group hoặc customizer |
| Không | Không | Kiểm tra bean, component scan, profile, mapping và proxy |
| Không | Có | Kiểm tra customizer tự thêm operation hoặc đang đọc document từ runtime khác |

Không expose actuator mappings công khai nếu không cần; endpoint này có thể tiết lộ path và cấu trúc nội bộ của ứng dụng.

## 35. Những trường hợp dễ hiểu nhầm

**Endpoint chạy được nhưng không có trong Swagger UI.** Có thể endpoint bị ẩn, không thuộc document group đang chọn hoặc bị package/path filter loại. Hãy gọi JSON endpoint trước khi sửa controller.

**Swagger UI không mở được nhưng JSON vẫn có.** Kiểm tra UI dependency, springdoc.swagger-ui.enabled, UI path và URL document. Không tắt API docs nếu chỉ muốn ẩn giao diện.

**Schema không có constraint như mong đợi.** Kiểm tra validation dependency, @Valid, annotation target, version Springdoc và OpenAPI output. Custom constraint không nhất thiết tự chuyển thành JSON Schema.

**JSON response khác schema.** Kiểm tra Jackson annotations, naming strategy, serializer, JsonView và DTO thực tế được trả về.

**Response status khác tài liệu.** Kiểm tra ResponseEntity, exception handler, status mapping và test HTTP.

**Operation biến mất sau khi thêm customizer.** Kiểm tra OpenApiCustomizer, GlobalOpenApiCustomizer và OperationCustomizer, kể cả customizer gắn riêng với group.

## 36. Các giới hạn của việc suy luận tự động

Springdoc có thể suy luận nhiều thông tin nhưng không thể tự biết mọi quy tắc nghiệp vụ:

- Quy tắc SKU duy nhất cần logic nghiệp vụ hoặc database.
- Quyền sở hữu tài nguyên cần authorization logic.
- Điều kiện rate limit phụ thuộc gateway hoặc filter.
- Side effect như gửi email hoặc tạo payment cần description.
- Semantics của PATCH và cách xử lý field null cần được thiết kế.
- Quy tắc retry/idempotency có thể cần header và mô tả riêng.
- Error response tùy nghiệp vụ cần được khai báo.

Nếu thông tin có ý nghĩa với client nhưng không hiện diện trong type hoặc annotation, hãy mô tả rõ bằng OpenAPI annotations hoặc customizer. Đừng mong công cụ suy ra ý nghĩa mà code không biểu đạt.

## 37. Quản lý version và compatibility

Springdoc phải tương thích với Spring Boot, Spring Framework và web stack mà ứng dụng sử dụng. Cần chọn starter tương ứng với Spring MVC hoặc Spring WebFlux và kiểm tra compatibility matrix của phiên bản đang dùng.

Khi nâng Spring Boot hoặc Springdoc:

1. Kiểm tra dependency tree để phát hiện nhiều version Swagger/OpenAPI cùng tồn tại.
2. Kiểm tra import và package annotation.
3. Khởi động ứng dụng với profile cần phát hành.
4. Export OpenAPI JSON/YAML.
5. So sánh document trước và sau nâng cấp.
6. Chạy validator và contract tests.

Một nâng cấp thư viện có thể thay đổi cách suy luận schema hoặc annotation metadata. Không kết luận API không đổi chỉ vì source controller không đổi.

## 38. Kiểm thử contract ở nhiều lớp

Có ba loại kiểm tra bổ sung cho nhau:

| Kiểm tra | Xác minh |
|---|---|
| Unit/service test | Quy tắc nghiệp vụ |
| HTTP integration test | Status, header và body runtime |
| OpenAPI document test | Path, parameter, schema và response contract |

Ví dụ HTTP test có thể xác minh POST trả 201 và Location. OpenAPI document test xác minh operation POST có response 201 với ProductResponse. Cả hai cần cùng tồn tại để phát hiện trường hợp tài liệu đúng nhưng runtime sai hoặc ngược lại.

Khi API đã được phát hành, bổ sung compatibility check so với baseline. Một thay đổi có thể hợp lệ về code nhưng phá client cũ, ví dụ xóa field response, đổi kiểu hoặc xóa status code đã cam kết.

## 39. Checklist đọc một thay đổi API

Khi review pull request thay đổi controller hoặc DTO, hãy hỏi:

- [ ] Mapping path và HTTP method có thay đổi không?
- [ ] Có thêm, xóa hoặc đổi parameter không?
- [ ] Request body có thay đổi required field, type hoặc constraint không?
- [ ] JSON property có thay đổi tên hoặc quy tắc serialize không?
- [ ] Response type, status code hoặc header có thay đổi không?
- [ ] Error response có giữ cấu trúc ổn định không?
- [ ] Security requirement có phản ánh đúng authorization thực tế không?
- [ ] OperationId có còn ổn định và duy nhất không?
- [ ] Document group có đưa operation vào đúng phạm vi không?
- [ ] OpenAPI JSON/YAML đã được regenerate và validate chưa?
- [ ] Có contract test cho thay đổi quan trọng không?

Checklist này biến OpenAPI thành một phần của review API thay vì bước tạo tài liệu sau khi code đã hoàn tất.

## 40. Ghi nhớ

- Spring mapping quyết định endpoint và điều kiện định tuyến ở runtime.
- Java method signature và DTO cung cấp kiểu dữ liệu để suy luận parameter, request body và response schema.
- Swagger/OpenAPI annotations bổ sung mô tả có chủ đích cho operation, parameter, response và model.
- Bean Validation mô tả một phần constraint và đồng thời thực thi kiểm tra dữ liệu khi được kích hoạt.
- Jackson ảnh hưởng đến tên property và JSON thực tế.
- Springdoc tổng hợp metadata thành OpenAPI document; customizer có thể sửa kết quả sau quá trình scan.
- Swagger UI hiển thị document, còn /v3/api-docs là đầu ra hợp đồng JSON.
- Endpoint runtime có thể tồn tại mà không được công bố trong document; ẩn tài liệu không thay thế bảo mật.
- OpenAPI output phải được kiểm tra trực tiếp, không chỉ nhìn annotation hoặc UI.
- Contract tests và CI validation giúp giữ source, runtime và document nhất quán.

Quan hệ giữa mã Spring, metadata và hợp đồng API là một chuỗi chuyển đổi. Spring xác định endpoint; chữ ký Java, DTO, validation và Jackson bổ sung thông tin về dữ liệu; Swagger annotations mô tả những điều code không thể tự diễn đạt; Springdoc tổng hợp tất cả thành OpenAPI document. Khi hiểu từng nguồn đóng góp phần nào, người phát triển có thể giải thích và kiểm soát chính xác thay đổi trong hợp đồng mà client nhận được.

## Tài liệu tham khảo

- Springdoc OpenAPI – Documentation and FAQ: https://springdoc.org/
- Springdoc OpenAPI – FAQ: https://springdoc.org/faq.html
- Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html
- Spring Framework – Request Mapping: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Swagger Core – OpenAPI Annotations: https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
