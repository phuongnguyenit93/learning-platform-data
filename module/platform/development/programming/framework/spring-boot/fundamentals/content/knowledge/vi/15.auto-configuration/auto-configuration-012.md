# Thay dependency, property hoặc bean và kiểm chứng cấu hình thay đổi

Spring Boot tự cấu hình ứng dụng dựa trên những gì có mặt trong classpath, các property đang hoạt động và những bean mà ứng dụng đã khai báo. Vì vậy, khi bạn **thay dependency, đổi property hoặc cung cấp một bean tùy chỉnh**, tập auto-configuration được áp dụng có thể thay đổi theo.

Ví dụ:

- Thêm Spring Security starter có thể làm các request HTTP được bảo vệ theo cấu hình mặc định.
- Đổi `server.port` làm embedded web server lắng nghe ở cổng khác.
- Tự khai báo `DataSource` có thể khiến auto-configuration datasource mặc định nhường quyền.
- Bỏ một thư viện khỏi classpath có thể khiến auto-configuration phụ thuộc thư viện đó không còn phù hợp.

Nhưng chỉ nhìn file cấu hình hoặc thấy ứng dụng khởi động thành công chưa đủ để biết thay đổi đã có hiệu lực. Cần kiểm chứng ở nhiều tầng: **dependency đã được resolve chưa, property thực tế có được nạp không, condition nào match, bean nào đã đăng ký và hành vi runtime có thay đổi đúng không**.

## 1. Ba cách phổ biến để tùy chỉnh auto-configuration

Spring Boot cung cấp những giá trị mặc định để ứng dụng khởi động nhanh. Khi cần thay đổi hành vi, bạn thường bắt đầu từ một trong ba điểm:

| Điểm thay đổi | Bạn thay đổi điều gì? | Auto-configuration có thể phản ứng ra sao? |
| --- | --- | --- |
| Dependency | Thêm, bỏ hoặc thay thư viện trên classpath | `@ConditionalOnClass`, `@ConditionalOnMissingClass` và các điều kiện liên quan có thể match khác đi |
| Property | Thay giá trị trong `application.properties`, YAML, biến môi trường hoặc tham số chạy | `@ConditionalOnProperty` và các cấu hình đọc `Environment` có thể chọn nhánh khác |
| Bean | Tự khai báo một bean trong application context | `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` có thể thay đổi kết quả; bean tùy chỉnh có thể thay vai trò mặc định |

```text
                Thay đổi ứng dụng
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Dependency   Property       Bean
          |            |            |
          v            v            v
       Classpath    Environment   Bean registry
          |            |            |
          +------------+------------+
                       |
                       v
              Đánh giá conditions
                       |
                       v
            Auto-configuration thay đổi
                       |
                       v
              Bean definitions mới
                       |
                       v
              Runtime behavior mới
```

Ba điểm này có thể kết hợp. Chẳng hạn, thêm starter Data JPA đưa các thư viện JPA lên classpath, property datasource cung cấp thông tin kết nối, còn một bean `DataSource` tự định nghĩa có thể thay cấu hình mặc định. Mỗi thay đổi tác động vào một phần khác nhau của quá trình cấu hình.

## 2. Thay dependency: classpath làm thay đổi điều kiện

Spring Boot có thể kiểm tra một class hoặc thư viện có trên classpath hay không. Các auto-configuration thường dùng điều kiện như:

```java
@ConditionalOnClass(SomeLibrary.class)
@ConditionalOnMissingClass("com.example.legacy.LegacyClient")
```

Khi thêm hoặc bỏ dependency, kết quả của điều kiện classpath có thể đổi.

### 2.1. Thêm starter để bật một nhóm tính năng

Ví dụ ứng dụng cần Spring MVC để xây dựng REST API. Trong dự án Spring Boot 3.x dùng Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Hoặc Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Các ví dụ giả định dự án đã dùng Spring Boot dependency management (parent/BOM hoặc plugin tương ứng), vì vậy phiên bản starter được quản lý tập trung.

Khi dependency được resolve, classpath có các thành phần web cần thiết. Spring Boot có thể chọn những cấu hình MVC và web server phù hợp với classpath cùng các điều kiện khác.

Một controller đơn giản:

```java
package com.example.demo.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello";
    }
}
```

Nếu ứng dụng có Spring MVC, component scan bao phủ package controller và web server khởi động thành công, endpoint có thể được gọi tại:

```text
GET http://localhost:8080/hello
```

Chỉ thêm starter không tự tạo controller. Dependency cung cấp hạ tầng; ứng dụng vẫn phải khai báo endpoint và khởi động context phù hợp.

### 2.2. Bỏ dependency có thể làm auto-configuration không còn match

Giả sử trước đó ứng dụng có starter Web. Khi bỏ starter khỏi build file:

```groovy
dependencies {
    // Đã bỏ spring-boot-starter-web
}
```

Những class Spring MVC hoặc embedded servlet server có thể không còn trên runtime classpath. Auto-configuration phụ thuộc chúng có thể bị bỏ qua.

