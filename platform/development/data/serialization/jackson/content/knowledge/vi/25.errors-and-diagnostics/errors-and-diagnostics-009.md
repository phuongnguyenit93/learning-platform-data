# Phân biệt cấu hình sai và dữ liệu đầu vào sai

Khi Jackson không đọc được JSON thành object Java, lỗi có thể đến từ hai phía rất khác nhau: payload không đáp ứng hợp đồng dữ liệu, hoặc ứng dụng cấu hình Jackson không đúng với kiểu Java và định dạng wire đang sử dụng. Nếu phân loại nhầm, hệ thống có thể trả lỗi 400 cho một lỗi triển khai phía server, hoặc báo lỗi cấu hình trong khi client thực sự gửi dữ liệu sai.

Ví dụ, JSON thiếu dấu ngoặc là lỗi cú pháp của dữ liệu. JSON hợp lệ nhưng gửi một object vào nơi DTO yêu cầu array là lỗi không khớp hình dạng đầu vào. Ngược lại, nếu DTO dùng LocalDate nhưng ObjectMapper chưa đăng ký module hỗ trợ Java Time, payload có thể hoàn toàn hợp lệ mà ứng dụng vẫn không deserialize được. Nếu class không có creator phù hợp hoặc mapper đăng ký serializer sai, đó thường là vấn đề cấu hình hoặc mô hình Java.

Cách chẩn đoán đáng tin cậy là xem lỗi xuất hiện ở giai đoạn nào, exception cụ thể là gì, đường dẫn property nào bị lỗi, mapper thực tế được cấu hình ra sao và cùng payload đó có parse được thành JsonNode hay không. Không nên kết luận chỉ từ một thông báo lỗi hoặc tên exception chung.

## 1. Hai nhóm nguyên nhân cần phân biệt

Có thể chia nguyên nhân thành hai nhóm chính:

**Dữ liệu đầu vào sai hoặc không phù hợp hợp đồng**

- JSON sai cú pháp: thiếu dấu phẩy, dấu nháy, dấu ngoặc hoặc token không hợp lệ.
- JSON bị cắt dở khi truyền hoặc đọc file.
- Root có hình dạng không đúng: gửi array trong khi endpoint mong object.
- Property có kiểu không đúng: chuỗi thay vì số, object thay vì array.
- Giá trị không thể chuyển đổi: enum không tồn tại, ngày sai định dạng, số vượt phạm vi.
- Thiếu field bắt buộc, gửi explicit null hoặc gửi field lạ trong hợp đồng strict.
- Dữ liệu parse được nhưng vi phạm ràng buộc nghiệp vụ.

**Cấu hình Jackson hoặc mô hình Java sai**

- Thiếu module cần thiết, ví dụ module hỗ trợ kiểu ngày giờ Java.
- DTO không có constructor, creator hoặc property visibility phù hợp.
- Đăng ký nhầm serializer/deserializer hoặc đăng ký vào ObjectMapper không được endpoint sử dụng.
- Naming strategy, mix-in hoặc annotation khiến tên wire không khớp dự kiến.
- Cấu hình coercion, null, unknown property hoặc polymorphic type không phù hợp hợp đồng.
- Phiên bản các artifact Jackson không tương thích.
- Custom serializer/deserializer có lỗi triển khai.
- Kiểu Java trừu tượng không có mapping hoặc subtype information phù hợp.

Ranh giới giữa hai nhóm đôi khi phụ thuộc hợp đồng. Ví dụ, field status nhận chuỗi "archived" nhưng enum Java chỉ có ACTIVE và INACTIVE: có thể client gửi giá trị không được hỗ trợ, hoặc server đang chạy DTO cũ hơn phiên bản API. Exception cho biết điểm thất bại; phiên bản schema và cấu hình mới giúp xác định bên nào cần sửa.

## 2. Hiểu các giai đoạn xử lý JSON

Một request thường đi qua các bước:

~~~text
Byte / String / InputStream
          |
          v
JSON parsing (Jackson Core)
          |
          v
JsonToken / JsonNode
          |
          v
Databinding (Jackson Databind)
          |
          v
Java object / DTO
          |
          v
Bean Validation
          |
          v
Business logic
~~~

Mỗi giai đoạn có một loại lỗi điển hình:

