# Tạo stereotype ghép bằng meta-annotation và @AliasFor trong Spring Core Container

## Mục tiêu học tập

Trong Spring, một class có `@Component`, `@Service` hoặc `@Repository` có thể được phát hiện qua **component scanning** và đăng ký thành bean. Nhưng trong dự án lớn, ta thường muốn diễn đạt vai trò của class bằng annotation riêng như `@DomainService`, `@PaymentHandler` hoặc `@ApplicationUseCase`. Một annotation riêng chỉ có ích cho container nếu Spring hiểu nó là **stereotype** và đọc đúng metadata liên quan.

Hai cơ chế giúp giải quyết bài toán này là:

1. **Meta-annotation:** đặt một annotation lên định nghĩa của annotation khác. Ví dụ, đặt `@Component` lên `@DomainService` để lớp mang `@DomainService` cũng được coi là ứng viên component scan.
2. **`@AliasFor`:** khai báo một thuộc tính của annotation là alias cho thuộc tính khác, có thể nằm trong **cùng annotation** hoặc ở **meta-annotation**. Ví dụ cho phép `@DomainService(beanName = "invoiceProcessor")` chỉ định tên bean thông qua `@Component.value`.

Sau bài học, bạn sẽ:

- Tạo một custom stereotype được Spring phát hiện mà không cần đặt thêm `@Component` trên từng class.
- Dùng `@Target`, `@Retention` và `@Documented` đúng mục đích.
- Ánh xạ tên bean qua `@AliasFor(annotation = Component.class, attribute = "value")`.
- Phân biệt explicit alias, alias cho thuộc tính meta-annotation, và implicit alias.
- Hiểu yêu cầu về kiểu trả về, giá trị mặc định và phạm vi meta-annotation.
- Biết cách kiểm tra bean name và annotation đã merge bằng Spring API.
- Phát hiện lỗi phổ biến khi annotation xuất hiện trên class nhưng component scan không đăng ký bean.

**Giới hạn phạm vi:** Bài tập trung vào custom stereotype của **Spring Core Container**, không xây cơ chế xử lý annotation hoàn toàn mới hay dùng AOP làm trọng tâm. `@Transactional`, `@Qualifier` và custom filter chỉ được nhắc khi cần phân biệt trách nhiệm.

## 1. St​​ereotype là gì?

Spring gọi những annotation phân loại vai trò của một class thành **stereotype annotations**. `@Component` là stereotype tổng quát. `@Service`, `@Repository` và `@Controller` chuyên biệt hơn, nhưng đều được xây dựa trên cơ chế `@Component`.

Một phiên bản lược giản của `@Service` có dạng:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface Service {
    // Có thể khai báo các thuộc tính riêng.
}
```

Đây là **đoạn mô tả cấu trúc**, không phải mã để định nghĩa lại `org.springframework.stereotype.Service` trong dự án. Spring phát hiện class gắn `@Service` vì trong định nghĩa `@Service` đã có meta-annotation `@Component`.

Mối quan hệ:

```text
@Component
    ↑ meta-annotation
@DomainService
    ↑ annotation áp dụng lên class
InvoiceProcessor
    ↓ component scan
BeanDefinition cho InvoiceProcessor
    ↓
Spring container quản lý bean
```

Việc một class được coi là **ứng viên** không tự bảo đảm ApplicationContext khởi động thành công: class có thể bị loại bởi filter, thiếu dependency, có lỗi khi tạo bean, hoặc nằm ngoài package được scan.

Một custom stereotype hữu ích khi cùng một vai trò xuất hiện lặp lại trong mã:

```java
@DomainService
public class InvoiceProcessor {
    // ...
}
```

Người đọc nhận ra đây là dịch vụ miền nghiệp vụ, trong khi Spring hiểu nó như một component bình thường. Có thể thêm metadata có ý nghĩa khác cho annotation tùy nhu cầu, nhưng cần xác định rõ annotation đó ảnh hưởng **đăng ký bean**, **đặt tên**, **scope** hay **hành vi runtime**.

## 2. Ba khái niệm annotation cần nắm

### 2.1. Annotation thường

Java cho phép đánh dấu class:

```java
@SomeMarker
public class Example {
}
```

Nếu `@SomeMarker` chỉ là annotation tự tạo mà không có meta-annotation `@Component`, Spring mặc định **không** coi class này là component ứng viên chỉ vì có marker. Có thể viết custom include filter để quét annotation bất kỳ, nhưng đó là một cấu hình khác.

### 2.2. Meta-annotation

Một annotation đặt trên **định nghĩa annotation khác** được gọi là meta-annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface DomainService {
}
```

Sau khi custom stereotype có meta-annotation `@Component`, những class đánh dấu `@DomainService` nằm trong vùng component scan mặc định có thể được Spring phát hiện.

