# Xác thực thất bại sau đổi mật khẩu hoặc thay chứng chỉ

Trong chương **Chẩn đoán** của **SPRING_DATA_LDAP**, lỗi xác thực ngay sau khi đổi mật khẩu hoặc thay chứng chỉ thường khiến người vận hành kiểm tra nhầm lớp. Một thông báo chung như “LDAP authentication failed” có thể bắt nguồn từ nhiều tình huống: ứng dụng vẫn Bind bằng password cũ, pool tiếp tục cấp connection đã Bind trước khi password thay đổi, truststore chưa nhận CA mới, certificate chain thiếu intermediate, hostname không khớp SAN, hoặc ứng dụng vẫn dùng SSLContext cũ.

Cần phân biệt hai giai đoạn của một kết nối LDAP bảo mật:

1. **TLS handshake:** client xác minh certificate chain và hostname của LDAP server, sau đó thiết lập kênh TLS.
2. **LDAP Bind:** client gửi danh tính và credential để directory xác thực người dùng hoặc service account.

Nếu TLS handshake thất bại, LDAP Bind chưa diễn ra. Nếu TLS handshake thành công nhưng Bind bị từ chối, cần kiểm tra principal, password, trạng thái account và policy của directory. Một pool connection đã được Bind trước đó có thể vẫn hoạt động sau khi password thay đổi, tùy server; validation trên connection cũ không chứng minh password mới có hiệu lực.

Bài học này trình bày cách phân biệt các trường hợp đó, kiểm tra một Bind mới độc lập với pool, cập nhật truststore đúng cách, thay thế connection pool theo từng đợt, xác minh kết quả sau rotation và kiểm thử các tình huống lỗi thường gặp.

**Mục tiêu:** hiểu sự khác nhau giữa TLS handshake và LDAP Bind; nhận diện stale authenticated sessions trong pool; biết giới hạn của connection validation; xác minh password mới bằng một Bind mới; xử lý certificate chain, trust anchor và hostname verification; làm mới SSLContext và pooled connections sau certificate rotation; phân biệt lỗi ứng dụng với lỗi directory; và triển khai quy trình rotation có rollback, observability cùng integration tests.

## 1. Xác thực LDAP có hai lớp

### 1.1. TLS handshake xác minh máy chủ

Với LDAPS, TLS được thiết lập ngay khi mở socket tới endpoint có scheme **ldaps://**. Với StartTLS, client mở kết nối LDAP trước rồi gửi StartTLS extended operation để nâng cấp kết nối lên TLS. Sau handshake, client mới gửi LDAP Bind trên kênh đã được bảo vệ.

Client thường kiểm tra:

- Certificate còn hiệu lực theo thời gian.
- Certificate chain dẫn tới một trust anchor được tin cậy.
- Intermediate certificate cần thiết có trong chain hoặc trust configuration.
- Hostname của endpoint khớp với SAN trong certificate.
- Certificate không bị từ chối bởi policy của client.
- Nếu dùng mutual TLS, certificate client và private key phù hợp với yêu cầu server.

Một handshake thất bại thường xuất hiện dưới dạng **SSLHandshakeException**, **SSLPeerUnverifiedException**, **CertificateException**, **CertPathValidatorException** hoặc exception mạng được bọc bên ngoài. Hãy kiểm tra cause chain theo class và loại lỗi; không kết luận dựa trên một message chung.

### 1.2. LDAP Bind xác minh danh tính

Sau TLS handshake, client thực hiện Bind. Với SIMPLE Bind, client gửi DN/principal và password. Directory kiểm tra credential cùng trạng thái và policy của account.

Bind thất bại có thể do:

- Password cũ còn được cấu hình trong ứng dụng.
- Secret mới chưa được mount hoặc chưa được đọc bởi process.
- Password có ký tự đặc biệt bị shell, YAML hoặc secret templating làm thay đổi.
- DN của service account đã thay đổi.
- Account bị khóa, hết hạn, disabled hoặc cần đổi password.
- Directory policy yêu cầu cơ chế xác thực khác.
- Password mới chưa được replicate tới server/replica mà client đang kết nối.
- Connection pool đang cấp lại session được Bind bằng credential cũ.

LDAP result code **invalidCredentials** thường là code 49, nhưng server có thể che một số chi tiết để tránh tiết lộ thông tin. Không coi code 49 là bằng chứng password duy nhất là nguyên nhân.

### 1.3. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
    A["Ứng dụng mở LDAP connection"] --> B{"TLS handshake thành công?"}
    B -- "Không" --> C["Kiểm tra certificate chain, truststore, SAN, thời hạn, protocol"]
    C --> D["Tạo SSLContext/socket mới và kết nối lại"]
    B -- "Có" --> E{"LDAP Bind thành công?"}
    E -- "Không" --> F["Kiểm tra principal, password, account state, policy, replica"]
    F --> G["Thử Bind mới bằng ContextSource.getContext(principal, credentials)"]
    E -- "Có" --> H{"Connection lấy từ pool?"}
    H -- "Có" --> I["Kiểm tra tuổi connection, pool key, credential version và drain"]
    H -- "Không" --> J["Xác minh operation và ACL"]
    I --> K["Tạo pool/connection mới rồi chạy smoke test"]
    D --> K
    G --> K
~~~

## 2. Hiểu connection cũ sau khi đổi password

### 2.1. Password thay đổi không đồng nghĩa session cũ tự Bind lại

