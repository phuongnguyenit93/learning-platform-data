# Kiểm thử thuộc tính bảo toàn qua vòng ghi rồi đọc

Trong kiểm thử serialization, một câu hỏi quan trọng là: sau khi ghi một object Java thành JSON rồi đọc JSON đó trở lại, những thông tin nào phải được giữ nguyên? Đây là **kiểm thử round-trip**. Thay vì chỉ kiểm tra một chuỗi JSON mẫu, ta kiểm tra một thuộc tính tổng quát: với mọi object hợp lệ được tạo ra, quá trình serialize rồi deserialize phải khôi phục object tương đương theo hợp đồng của ứng dụng.

Với Jackson, thuộc tính cơ bản có thể viết:

~~~text
decode(encode(value)) ≈ value
~~~

Trong đó encode là serialize bằng ObjectMapper, decode là deserialize về kiểu Java, còn ký hiệu tương đương (≈) phụ thuộc vào ý nghĩa dữ liệu. Với record có equality rõ ràng, có thể dùng equals. Với BigDecimal, map không cần giữ thứ tự, timestamp có chuẩn hóa múi giờ hoặc DTO có field bị bỏ qua khi ghi, cần so sánh theo invariant nghiệp vụ thay vì đòi hỏi object giống hệt từng chi tiết.

Kiểm thử property-based giúp tạo ra nhiều giá trị đầu vào theo một generator, chạy cùng một invariant qua hàng trăm hoặc hàng nghìn trường hợp và thu nhỏ dữ liệu khi phát hiện lỗi. Kết hợp JUnit với jqwik, nhóm phát triển có thể phát hiện những trường hợp biên như chuỗi rỗng, quote, newline, Unicode, collection rỗng, số âm, giá trị sát giới hạn và cấu trúc lồng nhau.

## 1. Round-trip testing kiểm tra điều gì?

Một vòng round-trip JSON thông thường gồm hai bước:

~~~text
Java object
    |
    | ObjectMapper.writeValueAsString()
    v
JSON text
    |
    | ObjectMapper.readValue()
    v
Java object được khôi phục
~~~

Ví dụ:

~~~java
public record User(
    long id,
    String name,
    boolean active
) {}

ObjectMapper mapper = new ObjectMapper();

User original = new User(17L, "Linh", true);

String json = mapper.writeValueAsString(original);

User restored = mapper.readValue(json, User.class);

assertEquals(original, restored);
~~~

Test này xác nhận một trường hợp cụ thể. Nhưng một ví dụ đơn lẻ có thể không bao phủ chuỗi có dấu quote, Unicode, giá trị null, số ở biên hoặc các object lồng nhau.

Property-based test diễn đạt cùng một quy tắc cho một tập lớn dữ liệu được sinh:

~~~java
@Property
void userSurvivesRoundTrip(@ForAll("users") User original)
        throws JsonProcessingException {

    String json = mapper.writeValueAsString(original);
    User restored = mapper.readValue(json, User.class);

    assertEquals(original, restored);
}
~~~

Mỗi lần chạy, framework tạo nhiều User khác nhau. Nếu một trường hợp thất bại, framework có thể thu nhỏ dữ liệu để tìm một ví dụ đơn giản hơn vẫn tái hiện lỗi.

Round-trip không có nghĩa mọi byte JSON phải giống nhau sau khi ghi lại. JSON có thể thay đổi khoảng trắng, thứ tự property hoặc cách biểu diễn số mà vẫn mang cùng giá trị. Điều cần bảo toàn là thông tin semantic mà hợp đồng yêu cầu.

## 2. Xác định invariant trước khi viết test

Một test round-trip tốt bắt đầu bằng câu hỏi: điều gì phải được giữ lại?

Các invariant thường gặp:

- ID, mã nghiệp vụ và trạng thái phải giữ nguyên.
- String phải giữ đúng ký tự, kể cả dấu quote, dấu phẩy, newline và Unicode.
- Collection phải giữ số phần tử, thứ tự nếu thứ tự có ý nghĩa và giá trị từng phần tử.
- Map phải giữ cặp key/value; thứ tự key thường không phải invariant nếu contract không yêu cầu.
- BigDecimal phải giữ giá trị và, nếu nghiệp vụ cần, cả scale.
- Date/time phải giữ đúng instant hoặc local date/time theo contract.
- Enum phải giữ đúng trạng thái.
- Kiểu con trong polymorphic model phải được khôi phục đúng.
- Field bắt buộc không được biến thành null/default ngoài ý muốn.

Không phải mọi property đều cần round-trip giống hệt. Một DTO có @JsonIgnore, field write-only, transient field hoặc computed property có thể cố ý không được ghi ra JSON. Nếu test yêu cầu toàn bộ object bằng equals, test có thể thất bại dù serialization đang làm đúng hợp đồng.

Hãy viết rõ một trong các dạng invariant:

| Dạng | Ý nghĩa |
|---|---|
| Equality | Object khôi phục bằng object ban đầu theo equals |
| Semantic equivalence | Các giá trị nghiệp vụ quan trọng giống nhau |
| Invariant preservation | Một số điều kiện luôn đúng sau khi khôi phục |
| Canonicalization | JSON đầu vào được chuyển thành dạng chuẩn |
| Idempotence | Chuẩn hóa lặp lại không làm dữ liệu thay đổi thêm |

