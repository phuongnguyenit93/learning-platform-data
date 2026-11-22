# Rủi ro đặt điều kiện trên @Bean có kiểu trả về không tồn tại

> **Chủ đề:** Spring Boot auto-configuration → Điều kiện classpath.  
> **Nền tảng ví dụ:** Java 17, Spring Boot 3.3.x, Spring Framework 6.1; project Maven mẫu dùng Spring Boot **3.3.13**.  
> **Trọng tâm:** vì sao `@ConditionalOnClass` đặt ngay trên một `@Bean` method có **kiểu trả về thuộc dependency optional** không phải biện pháp bảo vệ an toàn, và cách cô lập phương thức đó trong một `@Configuration` được bảo vệ **ở cấp lớp**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **có lớp trên compile classpath** với **có lớp ở runtime classpath** và **ClassLoader có thể nạp lớp đó**.
2. Giải thích tại sao JVM hoặc Spring có thể phải xem **method signature** trước khi điều kiện trên `@Bean` method được áp dụng.
3. Nhận diện các lỗi `NoClassDefFoundError`, `TypeNotPresentException`, `ClassNotFoundException` và lỗi kiểu “Failed to introspect Class”, thay vì quy mọi trường hợp về `@ConditionalOnClass` không match.
4. Viết cấu hình sai để hiểu rủi ro, rồi sửa bằng **nested static `@Configuration(proxyBeanMethods = false)` có `@ConditionalOnClass` ở cấp lớp**.
5. Thiết kế class optional không xuất hiện trong chữ ký của các `@Bean` thuộc configuration luôn được phân tích.
6. Dùng `ApplicationContextRunner` + `FilteredClassLoader` kiểm thử tình huống dependency bị ẩn khỏi classpath, và phân biệt lỗi khởi tạo bean với lỗi class loading lúc phân tích.
7. Vận dụng đúng cơ chế này trong starter hoặc module autoconfigure có tích hợp SDK optional.

**Kết luận nền tảng:** Một điều kiện đặt **trên phương thức** không bảo đảm Spring/JVM sẽ chưa xem xét kiểu trả về của chính phương thức đó. Nếu kiểu trả về không tồn tại ở runtime, cấu hình có thể lỗi **trước khi** điều kiện method-level kịp bảo vệ. Hãy chuyển condition sang một **configuration class riêng** hoặc nested static configuration để Spring có cơ hội đánh giá metadata ở cấp lớp trước khi phân tích các `@Bean` signatures bên trong.

## 2. Một ví dụ tưởng đúng nhưng nguy hiểm

Giả sử thư viện của bạn tích hợp một codec từ SDK tùy chọn:

```text
com.vendor.codec.OptionalCodec
```

Khi SDK có mặt, bạn muốn tạo bean; khi SDK không có, ứng dụng chỉ bỏ qua tính năng codec và tiếp tục chạy.

Một đoạn code rất dễ viết:

```java
// ANTI-PATTERN: fragment minh họa, không phải file Java độc lập.
@AutoConfiguration
public class CodecAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
    com.vendor.codec.OptionalCodec optionalCodec() {
        return new com.vendor.codec.OptionalCodec();
    }
}
```

**Vấn đề không nằm ở cú pháp của annotation.** `@ConditionalOnClass` cho phép dùng tên class ở dạng string. Nhưng **chữ ký trả về** của method vẫn chứa `OptionalCodec`. Khi Spring đọc một `@Configuration` class và xác định các factory methods, framework/JVM có thể cần nạp, phản chiếu, phân giải hoặc dự đoán type từ method signature. Nếu `OptionalCodec` vắng mặt, một đường xử lý có thể ném lỗi **trước thời điểm điều kiện trên method được dùng để quyết định bỏ qua bean**.

Không phải mọi JVM và mọi đường code đều lập tức ném cùng một lỗi. Tính phân giải class là một phần có thể bị trì hoãn tùy ngữ cảnh, và Spring Boot có một số bước đọc annotation bằng metadata. Nhưng **an toàn của thư viện không được phụ thuộc vào may rủi rằng method-level condition sẽ luôn được đánh giá trước khi JVM xử lý kiểu trả về**.

### 2.1. Ba điều thường bị đánh đồng

| Phát biểu | Đúng hay sai? |
| --- | --- |
| “Dependency codec có ở compile time” | Chỉ chứng minh source module **biên dịch được** |
| “`@ConditionalOnClass` đặt trên method sẽ luôn giúp class đó nạp an toàn khi codec vắng mặt” | **Không thể bảo đảm** |
| “Cấu hình class-level có thể được Spring Boot xét bằng annotation metadata trước khi nạp class chứa signature optional” | **Đây là kỹ thuật bảo vệ được khuyến nghị** |
| “`@ConditionalOnClass` match là codec bean chắc chắn khởi tạo thành công” | Sai: còn điều kiện bean, factory, linkage, dependency và lifecycle |
| “Giấu kiểu trả về bằng `Object` là một cách sửa hoàn hảo” | Sai: có thể phá type metadata, dependency injection và các bean conditions |

**Lưu ý:** Việc annotation có `name = "..."` chỉ tránh tham chiếu trực tiếp ở **giá trị annotation**. Nó **không xóa** tham chiếu `OptionalCodec` khỏi **return descriptor** của `@Bean` method.

## 3. Điều gì xảy ra trước khi một bean được tạo?

Trong Spring Boot, thứ tự tư duy hữu ích là:

```text
Classpath / JARs / ClassLoader
       |
       v
Khám phá class auto-configuration qua
META-INF/spring/...AutoConfiguration.imports
       |
       v
Spring đọc metadata cấu hình và @Conditional
       |
       v
Spring xác định @Bean factory methods / return types
       |
       v
Đăng ký các bean definitions hợp lệ
       |
       v
Giải quyết dependencies và khởi tạo bean instances
```

