# Xác định cấu trúc JSON công khai độc lập với lớp triển khai

Một API có thể thay đổi cách tổ chức code nội bộ nhiều lần: đổi tên field Java, tách class, chuyển từ entity sang record, thay ORM, gom hoặc chia module, hay thay thư viện xử lý JSON. Những thay đổi đó không nên tự động làm thay đổi JSON mà client đang sử dụng.

Muốn giữ hợp đồng ổn định, cần xác định **cấu trúc JSON công khai** như một phần riêng của thiết kế API. Cấu trúc đó mô tả tên property, kiểu dữ liệu, quy tắc null, định dạng ngày giờ, enum, object lồng nhau, cách biểu diễn lỗi và quy tắc tương thích. Lớp Java chỉ là một cách triển khai để đọc hoặc tạo ra cấu trúc đã công bố.

Trong Jackson, có thể thực hiện điều này bằng DTO/record dành riêng cho wire format, annotation như `@JsonProperty` và `@JsonCreator`, cấu hình serializer/deserializer, mix-in hoặc adapter mapping. Lựa chọn phụ thuộc mức độ cần tách biệt giữa hợp đồng và model nội bộ.

## 1. Hợp đồng JSON là gì?

Hợp đồng JSON là thỏa thuận giữa bên gửi và bên nhận về hình dạng, ý nghĩa và quy tắc của dữ liệu trao đổi. Nó trả lời các câu hỏi:

- Object có những property nào?
- Tên property chính xác là gì?
- Mỗi property có kiểu dữ liệu nào?
- Property có bắt buộc không?
- Giá trị null có được phép không?
- Ngày giờ, số thập phân và enum được biểu diễn ra sao?
- Object lồng nhau, collection và dữ liệu đa hình có hình dạng nào?
- Client cũ sẽ xử lý thế nào khi server thêm property?
- Server sẽ xử lý thế nào khi nhận property không biết?
- Field nào chỉ được đọc, field nào client được gửi?

Ví dụ hợp đồng response:

```json
{
  "customer_id": "cus-1042",
  "display_name": "Nguyen An",
  "status": "ACTIVE",
  "created_at": "2026-04-18T09:30:00Z"
}
```

Hợp đồng có thể quy định:

| Property | Kiểu JSON | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| customer_id | string | Có | Định danh khách hàng ổn định |
| display_name | string | Có | Tên hiển thị |
| status | string | Có | Mã trạng thái công khai |
| created_at | string | Có | Thời điểm tạo theo ISO-8601 UTC |

Các quy tắc này không nên phụ thuộc vào tên field Java, tên cột database hoặc class đang dùng trong service.

## 2. Vì sao không nên để JSON tự phản chiếu lớp triển khai?

Một cách nhanh là serialize trực tiếp domain entity:

```java
public class CustomerEntity {
    private Long id;
    private String fullName;
    private String email;
    private String passwordHash;
    private Instant createdAt;
    private boolean deleted;
    private String internalSegment;

    // getters and setters
}
```

Nếu trả entity trực tiếp, hình dạng JSON có thể bị ảnh hưởng bởi tất cả getter, field visibility, annotation, naming strategy và cấu hình Jackson hiện tại.

Điều này tạo ra một số rủi ro:

1. Đổi tên field Java có thể làm đổi tên JSON.
2. Thêm field nội bộ có thể vô tình công khai dữ liệu.
3. Thay entity ORM hoặc cấu trúc quan hệ có thể làm thay đổi JSON.
4. Getter được thêm cho mục đích nội bộ có thể trở thành property JSON.
5. Lazy relationship có thể khiến serialize truy vấn dữ liệu ngoài ý muốn hoặc tạo vòng tham chiếu.
6. Cấu trúc persistence không nhất thiết phù hợp với nhu cầu của client.
7. Các annotation Jackson rải trên entity khiến model nghiệp vụ phụ thuộc vào chi tiết giao tiếp.

Đặc biệt, serialize entity có thể vô tình lộ thông tin nhạy cảm như password hash, token nội bộ, cờ kiểm soát hoặc dữ liệu chỉ dành cho nhân viên.

Hợp đồng công khai cần được thiết kế có chủ đích. Không nên xem mọi property mà Jackson nhìn thấy là property mà API được phép công bố.

## 3. Tách domain model khỏi wire model

Một giải pháp phổ biến là dùng một DTO riêng cho request hoặc response. DTO này đại diện cho cấu trúc dữ liệu trên đường truyền, thường được gọi là wire model hoặc API model.

