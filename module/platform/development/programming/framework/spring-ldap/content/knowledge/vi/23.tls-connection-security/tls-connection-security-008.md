# Luân phiên certificate và secret cho kết nối Spring LDAP

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt việc xoay vòng **certificate của LDAP server**, **CA/truststore phía ứng dụng**, **client certificate/private key dùng cho mutual TLS** và **mật khẩu bind của tài khoản dịch vụ**.
2. Lập một kế hoạch chuyển đổi có thời gian chồng lấn, kiểm tra trước, giám sát sau và phương án rollback mà không bỏ xác thực TLS.
3. Hiểu vai trò của `ContextSource`, `LdapTemplate`, `LdapClient`, LDAP authentication, LDAPS, StartTLS, SSL context và connection pooling trong quá trình thay đổi credentials.
4. Thử kết nối **mới** thực sự để xác nhận certificate/truststore/secret mới đang có hiệu lực; không nhầm kết nối đang mở với cấu hình đã được nạp lại.
5. Phân loại sự cố TLS handshake, thiếu CA, sai hostname, lỗi bind, secret hết hạn và kết nối còn giữ credential cũ.
6. Viết runbook, kiểm thử và quy trình quản lý bí mật phù hợp cho hệ thống LDAP thực tế.

> **Nguyên tắc:** “Đã thay file certificate” hoặc “đã đổi secret trong secret manager” chưa có nghĩa tiến trình Java đã sử dụng vật liệu mới. Cần kiểm tra **máy chủ đang trình bày gì, JVM tin cậy gì, kết nối đang dùng identity nào và connection pool có giữ phiên cũ hay không**.

## 1. Bốn thứ dễ bị gọi chung là “certificate/secret LDAP”

Một hệ thống Spring LDAP có thể dùng các loại vật liệu bảo mật khác nhau:

| Vật liệu | Ai sở hữu / dùng? | Dùng để làm gì? | Khi luân phiên cần cập nhật |
| --- | --- | --- | --- |
| **LDAP server certificate và private key** | LDAP server / load balancer TLS | Chứng minh danh tính endpoint `ldap.example.org`; mã hóa kênh | Endpoint cấp certificate mới và gửi đúng certificate chain |
| **CA certificate / truststore** | Ứng dụng Java đóng vai TLS client | Xác minh chữ ký chuỗi certificate của LDAP server | Các JVM/SSL context phải tin cậy CA mới trước khi server đổi chain |
| **Client certificate và private key** (chỉ khi có mTLS) | Ứng dụng Spring LDAP | Chứng minh danh tính client bằng TLS; có thể kết hợp SASL EXTERNAL | Client keystore/key material và trust policy phía LDAP server |
| **Service account bind secret** | Ứng dụng và hệ thống quản lý danh tính LDAP | Xác thực tài khoản đọc hoặc ghi thư mục qua LDAP bind | Password/token được cấp bởi hệ thống danh tính, cấu hình `ContextSource`, mọi phiên kết nối đã bind |

**Certificate công khai** như server leaf/CA không phải mật khẩu; **private key**, keystore password và service bind password là bí mật. Việc đưa public certificate vào truststore cần được kiểm tra nguồn gốc và dấu vân tay (fingerprint) theo quy trình PKI, vì thêm nhầm CA độc hại có thể mở rộng miền tin cậy.

Luân phiên certificate và luân phiên password là **hai thao tác độc lập**. Certificate hợp lệ không chứng minh reader bind password đúng; bind success không chứng minh TLS certificate/hostname được xác thực an toàn. Vì vậy, health check cần kiểm tra cả **TLS lẫn quyền LDAP thực sự**.

## 2. Bối cảnh kiến trúc: certificate được sử dụng ở đâu?

Giả sử ứng dụng Spring Boot/Spring LDAP truy cập LDAP theo cấu trúc:

```text
Spring application instance A/B/C
  ├─ ContextSource: ldaps://ldap.example.org:636
  ├─ Trust material: CA hiện tại / CA kế tiếp
  ├─ Bind identity: cn=directory-reader,ou=service-accounts,...
  ├─ Reader secret: từ secret manager/deployment secret
  ├─ LdapTemplate, LdapClient, Repository/ODM
  └─ Có thể có LDAP connection pool
              │
              │ TLS handshake / LDAP bind
              ▼
       LDAP DNS / TLS endpoint
              │
        LDAP server / replicas
              ├─ Server certificate + private key
              ├─ Certificate chain
              ├─ Identity directory / user entries
              └─ ACL / bind secret
```

**Luồng LDAPS:** client mở TCP tới endpoint `ldaps://...:636`; TLS handshake xác thực certificate trước các LDAP operation; client sau đó gửi LDAP bind qua kênh TLS.

**Luồng StartTLS:** client mở kết nối LDAP thường tới `ldap://...:389`, gửi LDAP StartTLS extended operation để nâng cấp **cùng kết nối** lên TLS, xác minh certificate, rồi mới gửi simple bind có password. Không được gửi mật khẩu trước khi StartTLS thành công, và không được fallback sang LDAP cleartext khi nâng cấp thất bại.

```mermaid
sequenceDiagram
    participant A as Spring LDAP client
    participant D as LDAP TLS endpoint
    A->>D: TCP connect
    Note over A,D: LDAPS: TLS ngay; StartTLS: negotiate TLS trước bind
    D-->>A: Server certificate + chain
    A->>A: Verify chain, validity, SAN/hostname, trust
    alt TLS hợp lệ
        A->>D: LDAP bind bằng reader identity + secret
        D-->>A: Bind accepted / rejected
        A->>D: Search/modify theo ACL
    else Certificate không hợp lệ
        A--xD: Ngừng kết nối, không gửi secret
    end
```

**Kết nối đã mở** thường vẫn sử dụng phiên TLS đã thỏa thuận trước đó; việc server thay certificate tác động ngay tới **TLS handshake mới**, chứ không “thay certificate” bên trong một kết nối đang hoạt động. Pool có thể khiến kiểm tra thành công dù JVM chưa tạo được kết nối mới với chain kế tiếp. Vì vậy, trong mọi lần luân phiên phải thử **fresh connection**.

## 3. Lập kế hoạch trước khi xoay vòng

