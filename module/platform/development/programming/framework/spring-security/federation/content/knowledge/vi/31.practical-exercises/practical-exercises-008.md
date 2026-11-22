# Tích hợp SPNEGO với keytab dịch vụ trong môi trường Kerberos thử nghiệm

> **Module:** Spring Security – federation · **Nhóm:** Thực hành tổng hợp. Bài này dựng một phòng lab Kerberos V5 có KDC, tài khoản thử nghiệm, HTTP service principal, keytab, một ứng dụng Spring Security nhận **SPNEGO / HTTP Negotiate** và bộ kiểm thử từ trình duyệt, `curl`, Java 17. Phân biệt rõ **ticket của người dùng**, **keytab bí mật của dịch vụ**, **HTTP principal/SPN**, **xác thực Kerberos**, **Spring Security Authentication** và **quyền truy cập nội bộ**. Các lệnh thay đổi KDC chỉ dùng trong realm LAB được phép quản trị. Ví dụ server Spring là fragment yêu cầu dependencies và môi trường Kerberos thực; ví dụ Java 17 policy ở phần 18 có thể biên dịch/chạy độc lập nhưng không tự xác minh GSS-API.

## 1. Bài toán và kết quả cần đạt

Một người dùng đã đăng nhập máy trạm vào realm `LAB.EXAMPLE.TEST`, truy cập `https://portal.lab.example.test/reports`. Trình duyệt muốn đưa ticket Kerberos tới Java web application để SSO, không nhập lại mật khẩu. Java server phải chứng minh nó là dịch vụ `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` nhờ keytab được cấp **bởi KDC của lab**. Spring Security chuyển kết quả GSS thành principal, áp các điều kiện tài khoản và quyền `ROLE_REPORT_VIEWER` rồi mới cấp dữ liệu.

Các tiêu chí nghiệm thu:

1. KDC/realm hoạt động; user test `student1@LAB.EXAMPLE.TEST` có thể `kinit` và `klist`.
2. KDC có đúng service principal `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST`.
3. Keytab dịch vụ chứa key/KVNO phù hợp; file chỉ ứng dụng được đọc và **không nằm trong Git/JAR/log**.
4. SPNEGO endpoint không xác thực trả `401` kèm `WWW-Authenticate: Negotiate`.
5. Trình duyệt hoặc `curl --negotiate` dùng ticket đã có để gửi `Authorization: Negotiate ...`.
6. Spring Security Kerberos validator dùng **đúng keytab + service principal** để accept AP token.
7. Principal `student1@LAB.EXAMPLE.TEST` chỉ được gán local authorities do ứng dụng cho phép; không tự thành administrator.
8. User thiếu quyền hoặc đã bị khóa vẫn bị từ chối tài nguyên mặc dù Kerberos xác thực thành công.
9. Sai FQDN/SPN, KVNO, enctype, giờ hệ thống, principal hoặc keytab bị loại bỏ và có chẩn đoán cụ thể.
10. App nhiều pods, TLS reverse proxy, cookie/session và keytab rotation được kiểm thử trong điều kiện có kiểm soát.

**Mục tiêu không phải** viết lại giao thức Kerberos bằng Java. Phần cryptographic accept/verify phải dùng Java GSS-API/JAAS qua Spring Security Kerberos hoặc framework đã được kiểm chứng.

## 2. Sơ đồ dòng tin cậy: KDC, client, browser, SPNEGO acceptor

```text
                      Kerberos LAB.EXAMPLE.TEST
                     +---------------------------+
                     | KDC / AS / TGS            |
                     | kdc.lab.example.test      |
                     | service keys, KVNO        |
                     +---------------------------+
                       ^              ^
             AS exchange|              |TGS for HTTP/portal...
                       |              |
                       v              |
  Linux/Windows client + browser      |
  student1@LAB.EXAMPLE.TEST            |
  kinit -> TGT in credential cache     |
             |                         |
             +-- requests service ticket
             |    HTTP/portal.lab.example.test
             |
             |  GET /reports
             +-------------------------------> Spring Web SP
             |                                  (behind TLS ingress)
             |<----------- HTTP 401             |
             | WWW-Authenticate: Negotiate      |
             |                                  |
             +----- Authorization: Negotiate -->|
                   <base64 SPNEGO token>         |
                                                v
                                        SpnegoAuthenticationProcessingFilter
                                                |
                                                v
                                        KerberosServiceAuthenticationProvider
                                                |
                                                v
                                         SunJaasKerberosTicketValidator
                                                |
                                /run/secrets/portal-http.keytab
                                contains service LONG-TERM KEY(S)
                                                |
                                    Java GSS acceptSecContext
                                                |
                                       authenticated client principal
                                                |
                                   UserDetailsService/local role policy
                                                |
                                       Spring SecurityContext
                                                |
                                           200 or 403
```

### 2.1. AS/TGS, TGT và service ticket

- **KDC (Key Distribution Center):** Kerberos server phát tickets, gồm Authentication Service (AS) và Ticket-Granting Service (TGS).
- **Realm:** vùng tin cậy, ở lab là `LAB.EXAMPLE.TEST`, thường viết hoa theo thông lệ.
- **User principal:** ví dụ `student1@LAB.EXAMPLE.TEST`.
- **TGT:** Ticket-Granting Ticket, client nhận sau `kinit` hoặc Windows domain logon; dùng xin service ticket.
- **Service principal / SPN:** ví dụ `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST`, mô tả dịch vụ HTTP mà browser thực sự truy cập. Phần `HTTP` là service class ngay cả khi URL dùng HTTPS.
- **Service ticket:** client lấy từ TGS dành riêng SPN; server có keytab tương ứng mới giải mã/xác thực phần liên quan.
- **KVNO:** key version number. Rotation có thể làm keytab cũ không khớp ticket mới.
- **Keytab:** container lưu *secret long-term keys của service*. Đây **không phải** token browser, public certificate hay “mật khẩu user” cần đưa vào frontend.
- **SPNEGO (Simple and Protected GSS-API Negotiation):** cơ chế negotiate GSS security mechanism, thường dùng Kerberos; nếu client/server hỗ trợ mechanism khác thì phải có chính sách chấp nhận rõ.
- **HTTP Negotiate:** scheme HTTP challenge/response chuyển GSS/SPNEGO token bằng headers.

### 2.2. 401 trong SPNEGO thường là bước bình thường

Một luồng đúng có thể bắt đầu bằng:

```http
GET /reports HTTP/1.1
Host: portal.lab.example.test

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
```

Client sau đó gửi request mới:

```http
GET /reports HTTP/1.1
Host: portal.lab.example.test
Authorization: Negotiate <base64-opaque-gss-token>
```

Khối trên **chỉ minh họa giao thức HTTP**; đừng copy chuỗi trong ngoặc làm token thật. Giá trị sau `Negotiate` là binary GSS token được base64, không phải JWT/JWS hay username/password. Đừng decode như JSON, chấp nhận hostname từ token mà không kiểm SPN, hoặc log toàn bộ header.

Trong trường hợp mutual authentication, server có thể trả `WWW-Authenticate: Negotiate <response-token>` ngay cả khi kết quả HTTP 200. Không giả định một round trip 401 duy nhất luôn đủ; GSS negotiation có thể cần nhiều bước tùy client/mechanism.

## 3. Topology phòng lab và tiền đề

Đặt các tên sau trong môi trường riêng:

| Thành phần | FQDN / principal ví dụ | Chức năng |
| --- | --- | --- |
| Kerberos realm | `LAB.EXAMPLE.TEST` | Phạm vi khóa và principal |
| KDC + admin | `kdc.lab.example.test` | MIT Kerberos KDC/kadmin |
| Application public DNS | `portal.lab.example.test` | Host browser gọi thật |
| Application URL | `https://portal.lab.example.test` | TLS frontend/canonical host |
| Service principal | `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` | SPNEGO acceptor |
| Test user | `student1@LAB.EXAMPLE.TEST` | Client principal, có TGT |
| Disabled user | `locked1@LAB.EXAMPLE.TEST` | Kiểm local deny logic |
| Java web app | Spring Boot 3 + JDK 17 hoặc stack tương thích | HTTP Negotiate + authorization |
| Keytab path | `/run/secrets/portal-http.keytab` | Secret chỉ app đọc |
| KDC config | `/etc/krb5.conf` / `/etc/krb5kdc/kdc.conf` | Realm và KDC discovery |
| Client ticket cache | Default ccache của OS/`kinit` | Không phải server keytab |

**Yêu cầu:** DNS hoặc `/etc/hosts` phải phân giải đúng (đối với lab), mạng thông tới KDC và SP, NTP/chrony đồng bộ, HTTPS certificate hợp lệ/trusted cho trình duyệt/curl. Trong triển khai thật ưu tiên DNS tập trung thay `/etc/hosts`. KDC TCP/UDP 88 (tùy cấu hình), admin 749 nếu dùng remote `kadmin`; không mở admin server tùy tiện ra internet.

### 3.1. Realm và DNS FQDN không giống nhau

`LAB.EXAMPLE.TEST` là realm; `portal.lab.example.test` là hostname. Một client dùng URL `https://alias.lab.example.test` có thể yêu cầu SPN `HTTP/alias.lab.example.test`, không phải `HTTP/portal.lab.example.test`. DNS CNAME, canonicalization và browser policies ảnh hưởng chọn SPN. **Khi muốn dùng alias, đăng ký SPN phù hợp và lập trust/rotation kế hoạch**, không tắt service principal validation.

IP literal `https://10.0.0.8` thường không phải SPN chuẩn của browser. Thử nghiệm bằng đúng hostname public; không sửa keytab thành `HTTP/localhost` chỉ để vượt qua lỗi lab.

### 3.2. Bốn luồng bí mật khác nhau

- Client user giữ TGT/ticket trong credential cache của người dùng; không đưa lên server.
- Browser chỉ gửi GSS service token trong header HTTP qua HTTPS.
- Java server đọc keytab long-term **service** key để accept token.
- KDC lưu secret/key DB của realm; không mount toàn bộ KDC database sang ứng dụng.

**Nguyên tắc tối thiểu quyền:** Web app keytab chỉ cần keys cho HTTP service principal liên quan, không phải KDC admin principal, `krbtgt`, host root principal hoặc tài khoản người dùng.

## 4. Chọn phiên bản Spring Security Kerberos đúng thế hệ

Spring Security Kerberos là chức năng/module cần dependency riêng, không tự bật chỉ vì đã có `spring-boot-starter-security`. **Cần kiểm tra release cụ thể đang deploy**:

| Stack | Artifact group (theo tài liệu) | Ghi chú |
| --- | --- | --- |
| Spring Boot 3 / Spring Security 6.5.x / Java 17 | `org.springframework.security.kerberos`, `spring-security-kerberos-core` và `spring-security-kerberos-web` phiên bản 2.2.x | Nhánh 2.2.0 được thử với Spring Security 6.5.1, Framework 6.2.8, Jakarta Servlet |
| Spring Security 7 / Framework 7 / Java 17+ | `org.springframework.security` cho `spring-security-kerberos-core` và `spring-security-kerberos-web` | **GroupId đổi** theo tài liệu phiên bản 7, version theo Spring Security BOM |
| Spring Boot 2 / Security 5 / javax.servlet | Thế hệ Kerberos legacy tương thích Spring 5 | **Không** trộn trực tiếp javax filters với Jakarta Servlet container |

Nguồn docs Spring Security Kerberos 7 nêu artifact coordinates đổi sang `org.springframework.security`; tài liệu 2.2.0 dùng `org.springframework.security.kerberos`. Dùng đúng version/BOM và runtime, không kéo lẫn cả hai group artifact cùng một ứng dụng.

### 4.1. Maven Spring Boot 3 lab

```xml
<!-- pom.xml dependency fragments; Boot parent/BOM supplies web/security -->
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
```

Đây là fragment, chưa phải một `pom.xml` hoàn chỉnh (cần parent, repositories, build plugins, app sources, Java target và lock dependency tree). Với Boot 3/Security 6 phải test binary compatibility của chính patch version. **Không** tự thay Spring Security dependencies do Boot BOM quản lý bằng bản của Spring 7 chỉ vì tên modules trông giống.

### 4.2. Maven Spring Security 7

```xml
<!-- Schematic current-generation coordinates. Align with Boot/Security BOM. -->
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
```

Không copy số version 2.2.0 sang group mới, và không đoán Boot 4/Framework 7 sẽ chạy mọi filter customization của Boot 3. Chạy compile, integration test và dependency convergence.

### 4.3. Vì sao không dùng KerberosRestTemplate làm server acceptor?

`KerberosRestTemplate` có thể làm **client outbound** tới dịch vụ protected bằng Kerberos, đôi khi dùng client keytab để xin credentials. **Bài này làm server nhận browser SPNEGO**, cần `SpnegoAuthenticationProcessingFilter` → `KerberosServiceAuthenticationProvider` → `SunJaasKerberosTicketValidator`. Client initiating credentials, service acceptor credentials và LDAP GSSAPI bind là những flow khác, không hoán đổi `isInitiator` một cách tùy tiện.

## 5. Dựng MIT Kerberos KDC trong môi trường lab

Trên một VM Linux test do bạn quản trị, cài các gói Kerberos server/admin và client tương ứng bản phân phối (ví dụ Debian/Ubuntu):

```bash
sudo apt-get update
sudo apt-get install krb5-kdc krb5-admin-server krb5-user
```

**Không chạy quy trình quản trị realm này trên domain/KDC doanh nghiệp khi chưa được phép.** Lab dùng network cô lập. Tài liệu distro có wizard cấu hình khác nhau; các câu lệnh bên dưới giả định một KDC MIT Kerberos đã khởi tạo với `LAB.EXAMPLE.TEST` và đúng ACL/admin principal. Cần hiểu chính xác phân phối Linux trước khi tự chạy `kdb5_util create -s` — lệnh tạo database/realm mới, **không dùng trên KDC đang phục vụ dữ liệu thật**.

### 5.1. Ví dụ /etc/krb5.conf dùng bởi lab

```ini
[libdefaults]
    default_realm = LAB.EXAMPLE.TEST
    dns_lookup_realm = false
    dns_lookup_kdc = false
    rdns = false
    udp_preference_limit = 1

[realms]
    LAB.EXAMPLE.TEST = {
        kdc = kdc.lab.example.test
        admin_server = kdc.lab.example.test
    }

[domain_realm]
    .lab.example.test = LAB.EXAMPLE.TEST
    lab.example.test = LAB.EXAMPLE.TEST
```

Đây là fragment **MIT krb5.conf**. Java JGSS thường dùng hệ thống Kerberos configuration; có thể chỉ định `-Djava.security.krb5.conf=/etc/krb5.conf`. Không hardcode realm của người dùng thực. Với Windows AD domain controller, KDC discovery qua DNS SRV/realm mapping có thể khác; DNS/UPN, trust và encryption policies phải được làm rõ.

### 5.2. KDC realm database — chỉ khi lab hoàn toàn mới

Theo hướng dẫn MIT, có thể tạo KDC DB bằng công cụ quản trị phù hợp:

```bash
# On a NEW isolated MIT KDC only.
sudo kdb5_util create -s -r LAB.EXAMPLE.TEST
```

Lệnh này có thể hỏi master database password; không đưa password vào command line/log/chat. Cần tạo admin principal và ACL theo tài liệu distro; ở lab có thể dùng `kadmin.local` khi có quyền root trên KDC. KDC daemon cần được khởi động theo systemd/service của distro và xác minh listening/network.

**Điều kiện dừng:** nếu KDC đã tồn tại, không chạy lại create. Nếu user test không thể `kinit` do KDC inaccessible, đừng debug Spring Security trước; sửa realm/NTP/network ở cấp Kerberos.

### 5.3. Principal test và service principal

Trên KDC lab, tạo user có mật khẩu **chỉ qua interactive prompt**:

```bash
sudo kadmin.local -q "addprinc student1@LAB.EXAMPLE.TEST"
```

Tạo HTTP service principal với random key, **không cần biết password**:

```bash
sudo kadmin.local -q \
  "addprinc -randkey HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

KDC database của lab sẽ có hai principals khác vai trò. Việc dùng `HTTP/` dù app gọi HTTPS là **đúng service class** của Kerberos HTTP SPNEGO.

### 5.4. Trích keytab dịch vụ

```bash
# Run on KDC lab administrator host.
sudo install -d -m 0700 /var/lib/kerberos-lab/export
sudo kadmin.local -q \
  "ktadd -k /var/lib/kerberos-lab/export/portal-http.keytab HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

**Cực kỳ quan trọng:** theo MIT Kerberos, `ktadd` mặc định **randomize service keys khi export**, làm tăng KVNO. Nếu lặp `ktadd` tùy tiện, keytab đã phát trước đó trên app A/B có thể không còn khớp tickets/key ở KDC.

Để xuất **bản keytab bổ sung cho cùng SPN mà không làm đổi key trên KDC**, MIT hỗ trợ:

```bash
sudo kadmin.local -q \
  "ktadd -norandkey -k /var/lib/kerberos-lab/export/portal-node-b.keytab HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

`-norandkey` cần quyền/khả năng export keys thích hợp và chính sách KDC cho phép; không dùng nếu key access đã bị khóa/hạn chế. **Không hiểu lầm** nó là biện pháp rotation; routine rotation đòi đổi key theo kế hoạch, duy trì phiên bản cũ/mới trong giai đoạn chuyển và cập nhật KDC/keytabs đồng bộ. Có môi trường enterprise/AD không dùng MIT `kadmin`; phải áp quy trình SPN/keytab của domain controller tương ứng.

### 5.5. Kiểm tra keytab, KVNO và enctype

Trên KDC export host:

```bash
sudo klist -kte \
  /var/lib/kerberos-lab/export/portal-http.keytab
sudo kadmin.local -q \
  "getprinc HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
```

`klist -kte` hiển thị principal, KVNO và enctype của keytab; **không** hiển thị secret key theo mặc định. Test principal phải chính xác từng thành phần host/realm. Các algorithms như AES256/AES128 phù hợp khi KDC/JVM hỗ trợ; không hạ xuống DES/RC4 cũ để “qua test” nếu chính sách cấm.

**Không có stdout cố định** cho các lệnh KDC: KVNO, enctype và key generation khác theo realm/config/version. Không copy một ví dụ KVNO=2 rồi coi đó là điều kiện bắt buộc.

## 6. Phân phối và bảo vệ keytab của server

Keytab tương đương **secret dài hạn của service principal**, khác private key TLS nhưng cùng cần bảo vệ nghiêm.

### 6.1. Di chuyển tới application node

Keytab được tạo trên KDC chỉ nên truyền qua kênh được quản trị/chứng thực, ví dụ secret management pipeline hoặc secure admin transfer. Trên server:

```bash
# Illustrative service-host path preparation.
sudo install -d -m 0700 /run/secrets
sudo install -o portalapp -g portalapp -m 0400 \
  /secure-admin-transfer/portal-http.keytab \
  /run/secrets/portal-http.keytab
sudo -u portalapp test -r /run/secrets/portal-http.keytab
```

Lệnh giả định service OS account `portalapp` đã tồn tại và file đã được chuyển qua kênh an toàn. Không dùng quyền root trong Java app, không `chmod 777`, không đặt keytab trong `src/main/resources`/JAR/Git/Docker image. Trong Kubernetes mount secret read-only, giới hạn namespace/RBAC, access logs và backup policy; xem xét CSI secret provider với rotation đúng vòng đời.

### 6.2. Keytab của các pods cùng public hostname

Nếu browser luôn truy cập `https://portal.lab.example.test`, client thường xin ticket `HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST`, **không xin** `HTTP/pod-a.internal`. Do đó các pods nhận cùng public host có thể dùng **cùng service keytab** hoặc mô hình key-service tương đương. Nếu pod A dùng KVNO 3 còn pod B dùng KVNO 2, login sẽ hỏng ngẫu nhiên theo load balancer. Secret rollout phải đồng nhất.

### 6.3. Kiểm không làm lộ secret

- Không in `keytab` bytes vào logs, metrics, support tickets hoặc stack traces.
- Không tải keytab xuống browser/trình duyệt; không đưa vào HTTP response.
- Không commit sample keytab “cho dễ chạy lab”; tạo riêng trong lab.
- Không nén keytab vào Docker image, helm values plain text hoặc ConfigMap.
- Hạn chế process quyền đọc, file permissions và volume mounts.
- Nếu bị lộ, coi như compromise **service principal** và rotate key/KVNO theo runbook.
- Không cho phép client cung cấp `keyTabLocation`/`servicePrincipal` qua query params.

### 6.4. Expose file name khác expose bytes

Log một config key như `app.kerberos.keytab=/run/secrets/portal-http.keytab` có thể chấp nhận tùy policy, nhưng không log secret contents hoặc dump toàn bộ environment/property sources vì có thể chứa credentials khác. Dùng allowlisted health readiness thay `ls -l` spam debug.

## 7. Kiểm tra Kerberos client trước khi chạy web app

