# 15.6 Phân biệt tin chuỗi chứng thư với xác minh tên máy chủ

Khi ứng dụng Java kết nối HTTPS/TLS, hai câu hỏi bảo mật độc lập phải được trả lời đúng:

1. **Có tin được chuỗi chứng thư (certificate path/chain) này không?** Chứng thư máy chủ có nối tới một **trust anchor** mà client chủ động tin, với chữ ký, hiệu lực và ràng buộc chứng thư hợp lệ không?
2. **Chứng thư ấy có chứng minh danh tính của đúng máy chủ mà ứng dụng muốn kết nối không?** Tên tham chiếu từ URL/config (hostname hoặc IP) có khớp **Subject Alternative Name (SAN)** trên chứng thư theo quy tắc xác minh endpoint không?

Một chứng thư có chuỗi hợp lệ **vẫn có thể thuộc về một hostname khác**. Chỉ kiểm chuỗi nhưng bỏ kiểm tên biến một kênh TLS có mã hóa thành kênh **không xác thực đúng đối tác**. Ngược lại, chứng thư in đúng hostname nhưng do CA không được tin cấp cũng không hợp lệ. Một kết nối HTTPS an toàn phải thỏa **cả hai điều kiện**, cùng các kiểm tra về mục đích sử dụng khóa, chính sách TLS và trạng thái chứng thư theo yêu cầu.

Bài học đặt trong **15. Nền tảng TLS**, tập trung vào sự khác nhau giữa **trust chain** và **hostname verification**, cách Java/JSSE thực hiện, ví dụ Java 17+ chạy thực tế với CA nội bộ và SAN `DNS:localhost`, rồi rút ra checklist vận hành.

## 1. Mô hình tổng quan: “ai ký?” không đồng nghĩa “đúng ai?”

Giả sử ứng dụng gọi:

~~~text
https://payments.example.com/api/charge
~~~

Peer gửi một chứng thư có SAN `DNS:reports.example.com`, nhưng chứng thư được một CA đáng tin ký, hợp lệ về ngày tháng và đường dẫn PKIX. Nếu chỉ kiểm chữ ký/CA, client có thể tin **một chứng thư của hệ thống reports** để nói chuyện với **payments**.

Hai phép kiểm liên quan nhưng có đầu vào khác nhau:

~~~text
                  TLS handshake / peer certificates
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
        (A) PATH TRUST              (B) ENDPOINT IDENTITY
        certificate chain           intended hostname or IP
        signature/path policy       from URL/config/request
        trusted root                versus leaf SAN
                 |                           |
                 v                           v
           pass / fail                 match / mismatch
                 |                           |
                 +-------------+-------------+
                               |
                      both pass => accept
                   either fails => reject
~~~

**Phép A (path trust)** trả lời: “Theo trust anchors và chính sách đã cấu hình, public key/chứng thư này có nằm trong chuỗi tin cậy hợp lệ hay không?”

**Phép B (endpoint identity)** trả lời: “Danh tính được chứng thư leaf chứng nhận có khớp **tên đích mà ứng dụng định liên lạc** hay không?”

**Không thể đổi phép A thành phép B** bằng cách chỉ import thêm CA vào truststore. Cũng không thể đổi phép B thành phép A bằng cách viết hostname đúng vào CN/SAN của một chứng thư tự ký chưa được tin.

### 1.1. Bảng kết quả bốn tình huống

| Chuỗi chứng thư được tin | Tên máy chủ khớp | Quyết định |
| --- | --- | --- |
| Có | Có | Có thể chấp nhận sau các kiểm tra TLS/chính sách khác |
| Có | **Không** | **Từ chối**: certificate có thể hợp lệ cho một máy chủ khác |
| **Không** | Có | **Từ chối**: tên đúng nhưng certificate không được trust |
| **Không** | **Không** | **Từ chối**: cả hai điều kiện đều sai |

**“Có thể chấp nhận” không đồng nghĩa đã được phân quyền**: TLS xác thực endpoint theo chính sách, còn quyền sử dụng API/tài khoản/tenant vẫn là vấn đề authorization, token, mTLS identity mapping hoặc các bước ứng dụng khác.

## 2. Chuỗi chứng thư và trust anchor: công việc của PKIX

Chứng thư X.509 leaf có public key của server. Một certificate path thường là:

~~~text
server leaf: SAN DNS:api.example.com
      |
      | chữ ký được kiểm bằng public key của issuer
      v
issuing intermediate CA: BasicConstraints CA=true
      |
      v
root CA (trust anchor do client cấu hình)
~~~

Đối với phép kiểm đường dẫn, client cần đánh giá:

- **Chữ ký** giữa leaf, intermediates và trust anchor được phép tin. Chỉ so tên `Issuer DN` với `Subject DN` là **không đủ**; hai certificate khác khóa có thể dùng cùng chuỗi tên.
- **BasicConstraints** và `pathLenConstraint` ở chứng thư CA trung gian, cùng `KeyUsage keyCertSign` khi áp dụng.
- **NotBefore/NotAfter** và đồng hồ hiện tại; chứng thư hết hạn hoặc chưa có hiệu lực không tự trở nên hợp lệ vì CA đã được tin.
- **Thuật toán, cỡ khóa, signature constraints, certificate policies/name constraints** và cấu hình PKIX/TLS của môi trường.
- **Mục đích sử dụng leaf**: ví dụ EKU `serverAuth`/`clientAuth` theo vai trò khi có extension; `KeyUsage` tương ứng.
- **Thu hồi** (CRL/OCSP và chính sách revocation) khi yêu cầu; có một path hợp lệ về chữ ký không đồng nghĩa certificate chưa bị thu hồi.
- **Trust anchor được chọn sẵn** và nguồn gốc của nó; root tự ký không tự chứng minh đáng tin.

Trong Java, các lớp thường liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `KeyStore` | Lưu các entry, có thể làm identity keystore hoặc truststore |
| `TrustedCertificateEntry` | Chứng chỉ công khai mà quản trị viên chọn làm trust anchor/đầu vào trust policy |
| `TrustManagerFactory` | Khởi tạo trust manager từ một KeyStore hoặc cấu hình trust mặc định |
| `X509TrustManager` / `X509ExtendedTrustManager` | Kiểm certificate chain theo ngữ cảnh phiên TLS và provider/chính sách |
| `CertPathValidator("PKIX")` | API xác minh đường dẫn chứng thư theo tham số trust anchors/policy |
| `CertPathBuilder` | Hỗ trợ dựng certificate path qua intermediate/trust anchors nếu có dữ liệu phù hợp |
| `KeyManagerFactory` | Lấy private key + chain của **chính** ứng dụng khi nó làm server hoặc client mTLS |

**Chú ý ranh giới:** Kiểm path bằng `CertPathValidator("PKIX")` với `TrustAnchor` biết trước **không tự cung cấp tên hostname cần so**. Đây là phần A, không thay được phần B. Chương trình demo phần 9 cố ý cho PKIX pass và sau đó để HTTPS endpoint identification chứng minh hostname mismatch.

### 2.1. Truststore không phải “danh sách mọi hostname được phép”

Một truststore chứa root `Example Internal Root` có thể tin **rất nhiều leaf certificates** do CA đó hoặc intermediate của nó ký. Nếu leaf dành cho `hr.internal`, nó không được dùng thay leaf của `payroll.internal` chỉ vì có cùng CA.

**Trusting a CA is not pinning a host.** Pinning public key/certificate (nếu chính sách yêu cầu) là một cơ chế bổ sung có vòng đời/rotation phức tạp, không tự thay HTTPS hostname validation. Đặc biệt, tin một CA nội bộ có phạm vi cấp rất rộng mà bỏ hostname check là lỗi có mức độ ảnh hưởng lớn.