### 3.1. Thu thập trạng thái hiện tại

Trước một thay đổi, ghi lại những thông tin sau (không ghi private key/password):

| Hạng mục | Ví dụ cần xác nhận |
| --- | --- |
| Tên endpoint | `ldap.example.org`, danh sách endpoint dự phòng hoặc load balancer |
| Giao thức và cổng | LDAPS `636` hoặc StartTLS `389` |
| Danh tính certificate | DNS SAN, issuer, serial/fingerprint, ngày `notBefore/notAfter` |
| Chain và trust | Root/intermediate nào được server gửi; truststore nào JVM đang thực sự dùng |
| Phiên bản nền tảng | Java runtime, Spring LDAP, Spring Boot và cơ chế SSL bundle nếu có |
| Bind identity | DN reader hoặc service account; nơi lấy secret; ACL được cấp |
| Connection lifecycle | JNDI native pooling, Spring LDAP `PoolingContextSource`, timeout/idle eviction |
| Replicas và rollout | Có bao nhiêu LDAP endpoint, ứng dụng, instance đang kết nối |
| Quan sát | TLS handshake failures, bind failures, operation latency, pool borrow error, login success |
| Kế hoạch khôi phục | Vật liệu đã được phê duyệt trước đó còn hiệu lực đến khi nào; người thực hiện rollback |

Không nên dùng ngày hết hạn của leaf certificate làm thời điểm duy nhất quyết định thay đổi. Cần đủ thời gian để **triển khai trust trước**, xác nhận tất cả instance đã nạp, rồi mới thay server. Với service secret, lịch thay đổi còn phụ thuộc LDAP server có hỗ trợ giai đoạn **cả secret cũ và mới cùng hợp lệ** hay không.

### 3.2. Định nghĩa điều kiện hoàn thành

Một lần xoay vòng thành công phải thỏa **đồng thời**:

1. Kết nối TLS **mới** tới tất cả endpoint thực sự xác thực được chain mới và hostname đích.
2. LDAP bind bằng reader identity được cấp phép hoạt động, **không** dùng anonymous fallback.
3. Search thử nghiệm trong base/scope được phép trả kết quả đúng theo ACL; nếu ứng dụng xác thực người dùng, đường search-then-bind vẫn hoạt động.
4. Không còn các instance/truststore/credential store dùng vật liệu sắp thu hồi sau thời điểm cutover.
5. Tỷ lệ lỗi handshake/bind/timeout không tăng bất thường; pool không giữ phiên lỗi hoặc phiên chứa credential cũ quá thời gian cho phép.
6. Secret cũ được vô hiệu hóa sau khi xác nhận toàn bộ client đã chuyển, theo khả năng thực tế của directory.

Không đưa nội dung password, private key, giá trị cookie phiên, JNDI environment hoặc raw bind request vào nhật ký xác minh. Có thể lưu **fingerprint certificate**, issuer, thời gian, tên node và mã kết quả đã chuẩn hóa để kiểm toán.

## 4. Xoay server certificate khi CA vẫn giữ nguyên

Nếu certificate mới và cũ đều được xác minh bởi **cùng trust anchor** đã có trong JVM, quá trình renewal thông thường **không cần thêm CA vào truststore**. Tuy nhiên cần kiểm tra:

- Certificate mới có **Subject Alternative Name (SAN)** đúng tên DNS mà ứng dụng thực sự kết nối, ví dụ `ldap.example.org`.
- Chain do server gửi gồm các intermediate cần thiết; không giả định tất cả client tự tải intermediate.
- `notBefore`, `notAfter`, key usage, extended key usage và thuật toán được Java runtime/server hỗ trợ.
- Certificate và private key trên server khớp nhau; private key không bị in ra log, copy vào repository hoặc trao đổi bằng kênh không bảo mật.
- Load balancer và từng LDAP replica đã thay đủ; một node cũ có thể khiến lỗi xuất hiện ngẫu nhiên.

### Quy trình thay leaf certificate điển hình

1. Cấp certificate mới và xác minh SAN/chain/issuer theo chính sách PKI; triển khai lên **môi trường thử nghiệm**.
2. Kiểm tra một kết nối LDAPS hoặc StartTLS **mới** từ Java runtime cùng cấu hình trust production.
3. Chuẩn bị thay certificate cho từng LDAP endpoint/load balancer theo cách nền tảng hỗ trợ, giữ endpoint còn lại sẵn sàng khi chuyển từng node.
4. Chuyển một endpoint hoặc một nhóm nhỏ trước, kiểm tra handshake, bind và search; sau đó thay các node còn lại.
5. Đóng/evict các phiên cũ theo lịch đã kiểm soát để client tạo handshake mới. Tránh cắt hàng loạt connection cùng lúc gây tải đột biến.
6. Theo dõi lỗi và xác nhận node nào cũng gửi đúng chain; kết thúc sau khi mọi nhóm client đã xác minh.

**Rollback:** Nếu certificate cũ vẫn hợp lệ, được phê duyệt và private key chưa bị lộ, có thể phục hồi cấu hình server cũ theo runbook. Nếu certificate cũ đã hết hạn hoặc bị thu hồi vì lộ private key, **không rollback về nó**; thay bằng certificate an toàn khác. Nếu lỗi do thiếu intermediate hoặc sai SAN, sửa chain/certificate thay vì tắt hostname verification.

## 5. Xoay CA hoặc truststore: triển khai trust trước khi đổi server

Thay CA có rủi ro cao hơn renewal cùng CA vì các Java client có thể không tin cậy chain mới. Một phương pháp thông dụng là **trust overlap**:

```text
Giai đoạn A                   Giai đoạn B                   Giai đoạn C
LDAP server: old chain        LDAP server: new chain        LDAP server: new chain
JVM trust:   old + new        JVM trust:   old + new        JVM trust:   new
       │                           │                             │
       └─ Rollout trust ──────────>└─ Chuyển server ────────────>└─ Thu hồi old CA
```

**Trình tự:**

