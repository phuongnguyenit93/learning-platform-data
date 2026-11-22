# HTTP/2, multiplexing và các nút thắt không được giao thức tự giải quyết

Trong một ứng dụng REST, trình duyệt có thể đồng thời tải danh sách sản phẩm, thông tin người dùng, ảnh và nhiều tài nguyên khác. HTTP/2 giúp trao đổi các yêu cầu đó hiệu quả hơn trên đường truyền, nhưng không làm truy vấn SQL nhanh hơn, không mở rộng connection pool và cũng không loại bỏ mọi hiện tượng *head-of-line blocking*. Phân biệt lợi ích của giao thức với giới hạn của toàn hệ thống là điều cần thiết khi tối ưu API Java/Spring.

Sau bài này, bạn có thể:

- Giải thích **connection, stream, frame, multiplexing, HPACK và flow control** trong HTTP/2.
- Chỉ ra điều HTTP/2 cải thiện so với HTTP/1.1 và những giới hạn vẫn tồn tại ở TCP, máy chủ, proxy và dịch vụ phụ thuộc.
- Bật, xác minh HTTP/2 tại điểm kết thúc TLS; sử dụng Java `HttpClient` để quan sát phiên bản giao thức đã thương lượng.
- Thiết kế phép đo nhằm phân biệt nút thắt đường truyền với nút thắt ứng dụng, cơ sở dữ liệu hoặc hệ thống phía sau.

## 1. HTTP/2 thay đổi cách truyền HTTP như thế nào?

HTTP/2 giữ nguyên phần lớn **ngữ nghĩa HTTP**: `GET`, `POST`, URI, mã trạng thái, cache, xác thực, phân quyền và tính idempotent vẫn có ý nghĩa như trước. Điểm khác biệt chính là cách **đóng khung và vận chuyển** request/response. Thay vì biểu diễn thông điệp HTTP/1.1 dưới dạng các dòng văn bản trên kết nối, HTTP/2 dùng các **frame nhị phân** thuộc các **stream** có định danh riêng.

| Khái niệm | Vai trò trong HTTP/2 | Cần nhớ |
| --- | --- | --- |
| Connection | Một kết nối HTTP/2, thông thường chạy trên một kết nối TCP; trên Internet thường có TLS | Nhiều stream có thể chia sẻ cùng kết nối |
| Stream | Luồng hai chiều, độc lập về mặt logic, chứa một trao đổi request/response | Một stream được nhận diện bởi stream ID; các frame của các stream khác nhau có thể xen kẽ |
| Frame | Đơn vị truyền trên connection, chẳng hạn `HEADERS`, `DATA`, `SETTINGS`, `WINDOW_UPDATE`, `RST_STREAM` | Frame được gắn với stream hoặc với cả connection tùy loại |
| Multiplexing | Xen kẽ frame của nhiều stream trên cùng connection | Không phải đợi **toàn bộ response trước** xong mới truyền response sau |
| HPACK | Nén tập header HTTP, có thể tận dụng bảng động theo connection | Giảm chi phí header lặp; không nén nội dung body |
| Flow control | Giới hạn lượng `DATA` được gửi khi phía nhận chưa cấp thêm cửa sổ | Có cửa sổ theo stream và theo connection; có thể tạo điểm chờ |

Ví dụ, hai yêu cầu đến `/v1/products/42` và `/v1/cart` có thể diễn ra như sau:

```text
Một kết nối TLS/TCP (HTTP/2)
Client                                                 Server
  |---- HEADERS [stream 1: GET /v1/products/42] ------->|
  |---- HEADERS [stream 3: GET /v1/cart] -------------->|
  |<--- HEADERS [stream 3: 200] -------------------------|
  |<--- DATA    [stream 3: phần dữ liệu] ----------------|
  |<--- HEADERS [stream 1: 200] -------------------------|
  |<--- DATA    [stream 1: phần 1] ----------------------|
  |<--- DATA    [stream 1: phần 2, END_STREAM] ----------|
  |<--- DATA    [stream 3: kết thúc, END_STREAM] --------|
```

