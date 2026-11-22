# Mô tả cấu trúc một cách độc lập với lớp entity lưu trữ

Đặc tả OpenAPI mô tả hợp đồng mà client sử dụng qua HTTP. Hợp đồng này nên phản ánh dữ liệu request và response của API, trong khi entity JPA phản ánh cách ứng dụng lưu trữ và liên kết dữ liệu trong cơ sở dữ liệu. Springdoc-openapi có thể suy luận schema từ kiểu Java của controller; vì vậy, nếu controller nhận và trả trực tiếp entity, cấu trúc lưu trữ rất dễ trở thành cấu trúc API ngoài ý muốn. Dùng DTO riêng cho request và response giúp giữ schema độc lập, kiểm soát dữ liệu công bố và cho phép thay đổi database mà không buộc client phải thay đổi theo.

## 1. Entity lưu trữ và API schema giải quyết hai bài toán khác nhau

Entity thường được thiết kế để đáp ứng yêu cầu persistence: khóa chính, quan hệ, trạng thái quản lý, optimistic locking, audit field và các quy tắc của ORM. DTO API được thiết kế để biểu diễn dữ liệu mà client cần gửi hoặc nhận. Hai mô hình có thể có một số field giống nhau, nhưng không có nghĩa chúng phải dùng chung một class.

| Khía cạnh | Entity persistence | DTO/API schema |
|---|---|---|
| Mục tiêu | Lưu trữ và quản lý trạng thái dữ liệu | Công bố hợp đồng HTTP cho client |
| Cấu trúc | Phụ thuộc bảng, quan hệ và ORM | Phụ thuộc use case và nhu cầu tích hợp |
| Trường dữ liệu | Có thể có khóa nội bộ, audit, version, quan hệ lazy | Chỉ gồm field được phép gửi hoặc công bố |
| Vòng đời | Có thể thay đổi khi migration hoặc tối ưu database | Thay đổi theo chính sách tương thích API |
| Validation | Constraint persistence và quy tắc domain | Validation đầu vào và ràng buộc hợp đồng |
| Biểu diễn | Có thể dùng kiểu phù hợp database | Có thể đổi tên, làm phẳng, tổng hợp hoặc chuyển đổi kiểu |

Ví dụ, bảng `products` có thể chứa `costPrice`, `supplierId`, `internalNote`, `createdBy`, `updatedAt` và `version`. Client của API danh mục chỉ cần `id`, `name`, `sellingPrice` và `category`. Nếu trả entity trực tiếp, các field nội bộ có thể bị công bố, hoặc quan hệ JPA có thể làm JSON phức tạp ngoài ý muốn.

Nguyên tắc thiết kế là: controller nhận và trả kiểu dữ liệu đại diện cho hợp đồng API; service/repository làm việc với domain model hoặc entity; lớp mapping chuyển đổi giữa hai mô hình.

## 2. Rủi ro khi dùng entity trực tiếp trong controller

Xét một entity đơn giản:

```java
@Entity
@Table(name = "products")
public class ProductEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    private BigDecimal sellingPrice;
    private BigDecimal costPrice;
    private String internalNote;

    @ManyToOne(fetch = FetchType.LAZY)
    private CategoryEntity category;

    @OneToMany(mappedBy = "product", fetch = FetchType.LAZY)
    private List<ProductImageEntity> images;

    @Version
    private long version;

    // getters và setters
}
```

Nếu controller trả trực tiếp `ProductEntity`, springdoc có thể dùng cấu trúc class đó để tạo schema. Điều này dẫn đến một số vấn đề:

- `costPrice` hoặc `internalNote` có thể xuất hiện trong tài liệu và response dù client không được phép biết.
- `category` và `images` có thể kéo theo nhiều schema liên quan, kể cả field không thuộc hợp đồng endpoint.
- Quan hệ hai chiều như `ProductEntity` và `ProductImageEntity.product` có thể tạo vòng tham chiếu hoặc lỗi serialization nếu không được xử lý.
- Quan hệ lazy có thể phát sinh truy vấn ngoài dự kiến hoặc lỗi khi session persistence đã đóng.
- Đổi tên cột, kiểu lưu trữ hoặc quan hệ entity có thể làm schema OpenAPI thay đổi ngoài ý muốn.
- Entity có thể chứa field phục vụ ORM mà client không nên gửi lên để cập nhật.