Đây là **sơ đồ khái niệm**, không phải lời hứa mọi đường thực thi đều diễn ra theo đúng năm stack frames độc lập. Đặc biệt, Spring có thể đọc metadata class bằng ASM mà chưa nạp nó, nhưng một số thao tác xử lý factory methods, introspection, type prediction hoặc resolution có thể đi qua reflection/JVM loading.

### 3.1. Vì sao Spring phải quan tâm đến return type của @Bean?

Return type của một factory method rất quan trọng để Spring:
- Suy luận **bean type** trước khi có instance;
- Quyết định một `@Autowired` injection point có ứng viên phù hợp không;
- Áp dụng `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` dựa trên type;
- Xử lý `@Primary`, qualifiers, generics và factory-method metadata;
- Tính bean definitions, wiring và các chính sách autoconfiguration trước khi chạy method.

Ví dụ:

```java
@Bean
OptionalCodec optionalCodec() {
    return new VendorCodec();
}
```

Để hiểu bean này có type gì, Spring cần xử lý thông tin về `OptionalCodec`. Nếu type được nêu trong signature không có ở runtime, vấn đề có thể xuất hiện ngay **lúc introspection**, không phải lúc gọi body `new VendorCodec()`.

### 3.2. Tại sao annotation ở method không đủ sớm?

Một method-level condition có thể đúng logic:

```text
Nếu OptionalCodec có trong classpath -> tạo bean
Nếu không -> bỏ qua bean
```

Nhưng để **đến** được nơi đánh giá condition method-level, hệ thống có thể đã phải xử lý một class chứa method signature tham chiếu `OptionalCodec`. Tức là trình tự thực tế có thể là:

```text
Load hoặc introspect configuration class
      |
      +--> Resolve return type OptionalCodec
              |
              +--> Class không có -> lỗi linkage/introspection
      |
      +--> Chưa đến lúc áp dụng điều kiện trên @Bean
```

Bởi vậy, hãy **bảo vệ ở lớp chứa method**: nếu class không hiện diện, Spring có thể loại configuration dựa trên metadata lớp, không cần phân tích phương thức có return type thiếu.

## 4. Tách compile classpath và runtime classpath

“SDK tùy chọn” không có nghĩa Java source có thể dùng type SDK mà không cần compile dependency.

- **Compile classpath:** compiler cần type `OptionalCodec` để kiểm tra return type, constructor, method calls.
- **Runtime classpath:** ứng dụng thực thi chỉ thấy những JAR thực sự được cung cấp lúc chạy.
- **Test classpath:** thường rộng hơn production; SDK có thể hiện diện trong test khiến lỗi chỉ nổ khi deploy.
- **ClassLoader visibility:** class có trong một JAR nào đó vẫn không nhất thiết được loader của ứng dụng nhìn thấy (isolation, plugin loader, server loader...).

Ví dụ:

```text
Library module biên dịch với SDK      -> OK
Library artifact phát hành             -> OK
Consumer không kéo SDK ở runtime       -> OptionalCodec vắng
Spring cố phân giải @Bean return type  -> có nguy cơ lỗi
```

Trong Maven, `<optional>true</optional>` làm dependency không tự động truyền transitively đến consumer qua cạnh đó. Nó **không có nghĩa dependency biến mất khỏi runtime của chính module khi bạn chạy module đó**. Trong Gradle, `compileOnly` không được đưa vào runtime classpath của source set theo cách thông thường. Mô hình packaging thực tế cần được kiểm tra qua dependency graph và artifact cuối.

**Tình huống kiểm thử không nên bỏ qua:** test suite chạy trên classpath có SDK rồi tất cả pass, nhưng production consumer không cài SDK. Đây là lý do phải mô phỏng vắng mặt bằng `FilteredClassLoader` hoặc một consumer module thực sự không có SDK.

## 5. Cơ chế đúng: bảo vệ một @Configuration class riêng

Spring Boot khuyến nghị đặt `@ConditionalOnClass` trên **configuration class** thay vì chỉ trên `@Bean` method mà return type mang SDK tùy chọn.

Mẫu cấu trúc:

```java
@AutoConfiguration
public class AppAutoConfiguration {

    // Các bean cốt lõi không phụ thuộc SDK.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
    static class OptionalCodecConfiguration {

        @Bean
        com.vendor.codec.OptionalCodec optionalCodec() {
            // Tạo codec thật nếu SDK hiện diện.
            return ...;
        }
    }
}
```

Đây là **mã giả minh họa**, không compile độc lập do type vendor và `return ...` chưa định nghĩa. Ví dụ chạy được ở mục 8 dùng một `OptionalCodec` tự định nghĩa để tránh phụ thuộc SDK thương mại.

**Tại sao cấu trúc này an toàn hơn?**

1. Cấu hình ngoài `AppAutoConfiguration` không cần để lộ optional return type trong bất cứ `@Bean` method nào của nó.
2. Nested configuration có `@ConditionalOnClass` **ở mức class**.
3. Spring có thể đọc metadata của nested class bằng ASM và thấy điều kiện không match **trước khi cần nạp / phản chiếu phương thức bên trong**.
4. Khi SDK vắng mặt, toàn bộ nhánh optional được bỏ qua; các bean cốt lõi ở configuration ngoài vẫn có thể được đăng ký.
5. Khi SDK hiện diện, Spring xét tiếp các điều kiện bean/property và tạo adapter như bình thường.

### 5.1. Tại sao phải là static nested class?

