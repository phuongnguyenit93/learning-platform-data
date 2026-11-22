# Chọn value hoặc name khi tham chiếu lớp tùy chọn — @ConditionalOnClass trong Spring Boot

> **Module:** Spring Boot — auto-configuration. **Nhóm:** Điều kiện classpath. **Mục tiêu:** Biết khi nào viết `@ConditionalOnClass(value = SomeClient.class)`, khi nào viết `@ConditionalOnClass(name = "com.vendor.SomeClient")`; hiểu vì sao tham chiếu `Class<?>` đôi khi an toàn ngay cả khi dependency không hiện diện lúc chạy, trường hợp nào bắt buộc dùng tên dạng chuỗi, và cách cô lập các `@Bean` method có chữ ký chứa kiểu tùy chọn. Ví dụ Java 17, Maven và Spring Boot 3.5.7.

## 1. Ý chính cần nhớ

`@ConditionalOnClass` là điều kiện Spring Boot kiểm tra **lớp được chỉ định có hiện diện trên classpath/class loader được sử dụng hay không** trước khi áp dụng một phần cấu hình.

Nó có hai thuộc tính quan trọng:

```java
Class<?>[] value() default {};
String[] name() default {};
```

Đây là hai **chữ ký annotation attributes** rút gọn, không phải file Java độc lập.

- `value` nhận literal kiểu `Class<?>`: ví dụ `@ConditionalOnClass(value = VendorClient.class)`, hoặc viết gọn `@ConditionalOnClass(VendorClient.class)`.
- `name` nhận chuỗi **tên fully-qualified của class**: ví dụ `@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")`.
- Khi chỉ định nhiều class trong danh sách `value`, nhiều tên trong `name`, hoặc cả hai, điều kiện yêu cầu **tất cả** các class được yêu cầu phải có mặt. Nó không tự hiểu các phần tử như OR.
- Cả hai dùng để **kiểm tra sự tồn tại của class**, không phải kiểm tra có bean, không tự tạo instance và không đảm bảo SDK có thể kết nối tới dịch vụ ngoài.
- Điều kiện này có thể xuất hiện trên class cấu hình hoặc `@Bean` method, nhưng mức an toàn với **lớp tùy chọn không có ở runtime** khác nhau; không thể chỉ dựa vào syntax `value` hay `name` để giải quyết mọi lỗi linkage.

**Quy tắc chọn nhanh:**

1. **Dùng trực tiếp trên một configuration class**, kiểu có mặt khi biên dịch nhưng có thể vắng mặt lúc chạy: dùng `value = SomeClient.class` được; Spring Boot đọc metadata annotation bằng ASM trước khi phải load class cấu hình.
2. **Không thể hoặc không muốn phụ thuộc compile-time vào kiểu đó**: dùng `name = "package.SomeClient"`.
3. **Viết custom composed/meta-annotation** chứa `@ConditionalOnClass`: **bắt buộc dùng `name`** thay vì `value`, theo hướng dẫn và Javadoc Spring Boot.
4. **`@Bean` method trả về hoặc nhận tham số có kiểu SDK tùy chọn**: đặt method trong một **nested `@Configuration(proxyBeanMethods = false)`** được gắn condition ở **cấp class**. Đổi `value` sang `name` ngay trên method **không phải** cách chữa đầy đủ nguy cơ JVM resolve chữ ký quá sớm.

## 2. Cơ chế kiểm tra classpath và vì sao value đôi khi an toàn

Ví dụ class trực tiếp:

```java
@AutoConfiguration
@ConditionalOnClass(VendorClient.class)
public class VendorAutoConfiguration {
    // Các @Bean cụ thể sẽ được đặt trong cấu hình tách biệt khi cần.
}
```

Đây là đoạn **minh họa chưa đủ import và file resource**. Lúc biên dịch, trình biên dịch Java phải tìm được `VendorClient` để tạo bytecode chứa annotation. Nhưng runtime của ứng dụng dùng thư viện này có thể **không có** JAR định nghĩa `VendorClient`.

Spring Boot đọc metadata của class cấu hình bằng ASM. Khi `@ConditionalOnClass` được đặt **trực tiếp trên class đó**, Boot có thể thấy tên class được biểu diễn trong bytecode mà không bắt JVM phải resolve `VendorClient.class` như một ứng dụng gọi trực tiếp một class literal trong code. Vì vậy `value` **là lựa chọn được hỗ trợ** trong vị trí này, dù dependency chỉ xuất hiện khi build thư viện.

Điều đó không biến mọi code có tham chiếu `VendorClient` trở nên an toàn. Ví dụ:

```java
public final class VendorConnector {
    private final VendorClient client;

    public VendorConnector(VendorClient client) {
        this.client = client;
    }
}
```

Nếu một code path phải load hoặc introspect `VendorConnector` trong khi `VendorClient` vắng mặt, việc resolve reference có thể gây `NoClassDefFoundError` hoặc lỗi linkage. Spring Boot chỉ hứa cơ chế an toàn **khi đọc trực tiếp annotation metadata trong tình huống phù hợp**, không loại trừ mọi phép nạp class do JVM thực hiện.

### value hoạt động tốt khi nào?

