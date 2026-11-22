# Quản lý module hỗ trợ kiểu dữ liệu Java

Jackson được thiết kế theo hướng mở rộng: phần lõi xử lý JSON và ánh xạ dữ liệu, còn nhiều kiểu dữ liệu Java và định dạng khác được hỗ trợ thông qua các module. Khi ứng dụng bắt đầu dùng các kiểu như Optional, Instant, LocalDate, Kotlin data class hoặc XML, YAML, CSV, việc chọn và quản lý module trở thành một phần của thiết kế dependency.

Quản lý module tốt cần giải quyết ba việc: **chọn đúng module cho kiểu dữ liệu hoặc định dạng cần hỗ trợ, giữ các artifact Jackson tương thích phiên bản, và đăng ký module nhất quán vào ObjectMapper đang thực sự được ứng dụng sử dụng.** Chỉ thêm dependency mà không kiểm tra mapper được cấu hình thế nào có thể khiến ứng dụng vẫn không xử lý được kiểu dữ liệu mong muốn.

## 1. Module Jackson là gì?

Trong Jackson 2.x, một module là một gói mở rộng có thể đăng ký vào ObjectMapper hoặc JsonMapper. Module có thể bổ sung serializer, deserializer, hỗ trợ kiểu dữ liệu, quy tắc introspection, mix-in hoặc các hành vi liên quan đến quá trình chuyển đổi.

Cần phân biệt hai khái niệm:

- **Jackson module:** phần mở rộng ở cấp thư viện, cung cấp khả năng xử lý một kiểu dữ liệu hoặc định dạng.
- **Dependency/artifact:** gói được khai báo trong Maven hoặc Gradle để đưa phần mở rộng đó vào classpath của ứng dụng.

Ví dụ, JavaTimeModule là module hỗ trợ các kiểu ngày giờ thuộc java.time. Để dùng module này trong ứng dụng, dự án cần dependency jackson-datatype-jsr310, sau đó module phải được đăng ký vào mapper hoặc được framework tự động đăng ký theo cấu hình của nó.

Luồng hoạt động tổng quát:

~~~text
Java application
      |
      v
ObjectMapper / JsonMapper
      |
      +---- Jackson core + databind
      |
      +---- JavaTimeModule
      |       -> Instant, LocalDate, LocalDateTime, ...
      |
      +---- Jdk8Module
      |       -> Optional, OptionalInt, ...
      |
      +---- Custom Module
              -> kiểu dữ liệu riêng của ứng dụng
~~~

Một dependency có mặt trên classpath chưa chắc đã được mọi ObjectMapper trong ứng dụng sử dụng. Đây là lý do cần hiểu cả dependency management lẫn module registration.

## 2. Các nhóm module thường gặp

### 2.1. Module hỗ trợ kiểu dữ liệu Java

Nhóm này bổ sung khả năng đọc và ghi những kiểu dữ liệu không được xử lý đầy đủ bởi cấu hình Databind cơ bản.

| Module | Artifact | Kiểu dữ liệu hoặc mục đích |
|---|---|---|
| JavaTimeModule | jackson-datatype-jsr310 | Các kiểu trong java.time như Instant, LocalDate, LocalDateTime, OffsetDateTime |
| Jdk8Module | jackson-datatype-jdk8 | Optional, OptionalInt, OptionalLong, OptionalDouble và một số kiểu JDK 8 |
| ParameterNamesModule | jackson-module-parameter-names | Dùng tên tham số constructor khi ánh xạ trong những trường hợp phù hợp |
| KotlinModule | jackson-module-kotlin | Kotlin data class, constructor, nullability và các đặc điểm của Kotlin |
| JodaModule | jackson-datatype-joda | Các kiểu ngày giờ thuộc Joda-Time |
| Hibernate module | jackson-datatype-hibernate* | Một số tích hợp với proxy và collection của Hibernate |

