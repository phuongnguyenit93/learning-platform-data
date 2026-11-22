# Phân biệt giao diện mở rộng công khai với lớp triển khai tự cấu hình nội bộ trong Spring Boot

## 1. Câu hỏi thiết kế: người dùng được mở rộng cái gì và không nên phụ thuộc vào cái gì?

Khi một thư viện cung cấp **Spring Boot auto-configuration**, người dùng thường chỉ cần thêm một starter rồi sử dụng bean được tạo. Nhưng một thư viện tốt còn cần hỗ trợ những tình huống: thay implementation mặc định, thay đổi một bước xử lý, đăng ký callback, cấu hình qua properties hoặc tắt một auto-configuration. Để làm vậy, phải phân biệt **hợp đồng mở rộng công khai (public extension API/SPI)** với **mã triển khai auto-configuration nội bộ**.

- **Public API:** các interface, class, annotation, kiểu dữ liệu và property mà thư viện **chủ đích công bố để ứng dụng gọi và tích hợp**. Ví dụ `GreetingClient` cho phép ứng dụng gọi `greet(...)` mà không biết class mặc định cụ thể.
- **Public SPI / extension point:** hợp đồng mà ứng dụng hoặc plugin **được phép tự triển khai hoặc đăng ký** để thay đổi hành vi thư viện. Ví dụ `GreetingCustomizer` cho phép ứng dụng đăng ký callback tùy biến lời chào, hoặc tự cung cấp một bean `GreetingClient` thay cho default.
- **Internal implementation:** class, nested configuration, thuật toán khởi tạo, bean factory methods và tên bean mà thư viện dùng **để hiện thực mặc định**. Ví dụ `DefaultGreetingClient` được tạo trong `AcmeGreetingAutoConfiguration`, nhưng ứng dụng không cần `new DefaultGreetingClient(...)`.

**Một class Java khai báo `public` không tự động đồng nghĩa với hợp đồng công khai mà nhà phát triển cam kết ổn định.** Trong Spring Boot, chính auto-configuration class thường phải có tên class có thể tham chiếu và được liệt kê trong file imports. Tuy nhiên, tài liệu Spring Boot nói rõ: đối với auto-configuration class, **khía cạnh được xem như public API là tên class để loại trừ cấu hình**; nội dung của class (bao gồm nested configuration và `@Bean` methods) là nội bộ và không được khuyến nghị sử dụng trực tiếp.

Mục tiêu của bài: xác định ranh giới extension/API/internal, xây một demo Java 17+ có **public interface**, **internal default implementation**, **auto-configuration có điều kiện** và **điểm mở rộng bằng bean**, rồi hiểu cách giữ tương thích cho người dùng khi nâng cấp thư viện.

## 2. Cách nhận biết hai lớp hợp đồng

| Tiêu chí | API/SPI được công bố cho ứng dụng | Lớp triển khai / auto-config nội bộ |
| --- | --- | --- |
| Người sử dụng chính | Application, plugin, code business | Spring Boot container và tác giả thư viện |
| Trách nhiệm | Định nghĩa **làm được gì**, cách mở rộng/tùy biến hợp lệ | Định nghĩa **mặc định được tạo như thế nào**, trong điều kiện nào |
| Ví dụ | `GreetingClient`, `GreetingCustomizer`, các configuration properties được tài liệu hóa | `DefaultGreetingClient`, phương thức `@Bean` mặc định, nested `@Configuration` |
| Ứng dụng có nên `new` trực tiếp? | Có thể tạo implementation do mình sở hữu theo contract | Không nên `new` implementation nội bộ của thư viện |
| Độ ổn định dự kiến | Do chính sách tương thích/versioning của thư viện quy định; nên công bố rõ | Có thể refactor không cần giữ các chi tiết triển khai, trừ tên class auto-config được sử dụng cho exclusion/ordering |
| Điểm thay thế | Tự khai báo bean cùng API, callback/customizer, property hoặc bean qualifier được thiết kế | `@ConditionalOnMissingBean` sẽ cho bean mặc định nhường chỗ |
| Vấn đề khi phá vỡ | Consumer code có thể không compile, API behavior đổi, callback không còn chạy | Consumer code chỉ hỏng nếu đã phụ thuộc vào implementation detail, nhưng lỗi vẫn có thể là vấn đề tương thích nếu đã vô tình để lộ internal |
| Nên document gì? | Phương thức, semantics, thread safety, lifecycle, order, config keys, fallback | Cơ chế vừa đủ để giải thích điều kiện và troubleshooting; không quảng bá như extension point |

**Phân biệt API và SPI:** API thường là thứ consumer **gọi**; SPI là thứ consumer **triển khai/đăng ký**. Chúng có thể là cùng một interface. Ví dụ `GreetingClient` là API để gọi `greet` và cũng là SPI để cung cấp implementation thay thế. Một callback như `GreetingCustomizer` thường mang ý nghĩa extension point rõ ràng hơn.

