# Phân biệt Spring Framework với Spring Boot

## 1. Bản chất: Spring Boot được xây trên Spring Framework

**Spring Framework** là framework cung cấp nền tảng phát triển ứng dụng Java: IoC container, **Dependency Injection (DI)**, quản lý bean, tài nguyên, sự kiện, AOP, transaction, truy cập dữ liệu, lập trình web và nhiều module chuyên biệt. **Spring Boot** là dự án xây **trên Spring Framework**, giúp tạo, cấu hình, đóng gói và vận hành ứng dụng Spring dễ hơn nhờ *auto-configuration*, *starters*, quản lý bộ dependency tương thích và các công cụ khởi động.

Câu ghi nhớ: **Framework cung cấp các khả năng nền; Boot giúp lắp và khởi động ứng dụng dùng các khả năng đó theo convention.** Spring Boot **không thay thế** IoC container bằng một loại container riêng; bean vẫn đi qua các khái niệm Spring như `ApplicationContext`, `BeanDefinition`, `@Bean`, `@Component` và constructor injection.

Không nên nhầm ba điều:
- Một dự án có Spring Framework **không nhất thiết** dùng Spring Boot: ứng dụng console có thể tự tạo `AnnotationConfigApplicationContext` và quản lý vòng đời context.
- Một dự án dùng Spring Boot **vẫn dùng Spring Framework** bên dưới; các API `@Configuration`, `@Bean`, `@Component`, `@Autowired` và `ApplicationContext` tiếp tục hoạt động theo quy tắc Framework.
- **Spring Boot không đồng nghĩa ứng dụng web**. Với starter nền không chứa thư viện Servlet/WebFlux, Boot có thể chạy một chương trình console hoặc tác vụ batch, hoàn toàn không mở cổng HTTP.

### So sánh trực diện

| Câu hỏi | Spring Framework (dùng trực tiếp) | Spring Boot |
| --- | --- | --- |
| Là gì? | Framework nhiều module: container, DI, web, transaction... | Dự án/tooling **xây trên Framework** để bootstrap và cấu hình thuận tiện |
| Ai quản lý bean? | IoC container Spring (`ApplicationContext`/`BeanFactory`) | **Cũng chính IoC container Spring** |
| Điểm bắt đầu thông dụng | Tạo `ApplicationContext` từ cấu hình Java/XML/programmatic | `SpringApplication.run(...)` thường đi cùng `@SpringBootApplication` |
| Khai báo cấu hình | `@Configuration`, `@Bean`, `@ComponentScan`, XML... | Sử dụng lại các cơ chế ấy; bổ sung auto-configuration, starters và property conventions |
| Dependency versions | Dự án tự chọn/đồng bộ hoặc dùng BOM phù hợp | Boot cung cấp BOM/parent quản lý tập phiên bản đã được phối hợp |
| Server HTTP | Có khi thêm module web + bootstrap server thích hợp | **Chỉ xuất hiện khi** có stack web và điều kiện/config thích hợp |
| Packaging | JAR/WAR tùy cách cấu hình build | Có plugin để đóng gói executable JAR/WAR và chạy thuận tiện |
| Có dùng không cần web? | Có | Có |
| Ưu tiên khi nào? | Học rõ IoC/DI, kiểm soát hạ tầng tối thiểu hoặc thư viện độc lập | Phần lớn ứng dụng cần startup/dependency/config có convention, web hoặc batch |

Bảng mô tả **mặc định và cách sử dụng phổ biến**, không phải hai bộ API hoàn toàn tách biệt. Spring Framework cũng có thể dùng BOM hoặc công cụ build hiện đại; Spring Boot cũng cho phép tùy chỉnh mọi thành phần khi cần.

## 2. Core Container nằm ở đâu trong hai mô hình?

Trong hai cách khởi tạo, **Core Container là một**:

~~~text
              NGHIỆP VỤ CỦA ỨNG DỤNG
     Service ----> Repository ----> Data source
                        ^
                        | dependency injection
                        |
           Spring ApplicationContext
            / BeanFactory / Bean graph
                 (Core Container)
                        ^
            +-----------+-----------+
            |                       |
   Dùng Framework trực tiếp       Dùng Spring Boot
   Tạo/configure context          SpringApplication.run(...)
   bằng code/XML                  + auto-configuration
            |                       |
            +--------- JVM ---------+
~~~

**Framework trực tiếp:** bạn thường chủ động khởi tạo `AnnotationConfigApplicationContext`, chỉ định `@Configuration` hoặc `@ComponentScan`, đăng ký cấu hình liên quan và đóng context khi xong.

**Boot:** `SpringApplication.run` tạo/chuẩn bị context phù hợp với loại ứng dụng, đăng ký nguồn cấu hình của bạn, áp dụng các điều kiện auto-configuration và thực hiện quá trình khởi động context. Các bean của bạn vẫn được tạo/inject qua Framework. Đoạn code kinh doanh như `GreetingService` không bắt buộc import class của Spring Boot.

Cụ thể:

- **`spring-core`, `spring-beans`, `spring-context`, `spring-expression`** là những module nền Framework. API `ApplicationContext` thuộc Spring Framework, **không** phải class độc quyền của Boot.
- **`spring-boot`, `spring-boot-autoconfigure`, các `spring-boot-starter-...`** thêm bootstrap, điều kiện cấu hình, conventions và tập phụ thuộc thuận tiện.
- Với ứng dụng Boot có Spring MVC, Boot có thể cấu hình web server/DispatcherServlet/controller theo các điều kiện. Nhưng DispatcherServlet là thành phần của **Spring MVC**; Boot giúp thiết lập nó khi stack và cấu hình cho phép.

**Không áp dụng câu “Framework phải cấu hình tất cả bằng XML; Boot mới dùng annotation”.** Cấu hình Java `@Configuration`/`@Bean` đã là một phần của Framework; Boot kế thừa thay vì phát minh lại chúng.

## 3. `@SpringBootApplication`: tiện ích nào được bật?

Một class khởi động Boot thường viết:

~~~java
// Đoạn minh họa, cần dependency Spring Boot phù hợp.
@SpringBootApplication
public class App {
    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
~~~

`@SpringBootApplication` kết hợp ba nhóm ý nghĩa:

1. **`@SpringBootConfiguration`**: class là nguồn cấu hình Spring; annotation này là biến thể chuyên cho Boot của `@Configuration`.
2. **`@EnableAutoConfiguration`**: cho phép Boot cân nhắc cấu hình tự động dựa vào môi trường, classpath, properties, các bean đã khai báo và điều kiện liên quan.
3. **`@ComponentScan`**: quét thành phần trong package của class cấu hình và các package con theo quy tắc mặc định. Vì vậy nên đặt main class tại một **root package** bao trùm phần code ứng dụng.

**Không phải** `@SpringBootApplication` = `@Component` đơn thuần; nó còn kích hoạt auto-configuration và cơ chế nguồn cấu hình của Boot. Ngược lại, Framework thuần vẫn có `@ComponentScan` nếu bạn khai báo rõ ràng; không cần dùng Boot để quét bean.

`SpringApplication.run(...)` trả về một `ConfigurableApplicationContext` (context Spring thực) để ứng dụng có thể dùng/đóng khi cần. Với ứng dụng web, thời gian sống context thường gắn với server; với batch/console, nên thiết kế đường kết thúc và lifecycle tài nguyên rõ ràng.

## 4. Auto-configuration hoạt động ra sao và *không* hoạt động ra sao?

Auto-configuration là cơ chế **đưa vào các bean/configuration mặc định có điều kiện**, không phải hệ thống tự động đoán toàn bộ nghiệp vụ. Các cấu hình có thể phụ thuộc vào:

- **Classpath**: có module/driver/web stack cụ thể không?
- **Bean đang tồn tại**: một cấu hình mặc định có thể không tạo bean khi ứng dụng đã cung cấp bean cùng trách nhiệm/kiểu và thỏa điều kiện tương ứng.
- **Configuration properties**: ví dụ một tính năng được bật/tắt hoặc có địa chỉ kết nối thích hợp.
- **Môi trường/loại ứng dụng**: console, Servlet web hoặc reactive web, profile...
- **Điều kiện Boot định nghĩa cho từng cấu hình**: không có một quy tắc chung rằng “cứ có JAR là mọi bean đều được tạo”.

Các annotation điều kiện như `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` thường xuất hiện trong các auto-configuration. Đây **không phải** lời hứa rằng mọi tính năng Boot đều dùng cả ba điều kiện ấy.

### Ví dụ dễ hiểu

Nếu đưa vào một **web starter** và không vô hiệu hóa web stack, Boot có thể tự cấu hình những thành phần HTTP thích hợp. Nếu chỉ dùng `spring-boot-starter` không có stack Servlet/reactive, Boot chạy như chương trình non-web mà không tự dựng Tomcat.

Nếu ứng dụng định nghĩa một bean cụ thể, một số auto-configurations có thể **back off** (nhường cho bean của bạn) theo điều kiện; một số khác vẫn tồn tại. Cần kiểm tra **conditions evaluation report** hoặc tài liệu của cấu hình đó, không suy đoán từ tên `@Bean`.

Dùng `--debug` khi khởi động Boot để xem thêm thông tin đánh giá điều kiện nếu cấu hình logging cho phép. Report giúp biết **vì sao** một auto-configuration được/không được áp dụng; nó không trực tiếp cho biết service nghiệp vụ đúng hay sai.

## 5. Starter, BOM, plugin và Spring Initializr: từng thứ làm gì?

| Thành phần Boot | Tác dụng thực tế | Không phải |
| --- | --- | --- |
| **Starter** (`spring-boot-starter`, starter web/data...) | Gom dependency thường dùng cho một khả năng | Một framework IoC thứ hai |
| **BOM/managed dependencies** | Quản lý phiên bản của nhiều thư viện tương thích | Tự động bật mọi feature trong dependency |
| **`spring-boot-starter-parent`** (Maven) | Parent build + dependency/plugin conventions | Điều kiện bắt buộc nếu dùng Boot với Gradle hoặc Maven khác |
| **Boot Maven/Gradle plugin** | Chạy/package executable app, build integration | Thay thế `javac` hay JVM |
| **Spring Initializr** (`start.spring.io`) | Công cụ khởi tạo project với metadata, build và dependency đã chọn | Nơi chạy IoC container ở runtime |
| **Externalized configuration** | Truyền tham số qua properties/YAML, environment, command line theo cơ chế Boot | Miễn trừ việc kiểm tra hợp lệ các giá trị cấu hình |

**Starters không phải auto-configuration.** Starter chủ yếu là tập dependency; auto-configuration là **logic có điều kiện** hoạt động khi Boot bootstrap. Cả hai thường đi cùng nhau nên dễ bị hiểu là cùng một thứ.

**Không tự ép phiên bản Spring Framework** trong ứng dụng Boot khi chưa có lý do kiểm soát rõ: BOM Boot thường đã ghép các phiên bản phù hợp. Override tùy tiện `spring-context` có thể làm lệch binary/API compatibility giữa các module.

Khi chuyển dự án giữa Spring Boot **3.x (nền Framework 6.x)** và **4.x (nền Framework 7.x)**, phải đọc migration guides và thay đổi hệ Jakarta/Servlet/testing/library. Cả hai thế hệ hỗ trợ **Java 17+**, nhưng không có nghĩa tất cả dependency/feature cũ đều tương thích ngay.

## 6. Ví dụ 1 — Spring Framework trực tiếp, không có Boot

Ví dụ này tạo `ApplicationContext` **thủ công**, khai báo hai bean và in kết quả. Không cần Spring Boot hay web server.

### 6.1. Cấu trúc dự án

~~~text
framework-console/
├── pom.xml
└── src/main/java/demo/FrameworkConsoleApp.java
~~~

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>framework-console</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FrameworkConsoleApp</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ khóa phiên bản **Spring Framework 7.0.9** và release 17 để dễ đối chiếu. Trong dự án thật, cần dùng phiên bản còn được bảo trì phù hợp và xem tài liệu migration khi cập nhật.

### 6.3. `src/main/java/demo/FrameworkConsoleApp.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FrameworkConsoleApp {
    private FrameworkConsoleApp() {
    }

