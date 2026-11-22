# HttpHandler và lớp chuyển đổi theo máy chủ trong Spring WebFlux

## 1. Vấn đề: một ứng dụng WebFlux chạy trên nhiều HTTP server

Spring WebFlux cung cấp một mô hình xử lý HTTP reactive, nhưng ứng dụng không nhất thiết phải gắn chặt với một API máy chủ cụ thể. Có thể triển khai trên **Reactor Netty**, **Tomcat**, **Jetty**, **Undertow** hoặc một Servlet container phù hợp. Mỗi máy chủ có cách nhận request, đọc body, ghi response, quản lý kết nối và báo hiệu client ngắt kết nối khác nhau.

Nếu controller phải biết trực tiếp API của Netty hay Servlet, code nghiệp vụ sẽ phụ thuộc runtime và rất khó thay máy chủ. Spring đặt một hợp đồng trung gian tên **HttpHandler** ở tầng thấp nhất của server-side reactive stack. Các **server adapter** chuyển đổi API riêng của máy chủ thành hợp đồng chung đó.

Bài học này tập trung vào:

- Hợp đồng **HttpHandler** và kiểu request/response reactive.
- Phân biệt **HttpHandler**, **WebHandler**, **HttpWebHandlerAdapter** và **DispatcherHandler**.
- Vai trò của **WebHttpHandlerBuilder** khi lắp ghép filter, exception handler và web handler.
- Các adapter **ReactorHttpHandlerAdapter**, **ServletHttpHandlerAdapter**, **TomcatHttpHandlerAdapter**, **JettyHttpHandlerAdapter**, **JettyCoreHttpHandlerAdapter** và **UndertowHttpHandlerAdapter**.
- Luồng request/response, backpressure, cancellation và DataBuffer.
- Cách Spring Boot tự cấu hình adapter và trường hợp cần tích hợp máy chủ thủ công.
- Một chương trình Java 17+ chạy được, tự tạo HttpHandler rồi gắn vào Reactor Netty.

## 2. Vị trí của HttpHandler trong kiến trúc WebFlux

Có thể nhìn kiến trúc theo các tầng:

~~~text
Ứng dụng:
  Annotated Controller / Functional Endpoint
                  |
                  v
  DispatcherHandler / WebHandler
                  |
          WebFilter chain
          WebExceptionHandler
                  |
                  v
  HttpWebHandlerAdapter
                  |
                  v
             HttpHandler
                  |
       Server-specific adapter
       /       |        |       \
 Reactor    Servlet   Tomcat   Jetty / Undertow
 Netty       API       API       native API
       \       |        |       /
                  |
                  v
             HTTP Server
                  |
                  v
               Client
~~~

Thứ tự trên là sơ đồ các lớp; khi xử lý request thực tế, server-specific adapter gọi vào HttpHandler, rồi chuỗi web handler xử lý request. Response và tín hiệu hoàn tất quay ngược ra server.

| Tầng | API tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| Mô hình ứng dụng | Annotated Controller, Functional Endpoint | Mô tả route và logic nghiệp vụ |
| Web handler | **DispatcherHandler**, **WebHandler**, **WebFilter**, **WebExceptionHandler** | Xử lý request ở mức web, session, security/filter và routing |
| HTTP abstraction | **HttpHandler**, **ServerHttpRequest**, **ServerHttpResponse** | Hợp đồng xử lý request/response reactive, độc lập API server |
| Adapter | **ReactorHttpHandlerAdapter**, **TomcatHttpHandlerAdapter**... | Chuyển đổi giữa API máy chủ cụ thể và HttpHandler |
| Runtime | Reactor Netty, Tomcat, Jetty, Undertow | Quản lý socket, kết nối, HTTP parsing và I/O |

**HttpHandler không phải controller.** Nó không ánh xạ URL vào method nghiệp vụ và không chứa logic route ở mức ứng dụng. Nó chỉ nhận một request đã được biểu diễn bằng abstraction của Spring, ghi response và trả tín hiệu hoàn tất.

## 3. Hợp đồng HttpHandler

Trong Spring, interface **org.springframework.http.server.reactive.HttpHandler** có một method chính:

~~~java
Mono<Void> handle(
    ServerHttpRequest request,
    ServerHttpResponse response
);
~~~

Ý nghĩa:

- **ServerHttpRequest** biểu diễn request phía server, bao gồm method, URI, headers và body.
- **ServerHttpResponse** biểu diễn response, cho phép đặt status, headers và ghi body.
- Giá trị trả về **Mono<Void>** báo rằng quá trình xử lý response đã hoàn tất hoặc kết thúc bằng lỗi.
- Body request có thể được đọc dưới dạng **Flux<DataBuffer>**.
- Body response được ghi bằng các API nhận Publisher, chẳng hạn **writeWith(Publisher<? extends DataBuffer>)** hoặc **writeAndFlushWith(...)** khi cần flush theo nhóm.

