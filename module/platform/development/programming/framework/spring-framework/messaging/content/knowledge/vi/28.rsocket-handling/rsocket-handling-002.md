
# Đăng ký acceptor và khởi tạo server RSocket

## Mục tiêu

Sau bài này, bạn có thể giải thích vai trò của `SocketAcceptor`, chuyển các handler Spring thành một acceptor bằng `RSocketMessageHandler`, khởi động RSocket server qua TCP và quản lý vòng đời của server.

Ví dụ sử dụng Java 17+, Spring Framework 7.0.10 và RSocket Java 1.1.5. Spring Framework 6.2 có cùng mô hình API chính cho phần này. Hãy đồng bộ phiên bản Spring theo BOM của dự án.

## 1. Từ kết nối đến acceptor

RSocket là giao thức nhị phân cho giao tiếp hai chiều, bất đồng bộ trên một kết nối. Nó có thể chạy trên TCP hoặc WebSocket và hỗ trợ các kiểu tương tác Request-Response, Request-Stream, Channel và Fire-and-Forget. Sau khi kết nối được thiết lập, cả hai phía đều có thể gửi yêu cầu; vì vậy RSocket dùng khái niệm requester và responder thay cho cách hiểu client/server cố định.

Khi một peer kết nối tới server, peer gửi frame `SETUP` chứa thông tin thiết lập như MIME type của data và metadata. Server dùng một `SocketAcceptor` để xử lý bước thiết lập kết nối và tạo responder `RSocket` cho kết nối đó.

Các thành phần có vai trò khác nhau:

- `RSocketServer`: cấu hình và bind server vào một transport.
- `SocketAcceptor`: tiếp nhận từng kết nối mới, đọc thông tin `SETUP` và trả về một `RSocket` responder.
- `RSocket`: xử lý các request trên kết nối, chẳng hạn Request-Response hoặc Request-Stream.
- `RSocketMessageHandler`: cầu nối của Spring Messaging; phát hiện các bean `@Controller`, ánh xạ `@MessageMapping` và `@ConnectMapping`, rồi cung cấp một `SocketAcceptor` thông qua `responder()`.
- `RSocketRequester`: API phía gửi request. Nó không phải acceptor và không có nhiệm vụ bind server.

Với ứng dụng Spring, ta thường không cần tự viết một lớp `RSocket` ở mức protocol. Ta khai báo các handler Spring, lấy acceptor từ `RSocketMessageHandler`, sau đó truyền acceptor đó cho `RSocketServer`.

Luồng khởi tạo có dạng:

```text
@Controller + @MessageMapping
          |
          v
RSocketMessageHandler
          |
          | responder()
          v
SocketAcceptor
          |
          | RSocketServer.create(acceptor)
          v
RSocketServer
          |
          | bind(TcpServerTransport)
          v
CloseableChannel đang lắng nghe
```

## 2. Khai báo dependency

Ví dụ Maven dưới đây dùng Spring Framework BOM để giữ các module Spring cùng phiên bản. Hai artifact RSocket cần thiết cho server TCP là `rsocket-core` và `rsocket-transport-netty`.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>7.0.10</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-messaging</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-core</artifactId>
        <version>1.1.5</version>
    </dependency>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-transport-netty</artifactId>
        <version>1.1.5</version>
    </dependency>
</dependencies>
```

Ý nghĩa của các dependency:

- `spring-context` cung cấp ApplicationContext và cấu hình bằng `@Configuration`, `@Bean`.
- `spring-messaging` cung cấp `RSocketMessageHandler`, `RSocketStrategies`, `@MessageMapping` và các API messaging liên quan.
- `spring-web` cung cấp `PathPatternRouteMatcher` cùng các codec bổ sung khi cần encode/decode kiểu dữ liệu phức tạp.
- `rsocket-core` cung cấp `RSocketServer`, `SocketAcceptor` và các abstraction của giao thức.
- `rsocket-transport-netty` cung cấp transport TCP/WebSocket dựa trên Reactor Netty.

Ví dụ bên dưới chỉ truyền `String`, nên có thể dùng các codec cơ bản mà `RSocketStrategies` cung cấp sẵn. Nếu truyền object như DTO, hãy thêm codec JSON hoặc CBOR tương ứng và cấu hình encoder/decoder tương thích ở cả hai phía.

## 3. Tạo responder bằng Spring Messaging

Một handler phía server là bean được đánh dấu `@Controller`. Mỗi phương thức `@MessageMapping` xử lý một route RSocket. Ví dụ sau nhận một tên và trả về lời chào:

```java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @MessageMapping("greeting")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Xin chào, " + name);
    }
}
```

Route `greeting` là metadata định tuyến của RSocket request, không phải URL HTTP. Phương thức nhận một payload và trả về một `Mono`, vì vậy Spring xử lý lời gọi này như một tương tác Request-Response.

Spring tìm các bean `@Controller` và đăng ký những phương thức có `@MessageMapping` hoặc `@ConnectMapping` khi khởi tạo `RSocketMessageHandler`. Handler này sẽ chuyển request thành lời gọi phương thức phù hợp, đồng thời dùng các codec trong `RSocketStrategies` để chuyển đổi payload.

## 4. Đăng ký acceptor và khởi tạo server TCP

Ví dụ đầy đủ dưới đây đăng ký controller, tạo `RSocketMessageHandler`, lấy `SocketAcceptor` bằng `handler.responder()`, rồi bind server vào `localhost:7000`.

```java
package example.rsocket;