Không nên thêm toàn bộ danh sách chỉ vì chúng cùng thuộc Jackson. Chỉ thêm module khi mô hình dữ liệu hoặc thư viện thực tế của ứng dụng cần nó.

**JavaTimeModule** là module thường cần trong ứng dụng Java hiện đại. Các kiểu java.time không nên được xử lý bằng cách chuyển tùy tiện thành chuỗi ở từng service. Module này giúp serializer và deserializer có hành vi tập trung, nhất quán.

Ví dụ DTO:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.Optional;

public record BookingRequest(
    String customerId,
    LocalDate bookingDate,
    Instant createdAt,
    Optional<String> note
) {}
~~~

Với DTO trên, JavaTimeModule xử lý các kiểu java.time; Jdk8Module bổ sung hỗ trợ Optional. Hai module giải quyết hai nhóm kiểu khác nhau, vì vậy có thể cần cả hai.

**ParameterNamesModule** có ích khi Jackson cần dùng tên tham số constructor để tạo object. Với constructor thông thường, compiler cần giữ metadata tên tham số, thường bằng tùy chọn biên dịch -parameters. Record đã có cơ chế hỗ trợ riêng trong các phiên bản Jackson 2 hiện đại, vì vậy không nên mặc định rằng mọi record đều cần module này.

**KotlinModule** dành cho ứng dụng Kotlin chạy trên JVM. Module giúp Jackson hiểu các constructor và đặc điểm của Kotlin như data class, nullability và tham số có giá trị mặc định. Phiên bản module cần tương thích với dòng Jackson và phiên bản Kotlin mà dự án sử dụng.

Hibernate module có thể hỗ trợ một số proxy và persistent collection, nhưng không nên xem nó là giải pháp mặc định để serialize Entity trực tiếp. Serialization có thể kích hoạt lazy loading, tạo truy vấn ngoài dự kiến hoặc làm lộ quan hệ nội bộ. DTO vẫn là ranh giới an toàn và dễ kiểm soát hơn cho API.

### 2.2. Module hỗ trợ định dạng dữ liệu

Jackson không chỉ xử lý JSON. Các module thuộc nhóm dataformat cho phép sử dụng mô hình Jackson với những định dạng khác.

| Định dạng | Artifact thường gặp | Mapper/API thường dùng |
|---|---|---|
| XML | jackson-dataformat-xml | XmlMapper |
| YAML | jackson-dataformat-yaml | YAMLMapper |
| CSV | jackson-dataformat-csv | CsvMapper |
| CBOR | jackson-dataformat-cbor | ObjectMapper với CBORFactory |
| Smile | jackson-dataformat-smile | ObjectMapper với SmileFactory |
| Avro | jackson-dataformat-avro | AvroMapper |

Ví dụ với XML:

~~~java
import com.fasterxml.jackson.dataformat.xml.XmlMapper;

XmlMapper mapper = new XmlMapper();

String xml = mapper.writeValueAsString(order);
Order restored = mapper.readValue(xml, Order.class);
~~~

Ví dụ với YAML:

~~~java
import com.fasterxml.jackson.dataformat.yaml.YAMLMapper;

YAMLMapper mapper = new YAMLMapper();

String yaml = mapper.writeValueAsString(configuration);
Configuration restored =
    mapper.readValue(yaml, Configuration.class);
~~~

Các ví dụ trên minh họa cách sử dụng API; ứng dụng vẫn cần khai báo artifact tương ứng và kiểm tra các dependency phụ trợ của module. Ví dụ YAML module dựa vào thư viện xử lý YAML bên dưới.

Không nên chọn một dataformat module chỉ vì nó cho phép tái sử dụng ObjectMapper. XML có namespace và mixed content; CSV có quy tắc về delimiter và quoting; YAML có quy tắc kiểu dữ liệu riêng. Nếu cấu trúc định dạng phức tạp, hãy kiểm tra khả năng biểu diễn bằng mapper và chạy thử với tài liệu thật trước khi chốt thiết kế.