Ví dụ domain model:

```java
public class Customer {
    private CustomerId id;
    private PersonName name;
    private EmailAddress email;
    private CustomerStatus status;
    private Instant createdAt;

    // Domain behavior and methods
}
```

Response DTO:

```java
public record CustomerResponse(
    @JsonProperty("customer_id") String customerId,
    @JsonProperty("display_name") String displayName,
    String status,
    @JsonProperty("created_at") Instant createdAt
) {}
```

Mapping:

```java
CustomerResponse toResponse(Customer customer) {
    return new CustomerResponse(
        customer.getId().value(),
        customer.getName().displayName(),
        customer.getStatus().externalCode(),
        customer.getCreatedAt()
    );
}
```

Controller trả DTO:

```java
@GetMapping("/customers/{id}")
public CustomerResponse getCustomer(@PathVariable String id) {
    Customer customer = customerService.findById(id);
    return customerMapper.toResponse(customer);
}
```

Domain model có thể đổi cách lưu trữ hoặc tên method mà JSON vẫn giữ nguyên. Chỉ mapper giữa domain và API model cần được cập nhật khi cách triển khai thay đổi.

Lợi ích của wire DTO:

- **Ổn định**: tên và kiểu JSON được khai báo rõ.
- **An toàn**: chỉ các field được chọn mới được xuất.
- **Độc lập**: entity có thể đổi mà không buộc client đổi theo.
- **Dễ kiểm thử**: có thể test JSON contract riêng.
- **Dễ versioning**: mỗi API version có DTO hoặc adapter tương ứng.
- **Rõ quyền ghi**: request DTO chỉ chứa field client được phép gửi.
- **Dễ tài liệu hóa**: schema công khai không phải suy luận từ entity.

DTO không nhất thiết phải có một class cho mọi object. Hãy tạo kiểu riêng ở ranh giới nơi hợp đồng cần ổn định hoặc khác với model nội bộ. Những kiểu đơn giản, nội bộ và không được công bố có thể dùng model hiện có nếu điều đó không làm ràng buộc API.

## 4. Đặt tên JSON tường minh bằng @JsonProperty

Tên field Java không nhất thiết phải giống tên JSON. Dùng `@JsonProperty` để khai báo tên công khai:

```java
public record CustomerResponse(
    @JsonProperty("customer_id") String customerId,
    @JsonProperty("display_name") String displayName,
    @JsonProperty("created_at") Instant createdAt
) {}
```

JSON đầu ra:

```json
{
  "customer_id": "cus-1042",
  "display_name": "Nguyen An",
  "created_at": "2026-04-18T09:30:00Z"
}
```

Nếu sau này đổi component Java từ displayName thành label, tên JSON vẫn là display_name nếu annotation được giữ nguyên.

`@JsonProperty` cũng có thể dùng trên field, getter, setter hoặc constructor parameter. Với record, annotation trên component giúp biểu đạt tên property ngay tại khai báo dữ liệu.

Không nên phụ thuộc hoàn toàn vào một naming strategy toàn cục để định nghĩa hợp đồng công khai quan trọng. Naming strategy hữu ích để áp dụng quy ước nhất quán, nhưng tên cụ thể của property công khai vẫn nên được xác nhận bằng contract test và schema.

## 5. Naming strategy và tên property công khai

Jackson hỗ trợ các quy tắc đặt tên như camel case, snake case và kebab case. Có thể cấu hình:

```java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
```

Với DTO:

```java
public record CustomerResponse(
    String customerId,
    String displayName,
    Instant createdAt
) {}
```

mapper dùng snake case có thể tạo:

```json
{
  "customer_id": "cus-1042",
  "display_name": "Nguyen An",
  "created_at": "2026-04-18T09:30:00Z"
}
```

Naming strategy tiện khi toàn bộ API dùng cùng quy ước. Tuy nhiên, nếu một property có tên ngoại lệ hoặc hợp đồng phải giữ nguyên một tên cũ, có thể khai báo tường minh bằng `@JsonProperty`.

Cần nhớ naming strategy là cấu hình của mapper. Nếu một mapper khác được dùng cho message queue hoặc file export, output có thể khác. Vì vậy:

- Định nghĩa rõ mapper nào chịu trách nhiệm cho từng giao thức.
- Không tạo mapper tùy tiện trong service.
- Kiểm thử output bằng mapper thực tế mà ứng dụng sử dụng.
- Ghi rõ các tên ngoại lệ trong DTO hoặc mix-in.

