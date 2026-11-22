# @ApiResponse, @ApiResponses và tập mã trạng thái của operation

Một operation trong OpenAPI cần mô tả những phản hồi mà client có thể nhận được: khi xử lý thành công, khi dữ liệu không hợp lệ, khi tài nguyên không tồn tại hoặc khi người gọi không có quyền. Với springdoc-openapi, annotation **@ApiResponse** và **@ApiResponses** giúp khai báo rõ từng mã HTTP, nội dung phản hồi và schema tương ứng.

Việc mô tả response cần bám sát hành vi thực tế của controller và exception handler. Annotation OpenAPI chỉ tạo tài liệu; nó không tự thay đổi status code, không tạo response body và không xử lý exception. Bài này giải thích cách xây dựng tập response cho operation, kết hợp với ResponseEntity, @ResponseStatus và kiểm tra đặc tả JSON được sinh ra.

## 1. Operation Response Object mô tả điều gì?

Trong OpenAPI, mỗi operation có một đối tượng **responses** chứa các phản hồi có thể xảy ra. Mỗi phản hồi được gắn với một mã HTTP hoặc khóa **default**.

Ví dụ rút gọn:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '200':
          description: Tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Không tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
        default:
          description: Lỗi ngoài các phản hồi đã liệt kê
~~~

Mỗi Response Object thường có các phần:

| Trường | Ý nghĩa |
|---|---|
| description | Mô tả ý nghĩa của phản hồi; đây là trường bắt buộc trong Response Object |
| headers | Các HTTP header được trả về |
| content | Nội dung body theo từng media type và schema |
| links | Liên kết đến operation khác có thể thực hiện tiếp từ phản hồi |

Phản hồi không nhất thiết phải có body. Ví dụ, HTTP 204 No Content biểu thị thao tác thành công nhưng không có nội dung phản hồi. Khi đó, response có thể chỉ cần description và headers nếu có.

Một operation có thể khai báo nhiều mã phản hồi. Hãy mô tả những mã mà API thực sự có thể trả về và có ý nghĩa với client; không cần liệt kê mọi mã HTTP tồn tại trong tiêu chuẩn.

## 2. Vai trò của @ApiResponse và @ApiResponses

**@ApiResponse** mô tả một trường hợp phản hồi của operation. Thuộc tính quan trọng nhất thường là:

- responseCode: mã HTTP dưới dạng chuỗi, ví dụ "200", "201", "404" hoặc "default".
- description: ý nghĩa của phản hồi.
- content: media type và schema của response body.
- headers: các header trả về.
- links: liên kết đến operation tiếp theo.
- ref: tham chiếu đến response component dùng chung nếu tài liệu được tổ chức theo cách đó.

**@ApiResponses** là annotation chứa một danh sách @ApiResponse. Nó giúp khai báo nhiều trường hợp phản hồi trên cùng method controller.

Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@GetMapping("/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy đơn hàng"
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy đơn hàng"
    )
})
public OrderResponse getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Một response có thể được mô tả đầy đủ hơn bằng content và schema. Khi cần biểu diễn response body, nên khai báo media type và kiểu dữ liệu để Swagger UI và client generator hiểu cấu trúc phản hồi.

Không nên nhầm tên annotation với hành vi HTTP. @ApiResponse(responseCode = "404") không làm controller tự trả về 404. Nó chỉ công bố trong OpenAPI rằng operation có phản hồi 404.

## 3. Mô tả response thành công có schema

Ví dụ endpoint trả về thông tin đơn hàng:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import java.net.URI;
import java.util.Optional;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@GetMapping("/{id}")
@Operation(
    operationId = "getOrderById",
    summary = "Lấy đơn hàng theo mã"
)
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy đơn hàng",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<?> getOrder(
    @PathVariable String id
) {
    Optional<OrderResponse> result = orderService.findById(id);
    if (result.isPresent()) {
        return ResponseEntity.ok(result.get());
    }
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(new ApiError("ORDER_NOT_FOUND", "Không tìm thấy đơn hàng", null));
}
~~~

Trong ví dụ:

- 200 mô tả body có kiểu OrderResponse.
- 404 mô tả tình huống không tìm thấy tài nguyên.
- ResponseEntity cho phép controller chọn status code thực tế theo kết quả xử lý.
- @ApiResponses công bố hai nhánh trong hợp đồng OpenAPI.

Implementation trả về ApiError trong nhánh 404, vì vậy body thực tế khớp schema được mô tả. Kiểu trả về ResponseEntity<?> phản ánh hai kiểu body khác nhau; nếu muốn client có kiểu lỗi rõ ràng, giữ schema success và error tách biệt như trong OpenAPI.

Nếu controller trả về một kiểu cố định và không có nhánh status động, springdoc có thể suy ra một phần response từ kiểu trả về. Tuy nhiên, các response lỗi hoặc các nhánh đặc biệt nên được mô tả tường minh.

## 4. Phân biệt response 200, 201, 202 và 204

Các mã 2xx đều biểu thị request được xử lý thành công ở một mức độ nào đó, nhưng không có cùng ý nghĩa.

| Mã | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| 200 OK | Request thành công; thường có response body | Truy vấn chi tiết đơn hàng |
| 201 Created | Một tài nguyên mới đã được tạo | Tạo khách hàng hoặc đơn hàng |
| 202 Accepted | Request đã được chấp nhận để xử lý, chưa có nghĩa xử lý hoàn tất | Gửi tác vụ chạy nền |
| 204 No Content | Request thành công và không trả response body | Xóa tài nguyên |

Ví dụ tạo đơn hàng trả 201:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Tạo đơn hàng mới"
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Đơn hàng đã được tạo",
        headers = @Header(
            name = "Location",
            description = "URL của đơn hàng vừa tạo",
            schema = @Schema(type = "string", format = "uri")
        ),
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu yêu cầu không hợp lệ",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<OrderResponse> createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    OrderResponse created = orderService.create(request);
    URI location = URI.create("/api/orders/" + created.getId());

    return ResponseEntity.created(location).body(created);
}
~~~

ResponseEntity.created(location) tạo phản hồi 201 và header Location. Trong OpenAPI, nếu muốn client biết header này, hãy mô tả header trong @ApiResponse.

Ví dụ thao tác xóa trả 204:

~~~java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
@ApiResponse(
    responseCode = "204",
    description = "Đơn hàng đã được xóa"
)
public void deleteOrder(@PathVariable String id) {
    orderService.delete(id);
}
~~~

Không nên mô tả response 204 có JSON body. Theo ngữ nghĩa HTTP, phản hồi 204 không có nội dung. Nếu cần trả thông tin xác nhận hoặc dữ liệu đã xóa, hãy chọn mã và thiết kế response phù hợp, thường là 200 với body.

## 5. Mô tả response lỗi với schema dùng chung

Các operation thường trả về cùng một định dạng lỗi. Có thể tạo DTO dùng chung:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "ApiError",
    description = "Thông tin lỗi trả về từ API"
)
public class ApiError {

    @Schema(
        description = "Mã lỗi ổn định để client xử lý",
        example = "ORDER_NOT_FOUND"
    )
    private String code;

    @Schema(
        description = "Thông báo dễ đọc",
        example = "Không tìm thấy đơn hàng"
    )
    private String message;

    @Schema(
        description = "Mã định danh để tra cứu log",
        example = "req-7f9a2c"
    )
    private String traceId;

    // Constructor, getters và setters.
}
~~~

Sau đó dùng schema này cho các response lỗi:

~~~java
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy tài nguyên",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Một schema lỗi thống nhất giúp client dễ đọc response và ánh xạ code nghiệp vụ. Tuy nhiên, chỉ dùng chung khi cấu trúc và ngữ nghĩa thực sự giống nhau. Lỗi validation có thể cần danh sách field violation; lỗi conflict có thể cần thông tin trạng thái hiện tại. Nếu response khác nhau, hãy tạo schema cụ thể hoặc một cấu trúc composition được thiết kế rõ ràng.

## 6. Mô tả nhiều mã lỗi cho một operation

