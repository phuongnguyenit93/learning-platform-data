# Phân biệt mapper tự tạo và mapper do ứng dụng Spring quản lý

Trong ứng dụng Spring, Jackson thường được dùng ở nhiều nơi: controller đọc request JSON, converter ghi response, service đọc message, job nạp file cấu hình và code nghiệp vụ chuyển đổi object. Vì vậy, lựa chọn ObjectMapper không chỉ ảnh hưởng đến một lời gọi readValue() hay writeValueAsString(); nó còn quyết định các thành phần trong ứng dụng có cùng hiểu một hợp đồng JSON hay không.

Một mapper được tạo bằng new ObjectMapper() có cấu hình mặc định của Jackson và những gì code tự đăng ký trực tiếp lên instance đó. Mapper do Spring Boot cấu hình thường được tạo từ cơ chế auto-configuration và builder của Spring, có thể nhận các property, Module bean, customizer và thiết lập mà ứng dụng đã khai báo. Nếu tự tạo mapper trong service hoặc controller, code có thể vô tình bỏ qua những thiết lập đang được dùng ở tầng HTTP.

**Nguyên tắc thực hành là tái sử dụng mapper do ứng dụng Spring cung cấp cho các luồng cần cùng chính sách serialization; tùy chỉnh mapper đó tại điểm cấu hình của Spring.** Chỉ tạo mapper riêng khi có một ranh giới dữ liệu thực sự cần chính sách khác, chẳng hạn YAML thay JSON, một định dạng legacy hoặc một nguồn dữ liệu có trust boundary riêng. Khi đó, hãy đặt tên bean rõ ràng, cấu hình đầy đủ và inject bằng qualifier.

Bài học này sử dụng ví dụ Spring Boot 3 với Jackson 2 để minh họa các API quen thuộc như ObjectMapper, Jackson2ObjectMapperBuilderCustomizer và MappingJackson2HttpMessageConverter. Tên lớp và cách tích hợp có thể thay đổi ở các major version mới, đặc biệt khi dự án chuyển sang Jackson 3; luôn đối chiếu với dependency và framework version thực tế của dự án.

## 1. ObjectMapper là gì trong ứng dụng Spring?

ObjectMapper là trung tâm databinding của Jackson. Nó phối hợp các thành phần để đọc JSON thành object Java và ghi object Java thành JSON. Cấu hình của mapper có thể bao gồm:

- Module cho các kiểu dữ liệu bổ sung như java.time, Optional hoặc kiểu từ thư viện khác.
- SerializationFeature và DeserializationFeature.
- Naming strategy, visibility và inclusion policy.
- Mix-in annotation và subtype registry.
- Custom serializer, deserializer, key serializer và key deserializer.
- Coercion rules, null handling và parser/generator configuration.
- Các cache serializer/deserializer và metadata đã phân giải.

Một ứng dụng Spring thường có một hoặc nhiều mapper với chính sách xác định. Spring quản lý vòng đời bean; Jackson cung cấp hành vi đọc/ghi và quy tắc thread-safety của mapper. Hai trách nhiệm này cần được phân biệt: Spring tạo và inject instance; Jackson quyết định cách instance xử lý dữ liệu.

Ví dụ một service nhận mapper qua constructor:

~~~java
@Service
public class OrderJsonService {
    private final ObjectMapper objectMapper;

    public OrderJsonService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderRequest parse(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, OrderRequest.class);
    }
}
~~~

Service không cần tự quyết định module, naming strategy hay feature. Nó dùng chính sách do composition root của ứng dụng cung cấp.

## 2. Mapper tự tạo bằng new ObjectMapper()

Đây là một cách tạo mapper độc lập:

~~~java
ObjectMapper mapper = new ObjectMapper();
~~~

Instance này được tạo trực tiếp từ Jackson. Nó không tự động trở thành bean trong Spring ApplicationContext và không tự nhận mọi cấu hình mà Spring Boot đang áp dụng cho mapper của ứng dụng.

Nếu code cần hỗ trợ java.time, có thể đăng ký module:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
~~~

Nếu cần naming strategy, inclusion policy hoặc custom serializer, code cũng phải tự cấu hình chúng trên instance này. Khi ứng dụng thêm module hoặc thay đổi policy ở cấu hình Spring, mapper được tạo thủ công trong service không tự cập nhật theo.

Mapper tự tạo không phải lúc nào cũng sai. Nó phù hợp khi cần một codec độc lập, một tool nhỏ không chạy trong Spring, một mapper chuyên biệt cho định dạng khác hoặc một chính sách serialization tách biệt có chủ ý. Vấn đề xuất hiện khi mapper riêng được tạo vô tình trong một luồng vốn phải tuân theo cấu hình chung của ứng dụng.

### 2.1. Anti-pattern: tạo mapper trong mỗi method

