# Phân biệt tin cậy CA và xác minh danh tính máy chủ khi kết nối TLS/HTTPS trong Java 10+

## 1. Hai câu hỏi khác nhau, đều phải trả lời

Khi một Java client gọi `https://api.example.com`, server gửi chứng thư X.509 trong quá trình TLS handshake. Để kết nối thật sự được xác thực, client phải thỏa **hai yêu cầu khác nhau**:

1. **Tin cậy CA / xác minh đường dẫn chứng thư (certificate-path validation):** chứng thư server có thuộc một đường dẫn được ký hợp lệ đến **trust anchor** mà client chấp nhận không, với thời hạn, key usage, algorithm constraints và các điều kiện áp dụng?
2. **Xác minh danh tính máy chủ (endpoint identification/hostname verification):** chứng thư đó có đại diện cho **`api.example.com`**, tức tên dịch vụ mà client thực sự định kết nối, không?

**Phải đạt cả hai.** Một CA có thể phát hành chứng thư hợp lệ cho rất nhiều tên miền. Chứng thư có chuỗi chữ ký dẫn đến CA được tin cậy **không có nghĩa được phép mạo danh mọi hostname**.

```text
Client: https://api.example.com
                |
TLS server gửi leaf certificate:
  Issuer: CA hợp lệ mà client tin
  Subject Alternative Name: DNS=other.example.com
                |
                +--> Chuỗi chứng thư hợp lệ?    CÓ
                +--> Đúng api.example.com?       KHÔNG
                |
                v
         TỪ CHỐI KẾT NỐI HTTPS
```

Nếu chỉ tin CA mà không kiểm hostname, một kẻ kiểm soát route/DNS/proxy có thể đưa chứng thư hợp lệ **cho website của chính họ**, khiến client chấp nhận sai máy chủ đích. Nếu chỉ kiểm hostname mà không tin chain, kẻ tấn công cũng có thể tự tạo chứng thư có SAN của bất kỳ domain nào.

**Bối cảnh module Java 10:** **JEP 319 — Root Certificates** đưa tập chứng thư CA gốc mặc định vào OpenJDK phù hợp. Điều đó **tăng khả năng xây dựng chuỗi tin cậy**, không làm mất yêu cầu kiểm danh tính endpoint. Nội dung bài ưu tiên các cơ chế **còn áp dụng trên JDK hiện đại** và không hướng dẫn bypass TLS.

## 2. Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt root CA, intermediate CA và leaf/server certificate.
2. Giải thích trust anchor, certificate chain và PKIX validation.
3. Phân biệt certificate signature/trust với TLS server identity.
4. Mô tả vì sao CA công cộng đáng tin vẫn có thể ký chứng thư cho sai hostname.
5. Đọc SAN `dNSName` và `iPAddress`, hiểu DNS name ≠ IP literal.
6. Tránh dựa vào `Common Name (CN)` như hostname source theo RFC 9525.
7. Hiểu vai trò của `cacerts`, `jssecacerts`, truststore tùy chỉnh và JEP 319.
8. Hiểu sự khác biệt giữa truststore và keystore chứa private key.
9. Phân biệt hostname verification với SNI (Server Name Indication).
10. Biết cách Java `TrustManagerFactory`/`X509ExtendedTrustManager` và `SSLParameters` phối hợp.
11. Bật `setEndpointIdentificationAlgorithm("HTTPS")` khi dùng raw `SSLSocket` phù hợp.
12. Dùng các HTTP clients mức cao đã áp dụng HTTPS verification theo mặc định.
13. Nhận diện khi nào revocation/OCSP, validity, EKU và algorithm policy có thể gây lỗi.
14. Tránh `TrustManager` bỏ qua chứng thư và `HostnameVerifier` luôn trả true.
15. Thực hành local-only: tạo CA và leaf có SAN bằng `keytool`.
16. Viết và chạy Java 17+ kiểm ba tình huống độc lập về trust CA và hostname.
17. Đọc các lỗi `PKIX path building failed` và `No subject alternative name matching` đúng loại.
18. Hiểu tác động của proxy, load balancer, mTLS và CA rotation.
19. Đưa ra checklist TLS client để giữ cả hai yêu cầu bảo mật khi nâng JDK.

## 3. Root CA, intermediate CA và leaf certificate

Một certificate chain thường có cấu trúc:

```text
Root CA certificate
  (client đặt niềm tin từ truststore / trust anchor)
            |
            | ký chứng thư CA cấp dưới
            v
Intermediate CA
  CA=TRUE, keyCertSign, các constraints
            |
            | ký chứng thư máy chủ
            v
Leaf / End-entity certificate
  SAN: DNS=api.example.com
  Extended Key Usage: serverAuth
  Public key của server
```

**Root CA** là trust anchor mà client đã chọn tin. **Intermediate CA** thường không cần import như anchor nếu client xây dựng được chain hợp lệ đến root được tin. **Leaf certificate** phải gắn với endpoint và mục đích sử dụng phù hợp.

Server thường gửi leaf và các intermediate cần thiết, không nhất thiết gửi root vì root đã được client lưu sẵn.

Các chi tiết cần phân biệt:

- Chữ ký của **issuer** chứng minh cert đã được issuer ký bằng private key tương ứng.
- `BasicConstraints` kiểm một cert có được làm CA không.
- `KeyUsage` (ví dụ `keyCertSign`) và `ExtendedKeyUsage` giới hạn vai trò.
- Mức độ tin cậy đến từ việc client **chủ động chấp nhận trust anchor**, không phải chỉ từ việc chứng thư tự khai “Root CA”.
- CA tin cậy có thể phát hành chứng thư cho **nhiều tên dịch vụ khác nhau**; đây là lý do kiểm hostname vẫn bắt buộc.

Một chứng thư server được ký bởi CA tin cậy **chỉ là một trong các điều kiện cần**, không phải điều kiện đủ.

## 4. Truststore chứa gì và khác keystore thế nào?

Một **truststore** chứa public certificates/trust anchors mà ứng dụng dùng để xác minh certificate chains. Nó **không phải** nơi client bắt buộc lưu private key của server.

Một **keystore chứa key entry** của server thường gồm server private key và certificate chain để server **chứng minh quyền sở hữu khóa** trong TLS handshake.

| Nội dung | Client truststore | Server keystore |
| --- | --- | --- |
| Root CA public certificates | Thường có | Có thể có để tạo chain |
| Server leaf public certificate | Không nhất thiết, tùy trust policy | Có |
| Server **private key** | **Không nên có** | **Có, phải bảo vệ** |
| Mục đích | Kiểm trust chain của peer | Chứng minh identity cho peer |
| Cấu hình Java liên quan | `TrustManagerFactory` | `KeyManagerFactory` |

