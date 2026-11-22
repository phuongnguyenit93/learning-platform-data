# FilteredClassLoader để mô phỏng thiếu lớp hoặc thiếu gói thư viện

## 1. Bài toán: kiểm tra auto-configuration khi thư viện tùy chọn không có

Một starter có thể tích hợp SDK của nhà cung cấp, client cloud, thư viện metrics, driver hoặc adapter đặc biệt. Ứng dụng tiêu thụ không phải lúc nào cũng đưa các dependency đó vào runtime classpath. Nếu auto-configuration vẫn cố phân giải kiểu của SDK, ứng dụng có thể lỗi lúc khởi động với `NoClassDefFoundError` hoặc `ClassNotFoundException`.

Chỉ kiểm tra trường hợp dependency có mặt chưa đủ. Thư viện cần chứng minh rằng:

- Khi SDK có mặt, nhánh auto-configuration cần SDK được áp dụng đúng.
- Khi một class cụ thể bị thiếu, nhánh đó được bỏ qua và context vẫn khởi động.
- Khi cả package của SDK bị thiếu, các bean phụ thuộc package đó cũng không xuất hiện.
- Các auto-configuration hoặc bean không liên quan vẫn hoạt động.
- Khi người dùng tắt feature bằng property, bean mặc định không được đăng ký dù SDK vẫn có mặt.

Spring Boot cung cấp `FilteredClassLoader` trong module test để mô phỏng classpath bị thiếu class hoặc package. Kết hợp nó với `ApplicationContextRunner`, bạn có thể kiểm tra từng kịch bản trong một `ApplicationContext` nhỏ, độc lập và nhanh.

Bài này dùng Java 17+, Spring Boot 3.3.13, Maven, JUnit 5 và AssertJ. Ví dụ giả lập một SDK tên `CatalogClient`; trong thư viện thực tế, kiểu này thường đến từ dependency bên ngoài.

## 2. Ôn lại ClassLoader và runtime classpath

JVM không tìm class bằng cách quét mọi JAR tùy ý ở mỗi lần dùng. Việc nạp class được thực hiện qua một chuỗi `ClassLoader`. ClassLoader nhận tên nhị phân, ví dụ `com.vendor.catalog.CatalogClient`, rồi tìm bytecode theo cơ chế của nó.

Trong một ứng dụng Java thông thường:

- Runtime classpath chứa thư mục class đã biên dịch và các JAR phụ thuộc.
- Application ClassLoader thường tìm các class của ứng dụng và thư viện.
- Spring có thể dùng ClassLoader của context để kiểm tra class, đọc resource và tạo một số thành phần.
- Nếu một class không thể được tìm thấy khi code cần nó, việc nạp hoặc liên kết class có thể thất bại.

Ví dụ, thư viện có method:

```java
@Bean
CatalogService catalogService(CatalogClient client) {
    return client::findById;
}
```

Nếu `CatalogClient` đến từ SDK không có trên runtime classpath, JVM/Spring có thể cần phân giải kiểu trong chữ ký method khi introspect configuration. Đặt `@ConditionalOnClass` trực tiếp trên method này không phải lúc nào cũng bảo vệ đủ sớm, bởi return type và tham số có thể đã cần được phân giải trước khi method condition được đánh giá.

Spring Boot khuyến nghị cô lập các method phụ thuộc class tùy chọn trong một nested `@Configuration` riêng và đặt `@ConditionalOnClass` trên chính nested configuration đó. Ví dụ hoàn chỉnh ở mục 6.

## 3. FilteredClassLoader là gì?

`org.springframework.boot.test.context.FilteredClassLoader` là một test ClassLoader do Spring Boot cung cấp. Nó hoạt động như một bộ lọc: những class hoặc resource được chỉ định sẽ bị xem như không thể tải được qua classloader này.

Điểm quan trọng: `FilteredClassLoader` thuộc **test support**, không phải cách cấu hình classpath cho ứng dụng production. Ta dùng nó để tạo một bối cảnh thử nghiệm có classpath bị giới hạn mà không phải sửa dependency của toàn dự án.

