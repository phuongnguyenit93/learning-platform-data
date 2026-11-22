# Luân chuyển keytab, phiên bản khóa và xử lý khóa không khớp trong Kerberos/SPNEGO

> **Module:** Spring Security – federation. **Nhóm:** Tích hợp Kerberos. Bài học trình bày ý nghĩa **KVNO**, **keytab**, **service principal** và **encryption type** khi một Spring Security SPNEGO service xác thực ticket từ Kerberos KDC; cách thay service keys có kiểm soát trên MIT Kerberos hoặc Microsoft Active Directory; cách cập nhật nhiều pods/JVMs, bảo vệ secret và xử lý lỗi khóa không khớp. Mã Java 17 cuối bài chạy độc lập chỉ **mô phỏng** nguyên lý khớp khóa, không phải Kerberos ticket validator thật. Địa chỉ, tài khoản và key labels là dữ liệu giả.

## 1. Tình huống: KDC cấp vé mới nhưng JVM còn keytab cũ

Ứng dụng được truy cập ở `https://portal.example.org` dùng SPNEGO với service principal:

```text
HTTP/portal.example.org@EXAMPLE.ORG
```

Browser user đã có TGT và xin **service ticket** từ KDC cho SPN này. Phần service ticket dành cho server được KDC mã hóa bằng **long-term service key** của principal. Trước rotation key có phiên bản **KVNO 7**. Quản trị viên đổi password/key của account hoặc principal, khiến KDC bắt đầu cấp ticket mới bằng **KVNO 8**. Trong khi đó JVM Spring Boot trên một số pods vẫn dùng keytab chỉ chứa khóa v7.

Browser gửi:

```http
GET /dashboard HTTP/1.1
Host: portal.example.org
Authorization: Negotiate BASE64_SPNEGO_TOKEN
```

Acceptor không có secret thích hợp để mở AP-REQ nên có thể trả 401, log `KRB_AP_ERR_MODIFIED`, `Message stream modified` hoặc lỗi không tìm được key/enctype. **Không nên kết luận ngay user nhập sai password**. Những phiên local đã authenticated có thể vẫn chạy, và những browsers giữ cached service ticket v7 đôi khi vẫn hoạt động nếu acceptor còn v7.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt KDC, TGT, service ticket, service principal (SPN), keytab, KVNO, enctype và session ứng dụng.
2. Hiểu vì sao keytab có cùng KVNO với KDC nhưng **key bytes sai** vẫn không xác thực được ticket.
3. Đọc keytab bằng `klist -k -e`, lấy service ticket KVNO bằng `kvno`, test decrypt với `kvno -k` khi hỗ trợ.
4. Tránh bẫy `kadmin ktadd` mặc định thay khóa KDC; biết `-norandkey`, `-keepold` dùng khi nào.
5. Phân biệt MIT principal với SPN–account mapping của AD, `ktpass`, `msDS-KeyVersionNumber` và DC replication.
6. Thiết kế rotation v7→v8 cho nhiều pods, giữ old+new bounded grace, restart/reinitialize acceptors và retire old keys.
7. Cấu hình JAAS và Spring `SunJaasKerberosTicketValidator` với secret path an toàn.
8. Chẩn đoán các lỗi principal/KVNO/enctype/secret/realm/DNS/clock/proxy mà không fail-open.
9. Chạy Java 17 demo và kiểm tra stdout chính xác.

## 2. Kiến trúc Kerberos/SPNEGO trong Spring Security

```text
User/browser                  KDC hoặc AD Domain Controller
    |                                      |
    | Có TGT                              |
    | Xin TGS cho HTTP/portal.example.org |
    |------------------------------------->|
    |<-------------------------------------|
    | Nhận service ticket                  |
    | (encrypt bởi service long-term key)  |
    v
Authorization: Negotiate <SPNEGO/AP-REQ>
    |
    v
Reverse proxy -> Spring Boot
    |
    v
SpnegoAuthenticationProcessingFilter
    |
    v
KerberosServiceAuthenticationProvider
    |
    v
SunJaasKerberosTicketValidator / JAAS / JGSS
    |
    +-- servicePrincipal đúng
    +-- keytab entries (principal/KVNO/enctype/key bytes)
    +-- GSS acceptSecContext + protocol validation
    |
    v
Kerberos-authenticated principal
    |
    v
UserDetailsService -> Spring authorities -> local session
```

Một request nhận 401 đầu tiên có thể chỉ là **HTTP Negotiate challenge bình thường**. Lỗi chỉ được kết luận khi browser gửi token dự kiến mà server vẫn challenge/deny hoặc logs chỉ rõ validator thất bại.

### 2.1. Principal không phải URL

Với `https://portal.example.org/dashboard`, SPN thông dụng là `HTTP/portal.example.org@EXAMPLE.ORG`, **không phải** full URL và không có path. Browser có thể canonicalize DNS alias theo OS/realm rules; service principal keytab phải tương ứng với **tên thực tế KDC dùng phát ticket**.

Reverse proxy dùng backend `http://portal-pod:8080` không có nghĩa SPN là `HTTP/portal-pod`. Với virtual hostname, mọi pods thường dùng **cùng service identity/keytab** tương ứng public SPN, trừ khi kiến trúc Kerberos chủ động tách principals.

### 2.2. Đừng nhầm khóa

