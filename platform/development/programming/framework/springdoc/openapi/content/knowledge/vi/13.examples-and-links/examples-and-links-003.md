# Phân biệt example, examples và default theo vị trí khai báo

Trong OpenAPI, ví dụ và giá trị mặc định đều giúp người tích hợp hiểu cách gửi dữ liệu, nhưng chúng có ý nghĩa khác nhau. **example** minh họa một giá trị; **examples** cung cấp nhiều mẫu có tên để người đọc chọn theo tình huống; **default** mô tả giá trị mặc định của một schema khi không có giá trị cụ thể. Với Spring MVC, các thuộc tính **defaultValue** trên annotation binding còn có thể thay đổi hành vi xử lý request thật.

Trong springdoc-openapi, vị trí khai báo quyết định metadata được sinh ra ở đâu: **@Schema** mô tả model hoặc kiểu dữ liệu, **@Parameter** mô tả path/query/header/cookie parameter, còn **@Content** mô tả dữ liệu theo media type của request body hoặc response. Annotation **@ExampleObject** được dùng để tạo các ví dụ có tên bên trong Parameter hoặc Content.

Bài này phân biệt từng vị trí, chỉ ra annotation tương ứng và cách xác minh JSON đầu ra để tránh nhầm ví dụ tài liệu với hành vi mặc định của server.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Có tự thay đổi request runtime không? |
|---|---|---|
| **example** | Một giá trị minh họa cho schema, parameter hoặc nội dung media type | Không |
| **examples** | Một tập hợp ví dụ có tên, mỗi ví dụ có thể có summary, description và value riêng | Không |
| **default** | Giá trị mặc định được mô tả cho schema khi không có giá trị cụ thể | Không tự động |
| **Spring defaultValue** | Giá trị fallback mà Spring MVC dùng khi request thiếu hoặc có giá trị rỗng ở vị trí hỗ trợ | Có |

Ví dụ một query parameter phân trang:

~~~java
@RequestParam(name = "size", defaultValue = "20")
int pageSize
~~~

Trong ví dụ này, Spring MVC dùng 20 khi client không gửi size hoặc gửi giá trị rỗng. Đây là hành vi runtime. Nếu tài liệu có:

~~~java
@Schema(defaultValue = "20", example = "10")
~~~

thì **defaultValue** và **example** chỉ mô tả hai khía cạnh trong schema: giá trị mặc định được công bố là 20, còn 10 là một giá trị minh họa. **@Schema** không khiến Spring tự thay giá trị đầu vào thành 20.

Một ví dụ đơn lẻ thường đủ khi mọi người dùng cùng một dạng dữ liệu. Dùng nhiều examples khi muốn minh họa các tình huống khác nhau, chẳng hạn sách giấy và sách điện tử, hoặc request hợp lệ và request có tùy chọn khác nhau.

## 2. example ở cấp schema: mô tả một property hoặc model

Annotation **@Schema(example = "...")** phù hợp khi một property hoặc kiểu dữ liệu có một ví dụ tiêu biểu có thể tái sử dụng ở nhiều operation.

Ví dụ ở cấp property:

~~~java
public record CreateBookRequest(
    @Schema(
        description = "Tên sách",
        example = "Spring in Action"
    )
    String title,

    @Schema(
        description = "Mã ISBN-13",
        example = "9781617297571",
        pattern = "^[0-9]{13}$"
    )
    String isbn,

    @Schema(
        description = "Định dạng xuất bản",
        example = "PRINT",
        allowableValues = {"PRINT", "EBOOK"}
    )
    String format
) {}
~~~

Schema đầu ra có thể chứa:

~~~yaml
CreateBookRequest:
  type: object
  properties:
    title:
      type: string
      description: Tên sách
      example: Spring in Action
    isbn:
      type: string
      description: Mã ISBN-13
      pattern: ^[0-9]{13}$
      example: "9781617297571"
    format:
      type: string
      description: Định dạng xuất bản
      enum: [PRINT, EBOOK]
      example: PRINT
~~~

Ví dụ ở cấp class dùng để minh họa một object hoàn chỉnh:

~~~java
@Schema(
    name = "BookResponse",
    description = "Thông tin sách trả về cho client",
    example = """
        {
          "id": "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
          "title": "Spring in Action",
          "published": true
        }
        """
)
public record BookResponse(
    UUID id,
    String title,
    boolean published
) {}
~~~

**Phạm vi:** ví dụ gắn với schema và có thể được dùng ở nhiều nơi tham chiếu schema đó. Nếu một operation cần ví dụ khác với ví dụ chung của DTO, hãy khai báo ví dụ ở cấp parameter hoặc media type của operation đó.

**@Schema(example = ...)** không:

- Tạo giá trị mặc định cho constructor hoặc field Java.
- Tự điền dữ liệu khi Jackson deserialize JSON thiếu property.
- Kiểm tra giá trị có đúng pattern hoặc giới hạn hay không.
- Tạo thêm nhiều lựa chọn có tên cho Swagger UI.

Để mô tả nhiều tình huống tại một request body hoặc response, dùng **@ExampleObject** ở cấp **@Content**.

## 3. default ở cấp schema: giá trị mặc định được công bố

OpenAPI Schema Object có thể mô tả giá trị mặc định bằng keyword **default**. Trong swagger-annotations, có thể khai báo qua **@Schema(defaultValue = "...")**:

~~~java
public record SearchOptions(
    @Schema(
        description = "Ngôn ngữ hiển thị",
        defaultValue = "vi",
        example = "en"
    )
    String locale,

    @Schema(
        description = "Số lượng kết quả tối đa",
        defaultValue = "20",
        example = "10",
        minimum = "1",
        maximum = "100"
    )
    Integer limit
) {}
~~~

Ở đây:

- **defaultValue = "vi"** công bố default của locale trong schema.
- **example = "en"** minh họa một giá trị hợp lệ khác.
- **defaultValue = "20"** công bố default của limit.
- **example = "10"** là một lựa chọn minh họa.

Default trong Schema Object là metadata của hợp đồng. Theo ý nghĩa của JSON Schema/OpenAPI, nó không phải chỉ thị buộc server hoặc client tự gán giá trị khi property bị bỏ qua. Ứng dụng cần triển khai hành vi fallback tương ứng nếu muốn thực sự áp dụng giá trị đó.

Ví dụ output ở cấp schema:

~~~yaml
type: integer
default: 20
example: 10
minimum: 1
maximum: 100
~~~

Client đọc được default là 20 và một giá trị minh họa là 10. Schema không buộc client gửi 20 hoặc server tự điền 20 vào request body.

### Default trên property không giống default của query parameter

Một property trong request body và một query parameter có thể cùng mang tên limit nhưng có luồng xử lý khác nhau:

- Với JSON body, giá trị mặc định phải được thực hiện bởi constructor, logic ứng dụng, Jackson configuration hoặc cơ chế phù hợp khác.
- Với query parameter, Spring MVC có thuộc tính **defaultValue** trên **@RequestParam** để áp dụng fallback trước khi gọi controller.

Không nên chỉ đặt **@Schema(defaultValue = "20")** rồi kỳ vọng Spring tự dùng 20 khi client bỏ property hoặc query parameter.

## 4. @Parameter.example và @Parameter.examples cho path, query, header, cookie

Annotation **@Parameter** mô tả một HTTP parameter. Nó có thuộc tính **example** cho một giá trị minh họa và **examples** cho nhiều Example Object có tên.

Một ví dụ query parameter:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(
        description = "Trạng thái xuất bản",
        example = "PUBLISHED"
    )
    @RequestParam(name = "status", required = false)
    BookStatus status
) {
    // ...
    return List.of();
}
~~~

Khi cần nhiều lựa chọn:

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(
        description = "Trạng thái cần lọc",
        examples = {
            @ExampleObject(
                name = "published",
                summary = "Sách đã xuất bản",
                value = "PUBLISHED"
            ),
            @ExampleObject(
                name = "draft",
                summary = "Bản thảo",
                value = "DRAFT"
            ),
            @ExampleObject(
                name = "archived",
                summary = "Sách đã lưu trữ",
                value = "ARCHIVED"
            )
        }
    )
    @RequestParam(name = "status", required = false)
    BookStatus status
) {
    // ...
    return List.of();
}
~~~