HttpHandler là một abstraction tối thiểu cho HTTP request handling với non-blocking I/O và Reactive Streams backpressure. Nó không bắt buộc ứng dụng biết request đến từ Netty, Servlet hay một server API khác.

### 3.1. Ví dụ handler ở mức thấp

~~~java
HttpHandler handler = (request, response) -> {
    response.setStatusCode(HttpStatus.OK);
    response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

    String body = "Hello " + request.getURI().getPath();
    DataBuffer buffer = response.bufferFactory()
        .wrap(body.getBytes(StandardCharsets.UTF_8));

    return response.writeWith(Mono.just(buffer));
};
~~~

Đây là snippet minh họa, cần import các kiểu Spring và Reactor tương ứng. Handler thực hiện các việc:

1. Chọn HTTP status.
2. Đặt Content-Type.
3. Tạo DataBuffer bằng buffer factory của response.
4. Trả Mono<Void> từ writeWith để framework biết khi nào ghi response xong.

Trong code thật, không cần tự tạo một HttpHandler cho từng controller. Spring WebFlux đã có tầng cao hơn để quản lý route và request lifecycle. HttpHandler thường là điểm kết nối giữa toàn bộ ứng dụng WebFlux với máy chủ.

### 3.2. Vì sao trả Mono<Void>?

Mono<Void> biểu diễn **completion signal**, không phải body response. Dữ liệu response được truyền qua ServerHttpResponse. Khi writeWith hoàn tất, Mono<Void> hoàn tất; nếu quá trình ghi gặp lỗi, Mono phát onError.

Không gọi **block()** bên trong HttpHandler để chờ ghi body. Việc đó có thể chặn event-loop hoặc thread xử lý I/O. Hãy trả Publisher cho adapter và để runtime điều phối subscription.

## 4. Phân biệt HttpHandler với WebHandler

Hai interface có tên gần nhau nhưng nằm ở hai tầng khác nhau:

~~~java
// Tầng HTTP thấp
public interface HttpHandler {
    Mono<Void> handle(
        ServerHttpRequest request,
        ServerHttpResponse response
    );
}

// Tầng Web cao hơn
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
~~~

| Tiêu chí | **HttpHandler** | **WebHandler** |
| --- | --- | --- |
| Package | org.springframework.http.server.reactive | org.springframework.web.server |
| Tham số | ServerHttpRequest, ServerHttpResponse | ServerWebExchange |
| Mục tiêu | Hợp đồng chung cho HTTP server runtime | API tổng quát cho xử lý web |
| Session / Principal / Locale | Không trực tiếp cung cấp ở contract này | Có thể truy cập qua ServerWebExchange và các abstraction liên quan |
| Filter / exception chain | Không phải nơi khai báo trực tiếp | Được lắp ghép bởi WebHttpHandlerBuilder |
| Controller / functional endpoint | Không trực tiếp route | Là tầng nền cho mô hình lập trình WebFlux |

**ServerWebExchange** bao bọc request và response, đồng thời cung cấp các khả năng web như attributes, session, principal, locale và truy cập dữ liệu form/multipart theo cơ chế tương ứng.

Có thể xem HttpHandler là ranh giới rất thấp giữa Spring và HTTP server; WebHandler là ranh giới thuận tiện cho ứng dụng web.

## 5. HttpWebHandlerAdapter và WebHttpHandlerBuilder

### 5.1. HttpWebHandlerAdapter làm nhiệm vụ gì?

**HttpWebHandlerAdapter** là adapter phía Spring, chuyển một **WebHandler** thành **HttpHandler**. Nó tạo/chuẩn bị ServerWebExchange từ ServerHttpRequest và ServerHttpResponse rồi gọi chuỗi WebHandler tương ứng.

Vì vậy có hai loại adapter dễ nhầm:

- **HttpWebHandlerAdapter:** chuyển từ API WebHandler của Spring sang contract HttpHandler của Spring.
- **ReactorHttpHandlerAdapter / ServletHttpHandlerAdapter / TomcatHttpHandlerAdapter...:** chuyển từ contract HttpHandler sang API của máy chủ bên dưới.

Một adapter thuộc **nội bộ kiến trúc Spring WebFlux**, adapter còn lại thuộc **ranh giới runtime/server**.

### 5.2. WebHttpHandlerBuilder lắp ghép chuỗi web

**WebHttpHandlerBuilder** giúp tạo một HttpHandler hoàn chỉnh từ WebHandler và các thành phần liên quan. Builder có thể nhận một ApplicationContext để tự phát hiện bean, hoặc được cấu hình thủ công.

Ví dụ khái niệm:

~~~java
HttpHandler httpHandler =
    WebHttpHandlerBuilder
        .applicationContext(applicationContext)
        .build();
~~~

Khi ApplicationContext có cấu hình WebFlux thích hợp, builder có thể phát hiện các bean như:

- **WebHandler** đích, thường là DispatcherHandler.
- **WebFilter** cho cross-cutting concern.
- **WebExceptionHandler** để xử lý lỗi web.
- **WebSessionManager**.
- **ServerCodecConfigurer**.
- **LocaleContextResolver**.
- Các thành phần observation hoặc decorator được hỗ trợ theo phiên bản.

Chuỗi xử lý về mặt logic:

~~~text
HTTP request
    |
    v
WebExceptionHandler chain
    |
    v
WebFilter chain
    |
    v
WebHandler (thường là DispatcherHandler)
    |
    v
Annotated Controller / Functional Handler
    |
    v
Mono<Void> hoàn tất response
~~~

Exception handlers được bọc bên ngoài filter chain để có thể xử lý lỗi phát sinh trong các tầng bên trong. Filter chain bao quanh WebHandler và có thể chạy logic trước/sau handler.

### 5.3. Khi nào dùng builder thủ công?

Trong ứng dụng Spring Boot WebFlux thông thường, Boot tự cấu hình chuỗi này. Không cần tự tạo WebHttpHandlerBuilder trong mỗi controller hoặc service.

Builder thủ công hữu ích khi:

- Tự tích hợp WebFlux vào một HTTP server được nhúng theo cách riêng.
- Tạo một HttpHandler từ WebHandler độc lập.
- Viết integration test hoặc môi trường runtime tùy chỉnh.
- Cần kiểm soát rõ filter, exception handler hoặc decorator ở cấp toàn ứng dụng.

Ví dụ dùng WebHandler tự viết:

~~~java
WebHandler webHandler = exchange -> {
    exchange.getResponse().getHeaders()
        .setContentType(MediaType.TEXT_PLAIN);

    byte[] bytes = "Hello from WebHandler"
        .getBytes(StandardCharsets.UTF_8);

    DataBuffer buffer = exchange.getResponse()
        .bufferFactory()
        .wrap(bytes);

    return exchange.getResponse()
        .writeWith(Mono.just(buffer));
};

HttpHandler httpHandler =
    WebHttpHandlerBuilder.webHandler(webHandler).build();
~~~

Đây là snippet minh họa. Khi dùng WebHandler tự viết, nó có thể được bọc bởi HttpWebHandlerAdapter để trở thành HttpHandler. Nếu muốn có controller mapping, cần cấu hình DispatcherHandler cùng các thành phần WebFlux liên quan; một WebHandler đơn giản không tự tạo annotation controller routing.

## 6. Server adapter là gì?

Mỗi HTTP server có API riêng để nhận request và ghi response. Server adapter của Spring chuyển đổi các sự kiện đó thành abstraction reactive:

- Nhận method, URI, headers và body từ server.
- Cung cấp ServerHttpRequest và ServerHttpResponse cho HttpHandler.
- Chuyển luồng byte/body giữa API native và DataBuffer.
- Kết nối vòng đời request với Mono<Void>.
- Phối hợp demand, ghi dữ liệu bất đồng bộ, lỗi và cancellation theo khả năng của runtime.

Adapter **không thay thế HTTP server**. Nó cũng không tự chọn controller hoặc quyết định business routing. Nhiệm vụ chính là cầu nối giữa hai hợp đồng.

### 6.1. Các adapter thường gặp

| Máy chủ | Adapter Spring | API đích | Ghi chú |
| --- | --- | --- | --- |
| **Reactor Netty** | **ReactorHttpHandlerAdapter** | Reactor Netty HttpServer handling function | Phù hợp runtime mặc định của Spring Boot WebFlux phổ biến |
| **Servlet container** | **ServletHttpHandlerAdapter** | Servlet API, async và non-blocking I/O | Dùng khi triển khai WebFlux trên Servlet container |
| **Tomcat** | **TomcatHttpHandlerAdapter** | Tomcat-specific APIs | Tối ưu bridge đọc/ghi ByteBuffer theo API Tomcat |
| **Jetty** | **JettyHttpHandlerAdapter** | Jetty qua Servlet integration | Có trong dòng Spring Framework 6.1; ở 6.2 được deprecated để chuyển sang JettyCoreHttpHandlerAdapter |
| **Jetty 12** | **JettyCoreHttpHandlerAdapter** | Jetty Core Handler API | Adapter trực tiếp, không cần lớp Servlet trung gian |
| **Undertow** | **UndertowHttpHandlerAdapter** | Undertow HttpHandler | Bridge tới handler API của Undertow |

Tên class và mức hỗ trợ phụ thuộc phiên bản Spring Framework cùng phiên bản server. Không copy adapter của một phiên bản Spring sang project đang dùng dependency version khác mà chưa kiểm tra Javadoc tương ứng.

### 6.2. ReactorHttpHandlerAdapter

