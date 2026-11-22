# Rủi ro ủy quyền danh tính và nhu cầu giới hạn delegation trong Kerberos/SPNEGO

## 1. Vấn đề thực tế: người dùng vào web an toàn, nhưng web có thể làm gì thay họ?

Giả sử một nhân viên sử dụng máy tính đã đăng nhập vào domain Active Directory để mở ứng dụng Spring Boot nội bộ:

~~~text
User browser -> https://portal.example.org
                HTTP Negotiate / SPNEGO
                Kerberos service ticket cho HTTP/portal.example.org
                -> Spring Security xác thực user@EXAMPLE.ORG
~~~

Ứng dụng tiếp tục cần đọc tài liệu trên `CIFS/files.example.org` hoặc truy vấn một backend `HTTP/api.example.org` **với danh tính nhân viên** để hệ thống đích áp dụng quyền theo user.

Một cách xử lý sai là nghĩ: “Spring đã nhận diện user nên có thể gọi bất kỳ backend nào dưới đúng danh tính đó”. **Không đúng.** Nhận diện principal trong `Authentication` chỉ nói về **giao dịch xác thực giữa client và portal**. Việc ứng dụng trung gian có thể **đại diện user để xác thực ở backend** là một quyền khác, thường gọi là **delegation** hoặc **impersonation**, chịu chính sách của Kerberos KDC, account, target service và runtime.

Nếu cấp **unconstrained delegation** cho portal chỉ để đọc một file share, khi web server/service account bị xâm nhập, attacker có thể có phạm vi sử dụng danh tính người dùng ở nhiều dịch vụ rộng hơn nhu cầu. Nếu dùng **constrained delegation** nhưng allow-list chứa cả `LDAP/domain-controller` hoặc những dịch vụ quản trị không cần thiết, nguy cơ vẫn lớn. Nếu backend tin một HTTP header `X-User: administrator` do client gửi, ứng dụng đang tự tạo **identity impersonation** mà **không cần Kerberos**.

Bài Knowledge thuộc **Spring Security - federation → Kerberos và SPNEGO**, chủ đề **“Rủi ro ủy quyền danh tính và nhu cầu giới hạn delegation”**. Trọng tâm là **thiết kế ranh giới tin cậy và giới hạn quyền**, không phải hướng dẫn chiếm quyền hoặc khai thác Active Directory.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Tách bạch **Kerberos authentication**, **local impersonation**, **credential delegation**, **authorization** và **service-to-service authentication**.
2. Mô tả hai-hop scenario browser → Spring SPNEGO → backend, chỉ rõ lý do “double-hop” xảy ra.
3. Phân biệt **forwarded TGT/unconstrained delegation**, **classic Kerberos Constrained Delegation (KCD)**, **S4U2Self/S4U2Proxy** và **Resource-Based Constrained Delegation (RBCD)**.
4. Hiểu `SPN`, ticket `FORWARDABLE/FORWARDED`, `OK-AS-DELEGATE`, GSS-API delegated credentials và giới hạn của SPNEGO negotiation.
5. Áp dụng nguyên tắc **không delegation theo mặc định**, chỉ định rõ **frontend identity, backend service, hành động, user/tenant, lifetime**.
6. Không đồng nhất `Principal.getName()`, JWT claims, HTTP headers với **Kerberos credentials**.
7. Biết cấu hình an toàn ở mức **Active Directory/KDC policy, service account/gMSA, SPNs, ACL, KCD/RBCD** và kiểm soát privileged accounts.
8. Hiểu chính xác vai trò Spring Security Kerberos: `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `KerberosTicketValidator`, `UserDetailsService`.
9. Phân tích `GSSContext.requestCredDeleg()</BT>, `getCredDelegState()`, `getDelegCred()` mà không gợi ý bật delegation đại trà.
10. Kiểm thử denial, backend authorization, multi-tenant, credential lifetime, logging, thread reuse, failure handling và monitoring.
11. Chạy demo Java 17 **độc lập** mô phỏng chính sách cho phép/không cho phép delegation theo service và thao tác, không cần domain thật.
12. Xây runbook trước khi đưa Kerberos delegation vào production.

**Môi trường minh họa:** Kerberos V5, SPNEGO qua HTTP Negotiate, Spring Boot 3.x/Spring Security 6.x+ Servlet/MVC, Windows Active Directory khi nói đến KCD/RBCD; Java 17+. RFC 4120 áp dụng cho Kerberos nói chung, còn **S4U/RBCD là extension/hành vi theo Microsoft Kerberos/AD**, không mặc định có ở mọi MIT/Heimdal KDC hoặc Java integration.

---

## 2. Trước hết, phân biệt năm khái niệm thường bị trộn

| Khái niệm | Ý nghĩa | Có tự cho phép truy cập backend dưới user không? |
| --- | --- | --- |
| **Authentication** | Chứng minh chủ thể với một dịch vụ, ví dụ browser trình Kerberos ticket cho HTTP portal | **Không** |
| **Authorization** | Quyết định user/service được phép làm hành động trên tài nguyên nào | **Không** tự tạo credential |
| **Impersonation cục bộ** | Một tiến trình dùng security context/token người dùng cho thao tác trong ngữ cảnh hệ điều hành | **Không mặc định** có thông tin xác thực cho network hop khác |
| **Credential delegation** | Một chủ thể trao hoặc cho phép service nhận khả năng chứng minh danh tính thay mình ở dịch vụ khác | **Có thể**, theo cơ chế/phạm vi credential được cấp |
| **Service identity** | Frontend kết nối backend bằng chính danh tính service account của nó | Không giả làm user; backend có thể xử lý **user context được xác minh** riêng |

**Ví dụ đúng:** Spring kiểm tra user đã login bằng SPNEGO và dùng `Authentication.getName()` để hiển thị “Xin chào, Linh”. Đây là **authentication** và sử dụng thông tin principal.

**Ví dụ cần delegation:** Spring dùng danh tính Linh để yêu cầu ticket truy cập `CIFS/files.example.org` làm cho file server kiểm tra ACL của Linh. Đó là một **Kerberos hop mới** cần credential/chính sách được cấp cho phép.

**Ví dụ service identity an toàn khi phù hợp:** Spring dùng một service principal `HTTP/portal.example.org` hoặc identity riêng để gọi API, truyền một **application-issued, signed, audience-bound on-behalf-of context** theo hợp đồng đã thiết kế để backend kiểm tra. Đây không phải tự động Kerberos KCD; backend phải tin **issuer/audience/signature/scope** và áp quyền đúng. Tuyệt đối không lấy `X-User` browser tự khai làm thông tin ủy quyền.

## 3. Kerberos/SPNEGO xác thực HTTP hoạt động như thế nào?

Đối với môi trường Windows/AD điển hình:

1. User login vào workstation và lấy **Ticket-Granting Ticket (TGT)** từ Key Distribution Center (KDC).
2. Browser truy cập `https://portal.example.org`.
3. Ứng dụng HTTP trả `401 WWW-Authenticate: Negotiate` để yêu cầu thương lượng SPNEGO.
4. Browser/SSPI/Kerberos stack xin **service ticket** cho SPN `HTTP/portal.example.org`.
5. Browser gửi `Authorization: Negotiate [base64 token]`.
6. Spring Security Kerberos filter/provider và JGSS/Jaas validator xác minh service ticket bằng keytab/service credentials tương ứng.
7. Spring Security tạo `Authentication`, ánh xạ principal/authorities theo `UserDetailsService` hoặc policy.
8. Browser có thể tiếp tục gửi request trên cùng phiên HTTP; backend authorization vẫn do app kiểm tra.

~~~mermaid
sequenceDiagram
    participant B as Browser/user
    participant K as Kerberos KDC
    participant W as Spring SPNEGO portal
    B->>K: Đã có TGT, xin service ticket cho HTTP/portal
    K-->>B: Service ticket cho HTTP/portal
    B->>W: Authorization: Negotiate token
    W->>W: Verify service ticket, tạo Authentication
    W-->>B: Portal response/session theo cấu hình
    Note over W,K: Chưa có quyền user-specific cho backend
~~~

**SPNEGO** là cơ chế thương lượng qua token HTTP `Negotiate`; Kerberos là một security mechanism có thể được chọn. Trong thực tế còn có NTLM fallback ở một số môi trường Windows. **Không suy “có header Negotiate” nghĩa 100% Kerberos**, và không dùng một username string xuất hiện trong header làm bằng chứng.

**Quan trọng:** Service ticket được phát **cho portal** không thể tùy tiện chuyển sang database/file server như một ticket hợp lệ cho backend đó. Mỗi backend có **SPN/key/audience** riêng. Việc “pass-through” raw SPNEGO token từ frontend sang backend khác là thiết kế sai trust boundary nếu không có protocol/credential exchange hợp lệ.

## 4. “Double-hop problem” là gì?

Xét ba máy:

~~~text
[User workstation] --(Kerberos)--> [Spring web portal]
                                       |
                                       | backend call as user?
                                       v
                                [File server / API / DB]
~~~

**Hop 1:** browser xác thực Kerberos với portal.

