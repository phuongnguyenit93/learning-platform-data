# Thay đổi starter, module, logging hoặc công cụ test khi nâng phiên bản

Nâng phiên bản Spring Boot không chỉ là đổi một con số trong file build. Spring Boot quản lý một hệ sinh thái gồm Spring Framework, Spring Data, Spring Security, Jackson, Hibernate, logging libraries, test frameworks và nhiều dependency khác. Các starter giúp đưa những thành phần phù hợp vào classpath, còn dependency management chọn những phiên bản tương thích. Khi nâng Boot, những lựa chọn này có thể thay đổi cùng lúc.

Vì vậy, một dự án có thể build thành công nhưng vẫn gặp lỗi lúc chạy: logging provider bị nạp hai lần, module không còn được auto-configuration discover, Hibernate đổi hành vi, test JUnit không được phát hiện hoặc một thư viện cũ gọi API đã bị loại bỏ. Ngược lại, một số thay đổi chỉ là đổi tên starter hoặc tách module nhưng không làm thay đổi nghiệp vụ.

Bài học tập trung vào cách xử lý những thay đổi thường gặp khi nâng phiên bản: **starter và dependency graph, cấu trúc module, logging stack, công cụ kiểm thử và quy trình migration**. Mục tiêu là giúp developer nhận diện phạm vi ảnh hưởng, thay đổi build có kiểm soát và xác nhận ứng dụng hoạt động trên phiên bản đích.

## 1. Vì sao nâng Spring Boot có thể ảnh hưởng nhiều thành phần?

Spring Boot cung cấp một bộ dependency versions đã được kiểm thử và quản lý cùng nhau. Khi dự án dùng Spring Boot parent hoặc BOM, nhiều thư viện được chọn phiên bản theo một tập hợp tương thích.

Ví dụ, một ứng dụng web có thể sử dụng:

~~~text
Application source
       |
       v
spring-boot-starter-web
       |
       +--> Spring MVC
       +--> Embedded servlet container
       +--> JSON integration
       +--> Logging starter
       |
       v
Spring Boot dependency management
       |
       +--> Spring Framework
       +--> Jackson
       +--> Tomcat
       +--> SLF4J / Logback
       |
       v
Runtime classpath
~~~

Khi nâng Boot, dependency management có thể cập nhật đồng thời nhiều thành phần. Điều này giúp tránh phải tự chọn từng version, nhưng cũng có nghĩa một thay đổi nhỏ ở parent version có thể kéo theo thay đổi đáng kể ở runtime.

Những nhóm ảnh hưởng phổ biến:

- **JDK và build tool:** Java baseline, Maven/Gradle plugin, compiler, annotation processing.
- **Spring Framework:** container, web, AOP, transaction, validation và các API nền tảng.
- **Starter:** tên, nội dung dependency và cách chia module.
- **Persistence:** Spring Data, Hibernate, JDBC driver và migration tooling.
- **Serialization:** Jackson, JSON configuration, date/time handling.
- **Logging:** SLF4J API, provider, bridges và implementation.
- **Testing:** JUnit, Mockito, AssertJ, Spring Test và test slices.
- **Auto-configuration:** imports metadata, condition evaluation và ordering.
- **Third-party integration:** thư viện security, metrics, tracing, messaging và cloud.

Một nâng cấp an toàn cần biết nhóm nào thay đổi và kiểm tra đúng hành vi phụ thuộc nhóm đó.

## 2. Phân biệt các phiên bản trong một dự án

Không nên coi “version của ứng dụng” là một con số duy nhất. Một dự án Spring Boot có nhiều lớp version:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Spring Boot | 3.x hoặc 4.x | Nền tảng và dependency management |
| Spring Framework | 6.x hoặc 7.x tùy Boot | Container, web, core APIs |
| Java | 17, 21 hoặc baseline được hỗ trợ | Ngôn ngữ và runtime |
| Maven/Gradle | Phiên bản wrapper | Build engine |
| Boot build plugin | Maven/Gradle plugin | Package, build image, AOT |
| Logging API/provider | SLF4J, Logback, Log4j 2 | Ghi log |
| Test platform | JUnit Platform/Jupiter | Phát hiện và chạy test |
| Test libraries | Mockito, AssertJ | Mock và assertion |
| Database stack | Hibernate, driver | ORM và kết nối dữ liệu |

Các phiên bản này có quan hệ tương thích. Ví dụ, một Spring Boot release chỉ hỗ trợ một khoảng Java và Spring Framework nhất định. Không nên nâng riêng Spring Framework lên một major version mới trong khi vẫn dùng Boot cũ nếu dependency management của Boot không hỗ trợ tổ hợp đó.

### Kiểm tra compatibility trước khi sửa

Trước khi nâng cấp, xác định:

1. Phiên bản Boot hiện tại và phiên bản mục tiêu.
2. Java baseline mà phiên bản đích yêu cầu.
3. Phiên bản Maven/Gradle wrapper được hỗ trợ.
4. Các thư viện bên ngoài có yêu cầu version cụ thể không.
5. Những thay đổi breaking/deprecated trong release notes và migration guide.
6. Các module nội bộ có phụ thuộc trực tiếp vào Spring API hay không.

Nên chọn một phiên bản đích cụ thể, đọc tài liệu migration của các major/minor releases liên quan, rồi lập danh sách thay đổi. Đừng nâng theo kiểu thay hàng loạt số version mà không biết mỗi số thuộc hệ sinh thái nào.

## 3. Dependency management: để Spring Boot chọn version tương thích

Một trong những lợi ích lớn của Spring Boot là dependency management. Thay vì khai báo version cho mọi thư viện Spring và thư viện liên quan, dự án có thể dùng Boot parent hoặc BOM.

### Maven với spring-boot-starter-parent

Một cấu hình phổ biến:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>
~~~

Các dependency được quản lý có thể khai báo không cần version riêng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Khi nâng version parent, tập version do parent quản lý có thể thay đổi đồng bộ.

### Maven khi không thể dùng Boot parent

