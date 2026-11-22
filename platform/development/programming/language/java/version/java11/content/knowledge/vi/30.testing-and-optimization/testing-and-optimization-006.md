# Kiểm thử và tối ưu Java 11+: TLS, XDH và ChaCha20 với đầu vào sai, dữ liệu bị sửa

> **Mục tiêu:** Xây dựng kiểm thử **âm tính (negative tests)** cho ba lớp mật mã thường gặp trên Java 11+: TLS/JSSE, XDH (đặc biệt X25519) và ChaCha20-Poly1305. Kiểm tra cả kết nối hợp lệ lẫn **hostname sai, chứng chỉ không được tin cậy, khóa công khai XDH không hợp lệ, nonce/key sai, ciphertext/tag/AAD bị sửa và dữ liệu bị cắt ngắn**. Chỉ dùng API đang được hỗ trợ; không khôi phục TLS 1.0/1.1, không tắt xác minh certificate, không dùng ChaCha20 trần như thể có kiểm tra toàn vẹn. Hai chương trình cuối bài đã được biên dịch bằng `javac --release 11` và chạy trên OpenJDK HotSpot hiện đại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **TLS** là giao thức bảo vệ kênh, **XDH** là thỏa thuận khóa, **ChaCha20** là stream cipher, **ChaCha20-Poly1305** là AEAD có xác thực.
2. Tạo ma trận test phân biệt **dữ liệu không đúng định dạng**, **khóa/cấu hình không hợp lệ**, **đối tác không đáng tin** và **ciphertext bị sửa**.
3. Dùng `SSLContext`/`SSLSocket`/`SSLParameters` tạo kết nối TLS 1.3 thử nghiệm trên loopback với certificate kiểm soát.
4. Xác minh kết nối có certificate hợp lệ, hostname khớp; từ chối **hostname không khớp** và **certificate không nằm trong trust store**.
5. Dùng `X25519`/`KeyAgreement` kiểm hai phía tạo cùng shared secret khi trao đổi keys hợp lệ.
6. Kiểm việc từ chối encoded public key sai, public point bậc nhỏ và key thuộc group khác; hiểu khác biệt giữa **rejected key** và **bị giả mạo bởi MITM**.
7. Biến shared secret XDH thành symmetric key bằng HKDF-HMAC-SHA256, không dùng raw shared secret làm ChaCha key tùy tiện.
8. Mã hóa và giải mã bằng `Cipher.getInstance("ChaCha20-Poly1305")` cùng AAD và nonce 12 byte.
9. Kiểm `AEADBadTagException` cho ciphertext, tag, AAD, nonce, key sai và payload cắt ngắn.
10. Thử nonce có độ dài không hợp lệ, key không đủ 256 bit; không nhầm input validation exception với authentication failure.
11. Chứng minh **ChaCha20 thuần không phát hiện chỉnh sửa ciphertext**, nên ưu tiên AEAD.
12. Thực hiện test có thể tái lập mà không làm yếu bảo mật production, không log keys/plaintext nhạy cảm, không biến một exception bị bắt tùy tiện thành PASS.

## 2. Ba tầng bảo vệ và ranh giới trách nhiệm

~~~text
Ứng dụng Java
  |
  | HTTP Client / SSL Socket
  v
TLS 1.3 (JSSE)
  |-- Chọn phiên bản giao thức / cipher suite / key exchange
  |-- Xác thực certificate và danh tính server (hostname)
  |-- Tính keying material từ handshake transcript
  |-- AEAD bảo vệ bản ghi TLS khỏi bị sửa
  v
Dữ liệu application được gửi trong kênh TLS

Khi tự xây một định dạng mã hóa riêng (không phải TLS):
  X25519 / XDH  -> shared secret
                     |
                  HKDF với context
                     |
                 key ChaCha20-Poly1305
                     |
               nonce duy nhất + AAD
                     |
                  ciphertext + tag
~~~

**Đừng lẫn trách nhiệm:**

- **TLS** đã thực hiện handshake, xác thực peer qua trust/certificate và bảo vệ TLS records theo giao thức; application không cần (và không nên) viết lại TLS bằng `Cipher`.
- **XDH** tạo một shared secret giữa hai bên có keys hợp lệ, nhưng **không xác thực rằng khóa công khai thực sự thuộc về đối tác mong muốn**.
- **HKDF** dẫn xuất key có cấu trúc từ keying material; nó **không bổ sung authentication nếu input XDH đã bị MITM tráo đổi**.
- **ChaCha20** chỉ giữ bí mật byte stream, **không phát hiện dữ liệu bị sửa**.
- **ChaCha20-Poly1305** là **AEAD** (Authenticated Encryption with Associated Data): xác thực ciphertext và AAD, nhưng **không tự giải quyết replay, key ownership hoặc certificate trust**.
- Cipher suite `TLS_CHACHA20_POLY1305_SHA256` có thể được TLS 1.3 thương lượng; TLS 1.3 **không luôn dùng ChaCha20**, thường có thể chọn AES-GCM tùy provider/cấu hình/peer.
- X25519 được TLS 1.3 hỗ trợ như một named group, nhưng **không được kết luận một connection đã dùng X25519 chỉ vì JVM hỗ trợ XDH**.

## 3. Vì sao phải có negative tests?

Một test thành công duy nhất như “encrypt → decrypt ra plaintext” chỉ chứng minh happy path cơ bản. Hệ thống bảo mật còn phải từ chối những tình huống:

| Nhóm | Đầu vào xấu | Lớp phải phát hiện | Kỳ vọng |
| --- | --- | --- | --- |
| TLS trust | Certificate self-signed ngoài trust store | JSSE trust manager/PKIX | Handshake thất bại |
| TLS identity | Certificate trusted nhưng SAN không khớp host | Endpoint identification | Handshake thất bại |
| TLS protocol | Không có protocol/cipher suite tương thích | JSSE negotiation | Handshake thất bại |
| TLS record | TLS record bị sửa/tag sai | TLS record protection | Record/connection bị từ chối; không trao plaintext giả |
| XDH format | Encoded public key hỏng | `KeyFactory` | `InvalidKeySpecException` hoặc exception thích hợp |
| XDH group | X448 public key đưa vào X25519 exchange | `KeyAgreement` | Key bị từ chối |
| XDH small-order | Low-order point, ví dụ u = 0 | XDH provider/key agreement | Không dùng shared secret nguy hiểm |
| XDH identity | MITM tráo public key **hợp lệ về toán học** | Authentication/transcript binding | Phải được certificate/signature/PSK xác thực; XDH đơn độc không phát hiện |
| AEAD ciphertext | Đảo bit trong ciphertext | `ChaCha20-Poly1305` | Authentication tag không khớp |
| AEAD tag | Đảo bit ở 16 byte tag | `ChaCha20-Poly1305` | Authentication tag không khớp |
| AEAD AAD | Header/sequence/type bị sửa | `updateAAD` | Tag check thất bại |
| AEAD key/nonce | Sai key hoặc nonce nhưng đủ độ dài | `doFinal` verification | Tag check thất bại |
| AEAD parameters | Nonce 11 byte, key 128 bit | `Cipher.init` | Parameter/key validation failure |
| AEAD truncation | Payload bị cắt | `doFinal` | Không xác thực; không dùng plaintext |
| AEAD replay | Gửi lại nguyên gói hợp lệ | **Application protocol state** | Từ chối nếu sequence/message ID đã dùng; AEAD tự nó không ngăn replay |

**Test hợp lệ phải phân biệt nguyên nhân**: handshake có thể fail vì certificate, lỗi mạng hoặc timeout. Nếu mục tiêu kiểm hostname mismatch, đừng bắt `Exception` bất kỳ rồi cho PASS; cần chứng minh test server lắng nghe, trust store đúng và happy path đã thành công.

## 4. TLS 1.3 trên Java 11: bắt tay và xác thực

Java 11 có hỗ trợ TLS 1.3 qua JSSE; những update/hotfix của JDK sau này có thể thay đổi danh sách thuật toán bật mặc định và giới hạn bảo mật. Một phiên TLS 1.3 bình thường thực hiện:

1. Client đề xuất versions, cipher suites, named groups và key shares.
2. Server chọn thông số giao thức tương thích.
3. Hai phía tạo keying material và xác nhận handshake transcript.
4. Client kiểm đường tin cậy certificate, thời hạn/usage/algorithm constraints, và hostname theo client API/cấu hình.
5. Hai phía sử dụng khóa AEAD bảo vệ bản ghi ứng dụng.
6. Nếu certificate/key exchange/Finished/record authentication sai, giao thức phải thất bại thay vì trao dữ liệu như một kênh đã xác thực.

### Không đồng nhất trust với hostname