**ReactorHttpHandlerAdapter** chuyển một HttpHandler của Spring sang handler function mà Reactor Netty có thể đăng ký với HttpServer.

Cách nối:

~~~java
HttpHandler springHandler = ...;

ReactorHttpHandlerAdapter adapter =
    new ReactorHttpHandlerAdapter(springHandler);

HttpServer.create()
    .host("127.0.0.1")
    .port(8080)
    .handle(adapter)
    .bindNow();
~~~

Ở đây Reactor Netty quản lý server socket, connection và HTTP protocol. Adapter đưa request/response qua abstraction Spring, sau đó trả Mono<Void> để Reactor Netty điều phối quá trình ghi response.

### 6.3. ServletHttpHandlerAdapter

**ServletHttpHandlerAdapter** thích hợp khi WebFlux chạy trên một Servlet container. Adapter sử dụng hỗ trợ **Servlet asynchronous processing** và **non-blocking I/O** để nối Servlet request/response với contract HttpHandler.

Servlet API vẫn có mặt ở lớp runtime, nhưng application handler của WebFlux tiếp tục dùng ServerHttpRequest, ServerHttpResponse, WebHandler và Reactor.

### 6.4. TomcatHttpHandlerAdapter

**TomcatHttpHandlerAdapter** là adapter chuyên biệt dựa trên ServletHttpHandlerAdapter và sử dụng các API riêng của Tomcat để đọc/ghi dữ liệu dạng **ByteBuffer**. Khi ứng dụng chạy với Tomcat, Spring có thể sử dụng bridge tương ứng thay cho việc để controller phụ thuộc trực tiếp Tomcat API.

### 6.5. JettyHttpHandlerAdapter và JettyCoreHttpHandlerAdapter

Với các phiên bản Spring Framework 6.1, **JettyHttpHandlerAdapter** tích hợp WebFlux qua Servlet layer và API Jetty.

Từ Spring Framework 6.2, **JettyHttpHandlerAdapter** đã được deprecated để chuyển sang **JettyCoreHttpHandlerAdapter**, adapter tích hợp trực tiếp với Jetty 12 Core API mà không cần Servlet layer. Khi nâng Spring Framework/Jetty, phải chọn adapter phù hợp với phiên bản đang dùng.

### 6.6. UndertowHttpHandlerAdapter

**UndertowHttpHandlerAdapter** chuyển HttpHandler của Spring sang **io.undertow.server.HttpHandler**. Undertow quản lý server runtime; adapter kết nối request/response của Undertow với abstraction reactive của Spring.

## 7. Luồng xử lý một request từ server đến controller

Một request GET tới endpoint WebFlux có thể được hình dung theo các bước:

1. **Server nhận request:** Reactor Netty, Tomcat, Jetty hoặc Undertow tiếp nhận kết nối và parse HTTP.
2. **Adapter tạo abstraction:** server-specific adapter chuyển thông tin native thành ServerHttpRequest/ServerHttpResponse.
3. **HttpHandler được gọi:** adapter gọi method handle và nhận Mono<Void>.
4. **HttpWebHandlerAdapter tạo exchange:** request/response được bọc thành ServerWebExchange và chuyển vào chuỗi web.
5. **WebExceptionHandler/WebFilter chạy:** xử lý exception, logging, security, CORS hoặc các concern chung.
6. **DispatcherHandler tìm handler:** ánh xạ request tới controller annotation hoặc functional endpoint.
7. **Controller trả Publisher:** Mono/Flux mô tả dữ liệu và thời điểm hoàn tất.
8. **Codec ghi body:** dữ liệu Java được encode thành DataBuffer/byte theo media type.
9. **Response được ghi:** server adapter chuyển DataBuffer sang API native và hoàn tất response.
10. **Mono<Void> kết thúc:** báo cho runtime biết quá trình xử lý response đã hoàn tất; nếu có lỗi, tín hiệu lỗi được xử lý qua chuỗi exception phù hợp.

~~~text
Client
  |
  v
HTTP Server (Netty / Tomcat / Jetty / Undertow)
  |
  v
Server Adapter
  |
  v
HttpHandler
  |
  v
HttpWebHandlerAdapter
  |
  v
WebExceptionHandler -> WebFilter -> DispatcherHandler
                                      |
                                      v
                         Controller / Functional Handler
                                      |
                                      v
                                  Mono / Flux
                                      |
                                      v
                              HTTP Message Codecs
                                      |
                                      v
                               ServerHttpResponse
                                      |
                                      v
                              Server Adapter -> Client
~~~

**Điểm cần nhớ:** controller không cần biết request được nhận bởi Netty hay Tomcat. Thay đổi runtime chủ yếu nằm ở dependency và adapter; mô hình lập trình ứng dụng vẫn dùng abstraction của Spring.

## 8. DataBuffer, streaming và backpressure ở ranh giới HTTP

### 8.1. Request body

