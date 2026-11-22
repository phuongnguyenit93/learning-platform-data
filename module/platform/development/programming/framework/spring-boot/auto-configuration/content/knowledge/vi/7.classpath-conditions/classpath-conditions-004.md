# Kiểm tra đồng thời nhiều lớp và thiết kế điều kiện cho từng nhóm tính năng trong Spring Boot

## 1. Bài toán: một starter có nhiều tích hợp tùy chọn

Giả sử thư viện của bạn cung cấp **nhiều tính năng độc lập**: mã hóa văn bản, nén dữ liệu và tích hợp codec của nhà cung cấp khác. Mỗi tính năng cần những lớp Java hoặc SDK khác nhau trên classpath. Nếu ứng dụng chỉ cài dependency cho phần mã hóa, các tính năng khác không nên gây lỗi khởi động; nếu chỉ thiếu một dependency của tích hợp codec bên ngoài, phần mã hóa và nén vẫn phải hoạt động.

Spring Boot giải bài toán này qua **classpath conditions**, chủ yếu là `@ConditionalOnClass` và `@ConditionalOnMissingClass`, được kết hợp với các nested `@Configuration` riêng cho từng nhóm.

Bốn nguyên tắc quan trọng:

1. **Một `@ConditionalOnClass` kiểm tra nhiều lớp theo logic AND.** Tất cả tên lớp được liệt kê phải có mặt thì điều kiện mới khớp.
2. **Nhiều nhóm tính năng nên được kiểm tra độc lập.** Đừng đặt tất cả optional SDK classes lên lớp auto-configuration cha nếu một nhóm vắng mặt mà các nhóm khác vẫn phải hoạt động.
3. **Phát hiện class không đồng nghĩa tạo bean.** `@ConditionalOnClass` chỉ xét classpath; bean còn phụ thuộc `@ConditionalOnBean`, `@ConditionalOnMissingBean`, property và các điều kiện khác.
4. **Tránh tham chiếu class tùy chọn quá sớm.** Khi có factory method dùng kiểu từ dependency có thể thiếu, nên cô lập nó trong một nested configuration được bảo vệ bằng điều kiện ở **cấp class**, thay vì chỉ đặt condition trên `@Bean` method.

Đích học tập: biết khi nào dùng mảng `value` hoặc `name`; phân biệt AND với OR; tạo nhiều feature groups không phụ thuộc lẫn nhau; xác định hành vi khi dependency tùy chọn thiếu; thiết kế cấu trúc auto-configuration dễ chẩn đoán và mở rộng.

## 2. Cú pháp kiểm tra nhiều class: tất cả đều phải hiện diện

Annotation `org.springframework.boot.autoconfigure.condition.ConditionalOnClass` có hai thuộc tính quan trọng:

```java
// Mã minh họa: đặt trên class @Configuration hoặc @AutoConfiguration.
@ConditionalOnClass({
        java.util.Base64.class,
        java.nio.charset.StandardCharsets.class
})
```

Đây là cách viết rút gọn của `value = {...}`. Hai class trong mảng **đều phải** hiện diện trên classpath. Java 17 luôn có các class trên, nên ví dụ này match ở môi trường Java 17 thông thường.

Cách dùng tên chuỗi:

```java
@ConditionalOnClass(name = {
        "java.util.Base64",
        "com.vendor.codec.FastCodec"
})
```

Ở đây cả `java.util.Base64` **và** `com.vendor.codec.FastCodec` phải hiện diện. Nếu `FastCodec` không có trong ứng dụng, điều kiện **false** — mặc dù `Base64` có sẵn.

### 2.1. Bảng chân trị AND

Xét `@ConditionalOnClass(name = {"com.acme.A", "com.acme.B"})`:

| Class A có? | Class B có? | Kết quả |
| --- | --- | --- |
| Có | Có | Match |
| Có | Không | Không match |
| Không | Có | Không match |
| Không | Không | Không match |

Với ba lớp A, B, C, điều kiện match **chỉ khi cả ba có mặt**.

Đừng hiểu “kiểm tra nhiều class” là “có ít nhất một class bất kỳ”. Nếu muốn **OR**, phải tổ chức các cấu hình riêng hoặc dùng một condition tổng hợp được thiết kế cho OR; `@ConditionalOnClass` nhiều phần tử không tự đổi thành OR.

### 2.2. Phối hợp `value` và `name`

Javadoc `@ConditionalOnClass` nêu:
- `Class<?>[] value()`: các class bắt buộc phải có.
- `String[] name()`: các tên đầy đủ của class bắt buộc phải có.

Nếu chỉ định đồng thời cả hai, các yêu cầu hiện diện của chúng được kết hợp theo nghĩa **tất cả**. Cách đọc thực tế: tất cả class literals và tất cả class names đều là điều kiện cần.

```java
@ConditionalOnClass(
        value = java.util.Base64.class,
        name = {"com.vendor.codec.FastCodec", "com.vendor.codec.CodecConfig"}
)
```

Đây là đoạn annotation minh họa, không phải class Java độc lập. Lý do `name` hữu ích: các lớp vendor **có thể không tồn tại trong compile classpath** của module này, vì annotation chỉ chứa chuỗi. Nếu sử dụng `FastCodec.class` trong source, module vẫn cần class đó trong **compile classpath**, dù nó có thể không nằm trong runtime classpath.

