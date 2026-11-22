# AnnotatedTypeMetadata và dữ liệu annotation khi đánh giá điều kiện

## 1. Tại sao Spring cần đọc metadata thay vì chỉ tạo đối tượng?

Một ứng dụng Spring Boot có thể khai báo cấu hình và bean theo điều kiện:

```java
@Configuration
@Conditional(SomeCondition.class)
class OptionalConfiguration {

    @Bean
    @Conditional(AnotherCondition.class)
    OptionalService optionalService() {
        return new OptionalService();
    }
}
```

Đoạn trên **chỉ minh họa**: `SomeCondition`, `AnotherCondition` và `OptionalService` là những kiểu giả định, chưa phải chương trình chạy độc lập.

Trước khi Spring quyết định đăng ký `OptionalConfiguration` và `optionalService`, nó phải biết các annotation đang gắn trên **lớp** hoặc **phương thức** tương ứng, kể cả những thuộc tính của annotation. Việc tạo bean rồi mới hỏi “có được phép tạo hay không?” vừa tốn tài nguyên vừa sai thứ tự lifecycle.

Spring Framework truyền hai đối tượng vào một `Condition`:

```java
boolean matches(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
```

- **`ConditionContext`** cung cấp bối cảnh để kiểm tra: `Environment`, registry, bean factory, class loader và resource loader khi thích hợp.
- **`AnnotatedTypeMetadata`** cung cấp thông tin **annotation trên đối tượng đang được xét**: loại annotation, thuộc tính được khai báo, meta-annotation và cách các annotation được hợp nhất theo cơ chế Spring.
- **Giá trị trả về**: `true` cho phép Spring tiếp tục đăng ký thành phần theo điều kiện đang xét; `false` phủ quyết đăng ký thành phần ấy.

Một `Condition` không nên tự tạo bean nghiệp vụ hay gọi `getBean()` để thử. Điều kiện được kiểm tra trong các pha Spring đang xây dựng registry; tùy thời điểm, các instance cần thiết có thể chưa tồn tại.

## 2. AnnotatedTypeMetadata là gì?

Giao diện `org.springframework.core.type.AnnotatedTypeMetadata` mô tả annotation của **một class hoặc method cụ thể** mà không buộc mã gọi phải nắm được một `Class<?>`/`Method` reflection tương ứng. Spring có thể sử dụng implementation đọc class metadata bằng ASM, bên cạnh implementation dựa trên reflection.

Quan hệ các giao diện chính:

```text
                   AnnotatedTypeMetadata
                      /            \
                     /              \
        AnnotationMetadata        MethodMetadata
          (cho một class)         (cho một method)
```

Đây là quan hệ kế thừa giao diện, không phải mô hình phân cấp bean. Trong xử lý điều kiện:

- Khi `@Conditional` nằm trên **lớp cấu hình**, tham số metadata thường cung cấp khả năng của `AnnotationMetadata`.
- Khi `@Conditional` nằm trên **phương thức `@Bean`**, tham số metadata thường cung cấp khả năng của `MethodMetadata`.
- Code điều kiện có thể viết một lần dựa trên các phương thức chung của `AnnotatedTypeMetadata`, thay vì buộc phải biết đang xét class hay method.

Metadata **không phải** `BeanDefinition`, **không phải** instance bean và **không phải** tập property trong `application.yml`. Nó mô tả annotation mà Spring đã đọc trên phần tử được xét. Muốn đọc property môi trường thì dùng `ConditionContext#getEnvironment()`.

### Các API thường dùng

| API | Trả về/ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getAnnotations()` | `MergedAnnotations` cho annotation trực tiếp và meta-annotation | API hiện đại hỗ trợ xử lý annotation tổng hợp và alias |
| `isAnnotated(String)` | Kiểm tra có annotation tương ứng, kể cả thông qua meta-annotation | Nhận **tên lớp đầy đủ** của annotation |
| `getAnnotationAttributes(String)` | `Map<String,Object>` các thuộc tính đã được Spring xử lý/hợp nhất | Có thể trả `null` khi không tìm thấy |
| `getAnnotationAttributes(String, boolean)` | Như trên, có lựa chọn biểu diễn class-valued attributes thành tên chuỗi | `true` giúp hạn chế việc phải resolve class từ một thuộc tính |
| `getAllAnnotationAttributes(String)` | `MultiValueMap` các nhóm thuộc tính của nhiều annotation trùng loại | Ngữ nghĩa gộp/override khác `getAnnotationAttributes`; không thay thế tùy tiện |
| `AnnotationMetadata#getClassName()` | Tên class đang được mô tả | Chỉ dùng sau khi xác định metadata là class |
| `AnnotationMetadata#getAnnotatedMethods(...)` | Các `MethodMetadata` của phương thức có annotation | Chỉ có trên metadata cấp lớp |
| `MethodMetadata#getMethodName()` | Tên phương thức đang được mô tả | Chỉ có trên metadata cấp method |
| `MethodMetadata#getReturnTypeName()` | Tên kiểu trả về của method | Có ích khi phân tích phương thức `@Bean` |

Ví dụ đọc một annotation cụ thể:

```java
String annotationName = "com.example.condition.FeatureEnabled";
Map<String, Object> attrs =
    metadata.getAnnotationAttributes(annotationName);

if (attrs != null) {
    String property = (String) attrs.get("property");
}
```

Snippet này **không độc lập**: giả định biến `metadata` đã được Spring truyền vào `Condition` và có import `java.util.Map`. Một điều kiện production phải xác định rõ annotation có bắt buộc hay không, kiểm tra kiểu dữ liệu và xử lý giá trị thiếu đúng ngữ nghĩa.

### "Dữ liệu annotation" có thể gồm những gì?

Giả sử tạo annotation:

```java
@FeatureEnabled(
    property = "demo.feature.enabled",
    matchIfMissing = true
)
```

Các dữ liệu đọc được có thể gồm:

- Tên annotation: `com.example.condition.FeatureEnabled`.
- Thuộc tính `property`: chuỗi `"demo.feature.enabled"`.
- Thuộc tính `matchIfMissing`: giá trị `true`.
- Annotation mà `@FeatureEnabled` sử dụng như meta-annotation, ví dụ `@Conditional`.
- Những thuộc tính được Spring xử lý khi annotation hợp thành có `@AliasFor`.

Vì vậy một `Condition` có thể kiểm tra **quy tắc do chính annotation khai báo** và so sánh với **trạng thái bên ngoài annotation** từ `Environment` hay registry.

## 3. @Conditional quyết định điều gì?

Annotation Spring:

```java
@Conditional(FeatureEnabledCondition.class)
```

có thể đặt trực tiếp lên lớp cấu hình, phương thức `@Bean` hoặc được dùng làm meta-annotation để xây annotation tùy chỉnh. Nó nhận một hay nhiều lớp triển khai `org.springframework.context.annotation.Condition`.

Với nhiều điều kiện trên cùng thành phần, về nguyên tắc **tất cả** điều kiện bắt buộc đều phải khớp để phần tử đủ điều kiện đăng ký. Spring có các quy tắc sắp xếp/đánh giá condition tương ứng; đừng coi điều kiện là một chuỗi lời gọi có thứ tự ngẫu nhiên có thể thay thế nhau.

### Phạm vi tác động ở class và method

```text
@Configuration
@Conditional(ClassCondition.class)
class FeatureConfiguration {
    @Bean
    @Conditional(MethodCondition.class)
    Service service() { ... }
}
```

- Nếu điều kiện **cấp class** sai, lớp cấu hình có thể bị bỏ qua, kéo theo các `@Bean`, `@Import` và `@ComponentScan` liên quan của lớp ấy không được xử lý theo cách thông thường.
- Nếu điều kiện **cấp class** đúng nhưng điều kiện **cấp method** sai, phương thức `@Bean` bị bỏ qua, trong khi các thành phần khác của lớp cấu hình vẫn có thể được xử lý.
- Nếu cả hai đúng, định nghĩa bean có thể được đăng ký; **vẫn chưa chắc instance được khởi tạo thành công** vì còn dependency và lifecycle.

`@Conditional` là công cụ quyết định điều kiện đăng ký, không phải annotation để chạy hoặc kiểm thử một bean đã tồn tại. Điều này đặc biệt quan trọng với auto-configuration: những lớp `@AutoConfiguration` và phương thức `@Bean` trong đó có thể mang nhiều điều kiện khác nhau.

## 4. ConditionContext cung cấp gì mà AnnotatedTypeMetadata không có?

Một chữ ký của `Condition` có hai tham số vì chúng trả lời **hai câu hỏi khác nhau**:

```text
AnnotatedTypeMetadata:
  Trên class/method này có annotation nào?
  Annotation đó khai báo thuộc tính nào?
  Có meta-annotation/alias nào liên quan?

ConditionContext:
  Các property đang hiệu lực là gì?
  Những bean definitions nào đã được đăng ký?
  Sử dụng class loader nào?
  Có thể truy cập resource nào?
```

Những API tiêu biểu của `ConditionContext`:

```java
context.getEnvironment()
context.getRegistry()
context.getBeanFactory()
context.getClassLoader()
context.getResourceLoader()
```

Đây là đoạn minh họa API trong một phương thức `matches(...)`, không phải mã chạy độc lập. Tùy context và giai đoạn, một số thành phần có thể vắng mặt hoặc chưa hoàn chỉnh. Điều kiện nên chỉ đọc dữ liệu thích hợp, tránh khởi tạo các bean instance ở pha đang đăng ký định nghĩa.

Ví dụ: metadata cho biết annotation yêu cầu thuộc tính `"demo.feature.enabled"`, còn environment cho biết giá trị thực tế của key đó trong lần chạy này là `true` hay `false`.

Có thể hình dung một condition là hàm:

```text
matches(context, metadata)
    = quy tắc được mô tả trong annotation
      + thông tin ngữ cảnh có thể kiểm tra tại pha này
      -> boolean
```

Không phải mọi `Condition` đều cần đọc mọi API. Ví dụ một điều kiện chỉ phụ thuộc environment không cần biết tên lớp được annotate; một điều kiện dựa trên classpath có thể dùng class loader.