Một **static nested configuration** là một class độc lập về mặt JVM, không cần implicit reference đến instance của outer class. Đây là ranh giới có chủ đích giúp Spring quét metadata, đánh giá condition của nested class và tránh phụ thuộc ngầm vào outer instance.

Không nên dùng một inner class không static cho auto-configuration guard; nó mang theo tham chiếu enclosing instance và khiến lifecycle/configuration processing phức tạp hơn.

### 5.2. Khi nào dùng separate top-level configuration?

Nếu nhánh optional có nhiều bean, nhiều điều kiện hoặc cần phát hành như một integration lớn, có thể dùng một class riêng:

```java
// Mã minh họa về tổ chức; import và implementation bị lược bỏ.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
public class VendorCodecAutoConfiguration {

    @Bean
    OptionalCodec optionalCodec() {
        return ...;
    }
}
```

Khai báo `VendorCodecAutoConfiguration` như candidate trong `AutoConfiguration.imports`. Class-level guard vẫn bảo vệ **return type bên trong chính class đó**. Với nhiều feature độc lập, tách top-level auto-configuration còn giúp exclude và debug theo từng feature.

Với một integration nhỏ là phần con của tính năng lớn, nested `@Configuration(proxyBeanMethods = false)` là lựa chọn gọn và đúng ranh giới.

## 6. Annotation class-valued và name-valued khác nhau thế nào?

Spring Boot `@ConditionalOnClass` hỗ trợ hai cách:

```java
@ConditionalOnClass(value = OptionalCodec.class)
```

```java
@ConditionalOnClass(name = "com.example.optional.OptionalCodec")
```

Hai đoạn là **fragments để đặt ở class-level**, không phải file Java độc lập.

Khi trực tiếp gắn lên `@Configuration` class, Spring Boot có thể đọc metadata của annotation bằng ASM trước khi nạp class, nên `value` dạng class literal cũng được hỗ trợ an toàn trong trường hợp khuyến nghị này. Tuy nhiên:
- Khi dùng **meta-annotation / composed annotation** tự định nghĩa, dạng `name` thường dễ tránh các vấn đề do tham chiếu class lúc xử lý annotation; cần kiểm tra contract của composition.
- Khi module auto-configuration không muốn yêu cầu import trực tiếp optional class trong đoạn annotation, `name` cho phép viết tên đầy đủ dạng string.
- Dù dùng `value` hay `name`, **đừng để optional type lọt vào signature của một class luôn được nạp**.

### 6.1. Điều gì không được phép kết luận?

Không nên nói “Dùng `name` trên `@Bean` là hoàn toàn an toàn”; rủi ro vốn nằm ở **signature của method**.

Cũng không nên nói “Mọi việc tham chiếu optional class đều lập tức gây lỗi khi class loaded”; JVM có cơ chế lazy resolution. Vấn đề là **không thể bảo đảm** Spring không introspect/signature-resolve trước khi condition của method được xử lý.

### 6.2. Vì sao @ConditionalOnMissingClass không thay thế giải pháp này?

`@ConditionalOnMissingClass` dùng để bật một cấu hình khi một class **vắng mặt**; còn bài này muốn tạo codec khi class **hiện diện**. Đổi sang MissingClass vừa sai logic, vừa không bảo vệ các signature unsafe nếu đặt không đúng tầng.

## 7. Không chỉ return type: còn parameter, extends và field

Return type là điểm nổi bật vì Spring cần bean type metadata, nhưng các tham chiếu optional khác cũng có thể làm cấu hình không an toàn:

```java
// Các fragment CÓ RỦI RO nếu SDK không hiện diện.
@Bean
CoreClient client(com.vendor.codec.OptionalCodec codec) {
    return ...;
}
```

```java
// Cấu hình luôn được nạp và kế thừa optional SDK class.
class UnsafeConfiguration extends com.vendor.sdk.BaseConfiguration {
}
```

```java
// Field type tùy chọn ở class cấu hình luôn được phân tích.
private com.vendor.codec.OptionalCodec codec;
```

```java
// Tham chiếu static initialization có thể gây lỗi khi class init.
private static final Object CLIENT =
        com.vendor.sdk.Factory.create();
```

Tất cả là **mã minh họa không độc lập compile** vì package vendor giả định, body chưa đầy đủ. Nguyên tắc chung là **giữ ranh giới optional dependency bên trong class đã được guard**.

### 7.1. Một trường hợp tinh tế: method return type trung tính

Nếu `@Bean` trả về một interface lõi không phụ thuộc SDK, như `CodecPort`, thì signature bên ngoài không trực tiếp chứa `OptionalCodec`. Tuy vậy, nếu body, method parameters, fields hoặc static initialization trực tiếp sử dụng class optional, bạn vẫn phải thiết kế guard đúng chỗ. Ngoài ra, việc đổi return type tùy tiện sang `Object` để né JVM có thể làm Spring mất thông tin bean type cần để autowire và đánh giá `@ConditionalOnMissingBean`.

Sửa **ranh giới classpath**, không chữa bằng cách khai báo return type chung chung làm hỏng API.

## 8. Demo runnable Java 17 / Spring Boot 3.3.13

Demo dưới đây thực sự có:
- **Core service:** luôn dùng được, dù codec tùy chọn bị ẩn.
- **Optional codec:** chỉ được tạo khi `OptionalCodec` hiện diện với loader đang xét.
- **Safe nested configuration:** chứa `@Bean` có return type `OptionalCodec` và được bảo vệ bằng `@ConditionalOnClass` **ở cấp class**.
- **Test FilteredClassLoader:** mô phỏng `OptionalCodec` vắng khỏi runtime mà không bắt buộc tạo nhiều Maven modules.

