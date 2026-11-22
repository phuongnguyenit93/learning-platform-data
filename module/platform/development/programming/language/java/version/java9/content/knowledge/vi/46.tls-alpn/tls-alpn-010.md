# Kiểm thử lỗi bắt tay TLS và xác minh danh tính đầu xa trong Java

**Bối cảnh:** Java 9 giới thiệu hỗ trợ ALPN trong JSSE; bài này dùng Java 17+ và các API TLS/ALPN vẫn được hỗ trợ trên JDK hiện hành. Nội dung tập trung vào **kiểm thử thất bại khi bắt tay TLS** (TLS handshake) và **xác minh đúng danh tính máy chủ/đầu xa**, kể cả khi có đàm phán ALPN. Ví dụ chạy trên máy cục bộ, không cần dịch vụ Internet hoặc dependency bên ngoài JDK.

> **Nguyên tắc bảo mật:** Một kết nối TLS chỉ nên được ứng dụng chấp nhận khi các điều kiện phù hợp đều đạt: phiên TLS được thương lượng theo chính sách, chuỗi chứng chỉ đáng tin cậy, danh tính trong chứng chỉ khớp **tên máy chủ dự định kết nối**, và giao thức ứng dụng sau ALPN phù hợp. **ALPN không chứng thực máy chủ**; một handshake thành công nhưng bỏ qua kiểm tra hostname vẫn có thể bị tấn công giả mạo.

## 1. Phân biệt bốn lớp kiểm tra

| Cơ chế | Câu hỏi nó trả lời | API/đối tượng Java liên quan |
| --- | --- | --- |
| **TLS handshake** | Hai đầu có thể thống nhất phiên bản TLS, bộ thuật toán và khóa phiên an toàn không? | `SSLContext`, `SSLSocket.startHandshake()`, `SSLEngine`, `SSLSession` |
| **Kiểm tra trust/certificate path** | Chứng chỉ của peer có được dẫn đến trust anchor đáng tin, hợp lệ theo chính sách, mục đích sử dụng, thời hạn... không? | `TrustManagerFactory`, `X509TrustManager`/`X509ExtendedTrustManager`, `KeyStore` |
| **Endpoint identity / hostname verification** | Chứng chỉ đã xác thực có thực sự đại diện cho `api.example.com` (hoặc IP đích) mà ứng dụng muốn gọi không? | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`, kiểm tra DNS/IP trong SAN |
| **ALPN** | Trên kênh TLS, hai đầu sẽ nói giao thức ứng dụng nào: ví dụ `h2` hay `http/1.1`? | `SSLParameters.setApplicationProtocols(...)`, `SSLSocket.getApplicationProtocol()`, selector phía server |

Các lớp này độc lập về mục tiêu:

- Trust store có chứng chỉ máy chủ **không đủ** nếu client gọi sai hostname.
- Hostname phù hợp **không đủ** nếu chứng chỉ không được tin cậy hoặc đã hết hạn.
- ALPN chọn được `h2` **không đủ** nếu danh tính peer sai; ALPN cũng **không triển khai HTTP/2** thay ứng dụng.
- Đường truyền đã mã hóa **không tự chứng minh** server đúng là đích mong muốn.
- HTTP status `200` hay `500` xuất hiện **sau** khi đã có kênh TLS và trao đổi HTTP; không thay cho kiểm tra handshake.

## 2. Luồng handshake và các điểm có thể thất bại

```text
Client muốn kết nối https://service.example.com
    |
    | Tạo TCP connection / khởi động TLS
    v
ClientHello: TLS versions, cipher suites, SNI, ALPN offered
    |
    v
ServerHello: chọn phiên bản TLS và các tham số phù hợp
    |
    | Server gửi certificate chain, chứng minh sở hữu private key
    v
Client kiểm tra certificate chain / trust anchor / validity / usage
    |
    | Kiểm tra certificate SAN khớp service.example.com
    v
Hoàn tất TLS handshake, thiết lập khóa phiên
    |
    | Xác nhận ALPN được thương lượng đúng theo yêu cầu ứng dụng
    v
