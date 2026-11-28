# Xác minh hostname và xử lý chứng chỉ theo môi trường

## Mục tiêu bài học

Trong **Spring Data LDAP**, ứng dụng Java truy cập directory bằng repository hoặc **LdapTemplate** để đọc, tìm kiếm và thay đổi các entry mang DN, objectClass và thuộc tính được schema quy định. Khi dữ liệu chứa danh tính người dùng, nhóm hoặc thông tin xác thực, kết nối đến LDAP server phải được bảo vệ bằng TLS. Tuy nhiên, **mã hóa đường truyền chưa đủ**: client còn phải xác định mình thực sự đang nói chuyện với đúng máy chủ đã định kết nối.

Bài học thuộc chương **TLS và xác thực** này tập trung vào **xác minh hostname** của chứng chỉ máy chủ, **chuỗi tin cậy chứng chỉ**, và cách triển khai chứng chỉ phù hợp cho **development, test/CI, staging và production**.

Sau bài học, bạn có thể:

- Phân biệt TLS, xác thực máy chủ bằng chứng chỉ, xác minh hostname, LDAP bind và xác thực client bằng certificate.
- Giải thích vì sao URL LDAP phải khớp với **Subject Alternative Name (SAN)** trên chứng chỉ; nhận biết lỗi không khớp tên, hết hạn và sai CA.
- Chọn **LDAPS** hoặc **StartTLS** đúng ngữ cảnh, bảo đảm xác thực bằng password chỉ diễn ra trên kết nối đã được bảo vệ.
- Cấu hình Spring Boot/Spring LDAP dùng LDAPS và quản lý **truststore** của JVM mà không tắt kiểm tra chứng chỉ.
- Thiết kế CA và vòng đời chứng chỉ theo môi trường, kiểm thử đổi chứng chỉ, tải lại kết nối và tình huống TLS lỗi.
- Phân tích lỗi TLS trước khi truy vấn repository hoặc LdapTemplate, không nhầm lỗi mạng/chứng chỉ với lỗi DN, schema hay LDAP filter.

## 1. TLS bảo vệ điều gì khi ứng dụng truy cập LDAP?

Một kết nối LDAP thường có các thông tin nhạy cảm như bind DN, mật khẩu bind, uid, email, tên người dùng, thuộc tính hồ sơ và quan hệ nhóm. Với kết nối LDAP thông thường qua TCP không dùng TLS, những thông tin này có nguy cơ bị quan sát hoặc can thiệp trên đường truyền.

TLS cung cấp ba mục tiêu chính:

1. **Bí mật (confidentiality):** dữ liệu giữa client và server được mã hóa.
2. **Toàn vẹn (integrity):** client và server phát hiện việc dữ liệu trên đường truyền bị thay đổi trái phép.
3. **Xác thực đầu bên kia (peer authentication):** client đánh giá chứng chỉ và tên dịch vụ của server trước khi gửi thông tin nhạy cảm.

Mục tiêu thứ ba có **hai phép kiểm tra riêng**:

- **Certificate path validation:** chứng chỉ có chuỗi ký số hợp lệ đến CA được client tin cậy, còn hạn và phù hợp chính sách sử dụng không?
- **Hostname verification / endpoint identification:** chứng chỉ có đại diện cho đúng tên server trong URL mà ứng dụng định truy cập không?

Một chứng chỉ có chữ ký hợp lệ từ CA đáng tin nhưng cấp cho **mail.example.org** vẫn không phù hợp với kết nối tới **ldap.example.org**. Ngược lại, chứng chỉ ghi đúng **ldap.example.org** nhưng được ký bởi CA không được tin cậy cũng không đủ để thiết lập kết nối an toàn.

~~~mermaid
flowchart TD
    A["Spring LDAP / JNDI mở kết nối"] --> B["Bắt tay TLS"]
    B --> C{"Chuỗi chứng chỉ hợp lệ và đáng tin?"}
    C -->|Không| X["Từ chối kết nối"]
    C -->|Có| D{"Hostname của URL khớp SAN?"}
    D -->|Không| X
    D -->|Có| E["TLS được thiết lập"]
    E --> F["LDAP bind nếu cần xác thực"]
    F --> G["Repository / LdapTemplate tìm kiếm, CRUD"]
~~~

**Phân biệt TLS với LDAP bind:** TLS có thể xác thực máy chủ, còn thao tác **bind** giúp server xác thực người dùng/tài khoản dịch vụ của ứng dụng (ví dụ simple bind với DN và password, SASL...). TLS **không tự xác thực tài khoản LDAP**, và simple bind **không thay thế kiểm tra chứng chỉ server**.