**Giới hạn thực nghiệm:** SDK demo được đóng chung project để code compile đơn giản, nên khi chạy `mvn spring-boot:run` thông thường, `OptionalCodec` có mặt. Chỉ khi dùng `FilteredClassLoader` trong test mới giả lập thiếu class. Để chứng minh hẳn trường hợp JAR optional **không** nằm trong runtime production, cần thêm một consumer project/module có graph dependency tương ứng.

### 8.1. Cấu trúc file

```text
optional-signature-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   ├── core/CoreService.java
    │   │   ├── optional/OptionalCodec.java
    │   │   └── autoconfigure/ExampleAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/autoconfigure/
            └── ExampleAutoConfigurationTest.java
```

Điểm bố trí package: main application ở `com.example.app`; auto-configuration ở `com.example.autoconfigure`. Component scan mặc định của app không tự quét class auto-configuration; danh sách imports là đường khám phá chủ động.

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
    <artifactId>optional-signature-demo</artifactId>
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

Dự án chỉ cần JDK 17+ và Maven 3.x. Hai starter trên cấp đủ dependency cơ bản và test.

### 8.3. Core service độc lập với SDK

Tạo `src/main/java/com/example/core/CoreService.java`:

```java
package com.example.core;

@FunctionalInterface
public interface CoreService {
    String reply(String input);
}
```

Interface này không import class optional. Dù `OptionalCodec` bị ẩn, phần core vẫn có thể hoạt động.

### 8.4. Optional SDK giả lập để biên dịch

Tạo `src/main/java/com/example/optional/OptionalCodec.java`:

```java
package com.example.optional;

@FunctionalInterface
public interface OptionalCodec {
    String encode(String text);
}
```

Trong sản phẩm thật, interface này sẽ nằm trong dependency SDK. Ở demo, ta đưa nó vào source để có thể compile cả method signature. `FilteredClassLoader` sẽ được dùng **trong test** để tạo điều kiện "vắng runtime" mà không cần chuyển đổi toàn bộ dependency graph.

### 8.5. Auto-configuration an toàn bằng nested class

Tạo `src/main/java/com/example/autoconfigure/ExampleAutoConfiguration.java`:

```java
package com.example.autoconfigure;

import com.example.core.CoreService;
import com.example.optional.OptionalCodec;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ExampleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CoreService.class)
    CoreService coreService() {
        return input -> "core:" + input;
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.optional.OptionalCodec")
    @ConditionalOnProperty(
            prefix = "demo.optional",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    static class OptionalCodecConfiguration {

        @Bean
        @ConditionalOnMissingBean(OptionalCodec.class)
        OptionalCodec optionalCodec() {
            return text -> "ENC:" + text;
        }
    }
}
```

**Điểm then chốt trong file này:**

1. `ExampleAutoConfiguration` là class **luôn có thể được Boot xét**, bất kể optional codec có mặt hay không.
2. `coreService()` chỉ dùng `CoreService`, không tham chiếu optional SDK trong method signature.
3. `OptionalCodecConfiguration` là static nested `@Configuration`, được bảo vệ **ở cấp class** bằng tên FQCN của `OptionalCodec`.
4. Phương thức `optionalCodec()` có return type optional, nhưng **nằm bên trong** lớp đã được bảo vệ. Khi codec vắng mặt, Spring có thể bỏ qua nested configuration sau khi đọc metadata của class, thay vì đi vào các method signatures của nó.
5. `@ConditionalOnProperty` cho phép người dùng chủ động tắt integration codec mà không ảnh hưởng core.
6. `@ConditionalOnMissingBean(OptionalCodec.class)` cho phép consumer tự cung cấp codec. Điều kiện này được đánh giá khi nested class có thể xử lý an toàn và SDK hiện diện.
7. Việc có import Java `import com.example.optional.OptionalCodec;` ở đầu file **không phải nguyên nhân lỗi**; nguy hiểm nằm ở **bytecode references** (signatures, superclass, fields, static initialization...) của những class không được guard. Imports trong Java source chỉ là cách viết tên cho compiler.

**Vì sao không bọc toàn bộ ExampleAutoConfiguration bằng `@ConditionalOnClass`?** Nếu làm vậy, khi codec vắng mặt thì ngay cả `CoreService` cũng bị bỏ qua. Nested configuration cho phép bảo vệ đúng **nhánh optional** thay vì tắt cả auto-configuration.

### 8.6. Đăng ký imports resource

Tạo đúng đường dẫn:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

```text
com.example.autoconfigure.ExampleAutoConfiguration
```

Không cần liệt kê `ExampleAutoConfiguration$OptionalCodecConfiguration` ở đây. Nested configuration được Spring xử lý như thành phần của outer configuration; imports file chỉ công bố outer candidate trong ví dụ này.

### 8.7. Main application để quan sát kết quả

Tạo `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.core.CoreService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showResults(
            CoreService coreService, ApplicationContext context) {
        return args -> {
            System.out.println("CORE=" + coreService.reply("ping"));
            System.out.println("OPTIONAL_DEFAULT_BEAN="
                    + context.containsBean("optionalCodec"));
        };
    }
}
```

Ở đây runner chỉ inject `CoreService`, type độc lập với optional SDK. Để quan sát default codec, code **hỏi sự tồn tại theo tên bean**; runner không dùng `OptionalCodec.class` hay inject SDK interface tùy chọn, nhằm tránh bản thân ứng dụng quan sát trở thành nguồn lỗi khi SDK vắng mặt.

### 8.8. Chạy mặc định và đọc stdout

```bash
mvn test
mvn spring-boot:run
```

Với SDK demo hiện diện trong cùng artifact và property mặc định, hai dòng từ `ApplicationRunner` là:

```text
CORE=core:ping
OPTIONAL_DEFAULT_BEAN=true
```

