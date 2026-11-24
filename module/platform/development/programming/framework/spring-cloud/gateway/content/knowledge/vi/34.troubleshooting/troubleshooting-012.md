# Khắc phục WebSocket ngắt sớm, SSE bị dồn bộ đệm và lỗi response đã commit

Spring Cloud Gateway thường chuyển tiếp các request HTTP có thời gian xử lý ngắn. WebSocket và Server-Sent Events (SSE) có vòng đời khác: kết nối có thể tồn tại nhiều phút hoặc nhiều giờ, dữ liệu được gửi từng phần và response có thể đã bắt đầu trước khi backend phát hiện lỗi. Vì vậy, một cấu hình timeout, filter hoặc proxy phù hợp với REST API thông thường vẫn có thể làm kết nối streaming bị ngắt hoặc dữ liệu đến client theo từng đợt.

Bài này tập trung vào ba biểu hiện thường gặp:

- WebSocket bắt tay thành công nhưng kết nối đóng ngay sau đó hoặc đóng theo chu kỳ.
- SSE trả về `200 OK` nhưng client chỉ nhận được nhiều event cùng lúc sau một khoảng chờ.
- Gateway hoặc custom filter báo response đã commit, không thể đổi status hay ghi thêm error body.

Các lỗi này có thể xuất hiện đồng thời. Hãy lần theo toàn bộ đường đi của request: client → CDN/WAF hoặc ingress → load balancer → Spring Cloud Gateway → service đích. Mỗi lớp có thể áp dụng timeout, buffering hoặc chính sách đóng kết nối riêng.

## 1. Phân biệt triệu chứng trước khi sửa

| Triệu chứng | Dấu hiệu cần xác nhận | Nhóm nguyên nhân thường gặp |
|---|---|---|
| WebSocket không nhận được `101 Switching Protocols` | Handshake trả về 4xx/5xx hoặc bị redirect | Route không khớp, URI dùng sai scheme, xác thực, `Origin`, TLS hoặc header handshake |
| WebSocket nhận `101` rồi đóng | Kết nối mở được nhưng đóng sau một khoảng thời gian khá ổn định | Idle timeout, thiếu ping/pong, backend đóng session, proxy không hỗ trợ upgrade hoặc lỗi khi reconnect |
| SSE trả `200` nhưng event đến theo cụm | Backend phát đều nhưng client không thấy dữ liệu ngay | Buffering ở proxy, compression, filter gom body, cache hoặc client tự buffer |
| SSE bị ngắt sau một thời gian | Khoảng thời gian ngắt có thể lặp lại | Response timeout, idle timeout ở ingress/load balancer, giới hạn thời lượng kết nối hoặc lỗi upstream |
| `response already committed` | Lỗi xuất hiện khi filter hoặc error handler cố đổi status/header hay ghi body | Response đã gửi header hoặc một phần dữ liệu; có nhiều nơi cùng ghi response; lỗi xảy ra giữa stream |

Không nên kết luận rằng Gateway là nơi đóng kết nối chỉ vì client kết nối thông qua Gateway. Trước hết, thử gọi trực tiếp service đích từ cùng môi trường mạng và so sánh với request đi qua Gateway. Nếu gọi trực tiếp cũng lỗi, hãy kiểm tra service và hạ tầng phía sau. Nếu chỉ lỗi qua Gateway, tập trung vào route, filter và cấu hình HTTP client của Gateway, sau đó kiểm tra ingress hoặc load balancer phía trước.

## 2. Thu thập bằng chứng từ client

### Kiểm tra SSE

Sử dụng `curl -N` để yêu cầu curl không buffer output. Nếu endpoint yêu cầu token, thêm header xác thực tương ứng:

```bash
curl -iN --http1.1 \
  -H 'Accept: text/event-stream' \
  -H 'Authorization: Bearer <token>' \
  https://gateway.example.com/events
```

Quan sát:

- Status code và thời gian nhận response header.
- `Content-Type` có phải `text/event-stream` hay không.
- Event có đến theo đúng nhịp backend phát hay chỉ xuất hiện sau một khoảng chờ.
- Kết nối đóng ở thời điểm nào và có lặp lại cùng khoảng thời gian hay không.

SSE dùng framing theo dòng. Một event thường kết thúc bằng một dòng trống, ví dụ:

```text
id: 42
event: update
data: trang-thai-moi

```

Nếu backend ghi dữ liệu nhưng không kết thúc event bằng dòng trống hoặc không flush dữ liệu, client có thể tiếp tục chờ dù TCP connection vẫn mở. Vì vậy, cần xác minh cả cách backend tạo event, không chỉ cấu hình Gateway.

