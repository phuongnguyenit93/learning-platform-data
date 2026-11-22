# Quản lý tên, phiên bản và thứ tự đăng ký module

Jackson Databind mở rộng `ObjectMapper` thông qua module. Một module có thể đăng ký serializer, deserializer, key serializer, key deserializer, mix-in, abstract type mapping, modifier hoặc các thành phần tích hợp khác. Khi ứng dụng có nhiều module, cách đặt tên, quản lý version và thứ tự đăng ký ảnh hưởng trực tiếp đến cấu hình cuối cùng của mapper.

Module nên được xem là một đơn vị cấu hình có danh tính ổn định. Tên module giúp nhận diện module và hỗ trợ phát hiện đăng ký trùng; version mô tả phiên bản của module; thứ tự đăng ký quyết định cách các extension cùng tham gia vào quá trình serialize/deserialize. Nếu cấu hình không rõ ràng, một module có thể bị bỏ qua do trùng ID, serializer mong muốn không được chọn, hoặc môi trường phát triển và production tạo JSON khác nhau.

## 1. Module trong Jackson dùng để làm gì?

`Module` là điểm mở rộng của Jackson Databind. Thay vì cấu hình từng serializer trực tiếp trên `ObjectMapper`, ứng dụng có thể gom nhiều extension thành một module rồi đăng ký một lần.

Ví dụ module có thể cung cấp:

- Serializer cho kiểu nghiệp vụ như `Money`, `PhoneNumber` hoặc `UserId`.
- Deserializer cho kiểu dữ liệu tùy chỉnh.
- Key serializer/deserializer cho khóa `Map` không phải `String`.
- Abstract type mapping, ví dụ ánh xạ interface sang implementation mặc định.
- `BeanSerializerModifier` hoặc `BeanDeserializerModifier` để tùy chỉnh quá trình tạo serializer/deserializer cho bean.
- Annotation introspector hoặc các extension khác được hỗ trợ qua `SetupContext`.

Một số module phổ biến trong hệ sinh thái Jackson:

| Module | Mục đích thường gặp |
|---|---|
| `jackson-datatype-jsr310` | Hỗ trợ các kiểu `java.time` như `Instant`, `LocalDate`, `OffsetDateTime` |
| `jackson-datatype-jdk8` | Hỗ trợ một số kiểu JDK 8 như `Optional` |
| `jackson-module-parameter-names` | Đọc tên tham số constructor trong các trường hợp phù hợp |
| `jackson-module-kotlin` | Hỗ trợ Kotlin data class, constructor và nullability |
| Hibernate datatype module | Xử lý một số proxy và persistent collection của Hibernate |
| `SimpleModule` do ứng dụng tạo | Đăng ký serializer/deserializer và extension nghiệp vụ |

Module không phải là một `ObjectMapper` riêng. Nhiều module có thể được đăng ký vào cùng mapper để kết hợp các khả năng. Vì vậy, cần kiểm soát module nào được nạp, version nào được dùng và module nào có quyền cung cấp extension khi xảy ra xung đột.

## 2. Module có tên và version

API cơ sở của Jackson `Module` cung cấp thông tin nhận diện như:

- `getModuleName()`: tên module.
- `version()`: thông tin version dưới dạng `com.fasterxml.jackson.core.Version`.
- `getTypeId()`: ID được dùng để nhận diện module khi kiểm tra đăng ký trùng; mặc định thường dựa trên module name, nhưng implementation có thể tùy chỉnh.
- `setupModule(SetupContext)`: nơi module đăng ký các extension với mapper.

Tên module và version có vai trò khác nhau:

- **Tên/ID** nhận diện một loại module trong quá trình đăng ký.
- **Version** mô tả phiên bản phát hành của module.
- **Version dependency** do Maven/Gradle quản lý xác định artifact nào thực sự được đưa vào classpath.

Thông tin version trong module không thay thế version của dependency và không tự bảo đảm binary compatibility. Một module có thể báo version `1.2.0`, nhưng nếu artifact Jackson Databind trên classpath không tương thích với module đó thì ứng dụng vẫn có thể gặp lỗi linkage hoặc runtime.

