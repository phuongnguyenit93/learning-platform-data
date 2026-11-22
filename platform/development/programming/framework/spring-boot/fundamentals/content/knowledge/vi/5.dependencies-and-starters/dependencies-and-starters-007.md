# Thêm dependency có thể kích hoạt auto-configuration như thế nào

Trong Spring Boot, một thay đổi nhỏ trong `build.gradle` hoặc `pom.xml` đôi khi làm thay đổi hành vi của cả ứng dụng. Chỉ cần thêm `spring-boot-starter-web`, ứng dụng có thể trở thành HTTP server; thêm `spring-boot-starter-security`, các HTTP request có thể bắt đầu phải xác thực; thêm thư viện truy cập dữ liệu, Boot có thể tự tạo `DataSource`, transaction manager hoặc repository infrastructure khi đủ điều kiện.

Đây là tác dụng của **auto-configuration** (tự động cấu hình): Spring Boot kiểm tra những thư viện thực sự có mặt khi chạy ứng dụng, kết hợp với cấu hình và các bean hiện có, rồi quyết định nên tạo thêm thành phần Spring nào. **Thêm dependency là một tín hiệu đầu vào, không phải cam kết rằng mọi cấu hình liên quan sẽ được kích hoạt.**

## 1. Từ dependency đến bean: toàn bộ chuỗi diễn ra như thế nào?

Hãy hình dung quá trình theo thứ tự sau:

~~~text
Sửa build.gradle / pom.xml
             │
             ▼
Gradle / Maven phân giải dependency và các dependency bắc cầu
             │
             ▼
Classpath lúc chạy thay đổi
             │
             ▼
Spring Boot khởi động, nạp danh sách ứng viên auto-configuration
             │
             ▼
Đánh giá điều kiện:
  - Class/thư viện cần thiết có tồn tại?
  - Đang chạy ứng dụng web loại nào?
  - Property có bật chức năng đó?
  - Đã có bean do ứng dụng hoặc thư viện khác cung cấp?
  - Các điều kiện tích hợp khác có thỏa mãn?
             │
       ┌─────┴─────┐
       │           │
     ĐÚNG         SAI
       │           │
       ▼           ▼
  Đăng ký bean   Bỏ qua cấu hình/bean
  và hạ tầng
       │
       ▼
Ứng dụng thể hiện hành vi mới khi chạy
~~~

Chẳng hạn:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Dependency này đưa Spring Web MVC, các thư viện hỗ trợ HTTP và một Servlet container nhúng mặc định vào runtime classpath theo tập dependency của starter. Nếu các điều kiện tương ứng đều đúng, Spring Boot tự đăng ký những thành phần như `DispatcherServlet`, hạ tầng ánh xạ request, HTTP message converters và web server. Nhờ vậy, ta không phải tự tạo tất cả bằng `@Bean`.

**Thời điểm quan trọng:** Việc đánh giá auto-configuration thông thường diễn ra **khi tạo Spring application context trong quá trình khởi động**. Sửa `build.gradle` rồi giữ nguyên JVM đang chạy không tự làm context hiện tại được cấu hình lại; cần đồng bộ dependency, build/chạy lại ứng dụng phù hợp.

## 2. Phân biệt dependency, starter và auto-configuration

Ba khái niệm này liên quan nhưng không giống nhau.

| Khái niệm | Bản chất | Tác dụng |
|---|---|---|
| **Dependency** | Quan hệ phụ thuộc tới một thư viện/module | Làm class và tài nguyên của thư viện có mặt ở compile/runtime classpath tùy scope |
| **Spring Boot starter** | Một dependency thuận tiện gom các thư viện thường cần cho một nhóm chức năng | Giúp đưa đúng nhóm dependency vào dự án với ít khai báo |
| **Auto-configuration** | Các lớp cấu hình Spring có điều kiện, được Boot nạp khi khởi tạo context | Quyết định tạo bean/hạ tầng nào dựa trên classpath, property, bean và môi trường |

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