| Khái niệm | Nơi giữ | Mục đích |
| --- | --- | --- |
| `krbtgt` long-term key | KDC | Cấp/xác minh TGT; rotation riêng, blast radius lớn |
| **Service long-term key** | KDC và **keytab** của acceptor | Encrypt/decrypt phần service ticket dành cho principal |
| Service ticket session key | Kerberos protocol | Bảo vệ authenticator/client-service exchange |
| Spring session cookie/`SecurityContext` | Ứng dụng web | Lưu authentication state sau login; không tự đổi khi keytab đổi |

Keytab không phải SAML public certificate hay OAuth client secret. Nó chứa **secret key material** của Kerberos service principal.

## 3. Keytab và KVNO là gì?

MIT Kerberos định nghĩa keytab là nơi chứa long-term keys cho một hoặc nhiều principals. Mỗi entry thường có **principal, KVNO, encryption type, key bytes và timestamp**.

Ví dụ **mô phỏng** output:

```text
Keytab name: FILE:/run/secrets/kerberos/http.keytab
KVNO Principal
---- -------------------------------------------------------------
   7 HTTP/portal.example.org@EXAMPLE.ORG (aes256-cts-hmac-sha1-96)
   7 HTTP/portal.example.org@EXAMPLE.ORG (aes128-cts-hmac-sha1-96)
   8 HTTP/portal.example.org@EXAMPLE.ORG (aes256-cts-hmac-sha1-96)
   8 HTTP/portal.example.org@EXAMPLE.ORG (aes128-cts-hmac-sha1-96)
```

### 3.1. KVNO là phiên bản key, không phải chứng cứ crypto

**Key Version Number (KVNO)** thay đổi khi principal/service account keys được thay. KDC có thể cấp ticket có version v8; acceptor cần key v8 tương ứng.

| KDC ticket | JVM keytab | Kết quả điển hình |
| --- | --- | --- |
| v7 | v7 | Thành công nếu secret bytes, enctype/principal đúng |
| v8 | chỉ v7 | Không decrypt ticket mới |
| v8 | v7 + v8 | Có thể nhận ticket mới và cached old ticket |
| v8 | file ghi nhãn v8 nhưng secret sai | Integrity/decryption failure |
| v7 cached | chỉ v8 | Ticket cũ có thể bị reject |
| v8 AES256 | chỉ v8 AES128 | Có thể thiếu key đúng enctype |

**Không sửa số KVNO thủ công trong keytab để ép khớp.** Cùng principal/KVNO/enctype chưa đủ nếu khóa được sinh từ password, salt hoặc account khác.

### 3.2. Encryption type (enctype)

Enctype quy định thuật toán/bộ tham số encrypt ticket:

- `aes256-cts-hmac-sha1-96`
- `aes128-cts-hmac-sha1-96`
- Những AES enctypes khác khi cả KDC/JVM/client hỗ trợ
- Legacy `arcfour-hmac`/RC4 và `des-cbc-*` cần tránh theo security policy

Nếu ticket yêu cầu enctype không có trong file, validator có thể báo không tìm thấy key phù hợp. Không tự hạ xuống RC4/DES để giảm 401. Cần kiểm tra config Kerberos, AD supported encryption types, JDK và source key derivation.

### 3.3. Chìa khóa thực và bí mật cần được bảo vệ

Keytab chứa long-term secret keys, không phải chỉ metadata. Người lấy được keytab có thể gây rủi ro giả mạo service hoặc lạm dụng ticket trong phạm vi khóa. Không đưa file vào Git/JAR/container image/CI logs; lưu qua secret manager/Kubernetes Secret với encryption at rest, ACL, minimum runtime permissions, backup retention và audit.

**Không chạy `klist -K` để chia sẻ logs:** MIT `klist -K` hiển thị giá trị encryption keys. Cũng không `cat`, `xxd` hoặc base64 keytab trong ticket hỗ trợ. Dùng `klist -k -e` chỉ xem principal/versions/enctypes.

## 4. Bốn đồng hồ trong key rotation

KDC key transition và rollout ứng dụng không xảy ra atomically:

1. **KDC active key:** thời điểm KDC dùng v8 phát service tickets mới.
2. **Keytab distribution:** khi mỗi pod/VM nhận file chứa v8.
3. **JVM/JAAS runtime:** khi Subject và Kerberos acceptor thực sự nạp keys mới.
4. **Client service ticket lifetime:** browser có thể tiếp tục gửi cached ticket v7.

Do đó rotation routine có thể cần **acceptor keytab chứa v7 và v8 đồng thời** trong giai đoạn grace giới hạn. KDC đổi sang v8 không tự invalidate tất cả client tickets v7. Tuy nhiên KDC giữ old key không có nghĩa file keytab ở acceptor cũng có old key.

**Zero downtime không mặc định được đảm bảo:** khác với public signature-verification cert có thể prepublish, Kerberos keytab chứa secret; nhiều KDC bắt đầu phát v8 ngay khi rotate. Nếu apps chưa có v8, có cửa sổ lỗi. Phải lập change window hoặc dùng staged-key mechanism có hỗ trợ thực tế, không phát biểu chung rằng cứ rollout là không gián đoạn.

## 5. Kiểm tra read-only trước khi thay khóa

### 5.1. Lập inventory

```text
Public URL:     https://portal.example.org
Expected SPN:   HTTP/portal.example.org@EXAMPLE.ORG
Keytab path:    /run/secrets/kerberos/http.keytab
KDC type:       MIT KDC hoặc Active Directory
Service owner:  svcPortal / principal admin
Pods:           portal-a, portal-b, portal-c
JDK:            17
Secret version:  v7
```

Tên giả lập. Kiểm tra file **đang mount và đang được JVM đọc**, không chỉ bản file bên ngoài container.

