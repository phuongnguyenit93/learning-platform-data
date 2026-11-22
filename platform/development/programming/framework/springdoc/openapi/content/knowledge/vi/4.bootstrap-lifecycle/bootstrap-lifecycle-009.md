# Chuỗi xử lý từ handler đến operation và schema

Khi một request đi vào ứng dụng Spring Boot, Spring MVC tìm handler phù hợp, bind dữ liệu request vào tham số method, gọi controller và chuyển kết quả thành HTTP response. springdoc-openapi đọc cấu trúc controller và các metadata liên quan để mô tả cùng endpoint đó trong đặc tả OpenAPI. Vì vậy, một endpoint có hai chuỗi xử lý liên quan nhưng phục vụ hai mục tiêu khác nhau: **chuỗi thực thi request** và **chuỗi xây dựng tài liệu API**.

Hiểu mối liên hệ giữa handler, operation và schema giúp ta trả lời những câu hỏi thường gặp: vì sao một method xuất hiện hoặc không xuất hiện trong Swagger UI, vì sao tham số được sinh thành query parameter hay request body, vì sao DTO trở thành một schema dùng chung, và nên tùy biến ở bước nào khi tài liệu chưa phản ánh đúng hợp đồng.

## 1. Phân biệt handler, operation và schema

Ba khái niệm này nằm ở ba lớp khác nhau:

| Khái niệm | Thuộc lớp nào | Vai trò |
|---|---|---|
| **Handler / HandlerMethod** | Spring MVC lúc chạy ứng dụng | Thành phần nhận và xử lý một request phù hợp với mapping |
| **Operation** | OpenAPI | Mô tả một hành động HTTP trên một path, gồm đầu vào và kết quả |
| **Schema** | OpenAPI | Mô tả cấu trúc, kiểu và ràng buộc của dữ liệu được truyền hoặc trả về |

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{bookId}")
    public BookResponse getBook(
        @PathVariable UUID bookId
    ) {
        // ...
        return null;
    }
}
~~~

Spring MVC xem method getBook là một handler có mapping GET trên path /api/books/{bookId}. Trong OpenAPI, springdoc mô tả mapping đó thành operation GET thuộc path item /api/books/{bookId}. Tham số bookId trở thành path parameter; kiểu UUID được biểu diễn bằng schema dạng string với format uuid. Kiểu trả về BookResponse được phân tích để tạo schema cho response.

Một handler không phải là operation. Một handler method có thể được ánh xạ tới một hoặc nhiều điều kiện mapping, và một path item trong OpenAPI có thể chứa nhiều operation cho các HTTP method khác nhau. Schema cũng không phải DTO Java: DTO là kiểu dữ liệu trong mã nguồn, còn schema là mô tả hợp đồng được xuất ra từ kiểu đó cùng các annotation và quy tắc chuyển đổi.

## 2. Chuỗi thực thi request của Spring MVC

Với ứng dụng Spring MVC dùng DispatcherServlet, request đi qua các thành phần chính sau:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DispatcherServlet"]
    B --> C["HandlerMapping"]
    C --> D["HandlerExecutionChain"]
    D --> E["HandlerAdapter"]
    E --> F["Argument resolvers"]
    F --> G["Controller handler method"]
    G --> H["Service / business logic"]
    H --> I["Return value handlers"]
    I --> J["HttpMessageConverter"]
    J --> K["HTTP response"]
~~~

### DispatcherServlet và HandlerMapping

**DispatcherServlet** là front controller của Spring MVC. Nó nhận request và điều phối việc tìm handler. **HandlerMapping** đối chiếu request với các mapping đã đăng ký, chẳng hạn những mapping được khai báo bằng @RequestMapping, @GetMapping, @PostMapping và các biến thể.

Việc chọn handler có thể phụ thuộc nhiều điều kiện: HTTP method, path, query parameter, header, Content-Type hoặc Accept. Khi tìm được mapping phù hợp, Spring tạo một **HandlerExecutionChain**, trong đó có handler và các interceptor áp dụng cho request.

Nếu không có mapping phù hợp, request có thể kết thúc bằng lỗi 404 hoặc lỗi mapping tương ứng. Nếu nhiều mapping xung đột hoặc điều kiện không thể phân giải, Spring có thể báo lỗi cấu hình hay lỗi request. Những lỗi này xảy ra trong chuỗi thực thi HTTP.

### HandlerAdapter và argument resolvers

