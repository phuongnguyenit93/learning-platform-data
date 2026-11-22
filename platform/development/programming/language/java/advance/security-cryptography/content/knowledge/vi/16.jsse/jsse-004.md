# 16.4 SSLSocket, SSLServerSocket và điều khiển thời điểm handshake

## Mục tiêu và bối cảnh

Bài học thuộc **16. JSSE** của Java Advance – security-cryptography. Sau khi hoàn thành, bạn có thể:

- Phân biệt `SSLContext`, `SSLSocketFactory`, `SSLServerSocketFactory`, `SSLServerSocket`, `SSLSocket`, `SSLParameters` và `SSLSession`.
- Hiểu trình tự **TCP connect/accept → cấu hình TLS → handshake → xác thực danh tính → đọc/ghi application data → close**.
- Giải thích sự khác nhau giữa **gọi `startHandshake()` tường minh** và **handshake tự động** khi sử dụng I/O của `SSLSocket`.
- Chỉ ra API có thể **kích hoạt handshake ngoài ý muốn** (đặc biệt `getSession()`), và hiểu ý nghĩa/giới hạn của `getHandshakeSession()` và `HandshakeCompletedListener`.
- Cấu hình phiên bản TLS, cipher suites, endpoint identification, mTLS, SNI/ALPN và timeout **trước khi handshake bắt đầu**.
- Chạy ví dụ độc lập với **Java 17+**, `keytool` và hai `SSLContext`: server/client trên loopback `127.0.0.1`, có xác minh certificate bằng truststore; so sánh explicit handshake và implicit handshake với một lần trao đổi dữ liệu.
- Chẩn đoán lỗi `SSLHandshakeException` ở đúng thời điểm, tránh tự tạo trust manager không kiểm tra certificate hoặc lặp `startHandshake()` để cố “renegotiate” TLS 1.3.

**Thông điệp quan trọng:** Một kết nối TCP đã `connect()/accept()` **chưa đồng nghĩa** có kênh TLS được xác thực. Và `SSLServerSocket` là listener, **không phải** kênh ứng dụng của một client. Chỉ khi handshake thành công theo chính sách trust/identity, cộng thêm authorization ở tầng nghiệp vụ, ứng dụng mới nên xử lý request có quyền.

## 1. Các thành phần JSSE phối hợp với nhau

JSSE (*Java Secure Socket Extension*) cung cấp TLS trong JVM. Các class sau không có cùng trách nhiệm:

| Thành phần | Vai trò | Ví dụ API |
| --- | --- | --- |
| `SSLContext` | Tập hợp key manager, trust manager và nguồn ngẫu nhiên; cung cấp socket factories | `SSLContext.getInstance("TLS")`, `init(...)` |
| `KeyManagerFactory` | Chọn private key và certificate chain để **chứng minh danh tính phía mình** | `init(keyStore, keyPassword)` |
| `TrustManagerFactory` | Tạo kiểm tra trust anchor/chain cho certificate từ **peer** | `init(trustStore)` |
| `SSLSocketFactory` | Tạo kết nối TLS phía client hoặc bọc một socket đã connect | `createSocket(host, port)` |
| `SSLServerSocketFactory` | Tạo listener TLS ở server | `createServerSocket(port, backlog, bindAddress)` |
| `SSLServerSocket` | Bind/listen/accept; thiết lập TLS defaults cho các kết nối nhận | `accept`, `setEnabledProtocols`, `setNeedClientAuth` |
| `SSLSocket` | Một kết nối TLS cụ thể; handshake, stream I/O và session | `startHandshake`, `getInputStream`, `getOutputStream` |
| `SSLParameters` | Cấu hình SSL/TLS liên quan socket, như endpoint identification, ALPN và SNI | `setEndpointIdentificationAlgorithm`, `setApplicationProtocols` |
| `SSLSession` | Thông tin phiên TLS, ví dụ protocol/cipher suite/peer cert | `getProtocol`, `getCipherSuite`, `getPeerCertificates` |
| `HandshakeCompletedListener` | Nhận sự kiện hoàn tất handshake của `SSLSocket` | `addHandshakeCompletedListener` |

**Sơ đồ:**

```text
        CLIENT                                      SERVER
  truststore -> TrustManagerFactory         keystore -> KeyManagerFactory
                    |                                      |
               SSLContext                              SSLContext
                    |                                      |
            SSLSocketFactory                    SSLServerSocketFactory
                    |                                      |
               SSLSocket  -------- TCP -------->  SSLServerSocket
                    |                                 accept()
                    |                                      |
                    |                                 SSLSocket (peer)
                    |                                      |
          cấu hình trước TLS                       cấu hình trước TLS
                    +---------- TLS handshake -----------+
                    |                                      |
             kiểm tra identity                      client-cert nếu mTLS
                    |                                      |
                    +==== encrypted application bytes ====+
```

Đầu client có thể chỉ cần **trust manager** để kiểm tra server certificate; server cần **key manager** chứa server private key và chain để trình diện. Với mTLS, client cũng phải có key manager/client certificate và server phải có trust manager để đánh giá client cert.

`SSLContext.init(...)` thành công **chưa làm một handshake nào**. `SSLServerSocket.accept()` nhận một kết nối tới listener và trả một `SSLSocket`; handshake TLS có thể chưa được thực hiện. `SSLSession` chỉ nên được dùng để quan sát session sau khi handshake thành công; việc gọi `getSession()` sớm tự nó có thể bắt đầu handshake.