### 5.2. Liệt kê keytab trên Linux/MIT

```bash
klist -k -e /run/secrets/kerberos/http.keytab
klist -k -t -e /run/secrets/kerberos/http.keytab
```

`-k` list keytab keys, `-e` hiển thị enctypes, `-t` hiển thị timestamps. Không thêm `-K` khi lưu logs.

### 5.3. Hỏi KDC về service ticket version

Từ **test client** có Kerberos credentials hợp lệ:

```bash
kvno HTTP/portal.example.org@EXAMPLE.ORG

# Nếu MIT Kerberos version hỗ trợ, thử decrypt ticket với file.
kvno -k /run/secrets/kerberos/http.keytab \
     HTTP/portal.example.org@EXAMPLE.ORG
```

`kvno` xin service ticket và in key version; `kvno -k` còn thử decrypt với keytab, giúp kiểm tra **secret bytes**, không chỉ nhãn KVNO. Tùy KDC/credentials/cache và tool release, cần bảo đảm thật sự test ticket mới thay vì ticket cũ trong cache.

`kinit -k -t <keytab> <principal>` có thể kiểm tra việc lấy initial credentials với service key, nhưng **không hoàn toàn thay** HTTP SPNEGO acceptor test với browser/AP-REQ và Spring Security. Không xóa credentials cache hàng loạt của users; dùng test identity riêng.

### 5.4. Kiểm tra cache của test client

```bash
klist -e
kvno HTTP/portal.example.org@EXAMPLE.ORG
```

Một cached v7 ticket có thể vẫn được browser gửi sau KDC đã active v8. Khi chẩn đoán, phân biệt cached old ticket với ticket mới issue; không khẳng định chỉ một lần test user pass là mọi client tickets sẽ pass.

## 6. Quy trình routine rotation v7 → v8

### 6.1. Chuẩn bị

- Chốt principal/realm/KDC backend, account owners và toàn bộ services dùng cùng long-term key.
- Ghi current KVNO/enctypes bằng KDC và keytab, xác nhận SPN uniqueness.
- Đo service ticket maximum lifetime và AD/DC replication timelines nếu có.
- Backup file v7 an toàn trong vault, hạn chế read access, không lộ secret.
- Kiểm thử trước trên staging realm; dựng rollout automation và canary SPNEGO probes.
- Xác định cách nhận v8 key từ KDC/AD, ai có quyền, có cần chấp nhận maintenance window.
- Thống nhất grace cutoff, rollback/incident path, version manifest và approvals.

### 6.2. Cutover thực tế

```text
T0: KDC active v7; mọi JVM accept v7
        |
T1: KDC admin đổi key sang v8 (KDC có thể phát v8 ngay)
        |
T2: Nhận v8 keytab an toàn; kết hợp v7+v8 nếu routine grace
        |
T3: Distrib/mount secret v7+v8 -> all pods
        |
T4: Reinitialize JAAS credentials hoặc rolling restart JVM
        |
T5: Canary SPNEGO mới v8 PASS trên mọi pod, old cached v7 PASS
        |
T6: Chờ hết bounded grace, retire v7 khỏi mọi runtime/vault copies
```

**T1–T4 có thể có khoảng gián đoạn.** Không có cách chung để KDC và tất cả pods cùng đổi atomically. Nếu KDC/secret tooling hỗ trợ safe pre-provisioning/dual-key protocol, triển khai theo tài liệu cụ thể; nếu không, kế hoạch phải phản ánh downtime risk.

### 6.3. Overlap có giới hạn, emergency revoke thì không

Giữ v7+v8 cho phép acceptor giải **tickets v7 đã cấp trước rotation** và tickets v8 mới, nếu ticket còn hợp lệ. Không giữ old v7 vô hạn vì kéo dài blast radius. Nếu v7 **bị lộ/compromise**, không giữ overlap như routine: revoke key cũ theo incident response và chấp nhận reauthentication/disruption.

### 6.4. Rollback không chỉ là rollback container image

Nếu KDC active v8 mà rollback app image quay lại keytab chỉ v7, login mới sẽ fail. Khi rollback, phải giữ runtime keytab v8-compatible hoặc điều phối KDC change riêng với admin, xét cached tickets/DC replication. Không rotate KDC thêm lần nữa chỉ để sửa lỗi secret rollout.

## 7. MIT Kerberos: lưu ý đặc biệt với ktadd

### 7.1. ktadd mặc định có thể tạo khóa mới và tăng KVNO

Ví dụ lệnh MIT `kadmin`:

```text
kadmin: ktadd -k /secure/keytabs/portal-new.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG
```

**CẢNH BÁO: LỆNH CÓ SIDE EFFECT TRÊN KDC.** MIT `ktadd` mặc định randomize keys và version, không phải chỉ “xuất lại file”. Nếu hai admin cùng chạy không điều phối, người A tạo v8, người B lại tạo v9; những pods vừa nhận v8 lập tức stale. Cần change lock, audit và owner KDC.

### 7.2. ktadd -norandkey

Nếu chính sách KDC và quyền cho phép, dùng option:

```text
kadmin: ktadd -norandkey \
  -k /secure/keytabs/portal-export.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG
```

MIT docs: `-norandkey` không randomize keys, không đổi KVNO; dùng để export current key material. **Vẫn là secret export**, không phải lệnh read-only về confidentiality. Không kết hợp `-norandkey` với `-e`; verify version/backend/permissions.

### 7.3. KDC -keepold không tự đưa old key vào ứng dụng