### 2.2. Root, intermediate và server gửi chuỗi gì?

Server TLS thường gửi **leaf và intermediate(s)** cần để dựng path; trust anchor root được client lưu sẵn (không nhất thiết gửi từ server). Nếu thiếu intermediate, client có thể không dựng được path, dẫn đến **path building failed**, dù leaf có SAN đúng.

Nếu server gửi cả root của mình, nó **không thể ép client tin root đó**. Client phải có trust anchor từ nguồn độc lập đã xác thực và chính sách của nó. Vì vậy “server gửi đầy đủ chain” và “client trust đúng CA” là hai trách nhiệm khác nhau.

## 3. Xác minh tên máy chủ (hostname verification) là phép kiểm khác

Hostname verification so sánh **reference identity** (tên mà ứng dụng dự định liên lạc) với **presented identity** trên **leaf X.509 certificate**.

Ví dụ:

~~~text
Đích theo URL:       https://api.example.com
Reference identity:  api.example.com

Leaf SAN:
  DNS: api.example.com
  DNS: api-backup.example.com

=> tên api.example.com khớp với một DNS SAN thích hợp
~~~

Một certificate hợp lệ cho `admin.example.com` không tự hợp lệ cho `api.example.com`. Việc server cầm private key và đã được CA ký chỉ chứng minh server sở hữu khóa của **một danh tính được CA chứng nhận**; cần bước so đúng danh tính đích.

### 3.1. Lấy tên tham chiếu từ đâu?

Đối với HTTPS, reference hostname thường lấy từ **hostname trong URL/endpoint được ứng dụng cấu hình** sau khi parse và canonicalize theo quy tắc giao thức, không lấy tùy ý từ:

- `Issuer DN` hoặc `Subject CN` của certificate server;
- `Host` header mà peer gợi ý khi đã kết nối;
- DNS PTR/reverse DNS của địa chỉ IP;
- SNI do server tự phản hồi;
- Tên alias trong `KeyStore`;
- Một tên mới do attacker trả về trong response hay redirect mà ứng dụng tự ý coi là tên cũ.

Ví dụ HTTPS client đang kết nối `https://api.example.com`; DNS có thể resolve sang `203.0.113.10`, nhưng reference identity vẫn là **api.example.com**, không phải IP mà DNS trả về. Nếu người dùng **cố ý** gọi `https://203.0.113.10`, reference identity là **địa chỉ IP literal** và phải theo quy tắc IP SAN.

**Nếu ứng dụng đi qua proxy, load balancer hoặc connect-by-IP nhưng mong danh tính DNS:** cần giữ đúng **logical peer host** lúc tạo TLS/HTTP client. `SSLSocketFactory.createSocket(tcp, "api.example.com", port, true)` có thể giữ peer hostname cho SNI và endpoint check khi transport socket đã được mở tới IP; điều này phải được thiết kế theo client API và chính sách kết nối, không chọn hostname theo certificate trả về.

### 3.2. SAN là nguồn danh tính chuẩn

`Subject Alternative Name` là extension X.509 cho nhiều loại danh tính:

| SAN type | Ví dụ | Khi nào được dùng |
| --- | --- | --- |
| `dNSName` (type 2) | `DNS:app.example.com` | Khi client xác minh tên DNS qua HTTPS |
| `iPAddress` (type 7) | `IP:192.0.2.10`, `IP:2001:db8::1` | Khi URL/endpoint dùng IP literal và chính sách TLS yêu cầu so IP |
| `uniformResourceIdentifier` (type 6) | `URI:spiffe://domain/service` | Giao thức workload identity riêng có quy tắc xác minh URI; **không mặc nhiên** thay HTTPS DNS hostname |
| `rfc822Name` | Email | Không dùng như DNS hostname cho HTTPS |

**Ví dụ đối chiếu:**

| Client yêu cầu | Leaf certificate chứa | Kết quả name check |
| --- | --- | --- |
| `https://localhost` | `DNS:localhost` | Khớp |
| `https://127.0.0.1` | Chỉ `DNS:localhost` | **Không khớp** vì thiếu `IP:127.0.0.1` |
| `https://127.0.0.1` | `IP:127.0.0.1` | Khớp về loại/tên, **nếu chain được trust** |
| `https://api.example.com` | `DNS:api.example.com` | Khớp |
| `https://api.example.com` | `DNS:other.example.com` | **Không khớp** |
| `https://api.example.com` | Chỉ `CN=api.example.com` | **Không nên dựa vào CN**, phải cấp SAN đúng |
| `https://192.0.2.10` | `DNS:192.0.2.10` | **Không thay IP SAN hợp lệ** khi yêu cầu IP literal |

**IP trong DNS SAN không tương đương iPAddress SAN.** Chỉ vì chuỗi có dấu chấm và số trông như IP, không thể nhập nó dưới type DNS rồi mong HTTPS IP matching chấp nhận.

### 3.3. Common Name (CN) và legacy fallback

Một số TLS implementations lịch sử có thể fallback sang `Subject CN` khi certificate không có DNS SAN phù hợp; quy tắc cụ thể thay đổi theo platform, phiên bản và chuẩn. **Không xem fallback đó là mục tiêu thiết kế**, không dựa vào CN để cấp hoặc đánh giá chứng thư HTTPS mới.

Với chứng thư server hiện đại, chủ động yêu cầu CA phát hành **SAN DNS/IP đúng loại và đúng hostname thực tế**. Nếu môi trường nào đó vẫn chấp nhận CN khi thiếu SAN, đó là behavior cần quản lý compatibility và hardening, **không chứng minh mọi client sẽ chấp nhận**.

### 3.4. Wildcard và IDN (tên quốc tế hóa)

- `DNS:*.example.com` chỉ nên được hiểu trong giới hạn wildcard mà client/protocol chấp nhận; **không tự suy ra** nó hợp lệ cho `example.com` hoặc `a.b.example.com`.
- `*.example.com` không phải cách cấp quyền không giới hạn cho mọi cấp subdomain. Các chuẩn/client có thể áp thêm ràng buộc về wildcard/public suffix.
- Tên IDN (có chữ ngoài ASCII) thường liên quan đến **IDNA/Punycode A-label**, normalization và so khớp không phân biệt hoa thường theo quy tắc DNS; **không tự dùng `String.equalsIgnoreCase`** để thay thuật toán chuẩn.
- URL, SNI, chứng thư SAN và thư viện HTTPS cần thống nhất cách biểu diễn tên; nếu ứng dụng phải tự xử lý ở tầng thấp, ưu tiên API chuẩn hoặc thư viện đã được kiểm thử interoperability.

**Không tự viết một hàm `hostnameMatches` ngây thơ** dùng `endsWith(".example.com")`, vì dễ có lỗi ranh giới label, wildcard, internationalized names hoặc confusion của chuỗi.

## 4. Vì sao PKIX hợp lệ vẫn không đủ cho HTTPS?

Có hai tình huống đặc biệt rõ:

### 4.1. CA đáng tin ký chứng thư cho hostname khác

~~~text
Truststore client:  Root CA R

Certificate X do R ký:
  Subject/SAN = DNS:files.example.com
  Validity    = còn hạn
  Signature   = hợp lệ

Client mong kết nối:
  https://payments.example.com

Path trust  = PASS (R được tin)
Name match  = FAIL (files != payments)
Decision    = REJECT
~~~

Nếu ứng dụng tắt name check, đối tượng bất kỳ được cấp certificate hợp lệ bởi một CA được tin (chẳng hạn CA nội bộ được phép cấp nhiều hostname) có thể bị nhầm thành đúng endpoint. TLS vẫn mã hóa tới peer, nhưng **peer không được xác nhận là đúng dịch vụ mục tiêu**.