Một công ty có thể có parent POM riêng. Khi đó, import Boot BOM trong `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Ứng dụng vẫn có thể khai báo các starter mà không lặp version. Tuy nhiên, việc import BOM **không tự mang theo mọi cấu hình plugin** như dùng Boot parent. Nếu cần executable JAR, repackage hoặc build-image, phải cấu hình plugin tương ứng.

### Gradle với plugin và dependency management

Một ví dụ Kotlin DSL:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
~~~

Tùy cấu hình Gradle, có thể dùng Spring Boot plugin cùng dependency management plugin hoặc Gradle native platform/BOM support. Điều quan trọng là phải hiểu **nguồn nào đang quản lý version** và tránh để nhiều cơ chế ghi đè lẫn nhau.

### Không gắn version thủ công cho mọi starter

Ví dụ không nên làm nếu không có lý do tương thích rõ ràng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.a.b</version>
</dependency>
~~~

Nếu các starter bị ép về version khác nhau, chúng có thể kéo các module Spring không cùng release train. Hãy để BOM quản lý version, trừ khi có một override được đánh giá và kiểm thử có chủ đích.

## 4. Starter là gì và vì sao tên starter có thể thay đổi?

Starter là dependency convenience của Spring Boot. Nó gom những thư viện thường được dùng cùng nhau để developer không phải tự chọn từng dependency nền tảng.

Ví dụ:

- `spring-boot-starter-web` cho ứng dụng servlet/web MVC.
- `spring-boot-starter-data-jpa` cho JPA và persistence integration.
- `spring-boot-starter-security` cho Spring Security.
- `spring-boot-starter-validation` cho Bean Validation integration.
- `spring-boot-starter-test` cho test stack phổ biến.

Starter thường không phải implementation trực tiếp của tính năng. Nó là điểm vào dependency graph.

### Một starter có thể kéo theo nhiều thư viện

~~~text
spring-boot-starter-data-jpa
          |
          +--> Spring Data JPA
          +--> Spring ORM / transaction integration
          +--> Hibernate ORM
          +--> JDBC-related infrastructure
          +--> Logging dependencies
~~~

Dependency graph chính xác phụ thuộc phiên bản Boot. Khi starter đổi nội dung hoặc module được tách, classpath có thể thay đổi dù dòng dependency trong POM không đổi.

### Không thêm starter chỉ vì tên nghe phù hợp

Nếu ứng dụng chỉ dùng JDBC template, có thể không cần JPA starter. Nếu chỉ expose REST API và không render server-side HTML, không cần thêm template engine starter. Starter không dùng làm tăng dependency count, scan surface và có thể kích hoạt auto-configuration không cần thiết.

Chọn starter theo capability thực sự sử dụng, không theo danh sách mẫu của một tutorial khác.

## 5. Thay đổi starter khi nâng phiên bản

Khi nâng Boot, một số starter có thể được đổi tên, thay nội dung, hoặc tách ra thành starter riêng. Quy trình xử lý:

1. Xác định dependency hiện tại.
2. Đọc migration guide/release notes của phiên bản đích.
3. Kiểm tra artifact mới thay thế hoặc module được tách.
4. Cập nhật dependency declaration.
5. Kiểm tra exclusions cũ còn cần thiết không.
6. Xem lại auto-configuration nào được kích hoạt.
7. Build và kiểm tra runtime classpath.

### Ví dụ: tách capability khỏi một starter lớn

Giả sử một phiên bản nền tảng tách một integration thành starter riêng. Trước đây project có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Sau migration, tính năng mới có thể yêu cầu thêm một starter/module riêng theo hướng dẫn của release đích:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-example-integration</artifactId>
</dependency>
~~~

Tên artifact trong ví dụ là placeholder minh họa cho ý tưởng tách module, không phải dependency để copy vào dự án. Hãy dùng đúng artifact được công bố trong release mà dự án nâng lên.

### Xóa dependency cũ chỉ sau khi hiểu dependency graph

Một thư viện có thể được kéo transitively bởi starter khác. Xóa một dependency trực tiếp không bảo đảm class đó biến mất khỏi runtime classpath. Ngược lại, thêm starter mới có thể đưa thêm một implementation cạnh tranh.

Dùng dependency tree để xác nhận kết quả cuối, không chỉ nhìn file build.

## 6. Dependency exclusions và thay implementation mặc định

Đôi khi ứng dụng muốn thay implementation mặc định, ví dụ dùng Log4j 2 thay Logback, hoặc dùng một HTTP client khác.

Maven exclusion:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là ví dụ loại logging starter khỏi dependency đi qua starter web. Nếu nhiều starter khác vẫn kéo logging starter, chỉ exclusion ở một dependency có thể chưa đủ để loại nó khỏi graph.

Một cách quản lý có thể là đặt exclusion ở nơi phù hợp trong dependency declarations hoặc dùng dependency management/constraints có chủ đích. Sau đó thêm đúng implementation thay thế.

### Exclusion có thể tạo lỗi runtime

Nếu loại một thư viện mà code hoặc starter khác vẫn cần, ứng dụng có thể gặp:

- `ClassNotFoundException`.
- `NoClassDefFoundError`.
- `NoSuchMethodError`.
- Bean auto-configuration không tạo được.
- Logging system không khởi động.

Không nên thêm exclusion chỉ để làm dependency tree trông ngắn hơn. Mỗi exclusion phải có lý do và được xác nhận bằng build/test/runtime.

## 7. Thay đổi module và ranh giới giữa application với library

Một hệ thống Spring Boot nhiều module có thể được tổ chức như:

~~~text
store-platform/
├── store-domain/
├── store-application/
├── store-persistence/
├── store-web/
├── store-observability/
└── store-service/
~~~

Ý tưởng:

- `store-domain` chứa model và business rules ít phụ thuộc framework.
- `store-application` chứa use cases và orchestration.
- `store-persistence` triển khai repository/database integration.
- `store-web` chứa controllers và HTTP adapters.
- `store-observability` chứa metrics/logging/tracing integration.
- `store-service` là module khởi chạy và tập hợp cấu hình.

Không phải dự án nào cũng cần tách nhiều module. Mỗi module tạo một ranh giới dependency và build riêng, do đó cần có lý do bảo trì, tái sử dụng hoặc phân chia ownership.

### Module library không nhất thiết là Spring Boot application

Một module dùng chung có thể chỉ là Java library:

~~~xml
<packaging>jar</packaging>
~~~

Nó không cần Boot plugin repackage hoặc main class. Nếu áp plugin Spring Boot lên mọi module mà không cần thiết, có thể tạo artifact sai mục đích hoặc làm build phức tạp.

Chỉ module deployable mới cần executable packaging, trừ trường hợp module library có yêu cầu build đặc biệt.

### Tránh dependency vòng giữa modules

Một cấu trúc tốt thường có dependency direction rõ:

~~~text
store-service
   |
   +--> store-web
   +--> store-persistence
   +--> store-application
              |
              v
         store-domain
~~~

Nếu domain phụ thuộc ngược vào web hoặc persistence implementation, việc nâng module hoặc thay starter có thể trở nên khó khăn. Đặt interface ở boundary phù hợp để implementation phụ thuộc vào abstraction.

## 8. Spring Boot auto-configuration trong module nội bộ

Một module có thể cung cấp auto-configuration để ứng dụng khác chỉ cần thêm dependency là nhận được bean mặc định.

Ví dụ:

~~~java
@AutoConfiguration
public class AuditModuleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

Với các thế hệ Spring Boot hiện đại, auto-configuration imports thường được khai báo trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file là tên đầy đủ của class auto-configuration, mỗi class trên một dòng:

~~~text
com.example.audit.AuditModuleAutoConfiguration
~~~

Khi module nội bộ nâng Boot, cần kiểm tra:

- Annotation auto-configuration còn phù hợp không.
- Imports metadata có đúng path/format không.
- Ordering và before/after constraints có đúng không.
- Condition classes và optional dependencies có tương thích không.
- Test có nạp auto-configuration qua cơ chế thật không.

### Vì sao test trực tiếp class chưa đủ?

Một test dùng:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        AuditModuleAutoConfiguration.class
                )
        )
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

chứng minh class hoạt động khi được nạp trực tiếp. Nó **không chứng minh imports metadata đã được đóng gói đúng trong JAR**.

Nên có thêm kiểm tra discovery/packaging hoặc integration test dùng module như một dependency thực tế.

### Không để auto-configuration trở thành component scan rộng

Một library module không nên ép ứng dụng chủ scan toàn bộ package của nó chỉ để tìm một bean. Dùng auto-configuration imports và conditions giúp integration có phạm vi rõ hơn, đồng thời cho phép ứng dụng override bean mặc định.

## 9. Khi nâng module, xem lại package và API công khai

Thay đổi major version của Spring Framework có thể ảnh hưởng package, method signature và annotation. Ví dụ nổi bật trong quá trình chuyển từ Spring Boot 2 sang Spring Boot 3 là hệ sinh thái Jakarta.

Những import cũ thuộc `javax.*` trong các API đã chuyển sang Jakarta có thể cần đổi thành `jakarta.*` tương ứng. Một ví dụ thường gặp:

~~~java
// Trước migration trong hệ sinh thái Java EE cũ:
import javax.persistence.Entity;

// Sau migration sang Jakarta Persistence:
import jakarta.persistence.Entity;
~~~

Tương tự, servlet, validation và annotation APIs cũng có những package chuyển đổi tương ứng.

### Không phải mọi javax đều đổi thành jakarta

Một số package thuộc Java SE vẫn giữ `javax`, ví dụ `javax.crypto` hoặc `javax.sql`. Không được thực hiện find/replace toàn bộ chuỗi `javax.` thành `jakarta.`.

Chỉ thay những API thuộc nhóm Jakarta EE đã chuyển namespace, dựa trên compiler errors và migration guide.

### Kiểm tra generated code và annotation processing

Lombok, MapStruct, QueryDSL và những processor khác có thể phụ thuộc vào compiler/JDK/framework API. Khi nâng JDK hoặc Spring, kiểm tra:

- Annotation processor versions.
- Compiler plugin.
- Generated source directories.
- Jakarta annotation/type imports.
- Build order trong multi-module.
- IDE annotation processing settings.

Một module có thể compile trên IDE nhưng fail trong CI nếu processor path khác nhau.

## 10. Nâng cấp Spring Boot major version: Java và framework baseline

Major upgrade thường có nhiều thay đổi hơn minor/patch upgrade.

Ví dụ migration Boot 2 sang Boot 3 gắn với việc chuyển sang Spring Framework 6, Java 17 baseline và namespace Jakarta cho nhiều API enterprise. Khi nâng, không chỉ thay parent version mà còn phải xử lý source code, dependencies và runtime.

Một checklist migration:

- Đảm bảo JDK build/runtime đáp ứng baseline.
- Nâng Maven/Gradle wrapper và plugin cần thiết.
- Chuyển package imports Java EE sang Jakarta ở đúng API.
- Kiểm tra Spring Security configuration.
- Kiểm tra Hibernate/JPA behavior và dialect.
- Kiểm tra validation provider.
- Kiểm tra servlet container và web APIs.
- Kiểm tra thư viện third-party đã hỗ trợ target framework.
- Xem property đã deprecated hoặc đổi tên.
- Chạy test trên target JDK và runtime.

### Không nâng JDK và Boot một cách mù quáng cùng lúc

Nếu dự án đang dùng JDK cũ, việc nâng JDK có thể tạo lỗi compiler/runtime riêng với lỗi framework migration. Có thể thực hiện theo các bước có kiểm soát:

1. Xác định target JDK được phiên bản Boot yêu cầu.
2. Nâng toolchain/build wrapper để compile được trên JDK đó.
3. Chạy test baseline trước khi đổi framework nếu có thể.
4. Nâng Boot và xử lý migration errors.
5. Sau khi ổn định mới tối ưu compiler flags/runtime options.

Một số migration bắt buộc phải kết hợp nhiều thay đổi, nhưng vẫn nên giữ commit/step đủ nhỏ để truy ra nguyên nhân.

## 11. Thay đổi logging: hiểu ba lớp API, bridge và implementation

Logging trong Java thường có nhiều lớp:

1. **Logging API/facade:** ứng dụng gọi API để ghi log, ví dụ SLF4J.
2. **Implementation/provider:** nơi thực sự ghi log, ví dụ Logback hoặc Log4j 2.
3. **Bridge:** chuyển lời gọi từ API logging khác sang facade/provider đang dùng.

Một sơ đồ:

~~~text
Application code
       |
       v
SLF4J API
       |
       v
SLF4J provider
       |
       +--> Logback
       |
       +--> Log4j 2 provider
       |
       +--> Provider khác
~~~

Các thư viện khác có thể gọi JUL, Commons Logging hoặc Log4j API. Bridge giúp gom những lời gọi đó về một logging implementation thống nhất.

### Tại sao logging hay lỗi sau nâng version?

- SLF4J API được nâng major nhưng provider cũ chưa tương thích.
- Có hai provider cùng nằm trên runtime classpath.
- Bridge và implementation tạo vòng chuyển tiếp.
- Starter logging mặc định vẫn tồn tại dù đã thêm Log4j 2.
- Một module kéo một version SLF4J riêng.
- Test runtime classpath khác application runtime classpath.

Triệu chứng có thể là warning không tìm thấy provider, nhiều binding/provider, log mất, log bị ghi hai lần hoặc startup failure do logging initialization.

## 12. SLF4J 1.7 và SLF4J 2.x: binding và provider

Trong SLF4J 1.7 và những thế hệ trước, implementation thường được phát hiện thông qua binding mechanism như:

~~~text
StaticLoggerBinder
~~~

Trong SLF4J 2.x, cơ chế provider được sử dụng, thường qua ServiceLoader:

~~~text
org.slf4j.spi.SLF4JServiceProvider
~~~

Vì vậy, khi nâng API SLF4J, cần nâng implementation/provider tương thích. Một binding cũ không tự trở thành provider 2.x.

### Không tự override slf4j-api

Nếu Spring Boot BOM đã quản lý SLF4J, thêm một version riêng chỉ vì một thư viện mới yêu cầu có thể làm runtime classpath không đồng bộ. Trước tiên xem release train Boot đích cung cấp version nào và library đó hỗ trợ version nào.

Nếu thật sự cần override, phải kiểm tra toàn bộ provider, bridge và logging modules có tương thích với API được chọn.

## 13. Giữ Logback mặc định hay chuyển sang Log4j 2?

Spring Boot thường cung cấp logging starter mặc định, trong đó Logback là implementation phổ biến. Nếu không có yêu cầu đặc biệt, giữ default thường là lựa chọn ít thay đổi nhất.

Nếu tổ chức chuẩn hóa Log4j 2 hoặc cần khả năng cụ thể, có thể thay implementation theo hướng dẫn Spring Boot.

Ví dụ Maven minh họa:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-log4j2</artifactId>
</dependency>
~~~

Trong ứng dụng web, dependency logging starter có thể đến qua nhiều starter. Cấu hình exclusion phải bao phủ dependency graph thực tế theo cách quản lý của dự án; ví dụ này chỉ minh họa việc thay default logging starter.

### Không thêm Log4j 2 mà vẫn để Logback provider hoạt động

Nếu cả Logback và Log4j 2 provider/binding cùng có trên classpath, SLF4J có thể phát hiện nhiều implementation. Hãy kiểm tra runtime dependency tree và loại implementation không được chọn.

### Log4j 2 API và provider không giống nhau

Một ứng dụng có thể có:

- `log4j-api`: API để code gọi.
- `log4j-core`: implementation của Log4j 2.
- `log4j-slf4j2-impl`: provider SLF4J 2.x cho Log4j 2.
- Bridge khác nhau cho JUL/Commons Logging/Log4j 1 API.

Không thêm tất cả chỉ vì tên có chữ Log4j. Chọn đúng provider và bridges theo logging architecture của ứng dụng.

## 14. Logging bridges: tránh vòng lặp

Bridge giúp đưa log từ API cũ về logging backend thống nhất, nhưng kết hợp sai có thể tạo loop.

Ví dụ về một chuỗi cần tránh:

~~~text
SLF4J
  |
  v
JUL bridge
  |
  v
JUL
  |
  v
SLF4J bridge
  |
  +---- quay lại SLF4J
~~~

Một số module bridge cụ thể có mục đích chuyển theo một chiều. Khi đặt cả hai chiều trên cùng classpath, log có thể lặp vô hạn hoặc gây lỗi runtime.

### Quy tắc kiểm tra

- Chọn một logging facade chính cho application code.
- Chọn một implementation/provider chính.
- Chỉ dùng bridge cần thiết cho thư viện gọi API khác.
- Không thêm bridge ngược chiều với bridge hiện có.
- Kiểm tra các logging starter transitively.
- Chạy test startup và xác nhận một log event được ghi đúng một lần.

### Log mất sau khi nâng cấp

Nếu ứng dụng start nhưng không thấy log:

1. Kiểm tra provider/binding tương thích với SLF4J API.
2. Kiểm tra provider có thực sự nằm trên runtime classpath không.
3. Kiểm tra configuration file được tìm thấy ở đâu.
4. Kiểm tra level/filter/appender.
5. Kiểm tra output đang đi tới stdout, file hay collector khác.
6. Kiểm tra bridge có chuyển log đúng chiều không.

Không nên đổi logging level sang TRACE trước khi xác nhận provider hoạt động.

## 15. Logging configuration cũng có thể thay đổi

Một số dự án có file:

~~~text
logback-spring.xml
logback.xml
log4j2-spring.xml
log4j2.xml
~~~

Khi thay backend, file cấu hình cũ không tự được chuyển đổi sang format mới. Ví dụ appender, encoder, rolling policy và property syntax của Logback khác Log4j 2.

Nếu chuyển Logback sang Log4j 2:

- Thay dependency/provider.
- Chuyển cấu hình appender/rolling.
- Kiểm tra profile-specific logging configuration.
- Kiểm tra environment property expansion.
- Kiểm tra async logging và shutdown.
- Xác nhận exception stack traces và MDC/context data.
- Kiểm tra test output và CI log capture.

### MDC và structured logging

SLF4J MDC có thể được sử dụng để gắn request ID, trace ID hoặc user-safe correlation data vào log. Khi thay backend/bridge, xác nhận MDC values được truyền qua thread/executor phù hợp và được format đúng.

Không đưa password, token hoặc dữ liệu nhạy cảm vào MDC. Logging migration là dịp kiểm tra cả policy dữ liệu, không chỉ syntax configuration.

## 16. Thay đổi starter logging theo cách có thể rollback

Không nên vừa nâng Boot, đổi provider, chuyển format JSON và sửa toàn bộ logging policy trong cùng một thay đổi lớn nếu không cần thiết.

Một trình tự rõ:

1. Nâng Boot với logging implementation mặc định trước nếu có thể.
2. Xác nhận startup và log cơ bản.
3. Nếu cần thay backend, tạo một thay đổi riêng.
4. Exclude default logging starter.
5. Thêm provider mới tương thích.
6. Chuyển config file.
7. Kiểm tra bridge và dependency graph.
8. Chạy integration tests và kiểm tra log thực tế.
9. Cập nhật tài liệu vận hành và container output.

Nếu lỗi xuất hiện sau bước 4, phạm vi điều tra hẹp hơn nhiều so với việc đổi tất cả cùng lúc.

## 17. Starter test chứa những gì?

`spring-boot-starter-test` là starter tiện ích cho test scope. Nó thường tích hợp những thư viện như:

- Spring Boot Test và Spring Test.
- JUnit Jupiter.
- AssertJ.
- Hamcrest.
- Mockito.
- JSON-related test utilities và những thư viện hỗ trợ khác theo phiên bản.

Danh sách chính xác có thể thay đổi theo Spring Boot release. Đừng giả định starter test của hai major versions có cùng dependency graph.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

### Không đưa test starter vào runtime

Test libraries nên ở test scope/configuration. Nếu thêm starter test vào runtime dependencies, ứng dụng có thể mang theo JUnit/Mockito và các thư viện chỉ phục vụ kiểm thử trong artifact deploy.

Kiểm tra scope sau migration, nhất là khi chuyển giữa Maven và Gradle hoặc refactor multi-module.

## 18. JUnit 4 và JUnit 5/Jupiter

Một migration thường gặp là từ JUnit 4 sang JUnit Jupiter.

JUnit 4:

~~~java
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.test.context.junit4.SpringRunner;

@RunWith(SpringRunner.class)
public class OrderServiceTest {

    @Test
    public void createsOrder() {
        // ...
    }
}
~~~

JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
class OrderServiceTest {

    @Test
    void createsOrder() {
        // ...
    }
}
~~~

Với `@SpringBootTest`, Spring Boot test annotation có thể tích hợp extension phù hợp nên không phải lúc nào cũng cần khai báo `@ExtendWith(SpringExtension.class)` tường minh.

### Thay đổi annotation phổ biến

| JUnit 4 | JUnit Jupiter |
|---|---|
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before` | `@BeforeEach` |
| `@After` | `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` |
| `@AfterClass` | `@AfterAll` |
| `@Ignore` | `@Disabled` |
| `@RunWith` | Extension model qua `@ExtendWith` |
| `@Rule` / `@ClassRule` | Extension APIs hoặc test lifecycle phù hợp |
| `Assert.assertEquals` | JUnit Jupiter Assertions hoặc AssertJ |