### Kiểm tra WebSocket

`curl` không phải công cụ kiểm thử WebSocket đầy đủ. Dùng `wscat`, `websocat` hoặc client WebSocket của ứng dụng:

```bash
wscat -c wss://gateway.example.com/ws
```

Ghi lại handshake có nhận `101 Switching Protocols` hay không, thời gian từ lúc kết nối đến lúc đóng, close code và close reason nếu client cung cấp. Thử cùng một endpoint trực tiếp tại service đích để khoanh vùng.

Handshake thành công chỉ chứng minh quá trình nâng cấp HTTP đã hoàn tất. Nó không chứng minh kết nối sẽ sống lâu, backend vẫn khỏe hoặc proxy sẽ giữ kết nối vô thời hạn.

## 3. Xử lý WebSocket bị ngắt sớm

### Khai báo route bằng scheme WebSocket

Spring Cloud Gateway nhận diện route WebSocket qua scheme `ws` hoặc `wss`. Ví dụ route trực tiếp đến một service:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: ws://chat-service:8080
          predicates:
            - Path=/ws/**
          filters:
            - StripPrefix=1
```

Khi service được tìm qua Spring Cloud LoadBalancer, có thể dùng scheme `lb:ws`:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/**
          filters:
            - StripPrefix=1
```

Chọn một cấu hình phù hợp với cách triển khai thực tế. Nếu backend nhận đường dẫn `/ws/**`, hãy bỏ `StripPrefix=1`; nếu backend chỉ nhận `/`, giữ filter này. Khi dùng `RewritePath`, kiểm tra biểu thức rewrite bằng một request cụ thể để chắc chắn đường dẫn sau biến đổi đúng với endpoint backend.

Các điểm cần kiểm tra:

1. Predicate có khớp đúng path và method handshake không. Một route REST khác có thể bắt request trước route WebSocket nếu điều kiện route quá rộng.
2. URI đích có dùng `ws://`, `wss://` hoặc `lb:ws://` đúng trường hợp không. Dùng `http://` cho route cần nâng cấp WebSocket là cấu hình sai.
3. Filter có vô tình xóa hoặc thay đổi các header handshake như `Upgrade`, `Connection`, `Sec-WebSocket-Key` và `Sec-WebSocket-Protocol` không. Để Gateway xử lý handshake theo cơ chế WebSocket của nó; tránh tự thêm các giá trị header cố định bằng filter nếu chưa có bằng chứng cần thiết.
4. Backend có chấp nhận `Origin`, subprotocol và thông tin xác thực mà client gửi không.
5. Nếu dùng `wss`, chứng chỉ và trust chain phải hợp lệ ở từng chặng TLS. Phân biệt TLS từ client đến ingress với TLS từ Gateway đến backend.

### Phân biệt timeout kết nối và timeout nhàn rỗi

`connect-timeout` giới hạn thời gian thiết lập kết nối đến upstream. Nó không phải cơ chế giữ một WebSocket đang mở. Một kết nối có thể handshake thành công rồi bị đóng bởi idle timeout ở ingress, load balancer, firewall, NAT hoặc backend.

Hãy đối chiếu cấu hình timeout của tất cả các lớp. Nếu kết nối luôn đóng sau khoảng 60 giây, chẳng hạn, tìm cấu hình có giới hạn gần 60 giây ở từng proxy và service thay vì tăng ngẫu nhiên timeout của Gateway. Chọn giới hạn phù hợp với thời gian nhàn rỗi dự kiến và tài nguyên hệ thống.

Với kết nối cần sống lâu, triển khai heartbeat ping/pong hoặc thông điệp keepalive theo giao thức ứng dụng. Heartbeat cần được phát thường xuyên hơn idle timeout ngắn nhất trên đường đi. Xác minh client, backend và proxy có xử lý heartbeat đúng cách; đừng giả định mọi lớp đều tự tạo ping.

Khi client reconnect, cần có chiến lược khôi phục session: định danh phiên, resume token hoặc đồng bộ trạng thái giữa các replica. Sticky session chỉ hữu ích khi ứng dụng thật sự giữ trạng thái cục bộ; nó không thay thế heartbeat và không khắc phục được timeout.

### Xem xét bảo mật sau khi nâng cấp

Các HTTP filter của Gateway xử lý request handshake. Sau khi kết nối đã được nâng cấp, frame WebSocket được chuyển tiếp qua đường xử lý WebSocket; không nên xem `RequestRateLimiter` của Gateway là giới hạn tốc độ cho từng frame hoặc từng message. Nếu cần giới hạn message, kích thước frame, quyền theo từng thao tác hoặc chống spam, hãy thực hiện tại WebSocket service hoặc tầng xử lý message chuyên dụng.

Xác thực handshake trước khi nâng cấp, kiểm tra `Origin` theo chính sách ứng dụng và giới hạn kích thước message ở backend. Không ghi token, cookie nhạy cảm hoặc nội dung riêng tư của frame vào log.

## 4. Xử lý SSE bị dồn bộ đệm

### Giữ response ở chế độ streaming

Backend WebFlux có thể trả về `Flux<ServerSentEvent<T>>` hoặc một publisher tương thích với `text/event-stream`. Ví dụ:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(10))
        .map(sequence -> ServerSentEvent.builder("update-" + sequence)
            .id(Long.toString(sequence))
            .event("update")
            .build());
}
```

Mỗi event phải được serialize đúng định dạng SSE và flush để client nhận được ngay. Với stream có thể im lặng lâu, backend có thể phát comment heartbeat:

```text
: keep-alive

```

Comment không tạo event dữ liệu cho ứng dụng nhưng giúp phát hiện kết nối còn hoạt động và giảm khả năng bị proxy xem là idle. Chọn chu kỳ heartbeat dựa trên idle timeout ngắn nhất trong hạ tầng.

Response nên có `Content-Type: text/event-stream` và chính sách cache phù hợp, thường là `Cache-Control: no-cache` hoặc `no-store` tùy dữ liệu. Nếu phía trước có Nginx, có thể cần `X-Accel-Buffering: no` theo cấu hình Nginx. Đây là header đặc thù của Nginx, không phải chỉ thị chung cho mọi proxy.

Không phụ thuộc vào `Transfer-Encoding: chunked` như một điều kiện bắt buộc. HTTP/1.1 thường truyền stream theo chunk khi không có content length, trong khi HTTP/2 truyền dữ liệu qua DATA frame. Điều cần xác minh là event được chuyển đến client liên tục, không bị giữ lại để gom thành một response lớn.

### Tìm lớp đang buffer

Kiểm tra lần lượt các điểm sau:

- **Backend:** event có được phát và flush đúng nhịp không; có code nào gom publisher thành `List`, `collectList()` hoặc một body hoàn chỉnh trước khi trả về không.
- **Gateway filter:** có `ModifyResponseBody`, response cache, filter tự đọc hết body hoặc logic chuyển toàn bộ `Flux<DataBuffer>` thành một buffer lớn không. Những xử lý này có thể làm mất tính streaming.
- **Compression:** thử tắt compression cho endpoint SSE ở lớp đang nén nếu quan sát cho thấy compressor giữ dữ liệu. Một số cấu hình nén hoặc proxy chỉ đẩy dữ liệu khi đủ kích thước buffer.
- **Ingress/CDN:** kiểm tra response buffering, cache, compression và quy tắc proxy cho `text/event-stream`. Cấu hình tắt buffer phải đặt ở đúng lớp đang thực hiện buffer.
- **Client:** dùng `curl -N` hoặc client SSE có hỗ trợ streaming để loại trừ buffering do công cụ kiểm thử.

Không áp dụng response rewrite, cache hoặc retry một cách máy móc cho stream dài hạn. Khi một phần event đã đến client, retry không thể phát lại trong suốt như thể client chưa nhận dữ liệu. Nếu cần khôi phục sau mất kết nối, thiết kế cơ chế resume bằng event ID và header `Last-Event-ID` ở backend.

### Cấu hình timeout theo route

Một timeout ngắn có thể phù hợp với API đọc dữ liệu thông thường nhưng không phù hợp với response stream tồn tại lâu. Ví dụ dưới đây đặt timeout mặc định cho HTTP client và tắt response timeout toàn cục đối với route SSE bằng metadata của route:

```yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 5000
        response-timeout: 30s
      routes:
        - id: event-stream
          uri: lb://event-service
          predicates:
            - Path=/events/**
          filters:
            - StripPrefix=1
          metadata:
            response-timeout: -1
```

`connect-timeout` ở ví dụ là mili giây. `response-timeout` toàn cục là một duration; metadata `response-timeout` theo route dùng giá trị mili giây, trong đó `-1` vô hiệu hóa response timeout toàn cục cho route theo cơ chế của Spring Cloud Gateway. Hãy xác nhận hành vi này với phiên bản Spring Cloud Gateway đang chạy và kiểm thử sau khi nâng cấp phiên bản.

Vô hiệu hóa response timeout của Gateway không vô hiệu hóa idle timeout của ingress, load balancer, CDN, firewall hoặc backend. Các lớp đó vẫn phải được cấu hình phù hợp và cần heartbeat nếu stream có khoảng im lặng dài. Không đặt timeout vô hạn cho mọi route nếu chỉ một endpoint cần streaming.

## 5. Hiểu đúng lỗi response đã commit

Trong WebFlux, response được xem là committed khi status/header đã được gửi hoặc body bắt đầu được ghi xuống kết nối. Trước thời điểm đó, filter hoặc error handler có thể chọn status và header. Sau khi response đã commit, ứng dụng không thể đổi `200 OK` thành `500 Internal Server Error`, cũng không thể thay phần dữ liệu đã gửi bằng một JSON error body mới.

Tình huống này rất dễ gặp với SSE và response streaming: Gateway đã gửi header `200`, client đã nhận một số event, sau đó backend gặp lỗi hoặc kết nối upstream bị timeout. Error handler chạy tiếp và cố ghi một response JSON khác. Kết quả thường là lỗi `response already committed`, lỗi ghi response hoặc kết nối bị đóng giữa stream.

Các nguyên nhân phổ biến khác:

- Custom `GlobalFilter` ghi body rồi vẫn gọi `chain.filter(exchange)`, khiến hai thành phần cùng cố ghi response.
- Filter đặt status/header sau khi `chain.filter(exchange)` đã hoàn tất hoặc sau khi body đã được flush.
- `onErrorResume` luôn tạo error body mà không kiểm tra response đã commit hay chưa.
- Nhiều nhánh xử lý cùng gọi `writeWith` hoặc `writeAndFlushWith`.
- Một filter biến đổi body tiêu thụ publisher trước, rồi một filter khác tiếp tục đọc publisher đã được tiêu thụ.

### Đăng ký header trước khi response commit

Nếu cần thêm header, đăng ký hành động trước khi gọi filter chain:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpResponse response = exchange.getResponse();
    response.beforeCommit(() -> {
        response.getHeaders().set("X-Gateway-Processed", "true");
        return Mono.empty();
    });
    return chain.filter(exchange);
}
```

Không sửa header trong callback chạy sau khi response đã được gửi. Nếu cần quan sát stream, hãy dùng cách decorate response phù hợp với WebFlux và giữ nguyên đặc tính streaming; tránh chuyển toàn bộ body thành một mảng byte chỉ để đo hoặc log.

### Xử lý lỗi có xét trạng thái committed

Với response thông thường chưa gửi dữ liệu, filter có thể tạo error response. Khi response đã commit, chỉ nên ghi nhận lỗi và kết thúc publisher/kết nối theo đúng vòng đời; không thử gửi status hoặc body thứ hai:

```java
return chain.filter(exchange).onErrorResume(error -> {
    ServerHttpResponse response = exchange.getResponse();

    if (response.isCommitted()) {
        log.warn("Lỗi xảy ra sau khi response đã commit", error);
        return Mono.error(error);
    }

    response.setStatusCode(HttpStatus.BAD_GATEWAY);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
    byte[] body = "{\"error\":\"upstream_failure\"}"
        .getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(body);
    return response.writeWith(Mono.just(buffer));
});
```

Đoạn xử lý này minh họa cho custom filter; cần bổ sung import, logger và điều chỉnh error contract theo ứng dụng. Nó không thể biến một stream đã gửi dở thành response hoàn chỉnh. Với stream, client nên hiểu việc đóng kết nối là tín hiệu mất stream và dùng cơ chế reconnect/resume của giao thức.

## 6. Quy trình khoanh vùng theo thứ tự

Thực hiện các bước sau trên cùng một request ID hoặc cùng một phiên kiểm thử:

1. **Xác định loại kết nối.** Với WebSocket, xác nhận handshake `101` và close code. Với SSE, xác nhận `200`, `Content-Type` và nhịp event. Với lỗi committed, xác định response đã gửi bao nhiêu dữ liệu trước khi lỗi xuất hiện.
2. **Gọi trực tiếp upstream.** Dùng cùng path, header xác thực và payload. Nếu lỗi tái hiện trực tiếp, kiểm tra service trước khi sửa Gateway.
3. **Kiểm tra route.** Xác nhận predicate, URI scheme, load balancing và path sau `StripPrefix`/`RewritePath`.
4. **Rà soát filter.** Tìm filter đọc hết body, sửa response body, cache, retry, fallback hoặc ghi response. Tạm loại bỏ từng filter nghi vấn trong môi trường kiểm thử để xác định tác nhân.
5. **So sánh timeout.** Đối chiếu thời điểm đóng với response timeout, idle timeout, connection lifetime và giới hạn thời lượng ở mọi proxy. Một khoảng thời gian lặp lại là manh mối để tìm cấu hình tương ứng.
6. **Kiểm tra buffering.** So sánh thời điểm backend phát event, Gateway nhận event và client nhận event. Tắt compression/buffering từng lớp trong môi trường kiểm thử để xác định nơi giữ dữ liệu.
7. **Đối chiếu log và metric.** Gắn correlation ID xuyên suốt các hop; ghi nhận route ID, upstream, thời lượng, close/error cause và trạng thái committed. Không ghi token hoặc nội dung nhạy cảm.
8. **Kiểm thử kết nối dài hạn.** Chạy thử lâu hơn idle timeout dự kiến, thử khi không có event trong một khoảng thời gian, thử reconnect và thử khi một replica backend bị restart.

Nếu ứng dụng bật Gateway Actuator metrics, có thể theo dõi metric request của Gateway, thường có tên `spring.cloud.gateway.requests`, cùng metric kết nối và lỗi của Reactor Netty. Tên và tag cụ thể phụ thuộc phiên bản, cấu hình và registry. Chỉ expose endpoint Actuator cần thiết và bảo vệ quyền truy cập.

## 7. Bảng quyết định nhanh

| Kết quả kiểm tra | Hướng xử lý tiếp theo |
|---|---|
| WebSocket không có `101` | Kiểm tra route `ws`/`wss`, predicate, auth, `Origin`, subprotocol và TLS handshake |
| WebSocket có `101`, đóng sau thời gian cố định | Đối chiếu idle timeout ở ingress/LB/firewall/backend; thêm heartbeat phù hợp |
| WebSocket chỉ lỗi khi đi qua Gateway | Rà soát route, header handshake và filter áp dụng cho path đó |
| SSE trực tiếp mượt, qua Gateway bị dồn event | Rà soát filter response, compression và proxy buffering trên đường Gateway |
| SSE cả trực tiếp lẫn qua Gateway đều bị dồn | Kiểm tra cách backend flush event và client kiểm thử |
| SSE đóng theo khoảng thời gian cố định | Đối chiếu response timeout và idle timeout trên từng hop; kiểm tra heartbeat |
| `response already committed` chỉ xuất hiện khi stream lỗi | Không ghi error body thứ hai; ghi log, kết thúc stream và hỗ trợ reconnect/resume |
| `response already committed` xuất hiện cả với REST | Kiểm tra filter có nhiều nơi ghi response hoặc sửa header/status sau khi commit |

## 8. Checklist trước khi đưa vào vận hành

- [ ] Route WebSocket dùng đúng `ws`/`wss` hoặc `lb:ws`, và path sau rewrite khớp endpoint backend.
- [ ] Handshake, xác thực, `Origin`, subprotocol và TLS được kiểm thử qua đúng đường mạng production.
- [ ] Heartbeat WebSocket ngắn hơn idle timeout thấp nhất; client có reconnect và xử lý close code.
- [ ] SSE phát event đúng framing, flush đều và có heartbeat khi cần.
- [ ] Response SSE có content type và cache policy phù hợp; proxy buffering/compression đã được kiểm chứng.
- [ ] Route streaming không đi qua filter gom toàn bộ response body hoặc cache response không phù hợp.
- [ ] Timeout của Gateway, ingress, load balancer, CDN và backend được đối chiếu với thời lượng kết nối dự kiến.
- [ ] Error handler kiểm tra `response.isCommitted()` và không cố ghi response thứ hai.
- [ ] Có correlation ID, metric kết nối và log close/error đủ để tìm đúng hop gây lỗi.
- [ ] Đã thử tải dài hạn, kết nối nhàn rỗi, upstream restart, reconnect và resume SSE bằng event ID.

WebSocket và SSE cần được vận hành như kết nối dài hạn. Khi đã xác định đúng route, giữ được nhịp truyền dữ liệu qua từng proxy và xử lý đúng thời điểm response commit, phần lớn lỗi ngắt sớm, dồn bộ đệm và ghi response trùng có thể được khoanh vùng rõ ràng.