**ServerHttpRequest.getBody()** cung cấp một Flux<DataBuffer>. Thay vì bắt buộc đọc toàn bộ request body vào byte array, handler có thể xử lý dữ liệu theo từng buffer. Điều này hữu ích cho streaming và payload lớn.

~~~java
Flux<DataBuffer> body = request.getBody();
~~~

Khi tiêu thụ DataBuffer, cần chú ý quyền sở hữu và vòng đời buffer, đặc biệt với pooled buffer của Netty. Nếu ứng dụng giữ lại buffer hoặc tự quản lý reference count, phải dùng đúng quy tắc retain/release và tiện ích như DataBufferUtils khi phù hợp. Không release một buffer mà downstream vẫn cần đọc, và không giữ buffer vô hạn ngoài vòng đời request.

### 8.2. Response body

**ServerHttpResponse.writeWith(...)** nhận một Publisher<DataBuffer>. Vì dữ liệu response là Publisher, quá trình ghi có thể tiếp tục theo demand và hỗ trợ streaming thay vì gom toàn bộ dữ liệu vào RAM trước.

~~~java
return response.writeWith(
    Flux.just(buffer1, buffer2, buffer3)
);
~~~

Đây là snippet minh họa. Trong code thật, các buffer phải được tạo đúng thời điểm, đúng thứ tự và có vòng đời hợp lệ. Nếu cần ghi nhiều nhóm buffer và flush từng nhóm, API **writeAndFlushWith(...)** có thể phù hợp.

### 8.3. Backpressure ở server adapter

Reactive Streams backpressure cho phép consumer biểu thị nhu cầu. Ở HTTP boundary, adapter và server runtime cần phối hợp việc đọc/ghi body theo khả năng của API bên dưới.

Không phải mọi HTTP server có cùng cơ chế nội bộ, nhưng mục tiêu của abstraction là giữ một contract reactive nhất quán cho ứng dụng. Điều này không có nghĩa mọi tầng đều không có buffer. Server, network stack, codec và operator có thể có buffer riêng; cần cấu hình giới hạn phù hợp.

### 8.4. Client disconnect và cancellation

Nếu client ngắt kết nối khi Flux response còn đang phát, runtime có thể phát sinh cancellation tới pipeline đang ghi response. Công việc reactive còn hoạt động được yêu cầu hủy. Tuy nhiên, cancellation không bảo đảm rollback một side effect đã commit vào database hoặc một HTTP request đã được gửi tới dịch vụ khác.

Không dùng việc client disconnect làm bằng chứng rằng nghiệp vụ chưa được thực hiện. Với lệnh ghi, cần transaction, idempotency hoặc cơ chế bù trừ theo yêu cầu nghiệp vụ.

## 9. Tích hợp thủ công với Reactor Netty: chương trình Java chạy được

Ví dụ sau tạo một HttpHandler độc lập, bọc bằng ReactorHttpHandlerAdapter và đăng ký với Reactor Netty. Nó không dùng controller annotation, vì mục tiêu là nhìn rõ ranh giới giữa HttpHandler và adapter.

Dùng Spring Boot 3.3.5 (Spring Framework 6.1.x) và Java 17.

Cấu trúc:

~~~text
http-handler-adapter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/adapter/
                └── HttpHandlerAdapterDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>http-handler-adapter-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/com/example/adapter/HttpHandlerAdapterDemo.java**:

~~~java
package com.example.adapter;

import java.nio.charset.StandardCharsets;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.http.server.reactive.ReactorHttpHandlerAdapter;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

public class HttpHandlerAdapterDemo {

    public static void main(String[] args) {
        HttpHandler handler = (request, response) -> {
            response.setStatusCode(HttpStatus.OK);
            response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

            String message =
                "Handled by HttpHandler: " + request.getURI().getPath();

            DataBuffer buffer = response.bufferFactory()
                .wrap(message.getBytes(StandardCharsets.UTF_8));

            return response.writeWith(Mono.just(buffer));
        };

        ReactorHttpHandlerAdapter adapter =
            new ReactorHttpHandlerAdapter(handler);

        DisposableServer server = HttpServer.create()
            .host("127.0.0.1")
            .port(8080)
            .handle(adapter)
            .bindNow();

        System.out.println(
            "Listening on http://127.0.0.1:" + server.port()
        );

        server.onDispose().block();
    }
}
~~~

Chạy trong thư mục chứa pom.xml, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.adapter.HttpHandlerAdapterDemo
~~~

Console:

~~~text
Listening on http://127.0.0.1:8080
~~~

Mở terminal khác, gửi request:

~~~bash
curl -i http://127.0.0.1:8080/demo
~~~

Response body:

~~~text
Handled by HttpHandler: /demo
~~~

Response có status **200 OK** và Content-Type **text/plain**. Có thể đổi path thành /orders hoặc /health để thấy handler dùng URI của request. Dừng server bằng Ctrl+C trong terminal đang chạy Maven.

