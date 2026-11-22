# proxyBeanMethods=false và cách cung cấp dependency qua tham số @Bean trong Spring Boot Auto-configuration

## 1. Cốt lõi: bean được Spring quản lý khác với lời gọi phương thức Java thông thường

Trong Spring, một phương thức có `@Bean` là **phương thức nhà máy** để container đăng ký và tạo bean. Nếu một phương thức `@Bean` thứ hai cần bean do phương thức thứ nhất cung cấp, cách ổn định là **nhận dependency bằng tham số**:

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {

    @Bean
    Engine engine() {
        return new Engine("default");
    }

    @Bean
    Vehicle vehicle(Engine engine) {
        return new Vehicle(engine);
    }
}
```

Các lớp `Engine` và `Vehicle` ở trên là kiểu minh họa, chưa có định nghĩa nên đoạn mã **không phải chương trình chạy độc lập**. Ý quan trọng: `vehicle(Engine engine)` nhận đúng `Engine` do **Spring container** giải quyết. Không cần và cũng không nên viết `vehicle() { return new Vehicle(engine()); }` chỉ để “tái sử dụng” một phương thức `@Bean`.

Với `@Configuration(proxyBeanMethods = false)`, gọi `engine()` trực tiếp từ mã Java thông thường sẽ chạy thân phương thức `engine()` như một lời gọi Java bình thường. Nếu thân phương thức tạo `new Engine(...)`, lời gọi trực tiếp có thể tạo **một object bổ sung nằm ngoài hợp đồng bean definition**; nó không bảo đảm trả lại bean singleton mà container đang quản lý.

Đây là một nguyên tắc đặc biệt quan trọng với **Spring Boot auto-configuration**: trong Spring Boot 3.3.x, `@AutoConfiguration` được meta-annotate bằng `@Configuration(proxyBeanMethods = false)`. Auto-configuration được thiết kế để khai báo những phương thức nhà máy độc lập, còn quan hệ giữa các bean được truyền qua DI của Spring.

Bài này giải thích cơ chế interception, khác nhau giữa **“gọi phương thức”** và **“đề nghị Spring tiêm bean”**, ví dụ chạy được với Java 17+ và Spring Boot, và các sai lầm khi xây dựng auto-configuration.

## 2. `proxyBeanMethods` điều khiển chính xác điều gì?

Annotation `@Configuration` thuộc Spring Framework có thuộc tính `proxyBeanMethods`:

- `@Configuration` hoặc `@Configuration(proxyBeanMethods = true)`: chế độ **full**, giá trị mặc định của annotation `@Configuration`. Spring tạo subclass tăng cường bằng CGLIB để **chặn những lời gọi phù hợp tới phương thức `@Bean`** từ configuration object do Spring quản lý. Điều này hỗ trợ *inter-bean method references* và hành vi scope, ví dụ gọi cùng một `@Bean` singleton từ một phương thức `@Bean` khác có thể trả object được container quản lý.
- `@Configuration(proxyBeanMethods = false)`: chế độ **lite** đối với phương thức `@Bean`. Container vẫn đăng ký và gọi các factory methods khi tạo bean, nhưng lời gọi Java **trực tiếp từ một phương thức tới phương thức `@Bean` khác không được Spring chặn để tra bean**.
- `@AutoConfiguration` trong Spring Boot 3.3.x: annotation này vốn đã mang `@Configuration(proxyBeanMethods = false)`; nó là một loại configuration được Boot import theo cơ chế auto-config và không hỗ trợ kỳ vọng inter-bean direct method interception.

**Giá trị false không tắt đăng ký bean, không tắt dependency injection, không đổi scope singleton mặc định và không vô hiệu hóa các điều kiện như `@ConditionalOnMissingBean`.** Nó chỉ tránh một loại proxy/enhancement dành cho **lời gọi tới các phương thức `@Bean` trên configuration class**.

### 2.1. So sánh trực quan

| Thao tác | `proxyBeanMethods=true` | `proxyBeanMethods=false` |
| --- | --- | --- |
| Spring nhận diện các phương thức `@Bean` trong class cấu hình hợp lệ | Có | Có |
| Spring gọi factory method để tạo bean | Có | Có |
| Spring có thể tiêm bean qua tham số factory method | Có | Có |
| Gọi `config.engine()` trên **configuration bean do Spring quản lý**, trong hoàn cảnh thông thường | Lời gọi được CGLIB intercept và có thể trả bean theo scope | Gọi thân hàm Java thông thường; không tự lấy bean từ context |
| Tham chiếu phụ thuộc kiểu `vehicle(engine())` | Có thể hoạt động nhờ interception trong full mode | Có nguy cơ tạo thêm object, bỏ qua lookup và condition |
| Configuration class/phương thức `@Bean` `final` | Enhancement CGLIB có giới hạn vì không thể override | Không cần loại enhancement đó |
| Phù hợp với custom auto-configuration Boot 3.x | Không phải giả định nên dựa vào | Chính là chế độ của `@AutoConfiguration` |

Cần giữ điều kiện **“configuration bean do Spring quản lý”** trong cột true: nếu bạn tự `new FeatureConfiguration()` rồi gọi `engine()`, đây vẫn là một object Java bình thường, không tự có CGLIB enhancement của context. Ngoài ra, việc intercept và kết quả chịu ảnh hưởng của scope, lifecycle và hoàn cảnh gọi; không suy rộng thành “true khiến mọi lời gọi method ở mọi nơi đều là bean lookup”.

### 2.2. Tại sao chế độ full có CGLIB?

Để chặn một lời gọi Java bình thường như `engine()`, Spring phải có khả năng thay đổi hành vi thực thi phương thức trên configuration object. Với chế độ full, Spring dùng subclass động để ghi đè những phương thức cần thiết và kiểm tra container trước khi quyết định trả bean hoặc gọi logic tạo bean.

Cách này cần class/method có thể được subclass/override, nên class cấu hình full hoặc những phương thức factory cần intercept không thể tùy tiện là `final`. Chế độ lite không cần tạo subclass đó cho bean method calls, phù hợp với những cấu hình không dùng cross-method references.

**Đừng nhầm với AOP của bean ứng dụng.** `proxyBeanMethods=false` nói về enhancement của **configuration class**, không có nghĩa các bean do nó tạo sẽ không bao giờ được AOP-proxy (ví dụ do `@Transactional` hoặc các aspect phù hợp).

## 3. `@AutoConfiguration` của Spring Boot mặc định ở chế độ lite

Trong Spring Boot 3.3.13, định nghĩa annotation `@AutoConfiguration` bao gồm:

```java
// Lược trích ý nghĩa annotation, không phải mã nguồn đầy đủ:
@Configuration(proxyBeanMethods = false)
public @interface AutoConfiguration {
    // before, after, beforeName, afterName ...
}
```

Lớp auto-config chẳng hạn:

```java
@AutoConfiguration
public class GatewayAutoConfiguration {

