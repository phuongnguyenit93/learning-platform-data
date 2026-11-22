# Phân biệt đăng ký tường minh và tự phát hiện module

## 1. Module trong Jackson dùng để làm gì?

Jackson Databind có thể ánh xạ nhiều kiểu Java phổ biến mà không cần cấu hình thêm. Tuy nhiên, một số kiểu dữ liệu hoặc quy tắc ánh xạ cần phần mở rộng riêng. **Module** là cơ chế để bổ sung serializer, deserializer, type resolver, mix-in hoặc các thành phần cấu hình khác vào ObjectMapper.

Một số module thường gặp:

| Module | Mục đích |
|---|---|
| jackson-datatype-jsr310 | Hỗ trợ các kiểu ngày giờ trong java.time, như Instant, LocalDate, LocalDateTime |
| jackson-datatype-jdk8 | Hỗ trợ các kiểu JDK 8 như Optional |
| jackson-module-parameter-names | Hỗ trợ lấy tên tham số constructor từ metadata biên dịch |
| jackson-module-kotlin | Hỗ trợ các tính năng Kotlin như constructor, nullability và data class |
| Module tùy chỉnh | Đăng ký serializer/deserializer và quy tắc riêng của ứng dụng |

Có hai cách chính để đưa module vào mapper:

1. **Đăng ký tường minh:** ứng dụng tạo module rồi gọi registerModule(...), registerModules(...) hoặc thêm module qua builder.
2. **Tự phát hiện:** ứng dụng gọi findAndRegisterModules(). Jackson dùng Java ServiceLoader để tìm các module đã khai báo theo cơ chế Service Provider Interface (SPI) trên classpath hoặc module path.

Hai cách đều có thể tạo ra mapper hỗ trợ cùng một kiểu dữ liệu, nhưng khác nhau về tính minh bạch, khả năng kiểm soát và yêu cầu đóng gói.

## 2. Đăng ký tường minh bằng registerModule

Cách trực tiếp nhất là tạo ObjectMapper, sau đó đăng ký từng module cần dùng:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
~~~

Sau khi đăng ký, mapper có thể dùng serializer/deserializer của module để xử lý các kiểu java.time.

Có thể đăng ký nhiều module:

~~~java
ObjectMapper mapper = new ObjectMapper();

mapper.registerModule(new JavaTimeModule());
mapper.registerModule(new Jdk8Module());
mapper.registerModule(new ParameterNamesModule());
~~~

Các lớp module phải có dependency tương ứng trên classpath. Đoạn mã trên chỉ minh họa các module được chọn; ứng dụng không cần thêm cả ba nếu không dùng những kiểu dữ liệu đó.

Đăng ký tường minh giúp người đọc mã nguồn biết mapper được cấu hình với những phần mở rộng nào. Nó cũng giúp kiểm soát chính xác module nào được dùng trong từng ứng dụng hoặc từng ranh giới dữ liệu.

## 3. Đăng ký nhiều module bằng registerModules hoặc builder

Nếu đã có danh sách module, có thể đăng ký theo một lời gọi:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModules(
        new JavaTimeModule(),
        new Jdk8Module()
);
~~~

Với JsonMapper, có thể cấu hình ngay trong builder:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .addModule(new Jdk8Module())
        .build();
~~~

Builder hữu ích khi muốn hoàn tất cấu hình trước khi mapper được sử dụng. Một ObjectMapper nên được cấu hình xong rồi mới chia sẻ cho nhiều thread; không nên thay đổi cấu hình trong lúc các request đang serialize hoặc deserialize.

Có thể dùng JsonMapper.builder() để đồng thời thiết lập feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();
~~~

Ở đây, module cung cấp hỗ trợ kiểu thời gian; các feature điều khiển hành vi serialize và deserialize. Đăng ký module không tự quyết định toàn bộ chính sách ngày giờ hoặc validation của ứng dụng.

## 4. Tự phát hiện bằng findAndRegisterModules

Jackson có phương thức tiện ích:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();
~~~

Phương thức này tìm các implementation của com.fasterxml.jackson.databind.Module được khai báo qua Java ServiceLoader rồi đăng ký chúng vào mapper.