Các ví dụ có tên giúp người đọc hiểu từng trường hợp. Với parameter dạng scalar, value thường là giá trị văn bản mà client gửi trong URL hoặc header. Hãy chọn giá trị phù hợp với schema và kiểu binding thực tế.

### Ví dụ cho path parameter

~~~java
@GetMapping("/{bookId}")
public BookResponse getBook(
    @Parameter(
        description = "UUID của sách",
        example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001"
    )
    @PathVariable("bookId") UUID bookId
) {
    // ...
    return null;
}
~~~

Path parameter luôn required theo OpenAPI. Example chỉ minh họa một UUID hợp lệ; nó không cung cấp giá trị mặc định khi client bỏ segment trong URL.

### Ví dụ cho header parameter

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
    @Parameter(
        description = "Ngôn ngữ phản hồi mong muốn",
        examples = {
            @ExampleObject(name = "vietnamese", value = "vi"),
            @ExampleObject(name = "english", value = "en")
        }
    )
    @RequestHeader(name = "X-Locale", required = false)
    String locale
) {
    // ...
    return List.of();
}
~~~

### Ví dụ cho cookie parameter

~~~java
@GetMapping("/preferences")
public PreferenceResponse preferences(
    @Parameter(
        description = "Cookie lưu ngôn ngữ giao diện",
        example = "vi"
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    // ...
    return null;
}
~~~

Với parameter có cả schema và ví dụ, hãy bảo đảm value khớp schema. Ví dụ UUID cần đúng định dạng; integer cần là số; enum cần dùng đúng một giá trị được phép.

## 5. @ExampleObject: cấu trúc của một ví dụ có tên

**@ExampleObject** là annotation mô tả một ví dụ riêng. Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| **name** | Khóa định danh ví dụ trong map examples |
| **summary** | Tiêu đề ngắn để người đọc chọn ví dụ |
| **description** | Giải thích tình huống hoặc cách dùng |
| **value** | Nội dung mẫu được khai báo trực tiếp |
| **externalValue** | URL trỏ tới nội dung ví dụ nằm bên ngoài tài liệu |
| **ref** | Tham chiếu tới một Example Object được định nghĩa ở nơi khác |

Ví dụ:

~~~java
@ExampleObject(
    name = "minimal",
    summary = "Request tối thiểu",
    description = "Chỉ cung cấp các trường bắt buộc",
    value = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\"}"
)
~~~

**name** nên duy nhất trong tập examples của cùng parameter hoặc media type. **value** phải có định dạng phù hợp với vị trí khai báo. Nếu content type là application/json, value cần là JSON hợp lệ; nếu là text/plain, value có thể là văn bản.

Có thể dùng **externalValue** khi ví dụ lớn hoặc được quản lý thành file riêng. Khi đó, URL phải truy cập được với người đọc tài liệu. Không khai báo value và externalValue như hai nội dung thay thế cùng lúc cho một Example Object.

Không đưa access token, session cookie, mật khẩu, dữ liệu cá nhân hoặc mã nội bộ thật vào ví dụ. Dùng dữ liệu giả lập nhưng vẫn đúng định dạng và ràng buộc của schema.

## 6. Phân biệt example và examples tại cấp Parameter Object

OpenAPI Parameter Object hỗ trợ hai thuộc tính:

- **example**: một giá trị đơn lẻ.
- **examples**: map nhiều ví dụ có tên.

Hai thuộc tính này loại trừ lẫn nhau trong cùng Parameter Object. Trong annotation, chọn một trong hai cách:

~~~java
@Parameter(example = "PUBLISHED")
~~~

hoặc:

~~~java
@Parameter(
    examples = {
        @ExampleObject(name = "published", value = "PUBLISHED"),
        @ExampleObject(name = "draft", value = "DRAFT")
    }
)
~~~

Không gán đồng thời example và examples cho cùng parameter. Nếu cần nhiều lựa chọn, dùng examples và đặt tên rõ ràng cho từng trường hợp.

Parameter Object có thể dùng schema để mô tả kiểu dữ liệu:

~~~java
@Parameter(
    name = "page",
    description = "Số trang, bắt đầu từ 0",
    examples = {
        @ExampleObject(name = "firstPage", value = "0"),
        @ExampleObject(name = "thirdPage", value = "2")
    },
    schema = @Schema(
        type = "integer",
        format = "int32",
        minimum = "0"
    )
)
@RequestParam(name = "page", defaultValue = "0")
int page
~~~

Trong ví dụ, schema xác định page là số nguyên không âm; examples đưa ra hai giá trị cụ thể. Spring MVC defaultValue vẫn quyết định giá trị server dùng khi query parameter vắng mặt hoặc rỗng.

Trong OpenAPI JSON/YAML, danh sách này nằm trong thuộc tính examples của Parameter Object. Mỗi khóa là tên ví dụ, còn value là Example Object:

~~~yaml
parameters:
  - name: page
    in: query
    schema:
      type: integer
      format: int32
      minimum: 0
    examples:
      firstPage:
        summary: Trang đầu tiên
        value: 0
      thirdPage:
        summary: Trang thứ ba
        value: 2
~~~

## 7. example và examples tại cấp @Content cho request body

Request body có thể có nhiều ví dụ theo media type. Annotation OpenAPI **@Content** hỗ trợ **example** cho một nội dung mẫu và **examples** cho nhiều Example Object có tên.

Ví dụ một request body với một mẫu:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Thông tin sách cần tạo",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateBookRequest.class),
        example = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\"}"
    )
)
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
    @org.springframework.web.bind.annotation.RequestBody
    @Valid CreateBookRequest request
) {
    // ...
    return null;
}
~~~