Trong mTLS, client có thể cần **một keystore private key riêng** để server xác thực client. Điều đó không thay việc client dùng truststore để xác thực server.

### Những nguồn trust của Java JSSE

Trên các SunJSSE JDK phù hợp:

- `$JAVA_HOME/lib/security/cacerts`: truststore CA mặc định của bản JDK.
- `jssecacerts`: truststore dành riêng cho JSSE nếu có, được ưu tiên theo cơ chế JSSE.
- `-Djavax.net.ssl.trustStore=...`, `-Djavax.net.ssl.trustStoreType=...`: chọn truststore riêng cho tiến trình.
- `TrustManagerFactory.init(KeyStore)`: chọn trust material cho một context cụ thể.

Ví dụ launcher:

```bash
java -Djavax.net.ssl.trustStore=client-trust.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -jar app.jar
```

Nếu truststore cần password, hãy cung cấp qua cơ chế quản lý secrets phù hợp. **Không đưa password thật vào Git, log hoặc ví dụ lệnh công khai.**

**Điểm cốt lõi:** thay truststore thay đổi tập CA mà client chấp nhận; nó **không tự thay hostname mà chứng thư được phép đại diện**.

## 5. JEP 319 của Java 10 làm được gì?

**JEP 319 — Root Certificates** hỗ trợ phân phối một tập root CA certificates mặc định với OpenJDK thời Java 10. Trước đó một số OpenJDK builds có `cacerts` rỗng, gây lỗi không xác minh được certificate chains của các HTTPS websites thông thường.

Tác dụng chính:

- Giúp Java client có sẵn một số **public trust anchors** trong bản JDK phù hợp.
- Giảm yêu cầu import thủ công root CA công cộng chỉ để truy cập Internet.
- Cho phép PKIX trust manager xây chain tới những root đó.

Nhưng JEP 319:

- **Không cấp quyền cho chứng thư một CA được dùng với mọi hostname**.
- **Không loại bỏ SAN matching**.
- **Không bảo đảm mọi public root CA đều có trong mọi JDK**.
- **Không đảm bảo root CAs và distrust policies bất biến theo năm tháng**.
- **Không tự tin cậy private/internal CAs của tổ chức**.
- **Không thay đổi yêu cầu sử dụng public/private keys đúng cách**.

Một tổ chức vẫn có thể cần truststore riêng cho CA nội bộ. Tuy nhiên thêm private CA vào truststore mặc định **mở rộng phạm vi tin cậy** trên các dịch vụ sử dụng truststore ấy, nên phải kiểm soát scope và fingerprint.

## 6. Thế nào là một certificate path hợp lệ?

Trong PKIX path validation, các bước có thể gồm:

1. Xây dựng được đường dẫn hợp lệ từ leaf đến một trust anchor client đã cấu hình.
2. Xác nhận chữ ký/mối quan hệ giữa issuer và subject.
3. Kiểm hạn hiệu lực `notBefore`, `notAfter`.
4. Kiểm `BasicConstraints` và `pathLenConstraint` của intermediate CAs.
5. Kiểm `KeyUsage` và `ExtendedKeyUsage` phù hợp TLS server.
6. Kiểm policy/algorithm constraints, chẳng hạn khóa/chữ ký quá yếu bị JDK cấm.
7. Kiểm `NameConstraints` hoặc các hạn chế khác khi áp dụng.
8. Kiểm tình trạng revocation theo **cấu hình thực tế** nếu policy yêu cầu.

**Không giản lược** path verification thành “issuer name trùng với tên root”. Chữ ký, public keys, chain và các constraints mới quan trọng.

### Cảnh báo về revocation

JSSE PKIX trust manager tạo qua `TrustManagerFactory.init(KeyStore)` có thể **không bật revocation checking mặc định** theo cấu hình provider. Muốn yêu cầu CRL/OCSP, cần thiết lập policy và cơ chế truy cập dữ liệu thu hồi phù hợp.

Không mặc định mọi Java HTTPS kết nối đều tra OCSP/CRL; cũng không nên tắt kiểm revocation một cách tùy tiện nếu ứng dụng đã bật theo chính sách bảo mật.

### Path hợp lệ vẫn chưa nói được hostname

Đường dẫn đến CA tin cậy có thể hợp lệ cho `other.example.net` nhưng không cho `api.example.com`. Tầng endpoint identity phải kiểm tiếp.

## 7. Endpoint identity verification kiểm điều gì?

Một HTTPS client gọi:

```text
https://billing.example.com/orders
```

Reference identity thường là hostname từ URL: **`billing.example.com`**. Client so với danh tính server leaf certificate, chủ yếu ở extension **Subject Alternative Name (SAN)**.

Ví dụ:

```text
Subject: CN=billing.example.com
Subject Alternative Name:
  DNS:billing.example.com
  DNS:api.example.com
```

Có SAN phù hợp với `billing.example.com` và `api.example.com`, **không** phù hợp `admin.example.com` chỉ vì cùng miền gốc.

Đừng để server tự chọn tên nào cần kiểm bằng cách đọc SAN rồi đổi tên đích. **Client phải biết tên dịch vụ cần liên hệ trước khi xác minh**, từ URL/cấu hình đáng tin.

### CN và chuẩn hiện hành

**RFC 9525 (2023)** là chuẩn hiện hành về xác thực service identity, thay RFC 6125. Nó yêu cầu dùng SAN cho danh tính DNS/IP phù hợp, **không** dựa vào Common Name (CN) như định danh thay thế.

Một số implementation hoặc phiên bản cũ có CN fallback vì tương thích lịch sử. **Không thiết kế chứng thư mới dựa vào fallback CN**; cấp SAN rõ ràng.

## 8. DNS SAN khác IP SAN

Hai loại định danh:

- `dNSName`: ví dụ `api.example.com` hay `localhost`.
- `iPAddress`: ví dụ `127.0.0.1` hay một địa chỉ IPv6 hợp lệ.

Một chứng thư:

```text
SAN: DNS=localhost
```

không tự khớp tên tham chiếu `127.0.0.1`, dù DNS `localhost` thường trỏ vào loopback IP.

Một chứng thư:

```text
SAN: IP=127.0.0.1
```

không tự khớp tên `localhost`.

**Lý do:** reference identity là **tên mà client muốn xác thực**, không chỉ địa chỉ TCP cuối cùng. DNS resolution và TLS identity là những bước khác nhau.

### Wildcard có giới hạn

Theo RFC 9525, wildcard của DNS-ID nếu được hỗ trợ chỉ nên là **toàn bộ nhãn ngoài cùng bên trái**, chẳng hạn `*.example.com`, không phải mọi chuỗi có hậu tố `example.com`.

