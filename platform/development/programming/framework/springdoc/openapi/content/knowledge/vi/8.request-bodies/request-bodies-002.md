# Request Body Object và cờ required

## 1. Request body là gì trong hợp đồng HTTP API?

Request body là phần dữ liệu được client gửi trong thân HTTP request. Nó thường dùng khi tạo mới hoặc cập nhật tài nguyên, gửi lệnh nghiệp vụ hoặc tải tệp lên server. Ví dụ, khi tạo sản phẩm, client gửi một JSON chứa tên, giá và danh mục; controller nhận JSON đó và chuyển thành một đối tượng Java để xử lý.

Trong OpenAPI, phần này được mô tả bằng **Request Body Object**. Object cho biết:

- Nội dung request được gửi theo media type nào, chẳng hạn **application/json** hoặc **multipart/form-data**.
- Dữ liệu có cấu trúc ra sao thông qua schema.
- Body có bắt buộc phải xuất hiện hay không.
- Người đọc cần biết gì về cách gửi dữ liệu qua description và examples.

Với Spring Boot, Springdoc OpenAPI thường suy luận request body từ tham số controller có **@RequestBody**, kiểu DTO và mapping của endpoint. Annotation OpenAPI bổ sung mô tả khi cần kiểm soát rõ hơn nội dung tài liệu.

Request body khác với parameter trong path, query, header hoặc cookie. Các giá trị đó được mô tả bằng Parameter Object; dữ liệu trong thân request được mô tả bằng Request Body Object.

## 2. Cấu trúc Request Body Object

Trong một Operation Object, trường **requestBody** chứa Request Body Object. Cấu trúc cốt lõi gồm ba thuộc tính:

| Thuộc tính | Vai trò |
|---|---|
| **description** | Giải thích mục đích, quy tắc hoặc điều kiện của dữ liệu gửi lên |
| **content** | Map media type tới schema, ví dụ và cách mã hóa nội dung |
| **required** | Cho biết request có bắt buộc phải có body hay không |

Trong đó, **content** là thuộc tính bắt buộc của Request Body Object. **description** và **required** là tùy chọn; theo OpenAPI, **required** mặc định là false nếu không khai báo.

Ví dụ một operation nhận JSON:

~~~yaml
paths:
  /api/products:
    post:
      summary: Tạo sản phẩm
      requestBody:
        description: Thông tin sản phẩm mới
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        "201":
          description: Đã tạo sản phẩm
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
        price:
          type: number
~~~

Ví dụ này thể hiện hai cấp bắt buộc khác nhau:

- **requestBody.required: true** yêu cầu client gửi thân request.
- **schema.required: [name, price]** yêu cầu object JSON có hai thuộc tính name và price.

Hai quy tắc này độc lập. Một request body có thể bắt buộc xuất hiện nhưng cho phép object rỗng; ngược lại, nếu body không bắt buộc, schema vẫn quy định các thuộc tính phải có khi client gửi body.

## 3. Hiểu đúng cờ required của Request Body

Cờ **required** trong Request Body Object xác định sự hiện diện của toàn bộ thân request.

- **required: true**: client phải gửi body theo một trong các media type được khai báo trong content.
- **required: false** hoặc không khai báo: client có thể bỏ qua body.
- Khi body được gửi, nội dung vẫn phải tuân theo schema và media type tương ứng.

Ví dụ:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        properties:
          comment:
            type: string
~~~

Body phải xuất hiện, nhưng schema trên không bắt buộc thuộc tính comment vì không có danh sách required ở cấp schema.

Ngược lại:

~~~yaml
requestBody:
  required: false
  content:
    application/json:
      schema:
        type: object
        required:
          - comment
        properties:
          comment:
            type: string
~~~

Client có thể không gửi body. Nếu gửi body, object phải có thuộc tính comment.

### 3.1. Phân biệt body required và property required

Đây là điểm dễ nhầm khi đọc OpenAPI:

| Cấu hình | Ý nghĩa |
|---|---|
| **requestBody.required** | Toàn bộ HTTP request body có bắt buộc hay không |
| **schema.required** | Những thuộc tính bắt buộc bên trong object |
| **schema.properties.name** | Mô tả kiểu và ràng buộc của một thuộc tính |
| **nullable** hoặc kiểu chứa null | Cho phép giá trị null theo phiên bản OpenAPI và schema |

Ví dụ, nếu name nằm trong schema.required, client phải gửi thuộc tính name khi gửi object. Điều đó không tự nói rằng giá trị name được phép là null; khả năng nhận null phải được mô tả riêng trong schema.

### 3.2. Phân biệt required với nullable

Ba trường hợp sau có ý nghĩa khác nhau:

1. Body không được gửi.
2. Body được gửi nhưng một thuộc tính không xuất hiện.
3. Body được gửi, thuộc tính xuất hiện với giá trị null.

Trong OpenAPI 3.0, schema có thể dùng **nullable: true** để cho phép null cùng kiểu được khai báo. Trong OpenAPI 3.1, có thể biểu diễn null bằng JSON Schema type union, ví dụ **type: [string, "null"]**. Việc một thuộc tính có bắt buộc xuất hiện hay không vẫn do danh sách **required** của object quyết định.

Không nên dùng nullable để biểu diễn một body tùy chọn. Cũng không nên bỏ requestBody.required chỉ vì một vài thuộc tính DTO có thể null.

## 4. RequestBody Object và @RequestBody của Spring

Spring MVC dùng annotation **org.springframework.web.bind.annotation.RequestBody** để đọc thân HTTP request và chuyển đổi nội dung thành kiểu Java thông qua HttpMessageConverter.

