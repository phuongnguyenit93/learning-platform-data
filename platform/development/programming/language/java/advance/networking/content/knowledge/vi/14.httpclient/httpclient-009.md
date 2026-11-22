# Ảnh hưởng của HTTPS, proxy và SSLContext đến việc dùng HTTP/3

## 1. Nhìn đúng vấn đề: HTTP/3 không chỉ là bật TLS

HTTP/3 là cách truyền HTTP semantics trên **QUIC/UDP**, không phải HTTP/2 đổi tên. QUIC tích hợp handshake **TLS 1.3**, dùng ALPN **h3** để chọn HTTP/3 và cho phép nhiều stream độc lập trong một kết nối. HTTP/2 thường được truyền qua **TLS/TCP** với ALPN **h2**. Cùng một địa chỉ bắt đầu bằng **https://** có thể được dùng với HTTP/2 hoặc HTTP/3 tùy khả năng thực tế của client và server.

**Giới hạn phiên bản Java là điểm xuất phát quan trọng nhất:**

| Phiên bản JDK | java.net.http.HttpClient.Version | Có HTTP/3 trong HttpClient built-in? |
| --- | --- | --- |
| **Java 17** | HTTP_1_1, HTTP_2 | **Không** |
| **Java 21/25** | HTTP_1_1, HTTP_2 | **Không** |
| **Java 26 trở lên** | Thêm HTTP_3 qua **JEP 517** | **Có**, với điều kiện phù hợp và phải opt-in |

**JDK 26** được phát hành vào tháng 3/2026 và bổ sung HTTP/3 cho HttpClient. Chương trình biên dịch với JDK 17 không thể tham chiếu **HttpClient.Version.HTTP_3**, vì symbol chưa tồn tại. SSLContext hay setApplicationProtocols không thể tự bổ sung QUIC vào HttpClient Java 17. Muốn sử dụng HTTP/3 khi phải giữ Java 17, cần một **thư viện QUIC/HTTP3 tương thích riêng** được đánh giá kỹ, hoặc đổi sang JDK 26+ cho bài thử nghiệm HTTP/3 built-in.

**Ngay trên JDK 26, HTTP/3 không được bật mặc định.** HttpClient vẫn ưu tiên HTTP/2 trừ khi đặt **Version.HTTP_3** trên HttpClient hoặc HttpRequest. Preferred version chỉ là mong muốn; response có thể là HTTP_2 hoặc HTTP_1_1 do fallback. Muốn biết thực sự dùng gì, luôn lấy **HttpResponse.version()**.

### Sáu điều kiện quan trọng

1. **HTTPS URI:** JDK 26 HttpClient không dùng HTTP/3 với request có URI scheme khác **https**.
2. **HTTP_3 preferred:** JDK 26 phải có opt-in, H3 discovery thích hợp.
3. **QUIC/UDP reachable:** server hỗ trợ H3, đường UDP và port thông suốt; TCP/443 hoạt động chưa đủ.
4. **Proxy:** implementation JDK 26 không hỗ trợ HTTP/3 **khi một proxy được chọn** cho request.
5. **SSLContext/SSLParameters:** TLS provider và cấu hình phải hỗ trợ yêu cầu QUIC/TLS 1.3; custom TLS context có thể không tương thích.
6. **Certificate identity:** TLS server vẫn phải được xác minh đối với HTTPS origin; không được tắt certificate/hostname validation để đạt H3.

## 2. HTTP/3, HTTPS, QUIC và TLS 1.3

### 2.1. Đường truyền khác nhau

~~~text
HTTP/2 qua HTTPS:                 HTTP/3 qua HTTPS:

URI https://api.example.com      URI https://api.example.com
          |                                |
       HTTP/2                           HTTP/3
          |                                |
     TLS 1.2/1.3                         QUIC
          |                         (tích hợp TLS 1.3)
         TCP                               |
          |                               UDP
         IP                                |
                                          IP
~~~

HTTP/3 giữ các khái niệm HTTP như method, status, header, request và response, nhưng đổi transport từ TCP sang QUIC. QUIC dùng UDP và có khả năng multiplex stream với xử lý mất packet ở mức stream; ưu điểm hiệu năng là **khả năng**, không phải cam kết HTTP/3 luôn nhanh hơn HTTP/2 trong mọi mạng.

