# ReactorResourceFactory và vòng đời tài nguyên HTTP dùng chung

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot chạy Spring WebFlux thường vừa **nhận HTTP request** bằng Reactor Netty, vừa **gọi HTTP service khác** qua WebClient. Dưới các đối tượng HTTP tiện dụng đó còn có tài nguyên thật của hệ điều hành và Reactor Netty: event-loop threads, connection pools, sockets, bộ nhớ buffer và những đối tượng cần được dọn dẹp khi ứng dụng dừng.

Nếu mỗi lần gọi API lại tạo một tập event loop hoặc connection pool mới, ứng dụng có thể tăng số thread, tăng socket, mất hiệu quả HTTP keep-alive và khó kiểm soát shutdown. Nếu ngược lại, mọi thành phần dùng tài nguyên global nhưng không hiểu phạm vi sở hữu của chúng, việc đóng một ApplicationContext có thể gây ảnh hưởng không mong muốn đến HTTP client hoặc server khác trong cùng JVM.

**ReactorResourceFactory** là điểm tích hợp của Spring Framework dành cho việc khởi tạo, truy cập và quản lý vòng đời các tài nguyên Reactor Netty. Nó giúp các thành phần dùng HTTP có thể **chia sẻ đúng tài nguyên** và **giải phóng tài nguyên đúng thời điểm**, thay vì tự tạo, tự dispose hoặc để các pool sống vô thời hạn.

Bài này tập trung vào ba câu hỏi:

1. Tài nguyên nào được chia sẻ, và “chia sẻ” có nghĩa gì?
2. Sự khác biệt giữa chế độ tài nguyên global mặc định và tài nguyên do ApplicationContext sở hữu?
3. Spring Boot và WebClient nên sử dụng ReactorResourceFactory như thế nào để startup, vận hành và shutdown an toàn?

Đây là kiến thức về **Spring WebFlux và Reactor Netty**, không phải cấu hình DispatcherServlet/Tomcat Servlet. Một WebClient vẫn có thể được dùng trong ứng dụng Spring MVC, nhưng mô hình web server và tài nguyên server khi đó phải được phân biệt.

## 2. Phân biệt những đối tượng có tên gần giống nhau

| Đối tượng | Vai trò | Phạm vi và điều cần nhớ |
|---|---|---|
| ReactorResourceFactory | Bean Spring quản lý tài nguyên Reactor Netty | Cung cấp LoopResources và ConnectionProvider; có vòng đời theo Spring |
| LoopResources | Quản lý event-loop resources của Reactor Netty | Cấp các event-loop threads để xử lý I/O bất đồng bộ |
| ConnectionProvider | Quản lý chiến lược cấp/reuse kết nối HTTP client | Pooling, giới hạn kết nối, chờ lấy connection, tái sử dụng socket |
| HttpResources | Bộ tài nguyên HTTP global của Reactor Netty | Có thể được dùng chung trong phạm vi **một JVM**, không phải toàn cluster |
| HttpClient | Cấu hình một Reactor Netty HTTP client | Dùng event loops và connection provider; không đồng nghĩa một TCP connection |
| ReactorClientHttpConnector | Adapter của Spring WebClient sang Reactor Netty HttpClient | Có thể nhận ReactorResourceFactory và mapper HttpClient |
| WebClient | API HTTP client reactive cấp cao của Spring | Có thể được xây từ WebClient.Builder; request tạo Publisher |
| HttpHandler / DispatcherHandler | Xử lý HTTP request trong Spring WebFlux | Không sở hữu connection pool HTTP client chỉ vì chúng là handler |
| NettyReactiveWebServerFactory | Factory tạo embedded Reactor Netty web server trong Boot | Chịu trách nhiệm cấu hình server, có thể tích hợp Reactor resources |
| ApplicationContext | Container Spring quản lý bean và lifecycle | Đóng context là mốc quan trọng để giải phóng tài nguyên Spring-managed |

**Một connection pool không phải một event loop.** Pool quản lý việc sử dụng lại kết nối HTTP client, còn event loop là cơ chế thực thi các thao tác I/O không chặn thread. Chúng có thể liên quan đến cùng một HttpClient, nhưng giới hạn pool và số event-loop threads có ý nghĩa khác nhau.

**Global không có nghĩa được chia sẻ giữa nhiều pod hoặc nhiều máy.** Reactor Netty HttpResources là tài nguyên global trong tiến trình JVM tương ứng. Mỗi container/JVM vẫn sở hữu các thread và socket riêng.

### 2.1. Event loop khác worker thread cho tác vụ blocking

Reactor Netty thường dùng một tập event-loop threads hữu hạn để phục vụ nhiều kết nối. Mô hình này hiệu quả khi callback I/O không bị block lâu. Nếu controller WebFlux gọi JDBC, SDK blocking hoặc Thread.sleep trực tiếp trên event loop, chia sẻ event loops sẽ trở thành điểm nghẽn: nhiều request khác có thể chậm theo.

LoopResources không tự biến lời gọi blocking thành non-blocking. Nếu buộc phải dùng một dependency blocking, cần cân nhắc scheduler dành cho blocking work như Schedulers.boundedElastic(), giới hạn concurrency và deadline; ưu tiên thư viện reactive khi có thể.

### 2.2. Connection pool không phải pool đối tượng WebClient

Một WebClient được build một lần có thể xử lý nhiều request. Bên trong WebClient, connector/HttpClient phối hợp với ConnectionProvider để giữ lại và tái sử dụng TCP connections khi điều kiện HTTP, proxy, TLS, server và chính sách pooling cho phép.

Không có lý do tạo một WebClient mới cho mỗi request chỉ để gọi cùng một upstream. Làm vậy không nhất thiết tạo pool riêng nếu client vẫn dùng chung resource factory, nhưng tăng cấu hình đối tượng, khó quản lý chính sách và dễ tạo lỗi khi ai đó đổi cách dựng HttpClient sau này.

## 3. Vì sao tài nguyên HTTP nên được dùng chung?

HTTP client thường phải thực hiện các công việc tương đối tốn chi phí:

- Tra cứu DNS và thiết lập TCP connection.
- Bắt tay TLS khi dùng HTTPS.
- Thiết lập trạng thái HTTP/1.1 keep-alive hoặc kết nối HTTP/2 theo khả năng hai bên.
- Phân bổ buffer, đăng ký channel vào event loop.
- Quản lý timeout, idle connection, connection acquisition và cleanup.

Dùng lại connection hợp lệ giúp giảm chi phí kết nối mới và độ trễ. Chia sẻ event loop giúp tránh tạo thêm một lượng lớn thread khi số WebClient hoặc module tăng. Tuy nhiên chia sẻ cũng đồng nghĩa các thành phần có thể ảnh hưởng lẫn nhau về tài nguyên: một client dùng quá nhiều connection hoặc một callback blocking chiếm event loop có thể làm xấu hiệu năng của client/server khác.

Mục tiêu không phải “mọi thành phần bắt buộc dùng chung mọi thứ”. Mục tiêu là **có chính sách sở hữu và giới hạn tài nguyên rõ ràng**:

- Có thể dùng chung một bộ tài nguyên cho HTTP server và nhiều HTTP client trong cùng ứng dụng.
- Có thể cần một connection provider riêng cho một upstream đặc biệt để cách ly giới hạn pool.
- Có thể dùng tài nguyên theo ApplicationContext thay cho global nếu ứng dụng được start/stop nhiều lần trong một JVM.
- Không được dispose thủ công tài nguyên còn đang được thành phần khác dùng.
- Không cho phép một số lượng client/pool tăng không kiểm soát theo số request.

### 3.1. Phạm vi reuse không phải một TCP socket cho mọi đích

ConnectionProvider có thể quản lý nhiều pool theo remote address và những thuộc tính kết nối liên quan. Một kết nối TCP đến api-a.example không tự trở thành kết nối đến api-b.example. HTTP keep-alive chỉ tái sử dụng connection khi phù hợp với endpoint, protocol và chính sách của client/server.

Khi nói “hai WebClient chia sẻ ConnectionProvider”, hãy hiểu rằng chúng dùng chung **hạ tầng quản lý pool** và các giới hạn liên quan, không phải mọi request đều đi qua cùng một socket bất kể host.

## 4. Hai chiến lược tài nguyên: global và ApplicationContext-managed

### 4.1. Global resources của Reactor Netty

Reactor Netty cung cấp tài nguyên HTTP global thông qua HttpResources. Một số API mặc định của HttpClient/HttpServer có thể sử dụng bộ event loops và connection provider chung này.

Với ReactorResourceFactory, thuộc tính **useGlobalResources** mặc định là true. Khi bật chế độ này, factory truy cập các tài nguyên HTTP global. Đây thường là lựa chọn hợp lý khi JVM có một ứng dụng chính, muốn tái sử dụng event loops và connection pools mặc định của Reactor Netty.

Sơ đồ:

~~~text
JVM Process
  |
  +-- Reactor Netty HttpResources (global trong JVM)
  |     +-- LoopResources / event loops
  |     +-- ConnectionProvider / pooled connections
  |
  +-- Spring ApplicationContext
        +-- ReactorResourceFactory (useGlobalResources=true)
        +-- Reactor Netty HTTP server
        +-- WebClient A -> ReactorClientHttpConnector
        +-- WebClient B -> ReactorClientHttpConnector
~~~

Trong một ứng dụng dùng Spring-managed ReactorResourceFactory, vòng đời factory còn có vai trò đảm bảo global resources được giải phóng phù hợp khi ApplicationContext đóng. Điều này đặc biệt hữu ích nếu ApplicationContext có thể start/stop trong một JVM vẫn còn sống, thay vì đợi cả process thoát.

**Điểm cần cân nhắc:** HttpResources là global trong JVM. Nếu có nhiều ApplicationContext độc lập cùng dùng bộ global resources, việc một context quản lý shutdown của tài nguyên global có thể ảnh hưởng context khác đang hoạt động. Không áp dụng mô hình “global resources và mỗi context tự đóng tùy lúc” cho môi trường nhiều context mà chưa thiết kế ownership thống nhất.

### 4.2. Tài nguyên riêng do Spring quản lý

Khi đặt useGlobalResources=false, ReactorResourceFactory có thể tạo và quản lý **một bộ LoopResources và ConnectionProvider riêng** bằng các supplier được cấu hình. Các tài nguyên này vẫn có thể dùng chung giữa nhiều HTTP clients hoặc server trong ApplicationContext nếu tất cả được nối tới cùng factory.

Sơ đồ:

~~~text
Spring ApplicationContext
  |
  +-- ReactorResourceFactory (useGlobalResources=false)
  |     +-- LoopResources riêng
  |     +-- ConnectionProvider riêng
  |
  +-- HTTP server --------------> LoopResources của factory (nếu được tích hợp)
  |
  +-- WebClient A --------------> Connector dùng cùng factory
  |
  +-- WebClient B --------------> Connector dùng cùng factory
  |
  +-- Context close
        +-- Dừng nhận request và hoàn tất các giai đoạn shutdown
        +-- ReactorResourceFactory giải phóng tài nguyên thuộc sở hữu
~~~

Lợi ích là có ranh giới sở hữu rõ theo Spring context. Điều này phù hợp với ứng dụng có vòng đời động trong một JVM, test integration tạo/dừng context nhiều lần, hoặc cần khác biệt rõ về pool, worker threads hay policy. Đổi lại, bạn phải **nối đúng các client/server vào factory riêng**: nếu code khác gọi Reactor Netty HttpClient.create() mà không có cấu hình tài nguyên tương ứng, nó có thể vẫn sử dụng global resources mặc định.

### 4.3. Bảng lựa chọn

| Yếu tố | useGlobalResources=true | useGlobalResources=false |
|---|---|---|
| Bộ tài nguyên cơ sở | Reactor Netty HttpResources global | LoopResources/ConnectionProvider do factory tạo/quản lý |
| Phạm vi tự nhiên | Cùng JVM | Những thành phần được nối vào factory |
| Dễ bắt đầu | Cao; thường phù hợp mặc định | Cần wiring và policy cụ thể hơn |
| Vòng đời | Có quan hệ với global resources; cần cẩn trọng nhiều context | Đóng theo Spring-managed factory/context |
| Kiểm soát cấu hình pool/event loops | Chủ yếu qua cơ chế global và các customizers được hỗ trợ | Có thể đặt supplier và cấu hình riêng |
| Cô lập với ứng dụng khác cùng JVM | Thấp nếu cùng dùng global | Tốt hơn nếu tất cả thành phần được nối đúng |
| Nguy cơ sai cấu hình | Dispose global khi context khác còn dùng | Dùng lẫn global/dedicated hoặc tạo nhiều pool ngoài ý muốn |

Không có một chế độ tốt nhất cho mọi triển khai. Trong một microservice Spring Boot chạy trong JVM riêng, mặc định global thường đơn giản và hiệu quả. Nếu cần tách vòng đời, hãy dùng factory dedicated và bảo đảm phạm vi resource ownership rõ ràng.

## 5. ReactorResourceFactory cung cấp và quản lý những gì?

Lớp nằm trong package:

~~~java
org.springframework.http.client.reactive.ReactorResourceFactory
~~~

Đây là thành phần tích hợp Spring Framework dành cho Reactor Netty. Các API quan trọng khi lập trình gồm:

| API hoặc khái niệm | Ý nghĩa |
|---|---|
| setUseGlobalResources(boolean) | Chọn dùng HttpResources global hay resource độc lập |
| setConnectionProviderSupplier(...) | Cung cấp cách tạo ConnectionProvider khi không dùng global resources |
| setLoopResourcesSupplier(...) | Cung cấp cách tạo LoopResources khi không dùng global resources |
| getConnectionProvider() | Truy cập ConnectionProvider đã được factory quản lý |
| getLoopResources() | Truy cập LoopResources đã được factory quản lý |
| setShutdownQuietPeriod(Duration) | Cấu hình khoảng quiet period khi tắt các resource theo cơ chế hỗ trợ |
| setShutdownTimeout(Duration) | Giới hạn tổng thời gian chờ shutdown resource theo cơ chế hỗ trợ |
| start(), stop(), isRunning() | Liên quan vòng đời thông qua Spring lifecycle |

