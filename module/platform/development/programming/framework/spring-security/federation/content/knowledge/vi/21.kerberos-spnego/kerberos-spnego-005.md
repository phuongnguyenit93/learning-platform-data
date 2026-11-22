# Phân biệt mật khẩu người dùng, ticket Kerberos và keytab dịch vụ

> **Module:** Spring Security – federation · **Nhóm:** Kerberos và SPNEGO. Tài liệu này giải thích ba loại credential trong Kerberos v5, ai giữ chúng, chúng xuất hiện ở giai đoạn nào, Spring Security SPNEGO dùng chúng ra sao, và cách kiểm tra/vận hành an toàn khi triển khai ứng dụng Java 17+.

## 1. Kết luận cốt lõi

Ba thuật ngữ không thể dùng thay cho nhau:

1. **Mật khẩu người dùng (user password):** một bí mật hoặc yếu tố xác thực ban đầu giúp user chứng minh danh tính với KDC/identity system. Với flow password-based Kerberos, mật khẩu liên quan đến **long-term key của user principal** thông qua cơ chế string-to-key; password **không được gửi đến ứng dụng Spring HTTP khi browser đang dùng Kerberos SPNEGO**. Nhiều môi trường có PKINIT, smart card, OS logon hay cơ chế khác thay cho việc nhập password trực tiếp.
2. **Ticket Kerberos:** artifact **do KDC phát hành**, chứa các thông tin principal, target service và thời hạn được bảo vệ mật mã. Có **Ticket Granting Ticket (TGT)** dùng để xin tickets khác và **service ticket (ST)** dành cho một service cụ thể. Client giữ session key phù hợp và gửi **ticket cùng Authenticator** để chứng minh sở hữu key. Ticket **không phải user password**.
3. **Keytab của dịch vụ:** file nhị phân chứa **long-term secret keys** cho một hoặc nhiều service principals cùng các trường principal/enctype/kvno. Spring/JAAS/GSS acceptor dùng keytab để giải mã/kiểm ticket gửi tới service của mình. File này **không phải ticket, không phải password plaintext**, nhưng là secret cấp độ cao cần bảo vệ nghiêm ngặt; không bao giờ gửi nó tới browser.

**Mô hình nhớ:** user password/phương thức ban đầu → **AS exchange** lấy TGT → **TGS exchange** lấy service ticket → client HTTP gửi **SPNEGO AP-REQ** → service dùng **keytab** kiểm ticket và Authenticator → Spring tạo Authentication/roles sau validation.

## 2. Kiến trúc tổng quan Kerberos + HTTP SPNEGO

~~~text
                   REALM: EXAMPLE.ORG
   +------------------------------------------------+
   | KDC: Authentication Server + Ticket Granting   |
   | Long-term principal keys, policies, ticketing  |
   +------------------------------------------------+
          ^ AS-REQ/AS-REP             ^ TGS-REQ/TGS-REP
          |                           |
 User/password or other auth       TGT + request
          |                           |
          v                           v
  +--------------------------------------------------+
  | Client workstation / OS credential cache        |
  | TGT + key material; service ticket + session key |
  +--------------------------------------------------+
                          |
                          | Browser / GSS / SPNEGO
                          | Authorization: Negotiate
                          v
  +--------------------------------------------------+
  | Spring Servlet app at portal.example.org         |
  | SPN HTTP/portal.example.org@EXAMPLE.ORG          |
  | Keytab with HTTP service long-term keys          |
  | Kerberos ticket validation -> trusted principal  |
  | UserDetailsService -> GrantedAuthority           |
  +--------------------------------------------------+
~~~

Không có bước nào ở sơ đồ yêu cầu browser **đưa password của alice cho ứng dụng portal**. GSS/SPNEGO chở một proof dùng service ticket, không phải thông tin đăng nhập cơ bản Basic Auth.

## 3. Những khái niệm quan trọng

| Thuật ngữ | Nghĩa |
|---|---|
| **Principal** | Identity Kerberos như `alice@EXAMPLE.ORG` hoặc `HTTP/portal.example.org@EXAMPLE.ORG` |
| **Realm** | Miền quản trị Kerberos, thường viết hoa |
| **KDC** | Key Distribution Center; gồm AS và TGS |
| **AS-REQ / AS-REP** | Initial exchange để client lấy TGT |
| **TGT** | Vé cấp cho `krbtgt/REALM@REALM`, dùng để xin service tickets |
| **TGS-REQ / TGS-REP** | Client dùng TGT xin ticket cho service khác |
| **Service Ticket** | Vé nhắm tới một service principal cụ thể |
| **AP-REQ / AP-REP** | Client trình ticket và Authenticator cho app; AP-REP có thể hỗ trợ mutual authentication |
| **Authenticator** | Dữ liệu tươi được bảo vệ bằng client–service session key |
| **Session key** | Khóa ngắn hạn do KDC phát cho phiên client-service |
| **Long-term key** | Khóa dài hạn của user principal hay service principal |
| **Keytab** | File chứa long-term keys, principal, enctype và kvno |
| **SPN** | Service Principal Name, ví dụ `HTTP/portal.example.org` |
| **kvno** | Key Version Number, hữu ích khi long-term key được rotate |
| **enctype** | Encryption type tương ứng một key/ticket |
| **Credential cache** | Chứa TGT, ST và key material phía client |
| **SPNEGO** | GSS-API mechanism negotiation, chuẩn RFC 4178 |
| **HTTP Negotiate** | HTTP authentication scheme mang GSS/SPNEGO token, RFC 4559 |
| **JAAS / Java GSS** | API Java làm Kerberos login và accept security context |
| **SecurityContext** | Trạng thái Authentication tại Spring Security, khác ticket Kerberos |

Ticket của **CAS**, **SAML Assertion** hoặc **OIDC ID Token** là những hiện vật **khác giao thức**. Không coi một chuỗi có tên “ticket” trong CAS là Kerberos service ticket.

## 4. Mật khẩu người dùng thuộc bước nào?

### 4.1. Với password-based authentication

Một user `alice@EXAMPLE.ORG` trên Linux có thể chạy:

~~~bash
kinit alice@EXAMPLE.ORG
~~~

Client tương tác với Authentication Service để xin TGT. Với phương thức dựa password, password/derived key phục vụ authentication và giải phần trao đổi được mã hóa theo Kerberos. **Không phải gửi password plaintext tới portal**. Sau khi lấy TGT, client có thể nhận ST cho nhiều services qua TGS mà không hỏi password lại mỗi lần.