Các constructor thường dùng trong Spring Boot 3.3:

| Constructor | Tác dụng |
|---|---|
| `new FilteredClassLoader(SomeSdkClient.class)` | Ẩn một class cụ thể |
| `new FilteredClassLoader(Foo.class, Bar.class)` | Ẩn nhiều class cụ thể |
| `new FilteredClassLoader("com.vendor.sdk")` | Ẩn các class thuộc package được chỉ định |
| `new FilteredClassLoader("com.vendor.sdk", "com.vendor.auth")` | Ẩn nhiều package |

API cũng hỗ trợ predicate để lọc tên class/resource và `ClassPathResource` để ẩn resource cụ thể. Với bài toán thiếu thư viện tùy chọn, hai dạng theo class và package thường đủ rõ ràng.

### 3.1. Ẩn một class

Dùng khi muốn kiểm tra một integration phụ thuộc vào một kiểu cụ thể:

```java
new FilteredClassLoader(CatalogClient.class)
```

Ví dụ này mô phỏng `CatalogClient` không có trong classpath mà context đang sử dụng. Class vẫn tồn tại trong dependency/test runtime của chính tiến trình test; bộ lọc chỉ làm nó không thể được tìm thấy qua classloader được đưa cho runner.

### 3.2. Ẩn toàn bộ package

Dùng khi integration phụ thuộc nhiều kiểu trong cùng một SDK:

```java
new FilteredClassLoader("com.vendor.catalog")
```

Nếu configuration sử dụng `CatalogClient`, `CatalogRequest`, `CatalogResponse` và các class khác thuộc package đó, test có thể mô phỏng trường hợp cả package không được cung cấp.

Nên lọc package nhỏ nhất đủ đại diện cho dependency tùy chọn. Nếu lọc một package cha quá rộng, test có thể vô tình ẩn cả class của ứng dụng hoặc framework mà configuration vẫn cần.

### 3.3. Ẩn class khác với xóa dependency

`FilteredClassLoader` không sửa `pom.xml`, không xóa JAR khỏi Maven repository và không thay đổi dependency graph. Nó chỉ kiểm soát việc context thử nghiệm tìm class/resource thông qua classloader được cấu hình.

Vì vậy có hai loại kiểm tra khác nhau:

- `FilteredClassLoader`: xác minh condition và cách auto-configuration phản ứng khi class/package không nhìn thấy.
- Dependency analysis hoặc consumer integration test: xác minh thư viện có vô tình kéo SDK vào runtime của ứng dụng tiêu thụ hay không.

Không dùng kết quả của một loại kiểm tra để thay cho loại còn lại.

## 4. Kết hợp FilteredClassLoader với ApplicationContextRunner

`ApplicationContextRunner` là tiện ích Spring Boot để tạo và chạy các application context nhỏ trong test. Mỗi lần gọi `run(...)`, runner tạo context cho kịch bản đang kiểm tra, gọi callback với context đó rồi đóng context.

Một runner cơ bản:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(CatalogAutoConfiguration.class));
```

`AutoConfigurations.of(...)` khai báo rõ auto-configuration nào cần kiểm tra. Điều này giúp test tập trung vào một nhánh, không phải khởi động toàn bộ ứng dụng.

Để thay classpath của context:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(CatalogClient.class))
        .run(context -> {
            // Assertions
        });
```

Để mô phỏng thiếu cả package:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader("demo.catalog.sdk"))
        .run(context -> {
            // Assertions
        });
