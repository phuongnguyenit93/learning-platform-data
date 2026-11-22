# JSON, XML và ảnh hưởng của việc nâng cấp serializer

Trong ứng dụng Java, nâng JDK hoặc nâng thư viện serializer không chỉ là thay một dependency. Một thay đổi nhỏ trong cách Java object được chuyển thành JSON/XML có thể làm ứng dụng khác không đọc được thông điệp, làm sai chữ ký số, mất dữ liệu khi rollback, hoặc khiến hệ thống không giải mã được dữ liệu đã lưu từ nhiều năm trước.

Điều nguy hiểm là phần lớn thay đổi này **không gây lỗi biên dịch**. API `writeValueAsString(...)` hoặc `marshal(...)` vẫn chạy, HTTP trả trạng thái thành công, nhưng payload có thể đổi tên field, biểu diễn ngày giờ, thứ tự phần tử, giá trị `null`, định dạng số, namespace XML hay cách xử lý field không biết trước.

Bài học này tập trung vào tương thích dữ liệu và giao thức trong Java khi nâng serializer: cách phân biệt các lớp hợp đồng, những thay đổi thường gặp ở Jackson, Gson, JSON-B và JAXB/Jakarta XML Binding; thiết kế kiểm thử contract; bảo mật parser; cùng quy trình triển khai an toàn qua nhiều phiên bản ứng dụng.

## 1. Serializer là gì và vì sao nâng cấp có rủi ro?

**Serialization** là quá trình biến đối tượng hoặc cấu trúc dữ liệu thành biểu diễn để truyền, lưu trữ hoặc trao đổi. **Deserialization** làm chiều ngược lại, đọc biểu diễn đó và xây dựng giá trị ở phía nhận.

Ví dụ một đối tượng Java:

```java
public record Customer(
        long id,
        String displayName,
        boolean active) {
}
```

Có thể được biểu diễn bằng JSON:

```json
{
  "id": 42,
  "displayName": "Minh",
  "active": true
}
```

Hoặc XML:

```xml
<customer>
    <id>42</id>
    <displayName>Minh</displayName>
    <active>true</active>
</customer>
```

Trong ví dụ trên, JSON và XML không phải cùng một giao thức. Chúng có những quy tắc khác nhau về kiểu dữ liệu, thứ tự, namespace và validation. Nhưng cả hai đều cần một **wire contract** rõ ràng: định dạng nào được chấp nhận, field nào bắt buộc, giá trị nào có nghĩa gì, phiên bản nào có thể đọc phiên bản nào.

Một serializer thường bao gồm nhiều hành vi:

- Khám phá property từ field, getter, record component hoặc annotation.
- Chọn tên field/tag/attribute.
- Chọn field nào bị bỏ qua và field nào luôn xuất hiện.
- Chuyển kiểu số, ngày, enum, collection và đối tượng lồng nhau.
- Tạo hoặc đọc metadata kiểu cho polymorphism.
- Xử lý `null`, field thiếu, unknown field và giá trị mặc định.
- Kiểm soát charset, XML namespace, escaping và biểu diễn byte.
- Cấu hình bảo mật khi đọc input không đáng tin cậy.

Khi nâng một thư viện, bất kỳ điểm nào ở trên cũng có thể bị ảnh hưởng bởi phiên bản, module tích hợp hoặc cấu hình mới.

## 2. Bốn lớp tương thích phải kiểm tra riêng

Từ “tương thích” rất dễ bị dùng quá rộng. Trong migration, nên chia thành bốn lớp:

| Lớp tương thích | Câu hỏi | Ví dụ |
|---|---|---|
| **Cú pháp / format** | Payload mới có vẫn là JSON/XML hợp lệ? | JSON vẫn parse được, XML vẫn well-formed. |
| **Schema / cấu trúc** | Tên, kiểu, tính bắt buộc, thứ tự và namespace có đúng hợp đồng? | `customerId` bị đổi thành `id`, `<item>` đổi namespace. |
| **Ngữ nghĩa** | Dữ liệu đọc được có giữ nguyên ý nghĩa nghiệp vụ? | `null` khác “chưa cung cấp”; timezone đổi ngày thanh toán. |
| **Byte-level** | Các byte có giống nhau khi bên nhận yêu cầu tuyệt đối? | Chữ ký HMAC, ETag, hash, snapshot, canonical XML/JSON. |

Hai payload đều hợp lệ về cú pháp không có nghĩa chúng tương thích về cấu trúc hoặc ngữ nghĩa.

Ví dụ:

```json
{"amount": 10.00, "currency": "VND"}
```

và:

```json
{"amount": 10, "currency": "VND"}
```

có thể biểu thị cùng giá trị số trong một số hệ thống; nhưng nếu phía nhận kiểm tra format thập phân, xử lý số bằng `BigDecimal` với scale cụ thể, hoặc ký nguyên văn byte, hai biểu diễn này có thể tạo hành vi khác.

Ngược lại, khác biệt về khoảng trắng giữa:

```json
{"id":1}
```

và:

```json
{
  "id": 1
}
```

thường không nên gây lỗi với JSON parser chuẩn. Nếu một consumer phụ thuộc vào dấu cách hoặc xuống dòng, đó thường là vấn đề hợp đồng bị định nghĩa sai, trừ khi hai bên đã cố ý cam kết một dạng byte cụ thể.

## 3. Phân biệt backward, forward và full compatibility

Giả sử phiên bản V1 của hệ thống tạo payload cũ, còn V2 tạo payload mới.

**Backward compatibility:** consumer V2 đọc được dữ liệu mà producer V1 đã tạo.

**Forward compatibility:** consumer V1 đọc được dữ liệu producer V2 tạo, trong những trường hợp contract cho phép.

**Full compatibility:** cả hai chiều đều được hỗ trợ theo phạm vi đã xác định.

```text
                 Dữ liệu V1  -------->  Consumer V2
                       backward compatibility

                 Dữ liệu V2  -------->  Consumer V1
                       forward compatibility
```

Ví dụ V1 có:

```json
{"id": 42, "name": "Minh"}
```

V2 bổ sung:

```json
{"id": 42, "name": "Minh", "marketingOptIn": false}
```

Consumer V2 thường dễ đọc dữ liệu V1 nếu có chính sách cho field bị thiếu. Nhưng consumer V1 có đọc được dữ liệu V2 hay không còn phụ thuộc cấu hình unknown fields: một số deserializer bỏ qua field lạ, một số lại từ chối.

Trong hệ thống rolling deployment, producer V1 và V2 có thể tồn tại cùng lúc. Vì vậy, chính sách không chỉ là “nâng được JDK mới”, mà là **giao tiếp được với mọi phiên bản còn hoạt động trong cửa sổ triển khai**.

## 4. Những thay đổi serializer không dễ nhận thấy

