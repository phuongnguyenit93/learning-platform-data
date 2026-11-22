# Timeout đọc của SSLSocket và quản lý kết nối trong Java TLS

`SSLSocket` thuộc `javax.net.ssl`, kế thừa `java.net.Socket` và bổ sung TLS để mã hóa, bảo đảm toàn vẹn dữ liệu và xác thực peer. Khi viết ứng dụng mạng bằng Java, cần **phân biệt thời gian chờ TCP connect, TLS handshake, đọc application data, ghi dữ liệu, accept kết nối và deadline tổng của một request**. Chỉ gọi `setSoTimeout(3000)` không làm mọi thao tác của một TLS request hoàn thành trong ba giây.

Đây là bài Knowledge thuộc nhóm **Cấu hình TLS**, tập trung vào **timeout đọc của `SSLSocket` và quản lý kết nối**. Nội dung dựa trên API Java 17+ và Java SE 26, không dùng các mẫu TLS yếu hoặc legacy để khuyên dùng. Một ví dụ Java hoàn chỉnh dùng **TLS 1.3**, certificate/truststore thử nghiệm được tạo bằng `keytool`, **endpoint identification HTTPS**, socket loopback, **đọc quá hạn**, **handshake quá hạn**, close và reconnect; ví dụ đã được biên dịch `javac --release 17` và chạy trên OpenJDK 21 với **12/12 kiểm tra PASS**.

**Kết luận cần nhớ ngay:**

- `Socket.connect(endpoint, timeoutMs)` giới hạn **kết nối TCP**.
- `SSLSocket.setSoTimeout(ms)` giới hạn thời gian **một blocking read**; với JSSE có thể giới hạn các blocking reads trong TLS handshake khi đặt **trước** `startHandshake()`.
- `SSLServerSocket.setSoTimeout(ms)` giới hạn chờ **`accept()`**, không áp cho mọi reads của socket đã nhận.
- `SO_TIMEOUT` **không phải timeout của write**, **không phải deadline tổng**, không tự đóng socket sau một application read timeout.
- Khi TLS handshake thất bại, **không tái sử dụng connection**. Nếu application read timeout khiến protocol state không rõ, lựa chọn bảo thủ là đóng socket và tạo connection mới với retry policy.
- Raw `SSLSocket` client cần tin đúng certificate **và xác thực tên máy/IP trong certificate**; dùng `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` trước handshake, không viết trust-all `TrustManager`.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Hiểu `SSLContext`, `SSLSocketFactory`, `SSLSocket` và `SSLServerSocket` hoạt động ở những tầng nào.
2. Phân biệt TCP connect timeout, server accept timeout, handshake read timeout, application read timeout, idle timeout, write và total deadline.
3. Dùng `setSoTimeout`, `getSoTimeout`, `SocketTimeoutException` đúng contract, hiểu giá trị 0, dương và âm.
4. Tạo TLS socket từ `Socket.connect(endpoint, timeout)` rồi bọc bằng `SSLSocketFactory.createSocket(Socket, String, int, boolean)`.
5. Bật endpoint identification `HTTPS` trước `startHandshake()`; không nhầm truststore với hostname verification.
6. Xử lý read timeout khác EOF, `SSLHandshakeException`, `SSLException` và `SocketException`.
7. Biết giới hạn per-read không ngăn một peer gửi dữ liệu nhỏ liên tục để kéo dài tổng thời gian.
8. Thiết kế application framing, max response size, total request deadline, cancellation và retry.
9. Quản lý tài nguyên bằng try-with-resources, chủ sở hữu socket, executor, connection pool và `close()`.
10. Biết sự khác nhau giữa TCP `SO_KEEPALIVE` và application heartbeat, TLS session và user session.
11. Hiểu TLS 1.3 half-close, `close_notify` và cách kiểm tra response bị cắt.
12. Chạy ví dụ offline/localhost, giải thích 12 kiểm tra Java đã được chứng thực.

## 2. Một kết nối TLS có nhiều giai đoạn độc lập

```text
Client                         Server
  |                              |
  |-- DNS (nếu có hostname)      |
  |-- TCP connect -------------->|  Socket.connect(..., timeout)
  |<- TCP established -----------|
  |                              |
  |-- TLS ClientHello ---------->|
  |<- TLS handshake records -----|
  |-- TLS Finished ------------->|  startHandshake()
  |<- TLS Finished --------------|  setSoTimeout before handshake
  |                              |
  |-- application request ------>|
  |<- application response ------|  InputStream.read()
  |      read timeout           |
  |                              |
  |-- close / TLS shutdown ----->|  try-with-resources
```

Đây là sơ đồ khái niệm, không mô tả đầy đủ TLS record flow của mọi protocol/version. Nếu request có DNS lookup, proxy, TLS handshake, application framing và multiple reads, chỉ một `SO_TIMEOUT` không thể thay thế các deadline đó.

| Giai đoạn | API chủ yếu | Phạm vi giới hạn | Không giải quyết |
| --- | --- | --- | --- |
| DNS lookup | Resolver/runtime/network policy | Thời gian tìm địa chỉ theo cơ chế resolver. | `Socket.connect` không phải DNS deadline độc lập. |
| TCP connect | `Socket.connect(address, timeout)` | Thời gian TCP connect. | TLS handshake và reads. |
| TLS handshake | `SSLSocket.startHandshake()`, `setSoTimeout` trước handshake | Các blocking read waits trong handshake. | Deadline tổng của nhiều bước handshake/write. |
| Application read | `SSLSocket.setSoTimeout` | Một blocking `InputStream.read`. | Tổng thời gian nhận cả response. |
| TCP server accept | `SSLServerSocket.setSoTimeout` | `accept()` chờ client mới. | Reads trên accepted socket. |
| Application write | `getOutputStream().write/flush` | Không có `SSLSocket.setSoWriteTimeout` trong API chuẩn. | SO_TIMEOUT không khống chế write. |
| TCP liveness | `setKeepAlive(true)` | TCP probes theo OS. | Request deadline, TLS application idle. |
| Tổng request | Deadline/cancellation do ứng dụng tạo | Từ lúc bắt đầu đến lúc response hoàn tất. | Không tự phát sinh từ SO_TIMEOUT. |