### 4.2. Password và user long-term key khác nhau

Password là chuỗi bí mật người dùng có thể nhớ/nhập. Kerberos long-term key là material mật mã gắn với principal. Trong nhiều password-based schemes, khóa được dẫn xuất theo chuẩn string-to-key, salt và enctype; **không thể thay bằng một hàm hash tự viết như SHA-256(password)** rồi mong tương thích Kerberos.

Bên KDC cũng có long-term keys của các principals, nhưng app Spring acceptor **không cần đọc user password** để verify service tickets.

### 4.3. Không phải mọi Kerberos user đều nhập password

Các hình thức như Windows domain sign-in, PKINIT/smart card, hardware auth hoặc OS credential cache có thể cung cấp TGT mà app web không thấy thao tác nhập password. Do đó “Kerberos session tồn tại” không chứng minh user vừa nhập password hoặc đã hoàn thành MFA đúng cấp độ doanh nghiệp.

### 4.4. Đổi password có xóa tickets cũ ngay không?

Không thể mặc định. Khi user đổi password/long-term key, những TGT/ST đã được cấp từ trước có thể tiếp tục hoạt động đến hết lifetime hoặc khi chính sách KDC/realm thực hiện revocation thích hợp. **Password change khác ticket expiry, kdestroy, logout ứng dụng và account disable**.

Trong incident response phải đánh giá tickets, OS logon sessions, remote sessions và session lifecycle, không chỉ reset password.

## 5. Ticket Kerberos thực sự là gì?

### 5.1. TGT dành cho Ticket Granting Service

TGT được AS cấp sau initial authentication; phần nhạy cảm của ticket được mã hóa cho `krbtgt/REALM` bằng key mà KDC kiểm soát. User/client giữ TGT và phần key material phù hợp để gửi TGS-REQ. **TGT không được trình trực tiếp tới HTTP portal trong SPNEGO thông thường.**

### 5.2. Service ticket dành cho một SPN cụ thể

TGS phát ticket cho ví dụ:

~~~text
Client principal = alice@EXAMPLE.ORG
Service principal = HTTP/portal.example.org@EXAMPLE.ORG
Lifetime = theo KDC policy
Service ticket = ticket encrypted for target service long-term key
Client side = ticket + client-service session key
~~~

Một service ticket dùng cho `HTTP/wiki.example.org` không tự dùng được cho `HTTP/portal.example.org`. Kiểm đúng **sname/service principal**, realm, keys và GSS proof chứ không chỉ nhận string username từ token.

### 5.3. Session key bên trong trao đổi Kerberos

KDC thiết lập key ngắn hạn client-service. Client biết session key từ phần reply thích hợp. Service khôi phục session key từ encrypted ticket part được bảo vệ bằng long-term service key.

Khác biệt:

| Session key | Long-term key trong keytab |
|---|---|
| Gắn ticket/context client-service | Gắn service principal và kvno/enctype |
| Có lifetime ngắn theo ticket | Có hiệu lực cho đến rotation/retirement |
| Bảo vệ Authenticator/GSS operations | Bảo vệ encrypted ticket part |
| Được client và service dùng trong phiên | Được KDC và service giữ |
| Không phải mật khẩu người dùng | Không phải mật khẩu người dùng |

### 5.4. Vì sao ticket không tự chứng minh người đang dùng nó?

Trong AP exchange, client trình ticket **kèm Authenticator được bảo vệ bằng session key**. Service dùng long-term key từ keytab để xử lý encrypted ticket part, lấy session key rồi kiểm Authenticator/timestamp/replay policy. Nếu client chỉ có một ticket binary mà không có session key/proof thích hợp, nó chưa hoàn tất authentication đúng Kerberos.

### 5.5. Ticket cache vẫn nguy hiểm khi bị lộ

Credential cache có thể chứa ticket và key material giúp attacker giả mạo session khi bị chiếm. **Không công khai klist cache files**, không log token bytes và không nói “chỉ là ticket nên không cần bảo vệ”.

## 6. Keytab dịch vụ là gì?

Một keytab thường chứa entries có:
- Principal, ví dụ `HTTP/portal.example.org@EXAMPLE.ORG`.
- kvno của long-term key.
- Encryption type/enctype, ví dụ AES Kerberos enctype.
- Secret key bytes tương ứng.

Keytab có thể chứa nhiều enctypes, nhiều kvnos trong rotation và thậm chí nhiều principals. **Một file không nhất thiết bằng một account hay một password.** Nó là file binary, không phải chứng thư HTTPS hay nơi lưu TGT.

### 6.1. Keytab không phải plaintext password

Keytab lưu cryptographic keys; trong AD hoặc realm dùng password-derived service secrets, keytab có thể mang key material được dẫn xuất từ account secret, nhưng không lưu chuỗi password giống trong form. Về **mức độ nhạy cảm**, MIT Kerberos docs coi host keytab tương tự password của host vì người chiếm keys có thể giả mạo principal trong phạm vi đó.

### 6.2. Keytab chủ yếu dùng ở phía nào?

Trong Spring Security SPNEGO:
- Browser là **initiator**, dùng OS TGT hoặc ticket cache.
- HTTP server là **acceptor**, dùng service principal key từ keytab để verify incoming AP-REQ.
- Service thường **không cần biết user password**.

Không phải keytab chỉ có thể dùng acceptor: các batch services cũng có thể dùng **kinit -k** với keytab chứa principal của chúng để lấy TGT không tương tác. Điều đó càng chứng minh keytab là secret đáng bảo vệ, không phải file cấu hình công khai.

### 6.3. Keytab bị lộ nguy hiểm thế nào?

Các long-term keys bị lộ có thể:
- Hỗ trợ giả mạo service theo SPN tương ứng.
- Giải encrypted ticket part của captured service tickets phù hợp key/kvno.
- Làm lộ session keys trong các trường hợp ticket bị thu thập.
- Cho phép thao tác Kerberos khác khi principal/key và policy cho phép.

Hậu quả không giới hạn một ST đã hết hạn; nó có thể kéo dài đến khi khóa được rotate và tickets cũ hết hiệu lực. **Cần incident response/key rotation** thay vì chỉ xóa file đã lộ.

## 7. Bảng so sánh ba loại credential

