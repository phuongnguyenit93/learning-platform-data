# Annotation tổng hợp, siêu dữ liệu annotation và khai báo theo tên lớp trong Spring Boot Auto-configuration

Khi viết hoặc đọc cơ chế **auto-configuration** của Spring Boot, ba ý tưởng này thường xuất hiện cùng nhau:

1. **Annotation tổng hợp (composed annotation)**: một annotation dùng các annotation khác làm *meta-annotation*, tạo ra một nhãn mới có ý nghĩa thuận tiện và nhất quán.
2. **Siêu dữ liệu annotation (annotation metadata)**: thông tin về annotation, thuộc tính, lớp và phương thức mà Spring đọc để tìm cấu hình hoặc đánh giá điều kiện. Spring có thể đọc siêu dữ liệu từ bytecode mà không cần khởi tạo bean hay tải tất cả class liên quan.
3. **Khai báo theo tên lớp (class-name declarations)**: dùng tên đầy đủ của class dưới dạng chuỗi `String` trong các vị trí phù hợp, đặc biệt khi class hoặc dependency là *optional* và có thể không nằm trên runtime classpath.

Đây là những **cơ chế hỗ trợ việc phát hiện và lựa chọn cấu hình**, không phải ba cách khác nhau để trực tiếp tạo một đối tượng. Spring Boot dùng chúng để tìm những auto-configuration candidate, xử lý các annotation/điều kiện và chỉ đăng ký bean khi điều kiện phù hợp.

## 1. Annotation trực tiếp, meta-annotation và composed annotation

Một annotation Java có thể được gắn trực tiếp lên class:

```java
@Component
public class InventoryService {
}
```