**Điểm quan trọng:** hai giá trị 2.000 ms, một cho TCP connect và một cho TLS read, **không hợp thành** một deadline 2.000 ms tổng.

## 3. Vai trò của các API

`SSLContext` nắm configuration TLS provider cùng `KeyManager[]`, `TrustManager[]` và nguồn random. Nó tạo `SSLSocketFactory`/`SSLServerSocketFactory`, không tự là một connection.

`SSLSocketFactory` tạo client sockets hoặc bọc một `Socket` đã kết nối bằng TLS. Khi bọc:

```java
SSLSocket ssl = (SSLSocket) context.getSocketFactory()
        .createSocket(tcp, "127.0.0.1", port, true);
```

`true` nghĩa đóng layered TLS socket sẽ đóng underlying TCP socket được bọc. `SSLSocket` là connection để handshake, đọc/ghi dữ liệu và đóng.

`SSLServerSocket` listen/accept TLS-capable connections. Sau `accept()`, mỗi accepted connection là một `SSLSocket` riêng, phải có timeouts và resource owner riêng.

`SSLParameters` chứa TLS protocol list, ciphers, SNI và **endpoint identification algorithm**. Với raw SSLSocket client, phải cấu hình xác minh hostname/IP:

```java
SSLParameters params = ssl.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
ssl.setSSLParameters(params);
ssl.setSoTimeout(2000);
ssl.startHandshake();
```

Đây là **mảnh code** yêu cầu `ssl` đã được tạo bằng đúng trust material; phần đầy đủ ở mục 9. Không gọi `getSession()` hoặc đọc/ghi trước cấu hình, vì những operation đó có thể **tự kích hoạt handshake**. Cấu hình TLS sau handshake có thể là quá muộn.

### 3.1. getSession không phải user session

`SSLSession.getProtocol()`/`getCipherSuite()` cung cấp thông tin TLS negotiation. TLS session resumption có thể cho nhiều TLS connections sử dụng thông tin bắt tay trước đó, **không phải** phiên đăng nhập application. Đừng lấy `SSLSession.getId()` làm session token hoặc tenant identity.

### 3.2. TLS versions hiện hành

Java SE 26 chuẩn hóa `SSLContext` cho TLS 1.2 và TLS 1.3. Với hệ thống mới, ưu tiên **TLS 1.3**, có thể cho phép TLS 1.2 nếu cần interoperability và được security policy duyệt. Không bật SSLv3, TLS 1.0/1.1, NULL ciphers hoặc bypass certificate validation chỉ để làm test pass.

## 4. setSoTimeout(int): ý nghĩa theo Javadoc Socket

`SSLSocket` kế thừa `Socket.setSoTimeout(int)`. Trong Java SE 26:

| Giá trị | Hành vi |
| --- | --- |
| `timeout > 0` | Bật per-read timeout theo milliseconds; hết hạn ném `SocketTimeoutException`. |
| `timeout == 0` | **Vô hiệu** read timeout; read có thể chờ vô hạn nếu không có bytes, EOF hoặc I/O error. |
| `timeout < 0` | Ném `IllegalArgumentException`. |

Phải đặt timeout **trước blocking operation** để nó có hiệu lực theo contract. `getSoTimeout()` đọc giá trị hiện tại.

```java
ssl.setSoTimeout(1500);
try {
    int first = ssl.getInputStream().read();
    if (first == -1) {
        // EOF: peer đã đóng stream. Không phải timeout.
    } else {
        // Nhận được một byte application data.
    }
} catch (SocketTimeoutException ex) {
    // Không có data kịp per-read deadline.
}
```

Mảnh code chưa bao gồm setup/cleanup và không tự chạy. `SocketTimeoutException` là một `IOException`, nhưng **không tương đương** mọi `IOException`. Không tự retry toàn bộ request khi mới thấy exception.

### 4.1. Socket có thể vẫn mở sau application read timeout

Theo `Socket` Javadoc, sau `SocketTimeoutException` từ read, socket **vẫn có thể hợp lệ**. Demo ở mục 9 kiểm tra `timeoutDoesNotAutoClose=PASS` trên OpenJDK 21. Nhưng đó **không phải cam kết** rằng mọi TLS implementation và application protocol vẫn có thể reuse connection an toàn:

- TLS internal state có thể có khác biệt theo provider.
- Response có thể đang nhận một phần.
- Server có thể đang xử lý lệnh có side effects.
- Một byte stream không cho biết phần dữ liệu nào là một full message nếu thiếu framing.

Nếu tình trạng protocol không rõ, **đóng socket và reconnect**, kiểm tra idempotency trước khi retry. Với handshake failure, `SSLSocket` Javadoc nêu kết nối không còn dùng được.

### 4.2. SO_TIMEOUT không phải tổng request deadline

Một peer có thể gửi một byte mỗi 900 ms, còn client đặt `SO_TIMEOUT=1000 ms`. **Mỗi lần read** có thể nhận được byte, nhưng một message dài 1.000 bytes có thể kéo dài rất lâu.

`BufferedReader.readLine()` cũng có thể thực hiện nhiều reads để chờ ký tự newline; đừng coi `SO_TIMEOUT=1000` là cam kết đọc xong cả dòng trong 1 giây.

Thiết kế thêm:

- Deadline tổng tính bằng đồng hồ monotonic `System.nanoTime()`.
- Max bytes và max number of records.
- Framing (newline hoặc length prefix + kiểm tra đủ bytes).
- Per-read cap nhỏ hơn ngân sách còn lại.
- Cancellation/close socket khi hết total deadline.
- Retry budget/idempotency policy.

### 4.3. Một pattern kiểm tra ngân sách còn lại

