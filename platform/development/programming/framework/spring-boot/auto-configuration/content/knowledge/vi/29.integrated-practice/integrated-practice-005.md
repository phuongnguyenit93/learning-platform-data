# Tách tích hợp tùy chọn và kiểm tra khi thiếu dependency bằng `FilteredClassLoader`

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Thực hành tổng hợp  
**Mục tiêu:** Thiết kế một tích hợp tùy chọn chỉ được kích hoạt khi thư viện bên ngoài có trên runtime classpath; cô lập các tham chiếu tới API tùy chọn để ứng dụng vẫn khởi động khi dependency vắng mặt; và kiểm thử cả hai trạng thái bằng `FilteredClassLoader` cùng `ApplicationContextRunner`.

## 1. Bài toán: thư viện có tính năng tích hợp tùy chọn

Giả sử một thư viện cung cấp abstraction để chuyển object thành JSON:

```java
public interface JsonCodec {
    String encode(Object value);
}
```

Thư viện có thể dùng Jackson để triển khai:

```java
ObjectMapper objectMapper;
```

Nhưng không phải ứng dụng nào cũng cần Jackson. Một ứng dụng có thể dùng JSON codec khác, hoặc không cần chức năng JSON của thư viện. Nếu auto-configuration luôn tham chiếu `ObjectMapper`, ứng dụng không có Jackson có thể gặp lỗi nạp lớp khi Spring xử lý configuration.

Mục tiêu thiết kế:

- Ứng dụng có Jackson và bật feature: đăng ký `JsonCodec` mặc định.
- Ứng dụng không có Jackson: bỏ qua riêng phần tích hợp Jackson và vẫn khởi động bình thường.
- Ứng dụng tắt feature: không đăng ký bean tích hợp.
- Ứng dụng tự cung cấp `JsonCodec`: auto-configuration nhường chỗ.
- Ứng dụng có `ObjectMapper` riêng: bean mapper mặc định không được tạo.

Đây là trường hợp điển hình của optional integration: thư viện có thể biên dịch với một dependency, nhưng không được bắt mọi consumer phải mang dependency đó ở runtime.

## 2. Phân biệt compile classpath và runtime classpath

Một dependency có thể cần để biên dịch module auto-configuration nhưng không nhất thiết phải được truyền sang ứng dụng tiêu thụ thư viện.

| Giai đoạn | Câu hỏi cần trả lời |
| --- | --- |
| Compile module | Source của thư viện có cần API `ObjectMapper` để biên dịch không? |
| Test module | Test cần Jackson để kiểm tra nhánh tích hợp có mặt không? |
| Runtime consumer | Ứng dụng cuối có thực sự cài Jackson không? |
| Auto-configuration | Khi Jackson không có, Spring có bỏ qua nhánh tham chiếu Jackson an toàn không? |

Với Maven, dependency có `<optional>true</optional>` vẫn được dùng để compile và test chính module hiện tại. Tính optional có nghĩa dependency đó không tự động được truyền như dependency transitive cho consumer.

Ví dụ:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

Ứng dụng sử dụng thư viện có thể nhận Jackson từ một starter khác, khai báo Jackson trực tiếp, hoặc không có Jackson. Auto-configuration phải xử lý được cả hai trường hợp.

Với Gradle, một dependency chỉ cần cho compile source của thư viện có thể được khai báo bằng `compileOnly`; test thêm dependency đó vào `testImplementation`:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    compileOnly("com.fasterxml.jackson.core:jackson-databind")

    testImplementation("com.fasterxml.jackson.core:jackson-databind")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu API công khai của thư viện để lộ kiểu Jackson trong public method, constructor hoặc generic signature, hãy xem xét kỹ publication contract. `compileOnly` không cung cấp dependency cho compile classpath của consumer. Tốt nhất giữ API tùy chọn bên trong adapter và chỉ công bố abstraction độc lập như `JsonCodec`.

## 3. Vì sao thiếu dependency có thể gây lỗi trước khi condition được áp dụng?

Giả sử configuration class chính chứa method:

```java
@Bean
JsonCodec jsonCodec(ObjectMapper objectMapper) {
    return new JacksonJsonCodec(objectMapper);
}
```