Ẩn từng field bằng annotation có thể xử lý một số trường hợp, nhưng entity vẫn bị dùng chung cho nhiều use case. Khi yêu cầu API và persistence khác nhau, DTO riêng thường tạo ra ranh giới rõ ràng và dễ kiểm soát hơn.

## 3. Tách request DTO và response DTO

Một use case thường cần ít nhất hai mô hình: dữ liệu client gửi vào và dữ liệu server trả ra. Ví dụ tạo sản phẩm:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Tên sản phẩm", example = "Bút bi")
    String name,

    @NotNull
    @DecimalMin("0.0")
    @Schema(description = "Giá bán", example = "12000")
    BigDecimal sellingPrice,

    @NotNull
    Long categoryId
) {}
```

Response có thể công bố một cấu trúc khác:

```java
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", example = "101")
    Long id,

    String name,

    BigDecimal sellingPrice,

    CategorySummary category
) {}

public record CategorySummary(
    Long id,
    String name
) {}
```

Request chỉ nhận `categoryId`, trong khi response trả `category` dưới dạng object tóm tắt. Client không cần gửi `id` của sản phẩm, `version` JPA hay toàn bộ entity category. `costPrice` và `internalNote` không xuất hiện ở cả hai DTO.

Các use case khác có thể có DTO riêng:

| Use case | DTO ví dụ | Dữ liệu chính |
|---|---|---|
| Tạo sản phẩm | `CreateProductRequest` | Tên, giá bán, category ID |
| Cập nhật sản phẩm | `UpdateProductRequest` | Các field được phép sửa; có thể khác request tạo mới |
| Trả chi tiết | `ProductResponse` | ID, tên, giá bán, category summary |
| Trả danh sách | `ProductListItem` | Field tối thiểu cho màn hình danh sách |
| Tìm kiếm | `ProductSearchRequest` hoặc query parameters | Từ khóa, bộ lọc và phân trang |

Không cần tạo DTO mới chỉ vì tên endpoint khác nhau nếu hợp đồng thật sự giống nhau. Tuy nhiên, khi quyền ghi, dữ liệu trả về hoặc vòng đời của hai use case khác nhau, DTO riêng giúp biểu đạt chính xác hơn.

## 4. Controller dùng DTO để tạo schema OpenAPI

Khi chữ ký controller sử dụng DTO, springdoc có thể suy luận request body và response schema từ các kiểu đó:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        return productService.create(request);
    }

    @GetMapping("/{id}")
    ProductResponse getById(@PathVariable Long id) {
        return productService.getById(id);
    }
}
```

Springdoc đọc `CreateProductRequest` để mô tả request body và `ProductResponse` để mô tả response. Schema được hình thành từ hợp đồng mà controller công bố, không phải từ bảng `products`.

Một phần OpenAPI có thể có cấu trúc như sau:

```yaml
paths:
  /api/products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Sản phẩm đã được tạo
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - sellingPrice
        - categoryId
      properties:
        name:
          type: string
          maxLength: 120
          example: Bút bi
        sellingPrice:
          type: number
          example: 12000
        categoryId:
          type: integer
          format: int64
    ProductResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        name:
          type: string
        sellingPrice:
          type: number
        category:
          $ref: '#/components/schemas/CategorySummary'
```

Đây là cấu trúc minh họa. Schema thực tế phụ thuộc phiên bản springdoc, cấu hình Jackson, kiểu dữ liệu và annotation validation. Hãy kiểm tra `/v3/api-docs` hoặc `/v3/api-docs.yaml` để xác nhận nội dung được sinh ra.

## 5. Chuyển đổi entity và DTO ở lớp service hoặc mapper

Controller không nên tự đọc từng quan hệ persistence hoặc chứa nhiều logic chuyển đổi. Có thể đặt mapping trong service hoặc một mapper chuyên biệt.

Ví dụ mapping thủ công:

```java
@Service
class ProductService {

    private final ProductRepository productRepository;
    private final CategoryRepository categoryRepository;

    ProductService(
        ProductRepository productRepository,
        CategoryRepository categoryRepository
    ) {
        this.productRepository = productRepository;
        this.categoryRepository = categoryRepository;
    }

    ProductResponse create(CreateProductRequest request) {
        CategoryEntity category = categoryRepository.findById(request.categoryId())
            .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));

        ProductEntity entity = new ProductEntity();
        entity.setName(request.name());
        entity.setSellingPrice(request.sellingPrice());
        entity.setCategory(category);

        ProductEntity saved = productRepository.save(entity);
        return toResponse(saved);
    }

    ProductResponse getById(Long id) {
        ProductEntity entity = productRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
        return toResponse(entity);
    }

    private ProductResponse toResponse(ProductEntity entity) {
        CategoryEntity category = entity.getCategory();
        CategorySummary categorySummary = category == null
            ? null
            : new CategorySummary(category.getId(), category.getName());

        return new ProductResponse(
            entity.getId(),
            entity.getName(),
            entity.getSellingPrice(),
            categorySummary
        );
    }
}
```

Mapping tường minh giúp kiểm soát field nào được chép, field nào được tính toán và quan hệ nào được rút gọn. Với ví dụ này, `costPrice`, `internalNote`, `images` và `version` không được đưa vào response.

Khi số lượng DTO lớn, có thể dùng MapStruct để sinh mã mapping ở compile time:

```java
@Mapper(componentModel = "spring")
public interface ProductMapper {

    @Mapping(target = "id", ignore = true)
    @Mapping(target = "category", ignore = true)
    @Mapping(target = "images", ignore = true)
    @Mapping(target = "version", ignore = true)
    ProductEntity toEntity(CreateProductRequest request);

    @Mapping(target = "category", source = "category")
    ProductResponse toResponse(ProductEntity entity);

    CategorySummary toSummary(CategoryEntity entity);
}
```

Đây là ví dụ định hướng; mapper thực tế cần cấu hình các kiểu đích, quan hệ và field không ánh xạ phù hợp với entity của dự án. Với quan hệ như `categoryId`, thường cần tra entity category từ repository hoặc dùng một phương thức mapping có `@Context`/service hỗ trợ. Không nên để mapper tự tạo entity quan hệ chỉ từ ID nếu việc kiểm tra tồn tại và quyền truy cập là quy tắc nghiệp vụ.

## 6. Tổ chức mapping để tránh cập nhật entity ngoài ý muốn

Không nên bind request trực tiếp vào entity rồi lưu toàn bộ object. Cách đó có thể cho phép client gán các field mà endpoint không dự định cho phép sửa, chẳng hạn `id`, `version`, `createdBy`, `costPrice` hoặc quan hệ khác.

Thay vào đó, chỉ gán những field được phép cập nhật:

```java
@Transactional
ProductResponse update(Long id, UpdateProductRequest request) {
    ProductEntity entity = productRepository.findById(id)
        .orElseThrow(() -> new ProductNotFoundException(id));

    entity.setName(request.name());
    entity.setSellingPrice(request.sellingPrice());

    if (request.categoryId() != null) {
        CategoryEntity category = categoryRepository.findById(request.categoryId())
            .orElseThrow(() -> new CategoryNotFoundException(request.categoryId()));
        entity.setCategory(category);
    }

    return productMapper.toResponse(entity);
}
```

`UpdateProductRequest` nên định nghĩa rõ field nào bắt buộc, field nào tùy chọn và ý nghĩa của `null`. Nếu API dùng PATCH, cần phân biệt “không gửi property” với “gửi property có giá trị null”; một DTO Java thông thường có thể không giữ được sự khác biệt này nếu chỉ dùng field nullable. Có thể dùng wrapper/JSON Merge Patch hoặc một mô hình cập nhật chuyên biệt khi hợp đồng cần phân biệt hai trạng thái.

## 7. Dùng @Schema để mô tả hợp đồng thay vì mô tả entity

DTO có thể dùng Swagger annotations để bổ sung mô tả cho client:

```java
@Schema(name = "ProductResponse", description = "Thông tin sản phẩm công bố qua API")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", example = "101", accessMode = Schema.AccessMode.READ_ONLY)
    Long id,

    @Schema(description = "Tên hiển thị", example = "Bút bi")
    String name,

    @Schema(description = "Giá bán theo đơn vị tiền tệ của cửa hàng", example = "12000")
    BigDecimal sellingPrice,

    @Schema(description = "Thông tin danh mục rút gọn")
    CategorySummary category
) {}
```

Các annotation có thể mô tả:

- `description`: ý nghĩa nghiệp vụ của schema hoặc property.
- `example` / `examples`: giá trị minh họa cho client.
- `format`: định dạng như `uuid`, `date`, `date-time`.
- `allowableValues`: tập giá trị cho phép trong schema phù hợp.
- `minimum`, `maximum`, `minLength`, `maxLength`: ràng buộc dữ liệu.
- `accessMode`: hướng sử dụng `READ_ONLY`, `WRITE_ONLY` hoặc `READ_WRITE`.
- `implementation`: chỉ định class dùng để mô tả schema khi kiểu khai báo không đủ rõ.

Đặt mô tả trên DTO API giúp tài liệu giữ đúng ngữ nghĩa ngay cả khi entity đổi tên field hoặc cấu trúc bảng. Không cần thêm annotation OpenAPI lên entity chỉ để phục vụ controller nếu entity không phải mô hình công khai.

## 8. Khi cần chỉ định schema bằng @Schema(implementation = ...)

Trong đa số trường hợp, kiểu DTO cụ thể trong chữ ký controller là đủ để springdoc suy luận schema. `@Schema(implementation = ...)` hữu ích khi kiểu Java ở vị trí đó là wrapper tổng quát, interface, kiểu trả về quá rộng hoặc khi cần công bố một schema đại diện cụ thể.

Ví dụ response:

```java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
@GetMapping("/{id}")
ResponseEntity<?> getById(@PathVariable Long id) {
    return ResponseEntity.ok(productService.getById(id));
}
```

Trong ví dụ, annotation yêu cầu tài liệu mô tả response theo `ProductResponse`. Tuy nhiên, chữ ký `ResponseEntity<?>` vẫn làm mất thông tin kiểu ở tầng Java. Nếu có thể, hãy khai báo kiểu rõ ràng:

```java
ResponseEntity<ProductResponse> getById(@PathVariable Long id) {
    return ResponseEntity.ok(productService.getById(id));
}
```

Schema override chỉ thay đổi tài liệu OpenAPI. Nó không chuyển đổi object trả về ở runtime. Nếu phương thức thực sự trả entity nhưng annotation lại khai báo `ProductResponse`, JSON thực tế vẫn có thể mang cấu trúc entity và hợp đồng sẽ sai. Cách đúng là chuyển đổi entity thành DTO trước khi trả response.

Tương tự với request body, có thể chỉ định schema trong Swagger `@RequestBody` bằng `@Content(schema = @Schema(implementation = ...))`. Điều này chỉ điều chỉnh tài liệu; controller vẫn cần tham số và cơ chế binding tương ứng.

## 9. Schema lồng nhau, tổng hợp và làm phẳng dữ liệu

API schema không nhất thiết phản chiếu quan hệ entity. Có thể rút gọn hoặc tổng hợp dữ liệu để phù hợp với client.

Ví dụ entity có quan hệ `ProductEntity -> CategoryEntity`, nhưng response chỉ cần một phần thông tin danh mục:

```java
public record ProductDetailResponse(
    Long id,
    String name,
    BigDecimal sellingPrice,
    CategorySummary category,
    List<ProductImageResponse> images
) {}

public record ProductImageResponse(
    Long id,
    String url,
    String altText
) {}
```

Schema `ProductDetailResponse` mô tả object lồng nhau. Client không cần biết category có bao nhiêu quan hệ JPA khác hoặc ảnh được lưu trong bảng nào.

Trong trường hợp cần dữ liệu phẳng cho màn hình danh sách, có thể dùng DTO khác:

```java
public record ProductListItem(
    Long id,
    String name,
    BigDecimal sellingPrice,
    String categoryName,
    String thumbnailUrl
) {}
```

Một response phẳng giúp client tránh nhiều lần truy cập object lồng nhau và cho phép backend tổng hợp dữ liệu từ nhiều bảng hoặc service. OpenAPI chỉ mô tả cấu trúc `ProductListItem`; nó không cần phản ánh các join hoặc query phía dưới.

## 10. Generic wrapper và schema API độc lập

Nhiều API dùng envelope chung:

```java
public record ApiEnvelope<T>(
    boolean success,
    T data,
    String message
) {}
```

Controller có thể khai báo kiểu cụ thể:

```java
@GetMapping("/{id}")
ApiEnvelope<ProductResponse> getById(@PathVariable Long id) {
    return new ApiEnvelope<>(true, productService.getById(id), null);
}
```

