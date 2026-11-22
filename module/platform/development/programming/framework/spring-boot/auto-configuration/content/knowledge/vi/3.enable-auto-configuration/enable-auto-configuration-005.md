# AutoConfigurationImportSelector trong chuỗi xử lý @Import

> **Ngữ cảnh:** Spring Boot 3.3.x (Java 17+, Spring Framework 6.1). Bài này giải thích **cách Spring Boot đưa các auto-configuration vào quá trình xử lý `@Import`**, tập trung vào `AutoConfigurationImportSelector`, thời điểm xử lý deferred import, cách tìm candidate, loại trừ, lọc và sắp xếp. Mục tiêu là đọc được cơ chế kích hoạt và chẩn đoán nguyên nhân một auto-configuration có hoặc không được áp dụng.

## 1. Cần hiểu trước: auto-configuration là một nhánh của @Import

`@Import` của Spring Framework có thể khai báo:
- Một lớp `@Configuration` hoặc class chứa bean definition hợp lệ;
- Một `ImportSelector`, tức đối tượng **chọn tên các class cần import**;
- Một `ImportBeanDefinitionRegistrar`, tức đối tượng trực tiếp tham gia đăng ký bean definition.

Đây là các cơ chế của Spring Framework. Spring Boot xây tính năng tự cấu hình dựa trên nhánh **`ImportSelector`**, cụ thể là `AutoConfigurationImportSelector`.

Khi bạn viết:

```java
@SpringBootApplication
public class DemoApplication {
}
```

thì `@SpringBootApplication` đã bao gồm `@EnableAutoConfiguration`; còn `@EnableAutoConfiguration` dùng:

```java
@Import(AutoConfigurationImportSelector.class)
```

Hai đoạn là **trích yếu annotation để giải thích**, không phải hai file Java độc lập. Ý nghĩa: ứng dụng kích hoạt một selector, selector trả về các lớp cấu hình tự động cần đưa vào quy trình phân tích cấu hình. Spring Framework tiếp tục xử lý các lớp ấy và mới quyết định bean definition nào được đăng ký.

Điểm quan trọng: `AutoConfigurationImportSelector` **không phải bean nghiệp vụ**, cũng **không phải nơi trực tiếp tạo tất cả bean mặc định**. Nó lựa chọn **configuration classes**; sau đó Spring mới xử lý `@Bean`, `@Conditional...` và các bước tạo bean.

## 2. Sơ đồ dòng xử lý từ ứng dụng đến bean

```text
SpringApplication.run(...)
        |
        v
ApplicationContext.refresh()
        |
        v
ConfigurationClassPostProcessor
        |
        v
ConfigurationClassParser đọc cấu hình ứng dụng
        |
        +-- @SpringBootApplication
              |
              +-- @EnableAutoConfiguration
                    |
                    +-- @Import(AutoConfigurationImportSelector.class)
                          |
                          +-- DeferredImportSelector
                                 (xử lý sau đợt cấu hình thông thường)
                                   |
                                   +-- AutoConfigurationGroup
                                        |
                                        +-- tìm candidates từ .imports
                                        +-- loại trùng, exclude, import filter
                                        +-- hợp nhất, sắp thứ tự
                                        |
                                        v
                              danh sách configuration cần import
                                        |
                                        v
                   Spring phân tích @Configuration / @Conditional
                                        |
                                        v
                        đăng ký bean definitions phù hợp
                                        |
                                        v
                       khởi tạo beans theo dependencies
```

Đây là **sơ đồ khái niệm**, không khẳng định tất cả bước diễn ra theo một stack frame tuần tự duy nhất. Spring có nhiều vòng phân tích cấu hình và xử lý import; trong thực thi, selector deferred được gom và xử lý qua group.

Phân biệt ba mốc:

1. **Chọn candidate**: tên lớp nằm trong danh sách auto-configuration có thể xem xét.
2. **Import và đánh giá điều kiện**: Spring đọc metadata, phân tích configuration và chỉ đăng ký bean definitions phù hợp.
3. **Khởi tạo bean**: Spring tạo đối tượng thực khi đến lượt, dựa trên phụ thuộc và vòng đời context.