LDAP Bind xác thực connection tại thời điểm Bind. Một connection đã Bind thành công có thể tiếp tục được server xem là authenticated cho đến khi connection đóng, server chủ động revoke session hoặc một policy riêng có hiệu lực. Hành vi sau password rotation phụ thuộc directory server và cấu hình bảo mật.

Vì vậy, hai điều sau có thể cùng đúng:

- Một connection đã mở trước rotation vẫn thực hiện được Search hoặc Modify.
- Một Bind mới dùng password cũ bị từ chối.

Đây không nhất thiết là lỗi cache password trong ứng dụng. Đó có thể là session cũ vẫn còn tồn tại.

### 2.2. Spring LDAP pool giả định credentials ổn định

Spring LDAP có thể pool các **DirContext** read-only và read-write riêng. Các context được lấy qua **getReadOnlyContext()** và **getReadWriteContext()** được tái sử dụng theo pool key. Pool giả định environment và credentials của các context cùng loại là ổn định.

Điều này quan trọng khi dùng **AuthenticationSource** trả credentials thay đổi theo thread hoặc thay đổi trong thời gian chạy. Pool có thể tiếp tục cấp một context được tạo bằng credential trước đó; việc đổi password trong secret source không tự động Bind lại mọi context đang nằm trong pool.

Spring LDAP cũng nêu rõ **PoolingContextSource.getContext(principal, credentials)** là đường lấy context xác thực bằng principal/credentials được cung cấp và không sử dụng native Java LDAP pooling, nhằm để password reset có hiệu lực với các lần xác thực mới sớm nhất có thể.

### 2.3. Connection validation không kiểm tra password mới

Các tùy chọn như **testOnBorrow**, **testOnReturn**, **testWhileIdle** và **DirContextValidator** giúp kiểm tra context hiện có còn sử dụng được hay không. Validator thường thực hiện một operation nhẹ trên context đã được Bind. Nó không đóng context rồi thực hiện Bind mới bằng password hiện tại.

Ví dụ:

1. Connection A được Bind bằng password cũ lúc 09:00.
2. Password account được đổi lúc 10:00.
3. Pool validation lúc 10:01 thực hiện một Search thành công trên connection A.
4. Ứng dụng kết luận pool healthy.
5. Một request khác cần mở connection mới và Bind bằng password cũ; Bind đó thất bại.

Validation thành công chỉ chứng minh session đang được kiểm tra vẫn dùng được cho operation validator. Nó không chứng minh secret mới đã được load hoặc directory chấp nhận credential mới.

### 2.4. Phân biệt service pool và user authentication

| Luồng | Danh tính | Vòng đời |
| --- | --- | --- |
| Repository/service operations | Service account cố định | Dùng read/write pool, credential được quản lý theo pool lifecycle |
| User login verification | DN và password do người dùng cung cấp | Tạo Bind riêng cho lần xác thực, đóng context sau khi kiểm tra |

Không đưa dynamic user credentials vào service pool. Không thay đổi Bind identity của một context đang nằm trong pool để thử password mới. Việc đó có thể làm rò identity giữa các request.

## 3. Chẩn đoán password rotation

### 3.1. Xác minh secret mà process thực sự đang dùng

Đừng chỉ kiểm tra secret trong secret manager hoặc file cấu hình. Process có thể vẫn dùng giá trị đã đọc lúc startup.

Kiểm tra theo thứ tự:

1. Xác nhận secret version mới đã được publish.
2. Xác nhận secret volume/environment/configuration đã được cập nhật trong container hoặc VM.
3. Xác nhận process đã nhận giá trị mới theo cơ chế reload mà ứng dụng hỗ trợ.
4. Xác nhận bean **LdapContextSource** hoặc **AuthenticationSource** đang dùng version mới.
5. Không in password ra console, log, actuator endpoint hoặc exception.
6. Ghi một **credentialVersion**/secret version ID không nhạy cảm để theo dõi rollout.

Không dùng hash không key của password để làm version identifier. Dùng version ID do secret manager cấp hoặc một label nội bộ không chứa secret.

### 3.2. Thử một Bind mới ngoài pool

Dùng **ContextSource.getContext(principal, credentials)** với principal và password mới để tạo một context riêng. Đóng context ngay sau khi xác minh.

~~~java
import javax.naming.directory.DirContext;

import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.support.LdapUtils;
import org.springframework.stereotype.Component;

@Component
public class DirectoryBindVerifier {

    private final ContextSource contextSource;

