# Cấu hình người dùng và thời điểm xem xét cấu hình mặc định trong Spring Boot

## 1. Vấn đề: Spring Boot làm sao biết khi nào nên nhường chỗ?

Spring Boot cung cấp **auto-configuration** để ứng dụng có thể sử dụng các thành phần hạ tầng mà không phải tự viết toàn bộ `@Configuration` và `@Bean`. Nhưng khi lập trình viên đã tự khai báo một bean phù hợp, nhiều auto-configuration sẽ **nhường chỗ** (*back off*) thay vì đăng ký bean mặc định.

Ví dụ: Boot có thể tạo một `DataSource` phù hợp khi có JDBC và cấu hình liên quan; nếu ứng dụng đã cung cấp `DataSource` theo cách tương thích với điều kiện của auto-configuration, cấu hình mặc định có thể không được đăng ký. Quy tắc này còn được thể hiện rõ qua `@ConditionalOnMissingBean`.

Ba câu hỏi phải được trả lời riêng:

1. **Cấu hình người dùng là gì?** Những class `@Configuration`, phương thức `@Bean`, component và bean definition mà ứng dụng cung cấp, kể cả những bean có điều kiện.
2. **Boot xem xét cấu hình mặc định khi nào?** Trong quá trình xử lý cấu hình và đăng ký bean definition, auto-configuration được xét sau những bean definition thông thường do ứng dụng khai báo.
3. **“Xem xét sau” có nghĩa gì?** Điều kiện có thể nhận ra bean definition đã tồn tại rồi quyết định không đăng ký bean mặc định; điều đó **không có nghĩa** bean của ứng dụng đã được khởi tạo trước bean mặc định.

Đích học tập của bài: đọc được những tình huống “ứng dụng khai báo bean → auto-config nhường chỗ”, xác định giới hạn của `@ConditionalOnMissingBean` và tránh nhầm **đăng ký bean definition** với **khởi tạo bean instance**.

## 2. Cấu hình người dùng được nhận diện như thế nào?

“Cấu hình người dùng” trong ngữ cảnh này không chỉ có file `application.properties`. Nó còn là **định nghĩa bean** do ứng dụng cung cấp.

### 2.1. Những nguồn phổ biến

| Nguồn | Ví dụ | Ý nghĩa đối với auto-configuration |
| --- | --- | --- |
| Class `@Configuration` của ứng dụng | `@Configuration class AppConfig` | Các phương thức `@Bean` được xử lý thành bean definitions |
| Phương thức `@Bean` | `@Bean MessageFormatter customFormatter()` | Có thể làm `@ConditionalOnMissingBean(MessageFormatter.class)` không khớp |
| Component scanning | `@Service class BillingService` | Có thể đăng ký bean kiểu tương ứng trước khi auto-config xét điều kiện |
| `@Import` và đăng ký chương trình | `@Import(OtherConfig.class)`, registrar | Có thể cung cấp definitions, nhưng phải xét **giai đoạn đăng ký** trong lifecycle |
| Cấu hình theo môi trường | `@Profile("prod")`, `@ConditionalOnProperty` | Quyết định bean của ứng dụng có được đăng ký ở môi trường hiện tại không |

Trong ví dụ dưới đây, “user bean” nghĩa là **bean do ứng dụng khai báo**, còn “default bean” nghĩa là **bean từ auto-configuration khi điều kiện cho phép**. Chúng thường cùng thực hiện một interface hoặc cung cấp cùng một loại dịch vụ.

Lưu ý: Một property như `demo.custom=true` **không tự tạo** bean. Trong ví dụ, property chỉ khiến `@ConditionalOnProperty` trên phương thức `@Bean` của ứng dụng khớp; **chính phương thức `@Bean`** là nguồn đăng ký bean.

### 2.2. Bean definition khác bean instance

