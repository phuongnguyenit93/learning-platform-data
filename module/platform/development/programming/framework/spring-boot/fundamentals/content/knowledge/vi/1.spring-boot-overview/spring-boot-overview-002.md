# Spring Framework cung cấp nền tảng gì và Spring Boot bổ sung điều gì?

Khi xây dựng ứng dụng Java với Spring, hai cái tên **Spring Framework** và **Spring Boot** thường xuất hiện cùng nhau. Điều này dễ tạo cảm giác chúng là hai framework cạnh tranh hoặc Spring Boot đã thay thế Spring Framework. Thực tế, **Spring Boot được xây dựng trên Spring Framework**: Spring Framework cung cấp các cơ chế cốt lõi để tổ chức và vận hành ứng dụng; Spring Boot giúp lắp ráp, cấu hình, khởi động và vận hành ứng dụng Spring thuận tiện hơn.

Hãy hình dung yêu cầu: tạo một API nhận tên người dùng và trả về lời chào. Lập trình viên cần viết quy tắc tạo lời chào và cách tiếp nhận HTTP request. Nhưng ứng dụng còn cần tạo các đối tượng, nối chúng với nhau, định tuyến HTTP, khởi chạy máy chủ, chọn thư viện tương thích, đọc cấu hình và cung cấp thông tin vận hành. Spring Framework và Spring Boot giải quyết những phần khác nhau của bức tranh đó.

## 1. Bức tranh tổng thể: ba lớp trách nhiệm

~~~text
Ứng dụng của bạn
  ├─ Nghiệp vụ: GreetingService, OrderService, ...
  ├─ Giao tiếp: REST controller, message listener, batch job, ...
  └─ Quy tắc và cấu hình riêng của hệ thống
           │ sử dụng
           ▼
Spring Boot
  ├─ Starter dependencies và quản lý phiên bản thư viện
  ├─ Auto-configuration theo điều kiện
  ├─ Khởi động ứng dụng và máy chủ nhúng khi cần
  ├─ Quy ước cấu hình và cấu hình theo môi trường
  └─ Tiện ích kiểm tra, đóng gói, quan sát ứng dụng
           │ xây dựng trên
           ▼
Spring Framework
  ├─ IoC container, bean và Dependency Injection
  ├─ Cấu hình ứng dụng, vòng đời đối tượng, sự kiện
  ├─ AOP, quản lý giao dịch
  ├─ Spring MVC / Spring WebFlux
  └─ Tích hợp dữ liệu, kiểm thử và hạ tầng khác
           │ sử dụng
           ▼
Java, JVM, thư viện bên thứ ba, máy chủ và tài nguyên hệ thống
~~~

Một cách phân biệt hữu ích:

- **Spring Framework trả lời:** Các thành phần của ứng dụng được tạo, liên kết, gọi và quản lý ra sao? Làm thế nào để xử lý web request, giao dịch và các mối quan tâm kỹ thuật chung?
- **Spring Boot trả lời:** Với các thư viện và cấu hình hiện có, cần thiết lập những gì để ứng dụng Spring chạy được nhanh, nhất quán, dễ cấu hình và dễ vận hành?
- **Mã của bạn trả lời:** Ứng dụng thực sự phải làm gì, dữ liệu nào hợp lệ và quy tắc nghiệp vụ nào phải được thực thi?

Spring Boot **không bỏ qua** Spring Framework. Khi một controller trong ứng dụng Boot nhận HTTP request, các cơ chế của Spring MVC và Spring IoC container vẫn đang làm việc.

## 2. Spring Framework cung cấp nền tảng gì?

### 2.1. IoC container: nơi quản lý đối tượng ứng dụng

Trong Java thuần, một lớp thường tự tạo các đối tượng mà nó cần:

~~~java
public class GreetingController {
    private final GreetingService greetingService = new GreetingService();
}
~~~

Cách viết này đơn giản ở ví dụ nhỏ nhưng khiến lớp sử dụng phụ thuộc trực tiếp vào việc tạo lớp được sử dụng. Khi ứng dụng lớn hơn, việc thay implementation, chia sẻ cấu hình, kiểm thử bằng đối tượng giả hoặc quản lý vòng đời trở nên khó khăn.

