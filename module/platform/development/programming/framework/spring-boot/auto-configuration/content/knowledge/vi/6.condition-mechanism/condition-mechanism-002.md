# ConditionContext cung cấp Environment, registry, BeanFactory và ClassLoader

> **Phạm vi:** Spring Boot 3.3.x / Spring Framework 6.1, Java 17+. Bài này giải thích **đối tượng `ConditionContext` mà Spring truyền vào khi đánh giá một `Condition`**: nó cung cấp thông tin cấu hình, bean definitions và khả năng nạp class để ra quyết định có đăng ký cấu hình/bean hay không. Đây là kiến thức về **cơ chế điều kiện**, không phải hướng dẫn dùng `ApplicationContext` để truy cập bean trong runtime.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chữ ký `Condition.matches(ConditionContext, AnnotatedTypeMetadata)` và vai trò của từng tham số.
2. Phân biệt năm API của `ConditionContext`: `getEnvironment()`, `getRegistry()`, `getBeanFactory()`, `getClassLoader()` và `getResourceLoader()`.
3. Biết khi nào kiểm tra **property/profile**, **bean definition**, **metadata của BeanFactory** hoặc **class có mặt**; biết vì sao những câu hỏi này khác nhau.
4. Nhận diện sự khác biệt giữa pha **parse configuration** và **register bean**; tránh đọc kết quả bean definition ở thời điểm chưa phù hợp.
5. Viết và kiểm thử một `Condition` tùy biến bằng Spring Boot 3.3 + Java 17 mà không tự khởi tạo bean hay làm thay đổi registry trong `matches`.
6. Biết khi nào **không cần viết Condition riêng**, vì Spring Boot đã có `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean` và `@ConditionalOnMissingBean`.

Tư duy quan trọng: **`ConditionContext` là một cửa sổ nhìn vào bối cảnh lúc Spring đánh giá điều kiện, không phải bản sao đầy đủ của ứng dụng đã khởi tạo xong.** Mỗi thành phần có phạm vi nhìn thấy, thời điểm và giới hạn riêng.

## 2. Từ @Conditional đến Condition.matches

Spring Framework có annotation `@Conditional`. Khi gắn nó lên một class cấu hình hoặc một phương thức `@Bean`, bạn chỉ định các class triển khai `Condition`:

```java
@Conditional(MyCondition.class)
```

Đây là một **fragment annotation**, không phải file Java độc lập. Hợp đồng cốt lõi:

```java
public interface Condition {
    boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata);
}
```

Đây là **chữ ký rút gọn để giải thích**, không phải định nghĩa lại interface Spring trong dự án.

- `context`: cung cấp các công cụ và trạng thái mà Spring có ở thời điểm đánh giá.
- `metadata`: mô tả class hoặc method đang mang annotation; có thể đọc các annotation attributes **mà không cần khởi tạo bean**.
- `true`: điều kiện match; Spring có thể tiếp tục xem xét class/method đó.
- `false`: điều kiện không match; Spring bỏ qua thành phần được bảo vệ ở pha thích hợp.

**`true` không có nghĩa “tạo bean ngay bây giờ”**. Còn có thể có condition khác, bean registration hoặc khởi tạo sau đó. **`false` không có nghĩa “xóa bean đã tồn tại”**; nó chủ yếu chặn việc xử lý cấu hình hay đăng ký bean definition đang xét.

### 2.1. @Conditional có thể gắn ở những mức nào?

```java
// Fragment: gắn trên class cấu hình.
@Configuration(proxyBeanMethods = false)
@Conditional(MyCondition.class)
class SomeConfiguration {
}
```

```java
// Fragment: gắn trên @Bean method trong @Configuration.
@Bean
@Conditional(MyCondition.class)
SomeService someService() {
    return new SomeService();
}
```

Trong ví dụ đầu, condition có thể loại cả class cấu hình. Trong ví dụ sau, condition quyết định việc đăng ký **bean definition của method** mà nó bảo vệ.

Đây là hai vị trí có thể được đánh giá ở những **pha khác nhau**. Vì thế, không thể giả định registry đã có cùng số bean definitions ở cả hai thời điểm.

## 3. ConditionContext gồm những gì?

Trong Spring Framework, interface `org.springframework.context.annotation.ConditionContext` cung cấp các phương thức sau:

| Method | Kiểu kết quả | Dùng để hỏi | Giới hạn quan trọng |
| --- | --- | --- | --- |
| `getRegistry()` | `BeanDefinitionRegistry` | Bean definition tên X đã được đăng ký ở registry này chưa? | Không đồng nghĩa đối tượng bean đã được tạo |
| `getBeanFactory()` | `ConfigurableListableBeanFactory` hoặc `null` | Factory có metadata của bean nào và cấu hình bean như thế nào? | Có thể không khả dụng ở một số môi trường/pha |
| `getEnvironment()` | `Environment` | Property, profile và nguồn cấu hình hiện tại có giá trị gì? | Giá trị phụ thuộc property-source precedence và thời điểm đánh giá |
| `getResourceLoader()` | `ResourceLoader` | Có thể truy cập resource qua abstraction của Spring không? | Resource tồn tại không bảo đảm nội dung hợp lệ hay mạng sẵn sàng |
| `getClassLoader()` | `ClassLoader` hoặc `null` | Loader dùng để tìm class là gì; class cần thiết có nhìn thấy được không? | Có class không đồng nghĩa API tương thích hoặc bean tạo thành công |

Hai getter có thể trả `null` là `getBeanFactory()` và `getClassLoader()`. Code điều kiện phải có chính sách xử lý thay vì gọi method trên giá trị có thể null mà không kiểm tra.

Sự khác biệt rất quan trọng:

```text
ConditionContext
  |
  +-- Environment    : properties, profiles, property sources
  |
  +-- Registry       : bean definitions đã đăng ký ở đây
  |
  +-- BeanFactory    : metadata / cơ sở tạo và quản lý beans
  |
  +-- ClassLoader    : khả năng nhìn thấy class trong runtime
  |
  +-- ResourceLoader : khả năng định vị resource
```

`ConditionContext` **không** phải `ApplicationContext`; nó không có contract “trả về mọi singleton đã khởi tạo xong”.

## 4. getEnvironment(): điều kiện dựa trên cấu hình

`context.getEnvironment()` trả `Environment`, cho phép kiểm tra một property hoặc trạng thái profile:

```java
String mode = context.getEnvironment()
        .getProperty("demo.mode", "safe");
boolean enabled = context.getEnvironment()
        .getProperty("demo.feature.enabled", Boolean.class, false);
boolean prod = context.getEnvironment()
        .acceptsProfiles(
                org.springframework.core.env.Profiles.of("prod"));
```

Đây là **fragment đặt bên trong phương thức `matches`**; cần imports và class bao quanh để compile.

- `getProperty(key, defaultValue)` lấy string hoặc giá trị mặc định.
- `getProperty(key, targetType, defaultValue)` yêu cầu Spring chuyển kiểu, ví dụ `Boolean`.
- `acceptsProfiles(Profiles.of(...))` kiểm tra biểu thức profile (Spring Framework 6.1).
- Các property sources có thứ tự ưu tiên; cùng key có thể nhận giá trị khác giữa CLI, environment variables và file cấu hình theo quy tắc của Spring Boot.

Ví dụ:

```properties
demo.feature.enabled=true
demo.feature.required-class=java.time.Instant
```

Điều kiện có thể kiểm tra cả hai key, nhưng nếu chỉ cần bật/tắt theo một property thì **ưu tiên `@ConditionalOnProperty`**: mã khai báo rõ hơn, có hỗ trợ condition diagnostics của Boot và ít rủi ro về xử lý giá trị.

### 4.1. Đọc property không tương đương bind cả object

`Environment#getProperty` thích hợp khi cần một vài key. Với cấu hình phức tạp, Spring Boot có `@ConfigurationProperties` và binder; không nên tự viết Condition dùng chuỗi property dài để tái tạo toàn bộ logic binding và validation của production.

Ngoài ra, property **không tự thay đổi kết quả condition trên context đang chạy** khi một biến môi trường được sửa sau startup. Conditions thông thường được đánh giá trong quá trình xây dựng context; muốn dynamic feature flag lúc runtime phải thiết kế cơ chế khác.

## 5. getRegistry(): xem bean definitions, không xem instances

`context.getRegistry()` trả `BeanDefinitionRegistry`, có API như:

```java
boolean declaredHere = context.getRegistry()
        .containsBeanDefinition("featureMarker");
int count = context.getRegistry().getBeanDefinitionCount();
```

Đây là fragment bên trong `matches`. Nó hỏi **định nghĩa bean** đã được đăng ký, không bắt đầu khởi tạo object. Một bean definition có thể chưa có singleton; bean cũng có thể được tạo bằng các cơ chế mà một phép kiểm tra tên definition đơn giản không mô tả đầy đủ.

Một ví dụ:

```java
@Bean
String featureMarker() {
    return "ready";
}
```

Nếu Spring đã xử lý method này và đăng ký bean definition tên `featureMarker`, registry có thể trả `true` ngay cả trước khi `String` instance được tạo.

### 5.1. Không nhầm tên bean với type

`containsBeanDefinition("featureMarker")` là kiểm tra tên definition, không tìm “bất kỳ bean nào có type `FeatureMarker`”.

- Nếu tên bean được đổi thành `anotherMarker` nhưng type giữ nguyên, điều kiện tên có thể thành false.
- Bean của parent context không tự động hiện diện khi kiểm tra một registry local.
- Alias, bean definition từ registrar, scope hoặc cơ chế factory làm ngữ nghĩa kiểm tra tên không luôn tương đương với câu hỏi “bean type nào dùng được”.

Vì vậy, với yêu cầu **“nếu đã có bean type X thì không đăng ký default”**, hãy dùng `@ConditionalOnMissingBean(X.class)` của Boot thay vì tự lặp `containsBeanDefinition` và đoán type.

### 5.2. Tại sao không nên sửa Registry trong Condition?

`BeanDefinitionRegistry` có các method **thay đổi** như `registerBeanDefinition(...)`, nhưng Condition chủ yếu nên là phép kiểm tra read-only.

**Không** dùng `Condition.matches` để bí mật đăng ký/xóa bean definitions, tạo side effect hoặc phụ thuộc thứ tự invocation. Muốn đăng ký bean theo chương trình, Spring có `ImportBeanDefinitionRegistrar`, bean definition registry post-processor hoặc cách cấu hình được thiết kế riêng. Condition chỉ trả quyết định match.

## 6. getBeanFactory(): biết metadata và giới hạn của nó

`context.getBeanFactory()` trả `ConfigurableListableBeanFactory` nếu registry hiện tại có thể cung cấp đối tượng này; contract có thể trả `null`. Vì vậy:

```java
org.springframework.beans.factory.config.ConfigurableListableBeanFactory factory =
        context.getBeanFactory();

if (factory == null) {
    // Không có BeanFactory: không được dereference.
    return false;
}

boolean defined = factory.containsBeanDefinition("featureMarker");
```

Đây là **fragment nằm trong `matches`**, không phải file độc lập.

Một `BeanFactory` có thể cung cấp thông tin như tên bean, definition metadata, scope, aliases, type đã biết hoặc bean đã được quản lý. Tuy nhiên, hãy phân biệt kỹ:

| Bạn hỏi | Có thể biết từ đâu | Có chắc đã có instance? |
| --- | --- | --- |
| Tên definition `featureMarker` đã được đăng ký? | Registry / Factory definition metadata | Không |
| Bean definition có `lazyInit` hoặc scope gì? | Definition metadata | Không |
| Type của bean theo factory hiện tại? | Type lookup | Chưa chắc; FactoryBean và type prediction có phức tạp riêng |
| `getBean("featureMarker")` trả gì? | BeanFactory | Có thể kích hoạt tạo bean; **không làm vậy trong Condition** |

**Tránh gọi `getBean()` trong `Condition.matches`** để “xem có bean không”. Nó có thể khiến bean tạo quá sớm, kéo theo dependency, network hoặc side effect và gây vòng phụ thuộc. Thậm chí một số cách lookup type có thể khiến `FactoryBean` bị eager-initialize; chọn API và flags phù hợp nếu buộc phải làm kiểm tra phức tạp.

Để hỏi điều kiện bean theo type/name, ưu tiên `@ConditionalOnBean`, `@ConditionalOnSingleCandidate` hoặc `@ConditionalOnMissingBean` của Boot. Chúng được viết cho quy trình auto-configuration và có chẩn đoán tốt hơn phép lookup thủ công.

### 6.1. Registry và BeanFactory có thể trùng nội bộ nhưng không nên đánh đồng

Trong một số ApplicationContext thường gặp, bean factory vừa giữ bean definitions vừa thực thi contract registry. Vì vậy hai cách `containsBeanDefinition("x")` có thể trả cùng kết quả. Nhưng **interface và mục đích khác nhau**:

- `BeanDefinitionRegistry` tập trung vào lưu trữ definitions;
- `ConfigurableListableBeanFactory` hỗ trợ quản lý/tra cứu metadata và đối tượng bean;
- `ConditionContext` để lộ cả hai vì điều kiện có thể được đánh giá ở các môi trường hay pha khác nhau.

Không mặc định factory luôn khác registry; cũng không mặc định nó luôn khả dụng.

## 7. getClassLoader(): điều kiện về sự hiện diện class

`context.getClassLoader()` trả loader mà Spring dùng trong context của condition, có thể null. Một ứng dụng có SDK ở compile classpath nhưng không có trong runtime classpath có thể không nạp được class SDK qua loader hiện tại.

Nếu cần kiểm tra theo **tên class**, Spring có helper:

```java
boolean found = org.springframework.util.ClassUtils.isPresent(
        "java.time.Instant",
        context.getClassLoader());
```

Đây là fragment bên trong `matches`. `ClassUtils.isPresent` là cách kiểm tra sự hiện diện tương đối an toàn, có xử lý những tình huống class không thể nạp/link; helper sẽ dùng cơ chế loader thích hợp khi tham số loader là null. Không nên gọi constructor SDK chỉ để kiểm tra có class.

Những giới hạn cần nhớ:

1. “Class hiện diện” có nghĩa loader có khả năng tìm/liên kết class; **không** bảo đảm API method đúng phiên bản.
2. Một JAR nằm trên ổ đĩa không có nghĩa ClassLoader đang dùng nhìn thấy nó.
3. Test classpath có thể khác runtime production; `FilteredClassLoader` có thể mô phỏng một class bị ẩn khỏi context trong test.
4. Cùng binary name do các custom loader khác nhau định nghĩa có thể là **hai JVM types khác nhau**.
5. Điều kiện classpath trên auto-configuration thông thường nên dùng **`@ConditionalOnClass`** hoặc `@ConditionalOnMissingClass`, vì Spring Boot có tối ưu metadata và xử lý an toàn hơn việc tự viết lại điều kiện.

### 7.1. Vì sao không tham chiếu OptionalClient.class trong class được nạp sớm?

Ví dụ SDK vendor không có tại runtime:

```java
// Fragment có nguy cơ: tránh tham chiếu SDK optional ở vị trí không được guard.
@Bean
com.vendor.sdk.OptionalClient optionalClient() {
    return new com.vendor.sdk.OptionalClient();
}
```

Nếu optional type xuất hiện trong chữ ký `@Bean` của configuration luôn bị phân tích, Spring/JVM có thể phải phân giải type trước khi condition trên method kịp bảo vệ. Mẫu Spring Boot nên dùng một configuration class riêng hoặc nested static configuration có `@ConditionalOnClass(name = "...")` ở **class level**.

Điều kiện không biến một type “không tồn tại” thành type có thể biên dịch. Muốn code Java compile, module cung cấp adapter vẫn phải có SDK tại compile time (thường là optional/compile-only khi phát hành), còn consumer runtime có thể không truyền dependency đó.

## 8. getResourceLoader(): tài nguyên trong classpath và bên ngoài

Mặc dù đề bài nhấn mạnh bốn thành phần đầu, `ConditionContext` còn có `getResourceLoader()`. Ví dụ:

```java
org.springframework.core.io.Resource resource =
        context.getResourceLoader()
                .getResource("classpath:demo/feature.properties");

boolean exists = resource.exists();
```

Đây là fragment trong `matches`. `ResourceLoader` cho phép định vị tài nguyên theo location abstraction của Spring, chẳng hạn `classpath:...`. `exists()` chỉ kiểm tra có thể truy cập tài nguyên theo contract; không chứng minh nội dung đúng định dạng, quyền đầy đủ cho mọi thao tác, hoặc tài nguyên mạng luôn ổn định.

Nếu chỉ cần kiểm tra có resource, Spring Boot đã có `@ConditionalOnResource`. Với remote URL, **không** nên thực hiện network probe trong `Condition.matches` vì làm startup chậm và khó dự đoán. Tách bước kiểm tra khả năng kết nối sang health check/lifecycle phù hợp.

## 9. Thời điểm đánh giá: đọc context ở pha nào?

