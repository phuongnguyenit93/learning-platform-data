# Kiểm thử sai realm, lệch giờ và keytab không khớp

**Kerberos SSO có thể thất bại dù người dùng đã đăng nhập Windows và ứng dụng Spring Boot hoạt động bình thường.** Ba nhóm nguyên nhân quan trọng cần kiểm thử độc lập là **sai Kerberos realm/trust path**, **lệch đồng hồ client–KDC–service**, và **keytab của service không tương ứng với SPN, key version, encryption type hoặc key material đang được KDC dùng**. Các lỗi này có triệu chứng tương tự ở phía browser: vòng lặp 401/Negotiate, popup đòi nhập mật khẩu hoặc `GSSException` trong log. Tuy nhiên cách chẩn đoán và biện pháp khắc phục hoàn toàn khác nhau.

Bài này thuộc **Spring Security – federation → Kiểm thử SSO**, tập trung vào **Kerberos V5 + SPNEGO HTTP Negotiate trên Spring Security Kerberos extension**, với ví dụ MIT Kerberos và Active Directory (AD). Mục tiêu là xây **kế hoạch kiểm thử âm tính có thể lặp**, biết cách định vị lỗi tại client, KDC, SPN, JVM acceptor, keytab hay tầng ứng dụng; phân biệt điều kiện giao thức với business authorization; và tránh những biện pháp làm yếu bảo mật.

**Bốn nguyên tắc cốt lõi:**

1. **Realm, SPN và principal có phạm vi rõ**. User `alice@CORP.EXAMPLE.TEST` không tự là `alice@PARTNER.EXAMPLE.TEST`; một service ticket cho `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST` không được trình cho service khác như cùng một bằng chứng.
2. **Clock skew là giới hạn freshness/replay**, không phải thời gian sống của ticket. Ngưỡng mặc định phổ biến ở MIT Kerberos và Sun/Oracle JDK là **300 giây (5 phút)**, nhưng **có thể được cấu hình**; không mặc định mọi tổ chức/hệ triển khai có cùng ngưỡng.
3. **Keytab chứa secret keys của service**, không chỉ tên principal. SPN, KVNO, enctype, key material và đường dẫn/keytab permissions phải tương thích với ticket thực tế; không tiết lộ keytab khi debug.
4. **Test pass Kerberos ≠ app user được phép truy cập**. Sau accept ticket, Spring vẫn phải map verified principal tới local user, load authorities và kiểm tenant/resource. Không tự cấp `ROLE_ADMIN` chỉ vì Kerberos exchange thành công.

## 1. Mục tiêu học tập và phạm vi

Sau bài này, người học có thể:

- Vẽ luồng AS-REQ/TGT → TGS-REQ/service ticket → HTTP SPNEGO AP-REQ → Spring authentication.
- Giải thích **realm** khác AD domain suffix, DNS hostname, UPN suffix hoặc Spring tenant như thế nào.
- Thiết kế test sai realm có/không có cross-realm trust và phân biệt sai cấu hình với referral hợp lệ.
- Đo lệch đồng hồ client/KDC/server trên hai hướng, xác nhận `KRB_AP_ERR_SKEW` thay vì đoán.
- Kiểm SPN ownership, keytab contents, KVNO/encryption type, lỗi `KRB_AP_ERR_MODIFIED` và `KDC_ERR_ETYPE_NOSUPP`.
- Chạy lệnh chẩn đoán **chỉ đọc**, dùng MIT `klist/kvno/kinit` và Windows `setspn/klist/w32tm` đúng môi trường.
- Viết test phân loại trạng thái bằng **Java 17 runnable** với stdout xác định, hiểu giới hạn của demo.
- Tổ chức kiểm thử tầng giao thức thật với test realm/AD staging, browser và Spring Security filter.
- Tạo runbook thu hồi credential, đồng bộ NTP và keytab rotation an toàn.

**Không bao gồm** cách vượt kiểm vé Kerberos, trích xuất secrets người dùng, bẻ khóa ticket hoặc cấp quyền admin cho user. Chỉ thử với KDC, tài khoản dịch vụ, service principal và môi trường được phép quản trị.

## 2. Kerberos SSO hoạt động như thế nào?

~~~text
Browser/OS                   KDC / AD Domain Controller             Spring SPNEGO service
    |                                   |                                 |
    | AS-REQ (login)                    |                                 |
    |---------------------------------->|                                 |
    |<--------------------- AS-REP + TGT                                  |
    |                                   |                                 |
    | TGS-REQ for HTTP/portal...        |                                 |
    |---------------------------------->|                                 |
    |<---------- TGS-REP: service ticket                                   |
    |                                                                     |
    | GET https://portal...                                            |
    |-------------------------------------------------------------------->|
    |<---------------------------------- 401 WWW-Authenticate: Negotiate |
    |                                                                     |
    | GET Authorization: Negotiate <SPNEGO token / AP-REQ>                 |
    |-------------------------------------------------------------------->|
    |                                                  Load service keytab |
    |                                                  GSS accept context |
    |                                                  Check AP authenticator
    |                                                  Verify service ticket |
    |                                                  Resolve user principal|
    |                                                  Load local permissions
    |<----------------------------------------- app response / challenge |
~~~

**Đừng nhầm:**
- **TGT**: ticket để xin các service tickets, không phải thứ browser gửi trực tiếp cho ứng dụng Spring.
- **Service ticket**: được KDC phát cho service principal/realm; server dùng secret tương ứng để giải mã/xác minh.
- **SPNEGO**: cơ chế thương lượng trong HTTP `Negotiate`; về thực tế có thể chọn Kerberos hoặc cơ chế khác tùy môi trường. Không giả định header `Negotiate` luôn chứa Kerberos hợp lệ.
- **Acceptor**: service/JVM nhận Kerberos token, thường dùng JAAS/GSS và keytab.
- **KDC/realm trust**: quyết định principal/service nào có thể được cấp tickets; **không cùng lớp** với Spring `UserDetailsService`.

## 3. Phân biệt realm, domain, UPN, SPN và tenant

| Tên | Ví dụ | Dùng ở đâu? | Sai lầm điển hình |
| --- | --- | --- | --- |
| Kerberos realm | `CORP.EXAMPLE.TEST` | KDC, ticket principal namespace | Nghĩ realm luôn là DNS suffix |
| AD DNS domain | `corp.example.test` | Directory/DNS | Coi mọi UPN suffix là realm |
| User principal | `alice@CORP.EXAMPLE.TEST` | Client/KDC | Tách `alice` rồi gộp mọi realms |
| HTTP service principal | `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST` | KDC/acceptor | Đổi sang máy backend dù browser truy cập VIP |
| UPN suffix | `alice@example.test` | AD login names | Dùng UPN suffix làm bằng chứng KDC realm |
| Host/SPN alias | `portal.example.test` | HTTP/Negotiate, KDC lookup | DNS CNAME khác SPN đăng ký |
| Keytab | `/etc/security/keytabs/portal.keytab` | Server acceptor secret store | Coi keytab là public metadata |
| Tenant | `north` | Application authorization | Suy ra tenant từ realm rồi auto-admin |

**Realm thường viết hoa theo quy ước**, nhưng ý nghĩa chính xác đến từ cấu hình realm/KDC và trust. Không tự uppercase/lowercase **một identity key đã xác minh** mà chưa hiểu mapping provider. DNS domain, UPN suffix, IdP tenant và Kerberos realm có thể liên quan nhưng không hoàn toàn đồng nhất.

**Ứng dụng đa miền:** cùng local username có thể tồn tại trong hai realms; cần map verified principal **gắn namespace nguồn** (realm/canonical principal) đến local account, không lookup chỉ bằng `getName().split("@")[0]`.

## 4. Ba pha có thể sinh lỗi khác nhau

| Pha | Việc xảy ra | Lỗi điển hình |
| --- | --- | --- |
| **AS exchange** | Client chứng minh danh tính với KDC và nhận TGT | Wrong client realm, principal unknown, clock skew, preauth errors |
| **TGS exchange** | Client xin service ticket cho đúng SPN/realm | Service SPN unknown/duplicate, wrong referral/cross-realm trust, enctype mismatch |
| **AP exchange** | Browser gửi AP-REQ cho Spring/JVM service | Service cannot decrypt ticket, wrong keytab/KVNO/etype, clock skew, replay |

Một `GSSException` tại backend thường báo **AP exchange** hoặc bước JAAS acceptor startup. Không phải lỗi nào cũng do service account password; một `401 Negotiate` có thể là **challenge bình thường** ở đầu flow.

