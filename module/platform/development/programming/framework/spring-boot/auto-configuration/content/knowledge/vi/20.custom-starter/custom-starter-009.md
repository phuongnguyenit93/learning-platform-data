# Giới hạn dependency bắc cầu để không vô tình kích hoạt tính năng khác

## 1. Vấn đề: starter lõi có thể kéo theo cả một feature stack

Một custom starter thường được thêm vào ứng dụng bằng một dependency duy nhất. Nếu starter lõi kéo theo quá nhiều thư viện, các thư viện đó sẽ xuất hiện trên runtime classpath của mọi consumer và có thể làm Spring Boot kích hoạt thêm auto-configuration.

Ví dụ:

- Starter lõi cần một client đơn giản nhưng phụ thuộc `spring-boot-starter-web`. Ứng dụng CLI có thể bị nhận diện là Servlet web application và khởi tạo embedded server.
- Thư viện thông báo chỉ cần email ở một số ứng dụng nhưng starter cơ bản luôn kéo theo `spring-boot-starter-mail`.
- Starter dữ liệu kéo theo `spring-boot-starter-data-jpa` dù consumer chỉ cần core API; JDBC, JPA và Hibernate xuất hiện không cần thiết.
- Một SDK bên thứ ba kéo theo một starter khác qua nhiều cấp bắc cầu, dù POM trực tiếp của ứng dụng không khai báo nó.

Điều cần kiểm soát là **đồ thị dependency thực tế của consumer**, đặc biệt là runtime classpath. Chỉ nhìn dependency trực tiếp trong POM không đủ.

### Dependency có mặt và auto-configuration được kích hoạt là hai việc khác nhau

Khi một JAR xuất hiện trên runtime classpath:

1. Spring Boot có thể phát hiện class của thư viện.
2. Các auto-configuration của Spring Boot hoặc thư viện đó có thể trở thành candidate.
3. Condition như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và `@ConditionalOnMissingBean` quyết định cấu hình/bean nào được áp dụng.
4. Bean được đăng ký nếu các điều kiện tương ứng match.

Vì vậy, cần phân biệt:

- **Giới hạn dependency bắc cầu:** ngăn JAR không cần thiết đi vào runtime classpath.
- **Giới hạn kích hoạt tính năng:** nếu dependency đã có mặt, chỉ đăng ký cấu hình khi điều kiện phù hợp.

`@ConditionalOnClass` chỉ kiểm soát việc áp dụng cấu hình; nó **không xóa JAR khỏi dependency graph**. `@ConditionalOnProperty` có thể tắt tính năng của starter bạn viết, nhưng không ngăn auto-configuration của thư viện khác chạy nếu dependency của thư viện đó vẫn hiện diện.

## 2. Cấu trúc custom starter dễ kiểm soát

Spring Boot khuyến nghị tách phần auto-configuration khỏi starter aggregator. Với thư viện có nhiều flavor hoặc tính năng tùy chọn, nên tách rõ từng integration để consumer chọn đúng thứ họ cần.

```text
acme/
├── acme-core
├── acme-spring-boot-autoconfigure
├── acme-spring-boot-starter
├── acme-spring-boot-starter-web
└── acme-spring-boot-starter-mail
```

| Module | Trách nhiệm | Dependency nên chứa |
| --- | --- | --- |
| `acme-core` | API và logic nền không phụ thuộc web/mail | Chỉ dependency thực sự cần cho core |
| `acme-spring-boot-autoconfigure` | Các lớp `@AutoConfiguration` cho core | Spring Boot autoconfigure; thư viện tùy chọn được đánh dấu optional |
| `acme-spring-boot-starter` | Starter lõi | Core + autoconfigure + `spring-boot-starter` |
| `acme-spring-boot-starter-web` | Flavor dành cho web | Starter lõi + `spring-boot-starter-web` |
| `acme-spring-boot-starter-mail` | Flavor dành cho email | Starter lõi + `spring-boot-starter-mail` |

Starter aggregator thường là JAR gần như rỗng, mục đích chính là khai báo dependency. Code auto-configuration nằm ở module riêng.

Nguyên tắc thiết kế:

- Starter lõi chỉ kéo theo dependency **mọi consumer đều cần**.
- Mỗi integration tùy chọn có starter riêng.
- Không đặt `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-mail` hoặc driver database vào starter lõi nếu không phải mọi ứng dụng đều cần.
- Nếu chưa thể tách module, đánh dấu dependency tùy chọn và yêu cầu consumer khai báo lại khi dùng feature.
- Tách auto-configuration theo tính năng để mỗi cấu hình có thể được bảo vệ bằng condition phù hợp.
- Không dùng dependency exclusion ở consumer để chữa một starter do mình sở hữu nhưng được thiết kế quá rộng; sửa đồ thị dependency tại module gốc khi có thể.

## 3. Maven: optional dependency và starter theo feature

### 3.1. Dependency thông thường được truyền bắc cầu

Giả sử module A khai báo dependency B:

```text
Application -> A -> B
```

Nếu B là dependency thông thường trong POM của A, Maven sẽ đưa B vào dependency graph của ứng dụng sử dụng A, trừ khi scope hoặc exclusion thay đổi quy tắc truyền.

Ví dụ không phù hợp cho starter lõi:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Nếu đoạn này nằm trong `acme-spring-boot-starter`, mọi ứng dụng dùng starter lõi đều nhận web stack. Dù ứng dụng không có controller, Spring Boot vẫn có thể nhận diện Servlet web classpath và tạo embedded server.

### 3.2. `<optional>true</optional>` ngăn dependency được truyền tiếp

Nếu module auto-configuration cần một thư viện để compile và kiểm thử, nhưng consumer không bắt buộc phải dùng thư viện đó, Maven cho phép khai báo optional:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-mail-client</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>
```

Khi module auto-configuration được build, `acme-mail-client` vẫn có trên classpath của chính module đó. Nhưng khi một ứng dụng khác chỉ phụ thuộc module auto-configuration, Maven **không tự truyền** dependency optional này sang ứng dụng. Consumer muốn dùng mail feature phải khai báo dependency đó một cách tường minh.

Điểm cần nhớ:

- `optional=true` không có nghĩa dependency chỉ dùng lúc compile.
- Nó không gỡ dependency khỏi classpath của module đang khai báo.
- Nó thay đổi việc dependency có được truyền sang **project phụ thuộc vào module đó** hay không.
- Nếu starter tính năng cần thư viện này ở runtime, starter đó phải khai báo dependency không optional.

### 3.3. POM mẫu cho các module

Các POM dưới đây dùng Spring Boot 3.3.5 làm parent quản lý version dependency Spring. Các module Acme dùng version nội bộ `1.0.0-SNAPSHOT`.

**POM gốc: `pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>acme-core</module>
        <module>acme-spring-boot-autoconfigure</module>
        <module>acme-spring-boot-starter</module>
        <module>acme-spring-boot-starter-web</module>
        <module>demo-app</module>
    </modules>
</project>
```

**Module `acme-core`: `acme-core/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-core</artifactId>
</project>
```

**Module `acme-spring-boot-autoconfigure`: `acme-spring-boot-autoconfigure/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-spring-boot-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-core</artifactId>
            <version>1.0.0-SNAPSHOT</version>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`acme-core` là optional ở module auto-configuration để ứng dụng chỉ dùng artifact auto-configuration không bị ép nhận core library. Starter lõi sẽ khai báo `acme-core` lại như dependency bắt buộc. Test dependency chỉ phục vụ test của module, không được truyền cho consumer.

**Starter lõi: `acme-spring-boot-starter/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-spring-boot-starter</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-core</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
```

Starter lõi chỉ mang Boot core, Acme core và auto-configuration lõi. Không có `spring-boot-starter-web`.

**Starter web tùy chọn: `acme-spring-boot-starter-web/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-spring-boot-starter-web</artifactId>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
```

Web starter là opt-in rõ ràng. Chỉ ứng dụng chọn `acme-spring-boot-starter-web` mới nhận Spring MVC, embedded Servlet server và các dependency liên quan.

### 3.4. Phân biệt `optional` với Maven scopes

| Khai báo | Classpath của module hiện tại | Truyền cho consumer | Ý nghĩa |
| --- | --- | --- | --- |
| `compile` (mặc định) | Compile + runtime | Có | Dependency bình thường |
| `runtime` | Runtime + test, không compile | Có ở runtime | Chỉ cần khi chạy |
| `provided` | Compile + test | Không | Môi trường/container khác cung cấp lúc chạy |
| `test` | Test compile + test runtime | Không | Chỉ phục vụ test |
| `optional=true` | Vẫn có theo scope khai báo | Không tự truyền | Consumer phải chọn lại nếu cần |