Các tên phương thức trên thuộc mô hình Spring Framework sử dụng cùng Spring Boot 3.x. Khi nâng cấp phiên bản, hãy tra đúng Javadoc của dependency đang chạy, vì chi tiết về default, timeouts và class Reactor Netty có thể thay đổi.

**Không nhầm factory với một HttpClient hoặc WebClient.** Factory sở hữu/chia sẻ tài nguyên; HttpClient dùng tài nguyên để cấu hình giao tiếp HTTP; WebClient là API gửi request mà ứng dụng gọi. Tạo một factory không tự thực hiện request HTTP nào.

### 5.1. Vì sao chỉ tạo bean là chưa đủ trong mọi tình huống?

Spring Boot có auto-configuration dành cho Reactor Netty khi môi trường phù hợp. Trong ứng dụng Boot dùng starter-webflux và Reactor Netty server, Boot thường tạo/kết nối ReactorResourceFactory theo cấu hình và điều kiện bean. Nếu ứng dụng khai báo một bean ReactorResourceFactory riêng, cần xác minh server factory và các HTTP client được wiring theo bean đó.

Một thư viện tự viết có thể trực tiếp gọi HttpClient.create(), tạo ConnectionProvider mới hoặc khởi tạo event loops riêng. Những đối tượng đó không tự động dùng factory chỉ vì một bean cùng loại tồn tại trong ApplicationContext.

Do đó ranh giới cần xác minh gồm:

- Spring Boot reactive web server đang dùng Reactor Netty hay server khác.
- ReactorResourceFactory nào là bean được inject thực tế.
- WebClient nào dùng ReactorClientHttpConnector gắn với bean đó.
- HttpClient riêng của SDK/thư viện ngoài dùng global hay pool riêng.
- Có bean factory thứ hai hoặc các customizer tạo resource ngoài ý muốn không.

## 6. HTTP server và WebClient chia sẻ tài nguyên ra sao?

Trong Spring Boot WebFlux dùng Reactor Netty, có hai đường quan trọng:

**Đường server:**

~~~text
Reactor Netty HttpServer
    -> nhận connection trên server.port
    -> dùng LoopResources/event loops để xử lý I/O
    -> Spring HttpHandler / WebHandler chain
    -> DispatcherHandler / HandlerMapping / HandlerAdapter
    -> @RestController hoặc functional endpoint
~~~

**Đường client:**

~~~text
Spring WebClient
    -> ClientHttpConnector (ReactorClientHttpConnector)
    -> Reactor Netty HttpClient
    -> ConnectionProvider cấp/tái dùng connection phù hợp
    -> LoopResources xử lý I/O
    -> response đến WebClient dưới dạng Mono/Flux
~~~

ConnectionProvider chủ yếu liên quan **outbound HTTP client connection pool**. Không được mô tả nó là “pool TCP inbound của server” hoặc dùng giới hạn maxConnections của HTTP client để suy ra số request mà server có thể tiếp nhận.

Khi hai đường dùng cùng LoopResources, callback HTTP server và HTTP client có thể cùng chạy trên một bộ event loops. Điều này phù hợp với non-blocking I/O nhưng đòi hỏi code ứng dụng không chặn event-loop threads.

### 6.1. Dùng WebClient.Builder được Spring Boot cung cấp

Khi cần cấu hình WebClient trong ứng dụng Boot, nên ưu tiên inject WebClient.Builder để giữ các customizations của Boot (codec, observation, HTTP connector tùy điều kiện), thay vì tự tạo toàn bộ bằng WebClient.builder() mỗi lần.

Ví dụ:

~~~java
@Bean
WebClient partnerClient(WebClient.Builder builder) {
    return builder.baseUrl("https://partner.example")
            .build();
}
~~~

Đây là snippet dùng trong class @Configuration hoặc một bean factory method; URL chỉ là minh họa, không phải một endpoint có thể gọi thực. Nếu dùng factory dedicated hoặc cần bảo đảm connector đặc biệt được chọn, hãy truyền ReactorClientHttpConnector nhận đúng factory theo ví dụ bên dưới.

Không tạo WebClient mới trong mỗi request handler để đổi base URL liên tục; với số lượng remote endpoints hữu hạn, thường khai báo client/connector có cấu hình tập trung và tái sử dụng. Nếu cần nhiều base URL động, thiết kế URI và các giới hạn pool theo upstream một cách chủ động.

## 7. Ví dụ Spring Boot 3.x: tạo tài nguyên riêng và dùng chung

Ví dụ này sử dụng Java 17+, Spring Boot 3.x, WebFlux và Reactor Netty mặc định. Mục đích là chứng minh **ReactorResourceFactory được khai báo một lần** rồi dùng lại từ HTTP client. Một endpoint /proxy/{id} gọi /echo/{id} trên chính ứng dụng qua HTTP để dễ kiểm tra mà không cần API bên ngoài.

Cấu trúc file:

~~~text
src/main/java/dev/example/resources/
    ResourceDemoApplication.java
    SharedResourcesConfiguration.java
    DemoController.java
src/main/resources/
    application.yml
~~~

### 7.1. Dependency

Trong một project Gradle đã có Spring Boot plugin và repository được cấu hình (ví dụ tạo từ Spring Initializr), thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Không thêm spring-boot-starter-web vào demo nếu muốn chắc chắn chạy reactive web server. Khi cả MVC và WebFlux có trên classpath, Spring Boot có quy tắc chọn loại web application; thấy WebClient trong project không chứng minh server đang chạy reactive.

### 7.2. Main class

File src/main/java/dev/example/resources/ResourceDemoApplication.java:

~~~java
package dev.example.resources;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDemoApplication.class, args);
    }
}
~~~

### 7.3. Một ReactorResourceFactory chung

File src/main/java/dev/example/resources/SharedResourcesConfiguration.java:

~~~java
package dev.example.resources;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.client.reactive.ReactorResourceFactory;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.resources.LoopResources;

@Configuration(proxyBeanMethods = false)
public class SharedResourcesConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        factory.setUseGlobalResources(false);

        factory.setConnectionProviderSupplier(
                () -> ConnectionProvider.builder("shared-demo-pool")
                        .maxConnections(80)
                        .pendingAcquireTimeout(Duration.ofSeconds(2))
                        .build());

        factory.setLoopResourcesSupplier(
                () -> LoopResources.create("shared-demo-http"));

        return factory;
    }

    @Bean
    WebClient localWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory resources) {

        ReactorClientHttpConnector connector =
                new ReactorClientHttpConnector(
                        resources,
                        httpClient -> httpClient
                                .responseTimeout(Duration.ofSeconds(4)));

        return builder
                .baseUrl("http://127.0.0.1:8080")
                .clientConnector(connector)
                .build();
    }
}
~~~