Đừng đánh giá chỉ bằng tên package `internal` hoặc `impl`. Mục đích công bố, Javadoc, tài liệu và cam kết compatibility mới quyết định một type có phải extension contract hay không. Package phân lớp giúp nhận diện, nhưng không thay thế tài liệu.

## 3. Vì sao không nên gọi trực tiếp phương thức trong auto-configuration?

Giả sử Spring Boot có auto-config:

```java
@AutoConfiguration
public class ExampleAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Transport.class)
    Transport transport() {
        return new DefaultTransport();
    }
}
```

Đây là **mã minh họa**: `Transport` và `DefaultTransport` chưa được định nghĩa nên không phải chương trình biên dịch độc lập.

Cách sử dụng **đúng về ranh giới**:

```java
@Service
public class ShippingService {
    private final Transport transport;

    public ShippingService(Transport transport) {
        this.transport = transport;
    }
}
```

Ứng dụng phụ thuộc vào **interface `Transport`** và nhận bean từ container. Auto-configuration có thể chọn default, hoặc người dùng có thể đăng ký một implementation riêng.

Cách sử dụng **không nên**:

```java
// Không lấy auto-configuration class làm API nhà máy ứng dụng.
Transport transport = new ExampleAutoConfiguration().transport();
```

Những vấn đề:

1. Lời gọi Java trực tiếp có thể bỏ qua `@ConditionalOnMissingBean`, dependency injection, bean lifecycle và những proxy/transformations do container áp dụng.
2. Với `@AutoConfiguration` của Boot 3.x, cấu hình có `proxyBeanMethods=false`; gọi trực tiếp `@Bean` method không được chặn như một lookup của bean container.
3. Phương thức `transport()` có thể bị đổi tên, chia nhỏ, hoặc chuyển sang một nested configuration mà không làm thay đổi **công khai** của thư viện.
4. Ngay cả khi class auto-config được khai báo `public`, đó vẫn **không phải lời mời** consumer tự gọi logic khởi tạo nội bộ.
5. Nếu thư viện đổi implementation từ `DefaultTransport` sang implementation khác, code business nên tiếp tục hoạt động miễn hành vi `Transport` vẫn đúng contract.

**Nguyên tắc:** Consumer gọi **bean qua interface**; container và auto-config quyết định **cách cung cấp bean**. Nếu cần thay đổi quyết định mặc định, consumer dùng extension point được thiết kế thay vì nhúng đường import của class nội bộ vào business code.

## 4. Tên auto-configuration class là ngoại lệ đáng chú ý

Tài liệu Spring Boot xác nhận dù một auto-configuration class mang mức truy cập `public`, **tên class** là phần được xem như public API vì ứng dụng có thể muốn **loại trừ auto-configuration**:

```properties
spring.autoconfigure.exclude=com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration
```

Một cách khác:

```java
@SpringBootApplication(excludeName =
    "com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration")
public class DemoApplication {
}
```

Đây là **hai ví dụ thay thế**, không nên đồng thời exclude auto-config trong demo đang sử dụng default. Tên class trong `excludeName` và property phải là tên class đúng, không phải tên bean.

Tuy nhiên, **chỉ vì được phép reference tên để exclude**, không có nghĩa bạn nên sử dụng các phương thức `@Bean`, nested class hay constructor của auto-config như API. Có thể cần làm mới:
- logic điều kiện `@ConditionalOnClass` / `@ConditionalOnProperty`;
- thứ tự các method và cách tách cấu hình con;
- class implementation phía sau bean;
- tên method và tên bean được sinh ra (trừ khi thư viện đã công bố bean name như một hợp đồng riêng).

Khi một **public auto-configuration class đã phát hành đổi tên/package**, hệ sinh thái có thể tham chiếu tên cũ qua `before/after`, `spring.autoconfigure.exclude` hoặc `excludeName`. Spring Boot hỗ trợ tệp:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Ví dụ:

```properties
com.acme.greeting.autoconfigure.LegacyGreetingAutoConfiguration=com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration
```

Tệp `AutoConfiguration.imports` phải được cập nhật để chỉ chứa **class mới**. `AutoConfiguration.replacements` giúp Spring Boot biết quan hệ giữa tên cũ và tên mới trong những đường ordering/exclusion được hỗ trợ; đây không phải cơ chế thay thế mọi thay đổi API hay mọi tham chiếu Java đã biên dịch.

Nếu một ứng dụng có:
```java
import com.acme.greeting.autoconfigure.LegacyGreetingAutoConfiguration;
```
và trực tiếp biên dịch phụ thuộc class cũ, việc thêm replacements file không bảo đảm rằng mã Java đó sẽ tự compile sau khi class cũ bị xóa. Đó là ví dụ vì sao consumer không nên coi class auto-config là type nghiệp vụ.

