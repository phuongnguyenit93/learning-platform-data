# So sánh TCP với WebSocket trong cùng điều kiện tải

RSocket có thể chạy trên TCP hoặc WebSocket. Khi so sánh hiệu năng, cần hiểu đây là hai transport của cùng giao thức RSocket: RSocket qua TCP dùng kết nối TCP trực tiếp; RSocket qua WebSocket đóng RSocket frame trong WebSocket binary message, và WebSocket vẫn chạy trên TCP. Vì vậy phép đo thực chất là so sánh chi phí của hai cách vận chuyển RSocket trên cùng nền TCP, không phải so sánh TCP với một giao thức không dùng TCP.

TCP thường có ít lớp đóng gói hơn và phù hợp với giao tiếp service-to-service trong môi trường kiểm soát được. WebSocket thêm framing và handshake HTTP Upgrade, nhưng hỗ trợ trình duyệt, dễ đi qua hạ tầng HTTP và thường thuận tiện hơn ở mạng doanh nghiệp. Chênh lệch hiệu năng thực tế phụ thuộc kích thước payload, tần suất message, TLS, proxy, số kết nối, backpressure và chi phí xử lý nghiệp vụ.

Muốn kết luận transport nào nhanh hơn, phải chạy cùng một ứng dụng RSocket, cùng payload, cùng interaction model, cùng tải và cùng điều kiện mạng. Không thể lấy một lần đo TCP ở LAN so với một lần đo WebSocket qua reverse proxy rồi quy toàn bộ chênh lệch cho transport.

## 1. Phân biệt hai transport

Trong bài này, TCP có nghĩa là RSocket TCP transport; WebSocket có nghĩa là RSocket WebSocket transport. Cả hai đều vận chuyển RSocket frame và hỗ trợ các interaction model của RSocket như request-response, fire-and-forget, request-stream và request-channel.

~~~mermaid
flowchart TD
    APP[Ứng dụng RSocket]
    APP --> FRAME[RSocket frame]
    FRAME --> TCP[RSocket TCP transport]
    FRAME --> WS[RSocket WebSocket transport]
    TCP --> TCPSTACK[TCP socket]
    WS --> WSFRAME[WebSocket binary frame]
    WSFRAME --> TCPSTACK
    TCPSTACK --> NETWORK[Mạng IP]
~~~

| Đặc điểm | RSocket qua TCP | RSocket qua WebSocket |
|---|---|---|
| Lớp vận chuyển | TCP trực tiếp | WebSocket trên TCP |
| Đóng gói | RSocket frame với length prefix của transport | RSocket frame nằm trong WebSocket binary message |
| Thiết lập kết nối | Mở TCP socket, sau đó RSocket SETUP | TCP (và TLS nếu dùng WSS), HTTP Upgrade, sau đó RSocket SETUP |
| Overhead mỗi frame | RSocket framing và TCP/IP | RSocket framing, WebSocket framing và TCP/IP |
| Browser | Trình duyệt web không cung cấp raw TCP socket API cho JavaScript | Có API WebSocket tích hợp |
| Proxy/hạ tầng HTTP | Cần cho phép cổng TCP tương ứng | Thường tận dụng reverse proxy và cổng HTTPS |
| Trường hợp phổ biến | Service-to-service, ứng dụng JVM/native | Browser-to-service, ứng dụng cần tương thích hạ tầng Web |

WebSocket không thay thế TCP ở tầng mạng. Nó bổ sung quy tắc message framing và handshake trên kết nối TCP. Khi RSocket chạy qua WebSocket, các interaction semantics của RSocket vẫn được giữ nguyên; transport chỉ thay đổi cách frame đi qua mạng.

## 2. Overhead của framing và handshake

RSocket TCP transport dùng length prefix 3 byte để phân định frame trên TCP byte stream. WebSocket cũng cần header cho mỗi message. Header WebSocket có 2 byte cơ bản; payload từ 126 đến 65.535 byte cần thêm 2 byte độ dài, còn payload từ 65.536 byte cần thêm 8 byte độ dài. Frame do client gửi lên server phải có masking key 4 byte theo WebSocket protocol; frame server gửi xuống client không cần mask.

Nếu mỗi RSocket frame tương ứng một WebSocket binary message, overhead framing có thể ước tính như sau:

| Payload của WebSocket message | WebSocket client → server | WebSocket server → client | RSocket TCP |
|---|---:|---:|---:|
| 0–125 byte | 6 byte | 2 byte | 3 byte mỗi frame |
| 126–65.535 byte | 8 byte | 4 byte | 3 byte mỗi frame |
| Từ 65.536 byte | 14 byte | 10 byte | 3 byte mỗi frame |

Với một request-response gồm một frame nhỏ theo mỗi chiều, phần framing WebSocket tăng khoảng 2 byte so với hai length prefix TCP; ở nhóm payload trung bình tăng khoảng 6 byte và ở nhóm rất lớn tăng khoảng 18 byte. Đây chỉ là phép tính header, chưa gồm TLS, TCP/IP, batching, fragmentation hoặc chi tiết implementation. Với luồng chỉ phát từ server về client, WebSocket frame không có masking key nên chênh lệch khác với chiều client-to-server.

Tỷ lệ overhead dễ thấy hơn khi payload rất nhỏ và message được gửi với tần suất cao. Khi payload lớn, số byte framing chiếm tỷ lệ nhỏ hơn tổng dữ liệu.

WebSocket còn có HTTP Upgrade handshake khi thiết lập kết nối. Đây là chi phí khởi tạo, không phải header HTTP được gửi lại cho từng RSocket payload. Khi đo steady-state throughput hoặc latency của message sau khi kết nối đã mở, không được cộng lại toàn bộ chi phí Upgrade cho mỗi request.

Nếu dùng WSS, TLS handshake và mã hóa cũng phát sinh chi phí. TCP có thể chạy plain TCP hoặc TCP được bảo vệ bằng TLS; so sánh công bằng cần đặt hai bên trong cùng chế độ bảo mật:

- Plain TCP so với WebSocket không TLS chỉ phù hợp cho phép đo nội bộ trong môi trường kiểm soát.
- TCP/TLS so với WSS là phép so sánh phù hợp hơn cho triển khai production có mã hóa.
- Không so sánh TCP plain với WSS rồi kết luận WebSocket chậm chỉ vì chi phí TLS.

## 3. Những yếu tố quyết định kết quả

Overhead transport chỉ là một phần của tổng thời gian xử lý. Các yếu tố sau có thể lớn hơn chênh lệch framing:

- **Payload size:** message vài chục byte nhạy với overhead framing hơn message hàng trăm kilobyte.
- **Message rate:** số message mỗi giây càng cao thì chi phí encode, decode, callback và scheduling càng đáng kể.
- **TLS:** mã hóa, giải mã, session resumption và cấu hình cipher ảnh hưởng CPU và latency.
- **Proxy/load balancer:** WebSocket đi qua reverse proxy có thể thêm hop, buffering, timeout và giới hạn connection.
- **Số kết nối đồng thời:** ảnh hưởng bộ nhớ socket, event loop, keepalive và scheduler.
- **Backpressure:** demand khác nhau làm số payload được gửi và hàng đợi khác nhau.
- **Interaction model:** request-response đo round-trip; request-stream và channel còn có chi phí duy trì stream và điều tiết hai chiều.
- **Serialization và nghiệp vụ:** JSON/CBOR, codec, database hoặc xử lý business có thể che khuất chênh lệch transport.

Do đó, không có một tỷ lệ cố định để nói WebSocket chậm hơn TCP bao nhiêu phần trăm. Cần đo trên topology và workload mà hệ thống thực sự sử dụng.

## 4. Thiết kế phép thử công bằng

Mục tiêu là thay đổi duy nhất transport, giữ nguyên các yếu tố còn lại. Dùng cùng mã handler, DTO, codec, route, logic xử lý và cấu hình RSocket ở cả hai lượt thử.

| Yếu tố | Điều kiện cần giữ giống nhau |
|---|---|
| Ứng dụng server | Cùng phiên bản binary, handler và cấu hình JVM |
| Client/load generator | Cùng máy hoặc cùng nhóm máy, cùng phiên bản thư viện |
| RSocket | Cùng version, MIME type, route và interaction model |
| Payload | Cùng dữ liệu, kích thước, schema và thứ tự |
| Serialization | Cùng codec và cấu hình compression |
| Tải | Cùng số client, concurrency, request rate và demand |
| Network | Cùng vùng mạng, RTT, băng thông và packet loss |
| Security | Cùng chính sách TLS, certificate và cipher khi so sánh production |
| Runtime | Cùng CPU/memory limit, JVM flags, GC và socket options |
| Đo lường | Cùng cách ghi latency, throughput, error và tài nguyên |