Nếu Jackson không có trên runtime classpath, kiểu `ObjectMapper` trong method signature có thể khiến JVM hoặc Spring phải phân giải một class không tồn tại khi introspect configuration. Khi đó lỗi có thể xảy ra trước lúc condition trên method bảo vệ bean được áp dụng.

Những lỗi thường gặp:

```text
java.lang.NoClassDefFoundError:
com/fasterxml/jackson/databind/ObjectMapper
```

hoặc:

```text
java.lang.ClassNotFoundException:
com.fasterxml.jackson.databind.ObjectMapper
```

Hai lỗi không hoàn toàn giống nhau:

- `ClassNotFoundException` thường xuất hiện khi code chủ động yêu cầu classloader tìm một class và không tìm thấy.
- `NoClassDefFoundError` là lỗi linkage khi JVM cần một class mà quá trình nạp/liên kết không thể cung cấp.

Một lỗi khác như `NoSuchMethodError` thường cho thấy class đã được nạp nhưng version runtime không có method mà bytecode đang gọi; đây là vấn đề binary compatibility/version mismatch.

**Điểm mấu chốt:** điều kiện phải bảo vệ cả nhánh configuration chứa tham chiếu tới optional type. Chỉ đặt `@ConditionalOnMissingBean` hoặc `@ConditionalOnProperty` trên method chưa đủ nếu Spring phải đọc method signature trước khi biết dependency có mặt hay không.

## 4. Đặt `@ConditionalOnClass` trên configuration riêng

Spring Boot cung cấp `@ConditionalOnClass` để kiểm tra class có tồn tại trên classpath hay không.

Với optional integration, hãy cô lập phần tham chiếu tới thư viện tùy chọn trong một nested static configuration:

```java
@AutoConfiguration
public class JsonCodecAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class JacksonConfiguration {

        // Các @Bean có tham chiếu tới ObjectMapper đặt ở đây.
    }
}
```

Có hai chi tiết quan trọng:

1. `JacksonConfiguration` là class riêng, được bảo vệ bằng class condition ở cấp class.
2. Thuộc tính `name` dùng tên đầy đủ dạng String, không buộc classloader phải phân giải `ObjectMapper.class` chỉ để đọc annotation.

Spring Boot đọc metadata của class condition trong quá trình phân tích configuration. Khi class không có, nested configuration được bỏ qua trước khi các bean method bên trong cần được xử lý.

Có thể dùng `@ConditionalOnClass(SomeOptionalType.class)` ở vị trí phù hợp khi type chắc chắn có thể được phân giải. Với optional type và class cần tồn tại trong nhiều runtime khác nhau, `name = "..."` giúp tránh tham chiếu class literal ngay trong annotation.

### 4.1. Không để optional type rò ra lớp configuration bên ngoài

Lớp ngoài nên tránh:

- Field có kiểu `ObjectMapper`.
- Constructor nhận `ObjectMapper`.
- Superclass hoặc interface phụ thuộc Jackson.
- Method `@Bean` trả về hoặc nhận `ObjectMapper`.
- Static initializer gọi Jackson.
- Annotation ở lớp ngoài chứa class literal của API tùy chọn.

Ví dụ không nên viết:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class JsonCodecAutoConfiguration {

    private ObjectMapper mapper;

    @Bean
    JsonCodec jsonCodec() {
        return new JacksonJsonCodec(this.mapper);
    }
}
```

Dù class có condition, field signature vẫn làm lớp ngoài phụ thuộc vào API tùy chọn. Hãy chuyển field, method và mọi tham chiếu Jackson sang nested configuration được bảo vệ.

### 4.2. Cấu hình lồng nhau phải là `static`

Dùng nested class `static`:

```java
@Configuration(proxyBeanMethods = false)
static class JacksonConfiguration {
}
```

Nested configuration không cần instance của lớp ngoài. Điều này giúp Spring đăng ký configuration độc lập và tránh phụ thuộc vào object instance của auto-configuration cha.

## 5. Tổ chức module và API độc lập với Jackson

Ví dụ dùng ba thành phần:

```text
json-codec-autoconfigure/
├── src/main/java/demo/json/
│   ├── JsonCodec.java
│   ├── autoconfigure/
│   │   ├── JsonCodecAutoConfiguration.java
│   │   └── JacksonJsonCodec.java
│   └── config/
│       └── JsonCodecProperties.java
├── src/main/resources/META-INF/spring/
│   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── src/test/java/demo/json/
    └── JsonCodecAutoConfigurationTests.java