- **Certificate trusted**: có chuỗi tin cậy được xác thực theo trust anchors/policy.
- **Certificate matches hostname**: danh tính peer trong SAN phù hợp với tên server mà client thực sự kết nối.
- Đặt custom trust store **không tự động chứng minh hostname hợp lệ**.
- Với ứng dụng `SSLSocket` tự tạo, nên bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` khi dùng kiểm danh tính như HTTPS.
- Với `HttpsURLConnection`/`java.net.http.HttpClient`, dùng cơ chế validation mặc định và chỉ cấu hình trust store khi có lý do rõ; **không** dùng “trust-all”/“verify-all hostnames” để làm test pass.

### Không coi mọi TLSv1.3 connection đã dùng ChaCha20

~~~java
SSLSession session = socket.getSession();

System.out.println(session.getProtocol());
System.out.println(session.getCipherSuite());
~~~

**Đoạn minh họa** cần một `SSLSocket socket` đã bắt tay thành công. `getCipherSuite()` cho tên suite được thương lượng; đó mới là dữ liệu để xác minh AEAD của phiên. Không tự suy từ TLS 1.3 rằng suite phải là `TLS_CHACHA20_POLY1305_SHA256`, hoặc suy ra group X25519 từ tên cipher suite TLS 1.3 (key exchange group không nằm trong tên suite).

## 5. Một bộ kiểm thử TLS địa phương — không Internet và không “trust-all”

Ta tạo một certificate thử nghiệm **chỉ dành cho localhost** với `keytool`, sau đó dùng:

- Một `SSLServerSocket` ràng buộc `127.0.0.1` và chỉ cho TLS 1.3.
- Client **tin certificate cụ thể này**, kết nối tới peer name `localhost` → **PASS**.
- Cùng client/trust store, nhưng yêu cầu xác thực peer name `not-localhost.example` → **bị từ chối**.
- Client dùng **trust store rỗng**, vẫn nối tới `localhost` → **bị từ chối**.

Việc tạo TCP socket đến `127.0.0.1` sau đó wrap bằng `SSLSocketFactory.createSocket(raw, peerHost, port, true)` giúp kiểm **hostname mà TLS client xác thực** mà không cần DNS công cộng.

### Tạo certificate tạm

Chạy lệnh bên dưới **trong thư mục thử nghiệm riêng**, nơi chưa có `server.p12`:

~~~bash
keytool -genkeypair -alias localhost -keyalg EC -keysize 256 -sigalg SHA256withECDSA -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost,OU=Lab,O=Local,C=VN" -ext "SAN=dns:localhost" -validity 2 -noprompt
~~~

**Chú ý bảo mật:** `changeit` là password **cố tình công khai trong một fixture vứt bỏ**, tuyệt đối không dùng với production key stores. Certificate self-signed này không phải chứng chỉ CA công cộng. `SAN=dns:localhost` cho phép test hostname `localhost`; certificate không hợp lệ cho tên `not-localhost.example`.

## 6. Java 11 hoàn chỉnh: TlsLocalNegativeLab.java

Tạo file **`TlsLocalNegativeLab.java`** với nội dung:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsLocalNegativeLab {

    private static SSLContext context(KeyStore store, boolean server)
            throws Exception {
        SSLContext ctx = SSLContext.getInstance("TLS");

        if (server) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(store, "changeit".toCharArray());
            ctx.init(kmf.getKeyManagers(), null, new SecureRandom());
        } else {
            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(store);
            ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
        }
        return ctx;
    }

    private static KeyStore emptyTrust() throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        store.load(null, null);
        return store;
    }

    private static String connect(
            SSLContext context, int port, String peerHost)
            throws Exception {
        Socket raw = new Socket();
        raw.connect(new InetSocketAddress("127.0.0.1", port), 4000);
        raw.setSoTimeout(5000);

        try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
                .createSocket(raw, peerHost, port, true)) {

            tls.setSoTimeout(5000);
            SSLParameters p = tls.getSSLParameters();
            p.setProtocols(new String[] { "TLSv1.3" });
            p.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(p);
            tls.startHandshake();

            String protocol = tls.getSession().getProtocol();
            tls.getOutputStream().write(0x5A);
            tls.getOutputStream().flush();
            return protocol;
        }
    }

    private static boolean rejected(
            SSLContext ctx, int port, String host)
            throws Exception {
        try {
            connect(ctx, port, host);
            return false;
        } catch (SSLException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: TlsLocalNegativeLab server.p12");
        }

        Path file = Paths.get(args[0]);
        if (!Files.isRegularFile(file)) {
            throw new IOException("Missing lab keystore");
        }

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (java.io.InputStream in = Files.newInputStream(file)) {
            store.load(in, "changeit".toCharArray());
        }

        SSLContext serverCtx = context(store, true);
        SSLContext trusted = context(store, false);
        SSLContext untrusted = context(emptyTrust(), false);

        AtomicInteger serverGood = new AtomicInteger();
        AtomicInteger serverRejected = new AtomicInteger();
        AtomicReference<Throwable> serverError = new AtomicReference<>();

        try (SSLServerSocket listener = (SSLServerSocket)
                serverCtx.getServerSocketFactory().createServerSocket(
                        0, 8, InetAddress.getByName("127.0.0.1"))) {

            listener.setSoTimeout(10000);
            listener.setEnabledProtocols(new String[] { "TLSv1.3" });

            Thread thread = new Thread(() -> {
                for (int i = 0; i < 3; i++) {
                    try (SSLSocket peer =
                            (SSLSocket) listener.accept()) {

                        peer.setSoTimeout(5000);
                        peer.startHandshake();

                        if (peer.getInputStream().read() == 0x5A) {
                            serverGood.incrementAndGet();
                        }

                    } catch (IOException expectedForNegativeCase) {
                        if (i == 0) {
                            serverError.set(expectedForNegativeCase);
                            return;
                        }
                        // Client may send TLS alert or abruptly close
                        // when rejecting server identity.
                        serverRejected.incrementAndGet();

                    } catch (Throwable unexpected) {
                        serverError.set(unexpected);
                        return;
                    }
                }
            }, "tls-local-server");

            thread.start();

            String goodProtocol = connect(
                    trusted, listener.getLocalPort(), "localhost");

            boolean wrongHost = rejected(
                    trusted, listener.getLocalPort(),
                    "not-localhost.example");

            boolean noTrust = rejected(
                    untrusted, listener.getLocalPort(), "localhost");

            thread.join(12000);
            if (thread.isAlive()) {
                throw new IllegalStateException(
                        "TLS server did not finish");
            }
            if (serverError.get() != null) {
                throw new IllegalStateException(
                        "TLS server failed", serverError.get());
            }

            System.out.println("tls.goodHandshake="
                    + "TLSv1.3".equals(goodProtocol));
            System.out.println("tls.negotiatedProtocol="
                    + goodProtocol);
            System.out.println("tls.badHostnameRejected="
                    + wrongHost);
            System.out.println("tls.untrustedCertificateRejected="
                    + noTrust);
            System.out.println("tls.serverAccepted="
                    + serverGood.get());
            System.out.println("tls.serverNegativeConnections="
                    + serverRejected.get());
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 11 TlsLocalNegativeLab.java
java TlsLocalNegativeLab server.p12
~~~

**Stdout thực tế của lượt thử trên HotSpot** (TLS 1.3 được hỗ trợ, loopback có thể bind):

~~~text
tls.goodHandshake=true
tls.negotiatedProtocol=TLSv1.3
tls.badHostnameRejected=true
tls.untrustedCertificateRejected=true
tls.serverAccepted=1
tls.serverNegativeConnections=2
~~~

**Giải thích:**

- `goodHandshake=true`: client có trust entry phù hợp và kiểm tên `localhost` thành công.
- `badHostnameRejected=true`: certificate vẫn nằm trong trust store, nhưng **peer hostname giả định không khớp SAN**.
- `untrustedCertificateRejected=true`: hostname là `localhost` nhưng **trust store rỗng**; certificate bị từ chối.
- `serverAccepted=1`: một kết nối server đã đọc được byte ứng dụng sau handshake.
- `serverNegativeConnections=2`: hai kết nối âm tính bị gián đoạn. Phía server có thể nhận **TLS alert hoặc SocketException** khi client đóng socket trước; không lấy loại exception ở server làm bằng chứng chính về lý do.
- Test xác nhận bên client bắt `SSLException`. Khi cần xác minh **chính xác nguyên nhân**, thêm assertions về certificate identity/trust diagnostics và chain causes ở môi trường thử; không assert nguyên văn exception message vì thay đổi theo provider/JDK/OS.
- Đừng in ``javax.net.debug` chi tiết trên hệ thống sản xuất: debugging TLS có thể lộ hostname, cert, handshake data hoặc thông tin nhạy cảm.

### Vòng đời TLS fixture