Spring `ApplicationContext` giữ metadata và cách tạo bean. Với:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
```

Spring có thể biết trước **tên**, **kiểu trả về** và **cách tạo** bean `paymentGateway` từ bean definition, trong khi phương thức `paymentGateway()` **chưa được gọi để tạo object thực tế**.

Đoạn trên chỉ minh họa, không phải chương trình tự chạy: `PaymentGateway` và `StripePaymentGateway` là các kiểu giả định của ứng dụng.

Do đó, điều kiện “đã tồn tại bean phù hợp chưa?” thường là điều kiện về **bean definitions đang được nhận biết**, không phải thao tác bắt Spring khởi tạo toàn bộ bean chỉ để so sánh.

## 3. Thời điểm xét auto-configuration: sau định nghĩa của ứng dụng

`@SpringBootApplication` kích hoạt `@EnableAutoConfiguration` cùng component scanning và cấu hình Spring. Trong Spring Boot 3.x, các auto-configuration candidate được công bố bằng tài nguyên:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Khi khởi động, Spring xử lý các class cấu hình, quét component, import cấu hình và đăng ký bean definitions; cơ chế `DeferredImportSelector` được dùng cho auto-configuration giúp nó được xét sau cấu hình thông thường của ứng dụng.

Điểm then chốt là **Spring Boot bảo đảm auto-configuration được áp dụng sau khi các bean definition do người dùng khai báo đã được thêm vào**, nên những điều kiện nhận biết bean trong auto-config có thể dựa trên các định nghĩa đó. Điều này là cơ sở cho hành vi *back off*.

Hình dung trình tự **logic** như sau:

```text
@SpringBootApplication
         |
         v
Đọc cấu hình ứng dụng + component scan + @Import
         |
         v
Đăng ký những bean definitions của ứng dụng
         |
         v
Xem xét auto-configuration candidates và các điều kiện
         |                               |
         | có bean phù hợp              | chưa có bean phù hợp
         v                               v
  Auto-config back off            Đăng ký bean definition mặc định
         \                               /
          \                             /
           v                           v
             Tập bean definitions cuối cùng
                         |
                         v
           Tạo bean instances và nối phụ thuộc (DI)
                         |
                         v
                 Ứng dụng chạy
```

Sơ đồ trên nhằm phân biệt các quyết định, **không** mô tả mọi callback của Spring Framework thành một danh sách tuyến tính cứng. Một số điều kiện có thể được kiểm tra trong những giai đoạn xử lý cấu hình khác nhau. Auto-configuration có thể được **phát hiện** từ imports file sớm; việc **đánh giá điều kiện và đăng ký bean definition** là câu chuyện riêng.

**Không suy ra:** “cấu hình người dùng luôn khởi tạo bean instance trước”; “mọi bean được đăng ký thủ công sau này đều được auto-config nhìn thấy từ trước”; hoặc “đăng ký sau là ghi đè định nghĩa của người dùng”.

## 4. Điều kiện quan trọng nhất: `@ConditionalOnMissingBean`

Spring Boot thường sử dụng:

```java
@Bean
@ConditionalOnMissingBean(MessageFormatter.class)
MessageFormatter defaultMessageFormatter() {
    return target -> "DEFAULT: " + target;
}
```

Đây là đoạn minh họa trong một class auto-configuration. Nó nói: **chỉ đăng ký bean này nếu điều kiện cho thấy chưa có bean `MessageFormatter` phù hợp** trong phạm vi tìm kiếm.

Nếu class/method có các điều kiện khác như `@ConditionalOnClass` hoặc `@ConditionalOnProperty`, tất cả điều kiện liên quan cũng cần thỏa.

### 4.1. Điều kiện dựa trên những gì đã được xử lý

Tài liệu Spring Boot lưu ý rằng `@ConditionalOnBean` và `@ConditionalOnMissingBean` phụ thuộc vào những bean definition **đã được xử lý cho tới thời điểm đánh giá**. Vì vậy, cách dùng an toàn được khuyến nghị là đặt chúng trong **auto-configuration**, nơi cơ chế deferred imports giúp xét các bean definitions của ứng dụng trước.

Ví dụ điển hình:

```java
// Ứng dụng khai báo:
@Bean
MessageFormatter userMessageFormatter() {
    return target -> "CUSTOM: " + target;
}

