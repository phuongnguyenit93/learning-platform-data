# Ticket Granting Ticket và service ticket trong Kerberos: từ KDC đến Spring Security SPNEGO

## 1. Mục tiêu và bối cảnh

**Kerberos V5** là một giao thức xác thực mạng dựa trên **vé (ticket)** và khóa mật mã, thường được sử dụng với Microsoft Active Directory, MIT Kerberos, môi trường doanh nghiệp và các ứng dụng có hỗ trợ **SPNEGO**. Kerberos cho phép người dùng đã có phiên đăng nhập trong domain truy cập dịch vụ khác mà không phải gửi mật khẩu tới từng ứng dụng.

Trong một ứng dụng Spring Boot dùng **Spring Security Kerberos**, người dùng có thể mở một trang web nội bộ. Trình duyệt trao đổi HTTP `Negotiate` với ứng dụng, sử dụng một **service ticket dành riêng cho service principal của website**. Server xác minh token bằng Kerberos/JGSS và keytab của chính service; ứng dụng sau đó ánh xạ Kerberos principal thành tài khoản và quyền nghiệp vụ.

Hai loại vé quan trọng nhất:

1. **Ticket Granting Ticket (TGT)**: vé mà **Authentication Service (AS)** trong **Key Distribution Center (KDC)** cấp cho client để chứng minh với **Ticket Granting Service (TGS)** rằng client được phép xin các vé khác.
2. **Service ticket**: vé mà **TGS** cấp cho **một service principal cụ thể**, ví dụ `HTTP/portal.example.test@EXAMPLE.TEST`. Client sử dụng vé đó cùng **authenticator** để xác thực với web server hoặc service đích.

Bài học thuộc nhóm **Kerberos và SPNEGO**, nhằm giúp người học:

- Nắm ba lần trao đổi chính **AS-REQ/AS-REP**, **TGS-REQ/TGS-REP** và **AP-REQ/AP-REP**.
- Phân biệt **TGT và service ticket** về nơi cấp, khóa mã hóa, phạm vi sử dụng, TTL, cache và rủi ro khi lộ.
- Hiểu `krbtgt/REALM@REALM` khác `HTTP/host@REALM` và vai trò của **Service Principal Name (SPN)**.
- Hiểu vì sao web app **không nhận TGT** mà nhận **SPNEGO/GSS-API token** chứa thông tin xác thực với **service ticket**.
- Hiểu **ticket có thể được dùng trong thời hạn** nhưng mỗi **authenticator** cần đủ mới và chống replay; không nhầm cơ chế một lần của một giao thức ticket khác.
- Biết cấu hình `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, **keytab** và local authorization.
- Biết dùng `kinit`, `klist`, `kvno` và `klist -k` để chẩn đoán mà không làm lộ khóa.
- Nhận diện lỗi SPN, principal, KVNO, encryption type, DNS/hostname, clock skew, 401/Negotiate, keytab và lỗi quyền nghiệp vụ.
- Có ví dụ **Java 17 chạy độc lập** minh họa trạng thái TGT/service ticket/replay, kèm ma trận negative tests và checklist triển khai.

**Điểm mấu chốt:** TGT là credential **đưa cho TGS**, service ticket là credential **dành cho service cụ thể**. **TGT không phải một vé mà ứng dụng Spring web được phép tự lấy từ browser hoặc giải mã bằng keytab HTTP.**

## 2. Bốn thành phần trong một lần đăng nhập Kerberos

~~~text
                +----------------------------------------+
                | Key Distribution Center (KDC)          |
                |                                        |
                | Authentication Service (AS)            |
                | Ticket Granting Service (TGS)           |
                +----------------------------------------+
                   ^                       ^
                   | AS-REQ/AS-REP         | TGS-REQ/TGS-REP
                   |                       |
                   +--------- Client -----+
                              |
                              | AP-REQ (service ticket +
                              |         authenticator)
                              v
                       Service / Acceptor
                         HTTP website
                         CIFS/SMB server
                         database service
~~~

| Thành phần | Trách nhiệm | Bí mật/credential chủ yếu |
| --- | --- | --- |
| **Client** | Người dùng hoặc tiến trình có Kerberos credentials; xin và dùng tickets | Credential cache chứa TGT, service tickets và session keys |
| **AS (Authentication Service)** | Xác thực client ban đầu; phát TGT theo chính sách KDC | Keys được KDC quản trị và khóa liên quan đến client |
| **TGS (Ticket Granting Service)** | Kiểm TGT và phát service ticket cho service được yêu cầu | Khóa của principal `krbtgt` và keys service đã đăng ký |
| **Application Server / Acceptor** | Xác minh AP-REQ để nhận diện client, sau đó kiểm quyền local | Long-term service key, thường được provision qua **keytab** |
| **DNS / realm configuration** | Giúp client tìm KDC và chọn service principal đúng | Không phải nguồn chứng minh user identity |
| **Identity/authorization store** | LDAP/AD/local DB ánh xạ principal vào user, groups, roles | Chính sách nghiệp vụ và trạng thái tài khoản |

**AS và TGS là hai chức năng logic của KDC**, không nhất thiết là hai máy chủ vật lý. Trong Active Directory, domain controllers thường cung cấp Kerberos KDC. Một realm có thể có nhiều KDC để dự phòng.

### 2.1. Realm, principal và service principal

Ví dụ realm:

~~~text
EXAMPLE.TEST
~~~

Ví dụ principal của người dùng:

~~~text
alice@EXAMPLE.TEST
~~~

Ví dụ các service principals:

~~~text
krbtgt/EXAMPLE.TEST@EXAMPLE.TEST
HTTP/portal.example.test@EXAMPLE.TEST
cifs/files.example.test@EXAMPLE.TEST
~~~

Phân biệt:

- `krbtgt/EXAMPLE.TEST@EXAMPLE.TEST` nhận diện dịch vụ **cấp vé** của realm, có khóa mật mã chỉ KDC/TGS được quyền quản trị. **Không dùng khóa krbtgt làm keytab cho web app**.
- `HTTP/portal.example.test@EXAMPLE.TEST` là **SPN của dịch vụ web**. Khi browser truy cập hostname công khai này, GSS/Kerberos client cần lấy service ticket dành cho đúng SPN.
- `cifs/files.example.test@EXAMPLE.TEST` là service principal khác, không phải tên khác của website.
- Realm thường viết chữ hoa theo quy ước; tên host/canonicalization phụ thuộc cấu hình KDC và client. Không tự chuẩn hóa principal bằng quy tắc đơn giản trong business code.

**SPN không đồng nghĩa URL đầy đủ**. `https://portal.example.test/reports` là URL của ứng dụng, còn Kerberos thường nhắm principal dạng `HTTP/portal.example.test@EXAMPLE.TEST`. Path `/reports` không tự là một phần của SPN HTTP. Port, alias, DNS và tên thực tế được chọn chịu ảnh hưởng client/JGSS/KDC/AD policy.

## 3. TGT là gì?

**Ticket Granting Ticket** là một **Kerberos ticket dành cho Ticket-Granting Service**, thường biểu diễn bằng service principal:

~~~text
krbtgt/EXAMPLE.TEST@EXAMPLE.TEST
~~~

TGT được cấp sau **AS exchange**, thường khi người dùng đăng nhập domain/đạt cơ chế xác thực ban đầu hoặc khi client thực hiện `kinit`. Nó cho phép client liên hệ TGS để xin service tickets cho các dịch vụ khác **mà không liên tục gửi password hoặc thực hiện AS exchange mỗi lần**.

TGT chứa phần dữ liệu được KDC mã hóa bằng khóa dài hạn của **krbtgt service**, bao gồm thông tin cần thiết như client principal, thời gian, session key, flags và authorization data theo profile. Client có thể **lưu và trình TGT** cho TGS, nhưng **không cần và thông thường không thể giải mã phần vé được bảo vệ bằng khóa krbtgt**.

Client đồng thời nhận **client–TGS session key**, được chuyển đến client trong phần phản hồi AS được bảo vệ bằng khóa thích hợp từ cơ chế xác thực ban đầu. Client cần khóa này để tạo authenticator cho **TGS-REQ**.

### 3.1. AS exchange — có TGT ban đầu

~~~text
Client                            KDC / AS
   |                                |
   | KRB_AS_REQ                     |
   | client = alice@EXAMPLE.TEST    |
   | realm, flags, pre-auth info    |
   |------------------------------->|
   |                                | xác thực principal theo
   |                                | password-derived key,
   |                                | PKINIT/smartcard, v.v.
   |                                |
   |<-------------------------------|
   | KRB_AS_REP                     |
   |   ticket = TGT for krbtgt      |
   |   encrypted reply = K_c,tgs   |
   |   times, flags ...             |
   |                                |
Client lưu TGT + K_c,tgs trong credential cache
~~~

**Đừng hiểu AS-REP gửi password đến TGS.** Mật khẩu/long-term key được dùng trong bước xác thực ban đầu theo Kerberos pre-authentication mechanism, không phải một password plaintext truyền đến từng ứng dụng.

### 3.2. Các quyền thực sự TGT mang lại

TGT hợp lệ cho phép client **xin** service ticket qua TGS, nhưng không đảm bảo:

- KDC cấp vé cho mọi SPN tồn tại.
- Client được phép truy cập mọi resource bên trong từng service.
- Client được phép delegate credentials đến bất kỳ service trung gian.
- Client có quyền quản trị do đã sở hữu TGT.
- Một web app có thể dùng TGT như bearer token để mở session.

KDC vẫn áp chính sách realm, lifetime, ticket flags, principal status và các điều kiện ủy nhiệm. Application server vẫn phải thực thi **local authorization** sau khi nhận diện principal.

### 3.3. TGT không được gửi tới Spring HTTP service

Mẫu sai về nhận thức:

~~~text
Browser -> Spring: TGT -> web server decrypt TGT -> logged in
~~~

Mẫu đúng:

~~~text
Client -> TGS: TGT + authenticator -> xin service ticket HTTP/portal
Browser -> Spring: SPNEGO/GSS token chứa AP-REQ dùng service ticket HTTP/portal
Spring/JGSS -> keytab HTTP/portal -> xác minh ticket + authenticator
~~~

Web app có **service keytab**, không có **krbtgt key**. Nếu thấy cách triển khai yêu cầu web app nắm khóa krbtgt hoặc lấy TGT từ browser để “xác minh login”, cần đánh giá lại kiến trúc và quyền đặc biệt nguy hiểm đó.

## 4. Service ticket là gì?

**Service ticket** được cấp bởi **TGS** cho **một service principal cụ thể**, ví dụ:

~~~text
HTTP/portal.example.test@EXAMPLE.TEST
~~~

Nó chứa phần được mã hóa bằng **long-term key của service principal** mà KDC biết. Service nhận ticket có thể sử dụng key tương ứng, thường trong **keytab**, để giải mã/xác minh. Client cũng được TGS cung cấp **client–service session key**, giúp nó tạo **Authenticator** chứng minh mình nắm khóa phiên thích hợp.

Vì vậy service ticket có hai ràng buộc quan trọng:

1. **Ràng buộc người dùng**: bên yêu cầu là Kerberos client principal đã được TGS xác thực/ủy quyền phát vé.
2. **Ràng buộc đích**: vé được phát cho **một SPN**, không phải danh sách mọi web app, API hoặc cổng dịch vụ.

### 4.1. TGS exchange — từ TGT sang service ticket

~~~text
Client                                   KDC / TGS
  |                                         |
  | KRB_TGS_REQ                             |
  |  TGT for krbtgt                         |
  |  authenticator dùng K_c,tgs             |
  |  sname = HTTP/portal.example.test       |
  |---------------------------------------->|
  |                                         | giải mã TGT bằng
  |                                         | krbtgt key; kiểm
  |                                         | time, flags, KDC
  |                                         | policy, principal
  |                                         |
  |<----------------------------------------|
  | KRB_TGS_REP                             |
  |  service ticket được bảo vệ bằng K_svc   |
  |  encrypted reply cấp K_c,svc            |
  |                                         |
Client cache ticket HTTP/portal và K_c,svc
~~~

**K_c,tgs** và **K_c,svc** là hai session keys khác nhau:

- `K_c,tgs` phục vụ quan hệ client–TGS, liên quan đến TGT.
- `K_c,svc` phục vụ quan hệ client–service, liên quan đến service ticket.
- `K_svc` là **long-term key của service**, nằm ở KDC và service keytab; **không phải session key**.
- `K_krbtgt` là key của Ticket-Granting Service; **không nằm ở service keytab HTTP**.

Không viết code application tự tạo lại các khóa này từ email/user ID hoặc dùng một chuỗi `ticketId` làm secret. Kerberos/JGSS/JDK/OS library xử lý giao thức và mã hóa.

### 4.2. Một TGT có thể dùng để xin nhiều service tickets

Ví dụ Alice đã có TGT:

~~~text
TGT(alice -> krbtgt/EXAMPLE.TEST)
   |
   +-> TGS request "HTTP/portal.example.test" -> ticket cho Portal
   |
   +-> TGS request "cifs/files.example.test" -> ticket cho Files
   |
   +-> TGS request "HTTP/wiki.example.test" -> ticket cho Wiki
~~~

**Không phải mỗi lần xin ticket cho service lại nhập mật khẩu**. Client OS/credential cache có thể giữ TGT đến khi hết hạn hoặc không còn dùng được; service tickets cũng được cache theo SPN trong thời hạn của chúng.

Tuy nhiên một service ticket dành cho Files không được dùng để đăng nhập Portal, ngay cả khi cả hai cùng realm và cùng client principal.

## 5. So sánh TGT và service ticket

| Tiêu chí | Ticket Granting Ticket (TGT) | Service ticket |
| --- | --- | --- |
| Bên cấp | KDC **AS** trong AS exchange, hoặc TGS với trường hợp inter-realm TGT | KDC **TGS** |
| Bên nhận/đích | `krbtgt/REALM@REALM` hoặc `krbtgt/DEST@SRC` liên realm | Service principal như `HTTP/portal...@REALM` |
| Mục đích | Xin thêm service tickets qua TGS; phục vụ xác thực tiếp theo mà không dùng lại password | Xác thực client với **một application service** |
| Khóa bảo vệ ticket | Khóa của TGS/krbtgt principal | Long-term key của service principal |
| Khóa phiên client nhận | Client–TGS session key | Client–service session key |
| Client gửi đi đâu | Trong KRB_TGS_REQ đến TGS, kèm authenticator | Trong KRB_AP_REQ/GSS token đến đúng service |
| Ứng dụng Spring web thường thấy? | **Không** | **Có qua GSS/SPNEGO token** |
| Bên có thể giải mã ticket | TGS/KDC có key phù hợp | Service đích có keytab; một số profile đặc biệt có khác biệt |
| Thời hạn | Theo KDC policy; có thể renewable/forwardable | Theo TGS policy; có start/end time và flags |
| Cách dùng lại | Có thể xin nhiều service tickets khi còn hợp lệ | Có thể xuất hiện trong nhiều AP exchanges khi còn hợp lệ; **Authenticator mỗi lần phải mới** |
| Rủi ro khi lộ | Kẻ nắm đủ TGT và session key có thể xin nhiều tickets trong phạm vi ticket/policy | Kẻ nắm đủ service ticket và session key có thể cố giả mạo dùng tại **service đã cấp** |
| Cách vô hiệu hóa | Expiration, ticket/policy checks, key rotation và cơ chế quản trị tùy triển khai | Expiration, service account key rotation, local sessions và chính sách theo môi trường |
| Mối quan hệ với local roles | Không tự cấp ROLE_ADMIN | Sau service authentication cần UserDetails/local authorization |

### 5.1. “TGT sống lâu hơn” không phải định luật

TGT thường được cấu hình với lifetime phù hợp SSO session; service ticket có lifetime theo policy riêng. Không khẳng định **TGT luôn dài hơn service ticket** hay luôn đúng một con số giờ cụ thể. KDC có các giới hạn **endtime, renew-till, realm policy, principal policy và service policy**; kiểm bằng ticket thực.

### 5.2. “Service ticket dùng một lần” là phát biểu sai cho Kerberos V5

Một điểm rất dễ nhầm khi học federation:

- **Kerberos service ticket** có thể được client sử dụng trong nhiều AP exchanges khi còn hiệu lực, với **Authenticator mới** và các điều kiện service/GSS security context.
- **Authenticator đã gửi** phải được chống **replay**; service/GSS sử dụng timestamps/sequence và replay cache hoặc các cơ chế tương thích.
- Không coi `Authorization: Negotiate <token>` là “vé dùng một lần theo mọi nghĩa”; HTTP negotiation và GSS token/state có vòng đời riêng.
- Một số application wrappers/cache có policy ngắn hơn Kerberos ticket lifetime, nhưng không thay đổi định nghĩa ticket của RFC 4120.

Đây là lý do cần phân biệt **TGT**, **service ticket**, **authenticator**, **GSS security context** và **HttpSession**; chúng không cùng loại state.

## 6. AP exchange — service ticket kết hợp với Authenticator

Sau khi nhận service ticket, client bắt đầu **Application Service exchange**:

~~~text
Client / GSS initiator                    Service / GSS acceptor
       |                                           |
       | KRB_AP_REQ                                |
       |   service ticket for HTTP/portal          |
       |   Authenticator encrypted by K_c,svc      |
       |------------------------------------------>|
       |                                           | keytab K_svc
       |                                           | -> decrypt ticket
       |                                           | -> recover K_c,svc
       |                                           | -> verify Authenticator
       |                                           | -> time/replay/identity
       |                                           |
       |<------------------------------------------|
       | Optional KRB_AP_REP for mutual auth        |
       |                                           |
       v                                           v
Client hiểu service identity               Server nhận client principal
~~~

Một **service ticket tự nó chưa chứng minh người gửi biết session key**. RFC 4120 mô tả **Authenticator** được mã hóa bằng session key để chứng minh possession và giúp ngăn một attacker chỉ sao chép ticket công khai rồi phát lại.

### 6.1. Service ticket mang những gì?

Ở mức khái niệm:

~~~text
Ticket:
  realm = EXAMPLE.TEST
  sname = HTTP/portal.example.test
  enc-part:
    client = alice@EXAMPLE.TEST
    session-key = K_c,svc
    flags = initial/forwardable/... (tùy ticket)
    authtime, starttime, endtime, renew-till
    client addresses (nếu áp dụng)
    authorization-data (nếu có)
  kvno = service key version
  enctype = thuật toán mã hóa ticket
~~~

Đây là **hình dung đơn giản**, không phải ASN.1/DER ticket đầy đủ, không phải một token JSON có thể sửa. TGS bảo vệ `enc-part` bằng **service long-term key**. Client không thể tự đổi `sname`, expiry, username hoặc flags rồi yêu cầu web app tin vào chúng.

### 6.2. Authenticator mang những gì?

Ở mức khái niệm:

~~~text
Authenticator:
  client realm/name
  timestamp (ctime, cusec)
  optional subkey / sequence / checksum
  protected by K_c,svc
~~~

Các kiểm tra cần có:

1. Service ticket có thể giải mã bằng đúng service key/kvno/enctype.
2. Service ticket phát cho đúng service principal mà server được cấu hình chấp nhận.
3. Ticket đang trong khoảng thời gian hợp lệ, các flags/constraints tương thích.
4. Client identity trong authenticator phù hợp client được ticket xác nhận.
5. Authenticator có bằng chứng nắm đúng client–service session key.
6. Timestamp, clock skew và replay cache không cho chấp nhận cùng authenticator giả lập lần nữa.
7. Nếu yêu cầu mutual authentication, client kiểm phản hồi `AP-REP`/GSS context tương ứng.
8. Nếu dùng channel binding/extended protection, thông tin binding phải phù hợp cấu hình cả hai đầu.

