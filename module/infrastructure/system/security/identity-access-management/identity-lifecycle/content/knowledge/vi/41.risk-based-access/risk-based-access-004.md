# Location signal: tín hiệu vị trí trong Risk-based access và vòng đời danh tính IAM

> **Chương: Risk-based access.** **Location signal** là dữ liệu hoặc bằng chứng giúp hệ thống ước lượng **người dùng, thiết bị, phiên hoặc workload đang kết nối từ đâu**, ở độ tin cậy nào, tại thời điểm nào, nhằm đánh giá rủi ro truy cập. Nguồn vị trí có thể gồm IP/GeoIP, vùng mạng doanh nghiệp, VPN egress, proxy, Wi-Fi, vị trí hệ điều hành cung cấp, tín hiệu di động, khu vực cloud region hoặc dữ liệu chứng thực tại cổng mạng. **Vị trí là tín hiệu ngữ cảnh, không tự chứng minh danh tính, ý định hoặc sự an toàn.** Trong IAM Identity Lifecycle, vị trí được kết hợp với Joiner–Mover–Leaver, IdP/SSO, MFA, SCIM, RBAC/ABAC/PBAC, quyền đặc quyền, danh tính máy và kiểm toán để hạn chế truy cập tồn dư mà không gây khóa nhầm người dùng hợp lệ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa location signal và phân biệt **vị trí ước lượng từ IP**, **vị trí thiết bị**, **vùng mạng**, **địa điểm công việc được khai báo** và **context của resource**.
2. Hiểu những yếu tố **nguồn phát, độ chính xác, confidence, freshness, khả năng giả mạo, tính đại diện và tình trạng thiếu dữ liệu** của tín hiệu vị trí.
3. Giải thích vì sao **VPN, proxy, NAT, mobile carrier, remote desktop, cloud egress, IPv6, CGNAT và mạng chuyển vùng** có thể làm địa điểm suy đoán khác vị trí vật lý của User.
4. Thiết kế **known/trusted locations, geofencing, unfamiliar-location, impossible travel** và kết hợp tín hiệu trong risk-based access mà không coi địa điểm là yếu tố xác thực duy nhất.
5. Chuyển kết quả rủi ro thành hành động thích hợp: **allow, step-up MFA, hạn chế scope, reauthenticate, chặn, điều tra**, có xử lý trường hợp location unknown.
6. Tích hợp location vào **IdP conditional access, SSO, OAuth/OIDC/SAML, RBAC/ABAC/PBAC, PAM/JIT**, và đánh giá quyền tại Resource Server.
7. Xử lý **Joiner–Mover–Leaver, contractor, remote work, travel, thiết bị mất kiểm soát, workload identities**, không để phiên/token cũ bỏ qua chính sách mới.
8. Áp dụng **data minimization, privacy, retention, accuracy testing, auditing và false-positive review** cho dữ liệu vị trí có thể nhạy cảm.
9. Xây dựng policy/pseudocode, luồng dữ liệu, ma trận kiểm thử, bài tập thực tế và tiêu chí xác minh enforcement.

## 1. Vì sao location signal quan trọng?

Giả sử Lan thường đăng nhập Finance Portal bằng laptop công ty từ một mạng doanh nghiệp ở Việt Nam. Một lần đăng nhập mới có địa chỉ IP được cơ sở GeoIP nhận diện là ở quốc gia khác, sử dụng thiết bị chưa được đăng ký và yêu cầu xuất dữ liệu nhạy cảm.

Không nên suy ngay rằng tài khoản bị đánh cắp: Lan có thể đang đi công tác, dùng VPN, proxy của doanh nghiệp hoặc mạng di động có egress ở nơi khác. Tuy nhiên, việc có **nhiều tín hiệu bất thường đồng thời** có thể làm tăng rủi ro và cần xác thực bổ sung.

Một chính sách hợp lý có thể:

1. Ghi nhận nguồn IP, ASN, proxy/VPN classification, thời điểm và độ tin cậy của việc định vị.
2. Đánh giá trạng thái **human identity, device registration, MFA assurance, role, resource sensitivity**.
3. So sánh vị trí kết nối hiện tại với lịch sử đáng tin, nhưng xem đó là **tín hiệu thống kê**, không là bằng chứng gian lận.
4. Với đăng nhập thông thường: yêu cầu step-up MFA hoặc device proof, nếu chính sách yêu cầu.
5. Với thao tác xuất dữ liệu rủi ro cao: chặn hoặc giới hạn đến khi có xác minh đáng tin.
6. Ghi audit lý do quyết định, signal confidence và đường khôi phục cho User hợp lệ.

**Điểm cần nhớ:** location có thể giúp phát hiện anomaly, nhưng quyết định Permit/Deny vẫn phải dựa trên **đủ điều kiện danh tính, quyền hạn, ngữ cảnh, chính sách và cơ chế thực thi hiện hành**.

## 2. Location signal không phải “người dùng đang đứng ở đâu”

Có nhiều khái niệm được gọi chung là “vị trí” nhưng có ngữ nghĩa khác nhau:

| Loại | Ví dụ | Điều nó thể hiện |
| --- | --- | --- |
| **Connection geolocation** | GeoIP suy ra IP tại cổng đăng nhập thuộc thành phố/quốc gia A. | Vị trí ước lượng của **địa chỉ mạng được nhìn thấy**, không chắc là vị trí người. |
| **Device location** | Tọa độ do OS cung cấp khi User cho phép. | Vị trí thiết bị theo công nghệ và quyền truy cập, có độ chính xác thay đổi. |
| **Network zone** | Truy cập qua VPN egress, office network hoặc private gateway đã xác minh. | Một quan hệ với hạ tầng mạng được quản trị, không mặc nhiên người ở văn phòng. |
| **Declared work location** | HR ghi nhân viên thuộc chi nhánh Hà Nội. | Địa điểm công việc/đăng ký, **không chứng minh vị trí hiện tại**. |
| **Service region** | Workload đang chạy tại cloud region theo resource metadata. | Vùng triển khai tài nguyên hoặc máy chủ, không phải vị trí con người. |
| **Resource jurisdiction** | Dữ liệu chỉ được xử lý trong khu vực đã quy định. | Ràng buộc tài nguyên/pháp lý, có thể khác client GeoIP. |
| **Session historical location** | Một lần login tuần trước có GeoIP khác. | Lịch sử quan sát, có độ trễ và có thể sai. |
| **Physical facility proof** | Thẻ ra vào, cổng onsite hoặc xác nhận presence có kiểm soát. | Một bằng chứng hiện diện riêng với thời hạn/độ tin cậy cụ thể, không thay authentication. |

### Ví dụ khác biệt

~~~text
Employee HR workLocation: Ho Chi Minh City
Actual person: traveling in Da Nang
Laptop network: corporate VPN
VPN public egress: Singapore
GeoIP country: Singapore
Protected workload region: Southeast Asia

Conclusion:
    Network egress location != exact physical location
    HR workLocation != current session location
    Resource region != user location
~~~

Chỉ nhìn GeoIP egress rồi kết luận Lan “đang ở Singapore” là **không có cơ sở chắc chắn**. Địa điểm quan sát phải được gắn **nguồn, loại tín hiệu và độ tin cậy**.

## 3. Các nguồn location signal và đặc tính

| Nguồn | Dữ liệu điển hình | Điểm mạnh | Hạn chế/rủi ro |
| --- | --- | --- | --- |
| **Public IP + GeoIP** | Quốc gia, vùng, thành phố ước lượng, ISP/ASN. | Phổ biến ở login gateway, không đòi GPS của User. | VPN, proxy, NAT, mobile carrier, dữ liệu GeoIP lỗi thời; độ chính xác không đồng đều. |
| **ASN/IP intelligence** | Tên mạng, hosting/provider, loại egress, nguy cơ proxy. | Phân biệt mạng tiêu dùng và datacenter, hỗ trợ risk scoring. | ASN không khẳng định actor xấu; classification có false positives. |
| **Corporate network zones** | CIDR egress được quản lý, gateway ID, tunnel identity. | Có thể xác minh đường đi qua hạ tầng do tổ chức quản trị. | Egress location không chứng minh device hoặc User sạch; split tunnel làm khác biệt. |
| **Device OS location API** | Tọa độ, độ chính xác, observation timestamp. | Có thể gần vị trí thiết bị hơn GeoIP. | Quyền riêng tư, permission, spoofing/mock location, thiết bị bị chiếm quyền. |
| **Wi-Fi positioning** | Wi-Fi access point, SSID/BSSID hoặc vị trí suy đoán. | Tốt trong một số môi trường trong nhà. | Có thể giả mạo thông tin client; vị trí AP database thay đổi; PII. |
| **Cellular/network mobility** | Cell/network area, roaming info. | Có thể hữu ích với thiết bị di động. | Độ chính xác thay đổi, carrier routing/roaming, quyền truy cập dữ liệu hạn chế. |
| **GPS/GNSS** | Lat/long và accuracy estimate từ thiết bị. | Có thể có độ chính xác cao ngoài trời. | Indoor failure, spoofing, privacy, không mặc nhiên được browser/IdP tin. |
| **Facility access system** | Thẻ vào cổng, khu vực site và timestamp. | Bằng chứng riêng về tương tác ở cơ sở. | Badge sharing/tailgating, không chứng minh người đang giữ phiên remote. |
| **Cloud control plane** | Region, VPC, workload identity, host metadata. | Hữu ích cho workload/resource placement. | Cloud region có thể khác egress IP; metadata không chứng minh nguồn kết nối của User. |
| **Endpoint management/attestation** | Device identity, posture, enrollment, location nếu được cấp phép. | Liên kết trusted device context. | Một thiết bị managed vẫn có thể bị compromise; location permission/freshness thay đổi. |

### Không có nguồn nào là “chứng cứ tuyệt đối”

GPS thường có thể chính xác về tọa độ thiết bị **khi dữ liệu thật và mới**, nhưng ứng dụng độc hại hoặc client bị kiểm soát có thể khai vị trí giả. GeoIP có thể hữu ích ở cấp quốc gia nhưng không chính xác tới đường phố. Office egress chỉ nói luồng mạng đi qua địa chỉ mạng nào. **Rủi ro truy cập cần nhiều nguồn độc lập và dữ liệu có provenance**, không đặt niềm tin tuyệt đối vào một trường location.

### IP, ASN và location là những dữ liệu khác nhau

- **Public IP:** địa chỉ cổng quan sát được ở tầng mạng; có thể thay đổi liên tục.
- **ASN/ISP:** mạng sở hữu/định tuyến IP; không phải địa chỉ người dùng.
- **GeoIP:** bản ánh xạ IP → khu vực ước lượng, tùy nhà cung cấp và thời gian.
- **Reputation:** tín hiệu về hành vi đáng nghi của IP hoặc mạng, không phải địa điểm.
- **Proxy/VPN detection:** phỏng đoán đường trung gian; VPN hợp pháp không phải hành vi gian lận.

Nếu một login từ datacenter ASN được đánh risk cao, phải nêu rõ **rủi ro do network classification**, không biến điều đó thành khẳng định người dùng có mặt vật lý trong datacenter.

## 4. Các giới hạn của GeoIP và mạng trung gian

### 4.1. VPN và enterprise proxy

Một người làm việc tại nhà có thể bật corporate VPN với egress ở quốc gia khác. Hàng nghìn nhân viên cùng xuất hiện từ một public IP. Việc **IP trùng nhau** không chứng minh cùng thiết bị/người; **IP ở xa** cũng không chứng minh người đang ở đó.

### 4.2. NAT, CGNAT và mobile carriers

Carrier-grade NAT và hệ thống di động có thể dùng egress tập trung xa vị trí thực. Thiết bị chuyển giữa Wi-Fi và 4G/5G trong một session có thể khiến IP/GeoIP thay đổi nhanh mà không phải bị chiếm quyền.

### 4.3. IPv6 và IP rotation

Thiết bị có thể thay IPv6 privacy addresses hoặc sử dụng nhiều đường truyền đồng thời. So sánh IP như định danh thiết bị lâu dài gây false positives và có thể bỏ sót sessions dùng chung một mạng.

### 4.4. Remote desktop, VDI và browser isolation

Người dùng ngồi tại Việt Nam nhưng thao tác qua **VDI/browser remote** chạy tại một datacenter. Ứng dụng đích quan sát IP của VDI, không phải địa chỉ người dùng. Với policy cần phân biệt, phải có **trusted upstream context** chứ không suy từ GeoIP phía đích.

### 4.5. TOR, hosting proxy và anonymization

Kết nối qua Tor hoặc proxy ẩn danh có thể tăng rủi ro ở một số tài nguyên, nhưng đây vẫn là **tín hiệu về đường kết nối**. Một nhân viên có nhu cầu bảo vệ riêng tư, nhà mạng hoặc công cụ công ty có thể tạo đặc điểm tương tự. Policy nên kết hợp **device assurance, authentication và hành động nhạy cảm**.

### 4.6. Tín hiệu vị trí giả từ client

Tọa độ do browser/mobile app gửi qua API có thể bị can thiệp hoặc giả lập nếu không có trust/attestation phù hợp. Một header tự thêm như “X-User-Location: office” **không phải bằng chứng có thẩm quyền**. Chỉ thành phần nhận từ kênh xác thực/trust đã định mới được cung cấp context quyết định.

## 5. Độ tin cậy: confidence, accuracy, freshness và provenance

Không nên chỉ lưu một cột country. Mỗi signal cần metadata mô tả **cách hình thành, mức tin cậy và cửa sổ sử dụng**.

### Các trường nên có

| Thuộc tính | Ví dụ | Vì sao |
| --- | --- | --- |
| signalId | loc-sig-882 | Correlate và dedupe. |
| subject/sessionRef | idp:sess-88 | Biết signal thuộc phiên nào. |
| observedEntity | network-egress / device / workload | Tránh gọi kết quả egress là vị trí người. |
| sourceType/sourceId | GEOIP_PROVIDER / OS_LOCATION / CORPORATE_GATEWAY | Provenance và khả năng kiểm toán. |
| observedAt | 2026-12-01T09:00+07:00 | Thời điểm nguồn ghi nhận. |
| receivedAt | 2026-12-01T09:00:02+07:00 | Độ trễ ingest. |
| locationGranularity | COUNTRY / REGION / CITY / COORDINATE | Độ chi tiết mà policy có thể dùng. |
| accuracyRadius | 2000m, nếu nguồn cung cấp | Không dùng thành tọa độ chính xác tuyệt đối. |
| confidence | HIGH/MEDIUM/LOW hoặc điểm có hiệu chuẩn | Mức độ tin cậy theo phương pháp cụ thể. |
| freshnessLimit | 5 phút cho signal runtime, ví dụ | Tránh dùng vị trí cũ để Permit dài hạn. |
| ip/ASN metadata | reference đã bảo vệ | Phân tích mạng, không log quá mức. |
| proxy/vpn classification | CORP_EGRESS / ANON_PROXY / UNKNOWN | Ngăn phân loại nhầm địa lý vật lý. |
| integrity/source verification | GATEWAY_SIGNED / CLIENT_UNVERIFIED | Chỉ rõ khả năng chống spoof. |
| policy/context version | location-risk-v4 | Tái dựng quyết định. |

### JSON mẫu: tín hiệu quan sát từ kết nối

