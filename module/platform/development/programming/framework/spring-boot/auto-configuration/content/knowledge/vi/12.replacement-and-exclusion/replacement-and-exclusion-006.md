# Loại trừ một cấu hình không đồng nghĩa loại dependency khỏi classpath

## 1. Mục tiêu bài học và vấn đề thường gặp

Trong Spring Boot, người phát triển có thể viết:

```java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
}
```

Sau đó thấy ứng dụng không còn tự tạo `DataSource` và kết luận: “Spring Boot đã gỡ JDBC driver, thư viện JDBC hoặc các JAR liên quan”. **Kết luận này sai.** Annotation trên chỉ yêu cầu Spring Boot **không áp dụng một lớp auto-configuration cụ thể** qua cơ chế tự cấu hình; nó **không chỉnh sửa dependency graph của Maven/Gradle, không xóa JAR khỏi runtime classpath và không xóa class khỏi package ứng dụng**.

Đây là bài về **thay thế và loại trừ auto-configuration**. Bạn sẽ biết cách xác định đang can thiệp vào tầng nào, chọn công cụ đúng mục tiêu, kiểm tra class/bean/dependency độc lập, và tránh nhầm lẫn khi debug hoặc xử lý một thư viện không mong muốn.

Sau khi học, bạn cần trả lời được bốn câu hỏi:

1. “Thư viện có còn trên **classpath** không?” → xem dependency graph và class loading.
2. “Lớp **auto-configuration** có được Spring Boot áp dụng không?” → xem exclude và condition report.
3. “Có **bean** mang tên/kiểu đó trong `ApplicationContext` không?” → xem bean definitions/condition, kể cả bean do ứng dụng định nghĩa.
4. “JAR có còn trong **artifact được đóng gói/deploy** không?” → xem nội dung artifact và dependency runtime.

Bốn câu hỏi này liên quan nhưng **không đồng nhất**. Một thư viện có thể tồn tại trên classpath mà không có bean nào được tạo từ nó; một bean vẫn có thể tồn tại dù một auto-configuration cụ thể đã bị loại trừ, vì bean có thể được định nghĩa theo cách khác.

## 2. Ba tầng cần phân biệt

### 2.1. Dependency graph và classpath

`Maven` hoặc `Gradle` quyết định các artifact và thư viện trực tiếp/chuyển tiếp được đưa vào lúc biên dịch, chạy thử, chạy ứng dụng và đóng gói. Với một ứng dụng dùng `spring-boot-starter-jdbc`, dependency graph thường có:

- `spring-jdbc`, chứa các API như `org.springframework.jdbc.core.JdbcTemplate`;
- một JDBC connection pool, chẳng hạn `HikariCP` từ starter;
- những dependency Spring và Boot cần cho ứng dụng.

Classpath là tập class/resource mà một class loader có thể nhìn thấy khi chạy. **Tắt auto-configuration không thay đổi dependency graph của quá trình build**. Nếu JAR `spring-jdbc` vẫn được resolve cho runtime, class `JdbcTemplate` vẫn có thể tải được.

Lưu ý: có dependency trong file build chưa đủ để khẳng định nó nằm trong **runtime** classpath; cần kiểm tra scope/configuration, dependency resolution, packaging và môi trường deploy. Ngược lại, bỏ một khai báo dependency trực tiếp chưa chắc loại được artifact nếu dependency đó đi vào qua nhánh chuyển tiếp khác.

### 2.2. Lớp auto-configuration

Một lớp có `@AutoConfiguration` thường được Spring Boot phát hiện dưới dạng ứng viên qua:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Việc một lớp auto-configuration **được liệt kê trong một JAR** không đảm bảo nó sẽ được áp dụng. Spring Boot còn xét cơ chế exclude, điều kiện (`@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnProperty`, v.v.) và những yếu tố liên quan khác.

Khi exclude `DataSourceAutoConfiguration`, bạn tác động vào **danh sách auto-configuration được nhập vào context**. Mã `DataSourceAutoConfiguration` vẫn có thể tồn tại bên trong `spring-boot-autoconfigure` và các thư viện JDBC vẫn có thể nằm trên classpath.

