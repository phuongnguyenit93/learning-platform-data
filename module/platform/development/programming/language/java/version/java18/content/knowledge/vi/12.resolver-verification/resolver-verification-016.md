# Giữ nguyên hostname khi kết nối HTTPS để bảo toàn Host, SNI và xác minh chứng chỉ

## 1. Tình huống: resolver trả về IP, nhưng HTTPS cần tên miền

Giả sử dịch vụ được gọi bằng địa chỉ:

~~~text
https://service.example.test:8443/health
~~~

Ứng dụng sử dụng một resolver tùy chỉnh, hoặc một bản ghi DNS phục vụ kiểm thử, để ánh xạ `service.example.test` đến `127.0.0.1`. Địa chỉ IP này xác định **đích kết nối TCP**. Nó **không thay thế danh tính HTTPS** mà ứng dụng định truy cập.

Nếu lập trình viên đổi URI thành `https://127.0.0.1:8443/health` sau khi phân giải tên, ba tín hiệu quan trọng có thể thay đổi:

- **HTTP Host** (với HTTP/1.1), hoặc **HTTP/2 `:authority`**, thường chuyển sang IP.
- **TLS Server Name Indication (SNI)** có thể không còn gửi tên miền mong muốn.
- **Xác minh hostname của chứng chỉ TLS** sẽ dựa trên IP trong URI thay vì tên miền ban đầu.

Kết quả có thể là kết nối bị từ chối, được chuyển sang virtual host khác, hoặc thất bại khi kiểm tra chứng chỉ. Cố “sửa” bằng một HTTP `Host` header chưa giải quyết được TLS, vì TLS handshake diễn ra **trước** khi gửi HTTP request.

Quy tắc trung tâm của bài: **giữ nguyên hostname trong URI HTTPS và trong thông tin peer host dùng cho TLS; chỉ để resolver quyết định địa chỉ IP kết nối**.

Đây là một tình huống kiểm chứng thực tế của module Java 18: từ Java 18, `InetAddressResolverProvider` có thể tham gia phân giải địa chỉ của `InetAddress`. Khi kiểm thử resolver trên JDK hiện đại, cần quan sát đồng thời cả đích mạng và danh tính HTTPS, thay vì chỉ kiểm tra kết quả `InetAddress.getByName(...)`.

## 2. Phân biệt bốn giá trị trong một kết nối

Ví dụ một yêu cầu tới `https://service.example.test:8443/health`, trong đó resolver ánh xạ tên miền sang loopback cho môi trường lab:

| Thuộc tính | Giá trị mong muốn | Mục đích |
| --- | --- | --- |
| **Hostname logic** | `service.example.test` | Danh tính dịch vụ ứng dụng muốn truy cập. |
| **IP đích** | `127.0.0.1` | Địa chỉ dùng để mở kết nối TCP trong bài kiểm thử. |
| **TLS SNI** | `service.example.test` | Gợi ý cho server chọn cấu hình/chứng chỉ TLS theo tên máy. |
| **TLS reference identity** | `service.example.test` | Tên dùng để kiểm tra chứng chỉ của server. |
| **HTTP/1.1 Host** | `service.example.test:8443` | Authority mà ứng dụng HTTP yêu cầu; có kèm cổng không mặc định. |
| **HTTP/2 `:authority`** | `service.example.test:8443` | Authority tương ứng trên HTTP/2. |

Ở đây, hostname không có cổng, còn HTTP authority có thể có cổng. SNI cũng **không mang số cổng**. Chứng chỉ server cần khớp với tên DNS phù hợp trong Subject Alternative Name (SAN). Việc CA ký chứng chỉ đáng tin là điều kiện khác với việc SAN khớp hostname; một chứng chỉ có chuỗi tin cậy hợp lệ vẫn có thể **sai tên máy**.

SNI chỉ là thông tin định tuyến/cấu hình được gửi cho server trong TLS ClientHello; **SNI tự nó không xác thực server**. Bước xác minh chứng chỉ mới kiểm tra liệu server có thực sự đưa ra chứng chỉ hợp lệ cho hostname được yêu cầu hay không.

