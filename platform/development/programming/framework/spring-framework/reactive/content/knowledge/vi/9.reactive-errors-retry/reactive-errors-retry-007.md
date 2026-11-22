# timeout và phân biệt hết thời gian với lỗi kết nối trong Reactor / Spring WebFlux

## 1. Vì sao không thể gọi mọi lỗi mạng là “timeout”?

Một dịch vụ Spring WebFlux có thể gọi HTTP API qua WebClient, chờ cơ sở dữ liệu reactive hoặc phối hợp nhiều Mono. Khi yêu cầu không thành công, ít nhất ba tình huống khác nhau có thể xảy ra:

1. **Quá thời hạn xử lý (deadline/timeout):** ứng dụng đã chờ quá khoảng cho phép mà chưa nhận tín hiệu mong đợi. Ví dụ một Mono không trả giá trị trong 3 giây, nên toán tử **timeout(Duration)** phát lỗi.
2. **Lỗi kết nối (connection failure):** không thiết lập được kết nối, DNS không phân giải được, peer từ chối TCP hoặc kết nối bị cắt. Lỗi có thể xuất hiện **ngay lập tức** trước khi hết bất kỳ thời hạn nào.
3. **Có phản hồi HTTP nhưng trạng thái báo lỗi:** server hoặc gateway trả **HTTP 408, 429, 500, 502, 503 hoặc 504**. Client **đã nhận phản hồi**; đây là lỗi trạng thái HTTP, không phải bằng chứng toán tử Reactor timeout đã hết hạn.

Ba loại này không đồng nghĩa, dù ở giao diện người dùng có thể đều được mô tả là “không tải được dữ liệu”. Phân biệt chúng giúp đặt đúng timeout, ghi log đủ nguyên nhân, kiểm soát retry, ánh xạ lỗi ra HTTP response và tránh vô tình thực hiện lại nghiệp vụ.

**Phạm vi bài này:** cơ chế **timeout** trong **Mono/Flux**, khác biệt với timeout ở tầng HTTP/TCP và lỗi kết nối, cùng cách áp dụng trong **Spring WebFlux/WebClient**.

## 2. Phân biệt khái niệm bằng dòng thời gian

Hãy quan sát một yêu cầu HTTP outbound:

~~~text
App subscribe WebClient
    |
    +-- lấy connection từ pool
    |      có thể phải chờ pool
    |
    +-- DNS lookup (nếu chưa có địa chỉ)
    |
    +-- TCP connect
    |      có thể timeout hoặc bị từ chối
    |
    +-- TLS handshake (nếu HTTPS)
    |
    +-- gửi request
    |
    +-- chờ và đọc response headers/body
    |      có thể hết response/read timeout
    |
    +-- decode body, transform, kết hợp kết quả
    |
    +-- Mono onNext + onComplete / onComplete rỗng
~~~

**Thời gian tổng của một operation** có thể chứa nhiều giai đoạn. Mỗi giai đoạn có thể có chính sách timeout riêng; tổng thời gian còn chịu ảnh hưởng của xếp hàng, tải ứng dụng, scheduler, cơ chế retry và mã xử lý nghiệp vụ.

Nếu đặt:

~~~java
Mono<String> result = webClient.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3));
~~~

thì **timeout(Duration.ofSeconds(3))** áp dụng cho Publisher phía trước nó: sau khi có subscription, nếu Mono không đưa ra tín hiệu kết quả như mong đợi trước thời hạn, pipeline chuyển sang lỗi timeout. Nó không nói chính xác **DNS, connect, TLS, đợi response hay xử lý body** là giai đoạn nào gây chậm.

Ngược lại, **connect timeout** gắn với riêng nỗ lực thiết lập TCP; **response timeout** gắn với giai đoạn phản hồi HTTP theo cấu hình client. Một lỗi TCP “Connection refused” có thể xảy ra sau vài mili giây và không phải timeout.

**Đặt tên đúng sự kiện:** “Hết thời hạn tổng của request” khác “TCP connect bị timeout”, khác “remote server trả HTTP 504”.

## 3. Reactor timeout(Duration) thực sự làm gì?

### 3.1. Với Mono

**Mono<T>.timeout(Duration)** theo dõi khoảng chờ trước tín hiệu giá trị của Mono. Với nguồn chưa có tín hiệu hoàn tất/giá trị đúng thời hạn, nó phát **java.util.concurrent.TimeoutException** thông qua onError và hủy subscription upstream.

~~~java
Mono<String> result = Mono.<String>never()
        .timeout(Duration.ofSeconds(2));
~~~

Nguồn **Mono.never()** không phát dữ liệu, lỗi hoặc onComplete. Khi có subscription, sau khoảng 2 giây, timeout phát onError với **TimeoutException**. Kết quả không phải Mono rỗng và cũng không phải HTTP 504.

Trường hợp không cần chờ:

~~~java
Mono<String> immediate = Mono.just("ready")
        .timeout(Duration.ofSeconds(2));
// Phát "ready" và hoàn tất bình thường.
~~~

Một Mono hoàn tất thành công hoặc báo lỗi của nguồn trước khi thời hạn hết sẽ chốt subscription theo tín hiệu của nó. **Lỗi kết nối đến sớm không bị timeout đổi thành TimeoutException**: onError của nguồn được truyền xuống, trừ khi pipeline có operator xử lý/thay đổi lỗi.