**Cần định vị:** lỗi xảy ra trước TGT, trước TGS, khi lấy token từ browser, hay khi backend xác minh? Kết quả đó quyết định lệnh chẩn đoán tiếp theo.

## 5. Chuẩn bị một test lab đáng tin

**Môi trường staging tách biệt production** nên có:

- Realm A: `CORP.EXAMPLE.TEST` và KDC hoặc AD test.
- Tùy bài cross-realm: realm B `PARTNER.EXAMPLE.TEST`, trust/referral được bật **chỉ ở case hợp lệ**.
- Service account riêng, SPN `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST`.
- Keytab tạo bởi administrator cho chính service account trong lab; quản lý như secret.
- Spring Boot/JDK 17+ server với Spring Security Kerberos extension và web endpoint `/secure/whoami`.
- Một browser có SPNEGO trust policy đúng, một browser profile sạch và một client MIT Kerberos cho negative tests.
- NTP/chrony/Windows Time Service và khả năng **giả lập lệch giờ ở VM/container lab** (không sửa thời gian domain controller production).
- DNS A/CNAME/SRV records đã biết để test hostname/SPN.
- Logging có correlation ID và redaction: không dump `Authorization: Negotiate`, keytab, tickets, session secrets.

**Bảng fixture** cần chốt trước: principal, realm, SPN, keytab path, KVNO, enctype, KDC endpoint, version Spring/JDK, browser policy, clock-skew threshold và expected account mapping. Ghi checksum/file version của keytab trong lab **không** ghi nội dung key.

## 6. Happy path làm chuẩn đối chiếu

**Given** client đã có TGT đúng, SPN duy nhất, service keytab đồng bộ, clocks synchronized và Spring config đúng.

**When** browser truy cập `https://portal.corp.example.test/secure/whoami` và hoàn tất SPNEGO.

**Then**:
1. Có Kerberos service ticket cho SPN HTTP tương ứng.
2. Spring acceptor xử lý ticket thành công.
3. Application nhận verified principal có realm mong đợi.
4. Principal được link vào đúng local account đang active.
5. Quyền `ROLE_VIEWER` được cấp từ server-side policy, không từ raw HTTP header.
6. Request hợp lệ được trả nội dung giới hạn theo authorization.
7. TGT/service ticket còn hiệu lực và replay protection vẫn hoạt động.
8. Không có user/password hoặc raw tickets trong logs.

**Một HTTP 200 đơn độc chưa chứng minh Kerberos pass.** Có thể browser được cho vào nhờ anonymous route, session cũ, cookie, NTLM fallback hoặc Basic authentication. Kiểm `Authentication` actual class/provider và security mechanism đã dùng.

## 7. Wrong realm: tình huống thực sự nghĩa là gì?

**Realm mismatch** có thể xảy ra khi:

1. Client yêu cầu TGT cho sai realm.
2. Client tìm KDC của realm sai vì `krb5.conf`/DNS mappings.
3. Client xin service ticket cho SPN mà KDC không biết.
4. Service ticket cho realm B được trình cho acceptor chỉ có keytab realm A và không có trust/delegation.
5. User realm B đăng nhập thành công qua cross-realm trust nhưng app mapping lại coi là user realm A.
6. UPN suffix trong AD bị hiểu nhầm thành Kerberos realm.
7. Reverse proxy/alias làm client xin SPN trên hostname khác với tài khoản dịch vụ đã đăng ký.
8. Referrals/canonicalization biến principal thành dạng khác với ứng dụng mong đợi.

**Không dùng một mã lỗi duy nhất để đại diện cho mọi wrong realm.** Có thể thấy `KDC_ERR_WRONG_REALM` trong referral-related exchanges, `KDC_ERR_S_PRINCIPAL_UNKNOWN` khi SPN không tìm thấy, `KRB_AP_ERR_MODIFIED` nếu service không giải mã được ticket hoặc lỗi client-side principal mapping; tùy giai đoạn/cấu hình.

**Cross-realm trust hợp lệ là ngoại lệ có thiết kế:** user realm B có thể lấy ticket cho service realm A thông qua referral/TGT chain. **Không được từ chối chỉ vì client realm khác service realm** nếu policy cho phép; thay vào đó xác minh trust path, service target và identity namespace tại app.

## 8. krb5.conf: default_realm và domain_realm

Ví dụ cấu hình cho **test MIT Kerberos**:

~~~ini
[libdefaults]
  default_realm = CORP.EXAMPLE.TEST
  dns_lookup_realm = false
  dns_lookup_kdc = false
  clockskew = 300

[realms]
  CORP.EXAMPLE.TEST = {
    kdc = kdc1.corp.example.test
  }
  PARTNER.EXAMPLE.TEST = {
    kdc = kdc1.partner.example.test
  }

[domain_realm]
  .corp.example.test = CORP.EXAMPLE.TEST
  corp.example.test = CORP.EXAMPLE.TEST
  .partner.example.test = PARTNER.EXAMPLE.TEST
  partner.example.test = PARTNER.EXAMPLE.TEST
~~~

**Đây là ví dụ lab, không phải cấu hình production**. Khi sử dụng AD với DNS SRV và referrals, chính sách discovery và mapping có thể khác. MIT `krb5.conf` hỗ trợ `[realms]`, `[domain_realm]`, `[capaths]` và các tham số canonicalization/DNS.

**Không “sửa” wrong realm bằng wildcard cho mọi host**. Ghi exact expected realm, kiểm KDC trust, DNS mapping, SPN registration và ứng dụng chấp nhận principal nào.

## 9. Kiểm wrong realm theo từng tầng

**Test R1 — Sai realm của user:**
- Client cố dùng `alice@PARTNER.EXAMPLE.TEST` trong khi tài khoản chỉ thuộc Corp, không có identity tương ứng.
- Kỳ vọng: client không lấy được TGT/ticket như `alice@CORP.EXAMPLE.TEST`; **không tự fallback thành account Corp**.

**Test R2 — Sai realm khi xin service ticket:**
- Với TGT Corp, yêu cầu SPN `HTTP/portal.partner.example.test@PARTNER.EXAMPLE.TEST` không thuộc đúng target.
- Kỳ vọng: tùy trust, KDC từ chối hoặc cấp đúng service ticket Partner; **Corp service không được accept như Corp**.

**Test R3 — Cross-realm có trust:**
- User Partner được phép truy cập Corp SPN theo trust.
- Kỳ vọng: AP exchange hợp lệ **nếu** service/key và trust path đúng, principal vẫn giữ namespace Partner; app membership quyết định quyền.

**Test R4 — Cross-realm không trust:**
- User Partner không có referral/trust tới Corp.
- Kỳ vọng: không có service ticket hợp lệ hoặc không hoàn tất AP; không bypass bằng Basic/login fallback.

**Test R5 — Same username khác realms:**
- `alice@CORP...` và `alice@PARTNER...` là hai external identities.
- Kỳ vọng: không tự gộp local account vì tên giống nhau.

## 10. Vì sao DNS và HTTP SPN dễ gây nhầm realm?

Browser lấy URL `https://portal.corp.example.test`, Kerberos HTTP SPN thường dựa trên **tên host mà client/GSS chọn sau quy tắc canonicalization**, ví dụ `HTTP/portal.corp.example.test`. Nếu reverse proxy dùng alias, CNAME hoặc VIP, service principal có thể khác tên máy backend.

Ví dụ:

~~~text
Browser URL: https://portal.corp.example.test
DNS CNAME:   portal.corp.example.test -> ingress-01.internal.test
Backend:     app-07.internal.test

Expected service principal by contract:
  HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST

Wrong candidates:
  HTTP/app-07.internal.test@CORP.EXAMPLE.TEST
  HTTP/portal.partner.example.test@PARTNER.EXAMPLE.TEST
~~~

**Không mặc định Kerberos luôn sử dụng đúng host từ URL**: một số clients canonicalize qua DNS hoặc dùng SPN generation rules riêng. Test actual service ticket principal bằng `klist`/`kvno` trên client và đối chiếu KDC/SPN registry.

**Trong AD**, kiểm SPN thuộc đúng account bằng `setspn -Q HTTP/portal.corp.example.test`. Nếu SPN nằm trên tài khoản khác, KDC có thể mã hóa service ticket bằng secret **không có trong keytab** của ứng dụng, dẫn tới lỗi integrity/AP.

