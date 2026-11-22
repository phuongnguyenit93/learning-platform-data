# FilteredClassLoader để kiểm thử khi dependency không có trên classpath

Một thư viện Spring Boot **auto-configuration** thường tích hợp với dependency tùy chọn: có Jackson thì tạo JSON codec; có JDBC driver thì cấu hình DataSource; có SDK của nhà cung cấp thì đăng ký client; không có SDK thì **không** nên khởi động bean của SDK hoặc phải tạo fallback hợp lệ. Một lỗi rất dễ bỏ sót là dự án của chính tác giả starter luôn có đầy đủ dependency trên **test classpath**. Test “context starts” vì thế xanh, nhưng ứng dụng của người dùng chỉ cài phần auto-config mà không cài SDK lại nhận `ClassNotFoundException`, `NoClassDefFoundError`, lỗi reflect trên chữ ký `@Bean`, hoặc một bean lẽ ra phải vắng mặt vẫn được đăng ký.

**FilteredClassLoader** là tiện ích test của Spring Boot giải quyết một phần quan trọng của bài toán: nó cho phép một `ApplicationContextRunner` chạy với **ClassLoader giả lập không nhìn thấy class/package/resource nhất định**, trong khi Gradle/Maven project vẫn biên dịch với dependency. Ta có thể kiểm nhanh cả hai nhánh `@ConditionalOnClass` và `@ConditionalOnMissingClass` mà không sửa dependency graph cho từng method.

Bài này thuộc nhóm **Kiểm thử auto-configuration** của module **Spring Boot – testing**. Nội dung đi từ khái niệm classpath/conditional evaluation, API `FilteredClassLoader`, thiết kế an toàn với optional dependency, đến một project Java 17+ và bộ JUnit 5 tests chạy được trên **Spring Boot 3.5.16**, rồi giải thích **giới hạn của mô phỏng**: `FilteredClassLoader` không phải một JVM thật sự đã gỡ JAR; có lỗi JVM linkage/reflection/packaging chỉ được phát hiện bằng integration test với runtime classpath thực sự thiếu module.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

- Giải thích `@ConditionalOnClass`, `@ConditionalOnMissingClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean` và ranh giới của từng điều kiện.
- Hiểu `FilteredClassLoader` đến từ `spring-boot-test`, **không phải** API cần dùng trong production.
- Ẩn **một class**, **một package**, **một resource** hoặc tùy chỉnh qua predicate.
- Viết `ApplicationContextRunner.withClassLoader(new FilteredClassLoader(...))`.
- Kiểm dependency **có mặt** → optional bean được đăng ký; dependency **vắng mặt** → bean biến mất và fallback hoạt động.
- Kiểm startup **không bị fail** khi class không tồn tại, không chỉ kiểm bean count.
- Phân biệt một class bị ẩn khỏi **context ClassLoader** với một dependency đã bị loại khỏi toàn bộ JVM/runtime.
- Đặt optional type vào **nested @Configuration có @ConditionalOnClass**, tránh signature được reflect quá sớm.
- Biết khi nào dùng `name` thay `value` trong composed condition annotations.
- Test `@ConditionalOnMissingBean` back off khi user đã định nghĩa bean của mình.
- Nhận biết vì sao `@MockBean`/`@MockitoBean` hoặc `excludeAutoConfiguration` không thay thế mô phỏng dependency vắng mặt.
- Xem `ConditionEvaluationReport` để biết điều kiện nào match/mismatch.
- Phân biệt `ApplicationContextRunner` cho context thường với `WebApplicationContextRunner`/`ReactiveWebApplicationContextRunner`.
- Thiết kế thêm **runtime packaging test** không có optional JAR khi cần bắt `NoClassDefFoundError` thực.
- Hiểu giới hạn của test này khi sử dụng native image/AOT hoặc hệ module/OSGi.

## 2. Vấn đề: dependency có trong test nhưng không có ở ứng dụng người dùng

Giả sử có auto-config:

```java
// Mã minh họa, không phải file runnable độc lập.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.VendorClient")
class VendorAutoConfiguration {
    // Khi SDK có mặt, tạo bean VendorClient.
}
```

Trên máy tác giả, `vendor-sdk.jar` luôn xuất hiện vì được khai báo trên `testImplementation`, hoặc vì starter kéo nó vào. Test:

```java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(VendorAutoConfiguration.class))
    .run(context -> assertThat(context).hasNotFailed());
```

chỉ xác nhận nhánh SDK **có mặt**. Nó không bảo đảm ứng dụng chỉ dùng `my-autoconfigure.jar` mà không cài SDK cũng khởi động được. Để bảo vệ nhánh còn lại, cần một môi trường nơi Spring **quan sát** như thể class `VendorClient` đã biến mất.

`FilteredClassLoader` cho một câu trả lời nhanh ở mức test context:

```java
// Snippet đặt trong test method, với runner đã đăng ký auto-config.
runner.withClassLoader(
        new FilteredClassLoader(VendorClient.class))
    .run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).doesNotHaveBean("vendorClient");
    });
```

Đây là **simulation ở phạm vi classloader dùng bởi runner**. Không ai sửa `build.gradle`, xóa JAR trên đĩa, thay classpath của cả JVM hay thay đổi ứng dụng production.

## 3. “Classpath thiếu dependency” gồm nhiều vấn đề khác nhau

| Tình huống | Điều bị thiếu | Bài test thích hợp |
|---|---|---|
| `@ConditionalOnClass` cần đánh giá false | Tên class không nhìn thấy với classloader của context | `FilteredClassLoader` + `ApplicationContextRunner` |
| `@ConditionalOnMissingClass` cần đánh giá true | Tên class không nhìn thấy với context | `FilteredClassLoader` + assert fallback |
| SDK hiện diện nhưng bean chưa được cấu hình | Bean definition/instance | `@ConditionalOnMissingBean` tests |
| SDK có mặt nhưng property tắt | Environment property | `withPropertyValues` |
| Một service metadata/resource thiếu | Resource trên classpath | Filter resource + condition tương ứng |
| JAR thực sự không được đóng gói trong ứng dụng | Runtime dependency graph/JVM linkage | Forked JVM hoặc project consumer không có JAR |
| SDK version không tương thích | API binary signature/method | Compatibility/integration tests với versions thực |
| Native image thiếu reflection hints | AOT image build/runtime | Native integration tests, không chỉ runner |
| Client được tạo nhưng downstream server không chạy | Network/service | Mock server/Testcontainers/integration test khác |

**Không đánh đồng class condition với bean condition.** Một JAR có mặt nhưng chưa có bean vẫn khiến `@ConditionalOnClass` match. Ngược lại, mock bean do test tạo có thể khiến `@ConditionalOnBean` match dù ứng dụng production không có bean ấy.

## 4. `FilteredClassLoader` là gì?

Spring Boot 3.5 cung cấp class:

```java
import org.springframework.boot.test.context.FilteredClassLoader;
```

Javadoc mô tả nó là test `URLClassLoader` có thể lọc classes và resources được load; implements `SmartClassLoader` và `Closeable`. Constructor phổ biến:

| Constructor | Dùng khi |
|---|---|
| `new FilteredClassLoader(SomeClass.class)` | Ẩn một hoặc nhiều class cụ thể |
| `new FilteredClassLoader("com.vendor.sdk")` | Ẩn toàn bộ classes thuộc package tương ứng |
| `new FilteredClassLoader(parent, SomeClass.class)` | Cần chỉ rõ parent loader khi mô phỏng |
| `new FilteredClassLoader(new ClassPathResource("..."))` | Muốn ẩn một classpath resource |
| `new FilteredClassLoader((Predicate<String>) name -> ...)` | Quy tắc lọc custom theo tên class/resource |

**Lưu ý API:** Constructor `String...` của Boot 3.5 nhận **tên package**, không phải một FQCN tùy ý dùng như chuỗi class name. Nếu chỉ cần ẩn chính xác một class, chọn `SomeClass.class`. Nếu không thể tham chiếu compile-time tới class, dùng predicate có kiểm soát đối với binary class name.

### 4.1. Ẩn class cụ thể

