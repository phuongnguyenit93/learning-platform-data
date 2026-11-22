# Chọn dependency cần thiết cho trải nghiệm sử dụng mặc định

## 1. Starter tốt bắt đầu từ trải nghiệm người dùng

Một custom Spring Boot starter là lời hứa về trải nghiệm khi ứng dụng thêm **một dependency**. Người dùng mong muốn tính năng được cấu hình hợp lý, các thư viện cần thiết có mặt, auto-configuration hoạt động khi phù hợp và không phải tự tìm từng JAR để ghép lại.

Vì vậy, khi thiết kế starter, câu hỏi quan trọng không chỉ là “module này cần thư viện nào để biên dịch?” mà còn là:

- Người dùng thêm starter thì **tính năng mặc định nào** phải hoạt động?
- Những thư viện nào là nền tảng bắt buộc của trải nghiệm đó?
- Tích hợp nào chỉ là tùy chọn, chỉ một nhóm người dùng cần?
- Starter có đang vô tình chọn server, database driver, logging implementation hoặc client SDK thay cho ứng dụng không?
- Khi ứng dụng đã có bean riêng, auto-configuration có nhường chỗ đúng cách không?
- Dependency graph có nhất quán với phiên bản Spring Boot và Java mà thư viện hỗ trợ không?

Starter tốt cung cấp đủ dependency để đường đi phổ biến hoạt động ngay, nhưng giữ các quyết định riêng của ứng dụng ở phía người dùng. Chẳng hạn, starter JDBC có thể cung cấp pool và Spring JDBC, nhưng không nên tự chọn PostgreSQL hay MySQL driver nếu thư viện không bị ràng buộc vào một vendor cụ thể.

Bài này thiết kế custom starter theo Spring Boot 3.3.x và Java 17+, phân chia module, lựa chọn dependency/scope, dùng BOM, tổ chức các starter biến thể, kiểm tra dependency tree và xác nhận trải nghiệm trong một ứng dụng consumer.

## 2. Phân chia hai module: autoconfigure và starter

Một cấu trúc phổ biến gồm hai artifact:

```text
acme-notify/
├── acme-notify-spring-boot-autoconfigure/
│   ├── src/main/java/...
│   └── src/main/resources/
│       └── META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-notify-spring-boot-starter/
    └── pom.xml
```

**Module `autoconfigure`** chứa mã Java:

- `@AutoConfiguration` và các condition.
- `@ConfigurationProperties` và metadata cấu hình.
- Bean mặc định, customizer, health indicator hoặc integration adapter.
- Resource `AutoConfiguration.imports` để Spring Boot phát hiện auto-configuration.
- Tests kiểm tra điều kiện, bean back-off và behavior.

**Module `starter`** chủ yếu là dependency aggregator:

- Phụ thuộc vào module autoconfigure.
- Kéo vào các thư viện nền tảng mà trải nghiệm mặc định thực sự cần.
- Kéo vào SDK/implementation mặc định đã được lựa chọn có chủ đích.
- Thường không chứa Java source, không đăng ký một auto-configuration thứ hai và không tự triển khai logic nghiệp vụ.

Cách tách này có lợi ở hai phía:

1. Ứng dụng chỉ cần auto-configuration hoặc muốn tự quản lý dependency có thể phụ thuộc trực tiếp vào artifact autoconfigure.
2. Người dùng thông thường chỉ cần thêm starter và nhận được bộ dependency đã được kiểm thử cùng nhau.

Tên artifact cho một starter bên thứ ba thường có dạng `acme-notify-spring-boot-starter`; module mã cấu hình có thể là `acme-notify-spring-boot-autoconfigure`. Tên bắt đầu bằng `spring-boot-starter-` được dành cho các starter chính thức của Spring Boot; bên thứ ba nên đặt tên tổ chức/sản phẩm ở đầu.

### 2.1. Vì sao không gộp mọi thứ vào một JAR?

Một JAR duy nhất vẫn có thể hoạt động với thư viện nhỏ. Tuy nhiên, khi tích hợp nhiều SDK hoặc nhiều loại web/database stack, nó dễ trở thành một dependency lớn mà mọi người dùng đều phải kéo theo.

Ví dụ, một thư viện notification có thể hỗ trợ:

- HTTP client mặc định.
- Kafka publisher.
- AWS SQS.
- Email qua SMTP.
- WebFlux adapter.

