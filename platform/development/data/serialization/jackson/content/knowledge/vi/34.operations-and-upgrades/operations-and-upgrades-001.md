# Lưu cấu hình và module đang có hiệu lực để hỗ trợ chẩn đoán

## 1. Vì sao cần lưu cấu hình Jackson thực tế?

Một ứng dụng thường không chỉ có một ObjectMapper với cấu hình mặc định. Mapper có thể được tạo từ nhiều nguồn:

- Cấu hình do ứng dụng viết trực tiếp.
- Các module đăng ký thủ công hoặc được tự phát hiện qua ServiceLoader.
- Các customizer của framework như Spring Boot.
- Annotation trên DTO, mix-in và naming strategy.
- Feature serialize/deserialize, coercion và null policy.
- Cấu hình riêng của JsonFactory, parser và generator.
- Cấu hình được áp dụng theo từng boundary: REST API, message broker, file import hoặc persistence.

Khi một payload bỗng được đọc khác đi sau khi deploy, chỉ nhìn vào DTO hoặc application.yml thường không đủ. Mapper thực tế có thể đã nhận thêm module, thay đổi feature, dùng một JsonFactory khác hoặc được framework tùy biến sau khi bean được tạo.

Ví dụ, cùng một field JSON có thể được xử lý khác nhau nếu một mapper:

- Bật hoặc tắt FAIL_ON_UNKNOWN_PROPERTIES.
- Bật ACCEPT_FLOAT_AS_INT.
- Đăng ký JavaTimeModule.
- Dùng property naming strategy khác.
- Thêm mix-in hoặc custom deserializer.
- Dùng coercion policy hoặc parser constraint khác.

Vì vậy, mỗi mapper quan trọng nên có một bản ghi chẩn đoán mô tả cấu hình và module thực sự có hiệu lực. Bản ghi này giúp trả lời: mapper nào đã xử lý message, đang dùng format nào, những module nào được đăng ký, feature nào đang bật và cấu hình đến từ đâu.

## 2. Phân biệt cấu hình dự kiến và cấu hình có hiệu lực

Có hai loại thông tin khác nhau:

- **Cấu hình dự kiến (declared configuration):** những gì đội phát triển định bật trong file cấu hình hoặc code.
- **Cấu hình có hiệu lực (effective configuration):** trạng thái cuối cùng của mapper sau khi builder, module, framework customizer, mix-in và các bước cấu hình khác đã chạy.

Ví dụ, file cấu hình có thể đặt FAIL_ON_UNKNOWN_PROPERTIES = false, nhưng một customizer chạy sau đó lại bật feature này. Nếu chỉ lưu file cấu hình, báo cáo sẽ không phản ánh hành vi thực tế.

Quy trình nên là:

~~~text
Application properties
        |
        v
Mapper builder / ObjectMapper
        |
        v
Module registration
        |
        v
Framework customizers
        |
        v
Application-specific configuration
        |
        v
Mapper hoàn chỉnh
        |
        v
Capture effective snapshot
~~~

Chụp snapshot sau bước cấu hình cuối cùng và trước khi mapper bắt đầu phục vụ request. Nếu hệ thống có nhiều mapper, chụp riêng từng instance và ghi rõ vai trò của chúng.

Không nên tạo một mapper mới chỉ để xem cấu hình rồi coi đó là cấu hình production. Bản ghi phải lấy từ chính instance mà request hoặc message consumer đang sử dụng.

## 3. Thông tin nào nên được lưu?

Một snapshot chẩn đoán hữu ích thường có các nhóm thông tin:

| Nhóm | Trường thông tin gợi ý | Mục đích |
|---|---|---|
| Nhận diện | mapperId, role, format | Biết mapper nào xử lý dữ liệu nào |
| Phiên bản | ứng dụng, JDK, Jackson Databind/Core, dataformat module | Phát hiện lệch phiên bản sau deploy |
| Factory | class của JsonFactory, format name | Biết parser/generator thuộc định dạng nào |
| Module | tên, class, version, type ID | Xác nhận serializer/deserializer mở rộng |
| Serialization | SerializationFeature đang bật/tắt | Giải thích JSON/XML/binary đầu ra |
| Deserialization | DeserializationFeature đang bật/tắt | Giải thích cách mapper đọc input |
| Mapper behavior | MapperFeature, naming strategy, visibility | Giải thích cách phát hiện property |
| Annotation | AnnotationIntrospector và mix-in policy | Xác định metadata được áp dụng |
| Format defaults | inclusion, locale, timezone, date format class | Giải thích null và ngày giờ |
| Parser safety | max nesting, string length, number length, duplicate policy | Xác nhận giới hạn input |
| Provenance | config source, customizer names, build ID | Tìm nguồn thay đổi |
| Thời điểm | capturedAt, environment | So sánh giữa các lần deploy |

