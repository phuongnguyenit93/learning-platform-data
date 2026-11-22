# Cấu hình JAAS, krb5.conf và đường dẫn thông tin bí mật khi tích hợp Kerberos

> **Module:** Spring Security – federation. **Nhóm:** Tích hợp Kerberos. **Trọng tâm:** cấu hình Kerberos V5 cho Java 17 và ứng dụng Spring Security dùng SPNEGO, xác định đúng vai trò **acceptor/initiator**, quản lý `krb5.conf`, **JAAS login configuration**, **keytab**, ticket cache và đường dẫn mount bí mật. Bài học dùng các miền/principals giả định `EXAMPLE.ORG` và `portal.example.org`, không dùng credential thật. Cấu hình ứng dụng phải được kiểm thử theo JDK, Spring Security Kerberos extension, KDC/Active Directory và nền tảng chạy thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích công việc riêng biệt của `krb5.conf` (tìm realm/KDC), **JAAS** (cách Java lấy/giữ Kerberos credentials) và **keytab/ticket cache** (dữ liệu xác thực nhạy cảm).
2. Phân biệt **principal phía nhận (acceptor)** cho dịch vụ HTTP/SPNEGO với **principal phía khởi tạo (initiator)** cho Java client gọi dịch vụ Kerberos khác.
3. Cấu hình `com.sun.security.auth.module.Krb5LoginModule` với `useKeyTab`, `keyTab`, `principal`, `storeKey`, `isInitiator`, `doNotPrompt`, `useTicketCache` và `ticketCache` đúng vai trò.
4. Xác định các Java system properties `java.security.krb5.conf`, `java.security.auth.login.config`, `javax.security.auth.useSubjectCredsOnly`; biết chúng khác các biến môi trường của MIT Kerberos.
5. Sắp xếp keytab vào **secret volume/read-only path**, bảo vệ file mode/UID/GID, cấm để credentials trong Git, Docker image, logs và user-controlled paths.
6. Giải thích luồng **HTTP 401 WWW-Authenticate: Negotiate** → Kerberos service ticket → `Authorization: Negotiate ...` → Java GSS/JAAS → Spring authentication → phân quyền ứng dụng.
7. Tạo file cấu hình `krb5.conf` và `jaas.conf` mẫu cùng lệnh chạy Java 17, phân biệt mã có thể chạy độc lập với mã yêu cầu KDC/keytab thật.
8. Tạo quy trình test **KDC, DNS, SPN, key version number (KVNO), encryption types, time skew, TLS**, kiểm tra không in secret và debug an toàn.
9. Biết xử lý multi-realm, reverse proxy, container/Kubernetes, restart/rotation keytab và permission failures.
10. Lập ma trận positive/negative QA trước khi đưa SPNEGO/Kerberos vào production.

**Kiến thức đầu vào:** HTTP, DNS và hostname/FQDN, Linux file permissions, Java 17, Spring Security `SecurityFilterChain`, Active Directory hoặc MIT Kerberos, nguyên tắc least privilege. Nếu mới học Kerberos, nên hiểu trước các thuật ngữ **KDC**, **AS/TGS**, **TGT**, **service ticket**, **realm** và **SPN**.

## 2. Bối cảnh: Portal Java xác thực bằng Kerberos/SPNEGO

Giả sử người dùng trong miền doanh nghiệp `EXAMPLE.ORG` truy cập:

~~~text
https://portal.example.org/private
~~~

Kerberos có các thực thể:

| Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Kerberos realm | `EXAMPLE.ORG` | Miền logic quản lý principal và keys |
| KDC/AD Domain Controller | `kdc1.example.org:88`, `kdc2.example.org:88` | Phát TGT và service tickets, kiểm principal |
| User principal | `lan@EXAMPLE.ORG` | Định danh người dùng đã được KDC xác thực |
| HTTP service principal/SPN | `HTTP/portal.example.org@EXAMPLE.ORG` | Danh tính server nhận Kerberos service ticket |
| Server Java/Spring | Portal trên VM hoặc Pod | Nhận SPNEGO token, giải/kiểm service ticket qua keytab |
| Keytab | `/run/secrets/kerberos/http-portal.keytab` | Chứa key dài hạn của service principal, **là secret** |
| JAAS config | `/etc/kerberos/jaas.conf` | Chọn login module và keytab/principal/path/flags |
| krb5.conf | `/etc/kerberos/krb5.conf` | Realm/KDC/domain mapping và Kerberos settings |
| Ticket cache | `/run/kerberos/ccache/svc-reader.ccache` | Có thể chứa TGT/credentials dùng bởi initiator, **là secret** |

Luồng browser SSO:

~~~text
User/browser                         KDC/AD                 Portal Java
    |                                  |                         |
    |-- truy cập HTTPS /private -------------------------------->|
    |<--------- 401 WWW-Authenticate: Negotiate ----------------|
    |                                  |                         |
    |-- lấy service ticket cho HTTP/portal.example.org -------->|
    |<--------- Kerberos ticket --------------------------------|
    |-- Authorization: Negotiate [SPNEGO token] ---------------->|
    |                                  |                   JAAS/JGSS
    |                                  |                 acceptor keytab
    |                                  |                   validate ticket
    |<-------------------- 200 /private (nếu authorized) --------|
~~~

Browser thường có TGT do người dùng đã đăng nhập domain. Server **không cần và không nên** sở hữu password/TGT của từng user chỉ để accept SPNEGO. Server cần **service key** cho đúng SPN, thông thường trong keytab. Kết quả Kerberos authentication cho phép ứng dụng biết principal; **role/tenant/resource permission vẫn do Spring Security và logic nghiệp vụ quyết định**.

### 2.1. Đừng nhầm Kerberos với các công nghệ khác

- Kerberos service ticket là chứng thực theo KDC và SPN, không phải SAML Assertion, OIDC ID Token hay OAuth Access Token.
- JAAS không phải KDC và không phát ticket; nó là API/configuration để Java authentication modules lấy hoặc nạp credentials vào `Subject`.
- `krb5.conf` không chứa private key của service; nó mô tả realm, KDC và chính sách tìm Kerberos infrastructure. Tuy nhiên file này vẫn có thông tin topology nội bộ, nên kiểm soát việc sửa/đọc theo policy.
- Keytab chứa **keys** dùng chứng minh danh tính service, có thể bị sao chép và lạm dụng. Đặt keytab lên filesystem có encryption at rest không làm nó tự an toàn khi ứng dụng hoặc host đã bị chiếm.
- Ticket cache chứa credentials có thời hạn; nó **không phải** metadata cấu hình và cần bảo vệ gần như keytab.

## 3. Ba lớp cấu hình phải khớp nhau

~~~text
Lớp 1 — Kerberos topology
  /etc/kerberos/krb5.conf
  -> default_realm, KDC, domain_realm

Lớp 2 — Java authentication behavior
  /etc/kerberos/jaas.conf
  -> Krb5LoginModule
  -> principal, keyTab, isInitiator, useTicketCache, storeKey

Lớp 3 — Secret material/runtime
  /run/secrets/kerberos/http-portal.keytab
  /run/secrets/kerberos/svc-reader.keytab
  /run/kerberos/ccache/svc-reader.ccache
  -> UID/GID, read/write permissions, secret manager, rotation

Java process (JDK 17):
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf
  Spring Security Kerberos acceptor / JGSS / LoginContext
~~~

**Vì sao không gộp chung?** Đổi KDC/realm routing thường không cần đổi service key; đổi principal hoặc keytab có thể đòi update AD/SPN và key version; đổi nơi mount file chỉ là thay đường dẫn/runtime configuration. Khi mọi thứ bị hardcode trong Java source, khó xoay key, audit và rollout.

### 3.1. Bảng phân biệt file

| File | Chứa | Có phải secret? | Ai cấp và cập nhật? | Quyền nên có |
| --- | --- | --- | --- | --- |
| `krb5.conf` | Realm/KDC/DNS mapping | Thường không phải credential, nhưng có thể nhạy về topology | Platform/Identity team | Admin-owned, app đọc, chỉ admin sửa |
| `jaas.conf` | Module/options/principal/keytab path | Thường không chứa secret **nếu không đặt password inline**, nhưng có thể lộ paths/IDs | App/Platform Security | App đọc, chỉ trusted deploy/admin sửa |
| `http-portal.keytab` | Keys của SPN HTTP | **Có, rất nhạy cảm** | Identity team / secret provisioning | Chỉ acceptor workload đọc, read-only |
| `svc-reader.keytab` | Key cho client/service principal | **Có** | Identity team / secret provisioning | Chỉ client workload cần thiết đọc |
| `svc-reader.ccache` | TGT/credentials (nếu dùng) | **Có** | Kerberos client/JAAS runtime | Chỉ đúng UID đọc/ghi, TTL/cleanup |
| JKS/PKCS12 TLS keystore | TLS private key/cert, khác Kerberos | **Có** nếu có private key | PKI/secret provisioning | Hạn chế theo server TLS policy |