Maven/Spring Boot có thể in nhiều startup logs khác; đây chỉ là hai dòng do runner tạo. `OPTIONAL_DEFAULT_BEAN=true` có nghĩa bean **tên "optionalCodec"** được đăng ký, không có nghĩa tất cả implementations của `OptionalCodec` đều mang tên đó.

### 8.9. Tắt nhánh optional bằng property, không tắt core

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.optional.enabled=false"
```

Hai dòng từ runner:

```text
CORE=core:ping
OPTIONAL_DEFAULT_BEAN=false
```

Property condition gắn trên nested class khiến toàn bộ nhánh optional không được áp dụng; outer core bean vẫn được đăng ký. Đây là một lý do khác khiến codec không xuất hiện, không đồng nghĩa SDK vắng mặt.

## 9. Kiểm thử đúng rủi ro: FilteredClassLoader

Tạo `src/test/java/com/example/autoconfigure/ExampleAutoConfigurationTest.java`:

```java
package com.example.autoconfigure;

import com.example.core.CoreService;
import com.example.optional.OptionalCodec;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ExampleAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ExampleAutoConfiguration.class));

    @Test
    void optionalClassPresentCreatesBothBeans() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CoreService.class);
            assertThat(context).hasSingleBean(OptionalCodec.class);
            assertThat(context.getBean(CoreService.class).reply("ping"))
                    .isEqualTo("core:ping");
            assertThat(context.getBean(OptionalCodec.class).encode("x"))
                    .isEqualTo("ENC:x");
        });
    }

    @Test
    void missingOptionalClassSkipsOnlyGuardedConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(OptionalCodec.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).doesNotHaveBean("optionalCodec");
                    assertThat(context.getBean(CoreService.class).reply("ping"))
                            .isEqualTo("core:ping");
                });
    }

    @Test
    void optionalFeatureDisabledSkipsCodec() {
        runner.withPropertyValues("demo.optional.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).doesNotHaveBean(OptionalCodec.class);
                });
    }

    @Test
    void userCodecMakesDefaultBackOff() {
        runner.withUserConfiguration(UserCodecConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).hasSingleBean(OptionalCodec.class);
                    assertThat(context.getBean(OptionalCodec.class).encode("x"))
                            .isEqualTo("USER:x");
                    assertThat(context).doesNotHaveBean("optionalCodec");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCodecConfiguration {

        @Bean
        OptionalCodec userCodec() {
            return text -> "USER:" + text;
        }
    }
}
```

Chạy:

```bash
mvn test
```

Bộ test kiểm tra bốn đường:
- **SDK có mặt:** core và codec tồn tại, cả hai hoạt động.
- **SDK bị FilteredClassLoader ẩn:** core vẫn hoạt động, bean optional không được tạo, **ApplicationContext không thất bại**.
- **Property tắt:** codec không được đăng ký mặc dù type tồn tại.
- **Consumer cung cấp bean:** codec mặc định back off; bean do app tạo được dùng.

### 9.1. Vì sao test này khác test thông thường?

Nếu chỉ chạy `mvn test` trên classpath đầy đủ, method signature nào có type `OptionalCodec` cũng resolve được. Điều này **không kiểm chứng** khả năng chịu thiếu SDK.

`FilteredClassLoader(OptionalCodec.class)` tạo một loader cho context trong đó class chỉ định được lọc đi; Spring Boot hỗ trợ dùng cùng `ApplicationContextRunner` để quan sát auto-configuration khi class bị loại khỏi classpath nhìn thấy.

Quan trọng: test thiếu class **không** yêu cầu trực tiếp `OptionalCodec.class` bên trong callback của context đã lọc. Nó chỉ kiểm tra `CoreService.class` (luôn có) và tên bean `"optionalCodec"`. Do đó chính test không cố tạo hoặc phân giải SDK type qua loader đã bị lọc.

**Giới hạn:** FilteredClassLoader mô phỏng visibility của class khi test, không tự chứng minh behavior của mọi app server hoặc mọi multi-ClassLoader environment. Với thư viện thật, nên có thêm một **consumer integration test** dùng dependency graph thiếu SDK và chạy trên artifact phát hành thực.

### 9.2. Kiểm tra đóng gói JAR

```bash
mvn package
jar tf target/optional-signature-demo-0.0.1-SNAPSHOT.jar
```

Trong Boot executable JAR, imports resource thường nằm tại:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Và class nested được biên dịch thành file dạng:

```text
BOOT-INF/classes/com/example/autoconfigure/ExampleAutoConfiguration$OptionalCodecConfiguration.class
```

Dấu `$` là cách JVM đặt binary name của nested class. Không thay nội dung imports file bằng class nested này; outer class là auto-configuration candidate được liệt kê.

## 10. Sửa lỗi ở thư viện thật có optional dependency

Trong dự án thực tế, optional SDK không nằm trong source giống demo. Kiến trúc phổ biến:

```text
library-core.jar
  CodecPort
  ApplicationFeature

library-autoconfigure.jar
  CoreAutoConfiguration
  VendorSdkAutoConfiguration (guarded class)
  META-INF/spring/...AutoConfiguration.imports

vendor-sdk.jar (OPTIONAL ở phía consumer)
  com.vendor.codec.OptionalCodec

consumer-app.jar
  -> library-core
  -> library-autoconfigure
  -> có thể có hoặc không có vendor-sdk
```

### 10.1. Mẫu Maven optional dependency

Trong `library-autoconfigure/pom.xml` (fragment dependencies):

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>vendor-codec-sdk</artifactId>
    <version>1.2.3</version>
    <optional>true</optional>
</dependency>
```

