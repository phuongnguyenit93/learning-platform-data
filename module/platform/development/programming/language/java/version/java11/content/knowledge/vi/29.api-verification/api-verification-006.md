# Quản lý truststore, locale, charset và tài nguyên hệ thống khi kiểm chứng API trong Java 11

**Chủ đề cha:** Kiểm chứng API  
**Bài học:** Quản lý truststore, locale, charset và tài nguyên hệ thống  
**Phạm vi:** Kiểm chứng hợp đồng của API Java 11 khi môi trường TLS, ngôn ngữ, mã hóa văn bản, hệ điều hành, process/thread và tài nguyên I/O khác nhau. Ưu tiên **API công khai và thực hành vẫn còn áp dụng trên Java hiện đại**; phân biệt chính xác hành vi Java 11 với thay đổi sau Java 11, không khuyên tắt xác minh chứng chỉ hoặc dùng API nội bộ/đã lỗi thời.

Một API có thể chạy đúng ở máy phát triển nhưng thất bại sau khi chuyển môi trường chỉ vì **truststore khác**, **locale mặc định khác**, **charset mặc định khác**, **múi giờ khác**, hoặc một test trước đó đã để lại **system property, file/socket/process chưa đóng**. Trong kiểm chứng API, các thay đổi như vậy phải được xem là **đầu vào và điều kiện chạy** cần kiểm soát, không phải phần “ngẫu nhiên của hệ thống” mà có thể bỏ qua.

Ví dụ: một REST client Java 11 gửi đúng JSON UTF-8 nhưng kết nối HTTPS bị từ chối khi JVM không có CA phù hợp; một giá trị `1,234.5` bị đọc thành số khác ở locale khác; chữ `TITLE` đổi sang chữ thường khác ở Turkish locale; hoặc test chạy song song bị lỗi vì test khác vừa gọi `Locale.setDefault`. Những trường hợp này liên quan trực tiếp đến **tính đúng, an toàn bảo mật và khả năng tái lập của API**, chứ không chỉ vấn đề cấu hình triển khai.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **truststore** (những danh tính/CA được tin cậy) với **keystore chứa identity/private key** (thông tin định danh của client/server).
2. Giải thích JSSE dùng truststore mặc định trong HotSpot/Java 11, và kiểm soát `javax.net.ssl.trustStore`, `trustStoreType`, `trustStorePassword` đúng mục đích.
3. Tạo `KeyStore("PKCS12")`, `TrustManagerFactory` và **`SSLContext` riêng** cho một API client/test, thay vì thay đổi trạng thái TLS chung của JVM.
4. Kiểm tra cả **certificate chain trust** và **hostname/endpoint identity**, không chọn trust manager chấp nhận mọi chứng chỉ.
5. Viết bài kiểm thử TLS localhost có chứng chỉ test chứa SAN, xác nhận kết nối hợp lệ, từ chối sai hostname và từ chối truststore rỗng.
6. Truyền `Locale` tường minh cho định dạng số/ngày, dùng `Locale.ROOT` cho chuẩn hóa key có ý nghĩa locale-independent, và tách **Locale** khỏi **ZoneId**.
7. Dùng `StandardCharsets.UTF_8` cho bytes, file và HTTP; giải mã malformed input theo chính sách `CodingErrorAction.REPORT`.
8. Phân biệt **default charset của Java 11** với thay đổi UTF-8-by-default từ **Java 18** (JEP 400).
9. Quản lý `InputStream`, `OutputStream`, `BufferedReader/Writer`, TLS sockets, temp files, subprocess và HTTP response streams bằng **try-with-resources + timeout + cleanup**.
10. Cô lập những thiết lập process-global như `Locale.setDefault` và `System.setProperty` bằng child JVM khi cần test thay đổi môi trường.
11. Kiểm chứng API tích hợp qua một HTTP server chỉ chạy ở loopback, có `Accept-Language`, `Content-Type`, UTF-8 và kiểm tra response body.
12. Thiết kế ma trận test có giá trị bất biến, test âm tính, quota, bí mật và portability giữa các môi trường JDK hiện đại.

## 2. Bốn nguồn sai khác của API nên kiểm soát

| Trục môi trường | Ví dụ | Rủi ro | Quy tắc kiểm thử |
|---|---|---|---|
| **TLS/truststore** | CA nội bộ, self-signed cert, SAN, chain khác | Handshake lỗi, hoặc tệ hơn là tắt validation | Dùng CA/test cert riêng, kiểm tra trusted + rejected |
| **Locale/format** | English, German, Vietnamese, Turkish | Số, chữ, ngày, currency và key khác | Truyền `Locale` rõ ràng, không phụ thuộc default |
| **Charset/bytes** | UTF-8, Windows code page, malformed bytes | Mojibake, thay ký tự, sai chữ ký/hash | Charset tường minh và kiểm tra byte-level |
| **Tài nguyên/trạng thái** | File, stream, socket, thread, system property, timezone | Leak, port conflict, test phụ thuộc thứ tự | Resource lifecycle, cleanup, timeout, process isolation |

Điểm khác biệt lớn nhất giữa *kiểm tra đúng một lần* và **kiểm chứng API có thể tái lập** là test phải biết mình đang phụ thuộc vào đâu. Mọi phụ thuộc môi trường nên thuộc một trong hai nhóm: (1) **truyền tường minh** và kiểm soát trong code, (2) **ghi nhận/kiểm tra như một precondition** khi chạy trên JVM mục tiêu.

### 2.1 Thứ tự ưu tiên trong thiết kế

```text
Dữ liệu / request / credential fixture có nguồn tin cậy
                 |
                 v
    Đặt Locale / ZoneId / Charset tường minh
                 |
                 v
    Tạo SSLContext riêng + trust policy nghiêm ngặt
                 |
                 v
    Thời hạn kết nối, request và tổng test
                 |
                 v
      try-with-resources / bounded work
                 |
                 v
    So sánh contract, không so giả định máy
                 |
                 v
      Cleanup và báo kết quả PASS/FAIL
```

Không chỉnh `Locale.setDefault`, `TimeZone.setDefault` hoặc `SSLContext.setDefault` trong một test chạy song song rồi tin rằng restore trong `finally` đã xóa hết rủi ro tranh chấp. Những state global này có thể đã bị thread khác quan sát hoặc cache trong thư viện.

## 3. Truststore và keystore: hai vai trò khác nhau

**Truststore** thường chứa **trusted certificates** hoặc **CA trust anchors** dùng để đánh giá chứng chỉ mà peer trình bày. **Keystore của identity** thường chứa **private key + certificate chain** để một phía chứng minh danh tính, ví dụ HTTPS server hoặc client sử dụng mutual TLS (mTLS).

| Thành phần | Câu hỏi nó trả lời | API Java 11 |
|---|---|---|
| Truststore | “Tôi tin ai đã ký/chứng thực peer?” | `KeyStore`, `TrustManagerFactory` |
| Server identity keystore | “Tôi trình bày chứng chỉ nào và ký handshake bằng private key nào?” | `KeyStore`, `KeyManagerFactory` |
| Client identity keystore cho mTLS | “Client chứng minh danh tính của mình ra sao?” | `KeyManagerFactory` với key pair của client |
| SSLContext | “Dùng các key/trust managers và TLS policy nào?” | `SSLContext.getInstance("TLS")`, `init` |
| Endpoint identity policy | “Peer có đúng hostname mong đợi?” | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` |
| HTTP layer | “Request/response có đúng method, status, headers, body?” | `java.net.http.HttpClient` hoặc HTTPS API phù hợp |

**Một chứng chỉ “được trust” không có nghĩa hostname bất kỳ đều hợp lệ.** Ví dụ truststore chứa chứng chỉ của `localhost` nhưng API đang gọi `not-localhost.invalid`, thì endpoint identification vẫn phải từ chối. Ngược lại, hostname đúng không làm một chain không được trust trở thành hợp lệ.

### 3.1 Truststore mặc định trong Java 11

Theo **JSSE Reference Guide Java SE 11** cho triển khai SunJSSE:

1. Nếu `javax.net.ssl.trustStore` được chỉ định, mặc định trust manager thử sử dụng file đó và các properties liên quan như `javax.net.ssl.trustStoreType`, `javax.net.ssl.trustStorePassword`.
2. Nếu **không** chỉ định `trustStore`, JSSE tìm `java.home/lib/security/jssecacerts` nếu tồn tại.
3. Nếu không có `jssecacerts`, thử `java.home/lib/security/cacerts`.
4. Khi không tìm được trust material phù hợp, trust manager có thể được khởi tạo với **empty truststore**.

**Bẫy quan trọng:** với SunJSSE, **đã đặt** `javax.net.ssl.trustStore` nhưng path **không tồn tại** thì trust manager mặc định có thể dùng **empty keystore**, **không tự fallback** về `cacerts`. Triệu chứng thường là `SSLHandshakeException` hoặc lỗi PKIX khi client không tìm được trust anchor. Không sửa bằng “accept-all TrustManager”.

Ví dụ cấu hình mặc định bằng system properties, chỉ để hiểu cơ chế:

```bash
java -Djavax.net.ssl.trustStore=/path/to/app-trust.p12 -Djavax.net.ssl.trustStoreType=PKCS12 YourApplication
```

Đây là **mẫu lệnh**, `/path/to/app-trust.p12` và `YourApplication` phải thay cho môi trường thật. Nếu truststore có password, đặt thông qua cơ chế secret/config được bảo vệ; tránh cung cấp **secret thật dưới dạng `-D...Password=...` ở command line**, vì process listing/log/diagnostic có thể lộ.

**Lưu ý:** quy tắc đường dẫn mặc định và các system properties trên mô tả **SunJSSE/HotSpot** trong Java 11, không phải cam kết mọi provider/VM đều tuân thủ tất cả chi tiết. Cùng một ứng dụng chạy trên custom runtime image/container có thể có `cacerts` khác với máy phát triển.

### 3.2 PKCS#12 thay vì suy đoán JKS

Từ Java 9, **PKCS12** là default keystore type trong Java SE triển khai phổ biến (JEP 229). Vì vậy trên Java 11, dùng tường minh `KeyStore.getInstance("PKCS12")` khi tệp thực sự là PKCS#12. Không suy từ phần mở rộng tên file để khẳng định định dạng: `.p12/.pfx` thường biểu thị PKCS#12, nhưng source of truth là file và provider.

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(path)) {
    trust.load(input, passwordChars);
}

TrustManagerFactory managers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
managers.init(trust);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, managers.getTrustManagers(), null);
```