    @Bean
    Backend defaultBackend() {
        return new Backend("default");
    }

    @Bean
    Gateway gateway(Backend backend) {
        return new Gateway(backend);
    }
}
```

Ở đây `@AutoConfiguration` **không cần viết thêm `@Configuration(proxyBeanMethods=false)`**. Cơ chế mặc định của annotation đã phù hợp.

Vì sao Spring Boot chọn cách này?

1. Các class auto-config thường khai báo **bean mặc định theo điều kiện**, chẳng hạn `@ConditionalOnMissingBean`, để nhường chỗ cho cấu hình người dùng.
2. Mỗi `@Bean` nên mô tả một factory có đầu vào rõ ràng; sự phụ thuộc của factory nên nằm ở **tham số `@Bean`**, do container resolve.
3. Không cần khả năng gọi `@Bean` khác qua CGLIB chỉ để đưa dependency vào factory; tránh được chi phí và giới hạn của loại enhancement này.
4. Khi dependency được resolve từ context, factory tôn trọng những bean do ứng dụng cung cấp, scope, qualifier và proxy thích hợp.

Những điểm này **không bảo đảm lợi ích hiệu năng cố định cho mọi ứng dụng**. Giá trị chính là hợp đồng và cách tổ chức factory rõ ràng, đặc biệt khi điều kiện tạo bean có thể thay đổi tùy classpath và cấu hình người dùng.

## 4. Cách truyền dependency qua tham số `@Bean`

Cú pháp cốt lõi:

```java
@Bean
Gateway gateway(Backend backend) {
    return new Gateway(backend);
}
```

Spring coi tham số `Backend backend` là một dependency cần giải quyết **từ BeanFactory**, tương tự tinh thần constructor injection. Khi tạo bean `gateway`, container:

1. Xác định bean `Backend` phù hợp đang có trong context hoặc có thể được tạo theo bean definition.
2. Giải quyết ứng viên theo kiểu và các quy tắc DI có liên quan: `@Qualifier`, `@Primary`, tên tham số trong trường hợp có đủ metadata, v.v.
3. Cung cấp **object dependency do container quản lý** cho phương thức factory.
4. Nhận object `Gateway` do phương thức trả về và áp dụng lifecycle/scope của bean `gateway`.

Không cần `@Autowired` trên từng tham số `@Bean`. Nếu thiếu `Backend` bắt buộc, khởi động có thể thất bại vì dependency chưa được thỏa mãn; nếu có nhiều ứng viên không phân giải được, DI cũng có thể thất bại.

### 4.1. Truyền nhiều dependency

```java
@Bean
ReportService reportService(ReportRepository repository,
                            Clock clock,
                            MeterRegistry metrics) {
    return new ReportService(repository, clock, metrics);
}
```

Đây là **mã minh họa, không biên dịch độc lập** vì các kiểu chưa được khai báo/import. Spring sẽ resolve riêng từng tham số, bất kể chúng đến từ auto-config, component scan hay `@Bean` do ứng dụng khai báo.

Một dependency dùng trong constructor của object trả về là khác với lời gọi `reportRepository()` tới một phương thức `@Bean` khác trong cùng configuration. Tham số `repository` đã qua bean resolution của container; lời gọi method trực tiếp thì không.

### 4.2. Phân giải khi có nhiều ứng viên

Nếu context có hai bean `Backend`, có thể chỉ rõ qualifier:

```java
@Bean
Gateway gateway(@Qualifier("primaryBackend") Backend backend) {
    return new Gateway(backend);
}
```

Đây là đoạn minh họa; cần `org.springframework.beans.factory.annotation.Qualifier` và bean `primaryBackend` tương ứng. Nếu chỉ có một ứng viên, không cần qualifier. Nếu muốn chọn mặc định giữa các ứng viên, `@Primary` trên một bean là một công cụ khác. Không giả định rằng “tham số có tên giống bean” luôn thắng mọi quy tắc resolution.

### 4.3. Optional dependency và cung cấp trễ

Khi việc tạo bean phụ thuộc sự tồn tại của thư viện hay bean tùy chọn, auto-configuration thường kiểm tra `@ConditionalOnClass`, `@ConditionalOnBean` hoặc các điều kiện liên quan. Nếu factory vẫn cần truy cập bean theo nhu cầu, `ObjectProvider<T>` có thể phù hợp:

```java
@Bean
Inspector inspector(ObjectProvider<Backend> backends) {
    return new Inspector(backends.getIfAvailable());
}
```

Đây cũng là đoạn minh họa (các kiểu `Inspector` chưa được khai báo). `getIfAvailable()` có thể trả `null` khi không có bean; implement cần xử lý. Chỉ nên dùng tùy chọn khi nghiệp vụ thực sự cho phép thiếu dependency. Đối với dependency bắt buộc, tham số kiểu `Backend` rõ ràng và dễ phát hiện lỗi hơn.

## 5. Ví dụ hoàn chỉnh: back-off vẫn đúng khi dùng tham số `@Bean`

Ví dụ chạy bằng **Java 17+**, Maven và **Spring Boot 3.3.13**. Ta sẽ thử hai tình huống:

- `demo.custom=false`: không có bean `Backend` của người dùng; auto-config cung cấp default, `Gateway` nhận default đó qua tham số factory.
- `demo.custom=true`: ứng dụng có bean `Backend` riêng; auto-config nhường theo `@ConditionalOnMissingBean`; `Gateway` nhận bean người dùng. Hai trạng thái đều cho kết quả `SAME_INSTANCE=true`.

Điểm mấu chốt: nếu auto-config gọi thẳng `backend()` từ `gateway()`, sự nhất quán này sẽ bị phá vỡ khi `proxyBeanMethods=false`.

### 5.1. Cấu trúc project

```text
lite-bean-methods-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/
    │   │   ├── Backend.java
    │   │   └── Gateway.java
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   └── UserBackendConfiguration.java
    │   └── autoconfig/
    │       └── GatewayAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Chủ ý đặt main class trong `com.example.app`, auto-config trong `com.example.autoconfig`: auto-config được phát hiện qua file imports, **không phải** nhờ package con nằm trong component scanning của ứng dụng.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>lite-bean-methods-demo</artifactId>
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

