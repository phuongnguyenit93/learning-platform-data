# Bộ đệm của máy chủ, proxy và phía nhận trong Spring WebFlux

## 1. Vì sao server đã flush mà client vẫn chưa thấy dữ liệu?

Một endpoint WebFlux có thể phát dữ liệu đều đặn bằng `Flux<T>`, encoder có thể tạo từng phần byte, và server có thể gọi flush sau mỗi event. Tuy vậy, người dùng vẫn có thể chỉ nhìn thấy toàn bộ nội dung khi stream kết thúc.

Lý do là **streaming là đặc tính của toàn đường truyền**, không chỉ của controller. Dữ liệu có thể được giữ lại ở nhiều tầng:

1. Publisher và các operator trong ứng dụng.
2. `HttpMessageWriter`, encoder và response abstraction của Spring.
3. Reactor Netty, outbound channel buffer và TLS.
4. Socket send buffer và ngăn xếp TCP của hệ điều hành.
5. Reverse proxy, ingress, API gateway, service mesh hoặc CDN.
6. Thư viện HTTP, runtime và UI phía client.

Mỗi tầng có thể gom nhiều byte lại trước khi chuyển tiếp. Vì vậy cần phân biệt ba thời điểm:

- **Application emitted:** Publisher phát một item.
- **Server flushed:** framework/server yêu cầu đẩy dữ liệu đang chờ xuống transport.
- **Client consumed:** ứng dụng phía nhận đã đọc và xử lý dữ liệu.

Ba thời điểm này không đồng nghĩa. Flush là tín hiệu cho tầng truyền tải tiếp tục gửi dữ liệu; nó không phải xác nhận rằng browser đã nhận, giải mã hoặc hiển thị event.

~~~text
Flux / Publisher
      |
      v
Spring encoder + HttpMessageWriter
      |
      v
ServerHttpResponse / writeAndFlushWith
      |
      v
Reactor Netty outbound buffer
      |
      v
TLS + OS socket send buffer
      |
      v
TCP / HTTP framing
      |
      v
Reverse proxy / ingress / CDN
      |
      v
Client HTTP library / browser
      |
      v
ReadableStream / EventSource / UI
~~~

Bài học này tập trung vào cách nhận diện và kiểm soát buffering ở từng tầng, cách thiết kế SSE/NDJSON, cách cấu hình proxy, và cách kiểm thử thời gian nhận event từ client thực tế.

## 2. Bốn khái niệm cần tách biệt

### 2.1. Buffering

Buffering là giữ byte hoặc item tạm thời rồi mới chuyển tiếp. Nó có thể nhằm:

- Giảm số lần gọi I/O.
- Tăng thông lượng khi ghi dữ liệu theo lô.
- Hỗ trợ compression hoặc encryption.
- Đáp ứng định dạng cần một document hoàn chỉnh.
- Điều tiết tốc độ giữa producer và consumer.
- Giảm số lần truyền qua mạng.

Buffering không mặc nhiên là lỗi. Với file lớn, batch database hoặc JSON document thông thường, buffering có thể hợp lý. Vấn đề xuất hiện khi ứng dụng cần event đến sớm nhưng một tầng trung gian lại chờ thêm dữ liệu hoặc chờ stream kết thúc.

### 2.2. Flushing

Flush yêu cầu một tầng ghi đẩy dữ liệu đang chờ xuống tầng thấp hơn. Trong WebFlux, `ServerHttpResponse.writeAndFlushWith` cho phép chia response thành các nhóm Publisher và flush sau từng nhóm.

Flush không:

- Tạo ranh giới message ở TCP.
- Buộc một TCP packet riêng cho mỗi event.
- Vượt qua mọi buffer của proxy hoặc CDN.
- Bảo đảm client application đã đọc dữ liệu.
- Bảo đảm UI render ngay trong cùng thời điểm.

### 2.3. Backpressure

Backpressure điều tiết demand từ downstream về upstream theo Reactive Streams. Nếu client/server không tiêu thụ nhanh, demand có thể giảm và nguồn reactive được điều tiết khi các thành phần hỗ trợ cơ chế đó.

Backpressure khác buffering. Một pipeline có backpressure vẫn có thể chứa buffer hữu hạn ở operator, Netty, socket hoặc proxy. Một proxy bật response buffering thậm chí có thể đọc nhanh từ upstream và giữ dữ liệu riêng trước khi gửi cho client.

### 2.4. Framing

Framing xác định cách bên nhận biết một message hoặc record kết thúc ở đâu. Ví dụ:

- SSE kết thúc một event bằng dòng trống.
- NDJSON dùng newline để phân tách object JSON.
- JSON array là một document có dấu ngoặc mở/đóng.
- HTTP/1.1 có thể dùng chunked transfer framing.
- HTTP/2 dùng DATA frames.

Ranh giới chunk của transport không nhất thiết trùng với ranh giới event của ứng dụng. Một event có thể đến qua nhiều lần đọc; nhiều event cũng có thể nằm trong một lần đọc.

