# Đóng máy chủ, `ApplicationContext` và tài nguyên mạng đúng vòng đời trong Spring WebFlux

## 1. Vì sao phải quản lý vòng đời cùng nhau?

Một ứng dụng Spring WebFlux thường có nhiều thành phần chạy lâu dài:

- **HTTP server** nhận kết nối và xử lý request, ví dụ Reactor Netty `HttpServer`.
- **Event loop** điều phối I/O và callback trên các thread chuyên dụng.
- **HTTP client** như `WebClient`, có thể duy trì connection pool để gọi dịch vụ bên ngoài.
- **Spring `ApplicationContext`** tạo, kết nối và quản lý các bean như controller, service, filter, client và resource factory.
- **Tài nguyên theo request** như `DataBuffer`, response body, subscription và các tác vụ đang xử lý.

Các thành phần này có quan hệ phụ thuộc. Một request đang chạy có thể cần gọi `WebClient`, đọc database reactive và ghi response. Nếu đóng connection pool hoặc event loop trước khi request hoàn tất, request đang xử lý có thể thất bại. Nếu chỉ đóng server mà quên tài nguyên do ứng dụng tự tạo, thread và connection có thể tiếp tục tồn tại sau khi server ngừng nhận request.

Quản lý đúng vòng đời nghĩa là **khởi tạo tài nguyên trước khi nhận traffic, dừng nhận request mới trước, cho công việc đang chạy thời gian hoàn tất, rồi đóng tài nguyên dùng chung khi không còn ai sử dụng**.

Bài này tập trung vào Spring Boot WebFlux chạy Reactor Netty. Những khái niệm về `ApplicationContext`, lifecycle và resource ownership vẫn hữu ích khi dùng server reactive khác, nhưng API cụ thể của Jetty/Tomcat/Undertow sẽ khác.

## 2. Phân biệt server, ApplicationContext và network resources

Ba khái niệm thường bị gộp làm một nhưng có chủ sở hữu và vòng đời khác nhau.

| Thành phần | Vai trò | Vòng đời thường do ai quản lý? |
|---|---|---|
| `HttpServer` / `DisposableServer` | Bind địa chỉ/cổng, nhận kết nối và phục vụ HTTP | Reactor Netty hoặc Spring Boot web server lifecycle |
| `ApplicationContext` | Tạo bean, quản lý dependency, startup và shutdown của ứng dụng | Spring Framework / Spring Boot |
| `LoopResources` | Nhóm event loop và thread xử lý I/O | Reactor Netty hoặc `ReactorResourceFactory` |
| `ConnectionProvider` | Quản lý pool kết nối outbound của Reactor Netty HTTP client | Reactor Netty hoặc `ReactorResourceFactory` |
| `HttpResources` | Tài nguyên Reactor Netty dùng chung, gồm event loop và tài nguyên client liên quan | Reactor Netty; có thể được Spring quản lý qua factory |
| `DataBuffer` / Netty `ByteBuf` | Bộ nhớ chứa dữ liệu request/response | Operator/handler sở hữu buffer và phải giải phóng đúng quy tắc |

### 2.1. Server không đồng nghĩa với event loop

`DisposableServer` đại diện cho server đã bind. Khi server được dispose, listener/channel của server được đóng theo API server. `LoopResources` lại là nhóm event loop được dùng để thực thi I/O. Một ứng dụng có thể có nhiều server/client cùng chia sẻ loop resources.

Vì thế, **đóng một server không tự động có nghĩa mọi network resource của ứng dụng đã được giải phóng**. Ngược lại, dispose event loop dùng chung khi server khác hoặc `WebClient` vẫn còn hoạt động sẽ làm hỏng những thành phần đó.

### 2.2. `ConnectionProvider` chủ yếu phục vụ kết nối đi ra

`ConnectionProvider` quản lý pool của Reactor Netty `HttpClient`/`TcpClient`, tức các kết nối ứng dụng **chủ động mở tới dịch vụ khác**. Các kết nối inbound mà server nhận từ browser/client được quản lý ở tầng server và Netty channel.

Boot có thể cấu hình dùng chung Reactor Netty resources giữa server và `WebClient` khi cùng công nghệ được sử dụng và client lấy từ `WebClient.Builder` do Boot auto-configure. Việc chia sẻ giúp giảm số nhóm thread và tránh tạo nhiều resource pool không cần thiết.

