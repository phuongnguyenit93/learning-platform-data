# Kho tin cậy riêng và thuộc tính `javax.net.ssl.trustStore` trong Java

*Chủ đề cha: Chứng thư gốc — Java 10. Bài Knowledge này hướng dẫn cách quản lý **trust anchors/chứng thư CA tin cậy**, tạo một kho tin cậy riêng (custom truststore) bằng `keytool`, cấu hình `javax.net.ssl.trustStore` và các thuộc tính JSSE liên quan, cũng như kiểm tra đường đi xác thực TLS thật trên Java 17+. Nội dung sử dụng cơ chế hiện còn được hỗ trợ trong JDK hiện đại; các bước tự ký chỉ dùng trong môi trường thực hành local, không phải quy trình tin cậy CA dành cho production.*

## 1. Câu trả lời ngắn

Khi ứng dụng Java kết nối HTTPS hoặc TLS, bên client cần **xác minh danh tính server** bằng chuỗi chứng chỉ X.509 và một tập các **trust anchors** được cho phép. Trong SunJSSE/JSSE reference implementation, một cách cung cấp trust anchors là **truststore** chứa các chứng chỉ được tin cậy. Một file truststore Java có thể dùng định dạng `PKCS12` và đuôi `.p12`, nhưng tên file không tự chứng minh nội dung đáng tin.

Thuộc tính hệ thống:

```bash
-Djavax.net.ssl.trustStore=/path/to/company-trust.p12
```

chỉ định file truststore mà **default JSSE TrustManager** sẽ dùng trong những trường hợp ứng dụng lấy cơ chế TLS mặc định từ SunJSSE.

Một cách gọi đầy đủ:

```bash
java \
  -Djavax.net.ssl.trustStore=/secure/config/company-trust.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=DEMO_ONLY \
  -jar app.jar
```

**Dòng này chỉ minh họa cấu trúc cờ:** không sao chép `DEMO_ONLY` làm mật khẩu thật. Trong production, tránh đặt mật khẩu trực tiếp trên command line vì có thể bị lộ qua process listing, log khởi động hoặc telemetry; dùng cơ chế cung cấp cấu hình/bí mật được bảo vệ và đánh giá đúng nhu cầu password của truststore. Đặt các `-D` **trước `-jar` hoặc trước tên main class** để Java launcher nhận làm JVM system properties.

**Quy tắc quan trọng:** tự chỉ định một truststore riêng thường có nghĩa **thay tập chứng thư mặc định** của default JSSE TrustManager, **không tự cộng thêm** CA của file đó vào `cacerts`. Nếu file mới chỉ có CA nội bộ, client có thể tin máy chủ nội bộ nhưng không còn tin nhiều HTTPS public sites từng được JDK mặc định tin cậy.

## 2. Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Giải thích vai trò của root CA, intermediate CA, leaf/server certificate và trust anchor.
2. Phân biệt **truststore** với **keystore lưu private key**.
3. Hiểu thứ tự lựa chọn truststore mặc định: explicit `javax.net.ssl.trustStore`, sau đó `jssecacerts`, rồi `cacerts` nếu không có property.
4. Biết vì sao **path không tồn tại** của explicit truststore có thể dẫn tới **truststore rỗng**, không tự fallback sang `cacerts`.
5. Biết `javax.net.ssl.trustStoreType`, `trustStorePassword`, `trustStoreProvider`, cùng `javax.net.ssl.keyStore` dành cho mục đích khác.
6. Tạo truststore `PKCS12` bằng `keytool -importcert`, kiểm tra fingerprint và entry type.
7. Có thể thực hiện một bài test TLS loopback với chứng chỉ thử nghiệm được tin cậy/không được tin cậy.
8. Hiểu vì sao xác thực chứng chỉ (chain trust) và xác thực hostname/SAN là **hai điều kiện riêng**.
9. Biết tạo `SSLContext` riêng bằng `KeyStore` + `TrustManagerFactory` thay vì sửa global system properties khi có nhiều outbound destinations.
10. Biết timing: cấu hình JSSE default context trước khi tạo client/socket; đổi property sau khi client đã tạo không phải phép hot reload an toàn.
11. Xử lý lỗi `PKIX path building failed`, `SSLHandshakeException`, file/format/password sai, certificate hết hạn, SAN không khớp, thiếu intermediate.
12. Bảo vệ CA certificate provenance, truststore integrity, permissions, rotation, rollback và tránh trust-all managers.
13. Biết khi nào cần `mTLS` và khi nào `trustStore` riêng **không** đủ để gửi chứng chỉ client.
14. Chẩn đoán thực tế bằng `keytool` và `javax.net.debug` mà không tiết lộ dữ liệu TLS nhạy cảm.

## 3. TLS dùng chứng chỉ để xây dựng niềm tin như thế nào?

Giả sử client kết nối `https://api.internal.example`. Server trình bày một **leaf certificate**, thường kèm một hoặc nhiều **intermediate certificates**. Client sẽ:

1. Kiểm tra thông tin X.509 và chữ ký/chuỗi chứng chỉ theo quy tắc PKIX của trust manager.
2. Tìm một **đường tin cậy (certification path)** dẫn tới trust anchor mà client đã cho phép.
3. Kiểm tra những điều kiện liên quan như hiệu lực thời gian, thuật toán bị cấm, CA constraints, key usage/extended key usage và các chính sách có áp dụng.
4. Xác minh **tên server yêu cầu kết nối** phù hợp Subject Alternative Name (SAN) của leaf certificate.
5. Khi phù hợp, xét thêm chính sách thu hồi/revocation và TLS protocol/cipher restrictions đã được cấu hình.

Ví dụ chuỗi:

```text
  Truststore của client
       |
       v
  Organization Root CA  <-- trusted certificate / trust anchor
       |
       | cấp chứng chỉ
       v
  Organization Intermediate CA
       |
       | ký leaf
       v
  api.internal.example (server leaf certificate)
       |
       v
  TLS client: xác thực chain + hostname
```

Một **root CA** là điểm khởi đầu được client tin cậy theo chính sách, thường mang chứng chỉ tự ký, nhưng việc “tự ký” **không khiến một chứng chỉ tự trở thành đáng tin**. Bạn chỉ nên import một CA sau khi xác minh được nguồn và SHA-256 fingerprint qua kênh độc lập đáng tin.

### 3.1. Trust anchor không đồng nghĩa tin cậy mọi server

Ngay cả khi đường chứng chỉ dẫn tới một CA đã tin cậy, client HTTPS vẫn cần so hostname thực sự kết nối với SAN của server. Chứng chỉ dành cho `service-a.internal.example` không tự hợp lệ cho `service-b.internal.example`.

Nếu tin cậy một **root CA rộng**, bạn đang cho phép root đó làm trust anchor cho các chuỗi chứng chỉ đủ điều kiện khác, không chỉ một leaf của service hiện tại. Vì vậy hãy giới hạn tập CA theo mục đích, vận hành root/private PKI đúng vòng đời và tránh import “một CA bất kỳ” chỉ để hết lỗi TLS.

### 3.2. Root, intermediate và leaf khác nhau

| Loại chứng chỉ | Thường nằm ở đâu? | Mục đích |
| --- | --- | --- |
| Root CA | Truststore đã được phê duyệt của client | Trust anchor để xác thực chain |
| Intermediate CA | Server gửi kèm chain hoặc một nguồn có thể dùng khi xây chain | Trung gian nối leaf tới root |
| Leaf/server certificate | Server trình bày khi TLS handshake | Chứng minh tên/danh tính của endpoint qua private key |
| Client certificate (khi mTLS) | Keystore/private-key material của client | Client chứng minh danh tính với server |
| Revocation/status information | OCSP/CRL/cấu hình PKIX khác nếu bật | Xử lý chứng chỉ bị thu hồi theo chính sách |