Có candidate **không đồng nghĩa** class được import; class được import **không đồng nghĩa** mọi `@Bean` trong class được đăng ký; có bean definition **không đồng nghĩa** object đã khởi tạo thành công.

## 3. Vì sao AutoConfigurationImportSelector là DeferredImportSelector?

`AutoConfigurationImportSelector` triển khai `DeferredImportSelector`, một biến thể của `ImportSelector`. Theo contract của Spring Framework, deferred selectors được xử lý **sau khi các `@Configuration` thông thường đã được phân tích**, thích hợp cho configuration có điều kiện phụ thuộc cấu hình do ứng dụng cung cấp.

So sánh:

| Kiểu import | Tác dụng | Thời điểm tương đối |
| --- | --- | --- |
| `@Import(SomeConfiguration.class)` | Import một cấu hình đã định danh | Trong quá trình Spring phân tích cấu hình có import |
| `ImportSelector` thường | Tính ra một số class để import | Trong quá trình xử lý import thông thường |
| `DeferredImportSelector` | Hoãn lựa chọn đến pha xử lý deferred import | Sau đợt phân tích các cấu hình thường; có thể gom theo `Group` |
| `AutoConfigurationImportSelector` | Chọn và sắp auto-configurations theo Spring Boot | Đi qua đường `DeferredImportSelector` và `AutoConfigurationGroup` |

Sự trì hoãn có giá trị thực tế: auto-configuration thường dùng `@ConditionalOnMissingBean` để **nhường chỗ** khi người xây ứng dụng tự khai báo bean. Nếu xử lý cấu hình mặc định quá sớm, kết quả condition trên bean definitions có thể khác mong muốn.

Tuy nhiên, `DeferredImportSelector` không đồng nghĩa rằng **mọi bean đã được tạo** trước khi auto-configuration chạy. Đây chủ yếu là thứ tự **phân tích cấu hình / đăng ký bean definitions**, không phải thứ tự khởi tạo object.

### 3.1. Vị trí trong lớp xử lý của Spring

Spring Framework dùng `ConfigurationClassPostProcessor` để nhận diện và xử lý các cấu hình. Trong quá trình đó, `ConfigurationClassParser` đọc `@Import` và nhận ra class triển khai `DeferredImportSelector`. Các selector deferred được giữ lại để xử lý ở pha thích hợp, có thể dùng `DeferredImportSelector.Group` để phối hợp các kết quả.

Khi `AutoConfigurationImportSelector` được phát hiện, Spring có thể cung cấp `BeanClassLoader`, `BeanFactory`, `Environment` và `ResourceLoader` nhờ các giao diện `Aware` mà selector triển khai. Selector cần các thông tin này để đọc resource candidates, properties exclude, metadata và các filter của Boot.

Không cần gọi thủ công `new AutoConfigurationImportSelector()` hay `selectImports()` trong ứng dụng thông thường. Đó là thành phần hạ tầng được `@EnableAutoConfiguration` kích hoạt qua `@Import`.

## 4. Những phương thức chính của AutoConfigurationImportSelector

Đọc theo **trách nhiệm** thay vì cố nhớ từng dòng source:

| API / thành phần | Trách nhiệm |
| --- | --- |
| `selectImports(AnnotationMetadata)` | Hình thức API của `ImportSelector`, trả danh sách class name khi không đi qua cơ chế nhóm |
| `getImportGroup()` | Cung cấp `AutoConfigurationGroup` để các deferred selector cùng nhóm có thể hợp nhất kết quả |
| `getAutoConfigurationEntry(AnnotationMetadata)` | Tính candidates và exclusions của một lần chọn |
| `getCandidateConfigurations(...)` | Lấy danh sách tên auto-configuration từ metadata imports |
| `getExclusions(...)` | Lấy các tên cấu hình cần loại trừ từ annotation và environment |
| `getAutoConfigurationImportFilters()` | Lấy các import filter có thể loại candidate sớm |
| `AutoConfigurationGroup.process(...)` | Thu các entry do selector cung cấp trong group |
| `AutoConfigurationGroup.selectImports()` | Hợp nhất, loại exclusions và sắp thứ tự rồi trả entries để import |

