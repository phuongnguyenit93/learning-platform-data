# Không tắt kiểm tra certificate để sửa lỗi tạm thời

## 1. Tình huống quen thuộc và mục tiêu bài học

Một dịch vụ Java dùng **Spring LDAP** cần đọc thông tin nhân viên từ máy chủ LDAP. `LdapTemplate` gọi `search`, nhưng sau khi đội vận hành gia hạn chứng thư TLS của máy chủ, ứng dụng bắt đầu báo lỗi tương tự `SSLHandshakeException: PKIX path building failed`. Một đề xuất thường xuất hiện là “tạm thời cho Java tin mọi certificate để hệ thống hoạt động lại”.

Đề xuất đó rất nguy hiểm. **TLS chỉ thực sự bảo vệ kết nối tới đúng máy chủ khi client kiểm tra chứng thư và danh tính endpoint**. Nếu bỏ kiểm tra để vượt qua lỗi, ứng dụng có thể tạo kênh mã hóa với **máy chủ giả mạo**, gửi tài khoản bind hoặc chấp nhận dữ liệu LDAP bị kẻ tấn công điều khiển. Chế độ “tạm thời” còn có xu hướng bị giữ nguyên qua lần triển khai tiếp theo.

Bài học thuộc chương **TLS và bảo mật kết nối** của **SPRING_LDAP** này làm rõ:

- Những kiểm tra nào phải được giữ lại trong LDAPS và StartTLS.
- Vì sao “trust all certificates”, bỏ hostname verification hoặc fallback sang LDAP không mã hóa gây rủi ro.
- Cách chẩn đoán đúng lỗi truststore, certificate chain, SAN/hostname, hiệu lực chứng thư và cấu hình Java.
- Cách khôi phục dịch vụ an toàn và viết kiểm thử nhằm phát hiện hành vi bỏ qua certificate validation.

Nguyên tắc xuyên suốt: **khi không thể xác minh máy chủ, dừng kết nối trước khi LDAP bind hoặc truy vấn nhạy cảm** (*fail closed*). Khắc phục nguyên nhân chứng thư, thay vì hạ tiêu chuẩn bảo mật của client.

## 2. “Có TLS” và “tin đúng máy chủ” là hai điều kiện khác nhau

Spring LDAP thao tác với thư mục qua `ContextSource` (thường là `LdapContextSource`). Cơ chế bảo mật kết nối thường được thực hiện bởi **Java JNDI/JSSE**:

- **LDAPS:** TLS bắt đầu ngay khi kết nối đến URL `ldaps://directory.example.org:636`.
- **StartTLS:** ứng dụng kết nối `ldap://directory.example.org:389`, yêu cầu nâng cấp StartTLS, hoàn tất bắt tay TLS rồi mới thực hiện bind.

Một phiên TLS có thể mã hóa lưu lượng nhưng vẫn **không xác thực đúng máy chủ** nếu client chấp nhận mọi chứng thư hoặc bỏ qua tên endpoint. Mã hóa lúc đó bảo vệ đường truyền **tới đối tượng đang kết nối**, chứ không bảo đảm đối tượng đó là dịch vụ thư mục được phép.

### 2.1. Hệ quả trong ứng dụng Spring LDAP

Giả sử tài khoản `cn=app-reader,ou=services,dc=example,dc=org` dùng simple bind rồi đọc `mail` và `memberOf`. Nếu kẻ tấn công điều khiển DNS, proxy hoặc một điểm chuyển tiếp mạng và client bỏ certificate validation, máy chủ giả có thể được chấp nhận trong quá trình TLS.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring LDAP
    participant Fake as Máy chủ giả
    participant Real as Máy chủ LDAP thật
    Note over App: Client tắt kiểm tra certificate/hostname
    App->>Fake: Kết nối tưởng là directory.example.org
    Fake-->>App: Chứng thư TLS không đáng tin hoặc sai tên
    Note over App,Fake: TLS vẫn có thể hình thành do client bỏ kiểm tra
    App->>Fake: LDAP simple bind và search trong kênh TLS tới máy chủ giả
    Fake-->>App: Dữ liệu LDAP do kẻ tấn công quyết định
    Note over Real: Server thật không tham gia phiên này
~~~

Rủi ro thực tế phụ thuộc khả năng kiểm soát đường truyền và loại LDAP bind, nhưng có thể bao gồm **lộ mật khẩu tài khoản dịch vụ**, **trả về danh sách nhóm sai**, **đọc thông tin nhạy cảm từ ứng dụng** hoặc **thao túng quyết định phân quyền**. Một tài khoản chỉ đọc vẫn có thể cung cấp dữ liệu giá trị cho kẻ tấn công nếu thông tin xác thực bị lộ.

