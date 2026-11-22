# Quy tắc sinh tên bean và tùy biến `BeanNameGenerator` trong Spring Core Container

## 1. Vì sao tên bean quan trọng?

Một Spring IoC Container quản lý các **bean definition** được định danh bằng tên. Khi viết `@Component`, `@Service`, `@Repository` hoặc các stereotype chuyên biệt, ta có thể cung cấp tên rõ ràng hoặc để Spring tự sinh. Tên bean xuất hiện trong nhiều thao tác:

- `applicationContext.getBean("orderService")`: lookup bằng tên;
- `@Qualifier("orderService")`: có thể dùng bean name làm giá trị qualifier mặc định khi phân giải dependency;
- `@Resource(name = "...")`: một cách chọn dependency theo tên trong ngữ cảnh hỗ trợ annotation đó;
- các tập hợp `Map<String, T>` được Spring autowire: khóa thường là bean name;
- các hệ thống quan sát/diagnostics, configuration hoặc integration tham chiếu bean bằng tên.

Ví dụ, hai thành phần sau cùng được scan:

```java
@Component
class InvoiceFormatter {
}

@Service("checkoutWorkflow")
class CheckoutService {
}
```

Với naming strategy mặc định, bean đầu thường có tên `invoiceFormatter`; bean thứ hai có tên **`checkoutWorkflow`** do đã khai báo rõ. Đây là **đoạn minh họa**, không phải file Java chạy độc lập.

Tại sao cần học `BeanNameGenerator`? Trong codebase lớn, nhiều package có thể chứa class trùng **tên ngắn**: `com.acme.sales.ReportService` và `com.acme.audit.ReportService`. Nếu cả hai được component scanning phát hiện và đều nhận tên mặc định `reportService`, Spring có nguy cơ báo xung đột bean definition. Có thể đặt tên riêng trên các stereotype hoặc dùng strategy sinh tên dựa vào tên class đầy đủ.

Mục tiêu của bài:

1. Hiểu quy tắc tên mặc định, tên tường minh, JavaBeans decapitalization và ngoại lệ với chữ viết hoa;
2. Nắm giao diện `BeanNameGenerator` cùng `AnnotationBeanNameGenerator` và `FullyQualifiedAnnotationBeanNameGenerator`;
3. Biết cấu hình `@ComponentScan(nameGenerator = ...)`, thời điểm áp dụng và tác động khi refactor;
4. Tự viết custom generator an toàn, ưu tiên giữ tên khai báo tường minh;
5. Nhận biết cách đặt tên của component scan khác `@Bean` và cấu hình import;
6. Kiểm thử bằng một dự án Java 17+ và Spring Framework 6.

## 2. Spring đặt tên cho component được scan như thế nào?

Khi Spring quét một base package bằng `@ComponentScan`, scanner tìm class ứng viên và đăng ký bean definition. Tại thời điểm đăng ký, nó cần tên cho từng definition. Chiến lược mặc định của **component scanner** là `org.springframework.context.annotation.AnnotationBeanNameGenerator`.

Logic có thể hiểu theo thứ tự:

1. Scanner phát hiện một component candidate có metadata annotation.
2. `AnnotationBeanNameGenerator` thử lấy **tên khai báo tường minh** từ stereotype thích hợp.
3. Nếu không có tên tường minh, nó sinh tên mặc định dựa vào **tên class ngắn** theo quy tắc JavaBeans.
4. Bean definition được đăng ký với tên đó; nếu tên đã dùng cho definition khác không tương thích, quá trình scan có thể thất bại vì xung đột.

Sơ đồ:

```text
Class được @ComponentScan phát hiện
                  |
                  v
       BeanNameGenerator
                  |
       +----------+-----------+
       |                      |
 @Component("explicit")      Không có tên tường minh
 / @Service("explicit")                  |
       |                                 v
       v                      Sinh từ class name
 "explicit"                   (mặc định tên ngắn)
       |                                 |
       +--------------+------------------+
                      v
         Đăng ký bean definition
                      |
           Tên bị trùng, xung đột?
             /               \
           Có               Không
           |                  |
     Lỗi đăng ký        Bean sẵn sàng resolve
```

Tên bean là **định danh trong registry**, không đồng nghĩa Java class name, package name, qualifier bất kỳ hoặc loại dependency. Một bean có thể có nhiều alias, nhưng vẫn chỉ có một primary bean name dùng khi đăng ký.

### 2.1. Tên mặc định: JavaBeans `decapitalize`

Với một class `com.acme.billing.InvoiceService`, Spring thường sinh tên `invoiceService`: lấy phần **simple class name** rồi áp dụng quy tắc bỏ viết hoa đầu theo JavaBeans.

| Class được scan | Tên mặc định với `AnnotationBeanNameGenerator` |
| --- | --- |
| `com.acme.billing.InvoiceService` | `invoiceService` |
| `com.acme.billing.MyJdbcDao` | `myJdbcDao` |
| `com.acme.api.UserController` | `userController` |
| `com.acme.util.URLFormatter` | `URLFormatter` |
| `com.acme.util.XMLParser` | `XMLParser` |

**Ngoại lệ cần nhớ:** `java.beans.Introspector.decapitalize` giữ nguyên chuỗi nếu **hai ký tự đầu đều viết hoa**. Vì vậy `URLFormatter` không trở thành `uRLFormatter`. Đây là lý do không nên tự triển khai tên mặc định bằng `Character.toLowerCase(name.charAt(0))`.

Đoạn Java độc lập sau kiểm tra được quy tắc decapitalize mà Spring sử dụng:

```java
import java.beans.Introspector;

public class BeanNameRuleDemo {
    public static void main(String[] args) {
        System.out.println(Introspector.decapitalize("InvoiceService"));
        System.out.println(Introspector.decapitalize("URLFormatter"));
        System.out.println(Introspector.decapitalize("XMLParser"));
    }
}
```

Lưu vào `BeanNameRuleDemo.java` rồi chạy bằng JDK 17+:

```bash
javac BeanNameRuleDemo.java
java BeanNameRuleDemo
```

Stdout:

```text
invoiceService
URLFormatter
XMLParser
```

Trong ví dụ này JavaBeans `Introspector` chỉ minh họa quy tắc đặt tên. Component scanning thật còn xử lý annotation, registry, bean definition và các điều kiện phát hiện class.

### 2.2. Tên khai báo tường minh

Spring stereotype hỗ trợ tên do developer chỉ định:

```java
@Component("auditWriter")
class AuditWriter {
}

@Service("paymentGateway")
class CardGateway {
}

@Repository("orderStorage")
class JpaOrderRepository {
}
```

Đây là **mã minh họa**; với lớp nằm trong package được scan, các tên được đăng ký lần lượt là `auditWriter`, `paymentGateway`, `orderStorage`. Tên do annotation cung cấp có mức ưu tiên hơn tên mặc định của generator.

`@Component(value = "auditWriter")` và `@Component("auditWriter")` tương đương. Các stereotype chuyên biệt như `@Service` có thuộc tính `value` thích hợp để khai báo tên.

Khi cần gọi bean theo tên từ code hoặc external configuration, **tên tường minh là một hợp đồng ổn định hơn tên suy ra từ class**. Nếu đổi tên class `CardGateway` thành `StripeGateway`, bean được khai báo `@Service("paymentGateway")` vẫn có tên `paymentGateway`. Ngược lại, tên mặc định tự đổi từ `cardGateway` sang `stripeGateway`.

### 2.3. Bean name không mặc nhiên là qualifier duy nhất

Ví dụ có hai bean implement `PaymentGateway`, một được đặt tên `cardGateway`, một tên `bankGateway`. Constructor cần `PaymentGateway` **không có qualifier** có thể gặp `NoUniqueBeanDefinitionException` nếu không có lựa chọn thắng theo quy tắc khác.

`@Qualifier("cardGateway")` thường có thể chọn bean tương ứng vì Spring xem bean name như giá trị qualifier mặc định trong trường hợp phù hợp. Nhưng khi nhóm nghiệp vụ có nhiều bean cùng qualifier, qualifier không bắt buộc phải trùng bean name và không nhất thiết là duy nhất.

Đừng dùng `BeanNameGenerator` để thay cho giải pháp rõ nghĩa khi dependency đơn có nhiều implementation. Generator giải quyết **định danh đăng ký**; `@Qualifier`, `@Primary` và các quy tắc autowire giải quyết **chọn bean**.

## 3. Các API chính của `BeanNameGenerator`

`org.springframework.beans.factory.support.BeanNameGenerator` là interface chiến lược sinh tên. Phương thức trọng tâm:

```java
String generateBeanName(
        BeanDefinition definition,
        BeanDefinitionRegistry registry
);
```

Đây là chữ ký API giản lược, cần imports `BeanDefinition` và `BeanDefinitionRegistry` từ `org.springframework.beans.factory.config` / `org.springframework.beans.factory.support`. Một implementation nhận metadata của bean và registry, trả **tên bean** để caller đăng ký.

Ba khái niệm liên quan:

| API | Vai trò | Đặc điểm |
| --- | --- | --- |
| `BeanNameGenerator` | Interface chiến lược | Có thể tự thực thi logic riêng |
| `AnnotationBeanNameGenerator` | Strategy mặc định cho component scanning | Đọc explicit stereotype name; fallback tên class ngắn kiểu JavaBeans |
| `FullyQualifiedAnnotationBeanNameGenerator` | Strategy tích hợp sẵn | Giữ explicit stereotype name; fallback tên class đầy đủ gồm package |

`AnnotationBeanNameGenerator` cung cấp phương thức protected `buildDefaultBeanName(BeanDefinition)` để subclass tùy biến cách sinh **tên mặc định**. Đây là extension point phù hợp nếu bạn muốn giữ cách Spring đọc tên từ stereotype nhưng đổi fallback format.

### 3.1. `AnnotationBeanNameGenerator`

Với `@Component class LocalProcessor` trong package `demo.catalog`, default name là `localProcessor`. Cùng một class name trong `demo.billing` cũng trở thành `localProcessor`. Nếu quét cả hai vào **cùng một BeanDefinitionRegistry**, xảy ra xung đột trừ khi có cách phân biệt tên.

Nó phù hợp với dự án nhỏ hoặc kiến trúc có convention bảo đảm tên class component không trùng trong phạm vi scan.

### 3.2. `FullyQualifiedAnnotationBeanNameGenerator`

Class `org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator` mở rộng `AnnotationBeanNameGenerator` và đổi fallback thành **tên class đầy đủ**:

| Component | Default generator | Fully-qualified generator |
| --- | --- | --- |
| `demo.catalog.LocalProcessor` | `localProcessor` | `demo.catalog.LocalProcessor` |
| `demo.billing.LocalProcessor` | `localProcessor` | `demo.billing.LocalProcessor` |
| `demo.catalog.URLFormatter` | `URLFormatter` | `demo.catalog.URLFormatter` |
| `@Service("invoiceWorkflow") demo.catalog.InvoiceService` | `invoiceWorkflow` | `invoiceWorkflow` |

Các tên có dấu chấm `.` hoàn toàn có thể là bean name. Đây không phải Java expression, và `context.getBean("demo.catalog.LocalProcessor")` hoạt động như lookup bằng chuỗi khi bean đã được đăng ký dưới tên đó.

