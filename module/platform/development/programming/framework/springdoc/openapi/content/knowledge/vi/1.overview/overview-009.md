# Bản đồ thuật ngữ: operation, parameter, request body, schema và response

Khi dùng **springdoc-openapi**, ta thường bắt đầu từ một controller Spring Boot rồi xem tài liệu OpenAPI được sinh ra. Để đọc và tùy biến tài liệu đó chính xác, cần phân biệt năm khái niệm cốt lõi: **operation**, **parameter**, **request body**, **schema** và **response**.

Các khái niệm này mô tả những phần khác nhau của một lần gọi API:

- **Operation** xác định một hành động HTTP trên một đường dẫn, chẳng hạn lấy thông tin sách hoặc tạo sách mới.
- **Parameter** truyền dữ liệu qua đường dẫn, query string, header hoặc cookie.
- **Request body** mô tả phần nội dung gửi trong thân request, thường là JSON.
- **Schema** mô tả cấu trúc và ràng buộc của dữ liệu.
- **Response** mô tả kết quả API trả về theo từng mã trạng thái HTTP.

springdoc-openapi đọc các mapping, kiểu dữ liệu và annotation của Spring MVC cùng các annotation OpenAPI để tạo đặc tả. Swagger UI dùng đặc tả đó để hiển thị tài liệu và cho phép thử API. Vì vậy, hiểu đúng bản đồ thuật ngữ giúp ta biết nên đặt thông tin ở đâu và vì sao một phần tài liệu xuất hiện như vậy.

## 1. Từ controller đến một operation trong OpenAPI

Trong OpenAPI, một **path** là đường dẫn tương đối của tài nguyên, ví dụ **/api/books/{bookId}**. Một **path item** gom các operation có cùng đường dẫn. Mỗi cặp HTTP method và path xác định một operation.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{bookId}")
    public BookResponse getBook(@PathVariable long bookId) {
        // ...
    }

    @PostMapping
    public BookResponse createBook(@RequestBody CreateBookRequest request) {
        // ...
    }
}
~~~

Controller trên tạo ra hai operation:

| HTTP method và path | Ý nghĩa |
|---|---|
| **GET /api/books/{bookId}** | Lấy một cuốn sách theo ID |
| **POST /api/books** | Tạo một cuốn sách từ dữ liệu gửi lên |

Đây là hai operation riêng dù chúng cùng nằm trong một controller. Ngược lại, một path có thể chứa nhiều operation nếu ứng dụng hỗ trợ nhiều HTTP method trên cùng đường dẫn.

~~~mermaid
flowchart TD
    A["Spring MVC controller"] --> B["Mapping: HTTP method + path"]
    B --> C["OpenAPI path item"]
    C --> D["Operation: GET"]
    C --> E["Operation: POST"]
    D --> F["Parameters"]
    D --> G["Responses"]
    E --> H["Request body"]
    E --> I["Responses"]
    F --> J["Schema của từng giá trị"]
    H --> K["Schema của payload"]
    G --> L["Schema của dữ liệu trả về"]
    I --> L
~~~

Sơ đồ cho thấy operation là điểm tập hợp các mô tả đầu vào và đầu ra. Parameter, request body và response không phải những operation riêng; chúng là các phần nằm bên trong một operation.

## 2. Operation: một hành động HTTP có thể được gọi

**Operation** là mô tả đầy đủ cho một hành động được cung cấp bởi API. Nó gắn với một HTTP method trên một path, ví dụ **GET /api/books/{bookId}**. Một operation thường có:

- Tên hiển thị và phần giải thích: summary, description.
- Định danh operation: operationId.
- Nhãn phân nhóm: tags.
- Các parameter và request body đầu vào.
- Danh sách response theo mã trạng thái.
- Thông tin bảo mật, tính deprecated và các metadata khác nếu được khai báo.

Trong springdoc-openapi, annotation **@Operation** dùng để bổ sung hoặc ghi đè thông tin ở cấp operation:

~~~java
@Operation(
    summary = "Lấy thông tin sách",
    description = "Trả về thông tin của một cuốn sách theo ID.",
    operationId = "getBookById",
    tags = {"Books"}
)
@GetMapping("/{bookId}")
public BookResponse getBook(@PathVariable long bookId) {
    // ...
}
~~~

Các trường cần phân biệt:

| Trường | Vai trò |
|---|---|
| **summary** | Tiêu đề ngắn để người đọc nhận biết operation |
| **description** | Giải thích hành vi, điều kiện hoặc lưu ý khi gọi |
| **operationId** | Định danh duy nhất của operation trong tài liệu; thường được công cụ sinh client sử dụng để đặt tên hàm |
| **tags** | Nhóm operation trong tài liệu, thường được Swagger UI hiển thị thành các nhóm |

**operationId** không phải URL và cũng không bắt buộc trùng với tên method Java. Nếu cần ổn định tên hàm khi sinh SDK, hãy đặt operationId rõ ràng, duy nhất và hạn chế thay đổi tùy tiện. Nếu bỏ trống, springdoc có thể tự suy ra định danh; kết quả cụ thể phụ thuộc cách đặt tên và cấu hình.

Một endpoint thường được hiểu là địa chỉ mà client gọi. Trong tài liệu OpenAPI, cần nhìn cả method và path: **GET /api/books/{bookId}** và **DELETE /api/books/{bookId}** là hai operation khác nhau dù cùng path.

## 3. Parameter: dữ liệu nằm ngoài thân request

**Parameter** là một giá trị đầu vào được truyền qua một trong bốn vị trí:

| Vị trí OpenAPI | Ví dụ | Annotation Spring MVC thường gặp |
|---|---|---|
| **path** | **/books/42** | **@PathVariable** |
| **query** | **/books?page=2&size=20** | **@RequestParam** |
| **header** | **X-Request-Id: abc-123** | **@RequestHeader** |
| **cookie** | Cookie phiên đăng nhập | **@CookieValue** |

Mỗi parameter được xác định bởi tên và vị trí (**name** + **in**). Mô tả của nó có thể gồm kiểu dữ liệu, việc có bắt buộc hay không, nội dung giải thích, giá trị ví dụ và các ràng buộc.

~~~java
@Operation(summary = "Tìm sách theo trang")
@GetMapping
public List<BookResponse> searchBooks(
    @Parameter(description = "Số trang, bắt đầu từ 0", example = "0")
    @RequestParam(defaultValue = "0") int page,

    @Parameter(description = "Số phần tử trên một trang", example = "20")
    @RequestParam(defaultValue = "20") int size,

    @Parameter(description = "Mã ngôn ngữ tùy chọn", example = "vi")
    @RequestParam(required = false) String locale
) {
    // ...
}
~~~

Ở đây, **page**, **size** và **locale** là query parameter. Chúng không phải JSON body. springdoc thường có thể suy ra vị trí và kiểu dữ liệu từ annotation Spring MVC; **@Parameter** bổ sung mô tả, ví dụ hoặc chi tiết OpenAPI cần thiết.

### Quy tắc về required

- Parameter ở vị trí **path** luôn bắt buộc vì giá trị đó là một phần của đường dẫn.
- Query, header và cookie parameter có thể bắt buộc hoặc tùy chọn. Ví dụ, **@RequestParam(required = false)** thể hiện query parameter tùy chọn.
- Giá trị mặc định trong Spring (**defaultValue**) và thuộc tính **required** có liên quan đến cách client sử dụng API, nhưng không nên dùng chúng thay cho mô tả nghiệp vụ. Hãy kiểm tra tài liệu sinh ra để xác nhận required và schema đúng với hợp đồng mong muốn.

Không nên đưa một payload JSON lớn vào nhiều parameter chỉ để tránh request body. Parameter phù hợp với giá trị định danh, bộ lọc, phân trang hoặc metadata nhỏ. Dữ liệu có cấu trúc gửi trong thân request nên được mô tả bằng request body.

