# Đối chiếu cùng một bài toán trên Spring MVC và WebFlux bằng hành vi quan sát được

## 1. Mục tiêu: cùng API, cùng upstream, so sánh điều nhìn thấy

Spring MVC và Spring WebFlux đều hỗ trợ xây dựng REST APIs nhưng có mô hình thực thi khác nhau. Nếu chỉ so sánh cú pháp “controller trả object” với “controller trả Mono”, chúng ta chưa chứng minh được khác biệt khi vận hành.

Bài thực hành sử dụng **một bài toán duy nhất**: cổng API truy vấn số lượng hàng từ một HTTP upstream có độ trễ khoảng 300 ms.

- Client gọi `GET /api/inventory/{id}`.
- Gateway Spring gọi `GET /inventory/{id}` ở upstream dùng chung.
- Upstream trả JSON `{"id":1,"available":true}` cho ID hợp lệ, trả HTTP `404` cho ID không tồn tại.
- Cổng MVC và cổng WebFlux cùng trả HTTP `200` + JSON tương đương hoặc HTTP `404`.
- Chạy nhiều request đồng thời và ghi nhận **thread names**, số request đang xử lý, p95 response latency, tổng thời gian và lỗi.
- Đối chiếu theo hành vi được quan sát, không suy ra framework “luôn nhanh hơn” từ một benchmark toy.

Trong bài này:

- **MVC** dùng Servlet/Tomcat + `RestClient` (HTTP client đồng bộ).
- **WebFlux** dùng Reactor Netty + `WebClient` (HTTP client reactive/non-blocking).
- **Upstream** là HTTP server độc lập viết bằng Java SE 17; cả hai cổng gọi cùng một URL. Nhờ vậy phép so sánh không vô tình đo hai backend khác nhau.

Các cấu hình và tên API tập trung vào **Spring Boot 3.x / Spring Framework 6.x, Java 17+**. Đừng lấy một kết luận hiệu năng trong môi trường này áp cho mọi loại workload.

## 2. Điều cần hiểu trước khi chạy

### 2.1. Spring MVC đồng bộ

Một request MVC điển hình:

~~~text
Client
  -> TCP/HTTP -> Tomcat servlet worker
                  |
                  -> @RestController
                  -> RestClient HTTP GET tới upstream (đồng bộ)
                  -> thread servlet CHỜ response
                  -> nhận Inventory record
                  -> Jackson serialize JSON
                  -> HTTP 200 cho client
~~~

Trong lúc `RestClient` đợi response, **servlet worker gọi nó bị chiếm**. Đây không phải lỗi: đó là mô hình lập trình imperative; đơn giản và phù hợp nhiều hệ thống đang dùng Spring MVC, JDBC/JPA, nghiệp vụ đồng bộ.

Nhưng nếu nhiều request phải chờ remote I/O lâu, giới hạn số servlet threads, HTTP connections và queue có thể ảnh hưởng throughput/tail latency. Việc tăng thread pool chỉ chuyển điểm nghẽn nếu upstream hoặc DB đã quá tải.

### 2.2. Spring WebFlux reactive

Một request WebFlux điển hình:

~~~text
Client
  -> Reactor Netty event-loop / WebFlux handler
                  |
                  -> @RestController trả Mono<Inventory>
                  -> WebClient HTTP GET tới upstream
                  -> subscribe bất đồng bộ; event-loop KHÔNG ngồi đợi 300 ms
                  -> nhận tín hiệu HTTP response
                  -> Mono phát Inventory record
                  -> WebFlux/Jackson ghi HTTP 200 JSON
~~~

Publisher `Mono<T>` biểu diễn **một kết quả có thể đến sau**, không phải một thread riêng. Reactor Netty dùng non-blocking I/O cho socket; reactor operators có thể chạy trên event-loop, scheduler khác hoặc thread đặc thù theo chuỗi xử lý. **Không mặc định mọi callback chạy trên một thread duy nhất** và không gọi `block()` trong event-loop.

Đặc biệt, Spring MVC **cũng có hỗ trợ async** bằng `Callable`, `DeferredResult`, `CompletionStage` và reactive return values như `Mono`. Vì vậy “MVC = mọi request phải giữ servlet worker” chỉ đúng với ví dụ **MVC đồng bộ** đang khảo sát, không đúng cho toàn bộ Spring MVC. MVC async dùng Servlet async; WebFlux có asynchronous contracts từ đầu. Ở Servlet stack, các lần ghi HTTP response vẫn có đặc tính blocking tùy kiểu response, khác WebFlux với non-blocking response I/O.

### 2.3. Khác nhau ở đâu, giống nhau ở đâu?

| Khía cạnh | MVC + RestClient | WebFlux + WebClient |
| --- | --- | --- |
| HTTP API bên ngoài | `GET /api/inventory/{id}` | Giống hệt |
| Response 200 | JSON Inventory | JSON Inventory tương đương |
| HTTP upstream | Cùng Java HTTP server | Cùng Java HTTP server |
| Độ trễ upstream | 300 ms mô phỏng | 300 ms mô phỏng |
| Handler return type | `Inventory` | `Mono<Inventory>` |
| HTTP client | `RestClient` synchronous | `WebClient` reactive |
| Khi chờ upstream | Servlet worker bị block | Không cần giữ một event-loop để đợi |
| Khi nhận lỗi 404 | Catch HTTP client exception | Map reactive error signal |
| Áp lực khi nhiều request | Servlet threads, pending tasks, pools | Open connections, event-loops, event queues, subscriber/backpressure |
| Tích hợp với JPA/JDBC blocking | Tự nhiên | Phải cô lập blocking calls hoặc lựa chọn mô hình khác |
| Khả năng chạy async | MVC hỗ trợ nếu thiết kế riêng | Thuộc mô hình nền tảng |