| Thay đổi | Ví dụ trước/sau | Ảnh hưởng |
|---|---|---|
| Property naming | `displayName` → `display_name` | Consumer tìm sai field. |
| Inclusion policy | Có `"nickname": null` → bỏ field | Field “có nhưng null” trở thành “không có”. |
| Unknown property | Bỏ qua → ném exception | Consumer cũ không đọc được payload mới. |
| Enum format | `"PENDING"` → `"pending"` hoặc số | Sai mapping hoặc rejected value. |
| Timestamp | Epoch millis → ISO-8601 | Khác kiểu JSON number/string; có thể đổi timezone. |
| Numeric coercion | `"100"` được nhận như number → bị từ chối | Dữ liệu lịch sử không parse được. |
| Float precision | `1.0` → `1`; khoa học `1E+7` | Sai byte-signature hoặc downstream parser. |
| Polymorphic metadata | `"@class"` → `"type"` | Không xác định được subtype. |
| Object property order | Thứ tự thay đổi | Snapshot hoặc chữ ký trên raw bytes thất bại. |
| XML namespace | Không namespace → URI mới | XPath/XSD/JAXB mapping không còn khớp. |
| XML empty/null | `<x/>` → bỏ `<x>` hoặc `xsi:nil` | Ý nghĩa nullable/optional khác. |
| XML attribute/element | `id="42"` → `<id>42</id>` | Phá vỡ XPath và XML schema. |
| Security defaults | Parser chặn DTD, type metadata không tin cậy | Input cũ có thể bị từ chối có chủ đích. |

Điểm quan trọng: *một thay đổi hành vi không nhất thiết là bug thư viện*. Nó có thể là thay đổi được công bố hoặc hệ quả của việc sửa lỗ hổng. Cần đối chiếu release notes và hợp đồng dữ liệu trước khi quyết định giữ cấu hình cũ.

## 5. JSON: hợp đồng thực tế nằm ở đâu?

JSON có các kiểu cơ bản: object, array, string, number, boolean và `null`. Bản thân JSON không gắn trực tiếp với các kiểu Java như `BigDecimal`, `Instant`, `LocalDate` hay enum.

Vì vậy, chỉ nói “API trả JSON” chưa đủ. Cần quyết định:

1. Tên field có cố định theo case/naming strategy nào?
2. Field nào bắt buộc, được phép `null`, hoặc có thể vắng mặt?
3. Số có giới hạn phạm vi/độ chính xác như thế nào?
4. Date/time dùng timezone nào và định dạng chuỗi nào?
5. Enum truyền bằng tên, mã nghiệp vụ hay số?
6. Unknown fields và duplicate fields được xử lý ra sao?
7. Có cho phép coercion, ví dụ nhận `"42"` thay cho `42`?
8. Payload được ký theo byte gốc hay dạng canonical?
9. Có version field hoặc đường dẫn API version hay không?

Các quy tắc cần được cụ thể hóa bằng JSON Schema, OpenAPI contract, protocol documentation hoặc contract tests. Không nên chỉ dựa vào “mặc định hiện tại của ObjectMapper” làm đặc tả giao tiếp.

### 5.1. JSON object không bảo đảm ý nghĩa thứ tự field

JSON object về mặt mô hình dữ liệu là tập các cặp tên/giá trị; thứ tự field không nên bị xem như điều kiện mang nghĩa nghiệp vụ, trừ khi có quy ước riêng cho biểu diễn byte. Nếu cần giữ thứ tự hiển thị trong một số API, có thể cấu hình serializer, nhưng consumer chuẩn vẫn nên tìm field theo tên.

Đối với array, **thứ tự phần tử có ý nghĩa** và phải được giữ đúng. Việc đổi từ `List` sang `Set` rồi xuất array có thể làm thứ tự thay đổi ngoài ý muốn.

### 5.2. Duplicate keys

Một payload như:

```json
{"role": "viewer", "role": "admin"}
```

có hai key trùng tên. Nhiều parser có chính sách xử lý khác nhau (lấy lần đầu, lấy lần cuối, từ chối). Nếu payload đi qua gateway, service và audit logger dùng parser khác nhau, đây có thể là vấn đề bảo mật.

Nên xác định chính sách rõ ràng, ưu tiên **từ chối duplicate keys trong input không đáng tin cậy** nếu hợp đồng không cho phép. Không mặc định rằng parser mới xử lý trùng key giống parser cũ.

## 6. Jackson: kiểm soát hành vi thay vì dựa vào default

Jackson là thư viện JSON phổ biến trong hệ sinh thái Java, gồm `jackson-core`, `jackson-databind` và nhiều module mở rộng. Framework có thể cấu hình Jackson thay cho ứng dụng; ví dụ cấu hình ObjectMapper do Spring Boot cung cấp có thể khác ObjectMapper được khởi tạo thủ công.

Những lựa chọn cần phân biệt:

- Phiên bản Jackson và dependency bắc cầu.
- Cấu hình `ObjectMapper` và các feature flags.
- Annotations trên DTO (`@JsonProperty`, `@JsonIgnore`, `@JsonInclude`...).
- Module mở rộng cho Java time, optional types hoặc kiểu dữ liệu đặc biệt.
- Framework-level customization, mixins và serializer/deserializer riêng.

### 6.1. Khai báo DTO tường minh

Ví dụ một contract cho order:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;

@JsonInclude(JsonInclude.Include.ALWAYS)
public record OrderPayload(
        @JsonProperty("order_id") String orderId,
        @JsonProperty("total_amount") BigDecimal totalAmount,
        @JsonProperty("note") String note) {
}
```

Ví dụ sử dụng Java record yêu cầu JDK hỗ trợ record và phiên bản Jackson có hỗ trợ xử lý record. Nếu baseline JDK cũ hơn, có thể dùng POJO với constructor/getter được annotation tương ứng.

`@JsonProperty` giúp cố định wire name độc lập với tên member Java. `@JsonInclude(ALWAYS)` thể hiện ý định luôn ghi các property theo phạm vi mà serializer xử lý, kể cả `null`; nếu schema không cho phép nullable, phải validate riêng, không được coi annotation là schema validation.

### 6.2. Không để cấu hình unknown-field là chuyện ngẫu nhiên

Ví dụ consumer chấp nhận field mới nhưng vẫn cần các giá trị cũ hợp lệ:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class JsonReaders {
    public static ObjectMapper tolerantReader() {
        return new ObjectMapper()
                .configure(
                        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                        false);
    }
}
```

Cấu hình này hữu ích cho forward compatibility nếu API được thiết kế theo nguyên tắc thêm field mới không phá consumer cũ. Nhưng chấp nhận mọi field lạ cũng có thể che lỗi chính tả hoặc lỗi schema. Với API nhạy cảm hoặc dữ liệu nhập lệnh nghiệp vụ, có thể chọn strict reader và versioning rõ ràng.

**Không có một chính sách đúng cho mọi luồng.** Đừng cho rằng default của một phiên bản Jackson, framework hay project sẽ mãi giống nhau. Hãy ghi chính sách vào code/test.

### 6.3. Java Time và định dạng timestamp

Giả sử API cần timestamp theo ISO-8601:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Với DTO:

```java
import java.time.Instant;

public record EventPayload(
        String eventId,
        Instant occurredAt) {
}
```

Ví dụ dữ liệu:

```json
{
  "eventId": "evt-100",
  "occurredAt": "2025-06-01T12:30:00Z"
}
```