**Chống nhầm lẫn:** Java `keyTab=...` là đường dẫn tới **binary keytab**, không phải đường dẫn `.crt`, `.pem`, TLS keystore hay `krb5.conf`. Java không thể kiểm SPNEGO service ticket chỉ vì được cấp TLS certificate.

## 4. Khai báo krb5.conf cho realm và KDC

Ví dụ file **`/etc/kerberos/krb5.conf`**:

~~~ini
[libdefaults]
    default_realm = EXAMPLE.ORG
    dns_lookup_realm = false
    dns_lookup_kdc = false
    forwardable = false

[realms]
    EXAMPLE.ORG = {
        kdc = kdc1.example.org:88
        kdc = kdc2.example.org:88
    }

[domain_realm]
    .example.org = EXAMPLE.ORG
    example.org = EXAMPLE.ORG
~~~

Đây là **MIT-style `krb5.conf`**. Java Kerberos runtime sử dụng tập cấu hình phù hợp; có khác biệt với MIT tools ở những keys ít phổ biến, vì vậy đừng giả định mọi directive MIT đều có cùng semantics trong JDK 17.

**Giải thích:**

- `[libdefaults] default_realm`: realm mặc định khi principal không ghi rõ realm. Trong ví dụ code/service hãy dùng **full principal có `@EXAMPLE.ORG`** để tránh ambiguity.
- `dns_lookup_realm=false`: không tự suy realm bằng DNS; dùng `[domain_realm]` có quản trị.
- `dns_lookup_kdc=false`: không tự tìm KDC bằng DNS SRV; `[realms]` khai báo KDC được phê duyệt. Trong một số tổ chức AD phụ thuộc DNS SRV discovery; hãy cấu hình theo chính sách thực, không bật/tắt mù.
- `kdc=...:88`: danh sách KDC có thể được dùng cho availability/failover. Cần kiểm network từ pod/VM tới TCP/UDP 88 theo policy, DNS của KDC, độ trễ và timeout.
- `[domain_realm]`: ánh xạ tên miền host tới realm Kerberos; không phải wildcard DNS certificate hoặc định nghĩa quyền truy cập.
- `forwardable=false` chỉ minh họa policy hạn chế delegation của TGT; nếu nghiệp vụ thật cần Kerberos delegation/constrained delegation, phải thiết kế policy riêng và kiểm KDC/AD settings. Không bật `forwardable=true` chỉ để “SPNEGO chạy được”.

**Không ép `default_tkt_enctypes` hoặc `default_tgs_enctypes` theo bộ thuật toán cũ** nếu chưa có yêu cầu KDC. Hạn chế DES/RC4 yếu và chọn encryption types được Java/KDC/AD policy hỗ trợ, ưu tiên AES theo cấu hình được tổ chức phê duyệt.

### 4.1. Các địa chỉ hay bị nhầm

~~~text
portal.example.org
    -> hostname PUBLIC browser truy cập
    -> HTTP/portal.example.org@EXAMPLE.ORG

kdc1.example.org
    -> hostname máy phát ticket (KDC)
    -> KHÔNG phải SPN của Portal

portal-pod-7.internal.cluster
    -> tên Pod/backend nội bộ
    -> KHÔNG tự thay HTTP/portal.example.org

/etc/kerberos/krb5.conf
    -> đường dẫn file mô tả KDC/realm, KHÔNG chứa service key
~~~

Nếu browser truy cập alias `alias.example.org`, ticket có thể được xin cho `HTTP/alias.example.org` (tùy hostname canonicalization/browser), còn keytab chỉ có `HTTP/portal.example.org`: xác minh có thể thất bại. Chọn **canonical public FQDN**, SPN và browser access đồng nhất; kiểm behavior DNS CNAME/canonicalization và reverse proxy trên môi trường thật. Không giải bằng cách chấp nhận arbitrary service principal với keytab toàn domain.

### 4.2. Multi-realm và trust

Đối với tổ chức có `EXAMPLE.ORG` và `PARTNER.ORG`:

- Mỗi principal có realm rõ, KDC và cross-realm trust phù hợp.
- `[domain_realm]` chỉ giúp chọn realm, không tự cấp trust.
- Keytab cho Portal cần key của SPN mà browser nhắm tới; không phải chứa keys của mọi realm nếu KDC trust cross-realm đã thiết kế.
- Kiểm referrals, clock/time synchronization, encryption types và routing giữa realms bằng integration tests.
- Không tự chọn realm từ query/header của user hoặc tạo keytab path từ tên tenant do client gửi.

## 5. File JAAS: chỗ Java chọn Krb5LoginModule

JAAS login configuration (khác `krb5.conf`) định nghĩa các **entry names** và chuỗi modules/options. Java `LoginContext("KrbAcceptor")` tìm đúng entry tên `KrbAcceptor`. Java GSS/HTTP SPNEGO có thể dùng các default entry names riêng như `com.sun.security.jgss.krb5.initiate`; vì vậy entry name phải **khớp với client/framework gọi**, không tự suy từ tên file.

### 5.1. Acceptor: Portal nhận SPNEGO token

**`/etc/kerberos/jaas.conf`**, entry cho server:

~~~text
KrbAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http-portal.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    isInitiator=false
    doNotPrompt=true
    useTicketCache=false
    debug=false;
};
~~~

**Các lựa chọn quan trọng:**

| JAAS option | Acceptor value | Ý nghĩa |
| --- | --- | --- |
| `useKeyTab=true` | Bật | Nạp key từ file keytab thay vì hỏi password |
| `keyTab="/run/secrets/.../http-portal.keytab"` | Tuyệt đối, chỉ mount được phép | Không phụ thuộc working directory/current user home |
| `principal="HTTP/portal.example.org@EXAMPLE.ORG"` | Full service principal | Khớp SPN mà browser xin ticket từ KDC |
| `storeKey=true` | Bật | Đưa key/keytab handle vào private credentials của JAAS `Subject`, để acceptor có thể dùng |
| `isInitiator=false` | Quan trọng | Acceptor-only: không bắt buộc lấy TGT qua AS exchange khi login |
| `doNotPrompt=true` | Bật | Fail-closed nếu keytab/principal không dùng được, không mở prompt interactive |
| `useTicketCache=false` | Bật rõ | Server acceptor không cần user TGT cache chỉ để accept HTTP ticket |
| `debug=false` | Production | Tránh log Kerberos/JGSS/JAAS internals |

**Không mặc định dùng `principal="*"`**: JDK 17 hỗ trợ wildcard principal ở acceptor với `isInitiator=false`, nhưng như vậy có thể nhận ticket cho bất kỳ principal có key trong keytab. Nếu ứng dụng chỉ có một SPN, dùng principal cố định. Khi có nhiều SPNs phải làm rõ trust policy, identity/multitenancy và contents của keytab.

### 5.2. Acceptor entry cho JGSS default login name

Một số Java GSS clients/acceptors dùng standard JAAS entry name:

~~~text
com.sun.security.jgss.krb5.accept {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http-portal.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    isInitiator=false
    doNotPrompt=true
    debug=false;
};
~~~

Khi dùng Spring Security Kerberos `SunJaasKerberosTicketValidator` với `setServicePrincipal(...)` và `setKeyTabLocation(...)`, implementation có thể tự dựng JAAS/GSS login config nội bộ. **Không được khẳng định** chỉ cần đặt entry `KrbAcceptor` là Spring sẽ đọc entry đó; cần kiểm library implementation và phiên bản. Cả hai cấu hình (app-managed JAAS và validator-managed keytab) phải thống nhất **principal, path và realm**, tránh nạp hai identity khác nhau.

### 5.3. Initiator: Java service gọi backend thay mặt **service identity**

Một service khác cần dùng Kerberos để **khởi tạo** request đến backend `HTTP/reports.example.org@EXAMPLE.ORG`, dùng principal riêng `svc-reader@EXAMPLE.ORG` và keytab riêng:

~~~text
KrbInitiator {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/svc-reader.keytab"
    principal="svc-reader@EXAMPLE.ORG"
    storeKey=false
    isInitiator=true
    doNotPrompt=true
    useTicketCache=false
    debug=false;
};
~~~

