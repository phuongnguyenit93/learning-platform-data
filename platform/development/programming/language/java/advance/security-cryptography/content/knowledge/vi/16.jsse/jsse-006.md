# 16.6 X509ExtendedKeyManager chọn alias và X509ExtendedTrustManager kiểm tra đối tác

## 1. Hai trách nhiệm khác nhau trong JSSE

**JSSE (Java Secure Socket Extension)** thực hiện TLS bằng các thành phần như `SSLContext`, `SSLSocket`, `SSLEngine`, `KeyManager` và `TrustManager`. Trong handshake TLS dùng certificate, có **hai câu hỏi tách biệt**:

1. **“Tôi sẽ trình chứng thư và dùng khóa riêng nào?”** — `X509ExtendedKeyManager` chọn *alias* trỏ đến một cặp private key + certificate chain phù hợp cho **chính endpoint này**. Khi JSSE cần chữ ký hoặc thao tác dùng khóa riêng, key manager cung cấp private key qua alias đã chọn.
2. **“Tôi có tin certificate của đầu bên kia không?”** — `X509ExtendedTrustManager` xác minh **certificate chain của peer**, ràng buộc PKIX, mục đích sử dụng, thuật toán và **ngữ cảnh kết nối** (socket/engine) theo cấu hình và chính sách. Nếu không tin, nó phải ném `CertificateException` thay vì cho handshake hoàn thành.

Hai thành phần đều dùng thuật ngữ X.509, nhưng **không thay thế nhau**:

| Thành phần | Đầu vào chính | Quyết định | Đầu ra |
| --- | --- | --- | --- |
| `X509ExtendedKeyManager` | `keyType`, `issuers`, `Socket` hoặc `SSLEngine`, local keystore | Chọn local alias để client/server trình chứng thư phù hợp | `String alias` hoặc `null`; `getPrivateKey` và `getCertificateChain` |
| `X509ExtendedTrustManager` | `X509Certificate[] chain` từ **peer**, `authType` và kết nối | Peer chain có đáng tin, hợp lệ và phù hợp ràng buộc không? | Không trả về khi chấp nhận; ném `CertificateException` khi từ chối |
| `KeyManagerFactory` | KeyStore chứa private key và certificate chain, password/protection | Khởi tạo provider key managers | `KeyManager[]` |
| `TrustManagerFactory` | TrustStore hoặc PKIX trust anchors/policy | Khởi tạo trust managers | `TrustManager[]` |

Một certificate có thể **được chọn để gửi** bởi key manager nhưng **bị từ chối** bởi trust manager của đối tác. Ngược lại, đối tác có thể tin chain, nhưng handshake vẫn thất bại vì key manager không tìm được alias/khóa riêng tương thích.

### Vai trò client, server và mTLS

```text
                   TLS server                         TLS client
        +-----------------------------+    +-----------------------------+
        | KeyManager                  |    | KeyManager (khi mTLS)       |
        | chọn alias chứng thư server  |    | chọn alias chứng thư client |
        +--------------+--------------+    +--------------+--------------+
                       |                                  |
        gửi Certificate/CertificateVerify -->     <-- gửi Certificate/
                                              CertificateVerify (mTLS)
                       |                                  |
        +--------------v--------------+    +--------------v--------------+
        | TrustManager                 |    | TrustManager                |
        | kiểm chứng client (nếu mTLS) |    | kiểm chứng server           |
        +-----------------------------+    +-----------------------------+
```

Trong TLS **server-auth-only**, client thường không phải gửi certificate và key manager client có thể không được gọi để chọn alias. Trong **mutual TLS (mTLS)**, server yêu cầu client certificate; **cả hai phía** thường có key manager để trình chứng thư của mình và trust manager để kiểm chứng bên kia.

**Không bao giờ biến “chọn được alias” thành “certificate được peer tin”.** Alias chỉ là tên của local entry (thường trong `KeyStore`), không phải trust decision.

## 2. KeyManager, X509KeyManager và X509ExtendedKeyManager

`X509KeyManager` là interface dùng chọn credential X.509 với `Socket`. `X509ExtendedKeyManager` mở rộng lớp này, bổ sung overload cho **`SSLEngine`**. Khi viết TLS client/server trên NIO, HTTP framework, proxy hoặc custom network stack sử dụng `SSLEngine`, các overload extended là thiết yếu.

| Method | Chức năng |
| --- | --- |
| `getClientAliases(String keyType, Principal[] issuers)` | Liệt kê alias local có thể dùng làm client certificate cho loại key và issuer constraints |
| `chooseClientAlias(String[] keyTypes, Principal[] issuers, Socket socket)` | Chọn một alias client phù hợp khi handshake bằng socket |
| `getServerAliases(String keyType, Principal[] issuers)` | Liệt kê alias có thể dùng làm server certificate cho loại key/issuers |
| `chooseServerAlias(String keyType, Principal[] issuers, Socket socket)` | Chọn một alias server trên handshake socket |
| `chooseEngineClientAlias(String[] keyTypes, Principal[] issuers, SSLEngine engine)` | Chọn client alias cho `SSLEngine` |
| `chooseEngineServerAlias(String keyType, Principal[] issuers, SSLEngine engine)` | Chọn server alias cho `SSLEngine` |
| `getCertificateChain(String alias)` | Lấy chuỗi certificate trình với alias, thường từ leaf đến intermediate |
| `getPrivateKey(String alias)` | Lấy private key **của local alias** để ký/handshake; có thể là opaque provider handle |

### Ý nghĩa của keyType, issuers và alias