JUnit Jupiter mặc định không dùng cùng runner model của JUnit 4. Nếu một test cũ vẫn dựa trên JUnit 4, phải quyết định migrate hoặc giữ Vintage engine trong giai đoạn chuyển tiếp nếu phiên bản dependency stack còn hỗ trợ.

### Test không được phát hiện

Một test class có thể compile nhưng không được chạy nếu:

- Import nhầm `org.junit.Test` trong khi chỉ có Jupiter engine.
- Maven Surefire/Gradle test task chưa cấu hình phù hợp.
- Test method/class không đáp ứng discovery rules.
- Test engine dependency bị thiếu.
- CI dùng wrapper/build configuration khác local.

Kiểm tra số lượng test được phát hiện, không chỉ exit code build.

## 19. Mockito và Spring test annotations

Mockito được dùng để tạo mock cho dependency trong unit test:

~~~java
@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    InvoiceRepository repository;

    @InjectMocks
    InvoiceService service;

    @Test
    void loadsInvoice() {
        // ...
    }
}
~~~

Đây là unit test thuần Mockito, không cần Spring context.

Trong test Spring, có thể cần thay một bean trong context bằng mock. Các annotation hỗ trợ việc này đã thay đổi theo thế hệ Spring Boot/Spring Framework. Một số phiên bản Spring Boot mới giới thiệu API thay thế annotation mock bean cũ và đánh dấu annotation cũ deprecated.