## 3. Đặt tên cho SimpleModule

Với extension đơn giản, `SimpleModule` thường là cách dễ nhất để đăng ký serializer/deserializer:

```java
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule moneyModule = new SimpleModule("money-module");
moneyModule.addSerializer(Money.class, new MoneySerializer());
moneyModule.addDeserializer(Money.class, new MoneyDeserializer());
```

Nên đặt tên tường minh và ổn định thay vì để module không có tên. Tên như `money-module`, `legacy-date-module` hoặc `partner-api-module` giúp người đọc hiểu mục đích và hỗ trợ phát hiện việc đăng ký cùng module nhiều lần.

Nếu cần cung cấp version metadata cho module:

```java
import com.fasterxml.jackson.core.Version;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule moneyModule = new SimpleModule(
        "money-module",
        Version.unknownVersion()
);
```

`Version.unknownVersion()` phù hợp khi module chỉ là cấu hình nội bộ của ứng dụng và không có version metadata độc lập. Với thư viện/module được phát hành riêng, nên cung cấp version thực tế tương ứng với artifact.

Ví dụ dùng `VersionUtil` để tạo metadata:

```java
import com.fasterxml.jackson.core.Version;
import com.fasterxml.jackson.core.util.VersionUtil;

Version moduleVersion = VersionUtil.parseVersion(
        "1.4.0",
        "com.example",
        "money-module"
);

SimpleModule moneyModule = new SimpleModule("money-module", moduleVersion);
```

Không dùng version metadata để biểu diễn version của Jackson Databind nếu đó không phải version của module. Version của module nghiệp vụ và version của Jackson là hai thông tin riêng.

## 4. Tạo module riêng khi cần cấu hình nâng cao

Nếu chỉ đăng ký serializer/deserializer, `SimpleModule` là đủ. Khi cần nhiều logic trong `setupModule`, có thể tạo class kế thừa `SimpleModule` hoặc `Module`.

Ví dụ một module nghiệp vụ:

```java
public final class MoneyModule extends SimpleModule {
    public MoneyModule() {
        super("money-module");

        addSerializer(Money.class, new MoneySerializer());
        addDeserializer(Money.class, new MoneyDeserializer());
        addKeySerializer(CurrencyCode.class, new CurrencyCodeKeySerializer());
        addKeyDeserializer(CurrencyCode.class, new CurrencyCodeKeyDeserializer());
    }
}
```

Sau đó mapper chỉ cần:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new MoneyModule())
        .build();
