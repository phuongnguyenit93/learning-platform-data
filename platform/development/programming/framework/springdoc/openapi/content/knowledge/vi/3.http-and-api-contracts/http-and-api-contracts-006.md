# Hợp đồng kiểu dữ liệu khác với quy tắc nghiệp vụ

OpenAPI schema mô tả hình dạng và những ràng buộc có thể kiểm tra trên dữ liệu HTTP: field nào bắt buộc, kiểu dữ liệu nào được chấp nhận, chuỗi dài bao nhiêu, số nằm trong khoảng nào, enum có những giá trị gì. Những điều kiện đó tạo thành hợp đồng dữ liệu giữa client và server.

Quy tắc nghiệp vụ trả lời một câu hỏi khác: với trạng thái hiện tại của hệ thống, người dùng này có được phép thực hiện hành động đó hay không? Một request có thể hoàn toàn đúng kiểu, đúng định dạng và vượt qua Bean Validation nhưng vẫn không thể thực hiện vì sản phẩm đã ngừng bán, tồn kho không đủ, tài khoản đã khóa hoặc trạng thái đơn hàng không cho phép hủy.

Khi xây dựng API Spring Boot với springdoc-openapi, cần giữ rõ hai lớp:

- **Hợp đồng kiểu dữ liệu:** mô tả bằng OpenAPI Schema, DTO và các constraint đầu vào có tính xác định.
- **Quy tắc nghiệp vụ:** thực thi trong application/domain layer, dựa trên chính sách và trạng thái thực tế; công bố kết quả bằng response status và error schema.

Không thể thay thế kiểm tra nghiệp vụ bằng cách thêm minimum, enum hoặc required vào schema. Ngược lại, không nên đẩy lỗi JSON sai kiểu hoặc chuỗi vượt giới hạn vào sâu trong domain service khi có thể từ chối ngay ở biên HTTP.

Các ví dụ Java trong bài dùng Java 17 và Spring Boot 3+ với Jakarta Validation. Ứng dụng Spring Boot 2 cũ dùng package javax.validation và cần phiên bản thư viện tương thích; hãy giữ đúng namespace theo nền tảng của project.

## 1. Bốn lớp ràng buộc thường gặp

Một API tạo đơn hàng là ví dụ dễ thấy:

| Lớp | Câu hỏi | Ví dụ | Nơi xử lý phù hợp |
|---|---|---|---|
| Cú pháp và kiểu dữ liệu | Body có parse được và đúng kiểu không? | quantity là integer, productId là UUID | HTTP message conversion, DTO |
| Constraint đầu vào | Giá trị có nằm trong giới hạn khai báo không? | quantity lớn hơn 0, tên không rỗng | Jakarta Bean Validation |
| Quy tắc nghiệp vụ | Hành động có hợp lệ trong ngữ cảnh hiện tại không? | Sản phẩm đang bán, khách hàng đủ điều kiện mua | Domain/application service |
| Toàn vẹn dữ liệu | Có vi phạm invariant khi nhiều request chạy đồng thời không? | SKU duy nhất trong tenant, số lượng tồn không âm | Database constraint và transaction |

Các lớp này bổ trợ nhau. Một constraint ở lớp DTO không bảo đảm database không có dữ liệu trùng do hai request chạy cùng lúc. Một database constraint cũng không thay thế response lỗi rõ ràng cho client.

Ví dụ request sau có thể hợp lệ về kiểu và constraint:

~~~json
{
  "productId": "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61",
  "quantity": 2,
  "deliveryMode": "STANDARD"
}
~~~

Nhưng server vẫn có thể từ chối vì sản phẩm không tồn tại, không còn được bán hoặc chỉ còn một đơn vị trong kho. Những điều kiện này không thể được quyết định chỉ từ ba field của request.

## 2. Hợp đồng dữ liệu mô tả điều gì?

OpenAPI Schema Object mô tả cấu trúc của representation mà API nhận hoặc trả. Các keyword thường gặp gồm:

| Keyword | Ý nghĩa | Ví dụ |
|---|---|---|
| type | Kiểu JSON | string, integer, number, boolean, object, array |
| required | Danh sách property bắt buộc trong object | required: [productId, quantity] |
| format | Gợi ý định dạng của một kiểu | uuid, date, date-time, email |
| enum | Tập giá trị được chấp nhận | [STANDARD, EXPRESS] |
| minLength, maxLength | Độ dài chuỗi | Tên từ 1 đến 80 ký tự |
| minimum, maximum | Giới hạn số | minimum: 1 |
| pattern | Biểu thức chính quy | Mã hàng theo mẫu cố định |
| minItems, maxItems | Số phần tử của array | Tối đa 50 sản phẩm |
| items | Schema của từng phần tử | Mảng UUID hoặc object |
| additionalProperties | Có cho phép property ngoài danh sách không | Cấm field lạ khi cần |

Các keyword này hữu ích khi quy tắc có thể được xác định từ chính representation. Chúng không tự truy vấn database, không biết user hiện tại thuộc tenant nào, không đọc trạng thái đơn hàng và không khóa tồn kho.

format cũng cần được hiểu đúng: một số công cụ chỉ coi format là annotation để hiển thị, không thực hiện kiểm tra định dạng nghiêm ngặt. Nếu format quan trọng, cần kiểm tra cấu hình validator và vẫn xác thực dữ liệu ở server.

## 3. Quy tắc nghiệp vụ phụ thuộc vào điều gì?

Quy tắc nghiệp vụ thường phụ thuộc vào ít nhất một yếu tố nằm ngoài body hiện tại:

- Trạng thái của aggregate hoặc resource trong database.
- Danh tính, role, scope hoặc tenant của người gọi.
- Thời gian hiện tại, thời hạn hoặc lịch làm việc.
- Tồn kho, hạn mức, số dư hoặc quota còn lại.
- Trạng thái của một resource khác.
- Lịch sử giao dịch hoặc chính sách đã được cấu hình.
- Kết quả của một thao tác đồng thời từ request khác.

Ví dụ:

| Quy tắc | Vì sao không chỉ là schema constraint? |
|---|---|
| SKU phải duy nhất trong tenant | Cần so sánh với dữ liệu đã tồn tại và tenant của người gọi |
| Chỉ bán sản phẩm đang ACTIVE | Phụ thuộc trạng thái hiện tại của sản phẩm |
| Không đặt số lượng vượt tồn kho | Tồn kho thay đổi liên tục và có cạnh tranh đồng thời |
| Chỉ chủ đơn hàng mới được hủy | Phụ thuộc principal và quyền sở hữu resource |
| Chỉ hủy đơn trước khi giao | Phụ thuộc trạng thái đơn hàng tại thời điểm xử lý |
| Chiết khấu không vượt ngân sách chiến dịch | Phụ thuộc chính sách và ngân sách còn lại |
| Chuyển tiền không vượt số dư khả dụng | Phụ thuộc số dư, giao dịch đồng thời và quy tắc kế toán |

Có thể mô tả các điều kiện này trong description, operation documentation và error responses của OpenAPI. Nhưng mô tả không phải là cơ chế thực thi; server phải kiểm tra chúng ở đúng tầng.

## 4. Phân biệt constraint đơn trường, constraint nhiều trường và invariant domain

Không phải mọi quy tắc liên quan nhiều field đều cần đưa vào domain model. Hãy xét dữ liệu cần thiết để quyết định:

1. **Constraint đơn trường:** chỉ phụ thuộc một giá trị, ví dụ quantity phải dương.
2. **Constraint giữa các field của cùng request:** chỉ phụ thuộc payload, ví dụ startDate phải trước endDate.
3. **Invariant domain:** phụ thuộc trạng thái hoặc chính sách của hệ thống, ví dụ ngày giao phải nằm trong lịch hoạt động của kho được chọn.

Constraint giữa các field có thể được kiểm tra bằng class-level Bean Validation nếu nó là điều kiện xác định từ payload. Ví dụ ngày bắt đầu phải trước ngày kết thúc:

~~~java
@ValidDateRange
public record CreateCampaignRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

Validator @ValidDateRange có thể so sánh hai field mà không cần gọi database. Nếu điều kiện phụ thuộc vào múi giờ của cửa hàng, lịch nghỉ được cấu hình hoặc chiến dịch khác đang hoạt động, đó là policy cần được đánh giá ở application/domain layer.