## 5. Kiến trúc thư viện: công khai hợp đồng, giữ default ở bên trong

Một cách tổ chức dễ mở rộng:

```text
acme-greeting/
├── api/
│   ├── GreetingClient.java       # Public API/SPI
│   └── GreetingCustomizer.java   # Public extension callback
└── autoconfigure/
    ├── AcmeGreetingAutoConfiguration.java  # Internal logic; class name can be excluded
    └── DefaultGreetingClient.java          # Internal default implementation
```

Trong bản phát hành thực tế, các package có thể nằm trong module riêng:

- `acme-greeting-core` hoặc `acme-greeting-api`: định nghĩa API/SPI và những kiểu dữ liệu công khai.
- `acme-greeting-autoconfigure`: chọn bean mặc định, kiểm tra điều kiện và áp dụng cấu hình.
- `acme-greeting-spring-boot-starter`: dependency tổng hợp giúp ứng dụng dùng nhanh.

Đây **chỉ là một phương án**. Spring Boot không bắt buộc mọi starter phải tách ba module; với thư viện nhỏ, một module kết hợp API + auto-config có thể đủ tốt. Điều quan trọng là **biên giới sử dụng**, không phải số lượng artifact.

**API/SPI nên nêu rõ:**
- dạng input/output, nullability, ngoại lệ, concurrency/thread-safety;
- điều kiện callback được gọi, tần suất và thứ tự;
- hành vi khi nhiều implementation/callback cùng có;
- fallback khi không cung cấp implementation;
- cách thay default bằng bean phù hợp.

**Internal implementation có thể:**
- đổi thuật toán, class nội bộ, constructor;
- chuyển đổi factory method hoặc nested configuration;
- thêm cache, thread pool, instrumentation;
- thay thư viện phụ trợ nếu hợp đồng và hành vi công khai vẫn được giữ.

Để tránh vô tình tạo API không cần thiết, các implementation chỉ dùng trong package cấu hình có thể để **package-private**. Java compile sẽ chặn consumer ở package khác sử dụng class đó trực tiếp; ranh giới kỹ thuật và lời cam kết tài liệu hỗ trợ nhau.

## 6. Ví dụ hoàn chỉnh Java 17+ và Spring Boot 3.3.13

Ví dụ sau là một dự án Maven **một module** để bạn có thể sao chép và chạy. Nó minh họa đầy đủ:

1. `GreetingClient` là API để ứng dụng gọi hoặc triển khai.
2. `GreetingCustomizer` là extension point có thể đăng ký bằng `@Bean`.
3. `DefaultGreetingClient` là class **package-private** mà app không biết.
4. `AcmeGreetingAutoConfiguration` là class `@AutoConfiguration` trong package riêng, tạo bean mặc định qua `@ConditionalOnMissingBean(GreetingClient.class)`.
5. `DemoApplication` chỉ import API, không import class nội bộ.
6. Ba chế độ chạy: mặc định, **decorate bằng callback**, **override toàn bộ implementation**.

### 6.1. Cấu trúc thư mục

```text
public-spi-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── com/acme/greeting/
    │   │   ├── api/
    │   │   │   ├── GreetingClient.java
    │   │   │   └── GreetingCustomizer.java
    │   │   └── autoconfigure/
    │   │       ├── AcmeGreetingAutoConfiguration.java
    │   │       └── DefaultGreetingClient.java
    │   └── com/example/app/
    │       ├── DemoApplication.java
    │       └── UserGreetingConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Package `com.example.app` **không bao trùm** `com.acme.greeting.autoconfigure`. Điều này giúp quan sát auto-config được Spring Boot nhận từ file imports thay vì vô tình bị component scan của ứng dụng đưa vào.

### 6.2. `pom.xml`

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
    <artifactId>public-spi-demo</artifactId>
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

`spring-boot-starter` đủ cho ví dụ non-web và `ApplicationRunner`. Trong starter thật, dependency API/third-party có thể được tách theo tính bắt buộc/tùy chọn để không ép ứng dụng kéo vào mọi integration.

### 6.3. `src/main/java/com/acme/greeting/api/GreetingClient.java`

```java
package com.acme.greeting.api;

/**
 * Public contract for producing greeting messages.
 */
@FunctionalInterface
public interface GreetingClient {
    String greet(String name);
}
```

Ứng dụng có thể gọi `GreetingClient.greet` hoặc tự viết implementation. Contract ở đây rất nhỏ: nhận `name` và trả thông điệp. Trong thư viện thật cần document rõ có cho phép `null`, thread safety và lỗi khi input không hợp lệ.

**Không có `@Component`** trên interface: đó là hợp đồng Java, không tự tạo Spring bean. Bean sẽ được cung cấp từ auto-config hoặc từ cấu hình người dùng.

### 6.4. `src/main/java/com/acme/greeting/api/GreetingCustomizer.java`

```java
package com.acme.greeting.api;

