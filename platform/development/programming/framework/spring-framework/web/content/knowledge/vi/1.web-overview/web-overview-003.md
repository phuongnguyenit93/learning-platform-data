# Các mô-đun `spring-web`, `spring-webmvc`, `spring-webflux` và `spring-websocket`

## 1. Bức tranh tổng thể

Trong Spring Framework, “web” không phải chỉ một cách xây dựng ứng dụng. Có một lớp hỗ trợ giao tiếp HTTP dùng chung, hai mô hình xử lý HTTP ở server và các API phục vụ giao tiếp hai chiều qua WebSocket.

| Artifact | Trách nhiệm chính | API/thành phần tiêu biểu | Phù hợp khi |
| --- | --- | --- | --- |
| `org.springframework:spring-web` | Hạ tầng HTTP và các chức năng web dùng chung | `HttpHeaders`, `HttpEntity`, `ResponseEntity`, `MediaType`, `RestClient`, HTTP message converters | Dùng HTTP abstractions, gọi REST đồng bộ, làm nền cho các web framework |
| `org.springframework:spring-webmvc` | Web/REST framework trên **Servlet stack** | `DispatcherServlet`, `@Controller`, `@RestController`, `HandlerMapping`, `ViewResolver` | REST CRUD, ứng dụng web dùng Servlet và nhiều thư viện blocking |
| `org.springframework:spring-webflux` | Web/REST framework **reactive**, thêm HTTP client reactive | `DispatcherHandler`, `Mono`, `Flux`, `RouterFunction`, `WebClient` | I/O non-blocking, streaming, luồng dữ liệu reactive |
| `org.springframework:spring-websocket` | WebSocket và STOMP messaging trên **Servlet stack** | `WebSocketHandler`, `TextWebSocketHandler`, `@EnableWebSocket`, `@EnableWebSocketMessageBroker` | Chat, thông báo thời gian thực, giao tiếp hai chiều trên ứng dụng Servlet |

**Không phải bốn lựa chọn ngang hàng:** `spring-web` là phần nền; `spring-webmvc` và `spring-webflux` là hai web framework HTTP khác nhau; `spring-websocket` bổ sung WebSocket cho Servlet stack. WebFlux còn có **API WebSocket reactive riêng**. Một ứng dụng có thể có nhiều artifact, nhưng sự tồn tại của một dependency không tự xác định loại server đang chạy.

```text
                      Spring Framework
                            |
                      spring-web
                HTTP foundation, codecs,
                 HTTP client đồng bộ
                            |
                 +----------+-----------+
                 |                      |
            spring-webmvc          spring-webflux
          Servlet / HTTP MVC      Reactive / HTTP
          DispatcherServlet       DispatcherHandler
                 |                      |
           spring-websocket      Reactive WebSocket API
          WebSocket + STOMP      trong spring-webflux
```

Sơ đồ mô tả **vai trò** của các module, không phải biểu đồ dependency transitive đầy đủ. Trong thực tế, các module cấp cao có thể kéo theo những thư viện nền qua cơ chế quản lý dependencies.

## 2. `spring-web`: nền tảng HTTP dùng chung

Module này cung cấp các đối tượng và cơ chế làm việc với HTTP, ví dụ:

- `HttpHeaders`: chứa header như `Content-Type`, `Accept`, `Authorization`.
- `HttpMethod`, `HttpStatusCode`, `MediaType`: phương thức, trạng thái HTTP và media type.
- `HttpEntity<T>`: body + headers; `ResponseEntity<T>` thêm trạng thái HTTP, thường dùng làm kết quả trả về controller.
- `HttpMessageConverter`: đọc/ghi body HTTP với các định dạng được hỗ trợ, chẳng hạn JSON khi đã có thư viện và cấu hình phù hợp.
- `RestClient`: HTTP client fluent **đồng bộ**; `RestTemplate` là HTTP client đồng bộ lâu đời còn gặp ở mã nguồn cũ.
- Các HTTP abstraction, codec và lớp tích hợp nền tảng được nhiều phần khác của Spring web sử dụng.

