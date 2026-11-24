# Cấu hình RSocket qua WebSocket trên máy chủ WebFlux dùng Reactor Netty

Spring Boot có thể đưa RSocket vào cùng máy chủ WebFlux đang phục vụ HTTP bằng transport WebSocket. Khi cấu hình đúng, ứng dụng chỉ cần một WebFlux server, một cổng HTTP và một đường dẫn dành cho RSocket. Reactor Netty tiếp nhận kết nối WebSocket, sau đó RSocket xử lý các interaction reactive trên kết nối đã được nâng cấp.

Điểm cần phân biệt là RSocket WebSocket **gắn vào WebFlux server** và một **RSocket server chạy độc lập**. Ở chế độ tích hợp, endpoint RSocket dùng chung cổng với HTTP và được xác định bằng mapping path. Ở chế độ độc lập, Spring Boot mở một server RSocket riêng theo cổng được cấu hình. Chọn nhầm chế độ có thể khiến client kết nối sai cổng hoặc ứng dụng mở thêm listener ngoài dự kiến.

Bài học hướng dẫn cấu hình Spring Boot WebFlux với Reactor Netty, khai báo endpoint RSocket WebSocket, tạo handler bằng Spring Messaging, kết nối bằng RSocketRequester và vận hành endpoint qua TLS, reverse proxy và kiểm thử tích hợp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách RSocket WebSocket được tích hợp vào WebFlux server.
- Chọn đúng dependency WebFlux và RSocket cho Spring Boot.
- Cấu hình transport là websocket và mapping path.
- Phân biệt cổng WebFlux với cổng của RSocket server độc lập.
- Viết handler RSocket bằng @MessageMapping.
- Kết nối đến endpoint bằng RSocketRequester.Builder.webSocket.
- Hiểu vai trò của Reactor Netty, RSocketMessageHandler và RSocketStrategies.
- Cấu hình TLS, reverse proxy, security và kiểm thử kết nối.

## 1. Kiến trúc RSocket WebSocket trên WebFlux

WebSocket cung cấp kết nối hai chiều tồn tại lâu dài qua HTTP Upgrade. RSocket sử dụng kết nối byte stream này để truyền frame và triển khai request-response, fire-and-forget, request-stream và request-channel.

Khi tích hợp vào WebFlux server, luồng xử lý có dạng:

~~~mermaid
flowchart TD
    C["RSocket client"] --> W["HTTP WebSocket handshake"]
    W --> N["Reactor Netty WebFlux server"]
    N --> P["Mapping path /rsocket"]
    P --> R["RSocket protocol"]
    R --> H["RSocketMessageHandler"]
    H --> M["Spring @MessageMapping"]
    M --> S["Reactive service"]
~~~

Các thành phần đảm nhiệm vai trò khác nhau:

- **Spring WebFlux** cung cấp ứng dụng web reactive và tích hợp với web server.
- **Reactor Netty** là web server hỗ trợ việc gắn RSocket WebSocket vào cùng listener.
- **Mapping path** xác định URL nhận WebSocket handshake dành cho RSocket.
- **RSocket protocol** xử lý frame, interaction model, multiplexing và flow control.
- **RSocketMessageHandler** chuyển request RSocket thành message để Spring dispatch.
- **@MessageMapping** ánh xạ route metadata đến method xử lý của ứng dụng.

RSocket không biến thành REST chỉ vì nó đi qua WebSocket. Sau bước HTTP Upgrade, hai phía trao đổi frame RSocket trên kết nối WebSocket.

### 1.1. Điều kiện để gắn RSocket vào WebFlux server

Spring Boot chỉ tích hợp RSocket vào web server khi ứng dụng có kiểu reactive và các thuộc tính RSocket server được cấu hình cho WebSocket với mapping path. Tính năng gắn trực tiếp vào web server hiện chỉ được hỗ trợ với Reactor Netty.

Điều này có nghĩa:

1. Ứng dụng phải chạy WebFlux.
2. Web server phải là Reactor Netty.
3. RSocket server transport phải là websocket.
4. Phải khai báo mapping path.
5. Cổng HTTP được điều khiển bởi cấu hình server của WebFlux.

Nếu ứng dụng chạy Tomcat hoặc Jetty, không thể giả định RSocket WebSocket sẽ tự gắn vào listener WebFlux theo cách này. Hãy dùng Reactor Netty cho mô hình tích hợp hoặc chọn server RSocket độc lập nếu kiến trúc yêu cầu.

## 2. Chuẩn bị dependency

Với Gradle và Spring Boot dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-rsocket")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Hai starter có trách nhiệm khác nhau:

| Dependency | Vai trò |
|---|---|
| spring-boot-starter-webflux | WebFlux application, HTTP stack và Reactor Netty mặc định |
| spring-boot-starter-rsocket | Spring Messaging RSocket, protocol integration và các codec mặc định |
| spring-boot-starter-test | Hạ tầng kiểm thử Spring Boot và JUnit |

Spring Boot quản lý version tương thích cho các dependency. Nên dùng cùng một Spring Boot release train thay vì tự ghim các version không tương thích của Reactor Netty, Spring Messaging và RSocket.

Không cần tự tạo RSocketServer bằng tay cho mô hình WebFlux tích hợp. Spring Boot tự cấu hình server và Spring Messaging handler khi dependency cùng thuộc tính phù hợp.

## 3. Cấu hình endpoint trong application.yaml

Ví dụ ứng dụng dùng cổng HTTP 8080 và dành đường dẫn /rsocket cho RSocket:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: realtime-gateway
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

Hai thuộc tính quan trọng là:

- **spring.rsocket.server.transport=websocket** chọn WebSocket làm transport của RSocket server.
- **spring.rsocket.server.mapping-path=/rsocket** chỉ định đường dẫn WebSocket handshake trên web server.

Trong cấu hình này, HTTP và RSocket WebSocket cùng dùng cổng 8080:

| Endpoint | URL ví dụ | Mục đích |
|---|---|---|
| HTTP | http://localhost:8080 | REST, health endpoint hoặc trang web nếu ứng dụng có |
| RSocket WebSocket | ws://localhost:8080/rsocket | RSocket qua WebSocket |

URL ws:// ở bảng biểu diễn endpoint WebSocket trên đường truyền. Với Spring RSocketRequester.Builder.webSocket, truyền URI http:// tương ứng; khi dùng TLS, truyền https:// và Spring thực hiện WebSocket handshake bảo mật.

Không cần khai báo một cổng RSocket riêng cho chế độ tích hợp này. Thuộc tính server.port là cổng của WebFlux web server.

### 3.1. Cấu hình bằng application.properties

Nếu dự án dùng properties thay cho YAML:

~~~properties
server.port=8080
spring.application.name=realtime-gateway
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
~~~

Hai định dạng cấu hình có cùng ý nghĩa. Chọn một định dạng thống nhất trong dự án để tránh khai báo trùng ở nhiều profile.

### 3.2. Không nhầm với RSocket server chạy độc lập

Spring Boot cũng hỗ trợ một RSocket server embedded độc lập. Ví dụ:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      port: 9898
~~~

Ở chế độ này, RSocket server mở listener riêng trên cổng 9898. Nó không phải endpoint được gắn vào WebFlux server tại mapping path /rsocket.

| Tiêu chí | Tích hợp WebFlux | Server độc lập |
|---|---|---|
| Cấu hình chính | transport và mapping-path | port và transport |
| Listener | Dùng web server hiện có | Mở listener riêng |
| Cổng | server.port của WebFlux | spring.rsocket.server.port |
| URL ví dụ | ws://host:8080/rsocket | ws://host:9898 |
| Điều kiện web server | WebFlux + Reactor Netty | Không cần gắn vào WebFlux listener |

Nếu mục tiêu là dùng chung cổng HTTP và WebSocket endpoint, hãy cấu hình mapping path và không cấu hình port cho RSocket server độc lập.