Không tự viết:

```java
// Không nên: tự kiểm host bằng endsWith(...) thay TLS engine.
boolean accepted = hostname.endsWith(".example.com");
```

Đoạn minh họa trên không phải standalone program; nó cho thấy **anti-pattern** có thể bỏ qua quy tắc một-level wildcard, IDNA và các trường hợp biên.

## 9. Ma trận CA trust và hostname

| Path/CA trust | Endpoint identity | HTTPS chấp nhận? |
| --- | --- | --- |
| **PASS** | **PASS** | Có thể, nếu các điều kiện TLS khác cũng hợp lệ |
| **PASS** | **FAIL** | **Từ chối** |
| **FAIL** | **PASS** | **Từ chối** |
| **FAIL** | **FAIL** | **Từ chối** |

“Độc lập” ở đây mô tả **hai yêu cầu bảo mật phải cùng đúng**, không đòi JVM gọi hai callback theo một thứ tự cố định. `X509ExtendedTrustManager` có thể kết hợp trust path và hostname checking trong **cùng TLS handshake** khi được cấu hình đúng.

### Hai lỗi bảo mật khác nhau

**Trust-all:** một client bỏ kiểm trust anchors, dễ chấp nhận chứng thư do attacker tự tạo với **SAN đúng**.

**Hostname verification bị tắt:** client vẫn kiểm CA nhưng có thể chấp nhận chứng thư hợp lệ do CA đó cấp **cho domain khác**.

**Không dùng cả hai cách bypass**, kể cả với môi trường staging hoặc internal services, trừ phi đó là một môi trường test cô lập được thiết kế đặc biệt và không xử lý dữ liệu nhạy cảm. Bài này dùng cách kiểm thật, không cần bypass.

## 10. Các API Java trong JSSE

| API | Mục đích |
| --- | --- |
| `KeyStore` | Lưu certificate/key entries, dùng làm keystore hoặc truststore |
| `TrustManagerFactory` | Tạo trust managers theo thuật toán, ví dụ `PKIX` |
| `X509TrustManager` | Xác minh chứng thư/chain từ peer |
| `X509ExtendedTrustManager` | Kiểm chain có ngữ cảnh `SSLSocket`/`SSLEngine` và SSL parameters |
| `SSLContext` | Tạo factory/engine cho TLS với key managers và trust managers đã cấu hình |
| `SSLParameters` | Điều khiển protocols, algorithm constraints, SNI và endpoint identification |
| `SSLSocket` | TLS socket với `startHandshake()` |
| `SSLEngine` | TLS engine dùng trong I/O tùy chỉnh, có cùng yêu cầu identity checking |
| `HttpsURLConnection` | HTTP-over-TLS client với hostname verification phù hợp theo mặc định |
| `java.net.http.HttpClient` | HTTP client JDK hiện đại, dùng HTTPS peer identity verification |

`X509ExtendedTrustManager` giải quyết vấn đề quan trọng: phương thức `checkServerTrusted(chain,authType)` cũ không biết hostname đang kết nối. Bản extended có thể xem socket/engine và endpoint identification policy, do đó kiểm cả path lẫn identity trong một call theo implementation.

**Không tự viết trust manager chỉ để làm việc SunJSSE đã hỗ trợ.**

## 11. Raw `SSLSocket`: phải chủ động bật endpoint identification

Ví dụ Java (mã rút gọn):

```java
SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket("api.example.com", 443);

SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);

socket.startHandshake();
```

`context` phải là `SSLContext` dùng trust manager hợp lệ; cần import, try-with-resources và exception handling để thành chương trình đầy đủ. Xem **mục 19** cho một chương trình Java 17+ chạy độc lập.

Điểm then chốt:

- `SSLContext.getInstance("TLS")` **không mặc nhiên** là bật HTTPS hostname matching trên mọi raw TLS socket.
- Gọi `setEndpointIdentificationAlgorithm("HTTPS")` **trước handshake**.
- Dùng hostname đúng của service từ URL/cấu hình **được tin cậy**.
- Không gửi thông tin nhạy cảm trước khi xác thực peer thành công.
- Nếu có `SSLHandshakeException`, **không tắt verification để retry**.

### Giao thức khác HTTPS

Thuật toán `"HTTPS"` áp dụng cho quy tắc endpoint identification của HTTPS. Các giao thức TLS khác có profile/rules riêng (ví dụ `LDAPS`). Không áp dụng mù quy tắc hostname HTTP cho mọi TLS protocol.

## 12. Client mức cao xử lý hostname thế nào?

Trên SunJSSE/JDK, các API HTTPS cấp cao thường bật kiểm server identity theo mặc định:

```java
var connection = (javax.net.ssl.HttpsURLConnection)
        new java.net.URL("https://api.example.com").openConnection();
connection.connect();
```

Với Java 11+:

```java
var client = java.net.http.HttpClient.newHttpClient();
var request = java.net.http.HttpRequest.newBuilder(
        java.net.URI.create("https://api.example.com/health"))
        .GET().build();
var response = client.send(
        request, java.net.http.HttpResponse.BodyHandlers.ofString());
```

Hai đoạn là ví dụ API **có truy cập mạng** và cần nằm trong một method có xử lý exceptions; không phải chương trình offline. Chúng cho thấy cách client xác định **hostname từ URL**.

### Cảnh báo `HostnameVerifier`

Không viết:

```java
// ANTI-PATTERN: KHÔNG sử dụng thực tế.
// connection.setHostnameVerifier((host, session) -> true);
```

Trả true vô điều kiện sẽ làm mất bảo vệ against host spoofing.

Tương tự, không tạo `X509TrustManager` có `checkServerTrusted(...)` rỗng rồi coi đó là “fix HTTPS”. Nếu chứng thư sai, cần **sửa chain, SAN, hostname đích hoặc truststore**, không bỏ authentication.

## 13. SNI không phải xác thực danh tính

**SNI — Server Name Indication** cho phép client gửi một tên DNS trong TLS handshake để server biết phải chọn certificate nào khi một IP phục vụ nhiều virtual hosts.

```text
Client -> IP của load balancer
          SNI: api.example.com
          |
Server chọn leaf certificate
          SAN: DNS=api.example.com
          |
Client vẫn kiểm:
  (1) certificate chain có tin cậy không?
  (2) api.example.com có nằm trong SAN phù hợp không?
```

**SNI là gợi ý chọn certificate**, không phải lời xác thực rằng certificate đã đúng. Server có thể trả cert khác hoặc không hỗ trợ SNI; client vẫn phải xác minh.

### Proxy và nhiều TLS hops

