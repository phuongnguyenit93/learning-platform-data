# Coi dữ liệu JSON bên ngoài là đầu vào không tin cậy

JSON là định dạng văn bản, nhưng không có nghĩa dữ liệu JSON nhận từ client, webhook, file import, message broker hoặc hệ thống đối tác là an toàn. Một payload có thể đúng cú pháp nhưng vẫn cố tình làm ứng dụng tiêu tốn bộ nhớ, CPU, tạo object ngoài dự kiến, ghi đè thuộc tính do server quản lý hoặc đưa dữ liệu độc hại vào log và hệ thống downstream.

Jackson giúp parse JSON và ánh xạ token thành Java object. Nó không tự xác thực người gửi, không quyết định người dùng có quyền thực hiện thao tác hay không và không thay thế chính sách bảo mật của ứng dụng. Cần cấu hình parser và mapper có chủ đích, giới hạn tài nguyên ở tầng nhận dữ liệu, dùng DTO allowlist, kiểm soát polymorphic typing, kiểm tra dữ liệu sau binding và xử lý payload theo đúng ranh giới tin cậy.

Bài học này tập trung vào Jackson Databind/Core trong ứng dụng Java. Các ví dụ dùng Jackson 2.x và package `com.fasterxml.jackson`. Một số API giới hạn parser có mặt ở các phiên bản Jackson 2.x mới; hãy đối chiếu với phiên bản thực tế trong dependency tree của dự án.

## 1. JSON hợp lệ không đồng nghĩa dữ liệu đáng tin

Parser chỉ có thể xác nhận dữ liệu tuân theo cú pháp JSON. Ví dụ sau là JSON hợp lệ:

```json
{
  "username": "an",
  "role": "admin",
  "quantity": 999999,
  "note": "..."
}
```

Nhưng điều đó không chứng minh:

- Người gửi được phép tự chọn `role`.
- Số lượng lớn như vậy được phép trong nghiệp vụ.
- `username` thuộc về người đang đăng nhập.
- `note` không chứa dữ liệu độc hại khi hiển thị hoặc ghi log.
- Payload có kích thước và độ sâu hợp lý.
- Kiểu object được yêu cầu trong JSON là kiểu mà ứng dụng muốn khởi tạo.

Một cách nhìn hữu ích là phân biệt ba câu hỏi:

| Câu hỏi | Thành phần chịu trách nhiệm chính |
|---|---|
| Body có phải JSON hợp lệ và nằm trong giới hạn tài nguyên không? | HTTP ingress, Jackson Core parser và cấu hình stream constraints |
| JSON có ánh xạ vào đúng kiểu dữ liệu được API cho phép không? | Jackson Databind, DTO, subtype allowlist và mapper configuration |
| Dữ liệu có được phép và hợp lệ trong trạng thái hệ thống hiện tại không? | Authentication, authorization, Bean Validation và domain/application service |

Không gộp ba câu hỏi này thành một khái niệm “Jackson đã parse thành công”.

## 2. Xác định ranh giới tin cậy

Hãy coi dữ liệu đến từ những nguồn sau là không tin cậy cho tới khi được xác thực và kiểm tra:

- HTTP request từ browser, mobile app hoặc client bên ngoài.
- Webhook và callback từ đối tác.
- Message từ queue/topic, kể cả khi broker nằm trong mạng nội bộ.
- File JSON được tải lên hoặc lấy từ object storage.
- Dữ liệu đồng bộ từ hệ thống khác.
- Cache hoặc dữ liệu lưu lâu dài được tạo bởi phiên bản ứng dụng cũ.
- Payload do một service nội bộ khác gửi nhưng service đó có thể bị lỗi hoặc bị xâm nhập.

Mạng nội bộ, chữ ký webhook hợp lệ hoặc TLS không làm payload tự động đúng schema hay hợp lệ về nghiệp vụ. Chúng giúp xác thực nguồn hoặc bảo vệ đường truyền; ứng dụng vẫn cần kiểm tra nội dung.

Phân loại nguồn dữ liệu giúp chọn chính sách:

| Nguồn | Cần kiểm tra |
|---|---|
| Public API | Body size, token/type, field allowlist, authorization, constraints và business rules |
| Webhook | Chữ ký/timestamp chống replay, schema version, giới hạn payload và idempotency |
| Message broker | Producer identity/ACL, schema version, retry/dead-letter policy và giới hạn record |
| File import | Kích thước file, encoding, record count, duplicate ID và cách ly record lỗi |
| Internal service | Contract version, service identity, timeout/retry và validation độc lập |

## 3. Không cho JSON quyết định tùy ý class Java được khởi tạo

Một rủi ro quan trọng của Jackson Databind là polymorphic deserialization. Nếu payload có thể chỉ định class cần tạo, ứng dụng có thể bị dẫn tới việc khởi tạo một kiểu không nằm trong hợp đồng dự kiến.

Ví dụ JSON có thể chứa thông tin class:

```json
{
  "@class": "some.package.SomeType",
  "value": "..."
}
```

Không nên bật default typing rộng hoặc dùng `JsonTypeInfo.Id.CLASS` cho JSON đến từ nguồn không tin cậy chỉ để tự động deserialize object graph. Trong một số classpath và cấu hình, việc cho dữ liệu bên ngoài điều khiển kiểu runtime có thể mở đường cho gadget chain: một tập hợp class có sẵn thực hiện hành vi nguy hiểm trong quá trình khởi tạo hoặc binding.