// Auto-configuration cung cấp default:
@Bean
@ConditionalOnMissingBean(MessageFormatter.class)
MessageFormatter defaultMessageFormatter() {
    return target -> "DEFAULT: " + target;
}
```

Kết quả mong đợi khi hai cấu hình được đăng ký đúng cách: Spring thấy definition của `userMessageFormatter` và **không đăng ký** `defaultMessageFormatter`. Không cần thực thi `userMessageFormatter()` trước mới biết nên nhường chỗ.

Nếu cùng điều kiện này được rải vào những class `@Configuration` thông thường, thứ tự xử lý cấu hình có thể khiến kết quả khó đoán: ở thời điểm điều kiện chạy, bean khác có thể **chưa được đăng ký**.

### 4.2. Điều kiện theo kiểu bean và theo tên bean không giống nhau

| Dạng điều kiện | Thứ cần vắng mặt | Ví dụ |
| --- | --- | --- |
| `@ConditionalOnMissingBean(MessageFormatter.class)` | Bean có kiểu `MessageFormatter` phù hợp | Bất kể tên bean mặc định |
| `@ConditionalOnMissingBean(name = "messageFormatter")` | Bean có **tên** `messageFormatter` | Một bean cùng interface nhưng tên khác không nhất thiết khiến điều kiện thất bại |
| `@ConditionalOnBean(MessageFormatter.class)` | Yêu cầu đã có bean `MessageFormatter` | Phù hợp với cấu hình phụ thuộc một bean khác |
| `@ConditionalOnClass(SomeLibrary.class)` | Class trên classpath, **không phải bean** | Có dependency không đồng nghĩa có bean |
| `@ConditionalOnProperty(prefix = "demo", name = "enabled", havingValue = "true")` | Property khớp giá trị mong đợi | Bật/tắt tính năng theo Environment |

Đừng lẫn **tên class**, **tên bean**, **kiểu bean** và **tên property**. Auto-configuration chỉ nhường chỗ nếu **điều kiện cụ thể** khớp với thứ ứng dụng đã cung cấp.

### 4.3. Kiểu trả về của `@Bean` quan trọng

Các điều kiện theo kiểu bean thường dựa vào **type metadata** của bean definition. Khi khai báo factory method, nên nêu kiểu trả về đủ cụ thể:

```java
// Có thông tin kiểu cụ thể, hỗ trợ điều kiện theo loại bean:
@Bean
FastCache fastCache() {
    return new FastCache();
}

// Quá chung, có thể khiến điều kiện dựa trên kiểu cụ thể
// không nhận ra bean tại thời điểm kiểm tra:
@Bean
Object fastCache() {
    return new FastCache();
}
```

Hai phương thức trên là **hai phương án minh họa riêng**, không đặt cùng một lúc trong một class vì trùng tên. `FastCache` là kiểu giả định. Vấn đề không nằm ở kiểu instance được trả lúc runtime, mà ở **kiểu Spring có thể suy ra từ khai báo factory method khi đánh giá điều kiện**. Trong các API có interface, kiểu trả về cũng cần cân nhắc tính tương thích/contract với những điều kiện thực tế.

### 4.4. Trường hợp còn nhiều điều kiện

Một auto-configuration có thể yêu cầu đồng thời:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.client.RemoteClient")
@ConditionalOnProperty(prefix = "feature.remote", name = "enabled",
        havingValue = "true")
class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteGateway.class)
    RemoteGateway remoteGateway() {
        // Chỉ là mã minh họa, cần implementation và dependency thực tế.
        return new RemoteGateway();
    }
}
```

Mã trên **không phải ví dụ có thể biên dịch độc lập**; `RemoteGateway` là kiểu minh họa. Mục đích: không có class SDK, property tắt, hoặc đã có `RemoteGateway` đều có thể khiến bean mặc định **không được đăng ký**. Không thể chỉ nhìn `@ConditionalOnMissingBean` để giải thích đầy đủ nguyên nhân.

## 5. Ví dụ chạy được: bean người dùng thắng cấu hình mặc định

Ví dụ sau dùng **Java 17+**, Maven và **Spring Boot 3.3.13**. Nó kiểm chứng hai lần chạy:

- Khi `demo.custom=false`: ứng dụng chưa đăng ký `MessageFormatter` của người dùng; auto-config cung cấp bean mặc định.
- Khi `demo.custom=true`: bean của ứng dụng đã được đăng ký; auto-config nhận ra và không tạo default.

### 5.1. Cấu trúc dự án

```text
user-config-order-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   ├── MessageFormatter.java
    │   │   └── UserMessageConfiguration.java
    │   └── library/autoconfigure/
    │       └── MessageAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ta đặt app tại `com.example.app`, auto-config tại `com.example.library.autoconfigure` để **auto-configuration không nằm dưới phạm vi component scanning mặc định**. Nó chỉ được đưa vào nhờ danh sách auto-config candidate.

### 5.2. `pom.xml`

```xml
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
    <artifactId>user-config-order-demo</artifactId>
    <version>1.0.0</version>
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

### 5.3. `src/main/java/com/example/app/MessageFormatter.java`

```java
package com.example.app;

@FunctionalInterface
public interface MessageFormatter {
    String format(String target);
}
```

Đây là **hợp đồng** mà ứng dụng và auto-config cùng cung cấp. Một annotation `@FunctionalInterface` không tự đăng ký bean.

### 5.4. `src/main/java/com/example/app/UserMessageConfiguration.java`

