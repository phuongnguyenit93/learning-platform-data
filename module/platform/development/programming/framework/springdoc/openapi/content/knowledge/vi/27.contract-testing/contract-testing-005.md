# Xác minh tham số bắt buộc, mặc định và quy tắc tuần tự hóa

Một hợp đồng API cần trả lời chính xác ba câu hỏi: client có phải gửi parameter hoặc request body hay không, server xử lý thế nào khi giá trị bị bỏ qua, và dữ liệu được chuyển thành JSON ra sao. OpenAPI mô tả những quy tắc này qua các thuộc tính như required, default, schema, style, explode, readOnly và writeOnly. Springdoc tạo metadata từ controller, DTO, validation annotation và Jackson, nhưng tài liệu chỉ chính xác khi metadata đó phản ánh hành vi runtime.

Khi kiểm thử hợp đồng, không nên chỉ xác nhận endpoint trả HTTP 200. Cần kiểm tra cả OpenAPI JSON/YAML lẫn request/response thực tế, đặc biệt ở các trường hợp thiếu parameter, dùng giá trị mặc định, gửi array/object và serialize property có tên hoặc định dạng tùy chỉnh.

## 1. Ba cấp độ của thuộc tính required

Trong OpenAPI, required xuất hiện ở nhiều vị trí và có ý nghĩa khác nhau:

| Vị trí | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Parameter.required | Client phải gửi query, path, header hoặc cookie parameter | Query parameter page bắt buộc |
| RequestBody.required | Client phải gửi request body | POST yêu cầu JSON body |
| Schema.required | Property phải xuất hiện bên trong object | CreateBookRequest cần title |

Không được nhầm ba cấp độ này. Một request body có thể bắt buộc nhưng bên trong object chỉ có một số property bắt buộc. Ngược lại, parameter có thể không bắt buộc nhưng nếu client gửi thì giá trị vẫn phải thỏa schema.

Ví dụ:

~~~yaml
paths:
  /api/books:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - title
              properties:
                title:
                  type: string
                subtitle:
                  type: string
~~~

Trong ví dụ, body phải có mặt và property title phải xuất hiện. Property subtitle có thể bị bỏ qua.

## 2. Path parameter luôn bắt buộc

Path parameter là một phần của URL, vì vậy OpenAPI yêu cầu nó có required = true. Ví dụ:

~~~java
@GetMapping("/api/books/{id}")
public BookResponse getBook(@PathVariable long id) {
    return bookService.findById(id);
}
~~~

OpenAPI tương ứng:

~~~yaml
paths:
  /api/books/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
~~~

Không thể mô tả path parameter là optional rồi vẫn giữ nguyên path template có biến {id}. Nếu endpoint có hai cách gọi, chẳng hạn /api/books và /api/books/{id}, hãy mô tả thành hai path/operation riêng.

## 3. Query, header và cookie parameter có thể tùy chọn

Với Spring MVC, các annotation binding quyết định parameter có bắt buộc hay không:

~~~java
@GetMapping("/api/books")
public List<BookResponse> search(
        @RequestParam String q,
        @RequestParam(required = false) String language,
        @RequestHeader(name = "X-Client-Version", required = false) String clientVersion,
        @CookieValue(name = "catalog-view", required = false) String viewMode) {
    return bookService.search(q, language);
}
~~~

Trong ví dụ:

- q bắt buộc vì @RequestParam mặc định có required = true.
- language tùy chọn vì required = false.
- X-Client-Version là header tùy chọn.
- catalog-view là cookie tùy chọn.

Springdoc thường suy ra required từ các annotation binding của Spring. Có thể dùng @Parameter để bổ sung mô tả hoặc điều chỉnh metadata khi cần:

~~~java
@GetMapping("/api/books")
public List<BookResponse> search(
        @Parameter(
            description = "Từ khóa tìm kiếm",
            required = true
        )
        @RequestParam String q,

        @Parameter(
            description = "Ngôn ngữ sách; mặc định là vi",
            required = false
        )
        @RequestParam(required = false) String language) {
    return bookService.search(q, language);
}
~~~