Trong ví dụ này, `spring-boot-starter` đủ để tạo ứng dụng Spring Boot chạy runner. Không cần Web starter, database hay dịch vụ bên ngoài.

### 5.3. `src/main/java/com/example/api/Backend.java`

```java
package com.example.api;

public record Backend(String id) {
}
```

Dùng record Java 17 để giữ dữ liệu bất biến. `id` giúp nhìn ra factory nào đã tạo backend: `"default"` từ auto-config hay `"user"` từ ứng dụng.

### 5.4. `src/main/java/com/example/api/Gateway.java`

```java
package com.example.api;

public record Gateway(Backend backend) {
    public String send(String value) {
        return backend.id() + ":" + value;
    }
}
```

Record `Gateway` phụ thuộc vào `Backend`. Nó không phải bean chỉ vì có field `backend`; bean được đăng ký từ một factory `@Bean` bên dưới.

### 5.5. `src/main/java/com/example/autoconfig/GatewayAutoConfiguration.java`

```java
package com.example.autoconfig;

import com.example.api.Backend;
import com.example.api.Gateway;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Backend.class)
    Backend backend() {
        return new Backend("default");
    }

    @Bean
    @ConditionalOnMissingBean(Gateway.class)
    Gateway gateway(Backend backend) {
        return new Gateway(backend);
    }
}
```