TLS bảo vệ tính bí mật và toàn vẹn khi được triển khai đúng; kiểm tra chứng thư và hostname giúp bảo đảm những thuộc tính đó gắn với **đúng đối tác**.

## 3. Những kiểm tra certificate không được bỏ qua

### 3.1. Xây và xác minh certificate chain

Máy chủ thường trình bày một chứng thư **leaf/server** và các chứng thư **intermediate CA** cần thiết. Client dùng **truststore** để xác định trust anchor được phép tin, thường là root CA hoặc một CA đã được tổ chức xác minh.

~~~text
Truststore của JVM
  Example Root CA (trust anchor tin cậy)
        |
        +-- Example Issuing CA (intermediate)
                  |
                  +-- directory.example.org (server certificate)
~~~

Quá trình xác minh đường dẫn chứng thư (certificate path/PKIX) gồm các kiểm tra phù hợp như chữ ký số, thời hạn hiệu lực, ràng buộc CA, `Key Usage`, `Extended Key Usage`, chính sách thuật toán và khả năng xây chuỗi tới trust anchor tin cậy.

**Thiếu intermediate** hoặc **truststore không có CA đúng** có thể gây lỗi `PKIX path building failed`. Cách xử lý là xác minh nguồn CA và sửa cấu hình chain/truststore, **không đổi trust manager sang loại chấp nhận mọi chứng thư**.

### 3.2. Hostname verification

Khi ứng dụng dùng `ldaps://directory.example.org:636`, chứng thư server phải có danh tính phù hợp, thường là SAN `DNS:directory.example.org`. Một chứng thư hợp lệ do cùng CA cấp cho `other.example.org` không thể thay thế.

| Tên đích của ứng dụng | SAN server certificate | Kết quả dự kiến |
| --- | --- | --- |
| `directory.example.org` | `DNS:directory.example.org` | Khớp, nếu các kiểm tra khác cũng đạt |
| `directory.example.org` | `DNS:ldap-node-01.example.org` | Không khớp |
| `10.20.30.40` | `IP Address:10.20.30.40` | Có thể khớp nếu chính sách và chuỗi hợp lệ |
| `10.20.30.40` | `DNS:directory.example.org` | Không đủ để xác thực đích là IP |

Không dựa vào việc hai hostname cùng trỏ về một IP để bỏ so khớp SAN. Chứng thư có wildcard cũng phải tuân thủ quy tắc hostname matching; không dùng wildcard như cách chấp nhận bất kỳ tên nào.

Trong Java/JNDI, hành vi hostname verification phụ thuộc đường kết nối, phiên bản JDK và các tùy biến TLS. Vì thế, cần **kiểm thử âm tính**: dùng chứng thư có chain hợp lệ nhưng SAN không khớp và xác nhận chính tiến trình Java từ chối kết nối. Cần thử riêng cả LDAPS lẫn StartTLS nếu hệ thống sử dụng hai cơ chế.

### 3.3. Thời hạn, mục đích và trạng thái chứng thư

Một chứng thư có thể không được chấp nhận vì:

- Chưa tới ngày `Not Before` hoặc đã quá `Not After`.
- Đồng hồ hệ thống sai khiến đánh giá thời gian bị lệch.
- Chứng thư CA không có `BasicConstraints` thích hợp hoặc chain không thỏa các ràng buộc áp dụng.
- Chứng thư server bị ràng buộc `Extended Key Usage` không phù hợp cho mục đích TLS server.
- Thuật toán/chìa khóa không đáp ứng chính sách bảo mật của JVM.
- Chứng thư bị thu hồi theo chính sách **nếu** kiểm tra revocation (CRL/OCSP) được bật và triển khai đúng.

Không mặc định mọi Java runtime luôn bật kiểm tra thu hồi chứng thư. Nếu tổ chức yêu cầu CRL/OCSP, phải cấu hình và kiểm thử đường kiểm tra đó. Không khắc phục sự cố bằng cách vô hiệu hóa mọi bước xác minh.

### 3.4. Xác minh server khác với xác thực LDAP

**TLS handshake thất bại** thường xảy ra trước LDAP bind. Sau khi TLS hợp lệ, LDAP vẫn có thể trả `invalidCredentials` do sai DN/mật khẩu, hoặc từ chối `search` do ACL. Cần phân biệt lỗi để sửa đúng nguyên nhân:

| Giai đoạn | Ví dụ sự cố | Nhóm xử lý |
| --- | --- | --- |
| TLS handshake | CA không tin cậy, SAN sai, chứng thư hết hạn | Certificate chain, truststore, endpoint/TLS |
| LDAP bind | `invalidCredentials` | DN, mật khẩu, phương thức xác thực và chính sách LDAP |
| LDAP search/modify | Không đủ quyền hoặc base DN sai | ACL, DN, filter, schema |

Thay truststore không giải quyết được sai mật khẩu LDAP; ngược lại, sửa thông tin bind không giải quyết được chứng thư server không hợp lệ.

## 4. Những “sửa lỗi tạm thời” cần loại bỏ

| Cách làm sai | Điều xảy ra | Hướng xử lý an toàn |
| --- | --- | --- |
| Dùng custom trust manager chấp nhận **mọi certificate** | Client mất kiểm tra chuỗi tin cậy; máy chủ giả dễ được chấp nhận | Khôi phục trust manager kiểm tra chuẩn, nhập đúng CA đã xác minh |
| Dùng hostname verifier luôn chấp nhận mọi tên | Chứng thư hợp lệ cho máy chủ khác vẫn có thể được dùng | Cấp chứng thư có SAN đúng hoặc sử dụng hostname chính xác |
| Vô hiệu hóa endpoint identification của JNDI/Java | Làm yếu hoặc bỏ kiểm tra hostname cho LDAPS | Khắc phục SAN/URL và bật lại kiểm tra danh tính |
| Bỏ cấu hình StartTLS khi gặp lỗi | Simple bind có thể đi trên `ldap://` chưa được mã hóa | Dừng kết nối; sửa StartTLS và yêu cầu nâng cấp trước bind |
| LDAPS lỗi thì tự thử lại bằng LDAP rõ | Từ chối TLS bị biến thành lộ dữ liệu trên mạng | Retry chỉ tới endpoint TLS hợp lệ; không hạ cấp |
| Nhập tùy tiện leaf certificate lấy từ kết nối đang lỗi vào truststore | Có thể biến chứng thư của máy chủ giả thành đối tượng được tin | Xác minh CA/chuỗi bằng nguồn PKI đáng tin, quản lý trust anchor có kiểm soát |
| Tắt kiểm tra chứng thư trong môi trường test rồi giữ nguyên khi phát hành | Đường không an toàn dễ lan sang staging/production | Thử nghiệm với CA lab tin cậy, thêm kiểm thử chặn cấu hình yếu |

Lưu ý: **certificate pinning** hoặc chủ động tin một chứng thư server sau khi xác minh ngoài băng có thể là một lựa chọn kiến trúc có kiểm soát trong trường hợp cụ thể. Tuy nhiên, nhập bừa chứng thư từ kết nối lỗi, bỏ hostname verification hoặc cố định chứng thư không có quy trình gia hạn **không phải cách sửa PKIX an toàn**. Với dịch vụ thư mục doanh nghiệp, quản lý CA và chuỗi chứng thư hợp lệ thường bền vững hơn.

### 4.1. Vì sao “chỉ vài phút” vẫn nguy hiểm?

Trong khoảng thời gian kiểm tra bị tắt, ứng dụng có thể thực hiện nhiều phiên bind và tìm kiếm. Các cờ cấu hình có thể bị sao chép sang môi trường khác, xuất hiện trong container image hoặc được quên trong cấu hình runtime. Kiểm thử chức năng thường chỉ xác nhận “truy vấn đã chạy”, không phát hiện được rằng client đã bỏ xác minh danh tính.

Một quyết định khôi phục dịch vụ cần cân nhắc tính sẵn sàng, nhưng **không thể coi kết nối LDAP không được xác thực máy chủ là phương án an toàn chỉ vì được gắn nhãn tạm thời**. Nếu chưa có endpoint đáp ứng TLS, cần dừng hoặc giới hạn chức năng phụ thuộc LDAP theo phương án vận hành đã được phê duyệt.

## 5. Phân tích đúng nguyên nhân lỗi

Thay vì bắt đầu từ việc tắt kiểm tra certificate, hãy xác định chính xác **lỗi thuộc bước nào**.