~~~json
{
  "signalId": "loc-sig-882",
  "subjectRef": "IAM:ID-LAN-2041",
  "sessionRef": "idp:session-88",
  "sourceType": "NETWORK_GEOIP_ENRICHMENT",
  "observedEntity": "NETWORK_EGRESS",
  "observedAt": "2026-12-01T09:00:00+07:00",
  "sourceVersion": "geo-dataset-2026-11",
  "location": {
    "countryCode": "SG",
    "granularity": "COUNTRY",
    "confidenceClass": "MEDIUM"
  },
  "network": {
    "asnClass": "ENTERPRISE_EGRESS",
    "corporateVpnVerified": true
  },
  "integrity": "TRUSTED_GATEWAY_OBSERVATION",
  "riskInterpretation": "COUNTRY_IS_EGRESS_NOT_PERSON_LOCATION"
}
~~~

Đây là **schema minh họa**, không phải chuẩn SCIM/OIDC. Không cần ghi IP đầy đủ hoặc tọa độ thô trong mọi event; có thể lưu reference bảo vệ riêng nếu thật sự cần điều tra.

### Confidence không tự là xác suất chính xác

Một vendor trả “confidence 95” không chắc có nghĩa **95% xác suất người ở địa chỉ đó**. Cần hiểu định nghĩa thống kê, phạm vi mẫu và đánh giá hiệu chuẩn (calibration). Không cộng/trừ điểm từ nhiều vendor như các đại lượng độc lập nếu chúng dùng cùng một nguồn GeoIP.

### Freshness và TTL

~~~text
Location observed: 09:00
Signal freshness: 10 minutes
Request at 09:06 -> signal still within freshness window
Request at 09:15 -> signal stale for policy requiring fresh context

Stale does NOT imply attacker is definitely remote.
It means the available evidence cannot establish current context.
~~~

Với session dài, location tại **đăng nhập ban đầu** không đại diện cho vị trí ở mọi thời điểm sau đó. Phải định nghĩa **khi nào re-evaluate** và ngữ nghĩa khi context không còn đủ mới.

## 6. Network zones và known/trusted locations

Nhiều tổ chức định nghĩa **named locations** hoặc **trusted network zones** trong IdP/conditional access bằng CIDR, địa chỉ egress, ASN và vùng địa lý. Những khái niệm này không đồng nghĩa “địa điểm này an toàn về mọi mặt”.

| Khái niệm | Cách định nghĩa minh họa | Điều nó chứng minh/không chứng minh |
| --- | --- | --- |
| **Known location** | IP/region User từng truy cập hợp lệ. | Là mẫu lịch sử; không chứng minh phiên mới là User thật. |
| **Named location** | CIDR/ASN/country group do admin khai báo. | Là tập quy tắc nhận diện, không mặc nhiên đáng tin. |
| **Trusted corporate egress** | Gateway enterprise có identity, route và ownership được xác minh. | Có quan hệ với hạ tầng công ty; không bảo đảm endpoint không bị chiếm. |
| **Allowed countries** | Danh sách quốc gia được phép theo policy nghiệp vụ. | Điều kiện truy cập, không phải bằng chứng compliance pháp lý tuyệt đối. |
| **Restricted network zone** | Tor exit/datacenter hoặc egress bị chặn cho admin. | Một đặc điểm đường kết nối, cần đánh giá ngoại lệ. |
| **On-prem facility** | Network segment tại cơ sở với kiểm soát vật lý. | Chứng minh truy cập qua segment; có thể vẫn là VPN hoặc compromised host. |
| **Cloud region constraint** | Chỉ workload tại vùng được phép. | Metadata deployment, không chứng minh data processing ở mọi đường. |

### Vòng đời named locations

Một trusted CIDR bị doanh nghiệp ngừng sử dụng và cấp lại cho bên khác có thể khiến **người lạ được xem là trusted** nếu danh sách không được cập nhật. Do đó cần:

1. Resource/network owner của mỗi CIDR/zone.
2. Source authoritative cho ownership/ASN/IP ranges.
3. Ngày tạo, review, expiry hoặc refresh.
4. Change approval với SoD khi zone được dùng để giảm yêu cầu MFA.
5. Audit trước/sau, policy impact và kết quả rollout.
6. Phát hiện stale CIDR, thay đổi ISP/cloud egress.
7. Negative test khi egress không còn thuộc tổ chức.

**Trusted location không bao giờ nên được dùng như “bỏ toàn bộ xác thực và authorization”**. Đặc biệt privileged access vẫn cần identity, role, device và nhiều control khác.

## 7. Vị trí so với mức rủi ro của hành động và tài nguyên

Một login từ vị trí mới và một lệnh xóa backup production là hai chuyện khác nhau. Location signal nên tác động theo **risk tier của resource/action**:

| Yêu cầu | Tín hiệu | Quyết định minh họa |
| --- | --- | --- |
| Đọc tài liệu nội bộ ít nhạy cảm | GeoIP khác lần trước, trusted device + MFA còn hợp lệ | Có thể Permit kèm monitor hoặc step-up theo policy. |
| Xem payroll/PII | Device unknown + unusual location | Yêu cầu step-up và managed device hoặc Deny theo rủi ro. |
| Finance export lớn | Proxy ẩn danh + login mới + chưa được step-up | Có thể Deny action và trigger investigation. |
| Production admin role | Lạ network + không có PAM/JIT activation | Deny privileged action dù vị trí không bị chặn. |
| Service-to-service internal API | Workload identity còn đúng nhưng egress xuất hiện ngoài VPC expected | Kiểm tra workload trust, egress policy và khả năng compromise. |
| DR/break-glass restoration | Corporate VPN mất, recovery path từ egress mới | Xét emergency policy riêng có custody/incident/TTL, không tự mở toàn quyền. |

### Sự kiện “địa điểm lạ” không tự xóa quyền

Một nhân viên còn ACTIVE, role FinanceReader hợp lệ có thể cần xác minh bổ sung khi đi công tác. **Location risk decision** không tự thay đổi entitlement bền vững; nó có thể chặn hoặc yêu cầu xác thực lại một phiên. Ngược lại, một User đã Leaver không được Permit chỉ vì đang ở office CIDR đáng tin.

### Least privilege theo ngữ cảnh

Nếu location confidence thấp, tổ chức có thể chọn **chế độ hạn chế** thay vì quyết định toàn bộ: chỉ đọc thông tin ít nhạy cảm, không xuất dữ liệu, không dùng production admin. Cần bảo đảm Resource Server thật sự cưỡng chế **action/resource scope**, không chỉ ẩn nút trong UI.

## 8. Mô hình risk-based access: từ signal đến quyết định

~~~mermaid
flowchart TD
    A["User / workload request"] --> B["Authentication + identity resolution"]
    B --> C["Collect trusted context"]
    C --> L["Location sources<br/>IP/GeoIP, gateway, device"]
    C --> D["Device posture + trust"]
    C --> U["Lifecycle, role, session, resource"]
    L --> P["Signal provenance, confidence<br/>freshness and proxy classification"]
    D --> E["Risk evaluator / policy engine"]
    U --> E
    P --> E
    E --> F{"Current policy decision"}
    F -->|Low risk and authorized| G["Permit within entitlement"]
    F -->|Elevated but recoverable| H["Step-up / device revalidation"]
    F -->|High/mandatory deny| I["Deny or restrict action"]
    F -->|Unknown or control failure| J["Fail-safe / predefined fallback"]
    G --> K["PEP enforcement + audit"]
    H --> K
    I --> K
    J --> K
~~~

### Bốn nguyên tắc

1. **Xác thực trước:** location không là danh tính; phải có trusted principal.
2. **Ủy quyền độc lập:** role, tenant, action, resource và JML không bị thay bởi country match.
3. **Ngữ cảnh đủ mới:** biết provenance/confidence/freshness, không dùng cached GeoIP cũ như sự thật hiện tại.
4. **Cưỡng chế đúng nơi:** IdP login decisions hữu ích nhưng API cần bảo vệ action sensitive khi session/token cũ còn tồn tại.

### Điểm kiểm soát

- **Policy Administration Point (PAP):** quản lý rule và version, owner/approval.
- **Policy Information Point (PIP):** cung cấp tín hiệu location, identity, device, HR và resource từ nguồn có thẩm quyền.
- **Policy Decision Point (PDP):** đánh giá policy, risk và nghĩa vụ.
- **Policy Enforcement Point (PEP):** gateway, IdP hoặc Resource Server áp Allow/Deny/step-up.

Các tên điểm chính sách là cách mô hình hóa kiến trúc, không có nghĩa mọi sản phẩm triển khai bốn dịch vụ tách rời.

## 9. “Unfamiliar location” và khái niệm quen thuộc theo lịch sử

Một địa điểm có thể được xem là **unfamiliar** khi nó không phù hợp mẫu đăng nhập trước đó của một principal. Điều này khác với **restricted location** do policy quản trị, và khác với vị trí **thực sự nguy hiểm**.

### Khi xây dựng baseline

- Nên chỉ học từ **các phiên đăng nhập đã được xác minh đáng tin**, không tự coi mọi login success là nguồn sạch.
- Có thể tách profile **human identity, device, client, tenant, corporate egress**.
- Phân biệt **địa chỉ egress VPN quen thuộc** với **physical location**.
- Tránh học quá mức một IP duy nhất vì mobile device thường đổi IP.
- Có giai đoạn warm-up với người mới, chuyển văn phòng hoặc thay ISP.
- Đánh dấu những phiên bị xác nhận compromise để không dùng chúng củng cố baseline.
- Có khả năng reset/rebuild baseline khi account recovery, rehire hoặc device reassignment.
- Không tạo profile vị trí chi tiết hơn nhu cầu bảo mật.

### Học baseline có thể bị “poisoning”

Nếu attacker đã chiếm credential và đăng nhập một số lần, hệ thống tự học địa điểm attacker là “familiar” có thể làm giảm cảnh báo những lần sau. Cần baseline **có nguồn sạch, xác thực mạnh, cửa sổ và quy tắc chấp nhận có kiểm soát**; không sử dụng tất cả event như ground truth.

### Ví dụ địa điểm mới là hợp lệ

~~~text
Identity: Lan, ACTIVE
Previous trusted network: Vietnam corporate egress
Current login: Japan hotel Wi-Fi
Reason: approved business travel
Device: managed laptop with current posture
MFA: phishing-resistant step-up completed
Requested action: report.read

Potential decision:
    allow within existing entitlement,
    log unfamiliar location + verification;
    do not create broad exception for report.export automatically.
~~~

**Thông tin chuyến công tác** có thể là một tín hiệu bổ trợ nếu thực sự có nguồn được phép và xác minh phù hợp; nó không tự chứng minh người đang đăng nhập là Lan.

### Rủi ro dùng lịch sử địa điểm

Người mới tuyển, người đi công tác thường xuyên, nhân viên trực từ xa, người thay đổi nơi ở hoặc dùng dịch vụ truy cập mạng cho privacy có thể bị cảnh báo cao hơn. Phải đo **false-positive rates theo kịch bản**, có recovery flow và không tự rút ra kết luận về cá nhân từ location anomaly.

## 10. Impossible travel: phát hiện chuyển địa điểm bất thường

**Impossible travel** thường là quy tắc cảnh báo khi **hai sự kiện xác thực** của cùng một identity có vị trí ước lượng cách xa nhau trong khoảng thời gian mà việc di chuyển vật lý được xem là khó hợp lý. Đây là **heuristic**, không phải chứng cứ tự động rằng account đã bị compromise.

### Công thức minh họa

Với hai vị trí đã được xác định đủ tin cậy:

\[
v_{\mathrm{estimated}} = \frac{d(\mathrm{loc}_1,\mathrm{loc}_2)}{\Delta t}
\]

Trong đó \(d\) là khoảng cách ước lượng (thường theo đường chim bay), còn \(\Delta t\) là chênh lệch thời điểm giữa hai quan sát. Nếu một hoặc cả hai vị trí là GeoIP **network egress**, giá trị không phải vận tốc vật lý thật của người dùng.

### Ví dụ

~~~text
Login 1: 09:00, IP GeoIP = Country A
Login 2: 09:12, IP GeoIP = Country B
Estimated distance: 4,000 km

Naive estimate:
    4,000 km / 0.2 hour = 20,000 km/h

Do NOT conclude:
    Human traveled at 20,000 km/h

Investigate:
    corporate VPN egress changed?
    mobile carrier routing?
    remote desktop?
    overlapping sessions?
    token replay or credential theft?
~~~

### Những nguồn false positive

| Nguyên nhân | Cơ chế làm sai |
| --- | --- |
| Corporate VPN chuyển egress | Session từ cùng device nhưng IP public ở hai nước. |
| GeoIP database sai/lỗi thời | Cùng IP bị ánh xạ sang khu vực khác nhau ở các thời điểm. |
| Mobile carrier routing | Thiết bị ở một nơi nhưng mạng dùng egress xa. |
| Browser/remote desktop | App quan sát địa điểm máy từ xa, không phải người dùng. |
| Multi-device login | User có thể sử dụng hai thiết bị ở hai nơi (ví dụ máy để ở nhà) hoặc một session bị chia sẻ; cần xác minh. |
| Clock skew/delayed events | Timestamp bị lệch hoặc log đến muộn khiến tính vận tốc sai. |
| Proxy/hosting provider | IP location là endpoint trung gian. |
| Account sharing hợp lệ theo sản phẩm | Một service account hoặc kiosk dùng chung nhưng không nên áp heuristic per-human. |

### Heuristic hữu ích khi kết hợp tín hiệu

Một possible impossible-travel event có thể đáng điều tra hơn nếu đồng thời:

- Xuất hiện **device mới, authentication method yếu hoặc MFA fatigue**.
- Có **token replay/reuse** hay phiên hoạt động cùng lúc trên thiết bị không liên quan.
- User chưa có **trusted corporate VPN** giải thích việc đổi egress.
- Có hành động nhạy cảm như cấp admin, xuất dữ liệu hoặc thay recovery factors.
- Có evidence từ **independent source** về tài khoản bị compromise.

Không dùng một threshold vận tốc cố định được bịa như “mọi giá trị hơn X km/h đều là hacker” mà không hiệu chuẩn bằng dữ liệu doanh nghiệp và loại nguồn.

## 11. Geofencing và country-based access restrictions

**Geofencing** áp quy tắc dựa trên việc một signal thuộc hoặc không thuộc một **vùng địa lý được định nghĩa**. Trong IAM, geofence thường dùng IP country/geolocation hoặc GPS/OS location; hai kiểu cần khác nhau về mức độ đảm bảo.

### Ví dụ chính sách

| Tài nguyên | Ràng buộc | Lưu ý |
| --- | --- | --- |
| Internal finance dashboard | Đăng nhập từ network zones định nghĩa; ngoài zone cần MFA. | Zone là network identity; không là địa chỉ vật lý. |
| Customer PII export | Phải có entitlement, managed device và thỏa policy địa lý/rủi ro. | Không chỉ cần country allowlist. |
| Production console | Chỉ admin JIT/PAM và mạng/quy trình được chấp thuận. | Bảo vệ direct session ngoài IdP. |
| Regional data workflow | Workload chỉ chạy/định tuyến trong cloud region được duyệt. | Cần kiểm data location, storage/replication; client IP không đủ. |
| Support portal cho người đi công tác | Location lạ → step-up hoặc temporary policy exception. | Có recovery, không auto-block vĩnh viễn chỉ vì đi xa. |

