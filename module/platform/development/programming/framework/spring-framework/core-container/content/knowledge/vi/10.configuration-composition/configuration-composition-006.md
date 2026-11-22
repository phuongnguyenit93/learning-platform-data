# Thời điểm xử lý DeferredImportSelector trong Spring Core Container

## 1. Tổng quan

Khi sử dụng Java configuration, Spring có thể ghép các lớp cấu hình thông qua `@Import`. Ta có thể import class trực tiếp, nhờ `ImportSelector` chọn các class cần import, hoặc dùng `DeferredImportSelector` để **trì hoãn bước chọn imports** đến sau khi các class cấu hình thông thường được Spring phân tích.

Điểm dễ hiểu sai là chữ **deferred**. Ở đây, nó có nghĩa **xử lý muộn trong pha phân tích metadata của configuration**, không phải **tạo bean sau khi ứng dụng khởi động**, không phải **chạy trên thread nền**, cũng không phải **bật lazy initialization**.

Theo hợp đồng Javadoc của Spring, `DeferredImportSelector` là một dạng `ImportSelector` được xử lý sau các `@Configuration` classes trong quá trình configuration processing. Đây là nền tảng hữu ích cho những imports phụ thuộc vào điều kiện, nhóm lựa chọn hoặc chiến lược auto-configuration.

### Mục tiêu

Sau bài học, bạn sẽ:

1. Nắm rõ điểm khác biệt giữa `ImportSelector` và `DeferredImportSelector`.
2. Đọc đúng timeline parser → deferred imports → bean definitions → bean instances.
3. Hiểu `AnnotationMetadata`, `getImportGroup()`, `Group.process()`, `Group.selectImports()` và `Group.Entry`.
4. Biết tác động và giới hạn của `Ordered`/`@Order` đối với deferred selectors.
5. Tránh dựa vào trạng thái bean runtime hoặc bean-definition registry chưa hoàn chỉnh trong thời điểm selector chạy.
6. Chạy một ví dụ Java 17+ có normal selector, nested normal selector và deferred group, đo thứ tự callbacks.
7. Hiểu vì sao Spring Boot dùng `AutoConfigurationImportSelector`, nhưng không nhầm API Boot với Spring Core.
8. Chẩn đoán lỗi khi một cấu hình được chọn bởi deferred selector vẫn không xuất hiện thành bean.

## 2. Những gì @Import có thể nhận

`@Import` hỗ trợ nhiều cách bổ sung nguồn cấu hình. Trường hợp tường minh nhất:

```java
@Configuration
@Import({StorageConfiguration.class, PricingConfiguration.class})
public class ApplicationConfiguration {
}
```

Đây là đoạn cấu hình minh họa, giả định hai class `StorageConfiguration` và `PricingConfiguration` có thật trong classpath và đã import `Configuration`, `Import`. Khi `ApplicationConfiguration` được nạp, Spring phân tích `@Import` rồi đưa các cấu hình liên quan vào cùng ApplicationContext.

Ngoài việc nhập class trực tiếp, `@Import` có thể làm việc với:

| Loại | Ý nghĩa |
| --- | --- |
| `ImportSelector` | Chọn tên class/configuration cần import trong quá trình xử lý thông thường. |
| `DeferredImportSelector` | Chọn tên class/configuration tại pha deferred của parser. |
| `ImportBeanDefinitionRegistrar` | Can thiệp vào registry để đăng ký bean definitions bằng code. |
| Class cấu hình hoặc component | Được thêm trực tiếp vào luồng xử lý cấu hình. |