~~~mermaid
flowchart TD
    A["URI: https://service.example.test:8443/health"] --> B["Resolver: service.example.test → 127.0.0.1"]
    B --> C["Kết nối TCP tới 127.0.0.1:8443"]
    A --> D["Tên logic: service.example.test"]
    D --> E["TLS SNI: service.example.test"]
    D --> F["Xác minh chứng chỉ cho service.example.test"]
    C --> G["TLS handshake"]
    E --> G
    F --> G
    G --> H{"TLS hợp lệ?"}
    H -->|Có| I["Gửi HTTP Host hoặc :authority = service.example.test:8443"]
    H -->|Không| J["Dừng kết nối, báo lỗi xác minh"]
~~~

Sơ đồ minh họa trường hợp kết nối trực tiếp. Khi có proxy, đường đi và bên thực hiện phân giải tên có thể khác; ứng dụng vẫn phải giữ danh tính HTTPS của đích mong muốn.

## 3. Vì sao không được thay URI hostname bằng IP?

Đoạn mã sau thể hiện một lỗi thiết kế thường thấy:

~~~java
import java.net.InetAddress;
import java.net.URI;

String hostname = "service.example.test";
InetAddress resolved = InetAddress.getByName(hostname);

// Sai ý tưởng: dùng IP đã resolve để tạo danh tính HTTPS mới.
URI target = URI.create(
        "https://" + resolved.getHostAddress() + ":8443/health");
~~~

Nếu resolver trả về `127.0.0.1` thì `target.getHost()` là `127.0.0.1`. Một HTTP client tiêu chuẩn sẽ xem **IP là host của URI**. Những hệ quả thường gặp:

1. HTTP/1.1 `Host` hoặc HTTP/2 `:authority` có thể mang IP thay vì `service.example.test`.
2. Với IP literal, client thường không phát SNI chứa hostname ban đầu; SNI hostname không được khôi phục tự động từ địa chỉ đã phân giải.
3. Khi hostname verification được bật đúng cách, client kiểm tra chứng chỉ theo IP. Chứng chỉ chỉ có DNS SAN `service.example.test` sẽ **không khớp** với IP literal `127.0.0.1`.

Thêm một HTTP header thủ công như `Host: service.example.test:8443` cũng không sửa được danh tính peer TLS. Thậm chí `java.net.http.HttpClient` có các ràng buộc đối với header do client quản lý; ứng dụng không nên dựa vào việc ghi đè `Host` để điều khiển kết nối. Việc tắt hostname verification để cho qua lỗi là cách làm không an toàn và che khuất nguyên nhân cần kiểm chứng.

Cách đúng là giữ nguyên:

~~~java
URI target = URI.create(
        "https://service.example.test:8443/health");
~~~

Resolver quyết định IP đích dưới tầng mạng. URI vẫn chứa hostname logic để HTTP client thực hiện xác thực server và hình thành HTTP authority phù hợp.

## 4. Dùng HttpClient hiện đại với URI chứa hostname

`java.net.http.HttpClient` có mặt từ Java 11, vẫn là API phù hợp trên các JDK hiện đại. Với use case thông thường, chỉ cần giữ hostname trong URI và sử dụng cơ chế kiểm tra TLS mặc định.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public final class HttpsHostnameCheck {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create(
                "https://service.example.test:8443/health");

        HttpClient client = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding());

        System.out.println("URI hostname: " + uri.getHost());
        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("HTTP version: " + response.version());
    }
}
~~~

**Điều kiện để ví dụ chạy thành công:** hostname cần được phân giải đến một endpoint HTTPS có thật trong môi trường test; server phải có chứng chỉ phù hợp với `service.example.test` và chuỗi chứng chỉ phải được JVM tin cậy. Vì `.test` dành cho kiểm thử, ví dụ này không ngụ ý tên đó tồn tại trên Internet công cộng. Nếu dùng CA nội bộ cho lab, cấu hình truststore tin cậy **CA kiểm thử** thay vì bỏ xác minh chứng chỉ.

Điều cần quan sát:

- `uri.getHost()` vẫn là `service.example.test`.
- Client kết nối tới địa chỉ được phân giải trong điều kiện chạy thực tế.
- HTTP/1.1 dùng `Host`, HTTP/2 dùng `:authority` theo authority của URI.
- TLS tiếp tục sử dụng hostname được yêu cầu để xác minh chứng chỉ khi endpoint identification được bật.

