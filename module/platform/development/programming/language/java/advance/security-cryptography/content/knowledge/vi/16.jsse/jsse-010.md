# 16.10 Tránh cấu hình tin mọi chứng thư hoặc bỏ qua kiểm tra hostname trong ví dụ ứng dụng

Một đoạn Java dùng HTTPS có thể **bắt tay TLS thành công, mã hóa dữ liệu và trả về HTTP 200** nhưng vẫn không bảo vệ được người dùng trước kẻ đứng giữa nếu người viết ví dụ cố tình cấu hình **tin mọi chứng thư (trust-all)** hoặc **không xác minh tên máy chủ (hostname verification)**. Đây là một trong những anti-pattern nguy hiểm nhất khi dùng **Java Secure Socket Extension (JSSE)**: lỗi chứng thư bị che đi thay vì được sửa, đoạn mã “chạy được trên máy tôi” bị sao chép sang ứng dụng thật, và thông tin đăng nhập/token có thể được gửi tới đối tác không được xác thực.

**Nguyên tắc của bài:** Một TLS client an toàn phải kiểm **cả (1) đường dẫn chứng thư tới trust anchor đáng tin** và **(2) danh tính endpoint đúng hostname/IP mà ứng dụng chủ định kết nối**. Không vì môi trường thử nghiệm hoặc lỗi certificate mà bỏ một trong hai phép kiểm. Ví dụ hoàn chỉnh ở đây sử dụng **trust manager chuẩn của Java và endpoint identification `HTTPS`**, đồng thời chủ động kiểm các trường hợp kết nối **phải bị từ chối** — không xây dựng một trust-all implementation có thể bị copy nhầm.

Bài học thuộc **16. JSSE** và tập trung vào các ví dụ ứng dụng Java 17+: chọn truststore có kiểm soát, bật xác minh endpoint cho `SSLSocket` thấp tầng, giữ mặc định an toàn của HTTPS clients, phân biệt lỗi trust và hostname, cùng chiến lược kiểm thử/code review ngăn cấu hình không an toàn lọt vào production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **mã hóa TLS không đủ** nếu đối tác không được xác thực, và hai cơ chế **PKIX chain validation** với **hostname verification** giải quyết hai câu hỏi khác nhau.
2. Nhận diện anti-pattern: trust manager chấp nhận mọi certificate, `HostnameVerifier` luôn trả `true`, vô hiệu hóa endpoint identification, tắt kiểm chữ ký/hạn dùng, hoặc tự động retry với cấu hình “insecure”.
3. Viết **JSSE client dùng `TrustManagerFactory` chuẩn**, truststore xác định và `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` khi cần.
4. Hiểu hành vi của `HttpsURLConnection`, `java.net.http.HttpClient`, `SSLSocket` và `SSLEngine`, cùng ranh giới trách nhiệm của `KeyManagerFactory` và `TrustManagerFactory`.
5. Chạy demo với CA local và chứng thư có SAN `DNS:localhost`: **đúng CA + đúng hostname thì pass; sai CA hoặc sai hostname phải fail**.
6. Thiết kế test âm tính/CI và sửa tận gốc lỗi `PKIX path building failed`, hostname mismatch, thiếu intermediate và certificate expired mà **không bỏ bảo mật**.

## 2. Điều TLS bảo vệ, điều TLS không thể làm khi bỏ xác thực

TLS có nhiều thuộc tính:

- **Confidentiality:** lưu lượng ứng dụng được mã hóa khi bắt tay và cipher suite được dùng đúng.
- **Integrity:** bản tin có cơ chế bảo vệ chống sửa đổi trong phiên TLS.
- **Endpoint authentication:** client cần biết mình đã thiết lập phiên an toàn với **đúng đối tượng**.
- **Protocol policy:** phiên bản TLS, cipher suite, certificate purpose, trust, identity và các ràng buộc được kiểm theo chính sách.

Nếu client **tin mọi certificate**, một kẻ đứng giữa có thể tạo certificate tự ký mang khóa của họ, thiết lập TLS riêng với client, giải mã request rồi chuyển tiếp tới server thật qua một phiên TLS thứ hai. Cả hai phiên đều có thể “mã hóa mạnh”; **vấn đề nằm ở chỗ client đã xác thực nhầm đối tác**.

Nếu client **kiểm CA chain nhưng bỏ hostname check**, kẻ có certificate hợp lệ cho **một hostname khác** cũng có thể được chấp nhận khi ứng dụng muốn kết nối endpoint mục tiêu. Ví dụ CA nội bộ đã cấp chứng thư cho `inventory.internal`, nhưng client cấu hình gọi `payments.internal`: certificate chain có thể hợp lệ và vẫn **không phải danh tính cần gặp**.

~~~text
Ứng dụng cần gọi: https://payments.example.test
                |
                v
             TLS peer
                |
       +--------+---------+
       |                  |
       v                  v
   PATH TRUST         ENDPOINT NAME
  CA/PKIX chain       DNS/IP trong URL
  chữ ký/hạn dùng     so với SAN leaf
       |                  |
       +--------+---------+
                |
          CẢ HAI PASS?
           /       \
         Có         Không
         |            |
   có thể tiếp tục  HỦY bắt tay
   theo policy       KHÔNG fallback insecure
~~~

**Tin chuỗi chứng thư không đồng nghĩa khớp hostname**, và **khớp hostname không đồng nghĩa CA được tin**. Hai điều kiện đều bắt buộc trong HTTPS client đúng chuẩn; việc TLS có trả `SSLSession` hay phiên đã dùng AES-GCM không làm thay đổi yêu cầu này.

### 2.1. Bảng quyết định tối thiểu

| Chain/CA tin cậy | Hostname/IP đúng | Hành vi đúng |
| --- | --- | --- |
| Pass | Pass | Có thể chấp nhận khi các kiểm tra TLS và chính sách khác đạt |
| Pass | **Fail** | **Reject**: chứng thư của host khác |
| **Fail** | Pass | **Reject**: CA/trust anchor không phù hợp |
| **Fail** | **Fail** | **Reject**: cả hai điều kiện sai |

Từ “có thể” là quan trọng: còn phải xét **KeyUsage, EKU, thời hạn, thuật toán, revocation, policy**, và **authorization** ở lớp ứng dụng. Một chứng thư hợp lệ không mặc định cho phép thực hiện lệnh thanh toán hoặc truy cập tenant bất kỳ.

## 3. Cấu hình “trust-all” thực sự phá điều gì?

Trong JSSE, trust manager chịu trách nhiệm xác minh certificate chain theo chính sách. Một trust manager bình thường dùng tập **trusted root CAs/certificates được chọn trước**, kiểm chứng chain, thuật toán và các điều kiện liên quan trong ngữ cảnh TLS.

Anti-pattern trust-all thường có dạng tư duy:

~~~text
Nếu TLS báo "certificate not trusted":
    thay trust manager chuẩn bằng bản luôn trả "accept"
    hoặc bỏ hết logic checkServerTrusted(...)
    hoặc đổi accepted issuers thành thứ gì đó để tránh lỗi
Kết quả: handshake có thể pass với certificate của bất kỳ kẻ nào.
~~~

Đây là **mô tả anti-pattern**, không phải hướng dẫn viết/cài trust manager bỏ qua kiểm tra. Không đưa một `X509TrustManager` rỗng hoặc một `SSLContext` trust-all vào chương trình thực hành vì code dễ bị sao chép. Tương tự, `getAcceptedIssuers()` tự nó **không quyết định certificate hợp lệ**; việc giả dữ liệu ở đây không thay thế xác minh chain thực sự.

Một ứng dụng áp dụng trust-all có thể gửi:

- Bearer token, cookie phiên, API key hoặc thông tin tài khoản;
- Dữ liệu người dùng/thanh toán;
- Nội dung yêu cầu điều khiển hệ thống;
- Trả lời quan trọng mà ứng dụng tin là từ server thật;

tới một đối tượng sở hữu private key của certificate **không hề được CA mà người dùng tin chứng nhận**.

**Mã hóa nhưng không xác thực đúng peer không thể được coi là HTTPS an toàn.** Bật encryption cipher suite mạnh hơn không khôi phục việc xác thực đã bị loại bỏ.

### 3.1. “Chỉ trust-all cho localhost/dev” có được không?

Không nên dùng trust-all làm ví dụ mẫu hoặc workaround:

1. Flag dev/test có thể bị bật nhầm ở staging/production.
2. Một thư viện dùng `SSLContext.setDefault` hoặc property toàn JVM có thể làm mất bảo mật của **những HTTP clients khác** cùng process.
3. Proxy, công cụ kiểm thử mạng, Wi-Fi công cộng hoặc kẻ kiểm soát DNS có thể chủ động tạo certificate bất kỳ để đánh chặn lưu lượng.
4. Cách chữa tạm không hướng dẫn người học **nguyên nhân thực**: CA chưa trust, hostname/SAN sai, thiếu intermediate hoặc certificate hết hạn.
5. Test chạy thành công với trust-all không kiểm chứng điều quan trọng nhất: ứng dụng **có từ chối peer không hợp lệ không**.

**Thay thế đúng cho môi trường phát triển:** tạo **CA dev riêng**, cấp leaf SAN đúng endpoint, đưa certificate CA dev đã xác minh vào **truststore chỉ dành cho dev**, dùng trust manager mặc định trên store đó, vẫn kiểm hostname.

### 3.2. Tại sao không “pin certificate” bằng trust-all?

Pinning public key/certificate (khi threat model cần) là **một ràng buộc bổ sung**, không phải giấy phép bỏ CA/hostname validation mặc định. Các triển khai pinning phải có kế hoạch backup pins, rotation, tránh khóa nhầm ứng dụng, và xác định rõ mối quan hệ với trust anchors. Một đoạn code trust-all rồi so string Subject hoặc một fingerprint lấy động từ kết nối **không phải pinning an toàn**; nó có thể pin luôn certificate attacker đưa vào lần đầu.

## 4. Bỏ hostname verification gây lỗi gì?

Một client có thể **tin CA** của certificate nhưng đang gọi **sai host**:

~~~text
URL mục tiêu: https://pay.example.com
Leaf được CA tin ký:
    SAN DNS: files.example.com

Chain validation = PASS
Name verification = FAIL
Quyết định an toàn = REJECT
~~~

Tắt hostname verification nghĩa là client **không còn yêu cầu certificate chứng minh tên đích**. Với CA nội bộ có khả năng cấp nhiều dịch vụ, một server hợp lệ khác có thể vô tình hoặc cố ý được dùng để mạo danh endpoint mục tiêu.

Các anti-pattern cần phát hiện:

- Một `HostnameVerifier` của `HttpsURLConnection` **luôn trả `true`**;
- Một client library có flag hoặc policy `NoopHostnameVerifier`, `allowAllHosts` hoặc tên tương đương; chú ý API phụ thuộc thư viện/version;
- Raw `SSLSocket` dùng trust manager chuẩn nhưng **không bật endpoint identification** khi đang dùng làm HTTPS client;
- `SSLEngine` không được cấu hình thuật toán xác thực endpoint hoặc thiếu peer host chính xác;
- “Retry fallback”: sau `SSLHandshakeException`, thử lại với client đã tắt hostname checking;
- Lấy hostname cần kiểm từ **certificate mà peer gửi** thay vì tên trong URL/config tin cậy;
- Tự viết bộ so khớp DNS bằng `endsWith` hoặc chấp nhận mọi wildcard.

Không xem `CN` trong Subject hoặc tên **alias** trong `KeyStore` là đủ thay **SAN**. Với chứng thư HTTPS hiện đại, certificate cần có `dNSName SAN` hoặc `iPAddress SAN` đúng loại theo reference identity mà client đã chọn.

### 4.1. SAN DNS và SAN IP không hoán đổi

| Đích client chủ định kết nối | Leaf SAN | Name check |
| --- | --- | --- |
| `https://localhost` | `DNS:localhost` | Pass nếu chain được tin |
| `https://127.0.0.1` | Chỉ `DNS:localhost` | **Fail**: thiếu IP SAN |
| `https://127.0.0.1` | `IP:127.0.0.1` | Pass về name nếu chain cũng được tin |
| `https://api.example.test` | `DNS:api.example.test` | Pass về name |
| `https://api.example.test` | `DNS:another.example.test` | **Fail** |
| `https://192.0.2.10` | `DNS:192.0.2.10` | Không thay `iPAddress` SAN hợp lệ |

DNS có thể resolve `api.example.test` thành địa chỉ IP cụ thể nhưng **tên tham chiếu vẫn là hostname URL**, không phải reverse DNS của IP. Nếu ứng dụng dùng TCP tới IP nhưng mong identity DNS, cần giữ **logical peer hostname** đúng ở tầng TLS/HTTP theo API.

**SNI (Server Name Indication)** chỉ giúp server chọn certificate khi phục vụ nhiều virtual hosts; SNI **không tự xác minh certificate do server trả về**. Client vẫn phải kiểm trust chain và SAN.

### 4.2. CN fallback, wildcard và IDN

- Tên `CN=api.example.com` trong Subject không nên dùng thay SAN. Một số implementations lịch sử có fallback đặc biệt khi thiếu SAN, nhưng **không dựa vào fallback đó cho cấp certificate hoặc kiểm thử HTTPS mới**.
- Wildcard `*.example.com` không được coi là hợp lệ cho vô hạn subdomain hay mọi cấp nhãn. Dùng thuật toán endpoint identification của HTTPS client chuẩn, không tự viết regex đơn giản.
- Internationalized domain names đòi quy tắc IDNA/Punycode và chuẩn so khớp tên phù hợp; `equalsIgnoreCase` trên Unicode string không phải giải pháp đầy đủ.
- SAN kiểu URI/email/workload identity có quy tắc riêng, không mặc nhiên thay DNS SAN cho HTTPS.

## 5. JSSE: ai có trách nhiệm kiểm chứng?

Một số API Java thường xuất hiện trong code:

| API | Vai trò | Điều phải giữ đúng |
| --- | --- | --- |
| `KeyStore` | Lưu identity key/cert hoặc trusted CA certificate | File/type/password/quyền truy cập đúng |
| `KeyManagerFactory` | Lấy private key và certificate chain để **trình danh tính của chính ứng dụng** | Không dùng key manager thay peer trust checking |
| `TrustManagerFactory` | Tạo trust manager chuẩn từ truststore | Chỉ import CA/peer cert được xác minh, không trust-all |
| `X509TrustManager` | Interface kiểm chain server/client theo cơ chế provider | Không thay bằng implementation chấp nhận mọi certificate |
| `X509ExtendedTrustManager` | Có phiên bản xử lý certificate với ngữ cảnh `Socket`/`SSLEngine` | Không bỏ qua endpoint constraints từ JSSE |
| `SSLContext` | Tập hợp key managers, trust managers, randomness/policy phiên TLS | Không thay default toàn JVM hoặc dùng manager insecure bừa |
| `SSLParameters` | Cấu hình protocol, cipher, endpoint identification, SNI... | Với raw HTTPS TLS cần `setEndpointIdentificationAlgorithm("HTTPS")` |
| `SSLSocket` / `SSLEngine` | API TLS tương đối thấp tầng | Cần biết logical peer name và chủ động bật endpoint check phù hợp |
| `HttpsURLConnection` | HTTPS client API | Giữ hostname verifier và trust chính thống |
| `java.net.http.HttpClient` | HTTP client JDK hiện đại | Giữ mặc định xác minh HTTPS, chỉ tùy chỉnh trust đúng phạm vi |

