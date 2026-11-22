# Phân biệt thời gian kết nối, thời gian chờ phản hồi và thời gian xử lý

## 1. Vì sao cần tách các loại thời gian?

Khi một ứng dụng Spring Boot gọi HTTP đến dịch vụ khác, độ trễ mà người dùng quan sát được là kết quả của nhiều giai đoạn: phân giải tên miền, lấy kết nối từ pool, thiết lập TCP, bắt tay TLS, gửi request, chờ byte phản hồi đầu tiên và tải body. Ở phía máy chủ, request còn phải đi qua hàng đợi, controller, nghiệp vụ và các lời gọi phụ thuộc như database hoặc API khác.

Ba khái niệm trong đề bài mô tả các phần khác nhau của hành trình đó:

- **Thời gian kết nối (connection time):** thời gian cần để có một kết nối có thể dùng được đến máy chủ. Tùy client và cách đo, giai đoạn này có thể bao gồm hoặc tách riêng DNS, TCP, TLS và kết nối qua proxy.
- **Thời gian chờ phản hồi (response wait time):** thời gian client chờ dữ liệu phản hồi từ máy chủ. Cần phân biệt thời gian đến byte đầu tiên với khoảng thời gian tối đa được phép không nhận thêm dữ liệu.
- **Thời gian xử lý (processing time):** thời gian phía máy chủ dành để tiếp nhận và xử lý request, chạy nghiệp vụ, gọi dịch vụ phụ thuộc và tạo response.

Đây không phải ba tên gọi cho cùng một timeout. Một request có thể kết nối rất nhanh nhưng chờ server xử lý lâu; cũng có thể server xử lý nhanh nhưng client mất nhiều thời gian thiết lập kết nối hoặc tải body lớn.

Một mô hình gần đúng cho tổng thời gian của một lần gọi là:

~~~text
Tổng thời gian client quan sát
  = chờ connection pool
  + DNS
  + TCP connect
  + TLS / proxy handshake
  + gửi request
  + chờ và nhận response
~~~

Thời gian xử lý phía server nằm bên trong khoảng từ khi server nhận request đến khi server hoàn tất response. Nó góp phần tạo nên thời gian client chờ phản hồi, nhưng hai số đo không giống nhau vì còn có network latency, proxy, hàng đợi và truyền body.

## 2. Thời gian kết nối và connect timeout

### Những giai đoạn trước khi request được xử lý

Khi client gọi một hostname, quá trình thiết lập kết nối có thể gồm:

1. **DNS lookup:** chuyển hostname thành địa chỉ IP. Kết quả có thể đến từ cache hoặc DNS resolver.
2. **Lấy kết nối từ pool:** nếu client dùng connection pool, request có thể phải chờ một kết nối rảnh. Đây là thời gian chờ pool, không phải TCP connect.
3. **TCP handshake:** thiết lập kết nối TCP với máy chủ hoặc proxy.
4. **TLS handshake:** nếu dùng HTTPS, client và server thương lượng TLS, xác minh chứng chỉ và thiết lập khóa.
5. **Proxy negotiation:** nếu đi qua HTTP proxy, client có thể phải thiết lập tunnel CONNECT trước khi gửi request HTTPS.

**Connect timeout** giới hạn thời gian cho thao tác thiết lập kết nối mới theo cách triển khai của HTTP client. Không nên mặc định rằng nó bao gồm mọi giai đoạn ở trên. DNS lookup, TLS handshake và thời gian chờ connection pool có thể có cấu hình hoặc giới hạn riêng. Cần xem tài liệu của request factory hoặc HTTP client đang dùng.

Connect timeout chỉ có ý nghĩa khi phải tạo kết nối mới. Nếu request dùng lại kết nối keep-alive hoặc kết nối đã có trong pool, client có thể không thực hiện TCP handshake mới. Với HTTP/2, nhiều request còn có thể dùng chung một kết nối và được multiplex trên đó.

