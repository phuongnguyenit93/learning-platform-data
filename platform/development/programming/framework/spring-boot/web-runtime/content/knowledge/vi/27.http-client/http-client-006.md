# Kết nối HTTP dùng chung, connection pool và vòng đời tài nguyên client trong Spring Boot

## 1. Mục tiêu

Ứng dụng Spring Boot thường gọi HTTP ra ngoài để lấy thông tin sản phẩm, thanh toán, xác thực, tra cứu giá hoặc liên hệ một dịch vụ nội bộ. Một lời gọi HTTP không chỉ là `GET` rồi đọc JSON: phía dưới còn có **DNS, TCP, TLS, HTTP keep-alive, connection pool, hàng đợi chờ connection, timeout, luồng I/O và tài nguyên cần đóng**.

Nếu tạo một HTTP client mới cho mỗi request rồi không dọn tài nguyên, hệ thống có thể gặp:

- TCP/TLS handshakes lặp lại, latency và CPU cao, nhiều socket ở trạng thái `TIME_WAIT`.
- Connection pools phân mảnh, vượt giới hạn socket và file descriptors, cạn tài nguyên máy hoặc upstream.
- Connection bị giữ không trả về pool do response body/stream không được đọc, hủy hoặc đóng đúng cách.
- Pending acquires tăng, request chờ pool, timeout dây chuyền khi lưu lượng cao.
- Background threads, event loops và idle connections không được giải phóng khi ứng dụng/test context kết thúc.
- Dữ liệu user/token/cookie của request A rò sang request B nếu client dùng chung nhưng lại giữ **mutable request-specific state** không đúng chỗ.

Bài này giúp bạn:

1. Phân biệt **dùng chung HTTP client** với **dùng chung một TCP connection**; hiểu việc kết nối có thể được tái sử dụng mà không được bảo đảm.
2. Chọn Spring `RestClient`/`WebClient` và HTTP transport phù hợp với **MVC blocking** hoặc **WebFlux non-blocking**.
3. Tạo **một client và pool có vòng đời ứng dụng**, không tạo pool mới trong mỗi method.
4. Thiết lập giới hạn pool, timeout, eviction và cơ chế shutdown có **owner** rõ ràng.
5. Đọc/đóng response body đúng để trả lại hoặc hủy connection; tránh thread blocking trên event loop.
6. Kiểm thử bằng **HTTP server cục bộ** và quan sát pool thực tế, phân biệt những gì test chứng minh với việc TCP socket thật sự được tái sử dụng.

Phạm vi chính: **Spring Boot 3.5.x, Spring Framework 6.2, Java 17+, Spring MVC, Apache HttpClient 5**. Một ví dụ độc lập với **WebClient/Reactor Netty** và lưu ý JDK HTTP client được trình bày sau. Các phiên bản Spring Boot 4.x có tổ chức auto-configuration và API tùy chỉnh mới; không chép nguyên import/cấu hình của Boot 3.5.x mà không đối chiếu tài liệu phiên bản triển khai.

> **Nguyên tắc:** dùng client/pool **lâu dài ở phạm vi ứng dụng**, nhưng request, headers nhạy cảm, body và response stream **chỉ thuộc lời gọi hiện tại**.

## 2. Một request HTTP đi qua những lớp nào?

Sơ đồ giản lược:

```text
Controller/Service trong Spring Boot
           |
           | RestClient hoặc WebClient (giao diện lập trình)
           v
ClientHttpRequestFactory / ClientHttpConnector
           |
           | HTTP engine (Apache HC5, Reactor Netty, JDK HttpClient...)
           v
Connection manager / ConnectionProvider
   |          |           |
   | idle     | leased    | pending
   v          v           v
TCP/TLS socket(s)  <--- request chờ connection
           |
           v
   API Gateway / Proxy / Upstream
           |
           v
      HTTP response
           |
           v
Consume/decode hoặc cancel/close response body
           |
           v
Connection đủ điều kiện -> trả về pool
Connection không an toàn/đã đóng -> loại bỏ
```

**Cần phân biệt ba đối tượng:**

- **HTTP client object** (`RestClient`, `WebClient`, Apache `CloseableHttpClient`, JDK `HttpClient`): cấu hình dùng để gửi nhiều request. Có thể tạo nhiều request spec từ một client.
- **Connection pool/manager:** giữ và cấp phát các kết nối vật lý theo remote endpoint/route; kiểm soát số lượng kết nối hoạt động, rỗi và số request chờ.
- **HTTP request/response:** có vòng đời ngắn; body, headers và data buffers cần được tiêu thụ/đóng/hủy đúng. Không dùng chung một đối tượng request đang mutable giữa các user.

**Dùng chung client không có nghĩa mọi request đi cùng một socket.** Client có thể mở nhiều connection vì concurrency, khác host/port/proxy/TLS route, keep-alive timeout, server đóng socket, HTTP/2 multiplexing hoặc chính sách pool. Đổi lại, việc cùng một pool **cho phép** reuse để tránh setup mới khi có socket phù hợp.

## 3. HTTP keep-alive, TCP keepalive, pooling và HTTP/2 khác nhau

| Cơ chế | Công dụng | Điều không bảo đảm |
| --- | --- | --- |
| HTTP persistent connection / keep-alive | Cho nhiều HTTP exchanges đi qua cùng một kết nối khi giao thức/peer cho phép | Không bắt buộc socket tồn tại vô hạn |
| Connection pool | Quản lý nhiều kết nối và cấp phát lại cho các request phù hợp | Không tự động bảo đảm cân bằng tải hoặc không có leak |
| TCP `SO_KEEPALIVE` | Probe mạng mức TCP khi socket idle lâu theo OS | Không thay cho HTTP timeout/pool idle eviction |
| HTTP/1.1 | Thường một request đang sử dụng một connection trong một thời điểm (không tính pipelining hiếm dùng) | Không có HTTP/2 multiplexing |
| HTTP/2 | Nhiều streams trên một connection theo giới hạn peer | Không có nghĩa luôn chỉ một connection; server giới hạn concurrent streams |
| TLS session resumption | Có thể giảm chi phí handshake mới | Không thay thế reuse TCP connection |

Ví dụ 100 request **nối tiếp** tới cùng host qua một client có thể dùng lại ít connection; 100 request **đồng thời** tới một host có thể cần nhiều connection trong HTTP/1.1. Với HTTP/2, nhiều stream có thể cùng socket, nên không ước lượng pool size chỉ bằng số request đang xử lý.

Connection đang **leased/active** được client sử dụng. Connection **idle/available** được trả về pool để request khác mượn. **Pending** là số yêu cầu chờ được cấp connection khi chạm giới hạn. Ngay cả khi request đã kết thúc ở controller, connection có thể chưa trả về pool nếu consumer chưa hoàn tất body hoặc response stream còn được giữ.

## 4. Chọn client cho ứng dụng

| Lựa chọn | Kiểu API | Transport và quản lý tài nguyên | Khi nào hợp lý |
| --- | --- | --- | --- |
| Spring `RestClient` | Imperative/blocking | Dựa vào `ClientHttpRequestFactory`, có thể dùng Apache HC5, JDK HttpClient... | Spring MVC, code đồng bộ, virtual threads hoặc service đồng bộ |
| Spring `WebClient` | Reactive/non-blocking | Dựa vào `ClientHttpConnector`, thông dụng là Reactor Netty | WebFlux, xử lý reactive và stream/backpressure |
| `RestTemplate` | Imperative, API cũ | Cũng dùng `ClientHttpRequestFactory` | Bảo trì code cũ; dự án mới cân nhắc `RestClient` |
| JDK `java.net.http.HttpClient` | Sync `send` và async `sendAsync` | Transport của JDK có khả năng tái sử dụng connection | Không cần abstraction của Spring hoặc cần JDK-only |
| Apache HttpClient 5 trực tiếp | Classic/blocking hoặc async stack riêng | `PoolingHttpClientConnectionManager` và cấu hình chi tiết | Khi cần điều khiển thấp, pool metric/route và timeout rõ |

