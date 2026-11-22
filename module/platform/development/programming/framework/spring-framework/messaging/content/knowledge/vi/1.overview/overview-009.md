# Phân biệt Spring Framework, Spring Boot và các dự án tích hợp

Trong hệ sinh thái Spring, các tên gọi thường xuất hiện cùng nhau nhưng đảm nhiệm những vai trò khác nhau. **Spring Framework cung cấp nền tảng lập trình và các cơ chế cốt lõi; Spring Boot giúp khởi tạo, cấu hình và vận hành ứng dụng dựa trên nền tảng đó; các dự án Spring bổ sung năng lực chuyên biệt theo nhu cầu của ứng dụng.** Spring Integration là một dự án cụ thể trong nhóm này, chuyên xây dựng luồng tích hợp và xử lý thông điệp.

Hiểu đúng các lớp này giúp chọn dependency phù hợp, tránh đưa quá nhiều thư viện vào ứng dụng và biết thành phần nào chịu trách nhiệm khi cấu hình hoặc chạy hệ thống.

## 1. Spring Framework: nền tảng cốt lõi

**Spring Framework** là framework nền tảng cho ứng dụng Java. Nó cung cấp mô hình quản lý đối tượng, dependency injection, lập trình hướng khía cạnh, giao dịch, truy cập dữ liệu, web và các cơ chế hỗ trợ kiểm thử.

### Những trách nhiệm chính

- **IoC Container và Dependency Injection (DI):** container tạo, cấu hình, kết nối và quản lý vòng đời các đối tượng do Spring quản lý, thường gọi là bean. Thay vì một lớp tự tạo mọi dependency bằng từ khóa **new**, dependency được khai báo và Spring cung cấp khi tạo bean.
- **Cấu hình và vòng đời bean:** bean có thể được khai báo bằng annotation, lớp **@Configuration** với **@Bean**, hoặc các cách cấu hình khác. **ApplicationContext** là container thường dùng trong ứng dụng.
- **AOP (Aspect-Oriented Programming):** hỗ trợ áp dụng hành vi dùng chung như transaction, logging hoặc kiểm tra quyền quanh các điểm thực thi phù hợp. Trong nhiều trường hợp, Spring thực hiện việc này thông qua proxy.
- **Transaction và truy cập dữ liệu:** cung cấp abstraction cho transaction, JDBC và tích hợp với các công nghệ persistence. Annotation **@Transactional** là một cách khai báo ranh giới giao dịch phổ biến.
- **Web:** cung cấp Spring MVC cho ứng dụng web theo mô hình Servlet và Spring WebFlux cho ứng dụng reactive.
- **Messaging và kiểm thử:** cung cấp các abstraction và tiện ích để tích hợp messaging, kiểm thử container, mock các thành phần Spring và kiểm tra ứng dụng.

Một ví dụ cấu hình bean bằng Java Config:

~~~java
@Configuration
class BillingConfig {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }

    @Bean
    BillingService billingService(Clock clock) {
        return new BillingService(clock);
    }
}
~~~

Spring thấy hai phương thức **@Bean**, tạo các bean tương ứng và truyền bean **Clock** vào **BillingService**. Ví dụ này minh họa cơ chế DI; để chạy độc lập cần có dependency **spring-context** và lớp **BillingService** với constructor nhận **Clock**.

### Spring Framework không tự đảm nhiệm điều gì?

Spring Framework không phải là cơ sở dữ liệu, message broker, máy chủ triển khai hay công cụ build. Nó cũng không bắt buộc ứng dụng phải dùng Spring Boot. Khi chỉ dùng Framework, nhóm phát triển tự quyết định cách tạo **ApplicationContext**, khai báo cấu hình, chọn dependency, thiết lập máy chủ web và đóng gói ứng dụng.

Cách dùng Framework trực tiếp phù hợp khi cần kiểm soát cấu hình ở mức thấp, tích hợp vào môi trường đã có sẵn hoặc duy trì ứng dụng được xây dựng theo cách không dùng Boot.

## 2. Spring Boot: cách khởi tạo và vận hành ứng dụng Spring

**Spring Boot được xây dựng trên Spring Framework.** Mục tiêu của Boot là giảm phần cấu hình lặp lại để nhóm phát triển tập trung vào chức năng nghiệp vụ. Boot cung cấp các quy ước mặc định, cơ chế auto-configuration, dependency starter và cách chạy ứng dụng thuận tiện.