**Server nên gửi chain cần thiết, đặc biệt các intermediate certificates**, không kỳ vọng client phải đi tìm/cài thủ công từng intermediate. Client truststore thường chứa trust anchors được chủ đích chấp thuận, không nên cứ import mọi leaf hay intermediate thấy trong log.

## 4. Truststore không giống keystore chứa private key

Java sử dụng trừu tượng `java.security.KeyStore` cho nhiều loại entry, nhưng **vai trò vận hành** của hai kho khác nhau:

| Thuật ngữ | Nội dung thường gặp | Ai dùng? | Thuộc tính mặc định liên quan |
| --- | --- | --- | --- |
| Truststore | `trustedCertEntry` cho root/CA hoặc certificate được tin cậy | TrustManager xác minh **đối tác** | `javax.net.ssl.trustStore` |
| Identity keystore | `PrivateKeyEntry` chứa private key và certificate chain | KeyManager chọn danh tính **của bên local** | `javax.net.ssl.keyStore` |
| Java `KeyStore` API | Container có thể chứa trusted certificate, private key và entry khác tùy loại | API trừu tượng để lưu/tải credential material | `KeyStore.getInstance(...)` |

Ví dụ client kết nối HTTPS thông thường:

- Client cần **truststore** hoặc cấu hình TrustManager đáng tin để xác minh server.
- Client **không cần identity keystore riêng** nếu server không yêu cầu mTLS.
- Server thường cần private key và certificate chain của chính nó.
- Khi server yêu cầu **mTLS**, client cần cả cơ chế tin cậy server **và** key manager/private key để trình bày chứng chỉ client; server cũng cần trust anchors để xác minh client.

**Đặt `javax.net.ssl.trustStore` không tự khiến client gửi certificate của mình.** Muốn cung cấp danh tính client, xem cấu hình `javax.net.ssl.keyStore` hoặc `KeyManagerFactory` tương ứng.

## 5. SunJSSE chọn kho tin cậy mặc định theo thứ tự nào?

Trong JSSE reference implementation được Oracle tài liệu hóa:

1. Nếu `javax.net.ssl.trustStore` được **định nghĩa**, default TrustManager tìm file/tài nguyên theo giá trị đó. Nếu file được tìm và đọc đúng, dùng nó.
2. Nếu property **được định nghĩa nhưng file không tồn tại**, SunJSSE có thể tạo **default TrustManager với empty keystore**. Điều này **không phải** “thử không thấy file rồi tự quay về `cacerts`”.
3. Nếu **không định nghĩa property**, SunJSSE kiểm tra file `$JAVA_HOME/lib/security/jssecacerts`; khi có, nó được ưu tiên.
4. Nếu không có `jssecacerts`, SunJSSE xét `$JAVA_HOME/lib/security/cacerts`.
5. Nếu không có kho mặc định thích hợp, việc không có trust anchors có thể dẫn tới TLS certificate validation failure. Không dựa vào các cipher suite anonymous/legacy để thay thế xác thực server.

Sơ đồ:

```text
Có -Djavax.net.ssl.trustStore ?
           |
    +------+------+
    |             |
   Có           Không
    |             |
Dùng path       jssecacerts tồn tại?
được chỉ định     |        |
    |            Có       Không
    |             |        |
Path sai?      Dùng nó   cacerts tồn tại?
    |                       |       |
  Empty / fail            Có      Không
(có thể dẫn tới           |        |
 TLS error)            Dùng nó   không có roots
```

`jssecacerts` và `cacerts` là các file trong **runtime image đang chạy**, không nhất thiết là JDK được terminal `javac` sử dụng hoặc path ở một máy khác. Trên các JDK hiện đại, `java.home` là thông tin đáng tin cậy hơn để tìm runtime đang chạy nếu bạn thật sự cần điều tra.

### 5.1. Vì sao đặt explicit truststore làm thay đổi khả năng truy cập Internet?

Giả sử `company-trust.p12` chỉ có một `Organization Root CA`. Khi Java HTTP client dùng default TrustManager được cấu hình chỉ với kho này, nó có thể tin `api.internal.example` do CA nội bộ ký nhưng **không còn tin** một website public được ký bởi CA chỉ có trong `cacerts`.

Đây là hiệu ứng **thay thế trust anchors**, không phải lỗi Java. Nếu yêu cầu vừa tin CA nội bộ vừa giữ public roots, cần **thiết kế hợp nhất trust anchors** (tạo truststore kết hợp từ nguồn CA đã phê duyệt, hoặc xây TrustManager/SSLContext theo chính sách), chứ không giả định SunJSSE tự merge khi `-Djavax.net.ssl.trustStore` được đặt.

### 5.2. Nếu truststore không tồn tại hoặc lỗi format/password?

Các trường hợp khác nhau:

- File được định nghĩa **nhưng không tồn tại**: reference implementation tạo empty trust material như đã mô tả, thường dẫn tới TLS authentication failure.
- File tồn tại nhưng **không đọc được**: có thể gặp lỗi khởi tạo trust manager/default SSLContext hoặc TLS failure; xem exception chain và JSSE debug, không gán một message bất biến.
- File có **format sai**, password không phù hợp, provider/algorithm không hỗ trợ: có thể phát sinh lỗi `KeyStoreException`, `IOException` khi load, `NoSuchAlgorithmException` hoặc lỗi SSLContext khởi tạo tùy nơi gọi.
- File tồn tại nhưng **không có CA/entry đủ điều kiện**: trust path xây dựng thất bại dù file được mở.
- File đúng nhưng server gửi certificate không hợp hostname: phải xử lý **name mismatch**, không phải import thêm một CA để bỏ qua name validation.

## 6. Những system properties quan trọng

| System property | Chức năng | Lưu ý |
| --- | --- | --- |
| `javax.net.ssl.trustStore` | Chỉ định truststore cho default JSSE trust manager | Explicit path thường thay bộ CA mặc định |
| `javax.net.ssl.trustStoreType` | Chỉ định loại KeyStore, ví dụ `PKCS12` | Dùng đúng định dạng thật của file |
| `javax.net.ssl.trustStorePassword` | Password đọc/kiểm integrity truststore | Không mặc định an toàn để đưa trên command line |
| `javax.net.ssl.trustStoreProvider` | Chỉ định security provider cho truststore | Chỉ dùng khi cần provider cụ thể |
| `javax.net.ssl.keyStore` | Đường dẫn keystore của **danh tính local** | Khác với truststore |
| `javax.net.ssl.keyStoreType` | Loại keystore | Cấu hình riêng với trustStoreType |
| `javax.net.ssl.keyStorePassword` | Password của identity keystore | Private-key protection tùy entry/provider |
| `javax.net.ssl.keyStoreProvider` | Provider cho identity keystore | Quan trọng với HSM/provider đặc biệt |
| `javax.net.debug` | Bật chẩn đoán JSSE/TLS | Không phải cờ tắt xác thực |
| `java.security.debug` | Chẩn đoán chính sách/certpath Java Security | Log có thể rất dài |

Các tên trên thuộc **JSSE reference implementation**. Một thư viện có TLS stack riêng, dùng `SSLContext` riêng hoặc security provider khác có thể không dùng các properties này theo đúng cách như default SunJSSE. Đừng sửa cờ global rồi kết luận mọi HTTPS client trong process buộc thay truststore.

### 6.1. Type nên chọn: `PKCS12`