```

Các thao tác thường dùng trong test:

| API | Ý nghĩa |
|---|---|
| `withClassLoader(...)` | Chạy context bằng classloader đã lọc |
| `withPropertyValues(...)` | Thêm property cho kịch bản |
| `withUserConfiguration(...)` | Bổ sung cấu hình do ứng dụng cung cấp |
| `withConfiguration(AutoConfigurations.of(...))` | Chỉ định auto-configuration cần chạy |
| `run(context -> ...)` | Tạo context và kiểm tra kết quả |
| `hasNotFailed()` | AssertJ kiểm tra context có khởi động thành công không |
| `doesNotHaveBean(...)` | Xác nhận bean không được đăng ký |
| `hasSingleBean(...)` | Xác nhận chỉ có một bean theo type |

### Vì sao phải kiểm tra cả hasNotFailed và doesNotHaveBean?

Nếu chỉ khẳng định bean không tồn tại, test chưa nói rõ context có khởi động bình thường hay không. Context có thể thất bại trước khi bean được đăng ký.

Với tình huống thiếu optional dependency, hai assertion nên đi cùng nhau:

```java
assertThat(context).hasNotFailed();
assertThat(context).doesNotHaveBean("catalogClient");
```

Assertion thứ nhất xác nhận ứng dụng vẫn tạo được context. Assertion thứ hai xác nhận nhánh tùy chọn thực sự không đăng ký bean.

## 5. Thiết kế auto-configuration an toàn khi thiếu class

Giả sử thư viện có SDK tùy chọn `demo.catalog.sdk.CatalogClient`. Thiết kế nên tách hai phần:

- Outer auto-configuration chỉ chứa các type luôn có mặt.
- Nested static configuration chứa toàn bộ tham chiếu tới `CatalogClient`, được bảo vệ bởi `@ConditionalOnClass`.

Mô hình:

```text
CatalogAutoConfiguration
        |
        +-- không tham chiếu trực tiếp CatalogClient
        |
        +-- CatalogSdkConfiguration
                |
                +-- @ConditionalOnClass(CatalogClient)
                +-- @ConditionalOnProperty(acme.catalog.enabled=true)
                |
                +-- CatalogClient bean
```

### 5.1. Vì sao nested configuration quan trọng?

Spring Boot có thể đọc metadata annotation của configuration class bằng ASM. Với `@ConditionalOnClass` trên một configuration class, bạn có thể chỉ định class bằng `value` hoặc `name`.

Điều kiện trên `@Bean` method có điểm khác: trước khi method condition được áp dụng, JVM có thể đã cần nạp class liên quan đến return type/tham số hoặc xử lý method reference. Nếu optional class thiếu, lỗi có thể xảy ra quá sớm.

Vì vậy, hãy đặt `@ConditionalOnClass` trên một configuration class riêng và giữ các method có optional type ở bên trong class đó. Outer class không nên có constructor, field, superclass hoặc `@Bean` signature phụ thuộc optional SDK.

Dùng `name` là lựa chọn dễ đọc khi muốn thể hiện rõ tên class dưới dạng chuỗi:

```java
@ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
```

Với condition class-level, Spring Boot cũng hỗ trợ `value = CatalogClient.class` nhờ đọc annotation metadata. Nếu đóng gói condition thành meta-annotation riêng, tài liệu yêu cầu dùng `name` cho class condition.

### 5.2. Kết hợp property condition

Classpath condition và feature flag giải quyết hai câu hỏi khác nhau:

- SDK có tồn tại không?
- Người dùng có bật integration không?

Ví dụ opt-in:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

Khi property thiếu hoặc có giá trị `false`, integration không được đăng ký. Khi SDK thiếu, đặt `enabled=true` cũng không thể khiến class xuất hiện.

### 5.3. Cho phép ứng dụng thay bean mặc định

Nếu ứng dụng có thể tự cung cấp client, dùng `@ConditionalOnMissingBean` trên bean mặc định:

```java
@Bean
@ConditionalOnMissingBean
CatalogClient catalogClient() {
    return new CatalogClient();
}
```

Điều kiện này có ý nghĩa khi nhánh classpath và property đã khớp. Nó cho phép ứng dụng override implementation mặc định, không thay thế việc kiểm tra SDK có mặt hay không.

## 6. Ví dụ hoàn chỉnh với Java 17 và Spring Boot 3.3

Ví dụ dưới đây có một class SDK giả lập nằm trong source của dự án. Trong thư viện thật, class đó đến từ dependency bên ngoài. Các test dùng `FilteredClassLoader` để mô phỏng việc ứng dụng tiêu thụ không nhìn thấy class hoặc package SDK.

### 6.1. Cấu trúc thư mục

```text
filtered-classloader-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/catalog/sdk/
    │   │   └── CatalogClient.java
    │   └── java/demo/catalog/autoconfigure/
    │       └── CatalogAutoConfiguration.java
    └── test/
        └── java/demo/catalog/autoconfigure/
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

    <groupId>demo</groupId>
    <artifactId>filtered-classloader-demo</artifactId>
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

