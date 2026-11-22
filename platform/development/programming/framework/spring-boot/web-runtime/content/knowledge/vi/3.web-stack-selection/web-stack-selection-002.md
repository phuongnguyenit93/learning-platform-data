# Cách Spring Boot suy luận loại ứng dụng từ classpath

## Mục tiêu

Spring Boot cần biết ứng dụng đang chạy theo mô hình web nào trước khi tạo ApplicationContext và cấu hình các thành phần web. Việc lựa chọn này ảnh hưởng đến loại ApplicationContext, web server, các auto-configuration được kích hoạt và cách request được xử lý.

Sau bài học, bạn có thể:

- Phân biệt ba giá trị của WebApplicationType: SERVLET, REACTIVE và NONE.
- Giải thích Spring Boot dựa vào những class nào trên runtime classpath để suy luận loại ứng dụng.
- Hiểu vì sao thêm một starter có thể làm thay đổi loại ApplicationContext.
- Chủ động cấu hình loại ứng dụng khi cần.
- Kiểm tra dependency tree để tìm nguyên nhân ứng dụng chọn sai web stack.

## 1. WebApplicationType là gì?

**WebApplicationType** là enum của Spring Boot mô tả mô hình ứng dụng mà SpringApplication sẽ khởi chạy. Enum có ba giá trị:

| Giá trị | Ý nghĩa | ApplicationContext thường dùng |
|---|---|---|
| SERVLET | Ứng dụng web dựa trên Servlet API, thường dùng Spring MVC | AnnotationConfigServletWebServerApplicationContext |
| REACTIVE | Ứng dụng web reactive, thường dùng Spring WebFlux | AnnotationConfigReactiveWebServerApplicationContext |
| NONE | Ứng dụng không khởi chạy web server | AnnotationConfigApplicationContext |

Đây là lựa chọn ở cấp ứng dụng. Nó quyết định Spring Boot tạo loại context nào và bật nhóm cấu hình web tương ứng.

**SERVLET** phù hợp với ứng dụng Spring MVC truyền thống. Request đi qua Servlet container, Filter chain và DispatcherServlet. Với starter mặc định, embedded Tomcat thường được sử dụng.

**REACTIVE** phù hợp với ứng dụng Spring WebFlux. Framework sử dụng mô hình Reactive Streams với các kiểu như Mono và Flux; runtime mặc định phổ biến là Reactor Netty khi dùng starter WebFlux.

**NONE** phù hợp với ứng dụng command-line, batch hoặc tác vụ nền không cần HTTP server. Spring vẫn tạo ApplicationContext để quản lý bean và dependency injection, nhưng không tạo web server.

Lưu ý: WebApplicationType không phải tên của web server. Chọn SERVLET không đồng nghĩa bắt buộc phải dùng Tomcat; loại server cụ thể còn phụ thuộc dependency và cấu hình. Tương tự, REACTIVE mô tả mô hình ứng dụng, còn Reactor Netty là một lựa chọn runtime phổ biến.

## 2. Spring Boot suy luận từ runtime classpath

Khi tạo SpringApplication, Spring Boot kiểm tra sự hiện diện của một số class chỉ thị trên classpath. Classpath ở đây là tập thư viện thực tế có thể được JVM nạp khi chạy ứng dụng, bao gồm dependency trực tiếp và dependency bắc cầu (transitive dependency).

Spring Boot không đọc trực tiếp nội dung file pom.xml hoặc build.gradle tại thời điểm suy luận. Build tool giải quyết dependency trước; sau đó ứng dụng được chạy với runtime classpath đã hình thành.

Trong Spring Boot 3.x, các class chỉ thị quan trọng gồm:

| Class | Vai trò trong việc nhận diện |
|---|---|
| org.springframework.web.reactive.DispatcherHandler | Dấu hiệu chính của Spring WebFlux |
| org.springframework.web.servlet.DispatcherServlet | Dấu hiệu của Spring MVC |
| org.glassfish.jersey.servlet.ServletContainer | Dấu hiệu của Jersey chạy trên Servlet |
| jakarta.servlet.Servlet | Servlet API của Jakarta |
| org.springframework.web.context.ConfigurableWebApplicationContext | Kiểu context web của Spring Servlet |

Cơ chế suy luận có thể diễn đạt theo thứ tự sau:

1. Kiểm tra class **DispatcherHandler** của WebFlux.
2. Nếu DispatcherHandler có mặt, đồng thời DispatcherServlet của Spring MVC không có mặt và Jersey ServletContainer cũng không có mặt, Spring Boot chọn **REACTIVE**.
3. Nếu điều kiện reactive không thỏa mãn, Spring Boot kiểm tra các class chỉ thị Servlet. Trong Spring Boot 3.x, hai class cần có là **jakarta.servlet.Servlet** và **ConfigurableWebApplicationContext**.
4. Nếu thiếu một trong các class chỉ thị Servlet, Spring Boot chọn **NONE**.
5. Nếu các class chỉ thị Servlet đều có mặt, Spring Boot chọn **SERVLET**.

Có thể tóm tắt bằng sơ đồ:

~~~mermaid
flowchart TD
    A[SpringApplication khởi tạo] --> B{DispatcherHandler có trên classpath?}
    B -- Không --> E{Các class chỉ thị Servlet đều có?}
    B -- Có --> C{DispatcherServlet và Jersey ServletContainer đều vắng mặt?}
    C -- Có --> R[REACTIVE]
    C -- Không --> E
    E -- Có --> S[SERVLET]
    E -- Không --> N[NONE]
~~~

Điểm cần nhớ là nhánh reactive được xét trước nhánh Servlet. Nếu ứng dụng có cả Spring MVC và Spring WebFlux, điều kiện chọn REACTIVE không thỏa mãn vì DispatcherServlet hiện diện. Khi các class chỉ thị Servlet cũng có mặt, kết quả là SERVLET.

Jersey là trường hợp đặc biệt trong điều kiện reactive: nếu Jersey ServletContainer có mặt, Spring Boot không chọn REACTIVE chỉ dựa trên DispatcherHandler; sau đó kết quả được xác định bởi các class chỉ thị Servlet.

### Ví dụ các tình huống thường gặp

| Runtime classpath | Kết quả thường gặp | Giải thích |
|---|---|---|
| Có spring-boot-starter-web | SERVLET | Starter đưa Spring MVC, Servlet API và embedded Tomcat vào runtime classpath |
| Có spring-boot-starter-webflux, không có MVC hoặc Jersey Servlet | REACTIVE | DispatcherHandler có mặt, các dấu hiệu loại trừ reactive vắng mặt |
| Có cả starter-web và starter-webflux | SERVLET | DispatcherServlet có mặt nên điều kiện chọn REACTIVE không thỏa mãn |
| Không có dấu hiệu WebFlux và thiếu Servlet indicator | NONE | Không đủ class để chọn mô hình Servlet |
| Ứng dụng console không có web dependency | NONE | Không có runtime web phù hợp |

Bảng mô tả các cấu hình dependency điển hình. Dependency bắc cầu do thư viện khác mang vào cũng có thể làm thay đổi kết quả; vì vậy cần kiểm tra runtime classpath thực tế khi kết quả khác dự kiến.

## 3. Vai trò của các starter

Starter là cách thuận tiện để khai báo một nhóm dependency có liên quan. Các starter web không chỉ thêm annotation để lập trình controller; chúng còn đưa framework và runtime tương ứng vào classpath.

### 3.1. Spring MVC với spring-boot-starter-web

Khai báo Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Starter này thường đưa các thành phần sau vào runtime classpath:

- Spring Web MVC, cung cấp DispatcherServlet và mô hình controller Servlet.
- Servlet API phù hợp với phiên bản Spring Boot.
- Embedded Tomcat theo cấu hình mặc định của starter.
- Các thư viện hỗ trợ chuyển đổi dữ liệu HTTP, thường có Jackson cho JSON.

Vì DispatcherServlet và các class chỉ thị Servlet hiện diện, Spring Boot thường suy luận loại ứng dụng là SERVLET.

### 3.2. Spring WebFlux với spring-boot-starter-webflux

Khai báo Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Starter này đưa Spring WebFlux và runtime reactive mặc định phổ biến là Reactor Netty vào classpath. Khi không có Spring MVC hoặc Jersey ServletContainer, DispatcherHandler là dấu hiệu để Spring Boot chọn REACTIVE.

WebFlux có thể sử dụng một số annotation controller giống Spring MVC, nhưng cách xử lý request và runtime khác nhau. Không nên chỉ nhìn vào việc có @RestController để kết luận ứng dụng đang dùng Servlet hay Reactive.

