# Mô tả động cơ sử dụng, điều kiện trước và kết quả quan sát

Một operation trong OpenAPI cần giúp người tích hợp trả lời ba câu hỏi: **Thao tác này dùng để làm gì? Client cần đáp ứng những điều kiện nào trước khi gọi? Sau khi gọi, client có thể quan sát được kết quả gì?** Đường dẫn, HTTP method và kiểu dữ liệu chỉ cho biết hình thức giao tiếp. Phần mô tả operation cần làm rõ ý nghĩa nghiệp vụ để người dùng API biết khi nào nên gọi, cần chuẩn bị gì và phải xử lý từng kết quả ra sao.

Với springdoc-openapi, ta thường dùng annotation **@Operation** để mô tả mục đích và điều kiện nghiệp vụ, kết hợp **@Parameter**, schema của request, **@ApiResponse** và response schema để mô tả đầu vào và kết quả. OpenAPI không có một trường riêng tên là preconditions hay postconditions; những thông tin này được biểu đạt qua mô tả operation, tham số, security requirement, request body, response, header và mã trạng thái HTTP.

## 1. Vì sao cần mô tả mục đích của operation?

Tên method và path có thể cho biết thao tác kỹ thuật, nhưng thường chưa đủ để giải thích quy tắc nghiệp vụ. Chẳng hạn, POST /api/v1/orders có thể tạo đơn hàng nháp, đặt hàng chính thức, hoặc tiếp nhận yêu cầu đặt hàng chờ xử lý. Người đọc cần biết operation thực sự thực hiện hành vi nào.

Một mô tả tốt giúp:

- **Chọn đúng operation:** client hiểu thao tác được dùng trong tình huống nào và có giới hạn gì.
- **Chuẩn bị request:** người tích hợp biết dữ liệu nào cần gửi, trường nào bắt buộc và giá trị nào được chấp nhận.
- **Xử lý lỗi:** client phân biệt lỗi xác thực, dữ liệu không hợp lệ, trạng thái nghiệp vụ không phù hợp và xung đột tài nguyên.
- **Dự đoán kết quả:** client biết tài nguyên nào được tạo hoặc cập nhật, trạng thái nào được trả về và có tác động phụ nào cần lưu ý.
- **Kiểm thử hợp đồng:** nhóm phát triển có thể chuyển các điều kiện và kết quả thành kịch bản kiểm thử cụ thể.

Mục tiêu là mô tả điều mà người gọi API cần biết. Không cần đưa toàn bộ thuật toán nội bộ, tên bảng database hoặc cách tổ chức service vào tài liệu công khai.

## 2. Phân biệt summary và description

Trong OpenAPI, mỗi operation có thể có summary và description.

| Trường | Vai trò | Cách viết |
|---|---|---|
| summary | Nêu ngắn gọn hành động chính | Một câu ngắn, có động từ và đối tượng |
| description | Giải thích mục đích, điều kiện, quy tắc và hành vi | Đoạn văn hoặc Markdown có cấu trúc |

Ví dụ:

```yaml
paths:
  /api/v1/orders:
    post:
      summary: Tạo đơn hàng
      description: |
        Tạo một đơn hàng mới từ danh sách sản phẩm và số lượng do khách hàng gửi.

        Đơn hàng được tạo ở trạng thái PENDING_PAYMENT. Hệ thống giữ chỗ
        tồn kho trong 15 phút để khách hàng hoàn tất thanh toán.
```

Summary giúp người đọc quét nhanh danh sách operation trong Swagger UI. Description giải thích những điều không thể hiện rõ qua tên endpoint. Tránh dùng summary chung chung như “Xử lý dữ liệu”, “Thực hiện thao tác” hoặc “API đơn hàng”, vì chúng không nói rõ client sẽ đạt được điều gì.

## 3. Điều kiện trước là gì?

**Điều kiện trước (preconditions)** là những yêu cầu phải được đáp ứng trước khi operation có thể thực hiện thành công. Có thể chia thành một số nhóm.

### 3.1. Điều kiện về danh tính và quyền

Client có thể phải đăng nhập, có access token hợp lệ hoặc sở hữu một vai trò cụ thể. Hãy mô tả:

- Operation có yêu cầu xác thực hay không.
- Nhóm người dùng hoặc quyền nào được phép thực hiện.
- Tài nguyên có thuộc phạm vi truy cập của người gọi hay không.
- Token hết hạn hoặc thiếu quyền sẽ tạo kết quả HTTP nào theo chính sách API.

OpenAPI có cơ chế security và securitySchemes để mô tả phương thức xác thực. Mô tả nghiệp vụ có thể bổ sung phạm vi quyền, ví dụ chỉ chủ sở hữu đơn hàng hoặc nhân viên có quyền quản lý mới được hủy đơn. Không nên ghi token mẫu, mật khẩu hoặc bí mật thật vào description hay example.

### 3.2. Điều kiện về trạng thái tài nguyên

Một thao tác có thể chỉ hợp lệ khi tài nguyên đang ở trạng thái nhất định. Ví dụ:

- Chỉ đơn hàng ở trạng thái DRAFT mới được xác nhận.
- Chỉ đơn hàng chưa giao mới được hủy.
- Chỉ tài khoản đang hoạt động mới được tạo giao dịch.
- Chỉ sản phẩm đang được mở bán mới được thêm vào đơn hàng.

Nếu điều kiện không được đáp ứng, hãy nêu trạng thái không hợp lệ và kết quả mà client nhận được. Ví dụ, một đơn hàng đã giao không thể hủy và API trả 409 Conflict.

### 3.3. Điều kiện về dữ liệu đầu vào

Request có thể yêu cầu các trường bắt buộc, số lượng dương, khoảng giá trị hợp lệ, định dạng ngày giờ hoặc giới hạn kích thước. Các quy tắc có thể được thể hiện ở nhiều lớp:

- required và schema mô tả cấu trúc trong OpenAPI.
- minimum, maximum, minLength, maxLength, pattern và enum mô tả ràng buộc có thể biểu diễn bằng schema.
- @Valid, Bean Validation và annotation OpenAPI bổ sung ràng buộc từ DTO.
- description giải thích quy tắc nghiệp vụ không thể biểu diễn đầy đủ bằng schema.

Ví dụ, schema có thể diễn tả quantity là số nguyên lớn hơn 0. Description có thể giải thích số lượng tối đa trên mỗi dòng đơn hàng là 20 và sản phẩm phải đang được mở bán.

### 3.4. Điều kiện về tài nguyên và môi trường

Một operation có thể phụ thuộc vào tài nguyên liên quan hoặc trạng thái hệ thống:

- Mã khách hàng phải tồn tại và thuộc tenant hiện tại.
- Kho hàng phải có khả năng đáp ứng số lượng yêu cầu.
- Một bản ghi phải chưa bị xóa mềm.
- Dịch vụ thanh toán phải hỗ trợ phương thức được chọn.

Chỉ nêu điều kiện mà client có thể hiểu hoặc kiểm tra được. Nếu điều kiện có thể thay đổi giữa lúc client kiểm tra và lúc server xử lý, cần giải thích rằng server vẫn xác minh lại tại thời điểm thực hiện.

## 4. Kết quả quan sát là gì?

**Kết quả quan sát (observable outcomes)** là những gì client có thể nhận biết sau khi gửi request. Chúng bao gồm:

1. HTTP status code.
2. Response body và schema.
3. Response header có ý nghĩa như Location, ETag, Retry-After.
4. Trạng thái tài nguyên sau thao tác.
5. Tác động nghiệp vụ mà API cam kết, chẳng hạn tồn kho đã được giữ chỗ hoặc một yêu cầu đã được tiếp nhận.
6. Hành vi tiếp theo mà client cần thực hiện, chẳng hạn thanh toán trước thời hạn hoặc truy vấn trạng thái xử lý.

Mỗi kết quả cần được mô tả bằng điều kiện cụ thể. Ví dụ, 201 Created cho biết tài nguyên đã được tạo; response nên cung cấp định danh và trạng thái ban đầu. Nếu operation chỉ tiếp nhận công việc xử lý bất đồng bộ, 202 Accepted cần được giải thích rõ rằng công việc đã được tiếp nhận nhưng chưa hoàn tất.

### 4.1. Mô tả thành công

Với từng response thành công, hãy cho biết:

- Trạng thái HTTP và ý nghĩa.
- Dữ liệu trả về, đặc biệt là định danh và trạng thái tài nguyên.
- Header cần thiết để tiếp tục tương tác.
- Tác động đã hoàn tất tại thời điểm trả response.
- Tác động nào sẽ diễn ra sau đó và điều kiện để chúng xảy ra.

Không dùng mô tả mơ hồ như “Thành công” nếu client cần biết tài nguyên đã được tạo, cập nhật, xóa hay chỉ được tiếp nhận xử lý.

### 4.2. Mô tả lỗi và trường hợp không thỏa điều kiện

Không phải mọi lỗi đều là 400 Bad Request. Hãy chọn mã trạng thái theo bản chất kết quả:

| Status | Tình huống điển hình | Thông tin nên giải thích |
|---|---|---|
| 400 Bad Request | Cú pháp hoặc tham số không hợp lệ | Trường sai, định dạng hoặc quy tắc kiểm tra |
| 401 Unauthorized | Thiếu hoặc không có thông tin xác thực hợp lệ | Cách xác thực cần thiết |
| 403 Forbidden | Người gọi đã xác thực nhưng không có quyền | Điều kiện quyền truy cập |
| 404 Not Found | Không tìm thấy tài nguyên hoặc không thể tiết lộ sự tồn tại của tài nguyên | Tài nguyên nào không được tìm thấy |
| 409 Conflict | Trạng thái hiện tại xung đột với yêu cầu | Trạng thái nào khiến thao tác không thể thực hiện |
| 412 Precondition Failed | Điều kiện HTTP có điều kiện, ví dụ If-Match, không thỏa | Cách lấy phiên bản mới và thử lại |
| 422 Unprocessable Content | Nội dung hợp lệ về cú pháp nhưng vi phạm quy tắc xử lý theo chính sách API | Quy tắc nghiệp vụ bị vi phạm |
| 429 Too Many Requests | Vượt giới hạn tần suất | Thời điểm có thể thử lại nếu có |

Đây là các tình huống thường gặp, không phải danh sách bắt buộc cho mọi operation. Chỉ công bố những response mà API thực sự có thể trả về. Mô tả cần khớp với exception handler, Spring Security, gateway và hành vi triển khai.

## 5. OpenAPI biểu đạt điều kiện trước và kết quả bằng cách nào?

OpenAPI không có trường chuẩn riêng cho preconditions hoặc postconditions. Ta kết hợp các thành phần sau:

| Thành phần OpenAPI | Thông tin có thể mô tả |
|---|---|
| summary | Mục đích chính của thao tác |
| description | Động cơ sử dụng, điều kiện nghiệp vụ, quy tắc chuyển trạng thái và tác động |
| security | Cơ chế xác thực cần có |
| parameters | Điều kiện truyền qua path, query, header hoặc cookie |
| requestBody | Dữ liệu cần thiết để thực hiện thao tác |
| schema | Kiểu, trường bắt buộc, giới hạn và giá trị hợp lệ |
| responses | Các kết quả thành công và lỗi |
| headers | Metadata kết quả như Location, ETag hoặc Retry-After |
| links | Liên kết một response với operation tiếp theo nếu có thể mô tả |

Nếu tổ chức cần máy đọc được một loại điều kiện nghiệp vụ đặc thù, có thể thống nhất một OpenAPI Specification Extension bắt đầu bằng x-. Tuy nhiên, extension là quy ước riêng; Swagger UI hoặc client generator có thể bỏ qua nếu không hỗ trợ. Với phần lớn API, description rõ ràng kết hợp schema và response đầy đủ là đủ.

## 6. Ví dụ nghiệp vụ: tạo đơn hàng và giữ chỗ tồn kho

Giả sử API cung cấp operation tạo đơn hàng tại POST /api/v1/orders. Khách hàng gửi danh sách sản phẩm và số lượng. Operation có các quy tắc:

- Người gọi phải được xác thực và có quyền đặt hàng trong tài khoản hiện tại.
- Tài khoản khách hàng phải đang hoạt động.
- Mỗi sản phẩm phải tồn tại và đang được mở bán.
- Số lượng mỗi dòng phải là số nguyên từ 1 đến 20.
- Tồn kho được kiểm tra và giữ chỗ trong cùng quy trình tạo đơn.
- Nếu không thể giữ chỗ đầy đủ, toàn bộ yêu cầu thất bại và không tạo đơn hàng một phần.

