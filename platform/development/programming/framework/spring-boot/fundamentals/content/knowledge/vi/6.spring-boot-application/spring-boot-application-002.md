# @SpringBootConfiguration trong mối liên hệ với @Configuration

Trong ứng dụng Spring Boot, lớp khởi động thường được đánh dấu bằng `@SpringBootApplication`:

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

Nhìn vào annotation này, người mới học thường chú ý tới component scanning và auto-configuration, nhưng bên trong nó còn có một thành phần nền tảng: **`@SpringBootConfiguration`**. Annotation này lại được xây dựng dựa trên **`@Configuration` của Spring Framework**.

Mối quan hệ đó giải thích vì sao lớp `ShopApplication` có thể khai báo phương thức `@Bean`, vì sao Spring Boot nhận diện đâu là cấu hình gốc của ứng dụng, và tại sao một số bài test cần tìm được `@SpringBootConfiguration`.

Bài học này thuộc chương **`@SpringBootApplication`** của **Spring Boot Fundamentals**. Trọng tâm là hiểu đúng vai trò của `@SpringBootConfiguration` so với `@Configuration`: những gì chúng chia sẻ, những gì Spring Boot bổ sung, và tình huống nên dùng mỗi annotation.

## 1. Bức tranh tổng thể: ba tầng annotation

Trước tiên, hãy xem quan hệ meta-annotation:

```text
@SpringBootApplication
    │
    ├── @SpringBootConfiguration
    │       │
    │       └── @Configuration
    │               │
    │               └── @Component (ở mức meta-annotation)
    │
    ├── @EnableAutoConfiguration
    │
    └── @ComponentScan
```

Sơ đồ chỉ thể hiện các thành phần quan trọng đối với bài học, không liệt kê mọi metadata hay alias của annotation.

Trong Spring, một annotation có thể được **đánh dấu bởi annotation khác**. Khi `@SpringBootApplication` được gắn lên một lớp, các annotation tạo thành nó cung cấp metadata để Spring xử lý.

Đọc từ dưới lên:

- **`@Configuration`**: đánh dấu lớp là nguồn định nghĩa bean của Spring, thường thông qua phương thức `@Bean`.
- **`@SpringBootConfiguration`**: là biến thể chuyên biệt của `@Configuration` nhằm đánh dấu **cấu hình ứng dụng Spring Boot**.
- **`@SpringBootApplication`**: gồm `@SpringBootConfiguration` cộng với các khả năng quan trọng khác, đặc biệt là kích hoạt auto-configuration và component scanning.

Nói cách khác, `@SpringBootConfiguration` **có khả năng cấu hình bean như `@Configuration`**, đồng thời mang ý nghĩa nhận diện riêng cho Spring Boot. Tuy nhiên, **chỉ sử dụng `@SpringBootConfiguration` không tự động bật component scanning hoặc auto-configuration** như `@SpringBootApplication`.

### 1.1. Meta-annotation không phải kế thừa lớp Java

Đây là quan hệ annotation composition, không phải:

```java
class SpringBootConfiguration extends Configuration { ... }
```

`@SpringBootConfiguration` và `@Configuration` đều là các annotation type. Quan hệ nằm ở việc annotation này có annotation kia trên phần khai báo của chính nó.

Có thể hình dung cách khai báo cốt lõi như sau:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Configuration
public @interface SpringBootConfiguration {
    // Các thuộc tính/metadata khác được lược bớt.
}
```

Đây là mã **minh họa ý tưởng**, không phải bản sao đầy đủ của source Spring Boot. Điều quan trọng là `@Configuration` xuất hiện trên định nghĩa `@SpringBootConfiguration`; Spring có cơ chế đọc metadata tổng hợp và xử lý lớp được gắn annotation ở tầng cao hơn.

## 2. `@Configuration` là gì?

`@Configuration` thuộc **Spring Framework**, nằm trong package:

```java
import org.springframework.context.annotation.Configuration;
```

Annotation này đánh dấu một lớp chứa các khai báo cấu hình Spring, thường là các phương thức `@Bean` trả về đối tượng cần được quản lý trong `ApplicationContext`.

Ví dụ:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    public DiscountPolicy discountPolicy() {
        return new PercentageDiscountPolicy(10);
    }
}
```

Giả sử `DiscountPolicy` là interface và `PercentageDiscountPolicy` là implementation phù hợp. Khi Spring xử lý `PricingConfiguration`, phương thức `discountPolicy()` cung cấp định nghĩa bean cho container. Theo phạm vi mặc định, bean này là **singleton trong một ApplicationContext**.

Ứng dụng có thể lấy bean bằng dependency injection:

```java
package com.example.shop.service;

import com.example.shop.config.DiscountPolicy;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final DiscountPolicy discountPolicy;

    public CheckoutService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }
}
```

Trong ví dụ này, Spring container tạo và cung cấp bean `DiscountPolicy`. `@Configuration` không yêu cầu lớp phải chứa phương thức `main`, và một ứng dụng có thể có **nhiều** lớp `@Configuration` để tách các nhóm cấu hình.

### 2.1. `@Bean` và `@Configuration` giữ hai vai trò khác nhau

