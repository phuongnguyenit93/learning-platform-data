# Thiết kế nhiều chính sách đọc ghi khi các tích hợp có hợp đồng khác nhau

Một ứng dụng Spring thường giao tiếp với nhiều hệ thống: API của đối tác A, webhook của đối tác B, service nội bộ, message broker và client mobile. Tất cả đều có thể trao đổi JSON, nhưng hợp đồng dữ liệu không giống nhau. Một đối tác dùng `snake_case`, đối tác khác dùng `camelCase`; một bên gửi ngày theo ISO-8601, bên khác dùng pattern riêng; một API từ chối field lạ trong khi API khác cần bỏ qua field mới để tương thích; một hệ thống cần serialize null, hệ thống khác yêu cầu bỏ null khỏi output.

Nếu dùng một `ObjectMapper` toàn cục rồi liên tục thay đổi naming strategy, date format, mix-in hoặc feature theo từng request, các tích hợp có thể ảnh hưởng lẫn nhau. `ObjectMapper` được thiết kế để cấu hình xong rồi tái sử dụng; thay đổi cấu hình sau khi mapper đã được dùng còn có thể gây lỗi khó dự đoán do serializer/deserializer cache và nhiều request chạy đồng thời.

Thiết kế tốt là xác định chính sách đọc/ghi theo **ranh giới hợp đồng tích hợp**. Có thể dùng một mapper riêng cho mỗi hợp đồng khi khác biệt nằm ở module, mix-in, naming, subtype hoặc nhiều cấu hình cùng lúc; dùng `ObjectReader` và `ObjectWriter` khi chỉ cần biến thể đọc/ghi cục bộ; cấu hình HTTP/message converter riêng khi Spring cần chọn đúng mapper ở ranh giới transport. Sau khi deserialize, chuyển DTO của đối tác sang model nội bộ ổn định để phần domain không phụ thuộc format của từng bên.

Bài học sử dụng Spring Framework 6 / Spring Boot 3 và Jackson 2.x trong ví dụ. Một số API HTTP client, Kafka và Jackson có thể khác giữa version; hãy đối chiếu Javadoc của dependency đang chạy.

## 1. Vì sao nhiều tích hợp cần nhiều chính sách?

Giả sử ứng dụng đặt hàng kết nối ba hệ thống:

| Tích hợp | Đặc điểm hợp đồng |
|---|---|
| Partner A | Field `order_id`, `customer_name`; ngày `dd/MM/uuuu`; bỏ qua field mới chưa biết |
| Partner B | Field `orderId`, `customerName`; ngày ISO; từ chối field không được khai báo |
| Internal API | Dùng DTO nội bộ, ISO date, strict typing và không chấp nhận coercion |

Cùng một khái niệm đơn hàng nhưng tên field và quy tắc binding khác nhau. Một JSON từ Partner A:

```json
{
  "order_id": "A-100",
  "customer_name": "An Nguyen",
  "created_date": "12/11/2026",
  "partner_note": "priority"
}
```

JSON từ Partner B:

```json
{
  "orderId": "B-200",
  "customerName": "An Nguyen",
  "createdDate": "2026-11-12"
}
```

Nếu dùng một mapper có `SNAKE_CASE`, Partner B có thể không được ánh xạ đúng. Nếu bật tolerant unknown property toàn cục để Partner A gửi thêm field, typo ở Internal API có thể bị bỏ qua. Nếu đặt date format toàn cục theo Partner A, các endpoint ISO có thể bị ảnh hưởng.

Đây không phải vấn đề riêng của Jackson. Nó là vấn đề ranh giới hợp đồng: mỗi tích hợp cần một chính sách rõ ràng về dữ liệu được nhận và dữ liệu được phát ra.

## 2. Những phần của Jackson có thể khác nhau theo tích hợp

Một chính sách đọc/ghi có thể bao gồm:

| Nhóm chính sách | Ví dụ |
|---|---|
| Property naming | `SNAKE_CASE`, `LOWER_CAMEL_CASE`, tên field tường minh bằng `@JsonProperty` |
| Date/time | ISO-8601, pattern riêng, timezone, precision |
| Unknown properties | Fail, ignore hoặc thu vào vùng extension được giới hạn |
| Coercion | Có nhận string number thành integer không; có nhận ordinal enum không |
| Null/inclusion | Ghi null, bỏ null, bỏ empty hay giữ nguyên |
| Access direction | `READ_ONLY`, `WRITE_ONLY`, field chỉ xuất hoặc chỉ nhận |
| Custom types | Money, partner code, enum wire value, date wrapper |
| Polymorphism | Type ID logic và subtype allowlist |
| Mix-in/annotations | Áp dụng metadata cho model không sửa được |
| Views/filters | Field được phép xuất cho từng representation |
| Security/resource limits | Trailing token, duplicate key, nesting/string/number limits |
| Data format | JSON, CBOR, Smile, XML, YAML hoặc format khác |

Không phải mọi khác biệt đều cần một `ObjectMapper` mới. Chọn phạm vi cấu hình nhỏ nhất đáp ứng hợp đồng, nhưng không cố nhét các chính sách không tương thích vào một mapper dùng chung.

## 3. Kiến trúc: mapper theo hợp đồng, DTO theo đối tác

Một mô hình dễ bảo trì:

```text
Partner A HTTP / webhook
        |
        v
Partner A message converter / reader
        |
        v
PartnerAOrderRequest DTO
        |
        v
Partner A adapter
        |
        v
Canonical Order command / domain model
        |
        +--------------------------+
        |                          |
        v                          v
Internal use case             Domain rules

Partner B HTTP / message
        |
        v
Partner B converter / reader
        |
        v
PartnerBOrderRequest DTO
        |
        v
Partner B adapter
        |
        +----> Canonical Order command
```

Mỗi adapter chịu trách nhiệm chuyển contract bên ngoài thành model nội bộ. Domain không cần biết Partner A dùng `order_id` hay Partner B dùng `orderId`.

### 3.1. Vì sao không dùng entity/domain model làm DTO của mọi đối tác?

Nếu tất cả đối tác deserialize trực tiếp vào một entity chung, model sẽ dần chứa nhiều annotation, alias, custom serializer, ignore rule và ngoại lệ theo từng hệ thống. Một thay đổi phục vụ đối tác này có thể làm thay đổi JSON của đối tác khác.

DTO riêng tạo ranh giới rõ:

- Chỉ chứa field mà tích hợp đó được phép gửi.
- Có kiểu và date format phù hợp hợp đồng.
- Không cho đối tác cập nhật field quản trị nội bộ qua mass assignment.
- Có thể version DTO mà không buộc domain model thay đổi.
- Dễ kiểm thử bằng fixture của từng đối tác.

DTO không nhất thiết phải có một class cho từng endpoint nếu các endpoint thật sự dùng cùng contract. Hãy tách khi schema, semantics, version hoặc policy khác nhau đáng kể.