Spring Framework giải quyết bằng **Inversion of Control (IoC)**: quyền quyết định cách tạo và liên kết nhiều đối tượng được chuyển cho **Spring container**. Các đối tượng được container quản lý gọi là **bean**. Giao diện container thường gặp là **ApplicationContext**; nó kế thừa các khả năng từ BeanFactory và bổ sung dịch vụ phục vụ ứng dụng.

Ví dụ một dịch vụ:

~~~java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

**@Service** là một dạng chuyên biệt của **@Component**. Khi lớp nằm trong phạm vi được quét component, Spring có thể đăng ký nó thành bean. Ngoài cách quét annotation, có thể khai báo bean một cách tường minh bằng **@Bean** trong lớp **@Configuration**. Không phải mọi đối tượng Java đều tự động trở thành bean.

### 2.2. Dependency Injection: cung cấp đúng đối tượng cần thiết

**Dependency Injection (DI)** là cách đưa dependency từ bên ngoài vào đối tượng, thay vì để đối tượng tự tạo dependency. Spring container có thể thực hiện DI qua constructor, setter hoặc field; với dependency bắt buộc, **constructor injection** thường rõ ràng và thuận tiện cho kiểm thử nhất.

~~~java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    public String hello(@RequestParam(defaultValue = "bạn") String name) {
        return greetingService.greet(name);
    }
}
~~~

Nếu cả hai lớp được đăng ký làm bean, container sẽ tạo **GreetingService**, sau đó cung cấp nó cho constructor của **GreetingController**. Vì controller chỉ cần biết dependency được nhận qua constructor, ta có thể truyền một implementation khác hoặc một đối tượng giả khi kiểm thử bằng Java thuần.

Phân biệt hai khái niệm thường đi cùng nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| IoC | Nguyên tắc đảo quyền kiểm soát việc tạo, lắp ráp và quản lý đối tượng. |
| DI | Một cách hiện thực IoC bằng cách cung cấp dependency cho đối tượng. |
| Bean | Đối tượng được Spring container quản lý. |
| ApplicationContext | Container và điểm truy cập các dịch vụ quản lý đối tượng của Spring. |

DI không phải tính năng do Spring Boot phát minh: **đây là nền tảng của Spring Framework**.

### 2.3. Vòng đời bean và cấu hình ứng dụng

Spring không chỉ gọi constructor. Tùy kiểu bean và cấu hình, container còn có thể:

1. Đọc định nghĩa bean từ annotation hoặc cấu hình Java.
2. Xác định dependency, tạo đối tượng và thực hiện injection.
3. Áp dụng các bean post-processor, proxy và cơ chế khởi tạo cần thiết.
4. Cho phép bean phục vụ các thành phần khác trong ứng dụng.
5. Gọi callback hủy đối tượng khi context đóng, nếu bean và scope hỗ trợ.

Các annotation như **@Configuration**, **@Bean**, **@Component**, **@Service**, **@Repository** và **@Controller** thuộc mô hình cấu hình và thành phần của Spring Framework. Một số annotation chỉ có tác dụng khi cơ chế tương ứng đã được kích hoạt; ví dụ **@Component** cần được quét hoặc đăng ký theo cách phù hợp.

Container cũng hỗ trợ các scope như **singleton** (mặc định cho bean thông thường) và **prototype**, cùng các scope liên quan đến web khi có môi trường web thích hợp. Singleton ở đây có nghĩa **một instance cho mỗi bean definition trong một container**, không nhất thiết là một instance duy nhất trên toàn bộ JVM.

### 2.4. Web: Spring MVC và Spring WebFlux

Spring Framework cung cấp hai mô hình web quan trọng:

- **Spring MVC**: nền tảng web theo mô hình Servlet, thường dùng cho ứng dụng REST/HTTP đồng bộ. **DispatcherServlet** nhận request và phối hợp với cơ chế ánh xạ handler, chuyển đổi dữ liệu, xử lý exception và tạo response.
- **Spring WebFlux**: nền tảng web hỗ trợ lập trình reactive và luồng xử lý bất đồng bộ, dựa trên Reactor. Đây là lựa chọn kiến trúc riêng; dùng Spring Boot không đồng nghĩa ứng dụng tự động trở thành reactive.

Trong ví dụ **GreetingController**, **@RestController**, **@GetMapping** và **@RequestParam** là các thành phần của **Spring MVC**, dù ví dụ thường được chạy bằng Spring Boot.

Một luồng xử lý HTTP kiểu MVC có thể hình dung như sau:

~~~text
HTTP GET /hello?name=Lan
        │
        ▼
Máy chủ HTTP / Servlet container
        │
        ▼
Spring MVC DispatcherServlet
        │ tìm handler phù hợp
        ▼
GreetingController.hello("Lan")
        │ gọi bean qua DI
        ▼
GreetingService.greet("Lan")
        │
        ▼
HTTP 200, body: Xin chào, Lan!
~~~

Máy chủ HTTP xử lý kết nối và Servlet request; Spring MVC định tuyến đến code ứng dụng. Spring Boot có thể tự chuẩn bị máy chủ và cấu hình Spring MVC, nhưng nghiệp vụ và handler vẫn do bạn viết.

### 2.5. Giao dịch, AOP, dữ liệu và kiểm thử

Ngoài web và DI, Spring Framework còn có những nền tảng quan trọng:

| Khả năng của Spring Framework | Vấn đề được giải quyết | Ví dụ |
|---|---|---|
| **AOP (Aspect-Oriented Programming)** | Áp dụng một số hành vi chung quanh lời gọi phương thức thông qua cơ chế như proxy | Ghi log, kiểm soát giao dịch, cơ chế cắt ngang theo cấu hình |
| **Transaction abstraction** | Tổ chức ranh giới giao dịch qua các công nghệ truy cập dữ liệu | **@Transactional**, **PlatformTransactionManager** |
| **Data access integration** | Giảm mã lặp và tích hợp các API dữ liệu | **JdbcTemplate**, tích hợp JPA |
| **Validation và conversion** | Chuyển đổi, ràng buộc và kiểm tra dữ liệu theo cơ chế thích hợp | **Validator**, conversion service |
| **Testing support** | Hỗ trợ tạo, cache và cấu hình Spring context trong kiểm thử | Spring TestContext Framework |
| **Events, resources, scheduling, caching** | Cung cấp hạ tầng dùng lại cho các nhu cầu phổ biến | **ApplicationEventPublisher**, **Resource**, **@Scheduled**, **@Cacheable** |

Ví dụ **@Transactional** đánh dấu mong muốn thực thi một đoạn công việc trong giao dịch. Tuy nhiên, cần có transaction manager phù hợp và lời gọi phải đi qua cơ chế quản lý giao dịch của Spring; việc thêm annotation vào bất kỳ phương thức Java nào không tự tạo ra một transaction.

Cũng cần phân biệt **Spring Framework** với các dự án trong hệ sinh thái Spring. Chẳng hạn **Spring Data**, **Spring Security**, **Spring Cloud** là các dự án liên quan với chức năng riêng. Spring Boot giúp tích hợp và cấu hình nhiều dự án đó, nhưng không biến tất cả chúng thành chức năng thuộc Spring Framework core.

## 3. Spring Boot bổ sung điều gì?

Spring Framework đã có thể xây dựng ứng dụng hoàn chỉnh mà không dùng Spring Boot. Tuy nhiên, lập trình viên phải chọn dependency, khởi tạo context, cấu hình web runtime, nối các thành phần, quản lý phiên bản và chuẩn bị nhiều thiết lập lặp lại. Spring Boot cung cấp một cách thiết lập có **quy ước hợp lý làm mặc định** và cho phép tùy chỉnh khi cần.

### 3.1. Starter dependencies: chọn một nhóm thư viện phù hợp

