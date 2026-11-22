# Đặt lớp tự cấu hình ngoài vùng quét thành phần của ứng dụng

## 1. Vì sao vị trí package của auto-configuration quan trọng?

Trong Spring Boot, **lớp auto-configuration** là một lớp cấu hình Spring đặc biệt: nó cung cấp các bean và thiết lập hạ tầng mặc định khi những điều kiện thích hợp được thỏa mãn. Tuy mang `@AutoConfiguration` (vốn có ngữ nghĩa `@Configuration`), lớp này **phải đi vào ứng dụng qua cơ chế import auto-configuration của Boot**. Theo hướng dẫn chính thức của Spring Boot, auto-configuration cần nằm trong một không gian package riêng, không trở thành đối tượng của component scanning và không tự quét component để kéo thêm bean vào container. Nếu cần các lớp cấu hình phụ trợ, hãy dùng `@Import` rõ ràng.

Hãy phân biệt hai con đường:

```text
Con đường A — component scanning của ứng dụng
@SpringBootApplication
  -> @ComponentScan
     -> package chứa lớp main và các package con
        -> @Component / @Service / @Repository / @Controller /
           @Configuration ...
        -> BeanDefinition của thành phần ứng dụng

Con đường B — chọn auto-configuration
@SpringBootApplication
  -> @EnableAutoConfiguration
     -> đọc META-INF/spring/...AutoConfiguration.imports
        -> exclusions + điều kiện + sắp thứ tự liên quan
        -> import các @AutoConfiguration phù hợp
        -> BeanDefinition mặc định có điều kiện
```

Cả hai con đường đều kết thúc trong **cùng một Spring `ApplicationContext`** và `BeanFactory`. Khác biệt nằm ở **cách cấu hình được phát hiện, chọn, loại trừ và xử lý**, không phải ở loại container cuối cùng.

**Quy tắc trọng tâm:** lớp `@AutoConfiguration` của thư viện không nên nằm trong phạm vi mà `@ComponentScan` của ứng dụng sẽ quét. Nếu bị quét như một `@Configuration` bình thường, nó có thể tham gia quá trình xử lý theo một đường ngoài ý định, làm thứ tự/điều kiện/exclusion khó dự đoán và khiến quá trình kiểm soát auto-configuration không còn rõ ràng.

## 2. Vùng quét mặc định được xác định thế nào?

Với ứng dụng:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` gồm các vai trò chính:

- `@SpringBootConfiguration`: đánh dấu cấu hình ứng dụng.
- `@ComponentScan`: phát hiện component trong package gốc và các package con.
- `@EnableAutoConfiguration`: bật lựa chọn auto-configuration qua metadata của các JAR.

Nếu không có chỉ định đặc biệt, component scanning bắt đầu từ **`com.acme.shop`** và các package con:

```text
com.acme.shop                    <- lớp @SpringBootApplication
├── service                     <- được scan
├── config                      <- được scan
├── web                         <- được scan
└── repository                  <- được scan

com.acme.integration.autoconfigure  <- ở ngoài cây package trên
```

Một class `com.acme.shop.service.OrderService` mang `@Service` có thể được phát hiện. Nhưng `com.acme.integration.autoconfigure.ClientAutoConfiguration` **không** thuộc cây `com.acme.shop`, nên component scanning mặc định sẽ không nạp nó. Nó vẫn có thể được Boot chọn thông qua tệp `AutoConfiguration.imports` của JAR chứa nó.

Nhớ rằng **package Java** là quan hệ tên định danh, không phải chỉ là folder trong IDE. Lớp có package `com.acme.shop.autoconfigure` nằm *trong* vùng scan dù được đặt ở một source module/JAR khác. Ngược lại, `com.acme.integration.autoconfigure` có thể nằm cùng repository nhưng vẫn ở *ngoài* vùng scan.

### Một cấu trúc dễ gây nhầm

```text
com.acme
├── Application.java             (@SpringBootApplication)
├── feature
│   ├── FeatureService.java      (@Service)
│   └── FeatureAutoConfiguration.java  (@AutoConfiguration)
```

Nếu lớp main ở `com.acme` thì `@ComponentScan` có thể chạm tới `com.acme.feature.FeatureAutoConfiguration`, vì `@AutoConfiguration` về bản chất là lớp `@Configuration`. Đặt nó trong package có tên `autoconfigure` **chưa đủ** để bảo đảm không bị scan. Cần kiểm tra phạm vi scan thực tế và quan hệ package.

Vì vậy:

- **Sai về mặt thiết kế:** chỉ đổi tên class hoặc tạo folder `autoconfigure` dưới package gốc rồi coi như đã tách đường import.
- **Đúng về mặt thiết kế:** đặt lớp auto-configuration trong package riêng nằm ngoài vùng scan ứng dụng và khai báo nó trong tệp `.imports` đúng tên đầy đủ.

## 3. Auto-configuration được phát hiện bằng metadata riêng

Với Spring Boot 3.x, nhà phát triển thư viện đăng ký các auto-configuration trong resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng chứa tên đầy đủ của một class:

```text
com.acme.integrations.autoconfigure.ClientAutoConfiguration
com.acme.integrations.autoconfigure.ClientMetricsAutoConfiguration
```

Khi khởi động, `@EnableAutoConfiguration` kích hoạt quá trình khám phá và lựa chọn những tên ứng viên này. `AutoConfigurationImportSelector` (một `DeferredImportSelector`) tham gia xử lý danh sách đó; Boot có thể áp dụng lọc, exclusions và thứ tự cần thiết trước khi Spring phân tích cấu hình được chọn.

Một class điển hình:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.Client")
class ClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ClientAdapter.class)
    ClientAdapter clientAdapter() {
        return new ClientAdapter();
    }
}
```

