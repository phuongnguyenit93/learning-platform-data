# Schema thiếu trường do Jackson, generic hoặc kiểu trả về quá tổng quát

Khi một property xuất hiện trong JSON runtime nhưng biến mất khỏi OpenAPI schema, hoặc ngược lại, cần kiểm tra cả Jackson, kiểu dữ liệu Java và chữ ký method của controller. Springdoc không đọc một JSON response ngẫu nhiên để đoán mọi cấu trúc có thể xảy ra; thư viện phân tích metadata của controller, kiểu trả về, DTO, annotation và mô hình Jackson để xây dựng OpenAPI document.

Ba nhóm nguyên nhân thường gặp:

1. Jackson không xem field là một property có thể serialize/deserialize, hoặc annotation làm đổi tên/ẩn property.
2. Generic type bị mất do raw type, wildcard, Object hoặc kiểu trả về quá tổng quát.
3. Controller khai báo ResponseEntity<?> hoặc Object, hoặc response annotation ghi đè schema bằng một kiểu khác.

Bài này dùng ví dụ Book API để xác định chính xác field mất ở đâu, sửa đúng lớp gây ra sai lệch và viết test để ngăn lỗi quay lại.

## 1. Phân biệt JSON runtime và OpenAPI schema

JSON runtime là dữ liệu server thực sự gửi cho client. OpenAPI schema là hợp đồng mô tả cấu trúc dữ liệu đó. Hai thứ liên quan nhưng được tạo theo hai quy trình khác nhau:

~~~text
Controller return type + DTO + annotations
                 |
                 v
       Springdoc / Swagger Core
                 |
                 v
          OpenAPI schema
                 |
                 v
       /v3/api-docs JSON/YAML

Controller result + Spring ObjectMapper
                 |
                 v
          Jackson serialize
                 |
                 v
          HTTP response JSON
~~~

Một field có thể vắng mặt ở một bên nhưng xuất hiện ở bên còn lại. Ví dụ:

- @Schema(hidden = true) có thể ẩn field trong tài liệu trong khi Jackson vẫn serialize field.
- @JsonIgnore có thể khiến Jackson bỏ field và Springdoc cũng không mô tả field đó.
- @JsonInclude(NON_NULL) có thể bỏ property khỏi một response cụ thể khi giá trị null, nhưng property vẫn tồn tại trong schema.
- ResponseEntity<?> làm mất kiểu cụ thể ở chữ ký controller, dù runtime tình cờ trả về một DTO có nhiều field.

Vì vậy, đừng bắt đầu bằng cách thêm @Schema cho mọi field đang thiếu. Trước tiên hãy xác định JSON runtime và OpenAPI schema đang khác nhau ở điểm nào.

## 2. Quy trình khoanh vùng nhanh

Khi schema thiếu field, thực hiện theo thứ tự:

1. Gọi endpoint thật và lưu JSON response.
2. Dùng chính ObjectMapper do Spring inject để serialize một DTO mẫu.
3. Tải /v3/api-docs và tìm operation cùng response content.
4. Kiểm tra schema được tham chiếu trong components.schemas.
5. So sánh tên property, kiểu dữ liệu và các annotation Jackson trên DTO.
6. Kiểm tra chữ ký return type của controller có giữ generic type cụ thể hay không.
7. Kiểm tra @ApiResponse, @Content, @Schema(implementation = ...) có ghi đè schema tự suy luận hay không.
8. Nếu DTO dùng serializer, mixin, JsonView hoặc JsonUnwrapped, tạo một test tối thiểu cho đúng cấu hình đó.

Kết quả của bước 3 và 4 giúp phân biệt hai tình huống:

| Quan sát trong /v3/api-docs | Hướng điều tra |
| --- | --- |
| Field không có trong components.schemas | Jackson visibility/annotation, model converter, kiểu property hoặc DTO |
| Field có trong components.schemas nhưng response không tham chiếu schema đó | Return type, generic wrapper, @ApiResponse hoặc @Content |
| Response có $ref nhưng trỏ đến schema khác | Generic bị mất, tên schema trùng hoặc implementation override |
| OpenAPI JSON có field nhưng Swagger UI không hiển thị | Kiểm tra $ref, document có hợp lệ không và UI đang tải đúng URL hay không |
| JSON runtime có field nhưng schema không có | Jackson/runtime mapper và model introspection của Springdoc chưa đồng bộ |
| Schema có field nhưng JSON runtime không có | Giá trị null, @JsonInclude, @JsonView, @JsonIgnore hoặc serializer runtime |

