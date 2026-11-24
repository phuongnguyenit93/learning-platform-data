# Kiểm thử tích hợp Spring Boot với cổng động và RSocketRequester

## Bối cảnh: kiểm thử phải đi qua kết nối RSocket thật

Một unit test có thể kiểm tra service hoặc handler riêng lẻ, nhưng không chứng minh client và server thực sự giao tiếp được qua RSocket. Những lỗi như route metadata không đúng, codec không tương thích, cấu hình transport sai, responder chưa được khởi động hoặc interaction model không khớp chỉ xuất hiện khi hai phía trao đổi payload.

Kiểm thử tích hợp Spring Boot có thể khởi động ApplicationContext thật, dựng RSocket server và dùng RSocketRequester làm client trong test. Thay vì cố định một cổng như 7000 hoặc 9898, hãy yêu cầu hệ điều hành cấp cổng chưa sử dụng bằng cách cấu hình:

~~~properties
spring.rsocket.server.port=0
~~~

Sau khi RSocket server bind thành công, Spring Boot công bố cổng thực qua thuộc tính local.rsocket.server.port. Test lấy giá trị đó bằng @LocalRSocketServerPort rồi tạo RSocketRequester kết nối tới localhost.

Cách làm này giúp test chạy song song trên CI mà không tranh chấp cổng cố định. Bài học này trình bày cách khởi động server, lấy cổng động, tạo và đóng requester, kiểm thử request-response và request-stream, xác minh lỗi, kiểm soát lifecycle và phân biệt cổng TCP độc lập với RSocket chạy trên WebSocket.

## 1. Phân biệt kiểm thử unit, slice test và integration test

Mỗi loại test xác minh một phạm vi khác nhau:

| Loại test | Thành phần được chạy | Điều được xác minh |
|---|---|---|
| Unit test | Service, mapper hoặc handler với dependency giả | Logic nghiệp vụ và nhánh xử lý |
| Spring context/slice test | Một phần ApplicationContext | Wiring, bean và cấu hình giới hạn |
| RSocket integration test | Spring Boot context, RSocket server, requester và transport thật | Route, codec, metadata, interaction và lifecycle |
| End-to-end test | Nhiều service và dependency thật | Hành vi của toàn hệ thống trong môi trường gần production |

Với mục tiêu kiểm tra Spring Boot và RSocketRequester, test nên đi qua transport thật. Không chỉ gọi trực tiếp method của controller hoặc gọi service bean rồi kết luận route RSocket hoạt động.

Một integration test cơ bản cần xác minh:

1. Spring Boot tạo được RSocket server.
2. Server bind thành công vào cổng động.
3. Test lấy đúng cổng thực tế sau khi server sẵn sàng.
4. RSocketRequester kết nối được tới server.
5. Route được định tuyến tới đúng @MessageMapping handler.
6. Payload được encode/decode đúng.
7. Response hoặc lỗi có semantics đúng.
8. Requester và tài nguyên test được đóng sau khi test kết thúc.

### Dependency cần thiết

Với Gradle và Spring Boot dependency management, các dependency thường dùng là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Nếu kiểm thử RSocket được map lên HTTP WebSocket bằng WebFlux, ứng dụng cần thêm spring-boot-starter-webflux. Để dependency management của Spring Boot chọn phiên bản tương thích; không tự ghim phiên bản Reactor khác với BOM nếu không có lý do cụ thể.

## 2. Khởi động RSocket TCP server trên cổng động

Nếu ứng dụng mở RSocket TCP server độc lập, cấu hình cổng bằng 0:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 0
~~~

Giá trị 0 yêu cầu hệ điều hành chọn một cổng khả dụng tại thời điểm bind. Không cần tự dò cổng trống bằng cách mở rồi đóng ServerSocket trong test.

Cách dò thủ công có race condition:

1. Test tìm một cổng đang trống.
2. Test đóng socket dùng để dò.
3. Một process khác có thể chiếm cổng đó.
4. RSocket server bắt đầu bind và gặp lỗi Address already in use.