Kiểu generic cụ thể giúp springdoc có cơ hội phân giải `T` thành `ProductResponse` để tạo schema. Nếu chữ ký dùng raw type `ApiEnvelope` hoặc `ApiEnvelope<?>`, schema `data` có thể trở nên tổng quát và mất cấu trúc.

Không nên chuyển sang raw type chỉ để làm controller ngắn hơn. Nếu một endpoint có response khác biệt, hãy khai báo generic cụ thể hoặc dùng DTO envelope cụ thể. Khi framework không suy luận được, có thể dùng `@ApiResponse` cùng `@Schema(implementation = ...)` để mô tả rõ schema mong muốn và kiểm tra JSON đầu ra.

## 11. Giữ API ổn định khi entity hoặc database thay đổi

Một trong những lợi ích quan trọng của DTO riêng là database có thể thay đổi mà hợp đồng HTTP không cần thay đổi tương ứng.

| Thay đổi persistence | DTO/API có thể giữ nguyên bằng cách |
|---|---|
| Đổi tên cột `selling_price` thành `price_amount` | Mapper tiếp tục gán vào property `sellingPrice` |
| Chuyển giá từ `DECIMAL` sang số nguyên lưu đơn vị nhỏ nhất | Mapper chuyển đổi về `BigDecimal` hoặc representation đã công bố |
| Tách bảng category thành nhiều bảng | Service tổng hợp thành `CategorySummary` như cũ |
| Đổi quan hệ ảnh từ one-to-many sang bảng liên kết | Mapper vẫn trả `List<ProductImageResponse>` |
| Thêm `internalRiskScore` vào entity | Không đưa field mới vào DTO nếu API không có nhu cầu công bố |
| Thêm `@Version` hoặc audit field | Giữ chúng trong persistence; chỉ đưa vào API nếu hợp đồng yêu cầu rõ |

Ngược lại, thay đổi DTO có thể là một thay đổi API cần đánh giá tương thích, ngay cả khi database không thay đổi. Ví dụ đổi `sellingPrice` thành `price` có thể phá client đang đọc property cũ. Vì vậy, migration database và versioning API nên được quản lý như hai quá trình riêng.

Nếu cần thay đổi cấu trúc API, có thể thêm field tùy chọn, duy trì field cũ trong giai đoạn chuyển tiếp hoặc công bố phiên bản API mới theo chính sách của hệ thống. Không để schema thay đổi âm thầm chỉ vì entity được refactor.

## 12. Kiểm tra OpenAPI để bảo đảm không lộ cấu trúc persistence

Sau khi chạy ứng dụng, tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Tìm schema request và response của endpoint, rồi đối chiếu với DTO đã thiết kế.

Các điểm nên kiểm tra:

1. `requestBody.content` tham chiếu đúng request DTO, không phải entity JPA.
2. Response schema tham chiếu đúng response DTO.
3. Không có field persistence nội bộ như `costPrice`, `internalNote`, `version` hoặc `createdBy` nếu hợp đồng không công bố chúng.
4. Quan hệ entity được biểu diễn thành nested DTO, summary hoặc field phẳng có chủ đích.
5. Các field bắt buộc, enum, format, example và giới hạn validation phản ánh đúng hợp đồng.
6. Các response lỗi và status code được mô tả theo hành vi endpoint.
7. Các schema trong `components.schemas` không vô tình phụ thuộc vào entity class.

Trong Swagger UI, xem phần Schemas và mở operation để kiểm tra request/response. Swagger UI chỉ hiển thị tài liệu; cần gửi request thật để xác nhận JSON runtime đúng với schema.

## 13. Kiểm thử hợp đồng và payload runtime

Có thể dùng MockMvc để xác nhận response JSON chứa đúng field công khai:

```java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @Test
    void returnsPublicProductSchema() throws Exception {
        given(productService.getById(101L)).willReturn(
            new ProductResponse(
                101L,
                "Bút bi",
                new BigDecimal("12000"),
                new CategorySummary(5L, "Văn phòng phẩm")
            )
        );

        mockMvc.perform(get("/api/products/101"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.name").value("Bút bi"))
            .andExpect(jsonPath("$.category.name").value("Văn phòng phẩm"))
            .andExpect(jsonPath("$.costPrice").doesNotExist())
            .andExpect(jsonPath("$.internalNote").doesNotExist());
    }
}
```