**Hai chi tiết quyết định thành công:**

1. `@AutoConfiguration` đã tương đương một lớp `@Configuration(proxyBeanMethods=false)` trong Spring Boot 3.3.x. Không viết code dựa vào interception giữa hai factory methods.
2. `Gateway gateway(Backend backend)` **không gọi `backend()`**. Spring quyết định bean `Backend` nào tồn tại; nếu ứng dụng đã có user bean, factory nhận chính user bean.

`@ConditionalOnMissingBean(Backend.class)` dùng để nhường chỗ khi người dùng có bean cùng type. `@ConditionalOnMissingBean(Gateway.class)` cho phép ứng dụng còn có thể thay cả `Gateway` nếu cần.

### 5.6. `src/main/java/com/example/app/UserBackendConfiguration.java`

```java
package com.example.app;

import com.example.api.Backend;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserBackendConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "custom", havingValue = "true")
    Backend customBackend() {
        return new Backend("user");
    }
}
```

Đây là cấu hình **do ứng dụng khai báo**. Nó cũng dùng `proxyBeanMethods=false` vì không có lý do cần gọi chéo `@Bean` methods. Khi `demo.custom=true`, bean `customBackend` được đăng ký trước khi auto-config đánh giá điều kiện missing-bean. Khi false, bean user đó không tồn tại.

Tham số của `gateway(Backend backend)` ở lớp auto-config không cần biết bean tên `customBackend` hay `backend`. Nó chỉ phụ thuộc vào **type** `Backend`; có một ứng viên phù hợp trong mỗi tình huống.

### 5.7. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.api.Backend;
import com.example.api.Gateway;
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
            Backend backend, Gateway gateway, ApplicationContext context) {
        return args -> {
            System.out.println("BACKEND=" + backend.id());
            System.out.println("GATEWAY_BACKEND=" + gateway.backend().id());
            System.out.println("SAME_INSTANCE=" + (backend == gateway.backend()));
            System.out.println("AUTO_BACKEND_BEAN=" + context.containsBean("backend"));
            System.out.println("USER_BACKEND_BEAN="
                    + context.containsBean("customBackend"));
            System.out.println("MESSAGE=" + gateway.send("hello"));
        };
    }
}
```

Runner được Spring gọi sau khi context sẵn sàng. Container tiêm `Backend` và `Gateway` vào factory method `report(...)`. Dòng `backend == gateway.backend()` kiểm tra **identity**, không chỉ so sánh chuỗi ID: cùng một managed backend đã được tiêm vào cả hai nơi.

### 5.8. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.custom=false
```

`spring.main.web-application-type=none` làm ví dụ chạy rồi thoát. `logging.level.root=OFF` giảm log Spring cho dễ xem output; property này không ảnh hưởng bean conditions.

