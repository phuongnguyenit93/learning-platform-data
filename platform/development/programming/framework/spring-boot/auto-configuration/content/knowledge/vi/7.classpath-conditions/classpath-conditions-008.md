# Annotation tổng hợp có điều kiện lớp và trường hợp cần dùng tên lớp

## 1. Vấn đề cần giải quyết

Một thư viện tích hợp với Spring Boot thường có các tính năng tùy chọn. Khi ứng dụng có một SDK trên classpath, auto-configuration được phép đăng ký adapter cho SDK ấy; khi SDK vắng mặt, cấu hình phải bỏ qua nhánh tích hợp hoặc chọn một phương án dự phòng.

Spring Boot có sẵn hai annotation cho phép quyết định dựa trên classpath:

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
@ConditionalOnMissingClass("com.vendor.sdk.Client")
```

Hai dòng trên là **hai ví dụ riêng** về điều kiện có mặt và vắng mặt, không nên gắn đồng thời lên cùng một cấu hình rồi hy vọng chúng cùng khớp.

Để tái sử dụng quy tắc, ta có thể tạo **annotation tổng hợp** (*composed annotation*) như `@WhenJacksonPresent` rồi đặt `@ConditionalOnClass` **lên định nghĩa của annotation ấy**. Chính lúc này xuất hiện một quy tắc an toàn rất quan trọng:

> **Với `@ConditionalOnClass` dùng làm meta-annotation, hãy dùng thuộc tính `name` chứa tên lớp dạng chuỗi, không dùng `value` chứa `SomeClass.class`.**

Spring Boot 3.3.13 nêu rõ: khi class condition được gắn **trực tiếp trên lớp `@Configuration`**, việc đọc metadata bằng ASM cho phép sử dụng class literal dù lớp đó vắng mặt lúc chạy; **bảo đảm ấy không áp dụng tương đương khi annotation được gói qua một tầng meta-annotation**. Vì vậy trường hợp annotation tổng hợp phải dùng chuỗi tên lớp.

Bài học giải thích điểm khác nhau giữa annotation trực tiếp và tổng hợp, cách chọn điều kiện, giới hạn class loading, ví dụ Java 17/Spring Boot chạy ở hai classpath và các lỗi thường gặp.

## 2. Annotation trực tiếp và annotation tổng hợp

### 2.1. Điều kiện đặt trực tiếp trên lớp cấu hình

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
class VendorClientConfiguration {
}
```

Đây là snippet minh họa; cần các import Spring phù hợp. Annotation `@ConditionalOnClass` được gắn **trực tiếp** lên phần tử đang xét. Spring Boot sử dụng `OnClassCondition` để kiểm tra liệu class có tên được chỉ ra có mặt trên classpath hay không.

Với một class type có tại **compile time** nhưng có thể thiếu ở **runtime**, cú pháp sau cũng được Spring Boot hỗ trợ trên một lớp cấu hình được annotate trực tiếp:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(com.vendor.sdk.Client.class)
class VendorClientConfiguration {
}
```

Đây là snippet minh họa, **không compile nếu SDK không được đưa vào compile classpath**. Điểm Spring Boot bảo đảm là kiểm tra annotation trực tiếp bằng metadata ASM có thể tránh phải nạp chính class SDK chỉ để đánh giá điều kiện trên lớp cấu hình. Nó không bảo đảm chương trình Java có thể biên dịch mà không có dependency tương ứng.

### 2.2. Điều kiện được gói thành annotation tái sử dụng

Khi một annotation khác mang `@ConditionalOnClass`:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public @interface RequiresVendorClient {
}
```

thì `@RequiresVendorClient` là **annotation tổng hợp**. Spring có thể tìm được `@ConditionalOnClass` như meta-annotation của nó. Các lớp cấu hình chỉ cần khai báo:

```java
@Configuration(proxyBeanMethods = false)
@RequiresVendorClient
class VendorClientConfiguration {
}
```

Những đoạn trên chỉ minh họa; để compile cần các import `java.lang.annotation.*` và Spring. Ví dụ runnable ở phần sau cung cấp đầy đủ từng tệp.

Phân tầng:

```text
VendorClientConfiguration
    |
    | @RequiresVendorClient                (annotation trực tiếp)
    v
RequiresVendorClient
    |
    | @ConditionalOnClass(name = "...")   (meta-annotation)
    v
OnClassCondition
    |
    v
Kiểm tra classpath -> chọn/bỏ cấu hình
```

Một annotation tổng hợp giúp đặt tên quy tắc theo ngôn ngữ nghiệp vụ: “cần client của hãng X”, “chỉ chạy với driver Y” hoặc “khi module JSON có mặt”, thay vì rải chuỗi class name trên mọi cấu hình.

### 2.3. Ví dụ không an toàn khi là meta-annotation

Không nên thiết kế:

```java
// KHÔNG KHUYẾN NGHỊ cho composed annotation:
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(com.vendor.sdk.Client.class)
public @interface RequiresVendorClient {
}
```

Vấn đề là **đây là `@ConditionalOnClass` nằm trên annotation tổng hợp**, không còn là việc đọc metadata trực tiếp trên lớp cấu hình đích. Theo tài liệu Boot, bảo đảm tránh resolve class literal khi class có thể thiếu không được áp dụng cho trường hợp meta-annotation. Ngoài ra, class literal đòi hỏi dependency ở compile time.

Giải pháp:

```java
// ĐÚNG: biểu diễn class tùy chọn bằng tên đầy đủ.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public @interface RequiresVendorClient {
}
```

