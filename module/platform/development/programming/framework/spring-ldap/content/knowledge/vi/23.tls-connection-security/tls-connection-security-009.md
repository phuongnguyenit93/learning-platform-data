# Kiểm thử kết nối TLS trên môi trường gần production với Spring LDAP

Ứng dụng có thể truy vấn LDAP thành công ở máy phát triển nhưng thất bại ngay sau khi triển khai vì Java không tin cậy chứng chỉ, tên máy chủ không khớp Subject Alternative Name (SAN), load balancer chuyển đến một nút dùng chuỗi chứng chỉ khác, hoặc client gửi mật khẩu trước khi bật StartTLS. Vì vậy, chỉ nhìn thấy thông báo “LDAP connected” chưa đủ để kết luận kênh kết nối an toàn.

Bài này hướng dẫn **kiểm thử kết nối TLS tới LDAP trên môi trường gần production** (staging hoặc pre-production) bằng OpenSSL, công cụ OpenLDAP và ứng dụng **Spring LDAP**. Mục tiêu là chứng minh backend thiết lập được kênh mã hóa **có xác thực đúng máy chủ**, thực hiện bind/search qua kênh đó, và **từ chối an toàn** khi TLS bị cấu hình sai.

Phạm vi bao gồm cả **LDAPS** (TLS được thiết lập ngay khi kết nối) và **StartTLS** (nâng cấp kết nối LDAP sang TLS *trước khi bind*), cấu hình `ContextSource`/`LdapTemplate`, chứng chỉ/`truststore`, lỗi xác minh, pooling, chuyển đổi chứng chỉ và quy trình nghiệm thu. Các ví dụ sử dụng tên miền, DN, tài khoản và chứng chỉ **giả định**; chỉ thực hiện trên môi trường được ủy quyền.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định những điểm môi trường gần production phải tương đồng với production để kiểm thử TLS có ý nghĩa.
2. Phân biệt bắt tay TLS, xác minh certificate chain, kiểm tra hostname/SAN và thành công của LDAP bind/search.
3. Thực hiện smoke test **LDAPS cổng 636** và **StartTLS trên LDAP cổng 389** bằng lệnh có kiểm tra chứng chỉ.
4. Cấu hình Spring Boot/Spring LDAP dùng kết nối LDAPS cùng truststore của JVM.
5. Tổ chức kiểm thử thành công và kiểm thử thất bại: CA không tin cậy, hostname sai, chứng chỉ hết hạn, StartTLS bị từ chối và node lỗi.
6. Phân tích lỗi thực tế mà không nhầm lỗi TLS, lỗi mạng, lỗi quyền search và `invalidCredentials`.
7. Xây checklist nghiệm thu trước khi bật TLS cho hệ thống LDAP đang phục vụ người dùng.

## 2. “Môi trường gần production” nghĩa là gì?

Staging không nhất thiết có cùng dữ liệu cá nhân hoặc cùng bí mật với production. Tuy nhiên, **đường đi của kết nối, cách xác minh danh tính máy chủ và cơ chế vận hành** phải đủ giống để kiểm thử bắt được các lỗi sẽ xảy ra khi triển khai thật.

| Thành phần | Cần tương đồng với production | Dữ liệu/giá trị nên tách biệt |
|---|---|---|
| Java và Spring LDAP | Phiên bản JDK, Spring Boot, Spring LDAP, JNDI và chính sách TLS | Cấu hình URL theo staging |
| DNS và mạng | Kiểu phân giải DNS, firewall, proxy, load balancer, đường đi giữa các subnet | Hostname staging riêng |
| LDAP endpoint | LDAPS/StartTLS, server type, các nút dự phòng, certificate chain | Server và directory test riêng |
| PKI/trust | Mô hình CA/intermediate, SAN, độ dài chuỗi và cách cấp phát truststore | CA và chứng chỉ staging được quản lý |
| Danh tính kết nối | Cách service bind, search base, ACL và timeout hoạt động | Tài khoản kỹ thuật và mật khẩu test riêng |
| Connection handling | Pooling, reconnect, idle timeout, health check và failover | Kích thước tải phù hợp staging |
| Quan sát | Log, metrics, cảnh báo, correlation ID và quy trình rollback | Không xuất credential hoặc dữ liệu thật |

Để tránh rò rỉ dữ liệu, **không sao chép mật khẩu hay dữ liệu người dùng từ production** sang staging. Nên tạo entry thử nghiệm như `uid=ldap-tls-test,ou=people,dc=example,dc=org` và một tài khoản dịch vụ chỉ có quyền search các OU cần thiết. Đường truyền nên sử dụng PKI đại diện cho production nhưng có chứng chỉ và bí mật dành riêng cho staging.

### 2.1. Sơ đồ kết nối cần kiểm thử