Nếu client gọi `https://service.company.example` qua reverse proxy, tên cần kiểm thường là `service.company.example` — tên service URL. Proxy có thể đóng TLS tại đó và mở một kết nối TLS khác tới backend; **mỗi TLS hop** có security/trust/identity policy của riêng nó.

Không mặc định lấy tên của backend internal container thay cho hostname public client đã yêu cầu, hoặc bỏ hostname check chỉ vì IP của load balancer khác A record kỳ vọng.

## 14. CA rotation, browser/JDK store và JEP 319

Một số JDK builds có tập root CAs khác nhau. Dữ liệu trust được cập nhật theo chính sách của vendor và các security updates. Cùng một website có thể hoạt động trên một runtime nhưng fail trên runtime khác vì:

- CA root thiếu hoặc đã bị distrust.
- Intermediate chain server gửi chưa đầy đủ.
- Truststore bị override bởi container hoặc command line.
- Thuật toán chữ ký/kích thước khóa bị policy hiện hành từ chối.
- DNS/SNI dẫn tới certificate khác.
- Đồng hồ máy sai hoặc certificate hết hạn.
- Client framework thay cách xử lý hostname.

**Không hardcode một danh sách root certificates của Java 10 như chân lý vĩnh viễn.** JEP 319 là một mốc của OpenJDK distribution; tin cậy CA là một hệ thống **cần quản lý cập nhật**.

**Khác biệt TLS/browser:** client Java không bắt buộc dùng đúng OS/browser truststore ở mọi nền tảng. Không suy ra “trình duyệt truy cập được nên Java chắc chắn tin cùng CA”.

## 15. Phòng lab ngoại tuyến: thiết kế ba trường hợp

Ta tạo bằng `keytool`:

- **Lab Root CA**: CA A dùng để ký server leaf certificate.
- **Other Root CA**: CA B không ký server certificate.
- **Server certificate**: có `SAN: DNS=localhost`, được CA A ký.
- **`server.p12`**: chứa server private key và certificate chain.
- **`trust-good.p12`**: client tin CA A.
- **`trust-bad.p12`**: client chỉ tin CA B.

Ba lần handshake:

| Lượt | Truststore | Tên cần kiểm | SAN của leaf | Kết quả |
| --- | --- | --- | --- | --- |
| A | Tin Lab Root CA | `localhost` | `DNS:localhost` | **Thành công** |
| B | Tin Lab Root CA | `127.0.0.1` | `DNS:localhost` | **Từ chối vì identity sai** |
| C | Chỉ tin Other Root CA | `localhost` | `DNS:localhost` | **Từ chối vì chain không tin** |

Chương trình chỉ bind server trên `127.0.0.1`. Nó không truy cập Internet, không sửa `cacerts` và không dùng insecure trust manager/hostname verifier.

**Quy trình yêu cầu JDK 17+ có `keytool`, `javac`, `java`.** Mật khẩu `changeit` và hiệu lực 30 ngày chỉ phù hợp file **thử nghiệm tạm thời**. Không dùng các private keys này làm CA hoặc server cert production.

## 16. Tạo hai CA thử nghiệm bằng `keytool`

Trong một **thư mục trống riêng**, chạy lệnh Unix-like shell:

```bash
keytool -genkeypair -alias lab-ca \
  -keyalg RSA -keysize 2048 \
  -dname "CN=Lab Root CA,O=Training" \
  -ext "bc=ca:true,pathlen:0" \
  -ext "ku=keyCertSign,cRLSign" \
  -validity 30 -storetype PKCS12 \
  -keystore lab-ca.p12 -storepass changeit \
  -keypass changeit -noprompt

keytool -genkeypair -alias other-ca \
  -keyalg RSA -keysize 2048 \
  -dname "CN=Other Lab Root,O=Training" \
  -ext "bc=ca:true,pathlen:0" \
  -ext "ku=keyCertSign,cRLSign" \
  -validity 30 -storetype PKCS12 \
  -keystore other-ca.p12 -storepass changeit \
  -keypass changeit -noprompt
```

Mỗi CA có một **private key khác nhau**. Lab root CA được phép ký cert theo `BasicConstraints`/`KeyUsage`; CA còn lại là control không ký leaf.

**Không import `lab-ca.p12` vào truststore client**: file này chứa private key CA. Thay vào đó ta sẽ chỉ export/import **public root certificate** `lab-ca.crt`.

### Tạo server keypair và CSR

```bash
keytool -genkeypair -alias localhost \
  -keyalg RSA -keysize 2048 \
  -dname "CN=localhost,O=Training" \
  -ext "san=dns:localhost" \
  -validity 30 -storetype PKCS12 \
  -keystore server.p12 -storepass changeit \
  -keypass changeit -noprompt

keytool -certreq -alias localhost \
  -keystore server.p12 -storepass changeit \
  -file server.csr
```

`server.csr` là yêu cầu cấp chứng thư, không chứa server private key.

## 17. Ký leaf với SAN và tạo client truststores

Dùng CA A ký leaf:

```bash
keytool -gencert -alias lab-ca \
  -keystore lab-ca.p12 -storepass changeit \
  -infile server.csr -outfile server.crt -rfc \
  -validity 30 \
  -ext "san=dns:localhost" \
  -ext "ku=digitalSignature,keyEncipherment" \
  -ext "eku=serverAuth"
```

**SAN chỉ là `DNS=localhost`.** Ta cố ý **không** cấp `IP=127.0.0.1` để có kịch bản sai hostname.

Xuất hai public CA certificates:

```bash
keytool -exportcert -rfc -alias lab-ca \
  -keystore lab-ca.p12 -storepass changeit \
  -file lab-ca.crt

keytool -exportcert -rfc -alias other-ca \
  -keystore other-ca.p12 -storepass changeit \
  -file other-ca.crt
```

Đưa root A certificate và leaf do root A ký vào **server key chain**:

```bash
keytool -importcert -alias lab-ca \
  -file lab-ca.crt -keystore server.p12 \
  -storepass changeit -noprompt

keytool -importcert -alias localhost \
  -file server.crt -keystore server.p12 \
  -storepass changeit -noprompt
```

Tạo truststore đúng (A) và sai (B):

```bash
keytool -importcert -alias lab-ca \
  -file lab-ca.crt -storetype PKCS12 \
  -keystore trust-good.p12 -storepass changeit -noprompt

keytool -importcert -alias other-ca \
  -file other-ca.crt -storetype PKCS12 \
  -keystore trust-bad.p12 -storepass changeit -noprompt
```

Kiểm lại SAN và chain:

```bash
keytool -list -v -alias localhost \
  -keystore server.p12 -storepass changeit
keytool -printcert -file server.crt
```

