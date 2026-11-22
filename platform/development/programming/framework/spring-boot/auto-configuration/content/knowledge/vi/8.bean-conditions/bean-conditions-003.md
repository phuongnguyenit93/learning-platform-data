# Tra cứu bean theo kiểu, tên và annotation trong Spring Boot Auto Configuration

## 1. Mục tiêu và bối cảnh

Trong Spring Boot, *bean condition* quyết định có đăng ký một cấu hình hoặc một bean hay không dựa trên **những bean đã được biết đến trong `BeanFactory` tại thời điểm đánh giá điều kiện**. Với bài này, ba cách tra cứu cần phân biệt là:

1. **Theo kiểu (type):** có bean mang kiểu mong muốn hoặc tương thích với kiểu đó?
2. **Theo tên (name):** có bean được đăng ký với tên cụ thể?
3. **Theo annotation trên bean:** có bean thuộc lớp được gắn annotation mong muốn?

Ba cách này phục vụ các ý định khác nhau. Ví dụ, một thư viện chỉ tạo `AuditDecorator` khi ứng dụng có bean `AuditService` (theo kiểu), chỉ tạo bộ tích hợp khi bean `"primaryDataSource"` tồn tại (theo tên), hoặc kích hoạt hỗ trợ riêng khi có bean thuộc lớp gắn `@AuditedComponent` (theo annotation).

**Phân biệt:** “có lớp `AuditService` trên classpath” là câu hỏi của `@ConditionalOnClass`; “đã có bean `AuditService` trong context” mới là câu hỏi của `@ConditionalOnBean`. Một class có mặt trong dependency **không đồng nghĩa** với việc đã có bean được đăng ký.

## 2. Hai annotation chính và cách chọn tiêu chí

- `@ConditionalOnBean`: khớp khi **mọi yêu cầu được khai báo đều được đáp ứng** bởi các bean đã được xét. Các yêu cầu có thể do **nhiều bean khác nhau** đáp ứng.
- `@ConditionalOnMissingBean`: khớp khi **không có bean nào đáp ứng bất kỳ yêu cầu đã khai báo nào**. Thường dùng để cung cấp bean mặc định nhưng nhường quyền cho cấu hình do ứng dụng tự khai báo.

Cả hai có thể đặt trên lớp `@Configuration`/`@AutoConfiguration` hoặc phương thức `@Bean`. Khi đặt trên lớp, toàn bộ cấu hình bên trong chịu điều kiện; khi đặt trên phương thức, chỉ bean của phương thức đó chịu điều kiện.

| Thuộc tính | Cách tra cứu | Ví dụ | Điều cần nhớ |
| --- | --- | --- | --- |
| `value` | Kiểu dưới dạng `Class<?>[]` | `@ConditionalOnBean(PaymentGateway.class)` | Cú pháp viết tắt của `value = PaymentGateway.class`; tra cả bean tương thích kiểu. |
| `type` | Kiểu dưới dạng tên lớp `String[]` | `@ConditionalOnBean(type = "com.acme.PaymentGateway")` | Hữu ích khi muốn khai báo tên lớp dạng chuỗi, đặc biệt cho meta-annotation hoặc tích hợp tùy chọn. |
| `name` | Tên bean `String[]` | `@ConditionalOnBean(name = "billingGateway")` | Tên bean không phải tên kiểu Java; `@Bean("billingGateway")` tạo tên rõ ràng. |
| `annotation` | Annotation cấp lớp trên bean `Class<? extends Annotation>[]` | `@ConditionalOnBean(annotation = FastPath.class)` | Tra cứu bean có annotation liên quan; nên dùng annotation có `@Retention(RUNTIME)` trong ví dụ tự tạo. |

Ví dụ cùng một ứng dụng:

```java
@Bean("billingGateway")
PaymentGateway gateway() {
    return new StripeGateway();
}
```

- `@ConditionalOnBean(PaymentGateway.class)`: xét **kiểu**, khớp với bean `billingGateway` vì kiểu trả về là `PaymentGateway`.
- `@ConditionalOnBean(name = "billingGateway")`: xét **tên**, khớp dù chưa biết class triển khai.
- `@ConditionalOnBean(annotation = SpecialGateway.class)`: xét **annotation trên loại bean tương ứng**; không tự khớp chỉ vì phương thức có tên `billingGateway`.

Đoạn trên là **minh họa ngắn**, giả định `PaymentGateway` và `StripeGateway` đã được định nghĩa; ví dụ chạy độc lập có đầy đủ lớp ở mục 5.