Không dùng `provided` để giả lập dependency tùy chọn. `provided` giả định môi trường triển khai cung cấp thư viện lúc runtime; executable JAR có thể thiếu class nếu không có container cung cấp dependency đó.

`runtime` cũng không phải cách loại dependency khỏi consumer. Nó vẫn có thể được truyền vào runtime classpath và kích hoạt auto-configuration.

## 4. Gradle: hiểu đúng api, implementation, compileOnly và runtimeOnly

Gradle Java Library Plugin có các configuration với ý nghĩa khác nhau:

| Configuration | Module hiện tại | Consumer compile classpath | Consumer runtime classpath |
| --- | --- | --- | --- |
| `api` | Compile + runtime | Có | Có |
| `implementation` | Compile + runtime | Không xuất API compile | **Có** |
| `compileOnly` | Compile only | Không | Không |
| `runtimeOnly` | Runtime only | Không | **Có** |
| `testImplementation` | Test only | Không | Không |

Một nhầm lẫn phổ biến: `implementation` không có nghĩa “private nên consumer không nhận dependency”. Nó không xuất dependency vào compile API của consumer, nhưng dependency vẫn có thể đi vào **runtimeElements** và runtime classpath của consumer. Vì vậy, khai báo `implementation 'org.springframework.boot:spring-boot-starter-web'` trong một thư viện vẫn có thể kéo Spring MVC vào ứng dụng.

Ví dụ module auto-configuration dùng một SDK tùy chọn để compile:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    compileOnly 'com.acme:acme-core:1.0.0'
    testImplementation 'com.acme:acme-core:1.0.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Trong starter lõi:

```groovy
dependencies {
    implementation project(':acme-core')
    implementation project(':acme-spring-boot-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Trong starter web:

```groovy
dependencies {
    implementation project(':acme-spring-boot-starter')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Consumer chọn web starter thì dependency web được đưa vào runtime graph. Consumer chỉ chọn starter lõi thì không nhận dependency web.

`compileOnly` không phải bản sao hoàn toàn của Maven `optional=true`. `compileOnly` cũng không đưa dependency vào runtime classpath của chính module. Nếu code auto-configuration cần SDK lúc runtime, starter tính năng phải khai báo SDK bằng dependency runtime phù hợp. Dùng `testImplementation` để test module có thể chạy test với SDK.

## 5. Condition bảo vệ auto-configuration khi dependency là tùy chọn

Giới hạn dependency graph là lớp bảo vệ đầu tiên. Nếu một thư viện vẫn có thể vắng mặt trong một cách đóng gói khác, auto-configuration cần kiểm tra classpath trước khi sử dụng type của thư viện.

### 5.1. Dùng `@ConditionalOnClass`

Ví dụ cấu hình có một integration tùy chọn:

```java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.mail.MailClient")
    static class MailConfiguration {

        @Bean
        @ConditionalOnMissingBean
        MailNotificationSender mailNotificationSender(
                MailClient mailClient) {
            return new MailNotificationSender(mailClient);
        }
    }
}
```

Đây là mẫu cấu trúc; các kiểu `MailClient` và `MailNotificationSender` thuộc integration module. Nested configuration cô lập các chữ ký method tham chiếu tới class tùy chọn. Khi `MailClient` không có trên classpath, Spring không áp dụng nested configuration.

Không đặt method có return type hoặc tham số là class tùy chọn trực tiếp trong outer configuration rồi cho rằng condition trên chính `@Bean` method luôn ngăn JVM tải type đó. Spring Boot lưu ý rằng điều kiện trên method không bảo vệ cùng cách như condition ở cấp configuration class, vì JVM có thể phải tải kiểu của method trước khi xử lý condition. Hãy tách nested configuration hoặc module auto-configuration riêng.

### 5.2. Kết hợp property khi cần người dùng chủ động bật tính năng

`@ConditionalOnClass` trả lời “thư viện có mặt không?”. Nếu dependency có mặt nhưng feature vẫn cần được bật có chủ ý, kết hợp property:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.acme.mail.MailClient")
@ConditionalOnProperty(
        prefix = "acme.mail",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
static class MailConfiguration {
    // Các @Bean chỉ dành cho mail integration.
}
```

Với `matchIfMissing=false`, thiếu property đồng nghĩa feature không bật. Nếu người dùng thêm starter mail riêng và muốn dependency đó tự thể hiện ý định opt-in, có thể chọn `matchIfMissing=true`. Quy tắc mặc định phải được ghi rõ trong tài liệu starter.

### 5.3. Những điều condition không làm

| Cơ chế | Làm được | Không làm được |
| --- | --- | --- |
| `@ConditionalOnClass` | Bỏ qua cấu hình khi class không có | Xóa JAR khỏi dependency graph |
| `@ConditionalOnProperty` | Bật/tắt cấu hình theo property | Ngăn dependency được tải |
| `@ConditionalOnMissingBean` | Cho default nhường chỗ khi đã có bean | Loại dependency hoặc tắt auto-config của thư viện khác |
| Maven `optional=true` | Không tự truyền dependency tới consumer | Tự bật lại dependency khi consumer cần feature |
| Maven `exclusions` | Loại dependency qua một đường truyền cụ thể | Loại mọi đường khác cũng đưa artifact vào graph |
| Tách starter | Cho consumer chọn dependency theo feature | Tự bảo đảm code feature không có lỗi khi dependency hiện diện |

Một property của Acme không thể vô hiệu hóa `WebMvcAutoConfiguration` của Spring Boot nếu `spring-boot-starter-web` vẫn có trong runtime classpath. Muốn tránh kích hoạt web stack ngoài ý muốn, phải sửa dependency graph.

## 6. Ví dụ chạy được: starter lõi không kéo Spring MVC, web starter mới bật web stack

Ví dụ dùng Spring Boot 3.3.5 và Java 17+. Ta xây multi-module Maven project theo POM ở mục 3.3. Ứng dụng demo chỉ cần Acme core starter; có thể thêm web starter để kiểm tra tác động.

### 6.1. Core API: `acme-core/src/main/java/com/acme/core/AcmeClient.java`

```java
package com.acme.core;

public record AcmeClient(String mode) {
}
```

### 6.2. Auto-configuration lõi: `acme-spring-boot-autoconfigure/src/main/java/com/acme/autoconfigure/AcmeAutoConfiguration.java`

```java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.core.AcmeClient")
    static class CoreConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeClient acmeClient() {
            return new AcmeClient("default");
        }
    }
}
```

Nested configuration chỉ được áp dụng khi Acme core API có trên classpath. Dependency `acme-core` được đánh dấu optional trong module auto-configuration, còn starter lõi khai báo nó là dependency bắt buộc để bean mặc định được tạo.

### 6.3. Đăng ký auto-configuration

Tạo file:

```text
acme-spring-boot-autoconfigure/
└── src/main/resources/
    └── META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.autoconfigure.AcmeAutoConfiguration
```

Spring Boot 3.x đọc file `AutoConfiguration.imports` để tìm auto-configuration từ JAR bên ngoài. Không đặt lớp auto-configuration vào package được component scan của ứng dụng dò tìm; hãy đăng ký qua imports.

### 6.4. Ứng dụng consumer: `demo-app/src/main/java/demo/DemoApplication.java`

```java
package demo;