**Không tự viết lại parser ASN.1 hay thuật toán Kerberos trong Spring controller.** Dùng JAAS/JGSS/Spring Security Kerberos và cấu hình KDC/service principal đúng.

### 6.3. Ticket key version number (KVNO)

**KVNO** chỉ phiên bản key dùng để mã hóa ticket. Khi service account đổi password/rotate key:

- KDC có thể phát ticket dùng **key mới**.
- Server vẫn giữ **keytab cũ** thì không giải mã được ticket mới.
- Service ticket cũ trong cache có thể còn dùng key cũ; nếu server đã xóa hết key cũ, requests cũ có thể fail.
- Một keytab có thể chứa nhiều entries khác **kvno/enctype** để hỗ trợ transition theo policy.

Vì vậy đừng sửa lỗi bằng cách tắt Kerberos hoặc “trust username từ header” nếu gặp GSS exception sau rotation. Cần điều phối **KDC key, service account, KVNO và keytab deployment**.

## 7. Kerberos credential cache và keytab khác nhau

| Kho | Nơi thường lưu | Chứa gì? | Vai trò |
| --- | --- | --- | --- |
| **Client credential cache** | OS logon session, MIT credential cache, Windows LSA | TGT, service tickets và session keys client | Để client/Browser xin và sử dụng tickets |
| **Server service keytab** | File/secret volume chỉ service đọc | Long-term keys của service principal, KVNO, enctype | Để GSS acceptor xác minh service ticket |
| **KDC principal database** | KDC/AD directory and key store | Long-term keys/principal policy | KDC phát/validate tickets và quản trị realm |
| **Spring HttpSession** | App server/session store | Local Authentication sau SPNEGO login theo cấu hình | Không phải TGT/ST cache gốc |
| **Replay cache/credential context** | Thư viện Kerberos/JGSS/OS | Thông tin để từ chối authenticator lặp | Khác session của Spring |

**Tuyệt đối không sao chép client credential cache hoặc user TGT sang web server chỉ để “giúp login”**. Bên acceptor thông thường chỉ cần **service keytab**, không cần user password/TGT. Keytab là một bí mật dài hạn: ai lấy được nó có thể giả danh service hoặc giải mã ticket phù hợp trong phạm vi khóa.

### 7.1. Không nhầm keytab với ticket

Keytab có thể được quan sát bằng:

~~~bash
klist -k -t -e /run/secrets/kerberos/http.keytab
~~~

Lệnh chỉ liệt kê principal, KVNO, timestamp và enctype (tùy bản MIT Kerberos), **không in raw keys**. Tránh `klist -K` trong log/CI vì `-K` có thể hiển thị **giá trị khóa mật mã**.

Một service keytab hợp lệ cho Portal có thể có entries:

~~~text
KVNO Principal
---- ------------------------------------------------
   4 HTTP/portal.example.test@EXAMPLE.TEST (aes256-cts-hmac-sha1-96)
   5 HTTP/portal.example.test@EXAMPLE.TEST (aes256-cts-hmac-sha1-96)
~~~

Đây là **output mô tả**, không trích từ một keytab thật. Enctype thực tế tùy môi trường/thuật toán được phép; đừng rập khuôn một loại bắt buộc.

### 7.2. Keytab là secret nên không commit

Các biện pháp:

- Provision từ KDC/AD theo quy trình có approval, service account riêng và audit.
- Mount vào container qua secret storage/volume read-only, giới hạn quyền filesystem và process identity.
- Không đặt file keytab trong `src/main/resources` hoặc artifact public; không gửi vào log, test report hay Git.
- Không dùng một service principal/keytab cho mọi ứng dụng nếu ranh giới trust/rotation cần tách.
- Đổi keytab/kvno theo kế hoạch, có testing trước/sau, tránh ứng dụng giữ key cũ trong memory quá lâu.
- Hạn chế quyền cấp delegation của service account, không bật unconstrained delegation ngoài ý muốn.
- Không cung cấp keytab cho untrusted reverse proxy/plugin chỉ vì cần đọc HTTP header.

## 8. Kerberos trên HTTP: SPNEGO và header Negotiate

**SPNEGO (Simple and Protected GSS-API Negotiation Mechanism)** cho phép client/server đàm phán cơ chế xác thực GSS-API. **HTTP Negotiate** theo RFC 4559 thường dùng SPNEGO để mang Kerberos authentication tokens qua HTTP headers.

Một cuộc trao đổi minh họa:

~~~http
GET /private HTTP/1.1
Host: portal.example.test

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Sau đó browser dùng OS Kerberos credentials, có thể xin service ticket từ TGS nếu chưa cache, rồi gửi:

~~~http
GET /private HTTP/1.1
Host: portal.example.test
Authorization: Negotiate <base64-GSS-token>
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate <optional-response-GSS-token>
~~~

**Đây là hình dạng message minh họa, không phải một trace HTTP hợp lệ để copy gửi trực tiếp.** `<base64-GSS-token>` không phải vé Kerberos dạng text thuần, không phải TGT, không phải username/password. Nó có thể chứa **SPNEGO NegTokenInit/NegTokenResp**, Kerberos AP-REQ, mech identifiers và thông tin security context theo profile.

### 8.1. Những việc browser thực hiện ngầm

1. Người dùng có phiên OS/domain Kerberos hoặc credential cache phù hợp.
2. Browser biết website được phép **Integrated Authentication/Negotiate** theo intranet allowlist/enterprise policy.
3. Browser/JGSS chọn service principal dựa vào URL và Kerberos config, ví dụ `HTTP/portal.example.test@EXAMPLE.TEST`.
4. Nếu chưa có service ticket trong cache, OS/GSS dùng **TGT** để xin ticket từ TGS.
5. Browser tạo GSS/SPNEGO token cho service.
6. Server nhận `Authorization: Negotiate` và xác minh với service keytab.
7. Browser/server có thể trao đổi thêm một round nếu GSS context cần.

**Không phải mọi HTTP request đều phải tới KDC.** Nếu TGT/service ticket/GSS context đã có trong cache, client có thể reuse thông tin phù hợp đến khi hết hạn. Một request không có header Negotiate đôi khi đã được nhận diện qua **HttpSession local** của web app.

### 8.2. SPNEGO có thể đàm phán NTLM — không giả định Kerberos

HTTP `Negotiate` trong một số môi trường Windows có thể thương lượng **Kerberos hoặc NTLM**. Nếu chính sách sản phẩm yêu cầu Kerberos:

- Giám sát **mech thực tế** và cấu hình client/server chỉ chấp nhận cơ chế được duyệt.
- Không coi có header `Negotiate` là bằng chứng rằng Kerberos AP-REQ đã được xác minh.
- Xác định hành vi khi browser không có TGT, SPN sai hoặc không có KDC kết nối.
- Nếu có fallback form/NTLM, phải có chính sách bảo mật riêng, không vô tình hạ authentication assurance.
- Không chuyển `WWW-Authenticate: Negotiate` thành “Basic Authentication” hoặc đọc credential trong query string.

### 8.3. HTTPS vẫn cần thiết

Kerberos/GSS-API cung cấp xác thực và có cơ chế bảo vệ thông điệp trong GSS khi được sử dụng đúng, nhưng **HTTP Negotiate alone không mã hóa toàn bộ HTTP URL, headers, cookies hay response body**. RFC 4559 lưu ý HTTP Negotiate **không tự bảo vệ toàn bộ HTTP payload**.

Dùng **HTTPS/TLS**, Secure/HttpOnly/SameSite cookies phù hợp, chống CSRF cho state-changing requests và tin cậy đúng proxy. Đừng bỏ TLS chỉ vì “ticket đã được mã hóa”.

## 9. Spring Security Kerberos: filter và provider

Khi ứng dụng Spring Boot là HTTP service phía sau Negotiate:

~~~text
Browser
  |
  | Authorization: Negotiate <GSS token>
  v
SpnegoAuthenticationProcessingFilter
  |
  | tạo KerberosServiceRequestToken
  v
AuthenticationManager / ProviderManager
  |
  v
KerberosServiceAuthenticationProvider
  |
  v
KerberosTicketValidator (ví dụ SunJaasKerberosTicketValidator)
  |
  | JAAS/JGSS acceptSecContext
  | servicePrincipal + service keytab
  v
Kết quả đã xác minh: alice@EXAMPLE.TEST
  |
  v
UserDetailsService / local identity mapping
  |
  v
Spring Authentication + GrantedAuthorities
  |
  v
SecurityContextRepository / session theo config
  |
  v
Authorization vào /private hay API
~~~

Các class tiêu biểu được mô tả trong tài liệu Spring Security Kerberos:

| Class | Vai trò | Không được nhầm |
| --- | --- | --- |
| `SpnegoEntryPoint` | Trả `401` và `WWW-Authenticate: Negotiate` khi cần xác thực | Không phải nơi xin TGT từ KDC |
| `SpnegoAuthenticationProcessingFilter` | Đọc header Negotiate, tạo `KerberosServiceRequestToken`, gọi AuthenticationManager | Không được tin base64 token trước validator |
| `KerberosServiceAuthenticationProvider` | Gọi KerberosTicketValidator và nạp UserDetails | Không tự kiểm tất cả business roles |
| `SunJaasKerberosTicketValidator` | JAAS/JGSS xác minh Kerberos/SPNEGO token với service principal/keytab | Keytab phải đúng service SPN/keys |
| `UserDetailsService` | Ánh xạ Kerberos principal đã được xác minh vào local authorities | Không phải KDC hoặc ticket validator |
| `SecurityContextRepository` | Giữ local Authentication giữa HTTP requests nếu stateful | Không phải TGT cache của client |

**TGT nằm ở đâu trong sơ đồ?** Ở **client OS/credential cache và KDC TGS exchange**, **không nằm trong SpnegoAuthenticationProcessingFilter để app xử lý trực tiếp**.

### 9.1. Hai provider dễ nhầm

- `KerberosServiceAuthenticationProvider`: dùng khi server **nhận service ticket/SPNEGO token** và cần xác thực client với acceptor keytab.
- `KerberosAuthenticationProvider`: có thể dùng cho **username/password Kerberos login** qua KerberosClient trong một số thiết kế/fallback; không phải bắt buộc khi chỉ nhận browser SPNEGO service tickets.