```java
package com.example.app;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserMessageConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "custom",
            havingValue = "true")
    MessageFormatter userMessageFormatter() {
        return target -> "CUSTOM: " + target;
    }
}
```

Class nằm dưới package gốc `com.example.app`, nên `@Configuration` được component scanning phát hiện. Khi property `demo.custom=true`, phương thức này tạo **bean definition có kiểu `MessageFormatter`**. Khi property false, định nghĩa bean `userMessageFormatter` không được đăng ký.

Không nên nghĩ hai trạng thái này là Spring tạo bean rồi xóa bean. Điều kiện được xét trong quá trình cấu hình để quyết định **định nghĩa nào sẽ được thêm vào container**.

### 5.5. `src/main/java/com/example/library/autoconfigure/MessageAutoConfiguration.java`

```java
package com.example.library.autoconfigure;

import com.example.app.MessageFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class MessageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageFormatter.class)
    MessageFormatter defaultMessageFormatter() {
        return target -> "DEFAULT: " + target;
    }
}
```

Auto-configuration có phương thức `@Bean` cùng kiểu, nhưng **chỉ đăng ký** nó nếu container chưa có bean `MessageFormatter` tương ứng khi điều kiện được đánh giá.

Trong dự án thực tế, một starter nên đặt hợp đồng `MessageFormatter` vào module API chung thay vì để auto-config phụ thuộc vào package của ứng dụng. Ở bài tập một module này, giữ mọi file trong một Maven project giúp dễ chạy và quan sát cơ chế.

### 5.6. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showResult(
            MessageFormatter formatter, ApplicationContext context) {
        return args -> {
            System.out.println("MESSAGE=" + formatter.format("Spring"));
            System.out.println("USER_BEAN="
                    + context.containsBean("userMessageFormatter"));
            System.out.println("DEFAULT_BEAN="
                    + context.containsBean("defaultMessageFormatter"));
        };
    }
}
```

`ApplicationRunner` chỉ được chạy sau khi context đã khởi tạo thành công. Tham số `MessageFormatter formatter` minh họa DI theo kiểu bean; cả hai tình huống bên dưới đều **chỉ có một bean `MessageFormatter`**.

### 5.7. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
demo.custom=false
```

Với dự án này, chế độ non-web bảo đảm ví dụ không mở server để chờ request.

### 5.8. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.library.autoconfigure.MessageAutoConfiguration
```

Đường dẫn và tên file phải chính xác. Trong Spring Boot 3.x, auto-configuration được công bố bằng file này. Chỉ có mặt trong classpath không đủ để Boot tự quét auto-config từ package bất kỳ; danh sách imports là nguồn candidate được hỗ trợ chính thức.

### 5.9. Đóng gói và chạy tình huống A — dùng mặc định

Trong thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/user-config-order-demo-1.0.0.jar
```

Các dòng do ví dụ tự in:

```text
MESSAGE=DEFAULT: Spring
USER_BEAN=false
DEFAULT_BEAN=true
```

**Giải thích:** `demo.custom=false` không thỏa `@ConditionalOnProperty(havingValue="true")`, nên `userMessageFormatter` không được đăng ký. Khi auto-configuration xét `@ConditionalOnMissingBean(MessageFormatter.class)`, nó thấy **chưa có bean phù hợp**, vì thế đăng ký `defaultMessageFormatter`.

Đây là ý nghĩa của từ **default**: được dùng khi người dùng chưa cung cấp lựa chọn tương ứng, chứ không phải bean “luôn được tạo sẵn” rồi mới bị thay thế.

### 5.10. Chạy tình huống B — ứng dụng cung cấp bean

Giữ nguyên JAR và truyền cấu hình qua command line:

```bash
java -jar target/user-config-order-demo-1.0.0.jar --demo.custom=true
```

Các dòng do ví dụ tự in:

```text
MESSAGE=CUSTOM: Spring
USER_BEAN=true
DEFAULT_BEAN=false
```

**Giải thích:**

1. Nguồn command-line properties được Spring Boot đưa vào `Environment` với mức ưu tiên phù hợp, làm `demo.custom=true`.
2. Trong lúc xử lý cấu hình do ứng dụng khai báo, điều kiện trên `UserMessageConfiguration.userMessageFormatter()` match, nên bean definition `userMessageFormatter` được đăng ký.
3. Khi xét auto-config, `@ConditionalOnMissingBean(MessageFormatter.class)` **không match** vì đã thấy bean definition kiểu `MessageFormatter`.
4. Spring **không đăng ký** bean `defaultMessageFormatter`. Khi tạo `ApplicationRunner`, DI cung cấp bean người dùng.