**Điều quan trọng:** Có thể endpoint check được triển khai trong call stack trust manager khi handshake có thông tin hostname, nhưng **về mặt an ninh vẫn là hai điều kiện khác nhau**. Nếu chỉ gọi `CertPathValidator("PKIX")`, bạn phải biết rằng API đó không tự nhận hostname URL để kiểm.

### 5.1. HTTPS clients cấp cao và raw TLS khác nhau

- `HttpsURLConnection` có xử lý HTTPS hostname verification mặc định; cài một verifier luôn trả true là xóa lớp bảo vệ này.
- `HttpClient` JDK 11+ cũng được thiết kế cho HTTPS endpoint verification theo cấu hình an toàn; không dùng property hoặc option thư viện để tắt vì gặp chứng thư dev.
- **Raw `SSLSocket`** không nhất thiết biết bạn đang dùng nó cho giao thức nào. Dùng trust manager chuẩn **chưa đủ** nếu bạn không cấu hình HTTPS endpoint identity.
- **`SSLEngine`** tương tự; phải đảm bảo peer host/port và `SSLParameters` mang policy cần thiết trước khi handshake.

Ví dụ cấu hình an toàn của raw client:

~~~java
SSLSocket tls = /* đã tạo đúng peer host/connection */;
SSLParameters p = tls.getSSLParameters();
p.setEndpointIdentificationAlgorithm("HTTPS");
tls.setSSLParameters(p);
tls.startHandshake();
~~~

Đây chỉ là **trích đoạn API**, không phải chương trình độc lập. Quan trọng là `"HTTPS"` được dùng trước `startHandshake()`, và **hostname phải là tên từ URL/config đã xác thực**, không được lấy từ certificate server gửi tới.

### 5.2. Không dùng `SSLContext.setDefault(...)` tùy tiện

`SSLContext.setDefault(...)` thay context mặc định có ảnh hưởng ngoài phạm vi một HTTP request/client. Một thay đổi không an toàn ở môi trường test có thể làm toàn bộ process tin certificates sai.

Ưu tiên xây **`SSLContext` riêng cho client cần CA nội bộ** và truyền vào builder/client cụ thể. Cấu hình truststore riêng làm **các CA được tin khác với tập mặc định**, không nhất thiết tự cộng thêm root mặc định. Nếu ứng dụng cần cả hai tập, phải thiết kế rõ chính sách bổ sung trust anchors và kiểm interop; không nối các store bằng cách tự viết trust-all.

## 6. Cấu hình truststore riêng đúng cách

Để kết nối một service có certificate do **CA nội bộ đã được xác minh** cấp, hãy:

1. Lấy **public root CA certificate** qua kênh quản trị đáng tin. Đối chiếu fingerprint và đối tượng có quyền quản lý CA.
2. Tạo một truststore dành cho môi trường/dịch vụ, chẳng hạn PKCS12, chứa **đúng trust anchor được phép**.
3. Trong Java, dùng `KeyStore.load` và `TrustManagerFactory.init(trustStore)` để tạo trust managers **chuẩn**.
4. Dùng `SSLContext.init(null, tmf.getTrustManagers(), new SecureRandom())` để lấy TLS context cho **client cụ thể**.
5. Với raw HTTPS TLS, bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`. Với HTTPS client cấp cao, giữ hostname verification mặc định và không override bằng verifier vô điều kiện.
6. Test cả endpoint **đúng** và endpoint **sai**. “Kết nối thành công” là test chưa đủ.

Trích đoạn đọc truststore chuẩn:

~~~java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(trustStorePath)) {
    trust.load(in, password);
}
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext clientContext = SSLContext.getInstance("TLS");
clientContext.init(null, tmf.getTrustManagers(), new SecureRandom());
~~~

Đây là **mảnh ghép minh họa**, chưa phải chương trình độc lập: `trustStorePath`/`password` cần được khai báo, exception cần được xử lý. Đoạn hoàn chỉnh và đã kiểm chứng ở phần 8.

**Không hard-code password production**. Password bảo vệ file truststore, còn **việc chọn root certificate để tin mới là quyết định an ninh cốt lõi**: không chỉ bảo vệ password mà nhập một CA attacker vào store thì vẫn mất tính xác thực.

### 6.1. Identity keystore không phải truststore

~~~text
Server:
    identity keystore
       PrivateKeyEntry: private key + server cert chain

Client:
    truststore
       TrustedCertificateEntry: approved root CA certificate
       (và trust policy ứng dụng)

Client checks: chain to approved trust anchor + URL hostname to leaf SAN
~~~

`KeyManagerFactory` giúp server chứng minh quyền sở hữu private key, trong khi `TrustManagerFactory` giúp client xác minh certificate của peer. Chuyển server private key vào client truststore để “hết lỗi certificate” là sai và có thể làm lộ secret. Với mTLS, mỗi bên có identity riêng và trust policy riêng.

### 6.2. CA nội bộ và truststore mặc định

JDK thường cung cấp tập CA mặc định như `cacerts` (vị trí, nội dung, chính sách có thể khác theo JDK/distribution). Một `SSLContext` khởi tạo với truststore riêng **không mặc nhiên hợp nhất** CA nội bộ với mọi root của JDK. Đừng giả định một API sẽ fallback sang default roots sau khi đã nhận custom trust managers.

Ứng dụng cần thêm CA nội bộ nên xác định rõ phạm vi:

- **Client chỉ dùng trong một security domain:** truststore riêng hạn chế được CA tin, thường là lựa chọn đơn giản.
- **Client cần CA công khai và nội bộ:** dùng cấu hình trust policy đã được thiết kế/kiểm kỹ theo platform hoặc thư viện; ghi rõ nguồn roots, không viết bộ trust manager thử lần lượt các CA tùy tiện không có kiểm soát.
- **Nhiều microservices:** mỗi môi trường/tenant có chính sách cấp certificate và rotation, không trust toàn bộ CA dev ở production.

## 7. Thực hành: tạo CA và chứng thư local nhưng vẫn giữ xác minh

Bài lab được thực hiện hoàn toàn ở **localhost/loopback** trong một **thư mục thử nghiệm mới**, dùng JDK 17+ và `keytool`. Ta tạo:

- `root.p12`: CA root demo đáng tin cho nhánh positive.
- `other-root.p12`: **CA khác** không liên quan, dùng làm trust anchor **sai** để chứng minh JSSE từ chối.
- `server.p12`: server private key và leaf được **root.p12** ký, SAN chỉ có `DNS:localhost`.
- `trusted.p12`: truststore client chứa **root thực sự cấp leaf**.
- `untrusted.p12`: truststore client chỉ chứa **other-root**, nên chain server không được tin.

**Không dùng các certificate/keystore demo trong production**; private key CA và server trong bài thực hành được bảo vệ bởi password cố định mẫu, dễ đoán; validity ngắn và không có hạ tầng CRL/OCSP thật. Hãy chạy từng lệnh trong **thư mục trống tạm**, không đụng các file keystore đang dùng.

### 7.1. Tạo root CA demo được phép tin trong bài lab

~~~bash
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 2048 -dname "CN=Trusted Demo Root,O=Training,C=VN" -validity 7 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore root.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

Root CA certificate được ký bằng chính private key CA. Self-signed **không có nghĩa tự động được tin**; trong bài, **client chủ động chọn root này** bằng cách import vào `trusted.p12`.

### 7.2. Xuất certificate root public

~~~bash
keytool -exportcert -alias lab-root -keystore root.p12 -storepass demo-pass-123 -rfc -file root.crt
~~~

`root.crt` chỉ chứa **certificate công khai**, không chứa private key CA. Trong hệ thống thực, phải xác minh **fingerprint và nguồn phân phối certificate** qua kênh độc lập trước khi import.

### 7.3. Tạo một CA khác để kiểm negative trust test

~~~bash
keytool -genkeypair -alias other-root -keyalg RSA -keysize 2048 -dname "CN=Unrelated Demo Root,O=Training,C=VN" -validity 7 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore other-root.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

~~~bash
keytool -exportcert -alias other-root -keystore other-root.p12 -storepass demo-pass-123 -rfc -file other-root.crt
~~~

Việc root thứ hai tự ký và cũng có `CA=true` **không cho nó quyền tin cậy certificate server** vốn được cấp bởi root thứ nhất. Truststore `untrusted.p12` chỉ chứa root khác này sẽ là negative test có thể tái hiện.

### 7.4. Tạo server identity với SAN DNS localhost

~~~bash
keytool -genkeypair -alias server-id -keyalg RSA -keysize 2048 -dname "CN=localhost,O=Training,C=VN" -validity 7 -ext "san=dns:localhost" -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

Lúc mới tạo, `server.p12` có một `PrivateKeyEntry` và certificate self-signed tạm thời. Đó chưa phải leaf do CA demo ký. Alias `server-id` được giữ nguyên ở các bước sau.

### 7.5. Tạo CSR PKCS#10 và CA đáng tin ký certificate

~~~bash
keytool -certreq -alias server-id -file server.csr -rfc -keystore server.p12 -storepass demo-pass-123 -ext "san=dns:localhost"
~~~

~~~bash
keytool -gencert -alias lab-root -infile server.csr -outfile issued.crt -rfc -keystore root.p12 -storepass demo-pass-123 -validity 7 -ext "san=dns:localhost" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

CA demo ký leaf có `SAN DNS:localhost` và `EKU serverAuth`. Một CA thật phải kiểm quyền đối với identity, chứng thư và policy cấp trước khi ký, không tự tin mọi yêu cầu SAN trong CSR.

### 7.6. Cài root và certificate reply vào đúng server alias

~~~bash
keytool -importcert -alias lab-root -file root.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

~~~bash
keytool -importcert -alias server-id -file issued.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

Bước sau cài **certificate reply vào chính PrivateKeyEntry alias `server-id`** để public key của leaf khớp private key đang được giữ. Không import leaf vào alias mới rồi tưởng server identity đã được thay đúng.

### 7.7. Tạo hai client truststores có chính sách rõ ràng

~~~bash
keytool -importcert -alias lab-root -file root.crt -keystore trusted.p12 -storetype PKCS12 -storepass demo-pass-123 -noprompt
~~~

~~~bash
keytool -importcert -alias other-root -file other-root.crt -keystore untrusted.p12 -storetype PKCS12 -storepass demo-pass-123 -noprompt
~~~

- `trusted.p12` chỉ tin root đã ký leaf → kết nối tới `localhost` có khả năng pass.
- `untrusted.p12` chỉ tin root khác → server certificate không có path tới root đó → **JSSE phải reject**.
- `server.p12` có private key server và certificate chain; **không có private key của hai root**.

**Cảnh báo:** `-storepass` trên dòng lệnh có thể lộ qua process listing/history; chỉ dùng ở môi trường demo cô lập. `-noprompt` bỏ xác nhận của `keytool`; đừng dùng để tự động import CA từ nguồn chưa được xác minh trong production.

### 7.8. Xem lại certificates/aliases

~~~bash
keytool -list -v -alias server-id -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123
keytool -list -v -alias lab-root -keystore trusted.p12 -storetype PKCS12 -storepass demo-pass-123
keytool -list -v -alias other-root -keystore untrusted.p12 -storetype PKCS12 -storepass demo-pass-123
~~~

Điều cần kiểm: leaf thực tế có `DNSName: localhost`, chain về `lab-root`, còn `untrusted.p12` chứa **root khác**. Root trong `trusted.p12` là `TrustedCertificateEntry` chứ không phải private key CA.

## 8. Java 17+ hoàn chỉnh: đúng CA/tên thì pass, sai CA/tên thì fail

Đây là chương trình **runnable**, có thể biên dịch/chạy trên JDK 17+ trong cùng thư mục với các file `server.p12`, `trusted.p12`, `untrusted.p12` ở phần 7.

Chương trình không có một dòng code trust-all hoặc hostname-verifier vô hiệu hóa nào:

1. Tạo server TLS cục bộ bằng `KeyManagerFactory` từ `PrivateKeyEntry` trong `server.p12`.
2. Tạo hai clients bằng **`TrustManagerFactory` chuẩn**: một có root đúng và một chỉ có root không liên quan.
3. Mở TCP loopback bằng `InetAddress.getLoopbackAddress()` nhưng gán **logical peerName** cho `SSLSocket`.
4. Luôn bật **`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`** trước handshake.
5. Chứng minh ba kết quả mong muốn: **trusted + localhost** thành công; **unrelated CA + localhost** bị từ chối; **trusted + 127.0.0.1** bị từ chối vì thiếu IP SAN.

### 8.1. Source `SafeJsseDemo.java`

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class SafeJsseDemo {
    static KeyStore load(String file, char[] password) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            ks.load(in, password);
        }
        return ks;
    }

    static SSLContext serverContext(KeyStore identity, char[] password)
            throws Exception {
        KeyManagerFactory km = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        km.init(identity, password);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(km.getKeyManagers(), null, new SecureRandom());
        return context;
    }

    static SSLContext clientContext(KeyStore trust) throws Exception {
        TrustManagerFactory tm = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tm.init(trust);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tm.getTrustManagers(), new SecureRandom());
        return context;
    }

    static void handshake(SSLContext context, int port, String peerName)
            throws Exception {
        // TCP luôn nối loopback. peerName là identity logic tin cậy
        // mà TLS cần đối chiếu với Subject Alternative Name của leaf.
        Socket tcp = new Socket(InetAddress.getLoopbackAddress(), port);
        try (SSLSocket tls = (SSLSocket) context.getSocketFactory()
                .createSocket(tcp, peerName, port, true)) {
            SSLParameters params = tls.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(params);
            tls.startHandshake();
        }
    }

    static boolean rejected(SSLContext context, int port, String name)
            throws Exception {
        try {
            handshake(context, port, name);
            return false; // LỖI: kết nối xấu không bị từ chối.
        } catch (SSLHandshakeException expected) {
            return true; // PASS: JSSE từ chối ngay ở handshake.
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-pass-123".toCharArray();
        try {
            SSLContext server = serverContext(
                    load("server.p12", password), password);
            SSLContext trusted = clientContext(
                    load("trusted.p12", password));
            SSLContext untrusted = clientContext(
                    load("untrusted.p12", password));

            try (SSLServerSocket listener = (SSLServerSocket)
                    server.getServerSocketFactory().createServerSocket(
                            0, 10, InetAddress.getLoopbackAddress())) {

                Thread responder = new Thread(() -> {
                    for (int i = 0; i < 3; i++) {
                        try (SSLSocket accepted =
                                (SSLSocket) listener.accept()) {
                            accepted.startHandshake();
                        } catch (Exception ignored) {
                            // Chỉ trong demo: negative tests có thể làm
                            // client hủy handshake; server tiếp tục test.
                        }
                    }
                });
                responder.start();
                int port = listener.getLocalPort();

                handshake(trusted, port, "localhost");
                System.out.println("Trusted + localhost = accepted");

                System.out.println("Wrong CA rejected   = " +
                        rejected(untrusted, port, "localhost"));

                System.out.println("Wrong name rejected = " +
                        rejected(trusted, port, "127.0.0.1"));

                responder.join(10000);
                if (responder.isAlive()) {
                    throw new IllegalStateException("Server not finished");
                }
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SafeJsseDemo.java
java SafeJsseDemo
~~~

**Stdout đã được kiểm chứng bằng JDK, `keytool`, `javac` và `java` trong thư mục tạm** sau khi thực hiện các lệnh phần 7:

~~~text
Trusted + localhost = accepted
Wrong CA rejected   = true
Wrong name rejected = true
~~~

Dù key pair và các chữ ký được tạo ngẫu nhiên ở mỗi lần chạy, ba kết quả này ổn định theo bộ certificate/KeyStore và chính sách demo. Một môi trường Java hoặc JCE provider có policy thuật toán đặc biệt có thể từ chối cả positive case; khi đó cần kiểm lỗi thực tế, **không hạ cấp xác minh để “làm output giống”**.

### 8.2. Phân tích đúng các dòng stdout

**`Trusted + localhost = accepted`**:

- Server xuất trình certificate leaf do root `lab-root` ký.
- Client sử dụng `trusted.p12` chứa chính root đó, với trust manager chuẩn.
- `peerName="localhost"` khớp `dNSName SAN localhost` trên leaf.
- `SSLSocket.startHandshake()` thành công. Ở đây chưa làm HTTP request hay phân quyền ứng dụng; chỉ kiểm lớp TLS.

**`Wrong CA rejected = true`**:

- Tên đích vẫn `localhost`, vẫn đúng SAN.
- Client lại dùng `untrusted.p12` chỉ chứa root **không liên quan** đến issuer leaf.
- Không có path hợp lệ tới trust anchor client chấp nhận; JSSE ném `SSLHandshakeException`.
- Chương trình coi việc **từ chối** là kết quả test **thành công**. Không thử lại với trust-all.

**`Wrong name rejected = true`**:

- Client vẫn dùng `trusted.p12` nên chain được trust.
- Logical peer identity đổi thành IP literal `127.0.0.1`.
- Leaf chỉ có `DNS:localhost`, không có `iPAddress SAN:127.0.0.1`.
- `HTTPS` endpoint identification khiến JSSE từ chối ngay cả khi CA chain hợp lệ. Đây là lớp phòng vệ riêng, **không thể bỏ**.

### 8.3. Vì sao ví dụ không in chi tiết exception?

Để test đơn giản và độc lập với message text của từng provider, `rejected` chỉ bắt `SSLHandshakeException` và trả boolean. Message/exception chain cụ thể có thể khác giữa JDK, CA profile và thuật toán; **không nên assert nguyên văn exception string**.

Trong production, hãy giữ nguyên stack/cause có lọc thông tin nhạy cảm và ghi nhật ký quản trị phù hợp. Đừng bắt mọi exception rồi “return success”; test fail nếu xuất hiện lỗi ngoài dự kiến. Thread server trong demo cố tình bỏ qua lỗi handshake ở **negative test** và không in dữ liệu nhạy cảm; **không dùng kỹ thuật nuốt exception như vậy trong server production**.

### 8.4. Vì sao không viết code trust-all để so sánh?

Để chứng minh hệ thống đúng, **không cần tạo một cài đặt không an toàn** rồi cho thấy nó chấp nhận CA giả. Thay vào đó, negative tests yêu cầu Java **phải từ chối** root khác và hostname sai; test sẽ báo thất bại nếu ai đó vô tình thay trust manager hoặc tắt HTTPS endpoint identification.

Đây là kiểu kiểm thử mạnh hơn một “demo chạy được với mọi server”, vì nó kiểm **hành vi từ chối quan trọng đối với an ninh**.

## 9. Với `HttpClient` hoặc `HttpsURLConnection` nên làm gì?

### 9.1. `java.net.http.HttpClient`

Đối với JDK 11+ (bao gồm JDK 17), khi cần dùng CA nội bộ, bạn có thể tạo `SSLContext` chứa trust manager chuẩn như phần 6 rồi đưa vào **`HttpClient.Builder`**:

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(clientContext)
        .build();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/status"))
        .GET()
        .build();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

**Đây là mảnh ghép API**, không phải chương trình độc lập: `clientContext` phải được khởi tạo an toàn, các import/exception/URL thật phải được xác định. Mặc định HTTPS endpoint identification phải được giữ nguyên, không bật các switch vô hiệu hóa hostname verification.

**Sửa đúng:** nếu API ở `https://api.example.test` dùng CA nội bộ, đặt CA đã được kiểm trong truststore; certificate leaf phải có SAN cho `api.example.test`. Nếu gọi bằng `https://10.0.0.20`, hãy có IP SAN phù hợp hoặc sửa URL/tên logic theo chính sách. Không dùng request “insecure mode” vì đang ở staging.

