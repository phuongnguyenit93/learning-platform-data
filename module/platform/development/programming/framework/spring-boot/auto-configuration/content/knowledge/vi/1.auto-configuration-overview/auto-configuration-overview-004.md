# Phân biệt tự cấu hình với quét thành phần, tiêm phụ thuộc và gắn thuộc tính

Trong Spring Boot, **auto-configuration**, **component scanning**, **dependency injection (DI)** và **configuration properties binding** thường diễn ra trong cùng quá trình khởi động. Vì vậy người mới học dễ nghĩ chúng là một. Thực tế, mỗi cơ chế trả lời một câu hỏi khác nhau:

- **Tự cấu hình:** Spring Boot nên cung cấp cấu hình và bean mặc định nào khi xét các thư viện, thuộc tính và bean hiện có?
- **Quét thành phần:** Những lớp do ứng dụng viết, được đánh dấu là component, nằm ở package nào để Spring đăng ký chúng?
- **Tiêm phụ thuộc:** Khi tạo bean, Spring lấy bean phụ thuộc ở đâu và đưa vào constructor/tham số nào?
- **Gắn thuộc tính:** Giá trị từ `application.properties`, YAML, biến môi trường hoặc dòng lệnh được chuyển thành dữ liệu cấu hình có kiểu như thế nào?

Đích của bài học là xác định được **nguồn đăng ký bean**, **điều kiện tạo bean**, **nơi phụ thuộc được tiêm** và **nơi dữ liệu cấu hình được bind**. Bốn câu hỏi này độc lập về trách nhiệm nhưng liên kết trong thực thi.

## 1. Bảng đối chiếu

| Cơ chế | Kích hoạt/công cụ phổ biến | Tạo ra điều gì? | Không tự làm điều gì? |
| --- | --- | --- | --- |
| Auto-configuration | `@EnableAutoConfiguration` (được đưa vào bởi `@SpringBootApplication`), `@AutoConfiguration`, `@Conditional...` | Các bean/bean definition hạ tầng mặc định theo điều kiện | Không quét tùy ý mọi class do ứng dụng viết; không bảo đảm starter nào cũng tạo mọi bean |
| Component scanning | `@ComponentScan`, `@Component`, `@Service`, `@Repository`, `@Controller`, `@Configuration` | Bean definition từ những class được phát hiện trong vùng package | Không tự quyết định cấu hình hạ tầng Boot theo classpath |
| Dependency injection | Constructor injection, tham số `@Bean`, đôi khi `@Autowired` | Liên kết một bean với các bean phụ thuộc thích hợp | Không tự tạo dependency chỉ vì thấy tên type trong constructor |
| Property binding | `@ConfigurationProperties` cùng `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` | Đối tượng cấu hình có kiểu, được nạp từ nguồn thuộc tính | Không tự bảo đảm lớp cấu hình đã được đăng ký làm bean |

**Quan hệ chính:** Component scanning và auto-configuration đều có thể cung cấp **định nghĩa bean**. DI là cơ chế **dùng các bean** để lắp ghép đối tượng. Property binding là cơ chế **chuyển dữ liệu cấu hình** thành trạng thái có kiểu. Một bean do Boot auto-config vẫn có thể được DI vào bean ứng dụng; không có mâu thuẫn.

## 2. Vì sao `@SpringBootApplication` dễ gây nhầm?

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` gộp ba ý nghĩa quan trọng: `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Vì cả scanning và auto-configuration được kích hoạt từ cùng một annotation, chúng có thể trông giống nhau dù đường tìm nguồn bean khác nhau.

- **Scanning** mặc định xét package chứa `DemoApplication` và các package con. `@Service` nằm ngoài phạm vi này thường không được tìm thấy.
- **Auto-configuration** chọn các lớp cấu hình của Boot/thư viện theo danh sách import riêng, không phải vì các lớp đó nằm dưới package ứng dụng. Trong Spring Boot 3.x, file đăng ký auto-config chuẩn là `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Điều kiện như `@ConditionalOnClass`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` có thể bật, tắt hoặc cho phép bean mặc định nhường chỗ.
- **DI** giải quyết phụ thuộc dựa trên những bean phù hợp trong `ApplicationContext`.
- **Binding** chuyển property thành `String`, số, enum, `Duration`, collection, record, v.v. theo khai báo.

Sơ đồ sau thể hiện **quan hệ logic**, không khẳng định thứ tự nội bộ cứng cho từng bước:

```text
        SpringApplication + Environment
                  |
                  v
          ApplicationContext
            /           \
           v             v
   @ComponentScan    Auto-config imports
   tìm @Service,      + @Conditional...
   @Component...           |
           \             /
            v           v
             Bean definitions
                    |
        @ConfigurationProperties:
        đăng ký + binding dữ liệu
                    |
                    v
        Bean creation + DI
                    |
                    v
             Ứng dụng chạy
```

Cách hiểu “Spring quét xong rồi mới auto-config xong, sau đó mới bind xong rồi mới inject” là **quá đơn giản**: Spring xử lý bean definition, điều kiện, tạo bean, binding và injection theo những giai đoạn có liên hệ với nhau. Dùng sơ đồ để hiểu vai trò, không dùng làm biểu đồ thứ tự thực thi tuyệt đối.

## 3. Ví dụ hoàn chỉnh với Java 17+ và Spring Boot 3.3.x

Mục tiêu: `GreetingService` được **component scanning** tìm thấy; `GreetingProperties` được **property binding** tạo dữ liệu từ file; Spring dùng **DI** đưa properties vào service; Boot **auto-config** một `ObjectMapper` vì Jackson hiện diện.

Ví dụ dùng Maven, Spring Boot 3.3.13 và Java 17. Thư mục:

```text
auto-config-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── GreetingProperties.java
    │   └── GreetingService.java
    └── resources/application.properties
```

**`pom.xml`**

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
    <artifactId>auto-config-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

`spring-boot-starter-web` cung cấp các phụ thuộc liên quan Jackson; ta sẽ tắt chế độ web để ví dụ chạy xong thì thoát.

**`src/main/java/com/example/demo/GreetingProperties.java`**

```java
package com.example.demo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "greeting")
public record GreetingProperties(String salutation, String target) {
}
```

Record này không có `@Component`. `@ConfigurationProperties` mô tả nhóm khóa `greeting.*` và kiểu dữ liệu đích. Để Spring tạo bean tương ứng, còn cần đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(GreetingProperties.class)`.

**`src/main/java/com/example/demo/GreetingService.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final GreetingProperties properties;

    public GreetingService(GreetingProperties properties) {
        this.properties = properties;
    }

    public String greet() {
        return properties.salutation() + ", " + properties.target() + "!";
    }
}
```

`@Service` là dạng chuyên biệt của `@Component`: scanning tìm lớp rồi đăng ký bean. Constructor yêu cầu Spring cung cấp `GreetingProperties`: thao tác đó là **dependency injection**, hoàn toàn khác việc scanning phát hiện `GreetingService`.

**`src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner show(GreetingService service, ObjectMapper mapper) {
        return args -> {
            System.out.println("GREETING=" + service.greet());
            System.out.println("MAPPER=" + mapper.getClass().getSimpleName());
        };
    }
}
```

`@ConfigurationPropertiesScan` tìm lớp cấu hình dưới package gốc và đăng ký `GreetingProperties` cho binder. `@Bean` tự khai báo `ApplicationRunner`; Spring cung cấp tham số `GreetingService` và `ObjectMapper` bằng DI. Đối tượng Jackson ở ví dụ đến từ **auto-configuration**, không phải class `@Service` của chúng ta.

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=ERROR
greeting.salutation=Xin chào
greeting.target=Spring Boot
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Hai dòng chương trình tự in (không tính thông điệp riêng của môi trường/Maven):

```text
GREETING=Xin chào, Spring Boot!
MAPPER=ObjectMapper
```

**Lần theo bốn cơ chế:**

1. Component scanning tìm `GreetingService` theo `@Service` và package `com.example.demo`.
2. `@ConfigurationPropertiesScan` đăng ký `GreetingProperties`; binder lấy `greeting.salutation` và `greeting.target` từ nguồn cấu hình, tạo record có giá trị tương ứng.
3. Jackson trên classpath thỏa điều kiện để Boot tự tạo `ObjectMapper` thông qua auto-configuration.
4. DI đưa `GreetingProperties` vào constructor `GreetingService`; tiếp theo đưa `GreetingService` và `ObjectMapper` vào phương thức `show(...)`. Runner in kết quả sau khi context sẵn sàng.

**Thử thay đổi:** đổi `greeting.target=Java` rồi chạy lại. Dòng đầu thành `GREETING=Xin chào, Java!`, vì **dữ liệu được bind** đã thay đổi. Ta không phải đổi phạm vi scan và cũng không viết lại auto-configuration.

## 4. Tách những khác biệt thường bị nhầm

### 4.1. Scanning không phải auto-configuration

Class do ứng dụng viết:

```java
@Service
public class PriceService {
    // Component scanning có thể đăng ký bean này.
}
```

Một auto-configuration trong thư viện thường có mô hình điều kiện như sau. Đây **chỉ là đoạn minh họa**, `SomeClient` cần được thay bằng class thật trong dependency cụ thể:

```java
@AutoConfiguration
@ConditionalOnClass(SomeClient.class)
public class SomeClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    SomeClient someClient() {
        return new SomeClient();
    }
}
```

`@ConditionalOnClass` yêu cầu loại thư viện tồn tại; `@ConditionalOnMissingBean` thường cho phép cấu hình mặc định nhường chỗ cho bean người dùng. Các auto-config khác có thể thêm điều kiện về property, bean, loại ứng dụng web, v.v. Thêm một starter **có thể** kích hoạt auto-config; không có nghĩa mọi bean đều được tạo vô điều kiện.

`@EnableAutoConfiguration` không “cứu” một `@Service` nằm ngoài vùng component scanning. Ngược lại, class auto-config trong JAR bên ngoài package ứng dụng vẫn có thể được import bằng cơ chế của Boot.

### 4.2. DI không phải cách tìm ra bean

```java
public OrderService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Constructor diễn đạt rằng `OrderService` cần một bean `PaymentGateway`. Spring chỉ đáp ứng được nếu **đã có ứng viên phù hợp** trong context, chẳng hạn từ `@Component`, một phương thức `@Bean` hoặc auto-config. Nếu không có, có thể xảy ra `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException`; nếu có nhiều ứng viên cùng kiểu, cần phân giải bằng `@Primary`, `@Qualifier` hoặc cách cấu hình rõ ràng khác. Constructor injection thích hợp cho dependency bắt buộc vì bộc lộ trực tiếp hợp đồng phụ thuộc.