Trên Linux client cùng realm/đường mạng, dùng principal test:

```bash
# Interactive password: no password on CLI.
kinit student1@LAB.EXAMPLE.TEST
klist

# Force/request ticket for HTTP service.
kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST
klist
```

Nếu `kvno` thất bại `Server not found in Kerberos database`, kiểm tên SPN, DNS alias/FQDN, realm và service principal thực trong KDC. Nếu `kinit` thất bại vì `Clock skew too great`, đồng bộ NTP. Nếu client không thể nhận TGT thì browser/curl SPNEGO cũng không có nền tảng để xác thực.

### 7.1. Có nên dùng keytab dịch vụ để kinit trên server?

Server `HTTP/portal...` là **acceptor**, không cần fetch TGT như user để nhận HTTP Negotiate. Lệnh `kinit -kt /run/secrets/portal-http.keytab HTTP/...` đôi khi được dùng trong lab để thử keytab có phù hợp với KDC, nhưng nó dùng service keytab theo vai trò **initiator**, tạo ticket cache và có thể bị policy chặn; **không** đặt nó thành bước bắt buộc hoặc daemon keepalive của SPNEGO server. Với acceptor, bắt đầu bằng `klist -kte`, JAAS config và real Negotiate flow.

### 7.2. Client và server có khác clock/time zone

Kerberos tickets có start/end times, KDC và client/server có clock-skew tolerance (thường cỡ phút, tùy realm). Giờ local hiển thị +07:00 không sai nếu UTC timestamps tương đương; vấn đề là **system clock thực sự lệch**, không phải timezone format. Dùng NTP/chrony trên KDC, clients và app nodes. Đừng tăng skew lên nhiều giờ để chữa hệ thống sai giờ.

## 8. JAAS/JGSS acceptor: service principal và keytab

Java 17 có `com.sun.security.auth.module.Krb5LoginModule` trong module `jdk.security.auth`, cung cấp các tùy chọn JAAS. Ví dụ file `/etc/portal/jaas-krb5.conf`:

```text
PortalAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/portal-http.keytab"
    principal="HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    debug=false;
};
```

Đây là entry cho **acceptor only**. Các flags có nghĩa:

| Option | Giá trị minh họa | Tại sao |
| --- | --- | --- |
| `useKeyTab=true` | Bật | Lấy long-term key từ keytab |
| `keyTab=...` | Path tuyệt đối | Không dựa working directory |
| `principal=HTTP/...@REALM` | Service identity cụ thể | Không accept mọi principal trong keytab |
| `storeKey=true` | Bật | Cung cấp secret keys trong JAAS Subject private credentials cho GSS accept |
| `doNotPrompt=true` | Bật | Không chờ password stdin trong server |
| `isInitiator=false` | Bật | Server là GSS acceptor, không cần TGT như user |
| `debug=false` | Mặc định an toàn | Tránh log/timing/secret-sensitive debug ngoài lab |

Oracle JDK docs cũng cho phép `principal="*"` khi `isInitiator=false` để accept bằng bất kỳ principal nào trong keytab. **Không dùng wildcard trừ khi có use case đa-SPN được review**; bài lab giữ principal cố định để chống nhầm keys/hostname.

### 8.1. JVM properties

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -Djava.security.auth.login.config=/etc/portal/jaas-krb5.conf \
  -jar portal.jar
```

Command trên là **launcher minh họa**; chỉ chạy khi build đã tạo `portal.jar` và configs thực tồn tại. Một số thư viện Spring Security Kerberos có thể dựng JAAS programmatically trong `SunJaasKerberosTicketValidator`, không dùng entry `PortalAcceptor` trực tiếp; tránh hiểu nhầm rằng đặt `-Djava.security.auth.login.config` là đủ để tự bật Spring SPNEGO filter. Với validator đang dùng, đối chiếu source/Javadoc về cách nó login và load keytab.

### 8.2. JDK 17, modules và GSS-API

Java JGSS thường dùng `org.ietf.jgss.GSSManager`, `GSSContext` và `GSSCredential`. Nếu chạy custom minimized JRE image tạo bằng `jlink`, phải có modules liên quan như `java.security.jgss` và `jdk.security.auth` khi code cần JAAS module. Nếu gặp `NoSuchAlgorithmException`/`ClassNotFound` do custom JRE, kiểm module graph trước khi thay Kerberos realm.

**Đừng** tự triển khai cipher/decryption Kerberos từ keytab. JAAS/GSS xử lý cryptographic accept; Spring Kerberos provider chuyển principal verified sang Spring Authentication.

### 8.3. Một JGSS fragment để hiểu acceptor

```java
// Fragment minh họa Java GSS-API; không phải server hoàn chỉnh.
// receivedToken: byte[] decoded from trusted HTTP Negotiate path.
// LoginContext/Subject được tạo theo JAAS acceptor config.
LoginContext login =
    new LoginContext("PortalAcceptor");
login.login();
Subject subject = login.getSubject();

String clientPrincipal = Subject.doAs(
    subject, (PrivilegedExceptionAction<String>) () -> {
        GSSManager manager = GSSManager.getInstance();
        GSSCredential credential = manager.createCredential(
            null, GSSCredential.INDEFINITE_LIFETIME,
            (Oid) null, GSSCredential.ACCEPT_ONLY);
        GSSContext context = manager.createContext(credential);
        try {
            byte[] serverToken =
                context.acceptSecContext(
                    receivedToken, 0, receivedToken.length);
            // If serverToken is non-null, protocol exchange
            // may require returning it to browser.
            if (!context.isEstablished()) {
                throw new SecurityException(
                    "GSS negotiation not complete");
            }
            return context.getSrcName().toString();
        } finally {
            context.dispose();
        }
    });
```

Mã trên là **fragment có imports/variables chưa khai báo** và rút gọn protocol context lifetime. Nó **không** encode SPNEGO token, không gửi response token, không xử lý multi-round challenge/response, không bind HTTP state, không quản lý replay/context toàn bộ. Trong app thực hãy dùng Spring Security Kerberos filter đã được duy trì thay vì tự viết từ đầu.

## 9. Spring Security: cấu hình SPNEGO trên server

### 9.1. Các lớp quan trọng

- `SpnegoEntryPoint`: tạo challenge `401 WWW-Authenticate: Negotiate`; có thể cấu hình form-login fallback theo risk policy.
- `SpnegoAuthenticationProcessingFilter`: đọc header Negotiate và tạo `KerberosServiceRequestToken`.
- `KerberosServiceAuthenticationProvider`: xử lý token qua `KerberosTicketValidator`, sau đó tra local `UserDetailsService`/authorities.
- `SunJaasKerberosTicketValidator`: dùng JAAS/GSS verify service ticket với **service principal và keytab**.
- `UserDetailsService`: mapping identity đã được xác thực thành account/authorities nội bộ; không tin role đến từ raw HTTP header.
- `SecurityFilterChain`: authorization trên route, session/CSRF, exception handling.
- `BasicAuthenticationFilter`: vị trí anchor mà tài liệu Spring đặt Spnego filter phía trước.

**Quan trọng:** `KerberosServiceAuthenticationProvider` trả user principal và local authorities từ `UserDetailsService`; Kerberos **không tự cấp** `ROLE_ADMIN`, xác thực tên principal không chứng minh quyền của tài khoản nội bộ.

### 9.2. application.yml fragment

```yaml
server:
  port: 8080

app:
  kerberos:
    service-principal: "HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST"
    keytab: "/run/secrets/portal-http.keytab"

logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.kerberos: INFO
```

Ứng dụng có thể chạy HTTP nội bộ cổng 8080 sau ingress, nhưng **browser dùng HTTPS public** và GSS service principal vẫn theo public FQDN, không phải `HTTP/pod:8080`. Không đưa keytab bytes vào YAML, environment dump hoặc secrets-as-config commits.

### 9.3. Cấu hình Spring Boot 3/Security 6 minh họa

```java
package example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication
        .KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun
        .SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication
        .SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication
        .SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www
        .BasicAuthenticationFilter;

@Configuration
public class KerberosSecurityConfiguration {

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            Environment env,
            UserDetailsService localUserDetailsService) {

        String servicePrincipal = env.getRequiredProperty(
            "app.kerberos.service-principal");
        String keytab = env.getRequiredProperty(
            "app.kerberos.keytab");

        SunJaasKerberosTicketValidator ticketValidator =
            new SunJaasKerberosTicketValidator();
        ticketValidator.setServicePrincipal(servicePrincipal);
        ticketValidator.setKeyTabLocation(
            new FileSystemResource(keytab));
        ticketValidator.setDebug(false);

        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(ticketValidator);
        provider.setUserDetailsService(localUserDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        ProviderManager manager = new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/healthz").permitAll()
                .requestMatchers("/reports/admin/**")
                    .hasRole("REPORT_ADMIN")
                .requestMatchers("/reports/**")
                    .hasRole("REPORT_VIEWER")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .addFilterBefore(filter, BasicAuthenticationFilter.class)
            .build();
    }
}
```

**Đây là Spring configuration fragment, chưa phải project tự chạy.** Cần Boot main class, dependency versions đúng, HTTP controller, `UserDetailsService` thực, test KDC/DNS/HTTPS, validation of local account status and authority mapping. `new SpnegoEntryPoint()` phát challenge Negotiate; có thể chọn fallback page qua constructor nhưng phải thử tránh login loops.

**Caveat quan trọng:** filter được khởi tạo **bên trong SecurityFilterChain**, không khai báo thêm như Servlet `@Bean Filter`/`FilterRegistrationBean`. Nếu tạo Filter bean và Boot auto-register ngoài `springSecurityFilterChain`, dễ xử lý Negotiate **hai lần**. Trong version đã kiểm, `SpnegoAuthenticationProcessingFilter` có `setSecurityContextRepository` và `setSessionAuthenticationStrategy`, xem phần tiếp theo nếu muốn persistent session.

### 9.4. SecurityContext persistence là quyết định riêng

Mã nguồn Spring Security Kerberos filter có default repository dựa trên request; nó **không mặc nhiên lưu authenticated SecurityContext lâu dài vào HttpSession**. Với SPNEGO stateless-per-request, có thể yêu cầu browser Negotiate trên mỗi request khi cần. Nếu muốn tạo session cookie cho frontend, phải chủ động tích hợp:

```java
import org.springframework.security.web.context
    .HttpSessionSecurityContextRepository;
import org.springframework.security.web.authentication.session
    .ChangeSessionIdAuthenticationStrategy;

// Fragment mở rộng trên filter đã được tạo.
HttpSessionSecurityContextRepository contextRepository =
    new HttpSessionSecurityContextRepository();