Đây là **mã minh họa, không phải chương trình Java độc lập**: `ClientAdapter` là kiểu giả định, và cần import annotation phù hợp. Tình huống cho thấy:

1. Chỉ khi thư viện SDK cần thiết có mặt, điều kiện class mới có thể khớp.
2. Nếu ứng dụng đã có bean phù hợp, `@ConditionalOnMissingBean` có thể khiến bean mặc định **không được đăng ký**.
3. Nếu mọi điều kiện được đáp ứng, Spring ghi nhận bean definition và sau đó container tạo bean theo lifecycle.

**Tệp `.imports` liệt kê ứng viên, không tạo bean tức thì.** Một class được liệt kê vẫn có thể bị exclusion hoặc `@Conditional` loại khỏi lần khởi động. Tách đúng package giữ cho các quyết định này đi qua đường auto-configuration đã được thiết kế.

### Phân biệt tệp quan trọng

| Tệp | Vai trò |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Danh sách lớp auto-configuration để Boot xem xét import |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata điều kiện có thể được tạo bởi annotation processor nhằm hỗ trợ lọc sớm |
| `META-INF/spring-configuration-metadata.json` | Thông tin hỗ trợ IDE và tooling về các key cấu hình |
| `META-INF/spring.factories` | Một số extension của Boot vẫn dùng; **không phải nơi đăng ký auto-configuration mới** theo cơ chế Spring Boot 3.x |

Không nhầm đăng ký auto-configuration trong `.imports` với khai báo `@ComponentScan`: hai cơ chế có mục tiêu khác nhau.

## 4. Vì sao không để component scanning “tìm hộ” lớp auto-configuration?

Giả sử thư viện đưa lớp `MyFeatureAutoConfiguration` vào vùng scan ứng dụng. Dù class có `@AutoConfiguration`, component scanning có thể xem nó như một lớp `@Configuration` để xử lý. Điều đó làm mất ranh giới rõ ràng giữa cấu hình ứng dụng và phần mặc định từ thư viện.

Các rủi ro cần nhận biết:

| Hậu quả khả dĩ | Vì sao cần quan tâm |
| --- | --- |
| Cấu hình được phát hiện ngoài tuyến import auto-configuration | Thứ tự xử lý vốn dự kiến cho auto-configuration có thể không còn đúng như ý định |
| Exclude không điều khiển mọi đường đăng ký cấu hình | `exclude` của Boot tác động danh sách auto-configuration; một class còn được scan/import theo đường khác vẫn có thể tham gia cấu hình |
| Các điều kiện phụ thuộc bean trở nên khó suy luận | `@ConditionalOnMissingBean` dựa trên bean definitions đã được xử lý tại lúc đánh giá |
| Tính năng xuất hiện bất ngờ khi thay đổi package main hoặc scan | Thư viện có thể bị quét sau một thay đổi ở cấu hình ứng dụng |
| Khó chẩn đoán một cấu hình được nạp từ đâu | Có thể nhầm giữa component scanning, explicit `@Import` và Boot import |
| Khó đóng gói một starter dùng lại cho nhiều ứng dụng | Mỗi ứng dụng có phạm vi scan khác nhau, trong khi auto-configuration cần cơ chế phát hiện nhất quán |

Không nên khẳng định mọi dự án như vậy đều ném lỗi bean trùng tên: Spring có các cơ chế xử lý cấu hình và loại trùng. Vấn đề chính là **vi phạm hợp đồng tổ chức của auto-configuration** và tạo đường nạp ngoài dự định, chứ không có một ngoại lệ cố định xuất hiện trong mọi phiên bản.