Đây không chỉ là vấn đề phong cách cú pháp; nó quyết định một starter có thể hoạt động an toàn khi dependency tùy chọn không được đưa vào runtime hay không.

## 3. Vì sao cần dùng chuỗi tên lớp?

Hai thuộc tính của `@ConditionalOnClass` (Spring Boot 3.3.x) có kiểu khác nhau:

| Thuộc tính | Kiểu dữ liệu | Ví dụ |
| --- | --- | --- |
| `value` | `Class<?>[]` | `@ConditionalOnClass(Foo.class)` |
| `name` | `String[]` | `@ConditionalOnClass(name = "com.example.Foo")` |

`SomeClass.class` là một class literal của Java. Một class phải có tại compile time để source sử dụng type đó một cách trực tiếp. Về runtime, việc đọc, tổng hợp và resolve annotation có thể đụng đến class references. **Nếu type có thể vắng mặt và điều kiện bị gói qua meta-annotation, dùng `name` để Spring kiểm tra theo chuỗi mà không phải resolve class literal ấy trước.**

Không nên rút gọn thành “dùng `value` luôn lỗi”. Khác biệt chính xác là:

- Trên lớp `@Configuration` có `@ConditionalOnClass` **trực tiếp**, Boot có cơ chế đọc bytecode/metadata ASM để đánh giá an toàn, ngay cả khi class được chỉ ra có thể không ở runtime classpath.
- Trên một **annotation tổng hợp**, Boot không cam kết cơ chế an toàn tương đương cho tham chiếu `Class<?>` nằm trong meta-annotation; **chọn `name`**.
- Khi điều kiện đặt trên **phương thức `@Bean`**, chữ ký phương thức có thể buộc JVM xử lý một kiểu vắng mặt **trước** lúc condition trên method được áp dụng. Dùng một lớp cấu hình riêng có class-level condition để cô lập những phương thức này.
- Với tên class viết bằng chuỗi, vẫn phải viết đúng **fully qualified class name**, gồm cả package. Sai chính tả sẽ khiến condition kiểm tra sai class.
- `name` không tự cài dependency. Nó chỉ diễn đạt điều kiện cần được kiểm tra.

Tài liệu Boot 3.3.13 nhấn mạnh cả hai khác biệt: **meta-annotation** và **method-level class loading**. Chúng là hai rủi ro khác nhau và có hai cách xử lý bổ sung cho nhau.

## 4. @ConditionalOnMissingClass khi là meta-annotation

Đôi khi ta cần annotation tổng hợp diễn đạt trường hợp class **không có**:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnMissingClass("com.vendor.sdk.Client")
public @interface WithoutVendorClient {
}
```

`@ConditionalOnMissingClass` trong Spring Boot 3.3.x có **thuộc tính `value` kiểu `String[]`**, không có thuộc tính `name`. Vì thế câu sau là **sai**:

```java
// SAI: ConditionalOnMissingClass không khai báo thuộc tính name.
@ConditionalOnMissingClass(name = "com.vendor.sdk.Client")
```

Đừng áp dụng máy móc câu “mọi điều kiện classpath phải ghi `name`” cho annotation thiếu class. Quy tắc chính xác:

```text
@ConditionalOnClass:
  - value = Class<?>[]; direct class-level có hỗ trợ ASM
  - name  = String[]; NÊN/BẮT BUỘC dùng cho composed meta-annotation

@ConditionalOnMissingClass:
  - value = String[]; đã dùng tên lớp dạng chuỗi
  - không có name