## 2. Hostname được so với thông tin nào trong chứng chỉ?

Ví dụ ứng dụng cấu hình:

~~~text
ldaps://ldap.example.org:636
~~~

Chứng chỉ server nên có SAN chứa DNS name tương ứng:

~~~text
Subject: CN=Directory Service
Subject Alternative Name:
    DNS:ldap.example.org
    DNS:ldap01.example.org
~~~

Khi dùng URL **ldaps://ldap.example.org:636**, client phải xác nhận tên **ldap.example.org** khớp danh tính mà chứng chỉ công bố. Các yếu tố thường được kiểm tra:

| Yếu tố | Điều cần đối chiếu | Ví dụ |
| --- | --- | --- |
| **DNS SAN** | URL dùng tên DNS nào thì chứng chỉ phải có SAN phù hợp tên đó | **ldap.example.org** |
| **IP SAN** | Nếu URL dùng IP trực tiếp, chứng chỉ cần IP SAN thích hợp | **ldaps://192.0.2.20:636** cần IP SAN **192.0.2.20** |
| **Chuỗi ký số** | Leaf certificate → intermediate CA → root CA được trust | Root CA của tổ chức hoặc CA công khai |
| **Thời hạn** | Chứng chỉ chưa hết hạn, chưa ở thời điểm trước Not Before | Thời gian JVM và hệ thống phải đúng |
| **Key usage / EKU** | Chứng chỉ dùng được để xác thực máy chủ TLS | **serverAuth** khi EKU có mặt, theo chính sách JVM |
| **Tên do client kết nối** | Tên được kiểm tra là endpoint mà client yêu cầu | Alias/DNS VIP cũng cần xuất hiện trong SAN |

**Common Name (CN) không nên được dùng làm phương án thay thế cho SAN.** Cấu hình hiện đại nên đưa mọi tên kết nối chính thức vào **subjectAltName** và kiểm tra bằng client tương ứng. Một bản ghi DNS CNAME trỏ đến server thật cũng không tự làm tên alias hợp lệ về mặt chứng chỉ.

### 2.1. Ví dụ đúng và sai

| URL trong ứng dụng | SAN của chứng chỉ server | Kết luận |
| --- | --- | --- |
| **ldaps://ldap.example.org:636** | **DNS:ldap.example.org** | Khớp tên nếu các điều kiện TLS khác cũng đúng |
| **ldaps://directory.internal.example.org:636** | **DNS:ldap01.internal.example.org** | Không khớp alias **directory.internal.example.org** |
| **ldaps://192.0.2.20:636** | **DNS:ldap.example.org** | Không đủ: URL IP cần danh tính IP phù hợp |
| **ldaps://ldap.example.org:636** | **DNS:ldap.example.org**, nhưng CA không được trust | Vẫn phải từ chối do lỗi chuỗi chứng chỉ |
| **ldaps://ldap.example.org:636** | SAN khớp nhưng chứng chỉ hết hạn | Vẫn phải từ chối |

Nếu dùng load balancer hoặc DNS round-robin, cần xác định **điểm kết thúc TLS**. Nếu client bắt tay trực tiếp với từng backend, từng backend phải có chứng chỉ phù hợp với tên mà client sử dụng. Nếu load balancer kết thúc TLS rồi tạo kết nối mới đến backend, phải xem xét **cả hai chặng**, quyền truy cập và cách bảo vệ lưu lượng nội bộ.

### 2.2. Tên trong môi trường container

Trong Kubernetes hoặc Docker, ứng dụng có thể kết nối tới **ldap**, **ldap.default.svc.cluster.local** hoặc tên FQDN nội bộ. Chứng chỉ cần chứa tên **thực tế được cấu hình trong URL ứng dụng**, không chỉ tên máy vật lý phía sau.

Ví dụ:

~~~text
spring.ldap.urls=ldaps://ldap.directory.svc.cluster.local:636
Certificate SAN: DNS:ldap.directory.svc.cluster.local
~~~

Không cần đổi sang địa chỉ IP hoặc tắt hostname verification chỉ vì tên dịch vụ là hostname nội bộ. Thay vào đó, dùng CA nội bộ và cấp chứng chỉ có SAN đúng.

## 3. LDAPS và StartTLS: chọn đúng cách thiết lập kênh bảo vệ