### 2.3. `@ConditionalOnMissingClass` kiểm tra điều ngược lại

`@ConditionalOnMissingClass` nhận tên class dưới dạng chuỗi:

```java
@ConditionalOnMissingClass("com.vendor.codec.FastCodec")
```

Nó match khi class được chỉ định **không** có trên classpath. Khi liệt kê nhiều tên lớp, ý nghĩa cần phân biệt với OR: các lớp được chỉ định phải **đều vắng mặt** để điều kiện match.

Kết hợp điều kiện này với `@ConditionalOnClass` nếu cần chuyển đổi giữa nhánh có SDK và nhánh không có SDK, nhưng chỉ làm vậy khi yêu cầu nghiệp vụ thực sự cần. Trường hợp phổ biến hơn là có cấu hình core độc lập và cấu hình vendor chỉ xuất hiện khi SDK hiện diện.

## 3. `@ConditionalOnClass` không phải một phép kiểm tra dependency đầy đủ

Chỉ vì class `com.vendor.codec.FastCodec` có mặt không bảo đảm:

- phiên bản class có các method/signature mà code của bạn cần;
- các dependency bắc cầu của SDK đều hiện diện và tương thích;
- bean `FastCodec` đã được đăng ký;
- cấu hình property cho SDK đã hợp lệ;
- không có `LinkageError` hoặc lỗi khởi tạo khác khi thực thi;
- ứng dụng thực sự bật tính năng qua properties.

Đây là **điều kiện về khả năng tìm thấy class**, không phải một bài kiểm tra runtime integration health.

Ví dụ class trên classpath nhưng bean chưa được đăng ký:

```java
@ConditionalOnClass(name = "com.vendor.codec.FastCodec")
```

Điều kiện này **có thể match**, nhưng khi inject `FastCodec` ở một factory method mà context chưa có bean tương ứng, DI vẫn thất bại. Nếu thực sự cần **bean**, hãy kết hợp `@ConditionalOnBean` thích hợp; nếu muốn tự cung cấp default, có thể dùng `@ConditionalOnMissingBean`.

Còn nếu muốn bật/tắt theo cấu hình, thêm `@ConditionalOnProperty`. Từng loại điều kiện trả lời một câu hỏi khác nhau.

| Điều kiện | Câu hỏi thực sự |
| --- | --- |
| `@ConditionalOnClass` | Một hoặc nhiều Java classes được yêu cầu có trên classpath không? |
| `@ConditionalOnMissingClass` | Các class được yêu cầu vắng mặt trên classpath không? |
| `@ConditionalOnBean` | Các bean cần thiết đã được nhận diện ở thời điểm điều kiện được xét chưa? |
| `@ConditionalOnMissingBean` | Có thiếu bean phù hợp để auto-config cung cấp default không? |
| `@ConditionalOnProperty` | Property có thỏa giá trị bật/tắt hoặc giá trị chỉ định không? |
| `@ConditionalOnResource` | Resource được yêu cầu có tìm thấy không? |

Trong Spring Boot, những annotation conditions xuất hiện cùng trên class hoặc method thường hoạt động theo logic **AND giữa các yêu cầu**: cấu hình chỉ được áp dụng khi các điều kiện cần thiết đều match.

## 4. Thiết kế nhiều nhóm tính năng: tránh một điều kiện quá rộng

### 4.1. Thiết kế dễ sai: một “cửa khóa” cho mọi tích hợp

Giả sử một auto-configuration cung cấp cả ba feature:

```java
@AutoConfiguration
@ConditionalOnClass(name = {
        "java.util.Base64",
        "java.util.zip.GZIPOutputStream",
        "com.vendor.codec.FastCodec"
})
class EverythingAutoConfiguration {
    // Cấu hình cả Base64, GZIP và vendor codec...
}
```

Đây là code minh họa, không độc lập chạy được.

Vấn đề là nếu ứng dụng **không cài vendor SDK** (điều hoàn toàn hợp lệ), **toàn bộ class auto-configuration không match**. Vì thế Base64 và GZIP cũng không có bean, dù hai tính năng này không liên quan đến SDK.

Điều kiện của parent đang đặt ra ràng buộc **AND toàn cục**. Nó phù hợp nếu *ba nhóm luôn phải đi cùng nhau*; không phù hợp nếu đây là **ba feature tùy chọn độc lập**.

### 4.2. Thiết kế đúng: nhiều nested configuration cùng thuộc một auto-config

```java
@AutoConfiguration
public class FeaturesAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {"java.util.Base64",
                                "java.nio.charset.StandardCharsets"})
    static class TextEncodingConfiguration {
        // @Bean cho feature mã hóa
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {"java.util.zip.GZIPOutputStream",
                                "java.io.ByteArrayOutputStream"})
    static class GzipConfiguration {
        // @Bean cho feature nén
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {"java.util.Base64",
                                "com.vendor.codec.FastCodec"})
    static class VendorConfiguration {
        // @Bean cho feature vendor
    }
}
```

Đây là **skeleton minh họa**, chưa có import hay bean methods.

