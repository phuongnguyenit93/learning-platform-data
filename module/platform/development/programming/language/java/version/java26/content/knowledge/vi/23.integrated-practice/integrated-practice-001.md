# Gọi dịch vụ HTTP/3, kiểm chứng giao thức và đường dùng giao thức thay thế

JDK 26 bổ sung HTTP/3 cho `java.net.http.HttpClient` thông qua **JEP 517**. Ứng dụng có thể ưu tiên HTTP/3, yêu cầu HTTP/3 nghiêm ngặt cho endpoint đã được xác nhận, hoặc để client tự chọn đường kết nối và fallback về HTTP/2/HTTP/1.1 khi QUIC không khả dụng.

Điểm cần nhớ trong bài thực hành này: cấu hình `HTTP_3` chỉ là yêu cầu ưu tiên. Giao thức thực sự dùng cho một response phải được kiểm tra bằng `HttpResponse.version()`. Một request trả HTTP 200 chưa chứng minh nó đi qua HTTP/3; client có thể đã dùng HTTP/2 hoặc HTTP/1.1 sau khi fallback.

Các API `HttpClient.Version.HTTP_3`, `HttpOption.H3_DISCOVERY` và `HttpOption.Http3DiscoveryMode` có từ JDK 26, là API Java SE ổn định, không phải preview/incubator. JDK 27 tiếp tục hỗ trợ. HTTP/3 không được chọn mặc định: `HttpClient` mới vẫn mặc định ưu tiên HTTP/2.

## 1. Bối cảnh: HTTP/3 khác HTTP/2 ở transport

HTTP/1.1 và HTTP/2 thường chạy trên TCP. HTTP/3 chạy trên **QUIC**, một transport dựa trên UDP, và dùng TLS 1.3 trong quá trình thiết lập kết nối. Vì TCP và QUIC là hai transport khác nhau, client không thể nâng một kết nối TCP đang tồn tại thành QUIC như cách HTTP/2 có thể được thương lượng trên một kết nối TCP/TLS.

Điều này tạo ra một bài toán discovery: trước khi kết nối, client không biết endpoint có đang phục vụ HTTP/3 hay không. JDK 26 bổ sung các chiến lược để lựa chọn đường kết nối:

```text
Ứng dụng Java
     |
     v
HttpClient ưu tiên HTTP/3
     |
     +--------------------------+
     |                          |
     v                          v
QUIC / UDP                  TLS / TCP
     |                          |
     v                          v
HTTP/3                     HTTP/2 hoặc HTTP/1.1
     |                          |
     +------------+-------------+
                  |
                  v
        HttpResponse.version()
        giao thức thực sự được dùng
```

HTTP/3 có thể giảm head-of-line blocking ở tầng transport giữa các stream và có hành vi phục hồi mất gói khác TCP. Tuy nhiên, không có quy tắc rằng HTTP/3 luôn nhanh hơn HTTP/2: kết quả phụ thuộc mạng, RTT, packet loss, server, CDN, firewall và cách client phát hiện endpoint.

## 2. Bật HTTP/3 ở HttpClient hoặc từng HttpRequest

Có hai vị trí đặt phiên bản ưu tiên:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();
```

Khi đặt ở `HttpClient`, mọi request không ghi đè version sẽ kế thừa ưu tiên HTTP/3.

Hoặc chỉ bật trên một request:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/status"))
        .version(HttpClient.Version.HTTP_3)
        .GET()
        .build();
```

Đặt ở request giúp ứng dụng chọn HTTP/3 cho một nhóm endpoint đã biết hỗ trợ, trong khi các request còn lại tiếp tục dùng ưu tiên của client. Khi HTTP/3 được ưu tiên ở request, implementation có thể thử QUIC trước TCP. Nếu endpoint không hỗ trợ QUIC, thời gian chờ trước khi fallback có thể khác với trường hợp ưu tiên HTTP/3 ở cấp client.

Nếu không cấu hình ở cả hai nơi, `HttpClient` mặc định ưu tiên HTTP/2. Chỉ đặt `H3_DISCOVERY` mà không chọn `HTTP_3` ở client hoặc request thì option discovery không có tác dụng.

