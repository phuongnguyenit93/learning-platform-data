# ObjectMapper configuration

Trong Spring Batch, khi đọc hoặc ghi JSON, ObjectMapper của Jackson quyết định cách chuyển đổi giữa JSON và Java object. Cấu hình mapper ảnh hưởng trực tiếp đến kiểu dữ liệu, ngày giờ, enum, null, tên field, unknown property, độ chính xác số và cách xử lý dữ liệu không hợp lệ.

Một Job có thể đọc JSON thành công trên máy developer nhưng thất bại ở production nếu hai môi trường dùng cấu hình mapper khác nhau. Ví dụ, một bên chấp nhận field không biết, bên kia từ chối; một bên parse timestamp theo timezone mặc định, bên kia dùng timezone khác; hoặc một bên ép chuỗi "123" thành số trong khi bên kia yêu cầu JSON number.

Trong batch processing, các khác biệt này còn ảnh hưởng tới restart. Nếu Job đã commit một số chunk rồi được restart bằng cấu hình ObjectMapper mới, cùng một input có thể được deserialize khác trước đó.

Cần thiết kế ObjectMapper như một phần của hợp đồng dữ liệu:

- Chọn module hỗ trợ kiểu Java cần dùng.
- Quy định naming, date/time, enum, number và null handling.
- Xác định chính sách unknown fields và type coercion.
- Dùng parser constraints và cấu hình an toàn cho input không tin cậy.
- Chia sẻ mapper đã cấu hình hoàn chỉnh, không thay đổi trong lúc Job chạy.
- Giữ cấu hình tương thích qua restart hoặc version hóa định dạng.

## 1. ObjectMapper làm gì?

ObjectMapper là thành phần trung tâm của Jackson Databind. Nó thực hiện hai hướng chuyển đổi:

- **Deserialization**: JSON bytes/text thành Java object.
- **Serialization**: Java object thành JSON bytes/text.

Ví dụ JSON:

~~~json
{
  "order_id": 1001,
  "customer_name": "Nguyễn An",
  "amount": 125.50
}
~~~

ObjectMapper có thể chuyển JSON thành object:

~~~java
public record OrderInput(
        Long orderId,
        String customerName,
        BigDecimal amount) {
}
~~~

Và chuyển object trở lại JSON. Các quy tắc mapping được quyết định bởi annotations, naming strategy, registered modules, serializer/deserializer và các feature được bật/tắt.

Trong Spring Batch, ObjectMapper thường được sử dụng bên trong JsonObjectReader hoặc JsonObjectMarshaller. Reader và writer của Spring Batch quản lý luồng item, checkpoint và resource; Jackson đảm nhận việc mapping nội dung JSON.

## 2. Tạo ObjectMapper dùng riêng cho batch

Một cách rõ ràng là tạo bean ObjectMapper riêng cho JSON batch:

~~~java
@Configuration
public class BatchJsonConfiguration {

    @Bean
    public ObjectMapper batchObjectMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .addModule(new Jdk8Module())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
                .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
                .build();
    }
}
~~~

Ví dụ dùng JsonMapper.builder() yêu cầu phiên bản Jackson hỗ trợ API builder tương ứng. Nếu dự án dùng phiên bản cũ hơn, có thể tạo ObjectMapper rồi đăng ký module và cấu hình feature trước khi sử dụng.

Tách batchObjectMapper khỏi mapper dùng cho REST API khi hai luồng có hợp đồng khác nhau. Một API có thể cần tương thích ngược và chấp nhận field lạ, trong khi file batch cần validation nghiêm ngặt để tránh âm thầm bỏ dữ liệu.

Nếu dùng Spring Boot, hãy kiểm tra mapper auto-configured và các customizer hiện có. Không tạo thêm một mapper tùy tiện rồi để reader/writer vô tình dùng mapper khác. Hãy inject bean có tên rõ ràng và dùng @Qualifier khi cần.

## 3. Cấu hình mapper trước khi sử dụng

ObjectMapper được thiết kế để dùng đồng thời sau khi đã cấu hình xong. Sau khi bắt đầu đọc/ghi, không nên thay đổi modules, mixins, serializers, deserializers hoặc features trên cùng mapper.

Một quy tắc tốt:

1. Tạo mapper.
2. Đăng ký module và custom mapping.
3. Cấu hình feature và parser factory.
4. Kiểm thử mapping.
5. Chia sẻ mapper đã hoàn tất cho các reader/writer.

Ví dụ không nên thay đổi mapper trong processor:

~~~java
public Order process(OrderInput input) {
    objectMapper.configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            false);
    return convert(input);
}
~~~

Nếu nhiều worker cùng dùng mapper, thay đổi runtime có thể tạo hành vi không nhất quán giữa các thread. Thay đổi cấu hình nên được thực hiện ở thời điểm khởi tạo ứng dụng hoặc tạo bean theo scope phù hợp trước khi Step chạy.

## 4. JavaTimeModule cho ngày và giờ

Jackson core không tự hiểu mọi kiểu ngày giờ của Java Time API theo cách ứng dụng mong muốn. Đăng ký JavaTimeModule để hỗ trợ các kiểu như:

- LocalDate.
- LocalTime.
- LocalDateTime.
- Instant.
- OffsetDateTime.
- ZonedDateTime.
- Duration và một số kiểu temporal khác.

Ví dụ:

~~~java
@Bean
public ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
}
~~~