Đây là **minh họa thứ tự các frame**, không phải cú pháp frame trên dây. Mỗi stream vẫn tuân thủ thứ tự logic của chính nó. Trên HTTP/2, các trường đặc biệt như `:method`, `:scheme`, `:authority` và `:path` biểu diễn thông tin request; `:status` biểu diễn mã trạng thái trong response. Chúng không làm thay đổi ý nghĩa của endpoint REST.

### HTTP/1.1 và HTTP/2 khác nhau ở đâu?

| Góc nhìn | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Nhiều request đồng thời | Client thường dùng nhiều kết nối TCP; pipelining ít được sử dụng trong thực tế | Multiplex nhiều stream trên một kết nối HTTP/2 |
| Biểu diễn thông điệp | Dạng văn bản với dòng bắt đầu và header | Frame nhị phân; giữ ngữ nghĩa HTTP |
| Header | Lặp lại header trên nhiều request nếu không có cơ chế khác | HPACK giúp giảm kích thước header trùng lặp |
| Chặn vì thứ tự truyền | Có thể gặp chờ response trong một kết nối HTTP/1.1 | Loại bỏ việc phải tuần tự hóa *các response HTTP* trong cùng một kết nối, nhưng vẫn có thể bị chặn ở tầng TCP |
| Tắc nghẽn phía server | Vẫn xảy ra | Vẫn xảy ra |

HTTP/2 có thể tiết kiệm số kết nối và chi phí thiết lập kết nối trong nhiều tình huống. Tuy nhiên, số connection thực tế phụ thuộc trình duyệt/client, origin, cấu hình proxy và khả năng tái sử dụng connection; **không có quy tắc rằng toàn bộ ứng dụng luôn chỉ dùng đúng một TCP connection**.

## 2. Multiplexing giúp gì và không giúp gì?

Giả sử trang web cần 24 tài nguyên nhỏ từ cùng một origin. Với HTTP/1.1, trình duyệt thường phải phân phối các yêu cầu qua một số kết nối hoặc xếp hàng đợi. Với HTTP/2, client có thể mở nhiều stream và gửi chúng gần như đồng thời trên một kết nối đã thiết lập. Lợi ích dễ thấy hơn khi **RTT cao, nhiều request nhỏ và header lặp lại**.

Nhưng các stream cùng chia sẻ băng thông, trạng thái tắc nghẽn và năng lực xử lý. Thời gian phản hồi của API vẫn có thể được mô tả sơ bộ như sau:

```text
Độ trễ người dùng quan sát
  = thời gian chờ ở client/proxy
  + truyền mạng, TLS và giao thức
  + thời gian chờ hàng đợi ở server
  + xử lý nghiệp vụ và dịch vụ phụ thuộc
  + truyền response về client
```

HTTP/2 chủ yếu tác động đến một phần chi phí **giao tiếp**. Nếu truy vấn cơ sở dữ liệu mất 800 ms, việc truyền request bằng HTTP/2 không tự biến truy vấn đó thành 20 ms. Ngược lại, nếu hàng chục request nhỏ bị giới hạn bởi số kết nối và RTT, multiplexing có thể mang lại cải thiện đáng kể.

Một vài điểm dễ hiểu sai:

- **Multiplexing không đồng nghĩa với thực thi song song vô hạn.** Server có giới hạn stream, thread, CPU, RAM, hàng đợi và tài nguyên downstream.
- **Ưu tiên stream không bảo đảm thứ tự hoàn thành.** Các tín hiệu ưu tiên và cách lập lịch phụ thuộc mức hỗ trợ của client, proxy và server; không nên dùng chúng làm điều kiện đúng/sai của nghiệp vụ.
- **HTTP/2 không tự tối ưu kích thước payload.** Cần phân trang, chọn trường cần thiết, nén body thích hợp, cache bằng `ETag`/`Cache-Control` và hạn chế gọi dư thừa.
- **HTTP/2 server push không nên được xem là chiến lược tối ưu mặc định.** Hỗ trợ ở client, đặc biệt trình duyệt hiện đại, bị hạn chế; đo đạc và dùng cache/preload thích hợp sẽ thực tế hơn.

## 3. Các nút thắt HTTP/2 không tự giải quyết

### 3.1. Head-of-line blocking ở tầng TCP