- Class có sẵn trong compile classpath của **module auto-configuration**.
- Spring Boot là bên đọc condition trực tiếp trên một **configuration class**.
- Những API có thể vắng mặt được cô lập trong class cấu hình con, không bị code khác chạm vào trước khi condition lọc.
- Bạn muốn IDE/refactoring phát hiện việc đổi tên class và compiler kiểm tra tên/kiểu ngay khi build.

### name hoạt động tốt khi nào?

- Chỉ có **fully-qualified name** của lớp tích hợp, chưa kéo SDK vào compile classpath.
- Muốn giữ auto-config module không phụ thuộc trực tiếp vào JAR chứa target type chỉ để kiểm tra presence.
- Viết **composed annotation** vì rule của Spring Boot yêu cầu string name.
- Muốn kiểm tra sự có mặt của class thuộc module tùy chọn mà không tạo import Java hay tham chiếu literal type trong source chứa annotation.

Cần nhớ: dùng `name` trong condition **không đủ để biên dịch code thực sự gọi constructor/method của SDK**. Nếu method body hay signature nhắc đến SDK class, module chứa code vẫn cần kiểu đó ở compile classpath hoặc phải dùng reflection/abstraction phù hợp.

## 3. So sánh value và name

| Tiêu chí | `value = VendorClient.class` | `name = "dev.lesson.vendor.VendorClient"` |
| --- | --- | --- |
| Dạng khai báo | Class literal | Chuỗi tên đầy đủ |
| SDK có cần hiện diện khi biên dịch source tham chiếu? | **Có** | **Không**, nếu phần code đó chỉ chứa chuỗi condition |
| IDE refactor package/class | Thường được cập nhật và kiểm tra bởi compiler | Dễ thành chuỗi lỗi thời, cần kiểm thử |
| Dùng trực tiếp trên `@Configuration` class | **An toàn theo cơ chế ASM được Boot hỗ trợ** | Có |
| Dùng bên trong custom meta-annotation | **Không nên; không được hỗ trợ an toàn như direct annotation** | **Phải dùng `name`** |
| SDK thiếu ở runtime | Condition không khớp nếu metadata được xử lý theo đường chuẩn | Condition không khớp |
| Tránh lỗi chữ ký `@Bean` nhắc SDK vắng mặt | Không tự bảo đảm | Không tự bảo đảm |
| Kiểm tra version/độ tương thích API của SDK | Không | Không |
| Tạo bean hoặc instance từ SDK | Không | Không |

### Cú pháp hợp lệ

```java
@ConditionalOnClass(VendorClient.class)
```

```java
@ConditionalOnClass(value = VendorClient.class)
```

```java
@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
```

```java
@ConditionalOnClass(
    value = { VendorClient.class, VendorMetrics.class },
    name = "com.example.optional.HealthApi"
)
```

Đây là **các đoạn annotation**, chưa phải class Java hoàn chỉnh. Trong ví dụ cuối, `VendorClient`, `VendorMetrics` cần compile classpath và cả ba class được yêu cầu phải tồn tại lúc condition khớp.

## 4. Trường hợp bắt buộc dùng name: custom composed annotation

Giả sử muốn chuẩn hóa annotation nội bộ:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
public @interface ConditionalOnVendorClient {
}
```

Đây là cấu trúc hoàn chỉnh của annotation nhưng cần các import Java/Spring; ở ví dụ project phía dưới sẽ có file đầy đủ.

`@ConditionalOnVendorClient` là **meta-annotation wrapper**: annotation do bạn định nghĩa chứa `@ConditionalOnClass`, sau đó bạn gắn wrapper lên một configuration class:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnVendorClient
static class VendorMarkerConfiguration {
    // ...
}
```

Spring Boot document/Javadoc nêu rõ nếu `@ConditionalOnClass` được dùng làm **meta-annotation**, phải tham chiếu class bằng thuộc tính `name`. Đừng biến wrapper thành:

```java
@ConditionalOnClass(VendorClient.class)
public @interface ConditionalOnVendorClient {
}
```

Dù code trên có thể biên dịch khi SDK có sẵn, nó **không có bảo đảm an toàn tương đương với direct class-level annotation** khi SDK bị loại khỏi runtime classpath.

**Lý do thiết kế:** Khi composition làm metadata được đọc theo những đường khác nhau, cơ chế xử lý `Class<?>` literal dựa trên ASM cho direct annotation không thể được giả định hoạt động y hệt. Chuỗi class name tránh ép một kiểu tùy chọn được resolve ở vị trí meta-annotation.

### Quy tắc kiểm thử

- Với direct annotation, test cả runtime có SDK và không có SDK.
- Với composed annotation, test thiếu SDK bằng cách thực sự loại lớp khỏi classloader; không chỉ đặt property false.
- Thử rename package hoặc upgrade SDK để phát hiện string `name` còn đúng hay không.
- Nếu annotation wrapper được public cho nhiều module, tài liệu hóa class name đang được check và rủi ro refactor.

## 5. Vấn đề khác: @ConditionalOnClass trên @Bean method

Cách viết dễ nhầm:

```java
@AutoConfiguration
public class RiskyVendorAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
    public VendorClient vendorClient() {
        return new VendorClient();
    }
}
```