Nếu WebSocket đi qua reverse proxy còn TCP kết nối trực tiếp, hãy coi đó là hai topology triển khai khác nhau. Có thể đo cả hai vì đó là đường đi production, nhưng phải ghi rõ proxy là một biến bổ sung, không quy toàn bộ khác biệt cho framing WebSocket.

## 5. Chạy cùng handler trên hai transport

Một cách dễ kiểm soát là đóng gói cùng ứng dụng server thành hai profile hoặc hai instance. Cả hai instance dùng cùng handler và service; chỉ thay transport, port và endpoint.

Ví dụ cấu hình TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Ví dụ cấu hình WebSocket:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      port: 8080
      mapping-path: /rsocket
~~~

Các thuộc tính trên minh họa cấu hình Spring Boot; cần xác nhận tên thuộc tính và hỗ trợ transport theo phiên bản Spring Boot đang dùng. Chạy từng profile trong điều kiện tài nguyên tương đương. Nếu chạy đồng thời trên cùng host, tránh để hai instance tranh CPU hoặc bộ nhớ làm sai kết quả; có thể chạy tuần tự hoặc dùng hai môi trường được cân bằng cấu hình.

Client chỉ thay endpoint kết nối. Với các phiên bản Spring Framework có API connectTcp và connectWebSocket, có thể tạo hai requester như sau:

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

Mono<RSocketRequester> tcpRequester =
    RSocketRequester.builder()
        .connectTcp("benchmark.internal", 7000);

Mono<RSocketRequester> websocketRequester =
    RSocketRequester.builder()
        .connectWebSocket(
            URI.create("wss://benchmark.internal/rsocket")
        );
~~~

API kết nối có thể khác giữa các phiên bản Spring Framework; hãy dùng phương thức tương ứng trong phiên bản dự án. Điều cần giữ nguyên là requester sau khi kết nối phải gọi cùng route và cùng payload.

## 6. Dùng cùng interaction model

Không nên benchmark TCP bằng request-response nhưng benchmark WebSocket bằng request-stream. Hai interaction model có đặc điểm tải và chi phí khác nhau.

| Interaction | Chỉ số chính | Điều cần giữ giống nhau |
|---|---|---|
| Request-response | Round-trip latency, successful requests/s | Cùng payload request/response và cùng xử lý server |
| Fire-and-forget | Payload gửi/s, payload xử lý/s, backlog và lỗi | Cùng tốc độ phát và cách xác nhận phía server |
| Request-stream | Thời gian tới event đầu tiên, event/s, inter-arrival latency | Cùng tốc độ nguồn, demand và thời lượng stream |
| Request-channel | Throughput hai chiều, latency response, backlog | Cùng publisher hai phía, demand và concurrency |

Fire-and-forget không có response payload để đo round-trip latency. Nếu cần biết server đã xử lý tới đâu, hãy dùng metric/counter phía server hoặc thiết kế một phép thử riêng có acknowledgment. Không suy ra số message được xử lý chỉ từ số lần client gọi API gửi.

Với request-stream và request-channel, giữ nguyên request(n) hoặc batch demand. Nếu một bên yêu cầu 1.000 phần tử mỗi lần còn bên kia chỉ yêu cầu 1 phần tử, phép đo sẽ phản ánh khác biệt backpressure chứ không còn chỉ phản ánh transport.

## 7. Ma trận payload và concurrency

Một payload size duy nhất không đủ để đánh giá transport. Nên thử nhiều nhóm kích thước:

| Nhóm | Kích thước gợi ý | Điều muốn quan sát |
|---|---:|---|
| Rất nhỏ | 32–128 byte | Framing, scheduling và chi phí mỗi message |
| Nhỏ | 256 byte–1 KiB | Workload event hoặc command ngắn |
| Trung bình | 4–16 KiB | Payload nghiệp vụ thông thường |
| Lớn | 64–256 KiB | Throughput, copy buffer và fragmentation |
| Rất lớn | 512 KiB–1 MiB | Buffering, memory pressure và giới hạn frame |