- `@Configuration` đặt trên **lớp cấu hình**, nói cho Spring biết lớp này cung cấp bean definitions.
- `@Bean` đặt trên **phương thức factory**, nói cho Spring biết đối tượng do phương thức trả về cần được đăng ký và quản lý như một bean.

Ví dụ:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

Khi code có constructor:

```java
public ReportService(Clock applicationClock) {
    this.applicationClock = applicationClock;
}
```

Spring có thể inject `Clock` nếu bean đó đã được đưa vào cùng `ApplicationContext`.

Annotation `@Configuration` tự nó **không chạy mã Java tùy ý** chỉ vì class có tồn tại trong classpath. Lớp cấu hình phải được Spring phát hiện hoặc đăng ký: qua component scanning, `@Import`, chỉ định làm nguồn khi khởi tạo context, hoặc một cơ chế đăng ký configuration tương ứng.

### 2.2. `@Configuration` cũng là một dạng component

`@Configuration` được meta-annotate bằng `@Component`. Do đó, trong một ứng dụng có component scanning phù hợp, Spring có thể tìm thấy lớp cấu hình như một candidate component.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java              (@SpringBootApplication)
├── config/
│   └── PricingConfiguration.java     (@Configuration)
└── service/
    └── CheckoutService.java          (@Service)
```

Khi `ShopApplication` ở package `com.example.shop`, component scan mặc định do `@SpringBootApplication` kích hoạt thường bao phủ `com.example.shop` và các package con. Khi đó `PricingConfiguration` được tìm và các phương thức `@Bean` của nó được xử lý.

Điều cần phân biệt:

- `@Configuration` là một **ứng viên được phát hiện nhờ scan**.
- `@ComponentScan` là annotation **bật/chỉ định việc quét package**.
- Hai annotation này không có cùng chức năng.

Vì thế, nếu một lớp chỉ có `@Configuration` nhưng không nằm trong vùng scan và cũng không được import hoặc đăng ký bằng cách khác, các `@Bean` bên trong có thể không được tạo trong application context.

## 3. `@SpringBootConfiguration` là gì?

`@SpringBootConfiguration` thuộc **Spring Boot**, nằm trong package:

```java
import org.springframework.boot.SpringBootConfiguration;
```

Nó là một annotation chuyên biệt mang ý nghĩa: **lớp này cung cấp cấu hình cấp ứng dụng Spring Boot**.

Về khả năng định nghĩa bean, nó hành xử như `@Configuration` do được meta-annotate bằng `@Configuration`. Điểm bổ sung là **dấu mốc nhận diện**: các thành phần của Spring Boot, đặc biệt trong hỗ trợ kiểm thử, có thể tìm một lớp cấu hình được đánh dấu `@SpringBootConfiguration` làm điểm bắt đầu cho ứng dụng.

Một cách hình dung:

```text
@Configuration
    └── "Đây là lớp cấu hình bean của Spring."

@SpringBootConfiguration
    ├── "Đây là lớp cấu hình bean của Spring."
    └── "Đây là lớp cấu hình ứng dụng Spring Boot."
```

Ý nghĩa thứ hai là lý do Spring Boot cung cấp annotation này dù Spring Framework đã có `@Configuration`.

### 3.1. Ví dụ sử dụng trực tiếp

Có thể khai báo:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

Cấu hình trên có thể cung cấp bean `Clock` cho Spring context. Nhưng nó **không mặc nhiên có các khả năng mà người dùng thường kỳ vọng khi thấy `@SpringBootApplication`**, chẳng hạn quét các lớp `@Service` trong package con hay bật auto-configuration dành cho web/data.

Nếu chỉ thay:

```java
@SpringBootApplication
```

bằng:

```java
@SpringBootConfiguration
```

trong một ứng dụng web hiện có, rất có thể controller không được phát hiện, DataSource không được auto-configure hoặc web server không được thiết lập theo cách trước đó. Đó là vì đã bỏ bớt hai thành phần quan trọng: `@ComponentScan` và `@EnableAutoConfiguration`.

### 3.2. Không phải mọi `@Configuration` đều cần đổi thành `@SpringBootConfiguration`

Trong một ứng dụng, thường có nhiều lớp cấu hình:

```text
com.example.shop
├── ShopApplication.java            (@SpringBootApplication)
└── config/
    ├── SecurityConfiguration.java  (@Configuration)
    ├── CacheConfiguration.java     (@Configuration)
    └── SchedulingConfiguration.java (@Configuration)
