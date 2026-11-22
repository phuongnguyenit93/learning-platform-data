# Đóng tài nguyên mạng tùy biến và tránh tạo pool cho mỗi yêu cầu trong Spring WebClient

## 1. Vấn đề: HTTP client cũng sở hữu tài nguyên dài hạn

Một request WebClient nhìn từ code thường rất ngắn:

~~~java
webClient.get()
    .uri("/users/42")
    .retrieve()
    .bodyToMono(User.class);
~~~

Nhưng phía dưới, một HTTP client reactive có thể sử dụng nhiều tài nguyên sống lâu hơn một request:

- **Connection pool:** giữ và tái sử dụng các TCP connection tới remote host.
- **Event loop:** các thread xử lý I/O non-blocking.
- **DNS resolver:** thực hiện phân giải hostname.
- **TLS resources:** hỗ trợ handshake và mã hóa kết nối.
- **Executor hoặc scheduler:** chạy tác vụ nền của HTTP client.
- **Buffer pool:** quản lý vùng nhớ phục vụ đọc/ghi bytes.
- **HTTP client/connector:** cấu hình và điều phối các tài nguyên trên.

Các tài nguyên này được tạo để phục vụ nhiều request. Một connection được trả lại pool sau khi response được tiêu thụ xong và có thể được request tiếp theo sử dụng.