Một số nguyên nhân làm connection time tăng:

- DNS resolver phản hồi chậm hoặc không truy cập được.
- Máy chủ không lắng nghe, route mạng lỗi hoặc firewall chặn kết nối.
- TLS handshake chậm do mạng, xác minh chứng chỉ hoặc cấu hình cipher.
- Connection pool hết kết nối rảnh và request phải đợi.
- Client tạo quá nhiều kết nối mới vì không tái sử dụng kết nối.

### Cấu hình connect timeout cho RestTemplate

Trong Spring Boot 3.4+, có thể cấu hình connect timeout và read timeout qua RestTemplateBuilder:

~~~java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
class HttpClientConfiguration {

    @Bean
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
                .connectTimeout(Duration.ofSeconds(3))
                .readTimeout(Duration.ofSeconds(5))
                .build();
    }
}
~~~

Trong các minor version Spring Boot cũ hơn, tên phương thức builder có thể là setConnectTimeout(...) và setReadTimeout(...). Cấu hình thực tế được áp dụng thông qua ClientHttpRequestFactory mà builder sử dụng.

Ví dụ đặt connect timeout 3 giây có nghĩa client giới hạn thời gian thiết lập kết nối mới theo semantics của request factory. Nó không có nghĩa toàn bộ HTTP request chắc chắn kết thúc trong 3 giây. Nếu dùng HTTP client có connection pool, hãy cấu hình riêng thời gian chờ lấy kết nối từ pool, chẳng hạn connection-request timeout của Apache HttpClient.

## 3. Thời gian chờ phản hồi: TTFB và read timeout

Cụm từ “chờ phản hồi” có thể nói đến hai phép đo khác nhau.

**Time to First Byte (TTFB)** là thời gian client quan sát từ lúc bắt đầu request đến khi nhận byte phản hồi đầu tiên. TTFB thường bao gồm thời gian thiết lập kết nối nếu chưa có kết nối sẵn, gửi request, thời gian xử lý ở server và độ trễ mạng trên đường về. Vì thế, TTFB cao không tự chứng minh controller xử lý chậm.

**Read timeout** hoặc response timeout giới hạn thời gian client chấp nhận chờ dữ liệu trong quá trình đọc response. Cách áp dụng phụ thuộc HTTP client:

- Với socket read timeout truyền thống, một lần đọc bị timeout nếu không nhận được dữ liệu trong khoảng thời gian cấu hình. Khi dữ liệu tiếp tục đến đều đặn, từng lần đọc có thể thành công dù tổng thời gian truyền rất dài.
- Với Reactor Netty, responseTimeout là khoảng thời gian tối đa giữa các thao tác đọc ở tầng mạng. Nó giúp phát hiện response bị im lặng quá lâu, nhưng không nhất thiết là giới hạn tổng thời gian của toàn bộ stream.
- Một số API có request timeout hoặc deadline tổng, bao trùm nhiều giai đoạn của một lần gọi. Không nên đánh đồng chúng với socket read timeout.

Ví dụ, server gửi một byte mỗi 4 giây và client có read timeout 5 giây. Nếu mỗi lần đọc nhận được dữ liệu trước khi hết 5 giây, response có thể tiếp tục lâu hơn 5 giây rất nhiều. Nếu yêu cầu nghiệp vụ là “toàn bộ lời gọi phải hoàn thành trong tối đa 10 giây”, chỉ đặt read timeout 5 giây chưa đủ; cần deadline tổng.

### Cấu hình WebClient với Reactor Netty

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

class RemoteApiClient {

    private final WebClient webClient;

    RemoteApiClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                .responseTimeout(Duration.ofSeconds(5));

        this.webClient = WebClient.builder()
                .baseUrl("https://api.example.com")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }

    Mono<Item> getItem() {
        return webClient.get()
                .uri("/items/42")
                .retrieve()
                .bodyToMono(Item.class)
                .timeout(Duration.ofSeconds(8));
    }
}
~~~

