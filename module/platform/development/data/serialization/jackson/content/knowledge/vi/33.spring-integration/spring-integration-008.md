# Tránh thay đổi mapper dùng chung sau khi bắt đầu phục vụ

Trong ứng dụng Spring, ObjectMapper thường được tạo một lần rồi inject vào controller, service, message converter hoặc các thành phần tích hợp khác. Cách dùng này giúp mapper được tái sử dụng, giữ cache serializer/deserializer và tránh chi phí khởi tạo lặp lại.

Tuy nhiên, ObjectMapper có cấu hình mutable. Trước khi ứng dụng bắt đầu đọc hoặc ghi dữ liệu, ta có thể đăng ký module, thay naming strategy, bật/tắt feature, thêm mix-in, thay visibility hoặc cấu hình polymorphic typing. Khi mapper đã phục vụ request, việc tiếp tục thay đổi cấu hình dùng chung có thể tạo hành vi không nhất quán giữa các luồng, làm các thành phần trong ứng dụng nhìn thấy policy khác nhau và gây lỗi khó tái hiện.

Nguyên tắc quan trọng là **xây dựng và cấu hình mapper hoàn chỉnh trong giai đoạn khởi tạo, sau đó tái sử dụng mà không sửa cấu hình của nó**. Khi một operation cần policy riêng, tạo ObjectReader hoặc ObjectWriter mới từ mapper. Khi một nhóm ứng dụng cần policy khác hẳn, tạo mapper riêng và cấu hình xong trước khi đưa vào sử dụng.

## 1. Vì sao ObjectMapper thường được dùng chung?

ObjectMapper là trung tâm databind của Jackson. Nó kết hợp:

- JsonFactory để đọc và ghi token.
- Serializer và deserializer cho các Java type.
- Annotation introspection và naming strategy.
- Module như JavaTimeModule hoặc Jdk8Module.
- Cấu hình serialization/deserialization.
- Cache thông tin serializer/deserializer và type handling.

Trong Spring, mapper thường được cấu hình ở startup rồi dùng lại qua dependency injection. Ví dụ một converter HTTP dùng mapper để bind request body thành DTO và serialize response DTO thành JSON.

~~~text
Spring Application Context
          |
          v
  ObjectMapper đã cấu hình
          |
   +------+-------+----------+
   |              |          |
   v              v          v
Controller     Service    Message converter
   |              |          |
   +--------------+----------+
                  |
                JSON I/O
~~~

Một mapper dùng chung giúp mọi thành phần dùng cùng naming strategy, module, date/time format và coercion policy. Điều này hữu ích khi các endpoint cần một JSON contract nhất quán.

Tái sử dụng mapper không có nghĩa là có thể tùy ý thay đổi nó bất cứ lúc nào. Mapper nên được xem như một thành phần đã được cấu hình và công bố cho ứng dụng, tương tự một object cấu hình bất biến sau khi khởi tạo.

## 2. ObjectMapper thread-safe trong điều kiện nào?

ObjectMapper được thiết kế để dùng đồng thời từ nhiều thread **sau khi đã cấu hình hoàn tất**. Điều kiện quan trọng là mọi thay đổi cấu hình phải xảy ra trước lần đọc/ghi đầu tiên.

Ví dụ phù hợp:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();

// Sau thời điểm này, tái sử dụng mapper cho nhiều request.
~~~

Mapper được xây dựng với policy hoàn chỉnh. Nhiều thread có thể gọi readValue(), writeValueAsString(), readTree() hoặc các API tương ứng đồng thời.

Ví dụ không phù hợp:

~~~java
// Mapper đã được inject và có thể đang phục vụ request.
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

// Một thread khác có thể đang deserialize trong lúc policy bị đổi.
~~~

Thay đổi cấu hình sau khi mapper đã được dùng không phải cách an toàn để tạo policy theo request. Jackson có cache và các đối tượng reader/writer được tạo từ cấu hình trước đó; cấu hình mutable cũng không phải một giao dịch nguyên tử mà mọi thread cùng nhìn thấy tại một thời điểm xác định.

Có thể một thay đổi đơn lẻ dường như hoạt động trong môi trường test, nhưng điều đó không chứng minh nó an toàn khi có request đồng thời hoặc khi ứng dụng chạy lâu.

### 2.1. Vì sao cấu hình sau lần sử dụng đầu tiên nguy hiểm?

Một số nguyên nhân:

- Serializer/deserializer đã được tìm và cache theo cấu hình tại thời điểm trước.
- Một ObjectReader hoặc ObjectWriter đã tạo có thể giữ cấu hình riêng từ lúc được tạo.
- Thread khác có thể đang đọc/ghi trong lúc cấu hình bị thay đổi.
- Một request có thể đi qua converter đã cấu hình, request khác đi qua thành phần vừa được thay đổi.
- Behavior có thể khác giữa lần chạy đầu, lần chạy sau hoặc giữa hai instance mapper.
- Thay đổi có thể ảnh hưởng rộng hơn dự kiến vì mapper được chia sẻ qua nhiều bean.

Không nên dựa vào giả định rằng mọi setter đều xóa đúng cache và làm mọi operation đang chạy chuyển sang policy mới. Thiết kế an toàn là không mutate mapper sau khi nó được công bố.

### 2.2. Cấu hình xong trước khi dùng

~~~text
Tạo mapper
    |
    v
Đăng ký module
    |
    v
Cấu hình feature / naming / visibility
    |
    v
Thêm mix-in / subtype policy
    |
    v
Hoàn tất cấu hình
    |
    v
Công bố bean cho Spring
    |
    v
Dùng đồng thời cho request
    |
    X  Không thay đổi cấu hình dùng chung
~~~