## 6. Request DTO và response DTO có trách nhiệm khác nhau

Không nên mặc định một DTO dùng cho cả đọc và ghi.

Response DTO mô tả dữ liệu server công bố. Request DTO mô tả dữ liệu client được phép gửi. Hai cấu trúc có thể khác nhau.

Ví dụ response:

```java
public record CustomerResponse(
    String id,
    String name,
    String email,
    String status,
    Instant createdAt
) {}
```

Request tạo khách hàng:

```java
public record CreateCustomerRequest(
    @NotBlank String name,
    @Email String email
) {}
```

Request cập nhật tên:

```java
public record RenameCustomerRequest(
    @NotBlank String name
) {}
```

Client không được tự gửi id, status, createdAt hoặc field quản trị trong request tạo. Server tạo các giá trị đó theo quy tắc nghiệp vụ.

Dùng DTO riêng giúp tránh mass assignment: nếu nhận thẳng entity, client có thể gửi property mà endpoint không định cho phép thay đổi.

### 6.1. @JsonProperty access

Trong một số trường hợp, cùng một DTO cần property chỉ đọc hoặc chỉ ghi. Jackson hỗ trợ:

- `JsonProperty.Access.READ_ONLY`: property được serialize nhưng không được dùng để bind từ JSON input thông thường.
- `JsonProperty.Access.WRITE_ONLY`: property được bind từ input nhưng không xuất trong JSON output.
- `JsonProperty.Access.READ_WRITE`: property có thể đọc và ghi theo cả hai chiều.

Ví dụ:

```java
public class CredentialView {

    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;
}
```

Đây là công cụ kiểm soát binding, nhưng không thay thế phân tách request/response khi hai hợp đồng có mục đích khác nhau. Với API công khai, DTO riêng thường dễ hiểu và an toàn hơn.

## 7. Kiểm soát property được xuất

Có thể dùng annotation để xác định rõ property nào thuộc JSON contract.

`@JsonIgnore` loại property khỏi binding theo cấu hình annotation:

```java
public class InternalCustomerView {

    private String name;

    @JsonIgnore
    private String internalNote;
}
```