- **`keyType`:** loại khóa/thuật toán phù hợp ngữ cảnh handshake, ví dụ `"RSA"`, `"EC"`; các tên giá trị và ràng buộc lựa chọn có thể phụ thuộc provider, TLS version và signature schemes. **Không** tự kết luận TLS 1.3 cipher suite tên `TLS_AES_128_GCM_SHA256` yêu cầu khóa AES để chọn certificate; TLS 1.3 đàm phán signature scheme riêng.
- **`String[] keyTypes` phía client:** nhiều loại credential có thể phù hợp theo đề nghị của server. Key manager cân nhắc những loại được phép và issuer constraints; trả `null` nếu không có credential phù hợp.
- **`Principal[] issuers`:** danh sách CA distinguished names mà phía yêu cầu certificate sẵn sàng chấp nhận, hoặc `null` trong các trường hợp không có giới hạn. Đây là **gợi ý/ràng buộc lựa chọn**, không phải giấy xác nhận một chain đáng tin. Phải truyền/áp dụng constraints đúng ngữ nghĩa thay vì bỏ qua.
- **`alias`:** định danh local key entry được manager biết; có thể tương ứng một `KeyStore` alias, nhưng một provider có thể tạo alias nội bộ. Đừng giả định alias là hostname, user ID, chứng minh danh tính hay mã định danh ổn định giữa các provider.
- **`getCertificateChain(alias)` và `getPrivateKey(alias)`:** phải tương ứng với **cùng credential**. Private key phải khớp public key trong certificate leaf. Không trộn chain của alias A với private key của alias B.

Alias selection có thể cần thêm thông tin handshake như **SNI**, TLS version, signature algorithms và key usages. Với `Socket`, có thể xem handshake session trên `SSLSocket` khi có; với `SSLEngine` có thể xem `engine.getHandshakeSession()` và các thông tin liên quan. **Handshake session có thể là `null` nếu chưa sẵn sàng**; không coi giá trị thiếu là lý do trả credential bừa bãi.

### Vì sao không hardcode `"server"` làm alias cho mọi handshake?

Khi server có nhiều certificate (ví dụ RSA và ECDSA, hoặc nhiều virtual hosts), chọn alias phải tính đến:

- keyType và signature schemes được peer hỗ trợ;
- SNI và virtual host **đã được cấu hình/ủy quyền**;
- certificate SAN, chain, thời hạn, KU/EKU, các thuật toán bị disabled;
- issuer constraints và policy;
- cipher/TLS version, khả năng thao tác của provider hoặc HSM.

Chỉ vì một alias tên `"server"` tồn tại không có nghĩa nó là lựa chọn hợp lệ cho mọi SNI/key type. Nếu không có credential hợp lệ, **trả `null`/để handshake thất bại**, không chọn nhầm tenant hay trình certificate sai danh tính.

## 3. TrustManager và X509ExtendedTrustManager

`X509TrustManager` có ba method cơ bản:

```java
void checkClientTrusted(X509Certificate[] chain, String authType)
        throws CertificateException;
void checkServerTrusted(X509Certificate[] chain, String authType)
        throws CertificateException;
X509Certificate[] getAcceptedIssuers();
```

`X509ExtendedTrustManager` mở rộng với **bốn overload có ngữ cảnh**:

```java
void checkClientTrusted(
        X509Certificate[] chain, String authType, Socket socket)
        throws CertificateException;
void checkServerTrusted(
        X509Certificate[] chain, String authType, Socket socket)
        throws CertificateException;
void checkClientTrusted(
        X509Certificate[] chain, String authType, SSLEngine engine)
        throws CertificateException;
void checkServerTrusted(
        X509Certificate[] chain, String authType, SSLEngine engine)
        throws CertificateException;
```

Các overload nhận `Socket`/`SSLEngine` rất quan trọng: provider có thể sử dụng **SSLParameters, endpoint identification algorithm, handshake session, requested server name, negotiated signature algorithm và TLS-specific constraints** khi xác minh peer. Phần kiểm tra **certificate path** thường cần trust anchor, validity, chữ ký, BasicConstraints, KeyUsage/ExtendedKeyUsage, algorithm constraints, critical extensions và chính sách thu hồi theo profile.

**Ranh giới quan trọng:** overload `checkServerTrusted(chain, authType, socket)` **không được thay bằng** `delegate.checkServerTrusted(chain, authType)` khi đang có socket, vì bạn có thể mất các kiểm tra phụ thuộc ngữ cảnh, đặc biệt hostname/endpoint identification. Tương tự, trong `SSLEngine` phải truyền nguyên engine tới overload extended của delegate.

### “Chấp nhận” không phải trả true

Method `checkServerTrusted`/`checkClientTrusted` có return type `void`:

- **Thành công:** kết thúc bình thường (không exception).
- **Thất bại:** ném `CertificateException` (hoặc subtype) để TLS handshake từ chối peer.

Một custom trust manager như dưới đây **không an toàn**:

```java
// CỐ TÌNH SAI: KHÔNG DÙNG TRONG SẢN PHẨM.
@Override public void checkServerTrusted(
        X509Certificate[] chain, String authType) {
    // Do nothing => trust-all, không kiểm tra certificate chain.
}
```

Sự tồn tại `getAcceptedIssuers()==new X509Certificate[0]` cũng **không** làm các method `check...Trusted` tự an toàn. Không sử dụng trust-all để “fix PKIX path building failed” hoặc “fix hostname mismatch”.

### Vai trò của authType

`authType` là tham số do JSSE cung cấp về loại xác thực được sử dụng trong handshake theo hợp đồng API và provider, **không phải OID EKU `serverAuth`/`clientAuth`** và không phải giá trị do app chọn tùy ý. Không viết policy kiểu `authType.equals("serverAuth")`. Không tự suy từ tên cipher suite TLS 1.3 ra giá trị `authType` cố định: TLS version/signature schemes/provider có thể thay đổi cách biểu diễn.

## 4. KeyStore và TrustStore: vật liệu khác nhau

Trong JSSE thường có **hai store với vai trò khác nhau**:

| Store | Nội dung | Dùng bởi | Có chứa private key local? |
| --- | --- | --- | --- |
| **KeyStore** | `PrivateKeyEntry`: private key + certificate chain tương ứng | `KeyManagerFactory` | Có, với credential phần mềm; HSM có thể dùng handle |
| **TrustStore** | `TrustedCertificateEntry` hoặc trust anchors/certificates tin cậy | `TrustManagerFactory` | Thường **không cần** private key |
| **Server key store** | Server private key và server certificate/chain | Server key manager | Có |
| **Client key store** | Client private key và client certificate/chain | Client key manager khi mTLS | Có |
| **Server trust store** | CA/certificate được server tin cho **client certificate** | Server trust manager | Không |
| **Client trust store** | CA/certificate được client tin cho **server certificate** | Client trust manager | Không |

Khi mTLS, **server kiểm client**, **client kiểm server**. Nếu đặt sai truststore (ví dụ client chỉ tin client certificate thay vì server issuer), handshake có thể fail dù cả key managers chọn alias hợp lệ.