`DeferredImportSelector` **kế thừa `ImportSelector`**, vì vậy nó vẫn sử dụng:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata);
```

Kết quả là **mảng tên class đầy đủ**, chẳng hạn `com.example.feature.FeatureConfiguration`, không phải bean name hay object instance. Nếu class là nested class Java, `SomeNestedConfig.class.getName()` trả binary name hợp lệ; nên dùng API này thay vì tự viết chuỗi.

## 3. Normal selector và deferred selector

Một normal selector:

```java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public final class NormalFeatureSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {
            NormalFeatureConfiguration.class.getName()
        };
    }
}
```

Đây là class minh họa, cần class `NormalFeatureConfiguration` cụ thể. Khi parser gặp nó trong `@Import`, Spring xử lý selector trong luồng phân tích imports thông thường và có thể tiếp tục parse configuration được trả về.

Một deferred selector:

```java
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public final class DeferredFeatureSelector
        implements DeferredImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {
            DeferredFeatureConfiguration.class.getName()
        };
    }
}
```

Đây cũng là class minh họa cần `DeferredFeatureConfiguration`. Khác biệt không nằm ở chữ ký method mà ở **thời điểm `ConfigurationClassParser` gọi/điều phối nó**.

| Thuộc tính | ImportSelector | DeferredImportSelector |
| --- | --- | --- |
| Kế thừa | Interface gốc | Mở rộng ImportSelector |
| Kết quả cơ bản | `String[]` class names | `String[]` class names |
| Thời điểm xử lý | Khi parser xử lý normal imports | Sau lượt parsing các configuration thông thường |
| Group API | Không có interface Group tương ứng | `DeferredImportSelector.Group` |
| Điều khiển singleton creation | Không | Không |
| Hỗ trợ điều kiện khi import | Có thể | Có thể; thường hữu ích hơn khi cần xử lý muộn |
| Dùng cho Spring Boot auto-configuration | Không phải cơ chế chính của Boot auto-configuration | Có: `AutoConfigurationImportSelector` implements DeferredImportSelector |

Dù dùng selector nào, **Spring vẫn cần tạo bean definitions và quản lý bean lifecycle sau đó**.

## 4. Chính xác deferred xảy ra ở đâu trong refresh?

Một `AnnotationConfigApplicationContext` có chu trình `refresh()`. Trong phần xử lý BeanFactoryPostProcessors, `ConfigurationClassPostProcessor` phân tích các configuration classes và phối hợp `ConfigurationClassParser` với việc đăng ký metadata.

Sơ đồ khái niệm:

```text
new AnnotationConfigApplicationContext(RootConfig.class)
                         |
                         v
                      refresh()
                         |
            ConfigurationClassPostProcessor
                         |
                         v
               ConfigurationClassParser
                         |
           +-------------+-------------+
           |                           |
   @Import(Config.class)       @Import(ImportSelector.class)
           |                           |
           +---------- normal processing
                         |
                @Import(DeferredImportSelector.class)
                         |
                    thu gom selector
                         |
                 parse xong các cấu hình thường
                         |
                   deferred handler
                         |
                 group/order/filter imports
                         |
                 parse các deferred imports
                         |
                         v
                bean-definition reader
                         |
                 registry có bean definitions
                         |
          register BeanPostProcessors / tạo singletons
                         |
                    refresh hoàn tất
```

**Điểm quan trọng:** khái niệm “sau tất cả `@Configuration` được xử lý” ở tài liệu API nói về **configuration parsing**, không có nghĩa Spring đã gọi tất cả constructor hoặc `@Bean` factory methods.

Có thể phân ra bốn thời điểm:

1. **Parse source metadata:** tìm config, annotation và import candidates.
2. **Choose imports:** normal selectors được xử lý trong parse; deferred selectors được chọn ở giai đoạn deferred.
3. **Register bean definitions:** đưa metadata bean cuối cùng vào BeanFactory/registry.
4. **Instantiate bean:** gọi constructor/factory methods theo scope và dependency, chạy post-processors/lifecycle.

Chính pha thứ **hai** được trì hoãn bởi `DeferredImportSelector`.

### Tại sao không thể xem deferred là lazy?

`@Lazy` ảnh hưởng thời điểm bean singleton được khởi tạo (trừ khi dependency khác khiến phải tạo sớm). `DeferredImportSelector` ảnh hưởng thời điểm Spring **quyết định class cấu hình nào được nhập**. Một cấu hình được deferred import vẫn có thể khai báo singleton eager được khởi tạo trước khi `refresh()` hoàn thành.

Ví dụ một deferred selector chọn cấu hình có bean `HttpClient`. Nếu bean đó không lazy và là singleton bình thường, Spring vẫn có thể khởi tạo HTTP client trong startup. Không được dùng deferred selector để bảo đảm client chỉ mở kết nối tại request đầu tiên.

## 5. Parser thu gom deferred imports ra sao?

Về mặt implementation, `ConfigurationClassParser` gặp một implementation `DeferredImportSelector` và **giữ nó cùng metadata của class đã import selector**, thay vì xử lý ngay như normal `ImportSelector`.

Cuối lượt parse, deferred selectors được gom và xử lý, có thể sắp theo thứ tự `Ordered` và gom vào các groups. Imports mà Group trả về tiếp tục được parser xử lý như những configuration candidates.

Quá trình này có thể mở ra imports mới, trong đó có imports lồng nhau. Vì vậy sơ đồ một vòng là mô hình học tập, **không phải hợp đồng rằng parser chỉ chạy đúng một pass**.

### Không suy luận quá mức về BeanFactory

Ngay trong callback `DeferredImportSelector.selectImports`, việc `ConfigurationClassParser` đã biết một `@Bean` method không nhất thiết có nghĩa bean definition của method ấy đã được BeanDefinitionReader đăng ký vào registry.

Do đó, một selector tự viết như sau là thiết kế dễ gây lỗi:

```java
// Phản ví dụ mang tính khái niệm:
// Trong selectImports(), không gọi beanFactory.getBean("appService")
// để kiểm tra xem một bean nghiệp vụ đã tồn tại hay chưa.
```

Đặc biệt không gọi `getBean()` để ép tạo bean nghiệp vụ trong lúc parsing; điều này có thể đưa bean creation vào pha sớm trước khi processor/lifecycle sẵn sàng.

Thay vào đó, ưu tiên metadata importer, `Environment` hoặc cơ chế condition có hợp đồng phase rõ ràng.

## 6. AnnotationMetadata thuộc class nào?

Phương thức:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata)
```