**Hop 2:** portal muốn kết nối backend **dưới user**, để backend thực thi quyền truy cập theo người dùng.

Nếu portal chỉ nhận một service ticket cho chính portal và biết username, nó **chưa có khả năng hợp lệ** để chứng minh danh tính người dùng ở backend. Hệ thống có thể trả lỗi truy cập, rơi về service identity hoặc không có delegation credential.

### Ba giải pháp khác mục đích

1. **Không delegation:** portal truy cập backend bằng service identity có quyền tối thiểu, kiểm tra quyền user ở ứng dụng hoặc bằng token context có chữ ký/audience/scope nếu kiến trúc hỗ trợ.
2. **Constrained delegation:** có lý do nghiệp vụ để backend thực thi native Kerberos authorization theo user; cấu hình KDC cho phép frontend đại diện user **chỉ tới target SPNs được chọn**.
3. **Credential forwarding rộng:** frontend nhận delegated credential có phạm vi rộng, có thể dùng để xin nhiều service tickets. Đây là lựa chọn rủi ro cao, **không dùng chỉ để giải quyết lỗi double-hop** nếu có phương án hẹp hơn.

Quyết định phải dựa trên **tài nguyên nào bắt buộc nhận user identity**, không dựa trên mong muốn “cho login chạy được”.

## 5. Credential forwarding và unconstrained delegation

Theo RFC 4120, một ticket có thể có flag **FORWARDABLE** để phục vụ việc chuyển tiếp xác thực; việc chuyển TGT sang một host cho phép host đó dùng danh tính người dùng để xin tickets cho các dịch vụ khác. Trong môi trường AD, **unconstrained delegation** là cấu hình rất nhạy cảm vì một server trung gian có thể nhận/use các delegated TGTs của những account được phép forward.

### Rủi ro

Nếu một web server đáng tin để delegation rộng bị compromise:
- Attacker trên server đó có thể tìm cách sử dụng delegated credentials hợp lệ cho **nhiều dịch vụ khác** trong giới hạn credentials và KDC policy.
- Phạm vi ảnh hưởng phụ thuộc **users đang xác thực tới service đó**, mức đặc quyền của họ, thời gian sống credential và khả năng lấy credential.
- Một delegated user có quyền cao có thể biến web server thành điểm trung chuyển ảnh hưởng tới nhiều hệ thống.
- Exfiltration của keytab/service key có thể gây hệ quả khác với exfiltration delegated user credentials; cần bảo vệ **cả hai**.
- Một ticket/credential còn hạn không tự hết hiệu lực chỉ vì UI browser logout.

**Điểm cốt lõi:** Unconstrained delegation trao năng lực **rộng hơn nhu cầu một backend cụ thể**. Đánh giá thường nên **loại bỏ**, thay bằng KCD/RBCD hoặc service identity.

### Không nhầm ticket flags

| Tên | Ý nghĩa sơ lược | Không được suy |
| --- | --- | --- |
| `FORWARDABLE` | KDC có thể cho phép xin credential được forward theo điều kiện | Không có nghĩa mọi server đã nhận forwarded TGT |
| `FORWARDED` | Ticket đã được phát theo hình thức forwarded | Không tự nói ứng dụng được phép gọi tất cả backend |
| `OK-AS-DELEGATE` | KDC thông báo chính sách realm coi service thích hợp nhận delegated credentials | Không tự thay app-level authorization |
| `PROXIABLE/PROXY` | Các khả năng proxy theo Kerberos RFC | Không đồng nhất Microsoft S4U hay mọi AD UI setting |
| `renewable` | Điều kiện ticket có thể renew | Không phải quyền delegation |
| `pre-authenticated` | Cho biết tiền xác thực Kerberos | Không phải MFA/authorization guarantee |

Trong Java GSS-API, một context **không tự delegated** chỉ vì service ticket có FORWARDABLE. Phía initiator phải có request/policy/credential capability tương ứng, mechanism phải hỗ trợ và context phải được thiết lập thành công.

## 6. Classic Kerberos Constrained Delegation (KCD)

KCD trong Active Directory dùng chính sách để giới hạn **frontend service account** chỉ được delegate tới **những SPN/backend service cụ thể**. Giả sử:

~~~text
Frontend service principal: HTTP/portal.example.org
Allowed backend SPNs:
  HTTP/reports-api.example.org
  CIFS/files.example.org

Not allowed:
  LDAP/dc01.example.org
  HOST/domain-controller.example.org
  MSSQLSvc/payments-db.example.org:1433
~~~

Đây là **allow-list minh họa**, không phải cấu hình AD áp dụng sẵn. Cần biết account nào giữ SPN, người nào sở hữu backend, user nào được phép delegation và authorization của backend.

### 6.1 “Use Kerberos only”

Trong mô hình classic KCD với `Use Kerberos only`, frontend có thể sử dụng **S4U2Proxy** dựa trên Kerberos evidence ticket phù hợp (thường yêu cầu forwardable theo điều kiện KDC). Việc client đã xác thực bằng Kerberos với frontend là một tiền đề quan trọng, nhưng **không tự bảo đảm** S4U2Proxy thành công: account delegation policy, target SPN, ticket flags, KDC trust và user restrictions phải cho phép.

### 6.2 “Use any authentication protocol” / Protocol Transition

Nếu frontend đã xác thực user bằng phương thức khác (ví dụ form hoặc token broker được bảo đảm) nhưng backend yêu cầu Kerberos, AD có cơ chế **protocol transition** dùng các extension S4U. Đây là một **năng lực nhạy cảm**, vì frontend có thể yêu cầu KDC phát ticket cho một user **không cần nhận trực tiếp password hay TGT của user** trong giao dịch đó.

**S4U2Self:** một service yêu cầu service ticket tới **chính nó** dưới danh tính user, theo KDC policy.

**S4U2Proxy:** service sử dụng evidence thích hợp để yêu cầu service ticket tới backend service **trong giới hạn delegation policy**.

Protocol transition không phải một checkbox Spring Boot; đó là một ranh giới **KDC/Active Directory trust**. Backend vẫn phải xác minh ticket cho chính SPN của mình và thực thi quyền user/object.

### 6.3 Hình dung KCD

~~~mermaid
sequenceDiagram
    participant U as User browser
    participant F as Frontend service
    participant K as KDC / AD
    participant B as Backend resource
    U->>F: Authentication tới HTTP/portal
    F->>K: S4U2Proxy xin ticket cho HTTP/reports-api as user
    K->>K: Kiểm tra evidence và delegation allow-list/policy
    alt Được phép
        K-->>F: Backend service ticket cho user
        F->>B: Kerberos AP-REQ as delegated user
        B->>B: Verify ticket + resource-level permissions
        B-->>F: Response theo quyền
    else Không được phép
        K-->>F: Kerberos error, không cấp backend ticket
        F-->>U: Deny/fail safely
    end
~~~

**Chú ý:** flow trên là mô hình logic. Một số classic KCD paths cần S4U2Self trước, có thể dùng existing evidence ticket ở trường hợp khác. Không giả định mọi Kerberos KDC đều hỗ trợ Microsoft S4U extension.

### 6.4 KCD giảm rủi ro nhưng không miễn nhiễm

Một frontend bị compromise vẫn có thể **mạo danh người dùng được KDC cho phép** tới các SPN nằm trong allow-list. Nếu allow-list quá rộng hoặc bao gồm backend quyền quản trị, mức độ rủi ro vẫn cao. Do đó:
- Hạn chế **tập SPNs** và service classes cần thiết;
- Hạn chế **user population** được delegate (đặc biệt privileged accounts);
- Hạn chế **ngữ cảnh nghiệp vụ** phía frontend;
- Backend thực hiện **authorization** trên từng resource/action;
- Theo dõi **KDC-issued delegated tickets** và thay đổi cấu hình delegation;
- Không coi “KCD” đồng nghĩa “không thể lateral movement”.

## 7. Resource-Based Constrained Delegation (RBCD)

**RBCD** là biến thể AD trong đó **quyền quyết định service nào có thể hành động thay user được đặt ở phía tài nguyên/backend**. Thuộc tính AD tiêu biểu:

`msDS-AllowedToActOnBehalfOfOtherIdentity`

Đây là một **security descriptor** trên object của resource service cho phép KDC đánh giá principal nào được phép delegate tới resource đó. Khác classic KCD, quyết định được quản lý qua **resource ownership/trust boundary**, đặc biệt hữu ích cho những trường hợp cross-domain theo chính sách.

| Đặc điểm | Classic KCD | RBCD |
| --- | --- | --- |
| Ai là nơi cấu hình delegation | Frontend service account, được phép tới target SPNs | Backend/resource account quyết định caller nào được phép |
| Dữ liệu AD tiêu biểu | `msDS-AllowedToDelegateTo` cho target service SPNs | `msDS-AllowedToActOnBehalfOfOtherIdentity` trên resource |
| Ủy quyền theo SPN/backend | Có | Có, nhưng enforcement thông qua resource ACL |
| Protocol transition | Cần xem KCD mode/policy | Có khác biệt quan trọng trong KDC behavior; không gán đơn giản giống classic mode |
| Rủi ro trọng tâm | Frontend account có allow-list rộng, target nguy hiểm | Ai được **ghi ACL** trên backend object, principal nằm trong ACL có đặc quyền gì |
| Kiểm toán | Thay đổi delegation list trên frontend | Thay đổi security descriptor của backend object |

