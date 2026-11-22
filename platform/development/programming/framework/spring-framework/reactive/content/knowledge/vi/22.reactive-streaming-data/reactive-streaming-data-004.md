# Media type text/event-stream, id, event và retry trong Spring WebFlux

## 1. Server-Sent Events dùng để làm gì?

**Server-Sent Events (SSE)** là cơ chế HTTP cho phép server gửi dữ liệu liên tục tới browser trên một kết nối response đang mở. Client mở một request GET; server trả media type **text/event-stream** rồi ghi các event khi chúng sẵn sàng. Browser có thể nhận từng event ngay khi được flush, không cần polling liên tục.

SSE phù hợp với:

- Tiến độ xử lý một tác vụ dài.
- Trạng thái đơn hàng hoặc quy trình đang chạy.
- Thông báo và cập nhật dashboard.
- Bảng giá, số liệu hoặc trạng thái hệ thống thay đổi theo thời gian.
- Log/notification một chiều từ server tới client.

SSE là giao tiếp **một chiều server → client**. Client vẫn gửi command, filter hoặc thao tác qua HTTP request riêng. Nếu cần giao tiếp hai chiều liên tục, hãy cân nhắc WebSocket hoặc một giao thức phù hợp khác.

Trong Spring WebFlux, một handler có thể trả **Flux<ServerSentEvent<T>>**. Framework dùng **ServerSentEventHttpMessageWriter** để encode từng event thành định dạng SSE và ghi theo reactive stream.

Một endpoint tối thiểu:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(sequence -> ServerSentEvent.builder(
                "update-" + sequence
            )
            .build());
}
~~~

Đây là snippet cần import Reactor, Spring WebFlux và Duration. Với mỗi phần tử của Flux, WebFlux ghi một event. Khi Flux chưa complete, response tiếp tục mở để gửi dữ liệu mới.

## 2. Media type text/event-stream và định dạng trên đường truyền

SSE dùng media type **text/event-stream** và nội dung được mã hóa UTF-8. Một event gồm các dòng field, kết thúc bằng một dòng trống. Dòng trống là dấu hiệu để client dispatch event.

Ví dụ:

~~~text
id: 42
event: progress
retry: 3000
data: {"percent":75,"message":"Đang xử lý"}

~~~

Ý nghĩa:

- **id**: mã nhận diện event, được browser ghi nhớ làm last event ID.
- **event**: tên event; client có thể đăng ký listener theo tên này.
- **retry**: thời gian chờ trước khi reconnect, tính bằng millisecond.
- **data**: payload của event. Payload có thể là text hoặc JSON được serialize.

Một event có thể chỉ chứa data:

~~~text
data: Xin chào

~~~

Khi không có field event, loại event mặc định phía browser là **message**.

Một event cũng có thể có nhiều dòng data:

~~~text
data: Dòng thứ nhất
data: Dòng thứ hai
data: Dòng thứ ba

~~~

Browser nối các dòng data bằng ký tự newline trước khi đưa nội dung vào event.data. Nếu data là JSON, hãy serialize thành một JSON document hợp lệ; client parse bằng JSON.parse.

### 2.1. Các field chuẩn

| Field | Mục đích | Ví dụ |
| --- | --- | --- |
| **data** | Nội dung event | data: {"status":"running"} |
| **event** | Tên loại event | event: progress |
| **id** | Event ID dùng khi reconnect | id: 105 |
| **retry** | Khoảng chờ reconnect, millisecond | retry: 3000 |
| **comment** | Dòng comment, không dispatch event | : heartbeat |

Tên field được viết đúng chữ thường như giao thức quy định. Field lạ bị client bỏ qua.

### 2.2. Blank line là ranh giới event

Mỗi event cần kết thúc bằng một dòng trống. Nếu server chỉ gửi các dòng data mà không có dòng trống, browser có thể chưa dispatch event đó. Vì vậy, khi tự tạo SSE bằng tay, phải kết thúc event đúng định dạng.