```java
new FilteredClassLoader(ThirdPartyClient.class)
```

Trong context classloader, cố load `com.example.optional.ThirdPartyClient` sẽ bị từ chối. Các class còn lại trong package có thể vẫn nhìn thấy, tùy những gì bạn lọc.

### 4.2. Ẩn package

```java
new FilteredClassLoader("com.example.optional")
```

Dùng khi dependency có nhiều entrypoints: client, factory, configuration, serializers hoặc annotations. Có thể mô phỏng tốt hơn “một JAR biến mất” so với chỉ ẩn một interface. **Đừng lọc package quá rộng như `org.springframework` hay `java`**, vì Spring context sẽ thiếu cả hạ tầng của chính bài test.

### 4.3. Ẩn resource

```java
// Snippet: lọc resource, không phải Java class.
new FilteredClassLoader(
        new ClassPathResource("features/optional-adapter.flag"))
```

Constructor nhận `ClassPathResource...`. Kịch bản này hữu ích khi thử `@ConditionalOnResource` hoặc lookup metadata của một integration. Nhưng việc ẩn một resource **không tương đương** ẩn class mà resource ấy mô tả; muốn mô phỏng service/provider discovery thật, cần hiểu code lookup đang dùng ClassLoader nào và resource path nào.

### 4.4. Predicate custom

```java
// Snippet với java.util.function.Predicate:
Predicate<String> hidden = name ->
        name.equals("com.example.optional.ThirdPartyClient")
        || name.startsWith("com.example.optional.internal.");

FilteredClassLoader loader =
        new FilteredClassLoader(hidden);
```

Javadoc cho biết predicate có thể nhận binary class name **hoặc resource name**; true nghĩa là **ẩn**. Khi dùng custom predicate, hãy cố định rule rõ và test không che class phụ thuộc thiết yếu ngoài ý muốn.

## 5. Spring Boot `ApplicationContextRunner`: môi trường test đúng cấp

`ApplicationContextRunner` tạo một **non-web ApplicationContext** có thể thay đổi property, user configuration, auto-configurations, bean registrations và classloader cho từng test. Sau callback `run(...)`, context được đóng. Nó khác `@SpringBootTest`:

- Không cần khởi động toàn bộ Spring Boot application.
- Không tự scan mọi component của module chỉ vì nó nằm trong package.
- Mỗi lần `run` xây một context nhỏ cho tình huống rõ ràng.
- Có `withConfiguration(AutoConfigurations.of(...))` để test chính auto-configuration.
- Có `withClassLoader` để kiểm điều kiện presence/absence.
- Có `withBean` hoặc `withUserConfiguration` để kiểm user overrides.
- Có `withPropertyValues` để kiểm property conditions.
- Có `hasNotFailed`/`getFailure` và assertions về bean để chỉ rõ expected.

**Quan trọng:** `ApplicationContextRunner` không được hỗ trợ như một kỹ thuật chạy trực tiếp cho tests bên trong native image. Một native image có mô hình AOT/classpath khác, cần test riêng.

### 5.1. Bốn trạng thái cần phân biệt

```text
JAR / class có trong classpath?
    |
    +-- Có:
    |     +-- @ConditionalOnClass matches?
    |     +-- Property cho phép?
    |     +-- User đã cung cấp bean?
    |           -> auto bean tạo hoặc back off
    |
    +-- Không:
          +-- @ConditionalOnClass false -> không tạo optional bean
          +-- @ConditionalOnMissingClass true -> có thể tạo fallback
          +-- ApplicationContext vẫn khởi động thành công
```

Kiểm **chỉ một bean name vắng mặt** chưa đủ nếu application context đã crash. Vì thế nhánh absence phải có cả `hasNotFailed()` và assertion về fallback/bean không tồn tại.

## 6. `@ConditionalOnClass` và `@ConditionalOnMissingClass`

Các condition được xét qua Spring Boot metadata/`OnClassCondition`:

```java
@ConditionalOnClass(ThirdPartyClient.class)
```

nghĩa là chỉ tiếp tục khi class có thể được tìm thấy trong classpath phù hợp. Còn:

```java
@ConditionalOnMissingClass(
        "com.example.optional.ThirdPartyClient")
```

nghĩa là chỉ tiếp tục nếu class không được tìm thấy.

Spring Boot dùng **ASM metadata** khi đọc annotation trên configuration class, nên việc tham chiếu class literal tại `@ConditionalOnClass` cấp class trực tiếp thường an toàn ngay cả khi dependency thật sự thiếu. Tuy nhiên:

- Với **composed/meta-annotation**, Spring Boot khuyến nghị dùng `name = "com.vendor.Type"` thay cho `value = Type.class` vì metadata processing có khác biệt.
- Trên **@Bean method**, JVM có thể introspect method signature/return type trước khi condition trên method được áp dụng.
- Một conditional false **không sửa được** việc code khác chủ động load class đã thiếu từ static initializer, constructor hoặc bean method signature.
- Cần tổ chức optional types trong nested configuration an toàn (mục 7).

## 7. Bẫy số 1: đặt condition trên bean method quá muộn

**Không nên viết:**

```java
// PHẢN VÍ DỤ — chỉ là cấu trúc lỗi, không dùng làm file runnable.
@AutoConfiguration
class FragileAutoConfiguration {

    @Bean
    @ConditionalOnClass(ThirdPartyClient.class)
    ThirdPartyClient client() {
        return new ThirdPartyClient("auto");
    }
}
```

Dù method có `@ConditionalOnClass`, JVM có thể phải resolve `ThirdPartyClient` từ **return type** khi Spring reflect `FragileAutoConfiguration`, trước khi condition bỏ qua method. Trên một JVM thực sự thiếu SDK, quá trình xử lý bean methods có thể sinh `NoClassDefFoundError`/`IllegalStateException`.

**Mẫu khuyến nghị trong Spring Boot docs:**

```java
@AutoConfiguration(proxyBeanMethods = false)
public class SafeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ThirdPartyClient.class)
    static class SdkPresentConfiguration {

        @Bean
        ThirdPartyClient thirdPartyClient() {
            return new ThirdPartyClient("auto");
        }
    }
}
```

Snippet này giả định imports đầy đủ. Nested configuration được bảo vệ ở **cấp class**, trước khi Spring cần xử lý bean method signatures bên trong.

**Tinh tế:** `FilteredClassLoader` giúp chứng minh Spring condition bỏ qua cấu hình; nó **không nhất thiết tái tạo mọi lỗi linkage trong JVM thực**. Class của auto-config có thể vẫn được **định nghĩa bởi parent loader** nhìn thấy optional dependency, khiến một lỗi reflection thật bị che trong mô phỏng. Vì vậy vừa thiết kế nested config theo tài liệu, vừa chạy consumer packaging test thật cho optional JAR quan trọng.

## 8. Bẫy số 2: hiểu nhầm class “có mặt” với bean “có mặt”

`@ConditionalOnClass(ThirdPartyClient.class)` được quyết định bởi **khả năng nhìn thấy type**, không phải việc đã có bean `ThirdPartyClient`.

`@ConditionalOnMissingBean(ThirdPartyClient.class)` được xét theo **BeanFactory** ở thời điểm auto-configuration chạy. Ý nghĩa thường gặp:

1. ThirdPartyClient class tồn tại.
2. User chưa cấu hình ThirdPartyClient bean.
3. Auto-configuration tạo default client.
4. Nếu user đã cấu hình custom bean, auto-config **back off**, không tạo bean trùng.

Đó là **hai điều kiện độc lập**; test nên có cả:

- Class present → default bean được tạo.
- Class absent → no default bean, context vẫn sống.
- Class present + custom user bean → auto-config back off.
- Class present + property disabled → no default bean **dù dependency vẫn hiện diện**.

Không dùng FilteredClassLoader để giả “user chưa có bean”; dùng `withBean`/`withUserConfiguration` và assert đúng số lượng bean.

## 9. Project Java 17+ runnable: một auto-config có SDK giả và fallback

Ví dụ sẽ gồm:

- `ThirdPartyClient`: type mô phỏng SDK tùy chọn.
- `VendorClientAutoConfiguration`: tạo client nếu type có mặt và app chưa định nghĩa bean.
- `FallbackAutoConfiguration`: tạo `FallbackStatus` nếu SDK vắng mặt.
- `@ConditionalOnProperty` để chứng minh **disabled** khác **classpath absent**.
- `AutoConfiguration.imports`: registration metadata cho library khi được cài vào app thật.
- `VendorClientAutoConfigurationTest`: các tests với `ApplicationContextRunner` và `FilteredClassLoader`.

**Giới hạn minh họa:** Để project một module **copy và test được ngay**, SDK giả `ThirdPartyClient` được đặt trong `src/main/java`. Trong một **starter production**, SDK thật nên nằm trong artifact riêng và được khai báo optional/compileOnly phù hợp. Điều này không làm mất giá trị của unit tests về condition; nhưng package của project demo sẽ thực sự chứa SDK giả, nên **không thể coi project này đã kiểm packaging optional JAR thật**. Mục 26–28 giải thích cách thêm một consumer test không có JAR.

### 9.1. Cây thư mục

```text
filtered-classloader-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/optional/
    ThirdPartyClient.java
  src/main/java/com/example/autoconfig/
    FallbackStatus.java
    VendorClientAutoConfiguration.java
    FallbackAutoConfiguration.java
  src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
  src/test/java/com/example/autoconfig/
    VendorClientAutoConfigurationTest.java
```

Không có `@SpringBootApplication` hoặc `main` vì đây là **thư viện auto-configuration**. Test dùng `ApplicationContextRunner` trực tiếp; không cần Docker, network, database hoặc HTTP server.

## 10. Gradle cho thư viện auto-configuration

**`settings.gradle`**

```groovy
rootProject.name = 'filtered-classloader-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java-library'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Tại sao không áp Spring Boot Gradle plugin ở đây?** Thư viện không có `main` và không cần executable `bootJar`. `java-library` + Spring Boot BOM làm đúng mục tiêu: biên dịch library và chạy JUnit tests. Một ứng dụng sử dụng starter có thể dùng Boot plugin riêng.

**Dependency của `FilteredClassLoader`:** Nó thuộc `org.springframework.boot.test.context` trong `spring-boot-test`; `spring-boot-starter-test` đưa module test này vào test scope. Không thêm `spring-boot-test` vào production runtime chỉ để sử dụng FilteredClassLoader trong production.

**Gradle test classpath:** `testImplementation` có JUnit/AssertJ/Spring Test; `useJUnitPlatform()` giúp Gradle tìm các `@Test` của Jupiter. Nhớ dùng Java 17+ cho Spring Boot 3.5.

## 11. SDK giả: chỉ là loại dependency để lọc

**`src/main/java/com/example/optional/ThirdPartyClient.java`**

```java
package com.example.optional;

import java.util.Objects;

public final class ThirdPartyClient {

    private final String source;

    public ThirdPartyClient(String source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    public String source() {
        return source;
    }

    public String ping() {
        return "pong:" + source;
    }
}
```

Class này **không phải Spring bean tự động**. Nó chỉ là Java type hiện diện trong physical classpath của demo. Bean chỉ xuất hiện nếu configuration được đăng ký và conditions match. Test `new FilteredClassLoader(ThirdPartyClient.class)` yêu cầu class literal biên dịch được trong test; việc dùng literal ở test **không phá tác dụng mô phỏng** vì runner sử dụng filtered ClassLoader riêng để đánh giá conditions.

**Ở production:** Thay type demo bằng SDK JAR thật, ví dụ `com.vendor.sdk.Client` nằm trong `vendor-sdk.jar`. Khi tạo một library optional, bảo đảm artifact dependency graph không vô tình bắt mọi consumers phải mang SDK jar nếu họ không dùng feature.

## 12. Fallback status: type luôn có trên classpath

**`src/main/java/com/example/autoconfig/FallbackStatus.java`**

```java
package com.example.autoconfig;

public record FallbackStatus(String reason) {
}
```

`FallbackStatus` độc lập hoàn toàn với `ThirdPartyClient`. Khi SDK vắng mặt, ta không muốn tạo `ThirdPartyClient` bean nhưng **có thể** tạo một fallback/metadata bean mà code khác dùng để báo feature không khả dụng. Đây là ví dụ về `@ConditionalOnMissingClass`, không có nghĩa mọi starter phải tạo fallback.

Một ứng dụng thật có thể chọn **không tạo gì** khi thiếu SDK. Nếu feature thật bắt buộc và thiếu dependency là lỗi deployment, nên fail-fast với error rõ — không tạo no-op giả khiến nghiệp vụ bị mất âm thầm. Chọn hành vi theo library contract.

## 13. Auto-config nhánh SDK có mặt: nested configuration an toàn

**`src/main/java/com/example/autoconfig/VendorClientAutoConfiguration.java`**

```java
package com.example.autoconfig;

import com.example.optional.ThirdPartyClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(proxyBeanMethods = false)
public class VendorClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ThirdPartyClient.class)
    @ConditionalOnProperty(
            prefix = "demo.vendor",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    static class SdkPresentConfiguration {

        @Bean
        @ConditionalOnMissingBean(ThirdPartyClient.class)
        ThirdPartyClient thirdPartyClient() {
            return new ThirdPartyClient("auto");
        }
    }
}
```

**Cơ chế:**

1. `VendorClientAutoConfiguration` chỉ chứa nested configuration, không đưa optional return type vào `@Bean` method của outer class.
2. `@ConditionalOnClass(ThirdPartyClient.class)` quyết định có xử lý nested configuration không.
3. `@ConditionalOnProperty` tách **“user tắt feature”** khỏi **“SDK không có trong runtime”**.
4. `@ConditionalOnMissingBean(ThirdPartyClient.class)` bảo đảm custom user bean được ưu tiên.
5. `@Bean` trả typed `ThirdPartyClient` chỉ nằm trong class đã được bảo vệ bởi condition.
6. `proxyBeanMethods=false` phù hợp configuration không cần gọi chéo bean methods.

**Về phần mềm đóng gói:** Mã auto-config **vẫn cần compile với ThirdPartyClient**. Trong một project multi-module thật, nên khai báo dependency compile-only/optional ở module auto-config và đảm bảo starter cho phép người dùng chọn SDK. Bài demo đặt type trong main sources để thuận tiện đọc, không khẳng định package đã optional thực.

## 14. Auto-config nhánh SDK vắng: dùng tên FQCN

**`src/main/java/com/example/autoconfig/FallbackAutoConfiguration.java`**

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(proxyBeanMethods = false)
@ConditionalOnMissingClass(
        "com.example.optional.ThirdPartyClient")
public class FallbackAutoConfiguration {

    @Bean
    FallbackStatus fallbackStatus() {
        return new FallbackStatus("optional SDK not available");
    }
}
```

Class fallback **không import ThirdPartyClient**; condition kiểm tên dưới dạng String. Nó không cần class SDK tồn tại để compile và không làm reflect return type optional. Khi class SDK thực sự thiếu, Spring vẫn có thể tạo `FallbackStatus` nếu auto-config được đăng ký.

**Điểm dễ nhầm:** `@ConditionalOnMissingClass` **không đồng nghĩa** `@ConditionalOnMissingBean`. Trong test mà class SDK vẫn hiện diện nhưng user đặt `demo.vendor.enabled=false`, fallback condition **không match** vì class vẫn có mặt. Theo contract demo, khi feature bị disabled thì không có cả SDK client bean lẫn fallback bean. Nếu business muốn “disabled = fallback”, cần một điều kiện khác, không giả đó là classpath absence.

## 15. Đăng ký auto-configuration trong Boot 3.5

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
com.example.autoconfig.VendorClientAutoConfiguration
com.example.autoconfig.FallbackAutoConfiguration
```

Trong **Spring Boot 3.x**, auto-configuration library được phát hiện từ file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Mỗi dòng là một fully qualified class name, có thể có comments bằng `#`. Đừng dựa vào việc Spring component scan tình cờ quét được auto-configuration class từ package của ứng dụng.

