# Tự cấu hình của Spring Boot và phần hành vi do ứng dụng sở hữu

> **Bối cảnh:** Spring Boot web runtime, trọng tâm Spring MVC trên Servlet stack. Ví dụ thực hành dùng Spring Boot 4.1.2, Java 17 và Maven. Các nguyên tắc về điều kiện tự cấu hình cũng áp dụng cho nhiều phiên bản Spring Boot 3.x; tên starter và một số API có thể khác theo phiên bản.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Spring Boot tự cấu hình hạ tầng** với **các quyết định và hành vi do ứng dụng định nghĩa**.
2. Giải thích vì sao dependency, thuộc tính môi trường và các bean sẵn có làm kết quả tự cấu hình thay đổi.
3. Lần theo đường đi của một HTTP request: web server → Spring MVC → controller → service → response.
4. Tùy biến Spring MVC theo cách giữ được cấu hình thuận tiện của Boot và chẩn đoán một cấu hình không được áp dụng.

## 1. Ranh giới trách nhiệm: Boot thiết lập khả năng, ứng dụng quyết định hành vi

**Auto-configuration (tự cấu hình)** là cơ chế Spring Boot xem xét thư viện trên classpath, loại ứng dụng, thuộc tính cấu hình và các bean đã được đăng ký để **có điều kiện** khai báo những bean hạ tầng phù hợp. Mục tiêu là giảm phần cấu hình lặp lại, chẳng hạn tạo web server nhúng và cấu hình Spring MVC khi ứng dụng có dependency web tương ứng.

**Phần hành vi do ứng dụng sở hữu** là hợp đồng nghiệp vụ và chính sách mà nhóm phát triển tự quyết định: URL nào tồn tại, dữ liệu nào được trả về, quy tắc kiểm tra đầu vào, xử lý lỗi, quyền truy cập, thao tác dữ liệu, chính sách HTTP riêng và các tích hợp cụ thể.

Ví dụ, khi thêm starter Spring MVC, Boot có thể cấu hình Tomcat và cơ chế định tuyến HTTP. Nhưng Boot không tự biết phải có API `GET /api/greetings/{name}`, thông điệp chào nào là đúng, hay ai được gọi API đó. Những quyết định này chỉ xuất hiện khi ứng dụng khai báo controller, service và cấu hình tương ứng.

| Thành phần/quyết định | Ai cung cấp hoặc quyết định? | Ý nghĩa thực tế |
| --- | --- | --- |
| Dependency `spring-boot-starter-webmvc` | Ứng dụng chọn; starter cung cấp thư viện | Tạo điều kiện để Boot nhận diện web MVC và auto-config hạ tầng |
| Tomcat nhúng, tích hợp Servlet, `DispatcherServlet`, cấu hình MVC mặc định | Spring Boot + Spring Framework khi điều kiện phù hợp | Có runtime tiếp nhận và dispatch HTTP request |
| `@RestController`, `@GetMapping`, `@Service` và thuật toán nghiệp vụ | Ứng dụng | Quyết định API và kết quả thực tế |
| `server.port=8090` | Ứng dụng khai báo; Boot đọc và áp dụng | Ứng dụng chọn giá trị, Boot đảm nhiệm cách cấu hình server |
| `WebMvcConfigurer`, interceptor hoặc bean cấu hình tùy chỉnh | Ứng dụng | Mở rộng hoặc thay thế hành vi cụ thể theo các điểm mở rộng đã hỗ trợ |
| Logging, JSON, lỗi HTTP, bảo mật | Framework/starter có thể cung cấp hạ tầng hoặc mặc định; ứng dụng quyết định yêu cầu riêng | Không được xem mặc định của framework là đặc tả nghiệp vụ hay chính sách an toàn đã hoàn chỉnh |

Có ba cơ chế dễ nhầm với nhau:

- **Component scan:** `@ComponentScan` tìm các lớp ứng dụng mang `@Component`, `@Service`, `@Controller`, `@RestController`, `@Configuration`… trong phạm vi quét. Đây là cách đưa **thành phần do ứng dụng viết** vào `ApplicationContext`.
- **Auto-configuration:** `@EnableAutoConfiguration` nhập các lớp cấu hình do Boot hoặc thư viện cung cấp, rồi xét điều kiện để tạo **bean/hạ tầng mặc định phù hợp**. Nó không quét và tự sinh business logic.
- **Cấu hình tường minh:** `@Bean`, `@Configuration`, thuộc tính `application.properties`/`application.yaml` và các extension point thể hiện **lựa chọn của ứng dụng**. Một số lựa chọn khiến auto-configuration áp dụng khác đi.