```

Đóng gói extension liên quan trong một module giúp ứng dụng có một điểm cấu hình rõ ràng. Khi nâng cấp hoặc thay đổi quy tắc serialize, có thể kiểm tra module này thay vì tìm nhiều lệnh đăng ký rải rác.

Với module phức tạp, hãy xem xét tách theo trách nhiệm: module ngày giờ, module kiểu tiền, module tích hợp đối tác. Một module quá lớn có thể khiến các ứng dụng chỉ cần một extension nhỏ phải kéo theo nhiều cấu hình không liên quan.

## 5. Quản lý version của Jackson bằng BOM

Jackson Databind, Core, Annotations và các module datatype thường có quan hệ version. Trộn các artifact ở những dòng version không tương thích có thể gây lỗi compile, `NoSuchMethodError`, `NoClassDefFoundError` hoặc hành vi khác nhau giữa môi trường.

Với Maven, có thể dùng Jackson BOM để quản lý version đồng bộ:

```xml
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
</dependencies>
```

Với Gradle:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:$jacksonVersion"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

Để BOM quản lý version giúp các artifact Jackson được chọn từ cùng một release line. Nếu framework như Spring Boot đã quản lý Jackson thông qua dependency management riêng, hãy tuân theo BOM/version set của framework hoặc override có chủ đích; tránh thêm một BOM khác mà không kiểm tra toàn bộ dependency graph.

### 5.1. Không trộn module theo cảm tính

Một lỗi thường gặp là Databind ở version mới nhưng JavaTimeModule hoặc Hibernate module lại ở version cũ. Việc compile thành công không bảo đảm mọi API runtime tương thích.

Hãy kiểm tra dependency tree:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Hoặc xem vì sao một version cụ thể được chọn:

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Khi nâng cấp Jackson, cần kiểm tra cả module do ứng dụng trực tiếp khai báo và module được framework hoặc thư viện khác kéo vào transitive dependency.

## 6. Version của module nghiệp vụ cần theo dõi thế nào?

Nếu ứng dụng phát hành một module dùng chung cho nhiều service, version của module nên phản ánh thay đổi contract và khả năng tương thích.

Ví dụ:

| Thay đổi module | Cách nghĩ về version |
|---|---|
| Thêm serializer cho một kiểu mới, không đổi hành vi cũ | Có thể là thay đổi tương thích/additive |
| Sửa format output của một kiểu đã được consumer dùng | Có thể là breaking change |
| Đổi type ID, tên field hoặc định dạng ngày giờ | Thường là thay đổi contract cần migration |
| Bỏ một deserializer hoặc format cũ | Có thể phá khả năng đọc dữ liệu đã lưu |
| Nâng Jackson dependency nhưng không đổi contract | Là thay đổi dependency; vẫn cần kiểm tra tương thích runtime |

Không nhất thiết mọi ứng dụng phải tạo version metadata riêng cho từng `SimpleModule`. Nhưng nếu module được phát hành như một thư viện, hãy quản lý artifact version theo chính sách release của tổ chức, công bố Jackson version range tương thích và kiểm thử với các version được hỗ trợ.

## 7. Đăng ký module bằng ObjectMapper

Cách trực tiếp nhất là đăng ký từng module một cách tường minh:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.registerModule(new Jdk8Module());
mapper.registerModule(new MoneyModule());
```

Hoặc dùng builder:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .addModule(new Jdk8Module())
        .addModule(new MoneyModule())
        .build();
```

Builder giúp gom module và feature vào một giai đoạn cấu hình trước khi mapper được sử dụng. Cách này làm cấu hình dễ đọc, dễ kiểm thử và giảm nguy cơ một nơi khác đăng ký thêm module sau khi ứng dụng đã bắt đầu xử lý request.

Nếu mapper được tạo trong Spring, hãy đăng ký module tại một cấu hình tập trung hoặc dùng cơ chế auto-configuration mà framework cung cấp. Tránh tạo nhiều mapper độc lập với module khác nhau cho cùng một loại API nếu không có mục đích rõ ràng.

## 8. Thứ tự đăng ký module có thể ảnh hưởng kết quả

Module có thể đăng ký extension cùng loại, ví dụ hai module đều cung cấp serializer cho `Money`. Khi đó, thứ tự đăng ký có thể ảnh hưởng extension nào được chọn.

Ví dụ hai module:

```java
SimpleModule compactMoneyModule = new SimpleModule("compact-money-module");
compactMoneyModule.addSerializer(Money.class, new CompactMoneySerializer());

SimpleModule verboseMoneyModule = new SimpleModule("verbose-money-module");
verboseMoneyModule.addSerializer(Money.class, new VerboseMoneySerializer());
```

Cấu hình mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(compactMoneyModule)
        .addModule(verboseMoneyModule)
        .build();
```

Hai serializer cùng nhắm tới `Money`. Kết quả phụ thuộc cơ chế lookup và extension point mà module sử dụng; không nên suy ra một quy tắc “module cuối luôn thắng” cho mọi loại extension. Serializer provider, deserializer provider, modifier, mix-in và annotation có thể có quy tắc ưu tiên khác nhau.

Khi hai module xung đột, hãy làm rõ:

1. Module nào thực sự cần chịu trách nhiệm cho kiểu/property đó?
2. Có thể hợp nhất logic vào một serializer/module duy nhất không?
3. Có annotation hoặc mix-in đang cung cấp serializer riêng không?
4. Extension đang được thêm qua `SimpleModule`, modifier hay cơ chế khác?
5. Output thực tế khi đăng ký theo thứ tự dự kiến là gì?