`@JsonInclude` điều khiển property nào được đưa vào output dựa trên giá trị:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record CustomerResponse(
    String id,
    String name,
    String nickname
) {}
```

Với cấu hình này, property null có thể bị bỏ khỏi JSON. Điều đó khác với việc serialize thành:

```json
{
  "nickname": null
}
```

Hai hình dạng này có thể mang ý nghĩa khác nhau với client. Vì vậy, quyết định bỏ field null hay giữ field với null phải thuộc hợp đồng.

Các lựa chọn thường gặp:

| Cấu hình | Hành vi output |
| --- | --- |
| ALWAYS | Luôn ghi property theo quy tắc serializer |
| NON_NULL | Bỏ property có giá trị null |
| NON_EMPTY | Bỏ giá trị rỗng theo định nghĩa của kiểu |
| NON_DEFAULT | Bỏ giá trị được xem là mặc định |
| NON_ABSENT | Bỏ giá trị absent như một số kiểu optional/reference |

Không nên bật NON_DEFAULT toàn cục mà không hiểu tác động. Một giá trị false, 0 hoặc chuỗi rỗng có thể là dữ liệu có ý nghĩa trong hợp đồng.

## 8. Phân biệt missing, null và default

Trong JSON, property có thể:

1. Không xuất hiện.
2. Xuất hiện với giá trị null.
3. Xuất hiện với một giá trị cụ thể.
4. Bị bỏ khỏi output do serialization inclusion rule.

Ví dụ:

```json
{}
```

```json
{
  "nickname": null
}
```

```json
{
  "nickname": "An"
}
```

Các trạng thái này không tương đương. Khi thiết kế request, cần quy định rõ:

- Thiếu field có nghĩa là giữ giá trị, dùng default hay báo lỗi?
- Null có được phép không?
- Null có nghĩa xóa giá trị không?
- Chuỗi rỗng có hợp lệ không?
- Giá trị mặc định do server áp dụng ở đâu?

Với DTO immutable, có thể dùng constructor/record và validation để yêu cầu field bắt buộc. Nếu cần phân biệt missing với null trong một partial update, một field nullable đơn giản có thể không đủ; cần presence wrapper, tree model hoặc một request model có trạng thái hiện diện rõ ràng.

Không nên dựa vào Java primitive để mô tả property optional nếu cần phân biệt “client không gửi” với “client gửi false/0”. Dùng wrapper hoặc kiểu biểu diễn presence phù hợp.

## 9. Quy định kiểu dữ liệu JSON, không để kiểu Java quyết định ngẫu nhiên

JSON có các kiểu cơ bản: object, array, string, number, boolean và null. Java có nhiều kiểu phong phú hơn. Hợp đồng cần xác định ánh xạ rõ ràng.

| Dữ liệu nghiệp vụ | Biểu diễn JSON thường dùng | Điều cần quy định |
| --- | --- | --- |
| ID | string | Format, độ dài, phân biệt hoa thường |
| Số lượng | number integer | Phạm vi và đơn vị |
| Tiền | number hoặc string decimal | Độ chính xác, scale, rounding |
| Ngày | string date | Format và timezone nếu có |
| Enum | string code | Giá trị công khai ổn định |
| Binary | string Base64 hoặc URL | Encoding, kích thước, cách tải |
| Map | object | Quy tắc key và value |
| Danh sách | array | Thứ tự, uniqueness, empty/null |

Không nên để Java implementation tự quyết định một cách vô tình. Ví dụ, BigDecimal có thể được ghi dưới dạng JSON number, nhưng hợp đồng cần nói rõ scale/precision và client có thể xử lý decimal chính xác đến đâu.

### 9.1. ID nên được xem là định danh, không phải số học

Một mã như "000123" thường nên được biểu diễn thành string, ngay cả khi nó chỉ chứa chữ số. Nếu serialize thành number, các số 0 ở đầu có thể mất và client có thể coi nó là đại lượng để tính toán.

Ví dụ:

```json
{
  "customer_id": "000123"
}
```

Nếu ID là số thứ tự có ý nghĩa toán học và phạm vi rõ ràng, number có thể phù hợp. Hãy chọn dựa trên ý nghĩa của dữ liệu, không dựa trên việc Java field tình cờ là Long hay String.

## 10. Định dạng ngày giờ ổn định

Ngày giờ thường gây khác biệt giữa các hệ thống do timezone, precision và format.

Một hợp đồng nên chọn định dạng rõ, ví dụ ISO-8601 UTC:

```json
{
  "created_at": "2026-04-18T09:30:00Z"
}
```

Trong Java, dùng kiểu biểu diễn phù hợp:

- Instant cho thời điểm tuyệt đối trên timeline.
- OffsetDateTime nếu cần giữ offset được gửi.
- LocalDate cho ngày lịch không gắn giờ.
- LocalDateTime cho ngày giờ địa phương khi timezone được xác định bên ngoài.

Không dùng LocalDateTime để đại diện một thời điểm toàn cầu nếu không có timezone/offset. Hai hệ thống ở timezone khác nhau có thể hiểu cùng chuỗi theo thời điểm khác nhau.

Jackson thường cần module Java Time như jackson-datatype-jsr310 để xử lý các kiểu java.time:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Hãy xác nhận cấu hình thực tế và kiểm thử chuỗi output. Không để một môi trường ghi timestamp dạng number trong khi môi trường khác ghi ISO string.

## 11. Enum công khai cần code ổn định

Serialize trực tiếp enum theo tên Java có thể làm hợp đồng phụ thuộc tên constant:

```java
public enum CustomerStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
```

Nếu đổi SUSPENDED thành PAUSED, JSON cũng có thể đổi theo. Có thể giữ code công khai ổn định bằng DTO string hoặc enum có external code:

```java
public enum CustomerStatus {
    ACTIVE("ACTIVE"),
    SUSPENDED("ON_HOLD"),
    CLOSED("CLOSED");

    private final String externalCode;

    CustomerStatus(String externalCode) {
        this.externalCode = externalCode;
    }