Thông thường chỉ đặt **một** `@SpringBootApplication` trên lớp khởi động. Annotation này kết hợp `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Đặt lớp khởi động ở package gốc của mã ứng dụng giúp component scan tìm controller/service ở các package con.

## 2. Điều gì xảy ra khi web runtime khởi động?

Với một ứng dụng Servlet MVC điển hình:

1. `main()` gọi `SpringApplication.run(...)`.
2. Spring Boot chuẩn bị `Environment`, đọc cấu hình và xác định loại `ApplicationContext` phù hợp với classpath/cấu hình.
3. Spring xử lý lớp `@SpringBootApplication`, đăng ký các component do ứng dụng khai báo và nạp những auto-configuration candidate.
4. Mỗi auto-configuration kiểm tra điều kiện: thư viện có mặt không, loại web application có đúng không, thuộc tính có bật không, bean tương ứng đã tồn tại chưa…
5. Trong quá trình refresh context, framework tạo/ghép bean cần thiết. Với ứng dụng Servlet và starter MVC, web server nhúng, `DispatcherServlet`, các thành phần mapping, argument resolution, message conversion… được thiết lập theo cấu hình.
6. Web server bắt đầu nhận request; lifecycle khởi động kết thúc khi ứng dụng sẵn sàng phục vụ theo các cơ chế readiness tương ứng.

Điểm quan trọng: **tự cấu hình chủ yếu quyết định cấu trúc ứng dụng khi context được khởi tạo**. Nó không tự viết lại logic controller mỗi khi HTTP request đến. Khi request chạy, các bean và pipeline đã cấu hình được sử dụng.

Luồng một request REST thông thường:

~~~text
HTTP client
    |
    v
Tomcat (Servlet container)
    |
    v
Servlet Filter chain (nếu có)
    |
    v
DispatcherServlet (Spring MVC)
    |
    +--> HandlerMapping tìm route phù hợp
    +--> HandlerInterceptor trước handler (nếu đăng ký)
    +--> HandlerAdapter gọi controller của ứng dụng
                         |
                         v
                  Service/nghiệp vụ của ứng dụng
                         |
                         v
                    Controller trả dữ liệu
    |
    +--> HttpMessageConverter ghi response, ví dụ JSON
    +--> Hoàn tất interceptor/filter tương ứng
    |
    v
HTTP response
~~~

Đường đi thực tế có thể có exception resolver, argument resolver, validation, security filter và nhiều thành phần khác. **Spring MVC thực hiện điều phối; controller/service của ứng dụng quyết định ngữ nghĩa nghiệp vụ.** Khi dùng WebFlux, pipeline phản ứng và server có thể khác (ví dụ Reactor Netty), nên không áp nguyên sơ sơ đồ Servlet này cho WebFlux.

## 3. Vì sao cùng mã nguồn mà auto-configuration có thể khác nhau?

Auto-configuration dùng các điều kiện như:

| Điều kiện | Câu hỏi kiểm tra | Ví dụ ý nghĩa |
| --- | --- | --- |
| `@ConditionalOnClass` | Một class/thư viện cần thiết có trên classpath? | Chỉ bật phần tích hợp nếu công nghệ tương ứng đã được thêm vào |
| `@ConditionalOnWebApplication` | Đây là ứng dụng Servlet hay reactive phù hợp? | Chọn nhánh cấu hình theo web stack |
| `@ConditionalOnBean` | Bean làm tiền đề đã hiện diện? | Cấu hình bổ sung chỉ chạy khi phụ thuộc phù hợp tồn tại |
| `@ConditionalOnMissingBean` | Chưa có bean do người dùng hoặc cấu hình khác cung cấp? | Mặc định có thể nhường chỗ cho bean ứng dụng tự khai báo |
| `@ConditionalOnProperty` | Cấu hình môi trường có giá trị tương ứng? | Có thể bật/tắt một tính năng có điều kiện |

**“Back off” có nghĩa hẹp:** khi điều kiện của **một phần auto-configuration cụ thể** không còn thỏa, bean/cấu hình mặc định tương ứng không được tạo. Nó không có nghĩa khai báo bất kỳ `@Bean` nào cũng tắt toàn bộ Spring Boot. Việc bean nào được thay thế phụ thuộc **đúng loại bean và điều kiện của auto-configuration đó**. Với `@ConditionalOnMissingBean`, cũng cần lưu ý thứ tự đăng ký bean definitions; tài liệu Boot khuyến nghị điều kiện kiểu này trong auto-configuration vì cấu hình của người dùng được xử lý trước.

Ví dụ về quan hệ nhân quả:

- **Thêm starter MVC:** classpath có các lớp web; điều kiện web MVC phù hợp hơn, Boot tạo các thành phần liên quan.
- **Đổi `server.port`:** hạ tầng server vẫn là Boot cấu hình, nhưng ứng dụng quyết định cổng lắng nghe.
- **Viết thêm `@RestController`:** ứng dụng có thêm route; Boot không phải tự “phát hiện” endpoint từ tên bài học hay tự sinh nghiệp vụ.
- **Cung cấp bean tùy chỉnh đúng extension point:** bean đó có thể bổ sung một phần hạ tầng hoặc khiến bean mặc định tương ứng back off.
- **Loại trừ một auto-configuration bằng `exclude`/`spring.autoconfigure.exclude`:** chỉ nên làm khi biết chính xác lớp cấu hình cần loại và hậu quả, vì có thể phải tự cung cấp phần hạ tầng còn thiếu.

Các auto-configuration candidate hiện đại được khai báo trong tệp `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của jar tương ứng. Đây là cơ chế nạp cấu hình, **không phải danh sách API nghiệp vụ** mà ứng dụng nên gọi trực tiếp.