## 11. Clock skew: ngưỡng 300 giây đến từ đâu?

Kerberos dùng timestamps trong authenticator và validity windows để chống **replay**. Nếu chênh lệch đồng hồ của client/service/KDC vượt allowed skew, một số request sẽ bị từ chối.

Ở MIT Kerberos, `clockskew` trong `krb5.conf` có **mặc định 300 giây**. JDK Kerberos cũng có thông số tương ứng; **deployment có thể cấu hình khác** hoặc AS/KDC áp chính sách khác.

**Phân biệt:**
- `KRB_AP_ERR_SKEW`: thường xuất hiện ở pha application AP khi authenticator timestamp nằm ngoài cửa sổ cho phép của acceptor.
- `KRB5KRB_AP_ERR_TKT_EXPIRED` / expired ticket: ticket hết lifetime; không nên nhầm với lệch giờ.
- `KRB_AP_ERR_REPEAT`: có thể liên quan replay cache/Authenticator reuse, không phải luôn là clock skew.
- `KDC_ERR_SKEW` hoặc KDC pre-auth failures: có thể phát sinh giữa client và KDC tùy phase.
- Clock lệch **client↔KDC** khác clock lệch **client↔server**; cần đo đủ cả ba thành phần.

**Lệch 299 giây có thể vẫn vượt giới hạn thực tế nếu còn network delay, KDC/acceptor policy khác hoặc ticket lifetime constraints.** Đừng đo 300 giây rồi cho kết luận pass biên tuyệt đối với mọi Kerberos stack.

## 12. Thiết kế test lệch giờ hai chiều

Một lab có clock skew limit 300 giây:

| Test | Client so với acceptor | Kỳ vọng khái niệm |
| --- | ---: | --- |
| T0 | 0s | Pass nếu các điều kiện khác đúng |
| T1 | +30s | Thường pass dưới ngưỡng |
| T2 | -30s | Thường pass |
| T3 | +299s | Biên sát, test có thể nhạy theo delay |
| T4 | -299s | Biên sát, test có thể nhạy theo delay |
| T5 | +301s | Từ chối do skew nếu thật sự ngoài ngưỡng |
| T6 | -301s | Từ chối do skew |
| T7 | +900s | Từ chối chắc chắn với limit 300s, trừ setup sai |
| T8 | -900s | Từ chối chắc chắn với limit 300s |
| T9 | Client/KDC lệch nhưng client/server đồng bộ | Có thể fail ngay AS/TGS, không phải AP |
| T10 | KDC/server lệch nhưng client/KDC đồng bộ | Ticket validity/AP behavior cần điều tra theo phase |

**Cảnh báo:** chỉ giả lập thời gian trong **test VMs/containers được cô lập**, không chỉnh NTP/domain controllers hoặc service production. Test ticket lấy mới sau khi đổi giờ cần chú ý ticket lifetime, cached TGT và Kerberos clock correction; purge test credentials trước mỗi case khi cần.

**Đặt SLA vận hành** giữ clock lệch thực tế thấp hơn nhiều so với skew tolerance. Không tăng mặc định 5 phút thành 30 phút chỉ để suppress lỗi.

## 13. Đo đồng hồ và dịch vụ đồng bộ thời gian

Trên Linux/staging host:

~~~bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
~~~

Đây là **lệnh chỉ đọc**; `chronyc` cần chrony có cài đặt và service hoạt động. Với môi trường NTP khác, dùng công cụ tương đương. Đo thời gian trên **client, KDC, SP** gần đồng thời và xem offset/root delay, không chỉ nhìn múi giờ địa phương.

Trên Windows (PowerShell/CMD):

~~~powershell
w32tm /query /status
w32tm /query /peers
Get-Date -Format o
~~~

**Múi giờ hiển thị khác nhau không đồng nghĩa có clock skew**: Kerberos dùng timestamps dựa thời gian tuyệt đối (UTC). Hai máy hiển thị local time khác nhưng UTC đúng vẫn có thể authenticate.

**Không chạy** lệnh chỉnh giờ hoặc restart Windows Time Service trên DC production khi không có change approval. Dùng test VM snapshot/NTP lab và ghi chính xác offset từng case.

## 14. Kerberos keytab thực sự lưu gì?

**Keytab** là tập các entries dạng **Kerberos principal + encryption type + key version number (KVNO) + secret key**. Nó cho JVM acceptor dùng secret tương ứng để giải mã/xác minh service ticket mà không lưu plaintext password trong application config.

Ví dụ:

~~~text
Principal (service):
  HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST

Ticket encrypted with:
  KVNO = 7
  enctype = aes256-cts-hmac-sha1-96
  service key = derived/stored secret for SPN's account

Keytab has:
  HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
  KVNO = 7
  same supported enctype
  matching key material
~~~

**Tên, KVNO và enctype giống nhau chưa đủ**: nếu account password đã reset hoặc keytab được xuất từ sai account/secret, key bytes không khớp và AP decrypt sẽ thất bại.

**Keytab là credential có độ nhạy cao.** Không commit vào Git, container image công khai, Slack/ticket, artifact build logs, hoặc chụp nội dung base64. Dùng secret vault/volume, file permissions và rotation process có owner.

## 15. Ba loại mismatch keytab phải phân biệt

| Mismatch | Cách phát sinh | Cách kiểm |
| --- | --- | --- |
| **Principal/SPN** | Ticket cho HTTP/portal, keytab chỉ chứa HTTP/backend | Inspect ticket service principal và keytab principal |
| **KVNO** | Service account password/key rotation làm version tăng; pod dùng keytab cũ | `kvno` / `klist -k -e` và target KDC state |
| **Enctype** | KDC phát AES key nhưng keytab/JAAS chỉ có RC4 hoặc bị policy chặn | `klist -k -e`, ticket encryption, JDK allowed etypes |
| **Key material** | Same principal/KVNO/etype nhưng keytab tạo bằng password/account khác | Decrypt verification test, controlled regeneration |
| **File/config** | Keytab sai path, thiếu quyền đọc, mount sai pod/namespace | Check permissions/volume/release config |
| **Service account/SPN owner** | Duplicate SPN, SPN đăng ký ở wrong AD account | `setspn -Q/-X`, AD ownership |
| **KVNO drift across nodes** | Rolling deploy pod A keytab v7, pod B v8 | Check every pod/version; staged overlap |

**`KRB_AP_ERR_MODIFIED` không có nghĩa chắc chắn keytab thiếu KVNO**. Microsoft ghi nhận nó có thể do SPN trên sai account, DNS/cluster alias, key/password khác, trust/etype hay cấu hình khác. Luôn đi từ ticket principal và actual acceptor key, không sửa ngẫu nhiên.

## 16. Kiểm nội dung keytab trên MIT Kerberos

Trên host chứa **keytab của môi trường test**, dùng:

~~~bash
klist -kte /etc/security/keytabs/portal.keytab
~~~

Ý nghĩa:
- `-k`: liệt kê entries trong keytab thay vì ticket cache.
- `-t`: hiển thị timestamps của entries.
- `-e`: hiển thị encryption type.
- KVNO có trong output theo implementation.

**Không hiển thị secret key bằng cách chọn option xuất key material**. Bản thân file keytab là secret, nhưng danh sách principal/KVNO/etype cũng có thể nhạy cảm; log phải được kiểm soát.

**Giới hạn:** output chỉ chứng minh **keytab chứa entries**; không chứng minh secret thực sự khớp với KDC. Dùng một test giải mã service ticket đúng SPN hoặc SPNEGO E2E để xác nhận.

## 17. Kiểm service ticket và KVNO bằng kvno

Với client đã có TGT hợp lệ trong lab:

~~~bash
klist
kvno HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
~~~

`kvno` có thể yêu cầu service ticket và in **KVNO mà KDC phát**. Để thử giải mã ticket bằng keytab **khi phiên bản MIT hỗ trợ**, có thể dùng:

~~~bash
kvno -k /etc/security/keytabs/portal.keytab HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
~~~

**Ý nghĩa của `kvno -k`:** thử decrypt ticket đã lấy để xác minh keytab có matching service key. Nếu operation thất bại, so SPN, KVNO, enctype và key material. Đây là bài test hữu ích hơn việc chỉ đọc keytab entries.

**Chú ý:** `kvno -k` là tiện ích MIT; Windows `klist` không có cùng cú pháp, và những môi trường không cho phép lấy TGT service account có thể cần một client principal riêng để request service ticket. Không sửa quyền service account production chỉ để một bài kiểm thử `kinit` pass.