Metadata @Parameter không thay đổi hành vi binding của Spring. Nếu annotation Spring yêu cầu parameter nhưng OpenAPI được tùy chỉnh thành optional, tài liệu sẽ không khớp runtime. Luôn kiểm tra cả controller và document được sinh ra.

Với Optional<T>, nullable type hoặc @Nullable, hãy xác minh Springdoc và Spring MVC diễn giải đúng theo phiên bản dự án. Khi hợp đồng cần rõ ràng, khai báo required tường minh và kiểm tra /v3/api-docs.

## 4. Giá trị mặc định ở runtime bằng defaultValue

Spring MVC cho phép khai báo giá trị mặc định trực tiếp trên annotation binding:

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
    return bookService.findPage(page, size);
}
~~~

Khi client không gửi page, Spring MVC dùng 0. Khi không gửi size, Spring MVC dùng 20. Tham số có defaultValue được xem là không bắt buộc; giá trị mặc định cũng được áp dụng khi parameter có mặt nhưng rỗng theo quy tắc của Spring binding.

OpenAPI nên thể hiện parameter là optional và schema có default tương ứng:

~~~yaml
parameters:
  - name: page
    in: query
    required: false
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    required: false
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
~~~

Nếu Springdoc không suy ra default như mong đợi trong phiên bản đang dùng, có thể bổ sung metadata bằng @Parameter hoặc @Schema:

~~~java
@Parameter(
    description = "Số trang, bắt đầu từ 0",
    schema = @Schema(defaultValue = "0")
)
@RequestParam(defaultValue = "0") @Min(0) int page
~~~

Điều quan trọng là cả hai phần phải thống nhất: Spring binding thực sự dùng 0 và OpenAPI cũng mô tả 0.

## 5. Phân biệt default, example và giá trị runtime

Ba khái niệm này phục vụ mục đích khác nhau:

| Thuộc tính | Mục đích | Có tự thay đổi request runtime không? |
| --- | --- | --- |
| default | Mô tả giá trị mặc định của parameter hoặc schema | Không |
| example | Cung cấp một giá trị mẫu để người tích hợp tham khảo | Không |
| defaultValue của Spring binding | Chọn giá trị server dùng khi input bị thiếu/rỗng theo binding | Có |

Ví dụ:

~~~java
@Parameter(
    description = "Số lượng kết quả mỗi trang",
    example = "50",
    schema = @Schema(defaultValue = "20")
)
@RequestParam(defaultValue = "20") int size
~~~

Trong ví dụ, server dùng 20 khi client bỏ qua size. Example 50 chỉ là giá trị mẫu; nó không thay đổi default runtime.

Chỉ đặt default trong @Schema hoặc @Parameter không làm Spring tự gán giá trị. Nếu controller không có defaultValue, không có logic khởi tạo DTO hoặc service fallback, metadata default có thể khiến client kỳ vọng sai.

Không nên đồng thời đánh dấu parameter required = true và khai báo default mà server dùng khi parameter bị thiếu. Nếu server thực sự chấp nhận thiếu input, hợp đồng nên mô tả parameter là optional. Nếu parameter bắt buộc, client vẫn phải gửi nó dù schema có một giá trị default được mô tả.

## 6. Required và default bên trong request DTO

Với request body là DTO, required trong OpenAPI Schema nói về việc property phải xuất hiện trong JSON object. Có thể dùng Bean Validation và @Schema để mô tả điều đó:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Tên sách",
        requiredMode = Schema.RequiredMode.REQUIRED,
        example = "Spring Boot căn bản"
    )
    String title,

    @Schema(
        description = "Ngôn ngữ; nếu bỏ qua, ứng dụng dùng vi",
        defaultValue = "vi"
    )
    String language,

    @NotNull
    @Schema(
        description = "Có cho phép mượn hay không",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    Boolean borrowable
) {}
~~~

@NotBlank và @NotNull giúp validation runtime từ chối dữ liệu không hợp lệ khi controller kích hoạt validation. requiredMode cung cấp metadata rõ ràng cho OpenAPI. Các constraint và metadata được Springdoc phản ánh tùy loại annotation và phiên bản; hãy kiểm tra schema đầu ra.

