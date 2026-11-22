# Hành vi khi đồng thời có Spring MVC và WebFlux trên classpath

## 1. Câu trả lời cần nhớ

Trong một ứng dụng Spring Boot thông thường, nếu cả spring-boot-starter-web và spring-boot-starter-webflux cùng nằm trong runtime classpath, **Spring Boot ưu tiên Spring MVC và khởi động ứng dụng web kiểu Servlet theo mặc định**. Việc có thư viện WebFlux không tự làm ứng dụng chuyển thành reactive web server, cũng không mặc nhiên chạy hai bộ xử lý HTTP độc lập song song.

Quy tắc này có chủ đích: nhiều ứng dụng Spring MVC thêm WebFlux để sử dụng HTTP client WebClient và Reactor, trong khi vẫn muốn giữ hệ thống controller và Servlet runtime hiện có.

Có thể chọn WebFlux làm server stack một cách tường minh bằng cấu hình spring.main.web-application-type=reactive hoặc bằng SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE), với điều kiện các dependency và cấu hình cho reactive server phù hợp.

Bài này tập trung vào **cơ chế chọn web stack khi cả hai framework có trên classpath**, các thành phần thực sự hoạt động lúc chạy, cách dùng chung thư viện và cách kiểm tra kết quả. Ví dụ áp dụng cho Spring Boot 3.3.x và Java 17+.

## 2. Hiểu đúng các khái niệm

### 2.1 Classpath không đồng nghĩa với runtime đang hoạt động

Runtime classpath là tập các thư viện mà JVM có thể nạp khi ứng dụng chạy. Dependency trực tiếp và dependency bắc cầu đều có thể đóng góp class vào classpath.

Khi thêm spring-boot-starter-web, dự án thường nhận Spring MVC, Servlet API và embedded Tomcat. Khi thêm spring-boot-starter-webflux, dự án thường nhận Spring WebFlux, Reactor và Reactor Netty.

Việc một class như DispatcherServlet hoặc DispatcherHandler tồn tại trong thư viện chỉ chứng minh class đó **có sẵn**. Nó không chứng minh Spring Boot đã tạo web application context tương ứng, đã đăng ký bộ xử lý request hay đã chọn HTTP server của framework đó.

Phân biệt ba câu hỏi:

1. **Classpath có gì?** Những thư viện nào có thể sử dụng?
2. **Spring Boot chọn loại ứng dụng nào?** SERVLET, REACTIVE hay NONE?
3. **Runtime thực sự khởi tạo gì?** Context, auto-configuration, web server, dispatcher, security chain và endpoint nào đang phục vụ request?

Kết luận đúng phải dựa trên câu hỏi thứ hai và thứ ba. Không thể chỉ nhìn tên starter hay sự xuất hiện của Mono, Flux, Netty hoặc WebClient rồi kết luận server đang chạy WebFlux.

### 2.2 Hai web stack khác nhau ở đâu?

| Khía cạnh | Spring MVC trên Servlet stack | Spring WebFlux trên reactive stack |
| --- | --- | --- |
| Bộ điều phối HTTP | DispatcherServlet | DispatcherHandler |
| Nền tảng xử lý | Servlet API | Reactive Streams và HTTP abstraction không phụ thuộc Servlet API |
| Filter web thường dùng | jakarta.servlet.Filter; có thể có Spring Security FilterChainProxy | org.springframework.web.server.WebFilter; có thể có Spring Security WebFilterChainProxy |
| Xử lý request mapping | MVC HandlerMapping và HandlerAdapter | Reactive HandlerMapping và HandlerAdapter |
| Chuyển đổi body | HttpMessageConverter | HttpMessageReader và HttpMessageWriter |
| Server mặc định của starter thông thường | Tomcat với spring-boot-starter-web | Reactor Netty với spring-boot-starter-webflux |
| Kiểu return phổ biến | DTO, ResponseEntity; hỗ trợ cả async/reactive return | Mono, Flux và các kiểu được reactive adapter hỗ trợ |

Spring MVC có hỗ trợ asynchronous request và reactive return type ở một số tình huống. Vì vậy controller MVC trả Mono không biến DispatcherServlet thành DispatcherHandler.