### 2.3. Module tùy chỉnh của ứng dụng

Khi ứng dụng có kiểu dữ liệu riêng, có thể viết module riêng để tập trung serializer và deserializer thay vì rải logic chuyển đổi trong nhiều lớp.

Ví dụ, hệ thống có kiểu Money:

~~~java
import java.math.BigDecimal;
import java.util.Currency;

public record Money(
    BigDecimal amount,
    Currency currency
) {}
~~~

Ứng dụng có thể định nghĩa hợp đồng JSON rõ ràng:

~~~json
{
  "amount": "125000.00",
  "currency": "VND"
}
~~~

Serializer và deserializer tương ứng nên được đặt trong một module riêng, chẳng hạn ApplicationJacksonModule. Module có thể đăng ký serializer cho Money và deserializer đọc đúng hai trường amount, currency. Khi đó, các DTO sử dụng Money có cùng quy tắc biểu diễn mà không cần tự chuyển đổi ở từng endpoint.

Không nên đưa mọi quy tắc nghiệp vụ vào module Jackson. Module chỉ nên chịu trách nhiệm biểu diễn và khôi phục kiểu dữ liệu. Kiểm tra số tiền có được phép giao dịch, giới hạn giao dịch hoặc quyền của người dùng vẫn thuộc tầng nghiệp vụ.

## 3. Chọn module theo nhu cầu thực tế

Hãy bắt đầu từ kiểu dữ liệu xuất hiện trong DTO, Entity hoặc hợp đồng trao đổi, sau đó chọn module tương ứng.

| Dấu hiệu trong mô hình dữ liệu | Module nên xem xét | Lưu ý |
|---|---|---|
| Có Instant, LocalDate, LocalDateTime | JavaTimeModule | Thống nhất timezone và format ngày giờ |
| Có Optional hoặc OptionalInt | Jdk8Module | Xác định rõ cách biểu diễn giá trị vắng mặt |
| Dùng constructor parameter name cho POJO | ParameterNamesModule | Kiểm tra compiler có giữ tên tham số |
| Dùng Kotlin data class | KotlinModule | Kiểm tra tương thích Kotlin/Jackson |
| Dùng Joda-Time trong hệ thống cũ | JodaModule | Chỉ giữ nếu mô hình còn sử dụng Joda-Time |
| Dùng Hibernate proxy hoặc collection | Hibernate module khi thực sự cần | DTO thường an toàn hơn cho API |
| Cần xuất XML/YAML/CSV | Dataformat module tương ứng | Kiểm tra tính năng đặc thù của định dạng |
| Có kiểu nghiệp vụ riêng | Module tự viết | Định nghĩa hợp đồng JSON ổn định |

Một ứng dụng có thể cần nhiều module. Ví dụ backend Java dùng Instant, Optional và XML có thể cần JavaTimeModule, Jdk8Module và jackson-dataformat-xml. Tuy nhiên, việc thêm module nên đi kèm một nhu cầu có thể giải thích và kiểm thử được.

## 4. Quản lý phiên bản dependency

### 4.1. Vì sao phải đồng bộ phiên bản?

Jackson gồm nhiều artifact có quan hệ với nhau, chẳng hạn:

- jackson-core: đọc và ghi token JSON.
- jackson-annotations: annotation dùng trong mapping.
- jackson-databind: ánh xạ giữa JSON và Java object.
- jackson-datatype-* và jackson-module-*: các phần mở rộng.
- jackson-dataformat-*: các định dạng dữ liệu bổ sung.

Các artifact cần nằm trong một bộ phiên bản tương thích. Nếu databind thuộc một phiên bản nhưng datatype module lại thuộc một phiên bản khác, ứng dụng có thể gặp lỗi liên kết class, method không tồn tại, lỗi lúc khởi động hoặc lỗi chỉ xuất hiện khi serialize một kiểu dữ liệu cụ thể.