Một giải pháp sai thường gặp:

```java
@SpringBootApplication(scanBasePackages = "com.acme")
public class ShopApplication {
}
```

Nếu thư viện `com.acme.integrations.autoconfigure` nằm dưới `com.acme`, mở rộng scan lên package chung `com.acme` có thể khiến class auto-configuration bị scan. Thay vì quét cả namespace của tổ chức, hãy giới hạn vùng scan tới component ứng dụng hoặc cấu hình các phần cần thiết bằng `@Import` chính xác.

## 5. Tổ chức package cho ứng dụng và thư viện

### 5.1. Một repository, nhiều module

Cấu trúc khuyến nghị khi phát triển thư viện:

```text
workspace/
├── shop-app/
│   └── src/main/java/com/acme/shop/
│       ├── ShopApplication.java             (@SpringBootApplication)
│       ├── service/OrderService.java        (@Service)
│       └── web/OrderController.java         (@RestController)
├── acme-client-core/
│   └── src/main/java/com/acme/client/
│       ├── AcmeClient.java                  (API)
│       └── DefaultAcmeClient.java           (implementation)
├── acme-client-autoconfigure/
│   ├── src/main/java/com/acme/client/autoconfigure/
│   │   └── AcmeClientAutoConfiguration.java (@AutoConfiguration)
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-client-starter/
    └── pom.xml                              (dependency convenience)
```

Ở đây, package gốc của `shop-app` là `com.acme.shop` trong khi auto-configuration ở `com.acme.client.autoconfigure`. Tách module là hữu ích khi xây starter có thể tái sử dụng, nhưng **chỉ module khác thôi chưa đủ**: nếu package nằm trong cây scan, scanner vẫn có thể tìm class từ JAR.

**Starter** chủ yếu cung cấp các dependency thường dùng, **auto-configure module** chứa cấu hình mặc định có điều kiện, còn **core module** chứa API/implementation của thư viện. Đây là một mô hình tổ chức phổ biến, không bắt buộc mọi dự án phải dùng ba module.

### 5.2. Package nào nên được scan?

Trong `shop-app`, các service/controller/config do ứng dụng sở hữu nên nằm dưới `com.acme.shop`. Những component này có thể được scan theo ý định.

Trong thư viện auto-configure, tránh:

```java
@AutoConfiguration
@ComponentScan("com.acme.client")
public class AcmeClientAutoConfiguration {
}
```

Đây là **anti-pattern trong ngữ cảnh viết auto-configuration**: class auto-configure có thể quét một loạt component ngoài ý định, bỏ qua khả năng chọn cụ thể những thứ cần đăng ký.

Thay vào đó, dùng `@Import` với các lớp hỗ trợ được xác định rõ:

```java
@AutoConfiguration
@Import(AcmeClientSupportConfiguration.class)
public class AcmeClientAutoConfiguration {
}
```

`AcmeClientSupportConfiguration` là lớp minh họa và cần được định nghĩa/import phù hợp khi áp dụng. `@Import` giúp nhà phát triển biết rõ những cấu hình phụ trợ nào được đưa vào; có thể đặt điều kiện trên auto-configuration và các lớp con tùy nhu cầu.

Tránh dùng `@ComponentScan` chỉ để “tiết kiệm danh sách import”, vì nó có thể kéo vào bean mà ứng dụng không cần hoặc không muốn.

## 6. Ví dụ runnable: auto-configuration nằm ngoài package scan

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.13** và **Maven**, trong một module đơn giản để tập trung vào cơ chế. Khi xây thư viện thật, có thể tách class auto-configuration thành JAR riêng nhưng vẫn dùng nguyên nguyên tắc package và `.imports`.

Mục tiêu của ví dụ:

- `demo.app.DemoApplication` là lớp main có `@SpringBootApplication`.
- `demo.autoconfig.GreetingAutoConfiguration` nằm ngoài `demo.app` nên component scanning mặc định không tìm thấy.
- `META-INF/spring/...AutoConfiguration.imports` đưa class auto-configuration vào danh sách ứng viên của Boot.
- `demo.api.Greeting` là API Java thông thường, không có stereotype component.
- `demo.app.UserGreetingConfiguration` khai báo bean tùy chỉnh khi bật property; auto-configuration có điều kiện sẽ nhường chỗ cho bean này.
- Bằng lệnh dòng lệnh, quan sát các trường hợp **mặc định**, **loại trừ auto-configuration** và **bean ứng dụng thay thế mặc định**.