Cho server bind trực tiếp vào port 0 giúp hệ điều hành chọn cổng trong cùng thao tác bind, loại bỏ khoảng thời gian tranh chấp này.

Có thể đặt thuộc tính ngay trên test:

~~~java
@SpringBootTest(properties = {
    "spring.rsocket.server.transport=tcp",
    "spring.rsocket.server.port=0"
})
class DeviceRSocketIntegrationTest {
    // Test body
}
~~~

Hoặc đặt trong file cấu hình dành cho profile test nếu nhiều lớp test dùng chung thiết lập. Với ví dụ này, thuộc tính trên annotation giúp người đọc thấy rõ test đang khởi động một RSocket TCP server độc lập.

### Không nhầm cổng RSocket với cổng HTTP

@SpringBootTest(webEnvironment = RANDOM_PORT) điều khiển cổng của embedded HTTP server. Nó không tự động biến cổng HTTP thành cổng RSocket TCP độc lập.

Khi ứng dụng dùng RSocket TCP server riêng, thuộc tính cần đặt là spring.rsocket.server.port=0 và cổng thực cần lấy là local.rsocket.server.port.

Không inject spring.rsocket.server.port rồi dùng giá trị 0 để kết nối. Giá trị cấu hình vẫn là 0; client phải dùng cổng thực được cấp sau khi server bind.

## 3. Lấy cổng RSocket thực tế bằng @LocalRSocketServerPort

Spring Boot cung cấp annotation @LocalRSocketServerPort để inject cổng mà RSocket server đã bind.

Ví dụ:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class DeviceRSocketIntegrationTest {

    @LocalRSocketServerPort
    private int rsocketPort;
}
~~~

Annotation này đọc thuộc tính local.rsocket.server.port. Spring Boot chỉ có thể cung cấp giá trị thực sau khi RSocket server khởi động và phát sự kiện RSocketServerInitializedEvent.

Nếu cần đọc trực tiếp qua Environment, có thể lấy thuộc tính local.rsocket.server.port sau khi ApplicationContext đã hoàn tất khởi động:

~~~java
int port = environment.getRequiredProperty(
    "local.rsocket.server.port",
    Integer.class
);
~~~

Không đọc giá trị này quá sớm trong constructor của bean ứng dụng. Cổng chỉ được biết sau khi server đã bind. Trong test, inject vào field hoặc phương thức test sau khi context sẵn sàng là cách đơn giản hơn.

### Khác biệt package theo phiên bản Spring Boot

Package của annotation đã thay đổi theo các phiên bản:

| Phiên bản Spring Boot | Annotation |
|---|---|
| 2.2 đến 2.6 | org.springframework.boot.rsocket.context.LocalRSocketServerPort |
| 2.7 trở lên | org.springframework.boot.test.rsocket.server.LocalRSocketServerPort |

Ở Spring Boot 2.7, package cũ được thay thế bằng annotation trong test package. Hãy dùng package phù hợp với phiên bản Boot do dự án quản lý.

Nếu phiên bản dự án chưa có annotation thuận tiện này, có thể inject thuộc tính local.rsocket.server.port bằng @Value hoặc đọc qua Environment, miễn là RSocketPortInfoApplicationContextInitializer được đăng ký theo cách phù hợp với phiên bản đó.

## 4. Tạo RSocketRequester từ builder do Spring Boot cung cấp

Spring Boot auto-configure RSocketRequester.Builder cùng các codec và RSocketStrategies của ứng dụng. Dùng builder này giúp test đi qua cùng cấu hình encode/decode mà ứng dụng sử dụng.

Ví dụ khởi tạo requester:

~~~java
RSocketRequester requester = requesterBuilder.tcp(
    "localhost",
    rsocketPort
);
~~~

Lời gọi tcp(...) tạo requester cho endpoint TCP. Kết nối thực tế thường được thiết lập khi interaction đầu tiên được subscribe, vì requester sử dụng kết nối dùng chung và có thể khởi tạo theo nhu cầu.

### Builder là prototype bean

RSocketRequester.Builder có trạng thái cấu hình. Spring Boot cung cấp builder theo scope prototype để mỗi lần inject hoặc yêu cầu bean có thể nhận một instance riêng.