| Giai đoạn | Ví dụ lỗi | Hướng điều tra |
|---|---|---|
| Đọc nguồn | IOException, timeout, connection reset | File, socket, HTTP framing, transport |
| Parse JSON | JsonParseException, JsonEOFException | Cú pháp, encoding, payload bị cắt |
| Mapping | MismatchedInputException, InvalidFormatException | Kiểu token, shape, giá trị và kiểu đích |
| Định nghĩa mapping | InvalidDefinitionException | DTO, creator, serializer, module, cấu hình |
| Tạo object | ValueInstantiationException | Constructor/factory, exception bên trong, dữ liệu truyền vào |
| Validation | ConstraintViolationException hoặc lỗi validation ứng dụng | Ràng buộc nghiệp vụ sau khi binding |
| Nghiệp vụ | Exception của domain/service | Quy tắc xử lý sau khi có object |

Đây là bản đồ chẩn đoán, không phải quy tắc phân loại tuyệt đối. Một số exception có thể xuất hiện trong nhiều tình huống. Cần xem nguyên nhân gốc, vị trí lỗi và cấu hình thực tế.

## 3. JsonParseException: lỗi cú pháp ở tầng parser

JsonParseException thuộc Jackson Core và thường cho biết parser không thể diễn giải input theo cú pháp JSON.

Ví dụ thiếu dấu phẩy:

~~~json
{
  "id": 10
  "name": "Linh"
}
~~~

Ví dụ chuỗi chưa đóng:

~~~json
{
  "name": "Linh
}
~~~

Ví dụ token không hợp lệ:

~~~text
{"active": truX}
~~~

Những lỗi này xảy ra trước khi Jackson cần biết DTO đích là class nào. Nếu cùng một payload được parse bằng readTree() cũng thất bại, khả năng cao vấn đề nằm ở cú pháp hoặc byte nguồn.

Có thể bắt lỗi parse:

~~~java
try {
    JsonNode root = mapper.readTree(input);
} catch (JsonParseException exception) {
    // JSON không hợp lệ theo cú pháp parser.
    log.warn("Malformed JSON", exception);
}
~~~

JsonEOFException là một dạng JsonParseException dành cho trường hợp nguồn kết thúc khi parser vẫn cần thêm dữ liệu để hoàn tất token hoặc cấu trúc. Nó thường gợi ý payload bị cắt, stream bị kết thúc sớm hoặc producer chưa ghi xong.

Không nên biến mọi JsonParseException thành "client gửi JSON sai" mà chưa kiểm tra transport. Ví dụ, file upload có thể bị truncate do lỗi lưu trữ; HTTP connection có thể bị đóng giữa chừng. Khi đó, cần điều tra cả tầng nhận dữ liệu.

## 4. JsonMappingException: JSON parse được nhưng mapping gặp vấn đề

Sau khi parser hiểu được cú pháp JSON, Databind phải ánh xạ token vào kiểu Java. Các lỗi trong giai đoạn này thường nằm dưới JsonMappingException.

Ví dụ DTO yêu cầu quantity là int:

~~~java
public record OrderRequest(int quantity) {}
~~~

Input:

~~~json
{
  "quantity": {
    "value": 2
  }
}
~~~

JSON hợp lệ, nhưng object không thể ánh xạ thành int. Jackson có thể ném MismatchedInputException, một nhánh của JsonMappingException.

Một ví dụ khác:

~~~json
{
  "quantity": "two"
}
~~~

JSON vẫn hợp lệ về cú pháp, nhưng chuỗi "two" không thể chuyển thành int theo quy tắc mapping hiện tại. Đây là lỗi dữ liệu so với kiểu đích hoặc coercion policy.

Tuy nhiên, nếu endpoint đáng lẽ nhận một DTO khác có quantity là object, lỗi có thể do server chọn sai target type. Vì vậy, khi gặp JsonMappingException, hãy kiểm tra cả payload lẫn kiểu đích mà endpoint thực sự dùng.

## 5. Những exception thường gặp và cách diễn giải

| Exception | Thường chỉ ra | Cần kiểm tra |
|---|---|---|
| JsonParseException | Cú pháp JSON không hợp lệ | Token, dấu ngoặc, dấu nháy, encoding, EOF |
| JsonEOFException | Nguồn kết thúc quá sớm trong cú pháp | Truncation, stream, file/message framing |
| MismatchedInputException | Input shape/type không phù hợp kiểu đích | JSON token, DTO/reader target, coercion |
| InvalidFormatException | Giá trị không chuyển được sang kiểu đích | Enum, date, number, format, range |
| UnrecognizedPropertyException | Có field không được DTO nhận diện khi strict | Tên field, version DTO, naming strategy, unknown-field policy |
| InvalidDefinitionException | Jackson không có định nghĩa mapping dùng được | Creator, serializer, abstract type, module, annotation |
| ValueInstantiationException | Constructor/factory/creator thất bại | Cause bên trong, validation trong constructor, dữ liệu |
| IOException | Đọc hoặc ghi nguồn gặp lỗi | File, network, permission, stream lifecycle |