Microsoft lưu ý **RBCD không dùng bit Trusted-to-Authenticate-for-Delegation làm cùng kiểu kiểm soát protocol transition như classic KCD**; quyền ủy nhiệm thuộc resource ACL và KDC extension behavior. Điều này **không có nghĩa bất kỳ service nào cũng được phép mạo danh mọi user vào mọi resource**: vẫn phải được KDC/AD cho phép theo ACL và các user/service policy. `Account is sensitive and cannot be delegated`, Protected Users, authentication policies và forest/domain trust vẫn là những ràng buộc cần đánh giá theo môi trường. **Không khẳng định chúng bảo vệ mọi đường RBCD như nhau mà không test phiên bản AD thực tế.**

### Rủi ro thiết kế RBCD

- Nếu ai đó có quyền sửa `msDS-AllowedToActOnBehalfOfOtherIdentity` trên backend object, họ có thể mở rộng danh sách principals được phép act-on-behalf.
- Nếu resource ACL cho phép một service account dùng chung hoặc principal chưa được harden, attacker compromise principal có thể thay mặt users tới resource trong phạm vi policy.
- Việc đổi quyền ghi AD object có thể tạo đường delegation mới mà đội quản trị frontend không biết.
- Cross-domain trust và ACL phức tạp làm khó review.
- RBCD vẫn yêu cầu backend thực thi authorization; ticket được KDC cấp **không chứng minh mọi hành động được phép**.

**Biện pháp:** thay đổi RBCD ACL phải được phê duyệt bởi resource owner, kiểm toán AD object modifications, tối thiểu hóa các principals trong allow-list và bảo vệ credential của những principal đó.

## 8. Bảng quyết định: khi nào cần delegation?

| Nhu cầu | Giải pháp nên xem trước | Có cần Kerberos delegation? |
| --- | --- | --- |
| Portal chỉ hiển thị dữ liệu theo quyền ở chính app | Spring authenticated principal + app authorization | **Không** |
| Portal gọi API thuộc cùng tổ chức, API hỗ trợ service auth và scoped on-behalf-of assertions | Service identity + audience-bound signed token/verified context, resource authorization | **Không nhất thiết** |
| Backend file share bắt buộc kiểm ACL Windows trên từng user | Kerberos KCD/RBCD được giới hạn tới CIFS SPN thích hợp | **Có thể** |
| Legacy SQL/SSRS backend yêu cầu Windows Integrated user auth | KCD/RBCD nếu stack hỗ trợ; xác minh SPNs và account restrictions | **Có thể** |
| Job nền dùng service account để đồng bộ dữ liệu | Service identity riêng với quyền tối thiểu | **Không dùng user delegation** |
| Frontend chỉ cần “biết user là ai” để audit | Principal identity đã được verify + audit | **Không** |
| Quản trị domain hoặc thao tác đặc quyền từ web | Không mở delegation rộng; xem privileged access workflow riêng | **Tránh** |
| App không hỗ trợ backend Kerberos và chỉ có username string | Xây boundary được xác minh hoặc điều chỉnh kiến trúc | **Không thể giả định KCD tự xảy ra** |

**Quy tắc:** Nếu yêu cầu chỉ là hiển thị thông tin/áp chính sách của portal, **đừng bật delegation**. Nếu backend **phải** nhận danh tính người dùng bằng Kerberos, chỉ bật **đúng service paths** đã được đánh giá rủi ro.

## 9. Một số rủi ro khi bật delegation quá rộng

### 9.1 Credential exposure và server compromise

Frontend trung gian chứa keytab/service keys, và tùy cơ chế có thể thấy delegated credentials. Một attacker có quyền OS/process có thể tận dụng credential còn sống hoặc truy vấn backend mà service được phép ủy quyền. Dùng service account không có interactive logon, protected keytab, secret rotation, process isolation, EDR và patching. Với AD, ưu tiên gMSA khi triển khai hỗ trợ vì giảm quản lý mật khẩu thủ công.

### 9.2 Lateral movement qua backend SPNs

Một allow-list có backend SPN không phục vụ nhu cầu của app có thể biến compromise ở portal thành khả năng kết nối backend nhạy cảm. Đặc biệt xem kỹ LDAP, CIFS/HOST trên domain controllers, SQL services quản trị và service SPNs chia sẻ. Không cần liệt kê “các SPN cho tất cả dịch vụ nội bộ” để tránh lỗi 403.

### 9.3 Principal confusion và service identity spoofing

Nếu backend tự tin `X-Authenticated-User` từ request browser hoặc proxy chưa được bảo vệ, attacker có thể giả danh user. Nếu service-to-service token được dùng thay Kerberos, token phải có **trusted issuer, signature, audience, expiry, scope, binding** và backend phải verify. Không được coi `Authentication.getName()` là một “vé” có thể chuyển nguyên sang bất kỳ API.

### 9.4 Cross-tenant account linking

Một tên như `alex` có thể trùng giữa `SALES.EXAMPLE.ORG` và `PARTNER.EXAMPLE.ORG`. Phải dùng scoped identity gồm Kerberos realm, principal, domain/tenant mapping và immutable account ID nếu có. Không xóa realm hoặc phân quyền theo username phần trước ký tự @.

### 9.5 Authorization snapshot cũ

Spring có thể tạo `GrantedAuthorities` tại thời điểm SPNEGO login. Nếu account bị khóa/đổi group sau đó, `SecurityContext` của phiên app có thể còn authorities cũ. Kerberos delegation có thể là một đường tiếp cận backend, nhưng **không thay live authorization policy/revocation**.

### 9.6 Audit mất actor gốc

Nếu backend chỉ thấy service account, cần log được chuỗi:
- Ai yêu cầu hành động (verified end-user principal);
- Frontend service identity nào thực hiện;
- Backend resource nào;
- Decision/action/tenant;
- Correlation ID, thời gian và policy version.

Không đơn giản biến mọi hành động backend thành “user thực hiện” nếu còn service trung gian. Audit phải tách **initiator**, **delegate**, **resource service**, **authorization decision**.

### 9.7 Caches, threads và connection pooling

Một `GSSCredential` hoặc JAAS Subject nhạy cảm không nên được đưa vào global singleton, shared thread-local còn sót sau request, Redis/session serialization hoặc JDBC connection pool dùng chung rồi vô ý tái sử dụng dưới user khác. Các connection pools và async jobs cần hiểu context propagation và reset identity. Không lưu user delegated credential trong cookie/JWT/session attribute rồi hy vọng “Spring tự quản lý”.

## 10. KDC có quyền cấp ticket; backend vẫn có quyền từ chối

Không được đồng nhất **authentication delegation succeeded** với **authorization succeeded**.

Ngay cả khi KDC phát service ticket cho backend dưới danh tính user:
1. Backend verify ticket dành đúng SPN/key của nó;
2. Áp domain/realm trust và local account mapping;
3. Kiểm tra account state/tenant/role/object ACL;
4. Kiểm tra quyền đối với action cụ thể;
5. Chặn request sai policy (thường 403 hoặc lỗi nghiệp vụ);
6. Audit decision.

Ví dụ:
- User có quyền **đọc** folder `/finance/reports` nhưng không được **sửa**.
- KCD được phép tới `CIFS/files.example.org`.
- Backend Windows ACL vẫn **chặn ghi file** nếu user không có quyền.

**KCD chỉ giới hạn mục tiêu có thể được xác thực thay user; nó không cấp sẵn mọi permission của backend.** Ngược lại, một backend cấp quyền quá rộng cho user vẫn có rủi ro dù KCD allow-list hẹp.

## 11. Khi SPNEGO thành công, Spring Security đã làm gì?

Với Spring Security Kerberos integration, các thành phần tiêu biểu:

| Thành phần | Vai trò |
| --- | --- |
| `SpnegoEntryPoint` | Khởi đầu HTTP Negotiate (thường 401 challenge) |
| `SpnegoAuthenticationProcessingFilter` | Nhận `Authorization: Negotiate`, tạo authentication request token |
| `KerberosServiceAuthenticationProvider` | Xác thực service ticket/SPNEGO token qua validator |
| `KerberosTicketValidator` | Tầng xác minh Kerberos service ticket theo runtime |
| `SunJaasKerberosTicketValidator` | Một implementation dùng JAAS/JGSS với SPN/keytab |
| `UserDetailsService` | Nạp local user/authorities theo principal đã xác thực |
| `Authentication / SecurityContext` | Lưu principal/authorities cho app theo HTTP security policy |

**Điều nó không tự làm:** bật AD delegation, tự thực hiện S4U2Self/S4U2Proxy, sinh backend service ticket cho mọi API, hoặc cung cấp forwarded TGT an toàn cho business service chỉ vì `Authentication.getName()` đã có.

