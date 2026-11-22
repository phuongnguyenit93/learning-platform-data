# Component scan, import và auto-configuration là các con đường đăng ký khác nhau

Trong Spring Boot, một bean có thể xuất hiện trong `ApplicationContext` mà bạn không hề gọi `new` trong code nghiệp vụ. Nhưng **không phải mọi bean được tạo bởi cùng một cơ chế**. Có bean được phát hiện bằng cách quét package, có bean được đưa vào qua một cấu hình được import rõ ràng, và có bean được Spring Boot tự động cấu hình dựa trên dependency cùng trạng thái ứng dụng.

Phân biệt **component scanning**, **`@Import`** và **auto-configuration** giúp bạn trả lời những câu hỏi thường gặp: Vì sao thêm `@Service` mà Spring không tìm được bean? Vì sao một thư viện vừa được thêm vào classpath lại có thêm `DataSource` hoặc HTTP client bean? Vì sao loại trừ auto-configuration nhưng controller vẫn được scan? Vì sao người dùng có thể tự khai báo bean để thay thế mặc định do Spring Boot cung cấp?

Bài học thuộc chương **Đăng ký bean**, tập trung vào cách **bean definition đi vào container**. Sau khi được đăng ký, Spring mới tiến hành giải quyết dependency, tạo instance và quản lý vòng đời theo scope và cấu hình tương ứng.

## 1. Đăng ký bean không đồng nghĩa với khởi tạo object ngay lập tức

Một **bean definition** là metadata để container biết một bean có thể được tạo như thế nào: tên, kiểu, factory/constructor, scope, lazy mode, điều kiện và các thông tin liên quan. Từ bean definition, Spring tạo instance khi thích hợp.

```text
Nguồn khai báo                Kết quả trong container             Khi sử dụng
-------------------          ------------------------             ------------
@Component / @Service ──┐
@Configuration/@Bean ───┤──> Bean definition ──> Bean instance/proxy ──> Caller
@Import ────────────────┤       (metadata)            (theo scope)
Auto-configuration ─────┘
```

Hình trên minh họa **nhiều con đường đưa definition vào cùng một container**. Một bean có thể được đưa vào bằng các cơ chế lồng nhau: chẳng hạn component scan tìm được lớp `@Configuration`, sau đó phương thức `@Bean` của lớp ấy khai báo thêm bean. Không nên coi các con đường là ba hệ thống độc lập.

Đừng nhầm việc **có definition** với **đã có instance**. Singleton mặc định thường được khởi tạo khi context được refresh; bean lazy có thể bị trì hoãn; prototype tạo instance mới khi được yêu cầu; bean request/session có vòng đời riêng.

## 2. Ba con đường chính khác nhau ở đâu?

| Cơ chế | Ai quyết định nơi tìm? | Dữ liệu đầu vào chính | Cách sử dụng tiêu biểu |
|---|---|---|---|
| **Component scan** | Bạn hoặc cấu hình ứng dụng chỉ định **package cần quét**. | Class trong package với `@Component` và các stereotype liên quan, cùng filter scan. | Tìm controller, service, repository và cấu hình thuộc ứng dụng. |
| **`@Import`** | Một lớp cấu hình chỉ định **class/configuration cần đưa vào**. | Các class được liệt kê trực tiếp, hoặc selector/registrar xác định động. | Ghép module cấu hình, bật một integration, dùng cấu hình ngoài phạm vi scan. |
| **Auto-configuration của Spring Boot** | Cơ chế Boot tìm **danh sách auto-configuration do các JAR cung cấp**, rồi áp điều kiện. | Metadata auto-configuration, classpath, bean đang có, property, loại ứng dụng... | Thiết lập mặc định cho web, data, messaging, observability và các thư viện tích hợp. |

**Cả ba cuối cùng đều dẫn tới việc đăng ký bean definitions** khi đủ điều kiện; điểm khác là **cách chúng được phát hiện và quyết định áp dụng**.

- Component scan: “Tìm component trong những package này.”
- `@Import`: “Đưa cấu hình/class này vào quá trình xử lý cấu hình.”
- Auto-configuration: “Xét các cấu hình được Boot liệt kê từ dependency, chỉ áp dụng khi điều kiện phù hợp.”

`@Bean` là cách khai báo bean trong một lớp cấu hình; nó **không phải cách tìm lớp cấu hình ban đầu**. Một `@Bean` chỉ phát huy tác dụng nếu lớp cấu hình chứa nó được nạp vào context qua scan, `@Import`, auto-configuration hoặc con đường đăng ký tương đương.

## 3. Bắt đầu từ một ứng dụng Spring Boot tối thiểu

Giả sử mã nguồn có package gốc `com.example.shop`:

```text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── api/
    ├── service/
    └── config/
```

Lớp chính:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp ba phần quan trọng:

1. **`@SpringBootConfiguration`**: đánh dấu cấu hình Spring Boot (dựa trên cấu hình Spring).
2. **`@EnableAutoConfiguration`**: yêu cầu Spring Boot xem xét các auto-configuration phù hợp.
3. **`@ComponentScan`**: tìm component trong package gốc và các package con theo mặc định.

Chỉ một annotation trên lớp main nên dễ làm người mới nghĩ Spring có **một** cơ chế phát hiện bean. Thực tế, trong quá trình khởi động có nhiều bước xử lý cấu hình phối hợp.

