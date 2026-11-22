# Đánh giá đổi API và module khi chuyển dòng phiên bản Jackson

Nâng Jackson từ một minor/patch release lên bản mới trong cùng major line thường ít ảnh hưởng hơn so với chuyển từ Jackson 2.x sang Jackson 3.x. Khi đổi major line, ứng dụng phải xử lý đồng thời dependency coordinates, package Java, baseline JDK, module, custom serializer/deserializer và integration với framework. Việc code biên dịch thành công cũng chưa chứng minh JSON wire contract còn tương thích.

Một lần migration an toàn cần đánh giá ba lớp riêng:

1. **Build/source compatibility:** project có resolve đúng dependency và compile được với API mới không?
2. **Runtime behavior:** mapper, module, annotation, coercion, date/time và exception có còn hoạt động như trước không?
3. **Wire compatibility:** JSON gửi/nhận có giữ nguyên tên field, kiểu dữ liệu, null semantics, discriminator và format mà consumer mong đợi không?

Bài học này tập trung vào quy trình đánh giá và chuyển từ Jackson 2.x sang Jackson 3.x, đồng thời áp dụng được cho các lần nâng cấp lớn khác. Các ví dụ Maven/Gradle minh họa hai release line; luôn dùng đúng version được Spring Boot hoặc dependency management của dự án hỗ trợ.

## 1. Phân biệt nâng cấp trong major line và migration sang major mới

Không phải mọi lần tăng version đều có cùng mức rủi ro.

| Thay đổi | Mức độ thường gặp | Việc cần làm |
|---|---|---|
| Patch release trong cùng major | Thấp đến trung bình | Đọc release notes/security fixes, chạy regression tests |
| Minor release trong cùng major | Trung bình | Kiểm tra API mới/deprecated, default và module compatibility |
| Jackson 2.x sang 3.x | Cao | Đổi dependency/package, kiểm tra JDK, framework integration và behavior |
| Thay một module riêng lẻ | Trung bình đến cao | Kiểm tra module có cùng release line và tương thích Databind |
| Đổi Spring Boot major | Cao | Đánh giá cả Spring, Jackson, HTTP converter/codec và dependency graph |

Không xem việc đổi jackson-databind là toàn bộ migration. Jackson gồm nhiều artifact: Core, Databind, Annotations, datatype modules, dataformat modules và các module tích hợp ngôn ngữ/framework.

Nếu một ứng dụng nâng Spring Boot major đồng thời nâng Jackson major, cần xác định lỗi đến từ thay đổi framework hay Jackson. Tách các thay đổi thành từng bước hoặc ít nhất có commit/branch rõ ràng để dễ khoanh vùng.

## 2. Những thay đổi nền tảng khi chuyển Jackson 2 sang Jackson 3

Jackson 3 là một major line với thay đổi source/binary compatibility. Các khác biệt nền tảng cần đưa vào inventory:

- Package Java chính chuyển từ com.fasterxml.jackson.* sang tools.jackson.*.
- Maven group ID của các artifact Jackson chuyển sang các group tools.jackson....
- Jackson 3 yêu cầu Java 17 trở lên; ứng dụng còn chạy JDK thấp hơn không thể chỉ thay dependency rồi tiếp tục build.
- Các module và integration phải là bản tương thích với Jackson 3; module Jackson 2 không thể đăng ký trực tiếp vào mapper Jackson 3.
- Spring Boot/Spring Framework release line quyết định Jackson integration nào được hỗ trợ và converter/codec nào được dùng.
- API, SPI và một số default có thể thay đổi; cần đối chiếu migration guide/release notes của đúng version đích.

Ví dụ về package:

| Jackson 2.x | Jackson 3.x |
|---|---|
| com.fasterxml.jackson.core.JsonParser | tools.jackson.core.JsonParser |
| com.fasterxml.jackson.core.JsonFactory | tools.jackson.core.JsonFactory |
| com.fasterxml.jackson.databind.ObjectMapper | tools.jackson.databind.ObjectMapper |
| com.fasterxml.jackson.databind.JsonNode | tools.jackson.databind.JsonNode |
| com.fasterxml.jackson.annotation.JsonProperty | tools.jackson.annotation.JsonProperty |
| com.fasterxml.jackson.datatype.jsr310.JavaTimeModule | tools.jackson.datatype.jsr310.JavaTimeModule |

Đây là thay đổi package có hệ thống. Một file source có thể cần đổi import ở nhiều vị trí, kể cả test, custom module, mix-in, helper và annotation trên DTO.