Trong đường **group** thường gặp của Spring Boot, đừng hình dung Spring chỉ gọi `selectImports()` một lần rồi dùng nguyên kết quả. `Group.process(...)` lấy `AutoConfigurationEntry`; `Group.selectImports()` trả danh sách cuối cùng sau hợp nhất và sắp thứ tự. Đây là chỗ dễ bỏ sót khi đọc call graph bằng cách chỉ tìm usages của `selectImports()`.

### 4.1. Ý nghĩa của AutoConfigurationEntry

`AutoConfigurationEntry` là dữ liệu nội bộ của selector, chứa:
- `configurations`: những class candidate còn lại sau các bước lọc ở entry;
- `exclusions`: các class bị yêu cầu loại trừ.

Khi có nhiều lần xử lý selector trong cùng group, group gom entries, loại mọi exclusion áp dụng rồi xử lý thứ tự cho toàn bộ danh sách. Không cần ứng dụng tự tạo hoặc chỉnh `AutoConfigurationEntry`; đây không phải API cấu hình nghiệp vụ.

## 5. Từ metadata đến danh sách candidate

Với Spring Boot 3.x, một thư viện tự cấu hình đăng ký candidate bằng tệp:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung ví dụ:

```text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.greeting.autoconfigure.GreetingMetricsAutoConfiguration
```

Mỗi dòng là một **tên đầy đủ** của configuration class. Spring Boot dùng `ImportCandidates` để đọc các tệp phù hợp từ các JAR trên classpath; vì vậy **dependency/runtime classpath và ClassLoader** quyết định các resource mà cơ chế này nhìn thấy.

Điều cần nhớ:
- `@AutoConfiguration` đánh dấu class là auto-configuration, nhưng **tự nó không khiến Boot tìm được class** nếu JAR không có tệp imports phù hợp.
- Tệp imports **công bố ứng viên**, không bảo đảm class cuối cùng được chọn.
- Một class trùng tên có thể xuất hiện từ nhiều resource; selector loại tên trùng.
- Spring Boot 3.x không sử dụng khóa `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `META-INF/spring.factories` làm đường đăng ký **candidate auto-configuration chính** như các phiên bản cũ. Tuy nhiên, `spring.factories` vẫn có thể phục vụ các extension point khác, chẳng hạn một số import filter/listener.
- Tệp imports cần có trong **artifact thực tế** mà ứng dụng tiêu thụ dùng. Đặt đúng ở source nhưng bỏ sót khi đóng JAR thì candidate không có.

### 5.1. “Dependency có mặt” không đủ để bean có mặt

Thêm starter có thể đưa cả thư viện lõi, adapter và tệp imports lên runtime classpath, nhưng vẫn có nhiều tầng điều kiện:

```text
JAR có trong runtime classpath?
   | có
   v
AutoConfiguration.imports chứa tên class?
   | có
   v
Candidate không bị exclude và filter loại sớm?
   | có
   v
Configuration có qua các @Conditional không?
   | có
   v
@Bean method có qua các @Conditional không?
   | có
   v
