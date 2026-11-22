# Rà soát độ rõ của mô tả, tính đúng của ví dụ và khả năng dùng của bên tích hợp

Một tài liệu OpenAPI hợp lệ về cú pháp vẫn có thể khó dùng nếu tên operation mơ hồ, schema thiếu ràng buộc, ví dụ không khớp dữ liệu thực tế hoặc không mô tả cách xác thực. Bài thực hành này xây dựng quy trình rà soát tài liệu do springdoc-openapi sinh từ controller Spring Boot, với mục tiêu để một nhóm tích hợp có thể hiểu hợp đồng, tạo request đúng và xử lý các response mà không phải đoán hành vi của API.

Ta sẽ dùng một API tạo đơn hàng làm ví dụ. Quy trình áp dụng tương tự cho API nội bộ, API đối tác và các nhóm tài liệu được tạo bằng `GroupedOpenApi`.

## 1. Xác định người dùng và phạm vi của tài liệu

Trước khi sửa annotation, xác định ai sẽ đọc tài liệu và họ cần hoàn thành thao tác nào. Người tích hợp thường cần biết:

- URL và HTTP method để gọi operation.
- Cách truyền path parameter, query parameter, header và request body.
- Trường bắt buộc, kiểu dữ liệu, định dạng, giới hạn và giá trị hợp lệ.
- Cách xác thực, quyền cần có và phản hồi khi token không hợp lệ.
- Response thành công, response lỗi, header quan trọng và trường hợp không có body.
- Ví dụ có thể sao chép để chạy thử trong môi trường được phép.
- Phiên bản API, server URL và những operation đã ngừng khuyến nghị.

Ghi rõ tài liệu đang mô tả API nào, môi trường nào và phiên bản hợp đồng nào. Một group tên `partner` có thể chỉ công bố API dành cho đối tác; group `internal` có thể chứa operation nội bộ. Người đọc cần nhận ra họ đang xem đúng tài liệu và đúng phạm vi quyền truy cập.

## 2. Rà soát mô tả operation

Mỗi operation nên có `summary` ngắn, nói rõ hành động và đối tượng; `description` giải thích điều kiện nghiệp vụ và hành vi mà người gọi cần biết. `operationId` cần duy nhất và ổn định để các công cụ sinh client có thể dùng làm tên hàm.

Ví dụ về cách viết:

| Thành phần | Mô tả yếu | Mô tả có ích cho bên tích hợp |
| --- | --- | --- |
| `summary` | `Order API` | `Tạo đơn hàng` |
| `description` | `Create an order` | `Tạo đơn hàng từ các sản phẩm còn được phép bán. API trả về mã đơn hàng và trạng thái ban đầu; tổng tiền được tính ở phía máy chủ.` |
| `operationId` | `postApiOrders1` | `createOrder` |

Description không cần lặp lại nguyên văn summary. Hãy bổ sung những chi tiết làm thay đổi cách gọi hoặc cách xử lý kết quả, chẳng hạn quy tắc kiểm tra tồn kho, giới hạn số dòng, ý nghĩa của trạng thái, tính idempotent, điều kiện phân quyền hoặc hành vi retry. Chỉ ghi những cam kết mà implementation thực sự bảo đảm.

Các tham số cũng cần mô tả rõ:

- Path parameter: định danh tài nguyên nào, định dạng và ví dụ hợp lệ.
- Query parameter: bộ lọc, cách sắp xếp, mặc định, giới hạn trang và ý nghĩa khi bỏ trống.
- Header: mục đích, định dạng và trường hợp bắt buộc.
- Request body: media type, trường bắt buộc, giới hạn và quy tắc kết hợp giữa các trường.

Tránh các câu như “ID của đối tượng” nếu API có nhiều loại ID. Ghi rõ `orderId` là UUID của đơn hàng, `customerId` là mã khách hàng và liệu các giá trị có phân biệt hoa thường hay không nếu điều đó ảnh hưởng tới việc gọi API.