Giờ đây:
- Nhóm Text match nếu **cả Base64 và StandardCharsets** có trên classpath.
- Nhóm GZIP match nếu **cả GZIPOutputStream và ByteArrayOutputStream** có trên classpath.
- Nhóm vendor match nếu **cả Base64 và FastCodec** có trên classpath.
- Thiếu FastCodec **không làm Text/GZIP bị loại**.

Nếu một bean Text cần thêm property bật/tắt hoặc cần nhường chỗ cho user bean, bạn có thể đặt condition ở group hoặc method tương ứng mà **không làm ảnh hưởng tới group khác**.

### 4.3. Khi nào đặt điều kiện ở parent?

Đặt classpath condition ở **parent `@AutoConfiguration`** khi nó phản ánh một **dependency thực sự dùng chung và bắt buộc cho tất cả nhóm**.

Ví dụ nếu mọi feature đều yêu cầu `com.acme.core.CoreRuntime` thì:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.core.CoreRuntime")
public class FeaturesAutoConfiguration {
    // Nested groups vẫn có điều kiện riêng.
}
```

Khi `CoreRuntime` vắng mặt, tất cả nhóm đều không thể hoạt động, nên parent gate là hợp lý. Nếu chỉ nhóm vendor cần `FastCodec`, đặt điều kiện đó lên nested vendor group, **không đặt lên parent**.

Một thiết kế tốt tạo **ranh giới điều kiện khớp với ranh giới feature/dependency thực sự**.

### 4.4. Nếu chỉ cần một trong hai SDK: OR, không phải AND

Một số bài toán là *có SDK A hoặc SDK B đều được*. Dùng một mảng `@ConditionalOnClass(name={"sdk.A","sdk.B"})` sẽ **sai ý** vì nó đòi cả hai.

Thiết kế dễ bảo trì hơn:

```java
@AutoConfiguration
public class StorageAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.alpha.AlphaClient")
    static class AlphaStorageConfiguration {
        // Tích hợp Alpha
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.beta.BetaClient")
    static class BetaStorageConfiguration {
        // Tích hợp Beta
    }
}
```

Đây là **skeleton không độc lập chạy**. Nó cho phép **hai nhánh tồn tại độc lập**, tương đương OR ở cấp “có ít nhất một nhánh được xem xét”.

Nhưng nếu **cả SDK A và B** có mặt, **cả hai nested configuration có thể match**. Khi chỉ được tạo **một bean duy nhất**, cần xác định precedence và điều kiện back-off, thứ tự auto-config, hoặc property chọn provider. Không thể chỉ tách nhóm là đã giải quyết xung đột bean.

Spring Boot có các công cụ như `AnyNestedCondition` cho các tổ hợp OR phức tạp, nhưng đừng dùng condition tùy biến khi hai nested configurations độc lập giải thích yêu cầu rõ ràng hơn.

## 5. Lớp tùy chọn và vấn đề load class quá sớm

Một dependency có thể có trong compile classpath nhưng vắng mặt ở runtime. Tài liệu Spring Boot cho phép sử dụng:

```java
@AutoConfiguration
@ConditionalOnClass(value = com.vendor.codec.FastCodec.class)
public class VendorAutoConfiguration {
}
```

Mã chỉ có thể **biên dịch khi có FastCodec ở compile time**. Khi `@ConditionalOnClass` gắn **trực tiếp lên configuration class**, Spring Boot có thể đọc annotation metadata qua ASM nên class literal của dependency tùy chọn có thể được kiểm tra an toàn trong những trường hợp được hỗ trợ.

Tuy nhiên, có **hai cạm bẫy**:

### 5.1. Class literal trong composed annotation

Nếu bạn tự định nghĩa annotation tổng hợp:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.codec.FastCodec")
public @interface ConditionalOnFastCodec {
}
```

Đây là đoạn minh họa (cần các imports). **Dùng `name`**, không dùng `value=FastCodec.class`, bởi Javadoc Spring Boot nhấn mạnh an toàn của class literal khi phân tích annotation trực tiếp **không được bảo đảm như vậy cho meta-annotation tùy chỉnh**.

### 5.2. Optional return type trong `@Bean` method

Xét cấu hình:

```java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.codec.FastCodec")
    FastCodec fastCodec() {
        return new FastCodec();
    }
}
```

Đây là **mã minh họa**, chỉ biên dịch nếu type FastCodec thực sự có trong compile dependencies. Việc kiểm tra `@ConditionalOnClass` ở cấp method **có thể đến quá muộn**: JVM hoặc Spring đã phải xử lý chữ ký method và các class tham chiếu trước khi điều kiện loại method được áp dụng. Một runtime không có SDK có thể gặp lỗi thiếu class.

Cách cô lập được Spring Boot khuyến nghị là nested configuration:

```java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "com.vendor.codec.FastCodec",
            "com.vendor.codec.FastCodecOptions"
    })
    static class VendorCodecConfiguration {

        @Bean
        @ConditionalOnMissingBean(FastCodec.class)
        FastCodec fastCodec() {
            return new FastCodec();
        }
    }
}
```