`@Component` là annotation **trực tiếp** trên `InventoryService`. Nhưng `@Service` của Spring có thể được định nghĩa theo mô hình:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface Service {
    // Lược bỏ thuộc tính để tập trung vào quan hệ meta-annotation.
}
```

Ở đây, `@Component` được gắn **lên định nghĩa annotation `@Service`**; nó là *meta-annotation*. Do Spring hiểu chuỗi annotation này, `@Service` là một stereotype hợp lệ để component scanning phát hiện.

Một **composed annotation** thường kết hợp một hoặc nhiều meta-annotation nhằm tạo API ngắn gọn, có nghĩa trong miền ứng dụng. Ví dụ, `@RestController` kết hợp hành vi của `@Controller` và `@ResponseBody`; `@SpringBootApplication` tổng hợp `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`; `@AutoConfiguration` mang ý nghĩa cấu hình Spring và khai báo đặc thù cho cơ chế auto-configuration.

Đừng nhầm ba lớp khái niệm:

| Thuật ngữ | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Annotation trực tiếp | Class/method được gắn annotation gì? | `@Service` trên `OrderService` |
| Meta-annotation | Annotation đang dùng được xây dựng từ annotation nào? | `@Component` trên định nghĩa `@Service` |
| Composed annotation | Có API annotation mới kết hợp/hạn chế/tùy biến những ý nghĩa nào? | `@SpringBootApplication`, annotation tùy chỉnh `@FeatureComponent` |

**Cảnh báo Java thuần:** việc một annotation A được meta-annotate bằng B không có nghĩa mọi API reflection Java sẽ trả B như annotation trực tiếp trên lớp sử dụng A. `Class.getAnnotation(B.class)` và thuật toán tìm annotation/meta-annotation của Spring là hai hành vi khác nhau. Spring cung cấp mô hình *merged annotations* để truy vấn hệ phân cấp này.

### 1.1. Những meta-annotation Java tạo nên hợp đồng của annotation

Khi tự định nghĩa annotation, cần hiểu ít nhất:

- `@Target`: nơi hợp lệ để đặt annotation, chẳng hạn `ElementType.TYPE` cho class/interface/annotation type hoặc `ElementType.METHOD` cho method.
- `@Retention(RetentionPolicy.RUNTIME)`: cho phép API reflection đọc annotation lúc chạy. Các annotation cấu hình Spring thường khai báo retention phù hợp.
- `@Documented`: đưa annotation vào Javadoc của phần tử được chú thích.
- `@Inherited`: nếu có, Java hỗ trợ kế thừa annotation trên **class** trong một số thao tác reflection; nó không tự mở rộng tương tự đến interface hoặc method override. Spring còn có chiến lược tìm annotation riêng, nên không thể dùng `@Inherited` làm phép thay thế cho mọi cơ chế hợp nhất.

Một annotation tổng hợp cần **định nghĩa mục đích rõ ràng**. Không nên đặt hàng loạt annotation vào một nhãn tùy chỉnh chỉ để giảm số dòng; điều đó làm hành vi thành phần trở nên khó thấy khi đọc code.

## 2. Thuộc tính annotation và `@AliasFor`

Trong composed annotation, vấn đề không chỉ là “gắn một annotation lên annotation khác”; còn có vấn đề **chuyển giá trị thuộc tính**. Nếu muốn annotation tùy chỉnh cho phép người dùng đặt bean name giống `@Component("name")`, hãy khai báo alias rõ ràng.

Ví dụ định nghĩa dưới đây là Java hoàn chỉnh trong file `FeatureComponent.java`:

```java
package com.example.app;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface FeatureComponent {

    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

Ứng dụng sử dụng:

```java
@FeatureComponent("timeReporter")
public class TimeReporter {
    // ...
}
```

**Điều đang xảy ra:**

1. Annotation `@FeatureComponent` trực tiếp trên `TimeReporter`.
2. `@Component` nằm ở cấp meta-annotation và cho phép Spring nhận class này là component.
3. `@AliasFor(annotation = Component.class, attribute = "value")` biểu thị thuộc tính `FeatureComponent.value` là alias cho thuộc tính `Component.value` trong mô hình merged annotations.
4. Khi class thuộc phạm vi component scanning, Spring có thể dùng giá trị `"timeReporter"` làm tên bean.

`@AliasFor` cũng có thể biểu đạt alias **giữa hai thuộc tính trong cùng annotation** hoặc **alias tường minh tới meta-annotation khác**, nhưng các alias phải tuân thủ hợp đồng về kiểu, mặc định và quan hệ tương đương. Không thể đổi tên một thuộc tính tùy ý rồi mặc định Spring sẽ suy ra nó là alias. Đặc biệt với Spring Framework 6.1+, custom stereotype nên khai báo alias tường minh cho thuộc tính đặt tên bean.

Phân biệt:

- `@AliasFor` liên quan **cách Spring diễn giải và hợp nhất thuộc tính annotation**.
- Dependency injection liên quan **đưa bean vào constructor/phương thức/field**.
- Property binding từ `application.properties` liên quan **gán dữ liệu cấu hình**, không phải alias cho thuộc tính của Java annotation.

## 3. Annotation metadata: đọc cấu hình từ metadata thay vì tạo bean

Trong Spring Framework, `AnnotationMetadata` đại diện thông tin annotation của một class; `MethodMetadata` biểu diễn thông tin về method. API `MergedAnnotations` cho phép quan sát annotation trực tiếp, annotation ở tầng meta và những giá trị thuộc tính đã hợp nhất, có xét `@AliasFor`.

Một số câu hỏi thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `metadata.getClassName()` | Tên đầy đủ của class đang mô tả |
| `metadata.getAnnotationTypes()` | Các loại annotation trực tiếp trên class |
| `metadata.hasAnnotation(fqcn)` | Class có annotation đó **trực tiếp** không? |
| `metadata.hasMetaAnnotation(fqcn)` | Class có annotation mà trong hệ meta-annotation của nó có loại này không? |
| `metadata.isAnnotated(fqcn)` | Có annotation **trực tiếp hoặc meta** theo tên hay không? |
| `metadata.getAnnotations()` | Truy cập mô hình `MergedAnnotations`, gồm việc kiểm tra annotation meta và thuộc tính đã merge |

`fqcn` là *fully qualified class name*, ví dụ `org.springframework.boot.autoconfigure.condition.ConditionalOnClass`.

Có hai cách tiếp cận khác nhau, cần phân biệt **ngay cả khi cả hai cùng trả về metadata**:

- `AnnotationMetadata.introspect(SomeClass.class)`: bắt đầu từ một `Class` đã được load rồi sử dụng reflection. Thích hợp cho code minh họa/kiểm thử hoặc khi đã có class.
- `MetadataReaderFactory`/`MetadataReader`: đọc metadata **từ class resource/bytecode** bằng ASM, thường tránh phải load class đang được quét. Cơ chế này đặc biệt quan trọng khi xem xét classpath có dependency tùy chọn.

Do đó câu “Spring đọc annotation metadata mà không load class” phải hiểu chính xác: **nhiều đường quét/phân tích metadata có thể làm vậy**, không phải mọi cách lấy `AnnotationMetadata` đều có tính chất này. Khi dùng `introspect(SomeClass.class)`, bạn đã truyền một `Class` vào.

### 3.1. Minh họa trực tiếp với metadata

Giả sử `ClockAutoConfiguration` được annotate như ví dụ đầy đủ ở phần 5:

```java
AnnotationMetadata metadata =
        AnnotationMetadata.introspect(ClockAutoConfiguration.class);

boolean direct = metadata.hasAnnotation(ClockAvailable.class.getName());
boolean meta = metadata.hasMetaAnnotation(ConditionalOnClass.class.getName());
boolean annotated = metadata.isAnnotated(ConditionalOnClass.class.getName());
```

Đây là **đoạn mã bên trong ứng dụng Spring ở phần 5**, không phải file chạy độc lập. Kết quả dự kiến:

- `direct == true` vì `@ClockAvailable` đặt trực tiếp trên class.
- `meta == true` vì `@ClockAvailable` mang meta-annotation `@ConditionalOnClass`.
- `annotated == true` vì `isAnnotated` tìm cả trực tiếp lẫn meta-annotation.

Kết quả này là về **metadata đã khai báo**, không chứng minh điều kiện `@ConditionalOnClass` đã match trong ứng dụng đang chạy. Muốn biết điều kiện match, phải kiểm tra classpath và condition evaluation; muốn biết có bean, phải kiểm tra context.

## 4. Khai báo theo tên lớp: vì sao `String` hữu ích với optional dependencies?

Giả sử thư viện tùy chọn `com.vendor.sdk.ExternalClient` có thể không được cài. Nếu trực tiếp `import com.vendor.sdk.ExternalClient;` và viết code phụ thuộc vào type đó, chương trình **không thể biên dịch** nếu thiếu dependency ở compile time. Nếu mã đã được biên dịch nhưng lúc chạy class biến mất, một số kiểu truy cập chữ ký class/method có thể phát sinh lỗi liên kết.

Ngược lại, một điều kiện **chỉ cần kiểm tra có hay không** có thể sử dụng tên class:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
public class OptionalClientAutoConfiguration {
    // Các bean chỉ liên quan khi ExternalClient tồn tại.
}
```

`@ConditionalOnClass(name = "...")` không cần source code import `ExternalClient`. Spring Boot dùng metadata và classpath để đánh giá điều kiện. Nếu class đó vắng mặt, auto-configuration này **không match**; đơn giản viết tên class không làm class được tải, tải xuống, hay tạo bean.

Đối chiếu ba cách dùng:

| Khai báo | Dùng khi nào | Cần lưu ý |
| --- | --- | --- |
| `@ConditionalOnClass(value = ExternalClient.class)` | Annotation điều kiện gắn **trực tiếp lên class cấu hình**; Boot có thể đọc metadata bằng ASM và kiểm tra class vắng mặt | Kiểu ở source vẫn cần tồn tại trên **compile classpath** |
| `@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")` | Không muốn reference type trực tiếp hoặc làm việc với optional class name | Phải đúng tên class; sai chính tả có thể khiến điều kiện không match |
| Composed `@MyConditionalFeature`, bên trong có `@ConditionalOnClass(name = "...")` | Khi điều kiện class được đặt như **meta-annotation** của annotation tự tạo | **Bắt buộc dùng `name`** cho class condition trong composed annotation, theo hướng dẫn Spring Boot; tránh `value = OptionalClass.class` ở đây |

Lưu ý quan trọng của Spring Boot: **cơ chế an toàn với `Class<?>` literal trong `@ConditionalOnClass` gắn trực tiếp trên cấu hình không được bảo đảm giống như khi annotation này được lồng vào một composed annotation**. Trong meta-annotation tùy chỉnh, luôn chọn thuộc tính `name` để kiểm tra optional class.

### 4.1. Class name còn được dùng ở những nơi nào?

- File `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` chứa các dòng tên class auto-configuration đầy đủ. Đây là **khai báo candidate để Boot tìm**, không phải Java annotation.
- `@AutoConfiguration(afterName = "com.vendor.sdk.SdkAutoConfiguration")` khai báo sắp xếp theo tên, hữu ích khi không muốn trực tiếp liên kết một class tùy chọn. `beforeName` tương tự.
- `@SpringBootApplication(excludeName = "com.vendor.sdk.SdkAutoConfiguration")` và `spring.autoconfigure.exclude` là những cơ chế loại trừ **auto-configuration** theo tên.
- `@ConditionalOnMissingClass("com.vendor.sdk.ExternalClient")` là điều kiện đảo chiều, dùng tên class để xét **vắng mặt**.

Tùy API, tên có thể là chuỗi đơn hoặc mảng; **đừng suy rằng một thuộc tính `name` ở annotation này có cùng ý nghĩa với `name` ở annotation khác**. Ví dụ `@ConditionalOnBean(name = "beanName")` kiểm tra *tên bean*, còn `@ConditionalOnClass(name = "...")` kiểm tra *tên Java class*.

Một class nằm trong package không đồng nghĩa class đang có trên runtime classpath; một tên class có trong `.imports` cũng không bảo đảm tất cả điều kiện auto-config sẽ match.

## 5. Ví dụ hoàn chỉnh có thể chạy: composed annotation, metadata và class names

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.13**, Maven. Nó chứng minh cả ba ý tưởng:

- `@FeatureComponent` là composed stereotype và đặt tên bean thông qua `@AliasFor`.
- `@ClockAvailable` chứa `@ConditionalOnClass(name = "java.time.Clock")` dưới dạng meta-annotation.
- `ClockAutoConfiguration` được Boot tìm qua **tên class** trong file `AutoConfiguration.imports`, dù nó nằm **ngoài package quét** của ứng dụng.
- `OptionalClientAutoConfiguration` cũng được liệt kê nhưng bị loại do optional SDK không tồn tại; không import type không có thật.
- `AnnotationMetadata` kiểm tra trực tiếp và meta-annotation; `ApplicationContext` cho biết bean nào thực sự tồn tại.

**Cấu trúc dự án** (tên tệp và package phải khớp):

```text
annotation-metadata-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── com/example/
    │       ├── app/
    │       │   ├── DemoApplication.java
    │       │   ├── FeatureComponent.java
    │       │   └── TimeReporter.java
    │       └── library/autoconfigure/
    │           ├── ClockAvailable.java
    │           ├── ClockAutoConfiguration.java
    │           └── OptionalClientAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**`pom.xml`** (starter cơ bản, không cần web server):

```xml
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
    <artifactId>annotation-metadata-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**`src/main/java/com/example/app/FeatureComponent.java`**

```java
package com.example.app;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface FeatureComponent {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

**`src/main/java/com/example/app/TimeReporter.java`**

```java
package com.example.app;

import java.time.Clock;

@FeatureComponent("timeReporter")
public final class TimeReporter {
    private final Clock clock;

    public TimeReporter(Clock clock) {
        this.clock = clock;
    }

    public String zoneId() {
        return clock.getZone().getId();
    }
}
```

`TimeReporter` không hề gắn `@Component` trực tiếp; Spring nhận ra annotation tổng hợp. `Clock` được yêu cầu qua constructor injection, và phải có một bean phù hợp thì ứng dụng mới khởi động thành công.

**`src/main/java/com/example/library/autoconfigure/ClockAvailable.java`**

```java
package com.example.library.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "java.time.Clock")
public @interface ClockAvailable {
}
```

Đây là composed condition. `java.time.Clock` là class Java chuẩn nên hiện diện trên Java 17. Dù ví dụ dùng class luôn có sẵn để dễ chạy, quy tắc **`name` thay vì `value` bên trong meta-annotation** trở nên rất quan trọng khi kiểm tra class của thư viện tùy chọn.

**`src/main/java/com/example/library/autoconfigure/ClockAutoConfiguration.java`**

```java
package com.example.library.autoconfigure;