Ví dụ gọi một API bên ngoài bằng `RestClient`:

```java
import org.springframework.web.client.RestClient;

public class BookClient {
    private final RestClient client =
            RestClient.create("https://api.example.com");

    public String findBook(String id) {
        return client.get()
                .uri("/books/{id}", id)
                .retrieve()
                .body(String.class);
    }
}
```

Đây là **class minh họa**, không phải chương trình độc lập và `api.example.com` chỉ là địa chỉ giả định. `body(String.class)` trong cách dùng đồng bộ sẽ lấy kết quả trước khi phương thức trả về; cần cấu hình timeout, xử lý HTTP error và giới hạn tải theo yêu cầu ứng dụng.

**Cần phân biệt:** `RestClient` là **HTTP client**. Chỉ có `spring-web` không đồng nghĩa ứng dụng đã thiết lập `DispatcherServlet`, `DispatcherHandler`, HTTP server hoặc REST controller.

## 3. `spring-webmvc`: Spring MVC trên Servlet stack

### 3.1. Front controller và đường đi request

Spring MVC dựa trên Jakarta Servlet API, thường chạy trong Servlet container (Tomcat, Jetty…). Trung tâm điều phối request là `DispatcherServlet` theo mô hình *front controller*. Framework định tuyến một HTTP request tới controller phù hợp, chuyển tham số thành giá trị Java, thực thi logic và tạo response.

```text
HTTP client
    |
Servlet container và Filter chain
    |
DispatcherServlet
    |
HandlerMapping -> HandlerAdapter -> Controller method
    |
Business service / repository
    |
HTTP message conversion hoặc view rendering
    |
HTTP response
```