### 3.3. Khi khai báo cả hai starter

Nếu một dự án khai báo cả spring-boot-starter-web và spring-boot-starter-webflux, dependency graph thường chứa cả DispatcherServlet và DispatcherHandler. Theo thứ tự suy luận, Spring Boot chọn SERVLET khi các class chỉ thị Servlet có mặt.

Điều này thường xảy ra khi một thư viện hoặc module khác kéo spring-webmvc vào như dependency bắc cầu. Nhóm phát triển có thể nghĩ ứng dụng chỉ dùng WebFlux nhưng runtime classpath lại chứa MVC.

Nếu chủ đích là xây dựng ứng dụng reactive, nên rà soát dependency để loại bỏ Spring MVC khi không cần. Việc chỉ ép loại ứng dụng thành REACTIVE trong khi vẫn giữ nhiều dependency MVC có thể làm cấu hình phức tạp và khiến nhóm khó hiểu runtime thực tế.

## 4. Loại ứng dụng ảnh hưởng đến quá trình khởi động ra sao?

Việc suy luận WebApplicationType diễn ra trong giai đoạn chuẩn bị SpringApplication. Kết quả được dùng khi tạo ApplicationContext và áp dụng cấu hình tự động.

Luồng tổng quát:

1. JVM chạy class có hàm main.
2. Ứng dụng tạo đối tượng SpringApplication.
3. Spring Boot suy luận WebApplicationType từ runtime classpath, trừ khi loại ứng dụng đã được cấu hình rõ ràng.
4. SpringApplication chuẩn bị Environment và các cấu hình ban đầu.
5. Boot tạo ApplicationContext phù hợp với loại ứng dụng.
6. Auto-configuration đăng ký các bean tương ứng.
7. Với SERVLET hoặc REACTIVE, web server factory phù hợp tạo embedded server.
8. Context được refresh; server bắt đầu nhận request và ứng dụng hoàn tất khởi động.

Ba loại context thường gặp:

- **SERVLET:** AnnotationConfigServletWebServerApplicationContext, tích hợp ServletWebServerFactory và các thành phần Spring MVC.
- **REACTIVE:** AnnotationConfigReactiveWebServerApplicationContext, tích hợp ReactiveWebServerFactory và các thành phần WebFlux.
- **NONE:** AnnotationConfigApplicationContext, là context Spring thông thường không có embedded web server.

Các cấu hình tự động thường sử dụng điều kiện như @ConditionalOnWebApplication để chỉ đăng ký bean khi loại ứng dụng phù hợp. Vì vậy, thay đổi WebApplicationType có thể khiến một nhóm auto-configuration được bật hoặc tắt.

Cần phân biệt hai quyết định:

- **WebApplicationType:** ứng dụng dùng Servlet, Reactive hay không chạy web.
- **Web server implementation:** server cụ thể được chọn từ các dependency có mặt, ví dụ Tomcat hoặc Jetty ở Servlet stack, Reactor Netty là lựa chọn phổ biến ở Reactive stack.

## 5. Quan sát loại ứng dụng bằng mã Java

Trong một dự án đã có dependency Spring Boot, có thể tạo SpringApplication và xem giá trị được suy luận trước khi gọi run.

Ví dụ:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTypeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(WebTypeApplication.class);

        System.out.println(
                "Detected WebApplicationType: "
                        + application.getWebApplicationType()
        );

        application.run(args);
    }
}
~~~

Giải thích:

- Constructor của SpringApplication xác định loại ứng dụng dựa trên classpath.
- getWebApplicationType() trả về giá trị đã được suy luận hoặc cấu hình trên đối tượng.
- run(args) thực hiện quá trình khởi tạo context và khởi chạy ứng dụng.

Nếu runtime classpath chứa starter-web theo cấu hình thông thường, dòng đầu ra sẽ có dạng:

~~~text
Detected WebApplicationType: SERVLET
~~~

Nếu chỉ có starter-webflux và không có các class loại trừ reactive, kết quả có dạng:

~~~text
Detected WebApplicationType: REACTIVE
~~~

Nếu không có web dependency phù hợp, kết quả thường là:

~~~text
Detected WebApplicationType: NONE
~~~