Đây là **mẫu minh họa**, vendor/phiên bản giả định, không phải dependency tọa độ có thật. Nó cho phép library module compile với SDK, trong khi consumer không mặc định nhận dependency đó transitively.

Trong Gradle có thể dùng `compileOnly("com.vendor:vendor-codec-sdk:1.2.3")` khi thiết kế variant/dependency publication phù hợp. Cần kiểm tra dependency metadata được publish chứ không chỉ nhìn build file.

**Nhưng đây mới là một nửa lời giải.** Dù SDK có thể vắng runtime, bytecode của autoconfiguration vẫn cần guard đúng tầng. `optional=true` không tự sửa return type signature gây lỗi.

### 10.2. Kiểm tra dependency tree thực tế

```bash
mvn dependency:tree
```

Hoặc Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với ứng dụng deploy, cần phân biệt runtime của IDE, Maven test, executable JAR, container và app server. Một SDK tưởng đã bị bỏ vẫn có thể tới qua starter khác; ngược lại class compile được nhưng runtime image không chứa JAR.

### 10.3. Tách cấu hình theo tính năng, không chặn mọi bean

Cấu trúc nên hướng tới:

```text
CoreAutoConfiguration
  -> @Bean CoreService (không phụ thuộc optional SDK)

VendorSdkAutoConfiguration
  -> @ConditionalOnClass(vendor SDK)
  -> @Bean VendorAdapter / OptionalCodec
```

Nếu đặt `@ConditionalOnClass` cho cả cấu hình chứa core và vendor, thiếu vendor sẽ làm **core biến mất** không cần thiết. Cần guard đúng ranh giới feature.

### 10.4. Không để SDK optional lọt ra API cốt lõi bắt buộc

Nếu interface công khai `CoreService` có phương thức nhận/return type `OptionalCodec`, mọi consumer core có thể vẫn cần giải quyết SDK type dù bạn đã tách `@Configuration`. Auto-configuration chỉ bảo vệ việc đăng ký bean; **không sửa được API lõi được thiết kế phụ thuộc optional SDK**.

Để tách biệt thật:
- `core` định nghĩa API trung tính;
- `vendor-adapter` phụ thuộc SDK và implement core API;
- `vendor-autoconfigure` guard sự có mặt SDK trước khi cấu hình adapter;
- consumer không cần SDK vẫn dùng được chức năng core.

## 11. Các thông báo lỗi và cách phân biệt

Không phải mọi lỗi do dependency vắng mặt đều có cùng exception. Tùy điểm xảy ra:

| Lỗi / dấu hiệu | Gợi ý nguyên nhân | Nên kiểm tra |
| --- | --- | --- |
| `java.lang.NoClassDefFoundError: com/vendor/codec/OptionalCodec` | JVM cố phân giải class mà runtime loader không thấy | Method return type, parameter, superclass, static initializer, packaging |
| `ClassNotFoundException: com.vendor.codec.OptionalCodec` | Một loader/API chủ động tìm class nhưng không thấy | Runtime JAR, ClassLoader, code reflection |
| `TypeNotPresentException` | Một type trong signature/annotation generic hoặc metadata không tồn tại | Annotation/generic signature, reflective access |
| `Failed to introspect Class [...]` | Spring phản chiếu methods/fields của class cấu hình và gặp type thiếu | Đọc `Caused by` sâu bên trong, class chứa `@Bean` |
| `@ConditionalOnClass did not find required class` | **Condition không match bình thường** | Condition report, đúng expected behavior nếu feature optional |
| `BeanCreationException` | Bean definition đã được chọn; constructor/factory/init gặp lỗi | Root cause: dependency, config, network, logic |
| `NoSuchMethodError` / `IncompatibleClassChangeError` | Class có mặt nhưng phiên bản binary/API không tương thích | Dependency convergence, version của SDK |
| `UnsatisfiedDependencyException` | Spring không tìm được bean bắt buộc cho injection | Feature có được bật không; có consumer fallback không |

Một `@ConditionalOnClass` không match **đúng cách** thường phải làm context vẫn khởi động nếu tính năng optional. Nếu JVM ném `NoClassDefFoundError` ở lúc introspection class cấu hình, bạn chưa cô lập type optional đúng.

### 11.1. Đừng nhầm điều kiện không match với lỗi bean creation

- **Condition không match:** Spring không đăng ký bean đó; có thể thấy Negative matches trong `ConditionEvaluationReport`.
- **Bean creation fail:** Spring đã có definition và gọi/khởi tạo object rồi mới lỗi. Có `BeanCreationException` cùng chain nguyên nhân.
- **Signature/class linkage fail:** Có thể xảy ra **trước khi** condition trên method kịp xét; có thể log “Failed to introspect”, `NoClassDefFoundError` hoặc lỗi JVM khác.
- **Configuration không được import:** Candidate có thể vắng khỏi imports hoặc bị exclude; điều này khác hẳn class đã được xử lý nhưng gặp lỗi signature.

Trong thực tế, sự phân loại phụ thuộc logs, stack trace và điểm exception xảy ra; một triệu chứng “ứng dụng không start” không đủ để kết luận.

## 12. Debug khi thêm starter làm app crash vì optional SDK

Hãy đi theo thứ tự sau:

1. **Tìm type vắng mặt.** Đọc chain `Caused by` đầy đủ: binary name trong `NoClassDefFoundError` hoặc `ClassNotFoundException` là gì?
2. **Xác định class đang bị introspect.** Stack trace “Failed to introspect Class” thường có tên configuration; tìm các `@Bean` methods, method arguments, superclass, fields.
3. **Xác minh SDK có trong runtime không.** So sánh `mvn dependency:tree` hoặc Gradle runtimeClasspath với nội dung artifact và classloader của process.
4. **Xem condition ở đâu.** Nếu chỉ có `@ConditionalOnClass` ngay trên method trả optional type, chuyển guard ra **class-level**.
5. **Tách cấu hình.** Dời mọi signature phụ thuộc SDK sang static nested `@Configuration` hoặc top-level dedicated `@AutoConfiguration` có class-level condition.
6. **Kiểm tra core unaffected.** Thiếu SDK phải không làm mất những bean core không có dependency vào SDK.
7. **Thêm test FilteredClassLoader.** Chạy cả đường có class, không class, property disable và consumer override.
8. **Kiểm tra resource imports.** Một lớp cấu hình guard tốt nhưng không được công bố trong `AutoConfiguration.imports` vẫn sẽ không hoạt động khi consumer có SDK.
9. **Đối chiếu exception khác.** Nếu class đã có nhưng `NoSuchMethodError`, kiểm tra version compatibility thay vì chỉ class existence.
10. **Quan sát condition report.** Khi context có thể chạy, bật `--debug`; nếu startup fail sớm, ưu tiên exception chain rồi mới tìm report.