## 18. kinit -k -t kiểm được gì và không kiểm được gì?

Ví dụ trong **test realm**:

~~~bash
kinit -k -t /etc/security/keytabs/portal.keytab HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
~~~

Ý nghĩa: client cố dùng keytab để **lấy initial credentials/TGT cho principal**, không đơn giản là thử accept một service ticket. Kết quả tùy KDC policy: service principals có thể không được phép/không phù hợp dùng như AS client.

**Không coi kinit -k failure là bằng chứng tuyệt đối keytab không decrypt được service ticket.** Với Kerberos HTTP acceptor, phù hợp hơn là:
1. Client user lấy TGT hợp lệ.
2. Client yêu cầu service ticket cho đúng SPN.
3. Dùng `kvno -k` hoặc thật sự gửi `Authorization: Negotiate` tới JVM acceptor.
4. Kiểm log GSS và authenticated principal.

**Không cần tự lấy TGT service account bằng mật khẩu thật** nếu test objective chỉ là acceptor keytab.

## 19. Windows AD: xác minh SPN ownership và ticket cache

Trên Windows domain-joined test workstation/server:

~~~powershell
klist tickets
klist tgt
setspn -Q HTTP/portal.corp.example.test
setspn -X
~~~

- `klist tickets`: liệt kê tickets được cache ở logon session hiện tại.
- `klist tgt`: xem TGT theo quyền/phiên.
- `setspn -Q`: tìm account sở hữu SPN cụ thể.
- `setspn -X`: tìm duplicate SPNs theo scope của tool/AD.

**Đọc kết quả bằng đúng quyền và miền**; một số kiểm tra forest-wide cần quyền/tuỳ chọn phù hợp. Đặc biệt với cross-forest trust, collision có thể tồn tại ở nhiều trusted forests, không thấy hết chỉ qua một lệnh trong một domain.

**Không chạy `setspn -D/-S` hoặc reset password ngay** khi chưa xác minh AD owner và kế hoạch rotation. Các thay đổi SPN có thể tác động tất cả services dùng account đó.

## 20. Ticket cache và phép thử âm tính

Một browser/OS có thể vẫn giữ TGT hoặc service ticket cũ sau khi bạn đổi keytab/SPN. Do đó test cần phân biệt:

- **Cached old ticket** trước account password rotation.
- **New ticket** với KVNO mới sau KDC cập nhật.
- **Old keytab** trên một subset pods.
- **New keytab** đã được deploy nhưng JVM/JAAS chưa reload keys.
- **Browser fallback** sang NTLM/Basic khiến UI vẫn “đăng nhập được”.

Trong **staging**, có thể dùng công cụ xóa ticket cache phù hợp để buộc cấp ticket mới; ví dụ MIT `kdestroy` hoặc Windows `klist purge` theo chính sách test. **Đây là thao tác làm thay đổi trạng thái xác thực hiện hành**: chỉ chạy trên tài khoản/VM test được phép, không purge TGT của người dùng đang làm việc hoặc service production.

Test phải ghi rõ **ticket được phát trước hay sau rotation**. Một AP request dùng old ticket có thể còn hoạt động trong overlap window nếu service còn old key và policy cho phép; điều này không nhất thiết là bug.

## 21. Key version rotation: thứ tự triển khai an toàn

Một keytab rotation thiếu điều phối có thể làm service down ngẫu nhiên:

~~~text
t0 KDC/service account dùng KVNO=7, pods keytab v7 -> OK
t1 Password/key rotate ở AD/KDC -> service ticket mới KVNO=8
t2 Pod A đã có v8, Pod B vẫn v7
t3 Browser load balanced tới pod B -> AP decrypt thất bại
t4 Rotation hoàn thành -> mọi pod cùng đúng keys, service OK
~~~

**Kế hoạch an toàn:**
1. Chốt SPN/account owner, keytab output và supported enctypes.
2. Lên maintenance/change window, test realm trước.
3. Phối hợp key rollover/overlap theo KDC/AD behavior và app support; **không giả mọi keytabs được giữ nhiều KVNO tự động**.
4. Roll out keytab qua secret-management system, kiểm permissions.
5. Bật health/acceptor test ở mọi pod và actual SPNEGO E2E.
6. Xác nhận service ticket phát với KVNO mới và mọi nodes giải mã được.
7. Theo dõi ticket lifetime và old key expiry; retire old keys theo policy.
8. Có rollback **có tổ chức**, không tự reset password liên tục hoặc chép keytab của môi trường khác.

**Không dùng “thử export keytab nhiều lần từ account password mới”** để chữa: mỗi lần reset có thể thay đổi KVNO và làm tệ hơn.

## 22. Enctype mismatch, JDK policy và AD

**Encryption type (enctype)** quyết định thuật toán dùng trong ticket/service key. Lỗi có thể xảy ra khi KDC phát ticket bằng enctype không có trong keytab hoặc bị JDK/service account/domain policy vô hiệu hóa.

Ví dụ:
- KDC yêu cầu AES256 nhưng keytab chỉ có key RC4 cũ.
- Service account chưa có AES keys tương ứng sau đổi policy/password.
- Ticket key KVNO đúng nhưng enctype khác keytab.
- Java 17 runtime/security policy không bật/enforce enctype đã chọn.
- Cross-realm trust có enctypes không tương thích.

**Không bật DES/RC4 hoặc `allow_weak_crypto=true` làm giải pháp mặc định**. Ưu tiên AES được tổ chức hỗ trợ; đồng bộ KDC, account encryption flags, keytab generation và Java runtime. Các chính sách cũ cần xử lý bằng migration có owner/chấp thuận.

**Lưu ý:** một lỗi `KDC_ERR_ETYPE_NOSUPP` thường liên quan pha KDC issuing ticket; `KRB_AP_ERR_MODIFIED` hoặc GSS accept failure thường liên quan pha AP service decryption. Cần xem logs và trace đúng phase.

## 23. Ứng dụng Spring dùng thành phần nào cho SPNEGO?

**Spring Security Kerberos** là **extension/module** riêng, không phải chức năng tự có khi chỉ thêm `spring-boot-starter-security`. Trong stack Servlet, các thành phần thường gặp:

| Thành phần | Vai trò |
| --- | --- |
| `SpnegoEntryPoint` | Gửi challenge HTTP `WWW-Authenticate: Negotiate` |
| `SpnegoAuthenticationProcessingFilter` | Đọc `Authorization: Negotiate` và đưa token tới AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Sử dụng ticket validator và load user details |
| `SunJaasKerberosTicketValidator` | JAAS/GSS acceptor với SPN và keytab |
| `UserDetailsService` | Ánh xạ Kerberos principal sang local account/authorities |
| `SecurityFilterChain` | Bảo vệ URL, filter ordering/entrypoint và fallback policy |
| `SecurityContext` | Lưu kết quả authentication theo session/repository strategy |

**Tầng nào kiểm realm/keytab/clock?** GSS/Kerberos trong JVM và KDC thực hiện protocol checks; Spring provider chuyển kết quả thành Authentication. **Không tự so chuỗi realm/đếm 300s ở controller rồi nghĩ đã verify ticket**.

**Tầng nào kiểm business quyền?** UserDetailsService và authorization layer của app. Ticket hợp lệ không có nghĩa `ROLE_ADMIN`.

## 24. Mảnh cấu hình Spring Security Kerberos đúng phạm vi

Ví dụ một phần cấu hình **trong dự án Spring có Kerberos extension**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class KerberosValidatorConfig {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator v =
                new SunJaasKerberosTicketValidator();
        v.setServicePrincipal(
                "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST");
        v.setKeyTabLocation(
                new FileSystemResource(
                    "/run/secrets/kerberos/portal.keytab"));
        v.setDebug(false);
        return v;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            org.springframework.security.core.userdetails.UserDetailsService
                    userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }
}
~~~

**Đây là class cấu hình phụ thuộc thư viện**, chưa phải full application: phải có Kerberos extension tương thích Spring/Security Boot BOM, `UserDetailsService` thật, `SpnegoAuthenticationProcessingFilter`, entry point và `SecurityFilterChain` được wiring đúng. Đây **không phải chương trình Java 17 độc lập**.

**Quan trọng để test:** `setServicePrincipal` phải khớp tên service thật từ SPN/KDC; keytab path là secret mount đã được cấp quyền. Không dùng `setDebug(true)` lâu dài ở production vì log protocol/identity có thể nhạy cảm.