## 5. Đọc annotation trực tiếp, meta-annotation và annotation hợp thành

Spring không chỉ quan tâm `@Conditional` được viết trực tiếp hay gián tiếp. Một annotation như:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(FeatureEnabledCondition.class)
public @interface FeatureEnabled {
    String property();
    boolean matchIfMissing() default false;
}
```

vừa là annotation của người dùng, vừa là annotation **hợp thành** có meta-annotation `@Conditional`. Khi `@FeatureEnabled` xuất hiện trên class hoặc method, Spring có thể phát hiện điều kiện thông qua meta-annotation.

Các nguyên tắc:

1. **Direct annotation:** annotation được đặt trực tiếp trên phần tử, như `@FeatureEnabled`.
2. **Meta-annotation:** annotation đặt trên một annotation khác; ở đây `@Conditional` nằm trên `@FeatureEnabled`.
3. **Merged annotations:** Spring cung cấp mô hình `MergedAnnotations` để xử lý hệ thống annotation, bao gồm nhiều trường hợp alias/composed annotations.
4. **Attribute aliasing:** với `@AliasFor`, thuộc tính của annotation hợp thành có thể được ánh xạ sang thuộc tính ở một mức khác. Khi có alias, đọc qua API của Spring thường đúng hơn việc tự soi reflection đơn giản rồi tự ghép Map.
5. **Repeated annotations:** một annotation có thể xuất hiện qua nhiều đường trong hierarchy. Cần biết đang muốn **một bộ thuộc tính hợp nhất** hay **tất cả lần xuất hiện** trước khi chọn `getAnnotationAttributes` hoặc `getAllAnnotationAttributes`.

Lưu ý: `AnnotatedTypeMetadata` có thể tránh nạp **class được mô tả**, nhưng không có nghĩa mọi loại annotation đều được truy xuất mà không nạp bất kỳ class nào. Một số annotation và kiểu liên quan vẫn có thể phải được nạp; class-valued attributes và annotation thiếu dependency cần được thiết kế cẩn thận.

## 6. Ví dụ Java 17 chạy được: cùng một Condition cho lớp và @Bean

Chúng ta xây một ứng dụng Spring Boot **không có web server**, có một annotation tùy chỉnh `@FeatureEnabled` và một `Condition` đọc:

- Tên property và `matchIfMissing` từ **`AnnotatedTypeMetadata`**.
- Giá trị property đang hiệu lực từ **`ConditionContext#getEnvironment()`**.

Annotation được gắn cả trên một lớp `@Configuration` và một phương thức `@Bean`. Khi khởi động, chương trình đọc lại metadata của lớp và phương thức để chứng minh chúng là hai cấp khác nhau. Nhờ `ObjectProvider`, chương trình vẫn chạy khi điều kiện tắt bean.

Ví dụ dùng **JDK 17+**, **Spring Boot 3.3.13** và **Maven**.

### 6.1. Cấu trúc dự án

```text
annotation-metadata-demo/
├── pom.xml
└── src/main/java/demo/
    ├── MetadataDemoApplication.java
    ├── condition/
    │   ├── FeatureEnabled.java
    │   └── FeatureEnabledCondition.java
    ├── config/
    │   └── GreetingConfiguration.java
    └── model/
        └── Greeting.java
```

Lớp main ở package `demo`, các package `condition`, `config` và `model` nằm phía dưới. Nhờ vậy Spring Boot có thể scan `GreetingConfiguration`; các class không mang stereotype sẽ không tự biến thành bean chỉ vì cùng package.

### 6.2. pom.xml

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
    <groupId>example</groupId>
    <artifactId>annotation-metadata-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

`spring-boot-starter` mang các dependency Spring container cần thiết, nên ví dụ không phải tự khai báo các JAR `spring-core`, `spring-context` hoặc `spring-boot` rời rạc.

### 6.3. Annotation có thể áp dụng cho class và method

**`src/main/java/demo/condition/FeatureEnabled.java`**

```java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(FeatureEnabledCondition.class)
public @interface FeatureEnabled {

    String property();

    boolean matchIfMissing() default false;
}
```

Hai thuộc tính mô tả chính sách:

- `property`: tên key cần kiểm tra trong Spring `Environment`.
- `matchIfMissing`: kết quả mặc định nếu property chưa tồn tại (ví dụ này để `false` khi không khai báo).

`@Conditional` trên annotation cho phép Spring dùng `FeatureEnabledCondition` mà không phải khai báo riêng trên mọi lớp và phương thức.

### 6.4. Condition đọc metadata, sau đó kiểm tra Environment

**`src/main/java/demo/condition/FeatureEnabledCondition.java`**

```java
package demo.condition;

import java.util.Map;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class FeatureEnabledCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
            metadata.getAnnotationAttributes(FeatureEnabled.class.getName());

        if (attributes == null) {
            return false;
        }

        String property = (String) attributes.get("property");
        boolean matchIfMissing = (Boolean) attributes.get("matchIfMissing");

        return context.getEnvironment()
            .getProperty(property, Boolean.class, matchIfMissing);
    }
}
```

Đây là phần lõi của bài:

1. `getAnnotationAttributes(...)` đọc các thuộc tính mà `@FeatureEnabled` khai báo trên **phần tử đang được đánh giá**.
2. Điều kiện không cần ép kiểu `metadata` thành `AnnotationMetadata` hoặc `MethodMetadata`, vì API chung đã đủ.
3. `Environment#getProperty(key, Boolean.class, defaultValue)` chuyển property sang boolean; nếu thiếu property, dùng `matchIfMissing` được khai báo trong annotation.
4. Hàm không gọi `getBean()`, không tạo instance và không thay đổi registry. Nó chỉ trả lời liệu annotation này có thỏa điều kiện hay không.

Đây là một **điều kiện được thiết kế riêng cho bài học**, không phải phiên bản thay thế đầy đủ của `@ConditionalOnProperty`. Trong ứng dụng thật, khi chỉ cần property boolean thông thường, nên ưu tiên annotation built-in của Spring Boot để có hành vi và báo cáo điều kiện đã được kiểm chứng.

### 6.5. Model đơn giản

**`src/main/java/demo/model/Greeting.java`**

```java
package demo.model;

public record Greeting(String message) {
}
```

Record này không có `@Component`, nên nó không tự được Spring đăng ký. Một bean `Greeting` sẽ chỉ tồn tại nếu phương thức `@Bean` bên dưới thỏa điều kiện.

### 6.6. Một điều kiện đặt trên lớp, một điều kiện đặt trên phương thức

**`src/main/java/demo/config/GreetingConfiguration.java`**

```java
package demo.config;

import demo.condition.FeatureEnabled;
import demo.model.Greeting;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@FeatureEnabled(
    property = "demo.module.enabled",
    matchIfMissing = true
)
public class GreetingConfiguration {

    @Bean
    @FeatureEnabled(
        property = "demo.greeting.enabled",
        matchIfMissing = true
    )
    Greeting greeting() {
        return new Greeting("Xin chào từ Spring");
    }
}
```

Cách đánh giá:

- Lớp `GreetingConfiguration` phải thỏa `demo.module.enabled`. Nếu không, cấu hình này bị bỏ qua; phương thức `greeting()` không được đăng ký theo con đường này.
- Khi lớp được chọn, phương thức `@Bean greeting()` còn phải thỏa `demo.greeting.enabled`.
- Chỉ khi cả hai điều kiện cần thiết đều khớp, bean definition `greeting` mới có thể được đăng ký.
- `Greeting` được tạo bởi container sau khi bean definition đã hợp lệ; `AnnotatedTypeMetadata` mô tả annotation **không phải instance `Greeting`**.

Hai property do ví dụ tự đặt; Spring Boot không tự cung cấp chúng như các thuộc tính có sẵn.

### 6.7. Quan sát AnnotationMetadata và MethodMetadata

**`src/main/java/demo/MetadataDemoApplication.java`**

```java
package demo;

import java.util.Map;
import demo.condition.FeatureEnabled;
import demo.config.GreetingConfiguration;
import demo.model.Greeting;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.type.AnnotationMetadata;
import org.springframework.core.type.MethodMetadata;

@SpringBootApplication
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ObjectProvider<Greeting> greetings) {
        return args -> {
            AnnotationMetadata classMetadata =
                AnnotationMetadata.introspect(GreetingConfiguration.class);

            Map<String, Object> classAttributes =
                classMetadata.getAnnotationAttributes(
                    FeatureEnabled.class.getName());

            MethodMetadata methodMetadata = classMetadata
                .getAnnotatedMethods(FeatureEnabled.class.getName())
                .stream()
                .filter(m -> m.getMethodName().equals("greeting"))
                .findFirst()
                .orElseThrow();

            Map<String, Object> methodAttributes =
                methodMetadata.getAnnotationAttributes(
                    FeatureEnabled.class.getName());

            System.out.println("CLASS_PROPERTY: "
                + classAttributes.get("property"));
            System.out.println("METHOD_NAME: "
                + methodMetadata.getMethodName());
            System.out.println("METHOD_PROPERTY: "
                + methodAttributes.get("property"));

            Greeting greeting = greetings.getIfAvailable();

            System.out.println("GREETING_PRESENT: "
                + (greeting != null));
            if (greeting != null) {
                System.out.println("GREETING: "
                    + greeting.message());
            }
        };
    }
}
```

Ở đây `AnnotationMetadata.introspect(GreetingConfiguration.class)` là **cách đọc bằng reflection để quan sát metadata trong ví dụ**, không phải khẳng định Spring luôn dùng chính instance metadata này khi startup. Trong quá trình quét classpath, Spring có thể đọc metadata qua ASM.

`classMetadata.getAnnotatedMethods(...)` trả các `MethodMetadata` của phương thức được đánh dấu annotation phù hợp. Phần lọc tên `greeting` giúp kết quả rõ ràng và không phụ thuộc thứ tự liệt kê. Khi cấu hình bị điều kiện loại, `GreetingConfiguration.class` vẫn có trên classpath nên phần đọc metadata từ class bằng reflection này **vẫn thực hiện được**; chỉ bean của nó không được đăng ký vào context.