### 5.9. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.autoconfig.GatewayAutoConfiguration
```

Trong Spring Boot 3.x, file này công bố class auto-configuration candidate. `@AutoConfiguration` đặt trên class đúng nhưng không nằm trong imports và không được import bằng cách khác sẽ không tự xuất hiện chỉ nhờ annotation.

### 5.10. Chạy trường hợp A: auto-config cung cấp default

Tại thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/lite-bean-methods-demo-1.0.0.jar
```

Những dòng `ApplicationRunner` tự in (không tính thông báo của Maven/JVM/môi trường):

```text
BACKEND=default
GATEWAY_BACKEND=default
SAME_INSTANCE=true
AUTO_BACKEND_BEAN=true
USER_BACKEND_BEAN=false
MESSAGE=default:hello
```

**Giải thích:** `demo.custom=false` nên `UserBackendConfiguration.customBackend` không được đăng ký. Condition missing-bean cho `backend` của auto-config khớp, Spring đăng ký và tạo `Backend("default")`. Sau đó, khi tạo `Gateway`, nó cung cấp **chính managed bean này** qua tham số. Vì scope mặc định là singleton nên identity đúng bằng nhau.

### 5.11. Chạy trường hợp B: ứng dụng cung cấp backend riêng

Giữ nguyên JAR, chạy:

```bash
java -jar target/lite-bean-methods-demo-1.0.0.jar --demo.custom=true
```

Stdout của chương trình:

```text
BACKEND=user
GATEWAY_BACKEND=user
SAME_INSTANCE=true
AUTO_BACKEND_BEAN=false
USER_BACKEND_BEAN=true
MESSAGE=user:hello
```

**Giải thích:**

1. Command-line property `demo.custom=true` làm `@ConditionalOnProperty` trên user bean khớp.
2. Spring đã có bean definition `customBackend` kiểu `Backend` khi xét auto-config.
3. `@ConditionalOnMissingBean(Backend.class)` trong auto-config không match, vì vậy bean mặc định mang tên `backend` **không được đăng ký**.
4. `Gateway gateway(Backend backend)` vẫn được tạo vì nó **không phụ thuộc vào lời gọi `backend()`**. DI tìm bean `Backend` hiện có là `customBackend`.
5. Runner nhận cùng bean user, do đó `SAME_INSTANCE=true` và `MESSAGE=user:hello`.

Đây là lợi ích thực tiễn khi dùng tham số `@Bean` trong auto-config: **tôn trọng cấu hình ứng dụng** dù bean mặc định đã nhường chỗ.

## 6. Lỗi kinh điển: tự gọi `@Bean` method khi `proxyBeanMethods=false`

Giả sử bạn sửa riêng phương thức `gateway` trong `GatewayAutoConfiguration` thành:

```java
// Sai trong trường hợp phụ thuộc vào bean do container quản lý.
@Bean
@ConditionalOnMissingBean(Gateway.class)
Gateway gateway() {
    return new Gateway(backend());
}
```

Đoạn trên là **phương án thay thế minh họa**, không được giữ song song với `gateway(Backend backend)` trong cùng cấu hình.

Khi `proxyBeanMethods=false`:

- `backend()` được gọi như phương thức Java thuần: nó thực thi `return new Backend("default")`.
- Lời gọi này không tra bean `Backend` đang nằm trong context; thậm chí khi `@ConditionalOnMissingBean(Backend.class)` đã ngăn đăng ký bean mặc định, thân `backend()` vẫn có thể bị gọi trực tiếp.
- Nếu `demo.custom=false`, container có một managed `Backend("default")`, còn `Gateway` chứa một **object `Backend("default")` khác**. ID bằng nhau nhưng identity khác: `SAME_INSTANCE=false`.
- Nếu `demo.custom=true`, container có `Backend("user")`, nhưng `Gateway` lại nhận một instance được tạo trực tiếp bằng `backend()` mang ID `"default"`. Kết quả không tôn trọng custom backend và identity cũng sai.

Trong hai lần chạy minh họa sau khi thay phương thức, các trường quan trọng trở thành:

| Cấu hình | `BACKEND` do container cung cấp | `GATEWAY_BACKEND` | `SAME_INSTANCE` |
| --- | --- | --- | --- |
| `demo.custom=false` | `default` | `default` | `false` |
| `demo.custom=true` | `user` | `default` | `false` |

