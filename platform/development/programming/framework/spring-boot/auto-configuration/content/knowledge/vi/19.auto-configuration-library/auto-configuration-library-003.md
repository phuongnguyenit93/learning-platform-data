# Khai báo điều kiện classpath để thư viện tùy chọn không gây lỗi nạp lớp

**Chủ đề:** Spring Boot Auto Configuration  
**Ngữ cảnh:** Thư viện tự cấu hình  
**Mục tiêu:** Thiết kế auto-configuration có thể hoạt động khi một thư viện tùy chọn có mặt và được bỏ qua an toàn khi thư viện đó không có trên runtime classpath. Trọng tâm là vị trí đặt `@ConditionalOnClass`, cách cô lập các tham chiếu tới kiểu tùy chọn và cách kiểm thử bằng classloader có lọc.

## 1. Vấn đề: dependency tùy chọn có thể làm hỏng ứng dụng không sử dụng nó

Giả sử thư viện `acme-json-autoconfigure` hỗ trợ Jackson nếu ứng dụng có `jackson-databind`. Một số ứng dụng muốn dùng tính năng JSON, nhưng ứng dụng khác không muốn thêm Jackson vào dependency graph.

Mong muốn:

- Có Jackson: đăng ký codec dựa trên Jackson.
- Không có Jackson: Spring Boot vẫn khởi động; phần tích hợp JSON tùy chọn được bỏ qua.
- Người dùng có thể cung cấp codec của riêng mình để starter nhường chỗ.
- Các class cấu hình chung của thư viện không buộc mọi ứng dụng phải cài thư viện tùy chọn.

Nếu lớp auto-configuration chính tham chiếu trực tiếp các kiểu chỉ tồn tại khi Jackson được cài, Spring có thể gặp lỗi liên kết lớp khi đọc hoặc introspect cấu hình. Một lỗi như `NoClassDefFoundError` có thể xuất hiện trước khi bean method được gọi. Khi đó ứng dụng không dùng tính năng JSON vẫn bị ảnh hưởng bởi một dependency mà nó không yêu cầu.

Đây là vấn đề **an toàn classpath**. Cần bảo đảm điều kiện kiểm tra sự hiện diện của lớp được đánh giá trước khi Spring/JVM phải nạp phần cấu hình chứa các tham chiếu tới lớp đó.

## 2. `@ConditionalOnClass` và `@ConditionalOnMissingClass`

Spring Boot cung cấp hai class condition chính:

```java
@ConditionalOnClass(SomeOptionalApi.class)
```

Điều kiện khớp khi kiểu được chỉ định có thể được tìm thấy trên classpath.

```java
@ConditionalOnMissingClass("com.vendor.optional.Client")
```

Điều kiện khớp khi kiểu được chỉ định không có trên classpath.

Cả hai có thể dùng để bật/tắt một configuration branch theo dependency thực tế:

| Trạng thái classpath | `@ConditionalOnClass` | `@ConditionalOnMissingClass` |
| --- | --- | --- |
| Có optional API | Match | No match |
| Không có optional API | No match | Match |

Có thể khai báo nhiều lớp. Với `@ConditionalOnClass`, tất cả lớp được yêu cầu phải hiện diện để điều kiện khớp. Với `@ConditionalOnMissingClass`, điều kiện khớp khi các lớp được chỉ định đều vắng mặt.

Ví dụ trực tiếp:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
static class VendorClientConfiguration {
    // Chỉ phần này mới được phép tham chiếu các API của vendor.
}
```

Đây là một nested configuration minh họa; phần thân chỉ được đưa vào khi class condition khớp.

### 2.1. Vì sao class-level condition có thể kiểm tra một lớp chưa có mặt?

Spring Boot đọc annotation metadata của configuration class bằng ASM. Nhờ đọc bytecode metadata, framework có thể xem giá trị `@ConditionalOnClass` và quyết định có nên nạp configuration class hay không, trước khi JVM cần xử lý toàn bộ các tham chiếu kiểu trong class đó.

Vì vậy, với annotation được đặt **trực tiếp trên một `@Configuration` class**, có thể dùng:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(SomeOptionalApi.class)
static class OptionalApiConfiguration {
}
```