Không nên coi mọi kiểu thời gian là tương đương: `LocalDate` không có timezone, `LocalDateTime` không mang offset, còn `Instant` thể hiện một thời điểm trên trục UTC. Nếu converter dùng timezone mặc định khi chuyển dữ liệu, kết quả có thể thay đổi khi nâng JDK, JVM flags hoặc môi trường container.

### 6.4. Cấu hình ObjectMapper trước khi chia sẻ

`ObjectMapper` thường được tái sử dụng và an toàn cho các thao tác đồng thời khi mọi cấu hình đã hoàn tất trước khi đưa vào sử dụng. Tránh thay cấu hình chung trong lúc nhiều thread đang serialize/deserialize. Nếu hai endpoint cần contract khác nhau, tạo reader/writer được cấu hình riêng hoặc mapper riêng, thay vì bật/tắt feature trên một mapper dùng chung giữa các request.

Ví dụ:

```java
ObjectMapper mapper = buildConfiguredMapper();

var strictWriter = mapper.writerFor(OrderPayload.class);
var reader = mapper.readerFor(OrderPayload.class);
```

`buildConfiguredMapper()` là hàm do ứng dụng định nghĩa để cấu hình mapper khi khởi tạo. Không có yêu cầu phải dùng một singleton cho mọi loại dữ liệu nếu schema và bảo mật của các luồng khác nhau.

## 7. Null, missing và default value: khác nhau ở ngữ nghĩa

Ba trạng thái sau có thể khác nhau:

```json
{}
```

```json
{"nickname": null}
```

```json
{"nickname": ""}
```

Trong một API cập nhật một phần (PATCH), chúng có thể mang nghĩa:

- **Missing:** không thay đổi field.
- **Null:** xóa giá trị hiện tại.
- **Chuỗi rỗng:** đặt giá trị thành chuỗi rỗng.

Tuy nhiên, đây là lựa chọn của contract cụ thể, **không phải** quy tắc tự động của mọi JSON API. Một serializer nâng cấp làm thay đổi inclusion policy từ “ghi null” sang “bỏ field” có thể gây lỗi nghiệp vụ dù client vẫn parse payload thành công.

Một rủi ro khác là primitive Java có default:

```java
public class AccountFlags {
    public boolean active;
}
```

Khi field `active` bị thiếu, giá trị có thể thành `false` sau binding nếu không có validation. Điều đó không chứng minh producer đã gửi `false`. Nếu cần phân biệt “không có” và “false”, dùng `Boolean` hoặc một representation có trạng thái presence rõ ràng, rồi validate theo hợp đồng.

Đối với API công khai, cần quyết định presence theo từng field và tạo test riêng cho missing, `null`, empty string, empty list và default value.

## 8. Number và độ chính xác khi nâng JSON serializer

JSON chỉ có một kiểu number; Java có nhiều kiểu khác nhau như `int`, `long`, `double`, `BigInteger`, `BigDecimal`.

Những lỗi thường gặp:

1. Consumer JavaScript nhận số nguyên 64-bit lớn và làm mất độ chính xác khi chuyển sang JS Number.
2. Deserializer mới thay cách coercion `"42"` → `42`.
3. Serializer đổi biểu diễn `1000.00` thành `1000.0`, `1000` hoặc exponent.
4. Giá trị `NaN`/`Infinity` ở Java không phải JSON number chuẩn; serializer có thể báo lỗi, ghi chuỗi hoặc dùng behavior riêng.
5. Field tiền tệ đi qua `double`, tạo sai số khi tính toán.

Ví dụ contract rõ ràng:

```json
{
  "amount_minor_units": 125000,
  "currency": "VND"
}
```

Hoặc dùng decimal string:

```json
{
  "amount": "125000.00",
  "currency": "VND"
}
```

Cả hai đều có ưu/nhược điểm. Điều quan trọng là producer/consumer thống nhất kiểu wire và quy tắc chuyển đổi, thay vì phó mặc serializer quyết định.

Với chữ ký số, hai biểu diễn số tương đương về giá trị vẫn có thể tạo byte khác. Nếu cần ký canonical JSON, phải áp dụng một chuẩn canonicalization thống nhất (ví dụ JSON Canonicalization Scheme, RFC 8785, trong phạm vi dữ liệu chuẩn hỗ trợ), không chỉ dựa vào việc bật một flag sắp xếp property.

## 9. Enum, tên field và thay đổi naming strategy

Giả sử enum:

```java
public enum OrderStatus {
    PENDING,
    COMPLETED,
    CANCELLED
}
```

Nếu API ghi `"PENDING"`, tên enum đã trở thành một phần wire contract. Đổi constant Java thành `WAITING` sẽ làm thay đổi dữ liệu, dù chức năng nghiệp vụ có thể giống nhau.

Một lựa chọn bền vững hơn là mã wire tách khỏi tên enum:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING("pending"),
    COMPLETED("completed"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown status: " + code);
    }
}
```

Khi thêm enum mới, phải quyết định consumer cũ nên làm gì: từ chối, map vào trạng thái `UNKNOWN` hay nâng cấp trước khi producer gửi giá trị mới. Không nên tự động gộp mọi giá trị lạ vào `PENDING` nếu điều đó làm thay đổi nghiệp vụ.

Tương tự, thay cấu hình từ camelCase sang snake_case có thể là breaking change:

```json
{"customerId": 42}
```

so với:

```json
{"customer_id": 42}
```

Nếu cần đổi tên field, có thể giai đoạn đầu **đọc cả tên cũ và mới nhưng chỉ ghi một tên chuẩn**, rồi chuyển producer sau khi consumer đã được nâng.

## 10. Polymorphic JSON: tương thích và bảo mật

Một API chứa nhiều subtype có thể dùng type discriminator:

```json
{
  "kind": "card",
  "lastFour": "4242"
}
```

Trong Jackson, có thể khai báo type names tường minh:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(
                value = CardPayment.class,
                name = "card"),
        @JsonSubTypes.Type(
                value = BankTransfer.class,
                name = "bank")
})
public interface PaymentMethod {
}
```

Các lớp `CardPayment` và `BankTransfer` là những subtype do ứng dụng định nghĩa. Tên `"card"` và `"bank"` cần được coi là wire identifiers ổn định.

**Rủi ro bảo mật:** không bật cơ chế default typing cho phép untrusted JSON tự quyết định tên lớp Java tùy ý. Các lỗ hổng deserialization lịch sử đã cho thấy việc cho input chọn loại object có thể nguy hiểm, nhất là với classpath có những gadget nguy hiểm. Ưu tiên danh sách subtype được cho phép hoặc schema cụ thể.

Khi nâng Jackson, các chính sách polymorphic typing và validation có thể được siết chặt. Nếu payload cũ không còn đọc được, phải xác định liệu nó dựa vào cấu hình không an toàn hay một contract được hỗ trợ. Không vô hiệu hóa kiểm soát bảo mật chỉ để khôi phục hành vi cũ.

## 11. Gson và JSON-B: không giả định cùng mặc định với Jackson

Trong hệ Java có thể gặp Gson hoặc JSON-B (Jakarta JSON Binding). Các thư viện này có cách khám phá property, xử lý annotation, date/time và null riêng.