**Ví dụ trên chưa phải project runnable**: cần import và compile dependencies cung cấp hai class vendor. Điều quan trọng là điều kiện nằm ở **cấp nested configuration class**, giúp Spring xem xét group trước khi phân tích chữ ký factory method. Khi module hoàn toàn không có vendor compile dependencies, cũng không nên đưa tên `FastCodec` như Java type trong source của module đó.

Tương tự, đừng đặt class thuộc SDK tùy chọn trong **field type, constructor signature hoặc superclass của parent auto-config** nếu bạn muốn parent được load an toàn khi SDK thiếu. Cô lập code tích hợp ở nested group hoặc module riêng.

## 6. Ví dụ hoàn chỉnh Java 17 + Spring Boot 3.3.13: ba nhóm độc lập

Dự án Maven sau chứng minh **kiểm tra nhiều lớp bằng `name`**, một group vẫn hoạt động khi SDK của group khác vắng mặt, và user bean có thể thay default. Project cố tình **không phụ thuộc** `com.vendor.codec.FastCodec` nên chứng minh nhánh vendor không match mà không gây `ClassNotFoundException`.

Cấu hình:
- Text group yêu cầu hai Java standard classes: `Base64` và `StandardCharsets`. Group này tạo bean `TextCodec` mặc định khi chưa có bean của ứng dụng.
- GZIP group yêu cầu `GZIPOutputStream` và `ByteArrayOutputStream`. Group này tạo marker bean `gzipFeatureMarker` làm bằng chứng được đăng ký.
- Vendor group yêu cầu `Base64` **và** `com.vendor.codec.FastCodec`. Do SDK không được cài, marker `vendorFeatureMarker` không xuất hiện.
- User config có thể thêm một `TextCodec` riêng qua `--demo.custom-codec=true`; trong tình huống đó default bean sẽ back off mà GZIP/Vendor groups vẫn độc lập.

> Lưu ý về tính chất ví dụ: `gzipFeatureMarker` và `vendorFeatureMarker` là **bean minh họa** để quan sát kết quả conditions, không phải một implementation nén hay tích hợp SDK hoàn chỉnh. Trong hệ thống thực, mỗi group sẽ tạo các service/adapter cần thiết thay vì chỉ một marker.

### 6.1. Cấu trúc thư mục

```text
grouped-classpath-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/TextCodec.java
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   └── UserCodecConfiguration.java
    │   └── autoconfig/
    │       └── FeatureAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`DemoApplication` nằm trong package `com.example.app`; `FeatureAutoConfiguration` nằm trong `com.example.autoconfig`. Vì vậy feature auto-configuration **không nằm trong component scan mặc định** của app và được Spring Boot tìm thông qua file imports.

### 6.2. `pom.xml`

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
    <artifactId>grouped-classpath-demo</artifactId>
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

### 6.3. `src/main/java/com/example/api/TextCodec.java`

```java
package com.example.api;

@FunctionalInterface
public interface TextCodec {
    String encode(String input);
}
```

Đây là **public API/SPI**; app có thể inject interface hoặc tự cung cấp bean triển khai khác. Interface tự nó không tạo bean.

### 6.4. `src/main/java/com/example/autoconfig/FeatureAutoConfiguration.java`

```java
package com.example.autoconfig;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import com.example.api.TextCodec;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class FeatureAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "java.util.Base64",
            "java.nio.charset.StandardCharsets"
    })
    @ConditionalOnProperty(
            prefix = "demo",
            name = "text-enabled",
            havingValue = "true",
            matchIfMissing = true)
    public static class TextConfiguration {

        @Bean
        @ConditionalOnMissingBean(TextCodec.class)
        TextCodec textCodec() {
            return input -> Base64.getEncoder().encodeToString(
                    input.getBytes(StandardCharsets.UTF_8));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "java.util.zip.GZIPOutputStream",
            "java.io.ByteArrayOutputStream"
    })
    public static class GzipConfiguration {

        @Bean
        String gzipFeatureMarker() {
            return "GZIP_AVAILABLE";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = {
            "java.util.Base64",
            "com.vendor.codec.FastCodec"
    })
    public static class VendorConfiguration {

        @Bean
        String vendorFeatureMarker() {
            return "VENDOR_AVAILABLE";
        }
    }
}
```

**Phân tích thiết kế:**

1. Parent `FeatureAutoConfiguration` **không có** condition đòi `FastCodec`. Vì vậy SDK vắng mặt không vô hiệu hóa cả parent.
2. Mỗi nested class được annotate `@Configuration(proxyBeanMethods=false)`. Nhóm nào match thì các `@Bean` tương ứng được xét đăng ký; nhóm khác có thể không match.
3. Text group kiểm tra **hai lớp**; đồng thời có property gate riêng. Điều kiện classpath match không bảo đảm group chạy nếu `demo.text-enabled=false`.
4. `@ConditionalOnMissingBean(TextCodec.class)` kiểm tra bean user để default nhường chỗ; đây **không phải** classpath condition.
5. Vendor group chỉ nhắc `FastCodec` dưới dạng **String name**. Project có thể compile không cần class vendor. Nó không khai báo Java field/method return type liên quan vendor.
6. GZIP/Vendor marker dùng `String` để demo. Trong hệ thống lớn, hãy đặt tên bean rõ ràng và tránh dựa vào String bean như contract nghiệp vụ; các service thực tế nên có kiểu domain riêng.
7. Nếu muốn triển khai FastCodec thật, phải có SDK trong compile dependencies ở module integration thích hợp và cô lập bean method dưới nested class có condition phù hợp.

**Đặc biệt:** chỉ có tên class trong `@ConditionalOnClass` **không** làm Boot tải dependency từ Maven và không tự tạo bean type đó. Annotation chỉ kiểm tra môi trường runtime đã cung cấp.

### 6.5. `src/main/java/com/example/app/UserCodecConfiguration.java`

```java
package com.example.app;