Đây là phần rất quan trọng để tránh sai kết quả dù code Condition không lỗi cú pháp.

Spring Framework xử lý configuration trong nhiều bước. Hai pha được biểu diễn bởi `ConfigurationCondition.ConfigurationPhase`:

- `PARSE_CONFIGURATION`: quyết định có phân tích một `@Configuration` class hay không.
- `REGISTER_BEAN`: quyết định có đăng ký bean definition tương ứng hay không.

Một `Condition` thông thường có thể được Spring đánh giá ở những điểm xử lý phù hợp; một `ConfigurationCondition` có thể tuyên bố rõ pha mà nó muốn chạy. Các built-in conditions của Boot được thiết kế để hoạt động đúng theo cơ chế này.

### 9.1. Vì sao registry có thể “thiếu” bean một cách hợp lệ?

Giả sử bean A khai báo trong cấu hình ứng dụng, bean B do auto-configuration dự kiến tạo. Nếu một condition kiểm tra registry **trước** khi Spring đã đăng ký definition của A, nó thấy `false` dù A có trong source code. Sau khi parser/reader xử lý thêm configurations, registry có thể đã có A.

Không dùng `ConditionContext.getRegistry().getBeanDefinitionCount()` làm chỉ số cuối cùng về số bean của cả ứng dụng ở thời điểm startup hoàn tất.

### 9.2. Method-level condition giúp kiểm tra bean đã khai báo

Nếu điều kiện phụ thuộc vào bean definition do ứng dụng cung cấp, đặt condition ở pha **đăng ký bean** thường phù hợp hơn điều kiện ở class-level parse. Trong demo ở mục sau, custom `Condition` được gắn **trên phương thức `@Bean` thuộc auto-configuration** để xem marker do ứng dụng tự khai báo. Đây là cách trình bày có chủ đích về thời điểm. Với ứng dụng production, dùng `@ConditionalOnBean`/`@ConditionalOnMissingBean` thay vì tự viết lookup nếu logic có thể diễn đạt bằng annotations có sẵn.

### 9.3. Khi nào dùng ConfigurationCondition?

Ví dụ **khai báo pha**:

```java
public final class RegistrationOnlyCondition
        implements org.springframework.context.annotation.ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            org.springframework.context.annotation.ConditionContext context,
            org.springframework.core.type.AnnotatedTypeMetadata metadata) {
        return context.getRegistry()
                .containsBeanDefinition("someMarker");
    }
}
```

Đây là **mã lớp Java minh họa cần package/import phù hợp**; tên marker giả định. `ConfigurationCondition` kế thừa `Condition` và thêm `getConfigurationPhase()`. Đừng áp dụng cấu hình này cho mọi trường hợp: nếu condition quyết định ngay việc parse một class chứa optional types, trì hoãn không đúng chỗ có thể gây vấn đề khác. Chọn phase theo câu hỏi mà condition thật sự cần trả lời.

## 10. Demo hoàn chỉnh: dùng ConditionContext trong một tính năng

Bài demo dùng **Java 17, Maven và Spring Boot 3.3.13**. Nó minh họa một `FeatureService` được tạo mặc định nếu:
- Property `demo.feature.enabled` bật (mặc định bật);
- Class nêu trong `demo.feature.required-class` có mặt (mặc định dùng class JDK `java.time.Instant`);
- Nếu `demo.feature.require-marker=true`, ứng dụng đã đăng ký bean definition tên `featureMarker`.

Nhờ đó, một Condition ngắn sử dụng **Environment, ClassLoader, Registry và BeanFactory**. Test sẽ kiểm tra cả trường hợp có và không có marker. Mục đích là hiểu các getter; khi thiết kế production, có thể phân rã những điều kiện này thành built-in annotations rõ nghĩa.

### 10.1. Cấu trúc thư mục

```text
condition-context-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── feature/
    │   │       ├── FeatureService.java
    │   │       └── autoconfigure/
    │   │           ├── FeatureGateCondition.java
    │   │           └── FeatureAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/feature/autoconfigure/
            └── FeatureAutoConfigurationTest.java
```

`com.example.app` không bao phủ `com.example.feature.autoconfigure` trong component scan mặc định; auto-configuration được khám phá qua resource imports, không phải được component scan tình cờ nhận.

### 10.2. Maven POM

Tạo `pom.xml`:

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
    <artifactId>condition-context-demo</artifactId>
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

Parent quản lý các version Spring phù hợp với Boot 3.3.13. Demo không cần database hay web server.

### 10.3. API tối giản không phụ thuộc Spring

Tạo `src/main/java/com/example/feature/FeatureService.java`:

```java
package com.example.feature;

@FunctionalInterface
public interface FeatureService {
    String process(String input);
}
```

Service chỉ dùng một method để việc quan sát kết quả Condition rõ ràng.

### 10.4. Custom Condition sử dụng bốn getter

Tạo `src/main/java/com/example/feature/autoconfigure/FeatureGateCondition.java`:

```java
package com.example.feature.autoconfigure;

import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;

public final class FeatureGateCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        boolean enabled = context.getEnvironment().getProperty(
                "demo.feature.enabled", Boolean.class, true);
        if (!enabled) {
            return false;
        }

        String requiredClass = context.getEnvironment().getProperty(
                "demo.feature.required-class", "java.time.Instant");
        if (!ClassUtils.isPresent(
                requiredClass, context.getClassLoader())) {
            return false;
        }

        boolean requireMarker = context.getEnvironment().getProperty(
                "demo.feature.require-marker", Boolean.class, false);
        if (!requireMarker) {
            return true;
        }

        boolean declaredInRegistry = context.getRegistry()
                .containsBeanDefinition("featureMarker");

        ConfigurableListableBeanFactory factory =
                context.getBeanFactory();

        boolean declaredInFactory = factory == null
                || factory.containsBeanDefinition("featureMarker");

        return declaredInRegistry && declaredInFactory;
    }
}
```