Bean definition được đăng ký; sau đó bean được tạo khi cần
```

Một `@ConditionalOnClass` không match có thể được loại sớm bởi filter có metadata, hoặc khi Spring đánh giá điều kiện của configuration. `@ConditionalOnMissingBean` thường được đánh giá trong quá trình xử lý bean definitions tương ứng. **Đừng coi import filter, class condition và bean condition là một thao tác giống nhau.**

## 6. Chuỗi chọn candidate: loại trùng, exclude, filter, sắp thứ tự

Xét đường xử lý logic của `getAutoConfigurationEntry(...)` ở Spring Boot 3.3:

1. **Kiểm tra cơ chế auto-configuration có bật không**. `spring.boot.enableautoconfiguration=false` có thể vô hiệu hóa mặc định lựa chọn auto-configuration của Boot.
2. **Đọc attributes của `@EnableAutoConfiguration`** từ metadata class khai báo import.
3. **Lấy candidates** từ các `AutoConfiguration.imports` khả dụng.
4. **Loại tên trùng** trong danh sách candidates.
5. **Thu thập exclusions** từ `exclude`, `excludeName` và property `spring.autoconfigure.exclude`.
6. **Kiểm tra exclusions không hợp lệ** theo quy tắc selector. Loại trừ một class hiện diện nhưng không phải candidate auto-configuration hợp lệ có thể tạo lỗi khởi động.
7. **Loại excluded candidates** khỏi danh sách đang xét.
8. **Chạy các `AutoConfigurationImportFilter`** để gạt bớt configurations không phù hợp dựa trên metadata.
9. **Phát sự kiện import** cho các `AutoConfigurationImportListener` được cấu hình.
10. **Trả về AutoConfigurationEntry**.

Sau đó, tại `AutoConfigurationGroup.selectImports()`, kết quả từ nhiều entries được hợp nhất, exclusions áp dụng trên tập chung và các auto-configuration được **sắp thứ tự** theo metadata trước khi thực sự import.

Đây là thứ tự **có ý nghĩa khái niệm** của nhánh Spring Boot 3.3; code source có các lớp helper, cache và chi tiết triển khai được giản lược.

### 6.1. Exclude có những nguồn nào?

Với ứng dụng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExampleApp {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApp.class, args);
    }
}
```

Đây là **chương trình minh họa riêng**, yêu cầu dependency chứa `DataSourceAutoConfiguration` và không thuộc project demo ở mục 8. `@SpringBootApplication(exclude=...)` cung cấp exclusion theo annotation.

Tùy chọn cấu hình tương đương về mục đích:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Nếu không thể tham chiếu class trong source (chẳng hạn dependency optional), có thể dùng `excludeName` với tên đầy đủ. Chỉ nên exclude khi hiểu ảnh hưởng đến các cấu hình liên quan, không dùng làm biện pháp ngẫu nhiên để “chữa startup”.

**Phân biệt:** `spring.autoconfigure.exclude` chỉ loại **những auto-configuration được nêu tên**. `spring.boot.enableautoconfiguration=false` là khóa ở mức rộng hơn đối với cơ chế chọn auto-configuration mặc định. Chúng không thay thế cho việc xóa các `@Configuration` do ứng dụng trực tiếp import.

### 6.2. AutoConfigurationImportFilter khác ConditionalOnClass như thế nào?

`AutoConfigurationImportFilter` là extension point cấp **lọc danh sách candidate**. Boot có thể tận dụng metadata được chuẩn bị trước để loại nhanh nhiều candidates trước khi phải xử lý chi tiết class configuration.

`@ConditionalOnClass` là **annotation điều kiện** trên configuration hay bean. Một số thông tin về điều kiện classpath có thể được tối ưu để lọc sớm, nhưng điều kiện cuối cùng vẫn phụ thuộc đường xử lý của Spring.

Không suy luận rằng mọi annotation `@Conditional` bất kỳ được selector hiểu và xử lý toàn bộ. Chẳng hạn, condition dựa trên bean do ứng dụng định nghĩa cần ngữ cảnh bean definitions, nên thường được đánh giá khi Spring xử lý configuration/bean definitions, không phải khi mới đọc tên ứng viên từ imports.

## 7. AutoConfigurationGroup và thứ tự xử lý

Lý do Boot dùng `DeferredImportSelector.Group`:
- Gom nhiều kết quả deferred selector có cùng group;
- Hợp nhất candidates và exclusions;
- Sắp xếp các auto-configuration theo các quan hệ thứ tự đã khai báo.

