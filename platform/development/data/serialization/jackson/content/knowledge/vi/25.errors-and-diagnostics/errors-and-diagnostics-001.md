# Phân biệt lỗi I/O, lỗi cú pháp và lỗi ánh xạ kiểu

Khi Jackson đọc hoặc ghi JSON, một thao tác có thể thất bại ở nhiều tầng khác nhau. Có lỗi đến từ nguồn hoặc đích dữ liệu như file không mở được, socket bị ngắt hoặc ổ đĩa hết chỗ. Có lỗi do nội dung JSON không đúng cú pháp. Cũng có lỗi khi JSON hợp lệ nhưng không thể chuyển thành kiểu Java mà ứng dụng yêu cầu.

Ba nhóm lỗi này cần cách xử lý khác nhau. Lỗi I/O có thể là sự cố môi trường hoặc kết nối tạm thời; lỗi cú pháp thường cho biết payload không phải JSON hợp lệ; lỗi ánh xạ kiểu thường cho biết cấu trúc hoặc giá trị JSON không phù hợp với mô hình Java, hoặc mô hình Java chưa được cấu hình đúng. Nếu gom tất cả thành một lỗi chung, ứng dụng dễ retry sai, trả sai HTTP status, ghi log thiếu thông tin hoặc che giấu lỗi lập trình.

Điểm quan trọng khi dùng Jackson là các exception JSON thường nằm trong hệ thống kế thừa IOException. Vì vậy, không thể chỉ bắt IOException rồi kết luận mọi lỗi đều là lỗi đọc file hay mạng. Cần bắt các loại exception Jackson cụ thể trước, sau đó mới xử lý IOException còn lại.

## 1. Ba tầng có thể phát sinh lỗi

Một luồng đọc JSON thường gồm ba giai đoạn:

~~~text
Nguồn dữ liệu
   |
   v
Đọc byte / character
   |
   |  Lỗi I/O
   v
JsonParser phân tích cú pháp
   |
   |  Lỗi cú pháp JSON
   v
Databind ánh xạ token vào kiểu Java
   |
   |  Lỗi ánh xạ kiểu
   v
Đối tượng Java
~~~

Ví dụ với lời gọi:

~~~java
User user = mapper.readValue(inputStream, User.class);
~~~

Jackson cần đọc dữ liệu từ inputStream, phân tích nội dung thành token, rồi gán token vào các property của User. Một exception có thể xuất hiện ở bất kỳ bước nào:

- Không đọc được inputStream: lỗi I/O.
- Gặp dấu phẩy, dấu ngoặc hoặc escape sai quy tắc JSON: lỗi cú pháp.
- JSON hợp lệ nhưng một object được gửi vào property int: lỗi ánh xạ kiểu.
- JSON hợp lệ nhưng class User không có creator phù hợp: lỗi định nghĩa kiểu.

Khi ghi JSON, các nhóm lỗi cũng xuất hiện:

- Không ghi được ra OutputStream: lỗi I/O.
- Generator không thể tạo token hợp lệ hoặc serializer gọi generator sai trạng thái: lỗi sinh JSON.
- Serializer không thể ánh xạ một giá trị Java: lỗi ánh xạ/serialization.

Không phải mọi lỗi xảy ra trong cùng một lời gọi readValue hoặc writeValue đều có cùng nguyên nhân. Hãy phân loại theo tầng phát sinh.

## 2. IOException không đồng nghĩa với lỗi I/O thuần túy

Trong Jackson 2.x, các exception liên quan đến JSON được xây dựng trên hệ thống exception của Jackson và có quan hệ với IOException. Một số kiểu quan trọng:

| Exception | Nhóm chính | Ý nghĩa |
|---|---|---|
| IOException | I/O | Lỗi từ nguồn hoặc đích dữ liệu, hoặc một lỗi I/O không được Jackson phân loại cụ thể |
| JsonParseException | Cú pháp/đọc token | Nội dung không thể được phân tích theo cú pháp JSON |
| JsonEOFException | Cú pháp/đọc token | Input kết thúc bất ngờ khi parser còn chờ phần nội dung bắt buộc |
| JsonMappingException | Databind | Lỗi khi ánh xạ giữa JSON và kiểu Java |
| MismatchedInputException | Databind | Token hoặc cấu trúc đầu vào không phù hợp kiểu đích |
| InvalidDefinitionException | Databind/configuration | Jackson không thể sử dụng định nghĩa kiểu hoặc cấu hình serializer/deserializer |
| UnrecognizedPropertyException | Databind | Gặp property không được kiểu Java nhận diện khi cấu hình không cho phép bỏ qua |
| InvalidFormatException | Databind | Giá trị có dạng không thể chuyển sang kiểu đích, ví dụ enum hoặc số |
| InvalidTypeIdException | Databind/polymorphism | Type id không thể được giải quyết thành subtype hợp lệ |
| JsonGenerationException | Sinh JSON | Lỗi trong quá trình tạo token JSON |

JsonParseException và JsonMappingException đều có thể được bắt bằng các kiểu Jackson cụ thể trước khi bắt IOException. Nếu chỉ viết:

~~~java
catch (IOException e) {
    // ...
}
~~~

thì cả lỗi đọc file, lỗi cú pháp JSON và lỗi ánh xạ kiểu có thể đi vào cùng một nhánh. Điều này làm mất khả năng phân biệt nguyên nhân.

Một quy tắc dễ nhớ:

1. Bắt exception chuyên biệt của Jackson trước.
2. Bắt JsonProcessingException chung nếu cần.
3. Bắt IOException còn lại cho lỗi I/O thực sự.

Thứ tự này quan trọng vì các exception Jackson cũng thuộc hệ thống exception có thể được khai báo dưới IOException.

## 3. Lỗi I/O là gì?

Lỗi I/O xảy ra khi ứng dụng không thể đọc nguồn dữ liệu hoặc ghi ra đích dữ liệu. Jackson không kiểm soát được toàn bộ vòng đời của file, socket, stream hay thiết bị.

Ví dụ khi đọc:

- File không tồn tại.
- Tiến trình không có quyền đọc file.
- Đường dẫn trỏ đến thư mục thay vì file.
- Network socket bị reset.
- Kết nối bị timeout.
- Stream đã bị đóng hoặc bị một thành phần khác tiêu thụ.
- Thiết bị lưu trữ phát sinh lỗi.

Ví dụ khi ghi:

- Không có quyền tạo file.
- Ổ đĩa hết dung lượng.
- Socket đóng trong khi ghi response.
- Remote server ngắt kết nối.
- OutputStream đã bị đóng.

Các exception có thể gặp gồm FileNotFoundException, NoSuchFileException, AccessDeniedException, SocketTimeoutException, SocketException, EOFException hoặc IOException tổng quát. Loại cụ thể phụ thuộc nguồn dữ liệu và hệ điều hành.

Ví dụ mở file:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    User user = mapper.readValue(input, User.class);
}
~~~

Nếu path không tồn tại, Files.newInputStream có thể ném NoSuchFileException trước khi Jackson bắt đầu phân tích JSON. Đây là lỗi truy cập nguồn, không phải lỗi cú pháp.

## 4. Lỗi cú pháp JSON là gì?

Lỗi cú pháp xảy ra khi parser gặp nội dung không tuân theo grammar JSON mà Jackson đang chấp nhận.

JSON lỗi:

~~~json
{
  "name": "Mai",
  "age": 25,
}
~~~

Dấu phẩy sau phần tử cuối không hợp lệ trong JSON chuẩn. Nếu parser không bật một extension cho phép trailing comma, nó sẽ báo lỗi phân tích.

Một số trường hợp khác:

~~~json
{ name: "Mai" }
~~~

Tên field không được đặt trong dấu ngoặc kép theo cú pháp JSON chuẩn.

~~~json
{
  "name": "Mai
}
~~~

Chuỗi chưa được đóng.

~~~json
{
  "message": "Line 1
Line 2"
}
~~~