Chương trình chỉ mở socket trên `127.0.0.1`, tạo một server thread, chấp nhận ba client và đóng khi xong. Mục đích **không phải** cung cấp HTTPS server production. Các trust keys và password literal ở đây chỉ cho thí nghiệm disposable.

## 7. TLS negative tests chưa cần viết lại record cipher

TLS 1.3 đã có AEAD record protection và kiểm tra Finished messages. Để kiểm implementation/protocol integration, ưu tiên:

- Certificate không được trust → handshake từ chối.
- Hostname/SAN sai → handshake từ chối.
- Cert hết hạn/không có extended key usage thích hợp → bị từ chối theo policy.
- Không có shared enabled protocol/cipher suite → handshake từ chối.
- Client chỉ cho TLS 1.3, server thử nghiệm chỉ cho TLS 1.2 → không bắt tay được nếu không có fallback được phép.
- Peer gửi TLS record sai tag/length → record bị từ chối; không chuyển plaintext không xác thực cho application.
- Peer cắt kết nối giữa handshake/response → protocol/transport error; không suy từ EOF rằng server đã chấp nhận request.
- Kiểm timeout, socket close, resource cleanup khi handshake thất bại.

**Không tự gửi ciphertext được sửa qua production network**, không tắt certificate validation và không áp dụng insecure fallback sang TLS 1.0/SSLv3. Muốn fault injection TLS records, dùng test proxy/record mutator **trong lab độc lập**, với assertions rằng **không có dữ liệu giả được giao tới application**, chứ không chỉ mong một stack trace đúng chính tả.

### Tại sao ví dụ trên không sửa trực tiếp TLS record bytes?

Bởi `SSLSocket` quản lý framing, AEAD sequence numbers và handshake transcript. Nếu tự thay vài byte trong socket application output, đó là **plaintext trước TLS encryption**, sẽ được JSSE mã hóa đúng và không tương đương “ciphertext bị kẻ khác sửa”. Thử tamper với **ChaCha20-Poly1305 trực tiếp** ở phần sau sẽ tách rõ tính chất xác thực, không viết một TLS stack tùy biến.

## 8. XDH/X25519: thỏa thuận khóa, không phải xác thực

Java 11 hỗ trợ các tên thuật toán **`XDH`, `X25519`, `X448`**. Trong thực hành, X25519 thường được dùng làm key agreement để hai phía tạo secret giống nhau:

~~~text
Alice: private_a + public_a
Bob:   private_b + public_b

Alice gửi public_a ------> Bob
Bob   gửi public_b ------> Alice

Alice: X25519(private_a, public_b) = K
Bob:   X25519(private_b, public_a) = K
~~~

**Public key được phép truyền**, private key phải bảo vệ. Tuy nhiên sơ đồ trên **dễ bị MITM** nếu kẻ tấn công thay cả hai public keys. Hai phía vẫn có thể tính secrets riêng với kẻ tấn công mà không biết đối tác không đúng.

Để thực sự bảo mật session, cần **xác thực keys/handshake transcript** bằng certificate/signature/PSK hoặc một protocol đã được phân tích. **TLS 1.3 làm việc đó**, nên nếu yêu cầu chỉ là giao tiếp mạng, dùng TLS thay vì xây giao thức XDH+AEAD riêng.

### API Java 11

~~~java
KeyPairGenerator generator =
        KeyPairGenerator.getInstance("X25519");

KeyPair alice = generator.generateKeyPair();
KeyPair bob = generator.generateKeyPair();

KeyAgreement agreement =
        KeyAgreement.getInstance("X25519");

agreement.init(alice.getPrivate());
agreement.doPhase(bob.getPublic(), true);
byte[] aliceSecret = agreement.generateSecret();
~~~

**Đoạn minh họa** cần imports `KeyPairGenerator`, `KeyPair`, `KeyAgreement`. Phía Bob phải chạy giao thức đối xứng và hai parties cần xác thực peer keys nếu đây là một kết nối thật.

## 9. XDH invalid input: ba trường hợp phải thử

### 9.1. Encoded public key sai định dạng

Một khóa công khai X25519 được mã hóa theo **X.509 SubjectPublicKeyInfo** khi dùng `PublicKey.getEncoded()`. Đừng tự coi một chuỗi 32 bytes bất kỳ là X509EncodedKeySpec hợp lệ.

~~~java
KeyFactory factory = KeyFactory.getInstance("X25519");
factory.generatePublic(
        new X509EncodedKeySpec(new byte[] { 0x30, 0x01 }));
~~~

**Đoạn minh họa có chủ đích gây lỗi**. Với input DER/SPKI bị cắt/hỏng, `generatePublic` phải thất bại bằng `InvalidKeySpecException` (hoặc lỗi tương đương theo provider nếu kiểm trường hợp khác). Test cần đảm bảo kết quả **không chấp nhận key**, không xác định tính hợp lệ qua độ dài file thôi.

### 9.2. Low-order public point

X25519 có các trường hợp low-order points có thể dẫn đến secret không an toàn. Kiểm `XECPublicKeySpec(NamedParameterSpec.X25519, BigInteger.ZERO)` và đưa key cho `KeyAgreement`. Trong HotSpot SunEC thử nghiệm, phương thức agreement **từ chối điểm low-order** bằng `InvalidKeyException`. Provider khác có thể từ chối ngay ở `KeyFactory`; cả hai là hành vi an toàn để test.

Không **tự dựa vào** đầu ra 32 bytes zero để làm encryption key; nếu provider chấp nhận một public key nguy hiểm, một thiết kế hệ thống phải xử lý theo security policy. **Không tự bỏ qua validation chỉ để hoàn thành handshake**.

### 9.3. Group không khớp

Một X448 public key không tương ứng với X25519 group. Bài test đưa public key X448 vào agreement X25519 và xác minh `InvalidKeyException`. Đừng thử “chỉnh bytes/key spec cho đúng số byte” để ép hai curves tương thích — đó là thay đổi ý nghĩa mật mã.

### Lưu ý: invalid key khác peer không được xác thực

Một public key X25519 **hoàn toàn hợp lệ về toán học** do MITM phát có thể qua kiểm định group/format. **Key validation không đủ chống MITM**. Cần signature/certificate/PSK authentication, transcript binding và chống downgrade. Tránh sai lầm “doPhase() thành công tức server thật”.

## 10. HKDF sau XDH: biến keying material thành AEAD key

`KeyAgreement.generateSecret()` trả **shared secret bytes**, không tự là khóa phù hợp cho mỗi mục đích. Trong một giao thức tự xây (chỉ dùng cho lab ở đây), cần KDF và thông tin ngữ cảnh.

**HKDF-HMAC-SHA256 (RFC 5869)** có hai bước:

1. **Extract**: `PRK = HMAC(salt, sharedSecret)`.
2. **Expand**: `OKM = HMAC(PRK, info || 0x01)` cho một output block 32 bytes.

Nếu dẫn xuất hơn 32 bytes, phải triển khai toàn bộ vòng HKDF Expand của RFC; chương trình dưới đây **chỉ yêu cầu đúng 32 bytes**, nên một block là đủ.

~~~text
X25519 shared secret:      32 bytes
HKDF salt:                32 bytes randomly generated for the session
HKDF info:                "lesson/xdh-chacha20poly1305/v1"
HKDF output:              32-byte ChaCha20-Poly1305 symmetric key
~~~

**Mô hình lab, không phải giao thức authenticated production.** Đổi salt/info không sửa lỗi MITM của XDH. Ở production, sử dụng TLS/cryptographic protocol đã chuẩn hóa và có cơ chế xác thực key exchange.

### Domain separation

Mỗi key purpose khác nhau cần `info` rõ ràng, ví dụ `app/v1/client-to-server/encryption` và `app/v1/server-to-client/encryption`. Không dùng cùng key, nonce và “kiểu dữ liệu” cho các mục đích khác nhau mà không có context. Với protocol nhiều messages, sử dụng key schedule/sequence và nonce management đã thiết kế, **không chỉ random nonce rồi quên đánh dấu gói đã nhận**.

## 11. ChaCha20 và ChaCha20-Poly1305 khác nhau thế nào?

| API/thuật toán | Bảo mật dữ liệu | Phát hiện chỉnh sửa | Tham số Java 11 |
| --- | --- | --- | --- |
| `Cipher.getInstance("ChaCha20")` | Stream cipher encryption | **Không** có authentication | `ChaCha20ParameterSpec(nonce12, counter)` |
| `Cipher.getInstance("ChaCha20-Poly1305")` | AEAD encryption + Poly1305 tag | **Có**, nếu key/nonce/AAD dùng đúng | `IvParameterSpec(nonce12)` |
| TLS 1.3 cipher suite ChaCha20-Poly1305 | AEAD trong TLS record protocol | Có, do JSSE quản lý sequence/keys | Không tự tạo `Cipher` ở application |
| `Cipher.getInstance("AES/GCM/NoPadding")` | AEAD thay thế | Có, với nonce/key policy phù hợp | `GCMParameterSpec` |