Chú ý câu 3 nói về **định nghĩa bean**; nó không đòi hỏi user bean phải được tạo instance trước lúc kiểm tra điều kiện.

### 5.11. Quan sát điều kiện trong log

Có thể bật báo cáo điều kiện:

```bash
java -jar target/user-config-order-demo-1.0.0.jar --demo.custom=true --debug
```

Tìm `MessageAutoConfiguration` hoặc `defaultMessageFormatter` trong *Condition Evaluation Report*. Khi `demo.custom=true`, điều kiện missing-bean thường được ghi là **không khớp** vì đã có `MessageFormatter`; khi property false, nó khớp. Tên dòng và nội dung diễn giải chi tiết có thể khác theo bản Spring Boot và log configuration.

## 6. “Xét sau” khác “khởi tạo sau”: ba lớp thời gian

### 6.1. Thời điểm 1 — khám phá candidate

Boot phát hiện danh sách tên class auto-config từ `AutoConfiguration.imports`. Việc một candidate **có tên trong imports** chỉ có nghĩa Boot có thể xem xét nó. Candidate có thể bị loại bởi filter/conditional và không tạo bean nào.

### 6.2. Thời điểm 2 — xử lý điều kiện và đăng ký bean definition

Spring xem xét những điều kiện thích hợp và quyết định có đưa bean definitions vào context không. Với `@ConditionalOnMissingBean`, **những definitions đã được xử lý** là thông tin quyết định.

Nguyên tắc áp dụng thực tế:

- Các bean definitions của ứng dụng được xử lý trước auto-config, giúp auto-config nhường chỗ theo kiểu bean hoặc tên bean.
- Nếu một bean chỉ được tạo bởi **auto-configuration khác**, điều kiện missing-bean có thể phụ thuộc **thứ tự giữa các auto-configuration**.
- Nếu bean chỉ được đăng ký **muộn bằng cơ chế đặc biệt**, không thể tự giả định rằng mọi điều kiện trước đó sẽ nhìn thấy nó.

Đây là lý do không nên đặt `@ConditionalOnMissingBean` tùy tiện trong mọi lớp cấu hình thường để “giải quyết tranh chấp”.

### 6.3. Thời điểm 3 — tạo bean instances và injection

Spring tạo các singleton không lazy theo quá trình refresh context, giải quyết dependency constructor, callback và những quan hệ `@DependsOn`.

**Thứ tự auto-configuration chỉ quyết định thứ tự áp dụng/đăng ký bean definitions**, không bảo đảm thứ tự khởi tạo bean instance. Bean X được khai báo trong auto-config xuất hiện trước auto-config Y vẫn có thể phải chờ bean Y tạo trước nếu X phụ thuộc Y.

Bởi vậy, ý tưởng “bean mặc định được xét sau = nó được `new` sau mọi bean người dùng” là không chính xác.

### 6.4. Sơ đồ các trạng thái cho một loại bean

```text
Có user bean definition kiểu T ở thời điểm xét?
                 |
           +-----+------+
           |            |
          Có           Không
           |            |
    @ConditionalOnMissingBean(T)
    không khớp         khớp (*)
           |            |
    Không đăng ký    Đăng ký
    default T        default T
           |            |
           +-----+------+
                 |
         Khởi tạo và DI sau đó
```

`(*)` giả định các điều kiện khác cũng thỏa, chẳng hạn `@ConditionalOnClass`, `@ConditionalOnProperty` và điều kiện về môi trường. Sơ đồ không hàm ý bean mặc định luôn tạo nếu không có user bean.

## 7. Tránh nhầm back-off với ghi đè bean và chọn bean ưu tiên

Có ba hiện tượng khác nhau:

| Hiện tượng | Mô tả | Ví dụ |
| --- | --- | --- |
| **Back-off theo điều kiện** | Default **không được đăng ký** khi bean người dùng phù hợp đã tồn tại | `@ConditionalOnMissingBean(MessageFormatter.class)` |
| **Ghi đè bean definition** | Định nghĩa mới cùng **tên bean** thay thế định nghĩa đã có, tùy cấu hình và chính sách container | Trường hợp xung đột tên bean; Spring Boot mặc định không cho phép overriding |
| **Chọn candidate khi injection** | Nhiều bean vẫn tồn tại, nhưng DI chọn một bean theo qualifier hoặc primary | `@Primary`, `@Qualifier` |