defaultValue trong @Schema chỉ mô tả default. Với language, ứng dụng vẫn phải gán giá trị vi bằng constructor, service hoặc logic chuyển đổi nếu muốn hành vi runtime thật sự có default. Nếu thiếu property và không có logic fallback, Java reference type có thể là null.

## 7. Phân biệt required với nullable

Required nói property có phải xuất hiện hay không. Nullable nói giá trị có được phép là null hay không. Hai khái niệm độc lập:

| required | nullable | Ý nghĩa |
| --- | --- | --- |
| true | false | Phải có property và giá trị không được null |
| true | true | Phải có property, nhưng giá trị có thể là null |
| false | false | Có thể bỏ property; nếu gửi thì không được null |
| false | true | Có thể bỏ property hoặc gửi null |

Trong OpenAPI 3.0, nullable thường được thể hiện bằng nullable: true. OpenAPI 3.1 dùng mô hình JSON Schema để mô tả kiểu có null. Cách Springdoc xuất metadata phụ thuộc phiên bản OpenAPI được cấu hình.

Trong Jackson, bỏ property và gửi null không nhất thiết giống nhau. Ví dụ @JsonInclude(NON_NULL) có thể bỏ field null khỏi response JSON; điều đó không tự động làm property thành optional trong request schema. Cần xác định riêng quy tắc deserialization và serialization.

## 8. Quy tắc serialization của query parameter

OpenAPI mô tả cách array và object parameter được mã hóa trong URL bằng style và explode. Giá trị mặc định phụ thuộc vị trí parameter và style:

| Vị trí | Style mặc định | Explode mặc định |
| --- | --- | --- |
| query | form | true |
| path | simple | false |
| header | simple | false |
| cookie | form | true |

Với query parameter kiểu array, form và explode = true thường biểu diễn bằng nhiều lần xuất hiện cùng tên:

~~~text
GET /api/books?tag=java&tag=spring
~~~

Với form và explode = false, các giá trị được nối bằng dấu phẩy:

~~~text
GET /api/books?tag=java,spring
~~~

Ví dụ mô tả tường minh array parameter:

~~~java
@GetMapping("/api/books")
public List<BookResponse> filter(
    @Parameter(
        name = "tag",
        in = ParameterIn.QUERY,
        description = "Các tag cần lọc",
        array = @ArraySchema(schema = @Schema(type = "string"))
    )
    @RequestParam(required = false) List<String> tag) {
    return bookService.filterByTags(tag);
}
~~~

Nếu dùng format comma-separated, hãy khai báo style/explode phù hợp và bảo đảm Spring binding thực sự parse cùng định dạng. Không chỉ thay metadata OpenAPI rồi kỳ vọng Spring tự đổi cách parse request.

Trong ví dụ array ở trên, query parameter dùng mặc định OpenAPI là style form và explode true, nên các giá trị được gửi lặp tên tag. Với swagger-annotations, khi khai báo phần tử array qua thuộc tính array của @Parameter, các thuộc tính style và explode có thể bị bỏ qua; nếu cần một kiểu serialize khác, hãy kiểm tra OpenAPI model đầu ra và tùy biến parameter sau khi Springdoc tạo tài liệu.

## 9. Serialization của object query parameter

OpenAPI hỗ trợ deepObject cho một số query parameter kiểu object. Ví dụ filter:

~~~text
GET /api/books?filter%5Bauthor%5D=linh&filter%5Byear%5D=2025
~~~

Có thể mô tả:

~~~java
@Parameter(
    name = "filter",
    in = ParameterIn.QUERY,
    style = ParameterStyle.DEEPOBJECT,
    explode = Explode.TRUE,
    schema = @Schema(implementation = BookFilter.class)
)
~~~

deepObject là quy tắc serialization của OpenAPI. Spring MVC không tự động bind mọi cấu trúc object lồng nhau theo mọi biến thể deepObject. Cần kiểm tra cơ chế binding thực tế, chẳng hạn @ModelAttribute, custom converter hoặc resolver. Nếu runtime nhận một cấu trúc khác, tài liệu phải phản ánh đúng cách client cần gửi.