Đừng cấu hình `KerberosAuthenticationProvider` rồi giả định đó là bộ xác minh browser `Authorization: Negotiate`; thông thường cần `KerberosServiceAuthenticationProvider` cho đường service ticket.

### 9.2. Spring Security Kerberos là module mở rộng

Spring Security Kerberos có tài liệu và artifact riêng. Theo tài liệu Spring Security 7.x, tọa độ dependencies là:

~~~groovy
// build.gradle: Spring Security 7.x, version do BOM quản lý
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.security:spring-security-kerberos-core"
    implementation "org.springframework.security:spring-security-kerberos-web"
}
~~~

**Cần kiểm version alignment với Spring Boot và Spring Security thật**. Với Spring Security Kerberos 6.x trước đây, artifact group thường là **`org.springframework.security.kerberos`** (ví dụ `spring-security-kerberos-web:2.2.0`). **Từ Spring Security Kerberos 7**, tài liệu chính thức mô tả group đổi sang **`org.springframework.security`**. Không trộn group/version bất kỳ để ép classpath chạy và không copy toàn bộ đoạn Gradle trên như một project đã đủ SPN/keytab/KDC.

Nguồn: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html .

## 10. Mẫu cấu hình Spring Security Servlet cho SPNEGO

Ví dụ hướng đến **Spring Security Kerberos 7.x** với JDK 17+ trong ứng dụng Servlet. Có sẵn service account/keytab phía hạ tầng và một bean `UserDetailsService` do hệ thống cung cấp. Ví dụ **không tự tạo KDC hoặc keytab thật**.

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class SpnegoSecurityConfig {
    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
            "HTTP/portal.example.test@EXAMPLE.TEST");
        validator.setKeyTabLocation(new FileSystemResource(
            "/run/secrets/kerberos/http.keytab"));
        // Do not enable verbose credential debug in production.
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {
        ProviderManager manager = new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);
        filter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error")
                .permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationProvider(provider)
            .addFilterBefore(
                filter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Đây là Spring configuration sample**, không phải Java runnable độc lập: cần Spring Boot project, đúng dependencies/API, `UserDetailsService` bean, KDC/realm config, service principal và keytab thật. Nếu dùng Spring Security 6.x, kiểm package/import/method và module version tương ứng.

Đọc theo luồng:

1. `SpnegoEntryPoint` thách thức browser bằng HTTP Negotiate.
2. Browser gửi GSS token cho SPN public.
3. `SpnegoAuthenticationProcessingFilter` tạo yêu cầu xác thực từ header rồi gọi `ProviderManager`.
4. `KerberosServiceAuthenticationProvider` giao `SunJaasKerberosTicketValidator` để xác minh token.
5. Validator dùng **service keytab**, không dùng password hoặc user TGT.
6. Khi có Kerberos principal hợp lệ, `UserDetailsService` tìm user và authorities trong ứng dụng.
7. Filter lưu `SecurityContext` vào HttpSession theo cấu hình stateful minh họa.
8. Các quy tắc `authorizeHttpRequests` vẫn kiểm local authorities/resource permissions.

**Lưu ý vận hành:** đừng khai thêm `@Bean SpnegoAuthenticationProcessingFilter` khiến Servlet container tự đăng ký filter lần thứ hai ngoài Spring Security chain. Nếu cần bean cho kiến trúc khác, phải kiểm soát `FilterRegistrationBean`. Một service ticket/GSS token không được đem xác thực ở hai filter trùng nhau như phương án dự phòng.

### 10.1. Service keytab và principal ở môi trường

Ví dụ ứng dụng chạy trong container:

~~~text
JAVA_OPTS:
  -Djava.security.krb5.conf=/etc/krb5.conf

Keytab file:
  /run/secrets/kerberos/http.keytab  (read-only)

Service principal:
  HTTP/portal.example.test@EXAMPLE.TEST
~~~

Những dòng trên là **thông số deploy mẫu**, không phải YAML Kubernetes hoàn chỉnh. SPN phải được đăng ký tại KDC/AD cho đúng service identity, keytab phải chứa khóa tương ứng và Java runtime cần quyền đọc file. Không để Spring tự suy SPN từ một Host header do client cung cấp.

### 10.2. Không trộn local session và Kerberos ticket

Sau khi SPNEGO xác minh thành công, ứng dụng có thể giữ local `HttpSession`. Một request tiếp theo có thể được phục vụ bằng session cookie mà **không gửi GSS token mới**.

**HttpSession logout** chỉ xóa session ứng dụng; nó **không tự xóa TGT/service tickets trong OS credential cache**. Lần truy cập tiếp theo browser có thể thực hiện Negotiate và **được xác thực lại ngay** với Kerberos credentials còn hợp lệ. Nếu sản phẩm cần logout khỏi domain/thiết bị hoặc “force interactive reauthentication”, phải thiết kế chính sách OS/KDC/browser riêng; không coi `POST /logout` của Spring là xóa mọi Kerberos tickets.

## 11. Thiết lập realm, KDC và service principal

### 11.1. Ví dụ krb5.conf

Tệp `/etc/krb5.conf` trên máy Linux hoặc cấu hình Kerberos tương đương:

~~~ini
[libdefaults]
    default_realm = EXAMPLE.TEST
    dns_lookup_kdc = false
    rdns = false

[realms]
    EXAMPLE.TEST = {
        kdc = kdc.example.test
    }

[domain_realm]
    .example.test = EXAMPLE.TEST
    example.test = EXAMPLE.TEST
~~~

Đây là cấu hình **mẫu để học**, không phải thông tin server có thật. Trong Active Directory, DNS SRV records và các chính sách referral/cross-realm có thể được dùng thay vì khai cứng KDC; đừng thay thế cấu hình môi trường đã được IT/domain team duyệt. `rdns=false` có thể giảm reverse DNS canonicalization không mong muốn trong một số topology, nhưng cần test theo hệ sinh thái client/JDK/AD thực tế.

### 11.2. Service principal HTTP phải đúng hostname public

Nếu người dùng truy cập:

~~~text
https://portal.example.test/private
~~~

Kerberos client thường cần SPN:

~~~text
HTTP/portal.example.test@EXAMPLE.TEST
~~~

Nếu keytab của app chỉ có:

~~~text
HTTP/app-node-1.internal@EXAMPLE.TEST
~~~

thì acceptor có thể không giải mã/xác minh ticket cho hostname public. Đừng gỡ kiểm tra service keytab để chấp nhận tùy ý; thay vào đó:

- Đăng ký SPN public/alias đúng KDC/AD.
- Map SPN đến đúng service account có quyền sở hữu.
- Cấp keytab tương ứng và đồng bộ KVNO.
- Kiểm tra DNS CNAME và canonicalization từ browser/JGSS, không suy host theo internal container name.
- Nếu dùng load balancer, mọi instance cần key/service principal hợp lệ hoặc xác thực tại một trusted edge có thiết kế rõ.
- Với reverse proxy, bảo đảm header `Authorization: Negotiate` đi đúng thành phần acceptor; **không tin `X-Remote-User` từ Internet**.

### 11.3. Active Directory và duplicate SPN

Trong AD, SPN cần đăng ký duy nhất cho service identity. Duplicate SPN, sai service account hoặc keytab phát từ tài khoản khác có thể gây hiện tượng:

~~~text
KRB_AP_ERR_MODIFIED
GSSException: Defective token / Cannot find key of appropriate type
401 Negotiate loop
~~~

Đây là triệu chứng tùy trường hợp, không phải một lỗi duy nhất luôn có cùng nguyên nhân. Domain admin có thể dùng các công cụ chính thức như `setspn -Q` để kiểm tra SPN và quy trình được phê duyệt để đăng ký/rotate service account. **Không tự phát hành keytab bằng cách đổi password production service account ngoài kế hoạch**, vì các instance khác có thể mất khả năng giải mã service tickets.

## 12. Công cụ chẩn đoán an toàn với MIT Kerberos

Các lệnh dưới đây là **ví dụ cho MIT Kerberos trên Linux/macOS tương thích**, không đảm bảo cú pháp hoàn toàn giống công cụ `klist` của Windows. Không chạy trên production nếu không có quyền và quy trình, nhất là thao tác thay credential cache.

### 12.1. kinit — lấy TGT

~~~bash
kinit alice@EXAMPLE.TEST
~~~

Mục đích: xin **TGT cho alice** từ KDC bằng cơ chế xác thực được cấu hình. Lệnh có thể yêu cầu password hoặc phương thức khác; không ghi password vào shell command/history.

Để đặt lifetime theo chính sách:

~~~bash
kinit -l 8h alice@EXAMPLE.TEST
~~~

**Lưu ý:** `-l 8h` là lifetime **yêu cầu**; KDC có thể cấp ngắn hơn theo policy. Không tạo TGT không giới hạn bằng cách tăng thông số client.

Nếu được KDC/IT cho phép và TGT có renewable flag:

~~~bash
kinit -R
~~~

Lệnh chỉ renew khi thỏa `renew-till` và current validity rules. `kinit -R` không phải cơ chế vượt qua TGT đã bị KDC/policy vô hiệu hóa.

### 12.2. klist — xem credential cache

~~~bash
klist
klist -f
klist -e
~~~

Kết quả mô tả có thể gồm:

~~~text
Default principal: alice@EXAMPLE.TEST

Valid starting      Expires             Service principal
...                 ...                 krbtgt/EXAMPLE.TEST@EXAMPLE.TEST
...                 ...                 HTTP/portal.example.test@EXAMPLE.TEST
~~~

Đây là **mẫu minh họa**, không có thời gian giả định và không phải output máy thật.

- Dòng `krbtgt/EXAMPLE.TEST@EXAMPLE.TEST` là **TGT**.
- Dòng `HTTP/portal.example.test@EXAMPLE.TEST` là **service ticket**.
- `-f` hiển thị flags như Forwardable/Renewable theo client.
- `-e` hiển thị enctypes theo ticket/session key.
- Nếu `klist` không có TGT, browser có thể không có credentials để tự xin service ticket; còn phải xem môi trường OS/Windows LSA.

Không tải ảnh chụp klist chứa principal thật/các ticket details lên nơi công khai khi điều tra quyền riêng tư.

### 12.3. kvno — xin và xem phiên bản service key

~~~bash
kvno HTTP/portal.example.test@EXAMPLE.TEST
klist
~~~

`kvno` yêu cầu client có ticket cache/TGT phù hợp và có thể xin service ticket cho SPN đã cho từ KDC. Nó hiển thị key version number theo bản MIT Kerberos; kiểm xem service principal có tồn tại và KDC có cấp vé không.

**Thành công ở kvno chưa đủ chứng minh Spring acceptor có keytab đúng**. Client lấy được service ticket nhưng service vẫn có thể giải mã fail vì keytab sai KVNO/enctype hoặc Java/security config.

### 12.4. klist -k — xem keytab phía service

~~~bash
klist -k -t -e /run/secrets/kerberos/http.keytab
~~~

Kiểm:

- Có `HTTP/portal.example.test@EXAMPLE.TEST` không?
- KVNO và encryption types có phù hợp ticket/KDC?
- File có quyền owner/group/permissions an toàn, JVM có quyền đọc không?
- Có đang dùng một keytab cũ sau rotation không?

**Không sử dụng `klist -K` trong log**, vì tùy phiên bản nó in actual key material. Không sao chép keytab từ production về máy cá nhân để thử.

### 12.5. kdestroy — xóa cache local, không phải logout mọi nơi

~~~bash
kdestroy
~~~

Lệnh xóa Kerberos credentials trong credential cache được chọn của client (theo MIT Kerberos semantics). Nó **không đồng nghĩa** mọi service local session hay mọi ticket đã được issued ở nơi khác bị thu hồi ngay. Với Windows domain logon, thao tác cache/SSO dùng công cụ/chính sách khác.

## 13. Kiểm tra thời gian, ticket flags và lifetime

Kerberos phụ thuộc vào thời gian để giới hạn ticket và chống replay:

| Trường/flag | Ý nghĩa khái quát | Lỗi triển khai thường gặp |
| --- | --- | --- |
| `authtime` | Thời điểm principal được xác thực ban đầu | Nhầm với thời điểm từng HTTP request |
| `starttime` | Thời điểm ticket bắt đầu hợp lệ | Lệch clock khiến ticket “chưa hiệu lực” |
| `endtime` | Hết hạn vé | Dùng token đã hết hạn hoặc cache quá lâu |
| `renew-till` | Giới hạn tối đa để renew ticket nếu flag cho phép | Tưởng TGT có thể gia hạn vô hạn |
| `forwardable` | Cho phép chuyển tiếp TGT dưới điều kiện được quy định | Vô tình cấp quyền delegation quá rộng |
| `renewable` | Cho phép yêu cầu renew TGT theo policy | Thiếu flag nhưng app vẫn cố renew |
| `ok-as-delegate` | Gợi ý dịch vụ được đánh giá thích hợp cho delegation trong policy | Coi flag như cho phép blanket delegation |
| `kvno` | Phiên bản key mã hóa ticket | Keytab stale sau rotation |
| `enctype` | Loại mã hóa ticket/session key | Client/KDC/service không có bộ thuật toán chung |
| `client addresses` | Ràng buộc địa chỉ nếu profile/policy sử dụng | NAT/proxy làm giả định địa chỉ không đúng |

Một số triển khai cho phép **clock skew** ở mức vài phút; ví dụ thường gặp là khoảng năm phút, nhưng **không có nghĩa mọi realm phải dùng đúng 5 phút**. Chọn NTP đáng tin và policy skew của môi trường; không tăng clock skew quá rộng chỉ để login thành công.

### 13.1. Service ticket hết hạn nhưng TGT còn

Nếu SPN service ticket hết hạn mà TGT còn hiệu lực, client có thể **xin service ticket mới từ TGS**. Browser/app không cần phải quay về AS exchange nếu các điều kiện khác vẫn cho phép.

### 13.2. TGT hết hạn nhưng có service ticket trong cache

Không suy rằng việc TGT hết hạn luôn ngay lập tức làm một **service ticket đã cấp** vô hiệu ở service. Service ticket có lifetime và validation riêng, có thể tiếp tục dùng trong thời hạn hợp lệ theo các chính sách liên quan; tuy nhiên KDC có thể giới hạn thời gian ST khi phát và policy ở môi trường cụ thể có thể thay đổi outcome.

Nội dung chính: **TGT và service ticket không phải cùng một TTL hoặc cùng một entry**.

### 13.3. Disable user hoặc logout có thu hồi mọi service tickets ngay không?

Không mặc nhiên. Một server Kerberos có thể xác minh AP-REQ **offline bằng keytab** và thông tin ticket; không nhất thiết gọi KDC để kiểm tra trạng thái tài khoản mỗi lần. Đã cấp ticket có thể còn hiệu lực đến `endtime` hoặc khi policy/keys/validation khác làm nó bị từ chối. Muốn thu hồi truy cập tức thời, cần cân nhắc:

- Ngắn hạn ticket lifetime theo yêu cầu.
- Local session invalidation và check enabled/locked/resource authorization.
- KDC/service account key rotation/credential invalidation có kiểm soát.
- Cơ chế quản trị phiên ứng dụng hoặc policy AD/KDC hỗ trợ.
- Tránh hứa “disable AD account → tất cả HTTP sessions biến mất ngay” khi chưa kiểm chứng.

## 14. Forwardable TGT và Kerberos delegation: rủi ro riêng

**Forwardable** hoặc **proxiable** flags cho phép các luồng ủy nhiệm Kerberos đặc thù. Ví dụ một web service cần truy cập SMB/database **nhân danh người dùng** thay vì dùng danh tính máy chủ.

**Không có nhu cầu delegation** thì nên tránh mở:

- Unconstrained delegation: service có thể nhận/tiếp cận forwarded credentials với phạm vi rộng, blast radius lớn nếu host/keytab compromise.
- Lưu TGT của user ở server như “trạng thái đăng nhập” mà không có thiết kế kiểm soát credential.
- Cho bất kỳ HTTP request header nào quyết định user và tự tạo KDC ticket thay họ.

Nếu thực sự cần delegation:

1. Xác định target services cụ thể được phép.
2. Sử dụng Kerberos constrained delegation/S4U hoặc model được domain/security team phê duyệt.
3. Kiểm client credential forwarding policy và service principal rights.
4. Scope user/service/realm, credential cache lifetimes và audit.
5. Hạn chế secrets keytab, quyền process/container và máy chủ được tin.
6. Kiểm trường hợp double-hop và TGS errors riêng, không chuyển thành quyền “đọc mọi data”.
7. Không giả định mọi SPNEGO token chứa user TGT để service tự forward.

**Service ticket bình thường cho `HTTP/portal` không đồng nghĩa server đã được cấp user TGT để gọi mọi downstream services.** Đây là ranh giới giữa **authentication** và **delegation**.

## 15. Cross-realm: một TGT không giới hạn phạm vi mọi realm

Một client thuộc `SALES.EXAMPLE.TEST` có thể cần service ở `CORP.EXAMPLE.TEST`. Với **cross-realm Kerberos**, KDC có thể cấp **inter-realm TGT** và sử dụng trust path được cấu hình để xin service ticket tại realm đích.

~~~text
alice@SALES.EXAMPLE.TEST
      |
      v
TGT ở SALES KDC
      |
      v
Inter-realm TGT (trust path đã thiết lập)
      |
      v
CORP KDC / TGS
      |
      v
Service ticket HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
      |
      v
Spring HTTP acceptor ở CORP
~~~

Điểm cần kiểm:

- Realm trust/transited policy: không mặc định mọi realm tin nhau.
- SPN và realm đích phải phù hợp, không lấy realm từ chuỗi user input một cách vô điều kiện.
- Cross-realm identity có thể có cùng username ở hai realms nhưng là **hai principals khác nhau**.
- Local identity key nên scope theo **principal + realm/issuer**, và quyền vẫn từ local policy.
- Không bật wildcard realm hoặc nhận mọi foreign principal với cùng `alice` rồi gắn vào cùng admin.
- MIT/AD referral và DNS canonicalization có thể khiến realm thực tế không như người vận hành phỏng đoán.

## 16. Ví dụ Java 17 độc lập: vòng đời TGT, service ticket và Authenticator

Chương trình này **chạy với JDK 17+**, không cần Spring Boot, JGSS, KDC, AD hay mạng. Nó là một **mô phỏng học tập**, không phải implementation Kerberos. Mục tiêu là kiểm các invariant:

- Một TGT hợp lệ có thể dùng để xin **hai service tickets** khác nhau.
- Một web acceptor từ chối **TGT** (vì TGT không dành cho web).
- Service ticket đúng `HTTP/portal`, đang còn hạn, cùng principal và có **authenticator proof** thì được chấp nhận.
- Gửi lại **cùng authenticator** bị replay cache từ chối.
- **Cùng service ticket** nhưng **authenticator mới** có thể được chấp nhận khi ticket chưa hết hạn.
- Sai SPN, sai principal, thiếu bằng chứng session key, ticket hết hạn, authenticator stale, TGT hết hạn và SPN không đăng ký đều bị từ chối.

**Lưu ý bảo mật bắt buộc:** các boolean `issuedByKdc` và `provesPossessionOfSessionKey` là **đầu ra đã được mô phỏng tin cậy trong unit test**, không phải dữ liệu được đọc từ HTTP request hoặc một "claim" do client tự gửi. Ở Kerberos thật, **long-term keys, session keys, ticket encryption, authenticator crypto, replay cache và time checks** được KDC/JGSS/Kerberos libraries xử lý. Không được dùng chương trình này trong web filter, không tạo TGT/service ticket bằng records Java, không cấp quyền từ boolean.

Tệp **KerberosTicketsLifecycleDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class KerberosTicketsLifecycleDemo {
    private static final String TGS = "krbtgt/EXAMPLE.TEST@EXAMPLE.TEST";
    private static final String WEB = "HTTP/portal.example.test@EXAMPLE.TEST";
    private static final String FILES = "cifs/files.example.test@EXAMPLE.TEST";

    // All trust booleans are outputs from a MOCK verifier, NOT user input.
    record Tgt(String client, String tgsPrincipal,
               Instant expiresAt, boolean issuedByKdc) {}
    record ServiceTicket(String id, String client, String servicePrincipal,
                         Instant issuedAt, Instant expiresAt,
                         boolean issuedByKdc) {}
    record Authenticator(String client, String nonce, Instant createdAt,
                         boolean provesPossessionOfSessionKey) {}

    static final class FakeTgs {
        private final Set<String> registeredServices = Set.of(WEB, FILES);
        private final AtomicInteger sequence = new AtomicInteger();

        Optional<ServiceTicket> request(Tgt tgt, String spn, Instant now) {
            if (tgt == null || !tgt.issuedByKdc()
                    || !TGS.equals(tgt.tgsPrincipal())
                    || !now.isBefore(tgt.expiresAt())
                    || !registeredServices.contains(spn)) {
                return Optional.empty();
            }
            return Optional.of(new ServiceTicket(
                "ticket-" + sequence.incrementAndGet(),
                tgt.client(), spn, now,
                now.plus(Duration.ofMinutes(15)), true));
        }
    }

    static final class FakeAcceptor {
        private final String expectedSpn;
        private final Set<String> replayCache = ConcurrentHashMap.newKeySet();
        private final Duration allowedSkew = Duration.ofMinutes(5);

        FakeAcceptor(String expectedSpn) {
            this.expectedSpn = expectedSpn;
        }

        boolean accept(Object credential, Authenticator authenticator,
                       Instant now) {
            // A TGT cannot authenticate directly to an application service.
            if (!(credential instanceof ServiceTicket ticket)) return false;
            if (authenticator == null || !ticket.issuedByKdc()) return false;
            if (!expectedSpn.equals(ticket.servicePrincipal())) return false;
            if (now.isBefore(ticket.issuedAt())
                    || !now.isBefore(ticket.expiresAt())) return false;
            if (!ticket.client().equals(authenticator.client())
                    || !authenticator.provesPossessionOfSessionKey()) {
                return false;
            }
            Duration difference = Duration.between(
                authenticator.createdAt(), now).abs();
            if (difference.compareTo(allowedSkew) > 0) return false;
            // Real Kerberos validates cryptographic authenticators
            // and uses a replay cache.
            return replayCache.add(ticket.id() + ":" + authenticator.nonce());
        }
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-01T10:00:00Z");
        FakeTgs kdc = new FakeTgs();
        Tgt tgt = new Tgt(
            "alice@EXAMPLE.TEST", TGS, start.plusSeconds(3600), true);
        Optional<ServiceTicket> web = kdc.request(tgt, WEB, start);
        Optional<ServiceTicket> files = kdc.request(tgt, FILES, start);
        System.out.println("oneTgtGetsTwoServiceTickets=" +
            (web.isPresent() && files.isPresent()));

        FakeAcceptor webServer = new FakeAcceptor(WEB);
        Instant now = start.plusSeconds(30);
        Authenticator one = new Authenticator(
            "alice@EXAMPLE.TEST", "auth-one", now, true);

        System.out.println("tgtRejectedByWeb=" +
            !webServer.accept(tgt, one, now));
        System.out.println("validServiceTicketAccepted=" +
            webServer.accept(web.orElseThrow(), one, now));
        System.out.println("sameAuthenticatorReplayRejected=" +
            !webServer.accept(web.orElseThrow(), one, now));

        Authenticator fresh = new Authenticator(
            "alice@EXAMPLE.TEST", "auth-two", now.plusSeconds(1), true);
        System.out.println("sameServiceTicketFreshAuthenticatorAccepted=" +
            webServer.accept(web.orElseThrow(), fresh, now.plusSeconds(1)));

        System.out.println("wrongServiceRejected=" +
            !webServer.accept(files.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "auth-files", now, true),
                now));
        System.out.println("wrongClientRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("mallory@EXAMPLE.TEST", "other", now, true),
                now));
        System.out.println("noSessionKeyProofRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "unproven", now, false),
                now));
        System.out.println("expiredServiceTicketRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "expired",
                    start.plusSeconds(901), true),
                start.plusSeconds(901)));
        System.out.println("staleAuthenticatorRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "stale",
                    start.minusSeconds(400), true), now));
        System.out.println("expiredTgtCannotIssueNewTicket=" +
            kdc.request(tgt, WEB, start.plusSeconds(3601)).isEmpty());
        System.out.println("unknownServiceDeniedByKdc=" +
            kdc.request(tgt,
                "HTTP/unknown.example.test@EXAMPLE.TEST", now).isEmpty());
        System.out.println("untrustedTgtRejectedByKdc=" +
            kdc.request(new Tgt(
                "alice@EXAMPLE.TEST", TGS, start.plusSeconds(3600), false),
                WEB, now).isEmpty());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 KerberosTicketsLifecycleDemo.java
java KerberosTicketsLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
oneTgtGetsTwoServiceTickets=true
tgtRejectedByWeb=true
validServiceTicketAccepted=true
sameAuthenticatorReplayRejected=true
sameServiceTicketFreshAuthenticatorAccepted=true
wrongServiceRejected=true
wrongClientRejected=true
noSessionKeyProofRejected=true
expiredServiceTicketRejected=true
staleAuthenticatorRejected=true
expiredTgtCannotIssueNewTicket=true
unknownServiceDeniedByKdc=true
untrustedTgtRejectedByKdc=true
~~~

Giải thích:

- **oneTgtGetsTwoServiceTickets=true**: cùng TGT xin vé cho Portal và Files.
- **tgtRejectedByWeb=true**: web server acceptor không xử lý TGT.
- **validServiceTicketAccepted=true**: service ticket cho đúng SPN được dùng cùng authenticator hợp lệ.
- **sameAuthenticatorReplayRejected=true**: cùng authenticator không được dùng hai lần trong replay cache demo.
- **sameServiceTicketFreshAuthenticatorAccepted=true**: chính ticket còn hạn được dùng lại với **authenticator mới** — phân biệt hai đối tượng.
- **wrongServiceRejected=true**: vé cho Files không được dùng ở Portal.
- **wrongClientRejected=true**: authenticator mạo nhận principal khác bị từ chối.
- **noSessionKeyProofRejected=true**: không chứng minh nắm session key thì không đủ.
- **expiredServiceTicketRejected=true**: service ticket quá `endtime` bị từ chối.
- **staleAuthenticatorRejected=true**: authenticator ngoài clock skew policy bị từ chối.
- **expiredTgtCannotIssueNewTicket=true**: TGT quá hạn không được TGS chấp nhận xin vé mới.
- **unknownServiceDeniedByKdc=true**: không có SPN được đăng ký trong mock KDC.
- **untrustedTgtRejectedByKdc=true**: TGT chưa được tin/kiểm chứng không được dùng để xin vé.