Trong ví dụ chạy ở phần 5, `DEFAULT_BEAN=false` ở trường hợp B chính là **back-off**. Nó **không phải** việc bean mặc định được tạo rồi bị người dùng ghi đè.

`@Primary` **không làm auto-config tự nhường chỗ** nếu điều kiện auto-config không quan tâm đến kiểu/tên bean đó. `@Primary` chỉ giúp chọn một bean phù hợp khi có nhiều ứng viên trong DI. Nếu có nhiều bean cùng interface nhưng không thể phân giải, Spring có thể báo lỗi *NoUniqueBeanDefinitionException*.

Spring Boot mặc định đặt `spring.main.allow-bean-definition-overriding=false` trong nhiều dòng phiên bản hiện đại (trong đó có Boot 3.x). Không nên bật cờ này để chữa các lỗi bean definition trùng tên khi chưa hiểu nguồn đăng ký. Back-off đúng cách thường rõ ràng và an toàn hơn thao tác ghi đè.

## 8. Hai auto-configuration phụ thuộc nhau cần xem xét ordering

Ví dụ: auto-config A đăng ký `CacheClient`; auto-config B đăng ký `CacheMetrics` **chỉ nếu có `CacheClient`**. Nếu B được xử lý trước A, `@ConditionalOnBean(CacheClient.class)` trong B có thể không nhìn thấy bean definition của A.

Trong Spring Boot, có thể mô tả thứ tự giữa các auto-config:

```java
@AutoConfiguration(after = CacheClientAutoConfiguration.class)
public class CacheMetricsAutoConfiguration {
    // Bean conditions được xem xét sau định nghĩa liên quan từ A.
}
```

Đây chỉ là một **đoạn minh họa**, vì không cung cấp class `CacheClientAutoConfiguration` hay phần import trong tài liệu này. Khi không muốn tham chiếu class trực tiếp, có thể dùng `afterName = "com.example.CacheClientAutoConfiguration"` nếu thích hợp.

Các công cụ liên quan trong Boot 3.x gồm:

- `@AutoConfiguration(before = ...)` và `@AutoConfiguration(after = ...)`;
- `beforeName` và `afterName` khi thứ tự được khai báo theo tên class;
- `@AutoConfigureBefore` / `@AutoConfigureAfter`;
- `@AutoConfigureOrder` cho quan hệ thứ tự auto-config tổng quát.

**Giới hạn:** những lựa chọn này sắp xếp **định nghĩa bean của auto-config**; chúng không bảo đảm thứ tự *khởi tạo instance*. Hãy dùng dependency injection và `@DependsOn` nếu bài toán thực sự là thứ tự tạo bean.

Nếu hai auto-config cùng có `@ConditionalOnMissingBean(CacheClient.class)` và cả hai đều có thể tạo bean cùng kiểu, thiết kế cần xác định **default ưu tiên** rõ ràng. Thứ tự auto-config có thể quyết định ai được xét trước; không nên để hành vi trọng yếu phụ thuộc vào thứ tự không được khai báo.

## 9. Những trường hợp cần thận trọng

### 9.1. Bean người dùng chỉ có theo profile/condition

```java
@Bean
@Profile("production")
MessageFormatter prodFormatter() {
    return target -> "PROD: " + target;
}
```

Khi profile `production` không active, phương thức đó **không đăng ký bean definition**, do vậy default có thể match. Auto-config không “nhìn thấy” những bean của profile không được áp dụng như bean đang hoạt động. Mã trên là đoạn minh họa trong một class cấu hình có sẵn, không phải một project độc lập.

### 9.2. Người dùng có bean cùng tên, nhưng khác kiểu

Một điều kiện kiểm tra `name = "reporter"` và một điều kiện kiểm tra `value = Reporter.class` đưa ra hai kết luận khác nhau. Điều kiện theo **tên** không chỉ quan tâm kiểu Java, còn điều kiện theo **type** không chỉ quan tâm bean name. Phải đọc chính xác điều kiện từng auto-config.

### 9.3. Bean được định nghĩa quá muộn

Nếu một extension đăng ký bean sau thời điểm `@ConditionalOnMissingBean` đã được đánh giá, sự hiện diện của bean đó không tự quay ngược thời gian để huỷ quyết định đăng ký trước đó. Vì vậy code tạo bean bằng cơ chế tùy biến muộn phải hiểu lifecycle của `BeanDefinitionRegistryPostProcessor`, configuration processing và auto-config, thay vì giả định bất kỳ bean nào cuối cùng có trong context đều được xét từ đầu.

### 9.4. Bean nằm ở parent context