**Không dùng `ChaCha20ParameterSpec` để khởi tạo `ChaCha20-Poly1305`**; trong SunJCE của Java 11+, AEAD mode yêu cầu `IvParameterSpec` chứa **nonce 12 bytes**. Với ChaCha20 thuần, `ChaCha20ParameterSpec` chứa nonce 12 bytes cùng initial counter.

### Kích thước tham số cần ghi nhớ

- ChaCha20 key: **256 bit = 32 bytes**.
- ChaCha20-Poly1305 nonce: **96 bit = 12 bytes**.
- Poly1305 authentication tag: **128 bit = 16 bytes**.
- Ciphertext AEAD Java API `doFinal` thông thường chứa **ciphertext và tag đi kèm**, không phải plaintext.
- AAD không bị mã hóa nhưng được xác thực: thay AAD phải làm verification thất bại.
- **Nonce không phải secret**, nhưng **không được tái sử dụng cùng key để encrypt message khác**.
- Mỗi operation encryption cần nonce duy nhất theo key; đối với protocol lâu dài, hãy dùng **nonce schedule/counter có ràng buộc và rotation**, không dựa mù vào random nonce mà không quản lý tổng số messages.

### Quy tắc thứ tự API

~~~java
cipher.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(nonce));
cipher.updateAAD(headerBytes);
byte[] ciphertextWithTag = cipher.doFinal(plaintext);
~~~

**Đoạn minh họa**: `headerBytes` được xác thực nhưng không mã hóa. `updateAAD` phải xuất hiện trước xử lý ciphertext/plaintext data qua `update/doFinal`. Không gọi `doFinal` thêm lần nữa trên cùng state để encrypt một message khác mà không reinitialize với nonce mới.

## 12. Kịch bản AEAD bad input và tampering

Bài test cần riêng các lớp lỗi:

### Sửa ciphertext

Copy một ciphertext đã tạo hợp lệ; đổi **một bit** trong phần data, không thay original. Khi decrypt, tag không khớp và `Cipher.doFinal` ném `AEADBadTagException`. **Không dùng bất kỳ bytes plaintext tạm nào khi tag chưa được xác minh**.

### Sửa tag

Copy message, đổi một bit trong 16 bytes tag cuối. Expect `AEADBadTagException`. Không nên kiểm đúng string exception vì provider có thể đổi thông báo.

### Sửa AAD

Giữ ciphertext/key/nonce nguyên, nhưng đưa AAD khác cho `updateAAD`. Verify phải thất bại. Đây là cách đảm bảo metadata như `message type`, `version` và `sequence` không thể thay mà vẫn được chấp nhận dưới cùng key/nonce.

### Sai key hoặc nonce

Nếu key/nonce **đúng độ dài nhưng khác giá trị**, initialization có thể hoàn tất; lỗi chỉ bộc lộ khi verification ở `doFinal`. Không kết luận “Cipher.init thành công” chứng minh peer sử dụng cùng key.

### Cắt ngắn payload

Nếu ciphertext/tag bị cắt, verification không hợp lệ. Với input còn đủ tag length nhưng tag sai, thường nhận `AEADBadTagException`; với input quá ngắn hoặc format sai, API/provider có thể ném loại lỗi khác. Test nên nêu **điểm nào bị cắt** và kỳ vọng không có plaintext xác thực.

### Sai độ dài key/nonce

Đây là **parameter validation**, không nhất thiết có authentication tag để xác minh: nonce 11 bytes có thể ném `InvalidAlgorithmParameterException` tại `Cipher.init`; key 16 bytes thay cho ChaCha20 32 bytes ném `InvalidKeyException`.

### Replay gói đúng

AEAD chỉ phát hiện sửa đổi chứ **không tự phát hiện người gửi lại nguyên message+nonce+AAD hợp lệ**. Ở tầng application, lưu message ID/sequence number, giới hạn cửa sổ nhận, và ràng buộc context/session. **Một nonce mới khi encryption không đủ thay thế anti-replay verification khi decryption**.

## 13. Java 11 hoàn chỉnh: CryptoBadInputLab.java

Ví dụ tự tạo keypairs X25519, chạy HKDF cho 32-byte key, mã hóa **một message** bằng ChaCha20-Poly1305 với nonce ngẫu nhiên 12 bytes, rồi thử các cách sửa đổi trên **bản sao ciphertext**. Các lần **decrypt cùng ciphertext để test** không phải tái sử dụng nonce để **encrypt** một message mới. Cuối cùng, dùng một raw ChaCha20 key/nonce **khác hẳn** để chứng minh dữ liệu sửa vẫn có thể decrypt mà không báo authentication error.

Tạo file **`CryptoBadInputLab.java`**:

~~~java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.NamedParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.security.spec.XECPublicKeySpec;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class CryptoBadInputLab {
    private static final SecureRandom RANDOM = new SecureRandom();

    @FunctionalInterface
    interface CryptoAttempt {
        void run() throws Exception;
    }

    private static boolean rejectsBadTag(CryptoAttempt op)
            throws Exception {
        try {
            op.run();
            return false;
        } catch (AEADBadTagException expected) {
            return true;
        }
    }

    private static byte[] shared(KeyPair self, PublicKey remote)
            throws Exception {
        KeyAgreement exchange =
                KeyAgreement.getInstance("X25519");
        exchange.init(self.getPrivate());
        exchange.doPhase(remote, true);
        return exchange.generateSecret();
    }

    private static byte[] hkdf32(byte[] ikm,
            byte[] salt, byte[] info)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = mac.doFinal(ikm);

        mac.init(new SecretKeySpec(prk, "HmacSHA256"));
        mac.update(info);
        mac.update((byte) 1);
        byte[] key = mac.doFinal();

        Arrays.fill(prk, (byte) 0);
        return key;
    }

    private static byte[] seal(byte[] key, byte[] nonce,
            byte[] aad, byte[] plaintext) throws Exception {

        Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
        c.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(key, "ChaCha20"),
                new IvParameterSpec(nonce));
        c.updateAAD(aad);
        return c.doFinal(plaintext);
    }

    private static byte[] open(byte[] key, byte[] nonce,
            byte[] aad, byte[] ciphertext) throws Exception {

        Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
        c.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(key, "ChaCha20"),
                new IvParameterSpec(nonce));
        c.updateAAD(aad);
        return c.doFinal(ciphertext);
    }

    private static boolean invalidNonceRejected(byte[] key)
            throws Exception {
        Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
        try {
            c.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(key, "ChaCha20"),
                    new IvParameterSpec(new byte[11]));
            return false;
        } catch (
                java.security.InvalidAlgorithmParameterException expected) {
            return true;
        }
    }

    private static boolean shortKeyRejected(byte[] nonce)
            throws Exception {
        Cipher c = Cipher.getInstance("ChaCha20-Poly1305");
        try {
            c.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(new byte[16], "ChaCha20"),
                    new IvParameterSpec(nonce));
            return false;
        } catch (InvalidKeyException expected) {
            return true;
        }
    }

    private static boolean malformedPublicRejected()
            throws Exception {
        try {
            KeyFactory.getInstance("X25519").generatePublic(
                    new X509EncodedKeySpec(
                            new byte[] { 0x30, 0x01 }));
            return false;
        } catch (InvalidKeySpecException expected) {
            return true;
        }
    }

    private static boolean lowOrderPublicRejected(KeyPair ours)
            throws Exception {
        try {
            PublicKey lowOrder = KeyFactory.getInstance("XDH")
                    .generatePublic(new XECPublicKeySpec(
                            NamedParameterSpec.X25519,
                            BigInteger.ZERO));
            shared(ours, lowOrder);
            return false;
        } catch (InvalidKeySpecException |
                 InvalidKeyException expected) {
            return true;
        }
    }

    private static boolean wrongGroupRejected(KeyPair ours)
            throws Exception {
        KeyPair other = KeyPairGenerator.getInstance("X448")
                .generateKeyPair();
        try {
            shared(ours, other.getPublic());
            return false;
        } catch (InvalidKeyException expected) {
            return true;
        }
    }

    public static void main(String[] args)
            throws Exception {
        KeyPairGenerator kpg =
                KeyPairGenerator.getInstance("X25519");

        KeyPair alice = kpg.generateKeyPair();
        KeyPair bob = kpg.generateKeyPair();

        byte[] aliceShared =
                shared(alice, bob.getPublic());
        byte[] bobShared =
                shared(bob, alice.getPublic());

        System.out.println("xdh.sharedEqual="
                + MessageDigest.isEqual(
                        aliceShared, bobShared));

        byte[] salt = new byte[32];
        RANDOM.nextBytes(salt);

        byte[] info =
                "lesson/xdh-chacha20poly1305/v1"
                        .getBytes(StandardCharsets.UTF_8);

        byte[] aliceKey = hkdf32(aliceShared, salt, info);
        byte[] bobKey = hkdf32(bobShared, salt, info);

        System.out.println("hkdf.keysEqual="
                + MessageDigest.isEqual(
                        aliceKey, bobKey));

        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);

        byte[] aad = "type=lesson;seq=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Xin chao, AEAD"
                .getBytes(StandardCharsets.UTF_8);

        byte[] ciphertext = seal(
                aliceKey, nonce, aad, plaintext);

        System.out.println("aead.roundTrip="
                + Arrays.equals(plaintext,
                        open(bobKey, nonce, aad, ciphertext)));

        byte[] corruptCiphertext = ciphertext.clone();
        corruptCiphertext[0] ^= 0x01;

        System.out.println(
                "aead.ciphertextTamperRejected="
                + rejectsBadTag(() ->
                        open(bobKey, nonce, aad,
                                corruptCiphertext)));

        byte[] corruptTag = ciphertext.clone();
        corruptTag[corruptTag.length - 1] ^= 0x01;

        System.out.println("aead.tagTamperRejected="
                + rejectsBadTag(() ->
                        open(bobKey, nonce, aad, corruptTag)));

        byte[] wrongAad = "type=lesson;seq=2"
                .getBytes(StandardCharsets.UTF_8);

        System.out.println("aead.aadTamperRejected="
                + rejectsBadTag(() ->
                        open(bobKey, nonce, wrongAad, ciphertext)));

        byte[] wrongNonce = nonce.clone();
        wrongNonce[0] ^= 0x01;

        System.out.println("aead.wrongNonceRejected="
                + rejectsBadTag(() ->
                        open(bobKey, wrongNonce, aad, ciphertext)));

        byte[] wrongKey = new byte[32];
        RANDOM.nextBytes(wrongKey);

        System.out.println("aead.wrongKeyRejected="
                + rejectsBadTag(() ->
                        open(wrongKey, nonce, aad, ciphertext)));

        byte[] truncated =
                Arrays.copyOf(ciphertext, ciphertext.length - 1);

        System.out.println("aead.truncatedRejected="
                + rejectsBadTag(() ->
                        open(bobKey, nonce, aad, truncated)));

        System.out.println("aead.badNonceLengthRejected="
                + invalidNonceRejected(aliceKey));
        System.out.println("aead.shortKeyRejected="
                + shortKeyRejected(nonce));
        System.out.println("xdh.malformedPublicRejected="
                + malformedPublicRejected());
        System.out.println("xdh.lowOrderPublicRejected="
                + lowOrderPublicRejected(alice));
        System.out.println("xdh.wrongGroupRejected="
                + wrongGroupRejected(alice));

        byte[] rawKey = new byte[32];
        byte[] rawNonce = new byte[12];
        RANDOM.nextBytes(rawKey);
        RANDOM.nextBytes(rawNonce);

        Cipher rawEncrypt = Cipher.getInstance("ChaCha20");
        rawEncrypt.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(rawKey, "ChaCha20"),
                new ChaCha20ParameterSpec(rawNonce, 1));

        byte[] rawCiphertext =
                rawEncrypt.doFinal(plaintext);
        rawCiphertext[0] ^= 0x01;

        Cipher rawDecrypt = Cipher.getInstance("ChaCha20");
        rawDecrypt.init(Cipher.DECRYPT_MODE,
                new SecretKeySpec(rawKey, "ChaCha20"),
                new ChaCha20ParameterSpec(rawNonce, 1));

        byte[] rawPlain =
                rawDecrypt.doFinal(rawCiphertext);

        System.out.println("rawChaCha20.tamperUndetected="
                + !Arrays.equals(plaintext, rawPlain));

        Arrays.fill(aliceShared, (byte) 0);
        Arrays.fill(bobShared, (byte) 0);
        Arrays.fill(aliceKey, (byte) 0);
        Arrays.fill(bobKey, (byte) 0);
        Arrays.fill(rawKey, (byte) 0);
    }
}
~~~

### Biên dịch/chạy

~~~bash
javac --release 11 CryptoBadInputLab.java
java CryptoBadInputLab
~~~

Các API được dùng đã có trên Java 11. Chương trình đã được biên dịch bằng `javac --release 11` và chạy thành công trên HotSpot OpenJDK hiện đại. Nếu provider khác không hỗ trợ X448, low-order validation hay ChaCha20-Poly1305 giống SunJCE, test phải **báo không tương thích/hỗ trợ khác**, không lén bỏ các ca thất bại.

### Stdout đã kiểm chứng

~~~text
xdh.sharedEqual=true
hkdf.keysEqual=true
aead.roundTrip=true
aead.ciphertextTamperRejected=true
aead.tagTamperRejected=true
aead.aadTamperRejected=true
aead.wrongNonceRejected=true
aead.wrongKeyRejected=true
aead.truncatedRejected=true
aead.badNonceLengthRejected=true
aead.shortKeyRejected=true
xdh.malformedPublicRejected=true
xdh.lowOrderPublicRejected=true
xdh.wrongGroupRejected=true
rawChaCha20.tamperUndetected=true
~~~

### Mỗi dòng có ý nghĩa gì?

- `xdh.sharedEqual=true`: cùng hai public/private key pairs tạo ra shared secret giống nhau. **Chưa chứng minh peer được xác thực**.
- `hkdf.keysEqual=true`: cùng IKM, salt, info dẫn xuất cùng 32-byte key.
- `aead.roundTrip=true`: AEAD nhận message đúng và trả plaintext đúng.
- Các dòng `aead.*TamperRejected`, `wrong*Rejected`, `truncatedRejected`: ciphertext/key/AAD/nonce không khớp dẫn đến failure ở xác thực tag.
- `badNonceLengthRejected` và `shortKeyRejected`: từ chối ngay tại bước tham số/key validation, **khác** mismatch tag.
- `xdh.malformedPublicRejected`: không parse public key SPKI hỏng.
- `xdh.lowOrderPublicRejected`: không chấp nhận low-order public point trong đường test đã thử.
- `xdh.wrongGroupRejected`: X448 public key không được dùng như public X25519.
- `rawChaCha20.tamperUndetected=true`: stream cipher không có tag, decrypt thành **plaintext bị sửa mà không phát lỗi xác thực**. Đây là minh chứng vì sao phải dùng AEAD.

**Giá trị keys, nonce, salt được random nên khác mỗi run**, nhưng các output booleans trên là điều kiện mong đợi của fixture khi provider phù hợp; không in/so sánh raw shared secret, ciphertext hay key trong logs.

## 14. Cách viết assertion an toàn cho negative tests

### 14.1. Không chấp nhận “bất kỳ exception nào = PASS”

Mẫu sai:

~~~java
try {
    decrypt(badMessage);
    fail("Expected an error");
} catch (Exception ignored) {
    // Sai: có thể pass dù do NullPointerException,
    // IOException hoặc lỗi lập trình khác.
}
~~~

Đây là **mã minh họa sai**, có các helpers không được định nghĩa. Nếu dùng JUnit, exception assertion nên **chỉ bắt đúng nhóm lỗi mong đợi** và không bắt lại exception assertion do test tự ném.

Mẫu đúng với Java thuần:

~~~java
boolean rejected = false;

try {
    cipher.doFinal(corruptedCiphertext);
} catch (AEADBadTagException expected) {
    rejected = true;
}

if (!rejected) {
    throw new AssertionError(
            "Tampered AEAD ciphertext was accepted");
}
~~~

**Mã minh họa** với `cipher` đã init cho DECRYPT, `updateAAD` đã cung cấp đúng AAD trước đó. Phương pháp này phân biệt verify failure với lỗi khác. Nếu provider ném một exception tổng quát hơn theo hợp đồng riêng, test compatibility phải được viết rõ, không bắt sạch tất cả rồi cho pass.

### 14.2. Không kiểm raw exception string

Thông báo “Tag mismatch”, “Tag mismatch!” hoặc “bad record MAC” có thể đổi theo JDK/provider. Nên assert:

- Exception **category/class** phù hợp;
- Thời điểm failure;
- Không có plaintext đáng tin nào được giao cho logic nghiệp vụ;
- Trạng thái connection/cipher bị giải phóng hoặc invalidated;
- Logs không chứa keys, plaintext, tokens hoặc raw ciphertext dài.

### 14.3. Không dùng plaintext trước khi tag được xác minh

Với một số AEAD APIs có streaming `update`, output trung gian có thể tồn tại **trước final authentication** theo provider. Chỉ dùng/decode/process plaintext sau `doFinal` verify thành công; với file lớn cần thiết kế **quarantine/atomic commit** output sau xác thực. Đừng ghi partially decrypted data ra file đích công khai rồi mới phát hiện tag sai.

