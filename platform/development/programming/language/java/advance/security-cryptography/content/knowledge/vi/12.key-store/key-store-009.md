# 12.9 Phạm vi của cacerts, kho tin cậy riêng và tác động khi thay đổi tập CA được tin

Khi ứng dụng Java gọi một dịch vụ HTTPS, nó không thể chỉ kiểm tra rằng “server có gửi một chứng thư X.509”. Ứng dụng phải quyết định **chứng thư đó có được tin cậy theo chính sách của kết nối hay không**, thường thông qua một đường chứng thư (*certificate path*) nối tới một **trust anchor** được cấu hình. Đối với Java, tập trust anchor thường đến từ **truststore**. Trong nhiều JDK, truststore mặc định có liên quan đến file `cacerts`; nhưng tên “mặc định” không đồng nghĩa một file `cacerts` cố định cho mọi process, mọi thư viện mạng hoặc mọi bản phân phối Java.

Bài này phân biệt ba tầng:

1. **`cacerts`**: kho chứng thư CA được phân phối/quản lý cùng một Java runtime, thường là nguồn mặc định cho JSSE nếu không có cấu hình ưu tiên khác.
2. **Kho tin cậy riêng của ứng dụng** (*application-specific truststore*): một tập trust anchor do ứng dụng hoặc môi trường chỉ định; có thể thay hoặc, nếu thiết kế rõ ràng, kết hợp với nguồn mặc định.
3. **Phạm vi tác động của thay đổi tập CA đáng tin**: thêm/xóa root hoặc intermediate CA làm thay đổi kết nối nào có thể xác thực được, mở rộng/thu hẹp bề mặt tin cậy và ảnh hưởng tới triển khai, rollback, TLS/mTLS và vận hành.

**Điểm quan trọng:** thêm một CA vào truststore không làm server “an toàn hơn” một cách tự động; nó **cấp thêm quyền được xét là nguồn tin cậy** trong các điều kiện kiểm chứng. Xóa CA không nhất thiết làm mọi phiên kết nối hiện hữu lập tức ngắt, nhưng có thể khiến **những TLS handshake mới** thất bại. Vì vậy, sửa CA store phải được đối xử như một thay đổi chính sách bảo mật có kiểm thử, audit và phương án rollback.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **truststore**, **keystore**, **trusted certificate entry**, **key entry** và **trust anchor** trong Java.
2. Biết `cacerts` thường nằm ở đâu, Java runtime/provider nào thực sự đọc nó, và khi nào không được giả định nó được sử dụng.
3. Phân biệt nguồn trust mặc định của JSSE với kho tin cậy riêng được chỉ định bằng `javax.net.ssl.trustStore` hoặc `SSLContext` / `TrustManagerFactory`.
4. Hiểu **custom truststore có thay thế hay hợp nhất với public roots**: mặc định không tự union tập CA chỉ vì đặt một file mới.
5. Phân tích tác động khi **thêm, loại bỏ, thay thế hoặc thu hẹp tập root/intermediate CA**, gồm nguy cơ chấp nhận đối tác không mong muốn hoặc làm đứt kết nối.
6. Tách **xác minh certificate chain** khỏi **hostname/SAN matching**, certificate usage, thuật toán, revocation, quyền nghiệp vụ và mTLS client authentication.
7. Tạo một trust manager riêng bằng Java 17+, không cần sửa `cacerts`, và kiểm tra test chứng thư/đường tin cậy theo policy.
8. Có quy trình vận hành để thay truststore an toàn trong container/Kubernetes, đa JDK, ứng dụng chạy dài hạn và những kết nối đang giữ trong pool.

## 2. Những đối tượng dễ bị nhầm

Một truststore Java thường là `KeyStore` (định dạng PKCS12 hoặc JKS tùy file/runtime) được dùng để tìm những **chứng thư được tin cậy**. Một keystore cho **danh tính TLS của chính ứng dụng** có thể chứa private key kèm certificate chain. Hai loại thường dùng cùng API `KeyStore` nhưng mục đích khác nhau.

| Khái niệm | Công dụng | Có private key không? | Dùng trong TLS để làm gì? |
| --- | --- | --- | --- |
| **Truststore** | Chứa certificate/trust anchor để kiểm peer | Thường không cần | `TrustManager` kiểm chain của phía đối diện |
| **`cacerts`** | Nguồn root CA mặc định trong nhiều runtime JDK | Thông thường là các trusted cert entries | Nguồn CA được runtime/JSSE dùng khi được cấu hình làm mặc định |
| **Identity keystore** | Chứa private key và certificate chain của local endpoint | Có thể có | `KeyManager` trình certificate và dùng private key khi cần |
| **TrustedCertEntry** | Một certificate được lưu trong `KeyStore` dưới alias | Không | Có thể làm trust anchor tùy cách trust manager nạp |
| **PrivateKeyEntry** | Private key cùng certificate chain | Có | Phục vụ local identity cho TLS hoặc signing |
| **Trust anchor** | Điểm kết thúc đường chứng thư mà verifier đã tin theo policy ngoài băng | Không cần private key của anchor | PKIX chấp nhận chain nếu mọi điều kiện và trust anchor phù hợp |
| **Intermediate CA** | CA cấp chứng thư dưới một root/CA khác | Certificate public của intermediate; private key giữ riêng | Xây dựng chain; không nhất thiết cần cài như trust anchor |
| **Leaf/end-entity certificate** | Certificate của server/client cụ thể | Bản certificate không chứa private key | Xác minh peer và tên/mục đích sử dụng |

**Truststore không phải nơi “để lấy khóa AES”**: nó thường quản lý các certificate dùng để xác thực peer. **`cacerts` không phải nơi lưu private key của HTTPS server**; private key của server có thể ở identity keystore/HSM/KMS. Một file PKCS#12 có thể chứa cả key và certificate entries, nhưng ý nghĩa khi được nạp phụ thuộc vào `KeyManagerFactory` hay `TrustManagerFactory`, không chỉ extension `.p12`.

### Định nghĩa “tin CA” có phạm vi

Một CA trusted có thể được xem là trust anchor khi xây dựng chain phù hợp. Tuy nhiên điều kiện chấp nhận leaf còn phụ thuộc:

- Đường chứng thư hợp lệ theo thuật toán/path-building và các ràng buộc hiện hành.
- Thời hạn, Basic Constraints, Key Usage và Extended Key Usage thích hợp; algorithm/key-size constraints.
- Endpoint identification: kết nối đến DNS/IP **đúng** tên trong Subject Alternative Name (*SAN*) của leaf.
- Revocation policy, distrust policy hoặc các hạn chế riêng của runtime/ứng dụng nếu được cấu hình.
- Trust anchor nào được phép cho **mục đích** kết nối đó và theo tenant/environment nào.

Vì vậy, có một CA trong truststore **không tự** cấp quyền truy cập API, cho phép mọi certificate của CA làm server certificate, hay chứng minh một request có quyền đọc dữ liệu.

## 3. `cacerts` nằm ở đâu và thuộc phạm vi nào?

Đối với JDK hiện đại, vị trí thường gặp là:

```text
<java.home>/lib/security/cacerts
```