### 6.1. Cấu trúc tệp

```text
greeting-autoconfig-scan/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       ├── api/
    │       │   └── Greeting.java
    │       ├── app/
    │       │   ├── DemoApplication.java
    │       │   └── UserGreetingConfiguration.java
    │       └── autoconfig/
    │           └── GreetingAutoConfiguration.java
    └── resources/
        └── META-INF/
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`demo.app` và `demo.autoconfig` là **hai package anh em**. Scanner bắt đầu ở `demo.app` không đi ngược lên `demo` để quét toàn bộ package con. Mặc dù class auto-configuration nằm trong cùng Maven project và có mặt trên classpath, nó **không** thành ứng viên component scan theo phạm vi mặc định.

### 6.2. pom.xml

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
    <artifactId>greeting-autoconfig-scan</artifactId>
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

Chỉ cần `spring-boot-starter` để dùng IoC container và những API Boot cơ bản. Không có starter web nên ví dụ không yêu cầu cổng HTTP hay web server. JDK 17+ là mức tương thích của Spring Boot 3.3 và cũng đủ để dùng Java `record`.

### 6.3. API Java thông thường

**`src/main/java/demo/api/Greeting.java`**

```java
package demo.api;

public record Greeting(String text) {
}
```

`Greeting` chỉ là record. Nó không có `@Component`, `@Configuration` hoặc `@Bean`, nên riêng việc class này tồn tại trên classpath không làm Spring tạo bean `Greeting`.

### 6.4. Lớp auto-configuration bên ngoài vùng scan

**`src/main/java/demo/autoconfig/GreetingAutoConfiguration.java`**

```java
package demo.autoconfig;

import demo.api.Greeting;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Greeting.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeting.class)
    Greeting defaultGreeting() {
        return new Greeting("default");
    }
}
```

Giải thích:

- `@AutoConfiguration`: lớp thuộc nhóm cấu hình mặc định do Boot chọn, không phải thành phần nghiệp vụ cần scanner tìm.
- `@ConditionalOnClass(Greeting.class)`: chỉ áp dụng khi API class tương ứng có trên classpath. Trong ví dụ class luôn có mặt, nên điều kiện này đúng.
- `@ConditionalOnMissingBean(Greeting.class)`: chỉ đăng ký bean `defaultGreeting` nếu chưa có bean `Greeting` phù hợp ở thời điểm đánh giá.
- `@Bean`: định nghĩa factory method. Việc tạo object `Greeting` do Spring IoC thực hiện sau khi definition hợp lệ đã được đăng ký.

Lớp auto-configuration không dùng `@ComponentScan`. Nếu một thư viện có thêm cấu hình phụ trợ, sử dụng `@Import` một cách tường minh theo khuyến nghị ở mục 5.

### 6.5. Tệp AutoConfiguration.imports

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
demo.autoconfig.GreetingAutoConfiguration
```

Lưu ý chính xác đường dẫn, kể cả chữ hoa trong `AutoConfiguration.imports` và package đầy đủ của class. Nếu thiếu dòng này, một auto-configuration không thuộc vùng component scan **không có con đường khám phá auto-configuration thông thường** qua JAR này.

Trong Spring Boot 3.x, auto-configuration nên được đăng ký theo cơ chế `.imports`, không phải chỉ thêm class vào một package được scan. `spring.factories` còn dùng cho một số extension khác; không dùng nó làm đường đăng ký chính của những auto-configuration mới trong ví dụ này.

### 6.6. Bean do ứng dụng chủ động cung cấp

**`src/main/java/demo/app/UserGreetingConfiguration.java`**

```java
package demo.app;

import demo.api.Greeting;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    name = "demo.greeting.custom",
    havingValue = "true"
)
public class UserGreetingConfiguration {

    @Bean
    Greeting userGreeting() {
        return new Greeting("custom");
    }
}
```

Vì `UserGreetingConfiguration` ở `demo.app`, component scan có thể tìm nó. Nhưng cấu hình này **chỉ đăng ký bean** khi property `demo.greeting.custom=true`.

Đây là property **do ví dụ tự định nghĩa**, không phải property mặc định Spring Boot. Khi property không bật, class cấu hình ứng dụng này không đóng góp bean. Khi property bật, nó cung cấp `Greeting("custom")`; auto-configuration dựa trên `@ConditionalOnMissingBean` sẽ nhường chỗ cho định nghĩa phù hợp đã có.

### 6.7. Ứng dụng chính

**`src/main/java/demo/app/DemoApplication.java`**