## 3. Ba chế độ discovery và fallback

`HttpOption.H3_DISCOVERY` được đặt trên `HttpRequest.Builder.setOption(...)`. JDK built-in `HttpClient` hỗ trợ ba giá trị:

| Mode | Cách tìm HTTP/3 | Đường thay thế | Trường hợp sử dụng |
| --- | --- | --- | --- |
| `ANY` | Thuật toán của implementation; thường có thể thử QUIC và TLS/TCP, dùng kết nối thành công trước. Có thể dùng Alt-Svc đã biết | HTTP/2 hoặc HTTP/1.1 nếu TCP thắng hoặc QUIC không khả dụng | Phù hợp với tập endpoint hỗn hợp; đây là mặc định khi HTTP/3 được bật mà không chỉ định option |
| `ALT_SVC` | Chỉ dùng HTTP Alternative Services đã được origin quảng bá để tìm endpoint HTTP/3 | Ban đầu dùng HTTP/2 hoặc HTTP/1.1; chuyển sang HTTP/3 khi có `h3` Alt-Svc | Phù hợp khi muốn server quảng bá rõ endpoint HTTP/3 trước khi client dùng QUIC |
| `HTTP_3_URI_ONLY` | Chỉ thử HTTP/3 tại đúng host và port của URI; không dùng Alt-Svc | Không fallback | Dùng cho endpoint do mình quản lý và đã xác nhận phục vụ HTTP/3 tại cùng authority |

### `ANY`: ưu tiên HTTP/3 nhưng chấp nhận fallback

Nếu chưa có kết nối hoặc thông tin Alt-Svc, JDK built-in client thường có thể thiết lập đường QUIC và đường TLS/TCP rồi sử dụng đường kết nối thành công trước. Khi request version được đặt trực tiếp thành HTTP/3, implementation có thể ưu tiên thử QUIC trước TCP. Chi tiết thứ tự và timing thuộc implementation.

`ANY` phù hợp khi gọi nhiều dịch vụ, trong đó một số hỗ trợ HTTP/3 còn một số chỉ hỗ trợ HTTP/2 hoặc HTTP/1.1. Ứng dụng vẫn nhận response nếu đường TCP có thể kết nối, miễn là các điều kiện mạng và request khác hợp lệ.

### `ALT_SVC`: để server quảng bá đường HTTP/3

HTTP Alternative Services được định nghĩa trong RFC 7838. Server có thể quảng bá một endpoint HTTP/3 bằng giá trị `h3` trong Alt-Svc, ví dụ `h3=":443"; ma=3600`. Server cũng có thể gửi thông tin Alternative Service qua cơ chế tương ứng của HTTP/2.

Ở chế độ `ALT_SVC`, client tiếp tục dùng HTTP/1.1 hoặc HTTP/2 cho đến khi nhận được quảng bá HTTP/3. Các request sau cùng origin có thể dùng endpoint `h3` đã học được. Vì vậy, cần tái sử dụng cùng một `HttpClient` để các request chia sẻ connection pool và trạng thái discovery; tạo client mới cho từng request có thể làm mất lợi ích tái sử dụng.

Nếu server không quảng bá HTTP/3, chế độ này tiếp tục dùng HTTP/2/HTTP/1.1. Nó không tự dò trực tiếp UDP tại host/port trong URI.

### `HTTP_3_URI_ONLY`: bắt buộc đường QUIC tại URI

Chế độ này chỉ kết nối HTTP/3 tại đúng host và port của URI, không dùng Alternative Services. Nếu server chỉ phục vụ HTTP/3 ở một port khác được quảng bá qua Alt-Svc, `URI_ONLY` vẫn không tìm port thay thế đó.

Nếu QUIC không khả dụng, request thất bại thay vì fallback. Dùng mode này trong integration test hoặc khi endpoint do nhóm vận hành kiểm soát; không dùng cho danh sách dịch vụ không đồng nhất.

## 4. Bài thực hành: tạo HTTP/3 probe có thể kiểm chứng