Spring Boot cung cấp **`RestClient.Builder`/`WebClient.Builder` đã được auto-configure** với converters/customizers phù hợp; nên inject builder rồi **build client một lần** trong bean có vòng đời dài. Builder là **mutable/stateful**; không dùng một builder đang thay đổi cho nhiều request đồng thời. Client sau khi build được thiết kế cho nhiều lời gọi đồng thời, còn request spec tạo từ client nên coi là riêng từng request.

**Không nhầm “Bean singleton” với “pool duy nhất toàn JVM”:** có thể có nhiều `RestClient` dùng chung một underlying `CloseableHttpClient` và pool; cũng có thể có hai `RestClient`, mỗi cái tạo một Apache client khác nhau và do đó có **hai pools**. Điều quan trọng là **ai thực sự sở hữu transport và pool**, không chỉ tên bean ở tầng Spring.

### 4.1. Anti-pattern: dựng client trong mỗi HTTP request

```java
// ANTI-PATTERN — minh họa, không dùng trong sản phẩm:
@GetMapping("/catalog")
String catalog() {
    RestClient client = RestClient.create();
    return client.get()
            .uri("https://partner.example.org/catalog")
            .retrieve()
            .body(String.class);
}
```

Đoạn này là snippet (cần lớp controller/import), và cách dùng factory ngầm của `RestClient.create()` phụ thuộc framework/classpath; **không kết luận mọi lần gọi đều chắc chắn tạo TCP socket mới**. Tuy nhiên, tạo client mới tại điểm nóng làm vòng đời/config/observability khó kiểm soát, có nguy cơ tạo underlying transport/pool dư thừa và làm mất cơ hội reuse. Chuyển client thành bean cố định, tạo request spec mới trong method.

### 4.2. Anti-pattern: đóng client sau từng lời gọi

```java
// Không làm thế này với transport được toàn ứng dụng chia sẻ:
try (CloseableHttpClient client = HttpClients.createDefault()) {
    // execute một request ...
}
```

`try-with-resources` phù hợp nếu ứng dụng **chủ ý tạo một transport dùng một lần**, không phù hợp với yêu cầu pool reuse. Với client dài hạn, **Spring ApplicationContext hoặc bean owner** phải đóng nó **một lần khi ngừng phục vụ**, không phải mỗi request.

## 5. Cấu hình pool: các giới hạn và timeout cần tách riêng

Một pool thường có những cấu hình sau:

| Tham số | Nghĩa | Triệu chứng nếu đặt sai |
| --- | --- | --- |
| `maxTotal` / `maxConnections` | Tổng số connections pool quản lý (phạm vi cụ thể theo implementation) | Quá nhỏ -> pending; quá lớn -> socket/upstream overload |
| `maxPerRoute` | Giới hạn connection tới một route/host qua Apache HC5 | Một upstream nóng chiếm hết pool hoặc bị nghẽn |
| `connectionRequestTimeout` / `pendingAcquireTimeout` | Chờ **mượn connection từ pool** tối đa bao lâu | Thiếu giới hạn -> queue, latency kéo dài |
| `connectTimeout` | Chờ thiết lập TCP connection | Upstream không route được -> request treo ở connect |
| `responseTimeout` / `readTimeout` | Chờ phản hồi/đọc dữ liệu tùy transport semantics | Upstream chậm -> giữ connection quá lâu |
| `maxIdleTime` | Giới hạn thời gian connection có thể idle trong pool | Socket stale bị phía server/LB đóng |
| `maxLifeTime` / TTL | Giới hạn vòng đời socket kể cả có lưu lượng | Giảm stale connections, cân bằng đời sống connection |
| `pendingAcquireMaxCount` | Số request tối đa chờ pool (Reactor Netty) | Queue không giới hạn -> memory/latency tăng |
| eviction/validation | Dọn connection hết hạn, hỏng, idle | Idle sockets cũ tích tụ hoặc tái dùng lỗi |
| concurrency / backpressure | Giới hạn số outgoing requests cùng lúc | Pool lớn không đủ khi downstream quá tải |

**Ba loại timeout hay bị nhầm:**

1. **Acquire timeout:** thời gian request xếp hàng **trước khi có connection**.
2. **Connect timeout:** thời gian mở network connection mới.
3. **Response/read timeout:** thời gian chờ dữ liệu sau khi connection đã có, theo semantics của thư viện.

**Không timeout nào đơn lẻ luôn là “thời gian tối đa end-to-end”**. Một business deadline có thể phải bao gồm DNS, acquire, connect, TLS, redirect, response body, retry và processing. Trong Reactor, toán tử `timeout(Duration)` có thể giúp giới hạn publisher theo ngữ nghĩa Reactive Streams nhưng không thay thế cấu hình network timeout cụ thể.

### 5.1. Ước lượng pool size, đừng lấy số mặc định làm SLA

Một heuristic ban đầu dựa trên Little's law:

```text
số outbound requests đồng thời ≈ throughput (request/s) × latency (s)
```

Ví dụ 100 requests/s và latency trung bình 0,2 giây gợi ý khoảng **20 requests đồng thời** trong điều kiện ổn định, chưa tính burst, retry, tail latency và multiplexing. Pool HTTP/1.1 đến host cụ thể có thể bắt đầu gần mức concurrency cần thiết, rồi đo; HTTP/2 phân bổ theo stream nên điều chỉnh khác.

- Giới hạn per-host/route và tổng không giống nhau; nếu gọi ba upstream độc lập, tổng phải xét toàn bộ lưu lượng.
- Một `maxConnections=500` không phải bảo chứng về throughput và cũng không nhất thiết đúng ở phiên bản Reactor Netty khác.
- Cần đo **active, idle, pending, pending wait, connect errors, TLS errors, p95/p99 duration** trước và sau thay đổi.
- Đặt queue hữu hạn; queue quá dài có thể khiến request hết deadline trước khi đến lượt mượn socket.
- Chọn idle timeout không vượt đáng kể idle timeout của load balancer/upstream nếu muốn hạn chế reuse socket đã bị đóng.
- Không dùng retry vô hạn để “chữa” pool saturation; retry có thể làm tăng tải và gây thundering herd.

## 6. Ví dụ chạy được: Spring Boot MVC + RestClient + Apache HttpClient 5

Ví dụ sử dụng **Spring Boot 3.5.16** (bản có thật trên Maven Central), **Java 17**, Spring MVC, `RestClient` và một `CloseableHttpClient` Apache dùng chung. Pool được tạo **một lần**; client được **Spring gọi `close()` khi ApplicationContext đóng**.

**Giới hạn phiên bản:** Spring Boot 3.5.16 là bản cuối của dòng 3.5.x được phát hành theo hỗ trợ OSS; đây là mốc **để tái lập ví dụ Spring Framework 6.2**. Với dự án production mới, chọn **nhánh Spring Boot còn được OSS hỗ trợ**, cập nhật bản vá và điều chỉnh import/API theo version tương ứng (ví dụ Boot 4.1.x). Không đưa một bản hết hỗ trợ ra sản phẩm chỉ vì bài thực hành dùng bản đó.

Ứng dụng có:

- `GET /upstream/hello/{name}`: upstream giả lập chạy cùng process, nhằm demo chạy local không cần Internet.
- `GET /demo/hello/{name}`: endpoint gọi upstream qua **RestClient bean dùng chung** và trả JSON.
- `CloseableHttpClient` tự sở hữu một `PoolingHttpClientConnectionManager`; không tạo pool trong mỗi request.
- Một test chạy HTTP server giả lập **cổng ngẫu nhiên riêng**, để chứng minh outgoing client thực sự gửi HTTP và nhận response, không phụ thuộc port 8080.

### 6.1. Cấu trúc dự án

```text
shared-http-client-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ SharedClientApplication.java
   │  │  ├─ OutboundClientConfiguration.java
   │  │  ├─ UpstreamGateway.java
   │  │  ├─ GatewayController.java
   │  │  └─ LocalUpstreamController.java
   │  └─ resources/application.properties
   └─ test/
      └─ java/com/example/demo/
         └─ SharedClientIntegrationTest.java
```