HTTP/2 chạy trên luồng byte TCP đáng tin cậy, có thứ tự. Khi một segment TCP bị mất, các byte đến sau thường phải đợi segment thiếu được truyền lại trước khi ứng dụng nhận được luồng dữ liệu đúng thứ tự. Vì nhiều HTTP/2 stream cùng nằm trong luồng byte này, **mất gói trên một TCP connection có thể ảnh hưởng mọi stream đang dùng connection đó**, dù các frame của chúng được xen kẽ.

```text
HTTP/2 streams:   A1  B1  A2  B2  A3  B3
TCP byte stream:  [A1][B1][A2][B2][A3][B3]
                         X  mất một segment
Ứng dụng nhận:    các byte đến sau vị trí mất phải chờ truyền lại
```

Đây là *TCP-level head-of-line blocking*, khác với việc response HTTP/1.1 phải chờ nhau vì cùng một kết nối. HTTP/3 trên QUIC hỗ trợ các stream vận chuyển độc lập để giảm kiểu chặn chéo do mất gói này, nhưng **không loại bỏ tắc nghẽn mạng, giới hạn băng thông hay tải backend**.

### 3.2. Giới hạn số stream và flow control

Server hoặc peer có thể công bố `SETTINGS_MAX_CONCURRENT_STREAMS` để giới hạn stream đồng thời. Nếu nhu cầu vượt giới hạn, client phải chờ hoặc điều phối lại; không thể tăng thông lượng bằng cách mở stream vô hạn. Mở thêm connection cũng không phải cách mặc định để vượt qua giới hạn, vì có thể làm tăng áp lực và đi ngược chính sách tải của server.

HTTP/2 còn có **flow control** đối với `DATA` ở hai mức: cửa sổ theo stream và cửa sổ theo connection. Bên nhận phát `WINDOW_UPDATE` khi có thể nhận thêm dữ liệu. Nếu phía nhận đọc chậm hoặc cửa sổ bị sử dụng hết, sender phải tạm dừng dữ liệu tương ứng. Điều này giúp tránh tràn bộ đệm nhưng có thể làm throughput giảm; các response lớn hoặc stream dài có thể cạnh tranh tài nguyên với response nhỏ. Frame điều khiển và header không bị điều tiết theo cách giống `DATA`.

Tình huống: một endpoint trả file JSON rất lớn trong khi nhiều request nhỏ cùng dùng connection. Nếu client xử lý body chậm và ứng dụng/server tạo nhiều dữ liệu hơn khả năng tiêu thụ, bạn cần quan sát **backpressure, bộ đệm, cửa sổ nhận, mức sử dụng memory và tốc độ đọc body**, thay vì chỉ tăng số stream.

### 3.3. CPU, thread pool và connection pool

HTTP/2 cho phép nhiều yêu cầu **đến** đồng thời, nhưng Spring MVC vẫn cần tài nguyên để xử lý chúng. Ví dụ service nhận 100 request đang hoạt động, trong khi HikariCP chỉ có 10 kết nối database. Nếu mỗi request cần giữ kết nối DB, nhiều request phải chờ pool; lúc này độ trễ p95/p99 có thể tăng dù kết nối client đã là HTTP/2.

Những giới hạn thường gặp gồm:

- Truy vấn chậm, N+1 query, thiếu index, lock và số kết nối DB không đủ.
- Hàng đợi executor, thread bị block vì I/O đồng bộ, CPU bão hòa, garbage collection.
- Gọi fan-out nhiều service, retry thiếu kiểm soát, timeout quá dài làm request tích tụ.
- Rate limit, queue hoặc connection pool ở API gateway, reverse proxy và hệ thống phía sau.

Theo định luật Little ở trạng thái ổn định, mức request đang xử lý trung bình xấp xỉ `throughput × response time`. Ví dụ ở 200 request/giây và thời gian ở hệ thống trung bình 0,25 giây, có khoảng **50 request đồng thời** trong hệ thống đó. Nếu thời gian chờ DB tăng, số request tích tụ sẽ tăng theo dù HTTP/2 vẫn truyền frame tốt. Đây là quan hệ để **ước lượng năng lực hệ thống**, không phải công thức dự báo chính xác p99.