Khi cần nhiều tình huống, thay example bằng examples:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Thông tin sách cần tạo",
    required = true,
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = CreateBookRequest.class),
        examples = {
            @ExampleObject(
                name = "printedBook",
                summary = "Sách in",
                value = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\",\"format\":\"PRINT\"}"
            ),
            @ExampleObject(
                name = "ebook",
                summary = "Sách điện tử",
                value = "{\"title\":\"Cloud Native Java\",\"isbn\":\"9781617294129\",\"format\":\"EBOOK\"}"
            )
        }
    )
)
~~~

Đây là OpenAPI RequestBody annotation, khác với **@RequestBody** của Spring MVC. Annotation Spring MVC bind JSON vào method parameter; annotation OpenAPI bổ sung mô tả, schema và ví dụ cho tài liệu.

Khi được xuất ra OpenAPI, examples nằm dưới media type:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateBookRequest"
      examples:
        printedBook:
          summary: Sách in
          value:
            title: Spring in Action
            isbn: "9781617297571"
            format: PRINT
        ebook:
          summary: Sách điện tử
          value:
            title: Cloud Native Java
            isbn: "9781617294129"
            format: EBOOK
~~~

Nếu một request body hỗ trợ nhiều media type, mỗi @Content có thể có schema và ví dụ phù hợp riêng. Ví dụ JSON và XML không nên dùng chung một value nếu cấu trúc hoặc cú pháp khác nhau.

## 8. example và examples tại cấp @Content cho response

Response có thể có một ví dụ đại diện:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin sách",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookResponse.class),
        example = "{\"id\":\"8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001\",\"title\":\"Spring in Action\",\"published\":true}"
    )
)
~~~

Hoặc nhiều ví dụ có tên:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Kết quả tìm kiếm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookSearchResponse.class),
        examples = {
            @ExampleObject(
                name = "oneResult",
                summary = "Tìm thấy một sách",
                value = "{\"items\":[{\"id\":\"8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001\",\"title\":\"Spring in Action\"}],\"total\":1}"
            ),
            @ExampleObject(
                name = "noResult",
                summary = "Không có kết quả",
                value = "{\"items\":[],\"total\":0}"
            )
        }
    )
)
~~~

Ví dụ response giúp người đọc hiểu payload server trả về. Chúng không tạo response runtime, không thay đổi status code và không thay thế implementation của controller.

## 9. @Schema.example và @Content.examples có phạm vi khác nhau

Một DTO có thể được dùng ở nhiều operation. Đặt **@Schema(example = ...)** trên DTO tạo ví dụ gắn với model. Khi một operation cần ví dụ theo nghiệp vụ riêng, đặt **@ExampleObject** trong **@Content** của request body hoặc response.