- `spring-boot-starter-web` mang những thư viện thường dùng cho ứng dụng HTTP dựa trên Spring MVC.
- `spring-boot-starter-validation` đưa hạ tầng Bean Validation thích hợp vào classpath để hỗ trợ validation khi các điều kiện cấu hình phù hợp.
- Các lớp auto-configuration của Boot sẽ xem những thứ có trong classpath rồi tạo những bean/hạ tầng có thể áp dụng.

**Starter không phải annotation và không phải đoạn mã chủ động chạy lúc thêm dòng dependency.** Mặt khác, một thư viện riêng lẻ không phải starter vẫn có thể ảnh hưởng tới auto-configuration nếu làm thỏa điều kiện classpath, hoặc nếu chính JAR đó cung cấp auto-configuration theo cơ chế đăng ký của Boot.

### Dependency bắc cầu cũng có ảnh hưởng

Giả sử dự án chỉ thêm một starter nhưng starter lại kéo theo nhiều thư viện. Spring Boot quan sát **runtime classpath sau khi công cụ build phân giải**, không chỉ những dòng do lập trình viên khai báo trực tiếp:

~~~text
spring-boot-starter-web
   ├── spring-web
   ├── spring-webmvc
   ├── thư viện JSON được starter sử dụng
   └── servlet container nhúng mặc định
~~~

Danh sách cụ thể phụ thuộc phiên bản Spring Boot và cấu hình dependency. Vì vậy, việc loại trừ một transitive dependency hoặc đổi phiên bản thư viện cũng có thể khiến một điều kiện auto-configuration chuyển từ đúng sang sai.

## 3. Ai bật cơ chế auto-configuration?

Ứng dụng Spring Boot thường có:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bao gồm các chức năng tương đương với:

- `@SpringBootConfiguration`: khai báo nguồn cấu hình ứng dụng.
- `@EnableAutoConfiguration`: bật cơ chế chọn auto-configuration.
- `@ComponentScan`: tìm các component do ứng dụng khai báo trong những package phù hợp.

Phân biệt hai việc thường bị nhầm:

**Component scanning** tìm `@Component`, `@Service`, `@Controller`, `@Configuration` và những stereotype tương ứng trong phạm vi package được chỉ định. **Auto-configuration** nhập các lớp cấu hình được thư viện đăng ký sẵn rồi đánh giá điều kiện của chúng. Auto-configuration của Boot không phụ thuộc vào việc lớp cấu hình của thư viện phải nằm trong package con của lớp main.

Trong **Spring Boot 3.x**, các auto-configuration class được thư viện khai báo trong tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng là tên đầy đủ của một lớp cấu hình, chẳng hạn `com.example.lib.ExampleAutoConfiguration`. Khi cơ chế `@EnableAutoConfiguration` hoạt động, Boot đọc các danh sách đó từ các JAR có liên quan, đánh giá điều kiện và nhập những cấu hình thích hợp. Đây là cơ chế đăng ký ứng viên, chưa đồng nghĩa mọi ứng viên đều chạy.

Một thư viện thông thường chỉ chứa class và không đăng ký auto-configuration vẫn có thể làm thay đổi kết quả, vì một cấu hình **đã có sẵn** trong `spring-boot-autoconfigure` có thể kiểm tra sự tồn tại của class vừa xuất hiện.

## 4. Những điều kiện nào quyết định cấu hình có được kích hoạt?

Spring Boot sử dụng họ annotation `@Conditional...`. Các điều kiện có thể nằm trên lớp auto-configuration hoặc trên từng phương thức `@Bean`.