Khi thành công:

- API trả 201 Created.
- Đơn hàng có trạng thái PENDING_PAYMENT.
- Tồn kho được giữ chỗ trong 15 phút.
- Response trả mã đơn hàng, tổng tiền, trạng thái và thời điểm hết hạn giữ chỗ.
- Header Location trỏ đến URI của đơn hàng.

Nếu khách hàng không thanh toán trước thời hạn, đơn hàng hết hạn và phần tồn kho giữ chỗ được giải phóng theo chính sách của hệ thống. Đây là một kết quả nghiệp vụ có thể quan sát về sau, nên tài liệu cần nêu rõ thời hạn và trạng thái tiếp theo.

### 6.1. Mô tả operation bằng OpenAPI YAML

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      tags:
        - Orders
      summary: Tạo đơn hàng và giữ chỗ tồn kho
      description: |
        Tạo đơn hàng từ danh sách sản phẩm và số lượng do khách hàng gửi.

        **Điều kiện trước**
        - Người gọi đã xác thực và có quyền đặt hàng trong tài khoản hiện tại.
        - Tài khoản khách hàng đang hoạt động.
        - Mọi sản phẩm đều tồn tại và đang được mở bán.
        - Số lượng mỗi sản phẩm là số nguyên từ 1 đến 20.
        - Tồn kho có thể đáp ứng toàn bộ yêu cầu tại thời điểm xử lý.

        **Kết quả khi thành công**
        - Đơn hàng được tạo ở trạng thái PENDING_PAYMENT.
        - Tồn kho được giữ chỗ trong 15 phút.
        - Response chứa mã đơn, tổng tiền và thời điểm hết hạn giữ chỗ.
        - Header Location chứa URI của đơn hàng mới.

        Nếu không thể giữ chỗ đầy đủ, request thất bại và không tạo đơn hàng
        một phần. Nếu khách hàng không thanh toán trước thời hạn, đơn hàng
        hết hạn và tồn kho giữ chỗ được giải phóng.
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đơn hàng đã được tạo và tồn kho đã được giữ chỗ.
          headers:
            Location:
              description: URI của đơn hàng mới.
              schema:
                type: string
                format: uri-reference
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          description: Request thiếu trường bắt buộc hoặc có giá trị sai định dạng.
        '401':
          description: Thiếu access token hoặc token không hợp lệ.
        '403':
          description: Người gọi không có quyền đặt hàng cho tài khoản này.
        '404':
          description: Không tìm thấy một hoặc nhiều sản phẩm được yêu cầu.
        '409':
          description: Tồn kho không đủ hoặc trạng thái sản phẩm không còn cho phép đặt hàng.
        '422':
          description: Tài khoản không hoạt động hoặc quy tắc nghiệp vụ không được đáp ứng.
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - items
      properties:
        items:
          type: array
          minItems: 1
          items:
            type: object
            required:
              - productId
              - quantity
            properties:
              productId:
                type: integer
                format: int64
              quantity:
                type: integer
                minimum: 1
                maximum: 20
    OrderResponse:
      type: object
      required:
        - orderId
        - status
        - total
        - reservationExpiresAt
      properties:
        orderId:
          type: string
          example: ord_1024
        status:
          type: string
          enum:
            - PENDING_PAYMENT
        total:
          type: number
          format: double
          example: 1250000
        reservationExpiresAt:
          type: string
          format: date-time
          description: Thời điểm hết hạn giữ chỗ tồn kho theo múi giờ UTC.