## 3. Buffering bên trong ứng dụng WebFlux

### 3.1. `Flux<T>` không tự bảo đảm flush từng item

Controller trả `Flux<T>` có nghĩa là nguồn có thể phát nhiều giá trị theo thời gian. Cách encode và flush phụ thuộc media type, `HttpMessageWriter` và cấu hình codec.

Ví dụ một stream SSE:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.<String>builder()
            .id(Long.toString(index))
            .event("tick")
            .data("message-" + index)
            .build());
}
~~~

`text/event-stream` là media type dành cho event streaming. Spring có writer chuyên biệt cho SSE và flush event theo từng phần tử. Reactor Netty cũng mô tả chiến lược SSE là flush sau mỗi phần tử Publisher được phát.

Với `application/json` thông thường, client thường mong một JSON document hoàn chỉnh. Dù server có thể ghi các byte của document theo nhiều lần write, client gọi `response.json()` hoặc `bodyToMono(String.class)` vẫn phải đợi toàn bộ body trước khi parse. Không dùng JSON document như một giao thức event chỉ vì controller trả Flux.

### 3.2. Buffer do operator tạo ra

Các operator như `buffer`, `bufferTimeout`, `collectList`, `reduce` hoặc một số chiến lược prefetch có thể giữ nhiều item trước khi phát tiếp.

Ví dụ cố ý gom năm event:

~~~java
Mono<List<Event>> buffered =
    Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(index -> new Event(index + 1, "event-" + index))
        .collectList();
~~~

Publisher chỉ phát List khi nguồn complete. Nếu nguồn là vô hạn, `collectList` không phát kết quả cho tới khi bị kết thúc hoặc hủy; đây là lỗi thiết kế nếu endpoint cần stream liên tục.

Các operator này không xấu. Hãy dùng chúng khi nghiệp vụ thật sự cần batch hoặc aggregate, và tránh đặt chúng trên đường đi của event cần phát ngay.

### 3.3. Buffer của encoder và message writer

Codec có thể cần gom dữ liệu để:

- Tạo một JSON document hợp lệ.
- Hoàn tất một object trước khi encode.
- Giải quyết charset hoặc framing.
- Thực hiện compression.
- Tạo một DataBuffer có kích thước phù hợp.

Với streaming response, hãy chọn media type mà writer hỗ trợ streaming. Spring WebFlux hỗ trợ các streaming media type như `text/event-stream` và có thể cấu hình streaming media types cho Jackson encoder. Đừng suy ra flush policy chỉ từ kiểu Java `Flux`.

### 3.4. Flush theo nhóm với `writeAndFlushWith`

`ServerHttpResponse.writeWith` ghi một Publisher các DataBuffer. `writeAndFlushWith` nhận một Publisher chứa nhiều Publisher con; mỗi Publisher con là một nhóm dữ liệu sau khi ghi xong sẽ được flush.

~~~java
Mono<Void> writeEvents(ServerHttpResponse response) {
    Flux<Publisher<? extends DataBuffer>> flushGroups =
        Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(index -> {
                String frame = "data: event-" + (index + 1) + "\n\n";
                DataBuffer buffer = response.bufferFactory().wrap(
                    frame.getBytes(StandardCharsets.UTF_8));
                return Mono.just(buffer);
            });

    response.getHeaders().setContentType(MediaType.TEXT_EVENT_STREAM);
    return response.writeAndFlushWith(flushGroups);
}
~~~

Ở đây mỗi inner Publisher tạo một SSE frame; response được flush sau mỗi nhóm. Khi chuyển DataBuffer cho response writer, ownership được chuyển cho thành phần ghi theo hợp đồng của API. Không release buffer trước khi writer tiêu thụ.

Dùng `writeAndFlushWith` khi thật sự cần kiểm soát nhóm flush ở tầng response. Với controller SSE thông thường, trả `Flux<ServerSentEvent<T>>` thường đơn giản hơn và để writer SSE quản lý framing.

## 4. Buffer ở server runtime, TLS và hệ điều hành

### 4.1. Reactor Netty có outbound buffer

Spring WebFlux thường chạy trên Reactor Netty khi dùng cấu hình WebFlux mặc định của Spring Boot. Dữ liệu được chuyển thành DataBuffer/ByteBuf và đi qua Netty channel pipeline trước khi ghi ra socket.

Netty có thể giữ dữ liệu trong outbound buffer cho tới khi channel có thể ghi. Khi channel bị nghẽn, write có thể chờ hoặc bị điều tiết theo khả năng của transport. Event loop xử lý I/O bất đồng bộ; không nên dùng `Thread.sleep`, `block()` hoặc thao tác đồng bộ kéo dài trong handler để cố điều khiển nhịp stream.

### 4.2. TLS và compression có thể gom dữ liệu

HTTPS thêm lớp TLS record trước khi byte đi xuống socket. Compression cũng có thể giữ một lượng dữ liệu để tạo block nén hiệu quả. Các tầng này có thể làm thay đổi kích thước và thời điểm dữ liệu được chuyển tiếp.

