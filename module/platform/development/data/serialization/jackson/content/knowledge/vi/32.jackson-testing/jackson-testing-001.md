# Thiết kế dữ liệu mẫu cho đọc và ghi độc lập

Kiểm thử Jackson cần dữ liệu mẫu để xác nhận hai hợp đồng riêng: dữ liệu bên ngoài được đọc thành object Java như thế nào, và object Java được ghi ra định dạng bên ngoài như thế nào. Hai chiều này liên quan với nhau nhưng không nên phụ thuộc vào cùng một lần round-trip.

Một test chỉ serialize object rồi deserialize lại bằng cùng ObjectMapper có thể thành công ngay cả khi cả hai chiều cùng sai. Ví dụ, mapper ghi tên property thành `user_name` trong khi hợp đồng yêu cầu `userName`; mapper cũng đọc được chính `user_name` đó nên round-trip vẫn qua. Test độc lập cần có fixture đầu vào và đầu ra được xác định từ hợp đồng hoặc nguồn tham chiếu bên ngoài.

Thiết kế fixture tốt giúp phát hiện lỗi đổi tên property, sai kiểu số, thiếu field, null handling, thứ tự collection, polymorphism, custom serializer và thay đổi cấu hình mapper. Bài này trình bày cách tổ chức dữ liệu mẫu riêng cho deserialize và serialize, cách chọn giá trị đại diện, cách so sánh output theo ngữ nghĩa định dạng và cách duy trì fixture qua các phiên bản.

## 1. Hai chiều kiểm thử cần hai nguồn dữ liệu kỳ vọng

Jackson thường thực hiện hai hướng chuyển đổi:

~~~text
Đọc / Deserialize
Wire data  ---------------------->  Java object
             ObjectMapper.readValue(...)

Ghi / Serialize
Java object --------------------->  Wire data
             ObjectMapper.writeValue(...)
~~~

Với kiểm thử độc lập:

~~~text
Fixture đầu vào đã biết
          |
          v
      ObjectMapper
          |
          v
     Java object
          |
          v
     Assertions

Java object được tạo độc lập
          |
          v
      ObjectMapper
          |
          v
   Wire output thực tế
          |
          v
So sánh với fixture đầu ra chuẩn
~~~

**Test đọc** bắt đầu từ một tài liệu JSON/XML/binary được chuẩn bị trước. Test xác nhận object Java có đúng giá trị, kiểu, trạng thái null và cấu trúc lồng nhau hay không.

**Test ghi** bắt đầu từ một object Java được tạo độc lập. Test xác nhận output có đúng tên field, kiểu wire, cấu trúc, null policy, format ngày giờ và các quy tắc serialization hay không.

Không tạo fixture kỳ vọng bằng cách gọi chính mapper đang được kiểm thử trong cùng test. Nếu dùng mapper để sinh expected output, test chỉ chứng minh mapper nhất quán với chính nó.

## 2. Vì sao chỉ kiểm thử round-trip là chưa đủ?

Một round-trip cơ bản:

~~~java
String json = mapper.writeValueAsString(user);
User restored = mapper.readValue(json, User.class);
assertEquals(user, restored);
~~~

Test này hữu ích để kiểm tra một số đặc tính nội bộ, nhưng có thể bỏ sót lỗi hợp đồng.

Ví dụ class:

~~~java
public class User {
    @JsonProperty("user_name")
    private String name;
}
~~~

Nếu hợp đồng thực tế yêu cầu `userName`, mapper vẫn ghi `user_name` rồi đọc lại `user_name` thành công. Round-trip không phát hiện sai tên field.

Một số lỗi khác cũng có thể bị che:

- Serializer và deserializer cùng dùng một naming strategy sai.
- Serializer ghi enum theo ordinal và deserializer cũng đọc ordinal đó, trong khi hợp đồng yêu cầu tên enum.
- Serializer làm tròn BigDecimal rồi deserializer đọc lại giá trị đã làm tròn.
- Cả hai chiều cùng bỏ qua một property quan trọng.
- Date serializer và deserializer cùng dùng timezone không đúng nhưng test chỉ so sánh object sau round-trip.
- Serializer và deserializer cùng áp dụng sai discriminator của subtype.

Round-trip nên là một lớp kiểm thử bổ sung. Nó không thay thế fixture độc lập cho từng chiều.

## 3. Fixture phải đại diện cho hợp đồng bên ngoài

Fixture là dữ liệu mẫu có tên, vị trí và mục đích rõ ràng. Nó có thể là:

- JSON text.
- XML document.
- Smile hoặc CBOR binary.
- BSON document.
- Avro payload đi cùng writer schema.
- Protobuf payload đi cùng message descriptor.
- File dữ liệu do đối tác hoặc hệ thống cũ phát hành.

Một fixture tốt phải trả lời được:

1. Nó đại diện cho phiên bản hợp đồng nào?
2. Dùng để kiểm tra deserialize hay serialize?
3. Giá trị nào là quan trọng đối với test?
4. Nguồn kỳ vọng đến từ đâu?
5. Có field nào cố ý thiếu, null, lạ hoặc ở giá trị biên không?
6. Fixture có phụ thuộc thứ tự, encoding, schema hay timezone không?

Không nên đặt một file `sample.json` dùng cho mọi test mà không nói rõ nó đại diện cho tình huống nào. Tên fixture nên thể hiện mục tiêu như `user-v1-minimal.json`, `user-v2-with-extensions.json` hoặc `payment-decimal-boundary.json`.

## 4. Tổ chức fixture trong source tree

Với Maven/Gradle project thông thường, dữ liệu test có thể nằm trong `src/test/resources`:

~~~text
src/
  main/
    java/
      ...
  test/
    java/
      com/example/serialization/
        UserReadTest.java
        UserWriteTest.java
        UserRoundTripTest.java
  test/
    resources/
      jackson/
        user/
          read/
            v1-minimal.json
            v1-all-fields.json
            v1-missing-optional.json
            v1-null-fields.json
            v1-unknown-property.json
          write/
            expected-minimal.json
            expected-all-fields.json
            expected-null-policy.json
          invalid/
            malformed.json
            wrong-number-shape.json
        payment/
          read/
          write/
        xml/
          read/
          write/
        binary/
          smile/
          cbor/
          bson/
          avro/
          protobuf/
~~~

Tách `read` và `write` giúp người đọc biết fixture nào là input bên ngoài và fixture nào là expected output. Không nên dùng chung một file cho cả hai mục tiêu chỉ để tiết kiệm vài dòng test.

Với dự án lớn, có thể nhóm theo bounded context, message type hoặc schema version. Điều quan trọng là vị trí phải ổn định và không phụ thuộc thứ tự chạy test.

## 5. Đặt tên fixture theo mục đích và phiên bản

Tên fixture nên cho biết:

- Kiểu dữ liệu hoặc message: `user`, `payment`, `order-created`.
- Hướng kiểm thử: `read`, `write`, `invalid` hoặc `roundtrip`.
- Phiên bản hợp đồng nếu có: `v1`, `v2`.
- Trường hợp cụ thể: `minimal`, `complete`, `unknown-field`, `decimal-boundary`.

Ví dụ:

~~~text
user/read/v1-minimal.json
user/read/v1-with-unknown-field.json
user/read/v1-null-email.json
user/write/v1-expected-defaults.json
user/write/v1-expected-omitted-null.json
~~~

Tránh tên chung chung như `test1.json`, `new.json`, `final.json` hoặc `sample-latest.json`. Tên chung khiến fixture khó tìm và dễ bị ghi đè khi hợp đồng tiến hóa.

## 6. Fixture đọc: dữ liệu wire được chuẩn bị trước

Một fixture đọc phải được xem như một message thực sự mà ứng dụng có thể nhận:

~~~json
{
  "id": 42,
  "userName": "Mai Nguyen",
  "active": true,
  "roles": ["ADMIN", "EDITOR"]
}
~~~

Test deserialize:

~~~java
@Test
void readsUserDocument() throws Exception {
    String json = readFixture("jackson/user/read/v1-all-fields.json");

    User user = mapper.readValue(json, User.class);

    assertEquals(42L, user.getId());
    assertEquals("Mai Nguyen", user.getUserName());
    assertTrue(user.isActive());
    assertEquals(List.of("ADMIN", "EDITOR"), user.getRoles());
}
~~~

Fixture được lưu như dữ liệu đầu vào độc lập. Assertions kiểm tra object Java sau khi Jackson bind.

Không tạo JSON input từ `mapper.writeValueAsString(new User(...))` trong test đọc. Làm như vậy sẽ biến test đọc thành một nửa của round-trip và có thể tái sử dụng lỗi serializer.

## 7. Fixture ghi: expected wire data được xác định độc lập

Test ghi bắt đầu bằng object Java được tạo từ constructor, builder hoặc factory test:

~~~java
@Test
void writesUserDocument() throws Exception {
    User user = new User(
        42L,
        "Mai Nguyen",
        true,
        List.of("ADMIN", "EDITOR")
    );

    String actual = mapper.writeValueAsString(user);
    String expected = readFixture(
        "jackson/user/write/v1-expected-all-fields.json"
    );

    assertJsonEquals(expected, actual);
}
~~~

Fixture expected phải được viết từ hợp đồng JSON, ví dụ tài liệu API, mẫu do đối tác cung cấp hoặc một wire example được duyệt. Không sinh nó bằng cùng ObjectMapper rồi chép lại mà không có kiểm chứng độc lập.

Test ghi nên kiểm tra cả property bắt buộc phải xuất hiện và property không được xuất hiện. Chỉ kiểm tra `actual` không rỗng hoặc deserialize lại thành object không đủ để xác nhận wire contract.

## 8. Đọc fixture từ classpath

Fixture trong `src/test/resources` nên được đọc qua classpath để test chạy được từ IDE, Gradle, Maven và CI:

~~~java
static String readFixture(String resourceName) throws IOException {
    ClassLoader classLoader =
        Thread.currentThread().getContextClassLoader();

    try (InputStream input =
             classLoader.getResourceAsStream(resourceName)) {
        if (input == null) {
            throw new FileNotFoundException(
                "Missing test fixture: " + resourceName
            );
        }
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Không dùng đường dẫn tuyệt đối trên máy cá nhân như `C:\Users\... ` hoặc `/home/... `. Đường dẫn tuyệt đối làm test phụ thuộc môi trường và dễ hỏng trên CI.

Nếu fixture binary, đọc trực tiếp byte:

~~~java
static byte[] readBinaryFixture(String resourceName) throws IOException {
    try (InputStream input = resource(resourceName)) {
        return input.readAllBytes();
    }
}
~~~

Trong ví dụ trên, `resource(...)` là helper trả về InputStream và ném lỗi rõ nếu không tìm thấy file. Không chuyển binary bytes thành String để đọc vì có thể làm hỏng dữ liệu.

## 9. Helper đọc resource nên báo lỗi rõ ràng

Một helper dùng chung:

~~~java
static InputStream resource(String name) throws IOException {
    InputStream input = Thread.currentThread()
        .getContextClassLoader()
        .getResourceAsStream(name);

    if (input == null) {
        throw new FileNotFoundException(
            "Test resource not found: " + name
        );
    }
    return input;
}
~~~

Sau đó:

~~~java
static String readUtf8(String name) throws IOException {
    try (InputStream input = resource(name)) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Tên resource nên dùng dấu `/` và không có tiền tố `src/test/resources`, vì thư mục resources đã nằm trên classpath.

## 10. Kiểm tra JSON theo cấu trúc thay vì raw string

Hai JSON object sau tương đương về cấu trúc dữ liệu:

~~~json
{"id":42,"name":"Mai"}
~~~

~~~json
{
  "name": "Mai",
  "id": 42
}
~~~

Thứ tự property trong object không nên được dùng làm một phần hợp đồng JSON thông thường. Nếu test so sánh chuỗi nguyên văn, thay đổi indentation hoặc thứ tự key có thể làm test thất bại dù dữ liệu tương đương.

Có thể parse cả expected và actual thành JsonNode:

~~~java
static void assertJsonEquals(
        ObjectMapper mapper,
        String expected,
        String actual) throws JsonProcessingException {

    JsonNode expectedNode = mapper.readTree(expected);
    JsonNode actualNode = mapper.readTree(actual);

    assertEquals(expectedNode, actualNode);
}
~~~

JsonNode equality so sánh cấu trúc object và array. Object field order không quan trọng; array order vẫn quan trọng. Kiểu node cũng có thể quan trọng: số nguyên và số thập phân không nên bị coi là giống nhau nếu contract phân biệt.

Nếu test cần xác nhận chính xác lexical representation như `1.00` so với `1.0`, cần assertion bổ sung hoặc so sánh raw output theo mục tiêu đó.

## 11. Khi nào cần so sánh raw bytes?

Raw byte comparison phù hợp khi byte sequence là một phần hợp đồng:

- Chữ ký số được tính trên byte canonical.
- Hash hoặc checksum phụ thuộc byte.
- Một giao thức yêu cầu encoding/canonicalization cụ thể.
- Golden binary fixture phải giữ nguyên chính xác.
- Test cần xác nhận header, magic bytes hoặc framing.

Không nên so sánh raw bytes chỉ vì output là binary. Một số format cho phép nhiều cách mã hóa tương đương; serializer có thể thay đổi encoding hợp lệ giữa phiên bản mà không đổi dữ liệu.

Với binary format, có thể cần kiểm tra cả:

- Bytes chính xác khi yêu cầu byte-stability.
- Wire token/type marker khi cần xác nhận kiểu.
- Giá trị sau decode bằng parser độc lập.

Chọn mức assertion theo hợp đồng thực tế.

## 12. Fixture cho trường hợp tối thiểu

Một fixture minimal chỉ chứa field bắt buộc:

~~~json
{
  "id": 1
}
~~~

Test đọc cần xác nhận:

- Jackson tạo được object.
- Field bắt buộc được gán đúng.
- Optional field có default hoặc null theo thiết kế.
- Không vô tình gán giá trị từ trạng thái trước đó.

Test ghi minimal cần xác nhận:

- Các field mặc định có được ghi hay không.
- Null field có bị bỏ qua không.
- Empty collection có được ghi không.
- Giá trị default có được phát ra theo hợp đồng không.

Fixture minimal đặc biệt hữu ích khi DTO có nhiều property optional. Nó giúp phát hiện việc vô tình biến field mới thành required.

## 13. Fixture cho trường hợp đầy đủ

Fixture complete nên có tất cả field quan trọng:

~~~json
{
  "id": 42,
  "userName": "Mai Nguyen",
  "email": "mai@example.test",
  "active": true,
  "roles": ["ADMIN", "EDITOR"],
  "profile": {
    "city": "Da Nang",
    "postalCode": "550000"
  }
}
~~~

Nó giúp kiểm tra mapping đồng thời giữa property, nested object, collection và scalar.

Không nên chỉ dùng một fixture complete cho tất cả test. Một fixture lớn có thể khiến test khó xác định nguyên nhân khi lỗi xảy ra. Hãy giữ một số fixture nhỏ theo mục tiêu và thêm complete fixture như một bài kiểm tra tích hợp.

## 14. Fixture cho missing, null và empty

Ba trạng thái thường bị nhầm:

**Missing:**

~~~json
{
  "name": "Mai"
}
~~~

**Explicit null:**

~~~json
{
  "name": "Mai",
  "email": null
}
~~~

**Empty string:**

~~~json
{
  "name": "Mai",
  "email": ""
}
~~~

Collection cũng có các trạng thái tương tự:

~~~json
{"roles": []}
~~~

~~~json
{"roles": null}
~~~

~~~json
{}
~~~

Mỗi trạng thái có thể tạo kết quả khác nhau trong Java:

- Missing có thể giữ initializer hoặc default constructor.
- Null có thể gọi setter với null.
- Empty string là một giá trị String có độ dài 0.
- Empty array thường tạo collection rỗng.
- Null collection có thể tạo null reference.
- Missing collection có thể giữ default hoặc null tùy cách tạo object.

Hãy tạo fixture riêng nếu hợp đồng phân biệt các trạng thái này.

## 15. Fixture cho giá trị số biên

Không chỉ dùng số nhỏ như 1, 2 hoặc 100. Hãy tạo các fixture kiểm tra:

- Integer.MIN_VALUE và Integer.MAX_VALUE.
- Long.MIN_VALUE và Long.MAX_VALUE.
- Số nguyên vượt 64-bit nếu target là BigInteger.
- Decimal có nhiều chữ số.
- Decimal có trailing zeros.
- Decimal exponent dương/âm.
- Float/double có giá trị gần biên.

Ví dụ:

~~~json
{
  "small": -2147483648,
  "large": 9223372036854775807,
  "amount": 12345678901234567890.123400
}
~~~

Lưu ý JSON number có thể được parser xử lý theo kiểu Number khác nhau tùy target type và feature. Nếu fixture có BigDecimal precision lớn, cần chắc chắn parser không đi qua double.

Với BigDecimal, test cả giá trị số học và scale nếu scale là một phần yêu cầu:

~~~java
assertEquals(4, result.getAmount().scale());
assertEquals(
    0,
    new BigDecimal("123.4500").compareTo(result.getAmount())
);
~~~

## 16. Fixture cho ngày giờ và timezone

Ngày giờ là nguồn lỗi phổ biến khi đọc/ghi. Fixture cần nói rõ:

- Instant hay LocalDateTime?
- Có timezone/offset không?
- Precision đến giây, millisecond hay nanosecond?
- Format ISO-8601 hay format tùy chỉnh?
- Có cho phép null không?

Ví dụ:

~~~json
{
  "createdAt": "2026-11-12T10:15:30Z",
  "scheduledAt": "2026-11-12T17:15:30+07:00",
  "businessDate": "2026-11-12"
}
~~~

Không dùng `new Date()` hoặc `Instant.now()` trong test expected. Giá trị thay đổi theo thời điểm chạy khiến test không ổn định.

Object ghi nên được tạo bằng thời điểm cố định:

~~~java
Instant createdAt = Instant.parse("2026-11-12T10:15:30Z");
~~~

Fixture expected phải được viết theo format hợp đồng và không được sinh bằng serializer đang test.

## 17. Fixture cho enum

Nếu hợp đồng dùng enum name:

~~~json
{
  "status": "PAID"
}
~~~

Nếu dùng `@JsonValue` hoặc custom serializer, wire value có thể khác tên Java:

~~~json
{
  "status": "paid"
}
~~~

Test đọc cần kiểm tra wire value được chuyển thành enum đúng. Test ghi cần kiểm tra enum Java được ghi ra đúng string contract.

Thêm fixture cho:

- Mỗi giá trị hợp lệ quan trọng.
- Giá trị không biết.
- Chữ hoa/chữ thường nếu contract quy định.
- Null và missing.

Không tạo expected bằng `status.name()` trong test ghi nếu mục tiêu là xác nhận tên wire; hãy ghi expected string trong fixture hoặc một constant độc lập đã được review.

## 18. Fixture cho polymorphic type

Nếu dùng `@JsonTypeInfo`, fixture cần kiểm tra discriminator:

~~~json
{
  "kind": "card",
  "amount": 250000,
  "lastFour": "1234"
}
~~~

Một fixture khác:

~~~json
{
  "kind": "bank-transfer",
  "amount": 500000,
  "bankCode": "ABC"
}
~~~

Test đọc phải xác nhận subtype thực tế:

~~~java
Payment payment = mapper.readValue(json, Payment.class);
assertInstanceOf(CardPayment.class, payment);
~~~

Test ghi cần xác nhận discriminator và field subtype:

~~~java
String actual = mapper.writeValueAsString(cardPayment);
assertJsonEquals(mapper, expectedFixture, actual);
~~~

Không chỉ kiểm tra object sau round-trip vì serializer và deserializer có thể cùng dùng sai discriminator.

## 19. Fixture cho unknown property

Một fixture có field chưa biết:

~~~json
{
  "id": 42,
  "name": "Mai",
  "futureField": {
    "enabled": true
  }
}
~~~

Test cần phản ánh policy:

- Mapper strict: kỳ vọng `UnrecognizedPropertyException`.
- Mapper tolerant: đọc được field đã biết.
- DTO có `@JsonAnySetter`: field chưa biết được giữ lại.

Không dùng cùng một expected behavior cho mọi mapper. Chính sách unknown field là một phần của contract.

## 20. Fixture cho lỗi cú pháp và lỗi kiểu

Tách fixture malformed syntax khỏi fixture JSON hợp lệ nhưng sai kiểu.

Malformed:

~~~json
{
  "id": 42,
  "name": "Mai",
~~~

Sai shape nhưng đúng cú pháp:

~~~json
{
  "id": {
    "value": 42
  },
  "name": "Mai"
}
~~~

Test đầu kiểm tra parser exception. Test thứ hai kiểm tra mapping exception. Nếu gom hai trường hợp vào một fixture invalid duy nhất, test khó xác nhận chính xác tầng xử lý lỗi.

## 21. Fixture cho custom serializer/deserializer

Custom serializer thường tồn tại để giữ wire format đặc biệt:

- Money thành object `{ "amount": ..., "currency": ... }`.
- Identifier thành string.
- Date dùng format riêng.
- Enum dùng code ngắn.
- Một kiểu domain được flatten thành scalar.

Với mỗi custom serializer/deserializer, nên có fixture độc lập:

~~~json
{
  "money": {
    "amount": "123.4500",
    "currency": "VND"
  }
}
~~~

Test đọc xác nhận object Money có đúng amount/currency. Test ghi xác nhận object Money tạo ra đúng JSON trên. Không để custom serializer và deserializer chỉ kiểm tra output của nhau.

Nếu serializer có nhiều nhánh theo null, subtype hoặc precision, hãy có fixture riêng cho từng nhánh quan trọng.

## 22. Fixture XML cần phản ánh cấu trúc XML

Với XmlMapper, fixture phải thể hiện đúng root element, attribute, child element, namespace và wrapper:

~~~xml
<user id="42" xmlns="urn:people">
    <name>Mai</name>
    <roles>
        <role>ADMIN</role>
        <role>EDITOR</role>
    </roles>
</user>
~~~

Test đọc phải xác nhận:

- Root có đúng local name và namespace URI.
- id được bind từ attribute.
- name được bind từ child element.
- roles được đọc từ wrapper và các item.

Test ghi bắt đầu từ Java object và so sánh XML theo cấu trúc, không nên phụ thuộc whitespace hoặc prefix nếu contract không yêu cầu.

## 23. So sánh XML theo cấu trúc

XML có thứ tự child element, nhưng thứ tự attribute không mang ý nghĩa. Prefix namespace cũng có thể thay đổi trong khi URI không đổi.

Vì vậy, expected XML nên được parse và so sánh theo cấu trúc hoặc kiểm tra XPath:

~~~java
String id = xpath.evaluate("/p:user/@id", document);
String name = xpath.evaluate(
    "/p:user/p:name/text()",
    document
);
~~~

Namespace prefix `p` trong XPath cần được ánh xạ tới đúng URI bằng NamespaceContext. Không dùng raw prefix từ tài liệu làm định danh.

Nếu thứ tự child element là một phần của XSD sequence, test phải xác nhận thứ tự đó. Nếu chỉ kiểm tra các node có tồn tại mà không kiểm tra thứ tự, test có thể bỏ sót lỗi schema.

## 24. Fixture binary phải được lưu dưới dạng bytes

Với Smile, CBOR hoặc BSON, fixture là file nhị phân:

~~~text
binary/
  smile/
    user-v1.bin
  cbor/
    user-v1.cbor
  bson/
    user-v1.bson
~~~

Không mở binary fixture như UTF-8 text và không chỉnh sửa bằng text editor. Lưu đúng byte sequence.

Test đọc:

~~~java
byte[] payload = readBinaryFixture(
    "jackson/binary/cbor/user-v1.cbor"
);

User user = cborMapper.readValue(payload, User.class);
~~~

Test ghi:

~~~java
byte[] actual = cborMapper.writeValueAsBytes(user);
~~~

Nếu encoding có thể thay đổi nhưng semantics không đổi, decode actual bằng parser phù hợp và so sánh cấu trúc/giá trị. Nếu byte stability là yêu cầu, dùng golden bytes được tạo bởi một nguồn tham chiếu độc lập và review rõ.

## 25. Fixture Avro phải đi cùng schema

Avro binary thường cần writer schema để giải mã. Chỉ lưu một file `.avro` hoặc raw payload mà không lưu schema tương ứng sẽ làm fixture khó hiểu và khó tái hiện.

Có thể tổ chức:

~~~text
avro/
  payment/
    v1/
      writer-schema.avsc
      reader-schema.avsc
      payment.bin
      expected.json
~~~

Test phải dùng writer schema chính xác của payload. Nếu đang kiểm tra schema evolution, giữ riêng writer schema và reader schema để xác nhận resolution.

Không dùng schema mới nhất để đọc một fixture cũ nếu mục tiêu là kiểm tra behavior của schema version cũ.

## 26. Fixture Protobuf phải đi cùng message definition

Protobuf binary payload cần descriptor/message definition để biết field number và kiểu dữ liệu. Giữ file `.proto` hoặc generated descriptor version tương ứng trong repository.

Ví dụ:

~~~text
protobuf/
  user/
    v1/
      user.proto
      user.bin
      expected.json
~~~

Khi test schema evolution, dùng generated message hoặc DynamicMessage theo descriptor cụ thể. Đừng đổi `.proto` cũ tại chỗ rồi giả định fixture cũ vẫn đại diện cho version cũ.

## 27. Fixture phải có provenance

Provenance là thông tin cho biết fixture đến từ đâu và tại sao được xem là chuẩn.

Nguồn có thể là:

- Ví dụ trong API contract đã được duyệt.
- Payload do hệ thống đối tác cung cấp.
- Message đã ẩn danh từ môi trường staging.
- Tài liệu schema hoặc specification.
- Golden output được tạo bởi implementation độc lập.
- Một payload versioned đã phát hành trong production.

Không nên ghi "expected output" nếu không ai biết ai xác nhận nó. Khi fixture thay đổi, reviewer cần hiểu thay đổi đó đến từ schema mới, bug fix hay vô tình cập nhật snapshot.

Có thể lưu provenance trong comment Markdown, README cạnh fixture hoặc metadata test riêng. Không nhúng metadata không thuộc contract vào JSON payload nếu consumer sẽ đọc nó như dữ liệu thật.

## 28. Không sinh expected fixture bằng code đang kiểm thử

Anti-pattern:

~~~java
String expected = mapper.writeValueAsString(user);
String actual = mapper.writeValueAsString(user);
assertEquals(expected, actual);
~~~

Test này luôn so sánh cùng một kết quả với chính nó.

Một dạng tinh vi hơn:

~~~java
Files.writeString(expectedPath, mapper.writeValueAsString(user));
~~~

Nếu chạy trong test, expected fixture sẽ tự cập nhật mỗi lần chạy và không còn là oracle độc lập.

Có thể dùng tool riêng để sinh fixture ban đầu, nhưng cần:

- Tool/implementation độc lập hoặc một nguồn contract có thẩm quyền.
- Review expected output trước khi commit.
- Ghi provenance và version.
- Không tự động ghi đè golden fixture trong test thường ngày.

## 29. Tạo object test độc lập với fixture expected

Object đầu vào cho test ghi có thể tạo bằng factory:

~~~java
static User aCompleteUser() {
    return new User(
        42L,
        "Mai Nguyen",
        "mai@example.test",
        true,
        List.of("ADMIN", "EDITOR")
    );
}
~~~

Expected JSON nằm trong file resource:

~~~json
{
  "id": 42,
  "userName": "Mai Nguyen",
  "email": "mai@example.test",
  "active": true,
  "roles": ["ADMIN", "EDITOR"]
}
~~~

Factory tạo object Java theo ý nghĩa nghiệp vụ. Fixture mô tả wire contract. Hai nguồn không được tạo ra từ cùng một phép serialize.

Nếu factory và fixture có giá trị lặp lại, đó không phải vấn đề. Sự lặp lại có chủ đích giúp test độc lập và dễ đọc.

## 30. Tránh dùng builder có logic giống serializer

Một builder test có thể vô tình sao chép logic production:

~~~java
User user = User.builder()
    .name("Mai")
    .wireName("userName")
    .build();
~~~

Nếu builder tự chuẩn hóa tên field hoặc giá trị wire, test có thể không còn độc lập với serializer.

Builder nên tạo domain state hoặc DTO state. Quy tắc mapping wire format phải nằm ở Jackson annotations/module/custom serializer được kiểm thử, không được lặp lại trong test factory.

## 31. Kiểm tra property presence, không chỉ giá trị

Trong test ghi, cần xác nhận field có mặt hay không:

~~~java
JsonNode actual = mapper.readTree(
    mapper.writeValueAsString(user)
);

assertTrue(actual.has("id"));
assertFalse(actual.has("internalNote"));
assertTrue(actual.has("email"));
~~~

Nếu `email` được phép null nhưng vẫn phải xuất hiện:

~~~java
assertTrue(actual.has("email"));
assertTrue(actual.get("email").isNull());
~~~

Nếu null phải bị loại bỏ:

~~~java
assertFalse(actual.has("email"));
~~~

`has()` và `hasNonNull()` có ý nghĩa khác nhau. `has()` trả true khi property tồn tại dù giá trị là null; `hasNonNull()` chỉ true khi node tồn tại và không null.

## 32. Kiểm tra field không mong muốn

Một serializer có thể vô tình phát thêm field nội bộ:

~~~json
{
  "id": 42,
  "name": "Mai",
  "passwordHash": "..."
}
~~~

Nếu contract không cho phép passwordHash xuất hiện, test ghi cần xác nhận field đó không có:

~~~java
assertFalse(actual.has("passwordHash"));
~~~

Fixture expected đầy đủ có thể phát hiện field thừa khi so sánh JsonNode. Assertion riêng giúp thông điệp lỗi dễ hiểu hơn đối với property nhạy cảm hoặc property có ý nghĩa bảo mật.

Không đưa dữ liệu thật hoặc bí mật vào fixture. Dùng giá trị giả nhưng có hình dạng đủ đại diện.

## 33. Kiểm tra thứ tự array và collection

JSON array có thứ tự. Nếu List Java có thứ tự nghiệp vụ, fixture phải giữ đúng thứ tự:

~~~json
{
  "steps": ["VALIDATE", "AUTHORIZE", "CAPTURE"]
}
~~~

Test ghi phải xác nhận đúng thứ tự. Nếu thay List bằng Set hoặc serializer sắp xếp ngoài ý muốn, test cần phát hiện.

Với collection không có thứ tự nghiệp vụ, hãy xác định contract có yêu cầu canonical order hay không. Không nên so sánh collection như Set nếu thứ tự trên wire vẫn có ý nghĩa với consumer.

## 34. Kiểm tra Map và property order

JSON object là tập property. Nếu contract không quy định canonical JSON, thứ tự key thường không nên là assertion chính.

Map implementation có thể giữ insertion order hoặc không. Nếu chữ ký số, hash hoặc canonicalization phụ thuộc byte, cần một quy tắc canonical JSON riêng thay vì dựa vào HashMap hoặc thứ tự tình cờ.

Ví dụ:

~~~java
Map<String, Object> values = new LinkedHashMap<>();
values.put("first", 1);
values.put("second", 2);
~~~

Nếu order không quan trọng, so sánh JsonNode. Nếu order là một phần của canonical wire contract, test byte/string theo quy tắc canonical đã công bố.

## 35. Kiểm tra naming strategy và tên field

Một fixture ghi cần chứa các tên wire chính xác:

~~~json
{
  "first_name": "Mai",
  "postal_code": "550000"
}
~~~

Nếu mapper dùng SNAKE_CASE, test cần xác nhận cả hai property. Nếu một property có JsonProperty override, expected phải phản ánh override đó.

Test đọc nên có fixture với đúng tên bên ngoài. Không tạo fixture bằng cách serialize object trước vì serializer có thể đang áp dụng cùng naming strategy sai.

## 36. Kiểm tra constructor, record và immutable type

Với record:

~~~java
public record User(
    long id,
    String name,
    boolean active
) {
}
~~~

Fixture đọc xác nhận Jackson gọi creator với đúng property name và kiểu:

~~~json
{
  "id": 42,
  "name": "Mai",
  "active": true
}
~~~

Fixture ghi xác nhận record được serialize theo wire contract đã công bố. Đặc biệt kiểm tra constructor property thiếu, null và default logic nếu record có compact constructor.

Không chỉ kiểm tra record round-trip vì property name inference có thể khiến cả hai chiều cùng đồng thuận trên một tên ngoài ý muốn.

## 37. Kiểm tra mix-in và cấu hình mapper theo profile

Một class có thể được ánh xạ khác nhau trên mapper khác nhau:

- Mapper public API.
- Mapper đọc payload đối tác.
- Mapper ghi event.
- Mapper lưu snapshot nội bộ.

Mỗi profile nên có fixture riêng nếu wire contract khác nhau:

~~~text
user/
  public-api/
    read/
    write/
  partner/
    read/
    write/
  event/
    read/
    write/
~~~

Không dùng một expected fixture chung nếu mix-in, naming strategy, visibility hoặc custom module khác nhau. Test phải lấy đúng mapper factory/bean mà luồng production sử dụng.

## 38. Không thay đổi ObjectMapper dùng chung trong test

ObjectMapper thường được cấu hình xong rồi tái sử dụng. Test không nên mutate mapper dùng chung giữa các test:

~~~java
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
~~~

Nếu test khác dùng cùng instance, kết quả có thể phụ thuộc thứ tự chạy.

Hãy tạo mapper riêng cho mỗi profile:

~~~java
ObjectMapper strictMapper = createStrictMapper();
ObjectMapper tolerantMapper = createTolerantMapper();
~~~

Hoặc dùng ObjectReader/ObjectWriter với cấu hình per-operation khi feature phù hợp:

~~~java
ObjectReader reader = mapper.readerFor(User.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter writer = mapper.writer()
    .with(SerializationFeature.INDENT_OUTPUT);
~~~

ObjectReader và ObjectWriter là immutable configuration views; chúng giúp test một số tùy chọn mà không thay đổi cấu hình gốc.

## 39. Dùng mapper production configuration trong test

Một test tạo `new ObjectMapper()` có thể không phản ánh production nếu ứng dụng đăng ký:

- JavaTimeModule.
- ParameterNamesModule.
- Kotlin module.
- Custom serializers/deserializers.
- Mix-ins.
- Naming strategy.
- Visibility rules.
- Deserialization/serialization features.
- Module tự viết.

Nên có một factory/configuration duy nhất tạo mapper production và được gọi trong test. Nếu dùng Spring Boot, có thể inject ObjectMapper đã auto-configure trong test context hoặc dùng `@JsonTest` để kiểm tra Jackson slice theo cấu hình Spring.

Đừng copy một danh sách feature vào test rồi hy vọng nó luôn đồng bộ với production. Cấu hình mapper cần có một nguồn quản lý rõ ràng.

## 40. Ví dụ test đọc và ghi với JUnit 5

Test đọc:

~~~java
class UserReadTest {

    private final ObjectMapper mapper = TestMappers.userReader();

    @Test
    void readsV1CompleteFixture() throws Exception {
        String json = Fixtures.readUtf8(
            "jackson/user/read/v1-all-fields.json"
        );

        User user = mapper.readValue(json, User.class);

        assertEquals(42L, user.getId());
        assertEquals("Mai Nguyen", user.getUserName());
        assertEquals("mai@example.test", user.getEmail());
        assertTrue(user.isActive());
        assertEquals(List.of("ADMIN", "EDITOR"), user.getRoles());
    }

    @Test
    void readsV1MinimalFixtureWithDefaults() throws Exception {
        String json = Fixtures.readUtf8(
            "jackson/user/read/v1-minimal.json"
        );

        User user = mapper.readValue(json, User.class);

        assertEquals(1L, user.getId());
        assertEquals("vi-VN", user.getLocale());
    }
}
~~~

Test ghi:

~~~java
class UserWriteTest {

    private final ObjectMapper mapper = TestMappers.userWriter();

    @Test
    void writesV1CompleteFixture() throws Exception {
        User user = UserFixtures.completeUser();

        String actual = mapper.writeValueAsString(user);
        String expected = Fixtures.readUtf8(
            "jackson/user/write/v1-expected-all-fields.json"
        );

        JsonNode expectedNode = mapper.readTree(expected);
        JsonNode actualNode = mapper.readTree(actual);

        assertEquals(expectedNode, actualNode);
    }

    @Test
    void omitsSensitiveProperty() throws Exception {
        User user = UserFixtures.userWithInternalSecret();

        JsonNode actual = mapper.readTree(
            mapper.writeValueAsString(user)
        );

        assertFalse(actual.has("passwordHash"));
    }
}
~~~

Hai class test dùng hai fixture corpus riêng. Test đọc không phụ thuộc serializer; test ghi không phụ thuộc deserializer.

## 41. Ví dụ test đọc với TypeReference

Khi đọc collection hoặc generic type, fixture vẫn nên độc lập:

~~~json
[
  {"id": 1, "name": "Mai"},
  {"id": 2, "name": "An"}
]
~~~

Test:

~~~java
List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);

assertEquals(2, users.size());
assertEquals("Mai", users.get(0).getName());
~~~

Không dùng raw `List.class` nếu test cần xác nhận kiểu phần tử. Type erasure khiến Jackson không biết generic element type khi chỉ truyền List.class.

## 42. Ví dụ kiểm tra serialization bằng JsonNode

Một helper:

~~~java
static JsonNode toTree(
        ObjectMapper mapper,
        Object value) throws JsonProcessingException {
    return mapper.readTree(mapper.writeValueAsBytes(value));
}
~~~

Test:

~~~java
JsonNode actual = toTree(mapper, user);
JsonNode expected = mapper.readTree(
    Fixtures.readUtf8("jackson/user/write/v1-expected.json")
);

assertEquals(expected, actual);
~~~

Helper chỉ chuyển output thực tế thành tree để so sánh. Expected vẫn được đọc từ fixture độc lập.

## 43. Parameterized tests cho nhiều fixture

JUnit 5 có thể chạy cùng một test trên nhiều fixture:

~~~java
static Stream<Arguments> userReadCases() {
    return Stream.of(
        Arguments.of(
            "jackson/user/read/v1-minimal.json",
            1L,
            "Unknown"
        ),
        Arguments.of(
            "jackson/user/read/v1-all-fields.json",
            42L,
            "Mai Nguyen"
        )
    );
}

@ParameterizedTest
@MethodSource("userReadCases")
void readsUserFixtures(
        String fixture,
        long expectedId,
        String expectedName) throws Exception {

    User user = mapper.readValue(
        Fixtures.readUtf8(fixture),
        User.class
    );

    assertEquals(expectedId, user.getId());
    assertEquals(expectedName, user.getName());
}
~~~

Nếu mỗi fixture có các assertion khác nhau, test riêng có thể rõ ràng hơn. Parameterized test phù hợp khi các case có cùng cấu trúc kiểm tra.

## 44. Dùng Spring Boot @JsonTest khi cần kiểm tra slice Jackson

Trong ứng dụng Spring Boot, `@JsonTest` tạo test slice tập trung vào JSON serialization/deserialization và có thể cung cấp JacksonTester.

Ví dụ:

~~~java
@JsonTest
class UserJsonTest {

    @Autowired
    private JacksonTester<User> json;

    @Test
    void readsFixture() throws Exception {
        User user = json.parseObject(
            Fixtures.readUtf8("jackson/user/read/v1-all-fields.json")
        );

        assertThat(user.getId()).isEqualTo(42L);
    }

    @Test
    void writesExpectedJson() throws Exception {
        User user = UserFixtures.completeUser();

        assertThat(json.write(user))
            .isEqualToJson(
                Fixtures.readUtf8(
                    "jackson/user/write/v1-expected-all-fields.json"
                )
            );
    }
}
~~~

API cụ thể của JacksonTester và AssertJ JSON assertion phụ thuộc Spring Boot version và test dependencies. Mục tiêu vẫn là giữ input fixture và expected output độc lập.

Nếu test cần XML hoặc binary format khác, `@JsonTest` không tự thay thế test cho mọi mapper. Hãy cấu hình XmlMapper/SmileMapper/CBOR mapper riêng theo module.

## 45. Fixture cho XML ghi độc lập

Object Java:

~~~java
User user = new User(42L, "Mai");
~~~

Expected XML:

~~~xml
<user id="42">
    <name>Mai</name>
</user>
~~~

Test ghi:

1. Serialize object bằng XmlMapper.
2. Parse expected XML và actual XML.
3. So sánh root name, namespace, attribute và child element.
4. Kiểm tra thứ tự child element nếu XSD yêu cầu.
5. Không phụ thuộc whitespace hoặc prefix nếu không thuộc contract.

Test đọc dùng fixture XML độc lập do schema/đối tác cung cấp và xác nhận object Java. Không dùng XML vừa serialize ở test ghi làm input cho test đọc.

## 46. Fixture binary và nguồn tham chiếu

Binary fixture khó review bằng mắt. Vì vậy, cần lưu thêm thông tin giúp hiểu nó:

- File schema hoặc message definition nếu format cần.
- Text rendering tương đương nếu có thể.
- Version của format/module dùng để tạo fixture.
- Mô tả từng giá trị số/field.
- Nguồn fixture.
- Hash để phát hiện thay đổi byte ngoài ý muốn nếu cần.

Ví dụ:

~~~text
cbor/
  user-v1.cbor
  user-v1.expected.json
  README.md
~~~

`expected.json` giúp người review hiểu dữ liệu. Tuy nhiên, nó không thay thế binary fixture và không chứng minh byte sequence hợp lệ; test cần thực sự decode binary.

## 47. Không tạo binary golden file từ mapper đang kiểm thử

Nếu test ghi binary cần expected bytes, không nên tạo expected trong setup bằng chính SmileFactory hoặc CBORFactory đang được test.

Golden bytes nên đến từ:

- Một implementation độc lập theo specification.
- Một phiên bản đã phát hành và được xác nhận.
- Fixture do đối tác cung cấp.
- Một tool chuyên dụng đã được review.

Nếu không có byte-stability requirement, tốt hơn là test wire semantics bằng parser/consumer độc lập thay vì đóng đinh toàn bộ bytes. Điều này tránh test thất bại chỉ vì serializer đổi một encoding hợp lệ.

## 48. Fixture cho schema version cũ và mới

Khi schema tiến hóa, giữ fixture theo version:

~~~text
order/
  v1/
    read/
    write/
  v2/
    read/
    write/
~~~

Test có thể kiểm tra:

- Reader mới đọc được payload v1.
- Reader cũ xử lý payload v2 theo policy.
- Writer v2 phát đúng schema v2.
- Writer v1 tiếp tục giữ wire contract cũ nếu cần.

Không sửa fixture v1 để thêm field v2. Hãy tạo fixture mới và giữ payload cũ để bảo vệ backward compatibility.

## 49. Fixture không hợp lệ nên có mục đích rõ

Thay vì một folder `bad`, phân nhóm lỗi:

~~~text
invalid/
  syntax/
    missing-closing-brace.json
    invalid-escape.json
  mapping/
    object-for-integer.json
    unknown-enum.json
    unknown-subtype.json
  validation/
    negative-quantity.json
    missing-required-business-field.json
~~~

Các nhóm này giúp test đúng tầng:

- Syntax: parser không thể đọc JSON.
- Mapping: parser đọc được nhưng không tạo được target type.
- Validation: Jackson tạo object nhưng dữ liệu vi phạm quy tắc nghiệp vụ.

Không dùng exception Jackson để kiểm tra mọi lỗi nghiệp vụ. Validation nên có test riêng sau khi deserialize thành công.

## 50. Fixture cho default và constructor behavior

Nếu DTO có field initializer:

~~~java
public class User {
    private String locale = "vi-VN";
}
~~~

Fixture thiếu locale cần xác nhận default còn nguyên:

~~~json
{
  "id": 42
}
~~~

Fixture có null:

~~~json
{
  "id": 42,
  "locale": null
}
~~~

Hai test có thể cho kết quả khác nhau. Hãy ghi tên fixture rõ như `missing-locale.json` và `null-locale.json`.

Với constructor-based DTO, test thêm:

- Property bị thiếu.
- Property explicit null.
- Property sai kiểu.
- Creator property required.
- Default do constructor tự áp dụng.

## 51. Fixture cho custom date/time format

Nếu serializer ghi `LocalDate` theo `dd/MM/yyyy`, fixture expected nên có đúng chuỗi wire:

~~~json
{
  "date": "12/11/2026"
}
~~~

Test ghi:

~~~java
record DatePayload(LocalDate date) {}

DatePayload payload =
    new DatePayload(LocalDate.of(2026, 11, 12));

String actual = mapper.writeValueAsString(payload);
assertJsonEquals(
    mapper,
    Fixtures.readUtf8("jackson/date/write/expected.json"),
    actual
);
~~~

Test đọc dùng fixture riêng với cùng contract. Không lấy `actual` từ test ghi để feed sang test đọc.

Nếu format phụ thuộc locale, timezone hoặc zone database, cố định cấu hình và giá trị trong test. Không dùng system default.

## 52. Fixture cho binary number và decimal

Nếu định dạng nhị phân hỗ trợ số nguyên lớn hoặc decimal, cần fixture được tạo độc lập với giá trị biên:

- Integer lớn hơn 64-bit.
- Decimal precision cao.
- Decimal có scale khác nhau.
- Float/double đặc biệt.
- Unsigned integer vượt signed range.

Fixture đọc xác nhận parser trả đúng Java type/giá trị. Fixture ghi xác nhận writer phát đúng wire representation hoặc consumer độc lập đọc đúng.

Với BSON Decimal128, fixture phải phản ánh giới hạn precision của Decimal128. Với Avro decimal, fixture cần schema precision/scale. Với Protobuf, fixture cần `.proto` và quy tắc decimal message nếu có.

## 53. Tạo bộ dữ liệu biên có thể tái sử dụng

Có thể định nghĩa các factory test cho giá trị Java:

~~~java
final class NumericCases {
    static BigInteger hugeInteger() {
        return new BigInteger(
            "1234567890123456789012345678901234567890"
        );
    }

    static BigDecimal scaledAmount() {
        return new BigDecimal("123.4500");
    }

    static double negativeZero() {
        return -0.0d;
    }

    private NumericCases() {
    }
}
~~~

Factory này phục vụ test ghi. Với test đọc, fixture wire tương ứng vẫn phải là file được lưu độc lập. Không dùng factory để tự serialize ra fixture expected trong mỗi lần test.

## 54. Property-based test bổ sung cho fixture

Fixture cố định kiểm tra những ví dụ có ý nghĩa hợp đồng. Property-based testing bổ sung bằng cách sinh nhiều giá trị trong miền:

- Số nguyên trong phạm vi target.
- Chuỗi Unicode.
- Collection có độ dài ngẫu nhiên.
- Decimal với precision/scale trong giới hạn.
- Nested object với optional fields.

Một property test có thể kiểm tra round-trip hoặc invariant chung. Tuy nhiên, nó không thay thế fixture golden vì dữ liệu sinh tự động không chứng minh tên property, discriminator hay wire format cụ thể đúng contract.

Kết hợp:

- Fixture tests: bảo vệ các ví dụ wire đã công bố.
- Property tests: tìm lỗi ở nhiều tổ hợp dữ liệu.
- Round-trip tests: kiểm tra tính nhất quán nội bộ.
- Interoperability tests: xác nhận consumer độc lập.

## 55. Không dùng random value không cố định trong fixture test

Random test data có thể hữu ích nhưng phải có seed cố định nếu cần tái hiện:

~~~java
Random random = new Random(12345L);
~~~

Đối với test fixture và expected output, tốt nhất dùng dữ liệu xác định. Tránh:

- UUID.randomUUID() trong expected JSON.
- Instant.now().
- Random number không seed.
- Giá trị lấy từ database hoặc network.
- Locale/timezone hệ điều hành.

Test cần cho cùng kết quả trên máy developer và CI.

## 56. Giữ fixture nhỏ nhưng có mục tiêu

Một fixture có hàng trăm field có thể kiểm tra nhiều thứ cùng lúc nhưng khó tìm nguyên nhân lỗi. Hãy chia theo behavior:

- Minimal.
- Complete.
- Missing optional.
- Explicit null.
- Unknown field.
- Nested collection.
- Numeric boundary.
- Polymorphic subtype.

Một fixture complete vẫn hữu ích như contract sample tổng thể. Nhưng mỗi edge case quan trọng nên có fixture nhỏ và test tập trung.

Không cần tạo file riêng cho mọi tổ hợp Cartesian có thể xảy ra. Chọn các trường hợp đại diện theo rủi ro và hợp đồng.

## 57. Tránh fixture phụ thuộc thứ tự chạy

Fixture test phải độc lập:

- Không sửa file resource trong lúc chạy.
- Không ghi output vào cùng path expected.
- Không dùng static mutable ObjectMapper thay đổi giữa test.
- Không dùng một DTO static bị chia sẻ trạng thái.
- Không dùng thư mục tạm chung với tên cố định nếu test chạy song song.

Nếu test cần ghi file tạm, tạo temporary directory riêng cho từng test và dọn bằng JUnit @TempDir.

## 58. Fixture và dữ liệu nhạy cảm

Không đưa payload production nguyên bản vào repository nếu có dữ liệu cá nhân hoặc bí mật:

- Tên, email, số điện thoại thật.
- Token, mật khẩu, API key.
- Địa chỉ hoặc thông tin tài khoản.
- Dữ liệu thanh toán.
- ID nội bộ có thể truy ngược người dùng.

Hãy tạo synthetic data có hình dạng tương tự hoặc ẩn danh hóa có kiểm tra. Đừng chỉ thay tên nhưng để lại token, ID hoặc metadata nhạy cảm trong nested object.

Fixture được commit vào repository thường tồn tại lâu và có thể được sao chép sang nhiều môi trường. Xem nó như dữ liệu source code.

## 59. Cập nhật fixture khi contract thay đổi

Khi contract thay đổi:

1. Xác định thay đổi có backward/forward compatible không.
2. Tạo fixture version mới nếu wire contract mới.
3. Giữ fixture cũ nếu cần hỗ trợ payload lịch sử.
4. Cập nhật expected output theo tài liệu/schema được duyệt.
5. Thêm test đọc fixture cũ bằng reader mới.
6. Thêm test writer mới phát đúng output mới.
7. Nếu cần, thêm test consumer cũ xử lý payload mới.
8. Ghi rõ lý do fixture thay đổi trong commit/PR.

Không cập nhật snapshot hàng loạt chỉ để test xanh. Mỗi thay đổi expected phải có lý do contract.

## 60. Review thay đổi fixture như review code

Khi một fixture thay đổi, reviewer nên biết:

- Field nào được thêm/xóa/đổi tên.
- Kiểu wire có thay đổi không.
- Null/missing behavior có thay đổi không.
- Decimal/date format có thay đổi không.
- Có thay đổi thứ tự array/element không.
- Schema version có đổi không.
- Fixture mới có đến từ nguồn tham chiếu đáng tin không.

Với binary fixture, diff text có thể không hữu ích. Hãy kèm một bản mô tả hoặc decoded view có thể tái tạo, cùng hash nếu byte identity quan trọng.

## 61. Kiểm thử mapper profile riêng biệt

Nếu ứng dụng có mapper JSON public và mapper JSON nội bộ:

~~~java
ObjectMapper publicMapper = MapperConfiguration.publicApiMapper();
ObjectMapper internalMapper = MapperConfiguration.internalMapper();
~~~

Không dùng fixture public API để khẳng định internal mapper đúng nếu hai contract khác nhau.

Tổ chức test theo profile:

~~~text
serialization/
  public-api/
    read/
    write/
  internal-event/
    read/
    write/
  partner-xml/
    read/
    write/
~~~

Mỗi test lấy đúng mapper factory và fixture tương ứng. Điều này giúp phát hiện việc một module hoặc mix-in vô tình được đăng ký vào sai mapper.

## 62. Test read và write có thể dùng chung DTO nhưng không dùng chung expected data

Cùng một Java class có thể tham gia hai chiều:

~~~java
User userFromReadFixture =
    mapper.readValue(readFixture, User.class);

String outputFromWriteObject =
    mapper.writeValueAsString(writeFixtureObject);
~~~

Nhưng hai test có dữ liệu nguồn độc lập:

- Read fixture mô tả wire data nhận vào.
- Write object mô tả trạng thái Java muốn phát ra.
- Write expected fixture mô tả wire data phải phát ra.

Không yêu cầu hai input phải có cùng nội dung nếu mục tiêu của chúng khác nhau. Có thể dùng cùng một ví dụ nghiệp vụ, nhưng vẫn phải chuẩn bị nguồn expected độc lập.

## 63. Kiểm tra serializer không làm mất dữ liệu

Với DTO có field mở rộng:

~~~java
public class Event {
    private String type;
    private Map<String, JsonNode> extensions;
}
~~~

Fixture expected nên xác nhận extension fields được phát đúng vị trí và không bị lồng sai:

~~~json
{
  "type": "user-created",
  "source": "mobile",
  "trace": {
    "id": "trace-42"
  }
}
~~~

Nếu contract muốn extension fields ở root, test phải xác nhận flattening behavior. Nếu serializer tạo:

~~~json
{
  "type": "user-created",
  "extensions": {
    "source": "mobile"
  }
}
~~~

thì đó là một cấu trúc khác.

## 64. Kiểm tra serialization của null và default

Một object có:

~~~java
new User(42L, "Mai", null, List.of())
~~~

có thể được serialize thành nhiều hình dạng tùy cấu hình:

~~~json
{
  "id": 42,
  "name": "Mai",
  "email": null,
  "roles": []
}
~~~

hoặc:

~~~json
{
  "id": 42,
  "name": "Mai",
  "roles": []
}
~~~

Fixture expected phải phản ánh inclusion policy đã công bố. Đừng chỉ kiểm tra object sau khi deserialize vì reader có thể tự áp dụng default và che việc writer phát sai.

## 65. Kiểm tra custom naming và root wrapping

Với JSON root object, tên class không xuất hiện như một wrapper mặc định. Với XML hoặc một số binary/message schema, root/container có thể là một phần wire contract.

Fixture ghi nên xác nhận:

- Root type/record name nếu format dùng.
- Field name và field number nếu schema-based.
- Wrapper collection.
- Type discriminator.
- Namespace hoặc tag.

Đừng chỉ kiểm tra field value. Một payload có đúng value nhưng sai root/container vẫn có thể bị consumer từ chối.

## 66. Dùng schema làm nguồn tham chiếu cho fixture

Nếu contract được mô tả bằng OpenAPI, JSON Schema, XSD, Avro schema hoặc `.proto`, fixture nên bám theo schema version tương ứng.

Schema giúp kiểm tra:

- Field required/optional.
- Kiểu dữ liệu.
- Cardinality.
- Decimal precision/scale.
- Enum values.
- Namespace và sequence.
- Field number hoặc logical type.

Nhưng schema không thay thế fixture. Schema mô tả tập dữ liệu hợp lệ; fixture cung cấp các ví dụ cụ thể và giúp test mapping thực tế.

## 67. Tách test serialization khỏi validation nghiệp vụ

Test đọc có thể xác nhận Jackson tạo DTO đúng. Validation nghiệp vụ là bước sau:

~~~java
Request request = mapper.readValue(json, Request.class);
validator.validate(request);
~~~

Fixture JSON hợp lệ về cú pháp và mapping nhưng có thể chứa amount âm. Test Jackson nên xác nhận amount được bind đúng; test validation xác nhận quy tắc amount không âm.

Không làm cho fixture invalid mơ hồ bằng cách gộp malformed JSON, mapping mismatch và business invalid vào một nhóm.

## 68. Bảo đảm fixture không phụ thuộc locale và môi trường

Đặt cố định:

- Charset UTF-8 cho text fixture.
- Timezone/ZoneId.
- Locale nếu format phụ thuộc locale.
- Jackson version và module version.
- Schema version.
- Numeric rounding mode nếu có.

Không dựa vào Locale.getDefault() hoặc ZoneId.systemDefault() trong serializer test nếu contract cần một format cố định.

## 69. Một bộ fixture tối thiểu cho mỗi kiểu message

Với một message có cấu trúc trung bình, có thể bắt đầu bằng:

| Fixture | Chiều | Mục đích |
|---|---|---|
| `minimal` | Read | Field bắt buộc và default |
| `complete` | Read | Tất cả field quan trọng |
| `missing-optional` | Read | Field vắng mặt |
| `explicit-null` | Read | Null handling |
| `unknown-property` | Read | Strict/tolerant policy |
| `nested-collection` | Read | Object lồng nhau và List |
| `numeric-boundary` | Read | Overflow và precision |
| `expected-minimal` | Write | Output tối thiểu |
| `expected-complete` | Write | Wire contract đầy đủ |
| `expected-null-policy` | Write | Null inclusion |

Không phải message nào cũng cần tất cả fixture. Chọn theo đặc điểm kiểu dữ liệu và rủi ro của contract.

## 70. Ví dụ cấu trúc test hoàn chỉnh

~~~text
src/test/java/com/example/serialization/
  Fixtures.java
  TestMappers.java
  UserFixtures.java
  UserReadTest.java
  UserWriteTest.java
  UserRoundTripTest.java

src/test/resources/jackson/user/
  read/
    v1-minimal.json
    v1-all-fields.json
    v1-null-email.json
    v1-unknown-field.json
  write/
    v1-expected-minimal.json
    v1-expected-all-fields.json
    v1-expected-null-policy.json
~~~

Trách nhiệm:

- Fixtures: đọc resource.
- TestMappers: cung cấp mapper profile được cấu hình giống production.
- UserFixtures: tạo Java object cho test ghi.
- UserReadTest: fixture wire → object.
- UserWriteTest: object → expected wire fixture.
- UserRoundTripTest: kiểm tra thêm tính nhất quán nội bộ.

Không đặt toàn bộ logic tạo expected output trong UserFixtures. Factory chỉ tạo object Java.

## 71. Round-trip test nên được giữ ở vai trò bổ sung

Round-trip vẫn hữu ích cho:

- Kiểu dữ liệu phức tạp.
- Collection lồng nhau.
- Custom serializer/deserializer có yêu cầu đối xứng.
- Binary format.
- Đối tượng có extension fields.

Nhưng cần hiểu giới hạn:

- Nó không xác nhận tên wire property độc lập.
- Nó không xác nhận payload tương thích với consumer khác.
- Nó không phát hiện mọi sai số nếu cả hai chiều cùng chuyển đổi.
- Nó không thay thế fixture version cũ.

Giữ round-trip test, nhưng đừng xem một test round-trip xanh là bằng chứng duy nhất cho contract.

## 72. Các lỗi thường gặp khi thiết kế fixture

| Cách làm | Vấn đề | Cách tốt hơn |
|---|---|---|
| Dùng output serializer làm input test đọc | Hai chiều phụ thuộc cùng mapper | Lưu fixture đọc độc lập |
| Sinh expected bằng mapper đang test | Expected không độc lập | Viết theo contract hoặc implementation tham chiếu |
| Chỉ so sánh raw JSON string | Nhạy với whitespace và key order | So sánh JsonNode khi phù hợp |
| Chỉ test một JSON complete | Bỏ sót missing/null/edge cases | Tạo fixture theo mục tiêu |
| Dùng new ObjectMapper() trong test production | Cấu hình khác thực tế | Dùng mapper factory/config production |
| Dùng đường dẫn file tuyệt đối | Hỏng trên CI | Đọc classpath resource |
| Đọc binary fixture như text | Hỏng bytes | Dùng byte[] |
| Không lưu Avro schema/Protobuf definition | Không thể diễn giải payload | Version schema cùng fixture |
| Ghi đè snapshot tự động | Che giấu thay đổi contract | Review expected fixture có chủ đích |
| Dùng dữ liệu production thật | Rò rỉ dữ liệu | Synthetic hoặc anonymized fixture |
| Chỉ test round-trip | Có thể cùng sai hai chiều | Read, write và interoperability tests |

## 73. Quy trình tạo và duy trì fixture

Một quy trình thực tế:

1. Xác định message type và schema version.
2. Xác định các hành vi cần kiểm thử riêng cho read và write.
3. Lấy input fixture từ contract, đối tác hoặc payload tham chiếu đã ẩn danh.
4. Tạo expected output từ contract hoặc implementation độc lập.
5. Lưu fixture đúng định dạng, đúng encoding và đúng thư mục.
6. Viết test đọc từ fixture vào kiểu Java.
7. Viết test ghi từ object Java độc lập sang fixture expected.
8. Thêm fixture cho missing/null/unknown/boundary nếu hợp đồng có các trường hợp đó.
9. Kiểm tra bằng mapper profile giống production.
10. Với binary/schema-based format, lưu schema và kiểm tra wire type.
11. Review mọi thay đổi fixture như thay đổi contract.
12. Giữ fixture version cũ khi cần bảo vệ dữ liệu lịch sử.

Sơ đồ:

~~~text
Contract / schema / payload tham chiếu
                 |
                 v
        Fixture đọc độc lập
                 |
                 v
             Read tests

Java object được tạo độc lập
                 |
                 v
           Write tests
                 |
                 v
       Expected fixture chuẩn
                 |
                 v
      Review và version control
~~~

## 74. Nguyên tắc thực hành

- Thiết kế test đọc và test ghi thành hai hướng độc lập.
- Không dùng output của mapper đang test làm fixture đầu vào hoặc expected output.
- Dùng fixture đọc phản ánh payload thực tế theo contract.
- Dùng Java factory để tạo object cho test ghi.
- Lưu expected wire output riêng và review nguồn gốc của nó.
- Tổ chức fixture theo message type, hướng kiểm thử và schema version.
- Đặt tên file thể hiện mục đích và edge case.
- Đọc text fixture từ classpath với UTF-8.
- Đọc binary fixture bằng byte array.
- So sánh JSON theo cấu trúc khi byte/string identity không thuộc contract.
- So sánh XML theo namespace và node structure; kiểm tra child order nếu schema yêu cầu.
- Lưu Avro schema và Protobuf definition cùng fixture.
- Test missing, null, empty, unknown property và giá trị biên.
- Test enum, polymorphism, custom serializer và naming strategy bằng wire example độc lập.
- Dùng đúng mapper configuration của production.
- Không mutate mapper dùng chung giữa các test.
- Không ghi đè golden fixture tự động trong test.
- Không đưa dữ liệu nhạy cảm vào repository.
- Giữ fixture version cũ để kiểm tra schema evolution.
- Bổ sung round-trip và interoperability tests, nhưng không dùng chúng thay fixture độc lập.

Fixture đọc và ghi độc lập biến kiểm thử Jackson thành việc xác nhận hai hợp đồng có thể quan sát được. Fixture đọc cho biết ứng dụng hiểu payload bên ngoài ra sao; fixture ghi cho biết ứng dụng phát ra payload nào. Khi hai nguồn kỳ vọng được chuẩn bị độc lập, đặt tên rõ, version hóa và kiểm tra bằng đúng mapper production, test sẽ phát hiện được những lỗi mà một lần round-trip với cùng mapper có thể che giấu.