Có thể hình dung quy trình:

~~~text
ObjectMapper.findAndRegisterModules()
                 |
                 v
       ServiceLoader.load(Module)
                 |
                 v
    Tìm provider được khai báo trong SPI
                 |
                 v
       Tạo các module tìm được
                 |
                 v
       Đăng ký module vào mapper
~~~

Tự phát hiện không có nghĩa Jackson quét mọi JAR rồi đoán module nào cần dùng. Module phải được công bố đúng theo cơ chế ServiceLoader và phải nằm trong phạm vi classloader/module layer có thể nhìn thấy.

Nếu một thư viện chỉ cung cấp lớp SomeModule nhưng không khai báo provider SPI, findAndRegisterModules() không tự biết lớp đó để tạo và đăng ký. Trong trường hợp này, ứng dụng cần đăng ký tường minh hoặc bổ sung metadata SPI phù hợp nếu đó là thư viện do ứng dụng quản lý.

## 5. Java ServiceLoader và file META-INF/services

Trên classpath, Java ServiceLoader thường tìm provider thông qua file trong thư mục:

~~~text
META-INF/services/
~~~

Với Jackson Module, tên file service là:

~~~text
META-INF/services/com.fasterxml.jackson.databind.Module
~~~

Nội dung file liệt kê tên đầy đủ của từng lớp module provider, mỗi provider trên một dòng:

~~~text
com.example.jackson.AuditModule
com.example.jackson.LegacyFormatModule
~~~

Các lớp được liệt kê phải đáp ứng quy tắc khởi tạo provider của ServiceLoader, thường là lớp public có constructor không tham số trong cách khai báo provider bằng tên lớp.

Ví dụ module tùy chỉnh:

~~~java
package com.example.jackson;

import com.fasterxml.jackson.databind.module.SimpleModule;

public class AuditModule extends SimpleModule {
    public AuditModule() {
        super("audit-module");
        addSerializer(
                AuditEvent.class,
                new AuditEventSerializer()
        );
    }
}
~~~

Khi JAR chứa AuditModule được đóng gói cùng file service nói trên, ứng dụng có thể tìm thấy module bằng findAndRegisterModules() mà không cần viết trực tiếp new AuditModule() trong cấu hình mapper.

Nếu provider nằm trong một module Java Platform Module System (JPMS), module có thể công bố service bằng chỉ thị provides trong module-info.java, ví dụ:

~~~java
provides com.fasterxml.jackson.databind.Module
        with com.example.jackson.AuditModule;
~~~

ServiceLoader vẫn phải nhìn thấy module provider trong module layer đang dùng. Chỉ viết provides trong source nhưng đóng gói hoặc chạy sai module path thì discovery vẫn có thể thất bại.

## 6. Viết module tùy chỉnh để đăng ký serializer

SimpleModule là lớp tiện lợi khi module chủ yếu cần thêm serializer/deserializer cho một số kiểu cụ thể.

Serializer ví dụ:

~~~java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import java.io.IOException;

public class AuditEventSerializer extends JsonSerializer<AuditEvent> {
    @Override
    public void serialize(
            AuditEvent value,
            JsonGenerator generator,
            SerializerProvider provider
    ) throws IOException {
        generator.writeStartObject();
        generator.writeStringField("eventId", value.getId());
        generator.writeStringField("action", value.getAction());
        generator.writeEndObject();
    }
}
~~~

Module đăng ký serializer:

~~~java
public class AuditModule extends SimpleModule {
    public AuditModule() {
        super("audit-module");
        addSerializer(
                AuditEvent.class,
                new AuditEventSerializer()
        );
    }
}
~~~

Đăng ký tường minh:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new AuditModule());
~~~

Hoặc đăng ký tự động nếu JAR của module có SPI metadata:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();
~~~

Hai mapper có thể dùng cùng AuditEventSerializer. Điểm khác biệt nằm ở cách ứng dụng tìm và tạo AuditModule, không nằm ở cách serializer ghi JSON.

Nếu module cần tùy biến nhiều hơn, có thể kế thừa Module và cài đặt setupModule(...). SimpleModule phù hợp với các đăng ký serializer/deserializer phổ biến; module phức tạp có thể dùng SetupContext để tích hợp các thành phần khác của Jackson.