**https:// không đồng nghĩa HTTP/3.** Đó là scheme của HTTPS origin. Trong built-in JDK 26, HTTP/3 được xét **chỉ khi URI scheme là https**, nhưng không phải cứ HTTPS là QUIC. Đừng đặt URL dạng giả **http3://** rồi mong HttpClient tự hiểu.

### 2.2. TLS 1.3 trong QUIC khác TLS trên TCP

QUIC phiên bản 1 dùng TLS 1.3 cho handshake bên trong transport QUIC. ALPN **h3** thông báo application protocol HTTP/3. HTTP/2 trên TLS/TCP thường dùng ALPN **h2**. Tạo SSLSocket TCP rồi tự gọi setApplicationProtocols("h3") **không biến nó thành QUIC/HTTP3**, ngay cả khi TLS 1.3 đã bật.

Với HTTPS, client cần kiểm tra server certificate được tin cậy và **khớp tên origin** trong URI. Nếu URI là **https://api.example.com**, certificate phải đại diện cho **api.example.com**. SNI giúp server chọn chứng chỉ, ALPN giúp chọn protocol, nhưng **không thay thế xác minh danh tính server**.

Đặc biệt khi HTTP/3 được tìm qua alternative service trên một host hoặc port khác, endpoint vẫn phải **được phép đại diện cho origin**. Không mặc định tin cậy một máy chủ mới chỉ vì nó xuất hiện trong header Alt-Svc.

### 2.3. Đường UDP có thể bị chặn

Ví dụ một firewall cho phép TCP/443 nhưng chặn UDP/443:

~~~text
Client JDK 26 ưu tiên H3
       |
     QUIC/UDP ----X----> server (UDP bị chặn)
       |
       +--> ANY / mode cho fallback: HTTP/2 hoặc HTTP/1.1 qua TCP
       |
       +--> HTTP_3_URI_ONLY: không có H3 thì báo lỗi
~~~

Các nguyên nhân khác cũng có thể làm H3 thất bại: DNS, load balancer chưa mở UDP, NAT/firewall, cổng QUIC khác, server chưa bật H3, lỗi certificate hoặc TLS provider không tương thích. **Response.version() = HTTP_2** không đủ chứng minh server thiếu H3.

## 3. Discovery: Alt-Svc và các chế độ HTTP/3 trên JDK 26

Một server có thể quảng bá HTTP/3 qua header:

~~~http
Alt-Svc: h3=":443"; ma=86400
~~~

Header đó cho biết một dịch vụ H3 có thể được dùng cho origin. **Nó không nói request mang header đã được gửi bằng H3**: header có thể xuất hiện trong một response HTTP/2. Client có HTTP3 có thể ghi nhớ thông báo này để thử HTTP/3 ở những request sau.

Với **Java 17**, HttpClient có thể nhìn thấy chuỗi Alt-Svc nhưng **không thể chuyển sang H3 bằng built-in client**. Phải phân biệt **server quảng bá** với **client có khả năng và đã sử dụng** H3.

### H3_DISCOVERY trên JDK 26

**HttpOption.H3_DISCOVERY** và **HttpOption.Http3DiscoveryMode** được bổ sung cùng HTTP/3 API:

| Mode | Cách tìm H3 | Có thể fallback? |
| --- | --- | --- |
| **ANY** | Implementation tự quyết định cách thử QUIC, TLS/TCP và/hoặc Alt-Svc; là mặc định khi H3 preferred mà không có hint | **Có**, response có thể H1/H2/H3 |
| **ALT_SVC** | Chỉ dùng HTTP Alternative Services để tìm địa chỉ H3; thường dùng H1/H2 cho tới khi nhận quảng bá h3 | **Có** |
| **HTTP_3_URI_ONLY** | Chỉ thử H3 tại chính host/port trong URI, **không dùng Alt-Svc** để chuyển alternative service | **Không**, H3 không khả dụng thì fail |

**Một bẫy quan trọng:** gắn **H3_DISCOVERY** nhưng cả client và request vẫn preferred **HTTP_2** thì hint đó **không kích hoạt HTTP/3**. Phải chọn **HttpClient.Version.HTTP_3** ở client hoặc request.

Với ANY, JDK 26 có thể thử đường QUIC và TCP, dùng kết nối thành công trước hoặc tùy thuật toán nội bộ. Do đó **một request đầu tiên có HTTP_2 vẫn hợp lệ khi client preferred HTTP_3**. Tránh thiết kế bài test phụ thuộc cứng vào kết quả của một lần chạy.

