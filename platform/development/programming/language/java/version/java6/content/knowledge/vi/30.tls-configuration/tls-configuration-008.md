# Chọn giao thức, thuật toán theo chính sách hiện hành

## 1. Mục tiêu: cấu hình TLS bằng một chính sách có thể kiểm chứng

Một ứng dụng Java dùng TLS không chỉ cần “mở được kết nối HTTPS”. Nó phải **chọn đúng giao thức, nhóm thuật toán mật mã, identity, trust và các điều kiện xác minh**, đồng thời **từ chối** một peer chỉ hỗ trợ cấu hình không còn được phép. Nếu có thể tùy tiện bật lại SSLv3, TLS 1.0/1.1 hoặc một cipher suite không an toàn để vượt qua lỗi handshake, việc dùng TLS không còn đáp ứng mục đích bảo vệ kết nối.

**`javax.net.ssl.SSLParameters`** có từ **Java 6**, vẫn là API hiện hành trong **Java SE 26**. Nhưng cách áp dụng cần dựa vào hướng dẫn bảo mật **hiện nay**, không dạy lại những lựa chọn legacy của thời Java 6 như khuyến nghị cho sản phẩm mới.

Một policy TLS thực tế nên trả lời:

- **Protocol floor**: có yêu cầu **TLS 1.3 only** hay chấp nhận **TLS 1.2** cho các clients còn được hỗ trợ?
- **Cipher suites**: cho phép **AEAD** như AES-GCM và ChaCha20-Poly1305; nếu dùng TLS 1.2, yêu cầu **ECDHE** cho forward secrecy.
- **Authentication**: xác minh server certificate chain **và** hostname; nếu có mTLS, xác minh client certificate và quyền ứng dụng.
- **Algorithms beyond cipher suite**: certificate signature, key size, key exchange groups, signature schemes và policy PKIX/JDK security.
- **Providers/versions**: algorithm nào được JDK/provider **hỗ trợ**, algorithm nào được **bật mặc định**, algorithm nào bị **cấm** bởi security properties?
- **Fail closed**: policy yêu cầu một version/suite mà runtime không cung cấp thì **không tự động hạ xuống** phiên bản cũ.
- **Evidence**: kiểm tra `SSLSession.getProtocol()` và `getCipherSuite()` sau handshake, thay vì chỉ nhìn danh sách đã cấu hình.

### Mục tiêu sau bài

Bạn sẽ:

1. Phân biệt `SSLContext.getSupportedSSLParameters()` với `getDefaultSSLParameters()`.
2. Chọn **TLS 1.3** làm ưu tiên, chỉ giữ **TLS 1.2** khi có yêu cầu tương thích thật và được phép.
3. Chọn TLS 1.3 AEAD suites, TLS 1.2 `ECDHE_RSA/ECDHE_ECDSA + AES_GCM`, hiểu vì sao phải loại bỏ RSA key transport, CBC/RC4/3DES, NULL/anonymous ciphers.
4. Phân biệt cipher suite **TLS 1.3** với cipher suite **TLS 1.2**; không suy key exchange/cert type từ tên TLS 1.3 cipher.
5. Hiểu tầng policy của Java: `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms`, `jdk.tls.legacyAlgorithms` và `SSLParameters.setAlgorithmConstraints`.
6. Áp dụng policy vào `SSLSocket`, `SSLServerSocket`, `SSLEngine` và những HTTP stacks có API tương ứng.
7. Thiết kế allowlist **giao với default-enabled và supported**; từ chối tập rỗng thay vì tự mở yếu tố legacy.
8. Không nhầm `SNI`/ALPN với certificate validation/hostname verification và không dùng trust-all.
9. Biên dịch/chạy **hai ví dụ Java 17+**: chọn TLS policy và TLS 1.3 handshake thật có negative protocol test.
10. Thiết kế integration test, audit, certificate rotation và quy trình cập nhật JDK/provider.

~~~text
                    Security policy của sản phẩm
                  (versions, suites, trust, identity)
                                |
              +-----------------+--------------------+
              |                                      |
              v                                      v
      SSLContext/provider                      PKI trust / cert
        defaults+supported                    path, hostname, EKU
              |                                      |
              v                                      |
       Policy allowlist                               |
              |                                      |
              +---------- SSLParameters --------------+
                                   |
                       apply trước handshake
                                   |
                     +-------------+-------------+
                     |                           |
                  SSLSocket                  SSLEngine
                     |                           |
                     +-------------+-------------+
                                   |
                      TLS handshake / negotiate
                                   |
                     +-------------+-------------+
                     |                           |
            thành công đúng policy         không tương thích
                     |                           |
                     v                           v
             SSLSession protocol            SSLHandshakeException
             SSLSession cipher suite         fail closed, không fallback
~~~

## 2. TLS version hiện hành: TLS 1.3 trước, TLS 1.2 có điều kiện

Theo hướng dẫn hiện hành của **OWASP Transport Layer Security Cheat Sheet**, nên mặc định dùng **TLS 1.3** và có thể hỗ trợ **TLS 1.2** nếu cần tương thích. **TLS 1.0/TLS 1.1 đã chính thức bị loại bỏ theo RFC 8996**; SSLv2/SSLv3 cũng không dùng. Các giao thức cũ có các rủi ro đã biết, và hạ cấp về chúng không phải cách sửa lỗi tương thích hợp lệ.

| Protocol | Dùng cho thiết kế mới? | Giải thích |
| --- | --- | --- |
| `TLSv1.3` | **Ưu tiên** | Phiên bản hiện đại, thiết kế handshake và cipher suites tốt hơn |
| `TLSv1.2` | **Chỉ khi cần và được duyệt** | Có thể bảo vệ tốt với ECDHE + AEAD và chính sách certificate phù hợp |
| `TLSv1.1` | **Không** | Đã bị loại bỏ, không phù hợp policy mới |
| `TLSv1` | **Không** | Đã bị loại bỏ, không phù hợp policy mới |
| `SSLv3` / SSLv2 | **Không** | Giao thức SSL cũ, không an toàn |
| `SSLv2Hello` | **Không dùng làm lựa chọn policy ứng dụng** | Tên tương thích cũ, không phải TLS security baseline |

**Không nên** phát biểu rằng TLS 1.2 luôn yếu hoặc phải xóa mọi nơi: nó vẫn có thể đáp ứng một số hệ thống/chuẩn khi chọn cipher suites, groups, certificates và thuật toán thích hợp. Tuy nhiên, **không giữ TLS 1.2 chỉ vì provider hỗ trợ nó**; phải có nhu cầu interoperability và vòng đời loại bỏ rõ ràng.

### 2.1. Hai profile policy hữu ích

**Profile A — TLS 1.3 only:** dành cho các endpoint mới có thể yêu cầu clients hiện đại, kiểm soát đầy đủ tích hợp, ít nhu cầu legacy interoperability.

~~~java
params.setProtocols(new String[]{"TLSv1.3"});
~~~

**Profile B — TLS 1.3 + TLS 1.2:** có chủ ý cho các clients còn hỗ trợ TLS 1.2 và đã được phê duyệt. Phải chọn TLS 1.2 cipher suites mạnh, không bật mọi supported suites.

~~~java
params.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
~~~

Hai đoạn trích này **chưa phải chương trình độc lập**; `params` là `SSLParameters`. Chúng **chỉ nêu danh sách được phép**, không chứng minh handshake thành công. Ví dụ runnable sẽ kiểm tra policy/ciphers và xác nhận negotiated protocol.

### 2.2. “Prefer TLS 1.3” không đồng nghĩa application tự quyết phiên bản

Hai phía thương lượng phiên bản chung từ các versions được mỗi phía chấp nhận và policy của TLS stack. Không thể buộc một server chỉ có TLS 1.2 chấp nhận TLS 1.3 bằng việc đặt chuỗi `"TLSv1.3"` trên client. Nếu không có tập giao, handshake phải thất bại.

### 2.3. Không tạo fallback vòng lặp xuống protocol thấp

~~~java
// PHẢN VÍ DỤ: Không làm trong ứng dụng mới.
try {
    connectWith("TLSv1.3");
} catch (Exception ignored) {
    connectWith("TLSv1"); // Hạ cấp không an toàn.
}
~~~

Đây là pseudo-code minh họa **sai lầm**, không phải chương trình runnable. Thay vì fallback tùy tiện, hãy phân loại lý do handshake fail (version/cipher/certificate/hostname/network), sửa peer hợp lệ hoặc cô lập hệ thống ngoại lệ qua chính sách bảo mật riêng.

## 3. Cipher suite không chỉ là “thuật toán mã hóa”

Một TLS cipher suite định nghĩa bộ tham số mật mã. Ý nghĩa của tên suite **khác nhau giữa TLS 1.3 và TLS 1.2**.

### 3.1. TLS 1.3 cipher suites

Ví dụ các lựa chọn AEAD hiện đại:

| Tên JSSE/TLS | Mã hóa dữ liệu | Hash/KDF liên quan |
| --- | --- | --- |
| `TLS_AES_128_GCM_SHA256` | AES-128-GCM | SHA-256 |
| `TLS_AES_256_GCM_SHA384` | AES-256-GCM | SHA-384 |
| `TLS_CHACHA20_POLY1305_SHA256` | ChaCha20-Poly1305 | SHA-256 |

**AEAD** (*Authenticated Encryption with Associated Data*) bảo vệ **tính bí mật và toàn vẹn** của records theo thiết kế. TLS 1.3 bỏ các cipher suites TLS cũ như RC4, CBC, NULL, RSA key transport khỏi tập TLS 1.3.

**Quan trọng:** một tên TLS 1.3 suite như `TLS_AES_128_GCM_SHA256` **không cho biết** certificate được ký bằng RSA hay ECDSA hoặc key exchange group đã dùng. TLS 1.3 đàm phán key-exchange groups và authentication/signature schemes **qua extension/tầng khác**. Vì vậy không thể suy “server dùng RSA key exchange” chỉ vì certificate có khóa RSA.

### 3.2. TLS 1.2 cipher suites (khi thật sự cần)

Ví dụ suites có ephemeral key exchange và AEAD:

| TLS 1.2 cipher suite | Ý nghĩa |
| --- | --- |
| `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | ECDHE forward secrecy, RSA certificate authentication, AES-GCM |
| `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384` | ECDHE + RSA cert, AES-256-GCM |
| `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` | ECDHE + ECDSA cert, AES-128-GCM |
| `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384` | ECDHE + ECDSA cert, AES-256-GCM |

Phân biệt **`ECDHE_RSA`** (ephemeral ECDHE key agreement, RSA certificate authentication) với **`TLS_RSA_WITH_...`** (RSA key transport kiểu cũ, **không cung cấp forward secrecy**). Dấu `RSA` trong `ECDHE_RSA` không có nghĩa đang dùng RSA key transport.

Ứng dụng không nên bật mọi TLS 1.2 cipher suites chỉ vì chúng có trong `getSupportedCipherSuites()`; nên chọn approved ECDHE+AEAD suites tương ứng với loại certificate và triển khai của đối tác.

### 3.3. Những lựa chọn không nên đưa vào policy hiện nay

- `TLS_RSA_WITH_*` (static RSA key transport, thiếu forward secrecy).
- `TLS_DH_*`/`TLS_ECDH_*` dạng key exchange tĩnh (thiếu forward secrecy).
- `TLS_*_anon_*` (không xác thực server, dễ MITM).
- `TLS_*_NULL_*` (không mã hóa nội dung).
- `TLS_*_EXPORT_*` (bộ suite suy yếu theo giới hạn xuất khẩu cũ).
- RC4, DES/3DES, CBC suites khi thiết kế endpoint mới; đặc biệt ưu tiên AEAD.
- SSLv2/3, TLS 1.0/1.1 và cryptographic signatures/certificates bị enterprise security policy cấm.

Tài liệu Java vẫn có thể liệt kê những tên legacy để giải thích compatibility/provider; **sự tồn tại của một tên trong Javadoc không phải sự chấp thuận bảo mật**.

### 3.4. AES-128-GCM có “kém an toàn” vì không phải AES-256?

AES-128-GCM là một bộ AEAD mạnh và được TLS 1.3 định nghĩa; không bắt buộc chọn AES-256-GCM cho mọi endpoint. Chính sách tổ chức, compliance, hardware acceleration, performance và tương thích có thể làm thay lựa chọn. Đừng suy từ chiều dài key mã hóa đối xứng ra toàn bộ chất lượng bảo mật của handshake/certificate/trust.

### 3.5. ChaCha20-Poly1305 có nên bật không?

`TLS_CHACHA20_POLY1305_SHA256` là TLS 1.3 AEAD hiện đại, có lợi ở một số thiết bị không có tăng tốc AES. Nếu JDK/provider + peers hỗ trợ và enterprise policy cho phép, nó có thể nằm trong allowlist. Ví dụ Java ở mục 10 kiểm tra nó **có trong default-enabled và supported** trước khi đưa vào cấu hình, chứ không giả định mọi JVM đều có.

## 4. Forward secrecy và key exchange groups

**Forward secrecy** nghĩa là việc lộ khóa dài hạn về sau không tự cho phép giải mã những session traffic đã ghi lại trước đó, khi handshake/ephemeral secrets đáp ứng đúng điều kiện. TLS 1.2 dùng ECDHE suites để có đặc tính này; TLS 1.3 hỗ trợ (EC)DHE và cơ chế session resumption hiện đại. **Không khẳng định mọi PSK-only TLS 1.3 handshake đều có forward secrecy**: mode và shared secrets thực tế vẫn quan trọng.

### 4.1. Named groups hiện hành

Những nhóm thường được cân nhắc tùy JDK/provider/compliance:

- `x25519` — một nhóm ECDHE mạnh, thường có hiệu năng tốt.
- `secp256r1` — NIST P-256, phổ biến và được hỗ trợ rộng rãi.
- `secp384r1` — NIST P-384, có thể phù hợp policy cụ thể.

Không tự coi một group đang được provider hỗ trợ là phù hợp mọi yêu cầu; đánh giá enterprise standards và interoperability. Nếu có policy post-quantum/hybrid key exchange ở những JDK/providers mới, kiểm tra tài liệu **đúng phiên bản runtime**, không giả định Java 17 có API/implementation đó.

### 4.2. Java 17 và APIs mới hơn

`SSLParameters` có `setAlgorithmConstraints(AlgorithmConstraints)` từ các bản Java trước, cho phép bổ sung constraints trên những runtime constraints. Nhưng các methods cấp cao như `setNamedGroups(...)` và `setSignatureSchemes(...)` xuất hiện ở những JDK mới hơn, **không tự viết code Java 17 gọi method chưa tồn tại**.

Có các system properties/provider-specific properties (ví dụ `jdk.tls.namedGroups` với SunJSSE) cho phép administrators điều chỉnh, nhưng không nên hardcode một danh sách groups tùy tiện rồi vô hiệu hóa nâng cấp TLS mới. **Kiểm thử đúng JDK/provider trước khi chỉnh** và giữ security policy cấp platform có thẩm quyền.

### 4.3. Một cipher suite an toàn không bù được key/certificate yếu

TLS handshake có thể còn phụ thuộc độ mạnh khóa RSA/ECDSA, signature schemes, PKIX path, certificate usage, trust anchors và hostname. Một `TLS_AES_128_GCM_SHA256` không làm certificate giả/hết hạn/sai SAN trở thành đáng tin. Trong sản phẩm, phải xác minh cả identity và mTLS requirements, không chỉ check cipher.

## 5. Security properties của JDK: lớp phòng vệ không nên tắt

### 5.1. Các tầng điều khiển

| Tầng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Application policy | `SSLParameters.setProtocols/setCipherSuites` | Chỉ chọn từ tập app chấp thuận |
| Default-enabled policy | `SSLContext.getDefaultSSLParameters()` | Tập mặc định đã bật theo provider/JDK |
| Capability | `SSLContext.getSupportedSSLParameters()` | Những thứ implementation nhận biết/hỗ trợ |
| TLS disable policy | `Security.getProperty("jdk.tls.disabledAlgorithms")` | SunJSSE chặn những algorithms/protocols đã bị vô hiệu hóa |
| Certificate path policy | `jdk.certpath.disabledAlgorithms` | Ràng buộc algorithms/key sizes/certs khi CertPath validation |
| Legacy preference | `jdk.tls.legacyAlgorithms` | Đánh dấu các legacy algorithms, không coi chúng là modern |
| Application constraints | `SSLParameters.setAlgorithmConstraints(...)` | Giới hạn bổ sung cho endpoint |
| Enterprise/config/runtime | `java.security`, provider policies, truststore | Có thể quy định constraints cao hơn app |

Điều cốt lõi của Oracle JSSE: ứng dụng **có thể đặt** một cipher suite vào enabled list bằng setter nhưng **không thể dùng nó trong handshake nếu `jdk.tls.disabledAlgorithms` đã cấm**. Ngược lại, không phải cái gì **supported** cũng **enabled mặc định**.

### 5.2. Supported, enabled và negotiated không giống nhau

~~~text
Supported (provider có khả năng)
       |
       v
Enabled by JDK/provider defaults
       |
       v
Ứng dụng giới hạn bằng policy allowlist
       |
       v
JDK security / algorithm constraints / trust rules
       |
       v
Common với peer trong handshake
       |
       v
Negotiated (SSLSession.getProtocol/getCipherSuite)
~~~

**Một getter không chứng minh kết quả handshake**. Sau kết nối, cần kiểm chứng protocol/cipher thực sự negotiated, và certificate/hostname verification đã qua.

### 5.3. Đọc policy tại runtime

~~~java
String tlsDisabled =
        java.security.Security.getProperty("jdk.tls.disabledAlgorithms");
String certDisabled =
        java.security.Security.getProperty("jdk.certpath.disabledAlgorithms");
~~~

**Đoạn trích**, chỉ để kiểm tra môi trường và hỗ trợ audit; không in toàn bộ policy lên endpoint công khai, không tự sửa property tùy tiện khi application đang chạy. Với SunJSSE, cấu hình thường nằm trong `<java-home>/conf/security/java.security` và có thể được override bởi deployment mechanisms. Những properties có thể được **caching** khi JSSE khởi tạo, vì vậy không triển khai chính sách bằng cách thay đổi global state giữa các requests.

### 5.4. Không vô hiệu hóa disabledAlgorithms để “fix lỗi”

Nếu handshake báo `No appropriate protocol` hoặc `no cipher suites in common`, trước tiên kiểm tra:
- policy client/server, provider/JDK version;
- TLS 1.3/1.2 availability;
- certificate type/supported signature schemes;
- truststore/hostname/key sizes/certpath;
- cấu hình proxy/offload và môi trường peer.

**Không xóa `TLSv1`, `RC4`, `3DES`, `TLS_RSA_*` hoặc key-size restrictions khỏi disabledAlgorithms chỉ để một legacy peer kết nối.** Cần nâng cấp peer hoặc thiết kế exception có phê duyệt, cô lập và hạn chế dữ liệu/permissions nếu compliance cho phép.

### 5.5. `setAlgorithmConstraints` không mở khóa thứ đã bị cấm

~~~java
SSLParameters parameters = context.getDefaultSSLParameters();
// Nếu có AlgorithmConstraints chính sách riêng:
// parameters.setAlgorithmConstraints(approvedConstraints);
~~~

**Đoạn trích**, `approvedConstraints` phải triển khai `java.security.AlgorithmConstraints` đúng yêu cầu. Constraints này được JSSE dùng **bổ sung** cho runtime security constraints, không phải một “bypass switch”. Không tự viết `permits(...)` trả true cho mọi thứ để cố gắng vô hiệu hóa policy hệ thống.

## 6. Lựa chọn SSLContext và SSLParameters hiện đại

### 6.1. SSLContext.getInstance("TLS") nghĩa là gì?

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, new SecureRandom());
~~~

**Đoạn trích** với key/trust managers được khởi tạo trước. `"TLS"` yêu cầu JSSE TLS implementation; **không đồng nghĩa giao thức thương lượng được cố định ở TLS 1.3**. SSLContext tạo sockets/engines, còn profile protocol cụ thể áp bằng `SSLParameters`.

Nếu đang dùng default truststore của một HTTPS client thông thường, `SSLContext.getDefault()` hoặc context mặc định của framework có thể phù hợp. Nhưng server TLS thực sự phải có **private key/certificate identity**; client trust cần đúng trust anchors, không dùng trust-all manager.

### 6.2. Default và supported là các bản sao (copies)

~~~java
SSLParameters defaults = context.getDefaultSSLParameters();
SSLParameters supported = context.getSupportedSSLParameters();
String[] enabledProtocols = defaults.getProtocols();
String[] availableProtocols = supported.getProtocols();
String[] enabledSuites = defaults.getCipherSuites();
String[] availableSuites = supported.getCipherSuites();
~~~

**Đoạn trích**. Hai API có từ Java 6 và trả **bản sao** `SSLParameters`. Những mảng protocols/cipher suites trong kết quả từ SSLContext là non-null theo Javadoc. Nhưng một `new SSLParameters()` không tự populate protocols/ciphers, nên getter của object rỗng có thể là null.

### 6.3. Chọn theo policy thay vì tự động chọn “mạnh nhất” từ mọi supported

Một hướng an toàn:
1. Đặt hai **allowlists được duyệt**: protocols và cipher suites.
2. Lấy `getDefaultSSLParameters()` và `getSupportedSSLParameters()` trên **runtime đang chạy**.
3. Chọn những phần tử **nằm trong cả allowlist + enabled defaults + supported**.
4. Bảo đảm **có đủ version/cipher bắt buộc** của profile.
5. Nếu không đủ, **throw/fail closed**; không thêm legacy ngoài allowlist.
6. Dùng `context.getDefaultSSLParameters()` mới, set hai arrays đã chọn.
7. Với outbound TLS client raw socket, bật `setEndpointIdentificationAlgorithm("HTTPS")`.
8. Apply lên endpoint **trước handshake**.
9. Kiểm tra `SSLSession` sau handshake để xác thực phiên bản/cipher negotiated.

Đây chính là logic của chương trình `TlsPolicySelectionDemo.java` ở mục 10.

### 6.4. Chọn cipher suites phải phù hợp TLS versions

Nếu profile **TLS 1.3 only**, không cần đưa các TLS 1.2 suites vào list. Nếu **TLS 1.3 + TLS 1.2**, list có thể chứa suites của **cả hai versions**; JSSE chỉ chọn suite phù hợp với phiên bản negotiated. Đừng kết luận “không thể có TLS 1.3 vì tên cipher suite không chứa RSA/ECDHE”, vì TLS 1.3 đặt key-exchange/signature bên ngoài tên suite.

### 6.5. Các ràng buộc tuân thủ

Một công ty có thể có thêm FIPS, PCI DSS, NIST hoặc các chuẩn nội bộ yêu cầu protocols, certificate profiles, crypto providers và key sizes cụ thể. Những hướng dẫn trong bài là **baseline kỹ thuật để học**, không tự động chứng nhận rằng deployment đáp ứng mọi yêu cầu pháp lý/compliance. Đọc policy chính thức của tổ chức và kiểm thử provider tương ứng trước khi go live.

## 7. Certificate trust, hostname và identity vẫn bắt buộc

Một TLS 1.3 cipher suite an toàn **không có nghĩa client đã kết nối đúng server**. Cần:

- Server certificate chain hợp lệ theo trust anchors/PKIX policy;
- thời hạn certificate hợp lệ, KeyUsage/EKU phù hợp;
- certificate Subject Alternative Name (SAN) khớp **DNS hostname hoặc IP** kỳ vọng;
- certificate/CA không bị revoke theo security policy;
- không dùng trust-all `X509TrustManager`;
- không vô hiệu hóa hostname verification;
- nếu có mTLS, server xác minh certificate client và application mapping identity-to-permissions.

### 7.1. Raw SSLSocket/SSLEngine nên bật HTTPS endpoint identification

~~~java
SSLParameters clientParams = context.getDefaultSSLParameters();
clientParams.setProtocols(new String[]{"TLSv1.3"});
clientParams.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(clientParams);
socket.startHandshake();
~~~

Đây là **đoạn trích**, `socket` là raw client `SSLSocket`. Đặt trước handshake. `"HTTPS"` giúp JSSE kiểm tra peer hostname theo certificate. Nếu server certificate không có SAN đúng, handshake phải fail — không sửa bằng cách tắt xác minh hostname.

### 7.2. SNI không phải hostname verification

`SNIHostName` gửi tên virtual host mong muốn tới server trong ClientHello. Nó **không chứng minh** certificate nhận về là đúng host, nên SNI phải đi cùng hostname verification. Với DNS hostname hợp lệ có thể cấu hình:

~~~java
clientParams.setServerNames(
        java.util.List.of(new javax.net.ssl.SNIHostName("api.example.com")));
~~~

**Đoạn trích**. Nếu kết nối theo IP literal, không nhồi IP vào `SNIHostName`; xác minh certificate với SAN IP tương ứng. Trong demo loopback, raw TCP kết nối `127.0.0.1` và layered SSL socket được cấp logical peer host `localhost`, certificate test có DNS SAN localhost và IP SAN 127.0.0.1.

### 7.3. Phân biệt inbound và outbound endpoints

- **Inbound TLS server**: `SSLServerSocket.setSSLParameters` hoặc `HttpsConfigurator` đặt protocols/ciphers, server identity, có thể bật mTLS.
- **Outbound TLS client**: `SSLSocket/SSLEngine` hoặc Java HttpClient bảo đảm trust/hostname verification, protocols/ciphers, timeouts, SNI.
- Cùng một application có thể có **hai TLS hops** (reverse proxy → backend), mỗi hop phải được cấu hình, không suy “HTTPS bên ngoài” tức “TLS nội bộ tự an toàn”.

### 7.4. Java HttpClient và ALPN

`java.net.http.HttpClient.Builder.sslParameters(...)` có thể chấp nhận custom `SSLParameters` nhưng Javadoc nói **một số tham số do implementation quản lý**, như application protocol list (ALPN), **có thể bị bỏ qua**. Không dùng custom ALPN value để suy rằng HTTP/2 chắc chắn được negotiated. Xem `HttpResponse.version()` và runtime telemetry; vẫn giữ hostname verification.

## 8. mTLS, key sizes, signature schemes và named groups

### 8.1. mTLS không tự động từ cipher suite

Một TLS 1.3 hoặc TLS 1.2 `ECDHE_RSA` cipher suite không có nghĩa client đã gửi certificate. Muốn **mutual TLS**:

~~~java
SSLParameters serverPolicy = serverContext.getDefaultSSLParameters();
serverPolicy.setNeedClientAuth(true);
~~~

**Đoạn trích**. Server còn phải có TrustManagerFactory kiểm tra client certificate, client phải có KeyManagerFactory cung cấp cert/key, và ứng dụng phải map identity của certificate sang authorization. `setWantClientAuth(true)` chỉ yêu cầu **tùy chọn**, không thể coi là mTLS bắt buộc.

### 8.2. Certificate keys và thuật toán ký

Các lựa chọn thường gặp hiện nay có RSA với key size phù hợp policy (ví dụ RSA-3072 cho test lab), ECDSA dùng curves được duyệt (ví dụ P-256), chữ ký SHA-256/SHA-384 và các RSA-PSS/signature schemes khi provider/protocol hỗ trợ. Không dựa vào SHA-1 signatures, MD5, DSA/TLS 1.3 hoặc key sizes đã bị security policy cấm. Cần kiểm tra certificate chain, leaf EKU và signature schemes/cert types tương thích thật.

Một cipher suite `TLS_AES_128_GCM_SHA256` **không nói** server certificate là RSA, ECDSA hay public key bao nhiêu bits.

### 8.3. Key exchange named groups

Các nhóm như `x25519`, `secp256r1` và `secp384r1` có thể thích hợp với provider hiện đại. Nếu chọn/giới hạn group bằng JSSE system property hoặc các APIs mới, phải test trên JDK deployment thực tế; **không tự giả định Java 17 có mọi setter xuất hiện ở Javadoc Java 26**.

### 8.4. Không tự tạo thuật toán mật mã riêng

TLS cần chuẩn handshake, record protection, key derivation, certificate parsing, downgrade prevention và session management. Không dùng `javax.crypto.Cipher` tự mã hóa raw TCP rồi gọi đó là TLS. Sử dụng JSSE/provider được cập nhật và cấu hình đúng các public APIs hiện hành.

## 9. Áp dụng policy vào kết nối

### 9.1. SSLSocket client

~~~java
try (SSLSocket sslSocket = (SSLSocket)
        context.getSocketFactory().createSocket(host, port)) {
    SSLParameters policy = chooseApprovedPolicy(context);
    policy.setEndpointIdentificationAlgorithm("HTTPS");
    sslSocket.setSSLParameters(policy);
    sslSocket.startHandshake();
    String actualProtocol = sslSocket.getSession().getProtocol();
    String actualCipher = sslSocket.getSession().getCipherSuite();
}
~~~

Đây là **đoạn trích**, không độc lập: `chooseApprovedPolicy` là policy-builder do ứng dụng cung cấp, `context` có trust config phù hợp, `host/port` phải xác định. Quan trọng: **apply trước `startHandshake()`**. Tới khi handshake thành công, thông tin mới là negotiated facts.

### 9.2. SSLServerSocket server

~~~java
try (SSLServerSocket server = (SSLServerSocket)
        serverContext.getServerSocketFactory().createServerSocket(8443)) {
    SSLParameters allowed = chooseApprovedServerPolicy(serverContext);
    server.setSSLParameters(allowed);
    try (SSLSocket peer = (SSLSocket) server.accept()) {
        peer.setSoTimeout(5000);
        peer.startHandshake();
        // Xử lý application protocol nếu handshake hợp lệ.
    }
}
~~~

**Đoạn trích**. ServerContext cần private key/certificate identity, và `chooseApprovedServerPolicy` do hệ thống định nghĩa. `SSLServerSocket.setSSLParameters` tác động tới **newly accepted** sockets, không thay các kết nối đã handshake. Trong server thực tế cần connection/handshake deadlines, concurrency limits, request framing, graceful shutdown, observability.

### 9.3. SSLEngine (non-blocking)

~~~java
SSLEngine engine = context.createSSLEngine("api.example.com", 443);
engine.setUseClientMode(true);
SSLParameters allowed = chooseApprovedPolicy(context);
allowed.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(allowed);
~~~

**Đoạn trích**. `SSLEngine` chỉ thực hiện TLS state machine; application phải xử lý `wrap/unwrap`, tasks, packet/application buffers và network transport. Không có TCP/HTTP tự động.

### 9.4. Tránh SSLParameters mutable global singleton

`SSLParameters` mutable. Nếu nhiều endpoints dùng cùng một object và thread A gọi `setProtocols` trong khi B đang apply lên socket khác, sẽ khó đảm bảo policy đúng. Thiết kế nên lưu một **immutable policy definition** (list/version, cipher allowlist, client/server role) và tạo **new SSLParameters** từ `SSLContext.getDefaultSSLParameters()` cho từng connection/endpoint.

## 10. Java 17+ runnable: chọn protocol và cipher theo allowlist

Chương trình `TlsPolicySelectionDemo.java` kiểm thử **policy selection**, không thực hiện network handshake:

- Hai profiles: `TLS13_ONLY` và `TLS12_13`.
- Allowlist TLS 1.3 gồm AES-128-GCM, AES-256-GCM, ChaCha20-Poly1305.
- Allowlist TLS 1.2 gồm ECDHE_RSA/ECDHE_ECDSA + AES-GCM.
- Giao với **defaults AND supported** của provider trước khi apply.
- Với TLS13_ONLY, bắt buộc có TLS 1.3 và ít nhất một TLS 1.3 suite; TLS12_13 bắt buộc cả TLS 1.3 và TLS 1.2 cùng ít nhất một suite được duyệt cho mỗi protocol.
- Bật hostname verification `HTTPS` cho outbound client.
- Không bao gồm SSLv3/TLS 1.0/1.1 trong policy.
- Cipher giả không supported → **fail closed**.
- Kiểm tra `jdk.tls.disabledAlgorithms` property có cấu hình trong JDK test.

**Giới hạn:** các suites được cho phép cần tương thích certificate type của peer thực tế. Danh sách ví dụ **không phải chuẩn tuân thủ bất biến cho mọi tổ chức**. Kết quả output là cố định trên JDK test nhưng code có chủ ý fail-closed nếu runtime thiếu TLS 1.3/1.2/cipher bắt buộc.

### 10.1. File TlsPolicySelectionDemo.java

~~~java
import java.security.*;
import java.util.*;
import javax.net.ssl.*;

public final class TlsPolicySelectionDemo {
    enum Mode { TLS13_ONLY, TLS12_13 }

    static final List<String> TLS13_SUITES = List.of(
            "TLS_AES_128_GCM_SHA256",
            "TLS_AES_256_GCM_SHA384",
            "TLS_CHACHA20_POLY1305_SHA256");

    static final List<String> TLS12_SUITES = List.of(
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384");

    static void check(boolean okay, String reason) {
        if (!okay) throw new AssertionError(reason);
    }

    static List<String> enabledIntersection(
            String[] defaults, String[] supported, List<String> choices) {
        Set<String> enabled = new HashSet<>(Arrays.asList(defaults));
        Set<String> available = new HashSet<>(Arrays.asList(supported));
        return choices.stream()
                .filter(name -> enabled.contains(name) && available.contains(name))
                .toList();
    }

    static SSLParameters choose(SSLContext context, Mode mode) {
        SSLParameters defaults = context.getDefaultSSLParameters();
        SSLParameters supported = context.getSupportedSSLParameters();
        List<String> wantedProtocols = mode == Mode.TLS13_ONLY
                ? List.of("TLSv1.3") : List.of("TLSv1.3", "TLSv1.2");
        List<String> protocols = enabledIntersection(
                defaults.getProtocols(), supported.getProtocols(), wantedProtocols);
        if (!protocols.contains("TLSv1.3")
                || (mode == Mode.TLS12_13 && !protocols.contains("TLSv1.2"))) {
            throw new IllegalStateException("Required TLS versions unavailable");
        }

        List<String> wantedSuites = new ArrayList<>(TLS13_SUITES);
        if (mode == Mode.TLS12_13) wantedSuites.addAll(TLS12_SUITES);
        List<String> suites = enabledIntersection(
                defaults.getCipherSuites(), supported.getCipherSuites(), wantedSuites);
        if (suites.stream().noneMatch(TLS13_SUITES::contains)) {
            throw new IllegalStateException("No enabled approved TLS 1.3 cipher");
        }
        if (mode == Mode.TLS12_13
                && suites.stream().noneMatch(TLS12_SUITES::contains)) {
            throw new IllegalStateException("No enabled approved TLS 1.2 cipher");
        }

        SSLParameters out = context.getDefaultSSLParameters();
        out.setProtocols(protocols.toArray(String[]::new));
        out.setCipherSuites(suites.toArray(String[]::new));
        out.setEndpointIdentificationAlgorithm("HTTPS");
        return out;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());
        SSLParameters strict = choose(context, Mode.TLS13_ONLY);
        SSLParameters compatible = choose(context, Mode.TLS12_13);

        check(Arrays.equals(strict.getProtocols(), new String[] {"TLSv1.3"}),
                "strict must be TLS 1.3 only");
        check(Arrays.equals(compatible.getProtocols(),
                new String[] {"TLSv1.3", "TLSv1.2"}), "compat versions");
        check(Arrays.asList(strict.getCipherSuites()).stream()
                .allMatch(TLS13_SUITES::contains), "strict cipher allowlist");
        check(Arrays.asList(compatible.getCipherSuites()).stream()
                .allMatch(c -> TLS13_SUITES.contains(c) || TLS12_SUITES.contains(c)),
                "compat cipher allowlist");
        check("HTTPS".equals(strict.getEndpointIdentificationAlgorithm()),
                "must check hostname");
        boolean oldOffered = Arrays.asList(compatible.getProtocols()).stream()
                .anyMatch(s -> s.equals("TLSv1") || s.equals("TLSv1.1") || s.equals("SSLv3"));
        check(!oldOffered, "old protocols must be rejected");

        boolean invalidRejected = false;
        try {
            List<String> onlyInvalid = enabledIntersection(
                    context.getDefaultSSLParameters().getCipherSuites(),
                    context.getSupportedSSLParameters().getCipherSuites(),
                    List.of("TLS_FAKE_UNSUPPORTED_SUITE"));
            if (onlyInvalid.isEmpty()) {
                throw new IllegalArgumentException("No approved cipher available");
            }
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check(invalidRejected, "unsupported cipher should reject");

        check(Security.getProperty("jdk.tls.disabledAlgorithms") != null,
                "missing JDK TLS security policy");
        System.out.println("strict-protocol=" + strict.getProtocols()[0]);
        System.out.println("strict-ciphers-allowlisted=true");
        System.out.println("compatible-protocols="
                + String.join(",", compatible.getProtocols()));
        System.out.println("compatible-ciphers-allowlisted=true");
        System.out.println("legacy-protocols-offered=" + oldOffered);
        System.out.println("hostname-verification=HTTPS");
        System.out.println("invalid-cipher-rejected=" + invalidRejected);
        System.out.println("jdk-disabled-algorithms-configured=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 10.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 TlsPolicySelectionDemo.java
java TlsPolicySelectionDemo
~~~

**Stdout chính xác**, đã chạy trên OpenJDK 24 với target Java 17:

~~~text
strict-protocol=TLSv1.3
strict-ciphers-allowlisted=true
compatible-protocols=TLSv1.3,TLSv1.2
compatible-ciphers-allowlisted=true
legacy-protocols-offered=false
hostname-verification=HTTPS
invalid-cipher-rejected=true
jdk-disabled-algorithms-configured=true
tests=PASS
~~~

### 10.3. Diễn giải các assertions

- `strict-protocol=TLSv1.3`: Strict profile chỉ cho TLS 1.3.
- `strict-ciphers-allowlisted=true`: không có cipher ngoài TLS13_SUITES trong profile.
- `compatible-protocols=TLSv1.3,TLSv1.2`: profile tương thích có **hai phiên bản**, không có TLSv1/1.1.
- `compatible-ciphers-allowlisted=true`: chỉ từ hai explicit lists.
- `legacy-protocols-offered=false`: không đưa các giao thức cũ vào app policy.
- `hostname-verification=HTTPS`: outbound client SSLParameters đã bật endpoint identification, chưa thực hiện actual peer validation.
- `invalid-cipher-rejected=true`: allowlist chứa toàn giá trị không thể dùng làm ứng dụng từ chối thay vì tự chọn suite khác.
- `jdk-disabled-algorithms-configured=true`: runtime cung cấp JDK TLS security property; **không xác minh toàn bộ nội dung property có đúng compliance**, cũng không chứng minh đã handshake.
- `tests=PASS`: những invariant Java policy ở fixture đã đạt trên JDK test.

**Điểm quan trọng:** Đây là **policy unit test**, chưa chứng minh server certificate đúng, TLS version thật negotiated hay lỗ hổng SSL/TLS network đã được loại bỏ. Bài tiếp tục có live TLS integration test.

## 11. Java 17+ runnable: TLS 1.3 handshake và từ chối TLS 1.2-only client

Một policy có thể trông đúng trong `SSLParameters` nhưng khi handshake vẫn có thể thất bại vì certificate/hostname/supported signature/key group. Vì vậy chương trình thứ hai dùng **TCP loopback + SSLSocket/SSLServerSocket thực tế** và truststore riêng:

- Server chỉ bật **TLSv1.3** và `TLS_AES_128_GCM_SHA256`.
- Client “compatible” cho phép **TLSv1.3 và TLSv1.2**, với cả cipher suites phù hợp.
- Server dùng certificate RSA-3072 self-signed cho **localhost** và truststore được import certificate test (không trust-all).
- Client bật `EndpointIdentificationAlgorithm="HTTPS"`, handshake thành công với TLSv1.3, ghi nhận cipher suite negotiated và trao đổi `ping/pong`.
- Sau đó client thứ hai chỉ bật **TLSv1.2** (với TLS 1.2 ECDHE_RSA+AES-GCM), không có common version với server, nên phải bị **`SSLHandshakeException`**.
- Kết nối thứ hai bị từ chối có thể khiến phía server gặp `SSLException/SocketException` do peer đóng TCP; code bỏ qua `IOException` **chỉ trên negative test connection**, không bỏ qua lỗi của connection đầu tiên.

### 11.1. Tạo certificate và truststore (test-only)

Trong **thư mục trống dành riêng cho bài lab**, chạy:

~~~powershell
keytool -genkeypair -alias demo -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=localhost, OU=Training, O=Local Demo, C=VN" -validity 2 -storetype PKCS12 -keystore identity.p12 -storepass changeit -keypass changeit -ext "SAN=dns:localhost,ip:127.0.0.1" -ext "EKU=serverAuth" -noprompt
keytool -exportcert -alias demo -keystore identity.p12 -storepass changeit -rfc -file cert.pem
keytool -importcert -alias demo -file cert.pem -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

Ba lệnh tạo:
- `identity.p12`: server **private key + certificate**;
- `cert.pem`: certificate công khai export;
- `trust.p12`: client **trust anchor riêng** của bài lab.

**Cảnh báo:** mật khẩu `changeit`, self-signed certificate 2 ngày và `identity.p12` chỉ để chạy local fixture. Không commit keystore/private key vào repo; sau test phải xóa. **Không** copy cấu hình trust self-signed hoặc password này lên production.

Client kiểm tra certificate của server theo truststore và DNS SAN `localhost`. Trong chương trình, lớp TCP nối tới `127.0.0.1`, còn layered SSLSocket được cung cấp logical host `localhost` để JSSE xác minh endpoint identity. Đây là test được kiểm soát, không tự động gọi Internet.

### 11.2. File TlsVersionNegotiationDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.concurrent.*;
import javax.net.ssl.*;

public final class TlsVersionNegotiationDemo {
    static final String TLS13 = "TLSv1.3";
    static final String TLS13_CIPHER = "TLS_AES_128_GCM_SHA256";
    static final String TLS12_CIPHER = "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256";
    static final char[] TEST_PASSWORD = "changeit".toCharArray();

    static void check(boolean test, String reason) {
        if (!test) throw new AssertionError(reason);
    }

    static KeyStore store(Path file) throws Exception {
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            keyStore.load(in, TEST_PASSWORD);
        }
        return keyStore;
    }

    static SSLContext serverContext(Path identity) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store(identity), TEST_PASSWORD);
        SSLContext result = SSLContext.getInstance("TLS");
        result.init(kmf.getKeyManagers(), null, new SecureRandom());
        return result;
    }

    static SSLContext clientContext(Path trusted) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store(trusted));
        SSLContext result = SSLContext.getInstance("TLS");
        result.init(null, tmf.getTrustManagers(), new SecureRandom());
        return result;
    }

    static SSLParameters clientPolicy(boolean tls12Only) {
        SSLParameters p = new SSLParameters();
        p.setProtocols(tls12Only
                ? new String[] {"TLSv1.2"}
                : new String[] {"TLSv1.3", "TLSv1.2"});
        p.setCipherSuites(tls12Only
                ? new String[] {TLS12_CIPHER}
                : new String[] {TLS13_CIPHER, TLS12_CIPHER});
        p.setEndpointIdentificationAlgorithm("HTTPS");
        return p;
    }

    static void handleTwoConnections(SSLServerSocket listener) throws Exception {
        for (int number = 0; number < 2; number++) {
            try (SSLSocket socket = (SSLSocket) listener.accept()) {
                socket.setSoTimeout(4000);
                try {
                    socket.startHandshake();
                    if (number == 0) {
                        BufferedReader reader = new BufferedReader(
                                new InputStreamReader(socket.getInputStream(),
                                        StandardCharsets.UTF_8));
                        BufferedWriter writer = new BufferedWriter(
                                new OutputStreamWriter(socket.getOutputStream(),
                                        StandardCharsets.UTF_8));
                        check("ping".equals(reader.readLine()), "expected ping");
                        writer.write("pong\n");
                        writer.flush();
                    }
                } catch (IOException error) {
                    if (number == 0) throw error;
                    // A protocol-mismatch handshake can fail on both ends.
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("identity.p12 trust.p12");
        }
        SSLContext server = serverContext(Path.of(args[0]));
        SSLContext client = clientContext(Path.of(args[1]));
        try (SSLServerSocket listener = (SSLServerSocket)
                server.getServerSocketFactory().createServerSocket(
                        0, 16, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);
            listener.setEnabledProtocols(new String[] {TLS13});
            listener.setEnabledCipherSuites(new String[] {TLS13_CIPHER});

            ExecutorService workers = Executors.newSingleThreadExecutor();
            Future<?> serving = workers.submit(() -> {
                try {
                    handleTwoConnections(listener);
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                }
            });
            try {
                int port = listener.getLocalPort();
                try (Socket tcp = new Socket("127.0.0.1", port);
                        SSLSocket tls = (SSLSocket)
                                client.getSocketFactory().createSocket(
                                        tcp, "localhost", port, true)) {
                    tls.setSoTimeout(4000);
                    tls.setSSLParameters(clientPolicy(false));
                    tls.startHandshake();
                    check(TLS13.equals(tls.getSession().getProtocol()),
                            "expected strongest common TLS version");
                    check(TLS13_CIPHER.equals(tls.getSession().getCipherSuite()),
                            "expected agreed cipher");
                    BufferedWriter writer = new BufferedWriter(
                            new OutputStreamWriter(tls.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    writer.write("ping\n");
                    writer.flush();
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(tls.getInputStream(),
                                    StandardCharsets.UTF_8));
                    check("pong".equals(reader.readLine()), "application reply");
                    System.out.println("server-policy=TLSv1.3-only");
                    System.out.println("client-policy=TLSv1.3,TLSv1.2");
                    System.out.println("negotiated-protocol=" + tls.getSession().getProtocol());
                    System.out.println("negotiated-cipher=" + tls.getSession().getCipherSuite());
                    System.out.println("hostname-verification=HTTPS");
                    System.out.println("application-roundtrip=pong");
                }

                boolean mismatchRejected = false;
                try (Socket tcp = new Socket("127.0.0.1", port);
                        SSLSocket tls = (SSLSocket)
                                client.getSocketFactory().createSocket(
                                        tcp, "localhost", port, true)) {
                    tls.setSoTimeout(4000);
                    tls.setSSLParameters(clientPolicy(true));
                    tls.startHandshake();
                } catch (SSLHandshakeException expected) {
                    mismatchRejected = true;
                }
                check(mismatchRejected, "no overlap must reject handshake");
                serving.get(8, TimeUnit.SECONDS);
                System.out.println("tls12-only-client-rejected=" + mismatchRejected);
                System.out.println("tests=PASS");
            } finally {
                workers.shutdownNow();
                workers.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
~~~

### 11.3. Biên dịch và chạy

Sau khi chạy keytool ở mục 11.1 trong cùng thư mục:

~~~bash
javac -encoding UTF-8 --release 17 TlsVersionNegotiationDemo.java
java TlsVersionNegotiationDemo identity.p12 trust.p12
~~~

**Stdout chính xác** đã được kiểm thử trên OpenJDK 24, target Java 17:

~~~text
server-policy=TLSv1.3-only
client-policy=TLSv1.3,TLSv1.2
negotiated-protocol=TLSv1.3
negotiated-cipher=TLS_AES_128_GCM_SHA256
hostname-verification=HTTPS
application-roundtrip=pong
tls12-only-client-rejected=true
tests=PASS
~~~

### 11.4. Đọc đúng kết quả

- `server-policy=TLSv1.3-only`: server **chỉ cho** TLS 1.3.
- `client-policy=TLSv1.3,TLSv1.2`: client 1 cho cả hai versions.
- `negotiated-protocol=TLSv1.3`: **thực tế thương lượng TLS 1.3**, bởi có version chung.
- `negotiated-cipher=TLS_AES_128_GCM_SHA256`: suite negotiated, lấy từ SSLSession.
- `hostname-verification=HTTPS`: JSSE check certificate name `localhost`; truststore chứa test certificate được phép.
- `application-roundtrip=pong`: hai phía đã trao đổi bytes thật qua TLS sau handshake.
- `tls12-only-client-rejected=true`: client thứ hai chỉ hỗ trợ TLS 1.2, server chỉ chấp nhận TLS 1.3 → **handshake thất bại** thay vì downgrade.
- `tests=PASS`: các assertions trên fixture đều thành công.

**Giới hạn:** đây là một demo cấu hình được thiết kế để có **không có protocol intersection**; nó **không chứng minh** mọi lỗi certificate/cipher/signature đều được xử lý đúng trong production. Ngoài ra test đầu đã dùng setter trực tiếp trên server `setEnabledProtocols/setEnabledCipherSuites`, tương đương ý tưởng apply allowlist nhưng vẫn cần áp dụng cùng một policy-builder ở hệ thống production.

### 11.5. Vì sao TLS 1.2-only bị từ chối dù TLS 1.2 vẫn có thể an toàn?

Không phải vì TLS 1.2 “luôn bị cấm”. Nó bị từ chối vì **server của endpoint này được cấu hình TLS 1.3 only**. Nếu policy có yêu cầu tương thích đã được phê duyệt, server có thể cho phép cả TLS 1.2 với suites AEAD+ECDHE. Security correctness nghĩa là **tuân thủ profile đã chọn**, không chạy version thấp hơn hoặc cao hơn ngoài thỏa thuận.

### 11.6. Dọn dẹp môi trường test

Sau bài test, xóa `identity.p12`, `trust.p12` và `cert.pem` khỏi thư mục test. `identity.p12` có **private key**. Mật khẩu `changeit` là public test password; không dùng trong production, không đưa certificate/keys demo vào repository.

## 12. Xây một policy configuration nhất quán

Thay vì mỗi endpoint viết một danh sách chuỗi độc lập, ứng dụng có thể dùng một **immutable definition** (ví dụ `record` Java 17) thể hiện:

~~~java
public record TlsPolicyDefinition(
        List<String> protocolAllowlist,
        List<String> tls13CipherAllowlist,
        List<String> tls12CipherAllowlist,
        boolean requireClientCertificate) {
    public TlsPolicyDefinition {
        protocolAllowlist = List.copyOf(protocolAllowlist);
        tls13CipherAllowlist = List.copyOf(tls13CipherAllowlist);
        tls12CipherAllowlist = List.copyOf(tls12CipherAllowlist);
    }
}
~~~

Đây là **đoạn trích**, cần `java.util.List`. Chưa phải một policy validator hoàn chỉnh. Lưu definition bất biến và dùng `SSLContext.getDefaultSSLParameters()` để tạo **SSLParameters mới cho mỗi endpoint**, áp intersection/fail-closed. Chỉ mở mTLS trên **server role** theo profile; raw outbound client phải có HTTPS hostname identification. Tránh share một SSLParameters mutable global.

### 12.1. Policy as code

Một cấu hình deploy có thể giữ một `tlsProfile` trong file quản lý tập trung, nhưng phải:

- Validate schema và những giá trị cho phép trước khi start service.
- Từ chối tên protocol/cipher không được phê duyệt.
- Không để per-user/per-request input quyết định security policy của outbound client.
- Dùng runtime allowlist theo JDK/provider, fail ở startup nếu không đáp ứng.
- Log policy version/hash và negotiated outcomes cho troubleshooting, tránh lộ secrets.
- Có audit trail và approval cho exceptions.
- Có kế hoạch rút TLS 1.2 theo dữ liệu client compatibility, không thay đổi mù.

### 12.2. Profile selection theo endpoint

Ví dụ:
- **Public API hiện đại**: TLS 1.3 only nếu có thể buộc tất cả clients cập nhật.
- **Enterprise partner API**: TLS 1.3 + TLS 1.2 ECDHE+AEAD nếu hợp đồng vẫn cần, có deadline loại bỏ, mTLS tùy business.
- **Internal services**: TLS 1.3 + service identity/mTLS theo zero-trust policy, không dựa vào “nội bộ là an toàn”.
- **Legacy isolated integration**: cần đánh giá risk acceptance riêng; nếu đối tác không thể nâng cấp, đặt gateway/segment bảo vệ thay vì hạ cấp toàn bộ ứng dụng chính.

Không đồng nhất “partner dùng TLS 1.2” với “cần bật TLS 1.0”: quyết định interoperability dựa trên **protocol scans và negotiated cipher evidence**.

### 12.3. Certificate and trust lifecycle không nằm trong SSLParameters

Cấu hình versions/ciphers không giải quyết:
- leaf certificate hết hạn;
- certificate SAN sai DNS;
- private key không match certificate;
- CA bị xóa khỏi truststore;
- revocation/status đã thay đổi;
- mTLS client identity không có quyền thao tác;
- LB/proxy terminate TLS bằng policy khác.

Những yêu cầu này phải được triển khai bằng PKI/key management và kiểm thử end-to-end.

## 13. Cách kiểm tra runtime và handshake

### 13.1. Trước khi kết nối

Có thể quan sát versions/suites JDK đang cho phép:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, new SecureRandom());
System.out.println(Arrays.toString(
        context.getDefaultSSLParameters().getProtocols()));
System.out.println(Arrays.toString(
        context.getDefaultSSLParameters().getCipherSuites()));
~~~

**Đoạn trích**. Không copy output vào tài liệu rồi coi là bất biến. Defaults khác nhau theo JDK version, vendor, provider order, `java.security`, hardware/PKCS#11, runtime flags và client/server role.

### 13.2. Sau handshake

~~~java
SSLSession session = socket.getSession();
String protocol = session.getProtocol();
String cipher = session.getCipherSuite();
~~~

**Đoạn trích**. Đây mới là negotiated facts. Không log raw TLS session secrets; nếu muốn metrics, log protocol/cipher values đã chuẩn hóa và hostname/endpoint identifier không chứa secrets. Không để logs sinh cardinality cực cao từ client-supplied strings.

### 13.3. Kiểm tra ngoài Java process

Nếu endpoint được public qua reverse proxy, một chương trình Java có policy đúng **không chứng minh public port đã đúng**, vì proxy có thể terminate TLS bằng config khác. Test từng hop TLS bằng công cụ phù hợp và CI security scans, có danh sách protocol/cipher outcomes:

- TLS 1.3 compatible client → success.
- TLS 1.2-only client → fail nếu endpoint strict, success nếu endpoint compatibility cho phép.
- TLS 1.1/1.0 client → fail.
- Certificate sai host → fail.
- Certificate expired/unknown CA → fail.
- Weak/static RSA cipher → fail theo policy.
- ALPN app protocol match/mismatch → hành vi application rõ.
- mTLS missing/untrusted cert → fail khi require.
- Valid clients qua proxy/backend → end-to-end policy đúng.

## 14. Troubleshooting lỗi TLS theo lớp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra an toàn |
| --- | --- | --- |
| `No appropriate protocol` | Không còn protocol enabled phù hợp | Kiểm tra SSLParameters, JDK disabledAlgorithms, peer support |
| `protocol_version` alert | Client/server không có common TLS version | So sánh allowed versions, không tự fallback legacy |
| `handshake_failure` | Không chung ciphers/groups/signature schemes/cert type | Kiểm tra accepted suites, cert/key/peer logs |
| `no cipher suites in common` | Policy quá hẹp, certificate type không phù hợp | Xem default+supported, provider, approved allowlists |
| `PKIX path building failed` | Trust chain không có anchor hợp lệ | Kiểm tra truststore/chain, không trust-all |
| `No subject alternative DNS name` | Certificate không có SAN cho hostname | Dùng đúng certificate/domain, không disable HTTPS check |
| `No subject alternative names matching IP` | IP address thiếu SAN kiểu IP | Cấp cert SAN IP hoặc gọi endpoint theo DNS phù hợp |
| `CertificateExpiredException` | Certificate hoặc chain expired | Rotate certificate/chain |
| `bad_certificate` | Peer từ chối client/server cert | Kiểm tra mTLS, chain, EKU, trust |
| `unknown_ca` | Peer không trust CA | Phân phối trust anchor theo PKI policy |
| `SSLHandshakeException` sau nâng JDK | Provider/security defaults thay đổi | So sánh release notes và java.security properties |
| TLS 1.3 chạy nhưng HTTP request fail | ALPN/application framing không khớp | Xem HTTP version, server/proxy behavior |
| Test TLS12-only client bị reject | Endpoint TLS13-only | Đây là **kết quả mong đợi** của strict profile |
| Supported có cipher nhưng handshake fail | Cipher bị disabled/PKIX/key constraint | Đừng nhầm capability với permission |
| mTLS client không có cert | Server needClientAuth | Cấu hình client key manager + cert đúng |
| Kết nối ngắt bất ngờ khi reject | TLS alert/TCP close ở một phía | Phân loại bằng exceptions/counters, tránh nuốt lỗi hợp lệ |

**Nguyên tắc xử lý:** làm rõ nguyên nhân ở tầng version, cipher, key exchange, certificate, trust, hostname hay network. Đừng dùng lời giải “tắt hết security” như trust-all/hostnameVerifier=true/enable legacy.

### 14.1. TLS debug logs có thể rất nhạy cảm

Java có `-Djavax.net.debug=ssl,handshake` để xem handshake trong môi trường dev/test. Debug output có thể lớn và tiết lộ thông tin của kết nối/certificate/metadata; không bật toàn thời gian production hoặc log thẳng vào ticket công khai. Che các thông tin nhạy cảm trước khi chia sẻ.

### 14.2. Khi gặp “unsupported cipher”

Không buộc ứng dụng bật `TLS_FAKE_UNSUPPORTED_SUITE` hoặc toàn bộ supported list. Test fixture cố tình dùng giá trị giả để chứng minh **fail closed**. Với cipher cụ thể nhưng thiếu trên môi trường thật, rà soát JDK version/provider/compliance/certificate type, rồi quyết định policy migration có phê duyệt.

## 15. Checklist tích hợp và kiểm thử an ninh

| Trường hợp | Kỳ vọng |
| --- | --- |
| Strict TLS13 policy | Chỉ `TLSv1.3` được offer |
| Compatibility profile | TLS 1.3 và TLS 1.2 approved, không protocol cũ |
| TLS13 AES-GCM | Cipher negotiated nằm trong allowlist |
| TLS13 ChaCha20 | Chỉ dùng khi provider/peer/policy hỗ trợ |
| TLS12 ECDHE+AES-GCM | Có thể dùng nếu compat approved |
| TLS12 static RSA key transport | Bị cấm theo policy |
| TLS1.1/1.0 | Bị từ chối |
| Unsupported cipher name | Policy selection reject trước connect |
| Supported-but-disabled suite | Handshake vẫn bị chặn |
| JDK disabledAlgorithms | Không bị ứng dụng vô hiệu hóa |
| JDK certpath policy | Certificate yếu/hết hạn/không trusted không qua validation |
| Runtime security properties changed | App startup validation và rollout theo kiểm soát |
| RSA/ECDSA server certificate | Signature schemes/cipher TLS12 phù hợp |
| TLS13 cipher vs certificate type | Không nhầm tên AES suite với RSA cert |
| TLS13 key exchange | Named group phù hợp peer |
| TLS session resumption | Security/identity rules giữ nguyên |
| Client expected DNS host | Certificate SAN DNS đúng |
| Client expected IP | Certificate SAN IP đúng |
| Invalid hostname | Handshake fail |
| Self-signed untrusted cert | Handshake fail |
| Self-signed test cert đã import | Pass trong fixture riêng, không trust-all |
| NeedClientAuth server | Client không có cert phải fail |
| WantClientAuth server | Không được nhầm là mandatory auth |
| ALPN HTTP/2 | Chỉ advertise khi app stack hỗ trợ |
| Java HttpClient custom SSLParameters | Không giả định internal ALPN override |
| SSLServerSocket config | Apply trước accept, policy cho new connections |
| SSLEngine config | Apply trước beginHandshake, wrap/unwrap đúng |
| Multiple outbound endpoints | Mỗi endpoint có trust + hostname policy riêng |
| Proxy TLS termination | Kiểm tra cả public TLS và backend hop |
| Slow handshake | Deadline/quotas ngăn DoS |
| Certificate rotation | Chain/issuer/key changes không làm mất availability bất ngờ |
| JDK patch upgrade | Repeat TLS compatibility + security suite |
| Monitoring | Negotiated versions/ciphers và handshake failures theo thời gian |

### 15.1. Negative tests đặc biệt quan trọng

Một test chỉ có “TLS 1.3 works” **không chứng minh** TLS 1.0/1.1 đã bị chặn. Với security policy, luôn có **negative matrix**:
- client TLS12-only vs strict server TLS13-only;
- client TLS10-only;
- wrong/untrusted/expired certificate;
- cipher suite ngoài allowlist;
- mTLS client thiếu cert;
- host khác SAN;
- invalid algorithm constraints.

Ngoài kết quả reject, cần chắc chắn **không có retry hạ cấp** ở HTTP client, gateway hoặc connection pool.

### 15.2. Đảm bảo production observability không lộ secrets

Metrics hữu ích: TLS handshake success/failure rate, error class, negotiated version/cipher distribution, mTLS auth fail, cert expiry horizon, truststore rotation, latency. Không log private key, session tickets/secrets, Authorization, HTTP Cookie, user passwords. Tên protocol/cipher không phải bí mật, nhưng peer identity/logs có thể chứa dữ liệu cần kiểm soát.

## 16. Câu hỏi tự đánh giá

**1.** Java `SSLParameters` có từ khi nào, còn dùng được không?

**Đáp án:** Từ Java 6, vẫn còn trong Java SE 26; dùng cùng JSSE và TLS policy hiện hành.

**2.** Giao thức nên mặc định chọn cho endpoint mới?

**Đáp án:** Ưu tiên TLS 1.3. TLS 1.2 chỉ giữ khi tương thích được yêu cầu và được chấp thuận.

**3.** TLS 1.0 và TLS 1.1 có nên bật cho hệ thống mới không?

**Đáp án:** Không; đã bị loại bỏ theo RFC 8996 và không đáp ứng baseline bảo mật hiện đại.

**4.** TLS 1.3 cipher `TLS_AES_128_GCM_SHA256` có cho biết server dùng RSA certificate không?

**Đáp án:** Không. TLS 1.3 tách cipher suite khỏi authentication/signature/key exchange groups.

**5.** TLS 1.2 `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` khác `TLS_RSA_WITH_AES_128_GCM_SHA256` thế nào?

**Đáp án:** Suite đầu dùng ECDHE key exchange có forward secrecy và RSA certificate authentication; suite thứ hai dùng static RSA key transport không có forward secrecy.

**6.** Có nên dùng toàn bộ `getSupportedSSLParameters().getCipherSuites()`?

**Đáp án:** Không. Supported chỉ nói về khả năng implementation, không phải mức an toàn/phê duyệt.

**7.** Cần dùng default hay supported?

**Đáp án:** Chính sách nên giao **explicit approved allowlist** với default-enabled/supported, rồi fail-closed khi không đủ bắt buộc.

**8.** `setCipherSuites` có thể mở lại suite bị `jdk.tls.disabledAlgorithms` cấm không?

**Đáp án:** Không. Setter có thể chấp nhận tên nhưng handshake vẫn bị JSSE chặn theo security property.

**9.** Cipher suite GCM mạnh có đủ chứng minh server đáng tin không?

**Đáp án:** Không. Cần kiểm tra certificate chain, hostname/SAN, trust, validity và policy.

**10.** SNI có giống hostname verification không?

**Đáp án:** Không. SNI nói hostname mong muốn; certificate verification chứng minh peer phù hợp hostname đó.

**11.** Nếu server TLS13-only và client TLS12-only, nên làm gì?

**Đáp án:** Handshake fail như policy. Nâng cấp client hoặc có exception/compat endpoint được duyệt, không tự bật protocol cũ.

**12.** `SSLSession.getProtocol()` khác `SSLParameters.getProtocols()`?

**Đáp án:** SSLParameters là tập allowed, SSLSession là phiên bản thực negotiated sau handshake.

**13.** Vì sao không mặc định hardcode duy nhất một cipher suite cho mọi hệ thống?

**Đáp án:** Provider/peer/certificate type/compliance/performance khác nhau và có thể thay khi nâng JDK; cần allowlist có quản lý.

**14.** NeedClientAuth và WantClientAuth có khác nhau không?

**Đáp án:** Need yêu cầu client cert, Want chỉ muốn/không bắt buộc; cần client truststore và authorization ngoài TLS.

**15.** Java HttpClient chắc chắn dùng ALPN list custom trong SSLParameters không?

**Đáp án:** Không, implementation có thể quản lý ALPN và bỏ qua phần đó của SSLParameters.

**16.** RSA-3072 self-signed certificate trong ví dụ có nên đưa lên production?

**Đáp án:** Không. Nó là vật liệu test nội bộ, truststore và password cũng chỉ phục vụ fixture.

**17.** Khi cập nhật JDK và phát sinh handshake fail, có nên gỡ disabledAlgorithms?

**Đáp án:** Không. Phân loại protocol/cipher/cert/trust issues, sửa peer hoặc có exception policy được duyệt; không mở yếu tố legacy.

### Bài tập thực hành

1. Chạy `TlsPolicySelectionDemo`, giải thích tập protocol/cipher đã chọn cho strict và compat.
2. Bỏ TLS 1.3 khỏi wanted list trong strict profile, kiểm tra fail-closed assertion.
3. Thêm một cipher không supported vào allowlist và xác nhận nó bị bỏ; nếu không còn suite hợp lệ phải reject.
4. Thử so sánh JDK default-enabled và supported TLS protocols/ciphers; không coi mọi supported đều được phép.
5. Chạy `TlsVersionNegotiationDemo`, kiểm tra negotiated protocol/cipher.
6. Sửa server cho phép TLS 1.2 + ECDHE_RSA AES-GCM trong **lab khác**, kiểm tra TLS12-only client có thể handshake.
7. Sửa server strict chỉ TLS 1.3 rồi thử client TLS1.1-only, xác nhận từ chối; không bật lại TLS1.1.
8. Đổi truststore client sang truststore trống, xác nhận PKIX path fail.
9. Cấp certificate thiếu SAN localhost rồi bật HTTPS endpoint identification, xác nhận reject.
10. Thử certificate expired/cert dùng key size trái policy ở môi trường test.
11. Tạo server mTLS thật với client PKCS12 identity + truststore, NeedClientAuth true và negative test không có cert.
12. Dùng JSSE debug logs có kiểm soát, tìm phiên bản TLS và thuật toán trong ClientHello/ServerHello.
13. Viết immutable TlsPolicyDefinition với List.copyOf, tạo SSLParameters fresh cho từng connection.
14. Thử hai endpoints client/server song song và xác nhận không rò mutable SSLParameters giữa chúng.
15. Đo negotiated TLS version/cipher trên reverse proxy và backend TLS hop khác nhau.
16. Viết test JDK upgrade regression để phát hiện policy đã đổi defaults.
17. Benchmark TLS 1.3 AES-GCM so với ChaCha20-Poly1305 trên provider/hardware thực, không suy chung chung.
18. Thêm SNI DNS name và certificate multi-SAN trong lab, xác nhận hostname verification độc lập.
19. Đọc OWASP và RFC 9325, nêu vì sao TLS 1.2 ECDHE AEAD được chấp thuận có điều kiện.
20. Tạo kế hoạch migration những clients còn TLS 1.2 sang TLS 1.3 dựa trên measured usage.

## 17. Tài liệu chính thức và nguồn còn áp dụng

- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): chọn protocols/cipher suites/endpoint identity/algorithm constraints.
- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): default-supported parameters và context factory.
- [Oracle Java SE 26 — SSLSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): configuration, handshake và session.
- [Oracle Java SE 26 — SSLServerSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLServerSocket.html): server-side protocol/cipher list.
- [Oracle Java SE 26 — SSLEngine](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): non-blocking TLS policy.
- [Oracle Java SE 26 — SSLSession](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSession.html): negotiated version và cipher.
- [Oracle Java SE 26 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): SunJSSE support/protocols/cipher suites.
- [Oracle Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): canonical protocol/cipher/crypto names.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): server/client certificate identity.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): trust anchors/certpath.
- [Oracle Java SE 26 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS client certificate/hostname handling.
- [Oracle Java SE 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): sslParameters, sslContext và internal application protocols.
- [Oracle Java SE 26 — Java Security API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html): security properties.
- [Oracle Java SE 26 — AlgorithmConstraints](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/AlgorithmConstraints.html): algorithm policy contracts.
- [Oracle Java SE 26 — SSLHandshakeException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html): handshake failures.
- [Oracle Java SE 26 — keytool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): test keystore/truststore.
- [Oracle Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): API Java17 example availability.
- [Oracle — Configure JDK and JRE Cryptographic Algorithms](https://www.java.com/en/configure_crypto.html): JDK disabled algorithms và hiện đại hóa chính sách.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS 1.3/TLS 1.2, suites, forward secrecy.
- [IETF RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html): TLS 1.3 negotiation/cryptographic design.
- [IETF RFC 9325 — Recommendations for Secure Use of TLS/DTLS](https://www.rfc-editor.org/rfc/rfc9325.html): secure protocol/cipher guidance.
- [IETF RFC 8996 — Deprecating TLS 1.0 and TLS 1.1](https://www.rfc-editor.org/rfc/rfc8996.html): status của các giao thức cũ.

**Ghi nhớ:** TLS policy hiện đại ưu tiên **TLS 1.3**, cho phép **TLS 1.2 ECDHE+AEAD chỉ khi có lý do được phê duyệt**. Chọn cipher suites từ **explicit allowlist ∩ default-enabled ∩ supported**, nhưng vẫn phải tôn trọng **JDK disabledAlgorithms/certpath policy, certificate chain và hostname verification**. Không bật mọi supported suites, không hạ cấp SSLv3/TLS1.0/1.1, không dùng trust-all. **SSLParameters là allowed policy; SSLSession mới phản ánh negotiated facts.** Hai chương trình Java 17+ đã chứng minh lựa chọn policy fail-closed và TLS 1.3 handshake thực tế từ chối client TLS1.2-only khi server chỉ cho TLS1.3.