Đây là **fragment phân tích rủi ro**, không phải cấu hình đề xuất để chạy. Chỗ nguy hiểm không nằm ở string name, mà ở **return type `VendorClient`** trong chữ ký method của class đang được Spring xử lý. Khi Spring/JVM phải load hoặc introspect class chứa method để tạo bean definitions, `VendorClient` có thể bị resolve **trước khi condition trên method kịp bảo vệ**.

Cách bền vững là tách:

```java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
    static class VendorPresentConfiguration {

        @Bean
        VendorClient vendorClient() {
            return new VendorClient();
        }
    }
}
```

Đây cũng chỉ là fragment vì thiếu imports và class SDK. Nhưng cấu trúc quan trọng là:

1. Outer auto-configuration có thể được khám phá và đọc metadata ngay cả khi SDK thiếu.
2. Nested configuration được **lọc ở cấp class** trước khi Spring cần xử lý các method có chữ ký SDK.
3. Chỉ khi SDK tồn tại, các method `@Bean` trong nested configuration mới được xử lý để tạo beans.
4. `proxyBeanMethods=false` là lựa chọn thông dụng để tránh proxy interception giữa các method bean.

Trong direct nested class condition, có thể dùng `value = VendorClient.class` nếu module compile được với SDK; hoặc `name="..."` theo nhu cầu. Ví dụ runnable dưới đây dùng **value trực tiếp** cho một nested configuration, và **name trong composed annotation** cho một nested configuration khác, giúp quan sát cả hai dạng.

## 6. Ví dụ runnable: SDK tùy chọn có mặt hoặc bị loại khỏi runtime

Ta sẽ dùng Maven reactor gồm ba module:

- `vendor-sdk`: JAR nhỏ có `VendorClient` làm SDK mô phỏng.
- `sample-autoconfigure`: JAR chứa auto-configuration, có dependency `vendor-sdk` ở mức compile **nhưng `optional=true`**. Vì optional, dependency **không tự truyền theo** qua module application.
- `app`: ứng dụng Spring Boot phụ thuộc `sample-autoconfigure`. Mặc định **không kéo vendor-sdk** vào runtime. Chỉ profile Maven `with-sdk` mới thêm vendor-sdk trực tiếp vào app.

Nhờ đó có thể build **cùng source** rồi chạy hai kết quả khác nhau: SDK vắng mặt và SDK có mặt.

### 6.1. Cấu trúc thư mục

```text
optional-class-demo/
├── pom.xml
├── vendor-sdk/
│   ├── pom.xml
│   └── src/main/java/dev/lesson/vendor/
│       └── VendorClient.java
├── sample-autoconfigure/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/dev/lesson/autoconfig/
│       │   │   ├── FeaturePort.java
│       │   │   ├── ConditionalOnVendorClient.java
│       │   │   └── VendorAutoConfiguration.java
│       │   └── resources/META-INF/spring/
│       │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│       └── test/java/dev/lesson/autoconfig/
│           └── VendorAutoConfigurationTest.java
└── app/
    ├── pom.xml
    └── src/main/java/dev/lesson/app/
        └── DemoApplication.java
```

Ứng dụng ở `dev.lesson.app`, còn auto-configuration ở `dev.lesson.autoconfig`, nên component scan mặc định của ứng dụng **không quét** class auto-configuration. Việc nó hoạt động phụ thuộc file imports.

### 6.2. Parent POM

File `optional-class-demo/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.lesson</groupId>
    <artifactId>optional-class-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <modules>
        <module>vendor-sdk</module>
        <module>sample-autoconfigure</module>
        <module>app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

### 6.3. Module vendor-sdk

`vendor-sdk/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>optional-class-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>vendor-sdk</artifactId>
</project>
```

`vendor-sdk/src/main/java/dev/lesson/vendor/VendorClient.java`:

```java
package dev.lesson.vendor;

public final class VendorClient {
    public String version() {
        return "vendor-1";
    }
}
```

Đây là SDK giả lập, không cần kết nối internet hoặc hệ thống bên ngoài.

### 6.4. Module sample-autoconfigure và optional dependency

`sample-autoconfigure/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>optional-class-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>sample-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>vendor-sdk</artifactId>
            <version>1.0.0</version>
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

Lưu ý: `optional=true` không loại dependency khỏi compile/runtime classpath **của chính module sample-autoconfigure**. Nó điều khiển tính **bắc cầu sang module khác** khi module đó phụ thuộc vào sample-autoconfigure. Vì thế test viết trong module auto-configuration mặc định có SDK, nhưng app phụ thuộc vào auto-configuration vẫn có thể chạy thiếu SDK.

### 6.5. Public contract không phụ thuộc vào SDK

`sample-autoconfigure/src/main/java/dev/lesson/autoconfig/FeaturePort.java`:

```java
package dev.lesson.autoconfig;

@FunctionalInterface
public interface FeaturePort {
    String message();
}
```

Interface này nằm trong JAR auto-config để app có thể dùng mà không phải import trực tiếp class SDK tùy chọn.

### 6.6. Composed annotation bắt buộc dùng name

`sample-autoconfigure/src/main/java/dev/lesson/autoconfig/ConditionalOnVendorClient.java`:

```java
package dev.lesson.autoconfig;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(name = "dev.lesson.vendor.VendorClient")
public @interface ConditionalOnVendorClient {
}
```

Đây là một **composed annotation**. Nếu thay `name` bằng `value = VendorClient.class` ngay ở phần khai báo annotation tự tổ hợp, bạn đã đi ngược quy tắc an toàn mà Spring Boot nêu cho meta-annotation. Vì tên class là chuỗi, hãy giữ test để phát hiện sai tên sau refactor.

### 6.7. Auto-configuration với value trực tiếp, name gián tiếp và fallback

`sample-autoconfigure/src/main/java/dev/lesson/autoconfig/VendorAutoConfiguration.java`:

```java
package dev.lesson.autoconfig;

import dev.lesson.vendor.VendorClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(value = VendorClient.class)
    static class SdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(VendorClient.class)
        public VendorClient vendorClient() {
            return new VendorClient();
        }

        @Bean
        @ConditionalOnMissingBean(FeaturePort.class)
        public FeaturePort sdkFeaturePort(VendorClient client) {
            return () -> "sdk:" + client.version();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnVendorClient
    static class ComposedAnnotationConfiguration {

        @Bean
        public String vendorMarker() {
            return "sdk-visible";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("dev.lesson.vendor.VendorClient")
    static class SdkAbsentConfiguration {

        @Bean
        @ConditionalOnMissingBean(FeaturePort.class)
        public FeaturePort fallbackFeaturePort() {
            return () -> "fallback";
        }
    }
}
```

**Đọc thiết kế theo ba nested class:**

1. `SdkPresentConfiguration` dùng `value = VendorClient.class` **trực tiếp ở cấp configuration class**, trường hợp được Boot hỗ trợ an toàn qua ASM. Bên trong mới khai báo `@Bean` method có return type/parameter của SDK.
2. `ComposedAnnotationConfiguration` gắn custom `@ConditionalOnVendorClient`, mà annotation này sử dụng **`name`** bên trong. Nó chỉ tạo marker `vendorMarker` khi SDK có mặt.
3. `SdkAbsentConfiguration` dùng `@ConditionalOnMissingClass`, vốn nhận **tên class dạng chuỗi**, để cung cấp fallback khi SDK vắng mặt.

Các cấu hình `SdkPresentConfiguration` và `SdkAbsentConfiguration` có classpath condition đối nghịch, vì vậy trong ngữ cảnh bình thường chỉ một bên đăng ký `FeaturePort`. Cả hai vẫn có `@ConditionalOnMissingBean(FeaturePort.class)` để tôn trọng bean do ứng dụng tự cung cấp nếu có.

**Vì sao không gắn `@ConditionalOnClass` lên outer `VendorAutoConfiguration`?** Vì outer chứa **cả fallback**. Nếu chỉ cần SDK mới được nhập outer, fallback sẽ không thể chạy khi SDK vắng mặt. Condition được đặt chính xác tại nhánh feature phụ thuộc SDK.

**Vì sao `VendorClient.class` ở import của outer vẫn có thể xuất hiện trong source?** Compile-time có dependency `vendor-sdk`. Khi runtime SDK vắng mặt, class literal nằm ở annotation của nested configuration, còn method sử dụng type tùy chọn được cách ly trong nested configuration. Điều này là mẫu Spring Boot khuyến nghị cho optional dependency, không phải lời bảo đảm cho mọi code tùy tiện tham chiếu SDK trong outer.

### 6.8. File đăng ký auto-configuration

Tạo `sample-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.lesson.autoconfig.VendorAutoConfiguration
```

File chỉ liệt kê **outer auto-configuration class**. Các nested configuration được tìm qua cấu trúc của class đó khi Spring xử lý cấu hình. Không cần thêm chúng thành các ứng viên top-level trong file imports.

### 6.9. Module app và Maven profile bật SDK

`app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>dev.lesson</groupId>
        <artifactId>optional-class-demo</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>dev.lesson</groupId>
            <artifactId>sample-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
    <profiles>
        <profile>
            <id>with-sdk</id>
            <dependencies>
                <dependency>
                    <groupId>dev.lesson</groupId>
                    <artifactId>vendor-sdk</artifactId>
                    <version>1.0.0</version>
                </dependency>
            </dependencies>
        </profile>
    </profiles>
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

Profile nằm ở **app**, nên khi chạy `-Pwith-sdk` nó bổ sung `vendor-sdk` thành **dependency trực tiếp** của ứng dụng. Không cần sửa mã nguồn hoặc file imports.

### 6.10. Application quan sát tình trạng classpath

`app/src/main/java/dev/lesson/app/DemoApplication.java`:

```java
package dev.lesson.app;