### Các khả năng nổi bật

1. **Auto-configuration:** Boot xem xét classpath, các bean đã khai báo và cấu hình hiện tại để quyết định cấu hình nào có thể áp dụng. Ví dụ, khi có thư viện web phù hợp, Boot có thể cấu hình Spring MVC và máy chủ nhúng theo các điều kiện mặc định. Auto-configuration có điều kiện; nó không tự đoán mọi yêu cầu nghiệp vụ.
2. **Starter dependencies:** starter gom các dependency thường dùng cho một nhóm chức năng. **spring-boot-starter-web** là lựa chọn phổ biến cho ứng dụng Spring MVC; **spring-boot-starter-data-jpa** hỗ trợ ứng dụng dùng Spring Data JPA; **spring-boot-starter-security** tích hợp Spring Security.
3. **Máy chủ nhúng:** với cấu hình web thông dụng, ứng dụng có thể đóng gói và chạy cùng máy chủ nhúng, chẳng hạn Tomcat. Nhờ vậy, không nhất thiết phải triển khai WAR lên một máy chủ ứng dụng cài đặt riêng.
4. **Externalized configuration:** cấu hình có thể được đưa ra file properties/YAML, biến môi trường hoặc tham số khởi chạy. Cùng một artifact có thể chạy ở nhiều môi trường với cấu hình khác nhau.
5. **Hỗ trợ vận hành:** Spring Boot Actuator cung cấp các endpoint và cơ chế quan sát như health, metrics và thông tin ứng dụng. Cần chủ động kiểm soát endpoint nào được expose và bảo vệ các endpoint quản trị.

Annotation **@SpringBootApplication** là annotation tổng hợp, kết hợp vai trò cấu hình Boot, bật auto-configuration và component scan cho package của ứng dụng. Điểm khởi động thường gọi **SpringApplication.run(...)**:

~~~java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### Ví dụ ứng dụng web tối thiểu

Ví dụ dưới đây dùng Spring Boot 3.3.0 và Java 17 trở lên. Đây là một ứng dụng web hoàn chỉnh tối giản; hai lớp Java nên đặt trong package **com.example.demo**, mỗi lớp ở file có cùng tên.

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/demo/GreetingController.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello Spring");
    }
}
~~~

Chạy ứng dụng bằng Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng **gradlew.bat bootRun**. Khi ứng dụng đã khởi động, gửi request:

~~~http
GET http://localhost:8080/hello
~~~

Response JSON:

~~~json
{
  "message": "Hello Spring"
}
~~~

Trong ví dụ này, Boot khởi chạy ứng dụng, cấu hình web theo dependency trên classpath và tạo máy chủ nhúng. Spring Framework vẫn thực hiện phần DI, quản lý bean, ánh xạ request và gọi controller.

### Boot không thay thế Spring Framework

Khi thêm starter của Boot, ứng dụng vẫn sử dụng các thành phần của Spring Framework ở bên dưới. Boot chủ yếu cung cấp cách lắp ráp và cấu hình thuận tiện. Có thể tùy chỉnh cấu hình mặc định bằng properties hoặc tự khai báo bean; nhiều auto-configuration sẽ nhường chỗ khi ứng dụng đã cung cấp bean tương ứng.

Boot cũng không tự cung cấp nghiệp vụ, database hay broker. Nếu ứng dụng cần lưu dữ liệu, xác thực người dùng hoặc giao tiếp Kafka, vẫn phải chọn và cấu hình công nghệ phù hợp.

## 3. Các dự án trong hệ sinh thái Spring

Ngoài Spring Framework và Spring Boot, hệ sinh thái Spring có nhiều dự án tập trung giải quyết từng nhóm vấn đề. Chúng thường được thêm vào ứng dụng theo nhu cầu. Khi dùng Spring Boot, nhiều dự án có starter hoặc được Boot quản lý phiên bản để tích hợp thuận tiện; khả năng hỗ trợ cụ thể phụ thuộc từng dự án và phiên bản.