Nếu stream có event nhỏ và cần độ trễ thấp:

- Kiểm tra compression có đang bật ở server, proxy hoặc CDN không.
- Đo cả đường HTTP và HTTPS nếu môi trường cho phép.
- Chỉ tắt compression cho endpoint streaming khi phép đo cho thấy nó gây trì hoãn và trade-off phù hợp.
- Không giả định thêm một lần flush ở controller sẽ buộc mọi lớp TLS/compression gửi ngay một record.

### 4.3. Socket send buffer và TCP

Hệ điều hành có socket send buffer. TCP truyền một luồng byte có thứ tự, không giữ ranh giới message của Publisher. Dữ liệu nhỏ có thể được ghép hoặc chia thành các segment theo trạng thái mạng, cửa sổ truyền và thuật toán transport.

Vì vậy, không được viết client giả định một lần read tương ứng đúng một event. Client phải parse framing của giao thức ứng dụng.

### 4.4. Flush không phải TCP acknowledgement

Flush chỉ đẩy dữ liệu xuống tầng transport gần hơn. TCP acknowledgement cho biết dữ liệu đã được xác nhận ở tầng TCP của peer, không chứng minh ứng dụng phía peer đã parse event hay render giao diện.

Nếu cần xác nhận nghiệp vụ rằng người nhận đã xử lý một event, hãy thiết kế acknowledgement ở tầng ứng dụng, ví dụ event ID và API xác nhận riêng.

## 5. Buffer ở reverse proxy và ingress

### 5.1. Nginx mặc định bật response proxy buffering

Khi `proxy_buffering on`, Nginx đọc response từ upstream càng sớm càng tốt, giữ dữ liệu trong buffer cấu hình và có thể ghi phần dư ra file tạm nếu response lớn. Client có thể chỉ nhận dữ liệu sau khi proxy đã gom đủ một lượng byte hoặc hoàn tất response.

Khi `proxy_buffering off`, Nginx chuyển dữ liệu tới client đồng bộ hơn khi nhận từ upstream và không cố đọc toàn bộ response trước. Tài liệu Nginx nêu rõ mặc định của directive này là `on`.

### 5.2. Cấu hình Nginx cho endpoint streaming

Ví dụ cấu hình trong server block:

~~~nginx
location /api/stream/ {
    proxy_pass http://webflux_app;
    proxy_http_version 1.1;

    proxy_buffering off;
    proxy_cache off;

    proxy_read_timeout 1h;
    gzip off;
}
~~~

Ý nghĩa:

- `proxy_buffering off` tắt response buffering cho location này.
- `proxy_cache off` tránh cache response stream ở location.
- `proxy_read_timeout` cần đủ dài cho kết nối stream ít dữ liệu.
- `gzip off` là lựa chọn khi compression gây trì hoãn event nhỏ; chỉ tắt nếu cần sau khi kiểm thử.

Đây là ví dụ cấu hình, không phải giá trị timeout tối ưu cho mọi hệ thống. Hãy đồng bộ timeout với gateway, load balancer, ingress và thời lượng kết nối mà sản phẩm yêu cầu.

### 5.3. Header `X-Accel-Buffering`

Nginx có thể bật/tắt response buffering theo từng response bằng header:

~~~http
X-Accel-Buffering: no
~~~

Spring có thể đặt header này trước khi response commit:

~~~java
response.getHeaders().set("X-Accel-Buffering", "no");
~~~

Header này hữu ích khi chỉ một số endpoint cần streaming. Nginx có thể được cấu hình để bỏ qua header điều khiển bằng `proxy_ignore_headers`, vì vậy hãy xác minh cấu hình thực tế.

### 5.4. Đừng nhầm response buffering với request buffering

- `proxy_buffering` điều khiển việc Nginx buffer response từ upstream trước khi gửi client.
- `proxy_request_buffering` điều khiển việc Nginx buffer request body của client trước khi chuyển tới upstream.

Khi debug server-sent events hoặc response stream, hãy kiểm tra `proxy_buffering`. Khi debug upload streaming từ client lên server, hãy kiểm tra `proxy_request_buffering`.

### 5.5. Các proxy khác cũng có thể buffer

Nginx không phải tầng duy nhất. Các thành phần sau có thể có chính sách buffering, compression, cache hoặc timeout riêng:

- Kubernetes ingress controller.
- Envoy hoặc service mesh sidecar.
- API gateway.
- CDN và edge cache.
- Load balancer của cloud.
- WAF hoặc reverse proxy của tổ chức.

Tên cấu hình khác nhau theo sản phẩm và phiên bản. Hãy kiểm tra tài liệu của đúng gateway đang triển khai; đừng áp dụng directive Nginx cho Envoy hoặc ngược lại.

## 6. Buffer ở client và giao diện

### 6.1. Client có thể chủ động đọc toàn bộ response

