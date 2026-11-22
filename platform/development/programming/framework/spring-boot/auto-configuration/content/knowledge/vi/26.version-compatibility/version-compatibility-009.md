# Phân biệt API công khai ổn định với lớp nội bộ không bảo đảm tương thích

## 1. Vì sao phải phân biệt?

Khi phát triển với Spring Boot, IDE có thể hiển thị rất nhiều class và method của framework. Một số là API được thiết kế để ứng dụng hoặc thư viện khác sử dụng lâu dài. Một số khác chỉ phục vụ cách Spring Boot đang triển khai một tính năng ở phiên bản hiện tại.

Hai nhóm này có thể đều xuất hiện trong Javadoc, nằm trong JAR và thậm chí có modifier `public`. Điều đó không khiến chúng có cùng cam kết tương thích.

Nếu ứng dụng phụ thuộc vào chi tiết nội bộ, một lần nâng Spring Boot có thể làm code không biên dịch, phát sinh `NoSuchMethodError`, lỗi khởi động hoặc thay đổi hành vi. Nếu ứng dụng phụ thuộc vào hợp đồng API được công bố và kiểm thử đúng cách, việc nâng cấp sẽ dễ dự đoán hơn.

Bài này giải thích cách nhận diện API công khai, lớp nội bộ và extension point được hỗ trợ; cách thiết kế thư viện auto-configuration có bề mặt API nhỏ; và cách kiểm thử để tránh khóa ứng dụng vào implementation detail. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.13.

## 2. Bốn khái niệm không nên đánh đồng

### 2.1. Java visibility: code có thể truy cập được hay không?

Java dùng các modifier:

| Modifier | Phạm vi truy cập |
|---|---|
| `public` | Có thể truy cập từ code ở package khác nếu module/classpath cho phép |
| `protected` | Truy cập trong package và từ subclass theo quy tắc Java |
| package-private (không ghi modifier) | Chỉ truy cập trong cùng package |
| `private` | Chỉ truy cập trong phạm vi class khai báo |

Đây là quy tắc của ngôn ngữ Java. Nó trả lời câu hỏi **compiler có cho phép tham chiếu tới thành phần này không?**

Nó không tự trả lời câu hỏi **nhà phát triển framework có cam kết giữ thành phần này tương thích cho người dùng không?**

Một class có thể cần `public` để framework gọi qua package khác, để reflection tạo instance, hoặc để một class khác trong thư viện sử dụng. Nhà phát triển vẫn có thể xem class đó là implementation detail và không hỗ trợ ứng dụng bên ngoài phụ thuộc trực tiếp vào nó.

### 2.2. Public API: hợp đồng được công bố cho người sử dụng

Public API là bề mặt mà thư viện chủ động cho người dùng dựa vào. Nó thường bao gồm:

- Type, constructor, method và annotation được tài liệu hướng dẫn sử dụng.
- Interface hoặc callback được công bố như extension point.
- Property key, kiểu dữ liệu, giá trị mặc định và ý nghĩa được tài liệu hóa.
- Bean type hoặc customization hook mà thư viện cam kết cung cấp.
- Resource name hoặc factory key nếu tài liệu yêu cầu người dùng khai báo chúng.
- Hành vi, lỗi và quy tắc tương thích được tài liệu mô tả.

Một API được công bố vẫn có thể thay đổi trong tương lai. Cam kết tương thích phụ thuộc chính sách phiên bản, deprecation và phạm vi phiên bản mà thư viện hỗ trợ. “Public API” không có nghĩa “bất biến mãi mãi”.

### 2.3. Internal API / implementation detail

Thành phần nội bộ phục vụ cách thư viện triển khai tính năng. Ví dụ:

- Lớp `internal`, `impl`, parser, registrar hoặc helper chỉ dùng trong framework.
- Nested configuration class bên trong một auto-configuration.
- Method `@Bean` chỉ tạo implementation mặc định.
- Tên bean được sinh từ tên method nhưng không được tài liệu cam kết.
- Field, constructor, method protected hoặc package-private không được công bố là extension point.
- Cấu trúc metadata, thứ tự gọi nội bộ hoặc class loader được dùng bên trong.

Các thành phần này có thể được đổi tên, tách, gộp hoặc thay thế khi implementation tiến hóa. Nếu không có hợp đồng hỗ trợ riêng, người dùng không nên giả định chúng được giữ tương thích.

### 2.4. Extension point: điểm mở rộng được hỗ trợ