Ký tự xuống dòng thô bên trong JSON string không hợp lệ; cần escape thành newline sequence.

~~~json
{
  "value": 12x
}
~~~

Token số không hợp lệ.

~~~json
{
  "path": "C:\new\file"
}
~~~

Một số escape trong chuỗi không hợp lệ nếu không được viết đúng theo quy tắc JSON. Ví dụ dấu gạch chéo ngược cần được escape khi biểu diễn ký tự backslash.

Jackson thường báo JsonParseException hoặc một subtype liên quan khi parser không thể tiếp tục. Exception thường kèm vị trí lỗi để tìm dòng và cột.

## 5. JsonParseException và JsonEOFException

JsonParseException là loại exception thường gặp khi Jackson Core không thể phân tích nội dung JSON. Ví dụ:

~~~java
String json = """
    {
      "name": "Mai",
      "age": 25,
    }
    """;

try {
    mapper.readValue(json, User.class);
} catch (JsonParseException e) {
    System.out.println(e.getOriginalMessage());
}
~~~

JsonEOFException biểu thị parser gặp kết thúc input bất ngờ trong khi cấu trúc hoặc token hiện tại chưa hoàn tất. Ví dụ:

~~~json
{
  "name": "Mai",
  "address": {
    "city": "Da Nang"
~~~

Object chưa được đóng. Parser đã đọc đến hết nguồn nhưng vẫn chờ các dấu đóng cấu trúc.

Trong một số phiên bản Jackson, JsonEOFException là subtype của JsonParseException. Có thể bắt JsonParseException nếu muốn xử lý chung lỗi cú pháp và EOF không mong đợi; chỉ bắt JsonEOFException riêng khi ứng dụng cần phân biệt input bị cắt cụt với các lỗi grammar khác.

Lưu ý rằng EOF trong JSON không luôn chứng minh producer đã gửi payload sai. Nếu JSON đến từ mạng, một kết nối bị ngắt giữa chừng cũng có thể khiến parser chỉ nhìn thấy một chuỗi byte kết thúc sớm. Về mặt parser, đó là input không hoàn chỉnh; về mặt vận hành, cần đối chiếu Content-Length, framing, checksum hoặc trạng thái giao thức để xác định có phải lỗi truyền tải.

## 6. Lỗi ánh xạ kiểu là gì?

Lỗi ánh xạ xảy ra khi JSON đã được phân tích thành token hợp lệ nhưng Jackson không thể chuyển token đó thành đối tượng Java theo kiểu đích và cấu hình hiện tại.

Ví dụ JSON hợp lệ:

~~~json
{
  "name": "Mai",
  "age": {
    "value": 25
  }
}
~~~

Nếu class Java khai báo:

~~~java
public class User {
    private String name;
    private int age;

    // Getter và setter
}
~~~

JSON trên hợp lệ về cú pháp, nhưng age là object trong khi Java yêu cầu int. Jackson có thể ném MismatchedInputException.

Một ví dụ khác là enum:

~~~java
public enum Role {
    USER,
    ADMIN
}
~~~

JSON:

~~~json
{
  "role": "SUPERUSER"
}
~~~

Nếu không có cấu hình xử lý giá trị enum không biết, Jackson có thể ném InvalidFormatException hoặc một lỗi ánh xạ tương ứng.

Lỗi ánh xạ không nhất thiết có nghĩa JSON sai cú pháp. JSON có thể hoàn toàn hợp lệ nhưng không khớp hợp đồng kiểu Java.

## 7. MismatchedInputException

MismatchedInputException là một dạng JsonMappingException dùng khi input không phù hợp với kiểu dữ liệu Jackson đang cố tạo.

Các ví dụ thường gặp:

- JSON object được đưa vào property số nguyên.
- JSON array được đưa vào một property chỉ nhận object đơn.
- JSON string được đưa vào kiểu không có cách coercion phù hợp.
- Cấu trúc lồng nhau không khớp với kiểu property.
- Input không có giá trị nhưng target yêu cầu một giá trị bắt buộc theo cấu hình.

Ví dụ:

~~~java
public class Request {
    private List<String> tags;
}
~~~

JSON:

~~~json
{
  "tags": {
    "first": "java"
  }
}
~~~

Property tags yêu cầu array/list, nhưng input cung cấp object. Đây là mismatch về cấu trúc.

Có thể bắt riêng:

~~~java
try {
    Request request = mapper.readValue(json, Request.class);
} catch (MismatchedInputException e) {
    // Input JSON không khớp kiểu đích
}
~~~

MismatchedInputException hữu ích khi muốn trả lỗi validation hoặc bad request. Tuy nhiên, không nên mặc định mọi JsonMappingException đều là lỗi do client. Một số lỗi ánh xạ xuất phát từ cấu hình server.

## 8. InvalidDefinitionException

InvalidDefinitionException thường chỉ ra Jackson không thể sử dụng định nghĩa kiểu hoặc cấu hình mapping. Đây thường là lỗi ở phía ứng dụng, mô hình Java hoặc cấu hình, chứ không đơn thuần là payload client sai.

Ví dụ:

- Không có constructor/factory phù hợp để tạo kiểu bất biến.
- Không có serializer cho một kiểu mà Jackson không biết cách ghi.
- Có cấu hình creator hoặc property xung đột.
- Một kiểu abstract/interface không có thông tin subtype hoặc cơ chế tạo đối tượng cần thiết.
- Cấu hình annotation khiến Jackson không xác định được cách ánh xạ.

Ví dụ class:

~~~java
public class ImmutableUser {
    private final String name;

    public ImmutableUser(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Tùy cấu hình, phiên bản Jackson và metadata constructor, Jackson có thể không biết cách tạo ImmutableUser khi đọc JSON. Có thể cần JsonCreator và JsonProperty:

~~~java
public class ImmutableUser {
    private final String name;

    @JsonCreator
    public ImmutableUser(
            @JsonProperty("name") String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Nếu lỗi là InvalidDefinitionException, cần kiểm tra kiểu Java, annotation, module và cấu hình mapper. Chỉ yêu cầu client gửi lại JSON thường không giải quyết được.

## 9. UnrecognizedPropertyException

UnrecognizedPropertyException xảy ra khi JSON có property mà kiểu Java không nhận diện được và mapper được cấu hình để từ chối property lạ.

Ví dụ class:

~~~java
public class User {
    private String name;
    // Không có property age
}
~~~

JSON:

~~~json
{
  "name": "Mai",
  "age": 25
}
~~~

Nếu FAIL_ON_UNKNOWN_PROPERTIES đang bật, Jackson có thể ném UnrecognizedPropertyException.

Ứng dụng có thể chọn chính sách:

- Từ chối field lạ để phát hiện sai schema.
- Bỏ qua field lạ để hỗ trợ producer bổ sung dữ liệu mà consumer chưa dùng.
- Thu thập field mở rộng vào một Map hoặc JsonNode nếu hợp đồng cho phép.

Ví dụ bỏ qua field lạ:

~~~java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Hoặc chỉ áp dụng trên một class:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class User {
    private String name;
}
~~~

Không nên tắt FAIL_ON_UNKNOWN_PROPERTIES toàn cục chỉ để né một lỗi cụ thể nếu các API khác cần kiểm tra schema nghiêm ngặt. Có thể dùng annotation hoặc mapper chuyên biệt cho hợp đồng cần tolerant parsing.

## 10. InvalidFormatException

InvalidFormatException là lỗi ánh xạ khi giá trị đầu vào có hình dạng hoặc nội dung không thể chuyển thành kiểu đích.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

JSON:

~~~json
{
  "status": "SHIPPED"
}
~~~

Nếu SHIPPED không có trong enum và không có cấu hình fallback, Jackson có thể ném InvalidFormatException.

Một trường hợp khác:

~~~json
{
  "quantity": "many"
}
~~~

Nếu quantity là int và coercion không thể chuyển chuỗi many thành số, Jackson báo lỗi định dạng/ánh xạ.

Không nên dựa vào mọi coercion mặc định. Jackson có thể chấp nhận một số chuỗi số hoặc chuyển đổi scalar tùy cấu hình. Nếu hợp đồng yêu cầu nghiêm ngặt, hãy cấu hình coercion và validation rõ ràng.

## 11. InvalidTypeIdException

Với JSON đa hình, Jackson cần type id để chọn subtype. Nếu type id không biết hoặc không được cấu hình, có thể xảy ra InvalidTypeIdException.

Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
}
~~~

JSON:

~~~json
{
  "kind": "crypto",
  "amount": 1000
}
~~~

Nếu crypto không phải subtype được đăng ký, Jackson không thể chọn lớp Java tương ứng. Đây là lỗi ánh xạ đa hình, không phải lỗi cú pháp JSON.

Khi xử lý lỗi này, hãy kiểm tra:

- Producer có gửi type id đúng chính tả không?
- Subtype đã được khai báo bằng JsonSubTypes, JsonTypeName hoặc registerSubtypes chưa?
- Producer và consumer có đang dùng cùng phiên bản schema không?
- Có defaultImpl hay chính sách unknown subtype được chủ đích không?

Không nên cho phép client gửi tên lớp tùy ý để tự động nạp class nhằm tránh lỗi type id.

## 12. ValueInstantiationException

ValueInstantiationException xuất hiện khi Jackson đã xác định cách tạo kiểu nhưng constructor hoặc factory method gặp lỗi trong lúc khởi tạo đối tượng.

Ví dụ:

~~~java
public class Age {
    private final int value;

    @JsonCreator
    public Age(@JsonProperty("value") int value) {
        if (value < 0) {
            throw new IllegalArgumentException("Age must not be negative");
        }
        this.value = value;
    }
}
~~~

JSON:

~~~json
{
  "value": -1
}
~~~

JSON hợp lệ, giá trị có thể ánh xạ sang int, nhưng constructor từ chối dữ liệu theo invariant nghiệp vụ. Jackson có thể bọc lỗi khởi tạo trong ValueInstantiationException hoặc JsonMappingException tương ứng.

Khi bắt lỗi này, nên kiểm tra cause để hiểu constructor/factory đã thất bại vì điều kiện gì. Không nên trả stack trace hoặc thông tin nội bộ của constructor trực tiếp cho client.

## 13. Lỗi sinh JSON khi ghi

Khi serialize, Jackson có thể gặp lỗi ở hai tầng:

1. Databind không thể chuyển object Java thành cấu trúc JSON.
2. Generator không thể tạo token JSON hợp lệ hoặc không thể ghi token xuống output.

Ví dụ serializer:

~~~java
public class UnsafeValueSerializer extends JsonSerializer<String> {

    @Override
    public void serialize(
            String value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeEndObject();
    }
}
~~~

Serializer gọi writeEndObject() khi không có object tương ứng đang mở. Generator có thể báo JsonGenerationException do trạng thái token không hợp lệ.

Trong khi đó, nếu output stream bị đóng hoặc socket bị ngắt khi generator ghi, Jackson có thể nhận IOException từ đích ghi.

Ví dụ:

~~~java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, response);
}
~~~

Nếu quyền ghi bị từ chối hoặc đĩa hết dung lượng, lỗi thuộc tầng I/O. Nếu serializer sai logic, lỗi có thể thuộc tầng mapping hoặc generation.

## 14. JsonProcessingException là lớp chung hữu ích

JsonProcessingException là một lớp exception chung cho nhiều lỗi liên quan đến xử lý JSON. Nó hữu ích khi một tầng ứng dụng muốn báo rằng thao tác JSON thất bại nhưng không cần phân biệt chi tiết ngay tại đó.

Ví dụ:

~~~java
try {
    return mapper.readValue(json, User.class);
} catch (JsonProcessingException e) {
    throw new InvalidPayloadException("Cannot read user JSON", e);
}
~~~

Tuy nhiên, nếu cần quyết định retry, HTTP status hoặc cách log, nên bắt loại cụ thể hơn:

- JsonParseException cho cú pháp.
- JsonMappingException cho mapping.
- InvalidDefinitionException cho cấu hình/type definition.
- IOException còn lại cho nguồn/đích I/O.

JsonProcessingException thường chứa message và location, nhưng không phải mọi subclass đều cung cấp cùng loại chi tiết path. Với mapping exception, nên dùng JsonMappingException để lấy path.

## 15. Thứ tự catch exception đúng

Vì exception Jackson có quan hệ kế thừa với IOException, catch tổng quát đặt trước có thể nuốt các nhánh cụ thể.

Ví dụ sai:

~~~java
try {
    User user = mapper.readValue(input, User.class);
} catch (IOException e) {
    log.error("I/O error", e);
} catch (JsonParseException e) {
    // Không bao giờ đến được đây
}
~~~

Compiler sẽ báo nhánh sau không thể bắt exception đã bị catch bởi nhánh cha, hoặc logic phân loại sẽ sai tùy cấu trúc cụ thể.

Mẫu phân loại:

~~~java
try {
    User user = mapper.readValue(input, User.class);
    return user;
} catch (JsonMappingException e) {
    // JSON đã được đọc nhưng không ánh xạ được vào kiểu Java
    handleMappingError(e);
} catch (JsonParseException e) {
    // Parser không thể đọc cú pháp JSON
    handleSyntaxError(e);
} catch (JsonProcessingException e) {
    // Lỗi xử lý JSON khác chưa được phân loại riêng
    handleJsonProcessingError(e);
} catch (IOException e) {
    // Lỗi I/O còn lại từ nguồn dữ liệu
    handleIoError(e);
}
~~~

JsonMappingException và JsonParseException là các nhánh cụ thể của lỗi xử lý JSON; chúng cần được bắt trước JsonProcessingException chung và IOException.

Nếu ứng dụng dùng phiên bản Jackson có các lớp cụ thể bổ sung như StreamReadException hoặc DatabindException, có thể dùng chúng trong thiết kế catch. Mẫu trên vẫn giúp phân biệt hai nhóm chính trên nhiều phiên bản Jackson 2.x.

## 16. Đọc từ String và đọc từ InputStream khác nhau ở điểm nào?

Khi đọc từ String:

~~~java
User user = mapper.readValue(jsonString, User.class);
~~~

Nguồn dữ liệu đã nằm trong bộ nhớ. Các lỗi thường quan tâm là cú pháp và mapping. Lỗi I/O từ file/socket không nằm trong thao tác đọc String này, dù phương thức vẫn khai báo exception theo API của Jackson.

Khi đọc từ InputStream:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    User user = mapper.readValue(input, User.class);
}
~~~

Ngoài lỗi cú pháp và mapping, thao tác còn có thể thất bại khi đọc nguồn. Files.newInputStream cũng có thể ném lỗi trước khi parser được tạo.

Vì vậy, nếu cần phân loại chính xác, hãy tách việc mở nguồn khỏi việc parse:

~~~java
InputStream input;
try {
    input = Files.newInputStream(path);
} catch (IOException e) {
    throw new SourceAccessException("Cannot open input file", e);
}

try (input) {
    return mapper.readValue(input, User.class);
} catch (JsonMappingException e) {
    throw new InvalidPayloadException("JSON does not match User", e);
} catch (JsonParseException e) {
    throw new InvalidPayloadException("Malformed JSON", e);
} catch (IOException e) {
    throw new SourceReadException("Cannot read JSON source", e);
}
~~~

Việc tách mở nguồn giúp phân biệt rõ file không mở được với nội dung file không phải JSON hợp lệ.

## 17. Đọc từ file: ví dụ phân loại đầy đủ

~~~java
public User readUser(Path path) {
    final InputStream input;

    try {
        input = Files.newInputStream(path);
    } catch (NoSuchFileException e) {
        throw new SourceAccessException(
            "Input file does not exist: " + path,
            e
        );
    } catch (AccessDeniedException e) {
        throw new SourceAccessException(
            "No permission to read input file: " + path,
            e
        );
    } catch (IOException e) {
        throw new SourceAccessException(
            "Cannot open input file: " + path,
            e
        );
    }

    try (input) {
        return mapper.readValue(input, User.class);
    } catch (JsonMappingException e) {
        throw new InvalidPayloadException(
            "Input JSON does not match User",
            e
        );
    } catch (JsonParseException e) {
        throw new InvalidPayloadException(
            "Input is not valid JSON",
            e
        );
    } catch (IOException e) {
        throw new SourceReadException(
            "I/O failure while reading input",
            e
        );
    }
}
~~~

Các exception ứng dụng như SourceAccessException, InvalidPayloadException và SourceReadException cần được định nghĩa theo kiến trúc của dự án. Ví dụ minh họa mục tiêu giữ nguyên cause để tầng trên có thể ghi log hoặc quyết định xử lý.

Nếu lỗi xảy ra trong lúc đóng stream, try-with-resources cũng có thể phát sinh IOException. Cần cân nhắc lỗi chính và lỗi suppressed khi chẩn đoán. Không nên bỏ qua hoàn toàn lỗi đóng tài nguyên trong các luồng xử lý file quan trọng.

## 18. Phân loại lỗi khi ghi JSON ra file

Khi ghi, cần phân biệt mapping/generation với lỗi đích I/O:

~~~java
public void writeReport(Path path, Report report) {
    try (OutputStream output = Files.newOutputStream(path)) {
        mapper.writeValue(output, report);
    } catch (JsonMappingException e) {
        throw new SerializationFailure(
            "Cannot map Report to JSON",
            e
        );
    } catch (JsonGenerationException e) {
        throw new SerializationFailure(
            "Cannot generate valid JSON output",
            e
        );
    } catch (JsonProcessingException e) {
        throw new SerializationFailure(
            "JSON serialization failed",
            e
        );
    } catch (IOException e) {
        throw new DestinationWriteException(
            "Cannot write report file",
            e
        );
    }
}
~~~

Các loại exception cụ thể có thể khác nhau tùy Jackson version và serializer. Mục tiêu là giữ nguyên phân loại:

- Lỗi mapping: object Java không thể được serialize theo cấu hình.
- Lỗi generation: chuỗi token JSON không thể được tạo theo trạng thái generator.
- Lỗi I/O: output không thể được ghi xuống đích.

Trong thực tế, JsonMappingException cũng có thể được dùng cho một số lỗi xảy ra khi serialize. Đừng chỉ dựa vào tên thao tác là writeValue để kết luận lỗi thuộc I/O.

## 19. Chẩn đoán vị trí lỗi cú pháp bằng JsonLocation

JsonParseException thường cung cấp vị trí parser phát hiện lỗi. Có thể lấy:

- Dòng bằng getLineNr().
- Cột bằng getColumnNr().
- Byte offset bằng getByteOffset() khi có.
- Character offset bằng getCharOffset() khi có.

Ví dụ:

~~~java
catch (JsonParseException e) {
    JsonLocation location = e.getLocation();

    if (location != null) {
        log.warn(
            "Malformed JSON at line {}, column {}, byte offset {}",
            location.getLineNr(),
            location.getColumnNr(),
            location.getByteOffset()
        );
    }

    throw e;
}
~~~

Vị trí là điểm parser phát hiện không thể tiếp tục, không nhất thiết là ký tự đầu tiên gây lỗi. Ví dụ dấu ngoặc mở thiếu có thể chỉ được phát hiện khi parser đến EOF.

Với InputStream, byte offset thường hữu ích. Với Reader/String, character offset có thể phù hợp hơn. Không nên giả định mọi nguồn cung cấp đầy đủ cả byte offset và character offset.

## 20. Chẩn đoán đường dẫn property bằng JsonMappingException

JsonMappingException có thể lưu path từ root đến property gây lỗi. Ví dụ:

~~~json
{
  "customer": {
    "addresses": [
      {
        "city": "Ha Noi"
      },
      {
        "city": {
          "name": "Da Nang"
        }
      }
    ]
  }
}
~~~

Nếu property city trong phần tử thứ hai yêu cầu String nhưng JSON lại cung cấp object, lỗi mapping có thể chứa đường dẫn tương tự:

~~~text
customer.addresses[1].city
~~~

Có thể lấy thông tin:

~~~java
catch (JsonMappingException e) {
    String path = e.getPathReference();
    List<JsonMappingException.Reference> references = e.getPath();

    log.warn(
        "Mapping failed at path {}: {}",
        path,
        e.getOriginalMessage()
    );
}
~~~

Reference có thể mô tả tên field hoặc index của phần tử collection. Dùng pathReference thường tiện cho log; dùng getPath() khi cần tạo cấu trúc lỗi chi tiết cho API.

## 21. Lấy field name và index từ mapping path

Mỗi JsonMappingException.Reference có thể chứa:

- Tên field nếu lỗi nằm ở property của bean.
- Index nếu lỗi nằm ở phần tử array/list.
- Đối tượng hoặc kiểu chứa property trong một số ngữ cảnh.

Ví dụ:

~~~java
for (JsonMappingException.Reference reference : e.getPath()) {
    if (reference.getFieldName() != null) {
        System.out.println("Field: " + reference.getFieldName());
    }
    if (reference.getIndex() >= 0) {
        System.out.println("Index: " + reference.getIndex());
    }
}
~~~

Có thể dùng path để tạo thông báo dễ hiểu như "addresses[1].city phải là chuỗi". Tuy nhiên, không nên đưa tên class nội bộ, package, giá trị bí mật hoặc stack trace vào response công khai.

## 22. getOriginalMessage() và getMessage()

JsonProcessingException cung cấp thông tin message. Hai phương thức thường gặp:

- getOriginalMessage(): nội dung message gốc của exception.
- getMessage(): message có thể kèm thông tin location hoặc path theo cách triển khai.

Ví dụ:

~~~java
catch (JsonProcessingException e) {
    log.warn("JSON processing failed: {}", e.getOriginalMessage());
    log.debug("Full Jackson detail", e);
}
~~~

Với JsonMappingException, message có thể đã bao gồm path. Với JsonParseException, message thường kèm vị trí. Khi ghi log, tránh nối message nhiều lần khiến cùng location xuất hiện lặp.

## 23. Phân biệt lỗi cú pháp với lỗi mapping trong ví dụ thực tế

Hai JSON dưới đây trông đều có vấn đề, nhưng thuộc hai tầng khác nhau.

Lỗi cú pháp:

~~~json
{
  "name": "Mai",
  "age": 25,
~~~

Object chưa đóng. Parser không thể tạo token stream hoàn chỉnh và báo lỗi parse/EOF.

Lỗi mapping:

~~~json
{
  "name": "Mai",
  "age": {
    "years": 25
  }
}
~~~

JSON này đúng cú pháp. Nhưng nếu age trong Java là int, cấu trúc object không thể ánh xạ vào số nguyên.

Phân biệt này giúp tìm đúng nơi sửa:

- Lỗi parse: sửa payload producer hoặc luồng truyền dữ liệu.
- Lỗi mapping: thống nhất schema với kiểu Java, thay DTO hoặc cấu hình coercion có chủ đích.

## 24. Không coi mọi lỗi mapping là lỗi client

Một request có thể gây MismatchedInputException vì client gửi sai kiểu. Nhưng InvalidDefinitionException thường chỉ ra server không chuẩn bị được kiểu Java. ValueInstantiationException có thể do dữ liệu vi phạm invariant hoặc do lỗi bên trong constructor.

Có thể phân nhóm ở tầng ứng dụng:

| Loại mapping error | Nguyên nhân thường gặp | Cách xử lý vận hành |
|---|---|---|
| MismatchedInputException | Cấu trúc/kiểu JSON không khớp DTO | Thường là lỗi payload, trả 400 nếu đến từ request |
| UnrecognizedPropertyException | Field lạ, schema lệch | Theo chính sách strict/tolerant |
| InvalidFormatException | Giá trị không thể chuyển kiểu | Thường là lỗi payload |
| InvalidTypeIdException | Type discriminator không biết | Lỗi schema/version hoặc payload |
| InvalidDefinitionException | DTO hoặc cấu hình Jackson không hợp lệ | Thường là lỗi server, cần sửa code/config |
| ValueInstantiationException | Constructor/factory từ chối giá trị hoặc ném lỗi | Xem cause và quy tắc validation |

Đây là định hướng, không phải quy tắc HTTP tuyệt đối. Cùng một exception có thể phát sinh khi đọc file nội bộ, message từ broker hoặc request client. Hãy xét nguồn dữ liệu và trách nhiệm của producer.

## 25. Lỗi I/O và retry

Retry chỉ phù hợp với lỗi có khả năng tạm thời. Ví dụ:

- Socket timeout khi gọi dịch vụ upstream.
- Connection reset trong một lần truyền tải.
- Một lỗi lưu trữ tạm thời có thể phục hồi.

Không nên retry một payload JSON sai cú pháp nhiều lần với cùng nội dung. Parse error thường là lỗi xác định; retry không làm dấu ngoặc bị thiếu tự xuất hiện.

Tương tự, mapping error do age là object thay vì số sẽ tiếp tục xảy ra khi gửi lại cùng payload. Cần sửa producer, schema hoặc DTO.

Bảng định hướng:

| Nhóm lỗi | Retry tự động? | Lý do |
|---|---|---|
| Timeout tạm thời | Có thể, có giới hạn và backoff | Nguồn có thể phục hồi |
| Connection reset | Có thể, tùy idempotency và giao thức | Kết nối có thể được thiết lập lại |
| File không tồn tại | Thường không | Retry không tạo ra file |
| Permission denied | Không | Cần sửa quyền hoặc cấu hình |
| JSON malformed | Không | Nội dung đầu vào vẫn sai |
| Mismatched input | Không | Payload vẫn không khớp kiểu |
| Invalid type id | Không, trừ khi consumer đang chờ schema rollout có chủ đích | Cần đồng bộ subtype |
| InvalidDefinitionException | Không | Cần sửa cấu hình hoặc model |

Nếu retry thao tác ghi, cần xem thao tác có idempotent không. Một lần ghi có thể đã gửi một phần dữ liệu trước khi kết nối đứt; gửi lại có thể tạo bản ghi trùng hoặc JSON bị nối vào output cũ.

## 26. EOF từ nguồn mạng: cú pháp hay I/O?

Đây là trường hợp dễ gây nhầm. Giả sử producer gửi JSON:

~~~json
{
  "name": "Mai",
  "age": 25
}
~~~

Nhưng kết nối bị ngắt sau:

~~~text
{"name":"Mai","age":
~~~

Parser có thể nhìn thấy một input kết thúc giữa chừng và báo JsonEOFException/JsonParseException. Từ góc nhìn grammar, JSON không hoàn chỉnh. Từ góc nhìn hệ thống, nguyên nhân gốc có thể là transport bị cắt.

Để phân biệt, cần thông tin ngoài parser:

- Content-Length mà HTTP client/server đã trao đổi.
- Chunked transfer framing có kết thúc đúng không.
- Checksum hoặc message length trong giao thức broker.
- Kích thước file dự kiến hoặc metadata upload.
- Trạng thái kết nối và log transport.

Không nên phân loại mọi JsonEOFException là lỗi người dùng. Nếu dữ liệu đến từ mạng và có bằng chứng body bị cắt, có thể ghi nhận đó là lỗi truyền tải/truncated payload ở tầng tích hợp, dù exception cuối cùng là parse exception.

## 27. Xử lý lỗi HTTP trong REST API

Một API có thể ánh xạ lỗi theo nguồn và loại lỗi:

| Tình huống | HTTP status thường cân nhắc |
|---|---|
| Request body sai cú pháp JSON | 400 Bad Request |
| JSON đúng cú pháp nhưng không khớp DTO | 400 Bad Request |
| Type id không hợp lệ do client gửi | 400 Bad Request |
| DTO hoặc serializer cấu hình sai ở server | 500 Internal Server Error |
| Không đọc được dịch vụ upstream do timeout | 502/503/504 tùy vai trò gateway và nguyên nhân |
| Client đóng kết nối khi server đang ghi response | Thường không thể gửi một response lỗi hoàn chỉnh nữa |

Không nên trả 500 cho mọi JsonProcessingException nếu lỗi rõ ràng do request body không hợp lệ. Ngược lại, không nên trả 400 cho InvalidDefinitionException do server thiếu cấu hình creator.

Trong Spring MVC, có thể xử lý lỗi request JSON qua exception handler:

~~~java
@RestControllerAdvice
public class JsonErrorHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadable(
            HttpMessageNotReadableException exception) {

        Throwable cause = exception.getMostSpecificCause();
        String message = "Request body is invalid";

        if (cause instanceof JsonParseException parseException) {
            JsonLocation location = parseException.getLocation();
            if (location != null) {
                message = "Malformed JSON at line "
                    + location.getLineNr()
                    + ", column "
                    + location.getColumnNr();
            }
        } else if (cause instanceof JsonMappingException mappingException) {
            message = "Request fields do not match the expected structure";
        }

        return ResponseEntity.badRequest()
            .body(new ApiError("INVALID_JSON", message));
    }
}
~~~

Đây là ví dụ định hướng. Trong Spring, exception có thể bọc nhiều lớp và nguyên nhân cụ thể không nhất thiết là trực tiếp cause. Nên duyệt cause chain hoặc dùng thông tin của HttpMessageNotReadableException một cách an toàn.

Nếu cause là InvalidDefinitionException do cấu hình server, không nên luôn trả 400. Hãy phân loại riêng lỗi cấu hình để trả 500 và ghi log mức error.

## 28. Cause chain giúp tìm nguyên nhân gốc

Jackson hoặc framework có thể bọc exception gốc. Ví dụ:

~~~text
HttpMessageNotReadableException
  caused by JsonMappingException
    caused by IllegalArgumentException
~~~

Khi chỉ nhìn exception ngoài cùng, có thể bỏ sót lỗi constructor hoặc converter bên trong.

Có thể duyệt cause chain:

~~~java
static Throwable rootCause(Throwable error) {
    Throwable current = error;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
~~~

Không phải lúc nào root cause cũng chứa thông tin đầy đủ nhất. JsonMappingException có thể chứa path hữu ích hơn cause cuối cùng. Khi chẩn đoán, nên giữ cả exception Jackson và cause chain:

~~~java
log.warn(
    "Mapping failed at {}: {}",
    mappingException.getPathReference(),
    mappingException.getOriginalMessage(),
    mappingException
);
~~~

## 29. Logging an toàn khi JSON có dữ liệu nhạy cảm

Khi lỗi xảy ra, không nên mặc định ghi toàn bộ request body vào log. JSON có thể chứa:

- Mật khẩu.
- Access token hoặc refresh token.
- Số tài khoản, thông tin thanh toán.
- Địa chỉ, số điện thoại hoặc email.
- Thông tin cá nhân hoặc dữ liệu nghiệp vụ bí mật.

Nên ghi những thông tin đủ để chẩn đoán:

- Correlation/request ID.
- Tên endpoint hoặc message type.
- Kiểu Java đích.
- Loại exception.
- JsonLocation nếu có.
- JsonMappingException path nếu có.
- Mã lỗi hoặc message đã được làm sạch.

Nếu cần lưu payload để tái hiện lỗi, hãy dùng kho dữ liệu bảo mật, masking hoặc cơ chế lấy mẫu có kiểm soát theo chính sách dữ liệu. Không đưa raw payload vào log ứng dụng một cách mặc định.

## 30. Không trả stack trace Jackson cho client

Message của JsonMappingException có thể chứa tên class, property nội bộ, package hoặc chi tiết cấu hình. Stack trace có thể tiết lộ cấu trúc hệ thống.

Không nên:

~~~java
return ResponseEntity.badRequest()
    .body(exception.getMessage());
~~~

Nên trả mã lỗi và thông điệp ổn định:

~~~json
{
  "code": "INVALID_JSON",
  "message": "Request body does not match the expected format"
}
~~~

Chi tiết như path, location và cause có thể ghi trong log nội bộ sau khi loại bỏ dữ liệu nhạy cảm. Nếu muốn trả field error cho client, hãy chuyển path thành tên field đã được công khai trong API contract và không đưa thông tin class nội bộ.

## 31. Xác định lỗi ở giai đoạn mở, parse hay bind

Một cách tổ chức code giúp phân loại rõ là tách các bước:

~~~java
InputStream openSource(Path path) throws IOException {
    return Files.newInputStream(path);
}

JsonNode parseTree(InputStream input) throws IOException {
    return mapper.readTree(input);
}

User bind(JsonNode tree) throws JsonProcessingException {
    return mapper.treeToValue(tree, User.class);
}
~~~

Luồng xử lý:

~~~java
try (InputStream input = openSource(path)) {
    JsonNode tree;
    try {
        tree = parseTree(input);
    } catch (JsonParseException e) {
        throw new InvalidJsonSyntaxException(e);
    }

    try {
        return bind(tree);
    } catch (JsonMappingException e) {
        throw new InvalidJsonShapeException(e);
    }
}
~~~

Ví dụ này dùng JsonNode làm ranh giới giữa parse và bind. Nó có thể giúp chẩn đoán hoặc kiểm tra schema, nhưng cần lưu ý tree model giữ toàn bộ cây JSON trong bộ nhớ. Với file rất lớn, streaming parser có thể phù hợp hơn.

Nếu không cần tách parse và bind, một lời gọi readValue thường gọn hơn. Việc chia giai đoạn chỉ đáng dùng khi ứng dụng cần quan sát, validate hoặc xử lý lỗi riêng ở từng bước.

## 32. Dùng JsonParser để phân biệt lỗi đọc token và lỗi mapping

Với Jackson Core, có thể parse token mà không ánh xạ vào DTO:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    while (parser.nextToken() != null) {
        // Xử lý token
    }
}
~~~

Nếu parser ném JsonParseException, lỗi xảy ra khi đọc cú pháp/token. Nếu parser đọc hết thành công nhưng Databind thất bại khi tạo User, vấn đề thuộc mapping.

Ví dụ:

~~~java
JsonNode tree = mapper.readTree(json);
User user = mapper.treeToValue(tree, User.class);
~~~

Nếu readTree thất bại do JSON malformed, lỗi parse xuất hiện ở bước đầu. Nếu readTree thành công nhưng treeToValue thất bại vì age là object trong khi Java cần int, lỗi mapping xuất hiện ở bước sau.

Tuy nhiên, không cần parse thành tree chỉ để phân loại trong mọi trường hợp. JsonParser và Databind đã cung cấp exception phân biệt; tách bước có thêm chi phí bộ nhớ và xử lý.

## 33. Lỗi charset và encoding

Dữ liệu JSON thường được truyền bằng UTF-8. Nếu byte stream được giải mã bằng charset sai, có thể xuất hiện ký tự méo hoặc lỗi parse.

Ví dụ:

~~~java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    User user = mapper.readValue(reader, User.class);
}
~~~

Nếu dùng Reader, ứng dụng chịu trách nhiệm chọn charset khi tạo Reader. Nếu truyền InputStream, Jackson có thể nhận diện encoding theo quy tắc JSON và BOM, nhưng giao thức/nguồn dữ liệu vẫn cần quy định encoding rõ.

Một số lỗi charset có thể được báo dưới dạng CharacterCodingException hoặc IOException từ reader; một số dữ liệu giải mã thành ký tự không mong muốn rồi gây JsonParseException. Vì vậy, hãy kiểm tra header/content type, charset nguồn và cách tạo Reader.

Không nên sửa JSON bằng cách thay ký tự lỗi một cách tùy tiện vì có thể làm thay đổi dữ liệu nghiệp vụ hoặc che giấu lỗi encoding của producer.

## 34. Lỗi do cấu hình coercion

Jackson có thể cho phép một số chuyển đổi giữa scalar JSON và kiểu Java. Ví dụ chuỗi "123" có thể được chuyển thành số nguyên tùy cấu hình coercion.

Điều đó có nghĩa một payload không đúng kiểu mong muốn có thể không phát sinh exception. Nếu hợp đồng yêu cầu strict type, hãy cấu hình coercion phù hợp hoặc validate token trước khi bind.

Jackson cung cấp CoercionConfig ở các phiên bản mới để điều chỉnh cách xử lý theo logical type và input shape. Ví dụ cấu hình cụ thể phụ thuộc phiên bản Jackson; hãy kiểm tra API của dependency đang dùng.

Khi chẩn đoán:

- Không thấy exception không đồng nghĩa payload đúng hợp đồng.
- Cần phân biệt parse thành công, coercion thành công và validation nghiệp vụ thành công.
- Kiểm thử cả giá trị hợp lệ, giá trị có thể coercion và giá trị cần từ chối.

## 35. Bật/tắt FAIL_ON_UNKNOWN_PROPERTIES có thay đổi loại lỗi không?

Có. Khi FAIL_ON_UNKNOWN_PROPERTIES bật, field không biết có thể dẫn đến UnrecognizedPropertyException. Khi tắt, Jackson bỏ qua field đó và không có mapping exception cho riêng field này.

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();

ObjectMapper tolerantMapper = JsonMapper.builder()
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Hai mapper có thể đọc cùng JSON nhưng cho kết quả khác nhau. Strict mapper giúp phát hiện schema drift; tolerant mapper hỗ trợ tương thích khi producer thêm field không ảnh hưởng consumer.

Đây là quyết định hợp đồng, không chỉ là quyết định để giảm log lỗi. Nếu tắt feature, cần chắc chắn field lạ không phải dữ liệu bắt buộc hoặc dữ liệu quan trọng đang bị bỏ qua.

## 36. Phân biệt lỗi mapping với validation nghiệp vụ

Jackson đảm nhiệm chuyển JSON thành kiểu Java. Nó không thay thế toàn bộ validation nghiệp vụ.

Ví dụ:

~~~java
public class TransferRequest {
    private BigDecimal amount;
    private String destination;
}
~~~

JSON:

~~~json
{
  "amount": -100,
  "destination": "ACC-001"
}
~~~

JSON hợp lệ và có thể ánh xạ thành TransferRequest. Nhưng amount âm có thể vi phạm quy tắc chuyển tiền. Đây là lỗi validation nghiệp vụ, không phải lỗi cú pháp hoặc lỗi mapping.

Phân biệt:

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| I/O | Có đọc/ghi được dữ liệu không? | File không đọc được |
| Parse | Nội dung có đúng cú pháp JSON không? | Thiếu dấu ngoặc đóng |
| Mapping | Token có chuyển được thành kiểu Java không? | Object vào int |
| Validation | Giá trị có hợp lệ theo nghiệp vụ không? | Số tiền âm |

Không nên bắt JsonMappingException để xử lý mọi lỗi validation. Hãy dùng Bean Validation hoặc quy tắc nghiệp vụ ở service sau khi DTO được tạo.

## 37. Tránh nuốt exception và trả object rỗng

Một anti-pattern là bắt mọi exception rồi trả DTO rỗng:

~~~java
try {
    return mapper.readValue(json, User.class);
} catch (Exception e) {
    log.warn("Invalid JSON");
    return new User();
}
~~~

Cách này làm lỗi nguồn, lỗi cú pháp, lỗi mapping và lỗi lập trình đều biến thành một object mặc định. Hệ thống có thể tiếp tục xử lý dữ liệu sai mà không biết.

Hãy trả lỗi có kiểu hoặc chuyển thành exception nghiệp vụ có cause:

~~~java
try {
    return mapper.readValue(json, User.class);
} catch (JsonParseException | JsonMappingException e) {
    throw new InvalidUserPayloadException(
        "Cannot decode user payload",
        e
    );
}
~~~

IOException còn lại nên được xử lý ở tầng quản lý nguồn/đích dữ liệu. Không nên biến lỗi đọc file thành User rỗng.

## 38. Tạo cấu trúc lỗi thống nhất ở tầng ứng dụng

Một ứng dụng có thể chuẩn hóa exception của Jackson thành các loại lỗi nội bộ:

~~~java
public class InvalidJsonSyntaxException extends RuntimeException {
    public InvalidJsonSyntaxException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class JsonTypeMismatchException extends RuntimeException {
    public JsonTypeMismatchException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class JsonConfigurationException extends RuntimeException {
    public JsonConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class JsonSourceException extends RuntimeException {
    public JsonSourceException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Tầng adapter Jackson chuyển exception:

~~~java
public User decode(InputStream input) {
    try {
        return mapper.readValue(input, User.class);
    } catch (InvalidDefinitionException e) {
        throw new JsonConfigurationException(
            "User mapping is not configured correctly",
            e
        );
    } catch (JsonMappingException e) {
        throw new JsonTypeMismatchException(
            "JSON does not match User",
            e
        );
    } catch (JsonParseException e) {
        throw new InvalidJsonSyntaxException(
            "Malformed JSON input",
            e
        );
    } catch (JsonProcessingException e) {
        throw new InvalidJsonSyntaxException(
            "JSON processing failed",
            e
        );
    } catch (IOException e) {
        throw new JsonSourceException(
            "Could not read JSON source",
            e
        );
    }
}
~~~

InvalidDefinitionException cần được bắt trước JsonMappingException vì nó là một dạng mapping exception nhưng thường biểu thị lỗi định nghĩa/configuration. Nếu ứng dụng muốn phân loại chi tiết hơn, có thể bắt thêm InvalidTypeIdException, UnrecognizedPropertyException hoặc InvalidFormatException trước nhánh mapping tổng quát.

## 39. Xây thông báo lỗi theo path và location

Một response lỗi có thể cung cấp thông tin đủ hữu ích mà không để lộ nội bộ:

~~~java
public record ApiError(
    String code,
    String message,
    String path,
    Integer line,
    Integer column
) {
}
~~~

Hàm chuyển mapping exception:

~~~java
ApiError toMappingError(JsonMappingException exception) {
    return new ApiError(
        "JSON_TYPE_MISMATCH",
        "A request field has an invalid type",
        exception.getPathReference(),
        null,
        null
    );
}
~~~

Hàm chuyển parse exception:

~~~java
ApiError toParseError(JsonParseException exception) {
    JsonLocation location = exception.getLocation();

    return new ApiError(
        "MALFORMED_JSON",
        "The request body is not valid JSON",
        null,
        location == null ? null : location.getLineNr(),
        location == null ? null : location.getColumnNr()
    );
}
~~~

Đối với API công khai, có thể không trả path nếu path chứa tên property nội bộ. Một số API chỉ trả code và message chung, còn chi tiết được ghi log nội bộ.

## 40. Đọc cause và path mà không làm mất exception gốc

Khi chuyển exception sang lỗi nội bộ, luôn truyền cause:

~~~java
throw new InvalidJsonSyntaxException(
    "Malformed import document",
    jsonParseException
);
~~~

Không nên chỉ tạo exception mới bằng message:

~~~java
throw new RuntimeException("JSON invalid");
~~~

Nếu bỏ cause, stack trace và vị trí lỗi gốc bị mất. Điều này làm khó chẩn đoán trong môi trường production.

Nếu cần bổ sung metadata như file name hoặc message ID, có thể gắn vào exception nội bộ hoặc log context. Không nên sửa message của exception Jackson bằng cách nối thêm raw payload.

## 41. Đọc JSON từ message broker

Khi JSON đến từ Kafka, RabbitMQ hoặc message broker khác, phân loại lỗi cần gắn với chính sách tiêu thụ message.

Ví dụ:

- Message body malformed: thường là poison message, không nên retry vô hạn.
- JSON đúng cú pháp nhưng schema không khớp consumer: có thể là version mismatch hoặc producer bug.
- Message bị cắt hoặc lỗi transport: phụ thuộc broker và giao thức, có thể cần kiểm tra integrity.
- Mapper thiếu subtype mới: consumer có thể cần nâng cấp hoặc route message sang dead-letter queue.

Không nên retry vô hạn một message luôn gây JsonParseException hoặc InvalidTypeIdException. Có thể dùng dead-letter queue, retry có giới hạn cho lỗi tạm thời và lưu metadata để điều tra.

Khi log, dùng message ID, topic/queue, partition/offset hoặc correlation ID thay vì ghi toàn bộ payload.

## 42. Đọc JSON từ file import

Với file import, lỗi thường cần được báo theo file và dòng:

- File không tồn tại hoặc không đọc được: lỗi truy cập nguồn.
- JSON malformed: file không đúng cú pháp.
- Mapping mismatch: file đúng JSON nhưng schema không khớp DTO import.
- Validation: giá trị đúng kiểu nhưng vi phạm quy tắc nghiệp vụ.

Nếu file lớn có nhiều record, nên cân nhắc streaming để có thể xác định record lỗi và tiếp tục theo chính sách. Nếu dùng readValue cho toàn bộ document, một lỗi có thể khiến cả thao tác thất bại.

Không nên tự động bỏ qua mọi record lỗi. Cần quyết định rõ import là atomic (tất cả thành công hoặc thất bại) hay partial (chấp nhận record hợp lệ và báo record lỗi).

## 43. Lỗi I/O khi ghi response HTTP

Server có thể bắt đầu serialize response rồi client đóng kết nối. Khi đó, generator có thể gặp IOException khi ghi xuống socket.

Đây không phải lỗi JSON request. Server có thể không còn khả năng gửi một response lỗi khác vì connection đã đóng.

Một số framework sẽ log lỗi ghi response ở tầng servlet/container. Không nên bắt lỗi này rồi thử ghi một JSON error body khác vào cùng output stream đã hỏng.

Nếu lỗi xảy ra trước khi response bắt đầu được gửi, framework có thể vẫn chọn status phù hợp. Nếu response đã commit một phần, status và body có thể không thay đổi được.

## 44. Ghi file an toàn khi output có thể thất bại giữa chừng

Nếu ghi JSON vào file quan trọng, không nên ghi trực tiếp lên file đích rồi giả định file luôn hoàn chỉnh. Lỗi I/O giữa chừng có thể để lại file bị cắt.

Một cách thường dùng là ghi file tạm, đóng thành công rồi mới move:

~~~java
Path temp = target.resolveSibling(target.getFileName() + ".tmp");

try (OutputStream output = Files.newOutputStream(temp)) {
    mapper.writeValue(output, report);
}

Files.move(
    temp,
    target,
    StandardCopyOption.REPLACE_EXISTING,
    StandardCopyOption.ATOMIC_MOVE
);
~~~

ATOMIC_MOVE phụ thuộc filesystem và có thể không được hỗ trợ trong mọi môi trường. Nếu không hỗ trợ, ứng dụng cần quyết định fallback phù hợp. Cũng cần xử lý và dọn file tạm khi serialize hoặc move thất bại.

Đây là chiến lược bảo vệ file đầu ra trước lỗi ghi một phần; nó không sửa lỗi mapping hoặc JSON generation.

## 45. Những thông tin nên thu thập khi chẩn đoán

Một log chẩn đoán hữu ích thường có:

| Thông tin | Mục đích |
|---|---|
| Exception class | Phân biệt parse, mapping, generation và I/O |
| Root cause | Tìm nguyên nhân sâu hơn |
| JsonLocation | Tìm vị trí parser phát hiện lỗi |
| JsonMappingException path | Xác định property/index gây lỗi |
| Target Java type | Biết Jackson đang tạo hoặc ghi kiểu nào |
| Source/destination | Biết file, socket, request hay broker |
| Correlation/message ID | Liên kết log giữa các thành phần |
| Jackson version | Phân biệt khác biệt API/hành vi |
| Mapper configuration profile | Xác định feature/module/mix-in liên quan |

Không cần ghi toàn bộ những thông tin này vào response client. Chúng chủ yếu phục vụ log và tracing nội bộ.

## 46. Ví dụ tổng hợp: phân loại lỗi khi đọc JSON

~~~java
public final class JsonReader {

    private final ObjectMapper mapper;

    public JsonReader(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public <T> T read(InputStream input, Class<T> type) {
        try {
            return mapper.readValue(input, type);
        } catch (InvalidDefinitionException e) {
            log.error(
                "Jackson type definition is invalid for {}",
                type.getName(),
                e
            );
            throw new JsonConfigurationException(
                "JSON mapping configuration is invalid",
                e
            );
        } catch (JsonMappingException e) {
            log.warn(
                "JSON mapping failed for {} at {}: {}",
                type.getName(),
                e.getPathReference(),
                e.getOriginalMessage()
            );
            throw new JsonTypeMismatchException(
                "JSON structure does not match the expected type",
                e
            );
        } catch (JsonParseException e) {
            JsonLocation location = e.getLocation();
            log.warn(
                "Malformed JSON at {}",
                location,
                e
            );
            throw new InvalidJsonSyntaxException(
                "Input is not valid JSON",
                e
            );
        } catch (JsonProcessingException e) {
            log.warn("JSON processing failed", e);
            throw new InvalidJsonSyntaxException(
                "Could not process JSON input",
                e
            );
        } catch (IOException e) {
            log.error("I/O failure while reading JSON", e);
            throw new JsonSourceException(
                "Could not read JSON source",
                e
            );
        }
    }
}
~~~

Ví dụ này cho thấy:

1. InvalidDefinitionException được bắt trước mapping exception tổng quát.
2. JsonMappingException được dùng để lấy path.
3. JsonParseException được dùng để lấy location.
4. JsonProcessingException là nhánh fallback cho lỗi xử lý JSON khác.
5. IOException cuối cùng đại diện cho lỗi I/O còn lại.

Các class exception nội bộ và logger trong ví dụ là thành phần minh họa. Trong dự án, cần điều chỉnh theo framework và chính sách lỗi hiện tại.

## 47. Những lỗi thường gặp khi phân loại

| Cách xử lý sai | Vì sao sai | Cách xử lý tốt hơn |
|---|---|---|
| Bắt IOException rồi gọi tất cả là lỗi file | Exception JSON cũng thuộc hệ thống IOException | Bắt JsonMappingException, JsonParseException và JsonProcessingException trước |
| Retry mọi JsonProcessingException | Parse/mapping error thường không tự hết | Chỉ retry lỗi I/O có tính tạm thời |
| Trả 500 cho mọi lỗi Jackson | Request malformed thường là lỗi phía client | Phân biệt payload với lỗi cấu hình server |
| Trả 400 cho InvalidDefinitionException | Server có thể cấu hình DTO/mapper sai | Ghi nhận lỗi server và trả 500 phù hợp |
| Log toàn bộ request body | Có thể lộ dữ liệu nhạy cảm | Log path, location, type, correlation ID |
| Trả stack trace cho client | Lộ class/package/cấu hình nội bộ | Trả error code và message ổn định |
| Bỏ cause khi wrap exception | Mất nguyên nhân và stack trace gốc | Giữ cause khi tạo exception nội bộ |
| Nuốt exception và trả object rỗng | Che giấu dữ liệu lỗi, tạo trạng thái giả | Chuyển thành lỗi có kiểu hoặc xử lý record lỗi rõ ràng |
| Coi JsonEOFException luôn là client gửi sai | Có thể do transport bị cắt | Kiểm tra framing, length và trạng thái kết nối |
| Dùng mapping exception cho validation nghiệp vụ | Hai tầng có trách nhiệm khác nhau | Validate DTO sau khi bind |

## 48. Quy trình chẩn đoán theo thứ tự

Khi một thao tác Jackson thất bại, có thể điều tra theo thứ tự:

1. Xác định nguồn hoặc đích là String, file, HTTP stream, broker hay một stream nội bộ.
2. Kiểm tra việc mở nguồn/đích có thành công không.
3. Xác định exception class cụ thể thay vì chỉ xem message.
4. Nếu là JsonParseException, đọc location và kiểm tra payload/encoding.
5. Nếu là JsonMappingException, đọc path, target type và property gây lỗi.
6. Nếu là InvalidDefinitionException, kiểm tra DTO, creator, module và mapper configuration.
7. Nếu là I/O exception, kiểm tra quyền, timeout, connection, thiết bị và vòng đời stream.
8. Xác định lỗi có thể tạm thời hay là lỗi xác định của payload/schema.
9. Chọn retry, dead-letter, HTTP status hoặc sửa cấu hình phù hợp.
10. Ghi log đủ để tái hiện nhưng không làm lộ raw payload nhạy cảm.

Sơ đồ quyết định:

~~~text
Jackson operation failed
          |
          v
Exception class?
   |
   +--> JsonParseException / JsonEOFException
   |          |
   |          +--> Kiểm tra JSON syntax, location, encoding,
   |               và khả năng payload bị cắt trên transport
   |
   +--> JsonMappingException
   |          |
   |          +--> Kiểm tra target type, path, subtype,
   |               creator và property shape
   |
   +--> JsonGenerationException
   |          |
   |          +--> Kiểm tra serializer và trạng thái generator
   |
   +--> IOException khác
              |
              +--> Kiểm tra nguồn/đích, quyền, timeout,
                   kết nối và vòng đời stream
~~~

Nếu exception bị framework bọc, hãy xem cause chain nhưng vẫn giữ thông tin path/location của exception Jackson.

## 49. Nguyên tắc thực hành

- Phân biệt I/O, parse, mapping, generation và validation nghiệp vụ.
- Không coi mọi IOException là lỗi nguồn dữ liệu; exception Jackson cũng nằm trong hệ thống này.
- Bắt JsonMappingException và JsonParseException trước JsonProcessingException/IOException.
- Dùng InvalidDefinitionException để nhận diện lỗi cấu hình kiểu.
- Dùng MismatchedInputException, InvalidFormatException và UnrecognizedPropertyException để hiểu lỗi input.
- Dùng InvalidTypeIdException cho subtype/type id không hợp lệ.
- Dùng JsonLocation để chẩn đoán cú pháp và JsonMappingException path để tìm property.
- Kiểm tra cause chain nhưng không bỏ mất thông tin Jackson hữu ích.
- Chỉ retry lỗi I/O có khả năng tạm thời và bảo đảm thao tác phù hợp với retry.
- Không retry vô hạn payload malformed hoặc mapping mismatch.
- Phân loại HTTP status theo nguồn lỗi và trách nhiệm client/server.
- Không log raw JSON nhạy cảm hoặc trả stack trace cho client.
- Tách validation nghiệp vụ khỏi quá trình Jackson binding.
- Với stream mạng bị cắt, đối chiếu framing/length thay vì chỉ nhìn exception cuối cùng.
- Kiểm tra cả đường đọc và đường ghi, vì lỗi mapping/generation cũng có thể xảy ra khi serialize.

Phân biệt đúng lỗi I/O, lỗi cú pháp và lỗi ánh xạ kiểu giúp hệ thống phản ứng đúng với nguyên nhân thực tế. Lỗi I/O cần kiểm tra nguồn/đích và khả năng phục hồi; lỗi parse cần kiểm tra grammar, encoding và tính toàn vẹn payload; lỗi mapping cần kiểm tra schema, kiểu Java và cấu hình Databind. Khi bắt exception theo đúng thứ tự, giữ path/location và không đánh đồng lỗi server với lỗi client, việc chẩn đoán Jackson sẽ rõ ràng và đáng tin cậy hơn.