Đây là các kết quả phụ thuộc dependency thực tế. Không thể khẳng định một giá trị duy nhất nếu chưa biết runtime classpath của dự án.

## 6. Chủ động cấu hình WebApplicationType

Suy luận tự động đáp ứng phần lớn ứng dụng thông thường. Tuy nhiên, có thể cấu hình tường minh khi ứng dụng có classpath đặc biệt hoặc khi cần kiểm soát môi trường chạy.

### 6.1. Dùng SpringApplication.setWebApplicationType

Ví dụ ép ứng dụng chạy theo Servlet stack:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.run(args);
    }
}
~~~

Có thể thay SERVLET bằng REACTIVE hoặc NONE:

~~~java
application.setWebApplicationType(WebApplicationType.REACTIVE);
~~~

~~~java
application.setWebApplicationType(WebApplicationType.NONE);
~~~

Cấu hình qua API hữu ích khi việc khởi tạo SpringApplication được điều khiển bằng mã Java. Loại được đặt tường minh sẽ thay thế kết quả suy luận mặc định cho lần chạy đó.

### 6.2. Dùng application.properties

Có thể cấu hình trong **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=servlet
~~~

Các giá trị hợp lệ:

~~~properties
spring.main.web-application-type=servlet
~~~

~~~properties
spring.main.web-application-type=reactive
~~~

~~~properties
spring.main.web-application-type=none
~~~

Hoặc dùng YAML:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Thuộc tính cấu hình phù hợp khi muốn chọn runtime theo profile hoặc theo môi trường triển khai mà không sửa class main.

Không nên ép REACTIVE chỉ để thử tăng hiệu năng nếu các thư viện nghiệp vụ vẫn blocking hoặc ứng dụng vẫn phụ thuộc Servlet. Hãy chọn mô hình dựa trên kiến trúc và các thư viện thực tế.

## 7. Kiểm tra dependency khi Spring Boot chọn sai loại ứng dụng

Khi ứng dụng khởi chạy bằng server không mong muốn hoặc không tạo web server, hãy kiểm tra dependency graph trước khi sửa code.

### 7.1. Với Maven

Liệt kê dependency liên quan đến web:

~~~bash
mvn dependency:tree
~~~

Có thể lọc các dependency quan trọng:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web,org.springframework.boot:spring-boot-starter-webflux,org.springframework:spring-webmvc,org.springframework:spring-webflux
~~~

Tìm các thư viện đáng chú ý:

- spring-webmvc và DispatcherServlet: dấu hiệu MVC.
- spring-webflux và DispatcherHandler: dấu hiệu WebFlux.
- spring-boot-starter-tomcat: embedded Tomcat.
- reactor-netty-http: runtime Reactor Netty.
- jakarta.servlet-api: Servlet API trong các ứng dụng Spring Boot 3.x.

Nếu spring-webmvc xuất hiện mà không được khai báo trực tiếp, hãy xem dependency nào kéo nó vào.

### 7.2. Với Gradle

Xem toàn bộ runtime dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do một dependency được đưa vào:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

Hoặc kiểm tra WebFlux:

~~~bash
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
~~~

Kết quả dependencyInsight giúp xác định module trực tiếp hoặc bắc cầu đã đưa thư viện vào dự án.

### 7.3. Quan sát lúc khởi động

Một số dấu hiệu trong log:

- Dòng thông báo Tomcat started thường cho thấy ứng dụng đang chạy với Servlet stack và Tomcat.
- Dòng thông báo Netty started thường xuất hiện với ứng dụng WebFlux dùng Reactor Netty.
- Ứng dụng NONE sẽ không có dòng khởi động embedded web server.

Có thể bật báo cáo điều kiện auto-configuration bằng tham số **--debug**:

~~~bash
java -jar target/application.jar --debug
~~~

Báo cáo này cho biết các auto-configuration nào được áp dụng hoặc bị loại trừ. Nó hỗ trợ tìm nguyên nhân bean web được tạo hoặc không được tạo, nhưng vẫn nên kiểm tra dependency tree để hiểu nguồn gốc classpath.

## 8. Những nhầm lẫn và lỗi thường gặp

### Nhầm lẫn 1: Có @RestController thì chắc chắn là Servlet

Không đúng. Spring MVC và Spring WebFlux đều hỗ trợ mô hình annotation controller. Loại ứng dụng được quyết định bởi WebApplicationType và cấu hình tương ứng, không phải chỉ bởi annotation trên controller.