Thay vì tự khai báo từng thư viện cho web, JSON, máy chủ và kiểm thử, Boot cung cấp các **starter**. Starter là các dependency tiện ích, kéo theo một tập thư viện có liên quan.

Ví dụ, trong dự án Gradle đã cấu hình plugin Spring Boot và cơ chế quản lý dependency tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với **Spring Boot 3.x**, starter web điển hình đưa Spring MVC, các thư viện web cần thiết và Tomcat nhúng mặc định vào classpath. Starter test tập hợp những công cụ kiểm thử thông dụng. Việc ghi một starter **không tạo ra controller hoặc quy tắc nghiệp vụ**.

Spring Boot còn cung cấp cách **quản lý phiên bản dependency** thông qua bộ phiên bản được kiểm thử tương thích (BOM/dependency management). Điều này giảm công sức ghép các phiên bản thư viện Spring và thư viện liên quan. Nó không đảm bảo mọi thư viện bên ngoài hoặc mọi phiên bản được tự ý ghi đè đều tương thích.

Một số starter khác trong hệ sinh thái gồm **spring-boot-starter-data-jpa**, **spring-boot-starter-validation** và **spring-boot-starter-actuator**. Chỉ thêm những starter mà ứng dụng thực sự sử dụng.

### 3.2. Auto-configuration: cấu hình tự động theo điều kiện

Đây là khác biệt rất quan trọng. **Auto-configuration** của Boot quan sát dependency trên classpath, cấu hình hiện tại, loại ứng dụng và các bean đã tồn tại để quyết định những cấu hình nào nên được áp dụng.

Ví dụ với ứng dụng dùng starter web theo mô hình Servlet:

1. Boot thấy các thư viện web cần thiết và xác định ứng dụng thuộc loại Servlet web.
2. Các auto-configuration phù hợp chuẩn bị hạ tầng Spring MVC, máy chủ nhúng và những thành phần liên quan, nếu điều kiện được thỏa mãn.
3. Spring tạo và quản lý controller, service và các bean của ứng dụng.
4. Ứng dụng có thể nhận HTTP request mà không cần bạn tự viết mã khởi tạo **DispatcherServlet** và cấu hình Tomcat cho trường hợp phổ biến.

Auto-configuration **không có nghĩa mọi tính năng đều được bật vô điều kiện**. Một cấu hình có thể phụ thuộc vào:

- Một lớp hoặc thư viện có hiện diện trên classpath hay không.
- Một property có giá trị phù hợp hay không.
- Một bean của loại nhất định đã được khai báo hay chưa.
- Môi trường hiện tại có phải là web application phù hợp hay không.

Các annotation điều kiện như **@ConditionalOnClass**, **@ConditionalOnMissingBean**, **@ConditionalOnProperty** là những công cụ quan trọng trong cơ chế này.

Ví dụ: chỉ thêm thư viện kết nối cơ sở dữ liệu không có nghĩa Boot có thể đoán URL, tài khoản và cấu trúc dữ liệu của hệ thống thực tế. Tùy các dependency và điều kiện, Boot có thể cấu hình DataSource mặc định, yêu cầu thêm thông tin, hoặc không áp dụng cấu hình liên quan.

**Có thể tùy chỉnh hay tắt auto-configuration không?** Có. Spring Boot cho phép khai báo bean/cấu hình riêng, cung cấp properties hoặc exclude những auto-configuration cụ thể. Mức độ ghi đè tùy theo từng cấu hình và các điều kiện của nó; không nên mặc định rằng một bean tùy ý sẽ tự thay thế được mọi thiết lập của Boot.

### 3.3. Điểm khởi động chuẩn hóa

Ứng dụng Boot thông thường có entry point như sau:

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

**SpringApplication.run(...)** điều phối việc chuẩn bị environment, tạo Spring application context thích hợp, nạp cấu hình, đăng ký bean và khởi động môi trường chạy. Nếu đây là ứng dụng web có cấu hình phù hợp, Boot còn có thể khởi chạy máy chủ HTTP nhúng.

**@SpringBootApplication** kết hợp các ý nghĩa chính:

| Thành phần | Vai trò |
|---|---|
| **@SpringBootConfiguration** | Đánh dấu lớp cấu hình ứng dụng; dựa trên cơ chế **@Configuration** của Spring. |
| **@EnableAutoConfiguration** | Cho phép Boot xem xét các auto-configuration phù hợp. |
| **@ComponentScan** | Tìm component/bean từ package của lớp ứng dụng và các package con theo quy ước mặc định. |

Do đó, đặt **DemoApplication** trong package gốc **com.example.demo** và đặt **GreetingService**, **GreetingController** ở các package con là một lựa chọn có chủ ý. Nếu đặt component ngoài phạm vi quét, Spring có thể không tìm thấy bean; cần điều chỉnh cách tổ chức package hoặc khai báo cấu hình quét tương ứng.

### 3.4. Máy chủ nhúng và cách đóng gói chạy được

Với ứng dụng Spring MVC thông thường, Boot có thể chạy **Tomcat nhúng** ngay trong tiến trình ứng dụng. Quy trình phổ biến là đóng gói thành executable JAR rồi chạy trên JVM, hoặc dùng **bootRun** khi phát triển.

~~~text
JVM
 └─ Ứng dụng Spring Boot
     ├─ Embedded Servlet container (ví dụ: Tomcat)
     ├─ Spring MVC DispatcherServlet
     ├─ Spring ApplicationContext
     └─ Controller, service, repository, ...
~~~

Điều này giảm nhu cầu tự chuẩn bị một ứng dụng WAR rồi triển khai vào một server Servlet đã được cài đặt sẵn cho mỗi dự án. Tuy vậy, **Spring Boot không bắt buộc phải là ứng dụng web hoặc luôn phải có Tomcat**: ứng dụng command-line có thể không mở cổng HTTP; ứng dụng WebFlux có lựa chọn runtime khác; và ứng dụng Boot Servlet vẫn có thể được đóng gói phù hợp để triển khai vào servlet container bên ngoài khi cần.

### 3.5. Externalized configuration: cấu hình tách khỏi code

Boot thống nhất cách cung cấp cấu hình từ nhiều nguồn như file **application.properties**, **application.yml**, biến môi trường, tham số chạy và nguồn cấu hình được hỗ trợ khác. Cách này giúp cùng một artifact ứng dụng dùng cấu hình khác nhau theo môi trường.

Ví dụ file **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: greeting-demo
~~~

Property **server.port** điều khiển cổng máy chủ web nhúng theo cấu hình Boot. Khi chạy trong môi trường phù hợp, ví dụ trên đổi cổng HTTP từ mặc định thường gặp **8080** sang **8081**.

Với property tự định nghĩa như **app.greeting-prefix**, Boot chỉ cung cấp cơ chế đọc và bind cấu hình; bạn vẫn cần viết code tiếp nhận giá trị đó, ví dụ qua **@ConfigurationProperties** hoặc **@Value**. Boot không tự biến một property nghiệp vụ thành hành vi mới.

**Profiles** hỗ trợ các cấu hình được kích hoạt theo môi trường, chẳng hạn **dev** và **prod**. Nên dùng cơ chế cấu hình và secret thích hợp thay vì hardcode mật khẩu vào source code hoặc ghi bí mật vào file cấu hình đem commit.

### 3.6. Quan sát ứng dụng và hỗ trợ phát triển

Spring Boot có thêm các tiện ích thường thấy ở ứng dụng thực tế:

- **Actuator** (thêm bằng starter riêng): hỗ trợ thông tin health, metrics và endpoint quản trị/quan sát. Ví dụ endpoint web **/actuator/health** có thể được cung cấp khi Actuator được bật; endpoint nào được expose phụ thuộc cấu hình và bảo mật.
- **Logging conventions**: thiết lập tích hợp logging mặc định cho tình huống phổ biến và hỗ trợ tùy chỉnh mức log.
- **Development tools**: tùy chọn như **spring-boot-devtools** giúp vòng lặp phát triển thuận tiện hơn.
- **Testing support**: các tiện ích như **@SpringBootTest** hỗ trợ kiểm thử trong ngữ cảnh Boot, xây dựng trên nền tảng kiểm thử của Spring.
- **Packaging và startup tools**: plugin build hỗ trợ tạo executable JAR/WAR phù hợp, chạy ứng dụng và một số tác vụ đóng gói.