## 4. Ví dụ chạy được: Boot dựng runtime, ứng dụng sở hữu API

Ví dụ sử dụng **Spring Boot 4.1.2**, **JDK 17+**, **Maven 3.6.3+**. Ở Spring Boot 4, `spring-boot-starter-webmvc` là starter trực tiếp cho Spring MVC/Tomcat; khi làm dự án Spring Boot 3.x, thường dùng `spring-boot-starter-web` với phiên bản Boot 3.x tương thích. Để mã dễ quan sát, demo chỉ dùng một API trả JSON và một interceptor thêm response header.

Cấu trúc thư mục:

~~~text
ownership-demo/
  pom.xml
  src/main/java/com/example/ownership/
    OwnershipApplication.java
    GreetingService.java
    GreetingController.java
    HttpPolicyConfig.java
  src/main/resources/
    application.properties
~~~

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>ownership-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

Parent của Boot quản lý các phiên bản dependency tương thích. Starter MVC cung cấp các thành phần cần cho Spring MVC, Tomcat và JSON theo bộ dependency của phiên bản minh họa; ứng dụng không cần tự khởi tạo `DispatcherServlet`.

**`src/main/java/com/example/ownership/OwnershipApplication.java`**

~~~java
package com.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
~~~

Đây là điểm khởi động, không chứa logic chào hỏi. Package `com.example.ownership` bao trùm các lớp còn lại để component scan tìm thấy chúng.

**`src/main/java/com/example/ownership/GreetingService.java`**

~~~java
package com.example.ownership;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Chuỗi `Hello, ...!` là **quy tắc nghiệp vụ do ứng dụng sở hữu**, không liên quan đến mặc định của Spring Boot.

**`src/main/java/com/example/ownership/GreetingController.java`**

~~~java
package com.example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/{name}")
    public GreetingResponse greet(@PathVariable String name) {
        return new GreetingResponse(service.greet(name));
    }

    public record GreetingResponse(String message) {}
}
~~~

Ứng dụng định nghĩa URL, HTTP method, tên tham số và hình dạng JSON qua `GreetingResponse`. Spring MVC ánh xạ request vào method này và bộ chuyển đổi HTTP/JSON được cấu hình phù hợp sẽ serialize record thành response. Constructor injection dùng bean `GreetingService` đã tìm được qua component scan.