    public DirectoryBindVerifier(ContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void verifyNewBind(String userDn, String password) {
        DirContext context = null;
        try {
            context = contextSource.getContext(userDn, password);
            // Bind đã thành công. Không ghi password hoặc raw context.
        } finally {
            LdapUtils.closeContext(context);
        }
    }
}
~~~

Đây là phép kiểm tra một Bind mới. Với **PooledContextSource**, method này đi theo đường xác thực bằng credential được truyền vào và không dùng native Java LDAP pooling. Kiểm tra API của đúng phiên bản Spring LDAP đang dùng; nếu bean được inject là một wrapper tùy biến, xác minh wrapper có giữ nguyên semantics của **getContext(principal, credentials)**.

Không bắt mọi exception rồi trả **false**. Phân biệt ít nhất authentication rejection, TLS handshake/certificate failure, network timeout/server unavailable, pool/resource acquisition failure và DN syntax/configuration error.

Một Bind test cũng không chứng minh account có quyền Search/Modify mà service cần. Nó chỉ xác minh việc tạo context và Bind cho danh tính/credential đã truyền.

### 3.3. Đọc lại trạng thái qua connection mới

Sau khi Bind thành công, dùng context mới để chạy một operation read-only tối thiểu mà account cần được phép thực hiện. Ví dụ đọc một entry cấu hình hoặc base object được dành riêng cho health check.

Không dùng một Search quá rộng hoặc đọc attribute nhạy cảm chỉ để kiểm tra. Dùng base/filter cố định, scope hẹp, count limit và time limit.

### 3.4. Khi nào cần drain pool?

Cần làm mới pool khi service account password đã thay đổi, pool vẫn giữ connection được Bind bằng credential cũ, TLS socket factory/trust configuration thay đổi, server certificate rotation yêu cầu handshake mới, hoặc có dấu hiệu connection stale sau failover/server restart.

Một connection đang được request sử dụng không nên bị đóng cưỡng bức giữa operation nếu có thể tránh. Hãy drain có kiểm soát:

1. Ngừng nhận operation mới trên pool cũ hoặc chuyển traffic sang pool mới.
2. Chờ active borrower hoàn tất trong giới hạn thời gian.
3. Đóng/huỷ pool cũ và context idle.
4. Tạo ContextSource/pool mới từ cấu hình và secret version mới.
5. Chạy Bind, Search và operation smoke test.
6. Chuyển traffic sang pool mới.
7. Theo dõi lỗi và giữ phương án quay lại pool/configuration trước trong thời gian cho phép.

Nếu framework/configuration không hỗ trợ thay bean pool an toàn trong runtime, dùng rolling restart hoặc blue-green deployment để tạo process mới với pool mới. Đừng sửa password trên object đang được nhiều thread dùng nếu không có cơ chế đồng bộ và thay pool được thiết kế rõ ràng.

### 3.5. Kiểm tra replica và replication delay

Trong hệ thống nhiều LDAP server:

- Password có thể đã được đổi trên một node nhưng chưa replicate tới node khác.
- Load balancer có thể đưa Bind mới tới replica chưa cập nhật.
- Các node có thể có policy lockout hoặc password history khác nhau.
- Một lần Bind thành công trên node A không chứng minh node B đã nhận password mới.

Ghi **directoryAlias**, endpoint alias và node/replica alias đã được xác minh. Không log raw referral hoặc endpoint nội bộ. Kiểm tra từng replica bằng công cụ quản trị được phép và cùng một test account, nhưng tránh thử sai password lặp lại vì có thể kích hoạt account lockout.

## 4. Quy trình password rotation an toàn

### 4.1. Rotation service account

Một quy trình có khoảng thời gian overlap credential thường giảm rủi ro:

1. Tạo hoặc cấp password mới theo policy.
2. Cập nhật secret manager và gắn version mới.
3. Triển khai một application instance/pool mới sử dụng credential mới.
4. Kiểm tra Bind mới và các operation tối thiểu.
5. Chuyển traffic sang instance/pool mới.
6. Drain và đóng pool cũ.
7. Chỉ thu hồi password cũ khi mọi instance đã chuyển và không còn connection cần giữ.
8. Xác minh metrics và audit sau rotation.

Không phải directory nào cũng hỗ trợ hai password đồng thời cho một account. Nếu không có overlap, phối hợp thứ tự cập nhật và thời điểm revoke với người quản trị directory; có thể cần cửa sổ bảo trì hoặc một service account thay thế tạm thời theo policy.

### 4.2. Rotation password người dùng

Khi user đổi password, không sửa password trong service account pool. Lần đăng nhập tiếp theo phải thực hiện Bind mới bằng password được gửi trong lần đăng nhập đó; đóng context xác thực sau khi kiểm tra; không cache password người dùng; không log password cũ/mới hoặc đưa chúng vào metric label. Nếu có password grace period/replication delay, hiển thị thông báo chung và tuân thủ policy xác thực của tổ chức.

Nếu ứng dụng giữ connection pool riêng cho từng user, cần rà soát lại thiết kế. Pool dynamic user identity làm phức tạp isolation và rotation; thông thường nên dùng Bind riêng cho authentication và pool service identity cho repository operations.

### 4.3. Không kiểm tra password bằng cách đọc userPassword

Không đọc **userPassword** để so sánh với password do người dùng cung cấp. Directory chịu trách nhiệm xác minh Bind credential. Attribute này có thể bị ACL bảo vệ, chứa hash/scheme khác nhau và việc đọc nó không thay thế được authentication protocol.

## 5. Chẩn đoán certificate rotation

### 5.1. Xác định loại certificate đã thay

| Thay đổi | Điều client cần kiểm tra |
| --- | --- |
| Server leaf certificate được gia hạn, cùng CA | Validity, SAN, chain và trust anchor hiện có |
| Leaf certificate đổi sang CA khác | Bổ sung trust anchor/chain mới theo policy |
| Intermediate CA được thay | Intermediate chain có được server gửi đầy đủ và client trust path có hợp lệ không |
| Root CA thay | Truststore phải tin cậy root mới theo kế hoạch overlap |
| Hostname/endpoint thay | SAN phải khớp hostname client thực sự kết nối |
| Client certificate thay (mutual TLS/EXTERNAL) | Server truststore, client key material, alias và expiry |
| TLS protocol/cipher policy thay | JVM/provider và LDAP server phải có bộ giao thức/cipher chung |

Không import leaf certificate một cách máy móc khi chính sách của tổ chức yêu cầu trust CA. Ngược lại, nếu dùng certificate pinning hoặc trust leaf có chủ đích, phải quản lý pin rotation và overlap cẩn thận.

### 5.2. Truststore và hostname verification

Truststore xác định CA/certificate mà client tin cậy. Hostname verification xác minh certificate được cấp cho đúng endpoint. Hai kiểm tra này độc lập.

Một certificate chain hợp lệ nhưng SAN không khớp hostname vẫn phải bị từ chối. Không tắt hostname verification để làm cho kết nối hoạt động; hãy sửa DNS/endpoint hoặc cấp certificate có SAN đúng.

Không dùng trust-all TrustManager, **NoopHostnameVerifier**, hoặc cấu hình bỏ qua certificate validation trong production.

### 5.3. LDAPS và StartTLS có cách cấu hình khác nhau

**LDAPS** dùng URL **ldaps://host:636**. Với Spring Boot, SSL bundle của LDAP có thể cấu hình qua **spring.ldap.ssl.bundle**; nếu tự tạo **LdapContextSource**, phải tự cấu hình SSL/trust material cho bean đó. Cấu hình SSL bundle của LDAP chỉ áp dụng cho LDAPS, không tự cấu hình StartTLS.

**StartTLS** bắt đầu từ URL **ldap://host:389**, sau đó nâng cấp bằng **DefaultTlsDirContextAuthenticationStrategy** hoặc strategy phù hợp. Có thể cung cấp **SSLSocketFactory** cho strategy. Native JNDI pooling phải tắt khi dùng TLS strategy; Spring LDAP pooling có thể dùng nếu lifecycle và TLS shutdown được kiểm thử với server đích.

### 5.4. Truststore mới không tự cập nhật SSLContext đang chạy

JSSE **SSLContext** được khởi tạo với key managers và trust managers. Socket factory tạo từ context đó sử dụng cấu hình trust đã nạp. Việc thay file truststore trên disk không tự sửa trust managers của SSLContext hiện tại, cũng không thay đổi TLS session đã được thiết lập.

Sau khi truststore thay đổi, cần tạo SSLContext/socket factory mới và mở connection mới. Nếu ứng dụng dùng default JSSE truststore được nạp lúc process khởi động, cách đơn giản và dễ kiểm soát thường là rolling restart. Nếu dùng custom SSLContext, cần tạo lại bean/connection source/pool theo một lifecycle được thiết kế rõ ràng.

## 6. Cấu hình TLS cho Spring LDAP

### 6.1. LDAPS với Spring Boot SSL bundle

Ví dụ cấu hình endpoint và bundle:

~~~yaml
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: uid=app-service,ou=services,dc=example,dc=org
    password: ${LDAP_SERVICE_BIND_PASSWORD}
    ssl:
      bundle: ldap-directory
~~~

Bundle **ldap-directory** cần được định nghĩa trong cấu hình SSL bundle của Spring Boot, chứa trust material đúng với CA chain của LDAP server. Cấu hình bundle phụ thuộc loại bundle được chọn (JKS/PKCS12 hoặc PEM) và phiên bản Spring Boot.

Nếu ứng dụng khai báo bean **LdapContextSource** riêng, các property SSL auto-configuration không tự động cấu hình bean đó. Hãy xác minh bean thực tế đang dùng trust material mới; không chỉ kiểm tra file YAML.

Không đưa password vào command line, source control hoặc log. Placeholder password phải được thay bằng secret do secret manager hoặc cơ chế bảo vệ tương đương cung cấp.

### 6.2. StartTLS với SSLContext tùy chỉnh

Đoạn ví dụ sau tạo SSLContext từ truststore PKCS12 và cung cấp socket factory cho Spring LDAP StartTLS strategy:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;

@Configuration
public class DirectoryStartTlsConfiguration {

