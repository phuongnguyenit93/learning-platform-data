# Tự cấu hình không được khám phá do thiếu tài nguyên hoặc sai tên lớp đăng ký trong Spring Boot

## 1. Nhận diện đúng loại lỗi

Một thư viện có thể đã chứa class `@AutoConfiguration` và các method `@Bean` hợp lệ nhưng ứng dụng tiêu thụ vẫn không tạo ra bean nào từ thư viện. Một nguyên nhân phổ biến là Spring Boot không tìm thấy class auto-configuration trong danh sách ứng viên.

Trong Spring Boot 3.3, danh sách này được công bố qua resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Resource phải nằm trên runtime classpath và liệt kê đúng tên đầy đủ của class cấu hình. Nếu file bị thiếu, đặt sai thư mục, không được đóng gói vào JAR hoặc class name trong file sai, auto-configuration có thể không được nạp như dự định.

Cần tách ba tình huống:

1. **Không tìm thấy descriptor:** Spring Boot không có danh sách ứng viên từ JAR đó, nên class không được khám phá qua cơ chế auto-configuration.
2. **Descriptor có entry nhưng class name sai hoặc class không có trên classpath:** Boot đã đọc tên ứng viên nhưng không thể nạp class tương ứng; quá trình khởi động có thể thất bại với lỗi import/class loading.
3. **Class đã được khám phá nhưng condition không khớp:** class nằm trong danh sách ứng viên, nhưng annotation như `@ConditionalOnClass`, `@ConditionalOnProperty` hoặc `@ConditionalOnResource` khiến cấu hình không được áp dụng.

Ba tình huống cần cách kiểm tra khác nhau. Không nên sửa condition khi vấn đề thực tế là file imports chưa được đóng gói.

## 2. Cơ chế khám phá auto-configuration trong Spring Boot 3.3

Ứng dụng bật auto-configuration thông qua `@SpringBootApplication` hoặc `@EnableAutoConfiguration`. Annotation này sử dụng cơ chế import candidates của Spring Boot để đọc danh sách class được công bố trên classpath.

Đối với thư viện bên ngoài, Boot tìm file:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

trong các JAR trên classpath. Mỗi dòng trong file là một fully qualified class name (FQCN), ví dụ:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
com.acme.widget.autoconfigure.WidgetWebAutoConfiguration
~~~

Có thể thêm comment bắt đầu bằng `#`:

~~~text
# Core integration
com.acme.widget.autoconfigure.WidgetAutoConfiguration

# Optional web integration
com.acme.widget.autoconfigure.WidgetWebAutoConfiguration
~~~

Boot đọc danh sách ứng viên từ resource, sau đó tiếp tục xử lý exclusion, import filters, ordering và conditions. Việc xuất hiện trong file imports có nghĩa class được công bố như một ứng viên; điều đó chưa bảo đảm tất cả bean bên trong sẽ được tạo.

### Quy trình tổng quát

~~~mermaid
flowchart TD
    A["@SpringBootApplication / @EnableAutoConfiguration"] --> B["Tìm AutoConfiguration.imports trên classpath"]
    B --> C["Đọc từng FQCN"]
    C --> D["Nạp auto-configuration class"]
    D --> E["Áp dụng exclusion và import filters"]
    E --> F["Đánh giá @Conditional"]
    F --> G{"Condition có khớp?"}
    G -->|"Có"| H["Đăng ký configuration và bean definitions"]
    G -->|"Không"| I["Bỏ qua cấu hình theo condition"]
~~~

Tài liệu Spring Boot 3.3 quy định auto-configuration chỉ được nạp bằng cách được liệt kê trong file imports; class không nên là mục tiêu của component scan. Nếu cần nạp cấu hình hỗ trợ, dùng `@Import` tường minh.

## 3. Tạo đúng file AutoConfiguration.imports

Trong module chứa auto-configuration, đặt resource tại đúng đường dẫn:

~~~text
acme-widget-autoconfigure/
└── src/
    └── main/
        ├── java/
        │   └── com/acme/widget/autoconfigure/
        │       └── WidgetAutoConfiguration.java
        └── resources/
            └── META-INF/
                └── spring/
                    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Các điểm phải đúng:

- Tên thư mục là `META-INF/spring`, không phải `META-INF/springs`, `META-INF/springboot` hoặc thư mục Java package.
- Tên file phải chính xác là `org.springframework.boot.autoconfigure.AutoConfiguration.imports`, bao gồm phần mở rộng `.imports`.
- Mỗi class nằm trên một dòng riêng.
- Ghi FQCN, không ghi tên ngắn như `WidgetAutoConfiguration`.
- Không ghi cú pháp Java như `import com.acme...`, không ghi dấu phẩy cuối dòng và không bọc tên class bằng dấu nháy.
- Có thể dùng comment `#`; không dùng comment kiểu `//`.
- Resource phải được đóng gói trong JAR được đưa vào runtime classpath.

Đây là resource metadata, không phải source Java. Đặt file cạnh class trong `src/main/java` hoặc trong thư mục package của class sẽ không tạo ra đúng resource path.

## 4. Tên lớp trong file phải khớp chính xác với class đã biên dịch

Giả sử source khai báo:

~~~java
package com.acme.widget.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
public class WidgetAutoConfiguration {
}
~~~

FQCN phải là:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Một số lỗi thường gặp:

| Entry sai | Lý do |
| --- | --- |
| `WidgetAutoConfiguration` | Thiếu package |
| `com.acme.widget.WidgetAutoConfiguration` | Package không trùng khai báo trong source |
| `com.acme.widget.autoconfigure.widgetAutoConfiguration` | Sai chữ hoa/chữ thường trong tên class |
| `com.acme.widget.autoconfigure.WidgetAutoConfiguration.java` | Imports cần tên class, không phải tên file source |
| `com.acme.widget.autoconfigure.WidgetAutoConfiguration.class` | Không ghi đuôi file bytecode |
| `com.acme.widget.autoconfigure.WidgetAutoConfiguration,` | Dấu phẩy không thuộc FQCN |

Tên package và class phân biệt chữ hoa/chữ thường. Điều này dễ bị bỏ sót khi phát triển trên filesystem không phân biệt case nhưng build hoặc triển khai trên Linux.

### Class lồng nhau dùng dấu $

Spring Boot cho phép khai báo auto-configuration class không phải top-level class. Khi đó tên trong file imports dùng `$` để phân cách class ngoài và class lồng:

~~~java
package com.acme.widget.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;

public class WidgetConfigurations {

    @AutoConfiguration
    public static class WebAutoConfiguration {
    }
}
~~~

Entry tương ứng:

~~~text
com.acme.widget.autoconfigure.WidgetConfigurations$WebAutoConfiguration
~~~

Tên dùng dấu chấm giữa package và class ngoài, sau đó dùng dấu `$` cho nested class. Trong thực tế, top-level auto-configuration class thường dễ đọc và ít lỗi đăng ký hơn.

## 5. Xác nhận class được biên dịch và package không bị thay đổi

Trước khi kiểm tra JAR, đối chiếu ba thứ:

1. Dòng `package` ở đầu file Java.
2. Tên class thực tế trong source.
3. Đường dẫn class sau khi compile.

Với class `com.acme.widget.autoconfigure.WidgetAutoConfiguration`, bytecode thường nằm ở:

~~~text
com/acme/widget/autoconfigure/WidgetAutoConfiguration.class
~~~

Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:clean :acme-widget-autoconfigure:compileJava
~~~

Maven:

~~~bash
./mvnw -pl acme-widget-autoconfigure -am clean compile
~~~

Sau compile, kiểm tra file class trong output directory:

~~~text
Gradle: acme-widget-autoconfigure/build/classes/java/main/
Maven:  acme-widget-autoconfigure/target/classes/
~~~