import com.acme.core.AcmeClient;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner reportDependencies(ApplicationContext context) {
        return args -> {
            boolean mvcPresent = ClassUtils.isPresent(
                    "org.springframework.web.servlet.DispatcherServlet",
                    context.getClassLoader());

            int servletFactoryCount =
                    context.getBeanNamesForType(
                            ServletWebServerFactory.class).length;

            System.out.println("acmeClient=" +
                    context.containsBean("acmeClient"));
            System.out.println("springMvcOnClasspath=" + mvcPresent);
            System.out.println("servletFactoryCount=" + servletFactoryCount);

            AcmeClient client = context.getBean(AcmeClient.class);
            System.out.println("clientMode=" + client.mode());
        };
    }
}
```

Ứng dụng không tạo controller hoặc API nghiệp vụ. Nó chỉ in một bean core và hai dấu hiệu web stack: class Spring MVC có trên classpath hay không, và số `ServletWebServerFactory` trong context.

`ServletWebServerFactory` thuộc Spring Boot API nên demo app có thể compile khi chỉ dùng starter lõi. Class `DispatcherServlet` được kiểm tra bằng tên chuỗi để không buộc demo app phải compile trực tiếp với Spring MVC.

### 6.5. `demo-app/pom.xml`: chỉ dùng starter lõi

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>demo-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>1.0.0-SNAPSHOT</version>
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

Build từ thư mục gốc:

```bash
mvn -q -pl demo-app -am package
```

Chạy:

```bash
java -jar demo-app/target/demo-app-1.0.0-SNAPSHOT.jar
```

Output kỳ vọng:

```text
acmeClient=true
springMvcOnClasspath=false
servletFactoryCount=0
clientMode=default
```

Ứng dụng vẫn có bean Acme core nhưng không có Spring MVC và không tạo embedded Servlet server. Starter lõi không vô tình kéo web stack vào runtime classpath.

### 6.6. Chọn thêm web starter

Nếu ứng dụng thực sự là web application, thêm dependency này vào `demo-app/pom.xml`:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-spring-boot-starter-web</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

Build và chạy lại cùng lệnh. Output kỳ vọng:

```text
acmeClient=true
springMvcOnClasspath=true
servletFactoryCount=1
clientMode=default
```

Lần này `spring-boot-starter-web` được thêm qua web starter. Spring MVC có mặt trên runtime classpath, Spring Boot chọn Servlet web mode và tạo embedded server factory. Process web sẽ tiếp tục chạy để phục vụ ứng dụng; dừng bằng Ctrl+C khi thử local.

Đây là thay đổi có chủ đích: chỉ một dependency feature được thêm, các thành phần web tương ứng mới xuất hiện. Không cần thêm controller giả để chứng minh web stack đã được kích hoạt.

## 7. Kiểm tra dependency graph thay vì đoán từ POM trực tiếp

### 7.1. Maven `dependency:tree`

Để tìm đường truyền Spring Web/Tomcat:

```bash
mvn -pl demo-app -am dependency:tree
mvn -pl demo-app -am dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web,org.springframework:spring-webmvc,org.apache.tomcat.embed:tomcat-embed-core
```

Khi demo chỉ dùng starter lõi, lệnh lọc không nên tìm thấy `spring-boot-starter-web`, `spring-webmvc` hoặc `tomcat-embed-core` qua đồ thị dependency của demo.

Sau khi thêm web starter, lệnh lọc sẽ chỉ ra đường truyền tương tự:

```text
demo-app
\- acme-spring-boot-starter-web
   \- spring-boot-starter-web
      +- spring-boot-starter-tomcat
      |  \- tomcat-embed-core
      \- spring-webmvc