| Điều kiện | Ý nghĩa | Ví dụ tình huống |
|---|---|---|
| `@ConditionalOnClass` | Class cụ thể có trên classpath | Có thư viện JDBC/Jackson/Spring MVC tương ứng |
| `@ConditionalOnMissingClass` | Class cụ thể không có trên classpath | Chọn cấu hình thay thế khi thiếu một tích hợp |
| `@ConditionalOnBean` | Đã có một bean thỏa yêu cầu | Chỉ tạo tích hợp khi một thành phần nền tảng đã được đăng ký |
| `@ConditionalOnMissingBean` | Chưa có bean tương ứng | Để cấu hình mặc định nhường chỗ cho bean của ứng dụng |
| `@ConditionalOnProperty` | Một property tồn tại hoặc có giá trị theo điều kiện | Bật/tắt một khả năng bằng cấu hình |
| `@ConditionalOnWebApplication` | Ứng dụng thuộc loại web phù hợp | Chỉ cấu hình Servlet hoặc reactive web |
| `@ConditionalOnNotWebApplication` | Ứng dụng không chạy kiểu web | Chọn cấu hình dành cho ứng dụng non-web |
| `@ConditionalOnResource` | Có tài nguyên được chỉ định | Chỉ kích hoạt khi classpath chứa resource yêu cầu |

Đó là những điều kiện phổ biến; cấu hình thực tế có thể có nhiều điều kiện đồng thời, điều kiện tổ hợp hoặc logic riêng. Ví dụ, để tạo bean phục vụ Spring MVC, một auto-configuration có thể vừa yêu cầu các class MVC có mặt, vừa yêu cầu ứng dụng là **Servlet web application**, vừa kiểm tra bean đã được tạo trước đó.

### 4.1. Classpath mở ra khả năng, không bảo đảm bean xuất hiện

Xét logic minh họa:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.mail.MailClient")
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailGateway.class)
    @ConditionalOnProperty(
            prefix = "app.mail",
            name = "enabled",
            havingValue = "true"
    )
    MailGateway mailGateway() {
        return new MailGateway();
    }
}
~~~

`MailAutoConfiguration` và `MailGateway` là các kiểu minh họa của một thư viện giả định; đây **không phải** các class có sẵn của Spring Boot.

Bean `MailGateway` chỉ có thể được tạo khi:

1. Auto-configuration của thư viện đã được Boot đăng ký và đưa vào diện đánh giá.
2. Class `com.vendor.mail.MailClient` có trên classpath.
3. `app.mail.enabled=true`.
4. Chưa có bean `MailGateway` khác khiến điều kiện `@ConditionalOnMissingBean` không thỏa.

Nếu thiếu một điều kiện, cấu hình hoặc phương thức bean tương ứng sẽ bị bỏ qua. Đây là lý do một dependency có thể **không làm thay đổi hành vi dễ quan sát** trong môi trường hiện tại.

### 4.2. Cơ chế “back off”: tôn trọng cấu hình do ứng dụng tự khai báo

Nhiều auto-configuration của Boot dùng `@ConditionalOnMissingBean` để cung cấp **giá trị mặc định**. Khi ứng dụng đã khai báo bean phù hợp, Boot thường nhường quyền cho cấu hình đó.

Sơ đồ:

~~~text
Auto-configuration muốn tạo bean loại X
              │
              ▼
ApplicationContext đã có bean X phù hợp?
       │                         │
      Có                       Chưa
       │                         │
       ▼                         ▼
Giữ bean hiện có          Tạo bean mặc định
và bỏ qua mặc định        nếu các điều kiện khác đúng
~~~

Không nên suy rộng rằng **mọi** auto-configuration đều tự động nhường chỗ theo cùng một quy tắc. Hãy xem chính xác điều kiện trên bean đang quan tâm; một số cấu hình cần thêm property, số lượng bean cụ thể hoặc thứ tự đăng ký.

### 4.3. Loại ứng dụng web cũng là một điều kiện

Thêm `spring-boot-starter-webflux` không nhất thiết khiến server chuyển sang reactive nếu ứng dụng đã có `spring-boot-starter-web`. Theo lựa chọn web application type mặc định của Boot, khi cả Spring MVC và WebFlux cùng hiện diện, ứng dụng thường được cấu hình thành **Servlet/MVC application**. Vẫn có thể sử dụng `WebClient` trong ứng dụng đó.