Nếu class đã được đổi package hoặc đổi tên, cập nhật FQCN trong imports cùng lúc. Chỉ đổi source mà giữ entry cũ sẽ để lại một tên đăng ký không còn tồn tại.

## 6. Đặt resource trong đúng module của multi-module build

Một cấu trúc thư viện thường có module auto-configure và module starter:

~~~text
acme-widget/
├── acme-widget-autoconfigure/
│   ├── src/main/java/com/acme/widget/autoconfigure/
│   │   └── WidgetAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-widget-spring-boot-starter/
    └── build.gradle hoặc pom.xml
~~~

Module `autoconfigure` sở hữu class cấu hình và descriptor. Module `starter` thường kéo module autoconfigure cùng dependency runtime cần thiết vào ứng dụng.

Gradle Kotlin DSL ở starter:

~~~kotlin
dependencies {
    api(project(":acme-widget-autoconfigure"))
}
~~~

Nếu không muốn dependency của module autoconfigure lộ ra compile API của starter, có thể dùng `implementation` tùy cách tổ chức module. Điều cần bảo đảm là JAR autoconfigure có mặt trên runtime classpath của consumer.

Maven ở starter:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-widget-autoconfigure</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Một lỗi hay gặp là file imports nằm đúng trong module autoconfigure nhưng starter không khai báo module này, hoặc chỉ khai báo ở scope test/provided. Khi đó test module có thể thấy class nhưng ứng dụng thật không có JAR chứa descriptor trên runtime classpath.

Kiểm tra dependency graph:

~~~bash
# Gradle: dependency của ứng dụng khi chạy
./gradlew :sample-app:dependencies --configuration runtimeClasspath

# Gradle: xem lý do module được chọn
./gradlew :sample-app:dependencyInsight --dependency acme-widget-autoconfigure --configuration runtimeClasspath

# Maven: cây dependency của ứng dụng
./mvnw -pl sample-app dependency:tree
~~~

## 7. Xác nhận resource đã được đóng gói vào JAR

File có trong source tree chưa đủ. Phải kiểm tra artifact sau khi build vì cấu hình resources, excludes hoặc custom source set có thể khiến file không được đưa vào JAR.

Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:clean :acme-widget-autoconfigure:jar
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar
~~~

Maven:

~~~bash
./mvnw -pl acme-widget-autoconfigure clean package
jar tf acme-widget-autoconfigure/target/acme-widget-autoconfigure-1.0.0.jar
~~~

Trong danh sách entry phải có chính xác:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trên Windows PowerShell, có thể lọc output:

~~~powershell
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports"
~~~

Trên macOS/Linux:

~~~bash
jar tf acme-widget-autoconfigure/target/acme-widget-autoconfigure-1.0.0.jar |
    grep "AutoConfiguration.imports"
~~~

Nếu không thấy entry, điều tra resource packaging:
- File có nằm dưới `src/main/resources` của đúng module không?
- Build có custom `sourceSets` hoặc `resources` khiến thư mục này bị thay thế không?
- Maven `<resources>` có `<includes>` hoặc `<excludes>` loại file `.imports` không?
- Resource có được thêm vào artifact đúng classifier/module không?
- Có đang kiểm tra nhầm JAR cũ trong thư mục build/target không?

Đừng chỉ kiểm tra JAR của ứng dụng nếu auto-configuration nằm trong dependency JAR lồng. Trước hết xác định JAR `acme-widget-autoconfigure` thực tế được đóng gói và kiểm tra chính JAR đó.

## 8. Đọc nội dung descriptor trong artifact

Sau khi xác nhận entry tồn tại, kiểm tra nội dung thực tế trong JAR. Đảm bảo dòng FQCN khớp source và không còn class name cũ.

Có thể giải nén resource ra thư mục tạm:

~~~bash
mkdir inspect-autoconfigure
cd inspect-autoconfigure
jar xf ../acme-widget-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Sau đó mở file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung mong đợi:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Nếu source file đúng nhưng artifact chứa tên cũ, kiểm tra:
- JAR có được build lại từ module hiện tại không.
- Có resource cùng tên ở source set khác hoặc module khác không.
- Build pipeline có lấy artifact từ local Maven/Gradle cache hoặc repository cũ không.
- Có nhiều version của cùng module trên runtime classpath không.

Khi phát hành, kiểm tra chính version JAR mà ứng dụng tiêu thụ, không chỉ JAR trong workspace đang phát triển.

## 9. Phân biệt thiếu descriptor với sai class name

Hai lỗi có biểu hiện khác nhau:

| Kiểm tra | Descriptor bị thiếu/sai path | FQCN trong descriptor sai |
| --- | --- | --- |
| `jar tf` | Không thấy file đúng đường dẫn | Có thấy file |
| Đọc nội dung file | Không có file để đọc | Có entry nhưng tên class không đúng |
| `ImportCandidates` | Không chứa class dự kiến | Chứa chuỗi sai hoặc không chứa class dự kiến |
| Nạp class | Không có candidate để nạp | Candidate có thể gây lỗi class loading/import |
| Hướng xử lý | Sửa vị trí/resource packaging | Sửa FQCN, package, class name hoặc dependency |

Nếu file có nhiều dòng, kiểm tra từng entry. Một dòng đúng không bù cho một dòng sai nếu Boot vẫn phải xử lý candidate sai trong cùng danh sách.

Không dùng việc ứng dụng “khởi động được” làm bằng chứng duy nhất. Nếu auto-configuration bị bỏ qua mà không có bean nào bắt buộc, ứng dụng vẫn có thể khởi động bình thường.

## 10. Kiểm tra trực tiếp danh sách candidates bằng ImportCandidates

Spring Boot cung cấp `ImportCandidates` để đọc danh sách import candidates theo đúng cơ chế classpath. Đây là cách kiểm tra descriptor tốt hơn việc tự ghép đường dẫn resource bằng chuỗi.

Ví dụ test JUnit 5 và AssertJ:

~~~java
package com.acme.widget.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.annotation.ImportCandidates;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationImportsTests {

    @Test
    void descriptorContainsTheExpectedAutoConfiguration() {
        var candidates = ImportCandidates.load(
                AutoConfiguration.class,
                getClass().getClassLoader());

        assertThat(candidates.getCandidates())
                .contains(WidgetAutoConfiguration.class.getName());
    }

    @Test
    void descriptorResourceIsVisibleOnTheTestRuntimeClasspath() {
        String resource =
                "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

        assertThat(getClass().getClassLoader().getResource(resource))
                .isNotNull();
    }
}
~~~

Test đầu tiên xác nhận Boot đọc được candidate có tên chính xác. Test thứ hai xác nhận resource path có thể được tìm thấy từ test runtime classpath.

Trong multi-module build, nên đặt test ở module chứa auto-configuration hoặc một consumer test module thực sự kéo starter vào. Nếu test chỉ chạy trong module autoconfigure, nó chưa chứng minh starter đã đưa dependency đó tới ứng dụng cuối.

Chạy Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:test --tests "*AutoConfigurationImportsTests"
~~~

Chạy Maven:

~~~bash
./mvnw -pl acme-widget-autoconfigure -Dtest=AutoConfigurationImportsTests test
~~~

Đây là test discovery metadata. Nó không thay thế test riêng cho bean registration và các condition của auto-configuration.

## 11. Phân biệt test discovery với test hành vi bean

Một test dùng:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(WidgetAutoConfiguration.class));
~~~

đưa class vào runner trực tiếp. Test này hữu ích để kiểm tra bean, nhưng **không xác minh** file `AutoConfiguration.imports` có được đọc hay không. Nếu descriptor bị thiếu, test vẫn có thể pass vì class đã được truyền trực tiếp.

