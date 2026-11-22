# Phân biệt máy chủ nhận yêu cầu với client gọi dịch vụ khác

## 1. Mục tiêu bài học

Trong Spring Boot, **cùng một tiến trình có thể vừa là HTTP server vừa là HTTP client**. Vai trò được xác định riêng cho từng HTTP exchange:

- Khi browser gửi `GET /api/items/42` tới Spring Boot, browser là client; Spring Boot là **server nhận yêu cầu**.
- Khi code Spring Boot gọi `GET http://catalog:8081/catalog/items/42`, Spring Boot lại là **client gửi yêu cầu**; catalog là server ở chặng thứ hai.
- Khi catalog trả kết quả, Spring Boot xử lý dữ liệu và **tạo một response mới** cho browser; không có quy tắc buộc hai response phải có status, header hay body giống hệt nhau.

Sau bài này, bạn có thể:

1. Phân biệt rõ **inbound** (đi vào ứng dụng) với **outbound** (đi ra khỏi ứng dụng), request với response và hai vai trò client/server.
2. Giải thích Spring MVC controller, embedded Tomcat và các HTTP client như `RestClient`, `WebClient`, `RestTemplate` và JDK `HttpClient`.
3. Chạy bài lab Java 17+/Spring Boot 3.3.5 với hai process ở port 8080 và 8081, có kết quả thành công, 404, timeout và dependency bị ngắt.
4. Hiểu vì sao `server.port` không phải port của outbound client, và vì sao thread pool server khác HTTP client connection pool.
5. Thiết kế timeout, response error mapping, xác thực service, observability và giới hạn retry.
6. Tránh nhầm CORS của browser với gọi API từ backend, và tránh lỗ hổng SSRF từ destination URL do người dùng điều khiển.

Bài thuộc nhóm **HTTP client** của Spring Boot web-runtime. Phần thực hành dùng Spring MVC đồng bộ và `RestClient`; cuối bài có đối chiếu với WebFlux reactive.

## 2. Một luồng nghiệp vụ nhưng có hai HTTP exchanges

~~~text
       Exchange A: inbound            Exchange B: outbound
Browser                         Spring Boot Gateway                Catalog Service
  |                                    |                                   |
  | GET /api/items/42                  |                                   |
  | Host: localhost:8080               |                                   |
  |----------------------------------->|                                   |
  |                                    | GET /catalog/items/42             |
  |                                    | Host: localhost:8081              |
  |                                    |---------------------------------->|
  |                                    |                                   |
  |                                    | 200 JSON: item 42                 |
  |                                    |<----------------------------------|
  |                                    |                                   |
  | 200 JSON: item 42                  |                                   |
  |<-----------------------------------|                                   |
~~~

**Exchange A:** Spring Boot có listener TCP/HTTP, nhận method, path, headers, query, body và quyết định cách xử lý. Kết quả là response A gửi ngược về browser.

**Exchange B:** Trong code xử lý A, ứng dụng quyết định gọi một URL khác. HTTP client library mở hoặc tái sử dụng kết nối tới downstream, gửi request B và nhận response B. Đây là exchange độc lập về network, HTTP method, headers, timeout và authentication.

Hai chặng có thể khác nhau:

| Thuộc tính | Exchange A (browser → gateway) | Exchange B (gateway → catalog) |
| --- | --- | --- |
| HTTP client | Browser | Spring Boot gateway |
| HTTP server | Spring Boot gateway | Catalog service |
| URL | `/api/items/42` | `/catalog/items/42` |
| Host / port ví dụ | `localhost:8080` | `localhost:8081` |
| Transport | Có thể HTTPS/HTTP2 | Có thể HTTP/1.1, HTTPS hoặc HTTP/2 độc lập |
| Credential | User cookie / token | Service credential hoặc delegation có kiểm soát |
| Timeout | Do browser/proxy quyết định | Do HTTP client gateway cấu hình |
| Status khi lỗi | Gateway chọn theo public API | Downstream trả hoặc network exception |
| Log / metric | Server-side request | Client-side dependency call |

Điểm quan trọng: gateway không biến mất khi nó gọi downstream. Nó vẫn là **server của A** đồng thời là **client của B**. Không nên hiểu “HTTP client” chỉ là frontend JavaScript hoặc ứng dụng di động.

## 3. Nhìn từ Spring Boot web runtime

~~~text
HTTP request đi vào
      |
      v
Listening socket :8080
      |
      v
Embedded Tomcat / Spring MVC DispatcherServlet
      |
      v
@RestController / @GetMapping / @PostMapping
      |
      v
Service, business rules, data mapping
      |
      +--> local computation
      |
      '--> RestClient / WebClient / HttpClient
                    |
                    v
         DNS + TCP/TLS + HTTP request outbound
                    |
                    v
          Remote HTTP server (:8081)
                    |
                    v
           Remote HTTP response
                    |
                    v
          Decode / validate / map error
                    |
                    v
         Controller returns ResponseEntity
                    |
                    v
          HTTP response của :8080
~~~

Ở chiều **server**, những thứ như `@RestController`, `@GetMapping`, `@RequestParam`, `@PathVariable`, `@RequestBody` khai báo cách xử lý request **nhận vào**. `@RestController` kết hợp chức năng controller và response-body serialization; đối tượng trả về thường được message converter như Jackson chuyển thành JSON.

Ở chiều **client**, `RestClient.get()`, `WebClient.post()` hoặc Java `HttpClient.send()` dùng để **khởi tạo request tới server khác**. Code tự chọn destination, method, body, authentication, timeout và cách xử lý response.

Ví dụ server-side API:

~~~java
@GetMapping("/api/items/{id}")
public ItemDto getItem(@PathVariable String id) {
    // Đang xử lý request inbound.
    return service.loadItem(id);
}
~~~

Ví dụ client-side API, **chỉ là đoạn bên trong method đã có RestClient**:

~~~java
ItemDto item = restClient.get()
        .uri("/catalog/items/{id}", id)
        .retrieve()
        .body(ItemDto.class);
~~~

Tên `RestClient` có chữ “Client” vì nó phát request. Tên `@RestController` chứa “Rest” nhưng bản thân annotation không tự đi gọi HTTP ở nơi khác.

