# Backpressure và truyền nội dung HTTP theo luồng

## 1. Vấn đề: dữ liệu đến nhanh hơn tốc độ xử lý

Một API Gateway phải nhận request từ client, áp dụng route predicate và filter chain, rồi chuyển tiếp tới microservice phù hợp. Với response JSON nhỏ, toàn bộ dữ liệu có thể được tạo và gửi rất nhanh. Nhưng nếu client tải một tệp nhiều gigabyte, theo dõi sự kiện thời gian thực hoặc nhận kết quả truy vấn dài, cách xử lý **gom toàn bộ nội dung vào bộ nhớ rồi mới gửi** tạo ra ba vấn đề:

- **Bộ nhớ:** một request lớn hoặc nhiều request đồng thời có thể chiếm lượng RAM vượt khả năng của gateway.
- **Độ trễ:** client phải đợi toàn bộ nội dung được tạo xong mới nhận được byte đầu tiên.
- **Chênh lệch tốc độ:** backend có thể phát dữ liệu nhanh hơn tốc độ mạng hoặc tốc độ tiêu thụ của client, khiến hàng đợi tăng liên tục.

**Streaming** cho phép dữ liệu được tạo, xử lý và truyền dần theo các phần. **Backpressure** là cơ chế để phía nhận trong một luồng xử lý bất đồng bộ thể hiện lượng dữ liệu nó sẵn sàng nhận, từ đó điều tiết phía phát. Trong **Spring WebFlux**, mô hình này dựa trên Reactor và đặc tả Reactive Streams. Trong **Spring Cloud Gateway Server WebFlux**, request/response body có thể được đại diện bằng luồng **Flux<DataBuffer>** và được chuyển tiếp qua hạ tầng reactive.

Hai khái niệm liên quan nhưng **không đồng nghĩa**: một HTTP response có thể được gửi theo luồng nhưng một tầng trung gian vẫn đệm dữ liệu quá nhiều; ngược lại, một chuỗi Reactor có backpressure vẫn có thể bị một phép toán **collectList()** gom hết dữ liệu trước khi ghi HTTP response.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích tín hiệu **request(n)**, **cancel** và giới hạn của backpressure trong Reactive Streams.
2. Phân biệt streaming ở cấp ứng dụng, HTTP và giao thức truyền tải; nhận ra nơi có thể phát sinh bộ đệm.
3. Đọc và thiết kế đường đi của **Flux<DataBuffer>** qua Spring WebFlux và Spring Cloud Gateway.
4. Triển khai ví dụ SSE, NDJSON, upload/download theo luồng và cấu hình route để proxy chúng.
5. Tránh vô tình gom toàn bộ body khi xây filter; xử lý vòng đời **DataBuffer**, timeout, lỗi giữa luồng và quan sát hiệu năng.

## 2. Cơ chế backpressure của Reactive Streams

Reactive Streams có bốn vai trò cơ bản:

| Thành phần | Vai trò |
| --- | --- |
| **Publisher&lt;T&gt;** | Nguồn phát dữ liệu bất đồng bộ |
| **Subscriber&lt;T&gt;** | Bên nhận dữ liệu, lỗi và tín hiệu hoàn tất |
| **Subscription** | Liên kết giữa publisher và subscriber; cho phép yêu cầu thêm dữ liệu hoặc hủy |
| **Processor&lt;T, R&gt;** | Kết hợp vai trò nhận và phát, có thể biến đổi dữ liệu |

Khi một subscriber đăng ký, nó nhận một **Subscription** qua **onSubscribe**. Subscriber gọi **request(n)** với số lượng dương để thông báo nhu cầu. Publisher không được phát vượt số lượng phần tử đã được yêu cầu qua **onNext** đối với subscription đó. Khi không cần dữ liệu nữa, subscriber có thể gọi **cancel()**.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Subscriber
    S->>P: subscribe()
    P->>S: onSubscribe(subscription)
    S->>P: request(2)
    P-->>S: onNext(item 1)
    P-->>S: onNext(item 2)
    S->>P: request(1)
    P-->>S: onNext(item 3)
    P-->>S: onComplete()
~~~

Trong Reactor, **Flux&lt;T&gt;** đại diện cho 0..N phần tử và **Mono&lt;T&gt;** đại diện cho 0..1 phần tử. Nhiều phép biến đổi như **map**, **filter**, **flatMap**, **limitRate** hoặc **publishOn** truyền hoặc điều chỉnh nhu cầu giữa các tầng. Khi dùng **flatMap**, cần nhớ rằng operator có thể đồng thời đăng ký nhiều nguồn con và có bộ đệm nội bộ; số phần tử đã được downstream yêu cầu không nhất thiết trùng 1:1 với số phần tử mà mọi nguồn upstream đã được yêu cầu ngay tại thời điểm quan sát.

### Ví dụ điều tiết số lượng phần tử

~~~java
Flux<Integer> numbers = Flux.range(1, 1000);

numbers.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(2);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Received: " + value);
        request(1);
    }
});
~~~

Đoạn mã minh họa cách subscriber yêu cầu trước hai phần tử rồi yêu cầu thêm từng phần tử. Một số chi tiết cần nhớ:

- **request(n)** là số **phần tử trong luồng**, không phải số byte, số gói TCP hay số HTTP request.
- Không nên dùng **Thread.sleep()** trong một callback reactive chạy trên event-loop để mô phỏng client chậm; thao tác blocking đó làm nghẽn luồng xử lý.
- Đặc tả quy định backpressure tại ranh giới publisher/subscriber; nó **không bảo đảm** mọi hệ thống phát sự kiện, socket hoặc proxy bên ngoài đều tuân thủ cùng cơ chế.
- **cancel()** có thể dừng các publisher hợp tác với việc hủy, nhưng một tác vụ đã được gửi đi hoặc hệ thống bên ngoài không nhất thiết dừng tức thì.

## 3. Backpressure và HTTP streaming: hai lớp cơ chế khác nhau

Có ít nhất ba lớp cần phân biệt:

1. **Lớp ứng dụng/reactive:** Reactor truyền tín hiệu demand, xử lý từng phần tử và hủy subscription khi cần.
2. **Lớp HTTP:** body được truyền dưới dạng chuỗi byte qua một hoặc nhiều lần ghi; HTTP/1.1 có thể dùng **chunked transfer encoding** khi chưa biết trước độ dài, còn HTTP/2 truyền dữ liệu qua các **DATA frame** và cơ chế flow control riêng.
3. **Lớp transport:** TCP có cơ chế flow control và các bộ đệm socket. Tốc độ đọc/ghi socket ảnh hưởng đến hạ tầng HTTP, nhưng không phải cùng một API với **Subscription.request(n)**.

~~~mermaid
flowchart LR
    S[Service Publisher] -->|Flux of DataBuffer| G[Gateway]
    G -->|HTTP response bytes| C[Client]
    C -.->|Network flow control / readiness| G
    G -.->|Reactive demand / cancellation| S
~~~

WebFlux và Reactor Netty có thể phối hợp khả năng ghi/đọc bất đồng bộ với demand để tránh lưu quá nhiều dữ liệu. Tuy nhiên, **không có bảo đảm chung rằng một phần tử Flux tương ứng với một HTTP chunk, một TCP packet hoặc một lần gọi hàm ở client**. Codec, HTTP framing, proxy, TLS, nén, buffering và tốc độ client đều có thể thay đổi cách dữ liệu đến nơi.

**Ví dụ:** Backend trả từng bản ghi 1 KB, gateway xử lý bất đồng bộ và client đọc chậm. Nếu các tầng trung gian không gom body, lượng dữ liệu cần giữ ở mỗi tầng có thể được khống chế tốt hơn so với việc tải toàn bộ response về RAM. Nếu một filter gọi **DataBufferUtils.join(...)** trên cả body, lợi thế này không còn tại filter đó.

### Streaming cải thiện những gì?

| Khía cạnh | Gom toàn bộ trước khi trả | Trả theo luồng |
| --- | --- | --- |
| Thời điểm nhận dữ liệu đầu tiên | Sau khi có toàn bộ kết quả | Có thể ngay sau khi phần đầu sẵn sàng |
| Bộ nhớ cho body | Có thể tăng theo kích thước toàn bộ body | Có thể gần với lượng dữ liệu đang xử lý/buffer nếu đường đi thực sự streaming |
| Cách xử lý phía client | Đợi một payload hoàn chỉnh | Nhận, giải mã và xử lý dần |
| Lỗi giữa quá trình trả | Thường còn có thể chọn HTTP status trước khi gửi | Sau khi header đã gửi, không thể đổi status đã commit |
| Mức độ phức tạp | Dễ xác thực payload một lần | Cần quan tâm framing, ngắt kết nối, timeout, partial result |

Streaming không mặc nhiên giúp một truy vấn chậm tạo được phần tử đầu tiên sớm: nguồn dữ liệu phải hỗ trợ phát kết quả dần thì lợi ích về độ trễ mới rõ.

## 4. Hình thức truyền nội dung HTTP theo luồng

Không phải loại streaming nào cũng có cùng contract:

| Kiểu | Content-Type điển hình | Đặc điểm | Trường hợp sử dụng |
| --- | --- | --- | --- |
| **Raw bytes** | application/octet-stream | Chuỗi byte liên tục, ứng dụng tự hiểu định dạng | Tải tệp, truyền dữ liệu nhị phân |
| **NDJSON** | application/x-ndjson | Mỗi dòng là một JSON value độc lập; ngăn cách bằng newline | Kết quả truy vấn, danh sách bản ghi lớn |
| **Server-Sent Events (SSE)** | text/event-stream | Server đẩy các sự kiện dạng text/event, kết nối HTTP dài | Thông báo, tiến độ, trạng thái thời gian thực |
| **Multipart upload** | multipart/form-data | Nhiều part có header riêng; framework có thể dùng bộ đệm hoặc tệp tạm | Upload tệp cùng metadata |
| **WebSocket** | Nâng cấp/chuyển giao giao thức WebSocket | Giao tiếp hai chiều, framing và cơ chế riêng | Chat, điều khiển thời gian thực hai chiều |

**NDJSON** và **SSE** giữ một HTTP response mở, cho phép tiêu thụ từng đơn vị logic mà không chờ toàn bộ danh sách. **SSE** chỉ truyền sự kiện từ server tới client trên một kết nối HTTP; chiều gửi ngược lại dùng HTTP request riêng. **WebSocket** có mô hình hai chiều khác, nên không nên đồng nhất với streaming body HTTP thông thường.