Một ứng dụng có thể dùng component scan nhưng tắt một auto-configuration cụ thể. Một thư viện có thể dùng `@Import` mà hoàn toàn không cần được component scan trong package ứng dụng. Đây là lý do phải đọc **nguồn đăng ký** khi chẩn đoán.

## 4. Con đường thứ nhất: component scanning

### 4.1. Spring tìm component nào?

Ví dụ service của ứng dụng:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long total(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

Nếu cấu hình scan bao phủ `com.example.shop.service`, lớp này được phát hiện là ứng viên component và bean definition của nó được đăng ký.

Các annotation phổ biến:

| Annotation | Vai trò thường gặp | Liên quan component scan |
|---|---|---|
| `@Component` | Component chung | Trực tiếp là ứng viên scan. |
| `@Service` | Tầng logic nghiệp vụ | Stereotype được meta-annotate từ `@Component`. |
| `@Repository` | Tầng persistence/data access | Stereotype component, có thể có tích hợp chuyển đổi exception. |
| `@Controller` | Controller web | Stereotype component. |
| `@RestController` | Controller trả response body | Bao gồm ngữ nghĩa controller và response body. |
| `@Configuration` | Lớp cấu hình bean | Có thể được phát hiện qua scan rồi xử lý các `@Bean`. |

**Không phải chỉ có annotation có chữ “Component” mới được scan.** Stereotype và annotation tùy biến có meta-annotation phù hợp cũng có thể được nhận diện. Tuy nhiên, có annotation trên lớp **không đủ** nếu lớp ở ngoài phạm vi scan hoặc bị filter/condition loại bỏ.

### 4.2. Phạm vi scan mặc định

Trong ví dụ `ShopApplication` đặt ở `com.example.shop`, các package con như `com.example.shop.service` và `com.example.shop.api` thường được quét.

Ngược lại:

```text
com.example.shop.ShopApplication         # Root package
com.example.shop.service.PriceService    # Trong phạm vi mặc định
com.example.shared.ExternalService       # Ngoài phạm vi mặc định
```

`ExternalService` không được scan chỉ vì cả hai class cùng tồn tại trên classpath.

Có thể định cấu hình phạm vi scan một cách có chủ đích:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.shop",
        "com.example.shared"
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Tuy nhiên, mở rộng scan sang package của thư viện quá rộng có thể đăng ký những thành phần không mong muốn. Thông thường, giữ lớp main ở package gốc hợp lý và sử dụng cơ chế cấu hình của thư viện sẽ đơn giản hơn.

**Chú ý:** `scanBasePackages` của `@SpringBootApplication` tác động tới **component scan**, không mặc nhiên thay đổi package được dùng cho mọi cơ chế như JPA entity/repository scanning. Những cơ chế đó có annotation và quy tắc riêng, chẳng hạn `@EntityScan` hoặc `@EnableJpaRepositories` khi cần tinh chỉnh.

### 4.3. Component scan và `@Bean` phối hợp

```java
package com.example.shop.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Nếu `TimeConfiguration` nằm trong package được scan, Spring phát hiện **lớp cấu hình**, sau đó xử lý phương thức `appClock()` để đăng ký một **bean `Clock`**. Bản thân `java.time.Clock` không có `@Component` và cũng không được scan.

```text
component scan
      │
      ▼
TimeConfiguration được phát hiện
      │
      ▼
Xử lý @Bean appClock()
      │
      ▼
Clock bean definition
      │
      ▼
Clock instance khi cần
```

Điều này cho thấy việc “bean được đăng ký qua component scan” đôi khi là cách nói tắt; **bean `Clock` được khai báo qua `@Bean`, còn lớp chứa định nghĩa ấy được tìm bằng scan**.

### 4.4. Filter giúp chọn hoặc loại component

`@ComponentScan` hỗ trợ `includeFilters` và `excludeFilters`. Ví dụ có thể loại một lớp ra khỏi scan:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.stereotype.Service;

@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ExperimentalService.class
    )
)
class ScanConfiguration { }
```

Đoạn trên giả định có lớp `ExperimentalService`. Filter chỉ ảnh hưởng đến **quá trình scan cụ thể**; nếu một configuration khác chủ động import/đăng ký chính lớp ấy, không nên kỳ vọng filter scan sẽ chặn mọi con đường đăng ký.

## 5. Con đường thứ hai: `@Import`

`@Import` là annotation của **Spring Framework** dùng để đưa các class/cấu hình khác vào quá trình xử lý configuration. Khác với scan, nó không yêu cầu Spring tự duyệt tất cả class trong một package rồi lọc bằng stereotype.

Ví dụ bạn muốn dùng một thành phần nằm **ngoài package scan của ứng dụng**:

```java
package com.acme.billing;

public interface InvoiceFormatter {
    String format(long amount);
}
```

```java
package com.acme.billing;

public class SimpleInvoiceFormatter implements InvoiceFormatter {
    @Override
    public String format(long amount) {
        return "Amount: " + amount;
    }
}
```

Thư viện cung cấp một configuration:

```java
package com.acme.billing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BillingConfiguration {

    @Bean
    public InvoiceFormatter invoiceFormatter() {
        return new SimpleInvoiceFormatter();
    }
}
```

Ứng dụng chủ động import:

```java
package com.example.shop;

import com.acme.billing.BillingConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(BillingConfiguration.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Dù `BillingConfiguration` nằm ở `com.acme.billing`, bên ngoài `com.example.shop`, Spring vẫn xử lý nó qua `@Import`. Bean `InvoiceFormatter` được khai báo từ method `@Bean` và có thể inject vào service/controller.

**Ở đây `@Import` đưa vào một configuration class; nó không đồng nghĩa với import package Java.** Dòng `import com.acme.billing.BillingConfiguration;` phía trên chỉ là cú pháp Java để tham chiếu kiểu. Annotation `@Import(BillingConfiguration.class)` mới yêu cầu Spring đăng ký/xử lý cấu hình.

### 5.1. Có thể import component class trực tiếp?

Có. `@Import` có thể nhận các class component thông thường ngoài `@Configuration`. Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Import(ExternalCalculator.class)
public class CalculatorFeatureConfiguration { }
```

Giả định `ExternalCalculator` là class có thể được tạo bởi container và đã có dependency phù hợp. Spring có thể đăng ký nó như một bean từ quá trình import ngay cả khi class không nằm trong package scan.

Dùng import trực tiếp **có chủ đích và minh bạch**, nhưng nếu module cần nhiều bean, cấu hình riêng với `@Bean` hoặc một annotation `@Enable...` thường giúp người dùng hiểu cách tích hợp hơn.

### 5.2. Import một tập cấu hình

```java
@Configuration(proxyBeanMethods = false)
@Import({
    BillingConfiguration.class,
    ReportConfiguration.class
})
public class BusinessFeatureConfiguration { }
```

Cách này thích hợp khi bạn muốn nhóm các cấu hình có quan hệ thành **một điểm kích hoạt rõ ràng**, không mở rộng component scan sang toàn bộ package thư viện.

Ví dụ một annotation tùy biến:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(BillingConfiguration.class)
public @interface EnableBilling { }
```

Sau đó:

```java
@SpringBootApplication
@EnableBilling
public class ShopApplication { /* main() */ }
```

Khi `@EnableBilling` được xử lý như một composed annotation, `BillingConfiguration` được import. Đây là cách nhiều annotation kích hoạt tính năng trong hệ sinh thái Spring hoạt động: đằng sau tên ngắn gọn có thể là `@Import` cùng các class hỗ trợ.

### 5.3. `ImportSelector` và `ImportBeanDefinitionRegistrar`

`@Import` còn có thể nhận:

- **`ImportSelector`**: chọn tên các class configuration để import dựa trên metadata và ngữ cảnh.
- **`DeferredImportSelector`**: một dạng selector cho phép trì hoãn lựa chọn import trong quá trình xử lý configuration.
- **`ImportBeanDefinitionRegistrar`**: đăng ký bean definitions theo chương trình thông qua registry.

Những extension point này phù hợp với framework, starter và thư viện hạ tầng hơn ứng dụng mới học. Chúng giải thích vì sao bạn có thể thấy bean được thêm vào dù source không có một `@Import(SomeConfiguration.class)` trực tiếp.

**Auto-configuration của Spring Boot cũng có cơ chế lựa chọn và import cấu hình**, nhưng việc lựa chọn từ metadata của các JAR cùng kiểm tra điều kiện thuộc tầng Boot; đó là khác biệt quan trọng với một `@Import` do ứng dụng chủ động khai báo.

## 6. Con đường thứ ba: Spring Boot auto-configuration

Spring Boot muốn ứng dụng có cấu hình hợp lý với những thư viện đã chọn. Ví dụ khi classpath có công nghệ web phù hợp, Boot có thể cung cấp web-server-related configuration; khi có thư viện persistence và cấu hình datasource phù hợp, Boot có thể cấu hình thành phần truy cập dữ liệu.

Việc này được thực hiện qua **auto-configuration classes**, là các lớp cấu hình được Boot phát hiện qua metadata và áp dụng theo điều kiện.

Một lớp main điển hình đã bật cơ chế này qua `@SpringBootApplication`, vì annotation đó bao gồm `@EnableAutoConfiguration`.

### 6.1. Auto-configuration được tìm ở đâu?

Trong Spring Boot **2.7 trở lên**, các JAR có thể cung cấp danh sách auto-configuration qua tệp:

```text
META-INF/spring/
└── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng trong file chứa **tên lớp đủ package** của một auto-configuration class. Ví dụ:

```text
com.acme.clock.autoconfigure.ClockAutoConfiguration
```

Ở các thế hệ Boot **2.6 trở về trước**, danh sách auto-configuration được khai báo theo cơ chế `EnableAutoConfiguration` trong `META-INF/spring.factories`. Boot 2.7 là giai đoạn chuyển tiếp hỗ trợ format `AutoConfiguration.imports`; với Boot 3.x và các dòng mới hơn, không nên đăng ký auto-configuration theo key cũ trong `spring.factories` như thể đây là cơ chế chính hiện hành.

Đây là **metadata riêng cho auto-configuration**, khác với việc component scan duyệt package của ứng dụng. Auto-configuration class thường nằm trong JAR thư viện hoặc starter đi cùng; Spring Boot đọc danh sách cấu hình và cân nhắc điều kiện trước/sau khi đưa các bean definitions vào context.

### 6.2. Boot kiểm tra những điều kiện gì?

Những annotation phổ biến:

| Điều kiện | Ý nghĩa khái quát |
|---|---|
| `@ConditionalOnClass` | Chỉ áp dụng cấu hình khi class cụ thể có trên classpath. |
| `@ConditionalOnMissingClass` | Chỉ áp dụng khi class được chỉ định không có trên classpath. |
| `@ConditionalOnBean` | Chỉ áp dụng khi đã có bean phù hợp tại thời điểm đánh giá điều kiện. |
| `@ConditionalOnMissingBean` | Đăng ký mặc định nếu chưa có bean phù hợp tại thời điểm xét. |
| `@ConditionalOnProperty` | Xét property, giá trị và tùy chọn hành vi khi property chưa được thiết lập. |
| `@ConditionalOnWebApplication` | Chỉ áp dụng trong web application context thích hợp. |
| `@ConditionalOnResource` | Xét sự hiện diện của tài nguyên được chỉ định. |

Không phải điều kiện nào cũng chỉ nhìn classpath. **Mỗi auto-configuration có thể cần nhiều điều kiện cùng đúng** và điều kiện có thể đặt ở cấp class hoặc method `@Bean`.

Một lớp thuộc thư viện có mặt trên classpath **không đảm bảo mọi bean auto-config được tạo**. Boot có thể không nạp cấu hình vì thiếu class khác, property vô hiệu hóa tính năng, một bean do người dùng cung cấp đã tồn tại hoặc context không thuộc loại thích hợp.

### 6.3. Auto-configuration “nhường chỗ” cho cấu hình người dùng

Một đặc điểm quan trọng của Spring Boot là auto-configuration thường đưa ra **default có điều kiện**, chẳng hạn chỉ đăng ký bean khi ứng dụng chưa có implementation phù hợp. Annotation `@ConditionalOnMissingBean` là cơ chế phổ biến cho hành vi này.

Ví dụ ý tưởng:

```text
Ứng dụng có tự cung cấp Clock bean?
          │
       ┌──┴───┐
       │      │
      Có     Không
       │      │
       ▼      ▼
 Dùng bean   Auto-config tạo
 người dùng  Clock mặc định
```

Điều này khác với việc nói “Spring Boot luôn ghi đè cấu hình”. Thông thường Boot cố gắng **back off** khi người dùng đã tự cấu hình đúng kiểu bean. Nhưng quy tắc cụ thể phải đọc từ annotation của từng auto-configuration; **không phải mọi auto-configuration đều có `@ConditionalOnMissingBean`**.

## 7. Ví dụ: tạo auto-configuration nhỏ cho một thư viện

Để thấy rõ sự khác biệt, giả sử bạn viết thư viện cung cấp bean `java.time.Clock` mặc định cho ứng dụng khác. Ví dụ này dùng mô hình dành cho **Spring Boot 3.x/4.x**, trong đó auto-configuration được đăng ký qua `AutoConfiguration.imports`.

Thư viện có package nằm **ngoài phạm vi component scan** của ứng dụng sử dụng:

```text
clock-integration/
├── src/main/java/com/acme/clock/autoconfigure/
│   └── ClockAutoConfiguration.java
└── src/main/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports

shop-app/
└── src/main/java/com/example/shop/
    └── ShopApplication.java
```

Ở module thư viện, file `ClockAutoConfiguration.java`:

```java
package com.acme.clock.autoconfigure;

import java.time.Clock;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.clock",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock defaultClock() {
        return Clock.systemUTC();
    }
}
```

Nội dung file metadata:

```text
com.acme.clock.autoconfigure.ClockAutoConfiguration
```

Tệp phải được đóng gói đúng đường dẫn `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` **bên trong JAR thư viện**. Một khai báo auto-configuration trong file này được Boot nhận diện thông qua cơ chế auto-configuration, **không cần thêm `@Component` hoặc `@Import` trên ứng dụng sử dụng**.

Ứng dụng `shop-app` chỉ cần đưa JAR thư viện có metadata và dependency phù hợp vào runtime classpath; lớp `ShopApplication` vẫn như phần 3.

Nếu property `demo.clock.enabled` không được thiết lập, `matchIfMissing=true` cho phép cấu hình được xét như đang bật. Nếu chưa có `Clock` bean, Boot đăng ký bean từ method `defaultClock()`. Nếu property là `false`, điều kiện cấu hình không thỏa và bean mặc định đó không được đăng ký.

Ứng dụng có thể chủ động khai báo `Clock` khác:

```java
package com.example.shop.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppTimeConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Khi Spring Boot đánh giá auto-configuration và nhìn thấy bean `Clock` người dùng đã cung cấp, `@ConditionalOnMissingBean(Clock.class)` làm mặc định **không được đăng ký**. Đây là hành vi thường được gọi là **back-off**.

**Lưu ý quan trọng về thứ tự:** Điều kiện dựa trên bean như `@ConditionalOnMissingBean` phụ thuộc vào những bean definitions đã được xử lý tại thời điểm đánh giá. Auto-configuration được thiết kế để chạy sau cấu hình người dùng trong quy trình phù hợp; không nên tùy tiện dùng annotation này trong mọi component configuration và kỳ vọng nó luôn nhìn thấy tất cả bean sẽ được đăng ký về sau.

### Tránh một lỗi phổ biến khi tự viết auto-configuration

**Không đặt auto-configuration class vào package bị ứng dụng component scan**, không thêm `@Component` hoặc cách import trực tiếp không cần thiết vào cấu hình đã được đăng ký qua `AutoConfiguration.imports`. Nếu bạn đưa cùng cấu hình vào context bằng hai đường khác nhau, bạn có thể làm khó việc suy luận điều kiện và thứ tự, thậm chí dẫn đến registration conflict tùy trường hợp.

Một starter thư viện thường đóng vai trò đưa các dependency cần thiết vào classpath. **Metadata auto-configuration** thường nằm trong module auto-config của thư viện. Hai artifact có thể tách riêng hoặc nằm cùng một JAR tùy thiết kế; không có quy tắc mọi starter tự chứa mọi lớp cấu hình.

## 8. Component scan, `@Import` và auto-configuration trong cùng ứng dụng

Hãy tưởng tượng một ứng dụng có:

- `ProductController` và `ProductService` của team, nằm dưới `com.example.shop`, có stereotype.
- `BillingConfiguration` của thư viện nghiệp vụ, được kích hoạt bằng `@Import(BillingConfiguration.class)`.
- `ClockAutoConfiguration` nằm trong JAR integration, được liệt kê trong `AutoConfiguration.imports`.

Khi Spring Boot xây dựng context:

```text
ShopApplication (@SpringBootApplication)
               │
               ├─ Component scan package com.example.shop
               │       ├─ ProductController definition
               │       └─ ProductService definition
               │
               ├─ @Import(BillingConfiguration.class)
               │       └─ @Bean InvoiceFormatter definition
               │
               └─ Enable auto-configuration
                       ├─ Đọc danh sách auto-config từ classpath
                       ├─ Kiểm tra conditions
                       └─ @Bean Clock mặc định (nếu đủ điều kiện)
                                         │
                                         ▼
                               ApplicationContext
                                         │
                                         ▼
                        Resolve dependencies, create beans
```

Các nhánh chỉ để diễn đạt **nguồn cấu hình**, không nhằm khẳng định một thứ tự thực thi cứng giữa mọi bước. Spring xử lý configuration classes qua nhiều phase, selector và điều kiện; bean definition đến từ scan, import hoặc auto-configuration cuối cùng đều được container xử lý chung.

Một service có thể inject bean từ bất kỳ nhánh nào miễn các định nghĩa phù hợp hiện diện trong context:

```java
@Service
public class ReceiptService {
    private final InvoiceFormatter formatter;
    private final Clock clock;

    public ReceiptService(InvoiceFormatter formatter, Clock clock) {
        this.formatter = formatter;
        this.clock = clock;
    }

    public String createReceipt(long amount) {
        return formatter.format(amount) + " @ " + clock.instant();
    }
}
```

Ví dụ trên giả định các kiểu `InvoiceFormatter` và `Clock` đã được import và có bean phù hợp. **Code sử dụng bean không cần biết bean đến từ scan, import hay auto-configuration**; container cung cấp dependency theo type/qualifier và những quy tắc resolution tương ứng.

## 9. `@Import` không phải auto-configuration

`@Import` và auto-configuration liên quan nhưng **không đồng nghĩa**.

Với import rõ ràng:

```java
@Import(BillingConfiguration.class)
```

Người viết cấu hình chỉ định **chính xác** lớp cần xử lý. Spring không cần tìm lớp này bằng quy tắc scanning package. Các annotation điều kiện bên trong cấu hình được import vẫn có thể quyết định bean nào được đăng ký.

Với auto-configuration của Spring Boot:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.acme.clock.autoconfigure.ClockAutoConfiguration
```

Ứng dụng không cần biết trực tiếp tên của `ClockAutoConfiguration`. Boot khám phá nó từ metadata trên classpath, đưa nó vào tập auto-configuration ứng viên, áp các điều kiện và sắp xếp theo quy tắc phù hợp.

Nói cách khác, **auto-configuration tận dụng hạ tầng import cấu hình của Spring**, nhưng thêm một lớp **khám phá tự động, thứ tự auto-configuration và các convention điều kiện** của Spring Boot. Không nên coi đó chỉ là `@Import` viết ở chỗ khác.

### `@ImportAutoConfiguration` dùng khi nào?

Spring Boot có `@ImportAutoConfiguration` để nhập chọn lọc một số auto-configuration trong các ngữ cảnh đặc biệt, chẳng hạn cấu hình test slice hoặc tình huống cần kiểm soát phạm vi. Nó khác `@Import` thông thường ở chỗ thiết kế dành cho các auto-configuration class.

Đối với ứng dụng Spring Boot thông thường, không nên thêm `@ImportAutoConfiguration` cho mọi starter. Cơ chế auto-configuration mặc định thường đã xử lý việc phát hiện các cấu hình thích hợp.

## 10. Loại trừ auto-configuration không có nghĩa tắt component scan

Có thể loại một auto-configuration của Spring Boot theo một cách rõ ràng:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Ví dụ này giả định đang dùng dòng Boot trong đó lớp `DataSourceAutoConfiguration` có tên/package như trên. Khi làm việc với dòng Boot khác, cần đối chiếu tên class tương ứng từ tài liệu của phiên bản đích.

Cách khác là cấu hình property `spring.autoconfigure.exclude` bằng danh sách tên lớp auto-configuration. Việc loại trừ chỉ **ngăn cơ chế auto-configuration áp dụng cấu hình được chỉ định**, không xóa bean do application component scan hoặc `@Bean` của người dùng tự khai báo.

Ví dụ:

- Bạn loại trừ Boot auto-configuration cho datasource.
- Một `@Configuration` tự viết vẫn có `@Bean DataSource`.
- Container vẫn có thể đăng ký datasource do người dùng khai báo.

Điều đó không mâu thuẫn: hai definition có **nguồn đăng ký khác nhau**.

Ngược lại, nếu bạn loại một package khỏi component scan, bean đi qua `@Import` hoặc auto-configuration vẫn có thể xuất hiện nếu không bị điều kiện khác chặn.

## 11. `@ComponentScan` và auto-configuration không luôn quét cùng phạm vi

Một misconception thường gặp là: “Có dependency trong `build.gradle` và lớp `@Service` trong JAR thì Spring Boot tự scan mọi package trong JAR đó.”

Không đúng theo mặc định. **Component scan có phạm vi package** bắt đầu từ ứng dụng hoặc cấu hình bạn khai báo; JAR chỉ đơn giản là một phần của classpath. Nếu service trong JAR nằm ngoài package scan và không được cấu hình riêng, nó có thể không trở thành bean.

Trong khi đó, **auto-configuration** dựa trên danh sách metadata và cơ chế Boot, không dựa vào việc quét tất cả stereotype trong JAR.

Một thư viện tốt có thể cung cấp:

```text
library.jar
├── com/acme/api/...                       # API công khai
├── com/acme/internal/...                  # Implementation
├── com/acme/autoconfigure/MyAutoConfiguration.class
└── META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Khi dependency có mặt, Boot có thể xét `MyAutoConfiguration` ngay cả khi package `com.acme` nằm ngoài scan mặc định của ứng dụng.

**Kết luận thao tác:** Thêm `scanBasePackages = "com"` để “Spring tìm thấy mọi thư viện” là phương án quá rộng. Nó có thể khiến nhiều component nội bộ từ các JAR khác nhau được đăng ký ngoài ý muốn. Hãy kiểm tra thư viện có starter, auto-configuration hoặc annotation `@Enable...` được hỗ trợ hay không.

## 12. Vai trò của dependency: có class chưa chắc có bean

Dòng khai báo Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
}
```

thường đưa vào các module để hỗ trợ JDBC cùng những integration liên quan, nhưng không nên suy luận rằng ở mọi môi trường sẽ có một datasource kết nối thành công.

Cần phân biệt ba mức:

1. **Artifact có trên classpath**: kết quả resolve dependency của Gradle/Maven.
2. **Auto-configuration là ứng viên**: Boot tìm thấy tên cấu hình trong metadata.
3. **Bean thực sự được đăng ký và có thể khởi tạo**: điều kiện của cấu hình thỏa và dependency có thể resolve.

Có trường hợp Boot đăng ký bean definition nhưng việc tạo bean thất bại vì thiếu thông tin kết nối hoặc điều kiện runtime khác. Vì vậy, nhìn thấy auto-configuration được chọn cũng không đảm bảo tất cả kết nối bên ngoài đã sẵn sàng.

Điều tương tự xảy ra với web, messaging, security và persistence. Starter là **đầu vào của classpath**; Spring Boot còn phải quyết định cách sử dụng classpath cùng bean/property đã có.

## 13. Cách chẩn đoán: bean xuất hiện từ đâu?

Khi một bean không có hoặc xuất hiện ngoài ý muốn, hãy xác định **nguồn đăng ký** trước.

### 13.1. Đọc thông báo lỗi và lớp gốc

Các lỗi thường thấy:

| Triệu chứng | Kiểm tra trước |
|---|---|
| `NoSuchBeanDefinitionException` | Class có được scan? `@Import` đã kích hoạt? Auto-configuration có được phát hiện và có đủ điều kiện không? |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type đến từ scan, config và auto-config? Có cần qualifier/primary không? |
| `BeanCreationException` | Bean đã đăng ký nhưng constructor, factory method, config hoặc dependency bị lỗi? |
| Auto-configuration không hoạt động | Có metadata `AutoConfiguration.imports`? Classpath phù hợp? Điều kiện class/bean/property/web có thỏa không? |
| Bean của thư viện không được scan | Package có nằm trong phạm vi scan? Thư viện có cơ chế `@Import` hoặc starter/auto-config không? |
| Một bean mặc định biến mất sau khi thêm `@Bean` | `@ConditionalOnMissingBean` đã khiến auto-config back off? |
| Annotation `@Service` không có tác dụng | Lớp có thuộc package scan? Bean có bị condition/profile/filter loại? |

### 13.2. Dùng conditions evaluation report

Trong môi trường phát triển, chạy ứng dụng với tham số:

```bash
java -jar app.jar --debug
```

hoặc đặt:

```properties
debug=true
```

Spring Boot có thể in **conditions evaluation report**, phân loại các cấu hình được áp dụng và không được áp dụng với lý do. Tên và hình thức log có thể khác theo phiên bản.

Report này đặc biệt hữu ích khi điều tra auto-configuration: thiếu một class, property không khớp, bean đã tồn tại, hoặc ứng dụng không thuộc loại web phù hợp. Nó **không thay thế** việc đọc lỗi gốc ở stack trace.

### 13.3. Xem bean definitions từ `ApplicationContext`

Trong ứng dụng thử nghiệm, có thể hỏi container xem bean đã đăng ký chưa:

```java
package com.example.shop;

import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.ConfigurableApplicationContext;

@Configuration(proxyBeanMethods = false)
public class BeanInspectorConfiguration {

    @Bean
    ApplicationRunner inspectBeans(ConfigurableApplicationContext context) {
        return args -> {
            ConfigurableListableBeanFactory factory =
                    context.getBeanFactory();

            for (String name : context.getBeanDefinitionNames()) {
                if (!factory.containsBeanDefinition(name)) {
                    continue;
                }
                var definition = factory.getBeanDefinition(name);
                if (name.contains("clock") || name.contains("Clock")) {
                    System.out.printf(
                            "%s -> %s%n",
                            name,
                            definition.getResourceDescription()
                    );
                }
            }
        };
    }
}
```

Ví dụ này có chủ đích giới hạn việc in theo tên `clock/Clock`; nguồn `resourceDescription` **không phải lúc nào cũng có giá trị** hoặc đủ để xác định duy nhất vì bean definition có thể được đăng ký theo nhiều cách. Nó chỉ là manh mối. Để điều tra sâu, xem `factoryBeanName`, `factoryMethodName`, `beanClassName`, condition report và metadata cấu hình liên quan.

Ở môi trường có Spring Boot Actuator, endpoint quản trị `/actuator/beans` và `/actuator/conditions` cũng có thể giúp quan sát các bean/điều kiện nếu dependency, cấu hình exposure và quyền truy cập cho phép. **Không công khai các endpoint quản trị ra internet chỉ để debug.**

### 13.4. Kiểm tra dependency graph

Một artifact không có trên runtime classpath thì auto-configuration trong artifact đó không thể được phát hiện.

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree
```

So sánh thư viện trực tiếp, dependency transitive, version và exclusion. Nhớ rằng tên artifact/starter có thể khác nhau theo dòng Spring Boot.

## 14. Trình tự khởi động: có scan trước rồi import sau không?

Không nên mô tả startup bằng một lịch trình cứng kiểu “quét hết mọi bean, rồi mới import, sau đó mới auto-config tất cả”. Spring xử lý configuration classes, import selectors, conditional registration và bean factory post-processing qua nhiều giai đoạn, và một cấu hình được scan có thể tiếp tục khai báo `@Import` hoặc `@Bean`.

Điều cần nắm ở cấp kiến thức cơ bản:

```text
SpringApplication.run(...)
       │
       ▼
Chuẩn bị Environment và ApplicationContext
       │
       ▼
Đọc cấu hình gốc + xử lý scan/import/auto-configuration
       │
       ▼
Tập hợp và xử lý bean definitions
       │
       ▼
Resolve dependency, tạo singleton phù hợp, callback lifecycle
       │
       ▼
Ứng dụng sẵn sàng phục vụ theo kiểu runtime tương ứng
```

**Thứ tự giữa các auto-configuration** có thể tác động đến điều kiện phụ thuộc bean definitions. Spring Boot hỗ trợ metadata ordering như `@AutoConfiguration(before = ...)`, `after = ...` hoặc `@AutoConfigureBefore`/`@AutoConfigureAfter` theo dòng phiên bản. Điều này nhằm kiểm soát **thứ tự xử lý cấu hình**, không đảm bảo thứ tự tạo tất cả bean hoặc thứ tự thực thi mọi business method.

Đối với developer ứng dụng, lựa chọn thường là:

- Đăng ký bean cụ thể của ứng dụng bằng component scan/`@Bean`.
- Bật integration có chủ đích bằng `@Import` hoặc annotation của thư viện.
- Để Boot cung cấp default qua auto-configuration khi điều kiện phù hợp.
- Override bằng bean người dùng nếu auto-configuration hỗ trợ back-off, thay vì can thiệp vào thứ tự xử lý không cần thiết.

## 15. Ví dụ phân biệt lỗi qua ba tình huống

### Tình huống A: `@Service` nằm ngoài scan

```text
com.example.shop.ShopApplication         # Package gốc
com.vendor.payment.PaymentService       # @Service, ngoài package gốc
```

`PaymentService` có annotation hợp lệ, nhưng component scan mặc định của `com.example.shop` không tìm thấy nó.

**Cách giải quyết:** nếu là class của chính ứng dụng, tổ chức lại package hoặc điều chỉnh scan có chủ đích. Nếu là thư viện, xem integration bằng configuration/`@Import`/auto-configuration được nhà cung cấp hỗ trợ. Không mở rộng scan toàn bộ classpath chỉ để giải quyết một bean.

### Tình huống B: `@Import` chưa được kích hoạt

Bạn có `BillingConfiguration` trong một module khác nhưng không dùng annotation tích hợp, `@Import` hoặc cơ chế nạp cấu hình nào. Vì nằm ngoài scan, class này chỉ là class có trên classpath.

**Cách giải quyết:** import cấu hình được thư viện công bố, chẳng hạn:

```java
@Import(BillingConfiguration.class)
```

hoặc dùng `@EnableBilling` nếu thư viện cung cấp. Việc chỉ viết `import com.acme.billing.BillingConfiguration;` ở đầu file Java **không tạo bean definition**.

### Tình huống C: Auto-configuration được phát hiện nhưng không tạo bean

`ClockAutoConfiguration` có trong `AutoConfiguration.imports`, nhưng ứng dụng đã có bean `Clock` của riêng mình. Với `@ConditionalOnMissingBean(Clock.class)`, Boot không đăng ký `defaultClock()`.

**Cách giải quyết:** đây có thể là kết quả **mong muốn**. Kiểm tra bean nào đang được inject. Nếu vẫn cần hai `Clock` khác nhau, phải thiết kế tên/qualifier rõ ràng và điều chỉnh điều kiện tương ứng. Đừng bỏ điều kiện một cách ngẫu nhiên để tạo thêm bean rồi gặp lỗi ambiguity.

## 16. Khi nào chọn cách đăng ký nào?

| Bối cảnh | Hướng tiếp cận phù hợp | Lý do |
|---|---|---|
| Service/controller của ứng dụng trong package gốc | `@Service`/`@RestController` qua component scan | Đơn giản, theo convention và dễ tìm code. |
| Đối tượng từ JDK/thư viện cần cấu hình constructor | `@Bean` trong `@Configuration` được nạp vào context | Kiểm soát rõ factory method, không phải sửa source thư viện. |
| Tập cấu hình cần người dùng chủ động bật | `@Import` hoặc annotation `@Enable...` đóng gói `@Import` | Không tự scan toàn bộ thư viện, dễ nhìn tính năng nào đã bật. |
| Viết thư viện Spring Boot muốn có cấu hình mặc định theo dependency | `@AutoConfiguration` + `AutoConfiguration.imports` + conditions | Hợp lý cho integration dùng lại trong nhiều ứng dụng. |
| Ứng dụng muốn thay default do Boot tạo | Khai báo bean riêng, đọc điều kiện back-off | Giữ cơ chế cấu hình theo convention khi được hỗ trợ. |
| Cần tắt một auto-configuration cụ thể | `exclude` hoặc `spring.autoconfigure.exclude` | Kiểm soát đúng nguồn auto-configuration thay vì tắt component scan. |

**Quy tắc thực tế:** code thuộc ứng dụng thường được đăng ký bằng stereotype/`@Bean`; thư viện muốn explicit opt-in có thể dùng `@Import`; integration Spring Boot muốn tự hoạt động khi dependency xuất hiện thường dùng auto-configuration. Đây là định hướng, không phải luật bắt buộc: có thể có nhiều thiết kế hợp lệ tùy yêu cầu.

## 17. Bài tập thực hành

### Bài tập 1 — Kiểm tra phạm vi component scan

1. Tạo `ShopApplication` tại package `com.example.shop`.
2. Đăng ký `@Service` trong `com.example.shop.service` và inject vào một runner/controller.
3. Tạo thêm `@Service` trong package độc lập ngoài phạm vi scan.
4. Quan sát khác biệt, sau đó chỉ mở rộng scan có chủ đích để kiểm tra dự đoán.

### Bài tập 2 — Import cấu hình ngoài package

1. Tạo `BillingConfiguration` với `@Bean InvoiceFormatter` trong package `com.acme.billing`.
2. Không import cấu hình và thử inject `InvoiceFormatter`: quan sát lỗi thiếu bean.
3. Thêm `@Import(BillingConfiguration.class)` vào lớp main.
4. Khởi chạy lại và kiểm tra bean được giải quyết.

Hãy giải thích vì sao **chỉ import class theo cú pháp Java** không đủ.

### Bài tập 3 — Auto-configuration có back-off

1. Tạo module integration `ClockAutoConfiguration` và file `AutoConfiguration.imports` như phần 7.
2. Thêm module này vào runtime classpath của ứng dụng.
3. Quan sát `Clock` bean được đăng ký khi chưa có bean khác.
4. Tạo `@Bean Clock businessClock()` và quan sát auto-configuration mặc định back off.
5. Thử đặt `demo.clock.enabled=false` và quan sát tác động của condition.

Khi đánh giá kết quả, xem cả conditions report; chỉ nhìn bean count không đủ giải thích mọi trường hợp.

### Bài tập 4 — Chẩn đoán trước khi sửa

Với một ứng dụng có controller, bean `Clock` tự khai báo và một starter database, trả lời:

- Controller đến từ component scan hay auto-configuration?
- `Clock` do `@Bean` của ứng dụng hay Boot đăng ký?
- Những auto-configuration database nào đã được xem xét và điều kiện nào không đạt?
- Nếu loại trừ datasource auto-configuration, controller có còn được đăng ký không? Vì sao?

### Bài tập 5 — Vẽ lại đường đăng ký

Chọn ba bean thực tế trong project. Với mỗi bean, xác định **class cấu hình hoặc component**, **đường đưa definition vào container**, **điều kiện đăng ký nếu có** và **dependency cần resolve**. Không cần suy diễn thứ tự tạo bean chỉ từ sơ đồ.

## 18. Ghi nhớ

- **Component scanning** tìm các class component trong phạm vi package và filter được cấu hình; đây thường là nơi bắt đầu của bean ứng dụng.
- **`@Import`** đưa trực tiếp các class/configuration vào quá trình xử lý, giúp kết nối module rõ ràng mà không cần quét rộng.
- **Spring Boot auto-configuration** tìm cấu hình được liệt kê trong metadata của JAR, rồi áp dụng conditions để cung cấp những mặc định phù hợp.
- **`@Bean` khai báo bean, không phải quy tắc tự tìm lớp configuration.** Lớp chứa method phải được nạp bằng một trong các con đường đăng ký.
- **Có artifact trên classpath không đồng nghĩa có bean.** Phải đi qua cơ chế discovery, conditional registration và bước tạo bean.
- **Các đường đăng ký có thể phối hợp.** Một bean được inject theo type/qualifier bất kể nó đến từ scan, import hay auto-configuration.

Khi không thấy một bean, hãy lần theo chuỗi **“definition đến từ đâu → cấu hình đã được nạp chưa → điều kiện có thỏa không → dependency đã resolve chưa → instance có tạo thành công không”**. Đó là cách phân biệt lỗi đăng ký bean với lỗi khởi tạo bean trong Spring Boot.