```

Các lớp `SecurityConfiguration`, `CacheConfiguration` và `SchedulingConfiguration` là cấu hình thành phần. Chúng **không cần** `@SpringBootConfiguration` để đăng ký `@Bean`.

Thông thường, dấu mốc `@SpringBootConfiguration` xuất hiện một lần, gián tiếp qua lớp `@SpringBootApplication` đại diện cho cấu hình ứng dụng chính. Điều này cũng giúp Spring Boot test bootstrap xác định một điểm cấu hình gốc rõ ràng.

### 3.3. Điều mà `@SpringBootConfiguration` không tự bổ sung

Bản thân `@SpringBootConfiguration`:

- Không phải một lệnh khởi chạy: JVM vẫn cần `main` hoặc cách bootstrap khác.
- Không tự bật `@ComponentScan`.
- Không tự kích hoạt `@EnableAutoConfiguration`.
- Không tự tạo web controller, web server, repository hoặc database connection.
- Không thay thế dependency của Spring Boot starter.
- Không yêu cầu mọi bean phải đặt cùng lớp.
- Không tự động làm các bean ở package khác xuất hiện nếu chúng chưa được phát hiện/đăng ký.

Khác biệt chủ đạo với `@Configuration` là **metadata nhận diện dành cho Boot**, không phải một hệ thống dependency injection mới.

## 4. `@SpringBootApplication` ghép các khả năng lại như thế nào?

Lớp main điển hình:

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

`@SpringBootApplication` là annotation tổng hợp, trong đó ba thành phần quan trọng là:

| Thành phần | Đóng góp |
|---|---|
| `@SpringBootConfiguration` | Đánh dấu đây là cấu hình ứng dụng Boot; mang chức năng của `@Configuration` |
| `@EnableAutoConfiguration` | Yêu cầu Spring Boot đánh giá các cấu hình tự động theo classpath, properties, beans và điều kiện |
| `@ComponentScan` | Cho phép tìm components trong package được quét: `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration`… |

Một lớp có `@SpringBootApplication` vì vậy **đồng thời có vai trò của một lớp cấu hình Spring** và là điểm vào thuận tiện để bắt đầu ứng dụng Boot.

Bạn có thể khai báo `@Bean` ngay trên lớp main:

```java
@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Với ví dụ này cần import `org.springframework.context.annotation.Bean` và `java.time.Clock`. Bean `Clock` được đăng ký vì `@SpringBootApplication` mang `@SpringBootConfiguration` và do đó mang semantics của `@Configuration`.

Tuy nhiên, nếu số lượng bean tùy chỉnh lớn, nên tách chúng thành các lớp `@Configuration` theo từng nhóm chức năng, thay vì đặt mọi phương thức `@Bean` vào lớp main.

### 4.1. Đặt lớp main tại package gốc

Cấu trúc nên dùng:

```text
com.example.shop
├── ShopApplication.java            (@SpringBootApplication)
├── controller/
│   └── ProductController.java      (@RestController)
├── service/
│   └── ProductService.java         (@Service)
└── config/
    └── PricingConfiguration.java   (@Configuration)
```

Mặc định, component scan từ `@SpringBootApplication` bắt đầu từ package chứa lớp ứng dụng và các package con. Đặt `ShopApplication` tại `com.example.shop` giúp tìm được controller, service và các configuration component bên dưới.

Nếu đặt main vào:

```text
com.example.shop.boot.ShopApplication
```

mà controller lại nằm ở:

```text
com.example.shop.controller.ProductController
```

thì controller là **package anh em**, không nằm bên dưới `com.example.shop.boot`. Component scan mặc định có thể bỏ sót nó. Khi đó có thể thay đổi vị trí main hoặc cấu hình vùng scan rõ ràng.

Lưu ý: **đây là vai trò của `@ComponentScan` trong `@SpringBootApplication`**, không phải hành vi riêng do `@SpringBootConfiguration` cung cấp.

### 4.2. Auto-configuration không phải chức năng của `@SpringBootConfiguration`

Spring Boot auto-configuration thường dựa trên starter dependencies và các điều kiện, ví dụ có/không có lớp nhất định, có/không có bean tự khai báo, hoặc giá trị properties.

Khi dependency cho Spring MVC phù hợp có trên classpath, auto-configuration có thể thiết lập những bean nền tảng cần thiết cho ứng dụng web, tùy môi trường và cấu hình.

Nếu một ứng dụng chỉ gắn `@SpringBootConfiguration`, đừng suy luận rằng nó tự động cấu hình web server chỉ vì được khởi chạy bằng `SpringApplication.run(...)`. Với cấu hình cơ bản, việc chọn nguồn configuration và auto-configuration là hai mối quan tâm khác nhau.

### 4.3. Kết hợp thủ công ba annotation: khi nào cần?

Trong tình huống học tập hoặc cần kiểm soát chi tiết, có thể khai báo rõ từng thành phần:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(basePackages = "com.example.shop")
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Cách này minh họa các vai trò cơ bản tương ứng với `@SpringBootApplication`. Tuy nhiên `@SpringBootApplication` thật còn mang một số cấu hình mặc định, bộ lọc scan và alias thuộc tính; vì vậy **không nên coi đoạn tổ hợp tối giản này giống hệt mọi chi tiết triển khai** của `@SpringBootApplication`.

Với dự án thông thường, `@SpringBootApplication` rõ ràng và dễ duy trì hơn. Chỉ tách các annotation khi có lý do thực tế và hiểu những gì đang tùy biến.

## 5. Bảng so sánh ba annotation