### Factory khởi tạo đúng cách

Đoạn minh họa trong một phương thức Java, chưa phải chương trình độc lập:

```java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(keyStore, keyPasswordChars);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext ctx = SSLContext.getInstance("TLS");
ctx.init(kmf.getKeyManagers(), tmf.getTrustManagers(),
         new SecureRandom());
```

Chú ý `KeyManagerFactory.getDefaultAlgorithm()` hoặc `TrustManagerFactory.getDefaultAlgorithm()` **chọn algorithm factory**, không đồng nghĩa “đã dùng đúng KeyStore”, “đã bật hostname verification” hoặc “đã cấu hình mTLS”. Những điều này cần được cấu hình riêng trên socket/engine/server.

**Một số factory chỉ cung cấp `X509KeyManager`/`X509TrustManager` cơ bản hoặc một implementation khác với JSSE profile:** ví dụ chạy trong bài kiểm tra rõ ràng yêu cầu kiểu `X509Extended...`. Khi không có loại extended tương ứng, ví dụ **fail closed bằng `IllegalStateException`**, không tùy tiện cast hay tự tạo trust-all adapter.

## 5. Cấu hình handshake mTLS an toàn

Đối với một mTLS channel qua `SSLSocket`:

1. Server có certificate + private key phù hợp hostname/thuật toán và đã khởi tạo `KeyManagerFactory`.
2. Client có `TrustManagerFactory` gắn trust anchors cho server. Client bật **endpoint identification**: `socket.getSSLParameters().setEndpointIdentificationAlgorithm("HTTPS")` và **áp lại** `socket.setSSLParameters(...)` trước `startHandshake()`.
3. Server cấu hình **`setNeedClientAuth(true)`**, không chỉ `setWantClientAuth(true)`. `need` yêu cầu client phải cung cấp certificate hợp lệ; `want` vẫn có thể cho phép peer không có certificate.
4. Client có key manager cung cấp client certificate/private key phù hợp issuer/key type; server có trust manager tin issuer/client certificate theo policy.
5. Cả hai chạy TLS handshake; `X509ExtendedKeyManager` được gọi để chọn alias phù hợp và `X509ExtendedTrustManager` được gọi để kiểm peer.
6. Sau thành công, ứng dụng **vẫn phải** thực hiện authorization dựa trên danh tính đã xác minh: role, tenant, endpoint/purpose, ACL, scopes. mTLS xác thực certificate **không** cho phép tất cả API tự động.

Nếu ứng dụng dùng NIO/`SSLEngine`, phải cài **cả các overload `chooseEngine...Alias` và `check...Trusted(..., SSLEngine)`**, rồi đảm bảo peer host và endpoint identification configured hợp lý. Dùng các overload nhận `Socket` cho engine là sai bối cảnh.

### SSLParameters và hostname verification

Trong raw `SSLSocket` client, một `TrustManager` xác minh chain **không tự bảo đảm** hostname được kiểm nếu không bật endpoint identification tương ứng. Với HTTPS client frameworks, cơ chế này thường được stack cấu hình cho bạn; với raw socket/engine cần kiểm tra.

Ví dụ:

```java
// Đoạn minh họa, socket phải là SSLSocket client chưa bắt tay.
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
```

Chữ `"HTTPS"` ở đây là endpoint identification algorithm theo SSLParameters, **không phải** TLS protocol string, không phải cipher suite. Chứng thư server cho IP `127.0.0.1` cần SAN kiểu iPAddress phù hợp; chỉ `CN=localhost` không đủ thay thế SAN trong giao thức hiện đại.

## 6. Java 17+ thực hành: đóng gói extended managers không bỏ qua trust

Bài thực hành chạy **server và client trên loopback `127.0.0.1`** với certificate demo:

- Hai local KeyStores riêng `server.p12`/`client.p12`, mỗi store chỉ có một private key alias và certificate tự ký cho riêng peer.
- Hai truststores riêng `server-trust.p12`/`client-trust.p12`. Server-trust tin certificate client test; client-trust tin certificate server test.
- `ObservedKeyManager extends X509ExtendedKeyManager` **ủy quyền cho manager do KeyManagerFactory tạo**, đếm các lần chọn alias thành công. Không log alias/private key/certificate chain để tránh lộ metadata không cần thiết.
- `ObservedTrustManager extends X509ExtendedTrustManager` **ủy quyền cho delegate đúng overload**; tăng bộ đếm **chỉ sau khi delegate kiểm tra thành công**. Không tự cài “trust-all”.
- Handshake mTLS bắt buộc client certificate, kiểm tra HTTPS endpoint identity theo IP SAN và trao đổi một byte application data sau handshake.
- Chạy hai phiên riêng biệt **TLSv1.3** và **TLSv1.2**, kiểm tra cả hai phía thống nhất negotiated protocol.

**Bảo mật:** Đây là chương trình demo với **chứng thư tự ký tạm** được chính ứng dụng test import làm trust anchor. Trong sản phẩm, chỉ tin CA hoặc public key/certificate được phân phối bằng kênh đáng tin; không nhập chứng thư do remote peer đưa rồi dùng ngay làm trust anchor.

### 6.1 Tạo chứng thư và truststores (PowerShell)

Chạy những lệnh sau trong **cùng phiên PowerShell** với JDK 17+ có `keytool`. Hai certificate ở đây là test fixtures, password `changeit` chỉ để minh họa.

```powershell
$t = Join-Path $env:TEMP ("extended-managers-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $t | Out-Null
$pw = "changeit"  # DEMO ONLY; không hardcode password sản phẩm.

# Server: SAN có iPAddress 127.0.0.1 để client xác minh hostname/IP.
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost" -ext "SAN=ip:127.0.0.1,dns:localhost" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -validity 7 -storetype PKCS12 -keystore (Join-Path $t "server.p12") -storepass $pw -keypass $pw -noprompt

# Client: certificate dùng mTLS client authentication.
keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=client-demo" -ext "KU:critical=digitalSignature" -ext "EKU=clientAuth" -validity 7 -storetype PKCS12 -keystore (Join-Path $t "client.p12") -storepass $pw -keypass $pw -noprompt

# Export CERTIFICATE PUBLIC, không phải private key.
keytool -exportcert -alias server -keystore (Join-Path $t "server.p12") -storepass $pw -rfc -file (Join-Path $t "server.pem")
keytool -exportcert -alias client -keystore (Join-Path $t "client.p12") -storepass $pw -rfc -file (Join-Path $t "client.pem")

# Server tin client, client tin server.
keytool -importcert -alias client -file (Join-Path $t "client.pem") -keystore (Join-Path $t "server-trust.p12") -storetype PKCS12 -storepass $pw -noprompt
keytool -importcert -alias server -file (Join-Path $t "server.pem") -keystore (Join-Path $t "client-trust.p12") -storetype PKCS12 -storepass $pw -noprompt
```