Một extension point là cách thư viện chủ động cho ứng dụng tùy biến. Ví dụ:

- Cung cấp interface `CatalogClient` để ứng dụng tự viết implementation.
- Cho phép ứng dụng khai báo bean thay thế thông qua `@ConditionalOnMissingBean`.
- Cung cấp interface `CatalogClientCustomizer` và tài liệu cách đăng ký.
- Cung cấp `@ConfigurationProperties` để người dùng cấu hình bằng property.
- Cung cấp annotation hoặc SPI được tài liệu hướng dẫn sử dụng.

Không phải mọi class có thể subclass đều là extension point. Hãy tìm lời hướng dẫn rõ ràng về mục đích, thứ tự gọi, lifecycle và trách nhiệm của implementation.

## 3. Một quy tắc rất cụ thể từ tài liệu Spring Boot

Spring Boot Reference 3.3 đưa ra một ví dụ quan trọng về auto-configuration classes:

> Dù các auto-configuration class có thể là public, chỉ tên class dùng để loại trừ auto-configuration được xem là public API. Nội dung bên trong class, như nested configuration class và bean method, chỉ dành cho sử dụng nội bộ.

Điều này có nghĩa ứng dụng có thể cần biết tên của một auto-configuration để loại trừ nó, nhưng không nên phụ thuộc vào các chi tiết như:

- `SomeAutoConfiguration.SomeNestedConfiguration`.
- Method `dataSource(...)` hoặc `redisConnectionFactory(...)` bên trong auto-configuration.
- Tên bean mặc định được suy ra từ tên method.
- Thứ tự khai báo method hoặc cấu trúc nested class.

Đây là quy tắc tài liệu nêu cho các auto-configuration của Spring Boot. Khi tự viết starter, hãy áp dụng cùng cách thiết kế: chỉ công bố những điểm mà thư viện thật sự muốn hỗ trợ; giữ nested configuration và bean factory method ở phạm vi nội bộ nếu chúng không phải extension point.

Nếu thư viện cam kết người dùng có thể loại trừ auto-configuration, hãy xem tên class được liệt kê trong `AutoConfiguration.imports` là một phần hợp đồng cần quản lý. Khi đổi package hoặc tên class, phải cân nhắc tác động tới người dùng đang dùng `exclude` hoặc `excludeName`.

### 3.1. Một class public vẫn có thể chỉ dành cho nội bộ framework

Javadoc của Spring Framework mô tả `SpringFactoriesLoader` là cơ chế factory loading tổng quát **dành cho sử dụng nội bộ trong framework**, dù bản thân class có modifier `public`.

Đây là ví dụ rõ ràng rằng:

- Class public có thể được nhìn thấy và import từ code ứng dụng.
- Javadoc có thể giới hạn mục đích sử dụng của class đó.
- Người dùng không nên tự suy ra một compatibility guarantee chỉ từ khả năng truy cập.

Khi đọc Javadoc, hãy chú ý các câu như `for internal use`, `not intended for direct use`, `do not use directly` hoặc mô tả rõ class chỉ là implementation. Những ghi chú này quan trọng hơn việc IDE có autocomplete class đó hay không.

## 4. Cách nhận diện một API có được hỗ trợ hay không

Không có một dấu hiệu đơn lẻ nào đủ để kết luận. Hãy kết hợp nhiều nguồn.

### 4.1. Đọc tài liệu chính thức và mục đích của API

Một thành phần có cơ sở để xem là API được hỗ trợ khi tài liệu:

- Giải thích rõ ứng dụng nên gọi hoặc triển khai nó như thế nào.
- Nêu tham số, lifecycle, kết quả và giới hạn.
- Có ví dụ sử dụng từ phía consumer.
- Mô tả cách tùy biến hoặc thay thế implementation.
- Đề cập compatibility, deprecation hoặc migration khi API thay đổi.

Javadoc có mô tả đầy đủ là tín hiệu tốt, nhưng vẫn cần đọc phần ghi chú về intended use. Một trang Javadoc có thể tồn tại chỉ để giải thích implementation cho người đọc source.

### 4.2. Kiểm tra package và tên class

Tên package như `internal`, `impl`, `support` hoặc `configuration` có thể là dấu hiệu cần thận trọng. Tuy nhiên, tên package không phải một chuẩn bảo đảm tuyệt đối:

- Có package `autoconfigure` chứa annotation/API công khai.
- Có package mang tên trung tính nhưng chứa helper nội bộ.
- Một class trong package công khai vẫn có thể được Javadoc đánh dấu internal.

Vì vậy, dùng package name như tín hiệu ban đầu, sau đó xác minh bằng Javadoc, reference documentation và ví dụ chính thức.

### 4.3. Kiểm tra annotation và trạng thái deprecation

Các annotation/metadata có thể cung cấp tín hiệu:

| Dấu hiệu | Cách hiểu |
|---|---|
| `@Deprecated` | Thành phần đã bị đánh dấu không nên tiếp tục dùng; đọc lý do và replacement |
| `@Deprecated(since = "...")` | Cho biết phiên bản bắt đầu deprecated |
| `@Deprecated(forRemoval = true)` | Có ý định loại bỏ trong tương lai; xem Javadoc/release notes để biết mốc và thay thế |
| `@since` trong Javadoc | Phiên bản giới thiệu API; không tự chứng minh API có compatibility guarantee |
| Ghi chú “internal use only” | Không nên coi thành phần là extension point cho ứng dụng |
| Ví dụ consumer trong tài liệu chính thức | Tín hiệu mạnh về cách sử dụng được hỗ trợ |

Không phải mọi dự án đều dùng cùng annotation hoặc cùng quy tắc. Đừng tự suy ra rằng thiếu `@Deprecated` nghĩa là API chắc chắn ổn định.

### 4.4. Tìm contract thay thế

Nếu một class bị deprecated hoặc được mô tả là internal, hãy tìm:

- Interface hoặc builder được đề xuất thay thế.
- Annotation mới thay cho class cũ.
- Customizer/callback được công bố.
- Configuration property thay cho việc gọi trực tiếp implementation.
- Release notes hoặc migration guide của phiên bản tương ứng.

Nếu không tìm được replacement, cần đọc issue/changelog hoặc tài liệu của module trước khi quyết định nâng cấp.

## 5. Ví dụ: auto-configuration có API công khai nhỏ và implementation nội bộ

Giả sử thư viện Catalog cung cấp chức năng tìm sản phẩm. Người dùng cần một contract để gọi service và một nhóm property để cấu hình timeout.

Thiết kế API công khai:

- `CatalogClient`: interface mà nghiệp vụ ứng dụng phụ thuộc.
- `CatalogProperties`: property contract có prefix `acme.catalog`.
- `CatalogAutoConfiguration`: class được công bố trong imports; thư viện cam kết tên class để ứng dụng có thể loại trừ nếu cần.
- Việc tạo client mặc định, nested configuration và implementation cụ thể được giữ nội bộ.
- Ứng dụng có thể cung cấp bean `CatalogClient` của riêng mình; auto-configuration mặc định sẽ back off.

Mô hình phụ thuộc:

```text
APPLICATION CODE
      |
      v
CatalogClient  <------ User implementation (optional)
      ^
      |
Default implementation
      ^
      |
Internal @Bean factory method
      ^
      |
Internal nested configuration
      ^
      |
CatalogAutoConfiguration
      ^
      |
AutoConfiguration.imports
```

Code nghiệp vụ chỉ phụ thuộc vào `CatalogClient`. Nó không cần biết thư viện dùng HTTP client, SDK nào hoặc cấu trúc nested configuration ra sao.

## 6. Ví dụ Maven hoàn chỉnh với Spring Boot 3.3.13

### 6.1. Cấu trúc thư mục

```text
catalog-api-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/catalog/
    │   │   ├── CatalogClient.java
    │   │   └── CatalogProperties.java
    │   ├── java/com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/catalog/autoconfigure/
        └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>catalog-api-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.3. CatalogClient.java — public API

```java
package com.acme.catalog;

/**
 * Public contract for looking up catalog items.
 * Consumers may inject this interface or provide their own bean.
 */
@FunctionalInterface
public interface CatalogClient {

    String findById(String id);
}
```

Đây là contract mà code nghiệp vụ sử dụng. Thư viện cần giữ ý nghĩa của method, kiểu tham số và kết quả trong phạm vi compatibility policy đã công bố.

### 6.4. CatalogProperties.java — public configuration contract

```java
package com.acme.catalog;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Documented configuration for the Catalog integration.
 */
@ConfigurationProperties(prefix = "acme.catalog")
public class CatalogProperties {