## 2. Phân biệt thời điểm TCP và TLS

| Giai đoạn | Điều chắc chắn | Điều chưa chắc chắn |
| --- | --- | --- |
| Tạo `SSLContext` | Có cấu hình cryptographic services được chọn | Chưa có peer/kết nối |
| Tạo `SSLServerSocket` | Server lắng nghe trên port | Chưa có client TLS authenticated |
| Client `SSLSocketFactory.createSocket(...)` | Socket được tạo, thông thường TCP đã connect | Chưa chắc handshake TLS đã xảy ra |
| Server `SSLServerSocket.accept()` | Đã nhận TCP connection | Chưa chắc certificate/client identity được xác minh |
| Cấu hình `setEnabledProtocols(...)` | Giới hạn TLS versions ứng dụng cho phép | Chưa biết negotiated version thực |
| `startHandshake()` hoặc I/O kích hoạt handshake | JSSE thực thi negotiation, key establishment và xác thực phù hợp | Có thể thất bại ngay tại đây |
| Handshake trả thành công | Có TLS channel được thiết lập theo chính sách JSSE đang dùng | Không tự cho client quyền truy cập API |
| Đọc `SSLSession` sau handshake | Có thể biết negotiated protocol/cipher | Không tự chứng minh resource authorization |

Trong TLS server authentication thông thường, client kiểm tra chain của server tới **trust anchor** đã tin từ trước và **hostname/IP đích** phải khớp certificate SAN. **Không coi** certificate hợp lệ dưới một CA bất kỳ là đúng server nếu SAN không khớp. Phía server cũng không thể suy ra danh tính người dùng chỉ từ việc một TCP connection đã được accept.

TLS là một **byte stream được bảo vệ**, không phải một hệ thống auth/authorization đầy đủ. Tầng ứng dụng vẫn phải phân tích request, kiểm tra quyền theo resource/tenant/user, chống replay nếu protocol yêu cầu và quản lý lifecycle.

## 3. Explicit handshake với `SSLSocket.startHandshake()`

Có thể yêu cầu handshake ở một điểm rõ ràng sau khi tạo và cấu hình socket:

```java
SSLSocket socket = (SSLSocket) sslFactory.createSocket(host, port);
socket.setEnabledProtocols(new String[] {"TLSv1.3"});
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();  // TLS checkpoint: thành công hoặc báo lỗi.
SSLSession session = socket.getSession();
```

Đoạn trên **chỉ là snippet**, chưa phải chương trình độc lập: cần `sslFactory` được tạo từ `SSLContext` với trust manager đúng, `host/port`, imports `javax.net.ssl.*`, xử lý exceptions và đóng socket trong try-with-resources.

**Lợi ích của `startHandshake()` tường minh:**

- Lỗi certificate/trust, TLS protocol mismatch hoặc cipher negotiation thường xuất hiện ở **chính `startHandshake()`**, thay vì ở lần `write/read` đầu tiên.
- Ứng dụng có thể chỉ gửi dữ liệu nhạy cảm **sau khi** TLS đã được thiết lập và policy bổ sung được kiểm tra.
- Rõ ràng về logging, telemetry và timeout cho giai đoạn TLS, tách khỏi application request.
- Không vô tình làm thay đổi thứ tự handshake bằng việc gọi `getSession()` trước khi cấu hình endpoint identity.

Tại server, nhận `SSLSocket` từ listener và chủ động handshake:

```java
try (SSLSocket peer = (SSLSocket) serverSocket.accept()) {
    peer.setSoTimeout(10_000);
    peer.startHandshake();
    // Chỉ bắt đầu xử lý yêu cầu sau khi handshake thành công.
}
```

Đây cũng là **snippet**, giả định `serverSocket` là `SSLServerSocket` đã cấu hình, và chỉ minh họa điểm checkpoint. `peer.startHandshake()` có thể block trong khi chờ client; server cần giới hạn thời gian và tài nguyên. Không thực hiện blocking handshake vô hạn trên thread nhận kết nối duy nhất của server production.

**Lưu ý:** Một lời gọi `startHandshake()` chỉ “bắt đầu handshake” theo contract trên socket TLS; để xác thực đúng server, client vẫn phải có **truststore/trust manager và endpoint identification**. Nếu ứng dụng cấu hình “trust all” thì handshake có thể thành công mà không bảo đảm danh tính đúng.

## 4. Implicit handshake: lần I/O đầu tiên cũng có thể là handshake

`SSLSocket` thực hiện **initial handshake tự động** khi một thao tác cần kết nối TLS có thể sử dụng. Ví dụ:

```java
try (SSLSocket socket = (SSLSocket) sslFactory.createSocket(host, port)) {
    // Phải cấu hình protocol, hostname/trust, timeout từ trước.
    socket.getOutputStream().write(requestBytes); // Handshake nếu cần.
    socket.getOutputStream().flush();
    int firstResponseByte = socket.getInputStream().read();
}
```

Snippet trên chưa độc lập: `sslFactory`, `host/port`, `requestBytes` phải được cung cấp; thiếu cấu hình trust/endpoint là một lỗi bảo mật. Nếu chưa có handshake, thao tác `write`/`read` sẽ kích hoạt nó, vì **application bytes không thể được truyền dưới kênh TLS đúng khi chưa thiết lập khóa phiên**.

**Sự khác biệt quan trọng nhất là vị trí lỗi:**

