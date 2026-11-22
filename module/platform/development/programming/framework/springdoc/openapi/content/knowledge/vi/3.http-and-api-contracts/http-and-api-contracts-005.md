# Biểu diễn JSON, form, multipart và dữ liệu nhị phân

Một API HTTP có thể nhận hoặc trả dữ liệu dưới nhiều dạng: JSON, biểu mẫu URL-encoded, biểu mẫu multipart có tệp đính kèm, hoặc một luồng byte như PDF và ảnh. Với **springdoc-openapi**, mục tiêu là để tài liệu OpenAPI mô tả đúng dạng dữ liệu mà controller Spring Boot thực sự nhận và trả về. Khi hợp đồng được mô tả chính xác, người tích hợp có thể biết phải gửi **Content-Type** nào, cấu trúc body ra sao và đọc response theo cách nào.

## 1. Media type quyết định cách biểu diễn dữ liệu

HTTP dùng header **Content-Type** để cho biết định dạng của body trong request hoặc response. Header **Accept** cho biết client muốn nhận response ở những định dạng nào. Hai header này có vai trò khác nhau:

- **Content-Type**: định dạng dữ liệu đang được gửi.
- **Accept**: định dạng response mà client có thể xử lý.
- **consumes** trong Spring MVC: giới hạn media type mà endpoint chấp nhận ở request.
- **produces** trong Spring MVC: khai báo media type mà endpoint có thể trả về.

Một số media type thường gặp:

| Media type | Cách biểu diễn | Tình huống thường dùng |
| --- | --- | --- |
| **application/json** | Đối tượng hoặc mảng JSON | Tạo, cập nhật và truy vấn tài nguyên qua API |
| **application/x-www-form-urlencoded** | Các cặp **key=value** được mã hóa trong body | Form đơn giản như đăng nhập hoặc gửi bộ lọc |
| **multipart/form-data** | Nhiều phần dữ liệu trong một body, mỗi phần có header riêng | Tải tệp cùng metadata hoặc nhiều tệp |
| **application/octet-stream** | Dãy byte thô | Upload hoặc download dữ liệu nhị phân không cần cấu trúc multipart |
| **application/pdf**, **image/png** | Byte của một định dạng cụ thể | Trả tài liệu PDF hoặc hình ảnh |

Không nên xem JSON, form và multipart là những cách viết khác nhau của cùng một body. Mỗi định dạng có quy tắc mã hóa, cách binding trong Spring và schema OpenAPI riêng.

## 2. JSON: biểu diễn đối tượng có cấu trúc

JSON phù hợp với request có nhiều trường dữ liệu liên quan. Spring MVC thường dùng **@RequestBody** để chuyển JSON thành DTO và dùng **@ResponseBody** hoặc **ResponseEntity** để ghi kết quả thành JSON. Trong REST controller, kết quả từ phương thức thường được ghi vào response thông qua message converter của Spring.

Ví dụ DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank
    @Schema(description = "Mã khách hàng")
    String customerCode,

    @Positive
    @Schema(description = "Số lượng sản phẩm")
    int quantity
) {}

public record OrderView(
    String id,
    String customerCode,
    int quantity,
    String status
) {}
~~~

Controller khai báo rõ media type:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(summary = "Tạo đơn hàng")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đơn hàng đã được tạo",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderView.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Dữ liệu đầu vào không hợp lệ"
        )
    })
    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderView> create(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        OrderView result = new OrderView(
            "ORD-1001",
            request.customerCode(),
            request.quantity(),
            "CREATED"
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
~~~

Springdoc có thể suy ra request body từ **@RequestBody**, kiểu DTO, **consumes** và kiểu trả về. Các annotation **@Schema**, **@Operation**, **@ApiResponse** và **@Content** giúp bổ sung mô tả hoặc xác định rõ schema khi hợp đồng cần chi tiết hơn.

Request JSON tương ứng:

~~~json
{
  "customerCode": "CUS-100",
  "quantity": 2
}
~~~

Trong OpenAPI, request body và response được mô tả riêng. Ví dụ rút gọn:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
responses:
  '201':
    description: Đơn hàng đã được tạo
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderView'
~~~

Nếu một endpoint nhận JSON nhưng trả về một media type khác, hãy mô tả riêng **consumes** và **produces**. Không suy ra response luôn là JSON chỉ vì request body là JSON.

## 3. Form URL-encoded: các trường đơn giản trong body

**application/x-www-form-urlencoded** mã hóa các trường thành chuỗi cặp khóa và giá trị, tương tự phần dữ liệu sau dấu hỏi trong URL nhưng được đặt trong body. Ví dụ:

~~~text
username=linh&password=secret
~~~

Spring MVC có thể bind dữ liệu dạng form vào một object bằng **@ModelAttribute**. Nếu muốn OpenAPI thể hiện đây là request body có media type **application/x-www-form-urlencoded**, có thể khai báo rõ **requestBody** bằng annotation của OpenAPI:

~~~java
public record LoginForm(
    @NotBlank
    @Schema(description = "Tên đăng nhập")
    String username,

    @NotBlank
    @Schema(description = "Mật khẩu", format = "password")
    String password
) {}

@PostMapping(
    value = "/api/sessions",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Đăng nhập bằng biểu mẫu",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            schema = @Schema(implementation = LoginForm.class)
        )
    )
)
SessionView login(
    @Parameter(hidden = true) @ModelAttribute LoginForm form
) {
    // Xác thực thông tin và tạo phiên làm việc.
    return sessionService.login(form);
}
~~~