Ví dụ nếu Java được cài ở `/opt/jdk-17` thì file có thể là `/opt/jdk-17/lib/security/cacerts`. Trên máy có nhiều JDK/JRE/container image, **mỗi runtime có thể có tập CA khác nhau**. Đường dẫn thật còn phụ thuộc package/vendor, symbolic link và cơ chế tích hợp CA của hệ điều hành.

Để quan sát runtime đang chạy:

```bash
java -XshowSettings:properties -version
```

Trong output, tìm thuộc tính `java.home` và kiểm cách cấu hình launcher/provider. Dùng `java` đúng đường dẫn mà ứng dụng production chạy; việc terminal sử dụng một JDK khác với service (hoặc một container image khác) rất phổ biến.

Để liệt kê chứng thư trong store mặc định được lệnh `keytool` của JDK chỉ định nhận diện:

```bash
keytool -list -cacerts
```

`keytool` có thể hỏi mật khẩu để kiểm tính toàn vẹn; không nhập password quản trị thật lên command line hoặc chia sẻ output chứa thông tin không cần thiết. Lệnh chỉ phản ánh **`cacerts` của JDK đi cùng `keytool` đang được chạy**, không xác nhận mọi Java process khác đang dùng chính file ấy.

### Tác động của bản phân phối Java và hệ điều hành

Không có một danh sách CA bất biến gọi là “bộ CA Java”. Runtime JDK có thể mang một tập root riêng, nhận cập nhật root store từ vendor, hoặc liên kết với hệ điều hành trong một số bản đóng gói. Container image được build ở thời điểm khác có thể có root store khác, kể cả nếu ứng dụng cùng version.

Hệ quả thực tế:

- Một service chạy JDK A tin certificate chain X, service chạy JDK B có thể từ chối X.
- Cập nhật JDK/container base image có thể thay tập CA được tin mà **không thay mã nguồn ứng dụng**.
- Sửa `cacerts` của máy host chưa chắc ảnh hưởng process đang dùng JDK trong container.
- Sửa file khi process đã khởi tạo `SSLContext`/trust manager không đảm bảo những kết nối mới tự dùng tập CA mới; thường cần **tạo lại trust manager/SSLContext, thay connection pool hoặc restart có kiểm soát**.
- Một thư viện có TLS stack/native store riêng có thể không dùng JSSE truststore.
- Đừng suy đoán từ `java -version` trên terminal nếu deployment dùng image/dịch vụ khác; cần quan sát đúng artifact và process.

**Không sửa `cacerts` làm lựa chọn mặc định** cho một đối tác duy nhất. Việc thêm CA vào JDK-wide truststore có thể mở rộng tin cậy của nhiều client trong cùng runtime và ảnh hưởng các ứng dụng khác nếu dùng chung JDK. Tốt hơn là tạo **truststore riêng có scope rõ**, hoặc client-specific `SSLContext`.

## 4. JSSE chọn truststore như thế nào?

Với SunJSSE trong OpenJDK/Oracle JDK thông dụng, khi tạo default trust manager (`TrustManagerFactory.init((KeyStore) null)`), cơ chế tìm nguồn trust thường xét:

1. Nếu có cấu hình `javax.net.ssl.trustStore`, dùng truststore được chỉ định (cùng type/password/provider phù hợp).
2. Nếu không được chỉ định, có thể ưu tiên file `jssecacerts` trong thư mục security của runtime nếu tồn tại.
3. Nếu không có `jssecacerts`, thường dùng `cacerts`.
4. Nếu không có tập trust anchor khả dụng, việc xác thực TLS có thể thất bại vì không tìm được path tới CA tin cậy.

**Đây là mô hình áp dụng cho nhiều JSSE provider/JDK phổ biến, không phải cam kết mọi Java runtime hay mọi HTTP client.** Tên file ưu tiên, khả năng load, system properties, cách tích hợp OS store và các trường hợp file không tồn tại/phân quyền lỗi có thể khác theo provider/phiên bản. Với một SunJSSE implementation, đặt `javax.net.ssl.trustStore` trỏ tới file không có thật có thể dẫn đến truststore trống hoặc lỗi load, **không nên giả định fallback an toàn về `cacerts`**.

Các thuộc tính liên quan:

| Cấu hình | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `javax.net.ssl.trustStore` | Đường dẫn truststore cho JSSE default trust | Có thể **thay** tập CA mặc định thay vì bổ sung |
| `javax.net.ssl.trustStoreType` | Kiểu keystore, ví dụ `PKCS12` hoặc `JKS` | Phải phù hợp file/provider |
| `javax.net.ssl.trustStorePassword` | Mật khẩu khi tải/kiểm tính toàn vẹn truststore | Command-line system property có thể lộ qua process args/log |
| `javax.net.ssl.trustStoreProvider` | Provider đọc store khi cần | Không tùy tiện chọn provider chưa kiểm tương thích |
| `javax.net.debug` | Debug TLS handshake/trust processing | Dùng có giới hạn, log có thể lộ metadata nhạy cảm |
| `java.security.debug` | Một số luồng debug security/certpath | Không bật quá rộng ở môi trường production |

Có thể cấu hình JVM lúc khởi động theo ý tưởng:

```text
-Djavax.net.ssl.trustStore=/etc/app/trust/outbound.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Đây là **ví dụ các tùy chọn JVM**, không phải lệnh độc lập cần chạy. Phải cung cấp cơ chế mở/kiểm integrity file theo chính sách, chẳng hạn secret manager và code tạo `SSLContext`. Đừng đặt plaintext password bằng `-Djavax.net.ssl.trustStorePassword=secret` trên command line vì có thể lộ qua công cụ giám sát process và log.

### Truststore riêng có tự cộng thêm root công khai của `cacerts` không?

**Thông thường không.** Nếu chỉ đặt một file custom qua `javax.net.ssl.trustStore`, JSSE mặc định sẽ lấy tập trust từ file đó cho default trust manager theo provider/config. Nếu file chỉ chứa CA của đối tác, các HTTPS call tới website công khai khác có thể **không còn** xây dựng được chain tới public CA vì những root này không nằm trong kho mới.

Đừng xem “custom truststore” = “cacerts + một CA”. **Hợp nhất hai bộ tin cậy là một quyết định kiến trúc riêng**, không phải hiệu ứng mặc định của một property.

Có những chiến lược khác nhau:

- **Replace:** custom store chỉ chứa CA cho mục đích cụ thể, dùng trong một `SSLContext` của client. Đây là lựa chọn có scope hẹp, dễ audit.
- **Curated bundle:** một file chứa tập approved public roots + private CA cần thiết, quản lý tập đó như một artifact có version. Tác động có thể rộng nếu cấu hình JVM-wide.
- **Composite trust manager có kiểm soát:** kết hợp hai trust managers, nhưng phải định nghĩa chính xác điều kiện OR/AND, thuật toán/hostname/revocation, xử lý lỗi, môi trường sử dụng và scope. Không tự ghép code “thử trust manager này, fail thì manager kia” nếu chưa security-review.
- **Per-client contexts:** outbound client A dùng public CAs; client B dùng private CA. Tránh làm rộng policy của tất cả outbound connections.

Hợp nhất không phải lúc nào cũng tốt: nếu một client chỉ được phép nói chuyện với một đối tác private CA, tự thêm toàn bộ public roots sẽ **mở rộng** tập certificate chains được xét đáng tin.

## 5. Phân biệt truststore mặc định, truststore riêng, và identity keystore

Xét một Java service gọi ra ngoài tới hai đích:

```text
Java service
   |
   +-- Public HTTPS API
   |       uses SSLContext A -> approved public root CAs
   |
   +-- Internal HTTPS API
           uses SSLContext B -> private CA / tightly scoped trust