| Flow | Điểm bắt đầu TLS | Lỗi TLS có thể được thấy ở đâu? |
| --- | --- | --- |
| Explicit | `socket.startHandshake()` | Ngay tại `startHandshake()` |
| Implicit | `getOutputStream().write(...)` hoặc `getInputStream().read()` | **Trong I/O** thay vì trong một lời gọi handshake rõ ràng |
| Đọc session sớm | `socket.getSession()` | `getSession()` có thể tự kích hoạt initial handshake |
| Server explicit | `peer.startHandshake()` sau `accept` | Trong handshake trên accepted socket |
| Server implicit | `peer.getInputStream().read()` | Trong lần I/O trên accepted socket |

Lấy `getInputStream()`/`getOutputStream()` không nên bị coi là một checkpoint xác thực trong mọi provider; khi **thực sự đọc/ghi** thì JSSE phải bảo vệ dữ liệu ứng dụng và có thể khởi handshake. Nếu muốn một điểm rõ ràng trước request, **chủ động gọi `startHandshake()`**.

### Bẫy `getSession()` và `getHandshakeSession()`

`SSLSocket.getSession()` có thể tự khởi tạo handshake nếu initial handshake chưa bắt đầu. **Không** dùng nó để “kiểm tra xem đã handshake chưa” trước khi thiết lập `SSLParameters`. Một getter có tác dụng phụ có thể khiến certificate được chấp nhận mà chưa bật endpoint identification đúng.

`getHandshakeSession()` dùng trong một **handshake đang diễn ra** (khi có handshake session) và có thể trả `null` khi không có handshake đang hoạt động. Nhưng `null` **không chứng minh** socket chưa bao giờ handshake: sau khi handshake kết thúc, cũng có thể không còn handshake session.

### Hai timeline

```text
EXPLICIT                                  IMPLICIT
createSocket()                            createSocket()
setEnabledProtocols(...)                  setEnabledProtocols(...)
set SSLParameters (HTTPS identity)         set SSLParameters (HTTPS identity)
startHandshake() ---------------- TLS     output.write(42) -------- TLS
  | success or SSLHandshakeException         | success or SSLHandshakeException
output.write(42)                           app byte 42 đi sau handshake
input.read()                               input.read()
getSession()                               getSession()
```

Cả hai có thể đạt cùng negotiated TLS version và trust policy. **Không phải implicit kém bảo mật hơn chỉ vì không gọi `startHandshake()`**; rủi ro phát sinh khi code không biết điểm handshake thật và **không xử lý lỗi hoặc cấu hình quá muộn**.

## 5. `SSLServerSocket`: điều khiển phía server

Các bước cho một server JSSE trực tiếp:

1. Tải keystore chứa private key và chain của server, khởi tạo `KeyManagerFactory` và `SSLContext`.
2. Tạo listener bằng `SSLServerSocketFactory.createServerSocket(...)`, có địa chỉ/port và backlog thích hợp.
3. Cài protocol/cipher allowlist, `SSLParameters` và chính sách client certificate **trên listener trước khi accept**.
4. `accept()` để nhận một `SSLSocket` cho **từng kết nối riêng biệt**.
5. Cài `setSoTimeout(...)` trên accepted socket, thêm listener/chỉnh policy cần thiết **trước handshake**.
6. Gọi `startHandshake()` hoặc để I/O đầu tiên kích hoạt.
7. Chỉ sau khi TLS thành công và ràng buộc danh tính/ủy quyền phù hợp mới xử lý application data.
8. Đóng socket kết nối khi xong; listener có thể tiếp tục accept connection khác.

`SSLServerSocket` không phải stream của ứng dụng. Các method `getInputStream` và `getOutputStream` nằm trên **accepted `SSLSocket`**, không nằm trên listener.

### mTLS: `setNeedClientAuth` và `setWantClientAuth`

- `setNeedClientAuth(true)`: server **yêu cầu** client certificate. Client phải có certificate/private key thích hợp và server phải có trust manager xác minh certificate đó; nếu không thỏa, handshake không thành công.
- `setWantClientAuth(true)`: server muốn nhận certificate nhưng có thể tiếp tục khi client không cung cấp; **không tự coi mọi client đã xác thực**.
- Nếu client certificate có thật và được trust, **vẫn cần ánh xạ** certificate identity tới user/service/tenant/role và kiểm tra quyền nghiệp vụ.

Hãy thiết lập chính sách client-auth **trước khi handshake**. Không “bật mTLS” sau khi connection đã được thiết lập mà mong client lập tức cung cấp chứng chỉ như một lần đăng nhập mới.

### TLS server không phải một thread duy nhất

`accept()` có thể block, handshake cũng có thể block khi chờ peer. Production cần accept loop, concurrency giới hạn, timeout, rate limiting, quota và khả năng shutdown. Một client có thể gửi TCP SYN/connect nhưng cố tình trì hoãn TLS handshake. Không để hàng nghìn socket chờ vô hạn và tiêu hết file descriptors/threads.

## 6. Những cấu hình phải đặt trước khi bắt đầu TLS