import java.time.Duration;

import io.rsocket.CloseableChannel;
import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketServerApplication {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    RSocketMessageHandler rsocketMessageHandler(RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        handler.setDefaultDataMimeType(MimeTypeUtils.TEXT_PLAIN);
        return handler;
    }

    @Bean
    GreetingController greetingController() {
        return new GreetingController();
    }

    @Bean(destroyMethod = "dispose")
    CloseableChannel rsocketServer(RSocketMessageHandler handler) {
        SocketAcceptor acceptor = handler.responder();

        CloseableChannel server = RSocketServer.create(acceptor)
                .bind(TcpServerTransport.create("localhost", 7000))
                .block(Duration.ofSeconds(10));

        if (server == null) {
            throw new IllegalStateException("RSocket server did not bind");
        }
        return server;
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(RSocketServerApplication.class);

        context.registerShutdownHook();

        CloseableChannel server = context.getBean(CloseableChannel.class);
        System.out.println("RSocket server listening at tcp://localhost:7000");

        server.onClose().block();
    }
}
```

Trong ví dụ này, `GreetingController` là bean Spring được đăng ký bằng phương thức `@Bean`. Nếu controller nằm trong package được component scan, có thể dùng `@ComponentScan` thay cho phương thức đăng ký bean tường minh.

### Giải thích từng bước

**Bước 1 — Tạo `RSocketStrategies`.**

`RSocketStrategies` gom cấu hình encoder, decoder, metadata extractor, reactive adapter và route matcher. `PathPatternRouteMatcher` là lựa chọn được Spring khuyến nghị khi có `spring-web`; nó hỗ trợ route phân cấp và dùng dấu chấm làm dấu phân cách mặc định, ví dụ `inventory.item.find`.

**Bước 2 — Tạo `RSocketMessageHandler`.**

Gọi `setRSocketStrategies(strategies)` để handler sử dụng cùng bộ codec và route matcher. `setDefaultDataMimeType(MimeTypeUtils.TEXT_PLAIN)` đặt MIME type mặc định cho data khi frame `SETUP` không chỉ định MIME type. Với payload kiểu `String`, `text/plain` là lựa chọn phù hợp.

**Bước 3 — Chuyển handler thành acceptor.**

Lệnh `handler.responder()` trả về một `SocketAcceptor` có khả năng tạo responder cho mỗi kết nối mới. Acceptor này dùng hạ tầng annotation của Spring để điều phối các route đến phương thức handler.

**Bước 4 — Tạo và bind server.**

`RSocketServer.create(acceptor)` tạo cấu hình server với acceptor đã đăng ký. `bind(TcpServerTransport.create("localhost", 7000))` chọn transport TCP và địa chỉ lắng nghe. `bind` trả về một `Mono<CloseableChannel>`; gọi `block` trong giai đoạn khởi động để thực sự thực hiện bind và nhận channel đang chạy.

**Bước 5 — Quản lý vòng đời.**

`CloseableChannel` đại diện cho server đã bind. Bean khai báo `destroyMethod = "dispose"` để Spring đóng channel khi ApplicationContext dừng. `registerShutdownHook()` đăng ký việc đóng context khi JVM tắt, còn `server.onClose().block()` giữ tiến trình chờ cho đến khi server đóng.

Không gọi `block()` bên trong một reactive handler hoặc event loop. Trong ví dụ này, `block` chỉ được dùng ở luồng khởi động và luồng chính của ứng dụng độc lập.

## 5. Gửi request để kiểm tra server

Có thể dùng `RSocketRequester` để gửi request đến route `greeting`. Requester tạo kết nối khi request đầu tiên được thực hiện; việc gọi `tcp` chỉ chuẩn bị requester.

```java
package example.rsocket;

import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

public class RSocketClientDemo {

    public static void main(String[] args) {
        RSocketRequester requester = RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
                .tcp("localhost", 7000);

        try {
            String response = requester.route("greeting")
                    .data("Mai")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            System.out.println(response);
        }
        finally {
            requester.dispose();
        }
    }
}
```

Kết quả:

```text
Xin chào, Mai
```

Client và server phải thống nhất cách encode/decode data và metadata. Ví dụ này dùng `text/plain` và `String` ở cả hai phía. Nếu một phía gửi JSON trong khi phía kia chỉ cấu hình codec cho text, request có thể thất bại khi giải mã dù kết nối TCP đã thành công.

## 6. Tùy biến acceptor ở mức RSocket

Khi không dùng `@MessageMapping`, ứng dụng có thể tự cung cấp một `SocketAcceptor`. Về bản chất, acceptor nhận thông tin thiết lập kết nối và `RSocket` dùng để gửi request về peer, sau đó trả về `Mono<RSocket>` chứa responder của kết nối đó.

```java
SocketAcceptor acceptor = (setupPayload, sendingRSocket) ->
        Mono.just(customResponder);

