# Thiết lập tin cậy giữa các realm và giới hạn triển khai tại hạ tầng

**Kerberos cross-realm trust** cho phép một principal được xác thực tại realm nguồn truy cập một dịch vụ nằm trong realm khác **mà không phải sao chép mật khẩu người dùng sang realm đích**. Điều này rất hữu ích khi một hệ thống Spring Security dùng **SPNEGO** phải phục vụ người dùng từ nhiều domain/forest của doanh nghiệp, công ty đối tác hoặc tổ chức sau sáp nhập. Nhưng “có trust” **không đồng nghĩa** “ai từ realm đối tác cũng được đăng nhập”, càng không đồng nghĩa “người đó có quyền đọc tài nguyên”.

Bài học thuộc nhóm **Kerberos và SPNEGO**, tập trung vào **quan hệ tin cậy giữa realm**, **chuỗi vé giới thiệu (cross-realm TGT/referral ticket)** và **những điều kiện hạ tầng** phải đồng thời đúng: KDC, khóa liên realm, hướng trust, DNS/SPN, kết nối mạng, thời gian hệ thống, chính sách mã hóa, keytab service, quản lý tài khoản, AD selective authentication/SID filtering và mapping quyền ở Spring. Những cấu hình chỉ “đổi default_realm trong Java” hoặc “đặt hai KDC vào một file” **không tạo trust**.

Ví dụ xuyên suốt:

~~~text
Realm người dùng:             USERS.EXAMPLE
Realm trung gian (nếu có):    HUB.EXAMPLE
Realm ứng dụng:               APPS.EXAMPLE

User principal:               lan@USERS.EXAMPLE
Spring public URL:            https://portal.apps.example/
HTTP service principal:       HTTP/portal.apps.example@APPS.EXAMPLE
Service keytab:               /etc/security/keytabs/portal.keytab
Local identity link:          (USERS.EXAMPLE, lan) -> localUser u-702
~~~

Tất cả host `.example` chỉ minh họa. **Không có kết nối thật đến KDC/Active Directory** cho đến khi triển khai với miền do tổ chức quản lý.

## 1. Các lớp tin cậy không thể nhập làm một

| Lớp | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Danh tính nguồn** | User thuộc realm nào, ai xác thực user? | `lan@USERS.EXAMPLE` |
| **KDC trust** | Realm ứng dụng có chấp nhận đường xác thực từ realm nguồn? | A → B hoặc A → HUB → B |
| **Referral routing** | Client tìm được realm/KDC tiếp theo để lấy ticket không? | Cross-realm TGT `krbtgt/APPS.EXAMPLE@USERS.EXAMPLE` |
| **Service identity** | Ticket được phát cho SPN nào? | `HTTP/portal.apps.example@APPS.EXAMPLE` |
| **Acceptor key** | Spring có đúng keytab/KVNO/enctype để giải ticket không? | Keytab cho Portal |
| **Hạ tầng** | DNS, Kerberos ports, clock, TLS, proxy có hoạt động? | DNS 53, KDC 88, HTTPS 443 |
| **Windows trust policy** | Trust chiều nào, forest trust, selective authentication, SID filtering? | Resource forest tin account forest |
| **Principal mapping** | Có user nội bộ tương ứng với principal đã xác minh không? | `(realm, principal) → localUserId` |
| **Authorization** | User được làm gì sau đăng nhập? | `ROLE_REPORT_VIEWER`, tenant allowlist |

Một hệ thống có thể **PASS KDC trust nhưng FAIL Spring authorization** (403), hoặc **PASS network nhưng FAIL service ticket** vì SPN/keytab không khớp (401). Đừng khắc phục lỗi 403 bằng cách mở rộng forest trust, và đừng khắc phục 401 bằng `permitAll()`.

## 2. Realm, KDC, principal và cross-realm key

**Realm** là không gian quản trị Kerberos chứa database principals/keys và một hoặc nhiều **Key Distribution Centers (KDC)**. KDC có hai dịch vụ logic:

- **AS (Authentication Service):** xác minh client, cấp **Ticket Granting Ticket (TGT)** cho realm của client.
- **TGS (Ticket Granting Service):** dựa vào TGT hợp lệ để cấp **service ticket** cho một service principal.

Ví dụ principal:

~~~text
Client principal:
  lan@USERS.EXAMPLE

Home-realm TGS principal:
  krbtgt/USERS.EXAMPLE@USERS.EXAMPLE

Cross-realm TGS principal for source USERS -> target APPS:
  krbtgt/APPS.EXAMPLE@USERS.EXAMPLE

Web service principal:
  HTTP/portal.apps.example@APPS.EXAMPLE
~~~

`krbtgt/DESTINATION@SOURCE` **không phải tên web server**, mà là principal/khóa hỗ trợ bước ủy quyền xác thực giữa KDCs. Khi hai realm MIT Kerberos tạo **direct cross-realm trust**, KDCs cần có các principal tin cậy liên realm với key material đồng bộ theo chiều tương ứng. Để đi chiều ngược lại có thể cần principal liên realm đảo chiều. Trong Microsoft Active Directory, các secrets/Trusted Domain Objects được AD quản lý thông qua cơ chế trust, không triển khai bằng cách chép thủ công lệnh MIT Kerberos vào domain controllers.

**Quan trọng:** tài khoản service/kho keytab của Spring **không chứa khóa krbtgt liên realm**. Spring chỉ cần credentials để nhận ticket tới HTTP SPN đích, còn **KDCs** chịu trách nhiệm phát và xác minh các referral/cross-realm tickets theo trust đã quản trị. Không sao chép krbtgt keys hoặc trust passwords sang JVM/app pods.

### Các thuật ngữ không được đồng nhất

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Cross-realm TGT / referral TGT** | Ticket giúp client đi đến KDC/realm tiếp theo |
| **Service Ticket** | Ticket cuối cùng cho `HTTP/portal.apps.example` |
| **Principal** | Tên danh tính người dùng/dịch vụ trong Kerberos namespace |
| **SPN** | Service Principal Name, ánh xạ service instance sang account/key phù hợp |
| **UserPrincipalName (UPN)** | Cách đặt tên người dùng trong AD; không đồng nghĩa SPN |
| **Realm trust** | Quan hệ KDCs/AD domains/forests được thiết lập và quản trị |
| **Kerberos delegation** | Khả năng chuyển tiếp/thay mặt principal đến service khác, là bài toán riêng |
| **Spring authorities** | Vai trò/quyền trong app; không tự sinh vì KDC tin user |

## 3. Luồng cấp ticket khi user A đến service B

Giả sử user `lan@USERS.EXAMPLE` truy cập Portal thuộc `APPS.EXAMPLE`. Hai KDC realms đã có trust theo hướng cho phép **USERS → APPS**.

~~~mermaid
sequenceDiagram
    participant B as Browser / user Lan
    participant UA as KDC USERS.EXAMPLE
    participant PA as KDC APPS.EXAMPLE
    participant SP as Spring Portal APPS
    B->>UA: AS-REQ (xác thực lan@USERS.EXAMPLE)
    UA-->>B: TGT trong USERS.EXAMPLE
    B->>UA: TGS-REQ cho HTTP/portal.apps.example
    UA-->>B: Cross-realm TGT/referral tới APPS.EXAMPLE
    B->>PA: TGS-REQ dùng referral TGT và target SPN
    PA->>PA: Kiểm trust, policy và xác định service key
    PA-->>B: Service Ticket cho HTTP/portal.apps.example
    B->>SP: HTTPS Authorization: Negotiate (GSS/SPNEGO token)
    SP->>SP: Keytab/JGSS accept ticket; xác định user principal
    SP->>SP: Tìm local account + roles + tenant policy
    SP-->>B: 200 hoặc 403 tùy local authorization
~~~

Nếu giữa hai realms có realm trung gian:

~~~text
USERS.EXAMPLE ──trust hop──> HUB.EXAMPLE ──trust hop──> APPS.EXAMPLE

Ví dụ chuỗi referrals:
  krbtgt/HUB.EXAMPLE@USERS.EXAMPLE
  krbtgt/APPS.EXAMPLE@HUB.EXAMPLE
  cuối cùng service ticket:
  HTTP/portal.apps.example@APPS.EXAMPLE
~~~

**Đây là luồng khái niệm**, số lần trao đổi và referrals phụ thuộc triển khai MIT/AD, kiểu trust, KDC policy, name suffix routing và client cache. Một Windows client có thể nhận referrals qua domain/forest hierarchy và global catalog; không được giả định luôn gửi đúng hai TGS-REQ hay luôn có một đường đi tĩnh.