| Góc nhìn | User password | Ticket Kerberos | Service keytab |
|---|---|---|---|
| Được tạo từ | User/account authentication process | KDC (AS/TGS) | KDC/admin và service account keys |
| Nơi dùng thường gặp | Initial auth AS-REQ/preauth | TGT tại TGS, ST tại service | Service-side GSS acceptor |
| Có gửi đến Spring HTTP app? | **Không** trong Kerberos SPNEGO | Token chứa ST/AP-REQ được gửi | **Không** |
| Mối quan hệ thời hạn | Account credential validity | Ticket lifetime/flags | Long-term key version/rotation |
| Dữ liệu chứa | Secret ban đầu | Client/service principal, encrypted part, session info | Principal, kvno, enctype, secret keys |
| User-specific hay service-specific? | User | TGT user→TGS; ST client→target service | Service principal |
| Có phải TLS cert? | Không | Không | Không |
| Có thể dùng để xác thực web user? | Thường để lấy TGT | ST+Authenticator sau verify | Chỉ giúp server kiểm ticket |
| Nếu lộ | User credential compromise | Ticket/cache hijack | Service impersonation/key compromise |
| Đổi user password tác động? | Có | Tickets đã phát có thể còn | **Không** trực tiếp đổi service keytab |
| Đổi service key/kvno tác động? | Không trực tiếp | ST cho service có thể bị ảnh hưởng | Phải đồng bộ keytab |
| Có tự cấp quyền business? | Không | Không | Không |
| Công cụ quan sát | Không log/dump | `klist`, `kvno` | `klist -kte` (metadata) |
| Logout local HttpSession có xóa? | Không | Không mặc định | Không |

**Hệ quả thực tế:** reset password của alice sẽ không sửa một keytab của portal đã sai SPN/kvno, và cập nhật keytab portal không làm browser mất user password/TGT.

## 8. Ba exchange của Kerberos

### 8.1. AS exchange – lấy TGT

~~~text
Client alice                    KDC Authentication Service
     |                                       |
     | AS-REQ / preauth theo policy          |
     +-------------------------------------->|
     |                                       | verify client identity
     |                                       | create TGT and session key
     |<--------------------------------------+
     | AS-REP                                |
     | Store TGT + client-side key material  |
~~~

TGT encrypted part thường dùng key của `krbtgt/REALM`. Client không lấy TGT và đem giải bằng password rồi đưa cho HTTP app. Với password-based AS exchange, user secret/derived key giúp giải phần thông tin thích hợp của AS reply, không phải dùng để giải service ticket.

### 8.2. TGS exchange – lấy ticket cho service

~~~text
Client with TGT                  KDC Ticket Granting Service
     |                                        |
     | TGS-REQ: HTTP/portal.example.org       |
     | includes TGT and authenticator         |
     +--------------------------------------->|
     |                                        | validate TGT
     |                                        | issue service ticket
     |<---------------------------------------+
     | TGS-REP: ST + client-side session key  |
~~~

Không hỏi user password ở bước TGS thông thường. Một TGT có thể được dùng để xin tickets tới nhiều target SPNs theo trust/policy.

### 8.3. AP exchange – trình vé cho service

~~~text
Browser with ST                      HTTP/portal service
     |                                        |
     | AP-REQ: service ticket + authenticator |
     +--------------------------------------->|
     |                                        | keytab -> service long-term key
     |                                        | decrypt ticket encrypted part
     |                                        | recover session key
     |                                        | check authenticator/replay/time
     |                                        | verified client principal
     |<---------------------------------------+
     | AP-REP if mutual auth required         |
~~~

Service thường **không liên hệ KDC cho mỗi AP-REQ** để validate ST bằng cách gửi ticket tới KDC. Nó dùng long-term key và GSS ticket verification tại chỗ, kết hợp KDC policies, clocks và realm configuration. Không nhầm với **CAS Service Ticket validation** vốn dùng back-channel call tới CAS.

## 9. HTTP SPNEGO/Negotiate là cách mang AP exchange

HTTP Negotiate theo RFC 4559:
1. Request protected chưa có credential phù hợp.
2. Service có thể trả **401 Unauthorized** và `WWW-Authenticate: Negotiate`.
3. Browser/SSPI/GSS-API lấy service ticket cho `HTTP/portal.example.org`, tạo token.
4. Browser gửi `Authorization: Negotiate <Base64GssToken>`.
5. Spring Security SPNEGO filter chuyển token cho GSS ticket validator.
6. Ticket/Authenticator được verify; trusted principal được lấy từ GSS context.
7. Spring tạo Authentication và thực thi UserDetails/authorization policy.

~~~http
GET /private HTTP/1.1
Host: portal.example.org
Authorization: Negotiate YIIB...example-opaque-token...
~~~

Header chỉ minh họa, không có token hợp lệ.

### 9.1. Có thể cần nhiều round trips

SPNEGO/GSS handshake có thể gồm nhiều 401/response tokens. Một success response cũng có thể chứa final `WWW-Authenticate: Negotiate ...` cho mutual authentication. Không hardcode giả định đúng một request và một response trong mọi client.

### 9.2. Header Negotiate có nhất thiết là Kerberos không?

**Không.** SPNEGO là thương lượng GSS mechanism. Một số môi trường Windows có thể fallback sang **NTLM**. Nếu chính sách yêu cầu Kerberos-only, phải kiểm negotiated mechanism và chặn fallback không được phép. Chỉ nhìn thấy chữ Negotiate chưa chứng minh đã chạy Kerberos v5.

### 9.3. Kerberos không thay HTTPS

RFC 4559 nhấn mạnh HTTP Negotiate chỉ là authentication facility, không tự mã hóa mọi HTTP headers/body/cookies. Ứng dụng vẫn cần **HTTPS/TLS**, session management, CSRF protection và business authorization.

## 10. Service Principal Name (SPN) gắn keytab với hostname

Ví dụ service principal:

~~~text
HTTP/portal.example.org@EXAMPLE.ORG
~~~

Thành phần:
- `HTTP` là service class.
- `portal.example.org` là hostname trình duyệt dùng cho dịch vụ.
- `EXAMPLE.ORG` là Kerberos realm.

Browser có thể xin ticket cho SPN dựa trên URL/DNS/SSPI chính sách. Keytab ở web server cần có principal/key tương ứng với ticket. Nếu browser dùng `portal.example.org` nhưng keytab chỉ có `HTTP/pod-001.internal`, GSS validation thường fail.