@ValidDateRange ở đây là tên minh họa cho custom constraint; dự án cần khai báo annotation và ConstraintValidator tương ứng, hoặc dùng validator hiện có.

Ranh giới không nằm ở việc rule có dùng nhiều field hay không. Ranh giới nằm ở việc rule có thể quyết định chỉ từ request hay cần ngữ cảnh có thẩm quyền của hệ thống.

## 5. Thiết kế DTO request với Bean Validation

DTO ở biên HTTP nên thể hiện rõ dữ liệu client được phép gửi và constraint có thể kiểm tra độc lập:

~~~java
public record CreateOrderRequest(
    @NotNull
    UUID productId,

    @NotNull
    @Positive
    Integer quantity,

    @NotNull
    DeliveryMode deliveryMode,

    @Size(max = 200)
    String note
) {}
~~~

Enum:

~~~java
public enum DeliveryMode {
    STANDARD,
    EXPRESS
}
~~~

Controller kích hoạt validation:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderApplicationService orderService;

    OrderController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity
            .created(URI.create("/api/orders/" + created.id()))
            .body(created);
    }
}
~~~

@NotNull, @Positive và @Size kiểm tra các điều kiện đầu vào cục bộ. Chúng không xác minh productId có tồn tại hay người dùng có được mua sản phẩm đó không.

Với @RequestBody, Spring MVC dùng HttpMessageConverter để deserialize body trước khi gọi controller. Sau đó @Valid hoặc @Validated kích hoạt Bean Validation. JSON sai cú pháp hoặc không thể chuyển sang kiểu Java thường bị từ chối ở bước conversion; dữ liệu parse được nhưng vi phạm constraint bị từ chối ở bước validation.

## 6. Đừng đưa trạng thái database vào DTO như một constraint giả

Một thiết kế dễ gây nhầm là tạo custom validator để query repository:

~~~java
// Không khuyến nghị cho request DTO thông thường
@ExistingActiveProduct
UUID productId;
~~~

Validator kiểu này có thể chạy được, nhưng làm DTO phụ thuộc persistence, khó kiểm soát transaction và dễ kiểm tra sai khi trạng thái thay đổi giữa lúc validation và lúc ghi dữ liệu.

Ví dụ: validator xác nhận sản phẩm đang ACTIVE lúc 10:00:00.001. Một quản trị viên tạm ngừng sản phẩm lúc 10:00:00.005. Request tạo đơn tiếp tục chạy lúc 10:00:00.010. Kết quả validation cũ không còn phản ánh trạng thái tại thời điểm nghiệp vụ được thực hiện.

Hãy giữ DTO validator cho những điều kiện ổn định, cục bộ và có thể quyết định từ payload. Truy vấn dữ liệu và áp dụng policy trong service/domain transaction.

## 7. Thực thi quy tắc nghiệp vụ trong application/domain layer

Application service điều phối use case; domain object hoặc policy chứa quyết định nghiệp vụ. Ví dụ:

~~~java
@Service
class OrderApplicationService {

    private final ProductRepository products;
    private final InventoryService inventory;
    private final OrderRepository orders;

    @Transactional
    public OrderResponse create(CreateOrderRequest request) {
        Product product = products.findById(request.productId())
            .orElseThrow(ProductNotFoundException::new);

        product.ensurePurchasable(request.quantity());

        inventory.reserve(product.id(), request.quantity());

        Order order = Order.create(
            product.id(),
            request.quantity(),
            request.deliveryMode(),
            request.note()
        );

        return OrderResponse.from(orders.save(order));
    }
}
~~~

ensurePurchasable có thể kiểm tra trạng thái sản phẩm, ngày bắt đầu/kết thúc bán hoặc policy của domain. inventory.reserve chịu trách nhiệm giữ số lượng tồn theo cơ chế an toàn khi có request đồng thời.

Không để controller tự quyết định quy tắc như “nếu tồn kho lớn hơn quantity thì tạo đơn”. Khi quy tắc nằm rải rác ở controller, batch job và message consumer có thể áp dụng hành vi khác nhau. Đưa invariant vào domain/application service giúp mọi entry point dùng cùng policy.