import com.example.api.TextCodec;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserCodecConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "custom-codec",
            havingValue = "true")
    TextCodec customTextCodec() {
        return input -> "CUSTOM:" + input;
    }
}
```

Nhờ nằm dưới `com.example.app`, bean này được xét trong cấu hình ứng dụng. Khi property bật, có một bean `TextCodec` do người dùng khai báo; default trong auto-configuration phải nhường chỗ theo condition trên `textCodec()`.

### 6.6. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.api.TextCodec;
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
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            boolean codecExists = !context.getBeansOfType(TextCodec.class).isEmpty();
            String text = codecExists
                    ? context.getBean(TextCodec.class).encode("Hi")
                    : "none";

            System.out.println("CODEC_PRESENT=" + codecExists);
            System.out.println("TEXT_RESULT=" + text);
            System.out.println("DEFAULT_TEXT_BEAN="
                    + context.containsBean("textCodec"));
            System.out.println("USER_TEXT_BEAN="
                    + context.containsBean("customTextCodec"));
            System.out.println("GZIP_GROUP_BEAN="
                    + context.containsBean("gzipFeatureMarker"));
            System.out.println("VENDOR_GROUP_BEAN="
                    + context.containsBean("vendorFeatureMarker"));
        };
    }
}
```

Runner không cần inject `TextCodec` bắt buộc, nên vẫn chạy khi Text group bị tắt và không có user codec. Trong trường hợp có đúng một `TextCodec`, `getBean(TextCodec.class)` trả bean tương ứng và minh họa cả default/custom. Trong ứng dụng phức tạp có nhiều bean cùng interface, phải giải quyết `@Qualifier` / `@Primary` hoặc chọn bean qua tên/`ObjectProvider` thay vì ngầm giả định có một ứng viên.

### 6.7. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.text-enabled=true
demo.custom-codec=false
```

`demo.text-enabled` điều khiển riêng Text group, còn `demo.custom-codec` điều khiển bean user để thử back-off. Hai property là **quy ước của ứng dụng demo**, không phải cấu hình built-in chung của Spring Boot.

### 6.8. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.autoconfig.FeatureAutoConfiguration
```

Đây là **duy nhất một** auto-configuration candidate chính. Các nested `@Configuration` ở bên trong được Spring phân tích theo cấu trúc configuration class của parent; không cần và không nên tự liệt kê ba nested group như ba auto-config candidates riêng nếu chúng chỉ là cấu hình con của parent.

### 6.9. Build và chạy — trường hợp A: tính năng mặc định