~~~mermaid
flowchart LR
    A["Ứng dụng Spring<br/>JDK + truststore"] -->|"LDAPS 636 hoặc<br/>StartTLS 389"| LB["DNS / LB / Proxy"]
    LB --> N1["LDAP node A<br/>chứng chỉ server"]
    LB --> N2["LDAP node B<br/>chứng chỉ server"]
    A -.->|"Xác minh CA, hostname, thời hạn"| LB
    N1 --> D["Directory test<br/>DN, schema, ACL"]
    N2 --> D
~~~

**Điểm phải kiểm tra:** một endpoint đi qua load balancer có thể phát sinh handshake với **nhiều node** hoặc lớp TLS termination khác nhau. Thành công trên một node chưa chứng minh mọi đường kết nối đều hoạt động. Nếu TLS kết thúc ở proxy/LB, phải xác định và bảo vệ rõ ràng **chặng từ proxy/LB tới LDAP server** theo chính sách bảo mật; không được giả định tự động có mã hóa end-to-end.

## 3. Nắm rõ hai kiểu kết nối TLS trước khi test

| Tiêu chí | LDAPS | LDAP + StartTLS |
|---|---|---|
| URL thường gặp | `ldaps://ldap.stage.example.org:636` | `ldap://ldap.stage.example.org:389` |
| Khi nào TLS bắt đầu? | Ngay khi client mở kết nối | Sau khi client gửi yêu cầu StartTLS và server chấp nhận nâng cấp |
| Thời điểm được phép gửi password | Sau handshake TLS và xác minh server thành công | **Chỉ sau khi StartTLS hoàn tất và xác minh server thành công** |
| Kiểm thử CLI | `openssl s_client -connect ...`, `ldapwhoami -H ldaps://...` | `openssl s_client -starttls ldap ...`, `ldapwhoami -ZZ -H ldap://...` |
| Lỗi cấu hình điển hình | Trust chain, SAN hoặc sai cổng | Server không hỗ trợ StartTLS, client không bắt buộc nâng cấp, pooling sai |

**LDAPS và StartTLS đều có thể đáp ứng yêu cầu mã hóa kết nối** nếu được cấu hình và xác minh đúng. Sự khác biệt là vị trí bước nâng cấp TLS trong giao thức. Không có cơ sở coi `ldap://...:389` là kết nối bảo mật nếu client chưa yêu cầu và hoàn tất StartTLS.

Trong phạm vi bài, chọn **một phương án chính** giống production rồi kiểm thử kỹ phương án đó; nếu ứng dụng hỗ trợ cả hai, chạy bộ ca kiểm thử tương ứng cho từng phương án.

## 4. Chuẩn bị trước khi chạy lệnh

### 4.1. Thông số thử nghiệm

Giả sử hệ thống staging dùng:

~~~text
LDAP_HOST:      ldap.stage.example.org
LDAP_LDAPS:     ldaps://ldap.stage.example.org:636
LDAP_STARTTLS:  ldap://ldap.stage.example.org:389
BASE_DN:        dc=example,dc=org
SEARCH_BASE:    ou=people,dc=example,dc=org
SERVICE_DN:     cn=svc-ldap-test,ou=system,dc=example,dc=org
TEST_USER:      uid=ldap-tls-test,ou=people,dc=example,dc=org
TRUSTED_CA:     ./certs/staging-ca.pem
~~~

Tệp `staging-ca.pem` cần chứa CA tin cậy để xác minh certificate chain phục vụ LDAP staging. CA này phải được người quản trị PKI phê duyệt và phân phối qua kênh tin cậy, **không lấy một certificate bất kỳ từ kết nối chưa xác minh rồi lập tức tin cậy nó**.

Chuẩn bị thêm: OpenSSL, công cụ OpenLDAP (ví dụ `ldapwhoami`, `ldapsearch`), `keytool` của JDK và quyền xem log server/proxy ở staging. Lệnh bên dưới dùng cú pháp shell POSIX; trên Windows có thể chạy trong môi trường Linux container/WSL hoặc điều chỉnh đúng cú pháp terminal, công cụ và đường dẫn.

### 4.2. Điều kiện bắt buộc để test có giá trị

- Dùng **hostname mà ứng dụng sẽ kết nối**, không thay bằng IP trừ khi chứng chỉ có IP SAN và ứng dụng thực sự dùng IP.
- Client có đường mạng thực tế tới các LDAP endpoint và các lớp firewall/proxy tương đương production.
- Đồng hồ của client và server được đồng bộ; sai lệch thời gian có thể làm chứng chỉ “chưa hiệu lực” hoặc “hết hạn”.
- Tài khoản test có secret riêng được quản lý trong vault/secret manager; không ghi mật khẩu vào command line, repository, log hoặc URL.
- Có kết quả kỳ vọng cho từng ca và quyền quan sát server để phân biệt lỗi TLS với lỗi LDAP bind/ACL.

## 5. Kiểm thử handshake và certificate bằng OpenSSL

### 5.1. LDAPS: xác minh CA và hostname

Trên máy test có OpenSSL, chạy:

~~~bash
openssl s_client \
  -connect ldap.stage.example.org:636 \
  -servername ldap.stage.example.org \
  -CAfile ./certs/staging-ca.pem \
  -verify_hostname ldap.stage.example.org \
  -verify_return_error \
  -showcerts < /dev/null