## 3. Kiểm tra JSON runtime bằng ObjectMapper của Spring

Không tạo một ObjectMapper mới trong test để kiểm tra DTO. ObjectMapper tự tạo có thể thiếu module Java Time, Kotlin module, naming strategy, mixin hoặc cấu hình mà ứng dụng thật đang dùng.

Hãy inject mapper do Spring quản lý:

~~~java
import java.math.BigDecimal;

@SpringBootTest
class BookSerializationTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesBookUsingPublicJsonNames() throws Exception {
        BookResponse response = new BookResponse();
        response.setId(42L);
        response.setTitle("Spring Boot");
        response.setPrice(new BigDecimal("250000"));

        String json = objectMapper.writeValueAsString(response);

        assertThat(json).contains("\"book_code\"");
        assertThat(json).contains("\"title\"");
        assertThat(json).doesNotContain("internalNote");
    }
}
~~~

Ví dụ trên giả định BookResponse có property id được đổi tên thành book_code và internalNote không được công bố. Hãy dùng DTO cùng cấu hình thật của ứng dụng để kết quả có ý nghĩa.

Nếu JSON runtime đã thiếu field, tập trung vào Jackson trước. Nếu JSON runtime có field nhưng OpenAPI thiếu, chuyển sang kiểm tra model introspection, generic và response mapping.

## 4. Jackson quyết định property nào được nhìn thấy

Jackson xây dựng logical property từ field, getter, setter, constructor parameter và annotation. Tùy visibility/configuration, một field Java không nhất thiết trở thành một property JSON.

Ví dụ DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;

@Schema(name = "BookResponse")
public class BookResponse {

    @JsonProperty("book_code")
    private Long id;

    private String title;

    private BigDecimal price;

    @JsonIgnore
    private String internalNote;

    public BookResponse() {}

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public String getInternalNote() { return internalNote; }
    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
~~~

Theo mặc định, Jackson thường nhận diện getter/setter theo JavaBean naming convention. Nếu dự án đổi visibility hoặc dùng kiểu accessor khác, property có thể không được phát hiện giống như mong đợi.

## 5. @JsonProperty đổi tên property

@JsonProperty cho phép chỉ định tên JSON khác tên field Java:

~~~java
public class CustomerResponse {

    @JsonProperty("customer_id")
    private Long id;

