# KerberosServiceAuthenticationProvider và xác minh ticket của dịch vụ

> **Chủ đề:** Spring Security – federation. **Nhóm:** Tích hợp Kerberos. Bài Knowledge này giải thích cách Spring Security xử lý HTTP SPNEGO/Negotiate với `KerberosServiceAuthenticationProvider`, dùng `KerberosTicketValidator` và **service keytab** để xác minh Kerberos **Service Ticket**, rồi nạp `UserDetails` và `GrantedAuthorities` để cấp phiên ứng dụng. Hướng dẫn tập trung vào Java 17+, ứng dụng Servlet và Windows Active Directory hoặc KDC Kerberos tương thích. Ví dụ tích hợp chọn Spring Security Kerberos **2.2.x với Spring Security 6.x**; với Spring Security 7.x phải dùng module/toạ độ dependency tương ứng, không pha hai dòng phiên bản.

## 1. Mục tiêu và giới hạn

Sau bài này, người học có thể:

1. Phân biệt `KerberosServiceAuthenticationProvider` với `KerberosAuthenticationProvider`; xác định đâu là cơ chế **server xác minh service ticket** và đâu là cơ chế **client gửi username/password qua Kerberos client**.
2. Mô tả đường đi từ browser nhận HTTP `401 WWW-Authenticate: Negotiate`, xin ticket từ **KDC**, gửi `Authorization: Negotiate ...`, đến `SpnegoAuthenticationProcessingFilter` và `KerberosServiceAuthenticationProvider`.
3. Giải thích quan hệ giữa **SPN** (Service Principal Name), **keytab**, **realm**, **KDC**, **TGT**, **TGS-REP**, **service ticket**, **authenticator**, **GSS-API/JAAS** và **SecurityContext**.
4. Cấu hình `SunJaasKerberosTicketValidator` bằng **đúng service principal và keytab**, thay vì lấy mật khẩu/ticket từ HTTP client rồi tự tin.
5. Hiểu provider chỉ nhận về **username** sau khi ticket hợp lệ; `UserDetailsService`/dịch vụ quyền nội bộ phải xác định account, tenant, disabled status và authorities.
6. Bảo vệ chương trình khỏi SPN sai, keytab/KVNO/etype lệch, ticket hết hạn, clock skew, replay, token giả, NTLM fallback không mong muốn, unauthorized principal, session fixation và sai scope dữ liệu.
7. Cấu hình Spring `SecurityFilterChain`, `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` và session repository một cách minh bạch.
8. Đọc đúng network trace, chạy `klist`/`kvno`/`curl --negotiate` trong môi trường test, kiểm tra keytab mà **không log ticket hoặc private service keys**.
9. Phân biệt **đăng nhập web bằng SPNEGO** với **API Kerberos delegation** và các cơ chế khác như CAS, SAML và OIDC.
10. Viết kế hoạch tích hợp và ma trận QA positive/negative có thể kiểm chứng trong domain/lab thực sự.

**Nguyên tắc quan trọng:** Người dùng được xác thực **chỉ sau khi server chứng minh có thể xử lý đúng Kerberos service token bằng key của SPN đã tin và nhận danh tính đã được KDC chứng nhận**. Không bao giờ chỉ cần chuỗi `Authorization: Negotiate ...`, chuỗi username hoặc tiền tố của một token rồi tạo `Authentication`.

## 2. Từ TGT đến Service Ticket: hai bước không được nhầm

Kerberos có ba tác nhân chính:

| Tác nhân | Vai trò |
| --- | --- |
| **Client** | Browser/process chạy trong danh tính người dùng, sở hữu credentials/TGT phù hợp |
| **KDC** | Key Distribution Center, thường gồm Authentication Service (AS) và Ticket-Granting Service (TGS), do Active Directory hoặc Kerberos realm cung cấp |
| **Service** | Ứng dụng Spring có service principal dạng `HTTP/web.example.org@EXAMPLE.ORG` và private key tương ứng trong keytab |

Các loại chứng cứ:

- **TGT (Ticket-Granting Ticket):** được cấp sau khi người dùng xác thực với AS/KDC; giúp client xin service tickets từ TGS mà không nhập lại password cho mỗi service.
- **Service Ticket / TGS ticket:** được TGS cấp cho **một service principal cụ thể**. Phần nhạy cảm của ticket được bảo vệ bằng khóa của service, không phải password của user được ứng dụng biết.
- **Authenticator:** dữ liệu xác thực do client tạo kèm với ticket trong `AP-REQ`, dùng session key/chứng cứ thời gian để chứng minh quyền sở hữu khóa phiên và chống replay theo policy.
- **SPNEGO token:** lớp negotiation mechanism trong HTTP `Negotiate` có thể mang Kerberos AP-REQ và trao đổi GSS tokens; token không phải username JSON hoặc bearer JWT.
- **Keytab:** file chứa service keys/KVNO/etype dùng bởi app server để accept Kerberos ticket. Đây là **secret đặc quyền**, không được phục vụ qua HTTP, đưa vào Docker image công khai hoặc commit repository.

### 2.1. Thời điểm KDC xuất hiện

```text
User workstation/browser          KDC                    Spring Service
      |                             |                            |
      |-- AS-REQ (nếu cần TGT) ----->|                            |
      |<-- AS-REP / TGT ------------|                            |
      |                             |                            |
      |-- TGS-REQ for HTTP/web ---->|                            |
      |<-- TGS-REP / Service Ticket-|                            |
      |                             |                            |
      |    HTTP GET /secure         |                            |
      |--------------------------------------------------------->|
      |<--- 401 WWW-Authenticate: Negotiate ---------------------|
      |    Authorization: Negotiate <base64 SPNEGO/GSS token>    |
      |--------------------------------------------------------->|
      |                        Spring SPNEGO filter               |
      |                        Provider + JAAS/GSS acceptor       |
      |                        decrypt/check token via keytab    |
      |<--- 200 / session cookie if authorized ------------------|
```

Trên thực tế, client có thể đã cache ticket cho SPN trước request hoặc nhận challenge rồi mới xin ticket; thứ tự network có thể thay đổi. **KDC không nhất thiết được gọi mỗi lần Spring server xác minh một request**: acceptor có thể dùng **service keytab** và quy tắc GSS/Kerberos tại chỗ; không diễn giải việc không thấy KDC traffic là “đã bỏ qua xác minh”.

Một client có thể chưa có TGT, không có quyền lấy TGS ticket hoặc không dùng browser integrated authentication, khi đó không có Negotiate ticket hợp lệ để gửi. Server nên trả challenge/fallback đã định nghĩa, không chấp nhận plain username.

### 2.2. Ví dụ Service Principal Name

Đối với website `https://web.example.org/secure`, SPN thường là:

```text
HTTP/web.example.org@EXAMPLE.ORG
```

- `HTTP` là service class thông dụng của HTTP Negotiate/Kerberos, không phải protocol scheme `http://`.
- `web.example.org` phải phù hợp **hostname public** client thực sự dùng để tạo Kerberos target name, xét DNS/canonicalization theo môi trường.
- `EXAMPLE.ORG` là Kerberos realm; trong AD thường liên quan domain nhưng có thể có quy tắc mapping/cross-realm trust.
- **SPN dùng cho HTTP không gắn trực tiếp với đường dẫn `/secure` hay port HTTP** theo cách build thông thường. Đừng tự sinh `HTTP/web.example.org:8443` trừ khi client/KDC/cơ chế của bạn đã được cấu hình sử dụng mô hình SPN ấy.
- `HTTP/web.example.org@EXAMPLE.ORG` khác `HTTP/web-internal@EXAMPLE.ORG`. Nếu browser gọi public alias nhưng service chỉ có keytab của host backend, có thể thất bại.
- Với nhiều aliases, phải đăng ký/đối chiếu đúng SPN owner/target key, **không** cho phép một service tự khai nhận mọi SPN.

**SPN đăng ký trên directory account và keytab chứa key của account đó phải nhất quán**. Trong Active Directory, việc SPN trùng hoặc đặt trên sai account gây lỗi cấp/giải mã ticket; kiểm SPN bằng công cụ domain admin và quản lý thông qua change ticket.

## 3. KerberosServiceAuthenticationProvider thực sự làm gì?

`KerberosServiceAuthenticationProvider` nằm trong:

```text
org.springframework.security.kerberos.authentication
    .KerberosServiceAuthenticationProvider
```

Đây là một Spring `AuthenticationProvider` thuộc module Kerberos extension. Theo Javadoc chính thức, nó:

1. Nhận `KerberosServiceRequestToken` có **Kerberos service ticket hoặc SPNEGO token** từ authentication manager.
2. Nhờ `KerberosTicketValidator` kiểm nội dung token theo cơ chế JAAS/GSS phù hợp JDK/OS.
3. Nếu ticket có thể được accept hợp lệ cho service, nhận thông tin **principal name** từ kết quả `KerberosTicketValidation`.
4. Dùng `UserDetailsService` tìm local user và `GrantedAuthorities` vì Kerberos ticket validation **không tự cung cấp role/permission của ứng dụng**.
5. Có thể áp `additionalAuthenticationChecks` theo policy/provider customization.
6. Trả về `Authentication` đã xác thực (hoặc lỗi `AuthenticationException` nếu không thể chấp nhận/không hợp lệ); Spring có thể lưu nó vào `SecurityContext`/session theo filter/repository.

**Provider không phải HTTP Filter**: nó không tự đọc `Authorization` header, không tự sinh `WWW-Authenticate` challenge và không đăng ký URL endpoint. Các nhiệm vụ đó thuộc `SpnegoEntryPoint` và `SpnegoAuthenticationProcessingFilter`.

### 3.1. Sơ đồ các lớp

```text
HTTP Request from browser
     |
     v
SpnegoAuthenticationProcessingFilter
  đọc Authorization: Negotiate <token>
  decode Base64 theo SPNEGO handling
  tạo KerberosServiceRequestToken
     |
     v
AuthenticationManager / ProviderManager
     |
     v
KerberosServiceAuthenticationProvider
     |
     +-- KerberosTicketValidator
     |     SunJaasKerberosTicketValidator
     |       servicePrincipal = HTTP/web.example.org@EXAMPLE.ORG
     |       keyTabLocation   = file:/run/secrets/http-service.keytab
     |       JAAS + GSS acceptSecContext()
     |       => authenticated Kerberos principal
     |
     +-- UserDetailsService
     |       local account lookup
     |       account status + GrantedAuthorities
     |
     v
Authenticated KerberosServiceRequestToken
     |
     v
SecurityContextRepository + SessionAuthenticationStrategy
     |
     v
Authorization rules and application data access
```

Ở tầng dưới, JDK `java.security.jgss`/JAAS thực hiện công việc Kerberos cryptographic validation. Không nên viết custom `Base64.decode(token)` rồi đọc username ở đầu byte array để thay provider.

### 3.2. So với KerberosAuthenticationProvider

| Đặc tính | `KerberosServiceAuthenticationProvider` | `KerberosAuthenticationProvider` |
| --- | --- | --- |
| Vai trò | **Service acceptor** xác minh incoming ticket/SPNEGO | **Kerberos client** xác thực bằng username/password thông qua `KerberosClient` |
| Input | `KerberosServiceRequestToken` | Username/password authentication request theo API |
| Thành phần cốt lõi | `KerberosTicketValidator` | `KerberosClient`, ví dụ `SunJaasKerberosClient` |
| Secret service | Keytab/SPN để giải mã/accept ticket | Credentials client theo flow |
| Cách dùng phổ biến | Browser Integrated Windows Authentication HTTP Negotiate | Form/credential-based authentication với Kerberos backend |
| Kết quả | Kerberos principal + local UserDetails authorities | Principal + authorities theo service user mapping |
| Có sinh challenge HTTP? | Không; filter/entry point làm việc đó | Không; web chain/controller quyết định flow |

**Không thay provider service bằng provider username/password chỉ vì cả hai có chữ “Kerberos”.** Bài này tập trung vào **service ticket verification**, nên cần `KerberosServiceAuthenticationProvider` + `KerberosTicketValidator`.

## 4. SpnegoAuthenticationProcessingFilter, SpnegoEntryPoint và các ranh giới HTTP

### 4.1. Phản hồi challenge

Khi người dùng GET URL bảo vệ mà chưa có authentication, `SpnegoEntryPoint` thường tạo:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
```

Browser có hỗ trợ integrated authentication và policy cho phép mới tìm Kerberos credentials/ticket và trả request:

```http
GET /secure HTTP/1.1
Host: web.example.org
Authorization: Negotiate YIIB...example-base64...
```

Chuỗi `YIIB...` chỉ là placeholder. Token thật chứa dữ liệu protocol nhạy cảm và không được đưa vào tài liệu hoặc log. Header **không** là bằng chứng hợp lệ cho tới khi token đã được provider/JAAS accept.

### 4.2. Filter không tự kiểm ticket

`SpnegoAuthenticationProcessingFilter` đọc Negotiate Authorization header, tạo `KerberosServiceRequestToken` và gọi `AuthenticationManager`. Nó không tự quyết định identity hay group. Với Spring Security Kerberos 2.2.x, filter có các tùy chọn đáng chú ý:

- `setAuthenticationManager(...)`: bắt buộc cấu hình manager có provider service tương ứng.
- `setSecurityContextRepository(...)`: để lưu context sau khi authentication thành công; Javadoc 2.2 lưu ý mặc định **không lưu SecurityContext**.
- `setSessionAuthenticationStrategy(...)`: gọi khi xác thực mới thành công; có thể dùng bảo vệ session fixation.
- `setSkipIfAlreadyAuthenticated(...)`: mặc định `true`, có thể bỏ qua negotiate khi request đã authenticated bằng app session; liên quan tới quyền bị thay đổi và chính sách reauthentication.
- `setStopFilterChainOnSuccessfulAuthentication(...)`: mặc định `false`, request tiếp tục qua các filter khác sau khi xử lý thành công.
- `setFailureHandler(...)`: xử lý lỗi có kiểm soát; không log raw token và không quay vòng login vô hạn.

Đừng gắn Filter vào **cả Spring Security chain và Servlet Filter auto-registration** khiến cùng request xử lý Negotiate header hai lần. Đối với custom filter, tạo instance bên trong cấu hình chain hoặc tắt auto-registration như cách Boot cho phép.

### 4.3. SPNEGO là cơ chế negotiation, không đảm bảo mọi `Negotiate` đều là Kerberos

SPNEGO có thể đàm phán các cơ chế tùy client/KDC/policy. Ở môi trường AD, cấu hình browser đôi khi fallback NTLM. **Không tự tin mọi header có tiền tố `Negotiate` đều chứa Kerberos AP-REQ hợp lệ**, và không silently accept NTLM nếu policy chỉ cho Kerberos. Hãy kiểm cơ chế negotiated qua lớp JAAS/GSS/provider và quy tắc security của domain; bật audit khi thấy NTLM fallback ngoài dự kiến.

Khi browser không có TGT hoặc website không nằm trong policy Integrated Authentication, browser có thể hiện login prompt, dùng cơ chế khác hoặc không gửi token. Không xử lý bằng `permitAll("/secure/**")` hay bỏ xác minh để giảm lỗi giao diện.

## 5. KerberosTicketValidator, JAAS và keytab

### 5.1. Interface tách provider khỏi cách validate

`KerberosTicketValidator` là abstraction để provider xác minh token. Triển khai phổ biến ở môi trường Oracle/OpenJDK là `SunJaasKerberosTicketValidator`, thuộc package:

```java
org.springframework.security.kerberos.authentication.sun
    .SunJaasKerberosTicketValidator