1. Nhận certificate CA mới qua kênh PKI tin cậy; so fingerprint out-of-band và kiểm tra đúng phạm vi tin cậy. Tránh import một leaf hoặc CA bất kỳ từ email không xác minh.
2. Tạo truststore chứa **CA cũ và CA mới** (nếu điều kiện an toàn cho phép), triển khai tới mọi JVM của ứng dụng. Đồng bộ cả cluster, job nền và các service phụ dùng LDAP.
3. **Buộc khách hàng nạp truststore mới** bằng cơ chế được phiên bản hỗ trợ, thường là rolling restart/recreate `ContextSource` và connection pool. Chỉ cập nhật file trên đĩa không chứng minh `TrustManager` đang dùng đã nạp lại.
4. Kiểm tra client với endpoint thử nghiệm trình bày chain mới, bao gồm hostname verification và LDAP bind. Nếu không thể thử endpoint mới trước, lập kế hoạch canary phù hợp.
5. Chuyển certificate chain của server theo từng endpoint, xác nhận các client cũ/mới đều kết nối.
6. Khi chắc chắn không còn server hay client cần old CA, loại CA cũ khỏi truststore, tiếp tục rolling rollout và kiểm tra fresh handshake.

Không giữ **cả CA cũ và CA mới vô thời hạn** chỉ để tiện vận hành; một CA cũ bị thu hồi hoặc mất tin cậy phải được loại bỏ theo yêu cầu bảo mật. Cũng không mở rộng truststore sang toàn bộ CA nội bộ không liên quan nếu chưa có lý do và phê duyệt.

### Ví dụ cấu hình Spring Boot với SSL bundle cho LDAPS

Với **phiên bản Spring Boot có hỗ trợ LDAP SSL bundle**, bạn có thể gắn một bundle tin cậy tới auto-configured `LdapContextSource`. Ví dụ PKCS12 truststore:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_READER_DN}
    password: ${LDAP_READER_PASSWORD}
    ssl:
      bundle: ldap-client
  ssl:
    bundle:
      jks:
        ldap-client:
          truststore:
            location: file:/run/secrets/ldap-truststore.p12
            password: ${LDAP_TRUSTSTORE_PASSWORD}
            type: PKCS12
```

Các placeholder ở trên có nghĩa là lấy bí mật từ cấu hình triển khai; **không ghi password thật** trong file YAML. `truststore` này dùng để **tin cậy server**; một client certificate cho mTLS là vật liệu **khác**, thường nằm trong `keystore` và phải được server chấp nhận.

**Giới hạn cần nhớ:**

- `spring.ldap.ssl.bundle` có trong các phiên bản Spring Boot mới; với phiên bản cũ phải dùng cách cấu hình truststore/`SSLSocketFactory` mà phiên bản đó hỗ trợ. Kiểm tra dependency trước khi sao chép thuộc tính.
- Thuộc tính này áp dụng với **LDAPS**; Spring Boot docs nói rõ không dùng bundle này để tự cấu hình **StartTLS**. Với StartTLS, thiết lập `DirContextAuthenticationStrategy` và socket factory/TLS context phù hợp.
- Nếu ứng dụng khai báo **`LdapContextSource` bean riêng**, cấu hình tự động từ `spring.ldap.ssl.bundle` không mặc nhiên áp vào bean đó.
- Spring Boot hỗ trợ reload SSL bundles ở một số consumer, nhưng hiện tài liệu chỉ nêu consumer như **Tomcat và Netty**. Đừng mặc định LDAP `ContextSource` hoặc các `DirContext` đã mở sẽ tự dùng truststore mới khi file thay đổi.

### Cách cấu hình JSSE ngoài ứng dụng

Ở dự án dùng JNDI/JSSE mặc định, JVM có thể nhận truststore được chỉ định **khi khởi động**:

```text
-Djavax.net.ssl.trustStore=/run/secrets/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Password mở truststore phải được cung cấp qua cơ chế bảo vệ của môi trường chạy; **không** đặt secret trên command line hoặc in `JAVA_TOOL_OPTIONS` chứa password ra log. Cần kiểm tra JVM thật sự sử dụng truststore mong muốn, vì thư viện có thể cung cấp `SSLContext` hoặc socket factory riêng.

**Cảnh báo nạp lại:** các system property này **không phải một API live reload**; `SSLContext`, `TrustManager` và connection đang tồn tại có thể giữ vật liệu đã nạp trước đó. Lựa chọn dễ kiểm thử là triển khai truststore mới và **rolling restart** instance ứng dụng, đóng/loại bỏ connection pool cũ theo cơ chế của hệ thống.

## 6. StartTLS và mTLS: hai trường hợp phải lập kế hoạch riêng

### 6.1. StartTLS khác LDAPS ở thời điểm nâng cấp kênh

Trong Spring LDAP, `DefaultTlsDirContextAuthenticationStrategy` thực hiện **StartTLS** rồi dùng SIMPLE bind với reader DN/password qua kênh đã bảo vệ. `ExternalTlsDirContextAuthenticationStrategy` cũng dùng StartTLS nhưng có thể xác thực qua **SASL EXTERNAL**, dựa vào client certificate đã cấu hình.

Ví dụ cấu hình StartTLS với simple bind (không dùng song song với URL `ldaps://`):

```java
package example.directory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapStartTlsConfig {
    @Bean
    LdapContextSource contextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldap://ldap.example.org:389");
        source.setBase("dc=example,dc=org");
        source.setUserDn(System.getenv("LDAP_READER_DN"));
        source.setPassword(System.getenv("LDAP_READER_PASSWORD"));

        DefaultTlsDirContextAuthenticationStrategy strategy =
            new DefaultTlsDirContextAuthenticationStrategy();
        source.setAuthenticationStrategy(strategy);

        // JNDI native pool không được dùng với StartTLS strategy.
        source.setPooled(false);
        source.setAnonymousReadOnly(false);
        return source;
    }
}
```

Đây là mẫu **định hướng cấu hình**: ứng dụng phải kiểm tra biến môi trường không null/rỗng, cấu hình SSL socket factory/trust phù hợp, xác minh hostname và certificate trong môi trường thực tế, có timeout, secret manager và xử lý lifecycle. `LdapContextSource` là bean do Spring quản lý; không tự gọi `afterPropertiesSet()` hai lần.

**Không phối hợp `DefaultTlsDirContextAuthenticationStrategy` với `ldaps://` chỉ vì “càng nhiều TLS càng an toàn”**: LDAPS đã thực hiện handshake TLS lúc mở kết nối; StartTLS là cơ chế nâng cấp trên kết nối LDAP thường. Chọn một kiểu theo server và cấu hình client.