### Cấu hình preferred và strict

~~~java
// CHỈ JDK 26+, không có enum HTTP_3 trên Java 17.
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_3)
        .build();
~~~

Đây là **ưu tiên**, không phải yêu cầu tuyệt đối. Để bắt buộc HTTP/3 tại URI, cần hint trên request:

~~~java
// CHỈ JDK 26+, khi request hoặc client có HTTP_3 preferred.
HttpRequest request = HttpRequest.newBuilder(uri)
        .setOption(
                HttpOption.H3_DISCOVERY,
                HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY)
        .GET()
        .build();
~~~

Đây là các **snippet**, các import và biến **uri** ở chương trình đầy đủ JDK 26 phía sau. HTTP_3_URI_ONLY chỉ thử QUIC tại authority của URI; nếu server chỉ quảng bá h3 tại một port khác, strict URI-only không dùng alternative đó.

## 4. Proxy thay đổi khả năng HTTP/3 như thế nào?

### 4.1. HTTP proxy qua TCP không phải QUIC

Một HTTP proxy truyền thống xử lý HTTPS bằng HTTP CONNECT, tạo tunnel **qua TCP**. Bên trong tunnel, client dùng TLS/TCP với origin hoặc với endpoint theo cấu hình mạng. Cơ chế này không tự cung cấp đường truyền QUIC/UDP cần cho HTTP/3.

Ngoài thị trường có các thiết kế proxy QUIC, CONNECT-UDP hoặc MASQUE, nhưng **implementation của JDK 26 HttpClient nêu trong Javadoc không hỗ trợ HTTP/3 khi proxy được chọn**. Đừng suy luận rằng vì proxy của tổ chức có chức năng UDP nên HttpClient built-in chắc chắn dùng được HTTP/3 qua proxy.

### 4.2. ProxySelector: có cấu hình khác với thực sự được chọn

HttpClient có **Builder.proxy(ProxySelector)**. Nếu không set, implementation thường dùng **default proxy selector** và các system properties/proxy policy liên quan. ProxySelector có thể chọn proxy cho URI A nhưng trả **DIRECT** cho URI B.

**client.proxy().isPresent()** chỉ cho biết client được cấu hình selector; nó **không chứng minh request cụ thể đã đi qua proxy**. Cần kiểm tra kết quả **ProxySelector.select(uri)** với đúng môi trường và cách HttpClient sử dụng nó; không đọc một biến boolean rồi kết luận H3 đã bị cấm.

| JDK 26 / tuyến kết nối | H3 preferred (ANY/ALT_SVC) | H3 strict URI-only |
| --- | --- | --- |
| Không có proxy được chọn | Có thể dùng H3 khi điều kiện khác phù hợp; cũng có thể fallback | Thử H3 trực tiếp, lỗi nếu không khả dụng |
| Có proxy được chọn cho URI | **Không dùng H3**, fallback HTTP/2 hoặc HTTP/1.1 nếu thành công | **Fail**, không được tự fallback |
| Selector được cấu hình nhưng trả DIRECT | H3 vẫn có thể dùng | Có thể thử H3 direct |

Nếu tổ chức yêu cầu đi qua proxy, **không được bỏ qua proxy policy chỉ để đạt HTTP/3**. Sử dụng H2/H1 là kết quả đúng trong giới hạn implementation, hoặc đánh giá một stack proxy/client được tổ chức hỗ trợ.

### 4.3. Proxy và TLS truststore

Khi HTTPS đi qua một gateway/proxy có TLS inspection được ủy quyền, certificate trình cho client có thể do CA nội bộ ký. Lỗi certificate chain/hostname cần được xử lý theo chính sách CA và endpoint được phép; **không sửa bằng TrustManager tin mọi certificate**. Việc proxy hoạt động với HTTP/2 không chứng minh đường HTTP3 khả dụng.

### 4.4. Ví dụ cấu hình proxy trong JDK 17

~~~java
// Snippet minh họa. Không cần kết nối proxy để tạo client.
HttpClient client = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .proxy(ProxySelector.of(new InetSocketAddress("127.0.0.1", 3128)))
    .build();
~~~

Đoạn code này chỉ cấu hình selector, **không bật HTTP/3**. Địa chỉ proxy giả trong ví dụ offline không phải lời khuyên đưa vào production.

## 5. SSLContext, SSLParameters và tương thích QUIC