## 4. Chọn giữa `ObjectMapper`, `ObjectReader` và `ObjectWriter`

Ba lựa chọn phục vụ ba phạm vi khác nhau:

| Công cụ | Dùng khi | Ví dụ |
|---|---|---|
| `ObjectMapper` riêng | Hợp đồng cần module, mix-in, naming, subtype, date format hoặc nhiều policy khác nhau | Mapper cho Partner A và Partner B |
| `ObjectReader` | Cần cấu hình deserialize theo target type/lần đọc | Strict reader và tolerant reader cho cùng DTO |
| `ObjectWriter` | Cần cấu hình serialize theo representation/lần ghi | Writer có view, pretty print hoặc inclusion khác |

`ObjectReader` và `ObjectWriter` là đối tượng cấu hình bất biến, có thể tạo từ mapper đã cấu hình và tái sử dụng. Chúng phù hợp cho những feature Jackson hỗ trợ ở phạm vi reader/writer.

Những khác biệt như module đăng ký, naming strategy, mix-in, subtype registry hoặc custom serializer thường thuộc cấu hình mapper. Không nên cố thay chúng bằng một reader/writer nếu API không cung cấp phạm vi cấu hình tương ứng.

### 4.1. Ví dụ reader/writer theo use case

```java
ObjectReader strictPartnerReader = mapper.readerFor(PartnerEvent.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

ObjectReader tolerantPartnerReader = mapper.readerFor(PartnerEvent.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter compactWriter = mapper.writerFor(PartnerEvent.class);

ObjectWriter prettyWriter = mapper.writerFor(PartnerEvent.class)
        .withDefaultPrettyPrinter();
```

Hai reader có thể chia sẻ cùng module và naming strategy nhưng áp dụng unknown-property policy khác nhau. Nếu hai đối tác còn dùng date format và property naming khác nhau, tạo mapper riêng thường rõ ràng hơn.

### 4.2. Không mutate mapper theo request

Không làm:

```java
// Không thay đổi mapper dùng chung theo từng request.
mapper.setPropertyNamingStrategy(strategyFor(request.getPartner()));
mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
```

Hai request đồng thời có thể chạy trong lúc cấu hình bị thay đổi. Serializer/deserializer cache cũng có thể được xây dựng từ cấu hình trước đó. Kết quả có thể phụ thuộc thứ tự request và thời điểm mapper được sử dụng.

Hãy tạo mapper theo hợp đồng ở startup hoặc chọn reader/writer đã cấu hình sẵn từ registry.

## 5. Xây dựng nhiều mapper trong Spring

Spring cho phép khai báo nhiều bean `ObjectMapper` và inject theo tên bằng `@Qualifier`. Nên đặt tên thể hiện ranh giới hợp đồng:

- `internalApiObjectMapper`
- `partnerAObjectMapper`
- `partnerBObjectMapper`
- `legacyImportObjectMapper`

Không đặt tên chung như `mapper1`, `specialMapper` vì người đọc không biết mapper dành cho hệ thống nào.

### 5.1. Cấu hình mapper dùng chung cho Internal API và hai đối tác

```java
@Configuration
public class JacksonIntegrationConfiguration {

    @Bean
    @Primary
    @Qualifier("internalApiObjectMapper")
    ObjectMapper internalApiObjectMapper(Jackson2ObjectMapperBuilder builder) {
        ObjectMapper mapper = builder.build();
        mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
        mapper.enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
        return mapper;
    }

    @Bean
    @Qualifier("partnerAObjectMapper")
    ObjectMapper partnerAObjectMapper(Jackson2ObjectMapperBuilder builder) {
        ObjectMapper mapper = builder.build();
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        mapper.addMixIn(PartnerAOrderRequest.class, PartnerAOrderMixin.class);
        return mapper;
    }

    @Bean
    @Qualifier("partnerBObjectMapper")
    ObjectMapper partnerBObjectMapper(Jackson2ObjectMapperBuilder builder) {
        ObjectMapper mapper = builder.build();
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.LOWER_CAMEL_CASE);
        mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        mapper.disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT);
        return mapper;
    }
}
```

`Jackson2ObjectMapperBuilder` là builder của Spring cho Jackson 2.x. Trong Spring Boot, builder thường được auto-configure với một số module, feature và customizer của ứng dụng. Gọi `build()` tạo mapper mới; sau đó áp dụng policy riêng trước khi bean được chia sẻ.

`@Primary` ở đây chọn mapper nội bộ làm ứng viên mặc định khi có injection chỉ theo type. Các integration phải dùng `@Qualifier` rõ ràng. Nếu không có một mapper mặc định hợp lý, có thể bỏ `@Primary` và yêu cầu mọi injection chọn qualifier.

### 5.2. Vì sao dùng `builder.build()` thay vì tự `new ObjectMapper()`?

Trong ứng dụng Spring Boot, builder có thể mang cấu hình chung như Java Time module, Kotlin module, naming/customizer, date/time settings hoặc module do ứng dụng đăng ký. Tạo `new ObjectMapper()` độc lập có thể bỏ qua những cấu hình đó.

`builder.build()` giúp mỗi mapper nhận baseline Spring đã cấu hình, sau đó thêm chính sách riêng. Tuy nhiên, không nên sửa builder dùng chung theo từng integration bằng cách liên tục gọi `featuresToEnable`, `modules` hoặc `mixIn` trên cùng builder trước mỗi lần `build()` nếu không kiểm soát việc các cấu hình đó tích lũy. Cách dễ hiểu là build mapper từ baseline rồi áp dụng các thay đổi riêng trực tiếp lên mapper mới trước khi publish bean.

### 5.3. Lưu ý khi khai báo nhiều `ObjectMapper` bean

Spring Boot auto-configuration thường tạo mapper mặc định khi chưa có bean `ObjectMapper` do ứng dụng cung cấp. Khi ứng dụng tự khai báo mapper, điều kiện auto-configuration có thể thay đổi; không giả định một mapper mặc định khác vẫn được tạo như trước.

Nếu ứng dụng cần mapper mặc định cho HTTP MVC, hãy khai báo bean `@Primary` rõ ràng hoặc cấu hình HTTP message converter cụ thể. Đồng thời kiểm tra `Jackson2ObjectMapperBuilder` và customizer còn được tạo theo cấu hình Spring Boot đang dùng.

## 6. Inject đúng mapper bằng `@Qualifier`

Ví dụ adapter Partner A:

```java
@Component
public class PartnerAClient {
    private final ObjectMapper mapper;

    public PartnerAClient(
            @Qualifier("partnerAObjectMapper") ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public PartnerAOrderRequest readResponse(byte[] body) throws IOException {
        return mapper.readValue(body, PartnerAOrderRequest.class);
    }
}
```