### 6.2. Giữ xác minh hostname và chain

Cả LDAPS lẫn StartTLS đều phải xác minh certificate theo DNS name mà ứng dụng thực sự dùng. Không cài `HostnameVerifier` trả `true` vô điều kiện, `TrustManager` tin mọi certificate, hoặc các tùy chọn tắt xác minh endpoint để chữa lỗi xoay CA. Nếu IP/DNS alias không khớp SAN, hãy cấp certificate có SAN đúng hoặc điều chỉnh tên endpoint phù hợp.

`AbstractTlsDirContextAuthenticationStrategy` cho phép cấu hình `SSLSocketFactory` và `HostnameVerifier` khi có yêu cầu đặc biệt; mặc định dùng cơ chế xác minh hostname. Chỉ tùy chỉnh khi có cơ sở rõ ràng và đảm bảo kết quả **không làm giảm xác thực TLS**.

### 6.3. Khi dùng mutual TLS / SASL EXTERNAL

Nếu LDAP server yêu cầu **client certificate**, quy trình xoay vòng có hai chiều:

1. Client phải **tin** server certificate/CA mới.
2. Server phải **tin** client certificate/CA mới.
3. Client phải sở hữu **private key đúng** với certificate mới; keystore và file secret được phân quyền chặt.
4. Nếu dùng SASL EXTERNAL, mapping từ certificate subject/SAN sang LDAP authorization identity cần được server hỗ trợ và kiểm thử, không suy rằng TLS handshake thành công nghĩa là đã có quyền directory.

Thứ tự khuyến nghị: phân phối CA client mới tới LDAP server trước; nếu chính sách cho phép, server tạm chấp nhận **cả client certificate/issuer cũ và mới**; sau đó cập nhật keystore và restart/recreate kết nối client theo từng instance; cuối cùng thu hồi trust cũ. Nếu old private key đã bị lộ, cần xử lý như sự cố bảo mật, không duy trì overlap chỉ để tiện rollback.

Với `ExternalTlsDirContextAuthenticationStrategy`, việc luân phiên không chỉ thay một JKS/PEM trên đĩa; `SSLSocketFactory`, `KeyManager` và pooled `DirContext` có thể còn sử dụng client certificate trước đó. Cần kiểm tra bằng **handshake mới và authorization tương ứng**, không chỉ xem file mới tồn tại.

## 7. Connection pooling có thể giữ phiên TLS hoặc credential cũ

Spring LDAP và Java/JNDI có **hai cơ chế pooling khác nhau**. Cách luân phiên certificate/secret cần tính đến cả hai.

| Cơ chế | Đặc điểm | Rủi ro trong quá trình xoay |
| --- | --- | --- |
| Không pooling | Mỗi operation hoặc context mới có thể tạo kết nối mới | Handshake nhiều hơn; lỗi CA/secret mới xuất hiện ngay |
| **JNDI native pooling** | Pool cấp JVM, cấu hình qua `com.sun.jndi.ldap.connect.pool` và system properties | Phiên còn sống có thể che lỗi của handshake/bind mới; **không dùng với StartTLS** |
| **Spring LDAP `PoolingContextSource`** | Pool quản lý `DirContext` và hỗ trợ validation/eviction | Phải drain/evict/đóng pool khi thay trust, key material hoặc identity |
| Pool tùy biến của ứng dụng | Có thể tái sử dụng context/connection theo logic riêng | Phải chỉ rõ khi nào credentials được nạp và khi nào kết nối bị loại |

Tài liệu Spring LDAP yêu cầu **tắt JNDI native pooling khi dùng TLS authentication strategy (StartTLS)**; nếu cần pooling để tránh chi phí bắt tay TLS, dùng cơ chế Spring LDAP `PoolingContextSource` phù hợp. Tài liệu JNDI của Oracle cũng cảnh báo không pooling connection khi application thực hiện StartTLS hoặc đổi security identity trên một connection, vì provider không theo dõi đúng thay đổi trạng thái này.

**Cảnh báo khác:** `PoolingContextSource` không thích hợp khi bọc `LdapContextSource` sử dụng `AuthenticationSource` thay đổi danh tính theo từng user/thread; pool giả định context read-only và read-write có identity ổn định. Nó có thể tái sử dụng context đã bind theo user trước. Luồng **user bind authentication** cần cách quản lý connection được thiết kế riêng, không cho user này kế thừa phiên của user khác.

### Vì sao kiểm tra có thể cho kết quả sai?

```text
T0: Một DirContext được tạo, handshake với certificate CŨ,
    reader bind bằng SECRET_CŨ; context nằm trong pool.
T1: Server đổi certificate, secret manager cập nhật SECRET_MỚI.
T2: Ứng dụng chỉ mượn lại DirContext đang mở -> search vẫn thành công.
T3: Một instance khác mở connection mới -> handshake hoặc bind thất bại.
T4: Pool cũ hết hạn / ứng dụng restart -> lỗi mới xuất hiện đại trà.
```

**Bài học:** Ping/search qua một pooled context chưa chứng minh việc xoay thành công. Health check/kiểm thử cần tạo kết nối mới với trust material và credential dự kiến, hoặc thực hiện sau khi chắc chắn pool cũ đã đóng và JVM đã nạp cấu hình mới.

Khi triển khai:

- Xác định nơi tạo pool và **vòng đời destroy/close** đúng theo framework; không giả định đặt `maxIdle=0` là đủ đóng mọi connection đang hoạt động.
- Dừng cấp operation mới cho instance cần thay, đợi operation đang chạy kết thúc rồi drain/close pool theo chiến lược của ứng dụng.
- Triển khai lại cấu hình và process/`ContextSource`, cho instance mới tạo connection; kiểm tra handshake, bind và search.
- Với cluster, quay vòng từng instance để giới hạn tải tăng đột ngột lên LDAP server.
- Với mTLS hoặc SASL EXTERNAL, kiểm tra cả chain client/server và identity mới.