Tìm `SubjectAlternativeName: DNSName: localhost` và chain server certificate -> lab-ca. Output chi tiết `keytool` không được coi là bất biến giữa các JDK builds.

### PowerShell trên Windows

Dấu `\` cuối dòng là cú pháp nối dòng của Bash, **không** áp dụng cho PowerShell. Có thể gõ từng lệnh `keytool` ở trên thành **một dòng** hoặc dùng nối dòng PowerShell đúng cách. Ví dụ một lệnh:

```powershell
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 2048 -dname "CN=Lab Root CA,O=Training" -ext "bc=ca:true,pathlen:0" -ext "ku=keyCertSign,cRLSign" -validity 30 -storetype PKCS12 -keystore lab-ca.p12 -storepass changeit -keypass changeit -noprompt
```

**Không nhập password thật trên command line production**; lệnh `-storepass changeit` trong lab dùng password dễ đoán để tái hiện thí nghiệm, không phải một best practice lưu secrets.

### Sau khi học

Xóa thư mục tạm chứa `lab-ca.p12`, `other-ca.p12` và `server.p12` theo quy trình dọn dẹp phù hợp. Không sử dụng các khóa tạm này cho public endpoints và **không import root CA lab vào truststore mặc định của máy**.

## 18. Vì sao lab dùng hai root CAs?

Nếu chỉ tạo một chứng thư server self-signed rồi import chính leaf làm trust anchor, ta vẫn chứng minh được hostname verification. Nhưng cấu trúc đó có thể làm người học nhầm **direct leaf trust** với **CA-issued certificate chain**.

Bài này tách:

```text
                      Lab Root CA (A)
                      TRUSTED trong trust-good.p12
                             |
                             | ký
                             v
                 server leaf: DNS=localhost
                             |
                             v
                 SSLServerSocket (127.0.0.1)

Other Root CA (B)
TRUSTED trong trust-bad.p12
      |
      x KHÔNG ký server leaf
```

Nhờ đó:

- Cùng leaf, truststore A và reference name `localhost` → PASS.
- Cùng leaf, truststore A nhưng reference identity IP `127.0.0.1` → FAIL **name**.
- Cùng leaf, truststore B và reference name `localhost` → FAIL **trust**.

**Hai biến được kiểm độc lập** trong cùng môi trường local loopback.

## 19. Chương trình Java 17+ độc lập

Tạo tệp **`TlsCertificateIdentityDemo.java`** cùng thư mục với `server.p12`, `trust-good.p12`, `trust-bad.p12`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public final class TlsCertificateIdentityDemo {
    private static final char[] PASSWORD = "changeit".toCharArray();

    private static KeyStore load(Path path) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (var in = java.nio.file.Files.newInputStream(path)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    private static SSLContext serverContext(Path directory) throws Exception {
        var kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(load(directory.resolve("server.p12")), PASSWORD);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), null, null);
        return context;
    }

    private static SSLContext clientContext(Path storeFile) throws Exception {
        var tmf = TrustManagerFactory.getInstance("PKIX");
        tmf.init(load(storeFile));
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);
        return context;
    }

    private static boolean succeeds(SSLContext context, int port,
                                    String expectedHost) throws Exception {
        // Both tests contact the same local TCP address.
        try (Socket raw = new Socket(InetAddress.getByName("127.0.0.1"), port);
             SSLSocket socket = (SSLSocket) context.getSocketFactory()
                     .createSocket(raw, expectedHost, port, true)) {
            SSLParameters p = socket.getSSLParameters();
            p.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(p);
            socket.startHandshake();
            return true;
        } catch (SSLHandshakeException rejected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Path.of(args[0]);
        SSLContext server = serverContext(directory);
        SSLContext trusted = clientContext(directory.resolve("trust-good.p12"));
        SSLContext wrongCa = clientContext(directory.resolve("trust-bad.p12"));

        try (SSLServerSocket listener = (SSLServerSocket)
                server.getServerSocketFactory().createServerSocket(
                        0, 3, InetAddress.getByName("127.0.0.1"))) {
            int[] accepted = {0};
            Thread worker = new Thread(() -> {
                for (int i = 0; i < 3; i++) {
                    try (SSLSocket peer = (SSLSocket) listener.accept()) {
                        accepted[0]++;
                        peer.setSoTimeout(4000);
                        try {
                            peer.startHandshake();
                        } catch (IOException expectedClientRejection) {
                            // The client may close after rejecting the certificate.
                        }
                    } catch (IOException error) {
                        throw new IllegalStateException(error);
                    }
                }
            }, "tls-lab-server");
            worker.start();

            boolean correct = succeeds(trusted, listener.getLocalPort(), "localhost");
            boolean wrongName = succeeds(trusted, listener.getLocalPort(), "127.0.0.1");
            boolean wrongRoot = succeeds(wrongCa, listener.getLocalPort(), "localhost");

            worker.join(5000);
            if (worker.isAlive()) {
                throw new IllegalStateException("Server did not finish");
            }
            if (!correct || wrongName || wrongRoot || accepted[0] != 3) {
                throw new AssertionError("Unexpected TLS result");
            }

            System.out.println("correctHostAndTrustedCA=true");
            System.out.println("wrongHostButTrustedCARejected=true");
            System.out.println("correctHostButWrongCARejected=true");
            System.out.println("serverConnections=" + accepted[0]);
            System.out.println("noTrustAllOrBypass=true");
        }
    }
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 TlsCertificateIdentityDemo.java
java TlsCertificateIdentityDemo .
```

**Stdout chính xác đã kiểm thử trên HotSpot JDK 24:**

```text
correctHostAndTrustedCA=true
wrongHostButTrustedCARejected=true
correctHostButWrongCARejected=true
serverConnections=3
noTrustAllOrBypass=true
```

Chương trình dùng `TrustManagerFactory.getInstance("PKIX")` cho client contexts và **`setEndpointIdentificationAlgorithm("HTTPS")`** trên từng TLS socket **trước** `startHandshake()`.

### Tại sao truyền `expectedHost` riêng từ địa chỉ TCP?

Cả ba raw TCP connections nối đến `127.0.0.1` để tránh phụ thuộc DNS và bảo đảm cùng một server. `SSLSocketFactory.createSocket(rawSocket, expectedHost, port, true)` đặt identity của peer cho TLS layer theo mục đích **thí nghiệm**.

Trong ứng dụng thật, hostname xác minh phải là **định danh service được client tin và muốn truy cập**, thường từ URL. Không tự thay bằng một tên khác chỉ để kết nối được.

### Tại sao không kiểm bằng text của exception?