~~~java
@Service
public class OrderJsonService {
    public OrderRequest parse(String json) throws JsonProcessingException {
        ObjectMapper mapper = new ObjectMapper();
        return mapper.readValue(json, OrderRequest.class);
    }
}
~~~

Mỗi lần gọi, method lại tạo mapper mới. Điều này lặp chi phí khởi tạo, không tận dụng cache của instance dùng chung và làm cấu hình khó đồng nhất. Nếu một endpoint khác dùng mapper do Spring quản lý, hai đường xử lý có thể cho kết quả khác nhau với cùng JSON.

### 2.2. Mapper static tự tạo cũng có thể gây lệch cấu hình

~~~java
public final class JsonUtils {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonUtils() {
    }

    public static String toJson(Object value) throws JsonProcessingException {
        return MAPPER.writeValueAsString(value);
    }
}
~~~

Cách này tránh tạo mapper mỗi lần, nhưng vẫn tạo một mapper ngoài Spring. Nó có thể bỏ qua customizer, module bean và property mà ứng dụng đã cấu hình. Static mapper còn khó thay thế trong test và khó phân biệt chính sách cho từng trust boundary.

Nếu helper cần dùng cấu hình ứng dụng, hãy biến nó thành component nhận ObjectMapper qua constructor hoặc nhận ObjectWriter đã cấu hình. Không nên dùng static mapper mặc định chỉ vì tiện gọi.

## 3. Mapper do Spring Boot quản lý được hình thành như thế nào?

Khi các dependency Jackson phù hợp có trên classpath, Spring Boot có thể auto-configure Jackson integration. Trong các ứng dụng Spring Boot 3/Jackson 2 thông dụng, cơ chế này thường tạo ObjectMapper từ Jackson2ObjectMapperBuilder và cung cấp nó dưới dạng bean trong ApplicationContext.

Quá trình cấu hình có thể kết hợp:

- Các property thuộc nhóm spring.jackson.*.
- Module bean trong ApplicationContext.
- Jackson2ObjectMapperBuilderCustomizer.
- Các cấu hình và auto-configuration do framework cung cấp.
- Điều kiện auto-configuration, chẳng hạn việc ứng dụng đã khai báo bean tương ứng hay chưa.

Nhờ đó, mapper được inject vào service có thể dùng cùng module và policy đã được thiết lập cho ứng dụng. Trong Spring Boot, bean mặc định thường có scope singleton, nghĩa là các consumer nhận cùng một instance trừ khi ứng dụng định nghĩa thêm mapper hoặc qualifier khác.

Không nên giả định mọi phiên bản Spring đều tạo mapper theo cùng một chi tiết nội bộ. Hãy xem cấu hình auto-configuration của đúng phiên bản dự án nếu cần biết chính xác bean nào được tạo và converter nào đang dùng instance nào.

## 4. Inject mapper do Spring quản lý

Cách thông thường là constructor injection:

~~~java
@Service
public class CustomerJsonService {
    private final ObjectMapper mapper;

    public CustomerJsonService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public CustomerRequest read(String json) throws JsonProcessingException {
        return mapper.readValue(json, CustomerRequest.class);
    }

    public String write(CustomerResponse response) throws JsonProcessingException {
        return mapper.writeValueAsString(response);
    }
}
~~~

Lợi ích:

1. Service dùng mapper đã được cấu hình tại một điểm tập trung.
2. Dependency thể hiện rõ trong constructor, dễ kiểm thử và thay thế.
3. Không lặp module registration ở từng class.
4. Có thể kiểm soát mapper bằng Spring profile hoặc cấu hình ứng dụng.
5. Cùng một chính sách có thể được tái sử dụng bởi nhiều service.

Nếu chỉ cần một mapper chính, injection theo type thường đủ. Nếu có nhiều ObjectMapper bean, cần dùng @Qualifier để tránh Spring không biết phải inject instance nào.

## 5. Mapper được Spring quản lý không có nghĩa được phép thay đổi mãi mãi

ObjectMapper của Jackson được thiết kế để dùng đồng thời từ nhiều thread khi cấu hình đã hoàn tất trước khi bắt đầu đọc/ghi. Spring singleton bean giúp chia sẻ instance, nhưng không tự làm cho việc sửa cấu hình sau startup trở nên an toàn.

Không nên làm:

~~~java
@Service
public class ExportService {
    private final ObjectMapper mapper;

    public ExportService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String exportPretty(Object value) throws JsonProcessingException {
        mapper.enable(SerializationFeature.INDENT_OUTPUT);
        String json = mapper.writeValueAsString(value);
        mapper.disable(SerializationFeature.INDENT_OUTPUT);
        return json;
    }
}
~~~

Nếu hai request chạy đồng thời, một request có thể quan sát feature mà request kia vừa bật hoặc tắt. Output sẽ phụ thuộc thời điểm thực thi.

