# exclude trên @SpringBootApplication và @EnableAutoConfiguration

> **Spring Boot Auto Configuration → Thay thế và loại trừ.** Bài học giải thích cách loại một auto-configuration cụ thể khỏi cơ chế tự cấu hình của Spring Boot, so sánh `@SpringBootApplication` với `@EnableAutoConfiguration`, phân biệt `exclude` và `excludeName`, thực hành với Java 17 + Spring Boot 3.3, và kiểm tra ảnh hưởng lên bean, dependency, các cấu hình do ứng dụng tự định nghĩa.

## 1. Vấn đề: Spring Boot có thể tự cấu hình thứ ứng dụng không cần

Khi có một số thư viện trên classpath, Spring Boot tìm những lớp *auto-configuration* phù hợp rồi đánh giá các điều kiện như `@ConditionalOnClass`, `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`. Ví dụ, khi một ứng dụng có các thư viện JDBC và driver database, Spring Boot có thể tự cấu hình `DataSource`. Đây là hành vi có ích khi ứng dụng sử dụng database nhưng có thể không mong muốn ở một dịch vụ hoàn toàn không truy cập database.

Nếu một auto-configuration nhất định **không phù hợp với kiến trúc ứng dụng**, Spring Boot cho phép khai báo loại trừ nó:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class Application {
}
~~~

Ý nghĩa: khi Spring Boot chọn danh sách auto-configuration để áp dụng, nó sẽ **không áp dụng lớp `DataSourceAutoConfiguration` qua cơ chế tự cấu hình thông thường**. Điều đó khác với việc xóa thư viện JDBC khỏi classpath, xóa mọi bean `DataSource`, hay vô hiệu hóa mọi phần liên quan đến database.

**Câu hỏi cần đặt trước khi exclude:** cấu hình đó thực sự không thuộc ứng dụng, hay nó đang báo lỗi vì thiếu cấu hình bắt buộc? Exclude là một quyết định kiến trúc có phạm vi rõ ràng; nó không phải mẹo chữa mọi lỗi startup.

## 2. Mối quan hệ giữa hai annotation

### 2.1. @SpringBootApplication thực chất bao gồm gì?

Trong Spring Boot 3.x, `@SpringBootApplication` là annotation tiện lợi kết hợp ba vai trò:

~~~text
@SpringBootApplication
  ├── @SpringBootConfiguration  (một dạng @Configuration)
  ├── @EnableAutoConfiguration  (bật cơ chế tự cấu hình)
  └── @ComponentScan           (quét component theo package)
~~~

Vì đã chứa `@EnableAutoConfiguration`, sử dụng `@SpringBootApplication` cũng đồng thời kích hoạt auto-configuration. Spring Boot cung cấp ngay trên `@SpringBootApplication` hai thuộc tính:

- `exclude`: mảng các **class auto-configuration** cần bỏ qua.
- `excludeName`: mảng **tên đầy đủ dạng chuỗi** của các class auto-configuration cần bỏ qua.

Hai thuộc tính này dùng `@AliasFor` để chuyển cho cơ chế `@EnableAutoConfiguration` bên trong. Do đó bạn có thể cấu hình loại trừ ngay trên class chính của ứng dụng, không cần tự thêm một annotation `@EnableAutoConfiguration` nữa.

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class DemoApplication {
}
~~~

Đây là **đoạn khai báo** minh họa. Một ứng dụng chạy được còn cần `main` gọi `SpringApplication.run(...)` và dependency tương ứng; phần 5 cung cấp chương trình đầy đủ.

### 2.2. @EnableAutoConfiguration dùng khi nào?

Nếu dự án không muốn dùng toàn bộ tính năng mà `@SpringBootApplication` gộp lại, có thể tự tổ chức cấu hình và bật auto-configuration bằng `@EnableAutoConfiguration`:

~~~java
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class ManualApplicationConfiguration {
}
~~~

Lớp trên là một **configuration component**; nó không tự có component scan, trừ khi thêm `@ComponentScan` hoặc một cơ chế đăng ký riêng. `@EnableAutoConfiguration` chủ yếu bật lựa chọn các auto-configuration và có sẵn `exclude`, `excludeName` như trên.

**Lưu ý:** đã dùng `@SpringBootApplication` thì không cần đặt thêm `@EnableAutoConfiguration` lên cùng application class. Việc thêm cả hai không làm bật auto-configuration “mạnh hơn” và khiến nơi khai báo loại trừ khó quản lý. Với một ứng dụng Boot thông thường, viết `exclude` ngay trên `@SpringBootApplication` là rõ nhất.