### Hai lỗi logic

~~~text
Wrong:
    if GeoIP.country == "VN":
        PERMIT all finance data

Wrong:
    if GeoIP.country != "VN":
        DENY all access without considering network egress,
        signal accuracy, business policy or available recovery.
~~~

Đúng hơn là đánh giá country/zone **cùng với quyền, authentication, device, action, subject và độ tin cậy của nguồn**. Nếu có **hard geographic/legal restriction**, phải mô tả nguồn thực thi và cơ chế kiểm chứng đủ cho nghĩa vụ cụ thể, không giả định GeoIP đủ chứng minh yêu cầu lưu trữ/chuyển dữ liệu.

### Boundary và sai số

Tọa độ gần biên giới, thành phố lân cận hoặc IP của provider có thể được định vị sai. Nếu policy là “bên trong bán kính 100 m”, cần **accuracy radius, timestamp, phương thức xác minh**; phép so sánh tọa độ thuần túy không thể bảo đảm boundary chính xác khi sai số lớn hơn khoảng cách tới mép vùng.

### Data residency không bằng GeoIP restriction

Quy định dữ liệu ở region A có thể liên quan nơi **lưu trữ, xử lý, truy xuất và truyền**. Chỉ chặn login từ GeoIP quốc gia B **không tự bảo đảm** dữ liệu chỉ được xử lý trong region A. Cần kiểm soát kiến trúc cloud/storage, dữ liệu sao chép và policy pháp lý phù hợp.

## 12. Risk scoring: gộp tín hiệu mà không double-count

Location thường là **một feature** trong quyết định adaptive access. Nó có thể được tính thành điểm rủi ro theo rule hoặc mô hình, nhưng cần giải thích nguồn và tránh suy diễn.

### Những feature ví dụ

| Feature | Đóng góp hợp lý | Cần dè chừng |
| --- | --- | --- |
| Unfamiliar GeoIP | Tăng nhu cầu xác minh. | GeoIP đã bị VPN/remote egress che. |
| Trusted corporate gateway | Có thể giảm nghi vấn về mạng. | Không thay chứng cứ danh tính/thiết bị. |
| Tor/anonymizer classification | Có thể tăng risk cho app nhạy cảm. | False positive; privacy use hợp lệ. |
| Device posture fail | Có thể tăng risk mạnh. | Không phải tín hiệu location; tránh gộp lẫn nguyên nhân. |
| New device + new location | Có thể ưu tiên step-up/incident detection. | Hai feature có thể tương quan do User mới đổi máy/đi công tác. |
| High-risk action | Yêu cầu assurance cao hơn. | Không nên được giảm rủi ro chỉ vì IP ở văn phòng. |
| Token replay/compromise alert | Có thể buộc deny/containment. | Có thể cần xử lý độc lập với score. |

### Pseudo score để giải thích tư duy

~~~text
baseRisk = 0
if locationConfidence == LOW: add uncertainty marker
if unfamiliarNetworkEgress: add 15 points
if unverifiedAnonymizingProxy: add 20 points
if deviceNotTrusted: add 35 points
if sensitiveAction: require higher assurance threshold

if confirmedCompromisedSession:
    mandatory DENY/containment regardless of score

finalDecision =
    policy(identity, entitlement, lifecycle, resource,
           risk, assurance, signalQuality)
~~~

Các số ở đây **hoàn toàn minh họa**, không là ngưỡng khuyến nghị cho production. Việc dùng score thật đòi **calibration, backtesting, monitoring false positives/false negatives, change control và risk acceptance**. Không cộng cùng một nguyên nhân hai lần, ví dụ “datacenter IP” và “VPN IP” đều suy từ một provider classification.

### Ngưỡng nên đi cùng hành động

| Kết quả đánh giá | Phản ứng minh họa |
| --- | --- |
| **Low risk, đủ quyền** | Permit theo scope hiện hành, có audit thông thường. |
| **Medium risk** | Yêu cầu MFA step-up, device revalidation hoặc monitor. |
| **High risk** | Deny sensitive action, revoke/đóng phiên theo policy, mở case điều tra. |
| **Signal unknown** | Dùng fail-safe/step-up theo risk tier; không mặc định country trusted. |
| **Mandatory veto** | Deny bất kể location/score: Leaver, credential bị revoke, tenant mismatch... |

**Risk score không được lấn át hard deny.** Người đã rời công ty không được đăng nhập vì “IP ở văn phòng” và Service không được vượt tenant chỉ vì “network trusted”.

## 13. Tín hiệu thiếu: unknown, denied permission và unavailable provider

Trong nhiều trường hợp location không thể thu thập:

- User từ chối quyền GPS/location API; không thể coi đó là bằng chứng họ ở vùng cấm.
- Browser/headless client không hỗ trợ device location.
- GeoIP provider lỗi hoặc không có ánh xạ đáng tin cho IP mới.
- User đi qua relay/proxy khiến vị trí vật lý không quan sát được.
- MDM/EDR đang offline, posture/location stale.
- IdP hoặc PIP lỗi, policy evaluation không nhận được feature bắt buộc.
- Workload server không có GPS; client location vốn không áp dụng cho loại principal này.

### Quy tắc ba trạng thái

~~~text
locationSignalState =
    KNOWN_WITH_QUALITY
    | UNKNOWN_OR_UNAVAILABLE
    | NOT_APPLICABLE_FOR_PRINCIPAL

NEVER:
    UNKNOWN == TRUSTED_OFFICE
    UNKNOWN == CONFIRMED_HIGH_RISK_COUNTRY
~~~

Nếu một application chỉ Permit với **verified office gateway**, unknown phải không đạt điều kiện đó. Nếu một app dùng **geo anomaly để yêu cầu step-up**, unknown có thể dẫn tới step-up chứ không cần đánh dấu user compromised.

### Fail-safe theo resource tier

| Kịch bản | Ví dụ phản ứng |
| --- | --- |
| Login vào ứng dụng ít nhạy cảm, GeoIP provider timeout | Có thể cho phép khi identity/device/MFA đủ mạnh, log unknown, theo risk acceptance. |
| API xuất dữ liệu nhạy cảm yêu cầu verified location | Không Permit nếu không đủ chứng cứ; có thể offer remediation/step-up. |
| Resource yêu cầu geo restriction bắt buộc | Deny hoặc fallback hợp lệ đã được thiết kế, không fail-open. |
| Emergency recovery khi network chính lỗi | Dùng emergency path có authority/custody/incident audit riêng. |
| Workload trong private network không có public IP | Dùng trusted VPC/cluster attestation/trust context thay GeoIP. |

**Không biến thiếu tín hiệu vị trí thành sự kiện xác thực thành công.** Trong risk-based access, cần hiển thị rõ **điều kiện nào được thỏa, điều kiện nào không kiểm được và boundary thực thi**.

## 14. Step-up MFA và Continuous/Adaptive Access

Một hành động phổ biến khi location bất thường là **step-up authentication**: yêu cầu người dùng thực hiện bước xác thực mạnh hơn trước khi dùng hành động nhạy cảm.

### Những bước có thể dùng

1. Phân loại resource/action yêu cầu assurance nào.
2. Kiểm tra session hiện có được xác thực bằng phương thức gì và authTime.
3. Thu thập location signal và signal quality ở thời điểm có yêu cầu.
4. Nếu risk vượt ngưỡng, phát **challenge step-up** được ràng buộc với đúng session, client, tenant, action hoặc scope.
5. Xác minh challenge thực sự đạt mức assurance cần (ưu tiên cơ chế chống phishing khi chính sách phù hợp).
6. Chỉ cấp quyền trong **thời gian và phạm vi đã duyệt**, không nâng toàn bộ sessions của User.
7. Re-evaluate khi risk/role/location/thiết bị thay đổi đáng kể hoặc session hết hạn theo policy.

### MFA không đồng nghĩa Permit

~~~text
Location anomaly -> user successfully completes MFA

Still check:
    lifecycleStatus ACTIVE?
    current entitlement for requested action?
    resource and tenant scope?
    SoD and device requirements?
    session/credential not revoked?
    mandatory geo/legal restrictions?
~~~

MFA xác minh người dùng ở một mức bảo đảm, không cấp role cho họ. Một User không có ProductionAdmin vẫn không được production.deploy sau khi pass MFA.

### Continuous access không có nghĩa mọi request đều gọi GPS

Re-evaluate theo rủi ro và nguồn có khả năng thực thi; có thể là mỗi request API nhạy cảm, mỗi lần phát token mới, lúc session renewal hoặc khi nhận event location/device thay đổi. Việc thu GPS liên tục có **chi phí, pin, privacy và độ tin cậy**; không phải mọi hệ thống làm được hoặc cần.

### Chú ý token và phiên cũ

Khi location risk tăng sau login, các access token tự chứa hoặc app sessions đã phát có thể vẫn được chấp nhận tới expiry nếu API không có **revocation/introspection/current-policy enforcement**. IdP đánh risk cao tại lần login tiếp theo chưa chắc ngắt quyền đang dùng.

## 15. IdP, SSO, OAuth/OIDC và SAML khi dùng Location signal

### IdP conditional access

IdP có thể đánh giá **country/ASN/named network, device compliance, authentication assurance, user/group và risk** khi login hoặc token issuance. Cần hiểu chính xác nhà cung cấp hỗ trợ những điểm re-evaluation nào.

### OIDC/OAuth

- OIDC giúp xác thực User và liên kết session/client, nhưng **location claim không mặc nhiên là một chuẩn bắt buộc** trong ID token.
- OAuth access token có **audience, scope, expiry**; Resource Server phải đánh giá quyền theo resource.
- Nếu policy ở IdP chỉ xét login, token sau đó vẫn có thể được API chấp nhận khi người dùng đã đổi mạng.
- Một claim vị trí trong token có thể **stale** vì được snapshot tại issuance; không nên coi như vị trí runtime nếu không có cơ chế cập nhật.
- Revoking refresh token có thể chặn lấy token mới, nhưng chưa chắc chặn access token cũ còn hạn.
- Các capability như token introspection, session revocation hoặc event-driven policy updates có thể giảm cửa sổ quyền tồn dư theo khả năng triển khai.

### SAML

SAML SP có thể tạo **local session** sau khi IdP xác thực; vị trí lúc login không tự được đánh giá lại tại mỗi action. Nếu cần hạn chế tài nguyên sensitive theo location hiện hành, SP hoặc API cần **policy enforcement riêng** hoặc cơ chế refresh/authentication phù hợp. Single Logout không đảm bảo mọi local session kết thúc trong mọi trường hợp.

### SCIM

SCIM đồng bộ User/Group/account lifecycle, **không là giao thức truyền vị trí runtime hay revoke mọi session mặc định**. Việc User chuyển department hoặc bị Leaver có thể dẫn tới Group/role revoke; location signal có thể là context tại điểm đăng nhập/API, nhưng không nên được “đóng băng” thành một Group static kiểu “đang ở nước X” mà thiếu TTL/version và consent/trust.

### Bảng phân vai

| Lớp | Trách nhiệm với location | Hạn chế |
| --- | --- | --- |
| **IdP** | Login risk/conditional access/step-up. | Không luôn kiểm action trong RP đã đăng nhập. |
| **SSO/RP** | Tạo app session, áp session-based policy. | Có thể dùng cached attributes/token. |
| **Authorization Server** | Phát/revoke token và grants theo policy. | Không tự ép Resource Server reevaluate current location. |
| **Resource Server/PEP** | Cưỡng chế action/resource scope và context mới khi cần. | Cần trusted location source, policy/latency. |
| **SCIM/IGA** | Desired entitlements và JML provisioning. | Không mặc nhiên hỗ trợ geolocation runtime. |
| **SIEM/IR** | Correlate risk anomalies và điều tra. | Detection không tự là preventive control. |

## 16. RBAC/ABAC/PBAC: đặt location đúng vai trò

**RBAC** cho biết người hoặc service có vai trò nào. **ABAC** bổ sung thuộc tính subject, resource, action, environment và session. **PBAC** là cách quản trị/chạy các quy tắc đó theo policy có version và owner.

### Ví dụ pseudo-policy

~~~text
PERMIT report.export WHEN
    subject.lifecycleStatus == ACTIVE
    AND subject.hasCurrentEntitlement("FinanceExporter")
    AND subject.tenantId == resource.tenantId
    AND resource.classification == "CONFIDENTIAL"
    AND session.authenticationAssurance >= requiredAssurance
    AND device.trustStatus == TRUSTED
    AND locationEvidence.isAcceptableFor(policy.requiredQuality)
    AND locationPolicy.allowsCurrentContext(
        locationEvidence.networkZone,
        locationEvidence.estimatedRegion,
        resource,
        action
    )
    AND noMandatoryVeto

ELSE:
    DENY_OR_STEP_UP_ACCORDING_TO_POLICY
~~~

Đây là **pseudo-policy**, không phải cú pháp của một hệ thống cụ thể. Nếu một nguồn location không đáng tin/không áp dụng, không truyền “trusted country” từ header do client tự khai. Việc đọc và diễn giải dữ liệu vị trí phải được **chuẩn hóa theo source**.

### DSoD và location

Một chính sách Dynamic Segregation of Duties có thể cấm hai thao tác xung đột trong cùng transaction/session, độc lập với địa điểm. Một User có cả role VendorEditor và PaymentReleaser không trở nên an toàn chỉ vì ở văn phòng. Location có thể bổ sung mức kiểm soát, nhưng **không giải quyết toxic combination**.

### Resource owner và policy impact

Thay allowlist quốc gia hoặc giảm assurance trong named location có thể mở truy cập cho một tập lớn người dùng; đó là **access-affecting policy change** cần review, approval và audit, dù không đổi Group/role của từng người.

## 17. Identity lifecycle: Joiner và location context

### Joiner không có location baseline

Một người mới tuyển thường **chưa có lịch sử location**. Nếu hệ thống đánh “unknown location = high risk attacker”, User mới có thể bị lockout ngay ngày đầu. Chính sách onboarding nên:

1. Xác minh identity proofing, HR startAt và account mapping đúng person.
2. Gán baseline **work location dự kiến** từ HR/contract dưới dạng thuộc tính nghiệp vụ, không dùng làm proof vị trí hiện tại.
3. Enroll thiết bị và MFA theo chính sách, tránh chỉ tin IP office.
4. Đặt login lần đầu hoặc thiết bị mới vào **step-up/verified enrollment flow** nếu cần.
5. Chỉ mở business access từ startAt và role/entitlement hiệu lực.
6. Lấy một số observation trusted để bắt đầu baseline mà không biến mọi nơi login lần đầu thành “trusted forever”.
7. Ghi audit signal quality, policy version, kết quả challenge.

### Pre-provisioning không cho phép truy cập trước hiệu lực

~~~text
HR startAt: 2026-12-01 09:00
Account pre-created: 2026-11-28
Device enrolled: 2026-11-29
Connection: known office network

Before startAt:
    allow limited onboarding flow if policy permits
    deny production finance.export

After startAt:
    require correct role, device assurance, location risk checks
~~~

Office IP không thay thế lifecycle guard. Nếu Joiner bị hủy mà task IdP vẫn retry, location “trusted” không được làm sống lại quyền đã bị thu hồi.

## 18. Mover: thay địa điểm công việc và thay quyền nghiệp vụ