    @Bean
    SSLContext directorySslContext(
            Path trustStorePath,
            char[] trustStorePassword) throws Exception {

        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(trustStorePath)) {
            trustStore.load(input, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
            null,
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );
        return sslContext;
    }

    @Bean
    DefaultTlsDirContextAuthenticationStrategy startTlsStrategy(
            SSLContext directorySslContext) {
        DefaultTlsDirContextAuthenticationStrategy strategy =
            new DefaultTlsDirContextAuthenticationStrategy();
        strategy.setSslSocketFactory(
            directorySslContext.getSocketFactory()
        );
        strategy.setShutdownTlsGracefully(false);
        return strategy;
    }
}
~~~

Ví dụ giả định ứng dụng đã cung cấp **trustStorePath** và **trustStorePassword** qua configuration/secret provider an toàn. Không lưu password truststore trong source control hoặc in nó ra log. Nếu dùng client certificate, cần nạp KeyManager phù hợp vào **SSLContext.init**; ví dụ trên chỉ cấu hình trust phía client.

Gắn strategy vào **LdapContextSource**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;

@Configuration
public class DirectoryContextSourceConfiguration {

    @Bean
    LdapContextSource directoryContextSource(
            DefaultTlsDirContextAuthenticationStrategy startTlsStrategy) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldap://directory.example.org:389");
        source.setBase("dc=example,dc=org");
        source.setUserDn(
            "uid=app-service,ou=services,dc=example,dc=org"
        );
        source.setPassword(loadServicePassword());
        source.setAuthenticationStrategy(startTlsStrategy);