### 3.4. Mạng, proxy và giới hạn vận hành

Multiplexing không tăng tốc đường truyền vật lý: bandwidth thấp, RTT cao, packet loss, congestion control, TLS handshake khi phải mở connection mới và payload quá lớn vẫn chi phối hiệu năng. Một kết nối chia sẻ cũng có thể khiến các luồng cạnh tranh cùng congestion window.

Trong kiến trúc thực tế, **đường đi có thể dùng nhiều phiên bản HTTP**:

```text
Browser --(HTTP/2, TLS)--> CDN / API Gateway
                               |
                               +--(HTTP/1.1 hoặc HTTP/2)--> Spring API
                                                               |
                                                               +--> DB / cache / dịch vụ khác
```

Thấy `h2` trong DevTools chỉ chứng minh chặng browser đến điểm kết thúc kết nối đó đã dùng HTTP/2. Nó **không chứng minh** gateway đang nói HTTP/2 với backend. Cần kiểm tra riêng các chặng upstream, cấu hình connection reuse, timeout và giới hạn đồng thời. Khi bảo trì, `GOAWAY` giúp thông báo ngừng nhận stream mới trên connection cũ để phục vụ thoát kết nối có kiểm soát; client vẫn cần chính sách retry phù hợp với tính an toàn và idempotency của request.

## 4. Bật HTTP/2 với Java/Spring và kiểm tra điều thực sự chạy

### 4.1. Spring Boot phía server

Với Spring Boot và web server nhúng hỗ trợ HTTP/2, cấu hình cơ bản:

```yaml
# application.yml
server:
  http2:
    enabled: true
```

Ở môi trường trình duyệt và production, HTTP/2 thường được thương lượng qua **HTTPS/TLS với ALPN** (`h2`). Vì vậy điểm chấm dứt TLS cần chứng chỉ hợp lệ và hỗ trợ HTTP/2. Nếu TLS kết thúc tại load balancer hoặc API gateway, phải bật HTTP/2 **tại đó** và kiểm tra giao thức ở chặng từ gateway đến ứng dụng riêng biệt. `server.http2.enabled=true` không thể buộc một proxy đứng trước dùng HTTP/2.

Với HTTP/2 cleartext (`h2c`), mức hỗ trợ và cách cấu hình phụ thuộc server/client; không nên giả định browser sẽ tự bật h2c cho API HTTP thường. Đồng thời, bật HTTP/2 **không thay thế** cấu hình giới hạn request, timeout, worker thread, connection pool và bảo vệ quá tải.

### 4.2. Kiểm tra bằng curl

Trên máy có bản `curl` hỗ trợ HTTP/2, chạy thử với một URL HTTPS hợp lệ (thay domain ví dụ bằng API của bạn):

```bash
curl --version
curl -sS --http2 -o /dev/null \
  -w 'version=%{http_version} connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  'https://api.example.com/v1/products/42'
```

Trên Windows có thể thay `/dev/null` bằng `NUL` và dùng `curl.exe`. `--http2` yêu cầu client thử HTTP/2; **hãy xem giá trị `version` thực tế** vì thương lượng có thể trở về HTTP/1.1. `time_starttransfer` là thời gian đến byte đầu tiên tính từ lúc bắt đầu phép đo; không thể coi riêng nó là thời gian SQL. Một yêu cầu đơn lẻ cũng không chứng minh lợi ích multiplexing; phải kiểm tra nhiều request đồng thời trên connection được tái sử dụng.

### 4.3. Client Java 11+ dùng chung `HttpClient`