```

Một số môi trường JDK khác có cách triển khai GSS/Kerberos riêng; không coi SunJaas implementation là lựa chọn phổ quát cho mọi runtime. Cần kiểm JDK vendor, system properties và native Kerberos/GSS provider phù hợp.

Theo Spring Kerberos Javadoc, các thiết lập quan trọng:

| Thuộc tính | Ý nghĩa | Hướng dẫn |
| --- | --- | --- |
| `setServicePrincipal(String)` | SPN app chấp nhận | `HTTP/web.example.org@EXAMPLE.ORG`, trùng keytab |
| `setKeyTabLocation(Resource)` | Nguồn file chứa service key | Ưu tiên `file:/run/secrets/http-service.keytab`, không nhúng image |
| `setDebug(boolean)` | JAAS/Kerberos debugging | `false` production; chỉ tạm bật trong staging |
| `setRefreshKrb5Config(boolean)` | Reload `krb5.conf` trước login theo cơ chế implementation | Không tự thay keytab runtime/realm policy nếu chưa test |
| `setHoldOnToGSSContext(boolean)` | Giữ GSS security context cho giao tiếp cần thêm thao tác GSS | Mặc định dispose; chỉ đổi khi có use case |
| `setMultiTier(boolean)` | Cơ chế multi-tier/ủy quyền Kerberos | Không bật nếu chỉ xác thực web cơ bản |
| `setRealmName(String)` | Realm name của ứng dụng khi cần | Không trộn realm client/tenant tuỳ ý |

**File keytab là secret.** Không commit `.keytab`, không upload vào Sheet, không log bytes, không để làm static resource. Spring Resource `classpath:` có thể không hoạt động như file path với JAAS ở một số runtime; docs gợi ý đường `file:` cho triển khai thực và bảo vệ file OS/k8s Secret mounts.

### 5.2. Vì sao phải có đúng key?

KDC mã hóa phần ticket cấp cho service bằng key của principal đích. Service phải có key thích hợp để giải mã/xác minh và nhận client principal qua Kerberos AP exchange. Nếu người vận hành dùng:

```text
Expected SPN: HTTP/web.example.org@EXAMPLE.ORG
Keytab only:  HTTP/legacy.example.org@EXAMPLE.ORG
```

thì ticket cấp cho `HTTP/web.example.org` có thể không được accept, dù user có TGT hợp lệ và KDC hoạt động. Tương tự, keytab cũ với **KVNO** không còn khớp sau thay mật khẩu service account hoặc encryption type không tương thích sẽ làm decryption thất bại.

**Không “sửa” bằng cách dùng bất kỳ keytab nào của domain controller hoặc key của user**. Service phải dùng một identity/permission tối thiểu được quản trị cho đúng public SPN.

### 5.3. KVNO, encryption type và rotation

- **KVNO** (Key Version Number) giúp chọn phiên bản key tương ứng trong Kerberos ticket/keytab. Khi service principal key thay đổi, KDC có thể phát ticket với KVNO mới.
- **Encryption type (etype)** của ticket/keytab/JDK/KDC phải tương thích; chính sách hiện đại ưu tiên AES và loại bỏ etype yếu theo chuẩn bảo mật tổ chức.
- **Rotation** cần phối hợp KDC/AD service account, keytab mới, thời hạn ticket cũ, rollout các node, replay cache và khả năng chấp nhận key versions phù hợp. Không thay keytab trên một node trước khi biết client tickets sẽ được cấp theo key nào.
- Sau rotation, test cả ticket mới và old in-flight theo chính sách. Không giữ key bị lộ trong keytab vì “overlap cho chắc”.
- Không gắn quyền domain admin cho HTTP service account; keytab chứa bí mật có thể bị dùng để mạo danh service trong phạm vi principal đó.

**Khi keytab mới không làm SPNEGO hoạt động**, cần kiểm đúng SPN owner, KVNO, etype, realm, file permissions và cache/restart của JAAS validator thay vì tắt encryption verification.

## 6. Spring Security Kerberos 6.x/7.x: phụ thuộc phiên bản đúng

Vì Kerberos extension thay đổi toạ độ Maven khi tích hợp với Spring Security 7.x, phải chọn **một dòng version duy nhất**:

| Hệ nền | Kerberos module Maven | Lưu ý |
| --- | --- | --- |
| Spring Boot 3.x, Spring Security 6.5.x | `org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0` và `org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0` | Dòng extension 2.2.0, Servlet Jakarta, Java 17+ |
| Spring Security 7.1.x / Spring Framework 7.x | `org.springframework.security:spring-security-kerberos-core` và `org.springframework.security:spring-security-kerberos-web` tương ứng 7.1.x | Tọa độ group đổi; dùng Boot/framework/BOM tương thích |
| Legacy Spring Security 5.x | Các phiên bản Kerberos extension cũ hơn | Không dùng code Jakarta/Boot 3 rồi bỏ qua migration |

Ví dụ Maven **fragment** cho Boot 3.x/Security 6.5.x, với Spring Boot BOM quản lý các dependency Boot/Security:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
    <version>2.2.0</version>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
    <version>2.2.0</version>
  </dependency>
</dependencies>
```

**Không** dùng group `org.springframework.security` + version 2.2.0, và không dùng group `org.springframework.security.kerberos` + version 7.1.x. Đồng thời kiểm `mvn dependency:tree` xem có version conflict Spring Security core/web/Jakarta hay không. Đây là **đoạn `pom.xml`**, project cần parent/BOM, build plugin và cấu hình Java phù hợp. Security advisories có thể thay đổi; với production cần kiểm phiên bản đã được hỗ trợ và các bản vá tại thời điểm triển khai, không giữ nguyên 2.2.0 một cách máy móc.

## 7. Lab: chuẩn bị KDC, SPN, keytab và HTTPS

Môi trường mẫu:

```text
Kerberos realm:          EXAMPLE.ORG
KDC/AD Domain Controller: kdc.example.org
Public web host:         web.example.org
Service principal:       HTTP/web.example.org@EXAMPLE.ORG
Keytab path on Spring:   /run/secrets/http-web.keytab
App HTTPS URL:           https://web.example.org/secure
Backend app:             http://spring-backend:8080
```

Điều kiện tiên quyết:

1. Được domain admin/Kerberos operator tạo hoặc xác nhận service account và **đăng ký SPN đúng một lần** cho public FQDN.
2. Có keytab được phân phối qua cơ chế bí mật an toàn, chứa principal, KVNO và etype đúng. Service process có quyền **read** file nhưng user thường không được đọc.
3. KDC/AD realm và DNS có thể tìm được từ máy client; browser có chính sách Integrated Authentication cho `web.example.org`.
4. Linux/Windows Spring JVM có cấu hình Kerberos (`krb5.conf` hoặc hệ điều hành), DNS/KDC, clock sync/NTP.
5. Browser→web host dùng HTTPS hợp lệ; proxy không sửa `Authorization: Negotiate`/`WWW-Authenticate`, trừ khi proxy có chủ đích tự làm Kerberos acceptor.
6. KDC và Spring host dùng timezone/UTC clock đồng bộ; ticket replay cache và principal mapping theo security policy.
7. Môi trường test có user `alice@EXAMPLE.ORG` **đã được tạo** trong Kerberos realm và user mapping/role nội bộ tương ứng.

### 7.1. Kiểm cấu hình keytab an toàn

Trên Linux MIT Kerberos, với quyền được cấp trên máy **giữ keytab**:

```bash
klist -k -t -e /run/secrets/http-web.keytab
```

Lệnh liệt kê principal/KVNO/etype của keytab; **không in bytes của key**. Tuy nhiên tên principal cũng là thông tin vận hành có thể nhạy cảm, không dán toàn bộ vào ticket công khai. Lệnh có thể khác trên Windows/heimdal, cần theo dõi công cụ được cài.

Dùng công cụ domain admin kiểm SPN trên AD (ví dụ trong Windows):

```powershell
setspn -Q HTTP/web.example.org
setspn -X
```

- `-Q` kiểm SPN trỏ đến account nào.
- `-X` tìm các SPNs trùng theo quyền/phạm vi của công cụ.
- Không dùng `setspn -A`/`-S` từ bản README để thay đổi directory production khi chưa có change approval.
- **Do not export password/keytab trong log** hoặc gửi cho web browser để test.

Nếu cần kiểm TGS ticket từ máy client đã có TGT:

```bash
klist
kvno HTTP/web.example.org@EXAMPLE.ORG
klist
```

Các lệnh trên chỉ có ý nghĩa trong Kerberos realm đã cấu hình; `kvno` có thể cần account và vé cấp phát hợp lệ. Không cung cấp stdout cố định vì KDC/DNS/realm/OS khác nhau. `kinit -k` bằng keytab trên service host là thao tác kiểm thử tài khoản dịch vụ nhạy cảm, chỉ thực hiện khi có quyền và hiểu chính sách; **không phải yêu cầu để browser SPNEGO login hoạt động**.

### 7.2. Reverse proxy phải làm gì?

Khi HTTPS terminate tại ingress/LB:

```text
Browser HTTPS web.example.org:443
      |
      | Authorization: Negotiate <token>
      v
Ingress / Reverse Proxy
      |
      | forwarded header, Host and target path preserved
      v
Spring Security / SpnegoAuthenticationProcessingFilter
      |
      | JAAS validates AP-REQ for HTTP/web.example.org
      v
Authentication + app SecurityContext
```

- Browser xin service ticket cho **public host `web.example.org`**, không phải container name `spring-backend`.
- Keytab Spring phải chứa đúng key của public SPN.
- Ingress phải **giữ** `Authorization: Negotiate` và chuyển `401 WWW-Authenticate: Negotiate` về browser.
- Không để reverse proxy làm authentication khác rồi gửi `X-Remote-User` chưa được bảo vệ tới app; nếu proxy là acceptor thì thiết kế chuyển sang trusted preauthentication với kênh mạng riêng.
- Browser HTTPS/TLS server certificate khác với Kerberos service keytab; cả hai cần bảo mật nhưng thực hiện chức năng khác nhau.
- Không tin `X-Forwarded-Host` do client tự gắn để dựng SPN tuỳ ý hoặc cấp quyền cho tenant mới.
- Nếu sử dụng hostname alias/CNAME, kiểm cách browser canonicalize SPN và cách KDC ánh xạ; không chỉ sửa DNS rồi kỳ vọng keytab cũ tự tương thích.