/**
 * Public extension hook that can transform a greeting.
 */
@FunctionalInterface
public interface GreetingCustomizer {
    String customize(String message);
}
```

Đây là **SPI/callback** cho người dùng tùy biến một bước xử lý mà không cần triển khai lại `GreetingClient`. Thiết kế này minh họa một extension point; không phải mọi thư viện đều cần thêm callback nếu một interface thay thế đã đủ.

Ở demo, các customizer sẽ được gọi theo thứ tự `ObjectProvider.orderedStream()` và được kỳ vọng trả string không null. Một SPI thực tế nên ghi rõ thứ tự, side effects, null policy và exception policy trước khi phát hành công khai.

### 6.5. `src/main/java/com/acme/greeting/autoconfigure/DefaultGreetingClient.java`

```java
package com.acme.greeting.autoconfigure;

import java.util.List;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;

final class DefaultGreetingClient implements GreetingClient {
    private final List<GreetingCustomizer> customizers;

    DefaultGreetingClient(List<GreetingCustomizer> customizers) {
        this.customizers = List.copyOf(customizers);
    }

    @Override
    public String greet(String name) {
        String result = "Hello, " + name + "!";
        for (GreetingCustomizer customizer : customizers) {
            result = customizer.customize(result);
        }
        return result;
    }
}
```

**Đây là internal implementation:**

- Class có mức truy cập package-private (không có `public`), nên code ở `com.example.app` không thể `import DefaultGreetingClient`.
- Nó hiện thực public API `GreetingClient` và có thể gọi những extension callbacks được cung cấp.
- Người dùng chỉ biết kết quả `greet`, không phụ thuộc vào class nội bộ này.
- Class có thể đổi cấu trúc trong một bản cập nhật, miễn hợp đồng công khai vẫn được đáp ứng.

Không gắn `@Component` cho class này, vì chúng ta muốn **auto-configuration có điều kiện** chủ động quyết định có đăng ký default hay không.

### 6.6. `src/main/java/com/acme/greeting/autoconfigure/AcmeGreetingAutoConfiguration.java`

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingClient.class)
    GreetingClient greetingClient(
            ObjectProvider<GreetingCustomizer> customizers) {
        return new DefaultGreetingClient(
                customizers.orderedStream().toList());
    }
}
```

Ở đây có ba quyết định quan trọng:

1. `@AutoConfiguration`: lớp này là configuration candidate do Spring Boot import theo cơ chế `AutoConfiguration.imports`, không phải một component mà app tìm qua package scan.
2. `@ConditionalOnMissingBean(GreetingClient.class)`: nếu ứng dụng đã khai báo bean tương thích với API `GreetingClient`, **default không được đăng ký**. Đây là điểm thay thế extension đã thiết kế.
3. `ObjectProvider<GreetingCustomizer>`: cho phép thu thập zero hoặc nhiều callback. `orderedStream()` dùng thứ tự các bean customizer theo cơ chế ordering của Spring; nếu cần thứ tự cụ thể trong library, hãy document và kiểm thử.

Phương thức `greetingClient` trả `GreetingClient`, tức **kiểu public contract**. Trong bài này điều kiện cũng kiểm tra chính `GreetingClient.class`, nên type metadata phù hợp. Với auto-config phức tạp cần điều kiện phân biệt các concrete subtypes, hãy cân nhắc hướng dẫn Spring Boot về kiểu trả về `@Bean` đủ cụ thể, đồng thời tránh vô tình biến internal class thành public API.

**Vì sao class `AcmeGreetingAutoConfiguration` vẫn phải `public`?** Nó cần được nhận diện/nạp như class cấu hình độc lập và tên class có thể dùng để exclude. Nhưng code ứng dụng vẫn không nên gọi `greetingClient(...)` trực tiếp. Để hỗ trợ người dùng, tác giả thư viện công bố `GreetingClient` và `GreetingCustomizer` làm API/SPI.

### 6.7. `src/main/java/com/example/app/UserGreetingConfiguration.java`

```java
package com.example.app;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserGreetingConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "mode",
            havingValue = "decorate")
    GreetingCustomizer vietnameseCustomizer() {
        return message -> message.replace("Hello,", "Xin chào,");
    }

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "mode",
            havingValue = "override")
    GreetingClient customGreetingClient() {
        return name -> "CUSTOM: " + name;
    }
}
```

Cả hai phương thức là **cấu hình ứng dụng**, trong package được `@SpringBootApplication` quét. Chúng tạo hai kiểu extension:

- `demo.mode=decorate`: người dùng cung cấp callback `GreetingCustomizer`. Auto-configuration vẫn cung cấp `GreetingClient` mặc định, nhưng implementation có thêm một bước do người dùng mở rộng.
- `demo.mode=override`: người dùng cung cấp **toàn bộ `GreetingClient` riêng**. Điều kiện missing-bean làm factory mặc định của auto-config nhường chỗ.