Hệ quả cần phân biệt:

- Ứng dụng có thể vẫn khởi động như một ứng dụng non-web.
- Controller class có thể không còn được xử lý như endpoint MVC.
- Những bean khác vẫn có thể được đăng ký nếu không phụ thuộc web stack.
- Nếu code trực tiếp tham chiếu class đã bị bỏ, quá trình biên dịch có thể thất bại trước khi ứng dụng chạy.

Không nên kỳ vọng bỏ dependency chỉ làm mất một endpoint mà mọi thứ khác không thay đổi. Hãy xem dependency tree và condition report để biết chính xác những cấu hình bị ảnh hưởng.

### 2.3. Thay web server nhúng

Trong một ứng dụng servlet Spring Boot 3.x, `spring-boot-starter-web` thường kéo theo Tomcat làm web server nhúng mặc định. Nếu muốn dùng Jetty, có thể loại Tomcat và thêm starter Jetty tương ứng:

**Gradle:**

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

Đây là ví dụ theo cách tổ chức starter phổ biến của Spring Boot 3.x. Tên artifact và cách cấu hình có thể thay đổi ở dòng phát hành khác; hãy dùng tọa độ được tài liệu của phiên bản dự án hỗ trợ.

Sau khi thay dependency, hãy kiểm tra:

1. Tomcat starter không còn trong runtime dependency tree.
2. Jetty starter và các module liên quan đã được resolve.
3. Ứng dụng khởi động với web server mong muốn.
4. HTTP request thực tế vẫn được xử lý.

Việc đổi server không nhất thiết thay đổi controller code. Nó thay thành phần hạ tầng nhận và xử lý kết nối HTTP.

### 2.4. Thêm Data JPA cần thêm driver database

Starter Data JPA cung cấp Spring Data JPA, Hibernate và những thành phần tích hợp. Nhưng nó không tự cung cấp mọi JDBC driver cho mọi database.

Ví dụ dùng PostgreSQL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Sau đó cần cấu hình kết nối:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_user
spring.datasource.password=${DB_PASSWORD}
```

Nếu chỉ thêm Data JPA nhưng thiếu JDBC driver, database server hoặc thông tin kết nối, ứng dụng có thể không khởi động được. Auto-configuration cần đủ điều kiện để tạo `DataSource`, và datasource cần kết nối được tới database.

### 2.5. Xem dependency đã thay đổi như thế nào

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để tìm một dependency cụ thể:

```bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
```

**Maven:**

```bash
./mvnw dependency:tree
```

Lọc theo artifact:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
```

Trên Windows, dùng `gradlew.bat` hoặc `mvnw.cmd`; trong PowerShell có thể cần đặt đối số `-D...` trong dấu ngoặc kép:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.boot:spring-boot-starter-tomcat"
```

Dependency tree cho biết build tool đã resolve gì. Nó không chứng minh auto-configuration đã match; đó là một bước kiểm tra khác.

## 3. Thay property: điều khiển cấu hình qua Environment

Nhiều auto-configuration đọc property để chọn hành vi. Ví dụ:

- `server.port` chọn cổng web server.
- `spring.datasource.*` cấu hình datasource.
- `spring.jpa.*` điều chỉnh hành vi JPA/Hibernate.
- `management.endpoints.web.exposure.include` điều khiển endpoint Actuator được expose qua HTTP.
- Property riêng của ứng dụng có thể bật/tắt một feature.

### 3.1. Đổi cổng web server

Trong `application.properties`:

```properties
server.port=8081
```

Sau khi khởi động lại ứng dụng, web server sẽ dùng cổng 8081 nếu cấu hình phù hợp và cổng đó khả dụng.

Kiểm chứng:

```bash
curl -i http://localhost:8081/hello
```

Nếu vẫn gọi cổng 8080, bạn có thể nhận lỗi kết nối hoặc đang truy cập một tiến trình khác. Hãy kiểm tra log startup để xác định cổng thực tế.

### 3.2. Đổi property qua command line

Spring Boot cho phép truyền application argument khi khởi động:

```bash
java -jar build/libs/demo.jar --server.port=8082
```

Hoặc dùng Gradle:

```bash
./gradlew bootRun --args='--server.port=8082'
```

Với Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=8082
```

Cú pháp truyền đối số Maven có thể cần điều chỉnh theo phiên bản plugin và shell; trong IDE, đặt `--server.port=8082` ở trường **Program arguments** là cách trực quan.

Command-line property thường có độ ưu tiên cao hơn property trong file cấu hình. Vì vậy, nếu `application.properties` ghi 8080 nhưng command line truyền 8082, giá trị được dùng có thể là 8082.

### 3.3. Dùng biến môi trường

Property `server.port` có thể được ánh xạ từ biến môi trường `SERVER_PORT`.

**Linux/macOS:**

```bash
SERVER_PORT=8083 java -jar build/libs/demo.jar
```

**Windows PowerShell:**