Với parameter object hoặc array phức tạp, hãy kiểm tra URL đã percent-encode và xem request thực tế trong integration test. Tránh tự giả định cách mã hóa dấu ngoặc vuông, dấu phẩy hoặc ký tự reserved.

## 10. style, explode và allowReserved

Các thuộc tính serialization thường dùng:

| Thuộc tính | Vai trò |
| --- | --- |
| style | Cách biểu diễn array/object trong parameter |
| explode | Có tách các phần tử thành nhiều cặp name/value hay không |
| allowReserved | Cho phép ký tự reserved xuất hiện không percent-encode trong query value |

allowReserved chỉ áp dụng cho query parameter. Bật thuộc tính này không có nghĩa server bỏ qua quy tắc URL encoding hoặc chấp nhận mọi ký tự ở mọi vị trí. Hãy kiểm tra gateway, servlet container và framework có xử lý cùng một cách.

Nếu không khai báo style/explode, client dùng mặc định của OpenAPI theo vị trí và style. Không cần ghi tường minh mọi default vào annotation; chỉ override khi hợp đồng yêu cầu một cách serialize khác.

## 11. Jackson quyết định tên property trong JSON

OpenAPI schema cần dùng tên property mà client thực sự gửi/nhận sau khi Jackson serialize hoặc deserialize. @JsonProperty có thể đổi tên JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record BookResponse(
    @JsonProperty("book_id")
    Long id,

    @JsonProperty("display_title")
    String title
) {}
~~~

JSON output sẽ dùng book_id và display_title. Springdoc tích hợp metadata Jackson để mô tả tên property; vẫn nên kiểm tra components.schemas trong /v3/api-docs để bảo đảm document khớp với ObjectMapper của ứng dụng.

Nếu dùng naming strategy như SNAKE_CASE ở cấp ObjectMapper, các property có thể đổi tên đồng loạt. Không giả định tên field Java luôn là tên JSON.

## 12. readOnly và writeOnly cho request/response

Một property có thể chỉ xuất hiện trong response hoặc chỉ được client gửi trong request. Jackson cung cấp access mode:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public class UserDto {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private Long id;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    private String password;

    private String displayName;
}
~~~

readOnly phù hợp với property do server tạo như id hoặc createdAt. writeOnly phù hợp với dữ liệu đầu vào không nên trả lại như password. Hãy dùng DTO request và response riêng nếu cấu trúc hai chiều khác nhau đáng kể; cách này giúp hợp đồng dễ hiểu và giảm nguy cơ lộ dữ liệu.

OpenAPI readOnly/writeOnly là metadata của schema. Jackson access mode mới quyết định hành vi serialize/deserialization runtime. Hai phần phải được đồng bộ.

## 13. @JsonInclude và property bị bỏ qua

Jackson có thể bỏ property khỏi JSON output:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record BookDetailResponse(
    @JsonProperty("book_id")
    Long id,
    String title,
    String subtitle
) {}
~~~

Nếu subtitle là null, Jackson có thể không đưa property này vào JSON. Điều đó không đồng nghĩa property không tồn tại trong schema hoặc client không được gửi property đó trong request. @JsonInclude điều khiển serialization; required và nullable điều khiển hợp đồng schema.

Các lựa chọn phổ biến:

| Giá trị | Hành vi |
| --- | --- |
| ALWAYS | Luôn serialize property |
| NON_NULL | Bỏ property có giá trị null |
| NON_EMPTY | Bỏ chuỗi rỗng, collection rỗng hoặc giá trị được xem là empty |
| NON_DEFAULT | Bỏ giá trị bằng default theo quy tắc Jackson |

Nếu API dùng NON_EMPTY hoặc NON_DEFAULT, kiểm tra JSON response thực tế với cả null, chuỗi rỗng, collection rỗng và giá trị mặc định. Không suy ra schema required chỉ từ việc một property có thể bị bỏ khỏi response.

## 14. Định dạng ngày giờ và kiểu dữ liệu

Jackson và module Java Time quyết định cách biểu diễn date/time. Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record BookDateResponse(
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate publishedOn,

    OffsetDateTime updatedAt
) {}
~~~

OpenAPI thường mô tả LocalDate là string format date và OffsetDateTime là string format date-time. Nếu dùng @JsonFormat với pattern tùy chỉnh, kiểm tra schema/example đầu ra và JSON runtime; không giả định format mặc định vẫn đúng.