Tài liệu Spring Kerberos nêu `KerberosServiceAuthenticationProvider` xác minh service tickets/SPNEGO tokens rồi dùng `UserDetailsService` để nạp quyền. Đó là **authN vào ứng dụng**, không phải một KCD broker tự động.

### Spring Boot dependency dạng minh họa

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // Lựa chọn Spring Security Kerberos module tương thích
    // Spring Boot/Spring Security/Jakarta Servlet của project.
    // Không chốt version độc lập khác BOM khi chưa kiểm thử.
}
~~~

Đây chỉ là **đoạn `dependencies` định hướng**, không phải `build.gradle` hoàn chỉnh. Module Spring Security Kerberos có **release/version tương thích riêng**; nếu cần `spring-security-kerberos-web` và `spring-security-kerberos-core`, chọn đúng artifact/repository theo tài liệu project, không sao chép tên class từ ví dụ năm cũ vào phiên bản hiện tại mà bỏ compile test.

## 12. Ví dụ Spring Security authorization không dựa vào delegated credential

Giả sử portal chỉ gọi API backend bằng service identity và cần kiểm soát người dùng nào được truy cập chức năng business. Không cần bật Kerberos delegation chỉ để thực thi quyền ở portal.

Ví dụ Spring Boot class:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/health", "/public/**").permitAll()
                        .requestMatchers("/reports/**")
                            .hasAuthority("REPORTS_READ")
                        .requestMatchers("/admin/**")
                            .hasAuthority("PORTAL_ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Đây chỉ là minh họa phần authorization**, dùng `httpBasic` làm một phương thức auth đơn giản trong đoạn cấu hình, **không phải cấu hình SPNEGO/Kerberos đầy đủ**. Trong app SPNEGO thật, thay `httpBasic` bằng entry point/filter/provider Kerberos đã đăng ký theo phiên bản. Mục đích là cho thấy **không có một dòng nào tự bật delegation**.

**Cần hiểu:**
- `hasAuthority` kiểm tra authorities hiện có trong Authentication, có thể stale khi group thay đổi.
- Route-level authorization chưa đủ cho từng tài liệu/file; service phải kiểm tra **ownership/tenant/ACL** ở tầng domain.
- Khi backend nhận user context qua service-to-service protocol khác, backend phải tự verify credential/context; không tin header do client tự đặt.
- Nếu backend thực sự phải nhận **Windows Kerberos user ticket**, authorization tại portal **không thay** nhu cầu KCD/RBCD.
- Với user bị khóa, cần app-local account gate/session revocation; không coi Kerberos ticket còn hạn là đảm bảo user hiện còn active.

## 13. Java GSS-API: xin delegation và kiểm tra kết quả

JDK Java 17 cung cấp API chuẩn `org.ietf.jgss.GSSContext`, `GSSCredential` và `GSSException`. Việc một ứng dụng **yêu cầu** delegation khác với việc KDC/mechanism **cho phép và thực sự cấp** delegation.

### 13.1 Phía initiator

~~~java
// Mảnh code đặt trước lần initSecContext() đầu tiên.
// Context phải được tạo với target principal đúng và GSSManager/JAAS
// credentials đã cấu hình. Không phải chương trình độc lập.
GSSContext context = /* initiator context đã cấu hình */;
context.requestMutualAuth(true);

// Chỉ đặt true nếu nghiệp vụ thực sự cần và policy cho phép.
// Với normal SPNEGO login không cần delegation, đặt false.
context.requestCredDeleg(false);

// Thực hiện initSecContext(...) đến khi context established.
~~~

**Điểm chính:** `requestCredDeleg(boolean)` được gọi **ở initiator trước lần initSecContext đầu**. Khi user/browser không nên delegate, hãy **không yêu cầu**. Một số sản phẩm/browser có policy quyết định có cho phép forwarding tới host tin cậy hay không; không thể ép browser toàn công ty tự chuyển TGT chỉ bằng Java code phía server.

### 13.2 Phía acceptor

~~~java
// Mảnh code chỉ hợp lệ trên acceptor context sau khi established.
// Không gọi getDelegCred() trước khi acceptSecContext hoàn tất.
if (context.isEstablished() && context.getCredDelegState()) {
    GSSCredential delegated = context.getDelegCred();
    if (delegated != null) {
        try {
            // Chỉ dùng trong request/service được cấp phép.
            // Không cache globally, không serialize/ghi log.
        } finally {
            delegated.dispose();
        }
    }
}
~~~

**Cần import:**

~~~java
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSCredential;
import org.ietf.jgss.GSSException;
~~~

Hai mảnh code là **minh họa JGSS** không có `main()`, không biên dịch độc lập vì chưa tạo context/credentials và có thể phải xử lý checked exceptions. Không phải API Spring Security trực tiếp. Thực tế:
- `getCredDelegState()` chỉ cho kết quả đáng tin khi context đã established.
- `getDelegCred()` gọi ở acceptor, có thể trả `null` nếu không có credential.
- Một GSSCredential được delegated không mặc nhiên là KCD S4U ticket; **forwarded credentials và AD S4U delegation là hai đường khác nhau**.
- Không dùng GSSCredential ở backend không được cho phép chỉ vì Java có object.
- Nếu không nhận delegated credentials, hãy **không bypass** bằng cách giả username hoặc gửi service keytab như user.

### GSS-API security status không thay KDC/AD policy

`getCredDelegState() == true` cho biết context thương lượng delegation, không tự chứng minh backend target cụ thể đã được phép theo KCD/RBCD. KDC policy, GSS mechanism, ticket flags, credentials, SPNs và backend authorization phải kiểm tra **tại chính hop backend**.

## 14. Spring Security Kerberos filter không phải nơi giữ TGT toàn cục

Một số ứng dụng thấy `Authentication.getPrincipal()` và muốn đưa toàn bộ Kerberos token vào `SecurityContext` hoặc session để gọi backend sau này. Điều này tạo vấn đề:
- User credential có thể vô tình bị serialize tới Redis/Spring Session hoặc log.
- Session id bị đánh cắp có thể tạo điều kiện sử dụng delegated credentials.
- Multi-node session replication có thể mang security context có credential sang host khác.
- Credential có lifecycle khác HttpSession; hết hạn và refresh cần chính sách riêng.
- Connection pooling có nguy cơ dùng sai principal giữa requests.
- Khó đảm bảo dispose credential và giới hạn lifetime.

**Đề xuất:** giữ Spring Authentication chứa **identity đã xác minh** và authorities cần thiết; giữ mọi credential nhạy cảm trong vùng tin cậy ngắn hạn, scoped theo request/operation, không đưa vào browser/session store. Nếu phải làm protocol transition/KCD cho backend, dùng thư viện/integration được đánh giá đúng version và thiết kế credential management riêng; không tự “gắn TGT vào Authentication object”.

## 15. Active Directory: nguyên tắc hạn chế delegation

Với môi trường AD, baseline an toàn gồm:

1. **Không cấp Unconstrained Delegation** nếu không có yêu cầu đặc biệt được phê duyệt.
2. Mỗi frontend service có **service account riêng** (ưu tiên gMSA khi phù hợp), không dùng Domain Admin hoặc account quản trị chung.
3. Đăng ký **SPNs chính xác**, tránh duplicated/misregistered SPNs.
4. Nếu cần KCD, allow-list **chỉ backend SPNs thực sự cần**.
5. Đừng cấu hình `Use any authentication protocol` nếu không có nhu cầu protocol transition và threat model rõ.
6. RBCD ACL trên backend resource object chỉ chứa các **delegate principals được ủy quyền**, quyền sửa ACL được hạn chế.
7. Không để frontend service account có đặc quyền ghi AD objects/KCD/RBCD khác không cần thiết.
8. Dùng `Account is sensitive and cannot be delegated` cho accounts đặc quyền theo chính sách, và nhóm **Protected Users**/authentication policies nếu môi trường hỗ trợ.
9. Không cho service nhận user credentials/cookies/tokens vượt quá scope nghiệp vụ.
10. Bảo vệ keytabs, service passwords, krb5.conf, JAAS configs và runtime secrets bằng ACL/secret manager; không commit vào Git.
11. Xem xét lifetime/renewability của Kerberos credentials, quản lý time sync.
12. Tách network giữa frontend, KDC, backend và chỉ mở cổng cần thiết.
13. Đặt quy trình phê duyệt thay đổi delegation thuộc **security/identity team và resource owner**.
14. Có monitoring AD object modifications và KDC service-ticket issuance.
15. Test negative paths cho user nhạy cảm, backend ngoài allow-list và protocol transition không được phép.

**Lưu ý:** RBCD/AD S4U có nhiều điều kiện version/trust; một cấu hình hợp lệ trên AD này chưa chắc hoạt động trên AD/forest khác. Không giảm bảo vệ privileged users chỉ để vượt lỗi KDC.

## 16. Protected Users và tài khoản “nhạy cảm không được ủy quyền”