nhận metadata của **class đang thực hiện import**, không tự động là metadata của class sẽ được import.

Giả sử cấu hình:

```java
@Configuration
@Import(DeferredFeatureSelector.class)
class PaymentApplicationConfiguration {
}
```

Khi selector được xử lý, metadata mà nó nhận tương ứng `PaymentApplicationConfiguration`. Selector có thể đọc annotations hoặc meta-annotations được khai báo trên cấu hình ấy.

Nếu tạo một annotation `@EnableFeature` có attributes rồi meta-annotate bằng `@Import`, selector có thể đọc attributes từ metadata của configuration class đã dùng annotation đó. Khi cần hỗ trợ meta-annotation và alias, nên sử dụng metadata/MergedAnnotations API của Spring thay vì reflection trực tiếp trên các bean instances chưa được tạo.

Điều này liên hệ mật thiết với `Group.Entry`: entry không chỉ mang tên target class, mà còn mang metadata của importer.

## 7. DeferredImportSelector.Group là gì?

Một deferred selector có thể override:

```java
Class<? extends DeferredImportSelector.Group> getImportGroup();
```

Mặc định không cung cấp group class riêng (giá trị mặc định có thể là `null`). Nếu selector trả một class Group, Spring dùng group đó để **thu thập nhiều imports và quyết định kết quả cuối cùng**.

Interface Group có:

```java
void process(
        AnnotationMetadata metadata,
        DeferredImportSelector selector);

Iterable<DeferredImportSelector.Group.Entry> selectImports();
```

**`Group.process`** nhận importing metadata và selector tương ứng. Group có thể tự gọi `selector.selectImports(metadata)`, ghi nhận candidates, deduplicate hoặc áp dụng policy.

**`Group.selectImports`** trả những `Entry` mà parser sẽ tiếp tục nhập. Mỗi Entry chứa metadata của importing configuration và tên class import.

Sơ đồ:

```text
Selector A --> Group.process(metadataA, selectorA) --+
                                                       |
Selector B --> Group.process(metadataB, selectorB) --+--> Group state
                                                       |
Selector C --> Group.process(metadataC, selectorC) --+
                                                       |
                                                      v
                                              Group.selectImports()
                                                      |
                                                      v
                                             Iterable<Group.Entry>
                                                      |
                                                      v
                                            Parser xử lý config imports
```

**Một điểm hay bị nhầm:** khi dùng Group, Spring không nhất thiết gọi selector `selectImports` theo một bước tách biệt trước Group. Chính implementation `Group.process` quyết định có gọi phương thức đó hay không. Nếu custom group bỏ qua việc gọi selector, các side effects đặt trong `selector.selectImports` sẽ không xảy ra. Không nên đặt business side effects ở bất kỳ selector callback nào.

### Vì sao Group có giá trị?

Khi nhiều modules cùng đóng góp imports, Group có thể:

- Thu thập imports của nhiều selectors.
- Loại trùng class names theo quy tắc được chỉ định.
- Áp exclusions.
- Sắp xếp thứ tự xử lý class imports.
- Quyết định ưu tiên giữa nhiều tập ứng viên.

Tuy nhiên, **loại trùng imports không đồng nghĩa loại trùng bean definitions của hai config khác nhau**. Các xung đột bean names/types vẫn phải được xử lý tại tầng registration/DI.

## 8. Ordered và @Order

`DeferredImportSelector` có thể implement `Ordered` hoặc sử dụng `@Order` để đưa ra precedence tương đối giữa các deferred selectors. Với `Ordered`, giá trị số nhỏ hơn thường có độ ưu tiên cao hơn.

Nhưng **đừng đánh đồng**:

- Selector có order thấp với target bean được tạo trước.
- Import được parse trước với bean chắc chắn xuất hiện trước trong singleton cache.
- Ordering selector với `@DependsOn` của bean.
- Ordering trong Spring Boot auto-configuration với global ordering của mọi custom selector.

Order ở đây phục vụ **pha selection**. Khi có Group, policy Group và ordering của các groups/imports còn ảnh hưởng cách kết quả cuối được đưa vào parser. Nếu yêu cầu application đảm bảo dependency, phải thể hiện dependency qua constructor/method parameters, `@DependsOn` khi đúng nghĩa, hoặc giải pháp lifecycle thích hợp.

## 9. Ví dụ đầy đủ Java 17+: đo thứ tự callback

Chúng ta sử dụng Spring Framework **6.2.19** và `AnnotationConfigApplicationContext`, không cần Boot. Bài thực hành có:

- `ImmediateSelector` — một normal `ImportSelector`.
- `ImmediateConfiguration` — class mà normal selector chọn.
- `NestedImmediateSelector` — normal selector được import **bên trong** `ImmediateConfiguration`.
- `DeferredSelector` — `DeferredImportSelector`.
- `DeferredGroup` — Group nhận selector, gọi `selectImports`, trả `Entry`.
- `DeferredConfiguration` — class được chọn ở pha deferred.
- Một danh sách ghi sự kiện. Sau khi context refresh, chương trình kiểm chứng **thứ tự selector callbacks** chứ không dùng thứ tự tạo bean làm đại diện.

### 9.1. Cấu trúc dự án

```text
deferred-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DeferredDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'deferred-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.DeferredDemo'
}
```

### 9.2. Java source

**`src/main/java/demo/DeferredDemo.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public final class DeferredDemo {
    private static final List<String> EVENTS = new ArrayList<>();

    @Configuration(proxyBeanMethods = false)
    @Import({ImmediateSelector.class, DeferredSelector.class})
    public static class RootConfig {
    }

    public static class ImmediateSelector implements ImportSelector {
        @Override
        public String[] selectImports(AnnotationMetadata metadata) {
            EVENTS.add("immediate");
            return new String[] { ImmediateConfig.class.getName() };
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(NestedSelector.class)
    public static class ImmediateConfig {
        @Bean
        String immediateMessage() {
            return "immediate";
        }
    }

    public static class NestedSelector implements ImportSelector {
        @Override
        public String[] selectImports(AnnotationMetadata metadata) {
            EVENTS.add("nested");
            return new String[0];
        }
    }

    public static class DeferredSelector implements DeferredImportSelector {
        @Override
        public Class<? extends Group> getImportGroup() {
            return DeferredGroup.class;
        }

        @Override
        public String[] selectImports(AnnotationMetadata metadata) {
            EVENTS.add("deferred.select");
            return new String[] { DeferredConfig.class.getName() };
        }
    }

    public static class DeferredGroup
            implements DeferredImportSelector.Group {

        private final List<Entry> entries = new ArrayList<>();

        @Override
        public void process(
                AnnotationMetadata metadata,
                DeferredImportSelector selector) {
            EVENTS.add("deferred.process");
            for (String name : selector.selectImports(metadata)) {
                entries.add(new Entry(metadata, name));
            }
        }

        @Override
        public Iterable<Entry> selectImports() {
            EVENTS.add("deferred.group.result");
            return List.copyOf(entries);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DeferredConfig {
        @Bean
        String deferredMessage() {
            return "deferred";
        }
    }

    public static void main(String[] args) {
        EVENTS.clear();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(RootConfig.class)) {

            int immediate = EVENTS.indexOf("immediate");
            int nested = EVENTS.indexOf("nested");
            int process = EVENTS.indexOf("deferred.process");
            int select = EVENTS.indexOf("deferred.select");
            int result = EVENTS.indexOf("deferred.group.result");

            System.out.println("immediate-before-deferred="
                    + (immediate >= 0 && immediate < process));

            System.out.println("nested-before-deferred="
                    + (nested >= 0 && nested < process));

            System.out.println("group-calls-selector="
                    + (process >= 0 && process < select));

            System.out.println("selector-before-group-result="
                    + (select >= 0 && select < result));

            System.out.println("immediate-bean="
                    + context.getBean("immediateMessage", String.class));

            System.out.println("deferred-bean="
                    + context.getBean("deferredMessage", String.class));

            System.out.println("event-count=" + EVENTS.size());
        }
    }
}
```

