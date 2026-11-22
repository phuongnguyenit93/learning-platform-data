# @Schema ở cấp lớp, thuộc tính và tham số

Trong OpenAPI, **schema** mô tả hình dạng và ràng buộc của dữ liệu: một object có những property nào, mỗi property có kiểu gì, giá trị nào được chấp nhận và client cần gửi trường nào. springdoc-openapi thường suy ra schema từ kiểu Java, Jackson và Bean Validation. Khi thông tin suy luận chưa đủ rõ, annotation **@Schema** của swagger-annotations cho phép bổ sung mô tả ngay tại lớp DTO, thuộc tính hoặc vị trí dữ liệu được dùng trong operation.

Điểm quan trọng là đặt annotation đúng tầng. **@Schema** mô tả cấu trúc dữ liệu; **@Parameter** mô tả một tham số HTTP; còn annotation Spring MVC như **@RequestParam**, **@PathVariable** và **@RequestBody** quyết định cách request được bind. Kết hợp đúng các lớp này giúp OpenAPI phản ánh hợp đồng mà client thực sự cần sử dụng.

## 1. Schema được tạo từ đâu?

Xét một DTO đơn giản:

~~~java
public class BookResponse {
    private UUID id;
    private String title;
    private String author;

    // constructors, getters và setters
}
~~~

Khi controller trả về BookResponse, springdoc phân tích kiểu Java để tạo schema object. Mỗi property có kiểu tương ứng; UUID thường được biểu diễn thành string với format uuid, còn title và author thành string.

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{bookId}")
    public BookResponse getBook(@PathVariable UUID bookId) {
        // ...
        return null;
    }
}
~~~

Một phần OpenAPI được sinh ra có thể tương tự:

~~~yaml
components:
  schemas:
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

Schema sinh ra không chỉ phụ thuộc vào tên class. springdoc và swagger-core còn xét kiểu Java, generic type, cấu hình Jackson, annotation Jackson, Bean Validation và annotation OpenAPI. Vì vậy, cùng một DTO có thể tạo ra schema khác nhau nếu cách serialize hoặc metadata được thay đổi.

@Schema giúp kiểm soát những phần mà kiểu Java không thể diễn đạt đầy đủ, chẳng hạn tên hiển thị, mô tả nghiệp vụ, ví dụ, giá trị hợp lệ, giới hạn số, giới hạn độ dài, trạng thái bắt buộc hoặc hướng dữ liệu.

## 2. @Schema ở cấp lớp

Đặt **@Schema** trên class hoặc record để mô tả toàn bộ model. Những thuộc tính thường dùng:

| Thuộc tính | Mục đích |
|---|---|
| **name** | Đặt tên schema trong tài liệu, thường xuất hiện dưới components/schemas |
| **title** | Tiêu đề dễ đọc của schema |
| **description** | Giải thích model đại diện cho dữ liệu gì |
| **example** | Ví dụ minh họa toàn bộ model |
| **requiredProperties** | Liệt kê tên property bắt buộc ở cấp schema |
| **additionalProperties** | Cho biết object có cho phép property động ngoài danh sách đã khai báo hay không |
| **additionalPropertiesSchema** | Chỉ định kiểu schema của các giá trị property động |
| **deprecated** | Đánh dấu schema đã lỗi thời và không nên dùng cho thiết kế mới |
| **hidden** | Loại schema khỏi tài liệu trong những trường hợp phù hợp |

Ví dụ với class:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "BookResponse",
    title = "Thông tin sách",
    description = "Dữ liệu sách được trả về cho ứng dụng client",
    example = """
        {
          "id": "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
          "title": "Spring in Action",
          "author": "Craig Walls"
        }
        """
)
public record BookResponse(
    UUID id,
    String title,
    String author
) {}
~~~

Ở đây:

- **name** điều khiển tên model được mô tả trong OpenAPI. Tên này có thể được tham chiếu từ request body hoặc response bằng $ref.
- **title** là nhãn dễ đọc, còn **description** giải thích ý nghĩa và phạm vi của model.
- **example** minh họa một object hoàn chỉnh. Ví dụ cần khớp kiểu dữ liệu và cấu trúc property.