### Mỗi bên xác thực điều gì?

- Client đã có TGT từ home realm, không cần đưa mật khẩu người dùng cho Portal.
- KDC nguồn dùng trust relationship để chỉ client đi đến KDC đích hoặc hop tiếp theo.
- KDC đích phải chấp nhận trust path, kiểm policy và phát service ticket đúng SPN.
- Spring acceptor phải có **service keytab** tương ứng với **target HTTP SPN** và xử lý GSS context hợp lệ.
- Ứng dụng phải ánh xạ **user principal + home realm** sang tài khoản/quyền nội bộ.

**Trust được cấu hình ở KDC/AD; SPNEGO được xử lý ở Java/web server; authorization được xử lý ở Spring/app.** Một lớp không tự làm thay lớp khác.

## 4. Trust một chiều và hai chiều: nói từ phía tài nguyên

Trong thực tế, mô tả chiều trust thường gây nhầm vì từ “inbound/outbound” được nhìn **từ miền đang đứng**. Hãy viết phát biểu nghiệp vụ rõ:

> **Realm APPS tin realm USERS:** các user được xác thực bởi USERS có thể xin ticket đến một số services trong APPS **nếu policy cho phép**.

Khi diễn đạt theo hướng **người dùng đi đến tài nguyên**, gọi đó là `USERS → APPS`. Không có nghĩa ngược lại là `APPS → USERS`.

| Kiểu | Ý nghĩa với luồng người dùng | Phạm vi |
| --- | --- | --- |
| **Một chiều** | User từ A có đường tin cậy để đến service B, nhưng chiều ngược không mặc nhiên đúng | Hạn chế hơn, thường phù hợp chỉ phục vụ partner users |
| **Hai chiều** | Các client của A và B có thể nhận dịch vụ bên kia theo policy | Không phải tài khoản/role tự dùng chung |
| **Transitive** | Một trust path có thể cho client A đi qua B tới C khi loại trust cho phép | **Không** có nghĩa mọi AD trust đều transitive |
| **Non-transitive** | A↔B không tự kéo theo A↔C thông qua B | Cần cấu hình các trust riêng nếu yêu cầu |
| **Forest trust** | Kết nối AD forests theo cơ chế quản trị forest roots | Name suffix routing, selective authentication, SID filtering, quyền |
| **External/domain trust** | Trust gắn miền cụ thể, phạm vi/hành vi khác forest trust | Không tự bao phủ toàn bộ domains/UPN suffixes |

**Đừng kết luận “A trusts B” và “users A truy cập B” là cùng một phát biểu**. Trong thuật ngữ AD, **resource domain/forest B phải trust account domain/forest A** để user A được xác thực vào tài nguyên B. Hãy luôn ghi rõ bên có accounts và bên chứa resources.

### Ví dụ chính sách đối tác

~~~text
Resource owner:  APPS.EXAMPLE (Spring Portal và backend)
Account owner:   PARTNER.EXAMPLE (nhân viên đối tác)

Business need:
  PARTNER users -> read reports tại APPS
  APPS users -> PARTNER resources: KHÔNG CẦN

Trust design:
  chỉ cấu hình chiều phục vụ account realm -> resource realm
  giới hạn services/AD selective authentication nếu dùng
  role local ROLE_REPORT_VIEWER cho allowlisted users
~~~

Hai chiều trust có thể làm tăng phạm vi liên thông mà không mang lợi ích nghiệp vụ, vì vậy **không chọn two-way “cho chắc”**. Mọi thay đổi domain/forest trust phải được owner IAM/AD và security phê duyệt.

## 5. Điều kiện thật sự để có direct cross-realm trust trong MIT Kerberos

Theo tài liệu MIT Kerberos, để KDC ở realm A xác thực tickets cho realm B theo quan hệ trực tiếp, hai bên phải chia sẻ key material cho các **cross-realm krbtgt principals** theo cấu trúc phù hợp. Các yếu tố vận hành gồm:

- Principal names tương ứng chính xác cặp realms nguồn/đích.
- Shared keys/long-term secrets nhất quán giữa KDC databases được liên kết.
- **Key Version Number (KVNO)** và encryption types có thể sử dụng chung.
- Ticket lifetime/renewal, policy KDC và transited-realm checking phù hợp.
- KDC discovery, DNS và liên lạc mạng giữa các thực thể cần thiết.
- Quan hệ tin cậy rõ chiều, không “tin mọi realm” chỉ vì thuộc một sơ đồ mạng.

Ví dụ hướng user `USERS.EXAMPLE` đến service `APPS.EXAMPLE`:

~~~text
Requested cross-realm service:
  krbtgt/APPS.EXAMPLE@USERS.EXAMPLE

Administrative responsibility:
  KDC admin ở USERS + KDC admin ở APPS
  chia sẻ long-term trust key qua kênh bảo mật, theo policy
  đảm bảo key versions và encryption types tương thích

Reverse direction if needed:
  krbtgt/USERS.EXAMPLE@APPS.EXAMPLE
  cần được thiết kế và cấu hình riêng
~~~

**Không ghi trust key hay password vào Markdown, CI logs hoặc application.yml**; người làm application không nên tự chạy `kadmin addprinc krbtgt/...` khi chưa có change plan và quyền chính thức. Thiết lập key liên realm là tác vụ quản trị KDC có blast radius lớn. Với AD thì dùng AD trust management, không tự tạo principals theo mẫu MIT.

### Rủi ro rotation

Nếu một bên rotate cross-realm trust key trước khi bên kia cập nhật, referrals có thể thất bại. Các KDC có thể hỗ trợ key history/overlap khác nhau, nhưng **không đảm bảo** mọi client/ticket đang tồn tại vượt quá thời gian rollover. Kế hoạch gồm owner hai bên, kiểm KVNO/enctype, test cả hai chiều có phép, lịch chuyển đổi và rollback.

**Không dùng RC4 hoặc DES chỉ để cứu trust cũ**. Ưu tiên AES theo Kerberos/AD interoperability và security baseline; kiểm phiên bản Windows, MIT KDC, Java crypto policies và service account keys thật trước khi đổi.

## 6. [capaths] là bản đồ đường đi, không phải thao tác tạo trust

Trong MIT Kerberos, cấu hình `krb5.conf` có thể chứa:

- `[libdefaults]`: default realm, DNS lookup và Kerberos options.
- `[realms]`: KDC hosts cho từng realm.
- `[domain_realm]`: map DNS hostname/domain tới Kerberos realm.
- **`[capaths]`: mô tả đường **cross-realm** không phân cấp (non-hierarchical)**, có thể chỉ định một hoặc nhiều realm trung gian.

Ví dụ **đường trực tiếp** USERS ↔ APPS **chỉ khi KDCs đã được thiết lập trust**:

~~~ini
[libdefaults]
    default_realm = USERS.EXAMPLE
    dns_lookup_realm = false
    dns_lookup_kdc = true

[realms]
    USERS.EXAMPLE = {
        kdc = users-dc01.users.example
    }
    APPS.EXAMPLE = {
        kdc = apps-dc01.apps.example
    }

[domain_realm]
    .apps.example = APPS.EXAMPLE
    apps.example = APPS.EXAMPLE
    .users.example = USERS.EXAMPLE
    users.example = USERS.EXAMPLE

[capaths]
    USERS.EXAMPLE = {
        APPS.EXAMPLE = .
    }
    APPS.EXAMPLE = {
        USERS.EXAMPLE = .
    }
~~~

**Dấu `.` trong `[capaths]`** biểu diễn hai realms có **direct shared-key relationship**, không có intermediate realm ở đường đó. Nó **không phải** wildcard “tin mọi realm”.

Ví dụ **đường qua HUB** khi KDC trusts USERS–HUB và HUB–APPS đã có:

~~~ini
[capaths]
    USERS.EXAMPLE = {
        APPS.EXAMPLE = HUB.EXAMPLE
    }
    APPS.EXAMPLE = {
        USERS.EXAMPLE = HUB.EXAMPLE
    }
    HUB.EXAMPLE = {
        USERS.EXAMPLE = .
        APPS.EXAMPLE = .
    }
~~~

**Cảnh báo phạm vi:** `[capaths]` mô tả đường đi/kiểm transited field **cho thư viện MIT Kerberos và các môi trường tương thích**; hành vi Windows AD forest referrals dựa trên domain/forest topology, trusted domain objects, name suffix routing và KDC referrals. Không coi `capaths` là cách duy nhất hay là lệnh tạo forest trust. Trong Java 17, độ hỗ trợ/diễn giải các tùy chọn `krb5.conf` phải được kiểm trên JDK thực tế.