```

Mô tả trên cho người gọi biết cả điều kiện và kết quả. Các response cũng được tách theo tình huống để client có thể xử lý đúng. Trong dự án thật, status code và schema lỗi cần khớp với cách backend triển khai; không nên khai báo 404, 409 hoặc 422 nếu API không trả những mã đó.

### 6.2. Đưa mô tả vào controller Spring Boot

Springdoc đọc annotation OpenAPI trên controller để bổ sung thông tin cho tài liệu. Ví dụ rút gọn:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders")
@Tag(name = "Orders", description = "API quản lý đơn hàng")
public class OrderController {

    @PostMapping
    @Operation(
        operationId = "createOrder",
        summary = "Tạo đơn hàng và giữ chỗ tồn kho",
        security = @SecurityRequirement(name = "bearerAuth"),
        description =
            "Tạo đơn hàng từ danh sách sản phẩm và số lượng do khách hàng gửi. " +
            "\n\n**Điều kiện trước**\n" +
            "- Người gọi đã xác thực và có quyền đặt hàng trong tài khoản hiện tại.\n" +
            "- Tài khoản khách hàng đang hoạt động.\n" +
            "- Mọi sản phẩm tồn tại, đang mở bán và có đủ tồn kho.\n" +
            "- Số lượng mỗi sản phẩm là số nguyên từ 1 đến 20.\n" +
            "\n**Kết quả khi thành công**\n" +
            "- Đơn hàng được tạo ở trạng thái PENDING_PAYMENT.\n" +
            "- Tồn kho được giữ chỗ trong 15 phút.\n" +
            "- Response chứa mã đơn hàng, tổng tiền và thời điểm hết hạn giữ chỗ.\n" +
            "- Nếu không thể giữ chỗ đầy đủ, không tạo đơn hàng một phần."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đơn hàng đã được tạo và tồn kho đã được giữ chỗ.",
            headers = @Header(
                name = "Location",
                description = "URI của đơn hàng mới."
            ),
            content = @Content(
                schema = @Schema(implementation = OrderResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Request thiếu trường bắt buộc hoặc có giá trị sai định dạng."
        ),
        @ApiResponse(
            responseCode = "401",
            description = "Thiếu access token hoặc token không hợp lệ."
        ),
        @ApiResponse(
            responseCode = "403",
            description = "Người gọi không có quyền đặt hàng cho tài khoản này."
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy một hoặc nhiều sản phẩm được yêu cầu."
        ),
        @ApiResponse(
            responseCode = "409",
            description = "Tồn kho không đủ hoặc sản phẩm không còn được mở bán."
        ),
        @ApiResponse(
            responseCode = "422",
            description = "Tài khoản không hoạt động hoặc quy tắc nghiệp vụ không được đáp ứng."
        )
    })
    public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        OrderResponse response = orderService.create(request);
        URI location = URI.create("/api/v1/orders/" + response.orderId());
        return ResponseEntity.created(location).body(response);
    }
}
```

Đây là ví dụ minh họa cấu trúc annotation; các kiểu CreateOrderRequest, OrderResponse và orderService cần được định nghĩa theo ứng dụng. Ví dụ giả định OrderResponse có accessor orderId() và scheme bearerAuth đã được khai báo trong cấu hình OpenAPI chung. Import java.net.URI cần được bổ sung cho biến Location.

@Valid kích hoạt Bean Validation cho request DTO. Các annotation OpenAPI mô tả hợp đồng công khai; chúng không tự thực thi quyền đặt hàng, kiểm tra tồn kho hoặc thời hạn giữ chỗ. Những điều kiện đó phải được backend triển khai và kiểm thử.

## 7. Mô tả điều kiện trước ở cấp HTTP

Ngoài điều kiện nghiệp vụ, HTTP còn có cơ chế điều kiện request. Ví dụ, client muốn cập nhật tài nguyên chỉ khi tài nguyên chưa bị thay đổi kể từ lần đọc trước. Client có thể gửi header If-Match với ETag đã nhận:

```yaml
paths:
  /api/v1/products/{productId}:
    put:
      summary: Cập nhật sản phẩm nếu phiên bản không đổi
      description: |
        Chỉ cập nhật khi ETag hiện tại của sản phẩm khớp với giá trị
        If-Match do client gửi. Nếu sản phẩm đã thay đổi kể từ lần đọc,
        server không áp dụng cập nhật và trả 412 Precondition Failed.
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: integer
            format: int64
        - name: If-Match
          in: header
          required: true
          description: ETag của phiên bản sản phẩm mà client đã đọc.
          schema:
            type: string
      responses:
        '200':
          description: Sản phẩm đã được cập nhật.
          headers:
            ETag:
              description: ETag mới của sản phẩm.
              schema:
                type: string
        '412':
          description: ETag không còn khớp; client cần đọc lại tài nguyên trước khi thử cập nhật.
```

Trong trường hợp này, If-Match là điều kiện ở tầng HTTP. Nó khác với điều kiện nghiệp vụ như “đơn hàng phải ở trạng thái DRAFT”. Cả hai đều cần được mô tả, nhưng cơ chế kiểm tra và mã trạng thái có thể khác nhau.