Khi dùng **ServerSentEvent** trong WebFlux, message writer chịu trách nhiệm serialize các field và delimiter. Không tự nối chuỗi SSE vào một String nếu không có lý do đặc biệt; dùng builder giúp tránh lỗi định dạng và hỗ trợ encode object.

### 2.3. Comment và heartbeat

Một dòng bắt đầu bằng dấu hai chấm là comment:

~~~text
: heartbeat

~~~

Browser bỏ qua comment, nên nó không tạo event message. Server có thể gửi comment định kỳ để giữ kết nối sống khi stream ít dữ liệu và tránh một số proxy/load balancer đóng kết nối nhàn rỗi.

Trong Spring:

~~~java
ServerSentEvent.<String>builder()
    .comment("heartbeat")
    .build();
~~~

Có thể ghép heartbeat vào stream bằng Flux theo lịch. Khoảng heartbeat phải ngắn hơn idle timeout của proxy/server trên đường truyền. Không gửi heartbeat quá dày vì sẽ tạo lưu lượng và công việc không cần thiết.

## 3. ServerSentEvent<T> trong Spring WebFlux

Spring cung cấp class **org.springframework.http.codec.ServerSentEvent<T>** để biểu diễn một SSE. Generic T là kiểu payload của field data.

Các thuộc tính chính:

- **id()**: mã event.
- **event()**: tên event.
- **retry()**: Duration được yêu cầu cho lần reconnect tiếp theo.
- **comment()**: comment/heartbeat.
- **data()**: payload.

Builder có thể tạo event với data ngay:

~~~java
ServerSentEvent<Progress> event =
    ServerSentEvent.<Progress>builder(
        new Progress(42, "running")
    )
    .id("42")
    .event("progress")
    .retry(Duration.ofSeconds(3))
    .build();
~~~

Hoặc tạo builder rồi gán từng field:

~~~java
ServerSentEvent<Progress> event =
    ServerSentEvent.<Progress>builder()
        .id("42")
        .event("progress")
        .retry(Duration.ofSeconds(3))
        .data(new Progress(42, "running"))
        .build();
~~~

Spring ghi retry theo millisecond. Ví dụ Duration 3 giây được serialize thành:

~~~text
retry:3000
~~~

Đừng nhầm kiểu Java **Duration** với giá trị wire format: API Spring nhận Duration, còn giao thức SSE truyền số nguyên millisecond.

### 3.1. ServerSentEventHttpMessageWriter

Khi handler trả Flux<ServerSentEvent<T>> và response dùng text/event-stream, Spring chọn **ServerSentEventHttpMessageWriter**. Writer xử lý:

1. Đặt/ghi media type phù hợp.
2. Serialize id, event, retry và comment.
3. Encode data bằng codec/message writer tương ứng.
4. Ghi từng event vào response.
5. Flush theo cách phù hợp với streaming response.

Nếu data là object Java và Jackson có mặt trong classpath, payload thường được serialize thành JSON. Nếu data là String, nội dung được ghi như text. Client phải biết schema của payload để parse đúng.

Không tự set Content-Length cho một stream có độ dài chưa biết. Không gom toàn bộ Flux thành List chỉ để trả SSE; làm vậy sẽ mất đặc tính streaming và trì hoãn việc gửi event cho client.

### 3.2. Có bắt buộc dùng ServerSentEvent không?

Không. WebFlux cũng có thể phát một Flux các object thông thường khi mapping khai báo text/event-stream:

~~~java
@GetMapping(
    value = "/messages",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<String> messages() {
    return Flux.just("one", "two", "three");
}
~~~

Trong trường hợp này, mỗi phần tử được ghi như một event chỉ có data. Dùng **ServerSentEvent<T>** khi cần id, event name, retry hoặc comment.

## 4. id: nhận diện event và tiếp tục stream

Field **id** là một chuỗi nhận diện event. Browser lưu ID gần nhất mà nó đã xử lý. Nếu kết nối bị ngắt và EventSource tự kết nối lại, browser gửi giá trị này trong request header **Last-Event-ID**.

Luồng cơ bản:

~~~text
Server gửi event id=101
          |
          v
Browser nhận và lưu last event ID = 101
          |
          v
Kết nối bị ngắt
          |
          v
EventSource tự reconnect
          |
          v
Request gửi Last-Event-ID: 101
          |
          v
Server đọc header và phát lại event sau 101
~~~

Ví dụ:

~~~text
id: 101
event: progress
data: {"percent":50}

id: 102
event: progress
data: {"percent":75}

~~~

Nếu connection rớt sau event 101, browser có thể reconnect với Last-Event-ID là 101. Server cần tìm event tiếp theo từ nguồn lịch sử để tiếp tục từ 102.

**id không tự lưu event trên server.** Nó chỉ là cursor do giao thức truyền. Muốn resume thực sự, ứng dụng cần event log, database, message broker hoặc một kho lưu trữ có thể truy vấn các event sau cursor đó.

### 4.1. Đọc Last-Event-ID trong WebFlux

Có thể nhận header trực tiếp:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Progress>> events(
    @RequestHeader(
        name = "Last-Event-ID",
        required = false
    ) String lastEventId
) {
    long lastSeen = lastEventId == null
        ? 0
        : Long.parseLong(lastEventId);

    return eventStore.findAfter(lastSeen)
        .map(this::toServerSentEvent);
}
~~~

Đây là snippet giả định eventStore trả Publisher các event có ID lớn hơn cursor. Nếu header có thể đến từ client không tin cậy, cần validate định dạng, giới hạn độ dài và xử lý ID không tồn tại hoặc quá cũ.

Không dùng số thứ tự từ 1 mỗi lần server restart nếu client có thể reconnect qua nhiều lần deploy. ID cần ổn định trong phạm vi retention của event store, ví dụ sequence từ database hoặc offset của message broker.

### 4.2. Event ID cần duy nhất và có thứ tự phù hợp

Một ID có thể là số tăng dần, offset, hoặc token có thể tra cứu. Điều quan trọng là server phải xác định được event nào đứng sau ID đó.

UUID có thể duy nhất nhưng không tự thể hiện thứ tự. Nếu dùng UUID, event store phải có index ánh xạ UUID sang vị trí. Với stream có thứ tự, sequence/offset thường thuận tiện hơn.

### 4.3. Không phát event trùng hoặc bỏ sót khi reconnect

Khi reconnect, server có thể phát lại event cuối đã nhận nếu client và server không đồng bộ hoàn toàn. Ứng dụng nên thiết kế consumer idempotent: xử lý lại cùng một event không làm nhân đôi side effect.

Một mô hình phổ biến:

- Event có ID ổn định.
- Client ghi nhận ID đã xử lý.
- Server truy vấn event sau Last-Event-ID.
- Client bỏ qua event đã xử lý nếu có overlap.
- Server giữ lịch sử đủ lâu cho cửa sổ reconnect đã cam kết.

SSE cung cấp cursor và reconnect; bảo đảm exactly-once là trách nhiệm của logic ứng dụng và kho sự kiện.

## 5. event: phân loại thông điệp

Field **event** đặt tên loại event. Nếu không có event, browser dispatch sự kiện mặc định là **message**.

Ví dụ:

~~~text
event: order-created
id: 501
data: {"orderId":"ORD-501","status":"created"}

event: order-shipped
id: 502
data: {"orderId":"ORD-501","status":"shipped"}

~~~

Browser đăng ký listener theo tên:

~~~javascript
const source = new EventSource("/api/orders/events");

source.addEventListener("order-created", (event) => {
    const payload = JSON.parse(event.data);
    console.log("Created:", payload.orderId);
});

source.addEventListener("order-shipped", (event) => {
    const payload = JSON.parse(event.data);
    console.log("Shipped:", payload.orderId);
});
~~~

Nếu server không gửi event field, dùng onmessage:

~~~javascript
source.onmessage = (event) => {
    console.log(event.data);
};
~~~

### 5.1. Đặt tên event theo contract

Tên event nên mô tả sự kiện nghiệp vụ hoặc loại cập nhật, ví dụ:

- progress
- completed
- failed
- order-updated
- notification
- heartbeat

Tránh dùng tên quá chung như update nếu client phải phân biệt nhiều luồng dữ liệu. Cũng không đưa dữ liệu nhạy cảm vào tên event; tên này là metadata được client nhìn thấy.

### 5.2. Phân biệt event name với data schema

event chỉ là nhãn phân loại. data chứa payload. Một event progress có thể mang phần trăm, task ID và timestamp; một event failed có thể mang mã lỗi và thông điệp đã được phép hiển thị.

Ví dụ:

~~~java
public record Progress(
    long sequence,
    int percent,
    String status
) {}

public record StreamFailure(
    String code,
    String message
) {}
~~~

Nên version hóa schema nếu client và server có thể được triển khai độc lập. Không đổi ý nghĩa field hiện có mà không có chính sách tương thích.

## 6. retry: thời gian reconnect

Field **retry** chỉ định thời gian client chờ trước khi thử kết nối lại sau khi stream bị ngắt. Giá trị trên đường truyền là số nguyên millisecond.

Ví dụ:

~~~text
retry:3000
~~~

Browser nhận giá trị này và cập nhật thời gian reconnect. Nếu field không phải số nguyên hợp lệ, client bỏ qua field đó và tiếp tục dùng giá trị reconnect trước đó hoặc mặc định của implementation.

Trong Spring:

~~~java
ServerSentEvent.builder("working")
    .event("progress")
    .retry(Duration.ofSeconds(5))
    .build();
~~~

Spring chuyển Duration thành số millisecond khi ghi SSE.

### 6.1. Chọn retry interval

- Retry ngắn giúp client phục hồi nhanh khi lỗi tạm thời.
- Retry dài giảm số lần reconnect khi server đang quá tải.
- Nếu nhiều client cùng mất kết nối, cùng retry một thời điểm có thể tạo reconnect storm.
- Có thể kết hợp jitter/backoff phía client hoặc phát retry interval phù hợp theo trạng thái server.

Không đặt retry quá thấp cho một dịch vụ có hàng chục nghìn kết nối. Tính tổng số reconnect có thể xảy ra khi server hoặc proxy phục hồi.

### 6.2. retry không phải retry của Reactor

Có hai khái niệm khác nhau:

- **SSE retry field**: hướng dẫn browser EventSource chờ bao lâu trước khi mở lại HTTP connection.
- **Reactor retryWhen/retry**: resubscribe Publisher ở phía server hoặc client code.

SSE retry không tự khởi động lại một Publisher đã lỗi ở server. Nó yêu cầu client mở một request HTTP mới. Server phải tạo pipeline mới và sử dụng Last-Event-ID/event store nếu cần resume.

### 6.3. Browser tự reconnect

EventSource của browser tự reconnect khi connection bị đóng theo điều kiện của giao thức. Có thể quan sát lỗi bằng onerror:

~~~javascript
source.onerror = (error) => {
    console.warn("SSE connection interrupted", error);
};
~~~

Không gọi **source.close()** nếu muốn giữ cơ chế reconnect mặc định. Gọi close() chuyển EventSource sang trạng thái đóng và dừng reconnect.

Không phải mọi HTTP response đều khiến browser tiếp tục retry. Response không hợp lệ hoặc status không được giao thức chấp nhận có thể làm kết nối đóng hẳn; hãy kiểm tra status và Content-Type ở server.

## 7. Controller WebFlux hoàn chỉnh cho SSE

Một controller có thể tạo event định kỳ:

~~~java
package com.example.sse;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class EventController {

    public record Progress(
        long sequence,
        int percent,
        String status
    ) {}

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Progress>> events(
        @RequestHeader(
            name = "Last-Event-ID",
            required = false
        ) String lastEventId
    ) {
        long lastSeen = lastEventId == null
            ? 0
            : Long.parseLong(lastEventId);

        return Flux.range(1, 5)
            .filter(sequence -> sequence > lastSeen)
            .delayElements(Duration.ofMillis(250))
            .map(sequence -> {
                Progress progress = new Progress(
                    sequence,
                    sequence * 20,
                    "processing"
                );

                return ServerSentEvent.<Progress>builder(progress)
                    .id(Long.toString(sequence))
                    .event("progress")
                    .retry(Duration.ofSeconds(3))
                    .build();
            });
    }
}
~~~

Đây là controller hoàn chỉnh trong ứng dụng WebFlux có Spring Boot. Nó phát năm event có ID từ 1 đến 5. Khi client reconnect với Last-Event-ID là 2, endpoint chỉ phát lại event 3, 4 và 5.

Nguồn trong ví dụ là Flux.range nên có lịch sử cố định để minh họa resume. Trong production, thay bằng event store hoặc message broker có cursor bền vững; không dùng một range mới bắt đầu từ 1 nếu dữ liệu sự kiện thay đổi qua thời gian.

### 7.1. Vì sao dùng Flux.delayElements?

Flux.interval hoặc delayElements giúp mô phỏng event đến theo thời gian. Publisher vẫn reactive và không cần tạo thread ngủ thủ công trong controller.

Không dùng Thread.sleep trong handler. Nó chặn thread đang xử lý request và có thể làm giảm khả năng phục vụ nhiều kết nối đồng thời.

### 7.2. Phát heartbeat

Nếu stream có thể im lặng lâu, có thể phát comment định kỳ:

~~~java
ServerSentEvent.<Progress>builder()
    .comment("heartbeat")
    .build();
~~~

Một cách triển khai đầy đủ cần ghép heartbeat với event nghiệp vụ và giữ thứ tự. Không phát heartbeat quá dày; đặt chu kỳ dựa trên idle timeout của proxy/load balancer và tải hệ thống.

## 8. Browser client bằng EventSource

Ví dụ JavaScript:

~~~javascript
const source = new EventSource("/api/events");

source.addEventListener("progress", (event) => {
    const progress = JSON.parse(event.data);
    console.log(
        progress.sequence,
        progress.percent,
        progress.status
    );
});

source.onerror = (error) => {
    console.warn("Connection interrupted", error);
};

// Khi người dùng rời màn hình hoặc không cần stream nữa:
function stopEvents() {
    source.close();
}
~~~

Browser tự gửi request GET và giữ kết nối mở. Khi server gửi event có id, EventSource lưu last event ID. Nếu connection bị ngắt và reconnect, browser gửi Last-Event-ID trong request mới.

### 8.1. EventSource không cung cấp API tùy ý cho request headers

Native EventSource không có tùy chọn đặt header Authorization tùy ý. Nếu cần xác thực, thường dùng:

- Cookie session an toàn với SameSite/Secure/HttpOnly phù hợp.
- Cơ chế token ngắn hạn trong URL khi threat model cho phép và tránh log token.
- Một SSE client dựa trên fetch khi cần custom headers và kiểm soát reconnect.

Không đưa access token dài hạn vào query string nếu URL có thể xuất hiện trong access log, history hoặc telemetry.

### 8.2. CORS và credentials

Nếu browser kết nối khác origin, cần cấu hình CORS đúng origin. Nếu dùng cookie credentials, client có thể tạo EventSource với tùy chọn withCredentials:

~~~javascript
const source = new EventSource(
    "https://api.example.com/events",
    { withCredentials: true }
);
~~~

Server phải trả CORS headers tương thích với credentials; không kết hợp wildcard origin với credentialed request. Kiểm tra chính sách cookie và SameSite khi triển khai qua nhiều domain.

## 9. Kiểm thử SSE bằng WebTestClient

SSE là stream, nên test phải đọc body và kiểm tra từng event, không chỉ kiểm tra status 200.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class EventControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void emitsEventsWithIdEventAndRetry() {
        FluxExchangeResult<ServerSentEvent<EventController.Progress>>
            result = client.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM
                    )
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<EventController.Progress>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "1".equals(event.id())
                    && "progress".equals(event.event())
                    && event.retry().equals(Duration.ofSeconds(3))
                    && event.data().percent() == 20
            )
            .expectNextMatches(event ->
                "2".equals(event.id())
                    && event.data().percent() == 40
            )
            .thenCancel()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void resumesAfterLastEventId() {
        FluxExchangeResult<ServerSentEvent<EventController.Progress>>
            result = client.get()
                .uri("/api/events")
                .header("Last-Event-ID", "2")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<EventController.Progress>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event -> "3".equals(event.id()))
            .expectNextMatches(event -> "4".equals(event.id()))
            .expectNextMatches(event -> "5".equals(event.id()))
            .verifyComplete();
    }
}
~~~