## 8. Quy tắc nghiệp vụ phải an toàn trước cạnh tranh đồng thời

Một lỗi phổ biến là kiểm tra trước rồi mới ghi:

~~~java
if (inventoryRepository.getAvailable(productId) >= quantity) {
    inventoryRepository.decrease(productId, quantity);
}
~~~

Hai request có thể cùng đọc số lượng tồn là 5, mỗi request đặt 4 sản phẩm, rồi cả hai cùng đi tiếp. Chỉ kiểm tra ở Java không ngăn được race condition.

Với database quan hệ, có thể dùng câu lệnh cập nhật có điều kiện để kiểm tra và trừ tồn trong cùng một thao tác nguyên tử:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

Sau khi chạy, kiểm tra số dòng được cập nhật:

- Một dòng: giữ chỗ thành công.
- Không dòng nào: sản phẩm không tồn tại hoặc số lượng không còn đủ; xác định lỗi cụ thể theo policy và truy vấn cần thiết.

Một lựa chọn khác là optimistic locking với version field hoặc pessimistic locking tùy workload. Dù dùng cách nào, transaction và database phải bảo vệ invariant cuối cùng; OpenAPI schema không thể làm việc này.

## 9. Ví dụ SKU duy nhất và giới hạn của kiểm tra trước

Giả sử SKU chỉ cần duy nhất trong từng tenant. DTO có thể kiểm tra định dạng:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Pattern(regexp = "^[A-Z0-9-]{3,32}$")
    String sku,

    @NotBlank
    @Size(max = 120)
    String name
) {}
~~~

Định dạng SKU là constraint của request. Tính duy nhất là invariant phụ thuộc database:

~~~java
if (productRepository.existsByTenantIdAndSku(tenantId, request.sku())) {
    throw new DuplicateSkuException(request.sku());
}
~~~

Kiểm tra trước giúp trả lỗi thân thiện, nhưng không đủ để bảo đảm duy nhất vì hai transaction có thể cùng kiểm tra trước khi transaction nào ghi dữ liệu.

Database cần unique constraint phù hợp:

~~~sql
ALTER TABLE product
ADD CONSTRAINT uk_product_tenant_sku UNIQUE (tenant_id, sku);
~~~

Khi constraint bị vi phạm, application phải chuyển lỗi persistence thành lỗi nghiệp vụ/API ổn định, chẳng hạn SKU_ALREADY_EXISTS với HTTP 409. Không trả SQL, tên bảng hoặc stack trace cho client.

## 10. Mô tả hợp đồng dữ liệu trong OpenAPI

OpenAPI nên phản ánh chính xác các constraint của request DTO. Ví dụ:

~~~yaml
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - productId
        - quantity
        - deliveryMode
      properties:
        productId:
          type: string
          format: uuid
        quantity:
          type: integer
          minimum: 1
        deliveryMode:
          type: string
          enum:
            - STANDARD
            - EXPRESS
        note:
          type: string
          maxLength: 200
~~~

Schema cho biết client cần gửi UUID, quantity là integer tối thiểu 1 và deliveryMode thuộc enum. Schema không nói sản phẩm có đang được bán hay còn đủ tồn kho.

Với springdoc, có thể dùng Swagger annotations để bổ sung mô tả:

~~~java
@Schema(name = "CreateOrderRequest")
public record CreateOrderRequest(
    @Schema(
        description = "Định danh sản phẩm cần mua.",
        example = "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61"
    )
    @NotNull
    UUID productId,

    @Schema(
        description = "Số lượng phải là số nguyên dương.",
        minimum = "1",
        example = "2"
    )
    @NotNull
    @Positive
    Integer quantity,

    @NotNull
    DeliveryMode deliveryMode,

    @Size(max = 200)
    String note
) {}
~~~

Springdoc có thể suy ra một số schema constraints từ Bean Validation annotations. Kết quả cụ thể còn phụ thuộc phiên bản, loại annotation, validation group và cấu hình. Kiểm tra /v3/api-docs để xác nhận schema được sinh ra; đừng giả định mọi custom validator đều được chuyển thành JSON Schema.

## 11. Mô tả quy tắc nghiệp vụ bằng description và error responses