Không nên đổi tên schema tùy tiện nếu tài liệu OpenAPI được lưu làm hợp đồng hoặc dùng để sinh SDK. Việc đổi tên component có thể làm thay đổi đường dẫn $ref và ảnh hưởng đến công cụ downstream, dù endpoint HTTP không đổi.

### Đặt tên schema và tái sử dụng

Nếu không đặt name, tên component thường được suy ra từ tên class. Có thể dùng name để tạo tên ổn định, dễ hiểu hơn tên nội bộ:

~~~java
@Schema(name = "CustomerSummary", description = "Thông tin khách hàng rút gọn")
public record CustomerSummaryResponse(
    UUID id,
    String displayName
) {}
~~~

Khi nhiều operation dùng cùng kiểu Java, springdoc thường tạo một component schema dùng chung rồi tham chiếu bằng $ref. Nếu hai class khác nhau được gán cùng một tên schema, có thể xảy ra xung đột hoặc phải xử lý model resolution theo cấu hình. Hãy giữ tên component duy nhất trong tài liệu và chỉ dùng tên trùng khi có chủ đích rõ ràng.

### Class-level schema không phải operation

@Schema trên class mô tả một model dữ liệu. Nó không tạo endpoint, không đặt HTTP method, không gắn path, không thay thế @Operation và cũng không thay thế @Tag. Một DTO có thể được dùng trong nhiều operation nhưng vẫn giữ cùng mô tả schema.

## 3. @Schema ở cấp thuộc tính

Khi cần mô tả từng trường, đặt **@Schema** trên field, getter hoặc record component mà cơ chế model resolution của dự án nhận diện. Các thuộc tính thường dùng:

- **description**: ý nghĩa của property.
- **example**: giá trị minh họa cho property.
- **type** và **format**: kiểu hoặc định dạng trên wire khi cần ghi đè suy luận.
- **allowableValues**: danh sách giá trị hợp lệ, thường dùng cho enum hoặc chuỗi có tập giá trị cố định.
- **minimum**, **maximum**, **exclusiveMinimum**, **exclusiveMaximum**: giới hạn số.
- **minLength**, **maxLength**, **pattern**: ràng buộc chuỗi.
- **requiredMode**: xác định property có bắt buộc hay không.
- **accessMode**: thể hiện property chỉ đọc, chỉ ghi hoặc đọc/ghi.
- **deprecated**: đánh dấu property đã lỗi thời.

Ví dụ:

~~~java
@Schema(
    name = "CreateBookRequest",
    description = "Dữ liệu client gửi để tạo sách"
)
public record CreateBookRequest(
    @Schema(
        description = "Tên sách",
        example = "Spring in Action",
        minLength = 1,
        maxLength = 200,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String title,

    @Schema(
        description = "Tên tác giả",
        example = "Craig Walls",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String author,

    @Schema(
        description = "Năm xuất bản",
        example = "2024",
        minimum = "1",
        maximum = "9999"
    )
    Integer publicationYear
) {}
~~~

Schema có thể biểu diễn ràng buộc tương tự:

~~~yaml
components:
  schemas:
    CreateBookRequest:
      type: object
      required:
        - title
        - author
      properties:
        title:
          type: string
          description: Tên sách
          minLength: 1
          maxLength: 200
          example: Spring in Action
        author:
          type: string
          description: Tên tác giả
          minLength: 1
          maxLength: 120
          example: Craig Walls
        publicationYear:
          type: integer
          format: int32
          description: Năm xuất bản
          minimum: 1
          maximum: 9999
~~~

Ví dụ YAML là hình dung kết quả hợp đồng; cấu trúc chính xác có thể thay đổi theo phiên bản OpenAPI, swagger-core, springdoc và cách cấu hình model resolution.

### requiredMode và requiredProperties

Trong các phiên bản swagger-annotations hiện đại, nên dùng **requiredMode** thay cho thuộc tính **required** cũ đã deprecated:

- **Schema.RequiredMode.REQUIRED**: property phải xuất hiện trong object.
- **Schema.RequiredMode.NOT_REQUIRED**: property không bắt buộc.
- **Schema.RequiredMode.AUTO**: để thư viện suy luận từ metadata có sẵn.

Ở cấp class, **requiredProperties** cho phép liệt kê tên property bắt buộc. Không nên khai báo cùng một quy tắc ở nhiều nơi nếu chúng có thể mâu thuẫn. Khi hợp đồng yêu cầu chính xác, đặt requiredMode ngay trên property thường giúp người đọc hiểu rõ ý định.

**Required** trả lời câu hỏi property có phải xuất hiện hay không. Nó không đồng nghĩa với việc giá trị có được phép là null hay không. Cách biểu diễn null cũng phụ thuộc phiên bản OpenAPI: OpenAPI 3.0 có từ khóa nullable, còn OpenAPI 3.1 dựa trên JSON Schema và cách biểu diễn union type. Hãy xác minh đặc tả đầu ra theo phiên bản mà ứng dụng phát hành.

### Bean Validation và @Schema

Các annotation Bean Validation như @NotNull, @NotBlank, @Size, @Min, @Max và @Pattern có thể cung cấp ràng buộc để springdoc bổ sung vào schema khi dependency và phiên bản hỗ trợ:

~~~java
public record CreateAuthorRequest(
    @NotBlank
    @Size(max = 100)
    @Schema(description = "Tên tác giả", example = "Ursula K. Le Guin")
    String name,

    @Email
    @Schema(description = "Email liên hệ", example = "author@example.test")
    String email
) {}
~~~

@Schema bổ sung metadata cho hợp đồng; Bean Validation định nghĩa ràng buộc được thực thi ở runtime khi ứng dụng kích hoạt validation phù hợp. Để Spring kiểm tra dữ liệu body, thường cần @Valid hoặc @Validated ở điểm bind và cấu hình validation tương ứng. Chỉ nhìn thấy minLength hoặc required trong OpenAPI không chứng minh server đã thực thi ràng buộc đó.

Nếu annotation Bean Validation và @Schema mâu thuẫn, tài liệu có thể gây hiểu nhầm. Hãy thống nhất nguồn quy tắc và kiểm tra JSON/YAML sinh ra. Ví dụ @Size(max = 100) không nên đi cùng @Schema(maxLength = 200) nếu hợp đồng runtime chỉ chấp nhận 100 ký tự.

## 4. Kiểu dữ liệu và format

OpenAPI có các kiểu cơ bản như string, integer, number, boolean, object và array. **format** bổ sung cách diễn giải cụ thể cho một kiểu. Thông thường springdoc suy ra chúng từ kiểu Java:

| Kiểu Java | Schema thường gặp |
|---|---|
| String | type: string |
| Integer / int | type: integer, format: int32 |
| Long / long | type: integer, format: int64 |
| BigDecimal | type: number, thường có format phù hợp với thư viện |
| Boolean / boolean | type: boolean |
| UUID | type: string, format: uuid |
| LocalDate | type: string, format: date |
| Instant / OffsetDateTime | type: string, format: date-time |
| Enum | type: string với enum values |
| List<T> / T[] | type: array, items là schema của T |

Chỉ ghi đè type hoặc format khi có lý do rõ ràng, chẳng hạn kiểu Java tùy biến được serialize thành chuỗi. Nếu khai báo type không tương thích với JSON thực tế, client generator có thể tạo kiểu dữ liệu sai.

Ví dụ một mã sản phẩm trong Java được lưu dưới dạng String nhưng hợp đồng chỉ nhận chuỗi theo mẫu:

~~~java
public record ProductCode(
    @Schema(
        description = "Mã sản phẩm gồm hai chữ cái và sáu chữ số",
        example = "AB123456",
        pattern = "^[A-Z]{2}[0-9]{6}$",
        minLength = 8,
        maxLength = 8
    )
    String value
) {}
~~~

Nếu đây là property của DTO, schema sẽ mô tả chuỗi và pattern. Tuy nhiên, pattern trong tài liệu không tự kiểm tra giá trị ở runtime; hãy dùng Bean Validation hoặc logic domain nếu server cần từ chối dữ liệu không hợp lệ.

## 5. Enum và tập giá trị được phép

Với enum Java, springdoc thường có thể suy ra danh sách giá trị:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

public record BookResponse(
    UUID id,
    String title,
    BookStatus status
) {}
~~~

Schema tương ứng có thể là:

~~~yaml
status:
  type: string
  enum:
    - DRAFT
    - PUBLISHED
    - ARCHIVED
~~~

Khi dùng @Schema(allowableValues = {...}) trên property kiểu String, có thể mô tả tập giá trị cho một chuỗi không dùng enum Java:

~~~java
@Schema(
    description = "Ngôn ngữ hiển thị",
    allowableValues = {"vi", "en", "ja"},
    example = "vi"
)
private String locale;
~~~

Nếu enum được serialize bằng tên khác thông qua Jackson, chẳng hạn @JsonValue hoặc custom serializer, hãy kiểm tra enum values trong OpenAPI có trùng với giá trị JSON thật không. Tên hằng enum Java không nhất thiết là giá trị được gửi trên HTTP.

## 6. Property chỉ đọc, chỉ ghi và dữ liệu nhạy cảm

Một model có thể chứa trường chỉ xuất hiện trong response hoặc chỉ được gửi trong request. Dùng **accessMode** để diễn đạt hướng sử dụng:

~~~java
@Schema(name = "UserProfile", description = "Thông tin hồ sơ người dùng")
public record UserProfile(
    @Schema(
        description = "Mã hồ sơ do server cấp",
        accessMode = Schema.AccessMode.READ_ONLY,
        example = "42"
    )
    Long id,

    @Schema(
        description = "Tên hiển thị",
        example = "Minh Anh"
    )
    String displayName,

    @Schema(
        description = "Mã khôi phục chỉ gửi khi tạo hoặc cập nhật",
        accessMode = Schema.AccessMode.WRITE_ONLY
    )
    String recoveryCode
) {}
~~~

- **READ_ONLY** cho biết client chỉ đọc trường từ response; server không mong client gửi trường đó như một phần dữ liệu đầu vào thông thường.
- **WRITE_ONLY** cho biết trường được gửi vào request nhưng không được trả về trong response.
- **READ_WRITE** thể hiện trường có thể xuất hiện ở cả hai hướng.

Các thuộc tính này mô tả hợp đồng OpenAPI. Chúng không tự xóa property khỏi JSON, không mã hóa dữ liệu và không thay thế kiểm soát truy cập. Nếu trường nhạy cảm không được phép xuất hiện trong response, hãy bảo đảm serializer và DTO thực tế không trả nó về; không dựa riêng vào accessMode hoặc hidden.

Trong nhiều API, dùng DTO riêng cho request và response là cách rõ ràng hơn một model dùng chung:

~~~java
public record CreateUserRequest(
    @NotBlank String displayName,
    @NotBlank String password
) {}

public record UserResponse(
    UUID id,
    String displayName
) {}
~~~

Hai DTO riêng giúp hợp đồng đầu vào và đầu ra thể hiện đúng những trường thực sự được nhận và trả về. @Schema tiếp tục bổ sung mô tả cho từng model.

## 7. @Schema ở cấp tham số operation

Tham số HTTP có hai phần: vị trí và tên của parameter, cùng schema mô tả kiểu dữ liệu được truyền. Với tham số trong path, query, header hoặc cookie, dùng **@Parameter** để mô tả parameter; thuộc tính **schema** bên trong @Parameter nhận một **@Schema** để mô tả kiểu và ràng buộc của giá trị đó.

~~~java
@GetMapping("/search")
public List<BookResponse> search(
    @Parameter(
        name = "keyword",
        description = "Từ khóa tìm kiếm theo tên sách hoặc tác giả",
        example = "Spring",
        required = true,
        schema = @Schema(
            type = "string",
            minLength = 2,
            maxLength = 80
        )
    )
    @RequestParam(name = "keyword")
    String query
) {
    // ...
    return List.of();
}
~~~

Ở đây có hai lớp metadata:

- **@RequestParam(name = "keyword")** cho Spring MVC biết query key nào được bind vào biến query.
- **@Parameter** mô tả tên, vị trí được suy ra từ mapping, ý nghĩa, ví dụ và trạng thái required trong tài liệu.
- **@Schema** bên trong @Parameter.schema mô tả kiểu string cùng giới hạn độ dài.

Tên biến Java là query; tên query parameter công khai là keyword. Nếu bỏ tên tường minh trong @RequestParam, ứng dụng cần metadata tên tham số như -parameters để Spring suy ra đúng tên.

### Path parameter

~~~java
@GetMapping("/{bookId}")
public BookResponse get(
    @Parameter(
        description = "UUID của sách",
        example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001",
        schema = @Schema(type = "string", format = "uuid")
    )
    @PathVariable("bookId") UUID id
) {
    // ...
    return null;
}
~~~

Path parameter luôn bắt buộc theo OpenAPI. Không khai báo required=false cho parameter ở vị trí path; nếu giá trị có thể vắng mặt, thiết kế URL thường nên dùng query parameter hoặc một route khác.

### Query parameter số

~~~java
@GetMapping
public List<BookResponse> list(
    @Parameter(
        description = "Số trang, bắt đầu từ 0",
        example = "0",
        schema = @Schema(
            type = "integer",
            format = "int32",
            minimum = "0",
            defaultValue = "0"
        )
    )
    @RequestParam(name = "page", defaultValue = "0")
    int page
) {
    // ...
    return List.of();
}
~~~

Giá trị mặc định trong annotation Spring MVC quyết định hành vi bind khi client bỏ query key. defaultValue trong schema mô tả hợp đồng cho người đọc tài liệu. Nên giữ chúng thống nhất; nếu chỉ cập nhật một phía, Swagger UI có thể hướng dẫn client sai so với server.

### Header và cookie parameter

~~~java
@GetMapping("/preferences")
public PreferenceResponse preferences(
    @Parameter(
        description = "Ngôn ngữ giao diện",
        example = "vi",
        schema = @Schema(
            type = "string",
            allowableValues = {"vi", "en", "ja"}
        )
    )
    @RequestHeader(name = "X-Preferred-Language", required = false)
    String language
) {
    // ...
    return null;
}
~~~

Đối với cookie:

~~~java
@GetMapping("/settings")
public SettingsResponse settings(
    @Parameter(
        description = "Cookie lựa chọn ngôn ngữ",
        schema = @Schema(type = "string", example = "vi")
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    // ...
    return null;
}
~~~

Không dùng @Schema để khai báo vị trí path/query/header/cookie. Vị trí thuộc Parameter Object và thường được springdoc suy ra từ annotation Spring MVC; nếu cần mô tả tường minh, đặt **in** trong @Parameter.

## 8. @Schema cho request body và response content

Với request body, schema thường được suy ra từ kiểu tham số @RequestBody. Có thể khai báo tường minh khi cần chọn kiểu triển khai cụ thể hoặc mô tả response/request phức tạp:

~~~java
@Operation(summary = "Tạo sách")
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public BookResponse create(
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
    return null;
}
~~~

Trong ví dụ, có hai annotation cùng tên RequestBody: một của Spring MVC để bind JSON và một của OpenAPI để mô tả request body trong tài liệu. Khi dùng cả hai, nên dùng tên đầy đủ hoặc import có chủ đích để tránh nhầm lẫn.

Với response:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Thông tin sách",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = BookResponse.class)
    )
)
@GetMapping("/{bookId}")
public BookResponse get(@PathVariable UUID bookId) {
    // ...
    return null;
}
~~~

**implementation** cho biết class nào được dùng để xây dựng schema. Cách này hữu ích khi kiểu trả về là wrapper, interface, generic hoặc khi muốn chỉ rõ model trong tài liệu. Không nên dùng implementation để mô tả một kiểu khác với JSON mà endpoint thực sự trả về.

## 9. Collection, object lồng nhau và schema của phần tử

Với collection, OpenAPI cần mô tả schema của phần tử bên trong mảng. Ví dụ:

~~~java
public record BookCollectionResponse(
    @Schema(description = "Các sách trong kết quả")
    List<BookResponse> items,

    @Schema(description = "Tổng số bản ghi", example = "120")
    long total
) {}
~~~

Schema của items là array và items schema tham chiếu tới BookResponse. Nếu cần mô tả trực tiếp một mảng ở request hoặc response content, swagger-annotations cung cấp **@ArraySchema** để mô tả container và schema của từng phần tử:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sách",
    content = @Content(
        array = @ArraySchema(
            schema = @Schema(implementation = BookResponse.class)
        )
    )
)
~~~