Cả hai có thể thực hiện cùng chức năng và cùng độ đúng nghiệp vụ. Một benchmark duy nhất không chứng minh WebFlux nhanh hơn về CPU, chi phí vận hành hay latency trong mọi tình huống.

## 3. Kiến trúc demo và các giả định đo

~~~text
                        +----------------------------+
  curl / LoadProbe ---> | MVC gateway :8081          |
                        | Tomcat + RestClient         |---+
                        +----------------------------+   |
                                                         | HTTP GET
                        +----------------------------+   | /inventory/{id}
  curl / LoadProbe ---> | WebFlux gateway :8082      |---+
                        | Reactor Netty + WebClient   |   |
                        +----------------------------+   v
                                                   +-------------------+
                                                   | Upstream :9090    |
                                                   | Java HttpServer   |
                                                   | delay ~= 300 ms   |
                                                   | 1..3 -> 200 JSON  |
                                                   | others -> 404     |
                                                   +-------------------+
~~~

Chủ động tránh các lỗi làm kết quả so sánh vô nghĩa:

- Một upstream **không tự gọi ngược chính server MVC**, vì vòng lặp tự gọi có thể gây cạn servlet worker.
- Upstream dùng fixed pool 64 workers để phục vụ các request demo đồng thời; nếu vượt capacity sẽ có queue và tăng latency.
- Hai gateway chạy ở **hai JVM, hai cổng khác nhau**; chỉ chạy một phép đo tải tại một thời điểm để tránh upstream bị hai nhóm đo tranh tài nguyên.
- Đường truyền là localhost. Nó phù hợp để quan sát execution model, **không đại diện cho mạng Internet hoặc production**.
- Cấu hình `server.tomcat.threads.max=8` dưới đây là **thí nghiệm có chủ đích**, làm rõ hiện tượng chờ thread; không phải khuyến nghị mặc định cho production.
- Kết quả latency phụ thuộc máy, hệ điều hành, JIT warmup, connection reuse, logging, memory, số CPU, client và tải khác. Ghi số thật thu được, không thay chúng bằng một con số “chuẩn”.

## 4. Ứng dụng upstream dùng chung: Java 17 thuần