### Không được “thêm realm là có SSO”

Một sai lầm phổ biến:

~~~ini
[realms]
    USERS.EXAMPLE = { kdc = users-dc01.users.example }
    APPS.EXAMPLE = { kdc = apps-dc01.apps.example }
~~~

Hai entries chỉ giúp **biết nơi liên lạc KDC**. Chúng **không** tạo cross-realm krbtgt keys, không khiến KDC USERS phát referral hợp lệ, không tạo SPN, không phân quyền users. Test phải chứng minh **service ticket thực được KDC đích phát** và **Spring acceptor đã verify**, không chỉ ping thành công KDC.

## 7. Windows Active Directory: domain trusts và forest trusts

Trong AD DS, trust được quản lý qua **Trusted Domain Objects (TDO)**, secrets, domain controllers và các chính sách AD. Một forest trust cho phép KDC/client tìm đường authentication giữa các forests, có thể một hoặc hai chiều tùy business requirement.

Trong nhiều AD forests:

- **Account forest** lưu user/computer identities.
- **Resource forest** chứa web apps, service accounts, file servers hoặc APIs.
- Resource forest cần **tin account forest** để user từ account forest có thể đến resources của nó, nếu được phép.
- Forest trust được thiết lập giữa **forest root domains** theo kiến trúc AD.
- AD **name suffix routing** dùng UPN/SPN suffixes và forest namespace để định vị KDC/destination forest.
- **Selective authentication** và **SID filtering** là các ranh giới bảo mật riêng ngoài việc tồn tại trust.
- Service vẫn cần registered HTTP SPN/AD account/keytab phù hợp.
- Spring ứng dụng vẫn cần chính sách local user mapping và authorization.

~~~mermaid
flowchart LR
    A[Account forest<br/>USERS.EXAMPLE] --> T[Forest trust/referral path]
    T --> B[Resource forest<br/>APPS.EXAMPLE]
    B --> SPN[HTTP/portal.apps.example]
    SPN --> APP[Spring SPNEGO acceptor]
    APP --> AUTH[Local user/tenant authorization]
~~~

Sơ đồ là conceptual, không mô phỏng từng TGT hop. Dòng đi từ account forest tới resource forest mô tả **nhu cầu truy cập**, không phải nhãn “inbound/outbound” của giao diện Microsoft. Khi thao tác trong UI, luôn xác minh **domain nào là trusting** và **domain nào là trusted**.

### Trust một chiều trong AD

Nếu resource forest **APPS** trusts account forest **USERS** thì users ở USERS có thể được xác thực đến resources trong APPS theo chính sách. User ở APPS **không tự** có quyền truy cập resources trong USERS. Nếu muốn đối xứng thì cần two-way trust được phê duyệt.

**Hai chiều là mở rộng trust surface, không phải một cách sửa lỗi KDC_ERR_S_PRINCIPAL_UNKNOWN.** Hãy kiểm hướng trust của resource access và SPN trước khi thay đổi trust.

## 8. Forest trust: name suffix routing và giới hạn cross-forest

KDC thường nhận yêu cầu cho service principal:

~~~text
HTTP/portal.apps.example
~~~

Ở một forest khác, nó có thể phải xác định target SPN thuộc forest nào. AD forest trust giữ thông tin về **routed name suffixes** và **Trusted Domain Objects**, giúp chuyển referrals tới forest thích hợp.

Điều kiện có thể phát sinh lỗi:

1. Forest name suffix liên quan đến `apps.example` chưa được route hoặc bị disabled.
2. Hai forests có suffix **trùng/conflict**, làm routing không rõ.
3. User dùng UPN suffix khác với Kerberos realm thực và routing policy chưa hỗ trợ.
4. Service SPN chỉ đăng ký trên một account nhưng browser yêu cầu hostname alias không có SPN phù hợp.
5. KDC/DNS/Global Catalog không nhìn thấy thông tin trust, hoặc replication chưa xong.
6. Trust direction không cho account forest xác thực vào resource forest.
7. Selective authentication hoặc policy khác cố ý từ chối.

Không sửa những lỗi này bằng cách **đổi `principal.getName()` trong Spring rồi “tự cho login”**. Ticket phải được cấp và kiểm từ realm/KDC đúng trước khi app xét principal.

### Forest trust và external trust khác nhau

| Khía cạnh | Forest trust | External/domain trust |
| --- | --- | --- |
| Phạm vi | Kết nối forests với routing theo namespace phù hợp | Giới hạn hơn ở các domain cụ thể |
| Chỗ tạo | Forest root domains | Domain-level theo loại/trường hợp |
| Transitive | Forest trust là loại transitive trong phạm vi quan hệ của hai forests | External trust điển hình non-transitive |
| Routing SPN/UPN | Có forest name suffix routing | Không mặc định mọi suffix/hierarchy |
| Security | Selective authentication, SID filtering, resource ACLs | Cũng cần policy phù hợp trust type |
| Use case | Enterprise federation trong AD forests | Quan hệ domain cục bộ có phạm vi hẹp |

**Không khẳng định một external trust sẽ hỗ trợ mọi kịch bản Kerberos referral giống forest trust.** Microsoft có hướng dẫn rằng một số cơ chế Kerberos Forest Search Order/short name SPN không dùng được qua external trust và cần FQDN/SPN rõ hoặc forest trust phù hợp. Mọi quyết định phải kiểm OS/domain functional levels và tài liệu của topology đang dùng.

## 9. Selective authentication: có trust vẫn phải “được phép xác thực”

Với Microsoft AD **selective authentication**, resource forest có thể yêu cầu cấp quyền **Allowed to Authenticate** cho users/groups của forest đối tác trên **máy/đối tượng tài nguyên phù hợp**, thay vì cho toàn bộ trusted forest được authenticated tới mọi nơi.

Ví dụ:

~~~text
Trust:
  APPS resource forest trusts USERS account forest

Service:
  HTTP/portal.apps.example on app server

Group from USERS:
  USERS\PortalPartners

Allow to Authenticate:
  only service computer/resource objects approved for Portal

App local role:
  only ACTIVE users with partner contract -> ROLE_PARTNER_VIEWER
~~~

Các kiểm tra này **không thay thế nhau**:

- **Selective authentication** ngăn người từ trusted forest xác thực vào các máy/đối tượng không được phép theo AD policy.
- **Local ACL/RBAC** trên target resource/app quyết định quyền tài nguyên sau xác thực.
- **Spring Security `UserDetailsService`/authorities** vẫn cần kiểm business entitlement và tenant.
- Không thể thay selective authentication bằng cách chỉ giấu nút UI, hoặc thay local roles bằng quyền “Allowed to Authenticate”.

Nếu tổ chức áp selective authentication mà chưa cấp phép cho đúng resource/host, **KDC/AD có thể từ chối** dù forest trust đã được cấu hình. Người hỗ trợ phải phân biệt “trust broken” với “chính sách cố ý không cho phép”.

### SID filtering và SIDHistory

AD uses **Security Identifiers (SID)** để phân quyền Windows resources. Với cross-forest trust, **SID filtering** bảo vệ chống việc một forest không đáng tin “mang theo” những SIDs không nên được tin trong authorization data. `SIDHistory` hữu ích trong migration nhưng cũng có thể bị lạm dụng nếu cấu hình trust quá rộng.

**Không tắt SID filtering hoặc bật rộng `EnableSIDHistory` chỉ để một ứng dụng từ chối quyền bắt đầu chạy.** Nếu thực sự cần migration SIDHistory, phải có threat assessment, giới hạn thời gian, kiểm trust boundary và change approval.

Với Spring app chỉ lấy Kerberos principal rồi tra local role, nhiều kiểm soát SID/PAC diễn ra trong AD/Windows layer, không phải trong một Java controller. **Không tự parse PAC rồi cấp `ROLE_ADMIN` theo một SID chưa qua chính sách**.

## 10. Trust không đồng nghĩa quyền truy cập hoặc delegation

Giả sử:

~~~text
User:
  lan@USERS.EXAMPLE

Kerberos cross-realm trust:
  PASS (client lấy service ticket đến APPS)

Spring acceptor:
  PASS (service principal/keytab đúng)

Local account:
  lan@USERS.EXAMPLE không có account được phê duyệt ở Portal

Expected:
  Spring từ chối quyền hoặc quy trình JIT theo policy
  tuyệt đối không tạo ROLE_ADMIN chỉ vì trust PASS
~~~