### Parameter object

Khi endpoint có nhiều bộ lọc query, có thể gom chúng vào một DTO hoặc object lọc. Với các kiểu object phù hợp, **@ParameterObject** của springdoc-openapi giúp bung các thuộc tính thành query parameter thay vì mô tả chúng như một object JSON trong request body.

~~~java
public class BookSearchCriteria {
    private String title;
    private String author;
    private Integer page;
    private Integer size;

    // getters và setters
}

@GetMapping("/search")
public List<BookResponse> search(
    @ParameterObject BookSearchCriteria criteria
) {
    // ...
}
~~~

Hãy dùng cách này khi các trường thực sự là query parameter. Nếu API nhận một object JSON trong thân request, hãy dùng request body.

## 4. Request body: dữ liệu gửi trong thân request

**Request body** mô tả nội dung nằm trong thân HTTP request. Với API REST, payload JSON thường được ánh xạ vào một DTO bằng **@RequestBody** của Spring MVC.

~~~java
public record CreateBookRequest(
    String title,
    String author,
    Integer publicationYear
) {}

@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse createBook(
    @Valid @RequestBody CreateBookRequest request
) {
    // ...
}
~~~

Ở ví dụ này:

- **@RequestBody** của Spring MVC yêu cầu Spring đọc nội dung request và chuyển đổi nó thành **CreateBookRequest**.
- **consumes = application/json** khai báo media type mà endpoint nhận.
- **CreateBookRequest** là kiểu dữ liệu của payload; cấu trúc của nó được biểu diễn bằng schema.
- **@Valid** kích hoạt kiểm tra các ràng buộc Bean Validation đã khai báo trên DTO, nếu ứng dụng có cấu hình validation tương ứng.

Request body trong OpenAPI có các thông tin chính:

| Thành phần | Ý nghĩa |
|---|---|
| **required** | Client có bắt buộc phải gửi thân request hay không |
| **content** | Các media type mà operation chấp nhận |
| **schema** | Cấu trúc dữ liệu cho từng media type |
| **example / examples** | Ví dụ payload để người dùng hiểu cách gửi |

Với payload JSON, phần content thường có key **application/json**. Một operation cũng có thể nhận nhiều định dạng, chẳng hạn JSON và multipart form, nếu controller và cấu hình ứng dụng hỗ trợ.

### Phân biệt hai annotation cùng tên RequestBody

Trong code Spring Boot có hai annotation dễ nhầm:

- **org.springframework.web.bind.annotation.RequestBody** thuộc Spring MVC, dùng để bind HTTP body vào tham số method.
- **io.swagger.v3.oas.annotations.parameters.RequestBody** thuộc OpenAPI, dùng để mô tả request body trong tài liệu.

Thông thường chỉ cần annotation Spring MVC để springdoc suy ra request body. Khi muốn khai báo chi tiết như mô tả, required, media type hoặc schema cụ thể, có thể bổ sung annotation OpenAPI. Nếu dùng cả hai trong cùng method, nên viết import rõ ràng hoặc dùng tên đầy đủ để tránh xung đột.

~~~java
@Operation(summary = "Tạo sách")
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public BookResponse createBook(
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Thông tin sách cần tạo",
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = CreateBookRequest.class)
        )
    )
    @org.springframework.web.bind.annotation.RequestBody
    @Valid CreateBookRequest request
) {
    // ...
}
~~~

Không nên khai báo request body cho một operation chỉ vì method Java có tham số. Hãy xác định tham số đó được truyền qua path, query, header, cookie hay thân request rồi chọn annotation phù hợp. Với **GET**, thiết kế thông thường truyền bộ lọc qua query parameter; request body trên **GET** không được nhiều client, proxy hoặc công cụ hỗ trợ nhất quán.

## 5. Schema: bản mô tả cấu trúc dữ liệu