Các annotation thường gặp gồm `@RestController`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam`, `@RequestBody`, `@ExceptionHandler`. Với REST API, `@RestController` thường trả dữ liệu trong response body; với ứng dụng render trang, `@Controller` có thể trả view name để `ViewResolver` xử lý.

Ví dụ REST controller:

```java
package example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/hello/{name}")
    public Greeting hello(@PathVariable String name) {
        return new Greeting("Xin chào, " + name);
    }

    public record Greeting(String message) {}
}
```

Khi ứng dụng MVC có server và JSON converter được cấu hình, gọi `GET /hello/Lan` sẽ nhận body:

```json
{"message":"Xin chào, Lan"}
```

Đây là **một class được Spring quản lý**, chưa phải ứng dụng chạy độc lập qua `javac`/`java`; cần application context, component scanning hoặc khai báo bean, cấu hình servlet và HTTP runtime. Trong Spring Boot, starter và auto-configuration thường lo phần lớn cấu hình này.

### 3.2. Blocking và asynchronous trong MVC

Ở mô hình Servlet phổ biến, thread do container cấp thực thi controller. Nếu code gọi JDBC blocking hoặc HTTP client blocking, thread thường chờ thao tác I/O hoàn thành. Điều này **không mặc nhiên là lỗi**: với JPA/JDBC và các thư viện đồng bộ, MVC là lựa chọn dễ hiểu và phổ biến.

Không nên kết luận MVC “chỉ có synchronous”: Servlet async và các kiểu như `Callable`, `DeferredResult` hoặc cơ chế streaming có thể cho phép xử lý bất đồng bộ trong một số giai đoạn. Tuy nhiên, application vẫn dùng **Servlet stack và DispatcherServlet**; các API này không tự biến server thành WebFlux.

## 4. `spring-webflux`: Spring WebFlux trên reactive stack

### 4.1. Mô hình reactive và non-blocking

WebFlux được Spring bổ sung từ phiên bản 5.0. Đây là web framework có hạ tầng **non-blocking**, Reactive Streams và hỗ trợ backpressure. Nó dùng `DispatcherHandler` cho cơ chế điều phối tương ứng, **không dùng `DispatcherServlet` làm dispatcher HTTP của WebFlux**.

WebFlux chạy được với Reactor Netty hoặc môi trường Servlet container có tích hợp non-blocking thích hợp. Vì vậy, **WebFlux không có nghĩa bắt buộc là Netty**.

WebFlux hỗ trợ hai phong cách xây endpoint:

1. **Annotated controller:** `@RestController`, `@GetMapping`… giống tên annotation ở MVC.
2. **Functional endpoint:** khai báo route qua `RouterFunction`, `HandlerFunction`.

WebFlux dùng Project Reactor trong nhiều API:

- `Mono<T>` đại diện một publisher có thể phát **0 hoặc 1** phần tử rồi hoàn tất/báo lỗi.
- `Flux<T>` đại diện một publisher có thể phát **0 đến nhiều** phần tử rồi hoàn tất/báo lỗi.
- `map`, `flatMap`, `filter`, `onErrorResume`… cho phép mô tả các bước biến đổi và xử lý.
- Backpressure trong Reactive Streams diễn tả khả năng bên tiêu thụ yêu cầu lượng dữ liệu cần nhận; không có nghĩa mọi tài nguyên phía sau đều tự giới hạn tải hoàn hảo.

Một endpoint WebFlux:

```java
package example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/hello/{name}")
    public Mono<Greeting> hello(@PathVariable String name) {
        return Mono.just(new Greeting("Xin chào, " + name));
    }

    public record Greeting(String message) {}
}
```

Request `GET /hello/Lan` trong một ứng dụng WebFlux được cấu hình đúng vẫn trả một JSON object tương đương ví dụ MVC. **Sự khác nhau quan trọng là HTTP runtime và cách xử lý kết quả**, không nằm ở tên annotation.

`Mono.just(...)` trong ví dụ tạo publisher từ giá trị có sẵn; nó **không minh họa một I/O non-blocking thực thụ**. Lợi ích WebFlux rõ hơn khi request kết hợp WebClient, database driver reactive hoặc luồng dữ liệu bất đồng bộ thật sự.

### 4.2. `WebClient`: client reactive thuộc WebFlux

`WebClient` là HTTP client dùng API reactive. Ví dụ:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class BookClient {
    private final WebClient client =
            WebClient.create("https://api.example.com");

    public Mono<String> findBook(String id) {
        return client.get()
                .uri("/books/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

`findBook` trả về `Mono<String>` để người gọi tiếp tục ghép các thao tác bất đồng bộ. HTTP request cần một HTTP connector thích hợp, endpoint thật và một subscriber; trong WebFlux, framework subscribe khi controller trả publisher phù hợp. Đây cũng là ví dụ **class minh họa**, chưa có chương trình chạy độc lập.

**Một ứng dụng MVC có thể dùng `WebClient`** để gọi dịch vụ khác mà server vẫn chạy MVC. Việc thêm `spring-webflux` nhằm lấy `WebClient` không tự chuyển dispatcher server thành `DispatcherHandler`.

### 4.3. Lợi ích và giới hạn thực tế

WebFlux có giá trị khi hệ thống xử lý nhiều I/O bằng thư viện **non-blocking thật**, cần streaming hoặc tổ hợp chuỗi sự kiện theo kiểu reactive. Nếu controller WebFlux gọi `Thread.sleep(...)`, JDBC blocking hay HTTP client đồng bộ ngay trên event-loop, thread có thể bị giữ và làm giảm khả năng đáp ứng của các request khác.

Khi bất khả kháng phải dùng code blocking, Reactor có scheduler như `Schedulers.boundedElastic()` để cô lập công việc blocking khỏi các thread nhạy cảm. Đó là biện pháp tương thích, **không chuyển driver blocking thành driver reactive**. Với hệ thống chủ yếu JPA/JDBC đồng bộ, MVC thường dễ thiết kế và vận hành hơn; WebFlux không mặc định nhanh hơn trên mọi workload.

## 5. `spring-websocket`: kết nối hai chiều trên Servlet stack

### 5.1. Phân biệt HTTP, WebSocket và STOMP

HTTP thông thường có mô hình request/response. WebSocket bắt đầu bằng một HTTP handshake nâng cấp giao thức khi thành công rồi duy trì một kết nối hai chiều. Cả client và server có thể chủ động gửi text hoặc binary message.

- **HTTP/REST:** phù hợp truy vấn, cập nhật tài nguyên, CRUD.
- **SSE (Server-Sent Events):** phù hợp việc server liên tục đẩy dữ liệu **một chiều** tới browser.
- **WebSocket:** phù hợp tương tác hai chiều thường xuyên trên kết nối lâu dài.
- **STOMP:** giao thức nhắn tin ở lớp ứng dụng có destination và lệnh như `SEND`/`SUBSCRIBE`; có thể chạy **trên WebSocket**, nhưng WebSocket **không bắt buộc** dùng STOMP.

`spring-websocket` cung cấp API WebSocket cho Servlet stack, ví dụ `WebSocketHandler` và `TextWebSocketHandler`. Với Spring messaging, Spring còn hỗ trợ STOMP broker relay, simple broker và xử lý message theo annotation.

### 5.2. Ví dụ WebSocket handler mức thấp

Ví dụ dưới đây là **một class cấu hình** dành cho ứng dụng Servlet/Spring MVC đã có server và các dependency cần thiết:

```java
package example.socket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws/echo");
    }

    static class EchoHandler extends TextWebSocketHandler {
        @Override
        protected void handleTextMessage(WebSocketSession session,
                                         TextMessage message) throws Exception {
            session.sendMessage(
                    new TextMessage("echo:" + message.getPayload())
            );
        }
    }
}
```

Client JavaScript trong browser có thể gửi thử:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");
socket.addEventListener("open", () => socket.send("hello"));
socket.addEventListener("message", event => console.log(event.data));
```