```

Nếu service còn nhận kết nối HTTPS/mTLS:

```text
Inbound server side:
  KeyManager -> private key + certificate chain của chính server
  TrustManager -> certificate CAs mà server tin khi xác thực client mTLS

Outbound client side:
  KeyManager -> client identity nếu endpoint yêu cầu mTLS
  TrustManager -> CA/path của HTTPS server phía đối diện
```

**Đừng nhập hai vai trò vào một**. Việc thêm root CA vào **client truststore** không tự làm server gửi certificate mới hoặc tạo client certificate. Việc nạp private key vào identity keystore không tự làm client tin một CA trên endpoint đích.

Ở server mTLS, truststore dùng để xác thực **client certificates** có thể nên chứa riêng những issuing CAs được phép. Nếu vô tình cho toàn bộ public WebPKI roots làm trust anchors của mTLS client auth, phạm vi client certificate được chấp nhận có thể rộng hơn mong muốn; vẫn cần mapping identity/authorization, nhưng tốt nhất thu hẹp trust roots ngay từ đầu.

### Scope của một JSSE SSLContext

- **JVM default:** properties và `SSLContext.getDefault()` có ảnh hưởng rộng tới những thư viện thực sự dùng default context.
- **Client-specific:** một `SSLContext` mới được cấu hình từ `TrustManagerFactory` riêng và gắn vào HTTP/TLS client cụ thể. Phạm vi thay đổi rõ hơn.
- **Provider/native TLS:** không phải tất cả thư viện mạng đều dùng JSSE. Cần kiểm tài liệu runtime/client.
- **Long-lived process:** thay file truststore không buộc các manager/context đã init cập nhật tự động. Version, reload/refresh và connection-pool lifecycle phải được thiết kế.

Ứng dụng có thể ghi audit về fingerprint/version của **trust bundle**, số CA và thời điểm load; tránh in đầy đủ chứng thư hoặc key material vào log nếu không cần.

## 6. Root CA, intermediate CA, leaf certificate và trust anchor

Đường chứng thư thường như sau:

```text
Root CA [trusted anchor installed/configured]
   |
   +-- Intermediate CA [signed by root]
          |
          +-- HTTPS server leaf [signed by intermediate]
                 +-- DNS SAN = service.example.test
                 +-- appropriate serverAuth purpose
```

Trong chain thông thường, **chỉ root CA** cần làm trust anchor; server gửi leaf và intermediate(s), hoặc path builder tìm intermediate từ nguồn thích hợp. Không mặc định phải import mọi intermediate vào truststore. Nếu server thiếu intermediate, sửa cấu hình **certificate chain của server** thường hợp lý hơn là thêm intermediate thành trust anchor trên mọi client.

**Root vs intermediate:** Khi đưa intermediate trực tiếp vào tập trust anchor, bạn có thể thay đổi trust model: intermediate được tin theo cách khác với việc chỉ chấp nhận nó dưới root và các kiểm tra của chain. Ràng buộc extensions đối với trust anchor có thể được xử lý khác với CA nằm trong chứng thư chain, tùy implementation và chính sách. Chỉ anchor một intermediate nếu bạn hiểu **phạm vi trust** và đã kiểm các ràng buộc cần thiết.

**Leaf pinning:** Import một leaf certificate vào trustedCertEntry có thể giống cách tin trực tiếp certificate đó đối với một số validator, nhưng **không phải thay thế toàn diện** cho certificate pinning, expiry management, hostname validation và revocation policy. Khi leaf renew, pin/truststore có thể phải cập nhật. Một số TLS stack có semantics riêng đối với trust anchor được cấu hình làm leaf.

### Chain validation khác hostname verification

Một certificate được public CA ký hợp lệ cho `api-a.example.test` **không được** chấp nhận cho `api-b.example.test` chỉ vì CA là trusted. Hostname/IP phải được kiểm đối chiếu SAN theo chính sách HTTPS/TLS.

- `X509Certificate.getPublicKey()` chỉ lấy public key; không kiểm trust.
- `X509Certificate.verify(issuerKey)` kiểm chữ ký với key đã cung cấp; không kiểm đầy đủ chain/trust/hostname.
- `CertificateFactory` parse certificate, không tự quyết định certificate được tin.
- `CertPathValidator` với `PKIXParameters` có thể thực hiện kiểm path phù hợp cấu hình; hostname kiểm theo endpoint identification riêng.
- Với `HttpsURLConnection` hoặc `java.net.http.HttpClient` cấu hình chuẩn, dùng chức năng xác minh tên máy chủ của TLS stack; không tắt nó để “sửa” lỗi certificate.
- Với `SSLSocket` tự quản, có thể cần cấu hình `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` đúng ngữ cảnh; đừng giả định việc cài trust manager đã bật hostname verification ở mọi socket API.

Một TLS handshake thành công vẫn không quyết định **authorization** của request; service phải kiểm quyền/tenant và ngữ cảnh nghiệp vụ riêng.

## 7. Thêm một CA: tác động và vùng tin cậy mở rộng

Giả sử ứng dụng trước đây tin CAs `A` và `B`; bạn nhập thêm CA `C` vào truststore mà một client dùng để xác thực server:

```text
Before: trusted anchors = {A, B}
After:  trusted anchors = {A, B, C}
```

Nếu CA C có thể phát hành certificate phù hợp tên máy chủ và policy, client đó có thể xác thực một chain mới trước đây bị từ chối. **Điều này có thể đúng mục đích** (kết nối đối tác private PKI) nhưng đồng thời mở rộng những bên có khả năng cấp certificate được xét hợp lệ.

Tác động cần phân tích:

1. **Blast radius:** Có áp dụng cho một HTTP client cụ thể, một JVM, một host, toàn cluster hay nhiều service?
2. **Tên miền/identity:** CA mới có thể cấp cho những DNS nào? Có name constraints được thực thi và application-level allowlist không?
3. **Nguồn chứng thư:** CA root được lấy từ kênh độc lập đáng tin nào? Fingerprint SHA-256 có được đối chiếu ngoài kênh vận chuyển file không?
4. **Mục đích:** Đây là CA dùng cho server TLS, client mTLS, code signing hay mục đích khác? Truststore dùng đúng phạm vi chưa?
5. **Mức độ rủi ro:** Nếu CA bị compromise hoặc governance yếu, attacker có thể lợi dụng để tạo chain hợp lệ cho endpoint mà client gọi (nếu các điều kiện khác như SAN/hostname cũng khớp).
6. **Vòng đời:** CA mới có expiry, rotation, revocation mechanism và chủ thể vận hành rõ ràng không?
7. **Rollback:** Nếu CA mới không nên tin nữa, có thể loại bỏ nhanh và khiến các context/pool liên quan nạp lại chính sách không?
8. **Môi trường:** Dev/staging CA có vô tình xuất hiện trong production truststore không?

**Không “sửa lỗi PKIX” bằng cách import mọi certificate gặp trên mạng.** Trước tiên xác định vấn đề thật: thiếu intermediate, sai chain, hostname khác, certificate hết hạn, hệ thống đồng hồ sai hay public root không nằm trong runtime.

### Một CA có thể ảnh hưởng nhiều hostname

Một root CA được tin trong client WebPKI nói chung có khả năng tạo đường tin cậy cho các hostname khác nhau khi chứng thư được cấp đáp ứng quy tắc/constraint. Thêm CA vào truststore dùng toàn JVM có thể **mở rộng cả các kết nối không liên quan tới đối tác được thêm**.

Giới hạn TCP hostname đích, xác thực tên máy chủ và application authorization giúp giảm rủi ro, nhưng chúng không thay thế việc **thu hẹp tập trust anchor** cho client chỉ cần kết nối một domain nội bộ.

## 8. Xóa hoặc thay thế CA: nguy cơ mất kết nối

Giả sử chain server trước đây xây dựng tới CA A. Khi CA A bị xóa khỏi truststore:

- **TLS handshake mới** có thể thất bại với lỗi kiểu `PKIX path building failed`, `unable to find valid certification path` hoặc `SSLHandshakeException` tùy provider và nguyên nhân.
- Nếu vẫn có **một đường chứng thư khác hợp lệ** tới anchor B được tin, handshake có thể tiếp tục thành công; không mặc định “xóa A chắc chắn mọi kết nối tới server X đều fail”.
- Các connection pool, TLS session resumption hoặc kết nối TLS đã thiết lập có thể **không lập tức** áp policy mới. Để thay chính sách nhanh, cần đánh giá đóng pool/reload context/restart và giới hạn session lifetime.
- Một số ứng dụng chạy custom `SSLContext` nạp truststore lúc khởi động sẽ không thấy thay đổi file cho đến khi được reload.

**Root CA rollover** thường cần một giai đoạn overlap:

```text
T0: client tin OldRoot; server trình chain tới OldRoot
T1: phân phối trust bundle {OldRoot, NewRoot}
T2: server chuyển sang chain tới NewRoot
T3: xác minh không còn client quan trọng cần OldRoot
T4: loại OldRoot theo risk/retention policy và kiểm hậu kiểm
```

Nếu xóa OldRoot trước khi client và server được cập nhật đồng bộ, có thể gây outage. Nếu giữ OldRoot quá lâu, bạn kéo dài trust đối với một CA không còn cần thiết hoặc đã có rủi ro. **Overlap phải có thời hạn và inventory**, không phải để hai root tồn tại mãi.

### Cross-sign và alternate path

Một certificate của intermediate hoặc root có thể được cross-sign, tạo nhiều đường path. Việc bạn xóa một root không phải lúc nào loại được mọi đường hợp lệ qua một root khác. Do đó, test phải dùng **chain thực tế, hostname, algorithm policy và truststore chính xác trên từng client/runtime**, thay vì chỉ so sánh số lượng CA entries.

### Khi bị nghi compromise CA

Trong một security incident, ưu tiên containment và distrust nhanh có thể quan trọng hơn duy trì mọi kết nối. Tuy nhiên cần đánh giá mức ảnh hưởng, thay CA/chain, cập nhật client trust, bảo vệ identity và log, thông báo đối tác, giám sát handshake. Việc chỉ xóa một root mà server vẫn dùng chain cũ sẽ dẫn đến outage nếu chưa xử lý luồng trust migration.

## 9. Tạo truststore riêng bằng keytool, không sửa trực tiếp cacerts

Quy trình minh họa cho **một private CA của đối tác**:

### 9.1 Nhận CA và xác minh nguồn gốc

Bạn nhận file `partner-root.pem` qua kênh đã được kiểm soát. Kiểm fingerprint SHA-256 và metadata certificate:

```bash
keytool -printcert -file partner-root.pem
```

Đây là bước **kiểm tra**, chưa phải tạo trust. Fingerprint cần đối chiếu với giá trị được xác nhận **qua kênh độc lập đáng tin**, ví dụ trang chính thức/đầu mối bảo mật đã được xác minh, thay vì chép fingerprint từ cùng email có thể đã bị sửa. Kiểm subject/issuer, Basic Constraints CA, key usage, thời hạn, thuật toán và phạm vi sử dụng phù hợp.

### 9.2 Import vào một file ứng dụng riêng

```bash
keytool -importcert -alias partner-root-2026 \
  -file partner-root.pem \
  -keystore app-outbound-trust.p12 \
  -storetype PKCS12