Đây là test snippet cần import JUnit, WebTestClient, ServerSentEvent, ParameterizedTypeReference, FluxExchangeResult, StepVerifier và Duration. Test đầu đọc hai event rồi cancel để không phải đợi hết stream. Test thứ hai kiểm tra cursor Last-Event-ID.

### 9.1. Test reconnect thật

WebTestClient gửi header Last-Event-ID để mô phỏng request reconnect. Nó không tự mô phỏng toàn bộ state machine của browser EventSource. Muốn kiểm tra browser tự reconnect, cần integration/e2e test bằng browser hoặc một client SSE thực tế.

Test reconnect cần xác minh:

- Event ID cuối được ghi nhận đúng.
- Request mới gửi Last-Event-ID.
- Server replay từ event tiếp theo.
- Event cũ được xử lý idempotent nếu có overlap.
- Event đã hết retention được xử lý theo chính sách resync.

## 10. Cấu hình dự án Java 17+ để chạy ví dụ

Ví dụ dùng **Spring Boot 3.3.5**, Spring Framework 6.1.x và Java 17.

Cấu trúc:

~~~text
webflux-sse-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/sse/
    │   │       ├── SseApplication.java
    │   │       └── EventController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/sse/
                └── EventControllerTest.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-sse-demo</artifactId>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