**Đây không phải Spring tạo hai singleton cùng tên.** Object được sinh ra bởi lời gọi Java trực tiếp `backend()` **không phải** bean `backend` do container quản lý. Nó có thể bỏ qua các bước phụ thuộc vào quản lý vòng đời, post-processing và wrapper/proxy được container áp dụng cho managed bean. Đừng tự khẳng định object ngoài container có đầy đủ lifecycle của bean.

Sửa về đúng phương thức:

```java
@Bean
@ConditionalOnMissingBean(Gateway.class)
Gateway gateway(Backend backend) {
    return new Gateway(backend);
}
```

### 6.1. Vì sao đổi thành `proxyBeanMethods=true` không phải cách sửa thích hợp?

Trong một class `@Configuration` thông thường, bật full mode có thể làm direct `@Bean` calls được intercept. Nhưng **`@AutoConfiguration` của Spring Boot 3.3.x mặc định là false** và được thiết kế theo mô hình factory methods độc lập. Cách sửa rõ ràng và bền vững là để Spring inject dependency qua tham số.

Đừng cố chuyển một class auto-config thành một cấu hình full mode chỉ để giữ nguyên code gọi `backend()`. Điều đó thay đổi hợp đồng thiết kế, đưa lại những ràng buộc CGLIB và vẫn làm mã khó nhận ra dependency cũng như điều kiện back-off.

## 7. Hiểu scope, proxy và vòng đời trước khi so sánh instance

Ví dụ trên dùng scope **singleton mặc định**: trong một `ApplicationContext`, cùng bean definition `Backend` thường trả cùng một instance được quản lý. Vì vậy identity `==` là phép chứng minh thích hợp.

Với bean `@Scope("prototype")`, Spring có thể tạo instance mới **mỗi lần dependency được resolve**. Khi đó không thể tự suy từ hai injection khác nhau rằng chúng phải là cùng một object. Với request/session scope hoặc scoped proxy, object được tiêm có thể là proxy đại diện cho target theo scope hiện hành.

Điểm cần giữ là:

- **Tham số `@Bean`**: đi qua cơ chế resolution của container và tôn trọng scope/proxy/qualifier.
- **Lời gọi Java trực tiếp tới factory method**: tự chạy thân phương thức; không tự tuân thủ các chính sách bean scope, condition hoặc lifecycle.
- **CGLIB của full `@Configuration`**: intercept *inter-bean calls* phù hợp, không phải khái niệm đồng nhất với AOP proxy trên mọi service.
- **Annotation `@Bean`**: mô tả cách Spring đăng ký factory; không biến mọi lần bạn gọi method đó thành thao tác container.

Đừng dùng `==` như bài test tổng quát cho mọi scope. Trong ví dụ mặc định, nó hợp lệ vì các beans liên quan đều là singleton và không có scoped proxy.

## 8. Khi nào không dùng tham số thường mà dùng cách khác?

Trong auto-config, ưu tiên factory method parameters cho dependency bắt buộc. Một số hoàn cảnh cần các công cụ khác:

| Tình huống | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Đúng một bean theo type | `@Bean Gateway gateway(Backend backend)` | Rõ ràng, Spring báo lỗi nếu thiếu |
| Nhiều bean cùng type | `@Qualifier` hoặc `@Primary` | Giải quyết ambiguity đúng business rule |
| Có thể thiếu bean | `ObjectProvider<Backend>` hoặc `Optional<Backend>` | Phải thiết kế hành vi khi vắng mặt |
| Muốn lấy bean theo thời điểm sử dụng | `ObjectProvider<Backend>` | Mỗi lần lấy vẫn tuân theo scope; đừng giả định luôn trả singleton |
| Cần danh sách nhiều plugin/strategy beans | `List<Strategy>`, `Map<String, Strategy>` | Spring có cơ chế thu thập và ordering; cần kiểm tra ứng viên |
| Dependency chỉ có khi một library tồn tại | `@ConditionalOnClass` và cấu hình riêng | Cách an toàn để tránh link class tùy chọn quá sớm |
| Bean user phải thay thế bean default | `@ConditionalOnMissingBean` trên default factory | Điều kiện nhìn thấy bean definitions đã xử lý ở thời điểm đánh giá |

Có thể inject dependency qua constructor của **configuration class**, nhưng tham số trực tiếp trên `@Bean` giúp **mỗi factory tự mô tả dependency**. Không ép mọi trường hợp vào một mô hình; chọn cách đơn giản, phù hợp với lifecycle và quy tắc resolution.

## 9. Một số nhầm lẫn và cách chẩn đoán