SunJSSE có thể thay đổi thông điệp giữa các versions, ví dụ “No subject alternative names matching IP address ...” và “PKIX path building failed”. Thay vì phụ thuộc nguyên văn, demo kiểm thành công/thất bại với `SSLHandshakeException` và giữ nguyên security checks.

### Tại sao server được tạo bằng `SSLServerSocket`?

Để không cần Internet hay một public HTTPS server, vẫn có thể chạy TLS handshake thật có certificate chain. Demo **không** gửi HTTP request; nó kiểm đúng phần certificate trust và endpoint identification trong TLS.

### Giới hạn của ví dụ

- Certificate validity rất ngắn; không dùng cho production.
- Server chỉ bind `127.0.0.1`, không lắng nghe trên public interfaces.
- Password hardcoded chỉ là dữ liệu lab.
- Revocation/OCSP/Certificate Transparency không thuộc các trường hợp đã test.
- Java SE không bảo đảm mọi JSSE provider tạo cùng exception text.
- Kết quả **đã kiểm trên HotSpot JDK 24**, không khẳng định một custom provider sẽ có cấu hình/hành vi tương tự.
- Không sử dụng trust-all hoặc bypass hostname checks.

## 20. Phân tích chính xác năm dòng stdout

**`correctHostAndTrustedCA=true`**

Server chain dẫn đến `lab-ca` mà `trust-good.p12` đã tin, đồng thời SAN `DNS=localhost` khớp reference name `localhost`. Đây là trường hợp **cả trust và identity đều đạt**.

**`wrongHostButTrustedCARejected=true`**

Client **vẫn** tin root A, nhưng reference name là **IP `127.0.0.1`**, trong khi chứng thư chỉ chứa **DNS SAN localhost**. TLS handshake bị từ chối. Đây là minh chứng rằng **CA trust không thay thế hostname/IP identity matching**.

**`correctHostButWrongCARejected=true`**

Client dùng `trust-bad.p12` chỉ tin root B (không ký leaf), dù tên `localhost` vẫn khớp. TLS handshake bị từ chối. Đây là minh chứng rằng **hostname đúng không thay thế trust anchor hợp lệ**.

**`serverConnections=3`**

Local TLS server đã chấp nhận ba TCP connections. Không có nghĩa cả ba TLS handshakes thành công.

**`noTrustAllOrBypass=true`**

Bài dùng PKIX trust managers và bật HTTPS endpoint identification, không chấp nhận mọi certificate bằng logic tùy chỉnh. Đây là mô tả tính an toàn của cấu hình lab, không phải cam kết về mạng Internet.

## 21. Các lỗi HTTPS và cách phân loại

### 21.1. `PKIX path building failed`

Dấu hiệu thường liên quan không xây được chain tới CA được client tin, hoặc các yếu tố PKIX làm path không hợp lệ.

Kiểm:

- Client đang dùng **truststore nào**?
- Có đúng root CA certificate/trust anchor chưa?
- Server có gửi intermediate certificate phù hợp không?
- Issuer/subject signatures, validity và constraints có đúng không?
- Có JDK distrust/algorithm policy mới không?

**Không giải quyết bằng trust-all TrustManager**.

### 21.2. `No subject alternative DNS name matching ...`

Leaf SAN không chứa DNS hostname client cần xác minh, hoặc rules matching không cho phép. **Sửa SAN hoặc đúng URL hostname**, không chỉ import thêm root.

### 21.3. `No subject alternative names matching IP address ...`

Client dùng IP literal nhưng leaf thiếu SAN `iPAddress` cho địa chỉ đó. DNS SAN có thể resolve tới IP ấy nhưng **không thay thế** IP SAN.

### 21.4. `CertificateExpiredException` / `CertificateNotYetValidException`

Certificate ngoài thời hạn cho phép hoặc đồng hồ client sai. Kiểm time sync và tiến trình cấp/gia hạn chứng thư; không tắt validity checks.

### 21.5. `Algorithm constraints check failed`

Một key hoặc signature algorithm có thể bị JDK policy từ chối. Kiểm security properties như `jdk.certpath.disabledAlgorithms` và cập nhật chứng thư/CA; không giảm bảo mật toàn JVM tùy tiện.

### 21.6. `SSLHandshakeException` khác

Có thể do TLS protocol/cipher, SNI, mTLS client auth, network disconnect hoặc sai cấu hình server. **Đọc cause chain và runtime logs**, không cho rằng mọi handshake error đều là thiếu CA.

## 22. Đừng nhầm lỗi keystore server với lỗi truststore client

| Triệu chứng | Thành phần cần kiểm |
| --- | --- |
| Server không thể khởi động TLS | Private key/alias/password/certificate chain của **server keystore** |
| Client thiếu CA/trust anchor | **Client truststore** và certificate path |
| Client kết nối được TCP nhưng hostname mismatch | **Leaf SAN** so với identity URL |
| Client kết nối bằng IP, cert chỉ có DNS SAN | **IP SAN** hoặc thay bằng đúng DNS URL |
| Đằng sau load balancer nhận nhầm cert | TLS terminator và **SNI** |
| Sau nâng JDK mới lỗi | Security updates, CA distrust, algorithm constraints |
| mTLS server từ chối client | Client certificate, CA và application authorization |
| Raw SSLSocket không kiểm tên | Endpoint identification chưa được bật |

**Không dùng workaround sai loại**: thêm CA không sửa hostname mismatch; đổi URL không tự tạo trust path; cấu hình SNI không thay yêu cầu kiểm trust và SAN.

## 23. Private CA nội bộ nên được triển khai thế nào?

Một tổ chức có thể phát hành CA riêng cho service nội bộ. Khi client Java tin một private CA, nó có thể chấp nhận các server certificates do CA này phát hành **cho các tên phù hợp** và đúng policy. Phạm vi tin cậy có thể rộng hơn một URL.

Khuyến nghị:

- Xác minh chính xác fingerprint/provenance của root CA trước khi nhập.
- Ưu tiên **application-scoped truststore** hoặc SSLContext riêng khi cần kiểm soát blast radius.
- Bảo vệ private keys của CA trong hệ thống phát hành chứng thư riêng, không gửi vào client containers.
- Không thay `cacerts` toàn JDK chỉ để sửa một service nếu không có chính sách/quyền quản trị.
- Quản lý certificate rotation, hết hạn và CA distrust.
- Giữ nguyên endpoint identity verification cho các tên DNS/IP nội bộ.
- Đảm bảo mọi truststore thay thế vẫn có các trust anchors khác cần thiết, nếu client gọi thêm public services.
- Không lưu password production trong source code/Git.

### Pinning có cần không?