Đây **không phải Kerberos crypto**, mà là **mô hình state/mối quan hệ**. `ConcurrentHashMap.newKeySet` chỉ mô phỏng replay cache **trong một JVM**, không an toàn cho GSS production nhiều node. **Không tự implement Kerberos replay cache trong HTTP controller**; dùng Kerberos/JGSS acceptor và cơ chế cache/token handling được hỗ trợ.

## 17. Xử lý danh tính sau khi Kerberos đã xác minh

Sau khi JGSS xác minh Kerberos token, ứng dụng nhận được **client principal** như:

~~~text
alice@EXAMPLE.TEST
~~~

Đây là **định danh đã xác thực bởi Kerberos service provider**. Nó không tự tạo các quyền:

~~~text
ROLE_ADMIN
ROLE_FINANCE_APPROVER
TENANT_B_RESOURCE_OWNER
~~~

`KerberosServiceAuthenticationProvider` thường dùng **UserDetailsService** để lấy authorities từ LDAP/AD/local DB. Tùy ứng dụng, cần:

- Ánh xạ principal+realm thành local user bền vững.
- Kiểm user enabled, không bị locked/deprovisioned theo policy.
- Chỉ cấp roles từ dữ liệu quyền đã được ứng dụng cho phép; không biến tên group/các header từ browser thành `ROLE_ADMIN`.
- Không lấy tên user chỉ trước ký tự `@` rồi gộp `alice@REALM_A` với `alice@REALM_B`.
- Không coi có TGT hoặc service ticket hợp lệ là đủ để truy cập tài liệu confidential.
- Kiểm tenant ownership/resource permission ở business API, không phụ thuộc một cờ authenticated.
- Nếu cần truyền user identity từ trusted gateway đến backend, dùng **mô hình chuyển trust** được đánh giá và header spoof protection; không mặc định `X-Forwarded-User` là Kerberos principal đã xác minh.

### 17.1. Bảo vệ auth token đầu vào

Một HTTP client có thể tự gửi:

~~~http
Authorization: Negotiate ZmFrZS10b2tlbg==
~~~

Chuỗi Base64 trên là **dữ liệu giả**, không có GSS context hợp lệ. Ứng dụng phải từ chối qua provider/validator. **Đừng Base64-decode header rồi tự đọc username** hoặc ghi raw token vào log.

### 17.2. Không coi Kerberos success là MFA proof chung

Kerberos chứng minh client nắm credential/session key hợp lệ theo KDC. Việc có dùng MFA/PKINIT/smartcard hay policy step-up trong **AS exchange** phụ thuộc hạ tầng và tín hiệu xác thực được công nhận, không phải mặc định mọi SPNEGO AP-REQ chứng minh “vừa hoàn thành MFA” ở thời điểm HTTP request.

Các API yêu cầu xác thực mạnh cần policy kết hợp identity assurance, step-up/freshness và session boundaries cụ thể.

## 18. Kerberos qua load balancer, reverse proxy và containers