Nếu gộp tất cả SDK vào một starter, ứng dụng chỉ muốn HTTP vẫn phải kéo Kafka, AWS, mail và reactive server. Dependency graph trở nên khó hiểu, classpath lớn hơn và có nhiều nguy cơ xung đột version.

Tách autoconfigure với starter chính, sau đó tách integration starter khi có nhu cầu thực, giúp mỗi artifact thể hiện rõ một hợp đồng sử dụng.

## 3. Phân loại dependency trước khi thêm vào POM

Trước khi thêm dependency, hãy phân loại theo vai trò thay vì dựa vào việc một class import xuất hiện trong source.

| Nhóm | Ví dụ | Có nên nằm trong starter mặc định? |
| --- | --- | --- |
| Spring Boot baseline | `spring-boot-starter`, `spring-boot-autoconfigure` | Có nếu trải nghiệm mặc định dựa vào nền tảng này |
| Core library bắt buộc | SDK HTTP cốt lõi của thư viện | Có nếu tính năng mặc định không thể chạy thiếu nó |
| Optional integration | Kafka, AWS SQS, Redis, SMTP SDK | Chỉ khi đó là phần mặc định hoặc tách thành starter riêng |
| Web runtime | Servlet/Tomcat hoặc reactive/Reactor Netty | Chỉ chọn nếu tính năng thật sự cần server runtime đó |
| Database pool/JDBC | HikariCP, Spring JDBC | Có khi starter mặc định cung cấp JDBC access |
| Database vendor driver | PostgreSQL, MySQL, Oracle | Thường để ứng dụng chọn |
| Validation | Jakarta Validation provider | Có nếu contract mặc định yêu cầu validation và code thực sự dùng nó |
| Metrics/Actuator | Spring Boot Actuator | Optional hoặc starter metrics riêng nếu không phải yêu cầu cốt lõi |
| Configuration processor | `spring-boot-configuration-processor` | Chỉ ở compile/annotation-processing, không phải runtime feature |
| Test libraries | `spring-boot-starter-test`, Testcontainers | Chỉ ở test scope |
| Logging implementation | Logback hoặc Log4j implementation | Không tự thay logging stack của ứng dụng nếu không có lý do rõ |

Một dependency chỉ nên là **bắt buộc** khi thiếu nó làm trải nghiệm mà starter quảng bá không thể hoạt động. “Có thể tích hợp” không đủ để biến nó thành dependency mặc định.

### 3.1. Bài kiểm tra quyết định dependency

Với mỗi dependency, hãy trả lời:

1. Nếu bỏ dependency này, người dùng thêm starter có còn chạy được use case mặc định không?
2. Dependency có được tham chiếu trong chữ ký public API, bean method hoặc class được load ngay khi startup không?
3. Nó là runtime implementation, API compile-time hay chỉ phục vụ annotation processing/test?
4. Ứng dụng consumer có nên được quyền chọn implementation khác không?
5. Dependency có kéo theo server, driver, native library hoặc transitive dependency lớn không?
6. Phiên bản của nó có được Boot BOM quản lý hay cần một version policy riêng?
7. Có thể tách nó thành một integration starter để tránh kéo theo ở mọi ứng dụng không?

Nếu câu trả lời cho câu 1 là “không”, dependency thường không nên nằm trong starter mặc định. Nếu câu 4 là “có”, hãy cân nhắc cung cấp một mặc định có thể thay thế thay vì ép implementation.

## 4. Maven dependency semantics: compile, runtime, optional và test

Maven scope ảnh hưởng đến classpath của module hiện tại và cách dependency truyền sang consumer.

| Scope / thuộc tính | Có ở compile classpath của module? | Có ở runtime của module? | Truyền sang consumer? |
| --- | :---: | :---: | --- |
| `compile` (mặc định) | Có | Có | Có, transitively |
| `runtime` | Không | Có | Có ở runtime của consumer |
| `provided` | Có | Có trong test/runtime Maven theo semantics scope | Không như compile dependency thông thường |
| `test` | Có trong test | Có trong test | Không |
| `<optional>true</optional>` trên dependency | Theo scope gốc | Theo scope gốc | Không tự truyền dependency đó như một dependency bắt buộc cho consumer |

Đối với autoconfigure module, dependency có thể cần để biên dịch nhưng **không nên tự động kéo vào mọi consumer**. Khi đó Maven `optional` rất hữu ích: module autoconfigure khai báo dependency SDK là optional; starter chính thức của thư viện thêm SDK đó như dependency thường.