### 4.2. Hostname đúng, CA không được tin

~~~text
Certificate tự ký:
  SAN DNS:payments.example.com
  Issuer = chính nó
  Signature có thể tự kiểm

Client truststore:
  KHÔNG tin public key/root của certificate này

Name match  = PASS về tên
Path trust  = FAIL về trust anchor
Decision    = REJECT
~~~

Một attacker có thể tự tạo chứng thư mang hostname bất kỳ. Bởi vậy **khớp SAN không thay chain trust**. Lỗi HTTPS chỉ hết đúng cách khi client được cấp trust anchors hợp lệ hoặc server triển khai chain từ CA được chấp nhận và chứng thư có đúng tên.

### 4.3. Không lẫn “bật TLS” với “xác thực đúng đối tác”

Một socket dùng TLS 1.3/cipher suite mạnh và có encryption **không đảm bảo** ứng dụng đang nói chuyện với bên mong muốn nếu bỏ CA validation hoặc hostname verification.

- **Trust-all certificate**: bỏ/qua mặt xác minh path trust.
- **HostnameVerifier luôn trả true** hoặc raw SSLSocket không cấu hình endpoint identification: bỏ/qua mặt name check.
- Hai cách **đều nguy hiểm**, nhưng là hai lỗi riêng. Sửa lỗi CA không đòi tắt hostname; sửa lỗi hostname không đòi trust-all.

## 5. Java/JSSE thực hiện hai phép kiểm ở đâu?

Các API Java có hành vi mặc định khác nhau; phải phân biệt **client HTTPS cấp cao** với **raw TLS socket**.

### 5.1. `HttpsURLConnection`

`javax.net.ssl.HttpsURLConnection` được thiết kế cho HTTPS và theo mặc định thực hiện xác minh certificate/trust và hostname với các cơ chế chuẩn (trừ khi ứng dụng thay custom trust manager/hostname verifier hoặc cấu hình không an toàn). Không viết:

~~~java
// PHẢN VÍ DỤ NGUY HIỂM - KHÔNG DÙNG
connection.setHostnameVerifier((host, session) -> true);
~~~

Điều đó biến hostname check thành “luôn chấp nhận”. Nó không phải cách sửa lỗi tên trên certificate. Nếu URL `https://api.example.com` mà server chỉ có SAN `DNS:localhost`, giải pháp đúng là **đề nghị cấp chứng thư cho api.example.com** hoặc sửa URL/đích theo yêu cầu đã xác thực.

Đừng thay `SSLSocketFactory` của `HttpsURLConnection` bằng factory trust-all. Cấu hình truststore đúng root CA và để client thực hiện endpoint verification theo API.

### 5.2. `java.net.http.HttpClient` (JDK 11+)

`HttpClient` hiện đại sử dụng TLS và thực hiện HTTPS endpoint verification theo cấu hình chuẩn. Bạn có thể cấu hình `SSLContext` dùng truststore nội bộ khi cần kết nối service có CA riêng, **không tạo X509TrustManager bỏ qua mọi lỗi**.

Lưu ý các JVM flags/thuộc tính nội bộ có thể tác động việc xác minh hostname ở những implementation cụ thể; **không dùng các switch “disable hostname verification” để fix production**. Dùng test HTTPS thực tế với đúng URL hostname và CA chain như môi trường deploy.

### 5.3. Raw `SSLSocket` và `SSLEngine`

**Điểm dễ mắc lỗi:** Tạo một raw `SSLSocket` hoặc `SSLEngine` với trust manager chuẩn **không có nghĩa HTTPS hostname checking tự bật**. Các API TLS thấp hơn không biết bạn đang thực hiện giao thức ứng dụng nào hoặc reference hostname nào cần so.

Khi dùng raw `SSLSocket` như HTTPS client và muốn áp dụng thuật toán endpoint identification của HTTPS:

~~~java
SSLSocket socket = /* client socket được kết nối đúng peer */;
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
~~~

**Đây chỉ là trích đoạn**, không phải class độc lập. Với `SSLEngine` cũng cần cấu hình `SSLParameters` phù hợp trước handshake, đồng thời bảo đảm engine có đúng peer host và peer port theo API.

`"HTTPS"` là tên endpoint-identification algorithm của JSSE, không phải chỉ định để `Cipher.getInstance` và không phải HTTP request header. Tên tham chiếu phải lấy từ **đích đáng tin mà ứng dụng đã chọn**, không từ một giá trị do server gửi ngược lại.

### 5.4. `TrustManagerFactory` khác `HostnameVerifier`

| API | Vai trò chính | Không nên hiểu nhầm |
| --- | --- | --- |
| `TrustManagerFactory.init(trustStore)` | Tạo trust manager trên tập trust anchors | **Không tự chọn tên hostname** của URL ở ứng dụng tùy ý |
| `X509TrustManager.checkServerTrusted` | API kiểm chứng trust/cert chain theo provider và ngữ cảnh; bản interface cơ bản không nhận hostname | Không tự viết “custom check chỉ path” rồi coi là hostname check |
| `X509ExtendedTrustManager` | Trust check có phiên bản theo socket/engine; có thể kiểm endpoint identity khi JSSE được cấu hình | Không được bypass bằng override tùy tiện |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Yêu cầu JSSE kiểm endpoint name theo HTTPS khi handshake | Không tự thêm trust anchor đang thiếu |
| `HttpsURLConnection` | HTTPS stack có hostname verification theo mặc định | Custom `HostnameVerifier` trả true là phá chính sách |
| `CertPathValidator("PKIX")` | Đánh giá certificate path theo policy | Không biết reference DNS/IP từ URL nếu không được bổ sung ở tầng phù hợp |

Một số triển khai JSSE đặt name check trong quá trình kiểm tin cậy theo ngữ cảnh socket/engine; phép kiểm có thể đi chung call stack với chain validation. **Về mặt an ninh chúng vẫn là hai điều kiện riêng**, không phải “một lần gọi hàm là chứng chỉ tự nhiên đúng hostname”.

### 5.5. `KeyManagerFactory` không thay `TrustManagerFactory`

- Server identity keystore chứa **PrivateKeyEntry** với private key + leaf/chain, để server chứng minh mình có private key tương ứng certificate.
- Client truststore chứa root/intermediate CA được chủ động chấp nhận cho path trust.
- `KeyManagerFactory` giúp server/client mTLS xuất trình identity của chính nó.
- `TrustManagerFactory` giúp bên **đang xác minh peer** đánh giá chứng thư đối tác.
- Reference hostname được xác định theo **đường kết nối**/endpoint, không theo alias hoặc tên CN trong server keystore.

Một file PKCS12 có thể chứa nhiều entry types nhưng **trách nhiệm và chính sách** của identity/trust vẫn phải tách bạch.

## 6. Chuẩn bị phòng thực hành: một CA được tin, một SAN DNS

Để thấy rõ phép A và B khác nhau, ta dùng một CA demo **tự tạo** (được client chủ động tin) và chứng thư server do CA đó ký với SAN chỉ gồm **`DNS:localhost`**.

Sau đó kết nối **cùng một server** qua loopback TCP `127.0.0.1`, nhưng đưa hai **reference identities khác nhau** cho TLS:

- `localhost` với `HTTPS` endpoint identification → **thành công**.
- `127.0.0.1` với `HTTPS` endpoint identification → **thất bại**, vì chứng thư **không có `IP:127.0.0.1`**.
- `127.0.0.1` **không bật** hostname identification → **thành công về chain**, nhưng **không an toàn để xác thực đúng đích**; chỉ là negative control trong bài lab.