Hãy cấu hình mapper ở giai đoạn khởi động. Với một biến thể theo thao tác, dùng ObjectWriter hoặc ObjectReader:

~~~java
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();
ObjectWriter compactWriter = mapper.writer();

String pretty = prettyWriter.writeValueAsString(value);
String compact = compactWriter.writeValueAsString(value);
~~~

Reader/writer giữ cấu hình riêng mà không sửa mapper singleton. Custom serializer/deserializer cũng phải an toàn đồng thời; việc mapper thread-safe không tự làm component tùy biến có state mutable trở nên thread-safe.

## 6. Tùy chỉnh mapper Spring Boot bằng property

Với những thiết lập phổ biến, nên ưu tiên property cấu hình của Spring Boot thay vì tự tạo mapper mới.

Ví dụ application.yml:

~~~yaml
spring:
  jackson:
    serialization:
      indent-output: false
      write-dates-as-timestamps: false
    deserialization:
      fail-on-unknown-properties: true
    default-property-inclusion: non_null
~~~

Tên property và các feature được hỗ trợ phụ thuộc Spring Boot version. Hãy kiểm tra metadata/configuration reference của phiên bản dự án trước khi dùng một key cụ thể.

Các property phù hợp cho cấu hình đơn giản, khai báo và dễ thay đổi theo profile:

~~~yaml
# application-dev.yml
spring:
  jackson:
    serialization:
      indent-output: true
~~~

~~~yaml
# application-prod.yml
spring:
  jackson:
    serialization:
      indent-output: false
~~~

Cấu hình theo profile giúp phân biệt môi trường mà không cần service tự bật/tắt feature trên mapper dùng chung. Không đưa các giá trị do request gửi trực tiếp vào property cấu hình toàn cục.

## 7. Tùy chỉnh bằng Jackson2ObjectMapperBuilderCustomizer

Khi property không đủ diễn đạt hoặc cần cấu hình nâng cao, Spring Boot 3/Jackson 2 hỗ trợ customizer cho Jackson2ObjectMapperBuilder.

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    public Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.featuresToDisable(
                    SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            );

            builder.featuresToEnable(
                    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
            );
        };
    }
}
~~~

Customizer bổ sung cấu hình vào builder do Spring Boot quản lý. Cách này thường phù hợp hơn với việc khai báo một ObjectMapper hoàn toàn mới chỉ để đổi một feature, vì ứng dụng vẫn đi theo cơ chế cấu hình chung của framework.

Có thể đăng ký nhiều customizer, nhưng nên giữ chúng có mục đích rõ ràng và tránh cấu hình chồng chéo. Nếu hai customizer bật và tắt cùng một feature, kết quả có thể phụ thuộc thứ tự áp dụng. Tập trung policy liên quan vào một nơi hoặc đặt thứ tự rõ ràng khi thật sự cần.

API customizer trong ví dụ thuộc hệ sinh thái Jackson 2. Khi dự án chuyển sang Spring Boot/Jackson major version khác, tên lớp và cơ chế tích hợp có thể đổi; không sao chép import từ dự án cũ mà không kiểm tra dependency hiện tại.

## 8. Đăng ký Module bean thay vì đăng ký lặp trong từng service

Jackson module mở rộng khả năng serialization/deserialization cho kiểu dữ liệu. Với Spring Boot, có thể khai báo module như một bean để framework tích hợp vào quá trình cấu hình mapper theo phiên bản hỗ trợ.

Ví dụ một SimpleModule chứa serializer tùy biến:

~~~java
@Configuration
public class CustomJacksonModuleConfiguration {

    @Bean
    public Module domainModule() {
        SimpleModule module = new SimpleModule("domain-module");
        module.addSerializer(
                Money.class,
                new MoneySerializer()
        );
        module.addDeserializer(
                Money.class,
                new MoneyDeserializer()
        );
        return module;
    }
}
~~~

Các class MoneySerializer và MoneyDeserializer là implementation của ứng dụng. Bean Module được Spring quản lý và có thể được builder/auto-configuration tích hợp vào mapper theo cơ chế của Spring Boot version đang dùng.

Không gọi registerModule() trên mapper ở mỗi request. Không đăng ký cùng module ở nhiều nơi nếu không hiểu thứ tự và hành vi duplicate registration. Hãy xác định một điểm sở hữu module và kiểm thử mapper sau khi ApplicationContext khởi tạo.

### 8.1. Module bean có thể ảnh hưởng nhiều mapper

Trong một số cấu hình Spring Boot, Module bean được áp dụng cho các mapper được tạo từ builder chung. Nếu ứng dụng có nhiều mapper với chính sách khác nhau, cần xem rõ phạm vi module nào được áp dụng. Một module tùy biến dành cho API công khai có thể không phù hợp với mapper import legacy hoặc YAML.

