# Vai trò của tự cấu hình trong mối quan hệ giữa Spring Framework và Spring Boot

## 1. Vị trí của auto-configuration trong bức tranh tổng thể

**Spring Framework** cung cấp nền tảng để ứng dụng Java hoạt động: IoC container (`ApplicationContext`), quản lý bean, Dependency Injection (DI), vòng đời bean, cấu hình bằng `@Configuration`/`@Bean`, môi trường và nhiều mô-đun như Spring MVC, giao dịch và truy cập dữ liệu. Nhà phát triển vẫn phải quyết định và khai báo những thành phần ứng dụng cần dùng.

**Spring Boot** xây trên Spring Framework. Một trong những đóng góp quan trọng nhất của Boot là **auto-configuration (tự cấu hình)**: dựa trên thư viện có mặt, thuộc tính cấu hình, loại ứng dụng và những bean người dùng đã khai báo, Boot *đề xuất* các bean/cấu hình hạ tầng thường dùng. Điều đó giúp giảm cấu hình lặp lại mà vẫn giữ quyền kiểm soát của ứng dụng.

> Ý chính: **Spring Framework thực thi cơ chế IoC/DI và xử lý các bean; Spring Boot tự quyết định có nên đóng góp một số định nghĩa bean mặc định vào cùng container ấy hay không.** Auto-configuration không tạo ra một IoC container khác và không thay thế kiến trúc nền tảng của Spring.

Ví dụ: một ứng dụng có thư viện web phù hợp trên classpath thì Boot có thể cấu hình các thành phần MVC, web server nhúng và các tiện ích liên quan; ứng dụng không có các điều kiện đó thì phần cấu hình tương ứng không được áp dụng. Nếu ứng dụng cung cấp một bean của loại mà auto-configuration được thiết kế để nhường chỗ, Boot không đăng ký bean mặc định đó.

## 2. So sánh trách nhiệm của hai lớp

| Vấn đề | Spring Framework | Spring Boot/auto-configuration |
| --- | --- | --- |
| Tạo và quản lý bean | `BeanFactory`/`ApplicationContext`, DI, scope, lifecycle | Đăng ký thêm **định nghĩa bean** được lựa chọn có điều kiện vào container của Framework |
| Cấu hình thủ công | Hỗ trợ `@Configuration`, `@Bean`, `@Import`, component scanning, `@Conditional` | Cung cấp các lớp `@AutoConfiguration` với điều kiện sẵn cho những công nghệ phổ biến |
| Phát hiện thành phần ứng dụng | `@ComponentScan` tìm bean trong package được quét | Nạp **danh sách auto-configuration riêng** từ metadata trong các JAR |
| Môi trường/cấu hình | `Environment`, property sources, profiles | Dùng các giá trị này để bật, tắt hoặc điều chỉnh cấu hình mặc định |
| Quyền quyết định cuối cùng | Ứng dụng có thể khai báo bean/cấu hình chủ đích | Nhiều mặc định được thiết kế để **back off** nếu ứng dụng đã định nghĩa bean thích hợp |
| Khởi chạy | Cung cấp các cơ chế xây dựng/refresh context | `SpringApplication` tổ chức khởi chạy, suy luận loại ứng dụng và áp dụng các thuận tiện của Boot |

Một cấu hình Spring thuần hoàn toàn có thể hoạt động không cần Boot. Ngược lại, ứng dụng Boot vẫn là ứng dụng dùng các cơ chế cốt lõi của Spring Framework; nó chỉ nhận thêm lớp lựa chọn mặc định và quy trình khởi chạy thuận tiện.

### Ba câu hỏi xác định trách nhiệm

1. **Ai tạo và quản lý đối tượng?** Spring container.
2. **Ai cung cấp một cấu hình hợp lý khi ứng dụng chưa cấu hình?** Spring Boot auto-configuration, *nếu* các điều kiện tương ứng thỏa mãn.
3. **Ai có quyền sửa cấu hình theo yêu cầu nghiệp vụ?** Ứng dụng, thông qua bean/cấu hình do mình khai báo, properties hoặc loại trừ auto-configuration thích hợp.

## 3. Auto-configuration tham gia lúc khởi động như thế nào?

Trong một ứng dụng Boot tiêu biểu:

```java
@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp ba ý chính:

- `@SpringBootConfiguration`: đánh dấu lớp cấu hình ứng dụng (một dạng `@Configuration`).
- `@EnableAutoConfiguration`: kích hoạt quá trình xem xét các cấu hình tự động.
- `@ComponentScan`: quét component của ứng dụng, thông thường từ package của lớp khởi động trở xuống.

**Component scanning và auto-configuration là hai nguồn định nghĩa bean khác nhau.** Một bean `@Service` của ứng dụng thường đến từ quét package; một bean mặc định cho thư viện bên ngoài có thể đến từ lớp auto-configuration được import. Không nên cho rằng Boot tìm mọi auto-configuration bằng cách quét package.

Luồng tư duy rút gọn:

```text
SpringApplication.run(...)
  -> chuẩn bị Environment và ApplicationContext
  -> xử lý cấu hình ứng dụng (@SpringBootApplication)
       -> quét component và xử lý @Bean của ứng dụng
       -> @EnableAutoConfiguration chọn các ứng viên tự cấu hình
  -> đánh giá @Conditional, đăng ký định nghĩa bean thích hợp
  -> Spring Framework khởi tạo, liên kết và quản lý các bean
  -> ứng dụng sẵn sàng theo vòng đời khởi chạy
```

Đây là **sơ đồ khái niệm**, không phải thứ tự thực thi chi tiết của từng processor hoặc mọi bean. Trong thực tế, việc phân tích cấu hình, đăng ký bean definition và khởi tạo bean có nhiều bước. Điểm cần nắm là các bean đến từ auto-configuration cuối cùng được quản lý bằng cùng cơ chế Spring IoC.

Trong Spring Boot 3.x, ứng viên auto-configuration của một JAR được khai báo trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng chứa tên đầy đủ của một lớp cấu hình. Các lớp này thường đánh dấu bằng `@AutoConfiguration` (một dạng `@Configuration`) và điều kiện `@Conditional...`. `@EnableAutoConfiguration` dùng cơ chế import để xem xét các ứng viên phù hợp; một ứng viên được liệt kê **không đồng nghĩa** mọi bean trong nó chắc chắn được tạo. Metadata nêu *ứng viên*, điều kiện quyết định phần nào được áp dụng.

## 4. Các điều kiện quyết định cấu hình mặc định

Các câu hỏi được hiện thực hóa bằng các annotation của Spring Boot:

| Điều kiện thường gặp | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `@ConditionalOnClass` | Chỉ áp dụng nếu một/một số lớp tồn tại trên classpath | Có thư viện tích hợp tương ứng |
| `@ConditionalOnMissingBean` | Chỉ đăng ký nếu chưa có bean phù hợp tại thời điểm đánh giá | Nhường chỗ cho bean của ứng dụng |
| `@ConditionalOnBean` | Chỉ áp dụng nếu bean cần thiết đã tồn tại | Bổ sung phần phụ thuộc vào một hạ tầng khác |
| `@ConditionalOnProperty` | Kiểm tra giá trị property; có thể dùng `havingValue`/`matchIfMissing` | Cho phép bật/tắt tính năng bằng cấu hình |
| `@ConditionalOnWebApplication` | Chỉ áp dụng trong loại ứng dụng web phù hợp | Phân biệt thiết lập servlet/reactive |

Một phép suy luận tiêu biểu:

```text
Có thư viện tương ứng trên classpath?
  ├─ Không -> bỏ qua phần cấu hình cần thư viện đó
  └─ Có
      Có đúng loại ứng dụng và các property cần thiết?
        ├─ Không -> bỏ qua
        └─ Có
            Ứng dụng đã khai báo bean cần ưu tiên?
              ├─ Có -> bean mặc định có @ConditionalOnMissingBean không được đăng ký
              └─ Chưa -> bean mặc định được đăng ký