**Tại sao test vẫn dùng `AutoConfigurations.of(...)` rõ ràng?** `ApplicationContextRunner` trong demo chủ động chỉ định auto-configuration cần test để giữ context hẹp; nó **không chứng minh imports metadata đã được quét đúng khi một consumer dùng starter**. Việc file đúng tên/đúng contents và auto-config xuất hiện trong ứng dụng consumer thực phải được kiểm riêng (mục 27).

Nếu library đổi tên auto-config class, cần xem cơ chế replacement metadata của Boot và backward compatibility đối với `before/after/exclude`; không tự đổi các tên trong imports file mà bỏ qua người dùng cũ.

## 16. JUnit tests: khung dùng lại cho mọi tình huống

**`src/test/java/com/example/autoconfig/VendorClientAutoConfigurationTest.java`**

```java
package com.example.autoconfig;

import com.example.optional.ThirdPartyClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

class VendorClientAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            VendorClientAutoConfiguration.class,
                            FallbackAutoConfiguration.class));

    @Test
    void sdkAvailableCreatesDefaultClient() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(
                    ThirdPartyClient.class);
            assertThat(context.getBean(
                    ThirdPartyClient.class).source())
                    .isEqualTo("auto");
            assertThat(context).doesNotHaveBean(
                    FallbackStatus.class);
        });
    }

    @Test
    void sdkClassHiddenSkipsClientAndCreatesFallback() {
        runner.withClassLoader(
                new FilteredClassLoader(ThirdPartyClient.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(
                            "thirdPartyClient");
                    assertThat(context).hasSingleBean(
                            FallbackStatus.class);
                    assertThat(context.getBean(
                            FallbackStatus.class).reason())
                            .isEqualTo(
                                    "optional SDK not available");
                });
    }

    @Test
    void sdkPackageHiddenBehavesLikeMissingLibrary() {
        runner.withClassLoader(
                new FilteredClassLoader("com.example.optional"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(
                            "thirdPartyClient");
                    assertThat(context).hasSingleBean(
                            FallbackStatus.class);
                });
    }

    @Test
    void customUserBeanWinsOverAutoConfiguredClient() {
        runner.withBean(
                ThirdPartyClient.class,
                () -> new ThirdPartyClient("custom"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            ThirdPartyClient.class);
                    assertThat(context.getBean(
                            ThirdPartyClient.class).source())
                            .isEqualTo("custom");
                    assertThat(context).doesNotHaveBean(
                            FallbackStatus.class);
                });
    }

    @Test
    void propertyDisabledDoesNotMeanClassAbsent() {
        runner.withPropertyValues(
                "demo.vendor.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(
                            ThirdPartyClient.class);
                    assertThat(context).doesNotHaveBean(
                            FallbackStatus.class);
                });
    }

    @Test
    void filteredLoaderRejectsClassNameDirectly()
            throws Exception {

        try (FilteredClassLoader loader =
                new FilteredClassLoader(
                        ThirdPartyClient.class)) {
            assertThrows(ClassNotFoundException.class,
                    () -> loader.loadClass(
                            ThirdPartyClient.class.getName()));
        }
    }
}
```

**Đây là một file JUnit hoàn chỉnh với sáu `@Test`**, không chỉ pseudocode. Tên package, imports, class names và files được giữ nhất quán. Mỗi `runner.run(...)` tạo context và đóng sau callback; các tests không dùng Docker/network/JPA hoặc `@SpringBootTest`.

### 16.1. Test 1 — dependency có mặt

`sdkAvailableCreatesDefaultClient` chứng minh:

- Context không fail.
- Chính xác một bean `ThirdPartyClient`.
- Bean default có `source="auto"`.
- Không có `FallbackStatus`.

Nếu test chỉ assert context startup mà không assert bean behavior, một condition bị xóa vô tình vẫn có thể khiến test xanh dù auto-config không làm gì.

### 16.2. Test 2 — dependency class bị ẩn

`sdkClassHiddenSkipsClientAndCreatesFallback` là bài học trung tâm:

- `withClassLoader(new FilteredClassLoader(ThirdPartyClient.class))` thay khả năng nhìn thấy class cho context.
- `@ConditionalOnClass` của nested config không match.
- `thirdPartyClient` bean không được tạo.
- `@ConditionalOnMissingClass` của fallback match.
- `FallbackStatus` được tạo đúng reason.
- Context không bị crash trong **simulation này**.

**Dùng assertion theo bean name** `"thirdPartyClient"` là cách rõ khi bean type thuộc optional dependency đang bị ẩn; không cần bắt context resolve chính optional type bằng một class literal từ test's parent ClassLoader.

### 16.3. Test 3 — ẩn cả package

`sdkPackageHiddenBehavesLikeMissingLibrary` mô phỏng phạm vi rộng hơn một type đơn lẻ. Hữu ích khi SDK có factory classes, annotations và converters mà nhiều conditions tham chiếu. Tuy nhiên, package filter vẫn không hứa xóa bytecode vật lý của mọi class/JAR khỏi JVM.

### 16.4. Test 4 — user bean override/backoff

`customUserBeanWinsOverAutoConfiguredClient` đưa bean trước khi auto-configuration có cơ hội đăng ký default. Điều này test **`@ConditionalOnMissingBean`**, không dùng FilteredClassLoader. Kết quả phải có một bean, nguồn `custom`, không tạo thêm `auto`.

### 16.5. Test 5 — property disabled

`propertyDisabledDoesNotMeanClassAbsent` mô phỏng tắt feature. SDK vẫn nhìn thấy, nên fallback **không** được bật theo classpath condition. Đây là dấu hiệu tốt để phát hiện nhầm `@ConditionalOnProperty` với `@ConditionalOnMissingClass`.

### 16.6. Test 6 — trực tiếp kiểm loader

`filteredLoaderRejectsClassNameDirectly` bảo đảm chính classloader có filter như dự kiến. Nó **không** chứng minh rằng mọi class được JVM định nghĩa bởi loader ấy; test số 2 mới cho thấy Spring condition có dùng visibility từ runner và cho ra branch mong muốn.

## 17. Kết quả kỳ vọng và cách chạy

Cấu trúc project có thể chạy với Gradle 8.x tương thích Spring Boot 3.5, JDK 17+ và dependencies theo BOM:

```bash
./gradlew test --tests com.example.autoconfig.VendorClientAutoConfigurationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.autoconfig.VendorClientAutoConfigurationTest
```

Nếu project chưa có Gradle wrapper, hãy tạo wrapper theo convention của nhóm trước; `build.gradle` và `settings.gradle` ở trên không tự tạo `gradlew`.

**Sáu test methods** được kỳ vọng PASS:

| Test | Class nhìn thấy? | Auto SDK bean? | Fallback bean? |
|---|---|---|---|
| `sdkAvailableCreatesDefaultClient` | Có | Có, 1 bean | Không |
| `sdkClassHiddenSkipsClientAndCreatesFallback` | Ẩn đúng class | Không | Có |
| `sdkPackageHiddenBehavesLikeMissingLibrary` | Ẩn package | Không | Có |
| `customUserBeanWinsOverAutoConfiguredClient` | Có | User bean, auto backs off | Không |
| `propertyDisabledDoesNotMeanClassAbsent` | Có nhưng property false | Không | Không |
| `filteredLoaderRejectsClassNameDirectly` | FilteredLoader trực tiếp | Không tạo context | Không tạo context |

Không có stdout business cố định. Nếu Gradle/JUnit sẵn sàng, kết quả dự kiến là `BUILD SUCCESSFUL`, còn report ở `build/reports/tests/test/index.html`. **Đây là đánh giá dựa trên API Spring Boot 3.5 và rà soát mã; tôi không tuyên bố đã chạy Gradle/JUnit trên repository của người học.**

## 18. Đọc kết quả bằng ConditionEvaluationReport

Một test khẳng định no bean là tốt, nhưng khi không biết **vì sao** bean bị bỏ qua, hãy dùng `ConditionEvaluationReport`. Spring Boot có initializer:

```java
// Snippet có thể thêm vào test khi cần debug.
import org.springframework.boot.autoconfigure.logging
        .ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

ApplicationContextRunner debugRunner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO))
                .withConfiguration(AutoConfigurations.of(
                        VendorClientAutoConfiguration.class,
                        FallbackAutoConfiguration.class));

debugRunner.withClassLoader(
        new FilteredClassLoader(ThirdPartyClient.class))
        .run(context -> assertThat(context).hasNotFailed());
```

