# Realm, KDC, principal và Service Principal Name trong Kerberos/SPNEGO

**Kerberos** là giao thức xác thực mạng dựa trên vé (ticket), khóa bí mật và một bên thứ ba được tin cậy là **Key Distribution Center (KDC)**. Trong tích hợp **Spring Security Kerberos + SPNEGO**, trình duyệt thường lấy một service ticket từ KDC và gửi nó cho ứng dụng qua HTTP `Authorization: Negotiate ...`. Ứng dụng chỉ chấp nhận token khi có thể kiểm chứng ticket bằng khóa của **đúng dịch vụ**, thường được lưu trong **keytab**. Để hiểu vì sao cấu hình hoạt động hoặc báo lỗi, người học phải nắm chính xác **realm, KDC, principal và Service Principal Name (SPN)**.

Một ví dụ xuyên suốt:

~~~text
Kerberos realm:           CORP.EXAMPLE
Domain/DNS zone:          corp.example
KDC (Windows DC):         dc01.corp.example
User principal:           lan@CORP.EXAMPLE
Service principal:        HTTP/portal.corp.example@CORP.EXAMPLE
AD SPN:                   HTTP/portal.corp.example
AD service account:       CORP\svc_portal
Browser public URL:       https://portal.corp.example/
Spring acceptor keytab:   /etc/security/keytabs/portal-http.keytab
~~~

**Phân biệt cực kỳ quan trọng:** **SPN không phải một địa chỉ URL, không phải tên file keytab, không phải username của người dùng và cũng không phải tên máy KDC.** SPN là định danh của *service instance* mà KDC dùng để tìm đúng service account/key. Trong AD, chuỗi SPN thường được đăng ký dạng `HTTP/portal.corp.example`; trong Kerberos principal đầy đủ, realm có thể được gắn thêm: `HTTP/portal.corp.example@CORP.EXAMPLE`.

Bài thuộc nhóm **Kerberos và SPNEGO**, đi từ khái niệm nền tảng đến luồng AS/TGS/AP, định danh/trust, cấu hình Windows AD và MIT Kerberos, Spring Security JavaConfig, keytab/KVNO/encryption types, lỗi khi chạy sau reverse proxy, bảo vệ quyền và kiểm thử. Có chương trình **Java 17** độc lập để minh họa logic khớp SPN, hostname và keytab, đồng thời chỉ rõ giới hạn của việc kiểm chuỗi.

## 1. Bản đồ thuật ngữ

| Thuật ngữ | Vai trò | Ví dụ | Không phải |
| --- | --- | --- | --- |
| **Realm** | Không gian quản trị Kerberos, chứa tập principals và KDC/keys | `CORP.EXAMPLE` | Không đơn giản là DNS zone hoặc Windows UPN suffix |
| **KDC** | Thành phần tin cậy phát TGT và service ticket | `dc01.corp.example` | Không phải chính web server Portal |
| **AS (Authentication Service)** | Thành phần KDC phát TGT sau khi xác minh client | AS-REQ/AS-REP | Không cấp trực tiếp role Spring |
| **TGS (Ticket Granting Service)** | Thành phần KDC phát service ticket dựa trên TGT | TGS-REQ/TGS-REP | Không phải một HTTP callback |
| **Principal** | Định danh của user, service hoặc thành phần hệ thống Kerberos | `lan@CORP.EXAMPLE` | Không tự đồng nghĩa account email |
| **Service principal** | Kerberos principal dành cho một dịch vụ cụ thể | `HTTP/portal.corp.example@CORP.EXAMPLE` | Không phải principal của mọi người dùng |
| **SPN** | Định danh service được KDC/AD dùng để tìm account/key | `HTTP/portal.corp.example` | Không phải TLS certificate SAN |
| **TGT** | Ticket cho TGS, thường được cache sau user login | `krbtgt/CORP.EXAMPLE@CORP.EXAMPLE` | Không gửi nguyên TGT cho Portal trong browser SPNEGO |
| **Service ticket** | Ticket cho service `HTTP/portal.corp.example` | Được bọc trong GSS/SPNEGO token | Không phải JWT hoặc SAML Assertion |
| **Keytab** | File chứa key entries và principal/kvno/enctype để acceptor dùng | `portal-http.keytab` | Không phải truststore TLS |
| **KVNO** | Key Version Number: phiên bản khóa của principal | `kvno=7` (minh họa) | Không phải HTTP status code |
| **SPNEGO** | Cơ chế GSS-API thương lượng qua `Negotiate` | HTTP 401 + Negotiate | Không phải tên KDC hoặc realm |
| **AD service account** | AD object giữ credentials/keys của service SPN | `CORP\svc_portal` | Không nhất thiết là tên HTTP host |
| **UserDetailsService** | Spring tra local user/authorities sau Kerberos check | `loadUserByUsername(...)` | Không phải bộ kiểm mật mã service ticket |

Ba lớp cần phân biệt: **DNS** tìm host; **Kerberos SPN** xác định service account; **HTTP/TLS** chuyển tải yêu cầu và bảo vệ kênh. Khi browser truy cập HTTPS, Kerberos HTTP service class **vẫn là `HTTP/`**, không phải `HTTPS/`.

## 2. Realm là gì?

Realm định danh miền quản trị của một hệ thống Kerberos. Theo quy ước, realm thường viết hoa dạng DNS-like (`CORP.EXAMPLE`), còn DNS domain thường viết thường (`corp.example`). Trong Windows Active Directory, AD domain thường gắn với Kerberos realm cùng tên về mặt chữ cái, nhưng đó **không phải đồng nhất bắt buộc của mọi hệ thống**.

Realm bao gồm:

- Tập user/service principals và khóa bí mật tương ứng.
- Một hoặc nhiều **KDC** cấp vé trong phạm vi tin cậy.
- Quy tắc đăng nhập, authentication policy, lifetime/renewal của ticket và chính sách encryption.
- Các quan hệ trust cần thiết để truy cập service ở realm khác.
- Cấu hình DNS/KDC discovery và mapping từ hostname/domain sang realm.

Ví dụ:

~~~text
DNS domain:           corp.example
Kerberos realm:       CORP.EXAMPLE
KDC hosts:            dc01.corp.example, dc02.corp.example
User:                 lan@CORP.EXAMPLE
Service:              HTTP/portal.corp.example@CORP.EXAMPLE
Cross-realm partner:  PARTNER.EXAMPLE (chỉ khi có trust phù hợp)
~~~

**Không phải user có email `lan@partner.example` thì Kerberos realm mặc nhiên là `PARTNER.EXAMPLE`.** Email, UPN, NetBIOS logon name và Kerberos principal có thể được cấu hình/mapping khác nhau. Ứng dụng cần dùng identity/realm được Kerberos validator xác minh, không dùng domain email để tự suy trust.

### Realm không đồng nghĩa tenant của ứng dụng

Một realm Kerberos có thể phục vụ nhiều ứng dụng và nhiều tổ chức nội bộ. Ngược lại, một ứng dụng đa tenant có thể chấp nhận principals từ nhiều realms qua trust/cross-realm mechanism. **Kerberos chứng minh một principal trong không gian tin cậy**; xác định người đó có quyền vào tenant A hay dữ liệu B vẫn là trách nhiệm của ứng dụng.

## 3. KDC, AS và TGS: cùng trung tâm nhưng vai trò khác

KDC có hai dịch vụ logic quan trọng:

1. **AS (Authentication Service):** nhận `AS-REQ`, xác thực client theo chính sách rồi cấp **Ticket Granting Ticket (TGT)** và key material phù hợp. Với AD có thể sử dụng pre-authentication, smart card/PKINIT và những chính sách khác, không mặc định mọi trường hợp là mật khẩu.
2. **TGS (Ticket Granting Service):** nhận `TGS-REQ` được bảo vệ bằng TGT và Authenticator, xác định service principal yêu cầu, rồi cấp **service ticket** cho đích đó.