| Thuộc tính | LDAPS | StartTLS |
| --- | --- | --- |
| URL thường dùng | **ldaps://host:636** | **ldap://host:389** rồi gửi StartTLS extended operation |
| Thời điểm bật TLS | Từ lúc thiết lập kết nối | Nâng cấp kết nối LDAP đã mở sang TLS |
| Kiểm tra chứng chỉ và hostname | Khi bắt tay TLS | Trong giai đoạn thương lượng TLS sau StartTLS |
| Simple bind | Thực hiện **sau** khi kênh TLS đã sẵn sàng | Chỉ gửi password **sau khi StartTLS thành công** |
| Sai lầm thường gặp | Dùng URL IP hoặc certificate không có SAN tương ứng | Cấu hình **ldap://** nhưng quên gửi StartTLS trước bind |

**LDAPS và StartTLS là hai phương án vận chuyển thay thế nhau** đối với kết nối LDAP thông thường. Không gửi StartTLS như một bước mặc định bổ sung lên socket LDAPS đã mã hóa.

Với StartTLS, việc để một client tự động tiếp tục bind không mã hóa khi StartTLS bị từ chối là **downgrade không an toàn**. Quy tắc là **fail closed**: nếu yêu cầu TLS là bắt buộc, không gửi credentials và không tiếp tục truy vấn trên kết nối chưa nâng cấp.

Trong Spring Boot, thay **ldaps://** bằng **ldap://** trong property **spring.ldap.urls** không tự đảm bảo StartTLS đã được thương lượng. Cần cấu hình **TLS authentication strategy/ContextSource** phù hợp với Spring LDAP và phiên bản đang dùng, hoặc triển khai JNDI StartTLS tường minh có kiểm tra chứng chỉ/hostname.

## 4. Cấu hình LDAPS cho Spring Boot và Spring Data LDAP

Spring Boot có thể tự cấu hình LDAP ContextSource/LdapTemplate từ các thuộc tính:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-app,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ở đây:

- **urls** chỉ địa chỉ server dùng TLS và tên sẽ được xác minh.
- **base** là DN gốc cho thao tác LDAP (ví dụ tìm ở **ou=people** thành DN đầy đủ dưới **dc=example,dc=org**).
- **username** là bind DN đầy đủ của tài khoản dịch vụ, không phải hostname.
- **password** lấy từ biến môi trường/secret manager, không lưu trong repository.

Giả sử ứng dụng dùng repository:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
}
~~~

Hoặc dùng LdapTemplate:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

// Đặt trong service đã inject biến ldapTemplate.
List<String> names = ldapTemplate.search(
        query().base("ou=people")
            .attributes("cn")
            .where("objectClass").is("inetOrgPerson")
            .and("uid").is("an"),
        (AttributesMapper<String>) attrs ->
            (String) attrs.get("cn").get()
);
~~~

Hai API này dùng **cùng nền tảng kết nối LDAP** đã được cấu hình. Nếu TLS hoặc hostname verification thất bại, ứng dụng không thể hoàn tất truy vấn: đó là lỗi kết nối/trust, không phải lỗi cú pháp LDAP filter hay lỗi ánh xạ entry Java.

### 4.1. Phân biệt truststore và keystore

Trong ứng dụng Java, các thuật ngữ hay gặp:

| Khái niệm | Nội dung và mục đích | Ai thường dùng? |
| --- | --- | --- |
| **Server certificate** | Chứng chỉ máy chủ LDAP trình bày trong TLS handshake | LDAP server |
| **CA certificate** | Chứng chỉ CA dùng xác thực chữ ký/chuỗi chứng chỉ | Client cần tin cậy CA cấp server certificate |
| **Truststore** | Kho certificate/trust anchor mà JVM dùng để quyết định tin server nào | Ứng dụng Spring LDAP |
| **Client keystore** | Certificate và private key của client nếu sử dụng mutual TLS | Ứng dụng khi server yêu cầu client certificate |
| **JVM default truststore** | Kho tin cậy mặc định của môi trường JDK hoặc môi trường quản trị | Có thể dùng nếu CA đã được tin cậy |

**Truststore không chứa private key của LDAP server.** Khi LDAP server yêu cầu **mTLS**, client mới cần chứng chỉ và private key riêng; đây là yêu cầu khác với việc chỉ xác minh chứng chỉ server. Không nhầm truststore dùng để *tin máy chủ* với keystore chứa *danh tính của client*.

### 4.2. Tạo truststore riêng cho ứng dụng

Nếu LDAP server dùng CA nội bộ chưa có trong truststore của JDK, quản trị viên có thể cung cấp chứng chỉ root/intermediate CA qua kênh đáng tin. Trước khi import, xác minh fingerprint và chủ sở hữu CA bằng một nguồn độc lập.

Ví dụ thao tác bằng công cụ **keytool** của JDK:

~~~bash
# Xem chi tiết chứng chỉ CA trước khi nhập.
keytool -printcert -file ldap-root-ca.pem

# Tạo/bổ sung truststore riêng, keytool yêu cầu mật khẩu tương tác.
keytool -importcert \
  -alias corp-ldap-root \
  -file ldap-root-ca.pem \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12

# Kiểm tra certificate đã được nhập.
keytool -list -v \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
~~~

Đây là các lệnh mẫu cho môi trường có **keytool**; không tự import mọi certificate nhận được từ một kết nối đang báo lỗi TLS. Hãy tin **đúng CA đã kiểm chứng** theo chính sách của tổ chức. Certificate leaf thường xuyên thay đổi theo chu kỳ cấp phát; tin CA phù hợp giúp chuẩn bị cho việc rotation, nhưng phải giới hạn phạm vi CA theo chính sách quản trị.

Khởi động JVM có thể chỉ định truststore chuyên biệt:

~~~text
-Djavax.net.ssl.trustStore=/opt/app/certs/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Nếu truststore yêu cầu password để đọc/xác minh toàn vẹn, cấu hình **javax.net.ssl.trustStorePassword** bằng cơ chế quản lý bí mật khi triển khai. Tránh đặt mật khẩu dạng literal trong mã nguồn, file cấu hình chia sẻ hoặc command line dễ bị đọc. Khi ứng dụng còn dùng HTTPS tới các dịch vụ khác, cần đánh giá phạm vi của truststore JVM: thay kho tin cậy mặc định bằng một kho chỉ có CA LDAP có thể khiến các kết nối TLS khác mất trust. Có thể xây truststore ứng dụng chứa đầy đủ các trust anchor cần thiết hoặc cấu hình trust manager theo từng client nếu kiến trúc cho phép.

**Lưu ý:** không thay đổi truststore hệ thống toàn máy một cách tùy tiện để xử lý lỗi của một ứng dụng. Cấu hình riêng giúp kiểm soát quyền và triển khai theo môi trường.

## 5. Chiến lược chứng chỉ theo development, CI, staging và production

Không có lý do bảo mật để bật hostname verification ở production nhưng tắt ở development hoặc CI. Các môi trường có thể sử dụng **CA khác nhau**, song **nguyên tắc xác minh danh tính endpoint** nên nhất quán.

| Môi trường | Nguồn chứng chỉ hợp lý | SAN cần phản ánh | Cách phân phối trust |
| --- | --- | --- | --- |
| **Local development** | CA phát triển được kiểm soát hoặc CA thử nghiệm nội bộ | Tên thực tế app gọi như **ldap.local.test**, **ldap** | Truststore local tách biệt, không đưa private key lên Git |
| **CI / Integration test** | CA test và certificate phát sinh/chuẩn bị cho test | Tên service trong mạng test/container | Mount truststore cho job; vòng đời ngắn, tái tạo được |
| **Staging** | CA nội bộ hoặc CA theo chuẩn của tổ chức | Tên endpoint staging thực tế, gồm DNS VIP/alias nếu dùng | Secret/certificate management như production |
| **Production** | CA tin cậy theo chính sách tổ chức, được quản lý và xoay vòng | Tên chính thức app kết nối, kể cả endpoint sau load balancing | Truststore được quản trị tập trung, kiểm soát thay đổi và cảnh báo hết hạn |

### 5.1. Development: sửa certificate cho đúng tên

Ví dụ ứng dụng trong Docker Compose kết nối **ldaps://ldap:636**, nhưng certificate chỉ có **DNS:localhost**. TLS sẽ báo lỗi tên dù kết nối mạng thành công.

Giải pháp là **cấp certificate có SAN: DNS:ldap**, hoặc cấu hình ứng dụng kết nối đến một hostname mà certificate đã bao phủ và DNS/mạng có thể phân giải. Tránh thay URL bằng IP bất kỳ hoặc tắt kiểm tra hostname.

Nếu phát hành CA dev tự quản, private key CA chỉ dùng trong phạm vi development; không chia sẻ chung root private key với production. Mỗi developer/CI runner nên chỉ trust CA dev theo phạm vi cần thiết.

### 5.2. CI: kiểm thử hành vi lỗi thật

Tạo fixture LDAP ở môi trường test kèm CA và certificate có SAN theo tên service. Chạy cả ca thành công và ca thất bại (khác SAN, CA không được trust, chứng chỉ hết hạn nếu test fixture hỗ trợ) để xác nhận ứng dụng **từ chối kết nối không hợp lệ**.