| Cấu hình | Thời điểm phù hợp | Ý nghĩa |
| --- | --- | --- |
| `SSLContext.init(keyManagers, trustManagers, random)` | Trước khi lấy socket factory | Nguồn private key/certificate và trust anchors |
| `SSLSocket.setUseClientMode(true/false)` | Trước handshake | Vai trò của đầu TLS; thay sau khi TLS bắt đầu có thể không hợp lệ |
| `SSLServerSocket.setEnabledProtocols(...)` | Trước accept/handshake của các kết nối | Allowed versions của peer sockets |
| `SSLSocket.setEnabledProtocols(...)` | Trước handshake trên socket | Allowed TLS versions; **không phải negotiated version** |
| `setEnabledCipherSuites(...)` | Trước handshake | Cipher suites được phép; hỗ trợ tùy provider |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Client trước handshake | Yêu cầu kiểm tra hostname/IP đích dựa trên certificate |
| `SSLParameters.setServerNames(...)` | Client trước handshake nếu cần | SNI giúp chọn virtual host/certificate |
| `SSLParameters.setApplicationProtocols(...)` | Trước handshake nếu có ALPN | Danh sách application protocols được phép |
| `setNeedClientAuth(...)`/`setWantClientAuth(...)` | Server trước handshake | Chính sách client certificate |
| `addHandshakeCompletedListener(...)` | Trước handshake muốn quan sát | Callback khi handshake hoàn tất |

Java 17 hỗ trợ TLS 1.3 trong provider chuẩn phù hợp. Dùng `SSLContext.getInstance("TLS")` có thể cho phép nhiều phiên bản tùy provider/policy, còn `setEnabledProtocols(new String[]{"TLSv1.3"})` giới hạn socket. **Phải kiểm tra phiên bản thực sự negotiated** sau handshake qua `SSLSession.getProtocol()`. Không bật TLS 1.0/1.1 hay cipher suites yếu chỉ để tránh lỗi interoperability.

### Endpoint identification là một phần khác trust chain

Client cần **cả** đường tin cậy tới trust anchor **và** kiểm tra danh tính endpoint. Ví dụ connect tới `127.0.0.1` thì certificate lab bên dưới có **IP SAN 127.0.0.1**. `CN=localhost` riêng lẻ không thay thế IP SAN khi host đích là IP literal.

SNI có thể giúp server chọn certificate nhưng **không thay hostname verification**. Với IP literal trong lab, demo không dựa vào SNI; với DNS virtual hosts, chính sách SNI, SAN và trust manager phải phối hợp.

## 7. Lab Java 17: hai chế độ handshake có chứng thư được trust

Mục tiêu là tạo một ví dụ **thực sự chạy được** trên cùng máy, không truy cập Internet và không dùng trust-all.

### 7.1 Chuẩn bị keystore/truststore

Tạo certificate **tự ký dành riêng cho test** có `SAN=dns:localhost,ip:127.0.0.1`. Import public certificate vào truststore của client. Đây là **trust được cấp phát chủ động ngoài kết nối mạng**, khác hoàn toàn việc tự tin bất kỳ certificate nào server gửi.

Mở PowerShell có `java`, `javac` và `keytool.exe` từ JDK 17+ trên `PATH`. Chạy toàn bộ script dưới đây. Chỉ dùng thư mục `%TEMP%\jsse-handshake-lab`, **không sửa `cacerts` hoặc truststore hệ điều hành**:

```powershell
$ErrorActionPreference = 'Continue'
$qa = Join-Path $env:TEMP 'jsse-handshake-lab'
New-Item -ItemType Directory -Force -Path $qa | Out-Null
Set-Location $qa
$p = 'changeit'

function Run-Keytool([string[]]$arguments) {
    $out = & keytool.exe @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("keytool failed: " + ($arguments -join ' ') + ' => ' + ($out -join ' '))
    }
}

if (Test-Path -LiteralPath 'server.p12') {
    Remove-Item -LiteralPath 'server.p12' -Force
}
if (Test-Path -LiteralPath 'trust.p12') {
    Remove-Item -LiteralPath 'trust.p12' -Force
}

Run-Keytool @("-genkeypair","-alias","localhost",
    "-keyalg","RSA","-keysize","2048",
    "-sigalg","SHA256withRSA","-validity","30",
    "-dname","CN=localhost,O=TLS Training",
    "-ext","SAN=dns:localhost,ip:127.0.0.1",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature,keyEncipherment",
    "-storetype","PKCS12","-keystore","server.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Run-Keytool @("-exportcert","-alias","localhost",
    "-rfc","-file","server.pem",
    "-keystore","server.p12","-storepass",$p)

Run-Keytool @("-importcert","-alias","localhost",
    "-file","server.pem",
    "-keystore","trust.p12","-storetype","PKCS12",
    "-storepass",$p,"-noprompt")

Write-Output "Local TLS lab stores ready"
```

**Stdout cuối trên môi trường kiểm thử:**

```text
Local TLS lab stores ready
```

Ba tệp:

- `server.p12`: keystore có **private key + certificate của server**; chỉ phía server cần.
- `server.pem`: **public certificate** đã export; có thể phân phối nhưng nguồn cần được xác thực khi dùng trong thực tế.
- `trust.p12`: truststore phía client chứa certificate lab được **tin cậy có chủ đích**.

`changeit` là mật khẩu cố định **chỉ dùng cho lab**. Không đưa `server.p12` vào git, không dùng certificate này trong production, không tự tin file public certificate do attacker cung cấp. Với production, dùng CA/KMS/HSM, chính sách phát hành, renew/revoke và secure secret storage phù hợp.

**Ghi chú PowerShell:** Script chạy trong một thư mục **tạm riêng** và xóa các tệp `server.p12`/`trust.p12` trong chính thư mục lab khi tạo lại. Không đặt tệp cá nhân có cùng tên vào thư mục lab. Hãy giữ cú pháp PowerShell, không copy y nguyên vào Bash.