Trong AD, một số account có yêu cầu ngăn delegation hoặc dùng authentication policies nghiêm ngặt:
- User/computer account option **“Account is sensitive and cannot be delegated”** ngăn những đường delegation theo chính sách AD/KDC được hỗ trợ.
- **Protected Users** group áp dụng tập chính sách tăng cường, bao gồm các hạn chế liên quan delegated credentials/NTLM hoặc Kerberos lifetime theo môi trường.
- Authentication Policies và Authentication Policy Silos có thể hạn chế **user có thể xác thực đến đâu và theo cách nào**.
- Đối với privileged identities (Domain Admin, break-glass accounts), không dựa vào web delegation để chạy automation; thiết kế admin workflows có least privilege.
- Khi account bị khóa hoặc quyền bị thu hồi, session app có thể vẫn tồn tại; cần live account gating, token/session revocation và bảo vệ backend.

### Sai lầm thường gặp

Thấy S4U2Proxy từ chối khi user thuộc nhóm Protected Users, đội vận hành đổi account thành **không được bảo vệ** hoặc bật unconstrained delegation. Điều này có thể làm “double hop hoạt động” nhưng **mở rộng rủi ro**. Cách đúng là xác định use case có cần act-as-user không, chọn service identity hoặc KCD/RBCD với user/target policy phù hợp, và xin phê duyệt ngoại lệ nếu thực sự cần.

## 17. RBCD: ai được phép sửa backend resource object?

Một kiến trúc RBCD nên ghi rõ:

~~~text
Resource:    Backend HTTP/reports-api
AD object:   service/computer account sở hữu backend SPN
Owner:       Backend security team
Allowed:     gMSA/service principal của portal được duyệt
Not allowed: tài khoản service dùng chung, domain users,
             service principals không thuộc workload
Control:     AD ACL, change review, protected backups, audit
~~~

**Nguyên tắc:**
- Người có quyền ghi `msDS-AllowedToActOnBehalfOfOtherIdentity` hoặc điều khiển backend object là người có thể làm thay đổi trust boundary này.
- Không cho developer pipeline quyền sửa AD delegation ACL trên toàn OU khi nó chỉ quản lý một service.
- Không tin một username trong LDAP object displayName làm delegate principal; phải dùng security principal/SID đúng.
- Kiểm tra quan hệ domain/forest trust, SPN ownership và backend authentication policy.
- Audit những **đối tượng được thêm/xóa** khỏi ACL, thay vì chỉ ghi “cấu hình RBCD đã đổi”.
- Đảm bảo không có quyền tạo computer/service account rộng dẫn tới unintended RBCD relationships theo chính sách AD.
- RBCD không thay backend authorization, cũng không phải mô hình truyền toàn bộ TGT cho frontend.

## 18. Phân biệt GSS Credential Delegation với S4U-based KCD

Hai đường có thể dễ bị nhập nhằng:

| Đặc điểm | GSS credential forwarding | AD KCD/RBCD với S4U |
| --- | --- | --- |
| Credential nguồn | Initiator/user đồng ý/chính sách cho phép forward credential | KDC phát backend ticket cho service theo S4U evidence/policy |
| Có cần user gửi delegated TGT cho frontend? | Có thể có trong Kerberos forwarding | **Không nhất thiết**, S4U tránh yêu cầu forwarded TGT trong nhiều kịch bản |
| Java API điển hình | `GSSContext.requestCredDeleg`, `getDelegCred` | Tùy SSPI/AD S4U library và server integration |
| Vị trí kiểm soát | User/client/browser policy, KDC flags, target service trust | AD KCD list hoặc RBCD resource ACL, user restrictions |
| Phạm vi rủi ro | Có thể rộng theo credential được forward | Hạn chế target SPNs; vẫn nguy hiểm nếu list/ACL sai |
| Spring SPNEGO filter tự xử lý? | Không mặc định expose/đảm bảo delegated credential | **Không tự triển khai S4U2Self/S4U2Proxy** |
| Yêu cầu backend | Service ticket đúng SPN và authorization | Service ticket đúng SPN và authorization |
| Khi không cần thiết | Không bật | Không cấu hình KCD/RBCD |

**Không có một dòng `http.saml2Login()</BT>, `oauth2Login()</BT> hay `spnegoFilter.setDelegation(true)` chuẩn nào tự cấp quyền AD RBCD.** Các stack này là những protocol integrations khác nhau.

## 19. Giới hạn delegation theo đủ bốn chiều

Chỉ cấu hình target SPN allow-list là cần thiết nhưng chưa đủ. Một policy tốt nên xét:

### 19.1 Ai được delegate?

- Frontend service account/hostname/SPN đã phê duyệt;
- User principal/realm/tenant nằm trong đối tượng được phép;
- Không phải privileged/protected account;
- Có account status enabled và authentication assurance phù hợp;
- Đúng chain của request user, không lấy user từ query parameter.

### 19.2 Delegation tới đâu?

- Chỉ backend services/SPNs được phê duyệt;
- Không cho bất kỳ host từ `Host` header hoặc URL user input;
- Tách môi trường prod/staging; không cross-realm nếu chưa thẩm định;
- Dịch vụ backend phải verify SPN/key và authorization.

### 19.3 Được làm gì?

- `READ_REPORT` khác `APPROVE_PAYMENT`;
- Tách quyền service delegation (có ticket backend) và quyền app/business action;
- Kiểm tra resource-level ACL/tenant/ownership;
- Có thể giới hạn chỉ GET/read-only theo ứng dụng, nhưng không coi HTTP method đủ thay backend ACL;
- Không trao credential cho job nền không có actor hợp lệ.

### 19.4 Trong bao lâu và bao nhiêu lần?

- Credential lifetime theo KDC policy;
- No global cache, không lưu trong HttpSession/log;
- Dispose sớm sau request;
- Version/revocation event cho quyền business;
- Reauthentication/step-up cho hành động nhạy cảm;
- Audit rate, blast radius và khả năng revoke.

**Policy dạng tư duy:**

~~~text
permitDelegation =
    verifiedFrontend
    AND trustedKerberosPrincipal
    AND accountEnabled
    AND notProtectedOrPrivileged
    AND targetSpnInAllowList
    AND businessActionAllowed
    AND backendObjectAuthorizationPasses
    AND delegationMethodApproved
    AND sessionAndCredentialNotExpired
~~~

Đây là **policy ở cấp kiến trúc**. Các điều kiện được kiểm ở các lớp khác nhau: KDC/SPN policy, portal business authorization và backend resource authorization. Không thể dồn hết vào một boolean Spring filter rồi nghĩ KDC sẽ tự tuân theo.

## 20. Java 17 độc lập: mô phỏng một delegation policy tối thiểu

Ví dụ này **không lấy Kerberos ticket thật**, không gọi KDC, không dùng JAAS/GSS/AD và **không thực hiện impersonation**. Nó chỉ mô hình hóa quyết định **có nên cho phép một yêu cầu act-on-behalf-of** khi frontend đã biết principal được xác minh, target SPN và thao tác business.

Mục tiêu là thực hành **deny-by-default, target allow-list, protected account ban, action/tenant checks**.