Với một truststore riêng mới trong Java 17+, định dạng `PKCS12` được hỗ trợ tốt và là lựa chọn thông dụng. Đừng dựa vào đuôi `.p12` để tự suy nội dung; hãy đặt:

```bash
-Djavax.net.ssl.trustStoreType=PKCS12
```

khi đó là file PKCS#12 thật. `JKS` vẫn được JDK hỗ trợ để tương thích nhưng bài mới không cần lấy nó làm mặc định. `KeyStore.getDefaultType()` của một JDK hiện đại thường là `pkcs12`; muốn chắc, kiểm tra cấu hình/runtime thay vì đoán từ tên file.

### 6.2. `trustStore=NONE` không phải shortcut để bỏ xác thực

Tài liệu JSSE cho phép giá trị `NONE` trong những trường hợp truststore **không nằm trên file**, ví dụ dùng phần cứng/HSM theo provider và type tương ứng như `PKCS11`. Nó **không** phải cờ “tin mọi chứng chỉ” và không nên dùng để cố vượt lỗi `PKIX path building failed`.

Các trường hợp PKCS#11 cần cấu hình provider/token theo chính sách bảo mật của hệ thống; không đủ chỉ gõ `-Djavax.net.ssl.trustStore=NONE` rồi mong client xác thực được server.

### 6.3. Password có phải bí mật giống private key không?

Một truststore chỉ chứa `trustedCertEntry` thường chứa **chứng chỉ công khai**, không chứa private key. Password của nó thường phục vụ bảo vệ/kiểm integrity nội dung khi load, **không biến certificate công khai thành bí mật**. Tuy nhiên:

- Vẫn bảo vệ password theo chính sách, không phát tán qua command line/log.
- Không dựa vào password thay OS file/dir permissions hay provenance.
- Nếu kho có private keys (không nên trong một CA truststore đơn thuần), mức rủi ro bảo mật khác.
- Không mặc định mật khẩu nhà cung cấp mặc định `changeit` là mật khẩu production có giá trị bảo vệ.

## 7. Chuẩn bị một truststore riêng bằng `keytool`

Quy trình production đúng hướng:

1. Yêu cầu nhóm PKI/CA cung cấp **root CA certificate** hoặc trust anchor đã được phê duyệt.
2. Kiểm tra subject, issuer, validity, key usages/CA constraints và đặc biệt **SHA-256 fingerprint từ kênh độc lập**.
3. Tạo truststore `PKCS12` mới ở khu vực build/config chỉ người được phép sửa.
4. Import certificate vào một alias có ý nghĩa, ví dụ `organization-root-2026`.
5. Liệt kê lại entry và fingerprint; xác nhận entry type là `trustedCertEntry`.
6. Phân phối truststore qua artifact/secret/config deployment tin cậy; giới hạn quyền ghi.
7. Test TLS chain và hostname với môi trường được phép.
8. Quản lý rotation và loại bỏ root không còn được tin tưởng theo lịch đổi kho đã kiểm thử.

### 7.1. Kiểm tra certificate trước khi import

Ví dụ được nhóm PKI cung cấp file `organization-root.crt`:

```bash
keytool -printcert -file organization-root.crt
```

Đọc thông tin hiển thị; **đối chiếu SHA-256 fingerprint với fingerprint đã xác nhận qua kênh độc lập**, không chỉ lấy certificate và fingerprint từ cùng nguồn email/download chưa được xác thực.

Khi đã xác minh:

```bash
keytool -importcert \
  -alias organization-root \
  -file organization-root.crt \
  -keystore company-trust.p12 \
  -storetype PKCS12
```

`keytool` sẽ hỏi password cho file mới hoặc hỏi xác nhận fingerprint tùy quy trình. **Không dùng `-noprompt` bừa bãi với chứng chỉ không tin cậy**, vì có thể làm tự động chấp thuận trust anchor mà chưa kiểm tra.

### 7.2. Xem nội dung truststore

```bash
keytool -list -v \
  -keystore company-trust.p12 \
  -storetype PKCS12
```

Kiểm tra alias, entry type, owner/issuer, validity, extensions, fingerprint. Khi làm báo cáo có thể che thông tin tổ chức nhạy cảm; certificate public không đồng nghĩa mọi hostname nội bộ phải được đưa vào log công khai.

**`keytool -importcert` thêm một trusted certificate entry** khi alias chưa tồn tại và không phải alias private-key entry. Nếu alias đã tồn tại, thao tác có thể lỗi hoặc theo nhánh certificate reply khác. Không ghi đè các alias một cách mù quáng.

### 7.3. Sử dụng password tương tác hoặc cơ chế được bảo vệ

`keytool` hỗ trợ các lựa chọn đọc password từ môi trường/tệp được bảo vệ như `-storepass:env` hoặc `-storepass:file` khi thích hợp, và mặc định có thể prompt nếu bỏ `-storepass`. Chọn chính sách phù hợp, tránh để password cố định trong shell history/CI log.

**Đối với thí nghiệm `localhost` ở phần sau**, bài dùng mật khẩu literal `changeit` để code/chạy dễ tái hiện trong thư mục tạm. Mật khẩu đó **chỉ dành cho demo**, không đưa certificate tự ký hoặc password demo vào cấu hình thật.

## 8. Thí nghiệm TLS loopback an toàn: một server chỉ nghe 127.0.0.1

Ta sẽ chứng minh bằng **một chương trình Java đầy đủ**:

- Server TLS chạy nội bộ trên `127.0.0.1` với certificate tự ký thử nghiệm.
- Client mặc định không tin certificate này nên handshake thất bại.
- Client được cung cấp truststore riêng chứa certificate thử nghiệm sẽ handshake thành công.
- Client dùng explicit truststore path sai vẫn không được tự chuyển sang bộ CA mặc định.
- Client được cấp `SSLContext` riêng bằng `TrustManagerFactory` cũng handshake thành công, dù không sửa global properties.

**Môi trường:** JDK 17+ có `javac`, `java`, `keytool`; một thư mục trống riêng cho ví dụ. Không chạy các bước keytool này trong thư mục/cấu hình production. **Đây là chứng chỉ leaf tự ký và được tin cậy trực tiếp chỉ trong thử nghiệm localhost**; production nên dùng CA/PKI hợp lệ được duyệt.

### 8.1. Tạo server identity keystore thử nghiệm

Trong thư mục demo:

```bash
keytool -genkeypair \
  -alias localserver \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 7 \
  -dname "CN=localhost" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1" \
  -keystore server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -keypass changeit \
  -noprompt
```

Giải thích:

- `server.p12` chứa **private key** và certificate của server; phải được bảo vệ mạnh hơn file certificate công khai.
- `-validity 7` giới hạn thời gian hiệu lực demo 7 ngày; thực hiện lại sau khi hết hạn.
- `SAN=DNS:localhost,IP:127.0.0.1` cho phép client kiểm tra endpoint identification khi kết nối tới IP loopback.
- `CN=localhost` không thay vai trò của SAN trong hostname verification hiện đại.
- RSA 2048 + SHA256withRSA là cấu hình tương thích để học, không phải khuyến nghị cố định cho mọi chính sách PKI; production theo thuật toán/key length được tổ chức chấp thuận.
- `changeit` chỉ là mật khẩu thử nghiệm; `-noprompt` được dùng vì tự tạo và tự kiểm soát keypair trong demo, không dùng để import CA lạ.

### 8.2. Xuất certificate công khai của server

```bash
keytool -exportcert \
  -rfc \
  -alias localserver \
  -keystore server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -file localhost.crt
```

`localhost.crt` ở đây chỉ chứa **public certificate**, không có server private key. Hãy giữ `server.p12` riêng và không chia sẻ nó cho các client. Có thể xem fingerprint:

```bash
keytool -printcert -file localhost.crt
```

Fingerprint là dữ liệu phụ thuộc certificate được tạo, **không có stdout cố định** cho mọi lần chạy.

### 8.3. Import certificate vào client truststore thử nghiệm

```bash
keytool -importcert \
  -alias demo-localhost \
  -file localhost.crt \
  -keystore client-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -noprompt
```

Trong demo **chúng ta tự tạo** `localhost.crt` nên việc bỏ prompt là có chủ đích. Trong production, phải xác minh chứng chỉ/fingerprint CA trước import; không chạy `-noprompt` trên một CA lấy tùy tiện từ mạng.

Kiểm tra:

```bash
keytool -list \
  -keystore client-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
```

Một dòng đáng chú ý là alias `demo-localhost` với **`trustedCertEntry`**. SHA-256 fingerprint của entry sẽ **khác theo từng lần bạn tạo keypair**, không copy fingerprint ví dụ vào code hoặc chính sách kiểm chứng thật.

## 9. Chương trình Java độc lập `LocalTlsDemo.java`

Tạo file **`LocalTlsDemo.java`** đúng nội dung sau:

```java
import javax.net.ssl.*;
import java.net.*;
import java.nio.file.*;
import java.security.*;

public class LocalTlsDemo {
    static SSLContext serverContext(Path p) throws Exception {
        var ks = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(p)) {
            ks.load(in, "changeit".toCharArray());
        }

        var km = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        km.init(ks, "changeit".toCharArray());

        var context = SSLContext.getInstance("TLS");
        context.init(km.getKeyManagers(), null, null);
        return context;
    }

    static SSLContext customContext(Path p) throws Exception {
        var ks = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(p)) {
            ks.load(in, "changeit".toCharArray());
        }

        var tm = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tm.init(ks);

        var context = SSLContext.getInstance("TLS");
        context.init(null, tm.getTrustManagers(), null);
        return context;
    }

    public static void main(String[] a) throws Exception {
        var srv = serverContext(Path.of(a[0]));

        try (var listener = (SSLServerSocket)
                srv.getServerSocketFactory().createServerSocket(
                        0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(10000);

            var worker = new Thread(() -> {
                try (var peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(10000);
                    peer.startHandshake();
                } catch (Exception ignored) {
                    // Kết quả handshake được in ở client.
                }
            }, "local-server");
            worker.start();

            try {
                SSLSocketFactory factory = a[1].equals("scoped")
                        ? customContext(Path.of(a[2]))
                              .getSocketFactory()
                        : (SSLSocketFactory)
                              SSLSocketFactory.getDefault();

                try (var client = (SSLSocket)
                        factory.createSocket(
                                "127.0.0.1",
                                listener.getLocalPort())) {
                    client.setSoTimeout(10000);

                    SSLParameters params = client.getSSLParameters();
                    params.setEndpointIdentificationAlgorithm("HTTPS");
                    client.setSSLParameters(params);

                    client.startHandshake();
                    System.out.println("client=trusted");
                }
            } catch (SSLException ex) {
                System.out.println("client="
                        + ex.getClass().getSimpleName());
            } finally {
                worker.join(12000);
            }
        }
    }
}
```

**Điều kiện:** truyền ít nhất hai đối số `server.p12` và `default`/`scoped`; ở chế độ `scoped`, truyền thêm đường dẫn `client-trust.p12`. Chương trình demo chủ động kiểm tra certificate bằng TLS handshake, nhưng chỉ mở cổng loopback ngẫu nhiên và không gửi dữ liệu nhạy cảm.

### 9.1. Giải thích những API trong chương trình

- `KeyStore.getInstance("PKCS12")`: đọc kho identity/trust material đúng định dạng.
- `KeyManagerFactory.init(serverKeyStore, password)`: chuẩn bị khóa bí mật và chain **dành cho server**.
- `TrustManagerFactory.init(clientTrustStore)`: tạo trust managers từ trusted entries **dành cho client**.
- `SSLContext.getInstance("TLS")`: tạo context TLS, không chỉ định SSLv3/TLS 1.0 cũ.
- `SSLContext.init(km, tm, null)`: cấu hình server/client bằng manager thích hợp; null ở tham số `SecureRandom` cho provider chọn default an toàn.
- `SSLServerSocket`: lắng nghe localhost với identity server; `SSLServerSocket.accept()` cho socket phía server.
- `SSLSocketFactory.getDefault()`: ở chế độ `default`, dùng JSSE default configuration, chịu ảnh hưởng của `javax.net.ssl.trustStore` nếu SunJSSE dùng thuộc tính đó.
- `customContext(...).getSocketFactory()`: ở chế độ `scoped`, **chỉ client của ví dụ** có truststore tùy chọn, không sửa global system properties.
- `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`: yêu cầu kiểm tra hostname/IP SAN trên **raw SSLSocket client** theo thuật toán HTTPS.
- `client.startHandshake()`: thực sự kích hoạt TLS handshake, không phải chỉ đọc file truststore rồi in `OK`.
- `Thread.join(12000)`: chờ server test hoàn tất; timeout ngăn ví dụ treo vĩnh viễn nếu môi trường có sự cố. Đây là demo chẩn đoán, không phải framework TLS server dùng production.

### 9.2. Vì sao bắt buộc bật hostname verification cho raw `SSLSocket`?

Không phải mọi client API tự bật hostname verification với cùng chính sách. Raw `SSLSocket` thường **không tự bật endpoint identification theo HTTPS**. Vì vậy ví dụ đặt:

```java
SSLParameters params = client.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
client.setSSLParameters(params);
```

trước khi handshake. Nếu không làm vậy, người học có thể quan sát TLS handshake “thành công” với certificate đi tới một root tin cậy nhưng **không đúng server hostname** và rút ra kết luận sai.

Với `java.net.http.HttpClient` hoặc `HttpsURLConnection` dùng đúng cách, xác thực HTTPS hostname là một phần quan trọng của cấu hình/client API. Không thay bằng custom `HostnameVerifier` luôn trả `true`.

## 10. Kiểm thử trường hợp thất bại mặc định

Biên dịch Java 17+:

```bash
javac --release 17 LocalTlsDemo.java
```

Chạy với default trust material của JDK:

```bash
java LocalTlsDemo server.p12 default
```

Trên môi trường thực hành **chưa có chứng chỉ `localhost` của demo trong bất kỳ truststore mặc định nào**, output client đã kiểm thử:

```text
client=SSLHandshakeException
```

Lý do: self-signed leaf thử nghiệm chưa là trust anchor được default TrustManager chấp nhận. **Không hardcode kết luận “mọi JDK đều fail”** nếu người quản trị đã import chính certificate demo vào truststore mặc định, hoặc dùng một SSLContext khác.

Lỗi `SSLHandshakeException` là một lớp ngoại lệ có thể có nhiều nguyên nhân khác nhau. Phải xem `cause`, JSSE logs và server chain trước khi quyết định thêm CA.

## 11. Kiểm thử `javax.net.ssl.trustStore` tùy chỉnh

Chạy lệnh sau **trong thư mục demo**:

```bash
java \
  -Djavax.net.ssl.trustStore=client-trust.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  LocalTlsDemo server.p12 default
```

Stdout đã kiểm thử trên HotSpot JDK 24:

```text
client=trusted
```

Bây giờ JSSE default TrustManager đã có entry `demo-localhost` nên tin certificate tương ứng. Đồng thời code vẫn bật `HTTPS` endpoint identification và certificate có SAN cho `127.0.0.1`, nên thành công **không phụ thuộc một phương án “trust all” vô hiệu hóa bảo mật**.