### Phân tích chương trình

1. **HttpHandler** là logic xử lý request ở tầng HTTP chung của Spring. Lambda không sử dụng API Netty.
2. **ServerHttpRequest** cung cấp URI; **ServerHttpResponse** cung cấp status, headers và buffer factory.
3. **DataBuffer** chứa nội dung response đã mã hóa UTF-8.
4. **writeWith(Mono.just(buffer))** trả Mono<Void>, báo completion của thao tác ghi.
5. **ReactorHttpHandlerAdapter** chuyển HttpHandler sang kiểu handler mà Reactor Netty nhận.
6. **HttpServer.handle(adapter)** gắn adapter vào server runtime.
7. **bindNow()** khởi động server đồng bộ tại ranh giới chương trình CLI; **server.onDispose().block()** giữ main thread chờ server được dispose.

Trong ứng dụng WebFlux thực tế, không nên tự khởi tạo một HttpServer thứ hai nếu Spring Boot đã quản lý server. Ví dụ này cố ý tự tạo runtime để làm rõ adapter.

## 10. Dùng các adapter khác khi tự tích hợp

### 10.1. Servlet container

Với Servlet container, có thể đăng ký **ServletHttpHandlerAdapter** như một Servlet:

~~~java
HttpHandler handler = ...;

Servlet servlet = new ServletHttpHandlerAdapter(handler);
~~~

Container quản lý Servlet lifecycle, còn adapter nối request/response Servlet với HttpHandler. Với ứng dụng triển khai WAR, Spring cung cấp các cơ chế khởi tạo reactive web application, chẳng hạn **AbstractReactiveWebInitializer**, để đăng ký adapter đúng cách.

### 10.2. Tomcat

Trong môi trường Tomcat, Spring có adapter chuyên biệt:

~~~java
Servlet servlet = new TomcatHttpHandlerAdapter(handler);
~~~

Khi dựng Tomcat nhúng thủ công, cần tạo Context, đăng ký Servlet và map URL cho Servlet đó. Phần khởi tạo server phụ thuộc cấu hình Tomcat và không cần thiết nếu Spring Boot đã tự quản lý embedded server.

### 10.3. Jetty

Với Spring Framework 6.1, có thể gặp:

~~~java
JettyHttpHandlerAdapter adapter =
    new JettyHttpHandlerAdapter(handler);
~~~

Với Spring Framework 6.2 và Jetty 12, ưu tiên adapter trực tiếp:

~~~java
JettyCoreHttpHandlerAdapter adapter =
    new JettyCoreHttpHandlerAdapter(handler);
~~~

Adapter mới làm việc với Jetty Core Handler API. Không dùng đồng thời hai adapter cho cùng một request pipeline.

### 10.4. Undertow

Với Undertow:

~~~java
UndertowHttpHandlerAdapter adapter =
    new UndertowHttpHandlerAdapter(handler);

Undertow server = Undertow.builder()
    .addHttpListener(8080, "127.0.0.1")
    .setHandler(adapter)
    .build();

server.start();
~~~

Đây là snippet cho project đã có dependency Undertow tương thích và Spring adapter tương ứng. Khi dừng server, cần gọi **server.stop()** theo vòng đời ứng dụng.

Các ví dụ trên minh họa điểm nối adapter; phần cấu hình TLS, thread pool, port, context path và shutdown của từng server cần theo tài liệu runtime tương ứng.

## 11. Spring Boot tự cấu hình adapter như thế nào?

Với ứng dụng Spring Boot WebFlux thông thường:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Boot nhận diện reactive web stack, cấu hình WebFlux và embedded server theo dependency/runtime có trên classpath. Với cấu hình phổ biến, **Reactor Netty** là server mặc định. Spring Boot xây dựng chuỗi HttpHandler và kết nối tới adapter/server tương ứng.

Điều này có nghĩa ứng dụng chỉ cần:

- Tạo class main Spring Boot.
- Khai báo controller hoặc functional route.
- Cấu hình WebFilter, WebFluxConfigurer hoặc các bean cần thiết.
- Trả Mono/Flux để framework quản lý subscription và response.

Không cần viết:

~~~java
new ReactorHttpHandlerAdapter(...);
HttpServer.create()...
~~~

trong mỗi ứng dụng Boot thông thường. Chỉ tự tích hợp khi bạn chủ động quản lý server runtime hoặc có yêu cầu embedding đặc biệt.

### 11.1. Chọn runtime qua dependency

Các lựa chọn runtime cần dependency tương thích:

- Reactor Netty: thường được kéo vào bởi starter WebFlux mặc định.
- Tomcat hoặc Jetty: cần cấu hình dependency/server tương ứng theo phiên bản Spring Boot và Spring Framework.
- Undertow: cần dependency và adapter được hỗ trợ ở phiên bản đang sử dụng.

