# Ví dụ thành công, dữ liệu không hợp lệ và trường hợp biên

Ví dụ trong OpenAPI giúp người đọc hiểu request cần gửi, response có thể nhận và cách API phản hồi khi dữ liệu không hợp lệ. Với springdoc-openapi, có thể mô tả ví dụ ngay trên schema bằng <code>@Schema</code>, hoặc khai báo nhiều ví dụ có tên bằng <code>@ExampleObject</code> trong nội dung request và response.

Một bộ ví dụ tốt cần phản ánh đúng hợp đồng: ví dụ thành công phải hợp lệ với schema; ví dụ lỗi phải cho thấy dữ liệu nào bị từ chối và response lỗi có cấu trúc ra sao; ví dụ biên phải làm rõ giá trị nhỏ nhất, lớn nhất, rỗng, thiếu, null hoặc định dạng đặc biệt. Annotation OpenAPI chỉ tạo tài liệu. Validation và xử lý lỗi thực tế vẫn phải được triển khai trong ứng dụng.

## 1. Phân biệt example và examples

OpenAPI có thể mô tả một ví dụ đơn giản hoặc một tập ví dụ được đặt tên:

| Cách mô tả | Mục đích | Khi nên dùng |
|---|---|---|
| <code>@Schema(example = "...")</code> | Một ví dụ ở cấp schema | Giá trị đại diện đơn giản cho một thuộc tính |
| <code>@Content(example = "...")</code> | Một ví dụ cho media type | Nội dung đơn giản, chỉ cần một payload minh họa |
| <code>@Content(examples = ...)</code> | Nhiều ví dụ có tên cho media type | Các request/response có nhiều tình huống |
| <code>@ExampleObject</code> | Một ví dụ có tên, mô tả và giá trị | Phân biệt thành công, biên và lỗi |

Trong OpenAPI, Media Type Object có thể chứa <code>example</code> hoặc <code>examples</code>. Hai thuộc tính này loại trừ lẫn nhau trong cùng một media type. Nếu cần nhiều ví dụ, dùng <code>examples</code> và đặt tên riêng cho từng ví dụ.

Mỗi <code>ExampleObject</code> có thể cung cấp:

- <code>name</code>: khóa định danh ví dụ trong map <code>examples</code>.
- <code>summary</code>: tiêu đề ngắn để người đọc chọn ví dụ.
- <code>description</code>: giải thích mục đích, điều kiện hoặc kết quả mong đợi.
- <code>value</code>: dữ liệu mẫu được nhúng trực tiếp.
- <code>externalValue</code>: URL trỏ đến nội dung ví dụ ở bên ngoài thay cho <code>value</code>.

Thông thường nên dùng <code>value</code> để tài liệu tự chứa. Nếu dùng <code>externalValue</code>, cần bảo đảm URL có thể truy cập và nội dung được quản lý cùng phiên bản hợp đồng.

## 2. Ví dụ thành công ở cấp schema

Với một thuộc tính đơn giản, có thể đặt ví dụ ngay trên DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @Schema(
        description = "Mã sản phẩm",
        example = "SKU-100",
        maxLength = 40
    )
    @NotBlank
    @Size(max = 40)
    String productCode,

    @Schema(
        description = "Số lượng đặt mua",
        example = "2",
        minimum = "1",
        maximum = "100"
    )
    @NotNull
    @Min(1)
    @Max(100)
    Integer quantity,

    @Schema(
        description = "Phương thức thanh toán",
        example = "CARD"
    )
    @NotNull
    PaymentMethod paymentMethod
) {}

enum PaymentMethod {
    COD,
    CARD,
    BANK_TRANSFER
}
~~~

<code>@Schema(example = "...")</code> phù hợp với ví dụ đơn lẻ cho từng field. Với annotation, giá trị <code>example</code> được khai báo dưới dạng chuỗi; springdoc/swagger-core diễn giải nó theo kiểu schema khi tạo tài liệu. Khi cần minh họa cả object request với nhiều field liên quan, dùng <code>@ExampleObject</code> ở cấp nội dung request body.

## 3. Khai báo nhiều request example bằng @ExampleObject