```powershell
$env:SERVER_PORT = "8083"
java -jar build/libs/demo.jar
```

Sau khi chạy, kiểm tra log startup và gọi đúng cổng. Biến môi trường hữu ích khi cùng một artifact cần chạy ở nhiều môi trường mà không sửa file cấu hình trong JAR.

### 3.4. Profile làm thay đổi tập property được nạp

Có thể tạo:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

`application.properties`:

```properties
spring.application.name=shop
server.port=8080
```

`application-dev.properties`:

```properties
server.port=8081
logging.level.com.example.demo=DEBUG
```

`application-prod.properties`:

```properties
server.port=8080
logging.level.root=INFO
```

Kích hoạt profile:

```properties
spring.profiles.active=dev
```

Hoặc qua biến môi trường:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
```

Khi profile `dev` active, Spring Boot nạp thêm cấu hình tương ứng. Các property cụ thể có thể ghi đè giá trị chung theo quy tắc property source của Spring Boot.

Profile không tự động tạo một bean nếu bean không được khai báo có điều kiện. Ví dụ, `@Profile("dev")` trên một configuration class hoặc bean method mới trực tiếp quyết định bean chỉ được đăng ký trong profile đó.

### 3.5. Property có hiệu lực khi nào?

Phần lớn auto-configuration được đánh giá trong quá trình khởi động application context. Vì vậy, khi thay property điều khiển điều kiện hoặc hạ tầng, cách đơn giản và dễ dự đoán nhất là **khởi động lại ứng dụng**.

Một số property có thể được dùng trong runtime bởi component đọc `Environment` mỗi lần thực thi. Nhưng không nên mặc định mọi property đều tự cập nhật bean đã tạo khi file cấu hình thay đổi. Muốn cấu hình động cần một cơ chế refresh/configuration phù hợp và phải biết bean nào hỗ trợ cập nhật.

## 4. Thay bean: để auto-configuration nhường quyền

Một pattern quan trọng trong Spring Boot là auto-configuration cung cấp bean mặc định, nhưng cho phép ứng dụng tự định nghĩa bean thay thế.

Ví dụ:

```java
@AutoConfiguration
public class ClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Nếu ứng dụng đã cung cấp một bean `Clock` phù hợp và bean đó được xử lý trước auto-configuration, `@ConditionalOnMissingBean` có thể khiến bean mặc định không được đăng ký.

### 4.1. Tự khai báo bean để thay mặc định

Trong ứng dụng:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

Khi auto-configuration được sắp xếp đúng, bean `businessClock` khiến điều kiện thiếu `Clock` không còn thỏa mãn. Spring Boot nhường quyền cho cấu hình ứng dụng.

Đây là cách tùy biến thông thường, không cần bật bean definition overriding. Bean tùy chỉnh có thể mang tên khác với bean mặc định; điều kiện xét theo kiểu `Clock` trong ví dụ này.

### 4.2. Phân biệt điều kiện theo kiểu và theo tên

Hai annotation dưới đây kiểm tra hai điều khác nhau:

```java
@ConditionalOnMissingBean(Clock.class)
```

```java
@ConditionalOnMissingBean(name = "appClock")
```

- Cách đầu kiểm tra bean phù hợp theo kiểu `Clock`.
- Cách thứ hai kiểm tra bean có tên `appClock`.

Nếu ứng dụng có một bean `Clock` tên `businessClock`, điều kiện theo kiểu có thể khiến cấu hình mặc định lùi lại; điều kiện theo tên có thể vẫn match nếu không có bean `appClock`.

Hãy chọn điều kiện theo đúng hợp đồng mà auto-configuration muốn cung cấp.

### 4.3. Thay bean mặc định bằng `@Primary` hay `@Qualifier`?

Giả sử ứng dụng có hai bean khác tên:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean
    @Primary
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

Nếu một service inject `Clock` mà không chỉ định qualifier, `businessClock` là ứng viên primary trong tình huống thông thường.

Nếu muốn chỉ rõ:

```java
public ReportService(@Qualifier("utcClock") Clock clock) {
    this.clock = clock;
}
```

`@Primary` và `@Qualifier` giải quyết **chọn bean khi có nhiều ứng viên**. Chúng không phải cơ chế loại bỏ auto-configuration. Muốn bean mặc định không được đăng ký, dùng condition phù hợp như `@ConditionalOnMissingBean`.

### 4.4. Bean overriding không phải giải pháp mặc định

Property:

```properties
spring.main.allow-bean-definition-overriding=true
```

cho phép một bean definition đăng ký sau thay thế definition cùng tên trong registry ở những trường hợp áp dụng. Đây không phải cách ưu tiên để tùy biến auto-configuration.

Nên ưu tiên:

1. Tự cung cấp bean theo hợp đồng được auto-configuration hỗ trợ.
2. Dùng `@ConditionalOnMissingBean` trong auto-configuration của thư viện.
3. Đổi bean name nếu cần giữ nhiều implementation.
4. Dùng `@Primary` hoặc `@Qualifier` khi cần chọn một bean trong nhiều ứng viên.
5. Chỉ dùng overriding khi đã xác định rõ tên bean, nguồn đăng ký và lý do cần thay thế definition.