Nếu thứ tự có ảnh hưởng, hãy ghi thứ tự đăng ký trong cấu hình trung tâm và thêm test xác nhận JSON output. Không dựa vào thứ tự tình cờ từ classpath hoặc ServiceLoader.

## 9. Tránh xung đột serializer và deserializer

Ví dụ hai module cùng đăng ký serializer cho một class:

```java
SimpleModule moduleA = new SimpleModule("module-a");
moduleA.addSerializer(Money.class, new MoneySerializerA());

SimpleModule moduleB = new SimpleModule("module-b");
moduleB.addSerializer(Money.class, new MoneySerializerB());
```

Nếu ứng dụng đăng ký cả hai, cần xác định serializer nào là contract cuối cùng. Một test đơn giản nên serialize một `Money` mẫu và kiểm tra shape/type/value mà API mong đợi.

Tương tự với deserializer: hai module có thể đăng ký các cách đọc khác nhau cho cùng kiểu. Điều này đặc biệt nguy hiểm nếu một module chấp nhận format cũ còn module kia áp dụng format mới.

Không nên dùng nhiều module trùng trách nhiệm như một cách tạo fallback ngầm. Nếu cần hỗ trợ version payload cũ, hãy triển khai logic tương thích rõ ràng trong deserializer hoặc chọn reader theo version của contract.

## 10. Module ID và phát hiện đăng ký trùng

Jackson có cơ chế nhận diện module đã đăng ký dựa trên type ID. Với module có ID trùng, `MapperFeature.IGNORE_DUPLICATE_MODULE_REGISTRATIONS` điều khiển việc bỏ qua đăng ký lặp. Khi feature này được bật, module có type ID đã xuất hiện thường không được setup lần thứ hai.

Ví dụ:

```java
SimpleModule first = new SimpleModule("money-module");
first.addSerializer(Money.class, new MoneySerializer());

SimpleModule second = new SimpleModule("money-module");
second.addSerializer(Money.class, new AlternativeMoneySerializer());

ObjectMapper mapper = JsonMapper.builder()
        .addModule(first)
        .addModule(second)
        .build();
```

Hai module có cùng tên/ID. Với duplicate registration detection được bật, lần đăng ký thứ hai có thể bị bỏ qua. Vì vậy, không tạo nhiều module khác cấu hình nhưng dùng chung tên rồi kỳ vọng module sau ghi đè module trước.

Tên module phải phản ánh danh tính của module, không phải một chuỗi tùy ý được lặp lại. Nếu hai module độc lập, đặt ID khác nhau. Nếu chúng là hai version của cùng một module, hãy chọn một version tương thích duy nhất cho mapper thay vì đăng ký đồng thời cả hai.

Không nên tắt `IGNORE_DUPLICATE_MODULE_REGISTRATIONS` chỉ để ép đăng ký lặp nếu chưa hiểu side effect. Việc setup cùng module nhiều lần có thể đăng ký extension lặp, tạo thứ tự lookup khó đoán hoặc gây khác biệt giữa các lần khởi tạo mapper.

### 10.1. Module không có ID rõ ràng

Nếu module không cung cấp tên/type ID, cơ chế nhận diện trùng có thể không hoạt động như mong muốn. Với module tự viết hoặc `SimpleModule`, hãy đặt tên tường minh. Nếu cần hành vi ID đặc biệt, xem xét override `getTypeId()` theo API của version Jackson đang dùng.

### 10.2. Tên module không phải version

Không đổi tên module theo từng patch version chỉ để tránh duplicate detection. Module ID nhận diện module; version metadata mô tả phiên bản. Nếu cùng module được đăng ký hai lần từ hai dependency version khác nhau, đó là vấn đề dependency/classpath cần giải quyết, không phải vấn đề cần che bằng hai tên khác nhau.

## 11. Tự động phát hiện module bằng ServiceLoader

Jackson hỗ trợ tìm module được công bố qua Java `ServiceLoader`. Có thể dùng:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.findAndRegisterModules();
```

Hoặc tìm danh sách module rồi đăng ký:

```java
List<Module> modules = ObjectMapper.findModules();