Trong ví dụ:

- CONNECT_TIMEOUT_MILLIS đặt giới hạn cho thao tác TCP connect mới.
- responseTimeout giới hạn khoảng im lặng giữa các lần đọc dữ liệu ở tầng mạng của Reactor Netty.
- timeout trên Mono đặt deadline cho publisher của lời gọi trong ví dụ. Nếu không nhận được kết quả trong 8 giây, Mono phát lỗi timeout và hủy subscription upstream.

Các giới hạn này có mục đích khác nhau. Nếu dùng pool, cần cấu hình thêm thời gian chờ lấy connection. TLS handshake, DNS và proxy negotiation cũng có thể cần giới hạn riêng theo client được chọn. Hãy xác minh semantics của phiên bản Reactor Netty và Spring đang chạy.

Với response dạng stream trả về Flux, timeout(Duration) thường kiểm soát khoảng thời gian không có tín hiệu tiếp theo, tức là giới hạn khoảng im lặng giữa các phần tử. Một stream phát sự kiện đều đặn có thể chạy lâu hơn Duration. Nếu cần giới hạn tổng tuổi thọ stream, hãy đặt deadline/cancellation riêng; Flux.take(Duration) có thể cắt stream và hoàn tất bình thường, vì vậy cần chọn cách kết thúc phù hợp với hợp đồng API.

## 4. Thời gian xử lý ở phía Spring Boot

Thời gian xử lý là thời gian server dùng để phục vụ request. Nó có thể gồm:

- Chờ request được dispatch hoặc chờ worker thread sẵn sàng.
- Đọc và giải mã request body.
- Chạy filter, interceptor, controller và service.
- Kiểm tra quyền, validation và xử lý nghiệp vụ.
- Truy vấn database, gọi HTTP service khác hoặc truy cập hệ thống lưu trữ.
- Tuần tự hóa response body và ghi response.

Phạm vi đo chính xác phụ thuộc điểm bắt đầu/kết thúc của công cụ đo. Ví dụ, timer của HTTP server thường đo thời gian xử lý request ở phía server đến khi response được hoàn tất theo vòng đời server. Nó không đo DNS hay TCP connect mà client thực hiện trước khi request đến server.

Một endpoint xử lý lâu có thể do query database chậm, gọi API phụ thuộc chậm, lock contention, thread pool bão hòa hoặc xử lý CPU nặng. Tăng connect timeout không giải quyết được các vấn đề đó. Tăng read timeout chỉ khiến client chờ lâu hơn trước khi bỏ cuộc; nó không làm server xử lý nhanh hơn.

### Timeout ở server không đồng nghĩa timeout của controller

Cần phân biệt:

- **Connection timeout của server/container:** điều khiển một số giai đoạn nhận kết nối hoặc chờ request, tùy servlet container. Đây không phải cấu hình tổng quát để giới hạn thời gian chạy code trong controller.
- **Async request timeout của Spring MVC:** có thể cấu hình qua spring.mvc.async.request-timeout cho request xử lý bất đồng bộ như Callable, DeferredResult hoặc WebAsyncTask. Nó không tự động giới hạn mọi controller đồng bộ.
- **Timeout của database và HTTP client phụ thuộc:** giới hạn thời gian các thao tác bên trong nghiệp vụ. Đây thường là lớp cần cấu hình để một request không bị giữ vô hạn ở một dependency.
- **Deadline nghiệp vụ:** giới hạn tổng thời gian còn lại cho cả chuỗi xử lý. Ứng dụng cần truyền hoặc tính thời gian còn lại cho các bước tiếp theo.
- **Timeout của reverse proxy/load balancer:** giới hạn thời gian proxy chờ upstream hoặc chờ dữ liệu. Một số cấu hình như proxy_read_timeout của Nginx là khoảng thời gian tối đa giữa các lần đọc liên tiếp từ upstream, không phải deadline tổng của request.