Ví dụ Gson:

```java
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

Gson gson = new GsonBuilder()
        .serializeNulls()
        .create();

String json = gson.toJson(
        new CustomerNote("C-1", null));
```

Với DTO minh họa:

```java
public record CustomerNote(String customerId, String note) {
}
```

`serializeNulls()` là lựa chọn có chủ đích; bỏ nó có thể làm payload khác. Hỗ trợ record và những kiểu Java khác phụ thuộc phiên bản thư viện thực tế.

Với JSON-B, có thể dùng annotation như `@JsonbProperty` hoặc cấu hình `JsonbConfig` để biểu diễn wire name và chính sách tương ứng. Không mang trực tiếp `@JsonProperty` của Jackson sang JSON-B rồi giả định nó được xử lý giống nhau.

Khi đổi serializer **khác họ** (Jackson → Gson hoặc JSON-B), phạm vi migration thường lớn hơn việc nâng minor/patch trong cùng họ. Hãy coi đây là một thay đổi serialization contract có kiểm thử riêng, không phải thao tác thay dependency đơn thuần.

## 12. XML có những quy tắc khác JSON

XML vừa mang cấu trúc dữ liệu, vừa có namespace, attribute, element order, text content, entity và cơ chế schema validation. Hai XML document đều well-formed nhưng vẫn có thể không tương thích với một XSD hoặc với XPath mà đối tác sử dụng.

Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<invoice xmlns="urn:example:invoice:v1" id="INV-1">
    <amount currency="VND">125000.00</amount>
    <paid>false</paid>
</invoice>
```

Các yếu tố có thể thuộc contract:

- Root element là `invoice`, không phải `Invoice`.
- Namespace URI là `urn:example:invoice:v1`.
- `id` là attribute, không phải child element.
- `amount` mang attribute `currency`.
- `paid` có nội dung lexical được XSD cho phép.
- Element order có thể bị ràng buộc bởi `xs:sequence`.

Nếu serializer mới thay `<amount currency="VND">` thành `<amount><currency>VND</currency>...`, dữ liệu có thể không còn hợp lệ dù vẫn là XML well-formed.

### 12.1. Namespace prefix khác namespace URI

Hai document:

```xml
<inv:invoice xmlns:inv="urn:example:invoice:v1"/>
```

và:

```xml
<x:invoice xmlns:x="urn:example:invoice:v1"/>
```

chỉ khác prefix nhưng cùng namespace URI và local name của element. Một XML-aware consumer đúng chuẩn thường nên phân biệt bằng expanded name (namespace URI + local name), không phụ thuộc prefix text.

Tuy nhiên, nếu hệ thống ký **raw bytes** hoặc sử dụng XPath không khai báo namespace đúng cách, việc đổi prefix vẫn có thể làm hệ thống thất bại. Vì vậy, cần tách kiểm thử ngữ nghĩa XML với kiểm thử byte-level.

### 12.2. Element order có thể là hợp đồng

Trong JSON object, thứ tự field thường không nên được ràng buộc. Trong XML, thứ tự child elements có thể được khai báo trong XSD bằng `xs:sequence`:

```xml
<xs:sequence>
    <xs:element name="id" type="xs:string"/>
    <xs:element name="amount" type="xs:decimal"/>
</xs:sequence>
```

Nếu JAXB marshalling đổi thứ tự element, message có thể bị XSD validator từ chối. Hãy định nghĩa `@XmlType(propOrder = {...})` hoặc schema binding phù hợp, không trông chờ vào thứ tự reflection của field.

## 13. JAXB và chuyển từ `javax.xml.bind` sang `jakarta.xml.bind`

JAXB từng là một phần các module Java EE đi kèm một số JDK cũ. Từ JDK 11, JEP 320 loại bỏ module JAXB khỏi JDK. Khi nâng từ JDK 8 lên JDK 11+, ứng dụng dùng:

```java
import javax.xml.bind.JAXBContext;
```

cần khai báo API và runtime JAXB tương thích bằng dependency riêng. Ở các thế hệ Jakarta XML Binding mới, namespace Java package chuyển sang `jakarta.xml.bind`.

**Không đồng nhất hai bước sau:**

1. Bỏ phụ thuộc vào JAXB *được JDK đóng gói*, chuyển sang JAXB dependency độc lập nhưng vẫn dùng API namespace `javax.xml.bind` phù hợp.
2. Nâng sang Jakarta XML Binding thế hệ dùng `jakarta.xml.bind` và cập nhật import, annotation và runtime.

Bước (2) có thể là thay đổi source/binary compatibility của Java code, ngoài những thay đổi liên quan trực tiếp tới XML wire format.

### 13.1. Ví dụ XML binding tường minh

Ví dụ sau minh họa API Jakarta XML Binding:

```java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlAttribute;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
        name = "invoice",
        namespace = "urn:example:invoice:v1")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"amount", "paid"})
public class InvoiceXml {
    @XmlAttribute(name = "id")
    public String id;

    @XmlElement(
            name = "amount",
            namespace = "urn:example:invoice:v1")
    public java.math.BigDecimal amount;

    @XmlElement(
            name = "paid",
            namespace = "urn:example:invoice:v1")
    public boolean paid;

    public InvoiceXml() {
    }
}
```

Ví dụ này cho thấy cách cố định root, namespace, attribute và element order. Để đáp ứng toàn bộ schema trước đó, có thể cần thêm package-level namespace configuration, attribute trên `amount`, validation hoặc adapter. Không nên coi DTO minh họa là tương đương hoàn toàn với mọi XML ví dụ trước đó.

### 13.2. Marshalling và unmarshalling

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;
import java.io.StringWriter;

public final class XmlCodec {
    private final JAXBContext context;

    public XmlCodec() throws Exception {
        this.context = JAXBContext.newInstance(InvoiceXml.class);
    }

    public String write(InvoiceXml invoice) throws Exception {
        Marshaller marshaller = context.createMarshaller();
        marshaller.setProperty(
                Marshaller.JAXB_FORMATTED_OUTPUT, Boolean.TRUE);
        StringWriter out = new StringWriter();
        marshaller.marshal(invoice, out);
        return out.toString();
    }

    public InvoiceXml read(String xml) throws Exception {
        Unmarshaller unmarshaller = context.createUnmarshaller();
        return (InvoiceXml) unmarshaller.unmarshal(
                new StringReader(xml));
    }
}
```

`JAXBContext` thường là đối tượng tương đối tốn chi phí khởi tạo và có thể được tái sử dụng theo hướng dẫn implementation; `Marshaller` và `Unmarshaller` không nên mặc định chia sẻ đồng thời giữa nhiều thread. Ví dụ tạo marshaller/unmarshaller mới cho mỗi thao tác để tránh tranh chấp trạng thái.

Nếu nhận XML không đáng tin cậy, cần kiểm soát parser/nguồn XML và external entities như phần bảo mật bên dưới; không nên coi việc dùng JAXB tự động ngăn XXE trong mọi trường hợp.

### 13.3. JPMS và reflection