Tất cả class đều thuộc một source file, nên bạn có thể copy nội dung vào đúng vị trí và chạy. `RootConfig`, `ImmediateConfig` và `DeferredConfig` là public static nested classes; Spring có thể import chúng qua tên class thực lấy từ `Class.getName()`. Không tạo riêng file cho các nested classes.

### 9.3. Chạy

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Chỉ gọi `javac DeferredDemo.java` riêng không đủ nếu không cung cấp Spring jars vào classpath.

**Stdout dự kiến từ các println:**

```text
immediate-before-deferred=true
nested-before-deferred=true
group-calls-selector=true
selector-before-group-result=true
immediate-bean=immediate
deferred-bean=deferred
event-count=5
```

Log của Gradle/runtime nếu xuất hiện không phải một phần của các dòng `System.out.println`.

### 9.4. Giải thích kết quả

1. Spring nạp `RootConfig` và gặp `@Import` gồm một normal selector và một deferred selector.
2. `ImmediateSelector` được xử lý trong luồng normal import, ghi `immediate` và chọn `ImmediateConfig`.
3. `ImmediateConfig` có `@Import(NestedSelector.class)`; nested normal selector ghi `nested`.
4. `DeferredSelector` được thu gom; sau normal parsing, framework chuyển nó tới `DeferredGroup`.
5. `Group.process` ghi `deferred.process` rồi **chính Group** gọi `DeferredSelector.selectImports`, sinh `deferred.select`.
6. `Group.selectImports` ghi `deferred.group.result` rồi trả `Entry` chỉ tới `DeferredConfig`.
7. Parser tiếp tục đưa `DeferredConfig` vào tập configuration metadata, và bean `deferredMessage` được tạo theo lifecycle thông thường.
8. Mỗi selector callback trong fixture chạy đúng một lần, nên có năm events.

Các boolean quan sát **quan hệ thứ tự giữa các callbacks**. Ngược lại, `immediate-bean` và `deferred-bean` chứng minh cuối cùng hai imports đều tạo được beans trong cùng context. **Không** suy luận bean nào được instantiate trước từ thứ tự lựa chọn imports.

## 10. Ví dụ Group loại trùng imports

Khi có nhiều deferred selectors cùng Group, có thể muốn các config class names chỉ xuất hiện một lần trong danh sách Group trả lại:

```java
public final class UniqueImportsGroup
        implements DeferredImportSelector.Group {

    private final java.util.Map<String, Entry> selected =
            new java.util.LinkedHashMap<>();

    @Override
    public void process(
            AnnotationMetadata metadata,
            DeferredImportSelector selector) {

        for (String className : selector.selectImports(metadata)) {
            selected.putIfAbsent(
                    className,
                    new Entry(metadata, className)
            );
        }
    }

    @Override
    public Iterable<Entry> selectImports() {
        return selected.values();
    }
}
```

Đây là một class demo riêng, yêu cầu imports `DeferredImportSelector` và `AnnotationMetadata`. `LinkedHashMap` giữ entry đầu tiên theo tên class. Với những ứng dụng yêu cầu xét annotation metadata khác nhau của nhiều importers, giữ entry đầu tiên **có thể không đúng policy**: cần quyết định dựa vào hợp đồng nghiệp vụ.

### Một bẫy quan trọng

Group loại tên config trùng **không loại được** việc hai config *khác nhau* cùng định nghĩa `@Bean("httpClient")`. Xung đột bean name, hai candidate cùng type, bean definition overriding policy và injection ambiguity vẫn tồn tại ở pha registry/DI.