Ngay cả khi `SomeOptionalApi` không nằm trên runtime classpath, annotation metadata của class có thể được đọc để điều kiện loại nhánh cấu hình.

Bạn cũng có thể dùng thuộc tính `name` với tên đầy đủ của lớp dưới dạng chuỗi:

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
```

`name` hữu ích khi muốn tránh class literal hoặc khi tạo composed annotation. Đổi sang chuỗi không thay đổi ý nghĩa condition; tên package/class phải chính xác.

**Giới hạn quan trọng:** khả năng đọc metadata bằng ASM không có nghĩa mọi tham chiếu tới lớp tùy chọn ở bất kỳ vị trí nào đều an toàn. Configuration class phải được cô lập để những tham chiếu nguy hiểm chỉ nằm trong nhánh được bảo vệ.

## 3. Bẫy thường gặp: đặt condition trên `@Bean` method có return type tùy chọn

Một cách viết có vẻ hợp lý nhưng không an toàn là:

```java
@AutoConfiguration
public class UnsafeJsonAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
    ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
```

Vấn đề nằm ở chữ ký:

```java
ObjectMapper objectMapper()
```

Để xử lý bean method, Spring cần đọc metadata và kiểu trả về của method. JVM có thể phải nạp lớp hoặc xử lý method references liên quan đến `ObjectMapper` **trước khi** condition ở method được áp dụng. Nếu Jackson không có mặt, điều kiện trên method có thể đến quá muộn để bảo vệ cấu hình khỏi lỗi class loading.

Không nên dựa vào việc method body chưa được gọi để kết luận method đó không thể gây lỗi. Việc introspect chữ ký và metadata đã có thể cần phân giải kiểu.

### 3.1. Cách sửa: chuyển condition lên một nested `@Configuration` riêng

Spring Boot khuyến nghị tách nhánh optional thành một configuration class riêng:

```java
@AutoConfiguration
public class SafeJsonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
    public static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean
        JsonCodec jsonCodec() {
            return new JacksonJsonCodec();
        }
    }
}
```

Điểm quan trọng:

1. Lớp ngoài `SafeJsonAutoConfiguration` chỉ tham chiếu các API luôn có mặt.
2. `JacksonConfiguration` có condition ở **cấp class**.
3. Các lớp/method/field cần Jackson được giữ bên trong nhánh đã được bảo vệ.
4. Bean method trả về `JsonCodec`, một interface ổn định của thư viện, thay vì đưa `ObjectMapper` thành kiểu return công khai.
5. `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp `JsonCodec` riêng để starter nhường chỗ.

Trong code thực tế, mọi tham chiếu tùy chọn cần được cô lập: superclass, interface, field, constructor, parameter, return type, annotation, static initializer và các nested implementation. Đừng chỉ di chuyển một dòng `new ObjectMapper()` mà vẫn để `ObjectMapper` xuất hiện trong chữ ký của configuration class bên ngoài.

### 3.2. Khi nào dùng `value`, khi nào dùng `name`?

Có một khác biệt cần nhớ:

- **Annotation trực tiếp trên configuration class:** `@ConditionalOnClass(SomeOptionalApi.class)` có thể dùng `value`; Spring đọc metadata bằng ASM.
- **Composed/meta-annotation:** khi tạo annotation riêng được gắn `@ConditionalOnClass` hoặc `@ConditionalOnMissingClass`, phải dùng `name`.

Ví dụ composed annotation đúng:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public @interface ConditionalOnJackson {
}
```

Sau đó dùng:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnJackson
static class JacksonConfiguration {
}
```

Không dùng `@ConditionalOnClass(ObjectMapper.class)` trong định nghĩa meta-annotation. Spring Boot không xử lý class literal trong meta-annotation theo cùng cách với annotation trực tiếp trên configuration class; dùng `name` để condition có thể được đọc an toàn.

## 4. Tổ chức auto-configuration cho dependency tùy chọn

Một cấu trúc dễ bảo trì:

```text
acme-json-autoconfigure/
├── pom.xml
└── src/main/
    ├── java/com/acme/json/
    │   ├── JsonCodec.java
    │   ├── ConditionalOnJackson.java
    │   └── autoconfigure/
    │       └── JsonAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Phân tách trách nhiệm:

- **API ổn định của thư viện:** interface như `JsonCodec`, cấu hình chung, property mà ứng dụng có thể sử dụng.
- **Configuration ngoài:** lớp auto-configuration được Spring Boot khám phá; không nhắc tới kiểu Jackson.
- **Configuration nhánh tùy chọn:** nested static class được bảo vệ bằng class condition.
- **Implementation tùy chọn:** các lớp dùng `ObjectMapper` chỉ nằm trong nhánh Jackson.
- **Imports file:** liệt kê lớp auto-configuration cấp cao nhất; không đưa helper nội bộ thành một auto-configuration độc lập nếu không có chủ đích.

Trong Spring Boot 3.x, auto-configuration của thư viện được khám phá qua:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ nội dung:

```text
com.acme.json.autoconfigure.JsonAutoConfiguration
```

Tên class trong file là tên đầy đủ của auto-configuration ngoài. Nested configuration được xử lý khi Spring đọc cấu hình chứa nó; nó không cần được liệt kê như một auto-configuration độc lập.

Auto-configuration nên được nạp thông qua imports file, không nên phụ thuộc vào component scanning của package nội bộ. Điều đó giúp ứng dụng chỉ nhận các cấu hình được starter chủ động công bố.

## 5. Dependency optional trong Maven và Gradle

Class condition và dependency declaration giải quyết hai việc khác nhau:

- Dependency declaration quyết định thư viện nào được đưa vào dependency graph của ứng dụng.
- Class condition quyết định nhánh auto-configuration nào được kích hoạt dựa trên classpath runtime thực tế.

Với Maven, module `autoconfigure` có thể khai báo thư viện tùy chọn như sau:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

`optional=true` có nghĩa dependency này được dùng để biên dịch/test module hiện tại nhưng không tự động truyền tiếp thành dependency bắt buộc cho mọi ứng dụng tiêu thụ module. Nếu ứng dụng muốn dùng nhánh Jackson, ứng dụng hoặc starter tương ứng phải đưa Jackson vào runtime classpath.

Với Gradle, có thể dùng `compileOnly` cho dependency chỉ cần lúc biên dịch module autoconfigure, đồng thời thêm dependency runtime/test phù hợp trong module kiểm thử. Nếu starter riêng muốn cung cấp sẵn Jackson như lựa chọn mặc định, starter đó có thể khai báo dependency runtime tương ứng.

Một cách tổ chức phổ biến khi thư viện có nhiều adapter:

- `acme-core`: API ổn định, không phụ thuộc Jackson.
- `acme-jackson`: implementation tích hợp Jackson.
- `acme-spring-boot-autoconfigure`: auto-configuration có dependency Jackson optional.
- `acme-spring-boot-starter`: starter tổng hợp những dependency được chọn làm mặc định.

Không nên để starter cơ bản luôn kéo theo tất cả thư viện tùy chọn nếu phần lớn ứng dụng không dùng chúng. Tuy nhiên, nếu starter được đặt tên rõ ràng là `acme-jackson-starter`, việc kéo Jackson vào là lựa chọn có chủ đích.

**Dependency optional không tự bảo vệ class loading.** Nếu module autoconfigure có một class bên ngoài tham chiếu `ObjectMapper` trong chữ ký method, field hoặc superclass, việc đánh dấu dependency Maven optional không sửa được lỗi. Cần cả dependency graph phù hợp lẫn cấu trúc class condition an toàn.

## 6. Ví dụ hoàn chỉnh: JSON adapter tùy chọn với Spring Boot 3.3.13

Ví dụ sau dùng **Java 17**, **Spring Boot 3.3.13**, Maven, Jackson và JUnit 5. Mục tiêu là kiểm tra cùng một auto-configuration trong ba tình huống:

1. Jackson có mặt: bean `JsonCodec` dựa trên Jackson được tạo.
2. Jackson bị ẩn khỏi classloader: context vẫn khởi động và nhánh Jackson không tạo bean.
3. Ứng dụng cung cấp `JsonCodec` riêng: bean mặc định nhường chỗ.

### 6.1. `pom.xml`

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
    <artifactId>optional-classpath-autoconfig</artifactId>
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

Jackson có mặt khi biên dịch và chạy test của module này, nhưng Maven không truyền dependency đó sang mọi ứng dụng sử dụng module autoconfigure. `FilteredClassLoader` trong test sẽ mô phỏng một consumer không nhìn thấy Jackson ở runtime.

### 6.2. API luôn có mặt: `JsonCodec.java`

```java
package demo;