Việc xác định invariant trước giúp tránh viết test quá chặt hoặc quá lỏng.

## 3. Equality và semantic equivalence khác nhau

Nếu DTO là Java record và mọi component đều thuộc wire contract, generated equals() thường phù hợp:

~~~java
public record Address(
    String city,
    String country
) {}

public record Customer(
    long id,
    String name,
    Address address
) {}
~~~

Với model trên:

~~~java
assertEquals(original, restored);
~~~

có thể kiểm tra toàn bộ cấu trúc lồng nhau vì record equality so sánh từng component.

Nhưng với Map, thứ tự iteration thường không phải ý nghĩa dữ liệu. Không nên so sánh chuỗi JSON để kết luận hai map tương đương:

~~~json
{"a":1,"b":2}
~~~

và:

~~~json
{"b":2,"a":1}
~~~

Hai object JSON có thể mang cùng cặp property dù thứ tự khác nhau. Hãy deserialize rồi so sánh Map bằng equals, hoặc so sánh JsonNode theo cấu trúc.

Với các kiểu có quy tắc riêng, hãy viết helper:

~~~java
void assertMoneyEquivalent(Money expected, Money actual) {
    assertEquals(expected.currency(), actual.currency());
    assertEquals(0, expected.amount().compareTo(actual.amount()));
}
~~~

Ở đây scale của BigDecimal không được coi là khác biệt nghiệp vụ. Nếu scale biểu diễn độ chính xác hoặc số chữ số thập phân có ý nghĩa, hãy dùng equals hoặc assert riêng scale.

## 4. Thiết lập property-based testing với jqwik

jqwik tích hợp với JUnit Platform và cung cấp các annotation như @Property, @ForAll, @Provide cùng API tạo Arbitrary.

Với Gradle, thêm jqwik vào test dependencies theo version được dự án quản lý:

~~~groovy
dependencies {
    testImplementation("net.jqwik:jqwik:<version-duoc-quan-ly>")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>net.jqwik</groupId>
    <artifactId>jqwik</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án không dùng dependency management cho jqwik, hãy khai báo phiên bản phù hợp với JUnit Platform đang dùng. Không cần đưa jqwik vào runtime dependency của ứng dụng.

Một test class cơ bản:

~~~java
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class UserRoundTripProperties {

    private final ObjectMapper mapper = new ObjectMapper();

    record User(long id, String name, boolean active) {}

    @Provide
    Arbitrary<User> users() {
        return Combinators.combine(
            Arbitraries.longs().between(1, 1_000_000),
            Arbitraries.strings().alpha()
                .ofMinLength(1)
                .ofMaxLength(40),
            Arbitraries.of(true, false)
        ).as(User::new);
    }

    @Property(tries = 500)
    void userRoundTrip(@ForAll("users") User original)
            throws JsonProcessingException {

        String json = mapper.writeValueAsString(original);
        User restored = mapper.readValue(json, User.class);

        assertEquals(original, restored);
    }
}
~~~

Ví dụ dùng record để equals có ý nghĩa rõ. Trong project thực tế, import thêm Combinators, JsonProcessingException, ObjectMapper và assertion của JUnit. Số lần thử có thể điều chỉnh theo thời gian test suite và độ phức tạp của generator.

## 5. Generator phải phản ánh miền dữ liệu hợp lệ

Property-based testing không có nghĩa tạo giá trị hoàn toàn ngẫu nhiên. Generator cần tạo dữ liệu thuộc miền mà ứng dụng cho phép.

Ví dụ ID dương:

~~~java
Arbitraries.longs().between(1, 1_000_000)
~~~

Tên không rỗng và giới hạn độ dài:

~~~java
Arbitraries.strings().alpha()
    .ofMinLength(1)
    .ofMaxLength(40)
~~~

Trạng thái enum:

~~~java
Arbitraries.of(OrderStatus.values())
~~~

Nếu generator tạo ID âm trong khi constructor/domain model cấm ID âm, property có thể thất bại ở bước tạo dữ liệu thay vì kiểm tra Jackson. Điều đó không có nghĩa Jackson sai.

Có thể tách hai nhóm:
- Generator hợp lệ để kiểm tra round-trip.
- Generator không hợp lệ để kiểm tra parser/validation từ chối đúng dữ liệu.

Không nên làm generator quá hẹp. Nếu chỉ sinh tên gồm chữ cái ASCII, test không kiểm tra escaping, Unicode hoặc newline. Hãy kết hợp generator miền hợp lệ với một tập edge case được chọn rõ ràng.

## 6. Tạo string có ký tự đặc biệt

String là một trong những nguồn lỗi phổ biến trong serialization. Cần kiểm tra ít nhất:
- Chuỗi rỗng.
- Dấu quote kép và đơn.
- Backslash.
- Dấu phẩy, dấu hai chấm và dấu ngoặc.
- Tab, carriage return và newline.
- Tiếng Việt có dấu.
- Ký tự Unicode ngoài ASCII.
- Emoji hoặc ký tự supplementary.
- Chuỗi có khoảng trắng đầu/cuối.

Có thể tạo một Arbitrary từ các ví dụ đại diện:

~~~java
@Provide
Arbitrary<String> interestingStrings() {
    return Arbitraries.of(
        "",
        "Linh",
        "Xin chào",
        "He said \"ready\"",
        "path\\\\to\\\\file",
        "first line\nsecond line",
        "a,b,c",
        " leading and trailing ",
        "東京",
        "🙂"
    );
}
~~~

Dùng generator này trong property:

~~~java
@Property
void textSurvivesRoundTrip(
        @ForAll("interestingStrings") String value)
        throws JsonProcessingException {

    TextPayload original = new TextPayload(value);

    String json = mapper.writeValueAsString(original);
    TextPayload restored = mapper.readValue(json, TextPayload.class);

    assertEquals(original, restored);
}
~~~

Tập ví dụ cố định bảo đảm các edge case quan trọng luôn được chạy. Có thể bổ sung Arbitrary tạo chuỗi dài/ngẫu nhiên để tăng độ đa dạng.

Không nên giả định JSON output giữ nguyên cách viết escape. Một writer có thể phát ký tự Unicode trực tiếp hoặc escape một số ký tự; sau khi đọc, giá trị String phải tương đương.

## 7. Generator cho object lồng nhau

Một DTO có nested object và collection nên được sinh theo cấu trúc thật:

~~~java
record Item(String sku, int quantity) {}

record Order(
    String orderId,
    String customerName,
    List<Item> items
) {}
~~~

Tạo generator cho item rồi kết hợp thành order:

~~~java
@Provide
Arbitrary<Item> items() {
    return Combinators.combine(
        Arbitraries.strings().alpha()
            .ofMinLength(1)
            .ofMaxLength(12),
        Arbitraries.integers().between(1, 100)
    ).as(Item::new);
}

@Provide
Arbitrary<Order> orders() {
    return Combinators.combine(
        Arbitraries.strings().alpha()
            .ofMinLength(1)
            .ofMaxLength(20),
        Arbitraries.strings().alpha()
            .ofMinLength(1)
            .ofMaxLength(40),
        items().list().ofMaxSize(20)
    ).as(Order::new);
}
~~~

Property:

~~~java
@Property(tries = 300)
void nestedOrderRoundTrip(@ForAll("orders") Order original)
        throws JsonProcessingException {

    String json = mapper.writeValueAsString(original);
    Order restored = mapper.readValue(json, Order.class);

    assertEquals(original, restored);
}
~~~

Generator này tạo cả danh sách rỗng và danh sách có item, với quantity trong miền hợp lệ. Nếu empty list không hợp lệ theo contract, hãy dùng ofMinSize(1) hoặc tạo generator riêng.

Với cấu trúc đệ quy như tree node, giới hạn chiều sâu generator để test không tự tạo dữ liệu quá lớn hoặc gây stack overflow. Độ sâu sinh dữ liệu nên bao gồm các trường hợp gần giới hạn hợp đồng.

## 8. Kiểm tra Map và collection mà không phụ thuộc thứ tự không cần thiết

Map JSON thường được biểu diễn bằng object với key dạng string. Khi kiểm tra round-trip:

~~~java
record Settings(Map<String, String> values) {}

@Property
void mapRoundTrip(@ForAll("settings") Settings original)
        throws JsonProcessingException {

    String json = mapper.writeValueAsString(original);
    Settings restored = mapper.readValue(json, Settings.class);

    assertEquals(original.values(), restored.values());
}
~~~

Map.equals() so sánh cặp key/value, không yêu cầu thứ tự iteration giống nhau. Đây thường là điều đúng nếu thứ tự key không thuộc hợp đồng.

Với List, thứ tự thường có ý nghĩa, vì vậy List.equals() là phép so sánh phù hợp. Với Set, thứ tự thường không có ý nghĩa, nên so sánh set equality.

Khi dùng custom key serializer/deserializer cho Map có key không phải String, hãy sinh cả key bình thường và key biên. JSON object key luôn là tên property dạng text ở cấp wire; custom key deserializer cần khôi phục đúng kiểu Java.

## 9. Kiểm tra null, empty và missing

Ba trạng thái này không giống nhau:
- Property không có trong JSON (missing).
- Property có mặt với giá trị JSON null.
- Property có mặt với giá trị rỗng, ví dụ "", [] hoặc {}.

Một DTO mutable có thể nhận giá trị mặc định khi property bị thiếu. @JsonInclude(NON_NULL) có thể bỏ property null khi serialize. Khi đọc lại, missing field có thể vẫn thành null, nhưng với primitive hoặc constructor default thì kết quả có thể khác.

Ví dụ:

~~~java
public record Profile(
    String nickname,
    List<String> tags
) {}
~~~

Property test có thể tạo cả null và empty:

~~~java
@Provide
Arbitrary<Profile> profiles() {
    Arbitrary<String> nickname =
        Arbitraries.of(null, "", "Linh", "Minh");

    Arbitrary<List<String>> tags =
        Arbitraries.of(
            null,
            List.of(),
            List.of("java"),
            List.of("jackson", "json")
        );

    return Combinators.combine(nickname, tags).as(Profile::new);
}
~~~

Nếu mapper bỏ null khi ghi, test equality vẫn có thể qua nếu kiểu đích khôi phục null. Nhưng với primitive hoặc default value, cần kiểm tra rõ. Đừng gộp null và empty thành cùng một kỳ vọng nếu API phân biệt chúng.

Nếu cần kiểm tra missing riêng, tạo JSON fixture không có property và test deserialization trực tiếp. Round-trip từ object null có thể không tạo ra cùng trạng thái wire như một property explicit null.

## 10. BigDecimal: giá trị và scale có thể là hai invariant khác nhau

BigDecimal có cả giá trị số và scale. Ví dụ:

~~~java
new BigDecimal("1.0")
new BigDecimal("1.00")
~~~

Hai giá trị so sánh bằng compareTo() là tương đương, nhưng equals() trả false vì scale khác nhau.

Nếu hợp đồng chỉ quan tâm giá trị tiền, test:

~~~java
assertEquals(0, expected.amount().compareTo(actual.amount()));
~~~

Nếu scale biểu diễn số chữ số thập phân được công bố, test cả scale:

~~~java
assertEquals(expected.amount().scale(), actual.amount().scale());
~~~

Ví dụ property:

~~~java
record Price(BigDecimal amount, String currency) {}

@Property
void priceRoundTrip(@ForAll("prices") Price original)
        throws JsonProcessingException {

    String json = mapper.writeValueAsString(original);
    Price restored = mapper.readValue(json, Price.class);

    assertEquals(original.currency(), restored.currency());
    assertEquals(0, original.amount().compareTo(restored.amount()));
}
~~~

Generator nên tạo số trong phạm vi nghiệp vụ và scale được cho phép. Không chỉ sinh số nguyên nếu production có decimal, exponent hoặc giá trị rất nhỏ.

Nếu ứng dụng bật WRITE_BIGDECIMAL_AS_PLAIN hoặc custom serializer, hãy test bằng mapper production. Không so sánh raw JSON string để kiểm tra số vì 1E+3 và 1000 có thể biểu diễn cùng giá trị.

## 11. Date/time và múi giờ

Kiểu thời gian có các semantics khác nhau:

| Kiểu | Điều cần bảo toàn |
|---|---|
| LocalDate | Ngày lịch |
| LocalTime | Giờ địa phương |
| LocalDateTime | Ngày giờ không gắn timezone |
| OffsetDateTime | Ngày giờ cùng offset |
| Instant | Một thời điểm tuyệt đối trên timeline |
| ZonedDateTime | Thời điểm và zone ID nếu hợp đồng cần |

Với Java Time, đăng ký JavaTimeModule và cấu hình format nhất quán:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Property cho Instant có thể kiểm tra đúng thời điểm:

~~~java
record Event(Instant occurredAt) {}

@Property
void instantRoundTrip(@ForAll("instants") Instant original)
        throws JsonProcessingException {

    String json = mapper.writeValueAsString(new Event(original));
    Event restored = mapper.readValue(json, Event.class);

    assertEquals(original, restored.occurredAt());
}
~~~

Với ZonedDateTime, cần quyết định có phải bảo toàn ZoneId khu vực như Asia/Ho_Chi_Minh hay chỉ cần bảo toàn instant/offset. Một format chỉ chứa offset có thể không đủ để khôi phục tên zone ban đầu. Nếu ZoneId có ý nghĩa nghiệp vụ, hãy serialize nó rõ ràng hoặc dùng DTO có field zone riêng.

## 12. Enum và tên wire

Nếu enum được serialize theo name() mặc định, round-trip có thể giữ enum constant. Nhưng annotation như @JsonValue, @JsonCreator hoặc custom deserializer có thể thay đổi cách biểu diễn.

Ví dụ:

~~~java
public enum Status {
    NEW,
    PAID,
    CANCELLED
}
~~~

Property test có thể sinh mọi enum constant:

~~~java
@Provide
Arbitrary<Status> statuses() {
    return Arbitraries.of(Status.values());
}
~~~

Nếu enum có wire value riêng:

~~~java
public enum Status {
    NEW("new"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    Status(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String wireValue() {
        return wireValue;
    }

    @JsonCreator
    public static Status fromWire(String value) {
        return Arrays.stream(values())
            .filter(status -> status.wireValue.equals(value))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Unknown status"));
    }
}
~~~

Hãy kiểm tra mọi enum constant và cả input cũ/alias nếu API hỗ trợ. Property round-trip cho enum hợp lệ không thay thế test riêng cho giá trị không được hỗ trợ.

## 13. Polymorphic type phải giữ đúng subtype

Nếu một property khai báo kiểu base class hoặc interface, JSON cần đủ thông tin để Jackson khôi phục subtype.

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "type"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank")
})
sealed interface Payment permits CardPayment, BankTransfer {}

record CardPayment(String lastFour) implements Payment {}
record BankTransfer(String accountReference) implements Payment {}

record Checkout(Payment payment) {}
~~~

Property test cần sinh nhiều subtype:

~~~java
@Provide
Arbitrary<Payment> payments() {
    Arbitrary<Payment> cards =
        Arbitraries.strings().numeric()
            .ofLength(4)
            .map(CardPayment::new);

    Arbitrary<Payment> transfers =
        Arbitraries.strings().alpha()
            .ofMinLength(1)
            .ofMaxLength(20)
            .map(BankTransfer::new);

    return Arbitraries.oneOf(cards, transfers);
}
~~~

Sau round-trip, kiểm tra subtype:

~~~java
assertEquals(original.payment().getClass(), restored.payment().getClass());
assertEquals(original, restored);
~~~

Nếu type discriminator bị bỏ hoặc không được cấu hình đúng, Jackson có thể không biết subtype cần tạo. Đừng chỉ test một subtype vì lỗi thường xuất hiện khi một nhánh khác được serialize.

Chỉ bật polymorphic typing theo type metadata có kiểm soát và cấu hình subtype được phép. Không dùng default typing không giới hạn cho dữ liệu không tin cậy.

## 14. Field bị ignore, write-only và read-only

Không phải property nào cũng được kỳ vọng bảo toàn qua round-trip.

Ví dụ:

~~~java
public class UserDto {
    public String username;

    @JsonIgnore
    public String internalNote;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    public String password;
}
~~~

internalNote bị bỏ qua khi đọc/ghi theo annotation. password có thể được nhận khi deserialize nhưng không được phát khi serialize. Sau khi serialize rồi đọc lại, object khôi phục không nhất thiết có password như object ban đầu.

Test kiểu này cần định nghĩa equivalence chỉ trên các property thuộc wire contract:

~~~java
void assertPublicFieldsEqual(UserDto expected, UserDto actual) {
    assertEquals(expected.username, actual.username);
    assertNull(actual.internalNote);
    assertNull(actual.password);
}
~~~

Không nên nới test bằng cách bỏ qua mọi field khó so sánh. Hãy liệt kê chính xác field nào được phép mất và vì sao.

## 15. Custom serializer/deserializer cần round-trip pair

Nếu một kiểu có custom serializer nhưng deserializer không hiểu output của serializer, round-trip sẽ thất bại.

Ví dụ kiểu tiền:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

Giả sử serializer ghi:

~~~json
{
  "value": "1250.50",
  "unit": "VND"
}
~~~

Deserializer phải đọc đúng cùng wire structure. Property test nên tạo nhiều amount và currency hợp lệ, rồi kiểm tra Money được khôi phục theo invariant.

Một custom serializer/deserializer cần được đăng ký vào cùng ObjectMapper dùng trong test và production. Nếu test dùng mapper mới không có module, test không đại diện cấu hình thực tế.

Có thể kiểm tra thêm:
- Giá trị âm/dương.
- Zero và scale.
- Currency hợp lệ/không hợp lệ.
- Field thiếu hoặc null.
- Input cũ nếu custom deserializer hỗ trợ alias.
- Dữ liệu không hợp lệ phải bị từ chối, không bị chuyển thành default.

## 16. Round-trip với JsonNode và semantic JSON

Đôi khi muốn kiểm tra output JSON của một object mà không phụ thuộc whitespace hoặc thứ tự property. Có thể parse JSON thành JsonNode rồi so sánh cấu trúc:

~~~java
String firstJson = mapper.writeValueAsString(original);

T restored = mapper.readValue(firstJson, targetType);

String secondJson = mapper.writeValueAsString(restored);

JsonNode firstTree = mapper.readTree(firstJson);
JsonNode secondTree = mapper.readTree(secondJson);

assertEquals(firstTree, secondTree);
~~~

Test này kiểm tra JSON sau lần ghi đầu và lần ghi sau khi khôi phục có cấu trúc tương đương. Nó hữu ích khi property order hoặc khoảng trắng không thuộc contract.

Nếu serializer chuẩn hóa số, ngày giờ hoặc bỏ null, hai tree có thể khác nhưng DTO vẫn tương đương theo domain. Khi đó hãy kiểm tra invariant domain và viết canonicalization test riêng.

JsonNode equality không thay thế schema validation hoặc business validation. Nó chỉ so sánh cấu trúc tree theo semantics của node type.

## 17. Kiểm tra canonicalization và tính idempotent

Một số hệ thống chấp nhận nhiều cách biểu diễn đầu vào nhưng luôn ghi ra một dạng chuẩn. Ví dụ alias cũ được đọc, nhưng khi serialize chỉ phát tên property mới.

Có thể định nghĩa:

~~~text
canonicalize(json) = serialize(deserialize(json))
~~~

Một thuộc tính hữu ích là canonicalization idempotent:

~~~text
canonicalize(canonicalize(json)) = canonicalize(json)
~~~

Ví dụ:

~~~java
String canonicalize(String json) throws JsonProcessingException {
    UserDto value = mapper.readValue(json, UserDto.class);
    return mapper.writeValueAsString(value);
}

@Property
void canonicalizationIsIdempotent(@ForAll("validJsonInputs") String json)
        throws JsonProcessingException {

    String once = canonicalize(json);
    String twice = canonicalize(once);

    assertEquals(
        mapper.readTree(once),
        mapper.readTree(twice)
    );
}
~~~

Generator validJsonInputs phải tạo JSON hợp lệ theo contract của UserDto, có thể từ DTO được sinh rồi serialize hoặc từ các fixture có alias được hỗ trợ. Nếu tạo chuỗi JSON tùy ý, phần lớn trường hợp chỉ kiểm tra parser từ chối input.

Idempotence hữu ích khi có alias, default value, normalization, date format hoặc custom serializer. Nếu mỗi lần ghi/đọc lại làm giá trị thay đổi thêm, có thể tồn tại lỗi rounding, timezone conversion hoặc normalization không ổn định.

## 18. Test round-trip không đồng nghĩa test parser từ chối input sai

Round-trip property thường dùng generator hợp lệ. Nó trả lời câu hỏi: dữ liệu hợp lệ có được giữ nguyên qua serialization không?

Một nhóm test khác phải kiểm tra dữ liệu không hợp lệ:
- Enum value không tồn tại.
- Number vượt range.
- Ngày sai format.
- Root shape sai.
- Required property bị thiếu.
- Unknown property theo strict policy.
- String hoặc nesting vượt giới hạn.
- Type discriminator không được hỗ trợ.

Ví dụ:

~~~java
@Example
void rejectsUnknownStatus() {
    String json = """
        {"status":"ARCHIVED"}
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(json, OrderRequest.class)
    );
}
~~~

Exception cụ thể tùy DTO, deserializer và cấu hình. Hãy kiểm tra loại lỗi hoặc error code ứng dụng phù hợp, không phụ thuộc quá mức vào message nguyên văn.

Tách test valid round-trip và invalid-input rejection giúp biết chính xác property nào bị vi phạm.

## 19. Shrinking giúp tìm ví dụ nhỏ tái hiện lỗi

Khi một property thất bại, jqwik cố thu nhỏ dữ liệu đầu vào theo quy tắc của Arbitrary. Ví dụ một Order có 20 item thất bại, framework có thể giảm số item, rút ngắn chuỗi hoặc giảm giá trị số để tìm case tối giản.

Một failure report có thể chỉ ra:
- Seed hoặc sample để tái hiện.
- Giá trị đầu vào đã thu nhỏ.
- Property thất bại.
- Exception/assertion xảy ra.
- Số lần thử.

Shrinking hữu ích vì lỗi round-trip thường chỉ xuất hiện ở một tổ hợp nhỏ, ví dụ:
- String chứa quote ngay trước backslash.
- List rỗng nhưng property được bỏ qua khi serialize.
- BigDecimal có scale âm hoặc exponent.
- Date ở biên ngày chuyển timezone.
- Map key chứa ký tự đặc biệt.

Không nên bỏ qua minimized sample. Hãy biến nó thành regression example hoặc thêm vào generator edge case để lỗi không quay lại.

## 20. Seed và khả năng tái hiện test

Property-based test tạo dữ liệu theo seed. Khi test thất bại, cần giữ thông tin seed/sample trong CI output để có thể tái hiện.

Không nên dùng random generator tự viết với nguồn ngẫu nhiên không kiểm soát rồi chỉ log thông báo test failed. Framework như jqwik quản lý seed và cung cấp cách replay theo báo cáo của nó.

Khi sửa lỗi:
1. Lấy seed/sample từ failure report.
2. Tái hiện trong local.
3. Xác định invariant bị vi phạm.
4. Sửa serializer, deserializer hoặc model.
5. Thêm regression example nếu case đặc biệt quan trọng.
6. Chạy lại property với seed cũ và nhiều sample mới.

Property test không thay thế test deterministic. Các ví dụ đã từng gây lỗi nên được giữ lại để regression luôn chạy ngay cả khi generator hoặc seed thay đổi.

## 21. Kết hợp property-based test với example-based test

Một chiến lược tốt có hai lớp:

**Example-based tests**
- Một JSON mẫu đúng contract.
- Một JSON có null.
- Một JSON thiếu property.
- Một JSON có Unicode/quote/newline.
- Một JSON có date và decimal đặc biệt.
- Một JSON sai phải bị từ chối.

**Property-based tests**
- Hàng trăm object hợp lệ được sinh.
- Nhiều tổ hợp nested collection.
- Giá trị ở biên và giá trị ngẫu nhiên trong miền.
- Round-trip invariant.
- Canonicalization idempotence.
- Domain invariant sau deserialize.

Example test dễ đọc và bảo vệ case cụ thể. Property test mở rộng không gian đầu vào và có thể phát hiện tổ hợp mà người viết test không nghĩ tới.

Không cần mọi test đều có hàng nghìn tries. Bắt đầu với số lần thử đủ nhanh trong CI, sau đó chạy profile nhiều tries hơn theo lịch hoặc trong pipeline nightly nếu thời gian phù hợp.

## 22. Kiểm tra cấu hình mapper production

Test round-trip chỉ đáng tin khi dùng cùng cấu hình với ứng dụng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Nếu production có naming strategy, mix-in, custom module, @JsonView, filter provider, polymorphic type configuration, coercion policy, StreamReadConstraints, inclusion policy hoặc custom serializer/deserializer thì test phải dựng mapper từ cùng factory/configuration hoặc dùng bean/factory cấu hình chung.

Đừng tạo một ObjectMapper mặc định riêng trong test nếu production mapper có nhiều module. Điều đó có thể khiến test xanh nhưng ứng dụng lỗi ở LocalDate, Optional, alias hoặc polymorphic type.

Cũng nên kiểm tra version Jackson của test runtime và production runtime giống nhau. Một số hành vi và API thay đổi giữa các phiên bản.

## 23. Property-based testing cho JSON views và filters

@JsonView và property filter có thể làm output phụ thuộc vào context. Khi dùng các cơ chế này, round-trip phải xác định view/filter nào đang được áp dụng.

Một object serialize dưới PublicView có thể bỏ internal fields. Deserialize JSON đó về DTO đầy đủ không thể khôi phục các field đã bị lược bỏ.

Vì vậy, property cần diễn đạt đúng:
- Public view chỉ bảo toàn public fields.
- Admin view bảo toàn tập field rộng hơn.
- Filter output chỉ chứa property được chọn.
- Deserialize không được giả định có thể khôi phục dữ liệu chưa từng được ghi.

Nếu một property test dùng writer không có view nhưng production dùng view, test sẽ không đại diện. Hãy dùng writerWithView() hoặc ObjectWriter đã cấu hình và so sánh theo contract của view.

## 24. Kiểm tra collection, order và dữ liệu lớn

Generator nên bao phủ kích thước collection từ rỗng đến giới hạn được phép. Ví dụ nếu API cho phép tối đa 100 item, hãy sinh:
- 0 item nếu hợp lệ.
- 1 item.
- Một số lượng trung bình.
- 99 và 100 item.
- 101 item trong test rejection riêng.

Không nên chỉ sinh list có kích thước nhỏ cố định. Một lỗi có thể xuất hiện khi list rỗng, khi phần tử cuối cùng được ghi hoặc khi collection vượt buffer nội bộ.

Với list có thứ tự, assert list equality. Với Set, assert set equality. Với sorted collection, kiểm tra comparator/order nếu đó là invariant. Với queue hoặc custom collection, xác định rõ serializer ghi thứ tự nào và deserializer khôi phục ra sao.

Đối với payload rất lớn, property test có thể tạo kích thước vừa phải để chạy nhanh; performance/load test riêng kiểm tra giới hạn và memory.

## 25. Round-trip qua nhiều định dạng

Jackson có các module cho XML, YAML, CSV và những định dạng khác. Invariant phải được xác định theo khả năng của từng format.

JSON và YAML có thể biểu diễn object/array lồng nhau khá tự nhiên. CSV là bảng phẳng nên không thể bảo toàn mọi cấu trúc nested nếu không có mapping riêng. XML có attribute, element, namespace và wrapper semantics; hai cấu trúc XML khác nhau có thể ánh xạ vào cùng DTO.

Nếu test nhiều mapper:

~~~java
String json = jsonMapper.writeValueAsString(value);
T fromJson = jsonMapper.readValue(json, type);

String yaml = yamlMapper.writeValueAsString(value);
T fromYaml = yamlMapper.readValue(yaml, type);

String xml = xmlMapper.writeValueAsString(value);
T fromXml = xmlMapper.readValue(xml, type);
~~~

Hãy kiểm tra từng kết quả theo contract của định dạng đó. Không giả định cùng một DTO sẽ giữ nguyên mọi chi tiết khi chuyển JSON -> XML -> JSON. CSV có thể cần DTO row riêng hoặc flattening adapter.

Cross-format test hữu ích khi ứng dụng hỗ trợ nhiều integration format, nhưng không nên gộp tất cả thành một assertion chung mà không xét khác biệt biểu diễn.

## 26. Kiểm tra giới hạn độ sâu và string cùng với round-trip

Nếu ObjectMapper dùng StreamReadConstraints, generator hợp lệ phải tạo dữ liệu nằm trong giới hạn. Property test có thể:
- Sinh depth trong phạm vi cho phép.
- Kiểm tra depth tối đa được đọc thành công.
- Tạo một payload vượt giới hạn và xác nhận parser từ chối.
- Sinh string ở sát maxStringLength.
- Tạo number token vượt maxNumberLength trong test rejection.

Round-trip từ object Java không luôn tạo được input vượt giới hạn theo cách mong muốn, vì serializer có thể chuẩn hóa hoặc giới hạn output. Với test rejection, hãy tạo JSON fixture trực tiếp hoặc viết generator JSON có kiểm soát.

Phân biệt:
- Property bảo toàn cho dữ liệu hợp lệ.
- Property từ chối cho dữ liệu vượt policy.
- Performance test cho payload lớn và concurrency.

Đừng biến property round-trip thành cách đo hiệu năng. Mục tiêu và công cụ đo khác nhau.

## 27. Một ví dụ test class hoàn chỉnh hơn

Ví dụ kết hợp DTO lồng, Java Time, generator và invariant:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDate;
import java.util.List;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class OrderRoundTripProperties {

    record Item(String sku, int quantity) {}

    record Order(
        String id,
        LocalDate orderedOn,
        List<Item> items
    ) {}

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

    @Provide
    Arbitrary<Item> items() {
        return Combinators.combine(
            Arbitraries.strings().alpha()
                .ofMinLength(1)
                .ofMaxLength(12),
            Arbitraries.integers().between(1, 100)
        ).as(Item::new);
    }

    @Provide
    Arbitrary<Order> orders() {
        return Combinators.combine(
            Arbitraries.strings().alpha()
                .ofMinLength(1)
                .ofMaxLength(20),
            Arbitraries.dates().between(
                LocalDate.of(2000, 1, 1),
                LocalDate.of(2040, 12, 31)
            ),
            items().list().ofMaxSize(20)
        ).as(Order::new);
    }

    @Property(tries = 500)
    void orderRoundTrip(@ForAll("orders") Order original)
            throws JsonProcessingException {

        String json = mapper.writeValueAsString(original);
        Order restored = mapper.readValue(json, Order.class);

        assertEquals(original, restored);
    }
}
~~~

Ví dụ dùng Arbitraries.dates() để tạo LocalDate trong một khoảng xác định. Các generator có thể điều chỉnh theo domain thực tế. Với test class đầy đủ, hãy bảo đảm jqwik engine được nhận diện bởi JUnit Platform và các dependency Jackson có cùng version.

## 28. Tránh những assertion dễ gây false positive hoặc false negative

Một số lỗi trong cách viết test:

| Cách test | Vấn đề |
|---|---|
| So sánh raw JSON string | Nhạy với whitespace và thứ tự property |
| Chỉ kiểm tra JSON không null | Không chứng minh dữ liệu được giữ |
| Chỉ kiểm tra ID | Bỏ sót field nested, list và null |
| So sánh mọi field dù có @JsonIgnore | Test sai hợp đồng |
| Dùng generator chỉ tạo ASCII | Bỏ qua Unicode và escaping |
| Chỉ tạo collection có một item | Bỏ sót empty/multiple/limit cases |
| Chỉ test mapper mặc định | Không phản ánh production config |
| Sinh dữ liệu ngoài domain trong round-trip property | Thất bại trước khi kiểm tra serialization |
| Bỏ qua failure sample | Lỗi có thể tái xuất hiện |

Một assertion tốt kiểm tra đúng invariant và có thông điệp đủ rõ để biết field nào bị thay đổi.

## 29. Quy trình điều tra khi round-trip property thất bại

Khi property test tìm thấy một sample lỗi:

1. Lưu seed và sample đã thu nhỏ.
2. Xác định lỗi ở serialize, parse, creator hay assertion.
3. Kiểm tra JSON trung gian.
4. So sánh original và restored theo từng field.
5. Xác định khác biệt là mất dữ liệu, chuẩn hóa có chủ ý hay bug.
6. Kiểm tra annotation, module, naming strategy và feature.
7. Viết regression example cho case tối giản.
8. Chạy lại property với seed cũ và nhiều sample mới.

Ví dụ:
- Nếu field null bị bỏ khi ghi, kiểm tra @JsonInclude.
- Nếu LocalDate không đọc được, kiểm tra JavaTimeModule và format.
- Nếu subtype bị đổi thành base class, kiểm tra type metadata.
- Nếu BigDecimal đổi scale, xác định scale có thuộc invariant không.
- Nếu Map có thứ tự khác, dùng semantic equality thay vì raw JSON.
- Nếu string bị đổi newline, kiểm tra serializer/deserializer custom và encoding.

Không nên sửa test để bỏ qua khác biệt trước khi xác định contract. Một property test thất bại có thể chỉ ra lỗi trong serializer, nhưng cũng có thể phơi bày giả định sai về semantics của model.

## 30. Kết hợp regression fixtures và property tests trong CI

Một pipeline test có thể gồm:

~~~text
Unit tests
  - ví dụ JSON cụ thể
  - null/missing/unknown field
  - custom serializer/deserializer
       |
       v
Property-based tests
  - round-trip invariant
  - nested structures
  - boundary values
  - canonicalization
       |
       v
Integration tests
  - mapper production configuration
  - API message converter
  - module/version compatibility
       |
       v
Performance tests
  - payload lớn
  - allocation/GC
  - throughput và tail latency
~~~

Trong CI:
- Chạy số tries vừa đủ để giữ feedback nhanh.
- Ghi lại seed khi thất bại.
- Giữ regression sample trong source control.
- Chạy thêm profile nhiều tries theo lịch nếu cần.
- Không phụ thuộc vào thứ tự test hoặc state dùng chung có thể thay đổi.
- Dùng cùng mapper factory/configuration với ứng dụng.

Property test cần deterministic về cấu hình và dễ tái hiện failure. Đừng để test phụ thuộc thời gian hiện tại, timezone mặc định của máy hoặc locale mặc định nếu những yếu tố đó không được cố định.

## Kết luận

Kiểm thử thuộc tính bảo toàn qua vòng ghi rồi đọc giúp xác nhận dữ liệu hợp lệ không bị mất hoặc biến đổi ngoài ý muốn khi Jackson serialize và deserialize. Invariant cơ bản là decode(encode(value)) tương đương với value theo hợp đồng của ứng dụng. Equality có thể đủ cho record đơn giản; BigDecimal, Map, date/time, polymorphic model và field bị ignore cần phép so sánh phù hợp với semantics.

Hãy dùng jqwik để sinh DTO hợp lệ, kết hợp generator có chủ đích cho nested collections và edge cases, rồi kiểm tra round-trip, canonicalization và các invariant domain. Giữ example-based tests cho những case quan trọng, lưu seed/minimized sample khi lỗi và dựng mapper đúng cấu hình production. Round-trip property không thay thế test từ chối input sai, schema validation hoặc performance test; chúng bổ sung cho nhau để kiểm tra cả tính bảo toàn lẫn độ tin cậy của pipeline serialization.