## 5. Thay đổi cấu hình bằng cách loại trừ auto-configuration

Đôi khi ứng dụng không muốn một auto-configuration cụ thể được áp dụng. Spring Boot hỗ trợ loại trừ qua `exclude`, `excludeName` hoặc property.

### 5.1. Loại trừ bằng class

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Ví dụ này loại `DataSourceAutoConfiguration` khỏi quá trình auto-configuration. Nếu ứng dụng vẫn có service bắt buộc cần `DataSource`, nó có thể không khởi động được.

### 5.2. Loại trừ bằng tên class

```java
@SpringBootApplication(
    excludeName = {
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
    }
)
public class DemoApplication {
}
```

`excludeName` hữu ích khi muốn chỉ định tên class mà không import trực tiếp class đó trong source.

### 5.3. Loại trừ bằng property

```properties
spring.autoconfigure.exclude=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Khi cần loại trừ nhiều cấu hình, khai báo danh sách tên theo định dạng property tương ứng.

### 5.4. Khi nào nên exclude?

Chỉ loại trừ khi bạn biết cấu hình nào đang được áp dụng và lý do nó không phù hợp. Ví dụ, ứng dụng không dùng database nhưng một dependency tùy chọn làm cấu hình datasource được xem xét; hoặc ứng dụng muốn tự cấu hình một hạ tầng theo cách riêng.

Exclude một auto-configuration không tự xóa mọi bean có cùng chức năng. Bean vẫn có thể đến từ component scan, `@Import`, một configuration class khác hoặc một thư viện khác.

## 6. Kiểm chứng dependency thay đổi

Khi thay dependency, kiểm tra theo hai bước: build tool resolve đúng thư viện và ứng dụng thực sự chạy với runtime classpath mong muốn.

### 6.1. Gradle

Liệt kê dependency runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Xem vì sao một artifact xuất hiện:

```bash
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath
```

Kiểm tra dependency đã bị loại:

```bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
```

Nếu không tìm thấy dependency, đó có thể là kết quả mong muốn sau exclusion. Nếu dependency vẫn xuất hiện qua một đường bắc cầu khác, hãy xem phần dependency path trong kết quả.

### 6.2. Maven

```bash
./mvnw dependency:tree
```

Lọc một artifact:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
```

Xem dependency bị conflict hoặc bị loại trừ:

```bash
./mvnw dependency:tree -Dverbose
```

`-Dverbose` giúp hiển thị thêm những dependency bị loại do quy tắc mediation. Đừng chỉ nhìn một dòng artifact; hãy kiểm tra version và đường dependency để biết vì sao nó có mặt.

### 6.3. Build thành công chưa đủ

Một build thành công chứng minh source và dependency đã vượt qua những bước build được thực hiện. Nó không chứng minh:

- Auto-configuration mong muốn đã match.
- Bean mong muốn đã được đăng ký.
- Database hoặc external service có thể kết nối.
- Endpoint HTTP hoạt động.
- Ứng dụng đang chạy đúng profile/cổng.

Sau khi dependency thay đổi, hãy tiếp tục kiểm tra condition report, application context và hành vi runtime.

## 7. Kiểm chứng property đã được áp dụng

### 7.1. Quan sát log startup

Với web application, log có thể cho biết server đã khởi động trên cổng nào:

```text
Tomcat started on port 8081 (http) with context path '/'
Started DemoApplication ...
```

Nội dung cụ thể phụ thuộc web server và phiên bản. Với WebFlux, server có thể là Netty; với ứng dụng non-web, không có embedded HTTP server.

Log startup là dấu hiệu hữu ích nhưng hãy kết hợp với request thực tế.

### 7.2. Gọi endpoint để xác nhận

Nếu endpoint `/hello` được khai báo:

```bash
curl -i http://localhost:8081/hello
```

Kiểm tra status code và body. Nếu server khởi động ở cổng 8081 nhưng endpoint trả `404`, property cổng có thể đã có hiệu lực trong khi component scan hoặc mapping chưa đúng.

### 7.3. Kiểm tra property trong `Environment`

Trong một bean được tạo sau khi context khởi động, có thể đọc giá trị:

```java
@Component
public class RuntimeConfigurationReporter {

    private final Environment environment;

    public RuntimeConfigurationReporter(Environment environment) {
        this.environment = environment;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {
        Integer port = environment.getProperty(
                "server.port",
                Integer.class
        );
        System.out.println("Configured server.port = " + port);
    }
}
```

Ví dụ này in property mà `Environment` đang cung cấp. Nếu `server.port` không được khai báo tường minh, giá trị đọc trực tiếp có thể là `null` dù web server sử dụng cổng mặc định. Muốn quan sát cổng thực tế, hãy xem web server startup log hoặc cấu hình web server phù hợp.