### 6.2. Maven dependencies

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>shared-http-client-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.httpcomponents.client5</groupId>
            <artifactId>httpclient5</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Spring Boot BOM quản lý version tương thích của `httpclient5`; không tự thêm version Apache HC5 khác tùy hứng. Cần Maven 3.6.3+ hoặc Maven Wrapper và JDK 17+.

### 6.3. Application properties

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Demo local gọi một endpoint trong chính ứng dụng.
# Production dùng HTTPS URL upstream được phép theo cấu hình.
demo.upstream-base-url=http://127.0.0.1:8080
```

`demo.upstream-base-url` là **application configuration do operator kiểm soát**, không được lấy nguyên từ query parameter client; nếu không sẽ có rủi ro SSRF. Khi chuyển sang môi trường test, giá trị này sẽ được override bằng cổng ngẫu nhiên của test HTTP server.

### 6.4. Main class

**`src/main/java/com/example/demo/SharedClientApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SharedClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(SharedClientApplication.class, args);
    }
}
```

### 6.5. Chỉ một transport và một pool, đóng khi context shutdown

**`src/main/java/com/example/demo/OutboundClientConfiguration.java`**

```java
package com.example.demo;

import java.time.Duration;

import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class OutboundClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient sharedApacheHttpClient() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofSeconds(2))
            .setSocketTimeout(Timeout.ofSeconds(5))
            .setTimeToLive(TimeValue.ofMinutes(2))
            .build();

        PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(24)
                .setMaxConnPerRoute(8)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

        // Client sở hữu manager; khi client.close(), pool và
        // các tài nguyên liên quan của client cũng được giải phóng.
        return HttpClients.custom()
            .setConnectionManager(manager)
            .evictExpiredConnections()
            .build();
    }

    @Bean
    RestClient sharedRestClient(
            RestClient.Builder builder,
            CloseableHttpClient sharedApacheHttpClient,
            @Value("${demo.upstream-base-url}") String upstreamBaseUrl) {

        var factory = new HttpComponentsClientHttpRequestFactory(
            sharedApacheHttpClient
        );

        // Timeout chờ mượn connection từ pool.
        factory.setConnectionRequestTimeout(Duration.ofSeconds(2));
        // Timeout phản hồi theo semantics Apache/Spring request factory.
        factory.setReadTimeout(Duration.ofSeconds(5));

        return builder
            .requestFactory(factory)
            .baseUrl(upstreamBaseUrl)
            .build();
    }
}
```

**Giải thích ownership thật kỹ:**

1. Spring tạo `CloseableHttpClient` bean **một lần** (singleton mặc định). Method này tạo **một `PoolingHttpClientConnectionManager`** rồi giao cho Apache client quản lý.
2. Apache `HttpClients.custom().setConnectionManager(manager)` mặc định **không** cấu hình connection manager thành shared với nhiều Apache clients không liên quan. Theo mô hình này **Apache client là owner của manager**.
3. `@Bean(destroyMethod="close")` chỉ định Spring gọi `CloseableHttpClient.close()` khi bean bị hủy cùng `ApplicationContext`; không gọi `close()` trong mỗi service method.
4. `evictExpiredConnections()` dùng background eviction do Apache client quản lý; khi client đóng, task liên quan cũng phải được dọn. Không giữ application context sống vô hạn trong test không cần thiết.
5. `RestClient.Builder` được Spring Boot cung cấp với converters và customizers. Ta chỉ định rõ `HttpComponentsClientHttpRequestFactory` để chắc chắn `RestClient` dùng đúng Apache client/pool; không dựa hoàn toàn vào thứ tự auto-detect theo classpath.
6. `RestClient` đã build là client có thể dùng qua nhiều thread; **không** mutate cùng builder giữa các HTTP requests.
7. Factory ở đây **không** là bean/destroy-owner riêng, nên trách nhiệm đóng Apache client đặt tại **một bean duy nhất**. Tránh tự đăng ký thêm destroy hook gọi `close` hai lần trên cùng transport.
8. `24` tổng connection và `8` trên một route chỉ là **giá trị minh họa**, không phải recommendation mặc định cho mọi ứng dụng. Cần đo concurrency/latency/upstream limits.
9. `ConnectionConfig.setConnectTimeout` là timeout TCP connect; `setSocketTimeout` ảnh hưởng socket I/O; `setReadTimeout` trên Spring 6.2 factory cấu hình response timeout của request; `setConnectionRequestTimeout` là chờ lease từ pool. Các mức này không nên được coi là một end-to-end SLA chung.
10. Chúng ta không ghi access token hoặc cookie dùng chung làm default header trên singleton. Những thứ thuộc user/request phải được thêm vào **request riêng** theo phương thức an toàn.

**Vì sao không tạo `PoolingHttpClientConnectionManager` thành bean thứ hai?** Để không tạo hai owner cùng đóng một pool. Nếu muốn expose pool manager để lấy `getTotalStats()`, hãy thiết kế ownership rõ: manager bean sống ở cấp application, Apache client dùng `setConnectionManagerShared(true)` và bean manager được hủy **sau** client; hoặc dùng một bean wrapper sở hữu cả hai. Đừng vừa để Apache client tự đóng manager vừa cho Spring đóng manager thêm mà không hiểu lifecycle.

### 6.6. Service dùng lại RestClient, tạo request spec mới mỗi lần

**`src/main/java/com/example/demo/UpstreamGateway.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class UpstreamGateway {

    private final RestClient client;

    public UpstreamGateway(RestClient sharedRestClient) {
        this.client = sharedRestClient;
    }

    public Greeting hello(String name) {
        return client.get()
            .uri("/upstream/hello/{name}", name)
            .retrieve()
            .body(Greeting.class);
    }

    public record Greeting(String message) {}
}
```

Khi gọi `hello("An")`, `client.get()` tạo **request spec mới**. `RestClient` và underlying pool là các đối tượng dùng lại, không phải HTTP response body hay request state.

`retrieve().body(Greeting.class)` đọc/decode phản hồi trong vòng đời request qua Spring message converters. Đối với mã 4xx/5xx, `retrieve()` mặc định xử lý bằng exception phù hợp; không tự xem 404 upstream là 200 hoặc nuốt lỗi và trả dữ liệu giả. Trong production, nên ánh xạ lỗi upstream sang trạng thái service của mình theo policy có chủ đích, log ở mức an toàn, không làm lộ URL/token nội bộ.

### 6.7. Controller gọi upstream qua client dùng chung

**`src/main/java/com/example/demo/GatewayController.java`**

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GatewayController {

    private final UpstreamGateway gateway;

    public GatewayController(UpstreamGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/demo/hello/{name}")
    public UpstreamGateway.Greeting hello(@PathVariable String name) {
        return gateway.hello(name);
    }
}
```

Vì đây là Spring MVC, request thread **có thể block** trong `RestClient`; điều đó đúng với kiểu lập trình này khi sizing thread pool và timeout hợp lý. Nếu dùng **WebFlux/Netty event loop**, **không** gọi `RestClient` blocking trên event loop; thay bằng `WebClient`/non-blocking pipeline hoặc offload có kiểm soát.

### 6.8. Upstream local giả lập, chỉ dùng để thực hành

**`src/main/java/com/example/demo/LocalUpstreamController.java`**

```java
package com.example.demo;

import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class LocalUpstreamController {

    private static final Set<String> KNOWN_NAMES = Set.of("An", "Binh");

    @GetMapping("/upstream/hello/{name}")
    public UpstreamGateway.Greeting hello(@PathVariable String name) {
        if (!KNOWN_NAMES.contains(name)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new UpstreamGateway.Greeting("Hello " + name);
    }
}
```

Trong demo, `/demo/hello/An` gọi HTTP tới `127.0.0.1:8080/upstream/hello/An` và lấy lại JSON. Cả hai endpoint chạy trong một ứng dụng chỉ nhằm giữ ví dụ tự chạy được **không cần upstream bên ngoài**. Production sẽ sử dụng service khác tại URL cấu hình an toàn và có giới hạn quyền/truy cập mạng.