**Quan trọng:** timeout bắt đầu khi Publisher được **subscribe**, không phải khi Java tạo biến Mono. Nếu ứng dụng tạo một CompletableFuture đã chạy **trước khi Mono.fromFuture(future)** được xây dựng, toán tử timeout được thêm sau này không thể giới hạn phần thời gian công việc chạy trước subscription.

### 3.2. Với Flux

**Flux<T>.timeout(Duration)** theo dõi **khoảng chờ trước phần tử đầu tiên và khoảng cách giữa các phần tử kế tiếp**. Nó phù hợp với việc phát hiện luồng streaming bị im lặng quá lâu:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(3))
        .timeout(Duration.ofSeconds(1));
~~~

Vì phần tử đầu của Flux.interval ở đây xuất hiện sau 3 giây, timeout 1 giây sẽ báo lỗi **trước phần tử đầu tiên**.

Ở chiều ngược lại, nếu luồng đều đặn phát từng phần tử trong giới hạn thì Flux có thể chạy rất lâu mà không timeout. Vì đồng hồ được làm mới sau các phần tử, **Flux.timeout(Duration)** không phải một deadline tổng cho toàn bộ stream. Muốn giới hạn **toàn bộ** quá trình tổng hợp, cần đặt deadline ở Mono kết quả cuối hoặc một cơ chế giới hạn tổng phù hợp.

Ví dụ:

~~~java
Mono<List<Long>> allWithinFiveSeconds =
        stream.collectList()
              .timeout(Duration.ofSeconds(5));
~~~

Đây là đoạn minh họa: **stream** là Flux do ứng dụng cung cấp. Toán tử ngoài cùng đo thời gian chờ Mono<List<Long>> hoàn tất việc gom, tức yêu cầu luồng phải cho kết quả cuối trong thời hạn. Trường hợp stream rất lớn cần kiểm soát bộ nhớ; timeout không thay thế phân trang hay giới hạn phần tử.

### 3.3. Overload có fallback

~~~java
Mono<String> result = slowSource
        .timeout(Duration.ofSeconds(2), Mono.just("cached"));
~~~

Nếu **slowSource** không đáp ứng trong thời hạn, Reactor chuyển sang **fallback Mono** được cung cấp. Điều này làm pipeline có kết quả thay thế thay vì phát TimeoutException, **chỉ cho nhánh timeout**. Một lỗi kết nối đến sớm vẫn là onError từ nguồn và không tự động được chuyển thành fallback bởi overload timeout có fallback.

Cần lưu ý:

- Fallback có thể chứa dữ liệu cũ; API cần làm rõ mức độ mới và nguồn dữ liệu.
- Fallback cũng có thể chậm, lỗi hoặc không kết thúc; hạn mức tổng thời gian phải tính cả nhánh fallback nếu cần.
- Dùng fallback không tự bảo đảm công việc upstream đã dừng ở server.
- Có những overload timeout dùng một **Publisher báo hết hạn** hoặc **Scheduler làm đồng hồ**, thích hợp cho kịch bản kiểm thử/giới hạn dựa trên tín hiệu.

### 3.4. Khác với block(Duration)

~~~java
String value = someMono.block(Duration.ofSeconds(2));
~~~

**block(Duration)** là lời gọi **chặn thread đang đợi kết quả** ở biên Java đồng bộ; khi hết thời gian, nó có thể ném RuntimeException với TimeoutException làm nguyên nhân. Đây là API khác với **someMono.timeout(Duration)**, vốn tạo **tín hiệu lỗi trong pipeline reactive**.

Trong Spring WebFlux, không đặt **block()** hoặc **get()/join()** để chờ kết quả bên trong luồng xử lý request non-blocking. Nên **trả Mono/Flux** cho framework quản lý.

## 4. Lỗi timeout và lỗi kết nối khác nhau ở loại exception

Một bảng phân loại thường hữu ích khi phân tích log:

| Tình huống | Dấu hiệu thường gặp | Bản chất |
| --- | --- | --- |
| **Reactor timeout(Duration) hết hạn** | **java.util.concurrent.TimeoutException** từ operator | Không có tín hiệu kết quả đúng thời hạn đã đặt trong pipeline |
| **TCP bị từ chối** | **java.net.ConnectException: Connection refused** | Endpoint không chấp nhận kết nối ở địa chỉ/cổng đó |
| **TCP connect hết thời gian** | **ConnectTimeoutException** của Netty hoặc lớp timeout liên quan, tùy client | Không hoàn tất bắt tay kết nối trong giới hạn connect |
| **DNS không tìm thấy máy chủ** | **UnknownHostException** hoặc lỗi resolver | Không phân giải được tên máy chủ, trước khi có HTTP response |
| **TLS handshake thất bại** | **SSLHandshakeException** hoặc lỗi SSL liên quan | Kết nối không hoàn tất TLS hợp lệ |
| **Đọc phản hồi quá hạn** | **ReadTimeoutException**, **SocketTimeoutException** hoặc exception tương ứng driver | Không đọc được dữ liệu đúng hạn ở tầng client/transport |
| **Kết nối bị cắt giữa chừng** | Connection reset, premature close, I/O exception | Kết nối đã thiết lập nhưng bị đóng/hỏng |
| **HTTP 408 Request Timeout** | HTTP status 408; WebClient có thể phát **WebClientResponseException** | Server gửi status 408 |
| **HTTP 504 Gateway Timeout** | HTTP status 504; **WebClientResponseException** | Gateway/proxy gửi status 504 khi upstream của gateway quá hạn |
| **HTTP 429 Too Many Requests** | HTTP status 429 | Server báo giới hạn tốc độ; có thể kèm Retry-After |