`followRedirects(NEVER)` giúp lần kiểm tra đầu tiên chỉ tập trung vào đích ban đầu. Nếu cho phép redirect, client có thể chuyển sang URI với hostname mới; lúc ấy các giá trị SNI, HTTP authority và hostname verification phải được xác định theo URI **sau redirect**.

**Không thể kết luận từ HTTP status 200 rằng mọi điều kiện đã được xác minh.** Cần đối chiếu cấu hình TLS, log của server và địa chỉ kết nối. Ví dụ: một client đã bị cấu hình bỏ hostname verification có thể nhận HTTP 200 nhưng vẫn không đạt mục tiêu bảo mật.

## 5. Resolver tùy chỉnh nên thay địa chỉ, không thay danh tính

SPI `java.net.spi.InetAddressResolverProvider`, được giới thiệu từ Java 18, cho phép cung cấp resolver cho `InetAddress` ở cấp JVM. Với bài toán ánh xạ tên trong môi trường test, việc thiết lập resolver được thực hiện ở tầng phân giải địa chỉ; mã gọi HTTPS vẫn xây dựng request từ hostname logic.

Tư duy luồng dữ liệu:

~~~text
Mã ứng dụng:
  URI = https://service.example.test:8443/health
                   |
                   v
Resolver:
  service.example.test -> 127.0.0.1
                   |
                   v
TCP:
  127.0.0.1:8443
                   |
                   v
TLS:
  SNI / peer hostname = service.example.test
                   |
                   v
HTTP:
  Host hoặc :authority = service.example.test:8443
~~~

Nếu provider trả về một hoặc nhiều `InetAddress` cho `service.example.test`, tên mà ứng dụng dùng trong URI **không cần đổi**. Provider phải xử lý đúng các hợp đồng `InetAddressResolver`, bao gồm `LookupPolicy` (địa chỉ IPv4/IPv6), `UnknownHostException`, và tra cứu ngược `lookupByAddress(...)`. Nếu muốn ủy quyền cho resolver mặc định, sử dụng `InetAddressResolverProvider.Configuration.builtinResolver()`; tránh gọi ngược `InetAddress.getByName(...)` từ resolver tùy chỉnh vì có thể đi lại vào resolver của chính mình.

Cũng cần nhớ: `InetAddress` phát hiện provider bằng `ServiceLoader` trong phạm vi **system class loader**, chọn provider tại quá trình thiết lập resolver dùng chung. Đặt implementation chỉ trong class loader của plugin, hoặc chỉ đổi thread context class loader, không bảo đảm `InetAddress` sẽ chọn provider đó. Khi kiểm thử thay đổi provider, hãy khởi động JVM mới.

Lưu ý về phạm vi: hợp đồng SPI áp dụng cho hoạt động phân giải của `InetAddress`. Mọi stack HTTP, proxy hoặc thư viện mạng đều có thể có cách chọn resolver riêng. Với `HttpClient` và môi trường chạy cụ thể, phải xác minh đường đi bằng log provider, log server hoặc công cụ quan sát kết nối; đừng suy đoán chỉ từ việc gọi `InetAddress.getByName(...)` riêng lẻ.

## 6. Trường hợp phải kết nối tới IP đã biết: tách TCP khỏi TLS identity

Đôi khi bài kiểm thử cần ép kết nối tới một IP cụ thể mà không thay DNS toàn JVM. API TLS ở tầng thấp có thể làm điều đó, miễn là **hostname logic vẫn được chuyển vào lớp TLS**.