Chương trình dưới đây nhận URL HTTPS, discovery mode và số lần gọi. Nó dùng một `HttpClient` xuyên suốt các lần gọi để tái sử dụng kết nối và trạng thái Alt-Svc, in giao thức thực tế cho từng response, đồng thời phân biệt timeout và lỗi không hỗ trợ HTTP/3.

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.net.http.UnsupportedProtocolVersionException;
import java.time.Duration;
import java.util.Locale;

public final class Http3Probe {
    private Http3Probe() {}

    public static void main(String[] args) throws InterruptedException {
        if (args.length < 2 || args.length > 3) {
            System.err.println(
                    "Usage: java Http3Probe <https-url> <any|alt-svc|h3-only> [count]");
            System.exit(2);
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("HTTP/3 requires an https URI");
        }

        Http3DiscoveryMode mode = parseMode(args[1]);
        int count = args.length == 3 ? Integer.parseInt(args[2]) : 3;
        if (count < 1) {
            throw new IllegalArgumentException("count must be positive");
        }

        HttpClient client;
        try {
            client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_3)
                    .connectTimeout(Duration.ofSeconds(5))
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();
        } catch (java.io.UncheckedIOException e) {
            System.err.println("Cannot create HTTP/3 client: " + e.getCause());
            return;
        }

        try (client) {

            for (int attempt = 1; attempt <= count; attempt++) {
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(20))
                        .setOption(HttpOption.H3_DISCOVERY, mode)
                        .GET()
                        .build();

                try {
                    HttpResponse<String> response = client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString());

                    System.out.printf(
                            "attempt=%d requested=%s discovery=%s actual=%s status=%d uri=%s%n",
                            attempt,
                            HttpClient.Version.HTTP_3,
                            mode,
                            response.version(),
                            response.statusCode(),
                            response.uri());

                    if (mode == Http3DiscoveryMode.HTTP_3_URI_ONLY
                            && response.version() != HttpClient.Version.HTTP_3) {
                        throw new IllegalStateException(
                                "Strict HTTP/3 probe received " + response.version());
                    }

                    response.headers().firstValue("alt-svc")
                            .ifPresent(value -> System.out.println("Alt-Svc: " + value));

                } catch (UnsupportedProtocolVersionException e) {
                    System.err.println("HTTP/3 is not supported by this client configuration: "
                            + e.getMessage());
                    break;
                } catch (HttpTimeoutException e) {
                    System.err.println("Request timed out: " + e.getMessage());
                    break;
                } catch (IOException e) {
                    System.err.println("HTTP exchange failed: " + e.getMessage());
                    break;
                }
            }
        }
    }

    private static Http3DiscoveryMode parseMode(String value) {
        return switch (value.toLowerCase(Locale.ROOT)) {
            case "any" -> Http3DiscoveryMode.ANY;
            case "alt-svc" -> Http3DiscoveryMode.ALT_SVC;
            case "h3-only" -> Http3DiscoveryMode.HTTP_3_URI_ONLY;
            default -> throw new IllegalArgumentException(
                    "Unknown discovery mode: " + value);
        };
    }
}
```

`HttpClient` được đóng bằng try-with-resources sau khi hoàn tất probe. Trong ứng dụng server chạy lâu dài, nên giữ client dùng chung ở scope phù hợp thay vì tạo một client mới cho mỗi request; connection pool và thông tin Alt-Svc gắn với instance client.

### Biên dịch và chạy

Dùng JDK 26 trở lên:

```bash
javac --release 26 -encoding UTF-8 Http3Probe.java