Dùng `ObjectProvider<Greeting>` thay vì inject bắt buộc `Greeting`, để các lần chạy tắt điều kiện không thất bại khi thiếu bean.

## 7. Chạy thử và đọc đầu ra chính xác

Từ thư mục chứa `pom.xml`, có Maven và Java 17+:

```bash
mvn -q -DskipTests package
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Không tính banner và log của Boot, các dòng do code tự in theo thứ tự:

```text
CLASS_PROPERTY: demo.module.enabled
METHOD_NAME: greeting
METHOD_PROPERTY: demo.greeting.enabled
GREETING_PRESENT: true
GREETING: Xin chào từ Spring
```

Giải thích: vì không cung cấp property nào, cả hai annotation đặt `matchIfMissing=true`, nên điều kiện class và method đều khớp. Spring đăng ký bean `Greeting` và `ObjectProvider` tìm thấy nó.

### 7.1. Tắt điều kiện cấp method

Chạy:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.enabled=false
```

Dòng do chương trình in:

```text
CLASS_PROPERTY: demo.module.enabled
METHOD_NAME: greeting
METHOD_PROPERTY: demo.greeting.enabled
GREETING_PRESENT: false
```

Lớp cấu hình vẫn đủ điều kiện vì `demo.module.enabled` không được khai báo và `matchIfMissing=true`. Nhưng điều kiện trên `@Bean greeting()` đọc metadata cấp **method**, gặp `demo.greeting.enabled=false` trong environment nên trả `false`. Do đó bean definition của phương thức không được đăng ký.

### 7.2. Tắt điều kiện cấp class

Chạy:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.module.enabled=false
```

Dòng do chương trình in:

```text
CLASS_PROPERTY: demo.module.enabled
METHOD_NAME: greeting
METHOD_PROPERTY: demo.greeting.enabled
GREETING_PRESENT: false
```

Lần này class `GreetingConfiguration` bị loại khi điều kiện cấp class không khớp. Dù thuộc tính method mặc định cho phép, `@Bean` bên trong lớp không còn được xử lý qua cấu hình bị bỏ qua. Phần in metadata vẫn hoạt động vì nó **đọc annotation từ class Java**, không phụ thuộc bean `Greeting` có được Spring đăng ký hay không.

### 7.3. Cả hai property đều true

Chạy:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.module.enabled=true \
  --demo.greeting.enabled=true
```

Các dòng in giống trường hợp mặc định ở đầu mục 7. Không có “hai bean” vì mỗi condition chỉ cho phép hoặc phủ quyết đăng ký definition tương ứng, không nhân đôi đối tượng khi được bật.

### 7.4. Bảng tổng hợp

| `demo.module.enabled` | `demo.greeting.enabled` | Kết quả bean `Greeting` |
| --- | --- | --- |
| Không đặt | Không đặt | Có (cả hai `matchIfMissing=true`) |
| `true` | `true` | Có |
| `true` | `false` | Không (method-level condition) |
| `false` | `true` | Không (class-level condition) |
| `false` | `false` | Không (class-level condition đã sai) |
| Không đặt | `false` | Không (method-level condition sai) |

Trong mọi lần chạy, `AnnotationMetadata.introspect(...)` vẫn thấy **các thuộc tính annotation được viết trong source**. Điều thay đổi là **giá trị `Environment`**, vì vậy quyết định đăng ký bean khác nhau mà không cần chỉnh sửa Java class.

## 8. Khi nào cần ép kiểu sang AnnotationMetadata hoặc MethodMetadata?

Phần lớn custom condition chỉ cần:

```java
metadata.getAnnotationAttributes(MyAnnotation.class.getName())
```

Nhưng một số điều kiện đặc biệt cần thêm thông tin của class/method:

```java
if (metadata instanceof AnnotationMetadata classMetadata) {
    String className = classMetadata.getClassName();
    // kiểm tra tên class hoặc metadata các phương thức liên quan
}
else if (metadata instanceof MethodMetadata methodMetadata) {
    String methodName = methodMetadata.getMethodName();
    String returnType = methodMetadata.getReturnTypeName();
    // logic dành riêng cho một phương thức @Bean
}
```

Đây là snippet minh họa, cần biến `metadata` và các import trong một lớp triển khai `Condition`. **Không giả định** mọi `AnnotatedTypeMetadata` đều có `getClassName()` hoặc `getMethodName()`: chúng là API của hai interface con khác nhau.

Khi condition phụ thuộc vào việc đang xét class hay method, nên tự hỏi đó có phải là thiết kế đúng không. Đôi khi việc viết hai annotation/condition riêng làm quy tắc rõ ràng hơn là một condition cố áp dụng cho mọi vị trí.

### AnnotationMetadata có thể dùng để đọc những gì khác?

Ngoài các thuộc tính annotation chung, `AnnotationMetadata` kết hợp thông tin cấu trúc lớp qua `ClassMetadata`:

- Tên class (`getClassName()`).
- Tên superclass hoặc interfaces khi metadata có dữ liệu tương ứng.
- Các annotation trực tiếp (`getAnnotationTypes()`).
- Những method mang annotation (`getAnnotatedMethods(...)`).
- Các phương thức do class khai báo (`getDeclaredMethods()`).