    private Duration timeout = Duration.ofSeconds(2);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Prefix `acme.catalog` và property `acme.catalog.timeout` là một phần contract cấu hình. Nếu đổi tên key, đổi đơn vị hoặc đổi ý nghĩa default, đó có thể là breaking change với ứng dụng đang dùng thư viện.

Ví dụ YAML:

```yaml
acme:
  catalog:
    timeout: 5s
```

### 6.5. CatalogAutoConfiguration.java — public candidate, internal implementation

```java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class DefaultClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogProperties properties) {
            return new DefaultCatalogClient(properties.getTimeout());
        }
    }

    /**
     * Internal default implementation. Not a supported consumer API.
     */
    static final class DefaultCatalogClient implements CatalogClient {

        private final Duration timeout;

        DefaultCatalogClient(Duration timeout) {
            this.timeout = timeout;
        }

        @Override
        public String findById(String id) {
            if (timeout.isNegative() || timeout.isZero()) {
                throw new IllegalStateException(
                        "Catalog timeout must be positive.");
            }
            return "catalog-item:" + id;
        }
    }
}
```

Các điểm quan trọng:

1. `CatalogAutoConfiguration` là top-level `public` để Spring Boot phát hiện nó từ imports. Nếu thư viện tài liệu hóa việc loại trừ auto-configuration, tên class này phải được quản lý như contract.
2. `DefaultClientConfiguration` là nested configuration nội bộ, không được ứng dụng import trực tiếp.
3. `catalogClient(...)` là bean factory method nội bộ. Consumer nên inject theo type `CatalogClient`, không phụ thuộc tên method hoặc tên bean được suy ra từ method.
4. `DefaultCatalogClient` là implementation mặc định. Ứng dụng không cần khởi tạo hoặc cast sang class này.
5. `@ConditionalOnMissingBean(CatalogClient.class)` là customization hook mà thư viện chủ động hỗ trợ: khi ứng dụng cung cấp client riêng, bean mặc định sẽ back off.

### 6.6. AutoConfiguration.imports

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Đây là class name được công bố để Spring Boot phát hiện auto-configuration. Không liệt kê nested configuration hoặc implementation class.

### 6.7. Consumer code chỉ dùng API công khai

Một service trong ứng dụng:

```java
package com.acme.orders;

import com.acme.catalog.CatalogClient;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final CatalogClient catalogClient;

    public ProductLookupService(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    public String lookup(String id) {
        return catalogClient.findById(id);
    }
}
```

Service không phụ thuộc `CatalogAutoConfiguration`, nested configuration hoặc `DefaultCatalogClient`. Nếu thư viện thay implementation mặc định trong một bản phát hành sau, service vẫn dùng cùng interface.

### 6.8. Ứng dụng thay implementation theo extension point đã công bố

Nếu ứng dụng muốn dùng một nguồn catalog riêng:

```java
package com.acme.orders;

import com.acme.catalog.CatalogClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient customCatalogClient() {
        return id -> "custom-item:" + id;
    }
}
```

Vì thư viện có `@ConditionalOnMissingBean(CatalogClient.class)`, auto-configuration không tạo implementation mặc định khi bean do ứng dụng cung cấp đã có mặt.

Đây là extension point có chủ đích và được thể hiện bằng type `CatalogClient`. Nếu thư viện không tài liệu hóa hành vi back-off này, người dùng không nên tự giả định mọi bean mặc định đều có thể thay thế.

### 6.9. Kiểm thử contract bằng ApplicationContextRunner

```java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void exposesTheDocumentedClientAndPropertyContract() {
        runner.withPropertyValues("acme.catalog.timeout=5s")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    CatalogClient client =
                            context.getBean(CatalogClient.class);

                    assertThat(client.findById("42"))
                            .isEqualTo("catalog-item:42");

                    assertThat(context.getBean(CatalogProperties.class)
                            .getTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                });
    }

    @Test
    void backsOffWhenTheApplicationProvidesItsOwnClient() {
        runner.withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    assertThat(context.getBean(CatalogClient.class)
                            .findById("42"))
                            .isEqualTo("custom-item:42");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return id -> "custom-item:" + id;
        }
    }
}
```

Test chỉ xác minh contract nhìn thấy từ consumer:

- Có bean theo type `CatalogClient`.
- Method `findById` trả về kết quả theo hợp đồng.
- Property `acme.catalog.timeout` được bind thành `Duration`.
- User bean thay thế implementation mặc định.

Test không kiểm tra class implementation cụ thể, tên nested configuration hoặc tên bean factory method. Điều này giúp test phát hiện breaking change thực sự đối với consumer mà không khóa test vào chi tiết nội bộ.

Chạy:

```bash
mvn test
```

Với hai test trong ví dụ, kết quả mong đợi là:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là kết quả kỳ vọng; cần chạy Maven trong dự án để xác nhận thực tế.

## 7. Những cách phụ thuộc nội bộ dễ gây lỗi

### 7.1. Cast sang implementation mặc định

Cách dễ tạo coupling:

```java
DefaultCatalogClient client =
        (DefaultCatalogClient) context.getBean(CatalogClient.class);
```

Ứng dụng buộc phải biết implementation mặc định. Nếu thư viện chuyển sang implementation khác, code có thể lỗi `ClassCastException` hoặc không biên dịch nếu class bị ẩn/đổi tên.

Dùng:

```java
CatalogClient client = context.getBean(CatalogClient.class);
```

### 7.2. Lấy bean bằng tên không được cam kết

Không nên phụ thuộc:

```java
CatalogClient client =
        context.getBean("catalogClient", CatalogClient.class);
```

Tên `catalogClient` có thể được suy ra từ tên `@Bean` method. Nếu thư viện đổi tên method, tên bean cũng có thể đổi.

Dùng type lookup hoặc constructor injection. Chỉ dùng bean name khi tài liệu của thư viện công bố rõ đó là tên ổn định.

### 7.3. Import nested configuration

Không làm:

```java
import com.acme.catalog.autoconfigure.CatalogAutoConfiguration
        .DefaultClientConfiguration;
```

Nested configuration là chi tiết tổ chức nội bộ. Framework có thể tách class, đổi điều kiện hoặc gom nhiều nested class mà không thay đổi contract `CatalogClient`.

### 7.4. Subclass một helper chỉ vì nó có modifier protected/public

Một method `protected` có thể chỉ phục vụ subclass nội bộ. Trước khi override, cần tìm Javadoc nói rõ method là hook được hỗ trợ, quy tắc gọi và lifecycle của nó.

Nếu không có contract, override method nội bộ có thể khiến subclass không còn hoạt động khi framework đổi thuật toán.

### 7.5. Reflection vào field hoặc method nội bộ

Reflection không biến implementation detail thành API ổn định:

```java
Field field = DefaultCatalogClient.class
        .getDeclaredField("timeout");
field.setAccessible(true);
```

Tên field, kiểu dữ liệu và quyền truy cập có thể đổi. Java module system còn có thể giới hạn reflective access. Dùng constructor, setter, property hoặc callback được công bố thay cho reflection vào implementation.

## 8. Những dạng compatibility cần kiểm tra

Một thay đổi có thể tương thích ở một khía cạnh nhưng phá vỡ khía cạnh khác.

| Loại tương thích | Câu hỏi |
|---|---|
| Source compatibility | Source cũ có biên dịch với dependency mới không? |
| Binary compatibility | Bytecode đã biên dịch có liên kết được với class/method mới không? |
| Behavioral compatibility | Kết quả, thứ tự callback, default và side effect có còn đúng không? |
| Configuration compatibility | Property key, kiểu dữ liệu, giá trị mặc định và ý nghĩa cấu hình có còn tương thích không? |
| SPI compatibility | Interface, callback, constructor và lifecycle của implementation do user cung cấp có còn đúng không? |
| Resource compatibility | Tên file, factory key, imports và metadata mà ứng dụng cần có còn được hỗ trợ không? |

Ví dụ lỗi thường gặp:

- Xóa một method public đang được consumer gọi: source và binary compatibility có thể bị phá.
- Giữ method nhưng đổi ý nghĩa default timeout: behavioral/configuration compatibility có thể bị phá.
- Đổi tên property `acme.catalog.timeout`: configuration compatibility bị phá nếu không có alias hoặc migration.
- Đổi interface callback mà plugin triển khai: SPI compatibility bị phá.
- Đổi nested configuration nội bộ nhưng giữ `CatalogClient`: có thể không ảnh hưởng consumer đang dùng đúng contract.

## 9. Deprecation và nâng cấp phiên bản

API công khai có thể được thay đổi theo một lộ trình có thông báo. Khi thấy thành phần bị deprecated:

1. Đọc lý do trong Javadoc.
2. Tìm replacement được đề xuất.
3. Xem `since` để biết từ phiên bản nào thành phần bị deprecated.
4. Xem `forRemoval` hoặc ghi chú removal target nếu có.
5. Đọc release notes và migration guide của phiên bản bạn định nâng cấp.
6. Chuyển code sang API thay thế và chạy lại contract tests.

Ví dụ minh họa:

```java
@Deprecated(since = "3.3", forRemoval = true)
public void oldConfigure(String value) {
    // Legacy method
}
```

`@Deprecated` là tín hiệu để người dùng chuyển dần. `forRemoval = true` thể hiện ý định loại bỏ trong tương lai; không nên bỏ qua cảnh báo chỉ vì code vẫn biên dịch ở phiên bản hiện tại.

Một số lưu ý:

- `@since` chỉ cho biết API được giới thiệu từ phiên bản nào.
- Không có `@Deprecated` không chứng minh API được bảo đảm vĩnh viễn.
- Một class nội bộ không cần phải có giai đoạn deprecation trước khi thay đổi.
- Không suy ra chính sách removal chỉ từ số phiên bản; hãy đọc Javadoc, release notes và migration guide cụ thể.

## 10. Quy trình nâng cấp Spring Boot an toàn

Khi nâng một ứng dụng hoặc starter từ phiên bản Boot này sang phiên bản khác:

1. Xác định chính xác phiên bản Boot và Spring Framework đang dùng.
2. Đọc release notes của từng feature release đã bỏ qua, không chỉ bản đích.
3. Kiểm tra deprecated API list và các replacement.
4. Tìm các import từ package `internal`, `impl` hoặc các nested auto-configuration class.
5. Tìm các cast sang implementation mặc định và lookup bean bằng tên không được tài liệu cam kết.
6. Thay các dependency nội bộ bằng interface, property hoặc extension point đã công bố.
7. Chạy compile/test trên phiên bản thấp nhất và cao nhất mà dự án cam kết hỗ trợ.
8. Chạy consumer integration test với artifact đã đóng gói, không chỉ test module nội bộ.
9. Kiểm tra property binding, bean back-off, classpath conditions và resource registration.
10. Đọc Condition Evaluation Report nếu auto-configuration không còn được áp dụng như trước.

### 10.1. Công cụ hỗ trợ

- `mvn dependency:tree`: xác định phiên bản Spring Boot/Spring Framework thực tế được resolve.
- Javadoc/deprecated-list: xác định API, replacement và trạng thái deprecation.
- Revapi hoặc japicmp: so sánh bề mặt binary API giữa hai artifact.
- Contract/integration tests: xác minh hành vi nhìn từ ứng dụng tiêu thụ.
- `--debug`: xem Condition Evaluation Report khi cần chẩn đoán auto-configuration.

Các công cụ so sánh API không thay thế việc đọc tài liệu. Một công cụ có thể phát hiện public method bị xóa nhưng không biết method đó vốn được tài liệu đánh dấu internal use only.

## 11. Checklist thiết kế API cho starter của riêng bạn

Trước khi phát hành thư viện auto-configuration:

1. Chọn một hoặc vài interface public làm contract cho code nghiệp vụ.
2. Chỉ công bố properties mà người dùng thực sự cần cấu hình.
3. Ghi rõ kiểu, default, đơn vị, validation và ý nghĩa từng property.
4. Định nghĩa extension point bằng interface/callback có tài liệu và test.
5. Dùng `@ConditionalOnMissingBean` khi muốn cho phép user thay implementation mặc định.
6. Giữ default implementation, helper và nested configuration ở phạm vi nội bộ.
7. Không yêu cầu consumer import nested configuration hoặc gọi bean factory method.
8. Chỉ cam kết bean name nếu có lý do và tài liệu rõ ràng; ưu tiên contract theo type.
9. Công bố class name của auto-configuration nếu người dùng cần exclude nó.
10. Ghi chính sách tương thích và cách xử lý deprecation.
11. Viết test từ góc nhìn consumer, tránh assert implementation class.
12. Kiểm thử artifact/JAR và dependency graph trên các phiên bản được hỗ trợ.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Class `public` chắc chắn là public API | Modifier chỉ điều khiển quyền truy cập; intended use và compatibility contract phải xem trong tài liệu |
| Có Javadoc nghĩa là được hỗ trợ | Javadoc có thể mô tả class nội bộ; đọc ghi chú intended use |
| Class nằm trong package `autoconfigure` chắc chắn nội bộ | Package có thể chứa cả annotation/API công khai và implementation |
| Class có `@since` là ổn định | `@since` chỉ cho biết phiên bản giới thiệu |
| Không deprecated nghĩa là sẽ không bị đổi | API vẫn chịu chính sách phiên bản và có thể được thay đổi trong tương lai |
| Nested configuration của auto-config là điểm mở rộng | Spring Boot mô tả nested configuration và bean methods của auto-config là internal |
| Bean name suy ra từ method luôn ổn định | Tên đó có thể đổi khi method đổi nếu không được cam kết |
| Test pass khi implementation hiện tại tồn tại là đủ | Consumer cần test contract, property và behavior nhìn từ bên ngoài |
| Reflection có thể thay thế API chính thức | Reflection vẫn phụ thuộc cấu trúc implementation và có thể bị module access chặn |
| API công khai không bao giờ được loại bỏ | API có thể deprecated và được loại bỏ theo lộ trình của phiên bản |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Java modifier `public` có đồng nghĩa thành phần là API ổn định không?

**Đáp án:** Không. Nó chỉ cho phép code bên ngoài truy cập. Cần kiểm tra tài liệu, intended use và compatibility contract.

**Câu 2.** Theo Spring Boot Reference, phần nào của auto-configuration class được xem là public API?

**Đáp án:** Tên class dùng để loại trừ auto-configuration. Nested configuration class và bean method là internal implementation detail.

**Câu 3.** Vì sao không nên cast `CatalogClient` sang `DefaultCatalogClient`?

**Đáp án:** Vì ứng dụng phụ thuộc implementation cụ thể; thư viện có thể thay implementation mà vẫn giữ nguyên interface `CatalogClient`.

**Câu 4.** `@since` có bảo đảm API không bị thay đổi không?

**Đáp án:** Không. Nó chỉ cho biết phiên bản API được giới thiệu.

**Câu 5.** `@Deprecated(forRemoval = true)` có ý nghĩa gì?

**Đáp án:** API đã deprecated và có ý định loại bỏ trong tương lai; cần tìm replacement và lộ trình cụ thể trong tài liệu.

**Câu 6.** Nếu thư viện muốn cho ứng dụng thay client mặc định, nên công bố gì?

**Đáp án:** Một interface như `CatalogClient`, tài liệu hóa contract và dùng `@ConditionalOnMissingBean(CatalogClient.class)` cho bean mặc định.

**Câu 7.** Vì sao test không nên assert tên nested configuration hoặc class implementation?

**Đáp án:** Vì đó là chi tiết nội bộ. Test nên kiểm tra type, property và behavior mà consumer được cam kết sử dụng.

**Câu 8.** Javadoc của một class public ghi “for internal use within the framework” nên được hiểu thế nào?

**Đáp án:** Không nên coi class đó là extension point hoặc API được hỗ trợ cho ứng dụng bên ngoài chỉ vì modifier là public.

## 14. Ghi nhớ

- Java visibility và public API contract là hai khái niệm khác nhau.
- API công khai là bề mặt được thư viện chủ động tài liệu hóa và hỗ trợ trong một compatibility policy cụ thể.
- Spring Boot nêu rõ: với auto-configuration, tên class dùng để exclude là public API; nested configuration và bean methods là internal.
- Javadoc của một class public vẫn có thể giới hạn nó ở mục đích sử dụng nội bộ.
- Ưu tiên interface, properties và extension point được công bố; tránh cast implementation, import nested config, phụ thuộc bean name hoặc dùng reflection vào field nội bộ.
- Kiểm thử từ góc nhìn consumer, không khóa test vào implementation detail.
- Khi nâng cấp, đọc deprecated API list, release notes và migration guide; dùng replacement được đề xuất.
- Thiết kế API nhỏ, rõ và có contract giúp thư viện thay đổi implementation mà ứng dụng tiêu thụ ít bị ảnh hưởng.

### Tài liệu chính thức

- [Spring Boot 3.3 — Developing with Spring Boot / Auto-configuration](https://docs.spring.io/spring-boot/docs/3.3.0-M2/reference/html/using.html)
- [Spring Boot 3.3.13 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3.13 API — Deprecated API List](https://docs.spring.io/spring-boot/3.3/api/java/deprecated-list.html)
- [Spring Framework 6.1 — SpringFactoriesLoader API](https://docs.spring.io/spring-framework/docs/6.1.0-M5/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