### 10.1. AD và SPN mapping

Trong Microsoft Active Directory, SPN được gắn với service/computer account. KDC mã hóa ticket cho key của principal/account liên quan. Nếu SPN duplicated hoặc gắn nhầm account, ticket có thể được mã hóa bằng key không khớp keytab hiện có.

**Không sửa bằng reset user password.** Cần kiểm SPN owner, keytab account, FQDN, canonicalization và KDC logs qua admin có quyền.

### 10.2. Load balancer, reverse proxy và Kubernetes

Nếu nhiều Spring nodes phục vụ cùng public hostname:
- Browser vẫn xin ticket cho public HTTP SPN.
- Các acceptor nodes phải có key phù hợp hoặc proxy xử lý Negotiate trước backend theo một kiến trúc đã được xác định.
- Không tự sử dụng từng pod hostname làm SPN nếu browser không truy cập host đó.
- Secrets/kvno/enctype phải rollout đồng bộ giữa replicas.
- TLS termination ở proxy **khác** service Kerberos keytab; tránh tin untrusted `X-Remote-User` từ client.

## 11. kvno và enctype trong keytab

### 11.1. kvno là gì?

**Key Version Number** giúp phân biệt các phiên bản long-term key của một service principal. Ví dụ:

| Entry | Principal | kvno | enctype |
|---|---|---:|---|
| 1 | HTTP/portal.example.org@EXAMPLE.ORG | 4 | aes256-cts-hmac-sha1-96 |
| 2 | HTTP/portal.example.org@EXAMPLE.ORG | 4 | aes128-cts-hmac-sha1-96 |
| 3 | HTTP/portal.example.org@EXAMPLE.ORG | 5 | aes256-cts-hmac-sha1-96 |

Đây là bảng **minh họa**, không chứa secret key bytes. Việc nhiều kvnos cùng tồn tại có thể hữu ích trong rotation nếu realm/service platform hỗ trợ.

### 11.2. Khi keytab đã cũ

Giả sử KDC phát ticket với kvno 5, nhưng server chỉ có keytab kvno 4. Server không có đúng long-term key để giải ticket. Người dùng vẫn có password đúng và TGT hợp lệ nhưng HTTP service trả 401/unauthorized.

Nên so:
- Principal chính xác.
- kvno.
- enctypes KDC/client/server support.
- Key material có đúng account/realm không.
- Time/clock skew.
- Các nodes có đang dùng versions đồng bộ không.

Không bật lại DES/RC4 yếu một cách tùy tiện để “làm ticket chạy”; phải bám security policy và compatibility plan.

### 11.3. Keytab có tự hết hạn như Service Ticket không?

Không. Keytab là file long-term keys, thường không có expiration giống `Ticket.endtime`. Cách nói “keytab expired” thường ám chỉ key đã rotate, kvno không còn đúng, account disabled hoặc mismatch về enctype/SPN. Hãy chẩn đoán nguyên nhân thật.

## 12. Các lệnh thực hành với MIT Kerberos

Chạy trên **môi trường đã được cấp quyền** và không dán ticket/keytab contents công khai.

### 12.1. Xem credential cache người dùng

~~~bash
klist
~~~

Có thể thấy client principal và TGT `krbtgt/EXAMPLE.ORG@EXAMPLE.ORG`, cùng những ST đã xin như `HTTP/portal.example.org@EXAMPLE.ORG`. Không nhầm với keytab.

### 12.2. Lấy TGT của user trong môi trường test

~~~bash
kinit alice@EXAMPLE.ORG
klist
~~~

`kinit` yêu cầu phương thức initial authentication theo policy; có thể prompt password. Đây là phía **initiator**. Không dùng user password này để cấu hình acceptor web Spring.

### 12.3. Xin ticket cho service cụ thể

~~~bash
kvno HTTP/portal.example.org@EXAMPLE.ORG
~~~

Lệnh thường yêu cầu TGT còn hiệu lực và liên lạc KDC, sau đó hiển thị kvno của ticket được cấp. Không có stdout cố định cho server thực; giá trị phụ thuộc KDC.

### 12.4. Liệt kê metadata keytab

~~~bash
klist -kte /run/secrets/portal-http.keytab
~~~

Kết quả liệt kê entries principal/kvno/timestamps/enctypes theo MIT Kerberos version. Không xuất secret bytes, nhưng metadata realm/host vẫn là thông tin hạ tầng nội bộ.

### 12.5. Dùng keytab để xin TGT (chỉ khi thật sự cần)

~~~bash
kinit -k -t /run/secrets/portal-http.keytab HTTP/portal.example.org@EXAMPLE.ORG
~~~

Điều này chứng minh keytab **có thể đóng vai trò credential cho principal**, không chỉ là file dùng ở acceptor. Nó không bắt buộc cho SPNEGO HTTP acceptor thuần; không chạy trên production service ngoài quy trình được phê duyệt.

### 12.6. Hủy ticket cache user

~~~bash
kdestroy
~~~

Lệnh xóa credentials cache trong phạm vi cấu hình. Nó **không reset user password, không xóa keytab server, không tự logout mọi HttpSession Spring trên hệ thống**.

### 12.7. Tạo hoặc rotate keytab cần quyền admin KDC

Trong MIT Kerberos, thao tác quản trị như `kadmin ktadd` có thể extract keys vào keytab. **Nhiều cấu hình ktadd mặc định randomize service keys**, ảnh hưởng kvno và mọi server đang dùng keytab cũ. Cần change control; không chạy ví dụ nguy hiểm trực tiếp trên realm production. Với AD, các công cụ như `ktpass` cũng có thể thay đổi tài khoản/service key nếu dùng không đúng tham số.

## 13. Java 17 JAAS: service acceptor dùng keytab

Java 17 có `com.sun.security.auth.module.Krb5LoginModule`.

Các options hay dùng với pure acceptor:
- `useKeyTab=true`: lấy keys từ keytab.
- `keyTab="/run/secrets/portal-http.keytab"`: đường file secret.
- `storeKey=true`: giữ keytab/key trong JAAS Subject private credentials.
- `principal="HTTP/portal.example.org@EXAMPLE.ORG"`: principal mong đợi.
- `isInitiator=false`: nhận GSS contexts, không tự thực hiện AS exchange lấy TGT cho client.
- `doNotPrompt=true`: không mở fallback hỏi password.
- `useTicketCache=false` khi pure acceptor không dùng client ticket cache.