Khi cần giới hạn phạm vi, có thể tạo mapper chuyên biệt và đăng ký module một cách tường minh trên mapper đó. Hãy dùng qualifier để consumer không vô tình nhận nhầm mapper.

## 9. Phân biệt ObjectMapper bean với Jackson message converter

Trong Spring MVC, HTTP request/response JSON thường đi qua HttpMessageConverter. Với Jackson 2, converter phổ biến là MappingJackson2HttpMessageConverter. Converter sử dụng ObjectMapper để đọc body thành DTO và ghi DTO thành response body.

Luồng đơn giản:

~~~text
HTTP request JSON
       |
       v
DispatcherServlet / Spring MVC
       |
       v
MappingJackson2HttpMessageConverter
       |
       v
ObjectMapper của converter
       |
       v
Request DTO
       |
       v
Controller / Service
~~~

Chiều response đi ngược lại qua converter để serialize object thành JSON.

Điểm quan trọng: mapper được inject vào một service và mapper đang được HTTP converter dùng không tự động là cùng instance trong mọi cấu hình tùy biến. Spring Boot thường cấu hình các thành phần này thông qua builder/auto-configuration, nhưng nếu ứng dụng khai báo converter hoặc mapper bean riêng, cần kiểm tra converter thực tế đang dùng instance nào.

Không nên chỉ test service với mapper inject rồi kết luận endpoint HTTP có cùng JSON behavior. Nếu contract được phục vụ qua MVC, hãy kiểm thử qua MockMvc hoặc integration test để xác nhận message converter thực tế.

## 10. Tránh tạo converter riêng không cần thiết

Nếu ứng dụng đã dùng Spring Boot auto-configuration, không nên tự tạo converter chỉ để đăng ký lại mapper mặc định mà chưa hiểu cấu hình hiện tại. Việc khai báo converter mới có thể làm thay đổi danh sách converter, thứ tự ưu tiên hoặc media type được hỗ trợ.

Khi thật sự cần converter Jackson 2 riêng, hãy truyền mapper đã cấu hình rõ ràng:

~~~java
@Bean
public MappingJackson2HttpMessageConverter customJsonConverter(
        @Qualifier("publicApiMapper") ObjectMapper mapper) {
    return new MappingJackson2HttpMessageConverter(mapper);
}
~~~

Đây là ví dụ cho một converter chuyên biệt. Việc thêm nó vào MVC converter list cần theo cơ chế cấu hình phù hợp với Spring Boot/Spring MVC version của dự án. Trước khi làm, hãy xác định converter mặc định nào đang tồn tại và có cần thay thế hay chỉ cần tùy chỉnh builder.

Nếu chỉ cần đổi serialization feature, module hoặc naming policy chung, customizer/property thường ít gây tác động phụ hơn việc thay toàn bộ converter.

## 11. Khi nào nên tạo mapper riêng?

Mapper riêng hợp lý khi chính sách dữ liệu thật sự khác biệt và cần được cô lập. Một số trường hợp:

- Đọc YAML bằng YAMLFactory thay vì JSON factory.
- Đọc file legacy có coercion hoặc naming policy riêng.
- Một đối tác có contract cũ khác API công khai.
- Dữ liệu nội bộ đã phát hành có subtype/type metadata riêng và cần allowlist giới hạn.
- Một công việc import/export cần format hoặc null policy riêng.
- Cần parser constraints hoặc duplicate-key policy khác cho một boundary cụ thể.

Ví dụ mapper JSON riêng cho một định dạng legacy:

~~~java
@Bean("legacyMapper")
public ObjectMapper legacyMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();
}
~~~

Mapper này được tạo một lần khi Spring khởi tạo context, không phải mỗi lần đọc file. Cấu hình riêng cần có lý do và được ghi rõ trong tên bean, class sử dụng và test.

Không tạo mapper riêng chỉ để đổi một writer sang pretty printing; dùng ObjectWriter. Không tạo mapper riêng chỉ để bỏ qua một field trong một lần đọc; dùng reader variant hoặc DTO phù hợp.

## 12. Inject nhiều mapper bằng @Qualifier

Khi có nhiều mapper, injection theo type đơn thuần trở nên mơ hồ. Hãy đặt tên bean và dùng @Qualifier.

~~~java
@Configuration
public class MultiMapperConfiguration {

    @Bean("publicApiMapper")
    public ObjectMapper publicApiMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .build();
    }

    @Bean("legacyMapper")
    public ObjectMapper legacyMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .build();
    }
}
~~~

Consumer chỉ rõ mapper cần dùng:

~~~java
@Service
public class PartnerImportService {
    private final ObjectMapper legacyMapper;

    public PartnerImportService(
            @Qualifier("legacyMapper") ObjectMapper legacyMapper) {
        this.legacyMapper = legacyMapper;
    }

    public PartnerRecord read(String json) throws JsonProcessingException {
        return legacyMapper.readValue(json, PartnerRecord.class);
    }
}
~~~