## 3. Những thay đổi nào cần thực hiện trước khi phục vụ request?

Các API cấu hình sau đây nên được gọi trong giai đoạn tạo mapper:

| Nhóm | Ví dụ API/cấu hình |
|---|---|
| Module | registerModule(), findAndRegisterModules() |
| Naming strategy | setPropertyNamingStrategy(), propertyNamingStrategy() |
| Serialization feature | enable(), disable(), configure() |
| Deserialization feature | enable(), disable(), configure() |
| Mapper feature | configure(MapperFeature, ...) |
| Visibility | setVisibility(), visibility() |
| Mix-in | addMixIn(), setMixIns() |
| Date/time | setDateFormat(), đăng ký JavaTimeModule |
| Inclusion | setSerializationInclusion() |
| Polymorphic typing | activateDefaultTyping(), setDefaultTyping() |
| Annotation introspector | setAnnotationIntrospector() |
| Creator handling | Cấu hình module và constructor/creator behavior |

Không nên gọi các API này trong controller, service method, filter hoặc interceptor theo từng request.

Ví dụ, không làm như sau:

~~~java
@RestController
class ReportController {

    private final ObjectMapper mapper;

    ReportController(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @GetMapping("/report")
    String report() throws JsonProcessingException {
        mapper.enable(SerializationFeature.INDENT_OUTPUT);
        return mapper.writeValueAsString(loadReport());
    }
}
~~~

Nếu request khác cũng dùng mapper này, behavior của chúng có thể bị ảnh hưởng bởi request report. Một request không nên thay đổi policy serialize của toàn ứng dụng.

## 4. Cấu hình mapper ngay trong Spring startup

Với Spring Boot sử dụng Jackson 2, có thể cấu hình mapper thông qua cơ chế auto-configuration và builder customizer.

Ví dụ dùng Jackson2ObjectMapperBuilderCustomizer:

~~~java
@Configuration
class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.propertyNamingStrategy(
                PropertyNamingStrategies.SNAKE_CASE
            );

            builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            );

            builder.featuresToDisable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
            );
        };
    }
}
~~~

Customizer được áp dụng khi Spring xây dựng mapper. Các bean sử dụng ObjectMapper sau đó nhận cùng policy đã được cấu hình.

API cụ thể phụ thuộc phiên bản Spring Boot và Jackson line. Ví dụ trên minh họa Spring Boot stack dùng Jackson 2; nếu dự án đã chuyển sang Jackson 3 hoặc Spring Boot major line mới, dùng builder/customizer API tương ứng của phiên bản đó.

### 4.1. Ưu tiên tùy chỉnh builder do Spring quản lý

Spring Boot có thể tự đăng ký module và áp dụng cấu hình từ application properties. Khi chỉ cần thay một vài feature, customizer giúp giữ lại cấu hình auto-configured hiện có.

Ví dụ:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
    serialization:
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: false
~~~

Các property hỗ trợ cụ thể phụ thuộc phiên bản Spring Boot. Hãy kiểm tra cấu hình của release line dự án đang dùng.

Không cần tạo một ObjectMapper mới chỉ để bật một feature mà Spring Boot đã hỗ trợ qua properties hoặc builder customizer.

### 4.2. Tránh vô tình thay thế mapper auto-configured

Ví dụ dễ gây lệch cấu hình:

~~~java
@Bean
ObjectMapper objectMapper() {
    return new ObjectMapper();
}
~~~

Khai báo bean như vậy có thể khiến Spring Boot không dùng mapper auto-configured của nó. Mapper mới có thể thiếu module, naming strategy hoặc customizer mà ứng dụng vốn dựa vào.

Nếu cần định nghĩa mapper riêng, phải quyết định rõ nó thay thế mapper mặc định hay phục vụ một format/policy độc lập. Nếu muốn giữ các module và setting của Spring, xây dựng từ builder/configuration của Spring thay vì khởi tạo một mapper trần.

### 4.3. Khi nào cần một ObjectMapper bean tường minh?

Có thể cần bean riêng khi:

- Ứng dụng có JSON contract độc lập với cấu hình mặc định.
- Cần một mapper cho YAML, CBOR hoặc Smile.
- Một integration boundary cần strict coercion riêng.
- Một subsystem cần naming strategy hoặc annotation mix-in riêng.
- Cần cấu hình serializer/deserializer nội bộ.

Trong trường hợp đó, đặt tên bean rõ ràng và inject đúng qualifier để tránh thành phần vô tình dùng nhầm mapper.

~~~java
@Bean("externalApiMapper")
ObjectMapper externalApiMapper(
        Jackson2ObjectMapperBuilder builder) {
    return builder
        .featuresToDisable(
            DeserializationFeature.ACCEPT_FLOAT_AS_INT
        )
        .build();
}
~~~

Đây là ví dụ cho Spring Boot/Jackson 2. Kiểm tra builder API của phiên bản dự án. Bean riêng nên được cấu hình hoàn chỉnh trước khi đưa vào controller hoặc converter.

## 5. Dùng ObjectReader cho policy đọc riêng

ObjectReader là đối tượng cấu hình đọc bất biến. Các method with()/without() không sửa mapper gốc; chúng trả về reader mới với policy tương ứng.

Ví dụ mapper mặc định strict với unknown property, nhưng một integration legacy cần bỏ qua field mới:

~~~java
ObjectReader strictReader =
    mapper.readerFor(PartnerMessage.class);