    static final class PrefixSource {
        private final String prefix;

        PrefixSource(String prefix) {
            this.prefix = prefix;
        }

        String value() {
            return prefix;
        }
    }

    static final class GreetingService {
        private final PrefixSource source;

        GreetingService(PrefixSource source) {
            this.source = source;
        }

        String greet(String name) {
            return source.value() + ", " + name + "!";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        PrefixSource prefixSource() {
            return new PrefixSource("Xin chao");
        }

        @Bean
        GreetingService greetingService(PrefixSource source) {
            return new GreetingService(source);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            GreetingService service = context.getBean(GreetingService.class);
            System.out.println("framework.message=" + service.greet("Lan"));
            System.out.println("framework.singleton="
                    + (service == context.getBean(GreetingService.class)));
        }
    }
}
~~~

### 6.4. Build, chạy và output

Từ thư mục `framework-console` có `pom.xml`, yêu cầu JDK 17+ và Maven 3.9+:

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

**Hai dòng stdout do code ứng dụng in** (không tính output của hai lệnh kiểm tra môi trường, log/diagnostic từ build hoặc logging backend):

~~~text
framework.message=Xin chao, Lan!
framework.singleton=true
~~~

`AnnotationConfigApplicationContext(Config.class)` tạo context và đọc `Config`. Factory method `greetingService(PrefixSource source)` nhận bean `PrefixSource` do container resolve, rồi tạo `GreetingService`. Scope mặc định là singleton, nên hai lần `getBean` của cùng definition trả reference giống nhau. Không có `SpringApplication`, `@SpringBootApplication`, Boot starter hoặc auto-configuration ở chương trình này.

Nếu gọi `javac FrameworkConsoleApp.java` trần mà không đưa các JAR Spring vào classpath, compiler sẽ báo thiếu package. Maven quản lý **transitive classpath** và gọi compiler trong lệnh trên.

## 7. Ví dụ 2 — Spring Boot dùng lại Core Container, vẫn là console

Ví dụ thứ hai thực hiện **cùng chức năng** nhưng để Spring Boot bootstrap context. Không thêm web starter: ứng dụng là console app, **không khởi động HTTP server**.

### 7.1. Cấu trúc dự án

~~~text
boot-console/
├── pom.xml
└── src/main/
    ├── java/demo/BootConsoleApp.java
    └── resources/application.properties
~~~

### 7.2. `pom.xml` và dependency quản lý bởi Boot

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.1</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>boot-console</artifactId>
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
~~~

Parent **Boot 4.1.1** cung cấp dependency management, nên không cần ghi version riêng cho `spring-boot-starter` hay `spring-context`. Boot 4.x tương ứng với thế hệ Spring Framework 7.x; ví dụ này giữ JDK 17 làm mức biên dịch. Không kết hợp `spring-boot-starter-parent 4.1.1` với `spring-context` 6.x bị khóa riêng.

### 7.3. `src/main/java/demo/BootConsoleApp.java`

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class BootConsoleApp {

    static final class PrefixSource {
        private final String prefix;

        PrefixSource(String prefix) {
            this.prefix = prefix;
        }

        String value() {
            return prefix;
        }
    }

    static final class GreetingService {
        private final PrefixSource source;

        GreetingService(PrefixSource source) {
            this.source = source;
        }

        String greet(String name) {
            return source.value() + ", " + name + "!";
        }
    }

    @Bean
    PrefixSource prefixSource() {
        return new PrefixSource("Xin chao");
    }

    @Bean
    GreetingService greetingService(PrefixSource source) {
        return new GreetingService(source);
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(BootConsoleApp.class, args)) {
            GreetingService service = context.getBean(GreetingService.class);
            System.out.println("boot.message=" + service.greet("Lan"));
            System.out.println("boot.singleton="
                    + (service == context.getBean(GreetingService.class)));
        }
    }
}
~~~