Không nên hiểu `ConnectionProvider` là pool của các HTTP request đến server; đó là hai hướng giao tiếp khác nhau.

### 2.3. `ApplicationContext` và Reactor `Context` là hai khái niệm khác nhau

- **Spring `ApplicationContext`** là container quản lý bean singleton, dependency và vòng đời ứng dụng. Khi context đóng, Spring phát tín hiệu dừng tới các bean lifecycle và gọi các callback hủy tài nguyên.
- **Reactor `Context`** là metadata gắn với subscription, ví dụ trace ID hoặc tenant ID. Nó đi theo reactive chain và không sở hữu server, thread pool hay connection pool.

`contextWrite` hoặc `deferContextual` không khởi động/đóng resource. Muốn quản lý tài nguyên, dùng Spring bean lifecycle, Reactor Netty disposal API hoặc cơ chế quản lý phù hợp với resource đó.

## 3. Các tài nguyên Reactor Netty cần biết

### 3.1. `LoopResources`

`LoopResources` cung cấp event loop group và channel factory cho Reactor Netty. Event loop nhận sự kiện I/O và chạy callback; nhiều kết nối có thể dùng chung một số lượng thread giới hạn.

Vòng đời cần nhớ:

- Tạo loop resources khi ứng dụng chuẩn bị khởi động.
- Dùng lại chúng cho các server/client được thiết kế để chia sẻ.
- Chỉ dispose sau khi các server/client dùng chúng đã dừng.
- Nếu dùng `LoopResources` tự tạo, ứng dụng phải chịu trách nhiệm quản lý và dispose nó.

Không tạo một `LoopResources` mới cho từng request hoặc từng lần gọi WebClient. Việc đó làm tăng thread và tài nguyên hệ điều hành, đồng thời khiến shutdown phức tạp.

### 3.2. `ConnectionProvider`

`ConnectionProvider` quản lý pool kết nối outbound. Pool có thể giới hạn số kết nối hoạt động, số yêu cầu chờ lấy kết nối và thời gian chờ acquire. Những giới hạn này bảo vệ ứng dụng khỏi mở quá nhiều kết nối tới cùng dịch vụ.

Khi shutdown:

1. Ngừng tạo các request outbound mới.
2. Cho request đang chạy hoàn tất trong thời gian grace period nếu có thể.
3. Dispose connection provider sau khi các thành phần dùng pool đã dừng.
4. Đảm bảo retry/reconnect không tiếp tục tạo request mới trong lúc ứng dụng đóng.

Nếu client và server cùng chia sẻ tài nguyên, không dispose pool hoặc loop chỉ vì một endpoint/server riêng lẻ đã ngừng.

### 3.3. `HttpResources` và global resources

Reactor Netty cung cấp global resources trong `reactor.netty.http.HttpResources`. Đây là chế độ dùng chung thuận tiện cho các ứng dụng có vòng đời trùng với vòng đời JVM.

Có một khác biệt quan trọng:

- Nếu ứng dụng sống đến khi JVM kết thúc, global resources thường có thể sống cùng process.
- Nếu Spring `ApplicationContext` có thể được đóng rồi mở lại trong cùng JVM (ví dụ integration test hoặc ứng dụng nhúng), cần có resource owner quản lý shutdown theo context.
- Khi nhiều server/client cùng dùng global resources, dispose global resources sẽ ảnh hưởng **tất cả** thành phần đó, không chỉ một bean.

Không gọi `HttpResources.disposeLoopsAndConnections()` trong `@PreDestroy` của một service tùy ý nếu service khác vẫn sử dụng Reactor Netty. Dùng `ReactorResourceFactory` được Spring quản lý hoặc để global resources sống theo process khi đó là chủ đích kiến trúc.

## 4. `ReactorResourceFactory`: giao tài nguyên cho Spring quản lý

Spring Framework cung cấp `ReactorResourceFactory` để quản lý Reactor Netty resources như `LoopResources` và `ConnectionProvider` trong vòng đời `ApplicationContext`.

Khi được đăng ký như một Spring bean, factory có thể khởi động resources trong lifecycle startup và đóng chúng trong lifecycle shutdown. Spring Boot tự cấu hình factory khi auto-configure Reactor Netty server. Nếu dùng `WebClient.Builder` do Boot cung cấp, server và client Reactor Netty có thể chia sẻ resources.

### 4.1. Dùng global resources (mặc định)