Trong Java WebClient:

~~~java
Mono<String> wholeBody = webClient.get()
    .uri("/api/stream/json")
    .retrieve()
    .bodyToMono(String.class);
~~~

`bodyToMono(String.class)` đợi body hoàn tất để tạo một String. Đây là cách hợp lý với document nhỏ, nhưng không phù hợp nếu muốn xử lý event ngay khi đến.

Để tiêu thụ theo phần tử, dùng API reactive tương ứng với media type:

~~~java
Flux<ServerSentEvent<String>> events = webClient.get()
    .uri("/api/stream/sse")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {});
~~~

Client vẫn có thể có buffer nội bộ. Cần subscribe và xử lý item theo luồng; tránh chuyển sang `collectList`, `blockLast` hoặc gom thành một String nếu mục tiêu là đọc sớm.

### 6.2. Browser Fetch có ReadableStream

`Response.body` trong Fetch API là `ReadableStream`. Có thể đọc từng chunk thay vì gọi `response.text()` hoặc `response.json()` để đợi toàn bộ body.

~~~javascript
const response = await fetch("/api/stream/flush");

if (!response.ok || !response.body) {
  throw new Error("HTTP " + response.status);
}

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const result = await reader.read();
  if (result.done) break;

  output.textContent += decoder.decode(result.value, { stream: true });
}

output.textContent += decoder.decode();
~~~

`TextDecoder` dùng `stream: true` để giữ trạng thái khi một ký tự UTF-8 bị chia giữa các chunk. Một chunk do browser đưa ra không nhất thiết tương ứng một SSE event hoặc một dòng NDJSON.

### 6.3. Dùng EventSource cho SSE

Nếu endpoint tuân theo giao thức SSE, browser có thể dùng `EventSource`:

~~~javascript
const source = new EventSource("/api/stream/sse");

