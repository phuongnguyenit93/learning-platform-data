# Áp dụng SSLParameters cho SSLSocket và SSLEngine trong Java 17+

## 1. Mục tiêu và bối cảnh

Một ứng dụng Java kết nối bằng TLS cần làm nhiều hơn việc tạo `SSLContext`: nó phải chọn phiên bản TLS/cipher phù hợp, xác minh **đúng danh tính hostname của server**, gửi đúng SNI, chọn ALPN khi cần, và quyết định có yêu cầu client certificate (mTLS) không. Trong JSSE, class `javax.net.ssl.SSLParameters` gom các thuộc tính này thành một object có thể áp cho:

- `SSLSocket`: kết nối TLS với `InputStream`/`OutputStream`, thường blocking I/O;
- `SSLEngine`: TLS/DTLS engine không gắn sẵn network transport, xử lý ciphertext và plaintext qua `ByteBuffer`;
- `SSLServerSocket`: listener TLS, áp policy trước khi nhận các kết nối.

`SSLParameters` vẫn là API **hiện hành** trong Java SE 17 và Java SE 25, thuộc module `java.base`. Bài chỉ dùng API còn áp dụng: TLS 1.3 và TLS 1.2 khi phù hợp, HTTPS endpoint identification, SNI, ALPN, JSSE `KeyManager`/`TrustManager`. Không dùng SSLv3, TLS 1.0/1.1, thuật toán yếu hoặc các internal APIs như `sun.security.*`.

**Phân biệt cốt lõi:** `SSLParameters` biểu diễn **cấu hình** cho handshake; kết quả TLS thực sự thương lượng phải được lấy **sau khi handshake hoàn tất** qua `SSLSession.getProtocol()`, `getCipherSuite()` và `SSLSocket/SSLEngine.getApplicationProtocol()`. Một phép kiểm `setSSLParameters` + `getSSLParameters` thành công **không chứng minh** certificate hoặc server identity đã được xác minh.

~~~text
SSLContext (key managers, trust managers, JSSE provider)
          |                                |
   SSLSocketFactory                 createSSLEngine(...)
          |                                |
       SSLSocket                        SSLEngine
          |                                |
   getSSLParameters()              getSSLParameters()
   thay đổi cấu hình               thay đổi cấu hình
          |                                |
   setSSLParameters(p)             setSSLParameters(p)
          |                                |
   startHandshake()             beginHandshake() + wrap/unwrap
          |                                |
   TLS record transport            Caller tự vận chuyển TLS records
          |                                |
   SSLSession/ALPN                  SSLSession/ALPN
~~~

## 2. API và mô hình trách nhiệm

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| `SSLContext` | `getDefault()`, `getInstance("TLS")`, `init(...)` | Khởi tạo TLS provider cùng credentials/trust |
| `SSLContext` | `getDefaultSSLParameters()` | Cấu hình mặc định cho provider |
| `SSLContext` | `getSupportedSSLParameters()` | Những option provider có hỗ trợ, có thể không enabled/allowed |
| `SSLParameters` | `setProtocols(String[])` | TLS versions được phép |
| `SSLParameters` | `setCipherSuites(String[])` | Cipher suites được enable |
| `SSLParameters` | `setEndpointIdentificationAlgorithm("HTTPS")` | Bật kiểm tra identity/hostname của TLS peer |
| `SSLParameters` | `setServerNames(List<SNIServerName>)` | SNI server names |
| `SSLParameters` | `setApplicationProtocols(String[])` | ALPN protocol names |
| `SSLParameters` | `setNeedClientAuth(boolean)` | Server yêu cầu bắt buộc client certificate |
| `SSLParameters` | `setWantClientAuth(boolean)` | Server yêu cầu tùy chọn client certificate |
| `SSLParameters` | `setUseCipherSuitesOrder(boolean)` | Gợi ý preference cipher phía server |
| `SSLParameters` | `setAlgorithmConstraints(AlgorithmConstraints)` | Bổ sung hạn chế thuật toán |
| `SSLSocket` | `getSSLParameters/setSSLParameters/startHandshake` | Áp config vào blocking TLS socket |
| `SSLEngine` | `setUseClientMode/setSSLParameters/wrap/unwrap` | Áp config và điều khiển TLS state |
| `SSLSession` | `getProtocol/getCipherSuite` | Kết quả đã thương lượng |
| `SSLSocket/SSLEngine` | `getApplicationProtocol` | ALPN đã được lựa chọn sau handshake |

**Supported khác default/enabled:** `getSupportedSSLParameters` có thể liệt kê nhiều options hơn `getDefaultSSLParameters`. Một protocol/cipher supported có thể bị runtime cấm theo `jdk.tls.disabledAlgorithms` hoặc không được default bật vì lý do an toàn. Không bật toàn bộ supported values để chữa lỗi handshake.

**SSLParameters không chứa private key/trust roots.** Key/cert chain của phía local đến từ `KeyManagerFactory`; trust anchors và certificate path verification đến từ `TrustManagerFactory`; cả hai được gắn vào `SSLContext.init(...)`. Cài `setEndpointIdentificationAlgorithm("HTTPS")` không biến một chứng thư không đáng tin thành đáng tin.

## 3. Thứ tự cấu hình đúng

~~~text
1. Có SSLContext với KeyManager/TrustManager thích hợp.
2. Tạo target SSLSocket hoặc SSLEngine MỚI.
3. Với SSLEngine, setUseClientMode(true/false) TRƯỚC handshake.
4. Lấy target.getSSLParameters hoặc context.getDefaultSSLParameters.
5. Chỉnh protocols/ciphers, endpoint identification, SNI, ALPN,
   thêm need/want clientAuth nếu là server.
6. GỌI target.setSSLParameters(p) để thực sự áp dụng.
7. CHỈ SAU ĐÓ:
      SSLSocket -> connect/startHandshake/I/O.
      SSLEngine -> beginHandshake, wrap/unwrap, vận chuyển records.
8. Khi handshake xong, kiểm SSLSession/ALPN/peer identity.
9. Đóng socket hoặc chạy TLS close_notify qua engine.
~~~