Tạo file `upstream/SlowInventoryServer.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class SlowInventoryServer {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9090), 0);
        server.createContext("/inventory", SlowInventoryServer::handle);
        server.setExecutor(Executors.newFixedThreadPool(64));
        server.start();
        System.out.println("Upstream listening on 127.0.0.1:9090");
    }

    private static void handle(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "GET");
            reply(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }

        String[] parts = exchange.getRequestURI().getPath().split("/");
        String id = parts.length == 3 ? parts[2] : "";

        if (!id.matches("[1-3]")) {
            reply(exchange, 404, "{\"error\":\"not_found\"}");
            return;
        }

        try {
            Thread.sleep(300); // Mô phỏng remote I/O / một backend chậm.
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            reply(exchange, 503, "{\"error\":\"interrupted\"}");
            return;
        }

        reply(exchange, 200,
                "{\"id\":" + id + ",\"available\":true}");
    }

    private static void reply(
            HttpExchange exchange, int status, String json)
            throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

Từ thư mục `upstream/`, biên dịch và chạy:

~~~bash
javac --add-modules jdk.httpserver SlowInventoryServer.java
java --add-modules jdk.httpserver SlowInventoryServer
~~~

Stdout khi server khởi chạy:

~~~text
Upstream listening on 127.0.0.1:9090
~~~

Thử ở một terminal khác:

~~~bash
curl -i http://127.0.0.1:9090/inventory/1
curl -i http://127.0.0.1:9090/inventory/9
~~~

Response thứ nhất có status `200`, body `{"id":1,"available":true}` và độ trễ chủ động khoảng 300 ms; response thứ hai `404` với body `{"error":"not_found"}`. Giá trị `Date`, thời gian thực và thứ tự headers không cố định. Nếu cổng 9090 bị chiếm, phải chỉnh URL ở upstream và cả hai gateway cùng lúc.

**Tại sao upstream dùng `Thread.sleep`?** Chỉ để tạo độ trễ kiểm soát được ở **một server độc lập**. Nó không ngụ ý rằng WebFlux cần hoặc nên sử dụng `Thread.sleep`. Khi ứng dụng WebFlux gọi endpoint, I/O của gateway vẫn do WebClient non-blocking đảm nhận; thread sleep nằm ở máy chủ upstream giả lập.

## 5. Gateway Spring MVC: synchronous RestClient

Tạo thư mục `mvc/` với cấu trúc:

~~~text
mvc/
  pom.xml
  src/main/java/demo/MvcInventoryApplication.java
  src/main/resources/application.properties
~~~

### 5.1. mvc/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-inventory</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Đây là ứng dụng **Servlet MVC** vì có `spring-boot-starter-web`. Không thêm WebFlux starter vào project MVC chỉ để gọi HTTP đồng bộ; `RestClient` đủ cho bài toán này.

### 5.2. mvc/src/main/resources/application.properties

~~~properties
server.port=8081
server.tomcat.threads.max=8
~~~

Giới hạn 8 servlet threads giúp quan sát khi số request đồng thời vượt capacity. Giá trị này có thể làm 40 request phải đợi nhiều đợt, nhất là khi mỗi request giữ worker khoảng 300 ms.

### 5.3. mvc/src/main/java/demo/MvcInventoryApplication.java

~~~java
package demo;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class MvcInventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcInventoryApplication.class, args);
    }

    @Bean
    RestClient upstream(RestClient.Builder builder) {
        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();
        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("http://127.0.0.1:9090")
                .requestFactory(factory)
                .build();
    }
}

record Inventory(long id, boolean available) {}

@RestController
class MvcInventoryController {
    private static final Logger log =
            LoggerFactory.getLogger(MvcInventoryController.class);

    private final RestClient upstream;
    private final AtomicInteger active = new AtomicInteger();

    MvcInventoryController(RestClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/api/inventory/{id}")
    Inventory get(@PathVariable int id) {
        int now = active.incrementAndGet();
        log.info("MVC start id={} active={} thread={}",
                id, now, Thread.currentThread().getName());

        try {
            Inventory result = upstream.get()
                    .uri("/inventory/{id}", id)
                    .retrieve()
                    .body(Inventory.class);

            if (result == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY, "Empty upstream body");
            }

            return result;
        } catch (RestClientResponseException ex) {
            if (ex.getStatusCode().value() == 404) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Inventory not found", ex);
            }
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Upstream rejected request", ex);
        } catch (RestClientException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Upstream unavailable", ex);
        } finally {
            int left = active.decrementAndGet();
            log.info("MVC end id={} active={} thread={}",
                    id, left, Thread.currentThread().getName());
        }
    }
}
~~~

Chạy từ thư mục `mvc/`:

~~~bash
mvn spring-boot:run
~~~

Quan sát log. Với request đơn bình thường, start và end thường có cùng tên thread Servlet worker, ví dụ `http-nio-8081-exec-1`, vì `RestClient` gọi đồng bộ ngay bên trong controller. Tên thread thực tế có thể khác theo Tomcat, phiên bản và môi trường; điều cần quan sát là **một worker bắt đầu request, đợi upstream và hoàn tất request**.

`active` đo số lời gọi còn đang ở method controller, **không phải tổng servlet threads trong container**. Số đo này giúp nhận diện lượng request đang chờ, nhưng để biết thread-pool saturation nên kiểm tra thêm Tomcat metrics hoặc thread dump.

Trong ví dụ trên, một response lỗi HTTP 404 từ upstream được chuyển thành status 404 của gateway. Lỗi HTTP khác hoặc lỗi kết nối được chuyển 502. Cấu hình timeout ở HTTP client là một lớp bảo vệ; timeout có thể biểu hiện như lỗi I/O trong `RestClientException`, nên ví dụ **không tuyên bố mapping 504 cho mọi timeout**.

## 6. Gateway Spring WebFlux: reactive WebClient

Tạo thư mục `webflux/` riêng:

~~~text
webflux/
  pom.xml
  src/main/java/demo/WebFluxInventoryApplication.java
  src/main/resources/application.properties
~~~

Không trộn `spring-boot-starter-web` với `spring-boot-starter-webflux` trong dự án này: nếu cả hai cùng có, Spring Boot thường chọn **MVC web application** làm default. Tách hai app giúp bạn xác thực chắc chắn server stack được dùng.

### 6.1. webflux/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-inventory</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 6.2. webflux/src/main/resources/application.properties

~~~properties
server.port=8082
~~~

WebFlux server Reactor Netty không dùng thuộc tính `server.tomcat.threads.max`. Không cố “công bằng hóa” bằng cách dùng cùng tên cấu hình thread: MVC servlet pool và Reactor Netty event-loop pool thực hiện các vai trò khác nhau. Khi benchmark nghiêm túc, cần ghi nhận và điều chỉnh **cả hai hệ thống theo capacity/resource budget**.

### 6.3. webflux/src/main/java/demo/WebFluxInventoryApplication.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxInventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxInventoryApplication.class, args);
    }

    @Bean
    WebClient upstream(WebClient.Builder builder) {
        return builder.baseUrl("http://127.0.0.1:9090").build();
    }
}

record Inventory(long id, boolean available) {}

@RestController
class WebFluxInventoryController {
    private static final Logger log =
            LoggerFactory.getLogger(WebFluxInventoryController.class);

    private final WebClient upstream;
    private final AtomicInteger active = new AtomicInteger();

    WebFluxInventoryController(WebClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/api/inventory/{id}")
    Mono<Inventory> get(@PathVariable int id) {
        return Mono.defer(() -> {
            int now = active.incrementAndGet();
            log.info("WebFlux subscribe id={} active={} thread={}",
                    id, now, Thread.currentThread().getName());

            return upstream.get()
                    .uri("/inventory/{id}", id)
                    .retrieve()
                    .bodyToMono(Inventory.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "Empty upstream body")))
                    .onErrorMap(
                            WebClientResponseException.class,
                            ex -> ex.getStatusCode().value() == 404
                                    ? new ResponseStatusException(
                                            HttpStatus.NOT_FOUND,
                                            "Inventory not found", ex)
                                    : new ResponseStatusException(
                                            HttpStatus.BAD_GATEWAY,
                                            "Upstream rejected request", ex))
                    .onErrorMap(
                            WebClientRequestException.class,
                            ex -> new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "Upstream unavailable", ex))
                    .timeout(Duration.ofSeconds(2))
                    .onErrorMap(
                            TimeoutException.class,
                            ex -> new ResponseStatusException(
                                    HttpStatus.GATEWAY_TIMEOUT,
                                    "Upstream response timed out", ex))
                    .doOnNext(value -> log.info(
                            "WebFlux result id={} thread={}",
                            id, Thread.currentThread().getName()))
                    .doFinally(signal -> {
                        int left = active.decrementAndGet();
                        log.info("WebFlux end id={} active={} signal={} thread={}",
                                id, left, signal,
                                Thread.currentThread().getName());
                    });
        });
    }
}
~~~

Chạy ở thư mục `webflux/`:

~~~bash
mvn spring-boot:run
~~~

Ở đây **controller không gọi `block()` hoặc `subscribe()`**. Nó trả `Mono<Inventory>`; WebFlux tự subscribe trong request lifecycle, serialize dữ liệu khi publisher phát giá trị và xử lý lỗi từ publisher.

`Mono.defer` bảo đảm việc tăng biến `active` và tạo request diễn ra **lúc subscribe**, không ngay lúc method tạo publisher. `doFinally` chạy khi stream kết thúc thành công, lỗi hoặc bị cancel; đếm in-flight vì vậy có cơ chế cleanup kể cả trường hợp request bị hủy.

`timeout(Duration)` là timeout cấp reactive chain, không thay thế đầy đủ connect timeout và các giới hạn connection pool của Reactor Netty. Response status 504 từ timeout này là chính sách minh họa; mapping timeout trong MVC ở trên chưa được chuẩn hóa thành 504, nên **chỉ xem 200/404 và lỗi mạng 502 là contract tương đương trong demo**, không kết luận hai stack có error contract hoàn toàn giống nhau ở mọi failure mode.

### Chú ý về log thread

Ví dụ khi log xuất hiện trên `reactor-http-nio-*`, nó cho thấy callback đang ở event-loop Reactor Netty. Nhưng Reactor có thể chọn thread khác dựa vào operator/scheduler; tên không cố định. Điểm đáng quan sát là **không có lời gọi đợi blocking trên handler thread** trong code này. WebClient thực hiện HTTP I/O theo non-blocking model trong khi upstream chờ khoảng 300 ms.

Nếu chèn `Thread.sleep(300)` vào `map` hoặc `doOnNext` bên WebFlux thì bạn đã phá giả định non-blocking. Nếu gọi JDBC/JPA synchronous hoặc đọc file blocking, phải chuyển phần đó sang cơ chế blocking có kiểm soát (`boundedElastic` hoặc thread pool riêng) hoặc chọn Spring MVC imperative nếu toàn hệ thống chủ yếu blocking.

## 7. Thử nghiệm đối xứng: kiểm tra chức năng và lỗi

Bật ba tiến trình ở ba terminal:

1. `SlowInventoryServer` lắng nghe 9090.
2. `MvcInventoryApplication` lắng nghe 8081.
3. `WebFluxInventoryApplication` lắng nghe 8082.

Gửi cùng request:

~~~bash
curl -i http://localhost:8081/api/inventory/1
curl -i http://localhost:8082/api/inventory/1
~~~

Cả hai có status `200 OK`, `Content-Type` JSON tương ứng và body về mặt dữ liệu:

~~~json
{"id":1,"available":true}
~~~

Thứ tự JSON fields, HTTP headers `Date`/`Content-Length`/`Transfer-Encoding` và server headers có thể khác; so **ý nghĩa dữ liệu, status và contract** thay vì so byte-for-byte toàn bộ response.

Thử resource không tồn tại:

~~~bash
curl -i http://localhost:8081/api/inventory/9
curl -i http://localhost:8082/api/inventory/9
~~~

Cả hai có HTTP status `404` nếu upstream đang chạy đúng như ví dụ. Spring Boot có thể tạo default error body khác giữa các stack/cấu hình, nhất là khi không bật `ProblemDetail` đồng nhất. **Cùng status không đồng nghĩa body lỗi đã có contract giống nhau**; nếu frontend cần body thống nhất, nên chuẩn hóa bằng `@RestControllerAdvice` tương ứng và kiểm thử schema.

Thử backend dừng: dừng `SlowInventoryServer`, sau đó gửi `/api/inventory/1` tới hai gateway. Với cơ chế catch/map trong ví dụ, **lỗi kết nối** thông thường được chuyển `502 Bad Gateway`. Khi backend đang chạy nhưng kéo dài quá timeout, MVC có thể map một I/O timeout thành 502 còn WebFlux có thể trả 504 từ `Mono.timeout`; đó là khác biệt đã được chỉ rõ, không che giấu như “cùng semantics tuyệt đối”.

Dùng `curl -w` để ghi nhận riêng latency:

~~~bash
curl -s -o /dev/null -w "MVC total=%{time_total}s\n" http://localhost:8081/api/inventory/1
curl -s -o /dev/null -w "WebFlux total=%{time_total}s\n" http://localhost:8082/api/inventory/1
~~~

`/dev/null` là đường dẫn trên hệ Unix-like; trên Windows có thể dùng công cụ HTTP CLI/tập lệnh phù hợp hoặc chỉ quan sát `curl -w` mà không dùng `-o /dev/null`. Thời gian một request khi không có queue thường bị chi phối bởi độ trễ upstream và không tự chứng minh stack nào hơn.

## 8. LoadProbe: đo nhiều request đồng thời bằng Java 17

Tạo file độc lập `probe/LoadProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class LoadProbe {
    record Result(int status, long elapsedMs) {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            System.err.println(
                    "Usage: java LoadProbe <baseUrl> [requestCount]");
            System.exit(2);
        }

        String baseUrl = args[0].replaceAll("/+$", "");
        int count = args.length == 2 ? Integer.parseInt(args[1]) : 40;
        if (count < 1 || count > 2000) {
            throw new IllegalArgumentException("requestCount must be 1..2000");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpRequest request = HttpRequest.newBuilder(
                    URI.create(baseUrl + "/api/inventory/1"))
                .GET()
                .timeout(Duration.ofSeconds(15))
                .build();

        List<CompletableFuture<Result>> pending = new ArrayList<>();
        long globalStart = System.nanoTime();

        for (int i = 0; i < count; i++) {
            long requestStart = System.nanoTime();
            CompletableFuture<Result> one = client.sendAsync(
                    request, HttpResponse.BodyHandlers.discarding())
                .handle((response, error) -> new Result(
                    error == null ? response.statusCode() : -1,
                    TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - requestStart)));
            pending.add(one);
        }

        CompletableFuture.allOf(
                pending.toArray(CompletableFuture[]::new)).join();

        long ok = pending.stream()
                .map(CompletableFuture::join)
                .filter(result -> result.status() == 200)
                .count();

        long[] latencies = pending.stream()
                .map(CompletableFuture::join)
                .mapToLong(Result::elapsedMs)
                .sorted()
                .toArray();

        int p95Index = (int) Math.ceil(count * 0.95) - 1;
        long totalMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - globalStart);

        System.out.printf(
                "requests=%d ok=%d failed=%d totalMs=%d p95Ms=%d%n",
                count, ok, count - ok, totalMs, latencies[p95Index]);
    }
}
~~~