| Tiêu chí | `@Configuration` | `@SpringBootConfiguration` | `@SpringBootApplication` |
|---|---|---|---|
| Thuộc framework | Spring Framework | Spring Boot | Spring Boot |
| Là nguồn định nghĩa bean `@Bean` | Có | Có, thông qua `@Configuration` | Có, thông qua `@SpringBootConfiguration` |
| Mang marker cấu hình ứng dụng Boot | Không | Có | Có |
| Tự kích hoạt component scanning | Không | Không | Có |
| Tự kích hoạt auto-configuration | Không | Không | Có |
| Có thể dùng cho lớp cấu hình phụ | Phổ biến | Thường không cần | Thường không nên |
| Thường dùng cho lớp main của ứng dụng Boot | Chỉ khi có cấu hình bootstrap riêng | Có thể, trong trường hợp đặc biệt | Phổ biến nhất |
| Được Spring Boot test bootstrap nhận diện như cấu hình Boot gốc | Không chỉ vì có `@Configuration` | Có | Có |
| Có thể cấu hình `proxyBeanMethods` | Có | Có, chuyển tiếp tới `@Configuration` | Có, chuyển tiếp qua `@SpringBootConfiguration` |

Một cách nhớ:

```text
@Configuration
    = định nghĩa cấu hình bean

@SpringBootConfiguration
    = @Configuration + marker cấu hình ứng dụng Boot

@SpringBootApplication
    = marker cấu hình Boot + auto-configuration + component scanning
```

Không nên đọc bảng theo kiểu “annotation bên phải luôn tốt hơn”. Mỗi annotation có phạm vi sử dụng. Một lớp `@Configuration` phục vụ riêng cache, security hoặc mapping vẫn hoàn toàn đúng trong ứng dụng dùng `@SpringBootApplication`.

## 6. `proxyBeanMethods` liên hệ giữa các annotation

Một phần quan trọng thường bị bỏ qua là thuộc tính **`proxyBeanMethods`**.

Vì `@SpringBootConfiguration` dựa trên `@Configuration`, nó cũng cho phép điều khiển hành vi proxy các phương thức `@Bean`. `@SpringBootApplication` cũng phơi bày thuộc tính này để áp dụng cho phần cấu hình tương ứng.

Ở các phiên bản Spring Boot thông dụng, mặc định của `proxyBeanMethods` là `true`. Khi được bật trong lớp configuration đầy đủ, Spring có thể tạo proxy lớp cấu hình để lời gọi trực tiếp giữa các phương thức `@Bean` tuân theo lifecycle/scope của bean do container quản lý.

### 6.1. Ví dụ phụ thuộc giữa hai bean

Giả sử có hai lớp Java đơn giản:

```java
public class MailClient {
    public void send(String message) {
        System.out.println(message);
    }
}
```

```java
public class ReportService {
    private final MailClient mailClient;

    public ReportService(MailClient mailClient) {
        this.mailClient = mailClient;
    }
}
```

Cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReportingConfiguration {

    @Bean
    public MailClient mailClient() {
        return new MailClient();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(mailClient());
    }
}
```

Trong trường hợp `@Configuration` mặc định có `proxyBeanMethods = true`, Spring sử dụng cơ chế tăng cường lớp cấu hình để khi `reportService()` gọi `mailClient()`, lời gọi đó có thể được chặn và trả về bean `MailClient` đã được container quản lý, tuân theo scope và semantics của bean.

Nếu thay:

```java
@Configuration(proxyBeanMethods = false)
```

thì lời gọi `mailClient()` bên trong `reportService()` là lời gọi Java trực tiếp, có thể tạo một **đối tượng `MailClient` mới**, ngoài instance singleton đã được Spring đăng ký riêng cho bean `mailClient`. Đây là khác biệt về identity và lifecycle, không chỉ về hiệu năng.

### 6.2. Viết cấu hình không cần lời gọi trực tiếp giữa các `@Bean`

Cách thường dễ hiểu hơn là để Spring inject bean qua tham số phương thức:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingConfiguration {

    @Bean
    public MailClient mailClient() {
        return new MailClient();
    }

    @Bean
    public ReportService reportService(MailClient mailClient) {
        return new ReportService(mailClient);
    }
}
```

Khi tạo `ReportService`, Spring resolve tham số `MailClient` từ container. Cách này không phụ thuộc việc gọi trực tiếp phương thức `mailClient()` trên đối tượng configuration.

Đây là mẫu phù hợp khi các `@Bean` độc lập hoặc liên hệ với nhau qua dependency injection do Spring thực hiện. Khi đó `proxyBeanMethods = false` có thể giảm nhu cầu proxy hóa configuration class.

**`proxyBeanMethods = false` không tắt `@Bean`, không tắt dependency injection và không biến lớp cấu hình thành một class Java không được quản lý.** Nó chủ yếu tác động đến việc chặn lời gọi phương thức `@Bean` giữa các method trên đối tượng cấu hình.

### 6.3. Thuộc tính này trên `@SpringBootConfiguration` và `@SpringBootApplication`

Có thể viết:

```java
@SpringBootConfiguration(proxyBeanMethods = false)
public class ApplicationConfiguration {
    // Các @Bean độc lập hoặc nhận phụ thuộc qua tham số.
}
```

Hoặc trên lớp main phổ biến:

```java
@SpringBootApplication(proxyBeanMethods = false)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Thuộc tính của `@SpringBootApplication` chuyển tiếp tới phần cấu hình gốc của annotation tổng hợp. Khi cấu hình này không khai báo phương thức `@Bean` cần gọi lẫn nhau, tắt proxy có thể phù hợp.

Việc đặt `proxyBeanMethods = false` trên **lớp main** không có nghĩa mọi lớp `@Configuration` khác trong dự án đều tự động đổi sang `false`. Mỗi lớp cấu hình cần được hiểu theo khai báo và cách Spring xử lý riêng.

Đừng thay đổi cờ này theo thói quen khi chưa biết liệu cấu hình có lời gọi giữa các phương thức `@Bean` hay không.

## 7. Vì sao Spring Boot Test cần nhận diện `@SpringBootConfiguration`?

Đây là điểm khác biệt thực tế quan trọng nhất giữa `@SpringBootConfiguration` và `@Configuration`.

Khi viết một integration test kiểu:

```java
package com.example.shop.service;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProductServiceIntegrationTest {

    @Test
    void contextLoads() {
        // Nếu context không khởi động được, test này thất bại.
    }
}
```

và **không** truyền lớp cấu hình rõ ràng cho `@SpringBootTest`, cơ chế bootstrap test của Spring Boot có thể tìm lên cấu trúc package của test để xác định lớp được đánh dấu `@SpringBootConfiguration`. Một lớp `@SpringBootApplication` cũng thỏa mãn điều kiện vì mang marker này.

Ví dụ bố cục hợp lý:

```text
src/main/java/
└── com/example/shop/
    └── ShopApplication.java        (@SpringBootApplication)

src/test/java/
└── com/example/shop/
    └── service/
        └── ProductServiceIntegrationTest.java (@SpringBootTest)
```

Test đặt trong `com.example.shop.service` có thể tìm lên package cha `com.example.shop` và nhận `ShopApplication` làm cấu hình Boot gốc.

### 7.1. Khi chỉ có `@Configuration` thì sao?

Giả sử lớp main được thiết kế theo một bootstrap tùy biến:

```java
@Configuration
public class CustomApplicationConfig {
    // ...
}
```

Nếu test chỉ viết:

```java
@SpringBootTest
class CustomIntegrationTest {
}
```

thì việc trong project có `@Configuration` **không đủ** để bảo đảm Spring Boot tự nhận ra nó là cấu hình gốc qua cơ chế tìm `@SpringBootConfiguration`.

Trong trường hợp đó, có thể:

- Cung cấp rõ lớp cấu hình mà test cần, chẳng hạn `@SpringBootTest(classes = CustomApplicationConfig.class)`, nếu phù hợp với cách bootstrap mong muốn.
- Sử dụng một lớp main với `@SpringBootApplication` trong cấu trúc package thích hợp.
- Dùng `@SpringBootConfiguration` khi bạn thực sự đang định nghĩa cấu hình gốc riêng cho ứng dụng Boot.

Ví dụ chỉ định nguồn test:

```java
package com.example.shop.service;

import com.example.shop.config.CustomApplicationConfig;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(classes = CustomApplicationConfig.class)
class CustomIntegrationTest {

    @Test
    void contextLoads() {
    }
}
```

Điều này không có nghĩa chỉ cần ghi `classes` thì tự xuất hiện mọi auto-configuration hay component. Nội dung context còn phụ thuộc các annotation và cấu hình của lớp được chọn.

### 7.2. Lỗi thường gặp: không tìm thấy cấu hình Spring Boot

Một lỗi bootstrap test có thể mang ý nghĩa tương tự:

```text
Unable to find a @SpringBootConfiguration.
You need to use @ContextConfiguration or @SpringBootTest(classes=...)
with your test.
```

Các nguyên nhân có thể gồm:

- Test nằm trong package không cùng nhánh với lớp main.
- Ứng dụng chỉ có `@Configuration`, không có nguồn `@SpringBootConfiguration` có thể tìm tự động.
- Cấu trúc project/module khiến cấu hình ứng dụng không có trên test classpath.
- Test cần một context riêng nhưng chưa chỉ định source configuration.

Hướng xử lý là xác định cấu hình mà test phải dùng, không phải gắn `@SpringBootConfiguration` lên mọi lớp `@Configuration` để “cho Spring tìm thấy”.

### 7.3. Vì sao không nên có nhiều marker gốc?

Nếu nhiều lớp được gắn `@SpringBootConfiguration` trong cùng phạm vi mà test bootstrap xem là ứng viên, quá trình tìm cấu hình gốc có thể trở nên mơ hồ hoặc báo rằng có nhiều cấu hình được tìm thấy.

Bố cục không nên dùng trong một ứng dụng đơn giản:

```text
com.example.shop
├── ShopApplication.java       (@SpringBootApplication)
└── config/
    └── CacheConfiguration.java (@SpringBootConfiguration)  <-- không cần thiết