## 25. JAAS và Java GSS: chẩn đoán có kiểm soát

Một số hệ dùng `Krb5LoginModule` làm acceptor. JAAS configuration mẫu **chỉ cho môi trường test đã xác minh JDK/provider**:

~~~text
com.example.KerberosAcceptor {
  com.sun.security.auth.module.Krb5LoginModule required
  useKeyTab=true
  keyTab="/run/secrets/kerberos/portal.keytab"
  principal="HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST"
  storeKey=true
  isInitiator=false
  doNotPrompt=true
  useTicketCache=false
  debug=false;
};
~~~

Các JVM flags hỗ trợ debug môi trường test:

~~~bash
java -Djava.security.krb5.conf=/etc/krb5.conf \
     -Dsun.security.krb5.debug=true \
     -jar app.jar
~~~

**Đây là lệnh minh họa cho Unix shell và dự án có app.jar**, không tự tạo keytab/tài khoản. Debug có thể lộ service principals, realms, ticket metadata và SPN lookup; chỉ bật khi có quyền, thời gian ngắn và có log redaction/retention.

**Không kết luận success chỉ từ log "Found key for principal"**. App còn cần accept thực tế AP-REQ, GSS context established, user principal đúng và authorization pass.

## 26. Phân biệt HTTP challenge bình thường với lỗi

Trong SPNEGO, request đầu tiên chưa có token có thể nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
Cache-Control: no-store
~~~

Browser có thể tự trả:

~~~http
GET /secure/whoami HTTP/1.1
Host: portal.corp.example.test
Authorization: Negotiate BASE64_SPNEGO_TOKEN
~~~

**401 ở round đầu không phải lỗi**. Nhưng nếu đã có Negotiate header mà server tiếp tục 401, hãy kiểm:
- Browser có gửi Kerberos chứ không phải NTLM fallback?
- Đúng SPN/hostname từ ticket?
- Keytab đọc được trong JVM process và có đúng secret?
- Realm trust và KDC referrals đúng?
- Clock skew nhỏ hơn policy?
- Có SecurityFilterChain/filter ordering đúng?
- Cổng proxy có strip/chuyển tiếp Authorization header không?

**Đừng log nguyên Base64 token**. Nó là security credential có thể nhạy cảm.

## 27. Java 17 độc lập: test logic phân loại ba nhóm lỗi

Ví dụ sau **chạy thuần JDK 17**, mô hình hóa các thông tin **được quan sát sau một quá trình kiểm tra tin cậy**: expected realm/SPN, clock offset, KVNO, enctype và kết quả kiểm key. Nó **không xác minh cryptographic Kerberos ticket**, không thay JAAS/GSS, không đọc keytab thật và không nên dùng trong production để quyết định Authentication.

Tạo file **KerberosFailureMatrixDemo.java**:

~~~java
import java.util.Set;

public class KerberosFailureMatrixDemo {

    record Evidence(
            String realm,
            String servicePrincipal,
            long clientTimeSeconds,
            long serviceTimeSeconds,
            int ticketKvno,
            int keytabKvno,
            String ticketEtype,
            Set<String> keytabEtypes,
            boolean matchingSecret,
            boolean replayed) {}

    static final String EXPECTED_REALM = "CORP.EXAMPLE.TEST";
    static final String EXPECTED_SPN =
            "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST";
    static final long BASE = 1_700_000_000L;
    static final long MAX_SKEW = 300L;

    static String diagnose(Evidence e) {
        if (!EXPECTED_REALM.equals(e.realm())) {
            return "DENY_REALM";
        }
        if (!EXPECTED_SPN.equals(e.servicePrincipal())) {
            return "DENY_SPN";
        }
        if (Math.abs(e.clientTimeSeconds()
                - e.serviceTimeSeconds()) > MAX_SKEW) {
            return "DENY_CLOCK_SKEW";
        }
        if (!e.keytabEtypes().contains(e.ticketEtype())) {
            return "DENY_ETYPE";
        }
        if (e.ticketKvno() != e.keytabKvno()) {
            return "DENY_KVNO";
        }
        if (!e.matchingSecret()) {
            return "DENY_KEY_MATERIAL";
        }
        if (e.replayed()) {
            return "DENY_REPLAY";
        }
        return "PASS_PRECHECK";
    }

    static Evidence sample(
            String realm, String spn,
            long deltaSeconds, int kvno,
            String etype, boolean secret, boolean replayed) {
        return new Evidence(
                realm, spn, BASE + deltaSeconds, BASE,
                kvno, 7, etype,
                Set.of("aes256-cts-hmac-sha1-96"), secret, replayed);
    }