ObjectMapper mapper = new ObjectMapper();
mapper.registerModules(modules);
```

Cách này tiện khi classpath có các module đã khai báo service provider metadata. Tuy nhiên:

- Không phải module nào cũng tự động được phát hiện trong mọi cách đóng gói.
- Module tự viết phải khai báo provider đúng cách nếu muốn được `ServiceLoader` tìm thấy.
- Kết quả phụ thuộc classpath/module path và môi trường đóng gói.
- Thứ tự module tìm thấy qua discovery không nên được xem là một contract ổn định.
- Nếu nhiều module xung đột extension, discovery có thể khiến kết quả khác nhau giữa môi trường.

Với ứng dụng cần cấu hình xác định, đăng ký module tường minh theo thứ tự trong một nơi duy nhất thường dễ kiểm soát hơn. Dùng discovery khi hệ thống plugin thực sự cần khả năng tự phát hiện và đã có quy tắc kiểm soát thứ tự/ID.

## 12. Đăng ký module trong Spring hoặc framework

Trong ứng dụng Spring Boot, Jackson thường được framework cấu hình và cung cấp `ObjectMapper` dùng chung. Tạo một mapper mới bằng `new ObjectMapper()` trong service có thể làm mất các module hoặc customizer mà framework đã đăng ký.

Một cách phổ biến là cung cấp `Module` bean:

```java
@Configuration
public class JacksonConfiguration {
    @Bean
    public Module moneyModule() {
        SimpleModule module = new SimpleModule("money-module");
        module.addSerializer(Money.class, new MoneySerializer());
        module.addDeserializer(Money.class, new MoneyDeserializer());
        return module;
    }
}
```

Spring Boot có thể tự phát hiện các bean `Module` và đăng ký chúng với mapper được auto-configure theo phiên bản/framework configuration. Hãy kiểm tra cơ chế của Spring Boot đang dùng và tránh đồng thời đăng ký cùng module ở nhiều nơi.

Nếu ứng dụng cần kiểm soát thứ tự tuyệt đối, hãy dùng cơ chế customizer/builder được framework hỗ trợ và kiểm tra mapper cuối cùng bằng integration test. Không giả định thứ tự bean creation hoặc thứ tự scan package sẽ tạo thứ tự serializer mong muốn.

## 13. Mix-in và module: hai cơ chế khác nhau nhưng có thể phối hợp

Module có thể đăng ký mix-in hoặc annotation introspector; bản thân mix-in là cách bổ sung annotation cho class mà ứng dụng không sở hữu source code.

Ví dụ:

```java
abstract class ExternalUserMixIn {
    @JsonProperty("user_name")
    abstract String getName();
}

ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalUser.class, ExternalUserMixIn.class);
```

Mix-in thay đổi metadata mà Jackson nhìn thấy cho một kiểu. Module có thể đóng gói thao tác này cùng serializer/deserializer khác. Nếu nhiều nơi cùng gắn mix-in cho một target class, cấu hình sau có thể thay thế mix-in trước theo API mapper; vì vậy cũng cần quản lý tập trung.

Annotation trên class/property, mix-in và serializer đăng ký trong module có thể cùng tham gia lựa chọn cách serialize. Không nên suy ra chỉ từ thứ tự module rằng custom serializer chắc chắn thắng annotation hoặc ngược lại trong mọi trường hợp. Hãy kiểm tra extension point cụ thể và output thực tế.

## 14. Thứ tự module và serializer modifier

`BeanSerializerModifier` và `BeanDeserializerModifier` can thiệp vào quá trình Jackson xây dựng serializer/deserializer cho bean. Nhiều module có thể đăng ký modifier cùng loại.

Ví dụ một modifier có thể thay đổi danh sách property trước khi bean serializer được tạo. Nếu một module đổi tên hoặc loại property và module khác tiếp tục sửa danh sách đó, kết quả phụ thuộc chuỗi modifier được áp dụng.

Vì vậy, khi dùng modifier:

- Giữ mỗi modifier tập trung vào một trách nhiệm.
- Không giả định thứ tự áp dụng nếu API/version không cam kết điều đó.
- Tránh hai modifier cùng sửa một property theo các hướng mâu thuẫn.
- Viết test tích hợp với toàn bộ module thực tế.
- Nếu thứ tự là bắt buộc, tổ chức logic trong một modifier hoặc một module tổng hợp có thứ tự rõ.

## 15. Không đăng ký module sau khi mapper đã bắt đầu được dùng

`ObjectMapper` được thiết kế để dùng chung và thread-safe khi cấu hình hoàn tất trước khi thực hiện read/write. Mapper có cache serializer/deserializer. Việc thay đổi module hoặc feature sau khi ứng dụng đã bắt đầu serialize có thể khiến hành vi khó dự đoán hoặc không áp dụng đồng nhất cho mọi kiểu đã được cache.

Nên khởi tạo mapper theo một giai đoạn:

```text
Tạo JsonFactory / JsonMapper builder
             |
             v