## 4. Tạo handler bằng @MessageMapping

Spring Boot tự cấu hình Spring Messaging RSocket infrastructure và tạo RSocketMessageHandler để xử lý request. Ứng dụng khai báo controller như các handler Spring thông thường:

~~~java
package com.example.realtime;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("devices.status")
    public Mono<DeviceStatus> status(DeviceQuery query) {
        return deviceService.findStatus(query.deviceId());
    }

    @MessageMapping("devices.events")
    public Flux<DeviceEvent> events(DeviceQuery query) {
        return deviceService.watchEvents(query.deviceId());
    }
}
~~~

Spring sử dụng routing metadata để chọn method có route tương ứng. Kiểu trả về reactive biểu diễn interaction:

| Kiểu trả về | Cách dùng thường gặp |
|---|---|
| Một payload vào, Mono<T> hoặc T ra | Request-response |
| Một payload vào, Flux<T> ra | Request-stream |
| Một payload vào, Mono<Void> hoặc void ra | Fire-and-forget |
| Flux<T> payload vào, kết quả 0, 1 hoặc nhiều phần tử ra | Request-channel |

Interaction model được Spring xác định theo cardinality của payload đầu vào và kết quả đầu ra. Method handler không cần tự đọc frame WebSocket hoặc tự parse RSocket protocol. Spring Messaging thực hiện việc chuyển đổi payload và dispatch route.

### 4.1. Route không phải URL HTTP

Route như devices.status là metadata của RSocket request. Mapping path /rsocket là URL dùng cho WebSocket handshake. Hai giá trị này thuộc hai lớp khác nhau:

~~~text
WebSocket URL: ws://localhost:8080/rsocket
    -> mở RSocket connection
    -> gửi RSocket request với route metadata
    -> route: devices.status
    -> DeviceController.status(...)
~~~

Không tạo một HTTP controller endpoint riêng cho từng RSocket route trừ khi ứng dụng có một API HTTP độc lập cần cung cấp.

### 4.2. Truyền DTO và codec

Client và server cần thống nhất định dạng data. Spring Boot auto-configures RSocketStrategies và các codec mặc định, thường ưu tiên CBOR với Jackson rồi JSON với Jackson nếu dependency tương ứng có sẵn. Starter RSocket cung cấp các dependency codec cần thiết theo cấu hình Spring Boot.

Ví dụ DTO:

~~~java
public record DeviceQuery(String deviceId) {
}

public record DeviceStatus(
        String deviceId,
        String state,
        Instant updatedAt) {
}
~~~

Nếu ứng dụng dùng kiểu dữ liệu tùy chỉnh, cần đăng ký encoder/decoder phù hợp trong RSocketStrategies. Client và server phải dùng codec tương thích; việc WebSocket handshake thành công không bảo đảm payload được giải mã đúng.

## 5. Tạo client bằng RSocketRequester

Spring Framework cung cấp RSocketRequester với API fluent để gửi object và nhận object. Với WebSocket, dùng phương thức webSocket và URL đầy đủ chứa mapping path:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketRequester deviceRequester(
            RSocketRequester.Builder builder) {

        URI endpoint =
                URI.create("http://localhost:8080/rsocket");

        return builder.webSocket(endpoint);
    }
}
~~~

Với TLS, URI đầu vào của Spring requester dùng scheme https:

~~~java
URI endpoint =
        URI.create("https://api.example.com/rsocket");
~~~

Phương thức webSocket của Spring nhận URI HTTP/HTTPS và thiết lập WebSocket handshake tương ứng. Ở phía trình duyệt hoặc công cụ WebSocket mức thấp, endpoint trên đường truyền tương ứng với ws:// hoặc wss://.

RSocketRequester.Builder của Spring Boot được cung cấp theo prototype scope vì builder có trạng thái. Mỗi cấu hình requester khác nhau nên nhận một builder riêng, tránh tái sử dụng cùng một builder đã được thay đổi cho nhiều endpoint hoặc setup khác nhau.