~~~

Các tùy chọn có ý nghĩa:

| Tùy chọn | Kiểm tra điều gì? |
|---|---|
| `-connect` | Mở kết nối tới hostname/cổng LDAP staging |
| `-servername` | Gửi SNI (nếu endpoint hỗ trợ hoặc yêu cầu) |
| `-CAfile` | Dùng CA tin cậy do đội PKI cung cấp |
| `-verify_hostname` | Kiểm tra danh tính tên máy chủ trong chứng chỉ |
| `-verify_return_error` | Kết thúc thất bại nếu quá trình xác minh chứng chỉ có lỗi |
| `-showcerts` | Hiển thị certificate chain để chẩn đoán |

**Kết quả mong đợi:** bắt tay thành công với thuật toán và phiên bản TLS được chính sách cho phép; chứng chỉ còn hiệu lực; chuỗi ký được xác minh bằng CA đã định; tên `ldap.stage.example.org` khớp SAN; đầu ra có chỉ báo xác minh thành công (chẳng hạn `Verify return code: 0 (ok)`). Không chỉ dựa vào việc có socket TCP mở hoặc OpenSSL in ra một certificate.

Nếu TLS đi qua load balancer, cần kiểm tra cả đường đi trực tiếp đến từng node theo thiết kế và tên máy chủ mà client thực sự dùng. Không bỏ qua kiểm tra hostname chỉ để có kết quả “pass”.

### 5.2. StartTLS: kiểm tra nâng cấp giao thức

Với endpoint cho phép StartTLS:

~~~bash
openssl s_client \
  -starttls ldap \
  -connect ldap.stage.example.org:389 \
  -servername ldap.stage.example.org \
  -CAfile ./certs/staging-ca.pem \
  -verify_hostname ldap.stage.example.org \
  -verify_return_error \
  -showcerts < /dev/null
~~~

Tùy chọn `-starttls ldap` yêu cầu OpenSSL thực hiện phần trao đổi StartTLS của LDAP trước khi bắt tay TLS. Kết quả thành công chứng tỏ endpoint **hỗ trợ nâng cấp** và certificate đã được xác minh theo các tùy chọn trên.

Tuy nhiên, một kiểm tra OpenSSL thành công **chưa xác minh Spring LDAP thực sự yêu cầu StartTLS**. Cần kiểm thử trong chính ứng dụng Java với `ContextSource`/JNDI và chiến lược StartTLS được cấu hình; không suy từ URL `ldap://` rằng mọi bind phía ứng dụng đã dùng TLS.

### 5.3. Kiểm tra chứng chỉ và phiên bản TLS

Khi gặp lỗi, xác minh:

1. **SAN/hostname:** giá trị DNS hoặc IP thực tế mà client dùng có trong SAN hợp lệ hay không.
2. **Certificate chain:** server/proxy có gửi đủ intermediate certificates cần thiết hay không và CA root có trong truststore của client.
3. **Validity:** `Not Before` và `Not After` có phù hợp thời điểm kiểm thử.
4. **Key usage/EKU:** chứng chỉ được cấp đúng mục đích cho TLS server.
5. **TLS protocol/cipher:** phiên bản được đàm phán nằm trong danh sách được policy cho phép (thông thường ưu tiên TLS 1.2/1.3 theo chính sách tổ chức và khả năng server/client).
6. **TLS ở mọi node:** những node cùng DNS/LB có cùng chính sách xác minh và chuỗi chứng chỉ hợp lệ.

Không sửa một lỗi handshake bằng cách tắt xác minh CA, tắt hostname verification hoặc cho phép cipher/protocol đã bị cấm. Khi thử nghiệm failover, chỉ dùng những nút/địa chỉ mà đội vận hành đã cấp quyền kiểm tra.

## 6. Kiểm thử bind và search **sau** khi TLS thành công

OpenSSL kiểm tra kết nối TLS, nhưng ứng dụng cần thêm bằng chứng rằng **LDAP bind và search** hoạt động đúng trên kênh đã bảo vệ.

### 6.1. LDAPS với `ldapwhoami`

~~~bash
LDAPTLS_CACERT=./certs/staging-ca.pem \
ldapwhoami -x \
  -H ldaps://ldap.stage.example.org:636 \
  -D "cn=svc-ldap-test,ou=system,dc=example,dc=org" \
  -W
~~~

Ý nghĩa: `-x` dùng simple bind, `-H` chỉ endpoint LDAPS, `-D` là DN tài khoản dịch vụ và `-W` **nhập mật khẩu tương tác** thay vì để trên dòng lệnh. Với cấu hình CA hợp lệ, thành công thường trả về danh tính đã bind:

~~~text
dn:cn=svc-ldap-test,ou=system,dc=example,dc=org
~~~

Biến `LDAPTLS_CACERT` là cấu hình dành cho **OpenLDAP command-line client**; nó không tự trở thành truststore của Java. Các client LDAP khác có thể dùng cách cấu hình trust riêng.