Các bean vẫn được định nghĩa bằng `@Bean` và nhận dependency qua tham số giống Framework trực tiếp. Sự khác biệt quan trọng là **cách bootstrap/cấu hình**: `SpringApplication.run` tạo context theo Boot, áp dụng các auto-configurations đủ điều kiện, đọc cấu hình ngoài và quản lý các bước startup. `@SpringBootApplication(proxyBeanMethods = false)` không yêu cầu các factory method tự gọi nhau; Spring sẽ inject qua tham số khi tạo bean.

### 7.4. `src/main/resources/application.properties` và chạy

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

Hai cấu hình này **chỉ giảm banner/log khi chạy ví dụ**, không quyết định việc ứng dụng có web server hay không. Không khai báo `spring-boot-starter-webmvc`, `spring-boot-starter-webflux` hay server stack nên ví dụ là non-web.

Trong thư mục `boot-console`:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

**Hai dòng do các lệnh `System.out.println` trong mã ứng dụng tạo ra** (không bao gồm Maven diagnostic, thông tin JVM hoặc log mà môi trường có thể thêm):

~~~text
boot.message=Xin chao, Lan!
boot.singleton=true
~~~

Có thể kiểm tra thêm packaging:

~~~bash
mvn -q package
java -jar target/boot-console-1.0.0.jar
~~~

Plugin của Boot tạo executable JAR với các dependency cần thiết; đây là **tiện ích build/package**, không thay đổi ý nghĩa `GreetingService` hay quy tắc singleton/DI của Framework.

**Lưu ý về startup:** class `BootConsoleApp` nằm tại package `demo`; nếu bổ sung `@Component` vào `demo.service.MyService`, mặc định component scan bao gồm package con đó. Nếu đặt bean ở package bên ngoài `demo`, cần đăng ký/scan rõ. Trong ví dụ, hai bean được khai báo bằng `@Bean` ngay trên cấu hình khởi động nên không cần tạo class `@Component` riêng.

## 8. So sánh đầu ra và phân tích nguyên nhân

| Quan sát | Framework thuần | Spring Boot |
| --- | --- | --- |
| Entry point | `main` dùng `new AnnotationConfigApplicationContext(...)` | `main` dùng `SpringApplication.run(...)` |
| Đăng ký bean | `@Configuration` + `@Bean` | `@SpringBootApplication` + `@Bean` |
| Dependency injection | Factory method nhận `PrefixSource` | **Cùng quy tắc** factory method nhận `PrefixSource` |
| Lấy bean | `context.getBean(GreetingService.class)` | **Cùng API** `context.getBean(GreetingService.class)` |
| Hai lần lấy bean | `framework.singleton=true` | `boot.singleton=true` |
| Lời chào | `framework.message=Xin chao, Lan!` | `boot.message=Xin chao, Lan!` |
| Tự động cấu hình | Không có cơ chế Boot tự động trong ví dụ | Boot có cơ chế, áp dụng những điều kiện thực sự khớp |
| HTTP server | Không | Không |
| Build/run | Exec Maven Plugin | Boot Maven Plugin, executable JAR |

Ở **cả hai ví dụ**, service thuần Java không import API Spring. Việc có DI là do các factory methods; **khác nhau ở ai khởi tạo context và những tiện ích hạ tầng được thêm khi khởi động**.