**`src/main/java/com/example/ownership/HttpPolicyConfig.java`**

~~~java
package com.example.ownership;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class HttpPolicyConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        HandlerInterceptor addHeader = new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request,
                                     HttpServletResponse response,
                                     Object handler) {
                response.setHeader("X-App-Policy", "greeting-demo");
                return true;
            }
        };
        registry.addInterceptor(addHeader).addPathPatterns("/api/**");
    }
}
~~~

Đây là **chính sách HTTP của ứng dụng**. `WebMvcConfigurer` bổ sung interceptor cho Spring MVC trong khi giữ phần lớn cấu hình MVC thuận tiện của Boot. `preHandle` trả `true` để tiếp tục gọi controller. Header trên chỉ minh họa ownership; nó không thay thế xác thực, phân quyền hoặc cơ chế bảo mật.

**`src/main/resources/application.properties`**

~~~properties
server.port=8090
~~~

Cổng là lựa chọn của ứng dụng; việc thực sự cấu hình connector của Tomcat là phần hạ tầng. Nếu bỏ dòng này, cổng HTTP mặc định thông thường là `8080`, với điều kiện không có nguồn cấu hình khác ghi đè.

**Chạy và kiểm chứng**

Tại thư mục `ownership-demo`, nơi chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Mở terminal thứ hai và gọi:

~~~bash
curl -i http://localhost:8090/api/greetings/Lan
~~~

Trên Windows PowerShell 5.1, có thể dùng `curl.exe -i http://localhost:8090/api/greetings/Lan` để gọi đúng chương trình curl. Kỳ vọng nhận **HTTP 200**, header `X-App-Policy: greeting-demo`, Content-Type JSON và body sau (các header như Date/Connection có thể thay đổi):

~~~json
{"message":"Hello, Lan!"}
~~~

Có thể đóng gói rồi chạy JAR:

~~~bash
mvn package
java -jar target/ownership-demo-0.0.1-SNAPSHOT.jar
~~~

Maven tải dependency và biên dịch source; chạy riêng `javac` mà không có classpath Spring sẽ không đủ để build ví dụ này.

**Tách nghĩa từng bước quan sát được:**

| Điều quan sát | Nguồn gốc |
| --- | --- |
| Ứng dụng có web server HTTP ở cổng `8090` | Boot cấu hình server theo dependency và thuộc tính do ứng dụng đặt |
| `GET /api/greetings/Lan` tìm được handler | Spring MVC dispatch theo mapping ứng dụng khai báo |
| Response body chứa `Hello, Lan!` | `GreetingService` và `GreetingController` của ứng dụng |
| Response có `X-App-Policy: greeting-demo` | Interceptor ứng dụng tự đăng ký |
| Response được serialize thành JSON | Hạ tầng message conversion + thư viện JSON được cấu hình phù hợp |

Thử sửa `GreetingService.greet()` thành `return "Welcome, " + name + "!";` rồi chạy lại: body đổi, trong khi server/MVC vẫn do Boot hỗ trợ. Ngược lại, đổi `server.port=8091` rồi khởi động lại: địa chỉ truy cập đổi, nhưng nội dung nghiệp vụ không phải viết lại. Đây là cách quan sát trực tiếp **ranh giới sở hữu**.

## 5. Chọn cấp độ tùy biến phù hợp

Theo thứ tự từ ít can thiệp đến nhiều can thiệp:

1. **Chấp nhận mặc định có điều kiện:** dùng starter phù hợp, chỉ viết controller/service cần thiết.
2. **Đặt property được hỗ trợ:** ví dụ `server.port`, giới hạn kích thước request hoặc chính sách session phù hợp; kiểm tra đúng tên property theo phiên bản.
3. **Thêm component/extension point:** khai báo `WebMvcConfigurer`, `Converter`, `Filter`, `HandlerInterceptor`, `@ControllerAdvice` hoặc các bean tùy biến mà framework hỗ trợ. Chọn cơ chế đúng tầng: Servlet filter chạy ở tầng Servlet, interceptor của MVC chạy quanh handler, service thực hiện nghiệp vụ.
4. **Cung cấp bean thay thế một mặc định:** chỉ làm khi tài liệu hoặc condition report xác nhận loại bean đó được auto-config tạo có điều kiện; cần kiểm tra tương thích và các phụ thuộc của bean thay thế.
5. **Tự nắm quyền cấu hình một nhóm hạ tầng:** chẳng hạn dùng `@EnableWebMvc` khi muốn kiểm soát toàn bộ cấu hình MVC. Đây là quyết định lớn: Spring Boot MVC auto-configuration sẽ không còn áp dụng như trước; ứng dụng phải tự xử lý những phần tiện ích mà mình cần.
6. **Exclude auto-configuration riêng:** biện pháp có chủ đích khi hoàn toàn không muốn một nhánh cấu hình. Không dùng exclude chỉ để “chữa” một lỗi chưa tìm được nguyên nhân.