### 6.2. StartTLS bắt buộc với `-ZZ`

~~~bash
LDAPTLS_CACERT=./certs/staging-ca.pem \
ldapwhoami -x -ZZ \
  -H ldap://ldap.stage.example.org:389 \
  -D "cn=svc-ldap-test,ou=system,dc=example,dc=org" \
  -W
~~~

`-ZZ` trong bộ công cụ OpenLDAP **yêu cầu StartTLS thành công** trước các thao tác tiếp theo; nếu server không hỗ trợ hoặc đàm phán TLS thất bại, lệnh phải thất bại. Tránh dùng tùy chọn StartTLS không bắt buộc rồi cho phép tiếp tục đăng nhập không mã hóa.

**Tiêu chí đạt:** LDAP không nhận credential từ ứng dụng qua kênh plaintext. Nếu StartTLS không thể kích hoạt, luồng phải **fail closed** và không tiếp tục simple bind trên kết nối không được bảo vệ.

### 6.3. Kiểm tra quyền search

~~~bash
LDAPTLS_CACERT=./certs/staging-ca.pem \
ldapsearch -x \
  -H ldaps://ldap.stage.example.org:636 \
  -D "cn=svc-ldap-test,ou=system,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s sub \
  "(&(objectClass=inetOrgPerson)(uid=ldap-tls-test))" \
  uid cn
~~~

Trong directory staging giả định, kết quả dự kiến:

~~~ldif
dn: uid=ldap-tls-test,ou=people,dc=example,dc=org
uid: ldap-tls-test
cn: LDAP TLS Test
~~~

Kết quả này cho biết **tài khoản dịch vụ** có thể tìm/đọc entry test sau khi kết nối LDAPS thành công. Nó không chứng minh mật khẩu của người dùng cuối hợp lệ; muốn kiểm thử authentication cần thêm **user bind** bằng tài khoản test, trên kênh TLS và với mật khẩu được cấp riêng.

Nếu bind thành công nhưng search trả rỗng hoặc lỗi, cần phân biệt search base/scope/filter, schema, ACL và dữ liệu thực. Đừng coi tất cả lỗi là “TLS lỗi”. Với username từ request, dùng `LdapQueryBuilder` hoặc filter builder an toàn trong Spring LDAP; các filter literal trong ví dụ CLI chỉ dành cho dữ liệu thử nghiệm cố định.

## 7. Cấu hình Spring Boot/Spring LDAP cho kiểm thử LDAPS

### 7.1. Sử dụng `spring.ldap`

Với ứng dụng Spring Boot đã cài Spring LDAP, một ví dụ `application-staging.yml`:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.stage.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các giá trị được lấy từ **biến môi trường hoặc secret manager**. Ví dụ `LDAP_URL=ldaps://ldap.stage.example.org:636` và bind DN là `cn=svc-ldap-test,ou=system,dc=example,dc=org`. Spring LDAP dùng `ContextSource` để tạo kết nối; `LdapTemplate` sử dụng context đó để search/lookup.

Với **LDAPS**, JVM dùng cấu hình tin cậy TLS của JSSE, chẳng hạn truststore được chỉ định bằng system property khi chạy ứng dụng:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/secure/config/ldap-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

Mật khẩu của truststore (nếu cần) phải được cấp bằng cơ chế secret/runtime an toàn và không hardcode trong tài liệu hoặc script dùng chung. Truststore cần được chuẩn bị và quản lý qua quy trình PKI. Không đặt `javax.net.ssl.trustStore` trỏ thẳng đến certificate chain tải từ một host chưa xác minh chỉ để vượt qua handshake.

### 7.2. Import CA vào truststore có kiểm soát

Trong quy trình thiết lập được đội PKI phê duyệt, có thể tạo hoặc cập nhật truststore test bằng JDK `keytool`:

~~~bash
keytool -importcert \
  -alias ldap-staging-ca \
  -file ./certs/staging-ca.pem \
  -keystore ./certs/ldap-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh có thể hỏi mật khẩu truststore qua prompt. Sau khi import, kiểm tra alias, subject, issuer và fingerprint với dữ liệu CA đáng tin đã nhận **qua kênh quản trị PKI**:

~~~bash
keytool -list -v \
  -keystore ./certs/ldap-truststore.p12 \
  -storetype PKCS12 \
  -alias ldap-staging-ca
~~~

Nên tin cậy CA thích hợp thay vì tùy tiện thêm từng chứng chỉ server rồi bỏ quên quy trình đổi chứng chỉ. Tùy chính sách, tổ chức có thể quản lý trust anchor qua JVM truststore, container image, runtime secret, SSL bundle hoặc cơ chế triển khai riêng.

**Quan trọng:** thành công ở `ldapwhoami` không bảo đảm thành công ở Java, vì bộ công cụ OpenLDAP và JVM có thể dùng **hai kho CA khác nhau**. Ngược lại, Java tin CA cũng không chứng minh ứng dụng đang gọi đúng hostname. Phải chạy kiểm thử ở cả lớp CLI và chính ứng dụng.