### 4.1. Ví dụ autoconfigure POM

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-notify-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-notify-client</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
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

Đây là POM minh họa; phiên bản được quản lý bởi parent hoặc dependency management của project. SDK notification là optional để một consumer chỉ phụ thuộc autoconfigure có thể không kéo SDK vào. Configuration processor chỉ hỗ trợ sinh metadata cho IDE/build; nó không cần có mặt trong runtime ứng dụng.

Nếu autoconfigure có class trực tiếp tham chiếu SDK tùy chọn, hãy đặt phần đó trong nested configuration có condition cấp class. Không giả định dependency optional sẽ tự bảo vệ việc JVM load mọi method signature. Ví dụ:

```java
@AutoConfiguration
public class NotifyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.notify.NotifyClient")
    static class NotifyClientConfiguration {
        // Bean method có thể tham chiếu NotifyClient ở đây.
    }
}
```

Đây là mảnh cấu trúc minh họa. Việc cô lập class tùy chọn trong nested configuration giúp condition được đánh giá trước khi phần cấu hình phụ thuộc class đó được xử lý.

### 4.2. Ví dụ starter POM

Starter thêm lại các dependency mà người dùng mặc định cần:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-notify-spring-boot-starter</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-notify-spring-boot-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-notify-client</artifactId>
        </dependency>
    </dependencies>
</project>
```

Starter này có ba phần: Boot baseline, autoconfigure code và SDK mặc định. Dependency SDK được thêm **không optional** trong starter, nên ứng dụng dùng starter nhận nó ở runtime.

Không đưa `spring-boot-starter-test` vào starter POM ở scope mặc định. Không đưa database driver hoặc server không liên quan chỉ vì chúng có thể hữu ích trong một số dự án.

### 4.3. Khi nào dùng runtime thay vì compile?

Nếu một implementation chỉ cần khi ứng dụng chạy và không xuất hiện trong public API, `runtime` có thể phù hợp. Ví dụ, một plugin implementation được nạp bằng SPI/reflection và không cần consumer biên dịch trực tiếp với class của nó.

Nếu người dùng cần khai báo bean, gọi API hoặc cấu hình class đó trong source code, dependency thường cần compile visibility. Hãy xem xét cả chữ ký của các bean mà autoconfigure công bố, không chỉ các import nội bộ.

`provided` không phải cách tổng quát để đánh dấu “optional”; nó mô tả dependency được môi trường triển khai cung cấp. Với starter chạy trong ứng dụng Boot thông thường, không dùng `provided` chỉ để tránh truyền dependency nếu consumer thực sự cần thư viện đó.

## 5. Gradle: api, implementation, compileOnly và runtimeOnly

Với Gradle, phân biệt API công khai với implementation nội bộ:

- `api`: dependency xuất hiện trên compile classpath của consumer, phù hợp khi public API của module phơi bày kiểu của dependency.
- `implementation`: dependency cần cho module nhưng không được đưa vào compile classpath consumer; vẫn có mặt ở runtime theo dependency graph.
- `compileOnly`: cần để biên dịch module nhưng không được thêm vào runtime classpath của consumer.
- `runtimeOnly`: chỉ cần lúc chạy, không cần compile.
- `testImplementation`/`testRuntimeOnly`: chỉ dành cho test.

Ví dụ với plugin `java-library`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly 'com.acme:acme-notify-client'

    annotationProcessor \
        'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation \
        'org.springframework.boot:spring-boot-starter-test'
}
```

Ví dụ này minh họa cách giữ SDK không truyền sang consumer từ module autoconfigure; starter sẽ thêm SDK như dependency của chính nó. Nếu SDK xuất hiện trong public API của autoconfigure và consumer phải biên dịch với type đó, xem xét `compileOnlyApi` hoặc thiết kế lại API để không buộc consumer biết SDK. Dù chọn cách nào, starter vẫn phải cung cấp SDK runtime.