**Hai lớp ngoại lệ TimeoutException rất dễ bị nhầm:** Reactor operator thường dùng **java.util.concurrent.TimeoutException**, còn một số thư viện I/O dùng **java.net.SocketTimeoutException**, lớp con của IOException. Cả hai liên quan thời gian nhưng phát sinh tại **các tầng khác nhau**, có thông tin chẩn đoán và chính sách retry riêng.

**ConnectException không phải ConnectTimeoutException.** Ví dụ cổng đang đóng có thể trả “Connection refused” tức thời. Ngược lại, mạng không đáp ứng có thể làm **connect timeout** hết hạn. Đừng gộp hai hiện tượng thành một lỗi duy nhất nếu cần vận hành, quan sát và khắc phục chính xác.

Trong **WebClient**, lỗi trước khi nhận response HTTP thường được trình bày dưới **WebClientRequestException** với **cause** từ thư viện mạng; lỗi HTTP status khi dùng **retrieve()** mặc định thường thành **WebClientResponseException**. Không nên kiểm tra chỉ một lớp exception bề mặt rồi kết luận chính xác nguyên nhân TCP: hãy xem **cause chain** và thời điểm lỗi.

## 5. HTTP 408/504 không phải lúc nào cũng do client timeout

**HTTP 408** thường biểu thị server không nhận đủ yêu cầu trong thời gian server cho phép. **HTTP 504** biểu thị gateway/proxy không nhận được phản hồi upstream đúng hạn của chính gateway. Cả hai là **status được gửi qua HTTP**.

Ví dụ, response được nhận trong 150 ms:

~~~text
Client gửi GET /products
Gateway phản hồi trong 150 ms:
HTTP/1.1 504 Gateway Timeout
~~~

Ở client, đó là một **HTTP response 504**. Không nên ghi log “Reactor timeout after 3 s” chỉ vì status chứa từ Timeout: đồng hồ timeout 3 s của client chưa hề hết.

Ngược lại:

~~~text
Client subscribe
Sau 3 giây không có tín hiệu kết quả
Reactor timeout(3 s) phát TimeoutException
Không có HTTP response cuối cùng từ server cho request đó
~~~

Ở đây lỗi xảy ra **phía client**, không có bằng chứng server đã gửi 504.

**Một request có thể gặp nhiều giới hạn cùng lúc**: proxy timeout, server timeout, HTTP client response timeout và deadline Reactor. Tín hiệu nào đến trước thường quyết định lỗi downstream quan sát được. Từ một thông báo “timeout” không thể tự suy ra giai đoạn nào hỏng; cần log và metric theo từng tầng.

## 6. Các lớp timeout khi sử dụng WebClient và Reactor Netty

Trong Spring WebFlux dùng **Reactor Netty**, có thể cấu hình nhiều loại thời hạn khác nhau. Phân biệt:

| Giới hạn | Phạm vi | Gợi ý |
| --- | --- | --- |
| **Pool acquire timeout** | Chờ lấy connection từ pool khi hết slot | Cho biết thiếu connection/áp lực tải; không đồng nghĩa remote chậm |
| **DNS resolve timeout** | Chờ phân giải tên miền | Lỗi giai đoạn DNS |
| **TCP connect timeout** | Thời gian thiết lập TCP | Cấu hình ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **TLS handshake timeout** | Thời gian đàm phán TLS | Cấu hình SSL phù hợp |
| **Response/read timeout** | Giai đoạn chờ/đọc response của HTTP client | Cấu hình HttpClient.responseTimeout(...) hoặc handler phù hợp |
| **Reactor Mono.timeout(...)** | Thời hạn chờ tín hiệu kết quả của Publisher | Có thể bao phủ nhiều bước cộng lại, tùy vị trí đặt operator |
| **Flux.timeout(...)** | Thời hạn trước phần tử đầu/giữa các phần tử | Phù hợp luồng streaming và phát hiện ngừng cập nhật |
| **Proxy/gateway/server timeout** | Giới hạn do phía hạ tầng/remote đặt | Có thể sinh HTTP 408/504 hoặc đóng kết nối |

### 6.1. Cấu hình connect timeout và response timeout