ObjectReader legacyReader = mapper
    .readerFor(PartnerMessage.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Sử dụng:

~~~java
PartnerMessage strictMessage =
    strictReader.readValue(strictJson);

PartnerMessage legacyMessage =
    legacyReader.readValue(legacyJson);
~~~

Mapper dùng chung không bị thay đổi. Hai reader có thể được tái sử dụng đồng thời.

### 5.1. Reader theo target type

~~~java
ObjectReader userReader = mapper.readerFor(UserDto.class);
ObjectReader orderReader = mapper.readerFor(OrderDto.class);
~~~

Reader có target type rõ ràng giúp giảm việc lặp lại class argument và thể hiện contract của operation.

Với generic type:

~~~java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, UserDto.class);

ObjectReader responseReader = mapper.readerFor(responseType);
~~~

### 5.2. Reader với feature riêng

~~~java
ObjectReader strictNumberReader = mapper
    .readerFor(QuantityRequest.class)
    .without(DeserializationFeature.ACCEPT_FLOAT_AS_INT);
~~~

Có thể tạo reader khác cho payload legacy nếu policy được xác định trước:

~~~java
ObjectReader compatibleReader = mapper
    .readerFor(QuantityRequest.class)
    .with(DeserializationFeature.ACCEPT_FLOAT_AS_INT);
~~~

Chỉ dùng coercion phù hợp hợp đồng. Việc reader có policy riêng không có nghĩa nên chấp nhận mọi dạng input; hãy xác định rõ vì sao một integration cần behavior đó.

### 5.3. Reader với context attributes

Một số serializer/deserializer cần ngữ cảnh theo operation. Có thể truyền attribute vào reader:

~~~java
ObjectReader reader = mapper
    .readerFor(Document.class)
    .withAttribute("sourceSystem", "partner-a");
~~~

Custom deserializer có thể đọc attribute qua DeserializationContext khi cần. Attribute phải là dữ liệu context cho operation, không phải cách lưu trạng thái mutable dùng chung bên trong deserializer.

## 6. Dùng ObjectWriter cho policy ghi riêng

ObjectWriter cũng là đối tượng cấu hình bất biến. Nếu một endpoint cần pretty print để tải file, trong khi response API thông thường cần JSON compact, tạo hai writer:

~~~java
ObjectWriter compactWriter =
    mapper.writerFor(Report.class);

ObjectWriter prettyWriter = mapper
    .writerFor(Report.class)
    .with(SerializationFeature.INDENT_OUTPUT);
~~~

Sử dụng:

~~~java
String apiJson = compactWriter.writeValueAsString(report);
String downloadJson = prettyWriter.writeValueAsString(report);
~~~

Không gọi mapper.enable(INDENT_OUTPUT) trong endpoint download. Writer riêng giữ policy của operation và không ảnh hưởng request khác.

### 6.1. Writer theo view

Nếu ứng dụng dùng JSON Views:

~~~java
ObjectWriter publicWriter = mapper
    .writerWithView(PublicView.class);

ObjectWriter internalWriter = mapper
    .writerWithView(InternalView.class);
~~~

Các writer có thể dùng chung mapper nhưng phát ra các tập property khác nhau theo view. View không thay thế authorization; service vẫn phải xác định người gọi được phép nhận dữ liệu nào.

### 6.2. Writer với filter hoặc root type

ObjectWriter có thể giữ cấu hình theo operation như filter provider, root type hoặc attributes. Điều này giúp tránh sửa global mapper chỉ để phục vụ một kiểu output.

Nếu filter provider hoặc custom object được truyền vào writer có trạng thái mutable, chính object đó cũng cần an toàn khi được dùng đồng thời. Reader/Writer bất biến không tự làm mọi collaborator trở nên thread-safe.

## 7. Vì sao không nên thay đổi mapper theo từng request?

Một anti-pattern thường gặp là đọc header hoặc tenant ID rồi đổi cấu hình mapper trước khi deserialize:

~~~java
// Không làm: mapper là bean dùng chung.
if (request.isLegacyClient()) {
    mapper.enable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
} else {
    mapper.disable(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
}

return mapper.readValue(body, RequestDto.class);
~~~

Hai request có thể chạy đồng thời. Request A bật feature, request B tắt feature. Một request có thể bị deserialize theo policy của request còn lại.

Cách phù hợp:

~~~java
ObjectReader modernReader = mapper
    .readerFor(RequestDto.class)
    .without(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);

ObjectReader legacyReader = mapper
    .readerFor(RequestDto.class)
    .with(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);

RequestDto dto = request.isLegacyClient()
    ? legacyReader.readValue(body)
    : modernReader.readValue(body);
~~~

Các reader được tạo trước hoặc tạo theo operation từ mapper đã cấu hình. Không có thao tác mutate global mapper.

### 7.1. Chọn policy ở ranh giới tích hợp

Nếu một đối tác có payload legacy, policy compatible nên nằm trong adapter của đối tác đó. Không bật coercion rộng cho toàn bộ ứng dụng chỉ vì một client cũ.

~~~text
External API A
    -> strict ObjectReader
External API B (legacy)
    -> compatibility ObjectReader
Internal event
    -> event ObjectReader
             |
             v
       shared configured mapper
~~~

Cách này giữ behavior khác nhau tại đúng boundary, dễ review và dễ loại bỏ khi client legacy ngừng hoạt động.

## 8. ObjectMapper.copy() và mapper riêng

Khi hai subsystem cần cấu hình nền khác nhau, có thể tạo mapper riêng. ObjectMapper.copy() tạo bản sao cấu hình của mapper hiện tại:

~~~java
ObjectMapper partnerMapper = mapper.copy();

partnerMapper.setPropertyNamingStrategy(
    PropertyNamingStrategies.KEBAB_CASE
);
~~~

Hãy tạo và cấu hình bản sao trước khi đưa nó vào sử dụng. Không mutate bản sao sau khi đã bắt đầu phục vụ request của subsystem đó.

copy() không phải thao tác rẻ để gọi mỗi request. Nó tạo một mapper mới và sao chép cấu hình; tài liệu Jackson lưu ý chi phí có thể tương đương tạo mapper mới. Hãy dùng khi thật sự cần một mapper độc lập, không dùng thay cho ObjectReader/ObjectWriter.

### 8.1. Khi nào dùng reader/writer, khi nào dùng mapper riêng?

| Nhu cầu | Lựa chọn |
|---|---|
| Cùng serializer/module, khác một vài feature đọc | ObjectReader riêng |
| Cùng mapper, khác pretty print hoặc view | ObjectWriter riêng |
| Khác target type | readerFor()/writerFor() |
| Khác context cho một operation | Reader/Writer attributes |
| Khác module, mix-in hoặc naming strategy nền | Mapper riêng |
| Khác JsonFactory/format như JSON và CBOR | Mapper riêng với factory tương ứng |
| Policy bảo mật khác hẳn ở trust boundary | Mapper riêng được cấu hình từ đầu |

Đừng tạo mapper mới cho từng DTO chỉ vì các DTO khác nhau. ObjectReader/ObjectWriter được thiết kế để tái sử dụng cùng mapper cho nhiều target type.

## 9. Nhiều định dạng cần nhiều mapper/factory riêng

Một ứng dụng có thể xử lý JSON, YAML, CBOR và Smile. Không nên đổi factory hoặc cấu hình mapper dùng chung tùy theo Content-Type của request.

Thay vào đó, tạo mapper riêng:

~~~java
@Bean
@Qualifier("jsonMapper")
ObjectMapper jsonMapper() {
    return JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
}

@Bean
@Qualifier("yamlMapper")
YAMLMapper yamlMapper() {
    return new YAMLMapper()
        .registerModule(new JavaTimeModule());
}

@Bean
@Qualifier("cborMapper")
ObjectMapper cborMapper() {
    return new ObjectMapper(new CBORFactory())
        .registerModule(new JavaTimeModule());
}
~~~

Ví dụ trên minh họa ý tưởng. Trong ứng dụng thực tế, nên áp dụng cùng chính sách module/feature cần thiết cho từng mapper, dùng đúng builder API của version và tránh gọi cấu hình sau khi bean đã được sử dụng.

Inject đúng mapper:

~~~java
class BinaryMessageWriter {

    private final ObjectMapper cborMapper;

    BinaryMessageWriter(
            @Qualifier("cborMapper") ObjectMapper cborMapper) {
        this.cborMapper = cborMapper;
    }
}
~~~

Một mapper không nên được tái sử dụng cho nhiều format bằng cách thay JsonFactory sau khi đã hoạt động. Factory là một phần của cách mapper parse/generate dữ liệu.

## 10. Custom serializer và deserializer cũng phải an toàn đồng thời

Ngay cả khi ObjectMapper không bị mutate, custom serializer/deserializer có thể chứa state mutable và gây race condition.

Jackson thường cache và tái sử dụng serializer/deserializer. Vì vậy, không nên lưu dữ liệu của request hiện tại vào field của serializer.

Ví dụ không an toàn:

~~~java
public class UserSerializer extends JsonSerializer<User> {

    private String currentTenant;

    @Override
    public void serialize(
            User value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        currentTenant = TenantContext.currentTenant();

        generator.writeStartObject();
        generator.writeStringField("tenant", currentTenant);
        generator.writeStringField("name", value.name());
        generator.writeEndObject();
    }
}
~~~

Nếu hai thread serialize đồng thời, currentTenant có thể bị ghi đè giữa các lần gọi.

Tốt hơn là lấy dữ liệu theo operation từ context hoặc truyền vào model/DTO:

~~~java
public class UserSerializer extends JsonSerializer<User> {

    @Override
    public void serialize(
            User value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        String tenant = TenantContext.currentTenant();

        generator.writeStartObject();
        generator.writeStringField("tenant", tenant);
        generator.writeStringField("name", value.name());
        generator.writeEndObject();
    }
}
~~~

Ví dụ này giả định TenantContext được triển khai an toàn theo request/thread hoặc context propagation phù hợp với runtime. Trong reactive execution, không nên dựa vào ThreadLocal nếu context có thể chuyển thread; dùng context mechanism của framework hoặc truyền dữ liệu rõ ràng.

### 10.1. Không giữ JsonParser/JsonGenerator hoặc request state trong serializer

Serializer/deserializer không nên lưu các đối tượng operation-specific vào field:

- JsonParser hoặc JsonGenerator của request.
- DTO đang được serialize.
- Request header hoặc user identity.
- Buffer tạm dùng chung.
- Collection đang được xây dựng cho một request.
- Mutable DateFormat hoặc NumberFormat không an toàn khi dùng chung.

Tạo state cục bộ trong method, dùng immutable formatter hoặc API context phù hợp.

### 10.2. Contextual serializer/deserializer

Khi behavior phụ thuộc annotation/property, dùng ContextualSerializer hoặc ContextualDeserializer. Jackson có thể tạo instance chuyên biệt theo property trong quá trình contextualization.

Instance contextual nên giữ cấu hình bất biến, ví dụ một format pattern hoặc flag đã đọc từ annotation. Không lưu state của lần serialize/deserialize vào đó.

Nếu serializer dùng formatter, chọn formatter thread-safe như DateTimeFormatter hoặc tạo formatter riêng theo operation nếu formatter mutable.

### 10.3. Module và serializer registration

Đăng ký module, serializer và deserializer trước khi mapper được sử dụng:

~~~java
SimpleModule module = new SimpleModule();

module.addSerializer(Money.class, new MoneySerializer());
module.addDeserializer(Money.class, new MoneyDeserializer());

ObjectMapper mapper = JsonMapper.builder()
    .addModule(module)
    .build();
~~~

Không gọi registerModule() trong một service method sau khi mapper đã được dùng. Module registration là cấu hình mapper, không phải request-level operation.

## 11. Mapper configuration và cache

Jackson sử dụng cache để giảm chi phí tìm serializer/deserializer và xây dựng type metadata. Cấu hình mapper trước khi dùng giúp cache được tạo dựa trên policy ổn định.

Nếu thay đổi naming strategy, mix-in, visibility hoặc module sau khi đã có operation, có thể xảy ra tình huống cache và policy không còn tương ứng với kỳ vọng của ứng dụng.

Không cần tự quản lý hoặc xóa cache trong code nghiệp vụ để cố sửa vấn đề này. Hãy tạo mapper mới với cấu hình mong muốn, hoặc dùng reader/writer cho những khác biệt được hỗ trợ ở cấp operation.

Một lý do khác để không mutate mapper là behavior có thể khó xác định khi nhiều framework component giữ reference đến cùng instance. Chỉ một bean ObjectMapper có thể được dùng bởi MVC converter, message converter, service hoặc thư viện khác.

## 12. Cấu hình riêng theo trust boundary

Không phải mọi nguồn JSON đều đáng tin như nhau. API công khai, message nội bộ, file import và payload từ đối tác có thể cần chính sách khác nhau.

Ví dụ:

- Public endpoint: strict coercion, giới hạn kiểu và unknown subtype.
- Legacy partner: chấp nhận một số dạng cũ đã được xác định.
- Internal event: reader theo event type và schema version.
- File cấu hình: strict unknown property để phát hiện typo.
- Admin export: writer pretty print hoặc view riêng.

Có thể dùng cùng một mapper nền nếu khác biệt chỉ nằm trong những feature reader/writer hỗ trợ. Nếu trust boundary cần khác biệt lớn như module, subtype validator hoặc annotation introspector, dùng mapper riêng.

Không bật default typing rộng trên mapper dùng chung để phục vụ một integration. Polymorphic typing có tác động bảo mật và cần cấu hình allowlist rõ ràng trước khi mapper được công bố.

## 13. Cấu hình ObjectMapper qua constructor hoặc factory

Một factory giúp gom toàn bộ policy vào một nơi:

~~~java
public final class MapperFactory {

    private MapperFactory() {
    }

    public static ObjectMapper createApiMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .addModule(new Jdk8Module())
            .propertyNamingStrategy(
                PropertyNamingStrategies.SNAKE_CASE
            )
            .serializationInclusion(
                JsonInclude.Include.NON_NULL
            )
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
            .build();
    }
}
~~~