### Nhầm lẫn 2: Chỉ khai báo starter là đủ để biết runtime

Starter có thể kéo nhiều dependency bắc cầu. Một module nội bộ hoặc thư viện bên thứ ba có thể đưa Spring MVC vào classpath dù module chính chỉ khai báo WebFlux.

Cách xử lý: xem runtime dependency tree và xác định dependency gây ra sự hiện diện của DispatcherServlet hoặc DispatcherHandler.

### Nhầm lẫn 3: Có WebFlux thì luôn chọn REACTIVE

Không đúng. Nếu DispatcherServlet có mặt hoặc Jersey ServletContainer có mặt, điều kiện reactive không thỏa mãn. Khi các class chỉ thị Servlet có mặt, kết quả có thể là SERVLET.

### Nhầm lẫn 4: NONE nghĩa là không có Spring ApplicationContext

NONE chỉ có nghĩa ứng dụng không được khởi chạy như một web application. Spring vẫn tạo ApplicationContext thông thường, khởi tạo bean và chạy các thành phần cần thiết.

### Nhầm lẫn 5: Chọn REACTIVE đồng nghĩa mọi lời gọi đều non-blocking

WebApplicationType chỉ xác định mô hình web và nhóm cấu hình. Nếu code gọi JDBC đồng bộ hoặc HTTP client blocking trên event loop, ứng dụng vẫn có thể bị nghẽn. Muốn tận dụng WebFlux cần xem xét toàn bộ chuỗi dependency và cách thực hiện I/O.

### Nhầm lẫn 6: Servlet API có mặt là chắc chắn ứng dụng dùng Tomcat

Servlet API là dấu hiệu của mô hình Servlet, còn server cụ thể do các server factory và dependency quyết định. Dự án có thể dùng embedded server khác nếu dependency và cấu hình tương ứng được thiết lập.

### Lỗi: Ứng dụng dự kiến WebFlux nhưng lại khởi chạy Tomcat

Nguyên nhân thường gặp là Spring MVC được đưa vào runtime classpath, trực tiếp hoặc gián tiếp. Kiểm tra dependency tree, loại bỏ starter MVC không cần thiết và xác nhận lại WebApplicationType sau khi build.

### Lỗi: Ứng dụng không có HTTP endpoint dù đã tạo controller

Có thể ứng dụng đang chạy với NONE, controller không được component scan, hoặc dependency web chưa có trong runtime classpath. Kiểm tra WebApplicationType, vị trí package của class main và dependency tree.

## 9. Checklist lựa chọn web stack

Trước khi chọn hoặc thay đổi web stack, hãy kiểm tra:

- Ứng dụng cần Servlet MVC, Reactive WebFlux hay không cần web server?
- Runtime classpath có đúng starter dự kiến không?
- Có dependency bắc cầu đưa spring-webmvc hoặc spring-webflux vào ngoài dự kiến không?
- WebApplicationType được suy luận hay bị ghi đè bằng API hoặc cấu hình?
- Embedded server factory nào có mặt trên classpath?
- Các thư viện truy cập database và HTTP có hỗ trợ mô hình non-blocking nếu chọn WebFlux không?
- Môi trường test có đang dùng web application type khác môi trường chạy thật không?

## 10. Tổng kết

Spring Boot suy luận WebApplicationType dựa trên sự hiện diện của các class chỉ thị trong runtime classpath. Trong Spring Boot 3.x, DispatcherHandler được dùng để nhận diện trường hợp reactive, đồng thời loại trừ khi Spring MVC DispatcherServlet hoặc Jersey ServletContainer hiện diện. Nếu không chọn reactive, Boot kiểm tra Servlet API và ConfigurableWebApplicationContext để quyết định SERVLET hay NONE.

Kết quả này quyết định loại ApplicationContext và nhóm auto-configuration được áp dụng. Starter web đưa framework và server runtime vào classpath; dependency bắc cầu cũng có thể ảnh hưởng đến kết quả. Khi cần, có thể đặt loại ứng dụng bằng SpringApplication.setWebApplicationType hoặc thuộc tính spring.main.web-application-type.

Khi runtime không như dự kiến, hãy kiểm tra dependency tree và giá trị WebApplicationType trước khi thay đổi controller hoặc cấu hình server.