Điều này minh họa rằng **có class trên classpath chưa đủ**: điều kiện về môi trường và loại web runtime vẫn quyết định auto-configuration nào phù hợp.

## 5. Ví dụ 1 — Thêm starter web làm ứng dụng có HTTP server

Giả sử ban đầu ứng dụng chỉ có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Khi chưa có web stack, đây có thể là ứng dụng Boot **non-web**. Thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Starter đem vào runtime classpath những thành phần cần thiết cho Spring MVC và Servlet container nhúng mặc định. Nếu không có cấu hình đặc biệt làm thay đổi loại ứng dụng hoặc ngăn hạ tầng web, Boot sẽ:

- Chọn kiểu **Servlet web application**.
- Cấu hình Servlet web server nhúng và các bean web liên quan.
- Đăng ký `DispatcherServlet` cùng cơ chế tìm handler và xử lý request.
- Cấu hình các HTTP message converter phù hợp với thư viện có trên classpath, thường bao gồm khả năng xử lý JSON.

Khi đó, controller:

~~~java
package com.example.catalog.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthGreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
~~~

có thể được Spring đăng ký nếu `com.example.catalog.api` nằm trong phạm vi component scan. Request đến `GET /hello` có thể được xử lý mà không cần viết cấu hình `DispatcherServlet` thủ công.

**Hai cơ chế cùng tham gia:** Auto-configuration dựng hạ tầng web; component scan tìm controller do chúng ta viết. Có starter web nhưng controller nằm ngoài phạm vi scan thì endpoint vẫn có thể không được đăng ký.

## 6. Ví dụ 2 — Thêm Spring Security thay đổi hành vi của HTTP API

Trong ứng dụng MVC đang chạy được, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Dependency này đưa Spring Security vào classpath. Khi điều kiện phù hợp và ứng dụng chưa cung cấp chính sách bảo mật thay thế, Spring Boot và Spring Security có thể thiết lập **cấu hình bảo mật web mặc định**.

Hiệu ứng dễ thấy trong một ứng dụng MVC điển hình là:

- Những request từng truy cập được không cần xác thực giờ có thể bị từ chối hoặc yêu cầu đăng nhập.
- Ứng dụng được gắn hạ tầng Spring Security filter chain.
- Nếu chưa có cách cấu hình người dùng/xác thực khác, Boot có thể tạo một tài khoản phát triển mặc định và ghi mật khẩu được sinh ra vào log lúc khởi động.

Ví dụ, trước khi thêm starter, `GET /hello` có thể trả HTTP 200. Sau khi thêm starter và khởi động lại, request chưa xác thực có thể nhận **HTTP 401**, hoặc gặp quy trình đăng nhập khác tùy cách client gửi request và cơ chế xác thực được thương lượng. Không nên coi một mã HTTP cụ thể là bất biến ở mọi cấu hình.

Nếu ứng dụng cần chính sách riêng, có thể khai báo bean `SecurityFilterChain` (trên Servlet stack):

~~~java
package com.example.catalog.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/hello").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Bean này khiến cấu hình bảo mật web mặc định tương ứng của Boot **nhường chỗ**; chính sách trong ứng dụng sẽ quyết định endpoint nào công khai. Ví dụ chỉ minh họa phân quyền URL. Trong hệ thống thực tế còn phải chọn đúng nguồn identity, phương thức đăng nhập, chính sách CSRF/CORS và bảo vệ method phù hợp với loại client.

Đối với **WebFlux**, lớp cấu hình Security tương ứng dùng `SecurityWebFilterChain` và `ServerHttpSecurity`; không dùng nguyên xi `HttpSecurity` của Servlet.

**Bài học:** Một starter tưởng như chỉ thêm “thư viện API” thực tế có thể kích hoạt những bean/filter mới và thay đổi cách client tương tác với ứng dụng.

## 7. Ví dụ 3 — Thêm Spring Data JPA có thể kích hoạt hạ tầng database