```

`CacheConfiguration` chỉ cần `@Configuration`. Nó có thể được phát hiện bằng component scan hoặc đăng ký theo cách phù hợp. Không có lợi ích thông thường khi dùng `@SpringBootConfiguration` cho mọi cấu hình phụ.

Trong các hệ thống nhiều ứng dụng, nhiều module hoặc test suite phức tạp, có thể tồn tại nhiều Boot application hợp lệ. Khi ấy cần bố trí package/test bootstrap cẩn thận hoặc chỉ định `classes` rõ ràng, thay vì suy luận rằng cả hệ thống chỉ được có một marker.

### 7.4. Phân biệt `@TestConfiguration` với marker cấu hình gốc

Spring Boot còn cung cấp `@TestConfiguration` để tạo configuration bổ sung dành cho test. Ví dụ:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfiguration {

    @Bean
    public Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2030-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Có thể import lớp này vào test khi cần:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(FixedClockTestConfiguration.class)
class ClockIntegrationTest {

    @Test
    void contextLoads() {
    }
}
```

`@TestConfiguration` phục vụ việc bổ sung bean hoặc tùy biến context trong test. Nó **không thay thế vai trò xác định cấu hình ứng dụng chính** của `@SpringBootConfiguration`. Nếu context vốn có bean `Clock` khác, test còn cần giải quyết vấn đề nhiều bean cùng type, ví dụ bằng qualifier hoặc `@Primary` theo tình huống; không giả định thêm một bean mới luôn ghi đè bean cũ.

## 8. Một ví dụ hoàn chỉnh: lớp main và lớp cấu hình phụ

Hãy xem cách tổ chức một dự án Spring Boot nhỏ:

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── config/
│   └── GreetingConfiguration.java
├── service/
│   ├── GreetingFormatter.java
│   ├── DefaultGreetingFormatter.java
│   └── GreetingService.java
└── web/
    └── GreetingController.java
```

### 8.1. Lớp cấu hình gốc

`ShopApplication.java`:

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

Class này là nguồn `@SpringBootConfiguration` thông qua `@SpringBootApplication`, đồng thời bật component scan và auto-configuration.

### 8.2. Định nghĩa các kiểu cần dùng

`service/GreetingFormatter.java`:

```java
package com.example.shop.service;

public interface GreetingFormatter {
    String format(String name);
}
```

`service/DefaultGreetingFormatter.java`:

```java
package com.example.shop.service;

public class DefaultGreetingFormatter implements GreetingFormatter {

    private final String prefix;

    public DefaultGreetingFormatter(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String format(String name) {
        return prefix + ", " + name + "!";
    }
}
```

Chúng là các kiểu Java thông thường, chưa tự động trở thành Spring bean chỉ vì nằm trong classpath.

### 8.3. Cấu hình bean phụ bằng `@Configuration`

`config/GreetingConfiguration.java`:

```java
package com.example.shop.config;

import com.example.shop.service.DefaultGreetingFormatter;
import com.example.shop.service.GreetingFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    public GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter("Xin chào");
    }
}
```

Không cần `@SpringBootConfiguration` cho lớp này. `@Configuration` đủ để đánh dấu nguồn cung cấp bean `GreetingFormatter`.

### 8.4. Service nhận dependency qua constructor

`service/GreetingService.java`:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

### 8.5. Controller dùng service

`web/GreetingController.java`:

```java
package com.example.shop.web;

import com.example.shop.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "Spring Boot") String name
    ) {
        return greetingService.greet(name);
    }
}
```

Với project có `spring-boot-starter-web` và ứng dụng chạy cổng mặc định, có thể gọi:

```text
GET http://localhost:8080/greeting?name=Lan
```

Kết quả:

```text
Xin chào, Lan!
```

Luồng hình thành ứng dụng:

```text
ShopApplication (@SpringBootApplication)
    │
    ├── @SpringBootConfiguration
    │       └── xác định cấu hình gốc Spring Boot
    │
    ├── @ComponentScan
    │       ├── phát hiện GreetingConfiguration (@Configuration)
    │       ├── phát hiện GreetingService (@Service)
    │       └── phát hiện GreetingController (@RestController)
    │
    ├── @EnableAutoConfiguration
    │       └── cấu hình nền tảng web theo dependency/điều kiện
    │
    └── GreetingConfiguration
            └── @Bean GreetingFormatter
                    │
                    ▼
            GreetingService
                    │
                    ▼
            GreetingController