**HandlerAdapter** biết cách gọi loại handler đã được tìm thấy. Với controller thông thường, handler thường là một Spring MVC HandlerMethod, tức một method trên bean được quản lý bởi Spring.

Trước khi gọi method, Spring phải tạo giá trị cho từng tham số. Các **HandlerMethodArgumentResolver** đảm nhận việc này. Ví dụ:

| Tham số method | Thành phần Spring MVC thường dùng |
|---|---|
| @PathVariable UUID bookId | PathVariableMethodArgumentResolver |
| @RequestParam int page | RequestParamMethodArgumentResolver |
| @RequestHeader String requestId | RequestHeaderMethodArgumentResolver |
| @CookieValue String locale | ServletCookieValueMethodArgumentResolver |
| @RequestBody CreateBookRequest body | RequestResponseBodyMethodProcessor cùng HttpMessageConverter |
| @ModelAttribute SearchCriteria criteria | ModelAttributeMethodProcessor |

Các tên resolver trong bảng giúp hình dung vai trò nội bộ; ứng dụng thông thường không cần gọi trực tiếp các lớp này. Spring còn có resolver cho principal, session, request object, model attribute và nhiều loại tham số khác.

Đối với @RequestBody, Spring chọn HttpMessageConverter dựa trên media type và kiểu đích, rồi đọc nội dung request thành object Java. Jackson thường xử lý JSON nếu ứng dụng có cấu hình Jackson phù hợp. Quá trình này có thể kích hoạt validation khi tham số được gắn @Valid hoặc @Validated theo cơ chế tương ứng.

### Gọi handler và tạo response

Sau khi các tham số được resolve, HandlerAdapter gọi method controller. Controller thường chuyển tiếp tới service để xử lý nghiệp vụ. Kết quả method được xử lý bởi các **HandlerMethodReturnValueHandler**.

Với @ResponseBody hoặc @RestController, Spring thường dùng HttpMessageConverter để ghi object thành nội dung HTTP response. Converter chọn cách tuần tự hóa theo kiểu trả về và media type được thương lượng. Với ResponseEntity, controller còn có thể xác định status code và header.

Chuỗi runtime vì vậy quyết định ứng dụng thật sự nhận gì và trả gì. Nó không tự động đảm bảo tài liệu OpenAPI đã mô tả đầy đủ mọi trường hợp; đó là nhiệm vụ của chuỗi xây dựng đặc tả.

## 3. Chuỗi springdoc-openapi xây dựng tài liệu

springdoc-openapi tích hợp với Spring Boot và Spring MVC để phát hiện các endpoint có thể mô tả, đọc kiểu tham số và kiểu trả về, kết hợp annotation OpenAPI rồi tạo đối tượng OpenAPI. Tùy cấu hình và phiên bản, đặc tả có thể được chuẩn bị trong quá trình khởi tạo hoặc được tạo/làm mới khi endpoint tài liệu được yêu cầu; không nên dựa vào giả định rằng controller sẽ được gọi để sinh tài liệu.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Spring MVC handler mappings"]
    B --> C["Handler methods và mapping metadata"]
    C --> D["Tạo PathItem và Operation"]
    C --> E["Đọc tham số method"]
    E --> F["Parameters / RequestBody"]
    C --> G["Đọc kiểu trả về"]
    G --> H["Responses"]
    F --> I["Model / schema resolution"]
    H --> I
    J["OpenAPI annotations và cấu hình"] --> D
    J --> F
    J --> H
    I --> K["Components / schemas và $ref"]
    D --> L["OpenAPI document"]
    F --> L
    H --> L
    K --> L
    L --> M["/v3/api-docs"]
    M --> N["Swagger UI hoặc công cụ client"]
~~~

Có thể hiểu các bước ở mức khái niệm như sau:

1. Spring tạo ApplicationContext và đăng ký controller, mapping cùng các bean cấu hình.
2. springdoc truy cập metadata mapping của Spring MVC để biết handler nào có thể được mô tả, path nào gắn với HTTP method nào.
3. Từ mapping và HandlerMethod, springdoc xây dựng path item và operation tương ứng.
4. Tham số method, annotation Spring MVC và annotation OpenAPI được phân tích để xác định parameter hoặc request body.
5. Kiểu trả về và mô tả response được dùng để xây dựng danh sách response.
6. Kiểu Java, Jackson metadata, Bean Validation và @Schema được dùng trong quá trình phân giải schema.
7. Các schema có thể tái sử dụng được đặt trong components/schemas và được tham chiếu bằng $ref.
8. Các tùy biến toàn cục, theo group hoặc theo operation được áp dụng vào đặc tả.
9. Tài liệu JSON được cung cấp qua endpoint OpenAPI; Swagger UI đọc tài liệu này để hiển thị.