### Không đổi annotation chỉ vì IDE gợi ý

Trước khi migrate:

1. Xác định version Spring Boot/Spring Test đang dùng.
2. Xem annotation hiện tại còn được hỗ trợ hay đã deprecated.
3. Kiểm tra API thay thế có trong version đích không.
4. Đọc semantics của mock/spy, bean override và reset.
5. Chạy lại context tests.

Ví dụ, trong những version có hỗ trợ `@MockitoBean`, có thể dùng API này để override bean trong test context:

~~~java
@SpringBootTest
class CheckoutIntegrationTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Test
    void usesConfiguredPaymentGateway() {
        // ...
    }
}
~~~

Đây là ví dụ theo phiên bản có API đó. Nếu version đích chưa có annotation này, cần dùng API được version hiện tại hỗ trợ; không copy annotation từ tài liệu của một release mới hơn.

### Mock trong unit test và mock trong Spring context test khác nhau

- `@Mock` tạo object mock thuần Mockito.
- `@InjectMocks` tạo object test và inject mocks theo quy tắc Mockito.
- Bean override annotation thay một bean trong Spring Test context.
- `@MockBean`/`@MockitoBean` có semantics gắn với Spring context và test framework.

Không thay mọi `@Mock` thành `@MockitoBean`. Làm vậy có thể biến unit test đơn giản thành context test chậm.

## 20. AssertJ và assertion API

Starter test thường đưa AssertJ vào test classpath. Một ví dụ:

~~~java
@Test
void calculatesTotal() {
    BigDecimal total = calculator.total(
            new BigDecimal("10.00"),
            new BigDecimal("5.00")
    );

    assertThat(total).isEqualByComparingTo("15.00");
}
~~~

AssertJ cung cấp fluent assertions, giúp test thể hiện điều mong đợi rõ ràng.

Nếu một dự án nâng version test stack, có thể gặp thay đổi API, generic inference hoặc overload resolution. Khi đó:

- Đọc compiler error đầy đủ.
- Kiểm tra static import.
- Xem method overload trong version mới.
- Tránh thay assertion bằng so sánh string chỉ để compile.
- Giữ semantics của assertion, đặc biệt với BigDecimal, collections và exceptions.

Ví dụ `BigDecimal.equals` phân biệt scale, còn `compareTo` so sánh giá trị số. Test cần chọn assertion đúng contract.

## 21. Spring test slices và starter changes

Spring Boot có các test slices để chỉ khởi tạo một phần application phù hợp với mục tiêu.

Ví dụ:

- `@WebMvcTest` cho MVC controller/web layer.
- `@DataJpaTest` cho JPA/persistence slice.
- `@JsonTest` cho JSON serialization.
- `@RestClientTest` cho REST client test scenarios.
- `@WebFluxTest` cho reactive web layer.

Khi nâng Boot, test slices có thể thay đổi auto-configurations được import hoặc cách mock bean được đăng ký. Một test trước đây pass có thể fail vì:

- Bean không còn nằm trong slice.
- Dependency được tách module.
- Auto-configuration condition thay đổi.
- Security filter chain được cấu hình khác.
- Jackson/module registration thay đổi.
- Một test annotation đã deprecated hoặc đổi semantics.

### Ví dụ @WebMvcTest

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        // Arrange mock và thực hiện request.
    }
}
~~~

Ví dụ dùng `@MockitoBean` chỉ phù hợp với version Spring Test có API này. Mục tiêu của slice là kiểm tra MVC layer, không khởi tạo database thật và toàn bộ service graph.

### Khi test slice fail sau upgrade

Đừng lập tức đổi thành `@SpringBootTest`. Trước tiên xem slice nào đang được nạp, bean nào bị loại, auto-configuration nào thay đổi và dependency nào cần mock. Chỉ mở rộng context nếu câu hỏi kiểm thử thực sự cần phạm vi rộng hơn.

## 22. Test runtime và build plugins

Một test framework có thể có trên classpath nhưng không được build tool phát hiện hoặc chạy đúng.

### Maven

