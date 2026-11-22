# Phân biệt @Primary, @Qualifier và việc ngăn đăng ký bean bằng điều kiện

Trong Spring Boot, có thể cùng lúc tồn tại nhiều bean triển khai một interface. Hai câu hỏi phải được phân biệt:

- **Bean có được đăng ký vào ApplicationContext không?** Đây là bài toán *đăng ký bean*; @ConditionalOnMissingBean, @ConditionalOnProperty và các điều kiện khác có thể khiến một bean definition không được đăng ký.
- **Khi nhiều bean đã tồn tại, Spring inject bean nào tại một điểm cần dependency?** Đây là bài toán *lựa chọn ứng viên*; @Primary và @Qualifier xử lý tình huống này.

Ví dụ: ứng dụng có emailSender và smsSender cùng kiểu MessageSender. @Primary có thể khiến emailSender được dùng mặc định, còn @Qualifier có thể chọn smsSender tại một service cụ thể. **Cả hai bean vẫn tồn tại.** Ngược lại, @ConditionalOnMissingBean có thể khiến bean mặc định hoàn toàn không được đăng ký khi ứng dụng đã cung cấp bean riêng.

## 1. Bảng so sánh

| Công cụ | Nơi sử dụng điển hình | Thời điểm/tác dụng | Có loại bỏ bean khác khỏi context không? |
| --- | --- | --- | --- |
| **@Primary** (Spring Framework) | @Bean hoặc class @Component | Ưu tiên một ứng viên khi inject dependency **đơn giá trị** theo kiểu | **Không** |
| **@Qualifier** (Spring Framework) | Tham số constructor, field, setter; metadata của bean | Thu hẹp các ứng viên tại **điểm inject cụ thể** | **Không** |
| **@ConditionalOnMissingBean** (Spring Boot) | @Bean trong auto-configuration | Đăng ký bean dự phòng **chỉ khi chưa có bean phù hợp** tại lúc điều kiện được xét | Bean dự phòng **không được đăng ký** nếu điều kiện sai |
| **@ConditionalOnBean** (Spring Boot) | @Bean hoặc class cấu hình | Chỉ đăng ký khi bean phụ thuộc đã có mặt | Có thể ngăn bean có điều kiện |
| **@ConditionalOnProperty** (Spring Boot) | @Bean hoặc class cấu hình | Chỉ đăng ký theo giá trị thuộc tính cấu hình | Có thể ngăn bean có điều kiện |

**Phân biệt cốt lõi:** @Primary và @Qualifier quyết định *chọn bean nào* trong các ứng viên sẵn có; các annotation @Conditional… quyết định *có đưa một bean definition vào context hay không*.

## 2. Hai giai đoạn trong vòng đời Spring

~~~text
Component scan, cấu hình @Bean, Spring Boot auto-configuration
    |
    v
Đánh giá @Conditional... trong lúc xử lý bean definitions
    | true                         | false
    v                              v
Đăng ký bean definition           Bỏ qua bean definition đó
    |
    v
Tạo bean và giải quyết dependency injection
    |
    +-- @Qualifier: giới hạn ứng viên phù hợp ở điểm inject
    +-- @Primary: ưu tiên ứng viên trong nhóm phù hợp khi cần một bean
    v
Inject thành công hoặc báo lỗi thiếu/mơ hồ dependency
~~~

Đây là sơ đồ tập trung vào chủ đề; cơ chế autowiring của Spring còn có các quy tắc khác, như tên dependency và độ ưu tiên. Tuy nhiên, **@Primary không loại bean khỏi context**, **@Qualifier không tạo hay xóa bean**, còn điều kiện đăng ký phải được xử lý **trước** khi dependency đó có thể được inject.

## 3. @Primary: ứng viên mặc định, không phải cơ chế tắt bean

Đặt @Primary trên một @Bean hoặc một class bean để ưu tiên nó khi nhiều bean phù hợp cùng kiểu và một nơi chỉ yêu cầu **một** dependency. Nếu một injection point đã chỉ định @Qualifier khớp với một bean khác, bean được chỉ định đó vẫn có thể được chọn thay cho primary.