Đoạn cấu hình Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Starter JPA đưa vào classpath các thư viện như Spring Data JPA, JPA provider và hạ tầng JDBC liên quan. Trong trường hợp cấu hình database đầy đủ, Boot có thể cấu hình:

1. Một `DataSource` sử dụng driver và kết nối được cấu hình.
2. `EntityManagerFactory` để quản lý các entity JPA.
3. Transaction manager phù hợp cho giao dịch JPA.
4. Hạ tầng Spring Data JPA repository và những repository trong phạm vi quét thích hợp.

Ví dụ cấu hình cho PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=${DB_PASSWORD}
~~~

Phần entity và repository của ứng dụng:

~~~java
package com.example.catalog.product;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.jpa.repository.JpaRepository;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}

interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Ví dụ mã đặt hai kiểu trong cùng package để minh họa; trong dự án thực tế có thể chia thành hai file Java tương ứng.

Tuy nhiên, **chỉ thêm starter JPA không bảo đảm ứng dụng sẽ kết nối database thành công**. Nếu chưa có driver phù hợp, chưa khai báo URL kết nối, chưa có embedded database khả dụng hoặc cấu hình sai, việc khởi tạo `DataSource`/JPA có thể thất bại và khiến ứng dụng không khởi động. Một số bean cũng sẽ không được tạo nếu điều kiện khác chưa thỏa.

Ngược lại, nếu thêm starter nhưng ứng dụng đã khai báo `DataSource`, một số auto-configuration có thể dùng lại bean đó hoặc nhường cho nó, tùy điều kiện cụ thể. Nên xem cơ chế này như **sự phối hợp giữa dependency, cấu hình và bean đang tồn tại**.

### Phân biệt với dữ liệu reactive

`spring-boot-starter-data-jpa` thường kết hợp với **JDBC**, mô hình truy cập I/O blocking. Thêm `spring-boot-starter-webflux` không làm JPA tự biến thành reactive. Với truy cập SQL reactive, cần xem xét `spring-boot-starter-data-r2dbc`, R2DBC driver và transaction manager reactive tương ứng. Chọn một starter phù hợp với đường đi I/O thực tế, không chỉ dựa trên việc controller trả `Mono`.

## 8. Vì sao “thêm một thư viện” đôi khi không có tác dụng, đôi khi làm ứng dụng lỗi?

### Trường hợp A: Có class nhưng thiếu điều kiện môi trường

Auto-configuration dành cho Servlet chỉ phù hợp với Servlet web application; ứng dụng CLI hoặc reactive web có thể không đáp ứng điều kiện. Dependency đã có nhưng một phần cấu hình bị bỏ qua.

### Trường hợp B: Property đang tắt chức năng

Một số auto-configuration yêu cầu property thỏa điều kiện. Ví dụ trong cấu hình minh họa của thư viện `MailAutoConfiguration` phía trên, thiếu `app.mail.enabled=true` thì bean không được tạo. Cần xem đúng tên property và giá trị mặc định của từng thư viện; không tồn tại một property “bật tất cả auto-configuration”.

### Trường hợp C: Đã có bean nên mặc định được bỏ qua

Nhiều cấu hình dùng `@ConditionalOnMissingBean`. Nếu ứng dụng đã khai báo bean phù hợp, Boot có thể không tạo bản mặc định. Đây là chủ đích để cho phép tùy chỉnh.

### Trường hợp D: Dependency không nằm trên runtime classpath

Một thư viện chỉ khai báo trong cấu hình `testImplementation` sẽ chủ yếu phục vụ test và thường **không có trên runtime classpath của ứng dụng production**. Phạm vi dependency khác nhau dẫn tới hành vi khác nhau. Tương tự, `compileOnly` không mang tính chất giống `implementation` khi chạy.

### Trường hợp E: Có bean definition nhưng không khởi tạo được

Đánh giá điều kiện thành công không đồng nghĩa bean luôn tạo được. Việc kết nối database, resolve secret, bind configuration properties hoặc xử lý dependency của constructor có thể lỗi. Ví dụ auto-configuration chọn đường JPA nhưng `DataSource` không thể kết nối tới database.