Ví dụ **JAAS config fragment**:

~~~text
KerberosAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/portal-http.keytab"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    principal="HTTP/portal.example.org@EXAMPLE.ORG";
};
~~~

Đây là cú pháp file JAAS để một LoginContext dùng entry tên `KerberosAcceptor`. Khi sử dụng `SunJaasKerberosTicketValidator` của Spring Security Kerberos, thư viện có thể cấu hình JAAS nội bộ; không mặc định một file này được validator tự đọc nếu chưa wiring tích hợp đúng.

### 13.1. JVM krb5 config

~~~bash
java -Djava.security.krb5.conf=/etc/krb5.conf -jar portal.jar
~~~

Đây là command minh họa, cần có JAR thật, KDC/DNS/realm config và secrets mount. Không coi việc set system property là đủ để bật Spring Security Kerberos.

## 14. Spring Security Kerberos/SPNEGO dùng những class nào?

| Class | Vai trò |
|---|---|
| `SpnegoEntryPoint` | Khi cần authentication, trả HTTP 401/Negotiate challenge |
| `SpnegoAuthenticationProcessingFilter` | Đọc Authorization: Negotiate và chuyển token cho AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Validate service ticket/SPNEGO token, load UserDetails |
| `SunJaasKerberosTicketValidator` | Ticket validator dựa JAAS/GSS với service principal/keytab |
| `UserDetailsService` | Từ verified Kerberos principal tìm account, quyền ứng dụng |
| `GrantedAuthority` | Quyền ứng dụng đã map, không phải được keytab cấp sẵn |
| `SecurityContext` | Authentication session của Spring sau validation |
| `SecurityFilterChain` | Các filters, entrypoint và authorization rules |

**Nguyên tắc:** Spring nhận verified Kerberos username từ provider. KDC/service ticket **không tự quyết định ROLE_ADMIN** hay quyền đọc thông tin nhân sự. Ứng dụng phải ánh xạ quyền theo directory/DB/tenant policy.

## 15. Mẫu tích hợp Java Spring Security SPNEGO

Ví dụ sau là **configuration class** cho Spring Security Servlet và Spring Security Kerberos release có API tương ứng, có syntax Java hợp lệ nhưng **không thể chạy bằng javac trần** vì cần Spring dependencies, KDC, SPN, keytab thật và web app.

Tệp `src/main/java/com/example/security/SpnegoSecurityConfig.java`:

~~~java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class SpnegoSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator() {
        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.example.org@EXAMPLE.ORG");
        validator.setKeyTabLocation(
                new FileSystemResource("/run/secrets/portal-http.keytab"));
        return validator;
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Demo: production cần directory/database và tenant policy.
        return username -> {
            if (!"alice@EXAMPLE.ORG".equals(username)) {
                throw new UsernameNotFoundException(
                        "Principal not provisioned");
            }
            return new User(
                    username,
                    "{noop}unused-for-spnego",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));
        };
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        AuthenticationManager manager = new ProviderManager(provider);

        // Local instance chỉ nằm trong Spring Security filter chain;
        // tránh vô tình auto-register lần hai như Servlet Filter bean.
        var spnegoFilter = new SpnegoAuthenticationProcessingFilter();
        spnegoFilter.setAuthenticationManager(manager);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationManager(manager)
            .addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

### 15.1. Giải thích

- SPN là **HTTP/public-hostname**, không phải user principal.
- `SunJaasKerberosTicketValidator` nhận đường keytab; bí mật nằm ở volume/secret manager, **không nằm trong source**.
- `SpnegoAuthenticationProcessingFilter` đọc token; `KerberosServiceAuthenticationProvider` thực hiện validation và trả authenticated principal.
- `UserDetailsService` demo chỉ provisioned một principal `alice@EXAMPLE.ORG`, không tự cấp ROLE_READER cho mọi user có Kerberos ticket. Trong production dùng DB/LDAP theo business policy.
- Password literal trên `UserDetails` là placeholder cho cấu trúc UserDetails; **không được dùng để xác minh SPNEGO**, và không có form login ở filter chain ví dụ.
- Chỉ đăng ký filter vào **SecurityFilterChain**, tránh định nghĩa một `@Bean Filter` rồi vô tình để Spring Boot tự đăng ký nó ở servlet container hai lần.
- Bắt buộc test filter order, Authentication persistence, session fixation, CSRF và browser/realm compatibility theo Spring Security/Spring Security Kerberos version.
- Mã là **integration sample**, không phải một ứng dụng Spring Boot runnable độc lập vì thiếu route/@SpringBootApplication, dependency management và KDC.

### 15.2. Maven dependencies fragment

Đặt bên trong `<dependencies>` của POM Spring Boot đã có BOM/parent và tương thích các phiên bản Kerberos module:

~~~xml
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
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
  </dependency>
</dependencies>
~~~

Không giả định có Spring Boot starter tự cấu hình Kerberos/keytab chỉ bằng các dependencies trên. Kiểm phiên bản module, Java/Jakarta Servlet, Spring Security core và hướng dẫn release trước triển khai.

## 16. Java 17 độc lập: minh họa ticket và keytab không hoán đổi

Chương trình dưới đây **biên dịch/chạy bằng Java 17+ và không dùng secret thật**. Nó chỉ mô phỏng kiểm metadata (SPN và kvno), **không thực hiện Kerberos cryptography**.

Tệp `CredentialKindsDemo.java`:

~~~java
public class CredentialKindsDemo {

    enum Kind {
        USER_PASSWORD,
        TGT,
        SERVICE_TICKET,
        SERVICE_KEYTAB
    }

    record Ticket(String servicePrincipal, int kvno, boolean tgt) {
    }

    record KeytabEntry(String servicePrincipal, int kvno) {
    }

    static String purpose(Kind kind) {
        return switch (kind) {
            case USER_PASSWORD -> "INITIAL_USER_AUTH";
            case TGT -> "OBTAIN_SERVICE_TICKETS";
            case SERVICE_TICKET -> "ACCESS_ONE_SERVICE";
            case SERVICE_KEYTAB -> "VERIFY_FOR_SERVICE_PRINCIPAL";
        };
    }