Không copy mô hình **self-call qua HTTP** để thay các lời gọi Java nội bộ trong sản phẩm: nó tạo thêm socket, chờ pool, serialization và nguy cơ deadlock/starvation nếu request concurrency bị giới hạn. Trong thực tế, client dùng để gọi **remote service**; local self-call chỉ là một bài tập quan sát transport.

### 6.9. Chạy ứng dụng và xem kết quả

Trong thư mục có Maven:

```bash
java -version
mvn spring-boot:run
```

Hoặc `./mvnw spring-boot:run` nếu project được tạo với Maven Wrapper (Windows: `mvnw.cmd spring-boot:run`). Với `server.port=8080`, đảm bảo port chưa bị chiếm.

Ở terminal khác:

```bash
curl -i http://127.0.0.1:8080/upstream/hello/An
curl -i http://127.0.0.1:8080/demo/hello/An
curl -i http://127.0.0.1:8080/demo/hello/Binh
```

Các response **thành công được kỳ vọng** có status 200 và JSON field `message` lần lượt `"Hello An"`, `"Hello An"`, `"Hello Binh"`. Không giả định thứ tự header hoặc formatting JSON cố định. Request thứ hai có thể dùng lại một connection ở pool nếu socket còn đủ điều kiện; bài thực hành **không tuyên bố chắc chắn** vì request HTTP không cam kết TCP reuse.

Thử gửi nhiều request nối tiếp:

```bash
for n in 1 2 3 4 5; do
  curl -s http://127.0.0.1:8080/demo/hello/An
  echo
done
```

Lưu ý: mỗi lần chạy `curl` ở đây là một process/client riêng ở phía **đầu vào**, nhưng ứng dụng vẫn dùng cùng `RestClient` và pool khi gọi upstream. Để xem connection phía outbound, hãy đo **phía ứng dụng/upstream** hoặc pool metrics, không chỉ đếm TCP sockets của curl tới port 8080.

## 7. Kiểm thử tích hợp không phụ thuộc Internet và không trói vào port 8080

Với `spring-boot-starter-test`, ta có thể dùng `MockMvc` cho inbound MVC, đồng thời dựng **HTTP server thật trên loopback** bằng JDK `com.sun.net.httpserver.HttpServer` để nhận outbound HTTP do Apache client gửi.

Vì server test chọn cổng ngẫu nhiên, `@DynamicPropertySource` cung cấp `demo.upstream-base-url` trước khi Spring tạo `RestClient` bean. Test này **không** chỉ mock transport layer, nên xác nhận được RestClient, Apache engine, HTTP request/response serialization và kết quả decode. Tuy nhiên, nó **chưa chứng minh một socket cụ thể đã được reuse**, vì server có thể đóng keep-alive hoặc pool chủ động mở socket mới.

**`src/test/java/com/example/demo/SharedClientIntegrationTest.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpServer;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SharedClientIntegrationTest {

    private static final HttpServer STUB = startStub();

    @Autowired
    MockMvc mvc;

    @Autowired
    UpstreamGateway gateway;

    @Autowired
    RestClient sharedRestClient;

    @Autowired
    CloseableHttpClient sharedApacheHttpClient;

    @Autowired
    ApplicationContext context;

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0
            );

            server.createContext("/upstream/hello/", exchange -> {
                String path = exchange.getRequestURI().getPath();
                String name = path.substring(
                    "/upstream/hello/".length()
                );

                if (!name.equals("An") && !name.equals("Binh")) {
                    exchange.sendResponseHeaders(404, -1);
                    exchange.close();
                    return;
                }

                byte[] body = (
                    "{\"message\":\"Hello " + name + "\"}"
                ).getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type", "application/json"
                );
                exchange.sendResponseHeaders(200, body.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(body);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Could not start local HTTP test server", ex
            );
        }
    }

    @DynamicPropertySource
    static void upstreamEndpoint(DynamicPropertyRegistry registry) {
        registry.add(
            "demo.upstream-base-url",
            () -> "http://127.0.0.1:" + STUB.getAddress().getPort()
        );
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    @Test
    void gatewayFetchesDataViaRealHttpTransport() throws Exception {
        mvc.perform(get("/demo/hello/An"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello An"));

        mvc.perform(get("/demo/hello/Binh"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello Binh"));
    }

    @Test
    void transportAndRestClientAreSharedSpringBeans() {
        assertSame(
            sharedRestClient,
            context.getBean(RestClient.class)
        );
        assertSame(
            sharedApacheHttpClient,
            context.getBean(CloseableHttpClient.class)
        );
    }

    @Test
    void sequentialCallsCanReuseSameConfiguredPool() {
        for (int i = 0; i < 5; i++) {
            UpstreamGateway.Greeting result = gateway.hello("An");
            org.junit.jupiter.api.Assertions.assertEquals(
                "Hello An", result.message()
            );
        }
    }

    @Test
    void upstream404RemainsAnError() {
        assertThrows(
            HttpClientErrorException.NotFound.class,
            () -> gateway.hello("missing")
        );
    }
}
```

Chạy:

```bash
mvn test
```

Với đúng Maven dependencies và các file Java ở trên, **bốn test được kỳ vọng pass**. Đây là kết quả thiết kế để người học tự chạy; **không phải tuyên bố đã biên dịch hoặc thực thi trong một repository thực tế**.

**Điểm giới hạn cần ghi nhớ:**

- Test `sharedBeans` chứng minh Spring inject **cùng instance** `RestClient`/`CloseableHttpClient`, không chứng minh request A và B dùng cùng một TCP socket.
- Test nối tiếp xác nhận nhiều calls thành công qua cùng cấu hình transport; không ép assert về số socket vì `HttpServer`/pool có thể quyết định close hoặc reuse theo HTTP headers và phiên bản.
- `HttpServer` chạy ngoài Spring context trong static fixture test, được stop ở `@AfterAll`. Apache client bean thuộc Spring context; Spring đóng client bằng destroy method khi context shutdown. **Không tự đóng Apache client ở `@AfterAll`**, vì Spring Test có thể cache application context cho test khác.
- Server stub chỉ bind `127.0.0.1` với cổng ngẫu nhiên; không nhận kết nối từ mạng ngoài.
- Không dùng `MockRestServiceServer` để chứng minh TCP pooling; mock request factory có thể kiểm tra HTTP semantics nhưng **không chạy socket/pool thật**.
- Test 404 kiểm tra `RestClient.retrieve()` giữ lỗi downstream có ý nghĩa; application production phải ánh xạ lỗi theo policy rõ, không tự trả luôn 404 của upstream cho mọi endpoint.

### 7.1. Làm thế nào kiểm chứng connection reuse thật?

**Đừng khẳng định từ hai HTTP 200**. Nếu mục tiêu là kiểm chứng reuse, cần một công cụ có thể quan sát **connection identity**:

- Bật instrumentation/pool metrics của Apache hoặc Reactor Netty và theo dõi active/available/leased, acquisition và creation rates.
- Capture TCP connections bằng công cụ được phép trên môi trường test (Wireshark/tcpdump, socket stats) và đối chiếu local source port, remote tuple, connect events. Không coi port trong response HTML là một định danh đáng tin.
- Gắn connection IDs ở upstream test server hoặc dùng access logs có connection key, lưu ý reverse proxy có thể thay TCP connection.
- Test dưới tải đồng thời và dưới idle timeout, không chỉ năm request nối tiếp. Pool mới có thể mở nhiều socket hợp lệ; “số socket = 1” không phải assert đúng chung cho mọi transport/protocol.
- Đo connection creation, pending waits, idle/leased ratio và tail latency. Nếu pool đúng nhưng server gửi `Connection: close`, socket sẽ không được giữ để reuse.
- Dùng benchmark có giới hạn concurrency và warm-up; tách CPU/tải upstream khỏi overhead TCP/TLS setup. Không bật pool vô hạn chỉ để latency đẹp trên localhost.

## 8. Vòng đời chuẩn: tạo một lần, sử dụng nhiều lần, đóng một lần

### 8.1. Lifecycle trong Spring