`testOnBorrow`/`testWhileIdle` giúp phát hiện context hỏng nhưng **không bảo đảm** pool tự áp dụng CA/secret mới. Ngay cả một context cũ vẫn đọc được directory, chính sách xoay vòng có thể yêu cầu nó phải được đóng vì đã bind bằng identity/credential sắp thu hồi.

## 8. Xoay password của LDAP service account

Mật khẩu `cn=directory-reader,ou=service-accounts,dc=example,dc=org` thường được Spring LDAP lấy khi cấu hình `ContextSource` khởi động. Nếu secret manager thay giá trị ở thời điểm chạy, **không tự suy luận** mọi bean và `DirContext` sẽ dùng password mới.

Mỗi lần xoay bind secret phải giải quyết ba câu hỏi:

1. Directory hiện chấp nhận credential nào, với DN nào?
2. Phiên Java nào đã nạp secret mới, phiên nào còn giữ giá trị cũ?
3. Pool có connection đã bind bằng credential cũ, và khi nào nó sẽ được đóng?

### 8.1. Phương án ưu tiên khi cho phép: tài khoản reader A/B

Thay vì đổi một password duy nhất khiến toàn bộ client phải cập nhật đồng thời, hệ thống có thể dùng **hai service account riêng** với ACL đọc tương đương, nếu chính sách danh tính cho phép:

```text
Giai đoạn 1
  App A/B/C -> reader-A + secret-A (đang hoạt động)
  LDAP      -> reader-A có quyền đọc, reader-B vừa được cấp

Giai đoạn 2
  Cấp secret-B từ secret manager
  Test reader-B: bind + search trên kết nối mới
  Rolling rollout ứng dụng:
    App A -> reader-B
    App B -> reader-B
    App C -> reader-B

Giai đoạn 3
  Xác nhận không còn kết nối/instance dùng reader-A
  Vô hiệu hóa reader-A và thu hồi secret-A
```

**Lợi ích:** Có giai đoạn hai danh tính hoạt động hợp lệ; các app instance có thể thay theo từng đợt, giảm nguy cơ mất truy cập đồng loạt. **Đổi lại:** Cần quản lý thêm identity/ACL, kiểm tra reader-B không được cấp quyền rộng hơn reader-A, và có quy trình vô hiệu hóa reader-A dứt điểm. Không tạo tài khoản thứ hai khi chính sách directory cấm.

### 8.2. Khi chỉ được dùng một DN và một password

Không phải LDAP server nào cũng cho phép **old password và new password** cùng đăng nhập trong khoảng chồng lấn. Không giả định có overlap. Một trình tự thực tế:

1. Đặt lịch có khả năng gián đoạn ngắn hoặc chuyển traffic sang hệ thống dự phòng đã chuẩn bị phù hợp.
2. Chuẩn bị **nguồn secret mới**, quyền truy cập, manifest/config cho client và phương án triển khai nhanh; chưa đổi trên directory nếu các client chưa sẵn sàng.
3. Theo quy trình đã được phê duyệt, đổi password trên directory và cập nhật secret manager, bảo đảm thứ tự/đồng bộ phù hợp nền tảng.
4. Khởi động lại hoặc refresh có kiểm soát các instance để `ContextSource` đọc secret mới; drain pool của các phiên đã bind.
5. Kiểm tra reader bind/search từ kết nối **mới** trên từng nhóm instance.
6. Xác nhận phiên cũ không còn được dùng; gỡ secret cũ khỏi cấu hình, artifact và nơi lưu không cần thiết.

Không áp dụng “dual password” nếu sản phẩm LDAP không hỗ trợ. Nếu password cũ bị lộ, cần **ưu tiên vô hiệu hóa credential cũ** theo quy trình sự cố, chấp nhận ngắt dịch vụ có kiểm soát nếu cần để giữ an toàn.

### 8.3. Secret manager, biến môi trường và dynamic credentials

Một số nơi phân phối secret:

| Cách cấp secret | Thay ở secret manager có tự cập nhật connection đang chạy? | Cách xác minh |
| --- | --- | --- |
| Environment variable lúc process start | **Không** tự đổi giá trị của process đã chạy | Restart/redeploy instance; kiểm tra bind mới |
| Mounted secret file | File có thể được cập nhật tùy orchestrator | Code có thực sự đọc lại file? SSL context/pool có được tạo lại? |
| Spring config property bind vào bean | Không tự động thay `ContextSource` đã khởi tạo | Kiểm tra cơ chế refresh bean thực tế và đóng pool cũ |
| Custom `AuthenticationSource` đọc từ vault mỗi lần tạo context | Có thể lấy giá trị mới cho **context mới**, nếu code thiết kế đúng | Test new context; kiểm tra caching, thất bại vault, consistency |
| Rotating credentials qua external provider | Phụ thuộc provider, directory, thời gian hiệu lực | Test cùng phiên bản và phương án fallback được phép |

Với `AuthenticationSource` động, Spring LDAP cho phép thay nguồn principal/password thay vì dùng giá trị cố định, nhưng **không** vì thế mà pool context mang danh tính cũ trở thành mới. Không ghép tùy tiện `AuthenticationSource` động với `PoolingContextSource` khi identity có thể thay đổi.

Trong **không trường hợp nào** nên log giá trị secret để xác nhận có thay đổi. Có thể ghi version/revision ID **không chứa secret** do secret manager cung cấp, hoặc mốc thời gian deployment, kết hợp bằng chứng bind thành công và đã ngắt phiên cũ.

## 9. Kiểm tra certificate và LDAP bind bằng công cụ

Các lệnh sau dành cho **môi trường thử nghiệm hoặc endpoint được phép quản trị**. Chúng chỉ minh họa thao tác kiểm chứng; không chứa secret thật, không bỏ TLS verification và không ghi password lên command line.

### 9.1. Kiểm tra file certificate trước triển khai

```bash
openssl x509 \
  -in /secure/staging/ldap-server-new.crt \
  -noout -subject -issuer -dates -fingerprint -sha256 \
  -ext subjectAltName
```

Kiểm tra fingerprint với dữ liệu PKI đã xác nhận qua kênh độc lập; kiểm tra SAN bao gồm **đúng DNS name client sẽ dùng**, thời hạn, issuer và yêu cầu thuật toán. Dòng lệnh chỉ xem certificate, **không** chứng minh server đã triển khai certificate mới, private key khớp hay chain đầy đủ.

