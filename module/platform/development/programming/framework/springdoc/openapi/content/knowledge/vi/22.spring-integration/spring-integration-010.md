# Các annotation trên interface và Controller kế thừa

## 1. Vì sao đặt hợp đồng API trên interface?

Trong ứng dụng Spring Boot, một controller thường vừa nhận HTTP request vừa gọi service để xử lý nghiệp vụ. Khi số lượng endpoint tăng, nhóm phát triển có thể muốn tách phần mô tả hợp đồng HTTP khỏi phần triển khai để nhiều controller, adapter hoặc phiên bản API dùng chung một quy ước.

Java interface có thể mô tả chữ ký phương thức và các annotation liên quan đến endpoint. Controller triển khai interface sẽ cung cấp phần xử lý thực tế. Spring MVC có thể phát hiện mapping trên interface method trong các cấu hình được hỗ trợ; Springdoc cũng có thể đọc OpenAPI annotation đặt trên interface để tạo operation, parameter, response và metadata.

Một mô hình thường dùng:

- **API interface** mô tả path, HTTP method, operation summary, parameter, request body và response.
- **Controller implementation** cung cấp code gọi service và trả kết quả.
- **DTO** mô tả cấu trúc dữ liệu request/response bằng kiểu Java và schema annotation.
- **Springdoc** kết hợp handler mapping với metadata OpenAPI để tạo tài liệu JSON/YAML.

Cách tổ chức này giúp hợp đồng API dễ tái sử dụng và controller ít annotation mô tả hơn. Tuy nhiên, cần hiểu chính xác cách Java, Spring Framework và Springdoc tìm annotation trên interface, superclass và method được override.

## 2. Ba cơ chế cần phân biệt

Khi đặt annotation trên interface hoặc superclass, có ba cơ chế khác nhau:

1. **Java annotation inheritance**: quy tắc của ngôn ngữ Java về annotation được đánh dấu @Inherited.
2. **Spring annotation lookup**: Spring Framework có cơ chế tìm annotation hợp nhất trên class, interface, method và method được override.
3. **Springdoc metadata resolution**: Springdoc đọc handler method và Swagger annotations để xây dựng OpenAPI model.

Không nên gộp ba cơ chế này thành một quy tắc duy nhất. Một annotation có thể được Spring MVC nhận diện để đăng ký route, nhưng annotation OpenAPI tương ứng chưa chắc được Springdoc diễn giải giống hệt trong mọi phiên bản.

Ví dụ, Java annotation @Inherited chỉ áp dụng cho annotation trên class và chuỗi superclass. Nó không làm annotation tự động kế thừa từ interface, cũng không áp dụng cho method hoặc parameter annotation. Spring Framework có thể tìm annotation trên interface bằng các API merged-annotation riêng; đó là hành vi của framework, không phải quy tắc @Inherited của Java.

Vì vậy, sau khi đặt annotation trên interface hoặc base controller, hãy kiểm tra cả mapping runtime lẫn OpenAPI document được sinh.

## 3. Những annotation thường đặt trên API interface

Các annotation sau thường hữu ích khi định nghĩa hợp đồng:

| Annotation | Mục đích |
|---|---|
| @RequestMapping, @GetMapping, @PostMapping | Khai báo URL và HTTP method |
| @Operation | Summary, description, operationId và metadata operation |
| @ApiResponses, @ApiResponse | Mô tả status code và response |
| @Parameter | Mô tả path/query/header/cookie parameter |
| @Parameters | Gom nhiều parameter annotation |
| @RequestBody | Mô tả request body của OpenAPI |
| @Tag | Nhóm operation trong tài liệu |
| @SecurityRequirement | Gắn yêu cầu bảo mật cho operation |
| @Hidden | Ẩn endpoint hoặc thành phần khỏi tài liệu theo phạm vi hỗ trợ |
| @Schema | Mô tả DTO, property, enum và validation metadata |

Cần phân biệt annotation của Spring MVC với annotation của Swagger:

- org.springframework.web.bind.annotation.RequestBody đánh dấu tham số nhận HTTP body.
- io.swagger.v3.oas.annotations.parameters.RequestBody bổ sung mô tả OpenAPI cho request body.