- Một @Primary duy nhất trong nhóm ứng viên phù hợp thường giải quyết sự mơ hồ khi inject một interface.
- Hai ứng viên cùng gắn @Primary vẫn có thể gây NoUniqueBeanDefinitionException.
- Khi inject List<MessageSender>, MessageSender[] hoặc Map<String, MessageSender>, các bean không-primary vẫn có thể xuất hiện trong collection; @Primary không lọc chúng.
- @Primary không phải biện pháp tránh tạo bean tốn tài nguyên, tránh bean name trùng nhau hay thay thế default auto-configuration.

### Ví dụ hoàn chỉnh chạy được với Java 17+ và Spring Boot

Tạo dự án Maven có hai file dưới đây. Ví dụ dùng Spring Boot 3.3.5, JDK 17 trở lên.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-choice-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

**src/main/java/com/example/demo/BeanChoiceApplication.java**

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@SpringBootApplication
public class BeanChoiceApplication implements CommandLineRunner {
    private final MessageSender defaultSender;
    private final MessageSender selectedSms;

    public BeanChoiceApplication(
            MessageSender defaultSender,
            @Qualifier("smsSender") MessageSender selectedSms) {
        this.defaultSender = defaultSender;
        this.selectedSms = selectedSms;
    }

    public static void main(String[] args) {
        SpringApplication.run(BeanChoiceApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println("Default: " + defaultSender.send("Xin chào"));
        System.out.println("Qualified: " + selectedSms.send("Xin chào"));
    }
}

interface MessageSender {
    String send(String content);
}

@Configuration(proxyBeanMethods = false)
class SenderConfiguration {
    @Bean("emailSender")
    @Primary
    MessageSender emailSender() {
        return content -> "EMAIL -> " + content;
    }