import dev.lesson.autoconfig.FeaturePort;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            FeaturePort port = context.getBean(FeaturePort.class);

            System.out.println("feature.message=" + port.message());
            System.out.println(
                "vendor.client.bean=" + context.containsBean("vendorClient")
            );
            System.out.println(
                "composed.marker.bean=" + context.containsBean("vendorMarker")
            );
        }
    }
}
```

Ứng dụng **không import `VendorClient`**. Nó chỉ phụ thuộc `FeaturePort` là interface luôn có. Điều này có ý nghĩa khi SDK là một integration thực sự optional.

### 6.11. Chạy khi SDK vắng mặt

Trong thư mục root `optional-class-demo/`, cần Java 17 và Maven:

```bash
mvn -q clean package
java -jar app/target/app-1.0.0.jar
```

Khi Maven build theo profile mặc định, module `sample-autoconfigure` vẫn compile với SDK; nhưng `app` **không kéo dependency optional đó** vào runtime JAR. Sau khi bỏ qua log startup, ba dòng do code in là:

```text
feature.message=fallback
vendor.client.bean=false
composed.marker.bean=false
```

Nguyên nhân:

- `SdkPresentConfiguration` không khớp điều kiện direct `value` vì `VendorClient` không nằm trên runtime classpath của app.
- `@ConditionalOnVendorClient` không khớp vì name `dev.lesson.vendor.VendorClient` không tìm được.
- `@ConditionalOnMissingClass` khớp, tạo `fallbackFeaturePort`.

Đây là minh chứng rằng **chỉ vì một thư viện có code tham chiếu SDK lúc biên dịch không có nghĩa ứng dụng phải mang SDK đó theo ở runtime**, nếu code được tổ chức và bảo vệ condition đúng.

### 6.12. Chạy khi SDK có mặt

Build lại cùng project, bật profile:

```bash
mvn -q -Pwith-sdk clean package
java -jar app/target/app-1.0.0.jar
```

Bây giờ app chứa dependency `vendor-sdk` trực tiếp. Ba dòng ứng dụng in (bỏ qua log startup):

```text
feature.message=sdk:vendor-1
vendor.client.bean=true
composed.marker.bean=true
```

Lúc này, cả condition dùng `value` trực tiếp và condition `name` bên trong composed annotation đều khớp. Nhánh fallback bị loại vì `@ConditionalOnMissingClass` không còn khớp.

**Chú ý khi chạy lần lượt hai biến thể:** Lệnh `clean package` phải được thực hiện lại khi đổi profile, nếu không bạn có thể đang chạy executable JAR được đóng gói từ profile cũ. Hai output là kết quả kỳ vọng khi các dependency đúng như cấu trúc ví dụ, không tính log Spring Boot.

## 7. Kiểm thử hai classpath bằng FilteredClassLoader

Vì project auto-config có SDK trong compile/test classpath, ta dùng `FilteredClassLoader` để giả lập việc SDK không nhìn thấy trong một context. Cách này phù hợp khi test classpath vốn cần SDK để biên dịch code, nhưng production consumer có thể không mang SDK.

File `sample-autoconfigure/src/test/java/dev/lesson/autoconfig/VendorAutoConfigurationTest.java`:

```java
package dev.lesson.autoconfig;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class VendorAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(VendorAutoConfiguration.class)
        );

    @Test
    void sdkPresentAllowsDirectValueAndComposedName() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FeaturePort.class);
            assertThat(context.getBean(FeaturePort.class).message())
                .isEqualTo("sdk:vendor-1");
            assertThat(context).hasBean("vendorClient");
            assertThat(context).hasBean("vendorMarker");
            assertThat(context).doesNotHaveBean("fallbackFeaturePort");
        });
    }

    @Test
    void sdkAbsentAllowsFallbackWithoutLinkageError() {
        runner.withClassLoader(
            new FilteredClassLoader("dev.lesson.vendor")
        ).run(context -> {
            assertThat(context).hasSingleBean(FeaturePort.class);
            assertThat(context.getBean(FeaturePort.class).message())
                .isEqualTo("fallback");
            assertThat(context).doesNotHaveBean("vendorClient");
            assertThat(context).doesNotHaveBean("vendorMarker");
        });
    }

    @Test
    void userPortMakesSdkDefaultBackOff() {
        runner.withUserConfiguration(UserPortConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(FeaturePort.class);
                assertThat(context.getBean(FeaturePort.class).message())
                    .isEqualTo("from-user");
                assertThat(context).doesNotHaveBean("sdkFeaturePort");
                assertThat(context).hasBean("vendorMarker");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPortConfiguration {
        @Bean
        FeaturePort userFeaturePort() {
            return () -> "from-user";
        }
    }
}
```

Chạy từ root:

```bash
mvn -q test
```

Kỳ vọng **3 test pass** trong module `sample-autoconfigure` khi dùng các source trên:

1. Có SDK: cả direct `value` và composed `name` đều khớp.
2. SDK bị ẩn: fallback được tạo, class dùng SDK bị loại trước khi gây lỗi linkage.
3. User đã cung cấp `FeaturePort`: auto-configuration back off cho bean mặc định theo interface.

**Giới hạn của test này:** `FilteredClassLoader` giúp test classloader visibility; nó không thay thế hoàn toàn việc kiểm chứng executable JAR production. Vì thế, hai lệnh `java -jar` ở mục 6 vẫn có giá trị trong smoke test đóng gói thực tế.

Class test cùng package `dev.lesson.autoconfig` nhưng application có main class ở `dev.lesson.app`, nên `UserPortConfiguration` lồng trong class test không bị application component scan mặc định của demo app thu nhận. Runner cũng chỉ đưa vào cấu hình đó ở test thứ ba.

## 8. Có cần dùng name cho mọi class có thể vắng mặt không?

**Không.** Đây là nhầm lẫn thường gặp.

Spring Boot chủ đích hỗ trợ `@ConditionalOnClass(value = OptionalSdk.class)` khi annotation được gắn **trực tiếp** vào configuration class và metadata được đọc qua ASM. Việc đổi tất cả value thành name có thể làm mất khả năng compiler/IDE bắt lỗi rename, không mang lại lợi ích an toàn tương ứng trong trường hợp đã được hỗ trợ.

Tuy nhiên, có ba tình huống thúc đẩy dùng name:

- **Meta-annotation:** quy định rõ ràng, dùng `name`.
- **Không có SDK trong compile dependency:** chỉ tham chiếu tên không yêu cầu Java compiler biết class đó.
- **Muốn giảm coupling trong metadata:** không gắn literal type reference ở class cần dùng condition; test sẽ bảo vệ chuỗi.

Ngược lại, nếu method body **thực sự** viết `new OptionalSdk()`, string `name` không làm module tự biên dịch mà không có SDK. Không trộn “giảm compile-time dependency cho điều kiện” với “giảm compile-time dependency cho mọi code”.

## 9. Tránh lỗi NoClassDefFoundError và linkage ngoài ý muốn

### 9.1. Điều kiện không bảo vệ mọi code path

Ví dụ có rủi ro:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
public class RiskyAutoConfiguration {

    private final com.vendor.Client eagerClient =
        new com.vendor.Client();
}
```

**Đây là minh họa không dùng để chạy.** Condition có thể khiến class cấu hình bị bỏ qua theo đường auto-configuration chuẩn, nhưng **một nơi khác** vẫn có thể trực tiếp tạo/load `RiskyAutoConfiguration`. Sử dụng condition không thay thế thiết kế cô lập dependency tùy chọn.

Cách bền vững thường là outer config không nhắc tới SDK trong method signature hoặc field, và nested config có class-level condition chứa mọi `@Bean` method sử dụng SDK.

### 9.2. @ConditionalOnClass chỉ kiểm tra hiện diện, không kiểm tra API compatibility

Khi `VendorClient.class` có trên classpath, condition khớp. Nhưng:

- API method có thể bị xóa/đổi giữa phiên bản SDK.
- Có thể thiếu một transitive dependency mà SDK cần khi khởi tạo.
- Driver/native library, credentials hoặc dịch vụ ngoài có thể không sẵn sàng.
- Class có thể tồn tại nhưng không tương thích với JVM/platform hiện tại.

Do đó không suy từ `@ConditionalOnClass` rằng tích hợp chắc chắn chạy thành công. Với API/version tùy chọn phức tạp, cần dependency management rõ, compatibility tests và cách fail-fast/diagnostic phù hợp. Tránh bắt `NoClassDefFoundError` rộng rồi âm thầm tiếp tục với trạng thái hỏng.

### 9.3. Type reference ẩn trong annotation khác

Ngay cả khi outer auto-configuration chỉ dùng `name`, một `@Import(SomeSdkConfiguration.class)` không được bảo vệ hoặc class signature tham chiếu SDK có thể làm Spring/JVM cần load class không có. Hãy xét **toàn bộ dependency graph của configuration**, không chỉ một dòng condition.

### 9.4. SDK optional trong Maven

Maven `optional=true` ở dependency của module auto-config nghĩa là dependency đó không tự bắc cầu sang consumer, không có nghĩa loại khỏi compile của module producer. Tương đương về mục tiêu ở Gradle có thể dùng `compileOnly` và bố trí runtime dependencies phù hợp, nhưng syntax/variant resolution của Gradle khác Maven; đừng giả định hai hệ thống đóng gói y hệt.

## 10. Các nhầm lẫn liên quan value/name cần tránh

`@ConditionalOnClass` không phải annotation duy nhất có các thuộc tính tên giống vậy.

| Annotation | `value` | `name` | Câu hỏi nó trả lời |
| --- | --- | --- | --- |
| `@ConditionalOnClass` | `Class<?>[]` | `String[]` | Những **class** được yêu cầu có mặt không? |
| `@ConditionalOnMissingClass` | Không có `value` dạng class literal | `String[] value` | Những class chỉ định có **vắng mặt** không? |
| `@ConditionalOnBean` | Bean type (class literal) | Bean **name** | Có bean tương ứng được biết ở thời điểm xét không? |
| `@ConditionalOnMissingBean` | Bean type (class literal) | Bean **name** | Có thiếu bean tương ứng ở thời điểm xét không? |
| `@ConditionalOnProperty` | Alias của `name` property | Property name | Environment có key/value đúng không? |

**Quan trọng:** `name` của `@ConditionalOnClass` nghĩa là **tên fully-qualified của Java class**; `name` của `@ConditionalOnBean` nghĩa là **tên Spring bean**, còn `name` của `@ConditionalOnProperty` nghĩa là **tên cấu hình property**. Cùng từ `name` nhưng ý nghĩa phụ thuộc annotation.

`@ConditionalOnMissingClass` trên Spring Boot 3.5 sử dụng chuỗi tên class trong `value` (ví dụ `@ConditionalOnMissingClass("dev.lesson.vendor.VendorClient")`), không dùng `value = VendorClient.class`. Điều kiện này được thiết kế để diễn đạt sự vắng mặt của class mà không bắt buộc tham chiếu kiểu cần có compile-time.

## 11. Dùng value/name với nhiều optional SDK và logic AND/OR

### 11.1. AND: mọi class đều cần có

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = {
    "com.vendor.Client",
    "com.vendor.Metrics"
})
class ClientMetricsConfiguration {
}
```

Class chỉ được áp dụng khi **cả hai** type có thể được tìm qua classloader. Nếu chỉ có `Client` mà thiếu `Metrics`, điều kiện không khớp.

Dạng tương đương ở cấu hình có compile dependency:

```java
@ConditionalOnClass(value = {
    Client.class,
    Metrics.class
})
```

Đây là **fragment**, chưa có imports.

### 11.2. OR: ít nhất một SDK có mặt

**Không** dùng danh sách hai tên trong cùng `@ConditionalOnClass` với kỳ vọng OR. Có thể tách thành **hai configuration class riêng**, mỗi class gắn condition cho SDK tương ứng rồi thiết kế bean back-off để chúng không xung đột.

Ví dụ khái niệm:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.alpha.Client")
class AlphaIntegrationConfiguration {
    // ...
}

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.beta.Client")
class BetaIntegrationConfiguration {
    // ...
}
```