Về mặt phân loại, `@Service` cũng là một stereotype meta-annotated bằng `@Component`. Nếu custom annotation được meta-annotate bằng `@Service`, `@Component` xuất hiện **gián tiếp** qua một tầng nữa. Spring có khả năng đọc chuỗi meta-annotation phù hợp, nhưng khi chỉ cần ví dụ đặt tên bean cơ bản, meta-annotate trực tiếp bằng `@Component` giúp cấu trúc dễ kiểm tra hơn.

### 2.3. Composed annotation

Một **composed annotation** (annotation ghép) tích hợp những meta-annotation và có thể **mở lại một số thuộc tính** cho người sử dụng. Chẳng hạn annotation dành cho feature có thể kết hợp ý nghĩa "đây là component" với một quy tắc tên bean, scope hoặc qualifier.

Cơ chế ghép không đồng nghĩa với Java tự sao chép thuộc tính giữa annotations. Spring phải đọc **merged annotation model** để áp dụng override và alias.

Ví dụ:

```java
@DomainService(beanName = "invoiceProcessor")
public class InvoiceProcessor {
}
```

Ở đây `beanName` là thuộc tính tự đặt tên của `@DomainService`. Để Spring dùng nó làm tên bean, cần định nghĩa alias tường minh tới `@Component.value`.

## 3. Định nghĩa custom stereotype chuẩn

Một annotation custom điển hình:

```java
package demo.stereotype;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

Ý nghĩa các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `@Target(ElementType.TYPE)` | Annotation áp dụng cho class/interface hoặc loại declaration thuộc `TYPE`. Trong component scan, đối tượng cần đăng ký là class ứng viên. |
| `@Retention(RetentionPolicy.RUNTIME)` | Annotation còn trong class file và có thể được đọc khi chạy. |
| `@Documented` | Đưa annotation vào tài liệu Javadoc của phần tử được đánh dấu; không làm Spring đăng ký bean. |
| `@Component` | Nói với component scanner rằng annotation này là một stereotype, khi có trong chuỗi meta-annotation. |
| `@AliasFor(...)` | Nói với Spring rằng `DomainService.beanName` ghi đè/ánh xạ sang `Component.value`. |
| `String beanName() default ""` | Người dùng có thể cung cấp tên bean hoặc để trống để dùng cơ chế tạo tên mặc định. |

**Quan trọng:** `@AliasFor` phải nằm **trên phương thức thuộc tính của annotation** (`beanName()`). Không đặt `@AliasFor` trên class thực thi `InvoiceProcessor` hoặc trên field Java thông thường.

`@Target` và `@Retention` đến từ `java.lang.annotation`; `@Component` đến từ `org.springframework.stereotype`; `@AliasFor` đến từ `org.springframework.core.annotation`. Lẫn package import sẽ khiến ví dụ không biên dịch hoặc hoạt động không đúng mục tiêu.

## 4. Vì sao cần @AliasFor để đặt tên bean?

`@Component` định nghĩa thuộc tính `String value() default ""`. Khi gọi:

```java
@Component("invoiceProcessor")
public class InvoiceProcessor {
}
```

Spring có thể dùng `invoiceProcessor` làm tên bean.

Giả sử bạn tạo:

```java
@Component
public @interface DomainService {
    String beanName() default "";
}
```

rồi viết:

```java
@DomainService(beanName = "invoiceProcessor")
public class InvoiceProcessor {
}
```

**Nếu không có `@AliasFor`**, không thể giả định Spring tự hiểu thuộc tính tùy ý tên `beanName` là `Component.value`. Vì vậy, dù class có thể vẫn được quét nhờ `@Component`, tên bean tùy chỉnh có thể **không được áp dụng**.

Thêm:

```java
@AliasFor(annotation = Component.class, attribute = "value")
String beanName() default "";
```

để khai báo rõ quan hệ "`DomainService.beanName` là bản ghi đè cho `Component.value`". Từ Spring Framework 6.1, cơ chế hỗ trợ tên stereotype với thuộc tính không gọi là `value` dựa trên alias tường minh này. Cũng từ 6.1, cách dựa vào quy ước **trùng tên `value` nhưng không có `@AliasFor`** đã bị đánh dấu deprecated; khi tạo annotation mới, nên khai báo alias rõ ràng.

### Khi để trống tên

Nếu dùng:

```java
@DomainService
public class ReportService {
}
```

`beanName()` dùng mặc định `""`. Khi không có tên tường minh khác, `AnnotationBeanNameGenerator` mặc định có thể tạo bean name `reportService` từ tên class `ReportService` theo quy tắc decapitalize của Spring.

Nếu cấu hình scanner dùng `BeanNameGenerator` tùy chỉnh, tên thực tế có thể khác. Đừng xây logic quan trọng dựa trên một tên bean mặc định khi ứng dụng có thể đổi chiến lược đặt tên.

## 5. Ví dụ runnable Java 17 và Spring Framework 6.2

Ví dụ bên dưới có hai class được đánh dấu cùng một custom stereotype:

- `InvoiceProcessor` dùng tên bean tường minh `invoiceProcessor` thông qua `beanName`.
- `ReportService` không chỉ định tên, dùng bean name mặc định `reportService`.

Spring dùng `@ComponentScan` để tìm hai class trong package `demo.app`. Chúng ta sẽ kiểm tra bean có thể được lấy theo tên và theo kiểu.

### 5.1. Cấu trúc thư mục

```text
composed-stereotype-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        ├── Main.java
        ├── config/
        │   └── AppConfig.java
        ├── stereotype/
        │   └── DomainService.java
        └── app/
            ├── billing/
            │   └── InvoiceProcessor.java
            └── report/
                └── ReportService.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>composed-stereotype-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Tạo annotation @DomainService