## 3. Bảng hành vi khi kết hợp dependency

Bảng sau giả định ứng dụng Spring Boot thông thường, starter mặc định, không có tùy biến thủ công đặc biệt và không ép web application type trừ khi ghi rõ:

| Runtime classpath / cấu hình | WebApplicationType | Web stack được Boot cấu hình |
| --- | --- | --- |
| Có spring-boot-starter-web | SERVLET | Spring MVC |
| Có spring-boot-starter-webflux, không có MVC | REACTIVE | Spring WebFlux |
| Có cả hai starter | SERVLET | Spring MVC |
| Có cả hai, ép spring.main.web-application-type=servlet | SERVLET | Spring MVC |
| Có cả hai, ép spring.main.web-application-type=reactive | REACTIVE | Spring WebFlux |
| Ép spring.main.web-application-type=none | NONE | Không tự mở web server bởi Boot |

Đây là hành vi **mặc định**, không phải cam kết rằng mọi tổ hợp thư viện hoặc cấu hình tự viết đều khởi động thành công. Ví dụ: ép REACTIVE nhưng loại mất các dependency cần cho reactive HTTP server có thể làm ứng dụng không khởi động được.

### Khi chỉ có WebFlux thì sao?

Nếu spring-webflux cùng các thành phần reactive server cần thiết hiện diện và các dấu hiệu MVC/Servlet không chi phối, Boot thường suy ra REACTIVE. Điều kiện cụ thể dựa trên các class mà SpringApplication kiểm tra, không chỉ dựa vào việc một dependency có chữ webflux trong tên.

### Khi cả hai starter cùng có mặt?

spring-boot-starter-web mang Spring MVC, còn spring-boot-starter-webflux mang Spring WebFlux và thư viện client/reactive. Với cả hai starter chuẩn, Boot suy ra SERVLET; vì thế MVC chịu trách nhiệm nhận HTTP request. Cách làm này được tài liệu Spring Boot mô tả rõ và là trường hợp cần ghi nhớ nhất của bài.

## 4. Spring Boot đưa ra lựa chọn như thế nào?

Khi SpringApplication được tạo và chạy, Spring Boot xác định WebApplicationType từ classpath, trừ khi ứng dụng chỉ định loại khác.

Ở mức khái niệm, cơ chế nhận diện của Spring Boot 3.3 diễn ra như sau:

1. Boot tìm dấu hiệu của reactive HTTP framework, chẳng hạn DispatcherHandler.
2. Nếu chỉ thấy reactive framework mà không có các dấu hiệu MVC hoặc Servlet framework cạnh tranh được kiểm tra, Boot có thể suy ra REACTIVE.
3. Nếu không chọn reactive, Boot kiểm tra các class cần có cho Servlet web application.
4. Khi có đầy đủ dấu hiệu Servlet, Boot suy ra SERVLET; nếu không đủ để tạo web runtime, kiểu ứng dụng có thể là NONE.
5. Loại ứng dụng được chọn chi phối việc tạo ApplicationContext và điều kiện auto-configuration.

Hãy hiểu đây là **mô tả quy tắc**, không phải bản sao từng dòng mã nguồn Spring Boot. Kết quả còn chịu ảnh hưởng của cấu hình explícit và cách đóng gói classpath.

Sau khi loại ứng dụng được xác định, Boot chọn context phù hợp:

- SERVLET: sử dụng một Servlet web application context, thường là AnnotationConfigServletWebServerApplicationContext.
- REACTIVE: sử dụng một reactive web application context, thường là AnnotationConfigReactiveWebServerApplicationContext.
- NONE: tạo non-web application context, không tự cung cấp HTTP endpoint.

Tên context cụ thể có thể khác nếu ứng dụng tùy biến cách tạo context. Điều cần kiểm tra là **loại context và dispatcher thực tế**, không chỉ tên class triển khai.

## 5. Auto-configuration nào sẽ thực sự có hiệu lực?

Spring Boot sử dụng các điều kiện như @ConditionalOnClass, @ConditionalOnWebApplication và @ConditionalOnMissingBean để quyết định có kích hoạt từng nhóm auto-configuration hay không.