## 7. So sánh hai cách đăng ký

| Tiêu chí | Đăng ký tường minh | Tự phát hiện |
|---|---|---|
| Cách gọi | registerModule, registerModules, builder addModule | findAndRegisterModules |
| Nguồn module | Mã cấu hình ứng dụng tạo/chọn module | ServiceLoader và SPI metadata |
| Khả năng nhìn thấy trong code | Cao; danh sách module hiện ngay trong cấu hình | Thấp hơn; phải kiểm tra dependency và service metadata |
| Kiểm soát tập module | Chính xác, dễ giới hạn | Phụ thuộc các provider nhìn thấy trong runtime |
| Thứ tự | Ứng dụng chủ động sắp xếp lời gọi | Phụ thuộc quá trình discovery và thứ tự provider |
| Đóng gói | Không cần service descriptor cho module được tạo trực tiếp | Cần khai báo provider đúng |
| Phù hợp | Ứng dụng cần cấu hình ổn định, rõ ràng | Ứng dụng/plugin muốn tự tìm các module được cài đặt |

Không có một cách luôn đúng cho mọi hệ thống. Nếu mapper là một phần quan trọng của hợp đồng API, đăng ký tường minh thường giúp cấu hình dễ đọc và dễ tái lập. Nếu ứng dụng được thiết kế như một nền tảng plugin, discovery có thể giảm việc phải sửa mã cấu hình mỗi khi thêm provider.

## 8. Thứ tự đăng ký và xung đột module

Module có thể đăng ký serializer, deserializer, modifier hoặc cấu hình có ảnh hưởng đến cùng một kiểu Java. Nếu hai module cùng tùy biến một kiểu, thứ tự đăng ký có thể ảnh hưởng đến thành phần được sử dụng.

Với đăng ký tường minh, thứ tự thể hiện trực tiếp:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new BaseFormatModule());
mapper.registerModule(new ApplicationOverrideModule());
~~~

Nếu ApplicationOverrideModule được thiết kế để thay thế một serializer đã đăng ký trước đó, hãy xác nhận hành vi precedence của loại extension đang dùng và kiểm thử kết quả. Không nên giả định mọi loại module đều có cùng quy tắc ghi đè.

Với tự phát hiện, không nên dựa vào một thứ tự không được tài liệu hóa để giải quyết xung đột. Nếu hai module phải được áp dụng theo thứ tự cụ thể, đăng ký tường minh sẽ dễ kiểm soát hơn.

Jackson có cơ chế nhận diện một số lần đăng ký module trùng dựa trên type id của module và cấu hình MapperFeature.IGNORE_DUPLICATE_MODULE_REGISTRATIONS. Việc một lần đăng ký trùng có bị bỏ qua hay không còn phụ thuộc module có cung cấp type id phù hợp. Vì vậy, không nên gọi registerModule lặp lại với kỳ vọng lần sau chắc chắn thay thế cấu hình lần trước.

Một mapper nên có một cấu hình module rõ ràng. Nếu cần một hành vi khác cho một API hoặc một loại payload, cân nhắc tạo mapper riêng đã cấu hình xong thay vì thay đổi mapper dùng chung sau khi ứng dụng bắt đầu xử lý request.

## 9. Lưu ý riêng với JavaTimeModule

JavaTimeModule là module phổ biến để xử lý các kiểu java.time. Hãy đăng ký tường minh:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule());
~~~

Không nên mặc định rằng findAndRegisterModules() chắc chắn sẽ phát hiện JavaTimeModule. Tài liệu của JavaTimeModule lưu ý module này không hỗ trợ auto-registration theo cách thông thường từ Jackson 2.10 do tồn tại module cũ JSR310Module; explicit registration được khuyến nghị.

Điều này minh họa một nguyên tắc quan trọng: có dependency trên classpath không đồng nghĩa mọi module đều được ServiceLoader tự phát hiện. Hãy kiểm tra tài liệu của module cụ thể và kiểm thử mapper trong môi trường runtime thực tế.