Adapter Partner B:

```java
@Component
public class PartnerBClient {
    private final ObjectMapper mapper;

    public PartnerBClient(
            @Qualifier("partnerBObjectMapper") ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public PartnerBOrderRequest readResponse(byte[] body) throws IOException {
        return mapper.readValue(body, PartnerBOrderRequest.class);
    }
}
```

`@Qualifier` làm rõ mapper nào thuộc hợp đồng nào và tránh phụ thuộc thứ tự bean được tạo. Nếu chỉ inject `ObjectMapper` trong khi có nhiều bean cùng type, Spring có thể báo `NoUniqueBeanDefinitionException` trừ khi có `@Primary` hoặc qualifier phù hợp.

Không truyền mapper tùy ý từ controller vào domain service. Giữ việc deserialize ở adapter/transport boundary; service nội bộ nên nhận DTO canonical hoặc command đã được chuyển đổi.

## 7. Tách DTO và chuyển về model nội bộ

Ví dụ DTO Partner A:

```java
public record PartnerAOrderRequest(
        String orderId,
        String customerName,
        LocalDate createdDate,
        String partnerNote) {
}
```

Mix-in hoặc annotation trên DTO có thể mô tả format cụ thể. Adapter chuyển DTO thành command nội bộ:

```java
public record CreateOrderCommand(
        String externalOrderId,
        String customerName,
        LocalDate createdDate) {
}
```

```java
@Component
public class PartnerAOrderAdapter {
    public CreateOrderCommand toCommand(PartnerAOrderRequest request) {
        return new CreateOrderCommand(
                request.orderId(),
                request.customerName(),
                request.createdDate());
    }
}
```

`partnerNote` có thể được giữ ở adapter/audit model nếu use case cần, hoặc bị loại có chủ đích. Domain không cần biết JSON field đó tên `order_id` hay `orderId`.

### 7.1. Không chia sẻ DTO chỉ vì hai JSON trông giống nhau

Hai đối tác có thể cùng gửi `id` và `name`, nhưng semantics khác nhau: một bên `id` là order ID, bên kia là customer ID. Nếu chia sẻ DTO, người bảo trì dễ giả định field có cùng ý nghĩa.

Chỉ dùng chung DTO khi schema và semantics thật sự giống nhau, có cùng lifecycle/versioning và cùng chính sách validation. Tên field giống nhau chưa đủ để chứng minh hợp đồng giống nhau.

## 8. Date/time policy theo từng đối tác

Partner A gửi ngày `dd/MM/uuuu`, Partner B gửi ISO. Có thể khai báo format trên DTO riêng:

```java
public record PartnerAOrderRequest(
        String orderId,
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "dd/MM/uuuu")
        LocalDate createdDate) {
}
```

```java
public record PartnerBOrderRequest(
        String orderId,
        LocalDate createdDate) {
}
```

Mapper cần Java Time module nếu builder/Boot chưa đăng ký module này:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
```

Annotation trên property phù hợp khi format thuộc DTO/property. Nếu toàn bộ date/time của một hợp đồng dùng cùng một quy tắc, có thể cấu hình mapper hoặc custom module. Không đặt global date format theo Partner A trên mapper `@Primary` rồi mong Partner B không bị ảnh hưởng.

Với `Instant`, `OffsetDateTime` và `LocalDateTime`, cần xác định timezone/offset semantics rõ ràng. `LocalDateTime` không mang timezone; không tự diễn giải nó thành UTC nếu hợp đồng không nói vậy.

## 9. Unknown property và coercion policy

Một đối tác có thể thêm field mới trước khi consumer được nâng cấp. Tùy contract, consumer có thể bỏ qua field lạ hoặc từ chối.

Strict mapper:

```java
mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Tolerant mapper:

```java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Tolerant mode giúp forward compatibility nhưng có thể che typo. Ví dụ `quanity` có thể bị bỏ qua thay vì báo lỗi. Với contract strict, hãy từ chối unknown field; với partner contract có extension field, cân nhắc vùng `metadata` riêng có giới hạn thay vì bỏ qua mọi typo.

Coercion cũng là policy theo tích hợp. Ví dụ, một partner gửi `"3"` cho field integer; hệ thống có thể chấp nhận hoặc yêu cầu JSON number `3`. Với Jackson version hỗ trợ, dùng coercion config theo logical type; test rõ token type được phép.

Không tắt coercion hoặc unknown-property feature toàn cục chỉ để làm một partner payload đọc được. Tạo reader/mapper riêng cho partner đó.

## 10. Chính sách null và field bị thiếu

Các hợp đồng có thể diễn giải khác nhau:

- Field không xuất hiện: giữ giá trị hiện tại.
- Field xuất hiện với `null`: xóa giá trị hoặc không cập nhật.
- Field xuất hiện với empty string: đặt thành chuỗi rỗng.
- Field có giá trị: thay thế.

Đối với create request, `null` có thể có nghĩa là thiếu dữ liệu. Với PATCH, `absent` và `null` thường có ý nghĩa khác nhau. DTO dùng `String` hoặc `Optional<String>` đơn giản có thể không giữ đủ ba trạng thái nếu Jackson cấu hình/default gộp chúng.

Nếu semantics khác nhau theo partner, hãy biểu diễn rõ bằng DTO/patch wrapper hoặc custom deserializer có test. Không cố dùng `@JsonInclude(NON_NULL)` để kiểm soát cách deserialize; `JsonInclude` chủ yếu điều khiển output.

## 11. Serialization policy cũng cần tách riêng

Nhiều ứng dụng chỉ nghĩ đến mapper khi đọc request. Nhưng output cũng là hợp đồng: field nào được xuất, tên gì, null có được ghi, enum/date được biểu diễn ra sao.

Ví dụ Partner A cần bỏ null:

```java
ObjectMapper partnerAMapper = builder.build();
partnerAMapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
```

Partner B cần giữ null:

```java
ObjectMapper partnerBMapper = builder.build();
partnerBMapper.setSerializationInclusion(JsonInclude.Include.ALWAYS);
```

Không đổi inclusion trên mapper dùng chung theo từng response. Tạo writer riêng nếu khác biệt chỉ là một lần ghi và Jackson hỗ trợ feature ở writer scope:

```java
ObjectMapper partnerAOutputMapper = builder.build();
partnerAOutputMapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
ObjectWriter omitNulls = partnerAOutputMapper.writerFor(PartnerAOrderResponse.class);
```

Ví dụ này dùng mapper riêng vì inclusion là một phần của policy output ổn định cho Partner A. Nếu chỉ một property cần quy tắc khác, có thể dùng `@JsonInclude` trên DTO/property. Luôn test JSON output cuối cùng.

## 12. HTTP MVC: message converter là nơi chọn mapper

Trong Spring MVC, `@RequestBody` và `@ResponseBody` thường đi qua `HttpMessageConverter`. Jackson converter đọc request dựa trên target Java type và request `Content-Type`; ghi response dựa trên return type và negotiated media type.

Một điểm quan trọng: chỉ khai báo nhiều `ObjectMapper` bean không làm Spring tự biết mapper nào dành cho Partner A. Converter cần được cấu hình để sử dụng mapper tương ứng và chỉ nhận media type phù hợp.

### 12.1. Dùng vendor media type để tách contract

Nếu hai tích hợp có thể dùng media type riêng, đây là cách rõ ràng:

```text
Partner A: application/vnd.example.partner-a+json
Partner B: application/vnd.example.partner-b+json
Internal:  application/json
```

Đăng ký converter:

```java
@Configuration
public class PartnerMessageConverterConfiguration implements WebMvcConfigurer {
    private final ObjectMapper partnerAMapper;
    private final ObjectMapper partnerBMapper;