Các tính năng này không tự bảo đảm ứng dụng an toàn hay sẵn sàng production. Ví dụ, việc expose endpoint quản trị cần quyết định rõ về mạng, quyền truy cập và bảo mật.

## 4. So sánh trực tiếp Spring Framework và Spring Boot

| Câu hỏi | Spring Framework | Spring Boot |
|---|---|---|
| Bản chất là gì? | Bộ framework nền tảng cho ứng dụng Java. | Công cụ và các quy ước xây dựng trên Spring Framework. |
| Ai tạo và nối các bean? | Spring IoC container. | Vẫn là Spring IoC container; Boot giúp khởi tạo và cấu hình. |
| Ai cung cấp **@Service**, **@Bean**, DI? | Spring Framework. | Sử dụng lại các cơ chế đó. |
| Ai cung cấp **@RestController**, **@GetMapping**? | Spring MVC thuộc Spring Framework. | Có thể tự cấu hình hạ tầng MVC khi dependency phù hợp. |
| Ai cung cấp **@Transactional**? | Hạ tầng transaction của Spring. | Có thể tự cấu hình một số thành phần transaction khi điều kiện phù hợp. |
| Chọn dependency thế nào? | Lập trình viên tự quyết định và quản lý. | Có starter và bộ phiên bản được quản lý. |
| Cần cấu hình bao nhiêu? | Phụ thuộc cách xây dựng; thường phải lắp ráp nhiều phần hơn. | Có sẵn nhiều mặc định theo điều kiện, vẫn cho phép tùy chỉnh. |
| Khởi chạy HTTP server? | Cung cấp framework web, nhưng việc tích hợp server do ứng dụng cấu hình. | Có thể khởi chạy server nhúng trong ứng dụng web thích hợp. |
| Cấu hình theo môi trường? | Có **Environment**, **PropertySource** và khả năng cấu hình nền tảng. | Chuẩn hóa việc nạp và sử dụng nhiều nguồn cấu hình, conventions, profiles. |
| Health/metrics tiện ích? | Có các cơ chế nền tảng để tích hợp. | Actuator cung cấp tập tính năng quan sát khi được thêm và cấu hình. |
| Có thể dùng độc lập không? | **Có.** Spring Framework không yêu cầu Boot. | **Không theo nghĩa thay thế Framework:** Boot dựa vào Spring Framework. |

Điểm cần ghi nhớ là **cùng một API của Spring Framework có thể xuất hiện trong ứng dụng dùng Boot lẫn ứng dụng không dùng Boot**. Ví dụ controller ở phần trước vẫn là Spring MVC controller; Boot chỉ giúp chuẩn bị môi trường cho nó chạy dễ dàng hơn.

## 5. Ví dụ đối chiếu: cùng một GreetingService, hai cách khởi động

### 5.1. Dùng Spring Framework trực tiếp, không dùng Boot

Nếu chỉ muốn một chương trình Java khởi tạo bean và gọi nghiệp vụ, có thể tạo **ApplicationContext** bằng API của Spring Framework:

~~~java
package com.example.demo;

import com.example.demo.service.GreetingService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.demo.service")
class CoreConfig {
}

public class PlainSpringApp {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            GreetingService service = context.getBean(GreetingService.class);
            System.out.println(service.greet("Lan"));
        }
    }
}
~~~

Kết quả:

~~~text
Xin chào, Lan!
~~~

Điều này minh họa rằng **IoC, component scanning và DI hoạt động mà không cần Spring Boot**. Chương trình này chưa mở HTTP server; nếu muốn cung cấp REST API trực tiếp bằng Spring MVC, cần thêm dependency và cấu hình web runtime phù hợp. Spring Framework hiện đại có thể cấu hình bằng Java annotation, không bắt buộc phải dùng XML.

### 5.2. Dùng Spring Boot cho REST API