## 3. Điều kiện hiện diện, vắng mặt và kết hợp nhiều tiêu chí

### 3.1. Tra cứu theo kiểu

```java
@ConditionalOnBean(PaymentGateway.class)
@Configuration(proxyBeanMethods = false)
class GatewaySupportConfiguration {
    // Các @Bean chỉ được xét khi đã có PaymentGateway.
}
```

Đây là điều kiện “tồn tại ít nhất một bean thuộc kiểu này”. Không yêu cầu bean có một tên cố định; một implementation của interface cũng có thể đáp ứng điều kiện nếu thông tin kiểu đã đăng ký đủ chính xác.

Dùng điều kiện ngược để cung cấp mặc định:

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultGateway() {
    return new LocalPaymentGateway();
}
```

Ý nghĩa: chỉ đăng ký `defaultGateway` khi chưa tìm thấy bean `PaymentGateway`. Ở đây `PaymentGateway` và `LocalPaymentGateway` là các kiểu giả định phục vụ minh họa; đoạn này nằm trong một lớp cấu hình và không phải file Java độc lập.

### 3.2. Tra cứu theo tên

```java
@Bean("billingGateway")
PaymentGateway billingGateway() {
    return new StripeGateway();
}
```

Khi đó `@ConditionalOnBean(name = "billingGateway")` khớp. Nếu chỉ có bean `"otherGateway"` cùng kiểu `PaymentGateway`, điều kiện tên **không khớp**. Với `@Bean` không chỉ rõ tên, mặc định thường dùng tên phương thức (`billingGateway` trong ví dụ trên); hãy khai báo tên minh bạch khi tên là một phần của hợp đồng tích hợp.

`@ConditionalOnMissingBean(name = "billingGateway")` cho phép tạo bean có tên này nếu tên đó còn thiếu. Nó **không** bảo đảm toàn bộ context thiếu kiểu `PaymentGateway`; có thể đã tồn tại một `PaymentGateway` tên khác.

### 3.3. Tra cứu theo annotation trên bean

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface SpecialGateway {
}

@SpecialGateway
final class FastGateway implements PaymentGateway {
    // Triển khai PaymentGateway ...
}
```

Điều kiện `@ConditionalOnBean(annotation = SpecialGateway.class)` tìm bean có annotation phù hợp trên **lớp bean**. Nó **không phải** điều kiện “annotation này xuất hiện ở một vị trí bất kỳ trong code” và cũng không thay thế cho `@ConditionalOnClass`. Với mẫu này, bean của `FastGateway` cần thực sự được đăng ký trước lúc đánh giá điều kiện.

**Lưu ý quan trọng riêng của Spring Boot 3.3:** trên **phương thức `@Bean`**, nếu chỉ ghi `@ConditionalOnBean(annotation = SpecialGateway.class)` mà không khai báo `value`, `type` hoặc `name`, Spring Boot 3.3 còn mặc định thêm **kiểu trả về của phương thức đó** vào yêu cầu. Vì thế kết quả có thể khác trực giác “chỉ tra annotation”. Tương tự với `@ConditionalOnMissingBean`. Cách minh bạch là đặt điều kiện annotation trên **lớp cấu hình**, hoặc khai báo đầy đủ tiêu chí kiểu thật sự muốn tra. Từ Spring Boot **3.4**, việc khai báo `annotation` đã thay đổi quy tắc suy ra kiểu mặc định; khi nâng phiên bản phải kiểm tra lại điều kiện. Ví dụ độc lập ở mục 5 đặt điều kiện trên lớp để diễn đạt đúng ý.

### 3.4. Phối hợp nhiều tiêu chí: mỗi yêu cầu phải được đáp ứng, không nhất thiết bởi một bean

```java
@ConditionalOnBean(
    value = PaymentGateway.class,
    name = "billingGateway",
    annotation = SpecialGateway.class
)
```

Điều kiện hiện diện trên có nghĩa đồng thời:

1. Tồn tại bean kiểu `PaymentGateway`.
2. Tồn tại bean tên `billingGateway`.
3. Tồn tại bean có annotation `@SpecialGateway`.