```text
ApplicationContext startup
   |
   +--> tạo pool/connection manager
   +--> tạo HTTP engine
   +--> build RestClient/WebClient bean
   +--> inject vào service(s)
                |
                v
       nhiều request song song
       - tạo request spec riêng
       - lease/multiplex connection
       - consume/cancel body đúng
       - trả/hủy connection
                |
                v
Application shutdown
   |
   +--> ngừng tiếp nhận request (graceful shutdown nếu cấu hình)
   +--> chờ in-flight work theo chính sách
   +--> close/dispose transport và pool
   +--> dừng eviction threads/event loops do mình sở hữu
```

Điều cần tránh:

1. **Per-request client creation:** nhiều pools và idle sockets dư thừa.
2. **Per-request client close:** phá reuse và có thể làm hỏng các request đang dùng transport chung.
3. **Never close owned resources:** khi context/test bị tạo-hủy nhiều lần trong cùng JVM, event loops/threads/sockets có thể tích tụ.
4. **Double close hoặc close sai owner:** hai component cùng nghĩ mình là owner; một service shutdown làm toàn app mất khả năng HTTP.
5. **Không drain response body:** leased connection hoặc allocator bị giữ lâu hơn dự kiến.
6. **Giữ dữ liệu user trong singleton client default headers:** vô tình dùng token của user trước cho user sau.

### 8.2. Ai đóng resource trong một app nhiều context?

Một `@Bean(destroyMethod="close")` phù hợp khi tài nguyên **thuộc ApplicationContext đó**. Nếu một pool nằm ngoài Spring (được tạo ở static field hoặc thư viện/host sở hữu), không để một context con đóng shared pool mà context khác còn dùng. Đây là vấn đề quan trọng với:

- Spring MVC WAR chạy trong application server có thể deploy/undeploy nhiều lần.
- DevTools restart hoặc integration tests có nhiều contexts.
- Nhiều WebClient cùng dùng Reactor Netty global `HttpResources`.
- Nhiều Spring apps cùng chạy trong một JVM không độc lập tài nguyên.

Với Reactor Netty, **global resources không nên bị một service tùy tiện dispose** nếu client/server khác còn sử dụng. Cần chọn rõ **global managed resources** hoặc **custom owned provider/event loops** và shutdown theo scope của owner.

### 8.3. Graceful shutdown và in-flight requests

Spring Boot có cơ chế graceful shutdown cho web server, nhưng **closing outbound clients quá sớm** có thể cắt các outgoing calls mà request inbound đang chờ. Trong production:

- Thiết kế readiness/termination sequence, ngừng nhận traffic mới và cho phép in-flight work hoàn tất trong grace period.
- Timeout cần có hạn: một stream vô hạn không thể đợi shutdown mãi.
- Khi hết deadline, hủy request/cancel subscription/đóng response theo API transport.
- Không tạo một HTTP client mới trong `@PreDestroy` chỉ để “xử lý nốt” hàng đợi khi lifecycle đang kết thúc.
- Nếu có async background job hoặc scheduler dùng client, ngừng/await chúng trước khi giải phóng transport phụ thuộc.

Ví dụ không được dùng như một luật tuyệt đối: “Spring gọi `destroyMethod` nên mọi request chắc chắn đã xong”. Thứ tự bean dependencies và graceful shutdown cần được kiểm tra trong kiến trúc triển khai.

## 9. WebClient + Reactor Netty: dùng chung event loops và connection pool

Spring Boot có thể inject một `WebClient.Builder` đã cấu hình, thường với Reactor Netty khi starter WebFlux có mặt. Trong **WebFlux**, ưu tiên dùng non-blocking `Mono`/`Flux` xuyên suốt thay vì `.block()` trên Netty event loop.

### 9.1. Cách dùng đơn giản: dùng builder được Spring Boot quản lý

```java
// Snippet: ứng dụng có spring-boot-starter-webflux.
@Service
public class PartnerService {
    private final WebClient client;

    public PartnerService(WebClient.Builder builder) {
        this.client = builder
            .baseUrl("https://partner.example.org")
            .build();
    }

    public Mono<String> getStatus() {
        return client.get()
            .uri("/status")
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

Đây là snippet (cần import `Service`, `WebClient`, `Mono`), không phải class độc lập với build file. `WebClient.Builder` có thể được Boot inject dạng prototype; hãy cấu hình rồi build trong constructor, **không build mỗi lần gọi service method**.

Với Reactor Netty mặc định, các clients có thể tham gia **global `HttpResources`** chứa event loops và pool. Điều này được khuyến nghị để chia sẻ tài nguyên cố định cho event-loop concurrency; Spring Boot có cơ chế quản lý resources tùy stack/context. **Không** gọi `HttpResources.disposeLoopsAndConnections()` từ một request/service đơn lẻ, bởi mọi client dùng global resource đó có thể dừng hoạt động.

### 9.2. Khi cần custom pool có owner rõ ràng

Ví dụ dưới đây là **một biến thể cấu hình WebFlux riêng**, không đặt vào project MVC/Apache của phần 6 cùng lúc. Cần dependency `spring-boot-starter-webflux` và Reactor Netty tương ứng.

**`ReactiveOutboundConfiguration.java`**

```java
package com.example.reactive;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class ReactiveOutboundConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerPool() {
        return ConnectionProvider.builder("partner-http")
            .maxConnections(40)
            .pendingAcquireMaxCount(100)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(2))
            .build();
    }

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ConnectionProvider partnerPool) {

        HttpClient transport = HttpClient.create(partnerPool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
            .responseTimeout(Duration.ofSeconds(5));

        return builder
            .clientConnector(new ReactorClientHttpConnector(transport))
            .baseUrl("https://partner.example.org")
            .build();
    }
}
```

**Giải thích:**

- `partnerPool` là bean có owner (Spring context) và được `dispose()` khi context dừng. Một WebClient không tự tạo một pool mới cho mỗi request.
- `HttpClient.create(partnerPool)` dùng pool đã truyền. Nó có thể vẫn sử dụng **Reactor Netty event loop resources theo cấu hình mặc định**; **không xem dispose pool là đồng nghĩa dispose toàn bộ global event loops**.
- `maxConnections(40)` và `pendingAcquireMaxCount(100)` giới hạn concurrency/queue theo pool; đây chỉ là ví dụ, phải đo traffic thực tế.
- `pendingAcquireTimeout` khác `CONNECT_TIMEOUT_MILLIS` và `responseTimeout`.
- `maxIdleTime` nên cân nhắc timeout idle ở upstream/proxy.
- Chỉ tùy biến HTTP connector nếu cần. Thay connector thủ công có thể bỏ qua một số tích hợp auto-config như SSL bundles/observability/proxy hoặc các customizer khác; đối chiếu Spring Boot version và cấu hình tổng thể.
- **Không dùng bean pool này cho hai ứng dụng Spring contexts độc lập** rồi cho cả hai tự dispose cùng tài nguyên.
- Nếu muốn shutdown mềm cho connections đang bận, xem `ConnectionProvider.disposeLater(Duration)`/dispose semantics của phiên bản Reactor Netty thay vì chỉ gọi dispose tức thời không phân biệt.

**Không tự đặt default authentication token cá nhân** vào singleton WebClient:

```java
// ANTI-PATTERN: không lưu token của user A trong WebClient dùng cho user B.
WebClient userAClient = builder
    .defaultHeader("Authorization", "Bearer token-of-user-A")
    .build();
```

Token của từng request/user phải được lấy từ **security context thích hợp** và gắn vào request riêng, có kiểm soát tenant/permissions. Nếu dùng một credential **service-to-service** dùng chung thì thiết kế token provider/rotation riêng; không hardcode token trong source code hoặc leak qua log.

### 9.3. Response body và DataBuffer phải được quản lý đúng

Với WebClient, cách đơn giản:

```java
Mono<Greeting> result = client.get()
    .uri("/upstream/hello/{name}", name)
    .retrieve()
    .bodyToMono(Greeting.class);
```

`retrieve().bodyToMono(...)` decode/consume response theo cơ chế chuẩn. Nếu dùng `exchangeToMono`/`exchangeToFlux`, **phải quyết định cách xử lý body trong callback**; Spring WebClient hiện hành sẽ kiểm tra và **release body chưa được consume khi publisher callback hoàn tất** để tránh leak. Không trông chờ response còn giải mã được sau callback đã hoàn thành.

```java
Mono<String> result = client.get()
    .uri("/status")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        return response.createError();
    });