### 2.3. So sánh nhanh

| Tiêu chí | `@SpringBootApplication(exclude=...)` | `@EnableAutoConfiguration(exclude=...)` |
| --- | --- | --- |
| Mục đích | Cấu hình Spring Boot ứng dụng với component scan và auto-configuration | Bật auto-configuration trên một cấu hình do bạn tổ chức |
| Có `exclude` / `excludeName`? | Có | Có |
| Có tự component scan? | Có, thông qua `@ComponentScan` | Không; muốn scan thì khai báo riêng |
| Có phải annotation thay thế nhau hoàn toàn? | Không; `@SpringBootApplication` gồm thêm các vai trò khác | Chỉ đảm nhiệm phần auto-configuration |
| Hiệu quả loại trừ auto-config | Cùng cơ chế thông qua alias | Khai báo trực tiếp |
| Tình huống dùng | Application class chuẩn | Khởi tạo context tùy chỉnh hoặc cấu hình modular có kiểm soát |

## 3. exclude: chỉ định class auto-configuration bằng Class literal

Cú pháp:

~~~java
@SpringBootApplication(
    exclude = {DataSourceAutoConfiguration.class}
)
public class DemoApplication {
}
~~~

Khi chỉ có một class, có thể bỏ cặp ngoặc nhọn:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

`exclude` có kiểu `Class<?>[]`. Spring Boot sử dụng **loại class auto-configuration được chỉ định** để loại khỏi các candidate được áp dụng. Với class có sẵn trong compile classpath, cách này được trình biên dịch kiểm tra tên package và type, nên giảm nguy cơ viết sai chính tả.

Ví dụ `DataSourceAutoConfiguration` trong **Spring Boot 3.3** có tên đầy đủ:

~~~text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Với Java source sử dụng Boot 3.3, import đúng:

~~~java
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
~~~

**Một điểm về phiên bản:** package của auto-configuration có thể thay đổi giữa các thế hệ lớn của Spring Boot. Ví dụ một số class đã di chuyển trong Spring Boot 4.x. Luôn dùng Javadoc đúng phiên bản của dự án thay vì sao chép một import thuộc phiên bản khác.

### 3.1. Exclude nhiều auto-configuration

Có thể khai báo nhiều class bằng mảng:

~~~java
@SpringBootApplication(
    exclude = {
        DataSourceAutoConfiguration.class,
        DataSourceTransactionManagerAutoConfiguration.class
    }
)
~~~

Đây là **đoạn annotation**, không phải chương trình độc lập. Khi dùng với Spring Boot 3.3, class thứ hai cũng nằm trong package `org.springframework.boot.autoconfigure.jdbc`; cần bổ sung import chính xác. Chỉ exclude từng auto-configuration khi đã xác định nó không phù hợp; đừng tự động loại một danh sách dài nếu chưa hiểu chuỗi ảnh hưởng.

### 3.2. Tại sao phải exclude đúng lớp auto-configuration?

Ví dụ không đúng về mặt mục tiêu:

~~~java
// KHÔNG dùng để loại một @Service do ứng dụng tự khai báo:
@SpringBootApplication(exclude = MyPaymentService.class)
~~~

`MyPaymentService` là một component thông thường, không phải auto-configuration candidate do Boot tuyển chọn. Exclusion không phải cơ chế chọn bỏ mọi bean; nếu đưa class không hợp lệ, Boot có thể từ chối cấu hình loại trừ.

Để điều khiển component scan của một bean do ứng dụng sở hữu, xem `@ComponentScan(excludeFilters=...)` hoặc điều kiện phù hợp cho bean đó. Để điều khiển việc đăng ký tự cấu hình của **một lớp auto-configuration**, dùng `exclude`.

## 4. excludeName: chỉ định tên class bằng chuỗi

Khi không muốn hoặc không thể tham chiếu class trực tiếp tại compile time, dùng `excludeName`:

~~~java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class DemoApplication {
}
~~~

Kiểu của `excludeName` là `String[]`. Chuỗi phải là **fully qualified class name** (package + tên class); chỉ ghi `"DataSourceAutoConfiguration"` sẽ không đủ.

Cách tương đương khi tổ chức cấu hình thủ công:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ManualConfiguration {
}
~~~