### 5.1. SSLContext gồm nhiều hơn TLS version

**SSLContext** xác định implementation/provider TLS cùng với key manager (danh tính client khi mTLS), trust manager (CA/certificate chain của peer) và nguồn ngẫu nhiên. HttpClient có thể dùng **SSLContext mặc định** hoặc một context tùy chỉnh qua **Builder.sslContext(...)**. **SSLParameters** cho phép thiết lập các protocol/cipher/thuộc tính được áp dụng.

~~~text
HttpClient.Builder
    |
    +-- sslContext(context)
    |      |
    |      +-- Provider / TLS implementation
    |      +-- TrustManager / certificate verification
    |      +-- KeyManager / client auth (mTLS)
    |
    +-- sslParameters(params)
    |      |
    |      +-- Enabled TLS versions / cipher / properties
    |
    +-- version(HTTP_3)  [JDK 26+]
             |
        QUIC-compatible TLS context + TLS 1.3 required
~~~

Một custom SSLContext có thể chạy **TLS/TCP cho HTTP/2** nhưng **không tương thích phần QUIC TLS** mà JDK 26 cần. Tài liệu JDK 26 mô tả khả năng xảy ra **UnsupportedProtocolVersionException** khi context/SSLParameters không cho phép H3 (khi tạo client hoặc khi gửi request strict). **Không kết luận mọi custom SSLContext đều bị cấm**; đánh giá provider và cấu hình thực tế.

### 5.2. TLS 1.3 là điều kiện cần nhưng chưa đủ

HTTP/3 trên QUIC phiên bản 1 yêu cầu TLS 1.3. Nếu SSLParameters chỉ bật **TLSv1.2**, HTTP/3 không thể thiết lập, dù HTTP/2 có thể vẫn chạy.

~~~java
// Snippet kiểm tra context mặc định.
SSLContext ctx = SSLContext.getDefault();
boolean tls13 = Arrays.asList(
        ctx.getDefaultSSLParameters().getProtocols())
        .contains("TLSv1.3");
System.out.println("TLSv1.3 enabled: " + tls13);
~~~

Ngay cả khi in true, còn cần **JDK 26+ có HTTP3 API**, context/provider tương thích QUIC, đường UDP, no selected proxy, server H3/ALPN và certificate đúng. **Bật TLS 1.3 trong SSLSocket TCP không thể tự biến HTTP/2 thành HTTP/3**.

### 5.3. Đừng tự sửa ALPN và tắt xác thực

HttpClient.Builder.sslParameters(...) lưu ý một số tham số **do HTTP client quản lý nội bộ** như danh sách application protocols và có thể bị bỏ qua nếu người dùng tự đặt. Gọi **setApplicationProtocols(new String[]{"h3"})** không thay thế việc chọn **Version.HTTP_3** và càng không thể bổ sung HTTP3 cho JDK17.

**Không thay TrustManager bằng phiên bản chấp nhận mọi certificate.** Khi certificate chain, hostname/SAN hoặc truststore sai, sửa CA, cert hoặc endpoint; H3 vẫn phải xác minh origin của HTTPS URI. Với mTLS, cấu hình client certificate/key hợp lệ qua KeyManager; không vì chuyển sang HTTP/3 mà giảm xác thực server.

## 6. Java 17: chương trình độc lập chạy offline và kiểm tra live

Chương trình **HttpClientTransportAudit.java** được thiết kế để biên dịch bằng **--release 17**. Nó không gọi symbol **HTTP_3** nên chạy được trên Java17. Self-test chỉ đọc các API/config, **không gửi request**, không kiểm chứng QUIC hay server thực.

Chế độ live nhận một URL https, tạo HttpClient preferred HTTP_2 và in **response.version()** sau request thực. Với **runtime JDK17**, version thực tế có thể là HTTP_1_1 hoặc HTTP_2, không thể là HTTP_3.

### Tệp HttpClientTransportAudit.java

~~~java
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import javax.net.ssl.SSLContext;

public class HttpClientTransportAudit {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            SSLContext context = SSLContext.getDefault();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .proxy(ProxySelector.of(
                            new InetSocketAddress("127.0.0.1", 3128)))
                    .sslContext(context)
                    .build();

            boolean hasHttp3 = Arrays.stream(HttpClient.Version.values())
                    .anyMatch(v -> "HTTP_3".equals(v.name()));
            boolean tls13 = Arrays.asList(context.getDefaultSSLParameters()
                    .getProtocols()).contains("TLSv1.3");