Với enum, @JsonValue hoặc custom serializer có thể thay đổi giá trị JSON. Schema enum phải liệt kê đúng các chuỗi client thực sự gửi/nhận, không chỉ tên hằng Java.

## 15. @JsonAlias và nhiều tên đầu vào

Jackson có thể chấp nhận tên property thay thế khi deserialize:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CreateBookRequest(
    @JsonProperty("display_title")
    @JsonAlias({"title", "bookTitle"})
    String title
) {}
~~~

Trong ví dụ, runtime có thể chấp nhận display_title, title hoặc bookTitle khi đọc JSON, nhưng khi serialize sẽ dùng tên chính display_title. OpenAPI schema thường mô tả tên chính; alias không phải lúc nào cũng được biểu diễn tự động. Nếu client phụ thuộc alias cũ, hãy ghi rõ trong description hoặc duy trì schema/endpoint tương thích phù hợp.

## 16. Ví dụ tổng hợp: endpoint tìm kiếm có default và array parameter

Controller:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping
    public List<BookResponse> search(
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestParam(required = false) String q,
            @RequestParam(required = false) List<String> tag) {
        return bookService.search(page, size, q, tag);
    }
}
~~~

Hợp đồng dự kiến:

~~~yaml
paths:
  /api/books:
    get:
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: q
          in: query
          required: false
          schema:
            type: string
        - name: tag
          in: query
          required: false
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
~~~

Các request cần được kiểm tra:

~~~http
GET /api/books
GET /api/books?page=2&size=50
GET /api/books?q=spring
GET /api/books?tag=java&tag=spring
~~~

Request đầu tiên dùng page = 0 và size = 20. Request cuối gửi hai giá trị tag theo form/explode. Nếu Spring binding hoặc custom converter của ứng dụng xử lý array khác với ví dụ, cập nhật serialization metadata cho đúng.

## 17. Kiểm thử OpenAPI metadata

Có thể dùng Spring Boot integration test để tải OpenAPI JSON và kiểm tra required/default:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void pageParameterIsOptionalAndHasDefault() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(body);
        JsonNode parameters = spec.at("/paths/~1api~1books/get/parameters");

        JsonNode page = StreamSupport.stream(parameters.spliterator(), false)
            .filter(parameter -> "page".equals(parameter.path("name").asText()))
            .findFirst()
            .orElseThrow();

        assertThat(page.path("required").asBoolean()).isFalse();
        assertThat(page.at("/schema/default").asInt()).isEqualTo(0);
    }
}
~~~

Trong test thực tế, bổ sung import cho MockMvc, ObjectMapper, JsonNode, StreamSupport, AssertJ và các static matcher. Nếu docs được bảo vệ bằng Spring Security, cung cấp test user/authority phù hợp hoặc cấu hình test security riêng.

Có thể kiểm tra request body schema tương tự:

~~~java
JsonNode schema = spec.at("/components/schemas/CreateBookRequest");
JsonNode required = schema.path("required");

assertThat(required.toString()).contains("title");
~~~

Test này giúp phát hiện khi thay annotation hoặc dependency khiến Springdoc đổi metadata required.

## 18. Kiểm thử hành vi runtime và JSON serialization

Kiểm tra tài liệu thôi chưa đủ. Cần xác nhận server thực sự áp dụng default và Jackson tạo JSON đúng:

~~~java
@Test
void missingPagingParametersUseRuntimeDefaults() throws Exception {
    // bookService là mock được inject trong test fixture.
    mockMvc.perform(get("/api/books"))
        .andExpect(status().isOk());

    verify(bookService).search(0, 20, null, null);
}
~~~

Kiểm tra JSON response:

~~~java
@Test
void responseUsesJsonNamesAndOmitsNullProperties() throws Exception {
    BookDetailResponse response = new BookDetailResponse(42L, "Spring Boot", null);

    String json = objectMapper.writeValueAsString(response);

    assertThat(json).contains("\"book_id\"");
    assertThat(json).doesNotContain("subtitle");
}
~~~