Nếu cần một builder mới cho từng test, có thể inject ObjectProvider:

~~~java
@Autowired
private ObjectProvider<RSocketRequester.Builder> requesterBuilders;

private RSocketRequester newRequester(int port) {
    return requesterBuilders.getObject()
        .tcp("localhost", port);
}
~~~

ObjectProvider.getObject() yêu cầu Spring cấp một instance builder mới. Điều này hữu ích khi mỗi test dùng setup data, metadata, MIME type hoặc responder khác nhau.

Không tái sử dụng một builder đã cấu hình cho nhiều requester với các setup khác nhau nếu không hiểu rõ trạng thái nội bộ của builder. Tạo builder mới giúp test độc lập và dễ đọc hơn.

## 5. Viết responder Spring để kiểm thử

Một integration test cần route thực sự được đăng ký trong Spring context. Ví dụ controller:

~~~java
package com.example.device;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
class DeviceRSocketController {

    @MessageMapping("device.greeting")
    Mono<String> greeting(@Payload String name) {
        return Mono.just("Hello, " + name);
    }

    @MessageMapping("device.samples")
    Flux<Integer> samples(@Payload Integer count) {
        return Flux.range(1, count);
    }
}
~~~

Route device.greeting nhận một payload và trả một response. Route device.samples nhận một request chứa số lượng phần tử và trả một Flux.

Spring Messaging dùng @MessageMapping để ánh xạ route metadata tới method handler. Kiểu trả về Mono biểu diễn một response; Flux biểu diễn nhiều response.

Trong test, nên gọi đúng route và payload như một client thực tế. Không gọi trực tiếp greeting(...) hoặc samples(...) vì cách đó bỏ qua route matching, transport và codec.

## 6. Integration test hoàn chỉnh cho TCP và cổng động

Một lớp test có thể dùng RSocketRequester.Builder và cổng đã được cấp:

~~~java
package com.example.device;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "spring.rsocket.server.transport=tcp",
    "spring.rsocket.server.port=0"
})
class DeviceRSocketIntegrationTest {

    @LocalRSocketServerPort
    private int rsocketPort;

    @Autowired
    private ObjectProvider<RSocketRequester.Builder> requesterBuilders;

    private RSocketRequester requester;

    @BeforeEach
    void setUp() {
        requester = requesterBuilders.getObject()
            .tcp("localhost", rsocketPort);
    }

    @AfterEach
    void tearDown() {
        if (requester != null) {
            requester.rsocket().dispose();
        }
    }

    @Test
    void startsServerOnDynamicPort() {
        assertThat(rsocketPort).isPositive();
    }