**Mover** có thể là chuyển bộ phận, đổi quốc gia công tác, chuyển văn phòng, thay manager/tenant hoặc đổi vai trò. Không phải mọi Mover đều thay vị trí hiện tại; cần tách **HR workLocation change** khỏi **live location signal**.

### Tình huống chuyển văn phòng

Lan từ bộ phận Finance tại Việt Nam sang Support tại Singapore:

| Thuộc tính | Trước Mover | Sau Mover mong muốn | Điều cần lưu |
| --- | --- | --- | --- |
| HR workLocation | Việt Nam | Singapore | HR sourceVersion/effectiveAt. |
| Department | Finance | Support | Thu hồi quyền Finance cũ. |
| IdP Group | FinanceExporters | SupportReaders | SCIM/IdP readback, quyền thực tế. |
| Named location policy | Quen office VN | Office SG có thể hợp lệ | Policy version và expected network egress mới. |
| Login anomaly baseline | Quen truy cập VN | Cần warm-up/đánh giá lại | Không coi mọi login từ SG là compromise. |
| Finance RP session | JWT chứa role Finance cũ | Không được finance.export | Session/token revocation hoặc runtime authorization. |
| Device trust | Laptop đã enroll | Có thể giữ hoặc thay theo ownership | Device posture và tenant policy mới. |

### Những điểm cần tránh

1. **Không đổi allowlist account** trước khi kiểm authority, role và tenant mới.
2. Không lấy việc workLocation chuyển Singapore làm bằng chứng User đã ở Singapore.
3. Không giữ **FinanceExporter** chỉ vì Lan vẫn login từ mạng Finance cũ.
4. Không dùng baseline location cũ để phủ quyết vĩnh viễn hoạt động công tác hợp lệ.
5. Kiểm việc **policy phiên và resource** có nhận entitlement mới/Leaver-like removal đúng lúc.
6. Theo dõi các exception location cũ: phải hết hạn/thu hồi nếu không còn cần.

### Location exception không tự kế thừa qua Mover

Một exception “Lan được đăng nhập Finance từ network khách hàng trong 14 ngày” có scope gắn với công việc Finance. Khi Lan chuyển Support, việc giữ exception như **đặc quyền phụ** có thể mở đường truy cập ngoài chính sách mới. Cần mô hình exception với **owner, entitlement, target resource, time bound, reason, approver và JML sourceVersion** để thu hồi có căn cứ.

### Rủi ro SoD khi hai môi trường còn quyền

Mover có thể tạo thời gian chồng lấp role cũ và mới. Location không giải quyết được xung đột quyền: dù login từ office cũ hay mới, **tổ hợp capability** vẫn cần SoD enforcement theo resource/action. Nếu access rules gắn country, phải kiểm cả **direct grant, nested role, JWT claims và policy exceptions**.

## 19. Leaver và suspension: không để trusted location mở lại quyền

**Leaver** là điều kiện phủ quyết truy cập theo thời điểm hiệu lực và policy tổ chức. Một corporate network không được làm thay đổi kết luận này.

### Luồng xử lý

~~~mermaid
flowchart TD
    A["HR Leaver / suspension event"] --> B["Resolve IAM identity<br/>sourceVersion + effectiveAt"]
    B --> C["Invalidate eligibility and access grants"]
    C --> D["Block new IdP sessions / token issuance"]
    C --> E["Revoke SCIM Group / app roles<br/>PAM eligibility and sessions"]
    D --> F["Re-evaluate risk and resource authorization"]
    E --> F
    F --> G{"Old session/token can still act?"}
    G -->|Yes/unknown| H["Residual access / containment<br/>owner + verification"]
    G -->|No within scope| I["Verified closure + audit"]
~~~

### Leaver trước khi job location exception hoàn tất

~~~text
v21  Temporary country exception requested
v22  Security approves bounded exception for project X
v23  HR Leaver effective
v24  Old exception activation job retries

Correct:
    job must revalidate lifecycle and authority
    no new exception/session/grant may be created after v23
~~~

Không chỉ bỏ User khỏi Group mà cần thu hồi **location-based policy exceptions, trusted device access, IdP/SSO sessions, refresh tokens, app-local credentials và PAM activations** khi thuộc scope offboarding.

### Suspension

Trong một số tình huống, HR/IAM dùng trạng thái SUSPENDED cho đình chỉ tạm thời. Chính sách có thể giữ account để điều tra nhưng hạn chế access. Location signal **không thể chuyển SUSPENDED thành ACTIVE** chỉ vì User ở trụ sở; việc thay trạng thái phải đi qua nguồn có thẩm quyền.

### Rehire

Khi nhân sự được tuyển lại, không tự kế thừa **country exceptions, trusted device list, historical session refresh grants hoặc risk baseline** chưa được kiểm duyệt từ lần làm việc trước. Có thể liên kết lại cùng stable person identity theo proofing, nhưng phải cấp access/exception theo role hiện hành và có audit.

## 20. Contractor, đối tác và truy cập xuyên quốc gia

Nhà thầu và vendor thường truy cập từ mạng của đơn vị bên ngoài. Nếu một named location chỉ liệt kê office network của công ty, **mặc định chặn mọi nhà thầu** có thể làm gián đoạn quy trình đã được duyệt. Ngược lại, miễn toàn bộ geofencing cho partner có thể mở đường lạm dụng.

### Các điều kiện nên xét

- Contractor identity có **internal sponsor, contract status và endAt**.
- Partner IdP/federation có issuer/trust đủ mạnh và quy tắc account linking.
- Resource scope/tenant được phê duyệt riêng; không cấp cross-tenant mặc định.
- Thiết bị partner đáp ứng posture hoặc assurance đã được thỏa thuận và khả thi.
- Kết nối qua **partner egress/VPN** được ghi là network context, không mặc định physical location.
- Location exception có owner/expiry/action scope và cơ chế thu hồi khi hợp đồng kết thúc.
- Có audit về source signal, decision, step-up và target enforcement.

### Ví dụ vendor support

~~~text
Contractor identity: PARTNER-ID-88
Sponsor: IAM:ID-RESOURCE-OWNER
Contract endAt: 2026-12-31
Target: tenant-b/payment-monitor
Allowed actions: diagnostics.read
Connection: partner verified VPN egress
GeoIP: Country X
Authentication: federated + MFA

Result:
    location context alone neither grants production admin
    nor proves contractor is physically in Country X.
~~~

Nếu một rule có tính ràng buộc pháp lý về **quốc gia xử lý dữ liệu**, cần chuyên môn pháp lý và kiểm soát dữ liệu tương ứng, không chỉ đánh giá GeoIP của partner.

## 21. PAM/JIT và Emergency access: location không thay thẩm quyền

**Privileged access** thường đòi MFA mạnh, device trust, PAM/PIM/JIT activation, authorization theo resource và audit. Location signal có thể tăng/giảm rủi ro, nhưng không được tạo ngoại lệ đặc quyền ngầm.

### So sánh hai yêu cầu

| Yêu cầu | Location signal | Các điều kiện không thể bỏ |
| --- | --- | --- |
| Admin đăng nhập production từ trusted VPN | Known corporate egress | Named human identity, PAM/JIT role, MFA, resource scope, SoD. |
| Admin đăng nhập từ khách sạn đi công tác | Unfamiliar network | Step-up và phê duyệt theo risk policy, thiết bị quản lý, JIT. |
| Admin đăng nhập từ anonymizer không xác minh | Network risk elevated | Có thể Deny/require alternate trusted path, không cấp quyền rộng. |
| Break-glass vì IdP/VPN chính outage | Egress ngoài allowlist bình thường | Emergency trigger/necessity, custody, scope/TTL, independent authority/audit. |
| Admin User đã Leaver | Bất kỳ location | Hard deny theo lifecycle, thu hồi sessions và credentials. |

### Break-glass có thể cần đường không phụ thuộc trusted egress

Nếu corporate VPN là thành phần bị lỗi, một policy kiểu “chỉ có corporate VPN mới mở admin” có thể khiến **không thể phục hồi IAM**. Tổ chức cần **emergency access path được chuẩn bị trước** với identity verification, credential custody, incident binding, least privilege và hậu kiểm. Không xử lý outage bằng cách đặt toàn bộ country/network = TRUSTED.

### Phiên PAM đã mở

Một privileged session có thể tồn tại sau khi location thay đổi (ví dụ admin chuyển từ VPN sang mạng khác). Policy phải nêu **tái đánh giá tại đâu**, có chặn session trực tiếp/SSH/cloud API được không, và phản ứng khi network signal thay đổi. **Đóng PAM broker** không tự ngắt mọi direct sessions ngoài broker.

## 22. Machine identity và service-to-service location context

Đối với **service accounts, workloads, IoT, CI/CD agents và API clients**, từ “location” thường là **deployment region, network zone, VPC/subnet, cluster/namespace, gateway và attested host**, không phải vị trí một người.

### Điều kiện khác Human login

| Tiêu chí | Human session | Workload/service |
| --- | --- | --- |
| Identity | PersonId, IdP subject, account. | Workload/service principal/instance ID. |
| Authentication | MFA, SSO, passkey, session. | mTLS, workload federation, signed JWT, short-lived credential. |
| Location | IP/GeoIP, device coordinates, network zone. | Cloud region, VPC, cluster, workload-origin trust. |
| Ownership | HR/manager/resource owner. | Service owner, platform owner, application registry. |
| Risk response | Step-up/reauth, device check, restrict action. | Revoke trust/token, isolate workload, require attested environment. |
| Lifecycle | JML và contractor status. | Provision/rotate/redeploy/decommission, owner handoff. |

### Host/cloud egress có thể không phải workload origin

Kubernetes workload trong private cluster có thể truy cập API thông qua **NAT gateway chung**; public IP biểu thị gateway, không phân biệt pod. Một container di chuyển node/region nhưng giữ workload identity; cần policy dựa trên **issuer/subject/audience, cluster identity, trusted attestation và resource scope**, không chỉ IP address.

### Workload rule mẫu

~~~text
PERMIT backup.restore WHEN
    workload.identity == "backup-restorer"
    AND workload.trustIssuer in approvedIssuers
    AND workload.namespace == "backup-prod"
    AND workload.clusterAttestation == VALID
    AND workload.region in approvedRecoveryRegions
    AND token.audience == "backup-control-api"
    AND resource.projectId == "prod-payments"
    AND emergencyOrChangeAuthorizationSatisfied
~~~

Mã trên là pseudo-policy. Nếu workload chỉ được phép chạy trong VPC/region nhất định, cần **enforce trust và network boundary** tại cloud IAM/API/gateway, không suy từ nhãn region do client tự truyền.

### Sự kiện host compromised

Nếu một node có quyền phát workload token bị chiếm quyền, GeoIP login “đúng region” không làm token an toàn. Phải đánh giá **key/token/trust, workload issuer, permissions, active sessions và khả năng tái phát hành token**, cô lập host và khôi phục trên môi trường tin cậy.

### Owner rời tổ chức

Leaver của service owner không tự nghĩa là workload production phải bị xóa. Cần **chuyển ownership, thu hồi quyền người, rotate shared secret bị biết, xem lại deployment region và network exceptions**; lưu audit.

## 23. Location và thiết bị mất kiểm soát

Một thiết bị laptop bị mất có thể tiếp tục phát sinh login từ vị trí cũ hoặc mới. Location anomaly có thể giúp điều tra, nhưng **thiết bị đã LOST/COMPROMISED là tín hiệu độc lập và nghiêm trọng hơn** đối với các tài nguyên cần trusted device.

### Ví dụ

~~~text
User identity: Lan ACTIVE
Device A: managed laptop, incident LOST, trust REVOKED
Device B: managed phone, trust TRUSTED

Session A:
    public IP GeoIP = familiar office country
    device trust REVOKED
    -> DENY protected actions per policy

Session B:
    public IP GeoIP = new country
    device trust TRUSTED
    valid MFA, approved travel
    -> evaluate risk/step-up within User entitlement
~~~

Không lấy “IP quen thuộc” để bỏ qua tín hiệu **device compromise**; cũng không mặc định mọi thiết bị của Lan mất tin cậy chỉ vì location của một session bất thường.

### Remote wipe và session revocation

Một lệnh remote wipe pending khi laptop offline không chặn được token đã sao chép. Cần **IdP session revocation, API checks, refresh token handling, device certificate/key revoke và app-local sessions** theo phạm vi. Khi điều tra, giữ riêng timestamp của signal vị trí, việc revoke và quyền còn sử dụng được.

### Vị trí thiết bị do MDM cung cấp

Không mặc nhiên có quyền thu tọa độ người dùng qua MDM; capability phụ thuộc thiết bị, enrollment, chính sách và quyền riêng tư. Nếu được sử dụng, phải có mục đích rõ, độ chính xác, retention phù hợp và kiểm tra nguồn tránh mock client location.

## 24. Bảo vệ dữ liệu vị trí và quyền riêng tư

Dữ liệu vị trí có thể tiết lộ thói quen, lộ trình, nơi sinh sống, quan hệ và hoạt động cá nhân. Location signal cần được quản trị như **dữ liệu có độ nhạy đáng kể**, không thu thập chỉ vì API hỗ trợ.

### Các nguyên tắc

1. **Purpose limitation:** chỉ xử lý vì mục đích bảo vệ truy cập/rủi ro cụ thể đã xác định.
2. **Data minimization:** nếu quyết định chỉ cần **country**, không mặc định thu GPS/địa chỉ chính xác.
3. **Transparency:** mô tả loại tín hiệu được sử dụng và thời hạn lưu trong chính sách phù hợp.
4. **Lawful basis/permissions:** tuân thủ nghĩa vụ pháp lý và consent/notice khi áp dụng; quyền app OS location là vấn đề riêng với cơ sở pháp lý.
5. **Least-privilege access:** không để mọi admin/analyst xem toàn bộ lịch sử vị trí.
6. **Retention schedule:** giới hạn lưu raw signal và derived risk event, áp legal hold khi hợp lệ.
7. **Data quality and correction:** có quy trình sửa false attribution, xử lý dữ liệu sai.
8. **Security:** encryption, access audit, không đưa GPS/PII vào logs công khai hoặc telemetry third-party không kiểm soát.
9. **Bias/false positive review:** không biến đặc điểm đi lại/khu vực thành suy luận nhân thân hoặc nhân quả không có cơ sở.
10. **Cross-border processing review:** đánh giá việc gửi IP/location tới vendor nếu có yêu cầu áp dụng.

### Mức dữ liệu phù hợp với từng mục đích

| Mục đích | Dữ liệu tối thiểu có thể đủ | Tránh |
| --- | --- | --- |
| Country restriction tại login | Country estimate, source, confidence, time. | Luôn lưu GPS chính xác của mọi User. |
| Trusted VPN egress | Gateway ID/network zone, source attestation. | Suy vị trí nhà riêng từ IP. |
| Impossible travel detection | Region/country observations, timestamp, signal quality. | Hiển thị chi tiết lịch trình cá nhân cho mọi quản lý. |
| Incident xác nhận device stolen | DeviceRef và telemetry thuộc incident theo thẩm quyền. | Sử dụng lịch sử location cho mục đích khác. |
| Workload region enforcement | Region/VPC/issuer claims đáng tin. | Thu dữ liệu vị trí của service owner con người. |

### Retention không có một con số chung