Một lệnh MIT thay khóa KDC có thể là:

```text
kadmin: change_password -randkey -keepold \
  HTTP/portal.example.org@EXAMPLE.ORG
```

**Đây cũng là lệnh làm thay đổi KDC key**, không được chạy thử trong production. `-keepold` giữ previous KDC keys theo policy, nhưng acceptor muốn mở cached v7 ticket vẫn phải có **đúng v7 key bytes trong keytab**. Đừng nhầm việc KDC giữ old keys với JVM tự có old key. MIT docs nhắc `-keepold` đặc biệt cho `krbtgt`, không máy móc sao chép mọi krbtgt rotation procedure sang HTTP service principal.

### 7.4. Ghép keytabs khi cần giữ v7+v8

Với hai keytab files đã được cấp an toàn, MIT `ktutil` hỗ trợ:

```text
$ ktutil
ktutil: read_kt /secure/keytabs/portal-v7.keytab
ktutil: read_kt /secure/keytabs/portal-v8.keytab
ktutil: list -e
ktutil: write_kt /secure/keytabs/portal-v7-v8.keytab
ktutil: quit
```

`ktutil` thao tác entries ở filesystem, không đổi KDC. **Đây là các lệnh vận hành nhạy cảm**, không chạy trước khi có quyền/backup. Không dùng `list -k` vì có thể in key bytes. Sau ghép:

```bash
klist -k -e /secure/keytabs/portal-v7-v8.keytab
```

Cần kiểm tra **thực tế** `kvno -k` hoặc Java GSS authentication mới. Một file chứa v7/v8 entries chưa chứng minh secret bytes chính xác; và JVM đang chạy chưa chắc đã reload file.

## 8. Microsoft AD: SPN, ktpass, key version và replication

### 8.1. SPN phải thuộc đúng account

KDC trên AD mã hóa service ticket bằng key của **AD account sở hữu SPN**. Nếu `HTTP/portal.example.org` bị gắn nhầm hoặc trùng, keytab sinh từ account khác không thể decrypt. Một dấu hiệu có thể là `KRB_AP_ERR_MODIFIED` dù KVNO nhìn tương tự.

Read-only commands:

```powershell
setspn -Q HTTP/portal.example.org
setspn -L EXAMPLE\svcPortal
```

Không thêm cùng SPN lên nhiều accounts để “load balancing”. Tất cả pods của public SPN cần khớp một account/key strategy rõ.

### 8.2. msDS-KeyVersionNumber

Microsoft có attribute `msDS-KeyVersionNumber` biểu thị version của current Kerberos key cho account. Nếu có module ActiveDirectory:

```powershell
Get-ADUser -Identity svcPortal -Properties "msDS-KeyVersionNumber","msDS-SupportedEncryptionTypes" | Select-Object SamAccountName,"msDS-KeyVersionNumber","msDS-SupportedEncryptionTypes"
```

Đây là lệnh **read-only** cho user service account. Computer/gMSA accounts dùng cmdlet tương ứng. Attribute này là **constructed**; DC replication lag có thể khiến các DC cấp keys/versions khác nhau trong giai đoạn rotation. Kiểm tra actual DC/KDC phục vụ clients và replication health trước kết luận.

### 8.3. ktpass có thể thay đổi account/password

Microsoft `ktpass` không chỉ “inspect keytab”; nó hỗ trợ `/princ`, `/mapuser`, `/pass`, `/crypto`, `/kvno`, `/out` và có thể ảnh hưởng mapping/secret. Ví dụ **cấu trúc lệnh chỉ để đọc hiểu**, không thực thi khi chưa được admin phê duyệt:

```text
ktpass /out C:\secure\portal-next.keytab
       /princ HTTP/portal.example.org@EXAMPLE.ORG
       /mapuser EXAMPLE\svcPortal
       /crypto AES256-SHA1
       /ptype KRB5_NT_PRINCIPAL
       /pass *
```

`/pass *` dùng prompt; không đưa password plaintext trong command line/history/CI logs. Microsoft docs nói `/kvno` default là 1 khi không cấu hình, nên **không mặc định nhãn KVNO từ file sẽ bằng AD current KVNO**. Không ép KVNO bằng số đoán: version trùng mà bytes sai vẫn fail, và ktpass có thể reset/mapping keys tác động nhiều services.

### 8.4. Những nguyên nhân AD cần kiểm tra

- SPN ownership/trùng SPN và service account thực.
- Password vừa đổi nhưng keytab sinh từ password cũ.
- AES salt/key derivation/casing/principal mismatch.
- Account `msDS-SupportedEncryptionTypes` khác enctype Java/KDC phát.
- DC replication chưa hoàn tất.
- Browser xin ticket cho DNS alias SPN khác.
- Java Subject/keytab cached hoặc runtime path sai.
- gMSA managed rotation có lifecycle riêng; không thay nó bằng `ktpass` thủ công.

**Không giảm Kerberos security xuống RC4/DES để vượt lỗi AES.** Sửa account, salt, enctype, secret source và runtime keytab.

## 9. Java JAAS và Spring Security Kerberos

### 9.1. Java acceptor login configuration

Một JAAS config dành cho service acceptor:

```properties
KerberosServiceAcceptor {
  com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    debug=false;
};
```

`useKeyTab` và `keyTab` chỉ file; `principal` chỉ service acceptor principal; `storeKey` cho Subject giữ service credentials; `isInitiator=false` phù hợp server acceptor; `doNotPrompt=true` không cần password tương tác. Đây là **JAAS syntax**, không phải Java program. Không dùng `principal="*"` để chữa sai SPN khi chưa review trust scope.

