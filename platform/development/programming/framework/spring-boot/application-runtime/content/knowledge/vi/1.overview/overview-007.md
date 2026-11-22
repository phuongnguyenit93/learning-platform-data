# Kiến thức Java 21, IoC và Spring Boot 3.3 cần chuẩn bị

## 1. Mục tiêu và bức tranh tổng thể

Trước khi học **Spring Boot Application Runtime**, cần nắm ba lớp kiến thức bổ trợ:

- **Java 21 và JVM:** viết, biên dịch, chạy chương trình; hiểu kiểu dữ liệu, hướng đối tượng, ngoại lệ, collection, luồng và cách quản lý tài nguyên.
- **Spring Framework và IoC/DI:** hiểu vì sao một đối tượng có thể được Spring tạo, cấu hình, kết nối với các phụ thuộc và quản lý vòng đời.
- **Spring Boot 3.3:** hiểu cách ứng dụng Spring khởi động, chọn cấu hình mặc định từ classpath, đọc cấu hình ngoài và khởi chạy máy chủ web nhúng khi cần.

Phân biệt ba vai trò:

| Khái niệm | Đảm nhiệm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Java 21 | Ngôn ngữ, thư viện chuẩn, JVM, luồng chạy chương trình | Mã được biên dịch và thực thi như thế nào? |
| Spring IoC container | Tạo và quản lý các `bean`, tiêm phụ thuộc, gọi các điểm vòng đời | Ai tạo `Service` và cung cấp `Service` cho `Controller`? |
| Spring Boot 3.3 | Tập hợp starter, auto-configuration, bootstrap và các tiện ích chạy ứng dụng | Vì sao thêm starter web thì có thể chạy HTTP server mà không phải tự dựng Tomcat? |

**Kết quả mong đợi:** tự chạy được một ứng dụng nhỏ với Java 21, giải thích được sơ đồ phụ thuộc `Controller -> Service`, biết vì sao `@SpringBootApplication` khởi tạo được `ApplicationContext`, và tự xử lý các lỗi thiết lập phổ biến.

## 2. Chuẩn bị môi trường và hiểu đúng phiên bản

Spring Boot **3.3.x yêu cầu tối thiểu Java 17**; dùng **JDK 21** là lựa chọn phù hợp để học đồng thời các tính năng Java 21. Dòng Spring Boot 3.3 dựa trên Spring Framework 6.1, dùng hệ sinh thái `jakarta.*` thay cho nhiều API Java EE `javax.*` cũ. Với ứng dụng Spring MVC thông thường, starter web cung cấp máy chủ Servlet nhúng (mặc định Tomcat).

Chuẩn bị:

1. Cài **JDK 21**, thiết lập `JAVA_HOME` và đường dẫn thực thi nhất quán giữa IDE, terminal và công cụ build.
2. Cài **Maven 3.6.3+** (hoặc Gradle bản được Spring Boot 3.3 hỗ trợ); ưu tiên Maven/Gradle Wrapper có sẵn trong dự án.
3. Dùng IDE hỗ trợ Java 21, Maven/Gradle và chạy/debug ứng dụng Java.
4. Kiểm tra `java -version`, `javac -version`, `mvn -version`; ba lệnh cần trỏ đến phiên bản mong muốn. Nếu IDE biên dịch bằng JDK 21 nhưng terminal chạy JRE/JDK cũ, lỗi vẫn xảy ra.
5. Nắm khái niệm **dependency**, **transitive dependency**, **classpath**, artifact JAR, và cách một dependency management/BOM giữ các thư viện tương thích nhau.

Ví dụ kiểm tra môi trường:

```bash
java -version
javac -version
mvn -version
```

Các lệnh in thông tin phiên bản phụ thuộc máy, không có một đầu ra cố định. Trong dự án thực tế, chọn bản vá phù hợp thuộc nhánh được yêu cầu và theo chính sách bảo trì của dự án; ví dụ thực hành phía dưới ghim `3.3.13` để bảo đảm có thể tái tạo.