Thời hạn lưu tùy **loại tài nguyên, mục đích bảo mật, nghĩa vụ pháp lý, hợp đồng và risk assessment**. Không bịa rằng mọi tổ chức phải giữ GPS một năm hoặc xóa ngay khi logout. Có thể lưu **derived decision evidence** (location class, confidence, policy/version, eventId) lâu hơn raw coordinates nếu phù hợp nghĩa vụ, nhưng vẫn cần đánh giá dữ liệu cá nhân và khả năng truy hồi.

### Đường khi User không cấp GPS

User có thể không cấp quyền location API. Một ứng dụng vẫn có thể dựa trên IP/network signals theo quy tắc hợp lệ; nếu hành động bắt buộc cần vị trí thiết bị đáng tin mà không thể chứng minh, có thể Deny hoặc cung cấp **một phương thức xác minh thay thế được phê duyệt**, thay vì ép User chia sẻ tọa độ ngoài phạm vi cần thiết.

## 25. Threat model: location spoofing, policy bypass và poisoning

### Những đối thủ và đường tấn công

| Mối đe dọa | Mô tả | Phòng vệ |
| --- | --- | --- |
| **Client-supplied location spoofing** | Attacker sửa GPS/header hoặc mock device location. | Không tin tự khai, kiểm source/attestation/permission và context. |
| **IP egress laundering** | Truy cập qua VPN/proxy đến country được allow. | Không coi GeoIP là chứng cứ danh tính; device/MFA/role guards. |
| **Trusted CIDR takeover** | IP trước thuộc công ty nay do bên khác kiểm soát. | Ownership review, CIDR lifecycle, certificate/gateway binding. |
| **Risk baseline poisoning** | Attacker đăng nhập nhiều lần khiến nơi lạ thành quen. | Chỉ học từ trusted events, review confirmed compromise, model controls. |
| **Header injection** | Request giả mạo X-Forwarded-For để chọn GeoIP an toàn. | Trusted proxy chain, overwrite headers tại ingress. |
| **GeoIP provider compromise/failure** | Provider trả vùng sai hoặc dữ liệu stale. | Multi-source reasonableness, provenance, fail-safe, monitoring. |
| **Location exception abuse** | User tự approve exception country/VPN rộng. | SoD, approval, scope, expiry, audit. |
| **Session/token replay** | Token lấy cắp được dùng từ location khác hoặc cùng location. | Token binding, short TTL, revocation/introspection, runtime policy. |
| **Admin policy tampering** | Attacker đổi allowlist, threshold hoặc disable logging. | Version control, privileged approval, tamper-evident audit. |
| **Workload location spoofing** | Client tự gửi region/cluster ID được allow. | Trust issuer/attestation và server-side resource config. |

### X-Forwarded-For cần chuỗi proxy đáng tin

Nếu ứng dụng tin giá trị **X-Forwarded-For** do client gửi mà không có trusted reverse proxy xử lý, attacker có thể chọn IP “thuộc quốc gia cho phép” trong header. Cần cấu hình ingress nhận diện **hops được tin cậy, bỏ hoặc chuẩn hóa client-supplied forwarding headers** và phân biệt original client IP với intermediary egress.

### Một IP được phép không chứng minh người dùng sạch

Kẻ tấn công có thể chiếm một máy **ngay trong office network**, dùng credential qua corporate VPN hoặc điều khiển remote browser đang ở country được allow. Geofencing là **một control bổ sung**, không thay phishing-resistant authentication, PAM, least privilege hoặc monitoring.

## 26. Explainability: vì sao hệ thống yêu cầu step-up hoặc Deny?

Một risk-based decision cần **có lý do giải thích được mà không tiết lộ toàn bộ rule bí mật**. Khi User bị chặn vì location, sản phẩm nên phân biệt **network mới**, **policy restriction**, **thiết bị không tin cậy**, **session bị revoke** hoặc **thiếu dữ liệu**.

### Mẫu reason codes

| Code minh họa | Ý nghĩa | Gợi ý xử lý |
| --- | --- | --- |
| LOCATION_UNFAMILIAR | Network/region mới so với baseline. | Step-up/confirm trusted device. |
| LOCATION_SIGNAL_LOW_CONFIDENCE | Không đủ chắc về vị trí. | Revalidate hoặc dùng signal khác. |
| RESTRICTED_NETWORK_ZONE | Kết nối qua zone bị hạn chế cho action. | Dùng access path được duyệt hoặc review exception. |
| TRUSTED_GATEWAY_NOT_VERIFIED | Không chứng minh đi qua gateway bắt buộc. | Kết nối qua phương thức công ty được phê duyệt. |
| HIGH_RISK_GEO_VELOCITY | Hai location observations có vẻ không khả thi. | Điều tra VPN/device/session, step-up theo policy. |
| DEVICE_TRUST_FAILED | Thiết bị bị chặn hoặc không đạt posture. | Khắc phục/enroll device, không chỉ đổi IP. |
| LIFECYCLE_INELIGIBLE | HR/IAM chưa ACTIVE hoặc đã Leaver. | Không xử lý bằng country exception. |
| ACCESS_DENIED_BY_RESOURCE_POLICY | Role/tenant/SoD không cho action. | Access request/owner review bình thường. |

### Audit explanation nên gồm

- Decision outcome (Permit, StepUp, Deny, Restrict, Unknown) và action/resource.
- Signal source, observation time, confidence/freshness **đã dùng**.
- Policy ID/version và reason code.
- Actor/subject/session/device references theo namespace.
- Control/step-up đã được thực thi ở PEP nào.
- Không ghi raw password, token, GPS cực kỳ chi tiết hoặc không cần thiết.

Một User có thể nhận thông báo thân thiện “Vui lòng xác minh lại do đăng nhập từ mạng mới” thay vì chi tiết những threshold hoặc detection logic có thể hỗ trợ kẻ tấn công né tránh. Auditor có thể xem event đầy đủ hơn theo quyền và mục đích điều tra.

## 27. Dòng dữ liệu Location signal: ingest, chuẩn hóa và đánh giá

Một hệ thống risk-based access cần xử lý location từ **nhiều nguồn có semantics khác nhau**, tránh trộn observation, enrichment, inference và policy decision.

### Luồng tham khảo

~~~mermaid
sequenceDiagram
    actor U as User or Workload
    participant GW as Trusted Ingress / Gateway
    participant LOC as Location Enrichment
    participant PIP as Identity / Device / Resource PIP
    participant PDP as Risk / Policy Decision
    participant PEP as IdP or Resource API PEP
    participant AU as Protected Audit
    U->>GW: Authentication/access request
    GW->>GW: Establish trusted source network context
    GW->>LOC: IP/network reference + observedAt
    LOC-->>GW: GeoIP/ASN/proxy class + provenance
    GW->>PIP: Request identity, device, JML and resource facts
    PIP-->>PDP: Verified attributes and freshness
    GW->>PDP: Network/location evidence
    PDP->>PDP: Evaluate mandatory guards + contextual risk
    PDP-->>PEP: Allow / StepUp / Restrict / Deny + obligations
    PEP->>PEP: Enforce on requested action
    PEP-->>AU: Decision + evidence references + actual outcome
    PEP-->>U: Response or challenge
~~~

### Các hợp đồng cần định nghĩa

| Hợp đồng | Điều kiện |
| --- | --- |
| **Ingress provenance** | Chỉ tin IP/proxy identity do gateway xác minh; chuẩn hóa forwarding headers. |
| **GeoIP lookup** | Ghi version dataset, fallback behavior, confidence/granularity. |
| **Device location** | Có permission/trust, observedAt và accuracy; không tin tọa độ client vô điều kiện. |
| **Identity context** | Nối tới stable IAM identity, account, tenant, lifecycle source. |
| **Resource context** | ResourceId/action/classification/tenant được server xác minh. |
| **PDP response** | Có outcome, policy version, reason, obligations và expiry. |
| **PEP enforcement** | Không chỉ hiển thị challenge; thực sự chặn action khi chưa đạt điều kiện. |
| **Audit** | Quyết định và thực thi có correlationId, không lưu bí mật/địa điểm thô quá mức. |

### Snapshot tại login không thay vị trí hiện hành

Một risk evaluation tại 09:00 có thể đúng với lúc login, nhưng User chuyển mạng lúc 10:00. Nếu giao diện tiếp tục cho phép tải dữ liệu nhạy cảm tới 17:00 mà không kiểm lại, chính sách location runtime không được thực thi. **Phải đặt contract**: reevaluate khi đổi network, refresh session, token issuance, action nhạy cảm hoặc thời hạn signal hết.

### Cache có thể hữu ích nhưng cần guard

Caching GeoIP và risk decisions giảm độ trễ; tuy nhiên phải có **TTL theo risk tier, invalidation theo incident/JML, version policy và tín hiệu device**. Đừng cache một Permit location-based lâu hơn thời hạn dữ liệu cần kiểm chứng hoặc bỏ qua một sự kiện credential revoked.

## 28. Pseudocode: đánh giá yêu cầu truy cập dựa trên Location signal

Mã giả này hướng dẫn thiết kế **trusted data flow** và cách dùng vị trí như tín hiệu, không phải một policy language chuẩn hay API sẵn có.

### 28.1. Thu thập tín hiệu

~~~text
collectLocationEvidence(request, trustedIngress):
    source = trustedIngress.resolveNetworkOrigin(request)

    if not source.verified:
        return LocationEvidence(
            state = UNKNOWN,
            reason = "UNTRUSTED_NETWORK_CONTEXT"
        )

    network = classifyNetworkOrigin(
        source.ipRef,
        source.gatewayIdentity,
        source.trustedProxyChain
    )

    geo = geoipProvider.lookup(source.ipRef)
    if geo.unavailable or geo.qualityBelowPolicyMinimum:
        geoResult = UNKNOWN_WITH_SOURCE_METADATA
    else:
        geoResult = canonicalizeGranularityAndCountry(geo)

    deviceLocation = optionalDeviceLocationEvidence(
        request.deviceRef,
        requireVerifiedSource = true,
        doNotTreatClientHeaderAsProof = true
    )

    return LocationEvidence(
        observedEntity = "NETWORK_EGRESS",
        geoEstimate = geoResult,
        networkZone = network.zone,
        proxyClassification = network.proxyClass,
        trustedGateway = network.verifiedCorporateGateway,
        deviceLocation = deviceLocation,
        observedAt = source.observedAt,
        providerVersion = geo.providerVersion,
        confidence = assessQualityWithoutInventingPrecision(geo, network),
        integrity = source.integrity
    )
~~~

**Không trả** “location=trusted office” khi GeoIP provider lỗi. Một IP nằm trong named CIDR cũng cần kiểm CIDR ownership còn đúng và request thật sự đến từ nguồn quan sát tin cậy.

### 28.2. Authorization và rủi ro

~~~text
authorizeAccess(request, authnContext):
    subject = resolveTrustedPrincipal(authnContext)
    resource = resolveTrustedResource(request.resourceRef)

    if subject unresolved or resource unresolved:
        return DENY_UNVERIFIED_PRINCIPAL_OR_RESOURCE

    lifecycle = loadCurrentLifecycleOrWorkloadOwnerPolicy(subject)
    entitlement = loadCurrentEntitlements(subject, resource)
    policy = loadVersionedRiskAccessPolicy(resource, request.action)

    if not lifecycle.eligible:
        return DENY_LIFECYCLE_GUARD
    if not entitlement.permits(request.action, resource):
        return DENY_NO_ENTITLEMENT
    if resource.tenantNotAllowed(subject):
        return DENY_TENANT_SCOPE
    if policy.mandatorySoDOrCredentialVeto(authnContext, subject):
        return DENY_MANDATORY_GUARD

    loc = collectLocationEvidence(request, trustedIngress)
    device = loadVerifiedCurrentDeviceContext(request)
    session = loadCurrentSessionAndAssurance(authnContext)

    if policy.requiresVerifiedNetworkZone and
       not loc.networkZone.isVerifiedAndAllowed:
        return DENY_OR_APPROVED_ALTERNATE_PATH

    risk = evaluateContextualRisk(
        loc.quality,
        loc.unfamiliarity,
        loc.networkClassification,
        device.posture,
        session.assurance,
        request.action,
        resource.sensitivity
    )

    if risk.mandatoryDeny:
        return DENY_AND_CONTAIN_WHEN_REQUIRED
    if risk.requiresAdditionalAssurance:
        return STEP_UP_WITH_BOUND_SESSION_ACTION_AND_TTL
    if risk.onlyPermitsReducedScope:
        return RESTRICT_TO_AUTHORIZED_LOW_RISK_ACTIONS

    return PERMIT_WITH_LIMITED_SCOPE_AND_AUDIT
~~~

**Permit không cấp role mới**; nó chỉ cho phép action đã có entitlement và đạt các điều kiện bắt buộc. Trường hợp service/workload dùng nguồn context khác Human User nhưng vẫn cần identity, trust, scope, resource policy.

### 28.3. Step-up và re-evaluation

~~~text
resumeAfterStepUp(challengeResult, originalDecision):
    if challengeResult.invalid or challengeResult.expired:
        return DENY

    if not challengeResult.boundTo(
        subjectId = originalDecision.subjectId,
        sessionId = originalDecision.sessionId,
        resourceId = originalDecision.resourceId,
        action = originalDecision.action
    ):
        return DENY_CONTEXT_MISMATCH

    latest = revalidateCriticalCurrentGuards(
        lifecycle,
        entitlement,
        resource,
        session,
        device,
        locationPolicy
    )
    if not latest.allMandatoryGuardsSatisfied:
        return DENY

    if challengeResult.assuranceBelowRequirement:
        return STEP_UP_STILL_REQUIRED

    return PERMIT_ONLY_ORIGINAL_APPROVED_SCOPE
~~~

Một User hoàn tất MFA không có nghĩa challenge được **dùng lại vô hạn** cho một action/tenant khác. Nếu policy yêu cầu fresh location sau step-up, phải lấy context mới thay vì tin snapshot cũ.

### 28.4. Vị trí thay đổi trong session

~~~text
onTrustedNetworkContextChanged(sessionRef, newContext):
    session = loadCurrentSession(sessionRef)
    if session.revoked or session.expired:
        return NO_REACTIVATION

    newRisk = evaluateCurrentPolicy(newContext, session)

    if newRisk.requiresRevocation:
        revokeOrRestrictSessionWithTargetVerification(sessionRef)
    else if newRisk.requiresStepUp:
        requireFreshChallengeBeforeSensitiveActions(sessionRef)
    else:
        keepExistingAuthorizedScope(sessionRef)

    auditDecisionWithSourceQualityAndPolicyVersion()
~~~

Không phải mọi IdP/RP có event network-change liên tục. Khi không hỗ trợ, **giới hạn thời hạn session/token và re-evaluate ở action nhạy cảm** theo mức rủi ro; công bố phần quyền còn tồn dư.

## 29. Impossible travel detection: pseudocode có kiểm tra chất lượng

Một thuật toán không nên tính vận tốc từ mọi login event mà không kiểm source và network intermediary.