Nếu test chạy bằng Testcontainers hoặc một LDAP container khác, địa chỉ hostname/port được cấp có thể thay đổi. Không được coi tên nội bộ **ldap** và **localhost** là tương đương với chứng chỉ. Chọn một hostname ổn định trong mạng test, cấu hình SAN tương ứng và dùng truststore của test.

### 5.3. Staging và production: vòng đời chứng chỉ

Staging nên kiểm thử gần giống production: cơ chế triển khai CA, cấu hình JVM, DNS, load balancer, ACL, thời gian hệ thống, rotation và cảnh báo.

Ở production:

1. Xác định **owner** của CA, certificate và endpoint LDAP.
2. Cấp chứng chỉ có SAN đúng danh sách hostname thực sự được sử dụng.
3. Bảo vệ private key ở phía server và phân phối CA tới client qua kênh được kiểm soát.
4. Giám sát ngày hết hạn của certificate leaf và intermediate; lên lịch rotation trước hạn.
5. Nếu **thay CA**, phân phối trust anchor mới tới client **trước** khi server chuyển sang certificate mới; duy trì khoảng chuyển tiếp cho cả CA cũ/mới khi chính sách cho phép.
6. Sau rotation, tạo kết nối TLS mới từ chính môi trường ứng dụng để xác nhận JVM truststore và endpoint identification. Kết nối LDAP được pool có thể vẫn đang dùng phiên TLS cũ và không đại diện cho kết nối mới.
7. Sau khi hoàn tất, thu hồi trust anchor cũ khi không còn cần thiết; kiểm tra các client còn cấu hình cũ.

Không giả định mọi JVM hoặc pool tự động đọc lại truststore mỗi khi file certificate thay đổi. Tùy ứng dụng, cần **restart các instance**, tải lại SSL context hoặc tái tạo connection pool theo kế hoạch rolling deployment.

## 6. Cách kiểm tra chứng chỉ và hostname trước khi chạy ứng dụng

### 6.1. Kiểm tra TLS endpoint bằng openssl

Trên môi trường có OpenSSL hỗ trợ các tùy chọn tương ứng:

~~~bash
openssl s_client \
  -connect ldap.example.org:636 \
  -servername ldap.example.org \
  -verify_hostname ldap.example.org \
  -CAfile ldap-root-ca.pem \
  -verify_return_error \
  -showcerts
~~~

Tham số:

- **-connect**: mở kết nối tới cổng LDAPS.
- **-servername**: gửi tên SNI nếu server hỗ trợ, hữu ích khi một endpoint phục vụ nhiều chứng chỉ.
- **-verify_hostname**: yêu cầu kiểm tra danh tính DNS theo tên mong đợi.
- **-CAfile**: tập CA mà công cụ kiểm tra tin cậy; cần xác nhận CA này có nguồn đáng tin cậy.
- **-verify_return_error**: để kiểm tra chứng chỉ không bị che khuất bởi cơ chế tiếp tục mặc dù có lỗi.
- **-showcerts**: hiển thị các chứng chỉ server cung cấp để chẩn đoán chain.

**Kiểm tra bằng openssl không thay thế kiểm tra với JVM thực tế**: Java có thể dùng truststore khác, chính sách thuật toán/chứng chỉ khác hoặc cách cấu hình tên endpoint khác. Công cụ này giúp khoanh vùng lỗi trước khi thử lại Spring Boot.

### 6.2. Kiểm tra thao tác LDAP trên TLS

Công cụ OpenLDAP client có thể thử xác thực trên LDAPS:

~~~bash
ldapwhoami -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-app,ou=service-accounts,dc=example,dc=org" \
  -W
~~~

Tương tự, khi server cung cấp StartTLS trên cổng LDAP:

~~~bash
ldapwhoami -x \
  -H ldap://ldap.example.org:389 \
  -ZZ \
  -D "uid=svc-app,ou=service-accounts,dc=example,dc=org" \
  -W
~~~

**-ZZ** yêu cầu StartTLS bắt buộc; nếu nâng cấp TLS không thành công thì lệnh phải thất bại. OpenLDAP client có cấu hình CA riêng (ví dụ **TLS_CACERT**), cần kiểm tra chính sách xác minh certificate của chính client và không dùng chế độ bỏ qua xác minh. Tham số **-W** yêu cầu nhập password qua prompt.

Thứ tự kiểm tra hợp lý: kiểm tra DNS/port → TLS handshake/trust/hostname → LDAP bind → truy vấn entry. Khi TLS chưa đạt, chưa cần sửa repository method hay LDAP filter.

### 6.3. Kiểm tra bằng Java