Đăng ký module theo thứ tự xác định
             |
             v
Cấu hình feature, mix-in và subtype
             |
             v
Build ObjectMapper
             |
             v
Publish mapper cho ứng dụng dùng
             |
             v
Read/write trong suốt vòng đời ứng dụng
```

Không đăng ký module mới trong từng request hoặc sau khi mapper đã xử lý dữ liệu. Nếu cần cách serialize khác nhau cho một lần gọi, tạo `ObjectWriter` hoặc `ObjectReader` với cấu hình riêng thay vì thay đổi mapper dùng chung.

## 16. Dùng ObjectReader và ObjectWriter cho cấu hình theo use case

`ObjectReader` và `ObjectWriter` là các đối tượng cấu hình bất biến, thích hợp cho các biến thể đọc/ghi từ một mapper đã cấu hình.

Ví dụ:

```java
ObjectWriter compactWriter = mapper.writer();
ObjectWriter prettyWriter = mapper.writerWithDefaultPrettyPrinter();

String compactJson = compactWriter.writeValueAsString(value);
String prettyJson = prettyWriter.writeValueAsString(value);
```

Hoặc cấu hình kiểu root:

```java
ObjectWriter paymentWriter = mapper.writerFor(Payment.class);
ObjectReader paymentReader = mapper.readerFor(Payment.class);
```

Các reader/writer này không phải cách đăng ký module mới cho một request. Chúng tái sử dụng cấu hình module của mapper và thêm cấu hình đọc/ghi theo use case. Nếu cần một bộ serializer module hoàn toàn khác, tạo mapper riêng trong giai đoạn khởi tạo và quản lý vòng đời riêng.

## 17. Kiểm tra module nào đã được đăng ký

Khi debug cấu hình, có thể xem module names mà mapper ghi nhận:

```java
Set<Object> moduleIds = mapper.getRegisteredModuleIds();
moduleIds.forEach(System.out::println);
```

API và kiểu trả về phụ thuộc version Jackson, nhưng ở các version hỗ trợ `getRegisteredModuleIds()`, đây là cách hữu ích để xác nhận module có ID đã được ghi nhận. Nó không chứng minh serializer cụ thể của module chắc chắn được chọn cho một property.

Để xác nhận serializer thực sự hoạt động, hãy serialize một object mẫu và kiểm tra output:

```java
String json = mapper.writeValueAsString(
        new Money("USD", new BigDecimal("12.50"))
);

JsonNode tree = mapper.readTree(json);
assertTrue(tree.isObject());
assertEquals("USD", tree.get("currency").asText());
assertTrue(tree.get("amount").isNumber());
```

Nếu output không đúng shape, kiểm tra module registration, module ID trùng, annotation, mix-in, serializer lookup và mapper thực tế đang được inject vào component.

## 18. Ví dụ cấu hình tập trung và xác định

Một factory có thể gom module theo thứ tự được ứng dụng lựa chọn:

```java
public final class ApplicationJsonMapper {
    private ApplicationJsonMapper() {
    }