`@ConditionalOnBean` và `@ConditionalOnMissingBean` có thể xét hệ phân cấp `ApplicationContext`. Thuộc tính `search` cho phép kiểm soát phạm vi, ví dụ chỉ xem context hiện tại. Nếu ứng dụng có parent/child contexts, default có thể không xuất hiện như bạn dự đoán khi chỉ nhìn bean local.

### 9.5. Dùng `@ConditionalOnMissingBean` trên class cấu hình thường

Trong cấu hình ứng dụng thông thường, thứ tự thêm definitions có thể không đủ để bảo đảm điều kiện nhìn thấy mọi bean dự kiến. Spring Boot khuyến nghị giới hạn việc dùng bean conditions này chủ yếu cho **auto-configuration**, nơi những definitions của ứng dụng được xử lý trước. Nếu mục tiêu là cấu hình mặc định cho thư viện, nên xây dựng auto-config chính thức và đăng ký qua imports file.

### 9.6. Tự động scan class auto-config

Không nên gắn `@Component` cho auto-config và đưa nó vào vùng component scanning để “cho chắc”. Auto-config được tạo để import qua cơ chế của Boot; quét nó như component ứng dụng có thể làm thứ tự và điều kiện trở nên khác với thiết kế ban đầu. Tài liệu Spring Boot hướng dẫn **không để auto-config bị component scanning chọn**.

### 9.7. Runtime thay đổi một property không nhất thiết lập tức thay lại bean

Các điều kiện để **đăng ký bean** thường được đánh giá khi xây dựng/refresh context. Thay giá trị ở file hoặc môi trường sau khi app đã chạy **không tự bảo đảm** bean definition sẽ được thay thế ngay. Cơ chế refresh/dynamic reconfiguration, nếu cần, là bài toán riêng. Ví dụ phần 5 yêu cầu **chạy lại ứng dụng** với tham số khác để quan sát hai cấu hình.

## 10. Quy trình gỡ lỗi khi bean mặc định không xuất hiện

Giả sử bạn muốn một bean auto-config nhưng không thấy nó. Đi theo quy trình này:

1. **Tìm candidate:** Kiểm tra auto-config class thực sự nằm trong `AutoConfiguration.imports` của dependency/JAR đúng phiên bản; có bị exclude bởi `@SpringBootApplication(exclude=...)` hay `spring.autoconfigure.exclude` không?
2. **Đọc điều kiện cấp class:** Có thiếu SDK trên classpath, sai property, sai web application type, thiếu resource, sai profile không?
3. **Đọc điều kiện cấp `@Bean`:** Có `@ConditionalOnMissingBean` nào? Nó kiểm tra **type**, **name**, annotation hay ngữ cảnh cha/con?
4. **Liệt kê bean definitions hiện có:** Người dùng có `@Bean` hoặc component tương ứng chưa? Type được khai báo trong method signature có đủ rõ để Spring nhận diện không?
5. **Kiểm tra thứ tự giữa auto-configs:** Nếu điều kiện cần bean từ auto-config khác, ordering đã xác định đúng chưa?
6. **Xem báo cáo điều kiện:** Bật `--debug` để tìm *Condition Evaluation Report*. Kết luận “did not match” có thể là hành vi chính xác, không phải lỗi.
7. **Chỉ sau đó mới xem DI:** Có thật sự thiếu bean hay có nhiều bean, `@Qualifier` sai, `@Primary` không như mong đợi hoặc vòng phụ thuộc?

Nếu có `spring-boot-starter-actuator` và endpoint được cấu hình exposure phù hợp, `/actuator/conditions` cung cấp thông tin điều kiện. Endpoint này không mặc định mở cho mọi request; tránh đưa dữ liệu chẩn đoán nhạy cảm ra public.

Một mẫu đọc lỗi:

- **Default không có, user bean tồn tại:** thường là back-off đúng thiết kế.
- **Cả default và user bean đều tồn tại:** kiểm tra xem condition có kiểm tra **đúng type/name** không, hoặc definitions có được xử lý ở giai đoạn không mong đợi.
- **Không có bean nào:** xem điều kiện class/property, imports, profile và bean user có thực sự được đăng ký chưa.
- **Context lỗi vì trùng tên bean:** đó là xung đột bean definition; đừng nhầm với `@ConditionalOnMissingBean` khi điều kiện không được khai báo đúng.
- **Nhiều bean cùng type, injection lỗi:** đây là bài toán chọn ứng viên DI, không nhất thiết là auto-config không chạy.

