# @SpringBootApplication kết hợp cấu hình ứng dụng, quét thành phần và tự cấu hình

## 1. Mục tiêu của bài học

Trong ứng dụng Spring Boot, lớp khởi động thường rất ngắn:

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Một annotation duy nhất ở đây thực hiện vai trò của **ba nhóm cấu hình**:

1. Đánh dấu lớp gốc là **cấu hình ứng dụng** để Spring có thể đọc các định nghĩa bean do ứng dụng cung cấp.
2. Bật **component scanning** để tìm những component trong package phù hợp.
3. Bật **auto-configuration** để Spring Boot xem xét các cấu hình mặc định dựa trên thư viện, môi trường và các bean hiện có.

Hiểu chính xác ba vai trò này giúp giải thích vì sao một `@Service` được inject, vì sao phương thức `@Bean` được xử lý, và vì sao một `JdbcTemplate` hoặc `DataSource` có thể xuất hiện dù ứng dụng không tự viết lớp cấu hình cho nó.

Điểm cần nhớ: `@SpringBootApplication` **không tự tạo mọi bean ngay lập tức**. Nó cung cấp điểm vào để Spring phân tích cấu hình và đăng ký bean definitions; `ApplicationContext` cùng `BeanFactory` mới quản lý việc tạo đối tượng, giải quyết dependency và vòng đời bean.

## 2. Ba annotation hợp thành @SpringBootApplication

Về mặt chức năng chính, có thể đọc:

```java
@SpringBootApplication
```