    public static ObjectMapper create() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .addModule(new Jdk8Module())
                .addModule(new MoneyModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .disable(DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE)
                .build();
    }
}
```

Ứng dụng dùng một factory này trong cấu hình dependency injection. Không nên gọi `ApplicationJsonMapper.create()` liên tục trong controller/service vì mỗi lần sẽ tạo mapper và cache mới, đồng thời có thể tạo cấu hình không nhất quán.

Nếu thứ tự module quan trọng do hai module có extension trùng nhau, hãy comment lý do tại nơi đăng ký và test output cho kiểu bị ảnh hưởng. Tốt hơn nữa, loại bỏ xung đột bằng cách chỉ đăng ký một module chịu trách nhiệm cho kiểu đó.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Module không có tác dụng | Chưa đăng ký hoặc mapper đang dùng không phải mapper đã cấu hình | Kiểm tra bean/factory và output thực tế |
| Module thứ hai không được setup | Trùng module type ID và duplicate detection đang bật | Dùng một module duy nhất cho ID đó; đặt tên đúng |
| Serializer không được chọn | Extension khác, annotation hoặc mix-in tác động | Kiểm tra cấu hình cuối cùng và viết test cho property |
| Hành vi khác giữa local và production | Discovery/classpath hoặc thứ tự module khác nhau | Đăng ký tường minh và kiểm tra dependency tree |
| `NoSuchMethodError` hoặc lỗi linkage | Jackson artifacts/module không tương thích | Dùng BOM và kiểm tra runtime dependency graph |
| Mapper thay đổi hành vi sau khi chạy | Đăng ký module hoặc đổi feature quá muộn | Cấu hình trước khi publish mapper |
| Spring dùng mapper khác dự kiến | Tạo `new ObjectMapper()` thay vì inject mapper được cấu hình | Dùng bean mapper hoặc factory trung tâm |
| Cùng module bị setup nhiều lần | Đăng ký từ nhiều config path hoặc module không có ID rõ | Tập trung registration, đặt module ID ổn định |
| Discovery tạo thứ tự không xác định | Dựa vào `findAndRegisterModules()` khi có xung đột | Đăng ký module tường minh theo thứ tự |

## 20. Quy trình quản lý module trong ứng dụng

Khi thêm hoặc nâng cấp module, hãy thực hiện theo trình tự:

1. Xác định module cung cấp extension nào và kiểu/property nào bị ảnh hưởng.
2. Chọn tên module ổn định, duy nhất trong phạm vi mapper và cung cấp version metadata phù hợp nếu module được phát hành riêng.
3. Quản lý version của Jackson Core, Databind, Annotations và datatype modules bằng BOM hoặc dependency management của framework.
4. Kiểm tra dependency tree để phát hiện version bị kéo vào từ transitive dependency.
5. Đăng ký module ở một nơi duy nhất, trước lần read/write đầu tiên.
6. Nếu nhiều module có extension trùng nhau, giải quyết xung đột hoặc ghi rõ thứ tự và kiểm thử kết quả.
7. Không phụ thuộc thứ tự ServiceLoader nếu kết quả serialize cần xác định.
8. Kiểm tra module ID đã đăng ký nếu API version hỗ trợ.
9. Test output thực tế của serializer/deserializer quan trọng, không chỉ test rằng module có mặt.
10. Chạy integration test trên runtime classpath giống môi trường triển khai.

## 21. Ghi nhớ

Module gom serializer, deserializer và các extension Jackson thành một đơn vị cấu hình. Tên module/type ID giúp nhận diện và phát hiện đăng ký trùng; version metadata mô tả module release nhưng không thay thế dependency version. Hãy đặt tên ổn định, dùng version metadata đúng ý nghĩa và quản lý các artifact Jackson bằng BOM hoặc dependency management thống nhất.

Thứ tự đăng ký có thể ảnh hưởng kết quả khi các module cùng cung cấp extension, nhưng quy tắc ưu tiên phụ thuộc extension point cụ thể; không áp dụng máy móc câu “module cuối luôn thắng”. Đăng ký tường minh trong một giai đoạn cấu hình, tránh module ID trùng, không thay đổi mapper sau khi đã sử dụng và kiểm tra JSON thực tế bằng test. `findAndRegisterModules()` tiện cho ServiceLoader nhưng thứ tự discovery không nên là nền tảng cho cấu hình có xung đột cần tính xác định.