    public static void main(String[] args) {
        Evidence valid = sample(
                EXPECTED_REALM, EXPECTED_SPN, 0, 7,
                "aes256-cts-hmac-sha1-96", true, false);

        System.out.println("Valid: " + diagnose(valid));
        System.out.println("Wrong realm: " + diagnose(sample(
                "PARTNER.EXAMPLE.TEST", EXPECTED_SPN,
                0, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Wrong SPN: " + diagnose(sample(
                EXPECTED_REALM,
                "HTTP/other.corp.example.test@CORP.EXAMPLE.TEST",
                0, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Clock +301: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                301, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Clock -301: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                -301, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Clock +300: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                300, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Wrong KVNO: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 8, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Wrong enctype: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 7, "arcfour-hmac", true, false)));
        System.out.println("Wrong key material: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 7, "aes256-cts-hmac-sha1-96", false, false)));
        System.out.println("Replayed authenticator: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 7, "aes256-cts-hmac-sha1-96", true, true)));
        System.out.println("After safe repair: " + diagnose(valid));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac KerberosFailureMatrixDemo.java
java KerberosFailureMatrixDemo
~~~

**Stdout chính xác:**

~~~text
Valid: PASS_PRECHECK
Wrong realm: DENY_REALM
Wrong SPN: DENY_SPN
Clock +301: DENY_CLOCK_SKEW
Clock -301: DENY_CLOCK_SKEW
Clock +300: PASS_PRECHECK
Wrong KVNO: DENY_KVNO
Wrong enctype: DENY_ETYPE
Wrong key material: DENY_KEY_MATERIAL
Replayed authenticator: DENY_REPLAY
After safe repair: PASS_PRECHECK
~~~

**Giải thích:** code tách precedence: realm trước, SPN, skew, enctype, KVNO, key material rồi replay. Với test `+300s`, đây chỉ là **mô phỏng phép so ngưỡng math**; Kerberos thật còn chịu network latency, ticket validity, KDC/acceptor policy và replay cache. Không dùng kết quả demo để khẳng định Java GSS đã authenticate. Cross-realm trust thật **có thể cho phép user realm B**; demo cố tình dùng service realm fixed để minh họa negative case.

## 28. Vì sao code trên không thay thế Kerberos integration test?

**Spring Security Kerberos** dùng JAAS/GSS để xử lý token có cơ chế mật mã thật, có KDC và keytab. Bài Java chỉ làm classification bằng dữ kiện đã giả định đúng.

Không nên:
- Cho browser gửi `realm=CORP.EXAMPLE.TEST` và `matchingSecret=true` trong header rồi coi là authenticated.
- Lấy `kid/kvno` trong request làm proof của keytab.
- Gán local `ROLE_ADMIN` sau khi mô phỏng cho PASS.
- Chỉ test `Math.abs(clockDelta) <= 300` rồi nói đã test replay defense.
- Bỏ test actual service ticket giải mã bằng keytab.

Một integration test đạt yêu cầu phải tạo service ticket **bằng KDC test được kiểm soát**, gửi SPNEGO AP-REQ thật và kiểm server identity/authorization.

## 29. Kịch bản end-to-end sai realm

**Case RR-A — Realm mapping sai:**

Given DNS và `krb5.conf` của client cố ý map service hostname sang Partner realm trong lab. When xin service ticket cho Corp HTTP service. Then ticket không đúng intended service realm hoặc TGS fail; SP không tự chấp nhận Partner principal.

**Case RR-B — Realm thiếu trust:**

Given client TGT Partner, Corp service chỉ chấp nhận referrals/trust theo allowlist. When thử truy cập Corp service mà cross-realm trust không tồn tại. Then không hoàn tất authenticating chain; không fallback authentication mechanism yếu hơn.

**Case RR-C — Cross-realm trust hợp lệ:**

Given trust đã được cấu hình và test user Partner được app cho phép. When KDC cấp service ticket cho Corp SPN qua referrals. Then GSS verify service ticket, app bảo toàn verified client realm Partner, quyết định quyền qua local account policy.

**Case RR-D — Same username collision:**

Given `alex@CORP.EXAMPLE.TEST` và `alex@PARTNER.EXAMPLE.TEST`. When cả hai Kerberos logins đều đúng. Then app không gộp tài khoản nếu chưa có identity link có chứng cứ.

**Case RR-E — SPN alias và CNAME:**

Given browser truy cập `portal.corp...` nhưng client canonicalize sang tên khác. When request TGS. Then kiểm actual ticket SPN và keytab/SPN ownership; không tự sửa SPN bừa bãi.

## 30. Kịch bản end-to-end lệch giờ

**Case TT-A — Client nhanh hơn server:**
1. Trong lab VM, đặt client clock offset +8 phút so với SP/KDC.
2. Lấy TGT/service ticket mới theo cách test harness kiểm soát.
3. Gửi SPNEGO AP-REQ.
4. Kỳ vọng thất bại khi vượt policy; ghi phase KDC/AP thực tế và error code nếu có.
5. Hoàn nguyên clock/NTP, retry bằng ticket hợp lệ, kỳ vọng pass.

**Case TT-B — Client chậm hơn server:** offset -8 phút, các bước tương tự.

**Case TT-C — Client và KDC lệch, SP khớp KDC:** có thể fail từ preauthentication/TGS, đừng chỉ tìm log tại Spring.

**Case TT-D — Clock đúng nhưng ticket expired:** cần phân biệt invalid lifetime với skew.

**Case TT-E — NTP hồi phục sau network partition:** theo dõi resync, đồng thời ngăn session/token freshness drift.

**Không chỉnh clock trên production DC hoặc làm yếu skew policy**. Đặt threshold cảnh báo lệch giờ thấp hơn nhiều so với 300 giây. Test E2E phải xác định các clock offsets và trạng thái caches, không dựa vào timezone hiển thị.

## 31. Kịch bản end-to-end keytab mismatch

**Case KT-A — SPN khác:** ticket cho HTTP/portal nhưng keytab chứa HTTP/backend. Kỳ vọng AP decrypt reject.

**Case KT-B — Keytab cũ:** KDC đã rotate KVNO 8, service pod vẫn keytab KVNO 7. Kỳ vọng ticket mới không giải mã được nếu không còn key tương ứng.

**Case KT-C — Enctype không tương thích:** ticket AES, keytab chỉ RC4, không bật legacy crypto để thử sửa. Kỳ vọng fail và xác nhận etype mismatch.

**Case KT-D — Cùng KVNO nhưng khác secret:** test keytab export từ account sai; expected failure. Không sửa bằng cách hardcode service account password vào app.

**Case KT-E — Keytab không đọc được:** file missing, wrong path, volume mount/permissions. Kỳ vọng fail closed, health alert.

**Case KT-F — Duplicated/wrong-owner SPN:** KDC cấp ticket theo account khác; service không thể decrypt bằng own keytab. Kiểm `setspn -Q/-X` và actual owner.

**Case KT-G — Mixed deployment:** pod A keytab mới, pod B cũ. Run tests từng pod và qua load balancer; chẩn đoán lỗi ngẫu nhiên sau rotation.

**Case KT-H — Old cached ticket:** user còn service ticket KVNO 7; nếu service giữ only v8, ticket cũ có thể fail. Thiết kế overlap/retirement theo policy.

## 32. Bảng lỗi và phân biệt nguyên nhân

| Triệu chứng/mã lỗi | Nơi quan sát | Giải thích khả dĩ | Không được tự kết luận |
| --- | --- | --- | --- |
| `KRB_AP_ERR_SKEW` | AP/GSS accept | Đồng hồ client/service lệch quá policy | Không mặc định keytab sai |
| `KDC_ERR_SKEW`/preauth time error | KDC/AS/TGS | Client/KDC time skew | Không mặc định Spring filter lỗi |
| `KRB_AP_ERR_MODIFIED` | Client/Windows Event 4 | Service không decrypt/validate ticket đúng | Không chỉ KVNO, có thể SPN owner/DNS |
| `KRB_AP_ERR_BAD_INTEGRITY` | GSS/Kerberos | Integrity check không pass, secret/account mismatch | Không tự mở legacy etype |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC/TGS | SPN service chưa có hoặc sai realm | Không chỉ keytab path |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | AD KDC/TGS | Duplicate SPN/account trong phạm vi tìm | Không xoá SPN khi chưa xác minh ownership |
| `KDC_ERR_ETYPE_NOSUPP` | KDC | Không có enctype chung | Không tăng clock skew |
| `KRB_AP_ERR_REPEAT` | AP/replay cache | Trùng authenticator/replay hoặc timestamp/sequence | Không auto retry cùng AP token |
| `GSSException: No valid credentials provided` | JVM | Không nạp credentials/keytab/principal | Không chắc user password sai |
| `GSSException: Checksum failed` | JVM GSS | Service secret/key mismatch hoặc token integrity | Không chắc timestamp sai |
| `Cannot locate KDC` | Client/JVM | DNS SRV, krb5.conf, network/realm mapping | Không mặc định issuer SSO lỗi |
| HTTP `401 Negotiate` đầu flow | Browser ↔ Spring | Challenge bình thường | Không luôn là authentication failure |
| `403 Forbidden` sau principal valid | Spring authorization | Local account/role/tenant không có quyền | Không reset keytab để “sửa” |

**Mã lỗi là gợi ý, không phải diagnosis tuyệt đối.** Cùng symptom có thể do nhiều tầng; cần đối chiếu ticket/SPN/realm, clocks, keytab entries và trace trong thời gian tương ứng.

## 33. Spring integration tests nên assert gì?

Kiểm từ HTTP layer đến local authorization:

1. GET protected endpoint khi chưa gửi Negotiate token → **401 challenge** nếu endpoint yêu cầu SPNEGO và không có session authentication khác.
2. Browser gửi valid Kerberos AP-REQ → `KerberosServiceAuthenticationProvider` accept, local user mapped, expected authority được áp.
3. Wrong realm/no trust → **không tạo Authentication** và không fallback vào form/basic không được phê duyệt.
4. Wrong service principal → không accept token.
5. Clock skew ngoài policy → authentication fail, metrics được ghi đúng phase.
6. Keytab old KVNO/wrong key material → GSS accept fail, không tạo SecurityContext authenticated.
7. Ticket valid nhưng local account disabled → deny.
8. Ticket valid nhưng user không thuộc tenant → 403.
9. Same username từ hai realms → local accounts được phân biệt.
10. Token replay → reject theo GSS/replay policy.
11. Load balancer hai pods có keytab versions khác → test phát hiện lệch và request failure.
12. Authorization header bị proxy strip → phân loại network/proxy issue chứ không giả principal.
13. Browser dùng NTLM fallback → test phải biết cơ chế thực tế; không ghi nhận là Kerberos pass.
14. Logout/session expiry → tái xác thực đúng policy, không dùng stale SecurityContext.
15. Khi keytab mount inaccessible, không tự cấp `ROLE_USER` mà không verify.

**MockMvc không tự tạo một Kerberos service ticket có chữ ký KDC thật.** Tầng MockMvc có thể kiểm filter/entrypoint/provider error handling, nhưng muốn chứng minh realm/skew/keytab cần actual KDC/JAAS/GSS integration.

## 34. Kiểm thử trên browser thật: SPNEGO hay fallback?

Khi thử Chrome/Edge/Firefox trên workstation được domain trust:

- Kiểm intranet/trusted URI policy và thiết lập SPNEGO được phê duyệt.
- Kiểm browser URL hostname khớp SPN intended.
- Quan sát 401 `WWW-Authenticate: Negotiate` và request sau có Authorization.
- Xác minh **ticket service principal trong OS ticket cache** và GSS acceptor logs.
- Không dùng Basic login/session cookie/anonymous thành công làm bằng chứng Kerberos.
- Tách browser profile sạch với profile còn cookies/sessions.
- Thử first login, refresh, logout, user switch và multi-tab theo policy.
- Kiểm proxy TLS termination và HTTP Authorization forwarding.
- Test service URL alias/CNAME, không tự thay keytab khi DNS thay.
- Không lưu raw Negotiate token trong HAR/support ticket.
- Khi lỗi, xác định liệu KDC TGS cấp ticket trước khi Spring trả 401 hay chưa.

**SPNEGO successful challenge/response ≠ user được phép gọi business API**. Quyền phải đến từ local authorization của Spring.

## 35. Ma trận kiểm thử âm tính tổng hợp

| # | Test | Kết quả yêu cầu |
| --- | --- | --- |
| 01 | Same realm, SPN/keytab/clock đúng | Kerberos accept và đúng user |
| 02 | Wrong client realm, principal không tồn tại | Không có TGT hợp lệ |
| 03 | Wrong service realm, không trust | Không có service ticket hợp lệ |
| 04 | Cross-realm trust đúng và app cho phép | Login hợp lệ; bảo toàn client realm |
| 05 | Cross-realm trust đúng nhưng app không cho membership | 403 |
| 06 | Same username ở hai realms | Không gộp local account |
| 07 | UPN suffix khác actual Kerberos realm | Mapping không đoán mò |
| 08 | KDC realm DNS mapping sai | Fail, phân loại DNS/realm |
| 09 | Cross-forest referral thiếu trust | Không bypass |
| 10 | SPN canonicalization đổi sang CNAME | Detect actual SPN |
| 11 | Duplicate SPN trong AD | Có alert/deny theo KDC behavior |
| 12 | SPN thuộc wrong account | AP decrypt fail; phát hiện owner |
| 13 | Client/acceptor offset +30s | Pass nếu policy/conditions cho phép |
| 14 | Offset -30s | Pass nếu policy/conditions cho phép |
| 15 | Offset +301s với limit 300 | Reject khi thực tế ngoài bound |
| 16 | Offset -301s với limit 300 | Reject |
| 17 | Client/KDC lệch, SP đồng bộ | Phân loại AS/TGS failure |
| 18 | Client/SP lệch, KDC đồng bộ client | Phân loại AP failure |
| 19 | Ticket expired dù clock synchronized | Reject expired khác skew |
| 20 | Clock normal sau NTP fix | Kerberos pass lại |
| 21 | Keytab thiếu SPN | Reject |
| 22 | Keytab chứa wrong realm | Reject |
| 23 | Keytab KVNO 7, ticket KVNO 8 | Decrypt fail nếu no overlap key |
| 24 | KVNO đúng, secret khác | Decrypt fail |
| 25 | AES ticket, keytab thiếu AES key | Fail, không hạ crypto policy |
| 26 | Keytab missing/permission denied | Fail closed |
| 27 | JVM load keytab path sai | Fail closed |
| 28 | Keytab đúng nhưng pod A/B khác versions | Detect per-node failures |
| 29 | Browser cached old ticket sau rotate | Respect overlap/retire policy |
| 30 | New ticket/updated keytab trên mọi pods | Pass |
| 31 | Wrong HTTP SPN qua load balancer VIP | Fail hoặc chính sách mapping đã chứng minh đúng |
| 32 | Request không có Authorization header | 401 Negotiate challenge |
| 33 | Request có NTLM token dù test yêu cầu Kerberos | Không coi là Kerberos pass |
| 34 | Valid AP ticket nhưng account disabled | Deny |
| 35 | Valid AP ticket nhưng role thiếu | 403 |
| 36 | Valid AP ticket nhưng sai tenant | 403 |
| 37 | Untrusted X-User header không Kerberos | Không mạo danh principal |
| 38 | Replayed AP-REQ | Reject theo replay cache |
| 39 | Ticket/service principal trước rotation | Test documented behavior |
| 40 | Realm policy thay đổi nhưng JVM cache config cũ | Detect/restart/reconfigure có kiểm soát |
| 41 | KDC outage nhưng session local còn | Xử lý theo session/freshness policy |
| 42 | Proxy strip Authorization: Negotiate | Detect proxy issue |
| 43 | Timezone khác, UTC thực giống | Không false positive skew |
| 44 | MFA/service delegation thiếu trust | Không bỏ Kerberos validation |
| 45 | Keytab nằm trong container image public | Security policy fail; secret relocation |
| 46 | Secret mount read-only và least-privilege | Pass permissions |
| 47 | JVM debug true lâu dài | Audit privacy/security fail |
| 48 | Browser service hostname thay đổi | Test SPN/DNS/realm mapping |
| 49 | User mất group giữa two requests | Revocation/role freshness policy |
| 50 | Service account rotated nhưng second pod chưa update | Alert & rollback staged plan |

**Pass thật** phải bao gồm Kerberos mechanism, verified principal + realm, không có fallback ngoài policy, application membership, authorization và redacted logs.

## 36. Runbook chẩn đoán theo thứ tự

1. **Xác định phase**: AS, TGS, AP hay Spring authorization? Ghi error codes/hostname/timestamp.
2. **Xác nhận SPNEGO thực tế**: có challenge/Negotiate token hay browser dùng Basic/NTLM?
3. **Đối chiếu clocks**: client/KDC/acceptor UTC, NTP offset và skew policy.
4. **Kiểm realm**: TGT realm, ticket service realm, krb5.conf/AD DNS/UPN referrals.
5. **Kiểm actual SPN** trong service ticket; so với URL, DNS alias và application service principal.
6. **Kiểm AD SPN owner** bằng setspn read-only hoặc KDC config.
7. **Liệt kê keytab entries** (principal/KVNO/enctype), không dump secret key.
8. **So KVNO ticket vs keytab**; kiểm account rotation/change audit.
9. **Thử decrypt trong lab** bằng kvno -k (nếu MIT) hoặc SPNEGO acceptor E2E.
10. **Kiểm file mount/permissions và JVM JAAS config**, đúng node/pod.
11. **Kiểm local account/roles/tenant** nếu Kerberos đã authenticate.
12. **Fix đúng lớp**: NTP, DNS/realm mapping, SPN owner, keytab rotation, allowed etypes hoặc app membership.
13. **Chạy negative regressions** sau fix, không bỏ signature/replay/skew checks.
14. **Chốt audit/metrics**, mã lỗi và thời gian phục hồi.

**Không làm:** reset service account password nhiều lần theo cảm tính, mở `allow_weak_crypto=true`, tắt clock skew validation, chấp nhận mọi realm, chia sẻ keytab qua email hoặc log nguyên Kerberos AP token.

## 37. Quy trình kiểm thử có rollback an toàn

**Chuẩn bị lab:**
1. Snapshot test VM, ghi NTP source và trạng thái giờ.
2. Ghi SPN owner, KVNO/keytab version vào test inventory có ACL.
3. Tạo test users cho Corp/Partner realms, trust/no-trust variants.
4. Tạo một SPNEGO-protected endpoint, tách business authorization.
5. Đảm bảo keytab backup/rotation mechanism chỉ trong staging.

**Thực hiện:**
1. Baseline happy path.
2. Wrong realm/TGT, SPN unknown/duplicate, CNAME alias.
3. Clock skew +8/-8 phút trên **isolated VM**, không chạm DC production.
4. Enctype/keytab KVNO/secret mismatch bằng **staging secrets riêng**.
5. Test fresh tickets và cached tickets trước/sau rotation.
6. Test mỗi pod, browser, proxy route và local authorization.
7. Quan sát error phases, không chỉ HTTP statuses.

**Khôi phục:**
1. Bật đồng bộ NTP trở lại và chứng minh UTC offsets bình thường.
2. Rollback test SPN/realm mappings theo recorded baseline.
3. Restore authorized keytab version, test key rotation đúng KDC state.
4. Purge test ticket caches nếu cần theo change approval.
5. Đóng debug logs, loại thông tin nhạy cảm và verify secret mounts.
6. Rerun happy path, wrong realm, skew và keytab negative cases.
7. Lưu evidence có mã lỗi, môi trường, elapsed time, không raw tickets.

## 38. Observability và logging đúng

Các metrics đề xuất do application/infra tự instrument, **không mặc định Spring Security sinh toàn bộ**:

| Metric | Nội dung |
| --- | --- |
| `kerberos_spnego_challenge_total` | Số 401 Negotiate challenge |
| `kerberos_ap_accept_success_total` | GSS accept thành công |
| `kerberos_ap_accept_failure_total` | Failure theo nhóm mã Kerberos |
| `kerberos_wrong_realm_total` | Realm/trust mismatch |
| `kerberos_clock_skew_reject_total` | Rejection do time skew |
| `kerberos_keytab_decrypt_failure_total` | AP decrypt fail |
| `kerberos_spn_unknown_total` | Service principal lookup failures |
| `kerberos_kvno_mismatch_total` | Ticket vs keytab KVNO mismatch |
| `kerberos_etype_unsupported_total` | Encryption type không tương thích |
| `kerberos_fallback_mechanism_total` | NTLM/Basic fallback nếu cần giám sát |
| `kerberos_authenticated_user_denied_total` | Kerberos pass, business auth deny |
| `kerberos_keytab_rotation_lag_seconds` | Mất đồng bộ rollout giữa pods |

**Không log** raw ticket blobs, Negotiate Authorization header, keytab binary, service account password, session cookies hoặc user credential data. Có thể log pseudonymized principal realm, expected SPN, truncated error codes, pod, KDC contact time và correlation ID với access controls.

**Alerts quan trọng:** clock drift tiến gần ngưỡng policy, keytab KVNO khác KDC sau rotation, SPN owner changed, lỗi AP bất thường chỉ trên một pod, fallback NTLM tăng đột ngột, replay errors, user từ wrong realm nhận role đặc quyền.

## 39. Câu hỏi tự đánh giá

**1. Kerberos realm có phải AD DNS domain không?**  
Không nhất thiết. Chúng thường liên quan nhưng không đồng nhất; UPN suffix, DNS alias và client realm mapping có thể khác nhau.

**2. KRB_AP_ERR_SKEW thường chỉ ra vấn đề gì?**  
Lệch thời gian giữa initiator/acceptor ở AP phase vượt tolerance, cần đo UTC client/server/KDC.

**3. 300 giây có phải một hằng số bất biến của mọi Kerberos setup?**  
Không. Đây là default của MIT/JDK phổ biến, có thể cấu hình và có policy đặc thù.

**4. Keytab có KVNO bằng ticket là đủ để decrypt không?**  
Không. Còn principal/SPN, enctype, key material và keytab readable.

**5. kinit -k và kvno -k có giống nhau không?**  
Không. kinit -k cố lấy initial ticket từ keytab; kvno -k có thể lấy/giải mã service ticket bằng keytab.

**6. KRB_AP_ERR_MODIFIED có luôn là sai mật khẩu service account không?**  
Không. Có thể SPN wrong owner, DNS alias, keytab stale, wrong encryption key và nhiều nguyên nhân khác.

**7. Vì sao cùng username ở hai realms không nên gộp?**  
Vì đó là hai identities khác nhau, phải có authoritative linking proof.

**8. Nếu client dùng cached service ticket KVNO cũ sau rotation thì sao?**  
Có thể cần overlap policy; test ticket được phát khi nào và keytab nào còn trên acceptor.

**9. HTTP 401 Negotiate đầu flow có phải Kerberos thất bại?**  
Không, thường là challenge bình thường. Xem request sau và GSS acceptor.

**10. Spring Security core tự bật Kerberos SPNEGO khi thêm starter-security không?**  
Không. Cần extension/JAAS/GSS và cấu hình filter/provider đúng.

**11. Lệch timezone hiển thị có phải nguyên nhân skew?**  
Không nếu UTC timestamps đúng. Kiểm clock offset tuyệt đối.

**12. Có thể tăng clockskew lên một giờ để xử lý sự cố?**  
Không nên; làm yếu freshness/replay guard. Sửa NTP và nguồn thời gian.

**13. Vì sao keytab là secret?**  
Nó chứa service keys có thể cho phép mạo danh service trong phạm vi bị xâm phạm.

**14. Nếu Kerberos authenticate thành công nhưng API trả 403 thì nên reset keytab không?**  
Không. Đó thường là account/authority/tenant authorization issue.

**15. Vì sao cần test actual KDC/JAAS/GSS thay vì chỉ Java demo?**  
Demo chỉ mô phỏng conditions; Kerberos thật cần cryptographic ticket issuance, decryption và replay validation.

## 40. Checklist production

- [ ] Có test realms và users được phép, không dùng service production làm fixture.
- [ ] Realm/UPN/DNS/domain_realm mapping đã được hiểu và ghi lại.
- [ ] Cross-realm trust/referrals và permissions được kiểm bằng test dương/âm.
- [ ] SPN HTTP hostname/alias có ownership đúng, không trùng SPN.
- [ ] SPN, principal và keytab được quản lý theo service account chuyên biệt.
- [ ] NTP/chrony/Windows Time đồng bộ client/KDC/acceptor; alert khi drift.
- [ ] Không tăng clockskew tùy tiện để chữa authentication errors.
- [ ] Keytab có đúng principal, KVNO, enctype và matching key material.
- [ ] Keytab được đặt trong secret store/volume, read-only và permissions tối thiểu.
- [ ] Keytab rotation có plan cho mọi pods, old ticket overlap và retirement.
- [ ] Không bật DES/RC4/allow_weak_crypto để vượt compatibility failure không được phê duyệt.
- [ ] Browser gửi Kerberos SPNEGO thật, không nhầm NTLM/Basic fallback.
- [ ] Reverse proxy giữ đúng Authorization header và public hostname.
- [ ] Spring Security Kerberos extension có filter, provider, GSS acceptor config đúng.
- [ ] Kerberos authenticated principal được map theo source/realm, không chỉ local username.
- [ ] Local account active, roles và tenant/resource authorization được kiểm độc lập.
- [ ] Fail closed khi KDC, SPN, keytab hoặc JAAS lỗi; không tự tạo authenticated user.
- [ ] Có test wrong realm/no trust, skew hai chiều, KVNO/etype/wrong key.
- [ ] Có test cached ticket và mixed keytab pod rotation.
- [ ] Có ký nhận kết quả từ môi trường KDC/AD thật của staging, không chỉ MockMvc.
- [ ] Có error/runbook classification và log redaction đúng.
- [ ] Không log/chia sẻ raw keytab/tickets/passwords; debugging có thời hạn.
- [ ] Có canary và rollback an toàn, không thay đổi production time/KDC secrets khi test.

## 41. Kết luận

**Kiểm thử sai realm, lệch giờ và keytab không khớp** phải đánh giá ở **đúng pha Kerberos**: realm/trust/SPN ở client–KDC, authenticator freshness ở client–service/KDC, và keytab decrypt ở service acceptor. Một `KRB_AP_ERR_MODIFIED` không tự chứng minh KVNO sai; một `401 Negotiate` không tự là lỗi; một user Kerberos hợp lệ không tự có quyền ứng dụng.

Cách tiếp cận đáng tin là: **baseline SPNEGO thật → xác minh ticket principal/realm và KDC phase → đo UTC offsets → đối chiếu keytab principal/KVNO/etype/key material → kiểm Spring GSS acceptor → kiểm local account/tenant roles → sửa đúng lớp và regression-test**.

Spring Security Kerberos extension giúp tích hợp HTTP Negotiate với JAAS/GSS, nhưng **nó không thay thế quản trị KDC, SPN, keytab rotation hoặc clock sync**. Môi trường production cần đồng bộ thời gian, secret management, cơ chế key rollover có kiểm soát và test fail closed; **không bỏ kiểm chữ ký, không bật legacy crypto hoặc wildcard realm** chỉ để làm SSO pass.

### Tài liệu tham khảo chính thức

- Spring Security Kerberos — reference cho Spring & Kerberos, SPNEGO filter/provider và SunJaasKerberosTicketValidator: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security — Kerberos integration reference: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- MIT Kerberos — krb5.conf, realm/domain_realm/clockskew default 300 seconds: https://web.mit.edu/kerberos/krb5-current/doc/admin/conf_files/krb5_conf.html
- MIT Kerberos — kinit, keytab client credential options: https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/kinit.html
- MIT Kerberos — kvno, service ticket KVNO and -k keytab decrypt validation: https://www.mit.edu/~kerberos/krb5-latest/doc/user/user_commands/kvno.html
- Microsoft Learn — Kerberos authentication troubleshooting (KRB_AP_ERR_SKEW, MODIFIED, SPN/etype): https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-authentication-troubleshooting-guidance
- Microsoft Learn — SPN registered to wrong account, setspn verification: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-event-4-access-denied
- Microsoft Learn — Windows klist tickets/tgt/purge: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/klist
- Oracle Java Security — Kerberos 5 GSS-API mechanism and supported krb5.conf settings: https://docs.oracle.com/en/java/javase/24/security/kerberos-5-gss-api-mechanism.html
- IETF RFC 4120 — Kerberos V5 protocol (realms, tickets, authenticators, errors): https://www.rfc-editor.org/rfc/rfc4120