**Nhắc lại:** password được viết thẳng chỉ vì đây là file demo sinh ra trong thư mục tạm. Khi vận hành thật, bảo vệ password/process arguments và không dùng certificate demo.

### 11.1. Truststore property phải đặt đúng vị trí

Hợp lệ:

```bash
java -Djavax.net.ssl.trustStore=client-trust.p12 -cp . LocalTlsDemo server.p12 default
```

Không đúng về mặt kỳ vọng Java launcher:

```bash
java LocalTlsDemo server.p12 default -Djavax.net.ssl.trustStore=client-trust.p12
```

Ở lệnh thứ hai, `-D...` xuất hiện **sau tên main class**, nên trở thành đối số ứng dụng thay vì JVM system property. Nếu ứng dụng không tự parse flag ấy, default truststore không đổi.

Với ứng dụng `-jar`:

```bash
java -Djavax.net.ssl.trustStore=/secure/path/trust.p12 -jar app.jar
```

Quy tắc tương tự: đặt các Java options trước `-jar`, không sau tên JAR.

## 12. Thử đường dẫn sai: một bẫy rất thường gặp

Tình huống:

```bash
java \
  -Djavax.net.ssl.trustStore=missing.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  LocalTlsDemo server.p12 default
```

Với `missing.p12` **không tồn tại**, output trong môi trường kiểm thử:

```text
client=SSLHandshakeException
```

**Điểm học quan trọng nhất:** SunJSSE có thể tạo TrustManager với **empty keystore** khi một file explicit truststore không tồn tại. Nó **không tự quay về `jssecacerts`/`cacerts`** trong nhánh này. Với các kết nối HTTPS khác, bạn có thể thấy nhiều lỗi certificate path dù trước khi đặt property chúng vẫn chạy tốt.

Đường dẫn tương đối cũng nguy hiểm: `client-trust.p12` được phân giải theo working directory của **process Java**, có thể khác giữa IDE, terminal, systemd service, Docker working dir hoặc Kubernetes container. Với production, ưu tiên đường dẫn tuyệt đối đã kiểm chứng và được mount đúng.

### 12.1. Không được chẩn đoán mọi lỗi dưới nhãn “file không tồn tại”

- Không tồn tại → default TrustManager có thể rỗng theo behavior SunJSSE.
- Sai password → có thể không load được PKCS12.
- Sai type/provider → có thể lỗi key store initialization.
- File thiếu CA phù hợp → chain không tìm thấy trust anchor.
- Certificate expired/not yet valid → kiểm tra ngày giờ.
- Server thiếu intermediate → thiếu bước xây chain.
- SAN không đúng → hostname mismatch.
- TLS protocol/cipher không tương thích → có thể lỗi handshake không liên quan trust roots.

Nhìn **exception chain** và log ở mức cần thiết thay vì tự thêm mọi certificate server vào truststore.

## 13. `SSLContext` riêng: không làm thay đổi trust của toàn process

Trong cùng `LocalTlsDemo.java`, chọn chế độ `scoped`:

```bash
java LocalTlsDemo server.p12 scoped client-trust.p12
```

Stdout đã kiểm thử:

```text
client=trusted
```

Trong chế độ này chương trình **không đặt** `javax.net.ssl.trustStore`. Nó:

1. Mở đúng file `client-trust.p12` bằng `KeyStore`.
2. Tạo `TrustManagerFactory` từ file đó.
3. Khởi tạo một `SSLContext` với trust managers riêng.
4. Lấy `SSLSocketFactory` **từ context vừa tạo**.
5. Tạo client TLS socket và bật hostname validation.
6. Handshake với server localhost.

Cách này rất phù hợp khi:

- Một ứng dụng gọi **nhiều outbound services** với các tập CA khác nhau.
- Cần giới hạn trust của một integration cụ thể thay vì sửa default trust global.
- Bạn muốn test truststore như dependency được inject vào client.
- Có policy khác nhau theo tenant/destination (với cấu trúc isolation rõ), không muốn một global CA thay đổi mọi kết nối.

**Tuy nhiên, `SSLContext` riêng không tự thêm các public CA mặc định.** `TrustManagerFactory.init(customKeyStore)` dùng các entries của custom KeyStore. Muốn giữ cả public roots và private CA, phải thiết kế tập trust anchors kết hợp thật sự.

### 13.1. Chương trình sử dụng `HttpClient` với scoped context

Trong ứng dụng thực, có thể dùng `java.net.http.HttpClient`:

```java
// Đoạn trong method, sau khi đã tạo SSLContext context
// bằng KeyStore và TrustManagerFactory như customContext(...).
java.net.http.HttpClient client =
        java.net.http.HttpClient.newBuilder()
                .sslContext(context)
                .build();
```

Đây là **đoạn minh họa phụ thuộc biến `context` đã tạo trước**, không phải file Java độc lập. Client đó dùng context được gán, trong khi client khác có thể dùng default SSLContext. Theo API `HttpClient`, cấu hình mặc định thường được lấy lúc instance được xây dựng; thay default system values **sau khi client đã build** không retroactively thay context của instance đã tồn tại.

**Không dùng scoped context với TrustManager “accept mọi certificate”**. Giữ `TrustManagerFactory` được khởi tạo từ CA đã phê duyệt để vẫn có PKIX validation.

## 14. Timing: system property và default SSLContext cache

Một bẫy khác:

```java
// Đoạn này minh họa thứ tự dễ gây nhầm, KHÔNG khuyến nghị:
javax.net.ssl.SSLContext oldDefault =
        javax.net.ssl.SSLContext.getDefault();

System.setProperty("javax.net.ssl.trustStore",
        "/secure/config/new-trust.p12");
```

Nếu default SSLContext, TrustManagers hoặc HTTP clients đã được tạo trước khi property đổi, **không thể dựa vào việc setProperty sẽ tái tạo mọi context/client và kết nối hiện tại**. Cơ chế khởi tạo/caching của implementation và thư viện có ảnh hưởng.

Cách đáng tin cậy:

- Đặt `-Djavax.net.ssl.trustStore=...` và type trước khi process Java khởi động các TLS clients.
- Kiểm tra môi trường/bootstrap và cấu hình ứng dụng trước khi tạo default `SSLContext`.
- Nếu cần **runtime rotation**, xây context/client mới từ truststore đã được xác minh và chuyển traffic theo lifecycle an toàn; không chỉ sửa `System.setProperty` rồi giả định mọi đối tượng cũ hot reload.
- Khi cần thay truststore toàn process và không có cơ chế reload an toàn của framework, **khởi động lại process** theo rollout đã kiểm thử là lựa chọn rõ ràng.

Một số thư viện như HTTP clients, application servers hoặc gRPC có cấu hình trust material riêng; ưu tiên dùng API chính thức của framework nếu nó hỗ trợ scoped TLS/hot reload. Global `-D` chỉ kiểm soát những thành phần đọc default JSSE truststore của runtime.

## 15. Truststore “thay thế” và bài toán vừa tin CA nội bộ vừa tin public Internet

Giả sử ứng dụng gọi:

- `https://api.internal.example` được ký bởi root CA riêng.
- `https://api.public.example` được ký bởi root public CA có trong default `cacerts`.

Nếu bạn cấu hình global truststore chỉ chứa private CA, client gọi public endpoint có thể mất đường tin cậy.

Có ba cách thiết kế phù hợp:

1. **Scoped TLS context:** chỉ client kết nối nội bộ dùng custom truststore, còn public client vẫn dùng default context.
2. **Truststore kết hợp:** phát hành một file truststore từ tập CA public/organization đã phê duyệt, thêm root nội bộ và quản lý cập nhật theo JDK/vendor policy.
3. **Trust manager composition có kiểm soát:** xây một chính sách minh bạch để kết hợp trust anchors, kiểm thử cả chain và hostname, không dùng logic “nếu manager A fail thì tin tất cả”.