Không nhất thiết phải ghi mọi chi tiết vào log mỗi request. Snapshot thường được tạo lúc khởi động hoặc khi cấu hình mapper hoàn tất, sau đó có thể xuất qua endpoint quản trị được bảo vệ hoặc lưu thành artifact triển khai.

## 4. Đặt tên và vai trò riêng cho từng mapper

Nhiều hệ thống có nhiều mapper:

- api-json-in: đọc request JSON từ REST API.
- api-json-out: serialize response.
- event-cbor: đọc/ghi message CBOR.
- legacy-xml: tích hợp với hệ thống XML cũ.
- audit-json: ghi sự kiện audit.

Không nên lưu một bản ghi chung mang tên jacksonMapper nếu ứng dụng có nhiều mapper với chính sách khác nhau.

Ví dụ metadata:

~~~json
{
  "mapperId": "event-cbor",
  "role": "MESSAGE_CONSUMER",
  "direction": "READ",
  "format": "CBOR",
  "environment": "production"
}
~~~

mapperId nên ổn định qua các lần deploy và có ý nghĩa trong log/trace. Không dùng object identity hoặc hash code của instance làm ID duy nhất vì chúng không ổn định giữa các tiến trình.

Nếu input và output dùng cùng một mapper, vẫn có thể ghi role = api-json và direction = READ_WRITE. Tuy nhiên, nếu hai chiều có feature hoặc module khác nhau, tách mapper thường giúp chẩn đoán rõ hơn.

## 5. Ghi nhận module khi đăng ký tường minh

Jackson Module có các thông tin có thể dùng để mô tả module:

- Tên module qua getModuleName().
- Version qua version().
- Type ID qua getTypeId().
- Tên lớp implementation qua getClass().getName().

Có thể tạo descriptor:

~~~java
import com.fasterxml.jackson.databind.Module;

public record ModuleDescriptor(
        String className,
        String moduleName,
        String version,
        String typeId
) {
    static ModuleDescriptor from(Module module) {
        return new ModuleDescriptor(
                module.getClass().getName(),
                module.getModuleName(),
                module.version().toFullString(),
                String.valueOf(module.getTypeId())
        );
    }
}
~~~

Khi đăng ký tường minh, ứng dụng có thể lưu descriptor ngay tại nơi tạo mapper:

~~~java
List<Module> modules = List.of(
        new JavaTimeModule(),
        new Jdk8Module()
);

ObjectMapper mapper = new ObjectMapper();
List<ModuleDescriptor> inventory = new ArrayList<>();

for (Module module : modules) {
    mapper.registerModule(module);
    inventory.add(ModuleDescriptor.from(module));
}
~~~

Lưu inventory theo đúng thứ tự đăng ký. Thứ tự có thể ảnh hưởng khi nhiều module cùng tùy biến serializer, deserializer hoặc modifier cho một kiểu.

Descriptor chỉ là metadata. Không ghi toàn bộ object module vào log hoặc snapshot; module có thể chứa state, collaborator hoặc đối tượng không thể serialize an toàn.

## 6. Ghi nhận module được tự phát hiện

Nếu ứng dụng dùng ServiceLoader để tìm module, có thể lấy danh sách module được phát hiện rồi đăng ký và ghi inventory:

~~~java
List<Module> discovered = ObjectMapper.findModules();

ObjectMapper mapper = new ObjectMapper();
List<ModuleDescriptor> inventory = new ArrayList<>();

for (Module module : discovered) {
    mapper.registerModule(module);
    inventory.add(ModuleDescriptor.from(module));
}
~~~

Cách này giúp snapshot biết những provider nào được tìm thấy trong runtime classpath/module path.

Nếu dùng findAndRegisterModules() trực tiếp, danh sách module được đăng ký có thể không được ứng dụng ghi lại tại thời điểm đăng ký. Có thể dùng getRegisteredModuleIds() như một tín hiệu bổ sung trong các phiên bản và cấu hình hỗ trợ tracking, nhưng ID đó không nhất thiết là danh sách class/version đầy đủ.

Đừng giả định mọi module có trên classpath đều được tự động đăng ký. Module cần công bố provider qua ServiceLoader/JPMS và phải được classloader/module layer nhìn thấy. Một số module cũng yêu cầu đăng ký tường minh theo tài liệu riêng.

Khi framework tự thêm module, hãy lấy inventory từ cấu hình thực tế của framework hoặc ghi nhận các module qua customizer/registry mà ứng dụng kiểm soát. Đừng chỉ dựa vào danh sách dependency trong build file: dependency có mặt không chứng minh module đã được đăng ký vào mapper.

## 7. Chụp trạng thái feature serialize và deserialize

ObjectMapper cho phép đọc trạng thái feature qua SerializationConfig và DeserializationConfig. Có thể tạo bản đồ tên feature và trạng thái:

~~~java
static Map<String, Boolean> serializationFeatures(
        ObjectMapper mapper
) {
    Map<String, Boolean> result = new LinkedHashMap<>();
    SerializationConfig config = mapper.getSerializationConfig();

    for (SerializationFeature feature : SerializationFeature.values()) {
        result.put(feature.name(), config.isEnabled(feature));
    }
    return result;
}