```

Các dấu `\` cuối dòng là cú pháp shell kiểu POSIX; trên Windows PowerShell, nhập thành một dòng hoặc dùng cú pháp tiếp dòng phù hợp. Công cụ có thể yêu cầu tạo/nhập password và xác nhận chứng thư. **Không dùng `-noprompt` chỉ để tránh kiểm nguồn tin cậy.** Đừng đưa mật khẩu vào `-storepass password` trên shell history/process arguments.

Kiểm lại:

```bash
keytool -list -v -keystore app-outbound-trust.p12 \
  -storetype PKCS12 -alias partner-root-2026
```

File vừa tạo chứa **một tập tin cậy do bạn chọn**, không tự chứa tất cả public CAs của `cacerts`. Nếu bạn cần public roots, thiết kế rõ ràng client nào dùng nguồn nào và cách duy trì approved bundle; không tự ghép không kiểm soát.

### 9.3 Triển khai

- Đặt file trong đường dẫn chỉ ứng dụng và người vận hành có quyền đọc, ví dụ mounted Secret/ConfigMap tùy chính sách; truststore chứa certificate công khai nhưng **tính toàn vẹn cấu hình rất quan trọng**, nên hạn chế người có quyền sửa.
- Version artifact, ghi fingerprint/certificate inventory và đường dẫn source-of-truth. Có review thay đổi CA và change window.
- Không commit password hoặc private key vào repository.
- Cấu hình đúng JDK/runtime chạy ứng dụng; chỉ định `trustStoreType` nếu có khả năng runtime khác default.
- Chạy test handshake với endpoint thật **sử dụng chính app trust manager** và kiểm hostname; không chỉ `keytool -list`.
- Có kế hoạch rollover certificate/CA và rollback nếu endpoint outage.
- Nếu custom store cần chứa public roots, nó phải được cập nhật theo lịch và chính sách distro/vendor, không copy `cacerts` một lần rồi quên nhiều năm.

## 10. Java 17+: tạo TrustManager và SSLContext có phạm vi riêng

Ví dụ độc lập minh họa **ranh giới phạm vi tin cậy** mà không cần kết nối mạng và không sửa `cacerts`. Nó lấy default trust manager từ provider, tạo một PKCS#12 KeyStore **rỗng trong RAM**, sau đó (nếu JDK có default anchors) thêm đúng một certificate được chọn từ default issuers để chứng minh custom manager chỉ nạp certificate đã thêm.

**Chú ý:** việc demo lấy phần tử đầu của danh sách public CAs là cách tạo input test từ runtime, **không phải chính sách lựa chọn CA cho ứng dụng thật**. Production phải chọn CA theo danh tính/fingerprint được xác minh độc lập, không theo vị trí trong mảng hoặc tên issuer đơn thuần. Chương trình cũng **không thực hiện TLS handshake**, nên không chứng minh hostname, PKIX hoặc revocation của endpoint nào.

Lưu thành **`TrustScopeDemo.java`**:

```java
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public class TrustScopeDemo {
    private static X509TrustManager firstX509(TrustManager[] managers) {
        for (TrustManager manager : managers) {
            if (manager instanceof X509TrustManager) {
                return (X509TrustManager) manager;
            }
        }
        throw new IllegalStateException("No X509TrustManager");
    }

    private static X509TrustManager trustManagerFor(KeyStore store)
            throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(store);
        return firstX509(factory.getTrustManagers());
    }

    public static void main(String[] args) throws Exception {
        // null means the configured/provider default trust source, not
        // necessarily a single fixed cacerts file on every Java runtime.
        X509TrustManager defaults = trustManagerFor(null);
        X509Certificate[] defaultIssuers = defaults.getAcceptedIssuers();

        KeyStore isolated = KeyStore.getInstance("PKCS12");
        isolated.load(null, "only-a-demo".toCharArray());
        X509TrustManager emptyManager = trustManagerFor(isolated);
        System.out.println("Custom empty entries: " + isolated.size());
        System.out.println("Custom empty accepted issuers: " +
                emptyManager.getAcceptedIssuers().length);

        if (defaultIssuers.length == 0) {
            System.out.println("Import demonstration skipped: no default CA");
            return;
        }

        // DEMO ONLY: do not select a production trust anchor by array position.
        isolated.setCertificateEntry("demo-ca", defaultIssuers[0]);
        X509TrustManager scoped = trustManagerFor(isolated);

        SSLContext clientContext = SSLContext.getInstance("TLS");
        clientContext.init(null, new TrustManager[] {scoped},
                new SecureRandom());

        System.out.println("Custom entries after import: " + isolated.size());
        System.out.println("Custom accepted issuers after import: " +
                scoped.getAcceptedIssuers().length);
        System.out.println("TLS context initialized: " +
                (clientContext.getSocketFactory() != null));
        System.out.println("Separate trust manager objects: " +
                (defaults != scoped));
        System.out.println("Default issuer list unchanged: " +
                (defaults.getAcceptedIssuers().length == defaultIssuers.length));
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac --release 17 TrustScopeDemo.java
java TrustScopeDemo
```

**Stdout chính xác trong môi trường thử nghiệm có default CA roots:**

```text
Custom empty entries: 0
Custom empty accepted issuers: 0
Custom entries after import: 1
Custom accepted issuers after import: 1
TLS context initialized: true
Separate trust manager objects: true
Default issuer list unchanged: true
```

Nếu runtime không có bất kỳ default CA được công bố trong `getAcceptedIssuers()`, hai dòng đầu vẫn xuất hiện, sau đó chương trình in `Import demonstration skipped: no default CA` và kết thúc. Đây là khác biệt môi trường được xử lý có chủ đích, không phải test secret hoặc lỗi TLS.

### Phân tích từng bước

1. `TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())` lấy implementation theo provider. `factory.init((KeyStore) null)` chọn nguồn trust **mặc định đã cấu hình**, không chứng minh đã mở đúng file `cacerts` cụ thể.
2. `KeyStore.getInstance("PKCS12")` + `load(null, ...)` tạo một keystore mới **rỗng trong RAM**. Nó không sửa `cacerts`, không ghi file và không làm default JSSE đổi trạng thái.
3. Khởi tạo factory với empty custom store cho `getAcceptedIssuers().length == 0` trong môi trường/provider đã thử nghiệm. Một trust manager không có trust anchor sẽ không được dùng như client trust policy cho public web.
4. `setCertificateEntry("demo-ca", certificate)` thêm **đúng một** certificate vào custom KeyStore. Tạo `TrustManagerFactory` mới nạp đúng nguồn này; nó không tự lấy union tất cả public CAs.
5. `clientContext.init(null, new TrustManager[] {scoped}, ...)` thiết lập một SSL context riêng dùng trust manager được chọn, không thay đổi `SSLContext.getDefault()`.
6. `getSocketFactory() != null` cho biết context đã khởi tạo, **không** chứng minh kết nối tới hostname bất kỳ đã được xác thực. Test mạng/cert chain/hostname là việc khác.
7. `defaults != scoped` minh họa hai đối tượng trust manager độc lập. `Default issuer list unchanged` kiểm rằng code không sửa state của manager ban đầu; nó không đánh giá CA trust của hệ thống ngoài.

Một số JDK có default truststore bị cấu hình rỗng hoặc `javax.net.ssl.trustStore` trỏ tới một file riêng. Vì vậy **số lượng root mặc định không cố định** giữa các máy hoặc build; ví dụ chỉ in các thuộc tính kiểm tra ổn định trên môi trường đã thử.

### Tạo SSLContext từ truststore file thật

Ví dụ sau là **đoạn minh họa trong method**, không phải chương trình độc lập. Giả sử `char[] password` được lấy an toàn từ secret manager và `Path path` trỏ tới file `PKCS12` được duyệt:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(path)) {
    store.load(input, password);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(store);

SSLContext scopedContext = SSLContext.getInstance("TLS");
scopedContext.init(null, tmf.getTrustManagers(), null);
```