Giải thích từng quyết định:

1. **useGlobalResources(false)**: tạo bộ tài nguyên riêng do factory quản lý thay vì dùng HttpResources global của JVM.
2. **setConnectionProviderSupplier**: cung cấp ConnectionProvider có tên để nhận diện trong chẩn đoán/metrics, giới hạn connection acquisition và thời gian chờ nhận connection.
3. **setLoopResourcesSupplier**: tạo một bộ event-loop resources với prefix tên riêng cho threads phục vụ I/O.
4. **ReactorClientHttpConnector(resources, mapper)**: khi WebClient dùng connector này, client sử dụng tài nguyên từ factory và mapper cấu hình HttpClient, ví dụ response timeout.
5. **WebClient.Builder được inject**: giữ phần lớn customizations Boot cung cấp nhưng thay connector rõ ràng cho client đang xét.
6. **Spring lifecycle quản lý factory**: không gọi dispose trực tiếp từ controller hoặc từ mỗi lần request.

Các số 80 connections, 2 giây pending-acquire và 4 giây response timeout là thông số demo, **không phải giá trị mặc định hay đề xuất production**. Giá trị phù hợp phụ thuộc remote endpoint, mức tải, latency, các giới hạn kết nối và SLO.

ConnectionProvider.maxConnections thường giới hạn kết nối trong các pool mà provider quản lý theo đích/khóa kết nối tương ứng; không tự suy ra tổng socket của toàn JVM luôn nhỏ hơn 80 khi có nhiều remote endpoints. pendingAcquireTimeout giới hạn thời gian chờ lấy connection khả dụng từ pool; responseTimeout giới hạn việc chờ HTTP response theo ngữ nghĩa của Reactor Netty. Cả hai không thay thế một deadline tổng cho request nghiệp vụ.

**Quan trọng:** Code này chứng minh WebClient dùng factory được inject. Trong Spring Boot với Reactor Netty, server factory cũng có thể được tích hợp với ReactorResourceFactory qua auto-configuration phù hợp; cần kiểm tra stack và phiên bản nếu mục tiêu là chứng minh client và server có cùng LoopResources. Một HttpClient được tạo riêng ngoài Spring vẫn có thể dùng global resources khác.

### 7.4. Controller có một endpoint local và một endpoint proxy

File src/main/java/dev/example/resources/DemoController.java:

~~~java
package dev.example.resources;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record Message(String value) {}

    private final WebClient localWebClient;

    public DemoController(
            @Qualifier("localWebClient") WebClient localWebClient) {
        this.localWebClient = localWebClient;
    }

    @GetMapping("/echo/{id}")
    public Mono<Message> echo(@PathVariable long id) {
        return Mono.just(new Message("echo-" + id));
    }

    @GetMapping("/proxy/{id}")
    public Mono<Message> proxy(@PathVariable long id) {
        return localWebClient.get()
                .uri("/echo/{id}", id)
                .retrieve()
                .bodyToMono(Message.class);
    }
}
~~~

Hai endpoint không dùng JDBC, không tạo thread bằng tay và không gọi block()/subscribe() trong controller. /proxy trả lại Mono<Message> cho WebFlux để HTTP runtime tự subscribe và ghi kết quả. Ví dụ này gọi lại cùng process qua HTTP nhằm minh họa client/server cùng hoạt động; trong dự án thật, upstream thường là một service khác.

### 7.5. application.yml và lệnh chạy

File src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

spring:
  main:
    web-application-type: reactive
~~~

Giữ port cố định 8080 cho demo vì localWebClient đã dùng http://127.0.0.1:8080. Với production hoặc test RANDOM_PORT, không hardcode client gọi lại chính port ứng dụng; cần inject host/port/config từ môi trường hoặc thiết kế test riêng.

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi ứng dụng khởi động xong, thử:

~~~bash
curl -i http://localhost:8080/echo/7
curl -i http://localhost:8080/proxy/7
~~~

Trong điều kiện bình thường, **cả hai** trả HTTP 200 với body JSON:

~~~json
{"value":"echo-7"}
~~~

Headers như Date, Transfer-Encoding và Content-Length có thể khác nhau theo hệ điều hành, Reactor Netty, HTTP version hoặc cấu hình codec. Đừng coi header là output bất biến. Nếu có Spring Security trong project thật, response có thể thay đổi do authentication/authorization.

**Điểm cần học:** /proxy dùng WebClient, WebClient dùng ReactorClientHttpConnector, connector được tạo với cùng ReactorResourceFactory bean. Chúng không tạo ConnectionProvider/LoopResources mới cho mỗi request. Khi ApplicationContext đóng đúng cách, factory chịu trách nhiệm dọn tài nguyên mà nó sở hữu.

## 8. Nếu muốn nhiều WebClient cùng dùng một factory

Giả sử một ứng dụng gọi hai upstream services. Nếu hai WebClient cùng nhận ReactorClientHttpConnector gắn vào cùng ReactorResourceFactory, chúng có thể sử dụng cùng ConnectionProvider và LoopResources; từng đích vẫn có kết nối riêng theo pooling policy.

Một cấu hình minh họa:

~~~java
@Bean
WebClient catalogClient(
        WebClient.Builder builder, ReactorResourceFactory resources) {
    return builder
            .baseUrl("https://catalog.example")
            .clientConnector(new ReactorClientHttpConnector(
                    resources, client -> client))
            .build();
}

@Bean
WebClient billingClient(
        WebClient.Builder builder, ReactorResourceFactory resources) {
    return builder
            .baseUrl("https://billing.example")
            .clientConnector(new ReactorClientHttpConnector(
                    resources, client -> client))
            .build();
}
~~~

Các bean trên chỉ là snippet để thêm trong class @Configuration đã import WebClient, ReactorResourceFactory, ReactorClientHttpConnector và Bean. Hai host là ví dụ, không có ý định khẳng định tồn tại dịch vụ thực.

Không khởi tạo hai ReactorResourceFactory độc lập trong mỗi bean WebClient. Tạo một factory làm bean được Spring quản lý và inject đúng instance là cách rõ ràng hơn. Nếu một upstream cần cô lập connection limits, có thể dùng một ConnectionProvider riêng có ownership rõ ràng, nhưng phải bảo đảm vòng đời dispose và test, không nên tạo tài nguyên vô danh trong mỗi method.

### 8.1. Khi sử dụng WebClient.Builder sau khi đã custom connector

WebClient.Builder có tính chất cấu hình builder. Các lời gọi baseUrl/filters/defaultHeaders/clientConnector có thể thay đổi builder được inject; khi tạo nhiều WebClient, cần chú ý mỗi builder/clone được dùng đúng cách để tránh vô tình áp cấu hình cho client khác.

Spring Boot thông thường inject WebClient.Builder trong scope phù hợp và có cơ chế customizer. Với cấu hình nhiều client phức tạp, nên xây dựng các bean riêng, đặt tên, kiểm thử base URL/connector/timeout/filter của từng bean và tránh giữ builder mutable ở trạng thái shared không kiểm soát.