Ví dụ:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ProductResponse create(
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Spring nhận JSON từ request body, chuyển đổi thành CreateProductRequest rồi truyền cho phương thức controller. Springdoc đọc chữ ký phương thức, kiểu DTO và mapping để tạo Request Body Object trong OpenAPI.

Có hai annotation tên gần giống nhau nhưng vai trò khác nhau:

| Annotation | Gói | Vai trò |
|---|---|---|
| **@RequestBody** của Spring | org.springframework.web.bind.annotation | Binding nội dung HTTP body vào tham số Java |
| **@RequestBody** của OpenAPI | io.swagger.v3.oas.annotations.parameters | Bổ sung metadata cho Request Body Object |

Annotation của Spring điều khiển runtime. Annotation của OpenAPI mô tả hợp đồng. Có thể dùng cả hai trên cùng tham số khi cần mô tả chi tiết.

Để tránh nhầm import, có thể viết đầy đủ tên annotation OpenAPI trong ví dụ:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ProductResponse create(
    @Valid
    @org.springframework.web.bind.annotation.RequestBody
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin cần thiết để tạo sản phẩm",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
    CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Khai báo OpenAPI tường minh hữu ích khi cần ghi rõ description, media type, schema hoặc required. Nếu Springdoc đã suy luận chính xác từ controller, không nhất thiết phải lặp lại mọi metadata.

## 5. Cách Spring @RequestBody xử lý required

Annotation Spring có thuộc tính **required**. Mặc định, **@RequestBody** của Spring MVC có **required = true**, nghĩa là request phải có nội dung body để binding thành công.

Ví dụ:

~~~java
@PostMapping("/api/comments")
public CommentResponse createComment(
    @RequestBody(required = false) CreateCommentRequest request
) {
    if (request == null) {
        return commentService.createDefault();
    }

    return commentService.create(request);
}
~~~

Trong trường hợp này, ứng dụng cho phép request không có body. Khi không có body, Spring có thể truyền giá trị null vào tham số và controller phải xử lý trường hợp đó an toàn. Hợp đồng OpenAPI tương ứng cần thể hiện **requestBody.required: false**.

Nếu body là bắt buộc, có thể giữ mặc định hoặc khai báo tường minh:

~~~java
@RequestBody(required = true) CreateProductRequest request
~~~

Không nên chỉ thay **@io.swagger.v3.oas.annotations.parameters.RequestBody(required = false)** để làm tài liệu báo body tùy chọn trong khi Spring vẫn yêu cầu body. Khi đó Swagger UI có thể cho phép bỏ trống nhưng ứng dụng vẫn trả lỗi lúc runtime.

Ngược lại, nếu Spring cho phép thiếu body nhưng OpenAPI ghi required true, client có thể hiểu sai hợp đồng và luôn gửi dữ liệu không cần thiết. Hãy đồng bộ cả hai lớp metadata.

## 6. Mô tả schema của request body

Schema cho biết cấu trúc dữ liệu mà client cần gửi. Trong Spring Boot, Springdoc thường suy luận schema từ DTO và các annotation liên quan.

Ví dụ DTO:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Schema(
        description = "Tên sản phẩm",
        example = "Bàn phím cơ"
    )
    String name,

    @NotNull
    @Positive
    @Schema(
        description = "Giá bán tính bằng VND",
        example = "1290000"
    )
    BigDecimal price,

    @Schema(
        description = "Mã danh mục",
        example = "12"
    )
    Long categoryId
) {}
~~~

Controller:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ProductResponse create(
    @Valid
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Springdoc có thể dùng kiểu Java, annotation **@Schema** và một số Bean Validation constraint để xây dựng schema trong components.schemas. Khi client mở Swagger UI, họ có thể xem cấu trúc JSON, ví dụ và các trường cần nhập.

Cần phân biệt các nguồn thông tin:

- Kiểu Java xác định cấu trúc và kiểu dữ liệu được binding.
- Bean Validation như **@NotBlank**, **@Positive** kiểm tra dữ liệu ở backend khi validation được kích hoạt.
- **@Schema** bổ sung mô tả, ví dụ, format và metadata cho tài liệu.
- **@Valid** kích hoạt quá trình validation cho đối tượng request theo cấu hình Spring.

Tài liệu chỉ chính xác khi các constraint công bố khớp với validation thực tế. Ví dụ, nếu OpenAPI đánh dấu price là bắt buộc nhưng backend không kiểm tra hoặc cho phép thiếu, hai hợp đồng có thể khác nhau.

## 7. Khai báo nhiều media type trong content

Thuộc tính **content** của Request Body Object là một map. Mỗi key là một media type; giá trị tương ứng là Media Type Object, có thể chứa schema, examples và encoding.

Một endpoint có thể chấp nhận nhiều định dạng:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/CreateProductXml'
~~~

Client chọn định dạng bằng HTTP header **Content-Type**. Ví dụ, gửi JSON thì request cần có:

~~~http
Content-Type: application/json
~~~

Nếu gửi XML:

~~~http
Content-Type: application/xml
~~~

Server phải thực sự có HttpMessageConverter hoặc cơ chế xử lý tương ứng. Chỉ thêm một media type vào OpenAPI không làm cho Spring Boot tự hỗ trợ parse định dạng đó.

Trong Spring MVC, mapping có thể công bố media type được chấp nhận qua thuộc tính **consumes**:

~~~java
@PostMapping(
    path = "/api/products",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    }
)
public ProductResponse create(
    @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Springdoc có thể sử dụng thông tin mapping và kiểu tham số để tạo nội dung tài liệu. Hãy kiểm tra OpenAPI JSON để xác nhận mỗi media type có schema phù hợp. Thuộc tính **produces** mô tả media type của response; không dùng nó để thay cho consumes của request.

## 8. Bổ sung description và ví dụ request

Một schema có kiểu dữ liệu đúng vẫn có thể khó sử dụng nếu thiếu ví dụ. Request Body Object có thể chứa description; từng Media Type Object có thể chứa **example** hoặc **examples**.

Ví dụ YAML:

~~~yaml
requestBody:
  description: Thông tin sản phẩm cần tạo. Giá được tính bằng VND.
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
      examples:
        validProduct:
          summary: Sản phẩm hợp lệ
          value:
            name: Bàn phím cơ
            price: 1290000
            categoryId: 12
~~~

Ví dụ có thể được khai báo bằng annotation:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Thông tin sản phẩm cần tạo",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateProductRequest.class),
        examples = @ExampleObject(
            name = "validProduct",
            summary = "Sản phẩm hợp lệ",
            value = """
                {
                  "name": "Bàn phím cơ",
                  "price": 1290000,
                  "categoryId": 12
                }
                """
        )
    )
)
~~~