```

Đây là snippet, thiếu biến `client`. Nếu thao tác trực tiếp với `DataBuffer`, dùng `DataBufferUtils` và ownership contract phù hợp, release các pooled buffers khi tự tiêu thụ/hủy; đừng lưu `DataBuffer` sống vô hạn trong cache/singleton. Khi cancel một Flux, hệ thống cần phản hồi cancel và giải phóng body/connection; timeout hoặc circuit breaker nên được test cho cả nhánh hủy.

**Không gọi `.block()` trong Netty event loop**. Blocking có thể làm nghẽn threads phục vụ nhiều connections, kéo tail latency lên cao và tạo “pool starvation” trông như lỗi network. Nếu một thư viện bắt buộc blocking trong reactive pipeline, offload có kiểm soát bằng scheduler thích hợp và xác định quota; tốt nhất giữ chain non-blocking khi có thể.

## 10. JDK `java.net.http.HttpClient`: reuse và khác biệt Java 17/21

JDK có HTTP client riêng:

```java
// Snippet Java 17+ — tạo một lần trong configuration/service.
HttpClient httpClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();
```

Cần import `java.net.http.HttpClient` và `java.time.Duration`. JDK HTTP client có cơ chế quản lý connections/thread nội bộ và có thể reuse; nếu tạo nhiều client instances, chúng **không nhất thiết chia cùng pool**. Hãy share một instance theo lifetime thích hợp thay vì tạo `HttpClient.newHttpClient()` với mỗi request.

**Khác biệt quan trọng:**

- Với **Java 17**, `java.net.http.HttpClient` **chưa có** API `close()`/`shutdown()` như JDK 21. Không viết `try (HttpClient client = ...)` rồi đòi code biên dịch trên Java 17.
- Từ **JDK 21**, `HttpClient` có các API `close()`, `shutdown()`, `shutdownNow()` và `awaitTermination()`. Đóng client theo ownership và đảm bảo không còn request mới; không đóng mỗi request.
- Nếu dùng `BodyHandlers.ofInputStream()`, phải đọc stream đến EOF hoặc đóng đúng cách; không giữ stream mở vô hạn, nếu không request/close có thể bị kẹt.
- Nếu dùng `sendAsync`, cần xét cancellation và việc hoàn tất response body. Future hoàn tất với một response có body stream **không đồng nghĩa stream đã được consume**.
- JDK client không tự cung cấp cùng các knobs hoặc pool metrics như Apache HC5 hay Reactor Netty; đừng copy `maxConnTotal` từ Apache sang JDK mà không có API tương ứng.
- Spring `JdkClientHttpRequestFactory` có thể dùng JDK HttpClient bên dưới `RestClient`. Cấu hình ownership và timeout phụ thuộc phiên bản Spring/JDK cụ thể.

## 11. Đọc response body đúng để không giữ connection mãi

### 11.1. Đối với RestClient

Với phần lớn lời gọi JSON:

```java
Greeting value = restClient.get()
    .uri("/upstream/hello/{name}", "An")
    .retrieve()
    .body(Greeting.class);
```

Spring xử lý lifecycle response thông thường khi decode body trong `retrieve()`. Không cần tự lấy raw stream cho JSON nhỏ. Nếu cần **stream file lớn**, tránh đọc toàn bộ body vào `byte[]` chỉ để sau đó ghi ra đĩa.

`RestClient.exchange(...)` cho phép kiểm soát response trực tiếp. Hãy **đọc/copy body bên trong callback**, đừng trả về raw stream rồi dùng khi response đã được framework đóng:

```java
// Snippet: path phải do server quyết định, không lấy raw request path.
restClient.get()
    .uri("/export")
    .exchange((request, response) -> {
        if (!response.getStatusCode().is2xxSuccessful()) {
            throw new IllegalStateException(
                "Upstream export failed: " + response.getStatusCode()
            );
        }
        Files.copy(
            response.getBody(),
            Path.of("/tmp/downloaded-report.csv"),
            StandardCopyOption.REPLACE_EXISTING
        );
        return null;
    });
```

Đây là snippet trong method Java, cần import `Files`, `Path` và `StandardCopyOption`, kiểm tra quyền filesystem và xử lý `IOException`. Với file thực, cần temp file an toàn, giới hạn dung lượng, checksum/sanitization, cleanup, không ghi thẳng tên do client đưa và tránh overwrite tài liệu người khác. Callback `exchange` có semantics lỗi và status riêng, không mặc định áp dụng mọi status handler như `retrieve()`.

**Không làm:**

```java
// ANTI-PATTERN: trả stream ra ngoài lifecycle của response.
InputStream body = restClient.get().uri("/large")
    .exchange((request, response) -> response.getBody());
// Sau callback, stream có thể đã đóng/không còn hợp lệ.
```

Nếu underlying transport trả raw response tự quản lý bằng thư viện Apache trực tiếp, dùng try-with-resources/response handler theo API Apache để đóng response và entity stream, kể cả khi exception. Tránh trả status mà bỏ quên body không tiêu thụ nếu adapter yêu cầu release.

### 11.2. Đối với WebClient

`WebClient.retrieve().bodyToMono(...)` thường là lựa chọn an toàn cho một response hữu hạn. Với dữ liệu streaming, dùng `bodyToFlux(...)` hoặc `exchangeToFlux(...)`, và **subscribe/cancel** theo vòng đời nghiệp vụ. Nếu consumer không subscribe, không có HTTP request được thực thi trong mô hình lazy reactive thường gặp; nếu đã subscribe rồi dừng giữa chừng, phải hủy subscription đúng cách.

Giới hạn số byte có thể decode vào memory: payload quá lớn có thể làm Spring báo `DataBufferLimitException` hoặc áp lực heap/direct memory; pool leak không phải nguyên nhân duy nhất. Tách lỗi decode, timeout, saturation và cancellation bằng metrics/logs.

### 11.3. Body không được tiêu thụ có thể ảnh hưởng pool như thế nào?

Kết nối chỉ được trả về pool khi transport biết đã kết thúc vòng đời exchange, còn reusable và không chứa byte chưa được xử lý gây lẫn request tiếp theo. Tùy protocol/client, transport có thể:

- Đọc hết/drain body rồi giữ socket.
- Đóng socket và loại khỏi pool nếu body bị cancel sớm.
- Giữ connection leased chừng nào stream/raw response còn mở.
- Từ chối reuse khi server gửi `Connection: close` hoặc connection có lỗi framing/TLS.

**Không giả định “cancel là chắc chắn trả về idle ngay”**. Khi một response stream dài bị cancel, nó có thể hủy socket để đảm bảo ranh giới dữ liệu, hoặc duy trì HTTP/2 connection trong khi đóng một stream, tùy transport.

## 12. Connection pool có giới hạn: hiểu tình trạng chờ và timeout dây chuyền

Giả sử pool Apache cho một route chỉ có tối đa 8 connections, nhưng đồng thời có 30 HTTP/1.1 calls tới cùng upstream:

```text
30 outbound calls
       |
       v
8 connections leased -> 8 calls đang dùng
22 calls chờ pool (tùy giới hạn queue)
       |
       +--> Một call hoàn tất và trả connection
       |           -> call đang chờ tiếp theo được lease
       |
       +--> Chờ vượt connectionRequestTimeout
                   -> lỗi timeout khi xin connection