## 11. Liên hệ với @Conditional

Một số imports chỉ phù hợp khi cấu hình đáp ứng điều kiện. `DeferredImportSelector` hữu ích vì những configuration thông thường đã được parser xử lý trước, từ đó có thêm ngữ cảnh cho một số chiến lược chọn import.

Nhưng không nên đồng nhất “đã xử lý `@Configuration` metadata” với “mọi bean đã tồn tại trong BeanFactory”. Conditions và registration có các pha khác nhau. Một điều kiện đọc `Environment`/classpath có thể an toàn; một điều kiện phụ thuộc `getBean()` hoặc trạng thái BeanFactory chưa hoàn thiện dễ sai.

### Selector theo Environment

```java
import org.springframework.context.EnvironmentAware;
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotationMetadata;

public final class AuditFeatureSelector
        implements DeferredImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        boolean enabled = environment.getProperty(
                "feature.audit.enabled", Boolean.class, false);

        return enabled
                ? new String[] { AuditConfiguration.class.getName() }
                : new String[0];
    }
}
```

Đoạn này là snippet riêng, cần class `AuditConfiguration` trong ứng dụng. Spring cung cấp `Environment` qua `EnvironmentAware` trong quá trình chuẩn bị selector. Điều kiện đọc property không cần instantiate service nghiệp vụ.

Dù vậy, chỉ kiểm tra property **không bắt buộc** phải dùng deferred processing. Nếu không cần Group/timing, normal `ImportSelector` hoặc `@Conditional` trực tiếp trên cấu hình thường đơn giản hơn.

## 12. Vai trò của Spring Boot auto-configuration

Một trường hợp thực tế nổi tiếng là `AutoConfigurationImportSelector` của **Spring Boot**: nó implement `DeferredImportSelector` để phục vụ auto-configuration.

Tư duy của Boot là application configuration được xử lý trước, rồi Boot chọn các default/auto-configurations thích hợp theo classpath, property, điều kiện loại trừ và metadata ordering. Các cơ chế như `@ConditionalOnMissingBean` có thể giúp default bean lùi lại trước bean do ứng dụng khai báo trong điều kiện hợp lệ.

Cần ba phân biệt:

1. `AutoConfigurationImportSelector` thuộc **Spring Boot**, không nằm trong dependency `spring-context` thuần của demo.
2. `@ConditionalOnMissingBean` là annotation **Spring Boot**, không phải Spring Core `@Conditional`.
3. Boot có logic candidate discovery, ordering, filtering và condition evaluation riêng; bản thân `DeferredImportSelector` **không tự triển khai những policy ấy**.

**Không được suy ra** một custom deferred selector tự biết toàn bộ bean definitions đã đăng ký hoặc có khả năng “đợi tới cuối” rồi tránh mọi xung đột.

## 13. DeferredImportSelector khác các cơ chế thời gian khác

| Công cụ | Thời điểm hoặc trách nhiệm chính |
| --- | --- |
| `ImportSelector` | Chọn imports trong parsing thông thường |
| `DeferredImportSelector` | Chọn imports muộn hơn trong parsing cấu hình |
| `DeferredImportSelector.Group` | Tổng hợp/lọc/sắp imports của selectors |
| `ImportBeanDefinitionRegistrar` | Đăng ký BeanDefinitions bằng API |
| `BeanFactoryPostProcessor` | Điều chỉnh metadata/definitions trước tạo beans thường |
| `BeanPostProcessor` | Xử lý bean instances trong lifecycle |
| `@Lazy` | Trì hoãn khởi tạo bean singleton khi thích hợp |
| `ObjectProvider<T>` | Deferred dependency lookup lúc caller yêu cầu |
| `@DependsOn` | Ràng buộc khởi tạo phụ thuộc theo bean definition |
| `@Async` | Chạy lời gọi method theo async infrastructure |
| `ContextRefreshedEvent` | Sự kiện context đã refresh |
| Boot auto-configuration | Lựa chọn/đăng ký defaults theo Boot conditions |

**Deferred selector không phải scheduler, async executor hoặc lifecycle callback sau startup.**

## 14. Lỗi thường gặp và cách chẩn đoán

### Lỗi 1 — Tưởng bean của deferred import chỉ được tạo sau refresh