Ví dụ dưới đây dùng `SSLSocket` và gửi một yêu cầu HTTP/1.1 đơn giản. Nó phục vụ kiểm chứng từng tầng, không thay thế HTTP client tiêu chuẩn trong mã ứng dụng.

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class DirectIpWithHostname {
    public static void main(String[] args) throws Exception {
        String logicalHost = "service.example.test";
        int port = 8443;
        InetAddress targetIp = InetAddress.getByName("127.0.0.1");

        SSLSocketFactory factory =
                (SSLSocketFactory) SSLSocketFactory.getDefault();

        try (Socket tcp = new Socket()) {
            tcp.connect(new InetSocketAddress(targetIp, port), 3_000);

            // Bọc TCP socket, truyền hostname LOGIC cho tầng TLS.
            try (SSLSocket tls = (SSLSocket)
                    factory.createSocket(tcp, logicalHost, port, false)) {

                SSLParameters parameters = tls.getSSLParameters();
                parameters.setServerNames(
                        List.of(new SNIHostName(logicalHost)));
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                tls.setSSLParameters(parameters);

                // Chỉ thành công khi TLS handshake và xác minh server đạt.
                tls.startHandshake();

                String request =
                        "GET /health HTTP/1.1\r\n"
                        + "Host: " + logicalHost + ":" + port + "\r\n"
                        + "Connection: close\r\n"
                        + "\r\n";

                tls.getOutputStream().write(
                        request.getBytes(StandardCharsets.US_ASCII));
                tls.getOutputStream().flush();

                BufferedReader input = new BufferedReader(
                        new InputStreamReader(
                                tls.getInputStream(),
                                StandardCharsets.US_ASCII));
                System.out.println(input.readLine());
            }
        }
    }
}
~~~

Ba hành động riêng biệt trong ví dụ:

1. `tcp.connect(...)` chọn **IP đích** và cổng TCP.
2. `createSocket(tcp, logicalHost, port, false)` kết hợp kết nối TCP đã mở với **hostname logic** dùng bởi TLS; `setServerNames(...)` chỉ rõ tên SNI. `setEndpointIdentificationAlgorithm("HTTPS")` bật kiểm tra danh tính HTTPS của peer đối với tên đó.
3. Dòng `Host: service.example.test:8443` được gửi **sau** khi `tls.startHandshake()` hoàn thành.

Ví dụ chỉ phù hợp với hostname DNS hợp lệ để tạo `SNIHostName` và server test có chứng chỉ được JVM tin cậy cho tên đó. Với IDN hoặc định dạng hostname đặc biệt, cần chuẩn hóa đúng trước khi tạo SNI. IP không được sử dụng làm DNS hostname trong `SNIHostName`.

Cần phân biệt hai thiết lập:

- `parameters.setServerNames(...)` chỉ cấu hình SNI, **không đủ** để kiểm tra chứng chỉ.
- `parameters.setEndpointIdentificationAlgorithm("HTTPS")` xác định việc xác minh danh tính server theo quy tắc HTTPS; **không phải** là thao tác ghi HTTP `Host`.

Đối với HTTPS thực tế, còn phải xử lý HTTP/2, redirect, timeout, proxy, pooling, lỗi, đóng kết nối và các yêu cầu giao thức khác. `HttpClient` được ưu tiên cho sản phẩm; ví dụ `SSLSocket` làm rõ quan hệ giữa IP kết nối và hostname TLS.

## 7. Thiết kế bài kiểm chứng ba lớp

Nên bố trí một endpoint HTTPS thử nghiệm với chứng chỉ chứa `DNS:service.example.test` trong Subject Alternative Name, và một resolver (hoặc mapping có kiểm soát) trỏ tên đó tới IP của máy chủ thử nghiệm. Hãy dùng CA nội bộ đã được trust trong JVM kiểm thử, đồng thời đảm bảo máy chủ thật sự nhận request. Không cần và không nên vô hiệu hóa xác minh chứng chỉ.

### Lớp 1 — Kiểm tra phân giải và đích TCP

- Ghi nhận giá trị mà resolver trả về cho `service.example.test`, ví dụ `127.0.0.1`.
- Quan sát IP và cổng của kết nối mạng được mở thực tế.
- Kiểm tra việc ánh xạ xảy ra trước hoặc khi client tạo kết nối; HTTP client có thể tái sử dụng connection và cache kết quả DNS.
- Nếu dùng provider SPI, xác minh provider đã được JVM phát hiện; test bằng một tiến trình JVM mới.

Phép gọi `InetAddress.getAllByName("service.example.test")` chứng minh **đường tra cứu của InetAddress** cho một thời điểm, nhưng một mình nó chưa chứng minh request HTTPS đã đi qua provider hoặc đến đúng server.

### Lớp 2 — Kiểm tra TLS SNI và chứng chỉ