Trong HTTP/1.1, khi một response được gửi dần và không có độ dài biết trước, server thường dùng **Transfer-Encoding: chunked**. Đối với HTTP/2, header **Transfer-Encoding: chunked** không được dùng; dữ liệu được đóng vào các frame HTTP/2. **Ranh giới giữa các chunk/frame không phải ranh giới bản ghi**. Với NDJSON, client dựa vào dấu xuống dòng; với SSE, client dựa vào định dạng sự kiện, không dựa vào kích thước một lần đọc socket.

### Minh họa dữ liệu NDJSON

~~~text
{"id":1,"name":"A"}
{"id":2,"name":"B"}
{"id":3,"name":"C"}
~~~

Mỗi dòng phải là một JSON value hợp lệ và độc lập. Không thêm dấu phẩy hoặc dấu ngoặc vuông như một JSON array thông thường. Client có thể parse từng dòng khi nhận đủ ký tự xuống dòng.

### Minh họa SSE

~~~text
id: 101
event: order-status
data: {"orderId":"O-42","status":"PAID"}

id: 102
event: order-status
data: {"orderId":"O-42","status":"PACKING"}

~~~

Mỗi sự kiện SSE kết thúc bởi một dòng trống. Trình duyệt có thể sử dụng **EventSource** để nhận các sự kiện. Nếu cần khôi phục sau mất kết nối, thiết kế backend phải hỗ trợ **ID sự kiện**, lưu lịch sử thích hợp và diễn giải **Last-Event-ID**; chỉ thêm trường **id** không tự tạo khả năng phát lại đáng tin cậy.

## 5. Body được xử lý như thế nào trong Spring WebFlux?

Với **Spring WebFlux**, API quan trọng nhất để hiểu streaming HTTP ở mức thấp là **ServerHttpRequest.getBody()** trả về **Flux&lt;DataBuffer&gt;**. **ServerHttpResponse.writeWith(Publisher&lt;? extends DataBuffer&gt;)** cho phép ghi dần các buffer ra response. Spring dùng codec để giải mã/ghi các kiểu dữ liệu cấp cao hơn như DTO JSON, SSE hoặc chuỗi.

~~~mermaid
flowchart LR
    IN[Request network bytes] --> R[Reactor Netty HTTP server]
    R --> F[Flux of DataBuffer]
    F --> C[WebFlux Handler / Filter]
    C --> B[Service or upstream call]
    B --> O[Publisher of response DataBuffer]
    O --> W[HTTP response writer]
    W --> OUT[Client]
~~~

**DataBuffer** là biểu diễn vùng bộ nhớ chứa byte. Trong cấu hình dùng Reactor Netty, buffer thường liên quan đến bộ nhớ được quản lý bằng **reference counting** của Netty. Vì vậy:

- Khi bạn chỉ **chuyển tiếp** DataBuffer qua chuỗi xử lý và không giữ lại, nên để framework quản lý vòng đời thông thường.
- Nếu tự giữ, biến đổi, loại bỏ hoặc tiêu thụ DataBuffer, bạn phải tuân thủ quy tắc **retain/release** tương ứng; tránh đọc rồi bỏ buffer mà không giải phóng.
- Không dùng **subscribe()** thủ công bên trong filter để “đọc thử” body. Subscription này có thể tiêu thụ luồng một lần, gây race, xử lý trùng hoặc làm request phía sau không còn body.
- Không giả định body có thể đọc lại nhiều lần; nếu phải đọc và thay đổi body, cần cơ chế cache/decorator được thiết kế đúng, đồng thời tính chi phí bộ nhớ và kích thước tối đa.
- Không giữ tham chiếu DataBuffer sau khi publisher đã chuyển quyền sở hữu hoặc buffer đã release.

Một quy tắc thực hành hữu ích: **chọn giải pháp ở cấp codec/controller khi có thể; chỉ xử lý DataBuffer trực tiếp khi thật sự cần thao tác trên byte**.

## 6. Spring Cloud Gateway proxy HTTP streaming

Trong **Spring Cloud Gateway Server WebFlux**, route được chọn dựa trên predicate; các gateway filter và global filter tham gia xử lý request/response. Ở triển khai nền trên Reactor Netty, các thành phần như **NettyRoutingFilter** thực hiện request tới upstream HTTP và **NettyWriteResponseFilter** tham gia ghi response trở lại client. Một đường đi **không buộc phải gom toàn bộ body** mới có thể proxy dữ liệu.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Spring Cloud Gateway
    participant Upstream as Streaming service
    Client->>Gateway: GET /api/stream/events
    Gateway->>Gateway: Path predicate / filter chain
    Gateway->>Upstream: GET /stream/events
    Upstream-->>Gateway: Headers + event 1
    Gateway-->>Client: Headers + event 1
    Upstream-->>Gateway: event 2
    Gateway-->>Client: event 2
    Note over Client,Upstream: Có thể tiếp tục nhiều sự kiện trên cùng response
    Client-xGateway: Client ngắt kết nối
    Gateway-xUpstream: Hủy/đóng upstream khi việc hủy được lan truyền
~~~