Sau khi đăng ký, các feature như WRITE_DATES_AS_TIMESTAMPS vẫn quyết định dạng đầu ra ngày giờ. Module cung cấp khả năng ánh xạ kiểu; mapper feature và annotation quyết định chính sách cụ thể.

## 10. Căn chỉnh phiên bản module và Jackson Databind

Các module Jackson thường được phát hành theo dòng phiên bản tương ứng với Jackson Core và Databind. Trộn các phiên bản không đồng bộ có thể gây lỗi liên kết binary, NoSuchMethodError, NoClassDefFoundError hoặc hành vi không tương thích.

Với Maven, có thể dùng Jackson BOM để quản lý phiên bản thống nhất:

~~~xml
<properties>
    <jackson.version>2.17.2</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
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
</dependencies>
~~~

Phiên bản trong ví dụ chỉ minh họa cách dùng BOM, không phải khuyến nghị phiên bản mới nhất. Hãy dùng dòng phiên bản đã được dự án chọn và bảo đảm các module Jackson tương thích với nhau.

Trong Gradle, có thể dùng platform BOM:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
~~~

Nếu một framework đã quản lý phiên bản Jackson, hãy theo BOM hoặc dependency management của framework đó. Không thêm một phiên bản module riêng lẻ làm lệch các artifact mà framework đang sử dụng.

## 11. Những nguyên nhân khiến auto-discovery không tìm thấy module

Nếu gọi findAndRegisterModules() nhưng module không hoạt động như mong đợi, kiểm tra lần lượt:

1. **Thiếu dependency:** JAR của module không có trong runtime classpath hoặc module path.
2. **Thiếu SPI descriptor:** module tùy chỉnh không có file META-INF/services/com.fasterxml.jackson.databind.Module.
3. **Sai tên provider:** dòng trong service file không phải tên lớp đầy đủ hoặc lớp không tồn tại.
4. **Không khởi tạo được provider:** provider không đáp ứng quy tắc ServiceLoader hoặc constructor phát sinh lỗi.
5. **Classloader không nhìn thấy provider:** môi trường plugin, application server hoặc container dùng classloader riêng.
6. **Metadata bị mất khi đóng gói:** công cụ shading/uber-JAR ghi đè hoặc không hợp nhất các file service descriptor.
7. **Module không hỗ trợ discovery:** một số module yêu cầu đăng ký tường minh.
8. **Mapper không phải mapper đang được sử dụng:** framework có thể tạo và quản lý một ObjectMapper khác với instance mà ứng dụng vừa cấu hình.

Đặc biệt với shaded JAR, nhiều dependency có thể cùng đóng góp nội dung vào một service file. Cấu hình build cần hợp nhất các service descriptor thay vì chỉ giữ file cuối cùng. Nếu descriptor của một provider bị mất, auto-discovery sẽ không thể tìm thấy provider đó.

## 12. Khi nào nên chọn đăng ký tường minh?

Đăng ký tường minh phù hợp khi:

- API cần cấu hình mapper có thể đọc và tái lập.
- Chỉ một tập module đã được phê duyệt được phép tham gia deserialization.
- Thứ tự áp dụng module có ảnh hưởng đến serializer/deserializer.
- Một module không công bố SPI hoặc yêu cầu cấu hình tham số riêng.
- Ứng dụng cần kiểm soát rõ module nào được bật trong từng môi trường.
- Cần tránh việc một dependency mới vô tình đưa thêm module vào mapper dùng chung.

Ví dụ cấu hình tập trung:

~~~java
public final class JsonConfiguration {
    private JsonConfiguration() {
    }

    public static ObjectMapper createMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .addModule(new Jdk8Module())
                .build();
    }
}
~~~

Danh sách module trở thành một phần rõ ràng của cấu hình ứng dụng. Khi nâng cấp hoặc thêm module, thay đổi được xem xét ngay tại một vị trí.

## 13. Khi nào nên chọn tự phát hiện?

Auto-discovery phù hợp khi ứng dụng được thiết kế để mở rộng bằng plugin hoặc module provider:

- Ứng dụng không biết trước toàn bộ module sẽ được cài đặt khi build.
- Các plugin tự đóng gói module và SPI descriptor của mình.
- Runtime classloader/module layer được quản lý rõ ràng.
- Không có xung đột thứ tự giữa các module được phát hiện.
- Việc thêm một provider mới là một phần được hỗ trợ của kiến trúc.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();
~~~

Nếu hệ thống cần ghi nhận chính xác module nào đã được phát hiện, có thể kiểm tra danh sách provider qua ObjectMapper.findModules() trong một công cụ chẩn đoán. Đây là thao tác discovery; sau đó ứng dụng có thể đăng ký danh sách đã kiểm tra theo cách tường minh nếu cần kiểm soát thứ tự.

Không nên dùng auto-discovery chỉ vì lời gọi ngắn hơn. Cần biết những JAR nào có quyền cung cấp module và những module đó có ảnh hưởng gì đến cách ứng dụng đọc dữ liệu.

## 14. Mix-in có phải là module không?

Mix-in và module liên quan nhưng không phải cùng một khái niệm:

- **Mix-in:** cung cấp annotation từ một lớp khác để Jackson áp dụng lên một kiểu đích mà không phải sửa lớp đích.
- **Module:** một đơn vị cấu hình có thể đăng ký serializer, deserializer, mix-in và các thành phần mở rộng khác vào mapper.

Có thể đăng ký mix-in trực tiếp:

~~~java
mapper.addMixIn(
        ThirdPartyUser.class,
        ThirdPartyUserMixin.class
);
~~~

Lời gọi này là cấu hình tường minh trên mapper. Jackson không tự quét classpath để tìm mọi lớp có tên kết thúc bằng Mixin. Nếu muốn một module cung cấp mix-in, module cần thực hiện đăng ký đó trong quá trình cấu hình module.

Ví dụ mix-in:

~~~java
abstract class ThirdPartyUserMixin {
    @JsonProperty("display_name")
    abstract String getDisplayName();
}
~~~

Sau khi đăng ký, Jackson dùng annotation trên mix-in như metadata bổ sung cho ThirdPartyUser, trong khi mã nguồn của lớp thư viện bên ngoài vẫn giữ nguyên.

## 15. Kiểm thử mapper sau khi đăng ký module

Không nên chỉ kiểm tra rằng lệnh registerModule hoặc findAndRegisterModules chạy không ném lỗi. Hãy kiểm tra hành vi thực tế mà module cung cấp.

Ví dụ kiểm thử Java Time:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.junit.jupiter.api.Assertions.*;

class ModuleRegistrationTest {
    @Test
    void explicitRegistrationSupportsJavaTime() throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();

        LocalDate date = LocalDate.of(2025, 3, 8);
        String json = mapper.writeValueAsString(date);

        LocalDate restored = mapper.readValue(json, LocalDate.class);
        assertEquals(date, restored);
    }
}
~~~

Với module tùy chỉnh, kiểm tra serializer hoặc deserializer đã đăng ký:

~~~java
@Test
void customModuleUsesRegisteredSerializer() throws Exception {
    ObjectMapper mapper = new ObjectMapper()
            .registerModule(new AuditModule());

    String json = mapper.writeValueAsString(
            new AuditEvent("E-1", "created")
    );

    JsonNode tree = mapper.readTree(json);
    assertEquals("E-1", tree.path("eventId").asText());
    assertEquals("created", tree.path("action").asText());
}
~~~

Với auto-discovery, test phải chạy trong đúng artifact/runtime mà ứng dụng triển khai. Nếu test chỉ chạy từ IDE nhưng JAR đóng gói bị mất service descriptor, kết quả ở production có thể khác.

Các trường hợp nên kiểm thử:

| Ca | Điều cần xác nhận |
|---|---|
| Đăng ký tường minh | Module được chọn thực sự thay đổi hành vi mapper |
| Tự phát hiện | ServiceLoader nhìn thấy provider trong runtime |
| Thiếu SPI descriptor | Module không bị giả định là tự động được tìm thấy |
| Hai module cùng tùy biến một kiểu | Kết quả theo thứ tự đăng ký đã thiết kế |
| Nâng cấp phiên bản module | Mapper vẫn serialize/deserialize đúng |
| Mix-in | Annotation trên mix-in được áp dụng cho kiểu đích |
| Framework-managed mapper | Mapper được cấu hình là mapper mà ứng dụng thực sự dùng |