~~~java
@Schema(
    name = "CreateBookRequest",
    example = "{\"title\":\"Spring in Action\",\"isbn\":\"9781617297571\"}"
)
public record CreateBookRequest(
    String title,
    String isbn,
    String format
) {}
~~~

Operation nhập sách từ nhà cung cấp có thể cần một ví dụ riêng:

~~~java
@PostMapping("/api/books/import")
public BookResponse importBook(
    @org.springframework.web.bind.annotation.RequestBody
    CreateBookRequest request
) {
    // ...
    return null;
}
~~~

Ở operation này, **@Content(examples = ...)** có thể cung cấp các ví dụ nhập từ nhà cung cấp. Như vậy:

- **@Schema.example** mô tả mẫu đại diện của model.
- **@Content.examples** mô tả các payload cụ thể cho media type của operation.
- **@Parameter.examples** mô tả các giá trị khác nhau của một HTTP parameter.

Chúng không phải ba cách viết thay thế cho cùng một mục đích; mỗi vị trí có phạm vi và hình dạng OpenAPI riêng.

## 10. Default runtime của Spring MVC

Spring MVC cung cấp **defaultValue** trên một số annotation binding. Các giá trị này ảnh hưởng đến việc bind request:

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
    @RequestParam(name = "page", defaultValue = "0")
    int page,

    @RequestParam(name = "size", defaultValue = "20")
    int size,

    @RequestHeader(name = "X-Locale", defaultValue = "vi")
    String locale,

    @CookieValue(name = "currency", defaultValue = "VND")
    String currency
) {
    // ...
    return List.of();
}
~~~

Trong Spring MVC, defaultValue của @RequestParam được áp dụng khi parameter không có mặt hoặc giá trị là chuỗi rỗng; khi đặt defaultValue, required mặc định trở thành false. @RequestHeader và @CookieValue cũng có cơ chế fallback tương tự khi giá trị không được cung cấp hoặc rỗng.

Điều này khác với ví dụ tài liệu:

~~~java
@Parameter(example = "2")
@RequestParam(name = "page", defaultValue = "0")
int page
~~~

Client thấy ví dụ 2 trong tài liệu, nhưng server dùng 0 khi client không gửi page. Ví dụ không ghi đè default runtime.

springdoc có thể suy ra defaultValue từ annotation Spring MVC và đưa vào schema của parameter tùy loại binding và phiên bản. Nếu cần bảo đảm hợp đồng hiển thị chính xác, hãy kiểm tra /v3/api-docs thay vì chỉ nhìn source code.

### Request body không có defaultValue như query parameter

Spring MVC **@RequestBody** không có thuộc tính defaultValue tương tự @RequestParam. Nếu body vắng mặt, hành vi phụ thuộc required và cấu hình binding; nếu body có property bị thiếu, giá trị sau deserialize phụ thuộc DTO, constructor, Jackson và logic ứng dụng.

Muốn có fallback cho property JSON, cần triển khai rõ ở DTO hoặc tầng ứng dụng. **@Schema(defaultValue = "...")** chỉ mô tả default trong tài liệu, không tự điền property khi deserialize.

Path variable cũng không có defaultValue thông thường. Một path parameter bắt buộc phải có mặt trong URL theo path template và OpenAPI.

## 11. Vị trí khai báo và kết quả OpenAPI

Bảng sau giúp chọn đúng annotation:

| Vị trí dữ liệu | Một ví dụ | Nhiều ví dụ | Default tài liệu | Default runtime |
|---|---|---|---|---|
| DTO class/property | @Schema(example = "...") | Theo phiên bản OpenAPI/JSON Schema; named examples thường đặt ở cấp media type | @Schema(defaultValue = "...") | Constructor, Jackson hoặc logic ứng dụng |
| Path/query/header/cookie parameter | @Parameter(example = "...") | @Parameter(examples = @ExampleObject(...)) | @Parameter(schema = @Schema(defaultValue = "...")) | defaultValue của annotation Spring MVC ở vị trí hỗ trợ |
| Request body media type | @Content(example = "...") | @Content(examples = @ExampleObject(...)) | Schema của body có thể khai báo default cho property | Logic DTO/deserialize/ứng dụng |
| Response media type | @Content(example = "...") | @Content(examples = @ExampleObject(...)) | Schema mô tả default nếu có ý nghĩa | Controller/service quyết định payload thật |