### 7.2 Chương trình `HandshakeTimingDemo.java`

Lưu source dưới đây trong **cùng thư mục** với `server.p12` và `trust.p12`. Dùng đúng tên file `HandshakeTimingDemo.java`:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public final class HandshakeTimingDemo {
    private static final String PASSWORD = "changeit"; // Local lab ONLY.
    private static final String TLS_VERSION = "TLSv1.3";
    private static final String HOST = "127.0.0.1";

    private record ServerResult(boolean received, boolean event,
                                String protocol) {}

    public static void main(String[] args) throws Exception {
        SSLContext server = serverContext("server.p12");
        SSLContext client = clientContext("trust.p12");
        runScenario("EXPLICIT", true, server, client);
        runScenario("IMPLICIT", false, server, client);
    }

    private static SSLContext serverContext(String keyStoreFile)
            throws Exception {
        KeyStore store = loadKeyStore(keyStoreFile);
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, PASSWORD.toCharArray());
        SSLContext context = SSLContext.getInstance(TLS_VERSION);
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    private static SSLContext clientContext(String trustStoreFile)
            throws Exception {
        KeyStore store = loadKeyStore(trustStoreFile);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store);
        SSLContext context = SSLContext.getInstance(TLS_VERSION);
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    private static KeyStore loadKeyStore(String file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            store.load(in, PASSWORD.toCharArray());
        }
        return store;
    }

    private static void runScenario(String label, boolean explicit,
                                    SSLContext serverContext,
                                    SSLContext clientContext) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 5, InetAddress.getByName(HOST))) {
            listener.setEnabledProtocols(new String[] {TLS_VERSION});

            Future<ServerResult> serverTask = executor.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(10000);
                    peer.setEnabledProtocols(new String[] {TLS_VERSION});
                    CountDownLatch event = new CountDownLatch(1);
                    peer.addHandshakeCompletedListener(done -> event.countDown());

                    if (explicit) {
                        peer.startHandshake();
                    }
                    int request = peer.getInputStream().read(); // Implicit if needed.
                    peer.getOutputStream().write(43);
                    peer.getOutputStream().flush();
                    boolean fired = event.await(2, TimeUnit.SECONDS);
                    return new ServerResult(request == 42, fired,
                            peer.getSession().getProtocol());
                }
            });

            try (SSLSocket socket = (SSLSocket)
                    clientContext.getSocketFactory().createSocket(
                            HOST, listener.getLocalPort())) {
                socket.setSoTimeout(10000);
                socket.setEnabledProtocols(new String[] {TLS_VERSION});
                SSLParameters parameters = socket.getSSLParameters();
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
                socket.setSSLParameters(parameters);
                CountDownLatch event = new CountDownLatch(1);
                socket.addHandshakeCompletedListener(done -> event.countDown());

                if (explicit) {
                    socket.startHandshake();
                }
                socket.getOutputStream().write(42); // Implicit if needed.
                socket.getOutputStream().flush();
                int answer = socket.getInputStream().read();
                boolean clientEvent = event.await(2, TimeUnit.SECONDS);
                ServerResult serverResult = serverTask.get(15, TimeUnit.SECONDS);
                boolean versionOk = TLS_VERSION.equals(
                        socket.getSession().getProtocol())
                        && TLS_VERSION.equals(serverResult.protocol());
                System.out.println(label + " TLSv1.3: " + versionOk);
                System.out.println(label + " handshake listeners: "
                        + (clientEvent && serverResult.event()));
                System.out.println(label + " one-byte exchange: "
                        + (answer == 43 && serverResult.received()));
            }
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy trong PowerShell (vẫn đứng trong `jsse-handshake-lab`):

```powershell
javac --release 17 HandshakeTimingDemo.java
java -cp . HandshakeTimingDemo
```

**Stdout đã kiểm thử bằng JDK hỗ trợ TLSv1.3:**

```text
EXPLICIT TLSv1.3: true
EXPLICIT handshake listeners: true
EXPLICIT one-byte exchange: true
IMPLICIT TLSv1.3: true
IMPLICIT handshake listeners: true
IMPLICIT one-byte exchange: true
```

**Lưu ý về thời gian:** Chương trình dùng `setSoTimeout(10000)`, chờ callback tối đa **2 giây** và chờ server worker qua `Future.get(15,...)`; những giá trị này nhằm tránh **lab treo vô hạn**, không phải cam kết của API JSSE. Nếu máy quá tải, một phép thử có thể bị timeout trước khi sự kiện callback được xử lý; đó chưa chắc là lỗi thuật toán TLS.

### 7.3 Vì sao Java code thể hiện đúng hai mode?

**Server và client contexts khác nhau:** `serverContext` tải keystore, khởi tạo `KeyManagerFactory` để trình server certificate. `clientContext` tải truststore, khởi tạo `TrustManagerFactory` để xác minh certificate. Không sử dụng trust manager kiểu “return true”. Client bật `HTTPS endpoint identification` trước khi bắt đầu handshake, khớp với **IP SAN** của certificate lab.

**Chỉ loopback:** Listener bind `InetAddress.getByName("127.0.0.1")`, port `0` do OS cấp. Không expose một server chưa có authorization ra mạng ngoài. Port không cố định nên nhiều lượt chạy ít xung đột.

**Tính đồng thời:** `ExecutorService` chạy phần `accept/read/write` phía server; main thread là client. Nếu không tách, client và server có thể block nhau. `accept()` không tự xử lý application bytes; code sử dụng **accepted `SSLSocket`** trong lambda.