Một route minh họa trong Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: streaming-service
              uri: lb://notification-service
              predicates:
                - Path=/api/stream/**
              filters:
                - StripPrefix=1
~~~

Theo ví dụ này, request **GET /api/stream/events** được chuyển thành **GET /stream/events** tại service. **lb://notification-service** sử dụng cơ chế tìm instance/cân bằng tải được cấu hình cho hệ thống, chẳng hạn qua Spring Cloud LoadBalancer và một nguồn service discovery. Nếu chạy thử mà chưa dùng discovery, có thể thay **uri** bằng địa chỉ service cụ thể như **http://localhost:8081**.

**Lưu ý phiên bản:** Cấu trúc thuộc tính cấu hình của Spring Cloud Gateway Server WebFlux khác nhau theo thế hệ; một số phiên bản sử dụng **spring.cloud.gateway.routes** thay cho **spring.cloud.gateway.server.webflux.routes**. Cần tra cấu hình của **đúng phiên bản Spring Cloud Gateway** đang chạy. Spring Cloud Gateway Server Web MVC cũng có API/cấu hình riêng; bài này tập trung vào **Server WebFlux**.

### Filter nào dễ làm mất streaming?

Một route đơn giản với **Path** và **StripPrefix** thường không cần đọc toàn bộ body. Nhưng các yêu cầu như **ký lại toàn bộ payload**, **giải mã toàn bộ JSON để viết lại**, **lưu toàn bộ response để cache**, hoặc **đọc body thành String để log** có thể cần tổng hợp dữ liệu và phá vỡ khả năng truyền dần.

Ví dụ về phép toán phải cân nhắc:

~~~java
// Minh họa điểm rủi ro: gom toàn bộ các buffer để có một body hợp nhất.
Mono<DataBuffer> aggregated = DataBufferUtils.join(request.getBody());
~~~

**DataBufferUtils.join(...)** tạo một kết quả chỉ có sau khi luồng hoàn thành, hoặc sau khi đạt giới hạn/điều kiện lỗi. Một body rất lớn hoặc vô hạn không phù hợp với cách xử lý này. Có overload hỗ trợ giới hạn **maxByteCount**, nhưng đặt giới hạn chỉ giúp chặn việc tiêu thụ quá lớn; nó **không chuyển phép tổng hợp thành streaming**. Khi tự thao tác với DataBuffer, cần quản lý release theo hợp đồng API và con đường xử lý thực tế.

Các filter biến đổi body như **ModifyRequestBody** / **ModifyResponseBody** cần được đánh giá riêng: tùy loại dữ liệu, codec và triển khai, chúng có thể decode body thành đối tượng/đoạn dữ liệu trước khi ghi lại. **Không coi mọi filter là streaming chỉ vì Gateway dùng WebFlux.**

## 7. Thực hành: SSE và NDJSON qua Gateway

Ví dụ dưới đây mô phỏng một service gửi sự kiện và danh sách bản ghi. Controller dùng Spring WebFlux với Reactor:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/stream")
class StreamingDemoController {

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .take(5)
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .event("tick")
                        .data("event-" + i)
                        .build());
    }

    @GetMapping(value = "/records", produces = "application/x-ndjson")
    Flux<Map<String, Object>> records() {
        return Flux.range(1, 5)
                .delayElements(Duration.ofMillis(400))
                .map(i -> Map.of("id", i, "name", "item-" + i));
    }
}
~~~

Endpoint **/stream/events** trả năm sự kiện SSE theo từng giây; endpoint **/stream/records** trả năm JSON object theo thời gian. Mỗi object NDJSON được phân cách bằng newline bởi encoder phù hợp với kiểu media của response. Đây là nguồn dữ liệu giả lập để quan sát thời điểm từng phần được gửi; trong hệ thống thật, thay chúng bằng luồng sự kiện hoặc truy vấn **có khả năng phát dần**. Nguồn theo đồng hồ như **Flux.interval** cũng có đặc điểm riêng khi downstream quá chậm; không nên dùng nó làm hàng đợi sự kiện đảm bảo không mất dữ liệu.

Với route ở phần trước, kiểm tra:

~~~bash
curl -i -N http://localhost:8080/api/stream/events
curl -i -N -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/stream/records
~~~

Tham số **-N** (hay **--no-buffer**) yêu cầu curl không tự đệm output khi hiển thị; nó không thay đổi tất cả các bộ đệm có thể tồn tại ở server/gateway/proxy. So sánh thời điểm từng dòng/sự kiện xuất hiện. Nếu dữ liệu chỉ xuất hiện dồn một lần ở cuối, cần lần lượt kiểm tra nguồn, codec, filter, gateway và các proxy phía trước.

### Lưu ý khi truy cập từ trình duyệt

JavaScript có thể dùng **EventSource** cho SSE:

~~~javascript
const events = new EventSource("/api/stream/events");

events.addEventListener("tick", (event) => {
  console.log("Event:", event.data, "ID:", event.lastEventId);
});

events.onerror = () => {
  console.warn("SSE disconnected or reconnecting");
};
~~~

Vì endpoint ví dụ chỉ gửi năm sự kiện rồi đóng kết nối, **EventSource** có thể thử kết nối lại theo hành vi của trình duyệt. Trong môi trường thật, cần xác định rõ có cho reconnect hay không, thời gian retry, cách phát lại và chính sách xác thực. SSE sử dụng HTTP nên các vấn đề như **CORS**, session/cookie, token và timeout vẫn phải được xử lý.