Trong một ứng dụng Spring Boot WebFlux đã có dependency Spring WebFlux và Reactor Netty:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration
public class RemoteClientConfiguration {
    @Bean
    WebClient remoteWebClient() {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
                .responseTimeout(Duration.ofSeconds(2));

        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Đây là **đoạn cấu hình trong ứng dụng WebFlux**, không phải chương trình standalone. Mã thiết lập:

- **1.000 ms** cho giai đoạn thiết lập TCP kết nối (nếu cần kết nối mới).
- **2 giây** cho chính sách response timeout do Reactor Netty thực thi.

**responseTimeout không mặc nhiên tương đương một deadline end-to-end cố định** bao phủ DNS, pool, connect, TLS, đọc toàn bộ response, decode và mọi toán tử downstream. Tham chiếu tài liệu Reactor Netty cho ngữ nghĩa chi tiết của từng timeout và phiên bản đang dùng; với phản hồi streaming, khoảng chờ giữa các hoạt động đọc cũng quan trọng.

Có thể đặt deadline cho toàn bộ **Mono** kết quả ở tầng service:

~~~java
public Mono<String> fetchText(WebClient client, String uri) {
    return client.get()
            .uri(uri)
            .retrieve()
            .bodyToMono(String.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

Đây là đoạn minh họa: client và uri do ứng dụng cung cấp. **Đặt timeout sau bodyToMono** có nghĩa kết quả Mono được theo dõi cho đến khi có dữ liệu/hoàn tất đúng hạn; thời gian có thể bao gồm pool, DNS, connect, response và decode theo cách nguồn được subscribe.

### 6.2. Chọn ngân sách thời gian có thứ tự ưu tiên

Ví dụ một yêu cầu người dùng có deadline 4 giây và gọi một API downstream:

- Có thể dành khoảng **1 giây cho TCP connect**, **2 giây cho response**, đồng thời giới hạn **tối đa 3 giây cho toàn Mono**.
- Cần dự trù cả thời gian queue, DNS/TLS, giải mã, fallback, retry và phần xử lý còn lại trước deadline 4 giây.
- Không được cộng đơn giản 1 + 2 = 3 rồi cho rằng mọi request kết thúc đúng 3 giây; các giai đoạn/timer có thể chồng lấp, chạy nối tiếp hoặc bị giới hạn khác cắt sớm.
- Nếu phải retry, giới hạn cho **toàn bộ chuỗi retry** phải được tính trong ngân sách; nếu không mỗi attempt có thể dùng trọn thời hạn riêng.

Con số chỉ là **minh họa**, phải đo P95/P99, thông lượng, tỷ lệ lỗi và SLA thực tế mới chọn cấu hình sản xuất.

### 6.3. Chờ pool không phải lỗi remote

Khi connection pool bận, request có thể chờ slot và **hết pendingAcquireTimeout** trước khi thử TCP connect. Nếu quy tất cả về “service bên ngoài chậm”, nhóm vận hành sẽ điều chỉnh sai chỗ. Hãy tách **pool acquire**, **DNS**, **connect**, **TLS**, **response** và **application timeout** bằng log/metric. Tăng pool vô hạn không phải biện pháp an toàn vì có thể chuyển áp lực sang upstream.

## 7. Vị trí đặt timeout trong pipeline làm thay đổi ý nghĩa

### 7.1. Timeout trên từng lời gọi bên ngoài

~~~java
Mono<String> first = clientA.fetch()
        .timeout(Duration.ofSeconds(2));

Mono<String> second = clientB.fetch()
        .timeout(Duration.ofSeconds(2));

Mono<String> combined = Mono.zip(first, second)
        .map(tuple -> tuple.getT1() + ":" + tuple.getT2());
~~~

Các đoạn minh họa giả sử clientA/clientB trả Mono<String>. Mỗi nhánh có **timeout riêng**. Nếu hai lời gọi được subscribe phối hợp, mỗi nhánh có giới hạn tính từ subscription của chính nó. Một nhánh lỗi có thể khiến quá trình ghép thất bại và hủy nhánh còn lại; **hủy không cam kết tác vụ đã chạy trên server được rollback**.

### 7.2. Timeout cho cả tổ hợp

~~~java
Mono<String> combined = Mono.zip(
        clientA.fetch(),
        clientB.fetch()
)
.map(tuple -> tuple.getT1() + ":" + tuple.getT2())
.timeout(Duration.ofSeconds(3));
~~~

Ở đây thời hạn 3 giây áp dụng cho **Mono kết quả của toàn bộ tổ hợp**. Nếu một lời gọi kéo dài hơn, toàn bộ tổ hợp có thể timeout. Nó không báo tự động nhánh nào là nguyên nhân; muốn chẩn đoán phải đo riêng từng nhánh.

### 7.3. Timeout trước hoặc sau retry

~~~java
// Mỗi subscription/attempt được giới hạn riêng:
Mono<String> perAttempt =
        apiCall()
            .timeout(Duration.ofSeconds(1))
            .retryWhen(retryPolicy);

// Deadline bao trùm cả retry và backoff:
Mono<String> wholeOperation =
        apiCall()
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(3));
~~~

Đây là đoạn minh họa: **apiCall()** và **retryPolicy** do ứng dụng định nghĩa. Ý nghĩa khác nhau:

- **timeout trước retryWhen**: khi retry đăng ký lại nguồn, mỗi attempt có thể được cấp thêm khoảng chờ; tổng thời gian có thể lớn hơn timeout từng attempt.
- **timeout sau retryWhen**: deadline bao gồm cả các lần retry và thời gian chờ giữa chúng trong phạm vi publisher đó.
- Có thể cần **cả hai**: mỗi attempt bị giới hạn, đồng thời toàn operation có deadline tổng. Thiết kế chính sách retry sao cho nó nhận biết thời gian còn lại thực tế.
- Nếu **apiCall()** đã tạo một CompletableFuture eager trước khi đăng ký, retry có thể chỉ subscribe lại Future cũ. Muốn request mới ở lần thử sau cần nguồn **deferred** phù hợp, chẳng hạn Mono.defer(...) hoặc API tạo Publisher mới theo subscription.

**Một TimeoutException xuất hiện sớm không chứng minh “lỗi kết nối”**. Nó chỉ cho biết một đồng hồ quy định của pipeline đã hết; có thể tác vụ vẫn chờ pool, DNS, CPU hoặc response.

## 8. Phân loại lỗi trong WebClient trước khi quyết định fallback hoặc retry

### 8.1. WebClientRequestException và WebClientResponseException

Trong Spring WebClient:

- **WebClientRequestException** thường đại diện cho lỗi phát sinh khi gửi/thực hiện request **trước khi có HTTP response hợp lệ**, chẳng hạn lỗi phân giải host, kết nối, TLS hoặc transport. Nguyên nhân chi tiết thường nằm ở **getCause()**.
- **WebClientResponseException** thường xuất hiện với response HTTP lỗi được xử lý bởi **retrieve()** mặc định, chứa **status code**, headers và dữ liệu response trong phạm vi sẵn có.
- **java.util.concurrent.TimeoutException** do toán tử Reactor timeout phát sinh là lỗi deadline của pipeline; nó **không mặc nhiên được bọc thành WebClientRequestException**.
- Các dạng khác như lỗi decode body, lỗi mapper, lỗi nghiệp vụ hoặc cancellation phải được phân biệt; không nên biến mọi Throwable thành “network failure”.

Ví dụ ghi nhận đúng loại lỗi ở một pipeline:

~~~java
Mono<String> result = webClient.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(3))
        .doOnError(java.util.concurrent.TimeoutException.class,
                error -> log.warn("Downstream overall deadline exceeded", error))
        .doOnError(
                org.springframework.web.reactive.function.client.WebClientRequestException.class,
                error -> log.warn("HTTP request transport failed", error))
        .doOnError(
                org.springframework.web.reactive.function.client.WebClientResponseException.class,
                error -> log.warn("Remote HTTP status failed: {}",
                        error.getStatusCode().value(), error));
~~~

Đây là **đoạn minh họa trong một service đã có webClient, uri và log**. Không phải chương trình độc lập. Những callback **doOnError** chỉ quan sát lỗi, **không nuốt lỗi**. Trên thực tế, cần chuẩn hóa nhãn metric và tránh in URL/token/body nhạy cảm.

### 8.2. Xem cause chain một cách có kiểm soát

Nếu lỗi là **WebClientRequestException**, kiểm tra nguyên nhân:

~~~text
WebClientRequestException
  └── cause: java.net.ConnectException       → TCP refused
  └── cause: io.netty.channel.ConnectTimeoutException → TCP connect timeout
  └── cause: java.net.UnknownHostException    → DNS
  └── cause: SSLHandshakeException            → TLS
  └── cause: ReadTimeoutException             → response/read timeout
~~~

Các dòng là **những khả năng độc lập**, không phải một chuỗi nguyên nhân phải xuất hiện cùng lúc. Kiểu wrapper phụ thuộc phiên bản thư viện và giai đoạn request. Có trường hợp cause ở sâu hơn một lớp hoặc khác loại; không viết classifier chỉ dựa vào chuỗi thông báo Exception.getMessage() vì dễ lệ thuộc ngôn ngữ, phiên bản hoặc transport.

### 8.3. Lỗi HTTP status cần xử lý theo status và nghiệp vụ

Ví dụ, có thể muốn tách **404 không có dữ liệu**, **429 bị giới hạn tốc độ**, **503 upstream chưa sẵn sàng**, **504 gateway timeout**. Cần dùng **getStatusCode()** và thông tin response, không kiểm tra chúng như lỗi “connection refused”.

HTTP 400/401/403/404 thường **không nên retry y nguyên** trong nhiều nghiệp vụ vì yêu cầu không hợp lệ hoặc thiếu quyền sẽ tiếp tục thất bại. HTTP 429/502/503/504 có thể là ứng viên retry **theo hợp đồng dịch vụ**, giới hạn tốc độ và tính an toàn của operation. HTTP 408 cũng cần xem tính idempotent và ngữ cảnh cụ thể.

**Không tự giả định 504 an toàn để retry mọi POST.** Server phía sau gateway có thể đã thực hiện side effect dù gateway không nhận được response đúng hạn.

## 9. RetryWhen và deadline: chỉ thử lại khi có lý do

Một policy retry thường xem xét:

1. **Loại lỗi:** timeout tổng, connect timeout, connection reset, 429, 503, 504 hay lỗi nghiệp vụ? Không cùng chính sách cho tất cả.
2. **Độ an toàn:** GET/idempotent thường dễ kiểm soát hơn một lệnh thanh toán hoặc tạo đơn hàng. Với side effect, cân nhắc idempotency key, transaction và deduplication.
3. **Giới hạn số lần:** đặt max retries; một retry vô hạn có thể đè upstream và giữ request rất lâu.
4. **Backoff và jitter:** tránh tất cả client retry đồng loạt sau cùng một khoảng.
5. **Deadline tổng:** đừng để retry vượt ngân sách response người dùng; timeout ngoài retry policy là một lớp bảo vệ.
6. **Quan sát:** đếm số attempt, nguyên nhân, latency từng attempt và kết quả cuối; không tạo log khổng lồ mỗi lần thử.
7. **Cấu hình nguồn:** đảm bảo retry tạo một lượt I/O mới khi cần; nguồn eager được giữ lại không tự gọi API lại.

Ví dụ retry có giới hạn, chỉ với lỗi kết nối do ứng dụng chấp nhận:

~~~java
Mono<String> resilient = Mono.defer(() -> client.fetchAsync())
        .retryWhen(
                reactor.util.retry.Retry.backoff(
                        2,
                        Duration.ofMillis(200)
                )
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(error -> error instanceof java.net.ConnectException)
        )
        .timeout(Duration.ofSeconds(4));
~~~

Đây là **đoạn minh họa**, giả sử client.fetchAsync() trả Mono<String> mới theo subscription. Retry tối đa **2 lần bổ sung sau lần thử đầu tiên**, có khoảng nghỉ tăng dần và jitter; tổng operation có timeout 4 giây. **Trong WebClient thực tế**, lỗi connect thường bị bọc trong WebClientRequestException, nên predicate ở ví dụ **chỉ trực tiếp bắt ConnectException** sẽ cần sửa theo classifier/cause chain thực tế. Không sao chép nguyên filter đó vào ứng dụng rồi nghĩ đã xử lý mọi lỗi TCP.

Nếu hết số lần retry, Reactor có thể đưa ra **retry-exhausted exception** bao lấy lỗi cuối theo policy. Khi logging/ánh xạ lỗi, kiểm tra cả root cause; không nhận diện chỉ dựa trên chuỗi của exception tổng.

### Lỗi không nên retry tự động

- **Lỗi dữ liệu đầu vào**: validation 400, tham số sai.
- **Không có quyền**: 401/403, nếu chưa có quy trình làm mới token phù hợp.
- **Lỗi mapping/decode/bug**: retry mạng không sửa được logic Java sai.
- **Lệnh không idempotent**: có thể thực thi hai lần nếu response lần đầu mất.
- **Hệ thống đang quá tải nghiêm trọng**: retry không giới hạn có thể làm thảm họa nghiêm trọng hơn.

Nếu một request đã timeout, không có nghĩa server chưa xử lý nó. Đặc biệt với write API, phải có cơ chế kiểm tra trạng thái hoặc idempotency trước khi phát lại.

## 10. Ví dụ Java 17+ chạy được: timeout khác connection error

Ví dụ dưới đây dùng **Reactor Core thuần**, không mở kết nối mạng thật. Nó giả lập từng tín hiệu một cách xác định:

- **fast:** Mono phát ngay, không timeout.
- **deadline:** Mono.never không phát gì; timeout tạo TimeoutException và được xử lý thành chuỗi “TIMEOUT”.
- **connection:** Mono phát ConnectException ngay; timeout không biến nó thành TimeoutException.
- **retry:** nguồn deferred bị ConnectException lần đầu, thành công ở lần thứ hai; **Retry.max(2)** cho phép tối đa hai lần retry.

Nhờ dùng Mono.never và exception được tạo chủ động, ví dụ **không phụ thuộc internet hay một server khó tái hiện trạng thái lỗi**.

Cấu trúc:

~~~text
reactor-timeout-demo/
├── pom.xml
└── src/main/java/TimeoutVsConnectionDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>TimeoutVsConnectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/TimeoutVsConnectionDemo.java**:

~~~java
import java.net.ConnectException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public class TimeoutVsConnectionDemo {
    public static void main(String[] args) {
        String fast = Mono.just("OK")
                .timeout(Duration.ofSeconds(1))
                .block();
        System.out.println("fast = " + fast);

        String deadline = Mono.<String>never()
                .timeout(Duration.ofMillis(50))
                .onErrorResume(
                        TimeoutException.class,
                        error -> Mono.just("TIMEOUT"))
                .block();
        System.out.println("deadline = " + deadline);

        String connection = Mono.<String>error(
                        new ConnectException("simulated refusal"))
                .timeout(Duration.ofSeconds(1))
                .onErrorResume(
                        TimeoutException.class,
                        error -> Mono.just("TIMEOUT"))
                .onErrorResume(
                        ConnectException.class,
                        error -> Mono.just("CONNECTION"))
                .block();
        System.out.println("connection = " + connection);

        AtomicInteger attempts = new AtomicInteger();

        Mono<String> request = Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            if (attempt == 1) {
                return Mono.error(
                        new ConnectException("temporary refusal"));
            }
            return Mono.just("RECOVERED");
        });

        String retried = request
                .retryWhen(
                        Retry.max(2)
                                .filter(ConnectException.class::isInstance))
                .block();

        System.out.println("retry = " + retried
                + ", attempts = " + attempts.get());
    }
}
~~~