Ví dụ cấu hình timeout cho các request Spring MVC bất đồng bộ:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 30s
~~~

Thiết lập này dành cho vòng đời request async của Spring MVC. Nếu controller đồng bộ đang chạy một câu SQL mất 60 giây, cấu hình trên không tự động ngắt câu SQL đó. Cần đặt query timeout, timeout cho HTTP client phụ thuộc hoặc cơ chế deadline phù hợp.

Với WebFlux, có thể đặt giới hạn cho một pipeline reactive bằng timeout operator:

~~~java
Mono<Result> result = service.loadResult()
        .timeout(Duration.ofSeconds(5));
~~~

Đây là deadline cho publisher Mono trong ví dụ. Nó không thay thế timeout cho từng dependency và không tự động tạo ra một giới hạn chung cho mọi request của server. Với Flux streaming, cần phân biệt deadline tổng và timeout giữa các tín hiệu như đã nêu ở phần trước.

## 5. Cách đo từng giai đoạn

Không nên suy ra thời gian xử lý server chỉ từ một con số latency ở client. Hãy kết hợp phép đo client, server và distributed tracing.

### Đo từ client bằng curl

Curl cung cấp các mốc thời gian hữu ích:

~~~bash
curl -sS -o /dev/null \
  -w 'dns=%{time_namelookup}s\nconnect=%{time_connect}s\ntls=%{time_appconnect}s\npretransfer=%{time_pretransfer}s\nttfb=%{time_starttransfer}s\ntotal=%{time_total}s\n' \
  https://api.example.com/items/42
~~~

Ý nghĩa các trường:

| Trường | Ý nghĩa |
|---|---|
| time_namelookup | Thời gian từ lúc bắt đầu đến khi phân giải tên miền xong |
| time_connect | Thời gian từ lúc bắt đầu đến khi kết nối TCP với host hoặc proxy hoàn tất |
| time_appconnect | Thời gian từ lúc bắt đầu đến khi hoàn tất TLS/SSL handshake |
| time_pretransfer | Thời điểm client sẵn sàng bắt đầu truyền dữ liệu request |
| time_starttransfer | Thời gian đến byte đầu tiên của response, thường được gọi là TTFB |
| time_total | Tổng thời gian đến khi curl nhận xong response |

Các mốc này thường là thời gian tích lũy tính từ lúc bắt đầu. Có thể dùng hiệu số để ước lượng một giai đoạn: time_connect trừ time_namelookup gần đúng thời gian thiết lập TCP sau DNS; time_appconnect trừ time_connect gần đúng phần TLS handshake. time_starttransfer trừ time_pretransfer cho biết khoảng từ lúc sẵn sàng truyền request đến byte đầu tiên, nhưng vẫn bao gồm độ trễ mạng, proxy và xử lý server. Nó không phải số đo thuần của controller.

Có thể giới hạn riêng connect và tổng thời gian ở curl:

~~~bash
curl --connect-timeout 3 --max-time 10 https://api.example.com/items/42
~~~

connect-timeout giới hạn việc kết nối theo semantics của curl; max-time giới hạn tổng thời gian thực thi lệnh. Đây là công cụ kiểm tra từ client, không cấu hình timeout cho ứng dụng Spring Boot.

### Đo từ Spring Boot bằng Actuator và Micrometer

Khi dùng Spring Boot Actuator và Micrometer, các metric HTTP thường gặp gồm:

- **http.server.requests:** thời gian request được xử lý ở phía server, kèm các tag như method, uri, status và outcome.
- **http.client.requests:** thời gian trao đổi HTTP ở phía client thông qua các client được instrument.

Metric client thường phản ánh toàn bộ lần gọi ở tầng client, không tự tách chính xác DNS, pool acquisition, TCP, TLS, TTFB và body transfer. Muốn phân tích các giai đoạn này, cần thêm metric từ HTTP client/connection pool, log phù hợp hoặc tracing span.