**Lưu ý:** `FullyQualifiedAnnotationBeanNameGenerator` vẫn **tôn trọng tên khai báo tường minh**. `@Service("invoiceWorkflow")` không bị đổi thành `demo.catalog.InvoiceService`. Nếu hai class ở hai package cùng được gắn explicit name `"invoiceWorkflow"`, đổi generator sang fully-qualified **không tự xử lý được xung đột tên tường minh**; phải sửa cấu hình đặt tên.

Theo Javadoc của Spring Framework 6.2, mặc định **component scanning** dùng `AnnotationBeanNameGenerator`, còn cơ chế **configuration-level import** có thể sử dụng `FullyQualifiedAnnotationBeanNameGenerator` mặc định. Không vì thế mà toàn bộ bean trong Spring context đều được sinh tên fully-qualified.

### 3.3. Khi nào tự triển khai một generator?

Một custom generator phù hợp khi codebase có naming convention rõ: ví dụ thêm prefix `site_`, thêm namespace theo domain hoặc tạo định danh từ metadata. Nhưng quy tắc phải ổn định, dễ kiểm thử và không làm hỏng bean name được cấu hình có chủ đích.

Nếu mục tiêu đơn thuần là tránh xung đột tên class ngắn từ nhiều package, **ưu tiên strategy fully-qualified sẵn có** trước khi viết custom generator. Điều đó giúp giảm code hạ tầng không cần thiết.

## 4. Cấu hình generator cho component scanner

`@ComponentScan` cung cấp thuộc tính `nameGenerator` nhận một class triển khai `BeanNameGenerator`:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