`spring-boot-autoconfigure` cung cấp annotation và cơ chế auto-configuration. `spring-boot-starter-test` đưa vào JUnit, AssertJ, `ApplicationContextRunner` và `FilteredClassLoader` cho test.

### 6.3. CatalogClient.java

```java
package demo.catalog.sdk;

public class CatalogClient {

    public String findById(String id) {
        return "catalog-item:" + id;
    }
}
```

Class này đóng vai SDK tùy chọn trong ví dụ. Nó chỉ có một method để test dễ quan sát kết quả.

### 6.4. CatalogAutoConfiguration.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.sdk.CatalogClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "demo.catalog.sdk.CatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    public static class CatalogSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean
        CatalogClient catalogClient() {
            return new CatalogClient();
        }
    }
}
```

Những điểm cần quan sát:

1. Outer `CatalogAutoConfiguration` không có method hoặc field nào trả về/giữ `CatalogClient`.
2. Nested `CatalogSdkConfiguration` là nơi duy nhất tham chiếu tới SDK.
3. `@ConditionalOnClass(name=...)` bảo vệ nhánh nếu class SDK không nhìn thấy.
4. `@ConditionalOnProperty` yêu cầu người dùng bật feature bằng `acme.catalog.enabled=true`.
5. `@ConditionalOnMissingBean` cho phép application cung cấp client riêng.

Nếu thư viện được đóng gói thành JAR để Spring Boot tự phát hiện, thêm resource sau:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
demo.catalog.autoconfigure.CatalogAutoConfiguration
```

Các test tiếp theo dùng `AutoConfigurations.of(CatalogAutoConfiguration.class)` để gọi trực tiếp auto-configuration, vì vậy runner không cần đọc file imports. Trong consumer integration test, nên kiểm tra thêm resource imports trong JAR đã đóng gói.

### 6.5. CatalogAutoConfigurationTests.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.sdk.CatalogClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void clientIsCreatedWhenSdkIsAvailable() {
        contextRunner
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);
                    assertThat(context.getBean(CatalogClient.class)
                            .findById("42"))
                            .isEqualTo("catalog-item:42");
                });
    }

    @Test
    void missingClassDisablesTheOptionalConfiguration() {
        contextRunner
                .withClassLoader(
                        new FilteredClassLoader(CatalogClient.class))
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                });
    }

    @Test
    void missingPackageDisablesTheOptionalConfiguration() {
        contextRunner
                .withClassLoader(
                        new FilteredClassLoader("demo.catalog.sdk"))
                .withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                });
    }

    @Test
    void disabledPropertyPreventsClientCreation() {
        contextRunner
                .withPropertyValues("acme.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("catalogClient");
                });
    }

    @Test
    void missingPropertyKeepsOptInFeatureDisabled() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("catalogClient");
        });
    }
}
```

### 6.6. Chạy test

Từ thư mục có `pom.xml`, chạy bằng JDK 17+ và Maven:

```bash
mvn test
```

Với đúng năm test ở trên, kết quả kỳ vọng là:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là kết quả kỳ vọng của ví dụ, không phải log của một lần chạy đã thực thi. Maven Surefire có thể trình bày thêm tên test, thời gian và thông tin plugin.

### 6.7. Đọc từng kịch bản

| Test | Classpath | Property | Kết quả |
|---|---|---|---|
| `clientIsCreatedWhenSdkIsAvailable` | SDK có | `true` | Có một `CatalogClient` |
| `missingClassDisablesTheOptionalConfiguration` | Ẩn `CatalogClient.class` | `true` | Context thành công, không có bean |
| `missingPackageDisablesTheOptionalConfiguration` | Ẩn package `demo.catalog.sdk` | `true` | Context thành công, không có bean |
| `disabledPropertyPreventsClientCreation` | SDK có | `false` | Context thành công, không có bean |
| `missingPropertyKeepsOptInFeatureDisabled` | SDK có | Thiếu | Context thành công, không có bean |

Hai test `missingClass...` và `missingPackage...` quan trọng vì chúng chứng minh classpath condition được kiểm tra. Nếu chỉ đặt property false, test mới chứng minh feature flag hoạt động; nó chưa chứng minh thư viện chịu được SDK vắng mặt.

## 7. Các mẫu lọc nâng cao

### 7.1. Ẩn nhiều class

Nếu auto-configuration phụ thuộc nhiều type tùy chọn nhưng các type nằm ở package khác nhau:

```java
new FilteredClassLoader(
        CatalogClient.class,
        CatalogRequest.class,
        CatalogResponse.class)