| Dấu hiệu thường thấy | Nguyên nhân có thể | Bằng chứng nên thu thập | Cách khắc phục phù hợp |
| --- | --- | --- | --- |
| `PKIX path building failed` hoặc `unable to find valid certification path` | JVM không tin CA, thiếu intermediate, đang dùng truststore khác | Chain server, alias trong truststore, JVM và đường dẫn cấu hình | Cấp đủ intermediate từ server; thêm CA đã xác minh vào truststore đúng |
| `No subject alternative DNS name matching` | URL không khớp SAN | Hostname URL thực tế và SAN của leaf certificate | Cấp lại chứng thư hoặc sửa URL sang đúng endpoint được phép |
| `CertificateExpiredException` | Chứng thư hết hạn | `Not After`, thời gian hệ thống | Gia hạn/cấp lại và triển khai chain mới |
| `CertificateNotYetValidException` | Chứng thư chưa có hiệu lực hoặc lệch đồng hồ | `Not Before` và thời gian đồng bộ NTP | Sửa thời gian hoặc triển khai chứng thư hợp lệ |
| `Received fatal alert: certificate_unknown` | Phía peer từ chối chứng thư; có thể liên quan mTLS | Log JSSE và log máy chủ, client certificate, issuer | Kiểm tra đúng phía từ chối và chính sách CA/mTLS |
| `handshake_failure` / `protocol_version` | Có thể do TLS version, cipher, thuật toán hoặc chứng thư | Phiên bản TLS, chính sách JDK và cấu hình server | Điều chỉnh cấu hình tương thích nhưng vẫn đạt chính sách bảo mật |
| Kết nối TCP thành công nhưng LDAP bind lỗi | Có thể là lỗi xác thực LDAP sau TLS | Kết quả TLS và LDAP BindResponse | Kiểm tra bind DN/credential/quyền, giữ nguyên kiểm tra TLS |
| OpenSSL hợp lệ nhưng Java lỗi | OpenSSL và JSSE dùng truststore/chính sách khác | Java runtime, JSSE debug, truststore JVM, custom socket factory | Sửa cấu hình của **chính JVM chạy ứng dụng** |

Các chuỗi lỗi chỉ là ví dụ, không phải ánh xạ một-một; Spring LDAP có thể bọc ngoại lệ JNDI trong exception riêng. Cần đọc **cause chain** của lỗi và thời điểm xảy ra thay vì suy đoán từ tên exception ngoài cùng.

### 5.1. Quy trình chẩn đoán từng bước

1. **Xác định đích thật:** ghi nhận hostname, cổng, URI `ldap://` hoặc `ldaps://`, node dự phòng, proxy và tên mà ứng dụng sử dụng.
2. **Xác định loại TLS:** LDAPS bắt tay ngay; StartTLS phải được nâng cấp bắt buộc trước bind. Nếu server không hỗ trợ StartTLS, không được tự chuyển xuống kết nối rõ.
3. **Kiểm tra chứng thư server:** subject, issuer, SAN, hạn dùng, intermediate, mục đích sử dụng và các ràng buộc PKI.
4. **Kiểm tra truststore thật của Java:** đường dẫn cấu hình, JDK đang chạy, alias CA, các custom SSLContext/socket factory, và quyền truy cập file.
5. **Kiểm tra hostname:** so SAN với hostname từ URL được ứng dụng gửi, kể cả tên service/load balancer.
6. **Thử từ chính ứng dụng:** xác minh kết nối an toàn thành công và các trường hợp CA/SAN sai bị từ chối.
7. **Khôi phục có kiểm soát:** chỉ mở lại đường LDAP sau khi cấu hình xác minh máy chủ hoạt động và không còn fallback không mã hóa.

### Sơ đồ xử lý lỗi

~~~mermaid
flowchart TD
    A["Spring LDAP báo lỗi kết nối"] --> B{"Có lỗi TLS handshake hoặc PKIX?"}
    B -- "Không" --> C["Chẩn đoán mạng, LDAP bind, ACL và truy vấn"]
    B -- "Có" --> D{"Certificate chain tới CA tin cậy hợp lệ?"}
    D -- "Không" --> E["Sửa CA/truststore hoặc intermediate"]
    D -- "Có" --> F{"SAN khớp hostname endpoint?"}
    F -- "Không" --> G["Sửa hostname hoặc cấp lại certificate"]
    F -- "Có" --> H["Kiểm tra hạn dùng, thuật toán, TLS policy, mTLS"]
    E --> I["Thử lại TLS với kiểm tra đầy đủ"]
    G --> I
    H --> I
    I --> J{"TLS được xác minh từ JVM thật?"}
    J -- "Không" --> K["Giữ fail closed, tiếp tục điều tra"]
    J -- "Có" --> L["Cho phép LDAP bind và các thao tác cần thiết"]
~~~

## 6. Dùng công cụ để kiểm chứng chứng thư đúng cách

Các ví dụ sử dụng tên miền giả định `directory.example.org`. Chỉ thử trên endpoint và môi trường được phép; không dùng dữ liệu LDAP thật hoặc bí mật sản xuất khi kiểm thử.