Lệnh với demo:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug"
```

Spring Boot có thể in Positive/Negative matches, Exclusions và các thông tin condition; nhưng **condition report không thay thế full stack trace** khi JVM lỗi liên kết type trước khi context khởi động xong.

## 13. Vì sao các “cách sửa nhanh” sau không tốt?

### 13.1. “Chỉ đổi @ConditionalOnClass value thành name”

Sai trọng tâm nếu method signature vẫn là `OptionalCodec`.

```java
@Bean
@ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
OptionalCodec optionalCodec() { ... }
```

Đây vẫn là fragment anti-pattern. `name` không làm method return descriptor biến mất khỏi bytecode.

### 13.2. “Bọc try/catch NoClassDefFoundError trong factory method”

```java
@Bean
OptionalCodec optionalCodec() {
    try {
        return buildCodec();
    } catch (NoClassDefFoundError err) {
        return null;
    }
}
```

Fragment trên **không phải sửa lỗi**: method có thể chưa từng được gọi vì lỗi xảy ra khi JVM/Spring introspect signature. `return null` cũng không thể thay thế thiết kế bean optional chuẩn và có thể gây các behavior khó hiểu trong Spring.

### 13.3. “Đổi return type thành Object để class không load SDK”

Ví dụ:

```java
@Bean
Object optionalCodec() {
    return buildOptionalCodec();
}
```

Điều này có thể né một descriptor cụ thể, nhưng type metadata của bean bị suy yếu; dependency injection theo `OptionalCodec` và condition theo type có thể không còn hoạt động như mong đợi. Nếu body vẫn nạp SDK không tồn tại, lỗi chỉ chuyển sang thời điểm khác. **Chỉ làm vậy khi hợp đồng bean thật sự là Object và đã có thiết kế/type discovery phù hợp**, không dùng như thủ thuật chữa classpath.

### 13.4. “Đặt @Lazy là xong”

`@Lazy` có thể hoãn **khởi tạo instance**, nhưng không cam kết hoãn **parsing configuration / return type resolution**. Nếu JVM lỗi trước khi bean definition đăng ký xong, lazy không giúp được.

### 13.5. “Thêm @ConditionalOnMissingBean để bảo vệ SDK”

`@ConditionalOnMissingBean` kiểm tra bean definitions, không kiểm tra classpath optional SDK theo cách có thể bảo vệ method return type khỏi JVM resolution. Nó có vai trò back-off khi consumer đã cung cấp bean, **không thay `@ConditionalOnClass` cấp lớp**.

### 13.6. “Đặt toàn bộ thư viện sau @ConditionalOnClass(vendorSdk)”

Cách đó tránh method signature lỗi nhưng có thể vô tình tắt các bean core không liên quan. Tách nhánh integration nhỏ hơn để người tiêu thụ không bị mất functionality khác.

## 14. Kiểm thử thêm: không nhầm classpath với version compatibility

`FilteredClassLoader` trả lời câu hỏi: **“Nếu class này không nhìn thấy được, configuration có được bỏ qua an toàn không?”**.

Nhưng một thư viện còn có các câu hỏi khác:

| Tình huống | Cần test gì? |
| --- | --- |
| SDK vắng hoàn toàn | Context vẫn lên, chỉ nhánh optional bị bỏ |
| SDK có, API tương thích | Bean adapter tạo và hoạt động |
| SDK có nhưng đổi method signature | Kiểm thử phiên bản SDK cụ thể; `@ConditionalOnClass` không xác nhận method tồn tại |
| SDK transitive từ dependency khác | Dependency graph thực tế, classpath convergence |
| Property user disable | Chặn feature dù SDK có |
| Consumer tự cung cấp bean | Default adapter back off, không tạo hai bean |
| SDK có static initializer gây lỗi | Chạy integration test lifecycle; class presence không bảo đảm khởi tạo |
| Custom ClassLoader | Test theo môi trường loader, đặc biệt trong plugin/container |
| Class hiện diện nhưng config thiếu endpoint/credential | Validation/config test; không “vá” bằng classpath condition |

Một test unit cho custom classloader không thay thế thử nghiệm trên artifact phát hành nếu phần tích hợp phụ thuộc classpath rất phức tạp.

### 14.1. Tránh chọn điều kiện quá rộng

Nếu một integration cần cả `OptionalCodec` và `VendorTransport`, class-level condition nên phản ánh dependency bắt buộc thật:

```java
@ConditionalOnClass(name = {
        "com.vendor.codec.OptionalCodec",
        "com.vendor.transport.VendorTransport"
})
```

Đây là fragment class-level. Nếu chỉ guard codec nhưng factory method lại gọi API transport thiếu, class-level condition có thể match và startup vẫn lỗi.

Ngược lại, không nên yêu cầu toàn bộ vendor SDK cho một feature chỉ cần API nhỏ đã có; chọn điều kiện chính xác theo kiến trúc tích hợp.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `@ConditionalOnClass(name="com.vendor.Optional")` đặt trên `@Bean com.vendor.Optional optional()` có bảo đảm app chạy khi class vắng không?

**Đáp án:** Không. Method signature tham chiếu optional type; Spring/JVM có thể cần phân giải nó trước khi điều kiện method-level được áp dụng. Hãy dời method vào cấu hình được guard ở class level.

**Câu 2.** Tại sao Spring vẫn cần return type nếu chưa tạo bean?

**Đáp án:** Spring cần bean type metadata để đăng ký bean definitions, type matching, dependency injection và điều kiện dựa trên bean, nên có thể introspect method trước khi factory body chạy.

**Câu 3.** Có phải cứ chứa import Java của SDK trong file là JVM luôn nạp class ngay không?

**Đáp án:** Không. `import` trong Java source là tiện ích cú pháp của compiler; runtime phụ thuộc bytecode references, class loading và resolution. Rủi ro là signature/field/superclass/static initialization ở class chưa được guard.

**Câu 4.** Vì sao dùng nested static `@Configuration` thay vì chỉ đặt condition trên method?

**Đáp án:** Nested class là ranh giới có metadata class-level để Spring đánh giá trước khi nạp/phân tích các method mang optional return type của nó.

**Câu 5.** Nếu đã bảo vệ cả outer auto-configuration bằng `@ConditionalOnClass` thì core bean có còn khi SDK vắng không?

**Đáp án:** Không, nếu core bean nằm trong class bị bỏ qua. Tách guard vào nhánh optional để core hoạt động độc lập.

**Câu 6.** `FilteredClassLoader(OptionalCodec.class)` chứng minh gì?

**Đáp án:** Nó mô phỏng class bị ẩn khỏi ClassLoader của ApplicationContext. Test xác nhận code guard không fail khi class vắng, nhưng không thay toàn bộ consumer runtime dependency test.

**Câu 7.** `@Lazy` có sửa được lỗi class linkage lúc Spring introspect configuration không?

**Đáp án:** Không bảo đảm. Lazy chủ yếu hoãn việc tạo bean instance; lỗi metadata/signature có thể xảy ra trước đó.

**Câu 8.** `@ConditionalOnClass` match có nghĩa factory method chắc chắn thành công không?

**Đáp án:** Không. SDK có class nhưng có thể thiếu method tương thích, không có credential, sai config hoặc factory method ném exception.

**Câu 9.** Dùng `@ConditionalOnMissingBean` có thay được `@ConditionalOnClass` không?

**Đáp án:** Không. Một cái xét bean đang có để back off, cái kia xét classpath để quyết định có kích hoạt integration hay không.

**Câu 10.** Test Spring Boot chạy với đủ dependencies có phát hiện được bug chỉ xảy ra khi SDK vắng không?

**Đáp án:** Thường không. Phải chủ động tạo test với `FilteredClassLoader` hoặc consumer runtime thiếu SDK.

## 16. Checklist review auto-configuration cho dependency optional

Khi đọc một pull request cho starter, kiểm tra:

- [ ] Optional integration có một **class-level `@ConditionalOnClass`** bao đủ kiểu SDK có trong signatures bên trong?
- [ ] Các `@Bean` methods ở configuration luôn được phân tích **không** có return type/parameter type thuộc optional SDK?
- [ ] Không có superclass, interfaces, fields hoặc static initialization không được guard tham chiếu SDK?
- [ ] Core functionality vẫn tồn tại khi SDK bị ẩn?
- [ ] `@ConditionalOnMissingBean` được dùng phù hợp để consumer tự thay bean?
- [ ] Property enable/disable có phạm vi riêng cho integration?
- [ ] `AutoConfiguration.imports` liệt kê candidate đúng FQCN và được đóng trong JAR?
- [ ] Test `FilteredClassLoader` chứng minh context không fail khi SDK vắng?
- [ ] Test có SDK và test consumer override đều pass?
- [ ] Dependency optional/compile-only được publish với metadata đúng?
- [ ] Khi có nhiều optional SDK types, tất cả dependencies bắt buộc của nhánh đều được bảo vệ?
- [ ] Không coi exception linkage là một negative condition thông thường khi chưa đọc root cause?

## 17. Tóm tắt và tài liệu chính thức

**Mẫu tư duy một dòng:**

```text
SAI:  @Bean OptionalSdkType method() + @ConditionalOnClass trên method
ĐÚNG: @Configuration + @ConditionalOnClass trên CLASS
      chứa @Bean OptionalSdkType method()
      (core beans nằm ngoài lớp optional được guard)
```

Spring Boot có thể kiểm tra class-level conditions bằng metadata mà chưa cần nạp configuration class và giải quyết các optional signatures. Ngược lại, method-level condition không bảo đảm tránh được class loading/introspection của method có kiểu trả về không tồn tại. Muốn thiết kế starter an toàn, **cô lập optional API ở ranh giới configuration class**, kiểm thử cả trường hợp class vắng và hiện diện, và phân biệt compile dependency với runtime dependency.

**Nguồn tham khảo chính thức:**

- Spring Boot 3.3 — Creating Your Own Auto-configuration, phần *Class Conditions* và *Testing*: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `ConditionalOnClass` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3 — `FilteredClassLoader` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.3 — `ApplicationContextRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Framework 6.1 — `Configuration` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Configuration.html
- Spring Framework 6.1 — `Bean` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html