Distributed tracing giúp nhìn một request xuyên qua nhiều service. Một trace có thể cho thấy server A dành bao lâu trong controller, bao lâu gọi service B, và service B tiếp tục chờ database bao lâu. So sánh client span với server span giúp xác định phần chênh lệch nằm ở network, proxy, queue hay thời gian xử lý.

Không ghi log URL chứa token, mật khẩu hoặc dữ liệu cá nhân. Khi thêm tag hoặc log để phân tích latency, tránh dùng giá trị không giới hạn như user ID, request ID hoặc URL đầy đủ làm metric label vì có thể tạo cardinality rất lớn.

## 6. Đọc tình huống thực tế

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| DNS hoặc TCP time tăng, TTFB cũng tăng | DNS resolver, route mạng, firewall, proxy, server availability |
| TCP nhanh nhưng TLS chậm | TLS handshake, certificate chain, proxy hoặc cấu hình bảo mật |
| Client chờ pool lâu nhưng TCP connect thấp | Pool quá nhỏ, response trước chưa giải phóng connection, request concurrency cao |
| TTFB cao và http.server.requests cũng cao | Controller, queue, database hoặc downstream service xử lý chậm |
| TTFB cao nhưng server metric thấp | Network latency, proxy buffering, queue trước điểm đo server hoặc khác biệt phạm vi metric |
| Byte đầu tiên đến nhanh nhưng total time cao | Body lớn, tốc độ truyền thấp, client đọc chậm hoặc stream kéo dài |
| Read timeout xảy ra khi stream không phát dữ liệu | Server/dependency bị treo, khoảng im lặng vượt timeout hoặc proxy ngắt upstream |
| Client timeout nhưng server vẫn ghi log xử lý xong | Client đã bỏ cuộc nhưng server chưa nhận biết disconnect hoặc công việc backend chưa được hủy |

Một số tình huống minh họa:

**Kết nối nhanh, xử lý chậm:** client hoàn tất TCP/TLS trong 80 ms nhưng TTFB là 4 giây. Metric server cũng cho thấy request mất gần 4 giây. Hãy điều tra service, database, lock hoặc thread pool. Nâng connect timeout từ 3 lên 10 giây không giải quyết nguyên nhân.

**Kết nối chậm, xử lý nhanh:** server metric chỉ 40 ms nhưng client mất 1,5 giây trước khi có byte đầu tiên; DNS/TLS hoặc thời gian lấy connection pool tăng cao. Hãy kiểm tra DNS, tái sử dụng connection, pool và TLS.

**Stream kéo dài nhưng không bị read timeout:** server gửi một phần dữ liệu mỗi vài giây, luôn ngắn hơn khoảng read timeout. Tổng thời gian có thể rất dài. Nếu nghiệp vụ cần giới hạn tổng thời gian, hãy dùng deadline tổng riêng.

**Client timeout nhưng server vẫn chạy:** client phát timeout và đóng request, trong khi controller vẫn thực hiện truy vấn hoặc tác vụ nền. Timeout phía client không bảo đảm hủy công việc phía server. Ứng dụng cần xử lý cancellation/disconnect khi có thể và đặt timeout cho database, HTTP client phụ thuộc cùng tác vụ nền.

## 7. Chọn timeout theo mục đích

Trước khi đặt giá trị, hãy xác định điều cần bảo vệ:

1. **Pool acquisition timeout:** tránh request chờ vô hạn khi không có connection rảnh.
2. **Connect timeout:** tránh chờ lâu khi không thiết lập được kết nối mới.
3. **TLS/DNS timeout:** kiểm soát các giai đoạn riêng nếu client hỗ trợ.
4. **Read/response inactivity timeout:** phát hiện upstream không gửi thêm dữ liệu trong khoảng quá lâu.
5. **Overall request deadline:** giới hạn tổng thời gian của một lần gọi.
6. **Server/dependency timeout:** giới hạn công việc phía server và từng database/API phụ thuộc.