```

Trách nhiệm:

| Thành phần | Có phụ thuộc Jackson không? | Vai trò |
| --- | --- | --- |
| `JsonCodec` | Không | Contract mà consumer sử dụng |
| `JacksonJsonCodec` | Có | Adapter triển khai contract bằng Jackson |
| `JsonCodecAutoConfiguration` | Không nên có | Điều kiện feature và import nhánh tích hợp |
| `JacksonConfiguration` | Có, nhưng được bảo vệ | Đăng ký mapper và codec khi Jackson hiện diện |
| Test | Có ở test runtime | Kiểm tra nhánh có dependency và nhánh bị lọc |

Nếu có nhiều tích hợp tùy chọn lớn, ví dụ Jackson, Gson, protobuf và một vendor SDK, có thể tách mỗi adapter thành module riêng. Core module chỉ công bố interface; module adapter phụ thuộc vào thư viện tương ứng và tự đăng ký auto-configuration của nó.

Cách tách module làm dependency graph của consumer rõ ràng: chỉ thêm adapter mà ứng dụng thật sự cần.

## 6. Tạo abstraction `JsonCodec`

File `JsonCodec.java`:

```java
package demo.json;

public interface JsonCodec {

    String encode(Object value);
}
```

Interface không nhắc đến Jackson. Controller, service hoặc module khác chỉ phụ thuộc vào contract này.

Ví dụ consumer:

```java
package demo.app;

import demo.json.JsonCodec;

public class AuditService {

    private final JsonCodec jsonCodec;

    public AuditService(JsonCodec jsonCodec) {
        this.jsonCodec = jsonCodec;
    }

    public String createAuditPayload(Object event) {
        return this.jsonCodec.encode(event);
    }
}
```

`AuditService` không cần biết implementation dùng Jackson, Gson hay serializer nội bộ. Điều này cho phép ứng dụng thay implementation mà không sửa business service.

## 7. Viết adapter chỉ dành cho nhánh Jackson

File `JacksonJsonCodec.java`:

```java
package demo.json.autoconfigure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import demo.json.JsonCodec;

final class JacksonJsonCodec implements JsonCodec {

    private final ObjectMapper objectMapper;

    JacksonJsonCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public String encode(Object value) {
        try {
            return this.objectMapper.writeValueAsString(value);
        }
        catch (JsonProcessingException exception) {
            throw new IllegalArgumentException(
                    "Cannot encode value as JSON",
                    exception
            );
        }
    }
}
```

Class adapter có tham chiếu trực tiếp tới Jackson. Đây là điều có chủ đích: class chỉ được dùng khi nhánh Jackson đã được xác nhận có mặt.

Adapter có package visibility thay vì public vì consumer chỉ cần `JsonCodec`. Điều này tránh làm optional Jackson type trở thành một phần API công khai của thư viện.

Không đặt `@Component` trên adapter trong ví dụ này. Auto-configuration sẽ đăng ký nó bằng `@Bean` khi nhánh Jackson match.

## 8. Viết auto-configuration với nhánh tùy chọn

File `JsonCodecAutoConfiguration.java`:

```java
package demo.json.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;