### 9.2. `HttpsURLConnection`

`HttpsURLConnection` dùng hostname verification mặc định cho HTTPS. Có thể cung cấp một `SSLSocketFactory` được tạo từ `SSLContext` tin đúng CA:

~~~java
HttpsURLConnection connection = (HttpsURLConnection)
        new URL("https://api.example.test/status").openConnection();
connection.setSSLSocketFactory(clientContext.getSocketFactory());
// Giữ HostnameVerifier mặc định, KHÔNG override thành always-true.
int status = connection.getResponseCode();
~~~

Đây là **trích đoạn**, cần có import, `clientContext` an toàn, kiểm IO và lifecycle connection trong chương trình thực. Cách làm đúng là **thay nguồn trust anchors có kiểm soát**, không bỏ qua hostname verification.

### 9.3. OkHttp, Apache HttpClient, Netty, Spring và thư viện khác

Các thư viện có tên flag/API khác nhau theo version. Quy tắc bất biến:

- Trust manager thực sự kiểm chain với nguồn CA được chọn, không có `acceptAll`/trust-all.
- Hostname verifier mặc định hoặc policy xác thực tương đương vẫn hoạt động.
- Không tự tạo SSLContext “một lần cho toàn hệ thống” rồi thay tất cả clients bằng trust manager không an toàn.
- Bất kỳ option `NoopHostnameVerifier`, `TrustAllStrategy`, `InsecureTrustManagerFactory` hoặc khái niệm tương tự đều phải bị **báo động trong code review**, đặc biệt với ứng dụng có dữ liệu thật.
- Test trên đúng **version của client library và JDK** sẽ deploy; cấu hình chắc chắn an toàn trong một API không bảo đảm được copy y nguyên sang API khác.

## 10. Gỡ lỗi TLS mà không hạ cấp bảo mật

Một exception có thể phát sinh từ nhiều tầng. Hãy điều tra đúng nguyên nhân, không áp “fix chung” là bỏ trust/hostname.

| Triệu chứng | Nhóm nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| `PKIX path building failed` | Client không dựng được path tới trust anchor | Xác minh CA/truststore, intermediate chain, đúng runtime đang dùng |
| `unable to find valid certification path` | Không có trust anchor/path được policy chấp nhận | Chọn đúng root đã thẩm định, không import certificate tùy tiện |
| `No subject alternative DNS name matching ...` | Leaf SAN không chứa DNS host cần kiểm | CA cấp lại SAN đúng, hoặc dùng endpoint URL đúng identity |
| `No subject alternative names matching IP address ...` | URL dùng IP nhưng leaf không có IP SAN | Dùng IP SAN đúng loại hoặc URL DNS được chứng thực |
| `certificate expired` / `not yet valid` | Thời gian leaf/issuer hoặc đồng hồ sai | Renew certificate, kiểm thời gian, không disable validity |
| `Extended key usage does not permit use for TLS server authentication` | Leaf không có mục đích `serverAuth` phù hợp | Xin cấp certificate đúng EKU |
| `Algorithm constraints check failed` | Key/signature không đạt policy | Nâng key/CA profile/cipher suite phù hợp |
| `Certificate revoked` | Certificate bị thu hồi theo policy | Kiểm sự cố key/CA, rotate và xử lý đúng, không bỏ revocation |
| Lỗi sau khi chuyển Docker/JDK | Store/type/CA bundle/provider khác | Kiểm chính xác truststore file, quyền, JDK distribution và cấu hình tiến trình |
| “Works after allow-all-hosts” | Name check đã bị vô hiệu hóa | **Rollback bypass** và cấp certificate SAN đúng |
| “Works after trust-all manager” | Chain trust đã bị vô hiệu hóa | **Rollback bypass** và cấu hình CA đáng tin |
| Lỗi ngẫu nhiên sau redirect/proxy | Endpoint host thực tế khác hoặc proxy TLS | Kiểm URL từng hop, trust anchors và certificate SAN tại điểm TLS termination |