Hai annotation có tên giống nhau nhưng vai trò khác nhau. Có thể dùng cả hai trên cùng tham số, với import chính xác.

## 4. Định nghĩa API interface với mapping và OpenAPI metadata

Ví dụ interface mô tả endpoint lấy sản phẩm:

~~~java
@RequestMapping("/api/products")
public interface ProductApi {

    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo mã",
        description = "Trả về thông tin chi tiết của một sản phẩm."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy sản phẩm",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    @GetMapping("/{id}")
    ProductResponse findById(
        @Parameter(
            description = "Mã định danh sản phẩm",
            example = "42"
        )
        @PathVariable("id") Long id
    );
}
~~~

Interface chứa mapping và metadata cho OpenAPI. Nó không cần biết service hoặc repository cụ thể nào sẽ thực hiện truy vấn.

Khi dùng @RequestMapping ở cấp interface, các mapping method bên dưới được kết hợp với base path theo quy tắc Spring MVC. Hãy kiểm tra URL cuối cùng bằng cách gọi endpoint hoặc xem handler mapping, đặc biệt khi controller implementation còn khai báo class-level mapping khác.

Không nên lặp lại cùng base path ở cả interface và implementation. Việc khai báo hai nguồn mapping có thể dẫn tới path bị ghép ngoài dự kiến hoặc mapping mơ hồ.

## 5. Controller triển khai interface

Controller triển khai interface và cung cấp phần xử lý:

~~~java
@RestController
public class ProductController implements ProductApi {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @Override
    public ProductResponse findById(Long id) {
        return productService.findById(id);
    }
}
~~~

Trong mô hình này:

- Spring MVC đăng ký endpoint từ mapping được phát hiện trên contract/interface theo khả năng của phiên bản Spring.
- Controller implementation cung cấp thân phương thức.
- Springdoc đọc mapping và metadata OpenAPI để tạo operation.
- DTO ProductResponse được dùng làm kiểu response và schema.

Không cần sao chép @GetMapping và @Operation lên implementation nếu interface đã là nguồn hợp đồng và việc resolve annotation hoạt động đúng trong phiên bản dự án. Nếu có annotation ở cả hai nơi, cần xác định rõ annotation nào là nguồn chính và kiểm tra kết quả cuối cùng.

## 6. Nên đặt mapping ở interface hay implementation?

Có thể đặt mapping ở interface hoặc controller implementation. Điều quan trọng là chọn một quy ước nhất quán.

| Cách đặt | Khi phù hợp | Điểm cần kiểm tra |
|---|---|---|
| Mapping ở interface | Muốn contract độc lập với implementation và tái sử dụng | Spring MVC và Springdoc phải nhận diện annotation interface |
| Mapping ở implementation | Controller tự quản lý route và không cần chia sẻ contract | Metadata OpenAPI có thể nằm cùng code triển khai |
| Mapping ở superclass | Nhiều controller chia sẻ handler method hoặc base path | Kiểm tra method được kế thừa và generic type |
| Mapping ở cả interface và implementation | Chỉ dùng khi có chủ đích rõ ràng | Tránh khai báo trùng hoặc tạo mapping không tương thích |

Một quy tắc thực tế là đặt mapping và mô tả OpenAPI trên interface, còn controller implementation chỉ triển khai logic. Nếu dự án có convention khác, hãy giữ convention đó nhất quán và thêm test xác nhận mapping.

## 7. Annotation trên interface method và quy tắc @Inherited

Một hiểu lầm phổ biến là annotation trên interface sẽ tự động được kế thừa vì controller implements interface. Điều đó không đúng theo Java language rule của @Inherited.

@Inherited chỉ ảnh hưởng annotation được đặt trên class khi annotation type có gắn @Inherited. Nó không áp dụng cho:

- Annotation trên interface được một class implements.
- Annotation trên method.
- Annotation trên parameter.
- Annotation trên field.

Ví dụ:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ApiFamily {
    String value();
}
~~~

Nếu @ApiFamily được đặt trên superclass, subclass có thể nhìn thấy annotation theo quy tắc @Inherited. Nhưng nếu đặt @ApiFamily trên interface, implementing class không nhận annotation đó chỉ nhờ @Inherited.