Đoạn này không cài JVM-wide truststore. `password` là biến nhạy cảm, cần dọn dẹp khi có thể và không log. `KeyStore.load` với null password có semantics integrity-check tùy định dạng/provider; hãy dùng đúng password và policy thay vì mặc định file có thể được tải “không cần bảo vệ”.

`scopedContext` chỉ có tác dụng với client/socket **thực sự được cấu hình dùng nó**. Chẳng hạn Java `HttpClient` hỗ trợ builder với `.sslContext(scopedContext)`; nếu bạn tạo context rồi không gắn vào HTTP client, các request vẫn có thể dùng default context.

**Lưu ý endpoint verification:** trust manager xác minh chain nhưng hostname vẫn phải được kiểm theo TLS API. Java `HttpClient`/HTTPS client thông thường có cơ chế endpoint identification, trong khi một raw `SSLSocket` có thể cần cấu hình `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`. Không tắt hostname verification, không dùng “trust all” để chữa chain lỗi.

## 11. Thay đổi root CAs có ảnh hưởng TLS đang hoạt động ngay không?

Không nên giả định một sự kiện “thay file truststore” có tác dụng tức thì với toàn bộ process. Có nhiều tầng cache/state:

- **File truststore:** cập nhật file trên disk.
- **`KeyStore` object trong JVM:** đã load certificate entries tại một thời điểm.
- **`TrustManagerFactory` / `X509TrustManager`:** đã init trên một tập trust anchors nhất định.
- **`SSLContext`:** đã init với các trust managers, key managers và session caches.
- **Connection pool / TLS session:** các TCP/TLS connection đã handshake trước đó có thể được tái sử dụng.
- **Process/container:** có thể chưa reload file/config sau khi cập nhật secret mount.

Thay CA ở file **không** bảo đảm tất cả các tầng trên thay đổi ngay. Một thiết kế reload đúng thường:

1. Nhận diện version mới và kiểm tính toàn vẹn của trust bundle.
2. Tải keystore mới vào bộ nhớ, xác minh các certificates/anchors dự kiến.
3. Tạo lại `TrustManagerFactory` và `SSLContext` theo cấu hình mới.
4. Cấu hình client/connection pool mới và chuyển traffic theo cơ chế an toàn.
5. Đóng hoặc quay vòng pool/session cũ theo threat model, đặc biệt khi **thu hồi trust** khẩn cấp.
6. Theo dõi handshake metrics, canary health, rollback với phiên bản đã duyệt.