Một mapper khác có thể được inject vào service public API. Không dựa vào tên bean mặc định hoặc thứ tự khai báo để chọn instance. @Primary có thể chỉ định một bean mặc định khi injection theo type, nhưng @Qualifier thường diễn đạt ý định rõ hơn tại nơi có nhiều policy.

### 12.1. Dùng @Primary có chủ đích

~~~java
@Bean
@Primary
public ObjectMapper applicationMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .build();
}
~~~

@Primary giúp Spring chọn mapper này khi có injection theo type mà không có qualifier. Tuy nhiên, nó không tự bảo đảm mọi converter, client hoặc codec đều sử dụng mapper đó. Hãy kiểm tra cấu hình của từng integration point.

## 13. Mapper JSON và mapper YAML là hai bộ cấu hình khác format

Nếu ứng dụng đọc cả JSON và YAML, thường cần factory tương ứng:

~~~java
@Bean("jsonMapper")
public ObjectMapper jsonMapper() {
    return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .build();
}

@Bean("yamlMapper")
public ObjectMapper yamlMapper() {
    return new ObjectMapper(new YAMLFactory())
            .registerModule(new JavaTimeModule());
}
~~~

Consumer chọn mapper theo định dạng:

~~~java
@Service
public class ConfigurationImportService {
    private final ObjectMapper yamlMapper;

    public ConfigurationImportService(
            @Qualifier("yamlMapper") ObjectMapper yamlMapper) {
        this.yamlMapper = yamlMapper;
    }

    public AppConfig readYaml(String yaml) throws JsonProcessingException {
        return yamlMapper.readValue(yaml, AppConfig.class);
    }
}
~~~

Hai mapper có thể dùng chung DTO và module, nhưng YAML parser có scalar resolution, tag và alias semantics riêng. Đừng thay factory của mapper đang dùng; tạo mapper riêng một lần cho mỗi format.

Nếu mapper YAML cần dùng chung custom serializer/deserializer với mapper JSON, hãy đăng ký module tương ứng trên cả hai theo một cấu hình được quản lý tập trung. Đừng giả định module được gắn vào một mapper sẽ tự xuất hiện trên mọi mapper do ứng dụng tạo thủ công.

## 14. Không để mapper riêng làm lệch date/time behavior

Một lỗi thường gặp là Spring mapper đã được đăng ký JavaTimeModule và cấu hình ISO-8601, trong khi mapper tự tạo không có module đó.

Ví dụ service dùng mapper Spring:

~~~java
@Service
public class EventService {
    private final ObjectMapper mapper;

    public EventService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public Event read(String json) throws JsonProcessingException {
        return mapper.readValue(json, Event.class);
    }
}
~~~

Một utility khác tự tạo mapper:

~~~java
public final class EventJsonUtil {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static String write(Event event) throws JsonProcessingException {
        return MAPPER.writeValueAsString(event);
    }
}
~~~

Nếu Event chứa Instant, LocalDate hoặc OffsetDateTime, hai mapper có thể khác hành vi do module và feature. Một nơi ghi ra timestamp, nơi khác mong ISO string; hoặc mapper thiếu module không đọc được kiểu Java Time.

Giải pháp là dùng cùng mapper Spring khi cùng contract, hoặc cấu hình mapper chuyên biệt với module/feature tương đương khi có lý do tách biệt. Test phải kiểm tra cả hai chiều và đúng format mong muốn.

## 15. Naming strategy và annotation cũng có thể bị bỏ qua

Ứng dụng có thể cấu hình snake_case:

~~~java
builder.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
~~~

Khi đó property Java customerId có thể được ghi/đọc theo tên JSON customer_id tùy cấu hình và annotation.

Một mapper tự tạo mặc định có thể vẫn dùng camelCase. Do đó, cùng một DTO có thể được ghi thành:

~~~json
{"customer_id":"cus-7"}
~~~

bởi mapper Spring và:

~~~json
{"customerId":"cus-7"}
~~~

bởi mapper thủ công.

Tương tự, mix-in, visibility, inclusion và custom annotation introspector có thể chỉ tồn tại trên mapper đã được cấu hình. Đừng cho rằng annotation trên class là yếu tố duy nhất quyết định output; cấu hình mapper cũng có thể tham gia.

## 16. Custom serializer/deserializer: cấu hình ở đúng mapper

Nếu ứng dụng có custom serializer cho Money:

~~~java
public final class MoneySerializer extends JsonSerializer<Money> {
    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers
    ) throws IOException {
        generator.writeNumber(value.amount().toPlainString());
    }
}
~~~

Serializer này chỉ có hiệu lực trên mapper đã đăng ký module chứa nó. Mapper mới tạo bằng new ObjectMapper() không tự biết serializer đó.