Chú ý: ứng dụng **chỉ import hai interface ở package `api`**, không import `DefaultGreetingClient` hoặc tự tạo `AcmeGreetingAutoConfiguration`. Hai đường tùy biến đã có ý nghĩa rõ ràng mà không cần thao tác vào chi tiết nội bộ.

### 6.8. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;
import org.springframework.beans.factory.ObjectProvider;
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
    ApplicationRunner report(
            GreetingClient client,
            ObjectProvider<GreetingCustomizer> customizers,
            ApplicationContext context) {
        return args -> {
            System.out.println("CLIENT=" + client.greet("Spring"));
            System.out.println("DEFAULT="
                    + context.containsBean("greetingClient"));
            System.out.println("CUSTOM="
                    + context.containsBean("customGreetingClient"));
            System.out.println("CUSTOMIZERS="
                    + customizers.orderedStream().count());
        };
    }
}
```

`GreetingClient` được Spring inject vào factory method `report`. Runner dùng **public contract**, không biết implementation mặc định là loại nào. `containsBean(...)` chỉ phục vụ minh họa để biết bean factory nào đang hoạt động; production code không nên dựa vào các tên bean nội bộ này khi đã có SPI ổn định.

### 6.9. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.mode=default
```

`demo.mode` ở đây là **property riêng của ứng dụng mẫu**, không phải một tính năng được Spring Boot cung cấp sẵn và không bắt buộc phải là property public của thư viện. Các annotation điều kiện trên `UserGreetingConfiguration` của ứng dụng tự diễn giải nó.

`spring.main.web-application-type=none` giúp ứng dụng in các dòng rồi thoát; `logging.level.root=OFF` làm output ví dụ gọn hơn.