Với ứng dụng nhiều tổ chức, **khóa định danh an toàn** phải giữ namespace nguồn:

~~~text
(trustedRealm, canonicalPrincipal)
  -> localUserId
  -> tenantMembership
  -> approvedAuthorities
~~~

Không bỏ realm và chỉ dùng `lan` vì `lan@USERS.EXAMPLE` khác `lan@PARTNER.EXAMPLE`; UPN suffix và email domain cũng có thể khác Kerberos realm. Nếu cần account linking, xây quy trình xác minh riêng.

### Double hop và constrained delegation

Trình duyệt Kerberos authenticate tới Spring Portal **không tự** làm Portal có thể thay user truy cập SQL/SMB/HTTP backend khác. Bước đó là **delegation/double hop**, khác việc chấp nhận một user từ realm khác.

- AD có Kerberos Constrained Delegation (KCD), Resource-Based Constrained Delegation (RBCD) và S4U theo điều kiện policy.
- Tài khoản service chỉ nên được delegate đến **SPNs đích cụ thể** và không hơn.
- Cross-forest delegation có hạn chế riêng theo trust flags và security updates.
- Không dùng **unconstrained delegation** để “sửa” lỗi double hop, vì có thể mở rộng đáng kể quyền lạm dụng.
- Nếu Java/Spring app không thực sự thực hiện delegation, không bật Kerberos forwardable/proxiable flags vô điều kiện.
- Service downstream phải validate ticket và thực thi authorization riêng; copy username vào HTTP header không phải delegation an toàn.

## 11. krb5.conf và Java 17: giới hạn rất dễ bỏ sót

Oracle Java 17 cho phép cấu hình:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
~~~

Hoặc khi chỉ cần một realm/KDC có thể dùng **cả hai**:

~~~text
-Djava.security.krb5.realm=USERS.EXAMPLE
-Djava.security.krb5.kdc=users-dc01.users.example
~~~

**Cảnh báo chính thức của Oracle:** nếu chỉ dùng hai system properties `java.security.krb5.realm` và `java.security.krb5.kdc` mà **không có `krb5.conf`**, cross-realm authentication có thể **không thực hiện được** vì thiếu cấu hình bổ sung cho realms/paths. Cả hai properties phải được đặt cùng nhau nếu dùng. Với multi-realm SPNEGO, cung cấp cấu hình `krb5.conf` đầy đủ và test trên đúng JDK/runtime.

### Ví dụ krb5.conf cho người dùng A đến service B

~~~ini
[libdefaults]
    default_realm = USERS.EXAMPLE
    dns_lookup_kdc = true
    dns_lookup_realm = false
    rdns = false

[realms]
    USERS.EXAMPLE = {
        kdc = users-dc01.users.example
        kdc = users-dc02.users.example
    }
    APPS.EXAMPLE = {
        kdc = apps-dc01.apps.example
        kdc = apps-dc02.apps.example
    }

[domain_realm]
    users.example = USERS.EXAMPLE
    .users.example = USERS.EXAMPLE
    apps.example = APPS.EXAMPLE
    .apps.example = APPS.EXAMPLE

[capaths]
    USERS.EXAMPLE = {
        APPS.EXAMPLE = .
    }
    APPS.EXAMPLE = {
        USERS.EXAMPLE = .
    }
~~~

Đây là **cấu hình minh họa cho direct trust đã tồn tại**. Trong một ứng dụng acceptor chạy tại APPS, `default_realm` có thể cần là `APPS.EXAMPLE` tùy keytab/JAAS/service principal và cách client chạy; không mặc định copy ví dụ máy client USERS sang SP server APPS. **Chỉ đổi default realm không tạo KDC trust**.

### Java Kerberos options không phải trust controls

- `java.security.krb5.conf` chỉ định file cấu hình.
- `javax.security.auth.login.config` chỉ định JAAS configuration file nếu bạn sử dụng kiểu login phù hợp.
- `javax.security.auth.useSubjectCredsOnly` thay đổi nơi GSS tìm credential, cần đánh giá theo flow.
- `sun.security.krb5.debug` chỉ hỗ trợ chẩn đoán ngắn hạn trong môi trường an toàn.
- `KRB5_CONFIG` là biến môi trường thường dùng với MIT libraries; **không mặc định** Java provider xử lý mọi biến môi trường giống MIT.
- `krb5.conf [capaths]` định tuyến/kiểm đường tin cậy, **không lưu keytab**.
- `javax.net.ssl.trustStore` phục vụ TLS CA trust, **không phải Kerberos cross-realm trust**.

**Không lẫn truststore PKIX của HTTPS với key material trust giữa Kerberos KDC realms.** Hai hệ thống khóa và threat models khác nhau.

## 12. DNS, KDC discovery và name canonicalization

Hạ tầng multi-realm phụ thuộc DNS chính xác. Một số bản ghi DNS SRV minh họa:

~~~dns
_kerberos._tcp.users.example. IN SRV 0 100 88 users-dc01.users.example.
_kerberos._tcp.apps.example.  IN SRV 0 100 88 apps-dc01.apps.example.
_kerberos._udp.users.example. IN SRV 0 100 88 users-dc02.users.example.
~~~

- Clients cần tìm KDC của home realm và realm đích (trực tiếp hoặc qua referrals).
- AD clients còn dùng DC Locator, Global Catalog/NetLogon theo trust topology.
- `[domain_realm]` ảnh hưởng mapping hostname/realm với MIT/JGSS contexts.
- SPN `HTTP/portal.apps.example` phải đăng ký trên **đúng service account ở realm đích** và keytab Spring phải chứa key phù hợp.
- DNS aliases/CNAME, VIP/load-balancer hostnames và canonicalization có thể làm client yêu cầu SPN khác dự tính.
- SNI/TLS certificate SAN cho `portal.apps.example` là vấn đề **HTTPS**, không tự làm Kerberos SPN hợp lệ.

**Đừng cấp SPN `HTTP/backend-pod-01` khi browser truy cập `https://portal.apps.example` mà không có thiết kế đổi SPN tương ứng**. Browser thông thường xin ticket cho public hostname, nên Spring acceptor phải giải được ticket của public service.

### Dùng FQDN rõ

Đối với cross-forest Kerberos, ưu tiên **fully qualified domain name (FQDN)** và xác định SPN chính xác, thay vì short name có thể được search suffix/canonicalize khác trên Windows, Linux, proxies. Tài liệu Microsoft ghi nhận một số cơ chế forest search order/short-name SPN không hoạt động qua external trust, do đó cần kiểm trust type thật.

## 13. Firewall và những giới hạn không giải được bằng code Spring

Một trust có thể được tạo, nhưng quá trình xác thực vẫn lỗi khi KDC/DC không nhìn thấy nhau hoặc client không truy cập đúng KDC. Không có một danh sách “mở port 88 là xong” cho mọi AD forest trust.

| Dịch vụ | Ports phổ biến | Khi nào cần |
| --- | --- | --- |
| **DNS** | UDP/TCP **53** | Realm/KDC/hostname/DC discovery |
| **Kerberos** | UDP/TCP **88** | AS/TGS, referral/service tickets |
| **Kerberos password change** | TCP/UDP **464** | Khi password/key workflows yêu cầu |
| **LDAP/LDAPS** | **389** / **636** | Directory queries hoặc AD trust operations theo topology |
| **Global Catalog** | **3268** / **3269** | AD cross-forest object/name lookups theo policy |
| **RPC Endpoint Mapper** | TCP **135** | AD/LSA/NetLogon/RPC functions khi cần |
| **Dynamic RPC** | Windows hiện đại thường TCP **49152–65535** | Một số DC-to-DC/LSA/NetLogon flows, tùy architecture |
| **SMB** | TCP **445** | Một số trust/domain ops, không phải mọi browser SPNEGO request |
| **NTP/time sync** | UDP **123** | Đồng bộ đồng hồ nếu topology sử dụng NTP |
| **HTTPS đến Portal** | TCP **443** | Browser→Spring, hoặc TLS ingress |

**Không mở toàn bộ các ports trên Internet.** Microsoft nêu không phải tất cả ports đều cần trong mọi topology; phải thiết kế matrix **nguồn → đích → mục đích**, least privilege, DNS/DC segmentation, trust creation vs steady-state. Một Spring backend nhận GSS token **không nhất thiết** cần trực tiếp kết nối tới mọi KDC của mọi realm, nếu keytab/identity lookup và flow không đòi hỏi; browser/KDC clients và AD/DC traffic mới có những nhu cầu tương ứng.

### Những network boundaries thường gây lỗi