Các kích thước chỉ là điểm bắt đầu. Cần chọn theo payload thật và giới hạn frame của hệ thống. Nếu RSocket fragmentation được bật, giữ cùng fragment size và chính sách fragmentation ở cả hai transport.

Tăng tải theo các bậc có kiểm soát, chẳng hạn 50, 100, 250 rồi 500 kết nối đồng thời, hoặc chọn mức phù hợp với giới hạn của môi trường. Ở mỗi bậc, giữ cùng request rate hoặc concurrency và chạy đủ lâu để đo steady-state. Không so một transport ở tải thấp với transport kia ở sát ngưỡng bão hòa.

## 8. Quy trình benchmark theo từng lượt

Một lượt đo nên có các pha tách biệt:

1. **Khởi động:** start server, chờ health check và tạo kết nối.
2. **Warm-up:** gửi tải đại diện để JIT, class loading, connection pool và cache ổn định.
3. **Steady-state:** phát tải theo profile cố định và thu thập số liệu.
4. **Cooldown:** ngừng tải, chờ queue và resource ổn định.
5. **Lặp lại:** chạy nhiều lần và đổi thứ tự TCP/WebSocket để giảm ảnh hưởng do nhiệt độ CPU, cache hoặc tải nền.

Đo thời gian thiết lập kết nối riêng với latency của request sau khi kết nối đã mở. Đối với WebSocket, ghi nhận TCP connect, TLS handshake (nếu có), HTTP Upgrade và RSocket SETUP. Đối với TCP, ghi nhận TCP connect, TLS handshake (nếu có) và RSocket SETUP.

Nếu mục tiêu là đo steady-state, loại bỏ thời gian warm-up và setup khỏi thống kê request latency. Nếu mục tiêu là trải nghiệm mở màn hình hoặc reconnect, báo cáo riêng thời gian cold start và reconnect.

## 9. Các chỉ số phải thu thập

| Chỉ số | Cách hiểu | Ý nghĩa |
|---|---|---|
| p50 latency | Phân vị 50 của round trip | Trải nghiệm điển hình |
| p95 latency | Phân vị 95 | Độ trễ ở phần lớn request |
| p99 latency | Phân vị 99 | Tail latency khi tải cao |
| Throughput | Request hoặc payload xử lý thành công mỗi giây | Năng lực xử lý |
| Error/timeout rate | Tỷ lệ lỗi và timeout | Độ ổn định ở mức tải |
| CPU | CPU server và client | Chi phí xử lý transport và application |
| Heap/direct memory | Bộ nhớ heap và off-heap | Áp lực buffer và connection |
| GC pause | Số lần và thời gian pause | Ảnh hưởng tới tail latency |
| Network bytes | Byte gửi/nhận và bytes trên mỗi payload | Overhead vận chuyển |
| Connection setup | Thời gian mở phiên hoàn chỉnh | Chi phí cold start |
| Reconnect time | Thời gian phục hồi sau mất kết nối | Độ bền khi có sự cố |
| Backlog/queue | Số message chờ xử lý | Dấu hiệu consumer không theo kịp |

Đo latency bằng đồng hồ monotonic trong cùng tiến trình load generator, ví dụ System.nanoTime() để tính round-trip duration. Không gửi giá trị nanoTime qua mạng hoặc so timestamp monotonic giữa hai máy. Nếu đo one-way latency, cần đồng bộ clock và ghi nhận sai số đồng hồ.

## 10. Ghi latency bằng Micrometer

Có thể gắn Timer vào cùng phương thức gọi request-response để ghi nhận round-trip latency. Timer và cách lấy percentile phải được cấu hình giống nhau cho hai requester:

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public Mono<BenchReply> measureRequestResponse(
    RSocketRequester requester,
    BenchRequest request,
    Timer latencyTimer
) {
    return Mono.defer(() -> {
        long startedAt = System.nanoTime();

        return requester.route("benchmark.request-response")
            .data(request)
            .retrieveMono(BenchReply.class)
            .doFinally(signal -> latencyTimer.record(
                System.nanoTime() - startedAt,
                TimeUnit.NANOSECONDS
            ));
    });
}
~~~