Trong Spring:

~~~java
@Configuration
class ApiMapperConfiguration {

    @Bean
    @Qualifier("apiMapper")
    ObjectMapper apiMapper() {
        return MapperFactory.createApiMapper();
    }
}
~~~

Factory tạo mapper hoàn chỉnh. Các bean inject apiMapper chỉ sử dụng mapper đó; không gọi setter để thay policy sau startup.

Nếu Spring Boot đã cung cấp mapper auto-configured và ứng dụng chỉ cần thay một vài setting, customizer thường là lựa chọn phù hợp hơn factory độc lập. Factory riêng phù hợp khi thực sự cần mapper có contract riêng.

## 14. Những thao tác nên tránh trong controller/service

Các thao tác sau không nên xuất hiện trong luồng xử lý request đối với mapper dùng chung:

~~~java
mapper.registerModule(...);
mapper.setPropertyNamingStrategy(...);
mapper.setDateFormat(...);
mapper.addMixIn(...);
mapper.setVisibility(...);
mapper.enable(...);
mapper.disable(...);
mapper.activateDefaultTyping(...);
~~~

Chúng đều thay đổi cấu hình hoặc behavior của mapper.

Một service nên nhận mapper/reader/writer đã được cấu hình:

~~~java
@Service
class PartnerPayloadService {

    private final ObjectReader reader;
    private final ObjectWriter writer;

    PartnerPayloadService(
            @Qualifier("partnerMapper") ObjectMapper mapper) {
        this.reader = mapper.readerFor(PartnerPayload.class);
        this.writer = mapper.writerFor(PartnerPayload.class);
    }

    PartnerPayload read(String json) throws IOException {
        return reader.readValue(json);
    }

    String write(PartnerPayload payload) throws JsonProcessingException {
        return writer.writeValueAsString(payload);
    }
}
~~~

Reader/writer được tạo một lần trong constructor và tái sử dụng. Không cần giữ mapper nếu service chỉ cần hai operation này.

## 15. Khi cần cấu hình runtime thay đổi thì làm thế nào?

Một số ứng dụng có yêu cầu cấu hình thay đổi khi chạy, ví dụ tenant có naming policy hoặc một schema version mới. Điều đó không có nghĩa nên mutate mapper đang phục vụ.

### 15.1. Chọn reader/writer đã được chuẩn bị trước

Nếu tập policy hữu hạn, tạo trước các reader/writer:

~~~java
final class PayloadReaders {

    private final ObjectReader strict;
    private final ObjectReader legacy;

    PayloadReaders(ObjectMapper mapper) {
        strict = mapper.readerFor(PartnerPayload.class)
            .without(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);

        legacy = mapper.readerFor(PartnerPayload.class)
            .with(DeserializationFeature.ACCEPT_SINGLE_VALUE_AS_ARRAY);
    }

    ObjectReader forLegacyClient(boolean legacyClient) {
        return legacyClient ? legacy : strict;
    }
}
~~~

Request chọn reader theo client/version. Mapper gốc không thay đổi.