### 9.2. Spring Security Kerberos components

| Component | Nhiệm vụ |
| --- | --- |
| `SpnegoEntryPoint` | Gửi HTTP Negotiate challenge |
| `SpnegoAuthenticationProcessingFilter` | Nhận `Authorization: Negotiate` |
| `KerberosServiceAuthenticationProvider` | Validate service ticket và tạo Authentication |
| `SunJaasKerberosTicketValidator` | Dùng JAAS/JGSS + keytab để xác minh |
| `UserDetailsService` | Map principal thành app authorities |
| `KerberosAuthenticationProvider` | Nhánh Kerberos client/username-password riêng, không thay acceptor |

Spring Security Kerberos là **extension** riêng, khác Spring Security SAML2/OIDC/CAS. Phải kiểm tra version tương thích Spring Boot, Security, JDK và Jakarta Servlet.

### 9.3. Ví dụ bean Spring

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.sun
        .SunJaasKerberosTicketValidator;

@Configuration
public class KerberosAcceptorConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator() {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.example.org@EXAMPLE.ORG");
        validator.setKeyTabLocation(
                new FileSystemResource(
                    "/run/secrets/kerberos/http.keytab"));
        validator.setDebug(false);
        return validator;
    }
}
```

Đây là Spring configuration class, **không chạy độc lập bằng javac/java**. Cần full application, `spring-security-kerberos` dependency và authentication filter/provider/entry point wiring. Lưu keytab ở external file mount, không nhúng vào JAR/classpath.

### 9.4. Provider/filter fragment

```java
import org.springframework.security.kerberos.authentication
        .KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.web.authentication
        .SpnegoAuthenticationProcessingFilter;

// Fragment: ticketValidator, userDetailsService, authenticationManager
// là các beans đã cấu hình trong Spring.
KerberosServiceAuthenticationProvider provider =
        new KerberosServiceAuthenticationProvider();
provider.setTicketValidator(ticketValidator);
provider.setUserDetailsService(userDetailsService);

SpnegoAuthenticationProcessingFilter filter =
        new SpnegoAuthenticationProcessingFilter();