Không phải mọi dữ liệu metadata đều nên quyết định một condition: ví dụ điều kiện có side effect khi kiểm tra tên class thường khó kiểm thử hơn một điều kiện dựa trên property hoặc classpath cụ thể.

## 9. Lấy dữ liệu annotation dưới dạng Map hay MergedAnnotations?

Hai cách đều tồn tại trong Spring Framework hiện đại, nhưng có mức biểu đạt khác nhau.

### Map-based API

```java
Map<String, Object> attrs = metadata.getAnnotationAttributes(
    FeatureEnabled.class.getName());

if (attrs != null) {
    String key = (String) attrs.get("property");
}
```

Ưu điểm: đơn giản, dễ tích hợp khi annotation được xác định bằng **tên class chuỗi**. Điểm cần chú ý: return `null` nếu không thấy annotation, và khi đọc thuộc tính cần biết đúng type của giá trị.

### MergedAnnotations API

```java
String key = metadata.getAnnotations()
    .get(FeatureEnabled.class)
    .getString("property");
```

Đây là snippet minh họa trong phạm vi đã có `metadata`/`FeatureEnabled`. Nó tiện khi đang dùng annotation type tại compile time và muốn truy xuất thuộc tính theo kiểu `MergedAnnotation`. Với annotation hợp thành phức tạp hoặc `@AliasFor`, nên dựa trên ngữ nghĩa hợp nhất được Spring cung cấp thay vì tự suy ra một Map thông qua reflection rời rạc.

`getAnnotationAttributes(annotationName, true)` còn hữu ích khi annotation có thuộc tính kiểu `Class`: ở những trường hợp được hỗ trợ, nó có thể trả về tên class thay vì buộc resolve trực tiếp một `Class<?>`. Đây không phải cơ chế “tắt class loading hoàn toàn”; chính annotation và các thành phần khác có thể vẫn phải được tải.

### Trường hợp repeatable/meta-annotation

Khi có nhiều lần xuất hiện của một annotation, `getAllAnnotationAttributes` trả `MultiValueMap` để đại diện nhiều bộ giá trị, nhưng phải đọc rõ Javadoc về cách các attribute từ annotation hợp thành/alias được xử lý. Không tự thay `getAnnotationAttributes` bằng `getAllAnnotationAttributes` với kỳ vọng chúng luôn tương đương.

## 10. Annotation metadata trong auto-configuration

Trong Spring Boot, rất nhiều điều kiện built-in dựa trên annotation: `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, `@ConditionalOnResource` và các điều kiện khác. Spring Boot dùng `SpringBootCondition` làm lớp cơ sở cho nhiều condition và cung cấp `ConditionOutcome` để ghi lý do khớp/không khớp.

Chữ ký quan trọng ở Boot:

```java
ConditionOutcome getMatchOutcome(
    ConditionContext context,
    AnnotatedTypeMetadata metadata
);
```

Đây là chữ ký API để đối chiếu: khi **tự kế thừa `SpringBootCondition`**, cần triển khai `getMatchOutcome(...)`, chứ không override `matches(...)` vốn được `SpringBootCondition` xử lý. Ví dụ trong mục 6 dùng `Condition` thuần túy, nên triển khai `matches(...)` là đúng.

Điểm cần phân biệt:

| Thành phần | Loại metadata/dữ liệu | Công dụng |
| --- | --- | --- |
| `AnnotatedTypeMetadata` | Annotation của một class/method đang xét | `Condition.matches(...)` đánh giá điều kiện |
| `ConditionContext` | Environment, registry, classloader, resources | Tra trạng thái bên ngoài annotation |
| `AutoConfigurationMetadata` (Boot) | Metadata được annotation processor tạo cho ứng viên auto-configuration | Tối ưu lọc sớm trước khi parse toàn bộ cấu hình |
| `BeanDefinition` | Metadata container về cách tạo bean | Được đăng ký nếu các điều kiện cần khớp |
| `ConfigurationProperties` | Dữ liệu cấu hình được bind vào object khi hệ thống tương ứng hoạt động | Không phải annotation metadata của `Condition` |

**`AnnotatedTypeMetadata` và `AutoConfigurationMetadata` không phải cùng một interface.** Cả hai liên quan đến việc tối ưu/đọc metadata, nhưng có thời điểm, cấu trúc và nhiệm vụ khác nhau.

### Điều kiện trên class auto-configuration và phương thức @Bean

Một lớp auto-configuration có thể mang điều kiện cấp class:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.OptionalClient")
class OptionalClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Connector.class)
    Connector connector() { return new Connector(); }
}
```

Đây là mã minh họa, không độc lập. Điều kiện cấp class kiểm tra classpath; điều kiện method kiểm tra ứng viên bean phù hợp ở thời điểm đăng ký. Metadata truyền cho điều kiện tùy thuộc phần tử được đánh giá.

Đừng suy luận rằng tất cả điều kiện có thể chạy tại một thời điểm duy nhất. Spring có thể đánh giá trong giai đoạn phân tích cấu hình hoặc đăng ký bean; những điều kiện phụ thuộc registry cần chú ý thứ tự. Một điều kiện tùy chỉnh dựa vào bean **instance** trước khi context refresh có thể phá vỡ logic khởi động.