**Schema** mô tả hình dạng và ràng buộc của một giá trị. Schema có thể đại diện cho:

- Giá trị đơn như string, integer, number hoặc boolean.
- Object gồm nhiều property.
- Array gồm các phần tử cùng kiểu.
- Giá trị có tập lựa chọn như enum.
- Các kiểu dữ liệu lồng nhau hoặc tham chiếu tới schema khác.

Schema có thể xuất hiện ở parameter, request body và response. Vì vậy, schema không đồng nghĩa với request body; request body là vị trí truyền dữ liệu, còn schema mô tả cấu trúc dữ liệu được truyền tại vị trí đó.

Ví dụ DTO:

~~~java
public record CreateBookRequest(
    @NotBlank
    @Schema(description = "Tên sách", example = "Spring in Action")
    String title,

    @NotBlank
    @Schema(description = "Tên tác giả", example = "Craig Walls")
    String author,

    @Min(1)
    @Schema(description = "Năm xuất bản", example = "2024", minimum = "1")
    Integer publicationYear
) {}
~~~

~~~java
@Schema(name = "BookResponse", description = "Thông tin sách trả về cho client")
public record BookResponse(
    @Schema(description = "Mã sách", example = "42")
    Long id,

    @Schema(description = "Tên sách", example = "Spring in Action")
    String title,

    @Schema(description = "Tên tác giả", example = "Craig Walls")
    String author
) {}
~~~

**@Schema** của swagger-annotations cho phép mô tả tên, ý nghĩa, ví dụ, kiểu hoặc cách biểu diễn của schema và property. Các ràng buộc Bean Validation như **@NotBlank**, **@Min** cũng có thể được phản ánh vào schema khi các thư viện và cấu hình liên quan được hỗ trợ. Sau khi sinh tài liệu, cần kiểm tra kết quả thực tế thay vì giả định mọi annotation đều được chuyển đổi giống nhau ở mọi phiên bản.

### Schema object và components/schemas

OpenAPI thường đặt các schema có thể tái sử dụng trong **components/schemas**. Một operation có thể tham chiếu tới schema này bằng **$ref**. Cách tổ chức đó giúp nhiều operation dùng chung một định nghĩa mà không phải lặp lại cấu trúc.

~~~yaml
components:
  schemas:
    BookResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
          example: 42
        title:
          type: string
          example: Spring in Action
        author:
          type: string
          example: Craig Walls
~~~

Khi controller trả về **BookResponse**, springdoc thường suy ra schema từ kiểu Java và có thể tạo tham chiếu tới component tương ứng. Tên component và cách tách inline schema phụ thuộc cấu hình, annotation và phiên bản thư viện.

### required khác nullable

Hai khái niệm này trả lời hai câu hỏi khác nhau:

- **required**: property có bắt buộc phải xuất hiện trong object hay không?
- **nullable**: nếu xuất hiện, property có được phép mang giá trị **null** hay không?

Một property có thể không bắt buộc nhưng nếu được gửi thì phải có giá trị; cũng có thể bắt buộc xuất hiện nhưng giá trị được phép là **null**, tùy phiên bản OpenAPI và schema được khai báo. Đừng suy ra nullable chỉ từ việc một field Java dùng kiểu tham chiếu. Hãy xem OpenAPI JSON/YAML được sinh ra và chọn cách biểu diễn phù hợp với phiên bản OpenAPI mà dự án sử dụng.

## 6. Response: kết quả được trả về theo mã trạng thái

**Response** mô tả những kết quả mà operation có thể trả về. Trong OpenAPI, mỗi response được gắn với một mã trạng thái HTTP hoặc key **default**. Một response có thể mô tả:

- Mã trạng thái, ví dụ **200**, **201**, **400**, **404**, **500**.
- Nội dung giải thích qua **description**.
- Dữ liệu trả về theo từng media type và schema.
- Header hoặc ví dụ nếu cần.