## 3. Rà soát schema request và response

Schema phải phản ánh DTO và hành vi validation thực tế. Với mỗi property, kiểm tra tên JSON, kiểu, `format`, trạng thái required, nullable, giới hạn, enum và ý nghĩa nghiệp vụ. Không suy ra rằng một trường bắt buộc chỉ vì Java dùng kiểu nguyên thủy; đối chiếu cả validation và dữ liệu thực tế được chấp nhận.

Ví dụ request tạo đơn hàng:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderRequest(
        @NotBlank
        @Schema(description = "Mã khách hàng đã được cấp", example = "cus_123")
        String customerId,

        @NotEmpty
        @Valid
        @Schema(description = "Danh sách sản phẩm cần đặt")
        List<OrderLineRequest> lines
) {}

public record OrderLineRequest(
        @NotBlank
        @Schema(description = "Mã SKU của sản phẩm", example = "SKU-RED-01")
        String sku,

        @Positive
        @Schema(description = "Số lượng phải lớn hơn 0", example = "2", minimum = "1")
        int quantity
) {}
```

`@NotBlank`, `@NotEmpty` và `@Positive` chỉ có tác dụng kiểm tra request khi validation được bật trong ứng dụng, ví dụ bằng `@Valid` tại điểm nhận request. Annotation OpenAPI mô tả schema; nó không tự thực thi validation. Vì vậy, hãy so sánh tài liệu với cả DTO, controller và cấu hình xử lý lỗi.

Một response có thể được mô tả bằng các kiểu dữ liệu có định dạng rõ ràng:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public enum OrderStatus {
    CREATED, CONFIRMED, CANCELLED
}

public record OrderResponse(
        @Schema(description = "Định danh duy nhất của đơn hàng", example = "7d444840-9dc0-11d1-b245-5ffdce74fad2")
        UUID id,

        @Schema(description = "Trạng thái hiện tại của đơn hàng", example = "CREATED")
        OrderStatus status,

        @Schema(description = "Tổng tiền do máy chủ tính", example = "125000.00")
        BigDecimal total,

        @Schema(description = "Thời điểm tạo đơn hàng theo ISO 8601", example = "2026-11-20T10:15:30+07:00")
        OffsetDateTime createdAt
) {}
```

Khi rà soát schema, đặc biệt chú ý các điểm sau:

1. `UUID`, ngày giờ, ngày tháng, số thập phân và binary phải có định dạng tương ứng, không mô tả chúng như chuỗi tùy ý nếu công cụ có thể biểu diễn chính xác hơn.
2. Enum trong tài liệu phải khớp các giá trị ứng dụng thật sự trả về và chấp nhận. Không thêm giá trị “dự kiến” chưa được triển khai.
3. Trường optional, nullable và trường có thể vắng mặt mang ý nghĩa khác nhau. Mô tả đúng cách server xử lý từng trường hợp.
4. Tên property trong JSON phải khớp serialization thực tế, kể cả khi DTO dùng `@JsonProperty` hoặc quy tắc naming strategy.
5. Schema dùng chung cần có tên và ý nghĩa ổn định. Tránh để hai cấu trúc khác nhau vô tình dùng chung một schema chỉ vì chúng có các trường trùng tên.
6. Với collection và phân trang, mô tả cấu trúc phần tử, thứ tự, `page`, `size`, `totalElements`, cursor hoặc token tiếp tục theo hợp đồng thực tế.

## 4. Làm cho ví dụ request và response có thể sử dụng

Ví dụ tốt phải là JSON hợp lệ, khớp schema và phản ánh một tình huống nghiệp vụ có thể xảy ra. Bên tích hợp thường sao chép ví dụ để tạo request đầu tiên, do đó một ví dụ sai có thể khiến họ mất thời gian điều tra dù endpoint hoạt động đúng.

Ví dụ request:

```json
{
  "customerId": "cus_123",
  "lines": [
    {
      "sku": "SKU-RED-01",
      "quantity": 2
    }
  ]
}
```

Ví dụ response `201 Created`:

```json
{
  "id": "7d444840-9dc0-11d1-b245-5ffdce74fad2",
  "status": "CREATED",
  "total": 125000.00,
  "createdAt": "2026-11-20T10:15:30+07:00"
}
```

Khi review, kiểm tra từng ví dụ theo các câu hỏi:

- Tên property có đúng với JSON thực tế không?
- Kiểu dữ liệu có đúng không? Ví dụ `quantity` là số, `total` là số thập phân và `createdAt` là ngày giờ có offset.
- Tất cả trường bắt buộc có mặt chưa? Có trường nào bị ghi thành `null` trong khi schema không cho phép không?
- Giá trị enum, độ dài chuỗi, giới hạn số và định dạng có hợp lệ không?
- Ví dụ response có đúng với status code được gắn không?
- Dữ liệu minh họa có vô tình chứa token, thông tin cá nhân hoặc dữ liệu thật không?
- Có thể sao chép ví dụ để gọi API trong môi trường đã chọn mà không cần tự đoán thêm trường nào không?

Không dùng ví dụ giả lập để che giấu hành vi chưa rõ. Nếu tổng tiền do máy chủ tính, ví dụ request không nên yêu cầu client gửi `total`. Nếu server tạo `id`, ví dụ request không nên yêu cầu người gọi tự sinh ID. Nếu API chấp nhận nhiều biến thể payload, tạo ví dụ riêng có tên và giải thích mục đích từng biến thể.

## 5. Mô tả response lỗi và quy tắc xác thực

Tài liệu chỉ liệt kê response `200` hoặc `201` là chưa đủ. Người tích hợp cần biết lỗi nào có thể xảy ra và cách xử lý. Hãy đối chiếu response thực tế của controller, exception handler và Spring Security.

Ví dụ DTO lỗi:

```java
import io.swagger.v3.oas.annotations.media.Schema;

public record ApiError(
        @Schema(example = "VALIDATION_ERROR")
        String code,

        @Schema(example = "quantity phải lớn hơn 0")
        String message,

        @Schema(description = "Mã dùng để tra cứu log hỗ trợ", example = "req_01JABCXYZ")
        String traceId
) {}
```

Một bảng response cho operation tạo đơn hàng có thể được rà soát như sau:

| HTTP status | Trường hợp | Bên tích hợp cần biết |
| --- | --- | --- |
| `201` | Đơn hàng được tạo | Schema response, trạng thái ban đầu và header `Location` nếu server trả về. |
| `400` | Request sai định dạng hoặc vi phạm validation | Cấu trúc lỗi, trường gây lỗi và cách sửa payload. |
| `401` | Thiếu hoặc token không hợp lệ | Cách lấy token và điều kiện cần xác thực lại. |
| `403` | Danh tính đã xác thực nhưng không có quyền | Quyền hoặc scope cần được cấp. |
| `409` | Xung đột trạng thái hoặc quy tắc nghiệp vụ | Điều kiện gây xung đột và liệu người gọi có thể thử lại sau khi cập nhật dữ liệu không. |

Không thêm status code vào OpenAPI chỉ vì nó phổ biến. Nếu API không trả `409`, không mô tả `409` như một cam kết. Ngược lại, nếu exception handler thực tế trả `400` hoặc `422`, tài liệu phải thể hiện đúng status và cấu trúc lỗi đó. Với response không có body như `204 No Content`, mô tả rõ không có nội dung response.

## 6. Gắn mô tả và ví dụ vào controller bằng springdoc-openapi