import demo.json.JsonCodec;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.json",
        name = "enabled",
        havingValue = "true"
)
public class JsonCodecAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(ObjectMapper.class)
        ObjectMapper jsonObjectMapper() {
            return new ObjectMapper();
        }

        @Bean
        @ConditionalOnMissingBean(JsonCodec.class)
        JsonCodec jsonCodec(ObjectMapper objectMapper) {
            return new JacksonJsonCodec(objectMapper);
        }
    }
}
```

**Lưu ý về cấu trúc:** trong source thực tế, import `ObjectMapper` và các method tham chiếu đến nó thuộc nested configuration được bảo vệ. Để giữ ranh giới classloading chặt chẽ nhất, có thể chuyển `JacksonConfiguration` thành một top-level configuration class riêng trong package `autoconfigure`, rồi để auto-configuration chính import class đó bằng `@Import` với condition ở cấp class. Dù chọn nested hay top-level, không đưa `ObjectMapper` vào chữ ký hoặc field của lớp ngoài.

Nếu dùng nested class như trên, hãy giữ mọi method, import cần thiết và adapter phụ thuộc Jackson trong nhánh nested; kiểm chứng bằng test `FilteredClassLoader` để phát hiện sớm bất kỳ tham chiếu nào bị rò ra ngoài.

Các điều kiện có ý nghĩa riêng:

- `@ConditionalOnProperty` bật/tắt toàn bộ feature theo cấu hình ứng dụng.
- `@ConditionalOnClass` chỉ kích hoạt nhánh Jackson khi `ObjectMapper` có trên classpath.
- `@ConditionalOnMissingBean(ObjectMapper.class)` cho phép ứng dụng cung cấp mapper riêng.
- `@ConditionalOnMissingBean(JsonCodec.class)` cho phép ứng dụng thay toàn bộ codec.

### 8.1. Khi nào nên dùng top-level optional configuration?

Nếu muốn ranh giới classloading rõ ràng nhất, dùng hai class:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.json",
        name = "enabled",
        havingValue = "true"
)
@Import(JacksonJsonCodecConfiguration.class)
public class JsonCodecAutoConfiguration {
}
```

File `JacksonJsonCodecConfiguration.java`:

```java
package demo.json.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;

import demo.json.JsonCodec;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(
        name = "com.fasterxml.jackson.databind.ObjectMapper"
)
class JacksonJsonCodecConfiguration {

    @Bean
    @ConditionalOnMissingBean(ObjectMapper.class)
    ObjectMapper jsonObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    @ConditionalOnMissingBean(JsonCodec.class)
    JsonCodec jsonCodec(ObjectMapper objectMapper) {
        return new JacksonJsonCodec(objectMapper);
    }
}
```

Trong ví dụ này, class configuration chứa optional type có class-level condition riêng. Đây là mẫu dễ kiểm tra và thường phù hợp khi nhánh tích hợp có nhiều bean hoặc nhiều class hỗ trợ.

Nếu dùng `@Import`, lớp ngoài chỉ tham chiếu đến configuration class của chính thư viện; nó không tham chiếu `ObjectMapper`. Khi class condition no-match, nhánh optional không tạo bean.

## 9. Đăng ký auto-configuration trong JAR