```

Cách này phù hợp khi muốn chỉ ra chính xác các class gây ra một nhánh integration.

### 7.2. Ẩn nhiều package

```java
new FilteredClassLoader(
        "com.vendor.catalog",
        "com.vendor.identity")
```

Dùng khi một integration cần cả SDK catalog và SDK xác thực. Test có thể kiểm tra nhánh chỉ được bật khi tất cả class cần thiết đều tồn tại.

### 7.3. Lọc theo predicate

API có constructor nhận predicate. Predicate trả về `true` cho tên class hoặc resource cần ẩn:

```java
new FilteredClassLoader(
        name -> name.startsWith("com.vendor.catalog."))
```

Đây là cách linh hoạt hơn, nhưng predicate rộng có thể vô tình lọc resource hoặc class không thuộc dependency dự định. Với test thông thường, constructor theo class/package dễ đọc và ít bất ngờ hơn.

### 7.4. Ẩn resource classpath

`FilteredClassLoader` cũng hỗ trợ ẩn `ClassPathResource`. Điều này hữu ích khi kiểm tra resource tùy chọn, ví dụ file cấu hình hoặc descriptor được thư viện tìm bằng `ClassLoader.getResource(...)`.

Không dùng resource filtering để thay cho class filtering. Một JAR có thể chứa resource nhưng thiếu class, hoặc có class nhưng thiếu resource; hai trường hợp cần test riêng nếu logic của thư viện phụ thuộc cả hai.

## 8. Mô phỏng thiếu dependency thật trong thư viện nhiều module

Ví dụ ở mục 6 đặt `CatalogClient` trong source để dự án tự chạy độc lập. Khi xây dựng thư viện thực tế, SDK thường là dependency riêng.

Một cấu hình Maven điển hình cho dependency không truyền tự động tới consumer:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>catalog-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Dependency optional vẫn có mặt khi compile/test module thư viện, nhưng Maven không tự truyền nó như dependency transitive tới ứng dụng tiêu thụ. Ứng dụng nào cần integration sẽ tự thêm SDK.

Trong dự án thực tế, có thể tổ chức:

```text
catalog-autoconfigure/
├── src/main/java/...
├── src/test/java/...
└── pom.xml