### 2.3. Bean definition và instance trong ApplicationContext

`@Bean`, `@Component`, `@Import` và auto-configuration có thể tạo định nghĩa bean. Khi một auto-configuration bị loại trừ, **những bean mà chỉ auto-configuration đó chịu trách nhiệm đăng ký sẽ không được đăng ký qua đường nhập tự động ấy**.

Tuy nhiên:

- Bean do người dùng khai báo qua `@Bean` hoặc component scanning vẫn có thể tồn tại.
- Một auto-configuration **khác** chưa bị exclude vẫn có thể đăng ký bean thuộc cùng thư viện, nếu điều kiện của nó thỏa.
- Nếu người dùng tự tạo `DataSource`, một auto-configuration khác như `JdbcTemplateAutoConfiguration` có thể tiếp tục tạo `JdbcTemplate`, dù `DataSourceAutoConfiguration` đã bị loại trừ.
- Việc class có trên classpath không đồng nghĩa có bean cùng kiểu; việc có bean không bắt buộc phải bắt nguồn từ auto-configuration mặc định.

Bởi vậy không được suy luận “exclude `DataSourceAutoConfiguration` ⇒ hoàn toàn không thể có `DataSource` hoặc `JdbcTemplate`”.

## 3. Bảng đối chiếu: exclude cấu hình với gỡ dependency

| Hành động | Tác động chính | JAR/class trên classpath | Ảnh hưởng bean |
| --- | --- | --- | --- |
| `@SpringBootApplication(exclude = X.class)` | Ngăn Spring Boot tự nhập auto-configuration `X` | **Không tự thay đổi** | Bean chỉ do X tự đăng ký không được tạo qua X; bean khác vẫn có thể xuất hiện |
| `@SpringBootApplication(excludeName = "fully.qualified.X")` | Như trên, dùng tên lớp dạng chuỗi | **Không tự thay đổi** | Như trên |
| `spring.autoconfigure.exclude=...` | Đặt danh sách auto-configuration không được áp dụng bằng cấu hình | **Không tự thay đổi** | Như trên |
| `@ConditionalOnProperty` không khớp | Làm một đoạn cấu hình/bean chịu điều kiện không được đăng ký | **Không tự thay đổi** | Chỉ tác động phần được gắn điều kiện |
| Bỏ một dependency khai báo từ `pom.xml`/`build.gradle` | Thay đổi đầu vào dependency resolution | **Có thể thay đổi** nếu không còn đường phụ thuộc khác | Các auto-configuration dựa vào class bị mất có thể không khớp; mã đang cần class có thể lỗi |
| Maven `<exclusions>` hoặc Gradle dependency `exclude` | Loại artifact chuyển tiếp trên nhánh khai báo tương ứng | **Có thể thay đổi**; phải kiểm tra graph cuối | Có thể ảnh hưởng condition và khả năng chạy; không trực tiếp ra lệnh loại một auto-configuration |

**Từ khóa:** *Exclude auto-configuration* là hành động tại **thời điểm Spring Boot xây dựng context**; *exclude dependency* là hành động của **build tool khi giải quyết dependency**. Chúng có thể được dùng cùng nhau nhưng phục vụ hai mục đích khác nhau.

## 4. Ba cách loại trừ auto-configuration trong Spring Boot 3.3

Ví dụ chọn `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration` làm lớp cần loại trừ. Đây là tên auto-configuration của Spring Boot 3.3; khi dùng phiên bản Boot khác, luôn xác minh package/class thực tế.

### 4.1. Qua `@SpringBootApplication(exclude = ...)`

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
}
```

Cách này phù hợp khi class đích có thể được tham chiếu tại thời điểm biên dịch. Nó không thao tác với `pom.xml` hoặc `build.gradle`.

### 4.2. Qua `excludeName`

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class DemoApplication {
}
```

`excludeName` dùng **tên lớp Java đầy đủ**, giúp không phải tham chiếu kiểu class đó trực tiếp trong source. Điều này hữu ích khi muốn duy trì source tương thích với những tổ hợp dependency mà class đích có thể vắng mặt.