Các điểm cần ghi nhớ:

- **Parameter Object** và **Media Type Object** có thể có example hoặc examples; hai trường này loại trừ nhau tại cùng vị trí.
- **@ExampleObject** tạo từng ví dụ có tên; name phải duy nhất trong tập examples tương ứng.
- **@Schema.defaultValue** tạo metadata schema; Spring MVC **defaultValue** tạo hành vi binding.
- **@Schema.example** gắn ví dụ với kiểu dữ liệu; **@Parameter.example** gắn ví dụ với một HTTP parameter; **@Content.examples** gắn nhiều payload theo media type.
- Nếu một annotation không có thuộc tính đúng với mục đích, đừng cố dùng annotation ở tầng khác để thay thế. Hãy chọn đúng vị trí hoặc dùng customizer khi thật sự cần.

## 12. Khác biệt giữa OpenAPI 3.0 và 3.1

Vị trí khai báo example cũng cần được hiểu theo phiên bản đặc tả:

- Trong OpenAPI 3.0, Schema Object có thuộc tính example đơn lẻ; Parameter Object và Media Type Object hỗ trợ example hoặc examples.
- Trong OpenAPI 3.1, Schema Object dựa trên JSON Schema. JSON Schema có keyword **examples** dạng mảng; thuộc tính **example** cũ trong Schema Object được đánh dấu deprecated trong đặc tả OpenAPI 3.1.
- Parameter Object và Media Type Object vẫn có cơ chế examples với các Example Object có tên. Đây không giống keyword examples dạng mảng trong JSON Schema.

swagger-annotations và springdoc có thể giữ annotation tương thích qua nhiều phiên bản. Vì vậy, **@Schema(example = ...)** có thể vẫn được hỗ trợ trong mã Java nhưng output phụ thuộc phiên bản OpenAPI mà ứng dụng xuất ra. Khi dự án chuyển từ OpenAPI 3.0 sang 3.1, hãy kiểm tra schema JSON/YAML và cách công cụ client xử lý example.

Không nhầm:

- **Schema examples** của JSON Schema là các giá trị minh họa ở cấp schema.
- **Parameter.examples** là map các Example Object cho một HTTP parameter.
- **Content.examples** là map các Example Object cho một media type.

Các cấu trúc này có tên giống nhau nhưng vị trí và cấu trúc dữ liệu khác nhau.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đặt @Schema(example) nhưng Swagger UI không hiện nhiều lựa chọn | Schema example là một mẫu đơn, không phải danh sách named examples | Dùng @ExampleObject trong @Content.examples hoặc @Parameter.examples |
| Đặt examples ở DTO nhưng muốn ví dụ riêng theo operation | Ví dụ được gắn ở cấp model, không phải media type cụ thể | Khai báo examples ở @Content của operation |
| Đặt @Parameter(example) nhưng server không dùng giá trị đó khi bỏ query | example chỉ là metadata | Dùng @RequestParam(defaultValue = "...") nếu cần runtime fallback |
| Đặt @Schema(defaultValue) nhưng DTO vẫn nhận null | Schema default không tự điền giá trị Java | Thực hiện default ở constructor, Jackson hoặc logic ứng dụng |
| Khai báo cả example và examples ở cùng Parameter/Content | Hai trường loại trừ nhau theo OpenAPI | Chọn một trường phù hợp |
| Example JSON không hợp lệ | value không khớp media type hoặc schema | Kiểm tra cú pháp và kiểu dữ liệu mẫu |
| Example enum không được chấp nhận | Giá trị không nằm trong enum/allowableValues | Dùng đúng giá trị trên wire |
| Nhiều ExampleObject trùng name | Tên map examples không duy nhất | Đặt tên duy nhất, dễ hiểu |
| Ví dụ ở schema không phù hợp DTO đã thay đổi | Mẫu không được cập nhật cùng model | Đồng bộ ví dụ và kiểm tra lại payload |
| Default hiển thị khác runtime | @Schema.defaultValue và Spring defaultValue khác nhau | Đồng bộ metadata và test binding |
| OpenAPI 3.1 hiển thị schema example khác dự kiến | Khác biệt giữa Schema Object và JSON Schema examples | Kiểm tra version, annotation output và công cụ hiển thị |