**Cảnh báo cú pháp:** Hai dòng `import` trên được xuống dòng để trình bày; Java không cho phép tách giữa package và class name bằng newline không có dấu chấm đúng vị trí. Khi dùng snippet, hãy thay bằng một import trên một dòng:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
```

`ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` có trong Spring Boot 3.5; nó ghi report mức INFO. Thường chỉ bật khi debug vì report có thể dài. Đọc các positive/negative matches cho `OnClassCondition`, `OnBeanCondition` và `OnPropertyCondition`. Đừng assert nguyên văn report text trong unit test vì phrasing/logging có thể đổi giữa phiên bản; ưu tiên bean assertions, report là dữ liệu hỗ trợ điều tra.

### 18.1. Một điều kiện có thể không match vì nhiều lý do

Một bean không xuất hiện có thể vì:

- `@ConditionalOnClass` không match.
- `@ConditionalOnProperty` bị false.
- User bean khiến `@ConditionalOnMissingBean` back off.
- Parent context/bean search strategy khác.
- Auto-configuration chưa được import.
- Web/reactive context type không phù hợp.
- Bean definition bị exclude hoặc scan không tới.

**Không suy lý do từ “bean không có” đơn lẻ.** Khi cần đặc tả nguyên nhân, test kịch bản riêng và xem condition report.

## 19. Vì sao không dùng `@SpringBootTest` cho mọi nhánh?

`@SpringBootTest` nạp full application context, có component scanning, data sources, HTTP clients, security và beans khác. Khi kiểm một optional class condition, full context thường:

- Chạy chậm hơn nhiều.
- Có thể chạm network/DB hoặc startup side effects.
- Dễ có bean condition bị một test configuration khác làm lệch.
- Không tiện hoán đổi classloader per test method.
- Khiến test bị phụ thuộc application startup path thay vì riêng auto-configuration contract.

`ApplicationContextRunner` được thiết kế đúng mục đích: **mỗi kịch bản tạo context nhỏ được kiểm soát**. Nhưng không tuyệt đối hóa nó: vẫn cần ít nhất một consumer integration test với `AutoConfiguration.imports`, dependencies và scanning thực tế để bảo vệ packaging.

## 20. Non-web, servlet và reactive context runner

`ApplicationContextRunner` tạo **non-web** context. Nếu auto-configuration có:

```java
@ConditionalOnWebApplication(type = Type.SERVLET)
```

thì test non-web có thể không kích hoạt nó dù mọi SDK classes đều có mặt. Cần dùng đúng runner:

- `ApplicationContextRunner`: core/non-web auto-config.
- `WebApplicationContextRunner`: servlet web context conditions.
- `ReactiveWebApplicationContextRunner`: reactive web context conditions.

Ví dụ snippet:

```java
WebApplicationContextRunner servletRunner =
        new WebApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        MyServletAutoConfiguration.class))
                .withClassLoader(
                        new FilteredClassLoader(
                                OptionalServletAdapter.class));
```

Snippet cần imports và những class giả định; không phải file trong project runnable. Tương tự, WebFlux/reactive auto-config phải dùng reactive runner và dependencies phù hợp. Đừng dùng `@SpringBootTest(webEnvironment=...)` chỉ vì muốn lớp điều kiện nghĩ nó đang ở servlet context — runner đã có loại tương ứng.

## 21. Class filter và package filter: chọn mức độ phù hợp

**Ẩn một class** phù hợp khi auto-config chỉ cần một “marker” type:

```java
new FilteredClassLoader(ThirdPartyClient.class)
```

**Ẩn package** phù hợp khi dependency có nhiều public API types và annotations:

```java
new FilteredClassLoader("com.example.optional")
```

Tuy nhiên, một SDK có thể dùng nhiều packages: `com.vendor.api`, `com.vendor.internal`, `org.reactivestreams`. Ẩn một package không nhất thiết bắt mọi điều kiện liên quan. Khi cần mô phỏng thiếu một **artifact thực**, runtime dependency test với JAR bị loại bỏ đáng tin hơn.

**Tối ưu test coverage theo ma trận:**

| Biến thể | Rủi ro | Ưu tiên |
|---|---|---|
| Hide main marker class | Auto-config tạo bean sai | Bắt buộc |
| Hide whole SDK package | Code vẫn load class phụ | Nên có nếu SDK rộng |
| Hide one optional SPI resource | Condition/service loader sai | Khi có SPI |
| Hide transitive optional module class | Indirect conditions | Theo dependency graph |
| Real absent JAR in consumer runtime | Linkage/packaging errors | Cần khi public starter |
| Mismatch SDK versions | Binary incompatibility | Khi support nhiều versions |

## 22. `@ConditionalOnBean` và `@ConditionalOnMissingBean` dưới test filter

Có một điểm tinh tế về thứ tự:

- Bean conditions đánh giá **BeanFactory tại thời điểm auto-configuration được xử lý**.
- User-defined beans được kỳ vọng đăng ký trước auto-config.
- Nếu hai auto-configs cùng tạo bean có type giống nhau, thứ tự và `@AutoConfigureAfter/Before` có thể ảnh hưởng.
- `@ConditionalOnMissingBean` không phải global “trên toàn JVM không có bean”; nó nhìn theo BeanFactory/context hierarchy và search strategy.
- Một mock bean được thêm ở test có thể làm condition match khác production.

Vì vậy test `withBean(ThirdPartyClient.class, ...)` nên đi **trên runner bình thường**, không lọc ThirdPartyClient khỏi chính context rồi lại cố inject một bean cùng type. Nếu mục tiêu là SDK vắng mặt, test no-bean/fallback; nếu mục tiêu custom user override, test class present.

Khi muốn test BeanFactory hierarchy, dùng `withParent(...)` hoặc context structure cụ thể và nêu rõ `SearchStrategy`. Đừng biến bài absence thành một bài kiểm cả hierarchy trừ khi auto-config của bạn thật sự phụ thuộc nó.

## 23. `@ConditionalOnMissingClass` vs `@ConditionalOnMissingBean`

Hai annotation có tên gần giống nhưng tình huống khác nhau:

```text
Dependency có trên classpath?
    |
    +-- No:
    |      @ConditionalOnMissingClass => true
    |      @ConditionalOnMissingBean   => tùy BeanFactory, không nói lên dependency
    |
    +-- Yes:
           @ConditionalOnMissingClass => false
           Bean có tồn tại?
               +-- No  => @ConditionalOnMissingBean true
               +-- Yes => @ConditionalOnMissingBean false
```

Với fallback chỉ khi SDK thiếu, dùng `@ConditionalOnMissingClass`. Với default SDK client nhưng tôn trọng bean do user tự cấu hình, dùng `@ConditionalOnMissingBean` trong nhánh SDK-present.

Nếu sản phẩm cần fallback cả khi SDK tồn tại nhưng bị disabled, hãy thiết kế điều kiện nhiều nhánh rõ ràng, có test property false. Không “fake classpath absent” để thử một property branch.

## 24. Giới hạn cơ bản: parent ClassLoader và JVM linkage

**Điểm không được nói quá:** `FilteredClassLoader` **không gỡ JAR** khỏi Gradle/Maven testRuntimeClasspath. Nó chặn load **qua loader bị lọc**; nhiều class auto-config có thể vẫn được **định nghĩa bởi parent application ClassLoader**. Khi JVM reflect một class được định nghĩa ở parent, nó có thể resolve optional types bằng parent loader vốn vẫn nhìn thấy SDK.

Hệ quả: Test dùng `FilteredClassLoader` có thể PASS ở `hasNotFailed()` dù **một JVM thật sự không có SDK** sẽ fail khi reflect một `@Bean` method với optional return type. Đây là hạn chế thực tế được thảo luận trong Spring Boot issue #51377 (2026) về classloader mô phỏng. Vì vậy:

1. Vẫn dùng `FilteredClassLoader` cho **`OnClassCondition` và `OnMissingClassCondition` branch tests**.
2. Đặt optional return types trong **nested configuration đã được class-level guard**, theo docs chính thức.
3. Không coi test filter là chứng minh 100% của linkage/NoClassDefFoundError.
4. Với starter quan trọng, chạy ít nhất một **consumer app/JVM** có runtimeClasspath **không chứa optional dependency** và kiểm startup.
5. Với ServiceLoader và resource scanning, kiểm loader mà thư viện thật dùng; ClassLoader khác nhau có thể thấy resources khác nhau.

### 24.1. Một test “pass” không đồng nghĩa SDK đã biến mất

```java
// Snippet: class SDK vẫn có trên bytecode classpath của test.
ThirdPartyClient compiledType =
        new ThirdPartyClient("test");