Với `isInitiator=true`, JAAS có thể cần **liên hệ KDC lấy TGT** khi login nếu không có ticket cache dùng được. Keytab trong ví dụ chứa key của **svc-reader**; không phải key HTTP Portal. Đây là **service-to-service authentication dưới danh tính svc-reader**, **không tự động là Kerberos delegation thay user Lan**. Nếu muốn constrained delegation/S4U, phải thiết kế AD/KDC policy, support của Java/GSS và downstream authorization riêng.

**Tránh một entry dùng chung cho acceptor và initiator** chỉ để giảm số dòng. Acceptor cần `storeKey=true` và `isInitiator=false`; initiator cần lấy credentials với `isInitiator=true`. Hai keytabs có quyền và blast radius khác nhau.

### 5.4. Initiator dùng ticket cache thay vì keytab

Nếu Java client chạy trong session đã có TGT và cần lấy từ cache theo cấu hình:

~~~text
KrbCachedClient {
    com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true
    ticketCache="/run/kerberos/ccache/svc-reader.ccache"
    useKeyTab=false
    storeKey=false
    isInitiator=true
    doNotPrompt=true
    debug=false;
};
~~~

Các tổ hợp phải hợp lệ theo JDK:
- `ticketCache` **chỉ hợp lệ khi `useTicketCache=true`**.
- `renewTGT=true` cũng yêu cầu `useTicketCache=true`; không bật nếu không hiểu chính sách renewable TGT và provider.
- `doNotPrompt=true` mà **không có** `useTicketCache`/`useKeyTab`/credential nguồn hợp lệ có thể cấu hình sai và thất bại.
- `keyTab=...` có hiệu lực khi `useKeyTab=true`; chỉ ghi path không bật option sẽ không hoạt động.
- Nếu cả cache và keytab cùng bật, `Krb5LoginModule` có thứ tự lấy credential (cache trước keytab); cần xác định rõ fallback và policy để tránh dùng credential không kỳ vọng.

**Ticket cache có TGT**: bảo vệ file, TTL, owner và cleanup; không đặt cache của nhiều users chung một đường dẫn hoặc world-readable.

## 6. Java system properties khác biến môi trường MIT Kerberos

Khởi chạy JVM khi dùng config/JAAS riêng:

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  -Djavax.security.auth.useSubjectCredsOnly=true \
  -cp app.jar \
  demo.KerberosAcceptorProbe
~~~

**Chú ý:** Lệnh trên chỉ minh họa cách đặt properties cho một class Java; nếu chạy Spring Boot executable JAR, dùng `java ... -jar app.jar`, không thêm `-cp app.jar demo.Class`. Trong section thử nghiệm cuối có lệnh riêng cho `KerberosAcceptorProbe` khi có keytab thật.

| Cấu hình | Bên sử dụng | Ý nghĩa | Có thay nhau được? |
| --- | --- | --- | --- |
| `-Djava.security.krb5.conf=/path/krb5.conf` | **JDK Kerberos** | Chỉ file cấu hình realm/KDC MIT-style | **Không** phải JAAS file |
| `-Djava.security.auth.login.config=/path/jaas.conf` | **JAAS** | Chỉ entry/login module/options | **Không** phải keytab path |
| `-Djavax.security.auth.useSubjectCredsOnly=true` | **JDK GSS-API** | Hạn chế lấy GSS credential từ JAAS `Subject` (theo standard model) | Không tự thực hiện login |
| `-Dsun.security.krb5.debug=true` | Java Kerberos debug | Trace Kerberos/KDC detail để xử lý sự cố | Không bật production lâu dài |
| `KRB5_CONFIG` | Thư viện/tooling **MIT Kerberos** | Chỉ file krb5.conf của MIT library | Không được mặc định thay Java property |
| `KRB5_KTNAME` | MIT Kerberos/keytab-aware tools | Default keytab location theo MIT | Không nên giả định override `keyTab` của Java JAAS |
| `KRB5CCNAME` | MIT Kerberos client tools | Default ticket cache (ví dụ `FILE:/run/...`) | Java JAAS có `ticketCache` riêng |
| `-Djava.security.krb5.realm` và `.kdc` | JDK Kerberos | Có thể định nghĩa realm/KDC trực tiếp; phải dùng cùng nhau khi chọn kiểu này | Không cần nếu dùng krb5.conf đúng |

**Phân biệt quan trọng:** Thử `kinit`/`klist` từ shell thành công chỉ xác minh **MIT Kerberos tools** và filesystem/network của môi trường đó. Nó **không bảo đảm** Java process đang đọc cùng krb5.conf, cùng ticket cache, dùng cùng service principal hoặc có cùng quyền file. Dùng Java system properties/JAAS explicit để giảm mơ hồ.

### 6.1. useSubjectCredsOnly phải chọn có chủ đích

JDK GSS-API thường dùng JAAS `Subject` chứa credentials. Khi `javax.security.auth.useSubjectCredsOnly=true`, ứng dụng nên login bằng `LoginContext`/framework JAAS và làm GSS operation trong subject phù hợp. Khi đặt `false`, JGSS có thể tìm credentials **ngoài Subject** (ví dụ default ticket cache). Điều này hữu ích ở một số HTTP/SPNEGO client integrations, nhưng có thể mở ra credential source không dự kiến.

**Không dùng `-Djavax.security.auth.useSubjectCredsOnly=false` làm “câu thần chú sửa Kerberos” cho mọi service**. Trước hết xác định ứng dụng đang chạy acceptor hay initiator, ai quản lý Subject, có keytab/ticket cache nào, liệu framework nội bộ đã tạo login context hay chưa. Oracle Java 17 HTTP/SPNEGO guide có ví dụ `false` cho client sử dụng OS ticket cache, không đồng nghĩa đây là mặc định bảo mật phù hợp với server dùng keytab riêng.

### 6.2. JAAS config single versus double equal sign

JAAS Reference Guide phân biệt:
- `-Djava.security.auth.login.config=/etc/kerberos/jaas.conf`: chỉ định URL/path và có thể được kết hợp với nguồn cấu hình `java.security` theo cách provider mặc định xử lý.
- Dùng `==` trong assignment (ví dụ `-Djava.security.auth.login.config==/path`) có ý nghĩa **override** tập JAAS configuration URLs thay vì cộng thêm.

Với ứng dụng triển khai mới, hãy quản lý config sources rõ ràng; đừng thay cú pháp ngẫu nhiên mà không biết môi trường có cấu hình JAAS khác từ JVM security properties hay không. Tránh sửa trực tiếp file `$JAVA_HOME/conf/security/java.security` trên mọi node chỉ để thay một app.

## 7. Đường dẫn secret: không được đưa keytab vào nguồn mã

**Đề xuất layout Linux/container:**

~~~text
/etc/kerberos/
    krb5.conf                 # non-secret topology config, admin-owned
    jaas.conf                 # config, contains ABSOLUTE keytab paths

/run/secrets/kerberos/
    http-portal.keytab        # secret SPNEGO ACCEPTOR
    svc-reader.keytab         # secret CLIENT INITIATOR, nếu cần

/run/kerberos/ccache/
    svc-reader.ccache         # short-lived ticket cache, nếu dùng
~~~

Không đặt keytab trong:
- `src/main/resources`, `classpath`, JAR/WAR, Docker build context hoặc container image layers;
- Repository Git (kể cả “private repo”), Git history, CI build artifacts;
- `application.yml` dưới dạng base64, Kubernetes ConfigMap, literal Helm values hoặc inline secrets;
- stdout/stderr, exception message, debug logs, APM traces, request headers, ticket/chat, wiki và email;
- Public shared volume hoặc `/tmp` không có permission/cleanup đúng;
- Path do user tự chọn từ HTTP query/form/header.

### 7.1. Least privilege trên Linux

Trong máy test/VM có filesystem bình thường, khi secret provisioner đã tạo keytab:

~~~bash
# Ví dụ admin thao tác trong môi trường đã được phê duyệt.
sudo chown kerberos-app:kerberos-app \
    /run/secrets/kerberos/http-portal.keytab
sudo chmod 0400 \
    /run/secrets/kerberos/http-portal.keytab

# Chỉ xem metadata file, KHÔNG xem bytes:
stat -L -c '%a %U %G %n' \
    /run/secrets/kerberos/http-portal.keytab

# Kiểm với đúng UID/GID của JVM:
sudo -u kerberos-app sh -c \
    'test -r /run/secrets/kerberos/http-portal.keytab && echo READABLE || echo DENIED'
~~~