Với ứng dụng thông thường, mặc định `useGlobalResources` là `true`. Factory quản lý global `HttpResources` theo vòng đời Spring. Không cần tự gọi `HttpResources.dispose...` trong mỗi service.

Nếu cần tùy chỉnh thời gian shutdown, có thể khai báo bean:

```java
@Configuration(proxyBeanMethods = false)
class ReactorResourceConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
        factory.setShutdownTimeout(Duration.ofSeconds(15));

        return factory;
    }
}
```

Đoạn code trên dành cho Spring Framework 6.1+ (package `org.springframework.http.client.ReactorResourceFactory`) và ứng dụng Spring Boot dùng Reactor Netty. Import cần thiết:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ReactorResourceFactory;
```

`shutdownQuietPeriod` là khoảng thời gian yên lặng trước khi loop resources kết thúc; nếu có task mới được submit trong khoảng đó, khoảng chờ được bắt đầu lại. `shutdownTimeout` là giới hạn tối đa để chờ dispose hoàn tất. Giá trị mặc định của Reactor Netty thường là 2 giây quiet period và 15 giây timeout; hãy chọn theo thời gian shutdown tổng thể của ứng dụng.

Nếu Spring Boot đã tự cung cấp factory, chỉ khai báo bean tùy chỉnh khi cần thay đổi cấu hình. Một bean `ReactorResourceFactory` tùy chỉnh được Boot dùng cho cấu hình resources của server và client Reactor Netty.

### 4.2. Dùng resources riêng thay vì global

Có thể đặt `setUseGlobalResources(false)` để factory tạo resources riêng được quản lý theo context:

```java
@Bean
ReactorResourceFactory reactorResourceFactory() {
    ReactorResourceFactory factory = new ReactorResourceFactory();
    factory.setUseGlobalResources(false);
    factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
    factory.setShutdownTimeout(Duration.ofSeconds(15));
    return factory;
}
```

Trong chế độ này, các server/client cần chia sẻ cùng resources phải được cấu hình dùng đúng factory đó. Nếu tự tạo thêm `LoopResources` hoặc `ConnectionProvider` ở một nơi khác, phải xác định rõ ai sở hữu và ai dispose từng instance.

Khi cung cấp supplier riêng:

```java
factory.setLoopResourcesSupplier(
        () -> LoopResources.create("application-http")
);

factory.setConnectionProviderSupplier(
        () -> ConnectionProvider.builder("application-http")
                .maxConnections(100)
                .build()
);
```

Đây là cấu hình nâng cao. Các supplier trên chỉ được dùng khi factory quản lý resources riêng; không có tác dụng khi factory đang dùng global resources. `maxConnections(100)` là ví dụ, cần tính theo tải, số host đích và giới hạn dịch vụ bên ngoài.

Không tạo factory hoặc pool mới mỗi lần xử lý request. Đặt chúng ở cấp ApplicationContext để các bean dùng chung và lifecycle được kiểm soát.

## 5. Startup: khởi tạo resources trước khi nhận traffic

Một trình tự startup phổ biến:

```text
Process bắt đầu
    |
    v
Spring ApplicationContext refresh
    |
    v
Tạo bean và ReactorResourceFactory
    |
    v
Khởi động LoopResources / ConnectionProvider
    |
    v
Khởi động reactive web server và bind port
    |
    v
Application ready
    |
    v
Readiness probe cho phép nhận traffic
```

Spring Boot quản lý phần lớn trình tự này. Khi cần custom server hoặc resource factory, phải đảm bảo resource được khởi tạo trước khi server sử dụng.

### 5.1. Warmup và thời gian khởi động request đầu tiên

Reactor Netty thường khởi tạo event loop và native transport theo nhu cầu; thao tác bind có thể chịu phần chi phí khởi tạo này. Khi độ trễ request đầu tiên quan trọng, có thể cân nhắc warmup server trước khi công bố readiness.

Ví dụ API Reactor Netty:

```java
HttpServer httpServer = HttpServer.create()
        .host("127.0.0.1")
        .port(8080);

httpServer.warmup().block();

DisposableServer server = httpServer
        .handle((request, response) ->
                response.sendString(Mono.just("ready\n")))
        .bindNow();