```java
package demo.app;

import demo.api.Greeting;
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
    ApplicationRunner showGreeting(ObjectProvider<Greeting> provider) {
        return args -> {
            Greeting bean = provider.getIfAvailable();
            String message = bean == null ? "missing" : bean.text();
            System.out.println("GREETING: " + message);
        };
    }
}
```

`ObjectProvider<Greeting>` được sử dụng vì trường hợp loại trừ auto-configuration có thể không còn bean `Greeting`. Nhờ vậy runner vẫn chạy và in `missing` thay vì thất bại do một dependency bắt buộc không có.

`ApplicationRunner` là một bean của ứng dụng, được Boot gọi sau khi context refresh thành công. Đây cũng là cách minh họa rằng bean từ auto-configuration, bean từ component scanning và bean từ `@Bean` cùng đi vào một container.

### 6.8. Build và chạy

Tại thư mục có `pom.xml`, dùng Java 17+ và Maven:

```bash
mvn -q -DskipTests package
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none
```

Ngoài log startup và banner, dòng do chương trình tự in là:

```text
GREETING: default
```

Lý do: `GreetingAutoConfiguration` được nạp **qua `.imports`**, điều kiện class khớp, không có bean `Greeting` do ứng dụng khai báo nên `defaultGreeting()` cung cấp bean mặc định.

**Thử loại trừ đúng auto-configuration:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
```

Dòng do chương trình in:

```text
GREETING: missing
```

Lý do: `GreetingAutoConfiguration` bị loại khỏi danh sách import. Nó cũng nằm **ngoài phạm vi component scan**, nên không có một con đường quét khác tự nạp lớp này. Không có cấu hình ứng dụng nào khác cung cấp `Greeting`, vì thế `ObjectProvider#getIfAvailable()` trả `null`.

**Thử bean do ứng dụng thay thế mặc định:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.custom=true
```

Dòng do chương trình in:

```text
GREETING: custom
```

Lý do: `UserGreetingConfiguration` thuộc vùng component scan và property cho phép bean `userGreeting` được đăng ký; khi auto-configuration xét `@ConditionalOnMissingBean`, đã có bean `Greeting` phù hợp nên `defaultGreeting` nhường chỗ.

**Thử thêm một tình huống kết hợp:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --demo.greeting.custom=true \
  --spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
```

Kết quả vẫn là:

```text
GREETING: custom
```

Điều này chứng minh bean ứng dụng không phụ thuộc việc Boot có import auto-configuration mặc định hay không.

**Bốn lần chạy** dùng cùng một JAR nhưng đưa ra những kết quả khác nhau nhờ điều kiện, exclusion và định nghĩa bean của ứng dụng. Không cần thay đổi component scanning giữa các lần chạy.

## 7. Tình huống sai: đặt auto-configuration trong package con của ứng dụng

Hãy thử phân tích cấu trúc này bằng mắt:

```text
demo/
└── app/
    ├── DemoApplication.java          (@SpringBootApplication)
    ├── UserGreetingConfiguration.java
    └── autoconfig/
        └── GreetingAutoConfiguration.java (@AutoConfiguration)
```

Lúc này tên package của auto-configuration là `demo.app.autoconfig`. Vì nó nằm dưới `demo.app`, component scanner của ứng dụng có thể tìm class đó như một `@Configuration`. Ngay cả khi bạn cũng cập nhật `.imports` để liệt kê tên mới, cấu trúc vẫn làm auto-configuration có thêm đường phát hiện không mong muốn.

**Không nên chỉ “xóa `.imports`” rồi dựa vào scan để làm cho chương trình chạy.** Làm vậy sẽ biến một lớp đáng lẽ được Boot lựa chọn có điều kiện thành cấu hình được đưa vào như một component thông thường, không còn bảo đảm những quy tắc phát hiện/exclusion/sắp thứ tự được thiết kế cho auto-configuration.

Cách sửa phù hợp:

1. Di chuyển class tới package ngoài vùng scan, ví dụ `demo.autoconfig.GreetingAutoConfiguration`.
2. Chỉnh package statement, import Java và tệp `.imports` theo tên đầy đủ mới.
3. Xác nhận component scan của ứng dụng không được mở rộng tới `demo.autoconfig`.
4. Giữ các `@Conditional...` cần thiết để mặc định nhường chỗ cho cấu hình ứng dụng.
5. Kiểm tra riêng đường import, đường exclusion và các trường hợp ứng dụng có bean tùy chỉnh.

Không cần tạo thêm một `@SpringBootApplication` ở module thư viện. Thư viện cung cấp `@AutoConfiguration` và metadata, còn ứng dụng chịu trách nhiệm có một entrypoint phù hợp.