| Dự án | Năng lực chính | Ví dụ sử dụng |
|---|---|---|
| **Spring Data** | Đơn giản hóa truy cập dữ liệu và mô hình repository cho nhiều loại kho dữ liệu. | Spring Data JPA, MongoDB, Redis. |
| **Spring Security** | Xác thực (authentication), phân quyền (authorization), bảo vệ request và method. | Đăng nhập, OAuth2 Resource Server, kiểm soát quyền truy cập API. |
| **Spring Integration** | Tổ chức luồng tích hợp giữa các hệ thống theo Enterprise Integration Patterns (EIP). | Nhận file, chuyển đổi thông điệp, định tuyến đến service hoặc hệ thống đích. |
| **Spring for Apache Kafka** | Cung cấp abstraction và listener để ứng dụng Spring gửi/nhận record Kafka. | **KafkaTemplate**, **@KafkaListener**, consumer group. |
| **Spring AMQP** | Tích hợp mô hình AMQP, thường dùng với RabbitMQ. | **RabbitTemplate**, listener container, queue và exchange. |
| **Spring Batch** | Xử lý các công việc theo lô với job, step, chunk, retry và restart. | Import dữ liệu lớn, đối soát, xử lý báo cáo định kỳ. |
| **Spring Cloud** | Hỗ trợ các mối quan tâm trong hệ thống phân tán. | Gateway, service discovery, centralized configuration, circuit breaker. |
| **Spring Session** | Quản lý HTTP session qua nhiều instance hoặc kho lưu trữ dùng chung. | Chia sẻ session khi ứng dụng chạy nhiều node. |

Các dự án này không phải những phần bắt buộc phải cài cùng nhau. Ví dụ, ứng dụng chỉ cần REST API và PostgreSQL có thể dùng Boot, Spring MVC và Spring Data JPA mà không cần Spring Cloud, Spring Batch hay Spring Integration.

### Spring Integration là gì?

Tên **Spring Integration** dễ bị hiểu nhầm là tên gọi chung cho mọi cách tích hợp trong Spring. Thực tế, đây là một dự án riêng triển khai các mẫu tích hợp hệ thống (Enterprise Integration Patterns).

Spring Integration mô hình hóa việc trao đổi dữ liệu thành các thông điệp và luồng xử lý. Các thành phần thường gặp gồm:

- **Message:** gói dữ liệu gồm payload và headers.
- **Message Channel:** kênh chuyển thông điệp giữa các thành phần.
- **Message Endpoint:** điểm nối luồng thông điệp với logic ứng dụng.
- **Transformer:** chuyển đổi payload hoặc cấu trúc thông điệp.
- **Filter:** chỉ cho thông điệp thỏa điều kiện đi tiếp.
- **Router:** chọn nhánh xử lý dựa trên nội dung hoặc metadata.
- **Service Activator:** gọi một service hoặc phương thức nghiệp vụ.
- **Channel Adapter / Gateway:** kết nối luồng trong ứng dụng với hệ thống hoặc API bên ngoài.

Một luồng điển hình có thể được hình dung như sau:

~~~text
Nguồn bên ngoài
    |
Inbound Adapter
    |
Message Channel
    |
Filter / Transformer
    |
Router
    |
Service Activator
    |
Outbound Adapter
    |
Hệ thống đích
~~~

Ví dụ, ứng dụng nhận file đơn hàng từ thư mục đầu vào, kiểm tra định dạng, chuyển đổi thành đối tượng nghiệp vụ, định tuyến theo loại đơn hàng rồi gọi service xử lý. Spring Integration giúp mô tả các bước kết nối và điều phối này bằng những thành phần có vai trò rõ ràng.

**Spring Integration không phải message broker.** Nó không thay thế Kafka hay RabbitMQ. Nó cung cấp mô hình và thành phần tích hợp để kết nối ứng dụng với các endpoint; broker vẫn là hạ tầng trung gian lưu trữ và chuyển thông điệp khi kiến trúc cần đến.

### Phân biệt Spring Integration với các tích hợp messaging khác