### Trường hợp F: Một dependency thay đổi nhánh cấu hình đã được chọn

Khi classpath có thêm hoặc mất đi một công nghệ, điều kiện `@ConditionalOnClass`/`@ConditionalOnMissingClass` có thể đổi kết quả; thêm bean của ứng dụng cũng có thể làm đổi `@ConditionalOnMissingBean`. Vì vậy nâng cấp, thêm hoặc exclude dependency cần kiểm tra **hành vi runtime**, không chỉ xem build thành công.

## 9. Một auto-configuration do thư viện tự cung cấp trông như thế nào?

Trong Spring Boot 3.x, một thư viện tích hợp có thể khai báo cấu hình tự động của chính nó. Ví dụ một thư viện audit giả định:

~~~java
package com.example.audit.autoconfigure;

import com.example.audit.AuditFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditFormatter.class)
    @ConditionalOnProperty(
            prefix = "audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    AuditFormatter auditFormatter() {
        return new AuditFormatter();
    }
}
~~~

Giả định `AuditFormatter` là class công khai của cùng thư viện và có constructor không tham số. Thư viện sẽ đặt tài nguyên:

~~~text
src/main/resources/META-INF/spring/
  org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.example.audit.autoconfigure.AuditAutoConfiguration
~~~

Khi ứng dụng Boot thêm JAR thư viện này vào runtime classpath, Boot có thể tìm được auto-configuration của nó mà không cần người dùng viết `@Import(AuditAutoConfiguration.class)`. Với cấu hình trên:

- `audit.enabled` không được khai báo: điều kiện property vẫn đúng nhờ `matchIfMissing = true`.
- `audit.enabled=true`: có thể tạo bean `AuditFormatter` nếu chưa có bean cùng loại.
- `audit.enabled=false`: bỏ qua bean do phương thức này khai báo.
- Ứng dụng đã đăng ký bean `AuditFormatter` của riêng mình: `@ConditionalOnMissingBean` khiến cấu hình mặc định nhường chỗ.

Ví dụ này giúp thấy vì sao việc thêm một **JAR có auto-configuration** có thể tự thay đổi Spring context. Thư viện chỉ chứa class thông thường mà không đăng ký cấu hình như trên sẽ không tự tạo bean theo cùng cơ chế, trừ khi có cấu hình khác đã hiện diện phản ứng với class của nó.

## 10. Boot chọn thứ tự và giải quyết xung đột như thế nào?

Auto-configuration không chỉ xét điều kiện từng lớp một cách hoàn toàn độc lập. Một cấu hình có thể cần bean tạo bởi cấu hình khác, hoặc cần đánh giá sau khi bean do người dùng khai báo đã được ghi nhận.

Spring Boot hỗ trợ chỉ định thứ tự tương đối của auto-configuration qua metadata/annotation như `@AutoConfigureBefore`, `@AutoConfigureAfter` hoặc thuộc tính `before`/`after` của `@AutoConfiguration`. Thứ tự này ảnh hưởng tới **thứ tự xử lý các auto-configuration definition**, không bảo đảm thứ tự khởi tạo bean trong mọi tình huống.

Trong ứng dụng thông thường, không nên cố dựa vào thứ tự tình cờ của dependency để thay thế bean. Khi cần tùy chỉnh, ưu tiên:

1. Cấu hình qua property chính thức của starter.
2. Khai báo bean ứng dụng nếu auto-configuration hỗ trợ cơ chế back off.
3. Chỉ loại trừ auto-configuration cụ thể khi có lý do rõ ràng.

**Dependency management** của Spring Boot giúp chọn tập phiên bản tương thích của nhiều thư viện phổ biến. Nhưng phiên bản được quản lý và việc auto-configuration có kích hoạt là **hai vấn đề khác nhau**: cùng một dependency vẫn có thể cho cấu hình khác khi property, classpath hoặc bean thay đổi.