Không dùng search/replace mù quáng trên toàn repository. Một số chuỗi com.fasterxml.jackson có thể xuất hiện trong tài liệu, tên cấu hình, reflection string, metadata hoặc dependency của thư viện khác. Thay đổi theo source imports và build coordinates, sau đó kiểm tra diff.

## 3. Java baseline và toolchain

Jackson 3 đặt baseline Java 17. Trước khi đổi dependency, kiểm tra:

- JDK dùng để chạy build trên máy developer.
- JDK toolchain trong Gradle hoặc Maven compiler configuration.
- JDK của CI.
- JDK runtime trong container/production.
- JDK của plugin build, annotation processor và test runtime.

Gradle toolchain ví dụ:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Maven compiler ví dụ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đừng chỉ đổi sourceCompatibility mà bỏ qua runtime. Bytecode có thể được compile theo target cao hơn môi trường production đang chạy.

Nếu ứng dụng vẫn phải hỗ trợ runtime Java thấp hơn 17, cần giữ Jackson 2.x hoặc thiết kế một tiến trình nâng cấp runtime trước khi chuyển Jackson 3.

## 4. Dependency coordinates và BOM

Jackson 2 và Jackson 3 dùng các group ID khác nhau. Cần đổi đồng bộ cả BOM lẫn các artifact trực tiếp.

Ví dụ khái quát với Maven:

~~~xml
<!-- Jackson 2.x -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<!-- Jackson 3.x: dùng BOM của release line 3.x -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>tools.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Ví dụ Gradle cho Jackson 3:

~~~groovy
dependencies {
    implementation(platform("tools.jackson:jackson-bom:3.x.y"))
    implementation("tools.jackson.core:jackson-databind")
    implementation("tools.jackson.datatype:jackson-datatype-jsr310")
}
~~~

Tên group/artifact ở các dòng module phản ánh release line tương ứng. Hãy kiểm tra BOM và repository metadata của version đích trước khi chốt tọa độ, nhất là với module bên thứ ba.

Nếu dùng Spring Boot, ưu tiên BOM của Spring Boot đang chọn. Không override riêng jackson-databind hoặc SnakeYAML/CBOR/YAML module nếu Boot chưa hỗ trợ tổ hợp đó. Nếu buộc phải override, ghi rõ lý do và kiểm tra dependency graph/runtime.

### 4.1. Những artifact cần tìm trong dự án

Không chỉ tìm jackson-databind. Hãy rà soát:

- jackson-core
- jackson-annotations
- jackson-databind
- jackson-datatype-*
- jackson-module-*
- jackson-dataformat-*
- Jackson integration của Spring Boot/Spring Framework
- Jackson module do thư viện nội bộ hoặc bên thứ ba cung cấp
- Test fixtures, plugin và code generation có phụ thuộc Jackson

Dependency có thể được kéo gián tiếp bởi Spring Boot starter, HTTP client, search client, database library, message broker hoặc SDK. Một artifact 2.x còn sót có thể gây compile/runtime conflict hoặc làm hai mapper thế hệ khác nhau xuất hiện trong cùng ứng dụng.

## 5. Kiểm tra dependency graph trước và sau migration

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson,tools.jackson
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Có thể dùng dependency insight để tìm ai kéo một module cũ vào:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Sau migration, kiểm tra:

- Các artifact Jackson trong runtime đều thuộc release line dự định.
- Không còn com.fasterxml.jackson.* module 2.x trong classpath ứng dụng đã chuyển hoàn toàn sang 3.x.
- Module ngoài đã có bản hỗ trợ Jackson 3.
- Không có version bị force hoặc conflict resolution chọn ngoài dự kiến.
- CI và production dùng cùng lockfile/BOM.
- Dependency của test cũng không kéo Jackson 2 trở lại.

Đừng suy luận từ build file rằng dependency graph đã sạch. Dependency mediation có thể chọn version khác với version khai báo trực tiếp.

## 6. Source migration: đổi import và API

Sau khi chọn dependency set và JDK, cập nhật imports theo package mới.

Ví dụ Jackson 2:

~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .build();
~~~

Tương ứng Jackson 3:

~~~java
import tools.jackson.core.JsonFactory;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

ObjectMapper mapper = JsonMapper.builder()
    .build();
~~~

Đây là ví dụ về thay package cho API tương ứng; không có nghĩa mọi method/constructor của mọi class đều giữ nguyên. Với custom code, đọc Javadoc và migration notes của đúng version 3.x.