java Http3Probe https://your-h3-service.example/status any 3
java Http3Probe https://your-h3-service.example/status alt-svc 3
java Http3Probe https://your-h3-service.example/status h3-only 3
```

Thay URL ví dụ bằng endpoint HTTPS thực tế. Nếu build bằng JDK 27 nhưng artifact vẫn phải chạy trên JDK 26, giữ `--release 26`. Code gọi `HttpClient.Version.HTTP_3` không thể biên dịch bằng JDK 25 trở xuống vì API này chưa tồn tại ở các release đó.

Không cần `--enable-preview` hoặc `--add-modules`; HTTP/3 API là API final từ JDK 26 trong module `java.net.http`.

## 5. Kiểm chứng giao thức thực tế

`HttpClient.version()` và `HttpRequest.version()` biểu thị phiên bản ưu tiên. Chúng không xác nhận giao thức đã được thương lượng thành công. Hãy đọc `HttpResponse.version()` sau mỗi response:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

System.out.println("Requested: " + request.version());
System.out.println("Client preference: " + client.version());
System.out.println("Actual: " + response.version());
```

Nếu request không đặt version riêng, `request.version()` có thể là `Optional.empty()`; khi đó client preference được dùng làm yêu cầu hiệu lực. `response.version()` luôn là nguồn cần kiểm tra để biết response cụ thể đã dùng HTTP/1.1, HTTP/2 hay HTTP/3.

Phân biệt hai kết quả độc lập:

- `response.statusCode()` cho biết kết quả HTTP ở tầng ứng dụng, ví dụ 200, 404 hoặc 503.
- `response.version()` cho biết phiên bản giao thức đã truyền response.

Ví dụ `status=200 actual=HTTP_2` nghĩa là request thành công nhưng đã fallback hoặc được phục vụ bằng HTTP/2. Nếu mục tiêu kiểm thử là HTTP/3, kết quả đó không đạt tiêu chí giao thức dù status là 200.

Nếu bật redirect, `response.uri()` là URI nhận response cuối cùng. Khi cần kiểm tra từng hop, xem `response.previousResponse()` để lần lại response trước đó; redirect có thể thay đổi origin hoặc scheme và do đó thay đổi giao thức thực tế.

## 6. Ma trận kiểm thử ba đường discovery

Chuẩn bị ít nhất hai endpoint do nhóm kiểm soát:

- Endpoint A: HTTPS, phục vụ HTTP/2 hoặc HTTP/1.1 và HTTP/3; có thể quảng bá `h3` bằng Alt-Svc.
- Endpoint B: HTTPS, chỉ phục vụ HTTP/2 hoặc HTTP/1.1, không có QUIC listener.

Chạy mỗi mode với một `HttpClient` mới cho lượt thử đầu tiên, sau đó lặp lại request trên cùng client.

| Endpoint | `ANY` | `ALT_SVC` | `HTTP_3_URI_ONLY` |
| --- | --- | --- | --- |
| A, H3 bật trực tiếp tại URI authority | Có thể HTTP/3 hoặc HTTP/2 ở request đầu tùy đường kết nối thắng; các request sau có thể dùng H3 | Dùng HTTP/2/1.1 đến khi nhận Alt-Svc; sau đó có thể dùng H3 | Phải dùng H3 nếu kết nối thành công |
| A, H3 chỉ ở authority/port thay thế qua Alt-Svc | Có thể dùng endpoint H3 đã học hoặc fallback | Dùng endpoint H3 sau khi nhận quảng bá | Không dùng endpoint thay thế; có thể thất bại |
| B, không có QUIC | Fallback HTTP/2 hoặc HTTP/1.1 nếu TCP kết nối được | HTTP/2 hoặc HTTP/1.1 | Thất bại hoặc timeout, không fallback |
| B, UDP bị firewall chặn | Thường fallback TCP | Tiếp tục TCP nếu không có Alt-Svc khả dụng | Thất bại hoặc timeout |

Không viết test khẳng định request đầu tiên của `ANY` luôn là HTTP/3. JDK có thể thử nhiều đường kết nối và dùng đường thành công trước. Test ổn định nên xác nhận endpoint H3-only bằng `HTTP_3_URI_ONLY`; test fallback dùng endpoint TCP-only và xác nhận response là HTTP/2 hoặc HTTP/1.1.

### Kết quả mẫu mang tính minh họa

Một server hỗ trợ cả HTTP/2, HTTP/3 và quảng bá Alt-Svc có thể tạo chuỗi kết quả như sau:

```text
ANY              -> HTTP_2, HTTP_3, HTTP_3
ALT_SVC          -> HTTP_2, HTTP_3, HTTP_3
HTTP_3_URI_ONLY  -> HTTP_3, HTTP_3, HTTP_3
```

Đây không phải kết quả cố định. `ANY` có thể trả HTTP/3 ngay lần đầu hoặc HTTP/2 trước; `ALT_SVC` chỉ chuyển sang H3 sau khi client nhận được thông tin Alternative Service; server, cache và mạng quyết định thời điểm chuyển.

## 7. Khi HTTP/3 không dùng được: phân tích fallback

HTTP/3 cần QUIC trên UDP. Một request có thể không dùng được H3 vì:

- Server chưa bật HTTP/3 hoặc chưa có QUIC listener.
- Firewall, NAT, VPN hoặc mạng doanh nghiệp chặn UDP đến endpoint/port H3.
- Server quảng bá Alt-Svc sai hoặc endpoint thay thế không truy cập được.
- Client đang đi qua proxy mà implementation JDK built-in không hỗ trợ HTTP/3 qua proxy.
- `SSLContext` hoặc `SSLParameters` tùy chỉnh không tương thích với QUIC transport của implementation.
- URI không dùng scheme `https`.

Với `ANY`, JDK có thể tiếp tục qua HTTP/2 hoặc HTTP/1.1 nếu đường TCP dùng được. Với `ALT_SVC`, client chỉ thử đường H3 được quảng bá; nếu chưa có quảng bá thì tiếp tục HTTP/2/1.1. Với `HTTP_3_URI_ONLY`, không có đường thay thế.

Một lỗi `HttpTimeoutException`, `ConnectException` hoặc `UnsupportedProtocolVersionException` không nhất thiết có cùng nguyên nhân. Hãy kiểm tra mode, URL scheme, proxy, SSL context, UDP reachability và log trước khi kết luận server không hỗ trợ H3.

## 8. Lưu ý đặc biệt về proxy

Trong JDK built-in `HttpClient` hiện tại, HTTP/3 qua proxy không được hỗ trợ:

- Nếu proxy được chọn cho URI và mode là `ANY` hoặc `ALT_SVC`, client downgrade sang HTTP/2 hoặc HTTP/1.1 và bỏ qua `H3_DISCOVERY`.
- Nếu proxy được chọn và mode là `HTTP_3_URI_ONLY`, request thất bại.

Điều này có thể khiến ứng dụng trả HTTP 200 nhưng không hề dùng HTTP/3. Kiểm tra proxy selector và các system properties như `https.proxyHost` trong môi trường CI/container. Không suy luận rằng đã dùng QUIC chỉ vì đã cấu hình `.version(HTTP_3)`.

Nếu yêu cầu bắt buộc H3, hãy xác minh đường đi thực tế không chọn proxy và thử `HTTP_3_URI_ONLY` trên endpoint do nhóm quản lý. Không tắt proxy hoặc bypass kiểm soát mạng của tổ chức một cách tùy tiện; cần cấu hình đường mạng theo chính sách vận hành.

## 9. SSLContext và UnsupportedProtocolVersionException

JDK built-in client dùng QUIC implementation có các điều kiện đối với TLS. Nếu client cấu hình một `SSLContext` hoặc `SSLParameters` mà implementation không thể dùng cho HTTP/3, nó có thể ném `UnsupportedProtocolVersionException` khi build client với HTTP/3 preference hoặc khi gửi request `HTTP_3_URI_ONLY`.

Khi bắt đầu tích hợp, hãy dùng default `SSLContext` và default `SSLParameters`. Chỉ thêm mutual TLS, custom provider hoặc TLS customization sau khi đã kiểm tra khả năng tương thích của cấu hình đó với HTTP/3 trên đúng JDK update. Không tự ghi đè các TLS application protocol/ALPN nội bộ mà `HttpClient` cần quản lý.

`UnsupportedProtocolVersionException` khác với việc server không có QUIC listener: exception này cho biết client instance không hỗ trợ protocol trong cấu hình hiện tại. Trong mode fallback, client có thể vẫn dùng HTTP/2/1.1 tùy điều kiện và implementation.