    public String externalCode() {
        return externalCode;
    }
}
```

Mapper chuyển status thành code:

```java
CustomerResponse toResponse(Customer customer) {
    return new CustomerResponse(
        customer.getId().value(),
        customer.getName().displayName(),
        customer.getStatus().externalCode(),
        customer.getCreatedAt()
    );
}
```

Đối với request, cần ánh xạ code ngược và xử lý giá trị không biết theo chính sách rõ ràng. Không dùng enum ordinal làm hợp đồng JSON vì thứ tự constant có thể thay đổi.

Nếu dùng @JsonValue và @JsonCreator trên enum, cần kiểm thử cả serialize lẫn deserialize, đồng thời quy định cách xử lý code cũ hoặc không nhận diện được.

## 12. Object lồng nhau và cấu trúc collection

Hợp đồng nên định nghĩa rõ object con thay vì để cấu trúc ORM quyết định.

Ví dụ:

```json
{
  "customer_id": "cus-1042",
  "address": {
    "line1": "12 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "country_code": "VN"
  },
  "tags": ["premium", "newsletter"]
}
```

DTO tương ứng:

```java
public record AddressResponse(
    String line1,
    String city,
    @JsonProperty("country_code") String countryCode
) {}

public record CustomerResponse(
    @JsonProperty("customer_id") String customerId,
    AddressResponse address,
    List<String> tags
) {}
```

Quy định thêm:

- address có bắt buộc không?
- address: null khác với bỏ address như thế nào?
- tags có thể là null không, hay luôn là array rỗng khi không có phần tử?
- Thứ tự trong tags có ý nghĩa không?
- Có cho phép tag trùng không?
- Object con có được mở rộng trong phiên bản sau không?

Không trả trực tiếp collection lazy hoặc entity relationship từ ORM. Chuyển thành DTO với dữ liệu cần thiết để kiểm soát số lượng property, tránh vòng tham chiếu và tránh truy vấn không mong muốn.

## 13. Dữ liệu đa hình và type discriminator công khai

Một property có thể chứa nhiều loại object. Hợp đồng cần cách phân biệt chúng.

Ví dụ một notification có thể là email hoặc SMS:

```json
{
  "type": "email",
  "recipient": "an@example.com",
  "subject": "Welcome"
}
```

hoặc:

```json
{
  "type": "sms",
  "recipient": "+84000000000",
  "message": "Welcome"
}
```

Có thể dùng discriminator ổn định:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "type"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = EmailNotification.class, name = "email"),
    @JsonSubTypes.Type(value = SmsNotification.class, name = "sms")
})
public sealed interface Notification
    permits EmailNotification, SmsNotification {
}
```

Không nên đưa tên class Java hoặc tên package vào JSON như một định danh type công khai. Tên class có thể đổi khi refactor, trong khi discriminator như "email" là một phần của hợp đồng.

Nếu API công khai nhận dữ liệu đa hình từ client, chỉ cho phép các subtype đã được xác định. Tránh cấu hình polymorphic typing quá rộng khiến dữ liệu bên ngoài có thể yêu cầu Jackson khởi tạo class tùy ý.

Với schema phức tạp hoặc client đa ngôn ngữ, có thể dùng DTO riêng cho từng subtype và tài liệu hóa discriminator cùng các field bắt buộc.

## 14. Unknown property và khả năng tương thích tiến

Khi server thêm một property mới, client cũ có thể không biết property đó. Hành vi phụ thuộc parser/client:

- Client strict có thể từ chối field không biết.
- Client lenient có thể bỏ qua.
- Client dùng extension map có thể giữ lại field.
- Client forward payload có thể cần bảo toàn dữ liệu lạ.

Jackson có thể cấu hình bỏ qua property chưa biết:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerResponse(
    String id,
    String name
) {}
```

Hoặc bật strict behavior để phát hiện payload sai:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
```

Chọn chính sách theo vai trò:

- Với response client nhận từ server, khả năng bỏ qua field mới thường giúp tương thích tiến.
- Với request server nhận từ client, strictness có thể giúp phát hiện lỗi tên field và payload sai hợp đồng.
- Với message cần forward extension, có thể giữ unknown field trong Map/JsonNode.

Đừng bật hoặc tắt FAIL_ON_UNKNOWN_PROPERTIES một cách toàn cục mà không xem xét tất cả giao thức dùng mapper đó. Có thể cấu hình theo reader hoặc DTO khi cần.

## 15. Versioning và thay đổi tương thích

Hợp đồng JSON sẽ phát triển. Mỗi thay đổi cần được đánh giá theo ảnh hưởng tới producer và consumer.