    @Test
    void handlesRequestResponse() {
        StepVerifier.create(
            requester.route("device.greeting")
                .data("RSocket")
                .retrieveMono(String.class)
        )
        .expectNext("Hello, RSocket")
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void handlesRequestStream() {
        StepVerifier.create(
            requester.route("device.samples")
                .data(3)
                .retrieveFlux(Integer.class)
        )
        .expectNext(1, 2, 3)
        .verify(Duration.ofSeconds(5));
    }
}
~~~

Các điểm quan trọng:

- @SpringBootTest tải cấu hình ứng dụng và khởi động RSocket server.
- spring.rsocket.server.port=0 yêu cầu cổng động.
- @LocalRSocketServerPort nhận cổng RSocket thực tế.
- ObjectProvider cấp builder mới cho mỗi test.
- requesterBuilder.tcp(...) tạo requester kết nối localhost và cổng đã bind.
- StepVerifier subscribe vào publisher và xác minh response.
- verify(Duration) giới hạn thời gian chờ để test không treo vô hạn.
- requester.rsocket().dispose() đóng kết nối sau test.

Ví dụ trên giả định dự án dùng Spring Boot 2.7 trở lên với package annotation hiện hành. Nếu dùng Boot cũ hơn, thay import @LocalRSocketServerPort bằng package tương ứng đã nêu ở phần trước.

## 7. Vì sao nên dùng StepVerifier?

RSocketRequester trả về Mono hoặc Flux. Đây là Publisher reactive, nên test cần subscribe để interaction thực sự diễn ra.

StepVerifier cho phép kiểm tra lần lượt các tín hiệu:

- onNext: response payload.
- onComplete: interaction hoàn tất bình thường.
- onError: interaction kết thúc bằng lỗi.
- Cancellation: test chủ động hủy stream.

Ví dụ request-response:

~~~java
Mono<String> result = requester.route("device.greeting")
    .data("Spring")
    .retrieveMono(String.class);

StepVerifier.create(result)
    .expectNext("Hello, Spring")
    .verify(Duration.ofSeconds(5));
~~~

Ví dụ request-stream:

~~~java
Flux<Integer> result = requester.route("device.samples")
    .data(4)
    .retrieveFlux(Integer.class);

StepVerifier.create(result)
    .expectNext(1, 2, 3, 4)
.verify(Duration.ofSeconds(5));
~~~

Nếu route có thể chờ lâu hoặc phụ thuộc external service, luôn đặt timeout:

~~~java
StepVerifier.create(result)
    .expectNextCount(4)
    .verify(Duration.ofSeconds(10));
~~~

Tránh gọi block() trong mọi test chỉ vì nó ngắn hơn. StepVerifier thể hiện rõ số response, thứ tự, complete, error và cancellation. block() vẫn có thể dùng khi test rất đơn giản, nhưng cần timeout và phải hiểu rằng nó chặn thread test.

## 8. Kiểm thử request-stream với cancellation

Một stream có thể phát liên tục. Test cần xác minh client hủy subscription thì server nhận cancellation và dọn resource tương ứng.

Ví dụ responder:

~~~java
@MessageMapping("device.live")
Flux<Long> liveSamples() {
    return Flux.interval(Duration.ofMillis(100))
        .doOnCancel(() -> metrics.streamCancelled());
}
~~~

Test chỉ nhận một vài phần tử rồi cancel:

~~~java
StepVerifier.create(
    requester.route("device.live")
        .retrieveFlux(Long.class)
)
.expectNext(0L, 1L, 2L)
.thenCancel()
.verify(Duration.ofSeconds(5));
~~~

Nếu cần xác nhận cleanup ở server, dùng latch, counter hoặc test probe để đợi tín hiệu cancellation trong giới hạn thời gian. Không dùng Thread.sleep dài vì test sẽ chậm và dễ flaky.

Khi server mở database cursor, listener hoặc broker subscription cho mỗi request-stream, cancellation phải được truyền tới nguồn và resource cần được đóng. Integration test có thể phát hiện listener bị rò rỉ hoặc publisher tiếp tục chạy sau khi client dừng.

## 9. Kiểm thử lỗi và route không tồn tại

Test thành công chỉ xác minh một đường đi. Cần kiểm tra cả route sai, payload không hợp lệ và lỗi từ service.

Ví dụ gọi route không tồn tại:

~~~java
@Test
void unknownRouteReturnsError() {
    StepVerifier.create(
        requester.route("device.unknown")
            .data("test")
            .retrieveMono(String.class)
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
}
~~~

Không nên phụ thuộc vào chuỗi message lỗi nội bộ nếu message có thể thay đổi giữa các phiên bản Spring. Chỉ assert loại lỗi hoặc nội dung ổn định mà ứng dụng đã định nghĩa.

Nếu service ném lỗi miền, có thể kiểm tra mapping lỗi:

~~~java
@Test
void invalidDeviceReturnsDomainError() {
    StepVerifier.create(
        requester.route("device.lookup")
            .data("missing-device")
            .retrieveMono(DeviceStatus.class)
    )
    .expectErrorSatisfies(error ->
        assertThat(error)
            .hasMessageContaining("Device not found")
    )
    .verify(Duration.ofSeconds(5));
}
~~~

Trong hệ thống thực tế, nên kiểm tra cả lỗi xác thực, phân quyền, codec và lỗi dependency. Đừng chỉ kiểm tra rằng client nhận được một lỗi chung; hãy xác nhận handler không thực thi tác dụng phụ nếu request phải bị từ chối ở tầng security.

## 10. Kiểm thử DTO và codec

Khi gửi DTO thay vì String hoặc Integer, test cần xác nhận encoder và decoder đã được cấu hình đúng.

Ví dụ DTO:

~~~java
public record DeviceQuery(String deviceId) {}

public record DeviceStatus(
    String deviceId,
    String state
) {}
~~~

Handler:

~~~java
@MessageMapping("device.status")
Mono<DeviceStatus> status(@Payload DeviceQuery query) {
    return Mono.just(
        new DeviceStatus(query.deviceId(), "ONLINE")
    );
}
~~~

Test:

~~~java
@Test
void encodesAndDecodesDtoPayload() {
    StepVerifier.create(
        requester.route("device.status")
            .data(new DeviceQuery("device-01"))
            .retrieveMono(DeviceStatus.class)
    )
    .assertNext(status -> {
        assertThat(status.deviceId()).isEqualTo("device-01");
        assertThat(status.state()).isEqualTo("ONLINE");
    })
    .verify(Duration.ofSeconds(5));
}
~~~

Spring Boot auto-configure RSocketStrategies và các codec theo dependency có trên classpath. Nếu ứng dụng dùng JSON, CBOR hoặc codec riêng, test nên sử dụng chính RSocketRequester.Builder do Boot cung cấp để kiểm tra đúng cấu hình đó.

Nếu client và server dùng cấu hình codec khác nhau, lỗi có thể xuất hiện ở bước decode dù route đã được gọi. Hãy xác nhận data MIME type, metadata MIME type và encoder/decoder của cả hai phía.

## 11. Kiểm thử metadata và SETUP

RSocket có metadata ở cấp connection và metadata theo từng request. Nếu ứng dụng dùng authentication trong SETUP, test có thể tạo requester với setup metadata:

~~~java
RSocketRequester requester = requesterBuilders.getObject()
    .setupMetadata(
        credentials,
        authenticationMimeType
    )
    .tcp("localhost", rsocketPort);
~~~

Nếu metadata được gửi theo từng request:

~~~java
Mono<DeviceStatus> result = requester
    .route("device.status")
    .metadata(tenantContext, tenantMimeType)
    .data(new DeviceQuery("device-01"))
    .retrieveMono(DeviceStatus.class);
~~~

Test nên xác minh:

- Server nhận được metadata đúng MIME type.
- Principal hoặc tenant context được tạo đúng.
- Request thiếu metadata bị từ chối khi route yêu cầu xác thực.
- Metadata sai định dạng tạo lỗi có thể quan sát.
- Request có quyền chỉ truy cập đúng phạm vi dữ liệu.

Không chia sẻ token hoặc credential thật trong test. Dùng test key, test identity hoặc mock identity provider dành riêng cho môi trường kiểm thử.

## 12. Kiểm thử RSocket qua WebSocket với cổng HTTP động

Một ứng dụng WebFlux có thể gắn RSocket vào HTTP server qua WebSocket. Cấu hình này khác với RSocket TCP server độc lập.

Ví dụ:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket

server:
  port: 0
~~~

Test dùng cổng HTTP ngẫu nhiên:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.rsocket.server.transport=websocket",
        "spring.rsocket.server.mapping-path=/rsocket",
        "server.port=0"
    }
)
class DeviceRSocketWebSocketIntegrationTest {