Với Swagger annotations như @Operation, @Parameter hoặc @ApiResponse, không nên dựa vào Java @Inherited. Hãy dựa trên khả năng tìm annotation của Springdoc/Spring và xác minh bằng document thực tế.

## 8. Spring MVC tìm mapping trên interface như thế nào?

Spring Framework hỗ trợ khai báo request mapping trên controller interface trong các mô hình được hỗ trợ. Handler mapping phân tích class controller và các method để tìm mapping tương ứng, bao gồm các annotation có thể được phát hiện qua interface hierarchy.

Tuy nhiên, có một số điểm cần giữ nhất quán:

- Đặt mapping trên interface method nếu interface là API contract.
- Đặt @RequestMapping base path ở một vị trí rõ ràng.
- Không tạo mapping khác nhau trên interface và implementation cho cùng method.
- Tránh dùng cùng một interface cho nhiều controller có base path hoặc hành vi không tương thích.
- Kiểm tra URL thực tế khi method được kế thừa hoặc override.

Nếu dùng proxy hoặc cấu hình AOP đặc biệt, khả năng tìm annotation và method signature có thể chịu ảnh hưởng bởi cách framework phân giải target method. Dùng annotation nhất quán và kiểm thử ở tầng Spring MVC sẽ giúp phát hiện vấn đề sớm.

## 9. Controller kế thừa method từ abstract base class

Ngoài interface, controller có thể kế thừa handler method từ một superclass:

~~~java
public abstract class BaseReadController<T, ID> {

    protected abstract T loadById(ID id);

    @GetMapping("/{id}")
    public ResponseEntity<T> getById(@PathVariable ID id) {
        return ResponseEntity.ok(loadById(id));
    }
}
~~~

Controller cụ thể:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController
        extends BaseReadController<ProductResponse, Long> {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @Override
    protected ProductResponse loadById(Long id) {
        return productService.findById(id);
    }
}
~~~

Spring MVC có thể phát hiện handler method được kế thừa từ superclass. Path cuối cùng là /api/products/{id}. Method getById được định nghĩa ở base class, còn dữ liệu cụ thể được cung cấp bởi loadById trong subclass.

Đối với OpenAPI, method kế thừa có thể được Springdoc nhận diện như operation của controller cụ thể. Tuy nhiên, schema response generic T có thể cần kiểm tra kỹ nếu type resolution không suy ra được ProductResponse trong cấu hình hoặc phiên bản đang dùng.

## 10. Đặt OpenAPI annotation trên superclass

Có thể đặt @Operation và response metadata trực tiếp trên method của base class:

~~~java
public abstract class BaseReadController<T, ID> {

    @Operation(
        summary = "Lấy tài nguyên theo mã",
        description = "Đọc một tài nguyên theo định danh."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy tài nguyên"
    )
    @GetMapping("/{id}")
    public ResponseEntity<T> getById(
        @PathVariable ID id
    ) {
        return ResponseEntity.ok(loadById(id));
    }

    protected abstract T loadById(ID id);
}
~~~

Các controller con có thể dùng chung mô tả operation. Tuy nhiên, description chung có thể quá trừu tượng với tài nguyên cụ thể. Nếu mỗi controller cần summary, response hoặc error semantics khác nhau, có thể override metadata ở một lớp phù hợp hoặc dùng interface contract riêng.

Không nên giả định annotation method của superclass tự động được kế thừa theo Java. Springdoc có thể tìm metadata từ method thực tế mà HandlerMethod tham chiếu, nhưng khi subclass override method, việc tìm annotation trên method bị override cần được kiểm tra trong phiên bản framework đang dùng.

## 11. Override method và xung đột annotation

Khi subclass override một handler method, annotation trên method của superclass không tự động sao chép sang method override theo Java reflection.

Ví dụ:

~~~java
public abstract class BaseController {

    @Operation(summary = "Thao tác chung")
    @GetMapping("/status")
    public abstract StatusResponse status();
}
~~~

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController extends BaseController {

    @Override
    public StatusResponse status() {
        return productService.status();
    }
}
~~~

Trong trường hợp này, method được override không có annotation trực tiếp. Spring có cơ chế tìm merged annotations và mapping metadata qua method hierarchy, nhưng cách resolve của từng loại annotation không giống quy tắc kế thừa Java thông thường.