static Map<String, Boolean> deserializationFeatures(
        ObjectMapper mapper
) {
    Map<String, Boolean> result = new LinkedHashMap<>();
    DeserializationConfig config = mapper.getDeserializationConfig();

    for (DeserializationFeature feature : DeserializationFeature.values()) {
        result.put(feature.name(), config.isEnabled(feature));
    }
    return result;
}
~~~

Các feature thường đáng chú ý khi điều tra:

| Feature | Ảnh hưởng |
|---|---|
| FAIL_ON_UNKNOWN_PROPERTIES | Từ chối hay bỏ qua property chưa biết |
| FAIL_ON_MISSING_CREATOR_PROPERTIES | Xử lý creator parameter bị thiếu |
| FAIL_ON_NULL_FOR_PRIMITIVES | Xử lý null cho primitive |
| ACCEPT_FLOAT_AS_INT | Có cho phép decimal vào kiểu integer hay không |
| USE_BIG_INTEGER_FOR_INTS | Kiểu số nguyên trong dữ liệu untyped |
| USE_BIG_DECIMAL_FOR_FLOATS | Kiểu decimal trong dữ liệu untyped |
| READ_UNKNOWN_ENUM_VALUES_AS_NULL | Cách xử lý enum chưa biết |
| WRITE_DATES_AS_TIMESTAMPS | Cách ghi date/time |
| INDENT_OUTPUT | Ghi JSON có thụt dòng hay không |
| WRITE_NULL_MAP_VALUES | Cách ghi giá trị null trong Map, tùy phiên bản |

Danh sách enum feature thay đổi giữa các phiên bản Jackson. Ghi tên feature và trạng thái giúp so sánh snapshot giữa các bản phát hành, nhưng phải đọc cùng Jackson version để hiểu chính xác semantics.

## 8. Ghi nhận MapperFeature và naming strategy

MapperFeature điều khiển nhiều hành vi chung như visibility, case-insensitive matching, duplicate module registration tracking hoặc access override.

Có thể ghi trạng thái:

~~~java
static Map<String, Boolean> mapperFeatures(ObjectMapper mapper) {
    Map<String, Boolean> result = new LinkedHashMap<>();
    DeserializationConfig config = mapper.getDeserializationConfig();

    for (MapperFeature feature : MapperFeature.values()) {
        result.put(feature.name(), config.isEnabled(feature));
    }
    return result;
}
~~~

Property naming strategy cũng nên được ghi:

~~~java
PropertyNamingStrategy strategy = mapper.getPropertyNamingStrategy();

String strategyClass = strategy == null
        ? "default"
        : strategy.getClass().getName();
~~~

Ví dụ, SNAKE_CASE có thể biến Java property displayName thành JSON key display_name. Nếu một môi trường dùng strategy khác, payload có thể không bind như mong đợi.

Ngoài tên class, snapshot có thể lưu một nhãn cấu hình do ứng dụng đặt như SNAKE_CASE hoặc CUSTOM_CUSTOMER_STRATEGY. Nhãn dễ hiểu hơn tên implementation nội bộ và giúp phân biệt các instance custom cùng class.

## 9. Ghi nhận annotation introspector, inclusion và locale

AnnotationIntrospector quyết định Jackson hiểu metadata annotation trên DTO như thế nào. Một ứng dụng có thể dùng introspector mặc định, kết hợp nhiều introspector hoặc introspector riêng.

Có thể ghi class đang có hiệu lực:

~~~java
String annotationIntrospectorClass = mapper
        .getDeserializationConfig()
        .getAnnotationIntrospector()
        .getClass()
        .getName();
~~~

Các cấu hình khác:

~~~java
SerializationConfig serialization = mapper.getSerializationConfig();

String inclusion = serialization
        .getDefaultPropertyInclusion()
        .toString();

String locale = serialization.getLocale().toLanguageTag();
String timeZone = serialization.getTimeZone().getID();
~~~

Inclusion policy có thể giải thích vì sao null hoặc empty property biến mất khỏi output. Locale/timezone có thể ảnh hưởng cách format date/time hoặc một số giá trị phụ thuộc locale.

Ghi class của DateFormat nếu mapper dùng format tùy chỉnh:

~~~java
DateFormat dateFormat = serialization.getDateFormat();
String dateFormatClass = dateFormat == null
        ? "default"
        : dateFormat.getClass().getName();
~~~

Nếu cần biết pattern hoặc timezone của DateFormat custom, hãy lưu cấu hình do ứng dụng tạo ra cùng snapshot. Không nên gọi toString() của mọi object cấu hình và giả định nó luôn là định dạng ổn định, an toàn để log.

## 10. Ghi nhận format và phiên bản factory

Mapper có thể dùng JSON, XML, YAML, Smile, CBOR hoặc CSV. Factory class và format name là thông tin quan trọng:

~~~java
JsonFactory factory = mapper.getFactory();

String factoryClass = factory.getClass().getName();
String formatName = factory.getFormatName();
String factoryVersion = factory.version().toFullString();
String databindVersion = mapper.version().toFullString();
~~~

Ví dụ snapshot:

~~~json
{
  "mapperId": "event-cbor",
  "formatName": "CBOR",
  "factoryClass": "com.fasterxml.jackson.dataformat.cbor.CBORFactory",
  "factoryVersion": "2.x",
  "databindVersion": "2.x"
}
~~~

Version string trong ví dụ chỉ minh họa cấu trúc. Hãy lấy giá trị thực từ runtime, không tự ghi phiên bản theo build file nếu ứng dụng có thể load nhiều phiên bản qua classloader hoặc dependency conflict.

Format name có thể null với một factory tùy chỉnh. Khi đó class name và metadata do ứng dụng cung cấp sẽ là dấu hiệu nhận diện.

## 11. Parser constraints và factory features cần được ghi riêng

Không phải mọi cài đặt parser/generator đều là DeserializationFeature hoặc SerializationFeature. Một số cấu hình thuộc JsonFactory, JsonParser hoặc JsonGenerator:

- Strict duplicate detection.
- StreamReadConstraints như max nesting depth, max string length và max number length.
- Parser feature về comment, trailing comma hoặc single quotes nếu được cho phép.
- Generator feature về quoting, escaping hoặc output target.
- Input/output decorators.

Các giá trị này cần được lưu tại thời điểm tạo factory vì không phải mọi phiên bản Jackson đều cung cấp API introspection đầy đủ cho từng cấu hình.

Ví dụ cấu hình có nguồn gốc rõ:

~~~java
record ParserPolicy(
        boolean strictDuplicateDetection,
        int maxNestingDepth,
        int maxStringLength,
        int maxNumberLength
) {
}

ParserPolicy parserPolicy = new ParserPolicy(
        true,
        100,
        1_000_000,
        1_000
);
~~~

Sau đó dùng cùng policy để xây dựng factory và snapshot. Cách này bảo đảm báo cáo phản ánh các giá trị mà ứng dụng đã truyền vào builder, thay vì cố suy ngược những thông tin không được API công khai.

Không ghi các giá trị giới hạn theo giả định hoặc default của phiên bản khác. Nếu ứng dụng không cấu hình một constraint, hãy ghi rõ DEFAULT/UNSPECIFIED và version Jackson tương ứng.

## 12. Xây dựng một snapshot có cấu trúc

Có thể dùng record để biểu diễn snapshot:

~~~java
public record MapperSnapshot(
        String mapperId,
        String role,
        String direction,
        String formatName,
        String factoryClass,
        String factoryVersion,
        String databindVersion,
        String propertyNamingStrategy,
        String annotationIntrospector,
        String defaultInclusion,
        String locale,
        String timeZone,
        String dateFormatClass,
        String configurationSource,
        String capturedAt,
        List<ModuleDescriptor> modules,
        Map<String, Boolean> serializationFeatures,
        Map<String, Boolean> deserializationFeatures,
        Map<String, Boolean> mapperFeatures,
        ParserPolicy parserPolicy
) {
}
~~~

Snapshot nên là dữ liệu bất biến hoặc bản sao độc lập. Không giữ tham chiếu tới ObjectMapper hoặc module instance trong bản ghi chẩn đoán.

Khi tạo snapshot, ghi thêm:

- Application version/build ID.
- Environment hoặc deployment ID.
- Tên bean hoặc config factory tạo mapper.
- Danh sách customizer đã áp dụng.
- Module inventory theo thứ tự.
- Thời điểm capture.

Không cần ghi mọi thông tin vào một JSON khổng lồ. Có thể tách phần module inventory và feature map thành các trường con để dễ diff.

## 13. Ví dụ chụp snapshot từ mapper thực tế

Ví dụ dưới đây kết hợp các helper đã trình bày:

~~~java
static MapperSnapshot snapshot(
        String mapperId,
        String role,
        String direction,
        String source,
        ObjectMapper mapper,
        List<ModuleDescriptor> modules,
        ParserPolicy parserPolicy
) {
    JsonFactory factory = mapper.getFactory();
    SerializationConfig serialization = mapper.getSerializationConfig();
    DeserializationConfig deserialization = mapper.getDeserializationConfig();

    PropertyNamingStrategy naming = mapper.getPropertyNamingStrategy();
    DateFormat dateFormat = serialization.getDateFormat();

    return new MapperSnapshot(
            mapperId,
            role,
            direction,
            factory.getFormatName(),
            factory.getClass().getName(),
            factory.version().toFullString(),
            mapper.version().toFullString(),
            naming == null ? "default" : naming.getClass().getName(),
            deserialization.getAnnotationIntrospector()
                    .getClass().getName(),
            serialization.getDefaultPropertyInclusion().toString(),
            serialization.getLocale().toLanguageTag(),
            serialization.getTimeZone().getID(),
            dateFormat == null ? "default" : dateFormat.getClass().getName(),
            source,
            Instant.now().toString(),
            List.copyOf(modules),
            serializationFeatures(mapper),
            deserializationFeatures(mapper),
            mapperFeatures(mapper),
            parserPolicy
    );
}
~~~