catalog-starter/
└── pom.xml
```

Module `catalog-autoconfigure` chứa code và condition. Module `catalog-starter` quyết định SDK nào được đưa vào dependency graph mặc định. Nếu starter cần SDK để tính năng hoạt động, starter khai báo dependency đó; nếu muốn SDK tùy chọn, để consumer chọn dependency hoặc cung cấp starter flavor riêng.

Dù cấu trúc module nào, test classpath vẫn nên có SDK trong test runtime để `FilteredClassLoader` có thể ẩn class/package đó cho từng kịch bản.

### Kiểm tra dependency graph của consumer

Dùng:

```bash
mvn dependency:tree
```

Đọc dependency tree của ứng dụng tiêu thụ, không chỉ module auto-config. Xác nhận SDK tùy chọn không xuất hiện ngoài ý muốn trong runtime graph. Với Gradle, dùng `./gradlew dependencies` và xem configuration runtime tương ứng, chẳng hạn `runtimeClasspath`.

## 9. Phân biệt các loại test classpath

| Kiểm thử | Cách làm | Câu hỏi được trả lời |
|---|---|---|
| SDK có mặt | Chạy runner không lọc | Nhánh integration có hoạt động khi đủ dependency không? |
| Thiếu một class | `FilteredClassLoader(SomeClass.class)` | Auto-config có bỏ qua nhánh phụ thuộc class đó không? |
| Thiếu một package | `FilteredClassLoader("com.vendor.sdk")` | Auto-config có chịu được toàn bộ package SDK vắng mặt không? |
| Thiếu nhiều dependency | Lọc nhiều class/package | Nhánh có xử lý đúng khi thiếu một trong các điều kiện classpath không? |
| Dependency propagation | Maven/Gradle dependency tree | Consumer có bị kéo SDK vào runtime ngoài ý muốn không? |
| Đóng gói và discovery | Build JAR rồi chạy consumer test | Imports, resources và dependency graph trong artifact thật có đúng không? |

Một test bằng `FilteredClassLoader` không chứng minh JAR đã publish có dependency metadata đúng. Ngược lại, dependency tree không chứng minh auto-configuration xử lý đúng trường hợp thiếu class. Một thư viện chất lượng cần cả kiểm tra logic condition và kiểm tra artifact/consumer.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test thiếu SDK nhưng context lỗi `NoClassDefFoundError` | Optional type bị tham chiếu trong outer auto-configuration hoặc method signature chưa được cô lập | Chuyển method phụ thuộc SDK vào nested `@Configuration` có `@ConditionalOnClass` |
| Test chỉ xác nhận bean không tồn tại | Context có thể đã fail trước đó | Kiểm tra cả `hasNotFailed()` và `doesNotHaveBean(...)` |
| Dùng class filter nhưng một type khác trong SDK vẫn được nạp | Nhánh integration còn phụ thuộc class khác | Ẩn cả package hoặc bổ sung các class cần thiết vào test |
| Lọc package cha quá rộng khiến nhiều bean không liên quan biến mất | Bộ lọc bao phủ cả class của ứng dụng/framework | Dùng package hẹp hơn hoặc ẩn đúng class |
| SDK có mặt nhưng bean không được tạo | Feature property thiếu/false hoặc condition khác không khớp | Kiểm tra property và Condition Evaluation Report |
| Property true nhưng bean vẫn không có | SDK thực sự bị lọc hoặc classpath condition không khớp | Kiểm tra tên class/package trong `@ConditionalOnClass` |
| Test pass nhưng ứng dụng consumer vẫn thiếu SDK | Test runtime có dependency mà consumer không có, hoặc dependency scope công bố sai | Kiểm tra dependency tree của consumer và chạy packaged integration test |
| Tưởng FilteredClassLoader đã xóa JAR khỏi dự án | Nhầm test classloader với dependency management | Dùng Maven/Gradle để kiểm tra dependency graph |
| Optional SDK bị nạp sớm khi introspect method | `@ConditionalOnClass` chỉ đặt trên `@Bean` method có signature chứa optional type | Đặt condition trên nested configuration class |
| Test context dùng chung state | Test thay đổi static state hoặc tái sử dụng context ngoài ý muốn | Tạo runner context mới cho từng kịch bản, tránh mutable static state |

### Lưu ý về giới hạn classloader

`FilteredClassLoader` mô phỏng khả năng nhìn thấy class/resource của context thử nghiệm. Nó rất phù hợp để xác minh điều kiện classpath và cách Spring Boot chọn bean. Tuy nhiên, nếu cần điều tra lỗi classloading rất đặc thù liên quan đến class đã được một parent/defining classloader nạp trước, cần kiểm tra thêm bằng một consumer process hoặc classloader isolation thực tế. Không nên coi một test lọc class là bằng chứng tuyệt đối cho mọi tình huống linkage của JVM.

## 11. Quy trình kiểm thử auto-configuration trước khi phát hành

1. Xác định các dependency tùy chọn và những class đại diện cho mỗi integration.
2. Cô lập mọi tham chiếu tới optional type trong nested configuration được bảo vệ bằng `@ConditionalOnClass`.
3. Dùng `ApplicationContextRunner` để gọi auto-configuration cần kiểm tra.
4. Viết test với classpath đầy đủ và xác nhận bean mặc định xuất hiện.
5. Dùng `FilteredClassLoader(SomeClass.class)` để kiểm tra thiếu class.
6. Dùng `FilteredClassLoader("com.vendor.sdk")` để kiểm tra thiếu package.
7. Kiểm tra context không fail và bean tùy chọn không được đăng ký.
8. Kiểm tra property off/missing và bean override nếu thư viện hỗ trợ các hợp đồng đó.
9. Kiểm tra dependency graph của ứng dụng tiêu thụ.
10. Build JAR, kiểm tra `AutoConfiguration.imports` và chạy consumer integration test để xác nhận artifact thật.

Khi test fail, thêm `ConditionEvaluationReportLoggingListener` vào runner ở mức INFO/DEBUG để quan sát condition:

```java
.withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
                LogLevel.INFO))