Đọc theo thứ tự:

1. **Environment:** property `demo.feature.enabled` không tồn tại thì mặc định `true`; `false` làm condition không match.
2. **Environment + ClassLoader:** đọc tên class cần có, rồi `ClassUtils.isPresent` kiểm tra bằng loader từ context; mặc định `java.time.Instant` là type JDK có trong Java 17.
3. **Environment:** nếu không bắt buộc marker thì trả `true`, không cần đọc registry/factory.
4. **Registry:** nếu marker được yêu cầu, kiểm tra bean definition tên `featureMarker` đã được đăng ký.
5. **BeanFactory:** nếu factory tồn tại, kiểm tra thêm chính bean definition đó; nếu factory null, không dereference và chỉ dùng kết quả registry.
6. **Return:** không tạo bất kỳ bean nào, không gọi `getBean()`, không ghi registry, chỉ trả một quyết định.

Hai lần kiểm tra registry/factory trong demo hơi dư thừa có chủ đích để minh họa **cả hai** getter. Trong thư viện thật, nên dùng một built-in bean condition phù hợp thay vì lặp lookup tên. Ngoài ra, `AnnotatedTypeMetadata` chưa cần dùng ở logic này; tham số vẫn bắt buộc theo interface. Bạn có thể dùng metadata để đọc attributes của annotation tùy biến, nhưng không nên khởi tạo class đang được mô tả chỉ để xem annotation.

**Lưu ý về thời điểm:** condition này sẽ được gắn trên `@Bean` method của auto-configuration ở phần tiếp theo. Các marker definitions trong user configuration đã được xử lý theo thứ tự cấu hình thường của ứng dụng trước auto-configuration. Không nên chuyển logic registry này lên class-level parse rồi mặc định có cùng kết quả.

### 10.5. Auto-configuration đăng ký FeatureService

Tạo `src/main/java/com/example/feature/autoconfigure/FeatureAutoConfiguration.java`:

```java
package com.example.feature.autoconfigure;

import com.example.feature.FeatureService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    @Conditional(FeatureGateCondition.class)
    @ConditionalOnMissingBean(FeatureService.class)
    FeatureService featureService() {
        return input -> "feature:" + input;
    }
}
```

Phân biệt:
- `FeatureGateCondition` là điều kiện tùy biến; nó kiểm tra property, sự hiện diện class và marker nếu được yêu cầu.
- `@ConditionalOnMissingBean(FeatureService.class)` là điều kiện **back-off** của Boot: khi app đã cung cấp một `FeatureService`, auto-configuration không tạo mặc định.
- Cả hai cùng phải match thì `FeatureService` mặc định mới được đăng ký.

Spring Boot vốn có `@ConditionalOnProperty` và `@ConditionalOnClass` cho phần lớn logic đầu tiên; demo gộp vào một Condition **để học API**, không khuyến nghị mọi starter đều viết Condition thủ công.

### 10.6. Đăng ký candidate auto-configuration

Tạo resource chính xác:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.feature.autoconfigure.FeatureAutoConfiguration
```

Đây là cách Spring Boot 3.x khám phá auto-configuration trên classpath. Nếu thiếu file này, class Java có thể compile nhưng ứng dụng không tự nhận default bean qua cơ chế imports.

### 10.7. ApplicationRunner cho phép quan sát feature có hay không

Tạo `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.feature.FeatureService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printFeature(
            ObjectProvider<FeatureService> services) {
        return args -> {
            FeatureService service = services.getIfAvailable();
            System.out.println(service == null
                    ? "FEATURE=ABSENT"
                    : "FEATURE=" + service.process("hello"));
        };
    }
}
```

`ObjectProvider<FeatureService>` cho phép runner chạy được cả khi không có bean; đó là cách quan sát một feature optional mà không làm startup thất bại do injection bắt buộc.

Chạy:

```bash
mvn test
mvn spring-boot:run
```

Với property mặc định, runner in **một dòng**:

```text
FEATURE=feature:hello
```

Đây là dòng do `ApplicationRunner` in, **không phải toàn bộ stdout** vì Maven và Spring Boot còn có startup logs.

### 10.8. Tắt bằng property

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.feature.enabled=false
```

Dòng do runner in:

```text
FEATURE=ABSENT
```

`Environment` cung cấp property false, custom Condition trả false, nên Spring không đăng ký default `FeatureService`.

### 10.9. Yêu cầu class không có trong runtime

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.feature.required-class=com.example.missing.OptionalSdk
```

Vì tên class giả định này không tồn tại trong project, `ClassUtils.isPresent(...)` trả false và runner in:

```text
FEATURE=ABSENT
```

Đây là hành vi **phát hiện class không có**, không phải thử kết nối một SDK thật. Nếu cần tích hợp SDK ngoài, hãy đặt class condition ở configuration có phạm vi bảo vệ đúng và tránh sử dụng optional type sớm trong method signatures.

### 10.10. Yêu cầu marker và bổ sung bean definition

Chạy:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.feature.require-marker=true
```

Không có bean definition tên `featureMarker`, condition không match; runner in:

```text
FEATURE=ABSENT
```

Để thêm marker, **bổ sung method sau vào bên trong `DemoApplication`**:

```java
@Bean
String featureMarker() {
    return "ready";
}
```

Đây chỉ là **fragment bổ sung**, không phải file Java độc lập. Chạy lại cùng property yêu cầu marker:

```text
FEATURE=feature:hello
```

Khi Spring xử lý auto-configuration bean method, registry và factory có thể thấy definition của marker do user configuration đã đăng ký. Không cần gọi `getBean("featureMarker")` để kiểm tra marker có tồn tại.