Hãy đăng ký module qua cấu hình Spring nếu đó là policy chung. Nếu chỉ một integration cần representation khác, đăng ký trên mapper riêng và đặt tên rõ. Không đăng ký serializer bằng cách mutate mapper sau khi ứng dụng đã bắt đầu xử lý request.

Custom serializer/deserializer được cache và có thể dùng đồng thời; tránh giữ state theo request trong field instance.

## 17. Ảnh hưởng tới RestTemplate, WebClient và các integration khác

ObjectMapper được inject vào service không nhất thiết tự động điều khiển mọi HTTP client trong ứng dụng.

- RestTemplate dùng danh sách HttpMessageConverter của nó. Converter Jackson có thể giữ mapper riêng.
- WebClient dùng codec configuration. Jackson encoder/decoder có thể được cấu hình qua ExchangeStrategies hoặc cơ chế codec của framework.
- Kafka/message listener có thể dùng JsonDeserializer hoặc converter riêng.
- Batch/file import có thể dùng mapper được tạo trực tiếp trong reader/writer của job.

Nếu một integration cần cùng JSON contract, hãy cấu hình converter/codec của integration bằng mapper tương ứng hoặc builder chung. Đừng giả định rằng có ObjectMapper bean nghĩa là tất cả thư viện bên thứ ba đều tự tìm và dùng nó.

Khi nâng cấp Spring Boot hoặc framework, kiểm tra integration point thực tế vì cách auto-configure converter/codec có thể thay đổi theo phiên bản.

## 18. Kiểm tra mapper mà ApplicationContext thực sự cung cấp

Có thể viết test để xác nhận bean tồn tại và đã có policy mong đợi:

~~~java
@SpringBootTest
class JacksonConfigurationTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void applicationMapperIsAvailable() {
        assertNotNull(objectMapper);
    }

    @Test
    void writesDatesAsStrings() throws Exception {
        String json = objectMapper.writeValueAsString(
                new Event(Instant.parse("2026-11-12T10:30:00Z"))
        );

        JsonNode tree = objectMapper.readTree(json);
        assertTrue(tree.path("occurredAt").isTextual());
    }
}
~~~

Test này cần DTO Event phù hợp với dự án và cấu hình JavaTimeModule. Mục tiêu là kiểm tra mapper được Spring inject, không phải một mapper mới được tạo bên trong test.

Nếu ứng dụng có nhiều mapper, test bean theo qualifier:

~~~java
@Autowired
@Qualifier("legacyMapper")
ObjectMapper legacyMapper;
~~~

Có thể kiểm tra từng mapper có module, naming strategy và feature đúng với contract tương ứng.

## 19. Kiểm thử HTTP converter bằng MockMvc

Service test không xác nhận HTTP converter đang dùng mapper nào. Với Spring MVC, dùng MockMvc để đi qua đường xử lý HTTP thực tế:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerJsonTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsExpectedJsonContract() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-42"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.orderId").value("ORD-42"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

Có thể dùng jsonPath để kiểm tra field tập trung. Nếu cần kiểm tra toàn bộ payload, lấy response content, parse thành JsonNode và so sánh với expected tree. Cách này bỏ qua whitespace và object property order nhưng vẫn phát hiện field dư/thiếu theo equality.

Nếu converter đã bị ứng dụng thay thế hoặc thêm mới, test MVC sẽ giúp phát hiện sự khác biệt giữa mapper trong service và mapper ở HTTP boundary.

## 20. Khi nào cần cung cấp converter với cùng mapper bean?

Nếu ứng dụng chủ động tạo converter Jackson 2, có thể truyền mapper bean vào constructor:

~~~java
@Bean
public MappingJackson2HttpMessageConverter apiJsonConverter(
        @Qualifier("publicApiMapper") ObjectMapper mapper) {
    return new MappingJackson2HttpMessageConverter(mapper);
}
~~~

Điều này làm quan hệ giữa converter và mapper rõ ràng. Tuy nhiên, việc đăng ký converter vào danh sách MVC cần thực hiện đúng extension point của phiên bản Spring đang dùng; không chỉ khai báo bean rồi giả định nó luôn thay thế converter mặc định.

Trước khi thay converter, hãy kiểm tra:

- Converter mặc định có đang hoạt động không?
- Có cần hỗ trợ thêm media type hay thay thế toàn bộ JSON converter?
- Thứ tự converter có ảnh hưởng tới request/response không?
- Mapper có module, naming policy và subtype registry đúng không?
- Các endpoint hiện tại có thay đổi behavior ngoài ý muốn không?

Nếu chỉ cần tùy chỉnh mapper chung, customizer hoặc Module bean thường là lựa chọn ít xâm lấn hơn.

## 21. Tránh thay ObjectMapper bean mặc định chỉ để đổi một feature

Một cấu hình như sau có thể làm ứng dụng có mapper bean do chính mình sở hữu:

~~~java
@Bean
public ObjectMapper objectMapper() {
    return new ObjectMapper();
}
~~~

Tùy điều kiện auto-configuration và phiên bản Spring Boot, bean này có thể khiến auto-configuration mặc định lùi lại hoặc thay đổi cách builder/converter được cấu hình. Nếu mapper mới không đăng ký lại các module và feature cần thiết, ứng dụng có thể mất những behavior mà trước đó framework cung cấp.

Nếu mục tiêu chỉ là tắt timestamp cho date/time hoặc đổi inclusion, hãy dùng property hoặc customizer. Nếu mục tiêu là custom serializer, hãy cân nhắc Module bean. Chỉ định nghĩa ObjectMapper bean hoàn chỉnh khi thật sự muốn sở hữu toàn bộ cấu hình và đã hiểu ảnh hưởng tới MVC, client và các integration khác.

## 22. Test không nên tự tạo mapper khác với production

Một test như sau có thể kiểm tra sai cấu hình:

~~~java
@Test
void writesEvent() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    String json = mapper.writeValueAsString(new Event(...));
    // Assertions...
}
~~~