~~~

Tệp **SseApplication.java**:

~~~java
package com.example.sse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SseApplication {

    public static void main(String[] args) {
        SpringApplication.run(SseApplication.class, args);
    }
}
~~~

Tệp **application.properties**:

~~~properties
spring.application.name=webflux-sse-demo
server.port=8080
logging.level.com.example.sse=INFO
~~~

Đưa EventController ở phần 7 và EventControllerTest ở phần 9 vào đúng package. Với test Spring Boot, có thể dùng @SpringBootTest(webEnvironment = RANDOM_PORT) để kiểm tra qua server thực; khi đó thêm thuộc tính webEnvironment vào annotation.

### 10.1. Chạy và quan sát stream

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Mở terminal khác:

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/events
~~~

Curl có thể hiển thị các event dạng:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

id:1
event:progress
retry:3000
data:{"sequence":1,"percent":20,"status":"processing"}

id:2
event:progress
retry:3000
data:{"sequence":2,"percent":40,"status":"processing"}

id:3
event:progress
retry:3000
data:{"sequence":3,"percent":60,"status":"processing"}
~~~

Đây là định dạng nội dung dự kiến; header phụ, thứ tự field và khoảng trắng có thể khác theo server/writer. Event ID, event type, retry và data mới là các giá trị cần xác minh.