filter.setAuthenticationManager(authenticationManager);
```

`AuthenticationManager` và `SecurityFilterChain` cần nối theo API release cụ thể. Đừng nhầm GSS accept thành business authorization: Spring có thể xác thực principal hợp lệ nhưng UserDetailsService từ chối disabled account hoặc thiếu role.

### 9.5. JVM có tự reload file keytab?

Không được **giả định** thay file là JVM tự nhận v8. JAAS `LoginContext`/`Subject` hoặc validator có thể giữ credentials đã đọc. Quy trình dễ kiểm soát: atomic file replacement, **reinitialize acceptor credentials hoặc rolling restart JVM**, test ticket mới. `setRefreshKrb5Config(true)` nếu có ở validator liên quan Kerberos config refresh, không cam kết reload secret keytab hiện nằm trong Subject.

Debug trong môi trường test:

```text
-Dsun.security.krb5.debug=true
-Djava.security.krb5.conf=/etc/krb5.conf
-Djava.security.auth.login.config=/etc/security/jaas.conf
```

Oracle document `sun.security.krb5.debug`; bật tạm, giới hạn log access và redact. Không in AP-REQ token, keytab, ticket ciphertext hoặc password.

## 10. Multi-node và triển khai an toàn

### 10.1. Secret mount vs effective JVM state

Một Kubernetes Secret đã cập nhật không chứng minh:

- Pod nhận volume revision mới (đặc biệt `subPath` có semantics update khác).
- Runtime có quyền đọc file version mới.
- JVM JAAS credentials đã reload.
- Tất cả pods/regions dùng **cùng KVNO/enctype/key bytes**.
- KDC/DC đã chuyển key và replicate đồng nhất.

Gắn secret version/expected KVNO vào deployment manifest và monitoring **không kèm secret**, dùng canary real SPNEGO readiness. Không chỉ check `/health` trả 200.

### 10.2. Rollout checklist

1. Phân phối approved keytab v8 qua secret manager/encrypted channel, không Git/image.
2. Giữ v7+v8 trong bounded routine grace khi policy cho phép.
3. Thay keytab atomically, hạn chế read permissions.
4. Restart/reinitialize Spring Kerberos acceptors có kiểm soát.
5. Test fresh v8 ticket trên **từng pod/region**.
6. Test cached v7 ticket nếu cần backward compatibility.
7. Drain stale pods, không tự đổi KDC key thêm lần nữa.
8. Monitor 401/GSS integrity failures theo pod, realm/service ID allowlist.
9. Retire v7 sau ticket lifetime/grace, xử lý vault/backups.
10. Nếu v7 compromise, revoke ngay, không giữ overlap.

### 10.3. Existing sessions có thể che lỗi

Người dùng đã authenticated trong `HttpSession` của Spring có thể tiếp tục truy cập app dù new SPNEGO authentication đang hỏng. Test phải dùng **fresh session/new ticket** để xác nhận. Ngược lại, rotate keytab không tự xóa mọi existing app sessions: nếu incident compromise, cần session/token revocation theo threat model.

## 11. Troubleshooting ma trận

| Triệu chứng | Khả năng | Bước xác minh |
| --- | --- | --- |
| `KRB_AP_ERR_MODIFIED` / “Message stream modified” | Key bytes sai, SPN thuộc account khác, enctype/KVNO mismatch | KDC service ticket + keytab + AD SPN owner |
| `Cannot find key of appropriate type` | Thiếu enctype/principal/version | `klist -k -e`, KDC ticket enctype |
| Key version incorrect | Ticket KVNO mới nhưng file old | `kvno` và keytab entries |
| Integrity check on decrypted field failed | Sai secret/salt/password source/realm | Account owner, key derivation, controlled decrypt test |
| `KDC_ERR_ETYPE_NOSUPP` | Không có enctype chung | KDC/account/JDK crypto policies |
| Server not found in Kerberos database | SPN/realm sai | MIT principal hoặc `setspn -Q` |
| Clock skew too great | Clock sync issue | NTP/chrony/DC time |
| Pod A pass, pod B fail | Keytab mount/JAAS cached khác nhau | Per-pod inspection/test |
| Chỉ DNS alias lỗi | Client yêu cầu SPN alias khác | Hostname/canonicalization/registered SPN |
| Chỉ cached old tickets fail | V7 retired quá sớm | Ticket lifetime và overlap policy |
| File v8 trên disk, JVM vẫn fail | Subject/validator cached v7 | Reinitialize/restart |
| Browser không có Negotiate token | Browser/client realm/policy hoặc proxy strip header | Check presence, không log token |
| Kerberos authenticated nhưng HTTP 403 | Authorization/role/user mapping | UserDetailsService, Spring policies |
| AD sau password change lỗi không đều | DC replication lệch | DC-specific key/version tests |
| MIT sau export tăng version bất thường | `ktadd` tạo key mới | KDC admin audit |

Không quy mọi exception về KVNO; **principal, enctype, key bytes, KDC, ticket, JVM, proxy và authorization** đều phải đúng.

### 11.1. Quy trình xử lý một sự cố 401

1. Xác nhận browser đã gửi `Authorization: Negotiate`, không nhầm initial challenge.
2. Kiểm tra expected public SPN và realm.
3. `klist -k -e` trên **mỗi pod** để xem effective file entries, không `-K`.
4. `kvno` từ test client để đọc ticket KVNO và, nếu hỗ trợ, `kvno -k` kiểm tra decrypt.
5. Trên AD, `setspn -Q`, current msDS-KeyVersionNumber và DC replication.
6. Trên MIT, xem admin history có `ktadd` không `-norandkey` hay `change_password` ngoài kế hoạch.
7. Nếu KVNO/enctype có vẻ đúng vẫn fail, điều tra wrong password/salt/key bytes/account owner/JVM cache.
8. Deploy verified keytab new, restart/reinitialize acceptors, test thực.
9. Không đổi KDC key liên tiếp, không bật weak enctype, không fail-open sang anonymous.
10. Khi ổn định, monitor và retire key old theo approved schedule.

## 12. Java 17 tự chạy: mô phỏng KVNO/keytab rollout

Ví dụ chỉ mô phỏng logic **matching principal + KVNO + enctype + secret bytes** bằng field `keyTag` (ký hiệu giả). Kerberos thật không so một string keyTag trong ticket; JGSS dùng cryptography, ticket checks, replay/clock policies. Mục tiêu là chứng minh **cùng KVNO nhưng secret sai vẫn fail** và **pod chưa có v8 vẫn fail**.

Lưu file `KerberosKeytabRotationDemo.java`:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class KerberosKeytabRotationDemo {

    record Key(String principal, int kvno, String enctype,
               String keyTag) {}

    record Ticket(String principal, int kvno, String enctype,
                  String keyTag) {}

    static final class Kdc {
        private Key activeKey;

        Kdc(Key key) {
            activeKey = key;
        }

        void rotateTo(Key next) {
            activeKey = next;
        }

        Ticket issueServiceTicket() {
            return new Ticket(activeKey.principal(),
                    activeKey.kvno(), activeKey.enctype(),
                    activeKey.keyTag());
        }
    }

    static final class Acceptor {
        private final Set<Key> keytab = new HashSet<>();

        Acceptor(Key... entries) {
            keytab.addAll(Arrays.asList(entries));
        }

        void install(Key key) {
            keytab.add(key);
        }

        void retire(Key key) {
            keytab.remove(key);
        }

        boolean accepts(Ticket ticket) {
            return keytab.stream().anyMatch(key ->
                key.principal().equals(ticket.principal())
                && key.kvno() == ticket.kvno()
                && key.enctype().equals(ticket.enctype())
                && key.keyTag().equals(ticket.keyTag()));
        }
    }

    public static void main(String[] args) {
        String principal =
                "HTTP/portal.example.org@EXAMPLE.ORG";
        String enctype = "aes256-cts-hmac-sha1-96";

        Key old = new Key(principal, 7, enctype, "secret-v7");
        Key next = new Key(principal, 8, enctype, "secret-v8");
        Kdc kdc = new Kdc(old);
        Acceptor podA = new Acceptor(old);
        Acceptor podB = new Acceptor(old);

        Ticket cachedOld = kdc.issueServiceTicket();
        System.out.println("Before rotation: "
                + (podA.accepts(cachedOld)
                && podB.accepts(cachedOld)));

        kdc.rotateTo(next);
        Ticket latest = kdc.issueServiceTicket();
        System.out.println("New ticket KVNO: " + latest.kvno());
        System.out.println("Old-only pod accepts v8: "
                + podA.accepts(latest));

        podA.install(next);
        System.out.println("Updated pod A accepts v8: "
                + podA.accepts(latest));
        System.out.println("Stale pod B accepts v8: "
                + podB.accepts(latest));

        podB.install(next);
        System.out.println("Both pods accept v8: "
                + (podA.accepts(latest) && podB.accepts(latest)));
        System.out.println("Cached v7 still accepted: "
                + (podA.accepts(cachedOld)
                && podB.accepts(cachedOld)));

        Acceptor wrongKey = new Acceptor(
                new Key(principal, 8, enctype, "different-secret"));
        System.out.println("Same KVNO, wrong key: "
                + wrongKey.accepts(latest));

        Ticket wrongEnctype = new Ticket(
                principal, 8, "arcfour-hmac", "secret-v8");
        System.out.println("Wrong enctype: "
                + podA.accepts(wrongEnctype));

        podA.retire(old);
        podB.retire(old);
        System.out.println("Old cached v7 after retire: "
                + podA.accepts(cachedOld));
        System.out.println("New v8 after retire: "
                + podA.accepts(latest));

        Ticket wrongPrincipal = new Ticket(
                "HTTP/other.example.org@EXAMPLE.ORG",
                8, enctype, "secret-v8");
        System.out.println("Wrong principal: "
                + podA.accepts(wrongPrincipal));
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac KerberosKeytabRotationDemo.java
java KerberosKeytabRotationDemo
```