    @Bean("smsSender")
    MessageSender smsSender() {
        return content -> "SMS -> " + content;
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Bên cạnh log khởi động, hai dòng do phương thức run in ra là:

~~~text
Default: EMAIL -> Xin chào
Qualified: SMS -> Xin chào
~~~

**Vì sao?** Constructor yêu cầu hai MessageSender. Tham số defaultSender không có qualifier; emailSender là ứng viên @Primary nên được inject. Tham số selectedSms khai báo @Qualifier("smsSender"), chọn đúng bean mang tên smsSender, dù emailSender được đánh dấu primary. Cả hai bean đều được tạo/đăng ký. Nếu gọi ApplicationContext.getBeansOfType(MessageSender.class), có thể quan sát hai tên emailSender và smsSender.

**Thử thay đổi để kiểm chứng:**

1. Xóa @Primary trên emailSender: tham số defaultSender trở nên mơ hồ giữa hai bean cùng kiểu; Spring thường báo NoUniqueBeanDefinitionException khi tạo ứng dụng.
2. Gắn @Qualifier("emailSender") trực tiếp vào tham số defaultSender: Spring chọn rõ ràng emailSender mà không cần @Primary.
3. Gắn thêm @Primary vào smsSender: có hai ứng viên primary, nên @Primary không còn giúp chọn duy nhất cho defaultSender.
4. Inject List<MessageSender>: cả emailSender lẫn smsSender vẫn là phần tử ứng viên; @Primary không khiến danh sách chỉ có emailSender.

## 4. @Qualifier: chọn rõ ràng theo từng injection point

Với một service bắt buộc dùng SMS, đặt @Qualifier ở tham số constructor:

~~~java
public NotificationService(
        @Qualifier("smsSender") MessageSender sender) {
    this.sender = sender;
}
~~~

Đây là **đoạn minh họa bên trong class NotificationService đã khai báo field sender**, không phải file Java độc lập.

String "smsSender" có thể khớp tên bean do @Bean("smsSender") hoặc metadata qualifier phù hợp. Với ứng dụng lớn, có thể tạo custom qualifier annotation để tránh rải chuỗi tên implementation khắp code. Constructor injection giúp dependency rõ ràng và dễ kiểm thử.

**Khi @Qualifier và @Primary cùng xuất hiện:** @Qualifier thu hẹp tập ứng viên theo yêu cầu tại điểm inject. Nếu chỉ một bean còn phù hợp, bean đó được chọn, dù bean khác mang @Primary. Nếu nhiều bean cùng thỏa qualifier, @Primary vẫn có thể được dùng **trong tập ứng viên còn lại**. Vì vậy nói “@Qualifier luôn xóa bỏ @Primary” là không chính xác.

**Giới hạn:** @Qualifier không ngăn implementation khác được khởi tạo, không phải công tắc feature và không sửa sự tồn tại của bean. Nếu bean không được đăng ký vì điều kiện sai, @Qualifier cũng không thể triệu hồi nó.

## 5. @ConditionalOnMissingBean: tạo fallback có thể được ứng dụng thay thế

Đây là một mẫu quan trọng trong **Spring Boot Auto Configuration**. Thư viện cung cấp implementation mặc định; ứng dụng sử dụng thư viện có thể khai báo implementation tùy chỉnh. Thư viện chỉ nên tạo mặc định **khi chưa có implementation phù hợp**.

Các mảnh mã sau thuộc **những tệp riêng của thư viện và ứng dụng**, không phải một chương trình Java độc lập.

**Trong thư viện: AuditPort.java**

~~~java
package com.example.audit;

public interface AuditPort {
    String record(String event);
}
~~~

**Trong thư viện: AuditAutoConfiguration.java**

~~~java
package com.example.audit;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AuditAutoConfiguration {
    @Bean("defaultAuditPort")
    @ConditionalOnMissingBean(AuditPort.class)
    public AuditPort defaultAuditPort() {
        return event -> "DEFAULT: " + event;
    }
}
~~~

Để Spring Boot tự nạp auto-configuration trong thư viện, thêm tệp **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** với nội dung:

~~~text
com.example.audit.AuditAutoConfiguration
~~~

**Trong ứng dụng tiêu thụ thư viện: AuditCustomization.java (tùy chọn)**

~~~java
package com.example.app;

import com.example.audit.AuditPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditCustomization {
    @Bean("customAuditPort")
    public AuditPort customAuditPort() {
        return event -> "CUSTOM: " + event;
    }
}
~~~

Ứng dụng cần khai báo dependency tới thư viện; class AuditCustomization phải nằm trong vùng component scan hoặc được import. Spring Boot tổ chức auto-configuration **sau** cấu hình do ứng dụng cung cấp, giúp điều kiện @ConditionalOnMissingBean nhìn thấy bean tùy chỉnh.

| Trạng thái cấu hình ứng dụng | Khi đánh giá @ConditionalOnMissingBean(AuditPort.class) | Bean kết quả |
| --- | --- | --- |
| Không khai báo AuditCustomization | Chưa có AuditPort phù hợp | Đăng ký **defaultAuditPort** |
| Có AuditCustomization | Đã có **customAuditPort** thuộc kiểu AuditPort | **Không đăng ký defaultAuditPort**; giữ customAuditPort |

Trường hợp thứ hai khác hẳn @Primary: ở đây **defaultAuditPort không tồn tại**; không có chuyện tạo cả default và custom rồi chọn custom lúc inject.

### Lưu ý về thứ tự và kiểu được kiểm tra

- @ConditionalOnMissingBean thuộc **Spring Boot**, package org.springframework.boot.autoconfigure.condition.
- Condition được kiểm tra trên các bean definition **đã được xử lý tại thời điểm đó**. Nếu đặt tùy tiện trên hai cấu hình thông thường, kết quả có thể chịu ảnh hưởng của thứ tự; đây là lý do annotation này phù hợp nhất với auto-configuration chạy sau cấu hình ứng dụng.
- Khi một auto-configuration phụ thuộc kết quả của auto-configuration khác, có thể khai báo thứ tự bằng @AutoConfiguration(after = …) hoặc @AutoConfiguration(before = …).
- Nếu hợp đồng của thư viện là interface AuditPort, nên dùng **@ConditionalOnMissingBean(AuditPort.class)** và trả về AuditPort trong phương thức @Bean, thay vì chỉ kiểm tra một implementation cụ thể. Spring còn hỗ trợ điều kiện theo name và điều chỉnh phạm vi tìm kiếm context cha/con khi cần.
- Đặt @Primary lên customAuditPort **không làm defaultAuditPort tự biến mất** nếu bean mặc định không có điều kiện đúng. Primary thuộc giai đoạn injection; điều kiện thuộc giai đoạn registration.

## 6. Điều kiện dựa trên cấu hình và các điều kiện liên quan

Nếu mục tiêu là tạo bean **chỉ khi tính năng được bật**, dùng @ConditionalOnProperty:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
AuditPort remoteAuditPort() {
    return event -> "REMOTE: " + event;
}
~~~

Đây là **phương thức minh họa bên trong một class @Configuration**, cần import ConditionalOnProperty, Bean và AuditPort phù hợp.

~~~properties
feature.audit.enabled=true
~~~

Khi thuộc tính bằng true, bean remoteAuditPort được đăng ký. Khi false hoặc vắng mặt (matchIfMissing = false), bean đó **không** được đăng ký. Nếu service vẫn inject bean này như dependency bắt buộc mà không có fallback, application context có thể khởi động thất bại: tắt đăng ký **không tự xử lý** mọi nơi đang tiêu thụ bean.

Một số điều kiện gần gũi:

- **@ConditionalOnBean(X.class)**: chỉ đăng ký khi đã thấy bean kiểu X phù hợp.
- **@ConditionalOnClass(X.class)**: chỉ đăng ký khi class X có trên classpath; thích hợp cho tích hợp tùy chọn.
- **@ConditionalOnSingleCandidate(X.class)**: kiểm tra có một ứng viên phù hợp duy nhất, hoặc nhiều ứng viên nhưng xác định được một ứng viên @Primary trong các điều kiện thích hợp.
- **@Profile("prod")** của Spring Framework: đăng ký bean/cấu hình theo profile đang bật.

Tất cả những công cụ này quyết định **có đăng ký bean definition hay không**, khác với @Qualifier/@Primary chọn bean tại điểm inject.

## 7. Ra quyết định đúng trong thiết kế

| Mong muốn | Giải pháp phù hợp | Giải thích |
| --- | --- | --- |
| Có email và SMS; mặc định dùng email | @Primary trên emailSender | Hai bean cùng tồn tại; email được ưu tiên khi inject đơn giá trị theo kiểu |
| Một service cụ thể luôn dùng SMS | @Qualifier("smsSender") ở constructor | Quyết định cục bộ cho một dependency |
| Thư viện có AuditPort mặc định, ứng dụng có thể tự cung cấp AuditPort khác | @ConditionalOnMissingBean(AuditPort.class) trong auto-configuration | Bean mặc định không được đăng ký khi đã có bean custom |
| Chỉ đăng ký một integration khi feature được bật | @ConditionalOnProperty | Điều kiện theo application.properties/yaml |
| Một service cần chạy tất cả implementation | Inject List<Interface> hoặc Map<String, Interface> | Không trông chờ @Primary lọc danh sách |
| Một implementation hoàn toàn không nên được khởi tạo trong môi trường này | @ConditionalOnProperty, @Profile hay điều kiện thích hợp | Ngăn việc đăng ký từ đầu |

**Ví dụ kết hợp:** emailSender luôn đăng ký và được @Primary; smsSender chỉ đăng ký khi feature.sms.enabled=true. Khi feature bật, @Qualifier("smsSender") chọn SMS ở nơi cần. Khi feature tắt, service vẫn yêu cầu bắt buộc @Qualifier("smsSender") có thể lỗi thiếu dependency. Cần điều kiện hóa cả consumer hoặc thiết kế fallback rõ ràng. @ConditionalOnProperty không tự thay đổi constructor của consumer.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| NoUniqueBeanDefinitionException | Nhiều bean cùng kiểu, không chọn được một ứng viên phù hợp duy nhất | Chỉ định @Qualifier tại injection point hoặc @Primary cho mặc định |
| Đã thêm @Primary nhưng bean khác vẫn được tạo | @Primary không chặn đăng ký | Dùng điều kiện phù hợp cho bean không cần tồn tại |
| @Qualifier("x") không tìm thấy bean | Tên/qualifier sai hoặc bean bị condition loại | Kiểm tra bean name và điều kiện đăng ký |
| @ConditionalOnMissingBean không nhường chỗ cho bean custom | Kiểu được kiểm tra sai hoặc thứ tự cấu hình không phù hợp | Kiểm tra interface, kiểu trả về @Bean, vị trí auto-configuration và thứ tự |
| Hai bean trùng **tên** gây lỗi đăng ký/ghi đè | Xung đột tên, khác với hai bean cùng interface | Dùng tên riêng hoặc fallback condition; @Primary không giải quyết |
| Tắt bean qua @ConditionalOnProperty làm ứng dụng không khởi động | Consumer vẫn yêu cầu dependency bắt buộc | Có fallback hoặc điều kiện hóa consumer |
| Cả hai ứng viên đều @Primary | Không còn một primary duy nhất | Chỉ giữ một primary hoặc dùng qualifier cụ thể |

Có thể dùng **ApplicationContext.getBeansOfType(MyInterface.class)** để kiểm tra số lượng/tên bean thực sự đã đăng ký. Với auto-configuration, bật báo cáo điều kiện của Spring Boot (chẳng hạn chạy app với đối số **--debug**) để xem lý do điều kiện khớp hay không khớp. Khi debug, hãy hỏi lần lượt: **“Bean có được đăng ký không?”**, rồi **“Vì sao điểm inject chọn bean này?”**

## 9. Câu hỏi tự kiểm tra

**1.** A và B cùng kiểu; A có @Primary, một constructor inject @Qualifier("B"). Bean nào được chọn?  
**Đáp án:** B nếu bean B tồn tại và khớp qualifier. A vẫn tồn tại trong context.

**2.** Muốn thư viện không tạo default implementation khi app đã cung cấp implementation của cùng interface. Dùng gì?  
**Đáp án:** @ConditionalOnMissingBean(Interface.class) trong auto-configuration. @Primary không ngăn default được đăng ký.

**3.** List<Interface> có chỉ chứa bean @Primary không?  
**Đáp án:** Không. @Primary chủ yếu giải quyết autowiring đơn giá trị; các implementation khác vẫn có thể nằm trong collection.

**4.** Tại sao đặt @ConditionalOnMissingBean trong cấu hình thông thường có thể không ổn định?  
**Đáp án:** Điều kiện được xét theo bean definitions đã xử lý tại thời điểm đó; thứ tự xử lý cấu hình có thể khiến nó chưa thấy bean custom.

**5.** Property tắt SMS, nhưng một service vẫn inject bắt buộc @Qualifier("smsSender"). Điều gì có thể xảy ra?  
**Đáp án:** Nếu không có bean nào khớp, dependency không được thỏa mãn và Spring có thể lỗi khởi động. Cần thiết kế consumer và fallback tương ứng.

**Ghi nhớ:** @Primary = ưu tiên ứng viên mặc định; @Qualifier = chọn ứng viên cụ thể ở điểm inject; @ConditionalOnMissingBean = đăng ký default chỉ khi chưa có bean phù hợp; @ConditionalOnProperty = chỉ đăng ký khi điều kiện thuộc tính thỏa. Xác định đúng bài toán *registration* hay *injection* trước khi chọn annotation.