Một endpoint truy vấn đơn hàng có thể có các trường hợp:

- 400: tham số không hợp lệ.
- 401: chưa xác thực.
- 403: đã xác thực nhưng không có quyền.
- 404: không tìm thấy đơn hàng.
- 429: vượt giới hạn request nếu hệ thống áp dụng rate limit.
- 500: lỗi ngoài dự kiến của server.

Không phải endpoint nào cũng có tất cả các mã trên. Hãy dựa vào security policy, controller, exception handler và gateway thực tế.

Ví dụ khai báo:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy đơn hàng",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Tham số truy vấn không hợp lệ",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "401",
        description = "Yêu cầu xác thực",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Không có quyền truy cập",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy đơn hàng",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
~~~

Nếu mọi response lỗi có cùng schema, có thể dùng một component response dùng chung để tránh lặp metadata. Dù vậy, mỗi operation vẫn nên công bố đúng tập status code có thể xảy ra trong ngữ cảnh của nó.

## 7. Phân biệt @ApiResponse với @ResponseStatus

Hai annotation có mục đích khác nhau:

| Annotation | Tác dụng |
|---|---|
| @ApiResponse | Mô tả response trong tài liệu OpenAPI |
| @ApiResponses | Gom nhiều mô tả response cho operation |
| @ResponseStatus | Đặt HTTP status thực tế cho handler khi Spring xử lý request |
| @ExceptionHandler | Chọn cách xử lý exception trong controller hoặc advice |
| ResponseEntity | Cho phép trả status, header và body theo từng nhánh runtime |

Ví dụ:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
@ApiResponse(
    responseCode = "201",
    description = "Tạo tài nguyên thành công"
)
public ProductResponse create(
    @RequestBody ProductRequest request
) {
    return productService.create(request);
}
~~~

Ở đây @ResponseStatus đặt status thực tế là 201; @ApiResponse ghi lại cùng status đó trong tài liệu.

Nếu chỉ có @ApiResponse(responseCode = "201") mà method không dùng ResponseEntity, @ResponseStatus hoặc cơ chế khác để trả 201, ứng dụng vẫn có thể trả status mặc định 200. Đây là một dạng sai lệch hợp đồng cần tránh.

Khi dùng ResponseEntity, status có thể thay đổi theo nhánh xử lý. Khi đó, hãy liệt kê các nhánh tương ứng trong @ApiResponses và kiểm tra test runtime.

## 8. @ApiResponse không thay thế exception handling

Giả sử service ném OrderNotFoundException. Để ứng dụng thực sự trả HTTP 404, cần có logic xử lý exception, chẳng hạn @RestControllerAdvice:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
        OrderNotFoundException exception
    ) {
        ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            exception.getMessage(),
            null
        );

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }
}
~~~

Trong operation controller, cần mô tả response 404 với schema ApiError. Việc có exception handler không tự động bảo đảm mọi operation được mô tả đầy đủ trong OpenAPI; hãy kiểm tra cách cấu hình springdoc của dự án và tài liệu đầu ra.

Tương tự, MethodArgumentNotValidException có thể được xử lý thành 400, AccessDeniedException thành 403 hoặc exception nghiệp vụ thành 409. Mỗi mapping phải thống nhất giữa:

1. Exception thực tế được ném ra.
2. Exception handler quyết định status và body.
3. @ApiResponse công bố status và schema.
4. Test xác minh phản hồi thực tế.

Nếu một exception có thể được ném ở nhiều operation, nhóm có thể cân nhắc cách khai báo response dùng chung hoặc customizer. Không nên giả định việc thêm @ApiResponse lên một exception handler sẽ tự áp dụng chính xác cho mọi operation trong mọi cấu hình.

## 9. Mô tả response không có body

Một số status không cần body hoặc không được phép có body theo ngữ nghĩa HTTP. Ví dụ phổ biến là 204 No Content.

Có thể khai báo:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Đã xóa thành công"
)
~~~

Nếu response chỉ có header, khai báo headers mà không thêm content:

~~~java
@ApiResponse(
    responseCode = "202",
    description = "Tác vụ đã được tiếp nhận",
    headers = {
        @Header(
            name = "Location",
            description = "URL để theo dõi trạng thái tác vụ",
            schema = @Schema(type = "string", format = "uri")
        )
    }
)
~~~

Với response 202, body có thể có hoặc không tùy thiết kế. Nếu API trả task identifier trong body, hãy khai báo content và schema tương ứng. Nếu chỉ trả Location, mô tả header đó để client biết cách theo dõi.

Tránh khai báo content với schema rỗng hoặc schema không liên quan cho một response không có body. Điều đó có thể khiến generator sinh method mong đợi dữ liệu mà server không gửi.

## 10. Mô tả response header

Response có thể mang metadata qua HTTP header, chẳng hạn Location, ETag, Retry-After hoặc X-Request-Id.

Ví dụ:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Tạo tài nguyên thành công",
    headers = {
        @Header(
            name = "Location",
            description = "URL của tài nguyên vừa tạo",
            schema = @Schema(type = "string", format = "uri")
        ),
        @Header(
            name = "ETag",
            description = "Mã phiên bản của tài nguyên",
            schema = @Schema(type = "string")
        )
    },
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Mô tả header hữu ích khi client cần lấy URL tài nguyên mới, kiểm soát cache hoặc gửi điều kiện cập nhật. Hãy xác minh server thực sự trả header đó ở runtime. Annotation không tự thêm Location hoặc ETag vào response.

Đối với header Retry-After khi trả 429 hoặc 503, mô tả kiểu và đơn vị/ý nghĩa trong description để client biết cách chờ trước khi thử lại. Không khai báo header chỉ vì gateway có thể trả nó trong một số trường hợp nếu ứng dụng không cam kết hành vi đó.

## 11. Mô tả media type và response body

Một response có thể trả JSON, XML, văn bản hoặc nội dung nhị phân. Thuộc tính content cho phép mô tả nhiều media type.

Ví dụ response JSON:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Trả về thông tin sản phẩm",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Ví dụ response dạng văn bản:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Trả về nội dung CSV",
    content = @Content(
        mediaType = "text/csv",
        schema = @Schema(type = "string")
    )
)
~~~

Ví dụ file nhị phân:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Tải xuống báo cáo",
    content = @Content(
        mediaType = "application/octet-stream",
        schema = @Schema(type = "string", format = "binary")
    )
)
~~~

Media type trong OpenAPI cần khớp với Content-Type thực tế. Nếu controller trả application/pdf nhưng spec mô tả application/json, client generator có thể tạo kiểu xử lý body sai.

Khi endpoint hỗ trợ nhiều Accept type, hãy mô tả từng loại và schema tương ứng. Với file download, kiểm tra cách generator xử lý stream hoặc byte array trong ngôn ngữ đích.

## 12. Response mặc định và mã lỗi chưa liệt kê

OpenAPI cho phép khóa **default** trong responses. Nó mô tả phản hồi dùng cho mọi mã HTTP không được liệt kê riêng trong operation.

Ví dụ:

~~~yaml
responses:
  '200':
    description: Thành công
  '404':
    description: Không tìm thấy
  default:
    description: Lỗi khác
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ApiError'
~~~

default không có nghĩa là HTTP 200 hoặc status mặc định của Spring. Nó là mô tả bao quát cho các response code không được khai báo cụ thể.

Có thể dùng @ApiResponse(responseCode = "default", ...) để khai báo trong annotation. Tuy nhiên, không nên chỉ dùng default thay cho các mã quan trọng mà client cần xử lý riêng. Nếu client cần phân biệt 400 với 409 hoặc 429, hãy liệt kê chúng tường minh.

## 13. Tái sử dụng Response Object

Nếu nhiều operation dùng chung một response lỗi, có thể định nghĩa component trong components.responses:

~~~yaml
components:
  responses:
    NotFound:
      description: Không tìm thấy tài nguyên
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
~~~

Operation tham chiếu response component:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '404':
          $ref: '#/components/responses/NotFound'
~~~

