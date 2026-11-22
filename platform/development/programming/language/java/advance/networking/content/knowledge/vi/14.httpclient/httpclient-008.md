# HTTP/3 từ JDK 26: phiên bản, HttpOption và cơ chế khám phá

**Chủ đề:** Java Advance - networking  
**Nhóm:** HttpClient

Từ **JDK 26**, thư viện chuẩn **java.net.http.HttpClient** hỗ trợ **HTTP/3** nhờ **JEP 517**. Đây là bổ sung ở tầng protocol, không phải thay thế cách viết HttpClient: ứng dụng vẫn tạo **HttpClient**, **HttpRequest**, gọi **send()** hoặc **sendAsync()**, rồi đọc **HttpResponse**. Điểm cần hiểu sâu là: **HTTP_3 là phiên bản ưu tiên**, còn **HttpOption.H3_DISCOVERY** quy định chiến lược tìm/thiết lập đường HTTP/3. Kết quả cuối cùng phải kiểm tra qua **response.version()**; không được suy từ thiết lập preference rằng mỗi request chắc chắn chạy qua QUIC.

Các quy tắc cốt lõi:

1. **HttpClient.Version.HTTP_3** chỉ có từ **Java 26**.
2. **HttpOption<T>**, **HttpOption.H3_DISCOVERY**, **HttpOption.Http3DiscoveryMode** và **HttpRequest.Builder.setOption(...)** là các API mới từ Java 26.
3. **HttpClient mặc định vẫn ưu tiên HTTP/2**, kể cả trên JDK 26. Không có chuyện tự chuyển tất cả request cũ sang H3 khi nâng JDK.
4. Chỉ đặt **H3_DISCOVERY** mà **không chọn HTTP_3 tại client hoặc request** thì option **không có tác dụng**.
5. **ANY** linh hoạt và có thể fallback; **ALT_SVC** học H3 qua HTTP Alternative Services; **HTTP_3_URI_ONLY** chỉ thử QUIC/H3 trực tiếp tới authority của request URI, không fallback H2/H1.
6. Built-in JDK 26 HttpClient chỉ sử dụng HTTP/3 cho URI scheme **https** và hiện không hỗ trợ **HTTP/3 qua proxy**.
7. Mã HTTP 2xx/4xx/5xx vẫn là response ở tầng ứng dụng; lỗi DNS, UDP path, TLS/QUIC hoặc timeout là lỗi transport/client, có thể không có HttpResponse.

Trong bài có **mã Java 26** minh họa API mới và **mã Java 17** đã biên dịch/chạy trên JDK 24 để kiểm chứng khác nhau giữa phiên bản ưu tiên và phiên bản thực tế. Ví dụ cần JDK 26 được ghi rõ về yêu cầu môi trường và không tự nhận là đã chạy nếu không có JDK 26.

## 1. HTTP/3 thực chất là gì?

HTTP/1.1 và HTTP/2 phổ biến chạy trên **TCP**. HTTPS sử dụng TLS trên TCP. HTTP/3 lại vận chuyển HTTP trên **QUIC**, và QUIC chạy trên **UDP**. QUIC tích hợp bảo vệ **TLS 1.3**, có cơ chế multiplex các streams, flow control, kiểm soát tắc nghẽn và phục hồi mất gói.

~~~text
HTTP/2                           HTTP/3
+-------------------+           +-------------------+
| HTTP semantics    |           | HTTP semantics    |
| request/response  |           | request/response  |
+-------------------+           +-------------------+
| H2 frames + HPACK |           | H3 frames + QPACK |
+-------------------+           +-------------------+
| TLS over TCP      |           | QUIC with TLS 1.3 |
+-------------------+           +-------------------+
| TCP               |           | UDP               |
+-------------------+           +-------------------+
| IP                |           | IP                |
+-------------------+           +-------------------+
~~~

| Vấn đề | HTTP/2 | HTTP/3 |
| --- | --- | --- |
| Transport | TCP byte stream | QUIC qua UDP |
| Multiplexing | Nhiều HTTP streams trên một TCP connection | Nhiều HTTP streams trên một QUIC connection |
| Header compression | HPACK | QPACK |
| Mất gói | TCP head-of-line blocking có thể làm trễ tất cả H2 streams của cùng connection | QUIC hạn chế transport-level HOL **giữa** các streams; vẫn chịu loss/congestion |
| HTTPS encryption | TLS qua TCP | TLS 1.3 trong QUIC |
| Hạ tầng cần thiết | TCP/TLS listener | QUIC listener, đường UDP, TLS/ALPN phù hợp |
| Lợi ích | Hệ sinh thái triển khai rộng | Có thể giảm một số độ trễ và tránh các trường hợp HOL trên TCP |

**Không suy ra HTTP/3 chắc chắn nhanh hơn HTTP/2.** Trong mạng chặn UDP, qua enterprise proxy hoặc trên một service chưa bật QUIC, thử HTTP/3 có thể tốn thời gian rồi mới fallback. Trên mạng ổn định với connection reuse tốt, chênh lệch hiệu năng có thể nhỏ. Cần đo **latency, negotiated version, errors và retries** theo workload thật.

**HTTP semantics không biến mất:** URI, methods GET/POST, status 200/404/503, headers, caching, body và business protocol vẫn cần được xử lý đúng. HTTP/3 không thay thế authentication, idempotency key, timeout hay thiết kế API.

## 2. JDK 26 có những API mới nào?