filter.setSecurityContextRepository(contextRepository);
filter.setSessionAuthenticationStrategy(
    new ChangeSessionIdAuthenticationStrategy());
```

**Không đơn giản copy hai dòng rồi coi là hoàn thành:** Cần đồng bộ `SecurityContextRepository` của Spring Security chain, session policy, invalidation, logout, CSRF và cluster store. Không khuyến nghị lưu GSS negotiation context/opaque token vào session; chỉ lưu Authentication tối thiểu đã được validate. Nếu app dùng Spring Session Redis, phải test serialization, session fixation ID rotation và logout/lock revocation.

Nếu một app dùng stateless API, có thể không muốn browser HttpSession. Chọn rõ stateless vs stateful và test behavior khi browser gửi cookie cũ, khi user bị revoke và khi request không còn `Authorization` header.

### 9.5. Không tự coi việc gọi UserDetailsService là bước đủ

Một local account trả `UserDetails` với `enabled=false` hoặc `accountNonLocked=false` cần được enforce theo policy, nhưng đừng giả định mọi custom provider đều áp giống `DaoAuthenticationProvider` xử lý password. Đặt account-status gate tường minh và test thật với provider đã chọn. For sensitive routes, authorities có thể được cache trong session; test role revocation/lock **sau** khi login.

### 9.6. Spring Security 7 khác groupId nhưng cùng khái niệm

Với Spring Security 7, groupId Kerberos modules đổi sang `org.springframework.security`. APIs như `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` vẫn xuất hiện trong tài liệu hiện hành, nhưng phải **đối chiếu constructors, builder DSL và BOM**. Không trộn 2.2.0 modules của org.springframework.security.kerberos với modules 7.x mới trong cùng classpath. Spring Security 6/7 có thay đổi cách persistence SecurityContext; test session thật thay vì suy từ ví dụ lịch sử.

## 10. Local UserDetailsService và quyền nội bộ

Một verified Kerberos user principal có thể là `student1@LAB.EXAMPLE.TEST`. Không dùng nó làm quyền admin mặc định, cũng không so raw substring/contains `"admin"`. Nên có mapping canonical identity→local account:

```text
Kerberos principal (verified by GSS):
  student1@LAB.EXAMPLE.TEST
      |
      v
Local identity mapping:
  protocol: kerberos
  realm: LAB.EXAMPLE.TEST
  name: student1
  localId: student-portal-001
      |
      v
Local account status = ACTIVE
Local grants = {REPORT_VIEWER}
      |
      v
GrantedAuthorities = {ROLE_REPORT_VIEWER}
```

Với multiple realms/forest trusts, chính sách canonicalization rất quan trọng. `student1@REALM-A` không tự bằng `student1@REALM-B`, và Windows UPN không luôn trùng sAMAccountName. Đừng tự strip realm trước DB lookup nếu có multi-realm; attacker từ realm khác có thể trùng phần username.

### 10.1. Minh họa local mapping

```java
// Fragment của UserDetailsService sau GSS authentication.
// localIdentityRepository và localGrantService do ứng dụng định nghĩa.
@Override
public UserDetails loadUserByUsername(String krbPrincipal) {
    LocalUser local = localIdentityRepository
        .findByKerberosPrincipal(krbPrincipal)
        .orElseThrow(() -> new UsernameNotFoundException(
            "Principal not provisioned"));

    if (!local.isEnabled() || local.isLocked()) {
        throw new DisabledException("Local access denied");
    }

    List<GrantedAuthority> authorities =
        localGrantService.grantsFor(local.getId()).stream()
            .map(SimpleGrantedAuthority::new)
            .toList();

    return User.withUsername(local.getId())
        .password("{noop}not-used-by-kerberos")
        .authorities(authorities)
        .accountLocked(false)
        .disabled(false)
        .build();
}
```

**Fragment, không phải code độc lập;** thiếu imports/interfaces/repositories và business policy. Password placeholder ở đây **không tham gia Kerberos**, nhưng nếu đối tượng `UserDetails` được tái dùng cho form login, chuỗi “not-used” có thể tạo đường password auth sai. Production nên tách local password authentication khỏi Kerberos UserDetails hoặc dùng credentials bị khóa, không tạo mật khẩu dự đoán được. Tùy provider, mapping có thể trả principal/authorities dạng custom `UserDetails` mà không hỗ trợ password login.

### 10.2. Test local status/role

- `student1@LAB.EXAMPLE.TEST` ACTIVE và `ROLE_REPORT_VIEWER`: request `/reports/overview` cho phép.
- `student2@LAB.EXAMPLE.TEST` ACTIVE nhưng không có role: GSS success, app trả 403 cho protected report.
- `locked1@LAB.EXAMPLE.TEST` có role nhưng local locked: reject auth hoặc deny mọi protected action.
- Principal từ `OTHER.REALM` với username giống student1: không map nhầm local account.
- User bị revoke sau khi đã có session: old cookie phải không còn đọc data theo revocation policy.
- Debug endpoint `/whoami` chỉ trả dữ liệu tối thiểu, không in service ticket hoặc keytab.

### 10.3. LDAP/AD lookup sau Kerberos

Một số deployment dùng AD LDAP/LDAPS để đọc groups/authorities. Đó là kết nối **riêng** với trust/bind credentials/LDAP filter/scope, không phải tự động có vì Kerberos đã verify user. Nếu dùng `KerberosLdapContextSource` hoặc GSSAPI LDAP bind, xác định role client initiator riêng và cấu hình trust; không dùng acceptor keytab của HTTP service với quyền LDAP admin trái principle of least privilege. LDAP groups cần map tenant/local policy; không cấp ROLE_ADMIN chỉ vì một nhóm mang chữ “admin”.

## 11. Browser và curl: kiểm thử đúng SPN

### 11.1. curl Negotiate trên Linux client có TGT

Trên máy lab client đã `kinit student1@LAB.EXAMPLE.TEST`:

```bash
curl --version
curl -i --negotiate -u : \
  https://portal.lab.example.test/reports/overview
```

`curl` phải được build với GSSAPI/Negotiate support. `-u :` là cú pháp thường dùng để kích hoạt curl's negotiate auth; **không phải** truyền password của student1 vào HTTP Basic. Với HTTPS, kiểm CA/hostname thật — không thêm `-k` trong runbook; nếu lab CA tự ký, cài CA trust đúng scope.

Kết quả kỳ vọng có thể bao gồm HTTP 401 challenge rồi HTTP 200 hoặc 403 theo local role. Không có stdout cố định vì version curl/HTTP/WWW-Authenticate headers và credential cache khác nhau. Kiểm browser/curl log ở chế độ debug **có redact**: đừng lưu giá trị header `Authorization: Negotiate` trong build logs.

### 11.2. curl không có TGT

```bash
kdestroy
curl -i --negotiate -u : \
  https://portal.lab.example.test/reports/overview
```

Kỳ vọng **không thể authenticate bằng Kerberos** khi không có credential cache hoặc OS SSO source; user có thể nhận 401/fallback nếu cấu hình. Một số host có credential cache khác (Windows SSPI hoặc service account) nên kết quả cụ thể phụ thuộc OS. Không dùng `kdestroy` trên máy dùng credential chính thức ngoài lab; chỉ cho principal test.

### 11.3. Browser điều kiện bắt buộc

- Máy client thuộc/trust realm hoặc user đã có Kerberos credentials.
- Browser được cấu hình **allowlisted SPNEGO/integrated auth site** theo enterprise policy.
- URL dùng FQDN đúng SPN; tránh IP literal.
- DNS/KDC discovery, NTP và CA TLS đều đúng.
- Browser hỗ trợ HTTP Negotiate; nếu browser không tự gửi token, có thể do site không thuộc trusted intranet allowlist.
- Không ép mọi browser gửi NTLM như fallback Kerberos; nếu NTLM không nằm trong threat model, tắt/giới hạn ở hệ thống phù hợp.
- Login mới và reauthentication khi local session hết phải được test, không chỉ lần đăng nhập đang có cookie.

### 11.4. Edge và proxy: ai nhận Negotiate?

Có hai kiến trúc khác nhau:

1. **Backend Java làm acceptor:** ingress **forward** `Authorization: Negotiate` (và response `WWW-Authenticate`) tới Spring Security Kerberos; backend đọc keytab.
2. **Ingress làm acceptor:** proxy/gateway tự verify Kerberos rồi forward identity đã xác thực đến backend qua channel tin cậy. Backend **không** được tự tin `X-Remote-User` do browser gửi; proxy phải strip spoofed headers và bind identity.

Không cài keytab ở cả ingress/backend và tự cho cả hai cùng “authenticate một lần nữa” nếu không có chủ đích; double consumption/context mismatch có thể xảy ra. Cấu hình HTTP auth at ingress ảnh hưởng Spring failure response; test real network path.

## 12. HTTP 401/403, redirect loops và fallback

Một SPNEGO flow không nên dùng `302` vô hạn tới một login form chỉ vì chưa có negotiate header. `SpnegoEntryPoint` dùng `401` challenge. Nếu hỗ trợ password/LDAP fallback:
- Form login phải qua HTTPS, CSRF, rate-limit, MFA theo risk.
- SPNEGO path và form login path rõ ràng, không mở web app `permitAll` khi negotiation thất bại.
- Browser có thể không hỗ trợ Negotiate; fallback chỉ cho accounts/methods được phép.
- Không dùng Basic auth prompt như fallback bí mật khi không chủ định.
- Khi user đã authenticated nhưng thiếu role, trả `403 Forbidden` (theo app handler), không làm vòng negotiate bất tận.
- Với API callers, làm rõ challenge vs redirect behavior; không bắt SPA `fetch` tự điều hướng đến KDC.

### 12.1. Khác biệt authentication vs authorization

| Tình huống | Authentication | Authorization | Outcome |
| --- | --- | --- | --- |
| Không có Negotiate, chưa có session | Chưa có | Chưa xét | `401 WWW-Authenticate: Negotiate` |
| Token invalid/malformed | Không thành công | Chưa xét | Reject/challenge, sanitized |
| Ticket valid, principal active, role đúng | Thành công | Thành công | 200 theo endpoint |
| Ticket valid, principal active, thiếu role | Thành công | Thất bại | Thường 403 |
| Ticket valid, account local LOCKED | Không cho app sử dụng | Thất bại | Deny, không tạo authenticated app session |
| Session cũ sau admin khóa account | Previously auth | Revoked | Không cho đọc protected data |

**Đừng** coi HTTP 401 đầu tiên là “SPNEGO failed”. Nó có thể là challenge cần thiết. Để test full SSO, kiểm final request/response sau negotiation và authenticated identity.

## 13. Kerberos key version, encryption types và rotation

### 13.1. Quan hệ KVNO và keytab

Mỗi service principal có key version(s) do KDC quản lý. `ktadd` thường lấy và export các keys của phiên bản đang active, nhưng **mặc định còn randomizes keys**, tăng KVNO. Một keytab có KVNO 2 trong khi service ticket mới được phát với KVNO 3 sẽ không thể accept, thường báo lỗi kiểu:

```text
GSSException: Failure unspecified at GSS-API level
  Mechanism level: Cannot find key of appropriate type
  or integrity check on decrypted field failed