## 3. Nền tảng Java cần biết trước khi viết Spring

### 3.1. Cú pháp, kiểu dữ liệu và hướng đối tượng

- Phân biệt **primitive** (`int`, `boolean`, `long`...) và **reference**; hiểu `null`, boxing/unboxing và nguy cơ `NullPointerException`.
- Phân biệt **class**, **interface**, **abstract class**, kế thừa và composition. Trong thiết kế ứng dụng, thường ưu tiên composition và phụ thuộc vào interface khi cần nhiều cách triển khai.
- Hiểu phạm vi truy cập `private`/`protected`/`public`, constructor, `final`, `static`; tránh xem `static` như nơi chứa trạng thái dùng chung cho toàn ứng dụng.
- Biết **method overload** khác **override**, cách `equals`/`hashCode` hoạt động khi dùng đối tượng làm khóa bản đồ, và vì sao trạng thái mutable làm kiểm thử/đa luồng khó hơn.
- Biết các ngoại lệ **checked** và **unchecked**, cách truyền nguyên nhân khi ném lại ngoại lệ, và đóng tài nguyên với `try-with-resources`.

### 3.2. Collections, generics, lambda và Stream

- `List` giữ thứ tự và cho phép phần tử trùng; `Set` biểu diễn tập phần tử không trùng; `Map` ánh xạ khóa–giá trị. Cần nắm thao tác cơ bản và ý nghĩa của `equals`/`hashCode`.
- **Generics** giúp kiểm tra kiểu lúc biên dịch: `List<String>` khác `List<Object>`. Với wildcard, quy tắc nhớ nhanh là “producer extends, consumer super” khi phù hợp.
- **Lambda/method reference** là cách truyền hành vi dưới dạng functional interface; phân biệt biến được capture với trường dữ liệu mutable.
- Một `Stream` thường có nguồn, các thao tác trung gian (`filter`, `map`) và thao tác kết thúc (`toList`, `collect`). Stream **không tự thay thế** dữ liệu nguồn; không dựa vào thứ tự tùy ý của `HashMap`/`HashSet`.

### 3.3. Những tính năng Java 21 đáng nhận diện

- **Record** biểu diễn kiểu dữ liệu mang giá trị, tự sinh accessor, `equals`, `hashCode`, `toString`; trạng thái record là **shallowly immutable**, không biến một `List` mutable bên trong thành immutable.
- **Pattern matching for `switch`** và `switch` expression hỗ trợ xử lý theo kiểu; trong Java 21, tính năng này đã chính thức, không cần cờ preview.
- **Sealed class/interface** cho phép giới hạn tập lớp triển khai trực tiếp theo quy tắc khai báo.
- **Virtual threads** (chính thức trong Java 21) hữu ích khi có nhiều tác vụ chủ yếu **chờ I/O**. Chúng không tự tăng tốc CPU, không loại bỏ giới hạn connection pool và vẫn cần kiểm soát tài nguyên.
- `var` chỉ suy luận **kiểu biến cục bộ lúc biên dịch**; Java vẫn là ngôn ngữ kiểu tĩnh.

Một chương trình Java 21 độc lập, không cần thư viện Spring:

**Tệp `Java21Check.java`**

```java
import java.util.List;

record Candidate(String name, int score) {}

public class Java21Check {
    static String describe(Object value) {
        return switch (value) {
            case Integer n when n >= 0 -> "nonnegative: " + n;
            case Integer n -> "negative: " + n;
            case String s -> "text: " + s;
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Candidate candidate = new Candidate("Lan", 9);
        List<String> names = List.of("An", "Lan", "Binh").stream()
                .filter(name -> name.length() <= 3)
                .map(String::toUpperCase)
                .toList();

        System.out.println(candidate.name() + ":" + candidate.score());
        System.out.println(describe(21));
        System.out.println(names);
    }
}
```

Biên dịch/chạy với JDK 21:

```bash
javac Java21Check.java
java Java21Check
```

Đầu ra chuẩn:

```text
Lan:9
nonnegative: 21
[AN, LAN]
```

Chương trình minh họa record, collection/Stream và pattern matching for switch. `filter` giữ `An` và `Lan` vì độ dài không quá 3; `Binh` có 4 ký tự nên bị loại. `toList()` tạo danh sách kết quả, không biến đổi `List.of(...)` ban đầu.

### 3.4. JVM và runtime ở mức cần thiết

Hiểu đường đi **`.java -> javac -> .class (bytecode) -> JVM`**. JVM dùng class loader nạp lớp, thực thi bytecode (thông dịch/JIT), cấp phát heap, sử dụng stack cho frame của lời gọi và thu gom rác khi thích hợp. `OutOfMemoryError`, lỗi nạp lớp và deadlock khác lỗi cú pháp; cần biết đọc stack trace từ **nguyên nhân gốc**.

Phân biệt **process** với **thread**; nhận diện vấn đề dùng chung trạng thái mutable, race condition, blocking I/O và timeout. Ứng dụng web có thể xử lý nhiều request đồng thời, nên bean singleton không nên chứa dữ liệu request trong field có thể thay đổi.

## 4. IoC và Dependency Injection: nền móng của Spring

### 4.1. IoC là gì?

**Inversion of Control (IoC)** nghĩa là quyền tổ chức việc tạo, kết nối và quản lý đối tượng được giao cho một thành phần điều phối — trong Spring là **IoC container** (thường là `ApplicationContext`). Thay vì controller tự khởi tạo mọi phụ thuộc bằng `new`, container cung cấp đối tượng đã được cấu hình.

**Dependency Injection (DI)** là một kỹ thuật hiện thực IoC: phụ thuộc được **truyền vào** đối tượng cần dùng. DI không đồng nghĩa hoàn toàn với IoC; Spring còn quản lý vòng đời, phạm vi, cấu hình bean và nhiều dịch vụ khác.

Hình dung một chuỗi phụ thuộc:

```text
HTTP request
    |
    v
GreetingController --constructor injection--> GreetingService
                               ^
                               |
                     Spring ApplicationContext
                     tạo và cung cấp các bean
```

Nếu `GreetingController` tự gọi `new GreetingService()`, controller gắn chặt vào cách khởi tạo service. Nếu nhận service qua constructor, ta có thể thay bằng implementation khác hoặc fake trong kiểm thử mà không đổi logic của controller.

### 4.2. Bean, container và các cách đăng ký

**Bean** là đối tượng được container Spring quản lý. Những cách đăng ký phổ biến:

- `@Component` cho một thành phần Spring chung; `@Service`, `@Repository` và `@Controller` là stereotype theo vai trò, có thể được component scan tìm thấy.
- `@RestController` kết hợp controller với việc ghi kết quả trực tiếp vào HTTP response body.
- `@Configuration` cùng phương thức `@Bean` hữu ích khi cần tạo đối tượng từ thư viện ngoài hoặc muốn kiểm soát cách khởi tạo.
- `@Import`, các cấu hình điều kiện và cơ chế tự cấu hình có thể bổ sung bean; **chỉ có annotation trên một class chưa đảm bảo class đó được quét hoặc import**.

Ví dụ khai báo bean cho lớp thư viện chuẩn (đặt trong package được quét):

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Ở đây `Clock` là bean do phương thức `clock()` cung cấp; các bean khác có thể nhận `Clock` qua constructor. Ví dụ trên là **một lớp bổ sung cho dự án Spring**, không phải chương trình `javac` độc lập vì cần thư viện Spring.

### 4.3. Constructor injection và xử lý nhiều implementation

Ưu tiên **constructor injection** cho phụ thuộc bắt buộc:

```java
@Service
class BillingService {
    private final PaymentGateway gateway;

    BillingService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Đoạn trên chỉ minh họa mẫu thiết kế; `PaymentGateway` và import `@Service` phải tồn tại trong dự án thật. Với class chỉ có **một constructor**, Spring không yêu cầu gắn `@Autowired` trên constructor đó.

Nếu container tìm được **nhiều bean cùng kiểu**, cần xác định đúng bean bằng `@Qualifier`, `@Primary` hoặc thiết kế lại điểm mở rộng. Nếu không có bean phù hợp, khởi tạo context có thể thất bại. Một dependency bắt buộc không nên được “sửa lỗi” bằng cách tự `new` trong controller, vì sẽ bỏ qua quản lý và cấu hình của container.

**Vòng đời và scope:** thông thường bean có scope `singleton` — **một instance cho mỗi Spring container**, không có nghĩa một instance duy nhất toàn JVM. `prototype` tạo instance theo lần yêu cầu; trong ứng dụng web có thêm scope như `request`. Container xử lý khởi tạo, tiêm phụ thuộc, callback như `@PostConstruct` và `@PreDestroy` với bean phù hợp (trên Spring 6 dùng `jakarta.annotation.*`). Không nên giữ trạng thái request trong singleton mutable.

**Lưu ý nâng cao cần nhận diện:** dependency vòng tròn làm khởi tạo khó khăn; các tính năng dựa trên proxy như `@Transactional` có giới hạn khi gọi nội bộ cùng bean. Chỉ cần biết đây là cơ chế của container, chưa cần triển khai sâu ở bài chuẩn bị.

## 5. Spring Boot 3.3 bổ sung điều gì?

### 5.1. Spring Framework khác Spring Boot

Spring Framework cung cấp IoC/DI và các module như Spring MVC, transaction, data access. Spring Boot giúp **thiết lập và vận hành** ứng dụng Spring nhanh hơn bằng:

- **Starter dependencies**: nhóm thư viện theo nhu cầu, ví dụ `spring-boot-starter-web` hoặc `spring-boot-starter-test`.
- **Auto-configuration**: cấu hình bean theo thư viện trên classpath, thuộc tính và các điều kiện hiện có; thường nhường chỗ cho bean do ứng dụng tự cấu hình khi điều kiện tương ứng được đáp ứng.
- **`SpringApplication`**: bootstrap `ApplicationContext`, chuẩn bị environment và chạy ứng dụng.
- **Máy chủ nhúng** khi dùng web starter thích hợp; đóng gói JAR có thể khởi động bằng `java -jar`.
- **Externalized configuration** qua `application.properties` / `application.yml`, environment variables, command-line arguments và các nguồn cấu hình được hỗ trợ.

`@SpringBootApplication` kết hợp ba cơ chế: `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Component scan mặc định bắt đầu từ **package chứa lớp ứng dụng** và các package con. Vì vậy, đặt lớp main tại package gốc của ứng dụng giúp Spring tìm thấy controller/service/configuration.

### 5.2. Luồng khởi động ở mức khái niệm

```text
main()
  -> SpringApplication.run(...)
  -> Chuẩn bị Environment / cấu hình / profile
  -> Tạo ApplicationContext, đăng ký cấu hình và bean definitions
  -> Component scan + auto-configuration theo điều kiện
  -> Khởi tạo, kết nối các bean và chạy lifecycle phù hợp
  -> Nếu là web app: khởi chạy embedded web server
  -> Ứng dụng sẵn sàng nhận request
```

Đây là **sơ đồ khái niệm**, không phải danh sách callback nội bộ theo thứ tự tuyệt đối. Khi gửi HTTP request tới ứng dụng MVC, web server chuyển request vào chuỗi xử lý của Spring MVC (bao gồm `DispatcherServlet`), tìm handler phù hợp, gọi controller/service và ghi response.

### 5.3. Cấu hình và profiles

Một cấu hình đơn giản:

**Tệp `src/main/resources/application.yml`**

```yaml
spring:
  application:
    name: java21-ioc-boot33
server:
  port: 8080
```