## 8. Truyền request body và upload theo luồng

Streaming không chỉ dành cho response. Request cũng có thể là một luồng byte, ví dụ client upload một tệp video tới backend qua gateway.

~~~mermaid
flowchart LR
    U[Uploader] -->|Request body: nhiều phần| G[Gateway]
    G -->|Chuyển tiếp các DataBuffer| F[File service]
    F --> D[(Storage)]
~~~

Đối với WebFlux, request body ở mức thấp là **Flux&lt;DataBuffer&gt;**. Nếu code xử lý upload tự gọi **collectList()**, **join()** không giới hạn hoặc **bodyToMono(byte[].class)**, có nguy cơ giữ toàn bộ nội dung trong RAM. Tương tự, việc log toàn bộ request body tại gateway có thể gây tăng bộ nhớ đáng kể khi nhiều upload diễn ra đồng thời.

Với multipart upload, WebFlux hỗ trợ **FilePart** để chuyển file tới đích mà không yêu cầu ứng dụng tự tạo một mảng byte chứa toàn bộ file:

~~~java
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class UploadController {
    private final Path uploadDirectory = Path.of("uploads");

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<Void>> upload(@RequestPart("file") FilePart part) {
        Path destination = uploadDirectory.resolve(UUID.randomUUID() + ".bin");
        return part.transferTo(destination)
                .thenReturn(ResponseEntity.accepted().build());
    }
}
~~~

Đây là ví dụ rút gọn: thư mục **uploads** phải được tạo, cấu hình quyền truy cập và quản lý dung lượng; cần xác thực, giới hạn kích thước và xử lý lỗi lưu trữ. Tên file từ client **không được tin cậy** để ghép trực tiếp thành đường dẫn lưu. Với multipart, framework có thể đệm một phần nội dung hoặc ghi ra file tạm theo cấu hình, nên “không gom toàn bộ vào heap của ứng dụng” không đồng nghĩa với “không dùng bộ đệm hoặc đĩa”.

### Hai nhóm giới hạn cần đặt riêng

1. **Giới hạn an toàn đầu vào:** kích thước request/part, số part, kích thước header/form field, thời gian upload, quota đĩa và số upload đồng thời.
2. **Giới hạn giải mã trong bộ nhớ:** khi WebFlux phải decode/aggregate một phần body, cấu hình như **spring.codec.max-in-memory-size** có thể ảnh hưởng đến lượng dữ liệu tối đa được gom bởi một số codec; điều này **không thay thế giới hạn kích thước upload tổng thể**.

Nếu gateway chặn request quá lớn hoặc backend từ chối sớm, client cần nhận lỗi phù hợp. Backpressure không thay cho chính sách từ chối tệp vượt quota.

## 9. Viết Gateway filter quan sát body mà không gom dữ liệu

Ví dụ sau minh họa một **GlobalFilter** đo số byte request body đi qua luồng tiêu thụ. Filter **không tự subscribe**, **không lưu DataBuffer**, và **không gọi join**:

~~~java
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class RequestBodyBytesFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(RequestBodyBytesFilter.class);

    @Override
    public int getOrder() {
        return -10;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        AtomicLong bytesSeen = new AtomicLong();

        ServerHttpRequestDecorator request =
                new ServerHttpRequestDecorator(exchange.getRequest()) {
                    @Override
                    public Flux<DataBuffer> getBody() {
                        return super.getBody()
                                .doOnNext(buffer ->
                                        bytesSeen.addAndGet(buffer.readableByteCount()));
                    }
                };

        return chain.filter(exchange.mutate().request(request).build())
                .doFinally(signal ->
                        log.debug("Consumed request-body bytes={}, signal={}",
                                bytesSeen.get(), signal));
    }
}
~~~

**Điều ví dụ thực hiện:** Đếm kích thước các buffer thực sự được tiêu thụ qua decorator. Đây là phép đo **byte đã đi qua publisher**, không phải bằng chứng rằng toàn bộ body đã upload thành công hoặc số byte backend thực nhận bằng hệt. Nếu request bị hủy/lỗi giữa chừng, giá trị có thể thấp hơn Content-Length. Khi không có ai tiêu thụ body, con số có thể bằng 0.

**Điều cần kiểm tra khi áp dụng thực tế:**

- Thứ tự filter phải cho phép decorator được cài trước thành phần tiêu thụ body. Một filter có thể được chạy trong nhiều đường xử lý khác nhau; chỉ đếm request theo mục đích cần thiết.
- **doOnNext** chỉ đọc **readableByteCount()**, không giữ tham chiếu DataBuffer và không làm công việc blocking.
- **doFinally** được gọi khi hoàn tất, lỗi hoặc cancel. Tránh ghi thông tin nhạy cảm và nhãn metric có cardinality quá cao.
- Một decorator có thể bị đăng ký/đọc nhiều lần trong các cấu hình cache/retry đặc biệt; nếu yêu cầu số byte mạng chính xác, cần đo ở lớp phù hợp và xác định lại ý nghĩa metric.
- Một số API hoặc package thay đổi theo phiên bản Spring Cloud Gateway; xác thực tương thích với stack đang sử dụng.