## 4. server.port, baseUrl và ephemeral port không phải một

Ví dụ cấu hình:

~~~properties
# Port local mà gateway LẮNG NGHE request.
server.port=8080

# URL remote do client của gateway KẾT NỐI tới.
app.catalog.base-url=http://127.0.0.1:8081
~~~

- `server.port=8080`: embedded Tomcat nhận inbound HTTP trên 8080.
- `app.catalog.base-url`: một **custom property của ứng dụng**; Spring Boot không có sẵn property này. Code đọc nó để biết server downstream ở đâu.
- Port `8081`: đích remote HTTP server. Nó không được quyết định bởi `server.port`.
- Khi gateway gọi downstream, OS có thể chọn **ephemeral source port** khác 8080 để mở TCP connection đến `8081`. Số source port phụ thuộc hệ điều hành và tình trạng kết nối.
- Trên Kubernetes, giá trị baseUrl thường là service DNS + port nội bộ; browser có thể gọi public domain hoàn toàn khác.

Đổi `server.port` không tự sửa outbound URL. Đổi `app.catalog.base-url` không mở listener mới tại gateway. Đây là một trong những nhầm lẫn cơ bản nhất khi mới học web runtime.

## 5. Tại sao server phải gọi HTTP client?

Các mô hình thực tế:

- **Backend for Frontend (BFF):** frontend chỉ gọi một API; backend gọi catalog, pricing, stock rồi dựng DTO phù hợp UI.
- **Service-to-service:** order-service gọi inventory-service hoặc payment-service.
- **Integration:** gọi logistics, email provider, CRM, object storage API.
- **API aggregation:** lấy dữ liệu nhiều nguồn, lọc và kết hợp.
- **Authentication:** ứng dụng gọi identity provider để đổi token hoặc lấy khóa xác minh theo quy trình phù hợp.
- **Background job:** scheduled task gửi HTTP mà **không có inbound web request**.
- **Webhook workflow:** nhận webhook với vai trò server rồi gọi một downstream API với vai trò client.

Một ứng dụng không bắt buộc phải gọi HTTP để truy cập database; JDBC/R2DBC là protocol khác. Một app sử dụng message broker cũng có thể không dùng HTTP outbound. Chỉ khi **nó phát HTTP request** thì vai trò HTTP client ở chặng đó mới xuất hiện.

## 6. Chọn HTTP client Java/Spring phù hợp

| API | Phong cách | Khi nên dùng |
| --- | --- | --- |
| `RestClient` | Đồng bộ, fluent API | Spring MVC/service imperative trên Spring Framework 6.1+ |
| `RestTemplate` | Đồng bộ, template methods | Project cũ đang sử dụng; bảo trì/migration dần |
| `WebClient` | Reactive, publisher `Mono/Flux` | Spring WebFlux hoặc pipeline async/non-blocking |
| `java.net.http.HttpClient` | JDK 17, `send`/`sendAsync` | Java core không muốn dùng Spring API |
| HTTP service interfaces | Java interface + annotation, backed by RestClient/WebClient | Muốn mô hình hóa contract client rõ ràng |

Trong Spring Boot 3.3, `RestClient.Builder` được Boot auto-configure cho ứng dụng không phải reactive web application khi classpath phù hợp. Inject builder giúp giữ converters và các customizers do Boot thiết lập; có thể cấu hình base URL/request factory cho từng dependency.

**RestClient là synchronous API**: khi gọi `retrieve().body(...)`, thread chờ response hoặc exception. **WebClient là reactive API**: trả `Mono`/`Flux`, và network I/O diễn ra khi pipeline được subscribe. Không gọi `block()` ngay trong WebFlux event-loop handler để biến API reactive thành blocking.

`RestTemplate` không biến mất khỏi các dự án Boot 3.3; nó là client cũ nhưng vẫn thường dùng. `HttpClient` của Java 17 cũng không phải HTTP server dù dùng chữ Client trong class name.

## 7. Lab đầy đủ: Spring Boot là server và đồng thời là HTTP client

Chúng ta dựng **hai tiến trình thật** trên máy local:

- **Downstream catalog**: một server HTTP từ JDK 17, lắng nghe `127.0.0.1:8081` và trả JSON.
- **Spring Boot gateway**: web server MVC tại `127.0.0.1:8080`, nhận inbound request rồi dùng `RestClient` gọi catalog tại port 8081.

Không cần Docker, database hay một project Spring Boot thứ hai. HTTP server downstream dùng module `jdk.httpserver` của JDK để tập trung quan sát hai vai trò HTTP.

### 7.1. Cấu trúc dự án

~~~text
http-client-roles/
├── downstream/
│   └── CatalogStubServer.java
└── gateway/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/gateway/
        │   ├── GatewayApplication.java
        │   ├── CatalogClient.java
        │   ├── GatewayController.java
        │   ├── ItemDto.java
        │   └── ErrorDto.java
        └── resources/
            └── application.properties
~~~

`downstream` và `gateway` là hai process riêng. Chỉ thư mục `gateway` chứa Maven `pom.xml` và được Spring Boot chạy qua Maven.

### 7.2. Downstream server: CatalogStubServer.java