Cấu hình file giúp xác định mặc định; giá trị có thể được **ghi đè** bằng nguồn có độ ưu tiên cao hơn, chẳng hạn command-line arguments. Ví dụ chạy với cổng khác: `java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=8081`. `spring.profiles.active` chọn môi trường cấu hình tương ứng, nhưng profile không phải cơ chế quản lý mật khẩu. Với nhiều thuộc tính liên quan, ưu tiên cấu hình có kiểu qua `@ConfigurationProperties` và validation phù hợp thay vì rải `@Value` khắp code. Đừng commit thông tin bí mật vào repository.

## 6. Thực hành hoàn chỉnh: Java 21 + Spring Boot 3.3 + DI

Ví dụ này không dùng database, đủ để quan sát container tạo service và tự tiêm vào controller. Tạo dự án Maven với cấu trúc:

```text
demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── GreetingService.java
    │   │   └── GreetingController.java
    │   └── resources/application.yml
    └── test/java/com/example/demo/
        └── GreetingServiceTest.java
```

**Tệp `pom.xml`**

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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Parent của Spring Boot quản lý các phiên bản dependency/plugin phổ biến; không cần tự thêm phiên bản cho hai starter trong ví dụ. Spring Boot 3.3.13 thuộc nhánh 3.3 và tương thích JDK 21. Nếu dự án đã có BOM hoặc parent riêng, phải tuân thủ cơ chế quản lý phiên bản hiện hữu.

**Tệp `src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**Tệp `src/main/java/com/example/demo/GreetingService.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

**Tệp `src/main/java/com/example/demo/GreetingController.java`**

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public String greet(@RequestParam(name = "name", defaultValue = "Java 21") String name) {
        return service.greet(name);
    }
}
```

**Tệp `src/main/resources/application.yml`** dùng nội dung ở mục 5.3.

Giải thích cơ chế: `@SpringBootApplication` quét package `com.example.demo`; `@Service` đăng ký `GreetingService`; `@RestController` đăng ký `GreetingController`; container nhìn thấy constructor `GreetingController(GreetingService)` rồi cung cấp service đang quản lý. `@GetMapping` định tuyến GET `/greet`; `@RequestParam` đọc query parameter `name`, mặc định là `Java 21` nếu thiếu. String được trả về trực tiếp làm response body. Không cần tạo controller/service bằng `new` trong `main()`.

Chạy trong thư mục `demo`:

```bash
mvn test
mvn spring-boot:run
```

Khi ứng dụng đang chạy, mở terminal khác:

```bash
curl -s "http://localhost:8080/greet?name=Lan"
```

Nội dung HTTP response body:

```text
Xin chào, Lan!
```

Nếu gọi `http://localhost:8080/greet` không truyền `name`, nội dung trả về là `Xin chào, Java 21!`. Không coi toàn bộ console log khi start là đầu ra cố định, vì thời gian khởi động, PID và các dòng log thay đổi.

Đóng gói và chạy JAR:

```bash
mvn package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

Nếu cổng `8080` đang dùng, dừng process hiện hữu hoặc đổi `server.port`. Lệnh `mvn test` ở trên sẽ chạy test sau khi thêm tệp kiểm thử dưới đây.

**Tệp `src/test/java/com/example/demo/GreetingServiceTest.java`**

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void greetsByName() {
        GreetingService service = new GreetingService();
        assertEquals("Xin chào, Lan!", service.greet("Lan"));
    }
}
```

Test này là **unit test** của logic service: tự tạo service hợp lệ vì không cần kiểm tra container; nó không chứng minh component scan hay HTTP mapping hoạt động. Để kiểm tra wiring/HTTP, có thể học thêm `@SpringBootTest` hoặc slice test như `@WebMvcTest` ở bài testing chuyên sâu. Nên phân biệt unit test với integration test thay vì luôn khởi động cả Spring context.