    static boolean metadataMatch(Ticket t, KeytabEntry k) {
        return !t.tgt()
                && t.servicePrincipal().equals(k.servicePrincipal())
                && t.kvno() == k.kvno();
    }

    public static void main(String[] args) {
        for (Kind k : Kind.values()) {
            System.out.println(k + "=" + purpose(k));
        }

        var target = "HTTP/portal.example.org@EXAMPLE.ORG";
        var webTicket = new Ticket(target, 5, false);
        var tgt = new Ticket("krbtgt/EXAMPLE.ORG@EXAMPLE.ORG", 7, true);
        var currentKey = new KeytabEntry(target, 5);
        var oldKey = new KeytabEntry(target, 4);

        System.out.println("current=" +
                metadataMatch(webTicket, currentKey));
        System.out.println("stale=" +
                metadataMatch(webTicket, oldKey));
        System.out.println("tgtAsWeb=" +
                metadataMatch(tgt, currentKey));
    }
}
~~~

Lệnh:

~~~bash
javac CredentialKindsDemo.java
java CredentialKindsDemo
~~~

**Stdout chính xác:**

~~~text
USER_PASSWORD=INITIAL_USER_AUTH
TGT=OBTAIN_SERVICE_TICKETS
SERVICE_TICKET=ACCESS_ONE_SERVICE
SERVICE_KEYTAB=VERIFY_FOR_SERVICE_PRINCIPAL
current=true
stale=false
tgtAsWeb=false
~~~

**Giải thích:**
- USER_PASSWORD đại diện bước initial authentication của người dùng, không lưu password string.
- TGT chỉ dùng trong ticket-granting flow, không phải service ticket cho web.
- Service ticket khớp principal/kvno hiện tại trong mô phỏng; stale kvno không khớp.
- Real Kerberos verification **phải kiểm** encrypted part integrity, authenticator/session key, replay cache, clock skew, realm/policy, enctype và SPNEGO mechanism.
- `metadataMatch` chỉ là **bài tập về metadata**, tuyệt đối không dùng làm AuthenticationProvider production.
- Một keytab có thể có nhiều kvnos/enctypes nên ví dụ một entry không đại diện mọi production configuration.

## 17. Keytab rotation, kvno và triển khai nhiều node

### 17.1. Vì sao rotation làm 401?

KDC phát ST được mã hóa bằng service long-term key mới kvno 6, server vẫn chạy keytab kvno 5. Service không có key phù hợp để xử lý ticket. User password vẫn đúng, TGT vẫn hợp lệ, nhưng browser nhận 401 khi app verify.

Chiều ngược lại: server chuyển quá sớm sang chỉ key mới khi browser đang giữ ST kvno cũ cũng có thể gây lỗi tùy platform/ticket cache và overlap policy.

### 17.2. Quy trình rotation an toàn

1. Xác định SPN, owner service account, all hosts/pods/reverse proxies accept Kerberos.
2. Ghi nhận enctypes, kvno cũ, keytab file locations và ticket lifetime.
3. Thống nhất CAS/AD/MIT KDC (ở đây là KDC Kerberos, **không phải CAS native protocol**) key rotation policy.
4. Tạo keytab mới qua quy trình quản trị được phê duyệt; kiểm account/SPN mapping.
5. Nếu platform hỗ trợ, giữ key overlap đúng thời gian tickets cũ còn sống.
6. Deploy secrets qua secret manager/volume chỉ cho đúng service UID.
7. Kiểm behavior JVM/GSS acceptor reload keytab; có thể cần restart/reinitialize.
8. Test từng node qua public hostname và ticket có kvno/enctype đang dùng.
9. Retire keys cũ theo TTL/policy và bảo đảm application continuity.
10. Nếu keytab bị lộ, có incident response, revoke/rotate service keys, đánh giá ticket/key exposure.

### 17.3. Không chạy ktadd tùy tiện

Một thao tác `kadmin ktadd` có thể **randomize service long-term key**, tăng kvno và khiến keytabs đang dùng ở các server khác không còn hợp lệ. Tùy môi trường có lựa chọn giữ key, nhưng việc chọn option/role cần admin phê duyệt. Không dùng các lệnh quản trị này như “cách lấy keytab để thử” trên production realm.

## 18. Những nhầm lẫn trong triển khai SPNEGO

### 18.1. Đăng nhập domain OK nhưng portal 401

Có thể browser xin ST đúng nhưng web service keytab sai SPN/kvno/enctype. **Không sửa bằng reset password alice.** Kiểm keytab, SPN mapping, DNS, JVM account permissions.

### 18.2. Keytab OK nhưng browser không gửi token

Browser có thể không có TGT, Integrated Windows Authentication policy không cho Negotiate host, proxy chặn header hoặc KDC không truy cập được. Kiểm `klist`, browser auth zone, SPN, 401 challenge và network.

### 18.3. 401 xong là 403

Kerberos validation có thể thành công nhưng `UserDetailsService` không có local user/role hoặc quyền business từ chối. Xác thực principal và authorization là hai bước khác nhau.

### 18.4. TLS certificate mới không sửa được lỗi keytab

Certificate HTTPS phục vụ TLS, service keytab chứa Kerberos long-term keys. Hai loại secret **khác nhau**. HTTPS hoạt động tốt chưa chứng minh SPNEGO ticket acceptance tốt.

### 18.5. Local logout rồi lại đăng nhập ngay

Spring `/logout` có thể xóa HttpSession, nhưng TGT trên workstation vẫn còn. Browser có thể lấy ST và Negotiate lại ngay. Đây là thiết kế SSO, không mặc nhiên là lỗi logout. Nếu cần logout mọi nơi, xây quy trình credential/session lifecycle riêng; local logout không xóa Kerberos OS ticket cache.

### 18.6. SPNEGO không có nghĩa chắc chắn Kerberos

Windows HTTP Negotiate có thể fallback NTLM. Nếu app cần chỉ Kerberos, kiểm mechanism đã được accept và tắt fallback theo policy; đừng chỉ kiểm header prefix.

### 18.7. Service keytab dùng để authenticate outgoing requests?

Một portal muốn gọi backend thay user có thể cần Kerberos delegation/constrained delegation hoặc service principal riêng. **Không copy incoming Negotiate token tới backend**: ticket dành cho portal, không dành cho backend SPN. Không tự lấy user password hoặc TGT từ incoming AP-REQ.