Starter Gradle có thể là:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':acme-notify-spring-boot-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.acme:acme-notify-client'
}
```

Trong một project đa module, `project(...)` là dependency tới module autoconfigure. Với artifact đã publish, thay bằng tọa độ Maven tương ứng.

**Lưu ý:** Gradle configuration model và Maven optional không hoàn toàn tương đương. Đừng dịch từng scope Maven thành một tên Gradle theo máy móc; hãy kiểm tra compile/runtime graph của consumer sau khi publish hoặc resolve project.

## 6. Dùng BOM để giữ phiên bản nhất quán

Một starter thường phụ thuộc vào nhiều thư viện Spring Boot và Spring Framework. Nếu mỗi dependency tự khai báo version riêng, rất dễ tạo ra tổ hợp không được Boot kiểm thử.

Spring Boot BOM quản lý tập phiên bản tương thích. Với Maven, có thể dùng `spring-boot-starter-parent` hoặc import `spring-boot-dependencies` trong `dependencyManagement`.

Ví dụ import BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó dependency Boot-managed không cần ghi version:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-autoconfigure</artifactId>
</dependency>
```

Với Gradle, có thể dùng plugin quản lý dependency hoặc import platform BOM:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
}
```

Không tự ghim một phiên bản Spring Framework khác với phiên bản do Boot BOM quản lý trừ khi có lý do tương thích đã kiểm thử. Nếu custom starter phát hành nhiều module, giữ version nội bộ đồng bộ; một BOM riêng của tổ chức có thể quản lý các artifact `com.acme` nếu hệ sinh thái lớn.

### 6.1. Version policy cho thư viện bên ngoài

Không phải mọi dependency đều do Boot BOM quản lý. Với SDK vendor:

- Chọn phiên bản đã kiểm thử với Java và Spring Boot mục tiêu.
- Quản lý tập trung bằng property hoặc BOM riêng.
- Tránh khai báo cùng một dependency với nhiều version trong các module.
- Theo dõi CVE và cập nhật định kỳ.
- Kiểm tra dependency convergence và version conflict trong consumer.

Không dùng version mới nhất một cách tự động nếu chưa xác minh compatibility; một SDK có thể đổi baseline Java, HTTP stack hoặc logging API.

## 7. Chọn đúng default runtime: MVC, WebFlux hay không có web server?

Một trong những quyết định dependency có ảnh hưởng lớn nhất là có kéo theo web starter hay không.

| Dependency | Trải nghiệm mặc định | Khi nên chọn |
| --- | --- | --- |
| `spring-boot-starter` | Nền tảng Boot, không tự chọn MVC/reactive server | Thư viện core, batch/CLI, integration không cần HTTP server |
| `spring-boot-starter-web` | Spring MVC + Servlet stack; mặc định thường có embedded Tomcat | Thư viện cung cấp REST MVC endpoint hoặc Servlet integration |
| `spring-boot-starter-webflux` | Spring WebFlux + reactive stack; thường có Reactor Netty server | Thư viện cần reactive server và non-blocking HTTP handling |
| `spring-boot-starter-web` + `spring-boot-starter-webflux` | Boot ưu tiên MVC khi cả hai có mặt | Chỉ khi ứng dụng thực sự cần cả hai nhóm API; thường WebFlux được thêm để dùng WebClient |
| Không thêm web starter | Không ép loại web application | Library chỉ cần HTTP client, domain service hoặc auto-configuration nền |

Không thêm cả MVC lẫn WebFlux chỉ để có `WebClient`. WebClient có thể được dùng với dependency WebFlux phù hợp trong một ứng dụng Servlet; tuy nhiên hãy chọn starter và dependency closure theo trải nghiệm thực sự muốn hỗ trợ. Nếu starter hứa tạo một reactive server, phải kéo server runtime cần thiết. Nếu nó chỉ cung cấp client, đừng vô tình biến ứng dụng thành web server.

### 7.1. Không chọn database vendor thay người dùng

Một starter cung cấp JDBC access có thể cần:

- `spring-boot-starter-jdbc` cho Spring JDBC và connection pool mặc định.
- Một abstraction hoặc driver-independent API trong thư viện.
- Auto-configuration cho `DataSource`/template nếu đó là phần sản phẩm chịu trách nhiệm.

Nó thường **không nên** kéo PostgreSQL hoặc MySQL driver mặc định. Ứng dụng chọn driver dựa trên database thực tế. Nếu sản phẩm tích hợp cố định với một dịch vụ có driver riêng, hãy giải thích quyết định đó và có thể cung cấp integration starter riêng.

Tương tự, không thêm `spring-boot-starter-data-jpa` nếu tính năng chỉ cần JDBC; JPA kéo theo ORM và nhiều lựa chọn runtime khác. Chọn dependency nhỏ nhất đủ đáp ứng contract.

### 7.2. Logging, metrics và security

- Dùng abstraction logging của Spring/JCL hoặc SLF4J; tránh tự ép một logging backend nếu không cần.
- Nếu Actuator integration là optional, đặt health indicator trong nested configuration có `@ConditionalOnClass(HealthContributor.class)` và tách dependency Actuator khỏi starter core.
- Nếu security là một tính năng cốt lõi, khai báo rõ dependency và default security policy. Nếu chỉ cung cấp adapter tích hợp Spring Security, tách thành module/starter riêng.
- Không tự bật endpoint quản trị hoặc expose sensitive information chỉ vì starter kéo Actuator.

## 8. Thiết kế một họ starter thay vì một starter khổng lồ

Nếu thư viện có nhiều integration độc lập, tổ chức theo capability:

```text
acme-notify-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── acme-notify-client