Các exception cụ thể và thông báo có thể thay đổi theo phiên bản Jackson. Đừng viết logic nghiệp vụ phụ thuộc vào một câu message cố định; hãy ưu tiên exception type, path, location và cause.

## 6. MismatchedInputException: kiểm tra cả dữ liệu và target type

MismatchedInputException thường xuất hiện khi token hoặc cấu trúc input không phù hợp kiểu Java đích.

Ví dụ mong object:

~~~java
public record CustomerRequest(String name) {}
~~~

Nhưng client gửi:

~~~json
["Linh", "Minh"]
~~~

Parser đọc được một array hợp lệ. Databind không thể ánh xạ array thành CustomerRequest theo cấu hình thông thường.

Cần đặt ba câu hỏi:

1. API contract có yêu cầu object hay array?
2. Client có gửi đúng endpoint và đúng phiên bản payload không?
3. Endpoint có đang dùng đúng DTO hoặc generic type không?

Ví dụ lỗi target type do generic bị mất:

~~~java
List<UserResponse> users = mapper.readValue(
    json,
    new TypeReference<List<UserResponse>>() {}
);
~~~

Nếu code thay bằng List.class, Jackson không còn thông tin kiểu UserResponse cho phần tử. Kết quả có thể là các Map hoặc kiểu dữ liệu tổng quát, rồi lỗi xuất hiện ở bước cast sau đó. Đây là lỗi khai báo kiểu đích, không phải JSON sai cú pháp.

Một số MismatchedInputException là lỗi input rõ ràng; một số khác lộ ra cấu hình hoặc lựa chọn target type sai. Hãy xác minh contract trước khi kết luận.

## 7. InvalidFormatException: token đúng loại nhưng giá trị không hợp lệ

InvalidFormatException thường dùng khi Jackson đã đọc được một scalar nhưng không thể chuyển giá trị sang kiểu đích.

Ví dụ enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}

public record OrderRequest(OrderStatus status) {}
~~~

Input:

~~~json
{
  "status": "ARCHIVED"
}
~~~

JSON hợp lệ và status là chuỗi, nhưng enum không có hằng ARCHIVED. Nguyên nhân có thể là client gửi giá trị ngoài contract hoặc server đang dùng enum chưa cập nhật.

Ví dụ ngày:

~~~java
public record EventRequest(LocalDate eventDate) {}
~~~

Input:

~~~json
{
  "eventDate": "31/12/2026"
}
~~~

Nếu format được mong đợi là ISO yyyy-MM-dd, giá trị trên không phù hợp. Nhưng nếu contract thật sự yêu cầu dd/MM/yyyy, cần cấu hình @JsonFormat hoặc JavaTime module/formatter phù hợp. Khi đó lỗi nằm ở sự không thống nhất giữa wire contract và cấu hình.

Ví dụ số vượt phạm vi:

~~~json
{
  "age": 999999999999999
}
~~~

Nếu kiểu đích là int, giá trị có thể vượt phạm vi. Cần xác nhận miền dữ liệu và kiểu Java trước khi điều chỉnh coercion.

Không nên bắt InvalidFormatException rồi mặc định giá trị 0, enum mặc định hoặc ngày hiện tại. Cách đó che mất dữ liệu sai và có thể làm sai nghiệp vụ.

## 8. UnrecognizedPropertyException: field lạ không luôn có nghĩa client sai

Ví dụ DTO chỉ có id và name:

~~~java
public record UserRequest(long id, String name) {}
~~~

Input:

~~~json
{
  "id": 10,
  "name": "Linh",
  "nickname": "linh10"
}
~~~

Nếu FAIL_ON_UNKNOWN_PROPERTIES đang bật, Jackson có thể ném UnrecognizedPropertyException cho nickname.

Có ít nhất ba khả năng:

- Client gửi field ngoài hợp đồng.
- Client và server đang dùng hai phiên bản schema khác nhau.
- Server dùng DTO hoặc naming strategy không đúng với endpoint.

Nếu API có chủ đích cho phép producer thêm field mới, có thể bỏ qua unknown fields hoặc giữ chúng dưới dạng JsonNode/Map. Nếu hợp đồng cần strict validation, từ chối field lạ là hợp lý.

Cấu hình:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Hoặc bỏ qua field không biết cho một kiểu:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record UserRequest(long id, String name) {}
~~~

Đây là quyết định tương thích schema. Đừng tắt strict mode toàn cục chỉ để che một lỗi mismatch cụ thể mà chưa xác định chính sách API.