~~~text
detectSuspiciousGeoVelocity(identityId, currentEvent):
    if currentEvent.principalType != HUMAN:
        return NOT_APPLICABLE

    if not currentEvent.authnWasTrusted:
        return INSUFFICIENT_TRUST

    if currentEvent.locationIsNetworkEgressWithLowQuality:
        return SIGNAL_LOW_CONFIDENCE

    previous = findPreviousTrustedComparableEvent(
        identityId,
        excludeConfirmedCompromiseBaseline = true,
        requireSameSemanticLocationType = true
    )
    if previous unavailable:
        return INSUFFICIENT_HISTORY

    if previous.timestampQualityPoor or currentEvent.clockQualityPoor:
        return UNRELIABLE_TIME

    if bothEventsShareTrustedCorporateVpnOrVDIExplanation:
        return EXPLAINABLE_EGRESS_CHANGE

    distanceRange = estimateDistanceWithLocationUncertainty(
        previous.location, currentEvent.location
    )
    elapsed = currentEvent.observedAt - previous.observedAt

    if elapsed <= 0 or distanceRange.unreliable:
        return INDETERMINATE

    if velocityRiskAboveCalibratedPolicyThreshold(
        distanceRange,
        elapsed,
        currentEvent.networkContext
    ):
        return RISK_SIGNAL_TO_CORRELATE_NOT_AUTOMATIC_COMPROMISE

    return NO_GEO_VELOCITY_ANOMALY_DETECTED
~~~

### Cải tiến quan trọng

- So sánh **các loại location tương đương**: không lấy GPS chính xác của device lần 1 và cloud egress GeoIP lần 2 như hai địa điểm vật lý.
- Với **uncertainty radius**, ước lượng khoảng cách có biên và diễn giải thận trọng.
- Chỉ dùng các event có **timestamp và identity mapping** tin cậy.
- Loại trừ hoặc giảm trọng số trường hợp VPN/VDI/mobile routing.
- Không để “địa điểm từng bị compromise” tự động thành baseline thân thuộc.
- Kết quả nên kích hoạt **additional verification/investigation** theo policy, không tự kết luận tội lỗi.

### Trường hợp hai sessions đồng thời

Nếu hai sessions cùng User xuất hiện ở hai nước và đều có MFA, chưa đủ chứng minh một người đã du hành không tưởng. Có thể một session là **token bị copy**, một session qua VPN hoặc User có remote workstation. Cần kiểm **device/session binding, token reuse, login method, risk events và API actions** thay vì dựa vào phép chia khoảng cách/thời gian.

## 30. Audit và sự kiện cho location-based access

Location signal có thể là dữ liệu nhạy cảm; audit nên lưu **đủ bằng chứng cho quyết định bảo mật**, không mặc định thu tọa độ toàn bộ người dùng.

### Event schema minh họa

~~~json
{
  "eventType": "IAM_RISK_BASED_ACCESS_DECISION",
  "eventId": "evt-risk-20261201-008",
  "correlationId": "access-attempt-771",
  "subjectRef": "IAM:ID-LAN-2041",
  "clientRef": "finance-portal",
  "sessionRef": "sess-88",
  "deviceRef": "uem:tenant-b:dev-882",
  "resourceRef": "finance:tenant-b:reports-prod",
  "action": "report.export",
  "observedAt": "2026-12-01T09:00:00+07:00",
  "locationEvidence": {
    "observedEntity": "NETWORK_EGRESS",
    "source": "TRUSTED_INGRESS_GEOIP",
    "granularity": "COUNTRY",
    "countryCode": "SG",
    "confidence": "MEDIUM",
    "corporateVpnVerified": true,
    "fresh": true
  },
  "identityLifecycleVersion": 72,
  "policyVersion": "finance-risk-location-v4",
  "assuranceBefore": "MFA_SESSION_STANDARD",
  "decision": "STEP_UP_REQUIRED",
  "reasonCodes": ["UNFAMILIAR_NETWORK_CONTEXT", "SENSITIVE_ACTION"],
  "enforcementPoint": "finance-api-gateway",
  "enforcementResult": "CHALLENGE_ISSUED"
}
~~~

Đây là **schema ví dụ**, không là chuẩn OAuth/OIDC/SCIM. Giá trị country dùng để minh họa egress, **không xác nhận vị trí người dùng**. Không ghi raw token, session cookie, password, MFA secret hoặc tọa độ GPS không cần thiết.

### Những thành phần audit cần phân biệt

| Thành phần | Câu hỏi |
| --- | --- |
| **Signal observation** | Nguồn nào quan sát IP/region/zone, lúc nào, confidence bao nhiêu? |
| **Risk evaluation** | Những feature nào được dùng, policy/model version nào? |
| **Decision** | Permit/StepUp/Restrict/Deny/Indeterminate vì điều kiện gì? |
| **Enforcement** | IdP, gateway hay API đã thực hiện yêu cầu chưa? |
| **User challenge** | Step-up có hoàn tất với assurance và session binding phù hợp không? |
| **Subsequent action** | API có Permit hoặc Deny action nhạy cảm đúng scope? |
| **Lifecycle/policy change** | User Mover/Leaver hoặc named location bị sửa ở thời điểm nào? |

### Một quyết định không phải hành động đã thực thi

Nếu PDP trả Deny nhưng Resource Server vẫn trả dữ liệu do authorization check diễn ra sau khi query, audit phải báo **enforcement failure**. Nếu IdP yêu cầu MFA nhưng ứng dụng có direct API token không kiểm, location policy login chưa bảo vệ đường API đó.

### Xử lý event đến muộn

~~~text
09:00 location signal observed
09:01 policy decision Permit issued
09:02 device marked COMPROMISED
09:03 old Permit audit event ingested late

Correct:
    record historical decision at its original time
    do not let event arrival reauthorize compromised device
~~~

Dùng **eventId, sourceVersion, occurredAt, receivedAt, policy version và revocation epoch**; không lấy order theo ingestion làm proof quyết định hiện hành.

## 31. Giám sát chất lượng tín hiệu và hiệu quả policy

| Chỉ số | Nội dung đo | Những điều có thể hiểu sai |
| --- | --- | --- |
| **Location signal coverage** | Tỷ lệ requests có signal đủ chất lượng theo policy. | Không có signal không đồng nghĩa “không có rủi ro”. |
| **GeoIP confidence distribution** | Phân bố confidence/granularity theo mạng/vùng. | Mức confidence vendor không phải xác suất tuyệt đối. |
| **GeoIP dataset freshness** | Tuổi/version của dữ liệu ánh xạ IP. | Update mới không tự sửa lỗi proxy/CGNAT. |
| **Trusted egress ownership freshness** | Bao lâu từ lần review CIDR/ASN tới hiện tại. | CIDR cũ có thể đổi owner. |
| **VPN/proxy false-positive rate** | Cảnh báo location do đường egress hợp lệ. | Điều tra có bằng chứng; không label tất cả VPN là xấu. |
| **Impossible-travel alert precision** | Tỷ lệ cảnh báo đã điều tra có tín hiệu compromise thực. | Không nhầm thiếu kết luận với false positive chắc chắn. |
| **Step-up challenge success** | User hợp lệ hoàn tất yêu cầu ở mạng lạ. | Success cao không đủ chứng minh tấn công bị chặn. |
| **Location-related helpdesk tickets** | Ma sát/lockout do policy. | Cần phân loại first-day/travel/accessibility. |
| **Restricted action denial coverage** | PEP thực thi policy sensitive actions bao nhiêu request. | Deny tại IdP chưa chứng minh API đã Deny. |
| **Policy drift across IdP/RP/API** | Các thực thể dùng policy version khác nhau. | Cùng country không đủ kết luận giống quyết định. |
| **Decision-to-enforcement lag** | Thời gian từ PDP decision tới PEP xử lý. | Async event không đảm bảo chặn token cũ. |
| **Session/token residual window** | Thời gian session có thể tiếp tục sau risk raise/revoke. | Đo resource scope, không chỉ app status. |
| **Unknown signal handling** | Permit/StepUp/Deny khi GeoIP/PIP unavailable. | Một policy fail-open có thể tạo đường bỏ guard. |
| **Privacy access/export rate** | Ai xem/xuất location events và vì mục đích gì. | Telemetry rủi ro là dữ liệu nhạy cảm. |
| **Unauthorized location-policy changes** | CIDR/allowlist/threshold bị đổi ngoài approval. | Có thể mở rộng truy cập mà không đổi role. |

### Đừng tối ưu chỉ bằng tỷ lệ chặn

Một hệ thống tăng tỷ lệ Deny lên 50% nhờ chặn mọi người dùng VPN không nhất thiết an toàn hơn: có thể làm gián đoạn nhân viên hợp lệ trong khi attacker dùng office remote desktop vẫn được Permit. Nên đo **độ đúng quyết định, coverage, risk reduction, false positives, false negatives, residual access và khả năng phục hồi hợp pháp**.

### Kiểm soát chất lượng model

Nếu dùng ML/anomaly detection, cần **ground-truth review, drift monitoring, incident feedback, rollback, calibration, bias assessment và versioned decisions**. Không tự sửa scoring rule trong production chỉ vì vài cảnh báo nhìn bất thường.

## 32. Ma trận kiểm thử Location signal và risk-based access

Bộ kiểm thử nên tách **nguồn tín hiệu, chất lượng dữ liệu, hành vi policy, lớp thực thi, tương tác session/token, JML, machine identity và quyền riêng tư**. Sử dụng test identities/network và tài nguyên được phép; không tự đánh cắp token thật, giả mạo người khác hay thao tác phá hoại production.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| LS-01 | Human ACTIVE, role đúng, trusted device và trusted network. | Permit đúng action trong scope; audit context/policy. |
| LS-02 | Human ACTIVE nhưng không có entitlement, IP ở office CIDR. | Deny do thiếu quyền, không được GeoIP override. |
| LS-03 | Human đã Leaver, login từ trusted network. | Hard deny và xử lý sessions/credentials theo policy. |
| LS-04 | Joiner pre-created account, login trước startAt tại office. | Không mở business access trước effectiveAt. |
| LS-05 | Joiner mới chưa có location history nhưng đã proofing/MFA. | Chính sách warm-up/step-up hợp lệ, không kết luận compromise mặc định. |
| LS-06 | Mover đổi workLocation và team, token cũ có role Finance. | Không còn Finance entitlement; location không giữ role cũ. |
| LS-07 | Rehire quay lại, history location cũ tồn tại. | Không tự hồi sinh sessions/exceptions/role cũ. |
| LS-08 | Contractor hết hạn contract nhưng partner IP quen thuộc. | Deny theo contract/lifecycle, không theo IP. |
| LS-09 | User đi công tác, GeoIP mới và managed device hợp lệ. | Step-up/allow theo policy, không tự chặn vĩnh viễn. |
| LS-10 | Corporate VPN egress ở quốc gia khác physical location. | Đánh dấu network egress đúng semantics, tránh false country attribution. |
| LS-11 | Mobile carrier chuyển IP GeoIP giữa hai thành phố trong vài phút. | Không tự kết luận impossible physical travel. |
| LS-12 | VDI ở cloud region khác nơi User đang ngồi. | Phân biệt VDI egress với vị trí người dùng. |
| LS-13 | Client tự gửi location header “office”. | Không chấp nhận là nguồn trust cho Allow. |
| LS-14 | Attacker tự sửa X-Forwarded-For. | Ingress chuẩn hóa trusted proxy chain; không bypass geofence. |
| LS-15 | GPS OS permission bị từ chối nhưng IP vẫn quan sát được. | Đánh signal unavailable/alternative; không suy “compromised”. |
| LS-16 | GeoIP provider timeout khi login low-risk. | Áp fail-safe hợp lệ theo risk tier, audit UNKNOWN. |
| LS-17 | GeoIP provider timeout khi action bắt buộc verified location. | Không Permit nếu guard bắt buộc không đạt. |
| LS-18 | GeoIP quốc gia gần biên giới bị sai. | Accuracy/confidence và review xử lý false positive. |
| LS-19 | IP/ASN egress do công ty ngừng sở hữu. | Trusted location review/expiry chặn stale CIDR. |
| LS-20 | Network zone được quản trị nhưng device bị COMPROMISED. | Deny theo device hard guard dù trusted egress. |
| LS-21 | User pass MFA step-up nhưng không có role Admin. | Vẫn Deny privileged action. |
| LS-22 | Step-up challenge của session A được replay trong session B. | Deny cross-session, bind challenge chính xác. |
| LS-23 | Location signal quá TTL tại action export. | Revalidation/step-up/fail-safe theo policy. |
| LS-24 | Một browser session giữ token sau khi đổi VPN. | Kiểm runtime enforcement/token window; không giả định login policy đang được tái áp. |
| LS-25 | Refresh token bị revoke nhưng JWT cũ còn hiệu lực. | Ghi residual action window và Resource Server test. |
| LS-26 | Policy geofence country allowlist thay đổi trong lúc session đang mở. | Policy version mới được cưỡng chế theo boundary đã định. |
| LS-27 | Named location policy thêm CIDR rộng ngoài approval. | Change control/SoD và audit cảnh báo. |
| LS-28 | Hai alerts cùng dùng một GeoIP provider data. | Không double-count như hai bằng chứng độc lập. |
| LS-29 | Identity login ở hai quốc gia do corporate VPN switch. | Heuristic giải thích network context, không auto compromise. |
| LS-30 | Hai events có timestamp lệch đồng hồ. | Không tính geo-velocity sai; audit clock quality. |
| LS-31 | Impossible travel trigger đồng thời với device mới và credential reuse. | Correlate nhiều tín hiệu, step-up/deny/investigate theo risk policy. |
| LS-32 | Attacker dùng office VPN của account bị lộ. | Trusted location không bỏ authn/device/role guards. |
| LS-33 | App chỉ kiểm geolocation khi login nhưng API nhạy cảm không kiểm. | Ghi enforcement gap; không claim continuous access. |
| LS-34 | API trả Deny nhưng action đã commit side effect. | FAIL; PEP phải kiểm trước action. |
| LS-35 | Cloud workload có egress từ NAT chung nhiều pods. | Không coi NAT IP là workload instance identity. |
| LS-36 | Workload region do client tự khai không có attestation. | Deny hoặc no-trust; dùng source đáng tin. |
| LS-37 | Workload token aud sai dù IP ở VPC tin cậy. | Deny audience/permission, không dựa network. |
| LS-38 | Compromised CI agent trong allowed cloud region. | Revoke/contain workload trust; region không override. |
| LS-39 | PAM role không active nhưng User ở office trusted CIDR. | Deny admin action; JIT/PAM authority bắt buộc. |
| LS-40 | Emergency recovery cần mạng ngoài VPN bị lỗi. | Chỉ emergency path đã phê duyệt với custody/TTL/audit, không permit-all. |
| LS-41 | User bị SUSPENDED và có country exception còn hạn. | Exception không bỏ qua lifecycle guard. |
| LS-42 | Device LOST, login từ IP GeoIP quen thuộc. | Deny theo device trust, điều tra session. |
| LS-43 | Một request gồm network GeoIP và GPS client giả. | Provenance/quality policy không nâng confidence do dữ liệu giả. |
| LS-44 | Reviewer điều chỉnh false-positive classification. | Có audit correction, không xóa event gốc. |
| LS-45 | GeoIP enrichment chỉ trả city nhưng confidence thấp. | Không dùng city làm exact geofence khi accuracy không đủ. |
| LS-46 | User có IP thuộc quốc gia không được phép vì corporate proxy. | Policy phân biệt network egress, exception và restriction nếu phù hợp. |
| LS-47 | Đổi role definition làm quyền rộng hơn dù location không đổi. | Ghi access-affecting change và reauthorize API. |
| LS-48 | User dùng nhiều browser sessions từ các IP khác nhau. | Không đếm location observations thành các identities mới. |
| LS-49 | SIEM nhận event trễ sau khi session đã revoked. | Không resurrect session hoặc biến policy cũ thành current. |
| LS-50 | PIP location cache cũ vẫn nói allowed sau policy update. | Version/freshness guard, detect drift. |
| LS-51 | Staff location history được xuất trái quyền. | Audit/export access bị chặn; privacy incident handling. |
| LS-52 | Decision log ghi raw GPS mọi request dù policy chỉ cần country. | FAIL data minimization; thu hẹp logging. |
| LS-53 | Location provider không phân trang được audit logs. | Missing coverage / UNKNOWN, không diễn giải “zero anomalies”. |
| LS-54 | Risk model calibration drift khi nhiều nhân viên đi công tác. | False-positive review, versioned backtest/rollout. |
| LS-55 | Hard geo restriction yêu cầu nguồn chính xác nhưng evidence chỉ là VPN IP. | Không tuyên bố compliance dựa trên egress GeoIP. |
| LS-56 | Country code sai/missing trong raw response. | Validation, unknown và an toàn khi mapping lỗi. |
| LS-57 | Two-person approval cho named location do hai account một người. | SoD nhận cùng human identity, từ chối self-approval. |
| LS-58 | Exception hết hạn nhưng refresh token có claim cũ. | Enforce expiry/resource scope, kiểm residual. |
| LS-59 | Một device có IPv4 và IPv6 GeoIP khác nhau. | Không đánh nhãn physical travel chỉ vì thay IP family. |
| LS-60 | Resource thuộc tenant B nhưng account/exception tenant A. | Deny tenant mismatch dù network trusted. |