## 8. Ví dụ cấu hình Spring Boot 3.x + Kerberos 2.2.x

### 8.1. File `application.yml`

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  kerberos:
    service-principal: "HTTP/web.example.org@EXAMPLE.ORG"
    keytab: "/run/secrets/http-web.keytab"
```

Đây là ví dụ sau một ingress HTTPS tin cậy. `forward-headers-strategy` chỉ an toàn nếu proxy xóa headers forwarded của client và cấp lại chính xác. Nếu chạy HTTP localhost không có proxy, cookie `secure=true` có thể không được gửi; dùng staging HTTPS thay vì tắt TLS production. Không đưa bytes keytab hay password KDC vào YAML.

### 8.2. SecurityFilterChain, ticket validator và provider

File `src/main/java/com/example/kerberos/KerberosSecurityConfig.java`:

```java
package com.example.kerberos;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator(
            @Value("${app.kerberos.service-principal}") String spn,
            @Value("${app.kerberos.keytab}") String keytabPath) {

        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(spn);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        validator.setDebug(false);
        return validator;
    }

    @Bean
    UserDetailsService users() {
        // LAB ONLY: username được Kerberos acceptor xác minh.
        // Sản phẩm thực dùng directory/internal account+tenant policy.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice@EXAMPLE.ORG")
                .password("{noop}not-used-for-spnego")
                .roles("REPORT_READER")
                .build());
    }

    @Bean
    KerberosServiceAuthenticationProvider serviceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {

        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider,
            SecurityContextRepository contextRepository)
            throws Exception {

        SpnegoAuthenticationProcessingFilter spnegoFilter =
            new SpnegoAuthenticationProcessingFilter();

        spnegoFilter.setAuthenticationManager(
            new ProviderManager(provider));

        // Trong Spring Security 6, custom filter phải chỉ rõ
        // nơi lưu context; mặc định Spnego filter không lưu.
        spnegoFilter.setSecurityContextRepository(contextRepository);
        spnegoFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());
        spnegoFilter.setSkipIfAlreadyAuthenticated(true);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/secure", "/secure/**")
                    .hasRole("REPORT_READER")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .authenticationProvider(provider)
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // Không khai báo @Bean cho Spnego Filter ở ngoài chain:
        // tránh Boot auto-register thêm một Servlet Filter.
        http.addFilterBefore(
            spnegoFilter, BasicAuthenticationFilter.class);
        return http.build();
    }
}
```

**Cấu hình trên có nghĩa gì?**

- `SunJaasKerberosTicketValidator` dùng keytab+SPN của ứng dụng để accept incoming Kerberos service tokens qua JAAS/GSS, không xem `Authorization` header như một API key.
- `KerberosServiceAuthenticationProvider` nhận validated principal từ validator rồi dùng `UserDetailsService` tìm user/authorities. Nếu user Kerberos không có account local, **không tạo role mặc định cho mọi user domain**.
- `ProviderManager(provider)` đảm bảo SPNEGO filter gọi chính provider service; `http.authenticationProvider(provider)` cũng đăng ký với Spring chain cho các đường authentication tương thích.
- `SpnegoEntryPoint` phát Negotiate challenge. Nếu cần form/LDAP fallback, dùng thiết kế riêng và hiểu chính sách failover; ví dụ này **chỉ minh họa Negotiate**.
- `securityContextRepository` được chia sẻ bởi SPNEGO filter và `HttpSecurity` để persistence nhất quán.
- `ChangeSessionIdAuthenticationStrategy` giảm nguy cơ session fixation khi tạo xác thực mới. Cấu hình thực có thể thêm concurrent-session controls và logout/revocation theo nhu cầu.
- `setSkipIfAlreadyAuthenticated(true)` có thể tiết kiệm việc xử lý ticket lặp khi local app session đã xác thực. **Điều này không có nghĩa phải recheck KDC ở mỗi request**, và làm stale authority trở thành một rủi ro cần chính sách refresh/revocation riêng.
- `hasRole("REPORT_READER")` yêu cầu local authority `ROLE_REPORT_READER`. Nó không phải role có sẵn do Kerberos ticket cấp; lab `UserDetailsService` là nơi gán.
- Không tắt CSRF toàn bộ để xử lý Negotiate; các thao tác POST có cookie/session vẫn cần CSRF protection phù hợp.
- Có thể dùng TLS terminator, nhưng JVM phải được cấp đúng keytab của **public SPN**; không gắn principal theo backend host mà user không truy cập.
- Tất cả imports đã dùng là từ Spring Security Servlet/Jakarta-compatible 6.x và Kerberos extension 2.2.x. Nếu đang dùng Spring Security 7.x, sử dụng module coordinate và APIs của bản 7.x, chạy compilation/integration tests tương ứng.

**Lưu ý quan trọng:** In-memory user `alice@EXAMPLE.ORG` chỉ là fixture. Thực tế Kerberos principal string có thể chứa case/realm đúng như GSS provider trả về; hãy đo trên môi trường test, chuẩn hóa theo mapping có kiểm soát và tra account bằng immutable directory ID khi phù hợp. Không dựa vào `String.toLowerCase()` hoặc cắt `@REALM` bừa bãi để gộp tài khoản giữa domains/tenants.

### 8.3. Một Spring Boot app và controller để thử

File `src/main/java/com/example/kerberos/KerberosApplication.java`:

```java
package com.example.kerberos;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {

    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
```

File `src/main/java/com/example/kerberos/TestController.java`:

```java
package com.example.kerberos;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TestController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "Kerberos SPNEGO lab");
    }

    @GetMapping("/secure")
    public Map<String, String> secure(Authentication authentication) {
        return Map.of(
            "status", "authenticated",
            "principal", authentication.getName());
    }
}
```

Nếu user Kerberos được validate nhưng không có `REPORT_READER`, kết quả đúng là bị chặn bởi authorization. Với code demo, user chưa được tạo local cũng có thể làm authentication fail. Nếu app xuất lỗi 401 sau khi browser đã có TGT, cần xem SPN/keytab/ticket validation; nếu app trả 403, trước hết kiểm `UserDetailsService` và `GrantedAuthorities`.

### 8.4. Chạy thử tích hợp cần gì?

Có Maven/Gradle project hoàn chỉnh, dependency versions nhất quán, Java 17, KDC/AD staging hoạt động, SPN trên directory, keytab secret mount, ingress HTTPS, browser integrated auth policy. Khi đủ điều kiện:

```bash
./mvnw spring-boot:run
```

Không có KDC/keytab hợp lệ thì dự án **không thể chứng minh Kerberos service ticket validation thành công**, dù Java compile và Spring start được. Không lấy việc app root `/` trả 200 làm bằng chứng Kerberos đã chạy.

## 9. Browser Integrated Authentication và phép thử từ client có TGT

Một browser trong domain có thể tự dùng Kerberos nếu:

- Trang đích nằm trong vùng/allowlist Integrated Authentication (Chrome/Edge/Firefox policy tùy tổ chức).
- User đã có TGT hoặc có cơ chế lấy credentials hợp lệ.
- DNS/SPN/realm mapping đúng.
- HTTP 401 Negotiate challenge tới được browser.
- Mạng máy khách có thể liên lạc KDC để xin ticket (hoặc đã có ticket còn hiệu lực trong cache).
- TLS callback được browser tin, không bị redirect hostname khiến đổi SPN ngoài ý muốn.

### 9.1. Xem handshake

Dùng DevTools Network trong **môi trường test**, nhưng **không sao chép `Authorization: Negotiate ...`** hay session cookie vào ticket/nhật ký. Dấu hiệu bình thường:

```text
1. GET https://web.example.org/secure
   => HTTP 401
      WWW-Authenticate: Negotiate

2. GET https://web.example.org/secure
   Authorization: Negotiate [redacted]
   => HTTP 200 nếu user có ROLE_REPORT_READER
      hoặc 403 nếu Kerberos hợp lệ nhưng quyền app không đủ.
```

Lưu ý multi-step GSS negotiation có thể có nhiều trao đổi header/status; số lần round-trip không cố định. Nếu thấy 401 cuối cùng, phải phân biệt browser không gửi ticket, token bị reject, keytab mismatch, user details fail, hoặc authenticated session không được lưu.

### 9.2. Công cụ dòng lệnh có ticket hợp lệ

Trên máy Linux/macOS có Kerberos/curl SPNEGO support, đã có TGT của **user test**:

```bash
klist
curl --negotiate -u : -i https://web.example.org/secure
```

- `--negotiate` yêu cầu curl dùng GSS Negotiate.
- `-u :` kích hoạt HTTP auth negotiation trong nhiều bản curl, không có nghĩa gửi password thật.
- Không dùng `-k`/`--insecure` vì nó tắt TLS verification của web host.
- Kiểm `curl -V` có hỗ trợ GSS-API/SSPI; không phải bản nào cũng build với Kerberos.
- `klist`/`kvno` chỉ phản ánh ticket cache/realm của client; không thay việc kiểm keytab và validator trên JVM service.
- Cần realm/host test đúng, không chạy trên endpoint production chưa được phép.

**Không in raw Negotiate token bằng `curl -v` ra log công khai**. Nếu cần trace chi tiết, giới hạn môi trường test/khả năng redact và chỉ ghi status, request ID, principal sau khi verify.

## 10. Java 17 chạy độc lập: tách xác minh ticket khỏi cấp quyền

Ví dụ này **không xác minh Kerberos ticket thật**; điều đó phải do JAAS/GSS và `KerberosTicketValidator` thực hiện. Nó chỉ mô phỏng **policy layer sau khi crypto verification đã thành công** để chứng minh một user có Kerberos principal hợp lệ vẫn phải được xác nhận là **account đang active, đúng realm và đúng quyền của ứng dụng**.

Tạo file `KerberosServiceDecisionDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public final class KerberosServiceDecisionDemo {

    record VerifiedIdentity(
        String clientPrincipal,
        String acceptedServicePrincipal,
        boolean ticketValidated
    ) { }

    record Account(boolean active, Set<String> roles) { }

    private static final String EXPECTED_SERVICE =
        "HTTP/web.example.org@EXAMPLE.ORG";
    private static final String EXPECTED_REALM =
        "EXAMPLE.ORG";

    private static final Map<String, Account> ACCOUNTS = Map.of(
        "alice@EXAMPLE.ORG",
        new Account(true, Set.of("REPORT_READER")),
        "bob@EXAMPLE.ORG",
        new Account(true, Set.of("EMPLOYEE")),
        "disabled@EXAMPLE.ORG",
        new Account(false, Set.of("REPORT_READER"))
    );

    static String decision(VerifiedIdentity identity) {
        if (identity == null || !identity.ticketValidated()) {
            return "DENY_UNVERIFIED";
        }

        if (!EXPECTED_SERVICE.equals(
                identity.acceptedServicePrincipal())) {
            return "DENY_SERVICE";
        }

        String client = identity.clientPrincipal();
        if (client == null
                || !client.endsWith("@" + EXPECTED_REALM)) {
            return "DENY_REALM";
        }

        Account account = ACCOUNTS.get(client);
        if (account == null || !account.active()) {
            return "DENY_ACCOUNT";
        }

        if (!account.roles().contains("REPORT_READER")) {
            return "DENY_ROLE";
        }

        return "ALLOW";
    }

    public static void main(String[] args) {
        System.out.println("valid=" + decision(
            new VerifiedIdentity(
                "alice@EXAMPLE.ORG", EXPECTED_SERVICE, true)));

        System.out.println("unverified=" + decision(
            new VerifiedIdentity(
                "alice@EXAMPLE.ORG", EXPECTED_SERVICE, false)));

        System.out.println("wrongService=" + decision(
            new VerifiedIdentity(
                "alice@EXAMPLE.ORG",
                "HTTP/other.example.org@EXAMPLE.ORG", true)));

        System.out.println("wrongRealm=" + decision(
            new VerifiedIdentity(
                "alice@EVIL.EXAMPLE", EXPECTED_SERVICE, true)));

        System.out.println("missingAccount=" + decision(
            new VerifiedIdentity(
                "charlie@EXAMPLE.ORG", EXPECTED_SERVICE, true)));

        System.out.println("disabled=" + decision(
            new VerifiedIdentity(
                "disabled@EXAMPLE.ORG", EXPECTED_SERVICE, true)));

        System.out.println("insufficientRole=" + decision(
            new VerifiedIdentity(
                "bob@EXAMPLE.ORG", EXPECTED_SERVICE, true)));
    }
}
```

Biên dịch/chạy bằng **JDK 17+**, không cần Spring:

```bash
javac --release 17 KerberosServiceDecisionDemo.java
java KerberosServiceDecisionDemo
```

Stdout **xác định**:

```text
valid=ALLOW
unverified=DENY_UNVERIFIED
wrongService=DENY_SERVICE
wrongRealm=DENY_REALM
missingAccount=DENY_ACCOUNT
disabled=DENY_ACCOUNT
insufficientRole=DENY_ROLE
```

Giải thích:

1. `valid=ALLOW` chỉ đạt vì **tất cả** giả định đã verified, service đúng, realm đúng, account active và có role phù hợp.
2. `unverified=DENY_UNVERIFIED`: có username nhưng chưa xác minh Kerberos không được cấp quyền.
3. `wrongService=DENY_SERVICE`: ticket dành cho service khác không hợp lệ đối với ứng dụng này.
4. `wrongRealm=DENY_REALM`: nguồn realm không nằm trong policy cho phép.
5. `missingAccount=DENY_ACCOUNT`: domain identity tồn tại không tự được app tạo account/role.
6. `disabled=DENY_ACCOUNT`: user bị khóa phải bị chặn dù trước đó đã có ticket hợp lệ.
7. `insufficientRole=DENY_ROLE`: xác thực Kerberos thành công chưa đủ để đọc báo cáo.

**Giới hạn tuyệt đối:** `VerifiedIdentity.ticketValidated` là **biến giả định chỉ dùng trong demo console**. Trong ứng dụng thật, một boolean từ browser/query/header **không chứng minh** Kerberos; object evidence phải xuất phát từ provider/validator sau GSS accept thành công. Không dùng class demo này làm hệ thống xác minh token hoặc quyết định authorization sản phẩm.

### 10.1. Điểm mở rộng cho UserDetailsService production

Trong production, `UserDetailsService.loadUserByUsername(kerberosPrincipal)` nên:

- Chỉ nhận username **đã được Kerberos provider validate**, không lấy từ request header tuỳ ý.
- Map principal+realm theo source đã tin; với AD có thể liên kết tới immutable SID/objectGUID/enterprise identity ID thay vì chỉ so string.
- Từ chối account DISABLED/DELETED, và kiểm membership/entitlements của từng tenant.
- Nạp authorities tối thiểu theo backend permission store; không cấp `ROLE_ADMIN` cho toàn bộ user thuộc domain.
- Không tự ghép các principal cùng phần tên `alice` nhưng khác realm `EXAMPLE.ORG`/`PARTNER.ORG`.
- Có cache/revocation SLA: nếu user bị thu hồi ở directory, app session cũ có thể giữ role cũ; cần cơ chế invalidation/recheck.
- Không tìm user bằng email alias chưa được verified hoặc auto-provision người không được tổ chức mời.
- Có audit source principal đã được verify, local account ID, tenant, policy decision và thời gian nhưng không log Kerberos token.

## 11. Vé dịch vụ hợp lệ vẫn chưa chắc được cấp phép

Phân biệt hai câu hỏi:

**Authentication:** Service có chứng minh được `AP-REQ` chứa ticket hợp lệ cho `HTTP/web.example.org@EXAMPLE.ORG`, còn trong thời gian cho phép, từ KDC/realm đã tin, và ánh xạ ra principal `alice@EXAMPLE.ORG` không?

**Authorization:** Local account `alice` có `ROLE_REPORT_READER`, membership tenant `org-red`, quyền xem report ID 123 và tuân thủ chính sách riêng không?

Không lấy các điều kiện này làm một. Kerberos ticket thường **không phải entitlement database**. Microsoft AD PAC/group data có thể tồn tại tùy môi trường, nhưng provider đơn giản này dùng `UserDetailsService` để nạp quyền; không tự coi mọi PAC hoặc group ID trong source tuỳ ý là quyền ứng dụng.

### 11.1. Ví dụ phân vùng tenant

Một realm `EXAMPLE.ORG` có thể xác thực nhân viên của cả `tenant-red` và `tenant-blue`. Service ticket chỉ cho biết danh tính đã được KDC xác minh với service, **không** cho biết user được đọc mọi dữ liệu tenant.

```text
Verified Kerberos principal = alice@EXAMPLE.ORG
Mapped local account       = acct-42
Tenant memberships:
    tenant-red -> REPORT_READER (ACTIVE)
    tenant-blue -> NONE

GET /t/tenant-red/reports/123  -> allow nếu report thuộc red
GET /t/tenant-blue/reports/987 -> deny
```

Phải kiểm tenant ở service/repository/data layer, không chỉ `anyRequest().authenticated()`. Một Kerberos principal đúng mà truy cập sai tenant vẫn là cross-tenant authorization defect.

## 12. Service ticket validation không giống kiểm ID Token/SAML Assertion

| Hệ federation | Chứng cứ trình ứng dụng | Cơ chế xác minh chính | Dữ liệu định danh/quyền |
| --- | --- | --- | --- |
| **Kerberos SPNEGO** | `Authorization: Negotiate` chứa GSS token/AP-REQ | GSS/JAAS acceptor + service principal keytab/kerberos protocol | Client principal; app nạp UserDetails/GrantedAuthorities |
| **CAS** | `ticket=ST-...` opaque qua browser callback | Backend gọi CAS `/serviceValidate` với đúng `service` | CAS principal/attributes, app map roles |
| **SAML2** | `SAMLResponse`/Assertion XML | XML signature, issuer, audience, recipient, conditions, replay | NameID/attributes, app map identity/rights |
| **OIDC** | ID Token JWT sau authorization code flow | JWT signature, issuer, audience, nonce/state, expiry | `iss+sub`/claims, app map identity/rights |
| **OAuth2 Resource Server** | Bearer access token (JWT/opaque) | Decoder/introspection, issuer, resource audience/scope | Scope/claims, app authorization |

Không gửi Kerberos service ticket làm `Authorization: Bearer` cho API JWT, và không đưa CAS ST hoặc SAMLResponse vào `KerberosTicketValidator`. Các cơ chế có cùng kết quả cuối là `Authentication` của Spring, nhưng có các trust boundaries khác nhau.

## 13. Replay, thời gian và GSS security context

### 13.1. Vì sao thời gian đồng bộ quan trọng?

Kerberos dùng timestamp và ticket validity, thường yêu cầu clock skew hạn chế giữa client/server/KDC. Nếu đồng hồ server lệch nhiều, ticket/authenticator có thể bị từ chối, dù SPN/keytab đúng. Cần dùng NTP/domain time sync có kiểm soát, **không nới clock skew tùy tiện** hoặc quay giờ hệ thống để “test qua”.

Các trường hợp:

- Ticket chưa đến `starttime` hoặc đã qua `endtime`.
- Authenticator timestamp vượt allowable clock skew.
- KDC/client/service lệch timezone/giờ hệ thống do NTP lỗi; xử lý theo UTC.
- Replay of authenticator trong cửa sổ cho phép; cơ chế replay cache phải phát hiện trùng lặp theo RFC 4120.

### 13.2. Replay cache không phải HttpSession

RFC 4120 yêu cầu server dùng **replay cache** trừ khi application protocol có cách bảo vệ tương đương theo điều kiện chuẩn. Với nhiều node cùng chia sẻ SPN/keytab, replay protection cần đánh giá kỹ: RFC cảnh báo trường hợp nhiều servers dùng chung service principal mà **không chia sẻ replay cache**, trừ khi ứng dụng có bảo vệ khác loại bỏ rủi ro.

**Đừng nhầm:**

- Kerberos replay cache theo authenticator ≠ Spring `HttpSession`.
- `SpnegoAuthenticationProcessingFilter.setSkipIfAlreadyAuthenticated(true)` ≠ replay protection.
- TLS connection ≠ bảo đảm mọi request Negotiate token không thể bị replay ở server khác.
- Một cache kết quả authentication tự xây không thay `GSSContext.acceptSecContext` và policy replay của Kerberos.

Xem implementation/JVM/realm thực tế có replay cache nào, scope ra sao và cách HA xử lý; **không tuyên bố mọi JDK/cluster mặc định dùng một cache chung**. Nếu nhận thấy replay cache bất khả thi, kiến trúc cần được security review theo RFC, không tự đặt `disableReplayCache=true` để giảm lỗi.

### 13.3. GSSContext và multi-step negotiation

JDK `GSSContext.acceptSecContext` có thể yêu cầu nhiều token exchanges, có thể trả output token cho initiator và chỉ báo `isEstablished()` khi context hoàn tất. Spring validator xử lý theo cấu hình/thư viện; **không tự sửa logic HTTP để assume mọi Negotiate handshake luôn chỉ có một token**. Với mutual authentication hoặc GSS delegated credentials, cần chủ ý giữ/giải phóng context và bảo vệ delegated credentials.

`SunJaasKerberosTicketValidator.setHoldOnToGSSContext(true)` chỉ có ý nghĩa nếu ứng dụng cần GSS operations sau xác thực. Không bật giữ context toàn hệ thống khi chỉ cần principal/role; giữ secret/session handles không cần thiết làm tăng tài nguyên và rủi ro.

## 14. Phân quyền và chính sách an toàn cho keytab

Keytab là **service-account secret**, không phải file cấu hình vô hại. Tối thiểu cần:

1. Mount qua hệ thống secrets, không embed trong JAR/Git/Docker image public.
2. File owner là process identity và quyền read hạn chế; container chỉ được truy cập keytab cần thiết.
3. Tránh service account có quyền domain admin, interactive login hoặc quyền rộng không cần thiết.
4. Bảo vệ build pipeline, file system backups, crash dumps và diagnostic outputs chứa keytab.
5. Rotate khi hết chính sách hoặc nghi lộ; phối hợp SPN/KVNO/etype và rollout mọi nodes.
6. Khi keytab bị lộ, attacker có thể mạo danh **service acceptor** trong phạm vi key đó; xử lý như incident, đổi key, rà soát ticket/traffic, không chỉ xóa file trên một node.
7. Giám sát file access/permission changes nhưng không log nội dung keytab.
8. Không đưa keytab vào `classpath:` của fat JAR cho production nếu có lựa chọn file secret mount rõ ràng; JAAS/JVM nhiều khi cần đường file thực.
9. Ở KDC/AD, audit service account, các SPN gán, encryption policy và thay mật khẩu ngoài quy trình.
10. Khi dùng multi-tenant SaaS, không chia sẻ một keytab để vượt ranh giới realm/tenant mà không đánh giá trust, SPN và authorization.

**HTTPS vẫn cần thiết** ngay cả khi Kerberos cung cấp authentication: HTTP Negotiate token, response/body dữ liệu, cookies và các request sau login phải được bảo vệ trên đường truyền. Kerberos không tự đặt CSP/CSRF/Secure/HttpOnly cho ứng dụng.

## 15. Ma trận QA tích hợp KerberosServiceAuthenticationProvider

Các ca negative cần **KDC/realm test hoặc token fixture đã được cấp hợp lệ** khi kiểm SPN/time/role, để phân biệt lỗi validation với lỗi dữ liệu giả. Đừng chỉ đổi một byte trong token rồi kết luận “realm sai” — thay byte sẽ hỏng signature/protocol trước khi tới kiểm realm.

| Test case | Input/thiết lập | Kết quả đúng |
| --- | --- | --- |
| **Happy path** | Client domain có TGT, browser xin ST cho SPN đúng, service keytab đúng, user active+role | SPNEGO login thành công, `/secure` cho phép |
| Không có Authorization header | Browser chưa thương lượng | `401 WWW-Authenticate: Negotiate` |
| Header Basic thay Negotiate | Browser gửi `Authorization: Basic` nhưng chain chỉ hỗ trợ SPNEGO | Không coi là Kerberos login |
| Header `Negotiate` chứa Base64 rác | Không có GSS token hợp lệ | Reject, không tạo Authentication |
| Token do attacker tự khai username | Không có service ticket | Reject |
| **SPN mismatch** | Ticket cho `HTTP/other.example.org`, keytab web app | Reject bởi service acceptor |
| **Sai keytab** | File chứa key cho principal khác | JAAS/GSS failure; reject |
| **Sai KVNO** | KDC phát ticket KVNO mới, keytab chưa cập nhật | Decryption/validation fail |
| **Etype không hỗ trợ** | KDC/client/keytab và JDK không thống nhất encryption types | Fail; sửa policy/keys, không bật DES/RC4 tùy tiện |
| **Keytab không đọc được** | Process thiếu file permissions/secret mount | Startup/validation failure, không fallback insecure |
| **SPN trùng trong AD** | Hai directory accounts cùng claim HTTP SPN | TGS request/validation lỗi, cần sửa registry |
| **DNS alias sai** | Browser dùng web alias, KDC ticket SPN không khớp | Fail; sửa DNS/SPN mapping |
| **Clock skew** | JVM lệch NTP so KDC/client | Reject theo Kerberos clock policy |
| Ticket expired | TGS ticket hết hạn | Reject, client cần ticket hợp lệ mới |
| Ticket/authenticator replay | Gửi lại token khi replay cache/policy đang có hiệu lực | Reject theo GSS/Kerberos policy |
| NTLM fallback | Client không xin được Kerberos và dùng NTLM | Từ chối nếu app policy chỉ chấp nhận Kerberos |
| User principal hợp lệ, local account thiếu | GSS success nhưng `UserDetailsService` không tìm user | Không login có quyền |
| User disabled | Valid ticket nhưng account nội bộ locked/disabled | Reject theo local account policy |
| User không có `REPORT_READER` | Kerberos success, user active nhưng role khác | 403, không xem `/secure` |
| Sai tenant | Kerberos user Red yêu cầu data Blue | Deny bằng membership/resource policy |
| Browser không ở allowlist Integrated Auth | Không tự gửi SPNEGO | 401/fallback đã định nghĩa, không bypass |
| Ingress bỏ `Authorization` | Request tới app không còn Negotiate header | Không xác thực; sửa proxy forwarding |
| Ingress bỏ `WWW-Authenticate` | Browser không nhận challenge | Không tự gửi ticket; sửa proxy |
| TLS cert của web không trusted | Browser HTTPS fail | Không bypass TLS hoặc thêm `curl -k` production |
| GSS established nhưng app session không lưu | Filter thiếu repository hoặc cookie/session store lỗi | Login từng request/loop; sửa persistence |
| Session fixation | Client có session ID trước login | Session ID đổi/được bảo vệ khi auth mới |
| App session còn nhưng user bị thu hồi | Authorities cached trong session | Revocation policy chặn trong SLA |
| Hai pods, keytab khác nhau | Một pod có KVNO/SPN sai | Login chập chờn; đồng bộ secret và version |
| Two services sharing SPN without replay strategy | Cùng keytab nhiều pods, replay cache local | Bị đánh giá security fail; thiết kế cluster protection đúng |
| Kerberos realm khác | Token từ realm không được trust theo policy | Reject, không auto-map account theo simple username |
| KDC unavailable sau ST đã cấp | Existing ticket còn hiệu lực, service có keytab | Có thể vẫn accept token theo GSS; đừng coi KDC outage = bỏ ticket validation |
| KDC unavailable lúc cần xin ticket | Client không có cached valid ST/TGT | Login thất bại/fallback policy, không cấp session giả |
| Keytab bị lộ | Incident security | Rotate service key, revoke sessions/credentials theo risk; không giữ trust cũ |

**Điều kiện PASS:** Không chỉ HTTP 200. Phải xác nhận `Authentication.getName()` đến từ ticket đã verify, đúng local account và authorities; protected resource đúng policy; những ca sai phải **không** tạo authenticated session. Một số lỗi phía client chỉ dẫn đến không gửi token và server chờ challenge; không bắt buộc phải có failure handler event cho mọi case.

### 15.1. Thử nghiệm phần mềm với fake KerberosTicketValidator?

Bạn có thể unit-test **mối nối provider → UserDetailsService** bằng một fake `KerberosTicketValidator` trả principal mô phỏng trong isolated test, nhưng **test này không chứng minh GSS/Kerberos cryptographic validation**. Với integration/security acceptance, cần có Kerberos test realm/KDC và real keytab/token generation; nếu không chỉ xác minh code wiring và authorization giả lập.

Cũng không dùng fixture ticket của production trong unit tests, CI logs hoặc Google Sheets. Ticket có lifecycle/identity và có thể bị khai thác nếu còn hiệu lực.

## 16. Lỗi thường gặp và cách chẩn đoán có thứ tự

| Dấu hiệu | Lớp nghi vấn | Hướng xử lý |
| --- | --- | --- |
| Browser nhận 401 Negotiate lặp đi lặp lại | Không gửi token, SPN, keytab, GSS accept, account lookup | Kiểm challenge, Authorization, SPN, KDC, JAAS logs |
| Browser không hề gửi `Authorization: Negotiate` | Browser policy/zone, chưa có TGT, DNS/realm | Kiểm Integrated Authentication allowlist, `klist`, `kvno` |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | SPN không được đăng ký | Kiểm `setspn -Q HTTP/web.example.org`, owner |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | SPN trùng | `setspn -X`, sửa directory registration |
| `KRB_AP_ERR_MODIFIED` | Ticket decrypt fail hoặc route/SPN/key sai | Kiểm KVNO, keytab, service account, SPN, DNS alias |
| `KRB_AP_ERR_SKEW` | Clock không đồng bộ | NTP, server/client/KDC time, không tự tăng skew |
| `KDC_ERR_ETYPE_NOSUPP` | Encryption types không tương thích | Cập nhật etype policy/keytab/JDK theo chuẩn mạnh |
| `KRB_AP_ERR_REPEAT` | Replay detected | Kiểm GSS replay cache/HA, không tắt bảo vệ |
| `GSSException: Defective token detected` | Token sai, NTLM/Negotiate mechanism mismatch, proxy sửa header | Kiểm header redacted, browser support, GSS logs |
| `KeyTab file not found` | Secret mount/path sai | Kiểm `file:` Resource, quyền file/volume |
| `LoginException` khi accept | SPN principal, JAAS config, KDC realm, keytab | Kiểm stacktrace đã redact và runtime configs |
| 401 sau auth dù keytab đúng | `UserDetailsService` không tìm user/disabled, context persistence | Kiểm mapping username/realm, account state |
| 403 sau SPNEGO thành công | Spring authorities/role/tenant policy | Kiểm `ROLE_REPORT_READER` và resource permissions |
| App login chập chờn qua load balancer | Node versions/keytab/replay/session store khác nhau | So pod labels, keytab KVNO, session repo, DNS route |
| Chỉ lỗi qua CNAME/alias | Client xin ticket cho host khác SPN đã tạo | Cấu hình DNS/SPN canonical identity, test alias |
| Keytab rotation làm fail một nhóm client | Ticket cũ còn dùng key version cũ | Lịch rollover, KDC ticket lifetime, keytab versions |
| SPNEGO login thành công nhưng gọi backend vẫn 401 | Service-to-service delegation là vấn đề riêng | Dùng constrained delegation/KerberosRestTemplate chỉ khi được phê duyệt |
| Đổi mật khẩu domain user không làm session logout | Local app session vẫn active | Revocation/session invalidation policy riêng |
| Thêm `ROLE_ADMIN` từ string domain user | Mapping quyền nguy hiểm | Map account ID/realm/tenant, fail closed |
| Hạ JDK security policy để qua handshake | Etype/krb5/trust issue | Kiểm tương thích và security review, không bật weak crypto |
| Dùng `WWW-Authenticate: Negotiate` trên API stateless | Browser/user agent không có Kerberos creds | Phân biệt API auth vs browser SSO, thiết kế phù hợp |

### 16.1. Chẩn đoán như một cây quyết định

```text
A. Browser đã GET URL HTTPS đúng public host?
  |
  +-- Chưa --> DNS/TLS/redirect/proxy.
  |
  +-- Rồi: nhận 401 WWW-Authenticate: Negotiate?
       |
       +-- Không --> SecurityFilterChain/SpnegoEntryPoint/proxy.
       |
       +-- Có: gửi Authorization: Negotiate token?
             |
             +-- Không --> browser policy/TGT/SPN/KDC.
             |
             +-- Có: SPNEGO filter được gọi?
                   |
                   +-- Không --> filter chain/order/proxy header.
                   |
                   +-- Có: KerberosTicketValidator accept thành công?
                         |
                         +-- Không --> SPN/keytab/KVNO/etype/time/GSS.
                         |
                         +-- Có: UserDetailsService map account?
                               |
                               +-- Không --> identity/realm/disabled state.
                               |
                               +-- Có: SecurityContext được lưu?
                                     |
                                     +-- Không --> repository/session/cookie.
                                     |
                                     +-- Có: Authorization resource/tenant đạt?
                                           |
                                           +-- Không --> đúng 403/deny.
                                           |
                                           +-- Có --> 200 protected resource.
```

**Dừng ở tầng đầu lỗi thật sự.** Một trace có `KRB_AP_ERR_MODIFIED` không được chữa bằng cách thêm user vào local `UserDetailsService`; provider chưa qua crypto validation. Ngược lại, một Kerberos-authenticated user 403 thiếu quyền không nên sửa keytab để “giải quyết 403”.

## 17. Vấn đề nâng cao: delegation, nhiều backend và ứng dụng nhiều realm

### 17.1. Server xác minh ticket khác server đại diện user gọi dịch vụ tiếp

`KerberosServiceAuthenticationProvider` trong bài là **acceptor** cho incoming SPNEGO. Nó **không tự cấp delegated credentials** cho A gọi B. Nếu ứng dụng cần:

```text
Browser/user -> Spring App A -> SQL/HTTP Service B
```

thì phải thiết kế Kerberos **constrained delegation** hoặc cơ chế identity/token exchange phù hợp, quản lý `GSSContext` và delegated credentials. Spring Kerberos có `KerberosRestTemplate` và các hỗ trợ multi-tier nhưng không nên bật `setMultiTier(true)` chỉ vì một endpoint backend trả 401. Delegation mở quyền impersonate user nên cần hạn chế services đích, KDC policy và audit.

### 17.2. Cross-realm trust

Một SPN ở `EXAMPLE.ORG` có thể được users từ realm khác xác thực qua Kerberos trust nếu được cấu hình. Application vẫn phải map principal **cùng realm đã verify**, trạng thái account và membership; không tự cắt `@PARTNER.ORG` rồi cho thành `alice@EXAMPLE.ORG`. KDC trust policy không tự cấp quyền tenant/app.

### 17.3. Web app session và ticket lifetime

Kerberos service ticket có thời hạn, nhưng Spring web app có thể lưu authenticated user trong HttpSession. Ticket hết hạn **không tự invalidate ngay** local session, tùy session policy. Với ứng dụng nhạy cảm:

- Xác định idle/absolute session lifetime và quyền revoke.
- Xem xét reauthentication cho hành động rủi ro cao.
- Bảo vệ cookies `Secure`/`HttpOnly`/`SameSite` và CSRF.
- Không lưu raw service ticket trong session chỉ để “kiểm lại sau”.
- Không coi `klist` ở client là nguồn truth để hủy session backend.
- Khi user bị disable hoặc group thay đổi, cần event-driven revocation/recheck theo SLA, không chờ Kerberos ticket tự hết.

### 17.4. Đừng tự tạo Kerberos/SPNEGO protocol implementation

JDK `java.security.jgss` có API accept token phức tạp; GSS context có thể có nhiều rounds và xuất response token cho client. Hãy dùng Spring Kerberos module/JAAS GSS của JDK hoặc Kerberos client library đã được kiểm thử. Không chỉ Base64-decode rồi đọc ASN.1 tự viết, không bỏ clock-skew/replay validation, không tự lấy mật khẩu KDC từ application.properties.

## 18. Checklist production cho ticket validator và provider

- [ ] `KerberosServiceAuthenticationProvider` thực sự được nối với `SpnegoAuthenticationProcessingFilter` qua `ProviderManager`; không nhầm với `KerberosAuthenticationProvider`.
- [ ] `SunJaasKerberosTicketValidator` (hoặc provider phù hợp JDK) dùng đúng **SPN + keytab** đã quản lý, trùng với service ticket KDC phát cho public web host.
- [ ] Keytab có đúng principal/KVNO/etype và chỉ process service được đọc; không nằm trong repo/image/log/HTTP.
- [ ] SPN owner trong AD/KDC đúng và không trùng; DNS alias/public FQDN được kiểm chứng trên máy client.
- [ ] Kerberos realm/krb5.conf/KDC discovery/time sync/NTP và cross-realm trust được cấu hình đúng.
- [ ] HTTP 401 challenge `WWW-Authenticate: Negotiate` đến browser, `Authorization: Negotiate` được ingress giữ nguyên.
- [ ] Browser policy Integrated Authentication/SSPI/GSS đã test với user thật trong lab.
- [ ] Không nhận raw username, `X-Remote-User` hoặc NTLM fallback làm Kerberos authentication khi chưa có trust contract.
- [ ] Provider kiểm ticket qua GSS/JAAS, có clock-skew/expiry/replay protection, fail closed trên token giả/sai SPN/etype.
- [ ] `UserDetailsService` nạp local user/roles sau xác thực; account disabled/tenant membership và object authorization được enforce.
- [ ] `SecurityContextRepository` và `SessionAuthenticationStrategy` được cấu hình, session fixation và logout/revocation được kiểm thử.
- [ ] Session/TGT/service ticket lifetimes được phân biệt; app không tin Kerberos AP-REQ đã được verify cho mọi request về sau khi session có thể stale.
- [ ] TLS HTTPS đúng certificate public host; cookies/CSRF/CSP phù hợp, không thay Kerberos keytab cho TLS private key.
- [ ] Không dùng debug KRB5/JAAS ghi raw tokens, keytabs, passwords trong production logs; có cơ chế redact và retention.
- [ ] Nhiều pods chia SPN/keytab theo thiết kế, replay cache/risk được đánh giá theo RFC 4120, không mặc định mỗi node an toàn riêng lẻ.
- [ ] Keytab rotation/KVNO/etype có runbook và integration tests trước/sau cutover; không giữ secret đã bị compromise.
- [ ] Spring Security 6.x dùng Kerberos 2.2.x group `org.springframework.security.kerberos`, còn Security 7.x dùng group `org.springframework.security` tương ứng.
- [ ] Đã chạy test normal Negotiate, wrong/missing SPN, wrong keytab, clock skew, revoked user, 403 authorization, session persistence và reverse proxy.
- [ ] Có monitoring theo category: no token, GSS validation failure, local account missing, insufficient role, session save failure, node/realm/SVN changes.
- [ ] Có quy trình điều tra liên hệ KDC administrator, application owner và ingress owner, giữ log đã redacted.
- [ ] Không tự bật delegation/multi-tier hoặc lưu delegated credentials khi nghiệp vụ chỉ cần web SSO.

**Kết luận:** `KerberosServiceAuthenticationProvider` đóng vai trò **cầu nối từ Kerberos service-ticket verification sang Spring Authentication**. Filter đọc SPNEGO token từ HTTP, provider gọi `KerberosTicketValidator` và JAAS/GSS xác minh vé bằng **keytab của đúng SPN**, sau đó `UserDetailsService` tìm local account/GrantedAuthorities; cuối cùng Spring Security mới lập SecurityContext/session và kiểm quyền ứng dụng. **Xác minh Kerberos ticket ≠ tự cấp quyền business**, và một HTTP header có tên “Negotiate” ≠ ticket đã được xác minh. Hệ thống chỉ an toàn khi SPN, keytab, KDC, thời gian, replay, browser/proxy, session và tenant authorization đều được kiểm thử ở đúng lớp.

## 19. Tài liệu tham khảo và phạm vi phiên bản

1. [Spring Security Kerberos – Core Authentication Provider and SPNEGO](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): ví dụ `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, `SpnegoEntryPoint` và `SpnegoAuthenticationProcessingFilter`.
2. [KerberosServiceAuthenticationProvider Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html): `setTicketValidator`, `setUserDetailsService`, kết quả Authentication.
3. [SunJaasKerberosTicketValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): servicePrincipal, keyTabLocation, debug/realm và GSSContext.
4. [SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): đọc Negotiate header, lưu context, session strategy và filter controls.
5. [SpnegoEntryPoint Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): HTTP 401 `WWW-Authenticate: Negotiate`.
6. [Spring Security Kerberos 7.x – Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): **dependency coordinates changed with Spring Security 7** và yêu cầu tương thích Java 17+/Spring Framework.
7. [Maven Central – Kerberos Web 2.2.0](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0): groupId/artifactId/version để chọn Spring Security 6.x.
8. [MIT Kerberos – klist](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html): xem credential cache và keytab.
9. [MIT Kerberos – kvno](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html): xin và hiển thị KVNO của service ticket.
10. [RFC 4120 – The Kerberos Network Authentication Service (V5)](https://www.rfc-editor.org/rfc/rfc4120): service ticket, authenticator, timestamp/clock skew và replay cache.
11. [RFC 4559 – SPNEGO-based Kerberos HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): `Negotiate` HTTP authentication scheme.
12. [Java 17 – GSSContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html): `acceptSecContext`, establishment, dispose, delegated credentials.
13. [Microsoft Learn – Kerberos Authentication Troubleshooting](https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-authentication-troubleshooting-guidance): `KRB_AP_ERR_MODIFIED`, SPN, key types và thời gian.
14. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, session fixation và web session persistence.
15. [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): session, reauthentication và authorization boundaries.