Với phương án 2, tránh **chỉnh trực tiếp `$JAVA_HOME/lib/security/cacerts`** trên mỗi máy runtime: mỗi lần update JDK/image có thể thay đổi file, gây mất cấu hình hoặc trôi khỏi image digest. Tốt hơn là tạo artifact riêng được version cùng ứng dụng/runtime và giữ quy trình đồng bộ CA khi root stores cập nhật.

### 15.1. Không merge bằng cách ghép bytes hai file

PKCS12/JKS không phải file text danh sách PEM đơn giản. Không dùng `cat cacerts company-trust.p12 > merged.p12`. Phải dùng `KeyStore` API, `keytool -importkeystore` hoặc quy trình PKI được kiểm soát để copy/import đúng entries, aliases, types và passwords. Sau đó xác minh số/loại certs và test cả public lẫn private TLS paths.

### 15.2. Điều gì xảy ra khi một root CA bị thu hồi khỏi chính sách?

Ngay cả khi file `company-trust.p12` còn hợp lệ về format, nó có thể **không còn phù hợp chính sách** nếu chứa root bị rút quyền tin cậy. Truststore cần vòng đời cập nhật, audit alias/fingerprint, ngày hết hạn và loại bỏ CA không còn được duyệt.

Chứng thư root hết hạn hoặc sắp rollover cũng cần kế hoạch: thêm CA mới từ trước khi server chuyển chain, thử song song, rồi bỏ CA cũ đúng thời điểm. Không tự trust tất cả intermediate/leaf thấy trong TLS logs để làm “rotation”.

## 16. Chẩn đoán bằng JSSE debug

Khi kết nối TLS không thành công và cần biết **truststore nào được đọc**, có thể tạm bật JSSE debug:

```bash
java \
  -Djavax.net.debug=ssl,handshake,trustmanager \
  -Djavax.net.ssl.trustStore=/secure/config/company-trust.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
```

Trong các trường hợp cần đọc cert path building details, có thể dùng thêm:

```bash
java -Djava.security.debug=certpath -jar app.jar
```

Giới hạn:

- Log có thể rất dài, có thể lộ hostname nội bộ, subject certificate, đường dẫn file, cấu hình và các chi tiết handshake.
- Chỉ bật trong môi trường debug/điều tra có kiểm soát, hạn chế thời gian và phạm vi log.
- Dòng log cụ thể thay đổi theo JDK, provider và phiên bản TLS; đừng assert nguyên văn một dòng “trustStore is ...” trên mọi runtime.
- Debug **không tự sửa** trust anchor, SAN hoặc certificate chain.
- Đừng bật tùy chọn dump secrets/traffic nhạy cảm khi không thực sự cần; quản lý logs theo data-handling policy.

### 16.1. Các triệu chứng phổ biến và hướng xử lý

| Triệu chứng | Điều tra trước |
| --- | --- |
| `SSLHandshakeException` + `PKIX path building failed` | Trust anchor, chain, intermediate, path/truststore thực tế |
| `InvalidAlgorithmParameterException: trustAnchors parameter must be non-empty` | File store rỗng, explicit path sai hoặc initialization không có anchors |
| `No subject alternative names matching IP address ...` | Certificate SAN không có đúng IP/hostname đã kết nối |
| `No name matching ... found` | SAN/hostname mismatch, không phải root CA thiếu |
| `certificate expired` hoặc `NotBefore` | Validity và đồng hồ hệ thống |
| `algorithm constraints check failed` | Chữ ký, key length, disabled algorithms và chính sách JDK |
| `UnrecoverableKeyException` / `IOException` ở load store | Password, KeyStore type, corrupt file |
| SSL provider/TrustManagerFactory init error | Provider name/type/algorithm, permission hoặc store |
| Kết nối nội bộ được, public HTTPS thất bại | Custom truststore đã **thay** default public roots |
| HTTPS client A hoạt động, B không hoạt động | Hai client dùng context/providers/config khác nhau |
| mTLS báo “certificate required” | Client identity keyStore/KeyManager, không chỉ trustStore |
| Chạy local được, container không được | Path/mount/working dir, image JDK, environment flags và permission |

**Không dùng cách “sửa” lỗi TLS bằng trust-all manager hoặc tắt hostname verification.** Đó là tước bỏ thuộc tính xác thực server, có thể tạo lỗ hổng man-in-the-middle.

## 17. Quyền truy cập và độ tin cậy của chính file truststore

Một truststore là đầu vào quyết định **CA nào được tin**. Vì thế người có khả năng sửa/đổi file đó có thể mở rộng phạm vi tin cậy của client một cách nguy hiểm.

Tối thiểu cần:

1. Chỉ nhóm build/deploy tin cậy được tạo và thay file truststore.
2. Service runtime chỉ được **đọc**, không có quyền ghi/sửa/xóa/đổi tên file hoặc thư mục cha.
3. Bảo vệ đường dẫn, symlink, mount và các phần tử thư mục tổ tiên; “file read-only” đơn lẻ không đủ nếu thư mục cho người khác thay entry.
4. Kiểm tra fingerprint cert mới từ nguồn độc lập trước import.
5. Nếu quy trình cần kiểm tra integrity của truststore, dùng digest/provenance từ một signed/trusted release manifest.
6. Phiên bản hóa truststore cùng application/release; không sửa tại chỗ giữa các JVM/client instances đang chạy.
7. Giữ bản cũ và kế hoạch rollback khi CA rollover/chain thay đổi.
8. Theo dõi chủ động lỗi TLS sau rollout, không chỉ nhìn process đã start.
9. Không commit private keys hoặc mật khẩu thật vào source repo/JAR/image công khai.
10. Phân biệt root CA public certificate (không phải private key) với **private key** của server/client; private key cần bảo vệ nghiêm ngặt hơn.

**Truststore password không phải một chữ ký số về CA được chấp thuận.** Phải xác thực nguồn file và identity được quyền sửa file. Việc một file PKCS12 mở được bằng password không chứng minh root đã được security team duyệt.

### 17.1. Container/Kubernetes

Trong container, chọn path rõ ràng:

```bash
java -Djavax.net.ssl.trustStore=/etc/app/tls/trust.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -jar app.jar
```

Để test trong container, kiểm tra chính process nhìn thấy file và user đọc được nó. Một truststore được inject qua ConfigMap/Secret/mount có thể có permission và vòng đời thay đổi theo orchestrator. Không tự cho rằng file cập nhật qua mount làm **SSLContext đã tạo** tự reload; điều đó phụ thuộc framework/client.

Kubernetes Secret không tự động là giải pháp thay CA trust policy: cần kiểm soát người tạo Secret, scope đọc, rotation, encryption at rest theo cluster policy và cách tiến trình nhận bản mới.

### 17.2. Không log password để “chẩn đoán” việc trustStore không hoạt động

Nếu cần xác minh startup:

- Có thể log path **đã lọc/redact** và type của store.
- Kiểm tra file tồn tại, owner/group/quyền đọc, alias/fingerprint theo policy.
- Không in `javax.net.ssl.trustStorePassword` hoặc các biến môi trường bí mật ra logs.
- Đọc `javax.net.debug` ở môi trường được phép, giữ log theo thời gian ngắn.

## 18. Quản lý root CA rotation an toàn

Khi một CA nội bộ thay khóa/root:

1. Nhận root mới từ PKI đáng tin, xác minh fingerprint độc lập.
2. Tạo truststore mới ở staging, trong một thời gian có thể chứa cả **root cũ và root mới** nếu chính sách cho phép.
3. Test chain của server hiện tại và chain sau rollover.
4. Deploy truststore/SSLContext mới đến client trước khi server chuyển sang chain chỉ do root mới ký.
5. Quan sát handshake failure, tên server, đường trust path và các client instances chưa refresh.
6. Chuyển server certificates/chain theo kế hoạch.
7. Gỡ root cũ khỏi truststore sau khi hết cửa sổ chuyển tiếp và rủi ro được đánh giá.
8. Quản lý rollback: một rollback server chain có thể cần client vẫn tin root thích hợp.

Không nên “tạm thời tắt xác minh certificate” để vượt rollover, vì sẽ gây mất xác thực server đúng vào thời điểm cấu hình đang thay đổi.

### 18.1. Cẩn trọng với certificate pinning thủ công

Trong demo, ta import **leaf self-signed** làm trustedCertEntry để tạo kết quả trực quan, nhưng cách này có thể trở thành “pin” certificate: khi server thay certificate/key, client phải cập nhật store, nếu không kết nối thất bại.

Trong production, CA trust policy là lựa chọn phổ biến hơn cho tập server được quản lý bởi PKI. Nếu thật sự cần pinning, phải có chiến lược backup pins, rotation, threat model, expiration và vận hành phù hợp. Không ngẫu nhiên import mọi leaf để “cho chạy được”.

## 19. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Truststore là kho private key của server.” | Truststore thường chứa trusted certificates để xác thực **đối tác** |
| “`javax.net.ssl.trustStore` giúp client gửi certificate khi mTLS.” | Cần keyStore/private key/KeyManager cho identity của client |
| “`-D...trustStore` tự merge vào `cacerts`.” | Explicit store thường **thay** default trust anchors của SunJSSE |
| “Nếu path sai, Java sẽ tự quay về `cacerts`.” | SunJSSE có thể dùng **empty trust material** |
| “File `.p12` chắc chắn chứa CA hợp lệ.” | Đuôi file không xác minh type/contents/provenance |
| “File mở bằng password là file đáng tin.” | Password/integrity không chứng minh root được phê duyệt |
| “Chứng chỉ tự ký mặc nhiên tin được.” | Phải được chấp thuận như trust anchor theo policy |
| “Root CA đã tin thì hostname không cần kiểm tra.” | Chain trust và hostname/SAN đều quan trọng |
| “Raw `SSLSocket` luôn tự bật HTTPS hostname verification.” | Ví dụ tự bật `setEndpointIdentificationAlgorithm("HTTPS")` |
| “`javax.net.ssl.trustStorePassword` là certificate private key.” | Nó bảo vệ/đọc truststore, không tự cung cấp private key |
| “Đặt `-D` sau `-jar app.jar` vẫn là JVM option.” | Sau main/JAR thường là application arguments |
| “Có thể đổi `System.setProperty` sau startup để mọi client reload.” | Default SSLContext/client instances có cache/lifecycle riêng |
| “Một SSLContext riêng sẽ thay trust của mọi client khác.” | Nó chỉ ảnh hưởng các socket/client được tạo từ context đó |
| “`SSLHandshakeException` chắc chắn là thiếu root CA.” | Còn SAN, chain, expiry, algorithm, protocol, client-auth |
| “Import intermediate bất kỳ sẽ sửa mọi lỗi chain.” | Server nên gửi intermediate, trust anchors phải được duyệt |
| “Tin CA nội bộ sẽ luôn giữ tin public Internet.” | Không khi CA public bị thay bằng custom truststore riêng |
| “`trustStore=NONE` là flag trust all.” | Dùng cho non-file truststore/provider như PKCS11, không phải bypass |
| “`keytool -noprompt` luôn an toàn trong automation.” | Không nếu import certificate chưa xác minh fingerprint |
| “Sửa `cacerts` của JDK image trực tiếp là cách duy nhất.” | Có thể dùng custom scoped/merged store, tránh drift khi nâng JDK |
| “Không cần restart hoặc refresh SSLContext khi CA thay.” | Phải thiết kế lifecycle context/client theo framework |
| “Mật khẩu literal `changeit` trong demo là gợi ý production.” | Chỉ để bài test local dễ chạy |
| “Tin mọi certificate trong debug là cách xử lý sự cố hợp lệ.” | Không: đánh mất xác thực TLS |
| “Mọi TLS client Java đều dùng SunJSSE default properties.” | Provider, framework hoặc native TLS client có thể dùng cơ chế riêng |
| “SAN đúng nhưng chứng chỉ không có trusted chain vẫn được chấp nhận.” | Cần cả path trust và endpoint identification |

## 20. Bài tập kèm lời giải

### Bài 1 — Chọn đúng property

Một HTTPS client cần tin root CA nội bộ. Property default JSSE liên quan là gì?

**Đáp án:** `javax.net.ssl.trustStore` trỏ đến kho trusted certificates được phê duyệt; thường kèm `javax.net.ssl.trustStoreType=PKCS12` và cấu hình password phù hợp.

### Bài 2 — Khác biệt với keyStore

Một server yêu cầu client trình bày certificate mTLS. Chỉ đặt `trustStore` đã đủ chưa?

**Đáp án:** chưa. Client còn cần key material/private key qua `javax.net.ssl.keyStore`/`KeyManagerFactory` hoặc framework-specific identity configuration, và vẫn cần trust server.

### Bài 3 — Thứ tự tìm store

Không có `javax.net.ssl.trustStore`; cả `jssecacerts` và `cacerts` tồn tại. SunJSSE ưu tiên file nào?

**Đáp án:** `jssecacerts` của runtime hiện tại.

### Bài 4 — Explicit path không tồn tại

Bạn đặt `-Djavax.net.ssl.trustStore=/missing/trust.p12`. Có chắc Java quay về `cacerts`?

**Đáp án:** không. SunJSSE có thể khởi tạo empty trust material; nhiều TLS connections sẽ thất bại xác thực certificate.

### Bài 5 — File đúng nhưng hostname sai

Server gửi certificate dẫn tới root đã tin, nhưng SAN chỉ có `api-a.internal.example`; client kết nối `api-b.internal.example`. Có nên tắt hostname verification để test qua?

**Đáp án:** không. Sửa certificate SAN/endpoint name/route để khớp identity mong đợi; không bỏ qua xác thực hostname.

### Bài 6 — Tin CA nội bộ và public CA

Sau khi đặt custom truststore chỉ có root nội bộ, client public HTTPS bắt đầu lỗi. Vì sao?

**Đáp án:** default JSSE trust anchors bị thay bởi custom store, thiếu public roots. Dùng scoped context hoặc tạo truststore kết hợp được kiểm soát.

### Bài 7 — Cài CA trước khi kiểm tra fingerprint

Nhận file root CA trong email không xác thực. Có nên import ngay với `-noprompt`?

**Đáp án:** không. Kiểm tra chain/provenance và SHA-256 fingerprint từ kênh độc lập tin cậy trước khi đưa certificate thành trust anchor.

### Bài 8 — Kết quả loopback

Sau khi tạo `client-trust.p12`, chạy:

```bash
java -Djavax.net.ssl.trustStore=client-trust.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -Djavax.net.ssl.trustStorePassword=changeit \
     LocalTlsDemo server.p12 default
```

Trong bài demo đã kiểm thử, kết quả client là gì?

**Đáp án:** `client=trusted`, vì trustedCertEntry của demo phù hợp certificate server, và SAN đúng IP loopback.

### Bài 9 — Scoped context

Không muốn sửa default TLS của toàn process, làm thế nào?