Với swagger-annotations, @ApiResponse hỗ trợ thuộc tính ref để tham chiếu response đã định nghĩa trong tài liệu. Khi dùng tham chiếu, hãy kiểm tra $ref đầu ra có đúng đường dẫn component và component có tồn tại hay không.

Tái sử dụng giúp giảm lặp nhưng chỉ nên dùng khi description, schema, headers và ý nghĩa của response giống nhau. Nếu một lỗi 404 của đơn hàng có thông tin riêng khác lỗi 404 của khách hàng, có thể cần response component riêng hoặc mô tả tường minh tại operation.

## 14. Response theo nhiều nhánh runtime

Khi controller dùng ResponseEntity hoặc exception handler xử lý các nhánh lỗi, một operation có thể trả nhiều status code. Ví dụ:

~~~java
@PutMapping("/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Cập nhật thành công",
        content = @Content(
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Phiên bản sản phẩm đã thay đổi",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<?> updateProduct(
    @PathVariable String id,
    @RequestBody UpdateProductRequest request
) {
    // ProductNotFoundException và VersionConflictException được xử lý
    // bởi @RestControllerAdvice để trả 404 và 409 tương ứng.
    return ResponseEntity.ok(productService.update(id, request));
}
~~~

Ở ví dụ này, kiểu trả về ResponseEntity<?> quá tổng quát. Trong ứng dụng thật, hãy cân nhắc kiểu trả về cụ thể hoặc thiết kế response rõ ràng để springdoc phân tích tốt hơn. Các nhánh lỗi được xử lý trong service/advice cần có test và tài liệu tương ứng.

Không nên thêm status code vào @ApiResponses chỉ vì “có thể xảy ra” theo lý thuyết. Mỗi mã cần có căn cứ từ code, exception handler, security, gateway hoặc hợp đồng được nhóm thống nhất.

## 15. Kiểm tra mã trạng thái trong OpenAPI JSON

Sau khi ứng dụng chạy, tải tài liệu:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Xem toàn bộ response của operation:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses' openapi.json
~~~

Liệt kê các status code:

~~~bash
jq -r '.paths["/api/orders/{id}"].get.responses | keys[]' openapi.json
~~~

Xem schema của response 404:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["404"].content["application/json"].schema' openapi.json
~~~

Kiểm tra các điểm:

- Có đủ status code quan trọng không?
- Response 2xx có đúng mã với hành vi thực tế không?
- 204 có bị mô tả kèm body không?
- Response lỗi có đúng media type và schema không?
- Header như Location hoặc Retry-After có được mô tả không?
- default có đang che khuất các mã lỗi client cần xử lý riêng không?
- Các $ref có trỏ tới component tồn tại không?

Nếu springdoc tự suy ra response thành công, hãy so sánh với response được khai báo tường minh. Khi có khác biệt, kiểm tra thứ tự hoặc phạm vi annotation và cấu hình phiên bản thư viện. Kết quả cuối cùng trong JSON là tài liệu mà client generator sẽ đọc.

## 16. Kiểm tra hành vi runtime

Sau khi kiểm tra JSON, gửi request thật hoặc chạy integration test để xác minh status và body.

Ví dụ với endpoint tìm đơn hàng:

~~~bash
# Trường hợp tìm thấy đơn hàng
curl -i http://localhost:8080/api/orders/ORD-1001

# Trường hợp không tồn tại
curl -i http://localhost:8080/api/orders/unknown
~~~

So sánh status, Content-Type, header và body với OpenAPI. Nếu tài liệu ghi 404 nhưng ứng dụng trả 200 với body rỗng, cần sửa implementation hoặc tài liệu theo hợp đồng đã thống nhất.

Nên kiểm tra tối thiểu:

1. Nhánh thành công.
2. Dữ liệu request không hợp lệ.
3. Tài nguyên không tồn tại.
4. Chưa xác thực và không có quyền, nếu operation được bảo vệ.
5. Xung đột nghiệp vụ, nếu có.
6. Phản hồi không body như 204.
7. Lỗi hệ thống hoặc lỗi gateway có được mô tả ở phạm vi phù hợp không.

Các lỗi do reverse proxy hoặc API gateway có thể không đi qua Spring MVC. Nếu public contract cam kết định dạng lỗi thống nhất ở gateway, cần kiểm tra spec và test ở lớp tích hợp ngoài ứng dụng.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI chỉ hiển thị 200 | Chưa khai báo response lỗi hoặc exception handler chưa được mô tả trong operation |
| Tài liệu có 404 nhưng ứng dụng trả 200 | @ApiResponse chỉ là metadata; thiếu logic trả status thực tế |
| Response 201 nhưng không có Location | Controller chưa thêm header Location dù tài liệu mô tả |
| Response 204 có schema body | Khai báo content không phù hợp với ngữ nghĩa No Content |
| Client generator không tạo model lỗi | Response thiếu content/schema hoặc schema tham chiếu không hợp lệ |
| Body lỗi thực tế khác schema | Exception handler trả DTO khác với @Schema implementation |
| Response mặc định che mất mã quan trọng | Chưa khai báo tường minh các mã như 400, 401, 403, 404 hoặc 409 |
| Media type không khớp | Content-Type runtime khác với content trong OpenAPI |
| Header không xuất hiện trong tài liệu | Chưa khai báo headers trong @ApiResponse |
| $ref response bị lỗi | Component response hoặc schema được tham chiếu không tồn tại |
| ResponseEntity<?> làm schema quá chung | Kiểu trả về quá tổng quát; cân nhắc DTO hoặc mô tả response tường minh |

## 18. Quy ước thiết kế tập response cho operation

Một operation dễ tích hợp nên có tập response ngắn gọn, rõ ràng và phản ánh đúng hành vi:

- Ghi response thành công theo đúng status code mà controller trả về.
- Mô tả schema body cho các response có nội dung.
- Mô tả header quan trọng như Location, ETag hoặc Retry-After.
- Liệt kê riêng các lỗi client cần xử lý khác nhau.
- Dùng schema lỗi thống nhất nếu cấu trúc thực sự giống nhau.
- Dùng default cho các mã còn lại khi phù hợp, không thay thế mã quan trọng.
- Không khai báo body cho 204.
- Kiểm tra cả response do controller và exception handler tạo ra.
- Đảm bảo mã trạng thái, description, schema và test runtime thống nhất.

Không cần sao chép toàn bộ danh sách lỗi của toàn hệ thống vào từng operation. Hãy chọn các trường hợp có thể xảy ra và có ý nghĩa trong ngữ cảnh endpoint đó.

## 19. Checklist kiểm tra @ApiResponse và @ApiResponses

- [ ] Mỗi operation có mô tả response thành công phù hợp.
- [ ] responseCode khớp status code runtime.
- [ ] Mỗi response có description rõ ràng.
- [ ] Response có body đã khai báo đúng media type và schema.
- [ ] Response không body như 204 không khai báo content.
- [ ] Các mã lỗi quan trọng được liệt kê riêng.
- [ ] Schema lỗi khớp DTO do exception handler trả về.
- [ ] Header như Location, ETag hoặc Retry-After được mô tả nếu có.
- [ ] default được dùng đúng nghĩa fallback cho mã chưa liệt kê.
- [ ] Các component response và schema được tham chiếu hợp lệ.
- [ ] Đã kiểm tra responses trong /v3/api-docs.
- [ ] Đã chạy integration test cho các nhánh status quan trọng.

## 20. Nguồn tra cứu

- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Response Object](https://spec.openapis.org/oas/latest.html#response-object)
- [Swagger Annotations – API documentation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/index.html)
- [Spring Framework – @ResponseStatus](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html)
- [Spring Framework – Exception handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)

@ApiResponse và @ApiResponses mô tả tập phản hồi trong hợp đồng OpenAPI. ResponseEntity, @ResponseStatus và exception handler quyết định phản hồi thực tế khi ứng dụng chạy. Hãy giữ hai phía đồng bộ và xác minh JSON cùng integration test trước khi phát hành tài liệu cho client.