Không nên dùng `@EnableWebMvc` chỉ để thêm một interceptor, formatter hoặc mapping: trong trường hợp đó, `WebMvcConfigurer` là điểm mở rộng phù hợp hơn.

Một lưu ý quan trọng về **Spring Security**: thêm dependency bảo mật có thể kích hoạt các mặc định bảo mật do framework cấu hình. Tuy nhiên, chính sách ai được truy cập route nào, xác thực nguồn nào và cấp quyền nào vẫn cần được ứng dụng thiết kế, kiểm thử và sở hữu. Không suy ra rằng ứng dụng đã an toàn chỉ vì có starter hoặc auto-configuration.

## 6. Chẩn đoán khi Boot không cấu hình như mong đợi

Đừng đoán từ tên starter. Hãy kiểm tra chuỗi nhân quả:

1. **Classpath:** dependency đúng phiên bản và đúng web stack chưa? MVC và WebFlux là hai mô hình phục vụ request khác nhau; servlet controller/interceptor trong ví dụ này thuộc Spring MVC.
2. **Nguồn thuộc tính:** `application.properties`, profile, biến môi trường, tham số dòng lệnh có đang đặt cùng key không? Giá trị hiệu lực có thể đến từ nguồn ưu tiên cao hơn.
3. **Bean definitions:** ứng dụng có khai báo bean làm điều kiện `@ConditionalOnMissingBean` không còn đúng không? Có cấu hình tường minh chiếm quyền MVC không?
4. **Component scan:** lớp `@SpringBootApplication` có ở package cha của controller/service/config không? Bean có được đăng ký vào context không?
5. **Condition report:** khởi động với `--debug` để xem lý do các auto-configuration được hoặc không được áp dụng. Chẳng hạn có thể chạy `mvn spring-boot:run -Dspring-boot.run.arguments=--debug` với cú pháp truyền tham số tương thích shell.
6. **Actuator khi cần:** nếu thêm dependency `spring-boot-starter-actuator`, endpoint `conditions` có thể cho thấy các condition match/không match. Cần cấu hình quyền truy cập và exposure phù hợp; không công khai endpoint chẩn đoán nhạy cảm ra Internet.

Khi xem báo cáo, tìm tên auto-configuration liên quan (ví dụ MVC/Servlet web server) và phân biệt:

- **Positive matches:** điều kiện tương ứng thỏa.
- **Negative matches:** điều kiện không thỏa; lý do thường cho biết thiếu class, sai loại ứng dụng, thiếu bean hay có bean thay thế.
- **Exclusions:** auto-configuration bị loại trừ theo cấu hình.

Condition report nói về **quyết định cấu hình**, không chứng minh API nghiệp vụ đúng. Muốn biết endpoint thực sự trả gì, vẫn phải chạy request test hoặc integration test.

| Triệu chứng | Hướng kiểm tra đầu tiên | Ai cần xử lý? |
| --- | --- | --- |
| Ứng dụng chạy nhưng `/api/greetings/Lan` trả 404 | Mapping, component scan, context path, cổng đang gọi | Chủ yếu mã/cấu hình của ứng dụng |
| Khởi động báo thiếu bean | Dependency, annotation, constructor injection, condition report | Ứng dụng khai báo và Boot condition cần được hiểu cùng nhau |
| Cổng không như `application.properties` | Nguồn cấu hình có độ ưu tiên khác, profile, tham số chạy | Ứng dụng/triển khai |
| Interceptor không chạy | `HttpPolicyConfig` được scan chưa; path pattern có khớp không; có `@EnableWebMvc` bất ngờ không | Ứng dụng |
| JSON bị lỗi hoặc kiểu dữ liệu không serialize được | Dependency JSON, message converter, kiểu response và lỗi thực tế | Cả hạ tầng được cấu hình và mã ứng dụng |
| Thêm thư viện làm runtime thay đổi | Classpath, loại web app, các condition vừa đổi kết quả | Kiểm tra chính sách dependency và auto-configuration |