Một operation tạo đơn hàng có thể cần ví dụ thành công, ví dụ đặt số lượng ở biên và ví dụ dữ liệu không hợp lệ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    @Operation(
        summary = "Tạo đơn hàng",
        description = "Tạo đơn hàng từ mã sản phẩm, số lượng và phương thức thanh toán.",
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = "application/json",
                examples = {
                    @ExampleObject(
                        name = "validOrder",
                        summary = "Đơn hàng hợp lệ",
                        description = "Đặt hai sản phẩm bằng thẻ.",
                        value = """
                            {
                              "productCode": "SKU-100",
                              "quantity": 2,
                              "paymentMethod": "CARD"
                            }
                            """
                    ),
                    @ExampleObject(
                        name = "minimumQuantity",
                        summary = "Số lượng ở biên nhỏ nhất",
                        description = "quantity bằng 1 là giá trị hợp lệ nhỏ nhất.",
                        value = """
                            {
                              "productCode": "SKU-100",
                              "quantity": 1,
                              "paymentMethod": "COD"
                            }
                            """
                    ),
                    @ExampleObject(
                        name = "invalidQuantity",
                        summary = "Không hợp lệ: số lượng bằng 0",
                        description = "Ví dụ này cố ý vi phạm @Min(1), server cần trả lỗi validation.",
                        value = """
                            {
                              "productCode": "SKU-100",
                              "quantity": 0,
                              "paymentMethod": "CARD"
                            }
                            """
                    )
                }
            )
        )
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đơn hàng được tạo",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = OrderResponse.class),
                examples = @ExampleObject(
                    name = "createdOrder",
                    summary = "Đơn hàng đã xác nhận",
                    value = """
                        {
                          "orderId": "ORD-2026-001",
                          "status": "CONFIRMED",
                          "total": 259900.00
                        }
                        """
                )
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Request không hợp lệ",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ApiError.class),
                examples = {
                    @ExampleObject(
                        name = "quantityTooSmall",
                        summary = "Số lượng nhỏ hơn giới hạn",
                        value = """
                            {
                              "code": "VALIDATION_FAILED",
                              "message": "Request contains invalid fields",
                              "details": {
                                "quantity": "must be greater than or equal to 1"
                              }
                            }
                            """
                    ),
                    @ExampleObject(
                        name = "missingProductCode",
                        summary = "Thiếu mã sản phẩm",
                        value = """
                            {
                              "code": "VALIDATION_FAILED",
                              "message": "Request contains invalid fields",
                              "details": {
                                "productCode": "must not be blank"
                              }
                            }
                            """
                    )
                }
            )
        )
    })
    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = new OrderResponse(
            "ORD-2026-001",
            "CONFIRMED",
            new java.math.BigDecimal("259900.00")
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}

record OrderResponse(
    String orderId,
    String status,
    java.math.BigDecimal total
) {}

record ApiError(
    String code,
    String message,
    java.util.Map<String, String> details
) {}
~~~

Trong ví dụ:

- <code>validOrder</code> là payload hợp lệ thông thường.
- <code>minimumQuantity</code> minh họa biên dưới hợp lệ.
- <code>invalidQuantity</code> cố ý không thỏa schema vì <code>quantity</code> phải từ 1 trở lên.
- Response <code>201</code> mô tả kết quả thành công.
- Response <code>400</code> có hai ví dụ lỗi khác nhau để người tích hợp hiểu cấu trúc <code>details</code>.

Các ví dụ request lỗi được gắn nhãn rõ để người đọc không nhầm với payload có thể gửi thành công. Nếu Swagger UI cho phép chọn và gửi ví dụ này bằng Try it out, server cần từ chối nó theo validation thực tế.

Các ví dụ dùng Java text block, cần Java 15 trở lên. Với dự án Java cũ hơn, thay text block bằng chuỗi đã escape hoặc đặt ví dụ trong cấu hình OpenAPI riêng.

## 4. Mô tả response thành công và lỗi

Response example được đặt dưới từng mã trạng thái và media type tương ứng. Một operation có thể trả nhiều loại response:

| HTTP status | Tình huống | Ví dụ nội dung |
|---|---|---|
| <code>201</code> | Tạo tài nguyên thành công | ID, trạng thái và dữ liệu tài nguyên |
| <code>400</code> | Request không hợp lệ | Mã lỗi và chi tiết field vi phạm |
| <code>404</code> | Không tìm thấy tài nguyên | Mã lỗi và thông tin định danh |
| <code>409</code> | Xung đột nghiệp vụ | Mã lỗi như tồn kho không đủ hoặc trùng dữ liệu |
| <code>422</code> | Dữ liệu có cú pháp hợp lệ nhưng không xử lý được theo quy tắc nghiệp vụ | Mã lỗi nghiệp vụ và nguyên nhân |

Không đưa mọi lỗi vào response <code>400</code> nếu ứng dụng phân biệt rõ <code>404</code>, <code>409</code> hoặc <code>422</code>. Mỗi status cần có schema và ví dụ đúng với response thực tế của hệ thống.

Với response không có body như <code>204 No Content</code>, không khai báo ví dụ JSON. Chỉ mô tả status và header nếu có.

Ví dụ response lỗi xung đột:

~~~java
@ApiResponse(
    responseCode = "409",
    description = "Không đủ tồn kho để đáp ứng đơn hàng",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class),
        examples = @ExampleObject(
            name = "insufficientStock",
            summary = "Tồn kho không đủ",
            value = """
                {
                  "code": "INSUFFICIENT_STOCK",
                  "message": "Requested quantity is not available",
                  "details": {
                    "productCode": "SKU-100",
                    "available": "1",
                    "requested": "3"
                  }
                }
                """
        )
    )
)
~~~

Đoạn annotation trên có thể đặt trong danh sách <code>@ApiResponses</code> của operation. Bảo đảm DTO <code>ApiError</code> cho phép cấu trúc <code>details</code> đó; nếu chi tiết có nhiều kiểu giá trị, có thể dùng một DTO cụ thể hoặc kiểu JSON linh hoạt đã được mô tả schema rõ ràng.

## 5. Ví dụ YAML tương ứng trong OpenAPI

Các annotation ở trên tạo ra cấu trúc gần như sau trong tài liệu OpenAPI:

~~~yaml
paths:
  /orders:
    post:
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateOrderRequest"
            examples:
              validOrder:
                summary: Đơn hàng hợp lệ
                value:
                  productCode: SKU-100
                  quantity: 2
                  paymentMethod: CARD
              minimumQuantity:
                summary: Số lượng ở biên nhỏ nhất
                value:
                  productCode: SKU-100
                  quantity: 1
                  paymentMethod: COD
              invalidQuantity:
                summary: Không hợp lệ: số lượng bằng 0
                description: Cố ý vi phạm giới hạn min 1.
                value:
                  productCode: SKU-100
                  quantity: 0
                  paymentMethod: CARD
      responses:
        "201":
          description: Đơn hàng được tạo
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"
              examples:
                createdOrder:
                  summary: Đơn hàng đã xác nhận
                  value:
                    orderId: ORD-2026-001
                    status: CONFIRMED
                    total: 259900.00
        "400":
          description: Request không hợp lệ
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiError"
              examples:
                quantityTooSmall:
                  summary: Số lượng nhỏ hơn giới hạn
                  value:
                    code: VALIDATION_FAILED
                    message: Request contains invalid fields
                    details:
                      quantity: must be greater than or equal to 1
~~~

Tên ví dụ trong map <code>examples</code> giúp công cụ hiển thị danh sách lựa chọn. Nội dung <code>value</code> phải có kiểu JSON tương ứng với schema: số lượng là number, trạng thái là string và object lỗi có cấu trúc đúng.

## 6. Ví dụ cho dữ liệu rỗng và trường hợp biên

Ví dụ biên giúp tránh cách hiểu mơ hồ về dữ liệu hợp lệ. Nên chọn những trường hợp có ảnh hưởng đến cách client gọi API hoặc xử lý response.

### 6.1. Danh sách rỗng và danh sách có dữ liệu

Một endpoint tìm kiếm có thể trả trang kết quả rỗng hợp lệ:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