Deferred imports vẫn được xử lý trong quá trình configuration processing của refresh. Bean singleton eager có thể được tạo trước khi refresh hoàn tất.

### Lỗi 2 — Sử dụng getBean trong selector

`getBean()` có thể kích hoạt tạo object quá sớm trước khi infrastructure sẵn sàng, hoặc nhìn thấy trạng thái chưa đầy đủ. Ưu tiên metadata/Environment và đúng extension point.

### Lỗi 3 — Tưởng BeanFactory chứa đầy đủ definitions

Khi deferred selector được gọi, parser có thể đã phát hiện `@Bean` methods nhưng reader chưa hoàn tất đăng ký. `containsBeanDefinition(...)` lúc đó không thể mặc định đại diện cho registry cuối cùng.

### Lỗi 4 — selectImports trả bean name thay vì class name

`selectImports` trả fully qualified **class names**. Hãy sử dụng `TargetConfig.class.getName()`. Với nested class Java, cách này tránh lỗi binary name.

### Lỗi 5 — Group bỏ quên gọi selector.selectImports

Custom `Group.process` chịu trách nhiệm thu thập kết quả theo hợp đồng của nó. Nếu group không gọi selector và không tự tạo entries, imports có thể rỗng dù selector có logic trong `selectImports`.

### Lỗi 6 — Trả String[] từ Group.selectImports

Group phải trả `Iterable<Group.Entry>`, không phải `String[]`. Entry chứa metadata importer và tên class target.

### Lỗi 7 — Dùng @Order để ép bean instantiation order

`Ordered`/`@Order` của selector điều khiển precedence selection, không ràng buộc thứ tự constructor/factory method của các singleton. Dùng dependency injection hoặc lifecycle mechanism đúng ý định.

### Lỗi 8 — Không nạp root configuration

Nếu class có `@Import(MySelector.class)` không được register/import/scan vào context, selector sẽ không chạy. Kiểm tra composition root và annotations.

### Lỗi 9 — Tưởng Group dedup ngăn trùng bean types

Hai configuration classes khác nhau vẫn có thể tạo trùng bean names hoặc cùng return interface. Kiểm tra bean overriding, `@Primary` và `@Qualifier`.

### Lỗi 10 — Nhầm conditional Boot với conditional Core

`@ConditionalOnMissingBean` là Boot API. Project chỉ có Spring Framework dependency không có annotation đó. Các conditions phụ thuộc beans phải được đánh giá đúng phase.

### Lỗi 11 — Dùng DeferredImportSelector cho hot plugin loading

Deferred imports được quyết định khi context được dựng; không tự thêm plugin vào registry sau khi ứng dụng đã chạy.

### Lỗi 12 — Tạo selector có side effects nặng

Gọi network, DB, mở connection pool hoặc ghi dữ liệu trong `selectImports` làm startup chậm và khiến context khó test. Selector nên thuần metadata càng nhiều càng tốt.

### Lỗi 13 — Test bằng constructor order

Nếu muốn đo timing của selector, ghi event ngay trong `selectImports` hoặc Group. Constructors/`@PostConstruct` chạy pha khác và phụ thuộc bean graph.

### Lỗi 14 — Tin rằng deferred chỉ có đúng một vòng xử lý

Imported configurations có thể có imports lồng nhau và dẫn đến candidates mới. Xem deferred như một pha của parser có khả năng xử lý thêm metadata, không như một danh sách bất biến chạy một lần trong mọi trường hợp.

## 15. Phương pháp kiểm thử hiệu quả

Test nên tách thành hai lớp:

**Kiểm thử selection phase:** tạo context chỉ gồm configuration và selectors cần nghiên cứu, ghi events tại callback, assert normal selector xử lý trước deferred group khi fixture áp dụng. Nếu nhiều Group hoặc `Ordered`, kiểm tra đúng quan hệ thứ tự mà policy yêu cầu.

**Kiểm thử kết quả registration:** sau `refresh()`, dùng `containsBean`, `getBean` hoặc `getBeanNamesForType` để xác nhận bean được chọn. Nếu class được selector chọn nhưng `@Conditional` loại bỏ, kiểm tra điều kiện thay vì kết luận selector không chạy.