## 15. Nonce uniqueness: kiểm đúng nhưng đừng tạo nguy cơ mới

ChaCha20-Poly1305 yêu cầu mỗi **(key, nonce)** dùng để encrypt **duy nhất một message**.

**Hậu quả nếu reuse:** có thể lộ quan hệ giữa plaintexts và phá tính bảo mật/toàn vẹn của AEAD. Không thử reuse cùng key+nonce trên dữ liệu thật chỉ để xem điều gì xảy ra.

### Những tình huống cần test

1. Đếm sequence tăng đúng qua 0,1,2,... trong một session được quản lý.
2. Đổi key sau reconnect/rekey và reset sequence theo key mới.
3. Process restart không gây nonce collision dưới **cùng key** (tốt nhất rotation/session keys).
4. Dữ liệu song song có thread-safe nonce allocation, không lấy một counter mutable chưa đồng bộ.
5. Decrypt từ chối sequence/message ID cũ nếu protocol cần chống replay.
6. Encryption không nhận nonce 11 bytes hoặc key 16 bytes.
7. Không cache và gọi lại `doFinal` trên cùng encrypt cipher/IV để tạo message khác.
8. Không nhầm “random nonce 12 bytes” với **cam kết không bao giờ collision** ở quy mô vô hạn.

### Tại sao bài lab dùng random nonce?

Fixture encrypt **một message** duy nhất dưới key được tạo mới cho session, nên random 96-bit nonce là cách trình bày dễ hiểu. Một hệ thống nhiều messages cần **nonce management có cấu trúc**, giới hạn usage per key và kiểm key rotation theo protocol đã chuẩn hóa.

### Replay khác tampering

Một gói AEAD còn nguyên tag, AAD và ciphertext khi replay sẽ **vẫn qua tag check**. Nếu ứng dụng là thanh toán, cập nhật số dư hoặc lệnh điều khiển, người nhận phải kiểm **sequence/session ID/idempotency key**; không dựa vào `AEADBadTagException` để ngăn duplicate business operation.

## 16. Kiểm TLS theo cấu hình bảo mật còn được dùng

### TLS 1.3 và TLS 1.2

Trong môi trường Java 11/ứng dụng hiện đại, ưu tiên TLS 1.3, cho phép TLS 1.2 an toàn khi cần tương thích và tổ chức cho phép. **Không bật TLS 1.0/1.1/SSLv3 chỉ để test pass** hoặc tiếp tục handshake với peer cũ.

Mẫu cấu hình socket thử:

~~~java
SSLParameters params = socket.getSSLParameters();
params.setProtocols(new String[] { "TLSv1.3" });
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
~~~

**Đoạn minh họa** với `SSLSocket socket` của client. Không áp dụng cấu hình “HTTPS” này một cách máy móc cho server socket hoặc một giao thức danh tính khác mà không hiểu semantics.

### Thử downgrade và suite negotiation

Trong lab:

- Client chỉ bật TLS 1.3 và server chỉ bật TLS 1.2 → **bắt tay phải thất bại** vì không có shared version.
- Nếu cần chạy TLS 1.2, giới hạn suites theo security policy; không cho RC4, 3DES, static RSA key exchange, NULL/anonymous cipher suites trở lại.
- Khi testing suite ChaCha20, kiểm `getSupportedCipherSuites()` và `getEnabledCipherSuites()`; suite có thể **supported nhưng không enabled**, hoặc enabled nhưng peer không chọn.
- Không sửa system-wide `jdk.tls.disabledAlgorithms` để ép một thuật toán yếu hoạt động chỉ vì peer legacy.
- Test TLS 1.3 không đồng nghĩa kiểm thành công X25519 cụ thể nếu chưa ghi handshake named group từ JSSE diagnostics/approved tooling.

### Cert-specific tests

- Unknown CA/empty trust;
- Certificate đã hết hạn hoặc chưa đến hạn;
- Hostname không có trong SAN;
- Certificate chain không đầy đủ;
- Signature algorithm bị policy cấm;
- EKU/key usage không phù hợp server authentication;
- Client yêu cầu mutual TLS nhưng không gửi cert (nếu ứng dụng dùng mTLS);
- Certificate thay key khi pinning policy không cho;
- Revocation checks khi hạ tầng có OCSP/CRL policy phù hợp (không tự giả định mặc định luôn làm online revocation).

Đối với test cert hết hạn, tạo fixture expiry hợp lệ theo `keytool`/CA test, **không thay thời gian hệ thống production**.

## 17. Key agreement tests khó hơn: kẻ tấn công không nhất thiết gửi bytes rác

Một input công khai có thể:

1. **Malformed**: không decode được.
2. **Wrong group**: decode được nhưng không phù hợp X25519.
3. **Low order**: decode được theo format nhưng không thể dùng để tạo secret an toàn.
4. **Valid but unauthenticated**: hoàn toàn hợp lệ nhưng do attacker tạo.
5. **Replay old ephemeral key**: public key hợp lệ nhưng không thuộc handshake/session mong muốn.
6. **Cross-protocol confusion**: key hợp lệ, nhưng thiếu domain separation làm dùng nhầm mục đích.

Các kiểm thử `InvalidKeySpecException`/`InvalidKeyException` trong mã giải quyết **ba nhóm đầu**. Chúng **không** kiểm tra được nhóm 4–6. Đối với giao thức thực, cần identity binding/certificates/signatures/transcript hash/nonce/session identifiers.

**Không lấy kiểm thử XDH key agreement thành công làm chứng cứ TLS server authentication thành công.** Ngược lại, một TLS connection hợp lệ qua JSSE đã xác thực theo policy có thể sử dụng named group khác X25519; phải đọc kết quả handshake trước khi đưa ra khẳng định thuật toán cụ thể.

## 18. Phân tích khác biệt lỗi: invalid input hay tampering?

| Điểm bị hỏng | Exception thường gặp | Vì sao | Hành động |
| --- | --- | --- | --- |
| Keystore/cert path không tồn tại | `IOException` | Lab setup lỗi | Sửa fixture; **không** đánh dấu negative crypto PASS |
| Keystore password sai | `IOException`/`UnrecoverableKeyException` | Không đọc được private key | Sửa setup/quản lý secret |
| Trust path không đúng | `SSLHandshakeException` | Không xác thực chain | Từ chối peer, không fallback insecure |
| Hostname không đúng | `SSLHandshakeException` hoặc `SSLException` | Endpoint identity mismatch | Từ chối peer |
| Protocol không tương thích | `SSLHandshakeException` | Không negotiated version/suite | Cập nhật peer; không bật legacy |
| TCP bị đóng | `SocketException`/`EOFException` | Transport failure; chưa chắc cryptographic failure | Retry có giới hạn và idempotency |
| DER/SPKI public key hỏng | `InvalidKeySpecException` | Không parse key | Reject input |
| XDH public low order/wrong curve | `InvalidKeyException` hoặc spec error | Không an toàn/không tương thích | Reject key |
| ChaCha nonce sai độ dài | `InvalidAlgorithmParameterException` | Yêu cầu 12 bytes | Reject request/schema |
| ChaCha key sai độ dài | `InvalidKeyException` | Yêu cầu 32 bytes | Reject key configuration |
| Ciphertext/tag/AAD bị sửa | `AEADBadTagException` | Verification failed | Không giao plaintext |
| Ciphertext quá ngắn | `AEADBadTagException`/`IllegalBlockSizeException` tùy provider | Không có tag hợp lệ | Reject payload |
| Nonce reuse trong encryption | Có thể **không ném exception** | Vi phạm security contract | Enforce protocol uniqueness |
| Full replay hợp lệ | Có thể **không ném exception** | AEAD không lưu replay history | Dùng anti-replay state |
| MITM đưa X25519 public key hợp lệ | XDH có thể **không ném exception** | Chưa authenticate identity | Dùng TLS/certificate/signature |

**Fail closed:** không chuyển sang HTTP không mã hóa, bỏ certificate checks, giải mã bằng raw ChaCha20 hay chọn một key dự phòng mặc định khi TLS/AEAD thất bại.

## 19. Test dữ liệu bị sửa theo trường nào?

Một chương trình fault injection có thể tạo bản sao hợp lệ và sửa từng phần:

~~~text
Envelope (mô hình riêng của app, không phải TLS record)
+---------+-----------+--------------+--------------------+
| version | keyId     | nonce[12]    | ciphertext || tag |
+---------+-----------+--------------+--------------------+
      \        \             \                 \
       \        \             \                 +-- Flip data/tag
        \        \             +-- Wrong nonce
         \        +-- AAD binding: keyId mismatch
          +-- AAD binding: version mismatch

Chính AAD và key schedule quyết định metadata nào được xác thực.
~~~