Đừng đặt @Schema(type = "array") rồi bỏ qua schema của phần tử nếu client cần biết cấu trúc item. Với object lồng nhau, dùng DTO riêng để mô tả từng phần dữ liệu; springdoc có thể tái sử dụng chúng bằng $ref.

## 10. Jackson và tên property trong schema

Jackson quyết định cách Java object được chuyển thành JSON. Các annotation như @JsonProperty, @JsonIgnore, @JsonAlias, @JsonFormat, @JsonInclude và naming strategy có thể ảnh hưởng tên hoặc sự hiện diện của property trong JSON.

Ví dụ:

~~~java
public class CustomerResponse {

    @JsonProperty("customer_id")
    @Schema(description = "Mã khách hàng", example = "C-1024")
    private String id;

    @JsonProperty("display_name")
    @Schema(description = "Tên hiển thị", example = "Nguyen An")
    private String name;

    @JsonIgnore
    private String internalNote;

    // getters và setters
}
~~~

Schema công khai nên phản ánh tên JSON như customer_id và display_name. internalNote được Jackson bỏ qua khi serialize, vì vậy không nên xuất hiện như property công khai trong response schema. Khi cần kiểm soát tên hoặc cách biểu diễn, hãy kiểm tra kết quả OpenAPI thực tế vì vị trí annotation trên field/getter và cấu hình ObjectMapper có thể ảnh hưởng model resolution.