        // Tắt native JNDI pooling; có thể bọc bằng Spring LDAP pool riêng.
        source.setPooled(false);
        return source;
    }

    private String loadServicePassword() {
        return System.getenv("LDAP_SERVICE_BIND_PASSWORD");
    }
}
~~~

Phương thức **setAuthenticationStrategy** và kiểu strategy phải được đối chiếu với phiên bản Spring LDAP trong ứng dụng. Khi dùng StartTLS, cần kiểm thử cả thiết lập lẫn đóng TLS session vì các directory server có behavior khác nhau.

### 6.3. Cấu hình pool

Nếu dùng Spring LDAP pool, bọc ContextSource đã cấu hình TLS bằng pool Spring LDAP. Không bật native JNDI pooling bên trong ContextSource cùng lúc. Cần kiểm tra:

- Pool chỉ chứa connection đã được tạo với trust configuration hiện hành.
- Pool validation không bị hiểu nhầm là kiểm tra lại certificate.
- Khi truststore hoặc SSLContext thay đổi, pool cũ được drain và destroy.
- Context đang active được xử lý theo deadline trước khi pool cũ bị đóng.
- Pool mới có validator và giới hạn borrow phù hợp.

## 7. Kiểm tra certificate trước khi thay ứng dụng

### 7.1. Kiểm tra endpoint và chain bằng OpenSSL

Với LDAPS:

~~~bash
openssl s_client \
  -connect directory.example.org:636 \
  -servername directory.example.org \
  -showcerts \
  -verify_return_error
~~~

Với StartTLS nếu OpenSSL build hỗ trợ LDAP STARTTLS:

~~~bash
openssl s_client \
  -connect directory.example.org:389 \
  -starttls ldap \
  -servername directory.example.org \
  -showcerts \
  -verify_return_error
~~~

Kiểm tra certificate leaf và SAN, subject/issuer và thời hạn, chain server gửi, verify return code, hostname được gửi trong SNI, và certificate mới có được endpoint thực tế phục vụ trên tất cả node hay chưa.

OpenSSL test không chứng minh JVM truststore đang dùng cùng trust anchors hoặc cùng hostname verification policy. Đây là bước kiểm tra endpoint độc lập.

### 7.2. Kiểm tra truststore bằng keytool

~~~bash
keytool -list -v \
  -keystore /secure/path/ldap-truststore.p12 \
  -storetype PKCS12
~~~

Xác minh alias, subject, issuer, validity và fingerprint. Không đưa password truststore vào command line hoặc shell history; dùng prompt hoặc secret provider an toàn theo môi trường.

### 7.3. Kiểm tra bằng LDAP client

Một test Bind bằng OpenLDAP client có thể giúp tách lỗi server khỏi lỗi ứng dụng:

~~~bash
ldapwhoami \
  -H ldaps://directory.example.org:636 \
  -x \
  -D "uid=app-service,ou=services,dc=example,dc=org" \
  -W
~~~

Với StartTLS:

~~~bash
ldapwhoami \
  -H ldap://directory.example.org:389 \
  -ZZ \
  -x \
  -D "uid=app-service,ou=services,dc=example,dc=org" \
  -W
~~~

**-W** yêu cầu nhập password tương tác. Không dùng **-w password** trong script hoặc command history. Đảm bảo LDAP client sử dụng đúng CA trust configuration và hostname verification; nếu không, kết quả có thể khác JVM.

## 8. Phân biệt Bind failure với TLS failure

| Dấu hiệu | Khả năng cần kiểm tra trước | Hướng xác minh |
| --- | --- | --- |
| SSLHandshakeException | Chain, trust anchor, protocol/cipher hoặc certificate | Kiểm tra cause chain và endpoint certificate |
| CertPathValidatorException | Chain không dẫn tới trust anchor hoặc certificate policy | Kiểm tra CA/intermediate và truststore |
| CertificateExpiredException | Leaf/intermediate/root hết hạn hoặc chưa có hiệu lực | Kiểm tra validity trên mọi node |
| SSLPeerUnverifiedException | Hostname/certificate peer verification | So SAN với hostname client dùng |
| LDAP code 49 / AuthenticationException | DN/password/account policy | Bind mới bằng credential hiện tại |
| CommunicationException | Network/TLS/provider có thể bị bọc chung | Kiểm tra nested cause và kết nối endpoint |
| Pool borrow timeout | Pool exhausted hoặc context leak | Kiểm tra active/idle/waiters và transaction duration |
| Bind mới thành công nhưng repository lỗi | Service account có thể thiếu ACL hoặc repository dùng pool cũ | Kiểm tra service identity và pool generation |
| Connection cũ hoạt động, connection mới thất bại | Credential/trust rotation chưa được process mới nhận | Tạo connection mới và so sánh secret/trust version |

Không phải mọi lỗi TLS đều có một exception class giống nhau giữa JVM provider, LDAP server và Spring LDAP version. Ghi exception class/cause class, operation và endpoint alias; không parse message text thành một kết luận chắc chắn.

## 9. Quy trình thay certificate không gây gián đoạn

### 9.1. Chuẩn bị trust overlap

Nếu CA cũ và CA mới có thể cùng được tin cậy trong giai đoạn chuyển tiếp:

1. Xác minh CA mới qua kênh quản trị đáng tin cậy.
2. Thêm CA mới vào truststore cùng CA cũ theo policy.
3. Kiểm tra fingerprint và chain.
4. Tạo SSLContext mới từ truststore đã cập nhật.
5. Tạo pool/instance mới và thực hiện handshake mới.
6. Xác minh tất cả endpoint LDAP phục vụ chain được chấp nhận.
7. Chuyển traffic sang pool mới.
8. Sau khi toàn bộ node đã chuyển, gỡ CA cũ theo kế hoạch.

Trust overlap chỉ an toàn khi cả CA cũ và mới đều còn được tổ chức tin cậy. Không thêm certificate không xác minh chỉ để khắc phục lỗi handshake.

### 9.2. Blue-green pool hoặc rolling restart

Một mô hình triển khai:

~~~text
Pool A / generation 17
  SSLContext trust version = 4
  service credential version = 12
  active borrowers = 3

        prepare

Pool B / generation 18
  SSLContext trust version = 5
  service credential version = 13
  new TLS handshakes = PASS
  new Bind = PASS
  smoke Search = PASS

        switch traffic

Pool A
  stop new borrows
  wait active borrowers
  close idle contexts
  destroy pool
~~~

Ghi generation/version ID không nhạy cảm trong log và metrics. Không ghi password, private key hoặc nội dung truststore.

### 9.3. Rollback

Nếu pool mới không qua smoke test:

- Giữ pool cũ nếu certificate/password cũ vẫn còn được phép.
- Không chuyển traffic một phần nếu kết quả chưa rõ.
- Kiểm tra truststore, hostname, secret version và endpoint alias.
- Sửa cấu hình và tạo generation mới.
- Nếu certificate cũ đã bị thu hồi hoặc password cũ đã bị revoke, không rollback về credential/certificate không còn hợp lệ; chuyển sang recovery plan đã phê duyệt.

## 10. Quy trình password và certificate cùng thay đổi

Khi hai rotation xảy ra trong cùng cửa sổ, thay từng lớp một để xác định lỗi chính xác:

1. Kiểm tra certificate endpoint bằng công cụ TLS độc lập.
2. Cập nhật trust material và tạo SSLContext/pool mới.
3. Xác minh TLS handshake mới thành công.
4. Thực hiện Bind mới bằng service credentials hiện tại.
5. Cập nhật service password và tạo pool generation tiếp theo nếu cần.
6. Xác minh Bind mới bằng credential mới.
7. Chạy Search/operation smoke test.
8. Chuyển traffic và drain pool cũ.
9. Xác minh metrics, error rate và directory audit.
10. Thu hồi trust/credential cũ theo lịch đã thống nhất.

Nếu có thể, không thay CA, endpoint, service DN và password trong cùng một thay đổi. Nếu buộc phải thay đồng thời, lưu rõ từng version và thực hiện các phép kiểm tra độc lập cho TLS và Bind.

## 11. Observability cho rotation

Ghi các trường an toàn, có thể truy vết:

| Field/metric | Ý nghĩa |
| --- | --- |
| directoryAlias | Directory logic đang được gọi |
| endpointAlias | Node/endpoint đã được xác minh |
| poolGeneration | Pool generation hiện tại |
| credentialVersion | Version ID của secret, không phải secret |
| trustVersion | Version ID của trust material |
| operation | BIND, SEARCH, MODIFY hoặc HEALTH_CHECK |
| tlsHandshakeOutcome | SUCCESS/FAILED/NOT_ATTEMPTED |
| bindOutcome | SUCCESS/REJECTED/UNKNOWN |
| exceptionClass | Lớp exception đã kiểm soát |
| causeClass | Lớp cause đã kiểm soát |
| durationMs | Thời gian operation |
| poolActive / poolIdle | Số context đang mượn/đang chờ |
| poolWaiters | Số request đang chờ context |
| rotationGeneration | Đợt rotation đang triển khai |

Không ghi password, raw DN, Bind environment, private key, raw certificate PEM hoặc truststore password. Không dùng username/email làm metric label.

### 11.1. Các metric cần theo dõi

- Số TLS handshake failure theo endpoint alias.
- Số Bind rejection theo directory alias và operation class.
- Số lần connection được tạo mới.
- Pool active/idle/waiters và borrow latency.
- Tỷ lệ operation lỗi trước/sau switch.
- Số instance đang chạy trust/credential version cũ.
- Số context còn active trong pool cũ.
- Số lần validator loại connection stale.

Một validator có thể tăng tỷ lệ context bị loại khi server đóng connection idle, nhưng không thay thế một Bind mới để kiểm tra password mới và không buộc TLS handshake mới trên connection đã mở.

## 12. Ma trận kiểm thử rotation