### 18.1. Public SPN và private backend host

~~~text
Browser -> https://portal.example.test
                  |
                  v
       Load Balancer / Ingress
           /       |        \
        App 1    App 2     App 3
~~~

Browser thường xin service ticket cho `HTTP/portal.example.test@EXAMPLE.TEST`, **không phải** `HTTP/app-1.internal@EXAMPLE.TEST`. Cần thống nhất:

- Thành phần nào thực sự thực hiện GSS acceptor: ingress hay từng app?
- Nếu app nhận `Authorization: Negotiate` trực tiếp, những instance cần service credentials/keytab thích hợp.
- Nếu ingress terminate SPNEGO, backend chỉ được tin một **identity assertion đã được bảo vệ** qua mTLS/identity-aware proxy, không tin headers do Internet cung cấp.
- Session/replay security context phải hoạt động đúng giữa các instances; không tùy tiện disable replay.
- Nếu một instance có keytab KVNO mới và instance khác cũ, lỗi 401 có thể chỉ xuất hiện ngẫu nhiên theo node.
- Channel binding/Extended Protection nếu được yêu cầu phải được hai đầu phối hợp với TLS termination; **không tắt tính năng đó chỉ để hết lỗi**.

### 18.2. Không dùng keytab user để làm web acceptor

Container web service có thể cần keytab của `HTTP/public-host`, không cần `kinit alice` hay user password trong init container. Nếu app còn đóng vai client gọi một service Kerberos khác, đó là **vai trò initiator riêng**, có thể cần credential acquisition/delegation khác, không đồng nhất với chức năng acceptor.

## 19. Ma trận kiểm thử tích hợp và bảo mật

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| User domain chuẩn | Client có TGT, truy cập Portal qua trusted browser | Negotiate → service ticket → authenticated |
| Chưa có TGT | Credential cache trống và không có SSO logon | Không thể tự động Kerberos; hiển thị 401/fallback theo policy |
| TGT còn hạn | Client xin ticket Portal và Files | Cấp service tickets riêng theo SPN |
| TGT hết hạn | Xin ticket mới qua TGS không còn hợp lệ | Fail/renew/AS exchange theo KDC policy |
| Service ticket đúng Portal | HTTP/portal ticket + valid authenticator | GSS accept và local auth nếu user được phép |
| Service ticket dành Files ở Portal | Ticket cho cifs/files thay vì HTTP/portal | Từ chối |
| Gửi TGT vào web như service ticket | TGT for krbtgt | Web acceptor không xác thực |
| Authenticator replay | Lặp đúng AP-REQ/authenticator | Từ chối theo replay protection |
| Cùng service ticket, authenticator mới | Ticket còn hạn, fresh auth | Có thể được chấp nhận theo Kerberos semantics |
| Ticket hết hạn | `endtime` trước now | Từ chối |
| Time skew | Client/server lệch quá giới hạn | Từ chối, sửa NTP |
| Sai keytab principal | Keytab chỉ chứa HTTP/internal | Từ chối với service ticket cho public host |
| KVNO mismatch | KDC key mới, app keytab cũ | Fail, rollout keytab đúng |
| Enctype không tương thích | Không có key phù hợp enctype | Fail, sửa key/crypto policy |
| SPN chưa đăng ký | `kvno HTTP/portal...` không thể cấp vé | TGS error, sửa KDC/AD |
| Duplicate SPN AD | Một SPN gắn nhiều accounts | Điều tra/khắc phục bằng domain admin |
| Browser chỉ gửi NTLM | Negotiate fallback sang NTLM | Từ chối nếu policy require Kerberos |
| Header giả Base64 | Không phải GSS token hợp lệ | 401/failure; không tạo Authentication |
| HTTP không TLS | Auth Kerberos vẫn có nhưng URL/body lộ | Security test FAIL/deployment gate |
| Header spoof | Client tự gửi `X-Remote-User: admin` | Không xem là authenticated |
| Cross-realm user | `alice@REALM_B` qua trust hợp lệ | Identity scoped realm; không gộp alice@REALM_A |
| User local disabled | Kerberos ticket hợp lệ nhưng DB khóa user | Không cấp quyền vào app |
| User thiếu role | GSS success nhưng resource requires role | 403, không nhầm 401 |
| Local logout | Spring session bị xóa, OS TGT còn | Browser có thể SPNEGO lại; UI scope chính xác |
| Delegation disabled | Web app thử gọi downstream nhân danh user | Không có forwarded credentials tự động |
| Unconstrained delegation | Service bị cấp quyền rộng ngoài use case | Security review FAIL |
| Keytab leak test | File keytab bị world-readable | Security policy FAIL |
| Nhiều replicas | Một node keytab cũ sau rotation | Phát hiện 401 theo instance |
| Reverse proxy hostname | Public host vs internal host khác | SPN public/forwarded headers được thiết kế |
| Channel binding | TLS termination khác yêu cầu CBT | Fail an toàn, điều tra chính sách |
| Log/tracing | Authorization Negotiate token xuất hiện trong log | Redact, không lưu GSS token |
| KDC unavailable | TGT/ST cache đã có nhưng không xin mới được | Hành vi phân biệt cache vs new ticket, không bypass |

**Mỗi integration test cần phân biệt:** lỗi **client chưa có TGT**, lỗi **TGS không cấp ST**, lỗi **GSS acceptor không giải mã/verify ST**, và lỗi **application authorization**. Nếu gộp tất cả thành một thông báo “Sai mật khẩu” sẽ rất khó điều tra và có thể dẫn đến cấu hình bypass nguy hiểm.

## 20. Troubleshooting theo mã lỗi và biểu hiện

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| 401 không có Negotiate header | SpnegoEntryPoint/filter chain không cấu hình đúng | Xem SecurityFilterChain, Response headers |
| 401 có Negotiate nhưng browser không gửi Authorization | Browser không cho integrated auth, không có TGT, site không thuộc intranet allowlist | Browser policy, OS credential cache, klist |
| Browser gửi Negotiate rồi vẫn lặp 401 | Sai SPN, keytab/kvno, GSS token/mechanism, policy | Debug auth error ở app với token redacted |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | SPN không tồn tại hoặc realm/name sai | `kvno HTTP/portal...`, DNS/AD |
| `KRB_AP_ERR_MODIFIED` | Server không giải mã ticket: SPN/keys/kvno/account có vấn đề | KDC principal, keytab, AD duplicates |
| `KRB_AP_ERR_TKT_EXPIRED` | Service ticket quá hạn | `klist`, time sync, KDC policies |
| `KRB_AP_ERR_SKEW` | Chênh lệch đồng hồ | NTP client/KDC/service |
| `KRB_AP_ERR_REPEAT` | Replay của authenticator | Kiểm GSS replay cache/context, không disable |
| `KRB_AP_ERR_NOKEY` | Acceptor thiếu key thích hợp | `klist -k -t -e`, service principal |
| `KRB_AP_ERR_BADKEYVER` | Key version không được server hỗ trợ | KVNO rollout, service keytab |
| Encryption type unsupported | Client/KDC/service không thống nhất enctypes | KDC policy, Java crypto, keytab entries |
| `GSSException: No valid credentials provided` | Keytab không đọc được, JAAS login error, thiếu acceptor credential | File path, permissions, servicePrincipal |
| `GSSException: Defective token` | Token hỏng/mech sai, proxy sửa header, GSS context không hợp lệ | Header flow, SPNEGO client/server versions |
| Channel binding mismatch | TLS CBT/Extended Protection không tương thích | TLS termination, Java/browser/AD policy |
| NTLM fallback không mong đợi | Browser không chọn Kerberos/SPN không resolve | Mech selection, Windows policy |
| Service ticket có nhưng app không auth | Provider/validator/UserDetails lỗi | KerberosServiceAuthenticationProvider, UserDetailsService |
| Login thành công nhưng HTTP 403 | Local role/resource authorization từ chối | Roles, user status, tenant policy |
| Chỉ một replica lỗi | Keytab stale hoặc không chia sẻ session/config | Theo node logs và deployment version |
| Chỉ production lỗi | SPN/public host/TLS/trust khác DEV | DNS, ingress, KDC realm, keytab |
| Logout rồi vào lại tự động | OS TGT/service ticket còn hợp lệ | Giải thích local logout khác domain sign-out |
| User disabled nhưng session cũ vẫn hoạt động | Local session/authorization cache còn | Session invalidation và policy refresh |
| Double-hop lỗi | Service không có quyền/credential delegation | Constrained delegation, target SPN |
| Log chứa GSS token | Access log header nhạy cảm bị thu | Redaction và incident management |

### 20.1. Runbook gợi ý theo thứ tự

1. Xác định **website URL công khai**, realm, service SPN mong đợi.
2. Client: kiểm **TGT** trong credential cache bằng công cụ OS phù hợp.
3. Client: dùng `kvno HTTP/portal.example.test@EXAMPLE.TEST` (trong môi trường được phép) để kiểm TGS cấp service ticket.
4. Browser: kiểm 401 `WWW-Authenticate: Negotiate` rồi `Authorization: Negotiate`, **không ghi/đăng raw token**.
5. Server: kiểm JVM đọc được keytab, có đúng principal, KVNO/enctype bằng `klist -k -t -e`.
6. Kiểm NTP/KDC/AD trust/cross-realm và callback hostname/canonicalization.
7. Xem `KerberosServiceAuthenticationProvider` có nhận **KerberosServiceRequestToken** và mapping UserDetails thành công không.
8. Phân biệt 401 authentication failure với 403 local authorization denial.
9. Nếu login thành công ở một node nhưng fail node khác, kiểm keytab/version/session và GSS replay/cache topology.
10. Chỉ sau khi điều tra, điều chỉnh configuration dưới review. **Không chuyển sang tin username HTTP header hoặc tắt crypto/replay để chữa 401.**

### 20.2. Log đúng phạm vi

Có thể log an toàn theo policy:

~~~text
event=KERBEROS_SPNEGO_AUTH_FAILED
servicePrincipal=HTTP/portal.example.test@EXAMPLE.TEST
reason=SPN_OR_KEYTAB_MISMATCH
node=portal-2
traceId=trace-7f4e
elapsedMs=121
~~~

Không log **raw `Authorization: Negotiate`**, GSS tokens, ticket cache, keytab bytes, passwords, decrypted ticket/session keys hoặc principal chứa dữ liệu cá nhân nếu không có căn cứ và cơ chế bảo vệ.

## 21. Checklist triển khai production

- [ ] Đã hiểu TGT là vé dành cho `krbtgt`, service ticket dành cho SPN của application server.
- [ ] Có AS/TGS/KDC realm đáng tin, đúng trust policy và clock synchronization.
- [ ] Client credential cache chứa TGT/keys; server keytab chứa **service long-term keys**, không chứa user TGT.
- [ ] SPN `HTTP/public-fqdn@REALM` được đăng ký đúng và sở hữu bởi service account được duyệt.
- [ ] Browser được cấu hình Integrated Auth chỉ cho site được tin; không mở “auto logon” tùy ý trên Internet.
- [ ] Dùng HTTP `Negotiate` qua HTTPS; không coi header có tên Negotiate là bằng chứng Kerberos.
- [ ] Theo policy, tránh NTLM fallback khi yêu cầu Kerberos; test mech và assurance thực tế.
- [ ] Spring Security dùng đúng `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` và `SunJaasKerberosTicketValidator`.
- [ ] Kerberos dependencies/versions tương thích Spring Security 6.x hay 7.x; chú ý Maven group thay đổi trong 7.x.
- [ ] Service principal/keytab path/permissions/TLS proxy đã được triển khai đúng, không commit keytab.
- [ ] Không đăng ký filter SPNEGO hai lần ngoài và trong Spring Security chain.
- [ ] GSS validation xử lý service ticket, authenticator, time/replay và service identity; không parse raw token trong controller.
- [ ] Keytab KVNO/enctype khớp KDC/service account, có kế hoạch rotation/cutover.
- [ ] Client TGT và ST lifetimes theo KDC policy, không hardcode giả định tất cả tickets là one-time.
- [ ] Authenticator replay bị từ chối; không disable replay cache hoặc bỏ clock skew check.
- [ ] App không nhận TGT làm login credential và không cần krbtgt key.
- [ ] Local UserDetailsService kiểm user status và authorities; authentication khác authorization.
- [ ] Local logout/HttpSession không được hứa là xóa TGT trong OS hoặc các service tickets khác.
- [ ] Cross-realm identity không gộp users cùng tên nhưng khác realm.
- [ ] Delegation chỉ bật nếu có use case, ưu tiên constrained delegation; không truyền user TGT tùy tiện.
- [ ] DNS, CNAME, public FQDN, realm mapping và trusted forward headers có test.
- [ ] Nếu có LB/container, service keytab và SPN nhất quán giữa instances.
- [ ] HTTP CSRF, cookie/session security và HTTPS vẫn được duy trì dù login dùng Kerberos.
- [ ] Không ghi GSS token, ticket, keytab, password hoặc session keys vào logs/traces.
- [ ] Integration tests bao gồm happy path, TGT expired, wrong SPN, wrong keytab/KVNO, NTLM fallback, replay, clock skew, user disabled và 403.
- [ ] Có runbook KDC outage, rotation, AD SPN ownership và rollback an toàn.

## 22. Câu hỏi tự kiểm tra

**1. TGT được cấp bởi thành phần nào?**

Thông thường từ **Authentication Service (AS)** của KDC trong AS exchange. Nó dành cho **TGS/krbtgt**, không dành cho website.

**2. Service ticket được lấy bằng gì?**

Client sử dụng **TGT cùng authenticator sử dụng client–TGS session key** gửi **TGS-REQ** tới KDC/TGS để xin vé dành cho SPN đích.

**3. Web app có cần private key `krbtgt` để xác thực user không?**

Không. Web acceptor dùng **service keytab** của `HTTP/public-host@REALM` để kiểm **service ticket/AP-REQ**, không dùng key krbtgt.

**4. TGT có thể dùng để xin nhiều service tickets không?**

Có khi còn hợp lệ và policy cho phép. Một TGT có thể xin ticket cho Portal, Files và các service khác.

**5. Có thể đem service ticket cho Files dùng để đăng nhập Portal không?**

Không. Ticket ràng buộc với service principal. App phải xác minh đúng SPN.

**6. Service ticket Kerberos có dùng lại được không?**

Có thể dùng cho nhiều AP exchanges khi còn hạn và policy cho phép, **nhưng phải dùng authenticator mới và chống replay**. Không được replay nguyên AP-REQ/authenticator đã dùng.

**7. Vì sao ticket một mình chưa đủ xác thực client?**

Vì có thể bị sao chép. **Authenticator** được bảo vệ bằng session key chứng minh possession và hỗ trợ chống replay.

**8. Trong Spring Security, TGT được xử lý ở filter nào?**

TGT thuộc **client–KDC TGS exchange**, không phải web filter. `SpnegoAuthenticationProcessingFilter` nhận **GSS/SPNEGO service token** từ HTTP header.

**9. `Authorization: Negotiate` có luôn là raw service ticket không?**

Không. Đây là **base64 GSS-API/SPNEGO token**, có thể bao gồm NegTokenInit/NegTokenResp và Kerberos AP-REQ; không phải một chuỗi service ticket thuần hay username.

**10. Vì sao thành công Kerberos chưa chắc user được mở báo cáo tài chính?**

Kerberos chứng minh identity; **local authorization** còn kiểm user trạng thái, roles, tenant và resource permissions.

**11. `kinit`, `klist`, `kvno` khác nhau thế nào?**

`kinit` lấy TGT; `klist` xem tickets trong credential cache (hoặc keytab khi dùng `-k`); `kvno` xin/xem service ticket và key version number.

**12. Tại sao keytab bị lỗi sau khi domain admin đổi service account password?**

KDC có thể phát ticket với **KVNO/key mới**, còn app keytab đang có key cũ. Cần đồng bộ service credential và rollover.

**13. Tại sao local logout Spring xong người dùng lại vào ứng dụng ngay mà không nhập mật khẩu?**

Vì TGT/service ticket còn trong OS credential cache và browser có thể thực hiện SPNEGO lại. Local HttpSession logout không xóa domain credential cache.

**14. Mỗi HTTP request có luôn gửi TGT tới KDC không?**

Không. TGT/service tickets/GSS contexts và app local session đều có thể được cache. KDC thường không cần tham gia từng HTTP request.

**15. Nếu user Alice đã đăng nhập ở REALM_A và REALM_B, app có nên coi đó là cùng danh tính vì username giống nhau?**

Không tự động. Principal cần scope theo **realm**, và business account linking phải có policy/bằng chứng riêng.

**16. Vì sao SPNEGO không thay thế HTTPS?**

HTTP Negotiate xác thực client/service theo cơ chế phù hợp nhưng **không bảo vệ toàn bộ HTTP URL, headers, cookies và body**. TLS vẫn cần thiết.

**17. Có nên bật unconstrained delegation để web app truy cập downstream dễ hơn?**

Không. Delegation làm mở rộng quyền sử dụng credentials; nên giới hạn theo target/role và ưu tiên constrained delegation dưới quản trị KDC/AD.

**18. Sự khác nhau lớn nhất giữa session key và keytab là gì?**

**Session key** là khóa tạm thời gắn với ticket/đối thoại; **keytab** lưu long-term key của service principal, để acceptor giải mã/xác minh tickets đúng service.

## 23. Nguồn tham khảo chuẩn và tài liệu chính thức

- IETF **RFC 4120 — The Kerberos Network Authentication Service (V5)**: AS exchange, TGS exchange, AP exchange, ticket, authenticator, service keys, flags và replay: https://www.rfc-editor.org/rfc/rfc4120
- IETF **RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication**: `WWW-Authenticate: Negotiate`, `Authorization: Negotiate`, SPN `HTTP/hostname`, HTTP security considerations: https://www.rfc-editor.org/rfc/rfc4559
- IETF **RFC 4178 — SPNEGO**: cách đàm phán GSS-API security mechanism: https://www.rfc-editor.org/rfc/rfc4178
- IETF **RFC 4121 — Kerberos V5 GSS-API Mechanism**: GSS security context và tokens: https://www.rfc-editor.org/rfc/rfc4121
- Spring Security, **Introduction to Spring Security Kerberos**: module artifacts, dependency coordinates thay đổi với Spring Security 7: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security, **Spring and Spring Security Kerberos**: `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, keytab và JavaConfig: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Spring Security Javadoc, **SpnegoAuthenticationProcessingFilter**: HTTP Negotiate header → KerberosServiceRequestToken/AuthenticationManager: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Spring Security Javadoc, **KerberosServiceAuthenticationProvider**: validate service tickets và nạp UserDetails/authorities: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- MIT Kerberos, **kinit**: xin/cache TGT và options renew/forwardable: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kinit.html
- MIT Kerberos, **klist**: xem credential cache, keytab, ticket flags/enctypes: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html
- MIT Kerberos, **kvno**: xin service ticket và xem key version number: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html
- MIT Kerberos, **keytab**: service long-term keys, principal/KVNO/enctype: https://web.mit.edu/kerberos/krb5-latest/doc/basic/keytab_def.html

**Ghi nhớ:** **TGT** do KDC/AS cấp cho **`krbtgt`** để client xin thêm **service tickets** ở TGS; **service ticket** do KDC/TGS cấp cho **đúng SPN của service**, ví dụ `HTTP/portal.example.test@EXAMPLE.TEST`. Với web, browser đưa **GSS/SPNEGO AP-REQ** chứa service ticket và **authenticator** qua HTTP Negotiate; Spring Security Kerberos dùng **service keytab/JGSS** để xác minh, rồi mới ánh xạ principal vào local user và phân quyền. **TGT không đi thẳng vào web app, service ticket không thay quyền nghiệp vụ, còn replay của authenticator phải bị chặn ngay cả khi ticket chưa hết hạn.**