## 9. InvalidDefinitionException: dấu hiệu mạnh của lỗi định nghĩa hoặc cấu hình

InvalidDefinitionException thường xuất hiện khi Jackson không thể xây dựng một serializer/deserializer phù hợp cho kiểu được yêu cầu.

Một số nguyên nhân thường gặp:

- Kiểu Java không có cách tạo instance mà Jackson hiểu.
- Kiểu trừu tượng hoặc interface không có subtype/default implementation phù hợp.
- Thiếu serializer cho kiểu đặc biệt.
- Module cần thiết chưa được đăng ký.
- Annotation hoặc property definition mâu thuẫn.
- Custom serializer/deserializer không được cấu hình đúng.
- Class/module không tương thích với phiên bản Jackson đang chạy.

Ví dụ kiểu Java thời gian:

~~~java
public record EventResponse(LocalDate eventDate) {}
~~~

Nếu ứng dụng chưa có module hỗ trợ Java Time phù hợp, serialize/deserialize LocalDate có thể thất bại với thông báo yêu cầu thêm jackson-datatype-jsr310.

Cấu hình điển hình:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();
~~~

Trong nhiều cấu hình framework, module có thể được tự động đăng ký nếu dependency và auto-configuration phù hợp. Hãy kiểm tra mapper thực tế thay vì tạo một mapper thử nghiệm hoàn toàn khác.

Nếu lỗi xuất hiện ngay cả khi serialize một object Java được tạo từ code với dữ liệu cố định, khả năng cao vấn đề nằm ở kiểu Java hoặc cấu hình serializer hơn là payload đầu vào.

## 10. Thiếu constructor, creator hoặc property mapping

Jackson cần một cách tạo object đích. Với POJO mutable, cách phổ biến là constructor không tham số rồi gán setter/field. Với immutable class hoặc record, Jackson cần creator phù hợp.

Ví dụ class không có creator mà Jackson có thể sử dụng:

~~~java
public class ApiKey {
    private final String value;