```

Lưu ý:

- `@ConditionalOnMissingBean` không có nghĩa **mọi** bean do Boot cung cấp đều có thể thay thế theo cùng một kiểu. Phải xem điều kiện cụ thể của cấu hình liên quan.
- Điều kiện bean được đánh giá dựa trên những định nghĩa đã được xử lý tại thời điểm đó. Vì vậy `@ConditionalOnBean`/`@ConditionalOnMissingBean` thường nên đặt trong auto-configuration, vốn được xử lý sau cấu hình của người dùng, thay vì đặt tùy tiện vào những lớp `@Configuration` thông thường.
- `@ConditionalOnProperty` không mặc nhiên có nghĩa “chỉ bật khi giá trị là `true`”: ngữ nghĩa mặc định, `havingValue` và `matchIfMissing` phải được đọc theo từng annotation.
- Sự hiện diện của dependency là **tín hiệu đầu vào**, không phải lệnh bắt buộc tạo bean. Các điều kiện còn lại và cấu hình người dùng vẫn có tác dụng.

## 5. Phân biệt starter, auto-configuration và cấu hình ứng dụng

Ba khái niệm thường đi cùng nhau nhưng không đồng nhất:

- **Starter** là dependency thuận tiện, thường gom các thư viện cần thiết. Thêm `spring-boot-starter-web` giúp đưa những thành phần liên quan đến web vào classpath; riêng starter không phải trình tạo bean.
- **Auto-configuration** chứa logic cấu hình có điều kiện. Khi có đủ dependency và môi trường thích hợp, nó đóng góp bean definitions để Spring container sử dụng.
- **Cấu hình ứng dụng** là phần do lập trình viên chủ động định nghĩa: `@Bean`, `@Component`, cấu hình properties, v.v. Phần này thể hiện yêu cầu thực tế và có thể khiến các mặc định tương ứng nhường chỗ.

Có thể hình dung: **starter mang công cụ vào**, **auto-configuration kiểm tra điều kiện để lắp đặt mặc định**, còn **Spring Framework quản lý và vận hành các thành phần được lắp đặt**. So sánh này chỉ phục vụ tư duy; điều kiện và cơ chế thực tế vẫn là annotation, import và container.

## 6. Ví dụ chạy được: bean mặc định nhường chỗ cho bean do ứng dụng khai báo

Ví dụ tối giản dùng **Java 17, Spring Boot 3.3.13, Maven**; không cần web server. Ta tạo một `Greeter` do auto-configuration cung cấp khi ứng dụng chưa khai báo bean của loại này, rồi bật một bean ứng dụng bằng property.

Cấu trúc tệp:

```text
boot-auto-config-role/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── demo/
    │   │   ├── DemoApplication.java
    │   │   └── Greeter.java
    │   └── autoconfig/
    │       └── GreeterAutoConfiguration.java
    └── resources/
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**`pom.xml`**

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
    <artifactId>boot-auto-config-role</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

**`src/main/java/demo/Greeter.java`**

```java
package demo;

public interface Greeter {
    String greet();
}
```

**`src/main/java/demo/DemoApplication.java`**

```java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showGreeter(Greeter greeter) {
        return args -> System.out.println("GREETING: " + greeter.greet());
    }

    @Bean
    @ConditionalOnProperty(name = "demo.custom-greeter", havingValue = "true")
    Greeter applicationGreeter() {
        return () -> "from application";
    }
}
```

`ApplicationRunner` nhận bean `Greeter` qua DI và in kết quả sau khi ứng dụng khởi động. `applicationGreeter()` chỉ được đăng ký khi property `demo.custom-greeter=true`.

**`src/main/java/autoconfig/GreeterAutoConfiguration.java`**

```java
package autoconfig;

import demo.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(Greeter.class)
public class GreeterAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    Greeter defaultGreeter() {
        return () -> "from auto-configuration";
    }
}
```

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

```text
autoconfig.GreeterAutoConfiguration
```

Đặt `autoconfig` **ngoài package `demo`** để lớp auto-configuration được nạp qua file `.imports`, không vô tình lọt vào component scan của ứng dụng. Dự án thật thường đặt auto-configuration trong JAR thư viện riêng; việc đặt cùng một project ở đây chỉ để ví dụ ngắn, tự chạy được.

Tại thư mục chứa `pom.xml`, yêu cầu có JDK 17+ và Maven:

```bash
mvn -q -DskipTests package
java -jar target/boot-auto-config-role-0.0.1-SNAPSHOT.jar
```

Ngoài các log khởi động của Spring Boot, chương trình có dòng kết quả:

```text
GREETING: from auto-configuration
```

Ở lần chạy này, property chưa được bật; `applicationGreeter()` không tạo bean. Auto-configuration thấy có `Greeter` trên classpath và chưa có bean `Greeter`, nên định nghĩa `defaultGreeter()` được đăng ký.

Tiếp theo, chạy:

```bash
java -jar target/boot-auto-config-role-0.0.1-SNAPSHOT.jar --demo.custom-greeter=true
```

Dòng kết quả là:

```text
GREETING: from application
```

Lần này `applicationGreeter()` đăng ký bean của ứng dụng trước khi điều kiện auto-configuration cho `defaultGreeter()` được xét. Vì đã có bean `Greeter`, `@ConditionalOnMissingBean(Greeter.class)` không thỏa mãn và bean mặc định **không được đăng ký**. Spring Framework vẫn thực hiện DI cho `ApplicationRunner` như bình thường trong cả hai lần.

**Điều ví dụ chứng minh:** Boot giúp cung cấp lựa chọn mặc định; Spring IoC thực thi định nghĩa bean được chọn; ứng dụng vẫn có thể can thiệp bằng cấu hình tường minh. Bài học không phụ thuộc vào việc có web server.

## 7. Khi muốn kiểm soát hoặc điều tra auto-configuration

### 7.1. Đổi cấu hình qua properties

Tìm đúng property do tính năng cụ thể hỗ trợ trước khi tự tạo bean thay thế. Ví dụ trong chương trình trên, `demo.custom-greeter` là property **do ví dụ tự định nghĩa** qua `@ConditionalOnProperty`; đây không phải property mặc định của Spring Boot. Những auto-configuration có hỗ trợ properties thì có thể cho phép đổi timeout, endpoint hoặc chế độ hoạt động mà không thay toàn bộ cấu hình.

### 7.2. Khai báo bean tường minh

Khi mặc định không đáp ứng yêu cầu, tạo bean của chính ứng dụng với kiểu và tên phù hợp. Kiểm tra điều kiện `@ConditionalOnMissingBean` của cấu hình liên quan: có điều kiện dựa trên **type**, có điều kiện theo **name**, và có cấu hình không tự nhường chỗ trong tình huống mong muốn. Thêm một bean tùy ý không đảm bảo “vô hiệu hóa” mọi auto-configuration.

### 7.3. Loại trừ một auto-configuration cụ thể

Với những lớp auto-configuration hợp lệ cho phiên bản Boot đang dùng, có thể loại trừ bằng:

```java
@SpringBootApplication(excludeName = "autoconfig.GreeterAutoConfiguration")
public class DemoApplication {
    // Ví dụ minh họa thuộc tính excludeName; không thay thế class chạy ở mục 6.
}
```

Hoặc dùng property:

```properties
spring.autoconfigure.exclude=autoconfig.GreeterAutoConfiguration
```

**Cảnh báo về hệ quả:** nếu loại trừ `GreeterAutoConfiguration` mà cũng không tạo `Greeter` khác, ví dụ sẽ không khởi động thành công vì `showGreeter(Greeter greeter)` thiếu dependency. Loại trừ đồng nghĩa bỏ nguồn mặc định, **không** đồng nghĩa tự động có nguồn thay thế. Với những auto-configuration chính thức của Boot, hãy tra đúng tên lớp theo phiên bản đang dùng.

### 7.4. Xem điều kiện nào khớp

Đối với JAR ví dụ:

```bash
java -jar target/boot-auto-config-role-0.0.1-SNAPSHOT.jar --debug
```

Boot sẽ in **Conditions Evaluation Report** cùng các log khởi động. Tìm `GreeterAutoConfiguration` và các mục *Positive matches* / *Negative matches* để thấy vì sao điều kiện khớp hoặc không khớp. Có thể chạy thêm `--demo.custom-greeter=true` để so sánh.

Khi gỡ lỗi dự án thật, đặt câu hỏi theo thứ tự: dependency có hiện diện không, property nào đang có hiệu lực, context thuộc loại nào, có bean cùng type/name đã khai báo chưa, cấu hình có bị exclude không. Đây là các nguyên nhân trực tiếp hơn việc đoán Boot “không quét thấy class”.