Nếu OpenSSL/ldapwhoami thành công nhưng Spring Boot lỗi, kiểm tra cấu hình JVM đang chạy:

- JVM nào thực sự chạy ứng dụng, và phiên bản/cập nhật nào?
- **javax.net.ssl.trustStore** có trỏ tới file đúng, tài khoản process có quyền đọc file không?
- File truststore là **PKCS12/JKS** và password có khớp không?
- Certificate CA/intermediate có mặt trong truststore đúng scope không?
- App có dùng đúng URL/hostname không, hay bị override bởi profile hoặc biến môi trường?
- Có custom **SSLSocketFactory**, LDAP connection pool hoặc một ContextSource khác đang được dùng không?

Trong môi trường kiểm thử được kiểm soát, có thể bật chẩn đoán JSSE:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

Log TLS có thể lớn và tiết lộ thông tin vận hành về máy chủ/chứng chỉ. Chỉ bật tạm thời khi điều tra, giới hạn quyền đọc log và tắt sau khi đã có kết luận.

## 7. Phân biệt lỗi hostname, truststore và bind

| Biểu hiện thường gặp | Lớp gây lỗi | Cách chẩn đoán/khắc phục |
| --- | --- | --- |
| **No subject alternative DNS name matching ...** hoặc **No name matching ... found** | Hostname verification | So tên trong URL với SAN; cấp chứng chỉ có SAN đúng, kiểm tra DNS alias |
| **PKIX path building failed / unable to find valid certification path** | Certificate trust chain | Kiểm tra root/intermediate CA và truststore thực sự của JVM |
| **CertificateExpiredException / NotAfter** | Hiệu lực chứng chỉ | Gia hạn/rotate chứng chỉ hợp lệ, kiểm tra đồng hồ hệ thống |
| **NotYetValidException / NotBefore** | Hiệu lực chứng chỉ/thời gian | Kiểm tra NTP, thời điểm certificate bắt đầu hiệu lực |
| **SSLHandshakeException / handshake_failure** | TLS negotiation | Kiểm tra phiên bản giao thức, cipher suite, certificate, client authentication và log JSSE |
| **Connection refused / timeout** | Mạng hoặc dịch vụ | Kiểm tra DNS, cổng, firewall, listener; đây chưa chắc là lỗi chứng chỉ |
| **LDAP error 49 / invalidCredentials** | LDAP bind | TLS có thể đã thành công nhưng DN/password hoặc chính sách tài khoản sai |
| **No such object (32)** | Dữ liệu LDAP / base DN | Kết nối đã đi đủ xa để server xử lý; kiểm tra DN, base và cây entry |
| **Insufficient access rights (50)** | ACL LDAP | Kiểm tra quyền tài khoản bind trên nhánh và thuộc tính |
| **Object class violation (65)** | LDAP schema | Kiểm tra objectClass, MUST/MAY và thuộc tính khi ghi |

Lỗi có thể được bọc bởi **CommunicationException**, **AuthenticationException**, **NamingException** hoặc ngoại lệ Spring LDAP. Cần xem **nguyên nhân gốc (root cause)**; không đồng nhất mọi **CommunicationException** với mất mạng.

### 7.1. Tuyệt đối không dùng các cách “sửa lỗi” sau

Khi lỗi chứng chỉ xuất hiện, một số ví dụ trên mạng gợi ý:

- Tắt endpoint identification hoặc các property vô hiệu hóa hostname verification của JNDI.
- Tự cài một **TrustManager** chấp nhận mọi chứng chỉ.
- Dùng **HostnameVerifier** luôn trả **true**.
- Chuyển từ LDAPS/StartTLS sang simple bind qua LDAP thuần chỉ để kết nối thành công.
- Sao chép chứng chỉ server bất kỳ vừa nhận từ kết nối lỗi vào truststore mà không xác minh nguồn.

Các cách trên làm yếu hoặc bỏ hẳn bảo đảm xác thực server, có thể tạo cơ hội cho kẻ đứng giữa giả mạo directory và thu thập bind credentials. Cách đúng là **xác định tên endpoint/CA nào phải được tin**, sửa SAN và cấp phát/trust certificate theo quy trình quản trị.

Đặc biệt, các thuộc tính hoặc mẹo cấu hình liên quan đến **com.sun.jndi.ldap.object.disableEndpointIdentification** được nhắc trong một số môi trường Java cũ là cách **vô hiệu hóa** một lớp bảo vệ, không phải cấu hình chuẩn cần bật. Hành vi thực tế phải đối chiếu theo JDK/provider đang chạy; mục tiêu vẫn là **bật và kiểm chứng xác minh hostname**.