**Đáp án:** load `KeyStore` riêng, dùng `TrustManagerFactory.init(store)`, tạo `SSLContext.getInstance("TLS")` + `init(null, trustManagers, null)` rồi gán cho một `HttpClient`/socket factory cụ thể.

### Bài 10 — Thời điểm cấu hình

Một `HttpClient` đã được build trước khi bạn set `javax.net.ssl.trustStore`. Có chắc client đó đổi trust ngay?

**Đáp án:** không. Client có default SSLContext lấy lúc build và các cơ chế cache; phải dùng đúng lifecycle/rebuild context/client hoặc restart khi cần.

### Bài 11 — `PKIX path building failed`

Lỗi này có đủ để kết luận “server certificate bị hacker thay”?

**Đáp án:** không. Có thể thiếu CA, thiếu intermediate, sai truststore/path, policy hoặc chứng chỉ không hợp lệ. Điều tra chain và nguồn certificate trước khi thay đổi trust policy.

### Bài 12 — `SSLHandshakeException` bất kể đã import

Sau import root, client vẫn lỗi `No subject alternative names matching IP address 127.0.0.1`. Tiếp theo làm gì?

**Đáp án:** certificate leaf của server cần có IP SAN `127.0.0.1`, hoặc client kết nối tới tên DNS phù hợp SAN. Không tắt endpoint identification.

### Bài 13 — Password command line

Có nên in `javax.net.ssl.trustStorePassword` ra log để debug không?

**Đáp án:** không. Đối chiếu path/type và quyền file mà không để lộ password. Với production, dùng secret/config handling được bảo vệ.

### Bài 14 — Root rollover

Một CA root sắp thay. Nên xóa root cũ khỏi mọi client trước khi server chuyển certificate mới?

**Đáp án:** không mặc định. Lập kế hoạch overlap cũ/mới theo trust policy, phân phối truststore mới trước khi đổi chain, kiểm thử và loại root cũ ở thời điểm đã được phê duyệt.

### Bài 15 — Test self-signed localhost

Vì sao kết quả loopback tin leaf self-signed không phải một hướng dẫn production tổng quát?

**Đáp án:** đây là certificate tự tạo cho môi trường cô lập. Server thật cần PKI/CA được duyệt, chứng chỉ đúng SAN và quy trình rotation, cùng trust policy rõ.

### Bài 16 — Store type

File `client-trust.p12` được tạo với `-storetype PKCS12`. Nên đặt property loại gì?

**Đáp án:** `javax.net.ssl.trustStoreType=PKCS12`. Đuôi file không thay được việc xác nhận định dạng.

### Bài 17 — Scope provider

Một thư viện HTTP dùng TLS engine riêng, không phản hồi khi bạn đặt `javax.net.ssl.trustStore`. Có nghĩa JVM lỗi?

**Đáp án:** không nhất thiết. Kiểm tra thư viện/framework đang tạo SSLContext hay TrustManager riêng và cấu hình TLS chính thức của nó.

### Bài 18 — Trace logs

Bật `-Djavax.net.debug=ssl,handshake,trustmanager` cho toàn production để theo dõi mọi request có tốt không?

**Đáp án:** không mặc định. Log có thể rất dài, lộ metadata nhạy cảm và tăng chi phí. Chỉ bật theo phạm vi, thời gian và chính sách chẩn đoán thích hợp.

## 21. Checklist triển khai

1. **Truststore này dùng để tin server nào, dưới root CA nào?** Có scope rõ?
2. Đã xác minh CA fingerprint qua kênh độc lập?
3. Truststore có đúng type `PKCS12`/provider và entry `trustedCertEntry` không?
4. Có phân biệt truststore với identity keystore/private key?
5. Có tránh import certificate chưa rõ nguồn hoặc dùng `-noprompt` bừa bãi?
6. Có đặt `javax.net.ssl.trustStore` đúng trước main/JAR?
7. Có bảo đảm path absolute, file tồn tại, readable và mount đúng trong container?
8. Có tránh giả định explicit path lỗi sẽ tự fallback `cacerts`?
9. Có bảo vệ mật khẩu, file và thư mục chứa truststore?
10. Có tránh hardcode mật khẩu vào repo, process args production và logs?
11. Có xác minh rằng custom truststore **thay** hay **được kết hợp** với public roots theo thiết kế?
12. Có giữ tách biệt clients dùng CA nội bộ và clients public nếu cần?
13. Có kiểm tra JSSE provider/framework thực sự đọc system properties?
14. Có bật endpoint identification/hostname verification ở đúng client API?
15. Có kiểm tra SAN của leaf certificate và certificate chain?
16. Có biết server đã gửi intermediate đầy đủ?
17. Có phân biệt PKIX path building failure với hostname mismatch và mTLS client-auth failure?
18. Có tránh TrustManager “trust all”/HostnameVerifier luôn true?
19. Có chọn scoped SSLContext khi cần nhiều trust policies trong một JVM?
20. Có hiểu default SSLContext/client caching và yêu cầu restart/rebuild khi rotation?
21. Có test truststore mới trước rollout và giữ rollback?
22. Có kế hoạch root/intermediate/leaf expiration và CA rollover?
23. Có gắn truststore với release/JDK image/policy thay vì sửa `cacerts` bừa bãi?
24. Có giới hạn `javax.net.debug` và bảo vệ TLS logs?
25. Có test success **và** negative cases: unknown CA, sai SAN, path sai?
26. Có kiểm soát độ tin cậy của artifact và user được quyền cập nhật root?
27. Có biết `trustStore=NONE` chỉ dùng non-file keystore/provider phù hợp, không bypass?
28. Có giữ TLS protocol/cipher/algorithm restrictions còn an toàn, không bật SSL legacy vì lỗi trust?
29. Có ghi nhận JDK vendor/build, framework client version và truststore aliases khi xử lý sự cố?
30. Có rà soát những roots không còn cần thiết để giảm trust surface?

## 22. Tổng kết

**`javax.net.ssl.trustStore` cho SunJSSE default TrustManager biết dùng kho chứng thư tin cậy nào để xác minh đối tác TLS.** Một truststore riêng `PKCS12` có thể chứa root CA của tổ chức, nhưng phải được tạo từ certificate đã xác minh fingerprint, đặt quyền file phù hợp và quản lý như artifact bảo mật.

Khi khai báo file cụ thể, bạn thường **thay tập root CA mặc định**, chứ không tự merge vào `cacerts`. Đường dẫn explicit sai có thể dẫn đến **truststore rỗng** và lỗi TLS bất ngờ. Truststore không thay thế identity keystore/mTLS, không bỏ qua hostname verification và không đảm bảo mọi client sử dụng nếu chúng có `SSLContext` riêng.

Bài thử `localhost` đã chứng minh cùng certificate: default client từ chối, custom property truststore chấp nhận, path missing từ chối, và scoped `SSLContext` chấp nhận. Phương án production nên ưu tiên trust policy rõ theo từng integration, CA đã được phê duyệt, certificate chain/SAN hợp lệ, quản lý rollover có kiểm soát và **không bao giờ sửa lỗi TLS bằng cách tắt xác thực chứng chỉ hoặc hostname**.

### Tài liệu chính thức

- [Oracle Java SE 21 — JSSE Reference Guide, Customizing Default Truststores](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Oracle Java SE 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Oracle Java SE 21 — keytool Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
- [Oracle Java SE 21 — SSLContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Oracle Java SE 21 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Oracle Java SE 21 — KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
- [Oracle Java SE 21 — SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Oracle Java SE 21 — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 21 — Java Secure Socket Extension Debugging](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html#GUID-9A21C19D-1C6F-4FB6-877C-11DAF1DE7C61)