Nếu thêm cả **spring-boot-starter-web** và **spring-boot-starter-webflux**, Spring Boot thường ưu tiên MVC khi chọn application type. Vì vậy không nên suy luận rằng có Mono/Flux trong controller là ứng dụng chắc chắn chạy bằng WebFlux. Hãy kiểm tra dependency tree và loại server thực tế khi khởi động.

### 11.2. Không bật @EnableWebFlux chỉ để đổi adapter

**@EnableWebFlux** không phải nút chọn Reactor Netty/Tomcat/Jetty. Nó bật cấu hình WebFlux thủ công và có thể làm thay đổi cách Boot auto-configuration hoạt động. Việc lựa chọn server adapter thuộc tầng runtime/server, không phải chức năng của annotation controller.

## 12. HttpHandlerDecorator và cross-cutting concern ở tầng HTTP

Spring cung cấp các điểm mở rộng quanh HttpHandler. **HttpHandlerDecorator** và **HttpHandlerDecoratorFactory** có thể dùng để bọc handler, ví dụ đo thời gian xử lý ở ranh giới HTTP hoặc thêm instrumentation.

Ý tưởng decorator:

~~~java
HttpHandler decorated = (request, response) -> {
    long started = System.nanoTime();

    return delegate.handle(request, response)
        .doFinally(signal -> {
            long elapsedNanos = System.nanoTime() - started;
            metrics.record(elapsedNanos, signal);
        });
};
~~~

Đây là snippet giả định có **delegate** và **metrics** được cung cấp. Decorator bao trùm một lần xử lý request; **doFinally** chạy khi luồng kết thúc bằng complete, error hoặc cancel.

Cần phân biệt:
- **WebFilter** phù hợp với xử lý ở tầng web, có ServerWebExchange và các abstraction của WebFlux.
- **HttpHandlerDecorator** nằm thấp hơn, bao trùm contract HttpHandler.
- **Server adapter** là cầu nối tới API server, không nên dùng để viết logic nghiệp vụ.

Nếu chỉ cần correlation ID, CORS, security hoặc xử lý request theo API WebFlux, WebFilter thường là tầng dễ dùng hơn. Chỉ chọn decorator thấp hơn khi cần quan sát hoặc can thiệp toàn bộ HttpHandler chain.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Ứng dụng Boot khởi động nhưng chạy MVC | Có spring-boot-starter-web hoặc servlet stack được chọn | Kiểm tra dependency tree và log application type |
| Controller không được gọi | Handler mapping chưa đăng ký hoặc request không khớp | Kiểm tra DispatcherHandler, mapping, method và path |
| HttpHandler chạy nhưng response không kết thúc | Mono<Void> của handler không hoàn tất hoặc writeWith bị treo | Kiểm tra Publisher body, lỗi và cancellation |
| Response body bị thiếu | DataBuffer lifecycle hoặc Publisher kết thúc quá sớm | Kiểm tra ownership buffer, writeWith và demand |
| Adapter không tương thích | Spring Framework và server version lệch | Kiểm tra Javadoc, dependency management và server API |
| Class Jetty adapter không tìm thấy | Đang dùng phiên bản Spring khác với ví dụ | Kiểm tra Spring 6.1 hay 6.2+ và adapter Jetty tương ứng |
| Có hai server cùng bind một port | Boot tự tạo server nhưng code lại tạo HttpServer thủ công | Chỉ để một thành phần sở hữu port |
| Client ngắt kết nối gây lỗi | Cancellation hoặc write failure trong response | Phân biệt cancellation với lỗi nghiệp vụ và complete |
| Memory tăng khi stream body lớn | Gom body vào bộ nhớ hoặc buffer không giới hạn | Stream DataBuffer, đặt giới hạn codec/queue |
| Blocking làm giảm throughput | Gọi block hoặc API blocking trên event-loop | Dùng client reactive hoặc cô lập blocking bằng scheduler phù hợp |
| Adapter chạy nhưng WebFilter không hoạt động | Đang dùng HttpHandler tự viết thay vì chain được builder cấu hình | Kiểm tra WebHttpHandlerBuilder và ApplicationContext |
| Lỗi không được chuyển thành response phù hợp | WebExceptionHandler chain chưa được lắp vào handler | Kiểm tra builder/application context và exception handler |

### 13.1. Checklist điều tra

1. Server runtime thực tế là gì?
2. Dependency nào đưa server vào classpath?
3. Adapter nào đang được dùng?
4. HttpHandler được tạo trực tiếp hay qua WebHttpHandlerBuilder?
5. HttpWebHandlerAdapter có bao bọc WebHandler chain không?
6. DispatcherHandler có được cấu hình và phát hiện không?
7. WebFilter và WebExceptionHandler có nằm trong ApplicationContext/chain không?
8. Mono<Void> của handler có complete hay error?
9. Request body và response body có tuân thủ DataBuffer lifecycle?
10. Có blocking hoặc subscribe thủ công làm tách vòng đời request không?