- Xem log SNI của TLS server (hoặc công cụ quan sát TLS ClientHello trong môi trường test được phép).
- Với hostname DNS bình thường và cấu hình TLS phù hợp, kỳ vọng SNI là `service.example.test`.
- Bảo đảm chứng chỉ do server trình bày có SAN khớp `service.example.test` và chuỗi tin cậy hợp lệ.
- Tạo phép thử âm với một server/chứng chỉ **không khớp hostname**: handshake phải thất bại khi hostname verification hoạt động đúng.

SNI có thể phụ thuộc khả năng và cấu hình client/server; hãy đo thực tế. Một số trường hợp như IP literal sẽ không mang DNS SNI. SNI không thay thế kiểm tra SAN của chứng chỉ.

### Lớp 3 — Kiểm tra HTTP authority

- Nếu giao thức là **HTTP/1.1**, server ghi nhận `Host: service.example.test:8443`.
- Nếu là **HTTP/2**, server ghi nhận `:authority = service.example.test:8443`.
- Tránh áp đặt cách kiểm tra HTTP/1.1 `Host` lên HTTP/2 mà bỏ qua `:authority`.
- Nếu cổng là mặc định của HTTPS, authority thường không cần hậu tố `:443`; với cổng `8443` thì cần bảo toàn cổng tương ứng trong URI/authority.

Kiểm tra giá trị tại **server** đáng tin cậy hơn việc chỉ in lại URI ở phía client: URI cho biết ý định của ứng dụng, còn log server cho biết request đã đến endpoint với authority nào.

## 8. Ma trận kiểm thử đúng/sai

Dùng server có chứng chỉ tin cậy cho `service.example.test` và không có IP SAN cho `127.0.0.1`. Các dự đoán sau giả định HTTP client giữ kiểm tra TLS mặc định và kết nối được đến server test.

| Kịch bản | URI ứng dụng | IP thực | Host / :authority | Kiểm tra TLS kỳ vọng |
| --- | --- | --- | --- | --- |
| **A. Đúng** — hostname được phân giải sang IP lab | `https://service.example.test:8443/health` | `127.0.0.1` | `service.example.test:8443` | Thành công nếu cert SAN/CA hợp lệ. |
| **B. Sai** — dùng IP sau khi resolve để dựng URI mới | `https://127.0.0.1:8443/health` | `127.0.0.1` | `127.0.0.1:8443` | Thất bại nếu cert không có IP SAN phù hợp. |
| **C. Sai** — chỉ cố ghi đè HTTP Host | URI host là `127.0.0.1` | `127.0.0.1` | Có thể cố thay thành tên DNS | Không tự khôi phục SNI hoặc TLS reference identity. |
| **D. Đúng khi cần kết nối trực tiếp** — TCP theo IP, TLS/HTTP theo hostname | Kết nối tầng thấp | `127.0.0.1` | `service.example.test:8443` | Thành công nếu TLS peer host, SNI và xác minh cert đều cấu hình đúng. |

Với kịch bản B, việc thất bại khi kiểm tra chứng chỉ là **hành vi mong muốn**, vì đã thay danh tính HTTPS sang IP không có trong chứng chỉ. Nếu B vẫn thành công, trước tiên kiểm tra xem chứng chỉ có IP SAN hợp lệ hay không; sau đó mới xem liệu ứng dụng đã vô tình tắt hostname verification hoặc sử dụng trust manager không kiểm tra danh tính.

Không nên cố tạo tình huống thành công bằng cách tin tưởng mọi chứng chỉ hoặc đặt thuật toán endpoint identification thành rỗng. Làm vậy sẽ khiến bài kiểm chứng mất khả năng phát hiện lỗi bảo mật.

## 9. Các yếu tố khiến kết quả kiểm thử dễ bị hiểu sai