    @JsonProperty("display_name")
    private String name;
}
~~~

JSON runtime sẽ dùng customer_id và display_name. OpenAPI schema cũng cần mô tả đúng tên mà client nhìn thấy.

Nếu schema vẫn hiện id trong khi JSON trả customer_id, hãy kiểm tra:

- @JsonProperty được đặt trên field, getter hay constructor parameter nào.
- Có getter/setter khác mang annotation mâu thuẫn không.
- Có Jackson mixin hoặc naming strategy cấp ObjectMapper ghi đè không.
- Có @Schema(name = ...) đặt tên khác với JSON property không.

Không dùng @Schema(name = "customer_id") để che giấu một cấu hình Jackson sai. @Schema chỉ điều chỉnh tài liệu; Jackson mới quyết định tên JSON runtime.

## 6. @JsonIgnore và @JsonIgnoreProperties

@JsonIgnore đánh dấu logical property cần bị loại khỏi quá trình introspection serialize/deserialize:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class UserResponse {

    private Long id;
    private String username;

    @JsonIgnore
    private String passwordHash;
}
~~~

passwordHash không nên xuất hiện trong JSON công khai và cũng không nên được đưa vào schema response.

@JsonIgnoreProperties có thể loại bỏ một hoặc nhiều property:

~~~java
@JsonIgnoreProperties({"internalNote", "legacyCode"})
public class BookResponse {
    @JsonProperty
    private Long id;
    @JsonProperty
    private String title;
    @JsonProperty
    private String internalNote;
    @JsonProperty
    private String legacyCode;
}
~~~

Phân biệt:

| Annotation | Tác động chính |
| --- | --- |
| @JsonIgnore | Bỏ logical property khỏi Jackson serialization/deserialization |
| @JsonIgnoreProperties(value = ...) | Bỏ các property được chỉ định khỏi Jackson introspection |
| @Schema(hidden = true) | Ẩn property trong OpenAPI documentation |

Nếu chỉ muốn ẩn một field khỏi tài liệu nhưng vẫn giữ JSON runtime, dùng @Schema(hidden = true). Nếu field chứa dữ liệu bí mật, cần bảo đảm Jackson không serialize field đó; chỉ ẩn khỏi Swagger UI là chưa đủ.

## 7. @JsonInclude không đồng nghĩa với xóa field khỏi schema

@JsonInclude điều khiển khi nào Jackson đưa property vào JSON:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class BookResponse {
    @JsonProperty
    private Long id;
    @JsonProperty
    private String title;
    @JsonProperty
    private String subtitle;
}
~~~

Nếu subtitle là null, JSON response có thể bỏ property subtitle. Khi subtitle có giá trị, property vẫn xuất hiện.

Một số mode thường gặp:

| Mode | Hành vi |
| --- | --- |
| ALWAYS | Luôn serialize property |
| NON_NULL | Bỏ property có giá trị null |
| NON_EMPTY | Bỏ chuỗi rỗng, collection rỗng hoặc giá trị empty theo Jackson |
| NON_DEFAULT | Bỏ giá trị bằng default theo quy tắc Jackson |

Nếu schema thiếu hoàn toàn subtitle trong khi runtime đôi khi có subtitle, hãy kiểm tra @Schema(hidden), @JsonIgnore và visibility. Nếu chỉ một response thiếu subtitle vì giá trị null, @JsonInclude có thể là nguyên nhân bình thường.

## 8. readOnly và writeOnly cho request/response

Một property có thể được gửi vào request nhưng không được trả về response, hoặc ngược lại. Jackson và OpenAPI có metadata riêng để mô tả điều này:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public class AccountDto {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private Long id;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    private String password;

    private String displayName;
}
~~~

READ_ONLY phù hợp với id hoặc createdAt do server tạo. WRITE_ONLY phù hợp với password hoặc secret đầu vào. OpenAPI dùng readOnly/writeOnly để mô tả chiều sử dụng; Jackson access mode quyết định hành vi serialize/deserialization runtime.

Nếu cùng một DTO được dùng cho request và response, hãy kiểm tra schema của cả hai operation. Với API lớn, DTO request và response riêng thường dễ kiểm soát hơn một model dùng chung có nhiều property chỉ đọc/chỉ ghi.

## 9. Naming strategy và visibility của ObjectMapper

Spring Boot có thể cấu hình naming strategy để đổi tên property hàng loạt, ví dụ SNAKE_CASE:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
~~~

Khi đó Java field displayName có thể được serialize thành display_name. OpenAPI cần phản ánh tên sau naming strategy.

Cũng cần rà soát các cấu hình:

- Visibility của field/getter/setter qua @JsonAutoDetect hoặc ObjectMapper configuration.
- Jackson mixin đăng ký bằng application configuration.
- Custom PropertyNamingStrategy.
- Module bổ sung serializer/deserializer.
- Lombok getter và annotation processing.
- Fluent accessor như getName() so với name().

Nếu Lombok tạo getter nhưng annotation processing bị tắt trong một module, Jackson và Springdoc có thể nhìn thấy model khác với dự kiến. Với fluent accessor không theo chuẩn JavaBean, hãy dùng @JsonProperty tường minh hoặc cấu hình visibility rõ ràng.

Không tạo ObjectMapper riêng chỉ để sửa schema. Cấu hình mapper của ứng dụng qua Spring bean hoặc Jackson module được đăng ký thống nhất để serialization và schema introspection có cơ hội dùng cùng metadata.

## 10. Record, Kotlin data class và accessor

Jackson hiện đại hỗ trợ Java record và Kotlin data class thông qua module tương ứng. Tuy nhiên, phiên bản Jackson, module Kotlin và cấu hình visibility phải tương thích.

Java record:

~~~java
public record BookRecord(
    @JsonProperty("book_code") Long id,
    String title,
    BigDecimal price
) {}
~~~

Kotlin data class:

~~~kotlin
data class BookResponse(
    @JsonProperty("book_code")
    val id: Long,
    val title: String,
    val price: BigDecimal
)
~~~

Nếu record hoặc Kotlin property bị thiếu:

1. Xác nhận ứng dụng đang dùng Jackson version do Spring Boot quản lý.
2. Kiểm tra jackson-module-kotlin nếu dùng Kotlin.
3. Kiểm tra annotation được đặt trên component/property đúng target.
4. Serialize một instance bằng ObjectMapper của Spring.
5. Kiểm tra OpenAPI component schema riêng.

Đừng thêm một phiên bản Jackson khác chỉ để làm cho một record hoạt động nếu chưa kiểm tra dependency management. Các module Jackson lệch version có thể gây lỗi linkage hoặc hành vi introspection khác nhau.

## 11. @JsonUnwrapped có thể làm thay đổi cấu trúc JSON

@JsonUnwrapped yêu cầu Jackson đưa property của object lồng nhau lên object cha:

~~~java
public class Address {
    @JsonProperty
    private String city;
    @JsonProperty
    private String country;
}

public class CustomerResponse {
    @JsonProperty
    private Long id;