```

Tài liệu khái quát đôi khi nói “dùng tên class khi viết meta-annotation” cho cả hai nhóm. Khi chuyển thành mã Java cụ thể, hãy đọc đúng chữ ký API tương ứng: `@ConditionalOnClass(name = "...")` so với `@ConditionalOnMissingClass("...")`.

### Điều kiện có nhiều lớp

Ví dụ:

```java
@ConditionalOnClass(name = {
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

yêu cầu **tất cả** các class được liệt kê có mặt.

Ngược lại:

```java
@ConditionalOnMissingClass({
    "com.vendor.sdk.Client",
    "com.vendor.sdk.ClientBuilder"
})
```

yêu cầu **tất cả** class được liệt kê vắng mặt. Đây không phải điều kiện “chỉ cần thiếu một class là đủ”. Nếu tính năng chính chỉ hoạt động khi đồng thời có A và B, hai annotation dạng trên không tự bảo đảm nhánh fallback hoạt động ở hai trường hợp có A thiếu B và thiếu A có B. Phải thiết kế ma trận classpath chính xác.

## 5. Spring xử lý annotation tổng hợp như thế nào?

Ở mức cấu hình Spring:

```text
@Configuration hoặc @AutoConfiguration
  -> đọc AnnotationMetadata / AnnotatedTypeMetadata
  -> phát hiện annotation trực tiếp, meta-annotation
  -> đọc thuộc tính và quyết định các @Conditional
  -> đăng ký BeanDefinition khi các điều kiện phù hợp
  -> BeanFactory tạo bean theo scope và dependency
```

Spring Framework có mô hình **`MergedAnnotations`** để xử lý annotation trực tiếp, meta-annotation và những trường hợp alias/hợp thành. Tuy nhiên **đọc được meta-annotation** không có nghĩa **mọi hình thức Class literal đều an toàn** trong classpath thiếu dependency. API đọc metadata của Spring và cơ chế tránh load class tùy chọn cần được sử dụng cùng nhau đúng cách.

Một số API bạn có thể thấy trong framework hoặc custom condition:

```java
AnnotatedTypeMetadata metadata = ...; // ví dụ về biến đã được cung cấp
boolean found = metadata.isAnnotated("com.example.RequiresVendorClient");
Map<String, Object> attributes =
    metadata.getAnnotationAttributes(
        "org.springframework.boot.autoconfigure.condition.ConditionalOnClass");
```

Snippet minh họa này **không biên dịch độc lập** do chưa có nguồn biến `metadata` và import. Nó chỉ cho thấy annotation metadata có thể được truy xuất bằng tên lớp chuỗi. Trong `Condition.matches(...)`, Spring sẽ truyền metadata của class hoặc method đang được xét vào tham số tương ứng.

**`AnnotationMetadata`** mô tả metadata cấp lớp. **`MethodMetadata`** mô tả metadata cấp method. Cả hai mở rộng `AnnotatedTypeMetadata`. Một condition có thể dùng API chung khi kiểm tra thuộc tính annotation, nhưng không được ép mọi metadata thành `AnnotationMetadata`: khi condition đặt trên `@Bean` method, metadata có thể là `MethodMetadata`.

Để kiểm tra property môi trường, bean definitions hoặc classloader, dùng `ConditionContext`, không kỳ vọng metadata annotation tự chứa toàn bộ `application.properties`.

## 6. Phối hợp với @AutoConfiguration và @Import

Annotation tổng hợp thường xuất hiện trong module tự cấu hình do thư viện phát triển. Một auto-configuration hợp lệ trong Spring Boot 3.x được đăng ký trong resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ:

```text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
```

`AutoConfiguration.imports` là danh sách ứng viên; lớp được chọn còn phải thỏa điều kiện. Nó **khác** với `spring-autoconfigure-metadata.properties` dùng để tăng tốc lọc, và khác `spring-configuration-metadata.json` dùng cho IDE/tooling.

Một cấu trúc tổng quát:

```java
@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @RequiresVendorClient
    static class VendorConfiguration {
        // Các @Bean sử dụng SDK khi SDK hiện diện.
    }
}
```

Đây là đoạn minh họa vì cần khai báo `@RequiresVendorClient` và các import. `@RequiresVendorClient` sử dụng `@ConditionalOnClass(name="...")`, nhờ đó cấu hình nhánh SDK được bỏ qua khi class tùy chọn không hiện diện.

**Không đặt `@ComponentScan` để quét toàn bộ thư viện bên trong auto-configuration.** Nếu có nhiều lớp cấu hình phụ trợ, nên dùng `@Import` cụ thể hoặc nested `@Configuration` có điều kiện. Đồng thời đặt lớp `@AutoConfiguration` ở package **ngoài vùng component scanning mặc định** của ứng dụng, để Boot tìm nó qua `.imports` thay vì một đường scan ngoài ý muốn.

**Điều kiện classpath chưa phải chính sách ghi đè bean.** Nếu người dùng có thể cung cấp implementation riêng, hãy cân nhắc `@ConditionalOnMissingBean` trên các bean mặc định. Điều kiện ấy xét **bean definitions** tại thời điểm đánh giá, không xét sự vắng mặt của class.

## 7. Ví dụ chạy được: hai annotation tổng hợp và hai môi trường classpath

Chúng ta tạo một ứng dụng **Java 17 + Spring Boot 3.3.13 + Maven**, có hai annotation tổng hợp:

- `@WhenJacksonPresent`: meta-annotated bằng `@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")`.
- `@WhenJacksonAbsent`: meta-annotated bằng `@ConditionalOnMissingClass("com.fasterxml.jackson.databind.ObjectMapper")`.

Hai lớp cấu hình lồng `static` được đánh dấu bằng hai annotation này và cung cấp **cùng một interface** `ModeService`. Ứng dụng được build hai lần với Maven profile: không có Jackson Databind và có Jackson Databind. Điều này kiểm chứng classpath condition mà không cần dùng Jackson để thực hiện serialization thực sự.

### 7.1. Cây tệp

```text
composed-annotation-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── api/
    │   │   └── ModeService.java
    │   ├── app/
    │   │   └── ComposedAnnotationApplication.java
    │   ├── condition/
    │   │   ├── WhenJacksonPresent.java
    │   │   └── WhenJacksonAbsent.java
    │   └── autoconfigure/
    │       └── ModeAutoConfiguration.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`demo.app` và `demo.autoconfigure` là **package anh em**. Lớp main thuộc `demo.app`, vì vậy component scanning mặc định không nạp `ModeAutoConfiguration` bằng cách quét `demo.autoconfigure`. Boot sẽ nạp nó từ `.imports`. Các custom annotations chỉ được compiler và Spring dùng như metadata, không cần trở thành bean.

### 7.2. pom.xml: dependency mặc định và profile tùy chọn

**`pom.xml`:**

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
    <artifactId>composed-annotation-demo</artifactId>
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

    <profiles>
        <profile>
            <id>with-jackson</id>
            <dependencies>
                <dependency>
                    <groupId>com.fasterxml.jackson.core</groupId>
                    <artifactId>jackson-databind</artifactId>
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

`spring-boot-starter-parent` quản lý version của `jackson-databind`. Không nên gắn một version Jackson tùy tiện khi chỉ cần thử tính hiện diện. Profile `with-jackson` thay **dependency của lần build**, không phải chỉ là một property runtime.

Bản build không profile phải chạy và ghi lại kết quả **trước** khi build bằng profile, bởi `clean package` lần sau sẽ thay thế JAR cùng tên. Không cần hai source code khác nhau.

### 7.3. API ổn định, không phụ thuộc Jackson

**`src/main/java/demo/api/ModeService.java`:**

```java
package demo.api;

@FunctionalInterface
public interface ModeService {
    String mode();
}
```

Các consumer chỉ phụ thuộc vào interface `ModeService`. Chữ ký của nó không yêu cầu `ObjectMapper` hoặc class nào của Jackson; vì vậy nhánh dự phòng có thể compile/chạy khi thư viện Jackson vắng mặt.

### 7.4. Annotation tổng hợp chọn khi Jackson có mặt

**`src/main/java/demo/condition/WhenJacksonPresent.java`:**

```java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
public @interface WhenJacksonPresent {
}
```

Điểm quan trọng nhất nằm trong annotation definition:

```java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
```

`@ConditionalOnClass` là **meta-annotation** của `@WhenJacksonPresent`, nên ta dùng tên class dạng chuỗi. Tệp Java này **không import Jackson** và vẫn compile khi POM không có `jackson-databind`.

Nếu annotation được viết bằng `@ConditionalOnClass(ObjectMapper.class)`, module phải có Jackson compile dependency, và quá trình resolve meta-annotation khi runtime vắng class không có bảo đảm an toàn như cách dùng chuỗi. Vì thế không chọn class literal trong composed annotation của thư viện tùy chọn.

`@Target(ElementType.TYPE)` có chủ đích: annotation được dùng trên **lớp cấu hình**, giúp bảo vệ cả nhóm các `@Bean` trước khi method signatures cần được phân tích.

### 7.5. Annotation tổng hợp chọn khi Jackson vắng mặt

**`src/main/java/demo/condition/WhenJacksonAbsent.java`:**

```java
package demo.condition;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingClass;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnMissingClass(
    "com.fasterxml.jackson.databind.ObjectMapper"
)
public @interface WhenJacksonAbsent {
}
```

Vì `@ConditionalOnMissingClass` chỉ có thuộc tính `value` kiểu `String[]`, truyền trực tiếp chuỗi là cú pháp chuẩn. Không dùng `name = ...`, bởi annotation này không định nghĩa thuộc tính `name`.

`@WhenJacksonAbsent` cũng có `@Target(ElementType.TYPE)` để được dùng trên một nested configuration riêng, thay vì đặt condition trên phương thức có thể chứa chữ ký phụ thuộc SDK tùy chọn.

### 7.6. Auto-configuration sử dụng hai annotation

**`src/main/java/demo/autoconfigure/ModeAutoConfiguration.java`:**

```java
package demo.autoconfigure;

import demo.api.ModeService;
import demo.condition.WhenJacksonAbsent;
import demo.condition.WhenJacksonPresent;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ModeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @WhenJacksonPresent
    static class JacksonConfiguration {

        @Bean
        ModeService selectedMode() {
            return () -> "jackson-supported";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @WhenJacksonAbsent
    static class FallbackConfiguration {

        @Bean
        ModeService selectedMode() {
            return () -> "baseline";
        }
    }
}
```

Ở đây:

1. `@AutoConfiguration` là lớp được Boot lựa chọn từ danh sách ứng viên.
2. `JacksonConfiguration` chỉ được xử lý khi Jackson có mặt; `FallbackConfiguration` chỉ được xử lý khi Jackson vắng mặt.
3. Hai nested configurations đều dùng interface `ModeService` chung, không có method signature liên quan tới `ObjectMapper`.
4. `selectedMode()` có cùng bean name ở hai nhánh, nhưng **chỉ một nhánh được áp dụng** với một class marker đã biết. Vì thế không cần đổi tên bean để né xung đột trong hai môi trường minh họa.
5. `static` nested class tránh cần enclosing instance; `proxyBeanMethods=false` phù hợp vì không có các phương thức `@Bean` gọi lẫn nhau.

Hai nhánh chỉ in nhãn về **khả năng tích hợp**. Việc chọn `jackson-supported` chưa chứng minh ứng dụng đang serialize JSON bằng Jackson hoặc có một bean `ObjectMapper`. Bài học chỉ kiểm chứng **class condition qua composed annotation**.

### 7.7. Đăng ký auto-configuration đúng cơ chế

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
demo.autoconfigure.ModeAutoConfiguration
```

Đường dẫn và fully qualified class name cần đúng hoàn toàn. File này liệt kê **ứng viên auto-configuration**, không chứa tên annotation tổng hợp, tên interface `ModeService` hay tên class `ObjectMapper`.

Không đặt auto-configuration trong phạm vi scanner của lớp `@SpringBootApplication`. Nếu ứng dụng quét hoặc import auto-configuration qua đường ngoài `.imports`, các giả định về selection/order/exclusion có thể khác; thử nghiệm sẽ không còn tách bạch.

### 7.8. Ứng dụng in kết quả

**`src/main/java/demo/app/ComposedAnnotationApplication.java`:**

```java
package demo.app;

import demo.api.ModeService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class ComposedAnnotationApplication {

    private static final String JACKSON_CLASS =
        "com.fasterxml.jackson.databind.ObjectMapper";

    public static void main(String[] args) {
        SpringApplication.run(ComposedAnnotationApplication.class, args);
    }

    @Bean
    ApplicationRunner printMode(ModeService service) {
        return args -> {
            boolean present = ClassUtils.isPresent(
                JACKSON_CLASS,
                ComposedAnnotationApplication.class.getClassLoader()
            );
            System.out.println("JACKSON_ON_CLASSPATH: " + present);
            System.out.println("MODE: " + service.mode());
        };
    }
}
```

Trong ví dụ, `ClassUtils.isPresent(...)` **chỉ giúp hiển thị** việc class có trên classpath hay không. Spring Boot không dùng chính câu lệnh trong `ApplicationRunner` để quyết định auto-configuration; việc chọn nhánh đã diễn ra **trước** khi runner được gọi, qua `OnClassCondition`.

`ModeService` được inject trực tiếp, nên nếu không có nhánh nào đăng ký bean, startup sẽ báo lỗi dependency. Với hai điều kiện đối xứng trên cùng một marker, môi trường chuẩn sẽ có đúng một nhánh được chọn.

## 8. Build và chạy hai trường hợp

### 8.1. Chạy không có Jackson Databind

Trong thư mục chứa `pom.xml`, với Java 17+ và Maven:

```bash
mvn -q -DskipTests clean package
java -jar target/composed-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Bỏ qua Spring Boot banner và log startup, chương trình in:

```text
JACKSON_ON_CLASSPATH: false
MODE: baseline
```

Giải thích:

- `spring-boot-starter` cơ bản không đưa Jackson Databind vào classpath trong project đã cho.
- Điều kiện `@ConditionalOnClass(name = "...ObjectMapper")` bên trong `@WhenJacksonPresent` không khớp.
- `@ConditionalOnMissingClass("...ObjectMapper")` bên trong `@WhenJacksonAbsent` khớp.
- `FallbackConfiguration` đóng góp bean `ModeService` có `mode()` trả `"baseline"`.

Nếu bạn đã thay POM hoặc có một dependency khác đưa Jackson vào project, output có thể khác; kiểm tra dependency tree trước khi kết luận condition sai.

### 8.2. Build lại khi có Jackson Databind

```bash
mvn -q -Pwith-jackson -DskipTests clean package
java -jar target/composed-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Các dòng do chương trình in:

```text
JACKSON_ON_CLASSPATH: true
MODE: jackson-supported
```

Giải thích:

- Maven profile `with-jackson` thêm dependency `jackson-databind`; executable JAR mới sẽ mang các JAR liên quan.
- Điều kiện có mặt khớp nên nested `JacksonConfiguration` được xử lý.
- Điều kiện vắng mặt không khớp nên nested `FallbackConfiguration` không tạo bean.
- Bean `selectedMode` được lấy qua `ApplicationRunner`, làm chương trình in nhãn của nhánh được chọn.

Lưu ý cả hai bản build đều dùng **cùng source annotations**. Chúng khác nhau ở **classpath hiệu lực**, không phải thay đổi `application.properties`.

### 8.3. Bảng kết quả

| Điều kiện runtime | `@WhenJacksonPresent` | `@WhenJacksonAbsent` | Output `MODE` |
| --- | --- | --- | --- |
| Không có `ObjectMapper` | Không khớp | Khớp | `baseline` |
| Có `ObjectMapper` | Khớp | Không khớp | `jackson-supported` |

Đây là ví dụ đơn giản với **một class marker**. Nếu điều kiện tích hợp cần nhiều class cùng lúc, hãy kiểm tra mọi tổ hợp classpath thay vì giả định quy tắc “có/không” luôn chia thành hai nhánh bao phủ nhau.

### 8.4. Kiểm tra JAR và dependency

Nếu output không giống kỳ vọng, xác minh bản build và thư viện bên trong JAR:

```bash
mvn dependency:tree
jar tf target/composed-annotation-demo-0.0.1-SNAPSHOT.jar
```

Với Spring Boot executable JAR, dependency thường nằm dưới `BOOT-INF/lib/`. Có thể tìm `jackson-databind` trong danh sách sau khi build bằng profile.

Chỉ kiểm tra đường dẫn JAR là chưa đủ nếu chương trình được chạy từ classpath tùy chỉnh. Cần đối chiếu **cùng process** và **cùng build artifact** đã được dùng khi quan sát điều kiện.

## 9. Tại sao class-level condition an toàn hơn method-level condition?

Xét một tích hợp SDK tùy chọn:

```java
// MINH HỌA RỦI RO, không phải file độc lập:
@Bean
@ConditionalOnClass(name = "com.vendor.sdk.Client")
com.vendor.sdk.Client vendorClient() {
    return new com.vendor.sdk.Client();
}
```

Phương thức `@Bean` tham chiếu SDK ngay trong **return type**. JVM có thể cần xử lý chữ ký method khi nạp class cấu hình, trước khi Spring kịp áp dụng điều kiện method. Điều này có nguy cơ gây `NoClassDefFoundError` hoặc lỗi liên kết class khi SDK vắng mặt.

Giải pháp được Spring Boot khuyến nghị là **đưa method dùng SDK vào một lớp `@Configuration` riêng**, đặt class-level condition lên lớp đó:

```java
@AutoConfiguration
class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class VendorOnlyConfiguration {

        // Các phương thức @Bean dùng kiểu SDK đặt ở đây.
        // Chỉ phân tích sâu lớp này khi SDK hiện diện.
    }
}
```

Snippet này minh họa tổ chức lớp, chưa phải chương trình runnable. Nếu muốn dùng lại condition, có thể thay annotation trực tiếp bằng `@RequiresVendorClient` **được định nghĩa bằng `name` như mục 2**.

Đồng thời, lớp cấu hình fallback không được đặt kiểu SDK trong chữ ký `@Bean`, field hoặc constructor. Nếu fallback đã phụ thuộc SDK, bản thân nó không còn là phương án chạy khi SDK thiếu.

Đừng suy luận rằng đặt `@ConditionalOnClass(name="...")` trên **mọi** `@Bean` method đều đủ để bảo vệ signature chứa type vắng mặt. Đây chính là lý do cần tách lớp cấu hình theo capability.

## 10. Annotation tổng hợp và các điều kiện phối hợp

Một annotation tổng hợp có thể chỉ mang điều kiện classpath:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public @interface RequiresVendorSdk {
}
```

Hoặc kết hợp thêm một điều kiện property:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
@ConditionalOnProperty(
    prefix = "vendor.sdk",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
public @interface RequiresEnabledVendorSdk {
}
```

Đây là snippet minh họa cần các import. Theo cơ chế `@Conditional`, **các điều kiện áp dụng đều phải thỏa** để lớp cấu hình đủ điều kiện được xử lý.

Bảng ý nghĩa:

| SDK class có mặt? | `vendor.sdk.enabled` | Có thể áp dụng cấu hình? |
| --- | --- | --- |
| Không | `true` | Không: thiếu class |
| Có | `false` | Không: property không thỏa |
| Có | Không đặt | Không: `matchIfMissing=false` |
| Có | `true` | Có thể: hai điều kiện này thỏa |

Từ **“có thể”** quan trọng: các condition khác, exclusions hoặc lỗi đăng ký/khởi tạo bean vẫn có thể khiến tính năng chưa sẵn sàng.

Nên gom các quy tắc thành annotation tổng hợp khi chúng biểu diễn một capability ổn định và được dùng ở nhiều cấu hình. Nếu chỉ có một điều kiện dùng đúng một lần, đặt trực tiếp `@ConditionalOnClass(name=...)` thường đơn giản, dễ chẩn đoán hơn.

### Có thể truyền tên class động vào composed annotation không?

Một annotation cố định như `@RequiresVendorSdk` mã hóa một tên class rõ ràng. Nếu muốn khai báo:

```java
@RequiresLibrary("com.vendor.sdk.Client")
```

thì cần thiết kế một annotation có thuộc tính và cơ chế ánh xạ `@AliasFor` hoặc custom condition phù hợp; **không tự suy ra rằng mọi thuộc tính của annotation tùy chỉnh sẽ tự động chuyển sang `name` của `@ConditionalOnClass`**.

Nên ưu tiên một quy tắc cố định rõ ràng cho một thư viện cụ thể. Khi cần rất nhiều SDK với tên class thay đổi linh hoạt, có thể triển khai `Condition` riêng đọc `AnnotatedTypeMetadata`, hoặc dùng annotation aliasing có kiểm thử. Đó là bài toán mở rộng khác với yêu cầu cốt lõi của composed class condition.

## 11. So sánh với những loại điều kiện khác

Một lỗi thường gặp là dùng classpath condition cho tình huống thiếu **bean**, thiếu **property**, hoặc một tính năng bị lỗi **runtime**.

| Tình huống | Cơ chế phù hợp |
| --- | --- |
| Có/không có class SDK ở runtime | `@ConditionalOnClass(name=...)`, `@ConditionalOnMissingClass("...")` |
| Người dùng đã cung cấp bean cùng type | `@ConditionalOnMissingBean` |
| Chỉ bật feature khi cấu hình bật | `@ConditionalOnProperty` |
| Cấu hình chỉ dùng cho servlet/reactive web | `@ConditionalOnWebApplication` với type phù hợp |
| Bean được tạo nhưng lỗi trong constructor | Xem `BeanCreationException` và nguyên nhân gốc |
| SDK có mặt nhưng service bên ngoài timeout | Timeout/retry/circuit breaker hoặc fallback runtime có kiểm soát |

**Có class** không phải **có bean**. Một JAR có thể nằm trên classpath nhưng không đăng ký bean nào vì điều kiện khác không khớp. Ngược lại, nếu một bean definition đã tồn tại mà instance chưa được khởi tạo vì `@Lazy`, nó không đơn giản được xem là “thiếu” theo ngữ nghĩa `@ConditionalOnMissingBean`.

`@ConditionalOnMissingBean` thường dùng trong auto-configuration để cho phép người dùng thay thế bean mặc định. Nó xét bean definitions **đã được xử lý tại thời điểm điều kiện được đánh giá**, không dựa trên việc mọi singleton đã được tạo. Vì thế cần chú ý thứ tự và tránh đặt tùy tiện trong cấu hình thường của ứng dụng.

## 12. Chẩn đoán khi composed annotation không hoạt động

### 12.1. Bật báo cáo điều kiện

Spring Boot hỗ trợ Conditions Evaluation Report khi bật debug:

```bash
java -jar target/composed-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Tìm `ModeAutoConfiguration`, `JacksonConfiguration`, `FallbackConfiguration` và các kết quả liên quan `OnClassCondition`.

- **Positive matches**: các điều kiện đã được đánh giá và khớp.
- **Negative matches**: các điều kiện đã được đánh giá nhưng không khớp; thường kèm lý do.
- **Exclusions**: auto-configuration bị loại theo cấu hình.

Báo cáo không phải lịch sử đầy đủ mọi thao tác JVM class loading. Nếu một bean có definition nhưng tạo lỗi, hãy đọc stack trace và root cause riêng.

### 12.2. Khi condition không khớp ngoài dự kiến

Kiểm tra theo thứ tự:

1. **Đúng tên đầy đủ chưa?** Ví dụ `com.fasterxml.jackson.databind.ObjectMapper`, không phải `ObjectMapper` hoặc tên module `jackson-databind`.
2. **Đúng annotation definition chưa?** Composed `@ConditionalOnClass` phải dùng `name`, không dùng `ObjectMapper.class`.
3. **Đúng runtime artifact chưa?** Build profile đã đưa dependency vào executable JAR bạn đang chạy chưa?
4. **Đúng package/đường import chưa?** Auto-configuration của thư viện phải có tên trong `.imports`, ngoài component scan.
5. **Đúng vị trí điều kiện chưa?** Condition cấp lớp bảo vệ toàn bộ nested configuration; condition trên method chưa chắc bảo vệ type tùy chọn trong return signature.
6. **Có condition nào khác cùng xuất hiện không?** Điều kiện class khớp không bảo đảm bean definition được đăng ký khi property, bean hay web condition khác không khớp.
7. **Có đang nhầm class presence với bean presence không?** `ObjectMapper` có mặt trên classpath chưa chắc `ObjectMapper` là một Spring bean.
8. **Có thêm dependency qua transitive dependency không?** Class vắng trong danh sách dependency trực tiếp nhưng vẫn có thể được kéo vào qua starter khác.

Có thể kiểm tra Maven dependency tree:

```bash
mvn dependency:tree
```

Nếu dùng nhiều profile, hãy thêm `-Pwith-jackson` ở lệnh xem dependency khi đang điều tra bản có Jackson. Cũng cần kiểm tra classpath runtime chứ không chỉ POM.

### 12.3. Khi gặp NoClassDefFoundError

Đây là lỗi liên quan class loading/linking. Kiểm tra xem code đã tham chiếu class tùy chọn ngay trong chữ ký phương thức `@Bean`, superclass, interface hoặc field/constructor của cấu hình được nạp sớm chưa. Không cố khắc phục chỉ bằng đổi condition trên method nếu JVM vẫn phải resolve type trước khi Spring đánh giá method condition.

Một bố cục an toàn hơn:

```text
core-api/
  CommonService.java                  (không tham chiếu SDK)

auto-configuration/
  IntegrationAutoConfiguration.java
    nested SdkConfiguration           (@ConditionalOnClass(name="..."))
      SDK-specific @Bean methods
    nested FallbackConfiguration      (@ConditionalOnMissingClass("..."))
      core-only @Bean methods
```

Tùy nhu cầu sử dụng thật, các lớp triển khai SDK có thể thuộc module tùy chọn riêng, được đưa vào compile classpath của module đó nhưng không có tại runtime của ứng dụng không dùng SDK.

## 13. Những sai lầm phổ biến

### Sai lầm 1: Dùng Class literal trong composed @ConditionalOnClass

**Sai cho thư viện có SDK tùy chọn:** gói `@ConditionalOnClass(OptionalSdk.class)` trong `@RequiresOptionalSdk`. Dùng `@ConditionalOnClass(name="fully.qualified.OptionalSdk")`.

### Sai lầm 2: Viết @ConditionalOnMissingClass(name = "...")

`@ConditionalOnMissingClass` không có `name`. Thuộc tính của nó là `value` kiểu `String[]`; truyền chuỗi trực tiếp.

### Sai lầm 3: Coi điều kiện cấp @Bean là lá chắn tuyệt đối với SDK thiếu

JVM có thể cần xử lý method signature trước khi condition method được áp dụng. Tách nested `@Configuration` có class-level condition.

### Sai lầm 4: Biến annotation tổng hợp thành giải pháp cho mọi tình huống

Composed annotation hữu ích khi quy tắc ổn định và tái sử dụng. Với một điều kiện đơn lẻ, đặt annotation có sẵn trực tiếp thường minh bạch hơn.

### Sai lầm 5: Dùng @ComponentScan để tìm auto-configuration

Trong Boot 3.x, auto-configuration có đường đăng ký qua `.imports`. Quét package thư viện có thể kéo vào những cấu hình ngoài ý định và ảnh hưởng kiểm soát exclusion.

### Sai lầm 6: Cho rằng @ConditionalOnClass giúp tự động tải SDK

Điều kiện chỉ xem class có mặt hay không. Nó không cài dependency, không tạo bean SDK, không kiểm tra tính khả dụng của một endpoint mạng.

### Sai lầm 7: Dùng hai annotation với nhiều class mà không kiểm tra trường hợp trung gian

Nếu nhánh chính yêu cầu **A và B cùng có**, còn nhánh fallback yêu cầu **A và B cùng thiếu**, hai tình huống có một class và thiếu một class không được bao phủ. Thiết kế bảng quyết định.

### Sai lầm 8: Nhầm CLASS literal tại compile với class có mặt runtime

Một dependency có thể có lúc compile nhưng bị loại khi đóng gói hoặc chạy. Dùng `name` cho meta-annotation của dependency tùy chọn, và kiểm tra process runtime.

### Sai lầm 9: Đọc annotation bằng reflection tùy tiện rồi tự xử lý alias

Spring có `MergedAnnotations`/`AnnotatedTypeMetadata`. Khi annotation hợp thành và meta-annotation có alias, hãy dùng API Spring thay vì giả định `Class#getDeclaredAnnotation` luôn phản ánh kết quả framework nhìn thấy.

### Sai lầm 10: Dùng classpath condition để giải quyết timeout runtime

Nếu SDK class đã có nhưng server ngoài bị lỗi, class condition vẫn khớp. Fallback runtime là một bài toán về độ tin cậy riêng, không phải `@ConditionalOnMissingClass`.

## 14. Checklist áp dụng vào thư viện/starter

Trước khi phát hành một annotation tổng hợp cho classpath condition:

1. **Đặt tên diễn đạt capability**, ví dụ `@WhenJacksonPresent`, thay vì tên không phản ánh quy tắc.
2. **Dùng `@ConditionalOnClass(name="...")`** trong định nghĩa composed annotation.
3. **Dùng `@ConditionalOnMissingClass("...")`** khi cần nhánh vắng class; không dùng thuộc tính `name` không tồn tại.
4. **Chọn `@Target` hợp lý**: ưu tiên TYPE khi cần bảo vệ cả cấu hình chứa method signatures của SDK.
5. **Đặt retention phù hợp**, ví dụ `RUNTIME`, để hệ thống annotation của Spring có thể quan sát.
6. **Tách config SDK và config fallback**, giữ interface chung không phụ thuộc SDK tùy chọn.
7. **Không quét auto-configuration như component**; đăng ký lớp trong `AutoConfiguration.imports`.
8. **Kiểm thử classpath vắng/có** và một vài phiên bản SDK nếu cần.
9. **Bổ sung `@ConditionalOnMissingBean`** khi ứng dụng cần quyền tùy biến bean, không nhầm với class conditions.
10. **Bật debug/report khi điều tra**, so sánh actual classpath và điều kiện.
11. **Tránh tối ưu hóa quá sớm** bằng custom `Condition` khi built-in annotation đã đủ.
12. **Xem xét test tự động** bằng `ApplicationContextRunner` và `FilteredClassLoader` khi phát triển auto-configuration thật.

Những helper như `ApplicationContextRunner` và `FilteredClassLoader` thuộc module kiểm thử của Spring Boot, không cần thêm vào code production ở phần runnable. Mục tiêu là xác minh logic classpath theo từng tổ hợp, tránh chỉ dựa vào một môi trường developer có sẵn nhiều thư viện.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Điểm khác nhau giữa gắn `@ConditionalOnClass` trực tiếp và dùng nó trong composed annotation là gì?

**Đáp án:** Với annotation trực tiếp trên lớp cấu hình, Boot có thể đọc metadata ASM để hỗ trợ an toàn với class literal của dependency có thể thiếu. Khi `@ConditionalOnClass` là meta-annotation của annotation khác, phải dùng tên class dạng chuỗi qua `name`.

**Câu 2.** Cách khai báo đúng trong `@WhenJacksonPresent` là gì?

**Đáp án:** `@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")`.

**Câu 3.** Có thể viết `@ConditionalOnMissingClass(name = "...")` không?

**Đáp án:** Không. `@ConditionalOnMissingClass` dùng `value` là `String[]`. Viết `@ConditionalOnMissingClass("...")`.

**Câu 4.** Vì sao ví dụ chỉ có `spring-boot-starter` in `MODE: baseline`?

**Đáp án:** Runtime classpath của POM mặc định không có Jackson Databind; `ObjectMapper` vắng mặt, nên nhánh `@WhenJacksonAbsent` khớp.

**Câu 5.** Khi bật Maven profile `with-jackson`, output thay đổi mà không sửa source là do đâu?

**Đáp án:** Class `ObjectMapper` xuất hiện trong JAR/runtime classpath; `@WhenJacksonPresent` khớp và `@WhenJacksonAbsent` không khớp.

**Câu 6.** Điều kiện classpath có bảo đảm đã có bean `ObjectMapper` trong container không?

**Đáp án:** Không. Nó chỉ kiểm tra khả năng hiện diện của class. Sự tồn tại của bean phụ thuộc các cấu hình/condition khác.

**Câu 7.** Nếu một `@Bean` method trả về `OptionalSdkType` mà SDK không có runtime, thêm condition trên chính method luôn an toàn chứ?

**Đáp án:** Không. JVM có thể resolve chữ ký method trước lúc Spring kiểm tra condition; nên cô lập cả method trong lớp `@Configuration` được bảo vệ bằng class-level condition.

**Câu 8.** Hai điều kiện với nhiều class có tự động là phần bù nhau không?

**Đáp án:** Không nhất thiết. “Tất cả A, B có” và “tất cả A, B thiếu” bỏ sót hai trường hợp có một/thiếu một.

**Câu 9.** `AutoConfiguration.imports` chứa tên SDK class hay tên lớp auto-configuration?

**Đáp án:** Chứa tên fully qualified của các lớp `@AutoConfiguration`. Tên SDK class được kiểm tra nằm trong annotation điều kiện.

**Câu 10.** Khi nào nên viết custom composed annotation?

**Đáp án:** Khi quy tắc classpath là một capability rõ ràng, tái sử dụng được và mang ý nghĩa miền nghiệp vụ. Với một lần dùng đơn giản, trực tiếp `@ConditionalOnClass(name=...)` có thể dễ đọc hơn.

## 16. Tài liệu tham khảo

- Spring Boot 3.3.13, Creating Your Own Auto-configuration (Class Conditions): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13, `ConditionalOnClass` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3.13, `ConditionalOnMissingClass` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingClass.html
- Spring Framework 6.1, `AnnotatedTypeMetadata` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html
- Spring Framework 6.1, `@Conditional` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html