## 8. scanBasePackages có thể làm mất ranh giới này

Ngay cả khi lớp `@AutoConfiguration` đã nằm trong package khác, một ứng dụng vẫn có thể **mở rộng vùng scan** một cách quá rộng:

```java
@SpringBootApplication(scanBasePackages = "demo")
public class DemoApplication {
}
```

Đây là đoạn minh họa ý tưởng, **không thay thế file chính trong ví dụ runnable**. Nếu scanner bắt đầu từ `demo`, nó có thể tìm `demo.autoconfig.GreetingAutoConfiguration`, vì lớp auto-configuration mang ngữ nghĩa `@Configuration`.

Hai thuộc tính thường dùng:

```java
@SpringBootApplication(
    scanBasePackages = {"demo.app", "demo.otherapp"}
)
```

và:

```java
@SpringBootApplication(
    scanBasePackageClasses = {SomeApplicationMarker.class}
)
```

là các đoạn minh họa cần class/import phù hợp. Chúng điều chỉnh **component scanning**. Chúng không chuyển các auto-configuration ứng viên trong `.imports` thành component scan, cũng không mặc nhiên thay đổi mọi cơ chế quét JPA entity hoặc Spring Data repository.

Một quy tắc review hữu ích: mỗi lần thay `scanBasePackages`, hãy kiểm tra xem vùng scan mới có chứa package `*.autoconfig`, `*.autoconfigure` hoặc namespace thư viện nào mang `@AutoConfiguration` không. Tên package chỉ là dấu hiệu để tìm; **quan hệ package thực tế** mới quyết định scanner có đi tới lớp đó hay không.

## 9. Nếu thư viện cần những thành phần phụ trợ thì sao?

Tác giả thư viện thường có thêm encoder, serializer, client factory, validator hoặc adapter. Không nên đặt toàn bộ các class đó dưới một package rồi quét chung từ auto-configuration.

### Dùng @Bean cho đối tượng cần factory method

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
class VendorClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(VendorClientAdapter.class)
    VendorClientAdapter vendorClientAdapter() {
        return new VendorClientAdapter();
    }
}
```

Đoạn này minh họa API, giả định các class `VendorClientAdapter` đã tồn tại và import đầy đủ. `@Bean` cho phép kiểm soát tên bean, điều kiện và dependency rõ ràng.

### Dùng @Import khi cần một lớp cấu hình riêng

```java
@AutoConfiguration
@Import(VendorSupportConfiguration.class)
class VendorAutoConfiguration {
}
```

`VendorSupportConfiguration` là lớp giả định trong đoạn minh họa. `@Import` **chỉ rõ cấu hình phụ trợ** nào được áp dụng thay vì quét cả namespace thư viện. Nếu có các tính năng phụ thuộc classpath khác nhau, có thể đặt điều kiện riêng trên lớp hỗ trợ hoặc nested configuration.

### Dùng @ConfigurationProperties khi có tham số cấu hình

Nếu thư viện cần timeout, endpoint hoặc giới hạn kết nối, hãy khai báo lớp properties có prefix riêng như `acme.client` và đăng ký bằng cơ chế thích hợp, ví dụ `@EnableConfigurationProperties(AcmeClientProperties.class)` trên auto-configuration. Lớp properties là dữ liệu cấu hình, không phải lý do để mở `@ComponentScan` toàn thư viện.

Cần chú ý rằng **`@ConfigurationPropertiesScan` cũng là một cơ chế quét riêng** và có các quy tắc/phạm vi của nó; nó không thay thế lời khuyên tách auto-configuration khỏi component scanning. Một class được cấu hình qua annotation này không đồng nghĩa auto-configuration cần nằm trong package ứng dụng.

## 10. Kiểm tra việc loại trừ thực sự hoạt động

Spring Boot cho phép loại trừ lớp auto-configuration bằng:

```java
@SpringBootApplication(
    excludeName = "demo.autoconfig.GreetingAutoConfiguration"
)
public class DemoApplication {
}
```

Đây là snippet minh họa, không phải phiên bản hoàn chỉnh thay thế lớp `DemoApplication` chạy ở mục 6. Cách tương ứng bằng property là:

```properties
spring.autoconfigure.exclude=demo.autoconfig.GreetingAutoConfiguration
```

Tác dụng: loại lớp có tên đó khỏi những auto-configuration ứng viên được chọn. **Exclusion không phải lệnh xóa mọi bean cùng type** và không loại một bean được ứng dụng khai báo từ đường cấu hình khác. Bởi vậy ví dụ mục 6 vẫn in `custom` khi có bean do ứng dụng cung cấp.

Nếu class auto-configuration vẫn bị quét như cấu hình thường do package sai, chỉ thêm exclude chưa xử lý triệt để nguyên nhân. Hãy sửa cấu trúc package và đường đăng ký trước.

**Chẩn đoán bằng Conditions Evaluation Report:**

```bash
java -jar target/greeting-autoconfig-scan-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none \
  --debug