## 14. Kiểm tra ví dụ và default trong /v3/api-docs

Sau khi ứng dụng khởi động, mở **/v3/api-docs** hoặc endpoint YAML đã cấu hình. Kiểm tra đúng vị trí:

1. **components.schemas**: tìm example/default của class hoặc property.
2. **paths → operation → parameters**: kiểm tra example hoặc examples của path/query/header/cookie.
3. **requestBody → content → application/json**: kiểm tra example hoặc examples của request payload.
4. **responses → status → content**: kiểm tra ví dụ response cho từng status code và media type.
5. **schema**: kiểm tra default của property và kiểu dữ liệu đi kèm.

Có thể dùng jq để kiểm tra nhanh:

~~~bash
# Schema của DTO
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.CreateBookRequest'

# Các ví dụ của query parameter
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books/search"].get.parameters'

# Các ví dụ của request body
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books"].post.requestBody.content["application/json"]'

# Các ví dụ của response
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books"].post.responses["201"].content["application/json"]'
~~~

Nếu Swagger UI hiển thị khác mong đợi, trước hết kiểm tra JSON được sinh ra. Swagger UI chỉ trình bày tài liệu OpenAPI; cách render ví dụ còn phụ thuộc phiên bản Swagger UI và cấu trúc đặc tả.

## 15. Kiểm thử runtime default riêng với ví dụ tài liệu

Với query parameter có default, hãy gửi request theo ít nhất ba trường hợp:

~~~http
GET /api/books
GET /api/books?page=2
GET /api/books?page=
~~~

Xác nhận:

- Không có page: controller nhận giá trị default.
- page=2: controller nhận giá trị client gửi.
- page rỗng: Spring áp dụng defaultValue theo quy tắc của @RequestParam.

Với request body, kiểm tra property bị thiếu, property có giá trị null và property có giá trị cụ thể. Không suy ra kết quả từ @Schema.defaultValue; hãy kiểm tra object sau deserialize và response runtime.

Ví dụ tài liệu cần được kiểm tra riêng:

- Example phải hợp lệ với schema.
- Examples phải có tên và mô tả đủ phân biệt.
- Default công bố phải trùng với hành vi runtime nếu tài liệu nói đó là default của endpoint.
- Response example phải khớp JSON thật mà controller/service trả về.

## 16. Quy tắc chọn example, examples và default

- Dùng **@Schema(example)** cho một giá trị hoặc object tiêu biểu của DTO có thể tái sử dụng.
- Dùng **@Parameter(example)** cho một giá trị mẫu của path, query, header hoặc cookie.
- Dùng **@Content(example)** cho một payload đơn lẻ của request body hoặc response media type.
- Dùng **@ExampleObject** trong **@Parameter(examples)** hoặc **@Content(examples)** khi cần nhiều mẫu có tên, có thể chọn theo tình huống.
- Dùng **@Schema(defaultValue)** để công bố default ở cấp schema.
- Dùng **@RequestParam(defaultValue)**, **@RequestHeader(defaultValue)** hoặc **@CookieValue(defaultValue)** khi cần Spring MVC áp dụng fallback thật.
- Với request body, triển khai default trong DTO hoặc logic ứng dụng; annotation OpenAPI không tự gán giá trị.
- Giữ ví dụ khớp schema, enum, format, media type và payload runtime.
- Khi dùng OpenAPI 3.1, phân biệt keyword examples của JSON Schema với examples map của Parameter/Media Type Object.

## Kết luận

**example** là một mẫu minh họa; **examples** là tập hợp các mẫu có tên; **default** là giá trị mặc định được mô tả trong schema. **@Schema**, **@Parameter** và **@Content** đặt metadata ở những vị trí khác nhau, còn **@ExampleObject** định nghĩa từng mẫu có tên. Spring MVC **defaultValue** mới là cơ chế fallback runtime cho các parameter binding hỗ trợ nó. Hãy chọn annotation theo vị trí dữ liệu, giữ default tài liệu đồng bộ với hành vi server và kiểm tra /v3/api-docs cùng request thực tế trước khi công bố hợp đồng API.