Với **JDK 17+**, Maven và dependency đã tải, chạy từ thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

**Các dòng do chương trình in ra:**

~~~text
fast = OK
deadline = TIMEOUT
connection = CONNECTION
retry = RECOVERED, attempts = 2
~~~

### Giải thích từng trường hợp

1. **Mono.just("OK")** phát ngay trên nguồn đồng bộ; timeout 1 giây không hết.
2. **Mono.never()** không phát bất kỳ tín hiệu nào. Sau khoảng 50 ms kể từ subscription, **timeout** phát **TimeoutException**, và nhánh **onErrorResume(TimeoutException.class, ...)** trả “TIMEOUT”. Dòng kết quả là ổn định dù độ trễ thực tế của scheduler có thể không đúng chính xác 50 ms.
3. **Mono.error(new ConnectException(...))** phát **ConnectException** ngay. Timeout được tháo khi nguồn đã báo lỗi; nhánh cho TimeoutException **không** bắt lỗi đó. Nhánh ConnectException trả “CONNECTION”.
4. **Mono.defer(...)** gọi Supplier cho mỗi subscription. Lần đầu báo ConnectException, Retry đăng ký lại lần thứ hai; lần thứ hai phát “RECOVERED”. **Retry.max(2)** cho phép tối đa hai retry nhưng ở đây chỉ cần một.
5. **block()** ở ví dụ console là ranh giới đồng bộ để in kết quả. **Không dùng block() trong request handler WebFlux**. Các Mono trong controller/service nên được trả cho framework.