Đây là mô hình luồng xử lý ở mức kiến trúc. Chi tiết lớp nội bộ và thời điểm tạo tài liệu có thể thay đổi theo dòng springdoc và cấu hình ứng dụng.

### springdoc đọc metadata, không chạy nghiệp vụ

Khi tạo tài liệu, springdoc không gửi request thật vào từng endpoint, không gọi service để tạo dữ liệu mẫu, không truy vấn database và không thực thi logic controller chỉ để xem response. Nó chủ yếu sử dụng metadata có sẵn từ Spring context, chữ ký method, kiểu Java và annotation.

Điều này có hai hệ quả:

- Một controller có thể được mô tả ngay cả khi database chưa có dữ liệu, miễn là ứng dụng khởi động và metadata cần thiết có sẵn.
- Những hành vi chỉ xuất hiện lúc chạy như status code phụ thuộc dữ liệu, header được tạo động hoặc payload lỗi đặc thù không nhất thiết được suy ra đầy đủ. Cần mô tả chúng bằng annotation hoặc customizer và kiểm chứng bằng test.

Vì thế, OpenAPI là hợp đồng được khai báo và sinh từ metadata, không phải bản ghi tự động của mọi kết quả runtime.

## 4. Từ HandlerMethod đến path item và operation

Mapping Spring MVC cung cấp path và HTTP method. springdoc chuyển chúng thành cấu trúc OpenAPI:

- Một **PathItem** đại diện cho một path, ví dụ /api/books/{bookId}.
- Mỗi HTTP method được hỗ trợ trên path có thể tạo một **Operation**, chẳng hạn get, put hoặc delete.
- Operation chứa summary, description, operationId, tags, parameters, requestBody, responses, security và các metadata khác.

Ví dụ cùng một path có hai handler:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{bookId}")
    public BookResponse get(@PathVariable UUID bookId) {
        // ...
        return null;
    }

    @DeleteMapping("/{bookId}")
    public ResponseEntity<Void> delete(@PathVariable UUID bookId) {
        // ...
        return ResponseEntity.noContent().build();
    }
}
~~~

Đặc tả sẽ có một path item /api/books/{bookId} với operation get và operation delete. Không tạo hai path item chỉ vì có hai method Java. Nếu có hai handler cùng khai báo cùng method và cùng path nhưng điều kiện mapping khác, kết quả mô tả cần được kiểm tra cẩn thận vì một số điều kiện Spring MVC không có biểu diễn tương đương trực tiếp trong OpenAPI.

### Operation metadata

Annotation @Operation bổ sung nội dung ở cấp operation:

~~~java
@Operation(
    summary = "Lấy thông tin sách",
    description = "Tìm sách theo mã định danh.",
    operationId = "getBookById",
    tags = {"Books"}
)
@GetMapping("/{bookId}")
public BookResponse get(@PathVariable UUID bookId) {
    // ...
    return null;
}
~~~

@Operation không tạo ra endpoint Spring MVC. Mapping Spring MVC quyết định endpoint nào thực sự tồn tại; @Operation bổ sung cách endpoint đó được trình bày trong hợp đồng OpenAPI. Nếu gắn @Operation nhưng không có mapping hợp lệ, annotation đó không tự tạo ra route HTTP.

operationId nên duy nhất trong tài liệu. Nó thường được công cụ sinh client dùng làm tên hàm. Nếu operationId thay đổi giữa các lần phát hành, SDK được sinh lại có thể đổi tên method và gây ảnh hưởng đến mã nguồn client.

## 5. Từ tham số handler đến Parameter hoặc RequestBody

springdoc kết hợp vị trí bind của Spring MVC với metadata OpenAPI để phân loại đầu vào:

| Annotation / kiểu tham số | Thành phần OpenAPI thường tạo |
|---|---|
| @PathVariable | Parameter với in: path |
| @RequestParam | Parameter với in: query |
| @RequestHeader | Parameter với in: header |
| @CookieValue | Parameter với in: cookie |
| @RequestBody | RequestBody |
| @ModelAttribute hoặc @ParameterObject | Thường được biểu diễn thành các query parameter theo thuộc tính phù hợp |