`HttpClient.Builder.build()` không khai báo checked exception; nếu cấu hình protocol không được implementation hỗ trợ, nó có thể ném `UncheckedIOException`. Ví dụ probe xử lý trường hợp này khi tạo client. Khi gửi request, `UnsupportedProtocolVersionException` có thể được bắt như một `IOException` riêng để phân biệt với timeout hoặc lỗi mạng.

`HttpOption` là request option hint. JDK built-in `HttpClient` hiểu `H3_DISCOVERY`; một implementation khác có thể bỏ qua hint hoặc từ chối request nếu không hiểu option. Nếu ứng dụng thay implementation, cần kiểm tra tài liệu và integration test của implementation đó.

## 10. Bật log HTTP/3 và QUIC khi điều tra

Module `java.net.http` có system property `jdk.httpclient.HttpClient.log` để bật log các nhóm sự kiện. Ví dụ:

```bash
java \
  -Djdk.httpclient.HttpClient.log=errors,requests,http3,quic \
  Http3Probe https://your-h3-service.example/status any 3
```

Có thể bật thêm nhóm QUIC cụ thể khi cần xem điều khiển và retransmission:

```bash
java \
  -Djdk.httpclient.HttpClient.log=errors,requests,http3,quic:control:retransmit \
  Http3Probe https://your-h3-service.example/status h3-only 1
```

Logger được đặt tên `jdk.httpclient.HttpClient` và ghi ở mức INFO qua Platform Logging API. Cần cấu hình logging backend phù hợp để quan sát log. Không bật `content` hoặc log header nhạy cảm trên production nếu chưa có chính sách bảo vệ dữ liệu; log mạng có thể chứa URL, header và metadata nội bộ.

Các thuộc tính QPACK và QUIC như `jdk.httpclient.qpack.decoderMaxTableCapacity`, `jdk.httpclient.qpack.encoderTableCapacityLimit`, `jdk.httpclient.quic.receiveBufferSize` và `jdk.httpclient.quic.sendBufferSize` là tuning implementation. Chỉ thay đổi khi có số liệu đo và yêu cầu vận hành cụ thể; không coi các giá trị này là API Java portable.

## 11. Đánh giá hiệu năng trước khi chuyển mặc định

HTTP/3 không mặc nhiên nhanh hơn cho mọi request. Trước khi thay chiến lược của một service, benchmark cùng endpoint và cùng workload trên HTTP/2 và HTTP/3.

Giữ các điều kiện nhất quán:

1. Cùng JDK update, CPU, container limit, DNS và TLS certificate.
2. Dùng cùng endpoint, payload, request headers và mức concurrency.
3. Tách cold connection khỏi connection đã warm/reuse.
4. Đo cả request đầu tiên lẫn các request tiếp theo, nhất là khi dùng `ALT_SVC`.
5. Chạy ở mạng đại diện production: LAN, mobile, VPN, WAN hoặc mạng có packet loss.
6. Ghi `response.version()` cho từng mẫu; không gộp fallback HTTP/2 vào nhóm H3.

Các chỉ số cần thu thập:

| Chỉ số | Mục tiêu |
| --- | --- |
| Connect/handshake time | Đo chi phí thiết lập QUIC so với TCP/TLS |
| Time to first byte (TTFB) | Xác định thời gian nhận byte đầu tiên |
| p50/p95/p99 latency | Phát hiện ảnh hưởng lên tail latency |
| Throughput và transfer time | So sánh tải đơn và nhiều stream đồng thời |
| Retransmission/packet loss | Hiểu hành vi QUIC trên mạng không ổn định |
| Tỷ lệ HTTP/3 thực tế | Xác định bao nhiêu request thật sự dùng H3 thay vì fallback |
| Timeout/error rate | Phát hiện endpoint hoặc mạng không tương thích |

Đừng quyết định chỉ từ benchmark loopback hoặc một CDN. Lợi ích của QUIC có thể thể hiện rõ hơn trên mạng có packet loss hoặc nhiều stream đồng thời, trong khi trên mạng LAN sạch chi phí thiết lập hoặc implementation có thể khiến kết quả khác. Đo workload thật trước khi chuyển toàn bộ traffic.