import java.util.Map;

public interface JsonCodec {
    String encode(Map<String, Object> value);
}
```

Interface này không tham chiếu Jackson. Nó là kiểu ổn định mà các service khác trong ứng dụng có thể sử dụng dù implementation cụ thể là Jackson hay do người dùng tự cung cấp.

### 6.3. Composed condition: `ConditionalOnJackson.java`

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public @interface ConditionalOnJackson {
}
```

Vì `@ConditionalOnJackson` là meta-annotation, nó dùng `name` để Spring Boot đọc tên lớp tùy chọn dưới dạng chuỗi.

### 6.4. Auto-configuration: `JsonAutoConfiguration.java`

```java
package demo;

import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class JsonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnJackson
    public static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(JsonCodec.class)
        JsonCodec jsonCodec() {
            return new JacksonJsonCodec();
        }

        static final class JacksonJsonCodec implements JsonCodec {

            private final ObjectMapper objectMapper = new ObjectMapper();

            @Override
            public String encode(Map<String, Object> value) {
                try {
                    return this.objectMapper.writeValueAsString(value);
                }
                catch (JsonProcessingException ex) {
                    throw new IllegalArgumentException(
                            "Cannot encode the supplied value as JSON", ex);
                }
            }
        }
    }
}
```

Lớp ngoài `JsonAutoConfiguration` không dùng `ObjectMapper` trong field, superclass, interface hoặc method signature. Các tham chiếu Jackson chỉ nằm bên trong nhánh `JacksonConfiguration` đã được class-level condition bảo vệ.

Method `jsonCodec()` trả về `JsonCodec`, là interface luôn có mặt. Implementation cụ thể `JacksonJsonCodec` mới tạo `ObjectMapper`. `@ConditionalOnMissingBean(JsonCodec.class)` cho phép bean do ứng dụng cung cấp làm auto-configuration back off.