### 9.2. Kiểm tra LDAPS bằng TLS handshake mới

```bash
openssl s_client \
  -connect ldap.example.org:636 \
  -servername ldap.example.org \
  -verify_hostname ldap.example.org \
  -verify_return_error \
  -showcerts \
  -CAfile /secure/trust/approved-ldap-ca-chain.pem \
  < /dev/null
```

- `-servername` dùng SNI nếu endpoint hỗ trợ; **SNI không phải hostname verification**. `-verify_hostname` mới thể hiện việc xác thực hostname theo tên mong đợi.
- `-CAfile` là trust material đã được phê duyệt. Không dùng `-verify_return_error` cùng một CA file lấy tùy tiện từ chính endpoint mà chưa xác minh nguồn.
- `-showcerts` giúp kiểm tra chain hiện tại; không chỉ dựa vào dòng “CONNECTED”.
- Với load balancer/replica, chạy kiểm tra từng backend được phép truy cập, vì DNS chung có thể chuyển bạn tới chỉ một node.

### 9.3. Kiểm tra StartTLS

Một số bản OpenSSL hỗ trợ `-starttls ldap`:

```bash
openssl s_client \
  -starttls ldap \
  -connect ldap.example.org:389 \
  -servername ldap.example.org \
  -verify_hostname ldap.example.org \
  -verify_return_error \
  -CAfile /secure/trust/approved-ldap-ca-chain.pem \
  < /dev/null
```

Kiểm tra cả việc **StartTLS được chấp nhận** và certificate hợp lệ. OpenSSL tại môi trường chạy có thể không cung cấp tùy chọn nâng cấp LDAP; khi đó sử dụng LDAP client chuyên dụng hỗ trợ StartTLS và xác minh certificate, **không** chuyển sang simple bind cleartext.

### 9.4. Kiểm tra bind/search qua LDAPS bằng `ldapsearch`

```bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=directory-reader,ou=service-accounts,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s base \
  "(objectClass=organizationalUnit)" ou
```

`-W` yêu cầu password **tương tác**, tránh `-w actual-password` vốn có thể lộ trên process arguments hoặc lịch sử shell. Công cụ `ldapsearch` dùng trust configuration **riêng** của OpenLDAP client; thành công ở đây **không chứng minh** JSSE/`TrustManager` trong JVM đã tải đúng truststore. Cần thêm kiểm tra từ chính ứng dụng Java sau khi tạo connection mới.

Với StartTLS, dùng `-ZZ` để **bắt buộc** nâng cấp trước khi bind:

```bash
ldapsearch -LLL -x -ZZ \
  -H ldap://ldap.example.org:389 \
  -D "cn=directory-reader,ou=service-accounts,dc=example,dc=org" \
  -W \
  -b "ou=people,dc=example,dc=org" \
  -s base \
  "(objectClass=organizationalUnit)" ou
```

Trong mỗi trường hợp, endpoint phải được cấu hình trust CA và kiểm tra hostname; ví dụ OpenLDAP client có thể dùng `TLS_CACERT` trong cấu hình được quản lý. Không đặt `TLS_REQCERT never` hay tùy chọn tương đương chỉ để vượt qua lỗi chain.

### 9.5. Kiểm tra truststore Java và dấu vân tay

```bash
keytool -list -v \
  -keystore /secure/runtime/ldap-truststore.p12 \
  -storetype PKCS12
```

`keytool` sẽ yêu cầu password mở store theo chế độ tương tác. Kiểm tra alias/fingerprint/chain trong **truststore dự định triển khai**, không hiển thị private key hoặc copy password vào shell. Một danh sách alias đúng chỉ chứng minh **file store chứa certificate**, chưa chứng minh JVM đang dùng file đó.

## 10. Smoke test trong Spring LDAP trên một instance mới

Với Spring LDAP, kiểm tra nên có hai tầng:

1. **Transport check:** Client tạo handshake TLS mới tới endpoint mong muốn, xác minh server chain và hostname.
2. **Directory operation check:** `ContextSource` dùng reader identity mới để thực hiện một LDAP operation có quyền rõ ràng, ví dụ đọc entry OU đã biết. Điều này chứng minh không chỉ TLS mà cả bind/ACL.

Ví dụ integration test dưới đây giả định directory test có entry `ou=people,dc=example,dc=org` và reader được đọc attribute `ou`. Chạy test trên **process/ContextSource mới** đã nạp truststore/secret dự kiến:

```java
package example.directory;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

@SpringBootTest
class LdapRotationSmokeTest {
    @Autowired
    private LdapTemplate ldap;

    @Test
    void freshClientCanBindAndReadExpectedOu() {
        LdapQuery query = LdapQueryBuilder.query()
            .base("ou=people")
            .searchScope(SearchScope.OBJECT)
            .countLimit(1)
            .timeLimit(2000)
            .attributes("ou")
            .where("objectClass").is("organizationalUnit");

        List<String> names = ldap.search(
            query,
            attributes -> attributes.get("ou").get().toString()
        );

        assertEquals(List.of("people"), names);
    }
}
```

Với `ContextSource` base `dc=example,dc=org`, `base("ou=people")` ở test là DN **tương đối**. `OBJECT` chỉ kiểm tra chính OU, tránh search toàn bộ người dùng; `countLimit` và `timeLimit` hạn chế rủi ro truy vấn nặng. Dùng một fixture phù hợp với ACL của directory cần kiểm tra. Nếu directory không cho phép đọc OU này, hãy chọn **entry sentinel được phê duyệt**, không nới ACL production chỉ để test.

**Quan trọng:** Nếu test chạy trong process có pool đang mở từ trước, `ldap.search(...)` có thể mượn context cũ và **không** kiểm chứng handshake mới. Khi cần bằng chứng rotation, khởi chạy một instance mới (hoặc đóng pool và xây lại trust/`ContextSource` theo cách được kiểm chứng), sau đó chạy cùng phép thử. Nếu có nhiều LDAP backend, phải kiểm tra từng endpoint/replica.

### Ví dụ cấu hình đơn giản để hiểu credential được nạp khi khởi động