Nếu operation metadata phải ổn định, có thể đặt annotation trên interface method hoặc khai báo rõ trên implementation method. Tránh khai báo hai summary hoặc response khác nhau ở superclass và subclass mà không có quy tắc ưu tiên được kiểm thử.

Khi cần một operation có nội dung riêng cho subclass, khai báo rõ metadata trên method override để người bảo trì nhìn thấy ý định.

## 12. Generic base controller và schema response

Base controller generic giúp tái sử dụng handler logic:

~~~java
public abstract class BaseCrudController<T, ID> {

    @GetMapping("/{id}")
    public T getById(@PathVariable ID id) {
        return findOne(id);
    }

    protected abstract T findOne(ID id);
}
~~~

Controller cụ thể:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController
        extends BaseCrudController<ProductResponse, Long> {

    @Override
    protected ProductResponse findOne(Long id) {
        return productService.findById(id);
    }
}
~~~

Springdoc có thể cần resolve generic type từ subclass để tạo response schema. Nếu OpenAPI document hiển thị schema chung, object rỗng hoặc kiểu không đúng, hãy kiểm tra type resolution và khai báo response rõ ràng.

Ví dụ dùng @ApiResponse:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Nếu cùng base controller được dùng cho nhiều domain type, không nên hard-code ProductResponse ở base class. Có thể đặt response metadata ở interface hoặc method cụ thể của từng controller để schema đúng với từng endpoint.

## 13. Annotation trên parameter và request body của interface

API interface có thể mô tả parameter và request body cùng mapping:

~~~java
@RequestMapping("/api/products")
public interface ProductApi {