### Given–When–Then

~~~gherkin
Feature: Location is a contextual signal, not a substitute for identity or access rights

  Scenario: A trusted network cannot authorize a leaver
    Given Lan's authoritative lifecycle state is TERMINATED
    And a login request arrives through the known corporate gateway
    When the risk-based policy evaluates the request
    Then access is denied because of the lifecycle hard guard
    And the trusted network does not override the denial

  Scenario: A corporate VPN should not be mistaken for the person's physical location
    Given Lan is traveling and uses a verified corporate VPN
    And the public egress IP is geolocated to another country
    When the location signal is normalized
    Then its observed entity is classified as NETWORK_EGRESS
    And the decision does not claim Lan is physically in the egress country

  Scenario: Unfamiliar location prompts verification for a sensitive action
    Given Lan has the required FinanceExporter entitlement
    And the location context is unfamiliar
    And the resource requires fresh strong authentication
    When Lan requests a sensitive export
    Then a session-bound step-up challenge is required by policy
    And the action is not performed before the required verification

  Scenario: Client-provided location cannot bypass a restricted network policy
    Given an application requires a verified corporate ingress
    And the request arrives from an unverified network
    When the client sends a fake office-location header
    Then the trusted ingress ignores the unverified claim
    And the request is denied or routed to approved alternative verification

  Scenario: Impossible travel remains a risk signal rather than a verdict
    Given two login events appear far apart in a short interval
    And one event is from a corporate VPN egress
    When geo-velocity is evaluated
    Then network provenance and timestamp quality are considered
    And the events are not automatically labeled confirmed account theft

  Scenario: A stale location decision cannot revive a revoked session
    Given a location-based Permit decision was issued before device compromise
    And the device trust and session were revoked afterwards
    When an old Permit event arrives late
    Then it is kept as historical evidence
    And current authorization does not become Permit

  Scenario: A workload region label is not a trusted access credential
    Given a workload calls a protected production API
    And the workload provides a region label without verified trust
    When the API evaluates location and workload identity conditions
    Then the unverified region label does not establish approved origin
    And authorization requires current issuer, audience and resource guards

  Scenario: Location logging does not retain unnecessary exact coordinates
    Given a policy decision only requires a country-level network estimate
    When the access decision is logged
    Then the audit event records source, quality, country and policy version
    And no unnecessary precise personal GPS coordinates are stored
~~~

### Tiêu chí PASS không chỉ là HTTP status

- **Deny response** không đạt nếu API vẫn thực hiện side effect trước khi kiểm policy.
- **Step-up issued** không đạt nếu action nhạy cảm đã hoàn thành trước khi User xác minh.
- **Policy changed** không đạt nếu PEP khác vẫn dùng version cũ không có remediation.
- **Trusted country matched** không đủ nếu identity đã Leaver, session revoked hoặc role thiếu.
- **Logged anomaly** không đồng nghĩa risk đã được cưỡng chế tại Resource Server.
- Với các bài test về quyền riêng tư, cần kiểm cả **raw logs, distributed traces, telemetry vendor và error responses**, không chỉ một audit table.

## 33. Tình huống thực hành

### Tình huống A — Nhân viên ở Việt Nam, IP ở Singapore

**Bối cảnh:** Lan đang làm việc từ Thành phố Hồ Chí Minh, nhưng Finance Portal thấy IP Singapore vì corporate VPN egress.

**Câu hỏi:** Hệ thống có thể kết luận Lan đi công tác Singapore không?

**Gợi ý:** Không. Đây là **vị trí egress của VPN**, không là vị trí người. Kiểm network provenance và risk context; nếu source đáng tin, giảm false-positive với các guard identity/device vẫn bắt buộc.

### Tình huống B — Hai login trong 10 phút ở hai nước

**Bối cảnh:** SIEM phát hiện login đầu ở Việt Nam và login sau ở Nhật Bản cách nhau 10 phút.

**Câu hỏi:** Có thể đóng account ngay vì impossible travel không?

**Gợi ý:** Không chỉ dựa vào khoảng cách/thời gian. Kiểm GeoIP quality, VPN, remote browser, timestamps, device binding, token reuse và hành động nhạy cảm; sau đó step-up/contain theo policy và evidence.

### Tình huống C — Mạng office nhưng thiết bị bị compromise

**Bối cảnh:** Attacker chiếm laptop đang kết nối mạng nội bộ và gọi production API từ office IP.

**Câu hỏi:** Trusted location có giúp Permit không?

**Gợi ý:** Không khi device/credential đã bị đánh dấu compromise theo policy. Chặn theo device/session, đánh giá token và entitlement; office network không bảo đảm actor đáng tin.

### Tình huống D — User không cho quyền GPS

**Bối cảnh:** Ứng dụng payroll chỉ cần biết User đang dùng network nào cho mục đích risk, nhưng UI buộc cấp quyền GPS chính xác để đăng nhập.

**Câu hỏi:** Điều gì cần được xem lại?

**Gợi ý:** **Data minimization, mục đích, quyền truy cập và giải pháp ít xâm phạm hơn**. Có thể dùng network/IdP signals; nếu policy thật sự cần device presence, phải giải thích yêu cầu và có đường thay thế hợp lệ nếu phù hợp.

### Tình huống E — Country allowlist là toàn bộ authorization

**Bối cảnh:** API finance.export chỉ kiểm GeoIP thuộc quốc gia cho phép, bỏ qua role và tenant.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Bất kỳ requester có khả năng dùng egress được phép có thể qua guard. Phải kiểm **authenticated identity, entitlement, resource/tenant, device/session, SoD** trước Permit.

### Tình huống F — Mover chuyển chi nhánh, access không cập nhật

**Bối cảnh:** Minh chuyển từ Finance VN sang Support SG. Hệ thống cập nhật known country nhưng FinanceExporter role và API token cũ vẫn có thể export.

**Câu hỏi:** Location update đã xử lý Mover chưa?

**Gợi ý:** Chưa. Role/Group/direct grants và token/session phải được revoke/reevaluate theo JML, độc lập với location baseline.

### Tình huống G — Named location CIDR đã được bên khác sử dụng

**Bối cảnh:** Công ty ngừng thuê proxy cũ nhưng vẫn giữ CIDR trong trusted locations.

**Câu hỏi:** Lỗ hổng?

**Gợi ý:** Trust based on stale IP ownership. Cần network owner review, CIDR lifecycle, approval, version, revoke và kiểm thử Negative từ IP không còn được quản trị.

### Tình huống H — Location risk ở IdP nhưng app token còn hiệu lực

**Bối cảnh:** IdP thấy session từ anonymizing proxy và Deny new login, nhưng app-local JWT cũ tiếp tục được API dùng.

**Câu hỏi:** Điểm thực thi nào thiếu?

**Gợi ý:** Resource Server/runtime authorization hoặc session/token revocation contract. Phải đo residual access window và dùng các cơ chế được target hỗ trợ.

### Tình huống I — PIP vị trí timeout

**Bối cảnh:** GeoIP service lỗi; policy sensitive export yêu cầu network zone verified.

**Câu hỏi:** Có nên dùng cached country “office” từ 2 ngày trước?

**Gợi ý:** Không nếu vượt freshness policy. Dùng Unknown và fail-safe/alternate verification được phê duyệt; không auto Permit.

### Tình huống J — Service account chạy từ NAT chung

**Bối cảnh:** Hai workloads production và staging cùng NAT egress. Security định phân biệt production bằng public IP.

**Câu hỏi:** Vì sao không đủ?

**Gợi ý:** NAT IP không định danh workload. Dùng **workload issuer/subject, namespace, audience, attested cluster/VPC, resource scope** và network policy thực tế.

### Tình huống K — Break-glass khi VPN không hoạt động

**Bối cảnh:** Corporate VPN outage trong sự cố cần phục hồi IAM. Runbook yêu cầu admin chỉ có thể vào từ VPN.

**Câu hỏi:** Có nên tạm cho mọi IP trên Internet vào GlobalAdmin?

**Gợi ý:** Không. Phải có **independent emergency path** với custody, authority/incident, MFA/recovery authentication khả thi, scope/TTL và audit.

### Tình huống L — Risk scoring double-count VPN

**Bối cảnh:** Vendor A và B cùng dùng GeoIP feed, đều đánh “datacenter proxy”; policy coi hai kết quả là hai tín hiệu độc lập và block.

**Câu hỏi:** Lỗi phương pháp?

**Gợi ý:** Feature dependence/double counting. Kiểm provenance, correlation, calibration, false-positive rate và thay đổi scoring có kiểm soát.

### Tình huống M — GPS chính xác nhưng device đã root/compromised

**Bối cảnh:** Mobile app báo GPS nằm trong office zone với accuracy 10 m, nhưng device không còn trusted và cho phép mock location.

**Câu hỏi:** Có đủ chứng cứ để cho phép payroll export không?

**Gợi ý:** Không. Accuracy của một signal không chứng minh integrity của source; cần device trust và hard authorization guards.

### Tình huống N — Data residency chỉ dựa GeoIP

**Bối cảnh:** Ứng dụng tuyên bố dữ liệu khách hàng không ra khỏi region A vì chỉ cho IP từ region A đăng nhập, trong khi bản sao backup được lưu region B.

**Câu hỏi:** Tuyên bố có chính xác không?

**Gợi ý:** Không. Data residency phụ thuộc **nơi lưu trữ, xử lý, sao chép và truyền**, không chỉ location của client login.

### Tình huống O — Contractor hết hợp đồng, IP đối tác vẫn nằm trong allowlist

**Bối cảnh:** Partner VPN là named trusted zone; contractor đã hết endAt nhưng còn app session.

**Câu hỏi:** Điều gì phải thắng?

**Gợi ý:** Contract/lifecycle authority và resource policy; named location không bỏ hard deny. Đánh giá app session/token tồn dư và contractor access review.

### Tình huống P — Chỉ ghi risk score, không ghi nguồn

**Bối cảnh:** Log ghi “Risk=85, StepUp” nhưng không ghi network egress hay rule/version, hôm sau model thay đổi.

**Câu hỏi:** Kiểm toán tái dựng được không?

**Gợi ý:** Khó. Cần **signal source/type, confidence/freshness, policy/model version, decision and enforcement**, theo mức privacy phù hợp.

### Tình huống Q — Lịch sử địa điểm bị dùng ngoài mục đích

**Bối cảnh:** Đội bảo mật lưu GPS từng phút của nhân viên để phát hiện login lạ; quản lý nghiệp vụ muốn xem lịch trình làm việc.

**Câu hỏi:** Có nên cung cấp?

**Gợi ý:** Không mặc nhiên. Mục đích, quyền xem, minimization, thông báo, căn cứ pháp lý và retention cần được đánh giá riêng; log bảo mật không là nguồn theo dõi cá nhân vô hạn.

### Tình huống R — GeoIP vendor cập nhật country cho cùng IP

**Bối cảnh:** Hai lần login qua cùng public IP nhưng vendor thay ánh xạ từ Country A sang B, SIEM báo impossible travel.

**Câu hỏi:** Kiểm thử nào thiếu?

**Gợi ý:** Kiểm version GeoIP dataset, source provenance, identity/session/device binding và quality. Không suy người đã di chuyển chỉ vì mapping của vendor thay đổi.

## 34. Những sai lầm triển khai phổ biến

1. **Coi GeoIP là vị trí vật lý chính xác của con người.** IP thường thể hiện network egress qua VPN, proxy hoặc carrier.
2. **Dùng country match thay identity và entitlement.** Vị trí không cho User role mà họ không có.
3. **Tự cho trusted office CIDR bỏ qua mọi MFA.** Mạng nội bộ hoặc VPN có thể bị chiếm quyền; risk tier và MFA vẫn cần.
4. **Không phân biệt HR workLocation với live location.** Địa điểm công việc không chứng minh session đang ở đó.
5. **Tính impossible travel từ hai GeoIP kém chất lượng.** Có thể chỉ là đổi egress/GeoIP mapping.
6. **Không kiểm proxy/VPN/VDI.** Dẫn tới cảnh báo sai và chặn User đi công tác hợp lệ.
7. **Dùng địa chỉ IP như device ID vĩnh viễn.** NAT, IPv6 và mobile handover khiến IP không ổn định.
8. **Tin X-Forwarded-For từ client.** Attacker có thể tự chọn IP “được phép” nếu ingress không chuẩn hóa.
9. **Tin country/gps header do app gửi không có chứng thực.** Source integrity không được xác minh.
10. **Coi location UNKNOWN là office trusted.** Missing evidence không phải một Permit signal.
11. **Coi UNKNOWN là confirmed malicious.** Thiếu GPS không chứng minh User là attacker.
12. **Không lưu source/confidence/freshness.** Audit không giải thích được một quyết định.
13. **Đặt confidence vendor như xác suất người ở đúng địa chỉ.** Semantics có thể khác.
14. **Cộng hai nguồn GeoIP giống nhau như bằng chứng độc lập.** Double counting làm score sai.
15. **Để model tự học location attacker làm normal baseline.** Không kiểm verified login/training data.
16. **Không có policy cho Joiner mới.** Người chưa có lịch sử location bị lockout ngày đầu.
17. **Không cập nhật location exceptions khi Mover/Leaver.** Quyền phụ hoặc đường bypass còn tồn dư.
18. **Mặc định contractor từ mạng ngoài là attacker.** Cần hợp đồng, sponsor, identity trust và resource policy.
19. **Thấy MFA pass thì tự Permit sensitive action.** Vẫn phải kiểm role, tenant, session, device và SoD.
20. **Chỉ thực thi rule ở IdP login.** Resource Server có thể nhận token/app session cũ.
21. **Cho session được nâng quyền sau step-up một lần ở mọi client.** Cần session/action/scope binding và TTL.
22. **Không xử lý named CIDR hết hiệu lực.** IP được tái phân bổ có thể bị coi là trusted.
23. **Không version/rà soát thay đổi geofence.** Một policy edit có thể mở quyền rộng mà không có grant event.
24. **Dùng GeoIP để tuyên bố data residency compliance.** Nó không chứng minh nơi lưu trữ/xử lý dữ liệu.
25. **Áp human impossible-travel policy cho workloads.** Service replicas/NAT có semantics khác.
26. **Coi region label do client tự gửi là nguồn workload trust.** Cần issuer/attestation/resource context.
27. **Không có phương án dự phòng khi PIP/GeoIP lỗi.** Hoặc fail-open không kiểm, hoặc khóa toàn bộ production không có runbook.
28. **Lưu raw GPS mọi request không cần thiết.** Tăng rủi ro privacy/insider access.
29. **Không kiểm việc đọc và xuất location logs.** Người không có authority có thể xem lịch sử địa điểm.
30. **Đếm số lần Deny như thước đo an ninh duy nhất.** False positives cao có thể phá công việc mà không ngăn attacker.
31. **Không đo residual token/session window.** “Location Deny” ở IdP chưa đủ chứng minh các API đã ngắt quyền.
32. **Không phân biệt policy decision với enforcement.** PDP báo Deny nhưng API commit action là lỗi.
33. **Không ghi clock quality và event version.** Tính tốc độ/truy nguyên sai vì timestamps hoặc ingestion trễ.
34. **Cho ngoại lệ location không thời hạn.** Exception trở thành đường truy cập tồn dư sau nhiệm vụ.
35. **Dùng travel anomaly để kết luận sai về con người.** Risk signal phục vụ quyết định bảo mật, không phải bằng chứng chắc chắn về hành vi hoặc danh tính.