```java
long totalNanos = java.time.Duration.ofSeconds(5).toNanos();
long start = System.nanoTime();
// ... thực hiện các bước trước ...
long remainingNanos = totalNanos - (System.nanoTime() - start);
if (remainingNanos <= 0) {
    // Đã hết deadline: cancel và đóng kết nối.
}
long millis = Math.max(1L,
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(remainingNanos));
int waitMs = (int) Math.min(millis, 1200L);
ssl.setSoTimeout(waitMs);
```

Đây là mảnh code **minh họa**, không phải một deadline manager hoàn chỉnh. Trước khi thực hiện read mới phải cập nhật remaining; không truyền `0` vào `setSoTimeout` để biểu thị “hết thời gian”, vì **0 có nghĩa vô hiệu timeout**. Nếu cần hard total deadline cả khi write bị block, tầng điều phối phải đóng socket/cancel task theo policy.

## 5. TCP connect timeout: cần thực hiện trước TLS

Sai lầm phổ biến:

```java
SSLSocket ssl = (SSLSocket) factory.createSocket(host, port);
ssl.setSoTimeout(3000);
```

Lời gọi `createSocket(host, port)` có thể **đã thực hiện TCP connect** trước khi code kịp đặt `setSoTimeout`. Để quản lý connect đúng:

```java
Socket tcp = new Socket();
tcp.connect(new InetSocketAddress("127.0.0.1", port), 2000);
SSLSocket ssl = (SSLSocket) sslContext.getSocketFactory()
        .createSocket(tcp, "127.0.0.1", port, true);
ssl.setSoTimeout(2000);
ssl.startHandshake();
```

Đây chỉ là mảnh code, **chưa có cleanup nếu exception xảy ra giữa chừng**. Chương trình đầy đủ ở mục 9 thể hiện cách bọc TCP socket và cleanup. Trong production cần đóng **cả layered socket nếu một bước cấu hình sau createSocket thất bại**.

Khi dùng hostname thay IP, DNS lookup có thể có thời gian riêng; connect timeout không phải DNS timeout toàn cục. Không suy đoán connect thành công nghĩa TLS handshake đã qua certificate verification.

### 5.1. Vì sao có hai con số 2.000 ms?

`tcp.connect(..., 2000)` áp cho **TCP**. `ssl.setSoTimeout(2000)` áp cho **blocking read** (kể cả handshake reads ở JSSE). Chúng bắt đầu ở các giai đoạn khác nhau, không cùng một ngân sách tổng.

### 5.2. Đặt timeout trên đúng socket

Sau khi có layered `SSLSocket`, cấu hình `ssl.setSoTimeout`. Đừng đặt timeout lên raw TCP socket rồi kỳ vọng mọi TLS provider tự kế thừa và áp dụng như nhau. Bảo đảm đúng object thực hiện blocking read có policy cần thiết.

## 6. TLS handshake và hostname verification

`SSLSocket.startHandshake()` đồng bộ trong initial handshake. TLS peer có thể:

- Không trả lời TCP accepted connection.
- Gửi handshake records chậm.
- Trả certificate không được trust.
- Trả certificate đúng CA nhưng **không match hostname**.
- Không có TLS protocol/cipher suite chung.
- Gửi TLS alert hoặc đóng bất thường.

### 6.1. Đặt cấu hình trước handshake

```java
ssl.setEnabledProtocols(new String[]{"TLSv1.3"});
SSLParameters params = ssl.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
ssl.setSSLParameters(params);
ssl.setSoTimeout(1500);
ssl.startHandshake();
```

Đây là mảnh code. `setSoTimeout(1500)` giúp giới hạn các **blocking reads trong handshake** trên provider được thử, nhưng không tạo deadline tổng độc lập cho mọi I/O trong handshake. Với yêu cầu hard handshake deadline, cần timeout/cancellation layer bên ngoài cùng resource cleanup.

### 6.2. Trust chain khác endpoint identity

`TrustManagerFactory` kiểm tra chứng chỉ theo trust material. Trong một raw `SSLSocket`, **đừng giả định** hostname verification được bật như các HTTP client HTTPS mức cao. `setEndpointIdentificationAlgorithm("HTTPS")` làm provider đối chiếu host/IP với certificate theo quy tắc endpoint identification trong TLS handshake.

Đối với IP literal, certificate test có **SAN=IP:127.0.0.1**; với DNS name `localhost` có SAN DNS tương ứng. Không tắt identity check hoặc sử dụng trust-all `X509TrustManager` để sửa lỗi khi certificate mismatch.

### 6.3. Handshake lỗi thì phải bỏ connection

Javadoc `SSLSocket` nêu initial handshake lỗi khiến connection bị đóng, không thể tiếp tục giao tiếp. Khi nhận `SSLHandshakeException`, `SSLException` hoặc timeout trong handshake:

1. Dừng trao đổi application data.
2. Close socket/underlying transport.
3. Phân loại lỗi trust, protocol, network và timeout.
4. Chỉ retry khi nguyên nhân có thể transient và retry policy cho phép.
5. Không downgrade TLS, tắt hostname verification hoặc trust tất cả certificates.

## 7. Server accept timeout và connection lifetime

`SSLServerSocket` có `setSoTimeout` kế thừa từ `ServerSocket`. Nó giới hạn `accept()`, **không giới hạn reads của socket được accept**.

```java
try (SSLServerSocket listener = createListener()) {
    listener.setSoTimeout(3000); // Chỉ giới hạn accept().
    try (SSLSocket peer = (SSLSocket) listener.accept()) {
        peer.setSoTimeout(2000); // Giới hạn handshake/read của peer.
        peer.startHandshake();
        // Đọc application request với framing, quotas và deadline.
    }
}
```

Đây là mảnh code yêu cầu helper `createListener` và exception handling. Nếu `accept()` timeout, listener thường **vẫn valid** và có thể tiếp tục nhận request. Nếu peer đã được accept nhưng không gửi TLS handshake, chính accepted socket/worker cần timeout.