### 10.11. Thử consumer override

Thay vì marker, bạn cũng có thể thêm trong `DemoApplication`:

```java
@Bean
FeatureService customFeatureService() {
    return input -> "app:" + input;
}
```

Đây là fragment bổ sung riêng, không thêm đồng thời với thí nghiệm marker nếu không muốn thay đổi nhiều điều kiện. Khi chạy với properties mặc định, runner in:

```text
FEATURE=app:hello
```

Lý do: `@ConditionalOnMissingBean` của auto-configuration back off vì ứng dụng đã cung cấp bean. Điều này khác với việc custom `FeatureGateCondition` trả false do property/classpath/marker.

## 11. Test các nhánh Condition bằng ApplicationContextRunner

Tạo `src/test/java/com/example/feature/autoconfigure/FeatureAutoConfigurationTest.java`:

```java
package com.example.feature.autoconfigure;

import com.example.feature.FeatureService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FeatureAutoConfiguration.class));

    @Test
    void defaultPropertiesCreateFeature() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context.getBean(FeatureService.class)
                    .process("hello")).isEqualTo("feature:hello");
        });
    }

    @Test
    void disabledPropertySkipsFeature() {
        runner.withPropertyValues("demo.feature.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }

    @Test
    void missingRequiredClassSkipsFeature() {
        runner.withPropertyValues(
                "demo.feature.required-class=com.example.missing.OptionalSdk")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }

    @Test
    void requiredMarkerButAbsentSkipsFeature() {
        runner.withPropertyValues("demo.feature.require-marker=true")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(FeatureService.class));
    }

    @Test
    void registeredMarkerAllowsFeature() {
        runner.withUserConfiguration(MarkerConfiguration.class)
                .withPropertyValues("demo.feature.require-marker=true")
                .run(context -> {
                    assertThat(context).hasBean("featureMarker");
                    assertThat(context).hasSingleBean(FeatureService.class);
                });
    }

    @Test
    void consumerFeatureBeanOverridesDefault() {
        runner.withUserConfiguration(UserFeatureConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class)
                            .process("hello")).isEqualTo("app:hello");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class MarkerConfiguration {

        @Bean
        String featureMarker() {
            return "ready";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        FeatureService customFeatureService() {
            return input -> "app:" + input;
        }
    }
}
```

Chạy:

```bash
mvn test
```

Bộ test kiểm tra sáu tình huống:

| Test | Câu hỏi | Kỳ vọng |
| --- | --- | --- |
| `defaultPropertiesCreateFeature` | Không override property/bean | Một `FeatureService` mặc định |
| `disabledPropertySkipsFeature` | Environment tắt flag | Không có default feature |
| `missingRequiredClassSkipsFeature` | ClassLoader không tìm thấy tên class | Không có default feature |
| `requiredMarkerButAbsentSkipsFeature` | Registry chưa có tên marker | Không có default feature |
| `registeredMarkerAllowsFeature` | User config đã đăng ký marker definition | Feature được tạo |
| `consumerFeatureBeanOverridesDefault` | App có bean `FeatureService` | Chỉ dùng bean của app |

**Giới hạn:** `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` cấp trực tiếp auto-configuration class; test này tốt cho condition nhưng **không chứng minh** file `AutoConfiguration.imports` của JAR được khám phá đúng. Hãy chạy `DemoApplication` hoặc integration test consumer và kiểm tra resource đóng gói để xác minh đầy đủ.

Bộ test cũng **không trực tiếp chứng minh mọi thời điểm của các pha parse/register trên mọi loại ApplicationContext**; nó kiểm tra đúng contract của demo với `ApplicationContextRunner`. Với custom condition phụ thuộc vào registry trong hệ thống phức tạp, cần thêm integration test phù hợp môi trường triển khai.

### 11.1. Kiểm tra artifact và imports resource

```bash
mvn package
jar tf target/condition-context-demo-0.0.1-SNAPSHOT.jar
```

Trong Spring Boot executable JAR, resource imports được đóng dưới:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Với JAR thư viện thường, resource nằm ở `META-INF/spring/...` từ root. Class không được đăng ký qua imports thì app tiêu thụ có thể không thấy feature dù điều kiện của nó đúng.

## 12. Khi nào dùng annotation built-in thay vì Condition riêng?

Hầu hết các nhu cầu trong demo có thể viết thành nhiều condition khai báo:

```java
@AutoConfiguration
public class BuiltInConditionsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.feature", name = "enabled",
            havingValue = "true", matchIfMissing = true)
    @ConditionalOnClass(name = "java.time.Instant")
    @ConditionalOnMissingBean(FeatureService.class)
    FeatureService featureService() {
        return input -> "feature:" + input;
    }
}
```

Đây là **mã minh họa cấu hình không độc lập biên dịch**: cần package/import và `FeatureService` từ ví dụ. Nó diễn đạt ba điều kiện thường gặp theo cách Spring Boot hiểu rõ, có report match/negative match dễ đọc.

Phần **marker bắt buộc theo tên bean** có thể được diễn đạt bằng `@ConditionalOnBean(name = "featureMarker")` khi phù hợp với thứ tự bean definition của ứng dụng; không nhất thiết viết mã tra registry/factory riêng.

| Nhu cầu | Lựa chọn mặc định nên ưu tiên |
| --- | --- |
| Bật/tắt bằng property | `@ConditionalOnProperty` |
| Phụ thuộc vào một class có mặt | `@ConditionalOnClass` |
| Phụ thuộc vào một class vắng mặt | `@ConditionalOnMissingClass` |
| Bean type/name hiện diện | `@ConditionalOnBean` |
| Không có bean phù hợp thì tạo default | `@ConditionalOnMissingBean` |
| Chỉ một ứng viên bean cụ thể | `@ConditionalOnSingleCandidate` |
| Resource tồn tại | `@ConditionalOnResource` |
| Context là Servlet/Reactive/web | `@ConditionalOnWebApplication` hoặc điều kiện tương ứng |
| Logic domain đặc thù kết hợp nhiều thông tin không có built-in phù hợp | Cân nhắc custom `Condition` / `SpringBootCondition` |