Đoạn annotation trên là phần bổ sung cho tham số controller có Spring **@RequestBody**. Giá trị ví dụ phải là JSON hợp lệ và tuân theo schema. Nếu DTO có trường bắt buộc, ví dụ cần cung cấp đủ trường; nếu có enum, format hoặc giới hạn, ví dụ cần dùng giá trị hợp lệ.

Nên dùng ví dụ đại diện cho các tình huống thường gặp. Không đưa token thật, dữ liệu cá nhân hoặc thông tin sản xuất vào ví dụ tài liệu.

## 9. Request body với multipart và upload file

Khi client tải file cùng metadata, request thường dùng media type **multipart/form-data**. Mỗi phần của multipart có thể có kiểu nội dung riêng.

Ví dụ controller:

~~~java
@PostMapping(
    path = "/api/products/import",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ImportResult importProduct(
    @RequestPart("metadata") @Valid CreateProductRequest metadata,
    @RequestPart("file") MultipartFile file
) {
    return productService.importProduct(metadata, file);
}
~~~

Một mô hình OpenAPI tương ứng có thể là:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required:
          - metadata
          - file
        properties:
          metadata:
            $ref: '#/components/schemas/CreateProductRequest'
          file:
            type: string
            format: binary
~~~

Ví dụ schema file trên dùng cách biểu diễn phổ biến trong tài liệu OpenAPI 3.0. Nếu dự án xuất OpenAPI 3.1, hãy kiểm tra schema theo JSON Schema dialect mà tài liệu sử dụng và đối chiếu kết quả Springdoc sinh ra trước khi chuẩn hóa hợp đồng.

Trong đó, **metadata** là object dữ liệu; **file** là nội dung nhị phân. Nếu cần chỉ định content type hoặc header cho từng phần, Media Type Object có thể dùng thuộc tính **encoding**.

Springdoc thường suy luận một phần schema từ **@RequestPart**, DTO và **MultipartFile**. Tuy nhiên, cần kiểm tra OpenAPI JSON để xác nhận tên part, required và format binary. Không nên chỉ dựa vào việc Swagger UI hiện nút chọn file.

## 10. Tái sử dụng Request Body qua components

Nếu nhiều operation nhận cùng một cấu trúc request, OpenAPI cho phép định nghĩa Request Body Object dùng chung trong **components.requestBodies** và tham chiếu bằng **$ref**.

Ví dụ:

~~~yaml
components:
  requestBodies:
    CreateProductBody:
      description: Thông tin sản phẩm cần tạo
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'

paths:
  /api/products:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProductBody'
      responses:
        "201":
          description: Đã tạo sản phẩm

  /api/products/import-preview:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProductBody'
      responses:
        "200":
          description: Đã kiểm tra dữ liệu
~~~

Tái sử dụng giúp tránh lặp schema và mô tả. Tuy nhiên, chỉ dùng chung khi hai endpoint thực sự có cùng hợp đồng. Nếu một endpoint yêu cầu thêm trường, có quy tắc required khác hoặc media type khác, nên định nghĩa Request Body Object riêng để tài liệu phản ánh chính xác.

Springdoc có thể tạo schema dùng chung trong **components.schemas** khi nhiều DTO hoặc kiểu dữ liệu được tham chiếu. Việc tạo Request Body Object dùng chung thường cần cấu hình OpenAPI phù hợp hoặc tùy biến model; không nên giả định mọi DTO lặp lại sẽ tự động được đưa vào components.requestBodies.

## 11. Khi request không có body

Không phải operation nào cũng cần Request Body Object. Ví dụ GET để tra cứu tài nguyên thường truyền tiêu chí qua path hoặc query parameter và không cần body. DELETE thông thường cũng không cần body nếu hợp đồng không định nghĩa rõ một payload riêng.

HTTP có những trường hợp cho phép gửi body với các method khác nhau, nhưng client, proxy và framework không phải lúc nào cũng xử lý thống nhất. Với GET, nên ưu tiên query parameter cho điều kiện tìm kiếm để tăng khả năng tương thích.

Nếu endpoint không nhận body, không cần khai báo **requestBody** trong OpenAPI. Nếu endpoint chấp nhận body nhưng không bắt buộc, hãy khai báo Request Body Object với **required: false** và mô tả rõ hành vi khi body vắng mặt.

Không nên nhầm response không có body với request body tùy chọn. Response 204 No Content mô tả kết quả trả về của server; nó không quyết định client có phải gửi request body hay không.

## 12. Kiểm tra required và content trong tài liệu sinh ra

Sau khi khai báo controller và annotation, hãy tải OpenAPI document:

~~~http
GET /v3/api-docs
~~~

Tìm operation và kiểm tra:

- Có trường requestBody khi endpoint thực sự nhận body.
- requestBody.required có khớp với **@RequestBody(required = ...)** và hành vi runtime.
- content có đúng media type mà endpoint chấp nhận.
- Schema tham chiếu đúng DTO hoặc cấu trúc dữ liệu.
- Các thuộc tính bắt buộc trong schema được mô tả chính xác.
- Example là dữ liệu hợp lệ theo schema.
- Multipart part có tên, kiểu và required đúng.
- Không có request body được khai báo cho endpoint không nhận body.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI không hiển thị request body | Controller thiếu Spring @RequestBody, mapping hoặc annotation chưa được Springdoc nhận diện |
| Body bị đánh dấu required sai | required của Spring và OpenAPI annotation không đồng nhất |
| Thiếu schema hoặc schema quá chung | DTO không được suy luận như mong đợi hoặc thiếu @Schema(implementation = ...) |
| Media type không đúng | consumes, content type và cấu hình HttpMessageConverter không khớp |
| Body tùy chọn nhưng server vẫn trả lỗi | Spring @RequestBody vẫn required hoặc controller không xử lý null |
| Body bắt buộc nhưng schema cho phép object rỗng | requestBody.required đúng nhưng schema chưa có danh sách thuộc tính required |
| File upload không có nút chọn file | Schema multipart chưa mô tả thuộc tính file là string/binary hoặc tên part không khớp |

Kiểm tra OpenAPI document cần đi cùng integration test gửi request thật. Hãy thử request có body hợp lệ, thiếu body, sai Content-Type, thiếu trường bắt buộc và payload sai kiểu. Kết quả status code và response lỗi phải phù hợp với hợp đồng đã công bố.

## 13. Nguyên tắc thiết kế Request Body Object

Khi dùng Springdoc OpenAPI để mô tả request body, hãy giữ các quy tắc sau:

1. Dùng Spring @RequestBody để binding nội dung HTTP vào tham số Java.
2. Dùng Request Body Object để mô tả content, media type, schema, description và required.
3. Đồng bộ required của OpenAPI với hành vi runtime của Spring.
4. Phân biệt body required với các thuộc tính required bên trong schema.
5. Phân biệt dữ liệu không xuất hiện với dữ liệu có giá trị null.
6. Dùng consumes và HttpMessageConverter phù hợp với media type được công bố.
7. Dùng @Schema, Bean Validation và examples để mô tả cấu trúc, ràng buộc và dữ liệu mẫu.
8. Dùng multipart/form-data và schema binary cho upload file.
9. Chỉ tái sử dụng Request Body Object khi các endpoint có cùng hợp đồng thực tế.
10. Kiểm tra OpenAPI JSON/YAML cùng request runtime sau mỗi thay đổi.

Request Body Object cho client biết chính xác dữ liệu nào cần gửi, gửi theo định dạng nào và có thể bỏ qua thân request hay không. Khi cờ required, schema và binding của Spring thống nhất, Swagger UI có thể hiển thị biểu mẫu đúng và client có cơ sở đáng tin cậy để tích hợp API.