            System.out.println("HTTP versions: " +
                    Arrays.toString(HttpClient.Version.values()));
            System.out.println("HTTP/3 enum present: " + hasHttp3);
            System.out.println("Preferred version: " + client.version());
            System.out.println("Proxy configured: " +
                    client.proxy().isPresent());
            System.out.println("TLSv1.3 enabled: " + tls13);
            System.out.println("No network request performed");
            return;
        }

        if (args.length != 1 || !args[0].startsWith("https://")) {
            throw new IllegalArgumentException(
                    "Usage: java HttpClientTransportAudit --self-test | https-url");
        }

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(7))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(args[0]))
                .timeout(Duration.ofSeconds(15))
                .GET()
                .build();

        HttpResponse<Void> response =
                client.send(request, HttpResponse.BodyHandlers.discarding());
        System.out.println("Status: " + response.statusCode());
        System.out.println("Actual version: " + response.version());
        response.headers().firstValue("alt-svc")
                .ifPresent(v -> System.out.println("Alt-Svc: " + v));
    }
}
~~~

### Cách chạy

~~~bash
javac --release 17 -encoding UTF-8 HttpClientTransportAudit.java
java HttpClientTransportAudit --self-test
~~~

**Stdout đã kiểm tra thực tế trên OpenJDK 21, biên dịch với --release 17, default SSLContext ở môi trường thử nghiệm:**

~~~text
HTTP versions: [HTTP_1_1, HTTP_2]
HTTP/3 enum present: false
Preferred version: HTTP_2
Proxy configured: true
TLSv1.3 enabled: true
No network request performed
~~~

Phân biệt điều **luôn đúng trên runtime JDK 17** (chỉ enum H1/H2) với điều **phụ thuộc cấu hình** (TLSv1.3 enabled có thể khác nếu provider/security policy khác). Proxy configured=true chỉ do code tự gắn proxy selector trong self-test; **không có kết nối nào tới 127.0.0.1:3128**.

Khi chạy **cùng class biên dịch --release 17 trên JDK 26**, Version.values có thể liệt kê thêm HTTP_3 vì enum được lấy từ runtime. Đây là hiện tượng bình thường, không có nghĩa source dùng API mới của Java 26.

Để kiểm tra live trên endpoint mà bạn được phép truy cập:

~~~bash
java HttpClientTransportAudit https://api.example.com/
~~~

**URL chỉ là minh họa.** Khi chạy live, code sử dụng default ProxySelector của môi trường (không dùng địa chỉ proxy giả của self-test), xác minh certificate theo chính sách HttpClient và in status/version thực tế; nếu response có Alt-Svc thì in thêm header. **Kết quả mạng không thể có stdout cố định**; không được tuyên bố response HTTP_3 chỉ vì có Alt-Svc.

## 7. JDK 26+: chương trình yêu cầu HTTP/3, có thể chọn strict

Ví dụ này **chỉ biên dịch/chạy trên JDK 26 trở lên**, không dành cho --release 17. Nó dựa trên Javadoc JDK 26 và JEP 517; không giả định endpoint minh họa đã được kết nối hay mạng hiện tại có UDP.

Chế độ bình thường: **prefer HTTP_3**, chấp nhận fallback theo mode **ANY** mặc định. Chế độ **--require-h3**: thêm **HTTP_3_URI_ONLY**, không chấp nhận fallback và chỉ thử H3 tại authority trong URI. Cả hai dùng SSLContext mặc định, **không tắt certificate verification** và giữ proxy policy mặc định của JVM.

### Tệp Http3Probe26.java

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpOption;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Arrays;
import javax.net.ssl.SSLContext;