Ví dụ:

~~~java
@GetMapping("/{bookId}/search")
public List<BookResponse> search(
    @PathVariable UUID bookId,
    @RequestParam(required = false) String title,
    @RequestHeader(name = "X-Client-Version", required = false)
    String clientVersion
) {
    // ...
    return List.of();
}
~~~

Trong ví dụ, path template có placeholder bookId nên @PathVariable bind đúng giá trị đó; title là query parameter và X-Client-Version là header parameter. Khi viết mã thật, tên placeholder và tên được bind phải khớp, còn mỗi tham số cần được phân loại theo vị trí dữ liệu client gửi.

Với request body, ví dụ:

~~~java
public record CreateBookRequest(
    String title,
    String author
) {}

@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
    @Valid @RequestBody CreateBookRequest request
) {
    // ...
    return null;
}
~~~

springdoc có thể tạo requestBody với content type application/json và schema tham chiếu tới CreateBookRequest. Nếu cần mô tả required, media type, ví dụ hoặc schema khác với suy luận mặc định, có thể bổ sung annotation OpenAPI @RequestBody, @Content và @Schema.

Không phải mọi tham số method đều là dữ liệu client gửi. Ví dụ HttpServletRequest, Principal, Authentication hoặc các object được Spring inject theo cơ chế riêng không nên bị hiểu nhầm thành query parameter. springdoc có quy tắc nhận diện nhiều kiểu tham số đặc biệt; nếu một kiểu tùy biến bị tài liệu hóa sai, hãy dùng annotation phù hợp hoặc ẩn tham số khỏi tài liệu sau khi xác nhận hành vi thực tế.

## 6. Từ kiểu Java đến schema

Schema là phần mô tả cấu trúc dữ liệu. springdoc dùng kiểu Java cùng các metadata liên quan để tạo schema:

- Kiểu nguyên thủy và wrapper được ánh xạ thành boolean, integer, number hoặc string.
- UUID, ngày tháng và thời điểm có thể được biểu diễn bằng format tương ứng.
- Enum thường trở thành tập giá trị enum.
- Collection và array trở thành schema type array với schema items.
- Map thường trở thành object với additionalProperties.
- DTO hoặc record trở thành object với các property.
- Generic type như ResponseEntity<BookResponse> được phân tích để lấy kiểu dữ liệu bên trong khi có thể xác định được.

Ví dụ:

~~~java
@Schema(name = "BookResponse", description = "Thông tin sách")
public record BookResponse(
    @Schema(description = "Mã sách", example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001")
    UUID id,

    @Schema(description = "Tên sách", example = "Spring in Action")
    String title,

    @Schema(description = "Năm xuất bản", example = "2024")
    Integer publicationYear
) {}
~~~

Đặc tả có thể chứa schema tương tự:

~~~yaml
components:
  schemas:
    BookResponse:
      type: object
      description: Thông tin sách
      properties:
        id:
          type: string
          format: uuid
          description: Mã sách
          example: 8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001
        title:
          type: string
          description: Tên sách
          example: Spring in Action
        publicationYear:
          type: integer
          format: int32
          description: Năm xuất bản
          example: 2024
~~~

Ví dụ YAML trên minh họa cấu trúc, không phải bản chụp bảo đảm giống hệt kết quả của mọi cấu hình. Trong đặc tả thực tế, ví dụ UUID cần là một chuỗi UUID hợp lệ; ví dụ số năm là số nguyên. Khi viết tài liệu, luôn chọn example phù hợp kiểu đã khai báo.

### Jackson và Bean Validation ảnh hưởng đến schema

Jackson quyết định cách object Java được tuần tự hóa và đọc từ JSON. Các annotation như @JsonProperty, @JsonIgnore, @JsonPropertyOrder, naming strategy và cấu hình ObjectMapper có thể ảnh hưởng tên property, khả năng đọc/ghi và hình dạng dữ liệu được mô tả.

Bean Validation cung cấp các ràng buộc như @NotNull, @NotBlank, @Size, @Min, @Max, @Email và @Pattern. springdoc có thể dùng một số metadata này để bổ sung required hoặc giới hạn vào schema khi tích hợp và phiên bản hỗ trợ. Không nên mặc định rằng mọi constraint đều được chuyển đổi hoàn hảo hoặc rằng constraint Java đã được thực thi chỉ vì schema hiển thị nó.

@Schema có thể bổ sung description, example, allowableValues, minimum, maximum, minLength, maxLength, format và các metadata khác. Dùng nó khi suy luận từ kiểu Java chưa thể hiện hết hợp đồng.

### Component schema và tham chiếu $ref

Khi nhiều operation sử dụng cùng một DTO, OpenAPI thường đặt định nghĩa trong components/schemas rồi dùng $ref để tham chiếu. Điều này giúp tránh lặp lại schema và giữ các operation nhất quán.

~~~yaml
paths:
  /api/books:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookRequest"
      responses:
        "201":
          description: Đã tạo sách
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
components:
  schemas:
    CreateBookRequest:
      type: object
      properties:
        title:
          type: string
        author:
          type: string
    BookResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        title:
          type: string
        author:
          type: string
~~~

Không nên phụ thuộc vào tên component được sinh tự động nếu tên đó là một phần của hợp đồng cần ổn định. Có thể dùng @Schema(name = "...") để đặt tên rõ ràng. Khi đổi tên component hoặc cấu trúc DTO, hãy đánh giá ảnh hưởng đến tài liệu, SDK và client đã tích hợp.

## 7. Từ kiểu trả về đến Response

Kiểu trả về của handler là một đầu vào quan trọng để springdoc suy ra response thành công. Ví dụ:

~~~java
@GetMapping("/{bookId}")
public ResponseEntity<BookResponse> get(
    @PathVariable UUID bookId
) {
    // ...
    return ResponseEntity.ok(null);
}
~~~

springdoc có thể suy ra response body từ BookResponse bên trong ResponseEntity. Tuy nhiên, kiểu trả về không nhất thiết cho biết mọi status code có thể xuất hiện. Controller có thể trả các status khác nhau theo điều kiện, exception handler có thể chuyển lỗi thành response riêng, và filter hoặc security layer có thể trả lỗi trước khi handler được gọi.

Khi hợp đồng cần rõ ràng, mô tả response bằng @ApiResponse và @ApiResponses:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy sách",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = BookResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sách"
    )
})
@GetMapping("/{bookId}")
public ResponseEntity<BookResponse> get(
    @PathVariable UUID bookId
) {
    // ...
    return ResponseEntity.ok(null);
}
~~~

Nếu ứng dụng có @ControllerAdvice hoặc @ExceptionHandler dùng chung, cần quyết định cách phản ánh lỗi toàn cục vào hợp đồng. Không nên giả định mọi response do filter, gateway, security framework hoặc reverse proxy trả về đều được suy ra từ method controller. Có thể dùng annotation phù hợp, OpenApiCustomizer hoặc cơ chế cấu hình tài liệu theo dự án để mô tả các response chung.

## 8. Tùy biến đúng tầng trong chuỗi tạo tài liệu

springdoc cung cấp nhiều điểm mở rộng. Chọn điểm phù hợp giúp thay đổi có phạm vi rõ ràng:

| Điểm tùy biến | Phạm vi | Dùng khi |
|---|---|---|
| Annotation Spring MVC | Hành vi bind và route thật | Thay đổi mapping, required hoặc kiểu nhận dữ liệu |
| @Operation, @Parameter, @Schema, @ApiResponse | Một handler hoặc một phần hợp đồng cụ thể | Bổ sung mô tả, ví dụ, schema, response |
| OpenAPI bean | Metadata và cấu hình tài liệu chung | Tên API, phiên bản, server, security scheme, license |
| OperationCustomizer | Mỗi operation được xây dựng | Bổ sung metadata theo operation hoặc quy tắc chung |
| OpenApiCustomizer | Đối tượng OpenAPI của tài liệu | Chỉnh sửa cấu trúc tài liệu sau khi được tạo |
| GroupedOpenApi | Một nhóm endpoint và tài liệu riêng | Tách public/internal hoặc phân nhóm theo path/package |

Ví dụ metadata chung:

~~~java
@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI bookApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Book API")
                .version("v1")
                .description("API quản lý sách"));
    }
}
~~~

Ví dụ tùy biến operation:

~~~java
@Bean
OperationCustomizer operationIdPrefix() {
    return (operation, handlerMethod) -> {
        if (operation.getOperationId() != null) {
            operation.setOperationId("books_" + operation.getOperationId());
        }
        return operation;
    };
}
~~~

Ví dụ tùy biến tài liệu:

~~~java
@Bean
OpenApiCustomizer addCommonTag() {
    return openApi -> openApi.addTagsItem(
        new Tag().name("Books").description("Các thao tác với sách")
    );
}
~~~

Các đoạn code trên là minh họa cho API tùy biến của springdoc và swagger-models; cần có import và dependency phù hợp với phiên bản đang dùng. Customizer thay đổi tài liệu được sinh ra, không thay đổi cách Spring MVC chọn handler hay bind request. Nếu muốn sửa hành vi endpoint, hãy sửa mapping hoặc logic ứng dụng.

Với nhiều tài liệu độc lập, GroupedOpenApi cho phép chọn các path hoặc package phù hợp cho từng group. Khi đó, mỗi group có thể có endpoint tài liệu riêng. Cần kiểm tra customizer đang được áp dụng cho group nào để tránh vô tình đưa endpoint nội bộ vào tài liệu công khai hoặc bỏ sót operation.

## 9. Ví dụ truy vết một endpoint từ handler đến schema

Xét DTO và controller:

~~~java
public record CreateBookRequest(
    @NotBlank
    @Schema(description = "Tên sách", example = "Spring in Action")
    String title,

    @NotBlank
    @Schema(description = "Tác giả", example = "Craig Walls")
    String author
) {}

public record BookResponse(
    UUID id,
    String title,
    String author
) {}

@RestController
@RequestMapping("/api/books")
class BookController {

    @Operation(
        summary = "Tạo sách",
        operationId = "createBook",
        tags = {"Books"}
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đã tạo sách",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = BookResponse.class)
            )
        )
    })
    @PostMapping
    public ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request
    ) {
        // ...
        return ResponseEntity.status(HttpStatus.CREATED).body(null);
    }
}
~~~

Có thể truy vết như sau:

| Nguồn trong mã nguồn | Kết quả trong OpenAPI |
|---|---|
| @RequestMapping("/api/books") | Path item /api/books |
| @PostMapping | Operation post |
| @Operation(summary, operationId, tags) | summary, operationId và tags |
| @RequestBody CreateBookRequest | requestBody |
| consumes mặc định hoặc khai báo của mapping | Media type trong requestBody.content |
| CreateBookRequest | Schema cho payload request |
| @NotBlank và @Schema | Constraint, mô tả hoặc ví dụ nếu được hỗ trợ và suy ra |
| ResponseEntity<BookResponse> | Schema body cho response thành công |
| @ApiResponse(responseCode = "201") | Response 201 với mô tả rõ ràng |

Ví dụ OpenAPI rút gọn:

~~~yaml
paths:
  /api/books:
    post:
      operationId: createBook
      summary: Tạo sách
      tags:
        - Books
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookRequest"
      responses:
        "201":
          description: Đã tạo sách
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
components:
  schemas:
    CreateBookRequest:
      type: object
      properties:
        title:
          type: string
          description: Tên sách
          example: Spring in Action
        author:
          type: string
          description: Tác giả
          example: Craig Walls
    BookResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        title:
          type: string
        author:
          type: string
~~~

Đây là sơ đồ rút gọn để đọc mối liên hệ giữa handler, operation và schema. Đặc tả thực tế có thể thêm required, content type, response mặc định và các metadata khác tùy cấu hình cùng phiên bản.

## 10. Vì sao endpoint hoặc schema không xuất hiện như mong đợi?

Khi tài liệu khác kỳ vọng, hãy tìm lỗi theo đúng tầng:

| Dấu hiệu | Tầng cần kiểm tra | Hướng xử lý |
|---|---|---|
| Endpoint không có trong /v3/api-docs | Mapping và bộ lọc tài liệu | Kiểm tra @RequestMapping, HTTP method, package/path filter, group và @Hidden |
| Có path nhưng thiếu operation | Mapping method hoặc điều kiện mapping | Kiểm tra method mapping, mapping xung đột và khả năng biểu diễn trong OpenAPI |
| Parameter xuất hiện sai vị trí | Argument binding | Đối chiếu @PathVariable, @RequestParam, @RequestHeader, @CookieValue và path template |
| Object bị biến thành nhiều query parameter ngoài ý muốn | Model attribute / parameter object | Xác nhận ý định bind; dùng @RequestBody nếu dữ liệu thuộc body |
| Request body thiếu schema | Message body và model resolution | Kiểm tra @RequestBody, media type, kiểu generic và annotation ẩn |
| Property schema thiếu hoặc sai tên | Jackson và schema metadata | Kiểm tra @JsonProperty, @JsonIgnore, naming strategy và @Schema |
| Enum hoặc collection có dạng sai | Kiểu Java và serialization | Kiểm tra enum, item schema, style, explode và binding thực tế |
| Response thiếu mã lỗi | Exception handling và response metadata | Khai báo @ApiResponse hoặc tùy biến tài liệu cho lỗi chung |
| Tài liệu trùng hoặc có operationId xung đột | Mapping và operation customization | Kiểm tra route trùng, group và quy tắc operationId |