Muốn kiểm tra end-to-end discovery, cần có một context consumer bật `@EnableAutoConfiguration` và phụ thuộc vào starter/JAR như ứng dụng thật.

Ví dụ cấu hình ứng dụng test:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
static class ConsumerApplication {
}
~~~

Test tích hợp:

~~~java
@SpringBootTest(classes = ConsumerApplication.class)
class StarterDiscoveryIntegrationTests {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversLibraryAutoConfigurationFromTheStarter() {
        assertThat(context).hasSingleBean(WidgetClient.class);
    }
}
~~~

Test này có ý nghĩa khi test runtime classpath chỉ chứa dependency mà consumer thực sự khai báo. Không thêm `WidgetAutoConfiguration.class` bằng `@Import` hoặc `AutoConfigurations.of(...)` trong test này, vì làm vậy sẽ bỏ qua đường khám phá mà ta cần xác minh.

## 12. Không nhầm AutoConfiguration.imports với spring.factories

Trong các phiên bản Spring Boot cũ, auto-configuration được đăng ký qua key `EnableAutoConfiguration` trong `META-INF/spring.factories`. Spring Boot 2.7 giới thiệu file imports chuyên biệt; Spring Boot 3.x dùng `AutoConfiguration.imports` để khám phá auto-configuration candidates.

Với Boot 3.3, file chuẩn là:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Không kỳ vọng một entry `EnableAutoConfiguration` cũ trong `spring.factories` sẽ thay thế file này.

Tuy nhiên, không có nghĩa phải xóa toàn bộ `spring.factories`. Spring Boot vẫn dùng file đó cho một số extension point khác, ví dụ `AutoConfigurationImportFilter` và `AutoConfigurationImportListener`. Chỉ di chuyển cơ chế đăng ký auto-configuration sang file imports; giữ các entry khác nếu chúng vẫn được framework sử dụng.

## 13. Kiểm tra ứng dụng có bật auto-configuration và không loại trừ class

Ngay cả khi descriptor và FQCN đều đúng, auto-configuration sẽ không được áp dụng nếu ứng dụng không bật cơ chế auto-configuration.

Thông thường ứng dụng dùng:

~~~java
@SpringBootApplication
public class SampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SampleApplication.class, args);
    }
}
~~~

`@SpringBootApplication` đã bao gồm `@EnableAutoConfiguration`. Nếu không dùng annotation tổng hợp này, cấu hình gốc phải bật `@EnableAutoConfiguration`.

Kiểm tra thêm các exclusion:

~~~java
@SpringBootApplication(
        exclude = LegacyWidgetAutoConfiguration.class
)
public class SampleApplication {
}
~~~

Hoặc property:

~~~properties
spring.autoconfigure.exclude=com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Nếu class nằm trong exclusion list, candidate có thể tồn tại trong descriptor nhưng không được áp dụng. Kiểm tra:
- `exclude` hoặc `excludeName` trên `@SpringBootApplication` / `@EnableAutoConfiguration`.
- Property `spring.autoconfigure.exclude`.
- Custom `AutoConfigurationImportFilter` của ứng dụng hoặc dependency.
- Ứng dụng có thực sự chạy đúng main configuration và runtime profile dự kiến không.

## 14. Khi candidate đã được tìm thấy nhưng bean vẫn không xuất hiện

Nếu `ImportCandidates` đã trả về đúng FQCN và class có thể nạp, bước tiếp theo là đọc condition report. Đừng tiếp tục sửa file imports khi discovery đã thành công.

Một auto-configuration có thể có:

~~~java
@AutoConfiguration
@ConditionalOnClass(WidgetClient.class)
@ConditionalOnProperty(
        prefix = "acme.widget",
        name = "enabled",
        havingValue = "true"
)
public class WidgetAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    WidgetClient widgetClient() {
        return new DefaultWidgetClient();
    }
}
~~~