```

Boot ghi thông tin chẩn đoán điều kiện auto-configuration. Tìm `GreetingAutoConfiguration` ở các phần *Positive matches*, *Negative matches* hoặc *Exclusions* tùy trường hợp. Báo cáo điều kiện giúp biết vì sao một ứng viên được hoặc không được áp dụng; nếu một bean đã có definition nhưng tạo lỗi, vẫn phải đọc stack trace và nguyên nhân gốc.

### Checklist khi review một starter

| Kiểm tra | Tình trạng đúng |
| --- | --- |
| Lớp auto-configuration nằm ở package nào? | Tách khỏi cây package component scan mặc định của các ứng dụng dự kiến sử dụng |
| JAR có `AutoConfiguration.imports` không? | Có, tên fully-qualified class chính xác |
| Auto-configuration có `@ComponentScan` không? | Nên tránh; dùng `@Import` hoặc `@Bean` có chủ đích |
| Có `@ConditionalOnClass` cho dependency tùy chọn không? | Có nếu cấu hình phụ thuộc class/thư viện không luôn hiện diện |
| Mặc định có `@ConditionalOnMissingBean` phù hợp không? | Có nếu API cho phép ứng dụng thay thế bean |
| Có test trường hợp exclude không? | Loại trừ làm biến mất cấu hình mặc định, không nạp lại qua scan |
| Có test user-provided bean không? | Khi cấu hình cho phép, bean ứng dụng thắng theo điều kiện đã thiết kế |
| Có vô tình scan package gốc rộng không? | Phạm vi `scanBasePackages` chỉ gồm component ứng dụng cần thiết |

## 11. Những lỗi và hiểu nhầm phổ biến

### Lỗi 1: “Có @AutoConfiguration thì Spring không bao giờ scan class đó”

Sai. `@AutoConfiguration` mang cấu hình Spring, và nếu lớp nằm trong phạm vi component scanning, scanner vẫn có thể xem nó như một ứng viên cấu hình. Tên annotation không phải tường rào chống scan.

### Lỗi 2: “Chỉ cần đặt trong một JAR khác”

Không đủ. Component scanning có thể tìm component từ các JAR trên classpath nếu package nằm trong vùng quét. Sự phân tách **package** và phạm vi scanner mới là vấn đề trọng tâm.

### Lỗi 3: “Có file .imports thì class không thể được scan”

Sai. `.imports` cung cấp đường import cho Boot; nó không loại bỏ khả năng ứng dụng vô tình scan class đó. Cần tổ chức package để class chỉ đi vào ứng dụng bằng con đường dự kiến.

### Lỗi 4: “Mở scanBasePackages lên package cao nhất để hết thiếu bean”

Đôi khi khiến ứng dụng có thêm component không mong muốn, kể cả auto-configuration của thư viện. Hãy kiểm tra bean thiếu thuộc nguồn nào trước: component scan, cấu hình tường minh hay auto-configuration.

### Lỗi 5: “Auto-configuration nên @ComponentScan toàn bộ thư viện để tiết kiệm code”

Điều này đi ngược hướng dẫn của Spring Boot cho auto-configuration. Hãy dùng `@Import` cụ thể hoặc các phương thức `@Bean` được đặt điều kiện rõ ràng.

### Lỗi 6: “Exclude auto-configuration cũng xóa bean do tôi tự viết”

Không. Exclusion nhắm tới auto-configuration được chọn. Một bean do `@Configuration` của ứng dụng khai báo độc lập vẫn tồn tại nếu điều kiện riêng của nó khớp.

### Lỗi 7: “Bean mặc định không xuất hiện vì package auto-configuration nằm ngoài scan”

Nếu `.imports` và các điều kiện đúng, việc **nằm ngoài scan là chủ đích**, không phải lỗi. Hãy kiểm tra tên class trong `.imports`, dependency, exclusions và Conditions Evaluation Report.

### Lỗi 8: “@ConditionalOnMissingBean luôn bảo đảm không bao giờ có xung đột”

Condition phụ thuộc bean definitions được thấy ở thời điểm đánh giá và các tiêu chí type/name cụ thể. Không nên dùng nó tùy tiện để che một cấu trúc package sai hoặc đặt trên cấu hình thông thường rồi giả định có cùng thứ tự như auto-configuration chuẩn.

## 12. Cách áp dụng vào dự án thực tế

Khi tạo starter cho một chức năng mới, quy trình hợp lý:

1. **Thiết kế API trước:** xác định bean công khai nào cần cung cấp và điểm người dùng có thể thay thế.
2. **Chọn namespace tách biệt:** ví dụ `com.acme.lib.autoconfigure` cho auto-configure, `com.acme.app` cho ứng dụng.
3. **Tạo lớp `@AutoConfiguration`:** đặt điều kiện theo classpath, property, bean và kiểu ứng dụng phù hợp.
4. **Khai báo class trong `.imports`:** kiểm tra resource có thật sau khi đóng gói JAR.
5. **Đăng ký phụ trợ tường minh:** dùng `@Bean`, `@Import`, `@EnableConfigurationProperties`; hạn chế component scanning bên trong auto-configuration.
6. **Chạy thử cùng ứng dụng tiêu thụ:** bảo đảm ứng dụng có phạm vi scan thông thường nhưng vẫn nạp được auto-configuration qua metadata.
7. **Kiểm tra tùy biến và exclusion:** người dùng tạo bean riêng; cấu hình mặc định back off khi được thiết kế; loại trừ lớp auto-configuration không để sót đường scan.
8. **Xem điều kiện và lifecycle:** khi thiếu bean, phân biệt ứng viên không được tìm thấy, điều kiện không khớp, hoặc bean definition có rồi nhưng khởi tạo thất bại.

Đối với ứng dụng không phát triển starter, không cần tạo auto-configuration cho mọi component. Phần nghiệp vụ nên dùng `@Service`, `@Component`, `@Repository` và `@Configuration` thông thường. Auto-configuration thích hợp nhất khi cung cấp **tích hợp mặc định có điều kiện** cho nhiều ứng dụng hoặc một thư viện dùng lại.

## 13. Câu hỏi tự kiểm tra

**1.** Vì sao cùng một JAR chứa `GreetingAutoConfiguration`, nhưng `demo.app` không tự scan class đó?

Vì `demo.autoconfig` là package anh em với `demo.app`, không phải package con của `demo.app`. JVM classpath và vùng component scanning là hai khái niệm khác nhau.

**2.** Làm thế nào `GreetingAutoConfiguration` vẫn được nạp trong lần chạy mặc định?

Vì tên đầy đủ của class được ghi trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, từ đó Boot xem xét nó qua `@EnableAutoConfiguration`.

**3.** Vì sao lúc exclude tự cấu hình chương trình in `GREETING: missing` thay vì thất bại startup?

`ApplicationRunner` nhận `ObjectProvider<Greeting>` và xử lý trường hợp không có bean. Không có class auto-configuration nào khác đăng ký `Greeting` trong ví dụ.

**4.** Nếu di chuyển `GreetingAutoConfiguration` tới `demo.app.autoconfig`, liệu `.imports` còn đủ để bảo đảm nạp đúng tuyến?

Không. Class lúc đó có thể được component scan tìm thấy như cấu hình thường. Cần giữ class ngoài vùng scan và đăng ký qua `.imports`.

**5.** Khi thư viện có ba helper configuration, nên dùng `@ComponentScan` từ auto-configuration hay `@Import` có chọn lọc?

Theo hướng dẫn Spring Boot, nên dùng `@Import` rõ ràng cho lớp cấu hình phụ trợ, kết hợp điều kiện phù hợp; không để auto-configuration quét tùy ý cả package thư viện.

**6.** Khi người dùng khai báo `Greeting("custom")`, tại sao mặc định nhường chỗ?

`@ConditionalOnMissingBean(Greeting.class)` trên phương thức mặc định chỉ khớp nếu không có bean phù hợp tại thời điểm đánh giá. Cấu hình ứng dụng được xử lý để cung cấp bean tùy chỉnh trước pha quyết định mặc định trong ví dụ.

**7.** `scanBasePackages` có phải công cụ bật tắt auto-configuration không?

Không. Nó điều khiển component scanning; `@EnableAutoConfiguration`, `.imports`, conditions và exclusions quản lý auto-configuration. Mở scan quá rộng còn có thể vô tình quét class auto-configure.

## 14. Tài liệu tham khảo

- Spring Boot — Creating Your Own Auto-configuration, mục *Locating Auto-configuration Candidates*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Using the @SpringBootApplication Annotation: https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html
- Spring Boot — Auto-configuration và exclusions: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Framework — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Boot 3.3 — AutoConfiguration annotation API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