**Tệp `downstream/CatalogStubServer.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class CatalogStubServer {

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8081), 0);

        server.createContext(
                "/catalog/items/", CatalogStubServer::handle);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();

        System.out.println(
                "CatalogStub listening on http://127.0.0.1:8081");
    }

    private static void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        String id = path.substring("/catalog/items/".length());

        System.out.printf(
                "DOWNSTREAM %s %s%n",
                exchange.getRequestMethod(), path);

        int status;
        String json;

        if (!"GET".equals(exchange.getRequestMethod())) {
            status = 405;
            json = "{\"error\":\"METHOD_NOT_ALLOWED\"}";
            exchange.getResponseHeaders().set("Allow", "GET");
        } else if ("42".equals(id)) {
            status = 200;
            json = "{\"id\":\"42\",\"name\":\"Book\",\"price\":120}";
        } else if ("slow".equals(id)) {
            try {
                Thread.sleep(2500);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
            status = 200;
            json = "{\"id\":\"slow\",\"name\":\"Slow Book\",\"price\":130}";
        } else {
            status = 404;
            json = "{\"error\":\"ITEM_NOT_FOUND\"}";
        }

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
~~~

Các điểm cần quan sát:

1. `HttpServer.create(...)` và `start()` mở **listener HTTP port 8081**; nó thực sự là server của downstream.
2. `createContext` định nghĩa route server-side `/catalog/items/`.
3. `id=42` trả JSON 200, `id=slow` cố ý chậm 2,5 giây, ID khác trả JSON 404.
4. Log `DOWNSTREAM GET ...` chỉ xuất hiện khi có request **đến downstream**, dù caller là browser trực tiếp hay gateway.
5. Thread pool 4 của stub xử lý inbound trên port 8081; không phải pool client outbound ở gateway.
6. Server stub chỉ dành cho lab; không có TLS, authentication hay graceful shutdown như production.

Chạy trong terminal A:

~~~bash
cd http-client-roles/downstream
javac --add-modules jdk.httpserver CatalogStubServer.java
java --add-modules jdk.httpserver CatalogStubServer
~~~

Kỳ vọng stdout khi server khởi động:

~~~text
CatalogStub listening on http://127.0.0.1:8081
~~~

Gọi trực tiếp downstream bằng curl từ terminal khác:

~~~bash
curl -i http://127.0.0.1:8081/catalog/items/42
curl -i http://127.0.0.1:8081/catalog/items/unknown
~~~

Request đầu thường trả 200 JSON `{"id":"42","name":"Book","price":120}`; request thứ hai trả 404. Lúc này Spring Boot gateway chưa cần hoạt động.

### 7.3. Gateway pom.xml

**Tệp `gateway/pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>http-client-roles-gateway</artifactId>
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

`spring-boot-starter-web` cung cấp MVC, embedded Tomcat, `spring-web` có `RestClient` và Jackson để serialize/deserialize JSON. Không cần `spring-boot-starter-webflux` cho lab đồng bộ này.

### 7.4. application.properties

**Tệp `gateway/src/main/resources/application.properties`:**

~~~properties
# INBOUND listener ở Spring Boot.
server.address=127.0.0.1
server.port=8080

# OUTBOUND destination, là custom property của project.
app.catalog.base-url=http://127.0.0.1:8081
~~~

Cả hai địa chỉ dùng loopback để tránh phơi server demo ra mạng. Trong production/Kubernetes, cần network interfaces, DNS, Service và chính sách egress phù hợp. Đừng copy nguyên `127.0.0.1` vào môi trường có downstream nằm ở container/pod khác: `localhost` ở mỗi container trỏ về chính container đó.

### 7.5. Spring Boot main class

**Tệp `gateway/src/main/java/com/example/gateway/GatewayApplication.java`:**

~~~java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

Class trên khởi động Spring web application; việc mở inbound listener xảy ra nhờ Spring Boot/embedded server, không phải vì code trong main gọi RestClient.

### 7.6. DTO: Java 17 records

**Tệp `gateway/src/main/java/com/example/gateway/ItemDto.java`:**

~~~java
package com.example.gateway;

public record ItemDto(String id, String name, int price) {
}
~~~

**Tệp `gateway/src/main/java/com/example/gateway/ErrorDto.java`:**

~~~java
package com.example.gateway;

public record ErrorDto(String code, String message) {
}
~~~

Jackson có thể dùng các record để chuyển JSON thành Java và ngược lại. DTO của gateway có thể giống hoặc khác schema downstream; trong lab chúng giống nhau để tập trung vào vai trò HTTP.

### 7.7. CatalogClient — HTTP client thực sự

**Tệp `gateway/src/main/java/com/example/gateway/CatalogClient.java`:**

~~~java
package com.example.gateway;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient restClient;

    public CatalogClient(
            RestClient.Builder builder,
            @Value("${app.catalog.base-url}") String baseUrl) {

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(Duration.ofMillis(800));
        factory.setReadTimeout(Duration.ofMillis(1200));

        this.restClient = builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    public ItemDto fetch(String id) {
        return restClient.get()
                .uri("/catalog/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(ItemDto.class);
    }
}
~~~

Giải thích chi tiết:

- `@Service` đánh dấu thành phần nghiệp vụ có thể được controller inject; nó không mở listener HTTP mới.
- Spring Boot 3.3 cung cấp `RestClient.Builder` cho ứng dụng MVC khi dependency phù hợp. Dùng builder injected giúp giữ các cấu hình chung của Boot; `baseUrl` xác định remote service.
- `SimpleClientHttpRequestFactory` dựa trên JDK `HttpURLConnection`, phù hợp ví dụ sync đơn giản. Nó **không phải Apache HTTP connection pool** có sẵn. Khi production cần connection pooling, chọn request factory/client implementation phù hợp và đo pool.
- `connectTimeout` 800 ms bảo vệ việc chờ thiết lập kết nối; `readTimeout` 1200 ms bảo vệ đọc dữ liệu từ socket. Read timeout **không nhất thiết** là deadline tổng từ lúc gọi tới lúc response hoàn tất.
- `.get()` và `.uri("/catalog/items/{id}", id)` tạo outbound GET độc lập; URI template xử lý path variable thay cho nối string URL từ dữ liệu tùy ý.
- `.accept(MediaType.APPLICATION_JSON)` gửi header `Accept: application/json` **cho downstream**, không làm thay đổi request inbound của browser.
- `retrieve().body(ItemDto.class)` thực hiện exchange và parse JSON thành Java record; dòng này là **blocking/synchronous** trong RestClient.
- Theo cơ chế mặc định, response 4xx/5xx phát exception thuộc `RestClientResponseException` hoặc subclass; lỗi connect/read có thể thành `ResourceAccessException`.

Trong lab, URL đích là trusted config, không đến trực tiếp từ tham số `url` của browser. Đây cũng là cách đơn giản nhất để hạn chế nguy cơ SSRF.

### 7.8. GatewayController — nhận inbound và chọn public response

**Tệp `gateway/src/main/java/com/example/gateway/GatewayController.java`:**

~~~java
package com.example.gateway;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api/items")
public class GatewayController {

    private final CatalogClient catalogClient;

    public GatewayController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> one(@PathVariable String id) {
        if (!id.matches("[A-Za-z0-9-]{1,30}")) {
            return ResponseEntity.badRequest()
                    .body(new ErrorDto("INVALID_ID", "ID is invalid"));
        }

        try {
            ItemDto item = catalogClient.fetch(id);

            if (item == null) {
                return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                        .body(new ErrorDto(
                                "EMPTY_UPSTREAM_BODY",
                                "Catalog returned an empty body"));
            }

            return ResponseEntity.ok(item);

        } catch (HttpClientErrorException.NotFound ex) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorDto(
                            "ITEM_NOT_FOUND", "No matching item"));

        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorDto(
                            "CATALOG_HTTP_ERROR",
                            "Catalog service returned an error"));

        } catch (ResourceAccessException ex) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(new ErrorDto(
                            "CATALOG_UNAVAILABLE",
                            "Catalog service cannot be reached in time"));

        } catch (RestClientException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorDto(
                            "CATALOG_CLIENT_ERROR",
                            "Cannot process catalog response"));
        }
    }
}
~~~