```

Đây là đoạn minh họa cho ứng dụng tự quản lý `HttpServer`. `warmup()` khởi tạo các thành phần cần thiết theo cấu hình server, nhưng chưa thay thế thao tác `bind()`. `block()` ở đây nằm trong giai đoạn bootstrap trên main thread; không đưa nó vào event loop hoặc request handler.

### 5.2. Readiness và liveness

Readiness trả lời câu hỏi: instance có thể nhận request mới không? Liveness trả lời câu hỏi: process có còn hoạt động không?

Không nên đánh dấu instance ready chỉ vì JVM đã chạy. Hãy chờ server bind và các dependency bắt buộc đã sẵn sàng. Khi shutdown bắt đầu, readiness nên chuyển sang false hoặc instance cần được loại khỏi load balancer trước khi server đóng.

Readiness không thay thế việc drain request đang chạy. Nó ngăn traffic mới được điều phối tới instance; graceful shutdown xử lý các request đã được nhận.

## 6. Shutdown: dừng theo đúng thứ tự

Một quy trình shutdown an toàn thường có các giai đoạn:

```text
Nhận SIGTERM / đóng ApplicationContext
              |
              v
Đánh dấu instance không còn ready
              |
              v
Ngừng nhận request mới
              |
              v
Cho request đang chạy hoàn tất trong grace period
              |
              v
Dừng background workers và tác vụ phụ thuộc
              |
              v
Đóng server và client resources
              |
              v
Đóng database / message clients / các bean còn lại
              |
              v
ApplicationContext đóng hoàn toàn
              |
              v
Process kết thúc
```

Thứ tự chính xác giữa các bean phụ thuộc cấu hình lifecycle/phase. Với Spring Boot, graceful shutdown của embedded web server được thực hiện trong giai đoạn đầu của việc dừng các `SmartLifecycle` bean. Điều này cho phép server ngừng nhận request mới trước khi các dependency cần phục vụ request bị đóng.

Nếu tự viết bean chạy nền hoặc consumer, hãy thiết kế lifecycle sao cho chúng dừng nhận công việc mới và hoàn tất phần việc đang xử lý trước khi dependency bị dispose.

### 6.1. Graceful shutdown trong Spring Boot

Có thể cấu hình tường minh trong `application.properties`:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Hoặc YAML:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Trong thời gian grace period, Reactor Netty ngừng chấp nhận request mới ở tầng network và cho request đang xử lý cơ hội hoàn tất. Khi timeout kết thúc, ứng dụng vẫn phải tiến hành dừng; request chưa hoàn tất có thể bị hủy hoặc kết nối bị đóng.

`spring.lifecycle.timeout-per-shutdown-phase` là thời gian chờ cho một phase lifecycle. Đây không phải timeout cho từng request HTTP hay timeout cho database. Cấu hình timeout ở từng HTTP client/database client vẫn cần thiết.

Với Spring Boot hiện đại, graceful shutdown được tích hợp vào lifecycle của embedded server; khai báo rõ property giúp cấu hình có chủ đích và dễ kiểm tra giữa các môi trường/phiên bản.

### 6.2. SIGTERM, Docker và Kubernetes

Graceful shutdown cần process nhận tín hiệu dừng phù hợp, thường là `SIGTERM`. `SIGKILL` chấm dứt process ngay và không cho ứng dụng chạy callback cleanup. Một số thao tác Stop trong IDE cũng có thể không gửi tín hiệu như môi trường production.

Trong container/orchestrator:

1. Đưa instance ra khỏi readiness/load balancer.
2. Chờ thời gian deregistration/endpoint propagation phù hợp.
3. Gửi `SIGTERM` cho process.
4. Để Spring Boot drain request trong grace period.
5. Chỉ sau đó mới buộc dừng process nếu vượt `terminationGracePeriodSeconds`.

Thời gian cho phép container dừng cần lớn hơn thời gian drain của ứng dụng cộng thời gian cần thiết để hệ thống điều phối ngừng gửi traffic mới. Nếu thời gian của orchestrator ngắn hơn timeout của ứng dụng, process có thể bị kill trước khi cleanup hoàn tất.

### 6.3. Request dài, streaming và WebSocket

Một request thông thường có thể hoàn tất trong vài mili giây hoặc vài giây. Server-Sent Events, WebSocket và response streaming có thể giữ kết nối lâu hơn nhiều.

Không nên giả định mọi kết nối sẽ tự hoàn tất trong grace period. Cần chính sách riêng:

- Client có thể reconnect sau khi server dừng.
- Stream có thể phát event cuối hoặc cursor/checkpoint để client tiếp tục.
- Tác vụ nền cần checkpoint hoặc lưu trạng thái tiến trình.
- Timeout shutdown phải đủ cho công việc được phép drain.
- Nếu timeout hết, chấp nhận việc hủy kết nối và thiết kế client retry/reconnect có kiểm soát.

Graceful shutdown không đảm bảo mọi request kéo dài vô hạn đều được giữ đến khi hoàn tất.

## 7. Tự quản lý `DisposableServer` khi không dùng Spring Boot

Spring WebFlux cung cấp abstraction xử lý HTTP; nếu tự tạo Reactor Netty server, ứng dụng phải sở hữu vòng đời của `DisposableServer`.

Ví dụ:

```java
DisposableServer server = HttpServer.create()
        .host("127.0.0.1")
        .port(8080)
        .handle((request, response) ->
                response.sendString(Mono.just("hello\n")))
        .bindNow();