    @Operation(summary = "Tạo sản phẩm")
    @ApiResponse(
        responseCode = "201",
        description = "Tạo thành công",
        content = @Content(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
    @PostMapping
    ProductResponse create(
        @io.swagger.v3.oas.annotations.parameters.RequestBody(
            description = "Thông tin sản phẩm cần tạo",
            required = true
        )
        @org.springframework.web.bind.annotation.RequestBody
        @Valid
        ProductCreateRequest request
    );
}
~~~

Ví dụ dùng tên đầy đủ để phân biệt hai annotation có cùng tên RequestBody. Trong source code thực tế, có thể dùng import và tên rút gọn nếu không bị xung đột.

Parameter annotation cũng có thể đặt trên interface method:

~~~java
@GetMapping("/search")
List<ProductResponse> search(
    @Parameter(description = "Tên hoặc một phần tên sản phẩm")
    @RequestParam("q") String query
);
~~~

Hãy kiểm tra OpenAPI document để bảo đảm parameter được mô tả đúng vị trí, tên, required, schema và example. Nếu controller implementation khai báo tham số khác chữ ký interface, mapping và parameter metadata có thể không còn đồng nhất.

## 14. Tag và security metadata trên interface

Có thể dùng @Tag để phân nhóm API và @SecurityRequirement để mô tả bảo mật:

~~~java
@Tag(
    name = "Products",
    description = "Các operation quản lý sản phẩm"
)
@RequestMapping("/api/products")
public interface ProductApi {

    @Operation(
        summary = "Lấy sản phẩm",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    @GetMapping("/{id}")
    ProductResponse findById(@PathVariable("id") Long id);
}
~~~

Nếu nhiều controller dùng chung interface, tag trên interface có thể giúp nhóm các operation liên quan. Tuy nhiên, class-level annotation trên interface không được Java @Inherited tự động chuyển sang implementing class. Springdoc có thể đọc annotation interface tùy cơ chế scan và phiên bản; hãy xác minh tag xuất hiện trong OpenAPI document.

Một cách dễ kiểm soát là đặt @Tag trên concrete controller nếu tag thuộc riêng controller đó, còn @Operation và parameter metadata đặt trên contract method. Nếu tag thuộc contract dùng chung, có thể đặt trên interface và thêm test xác nhận.

Security requirement cũng cần được kiểm tra ở đúng cấp. Không giả định một annotation bảo mật trên interface tự động tạo security cho tất cả operation nếu tài liệu có cấu hình security toàn cục hoặc customizer ghi đè.

## 15. Interface dùng chung cho nhiều phiên bản API

Một interface có thể định nghĩa contract dùng chung cho nhiều controller hoặc API version, nhưng cần cân nhắc sự khác biệt về path và response.

Ví dụ:

~~~java
public interface ProductReadApi {

    @GetMapping("/{id}")
    @Operation(summary = "Lấy sản phẩm theo mã")
    ProductResponse findById(@PathVariable("id") Long id);
}
~~~

Các controller version khác nhau:

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductV1Controller implements ProductReadApi {
    // implementation
}
~~~

~~~java
@RestController
@RequestMapping("/api/v2/products")
public class ProductV2Controller implements ProductReadApi {
    // implementation có thể trả DTO khác nếu contract được thiết kế riêng
}
~~~

Nếu cả hai controller triển khai cùng interface, Spring MVC có thể đăng ký hai path khác nhau cho cùng signature. Springdoc cần tạo hai operation tương ứng. Tuy nhiên, một summary hoặc response schema dùng chung có thể không phù hợp nếu version 2 thay đổi semantics.

Khi API version khác nhau về request/response, nên dùng interface hoặc contract riêng cho mỗi version thay vì cố ép tất cả vào một interface generic. Chỉ chia sẻ phần thật sự giống nhau.

## 16. Nhiều interface và mapping mơ hồ

Một controller có thể implements nhiều API interface:

~~~java
@RestController
public class ProductController
        implements ProductReadApi, ProductWriteApi {
    // implementations
}
~~~

Cách này có thể hữu ích để tách contract đọc và ghi. Nhưng cần bảo đảm:

- Path và HTTP method giữa các interface không xung đột.
- OperationId là duy nhất trong toàn document.
- Tag và security requirement phản ánh đúng nhóm chức năng.
- Method signature tương thích.
- Không có hai interface định nghĩa metadata mâu thuẫn cho cùng method.
- Spring MVC chỉ đăng ký một handler mapping phù hợp cho mỗi request.

Nếu hai interface cùng khai báo GET /api/products/{id} nhưng khác response hoặc summary, controller có thể tạo mapping mơ hồ hoặc tài liệu không nhất quán. Tách endpoint hoặc hợp nhất contract trước khi triển khai.

## 17. Tạo annotation tổng hợp cho convention nội bộ

Dự án có thể tạo composed annotation để gom các metadata lặp lại. Ví dụ một annotation cho endpoint yêu cầu bearer authentication:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Operation(
    security = @SecurityRequirement(name = "bearerAuth")
)
public @interface AuthenticatedApiOperation {
}
~~~

Composed annotation có thể giảm lặp lại nếu Springdoc và Swagger Core hỗ trợ cách tìm meta-annotation tương ứng. Tuy nhiên, không phải mọi Swagger annotation đều được xử lý như Spring composed annotation trong mọi phiên bản.

Vì vậy, sau khi tạo annotation tổng hợp:

1. Xác nhận annotation được giữ ở runtime.
2. Kiểm tra target phù hợp: TYPE, METHOD hoặc PARAMETER.
3. Kiểm tra Springdoc có đọc meta-annotation đó không.
4. Tải /v3/api-docs để xác minh security hoặc metadata được sinh.
5. Nếu không được hỗ trợ, dùng annotation trực tiếp hoặc customizer.

Không tạo composed annotation chỉ để che giấu quy tắc quan trọng mà người đọc cần nhìn thấy trên API contract.

## 18. Cách kiểm tra annotation đã được Springdoc nhận diện

Sau khi khởi động ứng dụng, kiểm tra OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Tìm operation tương ứng và xác minh:

- Path và HTTP method đúng.
- Operation summary, description và operationId đúng.
- Parameter có tên, vị trí và schema chính xác.
- Request body có required, media type và schema đúng.
- Response có status code, content và schema phù hợp.
- Tag được gắn đúng operation.
- Security requirement áp dụng đúng phạm vi.
- Operation không bị lặp khi interface và implementation cùng khai báo.
- Generic response đã được resolve thành DTO cụ thể.

Nếu dùng document group, kiểm tra endpoint OpenAPI của từng group. Một operation có thể bị lọc khỏi group do path/package filter dù mapping runtime vẫn hoạt động.

Không chỉ dựa vào Swagger UI để xác minh. JSON là bằng chứng trực tiếp hơn về OpenAPI model mà Springdoc đã tạo.

## 19. Kiểm thử mapping và OpenAPI bằng MockMvc

Có thể kiểm tra endpoint runtime:

~~~java
mockMvc.perform(get("/api/products/{id}", 42))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));
~~~

Kiểm tra OpenAPI metadata:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.paths['/api/products/{id}'].get").exists())
    .andExpect(jsonPath(
        "$.paths['/api/products/{id}'].get.summary"
    ).value("Lấy sản phẩm theo mã"));
~~~

Có thể bổ sung kiểm tra response schema:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(jsonPath(
        "$.paths['/api/products/{id}'].get.responses['200']"
    ).exists());
~~~

Những test này kiểm tra hai khía cạnh khác nhau:

- Request test xác nhận Spring MVC thật sự đăng ký và xử lý endpoint.
- OpenAPI test xác nhận Springdoc mô tả endpoint và metadata đúng.

Một test pass không thay thế test còn lại. Endpoint có thể hoạt động nhưng thiếu trong tài liệu; tài liệu cũng có thể chứa operation mà runtime không còn phục vụ.

## 20. Các lỗi thường gặp với interface và inherited controller

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Mapping interface không hoạt động | Phiên bản Spring hoặc cấu hình không phát hiện interface mapping |
| Endpoint chạy nhưng thiếu @Operation metadata | Springdoc chưa resolve annotation từ interface method |
| Tag không xuất hiện | Đặt @Tag trên interface nhưng giả định Java @Inherited áp dụng |
| Annotation superclass mất sau khi override | Method annotation không được Java tự động kế thừa |
| Path bị lặp prefix | Base @RequestMapping khai báo ở cả interface và implementation |
| Operation xuất hiện hai lần | Mapping/metadata được khai báo trùng hoặc có nhiều handler |
| Generic response thành schema rỗng | Type erasure hoặc generic resolution chưa đủ thông tin |
| Parameter không đúng tên | Interface và implementation có signature/annotation khác nhau |
| Security không đúng | SecurityRequirement bị thiếu, bị override hoặc đặt ở sai cấp |
| Summary của subclass không như mong đợi | Metadata superclass/interface và override method xung đột |
| OperationId trùng | Nhiều interface hoặc controller dùng cùng operationId |
| Group thiếu endpoint | Group path/package filter không bao gồm mapping thực tế |

Khi điều tra, kiểm tra handler mapping trước, sau đó so sánh method signature và annotation hierarchy, cuối cùng kiểm tra OpenAPI JSON. Cách này giúp phân biệt lỗi route của Spring MVC với lỗi metadata của Springdoc.

## 21. Nguyên tắc tổ chức interface và controller kế thừa

Khi dùng interface hoặc base controller để chia sẻ hợp đồng API:

1. Đặt mapping ở một nguồn nhất quán: interface hoặc implementation.
2. Dùng interface cho contract khi nhiều implementation cần chia sẻ cùng HTTP signature.
3. Dùng abstract base controller khi thực sự cần chia sẻ handler logic.
4. Đặt @Operation, @ApiResponses và @Parameter tại nơi Springdoc có thể resolve và kiểm tra được.
5. Không dựa vào Java @Inherited cho interface, method hoặc parameter annotation.
6. Không khai báo annotation mâu thuẫn trên interface, superclass và override method.
7. Với generic base controller, kiểm tra response schema đã resolve thành kiểu cụ thể.
8. Đặt @Tag trên controller cụ thể nếu cần bảo đảm nhóm tài liệu rõ ràng.
9. Giữ operationId duy nhất và mapping không mơ hồ.
10. Kiểm tra cả HTTP runtime lẫn /v3/api-docs bằng test.

Interface giúp tách hợp đồng HTTP khỏi logic controller; superclass giúp tái sử dụng handler behavior; Springdoc biến metadata mà nó nhận diện thành OpenAPI document. Khi phân biệt đúng quy tắc annotation của Java với cơ chế merged annotation của Spring, đồng thời kiểm tra route và schema thực tế, nhóm phát triển có thể tái sử dụng contract mà không tạo mapping trùng hoặc tài liệu sai lệch.