    @JsonProperty
    @JsonUnwrapped
    private Address address;
}
~~~

JSON có thể trở thành:

~~~json
{
  "id": 7,
  "city": "Da Nang",
  "country": "VN"
}
~~~

Thay vì một property address chứa object lồng nhau, JSON có city và country ở cấp ngoài. Đây là một cấu trúc khác với Java object graph ban đầu.

Khi dùng @JsonUnwrapped, hãy so sánh JSON runtime với schema. Nếu phiên bản Springdoc/Swagger Core không mô tả được cấu trúc flatten đúng như mong muốn, cân nhắc:

- Tạo DTO response phẳng có property city/country.
- Khai báo schema chuyên biệt bằng @Schema(implementation = ...).
- Viết ModelConverter/customizer cho kiểu dùng chung nếu nhiều endpoint có cùng quy tắc.

Không dùng @Schema(implementation = Address.class) cho property đã unwrapped nếu điều đó làm tài liệu quay lại cấu trúc address lồng nhau trong khi JSON runtime không có object address.

## 12. @JsonView tạo các góc nhìn schema khác nhau

Một DTO có thể serialize khác nhau tùy JsonView:

~~~java
public class Views {
    public interface Public {}
    public interface Internal extends Public {}
}

public class UserResponse {

    @JsonProperty
    @JsonView(Views.Public.class)
    private Long id;

    @JsonProperty
    @JsonView(Views.Public.class)
    private String displayName;

    @JsonProperty
    @JsonView(Views.Internal.class)
    private String riskScore;
}
~~~

Endpoint public và endpoint internal có thể trả cùng class nhưng tập property khác nhau. Nếu dùng JsonView, kiểm tra annotation trên controller và cách Springdoc xử lý view cho từng operation.

Nếu hai view tạo ra hai hợp đồng khác nhau đáng kể, DTO riêng thường rõ ràng hơn. Nếu giữ JsonView, hãy viết integration test riêng cho từng endpoint để bảo đảm schema không vô tình công bố property nội bộ.

## 13. Custom serializer và deserializer

Khi dùng JsonSerializer/JsonDeserializer tùy chỉnh, cấu trúc JSON có thể không còn giống field Java:

~~~java
public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeStartObject();
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField("currency", value.currency());
        generator.writeEndObject();
    }
}
~~~

Serializer trên biến Money thành object có amount và currency. Nếu Springdoc chỉ nhìn thấy kiểu Money mà không hiểu serializer, schema có thể thiếu property hoặc mô tả không đúng.

Có ba cách xử lý:

1. Dùng DTO cụ thể cho JSON public thay vì expose domain value object có serializer đặc biệt.
2. Khai báo @Schema(implementation = MoneyDto.class) ở property/response phù hợp.
3. Viết ModelConverter hoặc schema customizer khi kiểu dữ liệu đặc biệt được dùng rộng rãi.

Ví dụ override schema cho property:

~~~java
@Schema(implementation = MoneyDto.class)
@JsonProperty
private Money price;
~~~

Ví dụ override response:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Chi tiết sách",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = BookResponse.class)
    )
)
~~~

@Schema(implementation = ...) chỉ thay đổi mô tả OpenAPI. Nó không làm Jackson serialize object theo class implementation được chỉ định. Hãy bảo đảm class schema mô tả đúng JSON thực tế.

## 14. @JsonValue và enum

Enum có thể serialize thành giá trị khác tên hằng Java:

~~~java
public enum BookStatus {
    AVAILABLE("available"),
    OUT_OF_STOCK("out-of-stock");

    private final String value;

    BookStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
~~~

JSON runtime dùng available hoặc out-of-stock, không dùng AVAILABLE hoặc OUT_OF_STOCK. Schema enum phải phản ánh giá trị mà client thực sự nhìn thấy và gửi vào.

Nếu enum trong Swagger UI hiển thị tên hằng Java, kiểm tra @JsonValue, custom serializer và OpenAPI component schema. Không tự viết example bằng giá trị nội bộ nếu runtime dùng giá trị khác.

## 15. Generic type bị mất khi dùng raw type

Java generic chỉ giúp Springdoc suy ra schema khi chữ ký method giữ được kiểu cụ thể. Ví dụ tốt:

~~~java
@GetMapping("/api/books")
public List<BookResponse> listBooks() {
    return service.findAll();
}
~~~

Springdoc có thể biết phần tử của list là BookResponse.

Các chữ ký quá tổng quát làm mất thông tin:

~~~java
public List listBooks() { ... }

public Object listBooks() { ... }

public ResponseEntity<?> listBooks() { ... }

public ResponseEntity<Object> listBooks() { ... }
~~~

Với những kiểu này, compiler không cung cấp đủ generic type cụ thể để Springdoc xác định property của phần tử. Runtime có thể trả BookResponse, nhưng tài liệu không nên dựa vào giá trị runtime của một request để đoán toàn bộ kiểu trả về.

Hãy giữ kiểu cụ thể:

~~~java
public ResponseEntity<List<BookResponse>> listBooks() { ... }
~~~

Nếu endpoint thực sự trả nhiều kiểu payload tùy điều kiện, hãy mô tả union bằng oneOf/anyOf hoặc các response code/media type riêng thay vì dùng Object không có schema.

## 16. Generic wrapper phải giữ type parameter

Một response wrapper phổ biến:

~~~java
public record ApiEnvelope<T>(
    T data,
    String traceId
) {}
~~~

Controller giữ generic cụ thể:

~~~java
@GetMapping("/api/books/{id}")
public ApiEnvelope<BookResponse> getBook(@PathVariable Long id) {
    return new ApiEnvelope<>(service.findById(id), traceIdProvider.current());
}
~~~

Chữ ký ApiEnvelope<BookResponse> cho biết data có kiểu BookResponse. Nếu đổi thành ApiEnvelope<?> hoặc ApiEnvelope raw type, schema data có thể trở thành object tổng quát và mất các property.

Với collection:

~~~java
public ApiEnvelope<List<BookResponse>> listBooks() { ... }
~~~

Kiểu lồng nhau vẫn cần được giữ đầy đủ. Tránh khai báo raw ApiEnvelope ở interface service hoặc base controller rồi chỉ trả subtype ở implementation; Springdoc có thể phân tích chữ ký method được expose chứ không suy luận mọi implementation runtime.

## 17. ResponseEntity<?> và Object làm response schema quá tổng quát

ResponseEntity không phải nguyên nhân trực tiếp làm mất schema; vấn đề là generic type bên trong:

~~~java
// Giữ được schema cụ thể
public ResponseEntity<BookResponse> getBook() { ... }

// Mất kiểu cụ thể
public ResponseEntity<?> getBook() { ... }

// Mất kiểu cụ thể
public ResponseEntity<Object> getBook() { ... }
~~~

Nếu không thể đổi chữ ký method, khai báo response schema tường minh:

~~~java
@GetMapping("/api/books/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Thông tin sách",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = BookResponse.class)
    )
)
public ResponseEntity<?> getBook(@PathVariable Long id) {
    return ResponseEntity.ok(service.findById(id));
}
~~~

Chỉ dùng cách này khi mọi response 200 thực sự có cấu trúc BookResponse. Nếu method trả nhiều kiểu dữ liệu, mô tả chúng bằng oneOf hoặc tách endpoint/response code rõ ràng.

## 18. Map<String, Object> và JSON động

Map<String, Object> thường tạo schema object có additionalProperties kiểu object vì key và value có thể thay đổi:

~~~java
public Map<String, Object> getStatistics() {
    return Map.of(
        "totalBooks", 120,
        "available", true
    );
}
~~~

Springdoc không thể biết mọi key có thể xuất hiện nếu kiểu khai báo không định nghĩa chúng. Nếu response có cấu trúc ổn định, hãy tạo DTO:

~~~java
public record BookStatistics(
    long totalBooks,
    boolean available
) {}
~~~

Nếu JSON thực sự động, mô tả additionalProperties và example rõ ràng. Không ép một schema cố định lên payload có key tùy ý vì client sẽ hiểu sai hợp đồng.

## 19. Generic wrapper chuyên biệt bằng DTO cụ thể

Nếu generic wrapper gây khó khăn cho tài liệu hoặc cần tên component dễ đọc, tạo DTO chuyên biệt:

~~~java
public record BookEnvelope(
    BookResponse data,
    String traceId
) {}

public record BookListEnvelope(
    List<BookResponse> data,
    String traceId
) {}
~~~

Controller có thể trả BookEnvelope hoặc BookListEnvelope trực tiếp. Cách này lặp một ít cấu trúc nhưng tạo schema tường minh và ổn định.

Nếu vẫn dùng generic wrapper, có thể chỉ định implementation cho response:

~~~java
@ApiResponse(
    responseCode = "200",
    content = @Content(
        schema = @Schema(implementation = BookEnvelope.class)
    )
)
~~~

Schema implementation cần là class cụ thể mô tả đúng data và traceId trong JSON. Không dùng raw ApiEnvelope.class nếu mục tiêu là mô tả BookResponse bên trong data.

## 20. Array response cần mô tả item schema

Với response là danh sách, có thể khai báo array schema tường minh:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sách",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = BookResponse.class)
        )
    )
)
~~~

Đừng đặt BookResponse trực tiếp làm schema của response nếu JSON runtime là một array. Khi đó OpenAPI phải mô tả type array và item schema tương ứng.

Nếu controller trả Page<BookResponse>, đó là một object có content và metadata, không phải array thuần. Chỉ dùng array schema cho List<BookResponse> hoặc JSON array thực tế.

## 21. Ví dụ khi thêm example làm mất schema

Một response có thể cần cả schema và example. Nếu chỉ khai báo examples mà bỏ schema, một số cách viết annotation có thể khiến response content chỉ còn example:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Chi tiết sách",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = BookResponse.class),
        examples = @ExampleObject(
            name = "book",
            value = """
                {
                  "book_code": 42,
                  "title": "Spring Boot"
                }
                """
        )
    )
)
~~~

Khi cần example, giữ cả schema và examples trong cùng @Content. Sau khi thay annotation, kiểm tra response content trong /v3/api-docs để chắc chắn schema không bị mất.

## 22. @Schema(implementation) không sửa JSON runtime

@Schema(implementation = SomeClass.class) hướng dẫn Springdoc mô tả một schema bằng class được chỉ định. Nó không:

- Thay đổi giá trị return của controller.
- Thay đổi Jackson serializer/deserializer.
- Tự thêm property vào JSON runtime.
- Bảo đảm class được chọn khớp với mọi nhánh response.

Ví dụ nếu JSON runtime có { "id": 1, "title": "A" } nhưng implementation class có thêm internalNote, OpenAPI sẽ mô tả sai nếu class đó được dùng trực tiếp. Hãy tạo DTO schema trùng với payload thực tế.

## 23. Inheritance và polymorphism

Nếu response có nhiều subtype, một base class quá tổng quát có thể chỉ hiển thị các property chung. Dùng metadata polymorphism để mô tả các biến thể:

~~~java
@Schema(
    oneOf = {PhysicalBookResponse.class, EbookResponse.class},
    discriminatorProperty = "kind"
)
public interface BookItemResponse {}
~~~

Các subtype:

~~~java
public record PhysicalBookResponse(
    String kind,
    Long id,
    int stockQuantity
) implements BookItemResponse {}

public record EbookResponse(
    String kind,
    Long id,
    String downloadUrl
) implements BookItemResponse {}
~~~

Nếu dùng Jackson @JsonTypeInfo/@JsonSubTypes, bảo đảm discriminator và các subtype trong OpenAPI khớp với giá trị JSON runtime. Nếu chỉ khai báo oneOf nhưng Jackson không serialize discriminator tương ứng, client có thể không phân biệt được biến thể.

## 24. Kiểm tra component schema và response reference

Khi tải /v3/api-docs, tìm:

- paths của operation đang gặp lỗi.
- responses theo status code.
- content theo media type.
- schema hoặc $ref trong response.
- components.schemas chứa định nghĩa component.

Ví dụ response tham chiếu:

~~~yaml
paths:
  /api/books/{id}:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/BookResponse"
components:
  schemas:
    BookResponse:
      type: object
      properties:
        book_code:
          type: integer
          format: int64
        title:
          type: string
~~~

Nếu $ref trỏ đến component đúng nhưng property thiếu, điều tra DTO/Jackson. Nếu component đầy đủ nhưng operation dùng component khác, điều tra chữ ký return type và @ApiResponse override. Nếu $ref không resolve, kiểm tra component name, customizer và dependency version.

## 25. Kiểm tra tên schema trùng nhau

Hai class ở package khác nhau có thể cùng tên đơn giản, ví dụ:

~~~text
com.example.customer.UserResponse
com.example.admin.UserResponse
~~~

Nếu cả hai cùng xuất hiện trong một document, component name đơn giản có thể gây khó phân biệt hoặc xung đột tùy cấu hình/version. Có thể đặt tên schema tường minh:

~~~java
@Schema(name = "CustomerUserResponse")
public class UserResponse { ... }

@Schema(name = "AdminUserResponse")
public class UserResponse { ... }
~~~