### 7.1. Đừng chỉ đặt timeout cho listener

Một listener có thể nhận nhiều connections. Các accepted sockets có lifecycle riêng, và mỗi connection phải có:

- Handshake timeout và total handshake budget.
- Application read timeout, max size và idle timeout.
- Connection concurrent quota và bounded executor.
- Failure cleanup.
- TLS client authentication/authorization khi giao thức yêu cầu.
- Max lifetime, drain/shutdown policy.

`backlog` không phải thread pool size hoặc max active TLS connections. Một peer cố tình kết nối nhưng không handshake có thể gây resource exhaustion nếu server không giới hạn worker/connection lifetime.

## 8. Chứng chỉ và truststore dành riêng cho ví dụ

Chương trình ở mục 9 không dùng Internet hoặc certificate của website thật. Hãy tạo test key/trust material trong thư mục **tạm, không phải production/repo**:

- `server.p12`: PKCS12 keystore chứa private key và certificate test.
- `server.crt`: public certificate đã export.
- `trust.p12`: PKCS12 truststore chứa đúng certificate server test.
- `SAN=DNS:localhost,IP:127.0.0.1`: hostname/IP phù hợp để client kiểm tra endpoint.
- Password `changeit` **chỉ dành cho lab disposable**. Không hardcode secrets/đưa password lên command line production.

### 8.1. Bash / Linux / macOS

```bash
keytool -genkeypair \
  -alias localtls -keyalg RSA -keysize 3072 \
  -sigalg SHA256withRSA -validity 2 \
  -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost,OU=Local Test,O=Example,C=VN" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1" -noprompt

keytool -exportcert -rfc -alias localtls \
  -keystore server.p12 -storetype PKCS12 \
  -storepass changeit -file server.crt

keytool -importcert -noprompt -alias localtls \
  -file server.crt -keystore trust.p12 \
  -storetype PKCS12 -storepass changeit
```

Các lệnh `keytool` và chương trình Java đã được chạy thành công trên JDK 21. Certificate có hạn 2 ngày kể từ khi được tạo, nên hãy **tạo mới** trước khi chạy demo và xóa các file sau khi thử.

### 8.2. Windows PowerShell