`SSLContext` không có API “sửa một CA trong mọi connection đang tồn tại” theo nghĩa chung. Cần hiểu lifecycle của HTTP/TLS library cụ thể và xem liệu session resumption có dùng lại trạng thái xác thực cũ hay không.

## 12. Kiểm tra certificate chain và hostname trong production

Sau khi có truststore, phải kiểm **TLS kết nối thực tế** với endpoint theo đúng hostname/SNI và chain:

| Kiểm tra | Câu hỏi |
| --- | --- |
| Trust anchor | Certificate chain có kết thúc ở một anchor được policy chấp nhận? |
| Path building | Intermediate(s) có đầy đủ, path constraints và signature hợp lệ? |
| Validity | Các certificate trong chain có đáp ứng thời hạn theo policy? |
| Algorithm | Algorithm/key size có nằm trong danh sách cho phép của runtime và ứng dụng? |
| ServerAuth/EKU | Leaf có mục đích phù hợp để làm TLS server? |
| SAN/hostname | Endpoint DNS/IP có khớp danh tính được cấp trong certificate? |
| Revocation/distrust | Có yêu cầu OCSP/CRL, denylist hoặc cơ chế distrust khác? |
| Scope | Client này chỉ dùng đúng tập CA cần thiết, không tin nhầm dev/staging CA? |
| Application authorization | Dù TLS hợp lệ, request có quyền và đúng tenant/resource? |

**Không phải mọi JSSE trust manager mặc định bật OCSP/CRL revocation checking giống nhau trong mọi cấu hình.** Revocation là quyết định policy và cách cấu hình; đừng tuyên bố “có cacerts thì CA bị thu hồi sẽ bị từ chối ngay”. Cơ chế browser WebPKI (có thể có danh sách distrust/CT policy riêng) cũng không thể suy ra tương đương với mọi Java HTTP client.

**Đừng tự viết kiểm hostname đơn giản** như `host.endsWith("example.com")`. Nó dễ mắc lỗi suffix/punycode/wildcard và spoofing. Ưu tiên endpoint identification do TLS stack hỗ trợ.

## 13. Ví dụ sự cố: thay tập CA làm ứng dụng lỗi

**Bối cảnh:** Java service gọi `https://billing.partner.test` và một public API khác. Hệ thống trước đây dùng default JSSE roots. Đội vận hành thêm private CA của đối tác bằng cách đặt:

```text
javax.net.ssl.trustStore=/etc/app/partner-only.p12
javax.net.ssl.trustStoreType=PKCS12
```

File mới chỉ chứa một private root CA.

**Hiện tượng:** kết nối tới `billing.partner.test` hoạt động, nhưng kết nối tới public API bắt đầu thất bại với lỗi `PKIX path building failed`, dù trước đây vẫn hoạt động.

**Nguyên nhân có thể:** custom truststore trở thành tập CA của default trust manager thay cho public roots. Việc tạo file mới **không** làm JSSE tự cộng private CA vào `cacerts`. Đó là tác động có phạm vi **JVM default TLS**, không phải chỉ endpoint đối tác.

**Phương án ưu tiên:**

- Public HTTP client dùng default trust policy được duyệt.
- Partner HTTP client dùng `SSLContext` riêng chỉ tin private CA/approved anchors.
- Cả hai vẫn bật hostname verification, giới hạn HTTP hosts và kiểm request authorization.
- Nếu product bắt buộc một JVM-wide bundle chung, tạo **curated bundle** có version gồm tất cả CA được phép và kiểm mọi downstream trước rollout; hiểu blast radius lớn hơn.

**Trường hợp khác:** xóa một root CA để hạn chế rủi ro nhưng không recreate long-lived connection pools. Trong một khoảng thời gian, kết nối cũ vẫn có thể hoạt động; sau restart mới thấy handshake fail. Kiểm thử phải bao gồm **new handshakes** và behavior sau refresh context/pool, không chỉ reuse kết nối đang mở.

### Sai lầm nghiêm trọng hơn: “trust all certificates”

Code như sau là **mã giả anti-pattern**, không phải triển khai hợp lệ để sử dụng:

```java
// KHÔNG dùng: chấp nhận mọi certificate chain mà không kiểm trust.
X509TrustManager trustAll = /* custom implementation
                               với checkServerTrusted() rỗng */;
```

Dù sửa được lỗi bắt tay ở môi trường thử, nó loại bỏ ranh giới xác thực peer và mở đường man-in-the-middle. Tương tự, tắt hostname verification không làm chain đáng tin hơn. Phải sửa nguyên nhân: đúng root/intermediate, hostname, endpoint certificate, thời hạn, thuật toán và cấu hình client.

## 14. Phân tích lỗi TLS theo từng lớp

Một số thông báo thường gặp:

| Hiện tượng | Nguyên nhân khả dĩ | Nên kiểm trước |
| --- | --- | --- |
| `PKIX path building failed` | Không dựng được chain tới trust anchor được phép | Runtime nào đang chạy, truststore nào, root/intermediate chain thực tế |
| `unable to find valid certification path` | Thiếu trust anchor/path phù hợp | `cacerts` vs custom truststore, chain server, constraints |
| `No subject alternative DNS name matching ...` | Hostname không khớp SAN | URL/SNI/hostname thực tế và leaf SAN |
| `CertificateExpiredException` / `CertificateNotYetValidException` | Leaf/chain certificate hết hoặc chưa tới hiệu lực | Server cert, chain, đồng hồ hệ thống |
| `Algorithm constraints check failed` | Key size/algorithm/signature bị policy loại | JDK security properties, certificate chain, kế hoạch chuyển thuật toán |
| `Invalid keystore format` | File type sai hoặc dữ liệu không phải keystore phù hợp | `PKCS12` vs `JKS`, file đúng, quyền đọc, integrity |
| `Keystore was tampered with, or password was incorrect` hoặc lỗi password tương tự | Mật khẩu sai, file hỏng hoặc format/provider không khớp | Secret/config/KeyStore.load parameters |
| Handshake lỗi chỉ sau restart | Process trước đó còn manager/context cũ | Lifecycle reload, phiên bản container/JDK, property startup |
| Public HTTPS fail sau khi import private CA | Custom store đã thay public roots | Kiểm phạm vi custom truststore, nên tách context |
| mTLS client auth fail | Server truststore hoặc client identity/chain không khớp | Server trust policy, client cert, KeyManager, EKU/identity |

**Không suy nguyên nhân tuyệt đối từ một chuỗi exception.** Lỗi PKIX có thể đến từ missing intermediate, expired/algorithm constraints, truststore sai môi trường hoặc provider policy. Thu thập evidence theo thứ tự: endpoint hostname, server chain, JVM runtime, effective truststore configuration, provider, key/certificate metadata và logs handshake đã được làm sạch.

Các tùy chọn debug (chỉ bật có kiểm soát):

```text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
```

Output có thể rất lớn và lộ endpoint metadata hoặc thông tin nhạy cảm liên quan. Không bật toàn bộ ở production lâu dài, không gửi debug log thô cho người ngoài mà chưa rà soát.

## 15. Quy trình thay trust bundle an toàn

Trước khi **thêm hoặc xóa** trusted CAs, tạo change plan:

1. **Định nghĩa scope:** đây là truststore outbound riêng của một client, JVM default, host JDK, container, hay inbound mTLS truststore?
2. **Inventory:** liệt kê trusted roots, intermediate anchors nếu có, fingerprints SHA-256, expiry, owner, mục đích, môi trường, file format và version.
3. **Xác minh nguồn CA:** nhận certificate từ nguồn uy tín, đối chiếu fingerprint độc lập, kiểm Basic Constraints/key usage/algorithm/expiry.
4. **Đánh giá ảnh hưởng:** endpoint nào đang dùng chain tới CA bị xóa? CA mới có thể cấp cho những tên nào? Có cross-signed alternate paths?
5. **Tạo bundle version mới:** không sửa trực tiếp trên production runtime như một thay đổi không theo dõi; có review/approval và cơ chế rollback.
6. **Kiểm thử âm/dương:** endpoint đúng phải kết nối được, endpoint lạ/sai hostname hoặc CA không được phép phải bị từ chối.
7. **Triển khai theo canary:** cập nhật một subset instances, tạo TLS handshakes mới, theo dõi lỗi và độ trễ.
8. **Reload/rotate:** đảm bảo các trust managers, SSLContexts và pools thực sự dùng bundle mới; với distrust khẩn cấp, xem xét đóng session cũ.
9. **Giám sát:** metrics handshake failures theo endpoint/JVM version, success rate, các đổi root/chain ngoài dự kiến, và audit truststore deployment.
10. **Rollback an toàn:** giữ bundle trước đó nếu vẫn được phép theo security policy; trong sự cố CA bị compromise, không được “rollback” đưa CA độc hại trở lại chỉ để giảm outage.
11. **Review sau rollout:** đếm lỗi mới, cập nhật tài liệu root inventory và hạn loại bỏ CA chuyển tiếp.
12. **Đồng bộ vòng đời:** theo dõi expiry, vendor root program updates, CA rotation, JDK image rebuild và chính sách security hardening.

### Canary cần test cả phép “không tin”

Nếu chỉ test `curl/java client tới partner => 200`, bạn chưa chứng minh trust policy được thu hẹp. Một suite an toàn nên có:

- Endpoint đúng chain được duyệt → **thành công**.
- Endpoint dùng CA thử nghiệm khác, không được duyệt → **thất bại**.
- Endpoint certificate có SAN sai tên → **thất bại**.
- CA đã bị xóa và không còn valid alternate path → **thất bại**.
- Chain hợp lệ nhưng application identity/tenant không được phép → TLS có thể thành công, request **bị từ chối bởi authorization**.
- Connection pool sau reload → handshake mới dùng đúng policy, không dựa vào session cũ.
- Multi-region/container images khác nhau → nhất quán theo version hoặc khác biệt được phép có tài liệu.

Đây là cách kiểm **phạm vi trust** thực tế thay vì chỉ nhìn số certificate entries.

## 16. Các ranh giới đặc biệt: client/server và môi trường

### 16.1 HTTPS outbound tới public internet

Thường phù hợp sử dụng vetted public root bundle của runtime/vendor, với hostname verification và lifecycle update. Nếu cần pinning/CA restriction cho một ứng dụng có threat model đặc biệt, phải thiết kế cả rotation/recovery; pin một leaf có thể gây outage khi certificate renew.

### 16.2 HTTPS outbound tới private PKI

Dùng truststore riêng chỉ chứa private issuing CAs/approved anchors cần thiết, gắn vào HTTP client cụ thể. Hạn chế DNS destinations và context AAD/authorization ở ứng dụng nếu cần. Không đưa private CA dev/staging vào production JVM-wide `cacerts`.

### 16.3 Inbound mTLS

Server dùng `TrustManager` để xác minh client certificate. Việc server tin CA không tự trao mọi role cho mọi cert do CA cấp. Cần mapping certificate identity (SAN/subject với profile đúng) tới principal đã được cấp quyền, EKU clientAuth khi yêu cầu, revocation, bảo vệ chống certificate spoofing và chính sách rotation.

### 16.4 CI/CD và container

Pipeline build có thể cập nhật JDK/root bundle khi rebase image. Image chạy mới không nhất thiết dùng cùng `cacerts` với host. Ghi lại JDK vendor/version, `java.home`, trust bundle digest/version và runtime flags trên release artifact. Với Kubernetes mounted Secrets/ConfigMaps, update file không bảo đảm JVM tự hot reload; có thể cần rollout restart hoặc reload logic đã test.

### 16.5 Nhiều HTTP libraries

JSSE là cơ chế TLS phổ biến cho Java, nhưng một số native clients, gRPC/Netty/OpenSSL provider, OS-native stack hoặc custom factories có thể dùng trust configuration khác. Khi gặp hai client trong cùng JVM có hành vi khác nhau, kiểm **client implementation thực tế**, không suy rằng cả hai đang dùng `javax.net.ssl.trustStore`.

## 17. Bảng so sánh nhanh

| Tiêu chí | `cacerts`/JSSE default | Custom JVM-wide truststore | Per-client custom `SSLContext` |
| --- | --- | --- | --- |
| Nguồn trust | Runtime/provider default, có thể khác nhau | File được chỉ định cho default trust manager | Keystore/manager do client thiết kế |
| Phạm vi thông thường | Mọi client dùng JSSE default | Mọi client dùng JSSE default trong JVM | Chỉ client/context được gắn |
| Có tự cộng public roots? | Tùy nguồn default | **Không** tự cộng chỉ vì file được chỉ định | **Không**, trừ khi code chủ động cấu hình |
| Cập nhật | JDK/vendor/OS policy hoặc custom maintenance | Deploy file+reload/restart | Replace/recreate client/context theo lifecycle |
| Kiểm soát riêng partner | Khó nếu dùng chung runtime | Có nhưng blast radius lớn | Thường rõ và hẹp nhất |
| Nguy cơ lớn | JDK root drift, root ngoài scope nếu dùng chung | Làm mất public roots hoặc thêm private CA quá rộng | Quên gắn context, hostname check hoặc reload pool |
| Phù hợp | Outbound public HTTPS thông thường | Bundle approved chung đã được quản lý | Private PKI, endpoint trust policy hẹp |

Bảng mô tả **hành vi thường gặp** với JSSE và kiến trúc hợp lý, không phải lời bảo đảm mọi runtime đều nạp cùng default roots. Chỉ có kết quả kiểm tra trên **ứng dụng và JDK thực tế** mới chứng minh chính sách hiệu lực.

## 18. Lỗi thường gặp cần tránh