Biên dịch ở `probe/`:

~~~bash
javac LoadProbe.java
~~~

Chạy **riêng từng gateway**, không đồng thời hai phép đo:

~~~bash
java LoadProbe http://localhost:8081 40
java LoadProbe http://localhost:8082 40
~~~

Chương trình in một dòng theo định dạng:

~~~text
requests=<N> ok=<M> failed=<N-M> totalMs=<measured> p95Ms=<measured>
~~~

Các chuỗi trong dấu `<...>` là **tên giá trị đo**, không phải output số cố định. Với demo và các tiến trình hoạt động bình thường, hy vọng phần lớn request trả 200; bất kỳ failed nào cũng phải được điều tra thay vì bỏ qua.

`LoadProbe` cố gắng khởi tạo nhiều HTTP requests gần nhau bằng `HttpClient.sendAsync(...)`. Nó là công cụ học tập, **không phải load generator chuẩn có warm-up, rate control, coordinated-omission correction, latency distribution hoàn chỉnh**. `totalMs` là thời gian từ lúc bắt đầu tạo các requests đến khi tất cả hoàn tất; `p95Ms` là percentile thực nghiệm từ các latencies ghi nhận sau `sendAsync`. Với 40 mẫu, phân vị rất nhiễu và phụ thuộc trễ ở client; cần nhiều vòng/đủ mẫu mới có kết luận.