Hàm này nhận module inventory và ParserPolicy từ nơi tạo mapper. Đây là chủ ý: một snapshot đáng tin cậy cần kết hợp phần có thể introspect từ mapper với metadata cấu hình mà ứng dụng kiểm soát.

## 14. Xuất snapshot thành JSON an toàn

Có thể serialize snapshot thành JSON dễ đọc bằng một mapper dành riêng cho diagnostics:

~~~java
ObjectMapper diagnosticMapper = new ObjectMapper();

String json = diagnosticMapper
        .writerWithDefaultPrettyPrinter()
        .writeValueAsString(snapshot);
~~~

Mapper diagnostics nên đơn giản và ổn định, không phụ thuộc mapper đang được kiểm tra. Nếu dùng chính mapper lỗi để serialize báo cáo, việc xuất snapshot cũng có thể thất bại hoặc tạo output theo format đang cần chẩn đoán.

Có thể ghi JSON snapshot vào:

- Startup log có cấu trúc.
- File artifact gắn với deployment.
- Endpoint quản trị yêu cầu xác thực.
- Hệ thống configuration inventory.
- Dashboard nội bộ so sánh giữa các môi trường.

Không nên công khai toàn bộ snapshot qua endpoint không xác thực. Danh sách module, phiên bản, customizer và cấu hình có thể tiết lộ chi tiết triển khai hữu ích cho người tấn công.

## 15. Gắn snapshot với chính ObjectMapper được framework quản lý

Trong ứng dụng framework-managed, hãy lấy đúng bean được dùng bởi controller hoặc message converter. Không tự new ObjectMapper trong diagnostic service rồi coi đó là mapper production.

Ví dụ với Spring:

~~~java
@Component
public class JacksonDiagnostics {
    private final ObjectMapper applicationMapper;

    public JacksonDiagnostics(ObjectMapper applicationMapper) {
        this.applicationMapper = applicationMapper;
    }

    public MapperSnapshot snapshot() {
        return snapshot(
                "application-json",
                "HTTP_API",
                "READ_WRITE",
                "Spring-managed ObjectMapper bean",
                applicationMapper,
                recordedModules,
                parserPolicy
        );
    }
}
~~~

Đây là ví dụ kiến trúc. recordedModules và parserPolicy cần được cung cấp từ cấu hình thực tế của ứng dụng; không tự suy ra từ danh sách dependency.

Nếu framework có nhiều ObjectMapper bean hoặc nhiều HttpMessageConverter, xác định rõ bean nào xử lý endpoint nào. Một ứng dụng có thể vô tình dùng mapper khác với mapper mà nhóm phát triển đang kiểm tra.

Với Spring Boot, các nguồn có thể gồm spring.jackson properties, Jackson2ObjectMapperBuilderCustomizer, Module bean và cấu hình converter. Ghi tên customizer/configuration class và thứ tự áp dụng nếu điều đó ảnh hưởng hành vi.

## 16. Lưu provenance để biết cấu hình đến từ đâu

Chỉ ghi trạng thái cuối cùng có thể cho biết mapper đang làm gì nhưng chưa giải thích vì sao. Provenance ghi lại nguồn cấu hình:

| Nguồn | Ví dụ metadata |
|---|---|
| Default Jackson | DEFAULT |
| application.yml | application.yaml: spring.jackson.deserialization |
| Java configuration | JsonConfiguration.createApiMapper |
| Module bean | JavaTimeModule bean |
| ServiceLoader | provider class từ SPI |
| Framework customizer | CustomerJacksonCustomizer |
| Environment override | APP_JACKSON_FAIL_UNKNOWN=true |
| Tenant/route configuration | tenant-specific mapper policy |

Không cần lưu toàn bộ environment variable hoặc application properties. Chỉ lưu tên nguồn và giá trị cấu hình đã được cho phép công bố.

Nếu nhiều nguồn cùng đặt một feature, ghi cả giá trị cuối cùng và nguồn được xác định là nguồn ghi đè cuối. Điều này giúp giải thích vì sao cấu hình file không khớp hành vi runtime.

## 17. So sánh snapshot giữa các lần deploy

Snapshot có giá trị nhất khi được so sánh giữa:

- Local, staging và production.
- Phiên bản ứng dụng trước và sau deploy.
- Producer và consumer.
- Mapper đọc và mapper ghi.
- Các instance trong cùng một cluster.

Ví dụ diff:

~~~text
mapperId: api-json-in
Jackson Databind: 2.16.x -> 2.17.x
FAIL_ON_UNKNOWN_PROPERTIES: true -> false
ACCEPT_FLOAT_AS_INT: true -> false
Modules:
  + com.fasterxml.jackson.datatype.jsr310.JavaTimeModule