Ví dụ nếu có hai auto-configurations:

```java
@AutoConfiguration(beforeName = "com.example.feature.FeatureAutoConfiguration")
class CoreAutoConfiguration {
}

@AutoConfiguration(afterName = "com.example.core.CoreAutoConfiguration")
class FeatureAutoConfiguration {
}
```

Đây là **đoạn minh họa quan hệ thứ tự**, không phải source compile độc lập: hai class thuộc package khác nhau nên cần đặt trong tệp riêng, annotation imports và dependency tương ứng. `beforeName`, `afterName` hữu ích khi muốn tránh tham chiếu compile-time tới class khác.

Còn có `before`, `after`, `@AutoConfigureBefore`, `@AutoConfigureAfter` và `@AutoConfigureOrder`. Các metadata này tác động đến **thứ tự các cấu hình được xem xét/bean definitions được đăng ký**. Chúng **không bảo đảm thứ tự khởi tạo instance của bean**. Khởi tạo phụ thuộc graph, lazy behavior, `@DependsOn` và lifecycle Spring.

Sự khác biệt đặc biệt quan trọng với `@ConditionalOnMissingBean`: condition nhìn những bean definitions đã được xử lý đến thời điểm đánh giá. Nếu hai auto-configurations độc lập cùng muốn tạo một bean mặc định cùng type, hãy làm rõ thứ tự hoặc quy tắc ưu tiên; không dựa vào thứ tự ngẫu nhiên của file JAR.

## 8. Demo chạy được: chứng minh @EnableAutoConfiguration đi qua imports

Bài thực hành dùng **Spring Boot 3.3.13 / Java 17 / Maven**. Một Maven project chứa cả code ứng dụng và class auto-configuration nhằm nhìn rõ quá trình khám phá; khi phát hành thư viện thật, nên tách code thư viện khỏi ứng dụng tiêu thụ.

### 8.1. Cấu trúc file

```text
selector-flow-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── greeting/
    │   │       ├── GreetingService.java
    │   │       └── autoconfigure/GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/greeting/autoconfigure/
            └── GreetingAutoConfigurationTest.java
```

`com.example.app` và `com.example.greeting` là **hai nhánh package ngang cấp**. Vì `DemoApplication` ở `com.example.app`, component scan mặc định không tự quét `com.example.greeting.autoconfigure`. Auto-configuration chỉ xuất hiện nhờ cơ chế imports.

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>selector-flow-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Parent cung cấp dependency management phù hợp nhánh Spring Boot 3.3. Nếu dự án thực tế dùng phiên bản mới hơn, kiểm tra API tương ứng trước khi áp dụng các chi tiết nội bộ của selector.

### 8.3. API nghiệp vụ trung tính

`src/main/java/com/example/greeting/GreetingService.java`

```java
package com.example.greeting;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
```

Chức năng chào không phụ thuộc vào Spring. `@FunctionalInterface` chỉ giúp compiler xác nhận có một abstract method để dùng lambda.

### 8.4. Auto-configuration tạo bean mặc định có điều kiện

`src/main/java/com/example/greeting/autoconfigure/GreetingAutoConfiguration.java`

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return name -> "Xin chào, " + name + "!";
    }
}
```

Ở đây có **hai lớp quyết định**:
- Selector chọn **tên** `GreetingAutoConfiguration` vì có trong imports resource và không bị exclude.
- Spring xét `@ConditionalOnClass`, `@ConditionalOnProperty`, rồi `@ConditionalOnMissingBean` trước khi có bean default.

`@ConditionalOnMissingBean` giúp app cung cấp bean riêng; `matchIfMissing=true` nghĩa là property `demo.greeting.enabled` không tồn tại vẫn được coi là bật, miễn các điều kiện khác phù hợp.

### 8.5. Resource khám phá candidate

Tạo đúng file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
```