## 9. Vòng đời tài nguyên: startup, runtime, shutdown

### 9.1. Startup

Một trình tự đơn giản hóa:

~~~text
Spring Boot start
  |
  +-- Tạo ApplicationContext
  |
  +-- Tạo ReactorResourceFactory bean
  |      +-- Chọn global / non-global
  |      +-- Tạo hoặc tham chiếu LoopResources
  |      +-- Tạo hoặc tham chiếu ConnectionProvider
  |
  +-- Reactive web server factory / HTTP connectors được cấu hình
  |
  +-- Khởi động Reactor Netty server
  |
  +-- Hoàn tất ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent / readiness availability
  |
  +-- HTTP clients và server hoạt động theo nhu cầu
~~~

Các giai đoạn chính xác về tạo resource, lazy initialization, callback và binding port phụ thuộc phiên bản Boot/Spring/Reactor Netty và việc dùng supplier. Không coi sơ đồ là thứ tự bytecode bắt buộc của mọi ứng dụng.

**Một TCP port đã mở không chứng minh toàn bộ application đã ready.** Đừng lấy socket LISTEN hoặc chỉ một WebClient health check làm tín hiệu readiness duy nhất; xét state của Spring Boot, warm-up và dependency thiết yếu theo yêu cầu hệ thống.

### 9.2. Runtime

Trong lúc ứng dụng phục vụ request:

- HTTP server nhận connection và dùng event loops.
- WebClient lấy hoặc tạo connection từ provider khi cần gọi upstream.
- Connection được trả về pool khi response/body được xử lý đúng cách và policy cho phép reuse.
- Idle connections có thể bị đóng bởi client/provider, server hoặc network.
- Event-loop threads vẫn tồn tại để phục vụ I/O mới; không tạo/đóng chúng theo từng HTTP call.
- Connection provider có thể giới hạn pending acquisition; khi quá tải, client có thể nhận lỗi timeout hoặc pool acquire failure thay vì cứ tăng sockets.
- Cancellation và xử lý lỗi phải hoàn tất hoặc giải phóng HTTP client resources theo hợp đồng của Reactor Netty; không được bỏ mặc response body đang mở.

Khi dùng WebClient.retrieve().bodyToMono(...), framework quản lý phần giải mã và hoàn tất response theo publisher. Với các API mức thấp trao quyền truy cập response thô, người viết code phải chú ý việc consume/release body để không giữ connection quá lâu.

### 9.3. Graceful shutdown

Một trình tự mong muốn khi pod/ứng dụng dừng:

1. Hệ thống orchestration ngừng chuyển request mới tới instance, nếu được tích hợp readiness/draining.
2. HTTP server ngừng nhận connection mới và xử lý in-flight requests trong giới hạn.
3. Các thành phần thực thi nghiệp vụ dừng gửi thêm outbound requests không cần thiết.
4. Các Spring lifecycle beans được stop theo phase/thứ tự thích hợp.
5. ReactorResourceFactory giải phóng ConnectionProvider và LoopResources mà nó quản lý.
6. JVM kết thúc sau khi cleanup hoàn tất hoặc hết shutdown deadline.

Spring Boot hỗ trợ graceful shutdown cho các embedded servers phù hợp, cấu hình ví dụ:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Các cấu hình này thuộc vòng đời server/application; chúng **không bảo đảm** rằng mọi lời gọi tới dịch vụ ngoài sẽ hoàn thành, mọi socket luôn đóng êm đẹp hoặc không có request timeout. Cần kiểm tra timeout ở client, deadline của ingress/Kubernetes và shutdown logic nghiệp vụ.

Trong một container, SIGTERM thường khởi động quá trình dừng ứng dụng; nếu terminationGracePeriodSeconds quá ngắn, tiến trình có thể bị kết thúc cưỡng bức trước khi resources được dispose đầy đủ.

### 9.4. Quiet period và total shutdown timeout

Một số phiên bản Reactor Netty hỗ trợ quá trình dispose tài nguyên với **quiet period** và **shutdown timeout**. ReactorResourceFactory có các setter tương ứng. Quiet period cho phép resource shutdown theo cơ chế đang được hỗ trợ thay vì lập tức đóng thô mọi công việc; timeout đặt giới hạn cho giai đoạn dừng.

Không đồng nhất quiet period với guarantee “mọi request đã trả 200”. Cần phối hợp server graceful shutdown, request deadlines, cancellation, pool disposal và application shutdown. Khi chỉnh cấu hình, đo thời gian dừng thực tế dưới tải và khi upstream mất kết nối.

### 9.5. Vì sao không nên gọi dispose bằng tay trong controller?

Nếu WebClient A và WebClient B đang dùng chung ConnectionProvider/LoopResources, một controller tự dispose provider sau khi xong request có thể làm client khác lỗi dù application vẫn chạy. Tương tự, một scheduled job gọi dispose HTTP global resources có thể khiến embedded HTTP server mất khả năng xử lý socket.

Nguyên tắc: **nơi nào sở hữu tài nguyên thì nơi đó quyết định kết thúc vòng đời**. Với resources được ReactorResourceFactory tạo dưới quản lý Spring, ApplicationContext/lifecycle của Spring là chủ sở hữu tự nhiên. Không gọi dispose từ request-scoped code.

## 10. Các tình huống cần chọn cách chia sẻ khác nhau

| Tình huống | Hướng xử lý |
|---|---|
| Một Spring Boot microservice chạy một JVM riêng | Thường giữ Reactor Netty global resources mặc định |
| Nhiều WebClient gọi cùng nhóm upstream | Dùng WebClient beans và connector/pool chia sẻ có kiểm soát |
| Ứng dụng được start/stop nhiều lần trong cùng JVM | Cân nhắc ReactorResourceFactory quản lý vòng đời rõ ràng |
| Nhiều ApplicationContext đồng thời trong một JVM | Tránh context shutdown tự dispose bộ global còn đang dùng; thiết kế ownership |
| Cần cách ly upstream chậm/không đáng tin | Cân nhắc connection pool riêng và chính sách timeout/bulkhead |
| Test chạy nhiều ApplicationContext nối tiếp | Bảo đảm context được close, resource threads/sockets được cleanup |
| Thư viện tạo HttpClient riêng | Kiểm tra nó có thực sự dùng factory chung hay không |
| Ứng dụng Spring MVC dùng WebClient | Shared Reactor Netty resources vẫn áp dụng cho outbound client, nhưng server Servlet không biến thành Reactor Netty |
| WebFlux server dùng engine khác Reactor Netty | Không giả định server sử dụng LoopResources của Reactor Netty |
| Triển khai nhiều pod | Mỗi JVM/pod có resources riêng; không “chia sẻ pool” qua network |

Điểm quan trọng là **cách ly không phải mặc định tốt hơn chia sẻ**. Nếu mỗi service client được cấp event loops riêng trong một JVM có vài trăm downstream modules, số thread và memory có thể tăng rất nhiều. Thường nên chia sẻ event loops và điều khiển concurrency bằng connection limits, timeout, bulkheads hoặc upstream-specific policies. Chỉ tách event loops khi có lý do đo lường rõ ràng.