**Khi nào custom Condition có giá trị thật?** Ví dụ một integration đòi hỏi tổ hợp property/metadata của thư viện riêng, trạng thái registry có ý nghĩa rõ, hoặc annotation tùy biến nhiều attributes; hoặc bạn muốn cung cấp một condition reusable có quy tắc được test đầy đủ.

Nếu viết condition cho thư viện, có thể cân nhắc kế thừa `SpringBootCondition` và trả `ConditionOutcome` với lý do match/không match. Điều này giúp condition evaluation report giải thích quyết định tốt hơn so với một `Condition` tự viết chỉ trả boolean. Đừng tự ghi log lặp nhiều lần hoặc in bí mật từ property sources.

## 13. Các lỗi thường gặp khi dùng ConditionContext

### 13.1. Gọi getBean() trong matches()

```java
// SAI VỀ MỤC ĐÍCH KIỂM TRA:
boolean ok = context.getBeanFactory()
        .getBean("client") != null;
```

Ngoài nguy cơ `getBeanFactory()` null, lệnh này có thể kích hoạt khởi tạo bean khi Spring còn đang xây bean definitions. Hãy đọc metadata cần thiết hoặc dùng `@ConditionalOnBean`.

### 13.2. Lấy registry count rồi cho rằng đó là “tổng số bean của app”

Đếm definition ở pha đánh giá không phải tổng số instance sau khi context refresh; registry còn có thể thay đổi qua các bước tiếp theo. Tránh dùng count như feature gate trong production nếu không có quy tắc rất rõ.

### 13.3. Kiểm tra bean bằng tên khi thực sự cần type

Một bean `auditClient` có thể được đổi tên thành `customAuditClient`. Nếu yêu cầu là “có một implementation `AuditClient`”, dùng built-in condition theo type sẽ bền vững hơn tên cố định.

### 13.4. Đặt condition dựa vào bean definitions quá sớm

Nếu điều kiện cần bean của user application nhưng chạy ở class-level parse, registry có thể chưa có definition đó. Đưa logic vào đúng phase hoặc dùng built-in bean conditions của Boot. Đừng giải quyết bằng cách gọi `getBean()` để ép Spring tạo sớm.

### 13.5. Không xử lý BeanFactory hoặc ClassLoader null

`getBeanFactory()` và `getClassLoader()` không được đảm bảo trả một instance không null trong mọi context. Phải tuân thủ contract; không bỏ kiểm tra chỉ vì test hiện tại luôn có giá trị.

### 13.6. Dùng Class.forName với initialize=true hoặc new SDK để “thử sự hiện diện”

Các hành động này có thể khởi chạy static initialization hoặc phụ thuộc chưa sẵn sàng. Với classpath condition, ưu tiên `@ConditionalOnClass` và metadata scanning của Boot; nếu buộc kiểm tra, dùng `ClassUtils.isPresent` hoặc API class loading có kiểm soát.

### 13.7. Viết Condition có tác dụng phụ

Ghi file, gửi network request, đăng ký bean, sửa environment hay xóa bean definition trong `matches` làm startup khó dự đoán. Condition nên hoạt động như **predicate** dựa trên bối cảnh hiện tại.

### 13.8. Coi Environment là nguồn cấu hình cố định vĩnh viễn

Environment có thể được chuẩn bị qua nhiều property sources và profile. Kết quả điều kiện chủ yếu áp dụng lúc context khởi tạo; thay property sau startup không tự khiến condition được đánh giá lại và thêm/xóa bean đã đăng ký.

### 13.9. Nhầm “class có” với “dịch vụ ngoài sử dụng được”

`ClassUtils.isPresent("com.vendor.Client", loader)` không bảo đảm endpoint reachable, token đúng, hoặc version của SDK tương thích. Điều kiện classpath chỉ trả lời một phần của khả năng bật integration; health check và exception handling là trách nhiệm riêng.

### 13.10. Kiểm tra tên definition nhưng quên parent context

`registry.containsBeanDefinition("x")` kiểm tra registry đó, không mặc định quét toàn bộ hierarchy. Trong cấu trúc parent/child ApplicationContext, điều kiện built-in có các lựa chọn `SearchStrategy` phù hợp hơn việc tự tra bằng tên.

### 13.11. Viết custom Condition cho điều kiện đã có annotation chuẩn

Điều này dễ dẫn đến lỗi xử lý property values, bean definitions và thiếu condition messages. Ưu tiên annotation built-in; custom code chỉ dành cho logic thực sự đặc thù.

## 14. Cách debug khi một Condition không match

Khi auto-configuration không tạo bean như dự kiến, hãy tách hai câu hỏi:

**A. Auto-configuration class có được tìm thấy không?** Kiểm tra đúng JAR, runtime classpath, `AutoConfiguration.imports`, exclusions và import filters.

**B. Sau khi class được xem xét, condition nào không match?** Bật condition evaluation report, kiểm tra property, classpath, bean definitions, phase và bean override.

Trong demo:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Điều kiện do Boot cung cấp thường hiện lý do rõ trong report. Một `Condition` tùy biến chỉ trả boolean có thể cung cấp ít thông tin hơn. Nếu cần báo cáo riêng có cấu trúc, `SpringBootCondition` với `ConditionOutcome` và reason messages là hướng phù hợp.

### 14.1. Ma trận chẩn đoán