Nếu mục tiêu chỉ là quan sát số request, latency và status theo route, nên **ưu tiên metrics/tracing có sẵn** hơn là đọc body. Chỉ dùng custom body filter khi thực sự cần tín hiệu theo byte và có lý do vận hành rõ ràng.

## 10. Các operator Reactor ảnh hưởng đến backpressure

Một pipeline reactive có thể hoạt động đúng về mặt chức năng nhưng vẫn dùng nhiều bộ đệm. Các operator sau có ý nghĩa khác nhau:

| Operator | Tác dụng | Rủi ro hoặc giới hạn |
| --- | --- | --- |
| **limitRate(n)** | Điều chỉnh nhu cầu yêu cầu upstream theo từng đợt | Không giới hạn số HTTP request/giây |
| **flatMap(fn, concurrency)** | Giới hạn số publisher con được đăng ký đồng thời | Vẫn có prefetch và buffering; kết quả có thể xen kẽ thứ tự |
| **concatMap(fn)** | Xử lý các publisher con theo thứ tự | Có thể giảm thông lượng nếu downstream chậm |
| **onBackpressureBuffer(capacity)** | Đệm có giới hạn khi bên nhận không theo kịp | Đầy buffer phải có hành vi overflow được thiết kế rõ |
| **onBackpressureDrop()** | Bỏ bớt phần tử khi downstream không theo kịp | Mất dữ liệu; không phù hợp cho thanh toán, đơn hàng hoặc audit |
| **onBackpressureLatest()** | Giữ giá trị mới hơn khi không theo kịp | Bỏ qua trạng thái trung gian |
| **collectList() / reduce()** | Gom phần tử thành kết quả cuối | Chờ luồng kết thúc, có thể tốn bộ nhớ hoặc không bao giờ hoàn tất |
| **buffer(n) / window(n)** | Nhóm phần tử thành lô hoặc cửa sổ | Tạo trạng thái/bộ đệm bổ sung, phải xét kích thước và tốc độ |

Ví dụ giới hạn concurrency của một bước xử lý bất đồng bộ:

~~~java
Flux<Result> results = source
        .limitRate(64)
        .flatMap(item -> processAsync(item), 8);
~~~

Ở đây, **processAsync(item)** là hàm giả định trả về **Mono&lt;Result&gt;**. **limitRate(64)** điều chỉnh cách pipeline yêu cầu dữ liệu từ upstream; **flatMap(..., 8)** hạn chế số publisher con xử lý đồng thời. Cả hai **không** tương đương với **RequestRateLimiter** của Spring Cloud Gateway, vốn áp chính sách giới hạn **HTTP request**.

Không nên áp dụng **onBackpressureDrop** lên dữ liệu cần xử lý đầy đủ rồi hy vọng backpressure sẽ giải quyết mọi vấn đề: các phần tử đã bị bỏ không thể tự khôi phục. Đối với sự kiện bắt buộc không mất, cần thiết kế hàng đợi bền vững, cơ chế phát lại và xác nhận tiêu thụ ở lớp thích hợp.

### Lưu ý về thao tác blocking

Đường đi mặc định của Reactor Netty sử dụng event-loop, nên việc gọi JDBC đồng bộ, đọc file chặn luồng hoặc **Thread.sleep()** trong **map**, **doOnNext** hay gateway filter có thể làm chậm nhiều request khác. Nếu có công việc blocking chưa thể thay thế, hãy cô lập có kiểm soát, ví dụ:

~~~java
Mono<Result> result = Mono.fromCallable(() -> legacyBlockingCall())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đoạn mã trên chỉ là giải pháp cô lập tác vụ blocking; nó vẫn tiêu thụ thread/tài nguyên hữu hạn. Với proxy streaming, ưu tiên API I/O bất đồng bộ hoặc thư viện reactive phù hợp.

## 11. Điều kiện để end-to-end streaming thật sự hoạt động

**End-to-end streaming** đòi hỏi tất cả tầng quan trọng đều cho phép phát dần:

~~~mermaid
flowchart LR
    A[Data source] --> B[Service / codec]
    B --> C[Gateway filters]
    C --> D[Proxy / TLS / compression]
    D --> E[Client / decoder]
~~~

Một tầng có thể phá vỡ việc truyền dần dù các tầng còn lại là reactive. Khi triển khai, kiểm tra:

1. **Nguồn:** database/client thư viện có phát kết quả dần không, hay thực tế đã tải toàn bộ danh sách?
2. **Service:** endpoint trả **Flux** và media type thích hợp chưa, hay controller dùng **collectList()** trước khi trả?
3. **Codec:** serializer có flush theo record/event không, hay chờ đủ body mới xuất?
4. **Gateway:** route/filter có đọc, rewrite, cache hoặc log toàn body không?
5. **Proxy phía trước:** NGINX, ingress, CDN, WAF hoặc bộ nén có buffer response không; timeout cho kết nối dài đã phù hợp chưa?
6. **Client:** công cụ hoặc thư viện có tự đệm output tới khi kết nối đóng không; đã parse NDJSON/SSE theo record chưa?

Một **Flux** ở chữ ký phương thức chỉ là điều kiện thuận lợi, **không phải bằng chứng đủ** rằng các byte đã đến client dần theo thời gian.