## 19. Troubleshooting theo triệu chứng

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm |
|---|---|---|
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC không tìm SPN | Kiểm SPN, FQDN, realm mapping |
| `KRB_AP_ERR_MODIFIED` | Keytab/account key không đúng, duplicate SPN | Kiểm SPN owner, kvno, enctypes |
| `KRB_AP_ERR_SKEW` | Clock skew giữa client/server/KDC | Đồng bộ NTP và realm clock policy |
| `GSSException: No valid credentials` | Keytab file không đọc được, JAAS principal sai | Kiểm path, owner/ACL, acceptor config |
| 401 không có Negotiate header | Filter/entrypoint chưa chạy | Kiểm SecurityFilterChain và 401 challenge |
| Browser không gửi Authorization: Negotiate | Không TGT/policy/chặn browser | Kiểm OS credentials, browser auth config |
| Ticket request fail dù user có TGT | Sai SPN/realm/KDC routing | `kvno HTTP/...`, DNS/KDC |
| Accept token lỗi sau rotation | Keytab stale/missing kvno/enctype | `klist -kte`, deploy timing |
| Chỉ một node lỗi | Node keytab cũ hoặc missing secret mount | Kiểm từng node |
| Authentication pass nhưng 403 | Thiếu UserDetails/role hoặc resource policy | Kiểm local account/authorities |
| Người dùng đổi password nhưng vẫn SSO | Existing TGT/ST chưa hết hạn | Ticket/session lifecycle policy |
| Header Negotiate thực chất NTLM | SPNEGO mechanism fallback | Kiểm security mechanism policy |
| SSL OK nhưng Kerberos fail | TLS cert khác Kerberos service key | Kiểm đúng keytab principal |
| Local Spring logout xong login lại | TGT user còn trong OS cache | Giải thích SSO/re-auth |
| Raw Authorization token xuất hiện log | Proxy hoặc application ghi header | Xóa/mask logs và xử lý incident |
| Service khởi động nhưng validator fail | Realm config/time/DNS/file quyền sai | JAAS/GSS/KDC diagnostics |

**Debug theo tầng:** user initial auth → TGT cache → TGS-REQ cho HTTP SPN → browser Negotiate → service keytab → GSS acceptor validation → Spring Authentication → UserDetails/authorization → business resource.

Không tự tắt time/replay checks hoặc chấp nhận unsigned/unvalidated token để làm login “chạy được”.

## 20. Bảo vệ keytab, ticket cache và user password

### 20.1. User password/long-term key

- Không thu, lưu hoặc log user password trong Kerberos SPNEGO HTTP acceptor.
- Dùng domain/password/PKINIT/MFA policies và account lifecycle.
- Khi password đổi, đánh giá existing TGT/ST còn sống.
- Không nghĩ user password có thể thay keytab.

### 20.2. Ticket cache

- Bảo vệ OS logon sessions và credential cache.
- Không gửi tickets/session keys qua logs/chat/debug dumps.
- Dùng ticket lifetime, replay defenses, constrained delegation theo policy.
- `kdestroy` chỉ hủy cache cục bộ, không tự logout mọi Spring sessions.

### 20.3. Service keytab

- Mount keytab từ secret storage, file ACL chỉ cho service UID.
- Không đặt trong source repo, public container image, artifact hay docs.
- Không chia một keytab chứa nhiều service principals ngoài nhu cầu.
- Rotate keys với change control/kvno overlap/test/restart plan.
- Không dùng domain administrator account làm web service principal.
- Nếu lộ keytab: xử lý như service long-term credential compromise.
- Không log raw keys hoặc nhầm keytab với certificate TLS.

### 20.4. HTTP application security

- Dùng HTTPS/TLS dù có Kerberos.
- Không bỏ CSRF protection cho POST chỉ vì đã SPNEGO.
- Kiểm Spring session fixation/logout/session persistence.
- Realm/tenant identity mapping phải ngăn user từ realm khác chiếm account trùng tên.
- Quyền business cấp theo verified user + UserDetails + resource scope, không theo keytab.
- GSS replay/clock checks phải còn hoạt động.

## 21. Kiểm thử tích hợp với KDC và Spring

### 21.1. Positive tests

| Test | Điều kiện | Kỳ vọng |
|---|---|---|
| P1 | Client có TGT hợp lệ | Có thể xin ST cho SPN được phép |
| P2 | ST phù hợp SPN, service keytab đúng | GSS accept thành công |
| P3 | Authenticator/time/replay hợp lệ | Trả verified principal |
| P4 | Principal có account active | Spring Authentication có authorities đúng |
| P5 | Resource authorization allow | HTTP 200 cho user hợp lệ |
| P6 | Public hostname qua load balancer | ST của public HTTP SPN được validate mọi node |
| P7 | Keytab mới phù hợp kvno/enctype | Service vẫn nhận valid tickets |
| P8 | Kerberos thành công nhưng business deny | 403 đúng policy |
| P9 | TGT còn sau local logout | Browser có thể Negotiate lại theo SSO policy |
| P10 | Production TLS bật | Dữ liệu HTTP vẫn được bảo vệ độc lập |

### 21.2. Negative tests

| Test | Lỗi | Kỳ vọng |
|---|---|---|
| N1 | Ticket cho SPN khác | Reject |
| N2 | Keytab thiếu key/service principal | Reject |
| N3 | Keytab kvno/enctype không khớp | Reject |
| N4 | AP-REQ bị sửa | Reject |
| N5 | Replay Authenticator | Reject theo Kerberos replay policy |
| N6 | Client/server lệch clock | Reject, sửa NTP |
| N7 | Principal thuộc realm/tenant không được phép | Không cấp local roles |
| N8 | UserDetailsService không provisioned user | Không login business |
| N9 | SPNEGO fallback NTLM ngoài policy | Fail policy |
| N10 | Keytab đọc được bởi container khác | Security audit fail |
| N11 | ST/Negotiate token xuất hiện log | Privacy/security fail |
| N12 | Cookie/session logout mismatch | Kiểm local SSO behavior |
| N13 | Keytab mới chỉ trên một node | Regression phát hiện theo node |
| N14 | User password reset, old tickets còn | Đánh giá revocation riêng |
| N15 | Copy incoming Negotiate sang backend SPN khác | Reject, không bypass audience |
| N16 | HTTP POST thiếu CSRF token | Spring bảo vệ theo policy |
| N17 | TLS cert valid nhưng SPN sai | Kerberos vẫn reject |
| N18 | Keytab file bị lộ | Rotate/incident response, không dùng file cũ |