**Phân biệt:** `excludeName` cần **tên lớp auto-configuration**, không phải tên bean (`dataSource`), module Gradle, artifact Maven (`spring-boot-starter-jdbc`) hay tên package chung (`org.springframework.jdbc`).

### 4.3. Qua cấu hình ứng dụng

Trong `application.properties`:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Hoặc trong `application.yml`:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Nếu dự án cần loại trừ nhiều lớp, khai báo danh sách theo định dạng cấu hình phù hợp. Tùy chọn này có thể được điều chỉnh theo môi trường triển khai mà không cần đổi annotation trong source.

Trong ứng dụng dùng `@EnableAutoConfiguration` trực tiếp thay cho `@SpringBootApplication`, các thuộc tính `exclude` và `excludeName` cũng tồn tại trên annotation đó.

**Lưu ý về phạm vi:** cả ba cách chỉ nhắm đến những **auto-configuration class hợp lệ** được quản lý bởi cơ chế nhập auto-configuration. Không dùng `exclude` để chặn một `@Configuration` bất kỳ do ứng dụng chủ động `@Import` hoặc một `@Component` được component scan. Nếu khai báo một lớp không phải auto-configuration có mặt trên classpath vào danh sách exclude, Spring Boot có thể báo lỗi loại trừ không hợp lệ. Hãy tìm đúng class trong condition report và tài liệu phiên bản đang chạy.

## 5. Ví dụ Java 17+ chạy độc lập: class còn, auto-configuration bị tắt

Ta tạo ứng dụng Spring Boot 3.3.13 dùng `spring-boot-starter-jdbc` để chắc chắn có `JdbcTemplate` và `HikariDataSource` trên runtime classpath. Đồng thời, ta loại trừ `DataSourceAutoConfiguration`, giữ một bean do người dùng khai báo để minh họa việc exclude **không xóa các bean khác**.

### 5.1. Cấu trúc thư mục

```text
classpath-vs-autoconfig/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ClasspathVsAutoConfig.java
```

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

    <groupId>demo</groupId>
    <artifactId>classpath-vs-autoconfig</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- JDBC API + Spring JDBC + HikariCP và những dependency cần thiết -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
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

Starter JDBC mang các thư viện JDBC vào quá trình giải quyết dependency. Việc loại trừ auto-configuration bên dưới **không can thiệp** khối `<dependencies>` này.

### 5.3. `src/main/java/demo/ClasspathVsAutoConfig.java`

```java
package demo;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ClasspathVsAutoConfig {

    // Bean do ứng dụng chủ động khai báo, không phụ thuộc vào
    // việc DataSourceAutoConfiguration có bị exclude hay không.
    @Bean
    String manualMessage() {
        return "still here";
    }

    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(ClasspathVsAutoConfig.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ClassLoader loader = ClasspathVsAutoConfig.class.getClassLoader();

            boolean jdbcClass = ClassUtils.isPresent(
                "org.springframework.jdbc.core.JdbcTemplate", loader
            );
            boolean poolClass = ClassUtils.isPresent(
                "com.zaxxer.hikari.HikariDataSource", loader
            );
            boolean autoConfigurationClass = ClassUtils.isPresent(
                "org.springframework.boot.autoconfigure.jdbc"
                    + ".DataSourceAutoConfiguration",
                loader
            );

            System.out.println("jdbcTemplateClass=" + jdbcClass);
            System.out.println("hikariClass=" + poolClass);
            System.out.println(
                "dataSourceAutoConfigurationClass=" + autoConfigurationClass
            );
            System.out.println(
                "dataSourceBean=" + context.containsBean("dataSource")
            );
            System.out.println(
                "jdbcTemplateBean=" + context.containsBean("jdbcTemplate")
            );
            System.out.println(
                "manualMessageBean=" + context.containsBean("manualMessage")
            );
        }
    }
}
```

**Yêu cầu:** JDK 17+, Maven và quyền tải dependencies. Từ thư mục `classpath-vs-autoconfig` chạy:

```bash
mvn -q spring-boot:run
```

**Sáu dòng được chương trình tự in** trong kịch bản dependencies đúng như file POM trên (các dòng log môi trường, nếu có, không nằm trong kết quả này):

```text
jdbcTemplateClass=true
hikariClass=true
dataSourceAutoConfigurationClass=true
dataSourceBean=false
jdbcTemplateBean=false
manualMessageBean=true
```

Giải thích từng kết quả:

1. `jdbcTemplateClass=true`: `spring-jdbc` vẫn nằm trong dependency runtime, nên lớp `JdbcTemplate` vẫn có thể được tải.
2. `hikariClass=true`: `HikariCP` vẫn nằm trên classpath, dù không có `DataSource` được auto-create.
3. `dataSourceAutoConfigurationClass=true`: bản thân lớp auto-configuration vẫn nằm trong `spring-boot-autoconfigure`. **Bị exclude không có nghĩa class bị xóa.**
4. `dataSourceBean=false`: trong chương trình tối giản này không có bean `DataSource` do người dùng khai báo và `DataSourceAutoConfiguration` bị loại trừ, nên không có bean `dataSource`.
5. `jdbcTemplateBean=false`: `JdbcTemplateAutoConfiguration` cần một `DataSource` phù hợp để tự tạo bean, nên không có bean `jdbcTemplate` trong tình huống này.
6. `manualMessageBean=true`: bean thủ công không phụ thuộc `DataSourceAutoConfiguration`, vẫn được đăng ký bình thường.

**Không khái quát quá mức:** nếu ứng dụng khác tự khai báo `DataSource` hoặc có cấu hình khác cung cấp bean đó, `JdbcTemplateAutoConfiguration` có thể tiếp tục hoạt động dù `DataSourceAutoConfiguration` bị exclude. Ví dụ trên cố ý không khai báo datasource để quan sát một kịch bản dễ kiểm chứng.

### 5.4. Tự chứng minh việc gỡ dependency khác với exclude auto-configuration

Giữ nguyên class Java và annotation `@SpringBootApplication(exclude = ...)` ở trên. Thay dependency `spring-boot-starter-jdbc` trong `pom.xml` bằng starter cơ bản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
```

Đây là **một trạng thái POM thay thế** cho ví dụ, không phải đoạn cần thêm đồng thời với starter JDBC. `spring-boot-starter` vẫn cung cấp lõi Spring Boot, còn thư viện JDBC và HikariCP không được yêu cầu bởi POM tối giản này.

Chạy lại:

```bash
mvn -q clean spring-boot:run
```

Các dòng ứng dụng tự in được kỳ vọng:

```text
jdbcTemplateClass=false
hikariClass=false
dataSourceAutoConfigurationClass=true
dataSourceBean=false
jdbcTemplateBean=false
manualMessageBean=true
```

Chỉ sau khi **thay đổi dependency graph**, ta mới thấy hai lớp JDBC cụ thể không còn trên classpath của ứng dụng tối giản. Lớp `DataSourceAutoConfiguration` vẫn hiện diện do lõi Spring Boot tiếp tục mang module `spring-boot-autoconfigure`; tuy vậy nó vẫn bị exclude. Sự thay đổi thứ hai không phát sinh từ annotation, mà phát sinh từ POM.

Mục tiêu của hai lượt chạy:

| Quan sát | Có starter JDBC, exclude DataSource auto-config | Chỉ có starter cơ bản, vẫn exclude |
| --- | :---: | :---: |
| Class `JdbcTemplate` trên classpath | Có | Không |
| Class `HikariDataSource` trên classpath | Có | Không |
| Class `DataSourceAutoConfiguration` trên classpath | Có | Có |
| Bean `dataSource` trong ví dụ | Không | Không |
| Bean `manualMessage` | Có | Có |

Các kết quả này áp dụng cho **hai POM độc lập trong ví dụ**; dự án có dependency khác có thể nhận `spring-jdbc`/HikariCP qua những đường khác nên cần kiểm tra dependency graph thực tế.

## 6. Gỡ dependency đúng cách trong Maven và Gradle

### 6.1. Maven: tìm nguồn dependency

Trước khi loại bỏ, xem cây dependencies:

```bash
mvn dependency:tree
```

Chỉ lọc nhóm JDBC đang quan tâm:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-jdbc,com.zaxxer:HikariCP
```