Đây là phép đo latency ở phía client, bao gồm thời gian gửi request, xử lý server và nhận response. Nó không tách riêng thời gian transport khỏi thời gian xử lý nghiệp vụ. Muốn phân tích sâu hơn, cần span/metric phía server và tracing instrumentation.

Chỉ ghi Timer khi một subscription thực sự chạy; Mono.defer bảo đảm thời điểm bắt đầu được lấy cho từng subscription. Cần phân biệt success, error, timeout và cancellation bằng counter hoặc tag có cardinality thấp. Không dùng request ID làm metric tag.

## 11. Tránh benchmark bị sai lệch

Các lỗi thường làm kết quả không thể so sánh:

- **Khác payload:** JSON ở một bên, binary ở bên kia làm thay đổi serialization và kích thước.
- **Khác tải:** số client, concurrency hoặc request rate không giống nhau.
- **Khác TLS:** một bên mã hóa, bên kia không mã hóa.
- **Khác topology:** WebSocket qua proxy nhưng TCP đi trực tiếp.
- **Không warm-up:** đo thời gian JIT hoặc class loading như thể đó là chi phí transport.
- **Chỉ nhìn average:** trung bình có thể che p99 tăng mạnh.
- **Closed-loop không kiểm soát:** client gửi request tiếp theo sau khi request trước hoàn tất; khi server chậm, tốc độ phát tự giảm và có thể che hiện tượng quá tải (coordinated omission).
- **Load generator quá yếu:** CPU hoặc event loop phía client bão hòa trước server.
- **Chỉ đo phía client:** không biết server đã xử lý hết fire-and-forget hay còn backlog.
- **Chạy hai lượt trong điều kiện nền khác nhau:** cache, CPU frequency và workload khác làm sai kết quả.

Nếu muốn đánh giá khả năng chịu tải ở mức arrival rate cố định, dùng load generator có thể phát theo lịch độc lập với response và ghi nhận cả request bị trễ. Nếu dùng concurrency-based load, báo rõ đây là closed-loop test và không diễn giải kết quả như arrival-rate benchmark.

## 12. Đọc kết quả theo loại workload

Không có kết quả benchmark chung đúng cho mọi hệ thống. Có thể diễn giải theo các mẫu sau:

| Quan sát | Cách hiểu có thể có | Việc cần kiểm tra |
|---|---|---|
| TCP tốt hơn rõ ở payload nhỏ, message rate cao | WebSocket framing và xử lý message tạo overhead tương đối lớn hơn | Byte/message, CPU client/server, số message/s |
| Chênh lệch rất nhỏ ở payload lớn | Chi phí payload và mạng chiếm phần lớn | Network throughput, copy buffer, fragmentation |
| WebSocket chậm hơn nhiều chỉ khi qua proxy | Proxy, TLS termination hoặc buffering có thể là yếu tố chính | Đo WebSocket trực tiếp và qua proxy riêng |
| p50 gần nhau nhưng p99 WebSocket cao | Tail latency có thể do event loop, proxy, queue hoặc GC | Queue depth, scheduler, GC và proxy metrics |
| Throughput tương đương nhưng CPU WebSocket cao hơn | Framing/masking hoặc implementation path có chi phí CPU | CPU profile, bytes/frame, allocation |
| TCP setup nhanh hơn nhưng steady-state tương đương | Khác biệt nằm chủ yếu ở thiết lập transport | Đo connect, TLS, Upgrade và SETUP riêng |

Các diễn giải trên là giả thuyết để điều tra, không phải kết luận tự động. Chỉ số cần được đối chiếu với CPU profile, network counters và topology thực tế.

## 13. Ví dụ bảng báo cáo kết quả

Không điền số liệu minh họa như thể đó là kết quả thật. Sau khi chạy benchmark, ghi dữ liệu đo được theo cùng một mẫu:

| Transport | Payload | Concurrency | Throughput | p50 | p95 | p99 | CPU server | Error rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RSocket TCP | 128 B | ... | ... | ... | ... | ... | ... | ... |
| RSocket WebSocket | 128 B | ... | ... | ... | ... | ... | ... | ... |
| RSocket TCP | 4 KiB | ... | ... | ... | ... | ... | ... | ... |
| RSocket WebSocket | 4 KiB | ... | ... | ... | ... | ... | ... | ... |
| RSocket TCP | 64 KiB | ... | ... | ... | ... | ... | ... | ... |
| RSocket WebSocket | 64 KiB | ... | ... | ... | ... | ... | ... | ... |