JSON không tự thực thi mã. Rủi ro xuất hiện khi ứng dụng cho phép type metadata điều khiển quá trình tạo object và class được chọn có hành vi nguy hiểm hoặc side effect.

### 3.1. Ưu tiên type ID logic với allowlist tường minh

Nếu một property thực sự cần đa hình, dùng `JsonTypeInfo.Id.NAME` và đăng ký các subtype mà use case chấp nhận:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPaymentRequest.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferRequest.class, name = "bank_transfer")
})
public interface PaymentRequest {
}
```

Payload hợp lệ theo allowlist:

```json
{
  "kind": "card",
  "last4": "4242"
}
```

Jackson chỉ có mapping cho những tên đã đăng ký. Type ID không phải tên class Java nên refactor package không làm đổi wire contract.

Nếu đăng ký bằng module, hãy khai báo `NamedType` cụ thể:

```java
SimpleModule paymentTypes = new SimpleModule("payment-request-types");
paymentTypes.registerSubtypes(
        new NamedType(CardPaymentRequest.class, "card"),
        new NamedType(BankTransferRequest.class, "bank_transfer")
);

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(paymentTypes);
```

Base type vẫn cần `@JsonTypeInfo` hoặc type resolver tương ứng. Việc đăng ký subtype chỉ định nghĩa mapping tên logic sang class; nó không tự bật polymorphic typing cho mọi property.

### 3.2. Từ chối type ID không được hỗ trợ

Không tự động fallback một type lạ thành một implementation có quyền rộng. Ví dụ `"kind": "admin_command"` phải bị từ chối nếu subtype đó không nằm trong allowlist của API.

Jackson có `DeserializationFeature.FAIL_ON_INVALID_SUBTYPE`; giữ hành vi từ chối type ID không hợp lệ. Không tắt feature này để che lỗi hoặc âm thầm tạo null cho subtype không nhận diện.

Nếu cần hỗ trợ phiên bản payload cũ, đăng ký alias type ID có chủ đích hoặc viết bước chuyển đổi phiên bản rõ ràng. Không dùng `defaultImpl` để biến mọi type lạ thành một subtype có ý nghĩa nghiệp vụ nếu chưa xác định chính sách.

### 3.3. Chỉ dùng `PolymorphicTypeValidator` khi thật sự cần default typing

Trong một hệ thống legacy có giao thức buộc phải dùng default typing, Jackson yêu cầu validator trong các API default typing hiện đại. Validator cần giới hạn loại class được phép ở phạm vi nhỏ nhất có thể.

Tuy nhiên, với dữ liệu bên ngoài, lựa chọn an toàn hơn thường là không bật default typing và chuyển sang type ID logic cùng danh sách subtype rõ ràng. `PolymorphicTypeValidator` không biến một thiết kế type metadata quá rộng thành an toàn một cách tự động; nó chỉ là một phần của chính sách cho phép subtype và phải được review theo classpath thực tế.

Tránh các allow rule kiểu “mọi class trong toàn bộ application package” nếu package đó chứa nhiều loại có side effect. Cũng không dùng `Id.CLASS` chỉ vì nó tiện khi serialize object graph nội bộ.

## 4. Không deserialize trực tiếp vào class tùy ý hoặc model quá rộng

API nên có target type cụ thể:

```java
CreateOrderRequest request = mapper.readValue(
        json,
        CreateOrderRequest.class
);
```

Hạn chế nhận dữ liệu bên ngoài vào các kiểu quá tổng quát như:

- `Object` rồi sau đó dùng reflection để tạo class theo field trong payload.
- `Class<?>` hoặc tên class do client cung cấp.
- Một entity nội bộ có nhiều property nhạy cảm và trạng thái quản trị.
- Một model chứa nhiều implementation/plugin không cần thiết cho endpoint.

Với JSON động, `JsonNode` hoặc `Map<String, JsonNode>` có thể phù hợp để giữ dữ liệu mà chưa khởi tạo kiểu tùy ý. Nhưng sau đó vẫn cần allowlist key, kiểm tra node type, kích thước và schema trước khi dùng dữ liệu.

Không gọi `Class.forName()` dựa trên chuỗi do JSON cung cấp. Nếu cần chọn handler, ánh xạ một mã logic đã kiểm tra qua map do server quản lý:

```java
Map<String, Handler> handlers = Map.of(
        "create", createHandler,
        "cancel", cancelHandler
);

Handler handler = handlers.get(request.action());
if (handler == null) {
    throw new UnsupportedActionException(request.action());
}
```

## 5. Dùng DTO allowlist để tránh mass assignment

Mass assignment xảy ra khi ứng dụng bind trực tiếp JSON vào object có nhiều field hơn client được phép thay đổi. Ví dụ entity:

```java
public class UserAccount {
    private Long id;
    private String username;
    private boolean admin;
    private boolean locked;
    private String passwordHash;
    private Instant createdAt;