Những điều kiện có thể khiến cấu hình không áp dụng:
- Dependency chứa `WidgetClient` không có trên runtime classpath.
- Property `acme.widget.enabled` không có hoặc không mang giá trị khớp condition.
- User đã cung cấp bean khiến `@ConditionalOnMissingBean` back off.
- Cấu hình bị exclude hoặc bị import filter loại bỏ.
- Condition trên resource không tìm thấy file được yêu cầu.

Nếu dùng `@ConditionalOnResource`, nhớ phân biệt resource của condition với descriptor discovery:

~~~java
@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:widget/widget-defaults.properties"
)
public class WidgetDefaultsAutoConfiguration {
}
~~~

Ở ví dụ này, file imports có thể hoàn toàn đúng và class vẫn được khám phá; nhưng condition không khớp nếu `widget/widget-defaults.properties` không có trên classpath. Đó là lỗi resource của condition, không phải lỗi thiếu `AutoConfiguration.imports`.

## 15. Dùng Condition Evaluation Report để xác định bước bị bỏ qua

Chạy ứng dụng với debug:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Hoặc:

~~~bash
java -jar sample-app.jar --debug
~~~

Spring Boot in Condition Evaluation Report, cho biết auto-configuration nào match hoặc không match và lý do. Với ứng dụng chạy trong môi trường khác, có thể bật logging phù hợp hoặc dùng Actuator conditions endpoint nếu endpoint được cấu hình và bảo vệ đúng cách.

Đọc report theo trình tự:

1. **Không có tên auto-configuration trong report:** kiểm tra descriptor path, JAR runtime, imports entry, auto-configuration enablement, exclusion và import filter.
2. **Có tên nhưng negative match:** đọc condition cụ thể; kiểm tra classpath, property, bean hoặc resource được yêu cầu.
3. **Configuration match nhưng bean method không tạo bean:** kiểm tra condition ở method, return type, dependency bean và lỗi khởi tạo.
4. **Bean definition có nhưng injection thất bại:** kiểm tra qualifier, primary, nhiều candidate và exception thực tế.

Một report không có class không chứng minh class name sai; có thể resource chưa nằm trên classpath hoặc ứng dụng đang dùng một artifact khác. Kết hợp report với `jar tf` và `ImportCandidates` để khoanh vùng.

## 16. Những nhầm lẫn và lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| File imports không xuất hiện trong JAR | Resource đặt sai thư mục hoặc bị build exclude | Đặt trong `src/main/resources/META-INF/spring` của module sở hữu auto-configuration |
| JAR có file nhưng candidate không có trong danh sách | Sai tên resource, đang đọc nhầm JAR hoặc classloader khác | Kiểm tra đúng path, runtime dependency và `ImportCandidates` |
| Candidate string có nhưng class không load | FQCN sai package/tên class hoặc class không có trên runtime classpath | Đối chiếu source, bytecode path và dependency graph |
| Tên class đúng trong IDE nhưng sai trên Linux | Khác chữ hoa/chữ thường | Đồng bộ package và class name chính xác |
| Đổi package nhưng quên sửa imports | Descriptor giữ FQCN cũ | Cập nhật entry trong cùng thay đổi refactor |
| Nested class không được tìm thấy | Dùng dấu chấm thay cho `$` | Dùng tên binary class có `$`, hoặc chuyển thành top-level class |
| Test `ApplicationContextRunner` pass nhưng starter consumer không nhận bean | Test nạp class trực tiếp bằng `AutoConfigurations.of(...)` | Thêm test `ImportCandidates` và consumer integration test |
| Test pass nhưng ứng dụng đóng gói không có bean | Dependency chỉ có ở test/compile, không có runtime | Kiểm tra runtimeClasspath/dependency tree |
| `spring.factories` còn entry cũ | Dùng cơ chế đăng ký auto-configuration của Boot 2.x | Đưa FQCN sang `AutoConfiguration.imports`; giữ các extension point khác còn dùng |
| Candidate có trong imports nhưng condition không khớp | Dependency/property/bean/resource condition không đạt | Đọc Condition Evaluation Report và sửa input tương ứng |
| File có trong source nhưng artifact vẫn chứa nội dung cũ | Build/cache/repository dùng JAR cũ | Clean build, kiểm tra version và artifact thực tế của consumer |
| Cấu hình chỉ hoạt động nhờ component scan | Auto-configuration đang bị nạp theo đường không đúng | Đăng ký bằng imports; dùng `@Import` cho cấu hình hỗ trợ |