    public PartnerMessageConverterConfiguration(
            @Qualifier("partnerAObjectMapper") ObjectMapper partnerAMapper,
            @Qualifier("partnerBObjectMapper") ObjectMapper partnerBMapper) {
        this.partnerAMapper = partnerAMapper;
        this.partnerBMapper = partnerBMapper;
    }

    @Override
    public void extendMessageConverters(List<HttpMessageConverter<?>> converters) {
        MappingJackson2HttpMessageConverter partnerAConverter =
                new MappingJackson2HttpMessageConverter(partnerAMapper);
        partnerAConverter.setSupportedMediaTypes(List.of(
                MediaType.valueOf("application/vnd.example.partner-a+json")));

        MappingJackson2HttpMessageConverter partnerBConverter =
                new MappingJackson2HttpMessageConverter(partnerBMapper);
        partnerBConverter.setSupportedMediaTypes(List.of(
                MediaType.valueOf("application/vnd.example.partner-b+json")));

        converters.add(0, partnerAConverter);
        converters.add(0, partnerBConverter);
    }
}
```

`setSupportedMediaTypes()` giới hạn converter vào media type của hợp đồng tương ứng. Converter JSON mặc định vẫn có thể xử lý `application/json` cho internal API.

Endpoint:

```java
@PostMapping(
        path = "/partner-a/orders",
        consumes = "application/vnd.example.partner-a+json",
        produces = "application/vnd.example.partner-a+json")
public PartnerAOrderResponse receivePartnerA(
        @RequestBody PartnerAOrderRequest request) {
    return partnerAService.handle(request);
}
```

Request có media type khác sẽ không được endpoint/converter chấp nhận theo contract. `consumes` và `produces` mô tả điều kiện mapping/content negotiation; converter mới là thành phần thực hiện Jackson binding.

### 12.2. Không đăng ký hai converter cùng hỗ trợ một media type chung mà khác policy

Nếu cả Partner A và Partner B đều gửi `application/json`, hai converter cùng hỗ trợ `application/json` có thể trở nên mơ hồ. Spring duyệt danh sách converter theo thứ tự và chọn converter phù hợp đầu tiên; kết quả có thể phụ thuộc thứ tự đăng ký thay vì partner identity.

Nếu có thể thay đổi contract, dùng vendor media type hoặc versioned media type. Nếu không thể thay đổi media type, hãy chọn một trong các cách:

- Tách endpoint và dùng argument resolver/handler có chọn mapper rõ ràng.
- Nhận `JsonNode` rồi bind bằng reader/mapper của endpoint.
- Viết converter tùy chỉnh có điều kiện theo target type và context rõ ràng.
- Dùng adapter/client riêng ở phía outbound thay vì phụ thuộc converter MVC chung.

Không thêm hai converter cùng `application/json` rồi hy vọng Spring tự nhận diện tên partner từ payload. Converter selection không tự hiểu business identity nếu contract không cung cấp tín hiệu.

### 12.3. Bind thủ công từ `JsonNode` khi media type không phân biệt được

Nếu hai endpoint cùng nhận `application/json` nhưng cần mapper khác nhau, có thể để MVC parse body thành `JsonNode`, sau đó bind tree bằng mapper đúng:

```java
@RestController
public class PartnerWebhookController {
    private final ObjectMapper partnerAMapper;

    public PartnerWebhookController(
            @Qualifier("partnerAObjectMapper") ObjectMapper partnerAMapper) {
        this.partnerAMapper = partnerAMapper;
    }