**Không bắt buộc là cùng một bean.** Chẳng hạn có bean kiểu `PaymentGateway` được đánh dấu `@SpecialGateway` với tên `fastGateway`, và một bean `String` tên `billingGateway`: cả ba yêu cầu trên đều được đáp ứng! Không dùng tổ hợp này nếu nghiệp vụ yêu cầu “bean tên `billingGateway` phải chính là `PaymentGateway` có `@SpecialGateway`”. Muốn kiểm tra sự liên hệ của **cùng một bean**, cần kiểm tra bằng logic riêng hoặc thiết kế lại cách khai báo/định danh; annotation điều kiện mặc định không biểu diễn mệnh đề quan hệ đó.

Với `@ConditionalOnMissingBean(value = PaymentGateway.class, name = "billingGateway")`, điều kiện chỉ khớp nếu **vừa không có bean kiểu `PaymentGateway`, vừa không có bean tên `billingGateway`**. Nó không có nghĩa “không có một bean duy nhất vừa mang kiểu đó vừa mang tên đó”. Đây là lỗi lập luận rất thường gặp.

## 4. Những tham số và giới hạn ảnh hưởng kết quả

- **Nhiều kiểu/tên/annotation:** `@ConditionalOnBean(value = {A.class, B.class})` đòi hỏi cả A và B đều có bean phù hợp, có thể ở hai bean khác nhau. `@ConditionalOnMissingBean(value = {A.class, B.class})` đòi hỏi cả A và B đều **vắng mặt**.
- **Ngữ cảnh cha–con:** `search = SearchStrategy.ALL` (mặc định) tìm trong hierarchy; `CURRENT` chỉ xét context hiện tại; `ANCESTORS` chỉ xét context cha. Ví dụ: `@ConditionalOnBean(value = PaymentGateway.class, search = SearchStrategy.CURRENT)`.
- **Container mang generic:** `parameterizedContainer` cho phép nhận diện kiểu cần tra bên trong một wrapper generic đã chỉ rõ, ví dụ có thể coi `Registration<PaymentGateway>` là sự hiện diện của `PaymentGateway` nếu khai báo wrapper tương ứng. Không mặc định suy ra mọi wrapper.
- **Loại trừ khi tìm bean thiếu:** `@ConditionalOnMissingBean` hỗ trợ `ignored` và `ignoredType` để bỏ qua một số kiểu bean khi xét vắng mặt. `@ConditionalOnBean` không có hai tham số này.
- **Chỉ cần tồn tại khác với chọn được duy nhất:** `@ConditionalOnBean(PaymentGateway.class)` vẫn có thể khớp khi có nhiều gateway, nhưng autowire một `PaymentGateway` đơn lẻ có thể mơ hồ. Khi mục tiêu là có đúng một ứng viên tiêm được, xem `@ConditionalOnSingleCandidate(PaymentGateway.class)`; nhiều bean vẫn có thể khớp nếu xác định được một ứng viên `@Primary`.
- **Thứ tự đăng ký:** các điều kiện chỉ thấy bean definition đã được xử lý **tính đến thời điểm đánh giá**. Spring Boot khuyến nghị dùng bean conditions trong auto-configuration vì auto-configuration chạy sau bean do ứng dụng khai báo. Nếu điều kiện phụ thuộc bean của auto-configuration khác, đặt thứ tự qua `@AutoConfiguration(after = OtherAutoConfiguration.class)` hoặc `@AutoConfigureAfter`. Không dựa vào thứ tự chữ viết giữa các phương thức `@Bean`.
- **Kiểu trả về `@Bean`:** khai báo kiểu trả về đủ cụ thể để Spring có metadata phát hiện kiểu. Trả về `Object` khi thực tế tạo `PaymentGateway` có thể khiến điều kiện theo kiểu không nhận ra bean tại thời điểm đánh giá.
- **Điều kiện không phải lời hứa về số lượng bean:** `@ConditionalOnBean` chỉ quyết định *đăng ký cấu hình*, không có chức năng chọn bean để inject, và không có nghĩa đối tượng đã được khởi tạo sẵn.

## 5. Ví dụ Java 17+ có thể chạy độc lập

Ví dụ dùng **Spring Boot 3.3.13** và `AnnotationConfigApplicationContext` để cô lập từng kịch bản. Mỗi điều kiện được đặt **trên lớp cấu hình**, nên tra cứu annotation không bị cơ chế tự thêm kiểu trả về của phương thức `@Bean` trong Boot 3.3.

Cấu trúc:

```text
bean-lookup-demo/
├── pom.xml
└── src/main/java/demo/BeanLookupDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-lookup-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
            <version>3.3.13</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/BeanLookupDemo.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanLookupDemo {

    interface Transport { }

    static final class PlainTransport implements Transport { }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Featured { }

    @Featured
    static final class FeaturedTransport implements Transport { }

    record Marker(String rule) { }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(Transport.class)
    static class ByTypeConfiguration {
        @Bean("byType")
        Marker byType() {
            return new Marker("type");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(name = "preferredTransport")
    static class ByNameConfiguration {
        @Bean("byName")
        Marker byName() {
            return new Marker("name");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(annotation = Featured.class)
    static class ByAnnotationConfiguration {
        @Bean("byAnnotation")
        Marker byAnnotation() {
            return new Marker("annotation");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(
        value = Transport.class,
        name = "preferredTransport",
        annotation = Featured.class
    )
    static class AllRequirementsConfiguration {
        @Bean("byAll")
        Marker byAll() {
            return new Marker("all");
        }
    }

    static void scenario(
        String label,
        boolean plainTransport,
        boolean featuredTransport,
        boolean unrelatedNamedBean
    ) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            // Đăng ký bean nguồn trước khi phân tích các cấu hình có điều kiện.
            if (plainTransport) {
                context.registerBean("plainTransport", PlainTransport.class);
            }
            if (featuredTransport) {
                context.registerBean("featuredTransport", FeaturedTransport.class);
            }
            if (unrelatedNamedBean) {
                context.registerBean(
                    "preferredTransport", String.class, () -> "unrelated"
                );
            }

            context.register(
                ByTypeConfiguration.class,
                ByNameConfiguration.class,
                ByAnnotationConfiguration.class,
                AllRequirementsConfiguration.class
            );
            context.refresh();

            System.out.printf(
                "%s: type=%s, name=%s, annotation=%s, all=%s%n",
                label,
                context.containsBean("byType"),
                context.containsBean("byName"),
                context.containsBean("byAnnotation"),
                context.containsBean("byAll")
            );
        }
    }

    public static void main(String[] args) {
        scenario("none", false, false, false);
        scenario("type-only", true, false, false);
        scenario("name-only", false, false, true);
        scenario("separate-beans", false, true, true);
    }
}
```