```

Dòng này có thể chạy bình thường trong JUnit test class đã load từ parent classloader, dù một **context riêng** được xây với `FilteredClassLoader(ThirdPartyClient.class)`. Đây không phải bug của FilteredClassLoader; nó thể hiện hai môi trường nhìn class khác nhau. Không dùng reflection ở test classpath để “chứng minh” context condition đã đánh giá sai.

## 25. Giới hạn: ẩn class không thay runtime API version

Một auto-config có thể gọi method chỉ có ở SDK v2:

```java
// Phản ví dụ conceptual:
client.newMethodOnlyInV2();
```

`FilteredClassLoader` chỉ kiểm **có nhìn thấy type hay không**. Nó không tự đổi bytecode của SDK v2 thành v1, cũng không kiểm mọi constructor/method signature differences. Vì vậy một SDK v1 vẫn có class `ThirdPartyClient` nhưng thiếu method v2; condition có thể match rồi runtime ném `NoSuchMethodError`.

Để bảo vệ:

- Công bố supported SDK version range.
- Dùng Gradle dependency constraints/BOM, version alignment.
- Test consumer apps với **từng version** được support.
- Kiểm binary compatibility bằng compile/runtime tests.
- Có startup test với **SDK absent**, **SDK present-min**, **SDK present-max**.
- Với native/AOT, có test riêng cho reflection/proxies/hints.

Nếu deployment production dùng Gradle dependency locking, hãy kiểm đúng runtimeClasspath từ lockfile, không chỉ compileClasspath.

## 26. Làm optional dependency thật trong project multi-module

Khi triển khai starter thực tế, cấu trúc thường có:

```text
acme-project/
  vendor-api/                   <- API của bên thứ ba hoặc dependency external
  acme-autoconfigure/           <- @AutoConfiguration, optional integration
  acme-starter/                 <- dependencies mặc định theo product
  consumer-with-sdk/           <- app chạy với vendor SDK
  consumer-without-sdk/        <- app chạy không có vendor SDK
```

Ví dụ cấu hình **ý tưởng Gradle** cho module auto-config:

```groovy
// Snippet thuộc :acme-autoconfigure/build.gradle, không độc lập:
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly 'com.vendor:vendor-sdk:1.2.3'
    testImplementation 'com.vendor:vendor-sdk:1.2.3'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

`compileOnly` cho phép compile source tham chiếu optional type mà không tự publish nó như runtime dependency bắt buộc. `testImplementation` để unit tests vẫn có class và áp `FilteredClassLoader`. Với Maven có thể dùng `<optional>true</optional>` trên dependency ở module autoconfigure, cùng chiến lược test cho consumers.

**Nhưng** đừng nhầm `compileOnly` là đủ để mọi runtime path an toàn: nếu `@Bean` signatures/static initializers vẫn tham chiếu SDK trước khi conditions đánh giá, ứng dụng không có SDK vẫn có thể crash. Phải kiểm cả packaging test thật.

### 26.1. Starter có thể cố ý kéo SDK vào

Nếu `acme-starter` đại diện experience “just add starter, SDK ready”, nó có thể kéo SDK theo runtime. `acme-autoconfigure` riêng phải vẫn an toàn khi SDK vắng. Test matrix theo **artifact mà user thật cài**, không chỉ module chứa source auto-config.

## 27. Consumer test với SDK thực sự không được cài

Mục tiêu của một **runtime absent-dependency test**:

- Fork một JVM hoặc chạy test trong một module consumer riêng.
- Dependencies chứa `acme-autoconfigure` và Spring Boot runtime cần thiết.
- **Không có** `vendor-sdk` trên runtimeClasspath.
- Boot startup/auto-configuration import được thực thi thật.
- Assert ứng dụng **khởi động**, không đăng ký vendor-specific bean, và fallback/absence behavior đúng.

Điều kiện “không có” phải được kiểm bằng dependency graph trước khi chạy:

```bash
./gradlew :consumer-without-sdk:dependencies --configuration runtimeClasspath
./gradlew :consumer-without-sdk:dependencyInsight --dependency vendor-sdk --configuration runtimeClasspath
```

Một lệnh thứ hai báo **no matching dependency** có thể là expected. Tuy nhiên chỉ nhìn `dependencyInsight` chưa đủ nếu jar được bỏ vào classpath thủ công hoặc được shaded trong một dependency khác. Với consumer thật, có thể dùng `Class.forName("com.vendor.sdk.VendorClient")` trong chính forked JVM để xác minh class absent.

**Không đặt SDK thật trong `testImplementation` của consumer-without-sdk** nếu test chạy trong cùng process với test runtime classpath — nếu không bạn sẽ vô tình đưa class trở lại. Khi cần assert bằng API type, dùng **tên class string** và bean names thay vì import optional SDK type vào consumer test.

### 27.1. Test startup như thế nào?

Một phương án: tạo một Spring Boot consumer application tối giản, cài `acme-autoconfigure`, dùng `@SpringBootTest` hoặc gọi `SpringApplication.run` trong forked JVM; **đảm bảo app không kéo SDK qua test dependencies**. Kiểm startup, condition report, bean names. Đây là một **integration test riêng**, không nằm trong runnable one-module demo ở mục 9–17.

## 28. Bẫy `AutoConfiguration.imports` bị test runner che mất

Trong runnable demo, test dùng:

```java
new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
                VendorClientAutoConfiguration.class,
                FallbackAutoConfiguration.class));
```

Điều này **đăng ký auto-configuration tường minh**. Nếu file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` bị viết sai tên, test vẫn có thể PASS vì runner không phụ thuộc file imports trong mẫu này.

**Giải pháp:** Ngoài test classloader branch, thêm một test/consumer module kiểm **auto-registration** từ published JAR:

- JAR chứa đúng imports file.
- Mỗi FQCN trong file tồn tại sau refactor.
- Spring Boot app thực thấy auto-config candidates.
- Với SDK có mặt, auto-config tạo bean (trừ custom override/property).
- Với SDK vắng, app vẫn startup theo contract.
- Không có component scan workaround vô tình che lỗi auto-imports.

Một test focused `ApplicationContextRunner` trả lời “điều kiện này đúng không?”; consumer test trả lời “library được đóng gói/import đúng không?”. Cả hai là cần thiết khi phát hành starter cho nhiều nhóm.

## 29. Resource filter và `@ConditionalOnResource`

Ví dụ auto-config chỉ hoạt động nếu một file có mặt:

```java
// Snippet:
@AutoConfiguration
@ConditionalOnResource(
        resources = "classpath:features/optional-adapter.flag")
class FeatureResourceAutoConfiguration {

    @Bean
    FeatureMarker featureMarker() {
        return new FeatureMarker();
    }
}
```

Muốn mô phỏng resource absent:

```java
runner.withClassLoader(new FilteredClassLoader(
        new ClassPathResource(
                "features/optional-adapter.flag")))
    .run(context ->
        assertThat(context).doesNotHaveBean("featureMarker"));