Quy tắc động vẫn cần được công bố để client biết request hợp lệ về cấu trúc có thể bị từ chối vì lý do nào:

~~~java
@Operation(
    summary = "Tạo đơn hàng",
    description = """
        Tạo đơn hàng cho sản phẩm đang được phép bán.
        Request phải có quantity là số nguyên dương.
        Server kiểm tra trạng thái sản phẩm và tồn kho tại thời điểm xử lý.
        Nếu sản phẩm không còn bán hoặc tồn kho không đủ, API trả lỗi nghiệp vụ.
        """
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng được tạo"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Request body sai kiểu hoặc vi phạm constraint đầu vào"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm"
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Sản phẩm không còn bán hoặc tồn kho không đủ"
    )
})
~~~

description giúp người tích hợp hiểu rule, còn response status giúp client xử lý kết quả. Không đặt một giá trị maximum giả cho quantity chỉ vì tồn kho hiện tại đang là 20; tồn kho có thể thay đổi ngay sau khi document được sinh.

## 12. Chọn HTTP status theo bản chất lỗi

Status code cần phản ánh lý do request không được xử lý. Một policy phổ biến:

| Status | Dùng khi | Ví dụ |
|---|---|---|
| 400 Bad Request | Body sai cú pháp, sai kiểu hoặc vi phạm constraint request | quantity là chuỗi, thiếu field bắt buộc |
| 401 Unauthorized | Thiếu hoặc không có credential hợp lệ | JWT hết hạn |
| 403 Forbidden | Người gọi không được phép thực hiện hành động | Không có quyền tạo đơn trong tenant |
| 404 Not Found | Resource cần thiết không tồn tại hoặc được ẩn theo policy | Không tìm thấy productId |
| 409 Conflict | Không thể thực hiện vì xung đột với trạng thái hiện tại | SKU trùng, đơn đã được thanh toán, tồn kho thay đổi |
| 412 Precondition Failed | Điều kiện HTTP precondition không còn đúng | ETag/If-Match không khớp |
| 422 Unprocessable Content | Server hiểu content type và cú pháp nhưng không thể xử lý chỉ dẫn trong nội dung theo semantics của API | Payload đúng cú pháp nhưng vi phạm quy tắc xử lý mà API quy ước trả 422 |

400 và 422 có thể được các API chọn khác nhau cho lỗi validation. Điều quan trọng là chọn policy nhất quán, ghi rõ trong OpenAPI và không trả 500 cho lỗi đầu vào hoặc xung đột nghiệp vụ có thể dự đoán.

409 đặc biệt phù hợp khi request xung đột với trạng thái hiện tại của resource. Nếu API dùng 422 cho một số lỗi semantic, hãy giữ sự phân biệt ổn định để client không phải đoán.

## 13. Tạo error contract ổn định

Đừng để client phụ thuộc vào message exception hoặc cấu trúc lỗi mặc định thay đổi theo framework. Có thể dùng Problem Details và thêm error code ổn định:

~~~java
public record ApiProblem(
    URI type,
    String title,
    int status,
    String detail,
    String code,
    List<FieldViolation> violations
) {}

public record FieldViolation(
    String field,
    String code,
    String message
) {}
~~~

Ví dụ lỗi validation:

~~~json
{
  "type": "https://api.example.com/problems/request-validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {
      "field": "quantity",
      "code": "POSITIVE",
      "message": "Quantity must be greater than zero."
    }
  ]
}
~~~

Ví dụ lỗi nghiệp vụ:

~~~json
{
  "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Order cannot be created",
  "status": 409,
  "detail": "The requested quantity is no longer available.",
  "code": "INSUFFICIENT_STOCK",
  "violations": []
}
~~~

Error contract nên phân biệt lỗi field với lỗi use case. violations phù hợp cho field-level validation; code ở cấp problem giúp client nhận diện lỗi nghiệp vụ mà không parse chuỗi detail.

## 14. Ánh xạ lỗi validation và lỗi domain trong Spring Boot