```

Thông báo thực tế khác theo JDK/KDC/enctype; không dựa vào một string duy nhất. Kiểm `klist -kte` của file và `getprinc`/`kvno` từ KDC/test client. Không đưa raw ticket/secret vào lỗi.

### 13.2. Rotation trong cluster an toàn

```text
Phase 0  old KVNO = 3 in app A/B and KDC
Phase 1  approved rotation plan, snapshot current keytab
Phase 2  generate new key/KVNO through KDC admin process
Phase 3  distribute updated keytab to ALL SP nodes
         with controlled overlap/maintenance window
Phase 4  observe new tickets accepted, old ticket lifetime
Phase 5  retire old keys only after risk window and verification
```

Không tự chắc KDC sẽ giữ nhiều active KVNO sau `ktadd`; tùy chính sách/history, keytab có thể chứa nhiều entries nhưng KDC chỉ phát ticket mới theo current key. Để tránh outage, thực hiện keytab rollout/key version overlap theo chính sách supported của MIT/AD realm; nếu không có overlap, dùng controlled short maintenance window. **Không** copy keytab cũ giữ nguyên rồi khẳng định nó sẽ accept mọi ticket mới.

### 13.3. Encryption types

Kerberos SPNEGO có thể hỗ trợ AES128/AES256 và enctypes khác tùy KDC, AD, JDK. Nếu KDC phát encryption type mà Java runtime/service keytab không có key tương ứng, GSS accept fail. Kiểm:
- `klist -kte` liệt kê loại key.
- KDC service principal permitted enctypes.
- JDK 17 provider/enctype support.
- AD account flags/keytab generation tool nếu dùng Active Directory.
- Policies cấm RC4/DES, không bật trở lại algorithms yếu để “sửa nhanh”.

### 13.4. Active Directory SPN có điểm khác

Với Microsoft AD, dùng SPN/service account và tools như `setspn`/`ktpass` theo hướng dẫn domain admin. Tránh SPN trùng trên nhiều accounts; không tự chạy `setspn -A` không kiểm uniqueness. `ktpass` có thể reset service account password/key, dẫn tới KVNO/etype mismatch với các hosts đã deploy. Test bằng `setspn -Q HTTP/portal.lab.example.test` trong AD lab có quyền và so service account/keytab identity.

**Lab này dùng MIT KDC**; không áp nguyên xi `kadmin.local` lên Domain Controller Windows.

## 14. JAAS debug, GSS debug và logging an toàn

### 14.1. Debug có phạm vi

Trong phòng lab cô lập có thể bật tạm:

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -Dsun.security.krb5.debug=true \
  -Dsun.security.jgss.debug=true \
  -jar portal.jar
```

**Không để debug flags mặc định production**, vì logs có thể chứa principal names, realm mappings và thông tin nhạy cảm/cấu hình. Không lưu raw Negotiate token, TGT, keytab bytes hoặc user attributes. Sau xác minh, tắt và dùng safe reason codes.

### 14.2. Phân loại lỗi theo tầng

| Giai đoạn | Ví dụ vấn đề | Công cụ |
| --- | --- | --- |
| DNS/hostname | Browser đi `portal` alias nhưng SPN dùng hostname khác | `getent hosts`, DNS, browser URL |
| KDC client auth | Không xin được TGT | `kinit`, `klist` |
| TGS lookup | Service principal không tồn tại | `kvno HTTP/portal...`, KDC admin |
| KDC/service key | KVNO/enctype mismatch, stale keytab | `klist -kte`, KDC `getprinc` |
| HTTP negotiation | Proxy bỏ headers, browser không allow Negotiate | HTTP 401/WWW-Authenticate headers |
| GSS accept | Bad keytab/JAAS/clock/mechanism | Sanitized GSS error, JDK/KDC configs |
| Spring authentication | Provider chưa wired, bean double-register | Security filter logs/tests |
| Local authorization | Role thiếu, account locked | Local authz service/test fixtures |
| Session | SecurityContext không persist hoặc stale | Filter repository/session config |
| TLS | Client chặn cert HTTPS | Browser/curl truststore, TLS diagnosis |

### 14.3. Không khắc phục bằng bypass

Không được:
- Disable TLS validation để “curl chạy được”.
- Accept arbitrary `Authorization` bytes mà không gọi GSS validator.
- Cho client gửi `X-User` và map thành principal.
- Mount KDC master keys/service administrator keytab lên web pod.
- Bật DES/RC4 và wildcard service principal không kiểm duyệt.
- Bỏ local account locked/tenant/role checks.
- Chấp nhận `Negotiate` value rỗng như authenticated.
- Chuyển mọi `401/403` thành `200` trong ingress.
- Log raw SPNEGO header trong reverse proxy/APM để debug lâu dài.

## 15. Multi-node/SPNEGO qua ingress và session consistency

### 15.1. SPN gắn với public hostname, không gắn mỗi pod

Browser muốn ticket `HTTP/portal.lab.example.test`. Node A và B phía sau LB đều phải có key đủ để accept tickets cho SPN đó. Có thể mount cùng keytab secret được quản trị/rotate thống nhất; tránh version skew.

```text
Browser -> https://portal.lab.example.test
         -> TLS ingress / LB
              -> portal-pod-a with keytab KVNO 3
              -> portal-pod-b with keytab KVNO 3

Both accept tickets for HTTP/portal.lab.example.test
```

Nếu một pod nhận `GSSException` còn pod khác không, kiểm keytab file content/version, permissions và env configuration trên từng pod; không đưa raw secrets vào diagnostic. Ingress phải forward Negotiate header không bị đổi/strip và giữ canonical hostname.

### 15.2. Sticky session không giải bài toán keytab

Sticky sessions chỉ điều phối browser cookie tới pod cũ. Khi pod bị restart, một request mới có thể đi pod khác: node ấy vẫn phải có keytab đúng. Nếu app dùng HttpSession to persist Spring SecurityContext, cần Spring Session Redis/DB hoặc chuẩn bị reauthentication khi failover. **Không** coi sticky as Kerberos trust model.

### 15.3. Ticket replay và session reuse

Kerberos/GSS triển khai replay protection theo cơ chế/protocol, nhưng app có thể cần thêm policy session fixation prevention, request replay/CSRF. Không tự dùng `TGT` hay AP token để gán user mãi mãi sau khi local account bị khóa. Session duration và revoked-role consistency cần được kiểm thử độc lập.

### 15.4. TLS termination và channel binding

Một số Kerberos/SSPI deployments áp **Extended Protection for Authentication (EPA)/channel binding tokens (CBT)** liên hệ GSS với TLS channel. Khi TLS bị terminate ở ingress nhưng GSS accept ở backend, channel binding expectations có thể mismatch; cách sửa phải theo supported JDK/proxy/EPA architecture hoặc negotiate termination, **không tắt extended protection trên Domain Controller bằng registry workaround cũ** để qua lab. Test browser policies, TLS topology và chosen service principal.

### 15.5. API stateless vs web session

Nếu mỗi HTTP request tự gửi Negotiate token, backend có thể authenticate theo request; nếu app tạo web session, bearer cookie sẽ tiếp tục cho phép access sau đó. Cần quyết định:

- Request-specific GSS negotiation và SecurityContextRepository.
- Session fixation strategy khi session được tạo.
- CSRF protection cho state-changing browser POST.
- Cookie Secure/HttpOnly/SameSite, expiration.
- Redis-backed sessions nếu nhiều nodes.
- Logout local không nhất thiết hủy OS TGT/domain login; browser có thể tự negotiate lại. Làm rõ “đăng xuất portal” vs “đăng xuất Windows/Kerberos realm”.
- Disable/locked user và revocation cần áp dụng dù client có TGT hợp lệ.

## 16. Lab test: điểm kiểm tra theo tầng

### 16.1. Test TGT (không liên quan Spring)

```bash
kinit student1@LAB.EXAMPLE.TEST
klist
```

Nếu fail, sửa KDC/time/DNS/password/user status. Không chạm web app trước.

### 16.2. Test service ticket (KDC lookup)

```bash
kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST
```

Nếu `Server not found in Kerberos database`, tên principal/realm sai. Nếu KVNO/enctype không như kỳ vọng, kiểm KDC/service key mapping và keytab.

### 16.3. Test backend acceptor từ curl

```bash
curl -i --negotiate -u : \
  https://portal.lab.example.test/reports/overview
```

Quan sát:
- First challenge `401 WWW-Authenticate: Negotiate` có thể là bình thường.
- Header `Authorization: Negotiate ...` có xuất hiện trên request tiếp theo không?
- GSS validator accept với keytab đúng không?
- Local principal có role viewer không?
- Response cuối là 200/403 hay 401 theo acceptance case?

### 16.4. Test user khác

Tạo test accounts trong lab:
- `student1` có `ROLE_REPORT_VIEWER`.
- `student2` không có role.
- `locked1` local locked mặc dù KDC vẫn cấp ticket nếu lab policy cho phép.

Không dùng role từ username pattern hoặc `realm==LAB => ADMIN`. Nếu KDC account locked thật thì client không lấy ticket mới; để cô lập **local lock policy**, có thể giữ KDC account vẫn hoạt động và chỉ khóa local app account trong fixture.

### 16.5. Test rotation

- Trước rotation, mọi nodes accept current ticket.
- Sau approved rotation, check `klist -kte` trên từng pod có expected KVNO/enctypes.
- Đăng nhập từ client có service ticket mới.
- Test existing cached tickets theo overlap policy.
- Không thay key trong KDC liên tục bằng `ktadd` mỗi pod.
- Thử failover giữa nodes sau rotation.

## 17. Test matrix âm tính và sự cố quan trọng