## 35. Câu hỏi tự kiểm tra

**1. Location signal trong IAM là gì?**

Là bằng chứng/ngữ cảnh về nơi một kết nối, thiết bị, User hoặc workload có thể xuất phát, kèm nguồn, độ tin cậy và thời gian, dùng để hỗ trợ risk-based access.

**2. GeoIP cho biết vị trí người dùng chính xác không?**

Không. GeoIP suy từ IP được quan sát, thường đại diện egress qua proxy/VPN/NAT và có sai số.

**3. Network zone khác GPS thế nào?**

Network zone mô tả quan hệ với hạ tầng mạng; GPS mô tả vị trí thiết bị do hệ thống cảm biến/OS báo. Cả hai có trust/accuracy/permission khác nhau.

**4. Một User từ trusted office IP nhưng đã Leaver có được phép truy cập không?**

Không. Lifecycle hard deny và current entitlement được kiểm trước/độc lập với vị trí.

**5. Tại sao corporate VPN có thể làm impossible-travel alert sai?**

VPN egress có thể đặt ở quốc gia khác vị trí người dùng; chuyển egress nhanh không phải di chuyển vật lý.

**6. Vì sao impossible travel chỉ là heuristic?**

Vì đầu vào có sai số, proxy, clock skew và nhiều devices/sessions; cần correlation và xác minh bổ sung.

**7. Known location có phải trusted location không?**

Không. Known có thể chỉ là mẫu lịch sử, trong khi trusted phải có định nghĩa và nguồn được quản trị; cả hai cũng không đảm bảo endpoint sạch.

**8. Dùng IP allowlist có tự thay thế MFA không?**

Không mặc định. Network control là một lớp bổ sung, không chứng minh User hay device không bị chiếm.

**9. Location UNKNOWN nên được đánh giá thế nào?**

Theo policy và risk tier: step-up, hạn chế, deny với guard bắt buộc hoặc alternative approved path; không tự coi trusted hoặc confirmed compromised.

**10. Accuracy radius khác confidence?**

Accuracy radius mô tả độ sai số vị trí theo cơ chế nguồn; confidence mô tả độ tin cậy/ước lượng theo định nghĩa nguồn. Không đồng nhất hai đại lượng.

**11. Vì sao GPS có accuracy cao vẫn có thể không đáng tin?**

Vì device/client có thể bị chiếm hoặc mock/spoof location; nguồn phải đủ integrity và authorization.

**12. Tại sao chỉ cần một network location history có thể bị poisoning?**

Attacker đăng nhập thành công có thể làm nơi lạ được học thành quen nếu baseline học mọi event không phân biệt trusted và compromise.

**13. Location signal giúp cấp role mới cho User không?**

Không. Nó chỉ hỗ trợ điều kiện Permit/StepUp/Restrict/Deny trên entitlement đã được cấp hợp lệ.

**14. Trong Joiner, không có location history có nghĩa phải chặn hoàn toàn không?**

Không nhất thiết. Có thể dùng verified enrollment, strong MFA và warm-up policy cho User mới.

**15. Trong Mover, đổi workLocation có tự thu hồi FinanceExporter không?**

Không. Phải cập nhật role/Group/direct grants, phiên/token và policy theo JML.

**16. Trong Leaver, location exception còn hạn có được ưu tiên hơn HR status không?**

Không. Exception không lấn át lifecycle hard deny.

**17. Vì sao không thể dùng GeoIP client để chứng minh data residency?**

Vì data residency liên quan nơi dữ liệu lưu trữ/xử lý/chuyển tiếp, không chỉ nơi client login.

**18. Workload trong cloud region A có nên bị đánh giá impossible travel như Human không?**

Không mặc định. Workload nhiều instances/regions và NAT có semantics riêng; phải dùng trust, issuer, audience và deployment policy.

**19. Trusted CIDR có thể trở thành rủi ro như thế nào?**

Khi IP range đổi chủ sở hữu, cấu hình stale có thể xem mạng không thuộc công ty là trusted; cần owner review và cập nhật.

**20. Tại sao API phải re-evaluate policy dù IdP đã kiểm tại login?**

Vì session/token có thể còn sống khi User đổi network, Mover/Leaver hoặc device compromise; PEP bảo vệ action cần bám trạng thái hiện hành theo risk tier.

**21. MFA step-up có thay thế kiểm role và tenant không?**

Không. MFA tăng assurance cho danh tính/session nhưng không cấp entitlement mới hoặc bypass tenant/SoD.

**22. Tại sao không nên log GPS chính xác mọi request?**

Vì nhiều policy chỉ cần country/zone, GPS chi tiết tạo rủi ro riêng tư, an ninh và retention không cần thiết.

**23. Nếu GeoIP provider lỗi, ứng dụng nhạy cảm nên làm gì?**

Áp fail-safe đúng policy, không giả country trusted; có thể Deny, step-up hoặc đường thay thế đã phê duyệt tùy mức yêu cầu.

**24. Vì sao risk score cần calibration?**

Vì trọng số/threshold tự đặt không chứng minh có khả năng phân biệt tấn công; cần ground truth, false-positive/negative review, đánh giá drift.

**25. Khi nào một location-based Deny thực sự được xác minh?**

Khi **PEP/resource** không cho thực hiện action trong scope yêu cầu; log quyết định PDP hoặc UI cảnh báo một mình chưa đủ.

**26. Có nên tự động cấm toàn bộ VPN không?**

Không phải quy tắc chung. Corporate VPN, privacy tools và carrier egress khác nhau; đánh giá loại network, trust, User, device, action và risk.

**27. Tại sao session-bound step-up quan trọng?**

Vì challenge của một session/tenant/action không nên tự mở privilege ở các sessions khác, giảm nguy cơ replay hoặc nâng quyền không chủ ý.

**28. Chính sách location thay đổi có cần access change log không?**

Có, nếu thay allowlist/threshold hoặc risk policy ảnh hưởng quyền truy cập, cần actor/approval/version/scope và target rollout.

**29. Location signal có thể hữu ích khi device bị mất không?**

Có, giúp điều tra bất thường, nhưng không thay device trust revocation, token/session containment hoặc forensic evidence.

**30. Người dùng đi công tác hợp lệ bị block thì nên xử lý ra sao?**

Có **recovery/step-up và policy exception hẹp có phê duyệt, TTL và audit**, không mở allowlist toàn cầu hay bỏ hard guards.

## 36. Checklist thiết kế và nghiệm thu Location signal

### 36.1. Nguồn và chất lượng tín hiệu

| Hạng mục | Câu hỏi nghiệm thu |
| --- | --- |
| **Signal semantics** | Trường đang chỉ network egress, device hay declared work location? |
| **Trusted ingress** | Có bảo vệ proxy chain/X-Forwarded-For khỏi client spoofing? |
| **GeoIP metadata** | Có dataset version, country granularity, confidence và observedAt? |
| **Proxy/VPN awareness** | Có tách corporate egress, VDI, carrier, anonymizer và Unknown? |
| **Accuracy and freshness** | TTL, uncertainty radius, clock skew được xử lý thế nào? |
| **Missing data** | Unknown/not applicable có kết quả policy rõ, không tự Allow? |
| **Baseline quality** | Chỉ học từ trusted events và có xử lý confirmed compromise? |
| **Source change** | Vendor feed/CIDR ownership thay đổi có review, rollback, monitoring? |

### 36.2. Policy và enforcement

| Hạng mục | Câu hỏi nghiệm thu |
| --- | --- |
| **Subject/entitlement** | Có kiểm stable identity, JML, role, resource, tenant và SoD độc lập? |
| **Risk tiers** | Threshold/action phù hợp dữ liệu và privileged access? |
| **Decision types** | Permit, StepUp, Restrict, Deny, Unknown được định nghĩa rõ? |
| **Step-up** | Challenge có session/action binding, assurance và TTL đúng? |
| **PEP** | API có cưỡng chế policy trước side effect và trên token/session cũ? |
| **SSO integration** | IdP/RP/API trách nhiệm nào, logout/revocation boundary ra sao? |
| **Network zones** | Trusted CIDR có owner, review, expiry và change approval? |
| **Exceptions** | Bounded resource/identity, approver độc lập, endAt và thu hồi theo JML? |
| **Emergency access** | Khi VPN/IdP lỗi có recovery path riêng, không fail-open? |
| **Workloads** | Có phân biệt human GeoIP với workload issuer/region/VPC/attestation? |

### 36.3. Audit, privacy và vận hành

| Hạng mục | Câu hỏi nghiệm thu |
| --- | --- |
| **Audit provenance** | Lưu signal source/quality, decision reason, policy version và enforcement? |
| **Secret hygiene** | Không log token, cookie, password, recovery secrets? |
| **Minimization** | Không thu GPS/toạ độ nếu chỉ cần network country/zone? |
| **Retention and access** | Chỉ người được phép xem/xuất location data, có audit và lịch lưu? |
| **False positives** | Có process xử lý travel/VPN/remote worker, model calibration và user recovery? |
| **Failure modes** | PIP/GeoIP/IdP outage, cache stale, region split có test? |
| **Residual access** | Chứng minh các API bị deny sau revoke/risk escalation trong boundary? |
| **Policy change QA** | Có tests, rollback, version/approval và rollout đa PEP? |

### 36.4. Tiêu chí nghiệm thu end-to-end

~~~text
Case: Lan has FinanceExporter and requests report.export from new network

ACCEPT nếu:
  1. Trusted ingress identifies network origin and provider/version.
  2. Location is labeled NETWORK_EGRESS, not physical-person location.
  3. GeoIP quality, VPN/proxy classification and freshness are recorded.
  4. IAM identity, lifecycle, tenant, resource and role are current.
  5. Risk engine evaluates policy version for sensitive export.
  6. Step-up is required when the approved policy needs it.
  7. Step-up is bound to the right session, resource and action.
  8. API does not export data until all mandatory conditions pass.
  9. A Leaver/device-compromise event overrides prior location Permit.
 10. Stale tokens and location decisions cannot resurrect access.
 11. Audit logs contain decision provenance without unnecessary exact GPS.
 12. False-positive travel path remains usable with verified recovery.
~~~

**Không có nghĩa mọi hệ thống đều cần GPS hoặc một model AI.** Nếu các yêu cầu được đáp ứng bởi trusted gateway/network zone, IAM lifecycle, MFA và rule engine rõ ràng, đó có thể là thiết kế phù hợp hơn một cơ chế theo dõi vị trí cá nhân phức tạp.

## 37. Kết luận: sử dụng đúng vai trò của location trong IAM

Location signal có giá trị khi nó **nói rõ đang đo cái gì**. IP quốc gia, corporate network gateway, GPS device và cloud region có các ngữ nghĩa khác nhau. Hệ thống cần đánh giá **nguồn, độ chính xác, tính mới, khả năng bị thao túng, trạng thái Unknown** trước khi đưa vào policy.

Risk-based access tốt không cố chứng minh “người dùng chắc chắn đang ở tọa độ X” từ một login, mà đặt câu hỏi **dựa trên bằng chứng hiện có, User/workload này có đủ điều kiện thực hiện action cụ thể với mức rủi ro chấp nhận được không?** Đáp án phải kết hợp lifecycle/entitlement/tenant, authentication/device/session, resource sensitivity và thực thi ở PEP.

Đối với tổ chức triển khai theo Joiner–Mover–Leaver, location exception, named zone, risk baseline, policy version và session/token cũng có **vòng đời**. Chúng cần owner, giới hạn, review, thu hồi và kiểm toán, không trở thành quyền truy cập tồn dư chỉ vì một mạng từng được gọi “trusted”.

## Ghi nhớ

- **Location signal là ngữ cảnh**, không phải identity, authorization hay vị trí vật lý chắc chắn. **GeoIP biểu thị network egress ước lượng**, có thể khác xa nơi User đang ở vì VPN, proxy, NAT, mobile carrier hoặc VDI.
- Cần phân biệt **IP/GeoIP, trusted network zone, OS/GPS device location, HR workLocation và workload deployment region**. Mỗi loại có provenance, confidence, accuracy, freshness và cơ chế chống spoof riêng.
- **Impossible travel, unfamiliar location và geofencing** hữu ích để phát hiện hoặc hạn chế rủi ro, nhưng là **heuristics/controls có giới hạn**, không tự chứng minh compromise hoặc tuân thủ data residency.
- Chính sách location phải kết hợp **IAM identity, JML, RBAC/ABAC/PBAC, role, tenant, MFA/step-up, device trust, session/token và quyền tại Resource Server**; trusted country/IP không được bỏ các hard denies.
- **Joiner** cần onboarding không phụ thuộc location history; **Mover** phải thay quyền và review exceptions; **Leaver/contractor hết hạn** phải thu hồi quyền dù đang ở mạng trusted; **workload** cần issuer/attestation/region trust riêng thay vì GeoIP như người.
- **Unknown/low-confidence location** phải có xử lý theo risk tier và fail-safe, không bị coi tự động trusted hoặc confirmed malicious. Khi IdP/VPN outage, **emergency recovery** phải theo playbook và authority riêng, không permit-all.
- Quản lý **privacy, minimization, access to location logs, retention, source integrity, policy version và false-positive review** là phần của bảo mật; không thu GPS chi tiết hơn mục đích yêu cầu.
- **PDP decision chưa đủ**: phải kiểm **PEP enforcement, token/session residual access, audit và hiệu quả step-up**. Những điều này giúp location signal giảm rủi ro thực tế trong toàn bộ vòng đời danh tính IAM.