| Thay đổi | Mức độ tương thích thường gặp | Ghi chú |
| --- | --- | --- |
| Thêm optional property vào response | Thường tương thích tiến nếu client bỏ qua unknown | Client strict có thể lỗi |
| Thêm required property vào request | Có thể phá client cũ | Client cũ không gửi field |
| Đổi tên property | Thường breaking | Có thể hỗ trợ alias trong giai đoạn chuyển tiếp |
| Xóa property | Có thể breaking | Client cũ có thể còn phụ thuộc |
| Đổi kiểu string thành number | Breaking | Parser và logic client có thể lỗi |
| Đổi enum code | Breaking | Client có thể không nhận diện |
| Đổi null thành omitted | Có thể thay đổi semantics | Client có thể phân biệt hai trạng thái |
| Đổi array thành object | Breaking | Cấu trúc hoàn toàn khác |
| Thay đổi ý nghĩa field mà giữ tên | Nguy hiểm | Schema vẫn parse nhưng business logic sai |

### 15.1. Alias để hỗ trợ tên cũ

Nếu server cần đổi tên input property, @JsonAlias có thể nhận cả tên mới và tên cũ:

```java
public record CreateCustomerRequest(
    @JsonProperty("display_name")
    @JsonAlias("name")
    String displayName
) {}
```

Đầu ra vẫn dùng tên chính thức theo @JsonProperty; alias chủ yếu hỗ trợ deserialize input. Đây có thể là bước chuyển tiếp để client nâng cấp dần.

Alias không tự giải quyết xung đột nếu payload gửi đồng thời cả hai tên. Hãy định nghĩa cách xử lý và kiểm thử trường hợp đó.

### 15.2. Versioning theo URL hoặc media type

API có thể version theo URL:

```text
/api/v1/customers
/api/v2/customers
```

hoặc theo media type/header khi kiến trúc cần content negotiation.

Mỗi version cần hợp đồng có thể xác định và kiểm thử riêng. Có thể dùng CustomerV1Response và CustomerV2Response, hoặc adapter chuyển domain model sang từng wire DTO.

Không nên đổi âm thầm ý nghĩa field trong cùng version chỉ vì code nội bộ đã thay đổi.

## 16. JSON Schema và OpenAPI là mô tả công khai

DTO Java và annotation Jackson giúp triển khai mapping, nhưng client không nên phải đọc source code Java để biết hợp đồng.

Có thể mô tả schema bằng JSON Schema hoặc OpenAPI. Ví dụ JSON Schema rút gọn:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "customer_id",
    "display_name",
    "status"
  ],
  "properties": {
    "customer_id": {
      "type": "string",
      "minLength": 1
    },
    "display_name": {
      "type": "string",
      "minLength": 1
    },
    "status": {
      "type": "string",
      "enum": ["ACTIVE", "ON_HOLD", "CLOSED"]
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    }
  },
  "additionalProperties": false
}
```

Schema có thể quy định type, required, enum, format như date-time, minimum, maximum, minLength, maxLength và additionalProperties.

OpenAPI bổ sung mô tả endpoint, method, status code, request body, response và authentication. DTO Java có thể là một cách triển khai schema, nhưng không phải bản thân tài liệu công khai.

Nếu sinh OpenAPI từ annotation, vẫn cần kiểm tra schema sinh ra có đúng ý nghĩa hợp đồng hay không. Annotation triển khai và tài liệu API có thể lệch nhau nếu cấu hình không đầy đủ.

## 17. Dùng mix-in hoặc serializer riêng khi không thể sửa lớp

Đôi khi không thể thêm annotation lên class:

- Class đến từ thư viện bên ngoài.
- Model được chia sẻ với nhiều ứng dụng.
- Không muốn đặt annotation Jackson vào domain module.
- Cùng một class cần hai hình dạng JSON cho hai giao thức.

Jackson hỗ trợ mix-in để gắn annotation bên ngoài:

```java
abstract class CustomerMixin {

    @JsonProperty("customer_id")
    abstract CustomerId getId();

    @JsonIgnore
    abstract String getInternalNote();
}
```

Đăng ký:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addMixIn(Customer.class, CustomerMixin.class)
    .build();
```

Mix-in giúp giữ class gốc không phụ thuộc annotation Jackson. Tuy nhiên, nó vẫn là cấu hình theo class và mapper. Nếu cùng class cần nhiều wire shape, DTO/adapters riêng thường dễ kiểm soát hơn.

Custom serializer/deserializer phù hợp khi cấu trúc khác biệt đáng kể hoặc cần logic mapping đặc biệt. Không nên viết custom serializer chỉ để đổi một tên field đơn giản; @JsonProperty hoặc DTO thường dễ đọc hơn.

## 18. Kiểm thử hợp đồng JSON