```

Đây là snippets, **không nằm trong runnable project**; cần thêm resource, bean type và imports nếu triển khai. Lưu ý `ClassPathResource` dùng path theo classpath, không phải một file bất kỳ trên ổ đĩa. Nếu code thật đọc file bằng absolute `Path` hoặc HTTP, FilteredClassLoader không can thiệp. Nếu code lấy resource qua parent ClassLoader trực tiếp, filter của runner có thể không được dùng. Test phải đi đúng lookup boundary mà production code sử dụng.

## 30. Không dùng `@MockitoBean` để “loại dependency khỏi classpath”

Một test đặt:

```java
@MockitoBean
ThirdPartyClient client;
```

không làm `ThirdPartyClient` vắng khỏi classpath. Ngược lại:

- Mockito muốn mock type phải nhìn thấy class.
- Bean mock có thể khiến `@ConditionalOnBean(ThirdPartyClient.class)` match.
- Bean mock có thể khiến `@ConditionalOnMissingBean(ThirdPartyClient.class)` **không match**.
- Auto-config có thể back off vì test đã thêm bean.
- Test pass nhưng không hề kiểm nhánh missing SDK.

Nếu muốn test **missing bean** với class vẫn có mặt, tạo runner không có bean hoặc test conditional bean logic. Nếu muốn test **missing class**, dùng `FilteredClassLoader`. Nếu muốn test **missing JAR**, dùng runtime packaging test.

## 31. Không dùng `excludeAutoConfiguration` làm bằng chứng thiếu class

`@SpringBootTest(excludeAutoConfiguration=...)` hoặc `@ImportAutoConfiguration(exclude=...)` (tùy annotation hỗ trợ) có thể **ngăn một auto-configuration được áp dụng**, nhưng không khiến dependency SDK biến mất khỏi classpath. Một test “bean không có” do auto-config bị exclude **không** chứng minh `@ConditionalOnClass` đã back off.

Tương tự, dùng `@ConditionalOnProperty` false có thể tắt bean nhưng class vẫn có mặt. Những điều kiện ấy cần test riêng theo nguyên nhân để tránh false confidence.

## 32. Tránh dùng class name String nhầm vị trí

Một số API nhận class names, một số nhận package names:

| API | Tham số string nghĩa là |
|---|---|
| `@ConditionalOnClass(name = "...")` | **Fully qualified class name** |
| `@ConditionalOnMissingClass("...")` | **Fully qualified class name** |
| `new FilteredClassLoader("...")` | **Package name(s)** bị ẩn |
| `new FilteredClassLoader(MyClass.class)` | Type cụ thể |
| `new FilteredClassLoader((Predicate<String>) name -> ...)` | Class binary name hoặc resource name tùy callback |
| `new ClassPathResource("...")` | **Resource path** trong classpath |
| `AutoConfiguration.imports` | Một **FQCN auto-configuration** mỗi dòng |

Nếu bạn viết `new FilteredClassLoader("com.vendor.sdk.VendorClient")` vì thấy `@ConditionalOnMissingClass("com.vendor.sdk.VendorClient")` giống nhau, bạn đang truyền **package filter string** chứ không khai báo chính xác một class theo API intent. Hãy dùng `new FilteredClassLoader(VendorClient.class)` khi class có thể tham chiếu, hoặc predicate khớp chính xác binary name.

## 33. Debug “bean vẫn xuất hiện dù đã filter class”

Các khả năng:

1. Điều kiện **không** được áp dụng: auto-config class không có `@ConditionalOnClass` đúng vị trí.
2. Filter nhắm sai package/FQCN/classloader.
3. Bean đến từ **user configuration** hoặc auto-config khác.
4. Condition dùng **một marker class khác** vẫn có mặt.
5. Filter chạy ở runner này nhưng test kiểm một context khác.
6. Một parent ClassLoader vẫn load/define auto-config class có optional reference.
7. SDK xuất hiện qua một transitive/shaded dependency khác hoặc classloader con.
8. Test lỡ thêm mock/user bean trước run.
9. App context đã được cache từ cấu hình khác (với `@SpringBootTest`).
10. Code dùng reflection/ServiceLoader không theo context classloader dự định.

**Cách debug:** Assert tên và type bean, xem `ConditionEvaluationReport`, kiểm đúng test runner classloader, kiểm dependency graph, rồi thêm **real absent-JAR** scenario nếu nghi JVM linkage. Không chỉ “thêm `@DirtiesContext`” vì nó không thay đổi classpath.

## 34. Debug “context crash khi SDK bị ẩn”

Các nguyên nhân thường thấy:

| Biểu hiện | Khả năng | Hướng xử lý |
|---|---|---|
| `NoClassDefFoundError` lúc Spring reflect auto-config | Optional type ở return/parameter của outer `@Bean` method | Tách nested config và đặt class-level `@ConditionalOnClass` |
| `ClassNotFoundException` khi gọi `Class.forName` | Code tự load class không guard | Dùng condition và tránh eager static load |
| `BeanCreationException` | Optional bean vẫn được gọi | Kiểm conditions, @Import, bean overrides |
| `NoSuchMethodError` | SDK version không hợp | Binary compatibility/real runtime tests |
| Report không có auto-config | Imports registration lỗi | Test consumer imports thực |
| Condition positive bất ngờ | Filter nhắm sai class hoặc condition dùng type khác | Javadoc, source, report |
| Fallback không tạo | Property/other condition, config chưa import | Kiểm condition report và bean names |
| Context fail do một library khác | Lọc package quá rộng | Filter đúng SDK, thu hẹp scope |
| Spring web condition không match | Dùng non-web runner | Web/Reactive runner phù hợp |
| Native tests không chạy với runner | AOT limitations | Native-specific tests |

**Không nuốt startup failure** rồi chỉ assert no bean; một context chết không phải một “skip optional dependency” thành công. Luôn dùng `assertThat(context).hasNotFailed()` cho nhánh được mong đợi startup.

### 34.1. Lỗi khiến test xanh giả

Nếu test chỉ viết:

```java
runner.withClassLoader(new FilteredClassLoader(
        ThirdPartyClient.class))
    .run(context -> assertThat(context)
            .doesNotHaveBean("someUnrelatedBean"));