Các vị trí thường bị bỏ sót:

- Import trong production source.
- Test source và test utilities.
- Annotation trên DTO/record.
- Custom serializer/deserializer.
- SimpleModule và module setup code.
- Mix-in class.
- Exception handler và code phân loại lỗi.
- Helper nhận JsonParser, JsonGenerator, JsonNode hoặc ObjectMapper.
- Reflection/class name string.
- Tài liệu ví dụ và code snippet được compile trong test.

Nếu thư viện nội bộ công khai API nhận com.fasterxml.jackson.databind.ObjectMapper, việc đổi sang tools.jackson.databind.ObjectMapper là thay đổi API của chính thư viện đó. Cần có version mới và migration note cho consumer, không thể chỉ đổi import bên trong mà giữ binary compatibility.

## 7. Đổi annotation và model contract

Annotation cũng thuộc package Jackson và cần đổi cùng release line:

~~~java
// Jackson 2
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
~~~

~~~java
// Jackson 3
import tools.jackson.annotation.JsonProperty;
import tools.jackson.annotation.JsonIgnore;
~~~

Các annotation có thể giữ tên và mục đích tương tự, nhưng cần kiểm tra API và behavior thực tế của version đích.

Rà soát các nhóm annotation:

- JsonProperty, JsonAlias, JsonIgnore
- JsonInclude, JsonFormat
- JsonCreator, JsonValue
- JsonTypeInfo, JsonSubTypes, JsonTypeName
- JsonView, JsonFilter
- JsonIdentityInfo
- JsonSerialize, JsonDeserialize
- Mix-in annotations

Test cả serialize lẫn deserialize. Một annotation có thể chỉ ảnh hưởng một chiều, hoặc behavior khi đặt trên field/getter/constructor parameter có thể thay đổi do introspection/defaults.

Đặc biệt, không coi migration package là đủ cho polymorphic type. Type ID, default typing, subtype allowlist và cách xử lý unknown subtype là phần contract và security boundary.

## 8. Chuyển custom serializer/deserializer và module SPI

Code mở rộng Jackson thường phụ thuộc trực tiếp vào các lớp Core/Databind. Đây là khu vực dễ phát sinh compile error sau đổi major.

Jackson 2 module ví dụ:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public class MoneySerializer extends JsonSerializer<Money> {
    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {
        generator.writeString(value.toPlainString());
    }
}
~~~

Trong Jackson 3, các type tương ứng chuyển sang package tools.jackson.*. Nhưng hãy kiểm tra signature của serialize, exception type, provider/context và method trên generator trong đúng version. Không thay package rồi mặc định toàn bộ SPI tương thích.

Rà soát:

- JsonSerializer và JsonDeserializer.
- ContextualSerializer / ContextualDeserializer.
- ResolvableSerializer / ResolvableDeserializer.
- BeanSerializerModifier và BeanDeserializerModifier.
- Serializers / Deserializers.
- SimpleModule và Module.SetupContext.
- TypeSerializer / TypeDeserializer.
- KeySerializer / KeyDeserializer.
- ValueInstantiator, AnnotationIntrospector, TypeResolverBuilder.
- SerializerProvider, DeserializationContext, DatabindContext.

Các module nên được biên dịch và phát hành lại với Jackson 3. Không đưa module Jackson 2 vào mapper Jackson 3 chỉ vì class của nó có cùng tên đơn giản.

### 8.1. Tách module nghiệp vụ khỏi Jackson khi có thể

Nếu thư viện nội bộ có nhiều custom serializer, cân nhắc tách logic chuyển đổi nghiệp vụ thành lớp độc lập, rồi để adapter Jackson 2 và adapter Jackson 3 gọi cùng logic đó.

~~~text
                 Domain conversion rules
                         |
               +---------+---------+
               |                   |
        Jackson 2 adapter    Jackson 3 adapter
               |                   |
        Mapper 2.x           Mapper 3.x
~~~

Cách này hữu ích khi cần giai đoạn chuyển tiếp hoặc một thư viện phải hỗ trợ hai nhánh ứng dụng. Adapter vẫn cần được compile riêng theo đúng dependency line.

Không cố dùng cùng một class serializer implement hai SPI khác package. Hai major line có các type system khác nhau dù tên class tương tự.

## 9. Module auto-discovery và đăng ký tường minh

Một ứng dụng có thể đăng ký module bằng nhiều cách:

- Gọi registerModule(...).
- Dùng findAndRegisterModules() hoặc cơ chế discovery của release line.
- Đăng ký module qua Spring bean/customizer.
- Dùng builder có module được cấu hình sẵn.