**Lưu ý:** một **javax.net.ssl.HostnameVerifier** dành cho HTTPS không có nghĩa đã thay đổi được cách JNDI LDAP xác minh danh tính server. Không dựa vào cấu hình HTTPS toàn cục để bảo đảm LDAPS.

## 8. Một ví dụ đầy đủ theo môi trường

Giả sử ứng dụng quản lý nhân viên chạy ở ba môi trường:

| Môi trường | URL LDAP | SAN dự kiến trên chứng chỉ | Trust anchor |
| --- | --- | --- | --- |
| Local | **ldaps://ldap.local.test:636** | **DNS:ldap.local.test** | Dev CA của nhóm |
| Staging | **ldaps://ldap.staging.example.org:636** | **DNS:ldap.staging.example.org** | CA staging do tổ chức quản trị |
| Production | **ldaps://ldap.example.org:636** | **DNS:ldap.example.org** | CA production theo chính sách tổ chức |

Một bộ cấu hình Spring Boot có thể dùng biến môi trường:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Giá trị **LDAP_URL** được triển khai bởi hệ thống cấu hình đáng tin, **không nhận trực tiếp từ request người dùng**. Mỗi môi trường đặt URL cùng truststore tương ứng qua launcher hoặc deployment manifest được kiểm soát.

Chẳng hạn, ở local:

~~~text
LDAP_URL=ldaps://ldap.local.test:636
JVM truststore: /opt/app/certs/ldap-dev-truststore.p12
Certificate SAN: DNS:ldap.local.test
~~~

Ở production:

~~~text
LDAP_URL=ldaps://ldap.example.org:636
JVM truststore: /opt/app/certs/ldap-prod-truststore.p12
Certificate SAN: DNS:ldap.example.org
~~~

Chỉ thay đổi **endpoint, CA và thông tin định danh tài khoản** theo môi trường; nguyên tắc **TLS hợp lệ + hostname verification + bind đúng quyền** giữ nguyên. Cần thêm giới hạn quyền của tài khoản LDAP, filter an toàn và schema hợp lệ trong các nghiệp vụ repository/LdapTemplate.

## 9. Kiểm thử tích hợp cần có

Trong integration test, dùng LDAP directory dành riêng cho test, có CA/certificate hợp lệ và hồ sơ **uid=an,ou=people,dc=example,dc=org**. Kết nối qua **LdapTemplate** để thực sự kích hoạt JNDI/JSSE từ JVM, và ghi lại kết quả/exception. Những kiểm tra sau quan trọng hơn việc chỉ mock LdapTemplate:

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| **Hợp lệ** | Certificate do CA tin cậy cấp, SAN khớp URL, chưa hết hạn | TLS, LDAP bind và truy vấn **uid=an** thành công |
| **Sai SAN** | URL khác mọi DNS/IP SAN trên certificate | TLS bị từ chối trước khi gửi password |
| **CA không tin cậy** | Bỏ CA phù hợp khỏi truststore | TLS bị từ chối do không xây được chuỗi tin cậy |
| **Chứng chỉ hết hạn** | Certificate test có NotAfter đã qua | TLS bị từ chối |
| **Tên IP và DNS** | Kết nối bằng IP nhưng certificate chỉ có DNS SAN | Tên endpoint bị từ chối |
| **Sai password bind** | TLS hợp lệ nhưng LDAP credentials sai | Server trả lỗi xác thực LDAP; không bị nhầm thành lỗi truststore |
| **Sai base DN** | TLS và bind đúng, base trong truy vấn sai | Trả kết quả rỗng hoặc lỗi LDAP tùy thao tác; TLS vẫn đã thành công |
| **Rotation** | Thay server certificate cùng CA/SAN hợp lệ; tạo kết nối mới | Kết nối mới thành công; nếu thay CA cần cập nhật truststore trước |
| **Pool và restart** | Đổi CA, tái tạo SSL context hoặc connection pool | Client mới dùng trust anchors đã cập nhật |
| **StartTLS bắt buộc** | Server từ chối StartTLS | Client không tiếp tục simple bind không mã hóa |

Các bước kiểm thử nên bao gồm:

1. **Seed directory** với DN, objectClass và thuộc tính hợp lệ.
2. **Tạo hoặc nạp CA/certificate test** có SAN đúng tên endpoint của mạng thử nghiệm.
3. **Cấu hình JVM** dùng truststore test và kết nối qua Spring LDAP trong bài test tích hợp.
4. **Tạo ca lỗi có chủ đích** (hostname khác, CA khác, chứng chỉ hết hạn) trên server test; xác minh kết nối bị từ chối.
5. **Đọc lại** một entry bằng LdapTemplate sau ca thành công, kiểm tra dữ liệu của **cn**, **uid** và kết quả truy vấn theo filter.
6. **Dọn dẹp** fixture/CA test và bảo đảm không ảnh hưởng cấu hình production.