### 6.5. Đăng ký trong `AutoConfiguration.imports`

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
demo.JsonAutoConfiguration
```

Ứng dụng Spring Boot sẽ khám phá auto-configuration ngoài qua file này. Không cần liệt kê `JacksonConfiguration` trong imports vì đó là nested configuration được xử lý bên trong auto-configuration cha.

### 6.6. Test: `JsonAutoConfigurationTest.java`

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class JsonAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(JsonAutoConfiguration.class));

    @Test
    void jacksonOnClasspathRegistersJsonCodec() {
        this.contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(JsonCodec.class);

            String json = context.getBean(JsonCodec.class)
                    .encode(Map.of("status", "ok"));

            assertThat(json).isEqualTo("{\"status\":\"ok\"}");
        });
    }

    @Test
    void missingJacksonSkipsOptionalConfigurationWithoutFailure() {
        this.contextRunner
                .withClassLoader(new FilteredClassLoader("com.fasterxml.jackson"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(JsonCodec.class);
                });
    }

    @Test
    void userCodecMakesJacksonDefaultBackOff() {
        this.contextRunner
                .withUserConfiguration(UserJsonCodecConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(JsonCodec.class);
                    assertThat(context).hasBean("customJsonCodec");
                    assertThat(context).doesNotHaveBean("jsonCodec");

                    String result = context.getBean(JsonCodec.class)
                            .encode(Map.of("status", "ok"));

                    assertThat(result).isEqualTo("custom-codec");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserJsonCodecConfiguration {

        @Bean
        JsonCodec customJsonCodec() {
            return value -> "custom-codec";
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Mã test không in stdout tùy biến. Maven Surefire có thể hiển thị thêm log tùy phiên bản và môi trường.

Ba test chứng minh:

- **Classpath có Jackson:** nested configuration match và tạo đúng một `JsonCodec`; kết quả encode là `{"status":"ok"}`.
- **Classpath không có Jackson:** `FilteredClassLoader` ẩn package `com.fasterxml.jackson`; context vẫn không fail và không có bean `JsonCodec` mặc định.
- **Có bean do ứng dụng cung cấp:** `@ConditionalOnMissingBean(JsonCodec.class)` không khớp, implementation mặc định không được đăng ký và bean custom được dùng.

`FilteredClassLoader` mô phỏng consumer thiếu dependency mà không cần tạo một Maven module thứ hai. Khi phát hành thư viện thực, vẫn nên kiểm thử artifact đã đóng gói trong một consumer module không khai báo Jackson để phát hiện các tham chiếu ngoài nhánh bảo vệ.

## 7. `@ConditionalOnMissingClass`: khi muốn có nhánh thay thế

Đôi khi không có thư viện tùy chọn vẫn cần một implementation khác. Có thể tạo một nhánh riêng được bảo vệ bằng `@ConditionalOnMissingClass`:

```java
@AutoConfiguration
public class TransportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class VendorConfiguration {
        @Bean
        Transport vendorTransport() {
            return new VendorTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("com.vendor.sdk.Client")
    static class BasicConfiguration {
        @Bean
        Transport basicTransport() {
            return new BasicTransport();
        }
    }
}
```

Đây là snippet minh họa cần các interface/class `Transport`, `VendorTransport`, `BasicTransport` của thư viện. Nhánh vendor được phép tham chiếu SDK tùy chọn; nhánh basic chỉ dùng các kiểu luôn có mặt.

Hai điều kiện classpath giúp chọn nhánh theo dependency. Nếu cả hai nhánh tạo cùng một contract, hãy xác định rõ quy tắc back-off và bảo đảm không có condition phụ khiến cả hai cùng đăng ký hoặc cùng bị loại ngoài ý muốn.

Nếu không có implementation thay thế hợp lý, bỏ qua nhánh optional hoàn toàn cũng là một thiết kế đúng. Đừng tạo một bean giả chỉ để ứng dụng có vẻ khởi động thành công nhưng rồi ném exception ở mọi lần sử dụng.

## 8. Những lỗi thiết kế thường gặp

### Lỗi 1: Condition nằm trên method nhưng kiểu optional xuất hiện trong return type

`@Bean ObjectMapper objectMapper()` có thể làm JVM phải xử lý `ObjectMapper` trước khi condition method bảo vệ. Chuyển condition lên nested configuration.

### Lỗi 2: Lớp ngoài vẫn giữ một tham chiếu optional

Di chuyển `@Bean` method nhưng quên rằng lớp ngoài còn một field, constructor parameter, superclass hoặc annotation tham chiếu thư viện optional. Class condition của nested class không bảo vệ các tham chiếu đó. Hãy giữ outer configuration chỉ phụ thuộc API ổn định.

### Lỗi 3: Dùng `value` trong composed annotation

`@ConditionalOnClass(OptionalApi.class)` trên một annotation tự tạo không có cùng cơ chế metadata an toàn như annotation trực tiếp. Trong meta-annotation, dùng `name = "fully.qualified.ClassName"`.

### Lỗi 4: Cho rằng Maven optional tự giải quyết lỗi nạp lớp

`<optional>true</optional>` ngăn dependency truyền tiếp tự động. Nó không bảo vệ một class có bytecode/signature tham chiếu tới kiểu không tồn tại. Vẫn phải đặt class condition đúng vị trí.

### Lỗi 5: Đưa dependency optional vào starter mặc định

Nếu starter cơ bản luôn kéo toàn bộ adapter, class condition vẫn match vì dependency có mặt, và người dùng phải nhận một dependency không cần thiết. Phân chia starter/adapter theo nhu cầu sử dụng.

### Lỗi 6: Chỉ test trường hợp dependency có mặt

Test chạy trên classpath phát triển thường có mọi thư viện cần thiết, nên lỗi optional dependency không lộ ra. Bắt buộc test classpath thiếu bằng `FilteredClassLoader` hoặc consumer module riêng.

### Lỗi 7: Chỉ ẩn một class nhưng package vẫn có các kiểu bắt buộc khác

Một integration có thể phụ thuộc nhiều class trong cùng một thư viện. Ẩn package của vendor trong `FilteredClassLoader` thường mô phỏng đầy đủ hơn; cũng có thể ẩn nhiều class cụ thể khi test chỉ nhắm tới một loại.

### Lỗi 8: Dùng `@ConditionalOnClass` để che lỗi phiên bản

Class có mặt không đồng nghĩa mọi method/field mà code cần đều có trong phiên bản thư viện đó. `@ConditionalOnClass` kiểm tra sự hiện diện của class, không kiểm tra toàn bộ binary compatibility. Nếu cần API mới, phải xác định thêm version/capability phù hợp hoặc bắt lỗi linkage trong quá trình phát triển và kiểm thử.

### Lỗi 9: Expose optional type trong API công khai không cần thiết

Nếu public interface của starter trả về `ObjectMapper`, mọi consumer muốn dùng interface đó có thể cần Jackson. Ưu tiên kiểu trung lập do thư viện sở hữu như `JsonCodec`; để implementation tùy chọn sử dụng `ObjectMapper` bên trong.

## 9. Annotation processor và metadata điều kiện

Spring Boot có thể tạo file:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Thông qua `spring-boot-autoconfigure-processor`, các condition trên auto-configuration có thể được thu thập thành metadata để Spring Boot lọc sớm những cấu hình không match, cải thiện startup time.

Đây là tối ưu hóa quá trình khám phá auto-configuration. Nó **không thay thế** class-level condition trong source code và không sửa được cấu trúc lớp có optional type trong chữ ký nguy hiểm. Thiết kế đúng phải hoạt động an toàn cả khi framework phải xử lý configuration metadata thông thường.

Với Maven Compiler Plugin 3.12.0 trở lên, tài liệu Spring Boot 3.3 hướng dẫn cấu hình `spring-boot-autoconfigure-processor` trong `annotationProcessorPaths`. Với Gradle, khai báo processor trong configuration `annotationProcessor`.

Không nhầm file này với `META-INF/spring-configuration-metadata.json`: file thứ nhất phục vụ lọc condition của auto-configuration; file thứ hai mô tả property để IDE/tooling gợi ý cấu hình.

## 10. Quy trình chẩn đoán `NoClassDefFoundError` trong starter

Khi ứng dụng không dùng tính năng optional nhưng vẫn lỗi nạp lớp:

1. Đọc stacktrace và tìm class đầu tiên bị thiếu. Xác định đó là API của dependency nào.
2. Tìm class auto-configuration, configuration hoặc bean method có tham chiếu kiểu đó.
3. Kiểm tra tham chiếu nằm ở outer configuration hay nested branch đã được bảo vệ.
4. Kiểm tra optional type có xuất hiện trong superclass, interface, field, constructor/method signature hoặc annotation của lớp ngoài không.
5. Kiểm tra `@ConditionalOnClass` có ở class-level hay chỉ ở `@Bean` method.
6. Nếu condition nằm trong composed annotation, xác nhận nó dùng `name`.
7. Kiểm tra dependency graph của consumer: optional library có bị starter kéo vào ngoài ý muốn không?
8. Dùng `ApplicationContextRunner` và `FilteredClassLoader` để tái hiện đúng classpath thiếu.
9. Thử artifact đã đóng gói trong một consumer tối giản. Test trên module source có đủ dependency có thể che giấu lỗi transitive/runtime.

Phân biệt một số tình huống:

| Dấu hiệu | Ý nghĩa có thể có | Hướng kiểm tra |
| --- | --- | --- |
| `NoClassDefFoundError` khi parse configuration | Có tham chiếu tới lớp không có ở runtime | Outer config, method signature, nested configuration |
| `ClassNotFoundException` từ reflection | Code chủ động tải lớp theo tên nhưng classloader không tìm thấy | Tên lớp, dependency, classloader |
| `NoSuchMethodError` | Class tồn tại nhưng version runtime thiếu method mà code đã compile against | Dependency mediation, version alignment |
| `NoSuchFieldError` | Class tồn tại nhưng field không tương thích | Version và binary compatibility |
| Condition no-match nhưng context chạy bình thường | Optional branch bị bỏ qua như thiết kế | Xác nhận tính năng có cần bật trong môi trường này không |
| Condition match rồi bean creation thất bại | Dependency đã hiện diện nhưng implementation/constructor/init thất bại | Root cause, version, config và runtime behavior |

Không nên bắt `Throwable` để bỏ qua tất cả lỗi classloading. Cách đó có thể che giấu `LinkageError`, bug thực thi hoặc dependency bị lệch version. Hãy sửa cấu trúc auto-configuration và dependency contract.

## 11. Checklist review trước khi phát hành

- [ ] Auto-configuration ngoài chỉ dùng các kiểu luôn có mặt.
- [ ] Mỗi optional integration nằm trong nested static `@Configuration` riêng.
- [ ] `@ConditionalOnClass`/`@ConditionalOnMissingClass` nằm trên configuration class bảo vệ nhánh.
- [ ] Không để optional type xuất hiện trong chữ ký method/class bên ngoài nhánh.
- [ ] Meta-annotation dùng `name`, không dùng class literal trong `value`.
- [ ] Dependency của optional library không bị truyền tiếp vô điều kiện.
- [ ] Starter riêng chỉ kéo optional dependency khi đó là lựa chọn sản phẩm có chủ đích.
- [ ] `AutoConfiguration.imports` liệt kê đúng auto-configuration cấp cao.
- [ ] Test classpath có thư viện, classpath thiếu thư viện và user bean override.
- [ ] Kiểm thử consumer với artifact đã đóng gói, không chỉ chạy test trong module phát triển.
- [ ] Nếu dùng annotation processor, xác nhận metadata được sinh nhưng không phụ thuộc nó để che lỗi thiết kế.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@ConditionalOnClass(OptionalClient.class)` trên một `@Configuration` class có thể hoạt động dù `OptionalClient` không có trong runtime classpath?  
**Đáp án:** Spring Boot đọc annotation metadata bằng ASM trước khi nạp configuration class; condition có thể loại lớp trước khi JVM cần phân giải các tham chiếu bên trong.

**Câu 2.** Vì sao `@ConditionalOnClass` trên `@Bean` method có return type `OptionalClient` không phải cách an toàn?  
**Đáp án:** Spring/JVM có thể cần nạp hoặc introspect method signature trước khi condition trên method được đánh giá.

**Câu 3.** Pattern nên dùng cho optional integration là gì?  
**Đáp án:** Đặt condition trên nested static `@Configuration(proxyBeanMethods=false)` riêng, rồi giữ các method và implementation tham chiếu optional API bên trong nhánh đó.

**Câu 4.** Khi viết composed annotation có `@ConditionalOnClass`, nên dùng thuộc tính nào?  
**Đáp án:** `name`, vì class literal `value` trong meta-annotation không được xử lý theo cơ chế metadata an toàn tương tự annotation trực tiếp.

**Câu 5.** `optional=true` trong Maven có thay thế class condition không?  
**Đáp án:** Không. Maven optional kiểm soát việc truyền dependency; class condition kiểm soát nhánh cấu hình theo runtime classpath.

**Câu 6.** Làm sao kiểm thử rằng ứng dụng thiếu Jackson vẫn khởi động?  
**Đáp án:** Dùng `ApplicationContextRunner.withClassLoader(new FilteredClassLoader("com.fasterxml.jackson"))`, rồi assert context không fail và bean thuộc nhánh Jackson không tồn tại.

**Câu 7.** Nếu class có mặt nhưng thiếu method mà integration cần thì `@ConditionalOnClass` có phát hiện không?  
**Đáp án:** Không. Condition này kiểm tra sự hiện diện của class, không bảo đảm binary compatibility của toàn bộ API.

## 13. Nguyên tắc cần nhớ

1. Kiểm tra dependency tùy chọn bằng class condition ở **cấp configuration class**.
2. Đưa toàn bộ tham chiếu tới optional type vào nested configuration đã được bảo vệ.
3. Không dựa vào method-level condition để cứu một return type hoặc method signature đã tham chiếu lớp vắng mặt.
4. Dùng `value` cho annotation trực tiếp trên class khi phù hợp; dùng `name` trong composed/meta-annotation.
5. Tách dependency optional ở Maven/Gradle khỏi dependency mặc định của starter.
6. Kiểm thử cả hai trạng thái classpath bằng `FilteredClassLoader`.
7. Dùng API trung lập cho contract chung, để adapter tùy chọn phụ thuộc implementation cụ thể.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration, Class Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@ConditionalOnClass`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 API — `@ConditionalOnMissingClass`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html)
- [Spring Boot 3.3 API — `FilteredClassLoader`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot 3.3 API — `ApplicationContextRunner`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