```

Trong ví dụ, **configuration gốc** và **configuration phụ** cùng tham gia xây dựng context nhưng không có cùng trách nhiệm. Đây là lý do quan trọng để giữ `@SpringBootApplication` ở lớp main, còn các cấu hình nghiệp vụ ở `@Configuration`.

## 9. Những nhầm lẫn thường gặp

### 9.1. “`@SpringBootConfiguration` là bản thay thế hoàn toàn của `@SpringBootApplication`”

Không đúng. `@SpringBootConfiguration` chỉ cung cấp vai trò configuration và marker. Nó không bao gồm component scanning và auto-configuration nếu bạn không khai báo riêng.

Khi đổi annotation lớp main từ `@SpringBootApplication` sang `@SpringBootConfiguration`, context có thể không tìm thấy controller hay service như trước.

### 9.2. “Lớp nào có `@Configuration` cũng là root configuration của Boot”

Không đúng. `@Configuration` là cơ chế chung của Spring. Trong khi đó, Boot test bootstrap có thể dùng `@SpringBootConfiguration` làm marker để xác định cấu hình gốc khi test chưa chỉ định explicit classes.

Trong ứng dụng điển hình, các lớp `@Configuration` phụ không cần đóng vai trò marker.

### 9.3. “`@Configuration` tự quét toàn bộ package”

Không đúng. `@Configuration` cho Spring biết cách xử lý lớp cấu hình đã được đăng ký. `@ComponentScan` hoặc cơ chế đăng ký khác mới quyết định lớp nào được phát hiện.

Một cấu hình nằm ngoài vùng scan không tự xuất hiện chỉ vì có annotation `@Configuration`.

### 9.4. “Chỉ khi có `@SpringBootConfiguration` mới dùng được `@Bean`”

Không đúng. `@Bean` làm việc trong nhiều hình thức cấu hình Spring được xử lý phù hợp. `@Configuration` là cách phổ biến nhất để gom các phương thức factory; `@SpringBootConfiguration` kế thừa khả năng đó, không tạo ra cú pháp `@Bean` mới.

### 9.5. “`proxyBeanMethods = false` làm Spring không quản lý bean”

Không đúng. Spring vẫn đăng ký bean từ `@Bean`. Khác biệt chủ yếu là cấu hình không dùng proxy để chặn lời gọi trực tiếp giữa các phương thức `@Bean`. Có thể truyền bean cần thiết qua tham số phương thức hoặc constructor injection.

### 9.6. “Thêm `@SpringBootConfiguration` lên mọi config giúp test chạy”

Không nên. Nếu test không tìm được cấu hình gốc, hãy kiểm tra package, classpath và test annotations. Tạo nhiều marker gốc có thể khiến việc xác định ứng dụng chính trở nên mơ hồ.

## 10. Chẩn đoán những lỗi có liên quan

| Hiện tượng | Điều cần kiểm tra | Lý do |
|---|---|---|
| `@SpringBootTest` báo không tìm được `@SpringBootConfiguration` | Package của test và lớp main, hoặc `@SpringBootTest(classes = ...)` | Test bootstrap cần nhận diện cấu hình Boot gốc |
| Test báo tìm thấy nhiều cấu hình Boot | Nhiều lớp mang `@SpringBootConfiguration` trong phạm vi tìm kiếm | Marker gốc bị mơ hồ |
| Application startup thiếu `@Service` hoặc `@Controller` | Vị trí lớp main và vùng component scan | `@SpringBootConfiguration` tự nó không quét package |
| Không có bean từ lớp `@Configuration` | Lớp đã được scan, import hoặc đăng ký chưa? | Có annotation trên classpath chưa đồng nghĩa class nằm trong context |
| Có `@Bean` nhưng thiếu dependency để khởi tạo bean | Constructor/bean method parameters, điều kiện config | Nguồn bean đã được nhận diện nhưng dependency chưa đáp ứng |
| Có hai đối tượng khác nhau khi gọi `@Bean` trực tiếp | `proxyBeanMethods` và cách gọi giữa các method | `false` cho phép lời gọi Java trực tiếp tạo instance mới |
| Có nhiều bean cùng type khiến injection mơ hồ | `@Qualifier`, `@Primary`, names và configuration đang active | Không phải lỗi marker `@SpringBootConfiguration` |
| Đổi sang `@SpringBootConfiguration` rồi ứng dụng web không lên | Các annotation bị bỏ khi thay `@SpringBootApplication` | Thiếu component scan/auto-configuration cần thiết |

### 10.1. Khi thiếu bean, hỏi theo thứ tự

Giả sử có log dạng:

```text
Parameter 0 of constructor in GreetingService
required a bean of type GreetingFormatter that could not be found.
```

Hãy phân tích:

1. `GreetingConfiguration` có ở package được quét không?
2. Lớp đó có thực sự mang `@Configuration` và được đăng ký trong context không?
3. Phương thức `@Bean` tạo `GreetingFormatter` có hợp lệ và đang active không?
4. Có cấu hình điều kiện hoặc profile khiến bean không được tạo không?
5. Lớp main còn `@SpringBootApplication` hay đã được thay bằng marker hẹp hơn?

Không giải quyết bằng cách đổi mọi `@Configuration` thành `@SpringBootConfiguration`: điều đó không thay thế việc phát hiện cấu hình và wiring bean.

### 10.2. Khi lỗi test, hỏi theo thứ tự

Nếu `@SpringBootTest` không tìm được application configuration:

1. Test có nằm trong nhánh package của lớp `@SpringBootApplication` không?
2. Lớp main có hiện diện trên test classpath không?
3. Có vô tình thay `@SpringBootApplication` bằng `@Configuration` thuần không?
4. Test có mục đích sử dụng application context chính hay một context riêng?
5. Nếu dùng context riêng, đã truyền `classes` hoặc cơ chế cấu hình test thích hợp chưa?

Với một integration test bình thường, bố cục package rõ ràng thường là giải pháp đơn giản nhất. Với test cần bootstrap đặc biệt, khai báo explicit configuration giúp ý định kiểm thử dễ đọc hơn.

## 11. Bài thực hành: quan sát sự khác nhau

Có thể thực hành trên một ứng dụng Spring Boot đơn giản đã có dependency `spring-boot-starter-web`.

### Thí nghiệm A — `@SpringBootApplication` có thể chứa `@Bean`

Giữ lớp main với `@SpringBootApplication`, thêm:

```java
@Bean
public Clock clock() {
    return Clock.systemUTC();
}
```

Tạo service nhận `Clock` qua constructor. Quan sát Spring inject được bean mà không cần đặt `@Configuration` riêng lên lớp main. Giải thích: `@SpringBootApplication` mang `@SpringBootConfiguration`, còn annotation đó dựa trên `@Configuration`.

### Thí nghiệm B — Tách `@Configuration` ra một class phụ

Chuyển `@Bean Clock` sang `TimeConfiguration`:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
```