Hai chương trình không nhằm chứng minh Boot “mạnh hơn” trong bài toán đơn giản này: ở một ứng dụng console nhỏ, Boot có thêm bootstrap/dependency/plugin và có thể là lựa chọn không cần thiết. Ở ứng dụng gồm web, database, configuration theo môi trường và nhiều integrations, Boot thường giúp giảm cấu hình thủ công và phối hợp phiên bản nhất quán.

## 9. Những hiểu nhầm cần tránh

1. **“Spring Framework và Spring Boot là hai framework DI khác nhau.”** Sai. Boot dùng lại IoC container của Framework.
2. **“Dùng Framework thì bắt buộc XML.”** Sai. `@Configuration`, `@Bean`, component scan và nhiều loại cấu hình đã có trong Framework.
3. **“Boot không cần hiểu Spring.”** Sai. Scope, bean lifecycle, wiring, proxy và transaction vẫn đòi hiểu cơ chế Framework để debug.
4. **“Auto-configuration tự viết service nghiệp vụ.”** Sai. Nó cấu hình **hạ tầng có điều kiện**, không suy ra business rules.
5. **“Có Boot là có REST API/Tomcat.”** Sai. Cần stack web và điều kiện khởi động phù hợp; console Boot không nhất thiết có server.
6. **“Starter là cùng thứ với auto-configuration.”** Sai. Starter gom dependency; auto-configuration là logic điều kiện được bật trong bootstrap Boot.
7. **“Boot thay thế Maven, javac hoặc JVM.”** Sai. Boot hỗ trợ build tool và đóng gói, còn chương trình vẫn được biên dịch/chạy trên công cụ và runtime Java.
8. **“Cứ thêm `@SpringBootApplication` là mọi class cùng project đều được scan.”** Sai. Mặc định scan từ package của main class xuống các package con; có thể tùy chỉnh.
9. **“Spring Boot không thể cấu hình thủ công.”** Sai. Bạn vẫn có thể tự định nghĩa `@Bean`, properties, exclude auto-configurations hoặc dùng cấu hình Framework khi cần.
10. **“Framework là phiên bản cũ, Boot là phiên bản mới thay thế.”** Sai. Đây là **hai dự án liên quan** với các release line riêng; Boot 4.x thường được xây trên Framework 7.x, không phải Framework bị ngừng tồn tại.

## 10. Khi nào chọn cách nào?

Chọn **Framework trực tiếp** khi mục tiêu là:
- Học sâu `ApplicationContext`, bean registration, DI/lifecycle, điều kiện tạo đối tượng, hoặc tự dựng container nhỏ.
- Viết thư viện/integration không cần áp toàn bộ conventions Boot lên bên dùng.
- Xây công cụ console nhỏ, dependency graph đơn giản, hoặc phải kiểm soát rõ ràng từng module và cách bootstrap.

Chọn **Boot** khi mục tiêu là:
- Tạo ứng dụng thực tế cần hệ web/data/messaging/observability mà không muốn tự phối hợp nhiều dependency/configuration.
- Cần conventions cho externalized configuration, profile, test/build/run/package và runtime operations.
- Làm việc nhóm, cần khởi tạo dự án và tái hiện cùng dependency versions nhanh hơn.
- Muốn dùng một starter + properties để khai thác khả năng của Framework và các thư viện tích hợp.

**Đây không phải lựa chọn loại trừ kỹ thuật tuyệt đối.** Một ứng dụng Boot có thể dùng phần lớn API Framework; một ứng dụng Framework không Boot vẫn có thể phát triển tốt và có nhiều chức năng nâng cao nếu được cấu hình đúng. Chọn theo chi phí phát triển, hạ tầng và nhu cầu, không theo khẩu hiệu.

### Nâng cấp và quản lý phiên bản

- Ví dụ khóa **Framework 7.0.9** và **Boot 4.1.1** để trình bày rõ cấu hình. Chúng không có nghĩa luôn là phiên bản khuyến nghị mới nhất ở mọi thời điểm.
- Boot 4.x cần Java 17+ và nền Framework 7.x, với các thay đổi Jakarta EE 11. Khi nâng từ Boot 3.x phải đọc migration guide; không sao chép cấu hình/web starter/plugin giữa hai thế hệ mà không kiểm tra.
- Theo bản vá được hỗ trợ và cảnh báo bảo mật của dự án khi dùng trong sản phẩm, kiểm tra dependency tree và build test sau khi nâng.