@ApiResponse(
    responseCode = "200",
    description = "Kết quả tìm kiếm",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderPageResponse.class),
        examples = {
            @ExampleObject(
                name = "emptyPage",
                summary = "Không có kết quả",
                value = """
                    {
                      "items": [],
                      "page": 0,
                      "size": 20,
                      "totalElements": 0
                    }
                    """
            ),
            @ExampleObject(
                name = "pageWithItems",
                summary = "Trang có dữ liệu",
                value = """
                    {
                      "items": [
                        {
                          "orderId": "ORD-2026-001",
                          "status": "CONFIRMED"
                        }
                      ],
                      "page": 0,
                      "size": 20,
                      "totalElements": 1
                    }
                    """
            )
        }
    )
)

record OrderPageResponse(
    List<OrderSummary> items,
    int page,
    int size,
    long totalElements
) {}

record OrderSummary(String orderId, String status) {}
~~~

Nếu không có kết quả, thường trả <code>200</code> cùng mảng rỗng thay vì <code>null</code>, trừ khi hợp đồng chọn quy ước khác. Ví dụ phải phù hợp với kiểu <code>items</code> và các thuộc tính phân trang được công bố.

### 6.2. Giá trị nhỏ nhất và lớn nhất

Nếu schema quy định <code>quantity</code> từ 1 đến 100, nên có ví dụ cho cả hai biên:

| Giá trị | Kết quả mong đợi |
|---:|---|
| 0 | Không hợp lệ |
| 1 | Hợp lệ, biên dưới |
| 2 | Hợp lệ, giá trị thông thường |
| 100 | Hợp lệ, biên trên |
| 101 | Không hợp lệ |

Không chỉ thử giá trị nằm giữa. Lỗi off-by-one thường xuất hiện ở đúng các giá trị sát biên.

### 6.3. Thiếu field, null và chuỗi rỗng

Ba payload sau có ý nghĩa khác nhau:

~~~json
{
  "productCode": "SKU-100"
}
~~~

~~~json
{
  "productCode": "SKU-100",
  "note": null
}
~~~

~~~json
{
  "productCode": "SKU-100",
  "note": ""
}
~~~

Payload đầu tiên không có khóa <code>note</code>; payload thứ hai có khóa với giá trị null; payload thứ ba có chuỗi rỗng. Schema cần thể hiện rõ field có bắt buộc không, có cho phép null không và chuỗi rỗng có được chấp nhận không.

Không dùng một ví dụ duy nhất để ngầm nói cả ba trường hợp là tương đương. Nếu API coi thiếu field là giữ nguyên, null là xóa giá trị và chuỗi rỗng là nội dung rỗng, hãy mô tả riêng từng ví dụ.

### 6.4. Unicode và ký tự đặc biệt

Nếu API nhận tên, địa chỉ hoặc ghi chú đa ngôn ngữ, thêm ví dụ Unicode:

~~~json
{
  "customerName": "Nguyễn Thị Ánh",
  "note": "Giao hàng sau 18:00 – gọi trước khi đến."
}
~~~

Kiểm tra cả ký tự có dấu, dấu gạch dài, emoji nếu hệ thống cho phép, và ký tự cần escape như dấu nháy kép hoặc dấu gạch chéo ngược. JSON phải được escape đúng để parser đọc được.

### 6.5. Ngày giờ và múi giờ

Nếu API dùng timestamp, nên minh họa rõ offset hoặc UTC:

~~~json
{
  "createdAt": "2026-11-20T10:30:00+07:00",
  "expiresAt": "2026-11-20T03:30:00Z"
}
~~~

Hai thời điểm trên biểu diễn cùng một thời điểm theo hai offset khác nhau. Ví dụ giúp client nhận ra API yêu cầu định dạng date-time và hiểu quy ước múi giờ.

## 7. Ví dụ cho query parameter và header

Không chỉ request body mới cần ví dụ. Query parameter và header cũng có thể được mô tả bằng <code>@Parameter</code>:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/orders/search")
List<OrderResponse> searchOrders(
    @Parameter(
        description = "Trạng thái cần lọc",
        examples = {
            @ExampleObject(name = "confirmed", value = "CONFIRMED"),
            @ExampleObject(name = "cancelled", value = "CANCELLED")
        }
    )
    @RequestParam(name = "status", required = false) String status
) {
    // ...
    return List.of();
}
~~~