@Schema không thay thế Jackson. Ví dụ, đổi description hoặc example không làm JSON đổi tên property. Ngược lại, @JsonProperty có thể thay tên JSON nhưng không tự cung cấp mô tả nghiệp vụ.

## 11. Ẩn schema hoặc property và giới hạn của việc ẩn

@Schema(hidden = true) có thể dùng để loại một schema hoặc property khỏi tài liệu trong trường hợp phù hợp:

~~~java
public record InternalBookData(
    UUID id,
    String title,
    @Schema(hidden = true)
    String internalClassification
) {}
~~~

Ẩn khỏi OpenAPI chỉ thay đổi tài liệu. Nó không ngăn Jackson serialize property, không xóa dữ liệu khỏi response và không bảo vệ endpoint. Nếu dữ liệu không được phép xuất hiện trong response, hãy dùng DTO phù hợp, cấu hình Jackson đúng và kiểm thử payload thực tế. Không xem hidden là biện pháp bảo mật.

## 12. Các lỗi thường gặp khi dùng @Schema

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Schema không có description | Annotation đặt ở member không được model resolver nhận diện hoặc thiếu annotation | Đặt trên field/getter/record component phù hợp và kiểm tra JSON |
| Property bị thiếu trong tài liệu | Jackson bỏ qua property hoặc schema bị hidden | Kiểm tra @JsonIgnore, visibility và @Schema(hidden) |
| Tên component thay đổi ngoài dự kiến | Tên class hoặc cấu hình model resolution thay đổi | Dùng @Schema(name = "...") khi cần tên ổn định |
| required không như mong muốn | Suy luận từ Bean Validation hoặc requiredMode khác ý định | Đặt requiredMode tường minh và kiểm tra phiên bản OpenAPI |
| Example sai kiểu | Giá trị ví dụ không tương thích schema | Sửa example và xác minh JSON/YAML |
| Giới hạn trong tài liệu khác validation runtime | @Schema và Bean Validation không đồng bộ | Đồng bộ constraint và kiểm thử validation |
| Parameter HTTP không bind dù schema đúng | Chỉ khai báo @Schema/@Parameter, thiếu annotation Spring MVC phù hợp | Sửa @RequestParam, @PathVariable, @RequestHeader hoặc @CookieValue |
| Schema hiển thị kiểu sai so với JSON | Ghi đè type/format không đúng với serializer | Đối chiếu payload thật và cấu hình Jackson |
| Trường nhạy cảm vẫn xuất hiện trong response | Chỉ dùng hidden hoặc writeOnly trong tài liệu | Loại trường khỏi DTO response hoặc cấu hình serializer, rồi kiểm thử |