## 11. Bài tập tự kiểm tra

1. **Đổi implementation** `PrefixSource` thành trả về `"Hello"` trong mỗi ví dụ. Dự đoán hai dòng `message`; vì sao kết quả tương ứng thay đổi mà không phải sửa `GreetingService`?
2. **Thêm bean thứ hai cùng kiểu** `PrefixSource` với tên khác. Thử dự đoán lỗi ambiguity ở factory method `greetingService(PrefixSource source)`; tìm cách dùng `@Primary`, `@Qualifier` hoặc một hợp đồng chọn bean phù hợp.
3. **Tắt auto-configuration ở Boot** có chủ đích cho một thành phần hạ tầng (khi đã học feature ấy). Hãy kiểm tra điều kiện thực tế trước/sau, đừng khẳng định `@EnableAutoConfiguration` luôn tạo mọi bean.
4. **Biến Boot console thành web app** bằng starter web đúng thế hệ và một controller; xác định phần nào do Spring MVC cung cấp, phần nào Boot tự lắp ráp, và khi nào HTTP server mở cổng. Không coi việc thêm `@RestController` vào project không có web stack là đủ để nhận HTTP request.
5. **Bỏ parent Maven ở Boot** và chuyển sang import BOM/quản lý plugin minh bạch. Hãy chỉ ra phần nào vẫn cần khai báo để `spring-boot:run` và executable JAR hoạt động.
6. **So sánh test:** xây một `GreetingService` bằng `new` với fake `PrefixSource` (không Spring), rồi kiểm thử qua context. Khi nào test thuần Java nhanh/hữu ích hơn, khi nào cần test có container?
7. **Phân tích startup:** so sánh `new AnnotationConfigApplicationContext(...)` với `SpringApplication.run(...)` theo các bước nạp cấu hình, đăng ký bean, resolve DI và lifecycle, chỉ ra phần giống/khác.

### Checklist đã nắm bài

- [ ] Phát biểu đúng **Framework cung cấp gì**, **Boot bổ sung gì** và **mối quan hệ giữa chúng**.
- [ ] Giải thích vì sao cả hai dùng `ApplicationContext` và bean graph của Spring.
- [ ] Nhận diện tác dụng của ba phần trong `@SpringBootApplication`.
- [ ] Phân biệt starter, dependency management, auto-configuration, plugin và Initializr.
- [ ] Giải thích được vì sao ví dụ Boot chỉ có starter nền **không mở HTTP server**.
- [ ] Tự chạy được hai dự án Maven Java 17, dự đoán bốn dòng stdout của ứng dụng và phân biệt chúng với log.
- [ ] Biết khi nào Boot hữu ích và khi nào Framework trực tiếp đã đủ.

## 12. Tài liệu chính thức để học đúng theo phiên bản

- [Spring Framework – Overview](https://docs.spring.io/spring-framework/reference/overview.html)
- [Spring Framework – The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
- [Spring Framework – Container Overview](https://docs.spring.io/spring-framework/reference/core/beans/basics.html)
- [Spring Boot – Getting Started](https://docs.spring.io/spring-boot/reference/getting-started/index.html)
- [Spring Boot – Using @SpringBootApplication](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot – Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot – Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Initializr](https://start.spring.io/)

**Kết luận:** Spring Framework tạo ra **nền tảng IoC/DI và các module ứng dụng**, còn Spring Boot bổ sung **cách khởi động, auto-configuration, starters và tooling** để sử dụng nền tảng ấy nhanh, nhất quán hơn. Học Boot hiệu quả khi vẫn hiểu bean, dependency injection, scope, lifecycle và những giới hạn của Core Container bên dưới.