## 11. Sizing: event loops, connections và pending acquire

### 11.1. LoopResources

Event loops thực hiện callback I/O. Không chọn worker count theo công thức “mỗi HTTP request một thread”; một event loop xử lý nhiều channels bằng cơ chế non-blocking.

Thông số cần quan sát:

- CPU usage của HTTP event-loop threads.
- Event-loop delay/latency và thời gian callback.
- Số kết nối active và I/O throughput.
- Tỷ lệ blocking operations trên event loop.
- Tổng số event loops do JVM tạo bởi các thư viện khác nhau.
- Năng lực CPU thực tế của container sau khi tính CPU quota/cgroup.

Nếu tăng event loops nhưng bottleneck là JDBC blocking, downstream timeout hoặc CPU saturation, thay đổi sẽ không giải quyết nguyên nhân. Nếu đặt số event loops quá lớn, chi phí threads/context switching có thể tăng.

### 11.2. ConnectionProvider

ConnectionProvider thường có các cấu hình liên quan:

- maxConnections: số connection pool được phép tạo ở một phạm vi thích hợp.
- pendingAcquireTimeout: thời gian chờ khi pool chưa cấp được connection.
- pendingAcquireMaxCount: giới hạn số yêu cầu đang chờ acquire.
- maxIdleTime: thời gian connection có thể nhàn rỗi trong pool.
- maxLifeTime: tuổi tối đa trước khi connection được đưa ra khỏi vòng reuse.
- eviction/background maintenance: cơ chế dọn connection không còn phù hợp theo cấu hình.

Tên và ngữ nghĩa cụ thể của các method cần được đối chiếu với phiên bản Reactor Netty đang dùng. Một số option như maxIdleTime/maxLifeTime có tác động mạnh đến độ ổn định khi upstream/load balancer cũng có idle timeout.

Một provider có thể quản lý các pool theo remote address/connection configuration. Nếu đặt maxConnections=80, không kết luận toàn JVM chỉ mở tối đa 80 sockets cho mọi upstream, và cũng không đồng nhất 80 connections với 80 request đồng thời trong mọi HTTP protocol.

### 11.3. Đọc hiện tượng pool exhaustion

Nếu lượng request đến nhanh hơn upstream xử lý, pool có thể đầy và requests chờ acquisition. Tăng connection limit đôi khi giúp tăng concurrency, nhưng cũng có thể làm upstream quá tải. Nên kiểm tra:

1. Latency của upstream tăng hay không.
2. Có response body hoặc connection bị giữ không release không.
3. Retry chồng nhiều tầng có khuếch đại số call không.
4. Pending acquire timeout có quá ngắn/dài so với SLO không.
5. DNS/TLS/connect timeout hay response timeout mới là nguyên nhân chính.
6. Pool bị phân mảnh vì nhiều HttpClient/ConnectionProvider riêng không.
7. Đã giới hạn concurrency ở tầng nghiệp vụ khi cần chưa.

Chỉ thay đổi maxConnections sau khi phân biệt rõ vấn đề pool saturation, network I/O hay downstream capacity.

## 12. Timeout nào thuộc Reactor Netty HTTP client?

Một lời gọi HTTP có nhiều giai đoạn:

~~~text
Chờ lấy connection từ pool
     |
     v
DNS / TCP connect / TLS handshake (nếu tạo connection mới)
     |
     v
Gửi HTTP request
     |
     v
Chờ HTTP response và đọc body
     |
     v
Hoàn tất publisher / release connection
~~~

Các timeout thường gặp:

| Loại | Bảo vệ giai đoạn | Ví dụ |
|---|---|---|
| Pending acquire timeout | Chờ pool cấp connection | ConnectionProvider.pendingAcquireTimeout |
| Connect timeout | Mở TCP connection mới | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| TLS handshake timeout | Hoàn tất TLS negotiation | Cấu hình secure/SSL provider phù hợp |
| HTTP response timeout | Chờ response/đọc response theo hành vi Reactor Netty | HttpClient.responseTimeout |
| Tổng deadline nghiệp vụ | Toàn chuỗi request và các retry | Reactive timeout / service policy |
| Server idle timeout | Connection nhàn rỗi phía server | Embedded server / proxy configuration |

Không hiểu nhầm responseTimeout=4s thành bảo đảm “mọi giao dịch hoàn thành trước 4 giây” nếu pipeline còn DNS, pool acquisition, retry hoặc các bước nghiệp vụ khác. Cần phối hợp các timeout theo mô hình request end-to-end.

**WebClient mặc định không tự retry mọi lỗi.** Nếu thêm Retry.backoff ở tầng ứng dụng, phải xét thao tác có idempotent không và giới hạn tổng số attempt. ConnectionProvider không giải quyết vấn đề duplicate charge/order khi retry một POST.

## 13. Kiểm thử việc chia sẻ resources và cleanup

Các phép thử có ý nghĩa:

1. Khởi động ứng dụng WebFlux/Netty với cấu hình resource factory mong muốn.
2. Gọi một endpoint qua WebClient nhiều lần và kiểm tra response.
3. Dùng HTTP keep-alive để quan sát connection reuse khi có thể, không giả định mọi lần đều dùng cùng socket.
4. Tạo nhiều WebClient cùng inject một factory và kiểm tra chúng dùng cùng provider/loop resources theo cấu hình.
5. Tạo tải giới hạn để kiểm tra pendingAcquireTimeout và phản ứng khi pool saturation.
6. Đóng ApplicationContext sau test, quan sát thread/socket/resources được giải phóng.
7. Mở ApplicationContext mới trong cùng JVM và chạy lại request; phát hiện nếu global resources bị dispose không như mong muốn.
8. Khi có nhiều context đồng thời, đóng một context và kiểm tra context còn lại vẫn phục vụ request nếu kiến trúc yêu cầu.
9. Mô phỏng upstream mất kết nối để kiểm tra timeout, cancellation và recovery.
10. Kiểm tra rolling shutdown dưới tải: service rút traffic, xử lý in-flight và dispose theo deadline.

### 13.1. Ví dụ test WebTestClient

Với demo ở mục 7, có thể viết test mức HTTP handler:

~~~java
package dev.example.resources;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = DemoController.class)
class DemoControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void echoEndpointWorks() {
        client.get()
                .uri("/echo/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.value").isEqualTo("echo-7");
    }
}
~~~

**Lưu ý về phạm vi test:** DemoController có dependency WebClient trong constructor; @WebFluxTest chỉ tạo MVC/WebFlux slice, vì thế test trên **cần cung cấp WebClient bean trong test context** (ví dụ qua @TestConfiguration) hoặc mock dependency theo cơ chế test phù hợp. Nếu muốn test nguyên code mà không tạo stub, sử dụng SpringBootTest với HTTP server thật và gọi /echo qua WebTestClient, vì application configuration thực đã có bean localWebClient.