### 10.1. Quy trình điều tra có cấu trúc

~~~text
1. Xác định URL/hostname hoặc IP thật sự do client chủ định gọi.
2. Xác định HTTPS client API, SSLContext và truststore đang dùng.
3. Kiểm leaf SAN, issuer, thời hạn, KU/EKU và chain/intermediates.
4. Kiểm CA root từ nguồn tin cậy; đối chiếu truststore của runtime.
5. Test chain trust độc lập; test hostname matching độc lập.
6. Sửa certificate/URL/truststore đúng nguyên nhân.
7. Rerun positive + negative tests.
8. Không retry bằng trust-all hoặc skip-hostname.
~~~

Dùng `keytool -list -v` hoặc công cụ đã được tổ chức cho phép để xem cấu trúc truststore. Khi dùng `openssl s_client`, nhớ rằng **chỉ in certificate/`Verify return code` chưa chắc đã chạy hostname verification**; phải cung cấp options/trust phù hợp nếu muốn kiểm identity. Không lấy một kết quả path-valid rồi suy ra toàn bộ HTTPS client đã an toàn.

### 10.2. JSSE debug logs có thể chứa dữ liệu nhạy cảm

JDK có một số chế độ debug TLS, ví dụ:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager YourApplication
~~~

Đây là **lệnh khái niệm**, không phải lệnh chạy sample `SafeJsseDemo` vì class name chỉ đại diện ứng dụng cụ thể. Dùng trong môi trường kiểm soát, xem lại nội dung log trước khi chia sẻ: trace TLS có thể lộ metadata hệ thống, hostname, certificate details và thông tin không phù hợp đưa ra công khai. **Không bật verbose debug vô hạn trong production**, không đưa password, private keys, token hoặc toàn bộ body xác thực vào logs.

**Không sửa debug bằng cách tắt kiểm chứng để “tiếp tục quan sát request”**. Khi cần tái hiện service lỗi, tạo CA/test certificate đúng yêu cầu, hoặc kiểm endpoints trong môi trường lab cô lập như phần 7–8.

## 11. Không trust CA lạ chỉ vì import thành công

Một sai lầm gần trust-all là **import mọi CA/certificate mà server gửi** vào truststore của client. Dù không cài trust-all manager, cách này biến tập trust anchors thành một danh sách không có quy trình xác minh.

**Ví dụ rủi ro:**

~~~text
Client báo: issuer chưa được tin
Operator tải root.crt từ chính đường kết nối chưa xác thực
Operator import root.crt với -noprompt
Client kết nối thành công
=> Không có bằng chứng root này thuộc CA dự kiến.
~~~

Attacker có thể cung cấp một root giả và leaf do chính họ ký. **Chữ ký có thể kiểm đúng đối với root giả mới import**, nhưng quyết định tin root ban đầu đã sai.

Cách làm đúng:

1. Xác minh fingerprint/public key CA qua kênh quản trị độc lập.
2. Kiểm chủ sở hữu CA, phạm vi cấp certificate, constraints, expiration và chính sách quản lý CA.
3. Import **đúng certificate được phê duyệt** vào truststore của môi trường cụ thể.
4. Kiểm permission file, backup, review và rotation; không dùng global truststore nếu chỉ một client cần CA đó.
5. Giữ hostname verification và kiểm end-to-end.
6. Audit các thay đổi trust anchors, không tự động cập nhật truststore theo certificate peer gửi trên mạng.

**Certificate pinning đúng** (nếu cần) cũng dựa trên giá trị được phân phối **từ nguồn tin cậy**, không phải fingerprint lấy tự động từ một kết nối chưa được xác thực và được coi là an toàn vĩnh viễn.

## 12. Mô hình an toàn cho dev/staging/production

### 12.1. Dev localhost

Nếu test endpoint `https://localhost`, tạo certificate dev có SAN `DNS:localhost`, tin CA dev **chỉ trong dev truststore**. Nếu test bằng `https://127.0.0.1`, phải cấp SAN loại `IP:127.0.0.1` hoặc dùng DNS `localhost` cho đúng.

Không yêu cầu developer tắt toàn bộ HTTPS validation vì một server local chỉ có self-signed certificate. CA dev có thể tự ký, nhưng phải được **chủ động tin với phạm vi giới hạn**; khác với trust mọi certificate trên mạng.

### 12.2. Staging và môi trường kiểm thử tích hợp

Staging nên có hostname ổn định như `staging-api.example.test`, certificate SAN đúng, CA/truststore staging riêng hoặc public CA tùy thiết kế. Negative tests trong CI phải xác nhận:

- Root khác không được chấp nhận.
- Certificate SAN không khớp không được chấp nhận.
- Certificate hết hạn/không đạt policy bị từ chối.
- Sau redirect/proxy, endpoint mới vẫn được xác minh.
- Không có configuration flag bypass verification tồn tại trong artifact sẽ deploy.

### 12.3. Production và load balancer

Với ingress/LB terminate TLS, certificate tại điểm TLS termination phải phù hợp hostname URL mà client thấy. Nếu LB mở TLS riêng đến backend, kết nối LB→backend **cũng có identity/trust policy riêng**; không “kế thừa” xác thực từ client→LB nếu chưa thiết kế.

Trong microservices, service A gọi service B qua DNS nội bộ có thể cần CA công ty, identity SAN phù hợp, truststore scoped và mTLS. **mTLS không thay hostname verification của client**, và certificate client được CA công ty ký **không tự cấp quyền** gọi mọi endpoint: authorization identity-to-role phải được kiểm riêng.

### 12.4. Proxy doanh nghiệp và TLS inspection

Một proxy có thể trình certificate do **CA proxy** cấp thay certificate từ server gốc. Nếu tổ chức có chính sách TLS inspection hợp pháp, client cần quản lý CA đó theo quy trình riêng và vẫn kiểm hostname của URL đích, scope, logging và rủi ro vận hành.

Không tự import CA proxy được gửi bởi một kết nối không tin cậy. Việc thêm CA proxy mở rộng trust anchors và có thể cho phép proxy terminate nhiều kết nối; đây là **quyết định quản trị bảo mật**, không phải workaround ở dòng code.

## 13. Phòng lỗi trong code review và kiểm thử

### 13.1. Những dấu hiệu cần tìm trong pull request

| Dấu hiệu | Câu hỏi kiểm tra |
| --- | --- |
| Custom `X509TrustManager` | Có thực sự kiểm chuỗi, thuật toán và trust anchor? Vì sao không dùng provider chuẩn? |
| `checkServerTrusted` không có logic xác minh | Đây có phải trust-all đang được ẩn bằng try/catch? |
| `HostnameVerifier` luôn trả true | Có phải đang bỏ mọi endpoint identity checks? |
| `NoopHostnameVerifier` hoặc `allowAllHosts` | Có test negative mismatch để phát hiện bypass không? |
| `SSLContext.setDefault` | Có vô tình thay TLS policy toàn process không? |
| Raw `SSLSocket`/`SSLEngine` | Đã bật endpoint identification và truyền peer name đúng chưa? |
| `SSLParameters.setEndpointIdentificationAlgorithm("")` hoặc bỏ algorithm | Có làm mất name check trong context HTTPS không? |
| Cấu hình `disableHostnameVerification` | Có thể lọt vào production build/runtime không? |
| Truststore import certificate tự động khi lỗi | CA từ đâu và ai xác minh fingerprint? |
| Retry sau `SSLHandshakeException` | Có nới lỏng trust/hostname ở lần thử sau không? |
| Test HTTPS chỉ assert HTTP 200 | Có negative tests với wrong CA và wrong hostname không? |
| Wrapper SSL factory được dùng ở nhiều clients | Có áp phạm vi trust rộng hơn dự kiến không? |