- VPN/site-to-site firewall chỉ cho KDC của realm nguồn, chặn realm đích.
- DNS split-brain khiến browser xác định sai realm đích hoặc chọn hostname alias.
- DC Locator chọn một domain controller unreachable qua firewall.
- Cross-forest name suffix routing chưa đồng bộ/đang conflict.
- App pod không có đường LDAP/LDAPS tới directory dùng cho `UserDetailsService`, dù GSS acceptor đã verify token.
- Service mesh/proxy strip hoặc biến đổi `Authorization: Negotiate` header.
- Load balancer thay hostname, khiến SPN browser yêu cầu không khớp keytab.
- UDP fragmentation/dropped Kerberos replies; cần hỗ trợ TCP 88 đúng policy.
- KDC/realm clocks chênh lệch hoặc Kerberos enctypes không tương thích.

**Chẩn đoán KDC ticket và Spring local lookup như hai hệ thống riêng**: nếu service ticket đến Spring và verify thành công nhưng LDAP lookup user failed, vấn đề có thể ở **directory connectivity/local identity service**, không ở trust key liên realm.

## 14. Clock skew, ticket lifetime, encryption và rotation

Kerberos dùng timestamp/authenticator và replay defenses. Đồng hồ client/KDC/service lệch vượt tolerance có thể gây `KRB_AP_ERR_SKEW` hoặc lỗi tương đương, kể cả khi trust keys đúng.

**Các điều kiện cần giám sát:**

1. NTP/Windows Time Service được đồng bộ theo domain/forest policy.
2. Ticket lifetimes, renewability và transited-policy behavior nhất quán với yêu cầu.
3. **KVNO và encryption types** của cross-realm trust keys không bị lệch khi rotate.
4. Service account keytab chứa đúng **service principal, KVNO và enctype** hiện hành.
5. KDCs không đòi dùng DES/RC4 yếu ngoài baseline phê duyệt.
6. Ticket sizes/PAC/authorization data có thể lớn khi user có nhiều AD groups, ảnh hưởng HTTP headers/proxy limits.
7. Kerberos replay cache và GSS security context không bị tắt tùy tiện.
8. Trust path có thể qua nhiều KDCs, tăng latency và dependency; cần metrics/timeout phù hợp.

**Không “fix” clock skew bằng cách mở vô hạn tolerance**: giảm khả năng chống replay và che lỗi hạ tầng. **Không “fix” enctype bằng cách bật RC4 trên toàn forest** nếu một keytab cũ; nên phối hợp cập nhật keys và runtime.

### Key rotation cần hai kế hoạch

- **Cross-realm trust secret/krbtgt keys:** KDC/AD admins hai bên chịu trách nhiệm, kiểm các referral tickets sau khi rotate.
- **HTTP service keytab:** owner ứng dụng và IAM chịu trách nhiệm phân phối tất cả replicas, kiểm KVNO/enctype của `HTTP/portal.apps.example`.

Hai loại khóa **khác mục đích**. Không đưa cross-realm krbtgt keys vào app keytab. Khi login fail sau rotation, xác định ticket hỏng ở **referral** hay tại **service acceptor**.

## 15. Trình duyệt SPNEGO và Spring Security Kerberos

Từ góc nhìn HTTP:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Trình duyệt được quản trị có thể lấy service ticket từ KDC (đi qua trust nếu cần), sau đó gửi:

~~~http
GET /reports HTTP/1.1
Host: portal.apps.example
Authorization: Negotiate <base64-GSS-token>
~~~

`Negotiate` là một cơ chế thương lượng GSS/SPNEGO. **Không tự khẳng định mọi Negotiate token là Kerberos**: trong một số Windows browser/policy có thể fallback sang NTLM. Nếu yêu cầu Kerberos cross-realm, kiểm mechanism thực sự đã được sử dụng và không chấp nhận cơ chế không được security policy cho phép.

Spring Security Kerberos sử dụng:

| Thành phần | Chức năng |
| --- | --- |
| `SpnegoEntryPoint` | Thách thức HTTP `WWW-Authenticate: Negotiate` và fallback login khi cấu hình |
| `SpnegoAuthenticationProcessingFilter` | Nhận GSS/SPNEGO token từ header |
| `KerberosServiceAuthenticationProvider` | Kiểm service ticket qua Kerberos ticket validator |
| `SunJaasKerberosTicketValidator` | JAAS/JGSS dùng HTTP service principal và keytab |
| `UserDetailsService` | Ánh xạ principal đã xác thực sang user/authorities nội bộ |
| `SecurityFilterChain` | Bảo vệ routes và áp authorization riêng |

**Không có thuộc tính `trustedRealms=["*"]` nào trong Spring Security tự thiết lập KDC cross-realm trust.** Ứng dụng chỉ kiểm ticket đúng qua GSS acceptor và xác định user identity/role. Realm trust nằm ở KDC/AD, không trong một `requestMatchers` hay login form.

### Spring bean fragment minh họa

Đoạn sau cần Spring Security Kerberos modules đúng version, JDK phù hợp và keytab thật:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class CrossRealmSpnegoBeans {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.apps.example@APPS.EXAMPLE");
        validator.setKeyTabLocation(
                new FileSystemResource(
                    "/etc/security/keytabs/portal.keytab"));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService directoryUsers) {
        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(directoryUsers);
        return provider;
    }
}
~~~