acme-notify-kafka-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── kafka integration SDK

acme-notify-sqs-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── AWS SQS integration SDK

acme-notify-webflux-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── WebFlux-specific adapter dependencies
```

Tên và module thực tế tùy sản phẩm. Điều quan trọng là người dùng chỉ kéo integration họ cần.

### 8.1. Không trộn server variants trong starter core

Nếu thư viện hỗ trợ cả Servlet và Reactive:

- Starter core chỉ chứa dependency chung và autoconfigure chung.
- Starter MVC thêm adapter/Servlet dependencies.
- Starter WebFlux thêm adapter/Reactive dependencies.
- Mỗi adapter có condition `@ConditionalOnWebApplication(type = ...)`.
- Không để hai starter vô tình đăng ký cùng bean name/type mà không có back-off.

Một ứng dụng có cả hai starter vẫn phải có hành vi được tài liệu hóa. Nếu cả hai runtime cùng có trên classpath, Spring Boot có quy tắc chọn web application type; việc có classpath WebFlux không tự chuyển ứng dụng MVC thành Reactive.

### 8.2. Đừng thêm mọi integration vào starter core rồi trông cậy condition

Condition có thể ngăn bean được đăng ký, nhưng nó không làm dependency biến mất khỏi dependency graph. Nếu starter kéo cả Kafka, AWS SDK, Redis, mail và WebFlux, người dùng vẫn tải tất cả JAR dù các auto-configuration không match.

Vì vậy, dùng `@ConditionalOnClass` là cần thiết cho auto-configuration tùy chọn, nhưng **không thay thế việc thiết kế dependency graph gọn**. Tách starter theo capability giảm download, classpath conflicts, attack surface và thời gian khởi động.

## 9. Auto-configuration phải phù hợp với dependency contract

Dependency graph và condition cần khớp nhau.

Ví dụ một custom starter cung cấp client notification:

```java
@AutoConfiguration
public class NotifyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.notify.NotifyClient")
    @ConditionalOnProperty(
            prefix = "acme.notify",
            name = "enabled",
            havingValue = "true")
    @EnableConfigurationProperties(NotifyProperties.class)
    static class NotifyClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        NotifyClient notifyClient(NotifyProperties properties) {
            return new NotifyClient(
                    properties.endpoint(),
                    properties.apiKey());
        }
    }
}
```

Đây là cấu trúc minh họa; `NotifyClient` là kiểu từ SDK và `NotifyProperties` là lớp cấu hình của thư viện. Các import và constructor phụ thuộc SDK thật cần được thay theo API vendor.

Ý nghĩa:

- Nếu SDK không có trên classpath, nested config không tham gia.
- Nếu tính năng chưa bật, client không được tạo.
- Nếu người dùng đã cung cấp client riêng, bean mặc định back-off.
- Properties chỉ được đăng ký trong nhánh tính năng bật, nếu hợp đồng yêu cầu cấu hình bắt buộc chỉ khi ON.

Không nên đưa SDK vào starter chỉ để condition có thể tìm thấy class nếu feature đó không phải một phần trải nghiệm mặc định. Nếu người dùng cần tự chọn SDK, hãy cung cấp autoconfigure artifact và tài liệu về dependency tùy chọn.

### 9.1. Đăng ký AutoConfiguration.imports

Trong module autoconfigure, tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.notify.autoconfigure.NotifyAutoConfiguration
```

Nếu resource thiếu hoặc sai tên class, starter có thể kéo đúng dependency nhưng auto-configuration không được phát hiện. Đây là lý do phải có consumer smoke test trên artifact đã đóng gói, không chỉ test trực tiếp bằng `AutoConfigurations.of(...)`.