Các giá trị cần phối hợp. Nếu deadline tổng của request là 8 giây thì một dependency không nên được phép tiêu hết 30 giây. Hãy dành ngân sách thời gian cho các bước tiếp theo và cho việc trả lỗi. Khi request đã tiêu tốn một phần deadline, các bước downstream nên dùng thời gian còn lại thay vì bắt đầu lại một timeout đầy đủ.

Retry cũng tiêu tốn ngân sách. Ba lần thử, mỗi lần chờ tối đa 5 giây, có thể khiến tổng thời gian vượt xa kỳ vọng. Chỉ retry các thao tác có semantics an toàn hoặc có idempotency key; tránh tự động lặp POST tạo dữ liệu khi không biết server đã xử lý lần trước hay chưa. Dùng backoff và giới hạn tổng thời gian retry.

Một timeout quá ngắn làm tăng lỗi giả khi hệ thống chỉ chậm tạm thời. Timeout quá dài giữ connection, thread, request context và tài nguyên lâu hơn, khiến quá tải lan rộng. Chọn giá trị dựa trên SLO, phân bố latency thực tế (p95/p99), tải hệ thống và yêu cầu nghiệp vụ; sau đó quan sát tỷ lệ timeout và điều chỉnh.

## 8. Các lỗi hiểu nhầm phổ biến

- **Tăng connect timeout để sửa API xử lý chậm:** connect timeout chỉ liên quan đến kết nối mới; kiểm tra server processing time và dependency.
- **Coi read timeout là tổng thời gian response:** nhiều client áp dụng nó cho từng lần đọc hoặc khoảng im lặng; đặt deadline tổng riêng nếu cần.
- **Coi TTFB là controller time:** TTFB còn chứa network, proxy, connection setup và các hàng đợi trước server.
- **Coi connection pool wait là TCP connect:** request có thể chờ connection rảnh dù server đang hoạt động bình thường.
- **Dùng server connection timeout làm request processing timeout:** cấu hình này thuộc tầng kết nối/container và có semantics riêng; không tự ngắt code nghiệp vụ.
- **Cho rằng client timeout sẽ hủy xử lý trên server:** server hoặc dependency có thể tiếp tục chạy; cần cancellation và timeout ở đúng tầng.
- **Retry mọi lỗi timeout:** thao tác có thể đã được server thực hiện; retry không an toàn có thể tạo dữ liệu trùng lặp.
- **Chỉ xem log của một service:** cần đối chiếu client metric, server metric, pool metric và trace để biết thời gian tăng ở đâu.

## 9. Quy trình điều tra latency

Khi một API Spring Boot chậm, thực hiện theo trình tự:

1. Đo tổng thời gian và TTFB từ client; ghi nhận DNS, TCP, TLS và total bằng curl hoặc công cụ tương đương.
2. Kiểm tra client connection pool: thời gian chờ lấy connection, số connection đang dùng, số connection tối đa và tỷ lệ connection được tái sử dụng.
3. Tìm request tương ứng ở metric/log server và so sánh thời gian server xử lý với TTFB.
4. Nếu server chậm, dùng trace để xác định thời gian trong controller, database, HTTP dependency, queue và các bước nghiệp vụ.
5. Nếu server nhanh nhưng client chậm, kiểm tra DNS, TLS, proxy, network, buffering và thời gian tải body.
6. Xác định timeout nào đã kích hoạt: pool, connect, read/response, deadline tổng, server async hay proxy.
7. Đặt timeout ở đúng tầng, bổ sung cancellation và kiểm thử cả tình huống upstream phản hồi chậm, không phản hồi, gửi dữ liệu nhỏ giọt và client ngắt kết nối.

Phân biệt rõ connection time, response wait time và processing time giúp tìm đúng tầng gây latency, chọn timeout có ý nghĩa và tránh che giấu vấn đề bằng cách chỉ tăng thời gian chờ ở client.