Lỗi thiết kế phổ biến là tạo một \`ConnectionProvider\`, \`HttpClient\` hoặc \`WebClient\` mới trong mỗi lần gọi service, rồi bỏ quên việc đóng tài nguyên. Kết quả có thể là quá nhiều pool, event loop, socket và thread; connection không được tái sử dụng; ứng dụng tăng memory, file descriptor và thời gian handshake.

**Nguyên tắc:** tạo HTTP client và pool ở phạm vi ứng dụng hoặc phạm vi downstream service, tái sử dụng chúng qua nhiều request, rồi để Spring quản lý vòng đời tài nguyên. Chỉ tạo pool riêng khi có lý do cô lập hoặc cấu hình riêng rõ ràng.

## 2. Phân biệt WebClient, ClientHttpConnector, HttpClient và ConnectionProvider

Các lớp này có trách nhiệm khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| \`WebClient\` | API cấp ứng dụng để xây dựng và thực hiện HTTP request |
| \`WebClient.Builder\` | Cấu hình WebClient trước khi build |
| \`ClientHttpConnector\` | Cầu nối giữa WebClient và thư viện HTTP client cụ thể |
| \`ReactorClientHttpConnector\` | Connector tích hợp Reactor Netty với WebClient |
| Reactor Netty \`HttpClient\` | Cấu hình request, TLS, timeout, protocol và các hành vi client |
| \`ConnectionProvider\` | Quản lý pool, acquisition và tái sử dụng connection |
| \`LoopResources\` | Quản lý event-loop resources của Reactor Netty |
| \`ReactorResourceFactory\` | Quản lý LoopResources và ConnectionProvider theo vòng đời Spring ApplicationContext |

Mô hình:

~~~text
Service / Controller
        |
        v
Reusable WebClient
        |
        v
ClientHttpConnector
        |
        v
ReactorClientHttpConnector
        |
        v
Reactor Netty HttpClient
        |
        +-------------------------+
        |                         |
        v                         v
ConnectionProvider          LoopResources
        |                         |
        v                         v
Connection pool             Event-loop threads
        |                         |
        +------------+------------+
                     |
                     v
              Network / Remote API
~~~

\`WebClient\` không đồng nghĩa với một TCP connection. Một WebClient có thể sử dụng pool chứa nhiều connection tới một hoặc nhiều remote host. Nhiều WebClient cũng có thể dùng chung connector hoặc resource factory.

## 3. Pool được tái sử dụng như thế nào?

Khi dùng Reactor Netty, \`HttpClient.create()\` mặc định tham gia vào global resources trong \`HttpResources\`. Các resources này bao gồm event loop và connection pool dùng chung.

Luồng thông thường:

1. Request cần kết nối tới một remote host.
2. \`ConnectionProvider\` tìm connection rảnh trong pool của host đó.
3. Nếu có connection phù hợp, request sử dụng lại connection.
4. Nếu chưa có và pool còn chỗ, client mở connection mới.
5. Nếu pool đã đạt giới hạn, request có thể chờ trong pending-acquire queue.
6. Khi response được đọc hết hoặc release đúng cách, connection có thể được trả lại pool.
7. Request tiếp theo tới cùng host có thể tái sử dụng connection đó.

Pool được tổ chức theo remote host, thường dựa trên hostname và port. Một pool có thể có nhiều connection; connection không bị đóng ngay sau mỗi response thành công.

Việc tái sử dụng giúp giảm TCP connection establishment, TLS handshake, chi phí tạo/hủy socket, số lượng file descriptor đang mở và áp lực lên event loop.

### WebClient mới có luôn đồng nghĩa pool mới?

Không nhất thiết. Nếu nhiều WebClient sử dụng Reactor Netty global resources, chúng có thể chia sẻ pool toàn cục. Tuy nhiên, tạo WebClient trong từng request vẫn làm tăng allocation và dễ dẫn tới cấu hình resource sai khi ứng dụng thêm connector hoặc provider riêng.

Vấn đề nghiêm trọng nhất là **tạo ConnectionProvider hoặc LoopResources mới trong mỗi request**. Mỗi provider có thể tạo một pool riêng, khiến các request không còn chia sẻ connection với nhau.

## 4. Dùng WebClient.Builder do Spring Boot cung cấp

Trong Spring Boot WebFlux, nên inject \`WebClient.Builder\` đã được auto-configure:

~~~java
@Service
public class UserClient {

    private final WebClient webClient;

    public UserClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://api.example.com")
            .build();
    }

    public Mono<User> findUser(String id) {
        return webClient.get()
            .uri("/users/{id}", id)
            .retrieve()
            .bodyToMono(User.class);
    }
}
~~~

Spring Boot cung cấp builder được cấu hình sẵn để chia sẻ HTTP resources và codec setup theo cách tương thích với server. Khi sử dụng Reactor Netty cho cả server và client, resources có thể được chia sẻ.

Cách tổ chức nên dùng:

- Build WebClient một lần trong constructor hoặc bean configuration.
- Giữ WebClient trong một singleton service.
- Mỗi method chỉ tạo request specification và thực hiện request.
- Dùng cùng WebClient cho nhiều request tới cùng downstream.
- Nếu cần nhiều client, build nhiều WebClient từ builder nhưng giữ nguyên resource sharing nếu có thể.

\`WebClient\` sau khi build là immutable, phù hợp để tái sử dụng. \`WebClient.Builder\` có trạng thái cấu hình; đừng sửa cùng một builder đồng thời từ nhiều request. Nếu cần các biến thể cấu hình, dùng \`builder.clone()\` hoặc cấu hình riêng lúc khởi tạo.

### Một bean WebClient dùng chung

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://api.example.com")
            .build();
    }
}
~~~

Service nhận bean đó qua constructor:

~~~java
@Service
public class PartnerService {

    private final WebClient partnerWebClient;

    public PartnerService(WebClient partnerWebClient) {
        this.partnerWebClient = partnerWebClient;
    }

    public Mono<String> status() {
        return partnerWebClient.get()
            .uri("/health")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Không cần tự tạo một pool cho mỗi lần gọi \`status()\`.

## 5. Anti-pattern: tạo pool mới cho mỗi request

Ví dụ dưới đây minh họa lỗi thiết kế:

~~~java
public Mono<String> callPartner() {
    ConnectionProvider provider =
        ConnectionProvider.builder("per-request").build();

    HttpClient httpClient = HttpClient.create(provider);

    WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://api.example.com")
        .build();

    return client.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Mỗi lần gọi method:

- Một \`ConnectionProvider\` mới được tạo.
- Một pool mới được tạo thay vì tái sử dụng pool cũ.
- WebClient và connector mới được tạo.
- Nếu không dispose provider, tài nguyên có thể tồn tại lâu hơn dự kiến.
- Nếu dispose provider sau mỗi request, pool không còn cơ hội tái sử dụng connection giữa các request.

Ngay cả khi thêm \`doFinally(signal -> provider.dispose())\`, việc tạo và hủy pool cho từng request vẫn gây overhead và làm mất lợi ích của pooling.

### Phân biệt tạo WebClient mới và tạo pool mới

Tạo WebClient mới không tự động tạo pool mới nếu nó dùng chung global resources. Nhưng việc tạo WebClient liên tục vẫn là allocation không cần thiết và làm code khó quản lý.

Tạo một \`ConnectionProvider\` mới là hành động trực tiếp tạo resource pool mới. Tạo \`LoopResources\` mới còn có thể tạo thêm event-loop threads.

Hãy tạo những resource này tại startup hoặc khi cấu hình downstream, sau đó tái sử dụng.

## 6. Khi nào dùng global Reactor Netty resources?

Đây là lựa chọn mặc định phù hợp với phần lớn ứng dụng:

~~~java
HttpClient httpClient = HttpClient.create();

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
~~~

\`HttpClient.create()\` tham gia global Reactor Netty resources, gồm event loop và connection pool. Đây là chế độ được Spring Framework khuyến nghị vì resources dùng chung giúp event-loop concurrency ổn định.

Ưu điểm:

- Không phải tự quản lý provider cho mỗi WebClient.
- Nhiều client có thể chia sẻ global resources.
- Connection pool được tái sử dụng.
- Không phải tự đóng global resources sau mỗi request.
- Phù hợp với ứng dụng có vòng đời trùng với process.

Global resources thường tồn tại đến khi process kết thúc. Nếu ứng dụng có thể start/stop nhiều lần trong cùng JVM, ví dụ môi trường nhúng hoặc container Spring được tạo và đóng nhiều lần, cần tích hợp lifecycle để resources được đóng khi ApplicationContext kết thúc.

**Không gọi \`HttpResources.disposeLoopsAndConnections()\` tùy tiện.** Thao tác đó có thể đóng resources mà nhiều Reactor Netty client/server khác đang sử dụng.

## 7. ReactorResourceFactory quản lý lifecycle trong Spring

\`ReactorResourceFactory\` là Spring-managed resource factory cho Reactor Netty. Nó quản lý:

- \`LoopResources\`: event-loop threads.
- \`ConnectionProvider\`: connection pool.
- Thời gian chờ shutdown.
- Khởi động và dừng resources theo \`ApplicationContext\`.

Class này triển khai \`SmartLifecycle\`, \`InitializingBean\` và \`DisposableBean\`. Vì vậy, khi được khai báo thành Spring bean, lifecycle của resources có thể được quản lý cùng ứng dụng.

### Quản lý global resources

Nếu muốn dùng global resources nhưng cần gắn shutdown với ApplicationContext:

~~~java
@Configuration(proxyBeanMethods = false)
public class ReactorResourceConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        return new ReactorResourceFactory();
    }
}
~~~

Mặc định \`useGlobalResources\` là \`true\`. Factory sẽ quản lý việc khởi tạo và dừng global Reactor Netty resources theo vòng đời Spring.

Trong ứng dụng Spring Boot WebFlux thông thường, Boot đã cấu hình HTTP resources và WebClient.Builder để chia sẻ. Hãy kiểm tra cấu hình hiện có trước khi tự đăng ký factory khác.

### Quản lý resources độc lập

Nếu cần pool riêng hoặc muốn tách vòng đời client khỏi global resources:

~~~java
@Bean
ReactorResourceFactory reactorResourceFactory() {
    ReactorResourceFactory factory = new ReactorResourceFactory();
    factory.setUseGlobalResources(false);
    return factory;
}
~~~

Khi \`useGlobalResources=false\`, factory tự quản lý resources riêng. Ứng dụng phải bảo đảm tất cả client/server cần dùng bộ resources này đều được cấu hình nhất quán.

Không tạo một factory mới cho mỗi request. Factory là bean cấp ứng dụng hoặc một đơn vị hạ tầng có vòng đời rõ ràng.

## 8. Cấu hình ConnectionProvider tùy biến

Khi cần kiểm soát số connection, thời gian chờ hoặc tuổi connection, có thể tạo provider riêng:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("partner-api")
        .maxConnections(40)
        .pendingAcquireMaxCount(80)
        .pendingAcquireTimeout(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .evictInBackground(Duration.ofSeconds(60))
        .build();
~~~

Các cấu hình:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| \`maxConnections\` | Số connection tối đa trong một pool |
| \`pendingAcquireMaxCount\` | Số yêu cầu tối đa được chờ khi pool chưa cấp được connection |
| \`pendingAcquireTimeout\` | Thời gian chờ tối đa để lấy connection từ pool |
| \`maxIdleTime\` | Thời gian connection được phép nằm idle |
| \`maxLifeTime\` | Tuổi thọ tối đa của connection |
| \`evictInBackground\` | Chu kỳ kiểm tra và loại bỏ connection hết điều kiện sử dụng |

### maxConnections

Giới hạn số connection hoạt động trong pool. Giá trị cần cân bằng mức đồng thời dự kiến, giới hạn connection của downstream, latency, số host mà ứng dụng gọi và tài nguyên socket/file descriptor của process.

Đặt giá trị quá thấp có thể tạo nhiều pending request và timeout. Đặt quá cao có thể gây quá tải downstream hoặc tăng số connection không cần thiết.

### pendingAcquireMaxCount và pendingAcquireTimeout

Khi pool đã đầy, request mới có thể phải chờ connection được trả về.

- \`pendingAcquireMaxCount\` giới hạn hàng đợi.
- \`pendingAcquireTimeout\` giới hạn thời gian chờ.

Nếu hàng đợi không giới hạn, tải tăng đột biến có thể làm nhiều request chờ cùng lúc và giữ nhiều trạng thái trong memory. Hãy đặt giới hạn phù hợp với SLA.

### maxIdleTime và maxLifeTime

- \`maxIdleTime\` giới hạn thời gian connection không được sử dụng.
- \`maxLifeTime\` giới hạn tổng tuổi connection, kể cả khi connection vẫn được tái sử dụng.

Khi đặt \`maxIdleTime\`, nên chọn giá trị bằng hoặc nhỏ hơn idle timeout của server đích. Điều này giảm khả năng client lấy lại một connection mà server đã chủ động đóng.

### evictInBackground

Pool có thể kiểm tra connection định kỳ để loại bỏ những connection không còn phù hợp. Chu kỳ eviction cần cân bằng giữa khả năng dọn dẹp và chi phí kiểm tra.

Không nên đặt các timeout quá ngắn một cách tùy tiện vì có thể làm connection bị đóng và mở liên tục, gây thêm TCP/TLS handshake.

## 9. Đưa custom ConnectionProvider vào ReactorResourceFactory

Nếu ứng dụng cần pool riêng, hãy để factory quản lý provider:

~~~java
@Bean
ReactorResourceFactory reactorResourceFactory() {
    ReactorResourceFactory factory = new ReactorResourceFactory();

    factory.setUseGlobalResources(false);

    factory.setConnectionProviderSupplier(() ->
        ConnectionProvider.builder("partner-api")
            .maxConnections(40)
            .pendingAcquireMaxCount(80)
            .pendingAcquireTimeout(Duration.ofSeconds(5))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(60))
            .build()
    );

    factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
    factory.setShutdownTimeout(Duration.ofSeconds(15));

    return factory;
}
~~~

Điểm quan trọng:

- Phải đặt \`setUseGlobalResources(false)\` nếu muốn factory quản lý resources độc lập.
- \`setConnectionProviderSupplier\` tạo provider trong lifecycle của factory.
- Supplier chỉ tạo provider khi resources cần được khởi tạo, không chạy cho từng HTTP request.
- Spring gọi lifecycle stop khi ApplicationContext đóng.
- Không gọi \`dispose()\` hoặc \`disposeLater()\` thủ công trên provider mà factory đang sở hữu.

Theo Javadoc Spring Framework 6.2, supplier tùy biến cho ConnectionProvider bị bỏ qua khi factory vẫn dùng global resources hoặc khi một provider đã được đặt trực tiếp.

## 10. Kết nối custom resource factory với WebClient

Spring Framework hỗ trợ constructor của \`ReactorClientHttpConnector\` nhận \`ReactorResourceFactory\` và một function để tùy biến \`HttpClient\`.

~~~java
@Bean
WebClient partnerWebClient(
        WebClient.Builder builder,
        ReactorResourceFactory reactorResourceFactory) {

    Function<HttpClient, HttpClient> mapper = httpClient ->
        httpClient
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
            .responseTimeout(Duration.ofSeconds(10));

    ClientHttpConnector connector =
        new ReactorClientHttpConnector(
            reactorResourceFactory,
            mapper
        );

    return builder
        .baseUrl("https://api.example.com")
        .clientConnector(connector)
        .build();
}
~~~

Ở đây:

- Factory sở hữu pool và event-loop resources.
- Mapper bổ sung timeout cho Reactor Netty HttpClient.
- Connector nối HttpClient với WebClient.
- WebClient được build một lần thành bean.
- Các request sau sử dụng cùng client và cùng pool.

Nếu dùng Spring Boot, có thể tiếp tục inject \`WebClient.Builder\` để giữ codec và các cấu hình Boot. Khi cung cấp custom \`ReactorResourceFactory\`, cần hiểu factory có thể ảnh hưởng cả Reactor Netty server lẫn client của ứng dụng.

## 11. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ tạo một WebClient gọi JSONPlaceholder:

- Dùng Spring Boot 3.5.0 và Java 17+.
- Dùng một \`ReactorResourceFactory\` bean.
- Dùng một custom ConnectionProvider giới hạn 40 connection.
- Dùng một WebClient singleton.
- Các request tới downstream tái sử dụng pool.
- Spring quản lý shutdown của resource factory.

Cấu trúc:

~~~text
webclient-resource-lifecycle/
├── pom.xml
└── src/main/
    ├── java/com/example/resources/
    │   ├── ResourceLifecycleApplication.java
    │   ├── HttpClientConfiguration.java
    │   ├── PartnerService.java
    │   └── PartnerController.java
    └── resources/
        └── application.properties
~~~

File \`pom.xml\`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-resource-lifecycle</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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
~~~

File \`src/main/java/com/example/resources/ResourceLifecycleApplication.java\`:

~~~java
package com.example.resources;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceLifecycleApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/resources/HttpClientConfiguration.java\`:

~~~java
package com.example.resources;

import java.time.Duration;
import java.util.function.Function;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ReactorClientHttpConnector;
import org.springframework.http.client.ReactorResourceFactory;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        factory.setUseGlobalResources(false);

        factory.setConnectionProviderSupplier(() ->
            ConnectionProvider.builder("partner-api")
                .maxConnections(40)
                .pendingAcquireMaxCount(80)
                .pendingAcquireTimeout(Duration.ofSeconds(5))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .evictInBackground(Duration.ofSeconds(60))
                .build()
        );

        factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
        factory.setShutdownTimeout(Duration.ofSeconds(15));

        return factory;
    }

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory reactorResourceFactory) {

        Function<HttpClient, HttpClient> mapper = httpClient ->
            httpClient
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                .responseTimeout(Duration.ofSeconds(10));

        ClientHttpConnector connector =
            new ReactorClientHttpConnector(
                reactorResourceFactory,
                mapper
            );

        return builder
            .baseUrl("https://jsonplaceholder.typicode.com")
            .clientConnector(connector)
            .build();
    }
}
~~~

File \`src/main/java/com/example/resources/PartnerService.java\`:

~~~java
package com.example.resources;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class PartnerService {

    public record PartnerUser(
        long id,
        String name,
        String username,
        String email
    ) {}

    private final WebClient partnerWebClient;

    public PartnerService(WebClient partnerWebClient) {
        this.partnerWebClient = partnerWebClient;
    }

    public Mono<PartnerUser> findUser(long id) {
        return partnerWebClient.get()
            .uri("/users/{id}", id)
            .retrieve()
            .bodyToMono(PartnerUser.class);
    }
}
~~~

File \`src/main/java/com/example/resources/PartnerController.java\`:

~~~java
package com.example.resources;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/partner")
public class PartnerController {

    private final PartnerService partnerService;

    public PartnerController(PartnerService partnerService) {
        this.partnerService = partnerService;
    }

    @GetMapping("/users/{id}")
    public Mono<PartnerService.PartnerUser> getUser(
            @PathVariable long id) {
        return partnerService.findUser(id);
    }
}
~~~

File \`src/main/resources/application.properties\`:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Chạy từ thư mục dự án với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/api/partner/users/1
~~~

Response dự kiến có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "id": 1,
  "name": "Leanne Graham",
  "username": "Bret",
  "email": "Sincere@april.biz"
}
~~~

Gọi endpoint nhiều lần sẽ tiếp tục sử dụng cùng WebClient bean và cùng ConnectionProvider. Connection cụ thể có thể được tái sử dụng nếu còn hợp lệ, không bị server đóng và response trước đã được tiêu thụ hoàn tất.

Đây là ví dụ kết nối tới dịch vụ demo bên ngoài; khi chạy cần có mạng và dịch vụ JSONPlaceholder khả dụng.

## 12. Cấu hình timeout đúng tầng

Không có một timeout duy nhất phù hợp cho mọi tình huống. Reactor Netty có các timeout ở những giai đoạn khác nhau:

| Timeout | Kiểm soát | API thường dùng |
| --- | --- | --- |
| Pool acquire timeout | Thời gian chờ lấy connection từ pool | \`pendingAcquireTimeout\` |
| Connect timeout | Thời gian thiết lập TCP connection | \`CONNECT_TIMEOUT_MILLIS\` |
| Response timeout | Khoảng thời gian chờ giữa các thao tác đọc response theo cấu hình Reactor Netty | \`HttpClient.responseTimeout\` |
| Read timeout | Thời gian không có dữ liệu đọc theo handler cấu hình | \`ReadTimeoutHandler\` |
| Write timeout | Thời gian không có hoạt động ghi theo handler cấu hình | \`WriteTimeoutHandler\` |
| Reactive deadline | Giới hạn thời gian của publisher/operation ở tầng Reactor | \`Mono.timeout\` hoặc \`Flux.timeout\` |

### Connect timeout

~~~java
HttpClient client = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000);
~~~

Nếu TCP connection không được thiết lập trong 5 giây, thao tác kết nối thất bại.

### Response timeout

~~~java
HttpClient client = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(10));
~~~

Timeout này thuộc tầng HTTP client. Với response stream dài, cần chọn giá trị phù hợp với khoảng thời gian chờ dữ liệu giữa các lần đọc; không xem nó là thời gian tối đa cho toàn bộ vòng đời của mọi stream.

### Read/write timeout

~~~java
HttpClient client = HttpClient.create()
    .doOnConnected(connection -> connection
        .addHandlerLast(new ReadTimeoutHandler(10))
        .addHandlerLast(new WriteTimeoutHandler(10)));
~~~

Các handler này có phạm vi hoạt động ở connection và có thể ảnh hưởng stream lâu dài. Đừng đặt timeout ngắn nếu API có response body hoặc upload được phép idle lâu.

### Reactive timeout

~~~java
return partnerWebClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .bodyToMono(PartnerService.PartnerUser.class)
    .timeout(Duration.ofSeconds(15));
~~~

\`Mono.timeout\` giới hạn thời gian của publisher mà nó bao quanh. Nó không thay thế việc cấu hình pool acquire, TCP connect hay response I/O timeout cụ thể.

## 13. Connection pool không thay thế việc tiêu thụ response body

Connection chỉ có thể được tái sử dụng sau khi response được xử lý phù hợp. Nếu ứng dụng nhận \`ClientResponse\` rồi bỏ qua body mà không tiêu thụ hoặc release, connection/buffer có thể bị giữ lâu hơn dự kiến.

Cách thông thường với \`retrieve()\`:

~~~java
Mono<User> user = webClient.get()
    .uri("/users/42")
    .retrieve()
    .bodyToMono(User.class);
~~~

Khi endpoint không có response body:

~~~java
Mono<Void> result = webClient.delete()
    .uri("/users/42")
    .retrieve()
    .toBodilessEntity()
    .then();
~~~

Khi dùng \`exchangeToMono()\`, hãy đọc body hoặc release rõ ràng:

~~~java
Mono<Void> result = webClient.get()
    .uri("/health")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.releaseBody();
        }
        return response.createError();
    });
~~~

Không giữ response body hoặc \`DataBuffer\` lâu hơn cần thiết. Nếu client cancel giữa lúc đọc response, connection có thể bị đóng thay vì trả lại pool; đó là hành vi cần thiết để bảo vệ tính toàn vẹn của connection.

## 14. Đóng ConnectionProvider khi nào?

Có hai trường hợp sở hữu tài nguyên khác nhau.

### Provider dùng chung do Reactor Netty quản lý

Nếu dùng \`HttpClient.create()\` với global resources, không dispose provider sau mỗi request. Resources có thể đang được nhiều client/server dùng chung.

Chỉ thành phần sở hữu vòng đời global resources mới được dừng chúng, thường là khi process kết thúc hoặc khi Spring-managed resource factory đóng ApplicationContext.

### Provider tùy biến do ứng dụng tự tạo

\`ConnectionProvider\` có các API:

- \`dispose()\`: bắt đầu disposal theo kiểu fire-and-forget.
- \`disposeLater()\`: trả về \`Mono<Void>\` để quan sát quá trình disposal; cần subscribe để kích hoạt.
- \`disposeWhen(remoteAddress)\`: yêu cầu disposal pool cho một remote address nếu implementation hỗ trợ.

Ví dụ standalone, không nằm trong controller/event loop:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("standalone-client")
        .maxConnections(20)
        .build();

HttpClient httpClient = HttpClient.create(provider);

// Thực hiện các request cần thiết tại đây.

provider.disposeLater().block();
~~~

\`block()\` ở đây chỉ minh họa chương trình standalone chờ shutdown trên thread điều phối thông thường. Không gọi \`block()\` trên event-loop hoặc trong reactive controller.

Trong Spring application, ưu tiên để \`ReactorResourceFactory\` quản lý provider. Không vừa để factory sở hữu provider vừa tự dispose nó ở một bean khác.

## 15. Graceful shutdown và vòng đời ApplicationContext

Khi ứng dụng dừng, cần cho các request đang chạy một khoảng thời gian hoàn tất trước khi đóng network resources.

Spring Boot hỗ trợ graceful shutdown cho embedded web servers. Có thể cấu hình thời gian chờ mỗi lifecycle phase:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Trong ReactorResourceFactory, có hai cấu hình riêng:

- \`setShutdownQuietPeriod(Duration)\`: thời gian yên lặng trước khi dừng LoopResources; nếu có task mới trong khoảng này, thời gian yên lặng được tính lại.
- \`setShutdownTimeout(Duration)\`: thời gian tối đa chờ việc dispose resources hoàn tất.

Ví dụ:

~~~java
factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
factory.setShutdownTimeout(Duration.ofSeconds(15));
~~~

Đây là hai lớp liên quan nhưng khác nhau:

- Graceful shutdown của server giúp request inbound đang chạy có thời gian hoàn tất.
- Shutdown của ReactorResourceFactory dừng client pool và event-loop resources do factory quản lý.

Không đóng pool ngay khi bắt đầu shutdown nếu còn request outbound đang dùng nó. Để Spring lifecycle điều phối thứ tự dừng các thành phần.

Sau khi resource factory stop/restart, factory có thể tạo instance LoopResources và ConnectionProvider mới. Không giữ reference tới provider cũ rồi tiếp tục dùng sau khi lifecycle đã restart.

## 16. Khi dùng connector khác Reactor Netty

WebClient có thể dùng nhiều HTTP client implementation. Mỗi loại có resource lifecycle riêng:

| Connector | Resource chính | Cách quản lý |
| --- | --- | --- |
| Reactor Netty | ConnectionProvider, LoopResources | Global HttpResources hoặc ReactorResourceFactory |
| Jetty Reactive HttpClient | Executor, ByteBufferPool, Scheduler và HttpClient | JettyResourceFactory hoặc lifecycle start/stop |
| Apache HttpComponents | CloseableHttpAsyncClient và connection manager | Start/close theo lifecycle của client |
| JDK HttpClient | HttpClient và executor tùy biến | Quản lý executor nếu ứng dụng tự cung cấp |

### Jetty

Jetty \`HttpClient\` có thể tự tạo Executor, ByteBufferPool và Scheduler. Nếu nhiều client cần chia sẻ resources hoặc cần đóng chúng khi ApplicationContext kết thúc, dùng \`JettyResourceFactory\` với \`JettyClientHttpConnector\`.

### Apache HttpComponents

Khi tự tạo \`CloseableHttpAsyncClient\`, phải start và close nó theo vòng đời ứng dụng. Đừng tạo một async client/connection manager mới cho từng request.

### JDK HttpClient

Nếu cung cấp một Executor riêng cho JDK HttpClient, hãy quản lý executor đó như resource của ứng dụng. Không tạo executor hoặc thread pool mới trong mỗi lần gọi WebClient.

**Nguyên tắc chung:** hiểu ai tạo resource, ai chia sẻ resource, ai sở hữu resource và ai chịu trách nhiệm đóng resource.

## 17. Giám sát connection pool

Khi bật Micrometer metrics cho Reactor Netty pool, có thể theo dõi các metric như:

| Metric | Ý nghĩa |
| --- | --- |
| \`reactor.netty.connection.provider.total.connections\` | Tổng số connection active và idle |
| \`reactor.netty.connection.provider.active.connections\` | Số connection đang được sử dụng |
| \`reactor.netty.connection.provider.idle.connections\` | Số connection rảnh trong pool |
| \`reactor.netty.connection.provider.pending.connections\` | Số request đang chờ connection |
| \`reactor.netty.connection.provider.max.connections\` | Giới hạn connection |
| \`reactor.netty.connection.provider.pending.connections.time\` | Thời gian chờ acquire connection |

Có thể bật metrics trong provider khi ứng dụng có Micrometer:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("partner-api")
        .maxConnections(40)
        .metrics(true)
        .build();
~~~

Với Spring Boot, có thể thêm \`spring-boot-starter-actuator\` để tích hợp Micrometer và xuất metrics theo hệ thống monitoring đã chọn.

Các dấu hiệu cần quan sát:

- Pending connections tăng liên tục: pool có thể quá nhỏ hoặc downstream phản hồi chậm.
- Active connections thường xuyên chạm max: cần kiểm tra concurrency và thời gian giữ response body.
- Idle connections cao nhưng không giảm: xem lại idle eviction và nhu cầu pool.
- Pool acquire timeout tăng: có thể do connection không được release, downstream quá chậm hoặc pool không đủ.
- Total connections tăng bất thường theo số request: kiểm tra có tạo nhiều provider/pool không.

Không chỉ tăng maxConnections khi thấy pending queue. Trước tiên xác định bottleneck ở downstream, response consumption, concurrency hay pool configuration.

## 18. Những lỗi thường gặp

1. **Tạo ConnectionProvider trong controller:** mỗi request có thể tạo pool riêng. Tạo provider ở application configuration và tái sử dụng.
2. **Không dispose custom provider:** pool, connection và resource có thể tồn tại sau khi không còn cần. Để Spring quản lý bằng ReactorResourceFactory hoặc dispose tại lifecycle shutdown.
3. **Dispose provider sau mỗi request:** phá hủy lợi ích pooling và gây connection/TLS handshake liên tục.
4. **Gọi global HttpResources.disposeLoopsAndConnections khi còn client khác dùng:** làm các client/server dùng chung resources mất khả năng hoạt động.
5. **Nhầm tạo WebClient mới với tạo pool mới:** WebClient mới có thể vẫn dùng global pool; provider/LoopResources mới mới tạo resource pool riêng.
6. **Gọi WebClient.Builder.build() trong mỗi method:** tạo object/configuration lặp lại và dễ dẫn tới connector riêng. Build một client bean hoặc field dùng chung.
7. **Dùng ConnectionProvider.newConnection() cho traffic thông thường:** mỗi acquisition mở connection mới, không tận dụng pooling.
8. **Đặt maxConnections quá cao:** có thể làm downstream hoặc hệ điều hành quá tải.
9. **Không giới hạn pendingAcquireMaxCount:** hàng đợi có thể tăng quá mức khi downstream chậm.
10. **pendingAcquireTimeout quá dài:** request có thể chờ lâu và chiếm tài nguyên. Chọn theo SLA.
11. **maxIdleTime lớn hơn idle timeout của server:** client có thể lấy lại connection đã bị server đóng.
12. **maxIdleTime quá thấp:** connection bị đóng/mở liên tục, làm tăng handshake và latency.
13. **Không cấu hình maxLifeTime cho connection lâu sống:** một số hạ tầng trung gian có thể yêu cầu luân chuyển connection định kỳ.
14. **Nhầm pool acquire timeout với connect timeout:** một bên chờ slot trong pool, một bên chờ TCP handshake.
15. **Nhầm responseTimeout với tổng request deadline:** response timeout thuộc I/O response; dùng reactive timeout nếu cần deadline toàn operation.
16. **Đặt ReadTimeoutHandler quá ngắn cho stream:** response hoặc upload hợp lệ có thể bị đóng khi idle.
17. **Không tiêu thụ hoặc release response body:** connection có thể không được trả lại pool đúng thời điểm.
18. **Tạo provider và connector nhưng không gắn Spring lifecycle:** ApplicationContext đóng mà resource tùy biến vẫn tồn tại.
19. **Để factory dùng global resources nhưng kỳ vọng custom provider supplier được áp dụng:** supplier tùy biến bị bỏ qua khi global resources vẫn bật.
20. **Đăng ký nhiều ReactorResourceFactory không có chủ đích:** có thể tạo nhiều bộ resources và khó xác định client/server đang dùng bộ nào.
21. **Giữ reference tới provider sau lifecycle restart:** factory có thể tạo instance mới; reference cũ không còn hợp lệ.
22. **Dùng block() để chờ dispose trong event-loop:** có thể deadlock hoặc làm nghẽn I/O. Để lifecycle reactive quản lý shutdown.
23. **Retry request không idempotent khi connection lỗi:** server có thể đã xử lý request trước khi client nhận lỗi; cần idempotency key và retry policy rõ ràng.
24. **Chỉ kiểm tra số WebClient mà không kiểm tra số ConnectionProvider:** nhiều WebClient có thể dùng chung pool; hãy theo dõi metric và nơi tạo provider.
25. **Không kiểm thử shutdown:** resource có thể bị đóng quá sớm hoặc process không thoát vì thread/resource còn hoạt động.

## 19. Checklist trước khi triển khai

- WebClient được build ở application scope hay bị tạo lại trong mỗi request?
- Builder có được inject từ Spring Boot và dùng đúng cách không?
- Connector nào đang được sử dụng: Reactor Netty, Jetty, Apache hay JDK?
- HTTP client có đang dùng global resources hay custom resources?
- Có thực sự cần pool riêng hay pool mặc định đã đủ?
- Nếu custom pool, ConnectionProvider được tạo ở đâu và ai sở hữu nó?
- ConnectionProvider có giới hạn max connections và pending acquire không?
- Timeout acquire, connect, response và overall operation có được phân biệt không?
- maxIdleTime có phù hợp với idle timeout của downstream không?
- Response body có được consume hoặc release không?
- Có metrics active/idle/pending connections không?
- Có shutdown lifecycle cho provider, event loop, executor và client tùy biến không?
- Có tránh dispose global resources khi client khác vẫn đang dùng không?
- Có kiểm thử tải đồng thời và shutdown khi request còn chạy không?
- Có xác nhận số pool không tăng theo số request không?

## 20. Câu hỏi tự kiểm tra

**1.** ConnectionProvider dùng để làm gì? Quản lý pool connection và việc cấp phát/tái sử dụng connection cho HTTP client.

**2.** WebClient có phải một TCP connection không? Không. Nó là API client; connector và HTTP backend quản lý connection resources.

**3.** Vì sao không tạo ConnectionProvider trong mỗi request? Vì mỗi provider có thể tạo pool riêng, làm mất tái sử dụng và tăng socket/resource.

**4.** HttpClient.create() của Reactor Netty mặc định dùng resources nào? Global Reactor Netty HttpResources, bao gồm event loop và connection pool.

**5.** WebClient.Builder của Spring Boot có lợi ích gì? Được auto-configure để chia sẻ HTTP resources và codec configuration phù hợp.

**6.** ReactorResourceFactory quản lý gì? LoopResources và ConnectionProvider theo lifecycle của Spring ApplicationContext.

**7.** setUseGlobalResources(false) có ý nghĩa gì? Factory quản lý resources độc lập thay vì dùng global HttpResources.

**8.** Khi nào cần setConnectionProviderSupplier? Khi cần factory tạo ConnectionProvider tùy biến trong lifecycle của nó.

**9.** Có nên gọi provider.dispose() sau mỗi request không? Không. Việc đó phá pooling và làm mất khả năng tái sử dụng.

**10.** pendingAcquireTimeout khác connect timeout thế nào? Một bên chờ connection trong pool; bên kia chờ thiết lập TCP connection.

**11.** maxIdleTime nên được chọn thế nào? Bằng hoặc nhỏ hơn idle timeout của server đích để giảm stale connection.

**12.** Khi nào dùng ConnectionProvider.newConnection()? Khi cố ý muốn mỗi lần acquire tạo connection mới; không phù hợp với traffic thông thường cần pooling.

**13.** Khi dùng custom provider trong Spring, cách quản lý tốt là gì? Đưa provider vào ReactorResourceFactory và để Spring lifecycle đóng resources.

**14.** Có thể dispose global HttpResources trong một service bất kỳ không? Không. Thao tác đó ảnh hưởng mọi client/server đang dùng global resources.

**15.** Vì sao phải consume hoặc release response body? Để giải phóng buffer và cho phép connection được trả lại pool khi phù hợp.

**16.** ReactorResourceFactory có tự tạo resource mới sau lifecycle restart không? Có; reference tới resource cũ không nên tiếp tục được sử dụng.

**Ghi nhớ:** WebClient và connection pool là resource dài hạn. Dùng WebClient singleton được build từ builder Spring Boot; để Reactor Netty tái sử dụng global resources khi phù hợp. Nếu cần pool tùy biến, tạo ConnectionProvider ở application scope và để ReactorResourceFactory quản lý lifecycle. Không tạo hoặc dispose pool trong mỗi request. Cấu hình giới hạn pool, timeout đúng tầng, tiêu thụ response body và kiểm tra metrics/shutdown để tránh rò rỉ tài nguyên.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebClient Configuration and Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html)
- [Spring Framework 6.2 — ReactorResourceFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/ReactorResourceFactory.html)
- [Spring Framework 6.2 — ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html)
- [Spring Boot 3.5 — Calling REST Services and WebClient Runtime](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Reactor Netty — HTTP Client, Connection Pool and Disposal](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Reactor Netty — ConnectionProvider Javadoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/resources/ConnectionProvider.html).