**Explicit:** cả hai phía gọi `startHandshake()` trước I/O. Nếu client không tin certificate server, lỗi thường xuất hiện ở điểm này (peer bên kia nhận TLS alert/lỗi tương ứng). Sau khi TLS hoàn tất, client gửi byte `42`, server trả `43`.

**Implicit:** không có lời gọi `startHandshake()`. Client bắt đầu `OutputStream.write(42)`, server đang chờ `InputStream.read()`; JSSE tự khởi initial handshake và bảo vệ bytes truyền đi. Kết quả một byte vẫn là `42/43` nhưng **địa điểm lỗi TLS có thể nằm trong `write/read`**.

**Listener:** `HandshakeCompletedListener` chỉ gọi `CountDownLatch.countDown()`. Callback có thể bất đồng bộ; code đợi event ngắn để kiểm thử. Đừng coi việc callback được kích hoạt là application authorization; cả hai đầu cần kiểm tra chính sách danh tính/role tùy use case.

**Protocol:** `SSLSession.getProtocol()` được đọc **sau** handshake/I/O. Chỉ khi đó mới xác nhận negotiated `TLSv1.3`; `setEnabledProtocols` trước đó là allowlist, không phải bằng chứng negotiation.

**Kiểm thử logic ứng dụng:** `answer == 43 && serverResult.received()` chứng tỏ hai đầu đã trao đổi byte mong đợi. Nó **không phải** một định dạng message production: TLS không cung cấp framing ứng dụng.

## 8. `startHandshake()` không phải công tắc renegotiation TLS 1.3

Phân biệt:

1. **Initial handshake** trên một `SSLSocket` mới.
2. **Session resumption** trên một **kết nối TLS mới**, có thể dùng session ticket/cache theo protocol và policy; dù resume vẫn có handshake của connection mới.
3. **Renegotiation** kiểu TLS cũ: **TLS 1.3 không hỗ trợ renegotiation theo kiểu TLS 1.2**. TLS 1.3 có những cơ chế khác như KeyUpdate, nhưng chúng không phải một lần `startHandshake()` để tự động đổi user/certificate hoặc làm lại full handshake.

**Không viết một workflow bảo mật dựa trên giả định gọi `startHandshake()` nhiều lần sẽ có phiên mới.** Hành vi lần gọi tiếp theo phụ thuộc TLS version/provider và có thể bị từ chối, không làm gì hoặc thực hiện một cơ chế khác. Nếu cần thiết lập một kết nối mới/identity mới, hãy thiết kế **kết nối TLS mới** và quy trình xác thực đúng.

`SSLSession.invalidate()` không chuyển một socket TLS đang hoạt động về trạng thái “chưa handshake”; nó liên quan khả năng reuse/cache của session. `getHandshakeSession()==null` cũng không là phép xác định “đã xác thực hay chưa”.

### TLS 1.3 early data và resumption

**0-RTT early data** trong TLS 1.3 có các điều kiện và nguy cơ replay riêng. Chương trình `SSLSocket` ở đây **không sử dụng 0-RTT**; không nhầm `OutputStream.write` trước một lời gọi `startHandshake()` với gửi 0-RTT. Với JSSE, gọi I/O có thể tự kích hoạt handshake thông thường trước khi truyền application data.

Không lấy `SSLSession` object làm login session nghiệp vụ. Authorization và chống replay ở ứng dụng cần token/role/nonce/sequence theo giao thức; không thể thay bằng số lần handshake callback đã bắn.

## 9. `HandshakeCompletedListener` có dùng để cấp quyền không?

**Không.** Listener chỉ thông báo về sự kiện handshake hoàn tất cho socket. Ví dụ tối giản (snippet):

```java
CountDownLatch latch = new CountDownLatch(1);
socket.addHandshakeCompletedListener(event -> latch.countDown());
socket.startHandshake();
```

Đây là snippet cần `socket` hợp lệ và `java.util.concurrent.CountDownLatch`; xử lý exceptions và thời hạn chờ trong code thật. **Không** giả định callback chạy đồng bộ trước dòng ngay sau `startHandshake()`, và đừng thực hiện network I/O, DB query hoặc blocking dài trong callback vì sẽ làm phức tạp concurrency/lifecycle.

Nếu dùng listener cho metrics, gắn **connection ID**, protocol/cipher và thời gian sự kiện. Với mTLS, `HandshakeCompletedEvent.getPeerCertificates()` có thể cung cấp peer chain khi được xác thực nhưng vẫn phải map identity tới authorization. Trong TLS server thông thường **không có client certificate**, vì vậy listener không phải bằng chứng user đã đăng nhập.

## 10. Khi handshake thất bại, exception xuất hiện ở đâu?