Ví dụ, thao tác tạo sách có thể trả **201 Created** cùng thông tin sách mới; nếu dữ liệu không hợp lệ, API có thể trả **400 Bad Request** cùng nội dung lỗi.

~~~java
@Operation(
    summary = "Tạo sách",
    description = "Tạo một cuốn sách mới và trả về thông tin vừa tạo."
)
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Tạo sách thành công",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = BookResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu đầu vào không hợp lệ",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<BookResponse> createBook(
    @Valid @RequestBody CreateBookRequest request
) {
    // ...
}
~~~

Trong ví dụ, **ApiError** là DTO lỗi do ứng dụng định nghĩa. Nếu dự án dùng **ProblemDetail** hoặc một cấu trúc lỗi khác, hãy mô tả đúng kiểu thực tế mà exception handler trả về.

springdoc có thể suy ra một phần response từ kiểu trả về của method, ví dụ **BookResponse** hoặc **ResponseEntity<BookResponse>**. Tuy nhiên, kiểu trả về Java không tự mô tả đầy đủ mọi trường hợp lỗi, mọi mã trạng thái hoặc mọi media type. Hãy khai báo **@ApiResponse** / **@ApiResponses** khi hợp đồng cần thể hiện rõ các trường hợp đó.

Các annotation thường dùng:

- **@ApiResponse**: mô tả một response cụ thể.
- **@ApiResponses**: nhóm nhiều response trên một operation.
- **@Content**: mô tả nội dung theo media type.
- **@Schema**: chỉ ra cấu trúc dữ liệu của nội dung.
- **@ExampleObject**: cung cấp ví dụ cụ thể cho nội dung.

Không nên chỉ mô tả response thành công. Client cần biết cả những kết quả lỗi có thể dự đoán được để xử lý đúng, chẳng hạn lỗi validation, không tìm thấy tài nguyên hoặc không đủ quyền.

## 7. Đọc bản OpenAPI sinh ra

Các khái niệm trên liên kết với nhau trong tài liệu. Ví dụ rút gọn dưới đây minh họa một operation đọc sách:

~~~yaml
paths:
  /api/books/{bookId}:
    get:
      operationId: getBookById
      summary: Lấy thông tin sách
      parameters:
        - name: bookId
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        "200":
          description: Lấy sách thành công
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
        "404":
          description: Không tìm thấy sách
components:
  schemas:
    BookResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        title:
          type: string
        author:
          type: string
~~~

Có thể đọc từ ngoài vào trong:

1. **paths** chứa đường dẫn của tài nguyên.
2. **get** là operation được cung cấp trên đường dẫn đó.
3. **parameters** mô tả giá trị **bookId** nằm trong path.
4. **responses** liệt kê các kết quả có thể trả về theo status code.
5. **content** chỉ ra media type; **schema** mô tả dữ liệu của response.
6. **$ref** trỏ tới định nghĩa dùng chung trong **components/schemas**.

Nếu operation nhận JSON body, phần **requestBody** sẽ nằm ngang cấp với **parameters** và **responses** bên trong operation. Trong **requestBody.content.application/json.schema**, ta lại gặp schema mô tả payload.

## 8. Bản đồ annotation thường gặp trong Spring Boot

| Mục tiêu | Spring MVC / Java | OpenAPI annotation bổ sung |
|---|---|---|
| Định nghĩa operation | **@GetMapping**, **@PostMapping**, **@PutMapping**, **@DeleteMapping**, **@RequestMapping** | **@Operation** |
| Path parameter | **@PathVariable** | **@Parameter** |
| Query parameter | **@RequestParam** | **@Parameter**, **@ParameterObject** |
| Header parameter | **@RequestHeader** | **@Parameter** |
| Cookie parameter | **@CookieValue** | **@Parameter** |
| Request body | **@RequestBody** | **@io.swagger.v3.oas.annotations.parameters.RequestBody** |
| Cấu trúc DTO và property | Kiểu Java, record, Bean Validation | **@Schema**, **@ArraySchema** |
| Response | Kiểu trả về, **ResponseEntity<T>** | **@ApiResponse**, **@ApiResponses**, **@Content**, **@ExampleObject** |