Không nên quản lý phiên bản từng module một cách độc lập nếu chúng thuộc cùng một bộ Jackson. Hãy dùng BOM hoặc dependency management của nền tảng để kiểm soát phiên bản tập trung.

### 4.2. Dùng Jackson BOM với Maven

Ví dụ dự án Java độc lập quản lý phiên bản Jackson bằng BOM:

~~~xml
<properties>
    <jackson.version>2.x.y</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jdk8</artifactId>
    </dependency>
</dependencies>
~~~

Giá trị 2.x.y là chỗ giữ phiên bản Jackson 2 mà dự án đã chọn; thay bằng phiên bản cụ thể được tổ chức phê duyệt. BOM cung cấp version cho các artifact được nó quản lý, vì vậy các dependency bên dưới không phải lặp lại version.

Nếu cần Kotlin module hoặc dataformat module, thêm dependency tương ứng nhưng vẫn để BOM quản lý phiên bản. Không tự thêm version riêng cho từng module trừ khi có lý do tương thích đã được xác minh.

### 4.3. Dùng Jackson BOM với Gradle

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation platform("com.fasterxml.jackson:jackson-bom:$jacksonVersion")

    implementation "com.fasterxml.jackson.core:jackson-databind"
    implementation "com.fasterxml.jackson.datatype:jackson-datatype-jsr310"
    implementation "com.fasterxml.jackson.datatype:jackson-datatype-jdk8"
}
~~~

Khai báo phiên bản tập trung, ví dụ trong gradle.properties:

~~~properties
jacksonVersion=2.x.y
~~~

Nếu module cần XML, thêm:

~~~groovy
implementation "com.fasterxml.jackson.dataformat:jackson-dataformat-xml"
~~~

BOM giúp Gradle áp dụng cùng bộ phiên bản cho các artifact Jackson có trong dependency graph. Nếu dự án dùng version catalog hoặc convention plugin để quản lý dependency, hãy tích hợp BOM vào cơ chế hiện tại thay vì tạo thêm một nơi quản lý phiên bản song song.

### 4.4. Khi Spring Boot quản lý dependency

Trong ứng dụng Spring Boot, nên ưu tiên dependency management do Spring Boot cung cấp. Các starter web thông thường đã đưa Jackson vào classpath và cấu hình mặc định thường đã hỗ trợ các kiểu dữ liệu phổ biến thông qua các module phù hợp.

Ví dụ:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
}
~~~

Nếu dự án cần một module bổ sung chưa có trong starter, có thể thêm dependency module đó và để Spring Boot quản lý phiên bản tương thích.

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "com.fasterxml.jackson.dataformat:jackson-dataformat-xml"
}
~~~

Không nên vừa để Spring Boot quản lý Jackson vừa ép một số artifact Jackson sang phiên bản khác mà không có kiểm tra tương thích. Nếu cần nâng Jackson độc lập với phiên bản do Boot quản lý, phải xem xét toàn bộ bộ artifact, Spring Boot version, các starter và test tích hợp trước khi thay đổi.

## 5. Đăng ký module vào ObjectMapper

Có dependency là bước đầu. Mapper phải thực sự nhận module thì serializer và deserializer của module mới được dùng.

### 5.1. Đăng ký tường minh

Với ứng dụng Java độc lập dùng Jackson 2.x, có thể đăng ký module khi tạo JsonMapper:

~~~java
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jdk8.Jdk8Module;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JacksonConfiguration {

    private JacksonConfiguration() {
    }

    public static JsonMapper createMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .addModule(new Jdk8Module())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
    }
}
~~~

Đăng ký tường minh giúp người đọc biết mapper hỗ trợ những kiểu dữ liệu nào. Nó cũng giúp cấu hình có tính xác định cao, dễ xem xét và kiểm thử.

Trong ví dụ, WRITE_DATES_AS_TIMESTAMPS được tắt để ngày giờ được biểu diễn dưới dạng chuỗi thay vì dạng timestamp/array tùy kiểu. Ứng dụng vẫn phải thống nhất timezone, độ chính xác và định dạng trong hợp đồng API.