### Timeout, keepalive và kết nối lâu

SSE có thể giữ response mở lâu. Cần phân biệt:

- **Connection timeout:** thời gian tạo kết nối TCP/TLS với upstream.
- **Response/idle timeout:** thời gian chờ phản hồi đầu tiên hoặc chờ dữ liệu tiếp theo, tùy client/proxy và phiên bản cấu hình.
- **Deadline tổng:** thời gian tối đa một thao tác cần hoàn thành; có thể không phù hợp để áp máy móc cho một stream chủ ý chạy liên tục.

Heartbeat định kỳ, ví dụ một dòng comment **: ping** trong SSE, giúp một số proxy biết kết nối vẫn còn hoạt động, nhưng **không thay cho cấu hình timeout và kiểm tra kết nối đầu-cuối**. Một số gateway/proxy có thời hạn kết nối tối đa dù stream có heartbeat.

### Retry và circuit breaker

Retry một request streaming cần đặc biệt cẩn trọng. Nếu response đã gửi vài sự kiện cho client, **retry tự động toàn bộ request** có thể tạo sự kiện trùng hoặc kết quả khó ghép. Nếu request upload bị gián đoạn, gửi lại từ đầu không đồng nghĩa có thể tiếp tục từ byte đã nhận. Dùng cơ chế resume/range, offset và idempotency do giao thức ứng dụng thiết kế khi cần.

Circuit breaker có thể ngăn request mới tới upstream đang lỗi. Tuy nhiên, nếu một stream đã gửi header/byte rồi mới lỗi, gateway **không thể quay lại trả mã HTTP 503 thay thế toàn bộ response**. Phía client cần nhận biết stream bị ngắt, quyết định reconnect, resume hoặc báo lỗi từng phần theo contract.

## 12. Bảo mật và quan sát luồng dữ liệu

Spring Cloud Gateway thường là điểm chung để áp dụng xác thực, giới hạn lưu lượng, chuyển đổi path/header, TLS và tracing. Với streaming, cần chú ý thêm vòng đời kết nối và dữ liệu đang truyền.

**Xác thực/ủy quyền:**

- Xác thực trước khi mở stream; service nghiệp vụ vẫn kiểm tra quyền trên dữ liệu được phát.
- Với stream dài, xác định chính sách khi token hết hạn hoặc quyền người dùng bị thu hồi; không mặc định một kết nối đang mở sẽ tự được xác thực lại mỗi sự kiện.
- Tránh đặt token nhạy cảm trong query string vì URL thường xuất hiện trong log, tracing hoặc lịch sử truy cập.

**Giới hạn tài nguyên:**

- **Rate limiting** giới hạn số HTTP request, còn **backpressure** điều tiết phần tử trong pipeline. Một SSE connection chỉ là một request nhưng có thể sống rất lâu, nên có thêm quota **số kết nối đồng thời**, thời gian tồn tại và ngân sách truyền dữ liệu.
- Giới hạn dung lượng upload, kích thước frame/record, bộ đệm codec, kết nối và lưu trữ theo đặc điểm của endpoint.
- SSE/NDJSON cần giới hạn kích thước mỗi sự kiện hoặc dòng để một record bất thường không khiến client/decoder giữ quá nhiều dữ liệu.

**Quan sát:**

| Tín hiệu | Câu hỏi được trả lời |
| --- | --- |
| Active streaming connections | Hiện có bao nhiêu kết nối mở lâu? |
| Bytes sent/received | Đang truyền bao nhiêu dữ liệu và chiều nào? |
| Time to first byte/event | Client bắt đầu nhận được dữ liệu sau bao lâu? |
| Event/record rate | Nguồn phát và client xử lý bao nhiêu bản ghi theo thời gian? |
| Cancellation/disconnect | Bao nhiêu stream kết thúc do client ngắt kết nối? |
| Retry/fallback/error midstream | Có lỗi sau khi response đã bắt đầu không? |
| Heap/direct memory, event-loop latency | Hệ thống có đệm quá nhiều hoặc nghẽn I/O không? |

Gắn **trace context** qua Gateway và backend để xác định nơi phát sinh độ trễ. Với stream dài, chỉ nhìn vào thời gian request hoàn tất có thể không phản ánh trải nghiệm; nên ghi nhận cả thời điểm sự kiện đầu tiên và khoảng cách giữa các sự kiện. Không thêm token, body chứa dữ liệu cá nhân hoặc ID có số lượng giá trị vô hạn làm nhãn metric.