**Lưu ý:** `0400` chỉ owner đọc; với projected secret volume thường owner là root và app UID khác, `0400` có thể gây lỗi. Nếu dùng group-mounted secret, cân nhắc `0440` + đúng GID trong pod, không mở `0644`/`0777`. Quyền traversal/write của parent directories quan trọng; một file secret không nên bị thay bằng symlink từ thư mục attacker có quyền sửa.

**Phân tách quyền:**
- Portal acceptor chỉ cần **http-portal.keytab**.
- Java backend caller chỉ cần **svc-reader.keytab** hoặc cache của chính nó.
- CI build/test không cần production keytabs; unit tests dùng fake/mock path.
- Chỉ Identity/Security custodians mới được tạo/rotate/revoke service principal keys.
- SRE break-glass phải có approval, MFA, TTL, audit; không cấp access vĩnh viễn cho mọi tenant/env.
- Không chia keytab production cho staging, dev hoặc người dùng cá nhân.

### 7.2. Trạng thái keytab và nội dung file

Một keytab là file **binary**, có thể chứa một hoặc nhiều entries cho principal/enctype/KVNO. Nó là credential có thể bị đánh cắp dù không chứa password plaintext. Không dùng `cat`, `base64`, `xxd` hoặc `strings` để “debug” keytab rồi gửi kết quả lên chat.

Dùng công cụ MIT trong môi trường được phép để **liệt kê metadata**:

~~~bash
klist -k -e /run/secrets/kerberos/http-portal.keytab
~~~

`klist -k -e` thường in principal, KVNO và encryption type, **không in raw key material**, nhưng danh sách principal cũng có thể nhạy về topology và không nên đưa vào log rộng quyền. Không dùng tùy chọn hiển thị key bytes nếu tool/version hỗ trợ.

Kiểm:
- Principal chính xác: `HTTP/portal.example.org@EXAMPLE.ORG`.
- KVNO đúng với KDC/AD hiện tại.
- Enctypes tương thích với KDC, ticket và JDK cryptographic policy.
- Secret version mới có được phân phối đồng đều các nodes không.
- File có UID/GID/mode và đúng binary format, không phải base64 string/text vô tình mount sai.

### 7.3. Ticket cache

Nếu initiator lấy TGT qua cache:
- Đặt ở private runtime directory có owner app, mode `0600` cho file khi có thể.
- Xác định rõ `ticketCache=...` trong JAAS nếu muốn JDK Java đọc đúng file.
- Với MIT tools, có thể dùng `KRB5CCNAME=FILE:/run/kerberos/ccache/svc-reader.ccache`, nhưng đừng mặc nhiên rằng Java JAAS sử dụng chính biến môi trường này.
- Khi chủ động thử `kinit`, bảo đảm credential/TGT không bị đặt ở một cache world-readable hoặc chia sẻ giữa app/tenant.
- Định nghĩa ticket renewal/expiration, logout/cleanup và xử lý process crash/restart. Một TGT hết hạn không được chữa bằng cách tắt validation thời hạn.

## 8. Container và Kubernetes: mount keytab, đừng đóng gói

Với Kubernetes, secret có thể được cấp qua Kubernetes Secret volume hoặc CSI integration với external secret manager. **Kubernetes Secret base64 là encoding, không phải encryption**, nên phải bật **encryption at rest** cho etcd và dùng RBAC/admission/network policy; với CSI cần kiểm cơ chế sync sang Secret, rotation, ownership/permissions và đường truy cập của privileged pods.

### 8.1. Pod template minh họa (không phải Deployment hoàn chỉnh)

~~~yaml
spec:
  serviceAccountName: kerberos-portal
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: portal
      image: registry.example.org/portal:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
      env:
        - name: JAVA_TOOL_OPTIONS
          value: >-
            -Djava.security.krb5.conf=/etc/kerberos/krb5.conf
            -Djava.security.auth.login.config=/etc/kerberos/jaas.conf
      volumeMounts:
        - name: kerberos-keytab
          mountPath: /run/secrets/kerberos
          readOnly: true
        - name: kerberos-config
          mountPath: /etc/kerberos
          readOnly: true
  volumes:
    - name: kerberos-keytab
      secret:
        secretName: portal-kerberos-keytab
        defaultMode: 0440
    - name: kerberos-config
      configMap:
        name: portal-kerberos-config
        defaultMode: 0444
~~~

**Giải thích:** Tên Secret/ConfigMap là **tham chiếu**, không chứa keytab bytes trong YAML này. `portal-kerberos-keytab` phải được secret provisioner tạo theo kênh kiểm soát; `portal-kerberos-config` chứa `krb5.conf` và `jaas.conf` đã được duyệt. `fsGroup` có thể giúp UID 10001 truy cập group-readable volume nếu volume provider hỗ trợ; CSI drivers khác nhau có thể không áp ownership như mong đợi. Kiểm `stat -L` và `test -r` **trong Pod chạy cùng UID/GID**, không sửa thành world-readable.

**Điểm cần điều chỉnh:**
- Khi app cần gọi Kubernetes API hoặc CSI workload identity, `automountServiceAccountToken: false` có thể không phù hợp; dùng token projection/Audience/TTL và quyền nhỏ nhất. Đừng tắt/bật theo mẫu mà không xem provider.
- `readOnlyRootFilesystem=true` có thể yêu cầu tách `/tmp`, JVM caches, ticket cache và logs sang writable volume được giới hạn. Acceptor chỉ dùng keytab thường không cần writable ticket cache, nhưng Java runtime vẫn có nhu cầu file tạm tùy ứng dụng.
- Mỗi node/pod phải có đúng version keytab và public DNS/hostname mapping; load balancer hostname là SPN public, **không tự chọn SPN theo tên Pod**.
- Helm ConfigMap, Java options và resource names phải được kiểm quyền chỉnh sửa; người thay JAAS/krb5.conf có thể khiến process đọc keytab khác hoặc tin KDC khác.
- Một privileged pod hoặc node root có thể đọc mounted keytab dù app đang chạy non-root. File mode giúp hạn chế nhưng không thay cluster security, host isolation và RBAC.

### 8.2. Vì sao không mount keytab bằng environment variable?

Một binary keytab không phải chuỗi environment variable tự nhiên. Đưa base64 keytab vào env rồi decode tại startup tạo thêm đường leak (shell history, command-line args, process environment, crash diagnostics, log, tmp files). **Ưu tiên secret volume/read-only file** hoặc một provider Kerberos đã được hỗ trợ và kiểm toán. JAAS `keyTab=...` dùng đường dẫn file cụ thể.

### 8.3. Dynamic secret rotation có tự reload không?

**Không mặc định.** Khi Secret/CSI cập nhật file mount, một Spring Kerberos validator/JAAS Subject/GSS credential đã khởi tạo có thể còn giữ keytab handle/keys/cached state. Java có `refreshKrb5Config=true` để làm mới **Kerberos config trước JAAS login**, nhưng **không chứng minh** toàn bộ keytab, Subject hoặc Spring authentication provider tự reload đúng.

Lập kế hoạch rolling restart hoặc controlled credential refresh theo khả năng thư viện, với overlapping keys/KVNO khi Identity/KDC policy cho phép. Kiểm dùng SPNEGO ticket thật **trước và sau** rotation.

## 9. SPN, realm, DNS và reverse proxy phải đồng nhất

Khi browser truy cập URL public `https://portal.example.org`, client thường yêu cầu service ticket cho `HTTP/portal.example.org@EXAMPLE.ORG`. Kerberos keytab phía Java server phải chứa đúng key của SPN này.

**Ví dụ lỗi:**

~~~text
Browser URL = https://portal.example.org
Expected SPN = HTTP/portal.example.org@EXAMPLE.ORG
Keytab actually contains = HTTP/node-1.internal@EXAMPLE.ORG

Result: acceptor cannot decrypt/validate ticket for requested SPN.
~~~

Nếu dùng load balancer:
- Mỗi node có thể chia cùng keytab của logical service SPN qua secret provisioning (với quản trị cẩn thận), hoặc cơ chế tập trung phù hợp.
- Không đăng ký một HTTP SPN với nhiều account tùy tiện trong AD, gây duplicate/ambiguous SPN và key mismatches.
- TLS termination ở LB không làm Kerberos service ticket tự động hợp lệ; SPNEGO server vẫn cần principal/key đúng.
- Nếu proxy thay `Host`/redirect scheme, kiểm hostname principal. Kerberos authentication không bảo vệ một arbitrary forwarded-user header từ proxy bị cấu hình sai.
- Nếu reverse proxy tự làm Kerberos acceptor rồi gửi identity tới app, đó là **kiến trúc ủy quyền trust qua proxy riêng**. Backend phải xác thực kênh/mTLS, strip forged headers và policy rõ, không mặc định cả proxy và app đều là acceptor.