Tại thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q -DskipTests package
java -jar target/grouped-classpath-demo-1.0.0.jar
```

Những dòng do `ApplicationRunner` in (không bao gồm log công cụ/môi trường):

```text
CODEC_PRESENT=true
TEXT_RESULT=SGk=
DEFAULT_TEXT_BEAN=true
USER_TEXT_BEAN=false
GZIP_GROUP_BEAN=true
VENDOR_GROUP_BEAN=false
```

Diễn giải:

- `Base64` và `StandardCharsets` đều có sẵn; Text group được chấp nhận, property bật và chưa có bean `TextCodec` khác.
- Chuỗi `"Hi"` có bytes UTF-8 `48 69` (hex), Base64 tương ứng `"SGk="`.
- GZIP group yêu cầu hai Java standard classes, đều có trên Java 17 nên marker xuất hiện.
- Vendor group cần **cả** Base64 và FastCodec, nhưng project không cài SDK; điều kiện không match và marker vắng mặt.
- Application khởi động bình thường, chứng minh thiếu optional SDK không được phép làm các nhóm khác thất bại.

### 6.10. Trường hợp B: tắt riêng Text group

```bash
java -jar target/grouped-classpath-demo-1.0.0.jar --demo.text-enabled=false
```

Các dòng runner:

```text
CODEC_PRESENT=false
TEXT_RESULT=none
DEFAULT_TEXT_BEAN=false
USER_TEXT_BEAN=false
GZIP_GROUP_BEAN=true
VENDOR_GROUP_BEAN=false
```

Dù **hai class trong Text group đều hiện diện**, `@ConditionalOnProperty` làm group không được áp dụng. GZIP vẫn chạy và Vendor vẫn bị loại. Điều đó chứng tỏ classpath presence là **một trong nhiều điều kiện**.

### 6.11. Trường hợp C: user thay default codec

```bash
java -jar target/grouped-classpath-demo-1.0.0.jar --demo.custom-codec=true
```

Stdout:

```text
CODEC_PRESENT=true
TEXT_RESULT=CUSTOM:Hi
DEFAULT_TEXT_BEAN=false
USER_TEXT_BEAN=true
GZIP_GROUP_BEAN=true
VENDOR_GROUP_BEAN=false
```

Cơ chế:
1. App register bean `customTextCodec` kiểu `TextCodec` theo property.
2. Text group vẫn match theo classpath và `demo.text-enabled=true`.
3. Factory `textCodec()` của auto-config **không được đăng ký** vì `@ConditionalOnMissingBean(TextCodec.class)` thấy user bean.
4. Runner lấy `TextCodec` do user cung cấp; GZIP/Vendor không bị tác động.

Nếu đồng thời `--demo.text-enabled=false --demo.custom-codec=true`, Text group bị tắt nhưng user codec **vẫn tồn tại**: `CODEC_PRESENT=true` và `TEXT_RESULT=CUSTOM:Hi`, trong khi `DEFAULT_TEXT_BEAN=false`. Vì user config độc lập với nested Text group nên đây là hành vi có chủ đích.

## 7. Cách tổ chức điều kiện cho từng nhóm trong starter thực tế

Một starter thường có nhiều integration phức tạp hơn demo:

```text
feature-autoconfigure/
├── CoreAutoConfiguration.java
├── DatabaseAutoConfiguration.java
├── MessagingAutoConfiguration.java
└── MetricsAutoConfiguration.java
```

Hoặc một parent auto-config với các nested `@Configuration` riêng. Chọn cấp phân tách theo độ lớn, khả năng bật/tắt và phiên bản thư viện; hai cách đều có thể đúng.

### 7.1. Tách theo “dependency closure” thực sự

Với mỗi feature, liệt kê **tập class bắt buộc**:

| Nhóm | Classpath tối thiểu | Điều kiện khác | Bean tạo ra |
| --- | --- | --- | --- |
| TextCodec | Base64, StandardCharsets | Property bật, chưa có user TextCodec | TextCodec |
| GZIP | GZIPOutputStream, ByteArrayOutputStream | Có thể cần property, resource hoặc bean khác | Compressor / marker demo |
| Vendor | SDK API, SDK configuration type | Credentials, property, bean client, version tương thích | VendorAdapter |
| Metrics | MeterRegistry, một API integration tương ứng | Đã có MeterRegistry bean, property metrics | MetricsBinder |

Đây là bảng thiết kế, **không phải lời khẳng định** rằng chỉ cần một class đã đủ chạy tích hợp thật. Với JDBC, messaging hoặc network clients, một số class bổ sung, native libraries, authentication hoặc resource có thể cần thiết; class condition không thể thay tất cả kiểm tra đó.

### 7.2. Group độc lập: condition ở nơi hẹp nhất hợp lý

Nếu chỉ Bean A cần `com.vendor.api.OptionalExtension`, đừng áp condition lên parent có cả Beans B/C. Đặt điều kiện ở một nested group hoặc `@Bean` phù hợp. Tuy nhiên nếu factory method có return/parameter types liên quan class vắng mặt, dùng **nested class-level guard** để tránh premature class loading.

Nếu hai bean trong cùng group luôn đi với nhau, đặt condition ở class-level group giảm lặp và đảm bảo chúng được bật/tắt cùng nhau.

### 7.3. Group phụ thuộc lẫn nhau: định nghĩa rõ quan hệ

Nếu adapter B cần core bean A:

- Kiểm tra classpath cần thiết của riêng B.
- Dùng `@ConditionalOnBean(CoreService.class)` ở thời điểm phù hợp nếu phải có bean A.
- Đặt `@AutoConfiguration(after = CoreAutoConfiguration.class)` cho **hai top-level auto-configs** khi B phụ thuộc definitions của A.
- Đừng nhầm ordering bean definitions với thứ tự tạo bean instances; DI mới quyết định instance dependencies.

Nếu B chỉ cần class A trên classpath nhưng tự tạo bean A bằng factory riêng, `@ConditionalOnBean` có thể không phù hợp. Đọc thiết kế thật trước khi kết hợp conditions.

### 7.4. Có nhiều provider thay thế: đừng vô tình tạo hai defaults

Nếu mỗi provider A/B có nested group độc lập và cả SDK A/B đều hiện diện, cả hai group có thể match. Khi chúng tạo cùng interface `Client`, cần thiết kế:
- một property lựa chọn provider ưu tiên;
- `@ConditionalOnMissingBean(Client.class)` và ordering rõ ràng;
- hoặc hai named beans với qualifier để ứng dụng chọn chủ đích.

**Không** dựa vào thứ tự tình cờ mà Spring parse hai nested classes để quyết định provider thắng. Nếu đây là quyết định quan trọng, hãy khai báo một quy tắc public rõ ràng và test khi cả SDK cùng có mặt.

### 7.5. Tách optional dependency compile/runtime

Có ba classpath cần hiểu:

1. **Compile classpath của module auto-config:** nơi compiler cần nhìn thấy những Java type được import/reference trực tiếp trong source.
2. **Runtime classpath của ứng dụng:** nơi Spring Boot thực tế kiểm tra `@ConditionalOnClass` và load services.
3. **Test classpath:** có thể có các SDK mocks, extras hoặc dependencies làm điều kiện match khác so với production.

Một condition dùng `name="com.vendor.FastCodec"` không đòi compiler biết type đó. Nhưng nếu method trả `FastCodec`, module **vẫn phải** có dependency compile hợp lệ; và bạn phải cô lập code đó khi runtime classpath thiếu SDK.

## 8. Chẩn đoán khi tính năng bị bỏ qua hoặc khởi động lỗi

### 8.1. Condition Evaluation Report

Chạy ứng dụng với:

```bash
java -jar target/grouped-classpath-demo-1.0.0.jar --debug --logging.level.root=DEBUG
```

Trong *Condition Evaluation Report*, tìm các nested groups như `TextConfiguration`, `GzipConfiguration` và `VendorConfiguration`. Khi FastCodec thiếu, condition theo class có thể báo class này không được tìm thấy; đó là kết quả hợp lệ cho một optional integration.

Nếu dùng Actuator, endpoint `/actuator/conditions` cũng hữu ích khi dependency và exposure được cấu hình phù hợp; không mở public tùy tiện. Đừng coi tên log hoặc format báo cáo là cố định giữa mọi bản Spring Boot.

### 8.2. Những câu hỏi nên kiểm tra theo thứ tự

1. Class auto-config cha có trong `AutoConfiguration.imports` và trong JAR không?
2. Parent có bị loại bởi classpath/property/exclusion trước khi nested groups được xem xét không?
3. Nhóm bị thiếu cần **chính xác những class nào**? Tên FQCN có đúng package/phiên bản không?
4. Class có thật trên **runtime** classpath hay chỉ compile/test classpath?
5. Có lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError` do code tham chiếu optional types trước khi điều kiện được xét không?
6. Classpath condition match rồi nhưng `@ConditionalOnProperty` hay `@ConditionalOnMissingBean` có loại bean không?
7. Hai provider groups có cùng match tạo beans trùng type/tên không?
8. Có xung đột phiên bản SDK, missing transitive dependency hoặc incompatible method signatures không?