Đặt class này trong package con của package lớp main. Ứng dụng vẫn có thể inject `Clock` khi component scan phát hiện `TimeConfiguration`.

Tiếp theo, đặt class config ra ngoài phạm vi scan mà không `@Import`. Sự thay đổi này giúp nhận ra `@Configuration` không tự tìm đường vào context.

### Thí nghiệm C — Chỉ dùng `@SpringBootConfiguration`

Trong một project thử nghiệm riêng, tạo một main chỉ có:

```java
@SpringBootConfiguration
public class MinimalApplication {

    public static void main(String[] args) {
        SpringApplication.run(MinimalApplication.class, args);
    }

    @Bean
    public ApplicationRunner runner() {
        return args -> System.out.println("Root configuration loaded");
    }
}
```

Nhớ import `SpringApplication`, `SpringBootConfiguration`, `ApplicationRunner` và `Bean`. Lớp `ApplicationRunner` được Spring Boot gọi sau khi context đã được khởi tạo thành công.

Hãy so sánh với main dùng `@SpringBootApplication`. Điều cần quan sát là bean khai báo trực tiếp vẫn được xử lý, nhưng cấu hình chỉ có marker `@SpringBootConfiguration` không kích hoạt toàn bộ component scan và auto-configuration của annotation tổng hợp.

### Thí nghiệm D — Tìm cấu hình gốc trong integration test

Tạo test `@SpringBootTest` cùng nhánh package với lớp main `@SpringBootApplication`. Sau đó thử đặt test ở nhánh package khác và chỉ định `@SpringBootTest(classes = ShopApplication.class)` nếu cần.

Qua đó, bạn thấy marker `@SpringBootConfiguration` phục vụ thêm cho việc xác định nguồn application configuration trong Boot test bootstrap, chứ không chỉ là một cách viết khác của `@Configuration`.

### Thí nghiệm E — Thay cách nối bean

Trong một lớp `@Configuration`, tạo hai phương thức `@Bean`, trong đó method thứ hai gọi trực tiếp method thứ nhất. Quan sát ý nghĩa khi `proxyBeanMethods` bật và khi tắt. Sau đó chuyển sang nhận bean phụ thuộc qua tham số phương thức:

```java
@Bean
public ReportService reportService(MailClient mailClient) {
    return new ReportService(mailClient);
}
```

Đây là cách thể hiện phụ thuộc rõ ràng, thường không đòi hỏi proxy để điều phối lời gọi trực tiếp giữa các phương thức `@Bean`.

## 12. Nguyên tắc áp dụng trong dự án Spring Boot

Khi tổ chức ứng dụng, hãy giữ phân công rõ:

- **Lớp main dùng `@SpringBootApplication`** khi muốn cách bootstrap thông thường của Spring Boot, bao gồm marker cấu hình gốc, auto-configuration và component scanning.
- **Các lớp `@Configuration`** dùng cho cấu hình bean theo module hoặc trách nhiệm riêng; chúng là cấu hình Spring hợp lệ và có thể được chia thành nhiều lớp.
- **`@SpringBootConfiguration` trực tiếp** phù hợp khi bạn cần kiểm soát thành phần bootstrap hoặc muốn đánh dấu root configuration của Boot mà không yêu cầu toàn bộ những tính năng mà `@SpringBootApplication` gộp sẵn.
- **`@TestConfiguration`** dành cho cấu hình hỗ trợ test, không thay thế marker Boot root configuration.
- **`@Bean`** là phương thức factory tham gia đăng ký đối tượng vào container; việc lớp cấu hình sử dụng proxy hay không là một vấn đề riêng.

Hãy hình dung mỗi annotation trả lời một câu hỏi:

```text
@Configuration
    "Bean definitions của nhóm này được khai báo ở đâu?"

@SpringBootConfiguration
    "Lớp nào là nguồn cấu hình ứng dụng Spring Boot?"

@SpringBootApplication
    "Lớp nào là điểm bootstrap thuận tiện, kết hợp
     cấu hình ứng dụng, scan và auto-configuration?"
```

Khi hiểu sự phân chia đó, bạn sẽ không nhầm việc **đăng ký bean**, **quét package**, **kích hoạt auto-configuration** và **xác định cấu hình gốc cho Spring Boot test** là một hành vi duy nhất. `@SpringBootConfiguration` chính là cầu nối giữa `@Configuration` của Spring Framework và `@SpringBootApplication` của Spring Boot.