### 9.2. Back-off và customization

Bean mặc định nên nhường bean do ứng dụng cung cấp khi hợp lý:

```java
@Bean
@ConditionalOnMissingBean(NotifyClient.class)
NotifyClient notifyClient(NotifyProperties properties) {
    return new NotifyClient(properties.endpoint(), properties.apiKey());
}
```

Mẫu này cho phép ứng dụng thay thế client. Hãy công bố rõ user override có miễn required properties hay không. Nếu configuration properties được bind ở cấp nested class, có thể việc validation vẫn diễn ra khi user bean đã thay client; đó là contract cần được test.

Không tạo hai bean cùng type/name rồi kỳ vọng `@Primary` giải quyết mọi trường hợp. Back-off đúng tầng làm dependency injection và behavior dễ dự đoán hơn.

## 10. Kiểm tra dependency graph mà consumer thực sự nhận

POM của starter nhìn có vẻ đúng chưa đủ. Điều cần kiểm tra là **dependency closure sau khi ứng dụng thêm starter**.

### 10.1. Maven

Xem dependency tree:

```bash
mvn dependency:tree
```

Lọc riêng artifact:

```bash
mvn dependency:tree -Dincludes=com.acme,org.springframework.boot
```

Tìm dependency đến từ nhánh nào, scope nào và có bị kéo phiên bản khác không. Nếu starter không nên kéo một integration optional, hãy xác minh nó thật sự vắng khỏi graph của consumer.

Kiểm tra dependency convergence bằng Maven Enforcer khi project có nhiều module/vendor SDK. Một starter không nên để consumer tự giải quyết xung đột version khó đoán.

### 10.2. Gradle

Xem runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm một artifact cụ thể:

```bash
./gradlew dependencyInsight --dependency acme-notify-client --configuration runtimeClasspath
```

Chú ý khác biệt giữa `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` và dependency constraints. Một dependency chỉ có trong test graph không chứng minh starter đã phát hành nó cho consumer.

### 10.3. Kiểm tra POM đã publish

Với artifact Maven đã publish hoặc cài local, đọc POM thực tế:

- Dependency nào được khai báo compile/runtime?
- Dependency nào đánh dấu optional?
- Có version đã hard-code không cần thiết không?
- Starter có phụ thuộc autoconfigure cùng version không?
- Test dependency có bị đóng gói thành runtime dependency không?
- Có dependency vendor/server mà ứng dụng không mong muốn không?

Đừng chỉ xem source POM của một module; consumer nhận POM đã được publish/resolved và có thể bị parent/BOM/profile thay đổi.

## 11. Kiểm thử trải nghiệm mặc định trong ứng dụng consumer

Nên có ít nhất hai tầng test:

1. **Autoconfigure tests:** kiểm tra condition, property, bean creation/back-off, classpath thiếu optional dependency.
2. **Starter consumer smoke test:** tạo ứng dụng chỉ thêm starter, kiểm tra auto-configuration được discover từ resource đóng gói và dependency closure đủ cho use case mặc định.

Test module autoconfigure trực tiếp với `AutoConfigurations.of(...)` không chứng minh file `AutoConfiguration.imports` đã được đóng gói đúng. Consumer smoke test phát hiện lỗi đó.

### 11.1. Test auto-configuration cơ bản

Ví dụ dùng `ApplicationContextRunner`:

```java
class NotifyAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(NotifyAutoConfiguration.class));

    @Test
    void disabledByDefaultDoesNotCreateClient() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context).doesNotHaveBean(NotifyClient.class);
        });
    }

    @Test
    void enabledWithSettingsCreatesDefaultClient() {
        runner.withPropertyValues(
                "acme.notify.enabled=true",
                "acme.notify.endpoint=https://notify.example.test",
                "acme.notify.api-key=test-token")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).hasSingleBean(NotifyClient.class);
                });
    }

    @Test
    void userClientReplacesDefault() {
        runner.withUserConfiguration(UserNotifyClientConfiguration.class)
                .withPropertyValues(
                        "acme.notify.enabled=true",
                        "acme.notify.endpoint=https://notify.example.test",
                        "acme.notify.api-key=test-token")
                .run(context -> {
                    assertThat(context).hasSingleBean(NotifyClient.class);
                    assertThat(context).hasBean("customNotifyClient");
                    assertThat(context).doesNotHaveBean("notifyClient");
                });
    }
}
```