Property naming:
  default -> SnakeCaseStrategy
~~~

Một diff nhỏ có thể giải thích thay đổi hành vi lớn. Ví dụ, việc chuyển property naming sang SNAKE_CASE có thể khiến tên JSON được nhận diện khác trước.

Không nên coi mọi diff là lỗi. Một thay đổi có thể là chủ đích. Hãy lưu snapshot cùng release note hoặc cấu hình mong đợi để phân biệt drift ngoài ý muốn với thay đổi đã phê duyệt.

## 18. Tạo test xác nhận cấu hình thực tế

Snapshot có thể được dùng trong test cấu hình:

~~~java
@Test
void apiMapperHasExpectedConfiguration() {
    ObjectMapper mapper = configuration.createApiMapper();

    assertTrue(
            mapper.getDeserializationConfig()
                    .isEnabled(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    );

    assertFalse(
            mapper.getDeserializationConfig()
                    .isEnabled(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    );

    assertEquals(
            "com.fasterxml.jackson.databind.PropertyNamingStrategies$SnakeCaseStrategy",
            mapper.getPropertyNamingStrategy().getClass().getName()
    );
}
~~~

Tên implementation class trong assertion là ví dụ và có thể khác theo phiên bản hoặc cách cấu hình. Trong test ổn định hơn, có thể kiểm tra hành vi thực tế bằng payload mẫu thay vì phụ thuộc class nội bộ.

Test module:

~~~java
@Test
void mapperRegistersJavaTimeModule() {
    ObjectMapper mapper = configuration.createApiMapper();

    assertTrue(
            mapper.getRegisteredModuleIds()
                    .contains("jackson-datatype-jsr310")
    );
}
~~~

Đoạn test trên chỉ phù hợp nếu module type ID được đăng ký là chuỗi tương ứng và mapper đang tracking module IDs. Không phải mọi module đều dùng cùng ID. Cách đáng tin cậy hơn là kiểm tra inventory do ứng dụng ghi lại khi đăng ký và thêm test hành vi serialize/deserialize kiểu JavaTime thực tế.

## 19. Introspection có giới hạn: không phải mọi thứ đều đọc ngược được

ObjectMapper cung cấp nhiều API để đọc trạng thái hiện tại, nhưng không có một API tổng quát đảm bảo tái tạo toàn bộ cấu hình ban đầu hoặc nguồn gốc mọi thay đổi.

Một số thông tin khó hoặc không thể suy ngược đầy đủ:

- Module class/version nếu chỉ còn module ID.
- Thứ tự customizer đã chạy nếu ứng dụng không ghi lại.
- Các giá trị parser constraints nếu phiên bản không cung cấp getter phù hợp.
- Coercion overrides theo từng logical type/property.
- Mix-in mapping đầy đủ trên toàn bộ kiểu nếu không có registry riêng.
- Custom serializer/deserializer và dependency bên trong module.
- Default typing và validator đã được cài ở bước nào.
- Property-level annotation và mix-in tương tác cho một kiểu cụ thể.
- Cấu hình được áp dụng qua một mapper wrapper hoặc converter khác.

Vì vậy, nên áp dụng hai nguồn:

1. **Runtime introspection:** đọc trạng thái mà API công khai của mapper/factory cho phép.
2. **Configuration registry:** ghi lại các module, customizer, coercion policy, parser policy và nguồn cấu hình ngay tại nơi tạo chúng.

Không nên dùng reflection để đọc field private nội bộ của Jackson nhằm lấp mọi khoảng trống. Cách đó dễ hỏng khi nâng cấp phiên bản và có thể làm diagnostic code phụ thuộc implementation detail.

## 20. Ghi nhận coercion và null policy

Coercion có thể thay đổi cách Jackson hiểu cùng một JSON token. Ví dụ, string "12" có thể được chấp nhận cho integer trong một cấu hình nhưng bị từ chối trong cấu hình khác.

Nếu ứng dụng dùng coercionConfigFor(...), hãy lưu policy tại nơi cấu hình:

~~~java
record CoercionPolicy(
        String logicalType,
        String inputShape,
        String action
) {
}
~~~

Ví dụ metadata:

~~~json
[
  {
    "logicalType": "Integer",
    "inputShape": "String",
    "action": "Fail"
  },
  {
    "logicalType": "Float",
    "inputShape": "EmptyString",
    "action": "AsNull"
  }
]
~~~

Tương tự, ghi lại null policy nếu ứng dụng dùng JsonSetter.Nulls hoặc default setter behavior:

- SET: áp dụng null vào property.
- SKIP: bỏ qua giá trị null.
- FAIL: từ chối explicit null.
- AS_EMPTY: dùng giá trị rỗng do deserializer cung cấp.
- DEFAULT: dùng policy mặc định.

Các policy có thể được đặt ở cấp class/property, nên snapshot mapper toàn cục không thể thay thế việc kiểm tra annotation và contract test cho DTO cụ thể.

## 21. Ghi nhận mix-in và custom serializer/deserializer

Mix-in có thể thay đổi annotation mà Jackson áp dụng cho một kiểu bên thứ ba. Custom serializer/deserializer có thể thay đổi hoàn toàn representation hoặc validation.

Nên ghi registry do ứng dụng quản lý:

~~~java
record MappingExtension(
        String targetType,
        String extensionType,
        String implementationClass,
        String configurationSource
) {
}
~~~

Ví dụ:

~~~json
[
  {
    "targetType": "com.example.ExternalUser",
    "extensionType": "MIX_IN",
    "implementationClass": "com.example.jackson.ExternalUserMixin",
    "configurationSource": "ExternalUserJacksonConfiguration"
  },
  {
    "targetType": "com.example.Money",
    "extensionType": "CUSTOM_DESERIALIZER",
    "implementationClass": "com.example.jackson.MoneyDeserializer",
    "configurationSource": "MoneyModule"
  }
]
~~~

Không phải lúc nào cũng có thể liệt kê mọi serializer/deserializer đã được đăng ký sau khi module chạy setupModule(). Registry ở nơi cấu hình giúp lưu được ý định và nguồn gốc. Hãy bổ sung test cho các kiểu quan trọng để xác nhận extension thực sự có hiệu lực.

## 22. Không đưa bí mật hoặc dữ liệu người dùng vào snapshot

Snapshot phục vụ chẩn đoán cấu hình, không phải dump trạng thái ứng dụng. Không ghi:

- API key, password, access token hoặc secret.
- Nội dung payload thực tế.
- Giá trị field của người dùng.
- Connection string có credential.
- Environment variable chứa bí mật.
- Đối tượng custom serializer có thể giữ dữ liệu nhạy cảm.

Ghi tên class, tên module, version, feature flag, policy label và nguồn cấu hình đã được cho phép. Nếu cần lưu raw config để điều tra, dùng hệ thống secret/config management có phân quyền và redaction riêng.

Endpoint diagnostics nên:

- Chỉ cho admin/operator được xác thực truy cập.
- Không expose trên public ingress.
- Có audit cho thao tác truy cập.
- Có thể tắt hoặc giới hạn trong production.
- Trả dữ liệu đã lọc và không bao gồm payload.

## 23. Theo dõi drift trong cluster

Trong cluster có nhiều instance, mỗi instance có thể vô tình chạy cấu hình khác nhau do:

- Image hoặc dependency khác version.
- Environment variable không đồng nhất.
- Một pod chưa được restart sau khi đổi config.
- Classpath/module path khác nhau.
- Customizer được kích hoạt theo profile.
- Feature flag hoặc tenant policy khác nhau.

Có thể publish snapshot fingerprint:

~~~text
mapperId + format + module inventory + feature map + parser policy
                         |
                         v
                 Stable fingerprint
~~~

Fingerprint giúp phát hiện hai instance cùng role nhưng có cấu hình khác nhau. Cần chuẩn hóa thứ tự key/list trước khi hash để fingerprint ổn định.

Không hash object mapper trực tiếp hoặc dùng Object.hashCode(). Hãy serialize một representation chuẩn hóa của snapshot rồi hash bytes bằng thuật toán ổn định như SHA-256.

Khi fingerprint khác nhau, hiển thị diff của các trường cấu hình để operator biết khác biệt nằm ở module, feature hay phiên bản.

## 24. Quy trình chẩn đoán khi hành vi Jackson thay đổi

Khi một payload bắt đầu serialize hoặc deserialize khác sau deploy:

1. Xác định mapperId và boundary đã xử lý payload.
2. Lấy snapshot từ đúng instance và đúng environment.
3. So sánh với snapshot của bản deploy trước.
4. Kiểm tra Jackson Core/Databind và dataformat module versions.
5. Kiểm tra module inventory và thứ tự đăng ký.
6. Kiểm tra feature serialize/deserialize và MapperFeature.
7. Kiểm tra naming strategy, visibility, annotation introspector và mix-in registry.
8. Kiểm tra coercion, null policy và parser constraints.
9. Xác định customizer hoặc config source đã thay đổi.
10. Tái hiện bằng đúng mapper factory/configuration và fixture payload.

Không nên debug bằng một ObjectMapper mới tạo với default configuration rồi kết luận payload production phải có cùng kết quả.

## 25. Ví dụ báo cáo chẩn đoán hoàn chỉnh

Một snapshot có thể được xuất dưới dạng:

~~~json
{
  "mapperId": "api-json-in",
  "role": "HTTP_API",
  "direction": "READ",
  "formatName": "JSON",
  "factoryClass": "com.fasterxml.jackson.core.JsonFactory",
  "factoryVersion": "runtime-value",
  "databindVersion": "runtime-value",
  "applicationVersion": "2026.11.12+build.42",
  "environment": "staging",
  "configurationSource": "ApiJacksonConfiguration",
  "capturedAt": "2026-11-12T08:00:00Z",
  "modules": [
    {
      "className": "com.fasterxml.jackson.datatype.jsr310.JavaTimeModule",
      "moduleName": "jackson-datatype-jsr310",
      "version": "runtime-value",
      "typeId": "jackson-datatype-jsr310"
    }
  ],
  "features": {
    "FAIL_ON_UNKNOWN_PROPERTIES": true,
    "ACCEPT_FLOAT_AS_INT": false,
    "USE_BIG_DECIMAL_FOR_FLOATS": true
  },
  "propertyNamingStrategy": "default",
  "parserPolicy": {
    "strictDuplicateDetection": true,
    "maxNestingDepth": 100,
    "maxStringLength": 1000000,
    "maxNumberLength": 1000
  }
}
~~~

Các giá trị runtime-value là chỗ giữ chỗ trong ví dụ; snapshot thực tế phải lấy version từ runtime. Không hardcode chúng trong diagnostic report.

Một báo cáo ngắn có thể lưu tất cả feature map; ví dụ trên chỉ hiển thị các feature quan trọng để dễ đọc.

## 26. Những lỗi thường gặp

### Ghi file cấu hình thay vì trạng thái mapper

File cấu hình thể hiện ý định, không nhất thiết phản ánh customizer và module được áp dụng sau đó. Capture mapper sau bước cấu hình cuối.

### Tạo mapper thứ hai để chẩn đoán

Mapper mới có thể không giống mapper production. Inject đúng instance đang được sử dụng.

### Chỉ ghi dependency trong build file

Dependency hiện diện không chứng minh module đã được đăng ký. Ghi module inventory tại nơi đăng ký và xác nhận hành vi.

### Chỉ ghi module ID

Module ID có thể không chứa class/version hoặc có thể null/không duy nhất theo cách ứng dụng mong muốn. Lưu descriptor class, name, version và type ID.

### Không ghi thứ tự module

Thứ tự đăng ký có thể ảnh hưởng extension precedence. Lưu danh sách theo thứ tự thực tế.

### Dump toàn bộ configuration hoặc environment

Có thể làm lộ secret và dữ liệu nhạy cảm. Chỉ lưu metadata cần thiết đã được lọc.

### Giả định introspection đọc được mọi cấu hình

Coercion, parser constraints, customizer provenance và extension registry có thể không đọc ngược đầy đủ. Ghi chúng ngay khi cấu hình.

### Chỉ kiểm tra snapshot, không kiểm tra hành vi

Snapshot cho biết feature/module đã đăng ký nhưng không chứng minh serializer/deserializer cho DTO cụ thể hoạt động như mong đợi. Bổ sung contract tests.

## 27. Checklist thiết kế diagnostics

Trước khi đưa mapper diagnostics vào production:

- [ ] Mỗi mapper có mapperId và role ổn định.
- [ ] Snapshot được chụp sau mọi builder/customizer.
- [ ] Snapshot lấy từ mapper instance thực tế đang phục vụ request/message.
- [ ] Jackson Databind, Core và dataformat version được ghi từ runtime.
- [ ] Module inventory có class, name, version, type ID và thứ tự.
- [ ] SerializationFeature, DeserializationFeature và MapperFeature được ghi.
- [ ] Naming strategy, inclusion, locale, timezone và annotation introspector được ghi.
- [ ] Parser constraints và factory policy được ghi từ nguồn cấu hình.
- [ ] Coercion, null policy, mix-in và custom extension có registry riêng khi cần.
- [ ] Configuration provenance và application build ID được lưu.
- [ ] Snapshot không chứa secret hoặc payload người dùng.
- [ ] Endpoint/file snapshot có kiểm soát truy cập.
- [ ] Có test so sánh cấu hình mong đợi và test hành vi thực tế.
- [ ] Có thể diff snapshot giữa các release và instance trong cluster.

## 28. Kết luận

Để chẩn đoán Jackson đáng tin cậy, cần lưu trạng thái cuối cùng của mapper sau khi tất cả module và customizer đã chạy. Snapshot nên nhận diện mapper theo vai trò, format và phiên bản; ghi module theo class/name/version/type ID và thứ tự; ghi feature serialize/deserialize, MapperFeature, naming strategy, annotation introspector, inclusion, locale/timezone và parser policy. Runtime introspection không thể khôi phục đầy đủ mọi coercion, mix-in, customizer hoặc parser constraint, nên hãy ghi provenance và registry ngay tại nơi cấu hình. Trong ứng dụng framework-managed, phải capture đúng ObjectMapper bean thực tế. Snapshot cần được lọc để không lộ secret hoặc payload, có thể so sánh giữa release/instance và đi kèm contract tests. Nhờ vậy, khi hành vi serialize hoặc deserialize thay đổi, nhóm vận hành có thể xác định mapper, module, feature và nguồn cấu hình gây khác biệt thay vì phỏng đoán từ file cấu hình.