### 4.3. Binding không phải DI và không đồng nghĩa `@Value`

`@ConfigurationProperties(prefix = "mail")` tập hợp các khóa như `mail.host` và `mail.port` thành một đối tượng có kiểu. Binder xử lý chuyển đổi kiểu và có thể phối hợp validation. Sau khi đối tượng đó là bean, DI có thể truyền **cả bean cấu hình** vào service.

`@Value` với placeholder thường đọc một giá trị đơn lẻ; nó thích hợp cho trường hợp nhỏ nhưng không thay thế hoàn toàn mô hình bind nhóm thuộc tính và metadata của `@ConfigurationProperties`.

**Chú ý registration:** một class Java chỉ có `@ConfigurationProperties` chưa chắc được tạo thành bean. Với các loại cấu hình thông thường có thể dùng:

- `@ConfigurationPropertiesScan` để quét các lớp properties hợp lệ trong phạm vi package;
- `@EnableConfigurationProperties(MyProperties.class)` để đăng ký tường minh;
- hoặc bind một bean được đăng ký theo cách phù hợp.

`@ConfigurationPropertiesScan` có chức năng khác `@ComponentScan`. Theo cơ chế scan mặc định của Boot, những class `@Component` không phải mục tiêu của `@ConfigurationPropertiesScan`; tuy vậy một bean component đã được đăng ký vẫn có thể được bind nếu được cấu hình thích hợp.

### 4.4. Định nghĩa bean khác với dữ liệu của bean

Ví dụ đổi `mail.port=8080` sang `mail.port=9090` không nhất thiết thêm hoặc bớt bean: cùng một bean có thể nhận trạng thái cấu hình khác. Ngược lại, một property được dùng trong `@ConditionalOnProperty` có thể quyết định **có đăng ký bean hay không**. Vì vậy phải đọc property trong đúng bối cảnh: property dùng **để bind giá trị** hay property dùng **làm điều kiện tạo bean**.

## 5. Các tình huống trước – sau

| Thay đổi | Hệ quả thường gặp | Kiểm tra ở đâu? |
| --- | --- | --- |
| Chuyển `GreetingService` ra khỏi vùng scan | Không có service bean, kéo theo lỗi DI khi runner cần nó | Package main class, `@ComponentScan` |
| Bỏ `@ConfigurationPropertiesScan` và không đăng ký record theo cách khác | Không có `GreetingProperties` cho constructor | `@EnableConfigurationProperties` hoặc cách registration khác |
| Đổi `greeting.target` | Nội dung lời chào thay đổi | Binder, tên key, nguồn cấu hình và thứ tự ưu tiên |
| Thêm starter/JAR có class tương ứng | Một số điều kiện auto-configuration có thể chuyển từ không khớp sang khớp | Classpath và Condition Evaluation Report |
| Tự khai báo bean `ObjectMapper` phù hợp | Auto-config mặc định của Jackson thường nhường chỗ theo `@ConditionalOnMissingBean` | Bean người dùng, điều kiện auto-config |
| Có hai bean `PaymentGateway` mà không có quy tắc chọn rõ ràng | DI có thể báo nhiều ứng viên | Qualifier, primary, tên/kiểu bean |
| Chuyển `@Service` thành class thường nhưng không khai báo `@Bean` | Bean không còn được đăng ký qua scan | Annotation và các cơ chế đăng ký khác |