### 6.1. Kiểm tra certificate trong file

~~~bash
# Xem danh tính, issuer, thời hạn và Subject Alternative Name.
openssl x509 -in directory-server.pem \
  -noout -subject -issuer -dates -ext subjectAltName

# Xem thông tin chứng thư CA do tổ chức cung cấp.
keytool -printcert -v -file directory-root-ca.pem
~~~

Một file chứng thư hợp lệ về cú pháp không chứng minh máy chủ đang sử dụng file đó. Phải kiểm tra **certificate chain thực tế được server gửi** ở cổng kết nối.

### 6.2. Xác minh endpoint LDAPS

~~~bash
openssl s_client \
  -connect directory.example.org:636 \
  -servername directory.example.org \
  -showcerts \
  -CAfile directory-root-ca.pem \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

Ý nghĩa các cờ:

- `-connect` chọn endpoint TLS cần thử.
- `-servername` cung cấp SNI khi máy chủ/hạ tầng sử dụng SNI; không thay hostname verification.
- `-showcerts` hiển thị các chứng thư mà server thực sự trình bày.
- `-CAfile` chỉ định nguồn CA tin cậy **đã được xác minh trước** cho phép thử bằng OpenSSL.
- `-verify_hostname` yêu cầu so khớp tên máy chủ.
- `-verify_return_error` yêu cầu lỗi xác minh ảnh hưởng đến quá trình bắt tay thay vì chỉ in cảnh báo.

Không kết luận an toàn chỉ từ dòng `CONNECTED`. Cần xem trạng thái xác minh chứng thư và những cảnh báo có liên quan. OpenSSL không nhất thiết dùng cùng tập CA và cùng chính sách với JVM của ứng dụng.

### 6.3. Xác minh endpoint StartTLS

~~~bash
openssl s_client \
  -starttls ldap \
  -connect directory.example.org:389 \
  -showcerts \
  -CAfile directory-root-ca.pem \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

`-starttls ldap` gửi yêu cầu nâng cấp trước bắt tay TLS. Phản hồi LDAP chấp nhận StartTLS **chưa đủ**; phải hoàn tất và xác minh TLS. Nếu máy chủ từ chối nâng cấp hoặc chứng thư không hợp lệ, ứng dụng không được gửi simple bind trên kết nối rõ.

### 6.4. Kiểm tra Java truststore

Giả sử nhóm PKI đã cung cấp và xác minh CA nội bộ `directory-root-ca.pem`. Có thể tạo truststore riêng cho ứng dụng:

~~~bash
# keytool sẽ yêu cầu mật khẩu cho truststore khi cần.
keytool -importcert \
  -alias directory-root \
  -file directory-root-ca.pem \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12

# Kiểm tra lại certificate đã nhập, gồm fingerprint.
keytool -list -v \
  -alias directory-root \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
~~~

Trước khi nhập, đối chiếu subject/fingerprint với hồ sơ CA từ kênh PKI đáng tin; không chấp nhận certificate mới một cách tự động chỉ vì nó xuất hiện trên endpoint đang lỗi.

Khi chạy ứng dụng có thể chỉ định truststore bằng thuộc tính JVM:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/security/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đây là đường dẫn minh họa. Nếu truststore có mật khẩu, cần cấp phát bí mật theo quy trình của môi trường, không đặt trực tiếp trong hướng dẫn hoặc log. Các thuộc tính JSSE mặc định có thể ảnh hưởng các tích hợp TLS **khác** trong cùng JVM. Trước khi thay truststore toàn tiến trình, hãy đánh giá nhu cầu tin cậy CA của HTTPS và các dịch vụ còn lại. Nếu dùng custom SSLContext/socket factory, xác nhận nó nạp trust anchors mong muốn.

### 6.5. Chẩn đoán từ JVM chạy Spring LDAP

Trong môi trường thử nghiệm, có thể bật debug TLS của Java:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
~~~

Các log này giúp xác định certificate chain, trust anchor và lý do xác minh không thành công. Chỉ bật có kiểm soát và tắt sau khi điều tra; log có thể chứa metadata kết nối/chứng thư hoặc thông tin cần bảo vệ. Bản ghi TLS của OpenSSL **không thay thế** kết quả từ JVM và cách JNDI/Spring LDAP thiết lập kết nối thực tế.

## 7. Cấu hình Spring LDAP an toàn khi khắc phục lỗi

### 7.1. Giữ LDAPS và xác minh danh tính server

Với Spring Boot và auto-configuration Spring LDAP, dùng endpoint an toàn:

~~~yaml
# application.yml — tên miền và DN là giả định
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Mật khẩu đến từ biến môi trường, tránh ghi cứng vào mã nguồn. Điều này giảm rủi ro lộ secret trong repository nhưng **không thay certificate validation**. JVM vẫn phải có trust anchors phù hợp và kiểm tra hostname của `directory.example.org`.

Nếu cùng ứng dụng còn dùng `LdapClient`, ODM, một `LdapContextSource` riêng hoặc kết nối JNDI trực tiếp, tất cả đường truy cập thư mục nhạy cảm đều phải duy trì chính sách TLS tương tự.

### 7.2. Với StartTLS, không tắt nâng cấp hoặc hostname validation

Nếu máy chủ cung cấp StartTLS, cách cấu hình source cho simple bind có thể là:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryStartTlsConfiguration {

    @Bean
    LdapContextSource ldapContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldap://directory.example.org:389");
        source.setBase("dc=example,dc=org");
        source.setUserDn("cn=app-reader,ou=services,dc=example,dc=org");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        source.setPooled(false);
        source.setAuthenticationStrategy(
            new DefaultTlsDirContextAuthenticationStrategy()
        );
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

`ldap://` ở đây là **kết nối ban đầu để yêu cầu StartTLS**, không phải sự cho phép gửi simple bind trên kênh rõ. Phải kiểm chứng rằng chiến lược nâng cấp TLS thực sự được sử dụng cho từng context và xử lý lỗi bằng cách dừng trước bind. `setPooled(false)` giúp tránh native JNDI pooling với StartTLS; nếu có pooling wrapper riêng, phải thử hành vi tái sử dụng phiên TLS.

Trong các cấu hình có custom `HostnameVerifier`, trust manager hoặc `SSLSocketFactory`, cần rà soát để bảo đảm không có nhánh **bỏ qua xác minh**. Không cần viết một verifier cho phép tất cả tên: phải giữ kiểm tra SAN/hostname theo đúng yêu cầu của endpoint.

### 7.3. Không thay thế cách xác thực để né lỗi TLS

`ExternalTlsDirContextAuthenticationStrategy` dùng cho StartTLS kết hợp **SASL EXTERNAL**, thường liên quan chứng chỉ client ở tầng TLS. Nó có những yêu cầu khác với chiến lược StartTLS + simple bind. Đổi chiến lược xác thực tùy tiện không giải quyết được sự cố certificate chain của LDAP server, và có thể gây lỗi hoặc ánh xạ sai danh tính ứng dụng.

Với cả LDAPS, StartTLS + simple bind và StartTLS + SASL EXTERNAL, **máy chủ vẫn phải được client xác minh**. Đừng xem việc một cơ chế xác thực LDAP trả thành công là bằng chứng hostname verification đã hoạt động nếu ứng dụng từng cấu hình bỏ qua nó.

## 8. Phương án khôi phục dịch vụ không hạ tiêu chuẩn TLS

Khi ứng dụng không kết nối được do certificate, có thể xử lý theo mức độ ưu tiên vận hành:

1. **Cô lập đúng nguyên nhân:** thu thập lỗi và chain server từ endpoint thực; kiểm tra cấu hình JVM, SAN và thời gian hệ thống.
2. **Dùng endpoint dự phòng đã được kiểm chứng** nếu có. Đảm bảo URL, certificate chain và hostname riêng của node dự phòng đều hợp lệ. Không trộn LDAP rõ làm phương án dự phòng.
3. **Khắc phục chứng thư tại nguồn:** triển khai lại intermediate thiếu, gia hạn certificate, sửa SAN hoặc cập nhật truststore bằng CA được phê duyệt.
4. **Kiểm tra lại từ ứng dụng thật:** kết nối hợp lệ phải thành công, còn CA/SAN sai vẫn bị từ chối.
5. **Khôi phục chức năng LDAP** sau khi TLS hợp lệ; nếu chưa thể khôi phục endpoint an toàn, áp dụng chế độ suy giảm dịch vụ phù hợp nghiệp vụ (ví dụ tạm ngưng tác vụ phụ thuộc thư mục).

Trong môi trường phát triển, có thể thiết lập CA lab riêng được tin cậy có chủ đích, cấp certificate có SAN chính xác cho hostname lab rồi kiểm thử. Đó là cách tạo môi trường hoạt động mà **không cần** trust manager chấp nhận mọi chứng thư.

### 8.1. Khi tổ chức đổi CA hoặc xoay vòng certificate

Một kịch bản thường gặp là máy chủ dùng certificate mới do `Root-New` ký trong khi truststore của ứng dụng chỉ có `Root-Old`. Ứng dụng báo PKIX error mặc dù hostname vẫn đúng.

Quy trình chuyển đổi phù hợp:

- Xác minh CA mới và chuỗi certificate mới qua nguồn PKI chính thức.
- Cập nhật truststore để hỗ trợ thời gian chuyển tiếp nếu chính sách cho phép.
- Thử kết nối từ cả endpoint chính/dự phòng và mọi container/JVM có liên quan.
- Sau khi hoàn tất chuyển đổi, loại CA cũ khỏi tập tin cậy khi không còn được phép.
- Giám sát ngày hết hạn, chuẩn bị rotation và kiểm tra việc kết nối mới thực sự dùng truststore/certificate đang có hiệu lực.

Không mặc định thay file truststore trên đĩa sẽ làm mọi TLS context và connection pool đang mở tải lại ngay. Tùy thiết kế, có thể cần tái tạo SSLContext, khởi động lại tiến trình hoặc làm mới connection pool một cách có kiểm soát.

## 9. Kiểm thử để ngăn cấu hình “trust all” quay trở lại

**Kiểm thử có chứng thư hợp lệ chỉ chứng minh chương trình có thể kết nối.** Muốn biết máy chủ thực sự được xác minh, cần những trường hợp phải thất bại.

### 9.1. Ma trận kiểm thử bắt buộc

| Kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Chứng thư đúng CA, đúng SAN | Máy chủ lab hợp lệ | TLS và thao tác LDAP thử nghiệm thành công |
| Certificate do CA không tin ký | Truststore không chứa CA đó | Ứng dụng từ chối handshake, không bind |
| Chain đúng CA nhưng sai SAN | URI `directory.example.org`, SAN `other.example.org` | Từ chối dù chain hợp lệ |
| Certificate đã hết hạn | Leaf với `Not After` trong quá khứ | Từ chối TLS |
| Thiếu intermediate | Server thiếu CA trung gian mà client không có | Từ chối do không xây được chain |
| StartTLS bị từ chối | Server không hỗ trợ/mô phỏng lỗi nâng cấp | Không gửi simple bind trên kết nối rõ |
| TLS handshake bị lỗi | Máy chủ test trả cấu hình TLS/chứng thư không hợp lệ | Không fallback sang LDAP rõ |
| Node dự phòng có CA/SAN sai | Kết nối chuyển tới endpoint thứ hai | Từ chối node sai, không bỏ kiểm tra |
| Referral tới server khác | Referral dẫn đến endpoint không đáp ứng chính sách TLS | Không tiếp tục trao đổi dữ liệu nhạy cảm |
| Context lấy từ pool sau lỗi | Pool có kết nối lỗi hoặc thay certificate | Không mượn lại context không hợp lệ; tạo lại phiên an toàn |

Không dùng mật khẩu thật hoặc dữ liệu sản xuất cho các ca kiểm thử tiêu cực. Có thể dựng máy chủ và CA lab để tạo các tình huống sai và quan sát chính xác **có hay không LDAP bind** sau lỗi TLS.

### 9.2. Kiểm tra cấu hình và mã nguồn

Trong review, kiểm tra mọi vị trí tạo `SSLContext`, `TrustManager`, `HostnameVerifier`, `SSLSocketFactory`, `LdapContextSource` và các đoạn retry. Tìm những dấu hiệu hành vi chấp nhận mọi chứng thư, bỏ so khớp hostname, vô hiệu hóa endpoint identification hay chuyển từ `ldaps://`/StartTLS sang LDAP rõ khi lỗi.

Kiểm thử âm tính phải chạy trên **cấu hình thực sự được triển khai**. Một test tự tạo SSLContext an toàn nhưng code production lại dùng socket factory khác không chứng minh production an toàn.

### 9.3. Giữ bằng chứng kiểm tra

Một báo cáo kiểm thử ngắn nên nêu:

- Endpoint/hostname được kiểm tra và loại kết nối LDAPS hay StartTLS.
- Phiên bản Java và nguồn truststore dùng trong ứng dụng.
- Thông tin certificate không nhạy cảm: issuer, SAN, hạn dùng, fingerprint.
- Kết quả kết nối hợp lệ và các ca CA/SAN sai.
- Xác nhận **không có LDAP bind** khi TLS hoặc hostname verification thất bại.

Không đính kèm private key, mật khẩu bind, log chứa secret hoặc toàn bộ dữ liệu LDAP nhạy cảm vào báo cáo.

## 10. Bài tập tình huống: lỗi sau khi thay chứng thư

**Bối cảnh:** Dịch vụ phân quyền nội bộ dùng `LdapTemplate` để đọc thuộc tính `memberOf` từ LDAP:

~~~yaml
spring:
  ldap:
    urls: ldaps://directory.hr.example.org:636
    base: dc=hr,dc=example,dc=org
    username: cn=group-reader,ou=services,dc=hr,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Sau khi đội PKI thay chứng thư server, ứng dụng xuất hiện `PKIX path building failed`. Một đồng nghiệp đề xuất cấu hình trust manager “trust all” rồi đánh dấu ticket đã xử lý. Quản trị viên cung cấp các dữ kiện:

~~~text
Client URL: ldaps://directory.hr.example.org:636
Leaf SAN: DNS:directory.hr.example.org
Leaf issuer: HR Issuing CA New
Intermediate: HR Issuing CA New
Truststore ứng dụng: HR Root CA Old
Trusted CA mới từ PKI nội bộ: HR Root CA New
~~~

**Câu hỏi:**

1. Với dữ kiện trên, nguyên nhân khả dĩ của lỗi PKIX là gì? Hostname verification có vẻ là nguồn lỗi chính không?
2. Tại sao trust manager chấp nhận mọi certificate không phải một bản sửa hợp lệ?
3. Những bước cần làm để cập nhật truststore và kiểm chứng CA mới một cách an toàn?
4. Nếu endpoint dự phòng có certificate hợp lệ theo CA cũ, có thể sử dụng nó không? Cần kiểm tra những gì?
5. Thiết kế hai kiểm thử âm tính giúp phát hiện việc vô tình bỏ kiểm tra certificate/hostname trong bản phát hành mới.

**Gợi ý đáp án:**

1. Truststore hiện chỉ tin `HR Root CA Old`, trong khi certificate mới đi theo `HR Root CA New`. Client có thể không xây được chain tới trust anchor đang tin. SAN đã khớp tên URL, dù vẫn phải kiểm chứng thực tế.
2. Bỏ xác minh sẽ cho phép server giả mạo trình bày certificate bất kỳ; ứng dụng có thể gửi mật khẩu bind và chấp nhận kết quả nhóm do bên không đáng tin cung cấp.
3. Xác minh thông tin `HR Root CA New` bằng kênh PKI đáng tin; kiểm tra fingerprint, nhập CA vào truststore thích hợp, kiểm tra chain/SAN và thử lại từ JVM thực tế. Chỉ mở lại kết nối khi mọi bước TLS thành công.
4. Có thể sử dụng endpoint dự phòng **nếu** đó là endpoint được phép, có chứng thư và hostname hợp lệ theo chính sách hiện tại, và không làm thay đổi quyền truy cập/dữ liệu ngoài dự kiến. Không tự suy rằng chứng thư cũ luôn hợp lệ.
5. Dùng server lab có (a) certificate từ CA không tin cậy và (b) chain từ CA tin cậy nhưng SAN không khớp. Cả hai phải bị từ chối **trước LDAP bind**.

## 11. Các nguyên tắc cần nhớ

- **Không tắt certificate chain validation hoặc hostname verification để vượt lỗi TLS.** Việc mã hóa với máy chủ không được xác minh không đạt mục tiêu bảo mật kết nối.
- **Tìm nguyên nhân trước khi sửa:** sai CA/truststore, thiếu intermediate, sai SAN, chứng thư hết hạn, lệch đồng hồ, chính sách TLS hoặc khác biệt Java runtime.
- **Sửa nơi đúng:** cập nhật CA qua kênh PKI đáng tin, cấp chứng thư đúng hostname, cấu hình đầy đủ chain trên server, kiểm tra JVM/JSSE và connection pool thực tế.
- **Giữ chính sách fail closed:** LDAPS lỗi hoặc StartTLS không thành công thì dừng trước simple bind; retry chỉ trên endpoint có TLS hợp lệ.
- **Kiểm thử âm tính:** buộc chương trình từ chối certificate không tin cậy và certificate sai SAN, kiểm tra mọi `ContextSource`, node dự phòng, referral và các đường truy cập bằng `LdapTemplate`, `LdapClient` hoặc ODM.

**Bảo mật kết nối LDAP là thuộc tính của toàn bộ đường đi thực tế**, gồm endpoint, certificate, nguồn tin cậy, Java runtime, chiến lược xác thực và cách ứng dụng xử lý lỗi. Một bản sửa đúng phải vừa phục hồi chức năng, vừa giữ nguyên những kiểm tra chứng minh client đang kết nối với **đúng máy chủ thư mục**.