Controller minh họa một ranh giới API rõ ràng:

1. `@GetMapping("/{id}")` **nhận inbound request** ở gateway. Route public là `GET /api/items/{id}`.
2. Phần kiểm tra ID là validation trước khi tạo request outbound.
3. `catalogClient.fetch(id)` làm gateway trở thành **HTTP client** của catalog-service.
4. Downstream trả 200 + JSON đúng schema → gateway trả 200 + `ItemDto` do chính gateway serialize.
5. Downstream trả 404 → `RestClient` báo `HttpClientErrorException.NotFound` → gateway quyết định trả 404 với `ErrorDto` khác body downstream.
6. Downstream trả HTTP error khác → gateway chọn 502 trong lab; production cần phân biệt business errors, rate limits, auth failures và các policy nghiệp vụ.
7. Network/connect/read lỗi → `ResourceAccessException` → gateway chọn 503 **theo chính sách demo**. Không coi đây là status do Spring tự dùng cho mọi timeout; nhiều gateway chọn 504 nếu phân loại chính xác timeout.
8. Không trả nguyên stack trace, internal hostname, raw upstream body hoặc service credentials cho browser.

**Thứ tự catch:** 404 subclass phải đứng trước `RestClientResponseException` chung; `ResourceAccessException` phải đứng trước `RestClientException` chung.

## 8. Chạy và quan sát hai exchanges

### 8.1. Terminal A — downstream

~~~bash
cd http-client-roles/downstream
javac --add-modules jdk.httpserver CatalogStubServer.java
java --add-modules jdk.httpserver CatalogStubServer
~~~

Đảm bảo process này vẫn chạy ở `127.0.0.1:8081`.

### 8.2. Terminal B — Spring Boot gateway

~~~bash
cd http-client-roles/gateway
mvn spring-boot:run
~~~

Tomcat sẽ lắng nghe `127.0.0.1:8080`. Dùng JDK 17+ và Maven 3.9+; không chạy trùng port. Trong PowerShell, có thể thực hiện các lệnh tương tự, còn trình duyệt/curl truy cập URL như nhau.

### 8.3. Terminal C — gọi gateway

~~~bash
curl -i http://127.0.0.1:8080/api/items/42
~~~

Nội dung response kỳ vọng có cấu trúc:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"id":"42","name":"Book","price":120}
~~~

Đây là đoạn tiêu biểu, không phải output byte-for-byte; header `Date`, thứ tự header, content length và formatting có thể khác. Ở **terminal A**, log có thêm:

~~~text
DOWNSTREAM GET /catalog/items/42
~~~

Điều này chứng minh gateway **đã khởi tạo một HTTP request mới** đến catalog. Ở browser/curl bạn chỉ gọi `:8080`, nhưng service backend thật sự nhận HTTP ở `:8081`.

### 8.4. Kiểm tra 404

~~~bash
curl -i http://127.0.0.1:8080/api/items/unknown
~~~

Downstream trả:

~~~json
{"error":"ITEM_NOT_FOUND"}
~~~

Gateway trả body **khác** theo contract của mình:

~~~json
{"code":"ITEM_NOT_FOUND","message":"No matching item"}
~~~

Hai response cùng status 404 là **kết quả của chính sách map trong gateway**, không phải vì response B tự động trở thành response A. Gateway có thể chọn status khác nếu semantics nghiệp vụ yêu cầu.

### 8.5. Kiểm tra downstream chậm

~~~bash
curl -i http://127.0.0.1:8080/api/items/slow
~~~

CatalogStub sleep 2,5 giây, trong khi RestClient có `readTimeout` 1,2 giây. Trong điều kiện lab, gateway thường gặp `ResourceAccessException` rồi trả 503 với:

~~~json
{"code":"CATALOG_UNAVAILABLE","message":"Catalog service cannot be reached in time"}
~~~

Thời gian và exception chính xác có thể khác do OS, scheduling và connection conditions. Downstream có thể phát lỗi ghi response sau khi gateway đã ngừng chờ. **Timeout ở client không đồng nghĩa remote đã hủy mọi tác vụ**.

### 8.6. Kiểm tra dependency down

Dừng terminal A bằng `Ctrl+C` nhưng giữ gateway chạy, rồi gọi lại:

~~~bash
curl -i http://127.0.0.1:8080/api/items/42
~~~

Gateway vẫn **nhận inbound request** nhưng không kết nối downstream được; trong lab thường trả 503. Đây là tình huống ứng dụng web server còn sống nhưng một HTTP dependency không sẵn sàng. Khởi động lại catalog sẽ giúp request thành công mà không cần restart gateway.

### 8.7. Đóng gói gateway

Trong thư mục `gateway`, sau khi dừng instance Maven nếu cần:

~~~bash
mvn clean package
java -jar target/http-client-roles-gateway-0.0.1-SNAPSHOT.jar
~~~

Executable JAR chỉ chứa gateway. Downstream JDK HttpServer vẫn cần chạy riêng ở port 8081.

## 9. Response downstream không tự là response gateway