Khi migration, đừng thay đổi đồng thời cách discovery và module set nếu không cần. Một module có thể không còn được tìm thấy tự động do artifact, service metadata hoặc integration thay đổi.

Ưu tiên một cách đăng ký dễ quan sát. Với Spring, dùng extension point chính thức của Spring Boot release line. Với ứng dụng độc lập, builder/factory có thể đăng ký module tường minh.

Ví dụ nguyên tắc:

~~~java
JsonMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .addModule(new MoneyModule())
    .build();
~~~

Cú pháp cụ thể phải khớp API version đích. Quan trọng là danh sách module được xác định rõ và có test xác nhận module thực sự hoạt động.

## 10. Spring Boot và Spring Framework là một phần của migration

Không nâng Jackson độc lập với Spring mà không kiểm tra compatibility matrix. Spring Boot quản lý dependency versions và cung cấp auto-configuration, builder, HTTP converter/codec và test slice.

Khi đổi Spring Boot major, hãy xác định:

- Release line đó hỗ trợ Jackson 2 hay Jackson 3 làm integration chính.
- Package và class của ObjectMapper builder/customizer được dùng.
- Module bean nào được auto-register.
- MVC converter và WebFlux codec nào được tạo.
- JsonComponent hoặc serializer scanning có thay đổi không.
- JsonTest và test auto-configuration có load đúng module không.
- Các thư viện starter nội bộ đã được nâng tương thích chưa.

Trong ứng dụng Spring MVC, Jackson tham gia qua message converter. WebFlux dùng encoder/decoder codec. Tên class và extension point có thể thay đổi theo Spring Framework/Boot release line; không sao chép cấu hình converter của một major version vào major khác mà chưa kiểm tra API.

### 10.1. Đừng mang customizer cũ sang framework mới theo tên

Một ứng dụng Spring Boot 2/3 có thể dùng Jackson2ObjectMapperBuilderCustomizer. Khi framework chuyển sang Jackson 3, hãy dùng customizer/builder được release line mới công bố. Hậu tố 2 trong tên class là tín hiệu API gắn với integration Jackson 2, không phải một adapter đa phiên bản.

Nếu ứng dụng cần hỗ trợ nhiều Boot major, tách cấu hình Spring theo source set/module hoặc phát hành starter riêng theo release line thay vì cố compile một cấu hình duy nhất với hai bộ API.

### 10.2. Kiểm tra mapper thực tế được HTTP layer dùng

Inject ObjectMapper trong service chưa chứng minh converter/codec dùng đúng instance. Kiểm thử HTTP integration để xác nhận:

- Request body được deserialize theo module mới.
- Response dùng naming strategy và inclusion policy mong muốn.
- Date/time có wire format ổn định.
- Unknown property và enum policy đúng.
- Custom serializer/deserializer hoạt động qua endpoint thật.

## 11. Đánh giá thay đổi default và coercion

Một major upgrade có thể thay đổi default, kể cả khi code không còn compile error. Không giả định mapper mới có cùng semantics với mapper cũ.

Những nhóm behavior cần so sánh:

| Nhóm | Trường hợp cần kiểm tra |
|---|---|
| Unknown property | Từ chối hay bỏ qua field lạ |
| Scalar coercion | "12" vào integer, decimal vào integer, boolean thành string |
| Null/missing | Field thiếu, explicit null, default value |
| Enum | Chữ hoa/thường, unknown enum, JsonValue |
| Duplicate property | Key JSON trùng và cách phát hiện |
| Polymorphism | Type ID, unknown subtype, default typing |
| Visibility | Getter/field/record component được phát hiện |
| Creator | Constructor, record, parameter names |
| Date/time | Timestamp/string, timezone, precision |
| Number | BigDecimal, BigInteger, exponent và scale |
| Binary | Base64 variant, padding, whitespace |
| Exception | Type exception, path, location và error message |

Nếu một behavior là contract, cấu hình nó tường minh thay vì dựa vào default. Nếu behavior không phải contract, vẫn cần test để phát hiện thay đổi có ảnh hưởng thực tế.

Đặc biệt kiểm tra coercion. Một payload JSON sai kiểu có thể trước đây được ép thành giá trị hợp lệ, nhưng sau nâng cấp lại bị từ chối, hoặc ngược lại. Cả hai đều có thể ảnh hưởng client.

## 12. Date/time và module JDK