Ở đây, <code>@RequestParam</code> xác định tên binding và tính tùy chọn tại runtime; <code>@Parameter</code> bổ sung ví dụ cho tài liệu. Nếu client không gửi query parameter, đó là trạng thái vắng mặt. Nếu gửi <code>?status=</code>, đó là giá trị chuỗi rỗng; ứng dụng cần quy định cách xử lý riêng.

Với header, có thể dùng <code>@Parameter</code> cùng <code>@RequestHeader</code> theo cách tương tự. Đừng khai báo một ví dụ header xác thực thật có token hoặc thông tin bí mật. Dùng giá trị giả an toàn như <code>Bearer eyJ...demo</code> nếu cần minh họa cú pháp.

## 8. Ví dụ không thay thế validation và kiểm thử

Việc thêm <code>@ExampleObject</code> không làm Spring tự kiểm tra payload. Ví dụ request sai chỉ là nội dung tài liệu; server cần validation thật:

Với Spring Boot, cần có implementation Bean Validation trên classpath, thường là starter sau:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Khi dùng Spring Boot dependency management, không cần tự đặt version cho starter này. Sau đó khai báo constraint trên DTO và kích hoạt bằng <code>@Valid</code> ở tham số controller.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @NotBlank
    @Size(max = 40)
    String productCode,

    @NotNull
    @Min(1)
    @Max(100)
    Integer quantity
) {}
~~~

Controller cần kích hoạt Bean Validation:

~~~java
@PostMapping("/orders")
ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Để response lỗi có cấu trúc thống nhất, có thể xử lý exception bằng <code>@RestControllerAdvice</code>:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {
        Map<String, String> details = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .collect(java.util.stream.Collectors.toMap(
                error -> error.getField(),
                error -> error.getDefaultMessage() == null
                    ? "Invalid value"
                    : error.getDefaultMessage(),
                (first, second) -> first
            ));

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(new ApiError(
                "VALIDATION_FAILED",
                "Request contains invalid fields",
                details
            ));
    }
}
~~~

Ví dụ handler này trả về cấu trúc <code>ApiError</code> như các response example ở trên. Trong dự án thực tế, nên chuẩn hóa mã lỗi, thông điệp, cách che thông tin nội bộ và xử lý các loại exception khác.

Hãy viết kiểm thử cho cả payload hợp lệ và không hợp lệ. Ví dụ thành công cần kiểm tra status, content type và body. Ví dụ lỗi cần kiểm tra status <code>400</code>, mã lỗi và chi tiết field. Một ví dụ trong tài liệu chỉ đáng tin khi nó tương ứng với hành vi đã được kiểm chứng.

## 9. Kiểm tra ví dụ được sinh ra trong OpenAPI

Sau khi ứng dụng khởi động, lấy đặc tả JSON:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra:

1. Request body có đúng media type như <code>application/json</code>.
2. Các ví dụ có tên nằm trong <code>content.application/json.examples</code>.
3. Ví dụ response nằm dưới đúng mã trạng thái như <code>201</code> hoặc <code>400</code>.
4. Mỗi ví dụ có summary/description đủ rõ để phân biệt.
5. Schema của từng request/response khớp kiểu và ràng buộc của giá trị.
6. Không khai báo đồng thời <code>example</code> và <code>examples</code> cho cùng Media Type Object.
7. Các ví dụ lỗi được đánh dấu rõ là payload không hợp lệ, không bị nhầm với mẫu request thành công.

Có thể xem tài liệu trong Swagger UI để kiểm tra danh sách lựa chọn ví dụ. Chọn từng request example, quan sát JSON được hiển thị và thử gửi trong môi trường phát triển. Không gửi ví dụ lỗi vào production chỉ để kiểm tra tài liệu.

## 10. Quy tắc viết ví dụ dễ sử dụng