### 5.2. Tự động phát hiện module

Jackson 2.x cung cấp khả năng phát hiện module qua Java ServiceLoader:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.findAndRegisterModules();
~~~

Cách này có thể tự tìm các module có khai báo service provider trên classpath. Nó tiện khi ứng dụng có nhiều module và chấp nhận cơ chế discovery của thư viện.

Tuy nhiên, auto-discovery khiến hành vi mapper phụ thuộc vào các dependency hiện có trên classpath. Khi thêm một thư viện mới, tập module được phát hiện có thể thay đổi. Nếu cần cấu hình rõ ràng, dễ dự đoán, hãy đăng ký module tường minh.

Không nên vừa auto-discovery vừa đăng ký lặp module theo nhiều cơ chế mà không hiểu cách Jackson xử lý việc đăng ký. Chọn một chiến lược nhất quán cho từng mapper.

### 5.3. Đăng ký module trong Spring Boot

Trong Spring Boot, ứng dụng thường dùng ObjectMapper do auto-configuration tạo ra. Spring Boot và Jackson builder có cơ chế tích hợp để đăng ký các module phù hợp có trên classpath và các bean Module được khai báo trong context.

Nếu chỉ cần thêm module chuẩn, thường có thể khai báo dependency rồi để cấu hình Boot hiện tại xử lý. Nếu cần cấu hình bổ sung, nên sử dụng Jackson2ObjectMapperBuilderCustomizer hoặc khai báo Module bean theo đúng phiên bản Spring Boot đang dùng.

Ví dụ đăng ký custom module bằng bean:

~~~java
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonModuleConfiguration {

    @Bean
    public SimpleModule applicationJacksonModule() {
        SimpleModule module = new SimpleModule("application-module");

        // Đăng ký serializer/deserializer cho kiểu dữ liệu riêng.
        // module.addSerializer(...);
        // module.addDeserializer(...);

        return module;
    }
}
~~~

Đây là ví dụ khung để minh họa vị trí đăng ký. Khi module có serializer/deserializer thực tế, hãy đăng ký chúng trong bean này hoặc đóng gói thành một Module riêng.

Không nên tạo một ObjectMapper mới tùy tiện trong controller hoặc service. Nếu Spring đang dùng mapper A để đọc request nhưng code nghiệp vụ lại tự tạo mapper B, hai nơi có thể có hành vi khác nhau dù cùng nằm trong một ứng dụng.

### 5.4. Cấu hình mapper trước khi sử dụng

ObjectMapper có thể được dùng đồng thời sau khi cấu hình hoàn tất. Vì vậy, hãy đăng ký module, feature, naming strategy và mix-in trước khi mapper bắt đầu xử lý request.

Tránh kiểu code:

~~~java
ObjectMapper mapper = sharedMapper;

// Một luồng khác có thể đang dùng mapper tại thời điểm này.
mapper.registerModule(new JavaTimeModule());
~~~

Việc thay đổi cấu hình sau khi mapper đã được chia sẻ có thể tạo hành vi khó dự đoán giữa các luồng hoặc giữa các lần xử lý. Nếu cần một cấu hình khác, hãy tạo mapper riêng với bộ quy tắc rõ ràng, thay vì thay đổi mapper dùng chung trong lúc chạy.

## 6. Kiểm tra module có thực sự hoạt động

Đừng chỉ kiểm tra dependency đã tải thành công. Hãy kiểm tra hành vi serialize và deserialize của kiểu dữ liệu mà module được thêm vào.

Ví dụ test JavaTimeModule:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

class JacksonModuleTest {

    @Test
    void shouldSerializeAndDeserializeLocalDate() throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .build();

        LocalDate original = LocalDate.of(2026, 11, 12);

        String json = mapper.writeValueAsString(original);
        LocalDate restored = mapper.readValue(json, LocalDate.class);