Ứng dụng dùng Instant, LocalDate, OffsetDateTime, ZonedDateTime hoặc Optional cần xác nhận module tương ứng có mặt và được đăng ký.

Các điểm cần kiểm tra:

- Module artifact thuộc đúng major line.
- Auto-discovery hoặc Spring registration vẫn hoạt động.
- WRITE_DATES_AS_TIMESTAMPS và các feature tương đương có behavior đúng.
- Timezone không bị áp dụng sai cho LocalDateTime.
- Epoch seconds/milliseconds không đổi đơn vị.
- Precision phần nano/micro/millisecond được giữ theo contract.
- Null và Optional có semantics nhất quán.

Ví dụ contract test:

~~~java
@Test
void writesInstantAsExpectedWireValue() throws Exception {
    Instant instant = Instant.parse("2026-11-12T10:30:00Z");

    String json = mapper.writeValueAsString(instant);

    assertEquals("\"2026-11-12T10:30:00Z\"", json);
}
~~~

Không chỉ test round-trip bằng cùng mapper. Serializer và deserializer cùng thay đổi theo một cách vẫn có thể round-trip thành công trong khi wire value đã đổi. Hãy assert giá trị JSON mà client nhìn thấy.

## 13. Number, null và property inclusion

Kiểm tra kỹ những field mà client có thể phân biệt:

- Missing property.
- Property có giá trị null.
- Empty string.
- Zero.
- false.
- Empty array/object.

Ví dụ, NON_NULL khác NON_EMPTY; thay đổi inclusion có thể làm response mất field mà client cũ đang dựa vào.

Với BigDecimal, kiểm tra cả giá trị và scale nếu scale thuộc contract. Với integer lớn, kiểm tra consumer JavaScript hoặc hệ thống khác có thể giữ chính xác giá trị hay không.

Không thay đổi number thành string hoặc ngược lại trong migration chỉ để làm test qua. Nếu wire representation cần thay đổi, xử lý như một API versioning decision riêng.

## 14. Polymorphism, default typing và security

Các ứng dụng dùng polymorphic deserialization cần đánh giá kỹ hơn migration package.

Rà soát:

- JsonTypeInfo và JsonSubTypes.
- JsonTypeName.
- Id.CLASS / Id.MINIMAL_CLASS.
- Default typing và PolymorphicTypeValidator.
- Custom TypeResolverBuilder.
- Unknown type ID và fallback/default implementation.

Type metadata có thể là một phần của JSON contract. Nếu output dùng class name, đổi package com.fasterxml sang tools có thể làm type ID hoặc class metadata khác đi tùy cách ứng dụng cấu hình. Đây có thể là breaking change với dữ liệu lưu lâu dài hoặc consumer phụ thuộc type string.

Ưu tiên logical type ID ổn định như kind: "card" thay cho tên class. Chỉ cho phép subtype trong allowlist. Không nới default typing để làm payload cũ deserialize thành công mà chưa đánh giá security impact.

Nếu cần đọc dữ liệu cũ, có thể tạo một migration reader riêng chỉ chấp nhận các type ID/shape được kiểm soát, sau đó ghi lại bằng schema mới.

## 15. Dataformat và module ngoài

Ngoài JSON, ứng dụng có thể dùng YAML, CBOR, Smile, XML, CSV hoặc Avro. Mỗi dataformat module có release line và compatibility riêng.

Với từng module:

1. Xác nhận artifact có bản tương thích Jackson 3.
2. Xác nhận group ID và package mới.
3. Xác nhận parser/generator API.
4. Kiểm tra behavior riêng của format.
5. Kiểm tra dependency bắc cầu (ví dụ YAML parser library).
6. Chạy test fixture cũ và mới.
7. Kiểm tra media type, framing và encoding ở transport.

Không giả định một module Jackson 2 có thể chạy với Core/Databind 3. Một số module bên thứ ba có thể chưa hỗ trợ Jackson 3; khi đó cần giữ adapter riêng, thay thư viện hoặc trì hoãn migration.

Với module có plugin SPI hoặc custom factory, kiểm tra cả ServiceLoader metadata và registration code. Đổi package Java nhưng quên file service provider có thể khiến module không được phát hiện.

## 16. Kiểm tra annotation processing, Kotlin và record

Ứng dụng có Kotlin, Java record, constructor-based DTO hoặc annotation processor nên thêm các test riêng.