Các annotation OpenAPI bổ sung thông tin cho handler mà Spring đã đăng ký. Ví dụ dưới đây minh họa một operation tạo đơn hàng; phần service được giả định đã có trong ứng dụng.

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    @Operation(
            operationId = "createOrder",
            summary = "Tạo đơn hàng",
            description = "Tạo đơn hàng từ danh sách SKU và số lượng. Máy chủ kiểm tra dữ liệu, tính tổng tiền và trả về trạng thái ban đầu.",
            security = @SecurityRequirement(name = "bearerAuth")
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "201",
                    description = "Đơn hàng được tạo thành công",
                    content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(implementation = OrderResponse.class),
                            examples = @ExampleObject(
                                    name = "createdOrder",
                                    summary = "Đơn hàng mới được tạo",
                                    value = "{\"id\":\"7d444840-9dc0-11d1-b245-5ffdce74fad2\",\"status\":\"CREATED\",\"total\":125000.00,\"createdAt\":\"2026-11-20T10:15:30+07:00\"}"
                            )
                    )
            ),
            @ApiResponse(
                    responseCode = "400",
                    description = "Request không hợp lệ",
                    content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(implementation = ApiError.class),
                            examples = @ExampleObject(
                                    value = "{\"code\":\"VALIDATION_ERROR\",\"message\":\"quantity phải lớn hơn 0\",\"traceId\":\"req_01JABCXYZ\"}"
                            )
                    )
            ),
            @ApiResponse(responseCode = "401", description = "Thiếu hoặc token không hợp lệ"),
            @ApiResponse(responseCode = "403", description = "Không có quyền tạo đơn hàng"),
            @ApiResponse(responseCode = "409", description = "Đơn hàng xung đột với trạng thái nghiệp vụ hiện tại")
    })
    public ResponseEntity<OrderResponse> createOrder(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Đoạn code cần được điều chỉnh theo response thật của ứng dụng. Nếu security filter trả body lỗi, bổ sung schema và ví dụ đúng cho `401`/`403`; nếu không trả body, giữ mô tả không có content. Nếu API có header `Location`, khai báo header đó khi implementation thực sự gửi. Annotation không thay thế logic validation, authentication hay exception handling.

Định nghĩa security scheme ở cấu hình OpenAPI, ví dụ:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
        info = @Info(
                title = "Orders API",
                version = "v1",
                description = "API quản lý đơn hàng cho các hệ thống tích hợp"
        )
)
@SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT"
)
public class OpenApiConfiguration {}
```

`@SecurityScheme` khai báo cách xác thực; `@SecurityRequirement` gắn yêu cầu đó vào operation hoặc phạm vi tài liệu. Hãy kiểm tra operation nào thực sự yêu cầu token. Không gắn security toàn cục nếu có endpoint công khai không cần xác thực, trừ khi hợp đồng chủ ý yêu cầu như vậy.

## 7. Kiểm tra tài liệu được sinh ra, không chỉ đọc annotation

Annotation là đầu vào; JSON/YAML được springdoc tạo ra mới là tài liệu mà công cụ và bên tích hợp tiêu thụ. Sau khi chạy ứng dụng với đúng profile, gọi API docs:

```bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
curl -sS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
```

Nếu tài liệu được chia group, gọi đúng URL `/v3/api-docs/{group}`. Kiểm tra JSON/YAML có:

- `info.title`, `info.version` và mô tả phạm vi API chính xác.
- Path và HTTP method đúng với mapping đang chạy.
- `operationId` không trùng giữa các operation.
- Summary, description và tham số đủ rõ.
- Request body có media type và schema phù hợp.
- Response có đúng status, content, schema và header cần thiết.
- Component schema có property, required, enum và format đúng.
- Security scheme và security requirement phản ánh chính sách thật.
- Ví dụ có cấu trúc hợp lệ và khớp schema.

Có thể dùng một OpenAPI linter trong CI để kiểm tra cấu trúc và quy ước. Ví dụ với Redocly CLI đã được pin phiên bản trong dự án:

```bash
npx @redocly/cli lint openapi.yaml
```

Linter có thể phát hiện lỗi cấu trúc, tham chiếu hoặc quy ước, nhưng không tự xác nhận rằng ví dụ phản ánh đúng dữ liệu nghiệp vụ hay endpoint thực sự trả status đã mô tả. Cần kết hợp kiểm thử tích hợp và review theo hợp đồng.

## 8. Kiểm thử hợp đồng mà bên tích hợp sẽ sử dụng

Không dừng ở kiểm tra `/v3/api-docs` trả HTTP `200`. Hãy kiểm tra các operation quan trọng có mặt và mô tả mong đợi được sinh đúng. Ví dụ với MockMvc, Jackson và AssertJ:

```java
MvcResult result = mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode document = objectMapper.readTree(
        result.getResponse().getContentAsString());