Với cấu hình này, các kiểu ngày giờ thường được biểu diễn dưới dạng chuỗi ISO-8601 thay vì timestamp dạng số hoặc mảng, tùy kiểu dữ liệu và cấu hình cụ thể.

Ví dụ:

~~~json
{
  "business_date": "2026-11-15",
  "created_at": "2026-11-15T10:30:00Z"
}
~~~

LocalDate phù hợp với ngày nghiệp vụ không gắn timezone. Instant hoặc OffsetDateTime phù hợp với thời điểm cần biểu diễn nhất quán trên nhiều hệ thống. LocalDateTime không chứa timezone/offset; không nên tự suy ra múi giờ cho nó nếu hợp đồng dữ liệu không nói rõ.

## 5. Quy định timezone rõ ràng

Timezone có thể làm thay đổi thời điểm được diễn giải hoặc serialize. Một timestamp có offset Z không giống một LocalDateTime không có offset.

Ví dụ:

~~~java
Instant occurredAt = Instant.parse("2026-11-15T10:30:00Z");
OffsetDateTime businessTime =
        OffsetDateTime.parse("2026-11-15T17:30:00+07:00");
~~~

Cả hai biểu diễn cùng một thời điểm trong ví dụ, nhưng kiểu dữ liệu thể hiện ý nghĩa khác nhau.

Không dùng timezone mặc định của máy chủ để diễn giải một chuỗi ngày giờ không có offset nếu nghiệp vụ cần kết quả ổn định. Hãy xác định timezone trong hợp đồng, dùng Instant/OffsetDateTime hoặc cấu hình timezone rõ ràng và kiểm thử qua môi trường khác nhau.

Có thể đặt timezone serialization cho mapper:

~~~java
mapper.setTimeZone(TimeZone.getTimeZone("UTC"));
~~~

Cấu hình này không thay thế việc chọn đúng kiểu temporal. LocalDate không phải thời điểm và không nên bị chuyển đổi như timestamp.

## 6. Naming strategy: snake_case và camelCase

JSON từ hệ thống khác có thể dùng snake_case trong khi Java model dùng camelCase.

JSON:

~~~json
{
  "order_id": 1001,
  "customer_name": "Nguyễn An"
}
~~~

Java:

~~~java
public class OrderInput {
    private Long orderId;
    private String customerName;

    // getters/setters
}
~~~

Có thể cấu hình naming strategy:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
~~~

Khi đó Jackson ánh xạ order_id sang orderId và customer_name sang customerName.

Naming strategy toàn cục tác động tới tất cả model được mapper xử lý. Nếu chỉ một DTO tuân theo snake_case, có thể dùng @JsonNaming trên class:

~~~java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class OrderInput {
    private Long orderId;
    private String customerName;
}
~~~

Dùng @JsonProperty khi một field có tên đặc biệt hoặc cần giữ nguyên tên JSON theo hợp đồng. Tránh đổi naming strategy toàn cục chỉ để sửa một DTO vì có thể làm các file khác bị mapping sai.

## 7. Unknown properties: strict hay tolerant?

Khi JSON chứa field không có trong Java model, Jackson có thể từ chối hoặc bỏ qua field đó tùy cấu hình.

Ví dụ input:

~~~json
{
  "order_id": 1001,
  "customer_name": "Nguyễn An",
  "new_partner_field": "value"
}
~~~

Nếu model chưa có new_partner_field và mapper bật FAIL_ON_UNKNOWN_PROPERTIES, deserialization thất bại.

Cấu hình strict là mặc định hữu ích cho batch file có schema cố định:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Nếu cần tương thích với producer thường bổ sung field, có thể bỏ qua unknown property:

~~~java
mapper.disable(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Hoặc chỉ cho phép một DTO cụ thể bỏ qua field lạ:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerOrderInput {
    // ...
}
~~~

Chính sách tolerant giúp tiếp nhận thay đổi additive, nhưng có thể che giấu lỗi đánh máy trong tên field. Ví dụ producer gửi order_amout thay vì order_amount; nếu unknown fields bị bỏ qua, amount có thể trở thành null và lỗi chỉ xuất hiện ở bước sau.

Trong batch, hãy quyết định theo hợp đồng: strict để phát hiện schema drift; tolerant khi producer có quyền thêm field không ảnh hưởng consumer. Dù chọn cách nào, vẫn cần validation cho field bắt buộc.

## 8. Phân biệt field thiếu và field null

Hai JSON sau không hoàn toàn giống nhau:

~~~json
{
  "order_id": 1001
}
~~~

~~~json
{
  "order_id": 1001,
  "customer_name": null
}
~~~

Ở trường hợp đầu, property không được cung cấp. Ở trường hợp thứ hai, property hiện diện với giá trị JSON null.

Với field tham chiếu thông thường, cả hai có thể dẫn tới Java null nếu không có cấu hình hoặc setter đặc biệt. Nếu nghiệp vụ cần phân biệt, có thể dùng constructor/creator logic, custom deserializer, wrapper hoặc kiểm tra cây JSON trước khi binding.

Jackson hỗ trợ Nulls policy qua @JsonSetter:

~~~java
public class OrderInput {

    private String customerName;

    @JsonSetter(nulls = Nulls.FAIL)
    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }
}
~~~

Nulls.FAIL từ chối giá trị null tường minh. Các policy khác như SKIP hoặc AS_EMPTY có ý nghĩa khác nhau. Hãy kiểm tra phiên bản Jackson và kiểu property cụ thể.