- Kotlin module phải tương thích Jackson 3 và Kotlin compiler/runtime version của ứng dụng.
- Record/constructor creator phải bind đúng tên property.
- Nullability/default parameter của Kotlin cần được giữ đúng.
- Mix-in phải còn gắn đúng method/constructor signature.
- Annotation trên record component, field và accessor cần được kiểm tra.
- Lombok-generated getter/constructor không nên làm thay đổi property visibility ngoài ý muốn.

Đừng giả định module Kotlin hoặc parameter names module tự động tương thích chỉ vì tên artifact tương tự. Dùng bản module đúng release line và test DTO đại diện.

## 17. Thiết kế bộ regression tests trước khi đổi

Trước migration, tạo một baseline từ mapper đang chạy production. Test nên tập trung vào wire contract và các payload thật đã được sanitize.

Một tập fixture hữu ích gồm:

- JSON request/response đại diện cho từng endpoint.
- Timestamp có Z, offset dương/âm và precision khác nhau.
- Decimal, integer lớn, exponent và trailing zeros.
- Null, missing, empty string, zero và false.
- Enum hợp lệ/không hợp lệ.
- Unknown property và duplicate key.
- Polymorphic type ID và subtype không được phép.
- Unicode, newline, escaped quote/backslash.
- Base64 binary và payload lớn.
- YAML/CBOR/Smile nếu ứng dụng sử dụng.
- Payload cũ được lưu trong database, queue hoặc object storage.

Test so sánh semantic JSON khi thứ tự field/whitespace không phải contract. Nếu payload được ký số, hash hoặc cache theo byte chính xác, cần test canonicalization/byte output riêng.

### 17.1. Dùng fixture để so sánh hai mapper

Có thể tạo test chạy cùng một bộ DTO/payload qua mapper 2.x và mapper 3.x trong hai module/build riêng hoặc hai tiến trình độc lập.

~~~text
              Shared JSON fixtures
                       |
             +---------+---------+
             |                   |
        Jackson 2 app       Jackson 3 app
             |                   |
        JSON outputs        JSON outputs
             |                   |
             +---------+---------+
                       |
                Contract comparison
~~~

Không cố đưa type từ cả hai major line vào cùng một method signature. Package khác nhau nên có thể coexist ở một số classpath, nhưng module/SPI của hai line không thể trộn. Cách cô lập bằng module/build/process thường dễ kiểm soát hơn.

### 17.2. Semantic comparison và byte comparison

Semantic comparison phù hợp khi thứ tự object property, whitespace và cách viết escape không quan trọng. Parse cả hai output thành tree rồi so sánh cấu trúc và giá trị.

Byte comparison cần thiết khi có:

- Chữ ký số trên JSON bytes.
- Hash/cache key tính trên representation.
- Canonical JSON.
- Snapshot hoặc protocol yêu cầu exact bytes.
- Consumer phụ thuộc thứ tự field/format đặc biệt.

Nếu cần byte-stable JSON, hãy định nghĩa canonicalization riêng. Đừng mặc định hai phiên bản Jackson sẽ phát cùng byte sequence.

## 18. Quy trình migration theo từng bước

Một kế hoạch có thể chia thành các giai đoạn sau.

### Giai đoạn 1: Inventory

- Ghi lại JDK, Spring Boot, Spring Framework và Jackson versions.
- Liệt kê artifact Jackson trực tiếp/gián tiếp.
- Tìm toàn bộ imports com.fasterxml.jackson.
- Liệt kê custom modules, serializers, deserializers, mix-ins và annotation.
- Xác định data formats và nơi lưu JSON lâu dài.
- Thu thập fixture request/response thực tế đã loại dữ liệu nhạy cảm.

### Giai đoạn 2: Chốt compatibility set

- Chọn JDK tối thiểu.
- Chọn Spring Boot/Framework release line hỗ trợ Jackson đích.
- Chọn Jackson BOM.
- Chọn phiên bản module datatype/dataformat.
- Xác nhận module bên thứ ba có bản tương thích.
- Xác định các thư viện nội bộ cần phát hành lại.

### Giai đoạn 3: Dependency và source

- Thay BOM/group IDs/artifact versions.
- Đổi package imports trong source/test.
- Cập nhật custom module và SPI.
- Chuyển builder/customizer theo API mới.
- Cập nhật annotation và mix-in.
- Xử lý compile errors theo migration guide, không sửa bằng cast hoặc reflection workaround tùy tiện.

### Giai đoạn 4: Runtime configuration

- Đăng ký module tường minh.
- Xác định mapper Spring dùng.
- Cấu hình default cần giữ nguyên.
- Kiểm tra converter/codec.
- Kiểm tra exception handler và logging.
- Kiểm tra security cho polymorphic deserialization.