Đây là **trích đoạn**, cần khai báo `path` (Path), `passwordChars` (char[]) và imports `KeyStore`, `Files`, `SSLContext`, `TrustManagerFactory`. Nó tạo một trust policy **riêng** theo object `context`, không tự sửa truststore mặc định của toàn JVM. Đối với server/mTLS, `context.init` còn cần đúng `KeyManager[]` từ identity keystore. Tham số null của `init` không có nghĩa “tin mọi chứng chỉ”; trong ví dụ này trust managers đã được tạo từ truststore chủ động.

### 3.3 Vì sao nên tạo SSLContext riêng?

- **Cô lập:** Client A có thể trust CA A, Client B trust CA B mà không sửa `System.setProperty("javax.net.ssl.trustStore", ...)` ở process global.
- **Tái lập:** test biết chính xác certificate(s) nào có trong truststore, không phụ thuộc JDK `cacerts`/container image.
- **Dễ kiểm tra âm tính:** cùng host nhưng dùng truststore rỗng phải bị từ chối.
- **Bảo mật:** không đụng `X509TrustManager` accept-all hay tắt hostname verification.
- **Vòng đời:** khi certificate rotation, tạo **SSLContext/client/connection pool mới** theo chính sách rồi chuyển traffic; đừng cho rằng sửa file truststore là mọi socket/context đang tồn tại tự nhận ngay thay đổi.

Với `java.net.http.HttpClient` Java 11 có thể truyền `HttpClient.newBuilder().sslContext(context)`, nhưng vẫn cần giữ verification của HTTPS; không cố tình dùng các internal flags/property để vô hiệu hóa endpoint identification. Với raw `SSLSocket`, phải đặt endpoint identification algorithm bằng `SSLParameters`.

## 4. Các kiểm tra bảo mật cần có cho TLS API

Một test HTTPS có ích **không chỉ kiểm tra status=200**, mà phải xác minh chính sách kết nối:

| Ca | Điều kiện | Kết quả hợp lệ |
|---|---|---|
| Positive | Cert hợp lệ, chain nằm trong truststore, hostname khớp SAN | Handshake thành công |
| Wrong host | Cert trusted nhưng SAN không khớp hostname đang gọi | Handshake bị từ chối |
| Empty truststore | Cert không có trust anchor tương ứng | Handshake bị từ chối |
| Missing truststore | Path không tồn tại hoặc không đọc được | Setup fail rõ, không fallback insecure |
| Wrong password | Không load được keystore/truststore | Fail rõ, không bỏ integrity check |
| Expired cert | Chứng chỉ hết hạn theo policy PKIX | Bị từ chối |
| Invalid chain | Chuỗi không hợp lệ hoặc thuật toán bị policy cấm | Bị từ chối |
| Rotated CA | Đổi sang CA đã được phê duyệt | Test positive/negative tương ứng |
| Redirect đến host khác | HTTPS destination thay đổi | Kiểm tra TLS peer identity của đích mới |
| mTLS | Server yêu cầu client certificate | Client gửi identity đúng, bị từ chối nếu thiếu |

Không đánh đồng `javax.net.ssl.trustStore` với `javax.net.ssl.keyStore`; property thứ hai phục vụ identity key material. Đừng import hàng loạt bất kỳ chứng chỉ nhìn thấy trên Internet vào `cacerts` chỉ để hết lỗi handshake. Xác minh CA/cert fingerprint bằng một kênh tin cậy, tuân thủ PKI policy, certificate expiry và rotation.

### 4.1 Hostname verification không phải tùy chọn “để test dễ chạy”

Với raw `SSLSocket`, JSSE Reference Guide khuyên kiểm tra credential/endpoint identity trước khi gửi dữ liệu ứng dụng. Có thể thiết lập:

```java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
sslSocket.setSSLParameters(parameters);
sslSocket.startHandshake();
```

Đây là **trích đoạn** sau khi tạo `sslSocket` bằng `SSLSocketFactory` với đúng expected peer hostname. Khi dùng layered socket `createSocket(tcpSocket, expectedHost, port, true)`, `expectedHost` cung cấp tên sẽ kiểm chứng trên chứng chỉ. **Không** dùng tên sai hoặc giá trị null để “tránh” SAN check.

API certificate/hostname failure thường báo `SSLHandshakeException` (subclass `SSLException`), nhưng wording chi tiết khác theo JDK/version/chain. Trong kiểm thử, assert handshake **thất bại vì lớp bảo mật thích hợp**, không phụ thuộc toàn văn thông điệp lỗi do provider tạo.

### 4.2 Đừng vô hiệu hóa TrustManager/HostnameVerifier

Các anti-pattern sau bị **loại bỏ** khỏi hướng dẫn hiện đại:

- `X509TrustManager.checkServerTrusted(...)` bỏ trống, không xác minh chain.
- `HostnameVerifier` luôn trả `true`.
- Dùng API nội bộ để bỏ endpoint identification cho `HttpClient`.
- Bật protocol/cipher suite yếu chỉ để tương thích server cũ.
- Đưa password/chứng chỉ khóa riêng vào repository hoặc log.

Test local nên tạo **cert test riêng** rồi trust đúng cert đó. Production phải có PKI, key storage và rotation được quản lý; không tái sử dụng self-signed private key của fixture.

## 5. Demo chạy được 1 — PKCS#12 + TLS localhost, có cả positive và negative cases

Đây là integration test về **truststore và certificate/hostname verification** trên Java 11. Chương trình không kết nối Internet, chỉ dùng `127.0.0.1` và ephemeral port.

Nó tạo hai `SSLContext` cho client: một từ truststore chứa chứng chỉ test `localhost`, một từ **empty PKCS12 truststore**. Server có identity riêng chứa private key. Ba kết nối được thử **trên cùng server certificate**:

1. Trusted store + expected hostname `localhost` → **thành công**.
2. Trusted store + expected hostname `not-localhost.invalid` → **bị từ chối** do name mismatch.
3. Empty truststore + expected hostname `localhost` → **bị từ chối** do thiếu trust anchor.

### 5.1 Tạo fixture hoàn toàn tạm thời bằng keytool

Dùng JDK `keytool` trên một **thư mục thử nghiệm riêng**. Đây là các câu lệnh cho test/disposable certificate, **password `local-test-only` cố ý là giá trị giả trong mã và CLI, không phải ví dụ quản lý secret production**.

```bash
# Chỉ chạy trong thư mục test trống, không sử dụng trên truststore thật.
keytool -genkeypair -noprompt -alias localhost-test -keystore identity.p12 -storetype PKCS12 -storepass local-test-only -keypass local-test-only -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -dname "CN=localhost, OU=Test, O=Local, C=US" -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert -rfc -alias localhost-test -keystore identity.p12 -storetype PKCS12 -storepass local-test-only -file localhost.pem

keytool -importcert -noprompt -alias localhost-test -file localhost.pem -keystore trust.p12 -storetype PKCS12 -storepass local-test-only
```

Lệnh thứ nhất tạo **identity.p12** có private key/cert self-signed với SAN `dns:localhost` và `ip:127.0.0.1`. Lệnh thứ hai xuất **public certificate**. Lệnh thứ ba import public cert vào **trust.p12**, không đưa private key vào truststore. Mỗi cert test chỉ có thời hạn 2 ngày; khi chạy lại sau hạn hoặc dùng tên khác, phải tạo fixture mới có SAN đúng và không reuse test identity trong production. `-noprompt` chỉ phù hợp với fixture test được kiểm soát, không dành cho nhập trust anchors không kiểm chứng.

### 5.2 Chương trình đầy đủ