Trên module path, JAXB có thể cần truy cập các member để binding. Một module định nghĩa DTO có thể cần khai báo `opens` cho runtime JAXB cụ thể:

```java
module com.example.invoice.xml {
    requires jakarta.xml.bind;

    opens com.example.invoice.xml.model
        to jakarta.xml.bind;
}
```

Đây là mẫu minh họa; tên module runtime và yêu cầu đọc/mở package tùy JAXB implementation và classpath/module-path thực tế. Nếu gặp `InaccessibleObjectException`, hãy xác định đúng package, module đang thực hiện reflection và cách đóng gói trước khi mở rộng quyền truy cập.

## 14. XML: `null`, element thiếu và `xsi:nil`

Ba XML fragment có thể mang ý nghĩa khác nhau:

```xml
<invoice/>
```

```xml
<invoice>
    <note/>
</invoice>
```

```xml
<invoice xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <note xsi:nil="true"/>
</invoice>
```

Trong XML Schema, khả năng element bị thiếu phụ thuộc `minOccurs`; khả năng dùng `xsi:nil="true"` phụ thuộc `nillable`. Element rỗng không mặc nhiên tương đương `null`.

Khi nâng JAXB hoặc thay XML serializer, cần kiểm tra:

- `@XmlElement(nillable = true)` và những binding tương ứng.
- Các giá trị mặc định của field khi unmarshal.
- Tính tương thích của generated classes từ XSD.
- `@XmlElementWrapper` cho collection.
- Cách phân biệt empty element, whitespace text và absence.
- Quy tắc namespace của element nil và root.

Nếu đối tác có XSD, hãy validate cả payload cũ và mới; chỉ parse được XML không đủ để xác nhận contract.

## 15. XML: escaping, CDATA và encoding

XML serializer có thể biểu diễn cùng nội dung ký tự theo nhiều cách:

```xml
<message>Tom &amp; Jerry</message>
```

hoặc dùng CDATA:

```xml
<message><![CDATA[Tom & Jerry]]></message>
```

Hai dạng có thể tương đương về text content sau khi parse, nhưng không giống raw bytes. Một serializer nâng cấp có thể thay cách escaping, xuống dòng, indentation hay chọn CDATA.

Để xử lý đúng:

- **So sánh ngữ nghĩa XML:** parse thành DOM/StAX hoặc model và so sánh những node/attribute cần thiết.
- **So sánh schema:** validate với XSD.
- **So sánh byte-level:** chỉ dùng khi giao thức yêu cầu nguyên văn hoặc có chữ ký số; khi đó dùng XML Canonicalization phù hợp, không tự nối chuỗi.
- **Encoding:** đọc và ghi theo encoding đã thỏa thuận; lưu ý XML declaration và thực tế byte stream phải thống nhất.

Nếu dữ liệu XML đi qua nhiều hệ thống, cần cẩn thận với line ending, BOM, whitespace trong mixed content, entity expansion và XML namespace prefix. “Pretty-print” không phải thao tác trung tính với mọi XML document, đặc biệt khi whitespace là dữ liệu có nghĩa.

## 16. Bảo mật: XXE và XML parser hardening

XML có DTD, entities và external references. Với input không đáng tin cậy, parser cấu hình không an toàn có thể dẫn đến **XML External Entity (XXE)**, truy cập file, SSRF hoặc resource exhaustion.

Một ví dụ JAXP DOM parser có chính sách thận trọng:

```java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import java.io.StringReader;

public final class SafeXmlReader {
    public static Document read(String xml) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);

        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        return factory.newDocumentBuilder().parse(
                new InputSource(new StringReader(xml)));
    }
}
```

Ví dụ dùng các tính năng thông dụng của JAXP; một parser provider cụ thể có thể không hỗ trợ mọi feature/attribute. Trong ứng dụng thực, nếu không cấu hình được chính sách cần thiết thì nên **fail closed** thay vì âm thầm bỏ qua. Cần kiểm tra cả schema validation, XSLT, XPath, StAX hoặc JAXB pipeline vì các tầng khác cũng có khả năng truy cập tài nguyên ngoài.

Không nên bật DTD/external entities trở lại chỉ vì vài XML legacy không đọc được sau khi nâng thư viện. Trước tiên kiểm tra hợp đồng có thật sự cần DTD không và tìm phương án thay thế an toàn. Nếu bắt buộc hỗ trợ, giới hạn resolver hoặc nguồn tài nguyên rõ ràng và được đánh giá bảo mật.

## 17. JSON deserialization và bảo mật

JSON parser không có XXE theo cùng cách như XML, nhưng vẫn có những rủi ro khác:

| Rủi ro | Ví dụ | Hướng xử lý |
|---|---|---|
| Polymorphic type injection | Input chỉ định Java class tùy ý. | Chỉ cho phép subtype được liệt kê hoặc validate type ID. |
| Excessive nesting | JSON hàng nghìn lớp array/object lồng nhau. | Giới hạn depth, payload size và tài nguyên parser. |
| Huge strings/arrays/numbers | Input rất lớn gây memory/CPU exhaustion. | Giới hạn kích thước request và parsing constraints. |
| Duplicate keys | `"role"` xuất hiện hai lần. | Quy định chính sách từ chối hoặc xử lý rõ ràng. |
| Mass assignment | Deserialize trực tiếp request vào domain entity có field nhạy cảm. | Dùng input DTO riêng và allowlist field có thể cập nhật. |
| Lenient coercion | `"true"`, `1` hoặc chuỗi rỗng bị ép sang kiểu không mong đợi. | Chọn strictness theo contract; validate dữ liệu. |

Một serializer update có thể thay mặc định bảo mật để giảm các rủi ro này. Khi dữ liệu cũ không còn được đọc, cần xác định liệu dữ liệu vi phạm contract hay security policy mới. Không tháo bỏ guard một cách rộng rãi mà không chứng minh nhu cầu và đánh giá rủi ro.

## 18. Ảnh hưởng của JDK, reflection và module system

Nâng serializer thường xảy ra đồng thời với nâng JDK. Cần phân biệt vấn đề thuộc thư viện và vấn đề thuộc nền tảng:

- **JDK 11:** JAXB không còn đi kèm JDK theo JEP 320; cần dependency riêng.
- **JDK 16/17 và JPMS:** strong encapsulation ảnh hưởng thư viện reflection truy cập field không được mở. Cần cập nhật thư viện hoặc module `opens` phù hợp.
- **Java records:** serializer cũ có thể chưa hỗ trợ record components/constructors; cần thư viện tương thích hoặc DTO khác.
- **Ngày giờ và locale:** JDK và thư viện có thể khác trong default timezone/formatter. Cần format tường minh.
- **Charset mặc định:** từ JDK 18, JEP 400 chuẩn hóa UTF-8 cho phần lớn API phụ thuộc default charset; tránh dựa vào implicit encoding khi đọc/ghi payload.
- **Class loader/module path:** provider của XML binding, Jackson modules hoặc SPI có thể không được phát hiện như trên classpath cũ.

Ví dụ lỗi:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field ... accessible:
  module ... does not "opens ..."