Không thể suy từ việc một bean đang tồn tại rằng nó **chắc chắn do scanning tạo**. Hãy hỏi nguồn đăng ký nào chịu trách nhiệm.

## 6. Quan sát cơ chế khi gỡ lỗi

**Kiểm tra auto-configuration:** bật debug khi chạy:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
```

`Condition Evaluation Report` giúp tìm auto-config được áp dụng hoặc không áp dụng và những điều kiện liên quan. Nếu thêm Spring Boot Actuator và cấu hình expose phù hợp, endpoint `/actuator/conditions` là một cách khác để xem điều kiện; endpoint này **không mặc định public**.

**Kiểm tra scanning:** xác định package của `@SpringBootApplication`, vị trí các `@Service`/`@Component`, khai báo `@ComponentScan` tùy chỉnh và các annotation như `@Profile` có thể làm bean không xuất hiện. Không nên khắc phục bằng cách quét toàn bộ package của thư viện ngoài.

**Kiểm tra DI:** đọc exception về thiếu bean, nhiều ứng viên, qualifier hoặc dependency vòng; kiểm tra thật sự có bean definition nào khớp type đang yêu cầu. Tham số constructor là **nơi phụ thuộc được yêu cầu**, không phải bằng chứng bean sẽ được tạo.

**Kiểm tra binding:** rà prefix, tên key, profile hoạt động, biến môi trường, kiểu đích và validation. Cấu hình không hợp lệ có thể khiến binding lỗi, từ đó bean/service dùng nó không khởi tạo được. Khi xử lý cấu hình nhạy cảm, không in token/mật khẩu ra log.

**Kiểm tra tùy biến default:** nếu bean hạ tầng của Boot biến mất sau khi ứng dụng khai báo bean cùng loại, tìm `@ConditionalOnMissingBean` và các điều kiện khác trước khi kết luận auto-config gặp lỗi.

## 7. Những kết luận sai cần tránh

- **“`@SpringBootApplication` quét tất cả các package.”** Không. Component scanning mặc định bị giới hạn bởi package gốc.
- **“Auto-configuration chính là DI.”** Không. Auto-config có thể cung cấp bean; DI đưa bean vào nơi cần.
- **“Có `@ConfigurationProperties` là chắc chắn binding chạy.”** Không, phải có cách đăng ký phù hợp và nguồn cấu hình hợp lệ.
- **“Tất cả property đều chỉ để gán giá trị.”** Không. Một số property là điều kiện bật/tắt bean.
- **“Thêm starter luôn tạo mọi bean mong muốn.”** Không, auto-config thường phụ thuộc nhiều điều kiện.
- **“Bean của người dùng luôn bị Boot ghi đè.”** Không. Nhiều auto-config nhường chỗ khi bean tương ứng đã tồn tại, nhưng cần kiểm tra từng trường hợp.

## 8. Câu hỏi tự kiểm tra

1. Một `@Service` nằm ngoài vùng scan khiến constructor khác báo thiếu bean: nguyên nhân bắt đầu ở **scanning**, sau đó biểu hiện thành **lỗi DI**.
2. `ObjectMapper` có sẵn dù không viết `@Bean`: hãy kiểm tra **Jackson auto-configuration** cùng classpath/conditions; việc tiêm mapper vẫn là **DI**.
3. `GreetingService` giữ nguyên nhưng đổi câu chào trong properties: đó là thay đổi **dữ liệu binding**, không phải scan một class mới.
4. Muốn dùng implementation riêng thay mặc định của Boot: xem auto-config, nhất là `@ConditionalOnMissingBean`, và đăng ký bean người dùng phù hợp.
5. `@ConfigurationPropertiesScan` có thay cho `@ComponentScan` được không? **Không**: hai cách scan phục vụ hai nguồn đăng ký khác nhau.

Khi đọc một ứng dụng Spring Boot, luôn tách riêng bốn câu hỏi: **Ai đăng ký bean? Điều kiện nào cho phép bean tồn tại? Giá trị cấu hình được bind ở đâu? Bean được inject vào chỗ nào?** Trả lời bốn câu này giúp phân biệt rõ tự cấu hình, quét thành phần, tiêm phụ thuộc và gắn thuộc tính.