Tệp `DelegationBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public final class DelegationBoundaryDemo {

    record User(
            String principal,
            String tenant,
            boolean enabled,
            boolean protectedAccount,
            Set<String> permissions) {
    }

    record Request(
            String targetSpn,
            String action,
            String tenant,
            boolean verifiedCaller) {
    }

    private static final String REPORTS_SPN =
            "HTTP/reports-api.example.org";
    private static final String FILES_SPN =
            "CIFS/files.example.org";

    private static final Map<String, Set<String>> ALLOWED =
            Map.of(
                REPORTS_SPN, Set.of("READ_REPORT"),
                FILES_SPN, Set.of("READ_FILE"));

    static String authorize(User user, Request request) {
        if (user == null || !request.verifiedCaller()) {
            return "DENY_UNVERIFIED";
        }
        if (!user.enabled() || user.protectedAccount()) {
            return "DENY_ACCOUNT";
        }
        if (!user.tenant().equals(request.tenant())) {
            return "DENY_TENANT";
        }
        Set<String> actions = ALLOWED.get(request.targetSpn());
        if (actions == null || !actions.contains(request.action())) {
            return "DENY_TARGET_OR_ACTION";
        }
        if (!user.permissions().contains(request.action())) {
            return "DENY_PERMISSION";
        }
        return "ALLOW_POLICY_ONLY";
    }

    public static void main(String[] args) {
        User reader = new User(
                "reader@EXAMPLE.ORG", "finance",
                true, false, Set.of("READ_REPORT"));
        User admin = new User(
                "admin@EXAMPLE.ORG", "finance",
                true, true, Set.of("READ_REPORT", "READ_FILE"));

        Request readReports = new Request(
                REPORTS_SPN, "READ_REPORT", "finance", true);
        Request unknownTarget = new Request(
                "LDAP/dc01.example.org", "READ_REPORT",
                "finance", true);
        Request elevatedAction = new Request(
                REPORTS_SPN, "APPROVE_PAYMENT", "finance", true);
        Request crossTenant = new Request(
                REPORTS_SPN, "READ_REPORT", "hr", true);
        Request unverified = new Request(
                REPORTS_SPN, "READ_REPORT", "finance", false);

        System.out.println("Normal read: "
                + authorize(reader, readReports));
        System.out.println("Unknown backend: "
                + authorize(reader, unknownTarget));
        System.out.println("Action not permitted: "
                + authorize(reader, elevatedAction));
        System.out.println("Protected admin: "
                + authorize(admin, readReports));
        System.out.println("Cross-tenant: "
                + authorize(reader, crossTenant));
        System.out.println("Unverified caller: "
                + authorize(reader, unverified));
    }
}
~~~

Chạy:

~~~bash
javac DelegationBoundaryDemo.java
java DelegationBoundaryDemo
~~~

Stdout **chính xác**:

~~~text
Normal read: ALLOW_POLICY_ONLY
Unknown backend: DENY_TARGET_OR_ACTION
Action not permitted: DENY_TARGET_OR_ACTION
Protected admin: DENY_ACCOUNT
Cross-tenant: DENY_TENANT
Unverified caller: DENY_UNVERIFIED
~~~

### Vì sao chỉ có `ALLOW_POLICY_ONLY`?

Chương trình **không cấp Kerberos service ticket**. Nó chỉ cho biết **policy của ứng dụng** không chặn use case đó. Trong production còn cần:
1. KDC cho phép delegation ở AD/Kerberos;
2. Target SPN tồn tại/được đăng ký duy nhất và gắn đúng backend account;
3. GSS/SSPI/AD S4U integration thực sự nhận được backend ticket;
4. Backend xác minh ticket và resource-level permissions;
5. Credentials không bị lộ, ghi audit và lifecycle cleanup.

Do đó nhãn `ALLOW_POLICY_ONLY` được chọn có chủ đích để người học **không nhầm quyết định Java với cấp quyền từ KDC**.

### Rủi ro của code demo nếu dùng như production

- Dùng `verifiedCaller</BT> Boolean do caller truyền vào **không an toàn** trong API thật. Production phải sinh trạng thái từ một **authentication context đã xác minh**, không nhận từ JSON/query.
- Policy trong `static Map` là illustrative, không tự đồng bộ AD/tenant permission changes.
- Không có cryptographic binding/credential lifetime/KDC trust validation.
- `principal` trong record chỉ là text; không chứng minh Kerberos login đã diễn ra.
- Nên đặt policy ở backend/service boundary có test, không coi frontend UI là quyền quyết định.
- Không có database/IO và không hoạt động thay cho `KerberosTicketValidator`.

## 21. Mã Spring theo mẫu policy ở business boundary

Một ứng dụng có thể đặt policy ở một Spring-managed service để kiểm tra **hành động**, không chỉ `@PreAuthorize("isAuthenticated()")`.

Ví dụ:

~~~java
package com.example.portal;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportsService {

    @PreAuthorize("hasAuthority('REPORTS_READ')")
    public String readReport(String reportId) {
        // Trong production:
        // 1. Validate reportId/tenant ownership
        // 2. Check current account/permission state
        // 3. Use approved backend authentication/delegation
        // 4. Audit subject, target, decision
        return "Report ID: " + reportId;
    }
}
~~~

Bật method security:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

**Đây là các class trong Spring project, không có `main()`; không chạy `javac` độc lập.** Mẫu `@PreAuthorize` chỉ check authority snapshot. Nó **chưa triển khai Kerberos KCD** và chưa kiểm quyền trên report ID thực. Trong production phải có authorization manager/live account gate, object ACL và backend ticket handling riêng.

### Khi backend chỉ có Windows Integrated Authentication

Nếu backend bắt buộc Windows ACL theo user:
- Thiết kế đường KCD/RBCD với AD team;
- Chọn implementation/service account và target SPNs;
- Không giả lập user bằng `X-User` header;
- Xác minh trên tích hợp thật rằng backend thấy đúng user principal;
- Chặn user/service không được phép ở KDC/backend;
- Không “sửa” bằng cách dùng một Domain Admin service account cho toàn bộ truy vấn.

## 22. Khi frontend dùng service identity thay vì user delegation

Một lựa chọn thiết kế là **on-behalf-of application authorization**:
1. Browser đăng nhập portal bằng SPNEGO.
2. Portal xác minh principal và current permissions.
3. Portal gọi backend bằng **mTLS/service principal/OAuth2 client credentials** hoặc mechanism phù hợp.
4. Portal truyền một **signed, short-lived, audience-bound** user context/token nếu backend cần user-scoped authorization.
5. Backend xác minh signature, issuer, audience, expiry, scope, calling service và policy, không tin raw headers.
6. Backend áp object-level access và audit actor + service.

**Ưu điểm:** không trao rộng credential Kerberos của user cho frontend. **Giới hạn:** đây là một **hợp đồng ứng dụng**, không đồng nghĩa backend Windows file share tự hiểu OIDC/JWT để áp ACL. Nếu backend chỉ hỗ trợ Kerberos user authentication, vẫn có thể cần KCD hoặc kiến trúc file access khác.

Các điểm phải làm đúng:
- Token không được tạo từ username người dùng tùy nhập;
- Token audience chỉ backend cần;
- Scope ngắn/hành động cụ thể, hết hạn ngắn;
- Chặn confused-deputy khi frontend gọi target do user chọn;
- Backend kiểm tra service identity độc lập với user context;
- Không dùng shared “superuser API key” lâu dài không audit.

## 23. Nguyên tắc ngăn confused-deputy

**Confused deputy** xảy ra khi một service có quyền truy cập backend sử dụng quyền đó **theo yêu cầu không được xác thực/ủy quyền của bên khác**.

Ví dụ portal có quyền đọc file share và cung cấp API:

~~~text
GET /download?target=\\files.example.org\secret\payroll.xlsx
~~~

Nếu portal chỉ dùng backend credential để đọc **bất kỳ target path nào client gửi**, người dùng không có quyền vào payroll vẫn có thể lợi dụng quyền của portal để tải file.

Giảm rủi ro:
1. Không chấp nhận arbitrary backend hostname/SPN/path từ client.
2. Dùng **resource ID** server-side map tới danh mục được cho phép.
3. Kiểm tra user tenant, ownership, permissions cho **từng tài nguyên**.
4. Kiểm tra service target allow-list trước khi xin backend credential.
5. Kết nối backend qua TLS/mutual auth phù hợp.
6. Tránh wildcard service account permissions.
7. Audit user actor và service delegate.
8. Với high-risk actions, kiểm tra lại quyền sát thời điểm commit.

**KCD không tự ngăn confused-deputy** nếu service được phép delegate tới backend nhưng chính ứng dụng không kiểm tra user có được yêu cầu truy cập tài nguyên cụ thể hay không.

## 24. SPN và keytab là một phần của trust boundary

**SPN (Service Principal Name)** cho phép KDC chọn account/key phù hợp với dịch vụ. Ví dụ:
- `HTTP/portal.example.org` — frontend service;
- `HTTP/reports-api.example.org` — backend HTTP API;
- `CIFS/files.example.org` — file service;
- `MSSQLSvc/sql.example.org:1433` — SQL Server service trong môi trường tương ứng.

Cần bảo đảm:
- SPN đăng ký đúng account/service, không trùng;
- Browser dùng **canonical host** đúng SPN, proxy/DNS phù hợp;
- Frontend có keytab/credentials đúng SPN để accept ticket;
- Backend chỉ accept ticket đúng SPN/identity của nó;
- GMSA/service account credential quyền tối thiểu;
- TLS/channel binding/Extended Protection nếu stack hỗ trợ, không tắt để chữa lỗi mà chưa tìm nguyên nhân;
- Cross-realm trust rõ và KDC time synchronization;
- Không để user quyết định targetSPN qua URL để thực hiện delegation ngoài allow-list.

### Keytab không phải user credential forwarding

Keytab của `HTTP/portal` cho phép service xác thực Kerberos service tickets phát **cho portal**. Nó **không tự cấp quyền mạo danh mọi user tới backend**. Nếu một app thấy username và có keytab, chưa thể tự ký ticket Kerberos cho backend. KDC vẫn có vai trò phát ticket theo policy.