```

thì cả khi optional client được tạo sai, test vẫn có thể xanh vì assert vào bean không liên quan. Test phải assert **đúng bean chịu điều kiện** và optionally fallback behavior.

## 35. Tests matrix tối thiểu cho một optional integration

| Dependency | Property | Custom user bean | Expected SDK bean | Expected fallback | Startup |
|---|---|---|---|---|---|
| Present | default true | No | Auto bean | None | PASS |
| Present | default true | Yes | User bean, auto back off | None | PASS |
| Present | false | No | None | None theo demo | PASS |
| Absent (FilteredClassLoader) | default | No | None | Fallback | PASS |
| Absent (whole package) | default | No | None | Fallback | PASS |
| Absent (real consumer runtime) | default | No | None | Fallback | PASS |
| Present but old binary-incompatible SDK | default | No | Policy-dependent | Policy-dependent | Test compatibility |
| Absent SDK but missing imports metadata | default | No | None | Có thể thiếu fallback | Test packaging, không chỉ runner |

**Tối thiểu** phải có positive + negative classpath tests + context startup. Với published starter, cần thêm consumer test để bảo vệ sự khác nhau giữa simulation và runtime packaging.

## 36. Khi nào không cần FilteredClassLoader?

Không cần nếu bài toán thực là:

- Một property false → `withPropertyValues("feature.enabled=false")`.
- User cung cấp bean → `withBean(...)`.
- Thiếu HTTP response → mock web server/RestClientTest.
- Một runtime service không reachable → Testcontainers/WireMock network tests.
- Một test slice không include bean do scan/filter → slice config tests.
- Một @Profile không active → profile property/environment test.
- Một enum value không được map → unit test/domain test.
- Một optional JAR **thật sự** cần bị gỡ → consumer runtime test.

FilteredClassLoader là **công cụ sắc cho class/resource visibility**, không phải cách chung để mô phỏng mọi dependency unavailable hay mọi exception của auto-config.

## 37. Bài tập thực hành

### A. Đọc kết quả filter

Một test dùng `new FilteredClassLoader(ThirdPartyClient.class)`, `@ConditionalOnClass` false nhưng context có fallback. Đây là skip thành công hay test fail? Điều kiện nào phải assert thêm?

**Đáp án:** Skip thành công **nếu** contract mong fallback; assert `hasNotFailed()`, client bean vắng và fallback có mặt.

### B. Class hay bean?

JAR SDK có mặt nhưng user không khai báo SDK bean. `@ConditionalOnClass` và `@ConditionalOnMissingBean` trả gì?

**Đáp án:** Class condition true; missing bean true (trong context/phase phù hợp), vì hai điều kiện đo hai thứ khác nhau.

### C. Property false

SDK class còn đó nhưng `demo.vendor.enabled=false`. Fallback có tự được tạo theo `@ConditionalOnMissingClass` không?

**Đáp án:** Không; class vẫn present. Bài demo mong không có cả auto client lẫn fallback.

### D. User bean

Ứng dụng có custom `ThirdPartyClient("custom")`. Auto-config được phép tạo thêm default client không?

**Đáp án:** Không, nhờ `@ConditionalOnMissingBean`; kiểm context chỉ một bean và source custom.

### E. Lọc package

SDK có classes trong `com.vendor.api` và `com.vendor.internal`. Ẩn `com.vendor.api` đã giống xóa toàn JAR chưa?

**Đáp án:** Chưa; package khác, resources, transitive JARs và parent loader vẫn có thể tồn tại.

### F. Composed annotation

Bạn tạo `@ConditionalOnVendor` như một meta-annotation trên `@ConditionalOnClass(VendorClient.class)`. Tài liệu Spring Boot lưu ý điều gì?

**Đáp án:** Nên dùng `name="com.vendor.VendorClient"` ở composed condition, vì ASM metadata xử lý class literal trên meta-annotation khác cấp class trực tiếp.

### G. Method signature

`@Bean @ConditionalOnClass(VendorClient.class) VendorClient client()` ở outer config bị JVM linkage error khi SDK thực sự không có. Sửa thế nào?

**Đáp án:** Chuyển optional bean method vào nested `@Configuration @ConditionalOnClass(VendorClient.class)`.

### H. Loader vs real JAR

FilteredClassLoader test xanh nhưng consumer không có `vendor-sdk.jar` bị `NoClassDefFoundError`. Test có “nói dối” không?

**Đáp án:** Nó chỉ chứng minh điều kiện dưới context classloader giả lập, không bảo đảm class resolution của parent-defined classes. Thêm consumer runtime test thật và sửa config signatures.

### I. Imports metadata

`AutoConfigurations.of(VendorClientAutoConfiguration.class)` pass, nhưng người dùng cài starter không thấy bean. Điều gì có thể sai?

**Đáp án:** File `AutoConfiguration.imports` sai/missing; context runner explicit import không kiểm auto-discovery. Test published artifact.

### J. Native image

Bạn chạy ApplicationContextRunner test trong native image và muốn kết luận auto-config an toàn AOT. Có đáng tin không?

**Đáp án:** Spring Boot ghi rõ runner không hoạt động như một công cụ test native image; dùng native-specific build/tests.

### K. Filter resource

Condition phụ thuộc `classpath:feature.flag` nhưng bạn chỉ filter một Java class. Có kiểm nhánh thiếu resource không?

**Đáp án:** Không; lọc resource cụ thể qua constructor `ClassPathResource`, test đúng lookup boundary.

### L. SDK đổi version

SDK v1 và v2 đều chứa class `VendorClient`, nhưng chỉ v2 có method `newFeature()`. `@ConditionalOnClass` có ngăn `NoSuchMethodError` trên v1 không?

**Đáp án:** Không; kiểm supported version và chạy compatibility test với JAR thật.

### M. Test framework hiện diện

Một test dùng `@MockitoBean` mock VendorClient để “giả SDK absent”. Vì sao không đúng?

**Đáp án:** Mock bean đòi class present và còn thay đổi `@ConditionalOnBean/MissingBean`, không làm class biến mất.

### N. Phương pháp debug

Context thiếu default client. Nêu năm nguyên nhân không liên quan FilteredClassLoader bị lỗi.

**Gợi ý:** Property false, user bean, imports không đăng ký, web-type condition không match, bean bị exclude, condition trên class khác, auto-config order.

## 38. Checklist trước khi merge starter

- [ ] Đã xác định loại optional dependency: class, bean, property hay runtime service.
- [ ] `@ConditionalOnClass` kiểm đúng entrypoint class của SDK.
- [ ] `@ConditionalOnMissingClass` dùng đúng FQCN theo contract.
- [ ] SDK optional không bị ép thành runtime dependency bắt buộc ngoài ý muốn.
- [ ] Optional type chỉ được tham chiếu trong configuration đã guard an toàn.
- [ ] Không đặt optional return type ở outer `@Bean` method rồi kỳ vọng method condition đủ bảo vệ.
- [ ] Composed annotation dùng `name` khi cần để tránh metadata issue.
- [ ] Có test class present với default bean.
- [ ] Có test class absent dùng `FilteredClassLoader(SomeClass.class)`.
- [ ] Có test package absent nếu library gồm nhiều types liên quan.
- [ ] Có assert context `hasNotFailed()` trong absence branch.
- [ ] Có assert optional bean vắng mặt **theo đúng bean name/type**.
- [ ] Có assert fallback được tạo hoặc cố tình không tạo theo contract.
- [ ] Có test custom user bean khiến auto-config back off.
- [ ] Có test feature property disabled riêng.
- [ ] Không dùng `@MockitoBean` để mô phỏng classpath absent.
- [ ] Không dùng `excludeAutoConfiguration` thay cho class condition test.
- [ ] Dùng `ApplicationContextRunner` khi mục tiêu là non-web auto-config.
- [ ] Dùng đúng Web/Reactive runner nếu có conditional web type.
- [ ] Có biết `FilteredClassLoader(String...)` là **package names**, không phải class names.
- [ ] Không lọc package Spring/JDK quá rộng trong test.
- [ ] Resource filter chỉ được dùng nếu code phụ thuộc classpath resources.
- [ ] Condition report có thể được bật để debug match/mismatch.
- [ ] `AutoConfiguration.imports` có đúng FQCN/đóng gói vào JAR.
- [ ] Có consumer startup test với SDK **thực sự absent** cho public starter/critical integration.
- [ ] Có tests cho SDK version compatibility nếu API thay đổi giữa versions.
- [ ] Có AOT/native test riêng nếu sản phẩm hỗ trợ native image.
- [ ] Không báo simulated classpath test là bằng chứng “đã gỡ JAR khỏi JVM”.
- [ ] Test vẫn đọc được sau nâng Spring Boot version, import packages không trộn Boot 3.x/4.x.
- [ ] QA báo trung thực code review so với tests thực sự đã chạy.

**Kết luận:** `FilteredClassLoader` giúp kiểm có hệ thống các nhánh **dependency present/absent** của Spring Boot auto-configuration mà không phải thay Gradle dependencies cho từng test. Kết hợp `ApplicationContextRunner`, `@ConditionalOnClass`, `@ConditionalOnMissingClass` và bean assertions, ta có thể xác nhận auto bean được tạo khi SDK có mặt, được bỏ qua khi SDK thiếu, fallback được đăng ký khi thích hợp, và context không crash trong mô phỏng. Nhưng **test classloader không phải phép chứng minh toàn bộ runtime linkage**. Khi phát hành starter cho người dùng thật, luôn bảo vệ optional class signatures bằng nested configuration và bổ sung consumer test trong một JVM **thực sự không có optional JAR**.

### Tài liệu tham khảo chính thức và bổ sung

- Spring Boot 3.5.16 — Creating Your Own Auto-configuration, phần Class Conditions, Testing Auto-configuration và Overriding the Classpath: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 — Javadoc `FilteredClassLoader` và các constructors/filter APIs: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 — Javadoc `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 — Javadoc `AbstractApplicationContextRunner.withClassLoader`/`withBean`/`run`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
- Spring Boot 3.5 — Javadoc `@ConditionalOnClass`, class-level annotation và @Bean method signature caveat: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 — `ConditionEvaluationReportLoggingListener` forLogLevel API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot — Discussed limitation of FilteredClassLoader and parent-defined classes, issue #51377: https://github.com/spring-projects/spring-boot/issues/51377
- Gradle — Dependency configurations, compileOnly vs implementation/testImplementation: https://docs.gradle.org/current/userguide/java_library_plugin.html