Annotation Spring MVC thể hiện hành vi thực thi của controller. Annotation OpenAPI bổ sung phần mô tả hợp đồng API. springdoc kết hợp hai nguồn này để tạo tài liệu. Khi có nhiều annotation cùng mô tả một thông tin, cần kiểm tra kết quả sinh ra để chắc chắn không có khai báo mâu thuẫn hoặc ghi đè ngoài ý muốn.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Một controller là một operation | Một controller có thể chứa nhiều operation; mỗi HTTP method trên một path là một operation riêng |
| Parameter và request body giống nhau | Parameter nằm ở path, query, header hoặc cookie; request body nằm trong thân HTTP |
| Schema chính là DTO Java | DTO là kiểu trong mã nguồn; schema là mô tả hợp đồng được xuất ra và có thể được tùy biến |
| Có kiểu trả về là đã mô tả đủ response | Kiểu trả về giúp suy ra response thành công, nhưng không nhất thiết mô tả hết mã lỗi, header và media type |
| **required** đồng nghĩa với **nullable: false** | required nói về việc property có phải xuất hiện; nullable nói về việc giá trị có thể là null |
| **operationId** là URL của endpoint | operationId là định danh operation, thường phục vụ sinh client và tham chiếu |

Một nguyên tắc hữu ích khi thiết kế tài liệu: hãy hỏi dữ liệu đang ở đâu trước, rồi mới chọn khái niệm OpenAPI. Nếu nó xác định hành động thì thuộc operation; nếu nó được truyền qua URL/header/cookie thì là parameter; nếu nó nằm trong thân HTTP thì là request body; nếu cần mô tả hình dạng dữ liệu thì dùng schema; nếu đó là kết quả API trả về thì mô tả bằng response.

## 10. Kiểm tra hợp đồng sau khi sinh tài liệu

Sau khi thêm hoặc sửa annotation, hãy kiểm tra đặc tả OpenAPI được springdoc tạo ra, thường tại endpoint **/v3/api-docs**; nếu dự án bật đầu ra YAML, có thể kiểm tra **/v3/api-docs.yaml**. Swagger UI thường được cấu hình tại **/swagger-ui/index.html** hoặc đường dẫn tương ứng của dự án.

Với từng operation quan trọng, hãy xác minh:

- Method và path có đúng với mapping của controller không?
- Parameter có đúng vị trí, kiểu dữ liệu và trạng thái required không?
- Request body có đúng media type, schema và required không?
- Schema có đủ property, kiểu, enum, ví dụ và ràng buộc cần thiết không?
- Response có đủ status code, mô tả, media type và schema cho thành công lẫn lỗi không?
- operationId có duy nhất và ổn định không?

Swagger UI giúp con người đọc và thử API, còn file OpenAPI JSON/YAML là hợp đồng có thể được kiểm tra tự động, dùng để sinh client hoặc tích hợp với công cụ khác. Vì thế, đừng chỉ nhìn giao diện Swagger UI: hãy kiểm tra trực tiếp đặc tả được sinh ra, đặc biệt khi thay đổi DTO, generic response, exception handler hoặc annotation.

## Kết luận

Năm khái niệm tạo thành một cấu trúc thống nhất: **operation** mô tả hành động HTTP; **parameter** và **request body** mô tả hai cách truyền đầu vào; **schema** mô tả cấu trúc dữ liệu; **response** mô tả kết quả theo mã trạng thái. springdoc-openapi kết nối cấu trúc controller Spring Boot với các khái niệm này để sinh tài liệu OpenAPI và cung cấp dữ liệu cho Swagger UI. Khi phân loại đúng từng thông tin và kiểm tra đặc tả đầu ra, tài liệu API sẽ phản ánh hợp đồng mà client thực sự cần sử dụng.