`Environment` cho biết giá trị property sau khi các property source được kết hợp; nó không tự chứng minh mọi bean đã tiêu thụ giá trị đó.

## 8. Kiểm chứng auto-configuration bằng Condition Evaluation Report

Spring Boot có thể in báo cáo cho biết auto-configuration nào match hoặc không match.

### 8.1. Bật debug mode

Có thể thêm tham số:

```text
--debug
```

Ví dụ Gradle:

```bash
./gradlew bootRun --args='--debug'
```

Hoặc cấu hình:

```properties
debug=true
```

Spring Boot có thể in **Condition Evaluation Report**, gồm:

- **Positive matches:** các cấu hình có điều kiện phù hợp.
- **Negative matches:** cấu hình bị bỏ qua và lý do.
- **Exclusions:** cấu hình bị loại trừ.
- **Unconditional classes:** các cấu hình không phụ thuộc một số điều kiện thông thường.

Đầu ra là thông tin chẩn đoán của auto-configuration. Nó không phải danh sách mọi bean instance trong application context.

### 8.2. So sánh báo cáo trước và sau thay đổi

Ví dụ bạn thêm Spring Security starter:

1. Chạy ứng dụng trước thay đổi với `--debug`, lưu lại các match liên quan security.
2. Thêm starter Security và đồng bộ dependency.
3. Chạy lại với cùng profile và property.
4. So sánh những condition liên quan đến security.
5. Thử truy cập endpoint để xác nhận hành vi bảo vệ thực tế.

Một thay đổi dependency có thể làm nhiều condition match khác nhau. Đừng chỉ tìm tên một auto-configuration; hãy xem điều kiện classpath và bean liên quan.

### 8.3. Phân biệt điều kiện match và bean được tạo

Một auto-configuration class match không có nghĩa tất cả bean method trong class đều tạo bean. Mỗi method có thể có condition riêng:

```java
@AutoConfiguration
@ConditionalOnClass(ReportClient.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "reports",
        name = "enabled",
        havingValue = "true"
    )
    ReportService reportService(ReportClient client) {
        return new ReportService(client);
    }
}
```

Class có thể được xem xét khi `ReportClient` có mặt, nhưng bean `ReportService` chỉ được đăng ký nếu property phù hợp và dependency cần thiết được resolve.

## 9. Kiểm chứng bean thực tế trong application context

Sau khi context khởi động, bạn có thể kiểm tra bean theo tên hoặc kiểu.

### 9.1. Kiểm tra bean theo kiểu

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

String[] names = context.getBeanNamesForType(Clock.class);
System.out.println(Arrays.toString(names));
```

Nếu ứng dụng có một bean `Clock`, đầu ra có thể là:

```text
[businessClock]
```

Nếu có nhiều bean `Clock`, tất cả tên phù hợp có thể xuất hiện. Phương thức này giúp xác nhận bean definitions/beans phù hợp theo kiểu trong context; không nên suy luận rằng chỉ có một bean chỉ vì một tên xuất hiện trong log khác.

### 9.2. Kiểm tra bean theo tên và kiểu runtime

```java
Clock clock = context.getBean("businessClock", Clock.class);
System.out.println(clock.getClass().getName());
```

Nếu bean được bọc bởi proxy, runtime class có thể khác class triển khai. Đối với bean đơn giản như `Clock`, thường không cần proxy; nhưng với AOP, transaction hoặc scoped bean, cần lưu ý khác biệt này.

### 9.3. Đếm bean theo kiểu

```java
Map<String, Clock> clocks = context.getBeansOfType(Clock.class);
System.out.println("Clock beans: " + clocks.keySet());
```

`getBeansOfType` có thể dẫn đến khởi tạo bean trong một số tình huống. Dùng nó ở giai đoạn context đã sẵn sàng để chẩn đoán, không nên gọi tùy tiện trong condition hoặc quá trình đăng ký cấu hình sớm.

### 9.4. Kiểm tra bean thay thế có thực sự được dùng

Không chỉ kiểm tra bean tồn tại; hãy xác nhận service đang nhận đúng implementation:

```java
@Service
public class ReportService {
    private final Clock clock;