@Configuration
@ComponentScan(
        basePackages = {"com.example.sales", "com.example.audit"},
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
public class AppConfig {
}
```

Đây là **đoạn minh họa** với các package giả định. Khi `AppConfig` được đăng ký vào context, scanner sử dụng generator chỉ định để đặt tên cho các component do lượt scan này phát hiện.

Bạn cũng có thể dùng class tự viết:

```java
@Configuration
@ComponentScan(
        basePackages = "com.example.sales",
        nameGenerator = PrefixBeanNameGenerator.class
)
class PrefixedConfig {
}
```

Đoạn này chỉ minh họa cú pháp; cần class `PrefixBeanNameGenerator` thật sự triển khai `BeanNameGenerator`, có constructor không tham số và được Spring tạo được tại lúc xử lý scan. Một generator khai báo qua annotation là **hạ tầng cấu hình scanner**, không phải bean nghiệp vụ bắt buộc phải được component scanner quét.

**Phạm vi tác động:** `nameGenerator` trên một `@ComponentScan` ảnh hưởng các component definitions **được đăng ký qua lượt scan đó**. Nó không mặc định đổi tên mọi bean do `@Bean` method, `@Import`, auto-configuration hoặc API đăng ký bean trực tiếp tạo ra. Nếu nhiều lượt scan có chiến lược khác nhau, cần hiểu chúng có thể cùng ghi vào một registry và cùng tạo xung đột tên.

### 4.1. Cấu hình bằng API chương trình

Nếu dựng `AnnotationConfigApplicationContext` bằng code, có thể cấu hình naming strategy trên context trước khi đăng ký các configuration class:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
context.setBeanNameGenerator(
        new FullyQualifiedAnnotationBeanNameGenerator());
context.register(AppConfig.class);
context.refresh();
try {
    // Sử dụng context...
} finally {
    context.close();
}
```

Đây là **mã minh họa**; cần imports và `AppConfig` thực tế. Đặt generator **trước** `register`/`scan` và `refresh` để việc đăng ký bean definition sử dụng đúng strategy. Tùy API đăng ký và mức cấu hình, `@ComponentScan(nameGenerator = ...)` cụ thể có thể chọn generator riêng cho lượt scan, nên khi cần kiểm soát chặt, hãy đặt policy thống nhất tại các điểm scan.

### 4.2. Spring Boot

Ứng dụng Spring Boot thông thường có component scanning nhờ `@SpringBootApplication`. Có thể cấu hình một generator cho scanner bằng `@ComponentScan` được khai báo tường minh, nhưng cần cẩn trọng: khi đặt `@ComponentScan` trực tiếp cùng `@SpringBootApplication`, bạn đang bổ sung hoặc thay đổi cách quét và cần kiểm tra các exclude filters mặc định mà Boot cung cấp qua composed annotation.

Một hướng ít mơ hồ là cấu hình naming strategy qua API context hoặc cấu hình hạ tầng thống nhất của ứng dụng, và **kiểm thử bean registry cuối cùng**. Với phạm vi bài học này, chương trình chạy ở mục 7 dùng Spring Context thuần để minh họa chính xác hành vi của `@ComponentScan`.

## 5. Custom `BeanNameGenerator`: thêm prefix nhưng tôn trọng tên khai báo

Một cách viết ngắn và an toàn là kế thừa `AnnotationBeanNameGenerator`, chỉ override logic tạo tên mặc định:

```java
package demo.app;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.AnnotationBeanNameGenerator;

public class PrefixBeanNameGenerator extends AnnotationBeanNameGenerator {

    public PrefixBeanNameGenerator() {
    }

    @Override
    protected String buildDefaultBeanName(BeanDefinition definition) {
        return "site_" + super.buildDefaultBeanName(definition);
    }
}
```

Đây là một class **hoàn chỉnh**, dùng trực tiếp trong dự án mẫu mục 7. Phương thức `buildDefaultBeanName(...)` chỉ được gọi khi generator không tìm được tên stereotype tường minh; do đó:

- `@Component class LocalProcessor` → `site_localProcessor`;
- `@Component class URLFormatter` → `site_URLFormatter`;
- `@Service("invoiceWorkflow") class InvoiceService` → **`invoiceWorkflow`**, giữ nguyên explicit name.

Một prefix như `site_` không đủ để giải quyết xung đột giữa **hai class cùng tên ngắn** trong hai package. Cả hai vẫn có thể nhận `site_localProcessor`. Nếu mục tiêu là hỗ trợ đồng thời `demo.catalog.LocalProcessor` và `demo.billing.LocalProcessor`, chọn fully-qualified generator hoặc đưa thêm package identifier vào policy đặt tên.

### 5.1. Khi implement interface từ đầu

Có thể tự implement `BeanNameGenerator` và truy cập `definition.getBeanClassName()`, rồi tạo tên từ class name. Nhưng cách này cần tự xử lý metadata stereotype, bean definition không có class name trực tiếp, naming collision và các quy tắc đặc biệt. Nếu chỉ muốn thay format của **tên mặc định**, subclass `AnnotationBeanNameGenerator` thường ít lỗi hơn.

Nếu vẫn tự implement hoàn toàn, hãy xác định:

1. Tên có được tạo khác nhau cho mọi bean trong registry đang đăng ký không?
2. Explicit stereotype name và custom composed annotation được ưu tiên ra sao?
3. Khi bean definition có factory method hoặc class name chưa resolved, policy xử lý thế nào?
4. Khi rename package/class, hợp đồng về bean name thay đổi ra sao?
5. Có cần tham chiếu `registry.containsBeanDefinition(name)` hay chiến lược uniqueness rõ ràng không?

Không nên âm thầm tự tăng hậu tố `1`, `2` dựa trên thứ tự scan nếu tên bean là hợp đồng ổn định. Nếu có xung đột logic, sửa convention lành mạnh hơn.

## 6. Các kiểu xung đột bean name thường gặp

### 6.1. Hai component có cùng simple class name

`com.acme.sales.ReportService` và `com.acme.audit.ReportService` cùng có `@Service` không đặt tên:

```java
// File: com/acme/sales/ReportService.java
package com.acme.sales;
@Service
public class ReportService { }

// File: com/acme/audit/ReportService.java
package com.acme.audit;
@Service
public class ReportService { }
```

Hai đoạn này minh họa, cần imports. Default generator đều đặt tên `reportService`. Khi scan cả hai vào một registry, Spring thường phát hiện bean definitions không tương thích cùng tên và báo lỗi đăng ký, thường là `ConflictingBeanDefinitionException`. Tùy nguồn đăng ký, cấu hình overriding và thời điểm xử lý, loại lỗi có thể khác; đừng cố dựa vào đúng một message exception.

Cách xử lý:

- đặt tên explicit khác nhau (`@Service("salesReportService")` và `@Service("auditReportService")`);
- hoặc dùng `FullyQualifiedAnnotationBeanNameGenerator`;
- hoặc đổi cấu trúc package/đăng ký có chủ đích để chỉ có một bean phù hợp.

### 6.2. Explicit names trùng nhau

`@Service("sharedService")` trên hai class khác nhau là xung đột dù dùng generator fully-qualified, vì explicit name được giữ. Giải pháp là đổi tên cụ thể theo role hoặc không đăng ký đồng thời hai bean không tương thích.

### 6.3. Hai bean khác tên nhưng cùng kiểu

Đổi tên đã giúp **đăng ký** cả hai bean, nhưng dependency kiểu `ReportService` hoặc interface chung vẫn có thể mơ hồ khi inject một bean đơn. Khi đó cần `@Qualifier`, `@Primary`, collection injection hoặc điều chỉnh thiết kế. Tránh nhầm “xung đột tên bean” với “nhiều ứng viên cùng type”.

### 6.4. Scan trùng và cấu hình registration khác

Một class vừa được quét qua component scanning, vừa được tạo thêm bằng `@Bean` có thể dẫn đến bean trùng kiểu, trùng tên hoặc ghi đè theo chính sách registry. `BeanNameGenerator` trên scanner chỉ xử lý tên cho phần **scanner đăng ký**; không đảm bảo đồng bộ tên với `@Bean`/`@Import`.

### 6.5. Alias và tên chính

Một bean có thể có **alias** để tham chiếu cùng instance dưới tên khác, nhưng một alias không biến object thành bean mới. Ví dụ `@Bean({"primaryWriter", "writerAlias"})` tạo bean với tên chính `primaryWriter` và alias `writerAlias` (khi cấu hình xử lý annotation phù hợp). Khi inject `Map<String, Writer>`, khóa thường là primary bean name, không phải tự thêm mỗi alias như một bean phần tử riêng.

## 7. Dự án Java 17+ chạy được: default, fully qualified và prefix

Dự án dưới đây dùng **Spring Framework 6.2.18**, không cần Spring Boot. Ba `AnnotationConfigApplicationContext` độc lập chứng minh:

1. Default scan một package: tạo tên ngắn `localProcessor`, giữ `URLFormatter` viết hoa và tên explicit `invoiceWorkflow`.
2. Fully-qualified scan hai package: hai class cùng tên ngắn `LocalProcessor` cùng được đăng ký nhưng có **tên đầy đủ khác nhau**.
3. Prefix generator: đổi fallback thành `site_*` nhưng giữ tên explicit.

### 7.1. Cấu trúc

```text
bean-name-generator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── demo/
        ├── app/
        │   ├── BeanNamingDemo.java
        │   └── PrefixBeanNameGenerator.java
        ├── catalog/
        │   ├── CatalogPackage.java
        │   ├── LocalProcessor.java
        │   ├── URLFormatter.java
        │   └── InvoiceService.java
        └── billing/
            ├── BillingPackage.java
            └── LocalProcessor.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'bean-name-generator-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.app.BeanNamingDemo'
}
```

### 7.2. Main và các cấu hình scanner

File `src/main/java/demo/app/BeanNamingDemo.java`:

```java
package demo.app;

import demo.billing.BillingPackage;
import demo.catalog.CatalogPackage;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

public class BeanNamingDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DefaultConfig.class)) {
            System.out.println("== DEFAULT ==");
            System.out.println("localProcessor = " +
                    context.containsBean("localProcessor"));
            System.out.println("URLFormatter = " +
                    context.containsBean("URLFormatter"));
            System.out.println("invoiceWorkflow = " +
                    context.containsBean("invoiceWorkflow"));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(QualifiedConfig.class)) {
            System.out.println("== QUALIFIED ==");
            System.out.println("catalog = " +
                    context.containsBean("demo.catalog.LocalProcessor"));
            System.out.println("billing = " +
                    context.containsBean("demo.billing.LocalProcessor"));
            System.out.println("explicit = " +
                    context.containsBean("invoiceWorkflow"));
            System.out.println("shortName = " +
                    context.containsBean("localProcessor"));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(PrefixConfig.class)) {
            System.out.println("== PREFIX ==");
            System.out.println("prefixed = " +
                    context.containsBean("site_localProcessor"));
            System.out.println("acronym = " +
                    context.containsBean("site_URLFormatter"));
            System.out.println("explicit = " +
                    context.containsBean("invoiceWorkflow"));
        }
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = CatalogPackage.class)
class DefaultConfig {
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackageClasses = {CatalogPackage.class, BillingPackage.class},
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
class QualifiedConfig {
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackageClasses = CatalogPackage.class,
        nameGenerator = PrefixBeanNameGenerator.class
)
class PrefixConfig {
}
```

`DefaultConfig` chỉ quét `demo.catalog`, nên không gặp bean `demo.billing.LocalProcessor` trùng tên ngắn. `QualifiedConfig` quét hai package và sử dụng tên fully-qualified. `PrefixConfig` quét một package để chứng minh hành vi prefix. Ba context riêng biệt không chia sẻ bean registry.

File `src/main/java/demo/app/PrefixBeanNameGenerator.java`:

```java
package demo.app;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.AnnotationBeanNameGenerator;

public class PrefixBeanNameGenerator extends AnnotationBeanNameGenerator {

    public PrefixBeanNameGenerator() {
    }

    @Override
    protected String buildDefaultBeanName(BeanDefinition definition) {
        return "site_" + super.buildDefaultBeanName(definition);
    }
}
```

Public constructor không tham số bảo đảm generator có thể được Spring khởi tạo khi đọc `@ComponentScan`. Subclass chỉ tùy biến fallback name, còn metadata tên explicit vẫn do `AnnotationBeanNameGenerator` xử lý.

### 7.3. Marker classes

File `src/main/java/demo/catalog/CatalogPackage.java`:

```java
package demo.catalog;

public final class CatalogPackage {
    private CatalogPackage() {
    }
}
```

File `src/main/java/demo/billing/BillingPackage.java`:

```java
package demo.billing;

public final class BillingPackage {
    private BillingPackage() {
    }
}
```

Các marker không mang `@Component`, chỉ xác định package root qua `basePackageClasses`.

### 7.4. Components trong package catalog

File `src/main/java/demo/catalog/LocalProcessor.java`:

```java
package demo.catalog;

import org.springframework.stereotype.Component;

@Component
public class LocalProcessor {
    public String id() {
        return "catalog";
    }
}
```

File `src/main/java/demo/catalog/URLFormatter.java`:

```java
package demo.catalog;

import org.springframework.stereotype.Component;

@Component
public class URLFormatter {
    public String format(String value) {
        return "[" + value + "]";
    }
}
```

File `src/main/java/demo/catalog/InvoiceService.java`:

```java
package demo.catalog;

import org.springframework.stereotype.Service;

@Service("invoiceWorkflow")
public class InvoiceService {
    public String name() {
        return "invoice";
    }
}
```

Class `URLFormatter` cố ý bắt đầu bằng hai chữ in hoa để biểu diễn ngoại lệ JavaBeans. `InvoiceService` đặt tên tường minh để kiểm tra generator không đổi tên đã định.

### 7.5. Component trùng tên ngắn ở package billing

File `src/main/java/demo/billing/LocalProcessor.java`:

```java
package demo.billing;

import org.springframework.stereotype.Component;

@Component
public class LocalProcessor {
    public String id() {
        return "billing";
    }
}
```

Hai class `demo.catalog.LocalProcessor` và `demo.billing.LocalProcessor` có tên class ngắn giống nhau nhưng **kiểu Java khác nhau** vì khác package. Java cho phép cả hai tồn tại trên classpath. Bean name mặc định kiểu tên ngắn mới là nguồn xung đột khi quét chung.

### 7.6. Chạy và stdout

Dùng JDK 17+ và một phiên bản Gradle tương thích với JDK:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper thì dùng `./gradlew run --quiet` trên Linux/macOS hoặc `.\gradlew.bat run --quiet` trên Windows PowerShell. Các dòng chương trình in ra:

```text
== DEFAULT ==
localProcessor = true
URLFormatter = true
invoiceWorkflow = true
== QUALIFIED ==
catalog = true
billing = true
explicit = true
shortName = false
== PREFIX ==
prefixed = true
acronym = true
explicit = true
```

**Phân tích:**

- Default: `LocalProcessor` thành `localProcessor`; `URLFormatter` giữ tên `URLFormatter`; `@Service("invoiceWorkflow")` giữ explicit name.
- Qualified: hai `LocalProcessor` được sinh tên `demo.catalog.LocalProcessor` và `demo.billing.LocalProcessor`, không còn tranh cùng `localProcessor`. Tên explicit `invoiceWorkflow` vẫn giữ nguyên.
- Prefix: `LocalProcessor` thành `site_localProcessor` và `URLFormatter` thành `site_URLFormatter`; `InvoiceService` không bị thêm prefix vì có tên stereotype khai báo rõ.
- `containsBean(...)` kiểm tra sự hiện diện của tên bean/alias trong context. Ví dụ dùng các tên không khai báo alias, nên kết quả cũng chứng minh tên được đăng ký.

**Giới hạn của ví dụ:** các class không có dependency phức tạp, để tách riêng hành vi bean naming khỏi vấn đề autowiring. Chương trình không dùng XML, web server, database hoặc repository khác.

## 8. Custom stereotype và `@AliasFor` ảnh hưởng bean name

Một nhóm muốn thay `@Service` bằng stereotype riêng `@UseCase` để thể hiện vai trò use case. Annotation tự định nghĩa có thể meta-annotate `@Component`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface UseCase {
    @AliasFor(annotation = Component.class, attribute = "value")
    String name() default "";
}
```

Đây là **nội dung minh họa file `UseCase.java`**, không phải phần của dự án chạy ở mục 7. Cách sử dụng:

```java
@UseCase(name = "fulfillOrder")
public class FulfillOrderUseCase {
}
```

Khi được scan, tên tường minh là `fulfillOrder`. Nếu không cung cấp `name`, strategy được chọn sẽ sinh fallback name như các component khác.

Từ Spring Framework 6.1, việc custom stereotype ngầm hiểu một thuộc tính `value` theo convention mà không có khai báo alias tường minh đã bị deprecate. Dùng `@AliasFor(annotation = Component.class, attribute = "value")` giúp annotation tùy biến công bố metadata tên rõ ràng.

Khi dùng custom generator kế thừa `AnnotationBeanNameGenerator` như ở mục 5, explicit name của custom stereotype có alias hợp lệ tiếp tục được tôn trọng. Nếu viết `BeanNameGenerator` từ đầu, đừng mặc định rằng tự nhìn `definition.getBeanClassName()` sẽ nhận ra mọi composed stereotype và alias.

## 9. `@Bean`, `@Import` và component scan có quy tắc khác nhau

Điểm quan trọng: không có một quy tắc naming duy nhất áp dụng bất biến cho mọi bean definition.

### 9.1. `@Bean` method

Tên mặc định của một bean do `@Bean` method tạo thường là **tên method**:

```java
@Configuration
class InfraConfig {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }

    @Bean("utcClock")
    Clock configuredClock() {
        return Clock.systemUTC();
    }
}
```

Đây là **đoạn minh họa**, cần imports `java.time.Clock` cùng `@Configuration` và `@Bean`. Bean từ method đầu có tên mặc định `systemClock`; method thứ hai có tên explicit `utcClock`. Thêm `FullyQualifiedAnnotationBeanNameGenerator` vào `@ComponentScan` **không tự đổi** `systemClock` thành tên fully-qualified.

### 9.2. `@Import` class cấu hình

Spring Framework 6.2 có trường hợp sử dụng `FullyQualifiedAnnotationBeanNameGenerator` làm mặc định cho **configuration-level import**. Vì vậy một class được nhập bởi `@Import` có thể mang tên khác với chính class ấy khi được phát hiện bằng scanner mặc định. Cần kiểm tra chính đường đi đăng ký khi mã phụ thuộc vào tên bean.

Không nên đưa tên của import-generated bean thành một string contract nếu framework có API tham chiếu theo type hoặc nếu không có nhu cầu chọn cụ thể tên. Khi gặp cấu hình có cả scan và import, hãy dùng `containsBean`/`getBeanDefinitionNames` để xác minh tên thực trong context.

### 9.3. Đăng ký trực tiếp

Các API như `GenericApplicationContext.registerBean(...)` có chiến lược đặt tên và overload riêng. Nếu caller cung cấp tên, tên đó có thể không liên quan đến `AnnotationBeanNameGenerator` của scanner. Đừng kỳ vọng thay một `@ComponentScan(nameGenerator = ...)` sẽ đổi tất cả bean name do mọi extension point tạo ra.

## 10. Đổi naming policy trong hệ thống đang chạy: tác động cần biết

Đổi naming generator từ tên class ngắn sang fully-qualified là một **thay đổi giao diện cấu hình** khi ứng dụng đang tham chiếu tên bằng string. Các điểm sau có thể bị ảnh hưởng:

| Thành phần sử dụng tên | Ví dụ trước | Ví dụ sau khi đổi sang fully-qualified |
| --- | --- | --- |
| `getBean("localProcessor")` | Lookup thành công | Có thể không tồn tại; cần `getBean("demo.catalog.LocalProcessor")` |
| `@Qualifier("localProcessor")` | Phân giải theo tên mặc định | Có thể cần qualifier tường minh trên bean hoặc cập nhật tên |
| `@Resource(name="localProcessor")` | Chọn bean theo tên | Có thể thất bại nếu không còn alias tương ứng |
| `Map<String, Processor>` | Key `localProcessor` | Key `demo.catalog.LocalProcessor` |
| Logging/monitoring định danh bean | `localProcessor` | `demo.catalog.LocalProcessor` |
| Tên explicit `@Service("invoiceWorkflow")` | `invoiceWorkflow` | Giữ nguyên nếu generator tôn trọng stereotype name |

Đổi generator **không tự tạo alias** cho tên cũ. Nếu tương thích ngược quan trọng, cần xác định rõ tên nào là hợp đồng; cân nhắc đặt explicit names cho bean đang được tham chiếu, hoặc đăng ký alias có kiểm soát thay vì hy vọng Spring hỗ trợ cả hai tên mặc định.

Tương tự, prefix generator làm đổi tên component không khai báo tên. Một tiền tố dễ đọc có thể giúp log hoặc namespace, nhưng không nên coi nó là cách thay cho dependency injection theo type/qualifier.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hai component ở hai package gây `ConflictingBeanDefinitionException` | Trùng simple class name, đều sinh cùng tên ngắn | Đặt explicit names khác nhau hoặc dùng fully-qualified generator |
| `@Component("foo")` vẫn tên `foo` sau khi dùng fully-qualified | Tên tường minh được ưu tiên | Đây là hành vi đúng; thay annotation nếu muốn đổi tên |
| Custom prefix không xử lý hai `LocalProcessor` | Prefix tạo cùng `site_localProcessor` | Dùng package-qualified policy hoặc FQ built-in |
| `URLFormatter` thành `URLFormatter` thay vì `uRLFormatter` | Quy tắc JavaBeans giữ hai ký tự đầu viết hoa | Kiểm tra `Introspector.decapitalize`, không tự lowercase một ký tự |
| `@Bean` method không đổi tên dù đã cấu hình `@ComponentScan(nameGenerator=...)` | Generator chỉ tham gia luồng component scan | Đặt `@Bean(name=...)` hoặc dùng registration policy phù hợp |
| `context.getBean("localProcessor")` không còn tìm thấy | Đã chuyển sang tên fully-qualified hoặc prefix | In bean names thực tế; cập nhật string reference/alias |
| `@Qualifier` bắt đầu lỗi sau đổi tên | Qualifier dựa vào bean name trước đó | Dùng qualifier annotation rõ nghĩa hoặc đồng bộ reference |
| Custom stereotype không dùng được explicit name | Thiếu `@AliasFor` trong composed annotation | Khai báo alias tới `@Component.value` |
| Generator custom bị lỗi khởi tạo | Constructor không tham số không khả dụng, class không load được hoặc exception | Cung cấp public no-arg constructor; kiểm tra classpath |
| Có hai bean type giống nhau dù tên khác | Xung đột ở autowiring, không phải registry naming | Dùng `@Qualifier`/`@Primary` hoặc tiêm collection |
| Mở rộng scan rồi xuất hiện xung đột | Bây giờ có thêm component mang cùng tên ngắn | So sánh package/classes và xem lại chiến lược naming |
| Đặt tên bean theo thứ tự quét | Registry có thể được xử lý theo trình tự thay đổi | Dùng quy tắc xác định được, có test và ổn định khi refactor |
| Spring Boot config kết quả lạ | Thêm `@ComponentScan` đã đổi root/filters hoặc có scan khác | Kiểm tra composition của `@SpringBootApplication` và registry cuối |

**Phân biệt lỗi:** tên bean bị trùng là vấn đề registration; thiếu bean là vấn đề scanning/registration/condition; nhiều bean type là vấn đề dependency resolution. Ba loại lỗi cần những hướng khắc phục khác nhau.

## 12. Kiểm tra bean names bằng code thay vì suy đoán

Một đoạn kiểm tra đơn giản trong ứng dụng đã có `ApplicationContext context`:

```java
String[] names = context.getBeanNamesForType(MyService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
```

Đây là **đoạn minh họa**, cần class `MyService` và biến `context` thực tế. Việc sort mảng giúp output ổn định khi so sánh. Nếu chỉ muốn xem một bean name đã biết:

```java
boolean present = context.containsBean("demo.catalog.LocalProcessor");
```

Khi cần hiểu một bean có alias nào:

```java
String[] aliases = context.getAliases("invoiceWorkflow");
```

Một số hướng kiểm chứng:

1. **Phân biệt context**: Bean ở child context không mặc nhiên nằm trong mọi parent context. Debug đúng context đang thực hiện injection/lookup.
2. **Đối chiếu config thực sự được sử dụng**: `@ComponentScan` với `nameGenerator` phải nằm trên configuration được đăng ký/import.
3. **Quan sát registration path**: Bean được scan, tạo qua `@Bean` hay được đăng ký bằng API khác?
4. **Đọc cả explicit name**: Tên khai báo trong stereotype hoặc custom annotation có alias sẽ thắng fallback name trong các generator built-in.
5. **Kiểm tra package root**: Fully-qualified generator không làm scanner quét rộng hơn; nó chỉ đặt tên các component đã được phát hiện.
6. **Kiểm tra dependency consumer**: Có `@Qualifier("...")` hoặc string lookup hard-code phụ thuộc tên trước đó hay không?

Một unit/integration test tạo `AnnotationConfigApplicationContext` với cấu hình scan nhỏ như mục 7 là cách kiểm chứng hiệu quả. Nếu đổi generator trong ứng dụng hiện hữu, nên có test riêng cho tên bean được xem là giao diện ổn định.

## 13. Bài tập tự thực hành

### Bài tập 1 — Dự đoán tên mặc định

Cho các class trong package `com.acme.sales` mang `@Component` mà không khai báo tên: `TaxService`, `XMLClient`, `ApiGateway`. Dưới `AnnotationBeanNameGenerator`, tên của chúng là gì?

**Đáp án:** `taxService`, `XMLClient`, `apiGateway`. `XMLClient` giữ chữ đầu nguyên dạng vì hai ký tự đầu đều viết hoa.

### Bài tập 2 — Xung đột khi scan hai nhánh

Hai class `com.acme.billing.ReportHandler` và `com.acme.audit.ReportHandler` đều có `@Component` không tên. Scanner mặc định quét cả hai thì có nguy cơ gì?

**Đáp án:** cả hai tên `reportHandler`; Spring có thể báo conflict khi đăng ký hai bean definitions không tương thích. Sử dụng `@Component("billingReportHandler")`/`@Component("auditReportHandler")` hoặc `FullyQualifiedAnnotationBeanNameGenerator`.

### Bài tập 3 — Thay một bean name mà không sửa generator

Dự án dùng `@Service class InvoiceService`, một file khác lookup `"invoiceService"`. Nếu muốn đổi class thành `BillingService` nhưng không đổi lookup, làm thế nào?

**Đáp án:** đặt `@Service("invoiceService")` trên `BillingService` (nếu tên cũ vẫn thể hiện đúng hợp đồng nghiệp vụ) hoặc chủ động cập nhật mọi nơi tham chiếu. Đổi class đơn lẻ làm tên mặc định thay đổi.

### Bài tập 4 — Hai tên explicit giống nhau

Hai class khác package đều khai báo `@Component("sharedProcessor")`. Đổi sang fully-qualified generator có xử lý xung đột không?

**Đáp án:** **Không**. Built-in generator ưu tiên tên tường minh; phải đổi ít nhất một explicit name hoặc chỉ đăng ký các bean có chủ đích.

### Bài tập 5 — Prefix generator và composed stereotype

Class `@UseCase(name="fulfillOrder") FulfillOrderUseCase` dùng custom stereotype đã gắn `@AliasFor`, scanner cấu hình `PrefixBeanNameGenerator`. Bean name nào được chọn?

**Đáp án:** `fulfillOrder`, vì tên tường minh được đọc trước khi gọi fallback `buildDefaultBeanName`. Nếu không khai báo name, generator sẽ dùng `site_fulfillOrderUseCase`.

### Bài tập 6 — FQ name nhưng autowiring vẫn mơ hồ

Hai class implement `Notifier` có tên bean fully-qualified khác nhau. Một constructor inject `Notifier notifier` và container vẫn báo `NoUniqueBeanDefinitionException`. Tại sao?

**Đáp án:** tên đăng ký đã phân biệt, nhưng có hai ứng viên cùng type cho **dependency đơn**. Chọn qua `@Qualifier`, `@Primary` hoặc thiết kế dependency rõ ràng.

### Bài tập 7 — Thay `@Bean` method

`@Configuration` có method `@Bean Clock systemClock()`. Cấu hình `@ComponentScan(nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class)` có tự đổi tên bean `systemClock` không?

**Đáp án:** **Không**. Bean factory method có quy tắc đặt tên riêng; muốn đổi tên, dùng `@Bean("newName")` và rà soát các tham chiếu.

## 14. Checklist cho thiết kế naming policy

Trước khi thay generator trên một dự án:

- Xác định các bean name nào được dùng trong `@Qualifier`, `@Resource`, `getBean(String)`, map keys, config hoặc integration.
- Liệt kê xem những tên đang dựa vào class name ngầm định hay đã được khai báo tường minh.
- Xác định vấn đề: trùng tên ngắn giữa package, nhu cầu namespace hay chỉ muốn tên dễ đọc.
- Cân nhắc `FullyQualifiedAnnotationBeanNameGenerator` trước khi tự viết generator để giải quyết xung đột tên ngắn.
- Nếu viết custom generator, bảo đảm constructor không tham số, naming deterministic và behavior với explicit stereotype names được kiểm tra.
- Kiểm tra những path đăng ký nằm ngoài component scan: `@Bean`, `@Import` và API registration.
- Dùng context test/inspection để xác nhận tên chính, alias, type và kết quả injection trước khi đổi policy trong ứng dụng đang vận hành.

## 15. Ghi nhớ

- **Default component scan:** `AnnotationBeanNameGenerator` sinh tên ngắn theo JavaBeans khi không có explicit stereotype name.
- **Tên tường minh:** `@Component("x")`, `@Service("x")` và stereotype composed có `@AliasFor` thường giữ tên `x` dù đổi built-in generator.
- **Tên class viết tắt:** `URLFormatter` vẫn là `URLFormatter` ở default strategy, không phải `uRLFormatter`.
- **Xung đột package:** hai `LocalProcessor` ở hai package đều thành `localProcessor` dưới default generator; dùng tên tường minh hoặc `FullyQualifiedAnnotationBeanNameGenerator`.
- **Custom generator:** kế thừa `AnnotationBeanNameGenerator` và override `buildDefaultBeanName` nếu chỉ muốn tùy biến fallback.
- **Đúng phạm vi:** `@ComponentScan(nameGenerator=...)` không thay đổi mọi nguồn đăng ký bean và không mở rộng package scan.
- **Tên bean khác lựa chọn bean:** naming giải quyết bean registry identity; qualifier/primary/selection policy giải quyết injection.

### Tài liệu chính thức

- [Spring Framework Reference — Classpath Scanning: Naming Autodetected Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- [Spring Framework 6.2 Javadoc — `BeanNameGenerator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/BeanNameGenerator.html).
- [Spring Framework 6.2 Javadoc — `AnnotationBeanNameGenerator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/AnnotationBeanNameGenerator.html).
- [Spring Framework 6.2 Javadoc — `FullyQualifiedAnnotationBeanNameGenerator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/FullyQualifiedAnnotationBeanNameGenerator.html).
- [Spring Framework 6.2 Javadoc — `@ComponentScan`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ComponentScan.html).
- [Spring Framework — Bean Naming Conventions](https://docs.spring.io/spring-framework/reference/core/beans/definition.html).