Đọc cả **đường đi qua dependency cha** trong cây. Nếu `spring-jdbc` được khai báo trực tiếp, xóa/đổi khai báo phù hợp trong `pom.xml`. Nếu được kéo vào chuyển tiếp bởi một starter/thư viện khác, cân nhắc giữ thư viện cha và exclude artifact chuyển tiếp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
    <exclusions>
        <exclusion>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Ví dụ XML trên minh họa **cú pháp Maven exclusions**, không phải khuyến nghị bỏ HikariCP trong ứng dụng cần connection pool. Nếu các tính năng còn sử dụng DataSource/HikariCP, bỏ artifact có thể khiến ứng dụng không hoạt động hoặc khiến auto-configuration chọn cơ chế khác. Ngoài ra, nếu HikariCP đi vào qua dependency khác, nó vẫn có thể tồn tại. Luôn chạy lại `dependency:tree`.

### 6.2. Gradle (Groovy DSL): tìm nguồn dependency

Trong một dự án Java/Spring Boot sử dụng Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-jdbc
./gradlew dependencyInsight --configuration runtimeClasspath --dependency HikariCP
```

Với module Gradle nhiều project, chạy task ở module ứng dụng, chẳng hạn `:app:dependencyInsight` khi `app` là project thật sự có `runtimeClasspath`. Những lệnh trên minh họa Gradle Wrapper trên hệ có shell tương ứng; với Windows có thể chạy `gradlew.bat`.

Ví dụ cú pháp exclude artifact chuyển tiếp trên một nhánh khai báo:

```groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-jdbc') {
        exclude group: 'com.zaxxer', module: 'HikariCP'
    }
}
```

Để **không dùng JDBC starter nữa**, bỏ dependency starter đó thay vì kỳ vọng một annotation trong Java xóa nó khỏi classpath. Nhưng phải xác nhận không có dependency khác kéo lại artifact tương đương.

### 6.3. Vì sao không cứ “exclude tất cả” cho gọn?

Loại một module khỏi dependency graph có thể làm mất API hoặc implementation mà ứng dụng đang cần:

- Source có import `JdbcTemplate` sẽ không biên dịch nếu loại `spring-jdbc` khỏi compile classpath.
- Class đã biên dịch có thể gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` ở runtime nếu JAR không còn.
- Thư viện khác có thể yêu cầu một pool JDBC thực tế; bỏ pool mà không cấu hình lựa chọn thay thế có thể khiến khởi động thất bại.
- Dependency có thể cần thiết cho một tính năng dù bạn không muốn **tự động cấu hình** tính năng đó.

Vì vậy, **chọn đúng nhu cầu**: muốn giữ API để viết cấu hình thủ công thì thường nên giữ dependency và tắt cơ chế auto-configuration không cần thiết; muốn ngăn artifact xuất hiện trong runtime thì phải xử lý ở build/dependency management và kiểm thử lại ứng dụng.

## 7. Classpath condition vẫn có thể khớp khi auto-configuration đã bị exclude

Giả sử một cấu hình khác không bị loại trừ có điều kiện:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
class JdbcClassPresentConfiguration {