Hai fragments chỉ minh họa cách tách nhánh; nếu cả hai SDK cùng hiện diện, hai class đều có thể được áp dụng. Nếu chúng cùng đăng ký một bean type, cần nêu rõ ưu tiên/condition/ordering. Với logic phức tạp, có thể viết `Condition` hoặc dùng các cấu trúc condition lồng thích hợp, nhưng cần kiểm thử đủ trường hợp.

## 12. Chẩn đoán khi conditional class không hoạt động

### Lỗi A — Class được khai báo đúng nhưng condition không khớp

Kiểm tra chính xác **runtime classpath**, không chỉ compile classpath của module auto-config. Trong Maven, `optional=true` hoặc `scope=provided`/`test` có thể khiến JAR không tới runtime app như bạn nghĩ.

Trong demo, chạy ở root:

```bash
jar tf app/target/app-1.0.0.jar
```

Quan sát trong danh sách entry có `BOOT-INF/lib/vendor-sdk-1.0.0.jar` hay không. Nếu dùng profile `with-sdk`, entry này được kỳ vọng có. Không có profile, nó được kỳ vọng vắng mặt.

### Lỗi B — Chỉ thêm @ConditionalOnClass vào method có return type SDK

Dù dùng `name`, một JVM/Spring code path vẫn có thể resolve method signature sớm. Di chuyển method vào **nested configuration class** được gắn class-level condition và kiểm thử thiếu dependency thật.