| API | Vai trò | Mốc |
| --- | --- | --- |
| **HttpClient.Version.HTTP_3** | Giá trị enum để lựa chọn HTTP/3 làm preferred version | Java 26 |
| **HttpOption<T>** | Interface sealed cho request configuration hints | Java 26 |
| **HttpOption.H3_DISCOVERY** | Option cấu hình cách tìm/thiết lập H3 | Java 26 |
| **HttpOption.Http3DiscoveryMode.ANY** | Chọn chiến lược implementation-specific, có thể dùng direct QUIC và fallback | Java 26 |
| **HttpOption.Http3DiscoveryMode.ALT_SVC** | Chỉ dùng Alt-Svc để khám phá H3 | Java 26 |
| **HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY** | Chỉ thử H3 tại host/port từ URI, không Alt-Svc hoặc fallback | Java 26 |
| **HttpRequest.Builder.setOption(option, value)** | Cấu hình hint cho từng request | Java 26 |
| **HttpRequest.getOption(option)** | Đọc hint đã lưu trên HttpRequest | Java 26 |

Các API cũ **HttpClient.Builder.version(...)**, **HttpRequest.Builder.version(...)**, **HttpClient.send(...)**, **sendAsync(...)**, **HttpResponse.statusCode()** và **HttpResponse.version()** vẫn giữ mô hình quen thuộc.

**Không có một class Http3Client tách biệt** trong API chuẩn của JEP 517. Ở JDK 26, **HttpOption** là sealed interface và chỉ cung cấp option **H3_DISCOVERY**; không tự tạo một option tùy ý rồi giả định built-in HttpClient hiểu. **setOption** là hint để implementation quyết định xử lý: với implementation khác built-in, option không hiểu có thể bị bỏ qua hoặc gây lỗi theo hợp đồng.

### Bốn tầng nên phân biệt

~~~text
HttpClient configuration
  preferred version: HTTP_2 (default) hoặc HTTP_3
             │
             ▼
HttpRequest configuration
  optional preferred version: override cấp client
  optional H3_DISCOVERY: ANY / ALT_SVC / HTTP_3_URI_ONLY
             │
             ▼
Implementation + network
  cached connections, Alt-Svc, QUIC/UDP, TCP/TLS, proxy, timeout
             │
             ▼
HttpResponse.version()
  HTTP_3, HTTP_2 hoặc HTTP_1_1 nếu response thành công
~~~

**Preferred version** là sở thích, **discovery mode** là cách chọn đường kết nối, **actual version** là kết quả. Không được gộp ba khái niệm thành một.

## 3. Chọn HTTP_3 ở cấp client hay cấp request

### Cấp client

~~~java
// Snippet Java 26+, import java.net.http.HttpClient.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();
~~~

Mọi request không đặt version riêng sẽ kế thừa **HTTP_3 preferred** từ client. Một instance HttpClient thường được tái sử dụng để hưởng connection pools, thông tin Alt-Svc đã biết và giảm chi phí thiết lập kết nối.

### Cấp request

~~~java
// Snippet Java 26+, import URI, HttpClient và HttpRequest.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/health"))
        .version(HttpClient.Version.HTTP_3)
        .GET()
        .build();
~~~

Request này ưu tiên HTTP_3 ngay cả khi client được tạo mặc định HTTP_2. Ngược lại, một request **version(HTTP_2)** sẽ override client **version(HTTP_3)** cho riêng request ấy.

| Client preference | Request preference | Preference có hiệu lực với request |
| --- | --- | --- |
| Không đặt (mặc định HTTP_2) | Không đặt | HTTP_2 |
| HTTP_3 | Không đặt | HTTP_3 |
| HTTP_2 | HTTP_3 | HTTP_3 |
| HTTP_3 | HTTP_2 | HTTP_2 |
| HTTP_3 | HTTP_1_1 | HTTP_1_1 |

**Không gọi HTTP_3 là hard requirement** khi chỉ set version. Javadoc nêu rõ phiên bản được chọn thực tế phụ thuộc nhiều điều kiện. Với built-in implementation, **H3_DISCOVERY=ANY** là chiến lược mặc định khi đã chọn HTTP_3; kết quả có thể là H3, H2 hoặc H1.

### Kiểm tra version

~~~java
// Snippet: client, request, response đã tồn tại.
System.out.println(client.version());   // Preferred tại client.
System.out.println(request.version());  // Optional preferred tại request.
System.out.println(response.version()); // Phiên bản thực của response.
~~~

**HttpRequest.version()** là Optional và có thể rỗng nếu request không set version riêng. Khi rỗng, client preference được dùng. **HttpResponse.version()** sau một lần send thành công mới là chứng cứ request/response thực sự đã chạy trên protocol nào. Đừng dùng **statusCode() == 200** làm bằng chứng HTTP/3 vì HTTP/1.1, HTTP/2 và HTTP/3 đều có thể trả 200.

## 4. HttpOption.H3_DISCOVERY hoạt động thế nào?

**HttpOption.H3_DISCOVERY** có kiểu **HttpOption<HttpOption.Http3DiscoveryMode>**. Đặt nó trên **HttpRequest.Builder** bằng API generic:

~~~java
// Snippet Java 26+.
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/api"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ALT_SVC)
        .GET()
        .build();
~~~

**Lưu ý tối quan trọng:** Nếu **cả** HttpClient lẫn HttpRequest không chọn **HTTP_3** làm preferred version, tùy chọn **H3_DISCOVERY bị bỏ qua**. Hình thức dưới đây **không** kích hoạt H3 với client mặc định:

~~~java
// Đúng cú pháp nhưng H3_DISCOVERY không có tác dụng nếu
// client cũng mặc định HTTP_2.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/"))
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ALT_SVC)
        .GET()
        .build();
~~~

**Cách sửa:** thêm **version(HttpClient.Version.HTTP_3)** ở request hoặc client. Đừng copy mẫu chỉ có **setOption** rồi kết luận JDK không hỗ trợ H3.