### 9.1. HTTP 401 Negotiate khác Basic

Một SPNEGO login thông thường:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Browser sau khi có ticket gửi:

~~~http
GET /private HTTP/1.1
Host: portal.example.org
Authorization: Negotiate <opaque-token>
~~~

`<opaque-token>` là dữ liệu minh họa, không phải token thật. **Không log giá trị Authorization header**. Sau khi Java/Spring xác minh token và tải user authorities, ứng dụng có thể trả `200` hoặc `403` tùy authorization. Một SPNEGO token valid không có nghĩa user có `ROLE_ADMIN`.

### 9.2. Kiểm principal nhận được sau authentication

Kerberos `lan@EXAMPLE.ORG` là một authenticated principal. Ứng dụng cần kiểm:
- User còn active/không bị khóa trong account directory nội bộ?
- Principal có thuộc expected realm/tenant không? Cross-realm trust có cần mapping riêng?
- User có quyền xem resource không? Object-level/row-level ownership và nhóm/role mapping đã được duyệt?
- Application session có timeout/reauthentication phù hợp không?
- Logout tại app có phải chỉ xóa local session không? Browser vẫn có TGT domain nên **có thể SSO lại ngay**.

Không tin principal do frontend tự gửi hoặc lấy từ unauthenticated HTTP header.

## 10. Spring Security Kerberos: tích hợp với JAAS/keytab đúng vai trò

Spring Security **Kerberos** là một extension/integration có những thành phần như:

- `SpnegoAuthenticationProcessingFilter`: đọc `Authorization: Negotiate ...` và tạo authentication request.
- `SpnegoEntryPoint`: khi chưa authenticated, kích hoạt SPNEGO negotiation (`WWW-Authenticate: Negotiate`), có thể hỗ trợ fallback trang login theo cấu hình.
- `KerberosServiceAuthenticationProvider`: xác minh service ticket/SPNEGO token bằng `KerberosTicketValidator`, rồi nạp user/authorities bằng `UserDetailsService`.
- `SunJaasKerberosTicketValidator`: triển khai JDK/JAAS-based validator, cần **servicePrincipal** và **keyTabLocation**.
- `AuthenticationManager`/`SecurityFilterChain`: ghép các providers/filters và quyết định authorization.
- `KerberosAuthenticationProvider`/`SunJaasKerberosClient`: một nhánh khác dành cho client Kerberos authentication, không thay thế service-ticket acceptor.

**Cảnh báo tương thích:** Không tồn tại một property Spring Boot core đơn giản tên `spring.security.kerberos.enable=true` làm đầy đủ Kerberos/SPNEGO. Phải thêm module/library **Spring Security Kerberos** version tương thích với Spring Security/Spring Boot và cấu hình beans, KDC/AD, keytab. Đừng tự suy từ Spring Security 6.5 rằng mọi APIs của Spring Security Kerberos 2.x sẽ biên dịch chính xác nếu chưa kiểm dependency tree.

### 10.1. Bean cấu hình keytab/service principal (minh họa)

Đây là **Spring configuration fragment**, không phải ứng dụng hoàn chỉnh: cần dependency `spring-security-kerberos` tương thích, `UserDetailsService`, `AuthenticationManager`, `SecurityFilterChain`, SPNEGO filter/entry point và authorization hoàn chỉnh.

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class KerberosBeans {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator(
            @Value("${app.kerberos.service-principal}") String principal,
            @Value("${app.kerberos.keytab-location}") String keytabPath) {

        SunJaasKerberosTicketValidator v =
                new SunJaasKerberosTicketValidator();
        v.setServicePrincipal(principal);
        v.setKeyTabLocation(new FileSystemResource(keytabPath));
        v.setDebug(false);
        return v;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        KerberosServiceAuthenticationProvider p =
                new KerberosServiceAuthenticationProvider();
        p.setTicketValidator(validator);
        p.setUserDetailsService(users);
        return p;
    }
}
~~~

Trong `application.yml` **chỉ đặt principal/path, KHÔNG đặt nội dung keytab**:

~~~yaml
app:
  kerberos:
    service-principal: HTTP/portal.example.org@EXAMPLE.ORG
    keytab-location: /run/secrets/kerberos/http-portal.keytab
~~~

**Giải thích:** `FileSystemResource` trỏ tới binary keytab đã provision; validator xác minh ticket do browser gửi. `UserDetailsService` phải lấy authorities từ nguồn nội bộ/AD mapping được phê duyệt; ví dụ không cấp `ROLE_ADMIN` cho mọi Kerberos principal. Bean không tự đăng ký SPNEGO filter hoặc entry point, nên **không copy riêng hai beans rồi tuyên bố ứng dụng đã có SSO**.

### 10.2. Mối quan hệ giữa JAAS file và Spring validator

Có hai mô hình tích hợp:

1. **Application-managed JAAS Subject:** code/framework dùng `LoginContext("KrbAcceptor")` hoặc entry JGSS phù hợp, nạp credentials, rồi thực hiện GSS accept operation trong `Subject`.
2. **Validator-managed JAAS:** `SunJaasKerberosTicketValidator` nhận servicePrincipal và keytabLocation, thực hiện login/validation theo implementation của Spring Kerberos library.

**Không tự động kết luận** Spring validator luôn đọc `KrbAcceptor` từ `-Djava.security.auth.login.config`. Nếu dùng mô hình 2, chính bean validator khai báo principal/keytab. Giữ `krb5.conf` đúng và test toàn flow với một SPNEGO token thật.

### 10.3. Ngăn “fallback bypass” authentication

Nếu app cung cấp form login/Basic/OIDC bên cạnh SPNEGO, phải thiết kế filter-chain và route policies:
- Chỉ định endpoints nào cho SPNEGO, endpoint nào cho fallback.
- Không để một filter chain `permitAll` vô tình mở `/private`.
- Không coi `Authorization: Negotiate` chỉ là Base64 user name; phải qua ticket validation.
- Không “fail open” khi KDC/JAAS/keytab lỗi; user chưa authenticated phải là 401/deny theo policy.
- Không dùng browser Kerberos ticket làm OAuth Access Token để gọi API khác; cần token exchange hoặc service delegation đúng giao thức riêng.

## 11. Java 17 độc lập: kiểm layout path/role trước deployment

Ví dụ sau là **một chương trình Java 17 thực sự biên dịch/chạy không cần KDC hoặc keytab**, xác minh **chính sách cấu hình**: service acceptor chỉ được map đúng principal/path, initiator chỉ được map đúng principal/path; nó **không đọc file secret** và **không xác minh Kerberos ticket**.

**Tệp `Krb5PathPolicyDemo.java`:**

~~~java
import java.util.Map;

public class Krb5PathPolicyDemo {
    record Policy(String principal, String keytab) {}

    static final Map<String, Policy> APPROVED = Map.of(
        "ACCEPTOR",
            new Policy("HTTP/portal.example.org@EXAMPLE.ORG",
                       "/run/secrets/kerberos/http-portal.keytab"),
        "INITIATOR",
            new Policy("svc-reader@EXAMPLE.ORG",
                       "/run/secrets/kerberos/svc-reader.keytab")
    );

    static final String JAAS =
        "/etc/kerberos/jaas.conf";
    static final String KRB5 =
        "/etc/kerberos/krb5.conf";

    static String check(String role, String principal,
                        String keytab, String jaas, String krb5) {
        Policy approved = APPROVED.get(role);
        if (approved == null) {
            return "DENY_ROLE";
        }
        if (!approved.principal().equals(principal)) {
            return "DENY_PRINCIPAL";
        }
        if (!approved.keytab().equals(keytab)) {
            return "DENY_KEYTAB";
        }
        if (!JAAS.equals(jaas) || !KRB5.equals(krb5)) {
            return "DENY_CONFIG_PATH";
        }
        return "ALLOW_LAYOUT";
    }

    static void show(String name, String role,
                     String principal, String keytab,
                     String jaas, String krb5) {
        System.out.println(name + "=" +
            check(role, principal, keytab, jaas, krb5));
    }