Kiểm tra:

- Maven Surefire Plugin version được Boot parent quản lý hay override.
- JUnit Platform provider có phù hợp không.
- Test source naming convention.
- Test scope của dependencies.
- Profile build có vô tình skip test không.
- Failsafe có được dùng cho integration tests không.

Một lệnh thường dùng:

~~~bash
mvn test
~~~

Để xem chi tiết test execution:

~~~bash
mvn -DtrimStackTrace=false test
~~~

Cấu hình plugin riêng chỉ khi có yêu cầu. Nếu dùng Boot parent, trước tiên thử version plugin được quản lý.

### Gradle

Với Gradle:

~~~kotlin
tasks.test {
    useJUnitPlatform()
}
~~~

Sau đó:

~~~bash
./gradlew test
~~~

Kiểm tra:

- JUnit Platform được bật.
- Test source set nằm đúng module.
- Dependency thuộc `testImplementation`.
- Engine được đưa vào test runtime.
- Filter/tag không loại toàn bộ test.
- Gradle wrapper tương thích JDK/Boot plugin.

### Test compile không đồng nghĩa test đã chạy

Một pipeline có thể compile test source nhưng không discover bất kỳ test nào. CI cần hiển thị số lượng test được thực thi và fail nếu test count bất thường bằng cách phù hợp với quy trình dự án.

## 23. Testcontainers và integration dependencies

Nếu dự án dùng Testcontainers để kiểm thử PostgreSQL, Kafka hoặc Redis, nâng Boot có thể kéo theo thay đổi:

- Java baseline.
- JUnit integration module.
- Container image versions.
- Docker/Testcontainers API.
- Database driver.
- Spring Boot service connection support ở những phiên bản tương ứng.

Ví dụ Gradle:

~~~kotlin
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Version Testcontainers có thể được quản lý bằng BOM riêng hoặc dependency management phù hợp. Không nên nâng một module Testcontainers riêng lẻ mà bỏ qua các module liên quan.

### ServiceConnection và dynamic properties

Một số phiên bản Spring Boot cung cấp tích hợp `@ServiceConnection` cho Testcontainers. Những phiên bản cũ hơn thường dùng `@DynamicPropertySource` hoặc cơ chế property injection khác.

Ví dụ theo API có hỗ trợ:

~~~java
@Testcontainers
@SpringBootTest
class RepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");
}
~~~

Đây là ví dụ phụ thuộc version. Nếu Boot version chưa hỗ trợ annotation hoặc container type tương ứng, dùng cách cấu hình test properties được release đó hỗ trợ.

### Đừng nâng database image mà không kiểm tra compatibility

Testcontainers image version là một phần môi trường kiểm thử. PostgreSQL major version mới có thể thay đổi behavior hoặc migration assumptions. Giữ database test version tương ứng với môi trường deploy hoặc chủ động kiểm thử migration.

## 24. Module test trong multi-module project

Trong multi-module Maven, một module library có thể cần test dependencies nhưng không cần starter test ở runtime:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong Gradle:

~~~kotlin
dependencies {
    testImplementation(
        "org.springframework.boot:spring-boot-starter-test"
    )
}
~~~

Nếu module application phụ thuộc module library, test libraries của module library không nên bị kéo vào runtime của application.

### Dùng test fixtures có chủ đích

Nếu nhiều module cần test helper, có thể dùng test-fixtures feature của Gradle hoặc test utility module riêng. Không đưa test helper vào main source set chỉ để module khác import được.

Điều này tránh việc test-only implementation bị đóng gói vào production artifact.

### Kiểm tra module graph sau migration

- Module nào là executable application?
- Module nào chỉ là library?
- Boot plugin áp dụng ở đâu?
- Dependency management có nhất quán không?
- Test dependencies có bị export transitively không?
- Generated sources có được build đúng thứ tự không?
- Auto-configuration metadata nằm trong JAR module nào?

## 25. Dependency tree: công cụ thiết yếu khi nâng phiên bản

Sau khi đổi starter/module, hãy kiểm tra dependency graph thực tế.

### Maven

~~~bash
mvn dependency:tree
~~~

Lọc theo một thư viện:

~~~bash
mvn dependency:tree -Dincludes=org.slf4j
~~~

Xem dependency conflict và version được chọn, rồi xác định module nào kéo dependency đó.

### Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem một dependency cụ thể:

~~~bash
./gradlew dependencyInsight \
  --dependency slf4j-api \
  --configuration runtimeClasspath
~~~

Với test:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

### Runtime và test classpath có thể khác nhau

Một lỗi chỉ xuất hiện khi chạy test có thể đến từ test runtime graph, không phải application runtime. Ngược lại, test pass vì test scope cung cấp một implementation mà production artifact không có.

Vì vậy, xem đúng configuration:

- Maven compile/runtime/test scope.
- Gradle compileClasspath/runtimeClasspath/testRuntimeClasspath.
- Annotation processor path.
- Plugin classpath nếu lỗi xảy ra trong build plugin.

### Tìm duplicate implementations

Đối với logging, kiểm tra:

- SLF4J API version.
- Provider/binding.
- Logback.
- Log4j 2 provider.
- JUL/Commons Logging bridges.
- Những dependency kéo implementation transitive.

Không chỉ nhìn số lượng artifact có chữ "logging"; xác định vai trò của từng artifact trong graph.

## 26. Version conflict và dependency convergence

Một module có thể yêu cầu thư viện version A, module khác yêu cầu version B. Dependency management chọn một version theo quy tắc của build tool. Điều này có thể dẫn đến runtime mismatch.

Ví dụ:

~~~text
Application
   |
   +--> Starter A --> library-core 2.x
   |
   +--> Module B --> library-core 3.x
   |
   v
Resolved version
~~~

Nếu code compile với API version mới nhưng runtime dùng version cũ, có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.

### Cách xử lý

1. Xác định dependency bị conflict.
2. Tìm module trực tiếp/transitive đưa từng version vào.
3. Kiểm tra Boot BOM có quản lý artifact đó không.
4. Xem thư viện nào tương thích với target Boot.
5. Nâng module liên quan theo một release train phù hợp.
6. Chỉ override version khi có căn cứ.
7. Chạy test và kiểm tra runtime classpath.

### Không dùng force version để dập mọi conflict

Ép tất cả modules về version cao nhất có thể làm build qua nhưng runtime fail vì API incompatible. Dependency convergence là tín hiệu cần điều tra, không phải mục tiêu đạt được bằng mọi giá.

## 27. Thay đổi configuration properties và deprecated settings

Nâng version có thể làm một số property deprecated, đổi tên hoặc đổi semantics. Một property cũ có thể vẫn hoạt động trong giai đoạn chuyển tiếp rồi bị loại ở major release sau.

Ví dụ khái quát:

~~~yaml
spring:
  feature:
    old-option: true
~~~

Nếu release notes chỉ ra property mới, cần:

- Thay key bằng property mới.
- Kiểm tra giá trị/default có tương đương không.
- Kiểm tra profile-specific files.
- Kiểm tra environment variables map tới property mới.
- Xóa key cũ sau khi xác nhận không còn consumer.
- Cập nhật deployment manifests và Helm values.

Không nên suy luận property mới chỉ bằng cách đổi tên key. Semantics có thể đã thay đổi.

### Configuration metadata

IDE autocomplete có thể đọc metadata từ dependencies. Sau khi nâng starter, metadata mới giúp phát hiện property deprecated hoặc không còn tồn tại. Tuy nhiên, metadata không phải lúc nào cũng bao phủ custom properties và environment overrides.

Hãy dùng release notes, generated configuration metadata và startup warnings cùng nhau.

## 28. Security configuration khi nâng Spring Security

Một nâng cấp Boot có thể kéo theo Spring Security version mới. Cấu hình cũ có thể deprecated hoặc không compile nữa.

Ví dụ cấu hình hiện đại thường dùng bean `SecurityFilterChain`:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http
    ) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().authenticated()
                )
                .build();
    }
}
~~~

Đây là skeleton minh họa. Một ứng dụng thực còn cần authentication mechanism, CSRF policy, CORS, session strategy, OAuth2/resource server và endpoint rules phù hợp.

### Đừng sửa compile error bằng cách permitAll toàn bộ