Stdout chính xác:

```text
Before rotation: true
New ticket KVNO: 8
Old-only pod accepts v8: false
Updated pod A accepts v8: true
Stale pod B accepts v8: false
Both pods accept v8: true
Cached v7 still accepted: true
Same KVNO, wrong key: false
Wrong enctype: false
Old cached v7 after retire: false
New v8 after retire: true
Wrong principal: false
```

### 12.1. Phân tích mô hình

- KDC active v7: pod A/B đều có key v7, accept cached ticket cũ.
- KDC đổi v8 trước khi pods đổi: ticket mới fail ở cả hai nếu v8 chưa có.
- Chỉ pod A cài v8: A pass, B fail, tạo hiện tượng intermittent 401.
- Cả pods có v7+v8: new ticket pass, cached v7 cũng có thể pass trong grace.
- File ghi v8 nhưng keyTag sai: fail. **Version number không đủ chứng minh secret đúng**.
- Wrong enctype/SPN: fail dù KVNO khớp.
- Retire v7: cached old ticket không còn được accept; v8 vẫn pass.

**Giới hạn:** chương trình không dùng KDC thật, không decrypt AP-REQ, không kiểm tra expiry/replay/clock/session key, không parse binary keytab, không phân quyền user. Không dùng `Acceptor.accepts` thay `SunJaasKerberosTicketValidator.validateTicket` production.

## 13. Kiểm thử âm tính và nghiệm thu

| Test | Kỳ vọng |
| --- | --- |
| KDC v7, pods v7 | New Kerberos auth pass |
| KDC v8, pod chỉ v7 | V8 ticket reject, alert |
| KDC v8, pods v7+v8 | New v8 ticket pass nếu crypto đúng |
| Client cached v7, acceptor v7+v8 | Pass trong permitted grace nếu ticket còn hạn |
| Client cached v7, acceptor chỉ v8 | Reject |
| KVNO 8 đúng nhưng secret sai | Reject/integrity error |
| AES256 ticket, keytab thiếu AES256 | Reject, không hạ xuống RC4/DES |
| Wrong servicePrincipal/realm | Reject |
| SPN trỏ AD account khác | Decrypt fail, cần fix ownership |
| AD DC replication stale | Test detect discrepancy |
| MIT ktadd bị chạy lại ngoài kế hoạch | Test/audit detect unexpected KVNO |
| JVM Subject còn key cũ sau file replace | Restart/reinitialize requirement detected |
| Secret path không tồn tại hoặc permissions deny | Fail closed, readiness fail |
| Pod A updated, B stale | Per-pod tests phát hiện |
| Rollback image kèm v7-only keytab khi KDC v8 | QA fail |
| Keytab lộ trong repo/CI/backup | Security QA fail + incident |
| Local Spring authenticated session vẫn hoạt động | Không lấy làm proof new SPNEGO acceptor pass |
| Successful GSS nhưng disabled app account | App deny theo policy |
| Wrong tenant principal/role mapping | Không cấp cross-tenant access |

### 13.1. Test HTTP Negotiate thực tế

Trong lab với test account đã có Kerberos credentials, `curl` có GSSAPI support:

```bash
curl --negotiate -u : \
     --silent --show-error --output /dev/null \
     --write-out '%{http_code}\n' \
     https://portal.example.org/protected
```

Tránh `--verbose` hoặc traces thu raw Authorization header, ticket/username. HTTP 200 không tự chứng minh Kerberos auth nếu route public/fallback, cần kiểm tra mechanism qua safe server telemetry. Test nên route đến từng pod/region trong controlled environment.

## 14. Khi keytab bị lộ: emergency khác routine overlap

Một secret keytab bị rò rỉ có thể đã bị sao chép. Xóa file không thu hồi bản sao. Incident response:

1. Cô lập source leak, giới hạn secret store/CI/repository access.
2. Xác định tất cả SPNs/accounts và pods cùng sử dụng key.
3. KDC/AD admin revoke hoặc đổi long-term service key theo incident procedure.
4. Phân phối new keytab và restart/reinitialize acceptors, **không giữ compromised old key trong grace**.
5. Đánh giá cached tickets, service sessions, delegated credentials và unauthorized activity.
6. Audit logs an toàn, thay IAM/ACL, rà soát backup/secret history.
7. Có thể phải chấp nhận downtime/re-login thay vì fail-open.