**Option không phải HTTP request header.** Không làm **header("H3_DISCOVERY", "ALT_SVC")** để thay thế; HTTP/3 discovery là hint của Java implementation, không phải nội dung gửi qua HTTP. **getOption(HttpOption.H3_DISCOVERY)** trả Optional của hint được cấu hình, không chứng minh đã mở kết nối QUIC.

Với built-in Java 26, nếu chọn HTTP_3 và không có hint H3_DISCOVERY, chiến lược mặc định là **ANY**. Trong trường hợp redirect, Javadoc cho biết hint H3_DISCOVERY (nếu có) được chuyển sang request mới, nhưng đường đi và actual version vẫn có thể thay đổi theo URI/proxy.

## 5. Discovery mode ANY: linh hoạt và chấp nhận fallback

**Http3DiscoveryMode.ANY** cho phép implementation tự tìm hoặc thiết lập đường HTTP phù hợp. JDK built-in **có thể**:

- Thử kết nối **HTTP/3 qua QUIC/UDP** tại authority trong request URI.
- Đồng thời hoặc theo lịch riêng thử **HTTP/2 qua TLS/TCP**, rồi chọn đường phù hợp.
- Khi request đặt **HTTP_3** tường minh, có thể ưu tiên thử H3 trước đường TCP.
- Tận dụng **Alt-Svc** đã học từ origin; khi chưa có Alt-Svc, có thể thử direct QUIC ở host/port của request URI.
- Khi H3 không khả dụng mà fallback được phép, xử lý request qua HTTP_2 hoặc HTTP_1_1.

~~~java
// JDK 26+: ANY tường minh.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ANY)
        .GET()
        .build();
~~~

**ANY là thuật toán implementation-specific**, không phải lời hứa sẽ luôn mở QUIC trước, sẽ luôn race hai kết nối, hay sẽ gửi hai HTTP requests nghiệp vụ trùng nhau. Mỗi môi trường có thể dùng lại connection pool hoặc đường đã thiết lập. **Actual version chỉ biết sau response.**

**Khi dùng:** muốn thử H3 tại những nơi hỗ trợ nhưng vẫn phục vụ clients ở mạng không cho UDP. Đây là một lựa chọn cho migration và rollout có giám sát. **Không** dùng ANY để viết test khẳng định request bắt buộc phải là HTTP_3.

## 6. Discovery mode ALT_SVC: học từ quảng bá của origin

**Http3DiscoveryMode.ALT_SVC** yêu cầu chỉ dựa trên **HTTP Alternative Services** để tìm/thiết lập đường HTTP/3. Ban đầu, nếu client chưa biết một h3 alternative service phù hợp, request có thể dùng **HTTP/2 hoặc HTTP/1.1**. Server quảng bá qua HTTP response header:

~~~http
HTTP/1.1 200 OK
Alt-Svc: h3=":443"; ma=3600
Content-Type: text/plain

hello
~~~

**Alt-Svc** không phải HTTP redirect. Ý nghĩa:

- **h3** là protocol identifier dành cho HTTP/3.
- **":443"** chỉ alternative service cùng hostname tại port 443 theo cú pháp Alt-Svc.
- **ma=3600** quảng bá max-age tính bằng **giây**; việc lưu/áp dụng advertisement phụ thuộc chính sách và implementation.
- **URI resource** trong ứng dụng vẫn đại diện **cùng origin**, không phải đổi sang đường dẫn resource mới.
- Server có thể quảng bá H3 khi trả 200 qua HTTP/2; lần request kế tiếp có thể dùng H3 nếu advertisement được chấp nhận và đường QUIC hoạt động.

~~~text
Lượt 1: Client ưu tiên HTTP_3, mode ALT_SVC, chưa biết Alt-Svc
         |
         +--> TCP/TLS => HTTP/2 hoặc HTTP/1.1
                      |
                      +-- Server trả Alt-Svc: h3=":443"; ma=3600
                            |
                            v
Lượt 2: Cùng client, cùng origin => có thể thử QUIC/H3
         |
         +--> Thành công: response.version() = HTTP_3
         +--> Chưa/không dùng H3: H2 hoặc H1 theo lựa chọn hợp lệ
~~~

~~~java
// JDK 26+: chọn HTTP_3 ở client thì hint mới có tác dụng.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/"))
        .setOption(HttpOption.H3_DISCOVERY, Http3DiscoveryMode.ALT_SVC)
        .GET()
        .build();
~~~

**Đừng giả định request đầu tiên dùng H3** chỉ vì origin thực sự hỗ trợ H3. Ở ALT_SVC, client phải biết advertisement phù hợp trước, thường thông qua HTTP response ở lần trước. **Không** có guarantee rằng lần 2 chắc chắn dùng H3; có thể advertisement chưa được áp dụng, đã hết hạn, không đủ điều kiện, connection cache được tái sử dụng hoặc network UDP/TLS không thành công.

### Alt-Svc khác HTTP 302

| Alt-Svc | HTTP Redirect |
| --- | --- |
| Quảng bá endpoint **alternative protocol service** cho cùng origin | Chỉ URI khác cho resource/request |
| Thường nằm trong response 200 hoặc response phù hợp khác | Thường status 301/302/303/307/308 với Location |
| Không đổi resource URI theo nghĩa HTTP | Có thể tạo request tới URI mới |
| Hữu ích cho chuyển H2 ↔ H3 | Hữu ích cho điều hướng URI/resource |
| Cần kiểm tra alternative service hợp lệ cho origin | Cần áp redirect policy, credentials và scheme restrictions |

**Security:** Alt-Svc không cấp quyền bỏ qua certificate validation. QUIC/TLS phải xác thực peer phù hợp với **origin**. Không lấy bất kỳ Alt-Svc header không tin cậy rồi tắt hostname verification.