CloseableChannel server = RSocketServer.create(acceptor)
        .bind(TcpServerTransport.create("localhost", 7001))
        .block(Duration.ofSeconds(10));
```

Trong đoạn minh họa, `customResponder` là một instance do ứng dụng tạo và triển khai `io.rsocket.RSocket`. Lớp đó phải cài đặt những interaction mà server muốn hỗ trợ, chẳng hạn `requestResponse`, `requestStream`, `requestChannel` hoặc `fireAndForget`. Những interaction không được triển khai sẽ dùng hành vi mặc định của RSocket, thường là trả lỗi không hỗ trợ.

Cách tự triển khai phù hợp khi cần kiểm soát protocol ở mức thấp hoặc tích hợp một responder không dựa trên annotation. Với ứng dụng Spring Messaging thông thường, `RSocketMessageHandler.responder()` giúp tránh phải tự quản lý việc ánh xạ route và gọi handler.

## 7. Dùng Spring Boot thay cho bind thủ công

Nếu ứng dụng đã dùng Spring Boot, starter `spring-boot-starter-rsocket` tự cấu hình hạ tầng Spring Messaging, tạo `RSocketMessageHandler` và khởi động RSocket server theo cấu hình. Ví dụ server TCP độc lập:

```properties
spring.rsocket.server.port=9898
```

Với ứng dụng WebFlux muốn gắn RSocket qua WebSocket, có thể cấu hình:

```properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
```

Trong trường hợp dùng auto-configuration của Spring Boot, chỉ cần khai báo các handler `@Controller` và cấu hình transport. Không tạo thêm một bean bind thủ công vào cùng cổng, vì như vậy có thể dẫn đến lỗi cổng đã được sử dụng.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Server không khởi động, báo địa chỉ/cổng đang được sử dụng | Một tiến trình khác đã bind cùng địa chỉ và cổng | Đổi cổng hoặc dừng tiến trình đang chiếm cổng |
| Client kết nối được nhưng không tìm thấy route | Route trong `requester.route(...)` không khớp với `@MessageMapping` | So sánh chính xác tên route, dấu chấm phân cấp và pattern |
| Không giải mã được payload | MIME type hoặc encoder/decoder giữa hai phía không tương thích | Kiểm tra MIME type trong `SETUP` và cấu hình `RSocketStrategies` |
| Handler không được gọi | Controller chưa được đăng ký vào ApplicationContext hoặc thiếu annotation | Xác nhận bean có `@Controller` và phương thức có `@MessageMapping` |
| Server chạy nhưng không dừng sạch | Không dispose `CloseableChannel` khi context đóng | Quản lý channel như bean và khai báo `destroyMethod = "dispose"` |
| Server bind không xảy ra | Chỉ tạo Mono từ `bind` nhưng không subscribe | Chờ kết quả bằng `block` lúc startup hoặc subscribe trong lifecycle phù hợp |

Một số lưu ý thiết kế:

- `SocketAcceptor` xử lý lúc mở kết nối; `@MessageMapping` xử lý request theo route sau khi kết nối được thiết lập.
- `@ConnectMapping` xử lý frame `SETUP` và `METADATA_PUSH`. Phương thức này chỉ được trả `void` hoặc `Mono<Void>`; nếu xử lý setup phát sinh lỗi, kết nối mới có thể bị từ chối.
- Không giữ việc xử lý `@ConnectMapping` chờ một request khác qua `RSocketRequester`. Frame setup cần được xử lý xong trước khi các request thông thường bắt đầu.
- Route RSocket là route messaging, không phải URL. Route matcher mặc định dùng `AntPathMatcher`; `PathPatternRouteMatcher` là lựa chọn hiệu quả hơn khi có `spring-web`.
- Với TCP, địa chỉ `localhost` chỉ cho phép truy cập cục bộ. Khi triển khai trong container hoặc trên máy chủ, chọn interface bind phù hợp với mạng và cấu hình bảo vệ kết nối theo yêu cầu của hệ thống.

## 9. Ghi nhớ

Để khởi tạo một RSocket server bằng Spring Framework, hãy thực hiện theo chuỗi sau:

1. Khai báo các responder bằng `@Controller`, `@MessageMapping` và khi cần `@ConnectMapping`.
2. Tạo `RSocketMessageHandler` và cấu hình `RSocketStrategies`.
3. Lấy acceptor bằng `RSocketMessageHandler.responder()`.
4. Truyền acceptor vào `RSocketServer.create(acceptor)`.
5. Gọi `bind(transport)` để mở server và quản lý `CloseableChannel` để đóng server đúng vòng đời.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Java — GitHub repository](https://github.com/rsocket/rsocket-java)
- [RSocket Core — Maven Central](https://central.sonatype.com/artifact/io.rsocket/rsocket-core)