Thực hiện trong integration/staging environment với test account và certificate test phù hợp. Các test có thể cần LDAP server thật hoặc container có TLS; mock exception đơn thuần không xác minh được handshake, Bind và pool lifecycle.

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| ROT01 | Bind mới bằng password hiện tại | Thành công |
| ROT02 | Bind mới bằng password cũ sau rotation | Bị từ chối theo policy của directory |
| ROT03 | Bind mới bằng password mới | Thành công |
| ROT04 | Pool còn context đã Bind bằng password cũ | Xác nhận hành vi session cũ theo server |
| ROT05 | Pool validator chạy trên session cũ | Không coi kết quả là bằng chứng password mới |
| ROT06 | getContext(principal, credentials) với password mới | Tạo Bind mới thành công |
| ROT07 | getContext với password sai | Phân loại authentication rejection |
| ROT08 | Secret manager đã đổi nhưng process chưa reload | Phát hiện credentialVersion cũ |
| ROT09 | Pool generation mới dùng password mới | Bind và smoke operation thành công |
| ROT10 | Drain pool cũ khi có borrower active | Request đang chạy hoàn tất trong deadline |
| ROT11 | Destroy pool cũ | Context idle được đóng, không còn borrow mới |
| ROT12 | Certificate leaf gia hạn cùng CA | Handshake mới thành công |
| ROT13 | Certificate chain dùng CA mới đã trust | Handshake mới thành công |
| ROT14 | Truststore thiếu CA mới | Handshake thất bại có phân loại TLS |
| ROT15 | Intermediate certificate bị thiếu | Chain validation phát hiện lỗi |
| ROT16 | Certificate hết hạn | Handshake thất bại; không bypass validation |
| ROT17 | SAN không khớp hostname | Hostname verification từ chối |
| ROT18 | DNS/endpoint alias đổi nhưng SAN cũ | Phát hiện mismatch |
| ROT19 | Truststore file đổi nhưng SSLContext cũ còn sống | Connection cũ không tự nhận trust manager mới |
| ROT20 | Tạo SSLContext mới và connection mới | Trust material mới được áp dụng |
| ROT21 | StartTLS với truststore mới | Handshake thành công trên connection mới |
| ROT22 | LDAPS với SSL bundle mới | Auto-configured ContextSource dùng bundle mới |
| ROT23 | Custom ContextSource cùng SSL bundle property | Xác minh custom bean được cấu hình TLS riêng |
| ROT24 | Tắt native pooling khi StartTLS | TLS lifecycle hoạt động đúng |
| ROT25 | Pool Spring LDAP bọc StartTLS ContextSource | Borrow/return và TLS shutdown hoạt động đúng |
| ROT26 | Replica A đã cập nhật password, replica B chưa | Phát hiện kết quả Bind khác nhau theo endpoint |
| ROT27 | Password change đồng thời certificate rotation | Phân biệt TLS và Bind bằng phép thử độc lập |
| ROT28 | Pool mới không qua health check | Traffic vẫn ở pool cũ nếu còn an toàn |
| ROT29 | Pool cũ đã drain, credential cũ bị revoke | Không còn request dùng credential cũ |
| ROT30 | Rollback sau switch thất bại | Chỉ quay lại credential/certificate còn hợp lệ |
| ROT31 | Bind thất bại lặp lại | Rate limit/lockout policy không bị khuếch đại bởi retry |
| ROT32 | LDAP server đóng connection idle | Validator loại connection stale |
| ROT33 | Pool hết context khi drain | Request chờ trong giới hạn, không treo vô hạn |
| ROT34 | TLS hostname verification bật | Không có trust-all hoặc NoopHostnameVerifier |
| ROT35 | Log khi rotation thất bại | Không có password, raw DN, PEM hoặc private key |
| ROT36 | Nhiều instance chạy các generation khác nhau | Có thể xác định instance nào chưa rotation |
| ROT37 | Rolling restart hoàn tất | Không còn instance dùng trust/credential version cũ |
| ROT38 | User password rotation | User Bind mới được kiểm tra riêng, không thay đổi service pool |
| ROT39 | Service account rotation | Repository pool mới dùng đúng service identity |
| ROT40 | Kết thúc rotation | Error rate, pool metrics và audit trở về trạng thái ổn định |

## 13. Checklist xử lý sự cố

### Khi Bind thất bại sau đổi password

1. Kiểm tra TLS handshake trước; xác nhận connection tới đúng endpoint.
2. Xác minh process đang dùng secret version mới.
3. Kiểm tra service DN/principal và trạng thái account.
4. Dùng **getContext(principal, credentials)** để thử Bind mới.
5. Nếu Bind mới thành công nhưng repository vẫn lỗi, kiểm tra pool generation và service identity.
6. Drain/recreate pool để loại context cũ.
7. Kiểm tra replica/replication delay và account lockout policy.
8. Không log password hoặc thử lặp password sai không giới hạn.

### Khi TLS thất bại sau thay chứng chỉ

1. Lấy certificate chain từ đúng endpoint và port.
2. Xác minh validity, issuer, SAN và fingerprint qua kênh tin cậy.
3. Kiểm tra truststore mà JVM/process thực sự sử dụng.
4. Kiểm tra thiếu intermediate hoặc CA mới.
5. Kiểm tra hostname client dùng có khớp SAN.
6. Xác định LDAPS hay StartTLS và cấu hình đúng cơ chế.
7. Tạo SSLContext/socket factory mới.
8. Tạo connection/pool mới hoặc rolling restart.
9. Chạy TLS handshake, Bind mới và smoke operation.
10. Không tắt hostname verification hoặc chuyển sang plaintext.