~~~mermaid
sequenceDiagram
    participant U as Client/Browser
    participant KDC as KDC của CORP.EXAMPLE
    participant WEB as Spring Portal acceptor
    U->>KDC: AS-REQ (user principal / preauthentication)
    KDC-->>U: AS-REP + TGT cho krbtgt/CORP.EXAMPLE
    U->>KDC: TGS-REQ cho HTTP/portal.corp.example
    KDC->>KDC: Tra SPN → service account → key version/enctype
    KDC-->>U: TGS-REP + service ticket của HTTP/portal...
    U->>WEB: HTTP Authorization: Negotiate <GSS token>
    WEB->>WEB: SPNEGO/JGSS dùng keytab để verify service ticket
    WEB-->>U: 200 hoặc thêm Negotiate token nếu cần mutual auth
~~~

**AS và TGS không nhất thiết là hai máy vật lý**. Trong Active Directory, Domain Controller thường đảm nhiệm vai trò KDC. Trong MIT Kerberos, có thể vận hành nhiều KDC chính/phụ cho cùng realm. **Đừng hardcode một DC duy nhất** nếu tổ chức dùng DNS SRV/discovery/failover.

### TGT không phải vé cho mọi dịch vụ

`krbtgt/CORP.EXAMPLE@CORP.EXAMPLE` là ticket-granting-service principal. TGT cho phép client yêu cầu service tickets tiếp theo, nhưng web server `HTTP/portal.corp.example` cần **service ticket mang service principal phù hợp**. Không thiết kế Spring app nhận raw TGT như một bearer token thay service ticket.

Service ticket thông thường chứa một phần được mã hóa bằng **long-term key của service principal**. Vì vậy Portal phải sở hữu đúng keytab/credential của service account — nếu key sai, ticket không thể được acceptor xử lý.

## 4. Principal: định danh của user, service và TGS

Theo Kerberos V5 (RFC 4120), principal name gồm các thành phần tên và một realm. Cách biểu diễn dễ đọc phổ biến:

~~~text
user principal:
  lan@CORP.EXAMPLE

service principal with host instance:
  HTTP/portal.corp.example@CORP.EXAMPLE

another service principal:
  host/node01.corp.example@CORP.EXAMPLE

TGS principal:
  krbtgt/CORP.EXAMPLE@CORP.EXAMPLE
~~~

Các dấu phân cách:

- `@REALM`: gắn name vào Kerberos realm cụ thể.
- `/instance`: thêm phần instance, thường là hostname cho network service.
- `HTTP/`: service class dành cho HTTP authentication, kể cả URL chạy trên HTTPS.
- `krbtgt/`: TGS principal, không phải một website HTTP.

### User principal và Service Principal Name khác gì?

| Loại | Đối tượng | Ví dụ | Khóa/cơ chế |
| --- | --- | --- | --- |
| User principal | Người dùng | `lan@CORP.EXAMPLE` | Client có TGT từ AS, do OS/credential cache nắm |
| HTTP service principal | Web service | `HTTP/portal.corp.example@CORP.EXAMPLE` | Keytab/service account của app/acceptor |
| TGS principal | Dịch vụ cấp vé | `krbtgt/CORP.EXAMPLE@CORP.EXAMPLE` | KDC và realm giữ khóa bảo vệ TGT |
| Computer/host principal | Máy/host service | `host/node01.corp.example@CORP.EXAMPLE` | Machine/service credential theo môi trường |

**Một principal không tự mang role.** Nếu KDC xác nhận `lan@CORP.EXAMPLE`, Spring vẫn phải tra local account và authorities; việc username trông như admin hoặc chứa cùng tên `service-account` không tự mang quyền.

### KerberosPrincipal trong Java 17

JDK cung cấp `javax.security.auth.kerberos.KerberosPrincipal` với hằng `KRB_NT_PRINCIPAL`, `KRB_NT_SRV_HST` và getters như `getName()`, `getRealm()`, `getNameType()`. Đây là **đối tượng định danh**, không phải API đăng nhập mạng hoặc xác minh vé:

~~~java
KerberosPrincipal user = new KerberosPrincipal(
        "lan@CORP.EXAMPLE",
        KerberosPrincipal.KRB_NT_PRINCIPAL);

KerberosPrincipal service = new KerberosPrincipal(
        "HTTP/portal.corp.example@CORP.EXAMPLE",
        KerberosPrincipal.KRB_NT_SRV_HST);
~~~

Cần import `javax.security.auth.kerberos.KerberosPrincipal`. Ví dụ là fragment để phân biệt name type; **constructor thành công không chứng minh principal đã tồn tại trong KDC** hay keytab chứa đúng key. Không đọc giá trị `getRealm()` rồi cho phép mọi principal trong realm đó truy cập admin.

## 5. SPN: địa chỉ logic của dịch vụ đối với Kerberos

Trong Active Directory, SPN được đăng ký trên một **account object**, thường là computer account hoặc service account. KDC sử dụng SPN để tìm khóa của account phục vụ dịch vụ. Với website:

~~~text
Browser URL:
https://portal.corp.example/reports

Service class:
HTTP

Browser target host:
portal.corp.example

Requested SPN:
HTTP/portal.corp.example

Corresponding Kerberos principal (common representation):
HTTP/portal.corp.example@CORP.EXAMPLE

AD account owning SPN:
CORP\svc_portal
~~~

**Quan hệ cần đúng:** browser yêu cầu `HTTP/portal.corp.example` → KDC tìm SPN đăng ký trên đúng account → KDC mã hóa vé bằng key của account → Spring acceptor có keytab hợp lệ cho account/principal → xác minh token → tra user details/role.

**Sai SPN có hai kiểu lỗi chính**:

1. **KDC không tìm được hoặc tìm quá nhiều owners:** `KDC_ERR_S_PRINCIPAL_UNKNOWN` hoặc `KDC_ERR_PRINCIPAL_NOT_UNIQUE` theo môi trường.
2. **KDC cấp được ticket nhưng Spring không thể giải mã/accept:** `KRB_AP_ERR_MODIFIED` hoặc Kerberos integrity/decryption failure, thường do keytab sai, account đổi mật khẩu, KVNO/enctype lệch hoặc SPN trỏ nhầm account.

SPN không phải đường dẫn HTTP: `HTTP/portal.corp.example` là một principal; `/login` hoặc `/api/reports` thường **không** là thành phần SPN. HTTPS URL path, query và fragment không dùng để chọn SPN trong use case HTTP Kerberos phổ biến.

## 6. SPN syntax và chuẩn tên theo Windows AD

Tài liệu Microsoft mô tả cú pháp chung có thể chứa service class, host, port và service name, ví dụ dạng `serviceclass/host:port/servicename` trong những trường hợp đặc biệt. Với **HTTP Negotiate**, mẫu thông dụng vẫn là `HTTP/fqdn`.

~~~text
Common HTTP SPN:
  HTTP/portal.corp.example

Another alias:
  HTTP/reports.corp.example

Service principal with realm:
  HTTP/portal.corp.example@CORP.EXAMPLE

A non-HTTP example:
  MSSQLSvc/sql01.corp.example:1433
~~~

**Không mặc định thêm cổng vào SPN HTTP** chỉ vì URL dùng `:8443`. HTTP SPN port handling phụ thuộc client/Windows settings/service convention; kiểm chính xác SPN mà client yêu cầu qua `klist`/trace thay vì suy đoán. Không đăng ký `HTTPS/portal...` vì trang dùng TLS.

**Case:** service class/hostname có thể được hệ thống AD so khớp theo quy tắc riêng; nhưng Kerberos realm và principal/keytab được lưu và hiển thị cụ thể. Hãy dùng một cách viết nhất quán, kiểm credential thực tế, đừng tự lowercase toàn bộ chuỗi rồi cho rằng các realm/keys tương đương trong mọi implementation.

### SPN phải thuộc về đúng một account

Microsoft khuyến nghị dùng `setspn -S` thay `-A` vì `-S` kiểm SPN trùng trước khi thêm. SPN trùng trên nhiều AD accounts có thể khiến KDC không xác định được key đúng, hoặc dẫn tới ticket mã hóa cho một account khác với keytab của Portal. Trước và sau khi đăng ký, kiểm SPN trong phạm vi domain/forest có liên quan.