Không mặc định thay mọi null thành chuỗi rỗng hoặc 0. Null có thể mang ý nghĩa "không biết", "không cung cấp", "xóa giá trị" hoặc "không áp dụng".

## 9. Primitive, wrapper và null

Java primitive như int, long, boolean không thể chứa null. Wrapper như Integer, Long, Boolean có thể biểu diễn trạng thái thiếu.

Ví dụ:

~~~java
public class OrderInput {
    private int quantity;
    private Integer discountPercent;
}
~~~

Nếu JSON có quantity: null, Jackson có thể dùng giá trị mặc định primitive hoặc từ chối tùy feature. Để tránh null bị chuyển thành 0 âm thầm, bật:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
~~~

Với field có thể vắng mặt, dùng wrapper rồi validate:

~~~java
if (input.getQuantity() == null || input.getQuantity() <= 0) {
    throw new InvalidOrderException("quantity must be positive");
}
~~~

Không dùng 0 để đại diện cho missing nếu 0 là giá trị nghiệp vụ hợp lệ. Hãy giữ trạng thái thiếu cho tới khi validation hoặc business logic quyết định cách xử lý.

## 10. Number và BigDecimal

JSON có kiểu number, nhưng Java có nhiều kiểu số với độ chính xác và miền giá trị khác nhau.

Với tiền tệ hoặc giá trị cần độ chính xác thập phân, ưu tiên BigDecimal thay cho double:

~~~java
public record PaymentInput(
        String paymentId,
        BigDecimal amount) {
}
~~~

Ví dụ JSON:

~~~json
{
  "payment_id": "P-100",
  "amount": 1250.75
}
~~~

BigDecimal giữ biểu diễn thập phân chính xác hơn cho phép tính tài chính so với binary floating point double. Tuy nhiên, cần xác định scale, rounding mode và validation theo nghiệp vụ.

Nếu producer gửi amount dưới dạng chuỗi, ví dụ "1250.75", Jackson có thể chuyển đổi tùy coercion policy. Không nên dựa vào coercion ngầm nếu hợp đồng yêu cầu JSON number. Hãy kiểm thử đúng kiểu token đầu vào.

Có thể cấu hình USE_BIG_DECIMAL_FOR_FLOATS khi map JSON vào Object, Number hoặc Map mà không có kiểu field cụ thể. Với DTO có field BigDecimal, khai báo kiểu field rõ ràng thường đủ.

## 11. Ép kiểu và coercion

Jackson có thể hỗ trợ một số chuyển đổi như chuỗi số sang integer, number sang string hoặc empty string thành null tùy phiên bản và cấu hình coercion.

Trong batch, coercion quá rộng có thể che giấu lỗi producer. Ví dụ:

~~~json
{
  "quantity": "12"
}
~~~

Nếu hợp đồng yêu cầu quantity là JSON integer, chuỗi "12" nên được coi là sai schema thay vì tự động chuyển đổi.

Các lựa chọn:

- Dùng kiểu DTO cụ thể.
- Cấu hình CoercionConfig phù hợp với phiên bản Jackson.
- Viết custom deserializer cho field có quy tắc đặc biệt.
- Validate token type trước khi chấp nhận dữ liệu.
- Tạo test cho chuỗi rỗng, chuỗi số, số thập phân và overflow.

Không áp dụng một coercion policy chung cho mọi loại dữ liệu nếu mỗi field có quy tắc khác nhau.

## 12. Enum và giá trị không được nhận diện

Jackson mặc định thường ánh xạ enum theo tên hằng Java:

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
  "status": "PAID"
}
~~~

Nếu producer gửi "IN_PROGRESS" nhưng Java enum chưa có giá trị đó, deserialization có thể thất bại. Đây là một dạng schema drift cần chính sách rõ ràng.

Có thể định nghĩa giá trị JSON bằng @JsonProperty:

~~~java
public enum OrderStatus {
    @JsonProperty("new")
    NEW,

    @JsonProperty("paid")
    PAID,

    @JsonProperty("cancelled")
    CANCELLED
}
~~~

Không bật chấp nhận số làm enum index nếu hợp đồng yêu cầu chuỗi:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS);
~~~

Không map unknown enum thành một trạng thái mặc định tùy tiện nếu điều đó làm thay đổi ý nghĩa nghiệp vụ. Nếu cần UNKNOWN, hãy thiết kế enum và custom mapping có chủ đích, đồng thời ghi nhận giá trị nguồn.

## 13. Optional và các kiểu JDK khác

Để hỗ trợ Optional, một số kiểu collection và kiểu JDK khác, có thể đăng ký Jdk8Module:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new Jdk8Module())
        .build();
~~~

Ví dụ:

~~~java
public record CustomerInput(
        Long id,
        Optional<String> phoneNumber) {
}
~~~

Optional có thể hữu ích khi field thực sự có tính tùy chọn. Tuy nhiên, Optional không phải lúc nào cũng giữ được khác biệt giữa property bị thiếu và property có giá trị null. Nếu hai trạng thái có ý nghĩa khác nhau, cần mapping chuyên biệt.

Không dùng Optional như cách thay thế validation. Sau khi deserialize, vẫn cần kiểm tra các field bắt buộc và quy tắc nghiệp vụ.

## 14. Constructor, record và ParameterNamesModule

Jackson có thể deserialize Java record và constructor-based model tùy phiên bản. Với class immutable dùng constructor, cần đảm bảo Jackson biết tên và kiểu tham số.

Ví dụ record:

~~~java
public record OrderInput(
        Long orderId,
        String customerName,
        BigDecimal amount) {
}
~~~

Record được hỗ trợ tốt trong các phiên bản Jackson hiện đại. Với class constructor thông thường, có thể dùng @JsonCreator và @JsonProperty để khai báo rõ:

~~~java
public class CustomerInput {

    private final Long id;
    private final String name;

    @JsonCreator
    public CustomerInput(
            @JsonProperty("id") Long id,
            @JsonProperty("name") String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

ParameterNamesModule có thể giúp Jackson dùng tên tham số constructor được biên dịch với metadata phù hợp. Dù vậy, annotation tường minh thường dễ đọc và ổn định hơn với DTO tích hợp.

Hãy kiểm thử bằng đúng compiler flags, Jackson version và model thực tế của dự án.

## 15. Annotation và MixIn

Có thể cấu hình mapping trực tiếp trên model:

- @JsonProperty: tên property trong JSON.
- @JsonIgnore: bỏ qua property.
- @JsonFormat: định dạng ngày giờ hoặc giá trị cụ thể.
- @JsonInclude: điều khiển field nào được serialize.
- @JsonAlias: chấp nhận nhiều tên khi deserialize.
- @JsonCreator: chọn constructor/factory để tạo object.
- @JsonDeserialize: chọn custom deserializer.
- @JsonSerialize: chọn custom serializer.

Ví dụ alias cho tên cũ và mới:

~~~java
public class OrderInput {

    @JsonAlias({"orderId", "order_id"})
    private Long id;
}
~~~

Nếu không thể sửa model của thư viện bên ngoài, dùng Jackson MixIn để bổ sung annotation mà không sửa class gốc.

Không tạo quá nhiều alias lâu dài mà không có kế hoạch loại bỏ. Alias có thể giúp migration schema, nhưng nếu giữ vô hạn sẽ làm hợp đồng dữ liệu khó hiểu và khó phát hiện producer cũ.

## 16. Custom serializer và deserializer

Khi field có format đặc biệt, có thể viết custom serializer/deserializer.

Ví dụ producer gửi ngày theo format dd/MM/yyyy:

~~~java
public class LegacyDateDeserializer
        extends JsonDeserializer<LocalDate> {

    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/yyyy");

    @Override
    public LocalDate deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        String value = parser.getValueAsString();

        try {
            return LocalDate.parse(value, FORMAT);
        } catch (DateTimeParseException exception) {
            throw InvalidFormatException.from(
                    parser,
                    "Expected date in dd/MM/yyyy format",
                    value,
                    LocalDate.class);
        }
    }
}
~~~

Gắn vào field:

~~~java
public class LegacyOrderInput {

    @JsonDeserialize(using = LegacyDateDeserializer.class)
    private LocalDate orderDate;
}
~~~

Custom deserializer nên:

- Chỉ nhận format được quy định.
- Báo lỗi có thông tin field và giá trị phù hợp.
- Không dùng mutable shared state.
- Không nuốt exception rồi trả default không rõ nghĩa.
- Có unit test cho valid, invalid, blank và boundary values.

Trong batch, lỗi deserialization thường xảy ra trước processor. Nếu cần skip theo record, cần biết reader có thể tiếp tục sau lỗi đó hay không. Một JSON array bị sai cú pháp có thể làm parser mất đồng bộ; không phải mọi parse exception đều an toàn để skip.

## 17. Date format theo từng field

Có thể dùng @JsonFormat khi chỉ một số field cần format riêng:

~~~java
public class PartnerOrderInput {

    @JsonFormat(pattern = "dd/MM/yyyy")
    private LocalDate businessDate;