### 6.10. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration
```

Trong Spring Boot 3.x, tên class này phải nằm trong imports file để thư viện cung cấp auto-configuration candidate. Một class trong file được **xem xét** nhưng có thể không tạo bean nếu điều kiện không khớp. Tài nguyên này chứa tên auto-config class, không chứa tên của public interface `GreetingClient`, callback `GreetingCustomizer` hoặc class internal `DefaultGreetingClient`.

### 6.11. Biên dịch và chạy ba tình huống

Đứng tại thư mục chứa `pom.xml`, dùng Java 17+ và Maven:

```bash
mvn -q -DskipTests package
java -jar target/public-spi-demo-1.0.0.jar
```

**A. Mặc định, không có callback và không có user implementation**:

```text
CLIENT=Hello, Spring!
DEFAULT=true
CUSTOM=false
CUSTOMIZERS=0
```

Bean `greetingClient` được auto-config đăng ký và dùng implementation `DefaultGreetingClient`. Consumer chỉ nhận `GreetingClient`.

**B. Cung cấp callback public SPI, không thay client mặc định**:

```bash
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=decorate
```

Các dòng chương trình tự in:

```text
CLIENT=Xin chào, Spring!
DEFAULT=true
CUSTOM=false
CUSTOMIZERS=1
```

Lần này `vietnameseCustomizer` được tạo vì property khớp; `DefaultGreetingClient` áp dụng callback cho chuỗi ban đầu `Hello, Spring!`. Class mặc định vẫn được Spring quản lý. Người dùng không hề chạm vào constructor hoặc method nội bộ của auto-config.

**C. Cung cấp `GreetingClient` riêng để thay toàn bộ default**:

```bash
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=override
```

Các dòng chương trình tự in:

```text
CLIENT=CUSTOM: Spring
DEFAULT=false
CUSTOM=true
CUSTOMIZERS=0
```

`@ConditionalOnMissingBean(GreetingClient.class)` nhìn thấy bean `customGreetingClient` do ứng dụng khai báo nên **không đăng ký** default. Runner nhận bean user qua DI. Chỉ thay bean theo interface `GreetingClient`, không yêu cầu mở rộng/copy-paste code nội bộ.

Cả ba trường hợp chứng minh: cùng một **public contract** phục vụ code business, còn auto-config/implementation thay đổi theo điều kiện và extension point đã định nghĩa.

## 7. Vì sao `@ConditionalOnMissingBean` là công cụ thiết kế SPI quan trọng?

Với thư viện cung cấp default, ranh giới mở rộng thường được định nghĩa như sau:

```java
@Bean
@ConditionalOnMissingBean(GreetingClient.class)
GreetingClient greetingClient(...) {
    // return default implementation
}
```

Ý nghĩa không phải “có Spring Boot thì luôn được ghi đè bean”, mà là: **nếu có bean `GreetingClient` phù hợp ở thời điểm đánh giá, auto-config không thêm default**.

Các điều kiện bean của Spring Boot nhạy với **thứ tự xử lý bean definitions**. Tài liệu Spring Boot khuyến nghị đặt `@ConditionalOnBean` / `@ConditionalOnMissingBean` trong auto-configuration vì definitions do ứng dụng khai báo được xử lý trước. Điều này giúp SPI rõ ràng: consumer cung cấp bean, default nhường chỗ.

Để định nghĩa extension point đúng, cần quyết định **thứ được kiểm tra**:

| Điều kiện | Thế nào làm default nhường chỗ? | Rủi ro khi dùng sai |
| --- | --- | --- |
| `@ConditionalOnMissingBean(GreetingClient.class)` | Đã có bean đúng loại API/SPI | Nếu user chỉ cung cấp callback, nó không tự thay toàn bộ client |
| `@ConditionalOnMissingBean(name = "greetingClient")` | Đã có bean mang đúng tên đó | User implementation với tên khác có thể khiến cả hai bean tồn tại |
| `@ConditionalOnMissingBean(DefaultGreetingClient.class)` | Đã có implementation **nội bộ** phù hợp | Có thể không nhận ra consumer tạo implementation khác của `GreetingClient` |
| `@ConditionalOnProperty(...)` | Property bật/tắt theo điều kiện | Property không phải một interface để consumer triển khai |
| `@ConditionalOnClass(...)` | Class thư viện hiện diện trên classpath | Có class không đồng nghĩa có bean hoặc điểm mở rộng |

Vì vậy, nếu mục tiêu là người dùng **cung cấp implementation tùy chọn**, missing-bean condition thường nên bám vào **public SPI** (interface mà user có thể triển khai), không bám vào một class internal cụ thể.

Dù vậy, không có một công thức duy nhất. Trong auto-config đa feature, cần xét các ứng viên, subtype, generic, annotation và phạm vi ApplicationContext. Thiết kế phải kiểm thử rõ trường hợp app có một/nhiều bean tương ứng.

### 7.1. `@Primary` và `@Qualifier` không thay thế API design

Một ứng dụng có hai bean `GreetingClient` có thể dùng `@Primary` hoặc `@Qualifier` để chọn bean khi DI, nhưng điều này khác với `@ConditionalOnMissingBean`:

- Missing-bean condition quyết định **có tạo default hay không**.
- `@Primary`, `@Qualifier` quyết định **chọn bean nào** khi có nhiều ứng viên.
- Một callback `GreetingCustomizer` là một **điểm mở rộng khác**, không trực tiếp chọn implementation client.

Nếu đã có custom client, default của demo không được đăng ký từ đầu; không có chuyện nó được khởi tạo rồi bị người dùng thay thế sau đó.

## 8. Khi nào dùng callback, khi nào thay cả bean?

Không phải mọi nhu cầu tùy biến đều nên giải quyết bằng cách subclass implementation nội bộ.

**Chọn public configuration property** nếu chỉ cần thay một giá trị (timeout, endpoint, flag), thư viện cung cấp `@ConfigurationProperties` và kiểm tra hợp lệ. Người dùng không phải viết Java code cho thao tác đơn giản.

**Chọn callback/customizer SPI** nếu người dùng cần thay một bước cụ thể trong pipeline, chẳng hạn đổi format của message, thêm header, đăng ký codec hoặc bổ sung strategy. Contract của callback nên xác định thứ tự và thời điểm gọi; ví dụ demo dùng `GreetingCustomizer`.

**Chọn public interface + user bean override** nếu người dùng cần thay implementation một cách thực chất, ví dụ chuyển transport/messaging backend khác. `@ConditionalOnMissingBean` trên public interface cho phép default back off.

**Chọn annotation/property riêng để bật/tắt một auto-config** nếu muốn vô hiệu hóa feature mặc định. `spring.autoconfigure.exclude` hoặc `excludeName` là phương tiện loại trừ ở cấp auto-config, nhưng **không tự cung cấp bean thay thế** cho những dependency mà ứng dụng vẫn cần.

**Đừng chọn subclass một implementation nội bộ** chỉ vì nó đang có constructor public hay bạn tìm thấy tên của nó trong log. Nếu library không công bố class là extension point, bản cập nhật sau có thể thay constructor/field và làm consumer code hỏng.

## 9. Lưu ý tương thích phiên bản cho người viết starter

Khi muốn thay đổi thư viện nhưng tránh làm người dùng phải sửa code:

1. **Bảo vệ public interface contract:** thêm method abstract vào interface có consumer implementation có thể làm source/binary compatibility gặp rủi ro. Cân nhắc default method, interface mới hoặc versioned SPI tùy tình huống.
2. **Duy trì semantics của callback:** thay thứ tự, số lần gọi hoặc khả năng chạy đồng thời có thể làm plugin thay đổi hành vi dù method signature không đổi.
3. **Kiểm thử back-off:** mỗi bản phát hành cần xác nhận app cung cấp bean riêng thì default không xuất hiện; app không cung cấp thì default hoạt động.
4. **Không để lộ implementation type qua API vô ý:** method công khai nhận/trả class internal, exception type nội bộ, hoặc docs yêu cầu người dùng gọi implementation constructor sẽ tạo coupling.
5. **Tách bean name và type contract:** nếu bean name là phần tài liệu công khai, phải coi đó như một hợp đồng. Nếu không, ưu tiên hướng dẫn consumer DI theo interface hoặc qualifier đã công bố.
6. **Chú ý tên auto-config class:** đổi package/class auto-config ảnh hưởng exclusion/ordering và cần xem `AutoConfiguration.replacements` cùng cập nhật imports.
7. **Ghi rõ property schema:** nếu có `@ConfigurationProperties`, các key đã được công bố cũng là interface cấu hình; đổi key/default có thể gây breaking behavior.
8. **Khi cần optional dependency:** cô lập integration phía sau `@ConditionalOnClass`; đừng để public API bắt buộc nhắc tới class của thư viện tùy chọn nếu người dùng không nhất thiết cài thư viện đó.
9. **Tôn trọng scope/proxies/lifecycle:** user bean có thể là proxy hoặc scope đặc biệt; auto-config nên nhận bean thông qua DI/`ObjectProvider`, không gọi `new` tới một internal class rồi bỏ qua container.

**Lớp auto-configuration không phải facade công khai của thư viện.** Nó là wiring code. Public API/SPI và những cấu hình documented mới là điểm tích hợp có chủ đích.

## 10. Các sai lầm và cách sửa

| Sai lầm | Tác động | Sửa bằng |
| --- | --- | --- |
| Ứng dụng import `DefaultGreetingClient` | Bị ràng buộc vào implementation nội bộ; demo package-private còn không compile | Inject `GreetingClient` hoặc cung cấp user implementation |
| Tự `new AcmeGreetingAutoConfiguration()` rồi gọi `greetingClient` | Bỏ qua bean conditions và lifecycle; có thể không compile nếu factory không public | Để Spring Boot import và inject bean |
| Đặt `@ConditionalOnMissingBean(DefaultGreetingClient.class)` cho extension có thể override | User `GreetingClient` khác có thể không khiến default nhường | Kiểm tra đúng interface `GreetingClient.class` |
| Dùng một bean name chưa được công bố làm API | Đổi tên factory method có thể phá consumer | DI theo kiểu/qualifier được thiết kế; document tên nếu buộc phải ổn định |
| Tạo customizer nhưng kỳ vọng default biến mất | Callback không thay thế client | Muốn replace thì đăng ký bean `GreetingClient` |
| Chỉ exclude auto-config, vẫn yêu cầu bean từ nó | Khởi động thiếu dependency | Cung cấp bean thay thế hoặc không sử dụng feature |
| Auto-config nằm trong vùng `@ComponentScan` | Có thể bị đưa vào sai thời điểm hoặc trái thiết kế | Đặt package riêng và dùng `AutoConfiguration.imports` |
| Library có API public nhưng không document null/order/thread safety | Nhiều implementation diễn giải khác nhau | Mô tả rõ contract và kiểm thử tích hợp |
| Sửa nội dung `@Bean` method nội bộ nhưng bảo đảm qua tên bean chưa document | Consumer phụ thuộc implementation detail bị ảnh hưởng | Chỉ cho phép customization qua API/SPI công khai |
| Đổi class auto-config mà không cập nhật imports và replacements | Exclusion/ordering bằng tên cũ không còn đúng | Cập nhật imports và hỗ trợ replacement phù hợp |

### 10.1. Nếu `DefaultGreetingClient` hiện bị một ứng dụng dùng trực tiếp thì sao?

Tình huống này xảy ra khi thư viện vô tình công bố class implementation và consumer sử dụng nó từ lâu. Không nên coi đây là một chi tiết “không cần quan tâm” rồi xóa class ngay. Tính tương thích thực tế còn phụ thuộc người dùng đã dựa vào phần nào. Có thể phải:

- công bố SPI thay thế;
- giữ adapter/deprecated compatibility class trong thời gian chuyển tiếp;
- cung cấp migration guide;
- test cả đường cũ và đường mới trước khi phát hành major version.

Phân biệt “nên coi internal” và “có thể xóa tùy tiện mà không ảnh hưởng ai”. Public surface vô tình lọt ra vẫn có thể đã tạo phụ thuộc thực tế.

## 11. Kiểm thử contract thay vì kiểm thử chi tiết wiring

Với một starter, nên xác nhận **hành vi có thể quan sát từ phía consumer**:

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| Không khai báo extension | Có đúng một bean `GreetingClient` mặc định, chức năng `greet` đúng |
| Có `GreetingCustomizer` | Default client vẫn hoạt động và thực sự chạy callback |
| Có bean `GreetingClient` tự khai báo | Default back off, consumer nhận user implementation |
| Có nhiều callback | Thứ tự thực thi theo tài liệu và kết quả ổn định |
| Loại trừ auto-config | Không tạo default; application hiểu cách cung cấp bean khi cần |
| Không có optional SDK | Auto-config không cố load class phụ thuộc vào thư viện bị thiếu |
| Nâng phiên bản internal implementation | Consumer chỉ compile against API/SPI vẫn hoạt động |

Spring Boot cung cấp `ApplicationContextRunner` trong module test để thử nhiều cấu hình context nhỏ, còn bài minh họa `DemoApplication` ở trên dùng các lần chạy thật để dễ quan sát.

Ví dụ kiểm tra thủ công:

```bash
java -jar target/public-spi-demo-1.0.0.jar
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=decorate
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=override
```

So sánh ba kết quả ở phần 6.11. Đối với thư viện phát hành nhiều phiên bản, nên đưa các kịch bản đó vào test tự động để bắt lỗi regression của missing-bean condition, callbacks và compatibility.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `AcmeGreetingAutoConfiguration` là `public class` nhưng không nên được ứng dụng gọi `greetingClient()`?

**Đáp án:** Spring Boot xem **tên auto-configuration class** như phần public API cho exclusion. Nested configuration và phương thức `@Bean` là **nội bộ**; chúng có thể thay đổi và lời gọi trực tiếp còn bỏ qua cơ chế container.

**Câu 2.** Nếu ứng dụng muốn đổi format lời chào nhưng vẫn dùng client mặc định, extension point nào hợp lý?

**Đáp án:** Đăng ký `@Bean GreetingCustomizer`. Default client đọc callback thông qua `ObjectProvider` và áp dụng khi gọi `greet`.

**Câu 3.** Nếu ứng dụng muốn thay hoàn toàn thuật toán `greet`, cần làm gì?

**Đáp án:** Tạo bean triển khai public `GreetingClient`. `@ConditionalOnMissingBean(GreetingClient.class)` của auto-config sẽ nhường default trong điều kiện bình thường.

**Câu 4.** Trong ví dụ, `DefaultGreetingClient` không `public` có cản Spring tạo bean không?

**Đáp án:** Không. `AcmeGreetingAutoConfiguration` ở cùng package có thể gọi constructor package-private; phương thức `@Bean` trả kiểu public `GreetingClient` và container quản lý object được trả. Ứng dụng không cần biết tên concrete type.

**Câu 5.** Nếu người dùng chỉ dùng bean name `greetingClient`, đó luôn là hợp đồng công khai ổn định chứ?

**Đáp án:** Không. Chỉ được xem là contract khi thư viện **chủ đích công bố và cam kết** tên đó. Mặc định ưu tiên phụ thuộc public interface.

**Câu 6.** Vì sao condition `@ConditionalOnMissingBean(DefaultGreetingClient.class)` không phù hợp với yêu cầu “cho phép người dùng thay client bằng implementation riêng”?

**Đáp án:** Implementation riêng thường **không phải** `DefaultGreetingClient`, nên condition có thể không nhận ra user bean. Kiểm tra public interface `GreetingClient.class` mới phản ánh mục đích.

**Câu 7.** Khi đổi tên `AcmeGreetingAutoConfiguration`, cần chú ý gì?

**Đáp án:** Cập nhật `AutoConfiguration.imports`, cân nhắc `AutoConfiguration.replacements` cho các reference ordering/exclusion cũ, và không kỳ vọng file replacements sửa mọi import Java trực tiếp của consumer.

**Câu 8.** Sự khác nhau giữa API và SPI là gì trong ví dụ?

**Đáp án:** API là contract để code **gọi** (`GreetingClient.greet`); SPI cho code **mở rộng/triển khai** (`GreetingCustomizer` hoặc user implementation của `GreetingClient`). Một interface có thể đóng cả hai vai trò.

## 13. Tài liệu tham khảo

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): phần loại trừ auto-config giải thích **chỉ tên class auto-config là public API**, nội dung nested configs/bean methods là internal.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): cách công bố auto-config trong imports, `@ConditionalOnMissingBean`, class conditions, replacement file, starter modules và callback interfaces.
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): `@Configuration`, `@Bean` và cách container tạo/tiêm bean.
- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): giới thiệu `ApplicationContextRunner` cho test các điều kiện.

**Ghi nhớ:** hãy công bố **interface/callback/property phù hợp để ứng dụng mở rộng**, để Spring container cung cấp bean theo hợp đồng ấy và để class auto-configuration thực hiện phần **wiring mặc định có điều kiện**. Một class `@AutoConfiguration` có thể là `public` vì tên của nó cần dùng cho exclusion, nhưng **các phương thức `@Bean`, nested configuration và implementation nội bộ không phải extension API cho ứng dụng gọi trực tiếp**.