Yêu cầu: **JDK 17+**, **Maven 3.8+**, có thể tải dependency Maven. Tại thư mục `bean-lookup-demo`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanLookupDemo
```

Bốn dòng từ `System.out.printf` (bỏ qua mọi thông báo khác nếu môi trường Maven tự in thêm):

```text
none: type=false, name=false, annotation=false, all=false
type-only: type=true, name=false, annotation=false, all=false
name-only: type=false, name=true, annotation=false, all=false
separate-beans: type=true, name=true, annotation=true, all=true
```

Giải thích từng kịch bản:

1. `none`: không khai báo bean nguồn `Transport`, bean tên `preferredTransport` hoặc bean mang `@Featured` → tất cả false.
2. `type-only`: chỉ đăng ký `PlainTransport` → điều kiện theo **kiểu** khớp; theo tên và annotation không khớp.
3. `name-only`: bean `String` có tên `preferredTransport` → chỉ điều kiện theo **tên** khớp. Một bean có tên đúng không có nghĩa là bean đúng kiểu.
4. `separate-beans`: `FeaturedTransport` mang cả kiểu `Transport` và `@Featured` nhưng có tên `featuredTransport`; bean `String` khác mang tên `preferredTransport` → cả ba tiêu chí khớp, và điều kiện phối hợp `byAll` cũng khớp mặc dù **không có một bean duy nhất thỏa tất cả thuộc tính**.

Để chuyển ví dụ thành starter thực tế, dùng `@AutoConfiguration`, khai báo auto-configuration trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và viết kiểm thử bằng `ApplicationContextRunner`. Ví dụ hiện tại dùng context thuần để các kết quả quan sát được rõ ràng và không phụ thuộc scan package.

## 6. Cách đọc và chẩn đoán điều kiện khi xây dựng auto-configuration

1. Ghi rõ câu hỏi nghiệp vụ: “cần bean thuộc kiểu nào”, “cần tên chính xác nào”, hay “cần annotation nào trên lớp bean”. Nếu cần tất cả trên **cùng một bean**, không giả định tổ hợp `value`/`name`/`annotation` tự đảm bảo quan hệ đó.
2. Kiểm tra chỗ khai báo `@Bean` (kiểu trả về, tên được chỉ định), `@Component`/`@Configuration`, annotation runtime trên class và thứ tự auto-configuration.
3. Dùng **condition evaluation report** của Spring Boot: chạy ứng dụng với `--debug` để xem lý do điều kiện matched/unmatched; với Actuator được cấu hình phù hợp, endpoint `/actuator/conditions` cũng cho thông tin condition report.
4. Viết test với `ApplicationContextRunner` cho ít nhất ba trường hợp: không có bean, có bean đúng kiểu nhưng sai tên/annotation, và có bean đầy đủ. Thêm trường hợp hai bean khác nhau đáp ứng nhiều tiêu chí khi dùng điều kiện phối hợp.
5. Khi kiểm thử `@ConditionalOnMissingBean`, xác nhận việc bean tự định nghĩa sẽ chặn mặc định; kiểm tra thêm tên bean vì điều kiện theo tên và theo kiểu có semantics khác nhau.

## 7. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nhầm `@ConditionalOnBean` với `@ConditionalOnClass` | Class có mặt trên classpath chưa chắc là bean | Tra bean definition / kiểu bean, dùng `@ConditionalOnClass` riêng khi muốn xét dependency |
| Tưởng `name` là tên class | Tên bean do `@Bean`/đăng ký bean quyết định | Xem tên đăng ký thực, đặt tên tường minh nếu có hợp đồng |
| Tưởng các tiêu chí phối hợp phải thuộc một bean | Yêu cầu có thể được đáp ứng bởi các bean khác nhau | Kiểm tra quan hệ riêng nếu thật sự cần cùng bean |
| Dùng `annotation` trên method trong Boot 3.3 và quên kiểu trả về mặc định | Method có thể tự thêm điều kiện theo kiểu trả về | Đặt điều kiện trên lớp hoặc khai báo `value`/`type`/`name` có chủ đích |
| Tưởng `@ConditionalOnMissingBean` “thiếu một trong nhiều thứ” | Nó cần **không tiêu chí nào** được thỏa | Phân tích từng yêu cầu vắng mặt, đừng dùng lẫn logic AND/OR |
| Điều kiện false dù bean xuất hiện sau đó | Lúc đánh giá bean definition chưa được xử lý | Đặt trong auto-configuration và khai báo `after` khi phụ thuộc cấu hình khác |
| Inject một bean interface nhưng có nhiều ứng viên | Điều kiện tồn tại không bảo đảm chọn được duy nhất | Dùng qualifier / primary hoặc `@ConditionalOnSingleCandidate` theo mục tiêu |
| Chỉ trả về `Object` trong method `@Bean` | Metadata kiểu của bean có thể quá chung | Khai báo kiểu trả về đủ cụ thể |

## 8. Tự kiểm tra

**Câu 1.** Có bean `"standard"` kiểu `PaymentGateway` và bean `"billingGateway"` kiểu `String`. `@ConditionalOnBean(value = PaymentGateway.class, name = "billingGateway")` có khớp không?  
**Đáp án:** Có; một bean đáp ứng kiểu, bean khác đáp ứng tên. Không suy ra `billingGateway` là `PaymentGateway`.

**Câu 2.** Có bean `PaymentGateway` tên `"customGateway"`, nhưng không có bean tên `"billingGateway"`. `@ConditionalOnMissingBean(name = "billingGateway")` có khớp không?  
**Đáp án:** Có; phép tra theo tên không bị chặn bởi một bean tên khác có cùng kiểu.

**Câu 3.** Trong Spring Boot 3.3, đặt `@ConditionalOnBean(annotation = Featured.class)` ngay trên method `@Bean Marker marker()` có chắc là chỉ tra annotation không?  
**Đáp án:** Không; khi `value`/`type`/`name` chưa được khai báo, Boot 3.3 còn dùng kiểu trả về `Marker` làm điều kiện mặc định. Hãy chọn vị trí annotation và tiêu chí cho đúng ý.

**Ghi nhớ:** type trả lời “bean thuộc kiểu nào?”, name trả lời “bean được gọi là gì?”, annotation trả lời “lớp bean được đánh dấu thế nào?”. Spring Boot đánh giá **những bean đã được đăng ký tại thời điểm đó**, và khi phối hợp nhiều tiêu chí thì mỗi tiêu chí có thể do bean khác nhau đáp ứng.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), mục *Bean Conditions*.
- Spring Boot 3.3 — [`@ConditionalOnBean` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).
- Spring Boot 3.3 — [`@ConditionalOnMissingBean` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).
- Spring Boot 3.3 — [`@ConditionalOnSingleCandidate` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html).
- Spring Boot 3.4 [Release Notes — Bean-based Conditions](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): khác biệt khi khai báo `annotation` trên method `@Bean`.