Contract test xác nhận JSON thực tế đúng với cấu trúc đã công bố, thay vì chỉ kiểm tra object Java có giá trị đúng.

Ví dụ serialize response:

```java
@Test
void writesStableCustomerResponseContract() throws Exception {
    CustomerResponse response = new CustomerResponse(
        "cus-1042",
        "Nguyen An",
        "ACTIVE",
        Instant.parse("2026-04-18T09:30:00Z")
    );

    JsonNode json = mapper.readTree(
        mapper.writeValueAsString(response)
    );

    assertEquals("cus-1042", json.path("customer_id").asText());
    assertEquals("Nguyen An", json.path("display_name").asText());
    assertEquals("ACTIVE", json.path("status").asText());
    assertEquals(
        "2026-04-18T09:30:00Z",
        json.path("created_at").asText()
    );
    assertFalse(json.has("customerId"));
}
```

Test này xác nhận tên JSON công khai. Nó không phụ thuộc component Java có tên customerId hay id.

### 18.1. Kiểm thử deserialize request

```java
@Test
void readsPublicRequestNames() throws Exception {
    String json = """
        {
          "display_name": "Nguyen An",
          "email": "an@example.com"
        }
        """;

    CreateCustomerRequest request =
        mapper.readValue(json, CreateCustomerRequest.class);

    assertEquals("Nguyen An", request.displayName());
    assertEquals("an@example.com", request.email());
}
```

### 18.2. Kiểm thử không lộ field nội bộ

Có thể kiểm tra danh sách field JSON:

```java
@Test
void doesNotExposeInternalFields() throws Exception {
    String json = mapper.writeValueAsString(response);

    assertFalse(json.contains("passwordHash"));
    assertFalse(json.contains("internalSegment"));
    assertFalse(json.contains("deleted"));
}
```

Tốt hơn nữa là parse JSON thành tree và xác nhận các property nhạy cảm không xuất hiện. Test nên gắn với DTO response công khai.

### 18.3. Snapshot test và semantic test

Snapshot test lưu JSON mẫu và so sánh output. Nó hữu ích để phát hiện mọi thay đổi nhưng có thể nhạy với whitespace hoặc thứ tự property.

Semantic contract test parse JSON rồi kiểm tra tên, kiểu, giá trị và presence. Nó thường ít phụ thuộc cách format hơn.

Có thể kết hợp:

- Semantic tests cho các quy tắc quan trọng.
- Snapshot/golden file cho các payload lớn và cần xem diff.
- Schema validation để kiểm tra payload theo JSON Schema/OpenAPI.
- Compatibility tests giữa phiên bản producer và consumer.

Không nên chỉ kiểm tra serialize rồi deserialize bằng cùng mapper. Nếu serializer và deserializer cùng mắc một lỗi, round-trip vẫn có thể thành công dù JSON không đúng hợp đồng bên ngoài.

## 19. Tách mapper theo giao thức khi cần

Một ứng dụng có thể trao đổi nhiều loại JSON:

- HTTP API công khai.
- Event message.
- File export.
- Cache payload.
- Internal RPC.

Mỗi giao thức có thể có quy tắc khác nhau về naming, unknown property, date/time, polymorphism hoặc inclusion.

Nếu dùng một mapper toàn cục với cấu hình thay đổi theo request, các giao thức có thể ảnh hưởng lẫn nhau. Có thể tạo mapper được cấu hình cố định cho từng giao thức, hoặc dùng ObjectReader/ObjectWriter chuyên biệt.

Ví dụ:

```java
ObjectMapper apiMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();

ObjectWriter compactApiWriter = apiMapper.writer()
    .without(SerializationFeature.INDENT_OUTPUT);
```

Hoàn tất cấu hình trước khi sử dụng mapper đồng thời. Không sửa naming strategy hoặc module trên mapper đang phục vụ request.

Dù dùng một hay nhiều mapper, wire DTO và contract test vẫn là nguồn kiểm soát quan trọng. Mapper chỉ là cơ chế thực thi hợp đồng.

## 20. Quy trình thiết kế JSON contract độc lập với lớp triển khai

Khi xây dựng một API hoặc message schema mới:

1. Xác định consumer và mục đích của payload.
2. Viết ví dụ JSON công khai trước khi quyết định entity hoặc class Java.
3. Định nghĩa tên property, kiểu, required, nullable, format và semantics.
4. Tách request DTO và response DTO khi quyền ghi/đọc khác nhau.
5. Dùng @JsonProperty cho tên công khai ổn định.
6. Dùng mapping giữa domain model và wire DTO.
7. Quy định enum code, date/time, decimal và polymorphic discriminator.
8. Quyết định chính sách unknown property và additional properties.
9. Công bố schema qua OpenAPI/JSON Schema hoặc tài liệu tương đương.
10. Viết contract tests cho serialize và deserialize.
11. Đánh giá mọi thay đổi theo backward/forward compatibility.
12. Version hóa khi thay đổi không tương thích.
13. Kiểm tra mapper thực tế, không chỉ mapper mới tạo trong unit test.
14. Giữ dữ liệu nội bộ và field nhạy cảm ngoài public DTO.

## 21. Bài thực hành tổng hợp

Xây dựng API khách hàng với domain model:

```java
public class Customer {
    private CustomerId id;
    private PersonName name;
    private EmailAddress email;
    private CustomerStatus status;
    private Instant createdAt;
    private String internalNote;

    // Domain behavior
}
```

Thiết kế hợp đồng response:

```json
{
  "customer_id": "cus-1042",
  "display_name": "Nguyen An",
  "email": "an@example.com",
  "status": "ACTIVE",
  "created_at": "2026-04-18T09:30:00Z"
}
```

Thực hiện:

1. Tạo CustomerResponse record có tên property đúng hợp đồng.
2. Tạo CreateCustomerRequest chỉ gồm field client được phép gửi.
3. Viết mapper từ Customer sang CustomerResponse.
4. Đổi tên field nội bộ trong Customer nhưng giữ nguyên JSON output.
5. Thêm internalNote vào entity và xác nhận response không công khai field này.
6. Quy định enum code ổn định cho CustomerStatus.
7. Cấu hình Java Time để created_at có định dạng date-time thống nhất.
8. Xác định email nullable hay required và viết test tương ứng.
9. Tạo JSON Schema cho response.
10. Viết contract test xác nhận tên, kiểu và presence của các property.
11. Thử thêm optional property và đánh giá ảnh hưởng với client strict/lenient.
12. Thử đổi tên property và dùng alias để mô phỏng giai đoạn chuyển tiếp.
13. Tạo version DTO thứ hai nếu cần một thay đổi breaking.
14. Kiểm tra response không chứa field nội bộ hoặc thông tin không được phép.

Bài thực hành hoàn thành khi có thể thay đổi class triển khai mà JSON contract vẫn giữ nguyên, và mọi thay đổi JSON công khai đều được xem xét, tài liệu hóa và kiểm thử có chủ đích.

## 22. Nguyên tắc ghi nhớ

- JSON công khai là hợp đồng giữa producer và consumer, không phải bản phản chiếu tự động của entity Java.
- Hợp đồng cần định nghĩa tên, kiểu, required, nullable, format và semantics của property.
- Dùng request/response DTO để kiểm soát dữ liệu đi qua ranh giới API.
- @JsonProperty giữ tên JSON ổn định khi tên component Java thay đổi.
- Naming strategy tiện cho quy ước chung nhưng phải được kiểm thử trên mapper thực tế.
- @JsonIgnore, @JsonInclude và JsonProperty.Access kiểm soát binding/output; chúng không thay thế thiết kế DTO.
- Missing, null, empty và default là các trạng thái khác nhau.
- ID, decimal, date/time và enum cần format công khai ổn định.
- Không công khai tên class Java làm discriminator type.
- Unknown property policy cần phù hợp với request, response và message forwarding.
- Thêm field, đổi tên, đổi kiểu hoặc đổi semantics có thể ảnh hưởng compatibility.
- JSON Schema/OpenAPI mô tả hợp đồng cho consumer; annotation Java chỉ là một phần triển khai.
- Mix-in hoặc custom serializer hữu ích khi không thể sửa class hoặc cần mapping đặc biệt.
- Contract tests phải kiểm tra JSON thực tế, không chỉ round-trip trong cùng mapper.
- Giữ field nội bộ, dữ liệu nhạy cảm và cấu trúc persistence ngoài public contract.

Hãy thiết kế JSON công khai trước, sau đó ánh xạ model nội bộ vào cấu trúc đó. Khi hợp đồng được biểu đạt bằng DTO/schema và được kiểm thử độc lập, việc đổi tên class, thay ORM hoặc tái cấu trúc domain không còn tự động làm thay đổi dữ liệu mà client đang phụ thuộc.