public class Http3Probe26 {
    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            throw new IllegalArgumentException(
                    "Usage: java Http3Probe26 https-url [--require-h3]");
        }

        boolean strict = args.length == 2 &&
                "--require-h3".equals(args[1]);
        if (args.length == 2 && !strict) {
            throw new IllegalArgumentException(
                    "Only --require-h3 is supported");
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme()) ||
                uri.getHost() == null) {
            throw new IllegalArgumentException(
                    "A valid https:// URI is required");
        }

        SSLContext context = SSLContext.getDefault();
        boolean tls13 = Arrays.asList(
                context.getDefaultSSLParameters().getProtocols())
                .contains("TLSv1.3");
        if (!tls13) {
            throw new IllegalStateException(
                    "HTTP/3 requires TLSv1.3 support");
        }

        HttpRequest.Builder requestBuilder =
                HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(20))
                        .GET();
        if (strict) {
            requestBuilder.setOption(
                    HttpOption.H3_DISCOVERY,
                    HttpOption.Http3DiscoveryMode.HTTP_3_URI_ONLY);
        }

        try (HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_3)
                .sslContext(context)
                .connectTimeout(Duration.ofSeconds(8))
                .build()) {

            HttpResponse<Void> response = client.send(
                    requestBuilder.build(),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("Status: " + response.statusCode());
            System.out.println("Actual version: " + response.version());
            response.headers().firstValue("alt-svc")
                    .ifPresent(v -> System.out.println("Alt-Svc: " + v));

            if (strict &&
                    response.version() != HttpClient.Version.HTTP_3) {
                throw new IllegalStateException(
                        "HTTP/3 was required but not used");
            }
        }
    }
}
~~~

### Biên dịch và chạy với JDK 26+

~~~bash
javac Http3Probe26.java
java Http3Probe26 https://api.example.com/
java Http3Probe26 https://api.example.com/ --require-h3
~~~

**Không in stdout cố định** cho chương trình JDK 26 vì kết quả phụ thuộc hostname, mạng, server, certificate, proxy và QUIC. Bài này không nhận một kết quả HTTP_3 nào khi chưa có **response.version() = HTTP_3** thật. File JDK 26 trên được viết theo public API docs, còn ví dụ Java17 ở phần 6 đã được biên dịch/chạy trực tiếp với javac --release 17.

Nếu custom SSLContext không tương thích QUIC hoặc SSLParameters không bật TLS 1.3, việc yêu cầu HTTP3 có thể thất bại với **UnsupportedProtocolVersionException** hoặc lỗi có cause tương ứng. Không giải quyết bằng cách cho phép certificate không tin cậy.

### ALT_SVC trên JDK 26

Để đợi server quảng bá H3 trước, có thể đặt **HttpOption.H3_DISCOVERY** với **Http3DiscoveryMode.ALT_SVC** trên request được preferred HTTP_3:

~~~java
// JDK 26+; minh họa khi đã có HttpRequest.Builder rb.
rb.setOption(
        HttpOption.H3_DISCOVERY,
        HttpOption.Http3DiscoveryMode.ALT_SVC);
~~~

**ALT_SVC** thường khiến các request ban đầu dùng H1/H2 cho tới khi có thông tin Alt-Svc h3. Không nhầm với HTTP_3_URI_ONLY (bắt buộc H3 trực tiếp cùng authority). Phải kiểm tra từng response.version.

## 8. Phân biệt nguyên nhân khi HTTP_3 không xuất hiện

| Triệu chứng | Nguyên nhân hay gặp | Hướng kiểm tra |
| --- | --- | --- |
| **Java 17 lỗi compile HTTP_3** | Không có enum/HTTP3 implementation | Chuyển lên JDK 26+ hoặc dùng thư viện QUIC/HTTP3 riêng |
| **HTTPS response là HTTP_2** | Có thể là fallback đúng | Xem preferred version, response.version, proxy route, UDP/H3 |
| **Có Alt-Svc h3 nhưng không dùng H3** | Alt-Svc không phải bằng chứng đã đổi protocol | Kiểm tra runtime hỗ trợ H3, discovery, request tiếp theo |
| **JDK 26 có proxy được chọn** | Built-in HTTP3 through proxy không được hỗ trợ | Chấp nhận H2/H1 theo proxy policy hoặc kiểm tra stack khác được phép |
| **Strict H3 thất bại khi có proxy** | HTTP_3_URI_ONLY không fallback | Đây là lỗi đúng theo strict mode; không tự bỏ proxy bắt buộc |
| **TCP/443 ổn nhưng QUIC fail** | UDP/port bị chặn, server không bật H3 | Điều tra network path và UDP listener |
| **Custom SSLContext chạy HTTP2 nhưng H3 fail** | Provider không tương thích QUIC hoặc SSLParameters thiếu TLS1.3 | Kiểm tra provider, enabled protocols và JDK26 docs |
| **Handshake lỗi certificate** | CA/chain/SAN/hostname hoặc thuật toán không đúng | Sửa certificate và truststore, giữ verification |
| **URL có scheme http** | Built-in JDK26 không dùng H3 cho URI này | Dùng đúng HTTPS origin nếu dịch vụ hỗ trợ |
| **Cùng code kết quả khác trên CI** | JDK, proxy selector, DNS, truststore, egress khác | So sánh môi trường và actual version |