```

Đây là hình dạng rút gọn; cây thực tế có thêm starter và thư viện liên quan, phụ thuộc version và dependency mediation.

### 7.2. Tìm dependency đến từ đâu

Khi một dependency xuất hiện ngoài dự kiến:

1. Chạy `mvn dependency:tree` ở đúng module consumer.
2. Tìm artifact đáng ngờ, ví dụ `spring-boot-starter-web` hoặc `spring-webmvc`.
3. Lần ngược các node cha để tìm dependency trực tiếp đầu tiên kéo nó vào.
4. Kiểm tra dependency đó có thật sự cần tính năng web không.
5. Sửa starter/module sở hữu dependency hoặc dùng exclusion trên đúng cạnh nếu không thể sửa upstream.
6. Chạy lại dependency tree và test runtime.

Không chỉ tìm artifact theo tên trong POM của ứng dụng. Dependency có thể đến từ SDK, starter khác hoặc module nội bộ ở nhiều cấp trung gian.

### 7.3. Gradle dependency report

Với Gradle:

```bash
./gradlew :demo-app:dependencies --configuration runtimeClasspath
./gradlew :demo-app:dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
```

`dependencies` cho thấy toàn bộ runtime graph; `dependencyInsight` chỉ ra vì sao dependency được chọn và đường nào đưa nó vào. Với bài toán kích hoạt auto-configuration, `runtimeClasspath` thường quan trọng hơn compile classpath.

## 8. Exclusions: chặn một dependency trên một đường truyền cụ thể

Nếu không kiểm soát được POM của thư viện bên thứ ba và nó kéo theo dependency không cần thiết, Maven cho phép exclusion:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>vendor-client</artifactId>
    <version>2.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion được khai báo trên **một dependency edge**. Nếu dependency khác cũng kéo `spring-boot-starter-web` vào, artifact vẫn có thể còn trong graph.

Trước khi exclude, phải kiểm tra thư viện vendor có dùng class từ dependency bị loại hay không. Nếu vendor-client thực sự cần Spring MVC để chạy, exclusion có thể gây `NoClassDefFoundError` hoặc lỗi tạo bean lúc startup.

Không dùng wildcard để xóa hàng loạt dependency nền, không exclude logging/JSON/validation chỉ vì muốn giảm số JAR mà chưa kiểm tra contract runtime.

Ưu tiên xử lý:

1. Tách feature thành starter riêng ở thư viện do mình sở hữu.
2. Đánh dấu dependency tùy chọn trong module auto-configuration khi đúng hợp đồng.
3. Dùng exclusion có mục tiêu nếu dependency không mong muốn đến từ upstream không thể sửa.
4. Xác minh runtime graph và chạy test sau khi loại dependency.

## 9. Kết hợp dependency graph với condition và property

Một starter tốt thường cần nhiều lớp bảo vệ:

| Lớp | Công cụ | Mục tiêu |
| --- | --- | --- |
| Artifact/module | Starter lõi và starter feature riêng | Consumer chỉ nhận dependency họ chọn |
| Dependency declaration | Maven optional / Gradle configuration phù hợp | Không truyền dependency tùy chọn ngoài ý muốn |
| Classpath | `@ConditionalOnClass` | Không nạp cấu hình khi thư viện không có |
| Property | `@ConditionalOnProperty` | Cho phép bật/tắt feature có chủ đích |
| Bean | `@ConditionalOnMissingBean` | Cho phép người dùng thay default bean |

Ví dụ một mail integration chỉ nên hoạt động khi mail SDK có mặt và property được bật:

```java
@AutoConfiguration
public class AcmeMailAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.mail.MailClient")
    @ConditionalOnProperty(
            prefix = "acme.mail",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    static class MailConfiguration {

        @Bean
        @ConditionalOnMissingBean
        MailNotificationSender mailNotificationSender(
                MailClient mailClient) {
            return new MailNotificationSender(mailClient);
        }
    }
}
```

Đây là pattern minh họa; các type mail thuộc integration riêng. Dependency mail nên được đưa vào `acme-spring-boot-starter-mail`, không đưa vào starter lõi. Property bảo vệ bean do Acme cung cấp; việc tách starter mới ngăn dependency mail đi vào app không dùng mail.

## 10. Kiểm thử dependency và auto-configuration

### 10.1. Test default core bean

Trong module auto-configuration, dùng `ApplicationContextRunner`:

```java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AcmeAutoConfiguration.class));

    @Test
    void createsCoreClientWhenCoreLibraryIsPresent() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context.getBean(AcmeClient.class).mode())
                    .isEqualTo("default");
        });
    }

    @Test
    void userClientReplacesDefault() {
        this.runner
                .withBean(AcmeClient.class, () -> new AcmeClient("custom"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).mode())
                            .isEqualTo("custom");
                });
    }
}
```

Test này xác nhận back-off của bean lõi. Nó không thay thế việc kiểm tra dependency graph của consumer.

### 10.2. Test classpath condition

Có thể thêm test ẩn core class bằng `FilteredClassLoader`:

```java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void skipsCoreConfigurationWhenCoreClassIsAbsent() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    AcmeAutoConfiguration.class))
            .withClassLoader(new FilteredClassLoader(AcmeClient.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(AcmeClient.class);
            });
}
```

Test này chứng minh condition classpath bảo vệ auto-configuration khi optional library không có. Nó không chứng minh thư viện đã bị loại khỏi dependency tree; đó là hai loại kiểm tra riêng.

### 10.3. Test dependency graph trong CI

Có thể đặt bước build để kiểm tra runtime dependency graph:

- Maven: lưu output `mvn -pl demo-app -am dependency:tree` hoặc lọc artifact không mong muốn bằng `-Dincludes`.
- Gradle: dùng `dependencies --configuration runtimeClasspath` và `dependencyInsight`.
- Integration test: khởi động consumer lõi và xác nhận `WebApplicationType.NONE` hoặc không có `ServletWebServerFactory`; consumer web xác nhận Servlet infrastructure có mặt.

Đừng chỉ test rằng ứng dụng khởi động thành công. Một ứng dụng CLI vẫn có thể khởi động được dù starter vô tình kéo Tomcat vào; bean inventory và dependency tree mới phát hiện web stack dư thừa.

## 11. Những lỗi thiết kế thường gặp

1. **Starter lõi phụ thuộc mọi starter Spring Boot.** Mỗi consumer nhận runtime graph lớn và có thể kích hoạt auto-configuration không cần thiết. Chỉ thêm dependency chung thực sự cần.
2. **Nghĩ `implementation` trong Gradle không truyền sang runtime consumer.** Sai: implementation không xuất compile API, nhưng dependency vẫn có thể xuất trong runtimeElements.
3. **Nghĩ `@ConditionalOnClass` xóa dependency.** Sai: condition chỉ bỏ qua cấu hình; JAR vẫn ở classpath.
4. **Dùng property để chữa dependency graph quá rộng.** Property chỉ điều khiển cấu hình của bạn hoặc cấu hình nào đọc property đó; nó không tự vô hiệu hóa auto-configuration của thư viện khác.
5. **Đặt class tùy chọn trong chữ ký `@Bean` của outer configuration.** Có thể gặp lỗi tải class trước khi method condition được xét. Cô lập trong nested configuration có `@ConditionalOnClass` hoặc module riêng.
6. **Đánh dấu optional mọi dependency.** Dependency core thực sự cần phải là required trong starter lõi; nếu đánh dấu optional sai, consumer có thể thiếu class lúc runtime.
7. **Dùng `provided` thay cho `optional`.** Hai scope có ý nghĩa khác nhau; provided giả định runtime environment cung cấp dependency.
8. **Exclude artifact mà không kiểm tra đường truyền khác.** Exclusion chỉ áp dụng cho edge khai báo; artifact có thể còn qua dependency khác.
9. **Exclude thư viện mà vendor thực sự cần.** Có thể build được nhưng runtime fail vì thiếu class hoặc auto-configuration phụ thuộc.
10. **Dùng `@ConditionalOnMissingBean` làm cổng classpath.** Bean condition không thay thế class condition; thiếu bean và thiếu thư viện là hai trạng thái khác nhau.
11. **Không test ứng dụng lõi và ứng dụng feature riêng.** Starter cần ma trận consumer để bảo đảm core không kéo feature ngoài ý muốn và feature starter cung cấp dependency cần thiết.
12. **Chỉ xem compile classpath.** Auto-configuration chạy khi ứng dụng khởi động, nên runtime classpath là nơi cần kiểm tra.

## 12. Checklist trước khi phát hành custom starter

- [ ] Starter lõi chỉ chứa dependency bắt buộc cho mọi consumer.
- [ ] Web, mail, database, messaging và integration tùy chọn có starter/module riêng khi cần.
- [ ] Dependency thư viện tùy chọn trong auto-configuration được khai báo đúng optional semantics.
- [ ] Starter feature khai báo lại dependency runtime cần thiết tường minh.
- [ ] Không dùng Gradle `implementation` với suy nghĩ dependency sẽ biến mất khỏi runtime consumer.
- [ ] Optional class được bảo vệ bằng `@ConditionalOnClass` ở configuration phù hợp.
- [ ] Feature cần opt-in có property namespace riêng của thư viện.
- [ ] Default bean có `@ConditionalOnMissingBean` khi người dùng cần thay thế.
- [ ] `AutoConfiguration.imports` chỉ đăng ký auto-configuration cần thiết.
- [ ] Đã xem dependency tree/runtimeClasspath của từng starter.
- [ ] Đã kiểm tra app chỉ dùng starter lõi không có web/database/mail stack ngoài ý muốn.
- [ ] Đã kiểm tra app thêm feature starter nhận đúng dependency và bean hạ tầng.
- [ ] Đã chạy test auto-configuration với dependency có/không có, property bật/tắt và bean custom.
- [ ] Đã xác minh dependency exclusion không làm hỏng runtime contract.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): cách tách auto-configuration/starter, optional dependencies, `@ConditionalOnClass`, `AutoConfiguration.imports` và test.
- [Maven — Optional and Excluded Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies): semantics của `optional` và exclusion theo dependency edge.
- [Maven POM Reference — Dependency Scopes](https://maven.apache.org/pom.html#dependency-scopes): khác biệt compile, runtime, provided và test.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`, `implementation`, `compileOnly` và `runtimeOnly`.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): cách các configuration tạo compile/runtime classpath và truyền dependency cho consumer.