    public ReportService(@Qualifier("businessClock") Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

Nếu mục tiêu là dùng `businessClock`, hãy kiểm tra qualifier và kết quả nghiệp vụ. Một bean có thể tồn tại nhưng service vẫn inject bean khác nếu cấu hình chọn bean không đúng.

## 10. Dùng Spring Boot Actuator để quan sát runtime

Actuator cung cấp các endpoint quản trị và quan sát ứng dụng. Khi thêm Actuator starter phù hợp, có thể dùng những endpoint như:

- `health`: trạng thái health indicator.
- `beans`: danh sách bean trong application context.
- `conditions`: condition evaluation report.
- `env`: thông tin environment/property source (cần cấu hình exposure và bảo vệ).
- `configprops`: các bean được bind từ `@ConfigurationProperties`.

Ví dụ dependency trong Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Cấu hình expose một số endpoint qua HTTP:

```properties
management.endpoints.web.exposure.include=health,beans,conditions,configprops
```

Sau đó, trong môi trường phù hợp có thể truy cập:

```text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/beans
http://localhost:8080/actuator/conditions
http://localhost:8080/actuator/configprops
```

Endpoint thực tế phụ thuộc dependency, phiên bản, web stack và cấu hình exposure. Một số endpoint nhạy cảm có thể bị giới hạn hoặc cần xác thực. Không expose `env`, `configprops` hay các endpoint quản trị nhạy cảm công khai trên production nếu chưa thiết kế bảo mật và lọc dữ liệu phù hợp.

### 10.1. `/actuator/conditions`

Endpoint `conditions` hữu ích để xem các condition của auto-configuration trong context đang chạy. Nó giúp trả lời:

- Cấu hình nào match?
- Cấu hình nào không match?
- Property hoặc classpath condition nào quyết định?

Kết quả endpoint có cấu trúc JSON. Nó bổ sung cho log `--debug`, đặc biệt khi muốn quan sát từ một ứng dụng đã khởi động.

### 10.2. `/actuator/beans`

Endpoint `beans` cho biết những bean definitions/beans mà Actuator có thể báo cáo trong context. Dùng nó để kiểm tra bean name, type và quan hệ phụ thuộc ở mức thông tin được endpoint cung cấp.

Nó không thay thế debugger hoặc test để xác nhận một service thực sự gọi implementation mong muốn.

## 11. Kiểm chứng tự động bằng test

Kiểm tra bằng tay hữu ích khi khám phá, nhưng test giúp xác nhận hành vi có thể lặp lại sau mỗi lần thay đổi dependency hoặc property.

### 11.1. `@SpringBootTest` kiểm tra context của ứng dụng

Ví dụ:

```java
@SpringBootTest(
    properties = {
        "features.reports.enabled=true"
    }
)
class ReportFeatureEnabledTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void registersReportServiceWhenFeatureIsEnabled() {
        assertThat(context.containsBean("reportService")).isTrue();
    }
}
```

Test này giả định `ReportConfiguration` cung cấp bean tên `reportService` khi property bật và toàn bộ dependency của ứng dụng có thể khởi tạo. Nếu bean có tên khác, hãy kiểm tra đúng tên thực tế hoặc kiểm tra theo kiểu.

### 11.2. Kiểm tra khi property tắt

```java
@SpringBootTest(
    properties = {
        "features.reports.enabled=false"
    }
)
class ReportFeatureDisabledTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void doesNotRegisterReportServiceWhenFeatureIsDisabled() {
        assertThat(context.containsBean("reportService")).isFalse();
    }
}
```

Nếu có bean khác cũng mang tên `reportService`, test cần giới hạn context hoặc dùng tên/kiểu cụ thể hơn để tránh kết luận sai.

### 11.3. `ApplicationContextRunner` kiểm tra auto-configuration độc lập

`ApplicationContextRunner` rất hữu ích khi phát triển auto-configuration. Nó tạo một context nhỏ, cho phép đặt property và import cấu hình cần kiểm tra mà không phải khởi động toàn bộ ứng dụng.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ReportAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportAutoConfiguration.class
                            )
                    );

    @Test
    void createsReportServiceWhenEnabled() {
        contextRunner
                .withPropertyValues("reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportService.class);
                });
    }

    @Test
    void backsOffWhenDisabled() {
        contextRunner
                .withPropertyValues("reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportService.class);
                });
    }
}
```

Đây là ví dụ minh họa cho auto-configuration độc lập có điều kiện `@ConditionalOnProperty`. Các class `ReportAutoConfiguration` và `ReportService` phải tồn tại trong dự án; test cần các dependency Spring Boot Test, JUnit và AssertJ tương ứng.

### 11.4. Kiểm tra bean mặc định nhường quyền

Giả sử auto-configuration tạo `SearchClient` nếu ứng dụng chưa có:

```java
@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Test khi chưa có bean tùy chỉnh:

```java
@Test
void createsDefaultClientWhenNoCustomClientExists() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(SearchAutoConfiguration.class)
            )
            .run(context -> {
                assertThat(context).hasSingleBean(SearchClient.class);
                assertThat(context.getBean(SearchClient.class))
                        .isInstanceOf(DefaultSearchClient.class);
            });
}
```

Test khi ứng dụng tự cung cấp bean:

```java
@Test
void backsOffWhenApplicationProvidesCustomClient() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(SearchAutoConfiguration.class)
            )
            .withBean(
                    SearchClient.class,
                    () -> new CompanySearchClient()
            )
            .run(context -> {
                assertThat(context).hasSingleBean(SearchClient.class);
                assertThat(context.getBean(SearchClient.class))
                        .isInstanceOf(CompanySearchClient.class);
            });
}
```

Test chứng minh condition `@ConditionalOnMissingBean` hoạt động theo mục tiêu: auto-configuration cung cấp default khi cần, và nhường quyền khi context đã có bean tùy chỉnh.