```

Không kết luận serializer “không hỗ trợ JDK mới” chỉ từ stack trace này. Có thể DTO đang nằm trong named module không mở package cần thiết hoặc một thư viện quá cũ cố deep reflection vào JDK internals. Cách sửa bền vững thường là dùng phiên bản serializer được hỗ trợ, đặt annotation/accessor thích hợp và khai báo module access chính xác.

## 19. Thư viện và dependency graph: nâng một artifact chưa chắc đủ

Một ứng dụng có thể dùng:

- Jackson qua framework web.
- Gson trong client HTTP phụ.
- JAXB trong SOAP integration.
- JSON-B trong một module Jakarta EE.
- Một serializer riêng trong cache, message broker hoặc persistence.

Nếu chỉ nâng `jackson-databind` mà giữ `jackson-core` hoặc module Java Time ở phiên bản khác, dependency graph có thể trở nên không nhất quán. Một framework có thể quản lý version qua BOM; dependency explicit của ứng dụng có thể ghi đè BOM.

Trước migration, cần thống kê artifact **đã resolve thực tế**:

```bash
mvn dependency:tree
```

Hoặc Gradle:

```bash
./gradlew dependencies
```

Với một module phụ thuộc cụ thể, có thể xem lý do chọn phiên bản trong Gradle bằng `dependencyInsight`. Không nên suy luận từ `pom.xml` hoặc `build.gradle` rằng runtime chỉ có đúng những artifact được liệt kê trực tiếp.

Khi thay một major version serializer, đọc migration notes của phiên bản nguồn và đích, các API bị loại, thay đổi security defaults, yêu cầu JDK baseline và module IDs. Đặc biệt cần đảm bảo các plugin serializers/deserializers và framework integrations tương thích với core library.

## 20. Dữ liệu đã lưu lâu dài nguy hiểm hơn HTTP response ngắn hạn

Một HTTP request có thể được thử ngay ở staging. Nhưng JSON/XML lưu trong database, object storage, file archive, cache hoặc message queue có thể tồn tại lâu sau khi serializer nguồn đã bị nâng.

Các tình huống:

**Đọc cũ bằng mới:** bản V2 phải đọc được toàn bộ dữ liệu V1 còn trên disk.

**Đọc mới bằng cũ khi rollback:** sau khi V2 ghi dữ liệu, bản V1 có còn hiểu không? Nếu không, rollback code có thể làm hệ thống mất khả năng khởi động hoặc đọc dữ liệu.

**Consumer xử lý trễ:** hàng đợi chứa message từ producer cũ; consumer mới không thể giả định mọi message đã ở schema mới.

**Cache:** serializer thay đổi có thể khiến cache entry cũ không đọc được. Có thể cần cache key versioning, TTL hoặc kế hoạch invalidation.

**Backup/restore:** dữ liệu từ nhiều năm trước có thể chứa field, enum hoặc format đã biến mất khỏi code hiện tại.

Vì vậy, trước khi nâng, cần kiểm kê nơi **payload được lưu lại**, thời gian tồn tại tối đa và giới hạn rollback. Không chỉ test dữ liệu vừa được serializer mới ghi ra.

## 21. Chiến lược schema evolution: expand → migrate → contract

Khi cần đổi payload, một cách triển khai ít rủi ro là ba giai đoạn.

### Giai đoạn 1 — Expand

Consumer mới chấp nhận cả schema cũ và mới; producer vẫn phát schema cũ. Ví dụ consumer đọc cả `customerName` và `displayName` nhưng trả về một internal field chuẩn.

Với Jackson, có thể dùng annotation đọc alias khi phù hợp:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record CustomerMessage(
        String id,
        @JsonProperty("displayName")
        @JsonAlias("customerName")
        String displayName) {
}
```

Ví dụ cho phép đọc hai tên, còn serializer thường ghi tên chuẩn `displayName`. Cần test theo phiên bản Jackson hỗ trợ record và annotation.

### Giai đoạn 2 — Migrate

Producer chuyển dần sang schema mới. Theo dõi consumer còn dùng schema cũ; chuyển đổi dữ liệu lưu trữ hoặc thiết lập dual-read/dual-write có kiểm soát khi cần.

### Giai đoạn 3 — Contract

Sau khi không còn consumer/điểm lưu dữ liệu đòi schema cũ, loại bỏ alias hoặc field legacy theo chính sách versioning. Việc xóa cần có deadline, owner và dữ liệu đo chứng minh rằng đường cũ đã ngừng sử dụng.

Không nên vừa đổi tên field ở producer vừa đồng thời xóa khả năng đọc field cũ trong cùng một lần deploy cuốn chiếu; cửa sổ hỗn hợp có thể bị hỏng.

## 22. Golden fixtures: khóa hợp đồng ở mức dữ liệu thực

Một bộ golden fixtures là các payload đại diện với kết quả kỳ vọng. Nên có dữ liệu do **serializer cũ thực sự phát ra**, không chỉ payload tự viết bằng tay.

Cấu trúc gợi ý:

```text
fixtures/
├── json/
│   ├── order-v1-normal.json
│   ├── order-v1-null.json
│   ├── order-v1-unknown-field.json
│   ├── order-v1-large-number.json
│   └── order-v2-normal.json
├── xml/
│   ├── invoice-v1.xml
│   ├── invoice-v1-nil.xml
│   ├── invoice-v1-namespaced.xml
│   └── invoice-v2.xml
└── expected/
    ├── order-semantic.json
    └── invoice-semantic.json
```

Với mỗi fixture, lưu:

| Trường | Mục đích |
|---|---|
| Producer version | Biết dữ liệu được tạo bởi serializer/configuration nào. |
| Schema version | Biết hợp đồng dữ liệu mà fixture tuân theo. |
| Encoding | Tránh đoán từ environment. |
| Representative edge case | Null, số lớn, timezone, namespace, collection... |
| Expected semantics | Giá trị nghiệp vụ sau khi parse. |
| Expected rejection | Trường hợp nào phải bị từ chối, kèm loại lỗi phù hợp. |

Nên có **cả fixture hợp lệ và fixture cố ý không hợp lệ**, đặc biệt cho duplicate keys, unknown enums, XML external entities, payload quá sâu, trường bắt buộc bị thiếu. Những trường hợp này giúp kiểm tra rằng nâng thư viện không vô tình nới lỏng bảo mật hoặc làm sai chính sách validation.

## 23. Test JSON theo cấu trúc thay vì so chuỗi nguyên văn

Ví dụ JUnit 5 với Jackson:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class JsonWireContractTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void equivalentObjectsIgnoreWhitespaceAndFieldOrder()
            throws Exception {
        String left = "{\"id\":42,\"active\":true}";
        String right = """
                {
                  "active": true,
                  "id": 42
                }
                """;

        JsonNode expected = mapper.readTree(left);
        JsonNode actual = mapper.readTree(right);

        assertEquals(expected, actual);
    }
}
```

Ví dụ dùng text block Java 15+. Trên baseline JDK cũ hơn, thay text block bằng string thông thường. Test này thích hợp khi contract quan tâm **cấu trúc JSON**, không quan tâm raw bytes.

Nếu ứng dụng ký payload hoặc bên nhận yêu cầu byte exact, cần test byte-level riêng sau khi thống nhất canonicalization. So sánh `JsonNode` không đủ để khẳng định chữ ký trên chuỗi gốc vẫn hợp lệ.

### 23.1. Test đọc dữ liệu V1 bằng V2

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CustomerBackwardCompatibilityTest {
    record CustomerV2(
            String id,
            String displayName,
            boolean marketingOptIn) {
    }

    @Test
    void canReadOldPayload() throws Exception {
        String v1 = """
                {"id":"C-1","displayName":"Minh"}
                """;

        CustomerV2 actual =
                new ObjectMapper().readValue(v1, CustomerV2.class);

        assertEquals("C-1", actual.id());
        assertEquals(false, actual.marketingOptIn());
    }
}
```