Tên annotation mock trong ví dụ có thể khác theo phiên bản Spring Boot và test framework; có thể dùng `@MockBean` ở các phiên bản còn hỗ trợ hoặc cấu hình mock theo chuẩn dự án. Mục tiêu của test là kiểm tra payload HTTP thực tế, không chỉ kiểm tra class DTO.

Có thể bổ sung kiểm tra tài liệu OpenAPI bằng cách gọi `/v3/api-docs` trong test tích hợp:

```java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.sellingPrice"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.costPrice"
    ).doesNotExist());
```

Nếu springdoc dùng tên component khác do cấu hình hoặc quy tắc đặt tên, điều chỉnh JSONPath theo tài liệu thực tế. Với kiểm thử đầy đủ, xác nhận cả schema, response JSON, validation request và mapping entity-DTO.

## 14. Những lỗi thường gặp khi dùng entity làm API schema

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| OpenAPI xuất hiện field nội bộ | Controller trả trực tiếp entity hoặc DTO dùng chung chứa field không công khai | Tạo response DTO chỉ gồm field cần công bố |
| Schema thay đổi sau khi đổi quan hệ JPA | Entity bị dùng làm kiểu response | Dùng DTO nested/summary độc lập với quan hệ ORM |
| JSON bị lặp vô hạn hoặc quá sâu | Quan hệ entity hai chiều được serialize trực tiếp | Chuyển sang DTO có cấu trúc hữu hạn và mapping tường minh |
| Swagger UI hiển thị nhiều bảng/quan hệ không cần thiết | Schema được suy luận từ entity graph | Thiết kế DTO theo use case |
| Client gửi được `id`, `version` hoặc field chỉ dành cho server | Request bind trực tiếp vào entity | Dùng request DTO và chỉ cập nhật field cho phép |
| Schema tài liệu khác JSON runtime | Dùng `@Schema(implementation = ...)` để override nhưng vẫn trả entity | Trả DTO thực sự tương ứng với schema |
| DTO generic mất kiểu `data` | Dùng raw type hoặc wildcard | Khai báo generic cụ thể hoặc response DTO cụ thể |
| Thay đổi database làm hỏng client | Entity persistence bị coi là hợp đồng API | Quản lý DTO và versioning API độc lập với migration |

## 15. Quy trình thiết kế schema độc lập với persistence

Khi xây dựng endpoint mới, có thể thực hiện theo thứ tự:

1. Xác định dữ liệu client được phép gửi và dữ liệu server được phép trả.
2. Thiết kế request DTO và response DTO theo use case, không sao chép toàn bộ entity.
3. Định nghĩa nested DTO, summary hoặc field phẳng phù hợp trải nghiệm client.
4. Dùng validation cho request DTO và `@Schema` để bổ sung mô tả, ví dụ, format cùng ràng buộc.
5. Viết mapping rõ ràng giữa DTO và entity; kiểm tra quan hệ, quyền cập nhật và giá trị mặc định.
6. Khai báo kiểu DTO cụ thể trong chữ ký controller để springdoc suy luận schema.
7. Chỉ dùng `@Schema(implementation = ...)` khi cần điều chỉnh tài liệu và bảo đảm object runtime thực sự có cấu trúc tương ứng.
8. Kiểm tra OpenAPI JSON/YAML, Swagger UI và payload HTTP.
9. So sánh schema giữa các lần phát hành để nhận biết thay đổi hợp đồng độc lập với migration database.

Schema OpenAPI là giao diện dữ liệu mà client phụ thuộc. Entity JPA là mô hình lưu trữ mà backend có thể thay đổi để đáp ứng nhu cầu kỹ thuật. Tách hai mô hình bằng DTO và mapping tường minh giúp springdoc công bố đúng hợp đồng, tránh lộ chi tiết nội bộ và giữ client ổn định khi persistence được refactor.

## 16. Tài liệu tham khảo

- [Springdoc OpenAPI](https://springdoc.org/): suy luận schema từ controller Spring Boot và tùy chỉnh tài liệu.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): mô hình schema và thuộc tính dữ liệu trong hợp đồng API.
- [Spring Framework – Web MVC Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): cách khai báo handler, request body và response.
- [Spring Data JPA – Entity Persistence](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): mô hình entity và persistence.
- [MapStruct Reference Guide](https://mapstruct.org/documentation/stable/reference/html/): tạo mapper giữa các kiểu Java ở compile time.