Có thể xử lý lỗi đầu vào và lỗi nghiệp vụ ở @RestControllerAdvice:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiProblem> handleInvalidBody(
            MethodArgumentNotValidException exception) {
        List<FieldViolation> violations =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    toApiCode(error),
                    "The supplied value is invalid."
                ))
                .toList();

        ApiProblem problem = new ApiProblem(
            URI.create("https://api.example.com/problems/request-validation"),
            "Request validation failed",
            400,
            "One or more request fields are invalid.",
            "REQUEST_VALIDATION_FAILED",
            violations
        );
        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(InsufficientStockException.class)
    ResponseEntity<ApiProblem> handleInsufficientStock(
            InsufficientStockException exception) {
        ApiProblem problem = new ApiProblem(
            URI.create("https://api.example.com/problems/insufficient-stock"),
            "Order cannot be created",
            409,
            "The requested quantity is no longer available.",
            "INSUFFICIENT_STOCK",
            List.of()
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
~~~

Đây là ví dụ rút gọn cho request body validation và một lỗi domain. Ứng dụng dùng method validation có thể cần xử lý thêm HandlerMethodValidationException; lỗi parse JSON hoặc type conversion có thể đi qua exception khác. Chuẩn hóa chúng theo cùng error contract, nhưng giữ mã lỗi phản ánh đúng nguyên nhân.

toApiCode là helper của ứng dụng, ánh xạ constraint hoặc lỗi binding sang mã công khai ổn định như NOT_NULL, POSITIVE hoặc INVALID_FORMAT. Không nên công bố trực tiếp message code nội bộ của Spring làm contract nếu muốn client không phụ thuộc framework.

Không biến mọi exception thành 400. Lỗi lập trình, lỗi dependency hoặc lỗi không dự kiến vẫn phải được xử lý như server error và ghi log nội bộ có correlation ID.

## 15. Đừng để OpenAPI schema hứa điều server không bảo đảm

Một schema có thể vô tình công bố constraint sai hoặc quá chặt:

- maximum được đặt theo tồn kho hiện tại.
- enum chứa trạng thái thay đổi theo cấu hình hoặc tenant nhưng lại được cố định như tập giá trị toàn cục.
- required đánh dấu field mà server thực tế cho phép bỏ qua.
- format: email được coi là chứng minh địa chỉ email tồn tại.
- uniqueItems: true được dùng để ám chỉ SKU duy nhất trong database.
- pattern được dùng thay cho việc kiểm tra quyền sở hữu resource.

Schema cần phản ánh contract có thể dự đoán và ổn định. Nếu danh sách lựa chọn thay đổi theo user/tenant, có thể mô tả kiểu dữ liệu tổng quát trong schema và cung cấp endpoint lấy lựa chọn hợp lệ hoặc mô tả rule động trong operation.

uniqueItems chỉ kiểm tra các phần tử trong một array của payload có trùng nhau theo semantics JSON Schema hay không. Nó không kiểm tra một giá trị có trùng với record đã lưu trong database hay không.

## 16. Tách request DTO và response DTO

Không nên dùng một entity persistence làm request body và response body chỉ vì chúng có cùng một số field. Entity thường chứa field nội bộ, trạng thái server quản lý, quan hệ persistence và quy tắc không thuộc public contract.

Ví dụ:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotNull
    @Positive
    BigDecimal price
) {}

public record ProductResponse(
    UUID id,
    String name,
    BigDecimal price,
    ProductStatus status,
    Instant createdAt
) {}
~~~

Client không được gửi id, status hoặc createdAt khi tạo sản phẩm nếu các field này do server quản lý. Response có thể công bố chúng như dữ liệu chỉ đọc.

DTO riêng giúp OpenAPI tạo hai schema có ý nghĩa khác nhau, làm rõ field nào client được phép điều khiển và field nào do server quyết định. Nó cũng giảm nguy cơ mass assignment khi Jackson bind trực tiếp request vào entity.

## 17. Kiểm thử từng lớp ràng buộc

Một bộ test tốt cần kiểm tra đúng tầng:

| Test | Điều cần xác minh | Ví dụ |
|---|---|---|
| DTO validation test | Constraint request cục bộ | quantity bằng 0 bị từ chối |
| Controller test | Status và error body tại HTTP boundary | request sai trả 400 |
| Domain unit test | Invariant và policy | sản phẩm DISCONTINUED không thể bán |
| Application service test | Điều phối repository và domain | product không tồn tại trả domain error |
| Persistence integration test | Unique/FK/check constraint | hai request không thể tạo SKU trùng |
| Concurrency test | Invariant khi có nhiều transaction | tồn kho không âm sau các request đồng thời |
| OpenAPI contract test | Document phản ánh request/response | quantity có type integer và minimum 1 |

Không dùng một test OpenAPI để chứng minh rule nghiệp vụ chạy đúng. Ngược lại, domain unit test không chứng minh /v3/api-docs đã mô tả response 409.

## 18. Kiểm thử DTO và Bean Validation

Ví dụ kiểm tra DTO độc lập:

~~~java
class CreateOrderRequestValidationTest {

    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void rejectsZeroQuantity() {
        CreateOrderRequest request = new CreateOrderRequest(
            UUID.randomUUID(),
            0,
            DeliveryMode.STANDARD,
            null
        );

        Set<ConstraintViolation<CreateOrderRequest>> violations =
            validator.validate(request);

        assertThat(violations).anySatisfy(violation ->
            assertThat(violation.getPropertyPath().toString())
                .isEqualTo("quantity")
        );
    }
}
~~~

Test này không cần database vì quantity dương là constraint cục bộ. Không mock repository để kiểm tra @Positive; test đúng nhiệm vụ của Bean Validation.

## 19. Kiểm thử quy tắc nghiệp vụ

Ví dụ domain unit test:

~~~java
class ProductTest {

    @Test
    void discontinuedProductCannotBePurchased() {
        Product product = Product.discontinued(
            UUID.randomUUID(),
            "PEN-1024"
        );

        assertThatThrownBy(() -> product.ensurePurchasable(1))
            .isInstanceOf(ProductNotPurchasableException.class);
    }
}
~~~

Test domain không cần HTTP status hoặc OpenAPI annotations. Nó xác minh invariant độc lập với cách API trình bày lỗi.

Ở application service test, xác minh khi sản phẩm không tồn tại hoặc tồn kho không đủ thì không tạo Order và không phát sinh side effect không hợp lệ. Với transaction và persistence constraint, dùng integration test trên database phù hợp để kiểm tra hành vi thực tế.

## 20. Kiểm thử HTTP contract và OpenAPI document

MockMvc có thể kiểm tra request sai constraint trả 400:

~~~java
@Test
void invalidQuantityReturnsBadRequest() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61",
                  "quantity": 0,
                  "deliveryMode": "STANDARD"
                }
                """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value(
            "REQUEST_VALIDATION_FAILED"
        ))
        .andExpect(jsonPath("$.violations[0].field").value("quantity"));
}
~~~

Và kiểm tra request đúng kiểu nhưng vi phạm nghiệp vụ trả 409:

~~~java
@Test
void unavailableProductReturnsBusinessConflict() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "cbd37c4a-6f6b-4ed9-bad2-77e8ec4d3f61",
                  "quantity": 2,
                  "deliveryMode": "STANDARD"
                }
                """))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("INSUFFICIENT_STOCK"));
}
~~~