như sự kết hợp của:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
```

Đây là cách **giải thích ba vai trò cốt lõi**, không phải lời hứa rằng thay trực tiếp một annotation bằng ba dòng trên sẽ luôn giữ nguyên mọi thuộc tính alias và bộ lọc mặc định. `@SpringBootApplication` có những chi tiết tích hợp riêng, chẳng hạn các bộ lọc liên quan đến component scanning và các thuộc tính chuyển tiếp.

| Thành phần | Chịu trách nhiệm | Đầu vào điển hình | Kết quả |
| --- | --- | --- | --- |
| `@SpringBootConfiguration` | Cấu hình gốc của ứng dụng | Lớp khởi động cùng các phương thức `@Bean`/`@Import` | Bean definitions từ cấu hình tường minh |
| `@ComponentScan` | Phát hiện component ứng dụng | Package gốc và các package con | Bean definitions cho `@Component`, `@Service`, `@Controller`, `@Repository`, `@Configuration`... |
| `@EnableAutoConfiguration` | Kích hoạt lựa chọn auto-configuration | Classpath, properties, ứng dụng web/non-web, bean definitions có sẵn | Các cấu hình/bean mặc định **khi điều kiện khớp** |

Ba đường dẫn đều đưa kết quả vào **cùng Spring IoC container**. Định nghĩa bean có nguồn khác nhau vẫn được Spring Framework xử lý bằng cơ chế quản lý bean nhất quán.

### 2.1. @SpringBootConfiguration: lớp gốc là cấu hình Spring

`@SpringBootConfiguration` là annotation chuyên biệt của Boot, được meta-annotate bằng `@Configuration`. Vì vậy lớp mang `@SpringBootApplication` có thể khai báo `@Bean`, `@Import` và những phần cấu hình Spring thông thường:

```java
@SpringBootApplication
public class DemoApplication {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Đoạn này minh họa ngữ nghĩa của `@Bean` và cần import `java.time.Clock`, `org.springframework.context.annotation.Bean`, cùng các annotation Boot để dùng trong chương trình thật. Spring phân tích phương thức `applicationClock()` thành bean definition; với singleton mặc định, bean sẽ được tạo khi container cần khởi tạo nó.

Điểm quan trọng:

- `@Bean` là cấu hình **do ứng dụng chủ động khai báo**; nó không phải auto-configuration chỉ vì được đặt trong lớp Boot.
- Lớp gốc thường chỉ chứa `main()` và phần cấu hình nhỏ; có thể tách các nhóm cấu hình vào những lớp `@Configuration` khác để dễ bảo trì.
- Spring Boot dùng `@SpringBootConfiguration` như dấu mốc cấu hình gốc. Một số cơ chế kiểm thử Boot có thể tìm ngược lên package để xác định lớp gốc này.
- `@SpringBootApplication` hỗ trợ thuộc tính `proxyBeanMethods`. Giá trị mặc định là `true`; khi cần tránh proxy cho các lời gọi giữa phương thức `@Bean`, có thể dùng `proxyBeanMethods=false`. Không nên tự gọi một `@Bean` method như phương thức Java bình thường để thay thế dependency injection.

### 2.2. @ComponentScan: phát hiện thành phần của ứng dụng

`@ComponentScan` tìm các lớp phù hợp trong phạm vi package được quét và đăng ký bean definition, ví dụ:

```java
@Service
public class PriceService {
    public int applyDiscount(int price) {
        return price - 10;
    }
}
```

Các stereotype như `@Service`, `@Repository`, `@Controller` đều là những dạng hoặc meta-annotation của `@Component`. Một lớp `@Configuration` trong vùng quét cũng có thể được tìm thấy và tiếp tục đóng góp các bean từ phương thức `@Bean`.

**Phạm vi mặc định:** Spring bắt đầu quét từ package chứa lớp đánh dấu `@SpringBootApplication` và các package con. Vì vậy vị trí lớp main là một quyết định tổ chức mã quan trọng.

Ví dụ cấu trúc package phù hợp:

```text
com.example.store
├── StoreApplication.java          (@SpringBootApplication)
├── config
│   └── PaymentConfiguration.java  (@Configuration)
├── service
│   └── OrderService.java          (@Service)
├── repository
│   └── OrderRepository.java       (@Repository)
└── web
    └── OrderController.java       (@RestController)
```

Nếu `StoreApplication` nằm tại `com.example.store`, những class trên thuộc các package con nên có thể được scan. Nếu đặt `StoreApplication` sâu ở `com.example.store.launcher`, thì `com.example.store.service` lại là **package anh em**, không thuộc phạm vi quét mặc định.

Cần phân biệt:

- **Classpath có class** không có nghĩa **component scan sẽ đăng ký class đó**; class phải nằm trong vùng quét hoặc được đưa vào container theo cơ chế khác.
- **Được scan** không đảm bảo bean được tạo thành công; dependency thiếu, điều kiện `@Profile`, cấu hình mâu thuẫn hoặc lỗi initialization vẫn có thể cản startup.
- `@Bean` trong một lớp cấu hình chỉ được xử lý khi lớp cấu hình đó thực sự được đưa vào hệ thống cấu hình qua scan, `@Import` hoặc cách đăng ký hợp lệ khác.

### 2.3. @EnableAutoConfiguration: kích hoạt cấu hình mặc định có điều kiện

`@EnableAutoConfiguration` là cơ chế khiến Boot lựa chọn các lớp auto-configuration theo điều kiện. Trong Spring Boot 3.x, các JAR cung cấp auto-configuration thường khai báo ứng viên trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File này chứa **tên lớp đầy đủ** của các auto-configuration. Đây là cơ chế đăng ký ứng viên khác với việc quét `@Component` của ứng dụng.

Ví dụ khái niệm:

```java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
class RemoteClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
```

`RemoteClient` trong ví dụ là lớp giả định, nên đoạn này chỉ minh họa điều kiện chứ không phải mã Java độc lập. Nó diễn đạt: khi lớp cần thiết hiện diện và chưa có bean tương ứng, cấu hình có thể cung cấp một bean mặc định. Nếu điều kiện không thỏa, định nghĩa bean ấy có thể **không được đăng ký**.

Những điều kiện phổ biến gồm:

- `@ConditionalOnClass`: một lớp/thư viện có trên classpath.
- `@ConditionalOnMissingBean`: chưa có bean phù hợp ở thời điểm điều kiện được xét.
- `@ConditionalOnBean`: có bean cần thiết.
- `@ConditionalOnProperty`: thuộc tính cấu hình đáp ứng yêu cầu.
- `@ConditionalOnWebApplication`: context thuộc loại web phù hợp.

Không có quy tắc “thêm dependency là Boot chắc chắn tạo bean”. Auto-configuration còn phụ thuộc các điều kiện khác, property, loại ứng dụng, exclusions và bean do chính ứng dụng khai báo.

## 3. Ba cơ chế hội tụ trong một ApplicationContext

Xét các nguồn bean khác nhau:

```text
                      @SpringBootApplication
                                |
             +------------------+--------------------+
             |                  |                    |
             v                  v                    v
  @SpringBootConfiguration  @ComponentScan  @EnableAutoConfiguration
  Cấu hình tường minh       Phát hiện       Chọn auto-configuration
  của ứng dụng              component       có điều kiện
             |                  |                    |
             +------------------+--------------------+
                                |
                                v
                       BeanDefinitionRegistry
                   (đăng ký bean definitions)
                                |
                                v
                   ApplicationContext / BeanFactory
                    (DI, khởi tạo, lifecycle)
                                |
                                v
                         Bean instances
```

Sơ đồ chỉ mô tả sự kết hợp về trách nhiệm. Trong thực tế, Spring có nhiều bước xử lý `@Configuration`, import selector, `BeanDefinitionRegistryPostProcessor`, kiểm tra condition và khởi tạo bean.

**Mốc thời gian khái niệm:**

1. `SpringApplication.run(...)` chuẩn bị `Environment`, quyết định loại context thích hợp và đưa lớp ứng dụng vào nguồn cấu hình.
2. Trong quá trình `refresh()`, Spring xử lý lớp cấu hình, component scan và imports, rồi đăng ký các bean definitions hợp lệ.
3. Auto-configuration được lựa chọn trong pha xử lý cấu hình, dựa trên các điều kiện có hiệu lực; những bean mặc định thích hợp được đăng ký.
4. Spring giải quyết dependency, chạy các processor và khởi tạo các singleton không lazy trong giai đoạn thích hợp.
5. Sau khi context được refresh thành công, Boot gọi các `ApplicationRunner`/`CommandLineRunner` đã đăng ký và tiến tới trạng thái sẵn sàng.

Vì vậy, `@ComponentScan` và `@EnableAutoConfiguration` thường cung cấp **các tập hợp định nghĩa bean khác nhau**, nhưng bean do hai cơ chế tạo ra có thể phụ thuộc lẫn nhau. Ví dụ một `@Service` ứng dụng nhận `JdbcTemplate` do Boot tự cấu hình, không cần hai container riêng.

## 4. Ví dụ chạy được: ba nguồn bean trong cùng một ứng dụng

Ví dụ dùng **Java 17 trở lên, Spring Boot 3.3.13 và Maven**. Ứng dụng không mở web server; ta thêm `spring-boot-starter-jdbc` cùng H2 embedded database để Boot có thể auto-configure `DataSource` và `JdbcTemplate`.

Chúng ta sẽ có:

- `@SpringBootApplication`: cung cấp class khởi động và một bean `ApplicationRunner`.
- `@Service`: được tìm thấy qua component scanning.
- `@Configuration` + `@Bean`: cung cấp `GreetingTemplate` do ứng dụng tự định nghĩa.
- `JdbcTemplate`: do Spring Boot tự cấu hình vì dependency và điều kiện phù hợp.

### 4.1. Cấu trúc tệp

```text
spring-boot-annotation-demo/
├── pom.xml
└── src/main/java/example/bootlesson/
    ├── BootLessonApplication.java
    ├── config/
    │   └── GreetingConfiguration.java
    ├── model/
    │   └── GreetingTemplate.java
    └── service/
        └── GreetingService.java
```

Chú ý `BootLessonApplication` nằm ở `example.bootlesson`, tức **package cha** của các lớp còn lại. Nhờ vậy component scan mặc định tìm được `GreetingConfiguration` và `GreetingService` mà không cần chỉ định package thủ công.

### 4.2. pom.xml

```xml
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

    <groupId>example</groupId>
    <artifactId>spring-boot-annotation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-starter-jdbc` mang các thành phần JDBC, `JdbcTemplate`, DataSource và connection pool cần thiết vào classpath; H2 giúp Boot phát hiện một embedded database mà không phải cung cấp URL database ngoài. Starter chỉ mang dependency vào; **các auto-configuration mới đánh giá điều kiện để đăng ký bean**.

### 4.3. Model do ứng dụng định nghĩa

**`src/main/java/example/bootlesson/model/GreetingTemplate.java`**

```java
package example.bootlesson.model;

public record GreetingTemplate(String prefix) {
    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
```

Đây là record Java 17 thông thường; **không có `@Component`**. Nó chưa là Spring bean nếu chưa được đăng ký qua cấu hình.

### 4.4. Bean từ cấu hình ứng dụng

**`src/main/java/example/bootlesson/config/GreetingConfiguration.java`**

```java
package example.bootlesson.config;

import example.bootlesson.model.GreetingTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    GreetingTemplate greetingTemplate() {
        return new GreetingTemplate("Xin chào");
    }
}
```

`GreetingConfiguration` là một component cấu hình được scan. Spring xử lý `@Bean greetingTemplate()` và đăng ký bean definition; `GreetingTemplate` trở thành bean khi container tạo nó.

`proxyBeanMethods=false` ở đây phù hợp vì các phương thức `@Bean` không tự gọi nhau. Nếu thực sự cần bean khác trong cấu hình, có thể inject qua tham số phương thức `@Bean` hoặc constructor thay vì tự gọi phương thức để tránh nhầm lẫn với lời gọi Java trực tiếp.

### 4.5. Service được tìm qua component scanning

**`src/main/java/example/bootlesson/service/GreetingService.java`**

```java
package example.bootlesson.service;

import example.bootlesson.model.GreetingTemplate;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingTemplate template;

    public GreetingService(GreetingTemplate template) {
        this.template = template;
    }

    public String hello(String name) {
        return template.greet(name);
    }
}
```

`@Service` khiến lớp trở thành ứng viên component scan. Spring tạo `GreetingService` và inject `GreetingTemplate` do cấu hình ứng dụng cung cấp. Đây là một ví dụ **constructor injection** rõ ràng, không phải gọi `new GreetingService(...)` thủ công.

### 4.6. Lớp gốc và bean do auto-configuration tạo

**`src/main/java/example/bootlesson/BootLessonApplication.java`**

```java
package example.bootlesson;

import example.bootlesson.service.GreetingService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class BootLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootLessonApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(GreetingService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("APP_CONFIG: " + service.hello("Spring Boot"));
            String value =
                jdbc.queryForObject("SELECT 'JdbcTemplate active'", String.class);
            System.out.println("AUTO_CONFIG: " + value);
        };
    }
}
```

Ở đây có ba cơ chế cùng hoạt động:

1. Lớp root `@SpringBootApplication` có phương thức `@Bean demonstrate(...)`, nghĩa là bean `ApplicationRunner` xuất phát từ **cấu hình ứng dụng**.
2. `GreetingService` và `GreetingConfiguration` ở các package con được component scan phát hiện; `GreetingConfiguration` lại khai báo `GreetingTemplate` thông qua `@Bean`.
3. Spring Boot sử dụng classpath và điều kiện của JDBC auto-configuration để cung cấp `DataSource` và `JdbcTemplate`. `ApplicationRunner` nhận `JdbcTemplate` thông qua DI như mọi bean khác.

**Chạy chương trình:**

```bash
mvn -q -DskipTests package
java -jar target/spring-boot-annotation-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Ngoài banner và log startup, chương trình in chính xác hai dòng do `ApplicationRunner` tạo ra:

```text
APP_CONFIG: Xin chào, Spring Boot!
AUTO_CONFIG: JdbcTemplate active
```

**Vì sao output như vậy?**

- `APP_CONFIG`: `GreetingService` nhận `GreetingTemplate("Xin chào")`; phương thức `hello("Spring Boot")` tạo ra lời chào tương ứng.
- `AUTO_CONFIG`: H2 chạy truy vấn SQL chọn một chuỗi hằng, nên `JdbcTemplate#queryForObject(...)` trả về `JdbcTemplate active`.
- `ApplicationRunner` được Boot gọi sau khi context refresh thành công. Vì không có `spring-boot-starter-web`, ứng dụng ở chế độ non-web và không cần mở HTTP port.

Khi quan sát ví dụ này, điều cần chứng minh không phải rằng mọi starter đều hoạt động hệt nhau, mà là **bean từ cấu hình ứng dụng, component scan và auto-configuration cùng được Spring IoC quản lý và inject bằng một cơ chế**.

## 5. scanBasePackages và scanBasePackageClasses thay đổi điều gì?

Khi không thể đặt lớp main tại package cha, `@SpringBootApplication` có thể chỉ rõ các package component scanning:

```java
@SpringBootApplication(scanBasePackages = {
    "example.bootlesson.service",
    "example.bootlesson.config"
})
public class BootLessonApplication {
}
```

Hoặc chọn package theo type để tránh chuỗi dễ sai chính tả:

```java
@SpringBootApplication(scanBasePackageClasses = {
    GreetingService.class,
    GreetingConfiguration.class
})
public class BootLessonApplication {
}
```

Hai đoạn này minh họa thuộc tính annotation và giả định có các class/import phù hợp; chúng không thay thế nguyên tệp `BootLessonApplication.java` trong ví dụ runnable trước đó.

`scanBasePackages` là alias chuyển tới `@ComponentScan(basePackages = ...)`, còn `scanBasePackageClasses` chuyển tới `@ComponentScan(basePackageClasses = ...)`.

**Giới hạn cực kỳ quan trọng:** hai thuộc tính này ảnh hưởng **component scan**. Chúng **không** đồng thời thay đổi mọi vùng dò tìm khác:

- Không làm thay đổi mặc định phạm vi quét JPA entity bằng `@EntityScan`.
- Không làm thay đổi trực tiếp phạm vi quét Spring Data repository bằng những annotation `@Enable...Repositories`.
- Không làm danh sách auto-configuration JAR chuyển thành component scan.
- Không nên được dùng như cách thay thế hàng loạt cho tổ chức package nhất quán của ứng dụng.

Spring Boot còn có khái niệm **auto-configuration package**, thường gắn với package của lớp bật `@EnableAutoConfiguration`. Một số auto-configuration dùng thông tin package gốc này để thiết lập tính năng phù hợp. Vì vậy thay `scanBasePackages` có thể sửa việc quét `@Service`, nhưng chưa chắc xử lý đúng entity/repository nếu chúng đặt bên ngoài package gốc.

**Cách đặt package dễ quản lý nhất:** lớp `@SpringBootApplication` ở package gốc của ứng dụng, các vùng `config`, `service`, `repository`, `web`, `domain` nằm trong package con. Nếu cố ý chia module/package đặc biệt, hãy cấu hình từng cơ chế đúng trách nhiệm.

## 6. Khi nào cần @Import hoặc cấu hình tường minh?

Không phải mọi cấu hình phải được scan. `@Import` cho phép đưa lớp cấu hình cụ thể vào hệ thống Spring mà không mở rộng vùng scan một cách quá rộng:

```java
@Configuration(proxyBeanMethods = false)
@Import(ExternalPaymentConfiguration.class)
class PaymentFeatureConfiguration {
}
```

Đây là đoạn minh họa: `ExternalPaymentConfiguration` là tên giả định và cần có class/import thật. Khi lớp `PaymentFeatureConfiguration` được Spring xử lý, `@Import` đưa cấu hình tham chiếu vào quá trình đăng ký bean definition.

So sánh:

| Tình huống | Cơ chế thường phù hợp |
| --- | --- |
| Phát hiện các service/controller/repository do ứng dụng sở hữu trong cây package | Component scanning |
| Tạo bean khi cần factory method hoặc thư viện bên thứ ba không có stereotype | `@Configuration` + `@Bean` |
| Đưa một lớp cấu hình cụ thể từ ngoài cây package vào | `@Import` |
| Cung cấp mặc định cho thư viện/starter theo điều kiện | Auto-configuration, với `@AutoConfiguration` và metadata `.imports` |
| Điều chỉnh cách một auto-config chính thức hoạt động | Property/bean override có chủ đích/exclusion theo tài liệu |

Không nên thêm `@ComponentScan` quét toàn bộ `org.springframework` hoặc package gốc quá rộng để “tìm” bean auto-configuration. Điều này có thể đăng ký các thành phần không chủ định, gây xung đột hoặc làm startup khó dự đoán.

## 7. Auto-configuration nhường quyền cho ứng dụng như thế nào?

Giả sử một auto-configuration có logic:

```java
@AutoConfiguration
class SampleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Formatter.class)
    Formatter defaultFormatter() {
        return new Formatter("default");
    }
}
```

`Formatter` ở đây là kiểu minh họa; đoạn code không độc lập. Khi ứng dụng đã đăng ký bean `Formatter` phù hợp trước khi điều kiện được kiểm tra, `defaultFormatter()` có thể **không được đăng ký**. Đây là hành vi **back off**, một lựa chọn phổ biến giúp ứng dụng thay đổi mặc định.

Phân biệt ba tình huống:

| Cơ chế | Tác dụng | Có xóa bean khác không? |
| --- | --- | --- |
| `@ConditionalOnMissingBean` | Quyết định có đăng ký bean mặc định hay không | Không cần tạo định nghĩa mặc định khi điều kiện không khớp |
| `@Primary` | Ưu tiên một bean khi có nhiều ứng viên autowire theo type | Không |
| Bean definition overriding | Một định nghĩa trùng tên thay định nghĩa khác nếu được phép | Có thể thay bean definition cùng tên |

Spring Boot thường tắt bean definition overriding theo mặc định. Đừng nhầm back off với việc Boot âm thầm ghi đè bean ứng dụng.

**Lưu ý về thứ tự:** các điều kiện phụ thuộc vào bean definitions hiện có được xét trong quá trình xử lý cấu hình. Vì vậy `@ConditionalOnMissingBean` dùng trong auto-configuration thích hợp hơn trong cấu hình thông thường của ứng dụng; việc đặt annotation này tùy tiện lên một bean ứng dụng không bảo đảm kết quả mong muốn nếu thứ tự đăng ký khác.

## 8. Kiểm soát auto-configuration ngay tại @SpringBootApplication

Có thể loại trừ một auto-configuration **cụ thể** bằng annotation:

```java
@SpringBootApplication(
    exclude = org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration.class
)
public class BootLessonApplication {
}
```

Hoặc theo tên lớp:

```java
@SpringBootApplication(
    excludeName = "org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration"
)
public class BootLessonApplication {
}
```

Hai ví dụ chỉ minh họa cách cấu hình; **không áp dụng thay thế vào chương trình chạy ở mục 4**, vì loại trừ `JdbcTemplateAutoConfiguration` có thể làm `ApplicationRunner` thiếu bean `JdbcTemplate`.

Một cách tương đương về mục đích cấu hình là property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration
```

Giới hạn:

- `exclude`/`excludeName` dành cho **auto-configuration**, không phải cách chung để loại bỏ một `@Service` do component scanning tạo ra.
- Loại trừ class auto-configuration không đồng nghĩa có bean thay thế; dependency injection vẫn cần các bean tương ứng.
- Khi thay đổi/exclude một cấu hình, kiểm tra những auto-configuration khác phụ thuộc vào nó. Ví dụ thiếu `DataSource` có thể kéo theo thiếu `JdbcTemplate`.
- Các class cụ thể có thể thay đổi giữa các đời Spring Boot; luôn tra đúng phiên bản ứng dụng.

Với nhu cầu tùy biến thông thường, ưu tiên property chính thức hoặc bean tường minh trước khi loại trừ nguyên một auto-configuration lớn.

## 9. Tự kiểm tra hoạt động khi startup

### 9.1. Bật Conditions Evaluation Report

Chạy ví dụ có thêm tùy chọn:

```bash
java -jar target/spring-boot-annotation-demo-0.0.1-SNAPSHOT.jar \
  --spring.main.web-application-type=none --debug
```

Tìm các mục liên quan tới `DataSourceAutoConfiguration` và `JdbcTemplateAutoConfiguration` trong **Conditions Evaluation Report**.

- **Positive matches**: điều kiện tương ứng được đáp ứng.
- **Negative matches**: điều kiện không được đáp ứng; báo cáo thường cho biết vì sao.
- **Exclusions**: auto-configuration bị loại trừ theo cấu hình.

Report giúp giải thích **vì sao một auto-configuration được hoặc không được áp dụng**. Nó không thay thế stack trace nếu một bean đã đăng ký nhưng tạo lỗi.

### 9.2. Một bean có trong registry nhưng chưa khởi tạo?

Khác biệt giữa **định nghĩa bean** và **instance** rất quan trọng. Spring có thể đã đăng ký bean definition nhưng hoãn tạo singleton do `@Lazy` hoặc vì đó là prototype/scope đặc biệt.

Ngược lại, khi `@ConditionalOnMissingBean` làm bean mặc định không được đăng ký, ngay từ đầu bean definition mặc định có thể không tồn tại. Hai tình huống cần hai cách gỡ lỗi khác nhau:

- Định nghĩa không có: xem component scan, `@Import`, điều kiện và exclusions.
- Định nghĩa có nhưng bean không sẵn sàng: xem lazy initialization, dependency, factory method, `BeanPostProcessor` và exceptions.

Có thể dùng `ConfigurableApplicationContext#getBeanFactory()` trong công cụ chẩn đoán để xem metadata như `containsBeanDefinition(name)` hoặc `getBeanDefinition(name)`. Nên ưu tiên constructor injection trong mã nghiệp vụ thay vì gọi `getBean()` để tự quản lý service.

### 9.3. Nhìn từ dependency

Trong ví dụ mục 4:

- Nếu bỏ `spring-boot-starter-jdbc` mà vẫn import `JdbcTemplate`, mã Java **không biên dịch được** vì không còn API JDBC trên compile classpath.
- Nếu giữ JDBC starter nhưng không có H2 và không cung cấp database phù hợp, ứng dụng có thể lỗi do không cấu hình được `DataSource`.
- Nếu `GreetingService` bị chuyển ra ngoài vùng component scanning mà không được đăng ký qua cách khác, `ApplicationRunner` có thể lỗi do không có bean `GreetingService`.
- Nếu giữ tất cả dependency và package đúng, Spring Boot có thể cấu hình infrastructure JDBC; `GreetingTemplate` vẫn do ứng dụng tự định nghĩa.

Đây là những thay đổi ảnh hưởng **các nguyên nhân khác nhau**. Không có một annotation “ma thuật” nào bù được mọi dependency, package hoặc property thiếu.

## 10. Những lỗi phổ biến

### Lỗi 1: Nhầm component scanning với auto-configuration

**Biểu hiện:** “Tôi không đặt package của JDBC config vào `@ComponentScan`, tại sao vẫn có `JdbcTemplate`?”

**Giải thích:** lớp auto-configuration được nạp theo danh sách ứng viên và điều kiện của Boot, không phải do ứng dụng quét package JDBC. `JdbcTemplate` cuối cùng vẫn là Spring bean.

### Lỗi 2: Đặt lớp main quá sâu

**Biểu hiện:** có `@Service` hợp lệ nhưng ứng dụng báo thiếu bean.

**Giải thích:** component scan mặc định chỉ quét từ package gốc xuống các package con. Cần di chuyển lớp main lên package cha phù hợp, cấu hình rõ `scanBasePackageClasses`, hoặc `@Import` khi thích hợp.

### Lỗi 3: Nghĩ rằng mọi @Bean đều do Boot auto-configure

**Giải thích:** `@Bean` do nhóm ứng dụng viết là cấu hình tường minh. Auto-configuration là những cấu hình Boot/thư viện đăng ký có điều kiện theo cơ chế riêng. Cùng được quản lý bởi Spring không khiến nguồn gốc của chúng giống nhau.

### Lỗi 4: Có starter nhưng không thấy bean mong muốn

**Giải thích:** starter thường gom dependency. Auto-configuration có thể không khớp `@ConditionalOnClass`, property, bean hiện có, loại web context hoặc đã bị exclude. Dùng Conditions Evaluation Report để tìm lý do cụ thể.

### Lỗi 5: Dùng scanBasePackages để sửa cả JPA entity và repository

**Giải thích:** các thuộc tính scan của `@SpringBootApplication` chỉ điều khiển component scanning. Đối với JPA/Spring Data, hãy kiểm tra `@EntityScan`, `@EnableJpaRepositories` và phạm vi auto-configuration package thích hợp, thay vì kết luận quét component đã bao phủ tất cả.

### Lỗi 6: Dùng @Primary để ngăn một bean mặc định tồn tại

**Giải thích:** `@Primary` chỉ ảnh hưởng chọn bean khi inject. Muốn thay mặc định, phải xem liệu cấu hình liên quan có back off theo type/name khi bean ứng dụng đã được khai báo hay không.

### Lỗi 7: Quét package quá rộng để chữa thiếu bean

**Giải thích:** quét nhiều thư viện hoặc package gốc không liên quan có thể kéo vào controller, repository hoặc bean không chủ định. Hãy xác định chính xác nguồn của bean cần thiết rồi mở rộng phạm vi phù hợp.

### Lỗi 8: Sao chép @SpringBootApplication cho nhiều lớp cấu hình tùy ý

**Giải thích:** một ứng dụng thường có một lớp gốc rõ ràng. Các nhóm cấu hình bổ sung nên là `@Configuration`/`@Import`. Việc có nhiều lớp mang `@SpringBootConfiguration` trong vùng được kiểm thử tự động dò tìm có thể gây tình huống nhập nhằng cấu hình gốc.

## 11. Cách thiết kế ứng dụng dễ hiểu và dễ bảo trì

Quy trình thực dụng:

1. Đặt lớp `@SpringBootApplication` ở package gốc bao trùm phần lớn mã ứng dụng.
2. Đặt service/controller/repository trong những package con và dùng stereotype phù hợp.
3. Đặt bean tạo qua factory method trong lớp `@Configuration` rõ trách nhiệm.
4. Thêm dependency/starter đúng tính năng; kiểm tra auto-configuration trước khi tự viết cấu hình hạ tầng trùng lặp.
5. Dùng properties để điều chỉnh cấu hình mặc định khi module hỗ trợ.
6. Khi bean không xuất hiện hoặc bị mơ hồ, phân biệt **scan**, **configuration**, **condition**, **khởi tạo bean** rồi mới sửa.
7. Khi cần thay default, kiểm tra `@ConditionalOnMissingBean` và hợp đồng cấu hình; khi cần exclude, loại trừ đúng lớp auto-configuration cụ thể.

Bảng chẩn đoán nhanh:

| Triệu chứng | Kiểm tra đầu tiên | Cách xác minh |
| --- | --- | --- |
| `@Service` không được inject | Package của lớp main và service | `@ComponentScan`, vị trí package, `@Profile` |
| `@Bean` không xuất hiện | Lớp `@Configuration` có được xử lý không | Component scan hoặc `@Import` |
| Bean hạ tầng Boot không xuất hiện | Điều kiện auto-configuration | `--debug`, Conditions Evaluation Report |
| Nhiều bean cùng type | Ứng viên và quy tắc chọn | `@Qualifier`, `@Primary`, bean name |
| Có definition nhưng startup lỗi | Dependency/constructor/init callback | Root cause của `BeanCreationException` |
| Đổi scanBasePackages nhưng entity vẫn thiếu | Cơ chế JPA/Spring Data khác component scan | `@EntityScan`/repository configuration |

## 12. Tự kiểm tra kiến thức

**Câu 1.** `@SpringBootApplication` mang những vai trò nào?

**Trả lời:** Cấu hình ứng dụng (`@SpringBootConfiguration`), quét component (`@ComponentScan`) và kích hoạt auto-configuration (`@EnableAutoConfiguration`).

**Câu 2.** Vì sao `@Service` ở package anh em với lớp main có thể không được tìm thấy?

**Trả lời:** Vì mặc định `@ComponentScan` bắt đầu từ package chứa lớp đánh dấu `@SpringBootApplication` và những package con, không tự bao trùm mọi package có trong dự án.

**Câu 3.** Nếu một ứng dụng đã khai báo bean đúng type mà auto-configuration có `@ConditionalOnMissingBean` định cung cấp, chuyện gì thường xảy ra?

**Trả lời:** Nếu điều kiện của auto-configuration được đánh giá khi bean ứng dụng đã được đăng ký và khớp đúng tiêu chí, bean mặc định sẽ back off, tức không được đăng ký.

**Câu 4.** Thêm `scanBasePackages` có tự điều chỉnh JPA entity scanning không?

**Trả lời:** Không. Thuộc tính đó điều chỉnh component scan, còn entity/repository scanning có phạm vi và cấu hình riêng.

**Câu 5.** Trong ví dụ Java 17, bean nào đến từ mỗi nguồn?

**Trả lời:** `ApplicationRunner` và `GreetingTemplate` đến từ phương thức `@Bean` của ứng dụng; `GreetingService` đến từ component scanning; `DataSource` và `JdbcTemplate` đến từ auto-configuration đáp ứng điều kiện của Boot với JDBC starter và H2.

**Câu 6.** Khi cấu hình auto-configuration có negative match, có chắc do `@ComponentScan` không?

**Trả lời:** Không. Điều kiện auto-configuration có thể thất bại vì classpath, bean, property, loại ứng dụng hoặc exclusions. Cần xem báo cáo điều kiện và lý do cụ thể.

## Tài liệu tham khảo

- Spring Boot — Using the `@SpringBootApplication` Annotation: https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework — Classpath Scanning and Managed Components: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