## 8. Những hiểu lầm và lỗi thường gặp

1. **“Spring Boot thay thế Spring Framework.”** Sai: Boot vận hành trên Spring Framework và tái sử dụng `ApplicationContext`, DI, cấu hình bean cùng các mô-đun của Framework.
2. **“Thêm starter là chắc chắn có mọi bean.”** Sai: starter chủ yếu gom dependency; auto-configuration còn phải vượt qua các điều kiện.
3. **“Auto-configuration là component scanning.”** Sai: danh sách auto-configuration được nạp qua cơ chế import/metadata; component scan là cơ chế phát hiện component của ứng dụng.
4. **“Có `@ConditionalOnMissingBean` thì bean tùy chỉnh lúc nào cũng thắng.”** Không luôn đúng: phải đặt điều kiện đúng chỗ, xem type/name và trình tự xử lý bean definition. Đây là lý do cấu hình tự động thông thường được xử lý sau cấu hình ứng dụng.
5. **“Bật debug sẽ sửa được cấu hình.”** `--debug` chủ yếu cung cấp thông tin chẩn đoán về điều kiện; nó không tự sửa dependency hoặc bean còn thiếu.
6. **“Có thể copy nguyên cấu hình auto-config nội bộ của Boot và sửa trực tiếp.”** Điều này thường gây lệ thuộc vào chi tiết triển khai. Ưu tiên properties, bean override có chủ đích hoặc `exclude` phù hợp; chỉ tự viết auto-configuration khi đang phát triển thư viện/starter thật sự.
7. **“Một cấu hình mặc định không được áp dụng là lỗi của Spring IoC.”** Thường cần kiểm tra classpath/conditions trước: IoC chỉ có thể tạo và inject những bean definition đã được đăng ký hợp lệ.

## 9. Cách vận dụng khi thiết kế ứng dụng

Khi bổ sung một tính năng dựa trên Spring Boot, có thể đi theo trình tự:

1. Xác định chức năng cần thiết và thêm đúng dependency/starter.
2. Khởi động với mức cấu hình tối thiểu; kiểm tra các bean và hành vi thực tế.
3. Dùng properties cho những tùy chọn mà module hỗ trợ; ghi rõ cấu hình theo từng môi trường.
4. Chỉ khai báo bean riêng khi cần can thiệp vượt khỏi những property có sẵn.
5. Nếu có xung đột hoặc bean vắng mặt, đọc Conditions Evaluation Report và xem điều kiện của auto-configuration liên quan.
6. Loại trừ đúng lớp auto-configuration nếu thực sự không dùng cơ chế đó, đồng thời đảm bảo ứng dụng còn các dependency cần thiết.

**Nguyên tắc thiết kế:** để Boot giảm phần việc lặp lại, còn các quyết định nghiệp vụ, bảo mật, hiệu năng và tích hợp thực tế vẫn phải được cấu hình, kiểm tra và chịu trách nhiệm trong ứng dụng.

## 10. Tự kiểm tra hiểu bài

- Nếu thêm một starter nhưng auto-configuration tương ứng không chạy, hãy nêu ít nhất ba loại điều kiện cần kiểm tra.
- Trong ví dụ `Greeter`, tại sao có thể đổi dòng `GREETING` mà không sửa `ApplicationRunner`? Phân biệt vai trò của điều kiện Boot và DI của Framework.
- Điều gì xảy ra nếu `GreeterAutoConfiguration` bị exclude mà không có bean `Greeter` của ứng dụng?
- Vì sao lớp auto-configuration của thư viện nên được khai báo trong `.imports` và nằm ngoài package component scan thông thường?

**Đáp án gợi ý:** kiểm tra classpath, properties, loại ứng dụng, bean đã tồn tại và exclusions; hai cấu hình chỉ thay đổi bean được đăng ký, còn `ApplicationRunner` vẫn phụ thuộc vào interface `Greeter`; exclude không có nguồn thay thế gây lỗi thiếu bean; metadata import cho phép Boot lựa chọn cấu hình có điều kiện một cách chủ đích, tránh quét nhầm và phụ thuộc package của ứng dụng.

## Tài liệu tham khảo

- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework, *Using the `@Configuration` annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html