| ID | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| KRB-01 | Không có TGT và không có credentials khác | Client không tự SSO thành công |
| KRB-02 | Có TGT, chưa có service ticket | Client có thể xin TGS ticket khi SPN registered |
| KRB-03 | Service principal `HTTP/portal...` không có trên KDC | TGS lookup thất bại |
| KRB-04 | Browser dùng IP literal/hostname alias không đăng ký | SPN mismatch, không accept |
| KRB-05 | Pod A keytab KVNO 3, pod B KVNO 2 | Failure theo node; readiness/rotation QA fail |
| KRB-06 | Keytab đọc được bởi process khác ngoài scope | Security QA fail |
| KRB-07 | Keytab được commit trong Git/JAR/Docker image | Security QA fail |
| KRB-08 | Client gửi raw `Authorization: Negotiate garbage` | GSS reject |
| KRB-09 | Header `Authorization: Basic` khi SPNEGO-only | Không authenticate bằng Basic |
| KRB-10 | Token cho service `HTTP/other.host` | Reject by service GSS acceptor |
| KRB-11 | Service ticket expired | GSS reject |
| KRB-12 | User/KDC/SP clocks lệch ngoài tolerance | GSS error, NTP correction |
| KRB-13 | Keytab có SPN đúng nhưng enctype sai | Reject, correct KDC/keytab policy |
| KRB-14 | `ktadd` re-run vô tình tăng KVNO | Thử mới fail, xử lý rotation |
| KRB-15 | Keytab unreadable (permission 000) | Startup/GSS accept fail, no fallback |
| KRB-16 | Wrong `krb5.conf` realm mapping | KDC discovery/principal mapping fail |
| KRB-17 | Browser không allow Negotiate cho site | 401/fallback, không bypass auth |
| KRB-18 | Ingress strip Authorization header | SPNEGO negotiation không complete |
| KRB-19 | Ingress strip WWW-Authenticate response | Browser không có challenge |
| KRB-20 | TLS cert self-signed không trusted | HTTPS fail; không dùng `curl -k` workaround |
| KRB-21 | Valid Kerberos user, local role missing | Protected path deny |
| KRB-22 | Valid Kerberos user, local account LOCKED | Deny despite successful GSS |
| KRB-23 | Principal `user@REALM-B` trùng username `user@REALM-A` | Không map chung local account |
| KRB-24 | Admin account role only present in untrusted header | Không cấp ADMIN |
| KRB-25 | Existing web session sau role revoke | Deny/revoke theo local consistency policy |
| KRB-26 | Existing web session sau account locked | Revocation/test old cookie |
| KRB-27 | Two nodes same SPN/keytab version | Both authenticate |
| KRB-28 | One pod missing keytab secret mount | Pod fail readiness, no insecure fallback |
| KRB-29 | Duplicate Spring Spnego filter registration | Test detects double negotiation |
| KRB-30 | Spring SecurityContext not persisted by design | Request-only auth expected, document behavior |
| KRB-31 | Stateful session configured but context not saved | Integration test fails |
| KRB-32 | Session invalidated, browser still has Kerberos TGT | May reauthenticate; logout UX documented |
| KRB-33 | Negotiate token logged raw at ingress | Security QA fail |
| KRB-34 | KDC unavailable but cached tickets still valid | Test real behavior, do not assume KDC always contacted per request |
| KRB-35 | KDC unavailable and client lacks valid tickets | Cannot initiate new SSO |
| KRB-36 | Kerberos vs NTLM mechanism accepted unexpectedly | Reject/limit by supported mechanism policy |
| KRB-37 | EPA/CBT mismatch across TLS proxy | Architecture review; no unsafe security disable |
| KRB-38 | Large or malformed HTTP auth header | Parser limits/reject, no OOM |
| KRB-39 | New JDK/SSPI library changes GSS behavior | Regression tests on actual OS/JVM |
| KRB-40 | User opens admin route with viewer role | 403, no privilege escalation |

### 17.1. Positive control bắt buộc

Một negative test có lỗi GSS mà vẫn thấy 401 **chưa chứng minh** local locked policy. Cần:
1. Valid TGT/service ticket/SPN/keytab/GSS success từ user test.
2. User ACTIVE + role chính xác ⇒ app route pass.
3. Cùng protocol verification nhưng local account LOCKED ⇒ app deny.
4. Cùng GSS, local account ACTIVE nhưng thiếu role ⇒ protected route deny.
5. Wrong SPN/keytab ⇒ GSS stage reject trước local user mapping.
6. Log reason code ở nơi nội bộ, không leak raw token.

### 17.2. MockMvc không thay một KDC thật

Spring Security Test `@WithMockUser` hoặc mock Authentication chỉ tạo SecurityContext/test principal; chúng không chạy `kinit`, `kvno`, browser Negotiate hay Java GSS acceptor. Unit tests policy rất hữu ích, nhưng phải có **lab integration** để chứng minh keytab thực, SPN, headers, GSS và KDC interoperability.

## 18. Java 17 chạy độc lập: kiểm chính sách sau GSS và keytab metadata

Ví dụ sau **không yêu cầu KDC, keytab hay Spring**. Nó tạo một bảng mô phỏng:
- Client có/không có Negotiate header.
- Phép verify GSS đã thành công hay thất bại (**boolean giả lập chỉ do trusted server verifier cung cấp**, không nhận từ HTTP/client).
- Expected service principal.
- Một **KVNO được phép** trong keytab view; trong thực tế **Java GSS handles keys/KVNO**, ứng dụng không parse ticket để tự kiểm thủ công.
- Thời hạn, replay indicator mô phỏng, account local ACTIVE/LOCKED và local role.
- Chấp nhận rotation khi keytab view có cả KVNO cũ/mới đã approved.

Chương trình này là **policy oracle** để học logic. Không xây hệ thống xác thực bằng cách tin một `gssAccepted` boolean do request JSON cung cấp, không deserialize Kerberos token bằng regex, không đọc secret keytab từ app demo.

Lưu file `SpnegoKeytabLabPolicyDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class SpnegoKeytabLabPolicyDemo {

    enum Decision {
        CHALLENGE,
        ALLOW,
        DENY_GSS,
        DENY_SPN,
        DENY_KEY_VERSION,
        DENY_EXPIRED,
        DENY_REPLAY,
        DENY_UNKNOWN_USER,
        DENY_LOCKED,
        DENY_ROLE
    }

    record KeytabView(
            String servicePrincipal, Set<Integer> acceptedKvnos) {
        KeytabView {
            acceptedKvnos = Set.copyOf(acceptedKvnos);
        }
    }

    record LocalAccount(
            boolean active, Set<String> authorities) {
        LocalAccount {
            authorities = Set.copyOf(authorities);
        }
    }

    record TicketFixture(
            String requestId,
            String servicePrincipal,
            String clientPrincipal,
            int kvno,
            Instant expiresAt,
            boolean gssAccepted) {}

    static class LabGate {
        private final KeytabView keytab;
        private final Map<String, LocalAccount> accounts;
        private final Set<String> seenRequestIds = new HashSet<>();

        LabGate(KeytabView keytab,
                Map<String, LocalAccount> accounts) {
            this.keytab = keytab;
            this.accounts = new HashMap<>(accounts);
        }

        Decision accept(
                TicketFixture fixture,
                boolean negotiateHeaderPresent,
                Instant now) {

            if (!negotiateHeaderPresent) {
                return Decision.CHALLENGE;
            }
            if (!fixture.gssAccepted()) {
                return Decision.DENY_GSS;
            }
            if (!keytab.servicePrincipal()
                    .equals(fixture.servicePrincipal())) {
                return Decision.DENY_SPN;
            }
            if (!keytab.acceptedKvnos().contains(fixture.kvno())) {
                return Decision.DENY_KEY_VERSION;
            }
            if (!now.isBefore(fixture.expiresAt())) {
                return Decision.DENY_EXPIRED;
            }
            if (!seenRequestIds.add(fixture.requestId())) {
                return Decision.DENY_REPLAY;
            }

            LocalAccount local = accounts.get(
                    fixture.clientPrincipal());
            if (local == null) {
                return Decision.DENY_UNKNOWN_USER;
            }
            if (!local.active()) {
                return Decision.DENY_LOCKED;
            }
            if (!local.authorities().contains(
                    "ROLE_REPORT_VIEWER")) {
                return Decision.DENY_ROLE;
            }
            return Decision.ALLOW;
        }
    }

    static TicketFixture ticket(
            String requestId, String service, String user,
            int kvno, Instant expiry, boolean gssAccepted) {
        return new TicketFixture(
            requestId, service, user, kvno, expiry, gssAccepted);
    }

    static void show(String description, LabGate gate,
                     TicketFixture fixture, boolean hasHeader,
                     Instant now) {
        System.out.println(description + ": "
                + gate.accept(fixture, hasHeader, now));
    }

    public static void main(String[] args) {
        String service =
            "HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST";
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Instant future = Instant.parse("2026-11-07T10:05:00Z");
        Instant past = Instant.parse("2026-11-07T09:59:00Z");

        Map<String, LocalAccount> accounts = Map.of(
            "student1@LAB.EXAMPLE.TEST",
                new LocalAccount(
                    true, Set.of("ROLE_REPORT_VIEWER")),
            "locked1@LAB.EXAMPLE.TEST",
                new LocalAccount(
                    false, Set.of("ROLE_REPORT_VIEWER")),
            "student2@LAB.EXAMPLE.TEST",
                new LocalAccount(true, Set.of()));

        LabGate oldKeytab = new LabGate(
            new KeytabView(service, Set.of(3)), accounts);

        TicketFixture valid = ticket(
            "ticket-1", service, "student1@LAB.EXAMPLE.TEST",
            3, future, true);

        show("No header", oldKeytab,
            valid, false, now);
        show("Valid GSS with local viewer role", oldKeytab,
            valid, true, now);
        show("Replay same request id", oldKeytab,
            valid, true, now);

        show("Wrong service principal", oldKeytab,
            ticket("ticket-2",
                "HTTP/other.lab.example.test@LAB.EXAMPLE.TEST",
                "student1@LAB.EXAMPLE.TEST",
                3, future, true), true, now);
        show("New KVNO on old keytab", oldKeytab,
            ticket("ticket-3", service,
                "student1@LAB.EXAMPLE.TEST",
                4, future, true), true, now);
        show("Expired fixture", oldKeytab,
            ticket("ticket-4", service,
                "student1@LAB.EXAMPLE.TEST",
                3, past, true), true, now);
        show("GSS verification failed", oldKeytab,
            ticket("ticket-5", service,
                "student1@LAB.EXAMPLE.TEST",
                3, future, false), true, now);
        show("Local account locked", oldKeytab,
            ticket("ticket-6", service,
                "locked1@LAB.EXAMPLE.TEST",
                3, future, true), true, now);
        show("Missing local role", oldKeytab,
            ticket("ticket-7", service,
                "student2@LAB.EXAMPLE.TEST",
                3, future, true), true, now);
        show("Unknown principal", oldKeytab,
            ticket("ticket-8", service,
                "unknown@LAB.EXAMPLE.TEST",
                3, future, true), true, now);

        LabGate rollover = new LabGate(
            new KeytabView(service, Set.of(3, 4)), accounts);
        show("New KVNO during approved overlap", rollover,
            ticket("ticket-9", service,
                "student1@LAB.EXAMPLE.TEST",
                4, future, true), true, now);
    }
}
```