### Những điều không nên làm

- Không xem **preferred HTTP_3** là kết quả thực tế; luôn xem **response.version()**.
- Không xem **Alt-Svc: h3** là dấu xác nhận request trước đó đã dùng QUIC.
- Không nghĩ **SSLSocket TLSv1.3 trên TCP** tương đương HTTP/3.
- Không bỏ qua **proxy tổ chức** chỉ vì JDK26 builtin không hỗ trợ H3 qua proxy.
- Không tự thay **TrustManager** hoặc hostname checking thành cơ chế chấp nhận tất cả.
- Không xóa các **disabledAlgorithms** trong java.security để làm H3 hoạt động.
- Không giả định mọi custom SSLContext đều hỗ trợ QUIC.
- Không hard-code **Status=200** hay **Actual version=HTTP_3** trong test mạng, vì endpoint và mạng thay đổi.

## 9. Kịch bản kiểm thử có ý nghĩa

**Test A — Java 17 offline.** Chạy chương trình phần 6 với --self-test; chứng minh API runtime chỉ có H1/H2, đồng thời hiểu proxy selector và SSLContext đã cấu hình. Không khẳng định đã kiểm chứng H3.

**Test B — Java 17 live.** Gửi tới endpoint HTTPS được phép dùng; in status và actual HTTP version. Alt-Svc nếu có chỉ là quảng bá; Java17 builtin vẫn không tạo HTTP3 request.

**Test C — JDK26 H3 preferred.** Dùng Http3Probe26 ở chế độ mặc định. Có thể nhận HTTP_3/H2/H1, tùy QUIC, discovery, server và proxy. Ghi tất cả điều kiện của test thay vì chỉ ghi status 200.

**Test D — JDK26 strict.** Dùng --require-h3, xác định rõ host/port đang hỗ trợ QUIC. Nếu không dùng được H3 thì lỗi, không tự nhận HTTP_2 là PASS.

**Test E — Proxy được chọn.** Cấu hình proxy trong môi trường thử nghiệm được phép. Với built-in JDK26, kiểm tra H3 không được sử dụng; strict phải fail. Không dùng thủ thuật lách proxy khi policy yêu cầu.

**Test F — SSLContext/TLS.** So sánh provider và SSLParameters có TLSv1.3 với trường hợp chỉ bật TLSv1.2. H3 phải không thể được dùng với cấu hình thiếu TLS1.3; thay đổi theo chính sách, không hạ bảo mật.

**Test G — Xác minh certificate.** Endpoint chain/SAN hợp lệ có thể thành công. Endpoint không tin cậy hoặc sai hostname phải bị từ chối **dù đang thử H3**; điều này xác nhận SSLContext không vô tình bỏ xác thực.

### Checklist sản xuất

1. Ghi JDK vendor/version thực tế và HttpClient.Version được hỗ trợ.
2. Xác minh request dùng URI https và hostname đúng.
3. Đặt preferred H3 trên JDK26+ nếu cần, chọn đúng discovery mode.
4. Ghi actual HttpResponse.version() từng request.
5. Quan sát Alt-Svc nhưng không suy ra version từ header.
6. Kiểm tra proxy selector chọn **proxy hay DIRECT** cho chính URI.
7. Xác minh UDP/QUIC path, port và ALPN/server H3.
8. Kiểm tra SSLContext provider, TLSv1.3, SSLParameters, CA/hostname.
9. Thử fallback và strict H3 riêng; xác định expectation của từng môi trường.
10. Bảo toàn certificate/hostname verification và chính sách mạng khi cấu hình.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao HttpClient.Version.HTTP_3 không compile trên JDK17?  
**Trả lời:** JDK17 chỉ có HTTP_1_1 và HTTP_2 trong enum; support H3 built-in mới được thêm ở JDK26.

**Câu 2.** Một request HTTPS có chắc dùng HTTP/3?  
**Trả lời:** Không. HTTPS scheme không quyết định transport; cần H3 support, opt-in, QUIC, TLS và đường kết nối phù hợp.

**Câu 3.** Bật TLSv1.3 trên SSLSocket TCP có biến HTTP/2 thành HTTP/3 không?  
**Trả lời:** Không. HTTP3 dùng QUIC/UDP và TLS 1.3 tích hợp, không phải chỉ đổi tham số SSLSocket.