Trong ví dụ, **SessionView** và **sessionService** đại diện cho kiểu response và dịch vụ nghiệp vụ của ứng dụng. Khi springdoc đồng thời suy luận **@ModelAttribute** thành các parameter riêng, hãy kiểm tra tài liệu sinh ra để tránh mô tả trùng trường form ở query và request body; dùng **@Parameter(hidden = true)** cho tham số binding nếu cần và giữ schema request body tường minh.

Ví dụ OpenAPI:

~~~yaml
requestBody:
  required: true
  content:
    application/x-www-form-urlencoded:
      schema:
        type: object
        required:
          - username
          - password
        properties:
          username:
            type: string
          password:
            type: string
            format: password
~~~

Form URL-encoded phù hợp với dữ liệu dạng trường văn bản. Khi cần gửi tệp, dùng **multipart/form-data** thay vì cố đưa nội dung tệp vào một trường URL-encoded.

## 4. Multipart: kết hợp tệp và metadata

**multipart/form-data** chia body thành nhiều part. Mỗi part có tên, header và nội dung riêng. Một request có thể gồm một part là tệp PDF, một part là metadata JSON và một số part văn bản khác.

Spring MVC thường dùng **MultipartFile** để nhận tệp và **@RequestPart** để đọc từng part. **@RequestPart** đặc biệt hữu ích khi một part cần được chuyển đổi bằng message converter, ví dụ metadata JSON.

Định nghĩa schema tài liệu upload:

~~~java
public record UploadMetadata(
    @NotBlank
    String title,
    String category
) {}

public record DocumentUpload(
    @Schema(
        description = "Tệp PDF cần tải lên",
        type = "string",
        format = "binary"
    )
    MultipartFile file,

    @Schema(description = "Metadata của tài liệu")
    UploadMetadata metadata
) {}
~~~

Controller nhận từng part và mô tả schema tổng thể:

~~~java
@PostMapping(
    value = "/api/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(
    summary = "Tải tài liệu lên",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
            schema = @Schema(implementation = DocumentUpload.class),
            encoding = {
                @Encoding(
                    name = "metadata",
                    contentType = MediaType.APPLICATION_JSON_VALUE
                ),
                @Encoding(
                    name = "file",
                    contentType = MediaType.APPLICATION_PDF_VALUE
                )
            }
        )
    )
)
DocumentView upload(
    @RequestPart("file") MultipartFile file,
    @Valid @RequestPart("metadata") UploadMetadata metadata
) {
    return documentService.store(file, metadata);
}
~~~

**@Schema(type = "string", format = "binary")** cho biết thuộc tính **file** chứa dữ liệu nhị phân. **@Encoding** mô tả media type của từng part; tên trong **@Encoding.name** phải khớp với tên property trong schema multipart. Nếu part metadata là JSON, client cần gửi part đó với **Content-Type: application/json** để Spring chọn đúng message converter.

OpenAPI rút gọn có dạng:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - file
          - metadata
        properties:
          file:
            type: string
            format: binary
          metadata:
            $ref: '#/components/schemas/UploadMetadata'
      encoding:
        metadata:
          contentType: application/json
        file:
          contentType: application/pdf
~~~

Một số điểm cần kiểm tra khi mô tả multipart:

- Tên part trong controller, tên property của schema và tên encoding phải thống nhất.
- Trường tệp phải được biểu diễn bằng **type: string**, **format: binary**.
- Metadata JSON cần khai báo đúng **contentType** nếu client phải gửi part dưới dạng JSON.
- Với nhiều tệp, xác định rõ API nhận một tệp hay danh sách tệp để schema phản ánh đúng kiểu dữ liệu.
- Client thường để thư viện HTTP tự tạo header **Content-Type** cùng boundary. Không tự đặt **multipart/form-data** thiếu boundary khi gửi request bằng trình duyệt hoặc thư viện hỗ trợ multipart.

## 5. Dữ liệu nhị phân: upload và download luồng byte

Khi API chỉ truyền nội dung tệp, không cần thêm metadata hoặc nhiều part, có thể dùng **application/octet-stream** hoặc media type cụ thể như **application/pdf**, **image/png**. Body lúc này là dãy byte thô.

### Upload dữ liệu nhị phân

Spring MVC có thể bind body vào **byte[]**, **Resource** hoặc kiểu dữ liệu phù hợp khác. Ví dụ dùng **byte[]**:

~~~java
@PutMapping(
    value = "/api/documents/{id}/content",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
@Operation(
    summary = "Thay nội dung tài liệu",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            schema = @Schema(type = "string", format = "binary")
        )
    )
)
@ApiResponse(responseCode = "204", description = "Nội dung đã được thay")
void replaceContent(
    @PathVariable String id,
    @RequestBody byte[] content
) {
    documentService.replaceContent(id, content);
}
~~~

Với tệp lớn, cân nhắc cách xử lý theo luồng hoặc dùng **Resource** phù hợp để tránh giữ toàn bộ nội dung trong bộ nhớ. Việc chọn kiểu Java phải phù hợp với giới hạn kích thước, cách lưu trữ và khả năng xử lý của ứng dụng.

### Download dữ liệu nhị phân

Ví dụ endpoint trả PDF:

~~~java
@GetMapping(
    value = "/api/documents/{id}/content",
    produces = MediaType.APPLICATION_PDF_VALUE
)
@Operation(summary = "Tải nội dung tài liệu PDF")
@ApiResponse(
    responseCode = "200",
    description = "Nội dung PDF",
    content = @Content(
        mediaType = MediaType.APPLICATION_PDF_VALUE,
        schema = @Schema(type = "string", format = "binary")
    )
)
ResponseEntity<Resource> download(@PathVariable String id) {
    Resource resource = documentService.loadAsResource(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_PDF)
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment()
                .filename(resource.getFilename())
                .build()
                .toString()
        )
        .body(resource);
}
~~~

Trong OpenAPI, response nhị phân cũng dùng schema **type: string**, **format: binary**. Header **Content-Disposition** có thể cho client biết nội dung nên được hiển thị trực tiếp hay tải xuống dưới dạng tệp. Nếu API trả nhiều định dạng, khai báo từng media type trong response **content** và bảo đảm controller thực sự hỗ trợ chúng.

## 6. Cách springdoc tạo request body và response

Springdoc đọc mapping và annotation Spring để tạo đặc tả OpenAPI. Các tín hiệu chính gồm:

| Thành phần Spring | Ý nghĩa trong hợp đồng OpenAPI |
| --- | --- |
| **@RequestBody** của Spring | Request body được chuyển đổi từ nội dung HTTP |
| **@RequestPart** | Một part trong request multipart |
| **@ModelAttribute** | Dữ liệu được bind vào object từ các request parameter hoặc form field |
| **consumes** | Media type được chấp nhận cho request body |
| **produces** | Media type của response |
| **@Schema** | Mô tả schema, field, kiểu dữ liệu, định dạng và ràng buộc |
| **@Operation** và OpenAPI **@RequestBody** | Bổ sung mô tả hoặc khai báo request body tường minh |
| **@ApiResponse**, **@Content** | Mô tả mã trạng thái và nội dung response |

Springdoc thường tự suy ra schema cho DTO và media type từ controller. Dùng annotation OpenAPI tường minh khi kiểu Java không đủ để thể hiện hợp đồng, khi cần mô tả nhiều media type, khi binding form tạo ra tài liệu không như mong muốn hoặc khi phải khai báo định dạng binary và encoding cho multipart.