Lưu thành **`TrustStoreIsolationDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.KeyStore;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TrustStoreIsolationDemo {
    private static final char[] TEST_PASSWORD =
            "local-test-only".toCharArray();

    static KeyStore loadPkcs12(Path path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(path)) {
            store.load(input, TEST_PASSWORD);
        }
        return store;
    }

    static SSLContext serverContext(KeyStore identity) throws Exception {
        KeyManagerFactory keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(identity, TEST_PASSWORD);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys.getKeyManagers(), null, null);
        return context;
    }

    static SSLContext clientContext(KeyStore trust) throws Exception {
        TrustManagerFactory managers = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        managers.init(trust);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, managers.getTrustManagers(), null);
        return context;
    }

    static void connectAndVerify(SSLContext context, int port,
                                 String expectedHost) throws Exception {
        try (Socket tcp = new Socket("127.0.0.1", port);
             SSLSocket tls = (SSLSocket) context.getSocketFactory()
                     .createSocket(tcp, expectedHost, port, true)) {
            tls.setSoTimeout(5000);
            SSLParameters policy = tls.getSSLParameters();
            policy.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(policy);
            tls.startHandshake();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: TrustStoreIsolationDemo <identity.p12> <trust.p12>");
        }

        KeyStore identity = loadPkcs12(Paths.get(args[0]));
        KeyStore trusted = loadPkcs12(Paths.get(args[1]));
        KeyStore empty = KeyStore.getInstance("PKCS12");
        empty.load(null, TEST_PASSWORD);

        SSLContext serverContext = serverContext(identity);
        SSLContext trustedClient = clientContext(trusted);
        SSLContext emptyClient = clientContext(empty);

        AtomicInteger accepts = new AtomicInteger();
        AtomicInteger serverOk = new AtomicInteger();
        AtomicReference<Exception> serverFailure = new AtomicReference<>();

        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 5, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(12000);
            Thread server = new Thread(() -> {
                try {
                    for (int i = 0; i < 3; i++) {
                        try (SSLSocket peer = (SSLSocket) listener.accept()) {
                            accepts.incrementAndGet();
                            peer.setSoTimeout(5000);
                            try {
                                peer.startHandshake();
                                serverOk.incrementAndGet();
                            } catch (java.io.IOException expectedFromRejectedClient) {
                                // The two negative client checks abort TLS.
                            }
                        }
                    }
                } catch (Exception failure) {
                    serverFailure.set(failure);
                }
            }, "isolated-local-tls-fixture");
            server.setDaemon(true);
            server.start();

            connectAndVerify(trustedClient, listener.getLocalPort(),
                    "localhost");
            boolean badHostRejected = false;
            try {
                connectAndVerify(trustedClient, listener.getLocalPort(),
                        "not-localhost.invalid");
            } catch (SSLException expected) {
                badHostRejected = true;
            }
            boolean untrustedRejected = false;
            try {
                connectAndVerify(emptyClient, listener.getLocalPort(),
                        "localhost");
            } catch (SSLException expected) {
                untrustedRejected = true;
            }
            server.join(12000);
            if (server.isAlive() || serverFailure.get() != null) {
                throw new AssertionError("TLS fixture server did not finish",
                        serverFailure.get());
            }
            System.out.println("truststore-cert-count=" + trusted.size());
            System.out.println("trusted-local-handshake=true");
            System.out.println("wrong-host-rejected=" + badHostRejected);
            System.out.println("empty-truststore-rejected="
                    + untrustedRejected);
            System.out.println("server-connections=" + accepts.get());
            System.out.println("server-successes=" + serverOk.get());
            System.out.println("global-sslcontext-not-overridden=true");
            if (trusted.size() != 1 || !badHostRejected
                    || !untrustedRejected || accepts.get() != 3
                    || serverOk.get() != 1) {
                throw new AssertionError("TLS trust isolation failed");
            }
        }
    }
}
```

Biên dịch/chạy trong **chính thư mục có hai tệp PKCS#12**:

```bash
javac --release 11 -encoding UTF-8 TrustStoreIsolationDemo.java
java TrustStoreIsolationDemo identity.p12 trust.p12
```

**Stdout đã chạy kiểm chứng:**

```text
truststore-cert-count=1
trusted-local-handshake=true
wrong-host-rejected=true
empty-truststore-rejected=true
server-connections=3
server-successes=1
global-sslcontext-not-overridden=true
```

**Giải thích kết quả:**

- `truststore-cert-count=1`: truststore kiểm thử có đúng một chứng chỉ được import.
- `trusted-local-handshake=true`: client trust cert và kiểm tra hostname `localhost`, sau đó handshake thành công.
- `wrong-host-rejected=true`: client vẫn trust certificate chain, nhưng endpoint name không khớp SAN.
- `empty-truststore-rejected=true`: không thể xác minh peer từ empty truststore.
- `server-connections=3`: server chấp nhận ba kết nối thử; negative cases có thể hủy handshake và server xử lý I/O exception tương ứng.
- `server-successes=1`: chỉ lần positive hoàn thành TLS handshake ở server.
- `global-sslcontext-not-overridden=true`: source code không gọi `SSLContext.setDefault` và không sửa `javax.net.ssl.*` global properties. Dòng này mô tả cách viết test, không phải phép đo tất cả đối tượng TLS khác trong JVM.

Trong demo, server dùng socket loopback địa chỉ 127.0.0.1, client tạo TCP tới địa chỉ đó rồi wrap TLS với peer hostname do test quy định. Hai thông tin không mâu thuẫn: **endpoint identification** của TLS dựa vào expected hostname và SAN. Việc bắt `java.io.IOException` ở phía server cho các negative cases là cần thiết vì client hủy handshake có thể hiện thành `SSLException`, EOF hoặc IOException khác ở phía nhận.

**Điểm an toàn:** Test đặt timeouts, dùng ephemeral port, đóng sockets/keystore streams, xử lý kết quả từng lần. `TEST_PASSWORD` hardcode chỉ được phép trong fixture test **được sinh mới rồi hủy**; production phải lấy password từ secret manager/credential provider bằng cơ chế phù hợp, xóa char[] tạm khi có thể, kiểm soát quyền file và tránh in password ra log.

### 5.3 Vì sao không thao tác global truststore ở runtime?

Một pattern sai trong test song song:

```java
System.setProperty("javax.net.ssl.trustStore", "a.p12");
// Sau đó test B lại set "b.p12" trong cùng JVM.
```

Đây là trích đoạn anti-pattern. Tùy provider và thứ tự khởi tạo, default `SSLContext` hoặc connection pools đã được tạo/cached từ trước; việc đổi property ở runtime **không có cam kết** mọi kết nối đang tồn tại sẽ dùng file mới. Hai test cùng process có thể gây race. Cách tốt hơn: tạo `SSLContext` riêng như ví dụ, inject vào client phù hợp và kiểm tra bằng test âm tính.

## 6. Locale: tham số đầu vào của định dạng chứ không phải chi tiết phụ

`java.util.Locale` quy định quy ước ngôn ngữ/vùng, ảnh hưởng:

- Tên ngày/tháng, cách hiển thị số, tiền tệ, phần trăm và dấu phân cách.
- Chuyển đổi chữ hoa/chữ thường khi dùng overload nhận `Locale`.
- Chọn resource bundle/localized messages.
- Một số thao tác parsing/formatting có locale default.
- Giá trị truyền qua HTTP như `Accept-Language` khi ứng dụng yêu cầu.

**Locale không tự quyết định múi giờ.** `Locale.forLanguageTag("vi-VN")` là vùng/ngôn ngữ; `ZoneId.of("Asia/Ho_Chi_Minh")` là time zone. Hai thứ cần tách ra. Một người dùng vi-VN có thể đang sống tại Tokyo, một API sử dụng UTC cho mọi dữ liệu; đừng suy ra zone từ locale một cách ngầm định.

### 6.1 Default Locale là process-global state

Các method như `Locale.getDefault()` và `Locale.setDefault(...)` sử dụng/thay đổi default process-wide, có thể ảnh hưởng thread khác. `Locale.getDefault(Locale.Category.FORMAT)` và `Locale.getDefault(Locale.Category.DISPLAY)` còn cho phép phân biệt nhóm mặc định theo chức năng. Dùng default trong thư viện/test có thể khiến kết quả khác giữa môi trường.

**Thực hành khuyến nghị:** truyền `Locale` trực tiếp:

```java
NumberFormat n = NumberFormat.getNumberInstance(Locale.US);
DateTimeFormatter dt = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd", Locale.ROOT);
String normalized = "TITLE".toLowerCase(Locale.ROOT);
```

Đây là trích đoạn; imports `NumberFormat`, `DateTimeFormatter`, `Locale`. Với payload API có định dạng máy đọc (ISO 8601, JSON number, HTTP headers), ưu tiên contract chuẩn và parser phù hợp thay vì format tùy locale của UI.

### 6.2 Locale.ROOT dùng lúc nào?

`Locale.ROOT` là locale trung lập ngôn ngữ, thường hợp lý cho chuẩn hóa tên **kỹ thuật** như protocol tokens/identifiers khi spec yêu cầu case-insensitive chuẩn đơn giản. Ví dụ `"TITLE".toLowerCase(Locale.ROOT)` trả `"title"`; Turkish locale có quy tắc riêng cho `I`/`i`, nên `toLowerCase(Locale.getDefault())` có thể tạo key khác.

**Ranh giới:** `Locale.ROOT` không thay thế một bộ thuật toán Unicode case folding/normalization đầy đủ. Với username/identifier đa ngôn ngữ, validation phải theo **protocol/security spec**, tránh tự suy ra case normalization là phép so sánh Unicode an toàn cho mọi ngôn ngữ.

### 6.3 NumberFormat và DateTimeFormatter

- `NumberFormat.getNumberInstance(Locale.US)` có thể hiển thị `1234.5` là `1,234.5`.
- `NumberFormat.getNumberInstance(Locale.GERMANY)` thường hiển thị `1.234,5`.
- `DateTimeFormatter.ofPattern("MMMM", Locale.US)` dùng tên tháng tiếng Anh.
- `DateTimeFormatter.ofPattern("MMMM", Locale.forLanguageTag("vi-VN"))` dùng tên tháng theo locale tiếng Việt.
- `DateTimeFormatter.withZone(ZoneId.of(...))` xác định zone; **không đồng nghĩa Locale**.

`NumberFormat`/`DecimalFormat` mutable, không dùng chung giữa threads mà không đồng bộ. `DateTimeFormatter` immutable và thread-safe, phù hợp tái sử dụng nếu định dạng/zone đã rõ. Với unit test multi-JDK, nội dung localized text có thể đổi theo **CLDR/locale data update**; chỉ assert chính xác chuỗi dịch khi đó là hợp đồng API cần kiểm chứng, còn test business value nên kiểm tra semantic equivalence.

## 7. Demo chạy được 2 — locale, Turkish case, số và timezone

Chương trình chủ động tạo các `Locale` và `ZoneId`, không đọc hay thay đổi default locale. Test có date/time cố định để chạy bất kể ngày hiện tại, máy CI và múi giờ OS.