Đây là skeleton minh họa; cần thêm import JUnit 5, AssertJ, `NotifyAutoConfiguration`, `NotifyClient` và `UserNotifyClientConfiguration`. Các method trên kiểm tra contract default OFF, ON và user override.

Nếu dependency SDK là optional, thêm test `FilteredClassLoader` để xác minh nested config không bị load khi class SDK vắng. Đồng thời kiểm tra context vẫn khởi động bình thường trong nhánh optional đó.

### 11.2. Consumer smoke test

Tạo một module hoặc project integration test chỉ khai báo starter như dependency chính:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-notify-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

Ứng dụng consumer cần có Boot application class. Test có thể khởi động context và kiểm tra:

- Auto-configuration được discover từ `AutoConfiguration.imports`.
- SDK mặc định thực sự có trên runtime classpath.
- Bean dự kiến xuất hiện khi property bật.
- Ứng dụng không phải khai báo lại từng dependency mà starter hứa cung cấp.
- Không có server/database driver hoặc integration ngoài ý muốn.
- User override được nhận diện.
- Dependency versions phù hợp BOM.

Một test chỉ gọi `AutoConfigurations.of(...)` trực tiếp không thay thế test này vì nó bỏ qua discovery qua imports resource và không kiểm tra starter POM đã đóng gói.

### 11.3. Ma trận test đề xuất

| Kịch bản | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Chỉ thêm starter, không bật feature | Dependency và startup | Context khởi động; không tạo kết nối ngoài |
| Thêm starter + bật feature + đủ settings | Default behavior | Bean/client mặc định được tạo |
| Bật nhưng thiếu required settings | Validation | Startup fail rõ ràng nếu contract yêu cầu fail-fast |
| User cung cấp bean | Back-off | Bean mặc định không tạo |
| Dùng autoconfigure không có optional SDK | Classpath condition | Context vẫn khởi động, nhánh integration bị bỏ qua |
| Dùng MVC app | Web type condition | Chỉ Servlet adapter hoạt động |
| Dùng Reactive app | Web type condition | Chỉ Reactive adapter hoạt động |
| Thêm hai starter integration | Dependency collision | Không trùng bean/server ngoài ý muốn |
| Consumer chỉ khai báo starter | Packaging/discovery | Auto-configuration được import từ resource |
| Nâng Boot BOM | Compatibility | Không có xung đột Spring Framework/Boot |

## 12. Ví dụ lựa chọn dependency cho ba sản phẩm khác nhau

### 12.1. Starter cho thư viện domain/client

Tính năng chính là một client gọi API bên ngoài:

- `spring-boot-starter` làm nền.
- SDK HTTP cốt lõi mà thư viện dùng.
- Autoconfigure module.
- Không thêm MVC server hoặc WebFlux server chỉ vì client dùng HTTP.
- Credentials/endpoint lấy từ properties hoặc secret source, không hard-code.

### 12.2. Starter cho REST API MVC

Tính năng chính là cung cấp controller/Servlet integration:

- `spring-boot-starter-web`.
- Autoconfigure module và MVC adapter.
- Có thể cần validation nếu request DTO được validate.
- Không thêm reactive server runtime.
- Không chọn database driver nếu ứng dụng tự quyết định database.

### 12.3. Starter cho reactive gateway

Tính năng chính là reactive HTTP endpoint:

- `spring-boot-starter-webflux`.
- Adapter WebFlux và autoconfigure module.
- Reactive server implementation mặc định phù hợp (thường đã được kéo bởi starter WebFlux).
- Không thêm MVC starter.
- Có test reactive context và integration test HTTP thật.

Các ví dụ là lựa chọn kiến trúc; nếu sản phẩm hỗ trợ nhiều mode, hãy phát hành starter biến thể và mô tả rõ cách kết hợp. Đừng để một starter core tự động kéo cả ba trải nghiệm.

## 13. Các lỗi thường gặp khi chọn dependency