Điều quan trọng là không nhầm test controller với test resource lifecycle. @WebFluxTest có thể kiểm tra routing/JSON, nhưng **không chứng minh Reactor Netty connection pool hoặc event loops đã được tạo/đóng đúng** vì nó không nhất thiết khởi động web server thật.

### 13.2. Integration test với server thật

Với SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT), Boot khởi động server thật. Tuy nhiên demo ở mục 7 đang cố định baseUrl("http://127.0.0.1:8080"), nên nếu muốn kiểm thử /proxy với RANDOM_PORT, phải truyền dynamic port đúng vào client. Một cách đơn giản để quan sát resource behavior ban đầu là chạy demo ở port 8080 với bootRun rồi dùng curl/load test như hướng dẫn, không giả định RANDOM_PORT hoạt động với base URL hardcode.

Trong test integration tự động, có thể inject port thực tế và tạo client trong test với URL tương ứng, hoặc dùng mock HTTP upstream có cổng được cấp động, thay vì cố định 8080. Test còn cần đóng cả context lẫn mock server, rồi xác nhận cleanup.

## 14. Metrics và chẩn đoán trong production

Một số dấu hiệu cần theo dõi:

- Số lượng HTTP client connections active/idle/pending theo remote endpoint và pool.
- Connection acquisition duration, pending queue, acquire timeout.
- Tỷ lệ lỗi TCP connect/TLS/response timeout.
- Event-loop thread count và sự xuất hiện của blocking callbacks.
- CPU, GC, direct memory, file descriptors và socket states của container.
- Số connection mới so với reuse khi keep-alive.
- Thời gian shutdown và số request lỗi trong rolling deployment.

Reactor Netty có thể xuất metrics qua Micrometer khi được bật theo cấu hình tương ứng; Spring Boot Actuator có thể góp phần tích hợp quan sát. Không giả định mọi metric luôn xuất hiện theo cùng một tên: điều đó phụ thuộc phiên bản Reactor Netty, metrics registry, cách bật instrumentation và loại client/server.

Không đưa URL có id ngẫu nhiên hoặc query parameters nhạy cảm vào metric tag không giới hạn; high cardinality khiến hệ thống metrics tốn bộ nhớ và khó truy vấn. Ưu tiên URI template, service name và các label có giá trị hữu hạn.

### 14.1. Khi shutdown vẫn còn thread Reactor Netty

Nếu sau khi context đóng mà JVM vẫn có thread Reactor Netty hoặc socket còn mở:

1. Kiểm tra có HttpClient/HttpServer tạo bằng Reactor Netty global resources nhưng nằm ngoài factory không.
2. Kiểm tra library bên thứ ba có tự tạo LoopResources/ConnectionProvider riêng không.
3. Kiểm tra resource factory bean có thực sự thuộc Spring ApplicationContext đang được close không.
4. Kiểm tra nhiều ApplicationContext đang hoạt động, dùng chung global resources hoặc factory khác nhau.
5. Kiểm tra một Publisher vẫn chạy, không kết thúc hoặc không được cancel đúng cách.
6. Kiểm tra shutdown quiet period/timeout và các scheduler do application tự tạo.
7. Dùng thread dump, metric, socket listing để phân biệt event-loop threads với thread pool của scheduler khác.

Đừng kết luận “ReactorResourceFactory bị leak” chỉ từ một thread name. Cần truy nguồn đối tượng sở hữu và xác định vòng đời thực tế của nó.

### 14.2. Dấu hiệu dùng nhầm global và dedicated

Ví dụ ứng dụng đã đặt setUseGlobalResources(false), nhưng một SDK dùng HttpClient.create() độc lập. Lúc đó SDK có thể tiếp tục sử dụng Reactor Netty HttpResources global trong khi các WebClient do ứng dụng tạo đã dùng factory dedicated. Nếu chỉ nhìn resource bean, bạn có thể tưởng mọi HTTP call đã được quản lý đúng.

Kiểm tra connector thật, HttpClient configuration, số provider/pool trong metrics và lifecycle của thư viện. Khi cần chia sẻ tài nguyên với SDK, tìm cơ chế inject HttpClient/ConnectionProvider/LoopResources của chính thư viện; nếu không có, ghi nhận rằng nó sở hữu tài nguyên độc lập và có policy dọn dẹp riêng.

## 15. Những lỗi phổ biến khi tùy chỉnh ReactorResourceFactory

### Lỗi 1: Tạo ConnectionProvider trong từng request

~~~java
// Không đặt đoạn này trong controller method theo từng request:
ConnectionProvider provider =
        ConnectionProvider.create("one-off");
~~~

Provider là tài nguyên có vòng đời riêng. Tạo rồi bỏ không dispose sẽ làm tăng pool/sockets theo thời gian. Thay bằng một provider chung do factory/Spring quản lý, hoặc một provider riêng có owner rõ ràng nếu cần isolation.

### Lỗi 2: Giả định một bean factory khiến mọi HttpClient tự dùng nó

Chỉ những thành phần được kết nối tới factory mới dùng bộ resource dedicated theo thiết kế. HttpClient.create() ở nơi khác có thể dùng global; một SDK có thể tạo pool mới hoàn toàn. Cần kiểm tra bean wiring và adapter của cả server/client.

### Lỗi 3: Gọi dispose từ request handler

Một request không sở hữu provider/loop resources dùng chung. Dispose ở đó có thể làm hỏng tất cả request khác. Để Spring lifecycle/owner chịu trách nhiệm đóng.

### Lỗi 4: Dùng global resources trong nhiều context mà không quản lý shutdown

Một context dừng có thể làm tài nguyên JVM-global bị dispose trong lúc context khác còn dùng. Với mô hình nhiều context, thiết kế shared owner thống nhất hoặc resource factory riêng theo context; kiểm thử đóng từng context.

### Lỗi 5: Tăng maxConnections vô hạn khi upstream chậm

Pool lớn hơn không khiến upstream nhanh hơn. Nó có thể làm tăng socket, memory và áp lực lên dependency. Cần đo latency, pending acquire, retries, timeouts và concurrency; có thể dùng bulkhead hoặc giới hạn request upstream.

### Lỗi 6: Tạo một bộ event loop mới cho mỗi WebClient

Đây thường là dư thừa và có thể tăng thread count đáng kể. Chia sẻ LoopResources là mặc định hợp lý nếu I/O non-blocking; chỉ cô lập event loops khi có lý do và đo lường.

### Lỗi 7: Chạy blocking code trên event loop

Ví dụ gọi JDBC hoặc Thread.sleep trực tiếp trong flatMap/map có thể block Reactor Netty threads. Offload blocking work có kiểm soát hoặc chuyển sang thư viện reactive; không hy vọng resource factory tự giải quyết.

### Lỗi 8: Hiểu nhầm pool acquire timeout với response timeout

PendingAcquireTimeout chỉ bảo vệ lúc chờ pool cấp connection; responseTimeout bảo vệ giai đoạn HTTP response theo Reactor Netty; cần deadline tổng nếu nghiệp vụ yêu cầu giới hạn end-to-end.