`-noprompt` chỉ dùng trong fixture mà bạn vừa tự tạo. **Không tự động import remote/unverified certificates** vào truststore production. Không reuse `server.p12`/`client.p12` này cho một dịch vụ thật.

### 6.2 Chương trình Java hoàn chỉnh

Lưu thành **`ExtendedManagersMutualTlsDemo.java`** trong thư mục làm việc (khác thư mục `$t` cũng được). Mã tương thích **Java 17+**, gồm toàn bộ sáu overload trust manager, bốn đường lựa chọn alias và các getter cần có của key manager.

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.*;

public final class ExtendedManagersMutualTlsDemo {
    private static KeyStore load(Path path, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(path)) {
            store.load(stream, password);
        }
        return store;
    }

    private static X509ExtendedKeyManager keyManager(
            Path path, char[] password) throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(load(path, password), password);
        for (KeyManager manager : factory.getKeyManagers()) {
            if (manager instanceof X509ExtendedKeyManager ext) return ext;
        }
        throw new IllegalStateException("Extended key manager unavailable");
    }

    private static X509ExtendedTrustManager trustManager(
            Path path, char[] password) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(load(path, password));
        for (TrustManager manager : factory.getTrustManagers()) {
            if (manager instanceof X509ExtendedTrustManager ext) return ext;
        }
        throw new IllegalStateException("Extended trust manager unavailable");
    }

    private static final class ObservedKeyManager extends X509ExtendedKeyManager {
        private final X509ExtendedKeyManager base;
        final AtomicInteger serverSelections = new AtomicInteger();
        final AtomicInteger clientSelections = new AtomicInteger();

        ObservedKeyManager(X509ExtendedKeyManager base) { this.base = base; }
        private String count(String alias, boolean server) {
            if (alias != null) {
                (server ? serverSelections : clientSelections).incrementAndGet();
            }
            return alias;
        }
        @Override public String chooseClientAlias(
                String[] types, java.security.Principal[] issuers, Socket socket) {
            return count(base.chooseClientAlias(types, issuers, socket), false);
        }
        @Override public String chooseServerAlias(
                String type, java.security.Principal[] issuers, Socket socket) {
            return count(base.chooseServerAlias(type, issuers, socket), true);
        }
        @Override public String chooseEngineClientAlias(
                String[] types, java.security.Principal[] issuers, SSLEngine engine) {
            return count(base.chooseEngineClientAlias(types, issuers, engine), false);
        }
        @Override public String chooseEngineServerAlias(
                String type, java.security.Principal[] issuers, SSLEngine engine) {
            return count(base.chooseEngineServerAlias(type, issuers, engine), true);
        }
        @Override public String[] getClientAliases(
                String type, java.security.Principal[] issuers) {
            return base.getClientAliases(type, issuers);
        }
        @Override public String[] getServerAliases(
                String type, java.security.Principal[] issuers) {
            return base.getServerAliases(type, issuers);
        }
        @Override public X509Certificate[] getCertificateChain(String alias) {
            return base.getCertificateChain(alias);
        }
        @Override public PrivateKey getPrivateKey(String alias) {
            return base.getPrivateKey(alias);
        }
    }

    private static final class ObservedTrustManager extends X509ExtendedTrustManager {
        private final X509ExtendedTrustManager base;
        final AtomicInteger serverChecks = new AtomicInteger();
        final AtomicInteger clientChecks = new AtomicInteger();

        ObservedTrustManager(X509ExtendedTrustManager base) { this.base = base; }
        @Override public void checkServerTrusted(
                X509Certificate[] chain, String authType, Socket socket)
                throws CertificateException {
            base.checkServerTrusted(chain, authType, socket);
            serverChecks.incrementAndGet();
        }
        @Override public void checkClientTrusted(
                X509Certificate[] chain, String authType, Socket socket)
                throws CertificateException {
            base.checkClientTrusted(chain, authType, socket);
            clientChecks.incrementAndGet();
        }
        @Override public void checkServerTrusted(
                X509Certificate[] chain, String authType, SSLEngine engine)
                throws CertificateException {
            base.checkServerTrusted(chain, authType, engine);
            serverChecks.incrementAndGet();
        }
        @Override public void checkClientTrusted(
                X509Certificate[] chain, String authType, SSLEngine engine)
                throws CertificateException {
            base.checkClientTrusted(chain, authType, engine);
            clientChecks.incrementAndGet();
        }
        @Override public void checkServerTrusted(
                X509Certificate[] chain, String authType)
                throws CertificateException {
            base.checkServerTrusted(chain, authType);
            serverChecks.incrementAndGet();
        }
        @Override public void checkClientTrusted(
                X509Certificate[] chain, String authType)
                throws CertificateException {
            base.checkClientTrusted(chain, authType);
            clientChecks.incrementAndGet();
        }
        @Override public X509Certificate[] getAcceptedIssuers() {
            return base.getAcceptedIssuers();
        }
    }

    private record Side(SSLContext context, ObservedKeyManager key,
                        ObservedTrustManager trust) {}

    private static Side side(Path keys, Path trust, char[] password)
            throws Exception {
        ObservedKeyManager km = new ObservedKeyManager(keyManager(keys, password));
        ObservedTrustManager tm = new ObservedTrustManager(trustManager(trust, password));
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(new KeyManager[]{km}, new TrustManager[]{tm}, new SecureRandom());
        return new Side(context, km, tm);
    }

    private static void test(String version, Side server, Side client)
            throws Exception {
        int sAlias = server.key.serverSelections.get();
        int cAlias = client.key.clientSelections.get();
        int sTrust = server.trust.clientChecks.get();
        int cTrust = client.trust.serverChecks.get();
        try (SSLServerSocket listener = (SSLServerSocket)
                server.context.getServerSocketFactory().createServerSocket(
                        0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(20000);
            listener.setEnabledProtocols(new String[]{version});
            listener.setNeedClientAuth(true);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> future = executor.submit(() -> {
                    try (SSLSocket peer = (SSLSocket) listener.accept()) {
                        peer.setSoTimeout(20000);
                        peer.setEnabledProtocols(new String[]{version});
                        peer.setNeedClientAuth(true);
                        peer.startHandshake();
                        int request = peer.getInputStream().read();
                        peer.getOutputStream().write(request + 1);
                        peer.getOutputStream().flush();
                        return peer.getSession().getProtocol();
                    }
                });
                try (SSLSocket socket = (SSLSocket)
                        client.context.getSocketFactory().createSocket(
                                "127.0.0.1", listener.getLocalPort())) {
                    socket.setSoTimeout(20000);
                    socket.setEnabledProtocols(new String[]{version});
                    SSLParameters p = socket.getSSLParameters();
                    p.setEndpointIdentificationAlgorithm("HTTPS");
                    socket.setSSLParameters(p);
                    socket.startHandshake();
                    socket.getOutputStream().write(17);
                    socket.getOutputStream().flush();
                    int response = socket.getInputStream().read();
                    String serverProtocol = future.get(20, TimeUnit.SECONDS);
                    System.out.println(version + " negotiated="
                            + (version.equals(socket.getSession().getProtocol())
                                && version.equals(serverProtocol)));
                    System.out.println(version + " serverAliasSelected="
                            + (server.key.serverSelections.get() > sAlias));
                    System.out.println(version + " clientAliasSelected="
                            + (client.key.clientSelections.get() > cAlias));
                    System.out.println(version + " clientVerifiedServer="
                            + (client.trust.serverChecks.get() > cTrust));
                    System.out.println(version + " serverVerifiedClient="
                            + (server.trust.clientChecks.get() > sTrust));
                    System.out.println(version + " applicationData="
                            + (response == 18));
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5)
            throw new IllegalArgumentException(
                    "server.p12 server-trust.p12 client.p12 client-trust.p12 password");
        char[] password = args[4].toCharArray();
        try {
            Side server = side(Path.of(args[0]), Path.of(args[1]), password);
            Side client = side(Path.of(args[2]), Path.of(args[3]), password);
            test("TLSv1.3", server, client);
            test("TLSv1.2", server, client);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

### 6.3 Biên dịch, chạy và output đã xác minh

Trong **cùng phiên PowerShell** còn biến `$t`/`$pw`, đứng ở thư mục chứa `ExtendedManagersMutualTlsDemo.java`:

```powershell
javac --release 17 -encoding UTF-8 -d $t ExtendedManagersMutualTlsDemo.java
java -cp $t ExtendedManagersMutualTlsDemo (Join-Path $t "server.p12") (Join-Path $t "server-trust.p12") (Join-Path $t "client.p12") (Join-Path $t "client-trust.p12") $pw
```

Kết quả **12 dòng đúng như lần chạy được kiểm thử** trên JDK 17+ có SunJSSE:

```text
TLSv1.3 negotiated=true
TLSv1.3 serverAliasSelected=true
TLSv1.3 clientAliasSelected=true
TLSv1.3 clientVerifiedServer=true
TLSv1.3 serverVerifiedClient=true
TLSv1.3 applicationData=true
TLSv1.2 negotiated=true
TLSv1.2 serverAliasSelected=true
TLSv1.2 clientAliasSelected=true
TLSv1.2 clientVerifiedServer=true
TLSv1.2 serverVerifiedClient=true
TLSv1.2 applicationData=true
```

**Diễn giải từng nhóm:**

- `negotiated=true`: hai bên báo cùng TLS version, khớp danh sách duy nhất được bật cho lần thử. Không suy ra mọi đối tác Internet hỗ trợ hai versions.
- `serverAliasSelected=true`: delegate key manager phía server đã chọn local server certificate alias được chấp nhận; đây là **đếm selection thành công**, không phải một chứng minh riêng về trust.
- `clientAliasSelected=true`: vì server yêu cầu client certificate (`setNeedClientAuth(true)`), phía client đã chọn alias để trình mTLS certificate.
- `clientVerifiedServer=true`: client-side **extended trust manager** đã gọi đúng delegate và chỉ tăng counter sau khi check server thành công.
- `serverVerifiedClient=true`: phía server cũng kiểm chứng client certificate thành công, thể hiện khác biệt giữa mTLS và TLS server-only.
- `applicationData=true`: sau handshake, client gửi một byte `17` và server trả `18`, buộc cả hai bên hoàn tất luồng bắt tay và xác nhận kênh có thể dùng để trao đổi data. Một số handshake implementations có thể hoàn tất đọc/ghi ở các thời điểm khác nhau; đừng dựa riêng vào `Future.get` khi chưa có I/O/timeout đúng.
- Các counter được lấy **trước và sau từng phiên**, vì cùng objects `Side` còn sống trong hai lần thử. Counter chứng minh delegate callback **đã chạy và thành công** trong phiên tương ứng; chúng không phải công cụ phân tích toàn bộ TLS certificate policy.

**Không có trust-all ở đây:** `ObservedTrustManager` chuyển nguyên `chain`, `authType`, `socket/engine` cho `base`, đồng thời client bật HTTPS endpoint identification. Hai truststores tin **test certificate đã được tạo** và không tự chấp nhận mọi chain. Trong hệ thống thực, trusted roots cần xuất phát từ trust configuration có kiểm soát, không được tạo từ certificate do peer gửi không xác thực.

**Tại sao không in alias/private key?** Key alias, issuer, chain và SNI đôi khi là metadata vận hành nhạy cảm. Log tối thiểu boolean/count và error code không có secret sẽ an toàn hơn so với log `getPrivateKey(alias).getEncoded()` (không bao giờ làm việc đó).

Khi xong bài, xóa fixtures demo:

```powershell
if ($t -like (Join-Path $env:TEMP "extended-managers-demo-*")) {
    Remove-Item -LiteralPath $t -Recurse -Force
}
```

Xóa file không bảo đảm xóa sạch mọi bản sao trên SSD/snapshot; **chỉ dùng test private keys** và không lưu chúng trong repository.

## 7. Vì sao decorator phải triển khai và ủy quyền đầy đủ?

Ví dụ dùng hai lớp decorator có trách nhiệm chính là **quan sát, không thay đổi policy**. Một wrapper thực tế có thể thêm lựa chọn certificate hoặc kiểm tra authorization riêng, nhưng phải hiểu hợp đồng cả superclass.

### 7.1 Những method key manager không được quên

Khi extends `X509ExtendedKeyManager`, hãy triển khai:

- `getClientAliases` và `getServerAliases`: kết quả có thể là `null` nếu không có credential phù hợp.
- `chooseClientAlias` / `chooseServerAlias`: cho socket-based handshake.
- `chooseEngineClientAlias` / `chooseEngineServerAlias`: cho `SSLEngine`.
- `getCertificateChain` và `getPrivateKey`: JSSE cần lấy certificate chain/private key của alias đã chọn.

Không nên implements `chooseEngineServerAlias` rồi **luôn trả `null`** với suy nghĩ ứng dụng chỉ dùng socket: nhiều frameworks dùng engine ngay cả khi giao thức chạy trên TCP. Khi chuyển từ blocking socket sang NIO, certificate selection có thể dừng hoạt động nếu thiếu engine overload.

Nếu cần ép một alias cụ thể:

1. Cho delegate chọn các candidates theo keyType/issuers/provider.
2. Chỉ chấp nhận alias được phép theo cấu hình tenant/hostname, key usage, certificate chain, thuật toán và handshake context đã xác minh.
3. Nếu không có alias phù hợp, fail closed bằng `null`/lỗi rõ ràng.
4. Không return alias tùy ý không có private key hoặc certificate phù hợp.

**SNI không phải identity authentication.** SNI do client đề xuất giúp server chọn virtual host, nhưng bản thân tên SNI không chứng minh client được ủy quyền. Certificate server phải phù hợp hostname và client vẫn cần kiểm tra SAN/endpoint identification. Đừng dùng SNI để cho phép truy cập tenant hoặc quyết định trust client certificate thay thế chính sách mTLS.

### 7.2 Những method trust manager không được quên

Khi extends `X509ExtendedTrustManager`, có **sáu** overload:

- `checkServerTrusted(chain, authType)`, `checkClientTrusted(chain, authType)` (cơ bản);
- `checkServerTrusted(chain, authType, Socket)` và `checkClientTrusted(chain, authType, Socket)`;
- `checkServerTrusted(chain, authType, SSLEngine)` và `checkClientTrusted(chain, authType, SSLEngine)`.

Thêm `getAcceptedIssuers()`. Nếu là decorator cho một delegate tin cậy, mỗi method extended cần **gọi delegate đúng overload**; không được rơi về basic overload chỉ vì dễ lập trình. Caller có thể cần chính context để kiểm hostname/SNI/SSLParameters/signature algorithms.

**Khi muốn thêm kiểm tra sau xác minh chain**, làm theo nguyên tắc *monotonic restriction*: gọi delegate an toàn trước, sau đó **chỉ thắt chặt** chính sách, ví dụ kiểm tra certificate public-key pin đã được phân phối an toàn hoặc subject mapping. Khi yêu cầu không đạt, ném `CertificateException`. Không cắt bỏ trust chain verification vì đã làm pinning (nếu đó không phải một thiết kế pinning thay thế được phân tích và phê duyệt kỹ).

Đoạn ý tưởng (không phải chương trình độc lập):

```java
@Override
public void checkServerTrusted(X509Certificate[] chain, String authType,
                               SSLEngine engine) throws CertificateException {
    delegate.checkServerTrusted(chain, authType, engine);
    // Chỉ sau khi delegate xác minh thành công:
    // verifyApprovedPublicKeyPin(chain[0]); // tự ném CertificateException nếu sai
}
```

**Pinning cẩn thận:** đừng hardcode raw certificate DER không có kế hoạch rotation/backup. Public key pin (SPKI hash) và certificate pin có tuổi thọ/rotation khác nhau. Một pin có khả năng chặn cả certificate hợp lệ khi key rotation, nên phải có rollout/escape hatch được bảo vệ; không tự biến đây thành “bỏ qua CA trust khi pin trùng” nếu không có threat model rõ ràng.

## 8. Socket và SSLEngine: ngữ cảnh ảnh hưởng kết quả

| Tiêu chí | `SSLSocket` | `SSLEngine` |
| --- | --- | --- |
| Mô hình giao tiếp | Blocking I/O trên socket | TLS state machine với ByteBuffers trong NIO/async/framework |
| Method chọn local client key | `chooseClientAlias(...,Socket)` | `chooseEngineClientAlias(...,SSLEngine)` |
| Method chọn local server key | `chooseServerAlias(...,Socket)` | `chooseEngineServerAlias(...,SSLEngine)` |
| Method kiểm peer trên client | `checkServerTrusted(...,Socket)` | `checkServerTrusted(...,SSLEngine)` |
| Method kiểm peer trên server mTLS | `checkClientTrusted(...,Socket)` | `checkClientTrusted(...,SSLEngine)` |
| Endpoint identification | `SSLParameters` trên socket | `SSLParameters` trên engine, cần host context đúng |
| SNI/handshake context | Có thể qua `SSLSession`/`ExtendedSSLSession` tùy thời điểm | `engine.getHandshakeSession()` và SNI/peer host nếu có |
| Rủi ro khi wrapper thiếu overload | Có thể hoạt động trên socket nhưng fail khi chuyển framework | Engine path dễ fail/mất context kiểm tra |

**Đặc biệt với SSLEngine:** khi tạo engine cho TLS client, nên có tên peer/port thích hợp (`SSLContext.createSSLEngine(host, port)`) và bật endpoint identification nếu giao thức cần. Dùng `createSSLEngine()` không host rồi mặc định “HTTPS hostname verification sẽ tự chạy” có thể làm thiếu dữ liệu định danh. Nếu handshake diễn ra qua reverse proxy, bảo đảm hostname cần kiểm là service identity mong muốn, **không** chỉ IP của proxy.

Khi override alias selection theo SNI, đọc `ExtendedSSLSession.getRequestedServerNames()` nếu handshake session và thông tin hỗ trợ; không dựa `getSession()` cũ khi đang handshake và không cho null/unsupported SNI trở thành lý do bypass policy.

## 9. Chọn certificate và kiểm peer không đồng nghĩa authorization ứng dụng

Ngay cả khi mTLS thành công:

- **Trust manager** chứng minh certificate/chain đạt ràng buộc PKIX/TLS của môi trường đó. Nó **không** tự ánh xạ client certificate sang role “admin” hay tenant.
- **Certificate subject/CN** không phải định danh ứng dụng đủ mạnh trong mọi profile. Cần quy tắc mapping đã phê duyệt (SAN URI/DNS, SPIFFE ID hoặc field chứng thư tương ứng), issuer đáng tin, policy và key lifecycle.
- **KeyUsage/ExtendedKeyUsage** quy định certificate được dùng cho mục đích mật mã/giao thức: serverAuth khác clientAuth. Một clientAuth certificate không được tự coi là server identity.
- **Hostname identification** kiểm tra server identity theo TLS/HTTPS; không thay kiểm tra client authorization trên API.
- **KeyManager chọn alias** có thể phụ thuộc SNI, issuer, signature algorithms, key type; không có nghĩa owner của alias có quyền truy cập mọi service.

Ví dụ với một API quản lý dữ liệu nhạy cảm, chỉ “mTLS handshake thành công” không đủ; service phải so định danh client đã xác thực với permission của endpoint/dataset/tenant, rồi audit.

Đừng log raw private key hoặc certificate chain đầy đủ trong mỗi handshake. Khi cần forensic, có thể log key ID/certificate fingerprint, issuer, certificate serial, role và TLS version theo chính sách dữ liệu, không đưa bí mật vào log.

## 10. Vấn đề thực tế và cách chẩn đoán

| Dấu hiệu lỗi | Nguyên nhân khả dĩ | Kiểm tra/khắc phục |
| --- | --- | --- |
| `SSLHandshakeException: no suitable certificate` | KeyManager không có alias đúng keyType/issuers/signature schemes | Xem KeyStore entries, chain, provider, `choose...Alias` và certificate profile |
| `no available authentication scheme` | Server không tìm được credential phù hợp key type/protocol | Kiểm certificate, signature schemes, server key manager và TLS 1.3 compatibility |
| `PKIX path building failed` | TrustStore không tin CA/peer certificate hoặc thiếu intermediates | Kiểm đúng trust anchors, chain và trust manager; không trust-all |
| `No subject alternative names matching ...` | HTTPS endpoint identification xác định peer host khác SAN | Cấp lại cert đúng SAN hoặc kết nối đúng hostname; không tắt hostname checks |
| `bad_certificate` / `certificate_unknown` | Peer từ chối certificate/chain | Xem log hai đầu; phân biệt selection failure với trust failure |
| `certificate_required` / client handshake rejected | Server yêu cầu client certificate nhưng client key manager trả null/sai loại | Kiểm `setNeedClientAuth`, client KeyStore, issuer list, EKU clientAuth |
| mTLS “thành công” dù client không có cert | Server đặt `setWantClientAuth(true)` hoặc chưa bật need | Dùng `setNeedClientAuth(true)` đúng socket/engine |
| Socket TLS thành công nhưng SSLEngine framework fail | Wrapper chỉ override Socket methods, engine methods trả null/không delegate | Implement cả engine overloads |
| Hostname không được kiểm khi dùng wrapper | `checkServerTrusted(...,Socket)` gọi basic overload, hoặc thiếu SSLParameters HTTPS | Delegate đúng contextual overload và bật endpoint identification |
| `InvalidKeyException` / key not found | Alias không có private key hoặc key handle/provider không tương thích | Đồng bộ `getCertificateChain`, `getPrivateKey`, provider, key policy |
| Một server nhiều certificates gửi sai virtual host | Chọn alias chỉ theo `keyType`, bỏ qua SNI/tenant và SAN | Lựa chọn có policy SNI an toàn, test từng hostname |
| `getAcceptedIssuers()` trả list gây lỗi client selection | Advertised CA list không khớp issuer chain của client | Kiểm trust anchors, issuer constraints; không trả list tùy ý |
| Certificate chain hợp lệ nhưng ứng dụng từ chối client | mTLS xác thực xong nhưng không có role/permission | Map identity được xác minh sang authorization nghiệp vụ |
| Fail khi rotate certificate | Alias/chain cũ còn cache, new alias thiếu key, truststore chưa cập nhật | Rollout trust trước, rotate key/cert có version và test |
| Connection chỉ fail ở TLS 1.3 | Key/cert/sig scheme hoặc group/provider khác TLS 1.2 | Kiểm trace JSSE, signature algorithms và KeyManager alias compatibility |
| `ClassCastException` khi lấy extended manager | Factory trả implementation chỉ tuân thủ interface cũ | Kiểm `instanceof`, đổi provider có hỗ trợ; không ép cast hoặc trust-all |
| `KeyStoreException` / `UnrecoverableKeyException` | Sai password, alias, store type hoặc token permissions | Kiểm stores, PIN, key material và provider |

**Không tự khắc phục lỗi bằng cách trả alias bừa bãi hoặc trust-all.** Một handshake thất bại là ranh giới bảo mật hữu ích; phải sửa root cause qua đúng truststore/credential/hostname/profile.

### Debug và quan sát an toàn

Trong staging/test, có thể bật JSSE trace:

```powershell
java "-Djavax.net.debug=ssl,handshake,keymanager,trustmanager" -cp $t ExtendedManagersMutualTlsDemo (Join-Path $t "server.p12") (Join-Path $t "server-trust.p12") (Join-Path $t "client.p12") (Join-Path $t "client-trust.p12") $pw
```

Log chứa thông tin certificate, hostname, issuer, alias, handshake metadata, và tùy debug flags có thể rất nhạy cảm. **Chỉ dùng với test certificates, giới hạn quyền truy cập log và không gửi nguyên logs production công khai**. Không bật chế độ dump traffic secrets. Với nhiều framework, xem thêm danh sách enabled protocols/suites, SNI, ALPN, trust anchors và TLS termination hop.

### Những test nên có trước khi deploy

- Chứng thư server đúng SAN và EKU serverAuth được client xác minh; sai SAN bị từ chối.
- mTLS client certificate hợp lệ được server xác minh; thiếu client cert khi `needClientAuth=true` phải thất bại.
- Client/server certificate do issuer không tin bị từ chối, không được silently import vào truststore.
- ClientAuth-only certificate không được chấp nhận làm serverAuth identity theo profile.
- Không có key alias đúng type/issuer: handshake thất bại, không fallback sang một tenant khác.
- Dùng `SSLEngine`: overload engine được gọi và context/hostname checks còn hiệu lực.
- Certificate rotation: alias/cert chain và trust anchors thay đổi có kiểm soát, không drop service ngoài kế hoạch.
- Thử TLS 1.2 và 1.3 phù hợp policy; đừng hạ xuống giao thức yếu vì một lỗi certificate.

## 11. Checklist thiết kế X509Extended managers

- [ ] Xác định rõ **local credential selection** và **peer trust validation** là hai bước riêng.
- [ ] `KeyManagerFactory` nhận đúng KeyStore/private key chain; `TrustManagerFactory` nhận đúng TrustStore/trust anchors.
- [ ] Cài toàn bộ `X509ExtendedKeyManager` methods, đặc biệt `chooseEngineClientAlias` / `chooseEngineServerAlias`.
- [ ] Cài đủ sáu overload của `X509ExtendedTrustManager`; delegation nhận đúng `Socket`/`SSLEngine`.
- [ ] Không dùng `checkServerTrusted` rỗng, trust-all, hoặc `getAcceptedIssuers` giả tạo để vượt xác minh chain.
- [ ] Client kiểm endpoint identity qua HTTPS/SAN trên raw socket hoặc engine có peer host thích hợp.
- [ ] Server mTLS bật `setNeedClientAuth(true)` và xác minh client chain theo đúng truststore.
- [ ] Alias selection tôn trọng `keyType`, `issuers`, SNI/context, algorithm policy, chain và key usage.
- [ ] Không hardcode một alias cho mọi tenant/host; fail closed nếu credential không phù hợp.
- [ ] Authentication thành công phải đi tiếp qua authorization ứng dụng theo certificate identity được phép.
- [ ] Quản lý key/cert/truststore rotation, backup, audit và kiểm thử handshake thật.
- [ ] Giới hạn debug và logs; không xuất private keys hoặc TLS secrets để quan sát callback.

## 12. Tự kiểm tra kiến thức

1. **`X509ExtendedKeyManager` làm gì?** Chọn local key alias và cung cấp certificate chain/private key cho handshake.
2. **`X509ExtendedTrustManager` làm gì?** Kiểm certificate chain của peer, ném `CertificateException` nếu không tin.
3. **Server certificate do ai chọn và ai kiểm?** Server key manager chọn; client trust manager kiểm.
4. **Trong mTLS, ai chọn client certificate?** Client key manager, khi server yêu cầu client authentication.
5. **`setNeedClientAuth(true)` khác `setWantClientAuth(true)`?** Need bắt buộc client cung cấp certificate phù hợp; want có thể chấp nhận thiếu.
6. **Socket cần method alias nào?** `chooseClientAlias` và `chooseServerAlias`; engine cần `chooseEngineClientAlias`/`chooseEngineServerAlias`.
7. **Nếu tự viết extended trust decorator, vì sao phải giữ Socket/SSLEngine?** Để giữ ngữ cảnh hostname, handshake, SSLParameters và policy của delegate.
8. **`checkServerTrusted` trả `boolean` à?** Không, `void`; ném `CertificateException` khi từ chối.
9. **`getAcceptedIssuers()` trả trust decision cho một certificate cụ thể?** Không; nó trả danh sách issuer certificates theo contract, không xác minh chain hiện tại.
10. **`authType` có phải OID `serverAuth` không?** Không; đây là thông tin kiểu xác thực handshake do JSSE cung cấp.
11. **Một alias bất kỳ trong `KeyStore` có đủ để handshake không?** Không; cần private key/chain khớp, keyType, issuer, protocol và provider policy.
12. **SNI có tự xác thực quyền tenant của client không?** Không; SNI là tín hiệu chọn virtual host, không chứng minh quyền truy cập.
13. **Vì sao client cần `setEndpointIdentificationAlgorithm("HTTPS")` trong raw SSLSocket demo?** Để kiểm IP/DNS SAN của server identity.
14. **Nếu trust manager được bọc chỉ gọi `delegate.checkServerTrusted(chain,authType)` thì rủi ro nào?** Bỏ mất kiểm tra phụ thuộc socket/engine, có thể làm yếu hostname/connection checks.
15. **mTLS thành công có tự cấp quyền gọi mọi API không?** Không; phải map certificate identity sang role/permissions nghiệp vụ.
16. **Tại sao ví dụ có server-trust.p12 và client-trust.p12 riêng?** Hai phía tin đối tác **khác nhau**; server cần tin client, client cần tin server.
17. **Nếu client không chọn được alias trong mTLS, nên làm gì?** Trả `null`/handshake failure và sửa credential/issuer constraints; không gửi private key hoặc chọn tenant sai.
18. **Một factory không trả extended manager, xử lý thế nào?** Phát hiện kiểu, fail closed hoặc dùng provider/adapter được đánh giá; không cast mù.
19. **TLS 1.2 và 1.3 cùng thành công trên loopback chứng minh Internet service khác cũng hỗ trợ?** Không; kết quả chỉ trên hai local contexts đã cấu hình.
20. **Làm thế nào thêm custom restriction an toàn?** Delegate full peer validation trước, sau đó chỉ thêm điều kiện reject với `CertificateException`; không thay thế trust bằng “accept all”.

## Tài liệu chuẩn và Java API

- [X509ExtendedKeyManager, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedKeyManager.html)
- [X509ExtendedTrustManager, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html)
- [X509KeyManager / X509TrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509KeyManager.html)
- [KeyManagerFactory / TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [SSLParameters và endpoint identification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [SSLSocket và SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html)
- [SSLEngine và handshake context](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html)
- [ExtendedSSLSession, SNI và peer signature algorithms](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/ExtendedSSLSession.html)
- [Oracle Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 5280: X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)