Lưu thành **`LocaleExplicitDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleExplicitDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;
        Locale de = Locale.GERMANY;
        Locale tr = Locale.forLanguageTag("tr-TR");
        Locale vi = Locale.forLanguageTag("vi-VN");

        NumberFormat usNumber = NumberFormat.getNumberInstance(us);
        NumberFormat deNumber = NumberFormat.getNumberInstance(de);
        usNumber.setMinimumFractionDigits(1);
        usNumber.setMaximumFractionDigits(1);
        deNumber.setMinimumFractionDigits(1);
        deNumber.setMaximumFractionDigits(1);
        System.out.println("us-number=" + usNumber.format(1234.5));
        System.out.println("de-number=" + deNumber.format(1234.5));

        String key = "TITLE";
        System.out.println("root-normalized="
                + key.toLowerCase(Locale.ROOT));
        System.out.println("turkish-lower-different="
                + !key.toLowerCase(tr).equals(
                        key.toLowerCase(Locale.ROOT)));

        LocalDate calendarDate = LocalDate.of(2026, 11, 7);
        DateTimeFormatter monthEnglish =
                DateTimeFormatter.ofPattern("MMMM", us);
        DateTimeFormatter monthVietnamese =
                DateTimeFormatter.ofPattern("MMMM", vi);
        System.out.println("month-us=" + monthEnglish.format(calendarDate));
        System.out.println("month-vi=" + monthVietnamese.format(calendarDate));

        DateTimeFormatter fixedZone =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.ROOT)
                        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("zone-explicit="
                + fixedZone.format(Instant.parse(
                        "2026-11-07T08:15:00Z")));
        System.out.println("root-decimal="
                + String.format(Locale.ROOT, "%.2f", new BigDecimal("2.5")));
        System.out.println("de-decimal="
                + String.format(de, "%.2f", new BigDecimal("2.5")));

        if (!"1,234.5".equals(usNumber.format(1234.5))
                || !"1.234,5".equals(deNumber.format(1234.5))
                || !"title".equals(key.toLowerCase(Locale.ROOT))
                || key.toLowerCase(tr).equals(key.toLowerCase(Locale.ROOT))
                || !"2026-11-07 15:15 +07:00".equals(
                        fixedZone.format(
                                Instant.parse("2026-11-07T08:15:00Z")))) {
            throw new AssertionError("Locale formatting mismatch");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 -encoding UTF-8 LocaleExplicitDemo.java
java LocaleExplicitDemo
```

**Stdout trên runtime đã kiểm chứng:**

```text
us-number=1,234.5
de-number=1.234,5
root-normalized=title
turkish-lower-different=true
month-us=November
month-vi=tháng 11
zone-explicit=2026-11-07 15:15 +07:00
root-decimal=2.50
de-decimal=2,50
```

Giải thích:

1. Một giá trị toán học `1234.5` cho hai biểu diễn ký tự khác nhau, nên không parse số từ UI locale như một chuỗi bất biến của API máy đọc.
2. `turkish-lower-different=true` chứng minh dùng `String.toLowerCase()` không chỉ rõ locale có thể nguy hiểm cho identifiers.
3. `month-vi=tháng 11` là localized display hiện tại; nội dung dịch tháng có thể phụ thuộc dữ liệu locale của bản JDK.
4. `zone-explicit` chuyển `2026-11-07T08:15:00Z` sang múi giờ Việt Nam `+07:00`, không cần gọi `TimeZone.setDefault`.
5. `String.format(Locale.ROOT,"%.2f",...)` tạo `2.50`, còn German locale dùng `2,50`. Không dựa vào `Locale.getDefault()` trong một assertion cần ổn định qua nhiều máy.

**Tách contract khỏi hiển thị:** Nếu API contract yêu cầu `2026-11-07T08:15:00Z`, nên so theo `Instant.parse(...)` hoặc `OffsetDateTime` thay vì so string hiển thị của một múi giờ tuỳ locale. Khi kiểm tra UX localized, có thể cố tình so chuỗi sau khi pin phiên bản dữ liệu localization.

## 8. Charset: chuỗi Java khác bytes trên mạng/tệp

`String` ở Java biểu diễn các ký tự Unicode theo cơ chế JVM, nhưng khi đi qua file, HTTP body, network hoặc chữ ký số, dữ liệu phải được **encode thành bytes**. `Charset` xác định mapping giữa characters và bytes.

### 8.1 Java 11 và sự thay đổi từ Java 18

**Trong Java 11** và các JDK trước Java 18, **default charset có thể phụ thuộc OS/locale/cấu hình khởi động**, đặc biệt trên Windows với các code pages khác nhau. Vì thế `new String(bytes)`, `string.getBytes()`, `new InputStreamReader(stream)` mà **không truyền Charset** có thể cho kết quả khác giữa môi trường.

Từ **Java 18**, **JEP 400** quy định UTF-8 là default charset của các Java SE APIs trong điều kiện mặc định. Đây là thay đổi hiện hành cần biết khi nâng JDK, **không phải lý do để bỏ chỉ định encoding cho dữ liệu qua biên API**. Các chế độ tương thích/vận hành khác có thể vẫn làm khác kết quả; source code rõ contract hơn khi truyền charset.

```java
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Đây là trích đoạn; cần import `StandardCharsets` và có biến `value`. Khi gửi HTTP, cần đặt header đúng (`Content-Type: application/json; charset=UTF-8` nếu contract yêu cầu) và kiểm tra bytes thực tế. JSON interop hiện đại nên dùng UTF-8 theo protocol; không tự encode ISO-8859-1 vì default hệ điều hành.

**Lưu ý ngoại lệ có ích:** `Files.newBufferedReader(Path)` và `Files.newBufferedWriter(Path,...)` của `java.nio.file.Files` đã dùng UTF-8 khi không truyền charset theo contract Java 11; dù vậy, truyền `StandardCharsets.UTF_8` rõ ràng giúp review code thống nhất và tránh nhầm sang `FileReader`/`InputStreamReader` vốn có quy tắc khác.

### 8.2 Strict decoding so với replacement

Một số API giải mã có thể thay chuỗi byte malformed bằng ký tự replacement (như `�`) thay vì ném lỗi, dẫn tới mất dữ liệu âm thầm. Khi kiểm chứng payload phải tuân thủ UTF-8 nghiêm ngặt, dùng:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
CharBuffer characters = decoder.decode(ByteBuffer.wrap(bytes));
```

Đây là **trích đoạn**, cần import `CharsetDecoder`, `CodingErrorAction`, `StandardCharsets`, `CharBuffer`, `ByteBuffer`, có biến `bytes`. Với bytes không hợp lệ, `decode` ném `CharacterCodingException`; chương trình phải quyết định reject/report lỗi input thay vì âm thầm đổi nội dung. Với API nhận raw bytes để kiểm chứng chữ ký/hash, **kiểm bytes gốc trước khi chuyển đổi**.

### 8.3 UTF-8 BOM, line endings và tệp cấu hình

- UTF-8 BOM không bắt buộc; một số parser giữ BOM như ký tự đầu tiên, một số bỏ. Không thêm/bỏ BOM tùy ý nếu contract yêu cầu exact bytes.
- `System.lineSeparator()` trả newline theo môi trường; với protocol/file format quy định `\n` hoặc `\r\n`, hãy dùng đúng ký tự hợp đồng.
- `Properties.load(InputStream)` sử dụng mã hóa theo quy định **ISO-8859-1** với escape sequences; khi cần file properties UTF-8 và dùng `Properties`, có thể mở bằng `InputStreamReader(..., StandardCharsets.UTF_8)` rồi gọi `load(Reader)`. Không suy rằng mọi Java properties parser đều đọc UTF-8 vì Java 18 đổi default charset.
- `Files.writeString/readString` có trên Java 11 và có overload nhận `Charset`; với file cấu hình quan trọng, truyền `StandardCharsets.UTF_8` tường minh.
- Dữ liệu được ghép/chữ ký số phải xác định normalization/newline/charset để hai phía tạo **cùng byte sequence**. Locale không thay thế charset, và charset không thay thế việc chọn normalization/hợp đồng.

## 9. Demo chạy được 3 — UTF-8, malformed bytes và đóng tài nguyên

Demo này:

1. Tạo temporary directory riêng cho một lần test.
2. Ghi text chứa dấu tiếng Việt, dấu gạch ngang và tiếng Nhật bằng `BufferedWriter` với UTF-8 tường minh.
3. Đọc lại bằng `BufferedReader` UTF-8, kiểm tra nội dung và EOF.
4. Dùng `InputStream.transferTo(OutputStream)` (có từ Java 9) để copy bytes và so sánh chính xác hai tệp.
5. Giải mã dãy bytes UTF-8 malformed bằng `CodingErrorAction.REPORT` và yêu cầu exception.
6. Đóng streams bằng `try-with-resources` rồi xóa file/thư mục test; không leak file handles.

Lưu thành **`CharsetResourcesDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class CharsetResourcesDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("java11-encoding-");
        Path original = dir.resolve("unicode.txt");
        Path copy = dir.resolve("copy.txt");
        String message = "Tiếng Việt – café – 日本語";
        boolean readAfterClose = false;
        boolean copiedExactly = false;

        try {
            try (BufferedWriter writer = Files.newBufferedWriter(
                    original, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                writer.write(message);
                writer.newLine();
                writer.write("Line two");
            }

            try (BufferedReader reader = Files.newBufferedReader(
                    original, StandardCharsets.UTF_8)) {
                readAfterClose = message.equals(reader.readLine())
                        && "Line two".equals(reader.readLine())
                        && reader.readLine() == null;
            }

            long bytesCopied;
            try (InputStream input = Files.newInputStream(original);
                 OutputStream output = Files.newOutputStream(
                         copy, StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE)) {
                bytesCopied = input.transferTo(output); // Java 9+
            }
            copiedExactly = bytesCopied == Files.size(original)
                    && Arrays.equals(Files.readAllBytes(original),
                                     Files.readAllBytes(copy));

            byte[] brokenUtf8 = {(byte) 0xC3, (byte) 0x28};
            boolean malformedRejected = false;
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(brokenUtf8));
            } catch (CharacterCodingException expected) {
                malformedRejected = true;
            }

            System.out.println("utf8-roundtrip=" + readAfterClose);
            System.out.println("stream-copy-exact=" + copiedExactly);
            System.out.println("malformed-utf8-rejected="
                    + malformedRejected);
            System.out.println("utf8-alias="
                    + java.nio.charset.Charset.forName("utf8")
                            .equals(StandardCharsets.UTF_8));
            System.out.println("default-charset-is-used=false");

            if (!readAfterClose || !copiedExactly || !malformedRejected) {
                throw new AssertionError("Charset/resource test failed");
            }
        } finally {
            Files.deleteIfExists(copy);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
        System.out.println("temporary-directory-deleted="
                + Files.notExists(dir));
    }
}
```