## 13. Kiểm tra schema được springdoc sinh ra

Sau khi chạy ứng dụng, mở endpoint OpenAPI JSON thường là **/v3/api-docs**; nếu bật YAML, có thể kiểm tra **/v3/api-docs.yaml**. Swagger UI thường được cung cấp tại **/swagger-ui/index.html** hoặc đường dẫn đã cấu hình.

Với mỗi DTO hoặc parameter quan trọng, hãy kiểm tra:

1. **Tên schema:** components/schemas có tên ổn định và duy nhất không?
2. **Mô tả:** description và title có giải thích đúng ý nghĩa nghiệp vụ không?
3. **Property:** tên property có khớp JSON sau khi Jackson serialize không?
4. **Kiểu và format:** string, integer, number, boolean, object, array và format có đúng không?
5. **Ràng buộc:** required, enum, minimum, maximum, minLength, maxLength và pattern có phản ánh hợp đồng không?
6. **Hướng dữ liệu:** readOnly/writeOnly có đúng với request và response không?
7. **Tham số operation:** name, in, required và schema có đồng bộ với annotation Spring MVC không?
8. **Payload runtime:** request/response thực tế có tuân theo schema và ví dụ không?

Ví dụ kiểm tra nhanh schema bằng jq:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.CreateBookRequest'
~~~