## 7. Tra cứu SPN trong Active Directory

Trên máy Windows đã cài RSAT/AD tools và có quyền phù hợp:

~~~powershell
# Tra SPN cụ thể (read-only):
setspn -Q HTTP/portal.corp.example

# Liệt kê SPN của một service account (read-only):
setspn -L CORP\svc_portal

# Tìm SPN bị trùng (read-only):
setspn -X

# Truy vấn phạm vi forest khi cần:
setspn -F -Q HTTP/portal.corp.example
~~~

Đây là **lệnh chẩn đoán**, không có stdout cố định và chỉ chạy trong một AD domain/forest thật khi đã được phép. Nếu SPN bị trùng cần xác định **đúng account owner, dịch vụ nào đang sử dụng và hiệu ứng ứng dụng khác** trước khi thay đổi. Không xóa mọi SPN “trông giống Portal” vì máy/ứng dụng khác có thể đang dùng.

### Đăng ký SPN (thao tác thay đổi AD, chỉ dành cho người được ủy quyền)

~~~powershell
# Minh họa thay đổi servicePrincipalName trong AD:
setspn -S HTTP/portal.corp.example CORP\svc_portal
~~~

Chỉ thực hiện sau khi service account đã được tạo/phê duyệt, đã kiểm duplicate và có change request. Đây **không phải lệnh phải chạy trên mọi node** của một Kubernetes/VM cluster. Một **public virtual hostname** thường tương ứng một SPN duy nhất có owner account rõ ràng; các backend replicas có thể sử dụng đúng credentials/keytab tương ứng theo chính sách.

**Không dùng `setspn -A` vô điều kiện** vì có thể bỏ qua kiểm trùng. Với migration từ account cũ sang account mới phải có kế hoạch cutover, keytab rollover và rollback; không tự chuyển SPN production chỉ vì một lần `KRB_AP_ERR_MODIFIED`.

### UPN, sAMAccountName và SPN

AD có những thuộc tính khác nhau:

- **sAMAccountName:** ví dụ `svc_portal`, tên account legacy trong domain.
- **userPrincipalName (UPN):** có thể trông như `svc_portal@corp.example` hoặc suffix khác.
- **servicePrincipalName:** giá trị ví dụ `HTTP/portal.corp.example`, dùng tìm account cho service ticket.

**Đừng lấy UPN của tài khoản service làm SPN**. KDC cần đúng servicePrincipalName của HTTP service; việc một account có UPN đúng không tự đăng ký `HTTP/portal...`.

## 8. Principal, SPN, DNS và browser target: chuỗi ràng buộc

Có thể coi kiểm cấu hình là một chuỗi:

~~~text
User opens:
  https://portal.corp.example/

Browser requests Kerberos service ticket for:
  HTTP/portal.corp.example

AD servicePrincipalName entry:
  HTTP/portal.corp.example -> CORP\svc_portal

KDC service ticket encrypted under:
  key of svc_portal, selected KVNO/enctype

Spring acceptor:
  servicePrincipal = HTTP/portal.corp.example@CORP.EXAMPLE
  keytab principal/key(s) for svc_portal

Result:
  valid GSS Kerberos security context -> user principal
~~~

**Nếu một mắt xích không khớp, single sign-on có thể fail dù DNS, TLS và LDAP đều hoạt động**. Ví dụ load balancer `portal.corp.example` chuyển đến `node01.corp.example`, nhưng Spring dùng keytab `HTTP/node01.corp.example@CORP.EXAMPLE`. Browser vẫn xin vé cho `HTTP/portal.corp.example`, nên node có thể không accept vé.

### DNS CNAME/alias

DNS alias giúp browser tìm IP/endpoint, nhưng **không tự tạo SPN hoặc cấp quyền dùng key của account đích**. Client có thể chọn SPN theo URL host hoặc canonicalized DNS name tùy hệ điều hành/SSPI/GSS settings. Trong nhiều hệ thống, browser truy cập hostname public và yêu cầu `HTTP/public-host`.

Nếu chuyển từ `portal.corp.example` sang `reports.corp.example`, phải kiểm thực tế:

1. Browser yêu cầu SPN nào (`HTTP/portal...` hay `HTTP/reports...`).
2. AD đã đăng ký SPN đó trên đúng account chưa.
3. Keytab/acceptor có principal/keys tương ứng chưa.
4. TLS certificate SAN có đúng public hostname mới không.
5. Reverse proxy/virtual host đã chuyển Negotiate header đúng chưa.

**Không suy rằng CNAME luôn làm SPN bằng canonical target** hoặc ngược lại; chuẩn hóa DNS tùy client. Microsoft có hướng dẫn riêng khi dùng Entra Application Proxy Kerberos Constrained Delegation (KCD) khuyên A record thay vì CNAME trong một số trường hợp; đây là **hướng dẫn cho kiến trúc đó**, không phải quy tắc DNS/Kerberos tổng quát.

## 9. Keytab: vì sao service phải giữ đúng khóa?

**Keytab** là file chứa principal và key material để service không cần nhập mật khẩu thủ công mỗi lần nhận Kerberos ticket. Khi KDC phát service ticket cho `HTTP/portal.corp.example`, một phần ticket được mã hóa bằng long-term key của account service. Java GSS/JAAS acceptor sử dụng key từ keytab để giải mã/xác minh và thiết lập security context.

Một keytab có thể chứa nhiều records cho:

- Một hoặc nhiều principals được quản trị.
- Các encryption types khác nhau (ví dụ AES256/AES128) theo chính sách.
- Các key version numbers (**KVNO**) trong quá trình rotation.

**Keytab rất nhạy cảm**: ai sao chép nó có thể có năng lực giả mạo service/accept Kerberos tickets hoặc thực hiện các hành động liên quan đến khóa trong phạm vi protocol. Không commit keytab vào Git, container image public hoặc artifact server không được bảo vệ. Ưu tiên secret volume/keystore quản trị, permission tối thiểu, rotation và audit truy cập.

### KVNO và key rotation

Khi password/secret của service account được thay đổi, KDC có thể cấp ticket với **KVNO mới**. Nếu keytab trên Portal vẫn chứa key cũ, Spring acceptor không giải được ticket. Một số môi trường có giai đoạn overlap các keys/version để bảo đảm dịch vụ không đứt ngay trong cutover, nhưng phải được quản trị minh bạch.

Để kiểm, trên Linux có công cụ phù hợp:

~~~bash
# Liệt kê metadata keytab, KHÔNG in key material:
klist -kte /etc/security/keytabs/portal-http.keytab
~~~

Tùy bản triển khai, `-k` hiển thị keytab, `-t` timestamp và `-e` encryption types. Không đăng toàn bộ output nếu chứa principal names nhạy cảm. Quan sát principal, KVNO và enctype, so với KDC/service account đã được chuẩn hóa.

**Không đổi password của service account hoặc chạy lại keytab exporter nhiều lần vô tội vạ**: một số công cụ (ví dụ `ktpass`) có thể tác động key/KVNO và làm tất cả app nodes đang dùng keytab cũ thất bại. Tạo/rotate keytab phải do AD/PKI/IAM owner thực hiện theo runbook.

## 10. MIT Kerberos và Windows AD khác gì ở bước quản trị?

| Nhiệm vụ | MIT Kerberos thường dùng | Active Directory thường dùng |
| --- | --- | --- |
| Cấu hình realm/KDC | `/etc/krb5.conf`, DNS SRV | Domain join, DC/KDC discovery, optional krb5.conf trên Linux |
| Tạo service principal | `kadmin`, `addprinc` theo policy | Tạo service account/computer account và gắn SPN |
| Phát keytab | `ktadd` theo quy trình MIT | AD-managed keytab export/ktpass/gMSA theo kiến trúc |
| Tra principals | `kadmin getprinc` (cần quyền) | `setspn -Q/-L` |
| User tickets | `kinit`, `klist` | Windows `klist`, logon cache hoặc MIT kinit |
| Service ticket | `kvno HTTP/host` | Windows `klist get HTTP/host` hoặc browser negotiation |
| KDC | krb5kdc/kadmind theo topology | Active Directory Domain Controllers |