## 11. Những hiểu nhầm thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Auto-config chỉ chạy sau khi tất cả bean ứng dụng đã được tạo instance.” | **Sai** | Đảm bảo quan trọng là về **đăng ký bean definitions**, không phải tạo instances trước |
| “`@ConditionalOnMissingBean` xét mọi bean sẽ xuất hiện trong tương lai.” | **Sai** | Điều kiện dựa trên bean definitions đã được xử lý tới thời điểm đánh giá |
| “Tôi khai báo bean cùng kiểu nên default được tạo rồi bị đè.” | **Thường sai** | Nếu default có missing-bean condition, nó có thể **không được đăng ký ngay từ đầu** |
| “Chỉ cần đặt `@Primary` là auto-config không tạo bean của nó.” | **Sai** | Primary ảnh hưởng chọn candidate khi DI; back-off do điều kiện đăng ký |
| “Hai auto-config cần phụ thuộc thứ tự tạo instances thì dùng `after`.” | **Sai mục đích** | `after` chủ yếu đổi thứ tự áp dụng/định nghĩa; thứ tự khởi tạo phụ thuộc quan hệ giữa beans |
| “`@ConditionalOnMissingBean` an toàn ở bất kỳ `@Configuration` nào.” | **Không bảo đảm** | Bean conditions nhạy với thứ tự xử lý definitions; Boot khuyến nghị dùng trong auto-config |
| “Có tên trong `AutoConfiguration.imports` thì bean mặc định chắc chắn sẽ tồn tại.” | **Sai** | Imports nêu candidates, các điều kiện vẫn có thể không match |
| “Thay `demo.custom` khi app đang chạy là default và user bean tự đổi chỗ.” | **Không mặc định** | Những điều kiện đăng ký bean được xét khi xây dựng context |

## 12. Câu hỏi luyện tập

**Câu 1.** Bean `@Bean MessageFormatter userFormatter()` đã được đăng ký từ user `@Configuration`. Auto-config có `@ConditionalOnMissingBean(MessageFormatter.class)`. Auto-config có tạo default không?

**Đáp án:** Trong cấu hình bình thường và không có điều kiện đặc biệt khác, **không**. Điều kiện missing-bean nhìn thấy definition kiểu `MessageFormatter` nên back off.

**Câu 2.** Có cần gọi `userFormatter()` trước rồi mới xét điều kiện trên không?

**Đáp án:** **Không**. Bean conditions xem metadata/bean definitions đã xử lý, không cần tạo mọi instance trước.

**Câu 3.** Vì sao Bean A do auto-config X cung cấp có thể không được nhìn thấy bởi `@ConditionalOnBean(A.class)` trong auto-config Y?

**Đáp án:** Y có thể được xử lý trước khi definition A từ X được đăng ký. Hãy xem quan hệ `before`/`after` giữa các auto-configuration và điều kiện khác.

**Câu 4.** Nếu hai bean cùng kiểu vẫn tồn tại, `@Primary` giúp gì?

**Đáp án:** Giúp Spring chọn ứng viên ưu tiên khi DI, nhưng **không ngăn việc đăng ký** các bean khác.

**Câu 5.** Trong ví dụ, khi `demo.custom=true`, vì sao `DEFAULT_BEAN=false`?

**Đáp án:** User bean definition được đăng ký trước. Khi auto-config xét missing-bean, điều kiện không khớp nên bean default **không được thêm vào context**.

**Câu 6.** Nếu dùng `spring.autoconfigure.exclude` để bỏ `MessageAutoConfiguration`, đồng thời `demo.custom=false`, chuyện gì xảy ra với ví dụ?

**Đáp án:** Không có user formatter lẫn default formatter; `ApplicationRunner` yêu cầu `MessageFormatter` và quá trình khởi động **thất bại vì thiếu dependency**. Loại trừ auto-config không tự tạo phương án thay thế.

## 13. Tài liệu đối chiếu

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): mô hình mặc định và cách cấu hình người dùng thay thế phần auto-configuration.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): thứ tự định nghĩa, `@ConditionalOnMissingBean`, điều kiện theo bean, imports file và thử nghiệm auto-config.
- [Spring Boot — ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): điều kiện và phạm vi đánh giá dựa trên bean definitions đã xử lý.

**Điểm cần nhớ:** Spring Boot cố gắng **để cấu hình của ứng dụng có quyền quyết định trước**, rồi dùng auto-configuration bổ sung những gì còn thiếu theo điều kiện. “Trước” và “sau” ở đây liên quan nhất đến **đánh giá/đăng ký bean definition**, chứ không phải thứ tự thực thi constructor hay khởi tạo bean.