```

Không nên phản ứng bằng cách lập tức tăng pool từ 8 lên 800. Trước tiên kiểm tra:

- Upstream đang chậm hoặc có request bị treo không?
- Response body có được đọc/đóng không?
- Có request dài (SSE/streaming download) chiếm pool trong thời gian rất lâu không?
- Retry/circuit-breaker có tạo thêm traffic khi upstream lỗi không?
- Có quá nhiều ứng dụng/instances cùng dùng chung upstream không? Tổng connections trên toàn cluster có thể vượt quota.
- HTTP/2 multiplexing có đang bật và được cả hai đầu hỗ trợ không?
- Pool metrics active/idle/pending có khớp lượng traffic đo từ tracing không?

Trong tình huống quá tải, cân nhắc **bulkhead/concurrency limit**, queue hữu hạn, timeout phù hợp, fallback có chọn lọc và circuit breaker. Connection pool bảo vệ sockets, **không thay thế** quota/rate-limit của nghiệp vụ và không tự giải quyết upstream chậm.

## 13. Observability: cần đo những gì?

### 13.1. Bộ chỉ số có ý nghĩa

| Nhóm | Chỉ số hữu ích | Phân tích |
| --- | --- | --- |
| Pool | active/leased, idle/available, pending | Có đang hết connection hoặc không release? |
| Acquire | pending acquire duration và timeouts | Request chờ pool lâu hơn thời gian upstream xử lý? |
| Network | DNS, connect, TLS handshake errors/duration | Tắc nghẽn ở network hay DNS, không phải controller |
| HTTP | client-side request count, status 2xx/4xx/5xx | Tỉ lệ lỗi upstream, thay đổi khi deploy |
| Latency | p50/p95/p99 end-to-end, per route | Queue time và tail latency |
| Lifecycle | pool count, background threads, sockets khi shutdown | Leak khi app redeploy/test contexts |
| Resilience | timeout, retry, cancellation, circuit-open | Có retry storm hoặc body stream treo? |

Reactor Netty cung cấp metrics với prefix như:

```text
reactor.netty.connection.provider.total.connections
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.pending.connections.time
```

Các metrics này cần **bật instrumentation/phụ thuộc Micrometer** và cấu hình tag phù hợp; không mặc định chắc chắn mọi metric có mặt chỉ vì đã thêm Spring Boot Actuator. Cẩn thận cardinality khi gắn tag theo URL có ID, tenant hoặc host tùy ý.

Với Apache HC5, `PoolingHttpClientConnectionManager` có API `getTotalStats()` và `getStats(route)`; thống kê có thể cho biết available/leased/pending/max. Vì demo đã để manager do Apache client sở hữu, muốn expose metrics cần thiết kế một resource-owner bean hoặc instrumentation **không đổi vòng đời sở hữu**; đừng tự đóng manager để “reset metric”.

### 13.2. Dấu hiệu chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Ưu tiên kiểm tra |
| --- | --- | --- |
| Latency tăng, CPU không cao | Pending acquire, upstream slow | Pool pending + request duration + timeout |
| Active cao mãi dù request đã xong | Raw response/stream chưa đóng, SSE dài | Body consumption/cancellation, leased connections |
| Socket/TIME_WAIT tăng nhanh | Tạo client mới/không reuse, server đóng keep-alive | Bean lifecycle, connection creation rate, Connection headers |
| Memory/direct buffer cao | Client/pool dư, DataBuffer không release, payload lớn | Allocator, heap/direct memory, streaming logic |
| 502/503 sau idle period | Stale connection bị LB/server đóng | maxIdleTime, validation, idle timeout upstream |
| Test suite lâu dần/chưa thoát | Context/client/event-loop/background threads chưa đóng | @Bean destroyMethod, test resources, JDK async |
| 429/503 từ upstream dù pool còn chỗ | Upstream quota hoặc quá tải | Retry, concurrency, rate limiting và backoff |
| Chỉ lỗi dưới load, local vẫn ổn | Pool quá nhỏ hoặc upstream tail latency | Load test có kiểm soát, p95/p99, pending queue |
| Thay version Boot rồi pool behavior khác | Auto-detect transport hoặc defaults đổi | Dependency tree, configured request factory, runtime metrics |

## 14. An toàn bảo mật khi dùng shared client

### 14.1. Tránh rò credential giữa các request

Một singleton `RestClient`/`WebClient` được phép dùng lại **cấu hình transport**, nhưng dữ liệu cá nhân phải được đưa vào request một cách riêng biệt:

```java
// Snippet: token đã được lấy và kiểm tra từ nguồn đáng tin.
String result = client.get()
    .uri("/me")
    .headers(headers -> headers.setBearerAuth(tokenForThisRequest))
    .retrieve()
    .body(String.class);