Chạy:

```bash
javac --release 11 -encoding UTF-8 CharsetResourcesDemo.java
java CharsetResourcesDemo
```

**Stdout đã kiểm chứng:**

```text
utf8-roundtrip=true
stream-copy-exact=true
malformed-utf8-rejected=true
utf8-alias=true
default-charset-is-used=false
temporary-directory-deleted=true
```

**Giải thích:** `utf8-roundtrip=true` chỉ chứng minh text test được giữ chính xác khi cả hai phía dùng UTF-8. `stream-copy-exact=true` là so bytes, không phải chỉ so chuỗi. `malformed-utf8-rejected=true` xác nhận decoder ném lỗi thay vì thay thế dữ liệu. Dòng `default-charset-is-used=false` mô tả source test chủ động chỉ định charset; nó không đo `Charset.defaultCharset()` của toàn JVM.

**Đừng dùng `Files.readAllBytes` để copy file cực lớn trong production**: demo gọi nó chỉ để xác minh fixture nhỏ. Khi API cần xử lý body/file lớn, dùng streaming và đặt giới hạn byte. `InputStream.transferTo` có thể sao chép dữ liệu đến EOF, nên nếu input không tin cậy cần thêm quota/giới hạn để tránh tiêu thụ disk không kiểm soát.

## 10. Tài nguyên hệ thống: vòng đời là một phần của hợp đồng API

Một integration test ổn định phải quản lý cả **streams, sockets, files, background threads, process và HTTP connections**. Dùng `try-with-resources` cho loại `AutoCloseable`:

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
```

Đây là trích đoạn, cần `source/target` hợp lệ. Java 11 `InputStream.transferTo` là API công khai còn phù hợp, không cần API nội bộ.

| Resource | Quy tắc Java 11 | Dấu hiệu test lỗi |
|---|---|---|
| File input/output stream | `try-with-resources` | File bị khóa, FD/handle leak |
| BufferedReader/Writer | `try-with-resources`, flush khi cần | Output thiếu cuối, file không xóa được |
| SSLSocket/Socket/ServerSocket | `try-with-resources` + connect/read timeout | Test treo, port bận, handshake pending |
| HttpResponse.BodyHandlers.ofInputStream | **Đóng InputStream body** sau khi đọc | Connection/resource chưa được release |
| `HttpClient` Java 11 | Tái sử dụng, quản lý lifecycle bằng thiết kế client | Tạo quá nhiều clients/connections/executors |
| ExecutorService | `shutdown`/`awaitTermination`, fallback `shutdownNow` | Thread sống sau test |
| Process từ ProcessBuilder | `waitFor(timeout,unit)`, destroy khi timeout | Child JVM zombie/hanging |
| `Files.list/walk/lines` streams | Close `Stream` bằng try-with-resources | Mở file/directory handles quá lâu |
| Temp files/directories | Tạo tên riêng, cleanup `finally` | Test không idempotent, disk đầy |
| CharsetDecoder/DateTimeFormatter | Không có file handle | Dùng đúng contract/thread-safety |

**Version-specific:** `HttpClient` trong **Java 11** **chưa** có lifecycle `close()`/`AutoCloseable` kiểu JDK mới; không viết `try (HttpClient c = ...)` trong bài hướng Java 11. Nó vẫn quản lý connections nội bộ; tạo client theo lifecycle hợp lý và đóng **response InputStream** nếu dùng streaming body. Tương tự, `ExecutorService` Java 11 **không được sử dụng như một AutoCloseable resource**; phải shutdown và await, không viết `try (ExecutorService e=...)` dựa vào API JDK đời sau.

### 10.1 Timeouts không phải lựa chọn tùy ý

- `HttpClient.Builder.connectTimeout(Duration)` giới hạn thời gian kết nối.
- `HttpRequest.Builder.timeout(Duration)` giới hạn request timeout phù hợp.
- `Socket.setSoTimeout` giới hạn thời gian blocking read trên socket.
- `Process.waitFor(timeout, TimeUnit)` tránh test treo vô thời hạn.
- Server test nên chọn **ephemeral port** (bind port 0), không hardcode 8080/8443 và gây xung đột CI.
- Với việc tải/ghi response dài, phải giới hạn **số bytes, thời gian và tốc độ**, không chỉ timeout mở kết nối.

Khi timeout xảy ra, test phải **cleanup** worker, file và socket, báo lỗi rõ. Không coi “đợi đủ lâu” là giải pháp chuẩn cho race/concurrency hoặc dependency không phản hồi.

### 10.2 Temp paths và bảo mật

- Dùng `Files.createTempDirectory`/`createTempFile` để tên riêng, tránh tên file cố định bị ghi đè bởi test khác.
- Đóng streams trước khi `Files.deleteIfExists`, nhất là trên Windows nơi file đang mở thường không thể xóa.
- Không nối đường dẫn từ user input không tin cậy rồi viết vào hệ thống tệp; tránh path traversal và symlink attacks bằng validation/policy.
- Khi tạo temp files chứa key/cert/response nhạy cảm, đặt permissions phù hợp, dọn sau test và không upload vào artifact công khai.
- Đừng thay đổi `System.setProperty("java.io.tmpdir",...)` giữa test rồi giả định mọi JDK API sẽ chuyển thư mục tạm ngay lập tức; chọn directory rõ ràng trong test.

## 11. Process-global configuration và test isolation

Ngoài TLS default context, các cấu hình sau thường có tác dụng rộng trong JVM:

| API/Property | Phạm vi ảnh hưởng |
|---|---|
| `Locale.setDefault(...)` | Default locale của **process**, có thể ảnh hưởng nhiều threads |
| `Locale.setDefault(Locale.Category.FORMAT,...)` | Default định dạng của process |
| `TimeZone.setDefault(...)` | Default time zone của process |
| `System.setProperty("user.language",...)` | Property process-wide, không bảo đảm mọi object đã cache sẽ cập nhật |
| `System.setProperty("file.encoding",...)` | Không phải cách portable để đổi charset default đã khởi tạo |
| `System.setProperty("javax.net.ssl.trustStore",...)` | Có thể ảnh hưởng default JSSE contexts mới, nhưng cache/old contexts vẫn tồn tại |
| `SSLContext.setDefault(...)` | Thay đổi default SSL context toàn JVM |
| `System.setOut(...)` | Global stdout, có thể ảnh hưởng test/song song |
| `Security.setProperty(...)` | Ảnh hưởng security algorithms/JCA policy rộng |

Nếu test cần mô phỏng môi trường hệ thống khác, cách sạch hơn là **spawn JVM riêng** với process/system properties phù hợp. Dùng `ProcessBuilder` với **arguments riêng biệt**, không ghép command shell từ chuỗi người dùng. Trong cùng process, truyền `Locale`, `ZoneId`, `Charset`, `SSLContext` vào các component thay vì dựa vào defaults.

### 11.1 Ví dụ vì sao restore default chưa đủ

```java
Locale original = Locale.getDefault();
try {
    Locale.setDefault(Locale.GERMANY);
    // Test something.
} finally {
    Locale.setDefault(original);
}
```

Đây là một đoạn code **có cleanup nhưng vẫn là anti-pattern cho parallel test**: thread khác có thể định dạng dữ liệu đúng vào khoảng default German đang bật, hoặc thư viện có thể cache formatter/locale trong thời gian đó. Dùng child JVM hoặc dependency injection; nếu bắt buộc sửa global state, test phải chạy serial và được bảo vệ bởi test isolation phù hợp.

## 12. Demo chạy được 4 — cô lập Locale và System properties bằng child JVM

Ví dụ tạo một child Java process bằng `ProcessBuilder`. Child thay `Locale.setDefault(Locale.FRANCE)` và một system property có tên test. Parent chờ tối đa 15 giây, đọc output nhỏ, kiểm tra child thực sự thay state của **child**, nhưng locale/property của parent vẫn không đổi.

Lưu thành **`SystemResourceIsolationDemo.java`**:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class SystemResourceIsolationDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "child".equals(args[0])) {
            Locale.setDefault(Locale.FRANCE); // changes this process globally
            System.setProperty("training.api.mode", "child-only");
            System.out.println("child-locale="
                    + Locale.getDefault().toLanguageTag());
            System.out.println("child-property="
                    + System.getProperty("training.api.mode"));
            return;
        }

        Locale parentLocale = Locale.getDefault();
        String parentProperty =
                System.getProperty("training.api.mode");

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("windows");
        Path javaExecutable = Paths.get(System.getProperty("java.home"),
                "bin", windows ? "java.exe" : "java");
        ProcessBuilder builder = new ProcessBuilder(
                javaExecutable.toString(),
                "-cp", System.getProperty("java.class.path"),
                SystemResourceIsolationDemo.class.getName(), "child");
        builder.redirectErrorStream(true);
        Process child = builder.start();
        child.getOutputStream().close();

        boolean finished = child.waitFor(15, TimeUnit.SECONDS);
        if (!finished) {
            child.destroyForcibly();
            child.waitFor();
            throw new IllegalStateException("Child JVM exceeded 15 seconds");
        }
        String output;
        try (InputStream stream = child.getInputStream()) {
            output = new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8);
        }

        boolean childSucceeded = child.exitValue() == 0;
        boolean childLocale = output.contains("child-locale=fr-FR");
        boolean childProperty = output.contains(
                "child-property=child-only");
        boolean unchangedLocale =
                Locale.getDefault().equals(parentLocale);
        boolean unchangedProperty =
                java.util.Objects.equals(parentProperty,
                        System.getProperty("training.api.mode"));

        System.out.println("child-exit-zero=" + childSucceeded);
        System.out.println("child-locale-updated=" + childLocale);
        System.out.println("child-property-updated=" + childProperty);
        System.out.println("parent-locale-unchanged=" + unchangedLocale);
        System.out.println("parent-property-unchanged=" + unchangedProperty);
        if (!childSucceeded || !childLocale || !childProperty
                || !unchangedLocale || !unchangedProperty) {
            throw new AssertionError("Global state leaked between processes");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 -encoding UTF-8 SystemResourceIsolationDemo.java
java SystemResourceIsolationDemo
```