## 8. Mô tả kết quả đồng bộ và bất đồng bộ

Một operation có thể hoàn tất ngay trong request hoặc chỉ tiếp nhận công việc.

| Kiểu xử lý | Response thường gặp | Điều client cần biết |
|---|---|---|
| Hoàn tất đồng bộ | 200 OK, 201 Created, 204 No Content | Kết quả đã có tại thời điểm response |
| Tiếp nhận xử lý bất đồng bộ | 202 Accepted | Công việc đã được tiếp nhận; chưa có nghĩa là đã hoàn tất |

Với 202 Accepted, hãy mô tả cách client theo dõi kết quả: URI trạng thái trong response body, header Location, webhook callback hoặc một cơ chế thông báo khác. Cũng cần nêu trạng thái trung gian và các kết quả cuối như hoàn tất, thất bại hoặc hết hạn.

Ví dụ:

```yaml
responses:
  '202':
    description: Yêu cầu xuất báo cáo đã được tiếp nhận, quá trình tạo file đang diễn ra.
    headers:
      Location:
        description: URI để truy vấn trạng thái tác vụ.
        schema:
          type: string
          format: uri-reference
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/JobAccepted'
```

Không nên mô tả 202 bằng câu “Xuất báo cáo thành công” nếu file chưa được tạo. Người tích hợp cần biết công việc đang ở trạng thái nào và phải làm gì tiếp theo.

## 9. Viết description dễ đọc và có thể kiểm thử

Một description hữu ích nên trả lời theo thứ tự:

1. **Mục đích:** operation giải quyết nhu cầu nào?
2. **Đối tượng:** tài nguyên hoặc chủ thể nào bị tác động?
3. **Điều kiện trước:** quyền, trạng thái, dữ liệu và tài nguyên liên quan cần đáp ứng điều gì?
4. **Quy tắc xử lý:** giới hạn hoặc quyết định nghiệp vụ nào ảnh hưởng kết quả?
5. **Kết quả thành công:** trạng thái HTTP, dữ liệu, header và trạng thái tài nguyên là gì?
6. **Kết quả không thành công:** điều kiện nào dẫn đến từng mã lỗi và client nên làm gì?
7. **Tác động theo thời gian:** có thời hạn, xử lý nền, giải phóng tài nguyên hoặc bước tiếp theo nào không?

Ví dụ description ngắn nhưng đủ thông tin:

```text
Tạo yêu cầu hoàn tiền cho một giao dịch đã thanh toán.

Điều kiện trước:
- Giao dịch tồn tại và thuộc tài khoản của người gọi.
- Giao dịch đang ở trạng thái PAID.
- Số tiền hoàn lớn hơn 0 và không vượt quá số tiền còn có thể hoàn.
- Người gọi có quyền quản lý hoàn tiền.

Kết quả:
- Trả 201 khi yêu cầu hoàn tiền được tạo.
- Yêu cầu bắt đầu ở trạng thái PENDING_REVIEW.
- Response chứa refundId và thời điểm tạo yêu cầu.
- Trả 409 nếu giao dịch không còn đủ số dư có thể hoàn hoặc trạng thái không cho phép hoàn.

Yêu cầu ở trạng thái PENDING_REVIEW chưa có nghĩa tiền đã được hoàn về tài khoản.
```

Mỗi điều kiện có thể chuyển thành một hoặc nhiều ca kiểm thử. Ví dụ, giao dịch PAID tạo yêu cầu thành công; giao dịch CANCELLED trả 409; người không có quyền nhận 403; số tiền bằng 0 bị từ chối theo quy tắc validation.

## 10. Tránh những mô tả gây hiểu nhầm