## 12. Chiến lược lựa chọn cho ứng dụng

| Bối cảnh | Cấu hình khởi đầu | Lý do |
| --- | --- | --- |
| Nhiều origin, chưa biết origin nào hỗ trợ H3 | Client preference `HTTP_3` + `ANY` | Thử H3 và có đường TCP thay thế |
| Origin thường dùng H2, đang triển khai H3 dần | Client preference `HTTP_3` + `ALT_SVC` | Dùng H3 sau khi server chủ động quảng bá |
| Endpoint H3 do nhóm vận hành kiểm soát | Request preference `HTTP_3` + `HTTP_3_URI_ONLY` trong test | Phát hiện ngay khi QUIC/H3 không khả dụng |
| Mạng có proxy bắt buộc | Giữ HTTP/2 hoặc HTTP/1.1 cho JDK built-in client | Proxy path hiện không hỗ trợ H3 trong implementation này |
| Chưa có số liệu production | Giữ mặc định HTTP/2, thử nghiệm H3 theo nhóm endpoint | Tránh đổi giao thức hàng loạt khi chưa đo |

Ví dụ cấu hình HTTP/3 opt-in nhưng fallback:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(15))
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ANY)
        .GET()
        .build();
```

Ví dụ kiểm tra H3 nghiêm ngặt cho endpoint đã xác nhận:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(15))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY,
                Http3DiscoveryMode.HTTP_3_URI_ONLY)
        .GET()
        .build();
```

Nếu ứng dụng phải đảm bảo request không bao giờ được gửi bằng HTTP/2/1.1, hãy xác nhận `response.version() == HTTP_3` trước khi coi operation là đạt yêu cầu. Nếu cần fail-fast ở tầng transport, `HTTP_3_URI_ONLY` khiến không có fallback; vẫn phải xử lý exception và timeout.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Compile báo không tìm thấy `HTTP_3` | Đang compile bằng JDK 25 trở xuống | Dùng JDK 26+; nếu target Java 26, đặt `--release 26` |
| Response 200 nhưng `version()` là HTTP/2 | Fallback, Alt-Svc chưa có, TCP thắng race hoặc proxy được chọn | Kiểm tra discovery mode, Alt-Svc, proxy và actual response version |
| `H3_DISCOVERY` không làm thay đổi giao thức | HTTP/3 chưa được chọn ở client hoặc request | Đặt `version(HTTP_3)` ở ít nhất một trong hai nơi |
| `ALT_SVC` luôn dùng HTTP/2 | Server chưa quảng bá `h3` hoặc client chưa nhận được Alt-Svc | Kiểm tra response/ALTSVC advertisement và tái sử dụng cùng client |
| `HTTP_3_URI_ONLY` thất bại | Không có QUIC listener tại đúng host/port, UDP bị chặn hoặc có proxy | Kiểm tra endpoint và đường UDP; không mong đợi fallback ở mode này |
| `UnsupportedProtocolVersionException` | Client/SSLContext/SSLParameters không hỗ trợ H3 hoặc proxy kết hợp URI_ONLY | Thử default SSL context, bỏ custom TLS config, kiểm tra proxy |
| Timeout khi dùng HTTP/3 | UDP bị chặn, QUIC handshake không hoàn tất hoặc timeout quá ngắn | Kiểm tra firewall/NAT/UDP và đo thời gian thiết lập; thử ANY nếu cho phép fallback |
| Lần đầu HTTP/2, lần sau HTTP/3 | ANY race hoặc Alt-Svc được học sau response đầu | Đây có thể là hành vi dự kiến; xác minh từng response |
| Dùng HTTP/3 trên `http://` URI | HTTP/3 yêu cầu HTTPS | Dùng URI HTTPS với certificate hợp lệ |

## 14. Checklist trước khi bật HTTP/3 cho một dịch vụ