Mỗi báo cáo cần ghi thêm:

- Phiên bản RSocket, Spring, Netty, JVM và hệ điều hành.
- CPU, RAM, container quota và vị trí client/server.
- TLS, cipher, certificate, proxy và compression.
- Warm-up duration, measurement duration và số lần lặp.
- Interaction model, payload schema, codec, fragmentation và demand.
- Cách tạo tải: fixed arrival rate hay concurrency-based.
- Số lỗi, timeout, reconnect và backlog trong từng lượt.

So sánh chênh lệch phần trăm chỉ sau khi có nhiều lượt chạy ổn định. Nên báo cáo median giữa các lần chạy và khoảng biến thiên; không chọn riêng lượt tốt nhất.

## 14. Chọn TCP hay WebSocket cho RSocket

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Service-to-service trong mạng nội bộ, kiểm soát cổng và client | TCP | Ít lớp framing hơn, đường đi trực tiếp |
| Ứng dụng JavaScript chạy trong browser | WebSocket | Browser có WebSocket API; không có raw TCP socket API thông thường |
| Môi trường chỉ cho phép lưu lượng qua HTTPS/reverse proxy | WebSocket/WSS | Dễ tích hợp với hạ tầng web đã có |
| Kết nối native qua mạng nội bộ có chính sách riêng | TCP hoặc TCP/TLS | Có thể tối ưu trực tiếp socket và mạng |
| Cần benchmark đường đi thực tế qua proxy | WebSocket | Đo được cả chi phí transport và hạ tầng triển khai |

Nếu một hệ thống có cả browser client và service JVM, có thể dùng WebSocket cho browser và TCP cho service-to-service. Hai nhóm client vẫn dùng cùng route contract và message schema; cần bảo đảm server expose đúng endpoint và chính sách bảo mật cho từng transport.

Không chọn WebSocket chỉ vì nó dùng cổng HTTPS, cũng không chọn TCP chỉ vì benchmark local nhanh hơn. Quyết định cần cân bằng latency, throughput, CPU, khả năng đi qua mạng, hỗ trợ client, TLS, vận hành và chi phí kết nối.

## 15. Checklist trước khi công bố kết quả

Trước khi kết luận TCP hay WebSocket phù hợp hơn, xác nhận:

- Hai lượt thử dùng cùng handler, route, DTO, codec và interaction model.
- Payload size, concurrency, arrival rate và demand giống nhau.
- TLS được bật/tắt giống nhau; WSS được so với TCP/TLS khi đánh giá production.
- Đã tách thời gian connection setup khỏi steady-state latency.
- Đã đo p50, p95, p99, throughput, error rate và CPU.
- Đã kiểm tra bộ nhớ, GC, network bytes và backlog.
- Load generator không phải bottleneck.
- Đã chạy nhiều lần, đổi thứ tự transport và ghi điều kiện môi trường.
- Proxy và network path được ghi rõ.
- Không biến một kết quả local thành kết luận cho mọi deployment.

## 16. Kết luận

RSocket TCP transport thường có đường vận chuyển đơn giản hơn vì không cần WebSocket framing. RSocket WebSocket transport thêm binary frame header, masking ở chiều client-to-server và HTTP Upgrade khi mở kết nối, nhưng vẫn chạy trên TCP và đem lại khả năng tương thích với trình duyệt cùng hạ tầng web.

Khác biệt steady-state thường dễ quan sát hơn với payload nhỏ và message rate cao; với payload lớn hoặc workload bị chi phối bởi xử lý nghiệp vụ, chênh lệch có thể nhỏ. TLS, proxy, backpressure, số kết nối và cấu hình runtime có thể thay đổi kết quả đáng kể.

Hãy giữ mọi yếu tố giống nhau và thay đổi riêng transport. Đo setup riêng, warm-up trước khi đo, dùng cùng tải và báo cáo percentile cùng throughput, CPU, memory và error rate. Chỉ dữ liệu thu được từ môi trường triển khai mục tiêu mới đủ cơ sở để chọn TCP hay WebSocket cho hệ thống RSocket.