| Cách viết chưa tốt | Vấn đề | Cách viết tốt hơn |
|---|---|---|
| “Thực hiện tạo đơn hàng.” | Không nói đơn hàng được tạo trong trạng thái nào | “Tạo đơn hàng ở trạng thái PENDING_PAYMENT và giữ chỗ tồn kho trong 15 phút.” |
| “Yêu cầu phải hợp lệ.” | Không xác định hợp lệ theo tiêu chí nào | Nêu trường bắt buộc, miền giá trị và quy tắc nghiệp vụ |
| “Trả lỗi nếu không thành công.” | Không giúp client phân loại lỗi | Khai báo response riêng cho 400, 401, 403, 404, 409... khi thực tế hỗ trợ |
| “202: Thành công.” | Có thể khiến client nghĩ công việc đã hoàn tất | Nêu rõ tác vụ đã được tiếp nhận và cách truy vấn trạng thái |
| “Chỉ admin mới được gọi.” | Không chỉ ra cơ chế quyền hoặc phạm vi admin | Mô tả security scheme và quyền cụ thể theo chính sách API |
| “Hệ thống xử lý theo quy trình nội bộ.” | Không cung cấp kết quả có thể quan sát | Mô tả trạng thái, response, header và thời hạn mà client nhìn thấy |
| “Không tìm thấy hoặc không hợp lệ.” | Gộp nhiều tình huống khác nhau | Phân tách 404, 409 hoặc 422 theo hợp đồng thực tế |

Không đưa cam kết mà hệ thống không bảo đảm. Ví dụ, nếu API chỉ kiểm tra tồn kho trước khi tạo đơn nhưng không giữ chỗ, đừng viết rằng tồn kho đã được giữ. Nếu xử lý thanh toán bất đồng bộ, đừng mô tả response tiếp nhận là thanh toán hoàn tất.

## 11. Đưa mô tả operation vào quy trình phát triển

Để mô tả không bị lỗi thời, hãy xem nó là một phần của hợp đồng cần được cập nhật cùng controller và DTO.

Khi thêm hoặc thay đổi operation:

1. Xác định nhu cầu nghiệp vụ mà operation giải quyết.
2. Ghi rõ quyền, trạng thái tài nguyên và điều kiện đầu vào.
3. Xác định kết quả thành công cùng các response lỗi có thể xảy ra.
4. Mô tả response body, schema và header để client có thể sử dụng kết quả.
5. Bổ sung @Operation, @Parameter, @ApiResponse hoặc @Schema ở vị trí phù hợp.
6. Kiểm tra tài liệu JSON/YAML do springdoc tạo ra.
7. Viết kiểm thử cho các nhánh điều kiện quan trọng và so sánh hành vi thực tế với tài liệu.

Có thể kiểm tra endpoint tài liệu mặc định bằng:

```bash
curl -s http://localhost:8080/v3/api-docs
```

Trong tài liệu JSON, tìm path và method của operation, sau đó kiểm tra summary, description, parameters, requestBody, security và responses. Mở Swagger UI để kiểm tra nội dung hiển thị có dễ đọc và đủ rõ cho người tích hợp hay không.

Với CI, có thể bổ sung kiểm tra rằng các operation công khai có summary, mô tả, response thành công và response lỗi theo quy ước của dự án. Kiểm thử hợp đồng cần xác nhận cả schema lẫn các kết quả nghiệp vụ mà description cam kết.

## 12. Ghi nhớ

- summary nêu ngắn gọn mục đích; description giải thích động cơ sử dụng và quy tắc nghiệp vụ.
- Điều kiện trước có thể liên quan đến danh tính, quyền, trạng thái tài nguyên, dữ liệu đầu vào và tài nguyên phụ thuộc.
- Kết quả quan sát gồm status code, response body, header, trạng thái tài nguyên và tác động tiếp theo.
- OpenAPI không có trường chuẩn riêng cho preconditions/postconditions; hãy kết hợp description, security, parameters, requestBody, schemas, responses và headers.
- Mỗi response phải mô tả điều client thực sự có thể quan sát; phân biệt rõ xử lý đã hoàn tất với yêu cầu mới được tiếp nhận.
- Annotation OpenAPI chỉ mô tả hợp đồng. Backend vẫn phải thực thi và kiểm thử các điều kiện nghiệp vụ.
- Description tốt giúp người tích hợp gọi đúng operation, xử lý đúng kết quả và giúp nhóm phát triển biến hợp đồng thành ca kiểm thử.

Khi viết tài liệu bằng springdoc-openapi, hãy mô tả operation từ góc nhìn của người gọi API: vì sao họ cần thao tác, cần đáp ứng điều kiện gì và có thể dựa vào kết quả nào. Một hợp đồng rõ ràng giúp client tích hợp ổn định và giúp thay đổi nghiệp vụ được đánh giá chính xác hơn.