Biên dịch và chạy với **JDK 17+**, không cần external dependency:

```bash
javac SpnegoKeytabLabPolicyDemo.java
java SpnegoKeytabLabPolicyDemo
```

Stdout **chính xác**:

```text
No header: CHALLENGE
Valid GSS with local viewer role: ALLOW
Replay same request id: DENY_REPLAY
Wrong service principal: DENY_SPN
New KVNO on old keytab: DENY_KEY_VERSION
Expired fixture: DENY_EXPIRED
GSS verification failed: DENY_GSS
Local account locked: DENY_LOCKED
Missing local role: DENY_ROLE
Unknown principal: DENY_UNKNOWN_USER
New KVNO during approved overlap: ALLOW
```

### 18.1. Diễn giải

- Không có Negotiate => **CHALLENGE**, tương ứng ý niệm `401 WWW-Authenticate: Negotiate`.
- Valid GSS và local viewer => **ALLOW**; successful Kerberos name authentication phải đi qua local policy.
- Replay requestId => **DENY_REPLAY** trong mô hình. GSS thật có replay semantics riêng; không tạo app-specific “ticket ID” từ raw GSS token bằng cách parse tùy tiện.
- Wrong SPN => **DENY_SPN**; browser token không được chấp nhận cho service khác.
- KVNO mới trên keytab cũ => **DENY_KEY_VERSION**; trong production verifier/krb5 sẽ tự đọc keytab KVNO, không làm app code thủ công.
- Expired => reject, không nới clock tolerance vô hạn.
- `gssAccepted=false` => **DENY_GSS**; boolean này chỉ là kết quả **mô phỏng của validator tin cậy**, không phải dữ liệu user.
- Account locked/role missing/unknown => deny sau verified identity, không auto-provision quyền.
- Keytab view với các version đã phê duyệt => accept KVNO 4 trong conceptual rollover.

### 18.2. Demo không thay được những gì?

- Không đọc `/etc/krb5.conf`, keytab, LDAP, CAS/SSO Session, SPNEGO tokens hoặc Kerberos tickets thật.
- Không gọi `GSSContext.acceptSecContext`, không xác minh encryption, KDC, key version thực, ticket authenticity hay replay cache của Kerberos mechanism.
- Không tạo HTTP headers/response, không chạy Spring Security filters, không session fixation protection.
- `gssAccepted` có thể bị giả nếu lấy từ request; production phải đến từ validated GSS result và **không** truy cập trực tiếp từ controller/JSON input.
- `acceptedKvnos` chỉ là mô hình trực quan; real keytab chứa actual encryption keys/enctypes và GSS tự chọn keys.
- `requestId` là một mock token identifier; SPNEGO API **không công bố ticket ID theo format đó** cho ứng dụng tự quản.
- Dữ liệu `LocalAccount` nằm trong `Map`, không có DB concurrency, revocation events, tenant, LDAP/AD trust hay active-session invalidation.
- Time `Instant` đã cố định; real Kerberos clocks/NTP phải được kiểm tra ở KDC/client/SP.

## 19. Troubleshooting từng bước

| Triệu chứng | Đọc lớp nào trước? | Hành động nên làm |
| --- | --- | --- |
| Không thấy `WWW-Authenticate: Negotiate` | HTTP entrypoint/ingress | Kiểm SecurityFilterChain, 401/302, proxy headers |
| Browser không gửi `Authorization: Negotiate` | Browser policy/client TGT | `klist`, site allowlist, exact FQDN, client OS |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC principal database | `kvno`, service principal registration |
| `KDC_ERR_PREAUTH_FAILED` ở `kinit` | Client credentials | User account/password/realm/time |
| `Clock skew too great` | NTP | Đồng bộ KDC/client/SP, không tăng skew tùy tiện |
| `Cannot find key of appropriate type` | Keytab/enctype | `klist -kte`, KDC KVNO/enctypes, JDK |
| `Integrity check on decrypted field failed` | SPN/keytab/key version | So KVNO và actual service principal/key rotation |
| `Keytab file not found` | OS container mount | Path/permission/read-only secret |
| `javax.servlet` mismatch | Dependency generation | Spring Boot 2 vs 3/4, Jakarta-compatible modules |
| 401 repeated despite TGT | Negotiate header or GSS | Proxy strip, browser policy, SPN mismatch |
| GSS succeeded but endpoint 403 | Spring local authorities | UserDetailsService/ROLE prefix/resource roles |
| GSS succeeded but user shown anonymous next request | SecurityContext persistence | Default request-only repo vs session strategy |
| Only node B fails | Keytab version/secrets | Per-pod mount, config, SPN/realm, runtime |
| Service login succeeds then instant logout | Session fixation/CSRF/cookie | Secure SameSite/Domain/Path, persistence |
| Browser accepts NTLM but org requires Kerberos | Mechanism policy | Browser/intranet auth and server accepted mech |
| Channel binding mismatch | TLS proxy + EPA/CBT | Supported architecture, not unsafe registry tweak |
| Keytab stale after repeated `ktadd` | KDC changed KVNO | Restore approved key management process |
| Java debug leaks principal/token material | Logging | Disable debug, redact and rotate if exposed |
| `curl: option --negotiate not supported` | curl build | Install GSSAPI-enabled curl |
| Local lock ignored | App policy gate | Review UserDetails/provider, test old sessions |

### 19.1. Trình tự điều tra ít tốn công

1. `getent hosts portal.lab.example.test` hoặc DNS lookup đúng trên client.
2. `kinit` và `klist` có TGT valid.
3. `kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` xin được service ticket.
4. `klist -kte /run/secrets/portal-http.keytab` trên server (với quyền cho phép) có SPN+KVNO phù hợp.
5. HTTP response đầu có `WWW-Authenticate: Negotiate`, không bị ingress nuốt.
6. Client gửi header Negotiate với actual GSS token, không phải Basic.
7. Spring validator accept và map đúng verified Kerberos principal.
8. Local UserDetails và role đúng; 403 nếu thiếu quyền.
9. Session policy/persistence đúng khi request tiếp theo hoặc node đổi.
10. Tắt debug, giữ only sanitized correlation và test negative cases.

### 19.2. Nguyên nhân “lúc được lúc không”

Có thể do hai pods dùng hai keytab versions, hệ thống DNS cân bằng hostname khác, browser có/không có ticket cache, một node lệch đồng hồ, Redis-backed session không nhất quán hoặc routing qua ingress bị strip headers không đồng nhất. Đừng tăng tolerance hoặc tắt Kerberos để giảm tỉ lệ 401; so node/config/policy theo từng bước đã đo.

## 20. Kiểm thử nâng cao: về phía HTTP, TLS và cluster

### 20.1. Header spoofing

Không cho `X-User: admin`, `X-Kerberos-Principal: student1` hoặc query `?user=admin` vào `Authentication`. Chỉ verified GSS principal từ `KerberosServiceAuthenticationProvider` hoặc trusted gateway authenticated identity được map. Nếu ingress làm Kerberos acceptor, phải **strip user-supplied identity headers** ở network edge và xác thực đường backend.

### 20.2. Không tin GSS token từ ứng dụng khác

Một ticket Kerberos được tạo cho `HTTP/service-b` không được phép đăng nhập `HTTP/service-a`. Nếu service A accept token B, có thể có keytab wildcard/keys bị chia sai hoặc proxy trust bypass. Test wrong-SPN tokens và exact public hostname.

### 20.3. CSRF sau SPNEGO

SPNEGO xác thực identity ở HTTP layer nhưng nếu app dùng cookies hoặc browser tự gửi Negotiate credentials cho trusted site, **CSRF vẫn là một mối đe dọa** đối với state-changing operations. Spring Security CSRF nên được giữ theo application threat model, dùng POST/CSRF token cho user-initiated logout và nghiệp vụ thay đổi state; không tắt CSRF toàn site vì dùng Kerberos.

### 20.4. Caching và SSO session

Browser có thể tiếp tục gửi service ticket sau local logout vì OS TGT còn valid. “Logout” từ web app không đồng nghĩa `kdestroy` hoặc Windows domain logout. Nếu nghiệp vụ đòi reauthentication/MFA thật, cần server-side auth freshness/context control và account policy; không tuyên bố clear HttpSession là đã xóa Kerberos credentials khỏi máy trạm.

### 20.5. Proxy timeout/body size

SPNEGO tokens có thể lớn khi có PAC/AD groups, proxy cần đủ header size nhưng không mở vô hạn, giới hạn DoS và kiểm memory. Một số reverse proxies mặc định không forward Authorization header; phải cấu hình explicit và test. Error 400/431 có thể xảy ra trước khi request đến Spring, nên log và monitor ở ingress chứ không chỉ JVM.

## 21. Runbook dựng lab từ trống đến nghiệm thu

### Bước 1 — Realm và network

- Cấp máy KDC riêng, domain thử nghiệm, đồng bộ NTP.
- Kiểm DNS `kdc.lab.example.test` và `portal.lab.example.test`.
- Tạo `/etc/krb5.conf` theo phần 5.
- Khởi tạo realm mới nếu và chỉ nếu KDC chưa tồn tại.
- Cho phép cổng KDC từ clients, không mở admin service công khai.

### Bước 2 — Test principals

- Admin tạo user `student1` qua interactive `addprinc`.
- Admin tạo `HTTP/portal.lab.example.test` qua `addprinc -randkey`.
- Admin `ktadd` một lần có kế hoạch, lưu KVNO/enctype.
- Đưa keytab qua channel an toàn tới service.

### Bước 3 — Client readiness

- `kinit student1@LAB.EXAMPLE.TEST`.
- `klist` có TGT hợp lệ.
- `kvno HTTP/portal.lab.example.test@LAB.EXAMPLE.TEST` thành công.
- Browser/curl có GSSAPI support và đúng hostname/CA.

### Bước 4 — Java app

- Chọn Spring Security Kerberos modules tương thích Boot major.
- Cấu hình service-principal/keytab path từ trusted server config.
- Đặt `SpnegoEntryPoint` + `SpnegoAuthenticationProcessingFilter` + `KerberosServiceAuthenticationProvider`.
- Wire local `UserDetailsService` + protected roles.
- Chọn stateless-vs-session strategy và CSRF.
- Bật TLS ingress, ensure Negotiate headers survive.
- Start app với file secret readable chỉ process identity.