Việc tạo requester không nhất thiết mở kết nối ngay lập tức. Connection được thiết lập khi ứng dụng thực hiện request và được tái sử dụng theo vòng đời requester.

### 5.1. Gửi request-response

~~~java
public Mono<DeviceStatus> getStatus(
        RSocketRequester requester,
        String deviceId) {

    return requester
            .route("devices.status")
            .data(new DeviceQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
}
~~~

### 5.2. Nhận request-stream

~~~java
public Flux<DeviceEvent> watchEvents(
        RSocketRequester requester,
        String deviceId) {

    return requester
            .route("devices.events")
            .data(new DeviceQuery(deviceId))
            .retrieveFlux(DeviceEvent.class);
}
~~~

Client có thể hủy subscription khi người dùng rời màn hình hoặc không còn cần dữ liệu. Cancellation được truyền qua RSocket stream để server có cơ hội dừng nguồn dữ liệu tương ứng.

## 6. Quản lý kết nối và setup

WebSocket handshake chỉ tạo transport connection. Trong quá trình khởi tạo RSocket session, requester còn gửi SETUP frame với các thiết lập như MIME type, setup data và setup metadata.

Spring RSocketRequester.Builder hỗ trợ cấu hình:

- data MIME type.
- metadata MIME type.
- setup data.
- setup route.
- setup metadata.
- responder phía client nếu server cần gửi request ngược.

Setup metadata có thể dùng cho thông tin xác thực ở cấp connection. Tuy nhiên, server phải xác minh credential và tạo Principal đã xác thực. Không coi user ID hoặc tenant ID do client tự gửi là bằng chứng phân quyền.

Spring Messaging hỗ trợ @ConnectMapping để xử lý sự kiện thiết lập connection và nội dung setup. Có thể dùng nó để ghi nhận session, xác minh thông tin khởi tạo hoặc gắn context connection. Các thao tác nghiệp vụ vẫn cần authorization phù hợp ở từng route.

### 6.1. Vòng đời requester

Requester thường được quản lý như một dependency có vòng đời rõ ràng:

- Tạo requester theo endpoint và cấu hình connection.
- Dùng requester cho các request trong thời gian ứng dụng hoạt động.
- Xử lý lỗi transport, timeout và reconnect theo chính sách.
- Đóng hoặc dispose connection khi component hoặc ứng dụng dừng.

Không tạo requester mới cho từng message nếu mục tiêu là tái sử dụng một connection lâu dài. Ngược lại, cũng không chia sẻ một requester giữa các tenant nếu setup metadata hoặc danh tính connection khác nhau.

## 7. Cấu hình bảo mật và TLS

Khi endpoint được công khai qua mạng, cần bảo vệ cả WebSocket transport lẫn RSocket request:

1. Dùng HTTPS/WSS với chứng thư TLS hợp lệ.
2. Xác thực requester ở setup hoặc theo cơ chế bảo mật đã chọn.
3. Kiểm tra quyền ở từng route và thao tác.
4. Giới hạn payload và metadata size.
5. Không ghi bearer token hoặc secret vào log.
6. Áp dụng giới hạn kết nối và admission control phù hợp.

Với endpoint công khai:

~~~text
https://api.example.com/       -> HTTP WebFlux
wss://api.example.com/rsocket -> RSocket qua WebSocket bảo mật
~~~

TLS bảo vệ đường truyền nhưng không thay thế authentication và authorization. Nếu reverse proxy kết thúc TLS, cần bảo đảm kết nối từ proxy đến backend cũng được bảo vệ theo yêu cầu của hạ tầng.

## 8. Reverse proxy và WebSocket Upgrade

Trong production, endpoint thường nằm sau Nginx, ingress controller hoặc API gateway. Proxy phải hỗ trợ WebSocket Upgrade và giữ kết nối hai chiều mở đủ lâu cho RSocket session.

Các điểm cần kiểm tra:

- Chuyển tiếp HTTP Upgrade và Connection headers đúng cách.
- Giữ nguyên mapping path /rsocket hoặc rewrite nhất quán.
- Cấu hình idle timeout lớn hơn thời gian im lặng dự kiến của session hoặc dùng keepalive.
- Hỗ trợ kết nối dài hạn và không áp dụng buffering HTTP thông thường cho WebSocket stream.
- Định tuyến reconnect đến backend phù hợp nếu ứng dụng có state gắn với connection.
- Cho phép lưu lượng hai chiều và frame nhị phân.

Nếu proxy trả 404, kiểm tra mapping path. Nếu trả 400 hoặc 426 trong handshake, kiểm tra Upgrade headers và WebSocket support. Nếu kết nối mở được nhưng thường xuyên đóng khi idle, kiểm tra timeout và keepalive giữa client, proxy và server.

## 9. Cấu hình Reactor Netty và web server

Khi RSocket WebSocket được gắn vào WebFlux, Reactor Netty đảm nhiệm listener HTTP/WebSocket. Các thuộc tính web server như server.port, SSL và compression vẫn thuộc cấu hình web server của Spring Boot.

Không nên tự tạo một Reactor Netty HttpServer listener thứ hai trên cùng cổng. Spring Boot đã tích hợp RSocket endpoint vào web server theo mapping path.

Nếu dự án có cấu hình web server tùy chỉnh, hãy bảo đảm nó vẫn sử dụng Reactor Netty. Việc thay sang servlet container hoặc một WebFlux server khác có thể làm mất khả năng gắn RSocket vào listener theo cách này.

### 9.1. Kiểm tra web application type

Spring Boot cần chạy ứng dụng ở kiểu reactive. Starter WebFlux thông thường giúp chọn WebFlux khi không có cấu hình hoặc dependency servlet làm thay đổi lựa chọn auto-configuration.

Nếu ứng dụng đồng thời kéo theo Spring MVC/servlet starter, hãy kiểm tra dependency tree và web application type thực tế. Không nên giả định chỉ vì có @EnableWebFlux hoặc một dependency WebFlux là server đang chạy trên Reactor Netty.

## 10. Kiểm thử endpoint RSocket WebSocket

Một kiểm thử tích hợp nên xác minh cả transport URL và route:

1. Khởi động Spring Boot WebFlux trên cổng test.
2. Cấu hình RSocket server transport là websocket và mapping path.
3. Tạo RSocketRequester client với URI WebSocket có đúng path.
4. Gửi request-response đến route đã khai báo.
5. Đăng ký request-stream và xác minh các event được nhận.
6. Hủy stream và xác minh nguồn upstream được cleanup.
7. Thử URL sai path để xác nhận handshake không đến đúng endpoint.
8. Kiểm tra codec hai phía bằng DTO thực tế.

Ví dụ kiểm tra client:

~~~java
@Autowired
RSocketRequester.Builder requesterBuilder;

@Test
void shouldCallRSocketRoute() {
    URI endpoint = URI.create("http://localhost:8080/rsocket");

// Inject builder prototype do Spring Boot auto-configure để có codec DTO.
    RSocketRequester requester =
            requesterBuilder.webSocket(endpoint);

    StepVerifier.create(
            requester.route("devices.status")
                    .data(new DeviceQuery("sensor-17"))
                    .retrieveMono(DeviceStatus.class))
            .assertNext(status ->
                    assertThat(status.deviceId()).isEqualTo("sensor-17"))
            .verifyComplete();
}
~~~

Trong kiểm thử Spring Boot thực tế, lấy port ngẫu nhiên từ web server đang chạy và ghép URI với mapping path. Không hardcode 8080 nếu test dùng random port. Ví dụ cần các import test tương ứng như @Autowired, @Test, StepVerifier và assertThat.

### 10.1. Kiểm thử qua WebTestClient có đủ không?

WebTestClient hữu ích để kiểm thử HTTP endpoint và WebFlux controller. Tuy nhiên, một request HTTP GET đến /rsocket không chứng minh RSocket hoạt động. Cần tạo RSocket client thực sự, thực hiện WebSocket handshake rồi gửi RSocket frame đến route.

Có thể kết hợp WebTestClient cho HTTP và RSocketRequester cho RSocket trong cùng integration test.

## 11. Các lỗi thường gặp

### Chỉ cấu hình transport mà quên mapping path

RSocket không được gắn vào WebFlux server nếu thiếu mapping path phù hợp. Khai báo cả transport websocket và mapping-path.

### Cấu hình port RSocket riêng khi muốn dùng chung WebFlux listener

spring.rsocket.server.port tạo chế độ server độc lập. Với mục tiêu dùng chung HTTP listener, cấu hình mapping path trên WebFlux và dùng server.port.

### Dùng Tomcat hoặc Jetty rồi kỳ vọng WebFlux tích hợp RSocket

Việc gắn RSocket vào web server yêu cầu Reactor Netty. Kiểm tra web server implementation thực tế.

### Dùng TCP requester để gọi WebSocket endpoint

Client phải dùng WebSocket transport và URI có đúng mapping path. TCP và WebSocket là hai transport khác nhau.

### Nhầm mapping path với route metadata

Mapping path chọn endpoint WebSocket. Route metadata chọn method @MessageMapping sau khi RSocket session đã được thiết lập.

### Chỉ kiểm tra HTTP handshake

Handshake thành công chưa chứng minh codec, route hoặc interaction hoạt động. Gửi một request RSocket thực sự trong integration test.

### Proxy đóng kết nối quá sớm

RSocket thường giữ WebSocket lâu dài. Kiểm tra idle timeout, keepalive, Upgrade headers và khả năng hỗ trợ connection dài hạn của proxy.

### Tạo requester mới cho mỗi request

Việc này làm tăng chi phí handshake và connection. Tái sử dụng requester theo endpoint và security context phù hợp.

## 12. Checklist triển khai

Trước khi phát hành RSocket WebSocket trên WebFlux, hãy xác nhận:

1. Có spring-boot-starter-webflux và spring-boot-starter-rsocket tương thích.
2. Ứng dụng chạy WebFlux reactive.
3. Web server thực tế là Reactor Netty.
4. spring.rsocket.server.transport được đặt là websocket.
5. spring.rsocket.server.mapping-path được khai báo chính xác.
6. server.port là cổng HTTP/WebFlux dùng chung.
7. Không vô tình cấu hình RSocket server độc lập nếu muốn dùng chung listener.
8. RSocketMessageHandler nhận và dispatch route @MessageMapping.
9. Client dùng RSocketRequester.Builder.webSocket với URI đúng path.
10. Codec data và metadata tương thích giữa hai phía.
11. TLS, authentication và authorization được cấu hình.
12. Reverse proxy hỗ trợ WebSocket Upgrade và kết nối dài hạn.
13. Integration test gửi request RSocket thật, không chỉ kiểm tra HTTP.
14. Cancellation, timeout và graceful shutdown được kiểm tra.

## 13. Tổng kết

Spring Boot có thể gắn RSocket qua WebSocket trực tiếp vào WebFlux server khi ứng dụng chạy reactive và sử dụng Reactor Netty. Cấu hình trọng tâm gồm transport là websocket và mapping path, ví dụ /rsocket. WebFlux dùng server.port cho listener HTTP; RSocket WebSocket dùng chung cổng đó tại mapping path.

Spring Boot tự cấu hình RSocketMessageHandler và RSocketStrategies để dispatch route, encode và decode payload. Ứng dụng khai báo handler bằng @MessageMapping và client kết nối bằng RSocketRequester.Builder.webSocket. Khi triển khai production, cần phân biệt mô hình tích hợp với server độc lập, kiểm tra Reactor Netty, bảo vệ bằng WSS, cấu hình proxy Upgrade và kiểm thử bằng một RSocket client thực sự.

## Tài liệu tham khảo

- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