Nếu app tự lưu `version`/`keyId` ở đầu file, hãy đặt những trường quan trọng vào **AAD**. Khi ciphertext được giải mã, AAD phải được tính lại từ **metadata không bị thay lén** và format phải có versioning chính xác.

### Invalid length/fuzzing

- Empty ciphertext;
- Ciphertext ngắn hơn 16-byte tag;
- Tag dài/short không đúng;
- Nonce 0, 11, 13, 64 bytes;
- Key 0, 16, 31, 33 bytes;
- Public key DER bị cắt 1 byte, đổi length field, append garbage;
- X25519 public low order;
- X448 public cho X25519 exchange;
- AAD null vs empty vs missing (quy tắc protocol phải rõ);
- Duplicate envelope/nonce/sequence;
- Very large input dẫn tới memory exhaustion.

**Mọi test có input rất lớn cần upper bound + memory/time limits.** Parser phải từ chối payload vượt giới hạn **trước khi cấp phát mảng lớn**, tránh DoS.

## 20. Tối ưu và benchmark: đo đúng thứ quan trọng

Phạm vi này thuộc **kiểm thử và tối ưu**, nhưng kết quả “chạy nhanh hơn” không có ý nghĩa nếu bỏ authentication checks.

### Metrics cần đo

| Nhóm | Metric | Không được bỏ |
| --- | --- | --- |
| TLS | Handshake success/failure, handshake latency, session resumption | Hostname/cert verification |
| TLS | CPU/bytes/request latency, negotiated protocol/suite | TLS record authentication |
| XDH | Key pair generation time, agreement time | Key validation/authentication |
| KDF | HKDF time, memory | Salt/info domain separation |
| ChaCha20-Poly1305 | Throughput MB/s, p99 encrypt/decrypt, CPU | Nonce uniqueness/tag verification |
| Negative test | Rejection rate/time, no plaintext release | Không được “catch all PASS” |
| Resource | Heap allocations, CPU, file/socket handles | Timeout, close và input size limit |

### Benchmark công bằng

1. Dùng cùng JDK/vendor/CPU quota, workloads và message sizes.
2. Warm up JIT trước khi đo, nhiều forks/runs; **không** tái dùng key+nonce để encrypt cùng plaintext hàng nghìn lần trong một benchmark.
3. Nếu test nhiều encryptions, tạo **fresh nonce duy nhất** cho từng message; chú ý không rekey mỗi message nếu muốn mô phỏng protocol thực nhưng phải quản lý nonce.
4. Đo riêng thời gian `KeyPairGenerator`/`KeyAgreement`, HKDF và AEAD, không trộn mọi thứ thành “ChaCha20 latency”.
5. Vẫn kiểm correctness/tag failure sau mỗi thay đổi provider/flags.
6. Đo tỉ lệ lỗi và thời gian fail khi input bị sửa, tránh timing/logging rò secret.
7. Với TLS, xác nhận cipher suite thực sự được negotiated; thay provider/JDK có thể đổi defaults.
8. Không bỏ authentication, hostname verification hay downgrade protocol để cải thiện số benchmark.
9. Không log raw keys, peer private material, session secrets hoặc plaintext chứa dữ liệu thật để debug.
10. Nếu dùng benchmark harness như JMH, nhớ measurement overhead, forks, generated inputs và nonce/key rotation.

**Đặc biệt:** So sánh `ChaCha20` thuần với `ChaCha20-Poly1305` rồi chọn raw ChaCha “vì nhanh hơn” là so sánh **khác security contract**; không được dùng nó để đưa ra quyết định production khi yêu cầu integrity.

## 21. CI test matrix khuyến nghị

| Case | Input | Kết quả mong đợi | Có trong hai demo? |
| --- | --- | --- | --- |
| TLS certificate trusted + đúng SAN | local `localhost` | Handshake thành công | Có |
| TLS trusted + sai SAN | `not-localhost.example` | `SSLException` | Có |
| TLS untrusted + đúng SAN | empty trust store | `SSLException` | Có |
| TLS protocol mismatch | client TLS1.3 / server TLS1.2 | Handshake failure | Hướng dẫn mở rộng |
| TLS expired cert | Fixture cert hết hạn | Reject theo trust policy | Hướng dẫn mở rộng |
| TLS modified encrypted record | Fault injection TLS proxy | Reject record/no bogus plaintext | Hướng dẫn mở rộng |
| X25519 valid pair | Alice, Bob | Shared secrets equal | Có |
| HKDF same input | Same secret/salt/info | Keys equal | Có |
| XDH malformed encoded key | Corrupt SPKI | Reject | Có |
| XDH low-order public | Zero u coordinate | Reject | Có |
| XDH wrong group | X448 public key | Reject | Có |
| XDH MITM valid key | Substitution by test proxy | Auth fails when protocol binds identity | Hướng dẫn, không giả TLS |
| AEAD valid message | Key/nonce/AAD chính xác | Plaintext equal | Có |
| AEAD ciphertext bit flip | Đổi byte đầu | Tag rejection | Có |
| AEAD tag bit flip | Đổi byte cuối | Tag rejection | Có |
| AEAD AAD mismatch | `seq=2` thay `seq=1` | Tag rejection | Có |
| AEAD wrong nonce | Same length but different | Tag rejection | Có |
| AEAD wrong key | 32-byte random other key | Tag rejection | Có |
| AEAD truncated payload | Bớt 1 byte | Rejected | Có |
| AEAD nonce length 11 | Invalid init parameters | Rejected | Có |
| AEAD key length 16 | Invalid key | Rejected | Có |
| Raw ChaCha20 altered bytes | Bit flip no tag | **Tampering not detected** | Có, minh họa lỗi |
| AEAD replay | Same valid envelope twice | App rejects duplicate based on state | Hướng dẫn mở rộng |
| Input oversized | > policy bound | Reject trước allocation khổng lồ | Hướng dẫn mở rộng |
| Concurrent nonce allocation | Parallel encrypt operations | Không trùng (key,nonce) | Hướng dẫn mở rộng |

### Điều kiện PASS

- Test hợp lệ trả đúng plaintext, protocol, message content.
- Mỗi test âm tính thực sự đưa dữ liệu sai vào lớp đang kiểm.
- Test từ chối **đúng cơ chế**, không chỉ fail vì fixture/cổng không hoạt động.
- Không giao dữ liệu chưa xác thực cho downstream business logic.
- Input hết hạn/khóa sai không dẫn đến fallback không an toàn.
- Check resource leak/timeout sau failure.
- Không dùng keys/password/cert test trong production và không lưu log nhạy cảm.

## 22. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| “TLS handshake thành công = chắc đúng server.” | SSLSocket có thể chưa bật hostname verification | Kiểm trust chain + endpoint identification |
| “Certificate self-signed trusted = phù hợp mọi hostname.” | Không khớp SAN vẫn nguy hiểm | Bật hostname verification |
| “Bắt mọi Exception là PASS.” | Lỗi mạng hoặc bug bị hiểu thành security reject | Bắt exception phù hợp + kiểm happy path |
| “X25519 shared secret bằng nhau = peer trusted.” | MITM vẫn có thể thay public keys | Authenticated key exchange / TLS |
| “Public key có 32 bytes là đủ hợp lệ.” | Format/curve/low-order có thể sai | KeyFactory/spec validation |
| “X448 có thể dùng như X25519 nếu cắt bytes.” | Không đúng group | Reject wrong group |
| “ChaCha20 đã phát hiện bit flips.” | Stream cipher không xác thực | Dùng ChaCha20-Poly1305 |
| “ChaCha20ParameterSpec dùng cho ChaCha20-Poly1305.” | Wrong parameters | Dùng IvParameterSpec 12 bytes |
| “Cipher.init thành công thì key và nonce đúng.” | Sai giá trị có thể chỉ lộ tại doFinal | Kiểm AEAD tag |
| “updateAAD sau khi decrypt data.” | Có thể ném IllegalStateException / sai protocol | AAD trước data |
| “doFinal() lỗi nhưng plaintext tạm vẫn dùng được.” | Có thể đưa dữ liệu giả vào business logic | Chỉ accept sau tag validation |
| “Nonce có thể lặp lại vì không phải secret.” | Vi phạm AEAD security | Unique per key |
| “Random nonce đảm bảo không bao giờ collision.” | Không có đảm bảo tuyệt đối vô hạn | Bound messages + nonce schedule |
| “AEAD ngăn replay hoàn toàn.” | Replay nguyên gói vẫn có tag hợp lệ | Anti-replay/app sequence tracking |
| “XDH hợp lệ thì không cần HKDF.” | Dùng raw secret thiếu key separation/context | KDF theo protocol |
| “HKDF giải quyết MITM.” | KDF không authenticate peer | Certificate/signature/PSK |
| “TLS1.3 luôn dùng ChaCha20 hoặc X25519.” | Negotiation chọn thuật toán phù hợp | Đọc session/capabilities |
| “Tắt hostname verification để benchmark.” | Mất bảo mật trọng yếu | Benchmark với đúng validation |
| “Dùng trust-all TrustManager trong test rồi quên bỏ.” | Rủi ro MITM production | Trust store thử có phạm vi rõ |
| “Log key/ciphertext toàn bộ để debug.” | Lộ secrets và diagnostic artifacts | Log metadata đã redaction |
| “Dùng TLS debug flags trên prod lâu dài.” | Logs lớn và nhạy cảm | Bật có thời hạn/kiểm soát |
| “Chỉ có một negative test là đủ.” | Không bao phủ trust, host, protocol, AEAD, replay | Ma trận lỗi có phân lớp |
| “Một JVM thử cho kết quả đúng thì mọi provider giống nhau.” | Version, provider policies khác | Test đúng JDK/vendor sẽ deploy |