## 7. Những hiểu lầm phổ biến

- **“Có starter web nghĩa là tự có API.”** Sai. Starter làm hạ tầng HTTP khả dụng; route vẫn phải được đăng ký trong ứng dụng.
- **“`@SpringBootApplication` chỉ là component scan.”** Sai. Nó còn kích hoạt auto-configuration và biểu diễn cấu hình chính của ứng dụng.
- **“Mọi `@Bean` đều override tự cấu hình.”** Sai. Chỉ các điều kiện liên quan đến bean cụ thể mới có thể back off; khai báo trùng hoặc sai loại còn có thể gây lỗi khởi động.
- **“Spring Boot sở hữu response vì Boot chạy web server.”** Sai. Boot/Framework thực thi pipeline; hợp đồng route và logic xử lý thuộc ứng dụng.
- **“Muốn chỉnh MVC phải thêm `@EnableWebMvc`.”** Sai trong đa số dự án Boot. Ưu tiên `WebMvcConfigurer` và extension point được hỗ trợ.
- **“Đổi property là tự cấu hình lại nóng ở mọi request.”** Không mặc định. Nhiều quyết định bean/server được áp dụng lúc khởi tạo context; thường cần khởi động lại để áp dụng thay đổi.
- **“Condition report có match thì ứng dụng đã đúng.”** Sai. Nó xác nhận điều kiện cấu hình, không xác nhận hành vi nghiệp vụ, bảo mật hay kết quả API.

## 8. Câu hỏi tự kiểm tra

**Tình huống A:** Có dependency MVC và controller `@GetMapping("/orders")` nhưng chưa có service. Ai chịu trách nhiệm định nghĩa dữ liệu của `/orders`?

**Đáp án:** Ứng dụng. Boot có thể cung cấp web server và cơ chế mapping, nhưng controller/service phải xác định dữ liệu/HTTP contract; thiếu dependency nghiệp vụ có thể làm context khởi động thất bại.

**Tình huống B:** Bạn chỉ muốn thêm header vào các response API. Nên thêm `@EnableWebMvc` hay `WebMvcConfigurer`?

**Đáp án:** Dùng extension point phù hợp như `WebMvcConfigurer` với `HandlerInterceptor` nếu tác vụ gắn với MVC handler; hoặc Servlet filter nếu phải áp dụng ở tầng Servlet. Không cần chiếm toàn bộ MVC configuration.

**Tình huống C:** Một bean mặc định không xuất hiện sau khi bạn thêm custom `@Bean`. Kết luận nhanh nhất có hợp lệ là “Boot đã tắt”?

**Đáp án:** Không. Xem chính xác loại bean, điều kiện `@ConditionalOnMissingBean` liên quan và condition report. Một nhánh auto-configuration có thể back off trong khi các nhánh khác vẫn hoạt động.

**Tình huống D:** Đổi `server.port` từ 8090 sang 8091. Điều gì thuộc Boot, điều gì thuộc ứng dụng?

**Đáp án:** Ứng dụng sở hữu giá trị cấu hình và quyết định triển khai; Boot áp dụng giá trị đó lên web server đã cấu hình. Route và business logic có thể giữ nguyên.

## Tài liệu chính thức tham khảo

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Servlet Web Applications / Spring MVC Auto-configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Creating Your Own Auto-configuration (giải thích conditions)](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Build Systems và System Requirements](https://docs.spring.io/spring-boot/reference/using/build-systems.html)

**Nguyên tắc cần nhớ:** Spring Boot chọn và lắp hạ tầng mặc định theo điều kiện; Spring Framework thực thi pipeline; ứng dụng sở hữu API, quy tắc nghiệp vụ và các lựa chọn cấu hình/chính sách mà mình công bố.