Nếu ứng dụng chạy ở cổng 8080 và WebSocket handshake thành công, kết quả nhận được là `echo:hello`. Ví dụ chỉ để hiểu cơ chế; triển khai thực tế phải xử lý đóng kết nối, lỗi mạng, giới hạn message, Origin, xác thực, phân quyền và vận hành session. `ws://` phù hợp cho local không mã hóa; kết nối được bảo vệ dùng `wss://`.

### 5.3. STOMP và pub/sub

Spring hỗ trợ STOMP over WebSocket qua `spring-websocket` cùng `spring-messaging`. Ví dụ cấu hình *broker đơn giản*:

```java
package example.socket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
```

Trong mô hình này, `/ws` là điểm kết nối STOMP qua WebSocket; message gửi tới destination có prefix `/app` được điều phối tới handler `@MessageMapping` được định nghĩa phù hợp; simple broker phục vụ subscription trên `/topic`. Class trên **chưa có message controller** và không tự sinh thông điệp broadcast. Simple broker thích hợp các tình huống cơ bản, không nên xem là thay thế mọi tính năng reliability/persistence/scale của message broker chuyên dụng. Khi cần, có thể cấu hình broker relay. **SockJS là tùy chọn**, không phải điều kiện bắt buộc của WebSocket hoặc STOMP.

### 5.4. WebSocket ở WebFlux là API khác

WebFlux có WebSocket reactive thông qua `org.springframework.web.reactive.socket.WebSocketHandler` và `org.springframework.web.reactive.socket.WebSocketSession`. Đây là **những kiểu khác package** với `org.springframework.web.socket.WebSocketHandler` và `WebSocketSession` của Servlet stack. Ví dụ `TextWebSocketHandler` phía trên vì vậy **không chuyển nguyên xi sang WebFlux**. Với ứng dụng thuần WebFlux, hãy dùng WebSocket handler reactive thuộc WebFlux.