System.out.println("Listening on port " + server.port());

Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    server.disposeNow(Duration.ofSeconds(10));
}));

server.onDispose().block();
```

Ý nghĩa:

- `bindNow()` bind server và trả `DisposableServer`.
- `port()` trả về cổng server đang lắng nghe.
- `onDispose()` là Publisher quan sát thời điểm server đã đóng.
- `disposeNow(Duration)` yêu cầu đóng channel và chờ theo timeout được chỉ định.
- `onDispose().block()` giữ main thread chờ server kết thúc; đây là chờ lifecycle trong chương trình bootstrap, không phải block trong event loop.

`disposeNow()` là API blocking; chỉ gọi ở main/shutdown thread phù hợp. Không gọi nó từ `HttpHandler`, controller hoặc callback event loop.

Đoạn trên thể hiện cách đóng server thủ công. Nếu cần drain các request đang chạy theo chính sách production, hãy dùng graceful shutdown của Spring Boot hoặc triển khai cơ chế drain phù hợp với server/channel group và timeout. Đừng suy luận rằng mọi lời gọi `disposeNow()` mặc định đều chờ vô hạn cho tất cả request đang hoạt động.

Một server tự tạo cũng có thể được Spring quản lý thông qua bean lifecycle, nhưng khi đó phải bảo đảm bean dừng đúng phase và resources không bị dispose trước server. Tránh tạo server trong một phương thức khởi tạo phụ rồi quên đăng ký callback đóng nó.

## 8. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ sau tạo một ứng dụng WebFlux có endpoint nhanh và endpoint mất 5 giây. Khi process nhận tín hiệu shutdown, Spring Boot dừng nhận request mới, chờ request hiện tại trong thời gian grace period rồi đóng Reactor Netty resources do Spring quản lý.

Cấu trúc:

```text
webflux-lifecycle-demo/
├── pom.xml
└── src/main/java/demo/LifecycleDemoApplication.java
└── src/main/resources/application.properties
```

File `pom.xml`:

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-lifecycle-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/demo/LifecycleDemoApplication.java`:

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ReactorResourceFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        // Dùng global Reactor Netty resources và để Spring quản lý lifecycle.
        factory.setUseGlobalResources(true);
        factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
        factory.setShutdownTimeout(Duration.ofSeconds(15));

        return factory;
    }
}