Unit tests có thể mock Authentication để kiểm `@PreAuthorize`, nhưng **không thay thế integration tests dùng KDC/browser/real signed Kerberos tickets**. Ví dụ Java17 ở mục 16 chỉ minh họa metadata, không test mật mã.

## 22. Checklist go-live

- [ ] Đã phân biệt user password, TGT, Service Ticket, session key và service keytab.
- [ ] Spring SPNEGO acceptor không đòi user password.
- [ ] Browser có Kerberos credentials và Negotiate đúng HTTP SPN.
- [ ] Service keytab chứa đúng principal, kvno, enctype và được secret-store bảo vệ.
- [ ] KDC/realm/DNS/clock/NTP được kiểm.
- [ ] SPN public hostname và proxy/ingress routing nhất quán.
- [ ] Keytab không nằm trong JAR, Git, public image hay logs.
- [ ] Key rotation được quản lý trên mọi replicas, có overlap nếu thích hợp.
- [ ] Spring Security filter/provider/validator đúng phiên bản và chỉ đăng ký một lần.
- [ ] Spring UserDetailsService dùng account/role/tenant policy chứ không gán admin cho mọi principal.
- [ ] HTTPS/TLS và CSRF còn hiệu lực.
- [ ] Không chấp nhận Negotiate/NTLM fallback nếu security policy không cho.
- [ ] Không coi local logout xóa OS TGT hay keytab.
- [ ] Có tests cho wrong SPN, stale keytab, replay, clock skew, missing TGT, wrong realm.
- [ ] Có incident response cho keytab leak và ticket cache compromise.
- [ ] Không dùng mã demo metadataMatch làm Kerberos validator thật.

## 23. Câu hỏi ôn tập

1. **Password dùng để làm gì?** Đóng vai trò initial user authentication/long-term key source trong password-based Kerberos.
2. **Browser Kerberos có gửi password tới Spring không?** Không.
3. **TGT là gì?** Ticket để xin service tickets từ TGS.
4. **ST là gì?** Ticket do KDC cấp cho một service principal cụ thể.
5. **Ticket được bảo vệ bằng key nào?** Encrypted ticket part thường dùng long-term key của target service.
6. **Service keytab chứa gì?** Service principal entries với long-term keys, kvno và enctype.
7. **Keytab chứa password plaintext không?** Không, nhưng phải bảo vệ như secret cấp cao.
8. **Session key có nằm cố định trong keytab không?** Không; session key theo ticket/context.
9. **Authenticator có vai trò gì?** Chứng minh client nắm session key và hỗ trợ replay/freshness checks.
10. **HTTP SPNEGO gửi loại ticket nào?** Service ticket cho HTTP SPN, không phải raw TGT.
11. **SPN thường có dạng nào?** `HTTP/portal.example.org@EXAMPLE.ORG`.
12. **kvno quan trọng khi nào?** Service key rotation và accept encrypted ticket part.
13. **Keytab stale biểu hiện thế nào?** 401/GSS failure do không có key đúng kvno/enctype.
14. **klist khác klist -kte?** Một bên xem credential cache, một bên xem keytab metadata.
15. **kinit -k có bắt buộc cho web acceptor?** Không, chỉ khi service cần làm initiator/kiểm cụ thể.
16. **Đổi user password có sửa lỗi keytab không?** Không.
17. **Kerberos pass nhưng Spring 403?** Authorization/role account mapping có thể từ chối.
18. **HTTPS certificate có thay keytab không?** Không.
19. **Header Negotiate chắc chắn là Kerberos?** Không, có thể negotiated mechanism khác.
20. **Local logout có làm OS TGT hết hạn?** Không mặc định.
21. **Dùng incoming token để gọi backend khác được không?** Không trực tiếp, target SPN khác; delegation cần cơ chế riêng.
22. **Khi keytab bị lộ phải làm gì?** Incident response, rotate service keys, đánh giá tickets/sessions có thể bị ảnh hưởng.
23. **Khi user có TGT nhưng không vào web được nên kiểm gì?** SPN, service ticket, keytab/kvno/enctype, GSS filter và roles.

## 24. Tài liệu kỹ thuật chính thức

- **RFC 4120 – The Kerberos Network Authentication Service (V5):** https://www.rfc-editor.org/rfc/rfc4120
- **RFC 4559 – SPNEGO-based Kerberos and NTLM HTTP Authentication:** https://www.rfc-editor.org/rfc/rfc4559
- **RFC 4178 – SPNEGO:** https://www.rfc-editor.org/rfc/rfc4178
- **RFC 4121 – Kerberos GSS-API mechanism:** https://www.rfc-editor.org/rfc/rfc4121
- **MIT Kerberos – Application servers and keytabs:** https://web.mit.edu/Kerberos/www/krb5-current/doc/krb_admins/appl_servers.html
- **MIT Kerberos – kinit:** https://web.mit.edu/Kerberos/www/krb5-current/doc/user/user_commands/kinit.html
- **MIT Kerberos – klist:** https://web.mit.edu/Kerberos/www/krb5-current/doc/user/user_commands/klist.html
- **MIT Kerberos – kvno:** https://web.mit.edu/Kerberos/www/krb5-current/doc/user/user_commands/kvno.html
- **MIT Kerberos – kadmin, ktadd:** https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/admin_commands/kadmin_local.html
- **Oracle Java SE 17 – Krb5LoginModule:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- **Spring Security – Spring Security Kerberos (Servlet):** https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- **Spring Security – KerberosServiceAuthenticationProvider JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- **Spring Security – SpnegoAuthenticationProcessingFilter JavaDoc:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html

**Tổng kết:** **Mật khẩu/initial user credential** dùng để xác thực user với KDC và lấy TGT; **Kerberos ticket** được KDC cấp, TGT để xin ticket, Service Ticket + Authenticator để chứng minh client tới một SPN cụ thể; **service keytab** chứa long-term keys giúp web acceptor xác minh ticket đã cấp cho mình. Ba loại khác nhau về owner, vòng đời, phạm vi và hậu quả rò rỉ. Spring Security chỉ cấp quyền sau khi ticket được GSS xác minh và UserDetails/authorization của ứng dụng chấp nhận người dùng; phải tiếp tục bảo vệ TLS, CSRF, sessions, keytab và ticket caches.