`excludeName` hữu ích cho module/tích hợp tùy chọn: source code không cần import class đó. Tuy nhiên, vì tên là chuỗi, trình biên dịch Java **không kiểm chứng chính tả**, nên test và kiểm tra danh sách auto-configuration thực tế là cần thiết.

### 4.1. Chọn exclude hay excludeName?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Class auto-configuration hiện diện ở compile time | `exclude = SomeAutoConfiguration.class` | Rõ ràng, dễ refactor và được kiểm tra tên class |
| Class thuộc integration tùy chọn, không có dependency compile | `excludeName = "com.vendor...AutoConfiguration"` | Tránh phụ thuộc nguồn vào class tùy chọn |
| Thông tin loại trừ cần thay đổi theo môi trường triển khai | `spring.autoconfigure.exclude` | Có thể thay đổi qua cấu hình ngoài code |
| Cần tắt một bean application-defined | Không dùng hai thuộc tính này | Điều chỉnh cách đăng ký bean, condition hoặc component scanning |
| Tính năng đã được auto-config bảo vệ bằng `@ConditionalOnClass` và class không hiện diện | Thường không cần exclude | Auto-config vốn đã tự bỏ qua khi không đủ điều kiện |

Có thể khai báo đồng thời `exclude` và `excludeName` nếu thực sự có nhiều đối tượng cần loại trừ và mỗi cách phù hợp với một nhóm. Tuy nhiên hãy quản lý tập exclusions rõ ràng, tránh trùng lặp vô ích.

## 5. Lab Spring Boot 3.3 + Java 17: loại DataSourceAutoConfiguration

Bài thực hành dưới đây chứng minh `exclude` tác động đến **bean do auto-configuration tạo**. Chúng ta cố ý thêm JDBC và H2 để Boot có đủ điều kiện tạo `DataSource`; sau đó tắt đúng auto-configuration của nó rồi so kết quả. Không yêu cầu kết nối đến database bên ngoài.

### 5.1. Cấu trúc dự án

~~~text
exclude-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── exclude/
    │               └── ExcludeDemoApplication.java
    └── test/
        └── java/
            └── demo/
                └── exclude/
                    └── ExcludeDemoApplicationTest.java
~~~

Cần **JDK 17+**, **Maven** và có thể tải dependency. Để kết quả được tái hiện, các đoạn code dùng Spring Boot **3.3.13**; các class imports ở đây dành cho Boot 3.3.

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>exclude-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
~~~

`spring-boot-starter-jdbc` cung cấp hạ tầng JDBC/pool; H2 cho phép Boot chọn database nhúng. Khi không exclude và không tự khai báo `DataSource`, `DataSourceAutoConfiguration` có thể tạo bean phù hợp. Từ đó ta có đối chứng rõ ràng.

### 5.3. ExcludeDemoApplication.java — cách 1 với @SpringBootApplication

~~~java
package demo.exclude;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExcludeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExcludeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            String[] names = context.getBeanNamesForType(DataSource.class);
            System.out.println("dataSource bean count: " + names.length);
        };
    }
}
~~~

Đoạn này là **chương trình hoàn chỉnh** trong dự án Maven ở trên. `ApplicationRunner` chạy sau khi context khởi động; code hỏi container có bao nhiêu bean thuộc type `DataSource`, không gọi SQL hoặc kết nối network.

### 5.4. Đóng gói và chạy khi có exclude