## 23. Security checklist trước khi triển khai

- [ ] TLS trust store và hostname verification hoạt động; không có trust-all/allow-all.
- [ ] Không bật TLS 1.0/1.1/SSLv3 và không vô hiệu hóa algorithm constraints.
- [ ] Khi cần TLS1.2, chỉ dùng suites đáp ứng chính sách hiện hành.
- [ ] Certificate SAN/expiry/EKU/path validation được kiểm thử.
- [ ] Nếu dùng mTLS, xác minh cả client certificate và authorization.
- [ ] Không viết lại TLS record encryption bằng `Cipher`.
- [ ] X25519 peer keys được authenticate/bind vào session transcript.
- [ ] Không chấp nhận malformed/wrong-group/low-order XDH public inputs.
- [ ] Không dùng raw shared secret trực tiếp cho nhiều key purposes.
- [ ] ChaCha20-Poly1305 dùng **32-byte key**, **12-byte nonce**, unique per key.
- [ ] AAD chứa đúng metadata/context cần xác thực, được xác định rõ format/version.
- [ ] Ciphertext/tag/AAD/key/nonce sai khiến operation **reject**.
- [ ] Không xử lý plaintext trước khi tag verify thành công.
- [ ] Application có anti-replay/idempotency nếu thông điệp có side effects.
- [ ] Không sử dụng ChaCha20 thuần cho dữ liệu cần integrity.
- [ ] Negative tests assert exception category, không swallow unexpected exceptions.
- [ ] Key material được cất giữ an toàn, có key rotation và deletion policy.
- [ ] Data kích cỡ lớn bị giới hạn trước khi parse/allocate.
- [ ] Không để password `changeit` của lab trong production.
- [ ] Logs/metrics tránh raw secret/PII, có retention và ACL.
- [ ] Kiểm thử lại trên đúng Java 11 update/vendor hoặc JDK hiện đại sẽ chạy production.
- [ ] Kiểm timeout, thread/socket/keystore file cleanup khi test thất bại.

## 24. Câu hỏi tự kiểm tra

**1.** Vì sao TLS client cần kiểm cả certificate chain và hostname?

Vì certificate có thể được trust nhưng thuộc **server khác**. Nếu không kiểm hostname, có thể tin nhầm peer dù certificate được ký hợp lệ.

**2.** Test tự tạo certificate self-signed có được dùng nó làm trust anchor trong lab không?

**Được trong lab khép kín**, nếu chính bạn kiểm soát key và trust store để chứng minh logic. Không biến lab trust store thành cấu hình trust-all.

**3.** X25519 tạo cùng secret hai phía có nghĩa không còn MITM?

**Không.** XDH tự nó không chứng minh peer identity. Cần authentication/transcript binding bằng protocol thích hợp.

**4.** `KeyFactory.generatePublic` không báo lỗi với input X25519, nghĩa public key luôn an toàn?

**Không.** Cần xét group, low-order point, key agreement và đối tác có được xác thực không.

**5.** ChaCha20 thuần decrypt ciphertext sau khi đổi một bit mà không ném exception, có bất thường không?

**Không.** Đó là đặc tính stream cipher **không kèm authentication**. Dùng ChaCha20-Poly1305 cho integrity.

**6.** Với ChaCha20-Poly1305, tag sai được phát hiện ở đâu?

Thông thường ở `Cipher.doFinal` khi decrypt và xác minh tag, với exception như `AEADBadTagException`.

**7.** Nonce 11 byte và nonce đúng 12 byte nhưng sai giá trị khác nhau thế nào?

Nonce 11 byte có thể bị từ chối **ngay ở init**; nonce 12 byte sai giá trị có thể init thành công nhưng **tag check thất bại**.

**8.** AAD bị sửa mà ciphertext không đổi, tag có hợp lệ không?

**Không.** AEAD xác thực AAD cùng ciphertext, nên AAD mismatch gây verification failure.

**9.** Có thể tái sử dụng cùng nonce để encrypt message khác với cùng ChaCha20 key không?

**Không.** Phải đảm bảo unique pair `(key,nonce)` cho mỗi encryption operation.

**10.** AEAD tự chặn người gửi lại nguyên ciphertext/tag hợp lệ hai lần không?

**Không.** Gói nguyên vẹn có thể qua tag verification; application phải dùng anti-replay state/sequence/idempotency.

**11.** Vì sao không catch `Exception` cho mọi negative test?

Vì test có thể fail do lỗi fixture, kết nối, NPE hoặc code bug, chứ không phải cơ chế mật mã thực sự từ chối input xấu.

**12.** Chạy TLS 1.3 có chắc đang dùng ChaCha20-Poly1305 và X25519?

**Không.** Phải xác minh negotiated cipher suite và named group nếu cần bằng công cụ handshake diagnostics phù hợp.

## 25. Tài liệu chính thức còn áp dụng

1. [Oracle Java 11 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/11/security/java-secure-socket-extension-jsse-reference-guide.html): TLS 1.3 handshake, cipher suites, certificate validation, debugging và lỗi JSSE.
2. [Oracle Java 11 — SSLParameters](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setProtocols`, `setCipherSuites`, `setEndpointIdentificationAlgorithm("HTTPS")`.
3. [Oracle Java 11 — SSLSocket](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLSocket.html): handshake, enabled suites/protocols, session.
4. [Oracle Java 11 — SSLContext](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLContext.html): key managers, trust managers và TLS contexts.
5. [Oracle Java 11 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/11/docs/specs/security/standard-names.html): XDH, X25519, X448, ChaCha20/ChaCha20-Poly1305, SSLContext TLS.
6. [Oracle Java 11 — Cipher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/Cipher.html): AEAD, AAD order, nonce uniqueness, init/doFinal.
7. [Oracle Java 11 — AEADBadTagException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/AEADBadTagException.html): lỗi xác minh authentication tag.
8. [Oracle Java 11 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): nonce 12 bytes, initial counter cho ChaCha20 thuần.
9. [Oracle Java 11 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/spec/NamedParameterSpec.html) và [XECPublicKeySpec](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/spec/XECPublicKeySpec.html): X25519/448 parameters và public-key spec.
10. [OpenJDK JEP 324 — Key Agreement with Curve25519 and Curve448](https://openjdk.org/jeps/324): XDH in JDK 11.
11. [OpenJDK JEP 329 — ChaCha20 and Poly1305 Cryptographic Algorithms](https://openjdk.org/jeps/329): ChaCha20 and ChaCha20-Poly1305 in JDK 11.
12. [RFC 7748 — Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): X25519/X448 và public point/security considerations.
13. [RFC 8439 — ChaCha20 and Poly1305 for IETF Protocols](https://www.rfc-editor.org/rfc/rfc8439): 256-bit key, 96-bit nonce, Poly1305 tag và AEAD security.
14. [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869): extract/expand và domain separation.
15. [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake, key schedule, AEAD records và authentication.
16. [Oracle JDK 26 — JDK Providers](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): thuật toán được các providers hỗ trợ trên JDK hiện đại.
17. [Oracle JDK 27 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): TLS hiện hành, debugging/compatibility và an toàn cấu hình.

**Kết luận:** TLS đúng cấu hình phải **xác minh trust và hostname**, không chỉ “mã hóa thành công”. XDH phải **xác thực public key/đối tác** và có KDF/context binding; việc key agreement thành công không ngăn MITM. ChaCha20 thuần **không phát hiện ciphertext bị sửa**; với dữ liệu cần integrity, dùng **ChaCha20-Poly1305** với nonce duy nhất, AAD đúng và chỉ nhận plaintext **sau tag verification**. Negative tests tốt kiểm từng lớp lỗi cụ thể, bao gồm input format, trust/identity, curve/group, tag, AAD, nonce, key, replay và resource cleanup, đồng thời không dùng thử nghiệm mật mã để làm yếu cấu hình production.