**Stdout đã kiểm chứng:**

```text
child-exit-zero=true
child-locale-updated=true
child-property-updated=true
parent-locale-unchanged=true
parent-property-unchanged=true
```

**Giải thích:** `ProcessBuilder` tìm binary `java` trong `java.home/bin`, dùng cùng classpath hiện tại và chạy class với argument `child`. Chỉ child gọi `Locale.setDefault`/`System.setProperty`; parent so lại với giá trị ban đầu. Đây là phép thử *isolation* đáng tin hơn so với kiểm tra có restore đúng property trong cùng JVM khi các test chạy parallel.

**Giới hạn demo:** Child chỉ in vài dòng nên parent chờ exit rồi `InputStream.readAllBytes()` không bị đầy pipe buffer. Trong production, **đọc/redirect stdout và stderr đồng thời** nếu child có thể in nhiều dữ liệu, không đợi child exit với pipe đầy; có thể dùng `ProcessBuilder.redirectOutput/redirectError` vào file temp được quản lý và theo dõi size. `Process.waitFor(timeout)` phải đi cùng `destroyForcibly()` và cleanup nếu child treo; đo process exit code, không dựa vào message substring tùy ý khi output protocol phức tạp.

## 13. Kiểm chứng API HTTP: locale, charset và stream body

Java 11 có HTTP Client công khai tại `java.net.http`:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(4))
        .build();

HttpRequest request = HttpRequest.newBuilder(URI.create(url))
        .header("Accept-Language", "vi-VN")
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
try (InputStream body = response.body()) {
    // Decode response theo Content-Type/charset contract.
}
```

Đây là **trích đoạn**, cần imports `HttpClient`, `HttpRequest`, `HttpResponse`, `InputStream`, `Duration`, `URI` và biến `url`. `HttpClient` không tự suy ra locale của người gọi để thêm `Accept-Language` theo business contract; test phải đặt header nếu service yêu cầu. Và `BodyHandlers.ofInputStream` giao trách nhiệm **đọc/đóng body** cho caller.

### 13.1 Demo chạy được 5 — local HTTP API không cần mạng ngoài

Demo cuối sử dụng `jdk.httpserver` (module có trong JDK 11) để dựng server chỉ lắng nghe trên `127.0.0.1` ở port động. API trả `Content-Type: text/plain; charset=UTF-8` và body `Xin chào – locale=vi-VN`. Client Java 11 gửi `Accept-Language: vi-VN`, có timeout và đóng response body stream trước khi dừng server.

Lưu thành **`ApiHttpLocalDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;