## 12. Quy trình thực hành: thay đổi rồi kiểm chứng

Khi cần thay dependency, property hoặc bean, có thể áp dụng quy trình sau.

### Bước 1 — Xác định hành vi mong muốn

Viết rõ điều gì phải thay đổi:

```text
Trước: ứng dụng dùng Tomcat, cổng 8080.
Sau: ứng dụng dùng Jetty, cổng 8081.
```

Hoặc:

```text
Trước: auto-configuration tạo DefaultSearchClient.
Sau: ứng dụng sử dụng CompanySearchClient.
```

Nếu không mô tả được kết quả mong muốn, rất khó chọn đúng dependency, property hoặc bean.

### Bước 2 — Xác định tầng cần thay đổi

| Kết quả mong muốn | Tầng nên xem |
| --- | --- |
| Có thêm tính năng thư viện | Dependency |
| Tắt/bật tính năng theo môi trường | Property/profile |
| Đổi implementation mặc định | Bean tùy chỉnh và condition |
| Không dùng cấu hình framework nào đó | Auto-configuration exclusion |
| Chọn một trong nhiều bean | `@Qualifier` / `@Primary` |

Tránh thay đồng thời nhiều tầng nếu chưa cần thiết; nếu thay cả dependency, property và bean một lúc, sẽ khó xác định thay đổi nào tạo ra kết quả.

### Bước 3 — Thực hiện một thay đổi có kiểm soát

Ví dụ, chỉ đổi cổng:

```properties
server.port=8081
```

Hoặc chỉ thêm một bean:

```java
@Bean
SearchClient searchClient() {
    return new CompanySearchClient();
}
```

Giữ các yếu tố khác ổn định để dễ so sánh.

### Bước 4 — Xác nhận đầu vào đã thay đổi

- Dependency: xem dependency tree.
- Property: kiểm tra `Environment`, profile và property source.
- Bean: kiểm tra configuration được scan/import và bean name/type.

Đừng chuyển sang kết luận về auto-configuration khi chưa biết thay đổi đầu vào có thực sự được áp dụng.

### Bước 5 — Xem condition report

Chạy với `--debug` hoặc xem `/actuator/conditions` nếu Actuator đã được cấu hình phù hợp. Xác định auto-configuration nào match, không match hoặc bị exclude.

### Bước 6 — Xác nhận bean definitions và bean instance

Dùng `ApplicationContext`, Actuator `/beans` hoặc test để kiểm tra bean mong muốn. Nếu có nhiều bean cùng kiểu, kiểm tra cả qualifier/primary và bean mà service thực sự nhận.

### Bước 7 — Kiểm tra hành vi bên ngoài

Gọi endpoint HTTP, thực hiện truy vấn database hoặc chạy thao tác nghiệp vụ. Cấu hình chỉ có ý nghĩa khi hành vi runtime đáp ứng mục tiêu.

### Bước 8 — Viết test giữ hành vi

Tạo test cho trường hợp bật/tắt property, có/không có bean tùy chỉnh hoặc classpath dependency khác nhau. Test giúp ngăn một lần nâng cấp starter hoặc thay property làm cấu hình thay đổi ngoài ý muốn.

## 13. Một ví dụ tổng hợp: tùy chỉnh client tìm kiếm

Giả sử một thư viện cung cấp `SearchAutoConfiguration`:

```java
@AutoConfiguration
@ConditionalOnClass(SearchClient.class)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "search",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Có ba cách thay đổi hành vi:

### 13.1. Tắt feature bằng property

```properties
search.enabled=false
```

Kết quả mong đợi: bean mặc định không được đăng ký từ configuration method này.

Kiểm chứng: test context với property false và xác nhận không có `SearchClient` từ cấu hình này.

### 13.2. Bỏ dependency chứa `SearchClient`

Nếu class `SearchClient` không còn trên classpath, condition classpath có thể khiến auto-configuration bị bỏ qua. Nhưng nếu code ứng dụng vẫn trực tiếp tham chiếu `SearchClient`, build có thể thất bại do thiếu class.

Kiểm chứng: dependency tree và condition report; đồng thời xác nhận source code không còn phụ thuộc kiểu đã bỏ.

### 13.3. Cung cấp implementation riêng

```java
@Configuration(proxyBeanMethods = false)
public class CompanySearchConfiguration {

    @Bean
    SearchClient searchClient() {
        return new CompanySearchClient();
    }
}
```

Khi custom bean được đăng ký trước auto-configuration và thỏa kiểu điều kiện, default bean method “back off”.

Kiểm chứng:

```java
assertThat(context).hasSingleBean(SearchClient.class);
assertThat(context.getBean(SearchClient.class))
        .isInstanceOf(CompanySearchClient.class);