## 25. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách điều tra an toàn |
| --- | --- | --- |
| Browser SPNEGO login thành công nhưng backend 401 | Chưa có delegation credential/service ticket cho target; backend auth config | Check target SPN và KDC policy, không copy Negotiate token |
| GSS context cho `getCredDelegState=false` | Initiator không request/policy không cho, mechanism không hỗ trợ | Browser/SSPI GSS policy, flags, KDC; **không ép user delegate** |
| S4U2Proxy bị KDC từ chối | Frontend account, evidence ticket, user sensitivity, target SPN policy sai | Check AD KCD/RBCD settings, user restrictions và KDC event |
| KCD tới một backend được, backend khác không | SPN allow-list hoặc target service account khác | So exact target SPN, account ownership |
| RBCD hoạt động ngoài dự kiến | ACL ở backend resource object quá rộng | Review `msDS-AllowedToActOnBehalfOfOtherIdentity`, delegation principals |
| Backend thấy service account thay vì user | Không có user delegation, chỉ dùng service credential | Xác định kiến trúc: service identity có cần user-context không |
| Backend thấy sai user sau nhiều requests | Thread/Subject/connection pooling leak hoặc mapping sai | Audit identity scopes, reset contexts/credentials |
| Browser Negotiate rơi sang NTLM | KDC/SPN/browser policy/clock/trust | Confirm Kerberos mechanism, không tự suy có delegation |
| SPNEGO 401 loop | SPN/keytab mismatch, browser allow-list, channel binding, time skew | Check safe configs, không disable channel binding |
| User privileged không delegate được | Account sensitive/Protected Users/auth policy | Không giảm protection; thiết kế privileged workflow khác |
| Kerberos ticket hợp lệ nhưng backend 403 | Resource-level ACL/business authorization | Check backend permissions, không tăng KCD target list |
| Spring Authentication role cũ | Authorities được nạp lúc login chưa refresh | Live account/permission checks, session invalidation |
| KDC service tickets tăng bất thường | Delegation misuse, policy change hoặc load spike | Triaging 4769 và service/actor/target |
| App crash/restart làm mất forwarded credential | Credential lifecycle/process memory | Không cache globally; thiết kế auth strategy phù hợp |
| Service account được cấp Domain Admin để “chữa lỗi” | Sai thiết kế blast radius | Least privilege và tách service identity |

Không tiết lộ ticket, keytab, raw Authorization header, PAC hoặc password qua support logs.

## 26. Test plan an toàn trước production

### Test A — SPNEGO authentication, delegation disabled

1. Dùng user test domain hợp lệ, browser gửi SPNEGO ticket cho `HTTP/portal.example.org`.
2. Spring Kerberos provider nhận diện đúng user/realm.
3. Portal route chỉ đọc dữ liệu app-local hoạt động.
4. Kiểm tra **không** có delegated user credential khi flow không yêu cầu.
5. Backend call phải dùng service identity được định nghĩa hoặc bị từ chối; **không âm thầm giả danh user**.

**Pass:** login đúng nhưng không cấp delegation “miễn phí”.

### Test B — KCD chỉ một backend

1. Service account portal được cấu hình KCD/RBCD đến `HTTP/reports-api.example.org` theo AD test policy.
2. User không thuộc nhóm nhạy cảm có quyền READ_REPORT.
3. Portal gọi reports backend với delegated user identity theo implementation được phê duyệt.
4. Backend verify đúng user, target SPN và resource permission.
5. Cùng user yêu cầu kết nối `LDAP/dc01.example.org`, policy/KDC/app phải deny.

**Pass:** backend cần thiết được phép, target ngoài allow-list bị chặn.

### Test C — Account có cờ nhạy cảm/Protected Users

1. Dùng tài khoản test được đặt policy không được delegate.
2. Login SPNEGO vẫn có thể hoạt động theo domain policy.
3. Delegation request phải không vượt cơ chế protection tương ứng.
4. Không tự đổi cờ/nhóm account để “test pass”.
5. Backend fallback phải fail closed, không dùng superuser service account thay thế.

### Test D — Protocol transition

1. Chỉ chạy trong AD test realm có policy rõ.
2. Frontend xác thực user bằng một flow được phê duyệt.
3. Thử use case S4U2Self/S4U2Proxy qua implementation có hỗ trợ.
4. Backend đúng SPN và user policy cho phép: success.
5. Với target ngoài allow-list/không có quyền: deny.
6. Không mặc định “Use any authentication protocol” cho mọi service.

### Test E — RBCD ACL

1. Resource owner kiểm tra backend object và allowed delegate principals.
2. Service account không có trong ACL: không được dùng làm delegate.
3. Chỉ account test được phê duyệt có quyền cho target.
4. Đổi ACL qua process change control, kiểm tra audit.
5. Không dùng tài khoản thật, không mở quyền ghi AD object trên OU rộng.

### Test F — Thread/connection pool identity isolation

1. User A được phép READ_REPORT, user B không có quyền.
2. Tạo hai concurrent requests đến portal rồi backend.
3. Backend không bao giờ thấy context A khi xử lý B.
4. Credential per-request được dọn/dispose, không còn trong session store.
5. Background jobs không dùng lại user identity không còn request.

### Test G — Account revocation

1. User login và được phép đọc.
2. IAM khóa account/thu hồi READ_REPORT.
3. Request mới/action nhạy cảm bị từ chối theo SLA policy.
4. Không coi Kerberos ticket còn hạn là bằng chứng account vẫn enabled.
5. Nếu có backend long-lived connection, kiểm tra revocation policy riêng.

### Test H — Wrong SPN, lost KDC, time skew

1. Dùng wrong target SPN trong lab, phải fail safely.
2. Gây KDC outage hoặc network policy failure, không “fail open”.
3. Kiểm tra log không in service ticket/keytab.
4. Test NTP/time skew có thể gây auth errors; không giảm clock validation quá rộng.
5. Trả error thân thiện và alert vận hành.

## 27. Monitoring: những dấu hiệu cần quan sát

Trên AD/KDC, tùy policy audit:
- **4768**: TGT được yêu cầu, giúp quan sát Kerberos authentication service events.
- **4769**: Kerberos **service ticket** được yêu cầu; có thể dùng để kiểm tra bất thường ở target SPNs, users và thời điểm phát ticket.
- **4771**: Kerberos pre-authentication failed; dùng theo mục đích cụ thể, không tự là delegation abuse.
- **4624**: Logon events tại target host, có thể cung cấp logon type/context.
- **5136**: AD Directory Service object modified, hữu ích nếu audit AD delegation attribute/ACL changes được bật.
- EDR/security tooling và backend logs kết nối ticket issuance với actual resource actions.

**Không suy từ một event 4769 đơn lẻ rằng đã có compromise**. Kerberos được dùng nhiều trong môi trường Windows; cần baseline workload, allow-list expected SPNs và service identities.

Các log application nên có:
- Correlation ID không phải raw ticket;
- Frontend service alias, backend SPN alias;
- Trusted initiator principal scoped theo realm/tenant (đã giảm dữ liệu cá nhân);
- Decision `DENY/ALLOW_POLICY_ONLY`;
- Lý do dạng enum `NO_DELEGATION_NEEDED`, `TARGET_NOT_ALLOWED`, `USER_PROTECTED`, `BACKEND_DENIED`;
- KDC error category không chứa bí mật;
- Policy version và timing;
- Alert khi delegation allow-list/RBCD ACL thay đổi, service principal account bị sửa hoặc service ticket requests bất thường.

**Không log:** raw Kerberos TGT, AP-REQ/SPNEGO token, keytab, passwords, PAC bytes, GSSCredential, complete Windows access token.

## 28. Threat model trước–sau cho một portal báo cáo

### Trước khi hardening

- `portal.example.org` dùng shared service account quyền rộng.
- Account được bật unconstrained delegation để “giải quyết double hop”.
- Web app nhận username từ authenticated session rồi cho user chỉ định backend path.
- Backend file share cấp nhiều quyền cho service account.
- Service logs chứa raw `Authorization: Negotiate`.
- Kịch bản compromise web server làm phạm vi rủi ro lan nhiều hệ thống.

### Sau khi hardening

1. Tách service account/gMSA portal, chỉ cấp quyền cần.
2. Tắt unconstrained delegation.
3. Quyết định: nếu backend API hỗ trợ scoped app token, dùng service identity + signed on-behalf-of context; nếu cần native Windows ACL, chọn KCD/RBCD tới **đúng backend SPNs**.
4. Đánh dấu privileged users không được delegate theo AD policy.
5. Backend áp resource ACL ngay cả khi delegated user Kerberos login thành công.
6. Portal mapping resource IDs server-side, không nhận arbitrary target URL/path.
7. Không lưu delegated credentials trong Spring session, logs, Redis hoặc connection pool dùng chung.
8. Theo dõi service tickets 4769, delegated principals và AD ACL modifications.
9. Test denied target, protected user, concurrent request và session revocation.
10. Có rollback plan khôi phục service access mà không mở wildcard delegation.

**Kết quả kỳ vọng:** portal có thể đọc báo cáo theo đúng người dùng/nhu cầu mà không nhận năng lực hành động thay user ở những backend không liên quan.

## 29. Checklist triển khai