    @LocalServerPort
    private int httpPort;

    @Autowired
    private ObjectProvider<RSocketRequester.Builder> requesterBuilders;

    @Test
    void communicatesOverWebSocket() {
        RSocketRequester requester = requesterBuilders.getObject()
            .websocket(URI.create(
                "ws://localhost:" + httpPort + "/rsocket"
            ));

        try {
            StepVerifier.create(
                requester.route("device.greeting")
                    .data("WebSocket")
                    .retrieveMono(String.class)
            )
            .expectNext("Hello, WebSocket")
            .verify(Duration.ofSeconds(5));
        }
        finally {
            requester.rsocket().dispose();
        }
    }
}
~~~

Trong trường hợp này:

- RSocket được gắn vào WebFlux HTTP server.
- server.port=0 yêu cầu HTTP server lấy cổng động.
- @LocalServerPort nhận cổng HTTP thực tế.
- RSocketRequester.Builder.websocket(...) kết nối tới đường dẫn mapping của RSocket.
- URL dùng ws:// cho kết nối không TLS hoặc wss:// khi dùng TLS.

WebSocket mapping cần môi trường WebFlux với Reactor Netty theo hỗ trợ của Spring Boot. Nếu ứng dụng có cả Spring MVC và WebFlux trên classpath, Spring Boot có thể chọn MVC; khi cần chạy reactive web application, hãy cấu hình spring.main.web-application-type=reactive trong test hoặc cấu hình ứng dụng phù hợp.