### 7.3. Kiểm thử truy vấn qua `LdapTemplate`

Đoạn service sau cho phép chạy smoke test tìm entry dự kiến; nó không xử lý đăng nhập hay cấp quyền HTTP:

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

@Service
public class LdapTlsProbe {
    private final LdapTemplate ldapTemplate;

    public LdapTlsProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findTestUser() {
        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.SUBTREE)
                .attributes("uid")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is("ldap-tls-test");

        return ldapTemplate.search(
                query,
                (AttributesMapper<String>) attrs ->
                        attrs.get("uid").get().toString()
        );
    }
}
~~~

Khi `spring.ldap.base=dc=example,dc=org`, `base("ou=people")` tìm dưới `ou=people,dc=example,dc=org`. Kết quả mong đợi là **đúng một** `uid=ldap-tls-test` trong dữ liệu staging. Query phải thất bại về kết nối hoặc ném lỗi tương ứng nếu TLS bị từ chối; không nên dùng một handler “bắt mọi lỗi rồi trả danh sách rỗng” để che mất `SSLHandshakeException`.

### 7.4. Kiểm thử tích hợp bằng JUnit

Một integration test với JUnit 5 có thể chạy khi pipeline cung cấp endpoint và chứng chỉ staging đã phê duyệt:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("staging")
@EnabledIfEnvironmentVariable(
        named = "RUN_LDAP_TLS_IT", matches = "true"
)
class LdapTlsIntegrationTest {

    @Autowired
    private LdapTlsProbe probe;

    @Test
    void canSearchTestEntryThroughConfiguredTlsConnection() {
        assertThat(probe.findTestUser())
                .containsExactly("ldap-tls-test");
    }
}
~~~

**Phạm vi khẳng định:** test này xác minh Spring LDAP có thể dùng connection đã cấu hình để search và nhận đúng dữ liệu. Nó **không tự xác minh** toàn bộ tính an toàn nếu môi trường đã vô tình tắt kiểm tra certificate/hostname; vì vậy cần thêm các **negative tests** và kiểm tra cấu hình. Nếu dùng StartTLS, thiết lập `ContextSource`/JNDI với chiến lược StartTLS tương ứng và chạy lại cùng kiểu test qua đường kết nối đó.

Không để test gọi LDAP production, không commit secret hoặc CA private key. Chạy bài kiểm thử mạng trên staging có phép; unit test không cần LDAP thật vẫn dùng để kiểm tra logic xây filter và xử lý kết quả.

## 8. Ma trận kiểm thử tích cực và kiểm thử thất bại

Bộ ca kiểm thử nên ghi rõ **điều kiện**, **hành vi kỳ vọng**, **lớp cần quan sát** và **kết quả thực tế**. Những ca tạo lỗi TLS cần thực hiện trên endpoint/giả lập có quyền kiểm soát; không chủ ý làm hỏng chứng chỉ hoặc cổng của production.

| Kịch bản | Kết quả cần thấy | Chú ý |
|---|---|---|
| CA đúng, hostname khớp SAN, cert hợp lệ | Handshake pass; service bind/search pass | Positive baseline |
| Client không tin CA của server | Handshake thất bại; không gửi bind password | Kiểm tra JVM và CLI riêng |
| Dùng hostname không có trong SAN | Hostname verification thất bại | Không tắt verify để “pass” |
| Server gửi thiếu intermediate cần thiết | Chain verification thất bại nếu client không xây được đường tin cậy | Đánh giá chain server/LB |
| Chứng chỉ hết hạn hoặc chưa hiệu lực | TLS bị từ chối theo chính sách xác minh | Dùng cert test được cấp cho ca âm |
| Server/proxy không hỗ trợ StartTLS | Lệnh `-ZZ` và Java StartTLS path thất bại | Không fallback sang simple bind plaintext |
| Cổng LDAPS không mở | TCP connection fail/timeout; không được ghi là sai mật khẩu | Kiểm tra DNS/firewall/LB |
| Protocol/cipher không giao nhau | Handshake fail, có lỗi negotiation | Không hạ chuẩn bảo mật ngoài chính sách |
| User bind với mật khẩu sai sau TLS hợp lệ | TLS pass; LDAP báo lỗi xác thực | Không nhầm với lỗi SSL |
| Service account thiếu quyền search | TLS và service bind có thể pass; search lỗi/không thấy entry | Phân biệt ACL/schema/base |
| Một node trong cụm có chứng chỉ sai | Đường qua node đó phải fail; phát hiện node không đồng nhất | Kiểm tra từng đường failover |
| Cert được thay/CA rotation có kiểm soát | Các node/client tin chuỗi mới theo kế hoạch; không mất kết nối ngoài mục tiêu | Kết nối cũ/pool cần được quan sát |
| Server bật yêu cầu client certificate (nếu dùng mTLS) | Chỉ client có identity hợp lệ mới kết nối | Cần keystore client riêng truststore |