**Cần:** JDK 17+, `keytool` và quyền tạo file trong thư mục thử nghiệm mới. **Không dùng keystore production**. Các lệnh bên dưới dùng password cố định mẫu trên command line để dễ tái hiện; với production password phải lấy từ secret manager/callback, không đặt trong Git, CI log, shell history hoặc process listing.

### 6.1. Tạo root CA local

~~~bash
keytool -genkeypair -alias demo-root -keyalg RSA -keysize 2048 -dname "CN=Local Demo Root,O=Learning,C=VN" -validity 7 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

CA demo có `BasicConstraints CA=true` và `KeyUsage keyCertSign`; đây **không phải** chứng thư được trình duyệt công cộng tin. RSA 2048 và hạn 7 ngày chỉ phục vụ lab; root CA production phải theo chính sách, bảo vệ private key CA (thường HSM) và có quy trình cấp/thu hồi chứng thư.

### 6.2. Xuất root CA certificate công khai

~~~bash
keytool -exportcert -alias demo-root -keystore ca.p12 -storepass demo-pass-123 -rfc -file root.crt
~~~

`root.crt` là certificate public, **không có private key CA**. Đối với CA thật, xác minh certificate fingerprint và provenance qua kênh tin cậy độc lập trước khi import.

### 6.3. Tạo private-key identity cho server

~~~bash
keytool -genkeypair -alias server-id -keyalg RSA -keysize 2048 -dname "CN=localhost,O=Learning,C=VN" -validity 7 -ext "san=dns:localhost" -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123 -keypass demo-pass-123 -noprompt
~~~

Ở bước này `server-id` chứa private key và self-signed placeholder. SAN DNS `localhost` là **điều cần so trong lab**; không có `IP:127.0.0.1`.

### 6.4. Tạo CSR từ đúng alias và CA ký leaf

~~~bash
keytool -certreq -alias server-id -file server.csr -rfc -keystore server.p12 -storepass demo-pass-123 -ext "san=dns:localhost"
~~~

~~~bash
keytool -gencert -alias demo-root -infile server.csr -outfile server-issued.crt -rfc -keystore ca.p12 -storepass demo-pass-123 -validity 7 -ext "san=dns:localhost" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

CSR PKCS#10 chứa public key, subject và requested extensions; private key **không được chuyển cho CA**. Lệnh `-gencert` tạo leaf thực tế với SAN DNS `localhost`, KU/EKU phù hợp lab. CA production phải kiểm quyền tên và chính sách cấp; không tự động ký mọi SAN mà CSR yêu cầu.

### 6.5. Cài CA certificate và phản hồi vào server KeyStore

~~~bash
keytool -importcert -alias demo-root -file root.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

~~~bash
keytool -importcert -alias server-id -file server-issued.crt -keystore server.p12 -storepass demo-pass-123 -noprompt
~~~

Lệnh thứ hai **cài certificate reply vào đúng PrivateKeyEntry alias `server-id`**. Private key vẫn ở server.p12; leaf/chain được cập nhật thành CA-issued certificate có chain về demo root.

### 6.6. Tạo client truststore chỉ chứa root certificate demo

~~~bash
keytool -importcert -alias demo-root -file root.crt -keystore trust.p12 -storetype PKCS12 -storepass demo-pass-123 -noprompt
~~~

`trust.p12` được client sử dụng để tin root của lab. **Không** đưa private key CA trong `ca.p12` sang client. Truststore được tạo bằng certificate đã có từ môi trường thực hành tin cậy; không tự thực hiện `-noprompt` cho root bất kỳ tải từ mạng.

### 6.7. Kiểm metadata trước khi chạy Java

~~~bash
keytool -list -v -alias server-id -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123
keytool -list -v -alias demo-root -keystore trust.p12 -storetype PKCS12 -storepass demo-pass-123
~~~

Cần nhìn thấy:

- `server-id` là `PrivateKeyEntry`, leaf SAN `DNSName: localhost`, issuer demo root và chain phù hợp.
- `demo-root` trong trust.p12 là `TrustedCertificateEntry`, không có private key CA.
- Leaf chỉ chứa **DNS SAN localhost**, không có **IP SAN 127.0.0.1**. Đây là **chủ ý** để test mismatch.

## 7. Java 17+ hoàn chỉnh: cùng CA tin cậy, khác kết quả tên

Lưu chương trình sau thành **`TlsNameCheckDemo.java`** trong cùng thư mục với `server.p12` và `trust.p12`. Chương trình chạy local loopback, không kết nối Internet.

### 7.1. Code