- Chọn **Spring for Apache Kafka** khi ứng dụng cần làm việc trực tiếp với Kafka: publish record, consume theo topic/partition, xử lý offset và consumer group.
- Chọn **Spring AMQP** khi ứng dụng cần làm việc với RabbitMQ hoặc hệ thống hỗ trợ AMQP: gửi/nhận qua exchange, queue và binding.
- Chọn **Spring Integration** khi bài toán cần điều phối một luồng gồm nhiều bước, adapter, chuyển đổi, lọc hoặc định tuyến giữa nhiều hệ thống. Nó có thể kết hợp với các công nghệ messaging, nhưng không bắt buộc mọi luồng đều phải có broker.
- Chọn **Spring Cloud Stream** khi cần mô hình ứng dụng hướng sự kiện với abstraction binder cho broker được hỗ trợ. Đây là lựa chọn khác với việc trực tiếp dùng API Kafka hoặc RabbitMQ.

Các lựa chọn có thể kết hợp nếu có lý do kiến trúc rõ ràng. Không nên thêm nhiều lớp abstraction chỉ để chuyển tiếp một lời gọi đơn giản.

## 4. So sánh trực tiếp ba nhóm

| Tiêu chí | Spring Framework | Spring Boot | Các dự án Spring |
|---|---|---|---|
| Vai trò | Nền tảng lập trình và runtime cho ứng dụng Spring. | Khởi tạo, cấu hình, đóng gói và hỗ trợ vận hành ứng dụng. | Bổ sung năng lực chuyên biệt cho một nhóm bài toán. |
| Trọng tâm | DI, bean lifecycle, AOP, transaction, web, messaging. | Auto-configuration, starter, embedded server, externalized config, Actuator. | Data, Security, Integration, Kafka, AMQP, Batch, Cloud... |
| Quan hệ | Là nền tảng mà Boot sử dụng. | Được xây dựng trên Framework. | Thường tích hợp với Framework; nhiều dự án có thể dùng thuận tiện cùng Boot. |
| Có bắt buộc không? | Chỉ bắt buộc khi ứng dụng chọn nền tảng Spring Framework. | Không bắt buộc; có thể dùng Framework trực tiếp. | Không; chỉ thêm dự án giải quyết nhu cầu thực tế. |
| Câu hỏi nó trả lời | “Ứng dụng được cấu tạo và các thành phần phối hợp thế nào?” | “Làm sao khởi chạy và cấu hình ứng dụng nhanh, nhất quán?” | “Ứng dụng cần thêm khả năng chuyên biệt nào?” |

## 5. Mối quan hệ khi xây dựng một ứng dụng thực tế

Với một backend hiện đại, cách kết hợp thường gặp là:

1. **Spring Boot** làm điểm khởi chạy, quản lý cấu hình, dependency và auto-configuration.
2. **Spring Framework** cung cấp container, DI, transaction, web và các abstraction mà code nghiệp vụ sử dụng.
3. **Các dự án bổ sung** được chọn theo yêu cầu: Spring Security để bảo vệ API, Spring Data để truy cập dữ liệu, Spring for Apache Kafka để giao tiếp Kafka, hoặc Spring Integration để điều phối luồng giữa nhiều hệ thống.

Có thể hình dung theo trách nhiệm:

~~~text
Ứng dụng nghiệp vụ
    |
    +-- Spring Boot
    |     Khởi chạy, cấu hình mặc định, dependency management
    |
    +-- Spring Framework
    |     IoC/DI, AOP, transaction, web, messaging abstractions
    |
    +-- Dự án bổ sung theo nhu cầu
          Spring Data / Security / Integration / Kafka / AMQP / Cloud...
~~~

Sơ đồ thể hiện vai trò logic, không phải cây dependency chính xác. Khi một ứng dụng dùng Boot, nhiều thư viện Framework được kéo vào thông qua starter và dependency management. Các dự án bổ sung cũng có thể kéo theo những module Framework cần thiết.

Khi quản lý phiên bản, nên dùng dependency management hoặc BOM do Spring Boot cung cấp thay vì tự ghim các phiên bản Spring Framework và từng thư viện Spring một cách rời rạc. Với Spring Cloud, cần chọn release train tương thích với dòng Spring Boot đang dùng. Khi nâng cấp, kiểm tra bảng tương thích và hướng dẫn của từng dự án.

## 6. Chọn thành phần nào cho bài toán?