| Hiện tượng | Khả năng và nơi kiểm tra |
| --- | --- |
| Property `demo.feature.enabled=false` | Environment gate trả false |
| Required class không tìm thấy | Runtime classpath/ClassLoader; có thể là dependency optional |
| `require-marker=true` mà không có definition | Registry/factory chưa có `featureMarker` hoặc tên khác |
| Consumer đã định nghĩa `FeatureService` | `@ConditionalOnMissingBean` back off, **không phải** custom Condition nhất thiết false |
| Test pass nhưng ứng dụng thật không có bean | Imports resource, packaging, runtime dependency, component scan |
| Condition phụ thuộc bean nhưng mỗi lần khác nhau | Xem phase, registration order, parent/child context |
| Startup lỗi dù condition true | Factory method, dependency injection, type mismatch hoặc side effect khi tạo bean |
| BeanFactory null | Cách ConditionContext được tạo ở môi trường đó; xử lý trường hợp không có factory |

Trong test, có thể dùng `ApplicationContextRunner` để thay property, classloader và user configuration một cách độc lập. Với class vắng mặt, `FilteredClassLoader` trong `spring-boot-test` có thể mô phỏng môi trường thiếu dependency cụ thể nếu cần test một adapter optional.

### 14.2. Không ghi lộ thông tin nhạy cảm

Condition report hoặc log tự tạo có thể vô tình đưa property values ra ngoài, kể cả endpoint hoặc secret. Khi thiết kế reason message, mô tả **điều kiện nào đạt/không đạt** mà không in token/password. Không bật debug logging dài hạn trên production mà không cân nhắc phạm vi truy cập.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `ConditionContext` và `ApplicationContext` có phải cùng interface không?

**Đáp án:** Không. `ConditionContext` cung cấp một số abstraction liên quan đến pha đánh giá condition; không cam kết toàn bộ lifecycle và bean access của ApplicationContext.

**Câu 2.** `getRegistry().containsBeanDefinition("foo")` trả true có đồng nghĩa bean `foo` đã được khởi tạo không?

**Đáp án:** Không. Nó nói về một bean definition đã đăng ký trong registry hiện tại; object có thể chưa tồn tại.

**Câu 3.** Vì sao không nên gọi `getBean()` trong Condition?

**Đáp án:** Có thể kích hoạt khởi tạo sớm, side effects và lỗi dependency/chu kỳ trong khi Spring đang phân tích cấu hình. Hãy dựa trên metadata hoặc condition built-in.

**Câu 4.** Một property không có giá trị trong Environment sẽ luôn là false?

**Đáp án:** Không. Tùy logic của condition và default value. Trong demo `enabled` mặc định `true`; `require-marker` mặc định `false`.

**Câu 5.** Có `SomeClient.class` trên compile classpath đồng nghĩa `ClassLoader` ở production cũng nhìn thấy?

**Đáp án:** Không. Runtime classpath có thể khác, nhất là với dependencies optional, provided, compile-only hoặc custom loaders.

**Câu 6.** `getBeanFactory()` có luôn non-null không?

**Đáp án:** Không theo contract của `ConditionContext`. Code điều kiện cần xử lý trường hợp không có factory.

**Câu 7.** Vì sao condition dựa trên registry có thể cho kết quả khác ở parse phase và register phase?

**Đáp án:** Bean definitions được bổ sung khi Spring phân tích và đăng ký các cấu hình; registry ở hai thời điểm có thể chứa số lượng definition khác nhau.

**Câu 8.** Nếu logic chỉ cần “có bean type X” thì nên viết custom Condition dùng registry không?

**Đáp án:** Thường không. Ưu tiên `@ConditionalOnBean(X.class)` hoặc `@ConditionalOnMissingBean(X.class)` theo đúng ý nghĩa.

**Câu 9.** `@ConditionalOnClass` match có bảo đảm bean từ SDK khởi tạo và kết nối thành công?

**Đáp án:** Không. Nó chỉ xét sự hiện diện của class theo cơ chế Boot; tương thích phiên bản, config và kết nối là các vấn đề khác.

**Câu 10.** Test `ApplicationContextRunner` cấp trực tiếp auto-configuration class có chứng minh resource imports chính xác không?

**Đáp án:** Không. Nó kiểm tra conditions/bean registration của class được cấp; cần integration test consumer hoặc kiểm tra artifact JAR để xác minh discovery.

## 16. Tóm tắt

`ConditionContext` đóng vai trò **ngữ cảnh đọc dữ liệu khi xét một điều kiện**:

```text
Environment   -> property và profile có hiệu lực?
Registry      -> bean definition tên X đã đăng ký tại đây?
BeanFactory   -> metadata bean có sẵn? (có thể null)
ClassLoader   -> class bắt buộc có thể được nhìn thấy?
ResourceLoader-> resource cần thiết có thể được định vị?
                      |
                      v
             Condition.matches(...) -> true / false
                      |
                      v
        Spring tiếp tục hoặc bỏ qua thành phần tương ứng
```

Khi thiết kế auto-configuration:
- **Ưu tiên điều kiện có sẵn của Boot** cho property, class, bean và resource.
- **Đọc metadata, không khởi tạo bean trong `matches`**.
- **Nhận biết phase**: registry/factory có thể chưa biết mọi definition.
- **Giữ condition thuần đọc và không có side effect**.
- **Test cả điều kiện đạt và không đạt**, plus consumer override và metadata đóng gói.

### Tài liệu tham khảo chính thức

- Spring Framework 6.1 API — `ConditionContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html
- Spring Framework 6.1 API — `Condition`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html
- Spring Framework 6.1 API — `ConfigurationCondition`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration (Condition Annotations & Testing): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `ConditionalOnBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 API — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Framework 6.1 API — `BeanDefinitionRegistry`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistry.html
- Spring Framework 6.1 API — `Environment`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/Environment.html