## 11. ConfigurationCondition: chọn pha đánh giá đúng khi cần

`org.springframework.context.annotation.ConfigurationCondition` mở rộng `Condition` để một condition có thể công bố pha phù hợp:

```java
ConfigurationPhase getConfigurationPhase();
```

Hai pha có ý nghĩa:

- **`PARSE_CONFIGURATION`**: quyết định có phân tích lớp cấu hình này hay không.
- **`REGISTER_BEAN`**: quyết định ở giai đoạn đăng ký bean definitions.

Đây là công cụ nâng cao. Một condition thuần `Condition` không chỉ định pha như vậy; framework xác định nơi/đợt cần kiểm tra theo quá trình xử lý configuration. Nếu điều kiện yêu cầu quan sát bean definitions đã được đăng ký, cần cân nhắc kỹ pha, thứ tự và khả năng các ứng viên chưa hoàn chỉnh.

Tránh:

- Gọi `context.getBeanFactory().getBean(...)` trong `matches`.
- Sửa registry trong lúc condition chỉ được yêu cầu quyết định true/false.
- Cho rằng mọi singleton đã khởi tạo ở pha `REGISTER_BEAN`.
- Dựa vào log side effect để xác định thứ tự các điều kiện; Spring có thể gọi điều kiện nhiều lần vì nhiều pha, hoặc có đường xử lý khác nhau.

Để tạo bean theo điều kiện đơn giản, annotation built-in như `@ConditionalOnProperty` phù hợp hơn. Custom `ConfigurationCondition` có giá trị khi thực sự cần một chính sách đăng ký/phân tích cấu hình đặc biệt.

## 12. Những sai lầm phổ biến

### 12.1. Đọc giá trị annotation bằng cách tìm property cùng tên trong Environment

**Sai:** metadata tự chứa giá trị của `application.properties`.

**Đúng:** metadata chứa thuộc tính **trên annotation** như tên key và cờ mặc định; `Environment` chứa giá trị property được nạp khi ứng dụng khởi động. Trong ví dụ, `metadata` trả `"demo.greeting.enabled"` còn `Environment` trả `true` hoặc `false` cho key này.

### 12.2. Ép mọi metadata thành AnnotationMetadata

Một `Condition` được dùng trên `@Bean` method có thể nhận `MethodMetadata`. Ép trực tiếp không kiểm tra type có thể ném `ClassCastException`. Ưu tiên API chung của `AnnotatedTypeMetadata`, hoặc dùng `instanceof` nếu cần thông tin riêng.

### 12.3. Cho rằng getAnnotationAttributes luôn khác null

Không. Annotation có thể không có trên phần tử hoặc được đọc bằng tên không đúng. Phải xử lý `null`/kết quả không hiện diện và hiểu hợp đồng của annotation tùy chỉnh.

### 12.4. Khởi tạo bean trong Condition để “xem có chạy không”

Điều này vi phạm mô hình tách quyết định đăng ký và tạo instance. Nó có thể gây vòng dependency, eager initialization, thiếu post-processor hoặc side effect sớm. Chỉ đọc những thông tin phù hợp ở pha hiện tại.

### 12.5. Nhầm true của Condition với bean đã tồn tại

`true` chỉ cho phép thành phần đủ điều kiện theo condition ấy. Lớp/method có thể còn những condition khác hoặc gặp lỗi tạo instance. `false` thường ngăn definition tương ứng được đăng ký, khác với việc trì hoãn khởi tạo bằng `@Lazy`.

### 12.6. Coi annotation meta và alias giống Java reflection đơn giản

Spring hỗ trợ composed annotations và alias, do đó trực tiếp dùng `getDeclaredAnnotation(...)` rồi tự xử lý có thể khác với metadata mà Spring nhìn thấy. Dùng `getAnnotations()`/`getAnnotationAttributes()` khi muốn đúng ngữ nghĩa Spring.

### 12.7. Tạo custom condition chỉ để bật/tắt boolean property

Nếu nhu cầu chỉ là `feature.enabled=true` thì `@ConditionalOnProperty` thường dễ hiểu và dễ bảo trì hơn, đồng thời tận dụng chẩn đoán điều kiện có sẵn của Boot. Viết `Condition` riêng để học cơ chế là hợp lý; đưa vào production cần cân nhắc lợi ích.

### 12.8. Đánh đồng metadata đọc từ ASM với reflection

`AnnotationMetadata.introspect(SomeClass.class)` sử dụng class Java đã có; quá trình classpath scanning có thể đọc metadata từ file `.class` qua ASM mà không cần nạp class mục tiêu ngay. Cả hai triển khai có thể cung cấp cùng interface, nhưng khác cơ chế và thời điểm class loading. Đừng dựa vào cách ví dụ tự introspect để khẳng định tất cả đường nội bộ Spring đều dùng reflection.

## 13. Gỡ lỗi theo dữ kiện

Nếu bean không xuất hiện như mong muốn:

1. **Xác định annotation ở đâu:** cấp `@Configuration`, cấp `@Bean` hay meta-annotation tùy chỉnh.
2. **Kiểm tra metadata thực tế:** tên annotation đầy đủ, thuộc tính, kiểu giá trị, default và alias.
3. **Đối chiếu Environment:** property có được nạp, kiểu boolean có hợp lệ, profile có làm thay đổi giá trị không.
4. **Đọc condition theo đúng pha:** condition có phụ thuộc bean definitions khác hoặc classloader không.
5. **Phân biệt thiếu definition với lỗi tạo instance:** nếu condition `false`, bean definition có thể không xuất hiện; nếu condition `true` nhưng constructor lỗi, xem root cause của `BeanCreationException`.
6. **Bật chẩn đoán:** với các điều kiện built-in Boot, dùng `--debug` để xem Conditions Evaluation Report. Với custom `Condition` thuần túy, không giả định nó sẽ có thông báo lý do chi tiết giống `SpringBootCondition`; có thể bổ sung logging kiểm soát hoặc viết unit test.

Ví dụ kiểm tra output ứng dụng ở mục 6:

```bash
java -jar target/annotation-metadata-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.enabled=false \
  --debug
```

Các dòng do ứng dụng tự in không thay đổi so với mục 7.1; Boot có thể thêm log debug. Một condition không có logging riêng vẫn có thể trả đúng boolean và làm bean definition bị bỏ qua.

### Kiểm thử condition mà không khởi chạy server

Trong bài này không cần HTTP vì chỉ quan sát IoC container. Đối với thư viện auto-configuration thật, có thể dùng `ApplicationContextRunner` của `spring-boot-test` để dựng context nhỏ dưới các tổ hợp property/bean và khẳng định bean nào được đăng ký. Khi kiểm thử annotation metadata, nên bao phủ:

- Annotation đặt trên class và trên method.
- Property bị thiếu, `true`, `false`.
- Composed annotation và thuộc tính mặc định.
- Metadata không có annotation yêu cầu.
- Những điều kiện khác cùng xuất hiện.
- Một phương thức `@Bean` đã có definition nhưng bị lỗi khởi tạo (tình huống khác condition false).

Không cần dùng `getBean()` trong chính `Condition` để thực hiện các kiểm thử này.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `AnnotatedTypeMetadata` có mang sẵn giá trị `demo.module.enabled` từ file cấu hình không?

**Đáp án:** Không. Nó mô tả annotation và các thuộc tính như tên key. Giá trị property hiệu lực nằm trong `Environment` qua `ConditionContext`.

**Câu 2.** Khi condition đặt trên `@Bean greeting()`, metadata có nhất thiết là `AnnotationMetadata` không?

**Đáp án:** Không. Nó có thể cung cấp khả năng của `MethodMetadata`. Dùng API chung `AnnotatedTypeMetadata` hoặc kiểm tra type trước khi cần cast.

**Câu 3.** `@FeatureEnabled` trong ví dụ liên hệ `Condition` bằng cách nào?

**Đáp án:** Chính annotation tùy chỉnh được meta-annotate bằng `@Conditional(FeatureEnabledCondition.class)`. Spring tìm thấy điều kiện khi phân tích class hoặc method có `@FeatureEnabled`.

**Câu 4.** Vì sao tắt `demo.module.enabled=false` vẫn in được metadata của class `GreetingConfiguration`?

**Đáp án:** `AnnotationMetadata.introspect(GreetingConfiguration.class)` đọc annotation từ class Java có trên classpath. Việc condition ngăn Spring đăng ký bean không xóa class hoặc annotation khỏi bytecode.

**Câu 5.** Nếu `getAnnotationAttributes(...)` trả null, nên làm gì?

**Đáp án:** Xác định hợp đồng condition. Nếu annotation là bắt buộc, có thể trả `false` hoặc báo lỗi cấu hình rõ ràng; không tự ép kiểu `null` rồi xử lý như Map.

**Câu 6.** `getAnnotations()` khác gì đọc annotation trực tiếp bằng Java reflection?

**Đáp án:** Nó sử dụng hệ `MergedAnnotations` của Spring, xử lý nhiều khía cạnh của annotation hợp thành, meta-annotation và alias. Nó không đơn thuần là một bản sao API `Class#getAnnotation`.

**Câu 7.** Một custom condition trả `true` nghĩa là bean sẽ chắc chắn được tạo?

**Đáp án:** Không. Thành phần có thể còn điều kiện khác, bean definition được tạo nhưng bean lazy chưa khởi tạo, hoặc việc tạo bean có thể thất bại sau đó.

**Câu 8.** `AutoConfigurationMetadata` có phải interface cha của `AnnotatedTypeMetadata` không?

**Đáp án:** Không. Chúng là hai API khác nhau, phục vụ những công việc và giai đoạn khác nhau.

## 15. Tài liệu tham khảo

- Spring Framework 6.1, `AnnotatedTypeMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html
- Spring Framework 6.1, `AnnotationMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotationMetadata.html
- Spring Framework 6.1, `MethodMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/MethodMetadata.html
- Spring Framework 6.1, `Condition` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html
- Spring Framework 6.1, `@Conditional` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html
- Spring Boot 3.3.13, `SpringBootCondition` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Spring Boot, Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