Certificate/public-key pinning có thể giới hạn thêm một peer nhưng tăng rủi ro downtime khi rotate. Nó không phải giải pháp mặc định và **không cho phép bỏ hostname verification** tùy tiện.

Nếu cần pinning, phải có threat model, kế hoạch backup pins/rotation và kiểm soát các hostnames được phép. Trong nhiều hệ thống nội bộ, dedicated truststore + SAN đúng là phương án đơn giản hơn.

## 24. mTLS là chiều xác thực riêng

Với **mutual TLS**, server yêu cầu client certificate; client đồng thời vẫn xác thực server.

- **Client kiểm server:** CA trust + endpoint identity server.
- **Server kiểm client:** client certificate chain/trust policy và ứng dụng xác định **client identity/authorization**.

Đừng đồng nhất client cert được CA ký với quyền gọi tất cả APIs. Một certificate có thể chỉ chứng minh khóa của một client principal; ứng dụng còn phải phân quyền.

Trong Java, client mTLS thường có **hai nguồn dữ liệu riêng**:

1. Keystore chứa **client private key + certificate chain**.
2. Truststore dùng để xác minh **server**.

Server có keyStore của chính server và truststore/identity policy cho client. Những trường hợp này không làm yêu cầu hostname verification biến mất.

## 25. Kiểm tra và chẩn đoán Java hiện hành

Khi gặp sự cố TLS:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager \
     -jar app.jar
```

Khi cần chẩn đoán certificate path:

```bash
java -Djava.security.debug=certpath \
     -jar app.jar