~~~java
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.InputStream;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class TlsNameCheckDemo {
    static KeyStore load(String filename, char[] password) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(filename))) {
            ks.load(in, password);
        }
        return ks;
    }

    static SSLContext serverContext(KeyStore server, char[] password)
            throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(server, password);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), null, new SecureRandom());
        return ctx;
    }

    static SSLContext clientContext(KeyStore trusted) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ctx;
    }

    static boolean connect(SSLContext client, int port,
                           String peerName, boolean hostnameCheck)
            throws Exception {
        // Kết nối vật lý luôn là 127.0.0.1; peerName thể hiện
        // DANH TÍNH LOGIC cần được chứng thư xác thực.
        Socket tcp = new Socket(InetAddress.getByName("127.0.0.1"), port);
        try (SSLSocket ssl = (SSLSocket) client.getSocketFactory()
                .createSocket(tcp, peerName, port, true)) {
            SSLParameters parameters = ssl.getSSLParameters();
            if (hostnameCheck) {
                parameters.setEndpointIdentificationAlgorithm("HTTPS");
            }
            ssl.setSSLParameters(parameters);
            ssl.startHandshake();
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        char[] password = "demo-pass-123".toCharArray();
        try {
            KeyStore server = load("server.p12", password);
            KeyStore trust = load("trust.p12", password);
            X509Certificate leaf = (X509Certificate)
                    server.getCertificate("server-id");
            X509Certificate root = (X509Certificate)
                    trust.getCertificate("demo-root");

            // PATH TRUST ĐỘC LẬP: kiểm leaf tới root được cấu hình.
            // Root là trust anchor, không đưa vào CertPath list.
            CertPath path = CertificateFactory.getInstance("X.509")
                    .generateCertPath(List.of(leaf));
            PKIXParameters pkix = new PKIXParameters(
                    Set.of(new TrustAnchor(root, null)));
            pkix.setRevocationEnabled(false); // Offline demonstration only!
            CertPathValidator.getInstance("PKIX").validate(path, pkix);
            System.out.println("PKIX trusted        = true");

            SSLContext serverTls = serverContext(server, password);
            SSLContext clientTls = clientContext(trust);
            try (SSLServerSocket listener = (SSLServerSocket)
                    serverTls.getServerSocketFactory().createServerSocket(
                            0, 10, InetAddress.getByName("127.0.0.1"))) {
                Thread responder = new Thread(() -> {
                    for (int i = 0; i < 3; i++) {
                        try (SSLSocket accepted =
                                (SSLSocket) listener.accept()) {
                            accepted.startHandshake();
                        } catch (Exception ignored) {
                            // Demo: client abort on hostname mismatch is expected.
                        }
                    }
                });
                responder.start();
                int port = listener.getLocalPort();

                System.out.println("HTTPS localhost     = " +
                        connect(clientTls, port, "localhost", true));

                boolean mismatchRejected = false;
                try {
                    connect(clientTls, port, "127.0.0.1", true);
                } catch (SSLHandshakeException expected) {
                    mismatchRejected = true;
                }
                System.out.println("HTTPS IP rejected   = " +
                        mismatchRejected);

                // DELIBERATELY UNSAFE: trust chain vẫn được kiểm,
                // nhưng endpoint name verification bị bỏ qua.
                System.out.println("Chain-only IP       = " +
                        connect(clientTls, port, "127.0.0.1", false));
                responder.join();
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

### 7.2. Biên dịch và chạy

~~~bash
javac TlsNameCheckDemo.java
java TlsNameCheckDemo
~~~

Đầu ra đã được kiểm chứng sau khi chạy đúng các lệnh `keytool` ở phần 6 trong **thư mục thử nghiệm rỗng**:

~~~text
PKIX trusted        = true
HTTPS localhost     = true
HTTPS IP rejected   = true
Chain-only IP       = true
~~~

**Diễn giải đúng các dòng output:**

1. `PKIX trusted = true`: leaf `server-id` được CA demo trong `trust.p12` ký và `CertPathValidator` chấp nhận path **trong điều kiện lab**. Lời gọi này **không kiểm hostname** và tắt revocation có chủ đích vì CA demo không có CRL/OCSP.
2. `HTTPS localhost = true`: client TCP tới loopback `127.0.0.1` nhưng **reference name** của TLS là `localhost`; leaf SAN `DNS:localhost` khớp; trust chain cũng hợp lệ, nên handshake thành công.
3. `HTTPS IP rejected = true`: client vẫn dùng **chính CA root ấy, chính server ấy, cùng TLS context**, nhưng reference name là IP literal `127.0.0.1`. Certificate chỉ có **DNS SAN**, không có `iPAddress SAN` đúng. JSSE từ chối qua `SSLHandshakeException` khi endpoint algorithm `HTTPS` được bật.
4. `Chain-only IP = true`: cùng IP và truststore nhưng **cố tình bỏ hostname check**, handshake thành công. **Dòng này mô phỏng anti-pattern để học**, không có nghĩa “an toàn”; nó chứng minh chain validation **không tự bảo đảm đúng endpoint**.

**Bí quyết của demo:** `createSocket(tcp, peerName, port, true)` giữ TCP connection tới `127.0.0.1` nhưng đưa tên logic `peerName` cho TLS khi kiểm endpoint identity. Việc **đổi tên logic** chỉ là bài kiểm khác biệt, **không phải cho ứng dụng tự tùy ý chọn tên mà server gợi ý**. Trong thực tế tên phải đến từ URL/config đã xác thực.

**Chương trình không in private key**; password demo được xóa ở mảng `char[]` do chương trình nắm giữ, nhưng literal/password trong dòng lệnh hoặc object của provider vẫn có thể để lại bản sao trong RAM/log. Không coi code sample là phương án lưu password production.

### 7.3. Tại sao chương trình không thực hiện HTTPS request thật?

`SSLServerSocket` chỉ tạo **local TLS handshake**, không triển khai HTTP parser hay gửi response; điều ta cần chứng minh là hai điều kiện xác thực ngay tại lớp TLS.

Một HTTPS client cấp cao có thể cũng làm URL parsing, redirects, hostname validation, connection reuse, proxy và nhiều cơ chế HTTP khác. Demo không mô phỏng toàn bộ những điều đó. Nó chỉ cho thấy sự độc lập giữa **PKIX trust** và **endpoint identification** bằng API JSSE chuẩn.

Ở nhánh mô phỏng không bật hostname check, server vẫn trình certificate có chữ ký CA, và `TrustManagerFactory` của client vẫn hoạt động. Do đó kết quả `Chain-only IP=true` là bằng chứng trực quan rằng **tin CA chưa đủ**.

### 7.4. Giới hạn an ninh của lab

- CA root và server cert được tạo trong môi trường bạn kiểm soát; không phải CA/public PKI thật.
- `PKIXParameters.setRevocationEnabled(false)` được đặt **chỉ để thử offline**. Khi triển khai thật, revocation policy và cách fail cần được quy định.
- Certificate SAN chỉ có localhost, thời hạn rất ngắn, password mẫu cố định; không phù hợp public HTTPS.
- `SSLSocket` không phải complete HTTPS/mTLS client; không chứng minh xử lý HTTP redirects, cookies, proxy, authorization hay session cache.
- Ngoài tên và chain, client vẫn cần thuật toán TLS mạnh, private key bảo mật, certificate usage phù hợp và chính sách hạn dùng/thu hồi.

## 8. Cách cấu hình đúng khi CA nội bộ và hostname không khớp

Giả sử công ty có CA nội bộ cấp chứng thư:

~~~text
Target URL: https://orders.internal.example
Server SAN: DNS:orders.internal.example
CA:        Company Issuing CA -> Company Root CA
~~~

Client phải thực hiện cả hai:

1. **Trust chain:** Nhận CA root phù hợp từ kênh quản trị đáng tin, kiểm fingerprint/chuỗi tin cậy, đưa vào client truststore hoặc cấu hình trust manager tương ứng; bảo đảm intermediate chain đầy đủ.
2. **Name match:** Truy cập qua `orders.internal.example` (đúng reference identity), certificate leaf có SAN phù hợp; giữ endpoint identification bật.

Nếu bạn cần truy cập qua IP trực tiếp, có hai lựa chọn thiết kế rõ ràng:

- **Dùng DNS name thực sự của endpoint** và để DNS/TCP route tới IP cần thiết; reference identity vẫn là hostname này.
- Nếu endpoint thật được định danh chính thức bằng IP literal, **phát hành certificate với iPAddress SAN đúng IP** và cấu hình ứng dụng kết nối theo IP đó, với trust chain hợp lệ.

**Không sửa bằng** `HostnameVerifier((host, session) -> true)`, `X509TrustManager.checkServerTrusted` rỗng, bật trust-all, hoặc chấp nhận tất cả hostname chỉ vì môi trường `dev`. Các cấu hình này thường bị copy vào staging/production và có thể dẫn tới MITM.

### 8.1. SNI không phải hostname verification

**Server Name Indication (SNI)** là extension trong TLS ClientHello để client báo hostname mong muốn, giúp một server có nhiều virtual hosts chọn certificate phù hợp.

- SNI hỗ trợ **server chọn** leaf certificate.
- **Hostname verification** là việc **client xác minh** certificate được chọn có tên khớp với endpoint mà client yêu cầu.
- Server thấy SNI đúng không đảm bảo nó trả chứng thư đúng; client vẫn phải kiểm chain và SAN.
- Với IP literal, hành vi gửi SNI khác nhau tùy API/triển khai; đừng dựa vào SNI để “cứu” chứng thư không có IP SAN.

SNI là tín hiệu định tuyến/chọn certificate, **không phải bằng chứng mật mã về danh tính server**.

### 8.2. DNS lookup, connection by IP và tên logic

Ứng dụng có thể resolve `api.example.com` sang `10.0.0.8` và mở TCP tới IP, nhưng reference identity vẫn `api.example.com`. Đây là mô hình bình thường.

Ngược lại, nếu ứng dụng chỉ dùng `https://10.0.0.8` và certificate chỉ có `DNS:api.example.com`, **không nên bỏ hostname check**; phải sửa cấu hình đích, cấp SAN IP đúng chính sách hoặc dùng DNS route.

**Cẩn thận:** Hostname trong HTTP `Host` header không tự cung cấp trust khi TLS handshake đã hoàn tất; attacker kiểm soát HTTP layer không được quyền “đổi” reference identity để hợp thức hóa cert đã được trình.

### 8.3. Redirects và connection reuse

HTTPS client có thể gặp redirect `Location: https://another.example.com/...`. Mỗi endpoint HTTPS mà client thực sự kết nối phải được xác minh với **hostname của endpoint đó** và trust chain hợp lệ.

Không lấy certificate cũ của endpoint A dùng để tin endpoint B mà bỏ hostname check. Với HTTP/2 connection coalescing hoặc pooling, client cấp cao phải thực hiện kiểm điều kiện bảo mật của các origins theo chuẩn/implementation; ứng dụng không tự bypass bằng cách chia sẻ raw socket không kiểm tên.

## 9. Phân biệt thông báo lỗi trong Java

Lỗi trust chain và lỗi hostname có thể cùng xuất hiện dưới `SSLHandshakeException` ở tầng ngoài, nhưng nguyên nhân sâu thường khác.

| Thông báo/triệu chứng điển hình | Kiểm tra đang thất bại | Cách khắc phục phù hợp |
| --- | --- | --- |
| `PKIX path building failed` | Không dựng được chain tới trust anchor chấp nhận | Kiểm truststore, root/issuer/intermediate, chain server gửi, policy |
| `unable to find valid certification path` | Không có path phù hợp trust policy | Đưa CA đúng nguồn vào truststore, cài đầy đủ intermediate |
| `No subject alternative DNS name matching ... found` | SAN DNS không khớp hostname | Cấp cert có DNS SAN đúng, hoặc sửa endpoint URL/config đúng |
| `No subject alternative names matching IP address ... found` | Thiếu `iPAddress SAN` khớp IP literal | Cấp IP SAN đúng khi dùng IP identity, hoặc dùng DNS endpoint chuẩn |
| `certificate expired` / `not yet valid` | NotAfter/NotBefore hoặc clock | Gia hạn certificate/điều chỉnh clock sau khi kiểm nguồn |
| `Extended key usage does not permit ...` | EKU không phù hợp mục đích TLS | CA phát hành leaf có EKU đúng profile |
| `Algorithm constraints check failed` | Khóa/signature/cipher bị policy/JDK từ chối | Cấp lại cert/key đạt policy, không tắt constraint bừa |
| `certificate revoked` | Revocation checker theo chính sách từ chối | Điều tra CA/revocation, xử lý key compromise theo quy trình |
| TLS handshake thành công nhưng client raw socket gọi sai hostname | Có thể **endpoint identification chưa bật** | Kiểm `SSLParameters`/client TLS stack và identity reference |
| Hết lỗi sau khi set `HostnameVerifier` luôn true | **Đã vô hiệu hóa name check**, không phải sửa cert | Bỏ bypass, sửa SAN/trust/URL theo nguyên nhân |
| Hết lỗi sau trust-all manager | **Đã vô hiệu hóa CA/path trust**, không phải sửa chain | Khôi phục trust manager chuẩn, cấp trust anchors đúng nguồn |

**Đừng bắt mọi `SSLHandshakeException` rồi retry với `SSLParameters` không có endpoint identification.** Một retry “nới lỏng bảo mật” khiến attacker có thể chủ động tạo lỗi đầu tiên rồi khiến lần sau bỏ xác minh. Nếu muốn log nguyên nhân, ghi exception class, đích URL/hostname đã cấu hình, certificate metadata đã lọc phù hợp, truststore version và policy; **không log private keys, passwords, session secrets hoặc token**.

### 9.1. Vì sao lỗi chain đôi khi che khuất lỗi tên?

Nếu server gửi certificate do CA không được trust, handshake có thể thất bại **trước khi đi đến name check**, nên bạn chỉ nhìn thấy lỗi path. Sau khi sửa truststore đúng cách, bạn mới thấy hostname mismatch. Đây không phải “sửa A gây lỗi B” mà là **hai điều kiện đã không được thỏa mãn từ đầu**.

Chiến lược chẩn đoán: xác định reference hostname/IP; kiểm chain và SAN của leaf độc lập; không tắt một kiểm tra để tìm lỗi kia trong hệ thống đang phục vụ request thật.

## 10. Kiểm tra certificate SAN/chain khi điều tra

Các thao tác kỹ thuật hữu ích trong môi trường được phép:

~~~bash
# Đọc leaf và chain đã lưu trong PKCS12:
keytool -list -v -alias server-id -keystore server.p12 -storetype PKCS12 -storepass demo-pass-123

# Đọc root được client trust trong lab:
keytool -list -v -alias demo-root -keystore trust.p12 -storetype PKCS12 -storepass demo-pass-123

# Đọc certificate leaf đã được CA ký:
keytool -printcert -file server-issued.crt -v
~~~

Ở production, tránh đặt `-storepass` trực tiếp trên command line; dùng phương pháp nhập credential an toàn theo công cụ và môi trường. Không dùng `-noprompt` để tự thêm CA root chưa xác minh.

Nếu bạn được phép kiểm server công khai/ngoại tuyến, `openssl s_client` có thể quan sát chain nhưng **phải hiểu flags**: lệnh chỉ in certificates chưa chắc đã thực hiện hostname verification; các flag như `-verify_hostname`/`-verify_ip` cùng trust CA/policy phải được cấu hình rõ nếu cần kiểm tên. Không lấy `Verify return code: 0` trong một phiên s_client chưa cấu hình hostname verification như bằng chứng tất cả HTTPS checks đã pass.

### 10.1. Không dùng `CN` hoặc alias để sửa lỗi SAN

Nếu `keytool -list` cho thấy:

~~~text
Alias: backend-key
Owner: CN=api.example.com
SubjectAlternativeName:
  DNSName: old.example.com
~~~

Không thể coi CN đúng là đủ cho mọi client, đặc biệt khi DNS SAN hiện diện nhưng **không khớp reference hostname**. Cần CA cấp certificate đúng SAN. Alias `backend-key` không phải DNS name của TLS endpoint và không cấp thêm quyền trust.

### 10.2. Kiểm đúng truststore thực sự được client dùng

Java runtime có thể dùng **truststore mặc định** (ví dụ `cacerts` tùy JDK/distribution) hoặc **truststore riêng** qua JSSE config. Việc import root vào một file mà ứng dụng **không sử dụng** không thay đổi trust decision.

Kiểm cấu hình runtime/container thực tế: đúng file/path, type, password, permissions, process restart/reload và client library có dùng SSLContext đó hay không. Đừng sửa global JVM security properties chỉ để giải quyết một endpoint, nếu một `SSLContext` truststore riêng có thể đáp ứng policy và phạm vi hẹp hơn.

**Thêm root vào truststore phải là quyết định bảo mật có kiểm soát**; nếu root bị cấp quyền quá rộng, mọi endpoint leaf do root đó cấp có thể pass path trust, làm hostname verification càng quan trọng.

## 11. HTTPS, mTLS và danh tính ở hai chiều

Trong HTTPS thông thường, **client xác minh server**. Trong mTLS, **server cũng xác minh chứng thư client**.

~~~text
HTTPS:
  Client --> kiểm chain server + hostname server của URL
  Server --> trình private key + certificate chain

mTLS:
  Client --> vẫn kiểm chain server + hostname server
  Server --> kiểm chain client + clientAuth/identity policy
  Application --> ánh xạ identity client sang quyền cụ thể
~~~

Các nguyên tắc:

- mTLS **không miễn cho client** bước hostname verification của server. Nếu client trust CA nhưng bỏ name check, vẫn có nguy cơ kết nối nhầm service hợp lệ khác.
- Server mTLS thường xác minh client certificate chain tới CA được chấp nhận, mục đích `clientAuth` và **identity được cấp quyền** (ví dụ SAN URI/DNS subject theo policy). Server không “xác minh hostname server” khi kiểm client; nó phải xác định và phân quyền **client identity** theo chính sách.
- Một SAN URI workload identity như SPIFFE có quy tắc xác minh/mapping riêng, không được nhầm với phép kiểm HTTPS DNS name.
- Nếu một CA ký nhiều certificate cho nhiều dịch vụ, server cần **authorization policy** để quyết định identity client nào được phép gọi API, không chỉ “do CA công ty ký là cho truy cập tất cả”.

Trong TLS server nhận client cert, chain trusted chưa đồng nghĩa user là admin. Trong TLS client xác minh server, hostname khớp và chain trusted cũng chưa đồng nghĩa response thuộc đúng tenant hoặc có quyền thực hiện tác vụ ứng dụng.

## 12. Certificate cho localhost/dev/staging/production

**Vì sao dev hay tắt hostname checking?** Chứng thư được cấp cho `dev.example.com` nhưng truy cập bằng `localhost`, `127.0.0.1` hoặc IP container nên mismatch.

Cách làm đúng:

- Nếu môi trường dev dùng `https://localhost`, tạo chứng thư dev với **`DNS:localhost`** và CA dev chỉ được trust trong phạm vi dev.
- Nếu dev client truy cập `https://127.0.0.1`, chứng thư cần **`IP:127.0.0.1`**; có `DNS:localhost` không đủ.
- Nếu staging dùng `staging-api.example.test`, cấp chứng thư có SAN phù hợp, không copy certificate `api.example.com` rồi tắt kiểm tên.
- Nếu production có load balancer/ingress, certificate tại **TLS termination point** phải khớp URL hostname mà client gọi. Kết nối LB→backend riêng cũng cần chính sách TLS/xác thực endpoint phù hợp nếu được bảo vệ bằng TLS.
- Khi chạy container, hostname service trong DNS của cluster có thể khác hostname công khai; phải thiết kế rõ **reference identity của từng kết nối** và SAN/CA tương ứng.

**Không chia sẻ CA dev root cho môi trường production** trừ khi có quy trình rõ ràng, vì trust rộng có thể cho phép certificates dev được nhận ở production. Hạn chế CA/truststore theo từng security domain và dùng rotation có kiểm soát.

## 13. Những lỗi bảo mật phổ biến

| Sai lầm | Điều thực sự hỏng | Cách sửa |
| --- | --- | --- |
| “Chuỗi chứng thư được CA đáng tin ký ⇒ đúng server” | Bỏ endpoint name binding | Kiểm SAN với reference hostname/IP |
| “Có `CN=api.example.com` ⇒ mọi client đều chấp nhận” | CN fallback không đủ/không ổn định | CA cấp SAN DNS/IP đúng |
| “DNS:127.0.0.1 giống IP:127.0.0.1” | Sai SAN type | Dùng `iPAddress` SAN cho IP literal |
| “Import root mới rồi hostname lỗi thì tắt name check” | Chấp nhận sai đối tác | Sửa URL/hostname hoặc xin cấp cert đúng SAN |
| “Server gửi root thì client phải trust nó” | Bỏ mô hình trust anchors | Truststore được quản lý từ nguồn tin cậy |
| “CertPathValidator pass là HTTPS verified” | PKIX path không biết URL host | HTTPS hostname identification riêng |
| “Raw SSLSocket với truststore mặc định tự check host” | Có thể không bật endpoint identification | `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` |
| “Chỉ cần `SSLSession.isValid()` để check identity” | Session còn hiệu lực không chứng minh hostname đúng | Endpoint check lúc handshake/connection policy |
| “Dùng `HostnameVerifier` trả true để vượt lỗi” | Vô hiệu hóa name check | Dùng verifier mặc định, cấp cert phù hợp |
| “Trust-all X509TrustManager cho dev là vô hại” | Vô hiệu hóa path trust, dễ tràn vào production | Tạo CA dev riêng, truststore giới hạn |
| “Hostname lấy từ certificate peer” | Attacker quyết định tên đích thay ứng dụng | Dùng hostname từ URL/config tin cậy |
| “SNI đã đặt đúng nên certificate không cần SAN” | SNI chỉ giúp chọn certificate | Client vẫn xác minh SAN |
| “Kết nối tới IP của api.example.com thì chỉ kiểm IP” | Mất identity DNS dự định | Giữ reference hostname của URL |
| “mTLS có CA nội bộ ⇒ không cần authorization” | Tất cả leaf client cùng CA có thể được chấp nhận | Mapping identity→quyền, EKU/role checks |
| “Bỏ revocation vì path valid rồi” | Certificate bị thu hồi vẫn có thể được dùng | Áp revocation policy đúng threat model |
| “Một máy kiểm thành công ⇒ mọi máy trust” | Truststore/JDK/policy khác nhau | Test từng runtime/client được hỗ trợ |

**Anti-pattern nghiêm trọng:** Không tạo `HostnameVerifier` luôn trả `true`, không cài `X509TrustManager` không kiểm chứng, không retry handshake bằng chế độ “allow insecure”. Đây không phải các bản sửa tạm vô hại mà **vô hiệu hóa xác thực** trong TLS.

## 14. Kiểm thử ứng dụng và CI

Một bộ test tốt cần hai nhóm đầu vào **độc lập**:

### 14.1. Test path trust

1. Leaf do CA được client tin ký, chain đầy đủ ⇒ path pass.
2. Leaf do CA không được tin ký ⇒ path fail.
3. Thiếu intermediate ⇒ path building fail nếu client không có cách dựng chain hợp lệ.
4. Intermediate không có `CA=true`/`keyCertSign` cần thiết ⇒ path fail.
5. Cert expired/not-yet-valid ⇒ fail.
6. Signature/certificate algorithm bị policy cấm ⇒ fail.
7. Revoked certificate ⇒ fail khi revocation policy yêu cầu.

Không làm test bằng cách tắt hostname verification rồi kết luận ứng dụng an toàn; path tests riêng là một tầng kiểm thử kỹ thuật, còn integration test cần bật cả hai điều kiện.

### 14.2. Test endpoint identity

1. Trusted leaf SAN `DNS:localhost`, reference `localhost` ⇒ pass.
2. Cùng leaf và CA, reference `127.0.0.1` nhưng thiếu IP SAN ⇒ fail.
3. Trusted leaf SAN `IP:127.0.0.1`, reference IP đúng ⇒ pass.
4. Trusted leaf SAN `DNS:files.example.com`, reference `payments.example.com` ⇒ fail.
5. Cert chỉ có CN nhưng không có SAN tương ứng ⇒ không chấp nhận dựa vào CN fallback như yêu cầu test production.
6. Wildcard ở cấp sai hoặc hostname ngoài phạm vi wildcard ⇒ fail.
7. Trường hợp IDN/Punycode, case/label và canonicalization ⇒ được xác minh bằng HTTPS library chuẩn.
8. SNI/virtual hosting chọn certificate khác ⇒ endpoint checker bắt được nếu SAN không khớp.

**Một test rất có giá trị:** Cùng CA/truststore, cùng TCP endpoint, chỉ thay **reference identity** ⇒ một trường hợp pass và một trường hợp fail như chương trình phần 7. Nó cho phép phát hiện cấu hình client “trust chain only” trước khi deploy.

### 14.3. Test các HTTPS client thực tế

Ngoài raw socket lab, chạy integration test với API sẽ deploy thật: `HttpsURLConnection`, `HttpClient`, OkHttp/Apache HttpClient, Netty hoặc framework service. Kiểm cấu hình SSLContext, truststore, proxy, redirects, SNI và hostname verification. Nếu framework có option disable hostname verification, CI/policy nên từ chối cấu hình đó ở môi trường có dữ liệu thật.

**Không kiểm bằng mắt qua certificate Subject.** Hãy kiểm handshake với hai reference identities cụ thể, log kết quả pass/fail và không xuất private key/session secrets.

## 15. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Một leaf có SAN `DNS:billing.example.com`, CA hợp lệ và không hết hạn. Client gọi `https://pay.example.com`. Có được chấp nhận không?

**Đáp án:** **Không.** Path trust có thể pass nhưng reference hostname `pay.example.com` không nằm trong SAN phù hợp. Cần certificate đúng tên hoặc URL/đích đúng chính sách.

**Câu 2.** Leaf SAN đúng `DNS:api.example.com` nhưng certificate tự ký và client không tin root. Có thể chấp nhận vì hostname khớp không?

**Đáp án:** **Không.** Name match không thay phép kiểm chain/trust anchor. Cần CA/truststore phù hợp và xác thực nguồn tin cậy.

**Câu 3.** `DNS:localhost` có hợp lệ khi ứng dụng gọi `https://127.0.0.1` không?

**Đáp án:** **Không** theo HTTPS IP literal matching: cần SAN loại `iPAddress` khớp `127.0.0.1`, hoặc gọi bằng DNS `localhost` nếu đó là tên đích mong muốn.

**Câu 4.** Vì sao `CertPathValidator.getInstance("PKIX").validate(...)` thành công chưa chứng minh đúng server?

**Đáp án:** Nó xác minh certificate path theo trust anchors/chính sách được cấp; không có reference hostname từ URL cho bài toán HTTPS endpoint identification. Cần kiểm SAN/hostname riêng qua HTTPS/JSSE.

**Câu 5.** Một raw `SSLSocket` dùng TrustManagerFactory chuẩn và TLS 1.3, nhưng không gọi `setEndpointIdentificationAlgorithm("HTTPS")`. Có chắc HTTPS hostname đã được kiểm không?

**Đáp án:** Không. Raw socket có thể chỉ kiểm certificate trust chain. Phải cung cấp peer name đúng và bật endpoint identification theo giao thức, hoặc dùng HTTPS client cấp cao đã làm việc này.

**Câu 6.** SNI chứa `api.example.com`; server trả certificate `DNS:other.example.com`. Có thể chấp nhận vì SNI đúng không?

**Đáp án:** Không. SNI chỉ giúp chọn certificate; client vẫn phải xác minh SAN của certificate trả về khớp reference identity.

**Câu 7.** Import một CA root bất kỳ từ email vào truststore để xử lý `PKIX path building failed` có an toàn không?

**Đáp án:** Không. Root/CA phải được xác minh nguồn và fingerprint từ kênh tin cậy; nếu tin CA giả, attacker có thể cấp certificate cho endpoint mục tiêu.

**Câu 8.** mTLS server có chain client certificate hợp lệ từ CA nội bộ. Như vậy mọi client certificate cùng CA được quyền làm admin?

**Đáp án:** Không. Server còn cần mapping certificate identity (và EKU/policy) sang quyền được phép của từng client/service. Trust không tự cấp quyền ứng dụng.

**Câu 9.** Một chứng thư có `CN=api.example.com` nhưng SAN `DNS:old.example.com`. Client gọi `api.example.com` nên xử lý thế nào?

**Đáp án:** Không dựa vào CN để ghi đè SAN đã được phát hành; cần certificate có SAN tương ứng với tên đích. Quy tắc fallback legacy có thể khác nhưng không phải đường triển khai an toàn hiện đại.

**Câu 10.** Java lab in `PKIX trusted = true` và `HTTPS IP rejected = true` có mâu thuẫn không?

**Đáp án:** Không. Phép kiểm CA/path và phép kiểm endpoint name độc lập. Leaf trusted cho `localhost` nhưng **không hợp lệ cho IP literal `127.0.0.1`**.

**Câu 11.** Tại sao hostname không nên lấy từ reverse DNS của IP TCP connection?

**Đáp án:** Vì reference identity phải là đích mà ứng dụng muốn kết nối (URL/config), còn reverse DNS không phải bằng chứng rằng chứng thư được cấp cho chính đích đó; có thể sai hoặc bị kiểm soát theo threat model.

**Câu 12.** Tắt `HostnameVerifier` để “khắc phục” lỗi TLS có thể tạo lỗ hổng gì?

**Đáp án:** Chấp nhận certificate tin cậy nhưng thuộc một hostname khác, dẫn tới kết nối nhầm peer và có nguy cơ MITM. Cần sửa SAN/URL/truststore đúng nguyên nhân, không disable verify.

**Câu 13.** Server có đúng leaf và intermediate, nhưng client vẫn báo untrusted. Nguyên nhân nào còn có thể xảy ra?

**Đáp án:** Truststore client không tin root, algorithm policy không chấp nhận chain, certificate hết hạn, bị thu hồi hoặc ràng buộc PKIX khác thất bại. Server gửi root không tự khiến client chấp nhận nó.

**Câu 14.** Tại sao demo đặt `pkix.setRevocationEnabled(false)` nhưng không nên sao chép điều đó vào production?

**Đáp án:** Demo CA offline không có CRL/OCSP; tắt revocation để bài thử nghiệm có kết quả ổn định, **không phải tiêu chuẩn an toàn mặc định**. Production cần xác định cơ chế revocation và failure policy đúng nghiệp vụ/threat model.

## 16. Checklist cho ứng dụng Java TLS

- [ ] Xác định **reference hostname/IP từ URL/config tin cậy** trước khi handshake, không lấy từ certificate server.
- [ ] Kiểm certificate **path/chain tới root trust anchor được chủ động tin**; không trust-all và không tự thêm root chưa xác minh.
- [ ] Kiểm leaf **SAN đúng type**: DNS host dùng dNSName, IP literal dùng iPAddress; không dùng CN/alias thay SAN.
- [ ] Với raw `SSLSocket`/`SSLEngine`, bật **`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`** khi thực hiện HTTPS endpoint identity checks.
- [ ] Với `HttpsURLConnection`/`HttpClient`, giữ hostname verification mặc định; không cài custom verifier luôn true.
- [ ] Đảm bảo SNI/virtual hosting chọn certificate phù hợp **và vẫn kiểm tên** client-side.
- [ ] Kiểm chain đầy đủ/issuer signature, thời hạn, BasicConstraints, KU/EKU, algorithm constraints và revocation policy.
- [ ] Đừng dùng server-sent root làm lý do trust; truststore và CA policy phải có provenance độc lập.
- [ ] Khi hostname mismatch, **cấp lại SAN đúng hoặc sửa endpoint name**; không tắt verify để “hết lỗi”.
- [ ] Khi client truy cập IP literal, dùng IP SAN; khi client truy cập DNS host, giữ DNS reference dù TCP kết nối tới IP resolved.
- [ ] Tách TLS authentication khỏi authorization/token/tenant; với mTLS còn kiểm client identity và quyền.
- [ ] Test cả **trusted wrong-host** và **correct-host untrusted**, cùng kiểm chính sách CA/revocation.
- [ ] Không log password/private key/session secret; quản lý key/truststore/rotation và quan sát lỗi handshake an toàn.
- [ ] Có test trên chính **client API/JDK/framework phiên bản sẽ deploy**, vì raw TLS và HTTPS clients có defaults khác nhau.

## 17. Tổng kết

**Tin chuỗi chứng thư** và **xác minh tên máy chủ** giải quyết **hai câu hỏi khác nhau**. PKIX/trust manager xác định certificate path có dẫn tới trust anchor được chấp nhận, còn hostname verification đối chiếu **tên đích mà client chủ định** với **SAN phù hợp trên leaf**. Có chứng thư từ CA đáng tin chỉ chứng minh danh tính **được CA cấp trong certificate**, không có nghĩa đúng hostname bạn gọi. Trong Java, HTTPS clients cấp cao thường có cơ chế hostname verification mặc định; với raw `SSLSocket/SSLEngine` bạn cần chủ động thiết lập endpoint identification khi dùng cho HTTPS. Ví dụ JDK 17+ cho thấy rõ: **PKIX pass, localhost pass, IP mismatch bị từ chối, nhưng chain-only bỏ name check lại pass và không an toàn**.

Tài liệu nền tảng để đọc sâu: [RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), [RFC 6125 — service identity verification](https://www.rfc-editor.org/rfc/rfc6125), [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525), và [Java 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html).