## 11. Kiểm soát auto-configuration khi không muốn dùng mặc định

### 11.1. Ưu tiên cấu hình bằng property

Nhiều starter có các property như `spring.datasource.*`, `spring.jpa.*`, `server.port` hoặc `management.*` để điều chỉnh chức năng. Ví dụ:

~~~properties
server.port=8081
spring.jpa.show-sql=false
~~~

Tên property chỉ có ý nghĩa khi các thành phần tương ứng hiện diện và được cấu hình. Không nên hiểu rằng thêm `spring.jpa.show-sql=false` sẽ tự mang JPA vào ứng dụng nếu không có dependency.

### 11.2. Cung cấp bean tùy chỉnh

Khi auto-configuration có `@ConditionalOnMissingBean`, có thể để Spring dùng bean do ứng dụng khai báo. Chẳng hạn cấu hình bảo mật web tùy chỉnh bằng `SecurityFilterChain` giúp thay đổi chính sách mặc định theo nhu cầu thực tế.

### 11.3. Exclude auto-configuration

Khi chắc chắn không muốn Boot tạo một hạ tầng cụ thể, có thể loại trừ đúng auto-configuration:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Hoặc thông qua property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Hai ví dụ mô tả **hai cách cấu hình thay thế nhau**, không cần dùng cùng lúc. Chúng chỉ thích hợp khi việc không có `DataSource` do Boot tạo là quyết định có chủ ý; các auto-configuration hoặc bean khác phụ thuộc `DataSource` vẫn có thể gặp vấn đề.

Không nên loại trừ hàng loạt auto-configuration chỉ để ứng dụng vượt qua lỗi khởi động. Trước hết cần xác định vì sao một điều kiện đã được chọn và bean nào thất bại.

## 12. Tìm chính xác auto-configuration nào đang bật hoặc bị bỏ qua

Khi thêm starter và thấy ứng dụng thay đổi hành vi, Spring Boot có công cụ để điều tra dựa trên điều kiện thực tế.

### Bật condition evaluation report

Chạy ứng dụng với:

~~~text
--debug
~~~

hoặc cấu hình:

~~~properties
debug=true
~~~

Boot có thể ghi **Conditions Evaluation Report** vào log. Báo cáo giúp phân biệt:

- **Positive matches**: cấu hình đáp ứng các điều kiện đã đánh giá.
- **Negative matches**: cấu hình bị bỏ qua vì một hoặc nhiều điều kiện không thỏa.
- **Exclusions**: các auto-configuration đã bị loại trừ.
- Các cấu hình không điều kiện khi được báo cáo.

Ví dụ thông điệp mang tính minh họa:

~~~text
DataSourceAutoConfiguration matched:
  - @ConditionalOnClass found required classes

SomeFeatureAutoConfiguration did not match:
  - @ConditionalOnProperty did not find the expected value
~~~

Nội dung và định dạng thực tế phụ thuộc phiên bản Spring Boot, dependency và ứng dụng. **Matched** có nghĩa điều kiện cấu hình được đáp ứng; không bảo đảm mọi bean đã khởi tạo thành công hoặc kết nối dịch vụ ngoài đã hoạt động.

### Spring Boot Actuator

Nếu ứng dụng có `spring-boot-starter-actuator`, endpoint `conditions` có thể cung cấp thông tin đánh giá điều kiện; việc có thể gọi qua HTTP còn phụ thuộc exposure và security configuration. Chỉ bật/cho phép truy cập endpoint chẩn đoán trong môi trường và phạm vi bảo mật phù hợp.

### Xem dependency tree

Nếu không hiểu một class xuất hiện từ đâu, xem dependency đã được phân giải:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Hoặc truy vết một thư viện cụ thể:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath
~~~

Đây là lệnh **tham khảo để người học tự thực hiện** trong dự án Gradle phù hợp. Dùng `./gradlew` trên hệ Unix-like hoặc `gradlew.bat` trên Windows. Việc nhìn vào **runtimeClasspath** quan trọng vì auto-configuration thường quyết định theo class và resource có mặt **khi ứng dụng chạy**.