| Tình huống | Lớp lỗi/cách quan sát thường gặp | Điều tra |
| --- | --- | --- |
| Certificate server không nối tới trusted root | `SSLHandshakeException`, có thể có `CertPathValidatorException`/builder cause | Truststore, issuer, intermediates, key policy |
| Kết nối tới IP nhưng certificate chỉ có DNS SAN khác | `SSLHandshakeException`/certificate mismatch | Cấp đúng SAN, kiểm tra endpoint identity |
| Server yêu cầu client cert nhưng client không có | TLS alert/`SSLHandshakeException` ở một hoặc hai phía | `needClientAuth`, client key manager/cert, trust manager server |
| Không có TLS version/cipher suite chung | TLS negotiation failure | Allowlist versions/cipher, JDK/provider/policy |
| Client implicit và gửi request lần đầu | Exception TLS có thể phát sinh **tại `write` hoặc `read`** | Đừng chỉ catch quanh `startHandshake` |
| Server implicit chờ read | Handshake error có thể phát sinh **tại `read`** | Peer certificate nếu mTLS, protocol/trust, slow client |
| Peer không nói gì hoặc kết nối bị treo | `SocketTimeoutException`/timeout kết nối hoặc EOF tùy giai đoạn | Timeout/deadlines, firewall, load và resource quota |
| `getPeerCertificates` khi peer không được xác thực bằng cert | `SSLPeerUnverifiedException` | Cấu hình mTLS và vai trò TLS đúng |
| Handshake đã thành công, I/O về sau lỗi | `SSLException` hoặc IO exception khác | Không mặc định đó là lỗi initial TLS handshake |

`SSLHandshakeException` kế thừa `SSLException`. Lỗi TLS handshake có thể bị bọc trong error của thư viện HTTP/JDBC/network; xem `getCause()` một cách có kiểm soát. **Không tự sửa bằng cách đổi trust manager thành trust-all** hoặc tự import một root certificate chưa xác thực vào global `cacerts`.

**Cũng không được suy rằng mọi `SSLException` đều là lỗi certificate**. Có thể là TLS protocol alert, close/truncation, network, unsupported cipher hoặc lỗi tầng record sau khi kết nối đã established.

### Đọc debug theo ngữ cảnh

Có thể bật JSSE debug tạm ở môi trường test:

```powershell
java -Djavax.net.debug=ssl,handshake,trustmanager -cp . HandshakeTimingDemo
```

Output debug không cố định và có thể dài; logging có thể chứa certificate/metadata/chi tiết giao thức nên chỉ sử dụng theo quyền, không bật tràn lan trên production. Các thông tin cần ghi: connection ID, TCP connect/accept duration, TLS handshake duration, negotiated version/cipher, truststore version, expected identity, exception category và correlation ID — không ghi private keys, keystore password hay payload nhạy cảm.

## 11. Timeout, deadlock, I/O framing và quản lý tài nguyên

### Timeout handshake không bằng timeout TCP connect

`setSoTimeout(...)` đặt thời hạn cho **blocking read** trên socket và thường ảnh hưởng việc đọc TLS record trong handshake; nó không thay cho **TCP connect timeout** và không đảm bảo deadline tổng của request.

Ví dụ snippet khi cần connect deadline:

```java
Socket raw = new Socket();
raw.connect(new InetSocketAddress(host, port), 3_000);
SSLSocket tls = (SSLSocket)
        factory.createSocket(raw, host, port, true);
tls.setSoTimeout(10_000);
// Cấu hình SSLParameters/trust/endpoint identity trước khi handshake.
tls.startHandshake();
```

Đây là snippet, cần import `java.net.Socket`/`InetSocketAddress`, `factory/host/port` và quản lý đóng socket. `autoClose=true` khiến wrapper đóng raw socket theo contract khi TLS socket đóng. Production còn cần overall deadline, connection limits, cancellation và handling rõ cho timeout/partial I/O.

### Đừng để hai phía cùng chờ byte ứng dụng

Hai bên cùng `read()` trước khi bên nào gửi application data có thể deadlock **dù TLS đã được thiết lập**:

```text
CLIENT                         SERVER
read()  -- waiting             read() -- waiting
   (không ai gửi dữ liệu ứng dụng trước)
```

Với giao thức request/response, quy định rõ **bên nào gửi trước**, framing, timeout và cách xử lý EOF. Demo chọn client gửi `42`, server đọc rồi đáp `43`, tránh waiting cycle.

### TLS là byte stream, không là message queue

Một `read` không được giả định trả đúng toàn bộ application message. Với message dài, cần xử lý partial reads, length prefix hoặc delimiter, giới hạn size, timeout, checksums nếu protocol yêu cầu và handling đóng kết nối. Không trộn raw `Socket.getInputStream` với stream của `SSLSocket` khi đã bọc TLS lên socket đó — raw reads có thể ăn vào byte handshake/encrypted records.

## 12. ALPN, SNI và client authentication

**SNI** giúp server chọn virtual host/certificate tương ứng DNS name mà client yêu cầu. Có thể cấu hình bằng `SSLParameters.setServerNames(...)` trước handshake, khi cần. SNI không chứng minh certificate đáng tin; client phải tiếp tục xác thực trust chain và SAN/hostname. Demo IP loopback không dựa vào SNI.

**ALPN** thương lượng **tên giao thức ứng dụng** như `h2` hay `http/1.1` trong TLS handshake. `SSLParameters.setApplicationProtocols(...)` đặt danh sách trước handshake và `SSLSocket.getApplicationProtocol()` đọc kết quả sau đó. Chọn `h2` không tự triển khai HTTP/2; ứng dụng cần stack framing/parser thực. Demo `42/43` không đặt ALPN vì không có HTTP.

**mTLS** yêu cầu server xác thực certificate phía client và ánh xạ certificate identity tới service/role/tenant. Bật `setNeedClientAuth(true)` trước handshake và cấu hình đầy đủ trust manager, CA/client cert. `setWantClientAuth(true)` chỉ yêu cầu tùy chọn: một client không có certificate có thể vẫn có kết nối TLS thành công. Đừng coi tất cả client của server đều authenticated chỉ vì server sử dụng `SSLServerSocket`.