Tệp `src/main/java/demo/stereotype/DomainService.java`:

```java
package demo.stereotype;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

Annotation này không có code khởi tạo bean theo cách thủ công. Khi component scanner gặp class mang `@DomainService` ở package được quét, Spring nhận ra `@Component` là meta-annotation và đăng ký class đó như ứng viên component. Alias ảnh hưởng đến **metadata tên bean**.

### 5.4. Service có tên bean tường minh

Tệp `src/main/java/demo/app/billing/InvoiceProcessor.java`:

```java
package demo.app.billing;

import demo.stereotype.DomainService;

@DomainService(beanName = "invoiceProcessor")
public class InvoiceProcessor {

    public String execute() {
        return "invoice-created";
    }
}
```

Class không trực tiếp gắn `@Component` hoặc `@Service`. Custom annotation đã đủ để component scanner nhận ra nó, nếu package `demo.app.billing` nằm trong vùng quét và không có filter loại bỏ.

### 5.5. Service dùng tên mặc định

Tệp `src/main/java/demo/app/report/ReportService.java`:

```java
package demo.app.report;

import demo.stereotype.DomainService;

@DomainService
public class ReportService {

    public String render() {
        return "report-ready";
    }
}
```

Vì không truyền `beanName`, mặc định là chuỗi rỗng. Bean name mặc định tương ứng class `ReportService` thường là `reportService`.

### 5.6. Bật component scan

Tệp `src/main/java/demo/config/AppConfig.java`:

```java
package demo.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "demo.app")
public class AppConfig {
}
```

Việc class cấu hình `AppConfig` ở `demo.config` không cản trở khả năng quét `demo.app`, vì `basePackages` đã chỉ định gốc rõ ràng. Class cấu hình được đưa vào context tường minh trong `Main`.

### 5.7. Truy vấn container và kiểm tra kết quả

Tệp `src/main/java/demo/Main.java`:

```java
package demo;

import demo.app.billing.InvoiceProcessor;
import demo.app.report.ReportService;
import demo.config.AppConfig;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("named=" +
                    context.containsBean("invoiceProcessor"));
            System.out.println("default=" +
                    context.containsBean("reportService"));

            InvoiceProcessor invoice =
                    context.getBean("invoiceProcessor", InvoiceProcessor.class);
            ReportService report =
                    context.getBean(ReportService.class);

            System.out.println("invoice=" + invoice.execute());
            System.out.println("report=" + report.render());
        }
    }
}
```

### 5.8. Chạy chương trình

Từ thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
```

Các dòng do chương trình in ra (không tính log Maven hoặc logging của môi trường):

```text
named=true
default=true
invoice=invoice-created
report=report-ready
```

**Giải thích kết quả:**

1. `AppConfig` yêu cầu scanner quét `demo.app` và các package con, nên cả `demo.app.billing` lẫn `demo.app.report` đều được xem xét.
2. Hai class mang `@DomainService`. Vì annotation này được meta-annotated bằng `@Component`, Spring nhận chúng là component ứng viên.
3. `InvoiceProcessor` có `beanName = "invoiceProcessor"`. Alias tường minh giúp Spring hiểu đây là giá trị cho `Component.value` và đăng ký bean với tên `invoiceProcessor`.
4. `ReportService` để `beanName` trống, do đó mặc định nhận tên `reportService`.
5. `getBean("invoiceProcessor", InvoiceProcessor.class)` và `getBean(ReportService.class)` đều lấy được bean. Hai phương thức ứng dụng trả chuỗi cố định, vì vậy output có thể dự đoán.

**Lưu ý:** Ví dụ này trình bày một chương trình độc lập đầy đủ gồm 5 file Java và 1 POM. Các ví dụ annotation nhỏ ở các mục khác có thể chỉ là **đoạn minh họa cần đặt vào project thích hợp**.

## 6. @AliasFor hoạt động theo ba kiểu quan hệ

`@AliasFor` được khai báo trên **attribute method** bên trong annotation. Trong Spring annotation programming model, có ba kiểu quan hệ đáng phân biệt.

### 6.1. Explicit alias giữa hai thuộc tính của cùng annotation

Giả sử bạn muốn `value` và `name` là hai cách viết tương đương:

```java
// Đoạn minh họa khai báo riêng một annotation.
import org.springframework.core.annotation.AliasFor;

public @interface LocalAlias {

    @AliasFor("name")
    String value() default "";

    @AliasFor("value")
    String name() default "";
}
```