```

Sau đó tìm `OnClassCondition` của nested configuration. Nếu condition không khớp nhưng context vẫn fail, tìm một class khác đang tham chiếu optional type bên ngoài nhánh được bảo vệ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Muốn mô phỏng thiếu đúng một class `CatalogClient`, dùng constructor nào?

**Đáp án:** `new FilteredClassLoader(CatalogClient.class)`.

**Câu 2.** Muốn mô phỏng cả package SDK không có, dùng cách nào?

**Đáp án:** `new FilteredClassLoader("com.vendor.sdk")`, với package name cần lọc.

**Câu 3.** `FilteredClassLoader` có xóa dependency khỏi Maven runtime graph không?

**Đáp án:** Không. Nó lọc việc tải class/resource qua classloader của context test. Dùng `mvn dependency:tree` để kiểm tra dependency graph.

**Câu 4.** Vì sao cần kết hợp `FilteredClassLoader` với `ApplicationContextRunner`?

**Đáp án:** Runner tạo context độc lập và cho phép gắn classloader riêng vào đúng kịch bản, sau đó kiểm tra condition và bean bằng AssertJ.

**Câu 5.** Khi SDK thiếu, vì sao `@ConditionalOnClass` nên đặt trên nested configuration?

**Đáp án:** Để Spring đánh giá classpath condition trên configuration class trước khi xử lý các method signature hoặc tham chiếu kiểu phụ thuộc SDK. Đặt condition trên một `@Bean` method có optional return/parameter type có thể quá muộn.

**Câu 6.** Nếu test chỉ gọi `doesNotHaveBean("catalogClient")`, đã chứng minh context chạy thành công chưa?

**Đáp án:** Chưa. Cần kiểm tra `hasNotFailed()` để xác nhận context khởi động bình thường.

**Câu 7.** Test với `FilteredClassLoader` pass có chứng minh ứng dụng tiêu thụ không bị kéo SDK vào runtime không?

**Đáp án:** Không. Cần kiểm tra dependency tree hoặc runtime classpath của consumer riêng.

## 13. Ghi nhớ

- `FilteredClassLoader` là tiện ích test của Spring Boot để ẩn class, package hoặc resource khỏi context.
- Dùng `new FilteredClassLoader(SomeClass.class)` để ẩn class cụ thể.
- Dùng `new FilteredClassLoader("com.vendor.sdk")` để ẩn package.
- Kết hợp `ApplicationContextRunner.withClassLoader(...)` để kiểm thử từng tình huống trong context độc lập.
- Khi SDK tùy chọn vắng mặt, đặt `@ConditionalOnClass` trên nested configuration và giữ optional type bên trong nhánh đó.
- Luôn kiểm tra cả context không fail và bean tùy chọn không xuất hiện.
- `FilteredClassLoader` không thay thế việc kiểm tra Maven/Gradle dependency graph hoặc consumer JAR thực tế.

### Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing and Overriding the Classpath](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3.13 API — FilteredClassLoader](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