Từ thư mục `exclude-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/exclude-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout nghiệp vụ do chương trình in:

~~~text
dataSource bean count: 0
~~~

**Giải thích:** `DataSourceAutoConfiguration` bị loại khỏi danh sách auto-configuration. Lab không tự đăng ký một `DataSource` khác, nên container không có bean loại đó. Nếu thấy thêm dòng của Maven hoặc thư viện trong môi trường riêng, hãy so **dòng do `System.out.println` in**, không giả định log tổng thể luôn giống nhau.

### 5.5. Đối chứng: bỏ exclude rồi chạy lại

Trong **cùng tệp** `ExcludeDemoApplication.java`, thay:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

bằng:

~~~java
@SpringBootApplication
~~~

Không sửa đoạn code báo cáo. **Đóng gói lại** rồi chạy:

~~~bash
mvn -q -DskipTests package
java -jar target/exclude-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng kết quả mong đợi trong môi trường demo với starter JDBC và H2:

~~~text
dataSource bean count: 1
~~~

**Ý nghĩa:** khi đủ điều kiện, `DataSourceAutoConfiguration` cho phép cấu hình mặc định tạo `DataSource`. Exclude ngăn việc áp dụng cấu hình này qua auto-selection; khi bỏ exclude, ứng dụng trong ví dụ có lại bean mặc định. Sự khác nhau do **quyết định áp dụng auto-configuration**, không phải do thay đổi classpath.

### 5.6. Cách 2: dùng @EnableAutoConfiguration thay cho @SpringBootApplication

Thay **toàn bộ** tệp `ExcludeDemoApplication.java` bằng phiên bản dưới đây; **không lưu cả hai phiên bản cùng lúc**:

~~~java
package demo.exclude;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration(exclude = DataSourceAutoConfiguration.class)
public class ExcludeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExcludeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> System.out.println(
                "dataSource bean count: " +
                context.getBeanNamesForType(DataSource.class).length
        );
    }
}
~~~

Tiếp tục:

~~~bash
mvn -q -DskipTests package
java -jar target/exclude-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do chương trình in:

~~~text
dataSource bean count: 0
~~~

Phiên bản này **không có `@ComponentScan`** nhưng lab vẫn chạy: bean `report` được khai báo ngay trong class cấu hình đã đưa cho `SpringApplication.run(...)`, còn các auto-configuration khác được bật nhờ `@EnableAutoConfiguration`. Trong một ứng dụng cần tìm component ở các package, phải thêm `@ComponentScan` hoặc cơ chế import thích hợp. Đây là **khác biệt về tổ chức cấu hình**, không phải khác biệt về hiệu lực của `exclude`.

### 5.7. Cách 3: dùng excludeName

Nếu quay lại phiên bản `@SpringBootApplication`, có thể thay dòng annotation bằng:

~~~java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
~~~

Hoặc trong phiên bản dùng `@EnableAutoConfiguration`:

~~~java
@EnableAutoConfiguration(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
~~~

Hai đoạn này là **annotation thay thế**, không phải class Java độc lập. Với đúng FQCN trong Boot 3.3, kết quả sẽ giống `exclude = DataSourceAutoConfiguration.class`. Cách dùng chuỗi không cần import class được loại trừ trong source.

## 6. Exclude thực sự thay đổi gì bên trong Spring Boot?

Ở mức khái niệm, auto-configuration diễn ra như sau:

~~~text
Classpath + AutoConfiguration.imports
               |
               v
   Tập auto-configuration ứng viên
               |
               v
    Áp dụng exclusions đã khai báo
     - @SpringBootApplication.exclude / excludeName
     - @EnableAutoConfiguration.exclude / excludeName
     - spring.autoconfigure.exclude
               |
               v
   Sắp xếp và đánh giá các điều kiện
               |
               v
    Đăng ký bean definitions hợp lệ
               |
               v
       Khởi tạo bean instances
~~~

Đây là mô hình đơn giản hóa nhằm giải thích **tác động thực tế**: loại trừ được áp dụng lên danh sách auto-configuration ứng viên, nên cấu hình bị loại **không đi tiếp để đăng ký các bean mặc định của nó qua auto-configuration**.

Không nhầm với:
- **Dependency resolution** của Maven/Gradle: thay `exclude` trong annotation **không xóa JAR** khỏi ứng dụng.
- **Component scan**: một bean do `@Component` / `@Service` thông thường vẫn có thể được phát hiện.
- **Cấu hình do ứng dụng đăng ký thủ công**: bean tự khai báo bằng `@Bean` vẫn có thể tồn tại, kể cả khi một auto-configuration tương ứng đã bị loại.
- **Điều kiện riêng của auto-configuration khác**: những auto-configuration khác vẫn được đánh giá theo classpath, property và bean hiện có.
- **Thứ tự tạo instance**: `exclude` loại cấu hình khỏi lựa chọn, không phải công cụ sắp xếp khởi tạo object.

Trong mã nguồn của Spring Boot, các lớp auto-configuration cung cấp cơ chế tiện ích, nhiều bean chỉ được tạo nếu chưa có bean tương ứng, ví dụ thông qua `@ConditionalOnMissingBean`. Exclude dành cho trường hợp **muốn vô hiệu hóa cả một auto-configuration cụ thể**, còn ghi đè bean hoặc bật/tắt feature qua property có thể cho kết quả nhẹ hơn.

## 7. Exclude không có nghĩa “không bao giờ có bean kiểu đó”

Hãy xem ví dụ thành phần dưới đây, áp dụng cho một ứng dụng có thư viện JDBC. Nó minh họa bean do ứng dụng **tự khai báo**:

~~~java
@Configuration(proxyBeanMethods = false)
class ManualDataSourceConfiguration {

    @Bean
    DataSource dataSource() {
        return new org.springframework.jdbc.datasource
                .DriverManagerDataSource(
                    "jdbc:h2:mem:manual",
                    "sa",
                    ""
                );
    }
}
~~~

Đây là **đoạn thành phần**, cần import `@Configuration`, `@Bean`, `javax.sql.DataSource` và bảo đảm nó được component scan/import. Đặt cấu hình này trong package được scan và đồng thời dùng:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

Khi đó ứng dụng **vẫn có thể có `DataSource`**, vì bean đã do cấu hình thủ công tạo. Exclude chỉ ngăn `DataSourceAutoConfiguration` tự áp dụng, không chặn mọi con đường đăng ký bean cùng type.

Tương tự, loại `SecurityAutoConfiguration` không bảo đảm mọi bảo mật biến mất; loại cấu hình web nào đó không xóa controller do ứng dụng tự viết. **Tên class bị exclude và nguồn gốc bean cần được xem cùng nhau.**

## 8. Phương án cấu hình bên ngoài: spring.autoconfigure.exclude

Ngoài hai annotation, Spring Boot cho phép khai báo danh sách class auto-configuration bị loại thông qua property `spring.autoconfigure.exclude`.

**application.properties:**

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**application.yml:**

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

**Tham số dòng lệnh:**

~~~bash
java -jar app.jar --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Property hữu ích khi muốn điều chỉnh theo môi trường mà không thay đổi annotation nguồn. Có thể có loại trừ ở cả annotation lẫn property; Spring Boot thu thập các loại trừ cần áp dụng từ những nơi được hỗ trợ.

**Khác biệt thiết kế:** nếu thư viện tích hợp **không bao giờ phù hợp** với module, khai báo exclusion ở application class thường thể hiện ý định rõ. Nếu tính năng phụ thuộc environment, property có thể giúp quản lý linh hoạt hơn. Tuy nhiên phải quản lý thay đổi theo profile, CI/CD, môi trường production để tránh loại bỏ nhầm một thành phần bắt buộc.

Đừng quên: property exclusion chứa **tên class đầy đủ**, không phải tên bean, artifact Maven hay cờ `spring.datasource.enabled=false` tự tạo theo suy đoán.

## 9. Khi nào nên exclude, khi nào dùng giải pháp khác?

| Mong muốn | Cách tiếp cận | Giải thích |
| --- | --- | --- |
| Ứng dụng hoàn toàn không cần một auto-configuration nhưng thư viện liên quan vẫn có trên classpath | `exclude` / `excludeName` | Loại rõ ràng auto-configuration đó |
| Muốn thay bean mặc định bằng bean do ứng dụng cung cấp | Tạo `@Bean` phù hợp, kiểm tra `@ConditionalOnMissingBean` | Nhiều auto-config sẽ tự nhường khi có bean người dùng; có thể không cần exclude |
| Tính năng tùy chọn có property chuyên biệt để bật/tắt | Dùng property mà auto-config hỗ trợ | Bảo toàn cơ chế chuẩn của starter, dễ vận hành |
| Muốn không tải một thư viện ở runtime | Sửa dependency Gradle/Maven và packaging | Annotation exclude không xóa artifact |
| Muốn loại `@Service` tự khai báo khỏi scan | Điều chỉnh `@ComponentScan`, `@Profile` hoặc điều kiện của bean | Không phải một auto-configuration candidate |
| Muốn một auto-configuration chạy trước/sau cái khác | `@AutoConfiguration(before/after)` | Đây là **sắp xếp thứ tự**, không loại cấu hình |
| Ứng dụng cần JDBC nhưng báo thiếu URL/driver | Cung cấp cấu hình datasource và driver đúng | Exclude có thể che nguyên nhân khiến tính năng quan trọng mất |
| Muốn dùng thư viện khác thay một thư viện hiện có | Đọc điều kiện auto-config và lựa chọn starter/dependency | Có thể cần đổi dependency hoặc bean thay thế, thay vì chỉ exclude |

### 9.1. Khi nào exclude là hợp lý?

Ví dụ một dịch vụ xử lý message có thư viện JDBC đi kèm qua dependency bắc cầu nhưng **không sử dụng database**. Nếu cơ chế tự cấu hình datasource gây khởi tạo không mong muốn, exclude `DataSourceAutoConfiguration` có thể phản ánh đúng kiến trúc. Tuy vậy vẫn cần xem vì sao thư viện JDBC nằm trong classpath và liệu bỏ dependency đó có thích hợp hơn không.

### 9.2. Khi nào exclude là dấu hiệu sửa sai hướng?

Ví dụ ứng dụng thật sự cần truy cập database và báo:

~~~text
Failed to configure a DataSource
~~~

Dùng `exclude = DataSourceAutoConfiguration.class` có thể làm thông báo đó biến mất, nhưng các repository, `JdbcTemplate` hoặc bean nghiệp vụ cần datasource sẽ không hoạt động đúng. Hướng xử lý là xác minh URL, driver, credentials, profile và dependency; không loại bỏ cấu hình nền bắt buộc chỉ để qua bước startup.

### 9.3. Đừng loại trừ tùy tiện cấu hình nội bộ

Spring Boot khuyến nghị chỉ dựa vào **tên class auto-configuration** như giao diện được phép dùng để exclude, tránh phụ thuộc vào class nested, phương thức hoặc chi tiết implementation nội bộ của auto-configuration. Khi nâng cấp phiên bản Boot, nên xác nhận FQCN và behavior các exclusions được khai báo.

## 10. Debug xem một auto-configuration có bị loại hay không

### 10.1. Dùng --debug để đọc Condition Evaluation Report

Chạy ứng dụng với:

~~~bash
java -jar target/exclude-demo-1.0.0.jar --debug
~~~

Báo cáo của Spring Boot cho biết những auto-configuration match/không match và phần exclusions trong môi trường tương ứng. Cách đọc:

1. Tìm **fully qualified class name** cần loại, ví dụ `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`.
2. Kiểm tra có xuất hiện trong danh sách **Exclusions** hoặc thông tin tương đương hay không.
3. Nếu không thấy exclusion mong đợi, xác minh annotation nằm trên đúng application configuration, tên class đúng phiên bản và property sources.
4. Nếu bean vẫn xuất hiện, truy nó được **cấu hình nào** đăng ký. Exclude không xóa bean do ứng dụng tự khai báo.
5. Nếu ứng dụng không khởi động, đọc **Caused by** trong stack trace; exclusion có thể đã hoạt động nhưng bean khác vẫn phụ thuộc vào thứ đã bị loại.

Trong ứng dụng có Spring Boot Actuator, endpoint `/actuator/conditions` có thể cung cấp thông tin tương tự khi đã được bật và expose phù hợp. Cần kiểm soát quyền truy cập các endpoint chẩn đoán ở môi trường triển khai.

### 10.2. Kiểm tra những yếu tố hay làm kết quả khác nhau

- **Version:** chính xác Spring Boot 3.x hay 4.x? Import class auto-config có thể thay đổi.
- **Classpath:** starter JDBC, driver, component do người dùng viết và dependency bắc cầu có thật trong artifact triển khai?
- **Annotation:** dùng `@SpringBootApplication(exclude=...)` hay `@EnableAutoConfiguration(exclude=...)`? Có đặt trên configuration thực sự được Boot dùng để khởi động không?
- **Tên class:** FQCN trong `excludeName` / `spring.autoconfigure.exclude` chính xác chưa?
- **Property source:** cấu hình theo profile, environment, lệnh chạy có tạo exclusion ngoài annotation không?
- **Nguồn gốc bean:** bean do auto-config, `@Bean` thủ công, component scan hay `@Import`?
- **Lỗi phụ thuộc:** ứng dụng đang mong có một bean đã bị auto-config bỏ đi hay không?

Điều tra từ **ứng dụng chạy thực tế**; việc source code có một annotation không đủ chứng minh container đang dùng chính application class đó.

## 11. Kiểm thử tự động để ngăn regression

Có thể dùng test để kiểm tra rằng khi ứng dụng khởi động theo cấu hình đã khai báo, nó không tự tạo datasource. Với dự án ở phần 5, tệp:

**src/test/java/demo/exclude/ExcludeDemoApplicationTest.java**

~~~java
package demo.exclude;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ExcludeDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ExcludeDemoApplicationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void datasourceAutoConfigurationIsExcluded() {
        assertThat(context.getBeanNamesForType(DataSource.class))
                .isEmpty();
    }
}
~~~

Test này tương ứng với **phiên bản có exclude** trong `ExcludeDemoApplication.java`. Với `spring-boot-starter-test` đã khai báo trong `pom.xml`, chạy:

~~~bash
mvn test
~~~

Kỳ vọng **1 test PASS**: không có `DataSource`. Nếu bỏ exclude để làm đối chứng, test sẽ thất bại trong lab vì datasource mặc định trở lại, cho thấy assertion thực sự phát hiện khác biệt. Khi ứng dụng có bean datasource thủ công, cần đổi tiêu chí test thành **cấu hình đã bị exclude hoặc bean cụ thể do auto-config tạo không tồn tại**; không được kiểm tra "không có datasource" nếu hợp đồng ứng dụng là có datasource tự định nghĩa.

Có thể mở rộng test cho:
- Một profile không exclude, profile khác exclude bằng `spring.autoconfigure.exclude`.
- Bean do người dùng tự cung cấp vẫn được giữ khi auto-configuration tương ứng bị loại.
- Một tính năng phụ thuộc datasource không bị bật nhầm khi datasource không có.
- Thay đổi phiên bản Boot không khiến tên trong `excludeName` bị lỗi hoặc mất hiệu lực.

## 12. Lỗi thường gặp

### Lỗi 1 — Nhầm auto-configuration với mọi @Configuration

Một `@Configuration` tự viết có thể được import hoặc component scan; nó **không mặc nhiên** là auto-configuration do Spring Boot tuyển chọn. Exclude chỉ nên trỏ đến các **auto-configuration classes được cơ chế Boot nhận diện**. Nếu muốn bỏ một cấu hình tự định nghĩa, thay đổi cấu hình đăng ký/scan hoặc điều kiện tương ứng.

### Lỗi 2 — Nhầm exclude với loại dependency

`@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)` **không tháo** `spring-boot-starter-jdbc` hoặc driver khỏi JAR. Nếu không muốn chứa một thư viện, phải sửa dependency graph và quá trình đóng gói của build tool.

### Lỗi 3 — Kỳ vọng mọi bean liên quan đều biến mất

Một cấu hình khác hoặc source ứng dụng vẫn có thể tạo cùng bean type. Exclude một auto-config **không cấm** bean đó tồn tại. Chỉ có kiểm tra bean thực tế và nguồn đăng ký mới kết luận được.

### Lỗi 4 — Đặt @EnableAutoConfiguration thêm vào @SpringBootApplication

`@SpringBootApplication` đã chứa `@EnableAutoConfiguration`. Không cần thêm annotation lặp chỉ để viết `exclude`. Hãy đặt exclusion trên nơi rõ ràng và có hiệu lực.

### Lỗi 5 — Sai package khi dùng excludeName

Ví dụ Boot 3.3:

~~~text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Tên ngắn `DataSourceAutoConfiguration` không phải FQCN. Khi nâng cấp Boot, package có thể thay đổi, nên kiểm tra tài liệu API theo phiên bản.

### Lỗi 6 — Exclude để chữa lỗi cấu hình bắt buộc

Ứng dụng cần database nhưng datasource auto-config báo lỗi vì thiếu driver/URL là một sự cố cần được sửa đúng nguyên nhân. Loại auto-config sẽ khiến dependency của bean khác thiếu hoặc làm mất chức năng.

### Lỗi 7 — Nhầm @ComponentScan(excludeFilters) với exclude của auto-config

`excludeFilters` tác động đến thành phần được **component scan** phát hiện; `exclude` của `@SpringBootApplication` chuyển cho cơ chế **auto-configuration import selection**. Hai cơ chế chọn đối tượng khác nhau.

### Lỗi 8 — Dùng exclusion để thay thế điều kiện kích hoạt

Nếu starter hỗ trợ một property chuẩn để tắt một tính năng nhỏ, nên xem xét property đó trước khi loại toàn bộ auto-configuration. Loại cả cấu hình có thể ảnh hưởng những bean nền khác.

### Lỗi 9 — Copy cấu hình từ một phiên bản Spring Boot khác

Tên class, package và tập auto-configuration có thể thay đổi ở các phiên bản lớn. Ví dụ code Boot 3.3 sử dụng `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`; kiểm tra API riêng của Boot 4 nếu ứng dụng chạy phiên bản đó.

### Lỗi 10 — Không kiểm thử những bean phụ thuộc

Sau khi bỏ một auto-configuration, bean khác có thể bị condition loại hoặc thất bại khi inject dependency. Kiểm tra cả mục tiêu loại trừ và các tính năng dựa trên nó.

## 13. Bài tập suy luận

**Bài 1.** Lớp chính dùng:

~~~java
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
~~~

Nhưng source khác có:

~~~java
@Bean
DataSource dataSource() { /* trả về DataSource hợp lệ */ }
~~~

Kết quả có chắc không có bean `DataSource` không? **Không.** Exclude chỉ ngăn auto-config tạo bean; `@Bean` do người dùng khai báo vẫn có thể đăng ký.

**Bài 2.** Ứng dụng dùng `@SpringBootApplication`. Có cần thêm `@EnableAutoConfiguration(exclude=...)` để bỏ một auto-config không? **Không.** Dùng `exclude` trực tiếp trên `@SpringBootApplication`.

**Bài 3.** Không có class auto-config tùy chọn trên compile classpath nhưng muốn khai báo một exclusion theo tên, dùng thuộc tính nào? **`excludeName`**, viết FQCN dưới dạng chuỗi.

**Bài 4.** Muốn bỏ một `@Service` do component scan tạo, có nên viết `@SpringBootApplication(exclude=MyService.class)`? **Không.** Đây không phải auto-configuration candidate; thay đổi scan/điều kiện đăng ký bean.

**Bài 5.** Exclude `DataSourceAutoConfiguration` có làm biến mất H2 trong Maven dependencies không? **Không.** Classpath chỉ thay đổi khi sửa cấu hình dependency/build.

**Bài 6.** Nếu dùng cùng phiên bản Boot, `@SpringBootApplication(exclude=X.class)` và `@Configuration + @EnableAutoConfiguration(exclude=X.class)` có cùng tác động loại X khỏi auto-configuration không? **Có.** Nhưng `@SpringBootApplication` còn gồm component scan và `@SpringBootConfiguration`; hai cách **không tương đương toàn bộ** về cấu trúc context.

**Bài 7.** Có nên dùng exclude nếu thiếu cấu hình datasource khiến app thật sự cần DB không chạy? **Không phải bước sửa mặc định.** Cần sửa URL/driver/profile/credentials hoặc các dependency đúng với chức năng bắt buộc.

## 14. Checklist áp dụng an toàn

1. Xác định **auto-configuration class chính xác** đang tạo bean/hành vi không mong muốn; dùng `--debug` và condition report nếu cần.
2. Xác nhận đây là **auto-configuration được Spring Boot nhận diện**, không phải một `@Configuration` / `@Service` thường.
3. Làm rõ **vì sao cần loại trừ** và các bean/tính năng phụ thuộc nó; tránh che lỗi cấu hình bắt buộc.
4. Chọn khai báo: application class chuẩn → `@SpringBootApplication(exclude=...)`; cấu hình tùy chỉnh → `@EnableAutoConfiguration(exclude=...)`.
5. Nếu class không tham chiếu được tại compile time, dùng `excludeName` và **FQCN đúng phiên bản**.
6. Nếu cần quản lý bằng môi trường thay vì code, cân nhắc `spring.autoconfigure.exclude`.
7. Đóng gói, chạy lại **đúng profile/classpath/artifact triển khai** và quan sát bean thực tế.
8. Kiểm tra condition report, stack trace và các bean downstream để xác nhận việc loại trừ **không làm mất chức năng cần thiết**.
9. Viết test xác nhận hành vi quan trọng: cấu hình bị loại không tự tạo bean ngoài ý định, và bean người dùng tự tạo được giữ theo thiết kế.

**Ghi nhớ:** `exclude` trên `@SpringBootApplication` và `@EnableAutoConfiguration` nhắm tới **cùng tập auto-configuration**. Sự khác biệt chính là cách tổ chức class cấu hình; `excludeName` thay class literal bằng tên class đầy đủ; không cách nào trong số đó thay thế việc quản lý dependency hoặc bean do ứng dụng tự tạo.

## 15. Tài liệu chuẩn để kiểm tra theo phiên bản

- [Spring Boot 3.3.13 Javadoc — @SpringBootApplication](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html).
- [Spring Boot 3.3.13 Javadoc — @EnableAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html).
- [Spring Boot 3.3.13 Javadoc — DataSourceAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html).
- [Spring Boot Reference — Auto-configuration / Disabling Specific Auto-configuration Classes](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).