## 16. Các lỗi thường gặp

### Nghĩ rằng thêm dependency là đủ

Dependency chỉ đưa lớp module vào runtime. Auto-discovery còn cần provider metadata; đăng ký tường minh cần lời gọi cấu hình. Một số module cũng yêu cầu đăng ký tường minh theo tài liệu riêng.

### Dùng findAndRegisterModules nhưng không kiểm tra provider

Phương thức này chỉ tìm những module mà ServiceLoader có thể nhìn thấy và đã khai báo. Module không có SPI descriptor sẽ không được tự động thêm vào mapper.

### Đăng ký module sau khi mapper đã được dùng

Nên cấu hình mapper trước khi chia sẻ cho các thread hoặc bắt đầu xử lý request. Thay đổi cấu hình sau khi mapper đã hoạt động có thể làm hành vi giữa các request khó dự đoán.

### Trộn phiên bản Jackson

Module không tương thích với phiên bản Databind/Core có thể gây lỗi runtime. Dùng BOM hoặc dependency management của framework để căn chỉnh phiên bản.

### Giả định mọi module đều có thể tự phát hiện

Kiểm tra tài liệu module. JavaTimeModule là ví dụ cần đăng ký tường minh theo khuyến nghị của module từ Jackson 2.10.

### Cho phép module không cần thiết tham gia mapper

Auto-discovery có thể làm tập module phụ thuộc các dependency runtime. Với dữ liệu không đáng tin cậy, hãy kiểm soát serializer/deserializer và subtype mà mapper được phép sử dụng.

### Nhầm mix-in với service provider

Một lớp mix-in không tự được ServiceLoader tìm thấy chỉ vì nó nằm trên classpath. Nó cần được đăng ký trực tiếp hoặc được một module đăng ký.

## 17. Quy trình lựa chọn và chẩn đoán

Khi cấu hình mapper, có thể đi theo trình tự:

1. Liệt kê các kiểu Java mà ứng dụng cần serialize/deserialize.
2. Xác định module nào cung cấp hỗ trợ cho từng kiểu.
3. Đọc tài liệu của module để biết có hỗ trợ auto-registration hay yêu cầu explicit registration.
4. Nếu cần cấu hình xác định, đăng ký tường minh theo thứ tự đã chọn.
5. Nếu dùng plugin discovery, kiểm tra SPI descriptor hoặc JPMS provides trong artifact runtime.
6. Căn chỉnh phiên bản Jackson bằng BOM hoặc dependency management.
7. Viết test xác nhận hành vi serializer/deserializer, không chỉ xác nhận mapper khởi tạo thành công.
8. Kiểm tra mapper thực tế được framework hoặc ứng dụng sử dụng.

Nếu auto-discovery không tìm thấy module, trước hết xác nhận dependency có mặt ở runtime, sau đó kiểm tra service metadata và classloader. Nếu mapper có module nhưng kết quả không đúng, kiểm tra xung đột serializer/deserializer, thứ tự đăng ký và phiên bản.

## 18. Kết luận

Đăng ký tường minh dùng registerModule, registerModules hoặc builder addModule để ứng dụng chủ động chọn và sắp xếp các phần mở rộng của Jackson. Tự phát hiện dùng findAndRegisterModules() dựa trên Java ServiceLoader, vì vậy module phải công bố provider bằng META-INF/services/com.fasterxml.jackson.databind.Module hoặc JPMS service declaration và phải được classloader nhìn thấy. Đăng ký tường minh phù hợp khi cần cấu hình dễ đọc, thứ tự ổn định và tập module được kiểm soát; auto-discovery phù hợp với kiến trúc plugin có SPI được quản lý. Luôn căn chỉnh phiên bản module với Databind/Core, kiểm tra yêu cầu riêng của từng module như JavaTimeModule, và kiểm thử hành vi thực tế của mapper. Mix-in là metadata bổ sung cho kiểu đích; bản thân một lớp mix-in không tự trở thành module hay tự được phát hiện.