| Triệu chứng | Lỗi thiết kế | Cách sửa |
| --- | --- | --- |
| Ứng dụng chỉ cần client nhưng tự mở server | Starter kéo web server không cần thiết | Dùng Boot baseline/client dependencies, bỏ web starter |
| Ứng dụng MVC bị kéo thêm reactive server | Starter core kéo WebFlux dù chỉ cần WebClient | Tách client dependency và WebFlux server adapter |
| Mọi consumer phải tải Kafka/AWS/Redis | Autoconfigure dependency optional không đúng hoặc starter quá lớn | Tách integration starter và kiểm tra graph |
| Không tìm thấy class lúc startup | Auto-config tham chiếu optional type ngoài nested guarded config | Dùng class-level condition và cô lập type tùy chọn |
| Auto-configuration không được phát hiện | Thiếu/sai `AutoConfiguration.imports` | Kiểm tra resource trong JAR đóng gói |
| Consumer dùng version Spring khác nhau | Không có BOM hoặc hard-code version rời rạc | Quản lý tập trung bằng Boot BOM và BOM nội bộ |
| Database connection fail vì driver không có | Starter giả định vendor database | Để consumer chọn driver hoặc cung cấp driver-specific starter |
| Consumer có hai bean cùng type | Thiếu `@ConditionalOnMissingBean` hoặc điều kiện không đúng type | Thiết kế back-off và test user override |
| Starter chạy trong test nhưng app thật không chạy | Test import class trực tiếp, bỏ qua resource/dependency closure | Thêm consumer smoke test |
| Dependency chỉ có trong test scope | POM/Gradle scope khai báo sai | Kiểm tra runtimeClasspath/POM đã publish |
| Artifact kéo theo test framework | Test dependency khai báo sai scope | Chuyển sang `test` / `testImplementation` |
| Logging bị thay đổi ngoài ý muốn | Starter ép logging backend | Dùng logging abstraction và để ứng dụng chọn backend |

## 14. Checklist trước khi phát hành custom starter

**Trải nghiệm mặc định**

- [ ] Mô tả rõ use case mà một dependency starter sẽ kích hoạt.
- [ ] Default ON/OFF có chủ đích; không tự tạo kết nối ngoài khi người dùng chỉ thêm dependency.
- [ ] Endpoint, credential và driver-specific choices được giao cho application khi chúng thuộc môi trường của application.
- [ ] User bean có thể override theo contract.

**Dependency graph**

- [ ] Có module autoconfigure chứa code và module starter làm dependency aggregator.
- [ ] Optional SDK ở autoconfigure không truyền sang mọi consumer ngoài ý muốn.
- [ ] Starter thêm lại các dependency cần cho default experience.
- [ ] Không kéo database vendor driver nếu không bắt buộc.
- [ ] Không kéo cả MVC và WebFlux nếu sản phẩm không thực sự cần cả hai.
- [ ] Không đưa test libraries vào runtime graph.
- [ ] Dependency scopes đúng với compile/runtime/API visibility.
- [ ] Dependency versions được quản lý bởi BOM và có compatibility policy.

**Auto-configuration và packaging**

- [ ] Có resource `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- [ ] Optional class được bảo vệ ở cấp cấu hình thích hợp.
- [ ] Conditions kiểm tra classpath, web type, properties và bean presence.
- [ ] Bean mặc định back-off khi user bean có mặt.
- [ ] Có metadata properties và validation phù hợp.
- [ ] Đã kiểm tra artifact thực sự được publish.

**Verification**

- [ ] Autoconfigure tests bao phủ ON/OFF, missing class và user override.
- [ ] Consumer smoke test chỉ thêm starter và xác minh default experience.
- [ ] Dependency tree không có integration ngoài ý muốn.
- [ ] Có kiểm tra MVC/Reactive nếu cung cấp web adapter.
- [ ] Có kiểm tra version alignment và dependency convergence.

**Ghi nhớ:** Starter là hợp đồng về dependency graph và trải nghiệm mặc định. Tách code auto-configuration khỏi dependency aggregator; giữ optional SDK ở module autoconfigure và chỉ kéo vào starter khi đó là phần mặc định được lựa chọn; quản lý version bằng BOM; không chọn hộ database driver hoặc web server nếu sản phẩm không cần; và kiểm tra trong một consumer project chỉ khai báo starter. Đó là cách để “thêm một dependency” thực sự mang lại một trải nghiệm rõ ràng, nhẹ và có thể dự đoán.

## Tài liệu chính thức

- Spring Boot 3.3 — Creating Your Own Starter: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration, optional dependencies và starter modules: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Dependency Versions / BOM: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Spring Boot 3.3 — Starters: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Maven — Introduction to Dependency Mechanism and Optional Dependencies: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Java Library Plugin and API/Implementation Separation: https://docs.gradle.org/current/userguide/java_library_plugin.html