Test thể hiện một **giả định của contract**: field boolean thiếu được xem như `false`. Nếu nghiệp vụ yêu cầu phân biệt “không cung cấp” với “false”, DTO cần kiểu `Boolean` hoặc validation tường minh, và expected result phải khác.

### 23.2. Test byte-level khi bắt buộc

Đối với hợp đồng ký raw payload, lưu byte fixture hoặc kiểm tra hash. Tránh dùng snapshot string để khóa chặt incidental whitespace trừ khi chính xác đó là hợp đồng được ký. Nếu dùng canonical JSON/XML, hãy test cả canonicalizer và serializer độc lập.

## 24. Test XML bằng schema và namespace

Với XML, một bài kiểm thử nên có ít nhất hai lớp:

1. **Schema validation:** dữ liệu có tuân XSD đối tác không?
2. **Semantic assertions:** sau khi parse, các element/attribute có đúng giá trị, namespace và ý nghĩa không?

Ví dụ khởi tạo XSD validator bằng API JAXP:

```java
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import java.nio.file.Path;

public final class XmlSchemaValidation {
    public static void validate(Path xsd, Path xml)
            throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Schema schema = factory.newSchema(xsd.toFile());
        Validator validator = schema.newValidator();
        validator.setProperty(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.validate(new StreamSource(xml.toFile()));
    }
}
```

Ví dụ giới hạn truy cập external DTD/schema. Nếu XSD có `xs:include` hoặc `xs:import` ngoài tập file đã kiểm soát, cần thiết kế resource resolver/nguồn hợp lệ rõ ràng thay vì mở quyền truy cập mạng tùy ý. Một parser provider có thể không hỗ trợ mọi property; hãy fail closed khi chính sách an toàn không được áp dụng.

Khi test payload XML, không chỉ so `toString()`. Nếu serializer đổi prefix namespace hoặc indentation nhưng giữ ngữ nghĩa và XSD validity, đó có thể là khác biệt được phép. Ngược lại, thứ tự child element trong `xs:sequence` hoặc `xsi:nil` có thể làm schema invalid dù text gần giống.

## 25. Tương thích giữa các thành phần triển khai khác phiên bản

Một thay đổi serializer có thể chỉ làm lỗi khi producer và consumer chạy khác phiên bản:

```text
     Producer V1  -------->  Queue  --------> Consumer V2
     Producer V2  -------->  Queue  --------> Consumer V1

     Database chứa V1 và V2 records
                    |
               V2 application
                    |
           Rollback trở lại V1?
```

Vì vậy, tạo ma trận:

| Producer / Stored data | Consumer V1 | Consumer V2 |
|---|---|---|
| V1 payload | Baseline | **Backward compatibility** cần test. |
| V2 payload | **Forward/rollback compatibility** nếu yêu cầu. | Normal operation. |

Nếu một ô không được hỗ trợ, phải được ghi rõ trong kế hoạch triển khai, và deployment order phải bảo đảm không có đường giao tiếp yêu cầu ô đó. Ví dụ, nếu consumer V1 không đọc được V2 payload, cần nâng toàn bộ consumer trước khi bật producer V2.

### 25.1. Feature flag và schema version

Có thể bổ sung version tường minh:

```json
{
  "schemaVersion": 2,
  "orderId": "ORD-100",
  "amount": "125000.00"
}
```

Version field giúp phân luồng decoder khi thực sự có nhiều schema. Nhưng không phải mọi thay đổi nhỏ đều cần tăng major version; nếu mở rộng tương thích được bằng additive fields và reader đã cho phép, một contract có thể hỗ trợ nhiều phiên bản mà không cần đường dẫn hoàn toàn mới.

Version field cũng không tự bảo đảm compatibility: vẫn cần schema contract, converter và test cho các phiên bản dữ liệu tồn tại.

## 26. Quy trình nâng cấp serializer trong ứng dụng Java

### Bước 1 — Kiểm kê codec và dữ liệu

Liệt kê mọi endpoint, queue topic, file, cache và database column dùng JSON/XML. Xác định serializer nào xử lý từng luồng, cấu hình annotation/custom module và phiên bản dependency thực tế.

### Bước 2 — Xác định các hợp đồng phải giữ

Với từng payload, mô tả field name, types, null/presence, enum, decimal, timestamp, namespace, XML schema, encoding và quy tắc chữ ký. Phân biệt contract công khai với chi tiết formatting không được cam kết.

### Bước 3 — Ghi baseline từ phiên bản cũ

Dùng dữ liệu đại diện, tạo golden fixtures từ serializer đang chạy. Lưu semantic expectations và raw bytes khi có giao thức yêu cầu byte exact.

### Bước 4 — Cô lập việc thay đổi dependency

Nâng serializer trong một nhánh hoặc môi trường riêng, hạn chế nâng đồng thời framework, JDK và schema nếu có thể. Nếu bắt buộc nâng nhiều thứ cùng lúc, ghi rõ thay đổi theo từng lớp và kiểm tra dependency graph.

### Bước 5 — Chạy bộ kiểm thử hai chiều

Đọc V1 bằng V2, ghi V2 rồi đọc bằng V1 nếu rollback/rolling deployment yêu cầu; kiểm tra JSON structure, XML XSD, semantic equivalence và dữ liệu lịch sử.

### Bước 6 — Thử dữ liệu không tin cậy

Kiểm tra duplicate keys, polymorphic type IDs, payload quá sâu, XML DTD, XXE, số cực lớn, string quá dài và lỗi schema. Không “sửa” test bảo mật bằng cách bật parser lenient vô điều kiện.

### Bước 7 — Triển khai theo thứ tự tương thích

Thường nên nâng consumer trước, chuyển producer sau. Với dữ liệu lưu trữ, áp dụng expand/migrate/contract và chọn thời điểm xóa hỗ trợ schema cũ dựa trên TTL/retention.

### Bước 8 — Quan sát production

Theo dõi deserialize failures, validation errors, unknown fields, enum values, dead-letter messages, số bản ghi không đọc được và kích thước payload. Không log nguyên văn thông tin nhạy cảm trong message.

### Bước 9 — Rollback có kiểm soát

Trước khi mở producer V2, xác nhận liệu V1 có đọc được dữ liệu V2 vừa ghi hay không. Nếu không, rollback code đơn thuần là không đủ; cần dual-read, converter hoặc kế hoạch dữ liệu tương ứng.

### Bước 10 — Gỡ cấu hình tạm