Chỉ đổi schema name khi đã kiểm tra toàn bộ $ref và client code generation. Đổi tên component trong OpenAPI có thể ảnh hưởng generated model của client dù JSON runtime không đổi.

## 26. Kiểm tra ObjectMapper, module và mixin

Nếu DTO được serialize đúng trong unit test nhưng OpenAPI vẫn thiếu field, hãy kiểm tra mapper configuration mà Springdoc đang sử dụng:

1. Có nhiều bean ObjectMapper trong context không?
2. Module Java Time/Kotlin/custom module đã được đăng ký chưa?
3. Naming strategy hoặc visibility có được cấu hình qua application.yml không?
4. Mixin có được đăng ký cho class DTO không?
5. Có custom ModelConverter hoặc SpringDocUtils replacement không?
6. Có dependency Jackson bị override lệch version không?

Không đăng ký một mixin riêng trong một ObjectMapper cục bộ rồi kỳ vọng Springdoc tự nhận. Hãy đăng ký cấu hình ở cấp Spring application và xác minh cả mapper runtime lẫn document.

## 27. Test schema và JSON cùng một DTO

Một test tốt kiểm tra cả hai đầu:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BookSchemaContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void jacksonAndOpenApiExposeSameBookProperties() throws Exception {
        BookResponse dto = new BookResponse();
        dto.setId(42L);
        dto.setTitle("Spring Boot");

        String json = objectMapper.writeValueAsString(dto);
        JsonNode runtime = objectMapper.readTree(json);

        assertThat(runtime.has("book_code")).isTrue();
        assertThat(runtime.has("title")).isTrue();
        assertThat(runtime.has("internalNote")).isFalse();

        String specJson = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(specJson);
        JsonNode properties = spec.at(
            "/components/schemas/BookResponse/properties"
        );

        assertThat(properties.has("book_code")).isTrue();
        assertThat(properties.has("title")).isTrue();
        assertThat(properties.has("internalNote")).isFalse();
    }
}
~~~

Test trên giả định BookResponse có setter/getter, schema name là BookResponse và DTO không có property khác. Nếu component name do Springdoc tạo khác, dùng $ref trong response để tìm đúng component thay vì hard-code tên.

## 28. Test response schema giữ generic type

Với wrapper generic, kiểm tra schema của data:

~~~java
JsonNode dataSchema = spec.at(
    "/components/schemas/ApiEnvelopeBookResponse/properties/data"
);

assertThat(dataSchema.path("$ref").asText())
    .contains("BookResponse");
~~~

Tên component generic do Swagger Core/Springdoc đặt có thể thay đổi theo version và cách resolve. Hãy đọc $ref từ response schema trước khi viết assertion cố định.

Nếu wrapper là ApiEnvelope<?> hoặc raw ApiEnvelope, test nên phát hiện data schema không còn tham chiếu BookResponse. Khi đó sửa chữ ký return type hoặc dùng response DTO cụ thể.

## 29. Flowchart chẩn đoán schema thiếu field

~~~mermaid
flowchart TD
    A["Field thiếu trong Swagger UI"] --> B["Đọc /v3/api-docs"]
    B --> C{"Field có trong components.schemas?"}
    C -->|Không| D["Kiểm tra Jackson visibility và annotations"]
    C -->|Có| E{"Response có tham chiếu đúng schema?"}
    E -->|Không| F["Kiểm tra generic return type và @ApiResponse"]
    E -->|Có| G["Kiểm tra $ref, media type và Swagger UI"]
    D --> H["Serialize DTO bằng Spring ObjectMapper"]
    H --> I{"JSON runtime có field?"}
    I -->|Không| J["Sửa Jackson/DTO/serializer"]
    I -->|Có| K["Kiểm tra ModelConverter, mixin và version"]
    F --> L["Giữ generic cụ thể hoặc schema implementation"]
~~~

Flowchart này giúp tránh thay annotation ngẫu nhiên. Mỗi nhánh được xác định bởi một bằng chứng có thể quan sát trong JSON runtime hoặc OpenAPI document.