**Một review tốt không chỉ grep từ khóa.** Có thể thư viện dùng tên khác hoặc configuration trong YAML/properties thay vì Java code. Cần xem **effective TLS settings**, dependency versions, container image và smoke tests.

### 13.2. Test matrix bắt buộc

| Test | Chain trust | Hostname | Kết quả mong muốn |
| --- | --- | --- | --- |
| Positive | CA đúng | SAN khớp | **Accept** |
| Wrong root | CA khác | SAN khớp | **Reject** |
| Wrong DNS | CA đúng | SAN không khớp | **Reject** |
| Wrong IP | CA đúng | Thiếu iPAddress SAN | **Reject** |
| Invalid date | CA đúng | SAN khớp | **Reject** |
| Missing intermediate | Path không dựng được | SAN khớp | **Reject** nếu không dựng được chain hợp lệ |
| Wrong EKU | Chain/usage policy không đạt | SAN khớp | **Reject** |
| Tampered certificate | Chữ ký không hợp lệ | SAN khớp | **Reject** |
| Revoked certificate | Revocation policy từ chối | SAN khớp | **Reject** |
| Wrong client identity (mTLS) | Client cert có thể hợp lệ | Không được authorization | **Deny** ở tầng tương ứng |

Hai negative tests **Wrong root** và **Wrong DNS** có giá trị nhất cho chủ đề này vì chúng trực tiếp phát hiện việc một developer đã vô tình bật trust-all hoặc bỏ name check.

### 13.3. Không làm test “đúng” bằng cách chấp nhận lỗi

Việc test máy phát triển không có CA đúng là **test setup chưa hoàn chỉnh**, không phải lý do sửa verifier:

- Không tắt certificate verification để có HTTP status.
- Không bắt `SSLHandshakeException` rồi giả lập thành công.
- Không dùng global insecure client trong test fixtures nếu cùng fixture được tái sử dụng trong production.
- Không tự import certificate root do server trả về mà không kiểm nguồn.
- Khi test cần self-signed CA, hãy **tạo và pin trust anchor trong test fixture riêng**, cấp leaf có SAN hợp lệ và giữ verification.

**Đúng là phải có ít nhất một test thất bại theo dự kiến.** Nếu kết nối với CA không tin cậy hoặc hostname sai vẫn thành công, hệ thống **có lỗ hổng xác thực**, không phải “test linh hoạt”.

## 14. Những lỗi dễ nhầm giữa certificate trust và hostname

### 14.1. `PKIX path building failed`

Đây thường là lỗi xác minh đường dẫn, không phải lỗi hostname. Hướng xử lý: kiểm certificate chain server gửi, intermediate, root mà client thực sự trust, policy JDK, thời hạn và thuật toán. Import một CA đúng có thể sửa trust issue; **không nên động đến hostname verifier**.

### 14.2. `No subject alternative DNS name matching ...`

Trust chain có thể đã hợp lệ nhưng SAN không chứa reference hostname. Cách sửa: certificate phải có đúng DNS SAN (CA cấp lại), hoặc ứng dụng dùng hostname thực sự được cấp theo thiết kế. **Không đổi trust manager để xử lý mismatch** và không tắt hostname verification.

### 14.3. Dùng IP thay vì DNS khi test

Server certificate được cấp cho `DNS:api.example.test` nhưng developer test bằng `https://10.10.0.20`. Đây là reference identity khác. Dùng endpoint DNS phù hợp và route DNS đến IP, hoặc xin cấp IP SAN nếu policy cho phép định danh qua IP.

### 14.4. Root import sai Java runtime

Máy dùng nhiều JDK/containers. Bạn import CA vào `cacerts` của JDK A nhưng ứng dụng chạy JDK B, hoặc ứng dụng có custom truststore riêng. Kiểm **đường dẫn thực tế, type, user permissions và effective config**. Không tạo trust-all vì không tìm đúng truststore.

### 14.5. Một server trả nhiều certificate theo SNI

Nếu SNI không phù hợp hoặc reverse proxy chọn default certificate, chain có thể hợp lệ nhưng SAN thuộc hostname khác. Sửa SNI routing/server certificate configuration, đảm bảo client gửi đúng hostname, **vẫn cần name check**. Đừng coi vì CA ký nên có thể bỏ SAN.

### 14.6. Chỉ một thư viện HTTP thất bại

`HttpClient`, `HttpsURLConnection`, OkHttp, Netty hoặc Apache HttpClient có thể dùng SSLContext/truststore/hostname policies khác nhau. Điều tra **client cụ thể và version cụ thể**, không áp flag JVM global “insecure SSL” hoặc tắt kiểm tên ở mọi client.

### 14.7. Certificate hết hạn hoặc thu hồi

Chứng thư có SAN đúng và CA được tin có thể hết hạn hoặc bị thu hồi. Không dùng trust-all hoặc set clock giả để bypass. Renew/rotate key/cert, xử lý incident với CA, kiểm đồng bộ thời gian và revocation policy.

## 15. Mật khẩu/khóa, logging và quản trị an toàn

Mật khẩu PKCS12 bảo vệ file theo provider, **không thay CA validation và hostname verification**. Certificate leaf/root có thể công khai, nhưng private keys, trust policy và các bản sao credential cần được bảo vệ.

- **Không commit** file `.p12` chứa private key, key pass, secret manager token, `javax.net.ssl.keyStorePassword` hay truststore passwords vào repo.
- Quản lý keystore/truststore bằng secret manager, deployment policy, volume permission hoặc HSM/KMS theo yêu cầu.
- Root/CA certificates từ nguồn chính thức cần được xem như **danh sách security policy**, có review/audit/rotation; đừng import không kiểm soát.
- Hạn chế thay đổi `SSLContext` mặc định toàn JVM; ưu tiên cấu hình per-client.
- Trong lỗi TLS, log mức phù hợp: hostname đích, loại lỗi, certificate issuer/SAN/expiry đã được lọc theo chính sách; **không log private key, password, session key, bearer token** hoặc full request chứa credential.
- Đừng vô hiệu hóa revocation theo thói quen: cơ chế CRL/OCSP và chính sách hard/soft-fail phụ thuộc ứng dụng; phải được quyết định rõ.
- Với server/client mTLS, theo dõi certificate expiry, rotation, cert usage và mapping identity-to-permissions; cả hai chiều vẫn có chính sách trust riêng.

Đoạn code demo xóa `char[] password` do ứng dụng nắm giữ sau khi sử dụng. Điều này giảm thời gian tồn tại của bản sao do ứng dụng kiểm soát nhưng không chứng minh JVM/provider đã xóa mọi bản copy; password **literal** trong ví dụ là cố ý đơn giản hóa, **không dùng trong sản phẩm**.

## 16. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Ứng dụng HTTPS kết nối thành công sau khi thay trust manager bằng implementation chấp nhận mọi certificate. Điều gì đã mất?

**Đáp án:** Mất **xác thực đường dẫn/chủ thể phát hành certificate**. Attacker có thể dùng self-signed certificate hoặc certificate do họ kiểm soát để làm peer, trong khi phiên vẫn có encryption.