Nếu một method API bị đổi, việc xóa rule hoặc mở rộng quyền truy cập để compile là thay đổi security behavior. Phải viết lại rule tương đương theo semantics mới và kiểm tra bằng security tests.

### Security test sau upgrade

- Anonymous request tới protected endpoint.
- Authenticated request với đúng role.
- User không đủ quyền.
- CSRF behavior cho state-changing requests.
- CORS/preflight nếu có browser client.
- OAuth2 token validation nếu dùng resource server.
- Actuator endpoint exposure và authorization.

## 29. Persistence module và Hibernate upgrade

Spring Boot quản lý Spring Data và Hibernate versions tương thích. Khi nâng, ORM major version có thể thay đổi:

- SQL generation.
- Type mapping.
- Dialect handling.
- Lazy loading/proxy behavior.
- Schema validation.
- Query parsing.
- Identifier generation.
- Transaction semantics hoặc API deprecations.

### Ví dụ: query behavior cần kiểm tra

Một repository method có thể compile nhưng SQL được generate khác hoặc query không còn hợp lệ. Vì vậy cần integration tests trên database phù hợp, không chỉ unit test repository interface.

### Kiểm tra schema migration

Nếu dùng Flyway hoặc Liquibase:

- Nâng version plugin/runtime library theo compatibility.
- Kiểm tra database driver.
- Chạy migration từ schema thực tế của production-like snapshot.
- Xác nhận Hibernate ddl-auto không vô tình thay đổi schema.
- Kiểm tra rollback/forward-only policy.
- Xác nhận migration chạy đúng một lần trong môi trường nhiều instance.

Không để migration test chỉ chạy trên một database in-memory nếu production dùng database engine có semantics khác biệt.

## 30. JSON serialization và Jackson module

Starter web thường kéo Jackson cho JSON. Khi version thay đổi, hãy kiểm tra:

- Date/time serialization.
- Enum handling.
- Null/missing properties.
- Polymorphic typing.
- Constructor/record deserialization.
- Custom serializers/deserializers.
- Java Time module.
- Naming strategy.
- Unknown property handling.

Một test JSON:

~~~java
@JsonTest
class OrderJsonTests {

    @Autowired
    JacksonTester<OrderResponse> json;

    @Test
    void serializesOrder() throws Exception {
        OrderResponse response =
                new OrderResponse("order-1", "PAID");

        assertThat(json.write(response))
                .extractingJsonPathStringValue("$.status")
                .isEqualTo("PAID");
    }
}
~~~

API và auto-configuration của JSON test slice cần tương ứng version Boot. Sau upgrade, chạy contract tests trên payload quan trọng để phát hiện thay đổi wire format.

### Không chỉ kiểm tra object Java

Một ứng dụng có thể deserialize/serialize object đúng trong unit test nhưng API contract vẫn thay đổi do property names, date format hoặc null handling. Hãy kiểm tra JSON thực tế mà client tiêu thụ.

## 31. Observability starter: metrics, tracing và logging

Một số hệ thống dùng Micrometer, tracing bridge, OpenTelemetry hoặc Actuator. Nâng Boot có thể thay đổi version hoặc integration module.

Kiểm tra:

- Meter registry được chọn.
- Tracing bridge và exporter.
- Observation conventions.
- Propagation format.
- Correlation IDs.
- Actuator endpoint exposure.
- Health contributors.
- Log correlation/MDC.

Đặc biệt, tránh đưa hai tracing bridges cùng chức năng vào classpath nếu chúng tạo instrumentation trùng lặp.

### Metrics name/tag có thể là contract vận hành

Dashboard, alert và SLO có thể phụ thuộc metric names/tags. Một nâng cấp thư viện có thể đổi naming convention hoặc histogram configuration. Kiểm tra dashboard và alert queries cùng với code.

## 32. Maven/Gradle plugin cũng cần nâng tương thích

Spring Boot build plugin có thể hỗ trợ:

- Repackage executable JAR/WAR.
- Build OCI image.
- AOT processing.
- Native image workflows.
- Build metadata và layered archive.

Khi nâng Boot, nên để plugin cùng release train nếu không có lý do cụ thể để pin version khác.

### Maven plugin

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu dùng Boot parent, plugin version thường được quản lý. Nếu chỉ import BOM, plugin version có thể cần khai báo riêng.

### Gradle plugin

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}
~~~

Không copy version plugin từ tutorial mà không xác nhận tương thích Gradle wrapper, Java và Boot.

### Wrapper là một phần của build

Commit Maven Wrapper hoặc Gradle Wrapper để developer và CI dùng cùng build engine version. Nâng JDK mà quên wrapper có thể gây lỗi build độc lập với code Spring.

## 33. Một quy trình nâng cấp theo từng bước

Một quy trình có thể kiểm soát:

~~~text
1. Ghi nhận baseline
       |
       v
2. Chọn target Boot/JDK/build tool
       |
       v
3. Đọc migration guide và release notes
       |
       v
4. Nâng parent/BOM/plugin
       |
       v
5. Resolve starter và dependency graph
       |
       v
6. Sửa source/module/API migration
       |
       v
7. Chốt logging provider/bridges
       |
       v
8. Nâng và sửa test tooling
       |
       v
9. Chạy tests theo tầng
       |
       v
10. Smoke test artifact/runtime
       |
       v
11. Cập nhật CI và deployment
       |
       v
12. Phát hành có rollback plan
~~~

### Bước 1: ghi nhận baseline

Trước khi sửa, lưu:

- Kết quả build/test hiện tại.
- Dependency tree.
- Java version.
- Maven/Gradle wrapper version.
- Startup logs.
- Logging backend.
- Các test được discover.
- Artifact size và startup behavior nếu quan trọng.

Baseline giúp biết lỗi nào đã tồn tại trước khi nâng.

### Bước 2: chọn target rõ ràng

Không dùng một range version mơ hồ. Chọn release cụ thể và xác nhận hỗ trợ JDK/build tool.

### Bước 3: đọc migration guide

Tập trung vào breaking changes có liên quan dependency thực tế của dự án. Không cần áp dụng mọi hướng dẫn cho module mà dự án không sử dụng.

### Bước 4: thay Boot version

Sửa parent/BOM/plugin version ở đúng nơi quản lý tập trung. Với multi-module, tránh khai báo một Boot version khác nhau ở từng module.

### Bước 5: build để nhận lỗi compile

Compile errors thường chỉ ra API/package đã thay đổi. Xử lý từng nhóm thay vì suppress warning hoặc loại dependency hàng loạt.

### Bước 6: chạy test và kiểm tra runtime

Một build thành công chỉ xác nhận compilation/packaging. Test startup, logging, persistence, web và external integrations mới xác nhận behavior.

## 34. Chiến lược nâng cấp nhiều major releases

Nếu dự án đi qua nhiều major versions, thường dễ kiểm soát hơn khi nâng tuần tự qua các mốc migration được hỗ trợ, thay vì nhảy qua nhiều release train mà không kiểm tra thay đổi trung gian.

Ví dụ khái quát:

~~~text
Current release
      |
      v
Intermediate supported release
      |
      v
Target major release
      |
      v
Resolve migration warnings/errors
      |
      v
Final validation
~~~

Không phải mọi dự án đều bắt buộc cài đặt và deploy từng intermediate release. Nhưng cần đọc migration notes của những mốc liên quan để không bỏ qua một property, package hoặc plugin change đã bị loại bỏ ở phiên bản cuối.

### Không giữ nhiều compatibility hacks vĩnh viễn

Trong giai đoạn chuyển tiếp có thể cần adapter hoặc bridge tạm thời. Hãy ghi rõ lý do và thời điểm loại bỏ, tránh để dự án mang cả API cũ và mới vô thời hạn.

## 35. Test matrix sau khi nâng

Một test matrix tối thiểu có thể gồm:

| Tầng | Điều cần xác nhận |
|---|---|
| Compile | Source và annotation processing tương thích |
| Unit tests | Business logic không đổi |
| Context tests | Bean wiring, conditions, lifecycle |
| Web slice | Controller, serialization, security |
| Persistence slice | JPA mappings, repositories, transaction |
| Logging | Provider duy nhất, output và levels đúng |
| Integration tests | DB, broker, external client |
| Packaging | Executable JAR/WAR và manifest |
| Container smoke | Image start, port, health, signal |
| CI | Test discovery, reports, artifact publication |