## 14. Ranh giới và nguyên tắc thiết kế

**Giữ code nghiệp vụ ở tầng WebHandler/controller, giữ việc tích hợp server ở tầng adapter.**

- Controller không nên phụ thuộc vào Reactor Netty request/response.
- WebHandler nên dùng ServerWebExchange khi cần API web tổng quát.
- HttpHandler chỉ nên xử lý những gì thuộc contract HTTP thấp.
- Adapter chỉ chuyển đổi API server, không chứa business rule.
- Khi chuyển runtime, kiểm tra dependency và cấu hình server, không viết lại controller chỉ vì server thay đổi.
- Nếu Spring Boot đang quản lý server, không tự tạo server thứ hai trên cùng port.
- Với body lớn, ưu tiên streaming DataBuffer thay vì gom tất cả vào byte[].
- Khi client disconnect, xem cancellation như một phần vòng đời request; không mặc định rollback side effect.
- Chọn đúng phiên bản adapter theo Spring Framework và server đang sử dụng.
- Dùng WebFilter cho cross-cutting concern ở tầng WebFlux; dùng HttpHandlerDecorator khi thật sự cần bao quanh toàn bộ HTTP handling contract.

## 15. Bài tập thực hành

**Bài 1 — Đọc hợp đồng:** Viết lại chữ ký HttpHandler và giải thích vì sao method trả Mono<Void> dù response có body.

**Bài 2 — Handler thuần:** Thay nội dung response trong chương trình Java thành JSON và đặt Content-Type application/json. Gửi request bằng curl rồi kiểm tra body.

**Bài 3 — Request body:** Mở rộng handler để nhận POST và đọc request.getBody(). Xử lý DataBuffer theo cách phù hợp, không subscribe body hai lần và không giữ buffer quá vòng đời.

**Bài 4 — Builder:** Viết một WebHandler đơn giản rồi dùng WebHttpHandlerBuilder.webHandler(...).build() để tạo HttpHandler. So sánh với HttpHandler lambda trực tiếp.

**Bài 5 — Adapter:** Giữ nguyên HttpHandler, thử nối vào Reactor Netty adapter. Xác định phần code nào thay đổi nếu chuyển sang Servlet/Tomcat.

**Bài 6 — Filter:** Thêm một WebFilter vào ApplicationContext và tạo HttpHandler bằng WebHttpHandlerBuilder.applicationContext(...).build(). Kiểm tra filter chạy trước WebHandler.

**Bài 7 — Exception:** Tạo một WebExceptionHandler xử lý lỗi do WebHandler phát ra. Quan sát sự khác nhau giữa lỗi được chuyển thành response và lỗi vẫn đi ra ngoài HttpHandler.

**Bài 8 — Cancellation:** Gửi một response Flux dài, ngắt curl giữa chừng và quan sát cancellation. Xác định những side effect nào đã hoàn tất trước khi client ngắt.

**Bài 9 — Phiên bản Jetty:** Đọc dependency tree của project dùng Spring Framework 6.1 và 6.2. Tìm adapter Jetty tương ứng và lý do thay đổi API.

## 16. Ghi nhớ

**HttpHandler là hợp đồng HTTP reactive thấp nhất của Spring, giúp WebFlux không phụ thuộc trực tiếp vào API của một máy chủ cụ thể.** WebHandler cung cấp API web ở tầng cao hơn; WebHttpHandlerBuilder lắp ghép WebHandler, WebFilter và WebExceptionHandler rồi tạo HttpHandler qua HttpWebHandlerAdapter. Sau đó server-specific adapter như ReactorHttpHandlerAdapter hoặc Servlet/Tomcat/Jetty/Undertow adapter kết nối HttpHandler với runtime.

Nhờ ranh giới này, controller và functional endpoint tiếp tục dùng Mono/Flux cùng abstraction của Spring khi thay đổi máy chủ. Khi debug, hãy xác định đúng tầng: route, WebHandler chain, HttpHandler contract, adapter hay server runtime.

## 17. Tài liệu tham khảo

- Spring Framework Reference — Reactive Core / HttpHandler: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework API — HttpHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/HttpHandler.html
- Spring Framework API — WebHttpHandlerBuilder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html
- Spring Framework API — ReactorHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ReactorHttpHandlerAdapter.html
- Spring Framework API — ServletHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServletHttpHandlerAdapter.html
- Spring Framework API — TomcatHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/TomcatHttpHandlerAdapter.html
- Spring Framework API — JettyCoreHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/JettyCoreHttpHandlerAdapter.html
- Spring Framework API — UndertowHttpHandlerAdapter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/UndertowHttpHandlerAdapter.html
- Reactor Netty Reference Guide: https://projectreactor.io/docs/netty/release/reference/
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