    public static void main(String[] args) {
        String acceptor = "HTTP/portal.example.org@EXAMPLE.ORG";
        String initiator = "svc-reader@EXAMPLE.ORG";
        String httpKey =
            "/run/secrets/kerberos/http-portal.keytab";
        String clientKey =
            "/run/secrets/kerberos/svc-reader.keytab";

        show("acceptor", "ACCEPTOR",
             acceptor, httpKey, JAAS, KRB5);
        show("initiator", "INITIATOR",
             initiator, clientKey, JAAS, KRB5);
        show("wrongPrincipal", "ACCEPTOR",
             "HTTP/evil.example.org@EXAMPLE.ORG", httpKey, JAAS, KRB5);
        show("wrongKeytab", "ACCEPTOR",
             acceptor, clientKey, JAAS, KRB5);
        show("wrongJaAs", "ACCEPTOR",
             acceptor, httpKey, "/tmp/jaas.conf", KRB5);
        show("unknownRole", "UNKNOWN",
             acceptor, httpKey, JAAS, KRB5);
    }
}
~~~

**Chạy với JDK 17+:**

~~~bash
javac Krb5PathPolicyDemo.java
java Krb5PathPolicyDemo
~~~

**Stdout chính xác:**

~~~text
acceptor=ALLOW_LAYOUT
initiator=ALLOW_LAYOUT
wrongPrincipal=DENY_PRINCIPAL
wrongKeytab=DENY_KEYTAB
wrongJaAs=DENY_CONFIG_PATH
unknownRole=DENY_ROLE
~~~

Giải thích:
- `ACCEPTOR` cần `HTTP/portal.example.org@EXAMPLE.ORG` và đúng HTTP service keytab.
- `INITIATOR` là principal riêng có keytab khác, không được dùng keytab acceptor.
- Một wrong principal hoặc wrong path bị policy từ chối ngay từ config review.
- Demo so chuỗi đường dẫn **chưa chống symlink/TOCTOU, mount injection hoặc quyền host**. Đây chỉ là kiểm soát cấu hình minh họa; production phải dùng realpath/secure mount, IAM, pod admission và validate file ownership.
- Chương trình không sinh keytab, không đọc credentials, không gọi KDC và không chứng minh SPNEGO login thành công. Muốn xác minh Kerberos thực tế phải chạy phép thử `LoginContext`/GSS theo mục kế tiếp.

## 12. Java 17 integration probe: LoginContext acceptor

Đoạn này **thực sự gọi JAAS** và yêu cầu keytab/principal/Kerberos config đúng. Nó có thể biên dịch trên JDK 17 thuần, **nhưng chỉ chạy PASS trong một môi trường đã provision đúng keytab**. Không có stdout cố định khi thiếu credentials; lỗi phải được ghi ở mức metadata, không in key.

**Tệp `KerberosAcceptorProbe.java`:**

~~~java
import javax.security.auth.Subject;
import javax.security.auth.kerberos.KerberosPrincipal;
import javax.security.auth.login.LoginContext;

public class KerberosAcceptorProbe {
    public static void main(String[] args) throws Exception {
        LoginContext context = new LoginContext("KrbAcceptor");
        context.login();
        try {
            Subject subject = context.getSubject();
            String required =
                "HTTP/portal.example.org@EXAMPLE.ORG";
            boolean principalMatches =
                subject.getPrincipals(KerberosPrincipal.class)
                       .stream()
                       .anyMatch(p -> p.getName().equals(required));

            if (!principalMatches) {
                throw new IllegalStateException(
                    "JAAS principal does not match approved SPN");
            }

            System.out.println("ACCEPTOR_JAAS_LOGIN=PASS");
            System.out.println("SERVICE_PRINCIPAL_MATCH=PASS");
            System.out.println("PRIVATE_CREDENTIALS_PRINTED=false");
        } finally {
            context.logout();
        }
    }
}
~~~

Biên dịch:

~~~bash
javac KerberosAcceptorProbe.java
~~~

Chạy **chỉ trên VM/container test có file JAAS/KDC/keytab tương ứng**:

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  KerberosAcceptorProbe
~~~

Nếu login acceptor thành công và đúng principal, stdout:

~~~text
ACCEPTOR_JAAS_LOGIN=PASS
SERVICE_PRINCIPAL_MATCH=PASS
PRIVATE_CREDENTIALS_PRINTED=false
~~~

Nếu keytab không tồn tại, không đọc được hoặc không chứa principal phù hợp, `LoginContext.login()` có thể ném `LoginException`. **Không** hardcode password/ticket để giả vờ PASS, không catch exception rồi trả 200 và không in `Subject.getPrivateCredentials()`. Một JAAS login pass chứng minh nạp credentials acceptor được, **chưa chứng minh browser SPNEGO negotiation, KDC ticket issuance hay Spring Security authorization**: cần integration test HTTP thực.

## 13. Kiểm chứng từ OS và KDC bằng các công cụ được phép

### 13.1. Kiểm filesystem mà không xuất secret

~~~bash
# Dùng đúng user runtime, không dùng root để suy quyền của app.
id

stat -L -c '%a %u %g %n' \
  /run/secrets/kerberos/http-portal.keytab

if test -r /run/secrets/kerberos/http-portal.keytab; then
  printf '%s\n' 'KEYTAB_READABLE_BY_RUNTIME=PASS'
else
  printf '%s\n' 'KEYTAB_READABLE_BY_RUNTIME=FAIL'
fi
~~~

`test -r` chỉ là kiểm quyền đọc theo process hiện tại, không chứng minh nội dung keytab hợp lệ, trusted source hay khả năng KDC tạo ticket. `stat -L` dereference symlink trên projected volumes; cần kiểm cả mount source và path ownership.

### 13.2. Kiểm metadata keytab

~~~bash
# Chỉ chạy trong môi trường được phép; tránh lưu output lên shared logs.
klist -k -e /run/secrets/kerberos/http-portal.keytab
~~~

Đối chiếu SPN, KVNO và enctype; **không chạy** công cụ xuất raw keys. Với một initiator test được cấp quyền riêng, có thể:

~~~bash
# Ví dụ dành cho principal client/sandbox, KHÔNG dùng trên user thật.
export KRB5_CONFIG=/etc/kerberos/krb5.conf
export KRB5CCNAME=FILE:/run/kerberos/ccache/svc-reader.ccache

kinit -k -t /run/secrets/kerberos/svc-reader.keytab \
  svc-reader@EXAMPLE.ORG

klist
# Sau test, cleanup cache theo policy:
kdestroy
~~~

**Điểm dễ nhầm:** `kinit` ở đây lấy TGT bằng service-client keytab để thử KDC, không thay JAAS acceptor và không đại diện cho user Lan. MIT tools có thể dùng `KRB5_CONFIG`/`KRB5CCNAME`; JDK Java vẫn cần kiểm `java.security.krb5.conf`/`ticketCache` options riêng.

### 13.3. Network, DNS và đồng hồ

- Kiểm DNS resolution của `kdc1.example.org` và `portal.example.org` từ đúng Pod/VM.
- Kiểm kết nối tới KDC TCP/UDP 88 và các dịch vụ AD/DNS cần thiết; network firewall không được mở rộng toàn cluster.
- Đồng bộ thời gian giữa browser/client, KDC và server qua NTP/PTP hoặc mechanism phù hợp. Kerberos có giới hạn clock skew; “Clock skew too great” là lỗi authentication, không chữa bằng cách tắt timestamp checks.
- Xác nhận SPN trong AD/KDC thuộc đúng service account, không duplicate, keytab KVNO/enctype cập nhật khi password/service key bị rotate.
- Nếu có CNAME hoặc cross-domain trust, test đúng canonical hostname mà browser dùng trong HTTP URL.

### 13.4. Test HTTP/SPNEGO end-to-end

Trong môi trường test domain-joined, browser được cấu hình tin phép Integrated Authentication tới Portal, khi mở `/private`:

1. Nhận `401 WWW-Authenticate: Negotiate`.
2. Browser xin service ticket cho `HTTP/portal.example.org` từ KDC.
3. Gửi `Authorization: Negotiate ...` (opaque token).
4. Spring Security Kerberos validator/JGSS dùng keytab nhận service ticket.
5. App map principal từ token đã xác minh sang user/authorities nội bộ.
6. Với user có quyền, nhận 200; với user đã xác thực nhưng không đủ quyền, 403.

Không dùng `curl -H 'Authorization: Negotiate blah'` rồi kết luận Kerberos phải accept; token giả phải bị từ chối. Nếu dùng curl built with GSS-API, tham khảo cách dùng `--negotiate -u :` trong môi trường có valid user ticket cache, nhưng **curl behavior không đồng nghĩa** với Browser SPNEGO policy và Java JAAS Subject.

## 14. Keytab generation và rotation: trách nhiệm identity team