Khi gọi remote API, có ít nhất ba kết quả:

1. **HTTP response hợp lệ**: downstream trả status, headers, body; gateway có thể chuyển đổi DTO hoặc chọn response.
2. **HTTP error response**: downstream trả 4xx/5xx; `RestClient.retrieve()` thông thường báo exception, gateway cần bắt/biến đổi.
3. **Không có HTTP response**: DNS lỗi, TLS handshake, TCP refused, read timeout, reset; gateway cần xử lý exception ở tầng client/network.

Ví dụ upstream 401 vì **service token của gateway** hết hạn. Điều này không tự có nghĩa user chưa login vào gateway. Nếu gateway forward nguyên 401, frontend có thể đăng xuất người dùng sai. Cần phân biệt **authorization lỗi tại downstream** với **authorization của caller inbound**.

| Downstream case | Gateway có thể trả | Lý do |
| --- | --- | --- |
| 200 JSON hợp lệ | 200 DTO public | Thành công theo hợp đồng |
| 201 Created | 201 khi public API thực sự tạo resource | Có thể rewrite `Location` thành URL public |
| 204 No Content | 204/empty | Không parse body rỗng thành object bắt buộc |
| 400 | 400 hoặc 502 theo nguồn lỗi | Có thể do input không hợp lệ hoặc gateway tạo request sai |
| 401/403 | 502/503 hoặc code domain thích hợp | Cần xác định service credential vs user auth |
| 404 | 404 nếu thực sự là domain item không tồn tại | Lab cố ý map thành public 404 |
| 409 | 409 khi có business conflict thật | Không luôn coi là network failure |
| 429 | Backoff/rate limit, 429 hoặc 503 tùy contract | Tránh tạo retry storm |
| 5xx | 502/503 theo policy | Cần quan sát service lỗi |
| Connect/read timeout | 503/504 tùy phân loại | Không có response upstream đầy đủ |
| Invalid JSON/schema | 502/integration error | Validate và version hóa contract |

Không copy nguyên raw response body chứa stack trace hoặc chi tiết database nội bộ ra browser. Một gateway có nhiệm vụ giữ **public contract ổn định**, kể cả khi dịch vụ downstream thay đổi.

## 10. HTTP body: đọc inbound khác gửi outbound

Server controller:

~~~java
@PostMapping("/api/orders")
public ResponseEntity<?> create(@RequestBody OrderRequest request) {
    // @RequestBody đọc JSON inbound thành Java object.
    return ...;
}
~~~

HTTP client:

~~~java
OrderResult result = restClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new OrderRequest("42", 2))
        .retrieve()
        .body(OrderResult.class);
~~~

Đây là **hai snippet minh họa không chạy độc lập**: cần định nghĩa `OrderRequest`, `OrderResult`, `restClient`, imports và method/class phù hợp. Điểm khác nhau:

- `@RequestBody` trên controller: lấy **request body inbound**.
- `RestClient.body(...)`: tạo **request body outbound**.
- `RestClient.retrieve().body(Class)`: đọc **response body outbound**.
- `ResponseEntity` ở controller: tạo **response inbound** gửi lại caller.

Header `Content-Type` mô tả loại body của message được gửi; `Accept` nói client muốn nhận loại nội dung nào. Hai exchange có headers riêng, không cần giống nhau.

## 11. Header, cookie và token không tự truyền qua HTTP client

Một browser có thể gửi:

~~~http
GET /api/items/42 HTTP/1.1
Host: api.example.com
Cookie: SESSION=...
Authorization: Bearer <user-token>
X-Request-Id: req-123
~~~

Gateway gọi downstream:

~~~http
GET /catalog/items/42 HTTP/1.1
Host: catalog.internal:8081
Authorization: Bearer <service-token>
X-Request-Id: req-123
Accept: application/json
~~~

Các header trên là ví dụ kiến trúc, không phải log của lab. Việc chuyển correlation ID hoặc token phải được code/config quyết định.

**Không copy vô điều kiện:**

- `Host`: phải là host upstream thực.
- `Cookie`: session của browser có thể không thuộc downstream; chuyển đi gây rò credential.
- `Authorization`: user token có audience/scope riêng; nếu cần delegation, làm theo auth flow được thiết kế.
- `Content-Length`: phải tương ứng với body bytes thực của outbound message.
- `Connection` và hop-by-hop headers: không được forward bừa.
- `Set-Cookie`: cookie downstream thường không nên phát thẳng cho public browser.
- `Location`: redirect upstream có thể trỏ tới internal hostname.
- `X-Forwarded-*`: phải tuân thủ trusted proxy chain, không tin giá trị từ client giả mạo.
- `Content-Encoding`: nếu gateway đã decode/transform body, không giữ header của representation cũ.

Với distributed tracing, propagation các header chuẩn như `traceparent` cần instrumentation và trust/PII policy; **không cần copy mọi header** để có correlation.

## 12. CORS không cấm RestClient gọi downstream

CORS là cơ chế **browser** sử dụng để kiểm soát JavaScript ở origin A đọc response từ origin B. HTTP client server-side như `RestClient` không chạy trong browser nên **không bị browser CORS check**.

Ví dụ:

~~~text
Browser JS from http://localhost:5173
  -> http://localhost:8080/api/items/42
  -> có thể cần CORS config trên gateway

Spring Boot RestClient at localhost:8080
  -> http://localhost:8081/catalog/items/42
  -> không cần catalog phát Access-Control-Allow-Origin
     chỉ để server-side Java đọc response
~~~

Đừng cấu hình `@CrossOrigin("*")` ở mọi service chỉ vì gateway không gọi được. Nếu lỗi xảy ra ở RestClient, thường cần kiểm tra DNS, network, URL, TLS, auth, status, timeout hoặc response format. CORS **không thay thế authentication hoặc firewall**: curl/backend client có thể gọi API mà browser JavaScript bị policy chặn.

## 13. Thread pool inbound và connection pool outbound khác nhau

Với Spring MVC/RestClient đồng bộ:

~~~text
Tomcat request worker
  -> GatewayController
  -> CatalogClient.fetch
  -> chờ outbound connect / response / timeout
  -> map ItemDto hoặc lỗi
  -> gửi response inbound