### 15.2. Tạo mapper mới rồi thay thế snapshot

Nếu thay đổi thực sự đòi hỏi mapper nền khác, xây dựng mapper mới hoàn chỉnh, kiểm tra cấu hình rồi công bố instance mới thông qua một provider/registry an toàn. Các request đang giữ reference cũ có thể hoàn tất với mapper cũ; request mới lấy mapper mới.

Ví dụ ý tưởng:

~~~java
@Component
final class MapperRegistry {

    private final AtomicReference<ObjectMapper> current;

    MapperRegistry(ObjectMapper initialMapper) {
        this.current = new AtomicReference<>(initialMapper);
    }

    ObjectMapper current() {
        return current.get();
    }

    void replace(ObjectMapper fullyConfiguredMapper) {
        current.set(Objects.requireNonNull(fullyConfiguredMapper));
    }
}
~~~

Chỉ publish mapper đã cấu hình xong. Không trả ra một mapper đang được chỉnh sửa dở dang. Các consumer cần lấy snapshot từ registry tại thời điểm bắt đầu operation thay vì giữ mapper cũ mãi mãi.

Cách này có độ phức tạp vận hành cao hơn. Nếu thay đổi cấu hình không thường xuyên, restart/redeploy ứng dụng với cấu hình mới thường đơn giản và dễ kiểm soát hơn.

## 16. ObjectReader/ObjectWriter không thay thế mapper riêng trong mọi trường hợp

Reader/writer phù hợp với các tùy chọn ở cấp operation. Chúng không thể biến một JSON mapper thành CBOR mapper hoặc thêm module mới vào mapper nền mà không thay đổi cấu trúc serializer/deserializer.

Nếu cần khác biệt như:

- Khác JsonFactory hoặc format.
- Khác module.
- Khác mix-in/annotation introspector.
- Khác subtype validator hoặc polymorphic typing policy.
- Khác visibility hoặc serializer registration.

thì tạo mapper riêng và cấu hình trước khi sử dụng.

Không cố nhồi mọi trust boundary vào một mapper rồi dùng một loạt feature flag mutable. Mapper riêng với tên và qualifier rõ ràng giúp policy dễ review hơn.

## 17. Tích hợp với Spring MVC và message converter

Spring MVC thường dùng HttpMessageConverter để đọc request body và ghi response body. Jackson converter giữ một ObjectMapper. Nếu mapper bị thay đổi sau khi converter được tạo, converter và các thành phần khác vẫn tham chiếu cùng instance mutable.

Cấu hình mapper nên hoàn tất trước khi converter bắt đầu xử lý request.

Nếu cần converter riêng cho một media type hoặc DTO boundary, cấu hình mapper riêng:

~~~java
@Bean
MappingJackson2HttpMessageConverter partnerJsonConverter(
        @Qualifier("partnerMapper") ObjectMapper partnerMapper) {

    return new MappingJackson2HttpMessageConverter(partnerMapper);
}
~~~

Đây là ví dụ cho Spring MVC với Jackson 2. API converter có thể khác nếu framework hoặc Jackson major line thay đổi.

Không thay đổi mapper bên trong converter theo từng request. Nếu cần strict/legacy policy theo endpoint, dùng converter/reader phù hợp được cấu hình sẵn hoặc xử lý ở adapter boundary.

### 17.1. WebFlux và codec

Spring WebFlux dùng codec thay vì MVC HttpMessageConverter theo cùng cách. Cấu hình Jackson decoder/encoder cũng cần được thực hiện trong startup configuration.

Không giả định cấu hình MVC tự động áp dụng cho WebFlux. Kiểm tra codec thực tế được đăng ký và mapper mà codec giữ.

### 17.2. Kiểm tra mapper thực tế trong application context

Một test application context có thể xác nhận bean được inject là mapper dự kiến và có module/feature cần thiết:

~~~java
@SpringBootTest
class JacksonConfigurationTest {

    @Autowired
    ObjectMapper mapper;

    @Test
    void applicationMapperHasExpectedConfiguration() {
        assertFalse(
            mapper.isEnabled(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            )
        );
    }
}
~~~

Assertion trên chỉ là ví dụ cho một feature. Nên kiểm tra contract cần thiết thay vì truy cập implementation detail không ổn định. Nếu có nhiều mapper bean, inject bằng @Qualifier.

## 18. Kiểm thử concurrency khi tái sử dụng mapper

Vì mapper được dùng đồng thời, có thể kiểm tra các operation độc lập với cùng mapper sau khi cấu hình xong.

Ví dụ JUnit:

~~~java
@Test
void sharedConfiguredMapperSupportsConcurrentOperations() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

    ExecutorService executor = Executors.newFixedThreadPool(8);

    try {
        List<Callable<UserDto>> tasks = IntStream.range(0, 100)
            .mapToObj(index -> (Callable<UserDto>) () -> {
                UserDto source = new UserDto(index, "user-" + index);

                String json = mapper.writeValueAsString(source);

                return mapper.readValue(json, UserDto.class);
            })
            .toList();

        List<Future<UserDto>> results = executor.invokeAll(tasks);

        for (int index = 0; index < results.size(); index++) {
            UserDto result = results.get(index).get();

            assertEquals(index, result.id());
            assertEquals("user-" + index, result.name());
        }
    } finally {
        executor.shutdown();
    }
}
~~~

Test này minh họa việc tái sử dụng mapper đã cấu hình. Nó không chứng minh mọi custom serializer trong ứng dụng đều thread-safe; các extension tự viết cần được kiểm tra riêng.

Không viết test cố tình mutate mapper trong lúc request đang chạy để hợp thức hóa behavior đó. Mục tiêu là giữ cấu hình ổn định, không phải tìm ra một race condition có thể tái hiện.