## 7. Discovery mode HTTP_3_URI_ONLY: strict H3, direct URI authority

**Http3DiscoveryMode.HTTP_3_URI_ONLY** yêu cầu thử **HTTP/3 trực tiếp ở authority của request URI**: host và port do URI xác định. **Không** dùng Alt-Svc để tìm host/port khác, **không** fallback HTTP/2 hoặc HTTP/1.1 nếu không lập được kết nối QUIC/H3.

~~~java
// JDK 26+: strict mode có hiệu lực vì chọn preferred HTTP_3.
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example:443/ping"))
        .version(HttpClient.Version.HTTP_3)
        .setOption(HttpOption.H3_DISCOVERY,
                Http3DiscoveryMode.HTTP_3_URI_ONLY)
        .GET()
        .build();
~~~

**Điều kiện:** đúng HTTPS URI, server phải lắng nghe QUIC/H3 tại **host:port** này, đường UDP có thể tới đích, TLS/ALPN/certificate phù hợp và không mắc ràng buộc proxy bị JDK từ chối. Nếu không đạt, request có thể ném exception.

**HTTP_3_URI_ONLY không có nghĩa cứ chọn HTTP_3 thì strict.** Chỉ khi **đặt option strict** cùng HTTP_3 preference mới áp dụng policy này. Chỉ dùng **version(HTTP_3)** và không đặt option tương đương **ANY** với built-in implementation.

### Alt-Svc chỉ port khác thì sao?

Giả sử origin **https://service.example/** quảng bá:

~~~http
Alt-Svc: h3=":8443"; ma=3600
~~~

- **ALT_SVC** có thể dùng advertisement tới H3 port 8443 sau khi đã biết/được chấp nhận.
- **ANY** có thể dùng advertisement ấy hoặc direct QUIC theo thuật toán.
- **HTTP_3_URI_ONLY** **bỏ qua Alt-Svc**, chỉ thử trực tiếp authority trong URI, tức port HTTPS mặc định 443. Nếu server chỉ mở QUIC 8443, strict URI_ONLY có thể thất bại.

**Khi dùng:** test endpoint đã biết có QUIC tại host/port, hoặc chính sách bắt buộc H3. **Không** bật trên mọi request của sản phẩm nếu mạng khách hàng có thể chặn UDP và ứng dụng vẫn cần fallback.

## 8. Ma trận hành vi cần ghi nhớ

| Client/request config | Discovery mode | Client thực sự có thể làm |
| --- | --- | --- |
| Cả hai không đặt HTTP_3 | H3_DISCOVERY absent | Default HTTP_2, có thể fallback HTTP_1_1 |
| Cả hai không đặt HTTP_3 | ALT_SVC hay URI_ONLY | **Option không có tác dụng** |
| Một trong hai chọn HTTP_3 | Không đặt option | Built-in xử lý như **ANY** |
| Một trong hai chọn HTTP_3 | ANY | Có thể H3, H2 hoặc H1 |
| Một trong hai chọn HTTP_3 | ALT_SVC | Trước khi biết h3 Alt-Svc, thường H2/H1; sau đó có thể H3 |
| Một trong hai chọn HTTP_3 | HTTP_3_URI_ONLY | Chỉ direct H3 tại URI; không fallback |
| Client chọn HTTP_3, request chọn HTTP_2 | Bất kỳ H3_DISCOVERY | Request preferred HTTP_2; hint H3 không có tác dụng |
| H3 preferred nhưng URI **http://** | ANY/ALT_SVC/URI_ONLY | **Không** gửi qua HTTP/3 |
| H3 preferred, HTTP proxy được chọn | ANY/ALT_SVC | JDK 26 built-in hạ về H2/H1, bỏ qua hint |
| H3 preferred, HTTP proxy được chọn | URI_ONLY | Built-in request thất bại |

**Ghi nhớ về proxy:** phần giới hạn này là **JDK 26 built-in implementation note**; không khẳng định mọi vendor/provider hoặc tương lai đều không thể triển khai HTTP/3 qua proxy. JDK 26 mặc định **không** có HTTP/3 qua proxy. Những môi trường buộc phải dùng corporate proxy có thể thấy request H3 preferred quay về HTTP/2/H1.

### Câu hỏi thường gặp: có phải ANY gửi hai POST song song?

**Không được kết luận vậy.** Javadoc mô tả việc thiết lập/so sánh đường **kết nối transport**, không hứa application tự gửi hai POST nghiệp vụ trùng nhau. Với một POST tạo tác dụng phụ, việc retry sau timeout vẫn phải tuân thủ **idempotency key, request IDs và business contract**. Không suy luận application outcome từ thuật toán connection discovery.

## 9. Chương trình JDK 26 không cần Internet: kiểm tra cấu hình

Demo này sử dụng **HTTP_3**, **HttpOption** và **getOption** của **JDK 26+**, nhưng **không thực hiện request**. Dùng để xác minh API version và option theo kiểu an toàn, không phụ thuộc server H3 ngoài Internet.

Tạo file **Http3Options26.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;

public class Http3Options26 {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .build()) {

            HttpRequest req = HttpRequest.newBuilder(
                    URI.create("https://example.com/"))
                    .version(HttpClient.Version.HTTP_3)
                    .setOption(HttpOption.H3_DISCOVERY,
                            Http3DiscoveryMode.ALT_SVC)
                    .GET()
                    .build();

            System.out.println("clientPreferred=" + client.version());
            System.out.println("requestPreferred=" +
                    req.version().orElseThrow());
            System.out.println("discovery=" +
                    req.getOption(HttpOption.H3_DISCOVERY).orElseThrow());
            System.out.println("scheme=" + req.uri().getScheme());
        }
    }
}
~~~

Biên dịch **bằng JDK 26 trở lên**, với release **26**:

~~~bash
javac --release 26 -encoding UTF-8 Http3Options26.java
java Http3Options26
~~~

**Output dự kiến theo contract công khai của JDK 26** (không được thực thi trên JDK 26 trong môi trường kiểm tra bài):

~~~text
clientPreferred=HTTP_3
requestPreferred=HTTP_3
discovery=ALT_SVC
scheme=https
~~~

**Giải thích:** các getter đọc cấu hình client/request. Chưa có HTTP response nên không thể khẳng định server example.com hỗ trợ H3 hay đã mở QUIC. **getOption(H3_DISCOVERY)** cho thấy request chứa hint **ALT_SVC**, không đồng nghĩa protocol đã được chọn.

**Lý do dùng JDK 26:** **HttpClient.Version.HTTP_3**, **HttpOption**, **Builder.setOption** và **HttpRequest.getOption** chưa có ở JDK 24/Java 17. Nếu lấy javac 24 hoặc **--release 17** để biên dịch, sẽ gặp compile error vì API không tồn tại; đó là đúng cơ chế bảo vệ API version, không phải bug của ví dụ.

## 10. Chương trình JDK 26 quan sát live actual HTTP version

Khi có **JDK 26+** và một endpoint HTTPS hợp lệ, chương trình sau cho phép chọn discovery mode, gửi **hai GET liên tiếp qua cùng HttpClient** và quan sát **response.version()**. Điều này hữu ích với ALT_SVC vì advertisement thường được học từ response trước.

Tạo file **Http3LiveProbe26.java**:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpOption.Http3DiscoveryMode;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class Http3LiveProbe26 {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java Http3LiveProbe26 <https-url> <ANY|ALT_SVC|HTTP_3_URI_ONLY>");
        }
        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("HTTPS URI required for HTTP/3");
        }
        Http3DiscoveryMode mode = Http3DiscoveryMode.valueOf(args[1]);

        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build()) {

            HttpRequest req = HttpRequest.newBuilder(uri)
                    .version(HttpClient.Version.HTTP_3)
                    .setOption(HttpOption.H3_DISCOVERY, mode)
                    .timeout(Duration.ofSeconds(15))
                    .GET().build();

            System.out.println("clientPreferred=" + client.version());
            System.out.println("requestPreferred=" +
                    req.version().orElseThrow());
            System.out.println("mode=" +
                    req.getOption(HttpOption.H3_DISCOVERY).orElseThrow());

            for (int i = 1; i <= 2; i++) {
                try {
                    HttpResponse<Void> response = client.send(
                            req, HttpResponse.BodyHandlers.discarding());

                    System.out.println("attempt=" + i
                            + " actual=" + response.version()
                            + " status=" + response.statusCode());
                    System.out.println("altSvc=" +
                            response.headers().firstValue("Alt-Svc")
                                    .orElse("absent"));
                } catch (IOException e) {
                    System.out.println("attempt=" + i +
                            " transportFailure=" +
                            e.getClass().getSimpleName());
                    break;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw e;
                }
            }
        }
    }
}
~~~

Biên dịch và chạy với **JDK 26**:

~~~bash
javac --release 26 -encoding UTF-8 Http3LiveProbe26.java
java Http3LiveProbe26 https://www.example.org/ ANY
java Http3LiveProbe26 https://www.example.org/ ALT_SVC
java Http3LiveProbe26 https://www.example.org/ HTTP_3_URI_ONLY
~~~

**Không có stdout cố định** cho HTTP/3 qua mạng: endpoint có thể không hỗ trợ H3, dùng CDN/proxy, quảng bá Alt-Svc khác nhau, UDP có thể bị chặn, TLS/QUIC có thể không tương thích. Kết quả **minh họa có điều kiện**, không phải kết quả đã chạy với example.org:

~~~text
clientPreferred=HTTP_3
requestPreferred=HTTP_3
mode=ALT_SVC
attempt=1 actual=HTTP_2 status=200
altSvc=h3=":443"; ma=3600
attempt=2 actual=HTTP_3 status=200
altSvc=absent
~~~

Nếu request dùng **HTTP_3_URI_ONLY** đến server không lắng nghe QUIC ở URI authority, ứng dụng có thể in **transportFailure=...**. Không được thay thế điều đó bằng **status=505** vì khi chưa có response HTTP thì **không có HTTP status**. Ngược lại, status 404 trên một response HTTP_3 chỉ nghĩa là resource không được tìm thấy; tầng HTTP/3/QUIC vẫn đã hoạt động đủ để nhận response.

**Giới hạn QA:** ví dụ Java 26 sử dụng API được kiểm tra qua **Javadoc JDK 26**. Môi trường chạy thực tế đang có **JDK 24**, không có **HTTP_3** để biên dịch/chạy hai chương trình JDK 26. Chương trình ở phần 11 được biên dịch và chạy thật theo **--release 17**.

### Lưu ý khi dùng live probe

- **HttpClient** được tái sử dụng cho hai request; một client mới cho mỗi request có thể không giữ được thông tin discovery/connection reuse.
- Chỉ gửi **GET** đến endpoint do bạn được phép thử; không thay bằng POST có side effect mà không có idempotency.
- **Redirect.NEVER** giúp quan sát origin đã đưa vào; nếu follow redirect, actual response có thể thuộc host khác.
- **IOException** là transport/client failure; nguyên nhân cụ thể vẫn cần đọc cause/log để phân biệt UDP path, TLS, timeout hoặc proxy.
- H3_DISCOVERY option trong request **không phải response field**; **getOption()** cho biết cấu hình, **response.version()** mới cho biết protocol thực.
- Hai request không đủ chứng minh mọi request tương lai sẽ H3: cache lifetime, network conditions và load balancing có thể thay đổi.