## 13. Checklist triển khai thực tế

**Trước handshake:**

- [ ] Server có private key và certificate chain thích hợp qua `KeyManagerFactory`; client có trust manager với trust anchors đáng tin.
- [ ] Client bật **endpoint identification** đúng hostname/IP; certificate có SAN phù hợp.
- [ ] Protocol/cipher allowlist được đặt trước khi socket bắt đầu I/O/TLS; tránh cấu hình quá muộn.
- [ ] Role client/server và mTLS/SNI/ALPN (nếu cần) được chuẩn bị từ trước.
- [ ] Định nghĩa handshake timeouts, connect/read timeouts, deadline tổng và giới hạn connection/CPU.

**Tại handshake và I/O:**

- [ ] Biết code chọn explicit hay implicit; `getSession()` không được sử dụng như probe trạng thái không có side effect.
- [ ] Nếu explicit: chỉ xử lý data sau `startHandshake()` thành công và policy checks.
- [ ] Nếu implicit: `write/read` đầu tiên có thể ném lỗi handshake; không nuốt exception.
- [ ] Sau handshake, kiểm tra negotiated `SSLSession.getProtocol/getCipherSuite` và role/identity theo policy.
- [ ] `HandshakeCompletedListener` chỉ dùng để quan sát, không làm request handler hoặc quyết định quyền.
- [ ] Quản lý EOF, close, record/stream boundaries, backpressure và concurrency đúng.

**Vận hành và bảo mật:**

- [ ] Không dùng trust-all, không bỏ qua hostname verification, không nhập root chưa đáng tin vào truststore.
- [ ] Certificate rotation/renewal, truststore updates và root revocation có quy trình.
- [ ] Nếu mTLS, map client certificate identity tới authorization; không chỉ dựa vào sự tồn tại của certificate.
- [ ] Không giả định TLS 1.3 cho phép renegotiation cổ điển hoặc rằng `startHandshake()` gọi lặp sẽ re-authenticate.
- [ ] Có test valid, untrusted server cert, SAN mismatch, protocol mismatch, mTLS thiếu client cert, slow peer và timeout.
- [ ] Log có correlation/metrics theo quyền; không ghi private key, password, session secrets hay thông tin nhạy cảm.

## 14. Bài tập

1. Trên `HandshakeTimingDemo`, chỉ ra dòng nào tạo **listener**, dòng nào `accept()` và dòng nào kích hoạt explicit TLS handshake. `accept()` có đảm bảo client certificate đã được xác thực không?
2. Đổi `explicit=true` sang `false`. Vì sao app byte `42` không được gửi “trần” dù không có `startHandshake()` trong branch này?
3. Tạo truststore thứ hai **không chứa** certificate server. Chạy hai mode và ghi vị trí/cause của exception. Vì sao ở implicit lỗi có thể xuất hiện từ `OutputStream.write`?
4. Cấp một certificate server chỉ có `DNS:localhost` và bỏ `IP:127.0.0.1`, giữ client kết nối `127.0.0.1` với endpoint identification `HTTPS`. Dự đoán kết quả; đề xuất cách sửa đúng không phải trust-all.
5. Di chuyển `socket.getSession()` **lên trước** `setEndpointIdentificationAlgorithm("HTTPS")`. Phân tích vì sao gọi getter này để “xem session” có thể gây handshake quá sớm.
6. In negotiated `getCipherSuite()`/`getProtocol()` sau TLS. Tại sao giá trị này khác bản chất với `getEnabledProtocols()` trước handshake?
7. Bật `SSLServerSocket.setNeedClientAuth(true)` mà không thêm client cert/private key cho client trong lab. Ghi kết quả; cấu hình nào phải bổ sung để có mTLS thật?
8. Cho client và server một danh sách TLS protocol không giao nhau. Khi explicit/implicit, exception phát sinh ở thao tác nào?
9. Đổi client và server đều gọi `read()` chờ application byte trước khi write. Giải thích deadlock tầng ứng dụng và thiết kế framing/timeout đúng.
10. Thiết kế vòng đời TLS connection của server production: accept queue, handshake timeout, quota, listener callback, peer identity, authorization, request parsing và close.
11. So sánh initial handshake, TLS session resumption và renegotiation. Vì sao không thể dùng `startHandshake()` lặp lại trên TLS 1.3 như API xác thực user lần nữa?
12. Ghi một checklist quan sát `SSLHandshakeException` có thể bị bọc từ `getCause()` trong ứng dụng HTTP; cách phân biệt truststore, SAN mismatch và protocol version mà không hạ bảo mật.

## Tài liệu tham khảo

- [Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): `startHandshake`, `getSession`, `getHandshakeSession` và implicit handshake.
- [Java SE 17 — SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): listener, protocols và client authentication.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): SSLContext init, key/trust managers và socket factories.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, SNI, ALPN và SSL/TLS parameters.
- [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated protocol/cipher và peer.
- [Java SE 17 — HandshakeCompletedListener](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HandshakeCompletedListener.html): callback khi TLS handshake hoàn tất.
- [Java SE 17 — SSLSocketFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocketFactory.html) và [SSLServerSocketFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocketFactory.html): tạo client/server sockets.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): khởi tạo JSSE, debugging, TLS socket coding và trust.
- [Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): thao tác với keystore và truststore.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): initial handshake, session resumption, 0-RTT, key update và bảo mật.