Test thứ hai cần fixture sản phẩm và tồn kho xác định để tái hiện lỗi. Hai request có cùng shape, nhưng kết quả khác nhau vì trạng thái hệ thống khác nhau.

Test OpenAPI document riêng:

~~~java
@Test
void documentsInputConstraintAndBusinessErrorResponse() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.CreateOrderRequest.properties.quantity.type"
        ).value("integer"))
        .andExpect(jsonPath(
            "$.components.schemas.CreateOrderRequest.properties.quantity.minimum"
        ).value(1))
        .andExpect(jsonPath(
            "$.paths['/api/orders'].post.responses['409']"
        ).exists());
}
~~~

Đường dẫn JSONPath và tên schema phụ thuộc cấu hình naming của project. Điều quan trọng là document công bố cả constraint request có thể kiểm tra tĩnh lẫn các business error response mà operation có thể trả.

## 21. Lỗi thường gặp khi trộn schema và quy tắc nghiệp vụ

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Swagger UI báo quantity tối đa 5 dù tồn kho thay đổi | Đưa tồn kho hiện tại vào maximum | Giữ schema theo giới hạn ổn định; trả lỗi nghiệp vụ khi tồn kho thiếu |
| Request có UUID hợp lệ nhưng API trả 404 | Nhầm format UUID với sự tồn tại của resource | Mô tả 404 và kiểm tra repository ở service |
| Bean Validation query database | DTO phụ thuộc persistence và trạng thái có thể thay đổi | Chuyển rule sang application/domain layer |
| SKU trùng khi hai request chạy cùng lúc | Chỉ dùng existsBy... trước khi insert | Thêm unique constraint và xử lý conflict |
| Domain test phải khởi tạo Spring context | Logic nghiệp vụ nằm trong controller hoặc service quá phụ thuộc framework | Đưa invariant vào domain/policy có thể unit test |
| OpenAPI có minimum nhưng server vẫn nhận giá trị nhỏ | Schema annotation không tương đương runtime validation | Thêm Bean Validation và test HTTP |
| API trả 500 cho SKU trùng | Persistence exception chưa được ánh xạ | Chuyển thành error code và status 409 |
| Client phải parse message để biết lỗi | Error contract thiếu mã ổn định | Cung cấp problem code và schema lỗi |
| uniqueItems được hiểu là SKU duy nhất toàn hệ thống | Nhầm uniqueness trong array với uniqueness trong database | Dùng database unique constraint |
| format email bị coi là xác minh email tồn tại | Format chỉ kiểm tra hình dạng, không xác minh ownership | Dùng verification flow nghiệp vụ |
| Một DTO dùng cho cả create và response | Entity/request/response bị trộn | Tách DTO theo hướng dữ liệu |
| Mọi lỗi đều trả 400 | Không phân biệt invalid input và state conflict | Xây dựng status policy rõ ràng |