## 19. Kiểm thử ObjectReader/ObjectWriter độc lập

Có thể xác nhận hai reader dùng policy khác nhau mà không ảnh hưởng nhau:

~~~java
@Test
void readersCanHaveDifferentPoliciesWithoutMutatingMapper() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    ObjectReader strict = mapper.readerFor(UserDto.class);

    ObjectReader tolerant = mapper
        .readerFor(UserDto.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    String json = """
        {
          "id": 1,
          "name": "An",
          "extra": true
        }
        """;

    assertThrows(JsonProcessingException.class, () ->
        strict.readValue(json)
    );

    UserDto user = tolerant.readValue(json);

    assertEquals("An", user.name());
}
~~~

Tương tự writer:

~~~java
@Test
void writersCanUseDifferentOutputStyles() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    ObjectWriter compact = mapper.writerFor(UserDto.class);

    ObjectWriter pretty = mapper
        .writerFor(UserDto.class)
        .with(SerializationFeature.INDENT_OUTPUT);

    UserDto user = new UserDto(1, "An");

    String compactJson = compact.writeValueAsString(user);
    String prettyJson = pretty.writeValueAsString(user);

    assertFalse(compactJson.contains("\n"));
    assertTrue(prettyJson.contains("\n"));
}
~~~

Test xác nhận operation-level configuration. Mapper vẫn giữ cấu hình nền ban đầu.

## 20. Test custom serializer không giữ state giữa các request

Nếu serializer/deserializer có logic context, hãy test hai operation liên tiếp hoặc đồng thời với hai context khác nhau.

Không giữ request ID, tenant hoặc locale trong field mutable của serializer. Thay vào đó:

- Truyền dữ liệu vào DTO nếu đó là dữ liệu domain.
- Dùng ContextAttributes/InjectableValues theo operation nếu phù hợp.
- Dùng context propagation đúng framework.
- Tạo contextual serializer bất biến theo property.
- Tránh singleton mutable collaborator.

Một test concurrency chỉ hữu ích nếu nó kiểm tra được extension cụ thể. Đừng giả định Jackson core có thread-safe nghĩa là custom code đăng ký vào mapper cũng tự động an toàn.

## 21. Các vấn đề với mutable collaborator

Ngay cả khi mapper không bị mutate, một số object cấu hình hoặc extension được đăng ký có thể mutable:

| Collaborator | Rủi ro | Cách xử lý |
|---|---|---|
| Custom serializer | Field mutable lưu state request | Dùng local variable và immutable config |
| Custom deserializer | Giữ parser/request state | Không giữ state giữa các lần gọi |
| DateFormat tùy chỉnh | Có thể không thread-safe | Dùng formatter thread-safe hoặc clone/copy theo operation |
| FilterProvider | Thay đổi filter map trong runtime | Chuẩn bị trước hoặc tạo writer riêng |
| InjectableValues | Chứa state thay đổi theo request | Dùng instance theo reader/operation |
| Context attributes | Có thể chứa object mutable | Dùng value immutable hoặc scope đúng |
| Module | Đăng ký serializer/deserializer | Đăng ký trước khi mapper được dùng |
| Subtype resolver | Danh sách subtype mutable | Cấu hình allowlist trước startup |

Không chỉ xem ObjectMapper; hãy xem mọi object mà mapper hoặc serializer giữ reference.

## 22. Quản lý nhiều mapper trong ứng dụng lớn

Khi có nhiều contract, nên đặt tên bean theo boundary/format:

~~~java
@Configuration
class MappingConfiguration {

    @Bean("publicApiMapper")
    ObjectMapper publicApiMapper() {
        return createPublicApiMapper();
    }

    @Bean("legacyPartnerMapper")
    ObjectMapper legacyPartnerMapper() {
        return createLegacyPartnerMapper();
    }

    @Bean("eventCborMapper")
    ObjectMapper eventCborMapper() {
        return createEventCborMapper();
    }
}
~~~

Mỗi factory tạo mapper hoàn chỉnh. Service inject đúng mapper bằng qualifier:

~~~java
PartnerService(
    @Qualifier("legacyPartnerMapper") ObjectMapper mapper
) {
    this.reader = mapper.readerFor(PartnerPayload.class);
}
~~~

Tránh đặt tên chung chung như mapper1, mapper2. Tên bean nên nói rõ contract, format hoặc trust boundary.

Nếu hai mapper chỉ khác một feature nhỏ theo operation, reader/writer thường đủ và ít tốn công quản lý hơn nhiều mapper độc lập.

## 23. Logging và quan sát cấu hình

Khi điều tra lỗi JSON, cần biết mapper nào đang xử lý payload và policy nào được áp dụng. Không nên log toàn bộ object mapper hoặc payload nhạy cảm.

Có thể log:

- Tên boundary/mapper bean.
- Schema version hoặc event type.
- Content-Type.
- Correlation ID.
- Kích thước payload.
- Loại lỗi mapping và property path.
- Build/version ứng dụng.

Không log token, password hoặc toàn bộ body nếu chứa dữ liệu nhạy cảm.

Nếu có nhiều mapper, một log tag như mapper=legacyPartnerMapper giúp xác định policy được dùng mà không cần in mọi cấu hình nội bộ.

## 24. Quy trình thay đổi cấu hình mapper an toàn

Khi cần thay đổi naming strategy, module hoặc coercion policy:

1. Xác định contract nào cần thay đổi.
2. Kiểm tra thành phần nào đang inject mapper dùng chung.
3. Quyết định thay đổi là global hay chỉ thuộc một operation/boundary.
4. Nếu là operation-level, tạo ObjectReader/ObjectWriter riêng.
5. Nếu là mapper-level, cập nhật factory/builder hoặc Spring startup customizer.
6. Khởi động ứng dụng với mapper mới đã cấu hình hoàn chỉnh.
7. Chạy contract tests cho request/response liên quan.
8. Kiểm tra MVC converter/WebFlux codec và message adapter.
9. Triển khai ứng dụng để mọi bean cùng dùng cấu hình mới.
10. Theo dõi lỗi binding và serialization sau deploy.

Không dùng một endpoint admin để gọi setter trên mapper hiện đang phục vụ traffic. Nếu cần thay policy runtime, tạo snapshot mapper mới và thay provider reference theo cơ chế thread-safe, hoặc triển khai/restart với cấu hình mới.

## 25. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi mapper.enable()/disable() trong controller | Thay đổi policy dùng chung theo request | Dùng ObjectReader/ObjectWriter |
| registerModule() sau khi app chạy | Cấu hình mapper bị thay đổi muộn | Đăng ký module trong bean factory |
| Thay naming strategy trong service | Các request có thể dùng policy khác nhau | Tạo mapper riêng hoặc cấu hình startup |
| Tạo mapper mới trong mỗi request | Mất lợi ích reuse và cache | Tái sử dụng mapper đã cấu hình |
| Tạo ObjectMapper trần trong Spring Boot | Bỏ qua module/customizer auto-config | Dùng builder/customizer hoặc cấu hình rõ bean |
| Dùng một mapper cho JSON và CBOR | Factory không phù hợp với format | Tạo mapper riêng theo factory |
| Cho rằng ObjectReader thay thế được module | Reader không thay đổi cấu trúc mapper nền | Tạo mapper riêng khi cần module/factory khác |
| Serializer lưu tenant/request trong field | Serializer có thể được tái sử dụng đồng thời | Dùng context hoặc biến cục bộ |
| DateFormat mutable được dùng chung | Formatter có thể không thread-safe | Dùng formatter an toàn hoặc scope riêng |
| Mutate FilterProvider dùng chung | Writer khác có thể thấy thay đổi | Chuẩn bị filter trước hoặc writer riêng |
| Test chỉ dùng mapper tự tạo | Không phản ánh mapper Spring thực tế | Test application context và converter |
| Cấu hình trong ApplicationRunner | Mapper có thể đã được bean khác sử dụng | Cấu hình khi tạo bean |
| Hot reload bằng setter | Race condition và cache behavior khó đoán | Tạo snapshot mapper mới rồi thay reference |
| Coi test concurrency pass là bảo đảm tuyệt đối | Custom extension vẫn có thể mutable | Review serializer/deserializer và collaborator |

## 26. Checklist triển khai trong Spring

### Giai đoạn startup

- Tạo mapper từ builder hoặc factory.
- Đăng ký module cần thiết.
- Cấu hình naming strategy, inclusion và date/time.
- Cấu hình coercion và unknown property policy.
- Cấu hình mix-in, subtype và security validator.
- Xác nhận mapper được inject đúng vào converter/codec.
- Không để bean khác mutate mapper sau startup.

### Trong request processing

- Chỉ dùng mapper đã cấu hình.
- Dùng reader/writer theo operation khi cần policy riêng.
- Không gọi setter, enable, disable hoặc registerModule.
- Không giữ request state trong custom serializer/deserializer.
- Không thay đổi filter/module dùng chung.
- Xác định rõ mapper theo trust boundary và content type.

### Khi nâng cấp hoặc đổi policy

- Sửa startup configuration.
- Chạy contract và integration test.
- Kiểm tra nhiều mapper/qualifier.
- Xác nhận module version tương thích.
- Deploy snapshot cấu hình mới.
- Theo dõi lỗi serialization/deserialization.

## 27. Nguyên tắc nên giữ

- ObjectMapper có thể được dùng đồng thời khi đã cấu hình hoàn chỉnh trước lần sử dụng đầu tiên.
- Xem mapper được inject như một cấu hình ổn định sau startup.
- Không thay module, feature, naming strategy, mix-in hoặc visibility trên mapper đang phục vụ request.
- Không mutate mapper theo tenant, header hoặc request.
- Dùng ObjectReader cho policy đọc riêng và ObjectWriter cho policy ghi riêng.
- Reader/Writer trả về từ with()/without() là cấu hình operation mới, không sửa mapper gốc.
- Tạo mapper riêng khi cần factory, module, subtype policy hoặc cấu hình nền khác.
- Dùng Spring builder/customizer để giữ auto-configuration khi phù hợp.
- Không tạo mapper trần vô tình thay thế mapper Spring Boot đã cấu hình.
- Custom serializer/deserializer phải tránh state mutable dùng chung.
- Contextual serializer nên giữ cấu hình bất biến.
- Xác định thread-safety của mọi collaborator mà mapper sử dụng.
- Nếu cần reload, tạo mapper mới hoàn chỉnh rồi công bố snapshot mới.
- Kiểm thử mapper thực tế trong application context và adapter.
- Tái sử dụng mapper/reader/writer thay vì khởi tạo lại theo request.

Tránh thay đổi mapper dùng chung sau khi bắt đầu phục vụ giúp JSON contract ổn định giữa các request và thread. Spring có thể quản lý một mapper singleton, nhưng mapper đó cần được cấu hình đầy đủ ngay trong startup. Những khác biệt theo operation nên được biểu diễn bằng ObjectReader/ObjectWriter; những khác biệt về module, format hoặc trust boundary nên có mapper riêng. Khi custom serializer và các collaborator cũng không giữ state mutable, ứng dụng có thể tái sử dụng Jackson an toàn và dễ kiểm soát hơn.