Với **SERVLET**:

- ServletWebServerFactoryAutoConfiguration và các thành phần Servlet web được xét theo điều kiện tương ứng.
- DispatcherServletAutoConfiguration và WebMvcAutoConfiguration cấu hình pipeline Spring MVC trong trường hợp phù hợp.
- Endpoint dùng các thành phần MVC; Servlet Filter có thể bao quanh DispatcherServlet.
- Các auto-configuration dành riêng cho một reactive web application không trở thành HTTP pipeline chỉ vì thư viện WebFlux có mặt.

Với **REACTIVE**:

- ReactiveWebServerFactoryAutoConfiguration và WebFluxAutoConfiguration được xét theo điều kiện tương ứng.
- DispatcherHandler và các thành phần WebFlux đảm nhiệm HTTP request.
- WebFilter được áp dụng trong reactive pipeline.
- Các phần MVC chỉ dành cho Servlet web application không tự trở thành bộ điều phối server.

Mỗi auto-configuration còn có những điều kiện khác. Chẳng hạn, khai báo bean đặc biệt hoặc cấu hình thủ công có thể khiến một auto-configuration nhường quyền. Vì vậy khi debug nên xem Condition Evaluation Report chứ không suy diễn rằng tất cả bean của một nhóm luôn được tạo.

## 6. Điều gì xảy ra ở runtime nếu có cả MVC và WebFlux?

Giả sử dự án khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Khi không có cấu hình ép reactive:

1. Boot chọn SERVLET.
2. Embedded Servlet web server, thông thường Tomcat, tiếp nhận kết nối.
3. Request đi qua Servlet Filter chain tới DispatcherServlet.
4. Spring MVC tìm controller, bind tham số và xử lý response.
5. Thư viện Reactor và WebFlux vẫn nằm trong classpath để code ứng dụng có thể dùng các API thích hợp, đặc biệt WebClient.

Luồng nhận request có thể minh họa như sau:

~~~mermaid
flowchart TD
    A["HTTP client"] --> B["Tomcat / Servlet connector"]
    B --> C["Servlet Filter chain"]
    C --> D["DispatcherServlet (Spring MVC)"]
    D --> E["MVC HandlerMapping / HandlerAdapter"]
    E --> F["Controller / Service"]
    F --> G["HTTP response"]
    H["WebClient / Mono / Flux trong classpath"] -. "Có thể được ứng dụng sử dụng" .-> F
~~~

**Không có quy tắc** tự động chia một số route sang MVC và một số route khác sang WebFlux chỉ vì hai dependency cùng có mặt. Nếu muốn hai ứng dụng HTTP độc lập sử dụng hai stack khác nhau, cần thiết kế, cấu hình và triển khai chúng một cách tường minh; đó là bài toán kiến trúc riêng.

### Có Reactor Netty trong classpath thì sao?

starter-webflux thường kéo Reactor Netty theo cả phần HTTP client và HTTP server. Reactor Netty xuất hiện trong dependency tree không đồng nghĩa server đang lắng nghe cổng ứng dụng là Netty. Trong tổ hợp hai starter mặc định, HTTP server phục vụ MVC thường vẫn là Tomcat. Khi ép reactive, việc chọn reactive server phụ thuộc các dependency server thực tế và cấu hình; không nên dựa duy nhất vào tên một dependency.

## 7. Có thể dùng WebClient trong Spring MVC

Có. Đây là trường hợp phổ biến và là một lý do Boot ưu tiên MVC khi cả hai starter xuất hiện.

Spring Boot có thể cung cấp WebClient.Builder đã được cấu hình khi WebClient có trên classpath. Service MVC có thể inject builder để tạo HTTP client gọi ra bên ngoài.

Ví dụ sử dụng WebClient trong một service, với URI đầu vào là địa chỉ gọi thực tế do ứng dụng quyết định:

~~~java
package com.example.dualstack;