- Dùng dữ liệu giả nhưng có hình dạng thực tế; không đưa thông tin cá nhân hoặc secret thật vào tài liệu.
- Đặt tên ngắn và có ý nghĩa như <code>validOrder</code>, <code>minimumQuantity</code>, <code>invalidQuantity</code>, <code>emptyPage</code>.
- Mỗi ví dụ chỉ nên minh họa một mục đích chính để người đọc hiểu được khác biệt.
- Ghi rõ ví dụ nào hợp lệ, ví dụ nào cố ý vi phạm schema.
- Giữ nhất quán ID, trạng thái, timestamp, đơn vị tiền và enum giữa request, response và mô tả.
- Khi schema thay đổi, cập nhật các ví dụ liên quan cùng lúc.
- Không tạo ví dụ chứa field không có trong schema nếu API không cho phép field mở rộng.
- Với ví dụ response, không công bố token, password, email hoặc dữ liệu thật của người dùng.
- Với ví dụ biên, ghi rõ giá trị nằm đúng tại biên hay vượt biên.

## 11. Lỗi thường gặp

**Đặt nhiều ví dụ vào example đơn.** Thuộc tính <code>example</code> chỉ dành cho một giá trị. Dùng <code>examples</code> với các <code>@ExampleObject</code> có tên.

**Ví dụ không khớp schema.** Ví dụ có thể khiến client sao chép payload sai. Kiểm tra kiểu dữ liệu, required, nullable, enum, min/max và format.

**Ví dụ lỗi không được đánh dấu.** Người dùng có thể chọn nhầm payload lỗi trong Swagger UI. Đặt tên và mô tả rõ rằng ví dụ cố ý không hợp lệ.

**Tưởng annotation tạo response lỗi runtime.** <code>@ApiResponse</code> và <code>@ExampleObject</code> chỉ mô tả tài liệu. Cần exception handler và validation để server thực sự trả lỗi.

**Dùng status code không khớp triển khai.** Nếu ứng dụng trả <code>400</code> nhưng OpenAPI mô tả <code>422</code>, client sẽ xử lý sai. Đồng bộ annotation và exception handler.

**Bỏ qua trường hợp rỗng và null.** Mảng rỗng, object rỗng, field vắng mặt, null và chuỗi rỗng có ý nghĩa khác nhau. Chỉ đưa vào ví dụ khi hợp đồng xác định rõ hành vi.

**Ví dụ ngày giờ không có offset.** Nếu API cần một thời điểm tuyệt đối, dùng date-time có offset hoặc UTC và ghi rõ quy ước.

## 12. Danh sách rà soát trước khi công bố

- [ ] Có ví dụ request thành công cho operation quan trọng.
- [ ] Có ví dụ response thành công cho từng status code chính.
- [ ] Có ví dụ request không hợp lệ và response lỗi tương ứng.
- [ ] Có ví dụ giá trị nhỏ nhất/lớn nhất hoặc sát biên khi cần.
- [ ] Có ví dụ danh sách rỗng, field thiếu, null hoặc chuỗi rỗng nếu chúng có ý nghĩa.
- [ ] Mỗi ví dụ có tên, summary hoặc description rõ ràng.
- [ ] Giá trị ví dụ khớp schema hoặc được đánh dấu rõ là cố ý không hợp lệ.
- [ ] Không có dữ liệu nhạy cảm thật trong ví dụ.
- [ ] Annotation OpenAPI và hành vi validation/exception handler nhất quán.
- [ ] Đã kiểm tra đầu ra <code>/v3/api-docs</code>, Swagger UI và test endpoint thực tế.

## Tài liệu tham khảo

- [OpenAPI Specification – Example Object](https://spec.openapis.org/oas/latest.html#example-object): các trường <code>summary</code>, <code>description</code>, <code>value</code> và <code>externalValue</code>.
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object): cách khai báo <code>example</code> và <code>examples</code> cho request/response content.
- [Swagger – Adding Examples](https://swagger.io/docs/specification/adding-examples/): ví dụ cho request body, response và parameter.
- [Swagger Core – ExampleObject annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/ExampleObject.html): thuộc tính của annotation <code>@ExampleObject</code>.
- [springdoc-openapi](https://springdoc.org/): tích hợp annotation OpenAPI với Spring Boot và Swagger UI.