Đây là mối nối từ `AutoConfigurationImportSelector` đến class auto-configuration của thư viện. Nếu bỏ resource này, main class của app vẫn có `@EnableAutoConfiguration`, nhưng auto-configuration **riêng của demo** sẽ không được khám phá. Các auto-configuration khác do Spring Boot cung cấp có thể vẫn được nạp như bình thường.

### 8.6. ApplicationRunner quan sát bean có hay không

`src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.greeting.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showGreeting(ObjectProvider<GreetingService> services) {
        return args -> {
            GreetingService service = services.getIfAvailable();
            System.out.println(service == null
                    ? "GREETING=ABSENT"
                    : service.greet("Lan"));
        };
    }
}
```

`ObjectProvider` cho phép runner chạy cả khi auto-configuration không đăng ký bean. Không cần import `GreetingAutoConfiguration` trực tiếp vào `DemoApplication`.

Chạy trong thư mục project:

```bash
mvn test
mvn spring-boot:run
```

Khi mặc định được bật, chương trình in một dòng:

```text
Xin chào, Lan!
```

Đây là dòng của `ApplicationRunner`, **không phải toàn bộ stdout** (Maven và Spring Boot còn có startup logs).

Nếu chạy với property disable:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.greeting.enabled=false
```

Dòng do runner in là:

```text
GREETING=ABSENT
```

Vì property condition không match, configuration không tạo `GreetingService`. Điều này **không đồng nghĩa** selector không tìm ra candidate; selector vẫn có thể chọn class qua imports, còn Spring loại nó ở pha điều kiện.

### 8.7. Ứng dụng tự cung cấp bean: auto-configuration back off

Thêm method sau **vào trong `DemoApplication`** ở mục 8.6:

```java
@Bean
GreetingService customGreetingService() {
    return name -> "App chào " + name + "!";
}
```

Đây là **đoạn bổ sung vào class đã có**, không phải file Java độc lập. Chạy không kèm property disable. Khi app đã đăng ký bean cùng type, bean mặc định từ auto-configuration không được đăng ký do `@ConditionalOnMissingBean`; dòng của runner là:

```text
App chào Lan!
```

Điểm mấu chốt để hiểu deferred import: ứng dụng có cơ hội khai báo bean của chính mình, rồi configuration mặc định xử lý phù hợp điều kiện. **Thứ tự đăng ký bean definitions** là điều cần nghiên cứu, chứ không phải chờ app khởi tạo object trước.

## 9. Kiểm thử các nhánh bằng ApplicationContextRunner

Tạo file `src/test/java/com/example/greeting/autoconfigure/GreetingAutoConfigurationTest.java`:

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenAllowed() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("Lan"))
                    .isEqualTo("Xin chào, Lan!");
        });
    }

    @Test
    void doesNotCreateWhenDisabled() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(GreetingService.class));
    }

    @Test
    void backsOffToConsumerBean() {
        runner.withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class).greet("Lan"))
                            .isEqualTo("Consumer: Lan");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        GreetingService consumerGreetingService() {
            return name -> "Consumer: " + name;
        }
    }
}
```

Chạy `mvn test`; ba test chứng minh bean default có thể được đăng ký, bị chặn bởi property hoặc nhường chỗ cho bean consumer.

**Giới hạn của test:** `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` chỉ định thẳng class, **không tự chứng minh việc `AutoConfigurationImportSelector` tìm class qua resource imports**. Muốn xác minh toàn bộ đường `@Import`, chạy `DemoApplication` thật hoặc thêm integration test khởi động ứng dụng và kiểm tra content JAR.

### 9.1. Kiểm tra resource có được đóng gói

Dùng Maven:

```bash
mvn package
jar tf target/selector-flow-demo-0.0.1-SNAPSHOT.jar
```

Trong danh sách phải có resource `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` bên trong `BOOT-INF/classes/` của executable JAR. Khi tách thành thư viện JAR thông thường, resource nằm ở đường `META-INF/spring/...` tương ứng. Với project demo này, lệnh `jar tf` có thể in nhiều mục; điều quan trọng là sự hiện diện của resource và tên class đúng.