        assertEquals(original, restored);
    }
}
~~~

Với API thực tế, nên test DTO thay vì chỉ test một scalar. Ví dụ test request chứa LocalDate, Instant và Optional để xác nhận toàn bộ hợp đồng hoạt động như mong muốn.

Nên có các trường hợp:

- Giá trị hợp lệ và giá trị biên.
- Field bị thiếu, field null và Optional.empty().
- Ngày giờ có timezone hoặc offset khác nhau.
- JSON cũ cần tiếp tục đọc được sau khi nâng phiên bản.
- Field không biết trước nếu hợp đồng cho phép mở rộng.
- Payload sai kiểu hoặc sai định dạng phải được xử lý rõ ràng.

Đối với module dataformat, test cả round-trip và các đặc điểm riêng của định dạng. XML cần kiểm tra namespace/attribute nếu hợp đồng sử dụng chúng; CSV cần kiểm tra dấu nháy, delimiter và newline; YAML cần kiểm tra kiểu dữ liệu và cấu trúc lồng nhau.

## 7. Chẩn đoán lỗi dependency và registration

### 7.1. Lỗi Java 8 date/time type not supported

Thông báo thường gặp là Jackson không tìm được serializer/deserializer cho kiểu như LocalDate hoặc Instant.

Nguyên nhân thường là:

- Chưa thêm jackson-datatype-jsr310.
- Dependency có nhưng mapper đang dùng không đăng ký JavaTimeModule.
- Ứng dụng tạo ObjectMapper thủ công, bỏ qua cấu hình Spring Boot.
- Có nhiều ObjectMapper khác nhau trong cùng ứng dụng.

Cách xử lý:

1. Kiểm tra dependency tree.
2. Xác định ObjectMapper thực sự được dùng.
3. Đăng ký JavaTimeModule hoặc sửa cấu hình framework.
4. Thêm test cho DTO có kiểu ngày giờ.

### 7.2. NoSuchMethodError hoặc lỗi tương thích class

Những lỗi này thường liên quan đến việc artifact Jackson bị lệch phiên bản hoặc dependency transitively kéo về một phiên bản khác.

Cách xử lý:

- Kiểm tra jackson-core, jackson-annotations, jackson-databind và module đang dùng.
- Dùng BOM hoặc dependency management để đồng bộ.
- Tìm dependency trực tiếp hoặc gián tiếp đang ép phiên bản khác.
- Tránh exclude hoặc override tùy tiện khi chưa hiểu dependency graph.

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Có thể chạy dependencyInsight với artifact khác để tìm module gây xung đột. Trên Windows, dùng gradlew.bat thay cho ./gradlew.

### 7.3. Dependency có nhưng Spring Boot không dùng module

Hãy xác nhận code đang inject ObjectMapper do Spring quản lý hay đang tạo mapper mới bằng new ObjectMapper(). Kiểm tra cấu hình customizer, các bean Module và các cấu hình auto-configuration bị loại trừ.

Một lỗi phổ biến là khai báo module đúng nhưng lại gọi mapper thủ công được tạo ở một lớp tiện ích. Mapper thủ công đó không tự nhận toàn bộ cấu hình của Spring Boot.

### 7.4. Serializer bị ghi đè hoặc kết quả khác mong đợi

Nếu cùng một kiểu dữ liệu có nhiều module đăng ký serializer, thứ tự đăng ký và cách module được cấu hình có thể ảnh hưởng đến kết quả. Hãy kiểm tra:

- Có module nào đăng ký serializer cho cùng kiểu không?
- Có custom serializer hoặc mix-in nào đang can thiệp không?
- Mapper được tạo từ builder nào?
- Auto-discovery có thêm module ngoài dự kiến không?
- Có nhiều ObjectMapper với cấu hình khác nhau không?

Nên giữ một điểm cấu hình trung tâm và viết test thể hiện JSON mong muốn. Đừng sửa lỗi bằng cách thêm module khác một cách thử-và-sai.