1. **Import CA vào một `cacerts` nhưng app vẫn fail:** Có thể app chạy JDK khác, custom SSLContext, container, native TLS hoặc chưa reload. Xác định effective runtime và trust manager.
2. **Đặt custom truststore rồi tưởng vẫn tin public web:** Custom file có thể thay default roots; cần tách context hoặc xây curated bundle theo policy.
3. **Chỉ thêm leaf server certificate để “sửa” chain:** Dễ hết hạn/renew hỏng; không giải quyết hiểu đúng trust anchor, CA và hostname.
4. **Đổi truststore password bằng lệnh và ghi trong shell history:** Rò credential. Dùng secure prompt/secret manager và quyền file.
5. **Cho rằng password truststore làm certificate thành bí mật:** Certificate công khai; password chủ yếu bảo vệ cách lưu/integrity tùy format. **Quyền sửa trust bundle** cực kỳ nhạy cảm dù cert public.
6. **Tin CA có nghĩa tin mọi application user:** CA trust là peer authentication ở TLS, authorization là tầng khác.
7. **Chỉ kiểm `CertificateFactory` parse được:** Không chứng minh chain/hostname/trust.
8. **Tắt `HostnameVerifier` hoặc cài `trustAll` để cứu production:** Loại bỏ xác thực peer và tạo MITM risk.
9. **Không nhớ mTLS server truststore:** Thêm public CA vào server client-auth trust có thể mở rộng tập principal client có certificate được xét, dù ứng dụng còn authorization.
10. **Sửa trust file mà không refresh manager/pool:** Process có thể dùng policy cũ, nhất là khi phải distrust CA nhanh.
11. **Remove root đột ngột khi partner chưa rotate:** Gây outage handshake mới. Cần overlapping trust và kế hoạch cutover.
12. **Không kiểm alternate chain/cross-sign:** Xóa một anchor có thể không làm certificate bị từ chối nếu còn valid path khác; kiểm bằng test thực tế.
13. **Copy `cacerts` vào riêng một lần và quên cập nhật:** Tập public roots stale, có thể mất CA mới hoặc giữ CA đã bị distrust.
14. **Nhầm TLS trust với DNS/hostname/IP allowlist:** CA có thể cấp nhiều tên; giới hạn đích và xác minh hostname vẫn cần.
15. **Không kiểm Java version/vendor và các runtime flags:** Hai instance cùng source code có thể có hành vi trust khác.
16. **Ghi log toàn bộ certificate và private key chỉ để debug:** Tránh lộ dữ liệu và hạn chế retention logs.
17. **Không có test negative:** Chỉ chứng minh một endpoint hoạt động, chưa chứng minh tập CA được tin là tối thiểu.
18. **Đưa certificate không được xác minh vào truststore:** Kẻ tấn công có thể tự gửi root certificate và làm hệ thống tự tin nó; chỉ import CA từ nguồn đã xác minh độc lập.

## 19. Bài tập thực hành

### Bài 1 — Xác định effective truststore

Trên một máy có nhiều JDK, tìm `java.home` của runtime chạy một service. So sánh với `keytool` trên `PATH` và các startup properties `javax.net.ssl.trustStore`. Trả lời: service sử dụng JSSE default hay client custom, và file trust thực tế nào được nạp? Không tự đọc thêm file nhạy cảm hoặc ghi đè CA store production.

### Bài 2 — Isolated trust bằng Java

Chạy `TrustScopeDemo`. Giải thích vì sao custom empty manager không tự kế thừa CA default, vì sao sau import đúng một certificate manager chỉ có một issuer trong ví dụ, và tại sao chương trình **chưa chứng minh** TLS tới hostname nào thành công. Bổ sung test với private CA certificate được xác minh fingerprint từ kênh đáng tin thay vì `defaultIssuers[0]`.

### Bài 3 — Replace vs union

Một Java app có hai HTTPS clients: client A gọi public API; client B gọi internal API dùng private CA. So sánh:

- Set một custom `javax.net.ssl.trustStore` có duy nhất private CA cho cả JVM.
- Merge public roots với private CA vào một truststore.
- Tạo hai `SSLContext` khác nhau và gắn đúng cho từng client.

Đánh giá ảnh hưởng khi private CA bị lộ và khi public root set của JDK thay đổi. Chọn cách có trust scope phù hợp nhất, giải thích trade-off về maintainability.

### Bài 4 — Rollover CA không downtime

Đối tác chuyển từ OldRoot sang NewRoot trong 60 ngày. Lập kế hoạch canary: nạp cả hai anchors trước cutover, kiểm chain và hostname, chuyển server certificate, đếm clients còn dùng chain cũ, xóa OldRoot sau thời hạn có bằng chứng. Test cả handshake mới và client có keep-alive/TLS resumption.

### Bài 5 — Kiểm thử phạm vi tin cậy

Dựng hai CA test độc lập trong lab và hai endpoint HTTPS test. Client chỉ tin CA A phải kết nối endpoint A thành công và từ chối endpoint B, đồng thời từ chối hostname không khớp dù chain do CA A cấp. Sau đó thêm CA B và chứng minh scope thay đổi **chỉ đối với client được cấu hình dùng store mới**. Không tạo CA test như trust anchor của production runtime.

### Bài 6 — mTLS và quyền nghiệp vụ

Một server bật mTLS và truststore chứa CA phát client certificates. Thêm một root CA mới dẫn đến nhiều client có khả năng trình certificate được chấp nhận hơn. Xác định vì sao vẫn cần mapping certificate identity tới tài khoản/role, EKU clientAuth, revocation và authorization. Lập negative test cho certificate của tenant khác.

### Bài 7 — Incident response

Một root CA nội bộ bị nghi compromise. Hãy mô tả hành động: inventory clients/server chains, giới hạn CA trust, thu hồi/thay chain, rotate danh tính liên quan, deploy trust bundle mới theo canary, refresh SSLContexts/sessions, log chứng cứ và theo dõi lỗi. Chỉ rõ tại sao khôi phục bundle cũ để sửa outage **có thể không được phép** trong security incident.

### Bài 8 — Debug một lỗi PKIX

Một ứng dụng mới chạy JDK trong container báo `unable to find valid certification path`, trong khi lệnh `curl` trên host thành công. Liệt kê các giả thuyết: runtime root khác, custom JVM truststore thay default, server thiếu intermediate, HTTPS hostname/SNI khác, chính sách algorithm, certificate expired, proxy TLS interception. Chọn dữ liệu kiểm thử từng giả thuyết và không tắt trust verification.

**Điều kiện hoàn thành:** bạn phân biệt được `cacerts` là một **nguồn tin cậy mặc định có phạm vi runtime/provider**, kho tin cậy riêng có thể **thay thế hoặc thu hẹp** trust anchors, và mọi thay đổi tập CA tin cậy có tác động tới **bảo mật lẫn khả năng kết nối**. Một quyết định đúng phải có proof về certificate chain, hostname, trust scope và cập nhật lifecycle thật sự của TLS client.

## 20. Tài liệu tham khảo

- [Java 17 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): default truststore search order, `TrustManagerFactory`, SSL contexts và cấu hình.
- [Java 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): khởi tạo trust manager từ KeyStore hoặc nguồn mặc định.
- [Java 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): init và phạm vi context TLS.
- [Java 17 — X509TrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509TrustManager.html): kiểm đường chứng thư và accepted issuers.
- [Java 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): trustedCertEntry, load và storage.
- [Java 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification algorithm.
- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cấu hình per-client SSLContext.
- [Java 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `-cacerts`, `-list`, `-printcert` và `-importcert`.
- [RFC 5280 — X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path, trust anchors và các ràng buộc.
- [RFC 6125 — Service Identity (historic HTTPS identity rules)](https://www.rfc-editor.org/rfc/rfc6125): danh tính TLS; với thiết kế mới, đối chiếu chuẩn được cập nhật của protocol và TLS stack.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): phương pháp xác minh tên máy chủ/định danh dịch vụ hiện đại.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS peer validation và vận hành.