### 8.1. Thực hiện negative tests đúng cách

Với các trường hợp như CA không tin, SAN sai, cert hết hạn, hãy dùng một **LDAP test endpoint hoặc TLS proxy** được dựng riêng trong staging để mô phỏng. Các bước:

1. Chạy test positive với endpoint hợp lệ để có baseline.
2. Thay **một yếu tố** của endpoint/CA ở môi trường cô lập: certificate hoặc hostname được thiết kế cố ý không hợp lệ.
3. Khởi động **JVM mới** với truststore và cấu hình tương ứng để tránh hiệu ứng cache `SSLContext`/connection pool từ lần trước.
4. Xác minh handshake thất bại trước LDAP bind, log nêu loại lỗi TLS và **không phát sinh phiên LDAP được xác thực**.
5. Khôi phục cấu hình positive và chạy lại smoke test.

Nếu server gửi cert không hợp lệ mà ứng dụng vẫn kết nối/bind được, đó là dấu hiệu **kiểm tra certificate hoặc hostname đang bị vô hiệu hóa**; cần chặn triển khai và điều tra.

### 8.2. Kiểm thử không hạ cấp sang plaintext

Với StartTLS, thiết kế phải yêu cầu TLS rõ ràng. Khi endpoint không chấp nhận StartTLS:

- Không tự chuyển qua `ldap://` và tiếp tục simple bind bằng mật khẩu.
- Không bỏ qua lỗi StartTLS để thử LDAP bind tiếp trên kết nối cũ.
- Không sử dụng `LDAPTLS_REQCERT=never` trong OpenLDAP hoặc trust manager “accept all” trong Java để buộc test thành công.
- Xác minh ứng dụng ghi lại lỗi kết nối bảo mật (đủ chi tiết để vận hành) và trả phản hồi ngoài không lộ credential.

Với LDAPS, khi cổng 636 lỗi không nên âm thầm thử cổng 389 không mã hóa. Nếu tồn tại cấu hình failover, mọi endpoint hợp lệ phải đáp ứng cùng yêu cầu TLS.

## 9. Pooling, failover và thay chứng chỉ

### 9.1. Pooling có thể che lỗi

Khi ứng dụng dùng JNDI/Spring LDAP pooling, một số request có thể tái sử dụng kết nối đã bắt tay TLS trước đó; đổi chứng chỉ ở server không nhất thiết gây handshake ngay cho kết nối cũ. Vì vậy:

- Kiểm thử **kết nối mới** sau khi đổi certificate hoặc CA.
- Kiểm thử kết nối **tái sử dụng**, reconnect sau idle timeout và khi pool bị đóng.
- Cấu hình pool tôn trọng danh tính của service account/user bind; không trộn context đã bind bằng người dùng vào pool tài khoản dịch vụ.
- Nếu dùng StartTLS, xác nhận cơ chế pooling hỗ trợ đúng chiến lược nâng cấp; không suy rằng mọi kiểu JNDI pooling đều tương thích.

### 9.2. Failover nhiều node

Ở hệ thống nhiều nút, từng node cần:

1. Trình certificate chain hợp lệ với hostname thực tế hoặc hostname mà client kết nối qua LB.
2. Hỗ trợ các TLS version/cipher được yêu cầu.
3. Có cấu hình LDAP bind/search/ACL đủ nhất quán để request không thất bại bất thường khi đổi node.
4. Được giám sát khi handshake lỗi sau rollout chứng chỉ.

Một vòng kiểm thử nên bao gồm **khởi tạo kết nối mới lần lượt tới từng endpoint được duyệt**, thử mất một node và quan sát failover theo cấu hình. Nếu không thể ép test đi qua từng node do LB, cần phối hợp với đội vận hành hoặc dựa vào log/telemetry trên các node để xác minh, không tự suy từ một request thành công.

### 9.3. Rotation certificate

Quy trình đổi chứng chỉ nên có giai đoạn chuẩn bị trust anchor mới, triển khai cert server, kiểm tra mọi node, refresh/khởi động lại kết nối mới khi cần và chỉ loại bỏ CA cũ khi toàn bộ client đã chuyển đổi. Phải thử cả **kết nối mới sau rotation** lẫn **kết nối đang tồn tại** theo yêu cầu thời gian gián đoạn.

Thời gian còn lại đến khi hết hạn chứng chỉ, cảnh báo sắp hết hạn và quy trình rollback nên được thống nhất trước rollout. Không coi “TLS handshake từng thành công tháng trước” là bằng chứng sau khi CA hoặc server certificate đã thay đổi.

## 10. Chẩn đoán sự cố theo từng lớp