## 10. Chẩn đoán chính xác: candidate không được chọn hay bean không được tạo?

Khi “thêm starter nhưng không thấy bean”, chia thành các trường hợp:

| Hiện tượng | Nên kiểm tra | Đừng kết luận vội |
| --- | --- | --- |
| Không thấy auto-configuration trong danh sách candidates | JAR, runtime classpath, resource imports, ClassLoader | “`@ConditionalOnMissingBean` làm mất candidate” |
| Candidate bị loại qua exclude | `@SpringBootApplication(exclude=...)`, `excludeName`, `spring.autoconfigure.exclude` | “Thiếu dependency nên phải thêm starter” |
| Class configuration xuất hiện ở negative matches | `@ConditionalOnClass`, `@ConditionalOnProperty`, web condition, resource condition | “Selector lỗi” |
| Bean default không xuất hiện dù configuration match | `@ConditionalOnMissingBean`, bean method condition, bean của app | “Auto-configuration không import được” |
| Có bean definition nhưng startup thất bại | Exception lúc tạo bean, missing runtime class, cấu hình/credentials | “Condition không match” |
| Auto-configurations chạy theo thứ tự bất ngờ | `before/after`, `@AutoConfigureOrder`, metadata, dependency khác | “Thứ tự JAR trong classpath quyết định mọi thứ” |

Có thể bật condition evaluation report:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Khi xem report, phân biệt:
- **Positive matches**: cấu hình/condition đã match;
- **Negative matches**: condition không match;
- **Exclusions**: những auto-configuration bị loại trừ;
- **Unconditional classes**: các auto-configuration không có điều kiện tương ứng ở mức báo cáo.

Tên mục và cách trình bày chính xác phụ thuộc patch version. `--debug` chỉ phục vụ chẩn đoán; output có thể dài.

Nếu có Actuator và đã cấu hình bảo vệ endpoint đúng cách, `/actuator/conditions` có thể cung cấp báo cáo điều kiện. Không mở rộng truy cập thông tin cấu hình/điều kiện một cách vô ý trên production.

### 10.1. Cách đọc hai tình huống gần giống nhau

**Tình huống A — không có resource imports:** thư viện có `GreetingAutoConfiguration.class` nhưng JAR phát hành không chứa file `AutoConfiguration.imports`. Selector không có tên class đó để chọn. Thêm `@ConditionalOnClass` vào class không sửa được lỗi **khám phá candidate**.

**Tình huống B — có imports nhưng property tắt:** selector có candidate, song `@ConditionalOnProperty(demo.greeting.enabled=true)` không đạt. Chỉ sửa file imports không làm bean xuất hiện; cần sửa property hoặc chủ động cung cấp bean.

Hai tình huống cuối cùng đều làm `GreetingService` vắng mặt, nhưng nguyên nhân nằm ở **hai pha khác nhau**.

## 11. Các ngộ nhận dễ gặp khi đọc source

1. **“`@Import` chỉ import class được ghi trực tiếp trong annotation.”** Không. `@Import` có thể import `ImportSelector`, và selector trả danh sách class do logic tính toán.
2. **“`selectImports()` luôn là nơi trả kết quả cuối cùng.”** Với `DeferredImportSelector.Group`, kết quả có thể đi qua `Group.process(...)` và `Group.selectImports()`; Spring Boot dùng con đường nhóm để hợp nhất, exclude và sort.
3. **“Resource imports là danh sách bean.”** Sai. Nó là danh sách **auto-configuration class names**. Bean được quyết định trong bước Spring xử lý configuration.
4. **“Nếu class trong imports thì chắc chắn đăng ký.”** Không. Exclusion, filter và condition có thể gạt class hoặc bean.
5. **“Deferred nghĩa là ứng dụng đã khởi tạo xong mọi bean.”** Không. Đây là cơ chế hoãn **import trong pha parsing configuration**.
6. **“`@AutoConfiguration(after=...)` ép bean tạo sau.”** Không. Nó chi phối thứ tự áp dụng các configuration; thứ tự tạo bean phụ thuộc dependency graph và lifecycle.
7. **“Chỉ cần thêm dependency là biết selector đã chạy.”** Không. Phải xác minh `@EnableAutoConfiguration`, resource imports và condition report.
8. **“Muốn cấu hình của thư viện được khám phá thì phải `@ComponentScan` package của nó.”** Không. Auto-configuration của thư viện nên nằm ngoài component scan ứng dụng và được khai báo qua resource imports.
9. **“Loại exclusion là xóa cả dependency.”** Không. Exclude chỉ bỏ auto-configuration tương ứng; class/JAR vẫn có thể nằm trên runtime classpath, và ứng dụng có thể tự sử dụng chúng.
10. **“Mọi `@Conditional` được xử lý một lượt trong selector.”** Không. Import filters là tối ưu hóa cấp candidates; nhiều condition vẫn do Spring đánh giá khi parse configuration hoặc đăng ký bean definitions.