Với Spring Boot 2.7 trở lên, tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
demo.json.autoconfigure.JsonCodecAutoConfiguration
```

Chỉ đăng ký auto-configuration chính. Không cần liệt kê `JacksonJsonCodecConfiguration` như một auto-configuration độc lập nếu nó được import từ class chính.

Với Boot 2.6 và cũ hơn, cơ chế đăng ký dùng key `EnableAutoConfiguration` trong `META-INF/spring.factories`. Nếu thư viện hỗ trợ nhiều dòng Boot, cần giữ registration tương thích và kiểm tra annotation/API của từng baseline. Ví dụ trong bài dùng `@AutoConfiguration`, nên target Boot 2.7+.

## 10. Khai báo dependency tùy chọn trong Maven

Ví dụ POM dùng Java 17 và Spring Boot 3.3.13:

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

    <groupId>demo</groupId>
    <artifactId>json-codec-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`jackson-databind` có mặt trên compile/test classpath của chính module để source adapter được biên dịch. Vì dependency được đánh dấu optional, consumer không tự nhận Jackson chỉ vì thêm `json-codec-autoconfigure`.

Ứng dụng muốn dùng tích hợp Jackson có thể khai báo:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

Hoặc Jackson có thể đến từ một starter khác. Ứng dụng không có Jackson vẫn dùng được những phần độc lập với adapter.

Không đặt Jackson ở `test` scope duy nhất nếu production source của adapter cần import `ObjectMapper`: main source phải compile với API đó. Cũng không đặt dependency tùy chọn vào runtime bắt buộc của mọi consumer nếu mục tiêu là cho phép ứng dụng bỏ qua tích hợp.

## 11. Gradle tương đương

Nếu dùng Gradle Java plugin và Spring dependency management, có thể khai báo:

```groovy
plugins {
    id 'java'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

`compileOnly` giúp module compile adapter mà không công bố dependency đó như runtime dependency thông thường cho consumer. `testImplementation` đưa Jackson trở lại test runtime để kiểm tra nhánh có mặt.

Kiểm tra dependency graph:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Kết quả mong đợi:

- Jackson xuất hiện ở compile classpath của module.
- Jackson có trong test runtime để test nhánh tích hợp.
- Consumer không tự nhận Jackson qua dependency runtime của thư viện nếu không có nguồn khác cung cấp.

Nếu thư viện cần expose kiểu Jackson trong public API, `compileOnly` có thể không đủ cho consumer compile. Hãy giữ optional type trong implementation adapter hoặc chọn configuration publication phù hợp với contract thực tế.

## 12. `FilteredClassLoader` là gì?

`FilteredClassLoader` là tiện ích test của Spring Boot trong package:

```java
org.springframework.boot.test.context.FilteredClassLoader
```

Nó tạo một classloader có chủ đích ẩn một class hoặc package khỏi context đang được test. Nhờ đó, test có thể mô phỏng ứng dụng consumer không cài một dependency tùy chọn, dù dependency đó vẫn có trong test runtime classpath để compile và chạy các test khác.

Ví dụ ẩn toàn bộ package Jackson Databind:

```java
new FilteredClassLoader("com.fasterxml.jackson.databind")
```

Hoặc ẩn một class cụ thể:

```java
new FilteredClassLoader(SomeOptionalClient.class)
```

`FilteredClassLoader` chỉ là công cụ kiểm thử. Nó không thay thế việc khai báo dependency đúng scope và không xóa dependency khỏi Maven/Gradle graph. Trong production, optional dependency phải thực sự vắng mặt trên runtime classpath nếu muốn xác nhận consumer không cần cài nó.

## 13. Kiểm thử bằng `ApplicationContextRunner`

`ApplicationContextRunner` tạo ApplicationContext nhỏ cho mỗi test và cho phép thay đổi:

- Property values.
- User configuration.
- Classloader của context.
- Auto-configuration được áp dụng.

Đây là cách phù hợp để kiểm tra condition và bean registration mà không khởi động toàn bộ web server hoặc ứng dụng production.

### 13.1. Cấu trúc test

```text
src/test/java/demo/json/
└── JsonCodecAutoConfigurationTests.java
```

### 13.2. Bộ test bốn tình huống

```java
package demo.json;

import java.util.Map;

import org.junit.jupiter.api.Test;

import demo.json.autoconfigure.JsonCodecAutoConfiguration;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class JsonCodecAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    JsonCodecAutoConfiguration.class
                            )
                    );

    @Test
    void createsJsonCodecWhenJacksonIsPresentAndFeatureIsEnabled() {
        this.runner
                .withPropertyValues("acme.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(JsonCodec.class);

                    String json = context.getBean(JsonCodec.class)
                            .encode(Map.of("name", "Ada"));

                    assertThat(json).isEqualTo("{\"name\":\"Ada\"}");
                });
    }

    @Test
    void skipsOptionalIntegrationWhenJacksonIsAbsent() {
        this.runner
                .withClassLoader(
                        new FilteredClassLoader(
                                "com.fasterxml.jackson.databind"
                        )
                )
                .withPropertyValues("acme.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(JsonCodec.class);
                });
    }

    @Test
    void skipsIntegrationWhenFeatureIsDisabled() {
        this.runner
                .withPropertyValues("acme.json.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(JsonCodec.class);
                });
    }

    @Test
    void applicationProvidedCodecReplacesDefaultCodec() {
        this.runner
                .withPropertyValues("acme.json.enabled=true")
                .withUserConfiguration(UserJsonCodecConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(JsonCodec.class);

                    String json = context.getBean(JsonCodec.class)
                            .encode(Map.of("name", "Ada"));

                    assertThat(json).isEqualTo("custom-json");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserJsonCodecConfiguration {

        @Bean
        JsonCodec customJsonCodec() {
            return value -> "custom-json";
        }
    }
}
```

Test thứ hai là phần quan trọng nhất của bài. Jackson vẫn có trong test dependency graph, nhưng `FilteredClassLoader` ẩn package khỏi ApplicationContext. Nếu optional class bị tham chiếu từ lớp ngoài hoặc một method không được bảo vệ, test có thể thất bại với lỗi class loading. Kết quả mong đợi là context vẫn khởi động và `JsonCodec` mặc định không được đăng ký.

Test thứ tư kiểm tra back-off: ứng dụng cung cấp `JsonCodec` riêng, nên auto-configuration không tạo thêm implementation mặc định.

### 13.3. Chạy test

```bash
mvn test
```

Kết quả mong đợi từ Maven Surefire:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Đây là số test mong đợi cho class test trên. Thời gian chạy và các dòng build khác phụ thuộc Maven/Surefire version.

## 14. Ma trận kết quả

| Tình huống | Jackson visible? | `acme.json.enabled` | User `JsonCodec` | Kết quả |
| --- | --- | --- | --- | --- |
| Tích hợp mặc định | Có | `true` | Không | Có một Jackson-backed codec |
| Thiếu dependency | Không | `true` | Không | Context chạy, không có default codec |
| Tắt feature | Có | `false` | Không | Không có default codec |
| User override | Có | `true` | Có | Chỉ dùng codec của ứng dụng |

Ma trận này tách ba quyết định:

1. Dependency có trên runtime classpath không?
2. Người dùng có bật feature không?
3. Ứng dụng có cung cấp implementation thay thế không?

Một test chỉ kiểm tra “bean có tồn tại” chưa đủ. Hãy assert implementation thực sự được dùng hoặc output của nó để xác nhận wiring đúng.

## 15. Kiểm tra consumer khi dependency thật sự vắng mặt

`FilteredClassLoader` kiểm tra behavior của Spring khi class không thể được nhìn thấy. Ngoài ra, nên có một consumer smoke test với runtime dependency graph không chứa Jackson.

Maven consumer có thể kiểm tra:

```bash
mvn dependency:tree -Dscope=runtime
```

Xác nhận `jackson-databind` không được kéo vào qua module auto-configuration. Sau đó chạy ứng dụng consumer có dependency của thư viện nhưng không khai báo Jackson.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Nếu Jackson vẫn xuất hiện, lần theo dependency nào đưa nó vào. Có thể một starter khác trong ứng dụng đã cung cấp Jackson; điều đó không có nghĩa auto-configuration module bắt buộc dependency.

Một consumer integration test có thể khởi động bằng `@SpringBootApplication`/`@EnableAutoConfiguration`, chỉ thêm artifact thư viện và không thêm Jackson. Test này xác nhận cả dependency publication lẫn registration resource. `ApplicationContextRunner` ở trên truyền auto-configuration class trực tiếp, nên nó kiểm tra condition/wiring chứ chưa chứng minh file `AutoConfiguration.imports` được đóng gói đúng.

## 16. Khi nào nên tách thành module tích hợp riêng?

Nếu optional integration có nhiều class hoặc dependency lớn, nên tách module:

```text
acme/
├── acme-core/
│   └── JsonCodec API và business contract
├── acme-jackson-autoconfigure/
│   ├── JacksonJsonCodec
│   ├── JacksonJsonCodecConfiguration
│   └── AutoConfiguration.imports
├── acme-gson-autoconfigure/
│   └── Gson adapter và registration
└── acme-starter/
    └── Các dependency mà ứng dụng chọn dùng
```

Lợi ích:

- Core không cần biết Jackson hoặc Gson.
- Consumer chỉ thêm adapter phù hợp.
- Optional dependency không rò vào public API của core.
- Mỗi adapter có thể có condition, property và test riêng.
- Nâng version một thư viện tích hợp ít ảnh hưởng module khác.

Nếu chỉ có một adapter nhỏ, một module auto-configuration với optional dependency và nested configuration được bảo vệ có thể đủ. Hãy chọn ranh giới module theo dependency graph và lý do thay đổi, không tách module chỉ vì một class.

## 17. Chẩn đoán khi test thiếu dependency vẫn thất bại

Nếu test với `FilteredClassLoader` vẫn gặp `NoClassDefFoundError`, kiểm tra theo thứ tự:

1. Optional type có xuất hiện trong superclass, interface, field hoặc constructor của outer auto-configuration không?
2. Có method ở outer class trả về hoặc nhận optional type không?
3. `@ConditionalOnClass` có đặt trên configuration class cô lập không?
4. Annotation có dùng `name` thay vì class literal khi cần tránh resolve optional type không?
5. Optional adapter có bị component scan hoặc import ở nơi không được bảo vệ không?
6. Có static initializer nào gọi optional library không?
7. Test có thực sự dùng `withClassLoader(new FilteredClassLoader(...))` trên runner đang khởi tạo configuration không?
8. Có dependency hoặc test setup khác làm optional class được nạp qua một classloader ngoài dự kiến không?

Nếu context khởi động nhưng bean không xuất hiện, bật debug để đọc Condition Evaluation Report:

```bash
java -jar app.jar --debug
```

Tìm condition `OnClassCondition` và property condition của auto-configuration. Báo cáo cho biết nhánh nào match/no-match và thường ghi rõ class bị thiếu.

Phân biệt hai tình huống:

- Class condition no-match là kết quả dự kiến khi dependency tùy chọn vắng mặt.
- Class loading failure là lỗi thiết kế hoặc dependency graph cần xử lý.

Không bắt `Throwable` hoặc `NoClassDefFoundError` rồi bỏ qua để ứng dụng tiếp tục. Làm vậy che giấu lỗi linkage và khiến trạng thái tích hợp khó dự đoán.

## 18. Những lỗi thường gặp

**Lỗi 1 — Chỉ đặt `@ConditionalOnClass` trên `@Bean` method có optional return type.**  
Spring có thể cần phân giải method signature trước khi condition method được áp dụng. Cô lập nhánh optional trong configuration class có class-level condition.

**Lỗi 2 — Đặt optional type trong field của outer auto-configuration.**  
Class ngoài vẫn phụ thuộc optional library khi JVM nạp/introspect. Chuyển tham chiếu vào nhánh được bảo vệ.

**Lỗi 3 — Dùng class literal trong annotation của lớp cần chạy khi class vắng mặt.**  
`ObjectMapper.class` yêu cầu type có thể được phân giải. Với optional class, dùng `name = "..."` trên configuration class phù hợp.

**Lỗi 4 — Nghĩ rằng Maven `optional=true` loại dependency khỏi module hiện tại.**  
Không đúng. Module hiện tại vẫn compile/test với dependency; optional chỉ ngăn truyền dependency đó tự động sang consumer.

**Lỗi 5 — Dùng `test` scope cho dependency mà main source cần compile.**  
Main source không thể import type chỉ có trong test classpath. Dùng Maven optional compile dependency hoặc Gradle compileOnly.

**Lỗi 6 — Test chỉ có nhánh dependency present.**  
Test pass không chứng minh consumer thiếu dependency vẫn khởi động. Thêm `FilteredClassLoader`.

**Lỗi 7 — Chỉ dùng `FilteredClassLoader` rồi bỏ qua dependency graph production.**  
Classloader test mô phỏng class absence; consumer runtime dependency tree vẫn cần được kiểm tra.

**Lỗi 8 — Dùng `@ComponentScan` để tự dò optional adapter.**  
Scan có thể nạp component phụ thuộc optional type ngoài nhánh được bảo vệ. Đăng ký adapter qua configuration có điều kiện.

**Lỗi 9 — Quên `@ConditionalOnMissingBean`.**  
Ứng dụng không thể thay default implementation sạch sẽ và có thể gặp nhiều candidate cùng kiểu.

**Lỗi 10 — Đưa optional type vào public API không có chủ đích.**  
Consumer có thể cần dependency chỉ để compile dù không sử dụng adapter. Giữ contract công khai độc lập với thư viện tùy chọn.

**Lỗi 11 — Cho rằng `ApplicationContextRunner` kiểm tra file registration.**  
Khi dùng `AutoConfigurations.of(...)`, test truyền class trực tiếp. Cần integration test qua `@EnableAutoConfiguration` để kiểm tra discovery.

**Lỗi 12 — Bắt lỗi class loading rồi trả về `null`.**  
Điều này che lỗi và tạo bean ở trạng thái không hợp lệ. Dùng condition để loại nhánh trước khi bean được tạo.

## 19. Checklist review

- [ ] Xác định dependency nào thật sự là optional đối với consumer.
- [ ] Dùng Maven `optional=true` hoặc Gradle configuration phù hợp.
- [ ] Giữ optional type ngoài public API nếu consumer không cần phụ thuộc trực tiếp.
- [ ] Đặt `@ConditionalOnClass` trên configuration class cô lập.
- [ ] Dùng tên class dạng String khi cần bảo vệ optional type.
- [ ] Không để optional type trong outer class field, constructor, superclass hoặc method signature.
- [ ] Tách adapter khỏi business contract.
- [ ] Dùng `@ConditionalOnProperty` cho feature switch khi cần.
- [ ] Dùng `@ConditionalOnMissingBean` để consumer override default.
- [ ] Test khi dependency có mặt.
- [ ] Test khi dependency bị ẩn bằng `FilteredClassLoader`.
- [ ] Test feature disabled.
- [ ] Test user-provided implementation.
- [ ] Kiểm tra runtime dependency graph của consumer.
- [ ] Có integration test discovery và kiểm tra registration resource trong JAR.
- [ ] Đọc Condition Evaluation Report khi condition không match như dự kiến.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một thư viện cần optional integration?  
**Đáp án:** Để consumer chỉ cần thêm dependency của tính năng họ sử dụng; ứng dụng không có thư viện tùy chọn vẫn có thể khởi động và dùng phần độc lập.

**Câu 2.** Maven `<optional>true</optional>` có nghĩa gì?  
**Đáp án:** Dependency vẫn dùng được để compile/test module hiện tại nhưng không tự động được truyền như dependency transitive cho consumer.

**Câu 3.** `@ConditionalOnClass` nên đặt ở đâu để bảo vệ các method tham chiếu optional type?  
**Đáp án:** Trên configuration class riêng/nested static configuration chứa các method đó, để Spring bỏ qua toàn bộ nhánh khi class không có.

**Câu 4.** Vì sao dùng `name = "com.fasterxml.jackson.databind.ObjectMapper"`?  
**Đáp án:** Dùng tên String tránh yêu cầu phân giải class literal khi annotation được đọc trong môi trường có thể thiếu dependency.

**Câu 5.** `FilteredClassLoader` làm gì?  
**Đáp án:** Tạo classloader test ẩn một class hoặc package khỏi ApplicationContext để mô phỏng runtime thiếu dependency.

**Câu 6.** `FilteredClassLoader` có loại dependency khỏi Maven runtime graph không?  
**Đáp án:** Không. Nó chỉ mô phỏng class absence trong test; cần kiểm tra dependency tree của consumer riêng.

**Câu 7.** Khi optional class vắng mặt, kết quả mong đợi là gì?  
**Đáp án:** Condition no-match, optional bean không được tạo và ApplicationContext vẫn khởi động.

**Câu 8.** Vì sao `@ConditionalOnMissingBean(JsonCodec.class)` cần thiết?  
**Đáp án:** Cho phép ứng dụng cung cấp implementation riêng và khiến default codec nhường chỗ.

**Câu 9.** `ApplicationContextRunner` với `AutoConfigurations.of(...)` có kiểm tra imports file không?  
**Đáp án:** Không. Nó đưa class trực tiếp vào runner; cần test discovery qua `@EnableAutoConfiguration` và kiểm tra JAR.

**Câu 10.** Nếu test thiếu dependency ném `NoClassDefFoundError`, nên làm gì?  
**Đáp án:** Tìm optional type bị tham chiếu ngoài configuration class được bảo vệ, sửa ranh giới classloading và giữ lỗi gốc để chẩn đoán.

## 21. Nguyên tắc cần nhớ

- Optional integration chỉ được kích hoạt khi dependency cần thiết có trên runtime classpath.
- Tách public contract khỏi adapter phụ thuộc thư viện bên ngoài.
- Maven `optional=true` và Gradle `compileOnly` giúp kiểm soát dependency được truyền sang consumer.
- Đặt `@ConditionalOnClass` trên configuration class cô lập các method dùng optional type.
- Dùng `name` dạng String để tránh class literal của dependency có thể vắng mặt.
- Không để optional type rò vào outer auto-configuration hoặc public API không cần thiết.
- `FilteredClassLoader` kiểm thử nhánh dependency vắng mặt trong ApplicationContext.
- Test cả dependency present/absent, property disabled và user override.
- Kiểm tra dependency graph consumer ngoài classloader test.
- Phân biệt condition no-match dự kiến với lỗi class loading thực sự.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@ConditionalOnClass`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 API — `FilteredClassLoader`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot 3.3 API — `ApplicationContextRunner`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Apache Maven — Optional Dependencies and Dependency Exclusions](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html)
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