Tên property và điều kiện bỏ null trong test phải khớp DTO thực tế của ứng dụng. Với request DTO, nên test cả JSON hợp lệ, thiếu property bắt buộc, giá trị null và alias nếu API hỗ trợ.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Parameter có default nhưng OpenAPI đánh dấu required | Binding metadata hoặc customizer không đồng bộ | Kiểm tra defaultValue, @Parameter.required và document đầu ra |
| OpenAPI ghi default nhưng server không dùng giá trị đó | Chỉ đặt @Schema.defaultValue hoặc @Parameter metadata | Cấu hình default runtime trong binding, DTO hoặc service |
| Body bắt buộc nhưng property lại optional | Nhầm RequestBody.required với Schema.required | Kiểm tra cả requestBody và schema.required |
| Property có thể null nhưng bị mô tả required sai | Nhầm required với nullable | Xác định riêng presence và nullability |
| Array query bị parse sai | style/explode không khớp cách Spring binding đọc request | Kiểm tra URL thực tế và cấu hình serialization |
| Object query không bind được | deepObject chỉ được khai báo trong OpenAPI | Cấu hình @ModelAttribute, converter hoặc resolver phù hợp |
| JSON dùng tên property khác schema | Jackson @JsonProperty hoặc naming strategy đổi tên | Kiểm tra ObjectMapper và components.schemas |
| Response vẫn chứa field null | @JsonInclude chưa áp dụng ở đúng scope | Kiểm tra annotation, mixin và cấu hình ObjectMapper |
| Schema cho phép gửi property chỉ đọc | Thiếu readOnly/writeOnly hoặc DTO request/response dùng chung | Đồng bộ Jackson access và OpenAPI schema |
| Enum hiển thị tên Java thay vì giá trị JSON | Custom serializer hoặc @JsonValue chưa được phản ánh | Kiểm tra JSON thực tế và schema enum |
| Date format trong tài liệu khác runtime | @JsonFormat hoặc Java Time module thay đổi format | Test serialize và đối chiếu schema/example |
| Alias được runtime chấp nhận nhưng không có trong tài liệu | @JsonAlias không được thể hiện tự động | Mô tả alias hoặc duy trì schema tương thích |

## 20. Checklist xác minh hợp đồng

- [ ] Path parameter được đánh dấu required.
- [ ] Query, header và cookie parameter có required đúng với binding runtime.
- [ ] Parameter có default runtime được mô tả là optional và có schema default phù hợp.
- [ ] Default và example không bị dùng thay thế cho nhau.
- [ ] RequestBody.required đúng với việc endpoint có chấp nhận thiếu body hay không.
- [ ] Schema.required phản ánh property bắt buộc trong JSON object.
- [ ] Nullable được kiểm tra riêng với required.
- [ ] style và explode khớp cách client phải serialize array/object parameter.
- [ ] Jackson property naming khớp schema và JSON runtime.
- [ ] readOnly/writeOnly khớp hành vi serialize/deserialization.
- [ ] @JsonInclude và @JsonFormat được kiểm tra với dữ liệu thực tế.
- [ ] Enum và alias phản ánh đúng các giá trị client có thể gửi/nhận.
- [ ] Integration test kiểm tra OpenAPI JSON/YAML.
- [ ] Runtime test kiểm tra default, validation và JSON serialization.

Hợp đồng chính xác phải đồng bộ giữa binding của Spring, metadata OpenAPI và hành vi Jackson. required quyết định client có phải gửi dữ liệu; default mô tả giá trị server dùng khi input bị thiếu; style/explode quyết định cách parameter được mã hóa; còn Jackson quyết định tên và hình dạng JSON. Kiểm tra đồng thời OpenAPI document và request/response runtime giúp phát hiện sớm sai lệch trước khi client tích hợp.

## Tài liệu tham khảo

- [OpenAPI Specification — Parameter Object và serialization](https://spec.openapis.org/oas/v3.1.0#parameter-object)
- [Swagger Core — @Parameter annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Parameter.html)
- [Swagger Core — ParameterStyle enum](https://docs.swagger.io/swagger-core/v2.2.11/apidocs/io/swagger/v3/oas/annotations/enums/ParameterStyle.html)