Mới gửi dữ liệu ứng dụng qua kênh TLS được chấp nhận
```

Đây là **sơ đồ khái niệm**, không mô tả thứ tự mọi thông điệp TLS 1.3/TLS 1.2. Trên TLS 1.3, certificate và thông tin ALPN được trao đổi theo cơ chế của TLS 1.3; việc kiểm tra certificate cũng nằm trong quá trình bắt tay. Nếu client không tin certificate, không nhận dạng được hostname, hoặc không thương lượng được thông số bắt buộc, ứng dụng cần **fail closed**: không gửi dữ liệu nghiệp vụ qua kết nối đó.

### Phân biệt SNI, SAN, hostname verification và ALPN

- **SNI — Server Name Indication:** client thông báo tên máy chủ dự định kết nối trong handshake để server chọn chứng chỉ/virtual host phù hợp. **Gửi SNI không phải là kiểm tra danh tính**.
- **SAN — Subject Alternative Name:** thông tin DNS name hoặc IP address mà chứng chỉ được phép đại diện. Với chứng chỉ hiện đại, nên dùng SAN phù hợp; không thiết kế hệ thống dựa vào mỗi trường `CN`.
- **Hostname verification:** client so sánh hostname/IP **mình muốn kết nối** với identity được chứng chỉ tin cậy khai báo. DNS SAN như `localhost` **không** đồng nghĩa với IP SAN `127.0.0.1`.
- **ALPN — Application-Layer Protocol Negotiation:** client đưa danh sách giao thức ứng dụng; server chọn giao thức tương thích. Nó không thay thế certificate validation, không bảo đảm nội dung ứng dụng sẽ tuân thủ giao thức được chọn.

## 3. API JSSE hiện hành cần biết

| API | Công dụng trong bài |
| --- | --- |
| `SSLContext.getInstance("TLS")` | Tạo TLS context theo provider đang dùng; `init(...)` với key managers/trust managers theo vai trò. |
| `KeyManagerFactory` | Server lấy certificate chain và private key từ keystore để trình bày danh tính. Cũng dùng với client certificate nếu thiết lập mutual TLS. |
| `TrustManagerFactory` | Tạo trust manager từ truststore để xác thực certificate của peer. |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | **Bật kiểm tra identity lúc handshake** khi ứng dụng tự quản raw `SSLSocket`/`SSLEngine`. |
| `SSLParameters.setApplicationProtocols(...)` | Khai báo giao thức ứng dụng muốn/cho phép đàm phán qua ALPN. |
| `SSLSocket.startHandshake()` | Chủ động thực hiện handshake, phát hiện lỗi trước khi gửi application data. |
| `SSLSocket.getApplicationProtocol()` | Lấy ALPN đã thương lượng sau handshake: tên nonempty khi có kết quả; `""` nếu không dùng ALPN; `null` khi chưa xác định. |
| `SSLSocket.setHandshakeApplicationProtocolSelector(...)` | Phía server chọn ALPN có kiểm soát; có thể từ chối nếu các giao thức do peer đưa ra không phù hợp. |
| `SSLSession.getProtocol()`, `getCipherSuite()` | Quan sát phiên bản TLS và cipher suite thực tế **sau handshake thành công**. |
| `SSLSession.getPeerCertificates()` | Lấy certificate chain peer của phiên được xác thực; không thay thế logic trust và hostname verification. |

### Vì sao phải bật hostname verification trên raw socket?

Với `SSLSocket`/`SSLEngine` dùng trực tiếp, **JSSE không tự động so khớp hostname trong chứng chỉ** nếu ứng dụng không cấu hình endpoint identification. Vì vậy, ở **phía client**, phải thiết lập trước handshake:

```java
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
params.setApplicationProtocols(new String[] {"h2", "http/1.1"});
socket.setSSLParameters(params);
socket.startHandshake();
```

Đây là **đoạn minh họa**, giả sử `socket` đã là `SSLSocket` client hợp lệ trỏ đến hostname thực sự mà ứng dụng muốn gọi. Danh sách ALPN trên chỉ đúng khi ứng dụng thật có khả năng triển khai giao thức đã chọn.

Với `java.net.http.HttpClient` và các HTTPS client tiêu chuẩn, hãy ưu tiên **cơ chế xác minh mặc định** của thư viện, giữ trust manager đúng chuẩn, tránh override làm vô hiệu hostname/certificate checking. `HttpClient` có cơ chế nội bộ để xử lý ALPN khi sử dụng HTTP/2; việc tự gán `SSLParameters.setApplicationProtocols` qua builder có thể bị bỏ qua vì danh sách giao thức thuộc quyền quản lý nội bộ của client. Nếu bạn tự quản `SSLEngine`, áp dụng endpoint identification trước handshake và hoàn thành đúng máy trạng thái của engine.

## 4. Thiết kế kiểm thử: kết quả tốt và lỗi phải bị từ chối

Một bộ test đáng tin cậy cần có ít nhất một **ca dương tính** và nhiều **ca âm tính**. Nếu chỉ chạy được HTTPS thành công, chưa biết ứng dụng có thực sự kiểm tra identity hay không.

| Tình huống | Trust | Tên đích | ALPN | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Certificate được tin và `DNS:localhost` khớp | Đúng | `localhost` | Có `demo/1` chung | Handshake thành công, ALPN `demo/1` |
| Chứng chỉ tự ký không có trong truststore | **Sai** | `localhost` | Có chung | **Từ chối TLS** |
| Chứng chỉ được tin nhưng chỉ có `DNS:localhost` | Đúng | **`127.0.0.1`** (không có IP SAN) | Có chung | **Từ chối TLS** |
| Hai đầu không có ALPN chung và server **yêu cầu** ALPN | Đúng | `localhost` | **Không có chung** | **Từ chối TLS** |
| Certificate hết hạn hoặc chưa hiệu lực | **Sai** theo chính sách certificate | Đúng | Có chung | **Từ chối TLS** |
| Không có phiên bản TLS/cipher phù hợp | Có thể đúng | Đúng | Không xét được | **Từ chối handshake** |
| Server bắt buộc mTLS nhưng client không có certificate hợp lệ | Không đủ thông tin client auth | Đúng | Có thể đúng | **Từ chối handshake** |

**Lưu ý về ALPN:** Khi không có giao thức chung, không phải mọi cấu hình đều tự làm handshake lỗi. Một số kết nối có thể hoàn tất TLS với `getApplicationProtocol()` trả `""`. Nếu ứng dụng **bắt buộc** ALPN (ví dụ giao thức chỉ hoạt động khi hai bên cùng chọn một identifier), cần có chính sách rõ ràng: server selector từ chối hoặc client từ chối kết nối không có kết quả ALPN hợp lệ. Ví dụ thực hành bên dưới cố ý dùng server selector để từ chối.

Khi viết assertion cho ca âm tính, kiểm tra rằng **client không có phiên TLS được chấp nhận để gửi dữ liệu ứng dụng**. Có thể thấy `SSLHandshakeException`, các `SSLException` khác hoặc lỗi I/O tùy thời điểm bên nào gửi alert/đóng socket; đừng buộc mọi provider phải có đúng một chuỗi thông báo lỗi.

## 5. Lab độc lập: tạo certificate và truststore chỉ bằng JDK

**Yêu cầu:** JDK 17+, có `java`, `javac`, `keytool`. Thực hiện trong một thư mục thực hành trống. Lab chỉ nghe trên `127.0.0.1`, không yêu cầu Internet.

Trước tiên, tạo **certificate tự ký dùng cho test**, với SAN chứa **chỉ** `DNS:localhost`. `changeit` là mật khẩu ví dụ của keystore cục bộ, **không dùng làm mật khẩu production**.

```bash
keytool -genkeypair -noprompt -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -dname "CN=localhost,OU=Lab,O=Example,C=US" -ext "SAN=dns:localhost"
```

Xuất public certificate, rồi import làm trust anchor **chỉ cho client lab**:

```bash
keytool -exportcert -rfc -alias localhost -keystore server.p12 -storepass changeit -file server.crt
keytool -importcert -noprompt -alias localhost -file server.crt -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
```

Sau các lệnh này:

- `server.p12`: có private key và certificate của server lab.
- `server.crt`: public certificate, **không chứa private key**.
- `client-trust.p12`: truststore lab chứa certificate của server để client **tin cậy có chủ đích**.
- `SSLContext.getDefault()`: trong môi trường JDK thông thường **không** tin certificate tự ký mới sinh này, vì nó không có sẵn trong truststore mặc định. Đây là điều ta sẽ kiểm thử.
- `DNS:localhost` khớp hostname `localhost`; không có SAN kiểu `IP:127.0.0.1`, nên kiểm tra identity với địa chỉ IP sẽ thất bại.

Lệnh `keytool` tạo chứng chỉ tự ký chỉ nhằm **mô phỏng** trust anchor và tình huống test. Trong hệ thống thực, dùng certificate do hệ thống PKI được quản lý cấp, thực thi chính sách trust, rotation và revocation phù hợp.

## 6. Ví dụ Java hoàn chỉnh: một handshake thành công và ba handshake thất bại

Lưu vào `TlsHandshakeLab.java` **cùng thư mục** với hai tệp `.p12`. Chương trình chạy server TLS loopback trên cổng tự chọn, thử lần lượt bốn client và in kết quả. Không gửi dữ liệu ứng dụng thực tế; tên ALPN `demo/1`, `demo/2` chỉ được dùng làm nhãn trong lab, không giả định chương trình đã triển khai HTTP/2.

```java
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.security.*;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class TlsHandshakeLab {
    static final char[] PW = "changeit".toCharArray();
    static SSLContext server;

    static SSLContext ctx(String path, boolean serverSide) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            ks.load(in, PW);
        }

        SSLContext x = SSLContext.getInstance("TLS");
        if (serverSide) {
            KeyManagerFactory f = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            f.init(ks, PW);
            x.init(f.getKeyManagers(), null, null);
        } else {
            TrustManagerFactory f = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
            f.init(ks);
            x.init(null, f.getTrustManagers(), null);
        }
        return x;
    }

    static void check(String label, SSLContext clientCtx, String host,
                      String offered, boolean expected) throws Exception {
        try (SSLServerSocket listener = (SSLServerSocket) server
                .getServerSocketFactory().createServerSocket(
                        0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);
            ExecutorService ex = Executors.newSingleThreadExecutor();
            try {
                Future<String> response = ex.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) listener.accept()) {
                        peer.setSoTimeout(5000);
                        SSLParameters p = peer.getSSLParameters();
                        p.setApplicationProtocols(new String[]{"demo/1"});
                        peer.setSSLParameters(p);
                        peer.setHandshakeApplicationProtocolSelector(
                                (s, offers) ->
                                        offers.contains("demo/1") ? "demo/1" : null);
                        peer.startHandshake();
                        return peer.getApplicationProtocol();
                    } catch (IOException e) {
                        // Khi client từ chối TLS, server cũng có thể nhận socket abort.
                        return "TLS_REJECTED";
                    }
                });

                boolean ok = false;
                String alpn = "";
                try (Socket tcp = new Socket("127.0.0.1", listener.getLocalPort());
                     SSLSocket c = (SSLSocket) clientCtx.getSocketFactory()
                             .createSocket(tcp, host, listener.getLocalPort(), true)) {
                    c.setSoTimeout(5000);
                    SSLParameters p = c.getSSLParameters();
                    p.setEndpointIdentificationAlgorithm("HTTPS");
                    p.setApplicationProtocols(new String[]{offered});
                    c.setSSLParameters(p);
                    c.startHandshake();  // Thử trust, identity, TLS, ALPN.
                    ok = true;
                    alpn = c.getApplicationProtocol();
                } catch (SSLException e) {
                    ok = false;
                }

                String serverResult = response.get(10, TimeUnit.SECONDS);
                if (ok != expected ||
                        ok && (!"demo/1".equals(alpn) ||
                               !"demo/1".equals(serverResult))) {
                    throw new AssertionError(label + ": ok=" + ok
                            + ", alpn=" + alpn + ", server=" + serverResult);
                }
                System.out.println(label + ": " +
                        (ok ? "OK (ALPN=" + alpn + ")" : "TLS_REJECTED"));
            } finally {
                ex.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        server = ctx("server.p12", true);
        SSLContext trusted = ctx("client-trust.p12", false);

        check("trusted-name", trusted, "localhost", "demo/1", true);
        check("untrusted-cert", SSLContext.getDefault(), "localhost", "demo/1", false);
        check("wrong-hostname", trusted, "127.0.0.1", "demo/1", false);
        check("alpn-no-overlap", trusted, "localhost", "demo/2", false);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TlsHandshakeLab.java
java TlsHandshakeLab
```

**Stdout khi chạy với JDK 24 và bộ certificate được tạo theo mục 5:**

```text
trusted-name: OK (ALPN=demo/1)
untrusted-cert: TLS_REJECTED
wrong-hostname: TLS_REJECTED
alpn-no-overlap: TLS_REJECTED
```

### Đọc từng kết quả

1. **`trusted-name`**: Client nạp truststore lab, nhận certificate `DNS:localhost`, yêu cầu kiểm tra endpoint theo HTTPS và đưa `demo/1` trong ALPN. Server chấp nhận nhãn này; chỉ trường hợp đó qua được toàn bộ điều kiện.
2. **`untrusted-cert`**: Client dùng trust configuration mặc định của JDK, không có certificate mới tạo trong trust anchors của lab. Dù hostname phù hợp và ALPN có thể khớp, certificate path không được tin nên handshake bị từ chối.
3. **`wrong-hostname`**: Client vẫn dùng **đúng truststore lab**, nên certificate **được tin**. Tuy nhiên client đặt identity cần kiểm tra là IP `127.0.0.1`, trong khi SAN chỉ có `DNS:localhost`; `setEndpointIdentificationAlgorithm("HTTPS")` khiến handshake thất bại. Đây là test quan trọng để phát hiện ứng dụng chỉ kiểm tra trust mà bỏ qua hostname.
4. **`alpn-no-overlap`**: Trust và hostname đều đúng nhưng client chỉ đưa `demo/2`. Server selector chỉ chấp nhận `demo/1`; khi không thấy giao thức thích hợp nó trả `null`, khiến JSSE trong lab từ chối handshake bằng cơ chế ALPN.

Hai chi tiết của chương trình cần hiểu:

- `new Socket("127.0.0.1", port)` chỉ dùng để kết nối vật lý tới server cục bộ; đối số `host` truyền vào `SSLSocketFactory.createSocket(tcp, host, port, true)` là **identity mà client chủ động yêu cầu xác minh**. Trong production, giá trị này phải xuất phát từ hostname đích tin cậy trong cấu hình/URL, không lấy từ input do peer tự khai báo.
- Chương trình dùng `IOException` trên phía server vì khi client từ chối handshake, Windows có thể báo socket abort thay vì một `SSLHandshakeException`. Phía client phân loại các `SSLException` trong test; **không** sử dụng cách catch rồi bỏ qua lỗi này để tiếp tục gửi dữ liệu trong code production.

**Phạm vi kiểm thử:** Chương trình lab sử dụng một server certificate tự ký được import có chủ đích vào truststore để tạo tình huống trust/hostname chính xác. Nó không kiểm thử certificate public CA, OCSP/CRL hoặc mutual TLS. Output trên là của cấu hình JDK/provider được kiểm tra; provider khác có thể biểu hiện lỗi hoặc thông báo khác, nhưng **các kỳ vọng bảo mật** vẫn giữ nguyên.

## 7. Kiểm thử âm tính nâng cao

### 7.1 Chứng chỉ không đúng danh tính

Tạo certificate chỉ chứa SAN `DNS:another.local` nhưng kết nối tới `localhost` bằng test client có endpoint identification bật. Kết quả đúng là **từ chối**, kể cả khi certificate đã được đưa vào truststore.

Nếu ứng dụng vẫn chấp nhận, cần xem có dùng trust manager tin tất cả hoặc đã vô hiệu `HTTPS` endpoint identification không. **Không sửa lỗi hostname bằng cách tắt kiểm tra hostname**. Cách đúng là cấp chứng chỉ đúng SAN và kết nối bằng hostname dự định.

### 7.2 Chứng chỉ hết hạn, không đúng mục đích, chain hỏng

Thử lần lượt với certificate hết hạn/chưa hiệu lực, thiếu intermediate CA, certificate không được cho phép làm server authentication hoặc thuật toán bị chính sách JDK cấm. Bộ kiểm tra certificate cần từ chối khi điều kiện chính sách không đạt. Không sửa bằng cách nhập tùy tiện chứng chỉ của đối tượng lạ vào truststore; phải giải quyết chain/CA/certificate và độ tin cậy thực.

**Không mặc định revocation luôn được kiểm tra.** Kiểm tra OCSP/CRL phụ thuộc cấu hình provider, PKIX/revocation policy và môi trường. Nếu nghiệp vụ yêu cầu revocation checking, cấu hình và kiểm thử riêng cả tình huống server OCSP/CRL không truy cập được.

### 7.3 Không tương thích TLS version/cipher

Nếu server chỉ chấp nhận TLS 1.3 còn client chỉ thử TLS 1.2, không có phiên bản chung và handshake phải thất bại. Với hệ thống hiện đại, ưu tiên TLS 1.3 và chỉ cho phép TLS 1.2 khi thực sự cần tương thích và dùng các cipher suites được chấp nhận theo chính sách hiện hành. Không bật lại SSLv3 hoặc TLS 1.0/1.1 để “làm bài test xanh”.

Có thể dùng trong **test cô lập** để ép tình huống mismatch (đoạn này không độc lập, giả sử đã tạo hai `SSLSocket` tương ứng):

```java
serverSideSocket.setEnabledProtocols(new String[]{"TLSv1.3"});
clientSideSocket.setEnabledProtocols(new String[]{"TLSv1.2"});
```

Thực hiện thiết lập **trước handshake**; các danh sách phải được runtime/provider hỗ trợ. Nếu cần kiểm tra tên cipher suite, dùng `getSupportedCipherSuites()` và chính sách runtime trước khi chỉ định, tránh hard-code bộ mã không được môi trường cho phép.

### 7.4 ALPN không khớp

Với ALPN, kiểm thử **hai kiểu chính sách khác nhau**:

- **Bắt buộc ALPN:** khi server chỉ hỗ trợ giao thức ứng dụng cố định, chọn selector từ chối nếu client không đề xuất giao thức đó. Đây là trường hợp lab đã kiểm chứng.
- **ALPN tùy chọn:** nếu không thương lượng protocol ID, handshake có thể thành công với kết quả rỗng. Ứng dụng phải từ chối hoặc dùng fallback **được thiết kế rõ**, không tự suy diễn `""` là `http/1.1` hay `h2`.

Giá trị `getApplicationProtocol()` **không tự xác minh** chứng chỉ và không đảm bảo application codec tương ứng thực sự đã được cài đặt.

### 7.5 Mutual TLS (mTLS)

Trong mTLS, **cả hai bên** kiểm tra certificate của nhau. Server cần trust material cho client certificate và bật yêu cầu client auth, ví dụ qua `SSLParameters.setNeedClientAuth(true)` hoặc `SSLServerSocket.setNeedClientAuth(true)` **trước handshake**. Kiểm thử client không có chứng chỉ, chứng chỉ hết hạn/không tin cậy, certificate đã bị thu hồi theo chính sách.

Ngay cả sau khi client certificate được TLS chấp nhận, ứng dụng vẫn cần **ủy quyền** theo danh tính/các thuộc tính đã xác minh; “client có cert hợp lệ” không có nghĩa “client được gọi mọi API”.

## 8. Cách chẩn đoán lỗi handshake trên JDK

Những lỗi điển hình:

| Triệu chứng | Giải thích thường gặp | Hướng điều tra |
| --- | --- | --- |
| `SSLHandshakeException`, nguyên nhân chứa `PKIX path building failed` | Client không dựng được đường tin cậy đến CA/trust anchor | Kiểm tra truststore, certificate chain và CA; không tự viết trust-all |
| Thông báo dạng `No subject alternative names matching ...` | Không khớp DNS/IP SAN với hostname mong đợi | Kiểm tra SAN và địa chỉ dùng khi kết nối |
| `handshake_failure` / `protocol_version` | Hai đầu không thống nhất TLS version/cipher hoặc có policy khác bị từ chối | Kiểm tra supported/enabled versions và chính sách hai đầu |
| `no_application_protocol` | Không thương lượng được ALPN khi phía server yêu cầu | Kiểm tra offered list, selector và giao thức ứng dụng thật |
| `bad_certificate` / `certificate_unknown` | Certificate bị peer hoặc local policy từ chối | Xác minh chain, usage, thời hạn, mTLS settings |
| `SSLPeerUnverifiedException` khi đọc peer cert | Chưa thiết lập được identity peer phù hợp với phiên | Kiểm tra handshake và peer authentication |
| `SocketException: connection reset/aborted` | Peer đóng kết nối trong/quanh handshake | Phối hợp log **hai phía**, xác định alert/nguyên nhân sớm hơn |

**Không coi bảng lỗi là ánh xạ một-một:** một nguyên nhân có thể tạo nhiều loại exception ở các giai đoạn và provider khác nhau. Khi test, assert “kết nối phải bị từ chối” cộng với điều kiện cấu hình kiểm thử, thay vì chỉ assert substring thông báo lỗi.

Bật debug JSSE trong **môi trường thử nghiệm có kiểm soát**:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager TlsHandshakeLab
```

Log này thường rất dài và do provider/JDK quyết định. Nó có thể chứa hostname, danh tính, chứng chỉ, thông tin kết nối và nhiều chi tiết nhạy cảm; **không bật đại trà trên production hoặc chia sẻ log thô**. Không dùng `all`, `data`, `plaintext`, `packet` nếu không thực sự cần, vì tăng lượng dữ liệu phơi bày. Khi điều tra, đối chiếu ClientHello/ServerHello, peer certificate và trust decisions; dữ liệu debug không có cấu trúc ổn định để parser ứng dụng phụ thuộc.

Một checklist điều tra ngắn:

1. Ghi **hostname/IP đích dự định**, không chỉ địa chỉ socket; kiểm tra SNI và SAN đúng.
2. Kiểm tra truststore/client `SSLContext` đang dùng; phân biệt trust lỗi với identity lỗi.
3. Ghi TLS version và `getApplicationProtocol()` **chỉ sau khi handshake thành công**; với handshake lỗi dùng trace phía client/server.
4. Kiểm tra yêu cầu ALPN; nếu không có giá trị phù hợp, ứng dụng có chấp nhận fallback hay phải từ chối?
5. Tránh retry vô hạn lỗi certificate hoặc fallback xuống giao thức/cipher yếu hơn; sửa cấu hình hoặc certificate.

## 9. Cách viết test để không tạo cảm giác an toàn giả

Test TLS thường dễ “đỗ” sai nếu mock mất phần bảo mật. Để test có giá trị:

- Dùng **server TLS thật chạy local** và **trust manager thật** khi muốn kiểm chứng certificate validation. Mock `SSLSocket.startHandshake()` chỉ chứng minh code gọi API, không chứng minh verify peer.
- Tạo một ca **trusted certificate + matching hostname** làm baseline. Nếu tất cả ca đều lỗi do thiếu file/cổng không mở, bộ test âm tính có thể báo xanh giả.
- Với ca âm tính, xác nhận server **đã thực sự lắng nghe và cung cấp certificate được dự kiến**; kiểm tra rõ điều kiện gây lỗi, không chỉ thấy `IOException` bất kỳ.
- Giữ độc lập từng ca: tạo context/connection mới, dùng truststore/test certificate có phạm vi riêng, test hostname mismatch **sau khi** chứng minh trusted-name thành công.
- Kiểm tra ALPN trên **cả client và server** khi cần, không kết luận chỉ từ danh sách client đề xuất.
- Không test theo cách sửa global `HostnameVerifier`, global truststore hoặc tắt verify để “kết nối được”; điều đó có thể làm các test khác vô tình kém an toàn.
- Trong CI, không phụ thuộc public Internet: network chập chờn, CA rotation và proxy có thể khiến test ngẫu nhiên. Cách lab loopback giúp tái lập lỗi và chỉ phụ thuộc JDK.
- Bài lab không đo hiệu năng, session resumption, certificate revocation hoặc tính đúng application protocol; bổ sung integration test riêng nếu nghiệp vụ cần.

### Những lỗi bảo mật phải tránh

1. **Trust-all `X509TrustManager`:** chấp nhận certificate bất kỳ, làm vô hiệu cơ sở xác thực peer.
2. **Tắt hostname verification:** một certificate được tin cậy cho host A có thể bị chấp nhận sai khi truy cập host B.
3. **Tưởng SNI thay cho verify:** SNI chỉ giúp server chọn certificate, chưa chứng minh nó thuộc server mong muốn.
4. **Tưởng ALPN thay cho certificate validation:** chỉ chọn codec ứng dụng, không chứng minh danh tính.
5. **Trả lỗi handshake nhưng tiếp tục gửi request:** phải dừng sử dụng socket/connection không thành công; không “fallback” sang HTTP hoặc TLS yếu một cách im lặng.
6. **Import bừa certificate lạ vào truststore chính:** làm mở rộng tập trust anchor quá mức; với lab chỉ tạo truststore cô lập.
7. **Gắn kết quả test vào một exception message:** dễ sai khi JDK hoặc OS đổi thông báo.

## 10. Câu hỏi tự kiểm tra

1. Vì sao một certificate đã có trong truststore mà handshake vẫn thất bại khi gọi `127.0.0.1` trong khi certificate chỉ khai báo `DNS:localhost`?
2. Với `SSLSocket` viết tay, dòng lệnh nào khiến JSSE kiểm tra hostname ngay khi handshake? Tại sao chỉ gọi `startHandshake()` chưa đủ?
3. Client đưa ALPN `["h2", "http/1.1"]` còn server chỉ cho `http/1.1`. Kết quả ALPN có thể là gì, và ai phải có khả năng triển khai giao thức đã chọn?
4. Tại sao một kết nối TLS có thể thành công nhưng `getApplicationProtocol()` vẫn trả `""`?
5. Cách khác nhau giữa test `untrusted-cert` và `wrong-hostname` trong lab là gì?
6. Server mTLS xác minh client certificate thành công. Ứng dụng có thể bỏ qua authorization theo người dùng/role hay không?

**Định hướng đáp án:** Trust path và SAN identity là hai kiểm tra khác nhau; với raw JSSE dùng `setEndpointIdentificationAlgorithm("HTTPS")`; ALPN thương lượng tên giao thức ứng dụng và có thể không dùng; mTLS authentication không thay authorization. Chỉ chấp nhận peer khi tất cả điều kiện bảo mật phù hợp với ứng dụng đều đạt.

## Tài liệu chính thống còn áp dụng

- [Java SE 26 — `SSLParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, ALPN, TLS parameters.
- [Java SE 26 — `SSLSocket`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): `startHandshake`, `getApplicationProtocol`, server ALPN selector (được bổ sung từ Java 9).
- [Java SE 26 — `SSLHandshakeException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html): lỗi khi hai đầu không thể thương lượng bảo mật.
- [Java SE 26 — `java.net.http.HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): HTTPS client cấp cao với TLS/ALPN do implementation quản lý.
- [Oracle JSSE Reference Guide (JDK 25)](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): hostname verification trên raw `SSLSocket`/`SSLEngine` và cách debug.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446) và [RFC 7301 — ALPN](https://www.rfc-editor.org/rfc/rfc7301).

**Cần nhớ:** Test thành công chỉ chứng minh kết nối hợp lệ của ca dương tính; để bảo đảm **xác minh danh tính đầu xa**, phải có ca âm tính cho certificate không tin cậy và hostname không khớp. ALPN là điều kiện tương thích ứng dụng, không thay thế trust hay endpoint identity.