PowerShell có thể chạy cùng các command `keytool` **mỗi lệnh trên một dòng**, không dùng dấu `\` nối dòng Bash. Ví dụ lệnh đầu:

```powershell
keytool -genkeypair -alias localtls -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 2 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost,OU=Local Test,O=Example,C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -noprompt
```

Tiếp theo dùng `-exportcert` và `-importcert` như trên, viết mỗi lệnh trên một dòng. Không commit `server.p12` vì chứa private key. Trong production, dùng certificate/CA/truststore và key management theo chính sách, không sử dụng test password/certificates.

## 9. Chương trình Java 17+ hoàn chỉnh

**File:** `SSLSocketTimeoutDemo.java`

Ba kết nối TLS nội bộ:

1. Kết nối thứ nhất handshake thành công, server im lặng 650 ms; client đọc với SO_TIMEOUT 150 ms, bắt `SocketTimeoutException` rồi close.
2. Kết nối thứ hai handshake thành công và đọc một dòng `"chao TLS"`, kiểm tra `SO_TIMEOUT=0`, giá trị âm bị từ chối và `SO_KEEPALIVE` độc lập.
3. Kết nối thứ ba server accept TCP nhưng chờ 700 ms không trả TLS handshake; client gọi `startHandshake()` với SO_TIMEOUT 150 ms và nhận timeout.

Source dùng SSLContext riêng server/client, truststore test **không bypass trust**, xác minh endpoint `HTTPS` và loopback `127.0.0.1`.

```java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.TrustManagerFactory;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class SSLSocketTimeoutDemo {
    private static final char[] PASS = "changeit".toCharArray();

    static SSLContext serverContext(Path file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(file)) {
            store.load(in, PASS);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, PASS);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    static SSLContext clientContext(Path file) throws Exception {
        KeyStore trust = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(file)) {
            trust.load(in, PASS);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    static SSLSocket connect(SSLContext context, int port)
            throws Exception {
        Socket tcp = new Socket();
        boolean handedOff = false;
        try {
            tcp.connect(new InetSocketAddress("127.0.0.1", port), 2000);
            SSLSocket ssl = (SSLSocket) context.getSocketFactory()
                    .createSocket(tcp, "127.0.0.1", port, true);
            handedOff = true;
            ssl.setEnabledProtocols(new String[]{"TLSv1.3"});
            SSLParameters params = ssl.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            ssl.setSSLParameters(params);
            ssl.setSoTimeout(2000);
            return ssl;
        } finally {
            if (!handedOff) tcp.close();
        }
    }

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        System.out.println(label + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "server.p12 and trust.p12 required");
        }
        SSLContext serverCtx = serverContext(Path.of(args[0]));
        SSLContext clientCtx = clientContext(Path.of(args[1]));
        ExecutorService workers = Executors.newSingleThreadExecutor();

        try (SSLServerSocket listener =
                     (SSLServerSocket) serverCtx.getServerSocketFactory()
                             .createServerSocket(0, 8,
                                     InetAddress.getByName("127.0.0.1"))) {
            listener.setEnabledProtocols(new String[]{"TLSv1.3"});
            listener.setSoTimeout(5000);
            Future<?> server = workers.submit(() -> {
                try {
                    try (SSLSocket first =
                                 (SSLSocket) listener.accept()) {
                        first.setSoTimeout(3000);
                        first.startHandshake();
                        Thread.sleep(650);
                    }
                    try (SSLSocket second =
                                 (SSLSocket) listener.accept()) {
                        second.setSoTimeout(3000);
                        second.startHandshake();
                        second.getOutputStream().write(
                                "chao TLS\n".getBytes(StandardCharsets.UTF_8));
                        second.getOutputStream().flush();
                    }
                    try (SSLSocket silent =
                                 (SSLSocket) listener.accept()) {
                        Thread.sleep(700);
                    }
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            int port = listener.getLocalPort();

            try (SSLSocket first = connect(clientCtx, port)) {
                check("endpointIdEnabled", "HTTPS".equals(
                        first.getSSLParameters()
                                .getEndpointIdentificationAlgorithm()));
                first.startHandshake();
                check("handshakeProtocolTLS13",
                        "TLSv1.3".equals(first.getSession().getProtocol()));
                first.setSoTimeout(150);
                check("readTimeoutConfigured",
                        first.getSoTimeout() == 150);
                boolean timedOut = false;
                try {
                    first.getInputStream().read();
                } catch (SocketTimeoutException expected) {
                    timedOut = true;
                }
                check("readTimeoutObserved", timedOut);
                check("timeoutDoesNotAutoClose", !first.isClosed());
            }

            try (SSLSocket second = connect(clientCtx, port)) {
                second.startHandshake();
                check("reconnectedAfterTimeout", "TLSv1.3".equals(
                        second.getSession().getProtocol()));
                String result = new BufferedReader(
                        new InputStreamReader(
                                second.getInputStream(),
                                StandardCharsets.UTF_8)).readLine();
                check("utf8Message", "chao TLS".equals(result));

                second.setSoTimeout(0);
                check("zeroMeansInfinite", second.getSoTimeout() == 0);
                boolean negativeRejected = false;
                try {
                    second.setSoTimeout(-1);
                } catch (IllegalArgumentException expected) {
                    negativeRejected = true;
                }
                check("negativeTimeoutRejected", negativeRejected);
                second.setKeepAlive(true);
                check("keepAliveIsNotReadTimeout",
                        second.getKeepAlive()
                                && second.getSoTimeout() == 0);
            }

            boolean handshakeTimedOut = false;
            try (SSLSocket third = connect(clientCtx, port)) {
                third.setSoTimeout(150);
                try {
                    third.startHandshake();
                } catch (SocketTimeoutException expected) {
                    handshakeTimedOut = true;
                }
            }
            check("handshakeReadTimeoutObserved", handshakeTimedOut);

            server.get(10, TimeUnit.SECONDS);
            check("serverFinished", true);
            System.out.println("checks=12/12");
        } finally {
            workers.shutdownNow();
            workers.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

### 9.1. Lệnh chạy

```bash
javac --release 17 -encoding UTF-8 SSLSocketTimeoutDemo.java
java SSLSocketTimeoutDemo server.p12 trust.p12
```

`java.base` đã chứa `javax.net.ssl`; không cần một thư viện TLS ngoài hoặc `--add-exports`. Java file mã hóa UTF-8, đặt cùng thư mục chứa `server.p12` và `trust.p12` (hoặc truyền đường dẫn thực).

### 9.2. Stdout đã kiểm chứng trên OpenJDK 21

```text
endpointIdEnabled=PASS
handshakeProtocolTLS13=PASS
readTimeoutConfigured=PASS
readTimeoutObserved=PASS
timeoutDoesNotAutoClose=PASS
reconnectedAfterTimeout=PASS
utf8Message=PASS
zeroMeansInfinite=PASS
negativeTimeoutRejected=PASS
keepAliveIsNotReadTimeout=PASS
handshakeReadTimeoutObserved=PASS
serverFinished=PASS
checks=12/12
```

Có **12 assertion PASS** và một dòng tổng kết. `keytool` có thể in log riêng trước khi chạy; đây **chỉ là stdout của Java demo**, không chứa private key, random key bytes hay local port. Cert test được sinh mới nên giá trị key/certificate không được coi là output cố định.

### 9.3. Ý nghĩa của từng phép kiểm tra

**`endpointIdEnabled`:** client đã đặt `SSLParameters` kiểm tra HTTPS endpoint trước handshake. Certificate có SAN cho IP literal; truststore chứa cert test.

**`handshakeProtocolTLS13`:** sau handshake, `SSLSession.getProtocol()` cho thấy TLSv1.3.

**`readTimeoutConfigured`:** getter của `Socket` cho biết 150 ms đã được đặt trước read.

**`readTimeoutObserved`:** server đã hoàn thành handshake nhưng không gửi application byte trong khoảng 650 ms. Client phát sinh `SocketTimeoutException` theo per-read wait 150 ms.

**`timeoutDoesNotAutoClose`:** sau application read timeout, `SSLSocket.isClosed()` vẫn false trong runtime thử nghiệm. Không sử dụng kết quả này để bảo đảm có thể tiếp tục parse message trên socket cũ.

**`reconnectedAfterTimeout`:** client **đóng kết nối cũ** rồi tạo connection TLS mới. Đây là recovery đơn giản khi trạng thái message không chắc chắn.

**`utf8Message`:** server mới trả một dòng theo UTF-8 và client nhận đúng `chao TLS`.

**`zeroMeansInfinite`:** `setSoTimeout(0)` đã làm option về zero; chương trình không cố read vô hạn để minh họa.

**`negativeTimeoutRejected`:** `setSoTimeout(-1)` ném `IllegalArgumentException` như contract.

**`keepAliveIsNotReadTimeout`:** bật TCP keepalive không biến timeout read hiện tại từ zero thành số khác. Đây không phải test phát hiện mạng bị đứt.

**`handshakeReadTimeoutObserved`:** server nhận TCP nhưng không trả handshake record; client `startHandshake()` quá hạn blocking read.

**`serverFinished`:** server xử lý đủ ba connections và Future hoàn thành trong 10 giây.

### 9.4. Giới hạn và tính ổn định

Test sử dụng `Thread.sleep` để tạo peer im lặng, vì vậy trên CI quá tải có thể có timing jitter; các kết quả trên đã được **kiểm chứng trên OpenJDK 21** chứ không cam kết mọi provider/OS sẽ có chính xác timing tương tự. Không sử dụng số mili giây trong demo như SLA production.

Hàm `connect` đóng raw TCP socket nếu chưa tạo layered SSL socket; **trong production** cần thêm cleanup nếu setup thất bại sau khi layered socket đã được tạo. Chương trình là **bài tập xác minh timeout**, không phải một network client framework xử lý đủ mọi failure path.

## 10. Quản lý kết nối và tài nguyên

### 10.1. Try-with-resources

`SSLSocket` là `AutoCloseable`. Hãy giữ ownership rõ ràng:

```java
try (SSLSocket socket = obtainConfiguredTlsSocket()) {
    socket.startHandshake();
    // Ghi request và đọc response theo framing/deadline.
}
```

Mảnh code cần helper `obtainConfiguredTlsSocket()` do ứng dụng cung cấp. Với layered socket tạo bằng `createSocket(raw, host, port, true)`, đóng SSL socket cũng đóng underlying raw TCP socket.

Khi thread bị interrupted, Future bị cancel hoặc timeout xảy ra, caller/owner phải đảm bảo `close()` được gọi. Đừng chỉ hủy một Future nhưng để socket đang block và resource manager không có khả năng đóng nó.

### 10.2. SO_KEEPALIVE không là timeout đọc

`socket.setKeepAlive(true)` bật TCP probes theo chính sách OS. Nó:

- Không đảm bảo peer TLS application vẫn xử lý request.
- Không đặt thời gian đọc tối đa cho `InputStream.read`.
- Không làm `OutputStream.write` tự có deadline.
- Không thay timeout/heartbeat của ứng dụng.

`getSoTimeout()` độc lập với `getKeepAlive()`. Nếu cần response trong ba giây, phải có per-read/total deadline riêng.

### 10.3. SO_TIMEOUT không khống chế write

Không có `SSLSocket.setSoWriteTimeout` trong public API Java 17+. `OutputStream.write` có thể block vì TCP buffers/peer không đọc. Với hard deadline bao gồm write:

- Áp giới hạn bytes gửi và backpressure.
- Có worker cancellation kết hợp close socket từ tầng quản lý.
- Có deadline chung đo bằng `System.nanoTime()`.
- Đánh giá `SSLEngine`/nonblocking transport hoặc HTTP client/server có API timeout rõ ràng nếu nhu cầu phức tạp.
- Không coi `setSoLinger` là write deadline; close behavior có thể phức tạp và gây block.

### 10.4. TLS close_notify và TLS 1.3 half-close

JSSE Reference Guide nêu TLS 1.2 và trước đó thường có duplex-close, còn TLS 1.3 có **half-close semantics**: inbound/outbound `close_notify` độc lập. Khi thiết kế streaming/protocol parsing, phải xét full completion và close messages, không giả định một bên đóng outbound đồng nghĩa đã đọc xong mọi data bên kia.

`SSLSocket.close()` là cách dọn resources thông thường trong blocking code. `SSLEngine.closeOutbound()/closeInbound()` là API khác dành cho nonblocking TLS engine; không trộn lẫn hai vòng đời.

### 10.5. EOF không đồng nghĩa đã nhận đủ message

Nếu application protocol yêu cầu 1.000 bytes mà client chỉ nhận 600 bytes rồi gặp EOF, **không được chấp nhận 600 bytes như response hoàn chỉnh**. TLS record integrity không thay thế application message framing. Luôn kiểm tra length-prefix, terminator, checksum/serialization và resource limits; phân biệt EOF với timeout.

## 11. Connection reuse, pooling và TLS session resumption

`SSLSocket` tự nó không cung cấp một HTTP connection pool đầy đủ. Nếu bạn xây pool:

- Chỉ đưa socket vào pool **sau khi handshake, trust và endpoint identification thành công**.
- Một request phải kết thúc đủ framing trước khi trả socket về pool.
- Sau TLS handshake failure, SSLException nghiêm trọng, truncated response hoặc timeout làm state không rõ: **discard**, không cho borrower tiếp theo sử dụng.
- Theo dõi idle lifetime, max age, max concurrent connections, acquire deadline và shutdown.
- Cách ly credentials/client certificates và authorization contexts nếu nhiều principals dùng chung service.
- Có retry idempotency, backoff và tổng thời gian giới hạn.
- Không nhầm TLS `SSLSession`/session ticket với user application session.

**Chọn công nghệ:** nếu mục tiêu chỉ là gọi HTTPS APIs thông thường, có thể dùng `java.net.http.HttpClient` với request timeout và SSLContext/trust options của nó thay vì tự code HTTP protocol trên `SSLSocket`. Đừng cố gán `SSLSocket.setSoTimeout` cho network connections nằm bên trong `HttpClient`, bởi đó là implementation detail và HTTP client có timeout API riêng.

## 12. Phân loại exception để xử lý đúng

| Tín hiệu | Phase thường gặp | Hướng phân tích |
| --- | --- | --- |
| `ConnectException` / connection refused | TCP connect. | Địa chỉ/port không lắng nghe, firewall hoặc service down. |
| `SocketTimeoutException` tại `tcp.connect` | TCP connect. | Network/route không connect kịp. |
| `SocketTimeoutException` tại `startHandshake` | TLS handshake read. | Peer không phản hồi TLS records kịp. |
| `SSLHandshakeException` | TLS negotiation/trust. | Certificate chain, SAN, algorithms, versions, peer alert. |
| `SSLException` | TLS protocol processing. | Record/certificate/protocol errors; bỏ socket không chắc chắn. |
| `SocketTimeoutException` tại `read` | Application data read. | Peer gửi chậm/không gửi hoặc response quá dài. |
| `read() == -1` | Stream EOF. | Kiểm tra message đủ chưa; có thể truncated. |
| `SocketException` connection reset | Transport. | Peer/network đóng bất thường. |
| `IOException` lúc close | Resource cleanup. | Giữ original exception, log metadata không có secrets. |

**Ghi log phase**, không chỉ tên exception. Cùng loại `SocketTimeoutException` nhưng connect và read có ý nghĩa khác nhau. Không retry vô hạn khi certificate/hostname validation fail.

### 12.1. Retry khi request đã có side effects

Ví dụ một lệnh thanh toán được server thực hiện xong, nhưng response tới client chậm. Client bị **read timeout**, rồi retry POST lần hai không có idempotency key có thể gây thực hiện hai lần.

Do đó:

- Đánh giá semantics idempotent/at-most-once/at-least-once của protocol.
- Dùng idempotency key nếu server hỗ trợ.
- Retry trên connection mới nếu trạng thái cũ không chắc chắn.
- Giới hạn số attempts và tổng deadline, có backoff/jitter.
- Không retry certificate errors như một transient timeout.
- Tránh để pool reuse broken sockets.

## 13. Logging và quan sát

Nên log metadata an toàn, không log private keys, passwords, plaintext secrets hay TLS session tokens:

| Field | Dùng để làm gì |
| --- | --- |
| `connectionId` | Correlation không chứa secret. |
| `destinationHost/port` | Server dự kiến, không log URL có credentials. |
| `tcpConnectMs` | Thời gian connect TCP. |
| `tlsHandshakeMs` | Thời gian handshake TLS riêng. |
| `soTimeoutMs` | Giá trị per-read wait tại thời điểm lỗi. |
| `overallBudgetMs` | Deadline tổng và thời gian đã dùng. |
| `negotiatedProtocol` | TLSv1.3/TLSv1.2 sau handshake thành công. |
| `phase` | CONNECT, HANDSHAKE, WRITE, READ, CLOSE. |
| `outcome` | SUCCESS, CONNECT_TIMEOUT, READ_TIMEOUT, TLS_FAIL, TRUNCATED, EOF. |
| `retryAttempt` | Theo dõi retry storm và idempotency. |

Khi debug JSSE trên máy local, có thể dùng:

```bash
java -Djavax.net.debug=ssl,handshake SSLSocketTimeoutDemo server.p12 trust.p12
```

Chế độ này có thể ghi log TLS rất dài ra stderr; không dùng làm stdout cố định hoặc bật rộng ở production không có bảo vệ dữ liệu. Với Java 17+, luôn kiểm tra security updates và cipher defaults theo provider/JDK đang triển khai.

## 14. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `setSoTimeout` được hiểu là TCP connect timeout. | Connect có thể diễn ra trước setting. | `Socket.connect(endpoint, timeout)`. |
| Dùng `SO_TIMEOUT=0` để “tránh timeout error”. | Read có thể chờ vô hạn. | Positive limit + total deadline. |
| Nghĩ `SO_TIMEOUT=-1` là infinite. | Ném IllegalArgumentException. | 0 nghĩa disabled. |
| Nghĩ mỗi lần read timeout làm socket tự đóng. | Socket Javadoc nói có thể vẫn valid. | Quyết định close/reuse theo protocol state. |
| Reuse sau handshake failure. | TLS connection không usable. | Close và connect mới. |
| Gọi `getSession()` trước SSLParameters. | Có thể implicit handshake. | Set trust/hostname/protocol/timeout trước. |
| Dùng trust-all TrustManager. | Mất xác thực TLS, có thể MITM. | Truststore/CA đúng. |
| Chỉ trust certificate mà không verify hostname. | Có thể kết nối nhầm peer identity. | Endpoint identification HTTPS/SAN. |
| Chỉ đặt timeout của SSLServerSocket. | Đã accept rồi vẫn có thể read treo. | Set timeout cho từng accepted SSLSocket. |
| Nghĩ `SO_KEEPALIVE` là 1s app deadline. | TCP probes phụ thuộc OS. | Application timeout riêng. |
| Nghĩ 1 lần `read()` nhận cả message. | TLS là byte stream. | Framing và length/max bytes. |
| Không giới hạn total response time. | Peer gửi trickle bytes để kéo dài. | Monotonic deadline/cancellation. |
| Nghĩ SO_TIMEOUT giới hạn write. | Không có public write-timeout counterpart. | Bounded work, cancellation/close. |
| Nhận EOF là response hợp lệ. | Có thể bị cắt dữ liệu. | Check framing/content completeness. |
| Retry POST ngay sau read timeout. | Server có thể đã hoàn thành operation. | Idempotency key/policy. |
| Không đóng socket trong exception path. | Rò resources/connections/threads. | Try-with-resources, cleanup. |
| Nhầm TLS session và user session. | Sai authentication/authorization. | Domain session riêng. |
| Log toàn bộ `javax.net.debug` production. | Dữ liệu và chi phí log lớn. | Debug có giới hạn, redact. |

## 15. Checklist production

- [ ] Đã phân biệt TCP connect, TLS handshake, read, write, accept và total request deadline?
- [ ] Có `Socket.connect(..., positiveTimeoutMs)` thay vì chỉ setSoTimeout sau connect?
- [ ] Có `setSoTimeout(positive)` **trước handshake/read**?
- [ ] Đã cấu hình `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`?
- [ ] Có trusted CA/certificate, không trust-all?
- [ ] Certificate SAN khớp hostname/IP thật?
- [ ] Có policies cho TLS 1.3/1.2 và cipher suites hiện hành?
- [ ] Có total deadline, framing, max body size, max lifetime?
- [ ] Có xử lý timeout khác EOF và TLS handshake failure?
- [ ] Có close connection sau lỗi protocol không chắc chắn?
- [ ] Có ownership/cleanup cho raw socket và layered SSLSocket?
- [ ] Server accepted sockets có timeouts và connection limits riêng?
- [ ] Executor/queue/connection pool có bounded capacities?
- [ ] Có phân biệt SO_KEEPALIVE với application heartbeat?
- [ ] Có kiểm tra complete message và close_notify/truncation?
- [ ] Có retry/idempotency policy cho side-effect operations?
- [ ] Có exception-phase logging, metrics, backoff và alerts?
- [ ] Không dùng SSLv3/TLS1.0/1.1 hoặc tắt certificate validation để chữa lỗi?
- [ ] Không commit test keystore hoặc production private key vào repo?
- [ ] Có tests silent handshake, slow data, wrong certificate, wrong hostname và reconnect?
- [ ] Có chạy integration tests trên JDK/provider/OS đúng môi trường production?

## 16. Bài tập thực hành

**A.** Thay `setSoTimeout(150)` bằng 350 ms ở first connection; giải thích vì sao vẫn có thể timeout khi server đợi 650 ms.

**B.** Chứng minh `Socket.connect(endpoint, 2000)` không phải total TLS request deadline bằng cách cho server hoàn thành TCP nhưng trì hoãn handshake.

**C.** Thay `SO_TIMEOUT=0` trong sandbox và thiết kế cancellation để test không treo vô hạn.

**D.** Cho server gửi một byte mỗi 500 ms trong 20 giây, client đặt SO_TIMEOUT 600 ms. Giải thích tại sao cần total deadline dù mỗi read thành công.

**E.** Tạo truststore test không chứa certificate server. Đoán `SSLHandshakeException`, không sửa bằng trust-all.

**F.** Dùng SAN không khớp IP/hostname của client. Quan sát endpoint identification fail, giải thích khác trust chain.

**G.** Đặt listener `setSoTimeout(300)` nhưng accepted socket không timeout. Phân tích server bị treo ở đâu.

**H.** Cho server gửi 4/10 bytes rồi đóng; client phải từ chối response bị cắt bằng length-prefix validation.

**I.** Bật `setKeepAlive(true)`; kiểm tra `getSoTimeout()` giữ nguyên và giải thích khác application liveness.

**J.** Mô phỏng slow writer: server không đọc request body; đề xuất tổng deadline, cancellation và đóng socket.

**K.** Thiết kế reusable TLS connection pool với các trạng thái NEW, HANDSHAKING, READY, IN_USE, BROKEN, CLOSED. Khi timeout ở read thì state chuyển thế nào?

**L.** Đọc JSSE close_notify guidance về TLS 1.3 half-close; viết các test peer normal close và abrupt close.

**M.** Xây retry policy cho idempotent GET và non-idempotent POST, có max attempts/backoff/total time budget.

**N.** Dùng monotonic `System.nanoTime()` để tính remainingMillis trước mỗi read, không truyền 0 vào `setSoTimeout` khi deadline hết.

**O.** Viết một bảng monitoring gồm handshake duration, connect failures, read timeout rate, truncated data và active connections.

## 17. Câu hỏi tự kiểm tra

**1. `SSLSocket` kế thừa timeout của class nào?** — `java.net.Socket`.

**2. `setSoTimeout(1500)` kiểm soát gì?** — Blocking InputStream read wait, không phải tổng request.

**3. Giá trị 0 nghĩa gì?** — Vô hiệu read timeout.

**4. Giá trị âm được chấp nhận không?** — Không; IllegalArgumentException.

**5. TCP connect được giới hạn bằng API nào?** — `Socket.connect(SocketAddress,int)`.

**6. Server listener setSoTimeout kiểm soát gì?** — `accept()`, không tự kiểm soát read của accepted socket.

**7. Vì sao nên đặt SO_TIMEOUT trước `startHandshake()`?** — Handshake có thể blocking read.

**8. SetSoTimeout có đảm bảo total handshake deadline không?** — Không, nó chỉ giới hạn các blocking reads.

**9. Truststore đủ để kiểm chứng đúng hostname không?** — Không nên giả định; bật HTTPS endpoint identification.

**10. SSLSession có phải phiên đăng nhập?** — Không; đó là TLS negotiation/resumption state.

**11. Khi application read timeout, socket có tự closed?** — Theo Socket contract vẫn có thể valid; demo JDK21 thấy chưa closed, nhưng nên close nếu protocol state không chắc chắn.

**12. Khi initial TLS handshake fail, có reuse được SSLSocket?** — Không.

**13. SO_KEEPALIVE có thay read timeout không?** — Không.

**14. SO_TIMEOUT có khống chế write không?** — Không.

**15. EOF có bảo đảm đầy đủ response không?** — Không; cần framing.

**16. Retry POST khi read timeout có an toàn tuyệt đối không?** — Không, server có thể đã thực thi; cần idempotency.

**17. Ví dụ có dùng Internet, trust-all hoặc external library không?** — Không. Chỉ dùng TLS test trên loopback với cert/truststore riêng.

**18. Ví dụ đã kiểm chứng mấy tests?** — 12/12, biên dịch cho Java 17 và chạy trên OpenJDK 21.

## 18. Nguồn tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — SSLSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): TLS handshake, socket lifecycle, SSLSession, thiết lập protocol.
- [Oracle Java SE 26 — Socket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Socket.html): `connect(endpoint, timeout)`, `setSoTimeout`, `getSoTimeout`, `SO_KEEPALIVE`.
- [Oracle Java SE 26 — ServerSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/ServerSocket.html): `accept` timeout và socket listener semantics.
- [Oracle Java SE 26 — SSLServerSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): server TLS socket.
- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification, SNI, protocols và cipher suites.
- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): key/trust managers, TLS 1.2/1.3, socket factories.
- [Oracle Java SE 26 — SSLSocketFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocketFactory.html): layered TLS socket.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): server key material.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): trusted certificates.
- [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): close_notify, TLS 1.3, bảo mật JSSE.
- [Oracle Java SE 17 — SSLSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html): API phù hợp `--release 17`.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS protocol, handshake và closure.

**Ghi nhớ:** `SSLSocket.setSoTimeout(ms)` là **read wait timeout**, không phải TCP connect timeout, write timeout hoặc total deadline. Hãy tách từng giai đoạn, bật trust và hostname verification trước handshake, có framing và ngân sách tổng, đóng connection lỗi/không rõ trạng thái, và chỉ retry theo idempotency policy. Đây là nền tảng quản lý TLS connection đúng trong ứng dụng Java hiện đại.