```

Kiểm root CA trong default truststore:

```bash
keytool -list -cacerts
```

**Lưu ý:** logging chi tiết có thể chứa hostnames, certificate details và metadata nhạy cảm. Chỉ bật khi cần và kiểm soát quyền/retention. Không chia sẻ private keys hoặc truststore chứa secrets.

Cũng không khẳng định chỉ vì `keytool -list -cacerts` thấy root thì **ứng dụng đang dùng đúng file đó**: `jssecacerts`, `javax.net.ssl.trustStore` hoặc custom `SSLContext` có thể override mặc định.

### Hai điểm đặc biệt quan trọng

1. **Trust manager log “trusted” chưa đủ để kết luận hostname match**; cần xem kết quả xác thực cuối cùng của TLS connection.
2. **Đừng tự bật insecure mode** chỉ để logs ngừng có lỗi; phân loại đúng trước khi sửa.

## 26. Những lỗi thiết kế và cách sửa

**Lỗi A — “CA đáng tin thì tên nào cũng được”:** sai. Một CA có thể cấp cert cho nhiều domain. **Sửa:** xác minh SAN với tên đích.

**Lỗi B — “Hostname đã đúng nên bỏ qua trust chain”:** sai. Attacker tự ký cert có SAN tùy ý. **Sửa:** dùng trust anchors và PKIX checks.

**Lỗi C — “CN đủ rồi, không cần SAN”:** cách làm cũ, không phù hợp RFC 9525. **Sửa:** đưa identity vào SAN thích hợp.

**Lỗi D — “DNS resolve cùng IP thì hostname match”:** sai. IP SAN và DNS SAN khác nhau.

**Lỗi E — “SNI làm hostname verification”:** sai. SNI chỉ giúp server chọn cert.

**Lỗi F — “Trả true trong HostnameVerifier là fix nhanh”:** nguy hiểm. **Sửa:** cấp lại cert hoặc dùng đúng URL.

**Lỗi G — “Trust-all X509TrustManager cho service nội bộ là vô hại”:** nguy hiểm, làm mất authentication.

**Lỗi H — “Import CA tùy ý vào cacerts”:** mở rộng trust cho những ứng dụng khác. **Sửa:** kiểm fingerprint và scope.

**Lỗi I — “TLS mặc định luôn kiểm CRL/OCSP”:** không thể khẳng định mọi provider/config đều vậy. **Sửa:** xác minh revocation policy.

**Lỗi J — “PKIX error là hostname error”:** có thể sai loại; cần đọc cause chain.

**Lỗi K — “Hostname error là CA error”:** sai; thêm CA không sửa SAN.

**Lỗi L — “Chuyển từ HttpsURLConnection sang raw SSLSocket vẫn an toàn như cũ”:** cần chủ động bật endpoint identification.

**Lỗi M — “Cứ dùng IP literal sẽ khớp DNS SAN”:** sai; cần IP SAN hoặc DNS URL.

**Lỗi N — “Có client cert mTLS là tự có quyền mọi endpoint”:** sai; vẫn cần authorization.

**Lỗi O — “Root certificates của JDK 10 không thay đổi”:** sai; theo dõi security updates.

**Lỗi P — “Certificate Transparency, revocation và hostname verification là một”:** khác nhau; mỗi cơ chế có scope/policy riêng.

**Lỗi Q — “SSLHandshakeException nào cũng do truststore”:** không; có thể TLS cipher, network, SNI, clientAuth, clock...

## 27. Checklist triển khai an toàn

1. **Định danh đích** của HTTPS URL/service đến từ nguồn tin cậy chưa?
2. **Client có PKIX trust manager thật** và không dùng trust-all?
3. **Root CA** có nằm trong effective truststore đúng không?
4. **Intermediate chain** có đầy đủ và hợp lệ không?
5. **Chữ ký, validity, KeyUsage/EKU** có phù hợp TLS server auth không?
6. **Algorithm constraints** trên JDK hiện hành có thỏa không?
7. **Revocation policy** có được xác định và cấu hình rõ chưa?
8. **SAN dNSName** có khớp hostname thực tế không?
9. Nếu URL là **IP literal**, có **SAN iPAddress** tương ứng không?
10. Có đang dựa vào **CN fallback** cũ không?
11. Có dùng wildcard đúng quy tắc không?
12. **SNI** có đưa server đến đúng certificate không?
13. Có hiểu SNI **không thay hostname check** không?
14. Raw `SSLSocket/SSLEngine` đã bật endpoint identification đúng lúc chưa?
15. Có cấu hình nào tắt `HttpsURLConnection` hostname verification không?
16. Có thư viện/framework nào dùng insecure SSL mode không?
17. Custom CA được import theo **scope phù hợp** chưa?
18. Private key của CA/server/client được bảo vệ đúng không?
19. Có kế hoạch **leaf/CA rotation** và cập nhật JDK trust policies không?
20. Có phân biệt mTLS identity và application authorization không?
21. Có test đúng **wrong-host** và **wrong-CA** scenarios không?
22. Có kiểm DNS/proxy/load-balancer không đưa về chứng thư sai không?
23. Có xử lý TLS handshake failures bằng fail-closed không?
24. Có kiểm security logs và không xuất private keys/secrets không?
25. Có test trên **đúng JDK vendor/build** được triển khai không?

## 28. Bài tập thực hành và đáp án

**Câu 1.** Cert được CA tin cậy ký nhưng chỉ có SAN `other.example.com`. Client gọi `api.example.com` có được chấp nhận không?

**Câu 2.** Leaf có SAN `api.example.com` nhưng được ký bởi CA chưa được trust. Kết quả?

**Câu 3.** Root CA và leaf certificate có vai trò giống nhau không?

**Câu 4.** JEP 319 trong Java 10 bổ sung gì?

**Câu 5.** JEP 319 có cho phép bỏ hostname verification không?

**Câu 6.** CA trust khác endpoint identity ở câu hỏi cần trả lời thế nào?

**Câu 7.** `TrustManagerFactory` làm nhiệm vụ gì?

**Câu 8.** `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` giải quyết điều gì?

**Câu 9.** `SSLSocket` raw mặc định có thể dựa vào để luôn check hostname không?

**Câu 10.** SAN `DNS:localhost` có khớp `127.0.0.1` không?

**Câu 11.** Vì sao `CN=localhost` không phải cách thiết kế cert mới được khuyến nghị?

**Câu 12.** `HostnameVerifier` luôn trả true có an toàn không?

**Câu 13.** `SNI=api.example.com` có tự chứng minh cert thuộc host đó không?

**Câu 14.** `HttpsURLConnection` mặc định có HTTPS hostname verification không?

**Câu 15.** Khi có private CA, nên đưa CA private key vào client truststore không?

**Câu 16.** Import một root CA nội bộ có thể mở rộng trust beyond một URL không?

**Câu 17.** Thấy `PKIX path building failed` cần kiểm yếu tố nào trước?

**Câu 18.** Thấy `No subject alternative name matching` cần kiểm yếu tố nào?

**Câu 19.** Java JSSE mặc định luôn bật revocation checking với mọi `TrustManagerFactory.init(KeyStore)` không?

**Câu 20.** Vì sao JDK update có thể làm một connection trước đó hoạt động nay bị từ chối?

**Câu 21.** Lab tạo hai root CAs để làm gì?

**Câu 22.** Lab tại sao dùng cùng TCP 127.0.0.1 nhưng hai reference names?

**Câu 23.** mTLS server có thể bỏ application authorization sau khi xác thực client certificate không?

**Câu 24.** Khi TLS handshake thất bại, nên tự động tắt verification và thử lại không?

**Đáp án:**

1. **Không**; CA trust PASS, identity FAIL.
2. **Từ chối**; tên đúng không thay trust path.
3. Không. Root làm trust anchor; leaf đại diện endpoint.
4. Tập default root CA certificates cho OpenJDK phù hợp.
5. Không.
6. CA trust hỏi chain đến trust anchor có hợp lệ không; endpoint identity hỏi server có đúng tên đích không.
7. Tạo trust managers dựa trên truststore và thuật toán.
8. Yêu cầu kiểm peer identity theo quy tắc HTTPS tại handshake.
9. Không; cần bật endpoint identification khi tự dùng raw socket.
10. Không, vì DNS SAN không phải IP SAN.
11. RFC 9525 yêu cầu SAN; CN fallback là cách tương thích cũ.
12. Không; nguy cơ MITM/host spoofing.
13. Không; SNI chỉ giúp server chọn certificate.
14. Có, với cấu hình HTTPS mặc định của SunJSSE/JDK.
15. Không; chỉ cần public CA certificate làm trust anchor.
16. Có, CA có thể cấp certificates cho nhiều tên hợp lệ.
17. Root/intermediate/truststore, chữ ký, validity và PKIX constraints.
18. Reference hostname/IP vs leaf SAN.
19. Không thể giả định; cần kiểm cấu hình revocation.
20. CA distrust, thuật toán bị cấm, truststore hoặc TLS defaults thay đổi.
21. Để kiểm trust chain FAIL độc lập với hostname FAIL.
22. Để transport giống nhau, chỉ thay danh tính cần xác minh.
23. Không; application authorization là bước riêng.
24. Không; phải fail-closed và sửa cấu hình/certificate theo nguyên nhân.

## 29. Tổng kết và nguồn chính thức

- **Cần đồng thời tin cậy CA/PKIX chain và xác minh server endpoint identity.**
- **CA trust PASS không đồng nghĩa hostname PASS**; hostname đúng cũng không sửa chain thiếu tin cậy.
- **Root CA là trust anchor**; intermediate phát hành theo constraints; leaf đại diện service có SAN phù hợp.
- **JEP 319 Java 10** bổ sung root CA certificates cho OpenJDK phù hợp, không làm mất hostname verification.
- **SAN dNSName và iPAddress khác nhau**; không coi DNS resolve cùng IP là cùng identity.
- **Không xây certificate mới dựa vào CN fallback**; tuân thủ RFC 9525.
- **SNI chỉ giúp chọn cert**, không thực hiện xác minh của client.
- **PKIX TrustManager + HTTPS endpoint identification** là hai thành phần tương thích trong Java JSSE.
- **HttpsURLConnection/HttpClient** có default HTTPS security; raw sockets cần tự chọn chính sách endpoint identification đúng.
- **Không dùng trust-all/always-true verifier.** Khi lỗi, sửa chain, trust anchors, SAN hoặc URL.
- **Private CA/truststore** cần được quản lý theo scope, key security, rotation và trust policies JDK hiện hành.
- Local JDK17+ lab đã cho kết quả: **đúng CA/đúng hostname → chấp nhận; đúng CA/sai hostname → từ chối; sai CA/đúng hostname → từ chối**.

**Nguồn học còn áp dụng:**

1. [JEP 319 — Root Certificates](https://openjdk.org/jeps/319): bối cảnh Java 10 và root CA certificates.
2. [Java 10 Consolidated Release Notes — JEP 319](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): thông tin phân phối root truststore.
3. [Oracle Java SE 26 — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): TLS certificate trust và endpoint verification theo socket/engine.
4. [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm`.
5. [Oracle Java SE 26 — SSLSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): handshake và TLS parameters.
6. [Oracle Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): truststores, PKIX, hostname verification.
7. [Oracle Java SE 26 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf): X509 trust managers và bảo vệ `cacerts`.
8. [Oracle Java SE 26 — keytool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): keystore, CSR, root certificates và PKCS12.
9. [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html): DNS-ID/IP-ID, SAN, wildcard và CN-ID.
10. [JDK Trust Management](https://ops.java/security/trust/): `cacerts`, default root CA và truststore semantics.
11. [Oracle Java SE 26 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS hostname verification.
12. [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): TLS HTTP client.