Không tự tăng ticket lifetime hoặc bật weak enctype để “giảm lỗi” sau compromise.

## 15. Checklist production

- [ ] Principal, realm, service account và public SPN xác minh đúng.
- [ ] Keytab đúng principal/KVNO/enctype/**key bytes**, không chỉ file name/version.
- [ ] MIT ktadd/AD ktpass được KDC owner kiểm soát, không chạy như lệnh read-only.
- [ ] KDC current KVNO và AD DC replication được kiểm tra.
- [ ] File secret được mã hóa/lưu ngoài source code, ACL tối thiểu, không log raw bytes.
- [ ] Mọi pods nhận same approved keytab revision, không drift.
- [ ] JAAS acceptor reload/restart có kiểm chứng bằng fresh v8 ticket.
- [ ] Browser cached v7 tickets được xử lý theo bounded grace hoặc revoke policy.
- [ ] Test negative KVNO/enctype/SPN/key bytes mismatch.
- [ ] Không bật RC4/DES hay anonymous fallback để che lỗi.
- [ ] Local Spring Security sessions và authorization có policy riêng.
- [ ] Rollback image không làm quay về keytab v7-only khi KDC v8.
- [ ] Retire v7 đúng lịch và xử lý backups, audit, monitoring.
- [ ] Có runbook emergency revoke khi keytab bị lộ.

## 16. Câu hỏi ôn tập

**1. KVNO giống nhau có đủ bảo đảm ticket decrypt được không?**  
Không. Secret bytes, enctype và principal phải khớp thực tế.

**2. Keytab là public certificate?**  
Không, là long-term secret key store cho Kerberos principal.

**3. Vì sao user cũ login được nhưng user mới fail sau rotation?**  
Client cached old service ticket có thể còn hợp lệ; KDC đã phát new ticket KVNO khác.

**4. Tại sao MIT ktadd có thể phá production?**  
Nó mặc định randomize keys/thay KVNO; không chỉ export file.

**5. ktadd -norandkey có làm gì?**  
Export current key material không randomize/đổi KVNO khi version và admin policy hỗ trợ.

**6. KDC giữ old keys có tự cho JVM decrypt old tickets?**  
Không; acceptor cũng phải có old key bytes trong keytab.

**7. Có thể sửa nhãn KVNO trong keytab cũ thành KVNO mới?**  
Không. Số thay đổi không sinh đúng key material.

**8. AD msDS-KeyVersionNumber cho biết gì?**  
Version key hiện tại của account; phải kiểm tra DC replication và đúng SPN/account.

**9. klist -k -e và klist -K khác nhau?**  
Lệnh đầu xem entries/enctypes; `-K` có thể in actual secret keys.

**10. Thay keytab file có bảo đảm JVM đang dùng file mới?**  
Không. JAAS/Subject có thể cache credentials; reinitialize/restart và E2E test.

**11. Service account compromise có nên giữ old+new grace?**  
Không. Revoke emergency, chấp nhận reauthentication nếu cần.

**12. Spring Security Kerberos dùng gì để validate token?**  
`SunJaasKerberosTicketValidator` được nối vào `KerberosServiceAuthenticationProvider` và `SpnegoAuthenticationProcessingFilter` theo cấu hình.

## 17. Tài liệu chuẩn và tham khảo

- [MIT Kerberos — Keytab](https://web.mit.edu/kerberos/krb5-latest/doc/basic/keytab_def.html): principal, KVNO, enctype và secret key entries.
- [MIT Kerberos — klist](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html): `-k`, `-e`, `-t`, cảnh báo `-K`.
- [MIT Kerberos — kvno](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html): KDC service ticket KVNO và `-k` decrypt check.
- [MIT Kerberos — kadmin](https://web.mit.edu/kerberos/krb5-latest/doc/admin/admin_commands/kadmin_local.html): `ktadd`, `-norandkey`, `change_password -keepold`, `purgekeys`.
- [MIT Kerberos — ktutil](https://web.mit.edu/kerberos/krb5-latest/doc/admin/admin_commands/ktutil.html): đọc/ghi/ghép keytabs.
- [Microsoft Learn — ktpass](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ktpass): AD keytab generation, SPN, crypto and KVNO options.
- [Microsoft Learn — msDS-KeyVersionNumber](https://learn.microsoft.com/en-us/windows/win32/adschema/a-msds-keyversionnumber): account Kerberos key version.
- [Spring Security Kerberos Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SPNEGO/Kerberos auth provider, SunJaasKerberosTicketValidator config.
- [Spring Security Kerberos Ticket Validator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): keyTabLocation/servicePrincipal/debug.
- [Oracle Java 17 — Krb5LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html): JAAS acceptor login options.
- [Oracle — Troubleshooting JGSS](https://docs.oracle.com/en/java/javase/26/security/troubleshooting-jgss.html): Kerberos debug behavior.
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ keytabs/long-term credentials.

**Ghi nhớ:** Kerberos service acceptor phải có **đúng keytab secret khớp principal, KVNO, enctype và bytes khóa** KDC dùng cho service ticket. KDC đổi version trước khi ứng dụng nhận keytab mới sẽ tạo lỗi; cached old tickets tạo nhu cầu bounded old+new acceptor overlap trong routine rotation. MIT `ktadd` và AD `ktpass` có thể tác động chính KDC/account, vì vậy phải điều phối, không chạy như công cụ đọc. Cần verify file và JVM runtime trên mọi pods, test SPNEGO thật, retire old đúng hạn; khi compromised key phải revoke, không giữ grace hoặc tắt validation.