**Câu 2.** Java client đã trust CA công ty nhưng gọi `payments.internal` và peer trình certificate `DNS:reports.internal`. Có được chấp nhận không?

**Đáp án:** **Không.** Chain hợp lệ không thay hostname match. Client cần cert đúng SAN `payments.internal` hoặc sửa endpoint hợp lệ, không tắt name check.

**Câu 3.** Một certificate có SAN `DNS:localhost` và client dùng URL `https://127.0.0.1`. Thiếu điều gì?

**Đáp án:** Thiếu SAN loại **`iPAddress` cho `127.0.0.1`**. Có DNS SAN localhost không làm URL dùng IP trở thành cùng reference identity.

**Câu 4.** Có nên cài `HostnameVerifier` luôn trả true vì TLS vẫn kiểm CA không?

**Đáp án:** Không. Một certificate hợp lệ của hostname khác có thể bị chấp nhận cho endpoint mục tiêu; đó là lỗi endpoint authentication riêng với path trust.

**Câu 5.** Raw `SSLSocket` dùng `TrustManagerFactory` chuẩn. Điều này tự bảo đảm HTTPS hostname đã được kiểm?

**Đáp án:** **Không chắc.** Raw TLS không biết mặc định giao thức ứng dụng; cần peer name đúng và cấu hình `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` trước handshake khi áp dụng HTTPS identity.

**Câu 6.** Vì sao test chỉ khẳng định HTTP 200 từ HTTPS server chưa đủ cho security QA?

**Đáp án:** Một client trust-all hoặc bỏ hostname vẫn có thể nhận HTTP 200. Phải có **negative tests** với CA không được tin và hostname không khớp, xác minh client từ chối.

**Câu 7.** Có thể import root certificate lấy từ cùng kết nối đang bị lỗi TLS để “sửa PKIX” không?

**Đáp án:** Không tự ý. Root có thể là của attacker; trust anchor phải được chọn và xác minh fingerprint/nguồn thông qua kênh đáng tin, rồi mới import.

**Câu 8.** SNI đã là `api.example.test` nhưng leaf server trả về `DNS:other.example.test`. Có đủ an toàn không?

**Đáp án:** Không. SNI chỉ là thông tin giúp server chọn chứng thư; client vẫn phải kiểm leaf SAN khớp reference hostname.

**Câu 9.** Test CA khác thất bại với `SSLHandshakeException`. Đó là bug của chương trình `SafeJsseDemo`?

**Đáp án:** Không. Đây là **expected failure** và được biểu diễn bằng `Wrong CA rejected = true`. Từ chối trust anchor sai là hành vi đúng.

**Câu 10.** Trong demo, CA đúng + `localhost` pass, CA đúng + `127.0.0.1` fail. Vì sao?

**Đáp án:** Do **danh tính endpoint khác nhau**. Leaf chỉ có SAN DNS localhost. Phép kiểm CA vẫn pass ở cả hai, nhưng IP literal không có SAN iPAddress tương ứng nên handshake bị từ chối.

**Câu 11.** Nếu `PKIX path building failed` sau khi chuyển sang container, có nên bật skip-verify?

**Đáp án:** Không. Cần xác minh truststore thực sự được JDK/container dùng, CA/intermediate, file permissions và algorithm policy; fix CA chain/config đúng nguyên nhân.

**Câu 12.** Một client cần CA công khai và một CA nội bộ. Dùng custom truststore có tự động giữ các root mặc định của JDK không?

**Đáp án:** Không mặc định. `TrustManagerFactory.init(customStore)` dùng nội dung store được cấp theo provider/policy; cần thiết kế rõ cách quản lý tập CA cần tin. Không fallback thành trust-all.

**Câu 13.** mTLS server tin CA của client, vậy mọi client certificate do CA đó ký được quyền gọi tất cả API?

**Đáp án:** Không. Trust certificate chain xác thực nguồn identity theo policy; ứng dụng vẫn phải **authorization** identity-to-role/tenant, kiểm mục đích certificate như `clientAuth` khi phù hợp.

**Câu 14.** Có thể sửa lỗi CA và hostname bằng cách giảm TLS version/cipher suite để bắt tay thành công không?

**Đáp án:** Không. Version/cipher suite là tầng khác; giảm chất lượng thuật toán không thay chain trust hoặc SAN. Sửa certificate/truststore/endpoint đúng chính sách.

**Câu 15.** Nếu team muốn đưa ví dụ TLS vào tài liệu public, nên minh họa như thế nào để người học không copy giải pháp nguy hiểm?

**Đáp án:** Dùng **CA test được tin có chủ đích, hostname SAN đúng, trust manager chuẩn, endpoint identification bật**, và thêm negative tests. Mô tả trust-all/skip-hostname như anti-pattern, không cung cấp helper insecure dễ copy sang production.

## 17. Checklist trước khi merge/deploy mã JSSE

- [ ] **Không** có trust manager bỏ qua kiểm chứng, trust-all SSLContext, certificate verifier “always accept”.
- [ ] **Không** có `HostnameVerifier` luôn trả true, `NoopHostnameVerifier` hoặc tắt endpoint identification khi dùng HTTPS.
- [ ] Không có retry insecure sau `SSLHandshakeException`; lỗi TLS phải fail closed.
- [ ] Trusted CA certificates được chọn từ **nguồn đã xác minh**, phạm vi truststore đúng môi trường/client.
- [ ] Server certificate có SAN **DNS/IP đúng type** và hostname thực tế từ URL/config; không dùng Subject CN/alias thay SAN.
- [ ] Client cấp cao giữ hostname verification mặc định; raw `SSLSocket`/`SSLEngine` bật `"HTTPS"` endpoint identification khi giao thức yêu cầu.
- [ ] Không thay `SSLContext.setDefault` toàn JVM bằng trust config bất cẩn.
- [ ] Chain đầy đủ/intermediate được xử lý, certificate validity, KU/EKU, algorithm constraints và revocation policy được kiểm đúng.
- [ ] Có test **đúng CA + đúng hostname ⇒ accept**.
- [ ] Có test **sai CA + đúng hostname ⇒ reject**.
- [ ] Có test **đúng CA + sai hostname/IP ⇒ reject**.
- [ ] Dev/staging/production có CA, truststore và SAN/endpoint riêng theo chính sách; không dùng root dev rộng ở production.
- [ ] HTTPS qua proxy/LB, redirect và mTLS vẫn xác minh đúng logical peer identity.
- [ ] Không hard-code password/keystore production, không log private key/session keys/API tokens; có audit và certificate rotation.
- [ ] CI hoặc code review phát hiện cấu hình insecure từ cả Java source, YAML/properties, system properties và thư viện HTTP đang dùng.

## 18. Kết luận

**Đừng biến lỗi TLS thành lý do bỏ xác thực.** Một HTTPS/JSSE client phải chứng minh **hai điều**: chain chứng thư hợp lệ với trust anchors **được chủ động tin**, và certificate leaf mô tả **đúng hostname/IP cần kết nối**. Trust-all bỏ lớp xác thực CA; skip-hostname bỏ lớp ràng buộc danh tính endpoint. Cả hai đều có thể để kẻ đứng giữa mạo danh peer dù lưu lượng vẫn được mã hóa.

Ví dụ Java 17+ trong bài không dùng các shortcuts này: nó thiết lập trust manager chuẩn, bật `HTTPS` endpoint identification và **bắt buộc từ chối sai CA/sai hostname**, bên cạnh trường hợp đúng đi qua. Khi gặp lỗi thực tế, sửa nguồn certificate, CA, SAN, URL hoặc client configuration **đúng nguyên nhân**, không giảm mức xác minh để có một lần kết nối “thành công”.

**Tài liệu tham khảo:** [Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html), [RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525), [Java 17 keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html).