## 17. Checklist chẩn đoán theo thứ tự

1. Xác nhận ứng dụng bật `@EnableAutoConfiguration`, thường qua `@SpringBootApplication`.
2. Xác nhận module autoconfigure có file đúng tên dưới `src/main/resources/META-INF/spring`.
3. Đọc file và so sánh từng FQCN với package/class source.
4. Với nested class, xác nhận dùng dấu `$`.
5. Clean compile module autoconfigure và xác nhận class `.class` tồn tại.
6. Build JAR rồi dùng `jar tf` kiểm tra descriptor.
7. Đọc nội dung descriptor bên trong JAR đã build.
8. Xác nhận starter đưa đúng JAR autoconfigure vào runtime classpath.
9. Dùng `ImportCandidates.load(AutoConfiguration.class, classLoader)` để kiểm tra candidate.
10. Nếu candidate có mặt, đọc Condition Evaluation Report và kiểm tra exclusion/condition.
11. Chạy consumer integration test không import trực tiếp class auto-configuration.
12. Kiểm tra lại artifact/version được triển khai, không chỉ source trong workspace.

## 18. Tự kiểm tra kiến thức

1. Spring Boot 3.3 đọc auto-configuration candidates từ resource nào? **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.**
2. Mỗi dòng trong imports chứa gì? **FQCN của một auto-configuration class.**
3. Có thể ghi tên class ngắn không? **Không; phải có package đầy đủ.**
4. Comment trong file imports bắt đầu bằng ký tự nào? **`#`.**
5. Nested class dùng ký tự nào để phân cách class ngoài? **`$`.**
6. File imports phải nằm ở đâu trong module Maven/Gradle mặc định? **`src/main/resources/META-INF/spring`.**
7. Vì sao kiểm tra source file là chưa đủ? **Resource có thể không được đóng gói vào JAR hoặc JAR không nằm trên runtime classpath.**
8. Test dùng `AutoConfigurations.of(MyAutoConfiguration.class)` có chứng minh descriptor đúng không? **Không; test đã truyền class trực tiếp.**
9. API nào đọc candidates theo đúng cơ chế imports? **`ImportCandidates.load(AutoConfiguration.class, classLoader)`.**
10. Candidate đã được tìm thấy nhưng condition không match thì nên xem gì? **Condition Evaluation Report.**
11. `@ConditionalOnResource` khác descriptor discovery thế nào? **Nó là condition của class đã được khám phá, kiểm tra một resource khác mà cấu hình yêu cầu.**
12. Có nên dùng component scan làm phương án thay thế imports không? **Không; auto-configuration phải được công bố bằng imports; dùng `@Import` cho cấu hình hỗ trợ.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): vị trí và nội dung `AutoConfiguration.imports`, class name, component scan, conditions, report và cách kiểm thử.
- [Spring Boot 3.3.13 — `ImportCandidates` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/annotation/ImportCandidates.html): cách tải danh sách candidates từ classpath.
- [Spring Boot 3.3.13 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation và quy tắc class auto-configuration.
- [Spring Boot 3.3.13 — `AutoConfigurationImportSelector` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): selector xử lý auto-configuration imports.
- [Spring Boot 3.3.13 — `@ConditionalOnResource` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html): điều kiện resource của auto-configuration.