## 9. Kết quả kỳ vọng về mặt cấu trúc, không dự đoán số đo

Khi 40 requests đều cần chờ một upstream 300 ms, có hai khả năng thường quan sát được (không bảo đảm mọi máy sẽ giống hệt):

**Ở MVC với Tomcat tối đa 8 request workers:**

- Nếu cả 40 requests gần như cùng đến, có thể thấy khoảng 8 lời gọi controller đồng thời, một số request phải chờ worker.
- Log start/end thường cùng servlet thread; trong khoảng chờ upstream, thread đó chưa phục vụ request khác.
- `active` trong controller thường không vượt quá số request threads đang thực thi controller. Nó có thể thấp hơn 8 khi client/network không bão hòa.
- Tail latency có thể tăng qua nhiều “đợt” chờ khi concurrency vượt capacity. Số đợt và total time còn phụ thuộc connection scheduling, upstream pool, JVM warmup.

**Ở WebFlux với Reactor Netty + WebClient:**

- Nhiều subscriptions có thể được mở trong khi chỉ có số event-loop threads tương đối ít; event-loop không bị block trong lúc chờ upstream.
- Log `active` có thể lớn hơn số event-loop threads vì nó đếm **đang chờ publisher hoàn tất**, không phải số threads.
- Thời gian chờ do upstream vẫn tồn tại; WebFlux không làm 300 ms network/backend latency “biến mất”.
- Nếu WebClient connection pool, upstream thread pool, CPU, queue, logging hoặc client cạn capacity, p95/tổng thời gian vẫn có thể tăng rất mạnh.

### Vì sao không lấy một con số để khẳng định WebFlux thắng?

Trong ví dụ này ta **cố ý giới hạn Tomcat chỉ 8 workers** nhưng không giới hạn một resource budget tương ứng của WebFlux. Điều này chứng minh tác động của **mô hình chờ thread** dưới một cấu hình cụ thể, chứ không so sánh công bằng toàn bộ framework.

Muốn đánh giá nghiêm túc:

1. Chạy warm-up để JIT/HTTP connection reuse ổn định.
2. Đo nhiều vòng và báo median/p95/p99, throughput, CPU, memory/GC, số connections, số threads, errors.
3. Đảm bảo upstream không thành điểm nghẽn; nếu thành bottleneck hãy ghi rõ đó là điều bạn đang đo.
4. Thử cùng host/cấu hình, giới hạn CPU/memory/network tương đương; ghi phiên bản Java/Spring/Netty/Tomcat và config.
5. So sánh cả **MVC async dùng WebClient/CompletionStage**, không chỉ MVC blocking, khi bài toán đòi hiệu quả chờ I/O cao.
6. Thử biến thể có nghiệp vụ blocking thật (JDBC/JPA), CPU-bound computation và streaming, vì “reactive = nhanh hơn” là suy luận sai.
7. Kiểm thử timeout, cancellation, backpressure và error rates, không chỉ happy path.