### Giai đoạn 5: Regression

- Chạy unit tests cho serializer/deserializer.
- Chạy fixture tests.
- Chạy Spring context test.
- Chạy MockMvc/WebTestClient.
- So sánh JSON semantic và exact bytes theo yêu cầu.
- Chạy integration test với database, queue và external API nếu có.

### Giai đoạn 6: Rollout

- Phát hành lên môi trường test/staging.
- Chạy canary hoặc một nhóm traffic nhỏ nếu kiến trúc cho phép.
- Theo dõi deserialize failures, HTTP 4xx/5xx, consumer lag và message DLQ.
- So sánh payload output và log lỗi đã sanitize.
- Giữ rollback artifact/config rõ ràng.
- Chỉ xóa compatibility adapter sau khi dữ liệu và consumer cũ đã được xử lý.

## 19. Migration dữ liệu đã lưu và message đang chờ

Nâng Jackson không chỉ ảnh hưởng request mới. Dữ liệu JSON đã ghi vào database, cache, file hoặc message queue có thể tồn tại nhiều năm.

Cần xác định:

- Payload cũ có chứa class-name type ID không?
- Có field date/number được ghi theo default cũ không?
- Có dữ liệu dùng alias/legacy property name không?
- Có duplicate key hoặc scalar YAML mơ hồ không?
- Queue có message được producer cũ gửi nhưng consumer mới đọc không?
- Cache có key/value cần invalidation hoặc migration không?

Một chiến lược an toàn là đọc schema cũ bằng reader tương thích, chuyển thành domain object, rồi ghi lại bằng schema chuẩn mới. Không nên dùng một mapper permissive vô hạn để nhận mọi dạng payload.

Với message queue, giữ consumer có thể đọc payload từ producer cũ trong thời gian rollout. Nếu thay đổi wire contract, version hóa event/schema và triển khai consumer trước producer khi cần.

## 20. Dual-read và dual-write có kiểm soát

Trong migration kéo dài, đôi khi cần hai adapter:

- Reader cũ đọc payload legacy.
- Reader mới đọc payload mới.
- Writer mới chỉ phát schema canonical sau khi consumer đã sẵn sàng.
- Một adapter chuyển dữ liệu legacy sang domain model trung lập.

~~~text
Legacy JSON --------> Legacy reader ----+
                                         |
                                         v
                                    Domain model
                                         |
New JSON ------------> New reader -------+
                                         |
                                         v
                                    New writer
                                         |
                                         v
                                  Canonical JSON
~~~

Không nhất thiết dual-write cả hai dạng. Dual-write có thể tạo nguồn dữ liệu mâu thuẫn, tăng chi phí và khiến rollback khó hơn. Chỉ duy trì hai format nếu có yêu cầu consumer cụ thể và có kế hoạch kết thúc.

Nếu cần phân biệt schema, dùng version field hoặc envelope rõ ràng. Không đoán version bằng cách thử deserialize tuần tự nhiều DTO khác nhau nếu các schema có thể bị parse thành công một cách mơ hồ.

## 21. Quan sát runtime sau nâng cấp

Trong rollout, theo dõi các chỉ số liên quan trực tiếp tới serialization:

- Số lượng JSON parse/mapping exceptions theo endpoint/message type.
- Tỷ lệ HTTP 400/415/500 và lỗi response serialization.
- Số message vào dead-letter queue.
- Consumer retry/lag.
- Kích thước request/response.
- Latency và allocation/GC trong các endpoint payload lớn.
- Lỗi parse date/time, enum, number và polymorphic type.
- Tỷ lệ payload legacy và payload mới.

Không log raw payload để chẩn đoán migration. Dùng request ID, schema version, endpoint/message type và exception category đã sanitize.

Nếu lỗi tăng sau rollout, xác định đó là compile/runtime integration, payload incompatibility hay lỗi nghiệp vụ downstream. Giữ canary/rollback window đủ dài để quan sát cả batch và queue backlog.

## 22. Rollback và khả năng tương thích ngược

Rollback không chỉ là deploy lại binary cũ. Nếu version mới đã ghi dữ liệu theo representation mà version cũ không đọc được, rollback ứng dụng có thể làm hệ thống mất khả năng xử lý dữ liệu mới.

Trước khi rollout, trả lời:

- Writer mới có phát JSON mà reader cũ không hiểu không?
- Có thay đổi type ID, date/time format, enum value hoặc numeric type không?
- Có ghi dữ liệu mới vào database/cache/queue không?
- Có cần dual-read trong cửa sổ rollback không?
- Có thể replay message hoặc tái tạo cache không?
- Có migration dữ liệu ngược hay chỉ forward migration?

Trong thời gian rollback window, nên giữ wire format tương thích nếu có thể. Nếu phải thay đổi format, version hóa rõ và bảo đảm reader cũ không bị buộc đọc payload mới.

## 23. Checklist quyết định có thể nâng cấp hay chưa

| Nhóm | Điều kiện cần xác nhận |
|---|---|
| JDK | Runtime và build toolchain đáp ứng baseline của Jackson đích |
| Spring | Spring Boot/Framework release line hỗ trợ integration tương ứng |
| Dependencies | Core, Databind, Annotations và modules cùng release line |
| Source | Imports, annotations, custom SPI và exception handlers đã cập nhật |
| Modules | Module bên thứ ba có bản tương thích |
| Defaults | Coercion, null, enum, date/time và visibility đã được so sánh |
| Security | Polymorphic typing và subtype allowlist đã được kiểm tra |
| Wire contract | Fixture cũ/new payload cho kết quả mong đợi |
| Persistence | Dữ liệu JSON lưu lâu dài vẫn đọc được hoặc có migration |
| Tests | Unit, context, HTTP và consumer contract tests đã chạy |
| Operations | Metrics, canary và rollback plan sẵn sàng |

Nếu một điều kiện chưa xác nhận, hãy ghi nhận blocker cụ thể. Không đánh đồng việc build thành công với migration hoàn tất.

## 24. Các lỗi thường gặp

**Chỉ đổi version của jackson-databind.** Core, annotations và module khác có thể còn ở major line cũ.

**Đổi package nhưng không đổi dependency coordinates.** Source có thể import tools.jackson.* nhưng build vẫn kéo artifact 2.x.

**Bỏ qua JDK baseline.** Build/production runtime thấp hơn Java 17 không đáp ứng yêu cầu Jackson 3.

**Ép module bên thứ ba lên classpath mới.** Module compile với Jackson 2 không tự tương thích Jackson 3 vì SPI và package khác nhau.

**Tin rằng compile pass chứng minh wire compatibility.** Default, coercion, date/time và type metadata có thể đổi mà source vẫn compile.

**Chỉ test round-trip bằng một mapper.** Serializer/deserializer cùng đổi có thể che giấu việc JSON output đã khác.

**Nâng Spring Boot và Jackson trong một bước không có baseline.** Khi lỗi xuất hiện sẽ khó xác định nguồn thay đổi.

**Dùng mapper mới để đọc mọi payload cũ mà không giới hạn.** Compatibility reader cần schema/allowlist rõ ràng, nhất là với polymorphic typing.

**Dual-write vô thời hạn.** Hai representation có thể lệch nhau và làm rollback phức tạp.

**Log raw payload khi điều tra.** JSON có thể chứa credential, PII hoặc dữ liệu nội bộ; log metadata đã sanitize.

## 25. Ghi nhớ

- Phân biệt nâng cấp trong cùng major line với migration Jackson 2.x sang 3.x; hai việc có mức rủi ro khác nhau.
- Jackson 3 đổi package từ com.fasterxml.jackson.* sang tools.jackson.*, đổi artifact group IDs và yêu cầu Java 17 trở lên.
- Nâng Core, Databind, Annotations, datatype/dataformat modules và integration đồng bộ theo release line.
- Dùng BOM/Dependency Management phù hợp với Spring Boot; kiểm tra runtime dependency graph thay vì chỉ đọc build file.
- Chuyển custom serializer/deserializer, module SPI, mix-in, annotation và exception handling theo API đích.
- Không trộn module Jackson 2 với mapper Jackson 3.
- Kiểm tra Spring Boot/Framework converter, codec, builder và customizer; API integration phụ thuộc release line.
- So sánh default behavior của coercion, null, enum, date/time, number, polymorphism và visibility.
- Dùng fixture/contract tests để so sánh wire JSON; round-trip đơn lẻ không đủ chứng minh compatibility.
- Đánh giá dữ liệu JSON đã lưu, message queue và cache, không chỉ request mới.
- Rollout theo giai đoạn, quan sát lỗi runtime và chuẩn bị rollback dựa trên khả năng đọc dữ liệu đã ghi.
- Chỉ coi migration hoàn tất khi source, runtime behavior, wire contract và vận hành đều được xác nhận.