```java
package example.directory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class PlainLdapsConfig {
    @Bean
    LdapContextSource ldapContextSource() {
        String readerDn = System.getenv("LDAP_READER_DN");
        String readerPassword = System.getenv("LDAP_READER_PASSWORD");
        if (readerDn == null || readerDn.isBlank()
                || readerPassword == null || readerPassword.isEmpty()) {
            throw new IllegalStateException("LDAP reader credentials missing");
        }

        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn(readerDn);
        source.setPassword(readerPassword);
        source.setAnonymousReadOnly(false);
        source.setPooled(false);
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
```

Mẫu này dùng **JSSE truststore mặc định hoặc cấu hình JVM phù hợp**; nó **không tự kế thừa `spring.ldap.ssl.bundle`** khi đã khai báo custom `LdapContextSource`. Trong hệ thống Spring Boot có auto-configuration và SSL bundle hoạt động, thường không cần khai báo hai bean trên. Hãy chọn **một** chiến lược cấu hình rõ ràng, tránh trộn làm thay đổi ý nghĩa của luân phiên truststore.

Đặc biệt, `System.getenv(...)` trong ví dụ được đọc khi bean khởi tạo. Cập nhật một secret bên ngoài process **không khiến biến cục bộ và các context có sẵn tự đổi**. Nếu muốn hot rotation, phải thiết kế riêng cơ chế tải lại secret, thay nguồn xác thực, tạo connection mới, drain pool và kiểm chứng không có giao dịch bị bỏ dở.

## 11. Runbook luân phiên an toàn theo từng giai đoạn

| Giai đoạn | Việc thực hiện | Cần có bằng chứng trước khi đi tiếp |
| --- | --- | --- |
| **Chuẩn bị** | Inventory endpoint/replica/Java app, phiên bản TLS/Java, truststore, secret store, pool | Danh sách owner, fingerprint, thời hạn, đường quay lui |
| **Preflight** | Kiểm tra chain/SAN, PKI source, reader permissions; thử trong staging | Fresh handshake + bind/search thành công |
| **Phân phối** | Trust CA mới hoặc reader-B đến các client; không đổi server ngay nếu đang chuyển CA | Từng nhóm client đã nạp vật liệu mới |
| **Canary** | Chuyển một endpoint hoặc một app instance, ép fresh connection | Chỉ số TLS và LDAP operations bình thường |
| **Rollout** | Thay từng nhóm còn lại; drain/close pool và rolling restart có kiểm soát | Mọi instance có thể bind/search theo chính sách mới |
| **Thu hồi** | Gỡ CA/identity/secret cũ khi hết overlap; thu hồi certificate bị lộ | Không còn client lệ thuộc vào vật liệu cũ |
| **Hậu kiểm** | Giám sát và ghi revision/fingerprint không nhạy cảm | Báo cáo kiểm thử và thời điểm hoàn tất |

### Chọn chiến lược rollback đúng với loại vật liệu

| Trường hợp | Rollback có thể làm gì? | Không được làm |
| --- | --- | --- |
| Renewal leaf certificate cùng CA, cert cũ còn hợp lệ/an toàn | Phục hồi certificate cũ trên endpoint theo quy trình | Dùng lại cert đã hết hạn hoặc private key bị lộ |
| Chuyển CA mới, trust overlap còn cả hai | Chuyển server về chain cũ **nếu được phép**, đồng bộ và kiểm thử | Tắt xác minh TLS hoặc xóa CA mới khi client chưa chuyển xong |
| mTLS client certificate mới, server tạm chấp nhận hai cert | Tạm chuyển client về key/cert cũ nếu vẫn còn an toàn | Cho phép key cũ đã bị lộ tiếp tục xác thực |
| Reader-A sang reader-B | Rollback app về reader-A **trước khi vô hiệu hóa reader-A**, nếu security policy cho phép | Khôi phục secret bị lộ hoặc tạo anonymous fallback |
| Đổi password cùng một DN, không có overlap | Dùng thao tác reset password được phê duyệt và triển khai đồng bộ | Giả định password cũ còn sử dụng được hoặc log password để kiểm tra |

**Quy trình dừng triển khai** cần rõ ràng: dừng khi có handshake fail, hostname mismatch, bind failure, search ACL ngoài mong đợi hoặc login error tăng vượt ngưỡng của dịch vụ. Không áp dụng “cứ rollout hết rồi sửa” khi đang chạm xác thực và danh tính.

### Một cách kiểm tra giám sát trong ca thay đổi

Theo dõi đồng thời:

- **TLS:** lỗi handshake, `PKIX path building failed`, chứng thư hết hạn, hostname mismatch và protocol/cipher negotiation failure.
- **LDAP bind:** `invalidCredentials`, `strongAuthRequired`, account lock, lỗi quyền read/search, timeout.
- **LDAP operations:** số lần thành công/thất bại, latency, referral lỗi và query timeout.
- **Pool:** số context đang mượn, số idle, thời gian đợi, validation failures, số lần tạo context mới.
- **Ứng dụng:** tỷ lệ login thành công, worker job truy cập directory, độ trễ endpoint phụ thuộc LDAP.

Ghi nhận mã lỗi chuẩn hóa, tên dịch vụ, phiên bản deployment, LDAP endpoint và fingerprint certificate **không có secret**. Tránh log JNDI environment (có thể chứa `java.naming.security.credentials`), password, client private key hoặc raw authentication request.

## 12. Ma trận chẩn đoán sau khi luân phiên