- [ ] Runtime là JDK 26+ và dùng implementation `HttpClient` hỗ trợ HTTP/3.
- [ ] URL là `https://` và certificate/hostname hợp lệ.
- [ ] Server hoặc CDN đã bật HTTP/3/QUIC.
- [ ] Firewall/NAT cho phép UDP đến host/port H3; nếu dùng Alt-Svc, kiểm tra cả endpoint/port được quảng bá.
- [ ] Xác định proxy selector trong developer machine, CI, container và production.
- [ ] Chọn rõ `ANY`, `ALT_SVC` hoặc `HTTP_3_URI_ONLY` theo yêu cầu fallback.
- [ ] Tái sử dụng `HttpClient` khi muốn giữ connection pool và Alt-Svc state.
- [ ] Ghi nhận `HttpResponse.version()` cho từng response trong kiểm thử.
- [ ] Kiểm tra status code tách biệt với giao thức thực tế.
- [ ] Có test H3-capable, TCP-only, UDP-blocked và proxy path.
- [ ] Có timeout, logging và metrics cho fallback/error.
- [ ] Benchmark latency/throughput trên mạng đại diện trước khi thay đổi mặc định.

## Ghi nhớ

- JEP 517 đưa HTTP/3 vào `java.net.http.HttpClient` từ JDK 26; API final, không cần preview flag.
- HTTP/3 chạy trên QUIC/UDP; HTTP/2 và HTTP/1.1 thường chạy trên TCP.
- `HttpClient` vẫn mặc định ưu tiên HTTP/2; muốn H3 phải chọn `HttpClient.Version.HTTP_3` ở client hoặc request.
- `HttpOption.H3_DISCOVERY` chỉ có hiệu lực khi HTTP/3 đã được chọn.
- `ANY` cho phép client tự chọn đường kết nối và fallback; `ALT_SVC` chờ server quảng bá H3; `HTTP_3_URI_ONLY` chỉ dùng QUIC tại host/port URI và không fallback.
- Chỉ `HttpResponse.version()` xác nhận giao thức thực tế; status 200 không chứng minh response đi qua H3.
- HTTP/3 yêu cầu HTTPS. JDK built-in client hiện không hỗ trợ HTTP/3 qua proxy; proxy có thể khiến ANY/ALT_SVC downgrade âm thầm, còn URI_ONLY thất bại.
- Custom `SSLContext`/`SSLParameters` có thể không tương thích QUIC và dẫn đến `UnsupportedProtocolVersionException`.
- Dùng cùng một `HttpClient` để tái sử dụng connection và thông tin Alt-Svc; đo riêng request đầu tiên và các request tiếp theo.
- Kiểm thử UDP, proxy, fallback, actual protocol và tail latency trước khi triển khai rộng.

## Tài liệu tham khảo

- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517) — mục tiêu và lựa chọn thiết kế HTTP/3 trong JDK 26.
- [HttpClient, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html) — version preference, HTTP/3 opt-in, HTTPS/proxy constraints và UnsupportedProtocolVersionException.
- [HttpClient.Version, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html) — `HTTP_3` được bổ sung từ JDK 26.
- [HttpOption, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.html) — `H3_DISCOVERY` và điều kiện có hiệu lực.
- [HttpOption.Http3DiscoveryMode, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html) — ngữ nghĩa `ANY`, `ALT_SVC`, `HTTP_3_URI_ONLY`.
- [HttpRequest.Builder, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — request version, `setOption` và timeout.
- [HttpResponse, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.html) — `version()` và response URI.
- [java.net.http Module Summary, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/module-summary.html) — logging HTTP/3, QUIC và QPACK implementation properties.
- [HttpOption.Http3DiscoveryMode, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html) — xác nhận các discovery mode tiếp tục có trong JDK 27.
- [HTTP Client Updates in Java 26 — Inside.java](https://inside.java/2026/03/04/jdk-26-http-client/) — ví dụ các chiến lược chuyển đổi HTTP/1.1/2 sang HTTP/3.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) — đặc tả HTTP/3.
- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000) — transport QUIC.
- [RFC 7838 — HTTP Alternative Services](https://www.rfc-editor.org/rfc/rfc7838) — cơ chế Alt-Svc discovery.