Với **GreetingService** và **GreetingController** đã định nghĩa ở phần 2, một ứng dụng Boot thông thường cần:

1. Dự án có cấu hình plugin/dependency management Spring Boot phù hợp và dependency **spring-boot-starter-web**.
2. Lớp **DemoApplication** với **@SpringBootApplication** và **SpringApplication.run(...)**.
3. Các component thuộc phạm vi quét của ứng dụng.

Sau khi chạy ứng dụng bằng tác vụ **bootRun** hoặc executable JAR đã build, có thể gửi:

~~~http
GET /hello?name=Lan HTTP/1.1
Host: localhost:8080
~~~

Ứng dụng trả response có body:

~~~text
Xin chào, Lan!
~~~

Ở ví dụ này, **Spring Framework** đảm nhiệm bean, DI, controller và định tuyến MVC; **Spring Boot** hỗ trợ chọn dependency, thiết lập MVC, tạo web application context, khởi chạy server nhúng và nạp cấu hình.

Nếu đã đặt **server.port: 8081** như phần trên, request cần gửi đến cổng **8081** thay vì **8080**. Kết quả cũng giả định máy chủ thực sự đã khởi động và không có cấu hình path/security khác can thiệp.

### 5.3. Diễn biến khi gọi SpringApplication.run

Ở mức khái niệm, quá trình chạy có thể mô tả như sau:

~~~text
DemoApplication.main()
    │
    ▼
SpringApplication.run(...)
    │
    ├─ Chuẩn bị environment và nguồn cấu hình
    ├─ Tạo loại ApplicationContext thích hợp
    ├─ Xử lý cấu hình ứng dụng và auto-configuration đủ điều kiện
    ├─ Đăng ký, tạo, liên kết các bean qua Spring container
    ├─ Khởi động embedded server nếu là ứng dụng web phù hợp
    └─ Hoàn tất giai đoạn khởi động
                    │
                    ▼
       Sẵn sàng xử lý nghiệp vụ/request
~~~

Đây là mô hình để hiểu trách nhiệm, không phải danh sách chính xác của mọi callback nội bộ; trình tự chi tiết thay đổi theo loại ứng dụng, phiên bản và các extension point.

## 6. Khi nào dùng Framework trực tiếp, khi nào dùng Boot?

**Spring Boot thường là lựa chọn mặc định hợp lý** cho một dịch vụ REST, backend web, tác vụ nền hoặc ứng dụng Spring mới cần cấu hình nhanh, quản lý dependency nhất quán và vận hành độc lập. Lợi ích đặc biệt rõ khi nhóm cần tạo nhiều dịch vụ có cách tổ chức và chạy tương tự.

**Dùng Spring Framework trực tiếp** vẫn phù hợp nếu bạn viết thư viện tích hợp cần ít ràng buộc vào Boot, có môi trường container được quản lý riêng, hoặc muốn tự quyết định cách khởi tạo hạ tầng. Đây là lựa chọn kỹ thuật có chủ đích, không phải một giai đoạn bắt buộc phải trải qua trước khi học Boot.

Trong cả hai trường hợp, vẫn nên nắm vững cách **bean được tạo**, **dependency được inject**, **component được quét**, **MVC xử lý request** và **giao dịch được quản lý**. Nếu thiếu những kiến thức đó, lỗi như *không tìm thấy bean*, *có nhiều bean cùng loại*, *vòng phụ thuộc* hoặc *auto-configuration không kích hoạt* sẽ khó phân tích.

## 7. Những hiểu nhầm thường gặp

**“Spring Boot là phiên bản mới hơn của Spring Framework?”**  
Không. Đây là hai dự án với vai trò khác nhau, phát triển và tương thích theo những phiên bản cụ thể. Spring Boot sử dụng Spring Framework làm nền tảng.

**“Dùng Boot thì không cần học IoC/DI và Spring MVC?”**  
Vẫn cần. Boot giảm mã cấu hình lặp lại; các đối tượng và request vẫn được Spring Framework quản lý. Biết nền tảng sẽ giúp hiểu hành vi và sửa lỗi.