| Hiện tượng | Diễn giải cần kiểm tra |
| --- | --- |
| `InetAddress` trả về đúng IP nhưng HTTP request không đến IP đó | Client dùng proxy, resolver riêng, connection pool, cache hoặc có redirect. |
| Không thấy log của provider trong lượt gọi thứ hai | Kết nối hoặc kết quả phân giải đã được cache; cần JVM mới và quan sát thời điểm request đầu tiên. |
| Server nhận đúng `Host` nhưng chứng chỉ vẫn lỗi | HTTP authority và hostname verification là các bước độc lập; cần xác minh TLS peer host và SAN. |
| SNI đúng nhưng server trả response của virtual host khác | Kiểm tra cấu hình server và HTTP Host/:authority; SNI là gợi ý lựa chọn TLS, không thay thế HTTP routing. |
| Gọi URL bằng IP mà chứng chỉ vẫn được chấp nhận | Chứng chỉ có thể có IP SAN đúng; không tự kết luận hostname verification đã bị tắt. |
| Test chạy được với HTTP/1.1 nhưng khác khi chuyển HTTP/2 | Kiểm tra `:authority`, ALPN, connection pooling và cách framework ghi log. |
| Chỉ lỗi trên môi trường proxy | Xem quy tắc CONNECT/tunnel và bên thực hiện phân giải tên; khác biệt với kết nối trực tiếp. |
| Test dùng CA tự ký hoặc CA nội bộ bị lỗi trust | Nhập CA kiểm thử vào truststore đúng quy trình; vẫn giữ nguyên hostname verification. |

Một lưu ý thêm: HTTPS có thể dùng lại kết nối cho nhiều request hợp lệ theo quy tắc của client/giao thức. Vì vậy một request sau có thể không tạo DNS lookup hoặc TLS handshake mới. Khi cần kiểm chứng một thay đổi resolver, nên dùng client/tiến trình riêng và ghi nhận chính xác request đầu tiên tạo kết nối mới.

## 10. Checklist review mã trước khi triển khai

- [ ] URI HTTPS trong mã nghiệp vụ chứa hostname logic của dịch vụ, không chứa IP đã phân giải dùng thay hostname.
- [ ] Resolver chỉ cung cấp địa chỉ mạng; không viết lại hostname của request.
- [ ] TLS được cấu hình xác minh hostname và chuỗi chứng chỉ hợp lệ; không có cơ chế `trust all` hoặc bỏ endpoint identification.
- [ ] Nếu dùng socket tầng thấp, tên được truyền cho TLS peer host và SNI phù hợp với hostname logic.
- [ ] Kiểm tra HTTP authority đúng cho phiên bản HTTP sử dụng: HTTP/1.1 `Host` hoặc HTTP/2 `:authority`.
- [ ] Trường hợp test dùng cổng khác 443, authority và kết nối sử dụng đúng cổng.
- [ ] Có kiểm tra âm cho chứng chỉ sai hostname; ứng dụng phải từ chối.
- [ ] Có đối chiếu IP đích thực tế, TLS handshake và request được server tiếp nhận.
- [ ] Test trong JVM mới khi thay SPI provider hoặc cấu hình resolver; đã xem xét cache, connection reuse và proxy.

## 11. Câu hỏi tự kiểm tra

1. Resolver trả về IP `127.0.0.1` cho `service.example.test`. Những giá trị nào được phép thay đổi, những giá trị nào phải giữ nguyên để kết nối HTTPS đúng danh tính?
2. Vì sao HTTP `Host` header không thể sửa một TLS handshake đã dùng SNI sai?
3. Nếu server có chứng chỉ chứa `DNS:service.example.test` nhưng không có `IP:127.0.0.1`, vì sao URI dùng IP có thể thất bại dù TCP đã kết nối thành công?
4. `SSLParameters.setServerNames(...)` và `setEndpointIdentificationAlgorithm("HTTPS")` giải quyết hai vấn đề khác nhau như thế nào?
5. Vì sao kiểm tra `InetAddress.getAllByName(...)` chưa đủ để kết luận HTTP client thực sự dùng provider?
6. Khi đổi từ HTTP/1.1 sang HTTP/2, nên quan sát trường nào của request để xác minh authority?
7. Khi phép thử đầu tiên có log resolver nhưng phép thử thứ hai không có, làm thế nào xác định cache, pooling, proxy hoặc redirect có ảnh hưởng?

## 12. Kết luận

**DNS/resolver trả lời “kết nối đến IP nào”; HTTPS trả lời “đang kết nối an toàn với hostname nào”.** Hai thông tin có liên quan nhưng không được đánh đồng. Khi kiểm chứng resolver của Java 18 trên JDK hiện đại, hãy giữ hostname ban đầu trong URI và thông tin xác minh TLS; để resolver quyết định IP; xác nhận HTTP Host hoặc `:authority`, TLS SNI và chứng chỉ qua phép thử thực tế, kể cả phép thử chứng chỉ sai tên.