Trong mã nguồn có hai annotation cùng tên **RequestBody**: **org.springframework.web.bind.annotation.RequestBody** của Spring dùng để binding dữ liệu và **io.swagger.v3.oas.annotations.parameters.RequestBody** dùng để mô tả hợp đồng OpenAPI. Ví dụ ở trên viết đầy đủ tên lớp OpenAPI trong thuộc tính **@Operation.requestBody** để tránh nhầm lẫn.

## 7. Thêm ví dụ và kiểm tra tài liệu sinh ra

Ví dụ giúp người tích hợp hiểu cách gửi body, nhất là với form và multipart. Có thể dùng **@ExampleObject** trong **@Content** để cung cấp ví dụ JSON hoặc dữ liệu minh họa phù hợp. Ví dụ phải khớp schema và media type của operation.

Sau khi chạy ứng dụng, kiểm tra tài liệu JSON tại endpoint OpenAPI mặc định **/v3/api-docs** hoặc đường dẫn đã cấu hình. Với mỗi operation, xác nhận:

1. **requestBody.content** chứa đúng media type mà endpoint nhận.
2. Schema JSON có đủ field, kiểu dữ liệu, trường bắt buộc và ràng buộc dự kiến.
3. Form URL-encoded xuất hiện dưới request body thay vì bị hiểu nhầm thành query parameter.
4. Multipart có schema object, tên part chính xác và field tệp được đánh dấu **format: binary**.
5. Request nhị phân dùng media type phù hợp và schema binary.
6. **responses** mô tả đúng mã trạng thái, media type, schema hoặc dữ liệu binary trả về.
7. Các header quan trọng như **Content-Disposition** được mô tả khi client cần sử dụng.

Mở Swagger UI để thử request cũng hữu ích, nhưng giao diện hiển thị được không chứng minh toàn bộ hợp đồng đã đúng. Hãy kiểm tra trực tiếp JSON OpenAPI, đặc biệt với form và multipart, vì đây là những trường hợp springdoc có thể cần annotation bổ sung để phân biệt request body với parameter.

## 8. Lỗi thường gặp

**Tài liệu hiển thị form field thành query parameter.** Kiểm tra cách controller bind **@ModelAttribute** hoặc **@RequestParam**. Nếu hợp đồng yêu cầu form body, khai báo **requestBody.content** với **application/x-www-form-urlencoded** và điều chỉnh việc suy luận parameter để không mô tả trùng.

**Swagger UI không hiển thị nút chọn tệp.** Kiểm tra schema của trường tệp có **type: string** và **format: binary**, operation có **multipart/form-data** hoặc media type nhị phân phù hợp, và tên property có khớp với tên part hay không.

**Part metadata không được parse thành object.** Đảm bảo client gửi đúng **Content-Type** cho part, ví dụ **application/json**, và controller dùng **@RequestPart** để Spring chọn message converter tương ứng.

**Tài liệu nói API trả JSON nhưng thực tế trả file.** Khai báo **produces** đúng media type, ví dụ **application/pdf**, và mô tả response bằng schema binary. Kiểm tra cả **Content-Type** thực tế trong response.

**Upload tệp lớn gây tiêu thụ bộ nhớ hoặc lỗi kích thước.** Kiểm tra giới hạn multipart của Spring Boot và máy chủ triển khai, giới hạn nghiệp vụ của API, cũng như cách đọc và lưu tệp. Đặc tả OpenAPI mô tả hợp đồng nhưng không tự đặt giới hạn upload cho ứng dụng.

## 9. Tóm tắt lựa chọn

| Nhu cầu | Media type nên dùng | Binding Spring MVC | Biểu diễn schema OpenAPI |
| --- | --- | --- | --- |
| Gửi object có cấu trúc | **application/json** | **@RequestBody** với DTO | Object và properties |
| Gửi các trường form đơn giản | **application/x-www-form-urlencoded** | **@ModelAttribute** hoặc binding form phù hợp | Object trong request body |
| Gửi tệp kèm metadata | **multipart/form-data** | **@RequestPart**, **MultipartFile** | Object có property binary và metadata |
| Gửi hoặc nhận byte thô | **application/octet-stream** hoặc media type cụ thể | **@RequestBody byte[]** / **Resource** | **type: string**, **format: binary** |

Hãy chọn media type theo dữ liệu thực tế của endpoint, mô tả request và response riêng biệt, rồi xác minh tài liệu OpenAPI sinh ra. Đó là cách bảo đảm Swagger UI và các client được tạo từ OpenAPI cùng hiểu đúng hợp đồng HTTP của ứng dụng.