Để phục vụ giám sát thực tế, có thể dùng Micrometer/Actuator (được cấu hình chính xác cho từng app) để quan sát `http.server.requests`, Tomcat busy threads, Reactor Netty connection pool và scheduler metrics; tên meter/tag thực tế có thể phụ thuộc phiên bản và configuration.

## 10. Sự khác nhau giữa blocking servlet thread và non-blocking event-loop

Một thread servlet đồng bộ chờ RestClient:

~~~text
Tomcat-Worker-1: [controller]->[HTTP call--------waiting--------]->[JSON]
Tomcat-Worker-2: [controller]->[HTTP call--------waiting--------]->[JSON]
Tomcat-Worker-3: [controller]->[HTTP call--------waiting--------]->[JSON]
...
       số request đang chạy bị giới hạn bởi worker pool và resources khác
~~~

Nhiều request WebFlux non-blocking:

~~~text
reactor-http-nio-1: [accept][subscribe][socket-event][write][accept]...
reactor-http-nio-2: [accept][subscribe][socket-event][write][accept]...
         |              |               |
         +--- nhiều upstream requests đang chờ HTTP response
              không cần mỗi request một blocking worker
~~~

Đây là sơ đồ logic, không mô tả scheduler internals một cách chính xác tuyệt đối. Netty có worker event-loops và networking tasks; operator chain có thể chạy ở các thread khác.

### Sai: ép WebFlux quay về blocking

~~~java
@GetMapping("/bad/{id}")
Inventory wrong(@PathVariable int id) {
    return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .bodyToMono(Inventory.class)
            .block();
}
~~~

Khi đoạn code này được thực thi trên Reactor event-loop, `block()` không được hỗ trợ, có thể ném `IllegalStateException`. Dù một đoạn blocking chạy được trên thread khác, nó vẫn lãng phí khả năng non-blocking mà API WebFlux đang cung cấp.

Đúng:

~~~java
@GetMapping("/good/{id}")
Mono<Inventory> correct(@PathVariable int id) {
    return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .bodyToMono(Inventory.class);
}
~~~

Hai snippet trên là minh họa tích hợp, giả định có `webClient` và `Inventory`. Với WebFlux, trả publisher; không gọi thủ công `subscribe()` để rồi controller trả response trước khi kết quả đến. Trả publisher giúp framework quản lý status, error, cancellation, trace và response lifecycle.

### Blocking code không được làm mất

Nếu tầng nghiệp vụ bắt buộc gọi JDBC/JPA synchronous hoặc client legacy blocking trong một reactive pipeline, bọc **riêng** đoạn blocking:

~~~java
Mono<Inventory> result = Mono.fromCallable(
                () -> legacyInventoryRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là một giải pháp phối hợp có giới hạn, không chuyển repository thành reactive và không tự làm DB queries có thể chạy vô hạn. Với nhiều thành phần blocking, cấu trúc MVC synchronous thường có tính đơn giản và khả năng kiểm soát tốt hơn; **sử dụng WebFlux không phải yêu cầu bắt buộc cho mọi web API hiện đại**.

## 11. Cùng một hành vi khi có lỗi, timeout và client cancel

### Upstream trả 404

Cả RestClient và WebClient mặc định coi HTTP 4xx/5xx là error path khi gọi `retrieve()` (với những API như `body(...)` và `bodyToMono(...)` trong ví dụ). Hai controller map upstream 404 thành gateway 404. Tuy nhiên default response body và xử lý exception có thể không giống nhau nếu không chuẩn hóa. Test phải kiểm tra status, format, fields cần thiết chứ không dựa vào thông điệp exception.

### Upstream trả 5xx

Ở MVC, `RestClientResponseException` được catch và map gateway 502. Ở WebFlux, `WebClientResponseException` được map trong `onErrorMap` thành gateway 502. Cả hai thể hiện rằng gateway không thể hoàn thành truy vấn do upstream failure, không nhất thiết giữ nguyên status 500 của backend.

### Upstream không mở hoặc network lỗi

Ở MVC, lỗi synchronous ở `RestClientException` được chuyển 502. Ở WebFlux, `WebClientRequestException` là error signal trên `Mono` và được map thành 502. Nếu ứng dụng thực cần retry, phải thêm có điều kiện, backoff và đảm bảo idempotency; không nên retry vô hạn làm tăng tải trên upstream đang lỗi.

### Timeout

Timeout cần phân biệt:

- MVC JDK HTTP request factory cấu hình connect/read timeout. Exception thường xuất hiện như I/O failure và ví dụ map 502.
- WebFlux `Mono.timeout(Duration.ofSeconds(2))` phát timeout của pipeline, được map 504 trong ví dụ. Nếu Netty connection acquisition hay connection setup có chính sách khác, cần cấu hình tương ứng.
- Client hoặc proxy có timeout riêng; chúng có thể trả lỗi hoặc đóng connection trước gateway.
- “Timeout HTTP gateway” không đồng nghĩa upstream đã dừng công việc. Với thao tác ghi, retry phải xét idempotency keys.

Nếu **contract API yêu cầu mọi timeout là 504**, hãy bổ sung mapper timeout nhất quán cho cả hai ứng dụng và tests cho từng failure mode, thay vì giả định mặc định Spring đồng nhất.

### Client rời trang và cancel

Spring WebFlux có khả năng truyền cancel qua reactive subscription; nhưng việc client đóng socket, thời điểm server nhận biết và khả năng huỷ request ở upstream tùy connector/protocol, không phải lúc nào cũng tức thì. Với MVC synchronous, servlet thread đang blocking vào HTTP client cũng không tự hủy remote operation chỉ vì browser đóng tab.

Đừng gắn ý nghĩa “cancellation = rollback” hoặc “WebFlux không bao giờ giữ tài nguyên khi client rời đi”. Quan sát metrics, cleanup của `doFinally`, connection pool và timeout thực.

## 12. Tự động kiểm thử contract hai gateway

Một lựa chọn đơn giản là chạy upstream 9090 và hai gateway, rồi dùng HTTP client thực để thử cùng bộ test cases:

| Test case | MVC :8081 | WebFlux :8082 | Assert bắt buộc |
| --- | --- | --- | --- |
| `GET /api/inventory/1` | 200 | 200 | JSON id=1, available=true |
| `GET /api/inventory/2` | 200 | 200 | JSON id=2, available=true |
| `GET /api/inventory/9` | 404 | 404 | Status 404, không trả 200 với body lỗi |
| Upstream 9090 tắt, gọi id=1 | thường 502 | thường 502 | Lỗi network được xử lý, không leak stack trace |
| Client gửi HTTP POST tới GET-only route | thường 405 | thường 405 | Method contract; `Allow` nếu framework trả |
| Chạy 40 request song song | đa số 200 nếu đủ capacity | đa số 200 nếu đủ capacity | Error count + total/p95 latency |
| Upstream trả chậm quá timeout | xem mapper MVC | xem mapper WebFlux | Không tự tuyên bố same status nếu code mapper khác |

Các test cases này **không yêu cầu body lỗi giống nhau** khi hai dự án chưa cùng cài error response contract. Nếu muốn strict equality, định nghĩa DTO/`ProblemDetail` và `@RestControllerAdvice` ở cả hai stack.

Một integration test đơn giản có thể dùng JUnit 5 + Java `HttpClient` và chạy ứng dụng ở random ports, hoặc Spring MVC `MockMvc` và WebFlux `WebTestClient` cho nhanh; tuy nhiên bài toán “cùng upstream thật” quan sát rõ hơn khi **chạy server trên port và dùng HTTP client thực**. `MockMvc` không đi qua socket Tomcat, vì vậy không dùng số đo từ `MockMvc` để chứng minh servlet thread saturation.

Một test Java thuần chỉ kiểm tra 200/404 có thể được viết như sau, không phụ thuộc vào Spring Test (giả sử hai gateway và upstream đã được bật):

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class ContractProbe {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        for (int port : new int[]{8081, 8082}) {
            check(client, port, 1, 200, "\"available\":true");
            check(client, port, 9, 404, null);
        }
        System.out.println("MVC and WebFlux HTTP contract: PASS");
    }

    static void check(HttpClient client, int port, int id,
                      int expectedStatus, String expectedFragment)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/api/inventory/" + id))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != expectedStatus) {
            throw new AssertionError(
                    "port=" + port + " id=" + id
                    + " status=" + response.statusCode());
        }

        if (expectedFragment != null
                && !response.body().contains(expectedFragment)) {
            throw new AssertionError("Unexpected body: " + response.body());
        }
    }
}
~~~

Lưu file `probe/ContractProbe.java` rồi chạy:

~~~bash
javac ContractProbe.java
java ContractProbe
~~~

Nếu tất cả các assertion pass, stdout chính xác là:

~~~text
MVC and WebFlux HTTP contract: PASS
~~~

Nếu kết quả khác, chương trình ném `AssertionError` hoặc lỗi kết nối thay vì in `PASS`. Đây là chương trình chạy được với Java 17+; không cần sửa code cho từng gateway.

## 13. Khi nào MVC async làm kết quả so sánh thay đổi?

Đây là phép đối chiếu quan trọng để tránh ngộ nhận.

MVC có thể dùng WebClient:

~~~java
@RestController
class MvcAsyncController {
    private final WebClient client;