~~~

Nếu 20 request cùng chờ catalog chậm, nhiều Tomcat workers có thể bị giữ trong thời gian chờ. Nhưng số Tomcat workers và số outbound TCP connections **không phải cùng một cấu hình**.

Ví dụ **giả định** khi có HTTP client pool:

~~~text
Tomcat request threads max = 20
Outbound client max connections to catalog = 5

20 inbound calls cần catalog
  -> 5 leased outbound connections
  -> 15 pending/acquire timeout nếu mọi connection bận
~~~

Mô hình này giải thích contention, **không phải thiết lập của lab**. Lab dùng `SimpleClientHttpRequestFactory`/URLConnection, không có Apache HttpClient pool max=5. Để dùng pool, chọn HTTP client implementation có pooling và cấu hình đúng.

Cần xét:

- Inbound Tomcat thread pool, accept queue, connection timeout.
- Outbound connection pooling, connection acquisition time, DNS/TLS, socket timeouts.
- Downstream server worker threads/event loops và database pool.
- Fan-out: một inbound request có thể tạo nhiều outbound calls.
- Retries: nếu mỗi lỗi retry nhiều lần, downstream load có thể tăng mạnh.
- Memory/CPU, connection churn, ephemeral port exhaustion.

Đừng tăng `server.tomcat.threads.max` để “sửa” outbound read timeout, và cũng đừng tăng client pool vô hạn khi downstream không đủ năng lực.

### 13.1. Little’s Law giúp nhìn concurrency

\[
L = \lambda W
\]

Nếu outbound arrival rate ổn định khoảng 50 calls/giây và thời gian gọi trung bình 0,2 giây, số calls đang xử lý trung bình xấp xỉ 10. Đây là ví dụ toán học, **không** phải số thread cần cấu hình. Queue time, retries và p99 có thể làm số pending cao hơn; hãy xác định cùng measurement boundary khi áp dụng.

## 14. Timeout có nhiều lớp

~~~text
Browser client deadline
       |
Reverse proxy timeout
       |
Spring Boot inbound handler
       |
Outbound HTTP client connect/read/response timeout
       |
Downstream server queue + business + DB timeout
~~~

**Kết nối thành công** chưa phải **nhận response thành công**:

- **Connect timeout**: giới hạn một giai đoạn thiết lập kết nối TCP theo semantics của client.
- **Read/response timeout**: giới hạn chờ dữ liệu/response theo client implementation; nhiều implementation dùng read inactivity timeout chứ không phải total deadline.
- **Overall deadline**: ngân sách thời gian của toàn nghiệp vụ, phải tính queue, retry, parse/transform và phản hồi.
- **Server idle/connection timeout**: tài nguyên cho inbound socket, không phải outbound dependency timeout.
- **Proxy timeout**: reverse proxy có ngân sách riêng và có thể kết thúc kết nối trước gateway.

Trong lab, `readTimeout=1200ms` chủ động thấp hơn `Thread.sleep(2500)` ở stub để minh họa lỗi. Khi production, hãy đặt timeout theo SLO và ngân sách còn lại của caller; tránh retry vượt deadline. Timeout không hủy chắc chắn công việc đã được remote nhận.

## 15. WebFlux WebClient: vẫn là hai vai trò HTTP

Nếu server được viết bằng Spring WebFlux, endpoint nhận request thường trả `Mono/Flux`, còn client reactive thường là `WebClient`. Hai vai trò vẫn độc lập.

Cấu hình bean **dành cho project WebFlux riêng**:

~~~java
package com.example.reactive;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OutboundConfig {
    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            @Value("${app.catalog.base-url}") String url) {
        return builder.baseUrl(url).build();
    }
}
~~~

Controller reactive:

~~~java
package com.example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ReactiveGatewayController {
    private final WebClient catalogWebClient;

    public ReactiveGatewayController(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    @GetMapping("/{id}")
    public Mono<ItemDto> one(@PathVariable String id) {
        return catalogWebClient.get()
                .uri("/catalog/items/{id}", id)
                .retrieve()
                .bodyToMono(ItemDto.class);
    }
}
~~~

Hai snippet là **ví dụ cấu hình/handler riêng**, chưa phải project độc lập: cần dependency `spring-boot-starter-webflux`, `ItemDto` record cùng package, app main và property base URL. Không đặt controller reactive có cùng route vào project MVC lab.

`Mono<ItemDto>` là publisher; WebFlux runtime subscribe để thực hiện outbound HTTP rồi viết inbound response. `retrieve()` phát error signal cho các status lỗi; project thật cần `onStatus`/`onErrorResume` và timeout phù hợp. **Không gọi `.block()` trong WebFlux event-loop handler** vì sẽ chặn thread, gây mất lợi ích reactive hoặc bị Reactor từ chối blocking.

Có thể dùng `WebClient` trong ứng dụng MVC để gọi outbound; chỉ cần `WebClient` trên classpath không biến MVC thành WebFlux. Khi cả starter-web và starter-webflux cùng có mặt, Spring Boot 3.3 thông thường ưu tiên MVC khi tự xác định web application type.

### 15.1. Java 17 HttpClient

JDK 17 có `java.net.http.HttpClient` với `send` synchronous và `sendAsync` asynchronous:

~~~java
// Đoạn trong một method throws Exception; cần imports
// java.net.URI và java.net.http.HttpClient/HttpRequest/HttpResponse.
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:8081/catalog/items/42"))
        .GET()
        .build();
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
System.out.println(response.body());
~~~

Đây là đoạn **không độc lập** chứ không phải class đầy đủ. Nó chứng minh HTTP client không nhất thiết phải là Spring-specific API; Java process vẫn có thể gửi request tới service khác.

## 16. Retry, idempotency và circuit breaker

Khi downstream lỗi/timeout, có thể cần retry, nhưng **không retry mù quáng**:

- GET đọc dữ liệu có thể phù hợp retry có giới hạn khi lỗi tạm thời, nhưng vẫn tốn capacity và có thể có side effects không đúng thiết kế.
- POST tạo đơn/thanh toán có thể đã được downstream thực hiện trước khi gateway timeout. Retry có thể tạo **đơn hoặc giao dịch trùng**.
- Cần retry budget, exponential backoff/jitter, tổng deadline, max attempts và thông tin từ `Retry-After` nếu phù hợp.
- **Idempotency key** hoặc cơ chế deduplication bên downstream quan trọng cho operation ghi.
- **Circuit breaker** có thể tạm ngắt call tới dependency lỗi nhiều; **bulkhead** giới hạn số call đồng thời để bảo vệ gateway.

Lab không cài Spring Cloud CircuitBreaker/Resilience4j, nên không tự có retry/circuit breaker. Chỉ áp dụng khi nghiệp vụ cho phép và có metrics.

## 17. Authentication giữa caller và downstream

Một user đã login vào gateway chưa chắc có credential hợp lệ với catalog/payment service. Có các mô hình:

1. **Service identity:** gateway dùng service account/OAuth client credentials hoặc mTLS để gọi downstream.
2. **Token delegation:** gửi token đại diện user đã được cấp đúng audience/scope nếu service cần kiểm soát theo user.
3. **Gateway authorization:** gateway xác thực user và chỉ gọi service nội bộ với quyền giới hạn; downstream vẫn nên có network/service identity controls.
4. **Không xác thực**: chấp nhận trong lab loopback, không là mặc định production.

**Không chuyển thẳng user bearer token tới mọi downstream**. Một token có audience của gateway có thể không hợp lệ ở catalog, và việc phát tán nó làm tăng rủi ro. Credential client cần rotate, bảo vệ khỏi log, hạn chế scope và được đưa qua HTTPS/mTLS phù hợp.

TLS giữa browser–gateway không tự bảo vệ đường gateway–downstream; đây là hai kết nối riêng. Nếu traffic backend cần mã hóa, dùng HTTPS tới downstream và xác minh certificate/hostname. Không dùng trust-all SSL trong production.

## 18. Chặn SSRF khi thiết kế outbound URL

Anti-pattern:

~~~java
@GetMapping("/fetch")
public String fetch(@RequestParam String url) {
    // KHÔNG AN TOÀN: caller tự chọn host để server kết nối.
    return RestClient.create()
            .get().uri(url).retrieve().body(String.class);
}
~~~

Đây là **mã minh họa cố tình không an toàn**, không được đưa vào production. Attacker có thể yêu cầu gateway gọi cloud metadata endpoint, private IP, localhost admin API hoặc các địa chỉ vượt khỏi quyền network của browser — **Server-Side Request Forgery (SSRF)**.

Biện pháp:

- Fixed `baseUrl` từ server config; chỉ nhận resource ID/path data có validation và URI template.
- Nếu thật sự phải gọi arbitrary URLs, allowlist strict scheme/host/port, kiểm tra DNS rebinding, redirect và dải IP private/link-local theo threat model.
- Network egress policies chặn những destination không cần.
- Giới hạn request/response size, redirects, timeout, protocol và content type.
- Không để user kiểm soát outbound `Authorization`, `Host` hoặc proxy settings.

Trong lab, `app.catalog.base-url` được cấu hình phía server và `id` chỉ được phép chữ, số, dấu gạch ngang — một ví dụ đơn giản về ranh giới này.

## 19. Tracing và metrics: quan sát server lẫn client

Một distributed trace của request đi qua hai services có thể trông như:

~~~text
Trace ID: trace-abc
  SERVER span: GET /api/items/{id}                (gateway)
    CLIENT span: GET /catalog/items/{id}          (gateway)
      SERVER span: GET /catalog/items/{id}        (catalog)
~~~

Trên thực tế, cần cấu hình Micrometer Observation/Tracing, exporter, trace context propagation (ví dụ W3C `traceparent`) và sampling; lab hiện tại chỉ log downstream request, **không tự tạo distributed trace**.

Nên đo riêng:

| Nhóm | Metric/log quan trọng |
| --- | --- |
| Inbound server | Requests/s, status 2xx/4xx/5xx, p95/p99, active threads/connections |
| Outbound client | Dependency/URI template, status, timeout, latency, retry count |
| Connection pool | Active, idle, pending acquisition, failures |
| Downstream | Queue time, DB query latency, 429/5xx, saturation |
| Tracing | Trace ID, client/server spans, context propagation |
| Reliability | Circuit breaker state, fallback rate, timeouts, errors |

Không log raw `Authorization`, session cookies, private keys, PII hoặc toàn bộ request/response body nhạy cảm. Không dùng high-cardinality full URL với user IDs cho mọi metric label nếu có thể dùng route template.

## 20. Những lỗi thường gặp

| Triệu chứng | Nhầm lẫn/nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Spring Boot chạy 8080 nhưng không gọi được 8081 | Downstream chưa chạy hoặc URL sai | Gọi trực tiếp `curl :8081`, kiểm tra process/network |
| Đổi `server.port` nhưng remote client vẫn gọi URL cũ | Listener khác destination | Sửa `app.catalog.base-url` |
| Controller trả 200 nhưng catalog không có log | Code không thực sự gọi client hoặc có cache | Kiểm tra service path và downstream log |
| Gateway trả 503 khi catalog stop | Outbound connect refused/timeout | Log exception client, phân biệt với server listener |
| Downstream trả 404 nhưng JSON public khác | Gateway map/transform response | Đây là hành vi có chủ đích theo contract |
| JSON decode lỗi khi upstream 200 | Schema/media type không đúng | Kiểm tra DTO/version, map lỗi integration |
| Browser báo CORS nhưng RestClient vẫn chạy | CORS áp cho browser, không áp cho Java HTTP client | Kiểm tra CORS tại gateway inbound |
| Spring Security login ở gateway nhưng downstream 401 | Thiếu/sai service credentials | Dùng service identity/delegation phù hợp |
| Timeout lớn dù server threads rảnh | Outbound pool/network/remote chậm | Đo client latency, pool, DNS/TLS, upstream |
| Tomcat workers đầy | Quá nhiều blocking calls | Giới hạn concurrency, timeout, pool, bulkhead |
| WebFlux giật/treo | Blocking `RestClient`/`block()` trên event loop | Giữ reactive WebClient hoặc offload có kiểm soát |
| API trả internal host trong Location | Forward raw upstream headers | Rewrite public URL, lọc hop-by-hop headers |
| Retry làm tạo đơn trùng | Không có idempotency key | Bổ sung deduplication, retry policy |
| TLS handshake thất bại | Certificate/hostname/truststore sai | Cấp CA/SAN đúng, không tắt verify |
| URL client nhận từ query parameter | SSRF | Fixed destination và egress policy |
| 200 từ health endpoint nhưng gọi downstream 503 | Gateway sống, dependency down | Đo readiness/dependency health độc lập |

### Quy trình debug theo 7 bước

1. **Inbound:** URL/method đúng, listener port nào, controller route nào?
2. **Outbound:** method nào gọi RestClient/WebClient, base URL và path thực tế là gì?
3. **Network:** DNS, TCP, TLS, firewall/proxy/egress có cho phép không?
4. **Downstream:** status, headers, content type và JSON schema thực?
5. **Mapping:** gateway bắt exception nào, chuyển thành status/body gì?
6. **Timeout/concurrency:** server threads, client pool, queueing, read/response timeout, retry budgets?
7. **Tracing:** có correlation/trace context và metrics ở cả hai chặng hay chỉ access log của server?

Đừng chỉ thấy gateway 500 rồi đoán embedded Tomcat lỗi; sự cố có thể nằm ở outbound HTTP call, decode JSON hoặc service downstream.

## 21. Bài tập và đáp án

**Câu 1.** Browser gọi `:8080/api/items/42` và gateway gọi `:8081/catalog/items/42`. Ai là client/server ở mỗi chặng?

**Câu 2.** Vì sao việc có `@RestController` không đồng nghĩa ứng dụng đã thực hiện HTTP client call?

**Câu 3.** `@RequestBody` trong controller khác `RestClient.post().body(...)` ra sao?

**Câu 4.** Khi catalog trả 401 vì service token hết hạn, có nên mặc định chuyển 401 cho browser không?

**Câu 5.** Vì sao CORS có thể chặn JavaScript gọi gateway nhưng không chặn RestClient gọi catalog?

**Câu 6.** Nếu catalog xử lý POST thành công nhưng response bị mất, retry POST có rủi ro gì?

**Câu 7.** Một ứng dụng chạy WebFlux dùng `RestClient.retrieve().body()` trong event-loop handler. Vấn đề gì?

**Câu 8.** Có 100 inbound requests/s và mỗi request gọi ba downstream services. Vì sao outbound RPS có thể vượt inbound RPS?

**Câu 9.** Thay `server.port` từ 8080 sang 9090 có thay địa chỉ `127.0.0.1:8081` của RestClient không?

**Câu 10.** Vì sao cho user cung cấp nguyên `url` để gateway gọi HTTP là thiết kế có nguy cơ?

**Câu 11.** Spring Boot trả 503 khi catalog ngừng hoạt động nhưng ứng dụng vẫn khởi động tốt. Điều đó chứng minh gì?

**Câu 12.** Gửi client token/cookie inbound nguyên vẹn sang downstream có luôn đúng không?

**Đáp án định hướng:**

1. Chặng A: browser client, gateway server. Chặng B: gateway client, catalog server.
2. Controller chỉ khai báo handler nhận request; muốn phát outbound HTTP cần gọi client API bằng code hoặc framework tương ứng.
3. `@RequestBody` đọc inbound body, `RestClient.body(...)` gửi outbound body.
4. Không mặc định; có thể là lỗi xác thực workload nội bộ, cần map lỗi phù hợp.
5. CORS do browser cưỡng chế với script cross-origin; backend HTTP clients không bị browser thực thi CORS.
6. Có thể tạo duplicate order/payment; cần idempotency key và retry policy.
7. Blocking event loop, gây latency/saturation; nên compose WebClient reactive.
8. Fan-out: 100 inbound × 3 = 300 outbound calls/s (chưa tính retry/cache).
9. Không, listener port và remote destination độc lập.
10. SSRF vào các IP/hosts nội bộ hoặc metadata endpoints; cần allowlist/fixed destination.
11. Inbound server có thể sống trong khi outbound dependency hỏng; cần đo cả hai.
12. Không; credentials có audience/scope/domain riêng, phải có thiết kế service identity/delegation.

## 22. Checklist triển khai

- [ ] Xác định rõ public inbound API và từng outbound dependency contract.
- [ ] Cấu hình base URL theo environment, không phụ thuộc `server.port` hoặc user-provided URL.
- [ ] Đặt method/path/query/body/Content-Type/Accept rõ ràng, validate input.
- [ ] Chọn RestClient sync hay WebClient reactive phù hợp stack; không block WebFlux event loop.
- [ ] Đặt connect/read/response/overall deadlines theo SLO và proxy timeouts.
- [ ] Quản lý outbound connection pool, concurrency, bulkhead, retry budget.
- [ ] Không retry operation ghi nếu thiếu idempotency/duplicate protection.
- [ ] Map 4xx/5xx, timeout, connect failure, malformed JSON thành public errors theo contract.
- [ ] Không copy vô điều kiện user auth token, cookies, Host, hop-by-hop headers, Location.
- [ ] Xác minh TLS/trust mỗi chặng, kiểm soát service identity và network egress.
- [ ] Chặn SSRF và tránh logging secrets/sensitive data.
- [ ] Có metric/trace cho inbound server và outbound HTTP client.
- [ ] Test service success, 404, 429/5xx, slow, down, timeout, invalid schema.
- [ ] Giới hạn body size/streaming và xử lý cleanup khi request bị hủy.

## 23. Tài liệu tham khảo

- Spring Boot 3.3 — Calling REST Services / RestClient và WebClient: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — RestClientAutoConfiguration: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html
- Spring Framework — REST Clients, RestClient và WebClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework — Spring MVC @ResponseBody / @RestController: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework 6.1 — SimpleClientHttpRequestFactory timeout API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html
- Spring Boot 3.3 — Detecting Web Application Type (MVC vs WebFlux): https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- JDK 17 — HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- JDK 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- W3C Trace Context — traceparent: https://www.w3.org/TR/trace-context/