## 13. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| SSE chỉ hiện khi request kết thúc | Codec/filter/proxy/client đang buffer | Gọi trực tiếp service bằng **curl -N** rồi đi qua từng tầng |
| Gateway tăng RAM khi proxy tệp lớn | Filter đọc toàn body, codec gom dữ liệu, nhiều request đồng thời | Tìm **join**, **collectList**, body logging/cache; giới hạn kích thước |
| Stream bị cắt sau một thời gian cố định | Proxy idle timeout, response timeout hoặc deadline | Đối chiếu timeout từng hop; dùng heartbeat phù hợp nếu là SSE |
| Client nhận event trùng sau reconnect | Server phát lại không theo ID; retry lặp nội dung | Thiết kế idempotency, event ID và cơ chế replay |
| Endpoint bị lỗi khi client chậm | Nguồn phát nhanh, buffer đầy, source không hỗ trợ backpressure | Giảm đồng thời, đo demand/buffer, chọn chiến lược overflow rõ ràng |
| Gateway trả 200 nhưng stream thiếu dữ liệu | Lỗi xảy ra sau khi header đã commit | Ghi nhận lỗi giữa luồng, kiểm tra server/client logs và contract resume |
| SSE hoạt động ở máy dev nhưng lỗi sau ingress | Proxy buffering, nén, timeout, HTTP version khác | Kiểm tra hạ tầng thực tế, header và thời điểm nhận từng sự kiện |
| Upload chậm làm nghẽn cả gateway | I/O blocking trên event-loop hoặc quota không phù hợp | Dùng API bất đồng bộ, kiểm soát concurrency, theo dõi event-loop |

Không chỉ dựa vào việc response có header **Transfer-Encoding: chunked** để kết luận stream đang tối ưu. Hãy đo **thời điểm dữ liệu đến client**, **bộ nhớ**, **số kết nối**, **độ trễ** và **hành vi khi một phía chậm hoặc ngắt kết nối**.

## 14. Bài thực hành tổng hợp

**Bối cảnh:** Một hệ thống đặt hàng có Notification service phát trạng thái đơn hàng qua SSE; Report service trả NDJSON gồm hàng nghìn bản ghi; File service nhận upload; tất cả đi qua Spring Cloud Gateway.

### Phần A — Thiết lập và định tuyến

1. Tạo Notification endpoint trả **Flux&lt;ServerSentEvent&lt;...&gt;&gt;** và Report endpoint trả **Flux&lt;ReportRow&gt;** với **application/x-ndjson**.
2. Tại Gateway, khai báo route cho **/api/stream/\*\*** và **/api/reports/\*\***; dùng **StripPrefix** hoặc **RewritePath** sao cho path chuyển tiếp phù hợp với backend.
3. Dùng **curl -N** qua gateway và trực tiếp tới service để so sánh thời gian nhận sự kiện/bản ghi đầu tiên.

### Phần B — Kiểm tra backpressure và bộ nhớ

1. Tạo client đọc response chậm có kiểm soát; thử nhiều kết nối đồng thời trong môi trường thử nghiệm.
2. Quan sát heap/direct memory, kích thước hàng đợi, sự kiện lỗi/cancel, CPU và latency theo route.
3. Thử thêm một phép **collectList()** trong một endpoint thử nghiệm với dữ liệu hữu hạn, sau đó so sánh thời điểm nhận byte đầu tiên và bộ nhớ. Không áp dụng phép gom này cho stream vô hạn.
4. Thử **limitRate** và giới hạn concurrency ở nơi xử lý từng bản ghi; giải thích vì sao đây không phải rate limiter HTTP.

### Phần C — Kiểm tra hủy và lỗi giữa luồng

1. Đóng client SSE giữa chừng và quan sát subscription/connection có được hủy không.
2. Cố ý cho upstream lỗi sau khi đã phát vài sự kiện và quan sát response đã commit có còn đổi status được không.
3. Thử đi qua ingress/reverse proxy thật để kiểm tra buffering, timeout và reconnect.
4. Với upload, đặt giới hạn dung lượng rõ ràng và kiểm tra trường hợp client gửi quá quota hoặc ngắt kết nối nửa chừng.

**Tiêu chí đạt:** Có bằng chứng dữ liệu được nhận dần; bộ nhớ không tăng tuyến tính theo tổng dung lượng stream trong đường đi dự kiến; giới hạn tài nguyên và hành vi khi hủy/lỗi được quan sát rõ; không có filter vô tình gom toàn bộ body. Không dùng mỗi chữ ký **Flux** hoặc một ảnh chụp status **200** làm bằng chứng.

## 15. Ghi nhớ

- **Backpressure** trong Reactive Streams là cơ chế subscriber truyền nhu cầu bằng **Subscription.request(n)**; tín hiệu này áp dụng cho **phần tử reactive**, không đồng nhất với tốc độ mạng hay số HTTP request.
- **HTTP streaming** truyền body theo các phần; SSE, NDJSON và raw bytes có cách framing khác nhau. HTTP chunk, TCP packet và bản ghi ứng dụng không có ranh giới tương đương.
- **Spring WebFlux** dùng **Flux&lt;DataBuffer&gt;** cho body ở cấp thấp. Spring Cloud Gateway Server WebFlux có thể proxy luồng mà không buộc giữ toàn bộ nội dung trong bộ nhớ, miễn là các thành phần trung gian không chủ động aggregate.
- **join**, **collectList**, một số codec/body filter, proxy buffering và client buffering có thể làm mất lợi ích của streaming; phải kiểm chứng end-to-end.
- **DataBuffer** cần tuân thủ vòng đời bộ nhớ; tránh subscribe thủ công, giữ buffer hoặc thực hiện I/O blocking trên event-loop.
- Đối với stream dài hoặc upload lớn, thiết kế thêm **timeout, quota, kiểm soát kết nối, xử lý hủy, retry có ngữ nghĩa, xác thực, tracing và metrics**. Backpressure giúp điều tiết dòng dữ liệu, nhưng không thay thế quản trị tài nguyên và độ tin cậy.