**Đây là Spring configuration fragment, không phải file Java17 standalone**; các components `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, AuthenticationManager, SecurityFilterChain, UserDetailsService và browser fallback cần được cấu hình trong application thật. Spring Security Kerberos version/namespace phải được kiểm trên dependency tree.

**Không đưa keytab service vào source tree hoặc image public.** Mount dưới secret volume có permissions tối thiểu; rotate keytab đồng bộ giữa pods.

### Một trust PASS vẫn có thể FAIL trong Spring

Sau khi `SunJaasKerberosTicketValidator` xác minh ticket, provider cần `UserDetailsService` tìm user. Với user đa realm:

~~~text
Validated Kerberos principal:
  lan@USERS.EXAMPLE

Rejected local lookup:
  app chỉ tìm "lan" trong APPS domain, không phân biệt realm
  hoặc LDAP chỉ tra default realm

Correct approach:
  trustedPrincipal = ("USERS.EXAMPLE", "lan")
  lookup approved identity-link registry
  require ACTIVE status and tenant grant
  assign minimal ROLE_REPORT_VIEWER
~~~

**Không tự strip `@REALM` rồi ghép người dùng**. Nếu local directory chỉ biết employees của APPS, cần một identity mapping/federated lookup được thiết kế rõ cho partner users; không tự mở LDAP bind/queries tới mọi realm mà user input chỉ định.

## 16. Reverse proxy, container và keytab: điều kiện chấp nhận ticket

Kiến trúc:

~~~text
Browser USER in USERS.EXAMPLE
     |
     | https://portal.apps.example
     | Authorization: Negotiate <ticket for HTTP/portal.apps.example>
     v
HTTPS ingress/load balancer
     |
     +------ Spring pod A
     |
     +------ Spring pod B

Kerberos service realm: APPS.EXAMPLE
Keytab on both pods:    HTTP/portal.apps.example@APPS.EXAMPLE
~~~

Browser thường xin ticket cho **hostname public của URL**, không phải tên pod. Vì vậy:

- SPN `HTTP/portal.apps.example` phải tồn tại ở realm/AD account đích đúng.
- Keytab Spring phải tương ứng với service principal/long-term key hiện hành.
- Tất cả replicas phải có keytab/KVNO phù hợp và secret distribution bảo vệ.
- Ingress phải **pass through `Authorization: Negotiate`** nếu Spring là acceptor.
- Nếu ingress tự terminate Kerberos và chuyển username header, trust boundary đổi: Spring phải xác thực kênh ingress→backend, strip headers do client gửi, và có policy rõ về proxy identity.
- HTTPS certificate SAN/hostname cho Portal khác với Kerberos SPN; cần cả hai.
- Nếu Windows Extended Protection/Channel Binding Tokens (CBT) được áp, TLS termination/relay qua proxy có thể cần thiết kế tương thích; **không tắt Extended Protection toàn domain để tiện tích hợp**.
- Session affinity không thay việc cấp đúng Kerberos keytab; sticky sessions cũng không sửa wrong SPN.

### Hạ tầng container có thể giới hạn cross-realm

Kubernetes pod không nhất thiết join Windows domain. Java acceptor có thể dùng keytab/JAAS đúng để nhận GSS token, nhưng **user-detail lookup** và một số KDC/LDAP requirements cần mạng/DNS/secret management riêng. Các pods có clock lệch, DNS policy khác, read-only file mounts hoặc principal config không đồng bộ có thể gây lỗi khó tái hiện.

**Không cấp đặc quyền container hoặc mount toàn bộ host AD credentials chỉ để chạy SPNEGO.** Dùng service identity/keytab tối thiểu và kết nối được phê duyệt.

## 17. Lộ trình thiết kế trust tối thiểu trước khi triển khai

**Bước 1 — Xác định use case:** ai từ realm nào cần đến dịch vụ nào, dùng cho thông tin gì, có cần mutual access hay không?

**Bước 2 — Chọn kiểu trust:** direct MIT cross-realm, AD forest trust, external trust hay một gateway broker. Xác định account realm, resource realm, trust direction, transitivity.

**Bước 3 — Phân tích bảo mật:** SID filtering, selective authentication, name suffix routing, risk từ domains có admin autonomy, token/PAC claims, nhóm được duyệt, delegation restrictions.

**Bước 4 — Rà soát KDC/keys:** cross-realm principal/secrets hoặc AD TDO, supported encryption types, KVNO, key rollover và trách nhiệm quản trị hai bên.

**Bước 5 — DNS/KDC connectivity:** tên FQDN, SRV/DC locator, split DNS, ports 53/88 và các AD ports cần thiết theo matrix.

**Bước 6 — Thiết kế HTTP service:** public URL, target SPN, service account, keytab, load balancing, reverse proxy Negotiate pass-through.

**Bước 7 — Cấu hình Java/OS:** `krb5.conf`, JVM options, JAAS/JGSS và keytab mounts cho Spring; không bịa trust từ YAML.

**Bước 8 — Principal và quyền:** allowlist realms, identity linking, local account status, tenant membership, least privilege RBAC, deny unknown users.

**Bước 9 — E2E test:** có TGT home realm → referral → service ticket → GSS accept → Spring role; test cả mặt thất bại.

**Bước 10 — Vận hành:** monitoring, key rotation, trust changes, DC health, audit, break-glass và rollback rõ ràng.

Nếu đối tác không thể/không muốn thiết lập forest/KDC trust, nên đánh giá **OIDC/SAML federation qua identity broker** thay vì yêu cầu kết nối Kerberos sâu giữa các mạng. Đó là một **kiến trúc thay thế**, không phải “bật SPNEGO qua Internet” bằng một property.

## 18. Java 17 độc lập: mô phỏng đường trust và local authorization

Ví dụ Java thuần sau minh họa hai điều **khác nhau**: có đường referral từ realm người dùng đến realm dịch vụ và có **phê duyệt quyền của ứng dụng**. Nó không liên hệ KDC, không phát vé, không kiểm keytab hay SID.

Thiết kế giả định **cạnh có hướng** trong graph chỉ có nghĩa “đường đi từ account realm sang resource realm **được phê duyệt trong mô hình học tập**”. Đây **không phải** giá trị trustDirection của AD hay một file `[capaths]` thực tế. Chương trình dùng một chuỗi route USERS → HUB → APPS, nhưng không có chiều ngược.

Tạo file **`CrossRealmTrustDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CrossRealmTrustDemo {

    static final String USERS = "USERS.EXAMPLE";
    static final String HUB = "HUB.EXAMPLE";
    static final String APPS = "APPS.EXAMPLE";

    static final String REQUIRED_SERVICE =
            "HTTP/portal.apps.example@APPS.EXAMPLE";

    static final Map<String, List<String>> ROUTES = Map.of(
            USERS, List.of(HUB),
            HUB, List.of(APPS),
            APPS, List.of());

    static List<String> findPath(String from, String to) {
        ArrayDeque<String> queue = new ArrayDeque<>();
        Map<String, String> parent = new HashMap<>();

        parent.put(from, null);
        queue.add(from);

        while (!queue.isEmpty()) {
            String current = queue.remove();
            if (current.equals(to)) {
                ArrayList<String> reversed = new ArrayList<>();
                for (String step = to;
                        step != null; step = parent.get(step)) {
                    reversed.add(step);
                }
                java.util.Collections.reverse(reversed);
                return reversed;
            }

            for (String next : ROUTES.getOrDefault(current, List.of())) {
                if (!parent.containsKey(next)) {
                    parent.put(next, current);
                    queue.add(next);
                }
            }
        }
        return List.of();
    }

    static String authorize(
            String userRealm,
            String targetService,
            boolean localAccountApproved) {

        if (findPath(userRealm, APPS).isEmpty()) {
            return "DENY: no trust path";
        }
        if (!REQUIRED_SERVICE.equals(targetService)) {
            return "DENY: wrong service principal";
        }
        if (!localAccountApproved) {
            return "DENY: local authorization missing";
        }
        return "ALLOW: route, service and local policy";
    }

    public static void main(String[] args) {
        System.out.println("Referral route: "
                + String.join(" -> ", findPath(USERS, APPS)));

        System.out.println("Reverse route: "
                + !findPath(APPS, USERS).isEmpty());

        System.out.println("Correct service: "
                + REQUIRED_SERVICE.equals(
                    "HTTP/portal.apps.example@APPS.EXAMPLE"));

        System.out.println("Before local grant: "
                + authorize(USERS, REQUIRED_SERVICE, false));

        System.out.println("After local grant: "
                + authorize(USERS, REQUIRED_SERVICE, true));

        System.out.println("Wrong SPN: "
                + authorize(USERS,
                    "HTTP/other.apps.example@APPS.EXAMPLE", true));

        System.out.println("Unknown realm: "
                + authorize("UNTRUSTED.EXAMPLE",
                    REQUIRED_SERVICE, true));
    }
}
~~~

Chạy JDK 17 trở lên:

~~~bash
javac CrossRealmTrustDemo.java
java CrossRealmTrustDemo
~~~

**Stdout chính xác:**

~~~text
Referral route: USERS.EXAMPLE -> HUB.EXAMPLE -> APPS.EXAMPLE
Reverse route: false
Correct service: true
Before local grant: DENY: local authorization missing
After local grant: ALLOW: route, service and local policy
Wrong SPN: DENY: wrong service principal
Unknown realm: DENY: no trust path
~~~

**Diễn giải:**

1. `Referral route` có hai hops theo graph demo đã định nghĩa. Điều đó chỉ mô phỏng **đường được duyệt**, không chứng minh KDCs có cross-realm keys.
2. `Reverse route: false` minh họa trust/use-case một chiều. Một cấu hình AD two-way thật có thể hoạt động khác.
3. `Correct service: true` là **so sánh tên principal**, chưa kiểm service ticket.
4. `Before local grant` vẫn **DENY** dù đã tìm được đường trust: Kerberos authentication không tự cấp business role.
5. `After local grant` chỉ **ALLOW trong mô hình**, chưa chứng minh thực tế account đã được KDC xác thực.
6. `Wrong SPN` từ chối khi target service khác public service.
7. `Unknown realm` không có route nên DENY ngay cả khi boolean local grant là true.

**Giới hạn bắt buộc:** graph Java không kiểm Kerberos `krbtgt` keys, transited-field validation, AD selective authentication/SID filtering, SAN/TLS, ticket lifetime/replay, DNS, KVNO/enctype, GSS token, KDC referral algorithm hoặc `UserDetailsService` thật. **Không dùng hàm authorize trong chương trình này thay Kerberos/Java GSS/API kiểm bảo mật production.**

## 19. Thử nghiệm Kerberos thật ở môi trường lab

Với MIT Kerberos/Linux client được quản trị:

~~~bash
# 1. Lấy TGT từ realm người dùng:
kinit lan@USERS.EXAMPLE

# 2. Xem các TGT/referral tickets trong cache:
klist

# 3. Xin service ticket của ứng dụng trong realm đích:
kvno HTTP/portal.apps.example@APPS.EXAMPLE

# 4. Xem lại tickets đã nhận:
klist

# 5. Chỉ trên Spring acceptor/pod: đọc metadata keytab:
klist -kte /etc/security/keytabs/portal.keytab
~~~

Lệnh chỉ minh họa, **không có stdout cố định**. Nếu trust thật chưa được tạo, `kvno` phải fail hoặc báo lỗi phù hợp. Một `kvno` thành công cho thấy KDC có thể cấp service ticket theo cấu hình client/trust, **không tự chứng minh Spring backend giải được ticket**.

Trong AD/Windows với quyền chẩn đoán phù hợp:

~~~powershell
# User machine: xem ticket cache:
klist

# User machine: yêu cầu service ticket:
klist get HTTP/portal.apps.example