Một **gMSA** trong Windows hữu ích khi dịch vụ chạy trong môi trường Windows có hỗ trợ quản lý mật khẩu tự động. Với Linux/Spring container dùng keytab, cần thiết kế identity/secret distribution và rotation phù hợp; **không giả định gMSA của Windows tự tạo một keytab Linux dùng được**.

**KDC port phổ biến là TCP/UDP 88**. Nếu chặn DNS/DC/KDC ở firewall, browser có thể không lấy được service ticket. Đăng ký SPN đúng nhưng không liên lạc được KDC cũng không tạo được SSO.

## 11. Cấu hình krb5.conf với realm và KDC

Một ví dụ Linux/JDK dùng MIT-style config:

~~~ini
[libdefaults]
    default_realm = CORP.EXAMPLE
    dns_lookup_realm = false
    dns_lookup_kdc = true
    rdns = false

[realms]
    CORP.EXAMPLE = {
        kdc = dc01.corp.example
        kdc = dc02.corp.example
    }

[domain_realm]
    .corp.example = CORP.EXAMPLE
    corp.example = CORP.EXAMPLE
~~~

Ý nghĩa:

- `default_realm`: realm mặc định khi không có `@REALM` tường minh.
- `kdc`: các hosts KDC cho realm; có thể dùng DNS SRV nếu policy hỗ trợ.
- `dns_lookup_kdc`: cho phép discovery KDC từ DNS tùy implementation.
- `rdns=false`: giảm việc dựa trên reverse DNS lookup trong nhiều client configs, nhưng không thay bước xác định hostname/SPN của toàn bộ browser stack.
- `[domain_realm]`: map DNS domain/hostname tới realm tương ứng.

**Các host chỉ minh họa**. Không dùng `CORP.EXAMPLE` như realm production thật nếu domain khác. KDC discovery có khác biệt giữa Linux MIT Kerberos, Windows LSA và Java; test trên OS/JVM/browser thực tế.

### Java 17 tìm KDC/realm như thế nào?

Oracle Java 17 hỗ trợ:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
~~~

Hoặc hai JVM properties cùng lúc:

~~~text
-Djava.security.krb5.realm=CORP.EXAMPLE
-Djava.security.krb5.kdc=dc01.corp.example
~~~

**Nếu đặt một property `java.security.krb5.realm` hoặc `java.security.krb5.kdc` thì cần đặt cả hai**. Oracle lưu ý chỉ dựa vào hai properties có thể không cung cấp đủ mapping cho **cross-realm**, nên khi có trust nhiều realms vẫn cần `krb5.conf` phù hợp.

Đường cấu hình có thể được JVM load/cache khi Kerberos classes được khởi tạo; không suy rằng sửa file rồi mọi JVM pod lập tức lấy cấu hình mới. Có thể phải restart/reinitialize hợp lệ theo runbook. Không lấy realm/KDC từ request HTTP rồi đổi JVM global properties trong runtime.

## 12. Browser SPNEGO: WWW-Authenticate và Authorization

SPNEGO (Simple and Protected GSS-API Negotiation Mechanism) là cơ chế thương lượng security mechanism trong GSS-API. Với HTTP, flow thường:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Browser (nếu được cấu hình tin website cho Integrated Authentication) lấy hoặc tái sử dụng service ticket, sau đó gửi:

~~~http
GET /private HTTP/1.1
Host: portal.corp.example
Authorization: Negotiate <base64-encoded-GSS-token>
~~~

Spring Security xử lý GSS token, không đọc password người dùng từ header. Trong môi trường AD, Windows SSPI/browser có thể **fallback sang NTLM** khi Kerberos không hoạt động, tùy chính sách client/server. Vì vậy:

**`Authorization: Negotiate` không tự chứng minh ticket Kerberos đã được dùng.** Nếu chính sách yêu cầu Kerberos mutual authentication hoặc không chấp nhận NTLM, phải kiểm mechanism được thương lượng và cấu hình reject fallback theo security policy. Không coi mọi `Negotiate` token đều mang Kerberos service ticket hợp lệ.

### Browser không tự gửi Negotiate tới mọi Internet host

Windows/Edge/Chrome/Firefox có policies về intranet/allowed authentication servers. Tùy hệ điều hành và quản lý browser:

- Site phải nằm trong zone/allowlist cho Integrated Authentication.
- Browser có credential cache/TGT hợp lệ.
- Hostname/SPN được phân giải đúng.
- Proxy không làm mất `WWW-Authenticate` hoặc `Authorization` headers.
- HTTPS/TLS và cookie/session vẫn cần bảo vệ theo threat model.
- Đối với cross-origin calls, không mặc định JavaScript fetch/XHR sẽ gửi Negotiate; CORS/credentials/browser policy là chủ đề riêng.

Đừng ép tất cả trình duyệt hoặc người dùng Internet phải dùng Kerberos. Thông thường SPNEGO phục vụ mạng nội bộ/managed devices, có fallback đăng nhập khác khi đã được chính sách phê duyệt.

## 13. Spring Security Kerberos: các thành phần đúng vai trò

Tài liệu **Spring Security Kerberos** có ví dụ:

| Thành phần | Chức năng |
| --- | --- |
| `SpnegoEntryPoint` | Trả HTTP 401 và `WWW-Authenticate: Negotiate` hoặc chuyển trang fallback theo cấu hình |
| `SpnegoAuthenticationProcessingFilter` | Nhận `Authorization: Negotiate ...`, tạo token request và chuyển cho AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Xác thực **service ticket/SPNEGO token** cho HTTP acceptor |
| `SunJaasKerberosTicketValidator` | Sử dụng Java JAAS/JGSS và **servicePrincipal/keytab** để xác minh ticket |
| `KerberosAuthenticationProvider` | Provider cho cách xác thực với username/password Kerberos (use case khác SPNEGO service-ticket) |
| `KerberosTicketValidator` | Hợp đồng xác minh Kerberos/GSS token |
| `UserDetailsService` | Load user attributes và Spring `GrantedAuthorities` sau khi ticket đã được xác minh |
| `SecurityFilterChain` / `HttpSecurity` | Gắn entry point, filter và authorization rules |

**Hai AuthenticationProviders dễ nhầm:** `KerberosServiceAuthenticationProvider` cho **browser SPNEGO service tickets**, trong khi `KerberosAuthenticationProvider` dùng một `KerberosClient` trong luồng username/password Kerberos. Đừng dùng provider thứ hai để nhận `Authorization: Negotiate` rồi kỳ vọng nó giải mã token bằng keytab.

Trong Spring Security Kerberos 7.1.x, coordinates của các module đã thay đổi so với những bài Spring Security Kerberos 2.x cũ. Cần kiểm version thực và dependency tree, không lấy mẫu Maven từ một blog nhiều năm trước rồi override Spring Security BOM.

## 14. JavaConfig Spring Security chấp nhận SPNEGO

Đây là **ví dụ lắp ghép trong project Spring Security Servlet**, cần các dependencies Kerberos phù hợp, principal/keytab thật, Spring MVC/Servlet và local UserDetailsService. **Nó không chạy độc lập bằng `javac`**.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosTicketValidator;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class SpnegoKerberosSecurityConfig {

    @Bean
    KerberosTicketValidator kerberosTicketValidator(
            @Value("${app.kerberos.service-principal}") String principal,
            @Value("${app.kerberos.keytab-location}") Resource keytab) {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(keytab);
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            KerberosTicketValidator validator,
            UserDetailsService users) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    AuthenticationManager kerberosAuthenticationManager(
            KerberosServiceAuthenticationProvider provider) {
        return new ProviderManager(provider);
    }

    @Bean
    SpnegoAuthenticationProcessingFilter spnegoFilter(
            AuthenticationManager kerberosAuthenticationManager) {
        SpnegoAuthenticationProcessingFilter filter =
                new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(kerberosAuthenticationManager);
        return filter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SpnegoAuthenticationProcessingFilter spnegoFilter)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(
                    new SpnegoEntryPoint("/login")))
            .addFilterBefore(
                    spnegoFilter, BasicAuthenticationFilter.class);
        return http.build();
    }
}
~~~