### Lỗi 9: Xem application shutdown là close socket tức thì

Có in-flight requests, quiet period, proxy connections và shutdown phase. Phải đo real behavior. Không dùng sleep cố định hoặc dispose gấp để “chắc chắn giải phóng” khi chưa hiểu hệ quả của request đang chạy.

### Lỗi 10: Cho rằng WebFlux đồng nghĩa luôn dùng Reactor Netty server

WebFlux có thể chạy với các runtime khác được hỗ trợ. ReactorResourceFactory dành riêng cho Reactor Netty; khi server không phải Reactor Netty, nó vẫn có thể hữu ích cho WebClient sử dụng Reactor Netty, nhưng không cấu hình server engine khác.

### Lỗi 11: Dùng WebClient.builder() thủ công khắp nơi

Có thể bỏ qua Boot customizers hoặc cấu hình chung. Ưu tiên inject WebClient.Builder, khai báo bean client theo mục đích và thống nhất timeout/codec/observability.

### Lỗi 12: Dùng .block() trong reactive endpoint

.block() chặn thread đang gọi và có thể gây lỗi trên event loop. Trả Mono/Flux cho Spring WebFlux xử lý; không ép chuyển sang synchronous API trừ khi đang ở một boundary blocking được thiết kế riêng.

## 16. Checklist thiết kế trước production

- [ ] Xác nhận ứng dụng chạy reactive WebFlux và HTTP runtime thực tế là Reactor Netty khi muốn chia sẻ server resources.
- [ ] Liệt kê những outbound WebClient/HttpClient và SDK sử dụng Reactor Netty.
- [ ] Chọn ownership: HttpResources global hay ReactorResourceFactory dedicated theo ApplicationContext.
- [ ] Nếu chọn useGlobalResources=false, wiring toàn bộ client cần chia sẻ tới đúng factory.
- [ ] Bảo đảm không khai báo nhiều ReactorResourceFactory ngoài ý muốn.
- [ ] Tách rõ event loops, connection provider và mỗi TCP connection.
- [ ] Không tạo/đóng provider hoặc loops trong mỗi request.
- [ ] Thiết lập connection limits, pending-acquire timeout và HTTP client response timeout theo SLO.
- [ ] Kiểm tra connect/TLS/overall deadline và chính sách retry độc lập với connection pooling.
- [ ] Tránh blocking trên event-loop threads; có giới hạn riêng cho blocking work.
- [ ] Nếu dùng nhiều ApplicationContext trong JVM, kiểm tra khả năng shutdown độc lập.
- [ ] Test context close/restart và test dưới tải để phát hiện thread/socket leak.
- [ ] Đo active/idle/pending HTTP connections, event-loop latency, CPU, memory, GC và lỗi timeout.
- [ ] Kiểm tra read/write body, cancellation và release connection trong error paths.
- [ ] Kết hợp readiness, graceful shutdown và termination deadline khi triển khai container.
- [ ] Không công khai metrics có tag giá trị không giới hạn hoặc dữ liệu nhạy cảm.

## 17. Câu hỏi tự kiểm tra

**Câu 1: ReactorResourceFactory có phải là WebClient không?**  
Không. Nó quản lý tài nguyên Reactor Netty mà WebClient/HttpClient có thể sử dụng; WebClient mới là API gửi HTTP requests.

**Câu 2: useGlobalResources=true nghĩa là chia sẻ pool giữa tất cả pod?**  
Không. Global resources nằm trong phạm vi một JVM. Các pod/JVM khác nhau có thread/socket pools riêng.

**Câu 3: Hai WebClient dùng chung factory có phải dùng cùng một TCP connection?**  
Không nhất thiết. Chúng chia sẻ cơ chế quản lý pool/event loops; socket được reuse khi remote endpoint, protocol và policy cho phép.

**Câu 4: Vì sao vẫn có nhiều Netty threads sau khi đã tạo dedicated factory?**  
Có thể thư viện khác tạo global resources hoặc LoopResources riêng, hoặc nhiều context vẫn đang chạy. Cần xem actual resource ownership, không chỉ số bean.

**Câu 5: Tại sao không gọi dispose sau mỗi HTTP request?**  
Vì ConnectionProvider và LoopResources thường được chia sẻ qua nhiều request và WebClient; dispose một lần có thể làm lỗi các request còn đang chạy.

**Câu 6: Set maxConnections=80 có nghĩa nhiều nhất 80 HTTP requests toàn ứng dụng?**  
Không. Giới hạn được áp vào các pool mà provider quản lý theo ngữ nghĩa Reactor Netty; server inbound requests, nhiều remote endpoints và giao thức HTTP có thể có các mức concurrency khác.

**Câu 7: Test WebFlux controller bằng WebTestClient có chứng minh resource cleanup?**  
Không. Controller slice có thể không khởi động HTTP server thật; cần integration test với ApplicationContext, client/server resources và shutdown để kiểm chứng.

**Câu 8: Dùng global hay dedicated phù hợp hơn cho microservice nhỏ?**  
Thường global mặc định phù hợp một JVM độc lập, đơn giản và tái sử dụng hiệu quả. Chọn dedicated nếu có yêu cầu rõ về isolation, ownership hoặc nhiều context cùng JVM.

## 18. Tổng kết

Trong ứng dụng Spring WebFlux dùng Reactor Netty, **ReactorResourceFactory là điểm quản lý vòng đời và chia sẻ tài nguyên HTTP**, không phải một HTTP client hay controller. Nó gắn kết hai loại tài nguyên chủ đạo: **LoopResources** cho event-loop I/O và **ConnectionProvider** cho connection pooling của HTTP client.

Mặc định, Reactor Netty có mô hình **HttpResources global trong một JVM**; đây thường là cách đơn giản để dùng chung tài nguyên cố định. Khi cần một vòng đời riêng cho ApplicationContext, có thể đặt useGlobalResources=false và cấp supplier để Spring quản lý tài nguyên dedicated. Điều kiện then chốt là các WebClient/HttpClient thực tế phải được wiring vào cùng factory; nếu không, ứng dụng có thể chạy lẫn global và dedicated resources mà không nhận ra.

Thiết kế đúng không chỉ là tăng pool hoặc số event loops. Cần một owner rõ ràng, connection/timeouts có giới hạn, code non-blocking, test đóng ApplicationContext và metrics dưới tải. Khi hiểu rõ **ai tạo — ai dùng — ai đóng**, bạn có thể tùy chỉnh WebFlux và Reactor Netty mà vẫn giữ ứng dụng ổn định từ startup đến graceful shutdown.

## 19. Tài liệu chính thức để tìm hiểu thêm

- Spring Framework — WebClient / Reactor Netty resources: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework API — ReactorResourceFactory: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorResourceFactory.html
- Spring Framework API — ReactorClientHttpConnector: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot — Graceful Shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Reactor Netty — HTTP Client: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Netty — ConnectionProvider API: https://projectreactor.io/docs/netty/release/api/reactor/netty/resources/ConnectionProvider.html