source.addEventListener("update", (event) => {
  const payload = JSON.parse(event.data);
  console.log("received event", payload);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect");
};
~~~

EventSource tự parse event framing và hỗ trợ cơ chế reconnect của SSE. Nếu cần gửi method khác GET hoặc custom authorization header, cân nhắc Fetch streaming hoặc thiết kế xác thực phù hợp; EventSource API tiêu chuẩn có giới hạn về cách cấu hình request.

### 6.4. UI có thể gom cập nhật dù network đã nhận

Ngay cả khi JavaScript đọc chunk ngay, UI framework có thể batch state update hoặc chờ frame render tiếp theo. Developer tools cũng có thể hiển thị response preview theo cách không phản ánh chính xác thời điểm từng byte đến.

Hãy phân biệt:

- Thời điểm browser nhận byte.
- Thời điểm JavaScript đọc chunk.
- Thời điểm parser hoàn tất một event.
- Thời điểm state được cập nhật.
- Thời điểm trình duyệt render pixel.

Nếu mục tiêu là trải nghiệm người dùng, hãy đo tới thời điểm UI hiển thị event chứ không chỉ đo log ở server.

## 7. Media type và framing quyết định cách client xử lý

### 7.1. JSON document

`application/json` phù hợp với một JSON object hoặc array hoàn chỉnh. Client thường parse sau khi body hoàn tất. Không dùng JSON array làm giao thức event nếu yêu cầu client xử lý từng record ngay.

### 7.2. NDJSON

NDJSON dùng một JSON object trên mỗi dòng:

~~~text
{"id":1,"type":"created"}
{"id":2,"type":"updated"}
{"id":3,"type":"closed"}
~~~

Client có thể parse mỗi dòng khi newline hoàn tất. Tuy nhiên, newline framing không tự bảo đảm server/proxy flush sau từng dòng. Hãy kiểm tra writer, streaming media type, proxy và client; nếu cần flush tường minh, dùng API response có flush group.

### 7.3. Server-Sent Events

SSE dùng `text/event-stream`. Một event có thể có các dòng `id`, `event`, `data`, `retry` và kết thúc bằng một dòng trống:

~~~text
id: 1
event: update
data: {"status":"ready"}

id: 2
event: update
data: {"status":"running"}

~~~

Spring có `ServerSentEvent<T>` và writer chuyên biệt. SSE phù hợp cho luồng server-to-browser một chiều, có event framing và reconnect. Dùng heartbeat comment như `: keepalive` khi cần giữ kết nối qua hạ tầng có idle timeout; comment không tạo event nghiệp vụ.

### 7.4. HTTP/1.1 và HTTP/2

Với HTTP/1.1, response không có Content-Length có thể dùng chunked transfer encoding. Chunked encoding chỉ là framing truyền tải; chunk không phải event của ứng dụng.

HTTP/2 dùng DATA frames và stream multiplexing, không dùng chunked transfer encoding của HTTP/1.1. Không tự đặt `Transfer-Encoding: chunked` cho response HTTP/2. Để server và proxy quản lý framing giao thức.

## 8. Backpressure khi có nhiều tầng buffer

### 8.1. Backpressure trong ứng dụng

Nếu client đọc chậm, demand có thể giảm và publisher downstream điều tiết tốc độ upstream. Một số operator vẫn có prefetch hoặc buffer hữu hạn; cần xem toàn bộ pipeline chứ không chỉ một operator.

### 8.2. Proxy buffering có thể tách nhịp upstream/downstream

Khi proxy nhận nhanh từ WebFlux nhưng gửi chậm cho browser, proxy có thể giữ dữ liệu trong bộ nhớ hoặc file tạm. Upstream server nhìn thấy một consumer là proxy, không phải trực tiếp browser.

Điều này có thể khiến server ghi thành công trong khi browser chưa nhận event. Tắt buffering cho endpoint streaming có thể làm backpressure truyền qua proxy sát hơn, nhưng vẫn còn các buffer ở transport và client.

### 8.3. Đừng dùng flush để thay thế giới hạn tải

Flush thường xuyên có chi phí I/O và có thể làm giảm hiệu suất nếu mỗi byte nhỏ đều bị đẩy riêng. Hãy chọn flush boundary theo giao thức:

- Mỗi SSE event là một boundary hợp lý.
- Mỗi record NDJSON có thể là boundary nếu latency yêu cầu.
- File download thường tối ưu theo chunk lớn hơn.
- Batch response có thể ưu tiên thông lượng thay vì latency từng item.

Cần cân bằng độ trễ, CPU, số lần syscall, băng thông và số kết nối đồng thời.

## 9. Timeout, heartbeat và vòng đời kết nối dài

Streaming response có thể tồn tại lâu hơn request/response thông thường. Các tầng proxy/load balancer có idle timeout; nếu không có byte nào được gửi trong khoảng thời gian đó, kết nối có thể bị đóng.

Các biện pháp:

- Chọn timeout ở gateway/proxy đủ dài cho kết nối dự kiến.
- Gửi heartbeat theo giao thức khi stream có thể im lặng lâu.
- Đóng stream khi user rời trang hoặc không còn subscription.
- Dùng `doFinally` để cleanup resource ở complete/error/cancel.
- Giới hạn số kết nối và số stream đồng thời.
- Có chính sách reconnect, replay hoặc resume nếu event bị mất khi client ngắt kết nối.

Heartbeat chỉ giữ kết nối hoạt động khi hạ tầng coi dữ liệu đó là traffic. Nó không thay thế reconnect, event ID hoặc xử lý duplicate. Với SSE, có thể dùng comment heartbeat:

~~~text
: keepalive

~~~

Đừng phát heartbeat quá dày; chọn khoảng thời gian dựa trên idle timeout của đường truyền và chi phí kết nối.

## 10. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Project dưới đây có ba endpoint để so sánh:

- `GET /api/stream/sse`: phát SSE mỗi giây; Spring writer xử lý event streaming.
- `GET /api/stream/flush`: tạo từng SSE frame và dùng `writeAndFlushWith` để flush sau mỗi nhóm.
- `GET /api/stream/buffered`: gom năm event thành List rồi mới trả JSON.

### 10.1. Cấu trúc project

~~~text
webflux-stream-buffering/
├── pom.xml
└── src/main/java/example/streaming/
    ├── StreamingApplication.java
    └── StreamController.java
└── src/test/java/example/streaming/
    └── StreamControllerTest.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-stream-buffering</artifactId>
    <version>1.0.0</version>

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

### 10.3. `StreamingApplication.java`

~~~java
package example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
~~~

### 10.4. `StreamController.java`

~~~java
package example.streaming;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/stream")
public class StreamController {

    public record Event(
        long sequence,
        String message,
        Instant createdAt
    ) {}

    @GetMapping(
        path = "/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Event>> sse(
        ServerHttpResponse response
    ) {
        prepareStreamingHeaders(response);

        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(index -> {
                long sequence = index + 1;
                Event event = new Event(
                    sequence,
                    "event-" + sequence,
                    Instant.now()
                );

                return ServerSentEvent.<Event>builder(event)
                    .id(Long.toString(sequence))
                    .event("update")
                    .build();
            });
    }

    @GetMapping(
        path = "/flush",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Mono<Void> explicitFlush(ServerHttpResponse response) {
        prepareStreamingHeaders(response);

        Flux<Publisher<? extends DataBuffer>> flushGroups =
            Flux.interval(Duration.ofSeconds(1))
                .take(5)
                .map(index -> {
                    String frame =
                        "id: " + (index + 1) + "\n"
                        + "event: update\n"
                        + "data: manual-" + (index + 1) + "\n\n";

                    DataBuffer buffer = response.bufferFactory().wrap(
                        frame.getBytes(StandardCharsets.UTF_8)
                    );

                    return Mono.just(buffer);
                });

        return response.writeAndFlushWith(flushGroups);
    }

    @GetMapping(
        path = "/buffered",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<List<Event>> buffered() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(index -> new Event(
                index + 1,
                "event-" + (index + 1),
                Instant.now()
            ))
            .collectList();
    }

    private static void prepareStreamingHeaders(
        ServerHttpResponse response
    ) {
        response.getHeaders().set(
            "Cache-Control", "no-cache, no-transform");
        response.getHeaders().set(
            "X-Accel-Buffering", "no");
    }
}
~~~

Giải thích:

- `/sse` phát một `ServerSentEvent` mỗi giây. Writer SSE của Spring định dạng event và flush theo event.
- `/flush` tạo frame SSE thủ công. Mỗi inner Publisher trong `flushGroups` chứa một DataBuffer; `writeAndFlushWith` flush sau mỗi nhóm.
- `/buffered` dùng `collectList()`. Client chỉ nhận JSON array sau khi năm event đã được gom xong.
- `Cache-Control` và `X-Accel-Buffering` là gợi ý cho các tầng trung gian; chúng không thể ép mọi proxy/CDN tuân theo nếu cấu hình của tầng đó bỏ qua header.

Đây là ứng dụng demo hữu hạn năm event. Với stream vô hạn, bỏ `take(5)` chỉ khi đã có chính sách cancellation, heartbeat, timeout và giới hạn kết nối.

### 10.5. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven. Trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

### 10.6. Thử SSE trực tiếp bằng curl

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream/sse
~~~

`-N` hoặc `--no-buffer` tắt buffering đầu ra của curl để terminal hiển thị dữ liệu sớm hơn. Body dự kiến có năm event, mỗi event cách nhau khoảng một giây:

~~~text
id: 1
event: update
data: {"sequence":1,"message":"event-1","createdAt":"..."}

id: 2
event: update
data: {"sequence":2,"message":"event-2","createdAt":"..."}

...
~~~

Giá trị `createdAt` là thời điểm runtime nên thay đổi theo lần chạy.

### 10.7. So sánh endpoint aggregate

~~~bash
curl -N -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/stream/buffered
~~~

Endpoint này đợi nguồn complete sau khoảng năm giây rồi mới trả một JSON array. `curl -N` không thể làm ứng dụng phát sớm dữ liệu mà Publisher chưa phát.

### 10.8. Thử qua proxy

Khi ứng dụng chạy sau Nginx, gọi URL public qua proxy bằng cùng lệnh `curl -N`. So sánh với port trực tiếp của ứng dụng:

- Nếu localhost phát mỗi giây nhưng URL qua proxy chỉ hiện sau năm giây, kiểm tra proxy buffering, compression, cache và ingress.
- Nếu cả hai đều chậm, kiểm tra Publisher, operator, codec, server và client.
- Nếu curl hiển thị đều nhưng UI cập nhật muộn, kiểm tra parser và UI scheduling ở client.

## 11. Kiểm thử streaming bằng WebTestClient

Một test chỉ gọi `expectBody(String.class)` thường thu thập body hoàn chỉnh, vì thế nó không chứng minh event được nhận sớm. Để kiểm tra streaming, lấy response body dưới dạng Flux và đọc phần tử đầu trước khi stream kết thúc.

~~~java
package example.streaming;

import static org.springframework.http.MediaType.TEXT_EVENT_STREAM;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void firstSseDataArrivesBeforeStreamCompletes() {
        FluxExchangeResult<String> result = client.get()
            .uri("/api/stream/sse")
            .accept(TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(TEXT_EVENT_STREAM)
            .returnResult(String.class);

        String firstChunk = result.getResponseBody()
            .next()
            .block(Duration.ofSeconds(3));

        assertNotNull(firstChunk);
    }
}
~~~

Test này kiểm tra server trực tiếp và xác minh có dữ liệu đầu tiên trong thời hạn ba giây. Nó không kiểm tra Nginx, CDN hoặc browser; cần chạy cùng bài đo qua URL public để xác minh toàn đường truyền.

Không đặt ngưỡng thời gian quá sát một giây vì CI có thể bị tải. Với hệ thống thực, hãy dùng tolerance phù hợp và kiểm tra thời gian nhận event đầu tiên thay vì yêu cầu thời điểm chính xác tuyệt đối.

## 12. Quy trình chẩn đoán từ đầu đến cuối

Khi stream chỉ xuất hiện sau khi hoàn tất, làm theo thứ tự để tìm đúng tầng:

1. **Xác nhận nguồn phát:** thêm log hoặc metric tại nơi Publisher phát item; kiểm tra có `collectList`, `buffer`, `reduce`, `delayUntil` hoặc operator nào chờ đủ dữ liệu không.
2. **Kiểm tra writer/media type:** xem response có đúng `Content-Type` không; dùng `text/event-stream` cho SSE và xác minh writer có flush event.
3. **Kiểm tra server trực tiếp:** dùng `curl -N` tới port ứng dụng, bỏ qua proxy.
4. **Kiểm tra header response:** xem `Cache-Control`, `Content-Encoding`, `X-Accel-Buffering`, `Content-Length` và status.
5. **Thêm từng tầng trở lại:** gọi qua ingress, gateway, CDN theo thứ tự để tìm nơi bắt đầu trễ.
6. **Tắt response buffering ở đúng route:** cấu hình proxy cụ thể và kiểm tra có policy khác ghi đè không.
7. **Kiểm tra compression/cache:** tạm tắt trên endpoint thử nghiệm để xác định tác động.
8. **Kiểm tra client:** dùng `ReadableStream`/`EventSource` hoặc WebClient `bodyToFlux`; tránh `text()`, `json()` hay `bodyToMono(String.class)` khi cần đọc sớm.
9. **Đo thời gian:** ghi timestamp lúc server phát, lúc client nhận byte đầu, lúc parser hoàn tất event và lúc UI hiển thị.
10. **Kiểm tra timeout/cancellation:** xác định proxy có đóng kết nối idle hoặc client có hủy subscription không.

Không dùng log `doOnNext` ở controller làm bằng chứng client đã nhận byte. Callback đó chỉ cho biết item đi qua một điểm trong pipeline ứng dụng.

## 13. Các phép đo và chỉ số hữu ích

Phân biệt các độ trễ:

| Chỉ số | Đo từ đâu đến đâu? | Ý nghĩa |
| --- | --- | --- |
| Time to first server item | Handler subscribe đến item đầu tiên | Nguồn reactive có phát sớm không? |
| Time to first response byte | Request bắt đầu đến byte đầu tiên tại client | Server/transport/proxy có trì hoãn không? |
| Time to first event | Request bắt đầu đến event đã parse hoàn chỉnh | Framing và client parser có hoạt động không? |
| Inter-event delay | Khoảng cách giữa hai event client nhận | Stream có đều không? |
| Time to first render | Request bắt đầu đến UI hiển thị event | Trải nghiệm người dùng thực tế |

Có thể theo dõi Reactor Netty metrics như `reactor.netty.http.server.response.time`, `reactor.netty.http.server.data.sent.time`, số kết nối/stream đang hoạt động và lượng dữ liệu gửi. Metric server không thay thế phép đo từ client vì proxy và mạng nằm ngoài process.

Khi kiểm thử, ghi timestamp ở client cho từng event. Đừng chỉ đo tổng thời gian hoàn tất: một stream năm giây có thể phát event đầu sau 100 ms hoặc chỉ phát toàn bộ ở giây thứ năm.

## 14. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — Nghĩ `Flux` đồng nghĩa với flush từng item.** Flux mô tả nhiều giá trị; writer và media type quyết định chiến lược encode/flush. Dùng SSE hoặc flush group khi cần.

**Lỗi 2 — Dùng `collectList()` trên stream vô hạn.** Publisher không complete nên client không nhận kết quả. Xử lý từng item và quản lý lifecycle stream.

**Lỗi 3 — Trả `application/json` nhưng client mong event ngay.** JSON document thường được client parse khi body hoàn tất. Dùng SSE hoặc NDJSON theo hợp đồng.

**Lỗi 4 — Server flush nhưng Nginx vẫn buffer.** Tắt `proxy_buffering` ở location streaming hoặc dùng `X-Accel-Buffering: no` nếu proxy cho phép.

**Lỗi 5 — Chỉ tắt `proxy_request_buffering`.** Directive này liên quan request body. Response stream cần kiểm tra `proxy_buffering`.

**Lỗi 6 — Quên CDN/ingress/service mesh.** Một proxy trung gian khác vẫn có thể buffer. Kiểm tra từng hop.

**Lỗi 7 — Dùng `bodyToMono(String.class)` hoặc `response.text()`.** Các API này thu thập toàn body. Dùng Flux hoặc ReadableStream để đọc dần.

**Lỗi 8 — Cho rằng một lần read là một event.** TCP và HTTP framing không bảo toàn ranh giới Publisher item. Parse newline hoặc SSE blank-line framing.

**Lỗi 9 — Compression gom nhiều event nhỏ.** Đo với compression bật/tắt; chỉ tắt trên route streaming nếu có lợi ích rõ và chấp nhận chi phí băng thông.

**Lỗi 10 — Cache response stream.** Cache có thể giữ hoặc phát lại response không đúng kỳ vọng. Dùng cache policy phù hợp và tránh cache SSE thông thường.

**Lỗi 11 — Không gửi heartbeat trên kết nối im lặng lâu.** Proxy có idle timeout và có thể đóng kết nối. Gửi heartbeat hợp lý hoặc điều chỉnh timeout.

**Lỗi 12 — Flush quá thường xuyên.** Flush từng byte làm tăng overhead. Flush theo event/record có ý nghĩa thay vì mỗi thao tác ghi nhỏ.

**Lỗi 13 — Đặt Content-Length cố định cho stream chưa biết kích thước.** Để server quản lý framing; không tự đặt length nếu chưa biết chính xác toàn bộ body.

**Lỗi 14 — Tự thêm `Transfer-Encoding: chunked` cho HTTP/2.** Chunked là framing của HTTP/1.1. Để server xử lý protocol framing.

**Lỗi 15 — Chặn event loop bằng `block()` hoặc `Thread.sleep`.** Handler không phát được event đúng lịch và các connection khác cũng bị ảnh hưởng. Dùng Publisher non-blocking và scheduler phù hợp cho công việc blocking.

**Lỗi 16 — Không xử lý cancellation.** Client đóng tab hoặc proxy ngắt kết nối có thể cancel subscription. Gắn cleanup bằng `doFinally` và giải phóng resource.

**Lỗi 17 — Cố đổi status sau khi response đã commit.** Khi event đầu đã được gửi, không thể thay status/body bằng JSON error response mới. Dùng error event theo giao thức hoặc kết thúc stream.

**Lỗi 18 — Dùng log server làm kết luận cuối.** Server phát event không chứng minh browser nhận và render. Luôn kiểm tra từ client qua toàn đường truyền.

## 15. Bài tập tự kiểm tra

1. Vì sao server flush nhưng browser chưa thấy event? **Có thể còn buffer ở Netty, TLS/socket, proxy, client library hoặc UI.**
2. `writeAndFlushWith` khác `writeWith` ở điểm nào? **Nó nhận các nhóm Publisher và flush sau từng nhóm.**
3. `Flux<T>` có tự bảo đảm flush từng item không? **Không; writer, media type và cấu hình quyết định.**
4. Media type nào phù hợp cho server-to-browser event một chiều? **`text/event-stream` (SSE).**
5. Vì sao `collectList()` không phù hợp với stream vô hạn? **Nó chờ source complete mới phát List.**
6. Nginx `proxy_buffering` mặc định là gì? **`on`.**
7. Cấu hình nào tắt response buffering ở Nginx? **`proxy_buffering off`.**
8. Header nào có thể điều khiển buffering theo response trong Nginx? **`X-Accel-Buffering: no`.**
9. `proxy_request_buffering` điều khiển chiều nào? **Request body từ client lên upstream.**
10. `curl -N` làm gì? **Tắt buffering đầu ra của curl, không thay đổi buffering phía server/proxy.**
11. `Response.text()` có xử lý event từng chunk ngay không? **Không; nó đợi body hoàn tất thành text.**
12. Browser API nào đọc response tăng dần? **`Response.body` là ReadableStream.**
13. Một TCP segment có tương ứng một SSE event không? **Không; client phải parse framing SSE.**
14. `Cache-Control: no-transform` giải quyết mọi proxy buffering không? **Không; cần cấu hình proxy và kiểm thử từng tầng.**
15. Khi stream im lặng lâu, giải pháp nào có thể giúp tránh idle timeout? **Heartbeat và timeout phù hợp.**
16. Vì sao cần đo time-to-first-event ở client? **Để xác minh dữ liệu thực sự tới nơi tiêu thụ, qua cả proxy và client.**

## 16. Ghi nhớ và tài liệu tham khảo

- **Streaming là thuộc tính end-to-end.** Một Publisher phát item sớm chưa bảo đảm client thấy item sớm.
- **Buffering** giữ dữ liệu; **flush** yêu cầu đẩy dữ liệu xuống tầng dưới; **backpressure** điều tiết demand; **framing** xác định ranh giới record.
- Flux không tự bảo đảm flush từng item. SSE và `writeAndFlushWith` cho phép biểu đạt flush boundary rõ ràng.
- Reactor Netty, TLS, socket, TCP, proxy, CDN và client đều có thể ảnh hưởng độ trễ.
- Nginx mặc định bật `proxy_buffering`; tắt ở endpoint streaming hoặc dùng `X-Accel-Buffering: no` nếu được phép.
- `proxy_request_buffering` là chiều request; `proxy_buffering` là chiều response.
- Browser Fetch dùng ReadableStream để đọc tăng dần; `text()`/`json()` đợi toàn bộ body.
- `curl -N` giúp kiểm tra client output, nhưng cần so sánh trực tiếp với port ứng dụng và qua proxy.
- Đo time-to-first-byte, time-to-first-event và time-to-first-render ở đúng tầng.
- Xử lý heartbeat, cancellation, timeout và lỗi sau khi response commit.

Tài liệu chính thức:

1. [Spring Framework Reference — Return Values in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): reactive return types, streaming media types và flush behavior.
2. [Spring Framework Javadoc — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): writeWith và writeAndFlushWith.
3. [Reactor Netty Reference — HTTP Server and SSE](https://projectreactor.io/docs/netty/release/reference/http-server.html): HTTP server, SSE flush strategy, compression, transport và metrics.
4. [Nginx Documentation — ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): proxy_buffering, buffer size và X-Accel-Buffering.
5. [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): response body, ReadableStream và cách đọc response tăng dần.
6. [MDN — Streams API](https://developer.mozilla.org/en-US/docs/Web/API/Streams_API): chunk processing, cancellation và backpressure ở phía browser.