Không dùng @LocalRSocketServerPort cho trường hợp RSocket đã được gắn vào HTTP WebSocket endpoint. Cổng cần lấy lúc này là cổng HTTP thông qua @LocalServerPort.

## 13. Phân biệt hai kiểu cấu hình cổng động

Hai trường hợp thường bị nhầm:

| Mô hình | Cấu hình cổng động | Annotation lấy cổng | Cách kết nối |
|---|---|---|---|
| RSocket TCP server độc lập | spring.rsocket.server.port=0 | @LocalRSocketServerPort | builder.tcp("localhost", port) |
| RSocket WebSocket gắn vào WebFlux HTTP server | server.port=0 | @LocalServerPort | builder.websocket(uri) |

RSocket TCP độc lập không cần HTTP server. Vì vậy @SpringBootTest mặc định với webEnvironment MOCK vẫn có thể chạy RSocket server độc lập khi cấu hình spring.rsocket.server.port.

Ngược lại, WebSocket mapping dùng HTTP server. Test phải khởi động embedded web server bằng RANDOM_PORT và kết nối tới URL WebSocket.

Chọn đúng mô hình trước khi viết test. Nếu dùng nhầm annotation lấy cổng, test có thể kết nối sai endpoint hoặc nhận giá trị không tồn tại.

## 14. Quản lý lifecycle của requester và test context

Spring Test có thể cache ApplicationContext giữa các lớp test có cấu hình giống nhau. Điều này giúp giảm thời gian khởi động server. Tuy nhiên, mỗi requester và connection vẫn cần được quản lý rõ ràng.

Các nguyên tắc nên áp dụng:

- Tạo requester trong @BeforeEach nếu mỗi test cần connection riêng.
- Hoặc dùng một requester dùng chung cho cả lớp nếu test không thay đổi SETUP và không có trạng thái tương tác gây ảnh hưởng lẫn nhau.
- Gọi requester.rsocket().dispose() sau khi test kết thúc.
- Không giữ requester trỏ tới server của context đã bị đóng.
- Không để stream vô hạn chạy qua nhiều test.
- Đóng subscription và resource trong finally hoặc lifecycle callback.
- Dùng timeout cho StepVerifier để phát hiện test bị treo.

Nếu tạo requester một lần trong @BeforeAll, cần đảm bảo requester vẫn hợp lệ trong toàn bộ vòng đời test class và được đóng ở @AfterAll. Nếu test chạy song song, không để nhiều test cùng sửa trạng thái mutable của một responder hoặc dùng chung dữ liệu test không cô lập.

### Builder prototype và requester lifecycle là hai việc riêng

Builder là đối tượng tạo requester. Requester đại diện cho kết nối RSocket và các interaction trên kết nối đó. Lấy builder mới không có nghĩa requester cũ đã đóng; test vẫn phải dispose requester khi hoàn tất.

Không tạo một requester mới cho mọi payload trong cùng stream. Tái sử dụng connection cho nhiều interaction là một phần của mô hình RSocket multiplexing và giúp test phản ánh cách ứng dụng thực tế vận hành.

### Khác biệt API giữa Spring Framework 5.2 và 5.3 trở lên

Ví dụ chính trong bài dùng API builder từ Spring Framework 5.3 trở lên: tcp(...) trả về RSocketRequester và kết nối được khởi tạo khi interaction đầu tiên được subscribe. Trong Spring Framework 5.2, API là connectTcp(...), trả về Mono<RSocketRequester>; test cần chờ kết quả kết nối trước khi dùng requester:

~~~java
RSocketRequester requester = requesterBuilders.getObject()
    .connectTcp("localhost", rsocketPort)
    .block(Duration.ofSeconds(5));
~~~

Tương tự, WebSocket builder ở Spring Framework 5.2 dùng connectWebSocket(URI) và trả về Mono<RSocketRequester>, còn từ Spring Framework 5.3 dùng websocket(URI) trả về requester. Các phương thức connectTcp và connectWebSocket vẫn tồn tại nhưng đã deprecated từ 5.3. Hãy kiểm tra Javadoc của phiên bản Spring Framework được Spring Boot BOM quản lý trước khi chọn lời gọi.

## 15. Test song song và tránh tranh chấp cổng

Cổng động giúp nhiều test context có thể khởi động server cùng lúc mà không cần phân công cổng tĩnh.

Một số lưu ý:

- Mỗi server phải bind trực tiếp vào port 0.
- Không tự chọn cổng bằng cách kiểm tra trước rồi mới bind.
- Lấy cổng từ thuộc tính local sau khi server đã sẵn sàng.
- Không ghi cứng localhost port vào test.
- Không để test phụ thuộc vào thứ tự chạy.
- Dữ liệu dùng chung phải được reset hoặc có định danh riêng.
- Nếu context cache được dùng chung, không đóng server context từ một test khi test khác còn sử dụng.

Test song song vẫn có thể tranh chấp ở database, message broker hoặc dữ liệu fixture. Cổng động chỉ giải quyết xung đột socket; nó không tự cô lập dependency và dữ liệu nghiệp vụ.

## 16. Transaction và dữ liệu test

Một test có thể được đánh dấu @Transactional để rollback thao tác database sau khi test hoàn tất. Nhưng với integration test RSocket, test client và server xử lý request trên các thread và transaction riêng.

Transaction mở ở test thread không tự bao quanh transaction trong handler server. Vì vậy, dữ liệu do RSocket handler ghi vào database có thể không bị rollback bởi transaction của test method.

Các cách quản lý dữ liệu phù hợp:

- Tạo dữ liệu fixture có ID riêng cho từng test.
- Xóa dữ liệu trong @AfterEach bằng repository hoặc test cleanup service.
- Dùng schema/database riêng cho test suite.
- Dùng Testcontainers nếu cần database thật trong integration test.
- Tránh dựa vào thứ tự chạy test để dữ liệu còn lại từ test trước.

Nếu test xác minh transaction nghiệp vụ, hãy kiểm tra kết quả đã commit bằng một truy vấn độc lập sau khi interaction hoàn tất.

## 17. Kiểm thử timeout, reconnect và nhiều interaction

Ngoài request-response và request-stream cơ bản, có thể bổ sung test cho các trường hợp thực tế:

| Tình huống | Kiểm tra |
|---|---|
| Server phản hồi chậm | Client timeout đúng chính sách |
| Handler phát lỗi | Client nhận lỗi và resource được đóng |
| Client cancel stream | Server dừng nguồn dữ liệu |
| Nhiều request trên một requester | Các interaction multiplex độc lập |
| Requester kết nối lại | Connection mới có thể thực hiện route |
| Metadata thiếu hoặc sai | Security policy từ chối |
| Payload sai schema | Codec trả lỗi có thể quan sát |
| Server context đóng | Request đang chạy kết thúc theo hành vi dự kiến |
| Stream dài hạn | Keepalive và cancellation được kiểm tra |

Không nên đưa mọi kịch bản vào một test lớn. Chia test theo mục đích giúp xác định nhanh lớp lỗi: cấu hình server, route, codec, security hay lifecycle.

Với reconnect và Resume, cần test riêng vì hành vi đó phụ thuộc cấu hình Resume, session state và transport. Một test chỉ dispose requester rồi tạo requester mới là test kết nối mới, không phải test Resume session cũ.

## 18. Cấu trúc test suite đề xuất

Một bộ test vừa đủ có thể chia như sau:

| Lớp test | Mục tiêu | Ví dụ |
|---|---|---|
| DeviceServiceTest | Logic nghiệp vụ | Tra cứu trạng thái, validation |
| DeviceRSocketIntegrationTest | TCP và route | Request-response, request-stream |
| DeviceRSocketCodecTest | Serialization | DTO, nested type, MIME |
| DeviceRSocketSecurityTest | Authentication/authorization | SETUP metadata, request metadata |
| DeviceRSocketLifecycleTest | Resource lifecycle | Cancel, dispose, timeout |
| DeviceRSocketWebSocketTest | WebSocket transport | Mapping path và HTTP dynamic port |

Cấu trúc này tránh việc mọi thay đổi đều phải chạy một test suite end-to-end rất lớn, đồng thời vẫn giữ một lớp integration test đi qua transport thật.

## 19. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng cổng TCP cố định | Test song song có thể bind trùng cổng | Dùng spring.rsocket.server.port=0 |
| Dùng @LocalServerPort cho RSocket TCP độc lập | Lấy nhầm cổng HTTP hoặc không có HTTP server | Dùng @LocalRSocketServerPort |
| Dùng @LocalRSocketServerPort cho WebSocket mapping | Kết nối sai cổng | Dùng @LocalServerPort của HTTP server |
| Inject spring.rsocket.server.port sau khi đặt 0 | Client cố kết nối tới port 0 | Lấy local.rsocket.server.port |
| Tự dò cổng trống trước khi server bind | Có race condition | Để server bind port 0 trực tiếp |
| Gọi controller method trực tiếp | Bỏ qua transport, route và codec | Gửi request qua RSocketRequester |
| Không subscribe Mono/Flux trong test | Interaction không thực sự chạy | Dùng StepVerifier hoặc block có timeout |
| Không đặt timeout | Test có thể treo lâu | Dùng verify(Duration) |
| Dùng một builder mutable cho nhiều setup | Cấu hình test có thể ảnh hưởng lẫn nhau | Lấy builder prototype mới |
| Không dispose requester | Connection và resource còn mở | Dispose trong @AfterEach/@AfterAll |
| Cho rằng @Transactional rollback server request | Dữ liệu server đã commit vẫn còn | Cleanup dữ liệu riêng |
| Dùng HTTP WebTestClient để kiểm tra route RSocket | Không kiểm tra RSocket interaction | Dùng RSocketRequester |
| Không kiểm tra codec | Route có thể chạy nhưng DTO decode sai | Test payload DTO qua requester |
| Chỉ test happy path | Bỏ sót lỗi route, timeout và security | Bổ sung test lỗi và lifecycle |

## Kết luận

Kiểm thử tích hợp RSocket với Spring Boot cần một server thật, một cổng được cấp động và một requester gửi request qua transport. Với RSocket TCP độc lập, đặt spring.rsocket.server.port=0 rồi lấy cổng thực bằng @LocalRSocketServerPort. Tạo RSocketRequester từ builder do Spring Boot cung cấp và dùng StepVerifier để kiểm tra response, stream, lỗi và cancellation.

Nếu RSocket được gắn vào WebFlux HTTP server qua WebSocket, hãy dùng server.port=0, @SpringBootTest với RANDOM_PORT và @LocalServerPort để tạo URL WebSocket. Hai kiểu cổng có vòng đời khác nhau nên phải chọn đúng annotation và transport.

Hãy tạo builder mới khi cần setup độc lập, dispose requester sau test, đặt timeout, cô lập dữ liệu database và kiểm tra cả codec lẫn lifecycle. Những nguyên tắc này giúp integration test chạy ổn định trên máy phát triển và CI, đồng thời phát hiện lỗi mà unit test không thể nhìn thấy.

## Tài liệu tham khảo

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — RSocket Messaging](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot — LocalRSocketServerPort API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [Spring Boot — RSocketServerInitializedEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/rsocket/context/RSocketServerInitializedEvent.html)
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring — Getting Started with RSocket: Testing Spring Boot Responders](https://spring.io/blog/2020/05/25/getting-started-with-rsocket-testing-spring-boot-responders/)