import java.time.Clock;
import java.time.ZoneId;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ClockAvailable
@ConditionalOnProperty(
        prefix = "demo.clock",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock demoClock() {
        return Clock.system(ZoneId.of("UTC"));
    }
}
```

`@AutoConfiguration` biểu thị class cấu hình do Boot có thể áp dụng. `@ClockAvailable` giúp điều kiện class; `@ConditionalOnProperty` quyết định bật/tắt theo cấu hình; `@ConditionalOnMissingBean(Clock.class)` cho bean mặc định nhường khi đã có `Clock` phù hợp. Bean `Clock` là bean **được định nghĩa bởi auto-configuration**, còn việc truyền nó vào `TimeReporter` là DI.

**`src/main/java/com/example/library/autoconfigure/OptionalClientAutoConfiguration.java`**

```java
package com.example.library.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
public class OptionalClientAutoConfiguration {

    @Bean
    String optionalSdkMarker() {
        return "SDK_PRESENT";
    }
}
```

Không cần tồn tại class `com.vendor.sdk.ExternalClient` khi biên dịch mẫu này vì toàn bộ tham chiếu chỉ là chuỗi trong `name`. Trong dự án không có SDK đó, điều kiện không match và bean `optionalSdkMarker` không được đăng ký. `String` được sử dụng ở đây chỉ để **quan sát điều kiện**, không phải API tích hợp SDK thực tế.

**`src/main/java/com/example/app/DemoApplication.java`**

```java
package com.example.app;