### Giới hạn của ví dụ

Đây là phép mô phỏng **tín hiệu reactive**, không kiểm tra khả năng kết nối TCP thật và không chứng minh exception wrapper cụ thể của WebClient. Trong ứng dụng thật, sự kiện DNS/connect/response đến từ Reactor Netty/HTTP client, có thể được bọc bởi WebClientRequestException. Cần dùng bài test tích hợp để xác nhận phân loại của phiên bản Spring và driver đang chạy.

## 11. Kiểm thử timeout không phụ thuộc thời gian thực bằng StepVerifier

Một bài test dùng **Thread.sleep()** chờ đồng hồ có thể chậm và dễ flaky. Với **reactor-test**, StepVerifier hỗ trợ virtual time cho các toán tử tương thích:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutChecks {
    static void verify() {
        StepVerifier.withVirtualTime(
                () -> Mono.<String>never()
                        .timeout(Duration.ofSeconds(5)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(5))
                .expectError(TimeoutException.class)
                .verify();

        StepVerifier.create(
                Mono.<String>error(new java.net.ConnectException("refused"))
                        .timeout(Duration.ofSeconds(5)))
                .expectError(java.net.ConnectException.class)
                .verify();
    }
}
~~~

Đây là **đoạn test minh họa** trong dự án đã có **reactor-test**; không phải chương trình Maven standalone ở phần trước. Với virtual time, nguồn và timer phải được tạo theo đúng quy tắc của StepVerifier (bên trong Supplier truyền cho withVirtualTime). Test thứ hai xác minh lỗi kết nối giả lập không bị đổi thành TimeoutException.

Trong integration test WebClient, nên sử dụng server thử nghiệm kiểm soát được các trường hợp:

- Cổng đóng trả **connection refused** ngay.
- Không có DNS hoặc cấu hình DNS không hợp lệ.
- Server nhận kết nối nhưng **trễ response** hơn response timeout.
- Server gửi **HTTP 504 thực sự**, để xác minh phân loại HTTP status.
- Response stream bắt đầu nhanh nhưng **ngừng gửi chunk** lâu, để kiểm tra read timeout/Flux.timeout.
- Pool thiếu connection làm **pendingAcquireTimeout**.
- Cancellation/retry khi request có side effect, để xác minh việc hủy có tới server hay không.

Không dùng một trang web công cộng không do mình kiểm soát để kết luận loại exception chính xác, vì DNS, proxy, TLS và mạng của môi trường chạy có thể thay đổi.

## 12. Timeout, cancellation và nguy cơ “request vẫn chạy trên server”

Khi toán tử timeout hết hạn, nó thông thường **hủy upstream subscription** và phát lỗi. Trong một HTTP client non-blocking, cancellation có thể đóng/hủy request ở phía client tùy thời điểm; nhưng không thể khẳng định một thao tác ở hệ thống phía sau đã bị hủy hoặc rollback.

Ví dụ nguy hiểm:

~~~text
App POST /payments
   |
   +-- Server nhận yêu cầu và thực hiện thanh toán
   |
   +-- Response bị mất / client timeout sau 3 giây
   |
   +-- App retry POST giống hệt
   |
   +-- Có nguy cơ thanh toán lần thứ hai
~~~

Vì vậy, với lệnh ghi quan trọng:

- Sử dụng **idempotency key** khi API hỗ trợ và kiểm tra kết quả giao dịch.
- Có cơ chế **truy vấn trạng thái** sau timeout nếu không biết request đã được thực thi.
- Không tự retry vô hạn hoặc coi mọi timeout là thất bại chắc chắn ở server.
- Ghi nhận **request ID/correlation ID** để đối chiếu log ở client, proxy và downstream.
- Phân biệt **đã nhận response**, **đã gửi request** và **đã commit nghiệp vụ**; ba mốc không phải một.

Các giới hạn timeout, connect failure và HTTP 504 đều có thể để lại **trạng thái kết quả không chắc chắn** với tác vụ ghi: cần thiết kế giao thức ứng dụng, không suy đoán từ nhãn lỗi.

## 13. Quan sát và ghi log để phân biệt nguyên nhân

Một hệ thống có timeout đáng tin cần cho người vận hành thấy **giai đoạn chậm và loại thất bại**:

| Thuộc tính log/metric | Ví dụ / ý nghĩa |
| --- | --- |
| operation | catalog.fetch, order.details, payment.status |
| correlationId/traceId | Liên kết request qua gateway/service |
| remoteService | Tên dịch vụ, tránh ghi token hay URL chứa bí mật |
| outcome | success, reactor_deadline, tcp_refused, connect_timeout, dns_failure, read_timeout, http_504 |
| elapsedMs | Thời gian quan sát được của toàn operation |
| connectElapsedMs / responseElapsedMs | Nếu thư viện đo được, tách giai đoạn |
| attempt | Lần gọi thứ 1, 2, 3; số retry đã dùng |
| exceptionType / rootCauseType | Lớp exception thực tế, không chỉ message |
| httpStatus | Chỉ có khi có HTTP response |
| fallbackUsed | Có dùng dữ liệu thay thế không |
| poolPending / poolAcquireTimeout | Có nghẽn connection pool không |

Chỉ số cần xem theo thời gian: **tỷ lệ timeout**, **tỷ lệ connect failed**, **HTTP 5xx**, **P50/P95/P99 latency**, pending pool, số retry, tần suất timeout theo endpoint, mức dùng event loop/CPU và khả năng đáp ứng upstream.

Khi timeout tăng đồng thời với CPU và event loop bị nghẽn, thủ phạm có thể là **xử lý blocking trong app** hoặc scheduler quá tải, không hẳn đường mạng. Nếu “Connection refused” tăng ngay sau deploy, kiểm tra service lắng nghe port, service discovery và health readiness. Nếu HTTP 504 tăng nhưng client chưa đến deadline, kiểm tra gateway và upstream của nó.

Đặt metric tên có nghĩa thay vì một counter chung **network_error**. Không log request body hoặc thông tin xác thực nhạy cảm để phục vụ việc phân loại timeout.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “TimeoutException nghĩa là TCP không kết nối được.” | Chẩn đoán sai; một Mono chậm vì queue/CPU cũng có thể timeout. | Tách **operator deadline** khỏi exception TCP và các tầng timeout khác. |
| “Connection refused là kết nối timeout.” | Bỏ lỡ lỗi port/service down xảy ra ngay. | Xác định **ConnectException** khác **ConnectTimeoutException**. |
| “HTTP 504 là lỗi TimeoutException của Reactor.” | Bỏ qua response status thật. | Phân loại **WebClientResponseException** và status code. |
| “Đặt timeout(2 s) sau một thao tác đã chạy eager sẽ giới hạn từ lúc tạo Future.” | Một phần công việc xảy ra trước subscribe không được tính. | Hoãn tạo nguồn bằng **Mono.defer** hoặc Supplier khi cần. |
| “Flux.timeout(2 s) là hạn mức tối đa 2 giây cho cả stream.” | Luồng đều đặn phát có thể chạy rất lâu. | Phân biệt **khoảng giữa onNext** với **overall deadline**. |
| “responseTimeout(2 s) chính là toàn bộ SLA của request.” | Có thể không bao phủ pool, DNS, TLS và xử lý downstream. | Có thêm deadline ở tầng operation và metric theo từng phase. |
| “Retry lỗi nào cũng tốt.” | Gây retry storm, lặp side effect hoặc đè upstream. | Filter theo loại lỗi/nghiệp vụ, backoff/jitter, max attempts và idempotency. |
| “Timeout rồi thì server không xử lý gì cả.” | Có thể ghi dữ liệu hai lần khi retry. | Sử dụng idempotency key và API kiểm tra trạng thái. |
| “block(Duration) giống timeout(Duration).” | Chặn thread và đổi ranh giới xử lý exception. | Trong WebFlux, giữ Mono/Flux và dùng operator timeout. |
| “Catch Throwable rồi trả success fallback cho mọi lỗi.” | Che giấu bug, validation và lỗi quyền. | Chọn lọc loại lỗi; phản hồi rõ nếu không thể phục hồi. |
| “Test bằng sleep 100 ms sẽ luôn ổn.” | Flaky dưới tải/CI. | Dùng StepVerifier virtual time và test server kiểm soát được. |
| “Chỉ log getMessage() là đủ phân loại.” | Mất wrapper/cause/status/giai đoạn. | Ghi exception type, root cause, status, elapsed và attempt. |

## 15. Checklist thiết kế timeout và retry cho một WebClient call

1. **Xác định deadline của người dùng:** tổng request được phép chờ bao lâu?
2. **Xác định các giai đoạn:** pool acquire, DNS, TCP connect, TLS, response, decode và nghiệp vụ.
3. **Chọn timeout riêng:** connect/response/pool theo tài nguyên mạng; Reactor timeout để chặn tổng Mono khi cần.
4. **Đặt operator ở vị trí đúng:** timeout trước/ sau retry tạo hành vi khác nhau; có thể cần cả per-attempt và overall.
5. **Phân loại tín hiệu:** TimeoutException của Reactor, WebClientRequestException với cause, WebClientResponseException với HTTP status.
6. **Chọn retry có điều kiện:** tạm thời hay vĩnh viễn, có idempotent không, có Retry-After không, đã đủ ngân sách chưa?
7. **Xử lý trạng thái không chắc chắn:** khi server có thể đã thực hiện lệnh ghi trước timeout, có idempotency và truy vấn trạng thái.
8. **Chọn fallback hợp lệ:** có chấp nhận cache/stale data không? Fallback có cần deadline riêng không?
9. **Kiểm tra bằng test:** mô phỏng DNS, connection refused, TCP connect timeout, response delay, HTTP 504 và cancellation.
10. **Đo trên môi trường thực:** P95/P99, error class, pool saturation, attempt và metric upstream; chỉnh thời hạn bằng dữ liệu, không dựa vào cảm tính.

## 16. Ghi nhớ

**timeout(Duration)** trong Reactor đặt giới hạn chờ tín hiệu của **Publisher** sau subscription và có thể phát **java.util.concurrent.TimeoutException**; với **Flux**, nó chủ yếu đo khoảng chờ đầu tiên và giữa các phần tử. **Lỗi kết nối** như ConnectException, connect timeout, UnknownHostException, TLS/read timeout phát sinh tại **tầng transport**, nhiều khi được WebClient bọc trong WebClientRequestException. **HTTP 408/504** lại là **HTTP response status** do server/gateway gửi.

Dùng cả **timeout tầng mạng đúng mục đích** và **deadline của toàn thao tác**, phân loại exception theo tầng, đặt retry có giới hạn và kiểm soát tổng thời gian. Khi client timeout, không được mặc định server đã dừng hoặc giao dịch đã rollback.

**Tài liệu chính thức:**
- [Project Reactor — Mono.timeout và các overload](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Flux.timeout](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Spring Framework — WebClient Configuration / Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor — RetryBackoffSpec và error handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