**Cần thiết để chạy:**

- `UserDetailsService` phải là bean thật ánh xạ Kerberos principal sang local account/authorities, không dùng một service account như user chung.
- `/login` phải có flow fallback phù hợp nếu cấu hình `SpnegoEntryPoint("/login")`; nếu không, có thể tạo vòng lặp hoặc trang không tồn tại.
- Đây là một mẫu điểm tích hợp; authorization, logout, session strategy, CSRF, form login hoặc multi-chain filter matching cần hoàn thiện theo ứng dụng.
- Không bật `setDebug(true)` vô hạn trong production; GSS/JAAS debug có thể tiết lộ principals, infrastructure metadata và thông tin nhạy cảm.
- Các beans/classes phải khớp Spring Security Kerberos/JDK version đã resolve; không trộn Spring Security 7 modules với Spring Security 5-era APIs.

**Hệ quả của một principal sai:** `SunJaasKerberosTicketValidator` cần service principal/keytab phù hợp với **target ticket**. Nếu browser xin `HTTP/portal.corp.example` nhưng validator chờ `HTTP/node01.corp.example@CORP.EXAMPLE`, vấn đề không được giải bằng cách thêm role Spring hoặc thay `UserDetailsService`.

### application.yml tương ứng

~~~yaml
app:
  kerberos:
    service-principal: "HTTP/portal.corp.example@CORP.EXAMPLE"
    keytab-location: "file:/etc/security/keytabs/portal-http.keytab"
~~~

Cấu hình above chỉ ánh xạ hai `@Value`, **không** tự tạo keytab hoặc đăng ký SPN. Một số môi trường/phiên bản dùng principal dạng `HTTP/portal.corp.example` và lấy realm mặc định; để tránh mơ hồ, ưu tiên principal đầy đủ khi keytab/JGSS implementation hỗ trợ và đã được kiểm cùng KDC.

### Spring Security Kerberos dependencies theo phiên bản

Ví dụ **Spring Security Kerberos 7.1.x** từ reference Spring (dependency versions do BOM quản lý):

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
  </dependency>
</dependencies>
~~~

Đây là **Maven fragment**, không phải toàn bộ pom.xml. Dòng 7.1.x được tài liệu Spring mô tả với JDK 17 và Spring Security/Framework phiên bản tương ứng. Trong một hệ thống Spring Boot 3/Security 6 có thể cần coordinates/version tương ứng dòng Kerberos cũ; **không thay groupId hoặc tăng version theo cảm tính**.

## 15. Local user mapping sau Kerberos authentication

Một Kerberos ticket xác minh `lan@CORP.EXAMPLE` **không tự chứng minh Lan là admin**. `KerberosServiceAuthenticationProvider` sử dụng `UserDetailsService` để lấy authorities sau khi xác minh. Ví dụ policy:

~~~text
Verified Kerberos principal:
  lan@CORP.EXAMPLE

Identity-link store:
  (trustedRealm=CORP.EXAMPLE, principal=lan) -> localUserId=u-1007

Local status:
  ACTIVE

Local roles:
  ROLE_REPORT_VIEWER

Request to /admin:
  DENY unless local grant exists
~~~

Một hệ thống nhiều realms có thể có `lan@CORP.EXAMPLE` và `lan@PARTNER.EXAMPLE` là hai người khác nhau. **Không chỉ lấy phần trước `@` rồi tự gộp account.** Khóa identity link nên chứa realm (hoặc immutable identifier mà directory/trust contract bảo đảm).

Các bước authorization an toàn:

1. Ticket được verify bằng keytab đúng và KDC/trust semantics phù hợp.
2. Ghi nhận principal đã xác thực và trusted realm.
3. Kiểm local user enabled/locked/offboarding.
4. Map principal (kèm realm) vào identity nội bộ theo policy.
5. Chỉ cấp authorities đã được phê duyệt, không dựa vào tên account hay `memberOf` không xác minh.
6. Áp tenant/object-level authorization cho từng request.
7. Quản lý session lifetime, role refresh và local logout theo yêu cầu.

**SPNEGO authentication không thay HTTPS/TLS.** Kerberos chứng minh principal, trong khi HTTPS bảo vệ HTTP payload/cookies và chống downgrade/MITM theo threat model.

## 16. Browser → reverse proxy → Spring: public SPN và backend keytab

Giả sử kiến trúc:

~~~text
User Browser
   |
   | https://portal.corp.example/
   v
HTTPS Load Balancer (public virtual host)
   |
   +----> Spring pod A: portal-app-a.internal:8080
   |
   +----> Spring pod B: portal-app-b.internal:8080

Public SPN:
  HTTP/portal.corp.example

AD SPN owner:
  CORP\svc_portal

Spring acceptor principal:
  HTTP/portal.corp.example@CORP.EXAMPLE
~~~

**Browser thường xin vé cho hostname public của URL, không tự xin vé cho pod name**. Do vậy backend apps phải có credentials chấp nhận **public HTTP service principal**. Với nhiều replicas dùng chung service keytab, phải có secret distribution/rotation an toàn; keytab không phải public config có thể bake vào image.

Reverse proxy cần chuyển nguyên HTTP `Authorization: Negotiate` đến backend nếu nó chỉ pass through. Nếu reverse proxy **tự terminate Kerberos** và xây một identity assertion/header để gửi backend, thì **trust boundary đã thay đổi**: Spring backend không còn là Kerberos acceptor; phải xác thực ingress/proxy channel và chặn client Internet tự gửi identity headers như `X-Remote-User`. Không được đọc username header chưa được proxy kiểm và coi đó là Kerberos login.

### DNS alias/multi-URL

Nếu cùng ứng dụng phục vụ `portal.corp.example` và `reports.corp.example`, mỗi hostname mà browser thực sự sử dụng có thể cần SPN tương ứng, đăng ký trên owner account đúng. Một keytab/acceptor có thể cần nhiều principals hoặc host-specific credentials theo framework; không tự giả định keytab chỉ chứa một HTTP principal sẽ accept mọi alias.

### Kerberos channel binding và HTTPS

Một số Windows Extended Protection/Channel Binding Token (CBT) policies ràng buộc authentication token với TLS channel. Nếu TLS terminate ở proxy rồi GSS token chuyển backend, có thể xảy ra channel-binding mismatch tùy phiên bản/chính sách. **Không sửa bằng cách vô hiệu hóa Extended Protection toàn domain** chỉ vì một lỗi cấu hình: cần xem topology, phiên bản JVM/SSPI, proxy TLS termination, CBT support và phương án theo policy bảo mật.

## 17. KDC discovery, DNS SRV và firewall

KDC discovery có thể đến từ AD/DC Locator, DNS SRV hoặc `krb5.conf`. Các bản ghi kiểu:

~~~dns
_kerberos._tcp.corp.example. IN SRV 0 100 88 dc01.corp.example.
_kerberos._tcp.corp.example. IN SRV 10 100 88 dc02.corp.example.
_kerberos._udp.corp.example. IN SRV 0 100 88 dc01.corp.example.
~~~

Đây là **DNS ví dụ**, không nhất thiết là records mà mọi Windows/Java client sẽ hỏi chính xác như nhau. Port **88/TCP và UDP** là chuẩn phổ biến cho KDC. Tùy environment còn cần DNS, directory và những cổng AD khác để domain join/discovery.

Nếu `kinit` trên Linux thành công nhưng browser vẫn không SSO, nguyên nhân có thể là browser policy/SPN/HTTP header chứ không phải KDC reachability. Nếu browser gửi Negotiate nhưng Spring fail, cần kiểm keytab/KVNO/enctype và service principal. **Chẩn đoán theo đúng bước** thay vì mở toàn bộ firewall.