### 8.3. Bảng lỗi phổ biến

| Hiện tượng | Giải thích khả dĩ | Cách xử lý |
| --- | --- | --- |
| Có class A nhưng `@ConditionalOnClass({A,B})` false | Class B thiếu, do AND | Bổ sung dependency đúng hoặc tách feature groups |
| Thiếu vendor SDK làm cả core feature biến mất | Đặt condition SDK ở parent | Chuyển SDK gate xuống nested vendor group |
| Viết `@ConditionalOnClass` trên `@Bean` nhưng gặp `NoClassDefFoundError` | JVM có thể xử lý method signature trước condition | Cô lập factory trong nested configuration có class-level guard |
| Compile error do `OptionalSdk.class` không tồn tại | `value` là Java class literal cần compile dependency | Dùng `name` khi chỉ cần kiểm tra sự hiện diện bằng chuỗi |
| Class present nhưng bean không có | Bean conditions/property không khớp | Xem toàn bộ condition stack và bean definitions |
| Cả SDK A và B hiện diện nên hai provider được tạo | OR được biểu đạt qua hai groups nhưng thiếu chiến lược chọn | Thêm property chọn, precedence và back-off |
| Condition sử dụng string class sai chính tả | Compiler không kiểm tra FQCN string | Test start context với SDK có và thiếu |
| Missing class được nhắc trong composed annotation gây lỗi | Class literal qua meta-annotation không an toàn như direct annotation | Dùng `@ConditionalOnClass(name=...)` trong custom composed annotation |
| Bean đã được tạo thủ công nhưng default vẫn xuất hiện | Missing-bean condition kiểm tra sai type/name hoặc thứ tự xử lý | Soát điều kiện, type metadata và auto-config ordering |
| Test local match, production không match | Classpath test có dependency khác runtime | Test ma trận các classpath hoặc dùng `FilteredClassLoader` trong tests |
| Bật property nhưng group vẫn vắng | Classpath condition của group false | Property true không thay thế được class |
| SDK class tồn tại nhưng gọi method lỗi | `@ConditionalOnClass` không kiểm tra compatibility của method | Căn chỉnh version, kiểm thử integration, kiểm tra dependency tree |

## 9. Kiểm thử ma trận classpath thay vì chỉ kiểm thử một bản đóng gói

Một thư viện nhiều optional integrations nên test ít nhất:

| Classpath | Core/Text | GZIP | Vendor |
| --- | --- | --- | --- |
| Chỉ các dependency cơ bản | Hoạt động | Hoạt động nếu có JDK classes | Không |
| Có SDK vendor đầy đủ | Hoạt động | Hoạt động | Có thể được xem xét nếu các điều kiện khác khớp |
| Chỉ có một trong hai SDK classes bắt buộc | Hoạt động | Hoạt động | Không (AND) |
| Có SDK nhưng property vendor tắt | Hoạt động | Hoạt động | Không được đăng ký khi property gate không match |
| Có user-provided bean thay default | Nhường chỗ đúng contract | Không ảnh hưởng | Không ảnh hưởng |