## 14. Những lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ cập nhật secret manager | Process có thể vẫn dùng secret cũ | Theo dõi secret version và reload/restart |
| Chỉ chạy pool validation sau password rotation | Session cũ vẫn có thể được Bind hợp lệ | Thử Bind mới và drain pool |
| Dùng AuthenticationSource động với pool service | Pool có thể tái sử dụng context của credentials trước | Giữ service identity ổn định hoặc thay pool |
| Dùng service pool để kiểm tra password người dùng | Trộn identity và lifecycle | User Bind riêng bằng getContext(principal, credentials) |
| Thay truststore file và kỳ vọng SSLContext tự reload | Trust managers cũ vẫn được dùng | Tạo SSLContext/socket factory mới |
| Giữ connection TLS cũ sau certificate rotation | Connection không handshake lại | Mở connection mới và thay pool |
| Chỉ kiểm tra chain, bỏ hostname | Có thể kết nối nhầm endpoint | Giữ hostname verification |
| Import leaf certificate tùy tiện | Truststore khó quản lý và có thể trust sai | Theo trust policy CA/pinning đã phê duyệt |
| Tắt trust/hostname verification | Cho phép MITM | Sửa chain, SAN hoặc truststore |
| Fallback LDAPS sang LDAP plaintext | Lộ credential và dữ liệu | Fail closed |
| Thay password và certificate cùng lúc không có versioning | Khó xác định lớp gây lỗi | Ghi version và test từng lớp |
| Drain pool bằng cách đóng mọi context active ngay | Request đang chạy bị gián đoạn | Stop borrow, wait, close idle, destroy |
| Retry Bind failure liên tục | Account lockout và log flood | Không retry credential rejection |
| Tin rằng Bind success đồng nghĩa ACL đúng | Search/Modify vẫn có thể bị từ chối | Chạy smoke operation theo quyền cần thiết |

## 15. Câu hỏi tự kiểm tra

1. **TLS handshake và LDAP Bind khác nhau thế nào?** TLS xác minh certificate/thiết lập kênh; Bind xác minh danh tính LDAP trên kênh đó.
2. **Handshake thất bại thì Bind đã xảy ra chưa?** Thông thường chưa; client chưa có kênh TLS để gửi Bind.
3. **Vì sao connection cũ có thể hoạt động sau password rotation?** Session đã Bind có thể vẫn được server giữ trạng thái authenticated cho đến khi đóng hoặc bị revoke.
4. **Pool validation chứng minh điều gì?** Connection hiện tại còn trả lời được operation validator; nó không chứng minh password mới được chấp nhận.
5. **getContext(principal, credentials) hữu ích khi nào?** Khi cần tạo Bind mới với credential cụ thể, chẳng hạn xác minh password mới.
6. **Spring LDAP pool giả định gì về credentials?** Context read-only/read-write trong từng pool key có environment/credentials ổn định.
7. **Có nên đưa dynamic user credentials vào service pool không?** Không; user authentication nên có Bind riêng và đóng context.
8. **Thay truststore file có tự cập nhật SSLContext hiện tại không?** Không; trust managers được cấu hình khi SSLContext được khởi tạo.
9. **Vì sao phải tạo connection mới sau certificate rotation?** TLS certificate được xác minh trong handshake; connection đã mở không tự handshake lại.
10. **Trust chain hợp lệ nhưng hostname sai thì có được kết nối không?** Không; hostname verification vẫn phải từ chối.
11. **LDAPS và StartTLS khác nhau thế nào?** LDAPS dùng TLS ngay từ lúc mở socket; StartTLS nâng cấp kết nối LDAP sau khi mở.
12. **Spring Boot LDAP SSL bundle có tự cấu hình StartTLS không?** Không; SSL bundle LDAP áp dụng cho LDAPS; StartTLS cần TLS authentication strategy riêng.
13. **Tại sao cần tắt native JNDI pooling với StartTLS?** TLS strategy cần kiểm soát lifecycle của connection; native pooling có thể giữ context/TLS state không phù hợp.
14. **Có thể dùng trust-all để khắc phục certificate rotation không?** Không; phải cập nhật trust material và giữ hostname verification.
15. **Nếu Bind mới thành công nhưng repository vẫn lỗi thì kiểm tra gì?** Pool cũ, service identity, ACL và ContextSource mà repository đang dùng.
16. **Nếu nhiều replica có kết quả Bind khác nhau thì sao?** Kiểm tra replication và endpoint routing; không retry password sai liên tục.
17. **Khi nào nên dùng rolling restart?** Khi process không hỗ trợ thay SSLContext/pool an toàn tại runtime.
18. **Sau rotation cần kiểm tra gì ngoài Bind?** Search/operation smoke test, pool metrics, endpoint version và directory audit.

## Tài liệu tham khảo

- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html)
- [Spring LDAP — PooledContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/pool2/factory/PooledContextSource.html)
- [Spring LDAP — ContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/ContextSource.html)
- [Spring LDAP — Configuration and TLS](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Spring LDAP — DefaultTlsDirContextAuthenticationStrategy API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/DefaultTlsDirContextAuthenticationStrategy.html)
- [Spring Boot — LDAP SSL configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html)

**Ghi nhớ:** Password rotation và certificate rotation tác động lên hai giai đoạn khác nhau. Bind mới xác minh credential mới; TLS handshake mới xác minh truststore, certificate chain và hostname. Context đã được Bind hoặc TLS handshake từ trước có thể tiếp tục hoạt động, nên pool validation không thay thế hai phép thử mới này. Sau khi cập nhật secret hoặc trust material, hãy tạo pool/SSLContext generation mới, kiểm tra handshake, Bind và operation cần thiết, chuyển traffic rồi drain pool cũ. Không tắt hostname verification, không fallback plaintext và không log password hay private key.