import java.net.URI;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class RemoteTextClient {

    private final WebClient client;

    public RemoteTextClient(WebClient.Builder builder) {
        this.client = builder.build();
    }

    public Mono<String> fetch(URI uri) {
        return client.get()
                .uri(uri)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Đây là class có thể biên dịch trong dự án Spring Boot có dependency đã nêu; nó không tự phát sinh HTTP request khi khởi động. Chỉ khi code gọi fetch với URI hợp lệ, WebClient mới thực hiện lời gọi theo quá trình subscription của reactive pipeline.

Đừng nhầm:

- **WebClient** là HTTP client dùng để gọi một dịch vụ khác.
- **WebFlux web server stack** là framework xử lý request đến ứng dụng.
- Sử dụng WebClient không quyết định server có dùng DispatcherHandler hay không.

Nếu gọi .block() ngay trong request thread của MVC, code sẽ chờ kết quả và có thể giữ Servlet thread trong lúc đợi I/O. Điều này có thể cần thiết ở một ranh giới đồng bộ nhưng làm mất lợi ích non-blocking ở đoạn chờ đó. Nếu controller MVC trả một Mono thay vì gọi .block(), Spring MVC có thể thích nghi với reactive return value qua Servlet async support; nó vẫn là Spring MVC.

## 8. Mono hoặc Flux trong controller không chứng minh dùng WebFlux

Cả Spring MVC và Spring WebFlux có thể xử lý một số kiểu trả về reactive. Ví dụ:

~~~java
package com.example.dualstack;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveValueController {

    @GetMapping("/message")
    public Mono<String> message() {
        return Mono.just("Xin chào");
    }
}
~~~

Trong ứng dụng Boot chọn SERVLET, endpoint này vẫn được Spring MVC mapping và phục vụ thông qua DispatcherServlet. Spring MVC chuyển Mono một giá trị sang cơ chế xử lý bất đồng bộ thích hợp; việc ghi HTTP response cuối cùng vẫn dựa vào Servlet stack.

Trong ứng dụng Boot chọn REACTIVE, cùng kiểu return có thể được xử lý bởi WebFlux pipeline. Vì @RestController, @GetMapping và các annotation HTTP được cả hai framework hỗ trợ, chỉ nhìn vào annotation cũng không đủ để xác định stack.

Đối với Flux và streaming, cần xét Content-Type, hỗ trợ streaming, backpressure và cách ghi body của từng stack. MVC có thể tích hợp với reactive return values nhưng không vì thế mà có cùng mô hình non-blocking I/O của WebFlux.

## 9. Cách ép WebFlux làm server stack

### 9.1 Cấu hình qua application.properties

~~~properties
spring.main.web-application-type=reactive
~~~

Giá trị cấu hình hợp lệ cho thuộc tính này là servlet, reactive hoặc none. Dùng reactive khi thực sự muốn Boot tạo reactive application context, thay vì chỉ dùng WebClient.

Có thể truyền trực tiếp khi khởi động:

~~~bash
gradle bootRun --args='--spring.main.web-application-type=reactive'
~~~

Nếu project có Gradle wrapper, có thể thay gradle bằng ./gradlew trên Linux/macOS hoặc gradlew.bat trên Windows.

### 9.2 Chỉ định bằng Java

~~~java
package com.example.dualstack;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DualStackApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DualStackApplication.class);
        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
~~~

Đây là **phương án thay thế** cho việc cấu hình loại web application; trong ví dụ chạy hoàn chỉnh ở mục tiếp theo sẽ giữ main mặc định để quan sát cả hai tình huống bằng tham số khởi động.

Ép REACTIVE thay đổi loại application context và nhóm auto-configuration đủ điều kiện hoạt động. Nó không tự sửa mã dựa trên Servlet API, không tự chuyển mọi Filter thành WebFilter, không đảm bảo các thư viện blocking trở nên non-blocking và không bảo đảm ứng dụng đã có cấu hình bảo mật đúng cho reactive stack.

Nếu một dependency servlet vẫn có trên classpath, class đó vẫn có thể được JVM nạp; điều quan trọng là Boot đã chọn reactive web application runtime.

## 10. Ví dụ chạy được: cùng classpath, hai chế độ khởi động

Ví dụ tối giản sau cho phép thấy trực tiếp Boot chọn loại context nào. Cần Java 17+ và Gradle phù hợp với Spring Boot 3.3.x.

Cấu trúc project:

~~~text
dual-stack-classpath/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/dualstack/DualStackApplication.java
~~~

File settings.gradle:

~~~groovy
rootProject.name = 'dual-stack-classpath'
~~~

File build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

File src/main/java/com/example/dualstack/DualStackApplication.java:

~~~java
package com.example.dualstack;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DualStackApplication {

    public static void main(String[] args) {
        SpringApplication.run(DualStackApplication.class, args);
    }
}

@RestController
class RuntimeEndpoint {

    private final ApplicationContext context;

    RuntimeEndpoint(ApplicationContext context) {
        this.context = context;
    }

    @GetMapping(value = "/runtime", produces = MediaType.TEXT_PLAIN_VALUE)
    public String runtime() {
        if (context instanceof ServletWebServerApplicationContext) {
            return "SERVLET";
        }
        if (context instanceof ReactiveWebServerApplicationContext) {
            return "REACTIVE";
        }
        return "NONE";
    }
}
~~~

Tất cả import, package và class cần thiết cho endpoint đều có trong file trên. RuntimeEndpoint là class package-private được Spring component scan phát hiện vì cùng package với DualStackApplication.

### 10.1 Chạy mặc định

~~~bash
gradle bootRun
~~~

Ở terminal khác:

~~~bash
curl -s http://localhost:8080/runtime
~~~

Body dự kiến:

~~~text
SERVLET
~~~

Lý do: cả hai starter trên classpath, Spring MVC được ưu tiên. Thông tin trả về xuất phát từ loại ApplicationContext chứ không đoán theo tên thread hoặc dependency.

### 10.2 Chạy với reactive mode

Dừng tiến trình cũ đang giữ cổng 8080, sau đó khởi động lại:

~~~bash
gradle bootRun --args='--spring.main.web-application-type=reactive'
~~~

Gọi lại:

~~~bash
curl -s http://localhost:8080/runtime
~~~

Body dự kiến:

~~~text
REACTIVE
~~~

Lúc này Boot tạo reactive web application context và xử lý endpoint annotation trên WebFlux pipeline. Để kiểm tra trong hệ thống thực, xác nhận quá trình start hoàn tất và nhìn thêm thông tin server đang lắng nghe; các dependency hoặc bean tùy biến có thể làm việc ép reactive thất bại trong dự án khác.

Kết quả trên là hành vi dự kiến của dự án ví dụ với cấu hình đã nêu; không phải log của một lần chạy thử được thực hiện trong bài viết này.

## 11. Hệ quả với RouterFunction, Filter, Security và cấu hình

### 11.1 Hai loại functional route mang tên gần giống nhau

Spring MVC có API functional routing thuộc package org.springframework.web.servlet.function, còn WebFlux có API tương ứng thuộc org.springframework.web.reactive.function.server.

Chúng là những kiểu khác nhau. Một RouterFunction dành riêng cho reactive package không tự được MVC nhận làm Servlet route khi Boot chọn SERVLET. Điều này có thể khiến developer thấy bean đã khai báo nhưng gọi URL lại nhận 404.

Khi đọc code, hãy kiểm tra **tên package import**, web application type và các HandlerMapping thực sự được tạo.

### 11.2 Filter và security chain

- Ở Servlet/MVC stack, phần xử lý request HTTP dùng Servlet Filter và cơ chế Spring Security dành cho Servlet, chẳng hạn SecurityFilterChain.
- Ở reactive/WebFlux stack, phần xử lý HTTP dùng WebFilter và cơ chế Spring Security reactive, chẳng hạn SecurityWebFilterChain.
- Chỉ vì cả hai class có thể import, không có nghĩa cả hai cùng bảo vệ cùng một HTTP request.

Cấu hình bảo mật cần khớp stack thực sự chạy. Nếu chỉ chuyển thuộc tính web-application-type mà không soát lại security configuration, ứng dụng có thể thiếu bean, lỗi startup hoặc hành vi xác thực/phân quyền khác mong đợi.

### 11.3 Đừng dùng @EnableWebMvc hay @EnableWebFlux để thay cho lựa chọn Boot

Các annotation @EnableWebMvc và @EnableWebFlux cho phép ứng dụng chủ động kiểm soát nhiều phần cấu hình framework tương ứng. Chúng có thể khiến auto-configuration mặc định của Boot nhường quyền.

Chúng **không phải công tắc tiêu chuẩn** để xác định SpringApplication dùng SERVLET hay REACTIVE. Muốn chọn web stack, sử dụng dependency/classpath và SpringApplication web application type; chỉ thêm các annotation Enable khi cần kiểm soát cấu hình framework có chủ đích.

### 11.4 Configuration và thư viện phụ trợ

Một số component có thể hoạt động bất kể stack server, chẳng hạn service nghiệp vụ thuần Java, Repository hoặc HTTP client. Các component phụ thuộc trực tiếp Servlet API, reactive ServerWebExchange, hoặc framework-specific bean sẽ cần đúng runtime tương ứng.

Khi viết auto-configuration dùng chung, có thể kết hợp các điều kiện như @ConditionalOnWebApplication(type = SERVLET) và @ConditionalOnWebApplication(type = REACTIVE) để tạo bean theo loại ứng dụng. Không dùng @ConditionalOnClass đơn độc để suy ra stack, vì cả MVC và WebFlux có thể cùng tồn tại trong classpath.

## 12. Debug khi ứng dụng chạy khác mong đợi

### 12.1 Quy trình xác minh ngắn

1. Xem runtimeClasspath thực tế, bao gồm dependency bắc cầu, để biết starter-web và starter-webflux có mặt hay không.
2. Kiểm tra giá trị spring.main.web-application-type từ cấu hình và tham số khởi động.
3. Kiểm tra ApplicationContext thực tế là ServletWebServerApplicationContext hay ReactiveWebServerApplicationContext.
4. Xem log khởi động để nhận diện embedded server và cổng; nhớ rằng tên thư viện trên classpath không đủ để kết luận server nào đang chạy.
5. Nếu cần, bật Condition Evaluation Report để biết vì sao WebMvcAutoConfiguration hoặc WebFluxAutoConfiguration match hoặc không match.
6. Kiểm tra package import và bean cụ thể: servlet RouterFunction, reactive RouterFunction, Filter/WebFilter, SecurityFilterChain/SecurityWebFilterChain.
7. Gửi một HTTP request và xác minh endpoint hoạt động qua runtime tương ứng.

Lệnh xem dependency bằng Gradle:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Để xem báo cáo điều kiện auto-configuration trong lần chạy debug:

~~~bash
gradle bootRun --args='--debug'
~~~

Chỉ dùng đầu ra của báo cáo để kiểm tra điều kiện thực tế; không đoán bean nào tồn tại dựa trên tên starter.

### 12.2 Những triệu chứng phổ biến

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Thêm starter-webflux nhưng server vẫn log Tomcat | Bình thường nếu đồng thời có starter-web và Boot chọn SERVLET |
| Có WebClient.Builder nhưng controller vẫn đi qua DispatcherServlet | Bình thường: WebClient là HTTP client, không chọn server stack |
| Controller trả Mono nhưng runtime vẫn MVC | Bình thường: MVC hỗ trợ một số reactive return type |
| Reactive functional route không xuất hiện | Có thể ứng dụng đang SERVLET và bean dùng reactive RouterFunction |
| Cấu hình WebFilter không can thiệp vào request MVC | Do WebFilter thuộc pipeline reactive, không phải Servlet Filter |
| Cố ép reactive rồi startup lỗi | Xem reactive server dependencies, bean có điều kiện theo stack, security và cấu hình Servlet-specific |
| Thấy cả Tomcat và Netty trong dependency tree | Kiểm tra context và server thực tế, không suy từ classpath |
| Test muốn kiểm tra WebFlux nhưng luôn nhận MVC | Cần chỉ rõ spring.main.web-application-type=reactive trong test khi có cả hai stack |

## 13. Kiểm thử lựa chọn stack

Trong Spring Boot test, khi cả hai framework cùng có mặt, mặc định vẫn ưu tiên MVC. Vì vậy một bài test cho ứng dụng reactive cần ép loại ứng dụng đúng mục tiêu.

Ví dụ minh họa annotation cho test reactive:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveModeTest {
    // Có thể inject ApplicationContext rồi assert loại context phù hợp.
}
~~~

Đây là đoạn minh họa annotation, cần bổ sung import, dependency spring-boot-starter-test và mã assertion tương ứng để thành test độc lập. Có thể dùng MockMvc cho test MVC và WebTestClient cho test reactive; WebTestClient cũng có khả năng kiểm thử HTTP endpoint của Servlet application trong một số cách cấu hình, nên sự hiện diện của WebTestClient **không tự chứng minh** ứng dụng dùng WebFlux.

Ưu tiên test dựa vào loại context được khởi tạo, mapping thực tế và response mong đợi; đừng viết test chỉ kiểm tra thư viện WebFlux có tồn tại trong classpath.

## 14. Cách lựa chọn trong dự án thực tế

Nếu ứng dụng hiện tại dùng controller Spring MVC, Servlet Filter, Spring Security Servlet hoặc nhiều thư viện blocking, và chỉ cần HTTP client reactive để gọi service khác, có thể giữ MVC làm server stack rồi dùng WebClient ở phần client. Chỉ cần hiểu cách xử lý subscription, timeout, cancellation và việc có hay không gọi .block() tại ranh giới đồng bộ.

Nếu mục tiêu là WebFlux end-to-end với I/O non-blocking, hãy chọn reactive web application một cách có chủ đích, đảm bảo các client, bộ truy cập dữ liệu, security chain và quy tắc xử lý blocking phù hợp. Đổi mỗi starter hoặc một thuộc tính sẽ không tự biến toàn bộ service thành non-blocking.

Khi duy trì nhiều module, nên quy định rõ web stack cho mỗi module, tránh dependency bắc cầu làm tăng độ mơ hồ. Trong Spring Boot, **web application type quyết định cách Boot khởi tạo HTTP server framework**, còn classpath quyết định những thư viện có thể được sử dụng.

## 15. Những hiểu nhầm cần tránh

- “Có hai starter thì Spring Boot mở hai HTTP server”: sai đối với cấu hình mặc định; MVC được ưu tiên.
- “Có Reactor Netty nghĩa là request đi qua WebFlux”: sai; Netty cũng có thể chỉ là runtime cho HTTP client.
- “Dùng WebClient nghĩa là đã viết ứng dụng reactive”: sai; WebClient có thể nằm trong một ứng dụng Spring MVC.
- “Return Mono thì controller chắc chắn do WebFlux xử lý”: sai; MVC có cơ chế async/reactive return value.
- “Cả hai framework có mặt thì mọi cấu hình Filter đều áp dụng”: sai; Filter của Servlet và WebFilter của WebFlux thuộc hai pipeline khác nhau.
- “@EnableWebFlux là đủ để đổi cách Boot chọn ApplicationContext”: sai; chọn stack bằng web application type hoặc cấu hình classpath nhất quán.
- “Ép REACTIVE là toàn bộ xử lý đã non-blocking”: sai; thư viện và code blocking vẫn có thể làm nghẽn tài nguyên của reactive runtime.
- “Kiểm tra dependency tree là đủ để biết runtime”: sai; cần đối chiếu context, điều kiện auto-configuration và endpoint thực tế.

## 16. Tóm tắt

Với Spring Boot 3.3, cả spring-boot-starter-web và spring-boot-starter-webflux cùng xuất hiện trên classpath thì **Spring MVC/Servlet được chọn mặc định**. WebFlux vẫn có thể cung cấp WebClient và reactive API cho phần client hoặc các xử lý thích hợp, nhưng không tự trở thành HTTP server pipeline.

Muốn chạy WebFlux server, chọn REACTIVE tường minh và kiểm tra lại các dependency, cấu hình, security cùng mức độ blocking. Cách xác nhận đáng tin nhất là quan sát WebApplicationType, ApplicationContext, auto-configuration và request đang được phục vụ, thay vì suy từ tên thư viện.

## 17. Tài liệu tham khảo

- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Testing Spring Boot Applications, Detecting Web Application Type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