**Câu 4.** Alt-Svc h3 trên response HTTP2 chứng minh điều gì?  
**Trả lời:** Server quảng bá alternative service H3; không chứng minh request vừa rồi dùng H3.

**Câu 5.** JDK26 prefer HTTP_3 nhưng response.version là HTTP_2 có là lỗi?  
**Trả lời:** Không nhất thiết. Có thể là fallback hợp lệ; xem discovery, proxy, UDP và server.

**Câu 6.** ProxySelector được cấu hình có đủ kết luận HTTP3 bị tắt không?  
**Trả lời:** Không. Phải biết ProxySelector **thực sự chọn proxy** cho URI hay trả DIRECT.

**Câu 7.** Trong JDK26, khi proxy thực sự được chọn, strict HTTP_3_URI_ONLY ra sao?  
**Trả lời:** Request thất bại vì implementation không hỗ trợ HTTP/3 qua proxy và strict không fallback.

**Câu 8.** SSLContext có TLSv1.3 thì đủ cho H3 chưa?  
**Trả lời:** Chưa. Provider còn phải tương thích QUIC, certificate hợp lệ, mạng UDP hoạt động và client có HTTP3.

**Câu 9.** Khi H3 lỗi do certificate, có nên thay TrustManager chấp nhận tất cả?  
**Trả lời:** Không. Cần sửa trust anchor/certificate/SAN đúng nguồn, giữ xác thực.

**Câu 10.** Khi muốn chờ Alt-Svc mới dùng H3, mode nào thích hợp?  
**Trả lời:** ALT_SVC, khi đã chọn HTTP3 preferred trên JDK26+.

**Câu 11.** Khi buộc chỉ HTTP/3 trực tiếp cùng host/port URI, dùng mode nào?  
**Trả lời:** HTTP_3_URI_ONLY; không dùng Alt-Svc để đổi host/port và không fallback.

**Câu 12.** Cách chắc chắn biết một request sử dụng HTTP/3?  
**Trả lời:** Kiểm tra **HttpResponse.version() == HTTP_3** trên runtime hỗ trợ H3; kèm logs/telemetry kết nối nếu cần điều tra.

## Kết luận

**HTTPS** là điều kiện origin và xác minh peer, đồng thời trong HttpClient JDK26 là điều kiện scheme cần để dùng H3. **Proxy** quyết định đường kết nối; khi JDK26 built-in chọn một proxy, H3 không được dùng và request phải fallback hoặc strict fail. **SSLContext/SSLParameters** cung cấp TLS provider/trust/key/protocol, và có thể làm HTTP3 không khả dụng nếu không đáp ứng QUIC/TLS1.3, dù HTTP2 trên TCP vẫn chạy.

Với **Java17**, HttpClient chuẩn **chưa hỗ trợ HTTP/3**. Với **JDK26+**, bật preferred HTTP_3 không đủ: cần QUIC/UDP, discovery phù hợp, không bị proxy route ngăn cản, TLS context tương thích và xác minh certificate đúng. Kết luận dựa trên **actual HttpResponse.version()**, không dựa trên URL HTTPS hoặc header Alt-Svc một mình.

### Nguồn tham khảo chính thức

- [Java 17 — HttpClient.Version](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Version.html): HTTP_1_1 và HTTP_2.
- [Java 17 — java.net.http package](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/package-summary.html): phạm vi HttpClient có sẵn.
- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517): HTTP/3 được thêm ở JDK26.
- [Java 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): lựa chọn H3, HTTPS/proxy/SSLContext.
- [Java 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): proxy, SSLContext, SSLParameters và version.
- [Java 26 — HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html): enum HTTP_3.
- [Java 26 — HttpOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.html): H3_DISCOVERY và proxy limitations.
- [Java 26 — Http3DiscoveryMode](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpOption.Http3DiscoveryMode.html): ANY, ALT_SVC, HTTP_3_URI_ONLY.
- [Java 26 — UnsupportedProtocolVersionException](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/UnsupportedProtocolVersionException.html): SSLContext không tương thích.
- [Oracle Java team — HTTP Client Updates in Java 26](https://inside.java/2026/03/04/jdk-26-http-client/): các chiến lược khám phá H3.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html): QUIC, TLS 1.3, ALPN h3, Alt-Svc, origin authority.