Với Spring Boot tests, `ApplicationContextRunner` cho phép khởi động context nhỏ và kiểm tra auto-config/bean conditions. Có thể dùng `FilteredClassLoader` để **ẩn một số classes khỏi context classloader của test**, mô phỏng thiếu dependency, rồi kiểm tra bean tồn tại hay không.

Đây là **ý tưởng test**, không phải câu khẳng định rằng một `FilteredClassLoader` có thể loại bỏ mọi reference nếu JVM đã load classes trực tiếp trước đó. Tách integration và cấu hình theo class-level guard vẫn quan trọng. Khi cần test thực sự có SDK vendor, thêm dependency test thích hợp hoặc chạy một module integration test riêng.

Các assertions nên chứng minh **kết quả thấy được từ context**:
- khi class A và B có, feature bean được đăng ký nếu điều kiện khác khớp;
- khi thiếu một class bất kỳ, riêng feature group đó không được đăng ký;
- các group độc lập vẫn tồn tại;
- user bean làm default back off;
- khi cả hai provider SDK hiện diện, chiến lược chọn bean nhất quán.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Nếu `@ConditionalOnClass(name={"com.acme.A","com.acme.B","com.acme.C"})` thì có A và C nhưng không có B, cấu hình có match không?

**Trả lời:** Không. Đây là **AND**, tất cả ba class đều phải hiện diện.

**Câu 2.** Muốn chức năng X chạy nếu có A **hoặc** B, có nên đặt `@ConditionalOnClass({A.class,B.class})` không?

**Trả lời:** Không. Mảng này đòi A **và** B. Nên tạo các nested configurations riêng cho A/B hoặc condition tổng hợp OR nếu cần một bean chung.

**Câu 3.** Vì sao vendor SDK thiếu không nên ngăn core Text group?

**Trả lời:** Vì SDK vendor chỉ là dependency của vendor group. Nếu condition được đặt ở parent, nó biến SDK thành điều kiện bắt buộc của mọi feature. Hãy đặt condition ở ranh giới nhóm có sử dụng SDK.

**Câu 4.** Trong demo, không có `com.vendor.codec.FastCodec` nhưng `GZIP_GROUP_BEAN` là true. Vì sao?

**Trả lời:** GZIP có classpath conditions riêng chỉ phụ thuộc hai Java standard classes, không phụ thuộc FastCodec. Vendor group bị loại độc lập.

**Câu 5.** Trong demo, `--demo.text-enabled=false` có làm Java mất class `Base64` không?

**Trả lời:** Không. Class vẫn có trên classpath; property condition chỉ ngăn text group được áp dụng.

**Câu 6.** Trong demo, `--demo.custom-codec=true` có khiến Text group mất điều kiện classpath không?

**Trả lời:** Không. Classpath vẫn match, nhưng `@ConditionalOnMissingBean(TextCodec.class)` làm **default factory** nhường chỗ cho user bean.

**Câu 7.** Vì sao condition trực tiếp trên `@Bean` method có return type từ SDK tùy chọn có rủi ro?

**Trả lời:** Chữ ký method có thể bị JVM/Spring xử lý trước khi condition trên method bảo vệ được nó. Nên cô lập method trong một nested `@Configuration` được kiểm tra classpath ở **cấp class**.

**Câu 8.** Khi composed annotation tự định nghĩa sử dụng `@ConditionalOnClass` để kiểm tra optional SDK, chọn `value` hay `name`?

**Trả lời:** Chọn `name` với FQCN string. Spring Boot nêu rõ class literal không có bảo đảm xử lý tương tự khi nằm trong meta-annotation.

**Câu 9.** Có class của SDK trong JAR nhưng app vẫn lỗi vì thiếu một method, `@ConditionalOnClass` có bảo vệ được không?

**Trả lời:** Không bảo đảm. Condition chỉ kiểm tra sự hiện diện của **class**; ABI, method signatures, dependency versions và lỗi runtime phải được xác minh riêng.

**Câu 10.** Tại sao test chỉ một lần với đầy đủ dependencies là chưa đủ?

**Trả lời:** Vì khi đưa ứng dụng vào production, một số optional dependencies có thể bị lược bỏ hoặc khác version. Cần test các tổ hợp classpath, đặc biệt thiếu từng class trong các AND groups và tình huống cả hai providers đồng thời hiện diện.

## 11. Tài liệu đối chiếu

- [Spring Boot 3.3.13 — ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html): `value`/`name` là các class **phải hiện diện**, cảnh báo về method signature và meta-annotation.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): class conditions, nested `@Configuration` để cô lập optional dependencies, bean conditions, tài nguyên `AutoConfiguration.imports`.
- [Spring Boot 3.3 — ConditionalOnMissingClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html): đối chiếu điều kiện yêu cầu vắng mặt class.
- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner`, `FilteredClassLoader` và test bean conditions.

**Ghi nhớ:** `@ConditionalOnClass` có nhiều class là phép **AND**. Nếu các tính năng độc lập, tách điều kiện theo từng **nested configuration/feature group**, tránh “AND toàn cục” tại parent. Dùng `name` khi reference optional class chỉ bằng chuỗi, bảo vệ các method mang optional types bằng condition **cấp class**, và kiểm tra riêng classpath, property, bean conditions để thiết kế auto-configuration chính xác.