**Đừng quên bước 6.** `SSLParameters p = socket.getSSLParameters(); p.setProtocols(...);` chưa bảo đảm socket dùng thiết lập mới nếu chưa gọi `socket.setSSLParameters(p)`. Hãy coi `getSSLParameters` trả một cấu hình để chỉnh rồi **apply lại**. Tương tự với engine.

**Thời điểm phải trước handshake:** `SSLSocket.startHandshake`, read/write đầu tiên hoặc `getSession` có thể kích hoạt handshake; `SSLEngine.beginHandshake`, `wrap` và `unwrap` cũng có thể bắt đầu TLS. Cấu hình mode/parameters trước các lệnh ấy. Sau khi TLS đã negotiated, đổi parameters không có nghĩa phiên đang dùng lập tức đổi cipher, hostname hay giao thức.

Ví dụ ngắn khi đã có socket:

~~~java
SSLParameters p = socket.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
p.setServerNames(List.of(new SNIHostName("service.example.test")));
p.setApplicationProtocols(new String[]{"h2", "http/1.1"});
socket.setSSLParameters(p);  // Bắt buộc trước handshake.
socket.startHandshake();
~~~

Đây là snippet **trong method**: `socket` là SSLSocket đã chuẩn bị, dùng trust context hợp lệ; cần import `SSLParameters`, `SNIHostName`, `List`. Không phải chương trình runnable độc lập.

## 4. Phiên bản TLS và cipher suites hiện hành

**TLS 1.3** nên được ưu tiên; **TLS 1.2** vẫn có thể được dùng với cipher/crypto policy phù hợp khi cần tương thích. Theo RFC 9325, không thương lượng SSLv2/SSLv3/TLSv1.0/TLSv1.1. Không “bật lại” TLS 1.0/1.1 chỉ để kết nối được với một server lỗi thời; nên nâng cấp server hoặc cô lập compatibility bridge qua đánh giá bảo mật.

Đoạn helper chọn **giao giữa default enabled protocols và danh sách hiện hành**:

~~~java
static String[] modernDefaultProtocols(SSLContext context) {
    String[] enabled = context.getDefaultSSLParameters().getProtocols();
    String[] modern = Arrays.stream(enabled)
            .filter(p -> "TLSv1.3".equals(p) || "TLSv1.2".equals(p))
            .toArray(String[]::new);
    if (modern.length == 0) {
        throw new IllegalStateException("No acceptable TLS versions enabled");
    }
    return modern;
}
~~~

Đây là method hợp lệ Java 17+ nếu đã import `SSLContext` và `Arrays`. **Fail closed** nếu không có protocol an toàn đang enabled. Với hệ thống chỉ TLS 1.3, đổi allowlist theo approved policy, và test đối tác hỗ trợ.

### Cipher suite chọn thế nào?

Ưu tiên để **JDK default enabled cipher suites** xử lý nếu chưa có nhu cầu allowlist riêng. Nếu cần tổ chức quy định cipher allowlist, lấy giao với các suites đang enabled và xét cả loại certificate/key exchange:

~~~java
SSLParameters p = context.getDefaultSSLParameters();
Set<String> allowed = Set.of(
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256");
String[] selected = Arrays.stream(p.getCipherSuites())
        .filter(allowed::contains)
        .toArray(String[]::new);
if (selected.length == 0) {
    throw new IllegalStateException("No approved enabled cipher suite");
}
p.setCipherSuites(selected);
~~~

Snippet này **không độc lập**: cần context/imports. Danh sách chỉ minh họa AES-GCM với một môi trường thích hợp, không phải policy hoàn chỉnh cho mọi ECDSA-only profile/FIPS/provider. TLS 1.3 cipher names không tự mô tả toàn bộ key-exchange/signature algorithm; certificate policy và `jdk.tls.disabledAlgorithms` vẫn tham gia.

JDK còn có `jdk.certpath.disabledAlgorithms` và có thể có `jdk.tls.legacyAlgorithms` theo security configuration. `SSLParameters.setAlgorithmConstraints` là **lớp hạn chế bổ sung**, không phải cơ chế hợp lệ để bỏ disabled algorithms của JVM. Khi cấu hình một suite unsupported, `setSSLParameters` hoặc handshake có thể báo lỗi: sửa policy/compatibility, không tự hạ an toàn.

## 5. Hostname verification và SNI — phải nhất quán

Raw `SSLSocket` hay `SSLEngine` **không được mặc định coi là đã xác minh đúng hostname HTTP**. Nếu client có ý định truy cập `api.example.test`, certificate cần được kiểm tra với **hostname logic đó**, bên cạnh certificate chain/trust anchors. Bật:

~~~java
p.setEndpointIdentificationAlgorithm("HTTPS");
p.setServerNames(List.of(new SNIHostName("api.example.test")));
~~~

**Endpoint identification** yêu cầu JSSE áp quy tắc đối chiếu server identity theo HTTPS tại handshake. **SNI** đưa tên server mong muốn vào ClientHello để virtual-host server chọn đúng certificate. SNI **không phải** chứng minh danh tính; vẫn cần PKIX/trust manager/hostname check. Không lấy SNI từ user header không tin cậy.

**Chi tiết bảo mật quan trọng trong SunJSSE:** SNI **có thể được dùng trước peerHost khi xác minh endpoint**. Oracle JSSE Guide và implementation `X509ExtendedTrustManager` đề cập server name của SNI ảnh hưởng hostname identity check. Khi code thiết lập SNI khác với logical hostname, handshake có thể kiểm tra tên khác ý định ứng dụng. Hãy nhất quán **expected origin host ↔ peer host ↔ SNI name**.

Trong ví dụ end-to-end, khi muốn thử sai tên, ta đổi **cả peerHost và SNI** thành `untrusted.invalid`. Để SNI `localhost` mà chỉ đổi peerHost có thể khiến test không chứng minh đúng điều cần chứng minh.

Với IP literal, IDN, wildcard hay tên khác canonical URI, thiết kế rõ mối quan hệ certificate SAN, SNI và hostname kỳ vọng. Đừng “chữa” name mismatch bằng trust-all manager hoặc tắt `HTTPS` algorithm.

## 6. ALPN: áp config nhưng phải kiểm kết quả

Application-Layer Protocol Negotiation:

~~~java
p.setApplicationProtocols(new String[]{"h2", "http/1.1"});
// Sau TLS handshake:
String selected = socket.getApplicationProtocol();
~~~

`getApplicationProtocol()` trả kết quả thương lượng, **không phải phần tử đầu của mảng được cấu hình**. Khi chưa handshake, kết quả có thể không có giá trị; nếu TLS handshake hoàn tất nhưng không chọn được application protocol, code phải xử lý theo provider/application protocol. Một server có thể có callback chọn ALPN và thứ tự ưu tiên riêng.

**ALPN không tự biến TLS socket thành HTTP/2 implementation.** Nếu negotiated `h2`, application phải dùng đúng HTTP/2 parser/protocol; nếu negotiated `http/1.1` thì xử lý HTTP/1.1. Đừng gửi bytes của giao thức sai rồi đổ lỗi cho SSLParameters.

ALPN có cả trên `SSLSocket` và `SSLEngine` qua `getApplicationProtocol()`. Trong chương trình chạy thật ở phần 10, hai phía cùng chỉ quảng bá `http/1.1` nên có thể assert kết quả chính xác.

## 7. SSLParameters cho SSLEngine: mode và transport

`SSLEngine` không tự tạo TCP socket hoặc tự gửi TLS records. Cấu hình client:

~~~java
SSLEngine engine = context.createSSLEngine("api.example.test", 443);
engine.setUseClientMode(true);

SSLParameters p = engine.getSSLParameters();
p.setProtocols(modernDefaultProtocols(context));
p.setEndpointIdentificationAlgorithm("HTTPS");
p.setServerNames(List.of(new SNIHostName("api.example.test")));
p.setApplicationProtocols(new String[]{"h2", "http/1.1"});
engine.setSSLParameters(p);

// Khi buffers và transport đã sẵn sàng:
engine.beginHandshake();
~~~

Đây là snippet **trong một method**, cần context/helper/imports. `createSSLEngine(peerHost,port)` truyền peer metadata mang tính **advisory**, nhưng có ích cho hostname verification và session management. Trong client mode, đừng tạo engine không có peer host rồi mong JSSE tự suy ra expected hostname.

Sau `beginHandshake`, application **bắt buộc điều khiển vòng state machine**:

~~~text
NEED_WRAP         -> engine.wrap(plaintext, networkOut) -> gửi TLS records
NEED_UNWRAP       -> nhận bytes -> engine.unwrap(networkIn, plaintextOut)
NEED_UNWRAP_AGAIN -> tiếp tục unwrap theo yêu cầu provider
NEED_TASK         -> chạy getDelegatedTask() đến hết
FINISHED          -> kết quả operation báo hoàn thành handshake
NOT_HANDSHAKING   -> TLS hiện không trong handshake; xử lý app data
~~~

`SSLEngineResult.Status` khác `HandshakeStatus`:

| Status | Ý nghĩa | Cách phản ứng |
| --- | --- | --- |
| `OK` | Operation tiến bình thường | Xem HandshakeStatus/bytesConsumed/Produced |
| `BUFFER_UNDERFLOW` | Input thiếu một TLS record hoàn chỉnh | Nhận thêm bytes, giữ partial bytes |
| `BUFFER_OVERFLOW` | Output buffer không đủ | Resize hoặc dùng buffer lớn theo SSLSession |
| `CLOSED` | TLS engine đã/đang đóng | Hoàn tất closure/cleanup |

Khi `NEED_TASK`:

~~~java
Runnable task;
while ((task = engine.getDelegatedTask()) != null) {
    task.run();
}
~~~

Đoạn minh họa trong handshake driver có biến `engine`, không phải driver độc lập. Delegated task có thể thực hiện certificate verification hoặc tính toán tốn CPU; với event loop cần executor phù hợp. Bỏ qua tasks dẫn tới state không tiến.

Lấy kích thước buffer ban đầu từ API:

~~~java
int packetSize = engine.getSession().getPacketBufferSize();
int applicationSize = engine.getSession().getApplicationBufferSize();
ByteBuffer networkBuffer = ByteBuffer.allocate(packetSize);
ByteBuffer applicationBuffer = ByteBuffer.allocate(applicationSize);
~~~

Snippet cần `import java.nio.ByteBuffer` và biến engine hợp lệ. Không hardcode một cỡ buffer cố định rồi giả định đủ với mọi provider/handshake. Theo dõi `bytesConsumed()`/`bytesProduced()`, `ByteBuffer.flip/compact`, xử lý read/write từng phần và deadlines. `wrap` có thể tạo handshake data mà chưa consume application data.

**Đóng engine:** `closeOutbound()` không tự gửi close_notify tới peer; cần tiếp tục `wrap`, chuyển TLS records ra transport và xử lý response theo policy. Khi nhận closure bằng `unwrap`, theo dõi `isInboundDone()`; EOF TCP mà không có TLS close_notify có thể gây truncation risk. Engine đã đóng không được reuse.

## 8. Server side: need/want client certificate

Một TLS server có thể áp:

~~~java
SSLEngine serverEngine = context.createSSLEngine();
serverEngine.setUseClientMode(false);
SSLParameters p = serverEngine.getSSLParameters();
p.setProtocols(modernDefaultProtocols(context));
p.setNeedClientAuth(true);
p.setUseCipherSuitesOrder(true);
p.setApplicationProtocols(new String[]{"http/1.1"});
serverEngine.setSSLParameters(p);
~~~

Đoạn minh họa trong method, **chưa** tạo server credentials và chưa handshake. `setNeedClientAuth(true)` buộc client gửi certificate được server trust; nếu client không có, handshake thất bại theo TLS/profile. `setWantClientAuth(true)` chỉ yêu cầu tùy chọn và có thể cho phép client không có certificate.

**`needClientAuth` và `wantClientAuth` loại trừ lẫn nhau.** Gọi `setNeedClientAuth(true)` xóa `wantClientAuth`; gọi `setWantClientAuth(true)` xóa `needClientAuth`. Những flags này chỉ có ý nghĩa với server-side TLS client certificate authentication, **không phải hostname verification của client**.

Với `SSLServerSocket` cũng có `getSSLParameters/setSSLParameters`; hãy áp server policy **trước accept**. Server cần private key/cert qua `KeyManagerFactory`; nếu bật mTLS, server cần `TrustManagerFactory` tin đúng client CA. Một certificate TLS hợp lệ vẫn chưa cấp role `admin`: application phải map identity/tenant và kiểm authorization.

`setUseCipherSuitesOrder(true)` nói về preference server, có thể ảnh hưởng khác nhau theo provider/protocol; không bảo đảm server chọn phần tử đầu tiên trong mọi TLS handshake.

## 9. Chương trình Java 17+ số 1: chỉ áp cấu hình, không mở network

File **`TlsParametersDemo.java`** chạy độc lập với JDK chuẩn, không cần internet, certificate hoặc server. Nó tạo SSLSocket **chưa connected**, một SSLEngine client (peerHost có khai báo) và một server-mode engine, rồi kiểm `getSSLParameters` sau khi áp.

~~~java
import java.util.Arrays;
import java.util.List;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

public final class TlsParametersDemo {
    private static final String PEER = "api.example.test";
    private static final String[] APPLICATION_PROTOCOLS = {"h2", "http/1.1"};

    static String[] modernDefaultProtocols(SSLContext context) {
        String[] enabled = context.getDefaultSSLParameters().getProtocols();
        String[] modern = Arrays.stream(enabled)
                .filter(p -> "TLSv1.3".equals(p) || "TLSv1.2".equals(p))
                .toArray(String[]::new);
        if (modern.length == 0) {
            throw new IllegalStateException("No acceptable TLS versions enabled");
        }
        return modern;
    }

    static SSLParameters clientPolicy(SSLContext context, String host) {
        SSLParameters params = context.getDefaultSSLParameters();
        params.setProtocols(modernDefaultProtocols(context));
        params.setEndpointIdentificationAlgorithm("HTTPS");
        params.setServerNames(List.of(new SNIHostName(host)));
        params.setApplicationProtocols(APPLICATION_PROTOCOLS);
        return params;
    }

    static SSLParameters serverPolicy(SSLContext context) {
        SSLParameters params = context.getDefaultSSLParameters();
        params.setProtocols(modernDefaultProtocols(context));
        params.setNeedClientAuth(true);
        params.setUseCipherSuitesOrder(true);
        params.setApplicationProtocols(APPLICATION_PROTOCOLS);
        return params;
    }

    static boolean hasExpectedSni(SSLParameters params) {
        return params.getServerNames() != null
                && params.getServerNames().size() == 1
                && params.getServerNames().get(0) instanceof SNIHostName name
                && PEER.equals(name.getAsciiName());
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLParameters clientPolicy = clientPolicy(context, PEER);

        try (SSLSocket socket =
                (SSLSocket) context.getSocketFactory().createSocket()) {
            socket.setUseClientMode(true);
            socket.setSSLParameters(clientPolicy); // Before connect/handshake.
            SSLParameters effective = socket.getSSLParameters();
            System.out.println("socket modern protocols: "
                    + Arrays.equals(effective.getProtocols(),
                                    modernDefaultProtocols(context)));
            System.out.println("socket HTTPS name check: "
                    + "HTTPS".equals(effective.getEndpointIdentificationAlgorithm()));
            System.out.println("socket explicit SNI: " + hasExpectedSni(effective));
            System.out.println("socket ALPN configured: "
                    + Arrays.equals(effective.getApplicationProtocols(),
                                    APPLICATION_PROTOCOLS));
            System.out.println("socket default ciphers retained: "
                    + Arrays.equals(effective.getCipherSuites(),
                                    context.getDefaultSSLParameters().getCipherSuites()));
            System.out.println("socket connected: " + socket.isConnected());
        }

        SSLEngine clientEngine = context.createSSLEngine(PEER, 443);
        clientEngine.setUseClientMode(true); // Must be set before handshake.
        clientEngine.setSSLParameters(clientPolicy(context, PEER));
        SSLParameters engineEffective = clientEngine.getSSLParameters();
        System.out.println("engine client mode: " + clientEngine.getUseClientMode());
        System.out.println("engine peer host: " + PEER.equals(clientEngine.getPeerHost()));
        System.out.println("engine HTTPS name check: "
                + "HTTPS".equals(engineEffective.getEndpointIdentificationAlgorithm()));
        System.out.println("engine explicit SNI: " + hasExpectedSni(engineEffective));
        System.out.println("engine ALPN configured: "
                + Arrays.equals(engineEffective.getApplicationProtocols(),
                                APPLICATION_PROTOCOLS));
        System.out.println("engine handshake not started: "
                + (clientEngine.getHandshakeStatus()
                        == SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING));

        SSLEngine serverEngine = context.createSSLEngine();
        serverEngine.setUseClientMode(false);
        serverEngine.setSSLParameters(serverPolicy(context));
        SSLParameters serverEffective = serverEngine.getSSLParameters();
        System.out.println("server engine mode: " + !serverEngine.getUseClientMode());
        System.out.println("server engine mTLS required: "
                + serverEffective.getNeedClientAuth());
        System.out.println("server engine want disabled: "
                + !serverEffective.getWantClientAuth());
        System.out.println("server cipher order configured: "
                + serverEffective.getUseCipherSuitesOrder());

        SSLParameters precedence = new SSLParameters();
        precedence.setWantClientAuth(true);
        precedence.setNeedClientAuth(true);
        System.out.println("need clears want: "
                + (precedence.getNeedClientAuth()
                    && !precedence.getWantClientAuth()));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 TlsParametersDemo.java
java TlsParametersDemo
~~~

**Stdout chính xác** đã kiểm thử với OpenJDK **24.0.2** và `--release 17`:

~~~text
socket modern protocols: true
socket HTTPS name check: true
socket explicit SNI: true
socket ALPN configured: true
socket default ciphers retained: true
socket connected: false
engine client mode: true
engine peer host: true
engine HTTPS name check: true
engine explicit SNI: true
engine ALPN configured: true
engine handshake not started: true
server engine mode: true
server engine mTLS required: true
server engine want disabled: true
server cipher order configured: true
need clears want: true
~~~

**Ý nghĩa:** tất cả dòng true ở đây là **kiểm cấu hình**, không phải chứng minh đã bảo mật một kết nối TCP. `socket connected: false` và `engine handshake not started: true` cho thấy hoàn toàn không có TLS negotiation với đối tác bên ngoài. `server engine mTLS required: true` chỉ là một cờ, không chứng minh server có private key/cert hoặc client có certificate.

## 10. Chương trình số 2: handshake TLS thật với chứng thư test trên localhost

Để quan sát `SSLParameters` tác động vào handshake, dùng `SSLServerSocket` và `SSLSocket` trên **127.0.0.1**. Chương trình chỉ cần JDK, không cần internet hay thư viện ngoài. Hai phía dùng **chứng thư self-signed test** tạo bởi `keytool` và explicit TrustManager. Test:
1. TLS 1.2/1.3 được negotiated;
2. certificate test `localhost` được trust và hostname check được bật;
3. ALPN `http/1.1` thương lượng;
4. hai peer trao đổi một byte trong TLS tunnel;
5. hostname/SNI khác certificate là `untrusted.invalid` bị từ chối handshake.

**Tuyệt đối không dùng keystore và password demo ở production.** Lệnh sử dụng password giả cố định dễ thấy trong shell/process list để mục tiêu học tập có thể tái lập; production dùng secrets manager, CA/trust anchors đã thẩm định và kiểm rotation/revocation.

### A. Tạo PKCS12 bằng keytool

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 3072 \
  -sigalg SHA256withRSA -validity 2 -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -keystore test.p12 -storetype PKCS12 \
  -storepass testpass123 -keypass testpass123 -noprompt
~~~

Với Windows PowerShell, chạy một dòng duy nhất (không dùng dấu `\` của Bash):

~~~powershell
keytool -genkeypair -alias localhost -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 2 -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -keystore test.p12 -storetype PKCS12 -storepass testpass123 -keypass testpass123 -noprompt
~~~

Đây là private key/cert **tạm**, thời hạn hai ngày. Xóa file test khi không dùng; nếu cert hết hạn, tạo mới. Không commit file `test.p12` vào Git, không sử dụng như một Root CA cho dịch vụ thật.

### B. File TlsLoopbackHandshakeDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import javax.net.ssl.*;

public final class TlsLoopbackHandshakeDemo {
    static String[] modern(SSLContext c) {
        String[] values=Arrays.stream(c.getDefaultSSLParameters().getProtocols())
                .filter(p->p.equals("TLSv1.3")||p.equals("TLSv1.2"))
                .toArray(String[]::new);
        if(values.length==0)throw new IllegalStateException("No modern TLS");
        return values;
    }
    static SSLContext context(KeyStore keys,char[] password,boolean server)
            throws Exception {
        TrustManagerFactory trusts=TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trusts.init(keys);
        SSLContext c=SSLContext.getInstance("TLS");
        if(server){
            KeyManagerFactory km=KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            km.init(keys,password);
            c.init(km.getKeyManagers(),trusts.getTrustManagers(),
                    new SecureRandom());
        }else{
            c.init(null,trusts.getTrustManagers(),new SecureRandom());
        }
        return c;
    }
    static SSLServerSocket listener(SSLContext c)throws IOException{
        SSLServerSocket socket=(SSLServerSocket)c.getServerSocketFactory()
                .createServerSocket(0,4,InetAddress.getByName("127.0.0.1"));
        socket.setSoTimeout(5000);
        SSLParameters p=socket.getSSLParameters();
        p.setProtocols(modern(c));
        p.setApplicationProtocols(new String[]{"http/1.1"});
        socket.setSSLParameters(p);
        return socket;
    }
    static SSLSocket connect(SSLContext c,int port,String host)throws IOException{
        Socket tcp=new Socket();
        tcp.connect(new InetSocketAddress("127.0.0.1",port),5000);
        SSLSocket ssl=(SSLSocket)c.getSocketFactory()
                .createSocket(tcp,host,port,true);
        ssl.setSoTimeout(5000);
        SSLParameters p=ssl.getSSLParameters();
        p.setProtocols(modern(c));
        p.setEndpointIdentificationAlgorithm("HTTPS");
        p.setServerNames(List.of(new SNIHostName(host)));
        p.setApplicationProtocols(new String[]{"http/1.1"});
        ssl.setSSLParameters(p);
        return ssl;
    }
    public static void main(String[] args)throws Exception{
        if(args.length!=2)throw new IllegalArgumentException(
                "Usage: java TlsLoopbackHandshakeDemo test.p12 password");
        char[] pwd=args[1].toCharArray();
        KeyStore ks=KeyStore.getInstance("PKCS12");
        try(InputStream in=Files.newInputStream(Path.of(args[0]))){
            ks.load(in,pwd);
        }
        SSLContext server=context(ks,pwd,true);
        SSLContext client=context(ks,pwd,false);
        Arrays.fill(pwd,'\0');
        ExecutorService executor=Executors.newSingleThreadExecutor();
        try{
            try(SSLServerSocket bound=listener(server)){
                Future<Boolean> worker=executor.submit(()->{
                    try(SSLSocket peer=(SSLSocket)bound.accept()){
                        peer.setSoTimeout(5000);
                        peer.startHandshake();
                        int b=peer.getInputStream().read();
                        peer.getOutputStream().write(b+1);
                        peer.getOutputStream().flush();
                        return b==42&&"http/1.1".equals(peer.getApplicationProtocol());
                    }
                });
                try(SSLSocket clientSocket=connect(client,bound.getLocalPort(),"localhost")){
                    clientSocket.startHandshake();
                    clientSocket.getOutputStream().write(42);
                    clientSocket.getOutputStream().flush();
                    int read=clientSocket.getInputStream().read();
                    String version=clientSocket.getSession().getProtocol();
                    System.out.println("modern TLS negotiated: "+
                            (version.equals("TLSv1.3")||version.equals("TLSv1.2")));
                    System.out.println("peer certificate accepted: "+
                            clientSocket.getSession().getPeerPrincipal().getName()
                                    .contains("CN=localhost"));
                    System.out.println("ALPN negotiated: "+
                            "http/1.1".equals(clientSocket.getApplicationProtocol()));
                    System.out.println("encrypted roundtrip: "+(read==43));
                }
                System.out.println("server exchange succeeded: "+
                        worker.get(10,TimeUnit.SECONDS));
            }
            try(SSLServerSocket bound=listener(server)){
                Future<Boolean> worker=executor.submit(()->{
                    try(SSLSocket peer=(SSLSocket)bound.accept()){
                        peer.setSoTimeout(5000);
                        peer.startHandshake();
                        return false;
                    }catch(IOException handshakeOrTransportClosed){
                        return true;
                    }
                });
                boolean rejected=false;
                try(SSLSocket wrong=connect(client,bound.getLocalPort(),
                                            "untrusted.invalid")){
                    wrong.startHandshake();
                }catch(SSLHandshakeException expected){
                    rejected=true;
                }
                System.out.println("wrong hostname rejected: "+rejected);
                System.out.println("server handled failed handshake: "+
                        worker.get(10,TimeUnit.SECONDS));
            }
        }finally{
            executor.shutdownNow();
        }
    }
}
~~~

### C. Biên dịch và chạy

~~~bash
javac --release 17 TlsLoopbackHandshakeDemo.java
java TlsLoopbackHandshakeDemo test.p12 testpass123
~~~

**Stdout chính xác** đã kiểm thử với JDK 24.0.2 và chứng thư localhost được tạo bằng keytool:

~~~text
modern TLS negotiated: true
peer certificate accepted: true
ALPN negotiated: true
encrypted roundtrip: true
server exchange succeeded: true
wrong hostname rejected: true
server handled failed handshake: true
~~~

**Lưu ý cách diễn giải:**
- `modern TLS negotiated` dùng `SSLSession.getProtocol()` **sau** handshake, không phải mảng enabled.
- `peer certificate accepted` kết hợp handshake đã thành công với kiểm tên subject của fixture; việc kiểm SAN/hostname thực sự do HTTPS endpoint identification + TrustManager trong JSSE làm. **Chỉ so chuỗi CN không thay certificate verification.**
- `ALPN negotiated` là negotiated value, còn byte 42→43 không có nghĩa đang chạy HTTP/1.1 request thực; code chỉ thực hiện TLS protected raw-byte exchange.
- `wrong hostname rejected` chứng minh cấu hình HTTPS ID check có tác dụng khi expected peerHost và SNI cùng là tên không có trong SAN.
- `server handled failed handshake` gộp các lỗi IOException (TLS alert hoặc transport closed/reset); cụ thể Windows/Linux có thể phát exception khác nhau, không coi mọi lỗi là cùng một TLS alert.
- Bằng chứng này là về **SSLSocket**; `SSLEngine` ở chương trình số 1 mới kiểm config, chưa có engine-to-engine driver. Không suy luận engine handshake đã được kiểm thử.

### Lỗi test SNI lệch peerHost

Nếu giả lập wrong peerHost nhưng vẫn ép `SNIHostName("localhost")`, SunJSSE có thể dùng tên SNI để kiểm certificate và làm test pass sai mục tiêu. Mọi security test phải nói rõ **logical target**. Trong production cần lấy expected hostname từ origin tin cậy rồi nhất quán giữa URL, peer metadata và SNI.

## 11. SNI, ALPN, mTLS và authentication có thể sai dù TLS hoạt động

**SNI không cung cấp identity:** client gửi SNI để server chọn virtual-host certificate. Cert sau đó vẫn phải có chain và SAN đúng. Đừng cho rằng server nhìn thấy SNI là user đã đăng nhập hoặc client chứng minh được gì.

**ALPN không phải authorization:** `h2`, `http/1.1` chỉ tên protocol. Application phải có HTTP implementation đúng negotiated result, kiểm authentication và phân quyền riêng.

**mTLS chỉ cung cấp client certificate authentication ở TLS layer.** Muốn user/service nào được gọi API nào, cần map certificate subject/issuer/fingerprint/trust domain tới chính sách role/tenant/scope. Một TLS session client cert hợp lệ chưa tự cho phép xóa dữ liệu.

**Session reuse/rotation:** TLS session resumption và pooled connections có thể có vòng đời khác việc thay store/certificate. Thay SSLParameters/keystore file không buộc các TLS sessions đang mở tái xác minh. Khi rotate credentials, cần thay SSLContext/connection theo lifecycle và kiểm chính sách ứng dụng tại thời điểm request.

**TLS 1.3 0-RTT:** early data có replay risk; không tự giả định mọi dữ liệu trước handshake completion là an toàn. Ví dụ không bật 0-RTT; với tác vụ thay đổi trạng thái cần ngăn replay ở application layer.

## 12. SSLSocket và SSLEngine khác nhau ra sao?

| Vấn đề | SSLSocket | SSLEngine |
| --- | --- | --- |
| Tạo mới | `SSLContext.getSocketFactory().createSocket` | `SSLContext.createSSLEngine` |
| Client/server mode | `setUseClientMode` | `setUseClientMode` |
| Apply SSLParameters | `setSSLParameters` | `setSSLParameters` |
| Bắt đầu handshake | `startHandshake`/I/O ngầm | `beginHandshake` hoặc wrap/unwrap |
| Transport | Có Socket/TCP streams | Caller lo channel/network |
| ByteBuffers | Provider xử lý nội bộ | Caller quản lý packet/app buffers |
| Delegated tasks | Provider/socket handling | Caller phải chạy tasks |
| Negotiated TLS | `getSession` | `getSession` |
| ALPN result | `getApplicationProtocol` | `getApplicationProtocol` |
| Closure | `close` socket | closeOutbound/closeInbound/close_notify |
| I/O model | Thường blocking | Thích hợp NIO/nonblocking event loop |
| Chứng thư/identity | SSLContext + SSLParameters | Cùng cơ chế |
| Security level | Do policy/trust quyết định | Do policy/trust quyết định |

SSLEngine không “bảo mật hơn” SSLSocket chỉ vì nonblocking; bảo mật của cả hai phụ thuộc certificate/trust, hostname, protocol/cipher, SNI, ALPN và authorization.

## 13. Troubleshooting các lỗi TLS

| Hiện tượng | Nguyên nhân có thể | Phản ứng đúng |
| --- | --- | --- |
| Sửa getSSLParameters nhưng không tác dụng | Quên gọi setSSLParameters | Apply lại trước handshake |
| Protocol/cipher unsupported | Danh sách không thuộc provider | Dùng defaults+allowlist và fail closed |
| TLS protocol_version alert | Hai phía không có version chung | Kiểm TLS 1.3/1.2, không bật legacy |
| No cipher suites in common | Cipher/key/cert không tương thích | Kiểm suites enabled, certificate algorithms |
| PKIX path building failed | Thiếu trust anchor hoặc certificate chain sai | Sửa truststore/PKI, không trust-all |
| No subject alternative DNS name matching | Hostname/SNI không match SAN | Sửa origin/SAN, giữ HTTPS identification |
| Sai hostname nhưng handshake thành công | Endpoint algo chưa bật hoặc SNI mismatch | Kiểm p.getEndpointIdentificationAlgorithm/SNI/peerHost |
| No application protocol | ALPN không giao nhau | Sửa app-layer protocol policy |
| getApplicationProtocol null/empty | Chưa handshake hoặc chưa negotiate | Chỉ đọc sau handshake và có fallback rõ |
| Server needClientAuth nhưng client không có cert | mTLS yêu cầu cert bắt buộc | Cấp client cert/KeyManager phù hợp |
| SSLEngine đứng ở NEED_TASK | Chưa chạy delegated tasks | Run getDelegatedTask |
| SSLEngine BUFFER_UNDERFLOW | TLS packet chưa nhận đủ | Đọc thêm bytes, giữ input buffer |
| SSLEngine BUFFER_OVERFLOW | Output buffer thiếu | Resize và retry |
| TCP reset khi wrong-host handshake | Client đã đóng khi validation fail | Báo expected failure, không suy luận cipher |
| Đổi SSLParameters sau handshake mà không đổi session | Parameters không renegotiate tự động | Tạo connection mới |
| Server thiếu private key | Chỉ có TrustManager mà không KeyManager | Cấu hình keystore server |
| Certificate hợp lệ nhưng app user không có quyền | TLS authentication khác authorization | Kiểm tenant/role/permissions |
| Debug log lộ TLS internals | Bật javax.net.debug trên production | Giới hạn debug và redact dữ liệu |

## 14. Security/test checklist

| Test | Điều mong đợi |
| --- | --- |
| SSLContext có modern default protocols | Giao với TLSv1.3/TLSv1.2 không rỗng |
| SSLSocket setSSLParameters | Readback protocols/HTTPS/SNI/ALPN đúng |
| SSLSocket chưa connect | Không coi cấu hình là handshake |
| SSLEngine client mode | `getUseClientMode() == true` |
| SSLEngine peerHost | Bằng hostname logic cần xác minh |
| SSLEngine setSSLParameters | Readback HTTPS/SNI/ALPN |
| SSLEngine chưa beginHandshake | NOT_HANDSHAKING |
| Server engine mTLS required | need=true, want=false |
| SSLServerSocket config trước accept | TLS versions/ALPN áp vào accepted socket |
| Trust chain và SAN localhost đúng | Handshake thành công |
| Peer hostname/SNI sai | Fail TLS handshake |
| Certificate không được trust | Fail closed, không cài trust-all |
| ALPN http/1.1 của hai phía | Negotiated result đúng |
| TLSv1.0/TLSv1.1 server | Không fallback xuống legacy |
| TLSv1.2 hoặc 1.3 có cipher compatible | Handshake được nếu trust cũng đúng |
| Server require client cert, client thiếu | TLS handshake fail |
| Server want client cert, client thiếu | Có thể pass TLS nhưng app policy xét tiếp |
| Engine NEED_TASK | Tasks được chạy trước khi tiến |
| Engine BUFFER_UNDERFLOW | Retry khi nhận thêm data, không mất partial record |
| Engine BUFFER_OVERFLOW | Resize và retry |
| Engine close_notify | TLS orderly shutdown theo policy |
| Session protocol/cipher | Đọc negotiated, không suy đoán từ config |
| Cert/key rotation | Connection mới dùng context mới |
| TLS log | Không lộ private keys, secrets, plaintext |

**Ba tầng kiểm thử khác nhau:** (1) config readback trên socket/engine; (2) TLS handshake thật với trust/certificate/ALPN; (3) business authorization và credential lifecycle. Chỉ test một tầng không đủ chứng minh cả hệ thống an toàn.

## 15. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “SSLParameters là TLS handshake.” | Nó chỉ là config object |
| “Chỉnh params từ getSSLParameters là tự áp.” | Phải setSSLParameters trở lại |
| “Supported protocols là secure defaults.” | Supported có thể bị disabled hoặc không hợp policy |
| “Bật hết supported ciphers sẽ sửa mọi lỗi.” | Có thể mở thuật toán không nên dùng |
| “Hostname verification tự bật trên raw SSLSocket.” | Phải cấu hình HTTPS endpoint algorithm/trust đúng |
| “SNI chỉ là routing, không ảnh hưởng name check.” | SunJSSE có thể dùng SNI trong endpoint validation |
| “Tùy ý đặt peerHost và SNI khác nhau.” | Có thể kiểm sai identity logic |
| “ALPN h2 tức đã có HTTP/2.” | Chỉ negotiate protocol name |
| “setNeedClientAuth ở client để kiểm server.” | NeedClientAuth dành cho server-side mTLS |
| “setWantClientAuth và setNeedClientAuth cùng true.” | Setter này xóa cờ kia |
| “SSLEngine tự tạo network socket.” | Caller vận chuyển TLS records |
| “SSLEngine không cần delegated tasks.” | NEED_TASK phải được xử lý |
| “NEED_UNWRAP_AGAIN là error.” | Đây là handshake status cần được drive |
| “BUFFER_UNDERFLOW tức invalid TLS.” | Thường input chưa đủ |
| “BUFFER_OVERFLOW tức cipher lỗi.” | Thường output ByteBuffer quá nhỏ |
| “Đóng TCP tương đương TLS close_notify.” | Đóng TLS engine có state/records riêng |
| “TrustManager bỏ hết kiểm cert thì test thực tế.” | Mất tính đúng của TLS peer authentication |
| “Keystore self-signed demo dùng được trên production.” | Chỉ là ephemeral test trust |
| “Cipher đầu tiên trong mảng chắc chắn negotiated.” | Đọc SSLSession sau handshake |
| “TLS client cert đủ thay authorization.” | Vẫn cần identity/role/tenant checks |
| “Đổi SSLParameters là xoay TLS session đã tồn tại.” | Phải quản lý context và connection lifecycle |

## 16. Câu hỏi tự kiểm tra

1. SSLParameters thuộc package nào? — `javax.net.ssl`.
2. Gắn SSLParameters lên SSLSocket bằng gì? — `setSSLParameters`.
3. Gắn lên SSLEngine bằng gì? — `setSSLParameters`.
4. Có cần gọi setSSLParameters sau khi sửa getSSLParameters? — Có.
5. Nên chỉnh trước khi nào? — Trước handshake/đọc ghi đầu tiên.
6. Modern TLS versions? — TLSv1.3 và TLSv1.2 theo policy.
7. Supported có tương đương enabled không? — Không.
8. TLS 1.0/1.1 nên bật không? — Không.
9. HTTPS hostname verification bật bằng gì? — `setEndpointIdentificationAlgorithm("HTTPS")`.
10. Nó có thay TrustManager không? — Không.
11. SNI dùng làm gì? — Gửi tên server mong muốn trong ClientHello.
12. Vì sao peerHost/SNI phải khớp? — JSSE có thể dùng SNI để xác minh identity.
13. ALPN cấu hình ở đâu? — `setApplicationProtocols`.
14. Đọc ALPN thực tế ở đâu? — `getApplicationProtocol` sau handshake.
15. Đọc TLS version sau handshake? — `SSLSession.getProtocol`.
16. Đọc cipher suite thực tế? — `SSLSession.getCipherSuite`.
17. setNeedClientAuth và setWantClientAuth khác nhau? — Bắt buộc/tùy chọn client cert.
18. Hai flags need và want có cùng true được không? — Không theo setters.
19. SSLEngine client mode đặt khi nào? — Trước beginHandshake/wrap/unwrap.
20. Client engine nên tạo với peerHost không? — Có khi cần đúng peer identity.
21. SSLEngine tự làm TCP I/O không? — Không.
22. NEED_WRAP cần làm gì? — Gọi wrap và gửi TLS bytes.
23. NEED_UNWRAP cần làm gì? — Nhận bytes, gọi unwrap.
24. NEED_TASK cần làm gì? — Chạy các delegated tasks.
25. BUFFER_UNDERFLOW thường xử lý thế nào? — Đọc thêm dữ liệu.
26. BUFFER_OVERFLOW thường xử lý thế nào? — Tăng output buffer.
27. TLS engine đóng sạch thế nào? — closeOutbound và gửi close_notify theo contract.
28. mTLS đã pass có tự cho phép admin không? — Không.
29. Test config có chứng minh handshake không? — Không.
30. Test loopback chứng minh gì? — TLS handshake, trust+hostname, ALPN và data exchange.
31. CN test có thay SAN verification không? — Không.
32. Sao wrong-host test cần đổi cả SNI? — Để kiểm đúng expected hostname theo JSSE.
33. Đổi certificate file có tự cập nhật SSLContext đang chạy không? — Không.
34. TLSv1.3 có renegotiation kiểu TLSv1.2 không? — Không.
35. 0-RTT có replay risk không? — Có, nếu protocol/provider sử dụng.
36. Hệ thống thật nên kiểm thêm gì? — Truststore, authz, timeouts, credentials rotation và negative TLS tests.

## 17. Tài liệu chính thức còn áp dụng

- [Java SE 25 — SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): protocols, ciphers, endpoint identification, SNI, ALPN, mTLS.
- [Java SE 25 — SSLSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSocket.html): setSSLParameters/startHandshake/getSession.
- [Java SE 25 — SSLEngine](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html): transport-independent TLS, wrap/unwrap, tasks, close.
- [Java SE 25 — SSLEngineResult](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): Status/HandshakeStatus/bytesConsumed.
- [Java SE 25 — SSLContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLContext.html): defaults, supported params, createSSLEngine.
- [Java SE 25 — SSLServerSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): server-side TLS listener.
- [Java SE 25 — SNIHostName](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SNIHostName.html): SNI host names.
- [Java SE 25 — SSLSession](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated protocol/cipher and buffer sizing.
- [Java SE 25 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): private-key credentials.
- [Java SE 25 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): certificate trust anchors.
- [Oracle Java SE 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): application of SSLParameters, TLS/DTLS, SNI/hostname verification, ALPN, disabled algorithms.
- [RFC 9325 — TLS/DTLS Security Recommendations](https://www.rfc-editor.org/rfc/rfc9325): TLS 1.3 priority, TLS 1.2 compatibility, disabled legacy versions.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake và TLS record protocol.
- [RFC 6066 — TLS SNI Extension](https://www.rfc-editor.org/rfc/rfc6066): server name indication.
- [RFC 7301 — TLS ALPN Extension](https://www.rfc-editor.org/rfc/rfc7301): application protocol negotiation.
- [Java SE 25 — keytool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html): tạo PKCS12 test certificate với SAN.

**Kết luận:** để áp dụng cấu hình TLS trên Java 17+, lấy `SSLParameters`, điều chỉnh chính sách TLS/hostname/SNI/ALPN và **gọi `setSSLParameters` trước handshake** trên đúng `SSLSocket` hoặc `SSLEngine`. Trong client mode phải xác minh server certificate và hostname bằng TrustManager + endpoint identification; trong server mode, `needClientAuth`/`wantClientAuth` điều khiển mTLS đúng vai trò. `SSLEngine` còn cần state machine wrap/unwrap/ByteBuffer/delegated tasks do caller điều phối. Chỉ tin kết quả TLS thật sau handshake (SSLSession/ALPN), không coi các cờ cấu hình hay một chứng thư self-signed test là bằng chứng security production.