    // getters và setters
}
```

Nếu endpoint deserialize trực tiếp vào `UserAccount`, client có thể gửi:

```json
{
  "username": "an",
  "admin": true,
  "locked": false,
  "passwordHash": "attacker-controlled-value"
}
```

Việc field có setter và Jackson bind được không đồng nghĩa caller có quyền cập nhật field đó.

Tạo DTO chỉ chứa field client được phép gửi:

```java
public record UpdateProfileRequest(
        @NotBlank String displayName,
        @Email String email) {
}
```

Service cập nhật rõ các property được cho phép:

```java
public UserProfile updateProfile(UserId actor, UserId target,
                                 UpdateProfileRequest request) {
    authorization.requireCanEditProfile(actor, target);

    UserAccount account = repository.findById(target)
            .orElseThrow(UserNotFoundException::new);

    account.setDisplayName(request.displayName());
    account.setEmail(request.email());

    return repository.save(account).toProfile();
}
```

`admin`, `locked`, `id`, `passwordHash` và `createdAt` không có trong request DTO nên client không thể cập nhật chúng qua binding thông thường của endpoint này.

### 5.1. `READ_ONLY` và `WRITE_ONLY` là lớp bảo vệ bổ sung

Với model dùng chung, `@JsonProperty(access = READ_ONLY)` có thể bỏ qua giá trị client gửi cho property do server quản lý; `WRITE_ONLY` cho phép nhận giá trị nhưng không serialize lại. `@JsonIgnore` có thể loại property khỏi binding theo cấu hình thông thường.

Các annotation này hữu ích nhưng không thay thế DTO và authorization. Một endpoint khác có thể dùng mapper khác hoặc DTO khác; service vẫn cần kiểm tra quyền trước khi cập nhật trạng thái nhạy cảm.

### 5.2. Không dùng `@JsonIgnoreProperties(ignoreUnknown = true)` như bảo vệ mass assignment

`ignoreUnknown = true` chỉ bỏ qua field mà Jackson không nhận diện. Nếu entity có field `admin` và client gửi `admin`, field đó không phải unknown; Jackson có thể bind nó.

Để ngăn mass assignment, hãy loại field khỏi request type hoặc áp dụng allowlist input rõ ràng. Tính năng bỏ qua field lạ không ngăn client ghi vào field đã tồn tại.

## 6. Cấu hình mapper theo hướng strict có chủ đích

Một mapper nhận input bên ngoài nên có cấu hình phù hợp với hợp đồng. Ví dụ:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .streamReadConstraints(StreamReadConstraints.builder()
                .maxNestingDepth(100)
                .maxStringLength(1_000_000)
                .maxNumberLength(1_000)
                .build())
        .build();

ObjectMapper mapper = new ObjectMapper(factory)
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
        .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Các giới hạn số trong ví dụ là giá trị minh họa, không phải khuyến nghị áp dụng nguyên trạng cho mọi ứng dụng. Chọn ngưỡng theo kích thước request hợp lệ, độ sâu model và nhu cầu nghiệp vụ.

`FAIL_ON_UNKNOWN_PROPERTIES` giúp phát hiện typo và field ngoài hợp đồng. Nếu API cần forward compatibility, có thể dùng `ObjectReader` tolerant cho endpoint cụ thể, nhưng hãy ghi rõ field nào được chấp nhận và test hành vi.

`FAIL_ON_TRAILING_TOKENS` yêu cầu một lần đọc chỉ chứa một JSON value/document. Nếu giao thức là NDJSON hoặc nhiều root value, dùng parser/reader sequence riêng thay vì bật chế độ một document cho toàn stream.

`FAIL_ON_NULL_FOR_PRIMITIVES` tránh một số trường hợp null bị chuyển thành giá trị primitive mặc định. Dùng wrapper type và Bean Validation khi cần phân biệt field thiếu, null và giá trị thực.

### 6.1. Đừng phụ thuộc vào default của mapper

Framework có thể cấu hình `ObjectMapper` khác với mapper được tạo bằng `new ObjectMapper()`. Hãy khai báo các feature quan trọng trong cấu hình ứng dụng và kiểm tra mapper thực tế được HTTP converter hoặc message consumer dùng.

Không thay đổi cấu hình global sau khi mapper đã bắt đầu được chia sẻ giữa nhiều luồng. Tạo `ObjectReader` hoặc `ObjectWriter` riêng cho những khác biệt theo use case.

## 7. Phát hiện duplicate key để tránh parser disagreement

Payload:

```json
{
  "amount": 10,
  "amount": 100000
}
```

Nếu gateway, WAF, audit logger và service xử lý duplicate key khác nhau, một thành phần có thể kiểm tra giá trị đầu trong khi thành phần khác dùng giá trị cuối. Sự khác biệt này có thể gây bypass validation hoặc tạo dấu vết audit sai.

Bật strict duplicate detection:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
```

Parser sẽ báo lỗi khi cùng một object có tên field lặp. Đây là kiểm tra cấu trúc ở tầng parser, trước khi object được bind.

Nếu hệ thống nhận JSON từ nhiều parser khác nhau, cần thống nhất duplicate-key policy ở gateway và consumer. Không để một lớp âm thầm chọn “first wins” trong khi lớp khác chọn “last wins”.

## 8. Giới hạn kích thước body ở tầng HTTP hoặc ingress

Parser constraint chỉ hoạt động khi Jackson bắt đầu đọc. Trước đó, HTTP server, reverse proxy hoặc framework có thể đã nhận và buffer toàn bộ body.

Vì vậy, cần giới hạn ở nhiều lớp:

- Reverse proxy/API gateway: giới hạn request body bytes.
- HTTP server/framework: giới hạn nội dung được đọc hoặc buffer.
- Jackson Core: giới hạn độ sâu, độ dài string và number.
- DTO/validation: giới hạn số phần tử và độ dài nghiệp vụ.
- Streaming consumer: giới hạn record count và batch size.