Khi annotation được Spring xử lý bằng **MergedAnnotations** hoặc các API tương đương, hai thuộc tính là explicit aliases. Các điều kiện quan trọng:

- Cả hai phải có **cùng kiểu trả về** — trong ví dụ đều là `String`.
- Cả hai phải có **giá trị mặc định giống nhau** — trong ví dụ đều là `""`.
- Nên khai báo `@AliasFor` ở **cả hai phía** để tài liệu rõ ràng và tương thích tốt.
- Trong trường hợp cùng annotation, không chỉ định `annotation = ...` vì mặc định nó trỏ về annotation hiện tại.
- Nếu cung cấp hai giá trị **khác nhau** tại cùng một annotation, Spring có thể phát hiện xung đột alias khi tổng hợp metadata.

Ví dụ dùng:

```java
@LocalAlias("workerA")
class Alpha {
}

@LocalAlias(name = "workerB")
class Beta {
}
```

Tuy nhiên, `@LocalAlias` trong ví dụ này **không có `@Component`**, nên chỉ riêng alias không làm `Alpha` hay `Beta` trở thành Spring bean. Mục đích là minh họa quan hệ alias nội bộ; không phải một ví dụ component scan hoàn chỉnh.

### 6.2. Explicit alias tới meta-annotation

Đây là dạng chính của bài:

```java
@Component
public @interface DomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

`DomainService.beanName` là một **explicit override** cho `Component.value`. Giá trị từ annotation ở class sẽ được Spring truyền xuống cách nhìn metadata hợp nhất của `@Component`.

Các điều kiện cần hiểu:

1. `Component.class` phải là **meta-annotation được tìm thấy** trên định nghĩa của `@DomainService` (trực tiếp hoặc meta-present qua tầng hợp lệ).
2. Thuộc tính đích `value` phải tồn tại trên `@Component`.
3. Kiểu trả về của nguồn và đích phải tương thích/cùng loại: ở đây cả hai đều là `String`.
4. Ghi rõ `annotation = Component.class` và `attribute = "value"` để Spring biết thuộc tính nào được override.
5. Đảm bảo target annotation có retention/target phù hợp để metadata có thể được sử dụng.

Không thể dùng:

```java
// PHẢN VÍ DỤ — @Component không nằm trong chuỗi meta-annotation.
@Deprecated
public @interface BrokenService {
    @AliasFor(annotation = Component.class, attribute = "value")
    String name() default "";
}
```

rồi kỳ vọng Spring tự động hiểu `BrokenService` là stereotype. Ở đây `@Component` không meta-present trên `@BrokenService`; alias tham chiếu sai hệ meta-annotation và có thể khiến Spring phát hiện cấu hình annotation không hợp lệ khi đọc metadata. `@Deprecated` cũng không phải stereotype.

### 6.3. Implicit aliases khi hai thuộc tính cùng override một meta-attribute

Bạn có thể mở cả `value` lẫn `beanName`, mỗi thuộc tính cùng override `Component.value`:

```java
// Đoạn minh họa một custom stereotype khác.
// Cần import java.lang.annotation.*,
// org.springframework.core.annotation.AliasFor và
// org.springframework.stereotype.Component.

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface NamedDomainService {

    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

Hai thuộc tính trên trở thành **implicit aliases** của nhau vì cùng trỏ đến một meta-attribute `Component.value`. Chúng cần **cùng kiểu** và **cùng giá trị mặc định**; bạn có thể dùng `@NamedDomainService("a")` hoặc `@NamedDomainService(beanName = "a")`. Nếu khai báo hai giá trị khác nhau ở cùng một vị trí, Spring có thể báo xung đột khi xử lý merged attributes.

Không cần khai báo cả hai tên nếu dự án không có yêu cầu cú pháp tương đương. Một thuộc tính `beanName()` tường minh như ví dụ đầy đủ thường đơn giản và ít gây hiểu nhầm hơn.

### 6.4. Alias qua nhiều tầng meta-annotation

Spring hỗ trợ tổng hợp metadata qua nhiều tầng. Ví dụ `@SpecializedService` được meta-annotated bằng `@DomainService`, còn `@DomainService` được meta-annotated bằng `@Component`. Một alias của `@SpecializedService` có thể nhắm vào thuộc tính meta-annotation `@DomainService` rồi được truyền tiếp sang `@Component` nếu khai báo đúng chuỗi alias.

```java
// Đoạn minh họa: DomainService là annotation đã định nghĩa.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DomainService
public @interface SpecializedService {

    @AliasFor(annotation = DomainService.class, attribute = "beanName")
    String name() default "";
}
```

Ở đây `SpecializedService.name` trỏ tới `DomainService.beanName`; `DomainService.beanName` lại trỏ tới `Component.value`. Ví dụ cho thấy khả năng **transitive meta-annotation override**, nhưng không nên tạo nhiều tầng annotation chỉ vì có thể. Mỗi tầng làm người đọc khó thấy metadata cuối cùng hơn; trong hệ thống thực, cần integration test xác nhận tên bean và phần metadata áp dụng.

## 7. Java reflection và Spring merged annotation model

Một hiểu lầm phổ biến: khai báo `@AliasFor` sẽ khiến **Java reflection thuần** tự động đọc một alias như alias kia.

Thực tế, `@AliasFor` là **metadata cho cơ chế đọc annotation của Spring**. Java reflection như `SomeClass.class.getAnnotation(...)` chỉ phản ánh annotation theo mô hình Java, không tự thực thi quy tắc override giữa meta-annotations.

Ví dụ với `InvoiceProcessor`:

```java
// Đoạn minh họa trong dự án ví dụ đầy đủ:
DomainService direct =
        InvoiceProcessor.class.getAnnotation(DomainService.class);

System.out.println(direct.beanName());
```

`direct.beanName()` trả chuỗi `"invoiceProcessor"` vì giá trị này đã được khai báo trực tiếp trên annotation. Nhưng điều đó **không chứng minh** Java reflection tự tính ra `Component.value`.

Khi cần đọc kết quả tổng hợp:

```java
// Đoạn bổ sung trong project ví dụ.
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;

Component merged = AnnotatedElementUtils.findMergedAnnotation(
        InvoiceProcessor.class, Component.class);

System.out.println(merged.value());
```

Output dự kiến của đoạn bổ sung:

```text
invoiceProcessor
```

`findMergedAnnotation` dùng mô hình merged annotations của Spring, nên thấy thuộc tính `Component.value` đã được custom stereotype override. Nó cũng có thể trả `null` nếu annotation cần tìm không hiện diện; với `InvoiceProcessor` trong ví dụ này, `@Component` hiện diện ở tầng meta-annotation nên có kết quả.

Các API như `MergedAnnotations` và `AnnotatedElementUtils` là công cụ thích hợp khi tự viết infrastructure cần truy vấn composed metadata. Tránh viết một vòng reflection thủ công chỉ tìm `@Component` trực tiếp trên class rồi kết luận mọi custom stereotype đều không hợp lệ: `@Component` có thể **meta-present**.

## 8. @ComponentScan phát hiện custom stereotype ra sao?

Với:

```java
@Configuration
@ComponentScan(basePackages = "demo.app")
class AppConfig {
}
```

khi `useDefaultFilters` giữ giá trị mặc định `true`, scanner tìm những class được gắn `@Component` **trực tiếp hoặc qua meta-annotation**; `@Service` và custom `@DomainService` đều thuộc nhóm này.

Quy trình khái niệm:

```text
Quét classpath dưới demo.app
        |
        v
Đọc metadata annotation của class
        |
        v
Class có @Component trực tiếp / meta-present?
        | Có
        v
Kiểm tra bộ lọc và điều kiện ứng viên
        |
        v
Xác định bean name từ stereotype/alias hoặc generator mặc định
        |
        v
Đăng ký BeanDefinition
        |
        v
Tạo bean theo lifecycle/scope khi cần
```

Một class có `@DomainService` **không được tìm thấy** nếu nó nằm ngoài root `demo.app`, dù annotation được định nghĩa chính xác. Việc thay annotation từ `@Component` sang `@DomainService` cũng không tự mở rộng phạm vi scan.

Nếu scanner sử dụng:

```java
@ComponentScan(
    basePackages = "demo.app",
    useDefaultFilters = false
)
```

các default stereotype filters bị tắt. Khi ấy `@DomainService` không tự được nhận diện theo mặc định nữa; muốn lấy lại cần cấu hình `includeFilters` phù hợp. Vì vậy cần phân biệt **annotation được định nghĩa đúng** với **scanner có bật bộ lọc để nhận nó hay không**.

Cũng cần phân biệt một class annotation với bean definition: định nghĩa annotation chỉ làm class trở thành **candidate**; các vấn đề như dependency không thỏa, xung đột tên bean hoặc configuration conditions có thể ngăn việc đăng ký/khởi tạo thành công.

## 9. Composed stereotype và @Service/@Repository/@Controller

`@Component` là cơ sở đơn giản nhất, nhưng không phải mọi custom stereotype đều nên mang ý nghĩa chung giống nhau. Nếu muốn tạo annotation cho tầng dịch vụ, bạn có thể meta-annotate bằng `@Service`; vì `@Service` tự meta-annotated bằng `@Component`, class vẫn là component ứng viên. Khi đó cấu trúc metadata có nhiều tầng.

Tuy nhiên, cần hiểu:

- `@Service` thể hiện vai trò dịch vụ; bản thân annotation không tự bổ sung transaction hoặc security.
- `@Repository` có thể tham gia cơ chế dịch exception ở tầng persistence khi hạ tầng xử lý tương ứng được bật. Không dùng nó cho class chỉ vì muốn component scan.
- `@Controller` dành cho lớp điều khiển trong stack web; một custom stereotype meta-annotated bằng `@Controller` không tự định nghĩa các request mapping.
- `@RestController` của Spring MVC là ví dụ thực tế của annotation ghép từ `@Controller` và `@ResponseBody`, nhưng thuộc phạm vi web, không phải ví dụ core của bài.

Chọn meta-stereotype dựa trên **vai trò thật** của component. Khi mục tiêu là một annotation do ứng dụng sở hữu và có tên bean tùy chỉnh, `@Component` trực tiếp giúp xác định ý nghĩa tối thiểu rồi mở rộng khi có nhu cầu.

## 10. Ghép thêm metadata khác: không nhầm với @AliasFor

Custom stereotype có thể đặt nhiều meta-annotation nhưng mỗi annotation có hợp đồng riêng. Chẳng hạn, nếu một nhóm bean thực sự phải dùng scope prototype:

```java
// Đoạn minh họa annotation khác; cần đủ imports.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
@Scope("prototype")
public @interface PrototypeComponent {

    @AliasFor(annotation = Component.class, attribute = "value")
    String beanName() default "";
}
```

`@Scope("prototype")` quy định scope, còn `@AliasFor` ở trên chỉ quy định thuộc tính tên bean. Không suy ra rằng `@AliasFor` tự kích hoạt scope prototype. Nếu muốn công khai cả tùy chọn scope hoặc proxy mode, cần những alias đúng tới thuộc tính của `@Scope`, với kiểu trả về đúng và metadata meta-present hợp lệ.

Tương tự:

- `@Qualifier` dùng để gắn thông tin lựa chọn ứng viên tại injection point; không phải một cách đặt tên bean chung.
- `@Primary` ưu tiên một ứng viên trong single-bean autowiring; không phải alias hay yêu cầu tạo bean.
- `@Order` ảnh hưởng thứ tự ở các điểm cần sắp xếp; không làm bean tự được đăng ký.
- `@Transactional` cần hạ tầng quản lý giao dịch phù hợp để tạo hành vi transaction. Chỉ ghép annotation không bảo đảm proxy/transaction manager đã được bật.
- `@Lazy` ảnh hưởng lazy initialization hoặc lazy dependency resolution theo vị trí áp dụng; không đồng nghĩa custom stereotype là optional dependency.

Đừng gom tất cả metadata vào một annotation "vạn năng". Mỗi meta-annotation bổ sung một quyết định cấu hình và có thể tạo hiệu ứng khó quan sát khi áp dụng rộng.

## 11. Quy tắc @AliasFor cần nhớ khi thiết kế API annotation

### 11.1. Alias nội bộ phải đồng nhất kiểu và default

Đối với:

```java
@AliasFor("name")
String value() default "";

@AliasFor("value")
String name() default "";
```

hai thuộc tính có cùng kiểu `String` và cùng default `""`. Nếu một thuộc tính default là `"main"` còn thuộc tính kia là `""`, cặp alias không đáp ứng hợp đồng của Spring. Nếu một bên là `String` còn bên kia là `String[]`, kiểu cũng không khớp.

### 11.2. Alias tới meta-annotation phải trỏ đúng thuộc tính

```java
@AliasFor(annotation = Component.class, attribute = "value")
String beanName() default "";
```

`Component.value` là `String`, vì thế `beanName` cũng phải là `String`. Viết `attribute = "name"` nếu `@Component` không có `name()` là sai.

### 11.3. Không nên lạm dụng alias khi tên thuộc tính không có ý nghĩa

Nếu custom annotation chỉ để thay `@Component` bằng một tên miền nghiệp vụ và không cần đặt tên bean tùy chỉnh, có thể viết:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface DomainService {
}
```

Annotation này vẫn là custom stereotype hợp lệ. **`@AliasFor` là công cụ để khai báo quan hệ thuộc tính**, không phải bước bắt buộc cho mọi custom stereotype. Chỉ thêm khi cần công khai thuộc tính của meta-annotation hoặc tạo các tên đồng nghĩa.

### 11.4. Đừng dựa vào quy ước ngầm cũ

Một custom stereotype có `String value() default ""` nhưng không khai báo `@AliasFor` từng được một số cơ chế của Spring xử lý theo convention đặt tên. Từ Spring Framework 6.1, support đặt tên component theo quy ước kiểu này bị deprecated. Với code mới, khai báo explicit alias tới `Component.value` để ý định và khả năng tương thích rõ ràng.

### 11.5. @AliasFor không thay Java annotation semantics

Các giá trị annotation là phần của Java class metadata, không phải biến mutable. Không thể thay đổi một alias trong lúc ứng dụng chạy rồi mong mọi bean được đổi tên. Tên bean được quyết định khi Spring đăng ký bean definition; việc đọc annotation qua Spring merged model phục vụ cơ chế xử lý metadata.

## 12. Kiểm tra bằng integration test thay vì chỉ nhìn annotation

Một custom stereotype phải được kiểm tra ở **hai mức**:

1. Mức **metadata**: Spring đọc được `@Component` meta-present, và alias `beanName` được tổng hợp vào `Component.value`.
2. Mức **container**: component scanner phát hiện class ở đúng package, bean name đúng và bean có thể được inject/tra cứu theo kiểu.

Ví dụ đoạn kiểm tra thêm vào `Main` của dự án ở mục 5:

```java
// Đoạn minh họa thêm vào main, cần imports tương ứng.
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Component;

// Sau khi context được tạo:
Component merged = AnnotatedElementUtils.findMergedAnnotation(
        InvoiceProcessor.class, Component.class);

if (merged == null ||
        !"invoiceProcessor".equals(merged.value())) {
    throw new AssertionError("Incorrect merged component name");
}
if (!context.containsBean("invoiceProcessor")) {
    throw new AssertionError("Custom stereotype bean not registered");
}
if (!context.containsBean("reportService")) {
    throw new AssertionError("Default component name not registered");
}
```

Đây là **đoạn kiểm thử bổ sung**, không in thêm stdout khi đúng. Nếu tên bean bị thay đổi do alias lỗi hoặc package scan sai, nó giúp chỉ ra sự cố. Mục đích là test **kết quả thật của container**, không phải chỉ assert annotation có mặt qua reflection.

Nếu bạn triển khai một custom annotation có nhiều alias, nên thêm test cho trường hợp dùng từng tên alias và trường hợp khai báo xung đột. Nếu alias trỏ qua nhiều tầng meta-annotation, cần test thông tin được truyền đúng đến annotation đích.

Trong một dự án có bean naming strategy riêng, test nên được viết theo chiến lược đó, không dựa cứng vào `reportService` nếu đây không phải default name generator.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Class mang `@DomainService` nhưng không có bean | Thiếu meta-annotation `@Component`, class ngoài vùng quét, hoặc scanner bị đổi filter | Kiểm tra `@Component` trên định nghĩa annotation, root scan, `useDefaultFilters` và classpath |
| `beanName` bị bỏ qua | Không khai báo alias tường minh tới `Component.value` hoặc alias cấu hình sai | Thêm `@AliasFor(annotation = Component.class, attribute = "value")` |
| Spring báo lỗi annotation configuration | Alias trỏ thuộc tính không tồn tại, meta-annotation đích không có mặt, kiểu/default không hợp lệ | Đọc exception gốc và Javadoc `@AliasFor` |
| Tên bean mặc định khác dự kiến | Dùng bean name generator riêng hoặc class name có quy tắc đặc biệt | Truy vấn tên thực tế và cấu hình generator |
| Hai component có tên bean giống nhau | Alias gán trùng tên hoặc component scan rộng hơn dự định | Chọn tên duy nhất, thiết kế namespace/scan hợp lý |
| `@AliasFor` đặt trên class sử dụng | Không hiểu nơi khai báo alias | Đặt annotation trên method `String beanName()` **bên trong định nghĩa @interface** |
| Thiếu `@Retention(RUNTIME)` | Annotation không còn runtime metadata như cần thiết | Khai báo retention runtime |
| Chỉ thấy `@DomainService` qua reflection nhưng không thấy `@Component` trực tiếp | Java reflection không tự trả meta-annotation như annotation trực tiếp | Dùng `MergedAnnotations`/`AnnotatedElementUtils` của Spring |
| Annotation xuất hiện nhưng chức năng transaction không chạy | Meta-annotate `@Transactional` mà thiếu cơ chế transaction phù hợp | Cấu hình transaction manager/proxy theo nhu cầu, phân biệt bean discovery và behavior |
| Trùng alias trong cùng annotation có giá trị khác nhau | Vi phạm hợp đồng alias khi Spring tổng hợp metadata | Chỉ cung cấp một tên alias hoặc bảo đảm các giá trị thống nhất |
| `@DomainService` dùng được trong một module nhưng không trong module khác | Classpath, root scan hoặc component filter khác nhau | Kiểm tra cấu hình ApplicationContext và dependencies |
| Marker interface bị hiểu là component | Nhầm marker kiểu `basePackageClasses` với stereotype | Marker chỉ làm mốc quét package nếu không có `@Component` |

### Quy trình debug gọn

1. Xác nhận `@DomainService` có `@Target(TYPE)`, `@Retention(RUNTIME)` và meta-annotation `@Component`.
2. Kiểm tra bean class nằm trong package mà `@ComponentScan` thật sự quét.
3. Xác định scanner còn dùng default filters hay có custom include/exclude filters.
4. Kiểm tra thuộc tính alias: annotation đích, tên thuộc tính, kiểu trả về và default.
5. Dùng `AnnotatedElementUtils.findMergedAnnotation` để xem Spring tổng hợp được `@Component` và `value` như mong muốn không.
6. Tạo ApplicationContext nhỏ rồi kiểm tra `containsBean` và `getBean`; nếu lỗi, đọc root exception trước khi sửa cấu hình.

Không nên sửa bằng cách gắn thêm cả `@Component` lên mọi class sử dụng custom stereotype chỉ để làm hệ thống "chạy được"; cách này có thể che vấn đề nằm ở chính định nghĩa annotation hoặc scan configuration.

## 14. Bài tập tự kiểm tra

### Bài 1: bỏ @Component

Nếu xóa `@Component` khỏi định nghĩa `@DomainService` nhưng giữ `@AliasFor(annotation = Component.class, attribute = "value")`, scanner mặc định có còn nhận `InvoiceProcessor` không?

**Đáp án:** Không. `@DomainService` không còn là stereotype dựa trên `@Component`; alias cũng không thể thay thế meta-annotation đích. Hơn nữa quan hệ alias tới `Component.value` không còn có chuỗi meta-annotation hợp lệ, dễ dẫn tới lỗi khi Spring xử lý metadata.

### Bài 2: đổi beanName

Đổi `@DomainService(beanName = "invoiceProcessor")` thành `@DomainService(beanName = "billingInvoice")`. Cần thay đổi lệnh lấy bean theo tên thế nào?

**Đáp án:** `context.getBean("billingInvoice", InvoiceProcessor.class)`. Kiểu class và method `execute()` không đổi, nhưng tên bean được đăng ký thay đổi. Với consumer tiêm theo type khi chỉ có một ứng viên, việc đổi bean name có thể không ảnh hưởng; với lookup bằng chuỗi thì có.

### Bài 3: quét sai package

Nếu `@ComponentScan(basePackages = "demo.app.report")`, còn `InvoiceProcessor` nằm trong `demo.app.billing`, custom stereotype có làm InvoiceProcessor vẫn được phát hiện không?

**Đáp án:** Không. Meta-annotation quyết định class có phải ứng viên stereotype; package scan quyết định **class có được xem xét**. Phải quét thêm đúng gốc billing hoặc đăng ký bean bằng cơ chế khác.

### Bài 4: alias trong cùng annotation

Với:

```java
@AliasFor("name")
String value() default "";

@AliasFor("value")
String name() default "";
```

hai thuộc tính có thể có kiểu khác nhau hoặc default khác nhau không?

**Đáp án:** Không. Explicit aliases trong cùng annotation cần cùng kiểu và cùng default. Nếu muốn cho phép hai tùy chọn độc lập, đừng khai báo chúng là alias.

### Bài 5: alias nào ảnh hưởng bean name?

Một annotation có `@Component` và một thuộc tính `String category() default "core";` nhưng không có `@AliasFor`. `category` có tự trở thành tên bean không?

**Đáp án:** Không. Nó là metadata riêng do annotation định nghĩa; để ánh xạ tên bean, cần explicit alias tới `Component.value` hoặc một bean name generator/custom scanner thực hiện chính sách riêng.

### Bài 6: thiết kế custom stereotype

Bạn muốn class ở tầng application được đánh dấu `@ApplicationUseCase`, cho phép `@ApplicationUseCase(name = "orderCreation")` đặt tên bean. Hãy nêu những thành phần thiết yếu.

**Đáp án định hướng:** Khai báo một `@interface ApplicationUseCase` có `@Target(TYPE)`, `@Retention(RUNTIME)`, `@Documented` và meta-annotation `@Component`. Thêm `@AliasFor(annotation = Component.class, attribute = "value") String name() default "";`. Quét đúng package, rồi kiểm tra container có bean `orderCreation`. Chỉ thêm scope/transaction/qualifier nếu đó là yêu cầu thực sự của role.

## Ghi nhớ

- **Meta-annotation `@Component`** biến custom annotation thành stereotype mà component scanner mặc định có thể phát hiện.
- **`@AliasFor`** mô tả quan hệ giữa các attribute: alias nội bộ, override tới meta-attribute, hoặc implicit aliases giữa nhiều attribute cùng đích.
- Với custom stereotype có thuộc tính đặt tên riêng, dùng **`@AliasFor(annotation = Component.class, attribute = "value")`** để đặt bean name một cách tường minh và tương thích hướng phát triển Spring 6.1+.
- `@Target(TYPE)`, `@Retention(RUNTIME)` và phạm vi scan phải đúng; định nghĩa annotation hợp lệ chưa bảo đảm bean được đăng ký nếu scanner không tìm tới class.
- Java reflection thông thường không thay thế cơ chế **Spring merged annotations**. Khi cần xác minh alias, kiểm tra cả metadata được tổng hợp và bean thực tế trong ApplicationContext.
- Giữ custom stereotype nhỏ, đúng ý nghĩa nghiệp vụ và có integration test; không biến một annotation thành nơi gom mọi chính sách của Spring.

## Tài liệu chính thức

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): stereotype, meta-annotation, annotation ghép, tên bean và component scanner.
- [Spring Framework 6.2 — @AliasFor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/annotation/AliasFor.html): các loại alias, điều kiện kiểu và default, explicit/implicit overrides.
- [Spring Framework 6.2 — @Component Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/stereotype/Component.html): stereotype và convention naming từ Spring 6.1.
- [Spring Framework 6.2 — @ComponentScan Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html): phạm vi quét và các filter.
- [Spring Framework — Annotation Programming Model](https://github.com/spring-projects/spring-framework/wiki/Spring-Annotation-Programming-Model): giải thích sâu về merged annotation và aliases.