Nếu production dùng mapper do Spring quản lý với JavaTimeModule, custom naming strategy hoặc mix-in, test này không đại diện cho runtime.

Với Spring integration test, inject mapper từ context. Với unit test thuần không khởi tạo Spring, hãy tạo mapper qua cùng factory/configuration method mà ứng dụng sử dụng, hoặc dùng một test fixture được chia sẻ có cấu hình tương đương. Tránh copy một phần cấu hình vào từng test vì các bản sao có thể lệch nhau.

## 23. Cấu hình mapper theo ranh giới tin cậy

Không phải mọi nguồn JSON đều nên dùng cùng policy. Một public API, một message nội bộ và một file import do người dùng tải lên có thể có yêu cầu khác nhau về subtype, unknown property, coercion, duplicate key và giới hạn parser.

Một thiết kế có thể có:

~~~text
Public HTTP API
    -> publicApiMapper
    -> strict DTO contract

Legacy partner import
    -> legacyMapper
    -> compatibility policy đã giới hạn

YAML configuration
    -> yamlMapper
    -> YAMLFactory và schema phù hợp

Internal event stream
    -> eventMapper
    -> subtype allowlist riêng
~~~

Mỗi mapper được tạo một lần và inject rõ ràng. Không tái sử dụng một mapper permissive cho public input chỉ vì mapper đó tiện dùng cho dữ liệu nội bộ. Cũng không dùng một mapper khác nhau một cách vô tình cho cùng một contract.

Nếu các mapper cần chung module, có thể trích cấu hình module thành bean hoặc factory dùng chung; sau đó mỗi mapper áp dụng đúng tập module được phép.

## 24. Quản lý vòng đời và hiệu năng

Spring bean mặc định thường có scope singleton. Một ObjectMapper được cấu hình xong có thể được nhiều thread dùng đồng thời. Việc tái sử dụng giúp tận dụng cache serializer/deserializer và tránh lặp chi phí khởi tạo.

Các nguyên tắc:

- Tạo mapper ở startup, không tạo trong request method.
- Cấu hình xong trước lần đọc/ghi đầu tiên.
- Không bật/tắt feature trên mapper singleton theo request.
- Tạo ObjectReader/ObjectWriter cho type và policy thường dùng.
- Không chia sẻ readerForUpdating() đang giữ một object mutable cụ thể giữa các request.
- Custom serializer/deserializer phải an toàn đồng thời.
- Parser/generator tự tạo phải được đóng đúng cách.
- Chỉ tạo mapper riêng khi có policy/format khác biệt thực sự.

Mapper reuse không có nghĩa mọi thao tác đều miễn phí. Parse vẫn tạo DTO, collection và string; serialize vẫn phải duyệt object graph. Với payload lớn, cân nhắc streaming. Với tối ưu hiệu năng, đo bằng workload thực tế thay vì chỉ suy luận từ số lần tạo mapper.

## 25. Quy trình quyết định: dùng mapper Spring hay mapper riêng?

Khi cần thêm code Jackson vào ứng dụng Spring, có thể đi theo trình tự:

1. **Xác định nơi dữ liệu đi qua:** MVC controller, RestTemplate, WebClient, message broker, batch hay file import?
2. **Kiểm tra mapper hiện có:** inject ObjectMapper và xem cấu hình auto-configuration của dự án.
3. **Xác định policy cần thiết:** module, date/time, naming, null, unknown property, subtype và parser constraints.
4. **Ưu tiên cấu hình Spring:** property, Module bean hoặc customizer cho policy chung.
5. **Tạo mapper riêng nếu cần:** chỉ khi có định dạng hoặc trust boundary khác biệt rõ.
6. **Đặt tên bean:** dùng @Qualifier cho từng mapper chuyên biệt.
7. **Liên kết converter/codec:** xác nhận HTTP client/server hoặc message integration dùng đúng mapper.
8. **Hoàn tất cấu hình trước startup:** không mutate mapper sau khi đã publish.
9. **Kiểm thử context:** xác nhận bean, module và feature thực tế.
10. **Kiểm thử boundary:** dùng MockMvc hoặc integration test cho converter/codec.
11. **Kiểm tra version:** đối chiếu API Spring Boot và Jackson đúng major version.
12. **Đo hiệu năng khi cần:** tránh tạo mapper lặp lại và chỉ tối ưu sau profiling.