    public ApiKey(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Tùy phiên bản, metadata parameter name và cấu hình, Jackson có thể không biết phải bind JSON property nào vào constructor parameter.

Có thể khai báo creator rõ:

~~~java
public class ApiKey {
    private final String value;

    @JsonCreator
    public ApiKey(@JsonProperty("value") String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Nếu lỗi xảy ra với mọi payload hợp lệ của kiểu này, hãy xem xét creator/property definition. Nếu chỉ một payload có field thiếu hoặc null gây lỗi, có thể đó là dữ liệu không đáp ứng yêu cầu của creator.

Các feature sau có thể làm chính sách creator strict hơn:

- FAIL_ON_MISSING_CREATOR_PROPERTIES: từ chối creator property bị thiếu.
- FAIL_ON_NULL_CREATOR_PROPERTIES: từ chối creator property nhận null.
- FAIL_ON_NULL_FOR_PRIMITIVES: từ chối null cho primitive.

Bật các feature này có thể khiến payload cũ bắt đầu thất bại. Đó có thể là thay đổi chính sách có chủ đích, nhưng cần kiểm tra compatibility trước khi triển khai.

## 11. Naming strategy và annotation có thể làm sai tên property

Giả sử JSON gửi:

~~~json
{
  "user_id": 10
}
~~~

DTO:

~~~java
public record UserRequest(long userId) {}
~~~

Nếu mapper không dùng SNAKE_CASE và DTO không có @JsonProperty, Jackson có thể tìm property userId thay vì user_id. Khi strict unknown property được bật, lỗi có thể xuất hiện như field không nhận diện; khi không strict, giá trị có thể bị bỏ qua và userId nhận giá trị mặc định.

Có thể cấu hình naming strategy:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Hoặc khai báo wire name trực tiếp:

~~~java
public record UserRequest(
    @JsonProperty("user_id") long userId
) {}
~~~

Nếu JSON contract đúng theo tài liệu nhưng mọi request đều báo unknown property, hãy kiểm tra mapper có đang dùng đúng naming strategy và mix-in không. Đừng yêu cầu client đổi tên field chỉ vì một mapper riêng trong test đang dùng cấu hình khác production.

## 12. Coercion policy: lỗi có thể do quy tắc chuyển đổi của mapper

Jackson có các feature quyết định có cho phép một số kiểu chuyển đổi hay không.

Ví dụ ACCEPT_FLOAT_AS_INT điều khiển việc chuyển token floating-point sang kiểu nguyên. Nếu bật, một số giá trị có thể bị cắt phần lẻ; nếu tắt, token float có thể bị từ chối.

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();
~~~

Input:

~~~json
{
  "quantity": 2.5
}
~~~

Nếu quantity là int, lỗi mapping trong trường hợp strict mode có thể phản ánh chính sách coercion. JSON vẫn hợp lệ về cú pháp.

Các policy khác có thể liên quan đến:

- Chuỗi rỗng chuyển thành null hoặc empty value.
- Chuỗi số được phép chuyển thành number hay không.
- Null vào primitive.
- Boolean hoặc number bị ép sang kiểu khác.
- Enum nhận giá trị không khớp.

Khi payload trước đây chạy được nhưng bắt đầu thất bại sau khi đổi ObjectMapper feature, hãy so sánh cấu hình cũ và mới. Đó có thể là một thay đổi tương thích của mapper chứ không phải producer đột nhiên gửi JSON sai.

## 13. Module thiếu hoặc sai phiên bản

Một kiểu Java có thể cần module riêng. Ví dụ phổ biến:

- JavaTimeModule cho java.time.
- ParameterNamesModule trong một số trường hợp cần suy luận tên constructor parameter.
- Jdk8Module cho một số kiểu thuộc Java 8 như Optional.
- Module của thư viện bên thứ ba hoặc custom module nội bộ.

Nếu module chưa được đăng ký, Jackson có thể không biết cách serialize/deserialize kiểu đó hoặc dùng một cách xử lý không đúng mong muốn.

Cấu hình thủ công:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();
~~~

Hoặc đăng ký module:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
~~~

Trong dự án có dependency management, nên giữ jackson-core, jackson-annotations, jackson-databind và các jackson-datatype module ở phiên bản tương thích. Không trộn tùy tiện nhiều version khác nhau.

Nếu lỗi chỉ xuất hiện ở một môi trường, kiểm tra dependency tree, classpath thực tế và cách framework tạo mapper. Một unit test dùng classpath đầy đủ có thể thành công trong khi ứng dụng đóng gói thiếu module lúc chạy.

## 14. Serialization failure thường không phải lỗi JSON đầu vào

Cần phân biệt chiều đọc và chiều ghi.

**Deserialize** nhận JSON rồi tạo object Java. Lỗi có thể do cú pháp, dữ liệu, kiểu đích hoặc cấu hình deserializer.

**Serialize** nhận object Java rồi ghi JSON. Không có JSON input để đổ lỗi. Lỗi thường liên quan đến kiểu Java, getter, custom serializer, module hoặc trạng thái object.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(value);
~~~

Nếu value chứa kiểu không có serializer phù hợp, lỗi có thể là InvalidDefinitionException. Nếu custom getter ném exception, Jackson có thể bọc lỗi mapping với cause bên trong.

Với lỗi serialize, hãy kiểm tra:

- Kiểu runtime thực tế của object và nested properties.
- Serializer được chọn cho từng kiểu.
- Module và mix-in đã đăng ký.
- Getter hoặc custom serializer có ném lỗi không.
- Object graph có vòng tham chiếu không.
- Lazy property có kích hoạt truy vấn hoặc lỗi session không.

Không nên trả lỗi "invalid JSON request" cho một lỗi serialize phía server. Đây thường là lỗi server hoặc model/configuration cần được điều tra nội bộ.

## 15. ValueInstantiationException: xem cause trước khi kết luận

ValueInstantiationException cho biết Jackson đã cố tạo giá trị nhưng constructor, factory method hoặc creator thất bại.

Ví dụ:

~~~java
public record Age(int value) {
    public Age {
        if (value < 0) {
            throw new IllegalArgumentException("Age must not be negative");
        }
    }
}
~~~

Input:

~~~json
{
  "value": -2
}
~~~

Jackson có thể parse và chuyển -2 thành int, nhưng constructor từ chối vì quy tắc domain. Đây là dữ liệu không hợp lệ theo invariant của Age.

Tuy nhiên, nếu constructor luôn ném exception do một lỗi triển khai hoặc thiếu dependency, nguyên nhân lại thuộc server.

Khi gặp ValueInstantiationException:

1. Đọc original message.
2. Xem getCause() hoặc exception chain.
3. Xác định constructor/factory nào thất bại.
4. Kiểm tra giá trị truyền vào có vi phạm invariant hay không.
5. Kiểm tra lỗi có lặp lại với payload hợp lệ đã biết hay không.

Không nên chỉ nhìn ValueInstantiationException rồi tự động trả 400. Cause mới cho biết lỗi do dữ liệu hay code tạo object.

## 16. Dùng JsonLocation và path để tìm chính xác field lỗi

Jackson thường cung cấp vị trí parse và đường dẫn property liên quan đến lỗi mapping.

~~~java
try {
    OrderRequest request = mapper.readValue(json, OrderRequest.class);
} catch (JsonProcessingException exception) {
    JsonLocation location = exception.getLocation();

    log.warn(
        "Jackson failure: type={}, line={}, column={}, path={}",
        exception.getClass().getSimpleName(),
        location == null ? null : location.getLineNr(),
        location == null ? null : location.getColumnNr(),
        exception instanceof JsonMappingException mapping
            ? mapping.getPathReference()
            : null
    );

    throw exception;
}
~~~

Path có thể chỉ ra lỗi ở:

~~~text
OrderRequest["items"]->java.util.ArrayList[2]->ItemRequest["quantity"]
~~~

Nhờ đó, có thể biết lỗi nằm ở phần tử thứ ba trong items, field quantity.

Một số API hữu ích:

- JsonProcessingException.getLocation() lấy vị trí parser nếu có.
- JsonMappingException.getPath() lấy các path reference.
- JsonMappingException.getPathReference() tạo chuỗi mô tả đường dẫn.
- JsonMappingException.getOriginalMessage() lấy thông báo gốc chưa thêm path.
- Throwable.getCause() tìm exception gốc.

Với input từ Reader hoặc parser không giữ byte offset, byte offset có thể không hữu ích. Line/column hoặc path vẫn giúp điều tra.

Không phải mọi lỗi cấu hình đều có path. InvalidDefinitionException có thể chỉ ra kiểu class hoặc property definition bị lỗi thay vì vị trí trong JSON.

## 17. Một quy trình chẩn đoán có hệ thống

Khi production gặp lỗi Jackson, hãy đi theo thứ tự:

**Bước 1: Xác định chiều xử lý.**

Lỗi xảy ra khi đọc JSON (readValue/treeToValue) hay ghi object (writeValueAsString/writeValue)? Nếu là serialize, loại trừ giả thuyết JSON request sai.

**Bước 2: Xác định giai đoạn.**

Có parse được JSON thành JsonNode không? Nếu readTree() thất bại, xem cú pháp, encoding và transport. Nếu readTree() thành công nhưng binding thất bại, chuyển sang kiểm tra DTO và Databind.

**Bước 3: Ghi nhận exception cụ thể.**

Phân biệt JsonParseException, JsonEOFException, MismatchedInputException, InvalidFormatException, UnrecognizedPropertyException, InvalidDefinitionException và ValueInstantiationException. Giữ nguyên cause.

**Bước 4: Đọc path và location.**

Xác định field, index hoặc kiểu đích tại vị trí lỗi. Đừng chỉ đọc dòng đầu của stack trace.

**Bước 5: Xác nhận target type.**

Kiểm tra endpoint thực sự dùng DTO nào, JavaType nào, generic type có bị mất không và mapper có đọc đúng root shape không.

**Bước 6: Kiểm tra cấu hình mapper thực tế.**

Xem naming strategy, modules, mix-ins, annotations, visibility, creator, coercion, null policy, unknown property policy và custom handlers.

**Bước 7: Thử payload chuẩn đã biết.**

Dùng một JSON mẫu hợp lệ đã được version hóa. Nếu payload chuẩn cũng thất bại với mapper production, nghiêng về cấu hình hoặc model. Nếu payload chuẩn thành công nhưng payload lỗi thất bại, so sánh dữ liệu theo contract.

**Bước 8: Phân loại lỗi cho đúng tầng.**

Lỗi client có thể trả 400/422 theo API contract. Lỗi mapper/model/config phía server cần được ghi nhận như lỗi server, thường là 500, và có cảnh báo vận hành phù hợp.

Không có một exception đơn lẻ nào thay thế toàn bộ quy trình này.

## 18. So sánh cùng payload trên hai mapper

Một cách hữu ích để khoanh vùng là thử payload trên mapper production và một mapper tối giản đã biết rõ cấu hình. Tuy nhiên, kết quả chỉ có ý nghĩa nếu target type và dependency tương đương.

Ví dụ:

~~~java
ObjectMapper productionMapper = configuredMapper;

ObjectMapper baselineMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();

JsonNode parsedByProduction =
    productionMapper.readTree(payload);

JsonNode parsedByBaseline =
    baselineMapper.readTree(payload);
~~~

Nếu cả hai mapper không parse được, khả năng payload sai cú pháp hoặc byte nguồn hỏng.

Nếu cả hai parse được nhưng chỉ mapper production binding thất bại, so sánh cấu hình custom của production: naming strategy, modules, mix-ins, coercion và strictness.

Nếu cả hai đều thất bại ở cùng field, kiểm tra kiểu dữ liệu thực tế và contract. Tuy nhiên, baseline không phải nguồn chân lý nếu nó thiếu module hoặc policy bắt buộc. Không sửa production chỉ để làm cho payload vượt qua một mapper thử nghiệm dễ dãi hơn.

Một test tốt hơn là dựng mapper từ đúng factory/configuration của ứng dụng và dùng fixture JSON đã được contract xác nhận.

## 19. Kiểm thử cấu hình bằng payload chuẩn

Nên có smoke test để xác nhận mapper được cấu hình đúng trước khi xử lý request thật.

Ví dụ:

~~~java
class JacksonConfigurationTest {

    private final ObjectMapper mapper = applicationObjectMapper();

    @Test
    void readsKnownValidPayload() throws Exception {
        String json = """
            {
              "eventDate": "2026-11-12",
              "amount": 1250.50
            }
            """;

        EventRequest request =
            mapper.readValue(json, EventRequest.class);

        assertEquals(LocalDate.of(2026, 11, 12), request.eventDate());
        assertEquals(new BigDecimal("1250.50"), request.amount());
    }

    @Test
    void writesKnownTypeUsingExpectedWireFormat() throws Exception {
        EventResponse response = new EventResponse(
            LocalDate.of(2026, 11, 12),
            new BigDecimal("1250.50")
        );

        String json = mapper.writeValueAsString(response);

        JsonNode tree = mapper.readTree(json);

        assertEquals("2026-11-12", tree.path("eventDate").asText());
        assertEquals(
            new BigDecimal("1250.50"),
            tree.path("amount").decimalValue()
        );
    }
}
~~~

applicationObjectMapper() đại diện cho factory hoặc bean cấu hình thực tế của ứng dụng. Không nên thay bằng new ObjectMapper() nếu production có module hoặc feature riêng.

Ngoài fixture hợp lệ, cần test payload sai theo contract:

- Sai root shape.
- Sai token type.
- Enum không được hỗ trợ.
- Ngày sai format.
- Field thiếu/null.
- Unknown field theo chính sách.
- Duplicate key nếu yêu cầu strict.
- Number vượt phạm vi.
- JSON bị cắt dở.

Hai nhóm test trả lời hai câu hỏi khác nhau: mapper có hoạt động đúng với dữ liệu chuẩn không, và mapper có từ chối dữ liệu không hợp lệ theo đúng policy không.

## 20. Đừng biến lỗi cấu hình thành lỗi client

Trong API server, phân loại exception ảnh hưởng trực tiếp status code và khả năng retry.

Một hướng xử lý thường gặp:

| Loại lỗi | Phản hồi thường cân nhắc | Hành động vận hành |
|---|---|---|
| JSON syntax sai từ client | 400 Bad Request | Ghi nhận request invalid, không retry cùng payload |
| Field/shape/value sai contract | 400 hoặc 422 | Trả lỗi field rõ ràng |
| JSON bị cắt do client disconnect | Có thể không gửi được response | Ghi log transport, correlation id |
| InvalidDefinitionException do server | 500 Internal Server Error | Cảnh báo và sửa cấu hình/model |
| Serializer/deserializer custom bị lỗi | Thường là 500 nếu lỗi code/config | Điều tra code, module và regression |
| Lỗi I/O từ upstream | Tùy gateway/service contract | Retry có giới hạn nếu lỗi tạm thời |
| Bean Validation thất bại | 400 hoặc 422 theo API | Trả violations đã chuẩn hóa |

Không nên trả stack trace, tên class nội bộ hoặc cấu hình mapper cho client. Phản hồi công khai nên có error code, field/path và thông điệp an toàn. Log nội bộ có thể giữ exception đầy đủ cùng correlation id.

Một số lỗi như unknown property có thể là 400 theo policy strict, nhưng nếu producer và consumer lệch version do rollout không tương thích, cần điều tra quy trình phát hành schema thay vì chỉ yêu cầu client sửa payload.

## 21. Logging an toàn khi chẩn đoán

Payload JSON có thể chứa access token, email, số điện thoại, dữ liệu tài chính hoặc thông tin cá nhân. Không nên ghi toàn bộ raw payload vào log chỉ để tìm lỗi Jackson.

Nên ghi:

- Correlation/request id.
- Exception class.
- JsonLocation nếu có.
- Mapping path nếu có.
- Kiểu đích hoặc endpoint contract.
- Phiên bản ứng dụng và phiên bản Jackson.
- Tên mapper/configuration profile nếu có.
- Kích thước payload hoặc content type khi hữu ích.

Tránh ghi:

- Toàn bộ raw request body.
- Secret, token, password hoặc dữ liệu định danh nhạy cảm.
- Exception message có chứa giá trị input nếu chưa được kiểm tra.
- Stack trace vào response công khai.

Nếu cần giữ mẫu payload để tái hiện, hãy dùng fixture đã ẩn danh hoặc dữ liệu synthetic. Nếu log giá trị cụ thể là cần thiết, chỉ ghi field không nhạy cảm và theo chính sách lưu trữ của hệ thống.

## 22. Một ví dụ phân loại lỗi hoàn chỉnh

Giả sử endpoint nhận:

~~~java
public record CreateOrderRequest(
    String orderId,
    int quantity,
    LocalDate deliveryDate
) {}
~~~

Mapper cần hỗ trợ Java Time:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();
~~~

Xét các payload:

| Payload | Nhóm lỗi/kết quả | Diễn giải |
|---|---|---|
| {"orderId":"O-1","quantity":2,"deliveryDate":"2026-11-12"} | Hợp lệ | Token và format phù hợp. |
| {"orderId":"O-1","quantity":2.5,"deliveryDate":"2026-11-12"} | Mapping error | Float không được chấp nhận cho int theo policy. |
| {"orderId":"O-1","quantity":"two","deliveryDate":"2026-11-12"} | Mapping/format error | Chuỗi không chuyển được thành int. |
| {"orderId":"O-1","quantity":2,"deliveryDate":"12/11/2026"} | Format error | Ngày không theo format được mapper chấp nhận. |
| {"orderId":"O-1","quantity":2,"deliveryDate":"2026-11-12","debug":true} | Unknown property error | Strict policy từ chối field debug. |
| {"orderId":"O-1","quantity":2,"deliveryDate":"2026-11-12" | Parse/EOF error | Object chưa được đóng. |

Nếu mọi payload đều thất bại ở deliveryDate với thông báo không hỗ trợ LocalDate, hãy kiểm tra JavaTimeModule. Nếu chỉ payload dùng format ngày khác thất bại, hãy xác định contract và cấu hình @JsonFormat/formatter. Hai tình huống có biểu hiện gần nhau nhưng cách sửa khác nhau.

## 23. Checklist điều tra nhanh

Khi gặp lỗi, hãy ghi nhận các câu trả lời sau:

| Câu hỏi | Dấu hiệu nghiêng về dữ liệu | Dấu hiệu nghiêng về cấu hình |
|---|---|---|
| readTree() có parse được không? | Không: cú pháp/transport | Có nhưng binding thất bại |
| Payload chuẩn có chạy không? | Payload lỗi riêng lẻ thất bại | Payload chuẩn cũng thất bại |
| Chỉ một giá trị cụ thể lỗi? | Enum, date, range, token | Có thể policy/config mismatch |
| Mọi request của một kiểu đều lỗi? | Ít khả năng là từng payload riêng | DTO, creator, module, serializer |
| Chỉ một môi trường lỗi? | Có thể dữ liệu môi trường khác | Dependency/classpath/config khác |
| Lỗi xảy ra khi serialize object Java? | Không có JSON input | Model, serializer, module, object graph |
| Path trỏ vào field nào? | Field/value cụ thể sai | Có thể tên property hoặc target mapping sai |
| Cause là gì? | Giá trị vi phạm invariant | Constructor/custom handler có lỗi code |

Bảng này hỗ trợ khoanh vùng, không thay thế việc xác nhận contract. Một thay đổi mapper có thể khiến cùng payload chuyển từ hợp lệ sang không hợp lệ; một payload mới cũng có thể phơi bày một cấu hình vốn chưa được kiểm thử.

## Kết luận

Muốn phân biệt cấu hình Jackson sai với dữ liệu đầu vào sai, hãy xác định lỗi xảy ra ở tầng đọc nguồn, parse, databinding, tạo object hay validation. JsonParseException thường chỉ ra cú pháp; MismatchedInputException và InvalidFormatException chỉ ra vấn đề khi ánh xạ token/giá trị vào kiểu đích; InvalidDefinitionException thường hướng đến DTO, module hoặc serializer; ValueInstantiationException cần xem cause của constructor/factory. Nhưng exception type không phải bằng chứng duy nhất.

Hãy parse thử thành JsonNode, kiểm tra target type, path/location, cause và mapper production thực tế. Dùng payload chuẩn để smoke test cấu hình, test payload sai theo contract và giữ logging an toàn. Khi phân loại đúng, lỗi dữ liệu có thể được trả về client với thông tin field hữu ích, còn lỗi cấu hình/model phía server được chuyển đến đúng nhóm chịu trách nhiệm sửa.