Mô phỏng reconnect từ event 2:

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  -H "Last-Event-ID: 2" \
  http://localhost:8080/api/events
~~~

Server chỉ phát event có ID 3, 4 và 5. Đây là cách kiểm tra logic resume ở phía server; browser EventSource sẽ tự gửi header Last-Event-ID khi reconnect theo giao thức.

Dừng ứng dụng bằng Ctrl+C.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client nhận một JSON array sau khi đợi lâu | Endpoint trả Flux với media type application/json | Khai báo produces = text/event-stream |
| Browser không dispatch event | Thiếu dòng trống kết thúc event hoặc stream chưa flush | Dùng ServerSentEvent writer và kiểm tra response streaming |
| onmessage không chạy | Server đặt event name riêng | Dùng addEventListener với đúng tên event |
| JSON.parse thất bại | data không phải JSON hoặc payload được encode khác dự kiến | Kiểm tra schema và codec của data |
| Browser không reconnect đúng thời gian | retry không phải số nguyên millisecond hợp lệ | Dùng ServerSentEvent.Builder.retry(Duration) |
| Reconnect nhưng nhận lại từ đầu | Server bỏ qua Last-Event-ID | Đọc header và truy vấn event sau cursor |
| Reconnect bị mất event | Event ID không ổn định hoặc event store không đủ retention | Dùng sequence/offset bền vững và retention phù hợp |
| Client xử lý trùng event | Server replay có overlap | Thiết kế consumer idempotent theo event ID |
| Kết nối bị proxy đóng khi stream im lặng | Idle timeout ở proxy/load balancer | Gửi comment heartbeat định kỳ |
| CPU/tài nguyên tăng vì quá nhiều kết nối | Mỗi client giữ một stream dài | Giới hạn kết nối, timeout, backpressure và theo dõi metrics |
| Server vẫn tạo dữ liệu sau khi client đóng | Nguồn không phản ứng cancellation hoặc có subscribe thủ công | Compose Publisher và cleanup khi cancel |
| Không gửi được Authorization header bằng EventSource | Native EventSource không hỗ trợ header tùy ý | Dùng cookie phù hợp hoặc fetch-based SSE client |
| Test chỉ xác nhận 200 OK | Chưa tiêu thụ response stream | Dùng WebTestClient và StepVerifier kiểm tra event |
| Gọi close() rồi chờ tự reconnect | close() đóng EventSource vĩnh viễn | Tạo EventSource mới nếu muốn mở lại |
| Dùng retry SSE như retryWhen của Reactor | Nhầm retry phía browser với resubscribe phía server | Xử lý hai cơ chế ở đúng phía |
| Dùng UUID nhưng server không tìm được event tiếp theo | ID không có thứ tự/index tra cứu | Lưu mapping hoặc dùng sequence/offset |