Keytab của SPN phải được cấp từ quy trình Kerberos/AD được phê duyệt; không nên để application tự sinh keytab/password từ input user.

**Trình tự provisioning chuẩn:**

1. Xác định service principal chính xác, ví dụ `HTTP/portal.example.org@EXAMPLE.ORG`, và service account có owner/least privilege.
2. Registry/AD admin kiểm **SPN unique** và allowed cryptographic algorithms theo KDC policy.
3. Identity team tạo/export keytab cho principal bằng công cụ phù hợp, ghi rõ KVNO/enctypes và secret version.
4. Lưu binary keytab trong secret manager/secured artifact transfer, có encryption at rest/in transit và audit; không gửi qua email/ticket hoặc commit.
5. Provision đến đúng VM/Pod với path đã được JAAS/Spring cấu hình, chỉ runtime identity đọc.
6. Kiểm `klist -k -e` metadata trong môi trường hạn chế; thử `LoginContext` và HTTP/SPNEGO integration.
7. Khi rotate key, xác định KVNO mới và khả năng overlap: tùy KDC/AD policy, old key có thể mất hiệu lực ngay khi đổi password. Không hứa rằng old/new keytabs luôn có thể chạy song song.
8. Thực hiện controlled rollout và monitoring 401/GSS errors; thu hồi/cleanup keytabs cũ, backups, pod images/caches theo policy.
9. Khi lộ keytab, coi là **service credential compromise**: rotate/revoke keys, điều tra principal/targets đã bị giả mạo, audit and policy remediation. Xóa file khỏi Git không khiến key cũ vô hiệu.

### 14.1. Đừng thay SPN rồi chỉ sửa JAAS

Đổi `principal="HTTP/new-host.example.org@EXAMPLE.ORG"` trong JAAS **không tạo SPN mới ở KDC** và không cập nhật keytab. Cần phối hợp đủ: public DNS/URL, KDC SPN registration, keytab, app configs, browsers và reverse proxy.

### 14.2. Đừng mặc định “secret mount đã auto-rotate” nghĩa JVM đã nhận

Một ứng dụng có thể khởi tạo Kerberos ticket validator một lần lúc startup. Kể cả secret volume symlink đã trỏ tới keytab mới, Java `Subject` hoặc GSS credentials có thể đã cache. Cần thử rolling restart/re-initialize theo framework; không dựa vào thay file trên disk mà khẳng định runtime hiện tại dùng key mới.

## 15. Troubleshooting theo symptom

| Lỗi/hiện tượng | Khả năng gây ra | Cách xử lý đúng |
| --- | --- | --- |
| `Cannot locate KDC` / `Cannot find KDC for realm` | Wrong `krb5.conf`, realm, DNS hoặc KDC unreachable | Kiểm `-Djava.security.krb5.conf`, network TCP/UDP 88, realm case |
| `Server not found in Kerberos database` | SPN chưa đăng ký, FQDN sai hoặc realm mapping sai | Kiểm HTTP SPN, canonical URL và AD/KDC registry |
| `KRB_AP_ERR_MODIFIED` | Keytab không chứa key tương ứng, wrong KVNO, duplicate SPN hoặc encryption mismatch | Đối chiếu SPN/KVNO/enctype/keytab version, không tắt validation |
| `Clock skew too great` | Thời gian lệch giữa systems | NTP/time synchronization, không nới bừa kiểm time |
| `Unable to obtain password from user` | `doNotPrompt=false`/keytab missing và fallback prompt | Dùng đúng keytab, `doNotPrompt=true`, kiểm file permissions |
| `No valid credentials provided` / `Failed to find any Kerberos tgt` | Initiator Subject/cache sai hoặc TGT hết hạn | Phân biệt initiator/acceptor, ticketCache/JAAS config, TTL |
| `No key to decrypt ticket` | Acceptor keytab/SPN/KVNO/enctype sai | Kiểm approved SPN, keytab entries, runtime path |
| `Krb5LoginModule not found/config entry missing` | JAAS name/property sai hoặc JDK module/config không được đọc | Kiểm `java.security.auth.login.config` và entry names |
| `LoginException: Unable to obtain Principal Name` | Principal không khai báo, non-interactive prompt | Khai báo full principal, kiểm JAAS syntax |
| `Permission denied` đọc keytab | Mount owner/mode/UID/GID sai | Chỉnh secret provisioning; không mở chmod 777 |
| `401 loop` trên Browser | Browser không gửi Negotiate, SPN sai, GSS validation fail | Kiểm WWW-Authenticate/Authorization (không log token), browser zone, SPN |
| HTTP 401 vì browser không dùng Integrated Authentication | Browser/client không có TGT, policy website không cho delegation | Kiểm browser allowlist/OS login, không hạ security |
| HTTP 403 sau Negotiate | Authenticated nhưng app authorization deny | Kiểm user enabled/roles/tenant/resource, không sửa keytab |
| Ở host chạy được, trong Pod thất bại | krb5.conf/keytab mount khác, DNS/KDC blocked, hostname/cert/path sai | Kiểm đúng container UID, pod DNS/network và JVM flags |
| Lỗi chỉ một Pod | KVNO/secret version khác, stale validator/cache | So rollout/secret mount, restart plan, HA |
| MIT `kinit` OK nhưng Java fail | JDK đọc config/cache khác, JAAS wrong principal | Dùng Java system properties, `LoginContext` probe |
| After rotation all SPNEGO fail | New AD keytab chưa triển khai hoặc old key bị invalidated | Kiểm KDC KVNO/keytab, đồng bộ rollout |
| Excessive debug logs/tokens | `debug=true` hoặc `sun.security.krb5.debug` bị bật | Tắt debug production, purge logs theo incident policy |
| Cross-realm login bị từ chối | Trust/referrals/realm config hoặc tenant mapping | Review KDC trust, allowed realm/user authorization |

**Quy trình chẩn đoán hiệu quả:** Host URL/SPN → `krb5.conf`/realm/KDC/DNS/time → JAAS entry/name/options → keytab path+owner/mode → keytab principal/KVNO/enctype → JDK Subject/GSS behavior → Spring SPNEGO filter/provider → user/tenant authorization. Không chữa lỗi role bằng cách tắt Kerberos validation và không chữa DNS bằng cách chấp nhận arbitrary ticket issuers.

### 15.1. Bật debug ở đâu?

Có hai tầng:
- JAAS `Krb5LoginModule debug=true`.
- JDK `-Dsun.security.krb5.debug=true` (và các GSS debug cơ chế tùy version).

Chỉ bật tạm trong **sandbox**, bảo đảm logs bị giới hạn và xóa theo retention policy. Kerberos debug có thể chứa realm/principal, ticket metadata, network addresses hoặc context nhạy cảm. Không in raw `Authorization: Negotiate`/ticket data hoặc keytab bytes để giải quyết lỗi.

## 16. Kiểm thử và tiêu chí QA

| Tình huống | Expected result |
| --- | --- |
| Acceptor keytab SPN đúng, readable, JAAS đúng | `LoginContext("KrbAcceptor")` pass trên test environment |
| HTTP SPNEGO token hợp lệ cho Portal | Spring xác thực user rồi áp authorization |
| HTTP token thiếu/chưa negotiate | 401 + Negotiate challenge hoặc flow fallback được phê duyệt |
| HTTP token giả Base64 | Reject; không tạo authenticated principal |
| Token ký cho SPN khác | Reject tại GSS validation |
| Wrong realm/issuer trust | Reject hoặc KDC referral theo policy, không auto-trust |
| Keytab path sai/không tồn tại | Fail-closed, không fallback prompt password |
| World-readable keytab | Deployment security policy FAIL, dù login có thể chạy |
| App UID không đọc keytab | Startup/authentication fail rõ, không chmod 777 |
| `isInitiator=false` với acceptor | Nạp service key cho accept operation, không cần user TGT |
| Initiator keytab bị thay bằng HTTP keytab | Reject do principal mismatch / wrong credentials |
| `doNotPrompt=true` không có credential source | Fail, không prompt |
| `ticketCache` nhưng `useTicketCache=false` | JAAS config invalid/fail |
| `renewTGT=true` nhưng `useTicketCache=false` | JAAS config invalid/fail |
| Expired/missing initiator TGT | Fail hoặc re-login theo policy, không dùng stale cache |
| Wrong DNS/KDC | Login fail, cảnh báo cấu hình/network |
| Time skew cao | Kerberos reject, cần đồng bộ clock |
| Reverse proxy dùng internal hostname | SPN mismatch, chỉnh public hostname/registration |
| Pod A keytab version cũ, Pod B mới | Phát hiện drift trước rollout, không random 401 |
| Post-rotation new keytab | SPNEGO pass sau restart/refresh có kiểm chứng |
| User authenticated nhưng không có quyền app | 403, không phải 200 chỉ vì Kerberos ticket pass |
| Secret in debug/CI/log/image | QA FAIL và xử lý rò rỉ theo incident policy |
| App logout nhưng browser còn domain TGT | Có thể SSO lại ngay; UX giải thích đúng phạm vi |