    @JsonFormat(
            pattern = "yyyy-MM-dd'T'HH:mm:ssXXX",
            timezone = "UTC")
    private OffsetDateTime createdAt;
}
~~~

Format pattern phải phù hợp kiểu dữ liệu. Với OffsetDateTime, pattern cần giữ offset nếu hợp đồng cần phân biệt timezone.

Không dùng pattern ngày giờ mơ hồ như yyyy-MM-dd HH:mm:ss cho một thời điểm toàn cầu nếu không biết timezone. Nếu nguồn không gửi offset, hãy xác định timezone nghiệp vụ và chuyển đổi có chủ đích.

## 18. Serialization: null, empty và property inclusion

Khi ghi JSON, ObjectMapper quyết định property nào xuất hiện.

Ví dụ bỏ các field null:

~~~java
mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
~~~

Hoặc áp dụng trên class:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class OrderResult {
    // ...
}
~~~

Các policy thường gặp:

- ALWAYS: luôn ghi property.
- NON_NULL: bỏ property có giá trị null.
- NON_EMPTY: bỏ null và các giá trị empty theo Jackson.
- NON_DEFAULT: bỏ giá trị mặc định theo quy tắc tương ứng.

Không bỏ null chỉ để file nhỏ hơn nếu downstream phân biệt "field không tồn tại" với "field tồn tại nhưng null". Với API patch hoặc đồng bộ dữ liệu, khác biệt này có thể có ý nghĩa nghiệp vụ.

Hãy kiểm tra output JSON byte/text thực tế và contract của consumer.

## 19. Property order và output có tính tái lập

JSON object về mặt chuẩn không yêu cầu thứ tự property. Tuy nhiên, một số hệ thống hoặc test snapshot có thể yêu cầu output ổn định.

Có thể bật sắp xếp property:

~~~java
mapper.enable(
        MapperFeature.SORT_PROPERTIES_ALPHABETICALLY);

mapper.enable(
        SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
~~~

Chỉ bật nếu cần output deterministic. Nó có thể tăng chi phí và không thay thế canonical JSON nếu cần ký số hoặc tính hash theo chuẩn.

Nếu output được ký số, dùng một quy tắc canonicalization đã được thống nhất, không tự giả định thứ tự property là đủ để tạo chữ ký ổn định.

## 20. Polymorphic typing và an toàn dữ liệu

Jackson hỗ trợ polymorphic deserialization để tạo subclass theo type metadata. Ví dụ JSON chứa trường type để xác định kiểu cụ thể.

Tính năng này cần được kiểm soát chặt. Không bật default typing rộng cho JSON đến từ nguồn không tin cậy vì nó có thể cho phép khởi tạo kiểu không mong muốn.

Nếu thật sự cần polymorphism:

- Dùng một hierarchy type cụ thể.
- Whitelist các subtype được phép.
- Dùng @JsonTypeInfo và @JsonSubTypes có chủ đích.
- Nếu dùng PolymorphicTypeValidator, giới hạn package/type được chấp nhận.
- Kiểm thử payload có type ID lạ.

Không dùng type metadata từ producer để cho phép Jackson tạo bất kỳ class nào trên classpath.

## 21. Parser constraints và JSON không tin cậy

JSON có thể chứa chuỗi rất dài, cấu trúc lồng sâu hoặc số lượng token lớn. Streaming parser không tự động bảo vệ khỏi mọi input gây tiêu thụ tài nguyên quá mức.

Jackson có StreamReadConstraints trong các phiên bản hỗ trợ, cho phép giới hạn một số đặc điểm như nesting depth, string length và number length.

Ví dụ khái niệm với Jackson version hỗ trợ:

~~~java
StreamReadConstraints constraints =
        StreamReadConstraints.builder()
                .maxNestingDepth(100)
                .maxStringLength(1_000_000)
                .maxNumberLength(1_000)
                .build();

JsonFactory jsonFactory = JsonFactory.builder()
        .streamReadConstraints(constraints)
        .build();

ObjectMapper mapper = JsonMapper.builder(jsonFactory)
        .build();
~~~

Tên API và giới hạn có thể khác theo phiên bản Jackson. Hãy chọn giới hạn dựa trên dữ liệu hợp lệ thực tế, không đặt quá thấp làm từ chối record hợp lệ.

Có thể bật strict duplicate detection để từ chối object chứa cùng một key nhiều lần nếu hợp đồng yêu cầu:

~~~java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();
~~~

JSON object có duplicate key có thể được các parser xử lý khác nhau. Từ chối duplicate giúp tránh dữ liệu mơ hồ giữa producer và consumer.

## 22. Streaming JSON trong Spring Batch

Với file JSON dạng array:

~~~json
[
  {"order_id": 1, "amount": 10.00},
  {"order_id": 2, "amount": 20.00},
  {"order_id": 3, "amount": 30.00}
]
~~~

Không nên đọc toàn bộ thành List<OrderInput> nếu file rất lớn. Spring Batch cung cấp JsonItemReader để đọc từng object từ resource, thường kết hợp Jackson2JsonObjectReader.

Ví dụ:

~~~java
@Bean
@StepScope
public JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") Resource resource,
        @Qualifier("batchObjectMapper") ObjectMapper mapper) {

    Jackson2JsonObjectReader<OrderInput> objectReader =
            new Jackson2JsonObjectReader<>(OrderInput.class);

    objectReader.setMapper(mapper);

    return new JsonItemReaderBuilder<OrderInput>()
            .name("orderJsonReader")
            .resource(resource)
            .jsonObjectReader(objectReader)
            .saveState(true)
            .strict(true)
            .build();
}
~~~

JsonItemReader đọc tuần tự từng object trong JSON array, thay vì yêu cầu ứng dụng giữ toàn bộ danh sách trong memory. ObjectMapper được inject vào Jackson2JsonObjectReader để dùng đúng policy mapping của batch.

Tên class và method cần khớp phiên bản Spring Batch đang dùng. Các phiên bản Spring Batch khác nhau có thể thay đổi API hoặc hỗ trợ thư viện JSON khác; hãy kiểm tra dependency và documentation tương ứng.

## 23. JSON array và NDJSON là hai format khác nhau

JsonItemReader thường được dùng cho JSON array chứa nhiều object. Một định dạng phổ biến khác là NDJSON/JSON Lines, trong đó mỗi dòng là một JSON document độc lập:

~~~text
{"order_id":1,"amount":10.00}
{"order_id":2,"amount":20.00}
{"order_id":3,"amount":30.00}
~~~

NDJSON không có dấu ngoặc vuông bao quanh toàn bộ file. Không thể giả định JsonItemReader đọc NDJSON như một JSON array.

Với NDJSON, có thể dùng FlatFileItemReader để đọc từng dòng rồi dùng ObjectMapper.readValue() trong processor, hoặc xây dựng custom ItemReader streaming phù hợp. Cần xử lý blank line, newline, encoding và parse exception theo từng record.

Ví dụ processor:

~~~java
@Bean
public ItemProcessor<String, OrderInput> ndjsonProcessor(
        @Qualifier("batchObjectMapper") ObjectMapper mapper) {

    return line -> mapper.readValue(line, OrderInput.class);
}
~~~

Nếu JSON mỗi dòng có thể rất dài hoặc có newline trong string, định dạng NDJSON yêu cầu JSON document của mỗi record nằm trên một dòng vật lý. Không đưa multiline JSON vào NDJSON nếu không có quy tắc escaping riêng.

## 24. Đưa ObjectMapper vào JsonFileItemWriter

Spring Batch cung cấp JsonFileItemWriter và JsonObjectMarshaller để ghi item thành JSON. Có thể dùng Jackson2JsonObjectMarshaller với ObjectMapper đã cấu hình nếu phiên bản thư viện hỗ trợ API đó.

Ví dụ:

~~~java
@Bean
@StepScope
public JsonFileItemWriter<OrderResult> orderJsonWriter(
        @Value("#{jobParameters['outputFile']}") Resource output,
        @Qualifier("batchObjectMapper") ObjectMapper mapper) {

    Jackson2JsonObjectMarshaller<OrderResult> marshaller =
            new Jackson2JsonObjectMarshaller<>();

    marshaller.setObjectMapper(mapper);

    return new JsonFileItemWriterBuilder<OrderResult>()
            .name("orderJsonWriter")
            .resource(output)
            .jsonObjectMarshaller(marshaller)
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
~~~

Tên setter/constructor của Jackson2JsonObjectMarshaller có thể khác theo phiên bản Spring Batch. Hãy dùng đúng API được cung cấp bởi dependency đang cài đặt.

Nếu dùng custom ItemWriter, có thể gọi ObjectMapper.writeValueAsBytes() hoặc writeValue() theo từng item, nhưng cần quản lý dấu phẩy, array boundary, newline, encoding và restart. Tránh tự nối JSON bằng chuỗi vì dễ tạo output không hợp lệ khi có quote, escape hoặc ký tự đặc biệt.

## 25. Không đọc toàn bộ JSON lớn thành List

Cách đơn giản sau không phù hợp với file lớn:

~~~java
List<OrderInput> orders =
        mapper.readValue(
                inputFile,
                new TypeReference<List<OrderInput>>() {});
~~~

Nó materialize toàn bộ danh sách trong memory trước khi xử lý. Nếu file có hàng triệu record, memory tăng theo tổng số item.

Thay vào đó, dùng JsonItemReader hoặc Jackson streaming API để lấy từng object. Spring Batch sau đó gom object theo chunk size, xử lý và ghi theo transaction.

Memory lúc này phụ thuộc vào parser buffer, object hiện tại, chunk và working set của processor/writer, không phải toàn bộ danh sách.

## 26. ObjectMapper và thread safety

ObjectMapper có thể được chia sẻ giữa nhiều thread khi đã cấu hình xong. Không nên mutate mapper trong lúc các thread đang serialize/deserialize.

Cần chú ý cả custom serializers/deserializers:

- Không giữ mutable state theo từng item trong serializer singleton.
- Không lưu JsonParser hoặc JsonGenerator vào field dùng chung.
- Không dùng SimpleDateFormat mutable làm shared state nếu không thread-safe.
- Dùng DateTimeFormatter immutable.
- Nếu cần cache theo item, quản lý cache riêng theo execution và có giới hạn.

Trong multi-threaded Step hoặc partitioning, nhiều worker có thể dùng cùng ObjectMapper bean. Đây là lựa chọn bình thường nếu mapper immutable sau cấu hình và custom components thread-safe.

Reader và JsonObjectReader thường có state riêng theo resource/StepExecution; không chia sẻ cùng một reader instance giữa nhiều worker chỉ vì ObjectMapper dùng chung được.

## 27. ObjectMapper và Spring Boot

Spring Boot thường auto-configure ObjectMapper dựa trên Jackson modules, application properties và customizer. Nếu ứng dụng đã dùng mapper mặc định cho REST, có thể tái sử dụng khi hợp đồng JSON giống nhau.

Tuy nhiên, batch input/output thường có yêu cầu riêng:

- Input file có thể cần strict unknown-property handling.
- REST API có thể cần tolerant behavior để tương thích ngược.
- Batch cần date/time format cố định.
- Output batch có thể cần deterministic serialization.
- File đối tác có thể dùng naming strategy khác API.

Có thể tạo bean riêng:

~~~java
@Bean("batchObjectMapper")
public ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

Inject bằng @Qualifier:

~~~java
@Qualifier("batchObjectMapper")
ObjectMapper mapper
~~~

Nếu muốn dùng mapper auto-configured của Boot, hãy inject mapper đó và kiểm tra toàn bộ customizer/module đang tác động. Không giả định mapper mặc định giống nhau giữa mọi profile hoặc phiên bản Boot.

## 28. Validation sau khi deserialize

ObjectMapper kiểm tra cấu trúc và chuyển đổi kiểu, nhưng không thay thế validation nghiệp vụ.

Ví dụ JSON có thể deserialize thành công:

~~~json
{
  "order_id": 1001,
  "quantity": -5,
  "amount": -10.00
}
~~~

Nhưng quantity và amount có thể vi phạm quy tắc nghiệp vụ.

Có thể dùng Bean Validation:

~~~java
public class OrderInput {

    @NotNull
    private Long orderId;

    @Positive
    private Integer quantity;

    @DecimalMin("0.00")
    private BigDecimal amount;
}
~~~

Sau khi reader tạo object, processor có thể gọi Validator và ném exception nghiệp vụ nếu dữ liệu không hợp lệ.

Phân biệt:

- JSON syntax error: không parse được tài liệu.
- Binding error: token không map được sang kiểu Java.
- Bean validation error: object tạo được nhưng vi phạm constraint.
- Business validation error: cần kiểm tra logic nghiệp vụ sâu hơn.

Từng loại có thể cần chính sách retry/skip khác nhau. Một lỗi cú pháp trong JSON array có thể làm parser không thể tiếp tục an toàn; không nên skip mọi JsonParseException rồi giả định các record sau vẫn đọc được.

## 29. Error handling trong JsonItemReader

Khi JSON fragment không hợp lệ, reader có thể ném exception từ Jackson hoặc được Spring Batch bọc trong exception đọc item. Loại exception thực tế phụ thuộc reader và phiên bản.

Hãy kiểm thử và phân loại:

- JSON document malformed.
- Một object thiếu property bắt buộc.
- Giá trị không chuyển được sang kiểu Java.
- Unknown property.
- Invalid date/time.
- Enum không hợp lệ.
- File bị truncate.

Nếu file là một JSON array, lỗi cú pháp có thể phá vỡ khả năng xác định dấu phẩy và ranh giới object tiếp theo. Việc skip ở cấp item không phải lúc nào cũng an toàn.

Nếu cần cô lập record lỗi, NDJSON có thể thuận tiện hơn vì mỗi dòng là một document độc lập. Khi đó reader có thể ghi nhận dòng lỗi và tiếp tục với dòng sau nếu chính sách cho phép.

## 30. Restart và ObjectMapper configuration

JsonItemReader có thể lưu state để hỗ trợ restart. Reader cần tên ổn định và saveState phù hợp. Resource input cũng cần giữ nguyên nội dung giữa lần chạy và restart.

Ngoài checkpoint, ObjectMapper config phải tương thích:

- Property naming strategy không đổi.
- Date/time format không đổi.
- Enum mapping không đổi.
- Null và unknown-property policy không đổi ngoài ý muốn.
- Custom deserializer không đổi semantics.
- Input file giữ nguyên checksum/version.

Ví dụ lần chạy đầu chấp nhận order_id theo snake_case nhưng lần restart đổi sang naming strategy khác. Cùng một record có thể được deserialize khác hoặc thiếu field.

Nếu thay đổi schema hoặc mapper config là chủ đích, hãy version hóa hợp đồng, lưu format version trong JobParameters hoặc metadata và bảo đảm restart của JobInstance cũ dùng đúng mapping tương thích.

Không lưu cả ObjectMapper vào ExecutionContext. Chỉ lưu metadata nhỏ như schema version, input checksum hoặc format identifier; ObjectMapper là cấu hình ứng dụng được tạo từ code/configuration.

## 31. Reader name và saveState

Ví dụ JsonItemReader cần tên ổn định:

~~~java
return new JsonItemReaderBuilder<OrderInput>()
        .name("orderJsonReader")
        .resource(resource)
        .jsonObjectReader(objectReader)
        .saveState(true)
        .build();
~~~

Tên reader được dùng để lưu state trong Step ExecutionContext. Đổi tên reader khi một JobInstance cũ còn cần restart có thể làm checkpoint không được tìm thấy theo key cũ.

saveState(true) cho phép reader lưu vị trí đọc. Nếu tắt saveState, restart có thể bắt đầu đọc lại từ đầu. Khi đó writer cần idempotent hoặc ứng dụng phải có cơ chế chống xử lý trùng.

Input file cần bất biến. Nếu file được ghi đè bằng JSON mới nhưng vẫn giữ đường dẫn, checkpoint cũ có thể không còn trỏ tới cùng item.

## 32. Schema evolution và strictness

Schema JSON có thể thay đổi theo thời gian. Ví dụ producer thêm một field mới:

~~~json
{
  "order_id": 1001,
  "amount": 125.50,
  "source_channel": "MOBILE"
}
~~~

Nếu consumer cũ strict unknown properties, file mới sẽ bị từ chối. Nếu consumer tolerant, field mới có thể bị bỏ qua.

Để quản lý schema evolution:

- Version hóa schema hoặc file format.
- Xác định field nào bắt buộc, field nào optional.
- Quy định cách xử lý field mới và field bị loại bỏ.
- Dùng @JsonAlias cho migration có thời hạn.
- Kiểm tra type change và enum expansion.
- Lưu schema version cùng metadata Job.
- Duy trì fixture từ các phiên bản producer đang được hỗ trợ.

Không để unknown-property policy là một quyết định vô tình do default của Jackson. Hãy chọn strict hoặc tolerant theo hợp đồng và test.

## 33. Kiểm thử ObjectMapper riêng

Trước khi gắn mapper vào Job, kiểm thử mapping trực tiếp:

~~~java
@Test
void mapsSnakeCaseAndJavaTime() throws Exception {
    String json = """
            {
              "order_id": 1001,
              "business_date": "2026-11-15",
              "amount": 125.50
            }
            """;

    OrderInput input =
            batchObjectMapper.readValue(json, OrderInput.class);

    assertEquals(1001L, input.orderId());
    assertEquals(
            LocalDate.of(2026, 11, 15),
            input.businessDate());
    assertEquals(
            new BigDecimal("125.50"),
            input.amount());
}
~~~

Các test nên bao phủ:

- Naming strategy và @JsonProperty.
- JavaTimeModule và timezone.
- BigDecimal precision.
- Enum valid/invalid.
- Missing field và explicit null.
- Unknown property.
- Empty/blank string và type coercion.
- Custom serializer/deserializer.
- Duplicate JSON keys nếu policy bật.
- Nesting/string constraints.

Unit test mapper không thay thế integration test reader/writer. Nó chỉ xác nhận policy mapping ở cấp Jackson.

## 34. Kiểm thử JsonItemReader trong Step

Dùng một file JSON array nhỏ làm fixture và chạy reader qua lifecycle:

~~~java
@Test
void readsJsonArrayAsIndividualItems() throws Exception {
    ExecutionContext context = new ExecutionContext();

    reader.open(context);

    OrderInput first = reader.read();
    OrderInput second = reader.read();
    OrderInput third = reader.read();
    OrderInput end = reader.read();

    assertEquals(1L, first.orderId());
    assertEquals(2L, second.orderId());
    assertEquals(3L, third.orderId());
    assertNull(end);

    reader.close();
}
~~~

Trong test thực tế, cần cấu hình Resource và reader riêng cho test. Với restart, chạy một Step có nhiều chunk, cố ý làm chunk sau thất bại, rồi restart cùng JobInstance và xác nhận item đã commit không bị ghi trùng.

Cũng cần test file malformed, file rỗng, JSON array không đúng root structure và resource không tồn tại.

## 35. Kiểm thử output JSON

Với JsonFileItemWriter hoặc custom writer, xác nhận:

- JSON output parse lại được bằng mapper tương ứng.
- Property names đúng hợp đồng.
- Date/time có format và timezone đúng.
- Null fields được giữ hoặc bỏ theo policy.
- BigDecimal không bị đổi precision.
- Enum được serialize đúng chuỗi.
- Header/array boundary hoặc NDJSON line format đúng.
- Restart không tạo JSON bị lặp dấu phẩy, thiếu ngoặc hoặc ghi lặp item.

Nếu downstream cần output byte deterministic, so sánh byte hoặc canonicalized JSON theo hợp đồng. Không dựa vào thứ tự property nếu chưa quy định.

## 36. Những lỗi thường gặp

### Tạo nhiều ObjectMapper với cấu hình khác nhau

Reader, writer và service có thể serialize/deserialize khác nhau. Dùng bean rõ ràng và inject nhất quán.

### Cấu hình mapper sau khi Job đã bắt đầu

Nhiều worker có thể quan sát policy khác nhau. Cấu hình hoàn chỉnh trước khi chia sẻ mapper.

### Quên JavaTimeModule

LocalDate hoặc Instant không được map theo cách mong muốn. Đăng ký module và test format.

### Dùng timezone mặc định của máy

Cùng input có thể cho thời điểm khác giữa môi trường. Chọn kiểu temporal và timezone tường minh.

### Bỏ qua mọi unknown property

Field bị đánh máy sai có thể biến thành null mà không có lỗi. Chọn strict/tolerant theo schema và validate field bắt buộc.

### Dùng double cho tiền tệ

Sai số binary floating point có thể ảnh hưởng tính toán. Dùng BigDecimal với scale/rounding rõ ràng.

### Bật default typing rộng

Input có thể yêu cầu khởi tạo type không mong muốn. Dùng subtype whitelist và validator nếu cần polymorphism.

### Đọc toàn bộ JSON thành List

Memory tăng theo toàn bộ file. Dùng JsonItemReader hoặc streaming parser.

### Nhầm JSON array với NDJSON

Reader không nhận đúng cấu trúc. Chọn reader theo format thực tế.

### Skip mọi JsonParseException

JSON array malformed có thể làm parser mất đồng bộ. Chỉ skip lỗi record khi có ranh giới record đáng tin cậy.

### Đổi mapper config giữa restart

Cùng checkpoint có thể tạo object khác. Giữ config tương thích hoặc version hóa format.

### Chia sẻ custom deserializer có mutable state

Multi-threaded Step có thể có race condition. Giữ serializer/deserializer stateless hoặc đồng bộ đúng cách.

## 37. Quy trình cấu hình ObjectMapper cho Spring Batch

Khi xây dựng Job đọc/ghi JSON, hãy xác định:

1. JSON là array, NDJSON hay một document duy nhất?
2. Model Java và schema JSON có field nào bắt buộc/tùy chọn?
3. Naming strategy có phải snake_case hoặc mapping riêng không?
4. Có kiểu Java Time, Optional hoặc custom type nào cần module?
5. Date/time cần timezone và format nào?
6. Number nào cần BigDecimal và precision/scale ra sao?
7. Enum và giá trị không biết được xử lý thế nào?
8. Unknown properties được từ chối hay bỏ qua?
9. Missing property và explicit null có khác nhau không?
10. Coercion từ string/number có được phép không?
11. Parser có giới hạn nesting, string và number length không?
12. Có cần duplicate key detection hoặc polymorphic typing không?
13. Reader/writer có dùng cùng mapper được cấu hình rõ ràng không?
14. JSON lớn có được đọc streaming theo item không?
15. Reader name, saveState và input checksum có ổn định qua restart không?
16. Integration test có kiểm tra mapping, chunk, restart và output format không?

ObjectMapper là một phần của hợp đồng JSON của Job. Hãy cấu hình module, naming, date/time, number, enum, null và unknown-property policy một cách tường minh; chia sẻ mapper đã hoàn tất; dùng JsonItemReader hoặc streaming parser cho file lớn; và giữ mapping tương thích qua restart. Khi mỗi record được deserialize theo cùng một quy tắc ở mọi môi trường, Spring Batch có thể xử lý dữ liệu JSON ổn định, dễ kiểm soát lỗi và dễ khôi phục.