Ví dụ, một file JSON 500 MB có thể chứa một array hợp lệ với hàng triệu phần tử. `maxStringLength` không giới hạn tổng kích thước array hoặc tổng số object. Nếu endpoint chỉ chấp nhận file 5 MB, hãy từ chối ở ingress trước khi parse.

Không đọc toàn bộ body vào `String` hoặc `byte[]` nếu kích thước có thể lớn và không có giới hạn chặt. Dùng stream, nhưng vẫn cần giới hạn tổng byte và số record.

## 9. Giới hạn nesting depth, string và number

JSON lồng sâu có thể làm tăng chi phí parse, recursion trong binding hoặc gây stack/memory pressure. Chuỗi và số cực dài cũng tiêu tốn tài nguyên và có thể kích hoạt đường xử lý bất thường.

Jackson Core ở các phiên bản hỗ trợ `StreamReadConstraints`:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
        .maxNestingDepth(80)
        .maxStringLength(256_000)
        .maxNumberLength(200)
        .build();

JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(constraints)
        .build();
```

Các ngưỡng cần được chọn từ dữ liệu hợp lệ lớn nhất và margin phù hợp. Nếu một field nghiệp vụ chỉ chứa mã 32 ký tự, DTO constraint `@Size(max = 32)` vẫn cần được áp dụng sau binding; giới hạn parser string là lớp bảo vệ tổng quát trước khi validator chạy.

Parser constraints không thay thế:

- Giới hạn request body bytes.
- Giới hạn array/list size.
- Timeout và rate limit.
- Giới hạn CPU/worker concurrency.
- Giới hạn kích thước dữ liệu được lưu hoặc chuyển tiếp.

## 10. Giới hạn số phần tử và xử lý collection lớn

Một array chứa hàng triệu phần tử có thể làm ứng dụng tạo lượng object lớn dù từng record nhỏ. Bean Validation `@Size(max = ...)` chỉ chạy sau khi Jackson đã tạo collection; nó không ngăn allocation trong lúc parse một list rất lớn.

Với endpoint cần danh sách nhỏ, kiểm tra số phần tử sau binding:

```java
public record BulkUpdateRequest(
        @NotEmpty
        @Size(max = 500)
        List<@NotNull @Valid UpdateItemRequest> items) {
}
```

Nếu cần giới hạn cứng trước khi tạo toàn bộ list, có thể đọc streaming bằng `JsonParser` và dừng khi vượt số record cho phép:

```java
try (JsonParser parser = factory.createParser(inputStream)) {
    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new InvalidRequestShapeException("Expected an array");
    }

    int count = 0;
    while (parser.nextToken() != JsonToken.END_ARRAY) {
        if (++count > MAX_ITEMS) {
            throw new PayloadLimitException("Too many items");
        }

        UpdateItemRequest item = mapper.readValue(parser, UpdateItemRequest.class);
        process(item);
    }
}
```

Đoạn code minh họa streaming từng item; trong triển khai thực tế cần xử lý end-of-input, trailing token, exception và quyền sở hữu stream theo contract. `process()` cũng cần giới hạn batch hoặc backpressure để không tích lũy tất cả item trong bộ nhớ.

## 11. Kiểm soát coercion và kiểu token

Coercion có thể khiến JSON token khác kiểu mong đợi vẫn được chuyển thành Java value. Ví dụ, một chuỗi số có thể được chuyển thành integer theo cấu hình mapper.

Nếu API yêu cầu `quantity` phải là JSON integer, hãy từ chối string:

```json
{"quantity":"3"}
```

Với Jackson 2.12 trở lên, có thể cấu hình coercion theo logical type:

```java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

API coercion và default có thể khác theo Jackson version và logical type. Hãy test token thực tế mà API nhận: string, number, boolean, null, empty string và array/object. Đừng chỉ kiểm tra Java result vì coercion có thể làm hai payload khác nhau cho cùng một giá trị.

Với enum, tránh cho phép ordinal number nếu contract dùng tên logic. Có thể bật `FAIL_ON_NUMBERS_FOR_ENUMS` để từ chối ánh xạ số sang vị trí enum:

```java
mapper.enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS);
```

Tên enum trong JSON nên là wire value ổn định hoặc được ánh xạ qua `@JsonValue`/custom serializer theo contract. Không để client gửi ordinal phụ thuộc thứ tự khai báo enum.

## 12. Xử lý unknown property theo hợp đồng

Strict unknown-property handling giúp phát hiện field ngoài schema:

```java
mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Ví dụ client gửi `quanity` thay vì `quantity`; strict binding phát hiện lỗi thay vì âm thầm bỏ qua typo.

Tuy nhiên, một số API cần forward compatibility để client mới thêm field mà server cũ có thể bỏ qua. Khi đó, hãy quyết định ở cấp endpoint/DTO:

- Strict: từ chối field không được định nghĩa.
- Tolerant: bỏ qua field lạ nhưng vẫn chỉ bind vào DTO đã định nghĩa.
- Extension field: cho phép một vùng riêng như `metadata` nhưng áp dụng giới hạn key, depth, type và size.

Nếu cần tolerant input, tạo reader riêng:

```java
ObjectReader tolerantReader = mapper.readerFor(PartnerEvent.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Không tắt strict mode toàn cục mà không đánh giá các endpoint khác. Và nhớ rằng unknown-property handling không ngăn mass assignment vào field đã tồn tại trong target class.

## 13. Kiểm tra trailing token và ranh giới document

Một API nhận đúng một JSON document nên từ chối dữ liệu thừa sau root value:

```java
ObjectReader requestReader = mapper.readerFor(CreateOrderRequest.class)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Ví dụ:

```text
{"quantity":1} {"admin":true}
```

Nếu chỉ đọc object đầu và bỏ phần còn lại, các thành phần khác nhau có thể hiểu request không giống nhau. Với một request body, hãy định nghĩa rõ một document duy nhất.

Đối với NDJSON hoặc sequence nhiều root value, dùng parser/reader sequence và framing theo giao thức. Không dùng reader một document rồi mong nó tự xử lý mọi record.

## 14. Không để custom deserializer thực hiện side effect

Custom deserializer nên chuyển đổi dữ liệu thành giá trị Java. Tránh để nó:

- Ghi database hoặc gọi repository để thay đổi trạng thái.
- Gửi email, gọi HTTP hoặc publish message.
- Thực thi command, tải file hoặc mở URL từ payload.
- Khởi tạo plugin/class theo tên do JSON cung cấp.
- Đọc file hệ thống theo path do JSON cung cấp.
- Dùng giá trị từ payload làm SQL fragment hoặc expression.

Deserializer có thể được gọi lại khi retry, parse lại hoặc trong test; nó không phải ranh giới transaction của use case. Side effect ở đây khiến việc đọc JSON khó dự đoán và có thể tạo lỗ hổng khi payload được gửi lặp.

Ví dụ không nên làm:

```java
public Product deserialize(JsonParser parser,
                            DeserializationContext ctxt) throws IOException {
    String productCode = parser.getValueAsString();
    return productRepository.findByCode(productCode).orElseThrow();
}
```

Nên deserialize thành mã hoặc DTO:

```java
public record CreateOrderRequest(String productCode, Integer quantity) {
}
```

Sau đó application service resolve product, kiểm tra quyền và trạng thái trong transaction phù hợp.

Custom deserializer vẫn có thể thực hiện chuyển đổi thuần như parse `Money`, chuẩn hóa định dạng hoặc tạo value object có invariant cục bộ. Không đưa truy vấn và hành động bên ngoài vào quá trình parse.

## 15. Kiểm tra dữ liệu sau khi bind

Sau khi Jackson tạo DTO, tiếp tục validate:

```java
public record CreateUserRequest(
        @NotBlank
        @Size(max = 50)
        String username,

        @NotBlank
        @Email
        String email) {
}
```

Sau binding:

```java
CreateUserRequest request = mapper.readValue(json, CreateUserRequest.class);
Set<ConstraintViolation<CreateUserRequest>> violations =
        validator.validate(request);

if (!violations.isEmpty()) {
    throw new RequestValidationException(violations);
}
```

Bean Validation kiểm tra constraint trên object. Nó không xác thực quyền truy cập và không xác nhận dữ liệu tham chiếu còn tồn tại. Application service vẫn cần kiểm tra:

- Người gọi có quyền cập nhật target không?
- ID có thuộc tenant hiện tại không?
- Trạng thái entity có cho phép chuyển đổi không?
- Quan hệ được yêu cầu có hợp lệ không?
- Dữ liệu có xung đột với trạng thái hiện tại không?

## 16. Phân biệt authentication, authorization và validation

Các bước bảo vệ request không thay thế nhau:

- **Authentication:** xác định ai đang gửi request.
- **Authorization:** xác định người đó được phép thực hiện hành động nào trên tài nguyên nào.
- **JSON parsing/binding:** chuyển body thành kiểu dữ liệu được API định nghĩa.
- **Validation:** kiểm tra giá trị và invariant dữ liệu.
- **Business rule:** kiểm tra thao tác có hợp lệ trong trạng thái hiện tại không.

Không dùng field `userId`, `ownerId`, `role` hoặc `isAdmin` do client gửi làm bằng chứng danh tính/quyền. Lấy actor từ security context đã xác thực, sau đó kiểm tra quyền trên tài nguyên ở service.

Ví dụ, request có thể chỉ chứa:

```json
{
  "displayName": "An Nguyen"
}
```

Server lấy user ID từ principal và tự xác định record cần cập nhật. Nếu API cần nhận một `targetUserId`, service vẫn phải kiểm tra caller có quyền thao tác trên target đó.

## 17. Bảo vệ dữ liệu nhạy cảm khi ghi log

Payload không tin cậy có thể chứa password, token, dữ liệu cá nhân, ký tự điều khiển hoặc chuỗi rất dài. Không ghi toàn bộ request body hoặc `toString()` của DTO vào log theo mặc định.

Thay vì log raw body, ưu tiên:

- Correlation ID/request ID.
- Endpoint và loại thao tác.
- Kích thước payload.
- Mã lỗi phân loại.
- Tên field lỗi và vị trí JSON nếu không chứa bí mật.
- Actor/tenant ID đã được phép ghi log theo policy.
- Hash hoặc fingerprint khi cần đối chiếu mà không lưu nội dung gốc.

Nếu cần log một phần payload để điều tra, hãy dùng allowlist field và masking đã được phê duyệt. Tránh ghi Authorization header, cookie, password, access token, refresh token, private key và secret.

Ký tự newline/tab do người dùng cung cấp có thể làm giả nhiều dòng log hoặc phá cấu trúc log. Hãy encode/sanitize giá trị khi log. Không đưa raw JSON vào log format string mà không kiểm soát kích thước và ký tự.

## 18. Không dùng JSON string trực tiếp làm HTML, SQL hoặc shell command

Jackson đảm bảo JSON serialization theo cú pháp JSON. Điều đó không làm chuỗi trở nên an toàn khi đưa vào context khác.

Ví dụ:

- JSON string hiển thị trong HTML vẫn cần HTML escaping hoặc framework template auto-escaping.
- Giá trị JSON dùng trong SQL phải truyền qua parameterized query, không nối chuỗi SQL.
- Giá trị JSON dùng trong shell command không được nối trực tiếp vào command line; dùng API không gọi shell hoặc truyền arguments an toàn.
- URL từ JSON cần kiểm tra scheme/host/allowlist trước khi server gọi ra ngoài.

Đây là các lỗi injection ở context đích, không phải lỗi parser JSON. Serialize một string thành JSON hợp lệ không bảo vệ các hệ thống sử dụng chuỗi đó sau này.

## 19. Cẩn thận với URL, path và tên file trong JSON

Nếu payload có field như `callbackUrl`, `fileName`, `path` hoặc `imageUrl`, đừng thực hiện thao tác mạng/file chỉ vì Jackson deserialize thành công.

Với URL:

- Chỉ cho phép scheme cần thiết, thường là HTTPS nếu có outbound fetch.
- Kiểm tra host theo allowlist nếu use case biết trước domain.
- Chặn loopback, link-local, private network và địa chỉ metadata theo chính sách SSRF.
- Xử lý redirect và DNS resolution cẩn thận; kiểm tra lại đích sau redirect.
- Đặt timeout, response size limit và giới hạn số lần gọi.

Với path/file name:

- Không dùng path client cung cấp trực tiếp để đọc/ghi file hệ thống.
- Chuẩn hóa path và bảo đảm nằm trong thư mục được phép.
- Tạo tên file server-side khi có thể.
- Giới hạn extension, size và loại nội dung theo use case.

Những kiểm tra này thuộc service xử lý hành động sau deserialize, không nên được ngầm thực hiện trong một setter hoặc custom deserializer.

## 20. Cẩn thận với payload lồng nhau và object graph lớn

Một payload có thể chứa array rất lớn, object lồng nhiều tầng hoặc tham chiếu lặp. Các feature như `@JsonIdentityInfo` giúp biểu diễn object graph nhưng không tự giới hạn kích thước graph hoặc số lượng node.

Hãy xác định:

- Độ sâu lồng nhau tối đa.
- Tổng số record/node tối đa.
- Kích thước tối đa của từng string/binary field.
- Số lượng map key/array element.
- Chính sách duplicate ID và unresolved reference.
- Có cho phép chu trình không.
- Thời gian xử lý tối đa và giới hạn concurrency.

Nếu file có hàng triệu record, dùng streaming parser/`MappingIterator` thay vì deserialize toàn bộ thành `List`. Nhưng streaming vẫn cần giới hạn tổng record, backpressure và batch size; nếu consumer tích lũy tất cả record, lợi ích bộ nhớ sẽ mất.

## 21. Xử lý unknown fields và extension metadata an toàn

Một số giao thức cần trường mở rộng:

```json
{
  "eventType": "order_created",
  "eventId": "EV-100",
  "metadata": {
    "source": "mobile",
    "region": "apac"
  }
}
```

Có thể định nghĩa `metadata` thành `Map<String, JsonNode>` thay vì cho phép mọi field top-level:

```java
public record EventEnvelope(
        @NotBlank String eventType,
        @NotBlank String eventId,
        Map<String, JsonNode> metadata) {
}
```

Vùng mở rộng vẫn cần giới hạn:

- Số key tối đa.
- Độ dài key và string value.
- Loại node được chấp nhận.
- Độ sâu nested object/array.
- Tên key bị cấm hoặc reserved.
- Cách dữ liệu được chuyển tiếp sang downstream.

Không biến `metadata` thành nơi nhận mọi object Java tùy ý hoặc nơi chứa command. Nếu downstream chỉ cần một tập key, hãy lọc allowlist trước khi chuyển tiếp.

## 22. Quản lý phiên bản schema

Payload cũ có thể khác schema hiện tại. Không nên giải quyết mọi khác biệt bằng cách tắt strict mode hoặc chấp nhận coercion tùy ý.

Có thể đưa version rõ ràng vào envelope:

```json
{
  "schemaVersion": 2,
  "eventType": "order_created",
  "payload": {
    "orderId": "ORD-100",
    "quantity": 2
  }
}
```

Application layer đọc version, chọn DTO/reader phù hợp và chuyển payload cũ sang model nội bộ chuẩn. Không dùng version do client cung cấp để chọn class tùy ý; ánh xạ version qua bảng cố định do server quản lý.

Nếu cần hỗ trợ nhiều version:

```java
return switch (envelope.schemaVersion()) {
    case 1 -> migrateV1(readPayloadAsV1(envelope.payload()));
    case 2 -> readPayloadAsV2(envelope.payload());
    default -> throw new UnsupportedSchemaVersionException(
            envelope.schemaVersion());
};
```

Mỗi version có schema và migration rule rõ ràng. Test payload đại diện cho từng version, payload version không hỗ trợ và field lạ theo chính sách tương ứng.

## 23. Không tái sử dụng một ObjectMapper với cấu hình thay đổi theo request

`ObjectMapper` thường được chia sẻ và tái sử dụng giữa các thread sau khi cấu hình hoàn tất. Không bật/tắt feature, thay subtype registry hoặc đăng ký mix-in theo dữ liệu client trong mỗi request.

Ví dụ thiết kế không an toàn:

```java
// Không làm điều này trong request handler.
mapper.activateDefaultTyping(...);
mapper.addMixIn(ClientSuppliedType.class, ClientSuppliedMixin.class);
```

Thay vào đó:

- Cấu hình mapper ở startup.
- Dùng DTO/type cụ thể cho endpoint.
- Dùng `ObjectReader` với feature riêng nếu một use case cần policy khác.
- Dùng mapper riêng cho integration có hợp đồng thực sự khác nhau.
- Không để client điều khiển module hoặc subtype registration.

## 24. Cập nhật Jackson và quản lý dependency

Jackson là thư viện xử lý dữ liệu đầu vào nên cần được cập nhật theo chính sách dependency của tổ chức. Khi có advisory hoặc bản vá bảo mật:

1. Xác định version thực tế của `jackson-core`, `jackson-databind`, `jackson-annotations` và các module.
2. Kiểm tra dependency tree để tìm version bắc cầu hoặc nhiều version cùng tồn tại.
3. Nâng lên bản vá được hỗ trợ theo BOM/platform của dự án.
4. Chạy test JSON contract, subtype, custom serializer/deserializer và integration.
5. Kiểm tra các module Jackson đi kèm để tránh lệch version.
6. Theo dõi advisory từ nguồn chính thức và quy trình quản lý lỗ hổng của tổ chức.

Không dựa vào một danh sách “safe class” cố định từ bài viết cũ. Rủi ro polymorphic deserialization phụ thuộc version, classpath, cấu hình và subtype thực tế. Cập nhật dependency và thu hẹp type allowlist là hai việc bổ trợ nhau.

## 25. Kiểm thử bảo mật cho đầu vào JSON

Ngoài test happy path, cần có test cho các trường hợp bất thường:

| Nhóm | Payload/điều kiện | Kết quả mong đợi |
|---|---|---|
| Syntax | JSON thiếu dấu ngoặc hoặc dấu nháy | Parse thất bại, không gọi service |
| Trailing data | Một root object theo sau bởi root value khác | Bị từ chối với reader một document |
| Duplicate key | Cùng tên field xuất hiện hai lần | Parser từ chối nếu strict duplicate detection bật |
| Wrong type | Object gửi vào property integer | Mapping thất bại |
| Coercion | String number gửi vào integer strict | Bị từ chối theo policy |
| Unknown field | Client gửi field ngoài DTO | Bị từ chối hoặc bỏ qua đúng policy đã công bố |
| Polymorphism | Type ID không nằm trong allowlist | Deserialize thất bại |
| Mass assignment | Client gửi `admin`, `ownerId` hoặc trạng thái server-managed | Field không được bind hoặc service từ chối cập nhật |
| Resource limit | Body/string/number/nesting quá lớn | Bị từ chối trước hoặc trong parse theo giới hạn |
| Collection size | Array vượt số phần tử cho phép | Dừng xử lý và không tích lũy vô hạn |
| Validation | Chuỗi rỗng, số âm, nested object sai constraint | Bean Validation thất bại |
| Business | ID không thuộc tenant hoặc không đủ tồn kho | Service từ chối theo rule |
| Logging | Payload chứa secret/newline/chuỗi dài | Không log secret; log được giới hạn và sanitize |

### 25.1. Test rằng service không chạy khi parse/binding thất bại

Ở controller integration test, gửi JSON sai cú pháp hoặc sai kiểu và xác nhận service không được gọi. Ví dụ với Mockito:

```java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":{}}"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(orderService);
```

Điều này xác nhận lỗi binding được xử lý trước khi use case chạy. Với test service, không cần mock Jackson; test trực tiếp các business rule.

### 25.2. Test type ID không hợp lệ

```java
@Test
void rejectsUnregisteredPaymentSubtype() {
    String json = """
            {
              "kind": "arbitrary_class",
              "value": "payload"
            }
            """;

    assertThrows(JsonProcessingException.class,
            () -> mapper.readValue(json, PaymentRequest.class));
}
```

Test cần mapper dùng đúng allowlist subtype. Không chỉ test subtype hợp lệ; phải chứng minh subtype không được đăng ký bị từ chối.

### 25.3. Fuzz và property-based testing

Với parser boundary quan trọng, có thể bổ sung fuzz/property-based test tạo JSON ngẫu nhiên hoặc malformed input. Mục tiêu là phát hiện:

- Parser ném exception có kiểm soát thay vì làm process crash.
- Không có stack overflow hoặc memory blowup trong giới hạn đã đặt.
- Deserializer không thực hiện side effect trước khi payload hợp lệ.
- Các input lặp/biên không tạo object graph sai hoặc bypass policy.

Fuzz test không thay thế test schema và business rule. Nó bổ sung khả năng khám phá các trường hợp parser/mapper ít gặp.

## 26. Xử lý lỗi mà không làm lộ dữ liệu

Lỗi parse/mapping thường chứa thông tin về field, token hoặc input fragment. Không trả nguyên exception message cho client nếu nó có thể chứa secret hoặc dữ liệu nhạy cảm.

Có thể chuẩn hóa:

```json
{
  "code": "INVALID_REQUEST_BODY",
  "message": "Request body is invalid",
  "correlationId": "req-7f3a"
}
```

Log nội bộ có thể lưu exception class, field path, correlation ID và kích thước payload theo policy. Nếu cần payload để điều tra, lưu vào vùng quarantine có quyền truy cập và retention rõ ràng, sau khi redact dữ liệu nhạy cảm.

Không log raw body trong mọi trường hợp chỉ vì `JsonProcessingException` có message hữu ích. Không gửi stack trace, SQL, đường dẫn file hoặc classpath ra public response.

## 27. Checklist trước khi nhận JSON từ nguồn bên ngoài

- [ ] Request body có giới hạn byte ở gateway/server.
- [ ] Parser có giới hạn nesting depth, string length và number length phù hợp.
- [ ] Duplicate key được xử lý theo một policy nhất quán.
- [ ] API một document kiểm tra trailing token.
- [ ] DTO chỉ chứa field caller được phép gửi.
- [ ] Field server-managed không bị mass assignment.
- [ ] Coercion được kiểm soát cho các kiểu quan trọng.
- [ ] Unknown-property policy được chọn theo endpoint/schema version.
- [ ] Polymorphic typing dùng logical ID và subtype allowlist tường minh.
- [ ] Default typing rộng và class name do client điều khiển không được bật cho input không tin cậy.
- [ ] Custom deserializer không gọi network, database hoặc thực hiện side effect.
- [ ] Bean Validation và domain authorization được chạy sau binding.
- [ ] Array/record count và batch size có giới hạn.
- [ ] Log không chứa secret hoặc raw payload không kiểm soát.
- [ ] Dependency Jackson được quản lý và cập nhật theo advisory.
- [ ] Test có payload malformed, sai kiểu, type ID lạ, payload lớn và field bị cấm.

## 28. Quy trình xử lý JSON an toàn

Một pipeline thực tế có thể được tổ chức như sau:

```text
Nguồn bên ngoài
      |
      v
Ingress controls
- xác thực nguồn / authn
- giới hạn body bytes
- timeout / rate limit
      |
      v
Jackson Core
- strict duplicate detection
- nesting/string/number constraints
- một document hoặc sequence rõ ràng
      |
      v
Jackson Databind
- DTO cụ thể
- strict type/coercion policy
- subtype allowlist
- không class name tùy ý
      |
      v
Bean Validation
- required / size / range
- nested / cross-field constraints
      |
      v
Application / Domain
- authorization
- resolve ID và trạng thái
- business invariants
- transaction / atomic update
      |
      v
Output / downstream
- DTO output allowlist
- redact log
- encode theo context đích
```

Mỗi bước cần có giới hạn và lỗi riêng. Nếu parse hoặc binding thất bại, không tiếp tục gọi use case. Nếu Bean Validation thất bại, không thực hiện side effect. Nếu business rule thất bại, trả lỗi theo contract và giữ transaction nhất quán.

## 29. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
| Cho rằng JSON hợp lệ là an toàn | Bỏ qua quyền, schema và giới hạn tài nguyên | Kiểm tra theo từng lớp |
| Bật default typing rộng cho request | Cho payload ảnh hưởng class runtime được tạo | Dùng DTO và subtype allowlist `Id.NAME` |
| Dùng `Id.CLASS` với JSON công khai | Gắn payload với tên class và mở rộng bề mặt polymorphic | Dùng type ID logic do server định nghĩa |
| Deserialize thẳng vào entity | Mass assignment vào field server-managed | Request DTO allowlist |
| Tắt unknown properties toàn cục | Che typo và thay đổi schema ngoài ý muốn | Reader/DTO riêng theo contract |
| Dựa vào `@NotNull` để giới hạn payload | Constraint chạy sau khi object được tạo | Giới hạn body/parser trước binding |
| Chỉ dùng `@Size` cho array khổng lồ | Collection đã được tạo trước khi validate | Streaming hoặc giới hạn trước khi materialize |
| Gọi database trong deserializer | N+1 query, side effect và binding khó kiểm soát | Resolve ở service theo batch |
| Log toàn bộ JSON | Lộ secret, PII và log injection | Allowlist/redact/sanitize |
| Dùng URL/path từ payload trực tiếp | SSRF hoặc path traversal | Validate ở tầng hành động với allowlist và giới hạn |
| Tắt lỗi subtype không hợp lệ | Type lạ bị bỏ qua hoặc thành null ngoài dự kiến | Giữ fail-fast và kiểm thử unknown type |

## 30. Ghi nhớ

Dữ liệu JSON bên ngoài phải được xem là đầu vào không tin cậy, kể cả khi đến từ mạng nội bộ hoặc đối tác đã xác thực. Jackson chỉ parse và bind theo cấu hình; ứng dụng vẫn phải kiểm soát kiểu runtime, field được phép, kích thước, độ sâu, coercion, quyền và quy tắc nghiệp vụ.

Ưu tiên DTO allowlist và type ID logic với subtype được đăng ký tường minh. Tránh default typing rộng và class name do client điều khiển. Giới hạn body ở ingress và token ở parser; bật các kiểm tra strict phù hợp như duplicate detection, trailing-token và unknown-property policy; không để custom deserializer thực hiện side effect; validate object và authorization ở application layer. Cuối cùng, kiểm thử cả payload bất thường và giới hạn tài nguyên, đồng thời không đưa secret hoặc raw payload không kiểm soát vào log.