Kiểm tra parameter của một operation:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/books/search"].get.parameters'
~~~

Nếu Swagger UI hiển thị sai, hãy kiểm tra JSON trước. Swagger UI trình bày tài liệu được sinh ra; nó không tự sửa schema sai và cũng không chứng minh payload runtime tương thích.

## 14. Quy tắc chọn đúng annotation

| Nhu cầu | Annotation phù hợp |
|---|---|
| Đặt tên và mô tả model DTO | @Schema trên class hoặc record |
| Mô tả property, example, enum, giới hạn | @Schema trên field, getter hoặc record component |
| Mô tả query/path/header/cookie parameter | @Parameter; dùng @Schema lồng bên trong để mô tả kiểu |
| Quyết định vị trí bind của query/path/header/cookie | @RequestParam, @PathVariable, @RequestHeader, @CookieValue |
| Bind dữ liệu JSON body | @RequestBody của Spring MVC |
| Mô tả request body trong OpenAPI | RequestBody của swagger-annotations, @Content và @Schema |
| Mô tả response schema | @ApiResponse, @Content và @Schema |
| Mô tả mảng hoặc phần tử collection | @ArraySchema cùng @Schema |
| Thực thi kiểm tra dữ liệu | Bean Validation và @Valid/@Validated theo cấu hình |

Khi thông tin được suy ra chính xác từ kiểu Java và annotation Spring, không cần thêm @Schema cho mọi property. Chỉ bổ sung metadata khi nó giúp hợp đồng rõ ràng hơn hoặc cần kiểm soát một chi tiết mà suy luận mặc định chưa thể hiện đúng.

## Kết luận

**@Schema** mô tả cấu trúc dữ liệu ở nhiều cấp: trên class để đặt tên và giải thích model; trên property để mô tả kiểu, ví dụ, ràng buộc và hướng dữ liệu; bên trong **@Parameter** để mô tả schema của một giá trị HTTP. Spring MVC quyết định dữ liệu được bind từ đâu, @Parameter mô tả parameter của operation, còn @Schema mô tả hình dạng dữ liệu. Hãy đồng bộ metadata OpenAPI với Jackson, Bean Validation và payload thực tế, rồi kiểm tra JSON/YAML tại /v3/api-docs để bảo đảm hợp đồng chính xác.