# Domain admin/RSAT: tra cứu SPN:
setspn -Q HTTP/portal.apps.example

# Phát hiện SPN duplicates:
setspn -X

# Kiểm tình trạng trust (read-only diagnostics theo quyền):
nltest /domain_trusts

# Liệt kê trust configuration (read-only):
Get-ADTrust -Filter *
~~~

`Get-ADTrust` yêu cầu RSAT ActiveDirectory module và quyền truy vấn; với forest trust cần xem thông tin của **đúng forest root/domain**. `nltest` hiển thị trust relationships nhưng không thay phép thử Kerberos service ticket. Các công cụ Windows có cú pháp/khả năng khác nhau theo OS/domain; không có lệnh đơn lẻ nào chứng minh toàn bộ trust, SID filtering và quyền app.

### Cách kiểm `[capaths]` an toàn

Chỉ đọc file cấu hình, kiểm MIT Kerberos `KRB5_TRACE` trên **máy test** nếu được phép:

~~~bash
# Chỉ chạy trên máy test khi được quyền truy cập log:
KRB5_TRACE=/dev/stderr kvno HTTP/portal.apps.example@APPS.EXAMPLE
~~~

Trace có thể hiển thị usernames/realm/hostnames và thông tin hạ tầng, nên phải lưu trữ/che dữ liệu nhạy cảm. Không in ticket bytes hoặc password vào logs.

Java 17 có:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
-Dsun.security.krb5.debug=true
~~~

**Chỉ bật debug ngắn hạn trên staging** vì log có thể tiết lộ metadata Kerberos, principals và kết nối KDC. Trong production, metrics nên phân loại KDC errors, latency và Spring auth result ở mức tổng hợp.

## 20. Ma trận kiểm thử theo lớp

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Direct trust | USERS KDC và APPS KDC có keys/policy tương thích | Client nhận cross-realm referral/service ticket |
| No trust | APPS không tin USERS | Không thể có valid cross-realm service ticket |
| Trust direction | USERS → APPS được duyệt, APPS → USERS không | Chỉ chiều được duyệt hoạt động |
| Trust path via HUB | USERS → HUB → APPS đã cấu hình và tin | Có referral path hợp lệ |
| Wrong capaths | Path khai báo nhưng không có trust keys | Fail closed |
| Wrong KDC | DNS/SRV trỏ KDC realm khác | Fail hoặc referral không hợp lệ |
| Name suffix conflict | AD forest suffix trùng | Routing bị từ chối/đi sai, cần admin sửa |
| External vs forest | Short-name SPN qua external trust | Không giả định support như forest trust |
| Selective authentication | User đối tác không có Allowed to Authenticate | Từ chối dù trust tồn tại |
| SID filtering | Ticket mang SIDs ngoài trust boundary | AD policy loại/từ chối theo loại trust |
| ST-like service ticket | Service ticket cho SPN lạ | Spring acceptor không nhận |
| Valid SPN/keytab | HTTP public SPN với đúng KVNO/enctype | GSS/SPNEGO accept thành công |
| Stale keytab | Service account key đã rotate | Verify ticket fail |
| Wrong principal | User realm khác bị map cùng short username | Không gộp tài khoản |
| Local account disabled | Ticket hợp lệ nhưng user disabled | Spring deny access |
| Local role absent | Ticket hợp lệ, thiếu `ROLE_REPORT_VIEWER` | HTTP 403 ở route bảo vệ |
| Admin spoof | User từ realm đối tác có group “Admins” | Không tự cấp `ROLE_ADMIN` |
| DNS split horizon | Client thấy KDC/host sai | Chẩn đoán DNS, không bypass |
| Firewall KDC | UDP/TCP 88 bị chặn trên đường cần | Kerberos failure có thể tái hiện |
| AD RPC | DC trust flows thiếu ports cần thiết | Trust verification/maintenance fail |
| Clock skew | User/KDC/SP lệch clock | Kerberos reject |
| Enctype mismatch | KDC/trust/service không chung cipher | Reject; phối hợp đổi keys |
| PAC size | User quá nhiều groups, token quá lớn | Kiểm headers/proxy limits, không tăng vô hạn |
| Proxy strips Negotiate | Authorization header biến mất | 401/fallback, sửa ingress |
| NTLM fallback | Client không dùng Kerberos | Không coi là cross-realm Kerberos PASS |
| Cross-forest double-hop | Portal gọi backend thay user | Chỉ khi delegation policy approved |
| Multi-node rollout | Pods khác keytabs/krb5.conf | Phát hiện drift và sửa theo change plan |

**PASS end-to-end** chỉ khi có: user home TGT đúng → KDC referral đúng → target service ticket → Spring GSS accept → principal namespace đúng → local permission. Không sử dụng kết quả ping, chỉ có `Authorization: Negotiate` hay một Java graph demo để tuyên bố Kerberos trust đã hoạt động.

## 21. Runbook chẩn đoán theo triệu chứng

| Triệu chứng | Nơi điều tra đầu tiên | Điều không được làm |
| --- | --- | --- |
| `KDC_ERR_WRONG_REALM` | Realm mapping/DNS/referral hint/name suffix | Không tự sửa username realm để vượt kiểm |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | Target SPN chưa đăng ký hoặc routing sai | Không bật wildcard SPN/AD trust |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | Duplicate servicePrincipalName | Không xóa SPN không rõ owner |
| `KRB_AP_ERR_MODIFIED` | Keytab wrong KVNO/enctype/account/SPN | Không bỏ GSS integrity checks |
| `KDC_ERR_ETYPE_NOSUPP` | Trust key/service key encryption mismatch | Không bật weak crypto vô điều kiện |
| `KRB_AP_ERR_SKEW` | NTP/time sync client, KDC, Spring | Không mở skew vô hạn |
| `Cannot find KDC for realm` | krb5.conf, SRV, DNS, firewall | Không thay KDC sang máy lạ chưa trust |
| `Server not found in Kerberos database` | SPN/target realm | Không tự cấp realm-based admin role |
| `Authentication failed: Service not found` | SPN/alias, user details, filter chain | Không disable authentication |
| Browser 401 loop | Browser policy, missing ticket, proxy, keytab | Không bật `permitAll` |
| GSS accepted but Spring 403 | Local UserDetailsService/roles/tenant | Không mở two-way trust để sửa 403 |
| Works domain A, fails domain B | Trust direction, suffix routing, selective authentication | Không tắt SID filtering |
| Keytab works pod A, fails pod B | Keytab mount/KVNO/JDK config drift | Không copy keys qua insecure channels |
| AD trust verifies nhưng SSO fail | SPN, browser DNS, app authorization riêng | Không kết luận trust broken vội |
| Referral loops/long latency | capaths/DC locator/forest topology | Không tăng timeout vô hạn |
| Cross-forest user bị “not found” | Directory lookup user namespace/UPN mapping | Không bỏ realm và auto-link email |
| Double hop denied | KCD/RBCD/trust delegation flags | Không bật unconstrained delegation |

**Thứ tự gỡ lỗi ít xâm lấn:** (1) hostname/SPN thực; (2) user TGT và target service ticket; (3) trust direction/referral path; (4) network/DNS/clock; (5) SPN owner/keytab/KVNO; (6) browser/proxy Negotiate; (7) Spring principal mapping; (8) local authorization. Ghi nhận lỗi tại đúng tầng, không “bật nhiều quyền hơn” để che lỗi.

## 22. Cảnh báo về chi phí và hạn chế kiến trúc

Cross-realm trust giữa **hạ tầng thật** không chỉ là một file application.yml; nó thường đòi hỏi:

- Hai đội quản trị realms/forests phối hợp và chấp nhận quan hệ tin cậy dài hạn.
- Một vùng mạng/DC-to-DC routing có thể đi qua WAN/VPN/peering; firewall/segmentation cần bảo vệ.
- KDC/DNS/Global Catalog/NetLogon có khả năng chịu tải và failover.
- Quản lý certificate HTTPS riêng cho browser/SP, song song với Kerberos keytab/trust keys.
- Đồng bộ clocks/crypto policies/OS security patches của nhiều bên.
- Quản lý **UPN/AD groups/PAC/SIDHistory** và mapping người dùng giữa tổ chức.
- Quy trình rotate trust secrets và service keys ảnh hưởng nhiều services.
- Cân nhắc rủi ro đối tác có admin autonomy, có thể tạo principals/groups trong namespace của họ.
- Chi phí audit, giám sát, phát hiện SID/group spoof và trách nhiệm vận hành khi xảy ra sự cố.
- Giới hạn browser SPNEGO trên máy không domain-joined hoặc mobile/unmanaged devices.
- Không có guarantee delegation tới backend chỉ nhờ user đã qua SPNEGO tại front end.