## 11. Chương trình Java 17 đã kiểm thử: preferred không phải actual

Để chứng minh nguyên lý **preferred version ≠ actual version** một cách chạy được trên máy không có JDK 26, demo dùng HTTP server cục bộ **HTTP/1.1** và HttpClient mặc định ưu tiên HTTP_2. Kết quả thực từ response là HTTP_1_1. Mã cũng kiểm tra enum Version ở runtime có **HTTP_3** hay không bằng cách so tên, mà không tham chiếu API Java 26 tại compile time.

Tạo file **HttpVersionBaseline.java**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class HttpVersionBaseline {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/hello", exchange -> {
            try (exchange) {
                byte[] data = "OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, data.length);
                try (OutputStream stream = exchange.getResponseBody()) {
                    stream.write(data);
                }
            }
        });
        server.start();
        try {
            HttpClient client = HttpClient.newHttpClient();
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/hello");
            HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            System.out.println("preferred=" + client.version());
            System.out.println("requestVersionSet=" +
                    request.version().isPresent());
            System.out.println("http3EnumPresent=" + Arrays.stream(
                    HttpClient.Version.values())
                    .anyMatch(v -> v.name().equals("HTTP_3")));
            System.out.println("actual=" + response.version());
            System.out.println("status=" + response.statusCode());
            System.out.println("body=" + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 HttpVersionBaseline.java
java HttpVersionBaseline
~~~

**Stdout chính xác đã kiểm chứng trên JDK 24.0.2 khi biên dịch target Java 17:**

~~~text
preferred=HTTP_2
requestVersionSet=false
http3EnumPresent=false
actual=HTTP_1_1
status=200
body=OK
~~~

Vì sao?

- **preferred=HTTP_2** vì HttpClient mặc định ưu tiên HTTP/2.
- **requestVersionSet=false** vì request không override; nó dùng preference của client.
- **actual=HTTP_1_1** vì server demo chỉ nói HTTP/1.1 trên loopback và không có H2/H3.
- **http3EnumPresent=false** vì runtime kiểm thử là JDK 24; ở JDK 26 giá trị này dự kiến thành **true**.
- **status=200** và **body=OK** chứng tỏ response HTTP đến được, dù không dùng preferred version.

**com.sun.net.httpserver.HttpServer** trong module **jdk.httpserver** chỉ dùng làm HTTP/1.1 test fixture; **không phải một HTTP/3 server**. Demo này không thử QUIC. Với flag **--release 17**, HttpClient chưa là **AutoCloseable** ở API Java 17, nên mã không bọc HttpClient trong try-with-resources; điều đó đảm bảo biên dịch target Java 17 thật sự. Hai demo Java 26 có thể dùng try-with-resources cho HttpClient theo Javadoc mới.

## 12. Điều kiện thực tế để dùng HTTP/3

### 12.1. URI phải là HTTPS trong built-in JDK 26 HttpClient

Các request có URI scheme khác **https** sẽ **không** được gửi qua HTTP/3. Chỉ gọi **version(HTTP_3)** trên **http://** URI không tự tạo một HTTPS upgrade. HTTP redirect, HSTS, TLS và HTTP/3 preference là các cơ chế khác nhau.

### 12.2. HTTP/3 cần UDP path và QUIC listener

TCP/443 hoạt động không bảo đảm UDP/443 hoạt động. Firewall, NAT, VPN, load balancer, container ingress, cloud egress hoặc corporate proxy có thể chặn UDP. Với server chỉ có TCP-based HTTPS listener:

- **ANY** có thể dùng H2/H1.
- **ALT_SVC** có thể chỉ dùng H2/H1 nếu không có advertisement H3 hoặc QUIC không hoạt động.
- **HTTP_3_URI_ONLY** sẽ không âm thầm fallback xuống H2/H1.

### 12.3. TLS, certificate, ALPN và policy

QUIC tích hợp TLS 1.3 và cần certificate/hostname verification phù hợp. **Alt-Svc không cho phép bỏ qua trust manager/hostname check**, vì alternative service phải có thẩm quyền phục vụ origin. **ALPN** với identifier **h3** liên quan thỏa thuận protocol; nó khác hoàn toàn **HttpOption.H3_DISCOVERY** (hint lựa chọn ở phía ứng dụng Java).

Custom **SSLContext** hoặc **SSLParameters** không tương thích có thể làm HTTP/3 không sử dụng được; Javadoc nhắc tới **UnsupportedProtocolVersionException** trong một số trường hợp, đặc biệt khi strict HTTP_3_URI_ONLY hoặc khi xây client. Không nới lỏng TLS chỉ để “ép” benchmark H3.

### 12.4. Proxy trong built-in JDK 26

Ở implementation được tài liệu hóa, **HTTP/3 qua proxy chưa được hỗ trợ**. Nếu một proxy được chọn cho URI:

- Với **ANY** hoặc **ALT_SVC**, protocol hạ về **HTTP/2 hoặc HTTP/1.1**, hint H3_DISCOVERY bị bỏ qua.
- Với **HTTP_3_URI_ONLY**, request **thất bại**.

Không nói việc fallback qua proxy chứng minh HTTP/3 server không hoạt động; đó có thể là giới hạn transport path của Java client.

### 12.5. Alt-Svc và lifetime

Một Alt-Svc response header có thể quảng bá protocol/port thay thế với max-age. Client có thể dùng thông tin đã học trong các request sau. Trạng thái này không phải redirect cache hay DNS; không phải mọi h3 advertisement sẽ được dùng vĩnh viễn. Origin, certificate, cache lifetime, connection pooling và policy có vai trò quan trọng. **Không tự thêm Alt-Svc header vào request để bắt server trả H3**.

### 12.6. Redirect và version

Trong built-in JDK 26, **H3_DISCOVERY** được truyền cho request redirect nếu đã cấu hình. Tuy nhiên request sau có thể có **URI khác**, proxy khác và điều kiện hỗ trợ H3 khác. **response.version()** của response cuối mới chỉ ra version thực sự cho exchange được quan sát. Cần chú ý method preservation, credentials và redirect policy cho API có dữ liệu nhạy cảm.

## 13. Phân biệt lỗi HTTP với lỗi thiết lập H3

Một **HttpResponse** trả 200, 404, 429 hoặc 503 vẫn là HTTP response, bất kể actual version là H3, H2 hay H1. Một exception trong QUIC setup, TLS handshake hoặc connect không có nghĩa server “trả 503”.

| Hiện tượng | Có HttpResponse? | Diễn giải |
| --- | --- | --- |
| HTTP_3 response 200 | Có | Request thành công theo HTTP semantics |
| HTTP_2 response 200 trong mode ANY | Có | Fallback/đường TCP hợp lệ; không phải tự thân lỗi |
| HTTP_3 response 404 | Có | HTTP resource không tìm thấy, H3 vẫn đã hoạt động |
| HTTP_2 response 503 | Có | Server/gateway trả Service Unavailable |
| URI_ONLY thất bại do chặn UDP | Thường không có | Transport failure, có thể timeout/IOException |
| QUIC/TLS hostname certificate không hợp lệ | Không có response HTTP hoàn chỉnh từ request | TLS/client failure |
| DNS resolution error | Không có | Lỗi DNS/connection |
| Client timeout trong quá trình chọn đường | Không có response hoàn chỉnh từ send | Chưa biết request có side effect hay không |
| Redirect sang host mới bị lỗi DNS | Lần send có thể ném exception | Không tự tạo status 502/504 giả |

**Không gán status code = 0, 500 hoặc 505 để giả làm server response.** Nếu framework cần mã nội bộ, đặt trong trường riêng **transportError**, giữ **status** là absent. Đặc biệt với request POST, timeout/connection failure không chứng minh server chưa xử lý: cần idempotency key và kiểm tra trạng thái nghiệp vụ trước khi gửi lại.

## 14. Hướng dẫn rollout và observability

1. **Kiểm tra toolchain:** JDK 26+ được dùng cả khi build và chạy phần API mới. Không biên dịch HttpOption bằng javac 24 hoặc **--release 17**.
2. **Kiểm tra server:** endpoint HTTPS có QUIC/H3 listener thực, đường UDP và TLS/ALPN/certificate đúng. Một server **HttpServer** của JDK chỉ nói HTTP/1.1 không thể chứng minh H3.
3. **Bật dần HTTP_3:** tại client hoặc một số requests; bắt đầu ANY/ALT_SVC theo mục tiêu migration.
4. **Đo actual version:** thống kê **response.version()** theo HTTP_3, HTTP_2, HTTP_1_1. Preferred không phải metric negotiated.
5. **Đo errors:** Quic/TLS errors, timeouts, DNS/connect, proxy use, response statuses và retry. Không gộp transport failures vào 5xx.
6. **Sử dụng client lâu dài:** tái sử dụng pool và discovery information. Không tạo HttpClient mới cho từng request nếu không có lý do.
7. **Test strict:** chỉ dùng HTTP_3_URI_ONLY trên endpoint đã biết H3 direct, xác định rõ behavior khi UDP bị chặn.
8. **Giới hạn retry:** dùng exponential backoff+jitter có hạn, hỗ trợ idempotency và bảo vệ khỏi retry storm.
9. **Giữ bảo mật:** certificate/truststore đúng, không vô hiệu hóa TLS hostname verification, kiểm soát logs và secret.
10. **Có rollback:** có thể hạ request/client preference về HTTP_2 khi rollout H3 gây lỗi hoặc latency tăng.

### Các thông tin nên ghi khi debug

~~~text
preferred_client_version=HTTP_3
request_preferred_version=HTTP_3
discovery_mode=ANY
actual_response_version=HTTP_2
http_status=200
transport_failure=none
proxy_selected=true_or_false
latency_ms=...
~~~

Trường hợp lỗi transport:

~~~text
preferred_client_version=HTTP_3
discovery_mode=HTTP_3_URI_ONLY
actual_response_version=absent
http_status=absent
transport_failure=IOException_or_subtype
endpoint=https://service.example
~~~

Giữ URI log ở mức an toàn (không log token/query nhạy cảm). JDK 26 có logging của java.net.http, bao gồm categories **http3** và **quic**, có thể bật có kiểm soát bằng property:

~~~bash
java -Djdk.httpclient.HttpClient.log=errors,requests,http3,quic Http3LiveProbe26 https://service.example/ ANY
~~~

Đây là command minh họa khi đã có JDK 26 và endpoint thực. Log có thể chứa metadata nhạy cảm; không bật verbose debug liên tục ở production.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| JDK26 tự bật H3 cho mọi HttpClient | Triển khai không đổi protocol | Default vẫn **HTTP_2** |
| Chỉ set H3_DISCOVERY là đủ | Option bị bỏ qua | Chọn **HTTP_3** tại client/request |
| version(HTTP_3) bảo đảm H3 | Vẫn nhận HTTP_2/HTTP_1_1 | Phân biệt preferred vs actual |
| ANY luôn mở QUIC trước | Dự đoán latency sai | ANY là implementation-specific |
| ALT_SVC có nghĩa HTTP 302 redirect | Sai đường đi URI và security | Alt-Svc quảng bá alternative service, không chuyển resource |
| Có Alt-Svc là lần kế sẽ H3 chắc chắn | Sai metrics | Có thể không dùng alt service |
| HTTP_3_URI_ONLY sẽ tìm port từ Alt-Svc | Strict mode thất bại bất ngờ | URI_ONLY chỉ dùng authority URI |
| Chỉ có TCP/443 là H3 chạy được | UDP/QUIC không kết nối | Kiểm tra UDP listener/egress |
| HTTP3 chạy trên TCP | Kiến trúc mạng sai | HTTP/3 dùng QUIC/UDP |
| Proxy thường tự hỗ trợ H3 trong JDK26 | Strict fail hoặc H2 fallback | Xem JDK implementation note |
| TLS certificate không quan trọng vì QUIC | Nguy cơ MITM | TLS 1.3/identity verification vẫn cần |
| response có 200 nghĩa dùng HTTP_3 | Monitoring sai | Xem **response.version()** |
| Strict H3 fail nghĩa server trả 505 | Tự tạo mã HTTP giả | Phân biệt exception với HttpResponse |
| Dùng HttpServer cục bộ để test H3 | Test chỉ có H1 | Cần H3-capable server |
| Biên dịch Java26 API bằng --release17 | Compile failure | Dùng JDK26 và release26 |
| Retry POST sau timeout luôn an toàn | Có thể tạo side effect trùng | Idempotency key và business state |

## 16. Bài tập tự thực hành

1. Trên JDK 26, tạo client mặc định và client **version(HTTP_3)**. So sánh **client.version()**; vì sao chưa thể kết luận đường network?
2. Tạo request **version(HTTP_3)** từ client mặc định HTTP_2; kiểm tra **request.version()** và **response.version()**.
3. Chọn **H3_DISCOVERY=ALT_SVC** nhưng quên chọn HTTP_3. Vì sao option không có hiệu lực? Sửa cả hai cách: client-level và request-level.
4. Cho server phát **Alt-Svc: h3=":443"; ma=3600**. Với cùng HttpClient và ALT_SVC, log version của hai request liên tiếp; vì sao lần đầu có thể là HTTP_2?
5. Server có QUIC chỉ ở port khác URI authority. Giải thích vì sao ALT_SVC có thể dùng port đó còn HTTP_3_URI_ONLY có thể thất bại.
6. Cấu hình **HTTP_3_URI_ONLY** đến server không mở UDP/QUIC. Kiểm tra exception; vì sao không được tự chuyển thành status 505?
7. Bật HTTP proxy trong môi trường thử nghiệm. So sánh ANY, ALT_SVC và URI_ONLY theo implementation notes của JDK 26.
8. Dùng HTTPS URI và HTTP URI với HTTP_3 preferred. Request nào có thể chạy HTTP/3 theo JDK built-in?
9. Chạy **HttpVersionBaseline.java** trên JDK24 và JDK26; so giá trị **http3EnumPresent**, nhưng giải thích vì sao actual vẫn HTTP_1_1 trên server demo.
10. Tạo dashboard phân loại **actual HTTP_3/HTTP_2/HTTP_1_1**, percent of fallback, UDP failures, p95 latency, timeout và status codes; đề xuất quy tắc rollback.
11. Vì sao **ANY** không tự cho phép retry POST có side effect khi client gặp IOException? Đề xuất idempotency key theo API contract.
12. Đọc RFC 9114, RFC 9000 và RFC 7838. Tóm tắt khác biệt HTTP/3, QUIC và Alt-Svc.

## 17. Checklist ngắn trước khi sử dụng

- [ ] JDK 26+ ở runtime/toolchain, không dùng API mới dưới --release17?
- [ ] Chọn HTTP_3 ở client hoặc request, không chỉ đặt H3_DISCOVERY?
- [ ] Đã chọn đúng ANY/ALT_SVC/HTTP_3_URI_ONLY theo policy?
- [ ] Biết ANY có thể fallback, ALT_SVC cần advertisement, URI_ONLY strict?
- [ ] HTTPS URI và origin hostname/certificate hợp lệ?
- [ ] UDP/QUIC listener và network path phù hợp?
- [ ] Không giả định HTTP/3 hoạt động qua proxy built-in JDK26?
- [ ] Dùng **response.version()** để xác minh actual?
- [ ] Có timeout, retry limits, idempotency và metrics?
- [ ] Test với server HTTP/3 thực và trường hợp UDP bị chặn?

**Kết luận:** HTTP/3 trên JDK 26 là mở rộng của **HttpClient** với **HTTP_3** và **HttpOption.H3_DISCOVERY**. **ANY** tối ưu tính linh hoạt; **ALT_SVC** dựa trên alternative service được quảng bá; **HTTP_3_URI_ONLY** ép H3 trực tiếp và không fallback. Tính đúng đắn cần được đánh giá trên **HttpResponse.version()**, không chỉ các getter cấu hình. HttpClient mặc định vẫn ưu tiên HTTP/2; chỉ **HTTPS + QUIC/UDP + server/TLS/proxy/network phù hợp** mới cho phép H3 theo implementation JDK 26.

### Tài liệu chính thức

- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517)
- [Java SE 26: HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 26: HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html)
- [Java SE 26: HttpOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.html)
- [Java SE 26: HttpOption.Http3DiscoveryMode](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html)
- [Java SE 26: HttpRequest.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 26: java.net.http module](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/module-summary.html)
- [Oracle JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
- [Inside Java: HTTP/3 Support in JDK 26](https://inside.java/2025/10/22/http3-support/)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 9000 — QUIC Transport](https://www.rfc-editor.org/rfc/rfc9000)
- [RFC 9001 — QUIC TLS](https://www.rfc-editor.org/rfc/rfc9001)
- [RFC 7838 — HTTP Alternative Services](https://www.rfc-editor.org/rfc/rfc7838)
- [RFC 9204 — QPACK](https://www.rfc-editor.org/rfc/rfc9204)