Đặc biệt, phân biệt lỗi tài liệu với lỗi runtime. Nếu handler không được Spring MVC đăng ký, việc thêm @Operation sẽ không tạo route. Nếu handler chạy đúng nhưng schema sai, hãy xem model resolution và annotation mô tả. Nếu schema đúng nhưng server serialize khác, cần kiểm tra Jackson và converter.

## 11. Kiểm tra chuỗi tạo tài liệu từ đầu đến cuối

Sau khi ứng dụng khởi động, truy cập endpoint OpenAPI JSON thường là /v3/api-docs. Nếu bật YAML, có thể dùng /v3/api-docs.yaml. Swagger UI thường đọc endpoint này để hiển thị tài liệu tại /swagger-ui/index.html hoặc đường dẫn được cấu hình.

Với một endpoint mẫu, nên kiểm tra theo thứ tự:

1. **Mapping:** endpoint có đúng path và HTTP method trong Spring MVC không?
2. **Handler:** method controller có được Spring đăng ký và có thể được gọi không?
3. **Input binding:** từng tham số được lấy từ path, query, header, cookie hay body?
4. **Operation:** OpenAPI có đúng path item, HTTP method, operationId, summary và tags không?
5. **Schema đầu vào:** request body và parameter có kiểu, format, required, enum và ví dụ đúng không?
6. **Response:** status code, media type, header và schema có phản ánh kết quả API không?
7. **Serialization:** Jackson và HttpMessageConverter có tạo payload thực tế tương thích với schema không?
8. **Tùy biến:** customizer và group có thay đổi hoặc lọc tài liệu ngoài ý muốn không?

Nên có kiểm tra tự động cho các hợp đồng quan trọng. Có thể tải JSON từ /v3/api-docs trong môi trường kiểm thử, phân tích cấu trúc hoặc so sánh với snapshot đã duyệt. Nếu dùng OpenAPI làm đầu vào để sinh SDK, hãy kiểm tra operationId và schema tương thích trước khi phát hành.

## 12. Nguyên tắc chọn đúng điểm sửa

Khi thấy sai lệch, hãy xác định câu hỏi cần giải quyết:

- **Route hoặc cách bind sai:** sửa annotation và mapping Spring MVC.
- **Mô tả endpoint chưa rõ:** dùng @Operation hoặc @Parameter.
- **DTO chưa phản ánh hợp đồng:** sửa kiểu Java, Jackson metadata, Bean Validation hoặc @Schema.
- **Status code hoặc lỗi chưa đầy đủ:** bổ sung @ApiResponse hoặc cấu hình mô tả response chung.
- **Metadata toàn API chưa đúng:** dùng OpenAPI bean.
- **Quy tắc cần áp dụng cho nhiều operation:** cân nhắc OperationCustomizer hoặc OpenApiCustomizer.
- **Muốn tách tài liệu theo nhóm:** dùng GroupedOpenApi và kiểm tra path/package filter.

Một thay đổi ở tầng tài liệu không tự thay đổi hành vi server. Ngược lại, thay đổi kiểu DTO hoặc mapping có thể làm đặc tả thay đổi theo. Vì vậy, mỗi lần chỉnh sửa nên kiểm tra cả tài liệu sinh ra và request/response thực tế.

## Kết luận

Spring MVC xử lý request bằng cách tìm handler, resolve tham số, gọi method và chuyển kết quả thành response. springdoc-openapi dùng metadata của mapping, HandlerMethod, kiểu Java và annotation để xây dựng path item, operation, parameter, requestBody, response và schema. Handler là điểm thực thi trong ứng dụng; operation là mô tả hành động HTTP; schema là hợp đồng dữ liệu. Khi xác định đúng tầng gây sai lệch, ta có thể chọn annotation, model hoặc customizer phù hợp và kiểm chứng tài liệu với hành vi runtime.