| Dấu hiệu | Nguyên nhân thường gặp | Bước xác minh đúng |
| --- | --- | --- |
| `SSLHandshakeException: PKIX path building failed` | JVM không tin CA/intermediate của chain mới, truststore sai | So chain/fingerprint, nguồn truststore trong JVM, kiểm tra trên process mới |
| `No subject alternative DNS name matching ...` | DNS kết nối không nằm trong SAN | Đối chiếu `ldaps://host` với SAN; cấp lại cert phù hợp |
| Certificate `not yet valid` hoặc expired | Thời gian hệ thống sai hoặc certificate ngoài hiệu lực | Kiểm tra thời gian UTC, `notBefore/notAfter` và clock sync |
| OpenSSL thành công nhưng Java thất bại | OpenSSL và Java dùng truststore/hostname policy khác nhau | Kiểm tra JSSE SSLContext, bundle, truststore và Java version |
| Java vừa đổi file truststore nhưng vẫn lỗi | `TrustManager`/`SSLContext` hoặc pool chưa nạp lại | Rolling restart/rebuild connection, test fresh handshake |
| LDAP bind lỗi `invalidCredentials` sau đổi secret | Secret mới chưa tới mọi instance, password trên directory khác hoặc reader account bị khóa | Test bind trên fresh context, đối chiếu secret revision không lộ giá trị |
| Search rỗng dù bind thành công | Sai ACL, base DN, scope hoặc reader-B khác quyền | Đọc entry sentinel, so ACL reader-A/B |
| Chỉ một số request lỗi | Cluster chưa đồng bộ, DNS đi nhiều backend, pool giữ kết nối cũ | Kiểm tra từng LDAP node và từng app instance |
| StartTLS lỗi khi bật pooling | JNDI native pool được dùng sai hoặc context security state bị tái sử dụng | Tắt native pooling, dùng cơ chế Spring LDAP phù hợp |
| Client certificate mới handshake được nhưng SASL EXTERNAL fail | Mapping certificate tới authorization identity chưa đúng | Kiểm tra trust server, cert identity, SASL EXTERNAL và ACL |
| Đổi secret rồi pool cũ vẫn đọc được | Context được bind trước lúc secret đổi còn tồn tại | Drain/close pool, thử connection mới; không coi đó là bằng chứng password mới đúng |
| Java app khởi động thất bại sau cấu hình bundle | Spring Boot không hỗ trợ thuộc tính/version hoặc custom `ContextSource` tự cấu hình khác | Kiểm tra phiên bản, bean thực tế và auto-configuration conditions |

Không xử lý mọi lỗi bằng cách “đổi sang `ldap://`” hoặc đặt `TrustManager` tin tất cả certificate. Làm như vậy có thể khiến mật khẩu người dùng và reader account bị lộ dù ứng dụng tạm thời truy cập được LDAP.

## 13. Bài thực hành

Ứng dụng có ba instance **App A, B, C** dùng `ContextSource` base `dc=example,dc=org`, đọc `ou=people` qua `ldaps://ldap.example.org:636`. Directory có hai LDAP replica sau load balancer, các ứng dụng có pool. Đội vận hành phải thực hiện hai thay đổi:

1. Chuyển server certificate từ **CA-Old** sang **CA-New**.
2. Thay reader service secret; hệ thống cho phép tạo thêm tài khoản `reader-B` có ACL giống `reader-A`.

**Nhiệm vụ:**

1. Đề xuất trình tự để các JVM tin CA-New **trước** khi hai LDAP server đổi chain. Chỉ ra chính xác khi nào cần rolling restart, khi nào phải kiểm tra fresh handshake.
2. Lập một quy trình đổi reader-A sang reader-B với ít nhất một giai đoạn chồng lấn; nêu thời điểm vô hiệu hóa reader-A.
3. Giải thích vì sao phép `ldapTemplate.search(...)` chạy thành công trên App A **không chứng minh** App A đã nạp CA-New hoặc reader-B.
4. Viết cách kiểm tra LDAPS certificate/hostname bằng `openssl s_client` với `-verify_hostname` và `-CAfile`; xác định vì sao `-showcerts` đơn độc chưa đủ.
5. Đề xuất smoke test Spring LDAP giới hạn một query trên `ou=people` bằng `SearchScope.OBJECT`, dùng `countLimit=1`, `timeLimit=2000`.
6. Xử lý tình huống App C báo `PKIX path building failed` sau khi một replica đổi chain, App B báo `invalidCredentials` sau khi đổi reader account. Không tắt TLS verification hoặc fallback anonymous.
7. Lập checklist log và giám sát, bảo đảm không chứa password reader, user password, private key, raw LDAP bind request.

**Gợi ý đáp án:**

- Triển khai truststore chứa **CA-Old + CA-New** tới App A/B/C; restart và kiểm tra từng app dùng trust mới, sau đó mới chuyển server chain theo từng replica; cuối cùng xóa trust cũ sau khi không còn dependency.
- Cấp reader-B với ACL tối thiểu tương đương, test bind/search trên connection mới, chuyển từng instance sang reader-B, đóng pool cũ, rồi **vô hiệu hóa reader-A** sau khi không còn instance lệ thuộc.
- Kết nối cũ có thể tiếp tục dùng phiên TLS/reader bind đã thiết lập từ trước. Cần fresh handshake và fresh bind để chứng minh vật liệu mới có hiệu lực.
- `PKIX` trên App C ưu tiên kiểm tra truststore/JSSE/chain và backend; `invalidCredentials` trên App B ưu tiên kiểm tra secret revision, DN reader-B, LDAP account status, pool và quy trình cấp phát secret.
- Nếu một CA/certificate/secret cũ **đã bị lộ** hoặc không còn tin cậy, không sử dụng lại để rollback; khôi phục bằng vật liệu thay thế an toàn theo quy trình ứng phó.

## 14. Tài liệu tham khảo

- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, LDAPS, `DefaultTlsDirContextAuthenticationStrategy`, `ExternalTlsDirContextAuthenticationStrategy` và cơ chế credentials.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): `PoolingContextSource`, validation, eviction và giới hạn khi dùng `AuthenticationSource` động.
- [Spring LDAP — AbstractTlsDirContextAuthenticationStrategy API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractTlsDirContextAuthenticationStrategy.html): socket factory, hostname verifier và TLS shutdown.
- [Spring Boot — Working with NoSQL Technologies / LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): `spring.ldap.ssl.bundle` áp dụng cho LDAPS và giới hạn với StartTLS/custom `ContextSource`.
- [Spring Boot — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): cấu hình JKS/PKCS12/PEM bundles, reload và các consumer được hỗ trợ.
- [Oracle JNDI — LDAP Connection Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/config.html): connection identity và điều kiện pooling.
- [Oracle JNDI — When Not to Use Pooling](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/pool.html): cảnh báo với StartTLS và thay đổi trạng thái bảo mật trên một connection.
- [Oracle — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLContext`, `TrustManager`, `KeyManager` và TLS verification.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): phân phối, quản lý vòng đời, luân phiên và thu hồi secret.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): LDAP bind và bảo vệ cơ chế xác thực.