### Đặt câu hỏi theo nguyên nhân

Giả sử sau khi thêm `spring-boot-starter-data-jpa` ứng dụng không khởi động:

1. Xác nhận starter và JDBC driver nào có trên runtime classpath.
2. Xem lỗi gốc, ví dụ `DataSource` không có URL/driver phù hợp hoặc database không kết nối được.
3. Đọc Conditions Evaluation Report xem những cấu hình nào matched.
4. Kiểm tra property theo environment/profile hiện hành, bean đã khai báo và các loại trừ.
5. Chọn sửa cấu hình, cung cấp bean hoặc bỏ dependency không cần thiết; **không mặc định lỗi nằm ở Spring Boot**.

## 13. Kịch bản so sánh: cùng ứng dụng, thay một dependency

Giả sử dự án có controller `GET /products` với dữ liệu mẫu in-memory. Các kết quả dưới đây là **tình huống điển hình với cấu hình mặc định**, có thể khác nếu ứng dụng tự khai báo bean hoặc property.

| Trạng thái dependency | Những thay đổi có thể quan sát |
|---|---|
| Chỉ có `spring-boot-starter` | Khởi động context Spring; chưa tự có HTTP server chỉ từ starter cơ bản |
| Thêm `spring-boot-starter-web` | Web application Servlet, embedded server và hạ tầng Spring MVC nếu đủ điều kiện; có thể phục vụ `/products` |
| Thêm tiếp `spring-boot-starter-security` | Xuất hiện security filter chain mặc định và yêu cầu xác thực đối với nhiều request nếu chưa tùy chỉnh |
| Thêm tiếp `spring-boot-starter-data-jpa` | Có cơ sở để cấu hình JPA, `DataSource` và repository; có thể lỗi khởi động nếu thiếu cấu hình database phù hợp |
| Bỏ starter Security hoặc thay bằng cấu hình riêng | Hành vi bảo mật thay đổi theo classpath và các bean/security policy còn lại |

Hãy đọc bảng từ trái sang phải như các **thay đổi đầu vào** dẫn tới đánh giá lại điều kiện lúc khởi động; không phải một danh sách các bước mà mọi ứng dụng Spring Boot đều phải làm.

## 14. Nguyên tắc thực hành khi thêm dependency

Khi chuẩn bị thêm một starter vào Spring Boot, nên trả lời năm câu hỏi:

1. **Thư viện nào thực sự vào runtime classpath?** Xem cả transitive dependencies, exclusion và dependency scope.
2. **Auto-configuration nào có thể được kích hoạt?** Xác định những cấu hình liên quan đến classpath mới.
3. **Những điều kiện nào còn phải thỏa?** Bao gồm loại ứng dụng, property, bean đã tồn tại và cấu hình môi trường.
4. **Hành vi runtime nào có thể đổi?** Ví dụ một HTTP server bắt đầu lắng nghe, filter bảo mật xuất hiện, database được kết nối hoặc bean mặc định bị thay thế.
5. **Làm sao xác nhận nguyên nhân?** Kiểm tra log khởi động, Conditions Evaluation Report, danh sách bean/endpoint và thử nghiệm tích hợp phù hợp.

Một dependency trong Spring Boot vì thế **không chỉ cung cấp class để lập trình viên gọi**. Nó còn có thể là tín hiệu làm những điều kiện auto-configuration trở thành đúng, dẫn đến Spring đăng ký bean và thiết lập hạ tầng khi khởi động. Ngược lại, khi điều kiện không thỏa hoặc ứng dụng đã cấu hình rõ ràng, Boot có thể bỏ qua cấu hình mặc định. Nắm được chuỗi **dependency → classpath → điều kiện → bean → hành vi** giúp giải thích những thay đổi tưởng như bất ngờ sau mỗi lần thêm starter.