    MvcAsyncController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/api/async-inventory/{id}")
    Mono<Inventory> inventory(@PathVariable int id) {
        return client.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
~~~

Đoạn trên là snippet tích hợp, cần bean `WebClient`, dependency `spring-webflux` cung cấp client và DTO. **Nó vẫn là Spring MVC nếu app chạy trên servlet stack**, chứ không tự chuyển thành WebFlux.

Khi controller trả `Mono`, Spring MVC chuyển sang Servlet asynchronous request handling tương tự `DeferredResult`. Servlet worker ban đầu có thể được giải phóng trong lúc chờ WebClient; do vậy mô hình này có thể giảm hiện tượng servlet worker bị giữ chờ I/O như MVC RestClient synchronous.

Nhưng MVC async vẫn có Servlet async dispatch và khi stream response dạng reactive, các lần ghi trên Servlet stack có thể blocking/được chuyển tới async executor. WebFlux xử lý asynchronous/non-blocking I/O sâu trong server stack. Độ chênh thực tế phải đo theo workload và implementation, không chỉ dựa tên lớp controller.

### Bốn biến thể đáng benchmark nếu muốn công bằng

1. MVC synchronous + RestClient: đơn giản, baseline imperative.
2. MVC async + WebClient trả `Mono`: tách hiệu ứng của HTTP client blocking khỏi Servlet server model.
3. WebFlux + WebClient: toàn chuỗi HTTP I/O reactive.
4. MVC với Java virtual threads (nếu JVM/framework/config hỗ trợ): cho phép nhiều tác vụ blocking theo mô hình thread-per-request với chi phí khác platform threads, nhưng **không làm HTTP client và database tự thành non-blocking**.

Java 17 của demo **chưa có virtual threads chính thức** (được chuẩn hóa ở Java 21). Vì vậy không biến phép đo Java 17 hiện tại thành nhận định về chi phí thread trên Java 21+.

## 14. Bẫy đo đạc và vận hành thường gặp

### Chỉ đo một request

Một request chờ upstream 300 ms thường cho thời gian tương tự nhau giữa MVC và WebFlux. Khác biệt quan trọng thường nằm ở concurrency, thread/resource cost và tình huống client/network chậm. Hãy đo từ 1 → 8 → 40 → 100 requests, ghi cả latency và số lỗi, nhưng không làm quá capacity upstream nếu không định nghiên cứu nghẽn tải.

### Benchmark trên cùng process hoặc khác workload

Nếu MVC gọi DB synchronously nhưng WebFlux chỉ chờ `Mono.delay` không cần network thì **không tương đương**. Trong demo này cả hai thực hiện HTTP GET tới đúng upstream. Tuy nhiên MVC Tomcat thread limit 8 là ràng buộc cố ý, nên cần xem đó là **thí nghiệm minh họa giới hạn worker**, không phải so sánh default performance.

### Bỏ qua connection pool

WebClient Reactor Netty có pool connection và quy tắc giới hạn; RestClient phụ thuộc request factory/client cụ thể. Nếu số socket/pending acquisitions bị giới hạn, requests phải chờ dù event-loop rảnh. Cần theo dõi active/pending connections và timeout acquire khi scale.

### Dùng blocking API trong WebFlux

Một lần gọi `Thread.sleep`, JDBC/JPA blocking hoặc `block()` sai vị trí trên event-loop có thể làm nhiều connection chậm. Cần thay bằng reactive driver hoặc offload phần blocking có giới hạn; `subscribeOn(boundedElastic)` không thay đổi bản chất I/O đã blocking.

### Không xử lý chuỗi reactive rỗng

`Mono<Inventory>` có thể hoàn thành không phát dữ liệu nếu upstream trả body rỗng. Demo dùng `switchIfEmpty(Mono.error(...))` để biến thành 502, thay vì âm thầm trả empty response gây nhầm với 404 hoặc 200 null. MVC kiểm tra `result == null` tương tự.

### Log sai thông tin thread

Thread name là dấu hiệu chứ không phải metric đầy đủ. Thread có thể đổi sau async boundary, `publishOn`, `subscribeOn` hoặc I/O callbacks. Sử dụng trace IDs/correlation IDs, metrics và profiling khi cần kết luận.

### Không kiểm tra error path

Khác biệt status mapping 502/504, response body, timeout và cancel mới là điểm dễ gây bug khi đổi framework. Trước migration nên viết contract tests (happy path, missing resource, timeout, upstream 5xx, auth, validation và cancel).

### Trộn hai starters và vô tình chạy sai stack

Spring Boot ứng dụng chứa cả `spring-boot-starter-web` và `spring-boot-starter-webflux` thường tự cấu hình **Spring MVC**. Việc thấy WebClient hoặc Mono trong code không đủ để kết luận server đang chạy WebFlux. Kiểm tra dependency tree, startup logs, application context type và embedded server thật.

## 15. Checklist đưa quyết định vào dự án thực tế

| Câu hỏi | Nếu câu trả lời là... | Hướng xử lý |
| --- | --- | --- |
| Đường đi đang chờ nhiều HTTP/database I/O? | HTTP reactive nhưng DB blocking | Tính lợi ích của MVC async/WebClient và chi phí offload; không chọn WebFlux vội. |
| Phần lớn code hiện tại là imperative/JPA? | Có | MVC thường là default hợp lý, giữ contract và monitor threads. |
| Cần hàng chục nghìn socket/stream? | Có, công việc mỗi message non-blocking | WebFlux có thể là lựa chọn tốt, nhưng phải load test fan-out, pools, slow consumers. |
| Tác vụ chủ yếu CPU-bound? | Có | Tối ưu thuật toán/CPU/scheduler; reactive không tự gia tốc xử lý CPU. |
| Có nhu cầu backpressure/streaming? | Có | Đánh giá WebFlux và cách ghi response, buffering, cancellation; MVC cũng có async streaming với khác biệt I/O. |
| Có yêu cầu migration? | Có | Viết HTTP contract tests trước, thử từng endpoint, đo error rate và p95/p99. |
| Có lo dữ liệu mất/duplicate sau timeout? | Có | Thiết kế retry/idempotency, persistence, không dựa vào transport để đảm bảo. |

**Kết luận:** Trong bài toán truy vấn upstream chậm với cùng HTTP contract, MVC + RestClient chờ đồng bộ trên servlet worker; WebFlux + WebClient biểu diễn kết quả bằng `Mono` và dùng non-blocking I/O. Quan sát đồng thời thread names, in-flight requests, p95, latency, resource limits và lỗi thực tế mới cho phép đưa ra quyết định. Nếu nghiệp vụ chủ yếu blocking, MVC hoàn toàn có thể là lựa chọn đúng; nếu yêu cầu nhiều concurrent I/O và reactive end-to-end, WebFlux đáng được kiểm nghiệm.

## 16. Tài liệu tham khảo

- Spring Framework — Web MVC (Servlet stack): https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring Framework — MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — REST Clients (RestClient, WebClient): https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework — WebClient Synchronous Use: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Framework — WebClient Error Handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Reactor Core — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Spring Boot — Web Application Type and Reactive Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