## 26. So sánh hai cách tiếp cận

| Tiêu chí | Mapper tự tạo | Mapper Spring quản lý |
|---|---|---|
| Vòng đời | Do code tự quyết định | Do ApplicationContext quản lý |
| Cấu hình | Phải tự đăng ký | Có thể nhận property, customizer và Module bean |
| Tái sử dụng | Phụ thuộc cách lưu giữ instance | Thường được cung cấp như singleton bean |
| Tích hợp MVC | Không tự động là mapper của converter | Có thể được tích hợp qua auto-configuration/builder |
| Kiểm thử | Dễ tạo nhưng có nguy cơ khác production | Có thể kiểm tra đúng cấu hình trong context |
| Nhiều policy | Tạo nhiều instance theo ý code | Dùng nhiều bean có tên và qualifier |
| Trường hợp phù hợp | Tool độc lập, format hoặc policy chuyên biệt | Chính sách serialization chung của ứng dụng |
| Rủi ro thường gặp | Bỏ qua module/feature Spring, lệch contract | Mutate singleton hoặc ghi đè auto-configuration thiếu chủ ý |

## 27. Những lỗi thường gặp

### 27.1. Tạo new ObjectMapper() trong service

Mapper riêng bỏ qua cấu hình chung và lặp khởi tạo. Inject mapper do Spring cung cấp.

### 27.2. Nghĩ mọi ObjectMapper trong ứng dụng là cùng một instance

Một bean, một static mapper và một mapper nằm trong converter có thể là các instance khác nhau. Xác định rõ bean và integration point.

### 27.3. Định nghĩa ObjectMapper bean mới để đổi một feature

Có thể làm auto-configuration lùi lại hoặc tạo lệch cấu hình. Ưu tiên property, customizer hoặc Module bean.

### 27.4. Bật/tắt feature trên mapper singleton

Thao tác này tạo trạng thái dùng chung có thể bị thread khác quan sát. Dùng ObjectWriter/ObjectReader variant.

### 27.5. Chỉ test service mà không test HTTP converter

Service có thể dùng mapper đúng trong khi converter dùng cấu hình khác. Dùng MockMvc/integration test cho contract HTTP.

### 27.6. Cho rằng mapper bean tự điều khiển WebClient hoặc Kafka

Mỗi integration có thể có codec/converter riêng. Cấu hình mapper ở đúng integration point.

### 27.7. Đăng ký module lặp ở nhiều nơi

Khó biết module nào được áp dụng và theo thứ tự nào. Chọn một điểm sở hữu module, kiểm thử mapper cuối cùng.

### 27.8. Dùng một mapper permissive cho mọi nguồn

Policy của dữ liệu nội bộ có thể không phù hợp public input. Tách mapper theo trust boundary.

### 27.9. Dùng qualifier không nhất quán

Khi có nhiều mapper, injection theo type có thể mơ hồ hoặc nhận nhầm bean. Đặt tên và dùng qualifier tại consumer.

### 27.10. Sao chép cấu hình mapper vào test

Test có thể khác production theo thời gian. Inject mapper từ Spring context hoặc dùng chung factory cấu hình.

## 28. Kết luận

Mapper tự tạo bằng new ObjectMapper() là một instance Jackson độc lập; nó chỉ có những module, feature và policy mà code đăng ký trực tiếp. Mapper do Spring Boot quản lý thường được tạo từ builder và auto-configuration, có thể kết hợp spring.jackson.* properties, Module bean và customizer, rồi được inject vào các thành phần ứng dụng. Vì vậy, với cùng một contract JSON, hãy ưu tiên dùng mapper do Spring cung cấp và tùy chỉnh tại điểm cấu hình chung thay vì tạo mapper mới trong từng service.

Mapper Spring quản lý vẫn cần được cấu hình xong trước khi dùng và không nên bị mutate theo request. HTTP message converter, RestTemplate, WebClient và message integration có thể giữ mapper/codec riêng; hãy xác nhận đúng integration point đang xử lý dữ liệu. Khi cần một format hoặc trust boundary khác, tạo mapper riêng một lần, đặt tên bean rõ và inject bằng @Qualifier. Kiểm thử cả mapper trong ApplicationContext lẫn đường HTTP thực tế để bảo đảm mọi thành phần cùng tuân thủ contract dự kiến.