Ví dụ sau phát 10 yêu cầu không đồng bộ bằng **cùng một** `HttpClient`, yêu cầu ưu tiên HTTP/2 và in giao thức thực tế của từng response:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class Http2Probe {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        List<CompletableFuture<Void>> calls = IntStream.rangeClosed(1, 10)
                .mapToObj(id -> {
                    HttpRequest request = HttpRequest.newBuilder(
                                    URI.create("https://api.example.com/v1/products/" + id))
                            .timeout(Duration.ofSeconds(5))
                            .GET()
                            .build();

                    return client.sendAsync(
                                    request, HttpResponse.BodyHandlers.ofString())
                            .thenAccept(response -> System.out.printf(
                                    "id=%d protocol=%s status=%d%n",
                                    id, response.version(), response.statusCode()));
                })
                .collect(Collectors.toList());

        CompletableFuture.allOf(calls.toArray(new CompletableFuture[0])).join();
    }
}
```

`Version.HTTP_2` là **ưu tiên phiên bản**, không phải bảo đảm: khi endpoint không hỗ trợ HTTP/2, Java client có thể dùng HTTP/1.1; kiểm tra `response.version()` để xác nhận. Các response được xử lý bất đồng bộ, nên thứ tự dòng log không cố định. Chạy nhiều lần với cùng điều kiện và đo p95/p99 nếu mục tiêu là hiệu năng, vì log này chỉ chứng minh hành vi giao thức và kết quả request.

## 5. Đo đúng nút thắt: ví dụ REST API tải cao

Giả sử `/v1/orders?status=PAID` có p95 = 1,2 giây khi 300 request/giây. Phía client báo giao thức `h2`, nhưng dashboard cho thấy CPU ứng dụng khoảng 40%, thời gian chờ lấy connection DB cao và query chưa có index thích hợp. Tăng giới hạn stream hoặc đổi lại HTTP/1.1 không giải quyết gốc rễ; cần điều tra SQL, index, truy cập dữ liệu và capacity DB trước.

Để xác định nguyên nhân, đo song song theo các tầng:

| Tầng | Chỉ số/công cụ tham khảo | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| Client và mạng | Phiên bản HTTP thực tế, RTT, retransmission, TTFB, tổng thời gian | Mất gói, truyền payload lớn, kết nối bị tạo lại, chờ stream |
| Gateway/proxy | Active connections/streams, queue, upstream time, 429/502/503/504, timeout | Một chặng đang dùng HTTP/1.1, chạm giới hạn stream hoặc queue |
| Spring API | Request rate, p50/p95/p99, lỗi, executor queue, CPU, heap/GC | Thread bị block, CPU cao, tắc ở bước xử lý |
| Database và downstream | Thời gian query, pool active/idle/pending, lock, dependency latency | Chờ pool, query chậm, fan-out hoặc retry làm tăng tải |

Quy trình kiểm chứng nên thực hiện theo thứ tự:

1. **Chốt phép đo nền:** cùng endpoint, payload, dữ liệu, cache, kết nối và mức concurrency; ghi p50/p95/p99, throughput và tỷ lệ lỗi. Không so sánh một request HTTP/1.1 lạnh với hàng trăm request HTTP/2 đã warm up.
2. **Xác minh đường đi:** kiểm tra ALPN/phiên bản ở client, chặng proxy và backend. Đo xem connection có được tái sử dụng, giới hạn concurrent stream có bị chạm và có lỗi `GOAWAY`/`RST_STREAM` bất thường không.
3. **Đổi đúng một biến:** giữ nguyên API và workload khi so sánh HTTP/1.1 với HTTP/2. Dùng công cụ load test có khả năng tạo traffic HTTP/2 thật; ví dụ `h2load` từ bộ nghttp2, với môi trường thử nghiệm được cấp phép và mức tải giới hạn.
4. **Liên hệ số đo:** nếu p95 vẫn cao cùng với DB pool pending hoặc upstream latency tăng, giải quyết nút thắt đó. Nếu API xử lý rất nhanh nhưng yêu cầu nhỏ bị chờ ở lớp kết nối, kiểm tra multiplexing, network và cấu hình gateway.
5. **Kiểm tra khi quá tải:** tăng concurrency từng bước; theo dõi p99 và 429/503. Áp dụng admission control/rate limit, timeout có giới hạn, retry với backoff + jitter cho các thao tác an toàn và phù hợp idempotency. Tránh retry đồng loạt gây khuếch đại tải.

Có thể dùng `h2load` để tạo tải thử nghiệm cho endpoint trong môi trường kiểm soát:

```bash
# Ví dụ: tổng 1.000 request, 5 connections, tối đa 20 stream mỗi connection.
h2load -n 1000 -c 5 -m 20 'https://staging.example.com/v1/products/42'
```

`-m 20` thể hiện mức đồng thời mục tiêu ở phía công cụ, không có nghĩa server nhất thiết nhận 20 stream cùng lúc; peer có thể công bố giới hạn thấp hơn. Không suy diễn nguyên nhân từ RPS đơn độc: một cấu hình có RPS cao hơn nhưng p99 hoặc tỷ lệ lỗi xấu hơn có thể không phù hợp yêu cầu thực tế.

## 6. An toàn và khả năng phục hồi vẫn phải thiết kế riêng

Multiplexing tăng khả năng gửi nhiều request đồng thời, nên server/gateway cần giới hạn tài nguyên hợp lý. Từng có kiểu tấn công **HTTP/2 Rapid Reset** khai thác việc tạo và hủy nhiều stream nhanh để làm cạn tài nguyên server. Các biện pháp vận hành gồm cập nhật bản vá cho web server/proxy, giới hạn request và stream, theo dõi mẫu `RST_STREAM` bất thường, timeout và kiểm soát tải. Không nên dựa vào HTTP/2 như một cơ chế bảo vệ DDoS.

Tương tự, đổi giao thức không thay thế **HTTPS, xác thực, phân quyền trên từng resource, giới hạn kích thước body, chống lộ dữ liệu qua cache và kiểm thử bảo mật**. Lỗi mạng có thể khiến client không biết một `POST` đã được server xử lý hay chưa; nếu nghiệp vụ cần retry an toàn, vẫn phải thiết kế **idempotency key** hoặc cơ chế chống xử lý lặp. `GET` nên là thao tác an toàn theo hợp đồng HTTP, nhưng client cũng không được retry vô hạn.

## 7. Bài tập thực hành và câu hỏi kiểm tra

**Bài tập 1 — Nhận diện tầng gây chờ.** Một trang gửi 30 `GET` nhỏ đồng thời. DevTools hiển thị `h2`, TTFB p95 900 ms, còn metric database cho thấy thời gian chờ pool p95 700 ms. Hãy nêu hai chỉ số cần kiểm tra thêm và thứ tự xử lý. **Gợi ý:** kiểm tra `pool.pending`, thời gian query và concurrency request trước khi thay `SETTINGS_MAX_CONCURRENT_STREAMS`.

**Bài tập 2 — Đo bằng Java.** Chạy `Http2Probe` với 10 endpoint nhỏ trên môi trường kiểm thử có HTTPS. Ghi `response.version()`, tổng thời gian hoàn thành và lỗi. So sánh với cấu hình `.version(HttpClient.Version.HTTP_1_1)` trong cùng điều kiện; warm up trước, lặp lại nhiều lần và dùng kích thước response tương tự. Giải thích vì sao tổng thời gian có thể tương đương hoặc HTTP/2 chậm hơn khi workload nhỏ, mạng ổn định và backend mới là nút thắt.

**Bài tập 3 — Phân tích mất gói.** Một HTTP/2 connection chứa stream A trả dữ liệu lớn và stream B trả JSON nhỏ. Khi có mất một segment TCP, B cũng bị chậm dù server đã xử lý xong. Phân biệt nguyên nhân với việc B phải chờ DB và giải thích HTTP/3 thay đổi điều gì, điều gì vẫn cần tối ưu ở backend.

**Bài tập 4 — Đọc kiến trúc.** Browser → gateway dùng `h2`, gateway → Spring dùng HTTP/1.1, Spring → DB dùng pool 10 kết nối. Hãy chỉ rõ nơi cần xác minh/đổi cấu hình nếu mục tiêu là tận dụng multiplexing trên chặng gateway → Spring; đồng thời giải thích vì sao chỉ đổi chặng đó chưa bảo đảm p95 tốt khi 100 request cùng chờ DB.

**Tiêu chí hoàn thành:** phân biệt được stream với TCP connection; nói rõ **HTTP/2 loại bỏ việc tuần tự hóa response HTTP trên cùng kết nối nhưng không loại bỏ TCP head-of-line blocking**; xác nhận giao thức thực tế qua công cụ; và tìm được số đo chứng minh nút thắt nằm tại mạng, gateway, Spring hay downstream trước khi tối ưu.