### 16.1. Test layers

1. **Static config QA:** kiểm Java flags, JAAS syntax, principal/path, `krb5.conf` mapping, secret path allowlist và file ownership. Chạy `Krb5PathPolicyDemo`.
2. **JAAS integration:** chạy `KerberosAcceptorProbe` trên một Pod/VM sandbox có keytab, xác minh không in private credentials.
3. **KDC integration:** chạy test được phê duyệt với MIT tooling/Java GSS, đối chiếu hostname/SPN/KVNO/time.
4. **HTTP browser E2E:** thử Negotiate handshake thật, authorized/unauthorized user, direct/aliased URLs và reverse proxy.
5. **Ops/chaos:** KDC failover, secret mount unavailable, bad keytab, expired cache, rolling rotation, nodes lệch version.
6. **Security regression:** không cho arbitrary Host/tenant chọn keytab, no public secret mount, no plaintext token logging, no fallback auth bypass.

**Bài toán test đúng nguyên nhân:** Nếu chỉnh service principal trong JAAS nhưng không đổi keytab, login fail chỉ chứng minh mismatch, không chứng minh DNS mapping. Nếu sửa Kerberos token bytes, failure chỉ chứng minh integrity; muốn test authorization, dùng một valid principal **không có quyền** rồi kiểm 403.

## 17. Checklist production

- [ ] Có danh sách realms/KDCs được phê duyệt; `krb5.conf` đúng với environment và reachable network.
- [ ] Browser public hostname, Kerberos HTTP SPN, keytab và reverse proxy thống nhất.
- [ ] JAAS acceptor: `useKeyTab=true`, `storeKey=true`, `isInitiator=false`, `doNotPrompt=true`, principal cố định.
- [ ] JAAS initiator (nếu có) dùng service identity/keytab hoặc ticket cache riêng, không dùng nhầm HTTP acceptor keytab.
- [ ] Java flags chỉ rõ đúng JAAS file và krb5.conf; hiểu sự khác biệt với biến môi trường MIT.
- [ ] Keytab binary không có trong Git, image, ConfigMap, application.yml, stdout, logs hoặc backup không được bảo vệ.
- [ ] Keytab volume read-only, đúng UID/GID/mode; quyền Pod exec, host/root, cluster RBAC và etcd encryption được review.
- [ ] JAAS/krb5.conf không cho user không đáng tin sửa để trỏ sang keytab/KDC khác.
- [ ] `SunJaasKerberosTicketValidator`/SPNEGO filter/provider có version tương thích Spring Security hiện dùng.
- [ ] Fail-closed khi keytab/KDC/ticket invalid; không cấp authentication bằng raw username/header.
- [ ] UserDetailsService/authorization kiểm active account, realm/tenant, authorities và resource ownership.
- [ ] NTP/DNS/KDC 88, SPN uniqueness, KVNO/encryption types và cross-realm policy được test.
- [ ] Rotation có secret versioning, rollout/restart plan, KDC coordination và incident runbook.
- [ ] Debug được tắt sau testing; logs/trace/APM loại raw Authorization Negotiate và credentials.
- [ ] Đã test 401/403, wrong keytab, wrong SPN, expired TGT, pod failover và secret permission denial.

## 18. Bài tập và đáp án định hướng

**Bài A — đọc ba loại file.** Cho `krb5.conf`, `jaas.conf`, `http.keytab`. Hãy nêu file nào cho KDC/realm, file nào xác định JAAS module, file nào có long-term service key. Vì sao chỉ dùng `chmod 600` trên `krb5.conf` mà keytab `0644` là không an toàn?

**Bài B — phân vai.** Portal nhận browser SPNEGO qua `HTTP/portal.example.org`, còn Report Client dùng `svc-reader` xin ticket đến `HTTP/reports.example.org`. Chọn `isInitiator` và keytab đúng cho từng vai. Vì sao không dùng keytab Portal acceptor để “đại diện người dùng” khi gọi Reports?

**Bài C — Java 17.** Chạy `Krb5PathPolicyDemo.java`, đối chiếu 6 dòng stdout. Đổi một keytab path sang `/tmp/http.keytab` và giải thích vì sao bị `DENY_KEYTAB`; nêu giới hạn của unit test này.

**Bài D — JAAS integration.** Trong sandbox do tổ chức cấp keytab, chạy `KerberosAcceptorProbe.java` với `-Djava.security.krb5.conf` và `-Djava.security.auth.login.config`. Kiểm stdout khi pass và expected fail khi đổi principal (chỉ trong sandbox), không in private credentials.

**Bài E — Kubernetes.** Pod UID 10001 mount keytab owner root mode `0400` và không đọc được. Đề xuất cách cấp ownership/group access đúng, kiểm `stat -L`/`test -r`, giải thích vì sao không chọn `0644`.

**Bài F — KDC/AD.** Sau xoay password của service account, `KVNO` tăng nhưng Pod vẫn mount keytab cũ. Nêu lý do `KRB_AP_ERR_MODIFIED` có thể xuất hiện và kế hoạch coordinated rollout.

**Bài G — SPNEGO lỗi 401.** Browser đã domain-joined nhưng không gửi `Authorization: Negotiate`. Kiểm browser allowlist, Host public, TLS, KDC và SPN; phân biệt lỗi thiếu ticket với lỗi Spring authorization 403.

**Bài H — session và delegation.** Browser user Lan đã login với Kerberos; service Java tự dùng `svc-reader.keytab` gọi API. Nó có đang “gọi thay Lan” không? Không mặc nhiên: identity Kerberos ở backend là service account, cần delegation/constrained delegation hoặc token exchange và authorization design riêng.

**Bài I — bảo mật.** Đề xuất 5 negative tests cho secret path injection, wrong realm/SPN, bad keytab mode, debug leak và KDC outage. Với mỗi test, nêu fail-closed behavior.

**Bài J — so sánh MIT và JDK.** Shell dùng `KRB5_CONFIG`/`KRB5CCNAME` và `kinit` pass, nhưng Java dùng `-Djava.security.krb5.conf` sai. Vì sao Java vẫn fail? Cách kiểm JAAS `ticketCache`/keytab/Subject theo đúng JVM?

**Tiêu chí đạt:** Tự giải thích được **KDC/realm (`krb5.conf`) + JAAS login options + secret keytab/cache + SPN + Spring SPNEGO validator + application authorization**; cấu hình đường dẫn an toàn, chạy Java 17 demo, biết khi nào cần KDC thật và có runbook cho permission, clock skew, SPN, KVNO và rotation.

## 19. Tài liệu tham khảo chính thức

- Oracle Java 17 API – `Krb5LoginModule` options, legal combinations, isInitiator, keyTab, ticketCache: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- Oracle Java 17 – Java Authentication and Authorization Service (JAAS) Reference Guide và login config: https://docs.oracle.com/en/java/javase/17/security/java-authentication-authorization-service-jaas-reference-guide.html
- Oracle Java 17 – HTTP/SPNEGO Authentication, krb5.conf/JAAS/useSubjectCredsOnly: https://docs.oracle.com/en/java/javase/17/security/part-vi-httpspnego-authentication.html
- Oracle Java 17 – JAAS Login Utility and Java GSS API: https://docs.oracle.com/en/java/javase/17/security/use-jaas-login-utility-and-java-gss-api-secure-message-exchanges.html
- Oracle Java 17 – javax.security.auth.kerberos and JGSS: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/javax/security/auth/kerberos/package-summary.html
- MIT Kerberos – krb5.conf (realms/domain_realm/KDC): https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/conf_files/krb5_conf.html
- MIT Kerberos – User configuration, KRB5_CONFIG/KRB5_KTNAME/KRB5CCNAME: https://web.mit.edu/Kerberos/krb5-latest/doc/user/user_config/kerberos.html
- Spring Security Kerberos – Spring integration, SPNEGO, KerberosServiceAuthenticationProvider, SunJaasKerberosTicketValidator: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security – SPNEGO integration reference: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Kubernetes – Secrets best practices: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Kubernetes – Encrypting data at rest: https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