### Lỗi C — Composed annotation dùng value

Sử dụng `@ConditionalOnClass(name = "...")` trong annotation tự tổ hợp. Đừng dựa vào việc test luôn có SDK nên phương án `value` “có vẻ vẫn chạy”.

### Lỗi D — name sai package sau refactor

String name không được Java compiler kiểm tra. Dùng integration test có SDK để khẳng định condition thực sự khớp và bean xuất hiện; IDE rename có thể bỏ sót chuỗi.

### Lỗi E — Nhầm “class tồn tại” với “bean tồn tại”

`@ConditionalOnClass` không bảo đảm một bean của class đó được đăng ký. Nếu cần bean, sử dụng `@ConditionalOnBean` theo điều kiện đúng và quan tâm tới thứ tự đăng ký bean definitions; hai loại condition giải quyết **hai câu hỏi khác nhau**.

### Lỗi F — Auto-configuration không có trong imports

Class có annotation `@AutoConfiguration` nhưng không được liệt kê trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` thì Spring Boot không tự tìm nó qua auto-configuration discovery chuẩn. Đừng chữa bằng cách mở `@ComponentScan` sang package autoconfigure.

### Lỗi G — Thêm nhiều tên nhưng muốn OR

Trong `@ConditionalOnClass(name={"A","B"})` phải có **A và B** mới khớp. Nếu muốn một trong hai, tách cấu hình hoặc viết condition logic tương ứng.

### Lỗi H — Class hiện diện nhưng API không tương thích

Condition classpath vẫn có thể khớp. Hãy kiểm tra dependency versions, method signatures, transitive dependencies, linkage failures, và integration test đúng runtime environment; condition presence không phải “health check”.

### Lỗi I — Không có SDK nhưng app vẫn cố gọi method SDK

Kiểm tra có class `@Configuration`/`@Component` khác đang được scan/import không; một condition trên một auto-configuration không chặn mọi code trong project. Tách optional dependency vào module và nested config riêng.

### Condition Evaluation Report

Có thể chạy app với:

```bash
java -jar app/target/app-1.0.0.jar --debug
```

Spring Boot report sẽ giúp kiểm tra classpath condition matched/unmatched. Khi xem log, phân biệt source nằm trong nested config nào và condition nào áp dụng cho source đó.

## 13. Checklist thiết kế production

1. **Xác định optional class** theo tên đầy đủ và artifact chứa nó. Đừng chỉ ghi một simple name không kèm package.
2. **Chọn đúng vị trí annotation:** direct class-level, custom meta-annotation hay method-level? Đây là bước quan trọng hơn việc “thích value hay name”.
3. **Direct class-level:** dùng `value` khi compile classpath có kiểu và muốn type safety/refactor support.
4. **Meta-annotation:** luôn dùng `name` cho `@ConditionalOnClass`.
5. **Không có compile dependency:** dùng string `name`, miễn là code không dùng trực tiếp SDK type ở nơi khác mà thiếu compile dependency.
6. **SDK type trong @Bean signature:** cô lập method trong nested `@Configuration` với condition ở cấp class.
7. **Đừng đặt classpath condition quá rộng:** nếu cần fallback, outer auto-configuration không nên bị tắt chỉ vì SDK chính vắng mặt.
8. **Bean fallback/back-off:** dùng `@ConditionalOnMissingBean` theo public contract khi phù hợp; tránh đăng ký hai implementation không chủ đích.
9. **Maven optional:** xác minh runtime JAR thực sự có hoặc không có dependency, không chỉ nhìn việc build thư viện thành công.
10. **Kiểm thử đủ hai trạng thái:** class present và absent, ưu tiên kết hợp `FilteredClassLoader` và executable-JAR smoke tests.
11. **Kiểm thử meta-annotation:** vì string name không được compiler hỗ trợ rename, giữ test có SDK và thiếu SDK.
12. **Quan sát nguyên nhân:** sử dụng Condition Evaluation Report và classpath dependency tree thay vì chỉ suy luận từ `NoClassDefFoundError`.
13. **Không nhầm presence với functionality:** muốn bảo đảm SDK tương thích, cần integration test với phiên bản SDK thực.
14. **Không tự mở component scan:** auto-configuration được nạp qua imports, không cần quét package thư viện.

## 14. Câu hỏi tự kiểm tra

1. Trên configuration class trực tiếp, `@ConditionalOnClass(VendorClient.class)` có thể an toàn khi runtime thiếu SDK không? **Có**, nhờ Boot đọc annotation metadata bằng ASM theo đường được hỗ trợ.
2. Khi tự tạo annotation `@ConditionalOnVendorClient` meta-annotated bằng `@ConditionalOnClass`, nên dùng `value` hay `name`? **Phải dùng `name`.**
3. Không có SDK trên compile classpath, muốn kiểm tra class bằng condition nhưng không gọi API trực tiếp: dùng gì? **`@ConditionalOnClass(name = "fully.qualified.ClassName")`.**
4. Chỉ đổi method-level `@ConditionalOnClass(value=Sdk.class)` thành `name="..."` có giải quyết mọi lỗi method return type chứa SDK không? **Không**; cần nested configuration được bảo vệ ở class-level.
5. `@ConditionalOnClass(name={"A","B"})` là AND hay OR? **AND**.
6. `@ConditionalOnClass` có chứng minh đã có Spring bean của SDK không? **Không**; nó kiểm tra classpath.
7. Vì sao `optional=true` trong POM của auto-config không đồng nghĩa thiếu SDK lúc test module đó? **Vì optional chủ yếu làm dependency không bắc cầu tới consumer, còn module producer vẫn thấy SDK.**
8. Trong ví dụ, app không bật `with-sdk` sẽ dùng implementation nào? **Fallback**.
9. Với `with-sdk`, condition nào giúp tạo marker? **Custom composed annotation dùng `name`**.
10. Nếu vendor SDK tồn tại nhưng method đã bị xóa trong version mới, classpath condition có báo lỗi trước không? **Không bảo đảm**; nó không kiểm tra tương thích toàn bộ API.
11. Tại sao outer auto-configuration không được gắn điều kiện có SDK? **Vì outer còn sở hữu nhánh fallback cần hoạt động khi SDK thiếu.**
12. Test bằng `FilteredClassLoader` có thay thế kiểm tra executable JAR không? **Không hoàn toàn**; nên test cả packaging thực tế.
13. `@ConditionalOnMissingClass` có `Class<?>[] value` giống `@ConditionalOnClass` không? **Không**; dùng chuỗi tên class.
14. Nếu class `VendorClient` có trong JAR nhưng application classloader không thể thấy nó, `@ConditionalOnClass` có thể không khớp không? **Có**; kiểm tra visibility theo class loader thực tế.

## Tài liệu chính thức

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): ghi rõ quy tắc direct class-level `value`, meta-annotation `name` và nested configuration cho method dùng optional types.
- [Spring Boot 3.5 — ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html): thông tin chính thức về `value()`/`name()`, ASM và lưu ý `@Bean` method.
- [Spring Boot 3.5 — ConditionalOnMissingClass Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html): cú pháp kiểm tra class vắng mặt.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): điều kiện, loại trừ, cấu hình mặc định và Condition Evaluation Report.
- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` và `FilteredClassLoader`.
- [Maven — Optional Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html): cách `optional=true` thay đổi phụ thuộc bắc cầu.