Một snippet lấy bean từ demo:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
                 DeferredDemo.RootConfig.class)) {

    System.out.println(
            context.containsBean("deferredMessage"));
}
```

Đoạn này có thể biên dịch khi dùng package demo và import `AnnotationConfigApplicationContext` của ví dụ, kết quả `true`. Nhưng nó **chỉ** kiểm tra bean tồn tại sau refresh; recorder events mới là bằng chứng về timing.

### Thử nghiệm biến thể hữu ích

- Đổi `DeferredSelector` thành normal `ImportSelector`: group callback sẽ không còn được gọi.
- Giữ deferred selector nhưng bỏ override `getImportGroup()`: Spring vẫn xử lý deferred, chỉ không dùng custom group.
- Tạo hai deferred selectors cùng trả một Group class: kiểm tra `Group.process` nhận đủ metadata của các importers.
- Dùng `Ordered` với precedence khác nhau: ghi order của callback trong một test riêng, không suy ra thứ tự tạo beans.
- Thêm `@Lazy` cho bean trong deferred config: timing tạo bean thay đổi, nhưng **selector vẫn chạy trong parsing**.
- Thêm một `@Conditional` dựa trên Environment trên imported configuration: theo dõi vừa callback vừa kết quả đăng ký bean.

## 16. Câu hỏi tự luyện

**Câu 1.** Sự khác biệt quan trọng nhất giữa `ImportSelector` và `DeferredImportSelector` là gì?

**Đáp:** Thời điểm parser chọn imports: deferred selector được thu gom và xử lý sau normal configuration parsing của lượt tương ứng.

**Câu 2.** Deferred import có bảo đảm bean được instantiate sau khi context hoàn tất startup không?

**Đáp:** Không. Eager singleton có thể được instantiate trong cùng `refresh()`.

**Câu 3.** `selectImports` nhận annotation metadata của class nào?

**Đáp:** Configuration class đã thực hiện import selector.

**Câu 4.** Một selector trả `"paymentClient"` thay vì tên configuration class đầy đủ có đúng không?

**Đáp:** Không. `selectImports` phải trả class names hợp lệ.

**Câu 5.** Nếu một Group không gọi `selector.selectImports(...)`, Spring có tự động gọi hộ trước khi Group.process không?

**Đáp:** Không nên giả định. Group là nơi điều phối cách xử lý; nó phải tạo các `Entry` cuối cùng theo logic đã thiết kế.

**Câu 6.** `Group.Entry` dùng để làm gì?

**Đáp:** Giữ annotation metadata của importer cùng class name được chọn, để parser xử lý đúng ngữ cảnh.

**Câu 7.** `@Order` trên deferred selector có buộc bean của selector đó được khởi tạo trước không?

**Đáp:** Không. Order thuộc pha selection, không bảo đảm constructor ordering.

**Câu 8.** Vì sao Spring Boot dùng `AutoConfigurationImportSelector`?

**Đáp:** Để chọn tập auto-configurations trong pha deferred, kết hợp với cơ chế filtering/ordering/conditional của Boot.

**Câu 9.** Làm thế nào để kiểm chứng selector thật sự chạy muộn?

**Đáp:** Ghi lại events trong normal selector và deferred selector/Group, rồi so sánh vị trí các callbacks trong integration test.

**Câu 10.** Muốn trì hoãn một client kết nối đến khi thật sự dùng, nên làm gì?

**Đáp:** Dùng `@Lazy` hoặc cơ chế lookup phù hợp, thiết kế lifecycle và connection policy của client; không dùng DeferredImportSelector thay thế.

## 17. Tài liệu chính thức

- [Spring Framework DeferredImportSelector API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html): hợp đồng chạy deferred, thứ tự và Group.
- [Spring Framework DeferredImportSelector.Group API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.Group.html): `process`, `selectImports`, `Entry`.
- [Spring Framework ImportSelector API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportSelector.html): return type của selector, metadata và exclusion filter.
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): cơ chế `@Import` khi ghép cấu hình.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): phân biệt metadata post-processing và bean instance post-processing.
- [Spring Boot AutoConfigurationImportSelector API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): ứng dụng của deferred selection trong Boot.

**Kết luận:** `DeferredImportSelector` trì hoãn **import selection trong pha phân tích cấu hình**, không trì hoãn **bean initialization** tới runtime. `DeferredImportSelector.Group` cho phép phối hợp nhiều kết quả import theo policy chung. Hãy đo thời điểm bằng **parser/selector callbacks**, và luôn tách timing của metadata processing khỏi timing tạo bean instances.