- [ ] Đã mô tả rõ **tại sao** cần user-specific backend Kerberos authentication.
- [ ] Nếu có thể dùng app-local authorization hoặc service identity, **không bật delegation**.
- [ ] Đã phân biệt authentication, local impersonation và network credential delegation.
- [ ] Không nhầm HTTP `Authorization: Negotiate` với quyền forward user TGT.
- [ ] SPNEGO đã thực sự chọn Kerberos mechanism; không chỉ nhìn header Negotiate.
- [ ] Dùng Kerberos service principal/SPN/keytab đúng account, không trùng SPN.
- [ ] Unconstrained delegation bị loại bỏ hoặc có exception/mitigation được duyệt.
- [ ] Classic KCD target allow-list chỉ chứa backend SPNs bắt buộc, không wildcard.
- [ ] Nếu dùng S4U protocol transition, đã xét user policy và phạm vi tin cậy.
- [ ] RBCD ACL ở backend resource object được resource owner phê duyệt và audit.
- [ ] Không cho CI/CD/developer role quyền sửa AD delegation trên phạm vi rộng.
- [ ] Privileged users được hạn chế delegation qua Protected Users/sensitive flags khi phù hợp.
- [ ] Service account/gMSA được harden, keytab/password không nằm trong source code.
- [ ] Backend verify Kerberos ticket hoặc service-to-service token có đúng audience/issuer.
- [ ] Backend thực thi resource ACL/business authorization, không chỉ thấy username là allow.
- [ ] Có chính sách theo user, tenant, action, target SPN, TTL và reauthentication.
- [ ] Mọi input `target URL/SPN/resource path` được allow-list/resolve server-side.
- [ ] Không tin `X-User`, `isAdmin=true` hay `verifiedCaller=true` từ browser.
- [ ] Không lưu GSSCredential/TGT/service tickets vào HttpSession/Redis/logs.
- [ ] Thread/async/connection pool không làm lộ security context user khác.
- [ ] Negative tests cho target ngoài allow-list, protected accounts, wrong SPN, KDC outage, cross-tenant, replay/context leakage đã chạy.
- [ ] Live account/permission changes vẫn được enforce; Kerberos ticket chưa hết hạn không được xem là quyền vĩnh viễn.
- [ ] Có audit KDC 4769/AD 5136 và change control delegation policies.
- [ ] Có kế hoạch rollback an toàn khi backend không hỗ trợ delegation.
- [ ] Thử việc không bật delegation trong môi trường chuẩn, xác nhận không có nhu cầu không cần thiết.

## 30. Bài tập và đáp án

**Câu 1.** Browser dùng Kerberos xác thực thành công với Spring portal. Portal có tự động nhận user TGT để gọi file server không?

**Đáp án:** không. SPNEGO service ticket xác thực tới portal. Forwarded credentials hoặc KCD/RBCD là cơ chế **riêng**, có KDC/client/AD policy.

**Câu 2.** Backend chỉ cần biết user nào gọi API, không yêu cầu Windows ACL. Có nhất thiết bật unconstrained delegation không?

**Đáp án:** không. Xem service identity + signed scoped on-behalf-of context với backend validation, hoặc app-local authorization.

**Câu 3.** Vì sao chỉ nhìn `Authentication.getName()` chưa đủ để gọi backend “as user”?

**Đáp án:** username string không phải Kerberos credential, không được KDC xác minh ở backend và có thể bị nhầm realm/tenant.

**Câu 4.** KCD cho phép `HTTP/reports-api` nhưng không cho `LDAP/dc01`. User yêu cầu truy cập LDAP thì sao?

**Đáp án:** phải từ chối theo app policy và/hoặc KDC target SPN restrictions; không mở LDAP target chỉ để tránh lỗi.

**Câu 5.** Unconstrained delegation rủi ro hơn KCD ở đâu?

**Đáp án:** scope delegated credentials có thể rộng qua nhiều services. Nếu frontend bị compromise, blast radius lớn hơn nhu cầu một backend được chọn.

**Câu 6.** S4U2Self và S4U2Proxy làm gì?

**Đáp án:** S4U2Self giúp service xin ticket cho **chính service đó** trong danh tính user theo policy; S4U2Proxy xin ticket tới **backend service** dựa trên evidence và delegation policy.

**Câu 7.** RBCD permission được lưu ở đâu?

**Đáp án:** ở resource/backend account security descriptor, tiêu biểu là AD attribute `msDS-AllowedToActOnBehalfOfOtherIdentity`, không phải chỉ frontend list.

**Câu 8.** “RBCD cho protocol transition” có nghĩa bất kỳ service nào muốn giả danh user tới backend cũng được không?

**Đáp án:** không. Backend ACL/KDC policies phải cho phép; còn account restrictions và authorization ở backend. RBCD không phải wildcard.

**Câu 9.** `getCredDelegState()</BT> trả `false` thì có nên tự dùng service account admin để gọi backend như user không?

**Đáp án:** không. Cần xem policy/capability, hoặc đổi kiến trúc; không bypass bằng quyền admin hoặc fake username.

**Câu 10.** User được delegate tới CIFS nhưng không có ACL đọc file X. Kết quả?

**Đáp án:** backend Windows file ACL phải từ chối file X. KDC ticket issuance không cấp quyền trên từng file.

**Câu 11.** Vì sao không lưu GSSCredential trong HttpSession?

**Đáp án:** credential nhạy cảm có thể bị serialize/leak hoặc được dùng ngoài lifetime/policy, có thể gây cross-user context leakage và tăng blast radius.

**Câu 12.** Protected Users account không delegate được. Cách chữa tốt có phải bỏ Protected Users group?

**Đáp án:** không. Giữ privileged identity protection; cân nhắc service identity hoặc KCD path khác được duyệt, không tự hạ chính sách.

**Câu 13.** Frontend có quyền gọi report API nhưng cho phép user tự chọn URL backend. Nguy cơ?

**Đáp án:** confused deputy, SSRF hoặc delegation tới target ngoài ý định. Dùng server-side allow-list/resource ID và business authorization.

**Câu 14.** Thấy event 4769 cho backend service có chứng minh attacker đang khai thác KCD không?

**Đáp án:** không. Cần baseline, user/SPN/host context và liên hệ với account/ACL changes, backend actions.

**Câu 15.** KDC cấp backend ticket hợp lệ nhưng Spring backend API trả 403. Có nên thêm SPN vào allow-list?

**Đáp án:** không mặc định. Đây có thể là object/tenant/action authorization ở backend, khác KDC delegation.

**Câu 16.** KCD classic “Use Kerberos only” và “Use any authentication protocol” khác nhau như thế nào?

**Đáp án:** chế độ protocol transition và loại evidence KDC chấp nhận khác nhau. S4U2Self/Proxy chịu các yêu cầu/phạm vi khác nhau; không bật broad transition nếu chỉ cần Kerberos hop.

**Câu 17.** SAML/ OIDC login thành công có thể thay bằng một Kerberos forwarded TGT không?

**Đáp án:** không. SAML Assertion/OIDC ID Token là chứng cứ theo giao thức riêng; nếu backend cần Kerberos, phải dùng S4U/protocol transition được KDC cho phép hoặc kiến trúc tương đương.

**Câu 18.** Vì sao RBCD ACL cần change control?

**Đáp án:** principal có quyền sửa resource attribute có thể thay danh sách service được phép đại diện users, làm đổi trust boundary và blast radius.

## 31. Tóm tắt

**Xác thực SPNEGO vào Spring Security không tự cấp quyền delegation.** Frontend muốn gọi backend “dưới danh tính người dùng” phải có **credential delegation hoặc KDC-mediated KCD/RBCD** đúng chính sách; hoặc phải chọn **service identity với một hợp đồng on-behalf-of được xác minh** nếu backend không thực sự cần Kerberos user tickets.

Bốn nguyên tắc giữ hệ thống an toàn:

1. **Không delegate nếu không cần.**
2. **Nếu cần, giới hạn theo frontend service identity, backend SPNs, user/tenant, hành động và thời hạn.**
3. **KDC ticket issuance không thay backend authorization/ACL.**
4. **Bảo vệ service accounts/credentials, audit delegation và kiểm thử các đường từ chối.**

Một kiến trúc có thể “đăng nhập SSO thành công” nhưng delegation thất bại; đó có thể là **một kết quả an toàn đúng**, không phải lỗi cần chữa bằng wildcard SPNs hay Domain Admin service account.

### Tài liệu chính thức tham khảo

1. IETF RFC 4120 — Kerberos V5, Sections 2.5–2.8 về proxy, forwardable tickets và OK-AS-DELEGATE: https://www.rfc-editor.org/rfc/rfc4120.html
2. IETF RFC 4178 — SPNEGO mechanism negotiation: https://www.rfc-editor.org/rfc/rfc4178.html
3. Microsoft Learn — Kerberos Constrained Delegation overview (classic KCD/RBCD, S4U and security implications): https://learn.microsoft.com/en-us/windows-server/security/kerberos/kerberos-constrained-delegation-overview
4. Microsoft Learn — Attribute `msDS-AllowedToActOnBehalfOfOtherIdentity` for RBCD: https://learn.microsoft.com/en-us/windows/win32/adschema/a-msds-allowedtoactonbehalfofotheridentity
5. Microsoft Open Specifications — MS-SFU Service for User and Constrained Delegation Protocol: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-sfu/
6. Microsoft Learn — Protected Users Security Group: https://learn.microsoft.com/en-us/windows-server/security/credentials-protection-and-management/protected-users-security-group
7. Microsoft Learn — Troubleshooting Kerberos Constrained Delegation: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/troubleshoot-kerberos-constrained-delegation-issues
8. Oracle Java 17 — `GSSContext`, `requestCredDeleg`, `getCredDelegState` and `getDelegCred`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html
9. Spring Security — Spring and Spring Security Kerberos, SPNEGO and providers: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
10. Spring Security Kerberos API — `SpnegoAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
11. Spring Security Kerberos API — `KerberosServiceAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