## 12. Câu hỏi kiểm tra sau bài

**Câu 1.** Vì sao `@SpringBootApplication` có thể kích hoạt hàng trăm auto-configurations dù trên class ứng dụng không có hàng trăm `@Import(SomeClass.class)`?

Vì `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`; annotation này import một **selector**. Selector khám phá candidates từ resources trên classpath rồi cung cấp danh sách configuration classes.

**Câu 2.** Tại sao `AutoConfigurationImportSelector` cần deferred import?

Vì auto-configuration là mặc định có điều kiện, thường cần xét các bean definitions mà ứng dụng đã khai báo trước; trì hoãn parsing giúp cơ chế back-off hoạt động đúng trong cấu trúc Spring thông thường.

**Câu 3.** `AutoConfiguration.imports` và `@ConditionalOnMissingBean` quyết định cùng một việc không?

Không. Imports quyết định **candidate configuration có thể được khám phá**; bean condition quyết định **bean definition có nên được đăng ký**.

**Câu 4.** Nếu `GreetingAutoConfiguration` được chọn nhưng `demo.greeting.enabled=false`, vì sao không thấy bean?

Vì class đã được phát hiện nhưng condition thuộc pha xử lý configuration không đạt. Đây là expected behavior, không phải candidate discovery failure.

**Câu 5.** `@AutoConfiguration(afterName=...)` có đảm bảo constructor của bean chạy sau bean kia?

Không. Metadata sắp thứ tự auto-configuration; thứ tự khởi tạo object do Spring dependency resolution và lifecycle quyết định.

**Câu 6.** Kiểm thử `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` pass có chứng minh file imports đúng không?

Không. Runner được cấp thẳng class auto-configuration. Cần kiểm tra JAR/resource và chạy ứng dụng consumer thật để chứng minh đường discovery qua selector.

## 13. Tóm tắt mô hình tư duy

`AutoConfigurationImportSelector` nằm tại **cầu nối giữa `@Import` của Spring Framework và metadata auto-configuration của Spring Boot**. Nó đọc candidates, loại exclusions, chạy filters, cùng group hợp nhất/sort và chuyển các configuration classes hợp lệ trở lại quy trình xử lý của Spring. Sau đó Spring mới đánh giá conditions, đăng ký bean definitions và khởi tạo bean theo phụ thuộc thực tế.

Nhớ thứ tự câu hỏi khi debug:

```text
Ứng dụng có @EnableAutoConfiguration?
  -> selector có nhìn thấy AutoConfiguration.imports?
  -> candidate có bị exclude/filter?
  -> cấu hình có pass @Conditional?
  -> bean method có pass @Conditional?
  -> bean có khởi tạo thành công?
```

### Tài liệu chính thức

- Spring Boot 3.3 Javadoc — `AutoConfigurationImportSelector`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Framework 6.1 Javadoc — `DeferredImportSelector`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Spring Framework 6.1 Javadoc — `ImportSelector`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ImportSelector.html