| Dấu hiệu | Lớp có khả năng lỗi | Cần kiểm tra |
|---|---|---|
| `UnknownHostException` hoặc DNS không phân giải | DNS | Tên miền, bản ghi, môi trường DNS |
| `Connection refused`, `Connect timed out` | Mạng / cổng / LB | Firewall, route, port, backend node |
| `PKIX path building failed` | Trust/certificate chain Java | JVM truststore, CA, intermediate cert |
| `No subject alternative DNS name matching ...` | Hostname verification | SAN và hostname trong URL |
| `certificate expired` / `not yet valid` | Thời hạn chứng chỉ hoặc clock | NotBefore/NotAfter, NTP |
| `SSLHandshakeException` do protocol/cipher | TLS negotiation | Phiên bản TLS, cipher, JDK/server policy |
| StartTLS extension bị từ chối | LDAP protocol / StartTLS | Server có hỗ trợ, ACL, proxy và cách cấu hình client |
| `invalidCredentials (49)` sau handshake pass | LDAP authentication | Service DN/password hoặc user credential theo ngữ cảnh |
| `insufficientAccessRights (50)` | LDAP ACL | Quyền search/read theo bind DN |
| `noSuchObject (32)` | LDAP directory/search | Base DN và vị trí entry |

**Không đồng nhất “TLS OK” với “LDAP login OK”.** Một kết nối có thể bắt tay TLS thành công rồi thất bại vì sai mật khẩu hoặc thiếu quyền. Ngược lại, nếu xuất hiện lỗi certificate, đừng thông báo nguyên nhân kỹ thuật đó ra giao diện đăng nhập như một cách tiết lộ cấu trúc hạ tầng.

### 10.1. Debug TLS trong JVM có kiểm soát

Trong môi trường kiểm thử cô lập, có thể bật JSSE debug cho một lần chạy:

~~~bash
java \
  -Djavax.net.ssl.debug=ssl,handshake \
  -Djavax.net.ssl.trustStore=/secure/config/ldap-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

Nhật ký có thể cho thấy bước chọn protocol/cipher, certificate chain và lỗi verification. **Chỉ bật trong thời gian chẩn đoán cần thiết**, kiểm soát quyền xem log và tắt sau test. Không dump mật khẩu LDAP, secret của service account, token hoặc nội dung entry nhạy cảm.

Spring LDAP/JNDI có thể bọc lỗi bắt tay TLS trong ngoại lệ kết nối/`NamingException` hoặc ngoại lệ LDAP của Spring; khi xử lý log hãy xem **root cause** thay vì chỉ dựa vào thông báo “LDAP operation failed”.

### 10.2. Những sai lầm thường gặp

1. Chỉ test `openssl s_client` rồi kết luận ứng dụng Java tin CA: **CLI và JVM có truststore khác nhau**.
2. Kết nối TCP tới cổng 636 thành công rồi coi TLS đã pass: **chưa xác minh chứng chỉ hoặc LDAP bind**.
3. Sử dụng IP thay hostname để “cho kết nối”, trong khi certificate chỉ có DNS SAN.
4. Cấp trust cho certificate bất kỳ tải từ server chưa xác minh nguồn.
5. Tắt hostname verification hoặc trust manager kiểm tra tất cả chứng chỉ là hợp lệ.
6. Dùng `ldap://` và tin rằng vì server có cổng 636 nên kết nối cổng 389 của ứng dụng tự được bảo vệ.
7. Chỉ test một node sau LB, bỏ qua khả năng node khác dùng certificate chain cũ.
8. Chỉ test kết nối đang nằm trong pool, không ép tạo kết nối mới sau rotation.
9. Thử simple bind với password trên shell command line, vô tình để lộ trong lịch sử lệnh và process list.
10. Bắt mọi exception thành `false`, khiến lỗi TLS bị hiểu nhầm là mật khẩu sai.

## 11. Checklist nghiệm thu và báo cáo kết quả

Đây là checklist có thể áp dụng cho một lần kiểm thử staging/pre-production:

| Hạng mục | Bằng chứng cần lưu | Tiêu chí PASS |
|---|---|---|
| Endpoint và mạng | Hostname, port, tuyến DNS/LB đã kiểm tra | Mọi đường kết nối trong phạm vi hoạt động |
| Certificate và chain | Subject/SAN, issuer, fingerprint, validity, chain | Khớp hostname, không hết hạn, CA đáng tin |
| Protocol/cipher | TLS version/cipher đã negotiate | Thuộc chính sách được phê duyệt |
| OpenSSL LDAPS/StartTLS | Kết quả lệnh có certificate verification | Handshake hợp lệ theo kiểu kết nối được dùng |
| LDAP bind | `ldapwhoami` với tài khoản test | Bind sau TLS pass; sai mật khẩu bị từ chối |
| LDAP search | `ldapsearch` hoặc `LdapTemplate` | Trả entry test đúng vùng và ACL |
| Java truststore | Cấu hình JVM và integration test | Spring LDAP thực sự kết nối và search thành công |
| Negative tests | Ca CA/SAN/expiry/StartTLS fail | Không bind plaintext, không tắt verify |
| Failover/pooling | Log các node, reconnect/new handshake | Không bỏ qua node lỗi; hoạt động theo chính sách |
| Secret/log | Log đã rà soát, cấu hình secret | Không ghi credential/hash, log có mã lỗi phù hợp |
| Rollback/rotation | Kịch bản và kết quả diễn tập | Có thể đổi/khôi phục cert an toàn |