## 18. Công cụ kiểm tickets trên client

Trong môi trường Linux/MIT Kerberos được quản trị:

~~~bash
# Nhận TGT cho user test trong realm:
kinit lan@CORP.EXAMPLE

# Xem credentials cache:
klist

# Yêu cầu service ticket đúng HTTP principal:
kvno HTTP/portal.corp.example@CORP.EXAMPLE

# Xem keytab phía acceptor (không in secret keys):
klist -kte /etc/security/keytabs/portal-http.keytab
~~~

Các lệnh này chỉ chạy ở máy có Kerberos client/keytab/KDC thật. **Không có stdout cố định** và sẽ fail nếu realm/host/cert/username minh họa chưa được thay. `kinit` có thể yêu cầu password hoặc phương thức xác thực khác; không ghi mật khẩu trong command line. `kvno` chỉ chứng minh KDC có thể cấp service ticket cho principal yêu cầu, **không tự chứng minh Spring backend có keytab đúng để giải vé**.

Trong môi trường Windows domain:

~~~powershell
# Quan sát ticket cache (read-only):
klist

# Yêu cầu ticket service cụ thể trong môi trường đã join domain:
klist get HTTP/portal.corp.example

# Kiểm SPN mapping:
setspn -Q HTTP/portal.corp.example

# Kiểm duplicates:
setspn -X
~~~

Có thể cần quản trị viên hoặc công cụ RSAT. Chạy chẩn đoán không nên thay SPN/account credential tự động. Khi test alias, thay hostname trong lệnh bằng **tên thật browser truy cập**.

## 19. Các lỗi hay gặp: xác định tầng trước khi sửa

| Lỗi hoặc triệu chứng | Tầng khả nghi | Diễn giải/giải pháp |
| --- | --- | --- |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC/SPN | Không tìm được service principal; kiểm `setspn -Q`, hostname/realm |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | AD/SPN | Trùng owner; kiểm `setspn -X` và quản trị lại mapping |
| `KRB_AP_ERR_MODIFIED` | Service acceptor/keys | Ticket không giải được; kiểm owner, keytab, password, KVNO, enctype |
| `KDC_ERR_ETYPE_NOSUPP` | Encryption policy | Client/KDC/service không có enctype chung; kiểm AES/RC4 policy |
| `KRB_AP_ERR_SKEW` | Clock | Thời gian giữa client/KDC/service lệch vượt tolerance; đồng bộ NTP |
| `Clock skew too great` | Clock | Kiểm đồng hồ hệ thống, không vô hiệu replay protection |
| `Cannot find KDC for realm` | DNS/krb5.conf | Kiểm realm, SRV records, network tới KDC port 88 |
| `Server not found in Kerberos database` | SPN/realm | Không tồn tại target service principal hoặc realm mapping sai |
| `Message stream modified` / checksum fail | Keytab/key | Key sai hoặc ticket bị thay; kiểm KVNO/key owner, không disable integrity |
| `Integrity check on decrypted field failed` | Keytab/enctype | File keytab khác KDC/service account key |
| HTTP 401 lặp lại | Browser/Negotiate | Không gửi ticket, keytab fail, fallback NTLM, filter chain hoặc DNS |
| Browser chỉ gửi NTLM | Mechanism/policy | Kerberos không lấy được SPN ticket hoặc policy không đúng; đừng lầm là Kerberos |
| Spring 403 sau Negotiate | Authorization | Kerberos auth có thể thành công nhưng local user thiếu authorities |
| Login đúng ở node A, fail ở node B | Keytab/rollout | Hai nodes có keytab/KVNO hoặc realm config khác |
| Truy cập alias fail, FQDN chính chạy | Host/SPN | Thiếu alias SPN hoặc browser canonicalize hostname khác |
| Sau đổi mật khẩu service account thì fail | Key rollover | Keytab cũ, KVNO mismatch; rotate đồng bộ |
| SPNEGO lỗi khi qua proxy HTTPS | Header/CBT | Proxy strip Negotiate, TLS channel binding, trust topology |
| Browser ngoài domain không silent SSO | Client setup | Không có domain session/TGT, trusted intranet settings thiếu |
| User role bị nhầm giữa realms | Identity mapping | Local principal mapping bỏ realm |
| `GSSException: Defective token detected` | SPNEGO parser/transport | Token bị cắt, mechanism không hỗ trợ hoặc key/encoding mismatch |

**Không mọi lỗi 401 là “SPN sai”.** Kiểm xem browser có gửi `Authorization: Negotiate` không, KDC đã phát ticket đúng SPN chưa, server có keytab đúng không, và Spring có thật sự nhận GSS token qua filter chain không.

### Cách debug theo thứ tự ít xâm lấn

1. Ghi nhận **public browser hostname**, protocol HTTPS và authentication challenge.
2. Kiểm browser policy có cho Negotiate tới host không.
3. Kiểm TGT và service ticket từ client với `klist`/`kvno`.
4. Tra SPN trong AD bằng `setspn -Q`; kiểm duplicate bằng `-X`.
5. Xác nhận SPN owner account, keytab principal, KVNO và enctype đã triển khai.
6. Kiểm Java `krb5.conf`/KDC discovery, clock skew và DNS.
7. Kiểm reverse proxy có giữ `WWW-Authenticate`, `Authorization` hay tự terminate auth.
8. Kiểm `SpnegoAuthenticationProcessingFilter`, provider, validator và local user mapping.
9. Chạy E2E test với user có role thấp trước, kiểm tenant/resource permissions.
10. Chỉ khi cần mới bật Kerberos debug ngắn hạn trên staging, lọc logs an toàn.

## 20. Keytab, encryption types và bảo vệ secrets

Service account keys được dùng trong Kerberos mã hóa/vé. Những điểm vận hành:

- Tránh **DES** và **RC4** cũ theo security baseline; ưu tiên AES enctypes tương thích AD/KDC/JDK, kiểm chính sách thực tế trước migration.
- Không đọc tên thuật toán dạng `aes256-cts-hmac-sha1-96` rồi tự kết luận có thể tùy tiện chuyển sang cipher HTTP/TLS khác; đây là **Kerberos enctype name**, không phải TLS cipher suite.
- Mỗi service account cần least privilege, không cấp Domain Admin để SPNEGO.
- Keytab phải được mount chỉ cho service process cần dùng, permissions chặt và không vào Git/image public.
- Key rotation cần đồng bộ KDC account credential/KVNO với **tất cả** Spring nodes.
- Không in key bytes vào logs; `klist -kte` thường chỉ xem metadata, nhưng vẫn chứa principal/infra names cần được bảo vệ.
- Hạn chế reuse cùng service keytab trên nhiều hệ thống không liên quan để thu nhỏ blast radius.
- Đánh giá replay cache, ticket lifetimes và clock synchronization; không tắt Kerberos replay protection để vượt lỗi ngẫu nhiên.

**Kerberos service ticket không phải Bearer JWT**. Không copy base64 `Negotiate` token qua chat/log hoặc tái sử dụng như một API key vĩnh viễn; dữ liệu xác thực/GSS context phải được xử lý bởi thư viện chuẩn.

## 21. Kerberos double hop và Constrained Delegation

SPNEGO cho phép browser xác thực **tới Portal**, nhưng điều đó **không tự có nghĩa** Portal có thể dùng danh tính user để truy cập SQL/SMB/HTTP service thứ hai.

Ví dụ:

~~~text
Browser user Lan
   | HTTP/portal.corp.example (Kerberos ticket)
   v
Spring Portal
   | muốn truy cập HTTP/reports-backend.corp.example as Lan
   v
Downstream service
~~~

**Đây là bài toán delegation/double hop**. Với Active Directory có Kerberos Constrained Delegation (KCD)/S4U flows trong điều kiện và quyền được admin cấu hình. Nó không hoạt động chỉ bằng cách chuyển tiếp token browser hoặc sao chép username Lan vào một HTTP header.

**Các quyền cần giới hạn**:

- Service account nào được phép delegation?
- Được delegate tới **SPN đích nào**?
- User/tenant nào có thể được impersonate theo policy?
- Nếu có protocol transition/S4U, điều kiện an ninh có được kiểm?
- Downstream service có thực sự validate Kerberos ticket mới không?

Không bật **unconstrained delegation** để giải lỗi thông thường. Nó mở rộng đáng kể quyền service account nếu bị xâm nhập. Trong multi-tier web apps, ưu tiên thiết kế có identity propagation rõ, least privilege và audit đầy đủ.

## 22. Java 17 độc lập: mô phỏng khớp realm–SPN–keytab

Chương trình dưới đây giúp học sinh hiểu một phép kiểm **cấu hình logic**: hostname public quyết định SPN kỳ vọng, realm gắn vào principal, và service principal mà keytab được cấu hình phải khớp. Nó còn mô phỏng một SPN bị đăng ký trên hai owners.

**Quan trọng:** mã này chỉ làm việc với **chuỗi**. Nó **không** thực hiện Kerberos AS/TGS/AP exchanges, không liên hệ KDC/AD, không kiểm keytab bytes, không verify GSS ticket, không kiểm DNS canonicalization thực, không quyết định IAM role. Chương trình chỉ hỗ trợ tư duy chẩn đoán.

Tạo file **`KerberosSpnBindingDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class KerberosSpnBindingDemo {

    static String expectedHttpSpn(String browserHost) {
        return "HTTP/" + browserHost.toLowerCase(Locale.ROOT);
    }

    static String fullServicePrincipal(String spn, String realm) {
        return spn + "@" + realm;
    }

    static String checkBinding(
            String browserHost,
            String registeredSpn,
            String keytabPrincipal,
            String realm) {

        String expectedSpn = expectedHttpSpn(browserHost);
        if (!expectedSpn.equalsIgnoreCase(registeredSpn)) {
            return "DENY: browser SPN is not registered";
        }
        String expectedPrincipal =
                fullServicePrincipal(expectedSpn, realm);
        if (!expectedPrincipal.equalsIgnoreCase(keytabPrincipal)) {
            return "DENY: keytab principal mismatch";
        }
        return "OK: names align";
    }

    public static void main(String[] args) {
        String realm = "CORP.EXAMPLE";
        String host = "portal.corp.example";
        String spn = "HTTP/portal.corp.example";
        String keytabName = "HTTP/portal.corp.example@CORP.EXAMPLE";

        Map<String, List<String>> owners = Map.of(
                "HTTP/portal.corp.example", List.of("CORP\\svc_portal"),
                "HTTP/legacy.corp.example",
                List.of("CORP\\svc_old", "CORP\\svc_other"));

        System.out.println("Realm: " + realm);
        System.out.println("Browser SPN: " + expectedHttpSpn(host));
        System.out.println("Full principal: "
                + fullServicePrincipal(spn, realm));

        System.out.println("Correct binding: "
                + checkBinding(host, spn, keytabName, realm));

        System.out.println("Wrong alias: " + checkBinding(
                host, "HTTP/node01.corp.example", keytabName, realm));

        System.out.println("Wrong keytab: " + checkBinding(
                host, spn, "HTTP/node01.corp.example@CORP.EXAMPLE",
                realm));

        System.out.println("Portal SPN owners: "
                + owners.get(spn).size());

        System.out.println("Legacy duplicate: "
                + (owners.get("HTTP/legacy.corp.example").size() > 1));

        System.out.println("HTTP over TLS still uses HTTP SPN: "
                + expectedHttpSpn(host).startsWith("HTTP/"));
    }
}
~~~

Chạy bằng JDK 17:

~~~bash
javac KerberosSpnBindingDemo.java
java KerberosSpnBindingDemo
~~~

**Stdout chính xác:**

~~~text
Realm: CORP.EXAMPLE
Browser SPN: HTTP/portal.corp.example
Full principal: HTTP/portal.corp.example@CORP.EXAMPLE
Correct binding: OK: names align
Wrong alias: DENY: browser SPN is not registered
Wrong keytab: DENY: keytab principal mismatch
Portal SPN owners: 1
Legacy duplicate: true
HTTP over TLS still uses HTTP SPN: true
~~~

### Bài học rút ra từ chương trình

- Browser dùng **hostname truy cập** để tạo SPN HTTP trong ví dụ đơn giản; reverse proxy không tự đổi sang node name.
- Realm được ghép vào principal đầy đủ; không nhầm với DNS record.
- SPN đúng nhưng keytab khác principal vẫn sai.
- Một SPN có **một owner** theo mô hình; duplicate trên AD forest là lỗi cần điều tra.
- HTTPS **không đổi service class HTTP**.

**Giới hạn cố ý:** `checkBinding` so chuỗi case-insensitive để dạy khái niệm, **không** thay Kerberos GSS-API hoặc AD SPN lookup. Nó không biết keytab KVNO, AES key, service account password, canonical DNS và Kerberos protocol. Đừng kết luận production an toàn chỉ vì output “OK”; phải test bằng KDC và Java acceptor thật.

## 23. Test Matrix để kiểm tích hợp Spring Kerberos/SPNEGO

| Nhóm | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Realm | `default_realm=CORP.EXAMPLE` và KDC reachable | Client có thể nhận TGT |
| KDC | DNS SRV và fallback DC đúng | KDC được tìm và phục vụ AS/TGS |
| User principal | `lan@CORP.EXAMPLE` hợp lệ | AS phát TGT theo policy |
| Unknown user | Principal không tồn tại | AS từ chối |
| SPN | `HTTP/portal.corp.example` được đăng ký đúng account | KDC cấp service ticket |
| Missing SPN | Không có record `HTTP/portal...` | KDC từ chối service request |
| Duplicate SPN | Hai AD accounts sở hữu cùng SPN | Phải phát hiện và sửa trước production |
| Wrong owner | SPN trỏ account khác keytab | Spring acceptor từ chối ticket |
| Keytab | Đúng principal/KVNO/enctype | JGSS ticket validation thành công |
| Stale keytab | Account password đã rotate | Fail closed, yêu cầu rollout keytab mới |
| Public hostname | Browser vào `portal.corp.example` | Browser xin HTTP/public SPN |
| Alias | Browser vào `reports.corp.example` | Đúng alias SPN và keytab, hoặc từ chối có kiểm soát |
| HTTPS | Browser sử dụng HTTPS Portal | TLS đúng, SPN vẫn HTTP/host |
| Browser policy | Managed intranet device | Negotiate header được gửi khi policy cho phép |
| No credential | External unmanaged browser | Fallback login hợp lệ, không 401 loop |
| Header proxy | Proxy pass-through | `Authorization: Negotiate` đến đúng filter |
| Reverse proxy terminates auth | Trusted identity header architecture | Backend không tin header từ Internet |
| Provider | `KerberosServiceAuthenticationProvider` | Verify ticket rồi mới load user details |
| Wrong realm | `lan@PARTNER.EXAMPLE` chưa trusted | Không gộp với `lan@CORP.EXAMPLE` |
| Local user disabled | Kerberos ticket đúng | Local app vẫn deny |
| Roles | `ROLE_ADMIN` không có trong local policy | HTTP 403 ở protected admin route |
| Clock skew | Client/KDC/service clock lệch | Kerberos từ chối theo policy |
| Enctype | Keytab chỉ chứa enctype không khớp KDC | Authentication fail, phải sửa key policy |
| NTLM fallback | Browser không dùng Kerberos | Không giả nhận là SPNEGO Kerberos success |
| Delegation | App gọi downstream với user identity | Chỉ được phép sau KCD/S4U policy và downstream validation |
| Two replicas | Pods A/B có cùng approved credentials | Cả hai chấp nhận ticket đúng |
| Key rotation | Tăng KVNO theo kế hoạch | Không gián đoạn ngoài thời gian chuyển đổi dự kiến |

**Chỉ dùng một chương trình Java kiểm chuỗi không chứng minh SPNEGO hoạt động.** Integration test phải chạy với test KDC/domain account, browser/HTTP client được quản trị, service principal/keytab thật, và Spring Security application đã wiring đúng. Cần có cả negative tests với wrong SPN/keytab/KVNO và mixed-realm users.

## 24. Quy trình triển khai vận hành an toàn

1. **Chốt public URL** của ứng dụng, ví dụ `https://portal.corp.example`, không dựa vào pod DNS.
2. **Chốt realm/KDC** và mô hình domain trust do IAM/AD owner quản trị.
3. **Tạo/chọn service account** với least privilege, không cấp domain admin.
4. **Tra SPN** trước bằng `setspn -Q`/`-X`, phân biệt service class và hostname.
5. **Đăng ký duy nhất SPN** `HTTP/portal.corp.example` lên account đúng theo change request.
6. **Tạo/rotate keytab** chính thức, kiểm principal, KVNO và enctypes.
7. **Phân phối keytab** qua secret management cho Spring nodes với file permission chặt.
8. **Cấu hình krb5.conf/JVM** đúng realm và KDC trong container/VM thực.
9. **Bật Spring Kerberos filter/provider/validator** với servicePrincipal/keytab đúng, không dùng password provider cho SPNEGO.
10. **Cấu hình browser policy** cho Negotiate tại hostname public; dùng HTTPS và proxy headers an toàn.
11. **Ánh xạ principal có realm** sang local user và authorities, kiểm disabled accounts/tenants.
12. **Test AS/TGS/AP** bằng `kinit/klist/kvno`, browser E2E và Spring logs được bảo vệ.
13. **Test negative cases** wrong SPN, duplicate, stale KVNO, user từ realm khác, NTLM fallback.
14. **Giám sát** lỗi KDC, 401 loop, keytab rotation, authentication latency, account lockouts.
15. **Có runbook rollback** keytab/account/SPN và lịch secret rotation với IAM/security team.