## 7. Nhận diện và xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Java runtime cũ hơn phiên bản bytecode đã biên dịch | Kiểm tra `java -version`, JDK của IDE/terminal và target build |
| `NoSuchBeanDefinitionException` hoặc thiếu bean lúc startup | Class chưa được scan/import, không có bean đúng kiểu hoặc điều kiện cấu hình không thỏa | Kiểm tra package, stereotype, `@Bean`, dependency và điều kiện |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng kiểu để inject | Xác định bằng `@Qualifier`/`@Primary` hoặc sửa thiết kế |
| `BeanCreationException`/circular reference | Constructor hoặc cấu hình bean tạo dependency vòng hoặc lỗi khi khởi tạo | Đọc nguyên nhân gốc, tách trách nhiệm, phá vòng phụ thuộc |
| Port `8080` already in use | Process khác giữ cổng | Dừng process hoặc thay cổng |
| HTTP 404 khi gọi `/greet` | URL/sai cổng, controller không được quét, sai mapping | Kiểm tra endpoint, package main class, log mapping |
| Lỗi import `javax.servlet.*` với Spring Boot 3 | Dùng API/thư viện Java EE cũ không phù hợp Jakarta | Dùng `jakarta.servlet.*` và dependency tương thích Boot 3 |
| Conflict phụ thuộc hoặc `NoSuchMethodError` | Trộn phiên bản thư viện ngoài BOM/parent | Kiểm tra dependency tree, bỏ override không cần thiết |
| Thay đổi field singleton gây kết quả lẫn giữa request | Chia sẻ trạng thái mutable không đồng bộ | Để service stateless, truyền dữ liệu qua tham số/request scope phù hợp |

Khi gặp lỗi, đọc **exception đầu tiên mang ý nghĩa nguyên nhân gốc** (`Caused by`), kiểm tra thay đổi gần nhất, dependency tree, profile và biến môi trường. Đừng vội thêm annotation hoặc dependency ngẫu nhiên cho đến khi hiểu vì sao container đang thiếu/nhân đôi bean.

## 8. Tự kiểm tra trước khi chuyển sang Application Runtime

Hãy tự trả lời và thực hiện được các yêu cầu:

1. Giải thích Java 21 là **JDK/runtime ngôn ngữ**, Spring là **framework**, Boot là **lớp hỗ trợ cấu hình/khởi động**. Vì sao Spring Boot 3.3 không bắt buộc Java 21 mà yêu cầu tối thiểu Java 17?
2. Viết record và một `switch` expression có pattern matching; giải thích điểm khác nhau giữa record shallow immutable và deep immutable.
3. Biết vì sao `List<String>` không phải `List<Object>`, khi nào dùng `Map`/`Set`, và vì sao service singleton cần tránh trạng thái request mutable.
4. Mô tả IoC, DI và bean bằng ví dụ `GreetingController -> GreetingService`. Nếu có hai `GreetingService` implementation phù hợp cùng kiểu, container quyết định thế nào?
5. Giải thích tác dụng của `@SpringBootApplication`, `@Service`, `@RestController`, `@Bean`, `@GetMapping` và constructor injection.
6. Đoán điều gì xảy ra khi di chuyển `GreetingService` ra ngoài package được component scan; biết cách sửa cấu trúc package hoặc đăng ký cấu hình phù hợp.
7. Chạy `mvn test`, `mvn spring-boot:run`, gọi `/greet` bằng `curl` và chạy JAR đã đóng gói.
8. Thử thay cổng qua command-line argument, đọc stack trace khi app không khởi động, biết nơi kiểm tra dependency/Java version.

**Thứ tự học hiệu quả:** Java core + collection/exception → Java 21 (record, switch, concurrency cơ bản) → interface/composition → IoC và DI → Spring bean/context → Spring Boot starters, auto-configuration, externalized config → khởi động, request flow và kiểm thử. Sau khi hoàn thành, có thể tiếp tục các chủ đề sâu hơn như lifecycle events, configuration binding, Actuator, graceful shutdown, thread pools và quan sát ứng dụng.

## 9. Tài liệu tham khảo chính thức

- Java SE 21 Documentation: https://docs.oracle.com/en/java/javase/21/
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 — Developing Your First Application: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Framework Reference (IoC container): https://docs.spring.io/spring-framework/reference/core/beans.html