```

Ba trường hợp tạo kết quả khác nhau: tắt feature, bỏ khả năng tích hợp khỏi classpath và thay implementation. Cần phân biệt chúng khi chẩn đoán.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Thêm starter là tính năng tự chạy.” | Starter cung cấp dependency; còn cần condition, cấu hình và thành phần ứng dụng phù hợp |
| “Bỏ dependency chỉ xóa một bean.” | Nó có thể làm nhiều auto-configuration condition không còn match và làm code không biên dịch |
| “Đổi property trong file là bean đang chạy tự cập nhật.” | Nhiều cấu hình được đánh giá lúc startup; thường cần restart hoặc cơ chế refresh riêng |
| “`@Primary` thay thế auto-configuration.” | Nó chọn ứng viên khi inject; không nhất thiết ngăn default bean definition được đăng ký |
| “`@ConditionalOnMissingBean` và overriding là một.” | Condition ngăn đăng ký default khi bean phù hợp đã có; overriding thay definition cùng tên khi được phép |
| “Condition report cho biết mọi bean instance.” | Nó giải thích quyết định điều kiện của auto-configuration |
| “Dependency tree chứng minh auto-configuration match.” | Nó chỉ cho biết dependency đã resolve; cần condition report để kiểm chứng cấu hình |
| “Ứng dụng khởi động thành công nghĩa là property đã có hiệu lực.” | Cần kiểm tra giá trị thực tế và hành vi runtime |
| “Exclude auto-configuration xóa mọi bean tương tự.” | Bean vẫn có thể được đăng ký từ configuration hoặc import khác |
| “Một custom bean luôn thay được mọi default bean.” | Phải thỏa kiểu/tên/condition và được đăng ký đúng thời điểm |

## 15. Bài thực hành

### Bài 1 — Thay cổng bằng property

Chạy một ứng dụng Spring Boot Web với cổng mặc định. Đổi:

```properties
server.port=8081
```

Khởi động lại, kiểm tra log và gọi endpoint ở cổng 8081. Sau đó truyền `--server.port=8082` qua command line.

**Câu hỏi:** vì sao giá trị command line có thể thắng giá trị trong file cấu hình?

### Bài 2 — Thêm và bỏ starter Web

Tạo một ứng dụng có controller `/hello`. Xem dependency tree trước và sau khi thêm Spring Web starter. Sau đó bỏ starter và quan sát build/startup.

**Câu hỏi:** classpath nào liên quan đến việc auto-configuration web được áp dụng?

### Bài 3 — Thay server nhúng

Trong dự án Spring Boot 3.x, loại Tomcat và thêm Jetty theo ví dụ. Xem dependency tree để xác nhận runtime server dependency. Khởi động và gửi request HTTP.

**Câu hỏi:** vì sao controller không cần thay đổi chỉ vì web server được đổi?

### Bài 4 — Bean mặc định nhường quyền

Tạo auto-configuration cung cấp `SearchClient` mặc định với `@ConditionalOnMissingBean`. Chạy context khi không có custom bean, sau đó thêm `CompanySearchClient`.

**Yêu cầu:** viết test chứng minh default được đăng ký trong trường hợp đầu và bị bỏ qua trong trường hợp thứ hai.

### Bài 5 — Tắt feature bằng property

Tạo bean `ReportService` chỉ được đăng ký khi `reports.enabled=true`. Viết hai test context với giá trị true và false.

**Câu hỏi:** nếu một service khác bắt buộc inject `ReportService`, điều gì xảy ra khi feature bị tắt? Làm thế nào để dependency đó trở thành optional?

### Bài 6 — Xem Condition Evaluation Report

Chạy ứng dụng với `--debug` trước và sau khi thêm một starter. Tìm một positive match và một negative match liên quan đến dependency mới.

**Yêu cầu:** ghi lại điều kiện classpath/property/bean đã quyết định kết quả.

### Bài 7 — Dùng Actuator kiểm tra bean

Thêm Actuator, expose endpoint `beans` và `conditions` trong môi trường local. Kiểm tra bean custom có xuất hiện và auto-configuration mặc định có match hay không.

**Lưu ý:** chỉ expose endpoint cần thiết trong môi trường học tập; không công khai thông tin quản trị nhạy cảm.

## 16. Ghi nhớ

Muốn tùy chỉnh Spring Boot auto-configuration, hãy xác định bạn cần thay **classpath, Environment hay bean registry**. Thay dependency làm điều kiện classpath thay đổi; thay property tác động đến cấu hình và những `@ConditionalOnProperty`; tự khai báo bean có thể khiến cấu hình mặc định nhường quyền thông qua `@ConditionalOnMissingBean`.

Sau thay đổi, kiểm chứng theo từng tầng: dependency tree xác nhận thư viện, Environment xác nhận property, Condition Evaluation Report giải thích auto-configuration, application context xác nhận bean và test/request xác nhận hành vi. Không nên kết luận chỉ từ việc ứng dụng khởi động thành công.

Khi bạn tách rõ đầu vào, điều kiện, bean definition và hành vi runtime, việc thay starter, chuyển môi trường hoặc tùy chỉnh implementation sẽ dễ dự đoán và dễ kiểm soát hơn.