### 9.1. “`proxyBeanMethods=false` nghĩa là `@Bean` không hoạt động.”

Sai. Spring vẫn đăng ký các bean definitions từ `@Bean` trong class cấu hình hợp lệ và gọi factory khi tạo bean. Chỉ hành vi interception của **lời gọi method Java trực tiếp** thay đổi.

### 9.2. “Tôi có bean singleton nên gọi `backend()` trực tiếp phải trả singleton.”

Sai trong lite mode. Singleton là chính sách của **bean definition trong Spring**, không phải chính sách tự động áp đặt lên mọi lời gọi Java đến một phương thức `@Bean`.

### 9.3. “`@Bean` factory có thể gọi factory khác trực tiếp vì chúng cùng một class.”

Đây chính là bẫy của `proxyBeanMethods=false`. Việc cùng class không làm lời gọi Java trở thành DI; hãy chuyển dependency thành tham số.

### 9.4. “Bean user nhường chỗ cho default nên method của default không tồn tại nữa.”

Không chính xác. Điều kiện missing-bean có thể ngăn **bean definition của default** được thêm vào context. Thân method Java vẫn tồn tại; nếu bị gọi trực tiếp, nó vẫn có thể chạy. Điều này giải thích tình huống sai ở phần 6.

### 9.5. “Bật false loại bỏ tất cả proxy trong ứng dụng.”

Sai. Đây chỉ là CGLIB enhancement của configuration class cho `@Bean` method calls. Bean target vẫn có thể được các cơ chế AOP hoặc scoped proxies bọc khi phù hợp.

### 9.6. “`@AutoConfiguration` cần thêm `@Configuration(proxyBeanMethods=false)` mới hoạt động tốt.”

Không cần trong Spring Boot 3.3.x: `@AutoConfiguration` đã meta-annotate `@Configuration(proxyBeanMethods=false)`. Nên tập trung thiết kế các factory độc lập và khai báo dependency rõ ràng.

### 9.7. “Mọi thứ hoạt động với full mode sẽ tự hoạt động với lite mode.”

Không đúng nếu thiết kế phụ thuộc vào **direct inter-bean method invocation**. Trước khi chuyển `@Configuration` thông thường từ true sang false, rà những đoạn `return new Thing(otherBean())` và thay bằng `Thing thing(OtherBean otherBean)` tương ứng.

### 9.8. “Bean khác loại được tạo sau nên Spring không thể inject nó.”

Spring có thể giải quyết dependencies dựa trên các bean definitions hiện có và tạo bean cần thiết theo thứ tự phụ thuộc; không cần gọi factory ở đúng thứ tự trình bày trong file source. Một số vòng phụ thuộc không được giải quyết tự động, đặc biệt với constructor injection, nên cần thiết kế lại quan hệ thay vì gọi method trực tiếp để “né” DI.

### 9.9. “Khi không thấy bean, chắc là `proxyBeanMethods=false`.”

Chưa đủ bằng chứng. Cần kiểm tra auto-configuration đã được tìm qua `AutoConfiguration.imports`, các `@Conditional...` đã match, bean người dùng có làm default back off, và thông báo thiếu/multiple dependency cụ thể.

## 10. Quy trình tự kiểm tra auto-configuration

1. **Xem annotation thực tế:** class là `@AutoConfiguration` hay `@Configuration` thường? `@AutoConfiguration` của Boot 3.3.x đã là lite mode; `@Configuration` mặc định full mode nếu không khai báo khác.
2. **Dò các `@Bean`:** mỗi method nên đọc như một factory độc lập. Tìm direct calls tới factory khác, ví dụ `backend()` xuất hiện trong `gateway()`.
3. **Đối chiếu dependency:** chuyển thành tham số `gateway(Backend backend)` khi muốn sử dụng bean quản lý bởi Spring.
4. **Xem điều kiện:** `@ConditionalOnMissingBean` của default backend có thể không match khi user cung cấp backend. Bảo đảm gateway vẫn sử dụng bean user.
5. **Kiểm tra bean definitions và tên:** dùng `ApplicationContext.containsBean`, `getBean` hoặc kiểm thử bằng `ApplicationContextRunner`; đừng chỉ so sánh một field như `id` mà bỏ qua identity.
6. **Bật báo cáo điều kiện:** chạy ứng dụng với `--debug` nếu cần xem *Condition Evaluation Report*, nhưng nhớ bỏ hoặc override `logging.level.root=OFF` của demo để output điều kiện có thể hiện ra.
7. **Kiểm tra scope:** singleton, prototype hoặc scoped proxy có thể làm kết quả so sánh instance khác nhau dù DI hợp lệ.
8. **Thử cả default và user override:** giống `demo.custom=false/true` trong bài, vì lỗi direct factory call có thể bị che khi hai object đều mang giá trị `"default"`.