Không nhất thiết mỗi commit phải chạy toàn bộ test matrix. Nhưng trước khi phát hành target version, cần có bằng chứng phù hợp với các integration thực sự được dùng.

### Test count là một tín hiệu quan trọng

Sau khi nâng JUnit/Surefire/Gradle, so sánh số test được discover với baseline. Nếu trước có 800 tests mà sau upgrade chỉ chạy 0 hoặc 120, build có thể vẫn exit 0 tùy cấu hình nhưng test suite không còn bảo vệ đầy đủ.

Kiểm tra reports và build logs, không chỉ nhìn chữ BUILD SUCCESSFUL.

## 36. Troubleshooting: starter mới gây thiếu bean

Triệu chứng:

~~~text
No qualifying bean of type 'ExampleClient' available
~~~

Các khả năng:

- Starter cung cấp bean đã đổi artifact.
- Auto-configuration không còn được import.
- Optional dependency không có trên classpath.
- Property condition không match.
- User configuration không được scan/import.
- Module mới chỉ cung cấp API nhưng implementation nằm trong starter khác.

Cách xử lý:

1. Kiểm tra dependency tree.
2. Xác định class và module chứa implementation.
3. Kiểm tra imports metadata của auto-configuration.
4. Bật condition evaluation report.
5. Kiểm tra property/profile.
6. Viết test context nhỏ cho auto-configuration.
7. Xác nhận JAR module được đóng gói đúng.

Không thêm component scan rộng trước khi biết bean được cung cấp từ đâu.

## 37. Troubleshooting: logging provider/binding bị trùng

Triệu chứng có thể gồm:

~~~text
Class path contains multiple SLF4J providers
~~~

hoặc warning về binding/provider không tương thích.

Cách xử lý:

1. Xem `runtimeClasspath` hoặc Maven dependency tree.
2. Tìm provider thực tế và version.
3. Kiểm tra starter logging mặc định còn tồn tại không.
4. Kiểm tra provider mới tương thích SLF4J API version không.
5. Kiểm tra bridge hai chiều.
6. Loại implementation thừa ở đúng dependency path.
7. Chạy ứng dụng và xác nhận log được ghi đúng một lần.

Đừng loại `slf4j-api` chỉ vì thấy nó trong graph. API thường là contract mà thư viện application sử dụng; vấn đề thường nằm ở provider/binding hoặc bridge.

## 38. Troubleshooting: JUnit test không chạy

Triệu chứng:

- Build báo thành công nhưng test count bằng 0.
- Test compile nhưng không được discover.
- Một số test JUnit 4 không chạy sau khi bỏ Vintage.
- Test chạy trong IDE nhưng không chạy trong CI.

Cách xử lý:

- Kiểm tra import annotation `@Test`.
- Kiểm tra JUnit engine trên test runtime.
- Kiểm tra Surefire/Gradle test configuration.
- Kiểm tra naming convention và test filters.
- Kiểm tra profile/skip flags.
- So sánh wrapper và JDK giữa local/CI.
- Đọc test reports.

Không chuyển test sang source folder khác chỉ để build tool tìm thấy nếu nguyên nhân là thiếu engine.

## 39. Troubleshooting: NoSuchMethodError sau nâng

`NoSuchMethodError` thường là dấu hiệu runtime đã nạp class version không có method mà code đang gọi.

Các nguyên nhân:

- Compile với version mới nhưng runtime resolve version cũ.
- Một dependency transitive override version do BOM quản lý.
- Module nội bộ build bằng API khác release train.
- Classpath có nhiều version và thứ tự resolution không như dự kiến.

Cách xử lý:

1. Tìm class trong exception.
2. Xác định artifact chứa class.
3. Xem dependency tree/insight.
4. Kiểm tra version được compile và version runtime.
5. Gỡ override không cần thiết hoặc nâng module phụ thuộc.
6. Rebuild toàn bộ multi-module để tránh dùng artifact cũ.

Đừng chỉ thêm một JAR version mới vào runtime nếu build tool vẫn chọn version khác ở nơi khác.

## 40. Troubleshooting: BeanCreationException sau nâng

Sau khi nâng Boot, startup có thể fail do:

- API đổi package.
- Auto-configuration condition thay đổi.
- Property bị deprecated/removed.
- Bean mặc định đổi hoặc bị tách module.
- Logging provider conflict.
- Hibernate mapping/query behavior.
- Validation provider thiếu.
- Dependency version mismatch.
- Security configuration không còn hợp lệ.

Cách điều tra:

1. Đọc bean name và nested cause.
2. Xác định dependency được tạo từ module/starter nào.
3. Kiểm tra release notes liên quan.
4. Kiểm tra property và active profile.
5. Dùng condition report nếu bean không được đăng ký.
6. Kiểm tra dependency tree nếu class/API không tương thích.
7. Viết context test để khóa behavior mong muốn.

Một exception container không tự chứng minh Spring Boot version bị lỗi; thường cần tìm dependency hoặc configuration cụ thể đã thay đổi.

## 41. Quản lý deprecation và removal

Deprecation warning là tín hiệu migration, không phải noise nên xóa bằng cách tắt warning.

Khi gặp API deprecated:

1. Tìm API thay thế trong version đích.
2. Xem deprecation note và planned removal.
3. Kiểm tra semantics, không chỉ tên method.
4. Chuyển test để xác nhận behavior.
5. Xóa adapter cũ khi toàn bộ callers đã migrate.

Nếu một thư viện bên thứ ba phát warning, kiểm tra version mới tương thích thay vì tự fork/suppress toàn bộ warning.

### Không nâng dependency chỉ vì có version mới nhất

Phiên bản mới nhất của một library không nhất thiết tương thích với Boot release đang dùng. Ưu tiên dependency management và compatibility information của nền tảng.

## 42. Cập nhật CI/CD sau khi nâng

Nâng version trong source nhưng CI vẫn dùng JDK/wrapper cũ sẽ tạo khác biệt local/CI.

Kiểm tra:

- JDK distribution và version.
- Maven/Gradle wrapper.
- Build cache.
- Environment variables.
- Testcontainers/Docker availability.
- Native toolchain nếu có.
- Artifact packaging task.
- Image builder và registry access.
- Test report upload.
- Dependency vulnerability scanning.
- Deployment runtime base image.

### Build matrix nếu hỗ trợ nhiều JDK

Nếu ứng dụng cam kết chạy trên nhiều JDK, CI nên kiểm tra các version được hỗ trợ. Nhưng build JDK và runtime JDK có thể khác nhau trong một số quy trình; ghi rõ toolchain target và runtime support.

### Không để CI dùng dependency cache cũ để che lỗi

Sau khi thay BOM/starter, build cache có thể khiến việc điều tra khó hơn. Dùng clean/reproducible build khi cần xác nhận migration, nhưng không xóa cache toàn bộ máy một cách vô tội vạ nếu không có dấu hiệu cache corruption.

## 43. Cập nhật tài liệu và module contracts

Sau migration, cập nhật:

- Java/Boot version trong README và build documentation.
- Starter dependencies mà module cung cấp.
- Public APIs và package imports.
- Logging backend và file configuration.
- Test framework conventions.
- Cách chạy unit/integration tests.
- Các profile/configuration properties.
- Hướng dẫn local development.
- Base image/runtime version.
- Known limitations và deprecation cleanup.

Nếu module nội bộ là starter cho nhiều ứng dụng, ghi rõ:

- Dependency nào là API contract.
- Dependency nào là implementation detail.
- Bean mặc định nào có thể override.
- Properties nào được hỗ trợ.
- Logging provider nào được kỳ vọng.
- Test utilities nào chỉ dành cho test scope.

Một module không có contract rõ ràng sẽ khiến mỗi ứng dụng consumer phải tự suy đoán khi nâng version.

## 44. Một ví dụ migration Maven có kiểm soát

Giả sử một ứng dụng có web, JPA, security, logging mặc định và test starter.

POM khái quát:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

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
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Version `3.x.y` là placeholder. Dự án phải dùng một release cụ thể được chọn sau khi kiểm tra compatibility.

Quy trình:

1. Cập nhật parent version.
2. Kiểm tra Java toolchain.
3. Chạy dependency tree.
4. Compile và xử lý Jakarta/API changes nếu thuộc migration.
5. Chạy unit tests.
6. Chạy context/web/JPA/security tests.
7. Kiểm tra logging provider.
8. Package executable JAR.
9. Chạy smoke test bằng JAR.
10. Cập nhật CI/runtime image.

Không cần thêm version cho từng starter nếu Boot parent đang quản lý chúng.

## 45. Một ví dụ migration Gradle có kiểm soát

Kotlin DSL minh họa:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Một lần nữa, version ở đây là placeholder. Cần chọn plugin version tương thích với wrapper và Boot release.

Chạy:

~~~bash
./gradlew clean test
./gradlew bootJar
~~~

Sau đó xem:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Mục tiêu là xác nhận application runtime và test runtime có đúng modules/provider/engines mong muốn.

## 46. Cách giữ thay đổi dễ review

Một migration thường có nhiều thay đổi. Có thể chia theo chủ đề:

| Nhóm thay đổi | Nội dung |
|---|---|
| Build baseline | Boot parent/BOM, JDK, wrapper, plugin |
| Source migration | Jakarta imports, API deprecations |
| Starter/module | Thêm/xóa/đổi starter, auto-configuration metadata |
| Logging | Provider, bridge, configuration |
| Testing | JUnit/Mockito/Spring Test, test discovery |
| Runtime integration | Hibernate, database driver, security, metrics |
| CI/deployment | JDK image, build tasks, health/smoke tests |

Chia commit theo nhóm giúp reviewer xác định nguyên nhân khi một test hoặc runtime behavior thay đổi. Nếu buộc phải làm một commit lớn, ít nhất ghi lại dependency graph và test results theo nhóm.

### Không thay behavior nghiệp vụ ngoài mục tiêu migration

Một migration nên giữ behavior của ứng dụng ổn định, trừ khi có yêu cầu thay đổi rõ ràng. Nếu đồng thời sửa business logic, rất khó biết regression đến từ version upgrade hay feature change.

## 47. Lựa chọn chiến lược khi thay logging hoặc test tool

Không phải mọi thay đổi đều cần thực hiện ngay khi nâng Boot.

| Thay đổi | Khi nào nên làm cùng migration? | Khi nào nên tách riêng? |
|---|---|---|
| Nâng SLF4J/provider do Boot quản lý | Khi dependency compatibility yêu cầu | Khi chỉ muốn đổi backend/format |
| Chuyển Logback sang Log4j 2 | Khi target platform bắt buộc | Khi là thay đổi kiến trúc logging độc lập |
| JUnit 4 sang Jupiter | Khi engine/API cũ không còn hỗ trợ | Khi có thể giữ Vintage trong giai đoạn chuyển tiếp |
| Mockito annotation mới | Khi API cũ bị loại bỏ | Khi chỉ là cleanup deprecation |
| Tách module nội bộ | Khi module API/metadata bắt buộc đổi | Khi refactor kiến trúc độc lập với version |
| Thay Hibernate major | Khi Boot target kéo theo major đó | Khi schema/data migration cần kế hoạch riêng |

### Giữ migration scope đủ nhỏ

Một nâng cấp nền tảng đã có rủi ro riêng. Không cần kết hợp đổi backend logging, chuyển JUnit, tách module và viết lại security trong một đợt nếu không có dependency bắt buộc.

Nhưng nếu target Boot đã loại bỏ API cũ, cần hoàn tất migration liên quan trước khi coi nâng cấp thành công.

## 48. Những sai lầm thường gặp

### Nâng riêng spring-core hoặc spring-context

Điều này có thể làm lệch version Spring Framework mà Boot đã quản lý. Ưu tiên nâng Boot release train hoặc dùng override có căn cứ rõ ràng.

### Giữ starter cũ sau khi capability đã được tách

Có thể kéo dependency thừa hoặc kích hoạt auto-configuration không mong muốn. Kiểm tra release notes và dependency tree.

### Thêm provider mới nhưng quên loại provider cũ

Có thể gây multiple-provider warnings hoặc logging behavior không xác định.

### Chuyển mọi test sang Spring context

Unit test thuần không cần Spring. Chỉ dùng context khi test thật sự cần DI, conditions hoặc framework integration.

### Xóa JUnit 4 nhưng còn test import JUnit 4

Test có thể compile/run sai hoặc không được discover nếu engine không còn.

### Nâng Mockito mà không kiểm tra Spring mock annotations

Một số API mock-bean thuộc Spring Test, không phải annotation Mockito thuần. Kiểm tra version và semantics trước khi thay.

### Chỉ chạy compile

Compile không phát hiện hết bean initialization, SQL behavior, logging configuration, test discovery hoặc container runtime errors.

### Ép version để dependency tree hết conflict

Build có thể pass nhưng runtime API mismatch. Phải kiểm tra compatibility, không chỉ số version.

### Tắt validation/security để context khởi động

Đây là thay đổi behavior và có thể làm giảm an toàn. Tìm nguyên nhân cấu hình hoặc API migration thực tế.

### Không kiểm tra artifact cuối

Test classpath có thể khác runtime artifact. Hãy chạy executable JAR/image hoặc native artifact theo đúng mục tiêu deploy.

## 49. Checklist trước khi hoàn tất nâng phiên bản

1. **Chốt target release.** Boot, Java, Maven/Gradle wrapper và plugin có tương thích không?
2. **Đọc migration guide.** Xác định breaking changes liên quan codebase.
3. **Kiểm tra dependency management.** Parent/BOM là nguồn version rõ ràng.
4. **Rà starter graph.** Starter nào đổi, tách hoặc không còn cần thiết?
5. **Rà module boundaries.** Application module và library module có vai trò đúng?
6. **Kiểm tra auto-configuration metadata.** Imports, conditions và ordering có đúng?
7. **Kiểm tra Jakarta/API migration.** Chỉ đổi namespace thuộc API đã chuyển.
8. **Kiểm tra logging stack.** Một provider, bridges đúng chiều, config tương thích.
9. **Kiểm tra test starter.** Test libraries ở đúng test scope.
10. **Kiểm tra JUnit engine.** Test discovery và số test thực thi đúng.
11. **Kiểm tra Mockito/Spring mocks.** Annotation tương thích version và đúng loại test.
12. **Kiểm tra test slices.** MVC, JPA, JSON, client và security behavior.
13. **Kiểm tra dependency tree.** Runtime và test classpaths không lệch ngoài ý muốn.
14. **Kiểm tra configuration properties.** Deprecated keys, binding, validation và profiles.
15. **Kiểm tra Hibernate/database.** Mapping, SQL, migrations và driver.
16. **Kiểm tra security.** Authentication, authorization, CSRF, CORS và actuator.
17. **Chạy integration tests.** External services dùng container/fakes phù hợp.
18. **Kiểm tra packaging.** JAR/image chứa đúng dependencies và launcher.
19. **Cập nhật CI/CD.** JDK, wrapper, build cache, test reports và artifact scans.
20. **Ghi lại kết quả.** Version, dependency changes, tests và rollback path.

## Kết luận

Nâng phiên bản Spring Boot là thay đổi một **release train**, không chỉ sửa một dòng version. Starter quyết định nhóm capability được đưa vào classpath; BOM/parent quản lý những version tương thích; module boundaries quyết định nơi cấu hình và auto-configuration được đăng ký; logging API/provider/bridges quyết định log được xử lý thế nào; còn test starter và build plugins quyết định test có được compile, discover và chạy đúng hay không.

Một quy trình migration vững chắc bắt đầu bằng việc chọn target Boot/JDK/build tool, đọc release notes, cập nhật dependency management và kiểm tra dependency graph. Sau đó xử lý source/API changes, starter/module metadata, logging provider và test tooling theo từng nhóm. Cuối cùng, chạy test theo tầng, xác nhận số test được thực thi, kiểm tra runtime classpath và smoke test artifact thực sự được phát hành.

Khi giữ rõ ranh giới giữa **starter, module, logging stack và test stack**, developer có thể nâng nền tảng với phạm vi thay đổi dễ hiểu, phát hiện dependency conflict sớm và giảm nguy cơ một build thành công nhưng ứng dụng production lại mất log, thiếu bean hoặc bỏ sót toàn bộ test suite.