    @PostMapping(path = "/webhooks/partner-a", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> partnerA(@RequestBody JsonNode body) throws IOException {
        try (JsonParser parser = body.traverse(partnerAMapper)) {
            PartnerAOrderRequest request = partnerAMapper
                    .readerFor(PartnerAOrderRequest.class)
                    .readValue(parser);
            partnerAService.handle(request);
        }
        return ResponseEntity.accepted().build();
    }
}
```

Đây là cách minh họa; controller cần inject service và xử lý lỗi theo ứng dụng. `JsonNode` được tạo bởi converter mặc định, sau đó mapper Partner A thực hiện tree-to-DTO binding. Cách này tránh đọc raw body hai lần, nhưng một số khác biệt ở tầng parser ban đầu như duplicate key hoặc coercion có thể đã được xử lý theo mapper tạo tree. Nếu các chính sách đó quan trọng, dùng custom argument resolver/converter đọc raw stream bằng mapper Partner A ngay từ đầu.

### 12.4. Khi nào cần custom `HttpMessageConverter`?

Custom converter phù hợp khi cần:

- Chọn mapper theo annotation trên controller parameter.
- Áp dụng một reader cụ thể cho target DTO.
- Kiểm tra schema/version header trước khi binding.
- Xử lý envelope hoặc framing riêng.
- Kiểm soát exception mapping/streaming đặc thù.

Converter nên có `canRead`/`canWrite` hẹp và có thể dự đoán. Tránh một converter bắt mọi `Object.class` và mọi media type vì nó có thể chiếm quyền của converter JSON/XML/binary khác.

## 13. Outbound HTTP: một client cho mỗi đối tác

Ở phía gọi đối tác, không nhất thiết phải dùng một converter MVC toàn cục. Có thể cấu hình HTTP client riêng theo hợp đồng.

### 13.1. `RestClient` với converter riêng

Spring Framework 6.1 có `RestClient`. Ví dụ tạo client dùng mapper Partner A:

```java
MappingJackson2HttpMessageConverter partnerAJsonConverter =
        new MappingJackson2HttpMessageConverter(partnerAMapper);
partnerAJsonConverter.setSupportedMediaTypes(List.of(
        MediaType.APPLICATION_JSON,
        MediaType.valueOf("application/vnd.example.partner-a+json")));

RestClient partnerAClient = RestClient.builder()
        .messageConverters(converters -> {
            converters.removeIf(
                    converter -> converter instanceof MappingJackson2HttpMessageConverter);
            converters.add(0, partnerAJsonConverter);
        })
        .build();
```

Đoạn ví dụ thay Jackson converter mặc định trong danh sách của client và thêm converter có mapper Partner A. Giữ các converter khác như String, byte array, resource và form nếu client cần chúng.

Trong Spring Boot, có thể inject `RestClient.Builder` đã được customize thay vì gọi `RestClient.builder()` trực tiếp. Nếu builder được dùng cho nhiều client, tạo builder clone hoặc builder riêng theo API version và kiểm tra các customization không bị tích lũy giữa partner clients.

Gọi API:

```java
PartnerAOrderResponse response = partnerAClient.post()
        .uri("/orders")
        .contentType(MediaType.valueOf("application/vnd.example.partner-a+json"))
        .accept(MediaType.valueOf("application/vnd.example.partner-a+json"))
        .body(partnerARequest)
        .retrieve()
        .body(PartnerAOrderResponse.class);
```

Client có mapper riêng nên serialization request và deserialization response tuân theo cùng partner contract. Nếu request và response có policy khác nhau, converter hoặc client có thể cần cấu hình reader/writer riêng.

### 13.2. `RestTemplate` với message converter riêng

Với ứng dụng còn dùng `RestTemplate`, có thể tạo instance riêng và thay Jackson converter:

```java
MappingJackson2HttpMessageConverter partnerBConverter =
        new MappingJackson2HttpMessageConverter(partnerBMapper);
partnerBConverter.setSupportedMediaTypes(List.of(
        MediaType.APPLICATION_JSON,
        MediaType.valueOf("application/vnd.example.partner-b+json")));

RestTemplate partnerBRestTemplate = new RestTemplate();
List<HttpMessageConverter<?>> converters =
        new ArrayList<>(partnerBRestTemplate.getMessageConverters());
converters.removeIf(
        converter -> converter instanceof MappingJackson2HttpMessageConverter);
converters.add(0, partnerBConverter);
partnerBRestTemplate.setMessageConverters(converters);
```

Đây là cấu hình theo client instance. Không sửa `RestTemplate` dùng chung của ứng dụng sau khi đã bắt đầu phục vụ request. Nếu dùng `RestTemplateBuilder` của Spring Boot, có thể tạo instance theo builder để giữ timeout, request factory và interceptor chuẩn của ứng dụng rồi thay converter trong bước cấu hình cuối.

## 14. Reactive HTTP: cấu hình `WebClient` codec riêng

`WebClient` dùng codec thay cho `HttpMessageConverter`. Để dùng mapper Partner A, cấu hình Jackson encoder/decoder:

```java
ExchangeStrategies partnerAStrategies = ExchangeStrategies.builder()
        .codecs(codecs -> {
            codecs.defaultCodecs().jackson2JsonEncoder(
                    new Jackson2JsonEncoder(partnerAMapper,
                            MediaType.APPLICATION_JSON,
                            MediaType.valueOf("application/vnd.example.partner-a+json")));
            codecs.defaultCodecs().jackson2JsonDecoder(
                    new Jackson2JsonDecoder(partnerAMapper,
                            MediaType.APPLICATION_JSON,
                            MediaType.valueOf("application/vnd.example.partner-a+json")));
        })
        .build();

WebClient partnerAWebClient = WebClient.builder()
        .exchangeStrategies(partnerAStrategies)
        .build();
```

Constructor và codec configuration có thể khác giữa Spring Framework versions; hãy xác nhận signature của `Jackson2JsonEncoder`/`Jackson2JsonDecoder` trong version đang dùng. Trong Spring Boot, có thể sử dụng `WebClient.Builder` đã được customize rồi áp dụng `ExchangeStrategies` cho client cụ thể.

Gọi:

```java
Mono<PartnerAOrderResponse> result = partnerAWebClient.post()
        .uri("https://partner-a.example.test/orders")
        .contentType(MediaType.valueOf("application/vnd.example.partner-a+json"))
        .accept(MediaType.valueOf("application/vnd.example.partner-a+json"))
        .bodyValue(partnerARequest)
        .retrieve()
        .bodyToMono(PartnerAOrderResponse.class);
```

Không sửa codec của một `WebClient` đang được chia sẻ cho các integration khác. Tạo builder/client có cấu hình riêng ở startup và tái sử dụng.

## 15. Message broker cũng cần mapper theo contract

HTTP không phải ranh giới duy nhất. Một ứng dụng có thể đọc event từ Kafka hoặc RabbitMQ với naming, schema và type policy riêng.

### 15.1. Spring Kafka

Spring Kafka cung cấp JSON serializer/deserializer có thể nhận `ObjectMapper`:

```java
JsonSerializer<PartnerAEvent> serializer =
        new JsonSerializer<>(partnerAMapper);

JsonDeserializer<PartnerAEvent> deserializer =
        new JsonDeserializer<>(PartnerAEvent.class, partnerAMapper);
```

Producer factory và consumer factory nên được cấu hình theo event contract. Nếu topic A và topic B dùng mapper khác nhau, tạo serializer/deserializer và factory tương ứng; không dùng một mapper global rồi thay feature trước mỗi record.

Tùy Spring Kafka version, các constructor, type header policy và trusted package configuration có thể khác. Nếu dùng type headers, kiểm tra rõ consumer có tin header do producer gửi hay không; không cho metadata tùy ý chọn class ngoài allowlist. Ưu tiên target type cố định hoặc subtype mapping có kiểm soát.

### 15.2. RabbitMQ

Với Spring AMQP, `Jackson2JsonMessageConverter` có thể được tạo từ mapper riêng:

```java
Jackson2JsonMessageConverter partnerAMessageConverter =
        new Jackson2JsonMessageConverter(partnerAMapper);
```

Gắn converter đó vào `RabbitTemplate` hoặc listener container factory của integration tương ứng. Nếu nhiều listener cần contract khác nhau, tạo các container factory/converter riêng.

Kiểm tra message properties như content type, type header và trusted packages theo version Spring AMQP. Converter riêng không thay thế kiểm tra quyền producer, schema version và validation nghiệp vụ.

## 16. Chính sách đọc và ghi có thể khác nhau ngay trong cùng một tích hợp

Một partner có thể gửi dữ liệu theo format cũ nhưng muốn nhận output theo format mới. Khi đó, không nhất thiết phải dùng cùng một policy cho hai chiều.

Ví dụ:

- Input: chấp nhận `created_date` và alias cũ `createdAt`.
- Output: chỉ ghi `created_date`.
- Input: tolerant với field mới không biết.
- Output: chỉ phát field nằm trong allowlist.

Có thể dùng `ObjectReader` và `ObjectWriter` riêng:

```java
ObjectReader partnerAInputReader = partnerAMapper
        .readerFor(PartnerAOrderRequest.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectWriter partnerAOutputWriter = partnerAMapper
        .writerFor(PartnerAOrderResponse.class)
        .with(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Ví dụ feature date chỉ mang tính minh họa; hãy dùng đúng format được partner quy định. Nếu output cần serializer/module hoặc mix-in khác hẳn input, dùng mapper riêng cho write path hoặc DTO output riêng.

Không mặc định rằng một mapper phải có cùng chính sách serialize và deserialize. Hãy ghi rõ input contract và output contract trong tài liệu tích hợp.

## 17. Mapper theo partner hay mapper theo format?

Một ứng dụng có thể có nhiều chiều phân chia:

- Theo đối tác: Partner A, Partner B.
- Theo version: Partner A v1, Partner A v2.
- Theo data format: JSON, CBOR, XML.
- Theo mục đích: public API, internal event, file import.

Không nhất thiết tạo mapper cho mọi tổ hợp nếu chúng có chung policy. Nhưng cũng không ép mọi thứ vào một mapper chỉ để giảm số bean.

Một registry có thể biểu diễn rõ ranh giới:

```java
public enum IntegrationContract {
    PARTNER_A_V1,
    PARTNER_A_V2,
    PARTNER_B_V1,
    INTERNAL_JSON
}
```

```java
public final class IntegrationMapperRegistry {
    private final Map<IntegrationContract, ObjectMapper> mappers;

    public IntegrationMapperRegistry(
            ObjectMapper partnerAV1,
            ObjectMapper partnerAV2,
            ObjectMapper partnerB,
            ObjectMapper internal) {
        this.mappers = Map.of(
                IntegrationContract.PARTNER_A_V1, partnerAV1,
                IntegrationContract.PARTNER_A_V2, partnerAV2,
                IntegrationContract.PARTNER_B_V1, partnerB,
                IntegrationContract.INTERNAL_JSON, internal);
    }

    public ObjectMapper mapperFor(IntegrationContract contract) {
        ObjectMapper mapper = mappers.get(contract);
        if (mapper == null) {
            throw new IllegalArgumentException("Unsupported contract: " + contract);
        }
        return mapper;
    }
}
```

Trong ứng dụng Spring, thường dùng bean qualifier cho injection trực tiếp; registry hữu ích khi contract được chọn từ một mã logic đã xác thực ở runtime. Không dùng chuỗi class name do payload cung cấp để tra mapper hoặc khởi tạo mapper.

## 18. Chọn contract từ request một cách an toàn

Nếu một endpoint nhận nhiều contract, tín hiệu chọn contract phải rõ và được kiểm tra:

- Route/path version đã công bố.
- Vendor media type.
- Header version do server quy định.
- Message topic/subject đã cấu hình.
- Partner identity được xác thực và ánh xạ sang contract trong server-side registry.

Không chọn mapper dựa vào field `mapperClass`, `javaType` hoặc tên package do payload gửi. Không cho request điều khiển module registration.

Ví dụ chọn adapter sau authentication:

```java
IntegrationContract contract = contractRegistry.contractFor(authenticatedPartnerId);
ObjectReader reader = readers.get(contract);
PartnerCommand command = reader.readValue(bodyBytes);
```

`authenticatedPartnerId` phải đến từ credential/security context đã xác thực, không phải từ một field JSON không được kiểm chứng. Nếu route/media type đã chỉ rõ contract, vẫn kiểm tra caller có quyền dùng contract đó.

## 19. Xử lý schema version và migration

Partner có thể thay đổi contract theo thời gian. Có thể duy trì mapper/DTO theo version:

```text
Partner A v1 JSON -> PartnerAOrderV1 DTO --+
                                          +--> CanonicalOrderCommand
Partner A v2 JSON -> PartnerAOrderV2 DTO --+
```

Version cũ có thể dùng `order_id`, version mới dùng `id`; adapter chịu trách nhiệm chuyển đổi. Domain chỉ nhận một command canonical.

Quy trình:

1. Xác định version qua route, media type parameter hoặc metadata đã công bố.
2. Chọn reader/mapper cố định cho version đó.
3. Deserialize vào DTO versioned.
4. Validate theo schema/constraint của version.
5. Migrate DTO sang command canonical.
6. Ghi metric version và thời điểm ngừng hỗ trợ version cũ.

Không thay đổi mapper đang dùng để “tạm hỗ trợ” một version mới trong request. Tạo cấu hình version riêng và test fixture cho từng version.

## 20. Không để custom serializer/deserializer chứa logic partner tùy tiện

Một custom handler nên biểu diễn một kiểu dữ liệu hoặc một quy tắc wire format rõ ràng. Nếu một `MoneyDeserializer` kiểm tra partner name từ global state để quyết định format, handler trở nên phụ thuộc request và không an toàn khi dùng đồng thời.

Các cách tốt hơn:

- Tạo `PartnerAMoneyDeserializer` và `PartnerBMoneyDeserializer` trong module riêng.
- Dùng DTO/property annotation khác nhau nếu format chỉ khác ở property cụ thể.
- Dùng contextual deserializer với metadata bất biến trên property.
- Chuyển đổi trong adapter sau khi deserialize raw DTO nếu khác biệt là nghiệp vụ chứ không phải token format.

Không gọi database, HTTP hoặc service khác từ custom deserializer. Nếu format phụ thuộc dữ liệu động từ hệ thống, deserialize thành raw value trước rồi xử lý ở application service.

## 21. Cấu hình module chung và module riêng

Một số module cần cho mọi mapper, ví dụ Java Time hoặc Kotlin; một số module chỉ dành cho một integration.

Có thể chia:

```text
Common Jackson modules
  - JavaTimeModule
  - ParameterNamesModule (nếu cần)
  - application-wide scalar modules

Partner A modules
  - PartnerA legacy date format
  - PartnerA enum serializer
  - PartnerA mix-ins

Partner B modules
  - PartnerB money format
  - PartnerB subtype mapping
```

Khi dùng Spring Boot builder, các module common có thể được đăng ký ở baseline. Module partner-specific được thêm sau khi `builder.build()` trên mapper riêng.

Không đăng ký module partner-specific vào mapper `@Primary` nếu internal API không dùng contract đó. Nếu một kiểu domain có wire format khác nhau theo đối tác, DTO/adapter riêng thường rõ ràng hơn một serializer global cho domain entity.

## 22. Kiểm soát mix-in theo mapper

Mix-in hữu ích khi cần áp dụng annotation cho class không sửa được. Nhưng mix-in được gắn vào mapper cụ thể:

```java
partnerAMapper.addMixIn(
        LegacyPartnerOrder.class,
        PartnerAOrderMixin.class);
```

Không thêm mix-in Partner A vào mapper dùng cho Partner B nếu nó đổi tên field, visibility hoặc creator. Một mix-in có thể thay đổi serialize và deserialize, do đó cần test cả hai chiều.

Nếu cùng class legacy được dùng bởi hai tích hợp với contract khác nhau, có thể dùng hai mapper riêng, mỗi mapper có mix-in riêng. Tuy nhiên, DTO adapter riêng vẫn thường dễ hiểu hơn nếu hai contract khác nhau nhiều.

## 23. Kiểm soát subtype và polymorphic policy theo tích hợp

Một partner có thể gửi nhiều loại event qua field `kind`. Subtype allowlist của partner đó nên nằm trong mapper/DTO của integration:

```java
@JsonTypeInfo(use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(value = PartnerAOrderCreated.class, name = "order_created"),
        @JsonSubTypes.Type(value = PartnerAOrderCancelled.class, name = "order_cancelled")
})
public interface PartnerAEvent {
}
```

Không dùng default typing rộng cho payload bên ngoài. Không để type ID hoặc class name do partner gửi khởi tạo bất kỳ class nào trên classpath. Nếu Partner B có event vocabulary khác, dùng base type/DTO và allowlist riêng.

## 24. Kiểm thử mapper theo từng hợp đồng

Mỗi mapper cần một bộ contract test riêng. Ví dụ Partner A:

```java
class PartnerAObjectMapperTest {
    private final ObjectMapper mapper = createPartnerAMapper();

    @Test
    void readsSnakeCaseAndPartnerDateFormat() throws Exception {
        String json = """
                {
                  "order_id": "A-100",
                  "customer_name": "An Nguyen",
                  "created_date": "12/11/2026"
                }
                """;

        PartnerAOrderRequest request = mapper.readValue(
                json, PartnerAOrderRequest.class);

        assertEquals("A-100", request.orderId());
        assertEquals("An Nguyen", request.customerName());
        assertEquals(LocalDate.of(2026, 11, 12), request.createdDate());
    }
}
```

Partner B test riêng với JSON camelCase và ISO date. Không dùng cùng fixture rồi chỉ đổi mapper; fixture nên đại diện đúng payload thực tế của từng đối tác.

## 25. Kiểm thử rằng các mapper không ảnh hưởng lẫn nhau

Một test quan trọng là deserialize payload Partner A bằng mapper A thành công, còn mapper B giữ policy riêng:

```java
@Test
void partnerPoliciesRemainIndependent() throws Exception {
    String partnerAJson = """
            {"order_id":"A-100","created_date":"12/11/2026"}
            """;

    PartnerAOrderRequest a = partnerAMapper.readValue(
            partnerAJson, PartnerAOrderRequest.class);
    assertEquals("A-100", a.orderId());

    assertThrows(JsonProcessingException.class,
            () -> partnerBMapper.readValue(
                    partnerAJson, PartnerBOrderRequest.class));
}
```

Điều kiện cụ thể phụ thuộc DTO và strictness của mapper. Mục tiêu là chứng minh cấu hình A không bị áp dụng ngầm cho B.

Test thêm:

- Partner A unknown property được bỏ qua theo policy; Partner B từ chối.
- Date format A không được chấp nhận ở B.
- Custom enum A không thay đổi output enum B.
- Mix-in A không đổi property của internal mapper.
- Serialization output của mỗi partner có tên field và null policy riêng.

## 26. Kiểm thử Spring HTTP converter và content negotiation

Unit test mapper không chứng minh MVC dùng đúng converter. Dùng `MockMvc` hoặc `WebTestClient` để kiểm tra ranh giới HTTP:

```java
mockMvc.perform(post("/partner-a/orders")
        .contentType("application/vnd.example.partner-a+json")
        .accept("application/vnd.example.partner-a+json")
        .content(partnerAJson))
    .andExpect(status().isAccepted());
```

Kiểm tra thêm:

- Request đúng vendor media type được bind bằng mapper A.
- Request media type không hỗ trợ bị từ chối (thường 415).
- Body sai format trả lỗi 400 theo error contract.
- Response `Content-Type` đúng representation.
- `Accept` không được hỗ trợ có thể dẫn đến 406.
- Internal endpoint vẫn dùng mapper mặc định, không bị partner converter chiếm.

Nếu hai converter cùng hỗ trợ `application/json`, test thứ tự converter và target type rõ ràng. Tốt hơn là dùng media type riêng hoặc argument resolver khi policy cần phân biệt theo endpoint.

## 27. Kiểm thử outbound client

Với `RestClient`/`WebClient`, test cần xác nhận cả body và header:

- Request `Content-Type` đúng.
- Request `Accept` đúng.
- JSON body được serialize bằng mapper partner.
- Response body được deserialize bằng mapper partner.
- Response media type không đúng bị từ chối hoặc xử lý theo policy.
- Lỗi mapping không bị biến thành response thành công.

Có thể dùng MockWebServer, WireMock hoặc mock HTTP server để ghi lại bytes/header. Đừng chỉ mock `PartnerAClient` vì test đó bỏ qua serializer và message converter thật.

## 28. Kiểm thử message converter và consumer factory

Với Kafka/RabbitMQ, kiểm tra:

- Producer serializer dùng đúng mapper.
- Consumer deserializer dùng đúng mapper và target type.
- Type headers/schema metadata được kiểm soát.
- Unknown type ID hoặc untrusted class bị từ chối.
- Payload version cũ được xử lý theo compatibility policy.
- Mapper của topic/queue khác không bị ảnh hưởng.
- Error handler, retry và dead-letter phân biệt lỗi tạm thời với payload không hợp lệ.

Không chỉ test gọi `mapper.readValue()` trực tiếp nếu production dùng Spring Kafka/Rabbit converter. Integration test nên đi qua serializer/deserializer hoặc converter được cấu hình trong container factory.

## 29. Quản lý lỗi theo hợp đồng

Mỗi tích hợp có thể cần error mapping khác nhau, nhưng lỗi nội bộ nên được phân loại nhất quán:

| Lỗi | Ý nghĩa | Xử lý |
|---|---|---|
| Unsupported media type | Không có mapper/converter cho format | Từ chối sớm, không đoán format |
| Parse error | Bytes/text không đúng cú pháp format | Báo malformed payload |
| Mapping error | Token/field không phù hợp DTO | Báo field/type invalid |
| Validation error | DTO được tạo nhưng vi phạm constraint | Trả lỗi validation theo contract |
| Business error | Dữ liệu hợp lệ về cấu trúc nhưng thao tác không được phép | Trả mã nghiệp vụ |
| Schema/version error | Version không được hỗ trợ hoặc schema ID không tìm thấy | Quarantine hoặc từ chối theo policy |
| Transport error | Timeout, kết nối hoặc body bị cắt | Retry có giới hạn nếu phù hợp |

Không trả stack trace hoặc raw payload nhạy cảm. Có thể log integration name, contract version, correlation ID, exception type và field path sau khi redaction.

## 30. Hiệu năng và số lượng mapper

Nhiều mapper không đồng nghĩa phải tạo một mapper mới cho mỗi request. Tạo mapper có chi phí khởi tạo và cache serializer/deserializer. Nên tạo một lần cho mỗi contract/configuration ổn định rồi tái sử dụng.

Một ứng dụng có thể có vài mapper theo partner/version/format; số lượng đó thường nhỏ và có chủ đích. Nếu số lượng tenant hoặc schema động lên đến hàng nghìn, không nên tạo mapper không giới hạn cho từng tenant. Hãy dùng một cấu hình chung với reader/writer theo policy có thể biểu diễn cục bộ, cache bounded hoặc thiết kế adapter/version strategy khác.

Không lưu mapper trong map không giới hạn theo header do client gửi. Chỉ chọn từ registry allowlist do server quản lý.

## 31. Vòng đời và thread safety

Sau khi cấu hình xong, `ObjectMapper`, `ObjectReader` và `ObjectWriter` có thể được tái sử dụng theo thiết kế của Jackson. Để giữ an toàn:

- Đăng ký module, mix-in và feature trước khi mapper được dùng.
- Không thay đổi mapper sau startup.
- Dùng reader/writer bất biến cho biến thể theo use case.
- Custom serializer/deserializer nên stateless hoặc giữ cấu hình bất biến.
- Không lưu request-specific value trong field của serializer/deserializer.
- Không giữ `JsonParser`/`JsonGenerator` qua nhiều lần gọi.
- Không tạo mapper mới cho từng request.

Nếu cần đổi contract, tạo bean/configuration version mới và rollout có kiểm soát. Không mutate mapper đang được nhiều thread sử dụng.

## 32. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Một mapper global cho mọi partner | Naming/date/null/unknown policy xung đột | Mapper theo hợp đồng hoặc reader/writer theo phạm vi |
| Thay feature mapper theo request | Race condition và cache không nhất quán | Cấu hình mapper ở startup |
| Chỉ khai báo nhiều bean mapper | Spring converter vẫn dùng mapper khác | Cấu hình converter/client/codec rõ ràng |
| Hai MVC converter cùng hỗ trợ `application/json` | Chọn converter phụ thuộc thứ tự | Vendor media type hoặc argument resolver |
| Dùng domain entity cho mọi partner | Annotation và field nhạy cảm bị trộn | DTO riêng và adapter |
| Dùng `@Primary` thay cho qualifier ở integration | Bean mặc định bị inject nhầm | `@Qualifier` theo partner/client |
| Tạo mapper mới mỗi request | Tốn startup và mất cache | Tạo mapper singleton theo contract |
| Dùng `JsonNode` mà không nghĩ tới parser policy | Duplicate/coercion đã bị xử lý theo mapper ban đầu | Custom converter nếu parser-level policy quan trọng |
| Để payload chọn mapper/class | Có thể khởi tạo type hoặc policy không được phép | Registry allowlist và authenticated identity |
| Không test HTTP/message converter thật | Unit mapper pass nhưng transport dùng mapper khác | Integration test qua ranh giới thật |

## 33. Quy trình thiết kế nhiều chính sách đọc ghi

Khi tích hợp thêm một hệ thống, thực hiện theo trình tự:

1. Thu thập payload input/output mẫu và schema/version của hệ thống đó.
2. Ghi rõ property naming, date/time, null, unknown field, coercion, subtype và format.
3. Xác định khác biệt nào là mapper-wide, khác biệt nào có thể dùng `ObjectReader`/`ObjectWriter`.
4. Tạo DTO riêng nếu semantics hoặc field allowlist khác model nội bộ.
5. Khai báo mapper bean có tên rõ và inject bằng `@Qualifier`.
6. Nếu là HTTP inbound, cấu hình message converter/argument resolver phù hợp; không chỉ khai báo mapper bean.
7. Nếu là HTTP outbound, tạo `RestClient`, `RestTemplate` hoặc `WebClient` riêng với converter/codec phù hợp.
8. Nếu là broker, cấu hình serializer/deserializer và container factory theo contract.
9. Chuyển DTO sang command/domain model ở adapter.
10. Viết contract test, mismatch test và integration test qua transport.
11. Ghi nhận schema version, error mapping và compatibility window.
12. Tạo mapper một lần, tái sử dụng và theo dõi lỗi theo integration.

## 34. Checklist trước khi đưa integration vào production

- [ ] Có input/output contract và payload fixture của đối tác.
- [ ] DTO chỉ chứa field mà đối tác được phép gửi.
- [ ] Mapper/reader/writer có tên và phạm vi rõ ràng.
- [ ] Module, mix-in, date format và naming policy được cấu hình trước khi dùng.
- [ ] Mapper được inject bằng `@Qualifier` ở adapter/client.
- [ ] Không mutate mapper theo request.
- [ ] `@Primary` chỉ dùng cho default mapper có chủ đích.
- [ ] MVC converter hỗ trợ đúng media type và mapper.
- [ ] Không có converter mơ hồ cùng hỗ trợ một media type chung với policy khác nhau.
- [ ] Outbound HTTP client dùng đúng converter/codec.
- [ ] Message broker dùng serializer/deserializer và type policy riêng.
- [ ] Input/output policy được kiểm tra độc lập.
- [ ] Unknown field, coercion, null và date format có test rõ.
- [ ] DTO được chuyển sang canonical command/domain model.
- [ ] Error response không lộ raw payload/stack trace.
- [ ] Integration test xác nhận bytes, header và mapper thật.
- [ ] Có schema version và kế hoạch tương thích khi contract thay đổi.

## 35. Ghi nhớ

Khi nhiều hệ thống có hợp đồng khác nhau, hãy đặt chính sách Jackson ở ranh giới tích hợp tương ứng. Dùng `ObjectMapper` riêng khi khác biệt liên quan module, naming, mix-in, subtype hoặc nhiều cấu hình; dùng `ObjectReader`/`ObjectWriter` khi chỉ cần biến thể đọc/ghi cục bộ. Trong Spring MVC, mapper bean không tự quyết định converter nào được dùng: cần cấu hình message converter và media type rõ ràng. Với outbound HTTP hoặc message broker, tạo client/converter/codec riêng cho từng hợp đồng.

Giữ DTO theo đối tác và chuyển chúng về model nội bộ qua adapter. Không mutate mapper theo request, không để payload chọn class/mapper tùy ý và không dùng một converter mơ hồ cho nhiều contract cùng media type. Kiểm thử mapper, transport converter, header, bytes và schema version riêng cho từng integration. Khi mỗi ranh giới có một chính sách đọc/ghi được đặt tên và kiểm thử rõ, thay đổi của một đối tác sẽ ít có nguy cơ làm hỏng các tích hợp còn lại.