Sau khi không còn dữ liệu/consumer cũ, loại bỏ alias, parser flags tương thích tạm và custom deserializer không cần thiết. Giữ contract tests để phát hiện thay đổi không mong muốn ở lần nâng thư viện tiếp theo.

## 27. Một mẫu hồ sơ thay đổi serializer

```yaml
changeId: SER-MIG-014
component: "Order API JSON serializer"
oldRuntime: "JDK nguồn + serializer/framework version"
newRuntime: "JDK đích + serializer/framework version"
wireContract: "order-message-v2"
format: "application/json"
encoding: "UTF-8"
criticalFields:
  - orderId
  - amount
  - occurredAt
compatibility:
  readV1WithV2: required
  readV2WithV1: required-during-rollout
goldenFixtures:
  - order-v1-normal.json
  - order-v1-null.json
  - order-v1-large-number.json
expectedChanges:
  - "Bổ sung optional field sourceSystem"
securityChecks:
  - "Reject unsafe polymorphic type IDs"
  - "Bound payload size"
deployment:
  consumerFirst: true
  producerFlag: "orderSchemaV2"
  rollbackDataPlan: "Dual reader during transition"
owner: "Order service team"
```

Mẫu trên là cấu trúc minh họa, không phải metadata có sẵn trong Jackson/JAXB. Điền đúng thông tin thực tế và liên kết tới test/contract tương ứng. Mỗi change request nên nêu rõ **thay đổi được phép** và **thay đổi bị cấm**, tránh câu mơ hồ “serializer upgraded successfully”.

## 28. Các nhầm lẫn thường gặp

**“JSON parse được tức là tương thích.”** Có thể sai field name, kiểu dữ liệu, precision hoặc ngữ nghĩa.

**“Bỏ qua unknown fields luôn tốt.”** Chính sách tolerant phù hợp với additive schema evolution nhưng có thể che lỗi input hoặc làm suy giảm validation.

**“XML đổi prefix là breaking change.”** Có thể chỉ khác biểu diễn text; phải xem namespace URI, XPath và chữ ký byte.

**“Cứ giữ output giống hệt byte cũ là an toàn nhất.”** Nếu không có yêu cầu byte-level, khóa chặt spacing và property order có thể ngăn một nâng cấp hoàn toàn hợp lệ.

**“Nâng JDK 11 tự làm JAXB biến mất khỏi dữ liệu.”** JEP 320 loại JAXB khỏi JDK packaging; XML có thể vẫn đọc được nếu thêm API/runtime dependency phù hợp và kiểm tra contract.

**“Đã dùng UTF-8 ở HTTP, chắc file lưu trữ cũng UTF-8.”** File/archive có thể được tạo bởi hệ thống cũ dùng charset khác; phải dựa vào metadata và byte thực tế.

**“Rollback application sẽ tự rollback dữ liệu.”** Producer mới có thể đã ghi format mà code cũ không đọc được; cần kế hoạch rollback dữ liệu riêng.

**“Nới quyền reflection/parser sẽ sửa được.”** Có thể vượt qua lỗi đầu tiên nhưng đồng thời mở lỗ hổng hoặc phụ thuộc API không được hỗ trợ.

**“Dùng @JsonProperty là đủ cho API compatibility.”** Còn phải kiểm tra null, date/time, numeric coercion, enum, unknown-field policy và các consumer khác.

## 29. Checklist trước khi phát hành nâng cấp

- [ ] Đã xác định đúng serializer, phiên bản, dependency bắc cầu và framework configuration.
- [ ] Đã kiểm kê tất cả payload JSON/XML, bao gồm dữ liệu lưu lâu dài và queue.
- [ ] Đã công bố field names, types, null/presence, enum và date/time format.
- [ ] Đã kiểm tra Decimal/large integer không mất precision.
- [ ] Đã kiểm tra JSON unknown fields, duplicate keys, coercion và polymorphism.
- [ ] Đã kiểm tra XML namespace URI, attribute/element mapping và element order.
- [ ] Đã xác nhận XML XSD validation và chính sách external entities/DTD.
- [ ] Đã chỉ định encoding tường minh cho các luồng cần ổn định.
- [ ] Đã kiểm tra chuyển `javax.xml.bind`/`jakarta.xml.bind` nếu có.
- [ ] Đã xử lý quyền reflection/`opens` trong JPMS khi cần.
- [ ] Đã có golden fixtures do serializer cũ thực sự tạo.
- [ ] Đã test đọc dữ liệu cũ bằng runtime mới.
- [ ] Đã test chiều ngược lại nếu rolling deploy/rollback yêu cầu.
- [ ] Đã phân biệt semantic comparison với byte-level comparison.
- [ ] Đã có cơ chế phát hiện message lỗi, dead-letter và lỗi parse trong production.
- [ ] Đã lên thứ tự triển khai consumer/producer và kế hoạch rollback dữ liệu.
- [ ] Đã ghi rõ những cấu hình compatibility tạm cần loại bỏ sau migration.

## Tài liệu tham khảo

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): định dạng và quy tắc chung của JSON.
- [RFC 8785 — JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785): canonical JSON khi cần xác định biểu diễn byte.
- [W3C XML 1.0 Specification](https://www.w3.org/TR/xml/): cấu trúc XML, entity và well-formedness.
- [W3C XML Namespaces](https://www.w3.org/TR/xml-names/): cách dùng namespace URI và prefix.
- [W3C XML Schema](https://www.w3.org/XML/Schema): định nghĩa cấu trúc và validation.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): ảnh hưởng của JDK 11 với JAXB và các module liên quan.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ JDK 18.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): kiểm soát truy cập reflection khi nâng JDK.
- [Jackson Documentation](https://github.com/FasterXML/jackson-docs): annotation, data binding và release compatibility.
- [Jackson Databind Project](https://github.com/FasterXML/jackson-databind): phiên bản thư viện và migration notes.
- [Gson Project](https://github.com/google/gson): cấu hình Gson và thay đổi theo release.
- [Jakarta XML Binding Specification](https://jakarta.ee/specifications/xml-binding/): chuẩn XML binding và namespace Jakarta.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): hướng dẫn cấu hình parser tránh XXE.

## Kết luận

Nâng serializer có thể làm thay đổi giao thức JSON/XML ngay cả khi Java code vẫn biên dịch và payload vẫn parse được. Cần đánh giá tương thích ở cả bốn lớp: cú pháp, schema, ngữ nghĩa và byte-level nếu có yêu cầu chữ ký hoặc canonicalization. Với JSON, hãy kiểm soát null/presence, naming, enum, number, date/time, unknown fields và polymorphic typing; với XML, cần chú ý namespace, attribute/element, thứ tự, XSD, encoding và XXE. Trong Java, migration còn liên quan tới JDK 11 loại JAXB đóng gói sẵn, Jakarta namespace, Java records và JPMS reflection. Quy trình đáng tin cậy là xác định contract, giữ golden fixtures từ dữ liệu thật, kiểm thử cả backward/forward compatibility, triển khai consumer trước producer khi phù hợp và chuẩn bị rollback dữ liệu trước khi bật schema mới.