- **Ứng dụng Spring mới, cần REST API hoặc web backend:** thường bắt đầu với Spring Boot. Chọn starter web phù hợp, sau đó bổ sung Data, Security hoặc messaging khi có yêu cầu.
- **Cần hiểu hoặc tùy chỉnh sâu container và cấu hình:** học Spring Framework trước hoặc xây dựng ứng dụng dùng Framework trực tiếp. Kiến thức về bean, DI, AOP và transaction vẫn cần thiết khi làm việc với Boot.
- **Cần truy cập cơ sở dữ liệu:** xem xét Spring Data phù hợp với loại kho dữ liệu và cách truy cập. Không mặc định mọi ứng dụng đều cần JPA.
- **Cần xác thực và phân quyền:** dùng Spring Security; xác định rõ cơ chế đăng nhập, nguồn danh tính và quy tắc authorization.
- **Cần xử lý thông điệp Kafka hoặc RabbitMQ:** dùng dự án tích hợp chuyên biệt tương ứng với broker.
- **Cần kết nối nhiều endpoint qua một luồng có bước lọc, chuyển đổi và định tuyến:** cân nhắc Spring Integration.
- **Cần job xử lý dữ liệu theo lô có khả năng restart và theo dõi tiến độ:** cân nhắc Spring Batch.
- **Cần năng lực hệ thống phân tán:** chỉ thêm Spring Cloud khi bài toán thực sự cần gateway, discovery, centralized configuration hoặc các capability liên quan.

Đối với ứng dụng messaging, trước tiên hãy xác định vai trò của hệ thống: gửi/nhận với một broker, điều phối nhiều endpoint, hay xây dựng luồng event-driven. Câu trả lời sẽ giúp chọn Kafka, AMQP, Spring Integration hoặc Spring Cloud Stream đúng mức.

## 7. Những nhầm lẫn thường gặp

1. **“Spring Boot là phiên bản mới của Spring Framework.”** Không đúng. Boot là dự án xây dựng trên Framework và bổ sung cách cấu hình, khởi chạy, đóng gói ứng dụng.
2. **“Dùng Boot thì không cần hiểu Framework.”** Không đúng. Các khái niệm bean, DI, proxy, transaction và MVC vẫn quyết định hành vi ứng dụng.
3. **“Spring Boot chỉ là Tomcat nhúng.”** Không đúng. Máy chủ nhúng chỉ là một phần của trải nghiệm Boot; auto-configuration, starter, externalized configuration và Actuator cũng rất quan trọng.
4. **“Starter chứa toàn bộ chức năng nghiệp vụ.”** Không đúng. Starter chủ yếu gom dependency và hỗ trợ cấu hình. Nhóm phát triển vẫn phải viết nghiệp vụ, cấu hình bảo mật và thiết kế dữ liệu.
5. **“Auto-configuration luôn ghi đè cấu hình của ứng dụng.”** Không đúng. Auto-configuration hoạt động theo điều kiện; nhiều cấu hình mặc định sẽ lùi lại khi ứng dụng tự khai báo bean phù hợp.
6. **“Spring Integration và Spring Cloud giống nhau.”** Không đúng. Spring Integration tập trung vào luồng tích hợp và Enterprise Integration Patterns; Spring Cloud tập trung vào các mối quan tâm của hệ thống phân tán.
7. **“Đã dùng Kafka thì bắt buộc phải dùng Spring Integration.”** Không đúng. Spring for Apache Kafka thường đủ cho nhu cầu producer/consumer trực tiếp. Chỉ thêm Integration khi cần mô hình hóa luồng và điều phối nhiều bước.
8. **“Cài tất cả Spring projects để có một bộ công cụ đầy đủ.”** Không nên. Mỗi dependency làm tăng bề mặt cấu hình, nâng cấp và bảo trì. Chỉ thêm dự án khi có nhu cầu cụ thể.

## 8. Ghi nhớ

- **Spring Framework** cung cấp nền tảng và cơ chế cốt lõi để xây dựng ứng dụng Spring.
- **Spring Boot** giúp lắp ráp, khởi chạy, cấu hình và vận hành ứng dụng dựa trên nền tảng đó.
- **Các dự án Spring** bổ sung năng lực chuyên biệt như Data, Security, Batch, Cloud và messaging.
- **Spring Integration** là một dự án cụ thể dành cho tích hợp hệ thống theo các mẫu xử lý thông điệp.

Trong một ứng dụng thực tế, Boot thường là điểm bắt đầu, Framework là nền tảng bên dưới, còn các dự án bổ sung được chọn theo yêu cầu nghiệp vụ và kiến trúc.