## 6. Chọn module theo yêu cầu

| Yêu cầu | Chọn gì? | Giải thích |
| --- | --- | --- |
| REST API CRUD, JDBC/JPA, code phần lớn đồng bộ | `spring-webmvc` | Servlet MVC khớp với nhiều thư viện blocking |
| Streaming/reactive server, nhiều I/O non-blocking | `spring-webflux` | Runtime và pipeline hỗ trợ Reactive Streams |
| Gọi HTTP synchronous | `spring-web` và `RestClient` | Client đồng bộ, không cần web server |
| Gọi HTTP reactive từ MVC hoặc WebFlux | `spring-webflux` và `WebClient` | Client reactive độc lập với loại server |
| Chat hai chiều trong ứng dụng MVC | `spring-websocket` | Handler WebSocket hoặc STOMP trên Servlet |
| WebSocket trong ứng dụng WebFlux | WebSocket API của `spring-webflux` | Handler/session reactive cùng stack |

Các module không giải quyết toàn bộ hệ thống chỉ bằng một dependency. Security, request validation, persistence, logging, backpressure ở những ranh giới khác, điều phối phiên kết nối và deployment cần được thiết kế riêng.

## 7. Khai báo dependency đúng cách

Nếu dùng Spring Framework thuần và đã quản lý phiên bản các artifact một cách nhất quán (ví dụ BOM), các tọa độ thư viện là:

```groovy
dependencies {
    implementation 'org.springframework:spring-web'        // nền HTTP
    implementation 'org.springframework:spring-webmvc'     // Servlet MVC
    implementation 'org.springframework:spring-webflux'    // WebFlux/WebClient
    implementation 'org.springframework:spring-websocket'  // Servlet WebSocket
}
```

Đây là **danh mục nhận diện**, không phải cấu hình yêu cầu cài đủ cả bốn. Chỉ chọn các module cần thiết; các module cấp cao có thể kéo `spring-web` theo dependency transitive. Với Framework thuần, application phải tự chuẩn bị server/runtime, context, các codec thích hợp và các cấu hình phụ trợ. STOMP messaging có thêm `spring-messaging`.

Khi dùng **Spring Boot 3.x**, starter giúp quản lý nhiều dependency và auto-configuration. Ba phương án **riêng biệt**:

```groovy
// 1. REST server trên Spring MVC:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

```groovy
// 2. REST server trên Spring WebFlux:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