### Bước 5 — Verify protocol

- Không header: 401 Negotiate challenge.
- Valid test user: GSS accept và role-allowed route pass.
- Wrong SPN, stale keytab, missing keytab: reject.
- Missing role: 403.
- Locked local account: reject.
- Repeat/new request: expected SecurityContext lifetime và browser behavior.
- Multi-pod: both nodes accept current KVNO.

### Bước 6 — Rotation/cleanup

- Review KDC/keytab ownership và expiry/rotation plan.
- Không lặp `ktadd` để phát keytab cho từng pod.
- Rotate theo versioned secret distribution, test overlap/maintenance.
- Xóa ticket cache user test khi kết thúc phòng lab nếu phù hợp.
- Không giữ raw token captures/keytabs trong CI artifacts.
- Tắt JAAS/GSS debug và ghi kết quả QA bằng các reason codes đã sanitize.

## 22. Security checklist trước khi đưa lên staging

- [ ] KDC realm/trust policy, principal ownership và service SPN được phê duyệt.
- [ ] SPN khớp chính xác public FQDN/browser URL, tránh IP/alias bất ngờ.
- [ ] Service keytab chỉ có principals tối thiểu và được mount read-only.
- [ ] KDC user tickets không nằm trong server keytab, không nhầm TGT với keytab.
- [ ] Không commit keytab vào Git/JAR/Docker image hoặc chat/log.
- [ ] KVNO/enctypes của KDC và mọi app nodes khớp; rotation có kế hoạch.
- [ ] KDC/client/SP clocks đồng bộ; skew config không quá rộng.
- [ ] `useKeyTab=true`, `isInitiator=false`, `storeKey=true`, `doNotPrompt=true` khi dùng JAAS acceptor.
- [ ] Spring Kerberos dependencies đúng groupId theo Spring Security 6 vs 7.
- [ ] Chỉ một Spnego filter/owner trong Spring Security chain.
- [ ] `SpnegoEntryPoint` phát 401 Negotiate; không login redirect loop.
- [ ] Spring Security provider gọi real GSS validator, không tin raw header.
- [ ] Principal được map theo realm/tenant và local account, không lấy email/header làm trust root.
- [ ] Role/admin privilege default-deny; locked/disabled user không được phép.
- [ ] SecurityContextRepository/session strategy rõ ràng và có test.
- [ ] User-initiated state-changing POST vẫn có CSRF protection.
- [ ] TLS cert CA/hostname verified; ingress trusted, forwarding headers đúng.
- [ ] GSS Negotiate token không bị log, leak hoặc rewrite qua proxy.
- [ ] Client browser intranet policy/allowed SPNEGO origins đã kiểm.
- [ ] Mechanism fallback NTLM chỉ khi risk policy thực sự cho phép.
- [ ] Cross-pod GSS, keytab mount, session and revocation tested.
- [ ] Logout UX giải thích OS TGT có thể còn nên browser reauthenticate.
- [ ] Không tắt EPA/channel binding hoặc TLS validation bằng workaround cũ.
- [ ] Lab tests gồm 401 challenge, valid 200, missing role 403 và malformed token reject.
- [ ] Test expired ticket, KDC offline, wrong SPN, wrong KVNO và node drift.
- [ ] Data/PII privacy: không lưu raw HTTP Authorization, keytab, PAC, TGT, full principals trong metrics.
- [ ] Monitoring và runbooks có owner/alert thresholds, rollback/rotation.
- [ ] Java17 demo được phân biệt khỏi production GSS cryptographic verification.

## 23. Câu hỏi ôn tập

**1. SPNEGO có giống username/password Basic auth không?**  
Không. Browser gửi opaque GSS token qua `Authorization: Negotiate`, thường dựa trên Kerberos ticket đã xin từ KDC.

**2. Keytab dùng ở client hay server?**  
Trong bài này keytab chứa **service principal long-term key trên server SPNEGO acceptor**. User client giữ TGT/tickets trong credential cache; không upload TGT thành keytab.

**3. Tại sao HTTP SPN vẫn bắt đầu `HTTP/` khi URL dùng HTTPS?**  
Vì service class của Kerberos HTTP authentication là `HTTP`; HTTPS là lớp vận chuyển TLS riêng.

**4. Vì sao `HTTP/pod-a.internal` không phù hợp khi browser gọi `portal.lab.example.test`?**  
Browser thường yêu cầu ticket cho host trong URL/canonical SPN, không theo pod mà ingress lựa chọn.

**5. `ktadd` có thay đổi service key không?**  
Theo MIT, `ktadd` mặc định randomizes keys/tăng KVNO. Có `-norandkey` cho export không đổi key khi KDC cho phép; không lặp vô thức.

**6. Keytab có nên chứa principal `krbtgt/REALM` không?**  
Không. Web app chỉ cần key của HTTP service, ít quyền nhất.

**7. `isInitiator=false` nghĩa là gì?**  
JAAS login làm Kerberos acceptor, không chủ động xin TGT như client. Cần `useKeyTab`/`storeKey` cho service key.

**8. First 401 có phải SSO fail không?**  
Không. Nó thường là `WWW-Authenticate: Negotiate` challenge để browser gửi token.

**9. SPNEGO token có thể decode như JWT không?**  
Không. Nó là opaque binary token giao thức GSS/SPNEGO, không phải JSON claims.

**10. Vì sao user Kerberos hợp lệ vẫn bị 403?**  
User thiếu local role hoặc resource authorization; authentication và authorization độc lập.

**11. Spring Security Kerberos 2.2 và 7 dùng groupId giống nhau không?**  
Không. Nhánh 2.2 dùng `org.springframework.security.kerberos`; nhánh 7 dùng `org.springframework.security` theo docs.

**12. `SpnegoAuthenticationProcessingFilter` có mặc định lưu SecurityContext vào HttpSession không?**  
Không nên giả định. Source hiện hành dùng request-level default; cần cấu hình `SecurityContextRepository`/session strategy nếu muốn persistent session.

**13. Có thể dùng raw `X-User` từ ingress làm principal không?**  
Không trừ khi ingress thực sự xác thực GSS, strip headers do client cung cấp và backend link trusted.

**14. Dùng `kinit -kt` service keytab làm server keepalive có cần không?**  
Không. SPNEGO server là acceptor; thử keytab bằng actual GSS flow và `klist -kte`.

**15. KDC down có làm mọi request thất bại ngay không?**  
Không nhất thiết: clients có cached TGT/service tickets còn hiệu lực. Test thật, không assume KDC always contacted mỗi request.

**16. Có thể tự tắt CSRF vì user dùng SPNEGO không?**  
Không. Browser vẫn có thể tự gửi credentials/cookies; state-changing operations cần CSRF controls theo threat model.

**17. Vì sao logout portal không đảm bảo browser không tự login lại?**  
OS/user Kerberos TGT vẫn còn, browser có thể tự Negotiate token mới. Cần auth freshness/step-up nếu cần.

**18. Nếu chỉ pod B fail GSS sau deploy thì nên kiểm gì?**  
Keytab/SPN/KVNO/enctypes/permissions, Kerberos config, clock và header forwarding trên pod B.

**19. Khi gặp channel-binding mismatch thì có nên tắt Windows EPA bằng registry không?**  
Không tùy tiện. Phải dùng supported TLS/proxy/GSS deployment architecture và security review.

**20. Java17 demo có thực sự verify Kerberos ticket không?**  
Không. Nó chỉ là policy oracle mô phỏng; cryptographic accept phải do Java GSS/JAAS qua Spring Kerberos validator.

## 24. Tài liệu chính thức

- [Spring Security — Kerberos Introduction (7.x)](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): bản 7.x, Java17, **artifact groupId change**.
- [Spring Security Kerberos — Introduction (2.2.x)](https://docs.spring.io/spring-security-kerberos/reference/introduction.html): bản 2.2.0 hỗ trợ Spring Security 6.5.1/Framework 6.2.8 và Jakarta Servlet.
- [Spring Security — Spring and Spring Security Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): SpnegoEntryPoint, SpnegoAuthenticationProcessingFilter, KerberosServiceAuthenticationProvider, SunJaasKerberosTicketValidator và Java config.
- [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): GSS headers, filter behavior, session/context repository.
- [Spring Security Kerberos — SunJaasKerberosTicketValidator Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): `setServicePrincipal`, `setKeyTabLocation`, JAAS validator.
- [Oracle JDK 17 — Krb5LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html): `useKeyTab`, `keyTab`, `principal`, `storeKey`, `isInitiator=false`.
- [Oracle JDK 17 — GSSContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html): `acceptSecContext`, security context mechanism.
- [MIT Kerberos — krb5.conf](https://web.mit.edu/kerberos/krb5-latest/doc/admin/conf_files/krb5_conf.html): realm, KDC and domain mappings.
- [MIT Kerberos — kadmin command reference](https://www.mit.edu/~kerberos/krb5-latest/doc/admin/admin_commands/kadmin_local.html): `addprinc -randkey`, `ktadd` mặc định rotate key và `-norandkey`.
- [MIT Kerberos — Application Servers](https://www.mit.edu/~kerberos/krb5-latest/doc/admin/appl_servers.html): service keytab, KVNO, Kerberos app server best practices.
- [RFC 4559 — SPNEGO-based Kerberos HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): `WWW-Authenticate: Negotiate`, `Authorization: Negotiate`.
- [RFC 4120 — Kerberos Network Authentication Service V5](https://www.rfc-editor.org/rfc/rfc4120): KDC/TGT/service tickets, replay/clock properties.
- [RFC 4178 — SPNEGO GSS-API](https://www.rfc-editor.org/rfc/rfc4178): negotiation mechanism security context.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): failure handling, local account status.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, fixation, revocation.
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): browser-driven state-changing requests.

**Ghi nhớ:** Một SPNEGO tích hợp đúng phải nối được **principal từ Kerberos realm** đến **dịch vụ HTTP SPN đúng public hostname**, giữ **service long-term secret trong keytab an toàn**, xử lý `401 Negotiate` và xác minh opaque GSS token bằng **JAAS/GSS**. Sau khi GSS xác thực, vẫn phải kiểm local user enabled/locked/roles, session/CSRF và authorization. Khi lab lỗi, kiểm theo thứ tự **kinit → kvno → keytab/KVNO/enctype → HTTP headers/proxy → GSS validator → Spring authorities**; không bỏ xác thực, log raw ticket hay reset keytab không kiểm soát để “làm cho login chạy”.