Không cần viết payload tấn công để kiểm chứng TLS. Việc ứng dụng **từ chối đúng** endpoint không đủ tin cậy là một test quan trọng ngang với đường đi thành công.

## 10. Tình huống thực hành

Một đội triển khai Spring Boot nhận lỗi:

~~~text
javax.net.ssl.SSLHandshakeException:
    No subject alternative DNS name matching
    directory.internal.example.org found
~~~

Ứng dụng cấu hình:

~~~yaml
spring:
  ldap:
    urls: ldaps://directory.internal.example.org:636
~~~

Nhưng certificate được cấp chỉ có:

~~~text
SAN: DNS:ldap01.internal.example.org
~~~

**Phân tích:** dù **directory.internal.example.org** có thể là CNAME của **ldap01.internal.example.org**, client đang yêu cầu kết nối tới **directory.internal.example.org**, nên certificate phải công bố tên đó. Đây là lỗi **hostname**, không giải quyết bằng cách thêm CA vào truststore hoặc sửa **username/password**.

**Cách xử lý:** yêu cầu cấp certificate có **DNS:directory.internal.example.org** trong SAN (có thể thêm tên backend cần dùng theo chính sách), hoặc điều chỉnh endpoint để ứng dụng dùng đúng hostname có trong certificate và được phép truy cập. Sau khi triển khai, kiểm tra lại handshake bằng Java/LdapTemplate. Không tắt hostname verification.

**Câu hỏi mở rộng:** nếu công ty thay CA staging, theo thứ tự nào cần cập nhật truststore client và certificate server để giảm gián đoạn? Điều gì xảy ra với LDAP connection pool trong giai đoạn chuyển đổi?

## 11. Tổng kết và câu hỏi tự luyện

Một kết nối Spring Data LDAP an toàn cần **đúng endpoint**, **certificate chain hợp lệ**, **hostname khớp SAN**, sau đó mới đến **LDAP bind và quyền truy cập entry**. **LDAPS** thiết lập TLS ngay khi kết nối; **StartTLS** phải hoàn tất nâng cấp TLS trước khi gửi simple bind credentials. Truststore quyết định CA được tin, còn SAN xác định tên máy chủ mà chứng chỉ đại diện; cả hai kiểm tra phải đạt.

Theo môi trường, hãy quản lý **CA, SAN, DNS, truststore và rotation** một cách nhất quán. Development và CI có thể dùng CA riêng, staging có thể mô phỏng production, và production cần theo dõi certificate expiry cùng thay đổi trên mọi instance. Không dùng mẹo bỏ qua hostname/certificate verification để khắc phục lỗi TLS.

**Câu hỏi tự luyện:**

1. Vì sao certificate do CA tin cậy cấp cho **mail.example.org** không đủ khi ứng dụng kết nối **ldaps://ldap.example.org:636**?
2. **Root CA** và **SAN** được kiểm tra ở hai bước khác nhau như thế nào?
3. Trong Spring Boot, đổi **spring.ldap.urls** từ **ldaps://** sang **ldap://** có tự động kích hoạt StartTLS không? Cần bảo đảm điều gì trước simple bind?
4. Nếu LDAP server được truy cập qua Kubernetes Service name, hostname nào cần xuất hiện trong SAN?
5. Điều gì cần kiểm tra nếu **openssl s_client** thành công nhưng ứng dụng Java báo **PKIX path building failed**?
6. Khi rotate CA production, vì sao client cần trust CA mới trước khi server chuyển sang certificate mới? Vì sao cần thử tạo kết nối mới sau rotation?
7. Lập ma trận kiểm thử riêng cho trường hợp CA không tin, SAN sai, certificate hết hạn và bind password sai. Mỗi trường hợp xảy ra trước hay sau bước LDAP authentication?

### Tài liệu tham khảo

- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513) — bảo vệ kết nối và xác thực LDAP.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — LDAP và StartTLS extended operation.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525) — hướng dẫn hiện hành về xác minh danh tính dịch vụ qua certificate, thay thế RFC 6125 (đối chiếu hành vi với JDK/provider đang dùng).
- [Oracle JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html) — TLS/SSLContext, trust manager và công cụ chẩn đoán Java.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) và [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — ContextSource, LdapTemplate và repository.