    @Bean
    String jdbcLibraryDetected() {
        return "JDBC class is available";
    }
}
```

Đây là **snippet minh họa**, được giả định là cấu hình được đăng ký hợp lệ bởi ứng dụng. Khi `spring-jdbc` còn trên classpath, `@ConditionalOnClass` vẫn có thể khớp dù `DataSourceAutoConfiguration` bị exclude. Điều kiện này hỏi **“class có tồn tại không?”**, không hỏi “có bean `JdbcTemplate` không?” hoặc “auto-configuration nào đã bị exclude?”.

Ngược lại, một điều kiện:

```java
@ConditionalOnBean(javax.sql.DataSource.class)
```

chỉ xét việc có bean kiểu `DataSource` được biết đến lúc đánh giá. Trong chương trình ở mục 5, nó không khớp vì không có bean này; nếu ứng dụng đăng ký thủ công một bean `DataSource`, kết quả có thể khác mà không phải khôi phục `DataSourceAutoConfiguration`.

Khi xây dựng starter, thường kết hợp `@ConditionalOnClass` (đảm bảo thư viện liên quan có mặt) với `@ConditionalOnMissingBean` (nhường quyền cho bean người dùng tự khai báo). Tuy nhiên **kết quả không thể suy luận từ một annotation exclude duy nhất**: phải đọc điều kiện thực tế của từng lớp auto-configuration và trạng thái bean.

## 8. Kiểm chứng ba điều độc lập: class, bean và cấu hình

Một quy trình chẩn đoán đáng tin cậy:

1. **Kiểm dependency graph:** dùng `mvn dependency:tree` hoặc Gradle `dependencies`/`dependencyInsight` theo đúng module và `runtimeClasspath`. Điều này trả lời “artifact tới từ đâu?”.
2. **Kiểm class loading:** dùng `ClassUtils.isPresent("fully.qualified.Class", classLoader)` như ví dụ, hoặc kiểm tra cấu trúc executable JAR. Điều này trả lời “class có thể được tải trong runtime đang chạy hay không?”. Không suy diễn từ mỗi IDE autocomplete.
3. **Kiểm bean:** dùng `ApplicationContext.containsBean("name")`, `getBeanNamesForType(...)`, hoặc công cụ introspection phù hợp để biết bean được đăng ký. Điều này trả lời “Spring có bean đó hay không?”.
4. **Kiểm condition report:** chạy ứng dụng với `--debug` để xem báo cáo condition và danh sách excluded auto-configurations khi phiên bản/thiết lập log cho phép. Nếu có Actuator phù hợp, endpoint `/actuator/conditions` hỗ trợ xem kết quả condition. Điều này trả lời “tại sao auto-configuration có hoặc không được áp dụng?”.
5. **Kiểm artifact deploy:** sau khi build executable JAR, xem các thư viện thực sự đóng gói, ví dụ `jar tf target/app.jar` (đổi tên file theo artifact thật). Maven/Gradle có thể có nhiều packaging task; đừng mặc định JAR chạy chính là file vừa kiểm tra nếu quy trình deploy dùng artifact khác.
6. **Thử theo kịch bản:** kiểm ứng dụng khi chỉ thêm exclude; khi thay POM/Gradle; và khi có bean thủ công. So sánh dữ liệu classpath, condition report và các bean thực tế thay vì kết luận từ một log đơn lẻ.

Ví dụ kiểm tra nội dung Spring Boot executable JAR:

```bash
mvn -q package
jar tf target/classpath-vs-autoconfig-1.0.0.jar
```

Trong trường hợp POM ở mục 5.2, có thể tìm các thư viện chứa `spring-jdbc` và `HikariCP` bên dưới `BOOT-INF/lib/`. Với POM chỉ dùng starter cơ bản ở mục 5.4, chúng không còn do dependency trực tiếp đó nữa (trừ khi build có nguồn dependency khác). **Một auto-configuration exclude không tự xóa các entry JAR này.**

### 8.1. Dấu hiệu lỗi và hướng truy vết

| Quan sát | Khả năng thực tế | Kiểm tra tiếp |
| --- | --- | --- |
| `JdbcTemplate.class` vẫn tải được sau `exclude` | JDBC JAR vẫn trong runtime classpath | `dependency:tree` / `dependencyInsight` và JAR contents |
| Condition report nói `DataSourceAutoConfiguration` bị excluded nhưng vẫn thấy `DataSource` bean | Bean có thể do `@Bean`, `@Import` hoặc cấu hình khác khai báo | Tìm nguồn bean definition; kiểm tra tên và kiểu bean |
| Không có `DataSource` bean nhưng có `HikariDataSource` class | Class hiện diện không buộc phải có bean | Tách kết quả classpath khỏi `ApplicationContext` |
| `@ConditionalOnClass(JdbcTemplate.class)` vẫn khớp | Class vẫn hiện diện dù auto-config khác bị loại | Kiểm dependency graph; xem điều kiện cụ thể |
| Bỏ dependency nhưng IDE hoặc runtime vẫn thấy class | Có đường phụ thuộc chuyển tiếp khác; runtime/IDE khác classpath | Xem dependency graph đúng configuration, rebuild và kiểm artifact đang chạy |
| Exclude tên của `@Configuration` thường và Spring Boot báo lỗi | Đích không phải auto-configuration hợp lệ theo importer | Dùng cách tắt riêng cho cấu hình thủ công; xác định đúng auto-config |
| Loại dependency dẫn tới `NoClassDefFoundError` | Mã hoặc thư viện vẫn tham chiếu class đã mất | Hoàn nguyên/thay implementation, sửa mã hoặc dependency nhất quán |

## 9. Những lỗi tư duy và thiết kế dễ mắc

### 9.1. “Đã exclude auto-config nên dependency không còn là vấn đề”

Sai. JAR có thể vẫn được đóng gói vào artifact, tiếp tục hiện diện trong runtime và được những thành phần khác sử dụng. Nếu mục tiêu là **loại một thư viện không mong muốn khỏi binary, giảm footprint hoặc xử lý cảnh báo dependency**, thao tác exclude trong annotation không đạt được mục tiêu đó. Cần xử lý phiên bản, scope hoặc dependency graph thực sự, sau đó xác minh artifact được triển khai. Có mặt của thư viện trong binary không tự chứng minh một lỗ hổng có thể khai thác; đánh giá bảo mật vẫn cần xét phiên bản, cấu hình và đường tấn công.

### 9.2. “Chỉ cần exclude một auto-config là tắt toàn bộ tính năng”

Không bảo đảm. Một tính năng có thể có **nhiều auto-configuration** với điều kiện riêng, và ứng dụng có thể tự đăng ký bean tương tự. Ví dụ loại `DataSourceAutoConfiguration` không xóa các `@Bean` `DataSource` do người dùng viết. Nếu mục tiêu là tắt toàn bộ tích hợp, hãy xác định chính xác các nguồn tạo bean, property bật/tắt và dependency của tính năng trước khi quyết định.

### 9.3. “Đã loại một JAR thì condition nào liên quan cũng tắt”

Không luôn đúng. Một số auto-configurations phụ thuộc vào class **khác** vẫn còn trên classpath, có thể fallback sang implementation khác hoặc được kích hoạt từ điều kiện bean/property khác. Ngược lại, mã ứng dụng có thể không khởi động được nếu nó trực tiếp sử dụng lớp đã bị loại. Phải thử thực tế và đọc condition report.

### 9.4. “Exclude auto-config giống như xóa @Configuration”

Không giống. Exclude của `@SpringBootApplication`/`@EnableAutoConfiguration` chủ yếu tác động đến cách Boot **nhập ứng viên auto-configuration**. Nó không là cơ chế xóa mọi cấu hình do người dùng chủ động import hoặc component scan. Tài liệu chính thức cũng khuyến nghị auto-configuration của starter **chỉ** được nạp qua `AutoConfiguration.imports`, tránh để component scanning vô tình nạp chúng theo cách khác.

### 9.5. “Thay `exclude` bằng `excludeName` sẽ loại dependency”

Không. Khác biệt giữa hai thuộc tính chỉ là **cách chỉ định lớp mục tiêu**: `Class` so với tên lớp đầy đủ dạng `String`. Không thuộc tính nào sửa `pom.xml`, `build.gradle` hoặc nội dung executable JAR.

## 10. Tự kiểm tra

**Câu 1.** Một ứng dụng có dependency `spring-boot-starter-jdbc` và `@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)`. Bạn gọi `ClassUtils.isPresent("org.springframework.jdbc.core.JdbcTemplate", loader)`; dự đoán kết quả?  
**Đáp án:** Trong dependency graph điển hình của starter JDBC, kết quả là true, bởi `spring-jdbc` vẫn được mang vào runtime. Exclude chỉ thay đổi danh sách auto-configuration được áp dụng.

**Câu 2.** Exclude `DataSourceAutoConfiguration` nhưng tự khai báo `@Bean DataSource customDataSource()`. Có thể vẫn có bean `JdbcTemplate` do auto-configuration khác tạo không?  
**Đáp án:** Có thể. Nếu chỉ có một ứng viên `DataSource` phù hợp và các điều kiện còn lại được đáp ứng, `JdbcTemplateAutoConfiguration` có thể đăng ký `JdbcTemplate`. Không được kết luận mọi JDBC bean đều biến mất.

**Câu 3.** Muốn loại JAR `HikariCP` khỏi runtime classpath, có nên chỉ viết `spring.autoconfigure.exclude=...DataSourceAutoConfiguration`?  
**Đáp án:** Không đủ. Cần chỉnh dependency graph Maven/Gradle hoặc scope thích hợp, xác minh artifact này không còn được resolve theo đường khác và kiểm thử ứng dụng.

**Câu 4.** `@ConditionalOnClass(JdbcTemplate.class)` có thể khớp khi `DataSourceAutoConfiguration` bị exclude không?  
**Đáp án:** Có. Một condition xét **class** khác một condition xét bean hoặc một auto-configuration đã được áp dụng.

**Câu 5.** Đặt `@SpringBootApplication(excludeName = "dataSource")` có đúng không?  
**Đáp án:** Không. `excludeName` nhận **fully qualified class name của auto-configuration**, ví dụ `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`; `dataSource` chỉ có thể là tên bean.

**Câu 6.** Bạn xóa dependency trực tiếp `spring-jdbc` nhưng `dependencyInsight` vẫn báo class/module này ở runtime. Nguyên nhân hợp lý?  
**Đáp án:** Một dependency khác vẫn mang `spring-jdbc` vào theo quan hệ chuyển tiếp. Phải tìm đầy đủ đường đi trong dependency graph và xác minh artifact cuối.

**Câu 7.** Muốn giữ JDBC API để tự tạo bean, nhưng không cho Boot tự tạo DataSource khi thiếu cấu hình. Thao tác phù hợp đầu tiên là gì?  
**Đáp án:** Giữ dependency JDBC cần thiết và xem xét exclude riêng `DataSourceAutoConfiguration` hoặc điều kiện/property liên quan; sau đó viết và kiểm tra cấu hình thủ công. Không nhất thiết gỡ `spring-jdbc` khỏi runtime.

## 11. Ghi nhớ và tài liệu chính thức

- `exclude`, `excludeName` và `spring.autoconfigure.exclude` **loại một auto-configuration khỏi quá trình tự áp dụng**, không loại JAR khỏi classpath.
- **Classpath, auto-configuration và bean registry là ba tầng khác nhau.** Class có thể còn mà bean không có; auto-configuration bị exclude nhưng bean từ nơi khác vẫn có thể tồn tại.
- Muốn **thay đổi dependency runtime**, sửa build file hoặc dependency management bằng Maven/Gradle và kiểm tra dependency graph thực tế.
- Muốn **tắt hành vi tự động nhưng vẫn dùng API**, giữ dependency cần thiết và dùng exclude/condition cấu hình đúng phạm vi.
- Muốn chứng minh kết quả, kiểm đồng thời dependency graph, khả năng tải class, bean trong context, condition report và artifact đã đóng gói.

Tài liệu tham khảo:

1. Spring Boot 3.3 — [Auto-configuration: Using Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html), đặc biệt phần *Disabling Specific Auto-configuration Classes*.
2. Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), phần *Locating Auto-configuration Candidates* và *Class Conditions*.
3. Spring Boot 3.3 — [`@SpringBootApplication` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html), thuộc tính `exclude`, `excludeName`.
4. Spring Boot 3.3 — [`@EnableAutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html).
5. Gradle — [Viewing Dependencies and `dependencyInsight`](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).
6. Apache Maven — [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html).