@RestController
class LifecycleController {

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ready\n");
    }

    @GetMapping("/slow")
    Mono<String> slow() {
        return Mono.delay(Duration.ofSeconds(5))
                .thenReturn("request completed\n");
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Chạy từ thư mục dự án bằng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Kiểm tra endpoint:

```bash
curl http://localhost:8080/health
```

Body:

```text
ready
```

Gửi một request mất 5 giây:

```bash
curl http://localhost:8080/slow
```

Body khi request hoàn tất:

```text
request completed
```

Để quan sát shutdown, hãy bắt đầu `/slow`, sau đó gửi `SIGTERM` cho process trong lúc request đang chạy. Nếu grace period đủ dài, request có thể hoàn tất và response được trả trước khi context đóng xong. Log shutdown cụ thể thay đổi theo phiên bản Spring Boot và môi trường chạy.

**Vì sao ví dụ này quản lý đúng vòng đời?**

1. `SpringApplication.run(...)` tạo `ApplicationContext` và để Boot quản lý embedded server.
2. `ReactorResourceFactory` là bean của context; factory quản lý Reactor Netty global resources.
3. Endpoint `/slow` trả `Mono` không chặn bằng `Mono.delay`; request không giữ event-loop thread trong lúc chờ.
4. Khi shutdown, server ngừng nhận request mới và cho request đang chạy thời gian hoàn tất.
5. Sau khi server dừng theo lifecycle, factory đóng resources theo cấu hình quiet period/timeout.
6. Ứng dụng không tự dispose global resources trong controller hoặc service.

Đây là mẫu tích hợp cho Spring Boot 3.3.5, Spring Framework 6.1 và Java 17. Nếu dự án dùng Spring Boot/Spring Framework khác, hãy để BOM của Boot quản lý phiên bản và kiểm tra package/API tương ứng.

## 9. Khi nào dùng global resources, khi nào dùng resources riêng?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Ứng dụng Boot bình thường, một lifecycle gắn với JVM | Global resources qua factory mặc định | Server và WebClient có thể chia sẻ event loop, giảm số tài nguyên |
| Ứng dụng có nhiều server/client Reactor Netty trong cùng context | Một resource factory được chia sẻ | Có một chủ sở hữu rõ ràng cho resources |
| Ứng dụng nhúng, context đóng/mở lại trong cùng JVM | Spring-managed `ReactorResourceFactory` | Resources có thể được dừng theo context |
| Cần cô lập pool/thread giữa nhóm client hoặc server | Resources riêng được cấu hình có chủ đích | Có thể đặt giới hạn và vòng đời độc lập |
| Một component chỉ dừng endpoint nhưng ứng dụng vẫn gọi WebClient | Chỉ dừng server component | Không phá resources đang được client dùng chung |
| Chạy test tạo server thủ công | Dispose server trong teardown | Tránh cổng và channel còn sống giữa các test |

Chế độ resources riêng không có nghĩa mỗi bean phải có một pool riêng. Nếu nhiều server/client cần chia sẻ, hãy dùng chung một factory hoặc truyền cùng resource instance cho chúng. Quá nhiều pool làm tăng thread, connection, memory và độ phức tạp shutdown.

## 10. Các lỗi quản lý vòng đời thường gặp

### Lỗi 1: Chỉ đóng server mà quên resources tự tạo

Một `DisposableServer` đã dừng nhưng `LoopResources` hoặc `ConnectionProvider` do ứng dụng tự tạo vẫn có thể sống. Thread không daemon hoặc connection pool còn hoạt động có thể giữ JVM không thoát.

**Cách xử lý:** xác định ai tạo resources, đăng ký owner trong Spring context hoặc gọi dispose ở teardown của component sở hữu chúng.

### Lỗi 2: Dispose global resources từ một service

Một service gọi `HttpResources.disposeLoopsAndConnections()` có thể làm server/client khác cùng JVM mất event loop hoặc pool.

**Cách xử lý:** để `ReactorResourceFactory` quản lý global resources theo context, hoặc chỉ dispose khi ứng dụng thực sự là owner duy nhất và tất cả server/client đã dừng.

### Lỗi 3: Đóng ConnectionProvider trước khi request drain xong

Một request đang xử lý có thể cần `WebClient` gọi dịch vụ khác. Nếu pool outbound đóng trước, request đó có thể thất bại giữa chừng.

**Cách xử lý:** dừng nhận request mới, đợi các request hiện tại hoàn tất trong grace period, sau đó mới đóng pool.

### Lỗi 4: Gọi `.block()` hoặc `disposeNow()` trong request handler

Đây là thao tác chặn. Nếu chạy trên event loop, nó có thể giữ thread phục vụ nhiều kết nối và làm nghẽn toàn server.

**Cách xử lý:** trả Publisher từ handler/controller. Chỉ dùng API blocking ở main thread, bootstrap hoặc shutdown thread khi thật sự cần chờ.

### Lỗi 5: Đặt timeout shutdown của container ngắn hơn timeout của ứng dụng

Orchestrator có thể gửi SIGKILL khi Spring vẫn đang drain request hoặc đóng resources.

**Cách xử lý:** phối hợp `spring.lifecycle.timeout-per-shutdown-phase`, timeout của resource factory, thời gian deregistration và `terminationGracePeriodSeconds`.

### Lỗi 6: Dùng `@PreDestroy` để đóng mọi thứ cùng lúc

`@PreDestroy` tiện cho một bean đơn giản, nhưng không tự biểu diễn trình tự drain phức tạp giữa server, worker, client và database. Đóng dependency quá sớm có thể phá request đang chạy.

**Cách xử lý:** dùng lifecycle phase phù hợp, `SmartLifecycle` khi cần stop bất đồng bộ có callback, hoặc dựa vào lifecycle tích hợp của Spring Boot. Chỉ dùng `@PreDestroy` cho cleanup đơn giản sau khi các thành phần phụ thuộc đã dừng.

### Lỗi 7: Tạo resources mới theo request

Mỗi request tạo `ConnectionProvider`, `LoopResources` hoặc scheduler riêng sẽ khiến tài nguyên tăng theo traffic và rất khó đóng đúng lúc.

**Cách xử lý:** tạo resource ở cấp ứng dụng/context, dùng chung theo phạm vi thiết kế và đặt giới hạn pool/concurrency rõ ràng.

### Lỗi 8: Nghĩ Reactor Context là nơi lưu tài nguyên để tự đóng

Reactor Context chỉ truyền metadata theo subscription. Nó không phải container lifecycle và không tự gọi dispose khi request hoàn tất.

**Cách xử lý:** resource có vòng đời ứng dụng nên do Spring bean quản lý; resource có vòng đời request phải có cleanup gắn với `using`, `usingWhen`, `doFinally` hoặc API sở hữu tài nguyên tương ứng.

### Lỗi 9: Quên cleanup `DataBuffer`/`ByteBuf` khi tự quản lý buffer

Một buffer được retain hoặc tách khỏi flow thông thường có thể cần release đúng số lần. Nếu discard buffer mà không giải phóng, memory leak có thể xảy ra; nếu release quá sớm, việc ghi response có thể lỗi.

**Cách xử lý:** ưu tiên API Spring/Reactor quản lý buffer theo pipeline. Khi tự retain, cache, discard hoặc giữ buffer ngoài flow, tuân thủ quy tắc ownership/reference count và dùng `DataBufferUtils.release` tại đúng boundary.

### Lỗi 10: Dừng process bằng SIGKILL rồi kỳ vọng callback chạy

SIGKILL không cho Spring gọi `stop`, `destroy` hoặc shutdown hook. Không có graceful cleanup ở cấp ứng dụng.

**Cách xử lý:** môi trường triển khai cần gửi SIGTERM và dành đủ thời gian shutdown; SIGKILL chỉ là biện pháp cuối khi timeout đã hết.

## 11. Kiểm thử và quan sát lifecycle

Cần kiểm tra cả startup, shutdown bình thường và shutdown khi có traffic.

### 11.1. Kiểm tra server đã dừng

Với server tự quản lý, có thể kiểm tra `DisposableServer.isDisposed()` sau khi gọi dispose và chờ `onDispose()`:

```java
server.dispose();
server.onDispose().block(Duration.ofSeconds(5));

if (!server.isDisposed()) {
    throw new IllegalStateException("Server is still running");
}
```

Đây là đoạn kiểm thử/diagnostic cho server thủ công. `block()` chỉ nằm trong test hoặc luồng điều phối; không gọi trong request handler.

### 11.2. Kiểm tra Spring context đóng

Trong integration test, tạo context, gửi request qua `WebTestClient` hoặc HTTP client, rồi đóng context. Xác minh server không còn nhận request và các resource factory/bean được dừng theo lifecycle.

Nếu test mở nhiều context trong cùng JVM, đặc biệt chú ý global resources và thứ tự đóng context. Tránh tự dispose global resource trong một test trong khi test khác còn dùng chúng.

### 11.3. Quan sát metric và log

Các tín hiệu hữu ích:

- Thời gian từ SIGTERM đến lúc process thoát.
- Số request đang xử lý khi shutdown bắt đầu.
- Số request hoàn tất, bị hủy hoặc timeout trong grace period.
- Event-loop thread và connection pool còn sống sau khi context đóng.
- Connection acquire pending, timeout và số kết nối outbound đang hoạt động.
- Lỗi `RejectedExecutionException`, connection closed hoặc lỗi ghi response trong giai đoạn shutdown.

Không log access token, request body nhạy cảm hoặc dữ liệu cá nhân chỉ để debug shutdown. Chọn metric có tag giới hạn cardinality; không dùng URI đầy đủ chứa ID động làm tag nếu điều đó làm số lượng metric tăng không kiểm soát.

## 12. Bài tập tự kiểm tra

**Câu 1.** Đóng `DisposableServer` có đồng nghĩa đã đóng mọi `LoopResources` và `ConnectionProvider` trong ứng dụng không?

**Đáp án:** Không. Server và network resources có thể được chia sẻ. Phải đóng từng resource theo đúng owner và sau khi các server/client sử dụng nó đã dừng.

**Câu 2.** `ConnectionProvider` thường quản lý kết nối nào?

**Đáp án:** Pool kết nối outbound do Reactor Netty HTTP/TCP client dùng để gọi dịch vụ khác. Kết nối inbound tới server được quản lý ở tầng server/channel.

**Câu 3.** `ApplicationContext` có vai trò gì khi shutdown?

**Đáp án:** Nó điều phối lifecycle bean: phát tín hiệu stop, đóng resource factory và gọi các callback destroy theo lifecycle/phase.

**Câu 4.** Reactor Context có thể thay thế `ReactorResourceFactory` không?

**Đáp án:** Không. Reactor Context truyền metadata theo subscription; `ReactorResourceFactory` quản lý resources theo lifecycle của Spring context.

**Câu 5.** Vì sao server cần ngừng nhận request mới trước khi đóng WebClient connection pool?

**Đáp án:** Request đang chạy có thể còn cần WebClient gọi dịch vụ ngoài. Nếu pool bị đóng sớm, request hiện tại có thể lỗi trước khi response hoàn tất.

**Câu 6.** `spring.lifecycle.timeout-per-shutdown-phase=20s` có nghĩa mọi request được chờ tối đa 20 giây riêng lẻ không?

**Đáp án:** Không. Đây là timeout cho một phase lifecycle shutdown. Request còn lại khi hết grace period có thể bị hủy hoặc kết nối bị đóng.

**Câu 7.** Tại sao SIGKILL không phù hợp cho graceful shutdown?

**Đáp án:** SIGKILL chấm dứt process ngay, không cho Spring chạy lifecycle callback hoặc resource cleanup.

**Câu 8.** Nếu server và WebClient cùng dùng global Reactor Netty resources, một bean service có nên tự gọi `HttpResources.disposeLoopsAndConnections()` trong `@PreDestroy` không?

**Đáp án:** Không. Hành động đó có thể phá các server/client khác đang dùng chung resources. Để resource factory quản lý chúng theo ApplicationContext.

## 13. Checklist đưa vào production

1. Xác định rõ owner của server, `LoopResources`, `ConnectionProvider`, WebClient, database pool và background workers.
2. Ưu tiên Spring Boot auto-configuration; dùng `ReactorResourceFactory` bean khi cần tùy chỉnh resource lifecycle.
3. Chỉ tạo resource ở cấp ứng dụng/context, tránh tạo theo request.
4. Bảo đảm server ngừng nhận traffic mới trước khi đóng dependency mà request đang chạy cần dùng.
5. Cấu hình graceful shutdown và timeout phù hợp với thời gian xử lý thực tế.
6. Phối hợp readiness, load balancer deregistration, SIGTERM và timeout của container.
7. Đặt timeout riêng cho HTTP client/database; không coi grace period là timeout cho mọi I/O.
8. Dispose resource riêng sau cùng; không dispose global resources khi còn thành phần khác sử dụng.
9. Kiểm thử shutdown trong lúc có request thường, request chậm, streaming và outbound call.
10. Theo dõi thread, connection pool, request bị hủy và thời gian process thoát.
11. Với code tự quản lý `DataBuffer`/`ByteBuf`, kiểm tra ownership và release.
12. Phân biệt Spring `ApplicationContext` với Reactor `Context`; mỗi loại có phạm vi và trách nhiệm riêng.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot — Reactive Web Applications, Reactive Server Resources Configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework — ReactorResourceFactory Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/http/client/ReactorResourceFactory.html)
- [Reactor Netty — HTTP Server Reference](https://projectreactor.io/docs/netty/1.1.24/reference/html/#http-server)
- [Reactor Netty — DisposableChannel Javadoc](https://projectreactor.io/docs/netty/1.1.24/api/reactor/netty/DisposableChannel.html)
- [Reactor Netty — HttpResources Javadoc](https://projectreactor.io/docs/netty/1.1.24/api/reactor/netty/http/HttpResources.html)

**Ghi nhớ:** `ApplicationContext` quản lý vòng đời bean; server quản lý listener và kết nối inbound; `ReactorResourceFactory` quản lý event loop và connection resources dùng chung. Khi shutdown, dừng traffic mới, drain request đang chạy, rồi mới dispose tài nguyên mạng mà chúng phụ thuộc.