```

Đây là snippet, biến `tokenForThisRequest` phải do auth/service layer cung cấp, không lấy raw từ request không kiểm tra. Không ghi token vào log hoặc metrics. Khi user A và user B gọi đồng thời, mỗi lời gọi phải có headers/body riêng, không dùng một mutable `HttpHeaders` singleton bị ghi qua lại.

Khi upstream cần **service credential dùng chung**, dùng token provider/cache bảo mật riêng có refresh/expiry và đồng bộ; không hardcode API key trong code, không truyền bearer token sang host khác nếu redirect bất ngờ.

### 14.2. SSRF và trusted destination

Không xây URL outbound tùy ý từ query như:

```java
// ANTI-PATTERN: client có thể ép server gọi vào mạng nội bộ/metadata.
client.get().uri(userProvidedUrl).retrieve().body(String.class);
```

`baseUrl` nên là service URL do operator kiểm soát; nếu nghiệp vụ buộc fetch URL ngoài, cần **allowlist scheme/host/port**, giới hạn redirect và DNS rebinding, egress firewall, không cho kết nối địa chỉ internal/metadata. Connection pooling không giúp chống SSRF; ngược lại một shared client có thể tái sử dụng auth header/proxy/credentials sai nếu cấu hình không tách route đúng.

### 14.3. TLS, proxy và cookie store

- Không tắt certificate validation/hostname verification chỉ để “cho connection pool hoạt động”.
- Nếu gọi qua HTTP proxy doanh nghiệp, cấu hình proxy/CONNECT và truststore theo hạ tầng. Pool có thể phân biệt route gồm cả proxy.
- Không dùng cookie store chia sẻ cho nhiều user/tenant nếu cookie thuộc identity người dùng; cookie trong HTTP client backend khác session cookie browser.
- Không log payload nhạy cảm hoặc `Authorization` trong wiretap/debug của Reactor Netty ở production.
- Cẩn thận cross-origin redirect: client có thể chuyển header nhạy cảm tới đích không mong muốn nếu thư viện/cấu hình tùy chỉnh xử lý sai. Định nghĩa redirect policy, allowlist target.
- Keep-alive/pooled connections không được coi là một session authentication: mỗi request cần đúng credentials và authorization.

## 15. Các lỗi code thường gặp và cách sửa

**Lỗi 1 — `WebClient.create(...)` mỗi request.** Có thể dùng lại global Netty resources tùy transport, nhưng tạo client liên tục vẫn làm cấu hình, testing và instrumentation khó quản lý. Inject Boot builder, build một client ở constructor hoặc bean.

**Lỗi 2 — Dùng `RestClient.Builder` stateful chung để thêm token per-user.** Builder thay đổi ảnh hưởng các client tạo sau. Đừng gọi `builder.defaultHeader("Authorization", ...)` với token user từ nhiều request; dùng headers trên request.

**Lỗi 3 — Dùng `CloseableHttpClient` trong try-with-resources trong mỗi service method.** Làm mất lợi ích pooling. Để Spring context là owner của transport dài hạn.

**Lỗi 4 — Đóng Reactor Netty `HttpResources` global từ một component.** Có thể làm hỏng các WebClient/server khác dùng chung event loops/pool. Tôn trọng ownership.

**Lỗi 5 — Gọi `.block()` trên Netty event loop.** Có thể tạo deadlock/starvation/latency cao; dùng reactive operators, hoặc offload blocking code có kiểm soát.

**Lỗi 6 — Bỏ quên response body hoặc truyền raw stream ra khỏi callback.** Connection/buffer chưa được trả hoặc stream đã đóng. Consume/decode đúng và đóng response theo contract.

**Lỗi 7 — Bật pool size rất lớn không đo tải.** Tăng áp lực upstream, file descriptors, connection storms; đo active/pending/tail latency và áp dụng bulkhead.

**Lỗi 8 — Không cấu hình acquisition timeout.** Pending queue kéo dài, request dùng hết deadline trước khi gọi upstream; đặt timeout cùng concurrency/queue hợp lý.

**Lỗi 9 — Dùng cùng giá trị timeout cho connect, acquire và toàn request mà không hiểu.** Kết quả mong đợi về latency có thể sai; đo từng giai đoạn và định nghĩa end-to-end business deadline riêng.

**Lỗi 10 — Giả định client object giống connection.** Một client có nhiều sockets, HTTP/2 có nhiều streams trên một socket, DNS/LB/proxy ảnh hưởng routing.

**Lỗi 11 — Không đóng Apache client do mình sở hữu khi context shutdown.** Pool/eviction thread có thể sống sau redeploy; dùng bean destroy method và test lifecycle.

**Lỗi 12 — Chỉ assert HTTP 200 rồi kết luận TCP reuse.** Test phải quan sát connection identity/pool stats nếu thực sự cần chứng minh reuse.

**Lỗi 13 — Java 17 dùng `try (HttpClient client = ...)`.** JDK HttpClient close API xuất hiện từ JDK 21; dùng đúng baseline Java.

**Lỗi 14 — Để upstream giữ response streaming vô hạn trong pool phục vụ short calls.** SSE, long-poll và file download dài có thể chiếm slots; cân nhắc pool/bulkhead riêng hoặc limit phù hợp theo loại traffic.

**Lỗi 15 — Không đồng nhất lifecycle trên test.** Tự đóng singleton transport ở `@AfterAll` trong khi Spring Test context còn cache, khiến test sau lỗi khó hiểu. Để Spring sở hữu/đóng bean; test tự đóng chỉ các tài nguyên do test trực tiếp tạo.

## 16. Checklist thiết kế HTTP client trước khi triển khai

- [ ] Client object được tạo và inject **một lần** theo application/service lifetime, không theo từng request.
- [ ] Underlying transport và connection pool có **owner rõ ràng**, không có hai component cùng close hoặc không ai close.
- [ ] Đã chọn `RestClient` cho blocking MVC hay `WebClient` cho reactive theo kiến trúc.
- [ ] Đã xác minh request factory/connector thực tế được chọn trong runtime và phiên bản dependency.
- [ ] Pool có giới hạn tổng/per-route, queue hữu hạn (nếu API có) và timeout acquire/connect/response phù hợp.
- [ ] Có chính sách TTL/idle eviction khớp upstream/load balancer keep-alive.
- [ ] Response body/stream luôn được consume, close hoặc cancel theo contract; không giữ raw stream ngoài lifecycle callback.
- [ ] HTTP/2 multiplexing, proxy route và số replicas được tính khi sizing pool.
- [ ] Đã có metrics active/idle/pending, acquire latency, HTTP status và timeout, cùng alerts có ý nghĩa.
- [ ] TLS validation/hostname verification giữ nguyên; SSRF được hạn chế bằng allowlist/egress policy.
- [ ] Token/cookie/user headers không bị giữ trong singleton mutable state; per-request auth được tách đúng.
- [ ] Retry/backoff/circuit breaker không gây tăng tải khi pool/upstream đã saturated.
- [ ] Có test HTTP thật với stub local và load test giới hạn concurrency, không chỉ mock request factory.
- [ ] Application graceful shutdown đóng transport/pool sau khi xử lý in-flight work đúng policy.
- [ ] Dòng Spring Boot/Framework/Apache/Reactor Netty đang chạy được duy trì security patches.

## 17. Câu hỏi tự kiểm tra

**1. Tạo một bean `RestClient` singleton có nghĩa ứng dụng chỉ dùng một TCP socket?**  
Không. Singleton client có thể tạo/lease nhiều TCP sockets trong pool tùy concurrency, route, protocol và upstream.

**2. Vì sao không tạo `CloseableHttpClient` rồi đóng ngay sau từng `GET`?**  
Vì mất reuse và tạo TCP/TLS/threads/socket setup lặp lại. Đóng tài nguyên khi owner (ApplicationContext) kết thúc, không theo từng request.

**3. `connectionRequestTimeout` khác `connectTimeout`?**  
Cái đầu giới hạn thời gian chờ được pool cấp connection; cái sau giới hạn thời gian thiết lập network connection mới.

**4. Khi `pending` tăng nhưng `idle` còn 0, có chắc pool leak?**  
Chưa. Có thể upstream thật sự chậm, quá nhiều requests đồng thời, streaming chiếm connection hoặc response chưa release. Cần xem active/response lifecycle/latency.

**5. Một HTTP 200 chứng minh connection reuse không?**  
Không. Cần pool metrics, connection IDs hoặc network tracing có kiểm soát.

**6. Spring Boot có tự cấu hình `RestClient.Builder` và `WebClient.Builder` không?**  
Có khi dependencies tương ứng tồn tại; nên inject builder và build client một lần. Nhưng underlying transport được chọn vẫn có thể phụ thuộc classpath/version và customization.

**7. Khi dùng Reactor Netty global resources, có thể cho một service gọi `HttpResources.disposeLoopsAndConnections()` sau request không?**  
Không. Các clients/servers khác có thể đang dùng global resources. Quản lý shutdown tại application/context owner.

**8. Vì sao phải đọc hết hoặc cancel body đúng cách?**  
Để transport hoàn tất exchange và có thể trả connection về pool hoặc đóng socket an toàn; nếu bỏ stream mở, leased resources có thể bị giữ.

**9. `@Bean(destroyMethod="close")` có nên đặt trên một Apache HttpClient được toàn JVM dùng bởi nhiều contexts?**  
Chỉ khi context thực sự sở hữu resource. Nếu dùng chung qua contexts, cần owner ngoài hoặc một lifecycle coordination chính xác.

**10. Tại sao dùng `RestClient` blocking trong WebFlux event loop có thể gây nghẽn?**  
Blocking I/O giữ event-loop thread, làm trì hoãn nhiều requests khác; dùng `WebClient` hoặc offload có giới hạn.

**11. Dữ liệu auth của từng user có được set vào default header của singleton client không?**  
Không. Dùng request-specific headers/context để tránh rò dữ liệu giữa users, kiểm soát token lifetime.

**12. Có nên luôn đặt `maxConnections` thật cao để tăng thông lượng?**  
Không. Dùng throughput × latency và load test; quota upstream, HTTP/2, queue, retry và resource budget quyết định ngưỡng.

**13. Nếu Java đang dùng JDK 17, có thể gọi `HttpClient.close()` không?**  
Không theo API Java 17. Các method quản lý shutdown chính thức của JDK HttpClient xuất hiện từ Java 21; không nhầm với Apache CloseableHttpClient.

**14. Pool đang ổn, nhưng API vẫn bị `PrematureCloseException` sau thời gian idle thì xem gì?**  
Upstream/LB idle timeout, stale socket, remote close, maxIdleTime/lifeTime/eviction và retry policy; không chỉ tăng maxConnections.

## 18. Tài liệu chính thức tham khảo

- Spring Boot 3.5 — *Calling REST Services* (`RestClient.Builder`/`WebClient.Builder`, client transport): https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html
- Spring Framework 6.2 — *REST Clients*: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Framework — *WebClient Configuration and Resources*: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — *WebClient Exchange*: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework 6.2 — `HttpComponentsClientHttpRequestFactory`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html
- Reactor Netty — *HTTP Client / Connection Pool / Disposing / Timeout Configuration*: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Apache HttpComponents Client 5 — *Connection Management*: https://hc.apache.org/httpcomponents-client-5.5.x/current/tutorial/html/connmgmt.html
- JDK 21 — `java.net.http.HttpClient` API và lifecycle `close/shutdown`: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- Spring Boot 3.5.16 release và OSS support note: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** HTTP client dùng chung là cách **tái sử dụng cấu hình và tài nguyên transport**; connection pool là nơi giới hạn/cấp phát các kết nối vật lý; response body và request spec có vòng đời riêng. Trong Spring Boot, hãy **build RestClient/WebClient một lần**, chọn transport phù hợp, kiểm soát **max connections + pending queue + timeouts**, consume/cancel response đúng, đóng **pool/client theo owner** khi ứng dụng dừng, và dùng metrics + test HTTP thật để phân biệt connection reuse với một loạt status 200 thành công.