### Những điều không nên làm

- Không bật `permitAll` cho toàn ứng dụng khi filter fail.
- Không đọc username từ header `X-Remote-User` không xác minh.
- Không cấp role admin chỉ vì principal thuộc `@CORP.EXAMPLE`.
- Không copy keytab vào Git hoặc Docker image được chia sẻ.
- Không tắt replay cache, encryption protection hoặc Extended Protection tùy tiện.
- Không bật unconstrained delegation để giải lỗi double hop.
- Không dùng NTLM fallback như bằng chứng Kerberos ticket đã được xác minh.
- Không tự thay SPN owner nhiều account trong production khi chưa có kế hoạch key rollover.
- Không đồng nhất user principal, SPN, UPN, DNS host và TLS certificate SAN.

## 25. Hỏi nhanh — đáp ngắn

**Hỏi:** Vì sao HTTPS Portal vẫn cần SPN `HTTP/portal.corp.example` thay vì `HTTPS/portal.corp.example`?

**Đáp:** `HTTP` là **Kerberos service class** cho HTTP authentication, độc lập việc tầng transport có TLS hay không. HTTPS bảo vệ kênh, không đổi SPN class thông thường.

**Hỏi:** KDC có phải là web server nhận `Authorization: Negotiate` không?

**Đáp:** Không. KDC phát TGT/service ticket, còn **web server/Spring acceptor** nhận và kiểm token bằng keytab.

**Hỏi:** Một user có `lan@CORP.EXAMPLE` thì server keytab phải chứa principal đó không?

**Đáp:** Không. Keytab của SPNEGO service thường chứa **HTTP service principal**; user principal/TGT thuộc phía client/KDC, không phải service keytab.

**Hỏi:** `HTTP/portal.corp.example` và `CORP\svc_portal` là một thứ?

**Đáp:** Không. SPN là định danh service; AD account sở hữu SPN/long-term key. KDC dùng mapping để cấp ticket cho đúng account.

**Hỏi:** SPN có cần gắn `@CORP.EXAMPLE` khi chạy setspn không?

**Đáp:** Trong AD `setspn` thường đăng ký giá trị `HTTP/portal.corp.example` trong `servicePrincipalName`. Trong Kerberos/JAAS/keytab có thể biểu diễn đầy đủ `HTTP/portal.corp.example@CORP.EXAMPLE`. Đừng tự ghép realm vào `setspn -S` theo phong cách keytab nếu AD không yêu cầu.

**Hỏi:** Vì sao `setspn -Q` tìm thấy nhưng Spring vẫn báo `KRB_AP_ERR_MODIFIED`?

**Đáp:** Có thể SPN gắn **sai account**, keytab không cùng key/KVNO/enctype, account password bị đổi hoặc acceptor đang chờ principal khác.

**Hỏi:** Có thể xóa mọi SPN trùng và đăng ký lại trong giờ cao điểm không?

**Đáp:** Không. SPN liên quan hệ thống khác; xác minh owner đúng và thực hiện migration/rotation với IAM change control.

**Hỏi:** Browser trả `Authorization: Negotiate` có chắc là Kerberos không?

**Đáp:** Không. SPNEGO có thể thương lượng cơ chế khác như NTLM theo client/server policy; phải kiểm mechanism thực và validator không chấp nhận fallback không mong muốn.

**Hỏi:** Domain CORP đã xác thực Kerberos, có tự động có `ROLE_ADMIN` không?

**Đáp:** Không. Spring cần local role/tenant authorization policy riêng.

**Hỏi:** Cùng web app có thêm hostname alias, chỉ thêm DNS là đủ không?

**Đáp:** Không chắc. Kiểm SPN mà browser thực sự xin, AD owner, keytab/acceptor, TLS SAN và proxy routing.

## 26. Tài liệu chính thức và tham khảo

1. [RFC 4120 — The Kerberos Network Authentication Service (V5)](https://www.rfc-editor.org/rfc/rfc4120): realm, principal, KDC, AS/TGS exchanges, tickets và security model.
2. [Oracle Java 17 — Kerberos Requirements](https://docs.oracle.com/en/java/javase/17/security/kerberos-requirements.html): `krb5.conf`, `java.security.krb5.realm` và `java.security.krb5.kdc`.
3. [Oracle Java 17 — KerberosPrincipal Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/javax/security/auth/kerberos/KerberosPrincipal.html): `KRB_NT_PRINCIPAL`, `KRB_NT_SRV_HST` và realm/name types.
4. [Spring Security Kerberos — Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): dependency coordinates và compatibility của Spring Security Kerberos 7.1.x.
5. [Spring Security Kerberos — Spring and Spring Security Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator` và keytab.
6. [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): nhận `Negotiate` token và AuthenticationManager.
7. [Microsoft Learn — Configure Service Principal Name](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/how-to-configure-spn): AD SPN format, ownership và nguyên tắc mapping.
8. [Microsoft Learn — setspn command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setspn): `-Q`, `-X`, `-L` và `-S`, kiểm duplicate SPN.
9. [Microsoft Learn — KRB_AP_ERR_MODIFIED and Wrong SPN Account](https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-event-4-access-denied): vấn đề KDC cấp ticket bằng account khác với service acceptor.
10. [Microsoft Entra — Troubleshoot Kerberos Constrained Delegation](https://learn.microsoft.com/en-us/entra/identity/app-proxy/application-proxy-back-end-kerberos-constrained-delegation-how-to): KCD, DNS, duplicate SPN và dịch vụ đích.
11. [MIT Kerberos Documentation](https://web.mit.edu/kerberos/krb5-latest/doc/): `kinit`, `klist`, `kvno`, krb5.conf, service principals và keytabs.
12. [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): HTTP `WWW-Authenticate: Negotiate` và GSS token exchange.

**Ghi nhớ cuối bài:** **Realm** xác định miền tin cậy Kerberos; **KDC** cấp TGT và service ticket; **principal** định danh user hoặc service; **SPN** ràng buộc hostname/service class với account/key đúng. Với Spring Security SPNEGO, chuỗi **browser hostname → HTTP SPN → AD owner/KDC ticket → service keytab → GSS validation → local authorities** phải nhất quán. Không được đánh đồng có thể phân giải DNS hoặc nhận HTTP 401 với việc ticket Kerberos đã được xác minh và người dùng được cấp quyền.