public class ApiHttpLocalDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 4);
        server.createContext("/hello", exchange -> {
            String language = exchange.getRequestHeaders()
                    .getFirst("Accept-Language");
            String text = "Xin chào – locale=" + language;
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream response = exchange.getResponseBody()) {
                response.write(bytes);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(4))
                    .build();
            URI url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/hello");
            HttpRequest request = HttpRequest.newBuilder(url)
                    .header("Accept-Language",
                            Locale.forLanguageTag("vi-VN").toLanguageTag())
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<InputStream> result = client.send(request,
                    HttpResponse.BodyHandlers.ofInputStream());

            String payload;
            try (InputStream body = result.body()) {
                payload = new String(body.readAllBytes(),
                        StandardCharsets.UTF_8);
            }

            boolean typeMatches = "text/plain; charset=UTF-8".equals(
                    result.headers().firstValue("Content-Type")
                            .orElse(""));
            boolean bodyMatches =
                    "Xin chào – locale=vi-VN".equals(payload);
            System.out.println("http-status=" + result.statusCode());
            System.out.println("explicit-charset-response="
                    + typeMatches);
            System.out.println("explicit-locale-request=true");
            System.out.println("utf8-payload-matches=" + bodyMatches);
            System.out.println("body-stream-closed=true");
            if (result.statusCode() != 200 || !typeMatches
                    || !bodyMatches) {
                throw new AssertionError("Local API contract mismatch");
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 ApiHttpLocalDemo.java
java --add-modules jdk.httpserver ApiHttpLocalDemo
```

**Stdout đã kiểm chứng:**

```text
http-status=200
explicit-charset-response=true
explicit-locale-request=true
utf8-payload-matches=true
body-stream-closed=true
```

**Đọc kết quả:** `http-status=200` xác nhận status, nhưng API contract còn kiểm `Content-Type`, locale đưa trong request, **bytes UTF-8 của response body** và việc stream đã được đóng. Dòng `explicit-locale-request=true` trong demo mô tả thao tác tạo request tường minh; giá trị tiếng Việt xuất hiện trong body giúp xác nhận server nhận header và phản hồi phù hợp.

**Không biến server fixture thành server production:** `com.sun.net.httpserver.HttpServer` là API công khai trong module `jdk.httpserver`, rất tiện cho test local, nhưng chương trình minh họa cố ý tối giản, không có authentication, throttling, request size limit hay logging policy cho môi trường Internet. Nó chỉ bind loopback, không expose ra public network.

### 13.2 Từ HTTP local đến HTTPS production

Đối với API HTTPS thực, thêm:

- `HttpClient.newBuilder().sslContext(customContext)` với `TrustManagerFactory` được khởi tạo từ truststore phù hợp.
- Để default TLS/hostname verification hoạt động, không dùng property “disable hostname verification”.
- Điều khiển redirect và target host để không vô tình gửi Authorization header/credential đến origin khác.
- Đảm bảo body charset/schema theo Content-Type/JSON contract và xử lý errors đúng status.
- Timeout và bounded body processing; với body lớn dùng stream/JSON parser streaming thay vì `readAllBytes`.
- Server test qua localhost certificate SAN đã được kiểm chứng trong demo TLS; không dùng certificate test vừa tạo trong môi trường production.

## 14. Quản lý truststore như tài nguyên của deployment

### 14.1 Nguồn cert và quản lý trust

Một truststore production nên chứa **chỉ trust anchors được phê duyệt**. Quy trình quản lý:

1. Lấy CA/root/intermediate certificate theo kênh chính thức, xác minh fingerprint/chain với nguồn độc lập.
2. Lưu truststore ở vị trí phù hợp, không đè trực tiếp lên `cacerts` trong JDK image nếu không có chiến lược quản lý nâng cấp.
3. Đặt file permissions tối thiểu, bảo vệ secret, kiểm soát mount/volume trong container.
4. Kiểm tra certificate expiry/algorithm constraints và kế hoạch rotation trước thời hạn.
5. Tạo truststore mới/SSLContext mới khi cập nhật, kiểm tra handshake, chỉ sau đó chuyển client/connection pool sang trust policy mới.
6. Không trộn dev/test CA với production CA một cách mặc định.
7. Log **metadata không nhạy cảm** (alias/count/certificate fingerprints nếu policy cho phép), không log private key/password hay raw token.
8. Với mTLS, quản lý identity keystore và truststore riêng, có key/permission lifecycle độc lập.

**Password của truststore không đồng nghĩa encryption bảo vệ private key** — truststore có thể chỉ chứa public certs, password thường dùng cho file integrity. Identity keystore có private key nhạy cảm hơn nhiều và đòi hỏi bảo mật mạnh. Không lấy lý do “chỉ là test cert” để commit private key production lên Git.

### 14.2 Test truststore path lỗi sớm

Nếu cấu hình path riêng, kiểm tra file tồn tại/đọc được ở bước setup và khi `KeyStore.load`, thay vì để request đầu tiên đi ra ngoài rồi mới báo lỗi PKIX khó truy vết. Với file bị thay đổi trong lúc chạy, phải có cơ chế reload có kiểm soát, tránh đọc một phần file đang được ghi. Một cách vận hành là **atomic swap** tệp cấu hình mới tại cùng filesystem nơi hỗ trợ, sau đó tạo client/context mới.

Không dựa vào việc một client Java tự theo dõi và cập nhật truststore khi file trên disk thay đổi. SSL sessions/connection pools có thể tiếp tục dùng trạng thái cũ; đo, test và triển khai lifecycle rõ.

### 14.3 Chẩn đoán TLS nhưng không lộ bí mật

Trên SunJSSE/HotSpot, có thể dùng logging thử nghiệm như:

```bash
java -Djavax.net.debug=ssl,handshake YourApplication
```

Đây là **mẫu lệnh**, chưa phải chương trình đầy đủ. TLS debug logs có thể rất lớn và chứa thông tin nội bộ như hostnames, certificates, session metadata. Chỉ bật trong môi trường kiểm soát, giới hạn thời gian và retention, redact trước khi chia sẻ. Không bật logging TLS chi tiết thường trực trên production chỉ để thấy lỗi.

Phân loại lỗi thường gặp:

| Thông báo/nhóm lỗi | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| `PKIX path building failed` | CA/cert thiếu, chain không hợp lệ | Truststore đúng file và CA được phép |
| `No subject alternative DNS name matching` | SAN không khớp hostname | Expected peer hostname và cert SAN |
| `Keystore was tampered with, or password was incorrect` | Sai password/type hoặc dữ liệu hỏng | Keystore format, secret, checksum, provider |
| `No such file`/`AccessDenied` | Sai path/quyền | Filesystem/mount/permissions |
| `handshake_failure` | Cert, auth, protocol hoặc cipher mismatch | SSL debug, provider and TLS policy |
| `certificate expired` | Hết hạn | Rotation/certificate validity |
| Kết nối treo | Không có timeout/dependency không trả lời | Connect/read/request timeout và process budget |

Thông điệp có thể khác nhau theo JDK/provider, nên test nên kiểm **loại lỗi/behavior** chứ không hardcode nguyên văn exception message.

## 15. Portability: Java 11 so với JDK đời mới

| Chủ đề | Java 11 | Java hiện đại | Hướng làm bền |
|---|---|---|---|
| Charset mặc định | Có thể khác theo OS/locale/startup | JEP 400: UTF-8 default từ Java 18 | Truyền `StandardCharsets.UTF_8` |
| Keystore mặc định | PKCS12 theo JEP 229 | PKCS12 tiếp tục phổ biến | Ghi rõ type khi load |
| Truststore mặc định | JSSE properties/jssecacerts/cacerts | Phụ thuộc VM/image/provider | Dùng per-app truststore/context khi cần |
| TLS | JSSE hỗ trợ TLS 1.3 trong Java 11 | Cấu hình security/algorithms thay đổi qua JDK | Không hardcode cipher yếu, test handshake |
| Locale data | Dữ liệu CLDR của JDK/vendor | Có thể được cập nhật | Pin locale và test semantic |
| Zone rules | tzdb của JDK | Có thể cập nhật | Dùng `ZoneId` rõ ràng, test dates có chủ đích |
| HttpClient | Java 11 API, không có AutoCloseable | Một số API lifecycle mở rộng sau này | Viết theo baseline thực tế |
| Resource streams | `AutoCloseable` phổ biến | Vẫn được áp dụng | try-with-resources |
| ExecutorService | Shutdown thủ công trong Java11 | Có APIs mới ở các JDK mới | Shutdown/await cho Java11 |
| System properties | Process-global | Vẫn là process-global | Inject config hoặc child JVM |

**Đừng viết test “chỉ pass nếu default charset UTF-8”** cho codebase Java 11 phục vụ nhiều môi trường, trừ khi đó là **precondition có chủ đích** được áp dụng ở runtime. Điều bền vững hơn là không lệ thuộc default khi encoding protocol/file đã xác định. Mặt khác, khi nâng lên Java 18+, phải test các đoạn code cũ dùng default charset vì behavior có thể thay đổi; đây là một kiểm chứng tương thích quan trọng hiện nay.

### 15.1 Locale có thể ảnh hưởng parse nhưng không nên ảnh hưởng numeric JSON

Theo JSON, decimal separator là dấu chấm, không phụ thuộc locale UI. Nếu chương trình dùng `String.format(Locale.GERMANY, "%.2f",value)` để dựng JSON number, nó có thể tạo `2,50` thay cho `2.50` và khiến JSON sai. Dùng JSON serializer đúng chuẩn hoặc API numeric serialization locale-independent; không tự ghép response JSON từ text đã localized.

### 15.2 Time zone và clock phải là dependency có kiểm soát

Kiểm chứng API có timestamp nên dùng `Clock.fixed(Instant, ZoneId)` hoặc truyền `Clock` vào code test được, thay vì giả định `LocalDateTime.now()` trả thời điểm giống nhau trên mọi máy. `Instant` phù hợp mốc thời gian tuyệt đối, `OffsetDateTime`/`ZonedDateTime` phù hợp khi contract có offset/zone. Không gọi `TimeZone.setDefault` trong test song song để “làm ổn” timestamp.

### 15.3 Dòng lệnh và console encoding

Console/terminal trên Windows và Linux có thể hiển thị Unicode khác nhau tùy encoding và locale dù byte file đúng. Khi test API, ưu tiên so **Unicode strings** hoặc **bytes UTF-8** nhận từ I/O, không dùng cách console render một ký tự làm oracle duy nhất. Biên dịch bằng `javac -encoding UTF-8` và chọn file encodings rõ ràng. Java 11 có JDK-specific console behavior; không tự suy từ `Charset.defaultCharset()` rằng mọi console đều dùng cùng encoding.

## 16. Checklist trước khi chạy test API

- **Trust material:** file truststore đúng, type rõ, password/permissions đúng, test cert còn hạn, SAN chính xác.
- **TLS:** xác minh chain và hostname, test cả reject cases, không tắt validation.
- **Locale:** locale dùng trong request và number/date formatting được truyền tường minh.
- **Time zone/clock:** ZoneId và thời điểm test cố định hoặc inject Clock.
- **Charset:** byte encoding và Content-Type charset rõ; strict decoder khi cần từ chối malformed bytes.
- **File resource:** đóng InputStream/OutputStream/Reader/Writer và cleanup temp artifacts.
- **Socket resource:** loopback/port động cho test, timeout cho connect/read/handshake.
- **HTTP client:** response body được đọc/đóng, không tạo client mới mỗi request vô cớ.
- **Global state:** không mutate defaults trong parallel tests; dùng child process khi phải kiểm tra thay đổi.
- **Concurrency:** có bounded executor/queue, shutdown và await, tránh thread leak.
- **Secrets:** không in password/key/tokens hoặc đưa credential thật vào command line/test fixture.
- **Portability:** kiểm thử trên JDK/vendor/OS mục tiêu, đặc biệt charset/CLDR/tzdb và TLS defaults.
- **Assertions:** kiểm đúng behavior/status/headers/bytes và negative security cases, không phụ thuộc error message hoặc phiên bản locale text khi không phải contract.
- **Quotas:** giới hạn response bytes, thời gian, số files/processes, disk và quyền truy cập của test runner.
- **Cleanup:** kết quả test phải không phụ thuộc thứ tự chạy, có thể chạy lại, không phá state người dùng.

## 17. Ma trận QA đề xuất

| Nhóm | Kịch bản | Kết quả cần xác minh |
|---|---|---|
| TLS/truststore | PKCS12 chứa 1 localhost cert | Load thành công, cert count=1 |
| TLS/truststore | Client với truststore đúng | Handshake thành công |
| TLS/identity | Hostname không khớp SAN | Handshake bị từ chối |
| TLS/trust | Empty truststore | Bị từ chối |
| TLS/config | Path không tồn tại | Fail sớm, không trust-all/fallback không mong muốn |
| TLS/config | Wrong password | Fail load rõ |
| TLS/lifecycle | Rotation cert trong deployment | Context/client mới được tạo & test |
| TLS/security | SSLParameters hostname check | Có `HTTPS` endpoint identification |
| Locale | US/German number format | Dấu phân cách đúng theo locale |
| Locale | Turkish uppercase I | ROOT normalization khác Turkish |
| Locale | English/Vietnamese month | Dữ liệu localized theo JDK |
| Time zone | Instant fixed + Asia/Ho_Chi_Minh | Offset/thời gian rõ, không lệ thuộc system default |
| Charset | UTF-8 tiếng Việt/Japanese | Roundtrip và byte compare đúng |
| Charset | Invalid UTF-8 | Strict decoding báo lỗi |
| Charset | Default khác UTF-8 | App vẫn chạy vì truyền charset tường minh |
| Files | BufferedReader/Writer đóng | Không còn open handle, cleanup thành công |
| Files | Stream copy | Byte-for-byte equal |
| Process | Child thay Locale | Parent locale giữ nguyên |
| Process | Child thay system property | Parent property giữ nguyên |
| Process | Child treo | Timeout/kill/cleanup |
| HTTP | Local server `127.0.0.1:0` | Không đụng Internet/port cứng |
| HTTP | Accept-Language vi-VN | Server đọc header đúng |
| HTTP | Content-Type UTF-8 | Client kiểm đúng response metadata |
| HTTP | UTF-8 payload | Đọc body và so Unicode đúng |
| HTTP | BodyHandlers.ofInputStream | Đóng InputStream sau đọc |
| Resources | Server/client đóng | Không tồn tại tài nguyên bỏ quên sau test |

Nếu một test thay đổi system properties rồi phải chạy độc lập mới pass, rất có thể **test isolation** chưa đủ. Nếu cùng body trả về khác nhau do default Locale/charset, hãy kiểm tra input/headers/encoding contract trước khi sửa assertion để “chạy qua”. Với lỗi TLS, đừng vô hiệu hóa validation chỉ để làm suite xanh.

## 18. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Thực hành đúng |
|---|---|---|
| Nhầm keystore identity với truststore | Có key pair nhưng không tin peer | Phân biệt KeyManager và TrustManager |
| Set trustStore path sai nhưng tin sẽ fallback `cacerts` | Có thể dùng truststore rỗng | Fail-fast path, validate material |
| Import mọi cert tìm thấy | Mở rộng trust anchors không kiểm soát | Xác minh fingerprint và least trust |
| Tắt hostname verification | MITM/peer spoofing | Kiểm tra SAN/HTTPS endpoint identification |
| Viết trust-all X509TrustManager | Mọi cert đều được nhận | PKIX trust manager đúng cấu hình |
| Dùng PKCS12 file nhưng mặc định ép JKS | Load lỗi/provider mismatch | Explicit `KeyStore.getInstance("PKCS12")` |
| Commit private key vào Git | Rò bí mật | Secret manager, test fixture ephemeral |
| Dùng `System.setProperty` TLS trong parallel tests | Race/cached contexts | Per-client `SSLContext` |
| Sửa truststore file và mong live clients cập nhật ngay | Kết nối giữ trust policy cũ | Quản lý rotation/context lifecycle |
| Dùng `String.toLowerCase()` cho technical keys | Turkish-I bug | `Locale.ROOT` khi hợp đồng cho phép |
| Dùng `NumberFormat` mặc định cho JSON number | Dấu phẩy sai JSON | Serializer chuẩn và locale-invariant |
| Dùng `Locale` để suy ra timezone | Date/time sai theo user | Explicit `ZoneId` |
| Chia sẻ `NumberFormat` giữa threads | Race/malformed output | Per-thread/per-call hoặc đồng bộ |
| Dùng `new String(bytes)` khi charset API cố định | Mojibake theo OS/JDK | `new String(bytes, UTF_8)` |
| Giải mã malformed UTF-8 bằng replacement mà không biết | Mất dữ liệu âm thầm | `CodingErrorAction.REPORT` khi contract yêu cầu |
| Xem JDK18 default UTF-8 là thuộc tính Java11 | Thất bại Windows/runtime cũ | Kiểm tra version hoặc chỉ định charset |
| Dùng `Properties.load(InputStream)` và nghĩ mặc nhiên UTF-8 | Đọc sai tiếng Việt | `load(Reader)` với UTF-8 rõ |
| Bỏ đóng `HttpResponse<InputStream>.body()` | Leak connection/resource | Try-with-resources |
| Dùng `try(HttpClient c=...)` theo API đời mới | Java11 không biên dịch | Lifecycle đúng baseline |
| Dùng `try(ExecutorService e=...)` trong Java11 | Java11 không có AutoCloseable contract | Shutdown/awaitTermination |
| Không timeout cho TLS/HTTP/process | CI treo vô hạn | Connect/read/request/wait timeout |
| Gắn port cố định cho integration tests | Collision giữa suites | Loopback + ephemeral port 0 |
| Không xóa temp file sau test | Rò secrets/disk/FD | Finally cleanup sau khi close |
| Gọi `Locale.setDefault` rồi restore trong parallel tests | Race vẫn xảy ra | Child JVM hoặc inject locale |
| Không kiểm soát response size | Exhaust memory/disk | Bound bytes/streaming |
| Hardcode exception message TLS | Dễ flaky giữa JDK/provider | Kiểm behavior/exception class |
| Coi Content-Type header đủ chứng minh charset | Có thể body bytes sai | So bytes và decode đúng |
| Không test negative security cases | Code tắt validation vẫn pass positive | Assert rejection của wrong host/CA |

## 19. Bài tập kèm đáp án

**Bài 1 — Truststore rỗng.** Client HTTPS Java 11 có cert SAN đúng, nhưng truststore không chứa CA cần thiết. Có nên bật HostnameVerifier luôn trả true?  
**Đáp án:** Không. Hostname verifier và trust chain là hai điều kiện riêng. Cần trust đúng CA/cert được phê duyệt, vẫn kiểm tra hostname.

**Bài 2 — Default truststore.** Trên SunJSSE, khi không khai báo `javax.net.ssl.trustStore`, JSSE tìm những file nào?  
**Đáp án:** `jssecacerts` trước, rồi `cacerts` trong `java.home/lib/security`. Nếu property được đặt tới file **không tồn tại**, có thể tạo empty truststore thay vì fallback; phải validate path.

**Bài 3 — PKCS12.** Vì sao tạo `SSLContext` riêng thay vì gọi `SSLContext.setDefault` khi nhiều test song song?  
**Đáp án:** Giảm ảnh hưởng process-global, cho phép mỗi client/test có trust policy riêng, tránh race/cache của default context.

**Bài 4 — Keystore và truststore.** Server chứa private key/cert trong identity.p12; client chỉ muốn tin certificate public của server. Nó cần file nào?  
**Đáp án:** Server dùng identity keystore; client dùng truststore chứa public certificate hoặc CA anchor đã xác minh, không cần/private key của server.

**Bài 5 — SAN.** Client trust certificate `localhost` nhưng kết nối với expectedHost `other.invalid`. Test đúng phải ra sao?  
**Đáp án:** Handshake bị từ chối do endpoint identification/hostname không khớp, dù chain được trust.

**Bài 6 — Turkish.** Vì sao `"TITLE".toLowerCase()` có thể không tạo một technical key giống nhau ở mọi máy?  
**Đáp án:** Overload không tham số sử dụng default locale, Turkish có quy tắc I khác English. Dùng `Locale.ROOT` khi spec muốn key neutral, nhưng vẫn phải theo quy tắc Unicode/protocol của ứng dụng.

**Bài 7 — Zone.** Gọi `Locale.forLanguageTag("vi-VN")` có bảo đảm giờ hiển thị là Việt Nam không?  
**Đáp án:** Không. Dùng `ZoneId.of("Asia/Ho_Chi_Minh")` hoặc offset/clock theo contract thời gian.

**Bài 8 — Java11 charset.** Tại sao `new String(bytes)` có nguy cơ khác kết quả ở Windows Java11 so với JDK18?  
**Đáp án:** Java11 default charset phụ thuộc môi trường, trong khi JEP400 chọn UTF-8 default từ Java18. Dùng charset tường minh để ổn định.

**Bài 9 — Malformed UTF8.** API yêu cầu reject bytes không phải UTF-8. Có thể dùng decoder mặc định với replacement không?  
**Đáp án:** Không nếu cần strict validation. `CodingErrorAction.REPORT` và bắt `CharacterCodingException`.

**Bài 10 — File resource.** Ghi UTF-8 rồi không close BufferedWriter trước khi đọc lại. Có nguy cơ gì?  
**Đáp án:** Chưa flush hết bytes, giữ file handle, có thể không xóa được. Dùng try-with-resources.

**Bài 11 — HttpClient.** Trong Java11, có viết `try (HttpClient client = ...)` được không?  
**Đáp án:** Không theo API Java11; quản lý lifecycle client và đóng body InputStream khi dùng `BodyHandlers.ofInputStream`.

**Bài 12 — Child process.** Vì sao test đổi `Locale.setDefault` trong child JVM đáng tin hơn test đổi rồi restore trong một test chạy song song?  
**Đáp án:** Child có process-global state riêng, thay đổi không thể bị thread test trong parent quan sát.

**Bài 13 — Content-Type.** API trả header `charset=UTF-8` nhưng body không phải bytes UTF-8 hợp lệ. Có được xem là pass không?  
**Đáp án:** Không. Kiểm cả header và payload decoding/bytes, báo lỗi contract.

**Bài 14 — Test password.** Password `local-test-only` hardcoded trong fixture có dùng như hướng dẫn quản lý secret production không?  
**Đáp án:** Không. Đây là giá trị giả cho cert tự sinh, tạm thời; secret thật phải được cấp/giữ bởi hệ thống quản lý bí mật và quyền truy cập.

**Bài 15 — Default locale.** Test A tạm đặt German locale, Test B định dạng số không truyền locale. Vì sao B có thể flaky?  
**Đáp án:** Locale default là process-wide; B có thể chạy trúng khoảng A đổi default. Truyền Locale tường minh hoặc cô lập JVM.

**Bài 16 — Timeout.** Khi subprocess test có thể in vài MB stdout, có nên chờ `waitFor` rồi mới đọc pipe?  
**Đáp án:** Không, pipe buffer có thể đầy và child bị block trước khi exit. Đọc output đồng thời, redirect file, hoặc thiết kế protocol output hữu hạn.

**Bài 17 — Certificate rotation.** Sau khi cập nhật trust.p12 trên disk, có thể chắc chắn `HttpClient` đang chạy dùng trust anchors mới không?  
**Đáp án:** Không. Quản lý SSLContext/client/connection pool lifecycle và test sau rotation.

**Bài 18 — UTF-8 default ở Files.** `Files.newBufferedReader(path)` Java11 mặc định dùng UTF-8. Vì sao vẫn truyền `StandardCharsets.UTF_8`?  
**Đáp án:** Làm rõ contract khi review, tránh nhầm với các API khác dùng default charset, và giúp test intent nhất quán.

## 20. Tài liệu chuẩn và nguồn kiến thức còn áp dụng

- [Java SE 11 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/11/security/java-secure-socket-extension-jsse-reference-guide.html): default truststore lookup, SSLContext, SunJSSE properties, TLS authentication.
- [Java SE 11 — SSLContext](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLContext.html): tạo custom TLS context.
- [Java SE 11 — SSLParameters](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm` và hostname verification.
- [Java SE 11 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): khởi tạo trust manager.
- [Java SE 11 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): server/client identity.
- [Java SE 11 — KeyStore](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/KeyStore.html): load PKCS12, keystore entries.
- [JEP 229 — Create PKCS12 Keystores by Default](https://openjdk.org/jeps/229): default keystore type từ Java9.
- [Java SE 11 — Locale](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Locale.html): Locale.ROOT, forLanguageTag, default locale.
- [Java SE 11 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/time/format/DateTimeFormatter.html): locale và zone của time formatting.
- [Java SE 11 — Charset](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/Charset.html), [StandardCharsets](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html), [CharsetDecoder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetDecoder.html): UTF-8, aliases và decoding.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi từ Java18, điểm cần test khi nâng Java11 lên phiên bản mới.
- [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): charset rõ, temp files, file streams và resource lifecycle.
- [Java SE 11 — ProcessBuilder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/ProcessBuilder.html): subprocess isolation.
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html), [HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html), [HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): thời gian chờ, locale headers, streaming response.
- [Java SE 11 — AutoCloseable](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources và cleanup.
- [Java SE 11 — HttpServer](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback HTTP fixture public API để test.

**Kết luận:** Để kiểm chứng API Java 11 đúng và có thể tái lập, quản lý truststore/identity/hostname verification như **security contract**, truyền `Locale`/`ZoneId`/`Charset` tường minh như **data contract**, và quản lý streams/sockets/process/temp files như **resource contract**. Tạo SSLContext riêng thay vì thay đổi trust toàn JVM; test cả kết nối TLS bị từ chối; dùng UTF-8 rõ và decoder nghiêm ngặt; cô lập global properties bằng process nếu cần; dùng timeout/try-with-resources/cleanup; kiểm cả status, headers và bytes của HTTP API. Những nguyên tắc này vẫn phù hợp trên Java hiện đại dù default charset, security policy và locale data có thể thay đổi theo JDK.