## 30. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field có trong Java class nhưng không có trong JSON | Jackson không thấy field/getter hoặc bị @JsonIgnore | Kiểm tra visibility, getter, annotation và ObjectMapper |
| JSON có field nhưng OpenAPI thiếu | Jackson model introspection, mixin hoặc converter khác runtime | So sánh mapper Spring và /v3/api-docs; kiểm tra ModelConverter |
| Tên property trong schema khác JSON | @JsonProperty, naming strategy hoặc @Schema(name) mâu thuẫn | Dùng một tên public nhất quán và kiểm tra JSON thực |
| Field null biến mất khỏi response | @JsonInclude(NON_NULL) hoặc NON_EMPTY | Kiểm tra giá trị runtime; không nhầm với schema hidden |
| Property nội bộ xuất hiện trong docs | Thiếu @JsonIgnore hoặc @Schema(hidden) | Loại khỏi JSON và schema theo yêu cầu bảo mật |
| ResponseEntity<?> sinh schema object rỗng | Generic type bị mất | Dùng ResponseEntity<ConcreteDto> hoặc @Schema(implementation) |
| ApiEnvelope raw type mất data fields | Type parameter bị xóa | Khai báo ApiEnvelope<BookResponse> hoặc DTO chuyên biệt |
| Map<String,Object> không có property cụ thể | Schema động, key không biết trước | Dùng DTO hoặc mô tả additionalProperties |
| List response chỉ hiện object tổng quát | Raw List hoặc wildcard | Dùng List<BookResponse> hoặc @ArraySchema |
| Wrapper generic hiển thị sai nested type | Method signature không giữ generic cụ thể | Dùng generic đầy đủ hoặc concrete envelope |
| Field flatten khác JSON | @JsonUnwrapped hoặc custom serializer | So sánh payload, dùng DTO/schema riêng |
| Schema enum hiển thị tên hằng Java | @JsonValue hoặc serializer đổi giá trị | Đồng bộ enum schema với JSON value |
| Một view có field, view khác không | @JsonView hoặc endpoint dùng view khác nhau | Kiểm tra view của controller và schema từng operation |
| Example xuất hiện nhưng schema biến mất | @Content chỉ khai báo examples | Khai báo đồng thời schema và examples |
| $ref trỏ component không đúng | Schema name trùng hoặc customizer ghi đè | Đặt @Schema(name) riêng và kiểm tra mọi $ref |
| Swagger UI không hiện property dù JSON schema có | UI tải document cũ hoặc lỗi resolve $ref | Kiểm tra Network, URL docs và validate OpenAPI JSON |

## 31. Checklist trước khi sửa annotation

- [ ] Đã lưu JSON response thật của endpoint.
- [ ] Đã serialize DTO bằng ObjectMapper do Spring inject.
- [ ] Đã kiểm tra operation và response schema trong /v3/api-docs.
- [ ] Đã tìm component schema tương ứng trong components.schemas.
- [ ] Đã phân biệt field không có trong component với response tham chiếu sai component.
- [ ] Đã rà soát @JsonProperty, @JsonIgnore, @JsonIgnoreProperties và @JsonInclude.
- [ ] Đã kiểm tra readOnly/writeOnly, @JsonView và @JsonUnwrapped nếu có.
- [ ] Đã kiểm tra getter/setter, Lombok, record/Kotlin module và visibility.
- [ ] Đã kiểm tra custom serializer/deserializer, mixin và naming strategy.
- [ ] Return type giữ generic cụ thể, không dùng raw type/Object/wildcard khi có thể tránh.
- [ ] Wrapper generic giữ type parameter ở chữ ký controller.
- [ ] @ApiResponse/@Content/@Schema(implementation) mô tả đúng JSON runtime.
- [ ] Array response dùng item schema; object wrapper dùng schema object.
- [ ] Example được khai báo cùng schema khi cần cả hai.
- [ ] $ref trỏ đến component tồn tại và đúng kiểu.
- [ ] Đã có test so sánh JSON runtime với OpenAPI component schema.
- [ ] Đã kiểm tra dependency Jackson/Swagger Core không bị lệch version.

Schema thiếu trường thường không phải một lỗi đơn lẻ của Swagger UI. Jackson quyết định property và hình dạng JSON; generic type và chữ ký controller quyết định Springdoc có thể suy ra response cụ thể đến đâu; @ApiResponse/@Schema có thể thay đổi schema cuối cùng. Hãy so sánh JSON runtime, components.schemas và response $ref theo đúng thứ tự, sau đó sửa đúng annotation, DTO hoặc return type. Khi test cả serialization lẫn OpenAPI document, lỗi thiếu field sẽ được phát hiện ngay trong quá trình phát triển.

## Tài liệu tham khảo

- [Springdoc OpenAPI FAQ — Jackson, schema và response customization](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ](https://springdoc.org/v2/faq.html)
- [Jackson Annotations — JsonIgnore](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Jackson Annotations — JsonUnwrapped](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonUnwrapped.html)
- [Swagger Core — @Schema annotation](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