Nhóm vận hành có thể lưu báo cáo ngắn theo mẫu sau. Chỉ ghi thông tin đủ để truy vết; không đưa mật khẩu hoặc nội dung entry thật vào tài liệu:

~~~text
Môi trường:          staging
Ứng dụng/JDK:        <version>
Spring Boot/LDAP:    <version>
Endpoint/kiểu TLS:   <hostname:port> / LDAPS hoặc StartTLS
Truststore alias:    <alias được duyệt>
Certificate issuer:  <CA được duyệt>
Certificate SAN:     <hostname được xác minh>
TLS phiên bản:       <version đã negotiate>
Service bind:        PASS/FAIL
Search test entry:   PASS/FAIL
Negative tests:      PASS/FAIL theo từng ca
Failover/rotation:   PASS/FAIL hoặc NOT_APPLICABLE có lý do
Thời điểm và log ID: <timestamp, correlation ID>
Người phê duyệt:     <đội chịu trách nhiệm>
~~~

Không có “PASS chung” nếu một ca âm quan trọng chứng minh ứng dụng vẫn chấp nhận chứng chỉ sai hoặc fallback sang plaintext. Việc chấp nhận giới hạn test phải được ghi rõ để người chịu trách nhiệm bảo mật quyết định trước khi triển khai.

## 12. Bài tập và câu hỏi tự kiểm tra

### Bài tập thực hành

Trong staging có hai node LDAP và một DNS `ldap.stage.example.org`, hãy:

1. Dùng OpenSSL xác minh certificate chain/SAN cho LDAPS và kiểm tra cả hai node theo phương án được cho phép.
2. Bind tài khoản dịch vụ bằng `ldapwhoami`, sau đó tìm `uid=ldap-tls-test` bằng `ldapsearch`.
3. Chạy integration test Spring Boot dùng chính truststore JVM của ứng dụng.
4. Dựng một endpoint test cố ý dùng CA không tin cậy, xác minh JVM **từ chối** và không gửi bind password.
5. Nếu có StartTLS, kiểm thử `ldapwhoami -ZZ` và chặn mọi đường fallback plaintext.
6. Mô phỏng rotation trên staging rồi kiểm thử kết nối mới và kết nối pool.

### Câu hỏi

1. Vì sao `openssl s_client` báo certificate hợp lệ nhưng Spring LDAP vẫn gặp lỗi `PKIX path building failed`?
2. Trong StartTLS, thao tác nào **phải hoàn tất trước** simple bind chứa mật khẩu?
3. Một kết nối LDAPS bắt tay thành công nhưng `ldapsearch` không tìm thấy entry. Có thể có những nguyên nhân nào?
4. Vì sao chỉ một request thành công qua load balancer chưa đủ để xác nhận toàn bộ LDAP cluster?
5. Sau khi server thay chứng chỉ, tại sao phải ép tạo thêm kết nối mới thay vì chỉ gọi request trên pool cũ?
6. Khi người dùng nhập sai password nhưng TLS hợp lệ, log và phản hồi nên phân loại sự kiện thế nào?
7. Nếu server chứng chỉ sai SAN mà ứng dụng vẫn bind thành công, cần điều tra điều gì?

**Gợi ý trả lời:** (1) CLI và JVM dùng truststore/chính sách khác nhau. (2) Nâng cấp StartTLS cùng xác minh certificate/hostname. (3) Base, scope, filter, ACL, schema hoặc entry không tồn tại. (4) Có thể một node dùng cert/CA sai. (5) Kết nối cũ có thể đã handshake trước rotation. (6) Lỗi xác thực LDAP, không phải lỗi TLS; bên ngoài tránh tiết lộ tài khoản. (7) Khả năng hostname verification hoặc xác minh certificate đã bị tắt/bỏ qua.

## Tài liệu tham khảo

- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `ContextSource`, kết nối và thao tác LDAP.
- [Spring Boot LDAP Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.ldap): thuộc tính `spring.ldap` và cách cấu hình kết nối trong Spring Boot.
- [OpenLDAP Admin Guide — TLS](https://openldap.org/doc/admin24/tls.html): CA, certificate và yêu cầu TLS cho OpenLDAP.
- [Java JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): truststore, TLS handshake và cấu hình JSSE.

## Kết luận

Kiểm thử TLS cho Spring LDAP trên môi trường gần production phải xác nhận **đúng toàn bộ chuỗi**: đường mạng và endpoint → handshake TLS → CA/certificate chain → hostname/SAN → service bind → LDAP search hoặc user bind → kiểm tra lỗi và phân quyền phù hợp. Hãy kết hợp OpenSSL, công cụ OpenLDAP và integration test dùng **truststore Java thật**, bổ sung các ca âm để chứng minh ứng dụng từ chối chứng chỉ không tin cậy và không truyền password trên kết nối plaintext. Cuối cùng, kiểm tra cả failover, connection pooling và certificate rotation trước khi phê duyệt triển khai production.