import com.example.library.autoconfigure.ClockAutoConfiguration;
import com.example.library.autoconfigure.ClockAvailable;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.type.AnnotationMetadata;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printEvidence(
            ApplicationContext context, TimeReporter reporter) {
        return args -> {
            AnnotationMetadata metadata =
                    AnnotationMetadata.introspect(ClockAutoConfiguration.class);

            System.out.println("DIRECT_CLOCK_AVAILABLE="
                    + metadata.hasAnnotation(ClockAvailable.class.getName()));
            System.out.println("META_CONDITIONAL_ON_CLASS="
                    + metadata.hasMetaAnnotation(ConditionalOnClass.class.getName()));
            System.out.println("CLOCK_BEAN=" + context.containsBean("demoClock"));
            System.out.println("OPTIONAL_BEAN="
                    + context.containsBean("optionalSdkMarker"));
            System.out.println("REPORTER_BEAN="
                    + context.containsBean("timeReporter"));
            System.out.println("REPORTER_ZONE=" + reporter.zoneId());
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.clock.enabled=true
```

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
com.example.library.autoconfigure.ClockAutoConfiguration
com.example.library.autoconfigure.OptionalClientAutoConfiguration
```

Đây là tệp tài nguyên **tên cố định**, không phải annotation và không có đuôi `.java`. Mỗi dòng là tên class đầy đủ của một auto-configuration candidate. Spring Boot sẽ kiểm tra file này trên classpath của các JAR và của ứng dụng; riêng việc có tên trong file **không** làm điều kiện của class luôn match.

Để thấy rõ hai cơ chế, ứng dụng `DemoApplication` nằm trong `com.example.app`, còn auto-config nằm trong `com.example.library.autoconfigure` — nằm ngoài phạm vi component scanning mặc định. `ClockAutoConfiguration` vẫn được tìm qua imports file.

**Chạy:** cài Java 17+ và Maven, sau đó đứng tại thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Với đúng mã và properties ở trên, những dòng do `ApplicationRunner` in (không tính thông báo từ môi trường/Maven) là:

```text
DIRECT_CLOCK_AVAILABLE=true
META_CONDITIONAL_ON_CLASS=true
CLOCK_BEAN=true
OPTIONAL_BEAN=false
REPORTER_BEAN=true
REPORTER_ZONE=UTC
```

**Giải thích từng dòng:**

1. `DIRECT_CLOCK_AVAILABLE=true`: `ClockAutoConfiguration` được gắn trực tiếp `@ClockAvailable`.
2. `META_CONDITIONAL_ON_CLASS=true`: Spring tìm được `@ConditionalOnClass` nằm trên định nghĩa annotation `@ClockAvailable`.
3. `CLOCK_BEAN=true`: Boot đã import auto-config, class `Clock` tồn tại, property bật và chưa có bean `Clock` khác; phương thức `demoClock` được đăng ký.
4. `OPTIONAL_BEAN=false`: auto-config thứ hai là candidate nhưng bị loại theo `@ConditionalOnClass(name=...)` vì tên class SDK không tồn tại.
5. `REPORTER_BEAN=true`: component scanning tìm thấy `TimeReporter` qua composed stereotype; alias chỉ định bean name `timeReporter`.
6. `REPORTER_ZONE=UTC`: DI đã tiêm `Clock` được auto-config vào `TimeReporter`; bean cung cấp zone `UTC`.

**Thử thay đổi có chủ đích:** nếu đổi `demo.clock.enabled=false`, `ClockAutoConfiguration` không match, nên ví dụ hiện tại **không khởi động được** vì `TimeReporter` vẫn cần một bean `Clock`. Đây là minh họa rằng điều kiện cấu hình ảnh hưởng đăng ký bean, còn DI không thể tự tạo bean bị thiếu. Nếu muốn chạy được khi tắt auto-config, cần cung cấp bean `Clock` thủ công (ví dụ qua một phương thức `@Bean` của ứng dụng).

## 6. Khi nào metadata theo bytecode đặc biệt hữu ích?

Tưởng tượng JAR auto-config có một class tùy chọn. Nếu Spring luôn phải load và link mọi class trước khi xem điều kiện, việc thiếu thư viện tùy chọn sẽ dễ gây `ClassNotFoundException` hoặc `NoClassDefFoundError` ở giai đoạn phát hiện cấu hình.

Đọc class resource bằng ASM giúp Spring quan sát annotation/class name **mà chưa cần khởi tạo bean và trong nhiều trường hợp chưa cần load class được mô tả**. Nhờ đó những điều kiện về classpath có thể được lọc sớm.

Tuy nhiên, không được diễn giải thành “metadata loại bỏ mọi vấn đề class loading”. Một số tình huống vẫn nguy hiểm:

**Tình huống A — annotation trên `@Bean` method nhưng return type là class tùy chọn:**

```java
// Mã MINH HỌA, giả định ExternalClient đến từ dependency tùy chọn.
@Bean
@ConditionalOnClass(ExternalClient.class)
ExternalClient externalClient() {
    return new ExternalClient();
}
```

Điều kiện có thể chưa kịp được xét trước khi JVM hoặc Spring cần xử lý chữ ký phương thức `externalClient()`. Spring Boot hướng dẫn **tách điều kiện vào một `@Configuration` class lồng riêng** để bảo vệ phần method dùng class tùy chọn:

```java
// Mã MINH HỌA; chỉ biên dịch nếu ExternalClient có trên compile classpath.
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
static class ExternalClientConfiguration {

    @Bean
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

Class có method phụ thuộc optional type được cô lập phía sau điều kiện class. Mẫu này thường được đặt bên trong một auto-configuration cha. Nếu không có SDK trong compile classpath, ví dụ minh họa có type `ExternalClient` sẽ không biên dịch; khi đó cần đặt integration ở module có compile dependency thích hợp.

**Tình huống B — annotation tổng hợp dùng class literal cho class tùy chọn:**

```java
// Không chọn cách này cho điều kiện optional class trong meta-annotation.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(value = ExternalClient.class)
public @interface ConditionalOnExternalClient {
}
```

Cơ chế đọc annotation qua meta-annotation có thể đòi hỏi xử lý tham chiếu class trước khi áp dụng bảo vệ ASM như với annotation điều kiện trực tiếp. Cách nên dùng là:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
public @interface ConditionalOnExternalClient {
}
```

Hai đoạn trên là **minh họa cơ chế**, không phải hai file Java đầy đủ (chưa gồm imports hoặc khai báo dependency).

**Tình huống C — dùng tên class trong danh sách imports nhưng class thực sự không tồn tại:** Spring Boot cần import được **class cấu hình candidate thực sự**; file imports không phải cơ chế “bỏ qua tên sai” cho auto-config của chính thư viện. `name` trong annotation điều kiện là tên *class được kiểm tra*; tên trong `AutoConfiguration.imports` là tên *class cấu hình sẽ được nạp nếu phù hợp*. Hai ý nghĩa khác nhau.

## 7. Các loại metadata của Spring Boot không nên nhầm

| Tài nguyên/API | Vai trò | Khi nào cần? |
| --- | --- | --- |
| `AnnotationMetadata`, `MergedAnnotations` | Mô hình đọc annotation trực tiếp, meta, thuộc tính merge; có thể dùng trong framework/test | Khi đọc/kiểm tra annotation trên class và method |
| `MetadataReader`, ASM | Đọc class metadata từ bytecode mà không nhất thiết load class | Component scanning, parse và filter cấu hình |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Liệt kê tên class auto-configuration candidate của JAR | **Bắt buộc** để Boot khám phá custom auto-config theo cơ chế chuẩn Boot 3.x |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata tối ưu do annotation processor tạo giúp lọc sớm một số auto-config không thỏa điều kiện | Tối ưu khả năng khởi động khi đóng gói thư viện auto-config; không thay thế imports |
| `META-INF/spring-configuration-metadata.json` | Metadata về **configuration properties**, hỗ trợ gợi ý IDE/tài liệu | Khi xuất bản nhóm property như `acme.timeout`; không phải danh sách auto-config |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` | Ánh xạ tên auto-config cũ sang tên mới cho cơ chế ordering/exclusion khi đổi tên lớp | Khi chuyển package/đổi tên auto-config công khai trong thư viện |

Trong Spring Boot 3.x, đừng dùng chỉ mỗi khóa `EnableAutoConfiguration` trong `META-INF/spring.factories` theo những tutorial cũ để đăng ký custom auto-config. Định dạng chuẩn cho candidate là `AutoConfiguration.imports`. Tài nguyên metadata tối ưu và file properties metadata phục vụ **hai mục đích khác nhau**.

## 8. Mẹo chẩn đoán và những lỗi hay gặp

**1. Composed annotation không tạo bean như mong đợi:** kiểm tra `@Target`/`@Retention`, meta-annotation `@Component`, package scan, alias và bean name. Một annotation “đẹp” nhưng không mang `@Component` hoặc không được cơ chế import nào xử lý sẽ không tự đăng ký bean.

**2. Alias tên bean không hoạt động:** xem `@AliasFor(annotation = Component.class, attribute = "value")` có khai báo đúng thuộc tính, kiểu trả về và giá trị mặc định tương thích không; tránh trùng alias với giá trị mâu thuẫn.

**3. `metadata.hasAnnotation(...)` trả `false`:** có thể annotation đang ở **cấp meta**, hãy dùng `hasMetaAnnotation` hoặc `isAnnotated`/`MergedAnnotations` cho đúng câu hỏi. Đừng nhầm “annotation không trực tiếp hiện diện” với “Spring không nhận ra annotation”.

**4. `@ConditionalOnClass` đúng nhưng gặp lỗi thiếu class:** kiểm tra tham chiếu kiểu trong method return type, constructor, annotation tổng hợp hoặc code được load quá sớm. Với composed annotation kiểm tra dùng `name`; với bean method phụ thuộc optional type, tách vào `@Configuration` class được bảo vệ.

**5. Auto-config không được phát hiện:** kiểm tra chính tả và đường dẫn `AutoConfiguration.imports`, mỗi dòng một FQCN, nội dung được đóng gói vào JAR. Không trông đợi component scanning tự tìm class auto-config; không khai báo auto-config làm component ứng dụng.

**6. Auto-config có trong imports nhưng bean vẫn không có:** đây có thể là kết quả hợp lệ của điều kiện `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` hoặc điều kiện khác. Dùng `--debug` để xem *Condition Evaluation Report*, chẳng hạn chạy:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
```

Nếu thử lệnh này, hãy điều chỉnh `logging.level.root=OFF` của demo để log debug có thể hiển thị. Khi dùng Actuator, endpoint `/actuator/conditions` cũng hỗ trợ kiểm tra điều kiện nếu dependency/exposure được cấu hình phù hợp; không mặc định public.

**7. Sắp xếp auto-config bằng tên class:** với `@AutoConfiguration(afterName=...)`, thứ tự liên quan **định nghĩa bean**, không phải cam kết thứ tự khởi tạo mọi bean. Quá trình tạo bean vẫn chịu chi phối bởi dependency và các quan hệ như `@DependsOn`.

**8. Tên class đổi package:** các string reference trong `AutoConfiguration.imports`, `beforeName`/`afterName` và exclusion phải cập nhật chính xác; khi đổi tên auto-config đã phát hành, xem khả năng dùng `AutoConfiguration.replacements` để giữ tương thích.

## 9. Câu hỏi tự kiểm tra

1. Một class có `@FeatureComponent` nhưng không có `@Component` trực tiếp có thể được scan không? **Có**, nếu annotation tùy chỉnh được meta-annotate với `@Component` hợp lệ và class thuộc phạm vi scan.
2. `metadata.hasAnnotation(ConditionalOnClass.class.getName())` khác `metadata.hasMetaAnnotation(...)` thế nào? Hàm đầu hỏi annotation **trực tiếp**; hàm sau hỏi **meta-annotation**.
3. Vì sao composed annotation kiểm tra optional class nên dùng `@ConditionalOnClass(name="...")`? Vì Spring Boot không bảo đảm xử lý class literal qua meta-annotation an toàn như annotation điều kiện gắn trực tiếp trên cấu hình.
4. `AutoConfiguration.imports` và `ConditionalOnClass.name` cùng chứa tên class; chúng có cùng nhiệm vụ không? **Không**. Imports liệt kê **auto-config candidate**; điều kiện kiểm tra **sự hiện diện của dependency/class**.
5. Một auto-config được tìm thấy nhưng không tạo bean: có chắc bị lỗi không? **Không**. Cần kiểm tra những `@Conditional...` và bean người dùng có khiến cấu hình không match hoặc nhường chỗ.
6. API nào giúp đọc metadata trước khi load class? `MetadataReader` dùng classfile/ASM là một lựa chọn; `AnnotationMetadata.introspect(SomeClass.class)` không thuộc nhóm này vì đã có đối tượng `Class`.

## 10. Tài liệu tham khảo

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports file, class conditions, optional dependencies, ordering và metadata processor.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): meta-annotations, composed stereotypes và alias cho tên bean.
- [Spring Framework — AnnotationMetadata API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotationMetadata.html): phân biệt annotation trực tiếp và meta-annotation.
- [Spring Framework — MergedAnnotations API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/annotation/MergedAnnotations.html): cách Spring hợp nhất annotation/meta-annotation và `@AliasFor`.

**Tư duy áp dụng:** Khi gặp một annotation trong auto-configuration, hãy hỏi: annotation được khai báo **trực tiếp hay qua meta**? Spring đang đọc nó **bằng reflection hay metadata bytecode**? Thuộc tính là **Java class literal**, **tên class dạng chuỗi** hay **tên bean**? Class trong `AutoConfiguration.imports` là **candidate** hay điều kiện đã match? Phân biệt đúng bốn tầng đó giúp tránh phần lớn lỗi thiếu optional dependency và lỗi auto-config không kích hoạt.