## 8. Những nguyên tắc nên giữ trong dự án

1. **Chỉ thêm module có nhu cầu cụ thể.** Kiểu dữ liệu nào cần hỗ trợ thì thêm module tương ứng.
2. **Quản lý phiên bản tập trung.** Dùng Jackson BOM hoặc dependency management của Spring Boot; tránh lệch phiên bản giữa core, databind và module.
3. **Dùng mapper thống nhất.** Các thành phần trong cùng hợp đồng nên dùng cấu hình ObjectMapper nhất quán.
4. **Đăng ký module trước khi sử dụng.** Không thay đổi cấu hình mapper dùng chung sau khi đã đưa vào xử lý đồng thời.
5. **Tách module tùy chỉnh theo trách nhiệm.** Serializer chỉ định nghĩa cách biểu diễn dữ liệu; nghiệp vụ thuộc service/domain.
6. **Không serialize Entity tùy tiện.** Ưu tiên DTO; chỉ dùng Hibernate module khi đã hiểu tác động của proxy và lazy loading.
7. **Kiểm thử hợp đồng.** Test JSON đầu vào/đầu ra trước và sau khi thay đổi module hoặc nâng phiên bản.
8. **Xem dependency graph khi có lỗi.** Lỗi runtime có thể đến từ một dependency bắc cầu chứ không phải dependency trực tiếp vừa khai báo.

## 9. Quy trình thêm một module mới

Giả sử một DTO mới có trường Instant và ứng dụng hiện chưa xử lý được kiểu này. Quy trình nên diễn ra như sau:

~~~text
Phát hiện kiểu dữ liệu cần hỗ trợ
              |
              v
Xác định module tương ứng
              |
              v
Thêm dependency
              |
              v
Kiểm tra BOM / dependency version
              |
              v
Đăng ký vào ObjectMapper đang dùng
              |
              v
Viết test serialize + deserialize
              |
              v
Chạy test tích hợp API
              |
              v
Xác nhận JSON đúng hợp đồng
~~~

Trong ví dụ này, module cần dùng là JavaTimeModule thuộc artifact jackson-datatype-jsr310. Nếu Spring Boot đã quản lý và đăng ký module phù hợp, có thể không cần tự tạo mapper hoặc đăng ký lại. Nếu ứng dụng Java độc lập, cần thêm dependency và đăng ký module tường minh hoặc dùng cơ chế discovery đã được lựa chọn.

Khi nâng phiên bản Jackson, áp dụng quy trình tương tự ở phạm vi toàn bộ dependency graph: xác định phiên bản mục tiêu, kiểm tra BOM và module, chạy test hợp đồng, sau đó mới triển khai. Nâng riêng một artifact trong khi các artifact liên quan vẫn ở phiên bản cũ dễ tạo lỗi khó tìm.

## 10. Kết luận lựa chọn

Một ứng dụng Java không cần cài mọi Jackson module. Bộ module nên phản ánh các kiểu dữ liệu và định dạng mà ứng dụng thực sự trao đổi.

- Dùng JavaTimeModule cho java.time.
- Dùng Jdk8Module cho Optional và các kiểu JDK 8 được hỗ trợ.
- Dùng KotlinModule cho mô hình Kotlin trên JVM.
- Dùng dataformat module khi cần XML, YAML, CSV hoặc định dạng tương ứng.
- Dùng custom module khi kiểu dữ liệu riêng cần một hợp đồng biểu diễn tập trung.
- Dùng BOM hoặc dependency management của Spring Boot để giữ các artifact tương thích.
- Xác nhận mapper đang chạy đã nhận module và kiểm thử JSON thực tế.

Quản lý module đúng giúp Jackson có thể mở rộng theo nhu cầu mà dependency graph vẫn dễ hiểu, ObjectMapper có hành vi nhất quán và hợp đồng dữ liệu không thay đổi ngoài dự kiến.