## 12. Bảo mật và vận hành SSE

SSE giữ kết nối HTTP mở trong thời gian dài. Mỗi stream cần được quản lý như một tài nguyên có vòng đời.

- **Authentication/authorization:** xác thực trước khi mở stream và kiểm tra user chỉ nhận event được phép.
- **CORS:** cấu hình origin rõ ràng, đặc biệt khi dùng cookie credentials.
- **Heartbeat:** giữ kết nối sống nhưng không tạo traffic quá dày.
- **Timeout:** đồng bộ idle timeout giữa server, reverse proxy và load balancer.
- **Backpressure:** tránh tạo hàng đợi event vô hạn cho client chậm; có chính sách drop, buffer giới hạn hoặc disconnect.
- **Cancellation:** khi client đóng kết nối, hủy subscription và giải phóng tài nguyên.
- **Retention:** giữ event đủ lâu cho cửa sổ reconnect đã cam kết.
- **Rate limit:** giới hạn số stream theo user/tenant/IP để bảo vệ server.
- **Observability:** theo dõi số kết nối mở, event rate, reconnect, lag, lỗi và cancellation.
- **Data privacy:** không gửi thông tin nhạy cảm trong event ID, URL, event name hoặc payload không cần thiết.

Không dùng SSE làm kho lưu trữ sự kiện. SSE chỉ là kênh truyền; dữ liệu cần replay phải nằm trong event store hoặc hệ thống lưu trữ có chính sách retention.

## 13. Checklist thiết kế SSE endpoint

Trước khi triển khai, hãy xác nhận:

1. Endpoint khai báo đúng text/event-stream?
2. Publisher có phát từng event thay vì gom toàn bộ dữ liệu?
3. Event có id ổn định khi cần resume?
4. Event name có rõ ràng và tương thích client?
5. retry có giá trị millisecond hợp lý?
6. Last-Event-ID được đọc và validate?
7. Server có nguồn replay bền vững nếu yêu cầu resume?
8. Event consumer có idempotent khi replay?
9. Có heartbeat phù hợp với proxy timeout?
10. Có cancellation và cleanup khi client disconnect?
11. Có giới hạn queue/buffer cho client chậm?
12. CORS và authentication đã đúng?
13. Browser client có xử lý onerror, named event và close()?
14. Test kiểm tra nội dung từng event, retry, ID và reconnect?
15. Metrics theo dõi kết nối, reconnect, lag và lỗi?

## 14. Bài tập thực hành

**Bài 1 — Event cơ bản:** Tạo Flux<String> và trả về text/event-stream. Dùng curl -N để quan sát từng event.

**Bài 2 — ServerSentEvent:** Chuyển sang Flux<ServerSentEvent<Progress>>. Đặt id, event và data cho từng phần tử.

**Bài 3 — Retry:** Dùng retry(Duration.ofSeconds(5)). Quan sát dòng retry trên wire và giải thích vì sao giá trị là 5000.

**Bài 4 — Named event:** Phát event progress và completed. Viết browser client dùng addEventListener cho từng loại.

**Bài 5 — Last-Event-ID:** Đọc header Last-Event-ID, bỏ qua các event cũ và chỉ phát event có ID lớn hơn cursor.

**Bài 6 — Event store:** Thay Flux.range bằng danh sách event lưu trong database hoặc message broker. Thiết kế retention và cách xử lý cursor đã hết hạn.

**Bài 7 — Heartbeat:** Phát comment heartbeat định kỳ. Mô phỏng proxy idle timeout và chọn chu kỳ phù hợp.

**Bài 8 — Cancellation:** Mở stream rồi đóng browser/curl. Quan sát doFinally nhận CANCEL và xác nhận nguồn được cleanup.

**Bài 9 — Slow consumer:** Mô phỏng client đọc chậm. Giới hạn queue và quyết định khi nào drop event hoặc disconnect.

**Bài 10 — WebTestClient:** Kiểm tra content type, event ID, event name, retry, data và reconnect từ Last-Event-ID.

**Bài 11 — Browser reconnect:** Dùng EventSource trong browser, chủ động ngắt kết nối server rồi xác minh request reconnect có Last-Event-ID.

**Bài 12 — Security:** Bảo vệ stream theo user. Xác minh user A không nhận event của user B và reconnect vẫn giữ đúng quyền.

## 15. Ghi nhớ

**text/event-stream** là media type cho một luồng event UTF-8, mỗi event kết thúc bằng dòng trống. Trong Spring WebFlux, dùng **Flux<ServerSentEvent<T>>** khi cần điều khiển metadata của event.

- **id** cho browser biết event cursor để gửi lại qua Last-Event-ID khi reconnect.
- **event** đặt tên loại thông điệp để client đăng ký listener.
- **retry** hướng dẫn thời gian chờ reconnect theo millisecond.
- **comment** có thể dùng làm heartbeat.
- **data** mang payload text hoặc JSON.

EventSource tự reconnect theo giao thức; server phải đọc Last-Event-ID và có event store nếu cần replay. Retry field không thay thế retryWhen của Reactor. Hãy thiết kế schema event, cancellation, retention, authorization và backpressure trước khi đưa SSE vào production.

## 16. Tài liệu tham khảo

- Spring Framework Reference — WebFlux Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework API — ServerSentEvent (6.1): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/codec/ServerSentEvent.html
- Spring Framework API — ServerSentEventHttpMessageWriter: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/codec/ServerSentEventHttpMessageWriter.html
- Spring Framework API — WebTestClient: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- WHATWG HTML Standard — Server-sent events: https://html.spec.whatwg.org/multipage/server-sent-events.html
- MDN — Using server-sent events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- MDN — EventSource: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