**Không đặt cross-forest trust rộng chỉ để một web portal có một màn hình đăng nhập** nếu đối tác chỉ cần truy cập vài ứng dụng. Đánh giá OIDC/SAML federation qua broker/identity provider có ranh giới mạng hẹp hơn và khả năng triển khai qua Internet/managed cloud cao hơn, nhưng các giao thức đó lại có identity/claim/consent semantics riêng; không gọi chúng là “Kerberos cross-realm” khi thực tế không có KDC trust.

## 23. Kịch bản thực hành và câu hỏi

### Tình huống A — thêm hai KDC vào krb5.conf nhưng không có referral

Đội app thêm `USERS.EXAMPLE` và `APPS.EXAMPLE` vào `[realms]`, DNS resolve đúng nhưng `kvno HTTP/portal.apps.example@APPS.EXAMPLE` thất bại.

**Giải thích:** cấu hình KDC discovery **không tạo cross-realm trust keys**. Cần owner KDCs/AD xác minh trust, referral path, direction, encryption và policy. Không tự thêm `capaths` rồi coi chắc chắn đã tạo trust.

### Tình huống B — trust có nhưng đối tác chưa được vào server

Forest APPS trusts USERS. Trong AD bật selective authentication nhưng user `lan@USERS.EXAMPLE` không có Allowed to Authenticate trên resource/host phù hợp.

**Kết quả:** authentication có thể bị chặn theo AD policy. Không phải lỗi Spring role mapping; phải xin quyền tối thiểu cho đúng resource qua AD owner. Sau đó vẫn cần local application entitlement.

### Tình huống C — một username ở hai realms

`lan@USERS.EXAMPLE` và `lan@PARTNER.EXAMPLE` cùng phần tên `lan`.

**Kết quả:** hai principal khác namespaces. Nếu ứng dụng `loadUserByUsername("lan")` cho cả hai, có thể tạo **account collision**. Phải giữ trusted realm trong key link và có quy trình identity verification.

### Tình huống D — đã login vào Portal nhưng không gọi được SQL downstream

Spring đã xác minh SPNEGO từ USERS, nhưng Portal không thể dùng identity của Lan trên SQL service nằm ở APPS forest.

**Giải thích:** đây là **delegation/double-hop**. Cần KCD/RBCD/S4U/trust configuration và quyền tại SQL theo policy; không tự lấy browser token gửi tiếp hoặc bật unconstrained delegation.

### Tình huống E — một trust khác forest có name suffix conflict

User cùng AD account có thể đăng nhập local, nhưng cross-forest referral đến SPN `HTTP/portal.apps.example` bị route nhầm/không route.

**Giải thích:** kiểm suffix routing trong TDO/forest trust và hostname SPN, không đổi role Spring hay làm “trust everyone”.

### Tình huống F — Kerberos pass nhưng user vẫn 403

KDC đã phát service ticket và `SunJaasKerberosTicketValidator` chấp nhận, nhưng Spring `UserDetailsService` không tìm thấy local active user có quyền xem báo cáo.

**Kết quả:** 403 có thể là đúng. Tạo account link/role sau khi phê duyệt, không nới KDC trust hay bỏ security filters.

## 24. Checklist cuối bài

- [ ] Phân biệt realm, KDC, principal, SPN, TGT và service ticket.
- [ ] Đã xác định account realm, resource realm và **chiều người dùng → dịch vụ** cần dùng.
- [ ] KDC trust keys/TDO được chủ sở hữu quản trị, không nằm trong app keytab.
- [ ] Biết `krbtgt/DEST@SRC` là principal liên realm, không phải SPN của Spring.
- [ ] Không nhầm direct/transitive/non-transitive forest/external trust.
- [ ] `[capaths]` chỉ mô tả đường đi, không tự tạo keys/trust.
- [ ] `krb5.conf` có KDC/realm/domain mappings đúng cho Java.
- [ ] Không chỉ dùng `java.security.krb5.realm/kdc` mà bỏ các thông tin cross-realm cần thiết.
- [ ] AD forest trust direction và name suffix routing đã kiểm.
- [ ] SID filtering và selective authentication được phê duyệt, không tắt để sửa lỗi ngẫu nhiên.
- [ ] DNS/FQDN, DC/KDC reachability và firewall matrix được đánh giá.
- [ ] KDC/service key enctypes, KVNO, rotation và time sync phù hợp.
- [ ] Browser dùng đúng HTTP SPN cho public hostname.
- [ ] Spring SPNEGO acceptor có đúng service keytab/principal, không chứa cross-realm trust key.
- [ ] Reverse proxy pass-through Negotiate hoặc trusted header architecture rõ.
- [ ] NTLM fallback không được nhầm là Kerberos cross-realm success.
- [ ] Spring principal mapping giữ **realm namespace**, kiểm local user status và tenant.
- [ ] Không tự cấp admin vì realm đã trusted hoặc vì AD group trông giống admin.
- [ ] Double-hop/delegation chỉ bật khi có KCD/RBCD policy rõ, không unconstrained.
- [ ] Positive/negative E2E tests kiểm AS/TGS referral + service ticket + GSS + authorization.
- [ ] Có vận hành/monitoring/rollover/runbook và owner của mỗi trust.
- [ ] Đã cân nhắc identity broker OIDC/SAML nếu thiết lập Kerberos trust quá rộng/rủi ro.

## 25. Tài liệu chính thức tham khảo

1. [RFC 4120 — The Kerberos Network Authentication Service V5](https://www.rfc-editor.org/rfc/rfc4120): principals, KDC, AS/TGS và cross-realm referral/ticket semantics.
2. [MIT Kerberos — Cross-realm authentication](https://web.mit.edu/kerberOS/krb5-1.22/doc/admin/database.html): `krbtgt` cross-realm keys, KVNO/encryption type và quản trị KDC.
3. [MIT Kerberos — krb5.conf và capaths](https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/conf_files/krb5_conf.html): `[realms]`, `[domain_realm]`, `[capaths]` và transited path checks.
4. [Oracle Java 17 — Kerberos Requirements](https://docs.oracle.com/en/java/javase/17/security/kerberos-requirements.html): JVM krb5.conf, realm/kdc properties và giới hạn cross-realm.
5. [Oracle Java 17 — Kerberos GSS-API Mechanism](https://docs.oracle.com/en/java/javase/17/security/kerberos-5-gss-api-mechanism.html): `[capaths]` support, realm mapping, client settings.
6. [Microsoft — How trusts work for AD forests](https://learn.microsoft.com/en-us/entra/identity/domain-services/concepts-forest-trust): trusted domain objects, forest trust, name suffix routing, KDC referral.
7. [Microsoft — Netdom trust](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netdom-trust): trust verification, selectiveauth/quarantine/name suffixes và các trust flags.
8. [Microsoft — Selective Authentication](https://learn.microsoft.com/en-us/dotnet/api/system.directoryservices.activedirectory.forest.getselectiveauthenticationstatus): Allowed to Authenticate và policy cross-forest.
9. [Microsoft — Firewall for AD domains and trusts](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/config-firewall-for-ad-domains-and-trusts): cổng DNS/Kerberos/LDAP/GC/RPC cần thiết theo topology.
10. [Microsoft — KFSO across external trusts](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/kfso-not-work-in-external-trust-event-is-17): giới hạn short-name SPN/forest referrals.
11. [Spring Security Kerberos — Spring and Spring Security Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, keytab và user details.
12. [Spring Security — KerberosServiceAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html): ticket validator + UserDetailsService semantics.
13. [Keycloak — Server Admin Guide / Cross-realm trust](https://www.keycloak.org/docs/latest/server_admin/): minh họa `krbtgt/B@A` và cách LDAP user lookup liên realm.
14. [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): HTTP `Negotiate` và cơ chế GSS/SPNEGO.

**Ghi nhớ cốt lõi:** **cross-realm trust là quan hệ giữa KDC/AD realms, không phải switch của Spring Security**. Muốn user từ USERS truy cập Spring Portal ở APPS, phải có đường referral được tin cậy, target SPN/keytab hợp lệ và các điều kiện hạ tầng (DNS, mạng, clocks, encryption, AD policies) đúng. Ngay cả khi Kerberos ticket được xác minh, **local principal mapping, tenant restrictions và authorities ở Spring vẫn quyết định user được truy cập tài nguyên nào**.