JsonNode createOrder = document
        .path("paths")
        .path("/api/orders")
        .path("post");

assertThat(createOrder.path("operationId").asText())
        .isEqualTo("createOrder");
assertThat(createOrder.path("summary").asText())
        .isEqualTo("Tạo đơn hàng");
assertThat(createOrder.path("responses").has("201")).isTrue();
assertThat(createOrder.path("requestBody").isMissingNode()).isFalse();
```

Ngoài kiểm tra tài liệu, thực hiện một lượt gọi API thực tế trong môi trường kiểm thử:

1. Gửi request hợp lệ theo ví dụ và xác nhận response có đúng status, content type, schema và các giá trị được mô tả.
2. Bỏ một trường bắt buộc hoặc gửi giá trị sai định dạng; xác nhận lỗi khớp status và schema lỗi trong OpenAPI.
3. Gọi khi thiếu token và dùng token không đủ quyền; xác nhận hành vi `401`/`403` thực tế.
4. Gửi ID không tồn tại hoặc trạng thái gây xung đột nếu API hỗ trợ tình huống đó; xác nhận status và nội dung lỗi.
5. Thử URL server và group mà người tích hợp sẽ dùng; xác nhận tài liệu không trỏ tới localhost hoặc môi trường không thể truy cập.

Nếu có client được sinh từ OpenAPI, tạo hoặc biên dịch client trong CI cho một operation đại diện. Việc này giúp phát hiện các schema hoặc tên operation gây lỗi cho công cụ tích hợp trước khi phát hành.

## 9. Đánh giá khả năng dùng từ góc nhìn bên tích hợp

Một reviewer nên thử hoàn thành một luồng thực tế chỉ dựa vào tài liệu. Với API đơn hàng, luồng có thể gồm lấy token, tạo đơn hàng, đọc ID trả về, sau đó truy vấn trạng thái. Ghi lại mọi điểm phải hỏi tác giả API hoặc suy đoán.

| Bước của bên tích hợp | Điều tài liệu phải cung cấp | Dấu hiệu cần sửa |
| --- | --- | --- |
| Chọn môi trường | Server URL, phiên bản và phạm vi group | Chỉ có `localhost`, thiếu URL môi trường hoặc không rõ API version. |
| Xác thực | Security scheme, token format và scope/role cần có | UI có nút Authorize nhưng operation không gắn security đúng. |
| Tạo request | Method, path, media type, tham số và ví dụ body | Thiếu trường bắt buộc hoặc ví dụ không chạy được. |
| Đọc response | Status, schema, enum, header và ví dụ | Response thực tế khác schema hoặc thiếu trường quan trọng. |
| Xử lý lỗi | Status lỗi, schema lỗi và hướng khắc phục | Chỉ có mô tả “Bad Request” mà không có cấu trúc lỗi. |
| Tích hợp dài hạn | Version, deprecation và thay đổi tương thích | Operation bị đổi hoặc xóa mà không có thông tin chuyển đổi. |

Nếu reviewer không thể hoàn thành luồng này, hãy xác định thiếu thông tin thuộc controller annotation, DTO/schema, cấu hình security, server URL hay xử lý lỗi. Sửa tại nguồn tạo ra hợp đồng rồi sinh lại tài liệu.

## 10. Rà soát group, phiên bản và thay đổi hợp đồng

Với `GroupedOpenApi`, kiểm tra từng group như một sản phẩm tài liệu riêng. Xác nhận tên group, tập path, package, security và server URL. Không giả định operation có trong group mặc định cũng xuất hiện trong group đối tác.

Trước khi phát hành phiên bản mới:

- So sánh OpenAPI của bản mới với baseline đã phát hành.
- Kiểm tra path hoặc method bị xóa, request field mới bắt buộc, enum bị loại, response schema bị thay đổi và security được siết chặt.
- Dùng `deprecated: true` hoặc annotation tương ứng khi operation/trường còn được hỗ trợ nhưng không nên dùng cho tích hợp mới; ghi rõ phương án thay thế và thời hạn nếu đã thống nhất.
- Kiểm tra `info.version` phản ánh phiên bản hợp đồng theo quy ước của dự án. Không tăng version chỉ vì build number thay đổi nếu hợp đồng không thay đổi theo quy ước đó.
- Giữ ổn định `operationId` và tên schema được dùng bởi client generator, trừ khi có kế hoạch migration rõ ràng.

Diff máy có thể phân loại thay đổi tương thích, nhưng cần xem xét ngữ cảnh. Chẳng hạn thêm một response enum có thể làm hỏng client sinh mã nếu client giả định enum đóng; thay đổi mô tả có thể không phá cú pháp nhưng vẫn thay đổi kỳ vọng nghiệp vụ. Hãy đánh giá cả tác động kỹ thuật lẫn tác động tới người tích hợp.

## 11. Checklist nghiệm thu bài thực hành

Chỉ đánh dấu đạt khi đã kiểm tra tài liệu được sinh ra và ít nhất một luồng tích hợp thực tế.

| Hạng mục | Tiêu chí PASS |
| --- | --- |
| Phạm vi | Đúng API, group, server URL và phiên bản. |
| Mô tả | Summary ngắn; description nêu hành vi và ràng buộc cần thiết. |
| Operation | Path, method, `operationId` và tham số chính xác. |
| Schema | Kiểu, format, required, nullable, enum và validation nhất quán với implementation. |
| Ví dụ | Request, success response và error response là JSON hợp lệ, khớp schema và dữ liệu giả lập an toàn. |
| Bảo mật | Scheme và requirement khớp chính sách; quyền của operation được mô tả. |
| Response | Status, body, content type và header phản ánh hành vi thật. |
| Group/version | Các group được kiểm tra riêng; thay đổi hợp đồng đã được đánh giá. |
| Kiểm thử | API docs được kiểm tra trong CI; request hợp lệ và lỗi đại diện đã được chạy thử. |
| Khả năng tích hợp | Reviewer hoàn thành luồng mẫu mà không cần đoán các thông tin thiết yếu. |

Ghi lại các phát hiện dưới dạng `Vị trí → Vấn đề → Tác động tới bên tích hợp → Cách sửa → Bằng chứng kiểm tra`. Ví dụ: `POST /api/orders → thiếu ví dụ 400 → client không biết cấu trúc validation error → bổ sung schema ApiError và ví dụ từ exception handler → MockMvc xác nhận response thực tế khớp OpenAPI`.

## Kết luận

Rà soát tài liệu OpenAPI cần kết hợp mô tả dễ hiểu, schema chính xác, ví dụ có thể chạy và kiểm chứng hành vi thực tế. springdoc-openapi giúp tạo hợp đồng từ controller Spring Boot, nhưng chất lượng cuối cùng phụ thuộc vào annotation, DTO, security, exception handler và quy trình kiểm thử. Khi một reviewer có thể chọn đúng group, xác thực, gửi request, đọc response và xử lý lỗi chỉ dựa vào tài liệu, API đã tiến gần hơn tới mức sẵn sàng cho bên tích hợp.