Lệnh gợi ý cho demo:

```bash
java -jar target/lite-bean-methods-demo-1.0.0.jar --demo.custom=true --debug --logging.level.root=DEBUG
```

Đọc condition report để biết bean mặc định được áp dụng hay back off. Không phụ thuộc vào câu log cố định theo một bản Boot; log có thể thay đổi theo phiên bản và cấu hình.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Trong Spring Boot 3.3.x, `@AutoConfiguration` có `proxyBeanMethods` ở trạng thái nào?

**Đáp án:** Nó được meta-annotate với `@Configuration(proxyBeanMethods=false)`. Không nên dựa vào direct inter-bean method interception.

**Câu 2.** Trong lite mode, gọi `new Gateway(backend())` bên trong factory method `gateway()` có bảo đảm dùng bean `Backend` trong context không?

**Đáp án:** Không. `backend()` là lời gọi Java trực tiếp, có thể tạo object mới không được container quản lý.

**Câu 3.** Viết lại factory an toàn nhất nếu `Gateway` phụ thuộc `Backend`?

**Đáp án:**

```java
@Bean
Gateway gateway(Backend backend) {
    return new Gateway(backend);
}
```

Tham số được Spring resolve từ container. Đây là đoạn mã minh họa nằm bên trong một configuration class.

**Câu 4.** Nếu user có `@Bean Backend customBackend()`, auto-config khai báo `@ConditionalOnMissingBean(Backend.class)` có tạo default backend không?

**Đáp án:** Trong cách dùng đúng và khi bean user đã được xử lý ở thời điểm điều kiện đánh giá, default **back off**. Factory `gateway(Backend backend)` vẫn có thể nhận custom backend.

**Câu 5.** Vì sao `SAME_INSTANCE=false` có thể xảy ra ngay cả khi cả hai id đều là `default`?

**Đáp án:** Một instance có thể là bean singleton của context, còn instance khác do lời gọi trực tiếp `backend()` tạo ra. Cùng giá trị dữ liệu không đồng nghĩa cùng object.

**Câu 6.** `@Configuration(proxyBeanMethods=false)` có ngăn Spring tiêm `@Bean` arguments không?

**Đáp án:** Không. DI bằng tham số `@Bean` vẫn hoạt động và chính là cách nên dùng khi factory phụ thuộc bean khác.

**Câu 7.** Dùng `@Primary` có thay thế nhu cầu truyền dependency qua tham số `@Bean` được không?

**Đáp án:** Không. `@Primary` giúp container chọn ứng viên khi có nhiều bean phù hợp. Bạn vẫn phải yêu cầu dependency bằng tham số/constructor hoặc một cơ chế container resolution khác.

**Câu 8.** Bật `proxyBeanMethods=false` có tắt `@Transactional` proxy trên service không?

**Đáp án:** Không. Hai loại proxy phục vụ nhiệm vụ khác nhau.

## 12. Tài liệu tham khảo

- [Spring Boot 3.3.13 — AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): xác nhận `@AutoConfiguration` được meta-annotate bằng `@Configuration(proxyBeanMethods=false)`.
- [Spring Framework 6.1 — Configuration API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/annotation/Configuration.html): mô tả `proxyBeanMethods`, full/lite mode, CGLIB và giới hạn của method interception.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): đăng ký auto-config, `@ConditionalOnMissingBean` và kiểm thử tình huống user override.
- [Spring Framework — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html): khác biệt giữa inter-bean references và cách cung cấp dependency đúng bằng DI.

**Ghi nhớ:** Hãy coi mỗi phương thức `@Bean` trong auto-configuration là **một factory được container gọi**, và khai báo bean phụ thuộc bằng **tham số của factory**. Với `proxyBeanMethods=false`, cách viết `gateway(Backend backend)` giữ đúng managed dependency, tôn trọng user override và tránh những object được tạo ngoài container bởi lời gọi `backend()` trực tiếp.