## 22. Checklist thiết kế một operation

Trước khi công bố operation trong OpenAPI, hãy trả lời:

1. Request có parse được theo media type và kiểu dữ liệu đã khai báo không?
2. Field nào bắt buộc? Có constraint đơn trường nào kiểm tra được từ payload?
3. Có constraint giữa các field chỉ phụ thuộc payload không?
4. Quy tắc nào cần principal, tenant, database, thời gian hoặc trạng thái resource?
5. Quy tắc nào cần transaction, locking hoặc database constraint?
6. DTO request có tách khỏi entity và response DTO không?
7. OpenAPI schema có mô tả đúng những constraint ổn định không?
8. Description có giải thích các business rule quan trọng và điều kiện có thể bị từ chối không?
9. Responses có status và error schema cho validation, not found, forbidden và conflict không?
10. Error code có ổn định để client xử lý mà không parse message không?
11. Test có tách DTO validation, domain rules, persistence integrity và HTTP contract không?
12. Có test cạnh tranh đồng thời cho invariant quan trọng như uniqueness hoặc tồn kho không?

## 23. Tài liệu tham khảo

- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): validation ở controller method, @Valid, method validation và các exception tương ứng.
- [Spring Framework – @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialize request body, HttpMessageConverter và kích hoạt Bean Validation.
- [OpenAPI Specification 3.1.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object): mô tả cấu trúc dữ liệu và các schema keyword.
- [OpenAPI Specification – Specification versions](https://spec.openapis.org/oas/): các phiên bản OpenAPI và schema iteration tương ứng.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa status 400, 403, 404, 409, 412 và các mã HTTP khác.
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/): constraint annotations, validator và validation groups.

## 24. Tổng kết áp dụng

OpenAPI schema và Bean Validation mô tả, kiểm tra dữ liệu mà client gửi qua HTTP. Domain/application layer quyết định hành động có hợp lệ trong trạng thái và chính sách hiện tại hay không. Database bảo vệ invariant cuối cùng khi có transaction đồng thời.

Trong Spring Boot, hãy dùng DTO và @Valid cho constraint đầu vào có thể quyết định từ payload; giữ quy tắc phụ thuộc resource, tenant, quyền, tồn kho hoặc trạng thái trong domain/application service; dùng transaction và database constraint cho tính toàn vẹn. Springdoc cần công bố schema request/response và các business error responses tương ứng để consumer hiểu cả dữ liệu cần gửi lẫn những kết quả có thể nhận được.