**“Cứ thêm @RestController là API sẽ tự hoạt động?”**  
Chưa đủ. Phải có Spring context đăng ký controller, hạ tầng web tương ứng, máy chủ HTTP và cấu hình phù hợp. Boot thường cung cấp sẵn nhiều phần đó khi có starter đúng.

**“Auto-configuration nghĩa là Boot biết hết mọi thứ mình muốn?”**  
Không. Nó ra quyết định dựa trên điều kiện và mặc định được định nghĩa trước. Nó không thể suy ra quy tắc nghiệp vụ, quyền truy cập, endpoint hoặc kết nối cơ sở dữ liệu tùy ý của bạn.

**“Starter chính là auto-configuration?”**  
Không. **Starter** chủ yếu giúp đưa một nhóm dependency vào dự án; **auto-configuration** là code cấu hình chạy có điều kiện, dựa trên classpath và thông tin môi trường. Hai cơ chế bổ trợ nhau.

**“Spring Boot luôn dùng Tomcat và chỉ viết được REST API?”**  
Không. Tomcat là lựa chọn mặc định phổ biến của ứng dụng Servlet web với starter phù hợp. Boot còn hỗ trợ loại ứng dụng khác, runtime khác và cả chương trình không có HTTP server.

**“Có Spring Boot thì mọi thứ trong Spring Data/Security/Cloud đã sẵn sàng?”**  
Không. Mỗi dự án có dependency, cấu hình và hành vi riêng. Boot giúp lắp ráp các phần được chọn; bạn vẫn cần thêm thư viện và thiết kế chính sách phù hợp.

## 8. Cách tự kiểm chứng điều Boot đã làm

Khi học một tính năng mới, thay vì chỉ nhìn vào đoạn code “chạy được”, hãy lần theo ba câu hỏi:

1. **Bean hoặc API này đến từ đâu?** Ví dụ, **@GetMapping** thuộc Spring MVC; **@SpringBootApplication** thuộc Spring Boot.
2. **Thư viện nào khiến tính năng có mặt?** Ví dụ, starter web đưa các dependency cần thiết cho trường hợp web MVC thông thường.
3. **Cấu hình nào khiến tính năng được kích hoạt?** Có thể là component scanning, auto-configuration theo điều kiện, property hoặc bean do bạn khai báo.

Trong môi trường Spring Boot, có thể chạy với tùy chọn **--debug** để xem thêm thông tin chẩn đoán về các điều kiện auto-configuration, bao gồm những cấu hình đã hoặc chưa được áp dụng. Không nên nhầm log này với việc tất cả bean đều được Boot tự tạo: component do ứng dụng khai báo vẫn được Spring container quản lý theo cơ chế của Framework.

Ví dụ thực hành mở rộng hợp lý là thay lời chào tĩnh bằng một **GreetingService** có cấu hình tiền tố riêng, sau đó thêm một dependency giả trong unit test. Khi thay service bằng constructor injection mà không sửa controller, bạn đang quan sát lợi ích của **Spring DI**; khi điều chỉnh **application.yml** mà không biên dịch lại logic nghiệp vụ, bạn đang quan sát lợi ích của **Spring Boot externalized configuration**.

## Ghi nhớ cốt lõi

**Spring Framework là nền móng kỹ thuật:** IoC container, DI, vòng đời bean, MVC/WebFlux, giao dịch, AOP và nhiều hạ tầng lập trình ứng dụng.

**Spring Boot là lớp tổ chức và tự động hóa dựa trên nền móng đó:** starter, dependency management, auto-configuration, entry point, máy chủ nhúng, cấu hình ngoài code, đóng gói và tiện ích vận hành.

**Ứng dụng vẫn do bạn thiết kế:** lựa chọn module, định nghĩa bean, API, nghiệp vụ, dữ liệu, bảo mật và cách triển khai. Hiểu đúng ranh giới này giúp bạn tận dụng sự tiện lợi của Spring Boot mà vẫn giải thích được điều gì đang thực sự xảy ra bên dưới.