```groovy
// 3. MVC + WebSocket/STOMP:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

Tên starter có thể thay đổi qua các thế hệ Spring Boot; kiểm tra tài liệu theo **phiên bản thực tế** của dự án. Trong Boot 3.x, nếu cùng có cả starter MVC và WebFlux, Boot thường tự chọn **MVC làm web application type**. Một lý do thường gặp để giữ cả hai là server MVC dùng `WebClient`. Đừng kết luận server sử dụng `DispatcherHandler` chỉ vì classpath có `spring-webflux`.

Với ứng dụng Spring Boot 3.x tối giản, có thể dùng điểm khởi chạy sau cùng controller MVC hoặc WebFlux đã nêu; đây là một file khác, ở package cha của `example.mvc` hoặc `example.reactive` sao cho component scan tìm thấy controller:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Để **chạy một trong các ví dụ HTTP**: tạo dự án Spring Boot 3.x với Java 17+, Gradle plugin/BOM phù hợp phiên bản Boot, chọn **một starter web** trong hai phương án đầu, đặt `Application.java` và `GreetingController.java` trong các package tương ứng rồi dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Khi server thông thường ở `localhost:8080`, chạy:

```bash
curl http://localhost:8080/hello/Lan
```

Body dự kiến (nếu không bị đổi bởi cấu hình khác): `{"message":"Xin chào, Lan"}`. Phần WebSocket chỉ chạy khi chọn ứng dụng MVC với dependency WebSocket và cấu hình handler ở mục 5; `curl` thông thường không phải WebSocket client.

## 8. Những ngộ nhận thường gặp

1. **“Có `@RestController` thì là Spring MVC.”** Sai: MVC và WebFlux đều hỗ trợ annotated controllers. Phải nhìn web stack/runtime.
2. **“Chỉ cần `spring-web` là đủ tạo server REST.”** Sai: module nền không đồng nghĩa web server và dispatcher đã được cấu hình.
3. **“WebFlux luôn nhanh hơn MVC.”** Sai: lợi ích phụ thuộc tính chất workload và số lượng thành phần I/O non-blocking thật sự.
4. **“WebFlux bắt buộc là Netty.”** Sai: WebFlux có cơ chế tích hợp với Servlet container hỗ trợ non-blocking.
5. **“Trả `Mono` khiến mọi tác vụ thành non-blocking.”** Sai: JDBC blocking hoặc `Thread.sleep` vẫn blocking nếu được gọi ở bên trong pipeline.
6. **“MVC không được dùng `WebClient`.”** Sai: MVC có thể gọi WebClient từ HTTP client layer.
7. **“Có `spring-websocket` tức thay thế `spring-webmvc`.”** Sai: WebSocket thêm giao thức kết nối hai chiều, không thay REST dispatching.
8. **“WebSocket bằng STOMP.”** Sai: WebSocket là transport hai chiều; STOMP cung cấp ngữ nghĩa messaging tùy chọn.
9. **“Cấu hình CORS HTTP tự bảo vệ hết WebSocket.”** Sai: cần xét Origin/handshake và authentication/authorization của giao thức/stack sử dụng.
10. **“Có cả MVC và WebFlux dependency thì hai server stack tự chạy song song.”** Sai: cần kiểm tra web application type, server và dispatcher thực tế.

## 9. Bài tập vận dụng

**Tình huống A:** Một hệ thống bán hàng dùng JPA đồng bộ, CRUD JSON, thỉnh thoảng gọi API vận chuyển. Điểm khởi đầu hợp lý: **Spring MVC + RestClient**. Có thể dùng **WebClient trong MVC** nếu nhu cầu tích hợp async cụ thể chứng minh được lợi ích.

**Tình huống B:** Bảng trạng thái công việc chỉ nhận cập nhật từ server. So sánh **SSE** và **WebSocket**. Nếu browser cần gửi hành động tương tác liên tục, WebSocket phù hợp hơn; nếu chỉ nhận luồng sự kiện một chiều, SSE có thể đơn giản hơn.

**Tình huống C:** Một controller WebFlux trả `Mono<Order>` nhưng gọi JDBC blocking trong `map(...)`. Giải thích vì sao Mono không tự loại bỏ blocking, thread nào có nguy cơ bị chiếm, và giải pháp dùng reactive driver hoặc tách blocking khỏi event-loop.

**Tự kiểm tra:**

- `DispatcherServlet` khác `DispatcherHandler` thế nào? — Trước là trung tâm MVC/Servlet; sau là trung tâm WebFlux/reactive.
- `RestClient` khác `WebClient` thế nào? — REST client đồng bộ so với HTTP client reactive/non-blocking.
- WebFlux muốn làm WebSocket có luôn cần `spring-websocket` không? — Không; WebFlux có WebSocket reactive API riêng.

## 10. Đọc thêm từ tài liệu chính thức

- Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Core và thành phần nền `spring-web`: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Servlet WebSocket API: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- STOMP: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html

**Điểm chốt:** `spring-web` là nền HTTP; `spring-webmvc` triển khai web server Servlet/MVC; `spring-webflux` là web framework reactive và cung cấp WebClient; `spring-websocket` phục vụ WebSocket/STOMP trên Servlet, còn WebFlux có WebSocket API reactive của chính nó.
