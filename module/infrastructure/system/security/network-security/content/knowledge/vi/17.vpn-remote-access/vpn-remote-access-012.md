# Xử lý tài khoản VPN bị lộ: phát hiện, cô lập, điều tra và khôi phục truy cập từ xa

Trong chương **VPN và truy cập từ xa** thuộc module **SECURITY_NETWORK_SECURITY**, chủ đề **Xử lý tài khoản VPN bị lộ** tập trung vào cách ứng phó khi mật khẩu, phương thức xác thực, khóa, chứng chỉ hoặc phiên đăng nhập dùng để truy cập mạng từ xa có nguy cơ rơi vào tay người không được phép. Khi một tài khoản VPN bị xâm phạm, hệ quả có thể vượt xa một phiên kết nối: kẻ sử dụng trái phép có thể có đường truy cập đến dịch vụ nội bộ, tài khoản khác, hệ thống quản trị, DNS doanh nghiệp và tài nguyên cloud tùy theo chính sách đã cấp.

Một quy trình an toàn cần xử lý đồng thời **ba câu hỏi**:

1. **Quyền truy cập nào có thể đã bị lộ?** Mật khẩu, MFA, thiết bị, certificate, private key, access/refresh token, session cookie hay VPN profile?
2. **Quyền truy cập nào hiện còn hiệu lực?** Khả năng đăng nhập mới, VPN tunnel đang hoạt động, phiên ứng dụng phía sau VPN, credential đã được tái sử dụng ở hệ thống khác?
3. **Bằng chứng nào cho biết đã xảy ra điều gì?** Log IdP/MFA, VPN gateway, RADIUS, firewall, DNS, IDS/IPS, endpoint và cloud audit cần được ghép theo thời gian và danh tính.

**Đổi mật khẩu chỉ giải quyết một phần rủi ro.** Một tunnel đã thiết lập, refresh token, chứng chỉ client, khóa VPN hoặc phiên ứng dụng downstream có thể vẫn hợp lệ tùy thiết kế. Hướng dẫn này vì vậy xem việc **thu hồi quyền, chấm dứt phiên, điều tra phạm vi, khôi phục thiết bị và kiểm chứng chính sách** là các bước liên kết với nhau.

Sau bài học, bạn có thể:

- Nhận diện các kiểu lộ VPN credential và phân biệt **dấu hiệu nghi vấn** với **truy cập trái phép đã được xác nhận**.
- Thực hiện triage, ưu tiên containment, bảo quản evidence và điều phối incident response mà không làm mất đường quản trị thiết yếu.
- Chọn hành động thu hồi đúng cho **password/SSO, MFA, certificate, client key, token và VPN session** theo kiến trúc thực.
- Dựng timeline và xác định phạm vi network access từ VPN tunnel tới ứng dụng nội bộ, DNS, firewall, IDS/IPS và cloud.
- Phục hồi tài khoản bằng xác minh danh tính độc lập, MFA chống phishing, endpoint tin cậy và quyền tối thiểu.
- Kiểm chứng bằng positive/negative tests rằng **quyền cũ không còn dùng được** và **người dùng hợp lệ đã được khôi phục đúng phạm vi**.

## 1. Hiểu đúng tài khoản VPN bị lộ

**VPN (Virtual Private Network)** tạo kênh kết nối giữa client và điểm kết thúc được quản trị theo giao thức/cấu hình phù hợp. VPN bảo vệ một hoặc nhiều thuộc tính của đường truyền, nhưng **không tự bảo đảm người đang sử dụng client hay credential là người được cấp quyền**.

Một sự cố thường liên quan nhiều loại bí mật:

| Thành phần | Vai trò | Nếu bị lộ hoặc bị chiếm quyền |
| --- | --- | --- |
| **Password của tài khoản VPN/IdP** | Chứng minh yếu tố biết trong xác thực | Có thể hỗ trợ đăng nhập mới hoặc thử đăng nhập ở dịch vụ dùng chung mật khẩu |
| **MFA authenticator / mã phục hồi / seed TOTP** | Bổ sung yếu tố xác thực | Có thể vô hiệu hóa lợi ích MFA nếu yếu tố thứ hai cũng đã bị chiếm |
| **MFA approval session** | Phê duyệt hoặc hoàn tất một lần xác thực | Có thể bị lạm dụng qua phishing, thao túng người dùng hoặc MFA fatigue tùy cơ chế |
| **Client certificate và private key** | Xác thực client hoặc thiết bị, đôi khi kết hợp user identity | Có thể cho thiết bị không được phép thiết lập tunnel nếu các điều kiện khác cũng được đáp ứng |
| **VPN access token / refresh token** | Duy trì hoặc cấp lại quyền truy cập tùy triển khai | Có thể còn dùng được sau khi mật khẩu đã đổi nếu không bị thu hồi |
| **Session cookie / VPN portal session** | Gắn trạng thái một phiên xác thực | Có thể cho tiếp tục truy cập tới khi phiên hết hạn hoặc bị invalidated |
| **Device enrollment / posture identity** | Xác minh thiết bị đáp ứng yêu cầu truy cập | Thiết bị giả mạo/đã chiếm có thể được coi là thiết bị tin cậy |
| **VPN profile, peer key hoặc pre-shared key** | Cấu hình và bí mật kết nối của giao thức | Có thể tác động tới một client hoặc nhiều peer tùy cách cấp phát khóa |
| **Quyền trong nhóm truy cập** | Xác định tài nguyên có thể tới sau khi xác thực | Nếu cấp quá rộng, ảnh hưởng của một tài khoản bị lộ tăng lên đáng kể |

**Lộ bí mật** và **có phiên truy cập trái phép** là hai sự kiện khác nhau. Chẳng hạn, một mật khẩu xuất hiện trong kho lưu trữ không được phép truy cập là sự cố cần xử lý dù chưa thấy đăng nhập lạ; ngược lại, một session bị đánh cắp có thể tồn tại mà không có dấu hiệu password đã bị biết.

### 1.1. Bốn mức tình huống để triage

| Tình huống | Ví dụ | Cần ưu tiên điều gì |
| --- | --- | --- |
| **Phơi lộ có khả năng, chưa có dấu vết sử dụng** | Người dùng gửi nhầm mật khẩu vào kênh chat hoặc repository | Thu hồi/đổi credential, kiểm tra log và nơi dữ liệu đã lan tới |
| **Nghi ngờ đang bị sử dụng trái phép** | Đăng nhập VPN lúc bất thường, MFA prompt người dùng không khởi tạo | Containment theo mức rủi ro, xác minh qua kênh tin cậy, giữ evidence |
| **Đã xác nhận session/tài nguyên bị sử dụng trái phép** | Log xác nhận đăng nhập ngoài ý muốn và truy cập dịch vụ nội bộ | Chấm dứt quyền truy cập, điều tra lateral movement, bảo vệ tài sản liên quan |
| **Thiết bị và nhiều yếu tố xác thực có thể bị chiếm** | EDR báo malware trên máy đang giữ certificate và VPN token | Cô lập endpoint, thu hồi credential/key/session, điều tra phạm vi rộng hơn |

Mức độ ưu tiên phụ thuộc **giá trị tài sản, quyền tài khoản, evidence, bề mặt mạng có thể truy cập và thời gian đang diễn ra**. Không có một nhãn “critical” cố định phù hợp cho mọi tổ chức.

## 2. Mô hình đường truy cập và các điểm có thể phải thu hồi

Một kiến trúc truy cập từ xa điển hình:

~~~mermaid
flowchart LR
    U["Người dùng / thiết bị từ xa"] --> C["VPN client / Portal"]
    C --> G["VPN gateway / Concentrator"]
    G --> F["Firewall / Segmentation"]
    F --> A["Ứng dụng nội bộ"]
    F --> D["DNS / Directory / Management"]
    G --> I["IdP / MFA / RADIUS / PKI"]
    C --> E["Endpoint security / MDM"]
    G -. "Session, IP pool, auth events" .-> S["SIEM / SOC"]
    I -. "Sign-in, MFA, revoke audit" .-> S
    F -. "Flow / deny / IPS / DNS" .-> S
    E -. "Device posture / EDR" .-> S
~~~

Sơ đồ chỉ minh họa các **điểm kiểm soát**. Trong thực tế, VPN gateway có thể xác thực cục bộ, qua RADIUS/LDAP, SAML/OIDC với IdP hoặc bằng chứng chỉ thiết bị; một số mô hình dùng ZTNA/SASE với quyền theo ứng dụng thay vì mở kết nối tới cả subnet.

### 2.1. Phân biệt control plane và data plane

- **Control plane / identity:** tài khoản, thuộc tính IdP, nhóm truy cập, MFA registration, chứng chỉ, khóa VPN, policy và bản ghi cấp quyền.
- **Session state / enforcement:** tunnel VPN đang tồn tại, session cookie, refresh token, gateway connection table, firewall connection state và phiên ứng dụng.
- **Data plane / activity:** packet tới subnet, DNS query, kết nối RDP/SSH/SMB, truy cập web nội bộ, API, database hoặc cloud service.

Vì các lớp này có thể **cache trạng thái riêng**, khóa một tài khoản trong directory chưa chắc tự động ngắt tunnel đang hoạt động. Tương tự, đóng tunnel VPN không nhất thiết vô hiệu hóa một **session ứng dụng** đã phát hành token độc lập.

### 2.2. Xác định phạm vi tài khoản trước khi hành động

Trong bước triage, cần biết:

1. VPN user ID có ánh xạ một-một với **IdP account** nào không?
2. Tài khoản là **người dùng cá nhân, quản trị viên, nhà thầu hay tài khoản dịch vụ**?
3. Quyền truy cập áp dụng theo **user, device, certificate, client IP, group hoặc role**?
4. Có những **gateway, region, VPN profiles, cloud tenants hoặc VPN concentrators** nào có thể chấp nhận credential?
5. Sau khi kết nối, tài khoản có thể tới những **subnet và application** nào; có thể dùng **split tunnel hay full tunnel**?
6. Có ứng dụng nào phát hành session riêng hoặc credential mới dựa trên phiên VPN đó?

Không thể chọn hành động thu hồi chính xác nếu chưa biết **điểm nào thực sự kiểm tra quyền**.

## 3. Dấu hiệu nhận biết và xác thực sự cố

### 3.1. Những tín hiệu đáng quan tâm

| Tín hiệu | Nguồn | Ý nghĩa có thể có |
| --- | --- | --- |
| Đăng nhập VPN từ IP/ASN không quen thuộc | VPN gateway, IdP sign-in logs | Có thể là truy cập lạ; cần phân biệt VPN thương mại, mobile, roaming hoặc ISP mới |
| Đăng nhập ở giờ khác thường so với hoạt động công việc | VPN/IdP, lịch vận hành | Tăng mức cần điều tra, không tự chứng minh credential bị đánh cắp |
| Nhiều MFA prompts bị người dùng từ chối | IdP/MFA logs, phản ánh của người dùng | Có thể là MFA fatigue hoặc đăng nhập nhầm, cần liên hệ xác thực |
| MFA method mới hoặc recovery codes được tạo | IdP audit log | Thay đổi yếu tố xác thực cần xác nhận quyền sở hữu |
| Phiên VPN đồng thời hoặc chuyển địa điểm bất thường | VPN sessions, device inventory | Có thể là hai thiết bị hợp lệ, NAT/proxy hoặc truy cập trái phép |
| Endpoint báo malware hoặc trích xuất credential | EDR/AV, MDM | Cần điều tra cả token, cookie, certificate và private key |
| Truy cập tài nguyên không nằm trong hành vi thông thường | Firewall/IDS/IPS, app logs | Có thể là sử dụng quyền không phù hợp, scan hoặc automation hợp lệ |
| VPN certificate/peer key dùng trên thiết bị lạ | Gateway/PKI/MDM, device posture | Có nguy cơ bí mật thiết bị bị sao chép |
| Credential bị phát tán ngoài nơi lưu hợp lệ | DLP, incident report, kho lưu trữ được kiểm soát | Có khả năng phơi lộ dù chưa có session bất thường |

Các dấu hiệu như **impossible travel** hoặc “thiết bị lạ” có thể tạo false positive do NAT, proxy, IP địa lý không chính xác hoặc người dùng đang di chuyển. Kết luận cần đối chiếu **ID phiên, cách xác thực, endpoint/device, timestamp và bối cảnh công việc**.

### 3.2. Xác minh với chủ tài khoản qua kênh độc lập

Nếu một email nói “tài khoản VPN của bạn bị lộ, hãy nhấn link để đổi mật khẩu”, chính email đó có thể là một phần của phishing. Khi liên hệ:

- Dùng **số điện thoại hoặc kênh hỗ trợ đã được xác minh từ trước**, không chỉ thông tin liên hệ trong email đáng nghi.
- Xác nhận người dùng có chủ động đăng nhập, đổi thiết bị, thay MFA hay truy cập trong khoảng thời gian cần điều tra không.
- Không yêu cầu người dùng đọc mật khẩu, mã OTP, backup code hoặc seed TOTP cho helpdesk.
- Không gửi credential mới dưới dạng văn bản rõ qua email/chat không được phê duyệt.
- Nếu tài khoản đã có nguy cơ bị takeover, **không coi sự trả lời từ chính tài khoản đó là bằng chứng danh tính duy nhất**.

### 3.3. Phân loại ở mức có thể chứng minh

Ví dụ:

> “Có ba lần đăng nhập thành công tới VPN account A trong khoảng 02:10–02:30 UTC từ hai nguồn mạng; người dùng xác nhận không chủ động tạo phiên thứ hai. Đã ghi nhận session ID tương ứng trên gateway, đang xác minh thiết bị và phạm vi traffic. **Trạng thái:** suspected unauthorized access; chưa khẳng định có truy cập trái phép dữ liệu.”

Sự tách biệt giữa **facts – hypotheses – unknowns** giúp SOC không suy luận quá mức và không bỏ qua các lỗ hổng cần xử lý.

## 4. Quy trình ứng phó theo thứ tự ưu tiên

Khi có tín hiệu nguy cơ đang diễn ra, cần phối hợp **containment đủ nhanh** với **thu thập bằng chứng có kiểm soát**. Không nên trì hoãn chặn quyền rõ ràng nguy hiểm chỉ để thu đủ log, nhưng cũng tránh xóa dữ liệu cần cho điều tra mà không có lý do.

~~~mermaid
flowchart TD
    A["Nhận alert hoặc báo cáo lộ VPN credential"] --> B["Tạo case, xác minh account và bối cảnh"]
    B --> C{"Có rủi ro truy cập trái phép đang diễn ra?"}
    C -- "Cao / đã xác nhận" --> D["Ưu tiên cô lập/thu hồi theo policy IR"]
    C -- "Chưa rõ" --> E["Kiểm tra nhanh sign-in/session/MFA và xác minh độc lập"]
    E --> D
    D --> F["Chặn đăng nhập mới + ngắt session + thu hồi bí mật liên quan"]
    F --> G["Bảo quản logs, timeline, xác định phạm vi"]
    G --> H{"Thiết bị hoặc tài khoản khác có thể đã bị chiếm?"}
    H -- "Có / chưa rõ" --> I["Mở rộng điều tra endpoint/identity và tài sản liên quan"]
    H -- "Không có bằng chứng" --> J["Khôi phục quyền có kiểm soát"]
    I --> J
    J --> K["Positive/negative tests, theo dõi và post-incident review"]
~~~

Sơ đồ là **quy trình khái niệm**, không phải hành động tự động có thể áp dụng nguyên trạng cho mọi doanh nghiệp. Tài khoản quản trị khẩn cấp, hệ thống điều khiển quan trọng hoặc VPN phục vụ vận hành liên tục có thể cần cơ chế **break-glass và xác nhận người chịu trách nhiệm** để tránh gây outage không kiểm soát.

### 4.1. Thời điểm phát hiện: lập hồ sơ tối thiểu

Ghi ngay:

- **Case ID**, thời điểm phát hiện, nguồn cảnh báo và người xử lý.
- **User ID / account ID chuẩn**, không chỉ display name.
- **VPN gateway/profile**, loại auth, MFA, thiết bị và role hiện có.
- **Tài khoản có session active không**, IP pool/assigned tunnel IP, session ID.
- **Bằng chứng phơi lộ** nếu có, đường dẫn artifact được quản lý quyền và không sao chép bí mật bừa bãi.
- **Tài sản/luồng nghiệp vụ** bị ảnh hưởng nếu khóa tài khoản ngay.

Nếu chưa thể lấy đủ một trường, ghi **unknown** và nguồn cần kiểm chứng; không bịa giá trị để điền mẫu.

### 4.2. Phân vai

| Vai trò | Trách nhiệm trong case |
| --- | --- |
| **Incident commander / SOC lead** | Chỉ huy ứng phó, ưu tiên containment, điều phối và lưu quyết định |
| **IAM/IdP team** | Khóa đăng nhập, reset credential, thu hồi sessions/tokens, rà soát MFA và role |
| **Network/VPN operations** | Liệt kê/ngắt tunnel, áp tạm policy gateway, kiểm tra pool IP, route và session logs |
| **Endpoint/EDR team** | Kiểm tra malware, device posture, chứng chỉ/private key và cách ly máy khi cần |
| **Application/service owner** | Xác định resource access và thu hồi session ứng dụng nếu có nguy cơ |
| **Helpdesk / communication owner** | Xác minh người dùng qua kênh độc lập, hướng dẫn phục hồi và cập nhật ảnh hưởng |
| **Risk/legal/privacy khi phù hợp** | Xử lý nghĩa vụ ghi nhận, bảo mật thông tin và thông báo theo quy định áp dụng |

**Một người chịu trách nhiệm chính** cần duy trì timeline và trạng thái các lệnh thu hồi ở các hệ thống khác nhau. Nếu mỗi nhóm chỉ báo “đã đổi mật khẩu” mà không kiểm tra session, rủi ro có thể vẫn tồn tại.

## 5. Containment: chặn đăng nhập mới và cắt quyền còn hoạt động

Hành động cần được lựa chọn từ **kiến trúc xác thực thật**, không mặc định một nút “Disable user” giải quyết tất cả.

### 5.1. Ma trận thu hồi theo loại credential

| Loại nguy cơ | Hành động containment cần xem xét | Bằng chứng đã hiệu lực |
| --- | --- | --- |
| **Mật khẩu local VPN** | Khóa hoặc disable local account; đặt lại password theo quy trình; kiểm tra mọi gateway dùng cùng account | Gateway auth log từ chối đăng nhập mới; trạng thái account |
| **Tài khoản IdP/SSO** | Disable/sign-in block, reset password; thu hồi IdP sessions/refresh tokens khi có khả năng; rà soát federation và cached state | IdP audit + VPN gateway không cấp phiên mới |
| **VPN tunnel hiện có** | Chủ động terminate/disconnect đúng session tại từng gateway/region, vô hiệu hóa reconnect | Active sessions không còn; gateway log có disconnect/reject |
| **Access/refresh token hoặc browser cookie** | Revoke hoặc invalidate theo cơ chế IdP/gateway/app; giảm TTL và xử lý trường hợp không thể thu hồi tức thì | Thử sử dụng lại trong môi trường kiểm thử được cấp quyền bị từ chối; audit token revoke |
| **Client certificate/private key** | Revoke certificate, cập nhật CRL/OCSP hoặc trust/allowlist theo công nghệ; cấp lại keypair mới từ thiết bị đáng tin | Gateway từ chối certificate cũ sau khi chính sách được áp, log PKI/gateway |
| **WireGuard peer private key** | Xóa/vô hiệu hóa **public key của peer bị lộ** khỏi gateway hoặc ACL tương ứng; phát hành keypair mới | Gateway không chấp nhận peer cũ; peer mới được quản lý hoạt động |
| **IPsec/IKE pre-shared key** | Thay PSK theo đúng phạm vi peer; nếu khóa dùng chung phải lập kế hoạch luân chuyển cho các peer liên quan | Cấu hình mới hiệu lực và peer sử dụng khóa cũ không còn xác thực |
| **MFA factor/seed/recovery code** | Vô hiệu hóa factor cũ, reset enrollment và mã phục hồi; đăng ký lại sau xác minh danh tính mạnh | IdP audit, factor mới; không còn đăng nhập bằng factor cũ |
| **Endpoint có nguy cơ bị chiếm** | Isolate bằng EDR/MDM theo policy, triage malware, thu hồi device credential | EDR/MDM posture, key/cert revocation và đánh giá thiết bị sạch |
| **Phiên ứng dụng downstream** | Thu hồi app token/session hoặc quyền đặc biệt nếu đã có dấu hiệu lạm dụng | Application audit và kiểm thử quyền sau thu hồi |

**Quy tắc quan trọng:** thu hồi certificate hoặc đổi mật khẩu có thể chỉ ngăn **kết nối mới**; tunnel hoặc phiên đang mở có thể cần **chủ động ngắt**. Hành vi chính xác phụ thuộc VPN protocol, gateway, thời gian phiên và cách kiểm tra trạng thái thu hồi.

### 5.2. Chặn phiên đang hoạt động không giống chặn traffic IP

VPN gateway thường cấp một **tunnel IP** từ pool, chẳng hạn **10.90.40.25**, cho user. IP pool có thể tái sử dụng khi session kết thúc. Một firewall rule chặn IP này có thể:

- Chỉ chặn được một phần traffic, trong khi gateway vẫn giữ session hoạt động.
- Không chặn được một session mới được cấp **IP khác**.
- Ảnh hưởng người dùng khác khi IP được cấp lại sau này.

Vì vậy, biện pháp chính thường là **thu hồi danh tính/session ở đúng enforcement point**, kết hợp network blocking có scope và thời hạn nếu phải giảm rủi ro tức thời. Trong log, hãy ghép **user + session ID + assigned VPN IP + khoảng thời gian** để tránh quy kết sai.

### 5.3. MFA cũng có thể cần thu hồi

Nếu nghi người dùng đã phê duyệt MFA push lạ, bị phishing thu mã hoặc seed TOTP, **chỉ đổi mật khẩu có thể chưa đủ**. Cần:

1. Rà soát **MFA methods đang đăng ký**, lần thêm/sửa gần nhất, thiết bị và thời điểm.
2. Thu hồi những factor có nguy cơ, **recovery codes và remembered/trusted device states** khi hệ thống hỗ trợ.
3. Xác minh danh tính người dùng qua quy trình độc lập trước khi cấp lại yếu tố.
4. Ưu tiên **phương thức chống phishing** như FIDO2/WebAuthn/passkey hoặc certificate-bound mechanism phù hợp với IdP và thiết bị.
5. Giới hạn quyền tự đăng ký factor mới nếu chính account đang nghi bị chiếm cho tới khi kết thúc xác minh.

**MFA push thành công không tự chứng minh người dùng thực sự muốn đăng nhập.** Phân tích yếu tố xác thực phải dựa trên ngữ cảnh yêu cầu và xác minh với chủ tài khoản.

### 5.4. Tránh phá đường quản trị thiết yếu

Nếu VPN là đường duy nhất tới hệ thống đang dùng để điều tra, việc ngắt **tất cả tunnel hoặc toàn bộ IdP** có thể làm mất khả năng ứng phó. Trước hành động có phạm vi lớn, xác nhận:

- Có **out-of-band management / break-glass** hoặc phiên ứng cứu khác đã được phê duyệt?
- Có thể giới hạn riêng **tài khoản/thiết bị/session** thay vì tắt VPN cho cả tổ chức?
- Có dự phòng cho các **dịch vụ sản xuất hoặc vận hành 24/7** bị ảnh hưởng?
- Ai được phê duyệt **risk acceptance, thay đổi firewall và rollback**?

Việc ưu tiên giảm rủi ro phải cân đối với tính sẵn sàng và an toàn con người nếu hệ thống liên quan đến vận hành quan trọng.

## 6. Bảo quản bằng chứng trước và sau containment

Một case VPN bị lộ cần trả lời **ai truy cập, từ đâu, khi nào, bằng cách nào, đã đi tới đâu và có thực hiện thay đổi nào không**. Thay đổi credential hoặc ngắt tunnel có thể khiến session biến mất khỏi màn hình quản trị, nên cần **export log và snapshot với phạm vi hợp lý**, đồng thời không trì hoãn containment khi có đe dọa hiện hữu.

### 6.1. Danh mục evidence

| Nguồn | Trường hữu ích | Câu hỏi giúp trả lời |
| --- | --- | --- |
| **IdP / authentication logs** | Account ID, auth result, method, MFA result, device ID, source IP, event ID | Có đăng nhập hợp lệ hay đáng nghi? MFA nào được dùng? |
| **VPN gateway** | Gateway ID, session ID, connect/disconnect, client public IP, assigned VPN IP, profile, tunnel type | Tài khoản có phiên nào, vào/ra lúc nào và được cấp IP gì? |
| **RADIUS/LDAP/PKI** | Request ID, certificate serial/thumbprint, group/role, failure reason | Danh tính/credential nào được xác thực? |
| **Firewall/session/NAT** | Timestamp, ingress VPN zone, original/translated IP, destination, port, action, policy ID | Phiên đã tới subnet/dịch vụ nào, bị allow hay deny? |
| **DNS resolver** | QNAME, resolver, VPN session/assigned IP mapping, time | Thiết bị đã hỏi những domain nào? |
| **IDS/IPS/NDR** | Alert/rule ID, flow tuple, detection vs prevention, evidence pointer | Có hoạt động đáng ngờ trong tunnel hoặc sau gateway không? |
| **Endpoint EDR/MDM** | Device identity, malware finding, security posture, process/network events | Client có bị chiếm hoặc token/key có thể đã bị lấy không? |
| **App/Cloud audit** | Principal, session, API action, resource ID, change details | Có đăng nhập, tải dữ liệu hoặc thay đổi ở tài nguyên phía sau VPN không? |
| **IAM change history** | Password reset, MFA enrollment, role/group changes, token/cert revoke | Đối tượng có tìm cách duy trì quyền hoặc nâng đặc quyền không? |

### 6.2. Ghép danh tính qua NAT và VPN IP pool

Ví dụ:

~~~text
Thời gian (UTC)   2026-11-28T02:14:03Z đến 02:42:19Z
Account ID        u-1042
Client public IP  198.51.100.27
Gateway           VPN-GW-A
VPN session ID    sess-9821
Assigned VPN IP   10.90.40.25

Firewall:
02:20:10Z  src 10.90.40.25 -> dst 10.20.30.15:443 ALLOW
02:21:06Z  src 10.90.40.25 -> dst 10.20.99.10:3389 DENY
~~~

Đây là **dữ liệu minh họa**; **198.51.100.0/24** là dải địa chỉ dành cho tài liệu. Nếu **10.90.40.25** được cấp cho người khác sau 02:42:19Z, không được gán log lúc 03:00Z cho account u-1042 chỉ vì trùng IP. Phải dùng **mapping IP–session–gateway–thời gian**, và xét log NAT/định tuyến phù hợp.

### 6.3. Thời gian và giới hạn suy luận

- Sử dụng timestamp **UTC/offset rõ ràng**, xác minh NTP và độ lệch đồng hồ.
- Đối chiếu **session connect/disconnect** với thời gian đăng nhập IdP và lúc firewall tạo flow; có thể có độ trễ ghi log.
- Một **successful VPN auth** chứng minh phiên xác thực được chấp nhận, không tự chứng minh tài nguyên nhạy cảm đã bị đọc.
- Một **firewall allow** chứng minh policy cho phép flow ở điểm kiểm soát đó, không tự chứng minh ứng dụng đã xử lý thành công request.
- **Không có log** chưa chứng minh không có hoạt động nếu sampling, retention, route khác, mã hóa hoặc sensor coverage chưa đủ.
- Một IP địa lý bất thường không phải bằng chứng xác thực cá nhân; cần xác minh nguồn kết nối và thiết bị.

### 6.4. Bảo mật và tính toàn vẹn của bằng chứng

VPN logs có thể chứa IP cá nhân, username, device identifier, hostname hoặc token. Cần:

1. Thu thập tối thiểu đủ để trả lời câu hỏi điều tra.
2. Lưu bản gốc theo **case ID**, người thu thập, nguồn, thời gian và quyền truy cập.
3. Khi thích hợp, tính **SHA-256 hash** cho file export sau khi thu thập; phân tích trên bản sao.
4. Che thông tin nhạy cảm trong báo cáo/ảnh chụp; không xuất raw token, cookie, seed MFA hoặc private key vào ticket.
5. Áp retention và quy định chia sẻ theo chính sách tổ chức.

Hash chỉ giúp phát hiện **thay đổi byte sau khi hash**, không chứng minh nguồn log ban đầu đầy đủ hoặc hệ thống không bị tấn công.

## 7. Tái dựng timeline và xác định phạm vi truy cập trái phép

### 7.1. Một timeline phải thể hiện nhiều lớp

~~~text
02:05  IdP: MFA prompt từ nguồn lạ, không được chủ tài khoản xác nhận
02:14  IdP/VPN: xác thực thành công, session sess-9821
02:14  VPN: cấp địa chỉ 10.90.40.25 và route profile
02:20  Firewall: 10.90.40.25 truy cập app-subnet TCP/443
02:21  Firewall: cố kết nối management-subnet TCP/3389 bị deny
02:30  Application: có một API request, còn đang xác minh actor/outcome
02:39  SOC: ghi nhận nghi vấn và tạo incident
02:42  VPN: terminate session sess-9821
02:43  IdP: disable sign-in, revoke sessions/tokens theo khả năng
02:46  Gateway: xác nhận session không còn, kiểm tra login mới bị từ chối
~~~

Mọi dòng trên chỉ là **case giả định**. Cần phân biệt **event đã được xác nhận** với **giả thuyết**: API request có tồn tại không có nghĩa nội dung bị lấy; firewall deny không có nghĩa một kỹ thuật truy cập đã thành công.

### 7.2. Tìm phạm vi từ tài khoản tới tài sản

Một quy trình scoping hợp lý:

1. **User identity:** quyền và nhóm VPN, thay đổi MFA/role, credential dùng chung với dịch vụ khác, thời gian phiên.
2. **Device identity:** máy nào đã xác thực, certificate/key nào, có dấu hiệu malware hoặc device posture bất thường không.
3. **Network reachability:** VPN profile cho phép các prefix nào, split/full tunnel, policy firewall và IPv4/IPv6.
4. **Session activity:** những 5-tuple nào thực tế xuất hiện, bao nhiêu bytes/flows, time window và action cho phép/từ chối.
5. **Application activity:** endpoint, tài khoản ứng dụng, audit action, thao tác đọc/sửa/xuất dữ liệu; đối chiếu request ID với VPN flow.
6. **Privilege escalation/persistence:** thay đổi group, tạo tài khoản, cấp token/key mới, remote administration, scheduled job hoặc policy change liên quan.
7. **Other accounts/tokens:** có dấu hiệu cùng thiết bị đã lấy credential của đồng nghiệp hoặc tài khoản dịch vụ không.

Scoping cần dựa trên các nguồn được cấp quyền và **không tạo thử tấn công** vào hệ thống sản xuất. Khi phát hiện dấu hiệu compromise lan rộng, mở case/điều phối Incident Response theo quy trình tổ chức.

### 7.3. Ý nghĩa của split tunnel, full tunnel và DNS

Một VPN full tunnel có thể chuyển Internet traffic qua gateway doanh nghiệp; một cấu hình split tunnel chỉ chuyển **prefix được chọn**. Nhưng cần lưu ý:

- Log của VPN gateway **không mặc định bao phủ** mọi traffic Internet của thiết bị nếu có split tunnel.
- DNS có thể dùng resolver nội bộ, DoH, cache hoặc chế độ split DNS; thiếu DNS query không chứng minh client không truy cập domain.
- Một policy IPv4 đúng **không bảo đảm IPv6** cũng đi qua tunnel. Cần xác minh **0.0.0.0/0**, **::/0**, các tuyến cụ thể, DNS và trạng thái VPN client.
- Route trong bảng điều khiển chỉ cho biết đường dự kiến; cần flow/session evidence để xác nhận forwarding thực tế.
- Quyền truy cập mà VPN cấp có thể bị giới hạn thêm bởi **microsegmentation, IAM role, server firewall và ứng dụng**.

Không suy ra một tài khoản bị lộ đã truy cập **mọi mạng có route**; cần tách **khả năng kết nối** với **hoạt động đã quan sát**.

## 8. Các loại VPN và điểm thu hồi đặc thù

| Kiểu triển khai | Thành phần phải xác minh | Điểm dễ bị bỏ sót |
| --- | --- | --- |
| **SSL/TLS VPN client-based** | Tài khoản/SSO, gateway session, client certificate nếu dùng, tunnel IP | Đổi password nhưng tunnel hoặc browser portal session vẫn sống |
| **Clientless VPN / browser portal** | IdP login, cookie/session portal, app tokens phía sau | Thu hồi tunnel không liên quan nếu phiên web vẫn hợp lệ |
| **IPsec/IKEv2 remote access** | IKE authentication, EAP/cert, IKE SA/CHILD SA, peer identity | Phải xóa SA/session phù hợp; certificate/PSK cũ có thể vẫn tồn tại |
| **WireGuard-based access** | Public key của peer trên server, private key thiết bị, AllowedIPs, IP/ACL | Không có khái niệm “đăng xuất SSO” mặc định nếu tích hợp chưa được thiết kế; phải thu hồi peer key/authorization |
| **ZTNA / identity-aware proxy** | IdP sessions, device posture, app-specific grants, connector/proxy policy | Chặn truy cập một ứng dụng không đồng nghĩa toàn bộ grant khác đã bị revoke |
| **VPN site-to-site dùng tài khoản hoặc shared secret** | Peer identity/PSK/cert, routing policy, các hệ thống dùng chung bí mật | Rotation thiếu kế hoạch có thể làm nhiều site ngừng kết nối |

**Tên giao thức không tự cho biết quy trình revoke cụ thể**. Ví dụ, hai sản phẩm cùng dùng IPsec/IKEv2 nhưng cách gọi lệnh xóa SA, kiểm tra CRL/OCSP và gắn user role có thể khác. Khi thao tác production, sử dụng runbook đã kiểm thử và tài liệu thiết bị ở đúng phiên bản.

### 8.1. Certificate revocation không phải phép màu

Nếu private key của certificate bị lộ:

- Thu hồi certificate cũ ở **PKI/CA** và cập nhật trạng thái xác minh mà VPN gateway thực sự sử dụng (CRL, OCSP hoặc allowlist/trust policy theo triển khai).
- Kiểm tra thời gian **cache revocation status** và hành vi gateway khi không truy cập được dịch vụ kiểm tra.
- Chủ động terminate những session hiện dùng certificate nếu cần; không đợi kỳ kiểm tra tiếp theo khi rủi ro đang cao.
- Cấp **certificate/keypair mới** trên thiết bị đã được xác minh an toàn; **không sao chép lại private key cũ**.

Nếu không thể thu hồi tức thời vì thiết bị không hỗ trợ kiểm tra trạng thái, có thể cần rule cấp quyền tạm hoặc xóa trust/peer cụ thể; phải nêu **rủi ro còn lại** cho tới khi việc thu hồi được kiểm chứng.

### 8.2. WireGuard: key identity là điểm trọng tâm

Trong triển khai WireGuard thuần túy, peer được nhận diện bằng **public key**, và khả năng truy cập còn chịu **AllowedIPs và firewall/route**. Khi private key thiết bị bị lộ, không thể chỉ đổi password IdP nếu hệ thống không có tích hợp IdP điều khiển peer admission.

Phải **vô hiệu hóa public key tương ứng tại gateway/control plane**, phát hành một keypair mới, cập nhật peer configuration và kiểm thử peer cũ không còn liên lạc được trong phạm vi đã định. Nếu nền tảng quản lý WireGuard qua controller, cần xác minh policy đã được áp tới **mọi node**.

### 8.3. IPsec PSK dùng chung có blast radius lớn

Một pre-shared key dùng chung giữa nhiều peer tạo rủi ro vượt phạm vi một người dùng. Khi PSK có khả năng bị lộ, phải inventory **toàn bộ peer cùng dùng key**, lập kế hoạch luân chuyển đồng bộ, thu hồi state cũ và xác minh liên kết hợp lệ. Tránh thay key tùy ý trên một đầu khi chưa có phương án dự phòng vì có thể làm mất kết nối mạng quan trọng.

## 9. Khôi phục tài khoản và thiết bị an toàn

Chỉ nên mở lại quyền truy cập khi **nguồn gây lộ** đã được xử lý ở mức chấp nhận được. Nếu malware vẫn chạy trên endpoint và tiếp tục lấy token, cấp mật khẩu mới sẽ tạo vòng lặp compromise.

### 9.1. Các điều kiện trước khi re-enable

| Điều kiện | Bằng chứng mong đợi |
| --- | --- |
| Xác minh **người sở hữu tài khoản** qua kênh độc lập | Helpdesk/IAM verification record không dùng riêng session đáng nghi |
| Mật khẩu hoặc credential cũ không còn hợp lệ | Auth policy, audit và negative test được cấp quyền |
| Phiên/tunnel cũ đã bị terminate hoặc phạm vi chưa thể revoke được xử lý | VPN gateway active session list, disconnect log, rủi ro còn lại |
| IdP tokens/cookies và MFA yếu tố bị lộ đã xử lý | Revocation audit, MFA enrollment history, trusted device reset phù hợp |
| Client certificate/key cũ được revoke nếu liên quan | PKI/peer inventory, gateway enforcement test |
| Thiết bị đã được đánh giá tin cậy | EDR/MDM posture, investigation result, reimage/re-enroll khi cần |
| Nhóm/quyền được rà soát | Approved VPN role, subnet/app access và admin privilege |
| Tài sản downstream đã đánh giá | App/session audit, cloud/IAM changes, pending containment tasks |
| Cảnh báo tăng cường đã sẵn sàng | SIEM detection, SOC owner, time window theo dõi |

### 9.2. Quy trình khôi phục có kiểm soát

1. **Đảm bảo identity:** xác minh người dùng thật và nhu cầu công việc hiện tại.
2. **Endpoint:** điều tra, cách ly hoặc khôi phục máy có nguy cơ; re-enroll device identity và khóa trên thiết bị đáng tin nếu cần.
3. **Credential:** reset hoặc cấp mới bí mật bị lộ, không tái sử dụng password/key; xem xét credential reuse ở những hệ thống khác.
4. **MFA:** đăng ký lại yếu tố đã bị ảnh hưởng; chọn phương thức chống phishing phù hợp với thiết bị và policy.
5. **Access policy:** cấp quyền VPN **tối thiểu** tới các ứng dụng cần thiết; tránh tạm cấp nhóm quản trị rộng để “kiểm tra cho nhanh”.
6. **New session:** người dùng đăng nhập từ thiết bị đã xác minh; theo dõi gateway session ID, tunnel IP, policy và kết nối hợp lệ.
7. **Observe:** tăng giám sát đối với tài khoản, thiết bị, tài sản liên quan và dấu hiệu đăng nhập lại bất thường.
8. **Close/handoff:** lưu incident record, thay đổi control, những việc còn mở và điều kiện đóng case.

Nếu sự cố cho thấy **truy cập trái phép ứng dụng hoặc dữ liệu**, quy trình phục hồi VPN **không thay thế** điều tra dữ liệu, nghĩa vụ thông báo hoặc xử lý tài sản downstream.

### 9.3. Vì sao nên ưu tiên MFA chống phishing?

MFA dạng SMS hoặc mã OTP có thể bị đánh cắp qua phishing hoặc thao túng người dùng; push approval có thể bị lạm dụng khi xuất hiện nhiều prompt. **FIDO2/WebAuthn/passkey hoặc credential được ràng buộc mật mã đúng với dịch vụ** có thể giảm nguy cơ phishing nhất định, tùy tích hợp IdP/gateway. Tuy nhiên, vẫn cần bảo vệ endpoint, thiết bị xác thực và quy trình account recovery.

## 10. Thiết kế network controls để giảm blast radius khi credential bị lộ

Không nên xây dựng mô hình bảo mật dựa trên giả định **mọi người đăng nhập VPN đều đáng tin với toàn bộ mạng nội bộ**.

~~~mermaid
flowchart LR
    U["Remote user / managed device"] --> V["VPN / ZTNA entry"]
    V --> I["Identity + MFA + posture"]
    V --> F["Firewall / policy segmentation"]
    F -->|Role: Support| A["Support applications"]
    F -->|Role: Engineer| B["Approved engineering services"]
    F -. "Default deny" .-> D["Database / management zone"]
    F -. "Telemetry" .-> S["SOC / SIEM / IDS"]
    I -. "Auth + risk signals" .-> S
~~~

### 10.1. Những biện pháp giảm tác động

| Control | Mục tiêu | Evidence cần kiểm tra |
| --- | --- | --- |
| **Least privilege VPN group/role** | Chỉ cấp subnet/app người dùng thực sự cần | Group membership và policy ID |
| **MFA + device posture** | Giảm nguy cơ credential đơn lẻ bị dùng từ thiết bị lạ | Auth logs, device compliance result |
| **Segmentation / microsegmentation** | Ngăn lateral movement từ VPN tới máy chủ nhạy cảm | Firewall deny/allow logs, negative tests |
| **Just-in-time privileged access** | Tránh VPN user mặc định có admin privilege | Privileged access approval và time-bound role |
| **Quản lý certificate/key per device** | Thu hồi đúng một thiết bị thay vì secret dùng chung | Certificate serial/key ID, inventory, revocation state |
| **Session lifetime và reauthentication policy** | Giới hạn thời gian quyền truy cập không kiểm tra lại | Gateway configuration và expiry test |
| **Conditional access / risk-based policy** | Áp thêm điều kiện theo thiết bị, vị trí/risk signal | IdP decision logs và false positive review |
| **Centralized logging và correlation** | Điều tra được user ↔ session ↔ IP ↔ resource | Tỷ lệ log đầy đủ, traceable event IDs |
| **IPv6 và route/DNS policy** | Không để traffic đi ngoài vùng kiểm soát qua tuyến khác | Route lookup, IPv6 firewall, split DNS và flow logs |

**MFA, VPN và segmentation là các lớp bổ trợ nhau**. Nếu VPN user bị chiếm nhưng tài khoản chỉ có quyền tới ứng dụng nội bộ cụ thể và ứng dụng tiếp tục kiểm tra authorization, tác động thường nhỏ hơn so với mô hình VPN toàn mạng không phân đoạn.

### 10.2. Kết nối giữa VPN và phát hiện xâm nhập

IDS/IPS có thể phát hiện hành vi bất thường trong traffic từ VPN pool, nhưng cần biết **mapping session** để gắn hoạt động với đúng identity. Nếu sensor chỉ ghi source **10.90.40.25** mà không có lịch sử lease, SOC sẽ khó truy ngược đúng user khi IP được tái sử dụng.

Trong mô hình cloud, cần ghép **VPN/identity logs** với security groups, route tables, VPC/VNet flow logs, workload audit và cloud API events. Một flow tới cloud workload không tự chứng minh hành động ứng dụng; cần bổ sung log ở lớp dịch vụ.

## 11. Kiểm thử thu hồi và khôi phục mà không gây sự cố mới

**Chỉ thực hiện trong môi trường được cấp quyền**, ưu tiên test account, lab gateway, staging IdP hoặc phiên được xác nhận có thể chấm dứt. Không đăng nhập thử bằng credential đã được công bố rộng, không tạo hành vi dò mật khẩu và không truy cập dữ liệu ngoài phạm vi cần kiểm chứng.

### 11.1. Positive và negative tests

| Test | Điều cần xác minh | Kỳ vọng |
| --- | --- | --- |
| **N1 – credential cũ** | Tài khoản/credential đã thu hồi không còn xác thực được trên gateway đã chỉ định | Auth bị từ chối, log có policy/reason phù hợp |
| **N2 – phiên VPN cũ** | Session ID bị revoke/terminate không còn chuyển traffic hoặc reconnect ngoài ý muốn | Không có session active; các flow tiếp theo không được cho phép theo quyền cũ |
| **N3 – refresh token / cookie cũ** | Token/session thuộc phạm vi revoke không còn tạo grant mới | Thất bại theo cơ chế hệ thống; audit có sự kiện thu hồi |
| **N4 – certificate/peer key cũ** | Certificate hoặc public key đã bị thu hồi không thể thiết lập liên kết hợp lệ | Gateway reject; trạng thái CRL/OCSP/peer policy được xác nhận |
| **N5 – MFA yếu tố cũ** | Recovery code/factor nghi bị lộ không còn được chấp nhận | IdP không cho dùng yếu tố bị thu hồi |
| **N6 – network least privilege** | User đã phục hồi không thể vào management/data subnet ngoài quyền | Firewall deny/synthetic test đúng policy |
| **P1 – đăng nhập mới hợp lệ** | Người dùng xác minh đăng nhập từ thiết bị sạch bằng credential/factor mới | Session mới được cấp và ghi log đầy đủ |
| **P2 – tài nguyên công việc được phép** | Ứng dụng mà user cần hoạt động qua VPN | DNS, route, TLS, app authorization, log đúng |
| **P3 – logout và session expiry** | Phiên mới kết thúc theo chính sách | Gateway/IdP session không tồn tại quá thời hạn mong muốn |
| **O1 – correlation** | Một auth event gắn được với session, tunnel IP, flow và app request | SOC dựng timeline cùng ID và time window |
| **R1 – rollback/availability** | Thao tác containment không gây mất đường ứng cứu thiết yếu | Break-glass và quản trị ngoài băng còn hoạt động |

Việc một server từ chối kết nối ở bước N6 có thể do **mạng không reachable, DNS lỗi hoặc application error**, không tự chứng minh firewall policy được thực thi đúng. Cần thấy **deny event/policy ID** hoặc evidence tương đương tại enforcement point và thử một luồng hợp lệ đối chứng.

### 11.2. Xác minh trên từng lớp

~~~text
IdP / Directory:
  Account disabled? MFA/token revoke events? Role changed?

VPN gateway:
  Old sessions gone? New authentication with revoked credentials rejected?
  Assigned IP/role and session lifetime correct?

Firewall / Network:
  User reaches only approved prefixes/services?
  No unexpected IPv6, route, split tunnel or bypass?

Endpoint:
  Device posture accepted only after remediation?
  Old key/certificate removed from managed inventory?

Application:
  Old app sessions revoked where required?
  Access only to authorized functions, with audit trail?
~~~

Trong sản phẩm không hỗ trợ thu hồi tức thời một số loại token/session, phải ghi **thời gian hiệu lực còn lại, biện pháp kiểm soát tạm và rủi ro residual**, không báo “đã vô hiệu hóa hoàn toàn” chỉ vì giao diện quản trị hiển thị trạng thái tài khoản disabled.

## 12. Playbook triage sự cố và bảng quyết định nhanh

| Tình huống khi nhận alert | Hành động ưu tiên | Evidence/giới hạn |
| --- | --- | --- |
| Người dùng báo mật khẩu VPN gửi nhầm nhưng không có session lạ | Khóa/đổi credential, kiểm tra nơi rò và sign-in logs | Không có session lạ chưa chứng minh chưa từng bị dùng |
| Phát hiện active VPN session mà chủ account phủ nhận | Contain session + identity nhanh theo IR policy, lưu log, điều tra flow | Cần kiểm tra device/session và hoạt động downstream |
| Nhiều MFA push bất thường nhưng chưa login thành công | Bảo vệ account, xác minh độc lập, rà soát factor và chính sách chống fatigue | MFA prompts là tín hiệu rủi ro, không tự chứng minh đã vào VPN |
| VPN private key hoặc certificate nằm trong thiết bị bị đánh cắp | Thu hồi key/cert/peer, ngắt session, cấp lại trên thiết bị tin cậy | Khóa riêng có thể đã bị sao chép; không chỉ thu hồi thiết bị khỏi MDM |
| Gateway bị mất IdP connectivity khi đang xử lý | Kiểm tra cache/fallback/local auth và hành vi session | Không mặc định IdP outage sẽ ngắt tất cả phiên |
| Tài khoản có quyền admin hoặc nhà thầu truy cập tài sản nhạy cảm | Ưu tiên scope/containment và mở rộng log review theo quyền có thể sử dụng | Quyền cao làm tăng rủi ro, nhưng cần chứng cứ về hành động thực |
| Nhiều VPN sessions từ một public IP | Xác minh NAT/CGNAT/office proxy và identity từng session | Không gán mọi session về cùng một người dùng |
| Sau reset password vẫn thấy tunnel active | Ngắt session gateway, kiểm tra token/cert/cache và thời hạn | Password reset chưa giải quyết tất cả trạng thái |
| Client khôi phục login nhưng không vào app | Kiểm tra group policy, route, DNS, MFA, firewall và app auth | Không vội cấp Any–Any hoặc admin rights |

### 12.1. Dữ liệu cần để quyết định mức ưu tiên

Đặt mức ưu tiên dựa vào **risk và impact**, chẳng hạn:

- Account có quyền **quản trị, đặc quyền cloud hoặc truy cập tài chính/khách hàng**?
- Có **thành công xác thực bất thường** hoặc session active rõ ràng không?
- Endpoint có dấu hiệu malware, lộ private key hoặc yếu tố MFA không?
- Có bằng chứng **tải/xuất dữ liệu, tạo tài khoản, thay quyền hoặc lệnh quản trị** không?
- Có quyền truy cập rộng tới các subnet thiếu segmentation không?
- Khả năng thu hồi **ngay lập tức** tới đâu, và hệ thống nào cần phụ thuộc quyền đó?

Tránh sử dụng một ngưỡng cứng kiểu “địa lý A = critical” mà thiếu ngữ cảnh thiết bị, công việc và evidence.

## 13. Case study: tài khoản nhân viên bị phishing dẫn tới VPN session lạ

### 13.1. Bối cảnh giả định

Một nhân viên làm việc từ xa dùng **SSL VPN với SSO và MFA**, gateway cấp địa chỉ **10.90.40.25/24** khi kết nối. SOC nhận cảnh báo từ IdP về phiên xác thực có đặc điểm bất thường. Người dùng cho biết đã mở một trang đăng nhập giả và nhìn thấy một MFA prompt không chủ động yêu cầu.

Điều cần xác định: có session VPN trái phép không, nó còn hoạt động không, những tài nguyên nào được tiếp cận, và user có thể trở lại công việc bằng thiết bị tin cậy hay chưa.

### 13.2. Timeline được tạo từ evidence giả định

| UTC | Evidence | Quan sát | Diễn giải thận trọng |
| --- | --- | --- | --- |
| **02:05** | E-01 / IdP | MFA prompt mới từ nguồn mạng không thuộc baseline | Dấu hiệu nghi vấn, cần xác minh với user |
| **02:14** | E-02 / IdP | Một sign-in thành công liên quan account u-1042 | Có token/session xác thực hợp lệ theo IdP |
| **02:14** | E-03 / VPN gateway | Session sess-9821 mở, IP pool 10.90.40.25 | Có VPN session cần xác minh actor |
| **02:20** | E-04 / Firewall | Flow TCP/443 từ 10.90.40.25 tới app 10.20.30.15 được allow | Có flow theo policy, chưa chứng minh dữ liệu bị đọc |
| **02:21** | E-05 / Firewall | Flow tới 10.20.99.10:3389 bị deny | Điểm kiểm soát có ghi nhận và từ chối kết nối đó |
| **02:31** | E-06 / Application | Có request tới API với user context liên quan | Cần xác minh request ID, action và kết quả |
| **02:39** | E-07 / User confirmation | User phủ nhận phiên được ghi nhận | Tăng mức nghi ngờ truy cập trái phép |
| **02:42** | E-08 / Gateway audit | Session sess-9821 bị terminate | Bằng chứng hành động tại gateway |
| **02:43** | E-09 / IdP audit | Account bị block sign-in, sessions/tokens được revoke theo policy | Cần xác minh các phiên/token không còn hiệu lực |
| **03:05** | E-10 / IR tracker | Endpoint đang được EDR kiểm tra và identity recovery chờ xác minh | Không nên khôi phục vội khi phạm vi chưa rõ |

Mọi IP, ID và mốc thời gian chỉ để **học cách dựng timeline**, không mô tả sự cố thật. Không được suy từ một flow cho phép rằng đã có exfiltration; cần evidence của application, storage, proxy hoặc DLP tương ứng.

### 13.3. Phản ứng có thứ tự

1. **Tạo case và xác minh independent contact** với nhân viên.
2. **Ghi trạng thái account/session**, audit IDs, profile và assigned tunnel IP trước khi thay đổi nếu không gây trì hoãn nguy hiểm.
3. **Chấm dứt sess-9821**, chặn sign-in mới của account, revoke tokens/remembered sessions theo khả năng.
4. **Rà soát MFA enrollment**, reset yếu tố đã bị ảnh hưởng và ngăn tự đăng ký ngoài quy trình xác minh.
5. **Kiểm tra endpoint** bằng EDR/MDM, quyết định có cần isolate, reimage hoặc re-enroll certificate/device identity.
6. **Ghép log network với app activity**, tìm thao tác có thể tác động dữ liệu, quyền hoặc thiết lập persistence.
7. **Review access role** và bổ sung segmentation ở management subnet nếu phát hiện quyền vượt nhu cầu.
8. **Khôi phục user** với credential và MFA mới từ thiết bị đáng tin, test chỉ truy cập ứng dụng được phép.
9. **Theo dõi sau khôi phục** với detection rule, owner và mốc rà soát rõ ràng.

### 13.4. Mẫu case record để review

~~~yaml
# Mẫu hồ sơ tổng hợp, không phải schema của IdP hay VPN vendor.
case_id: IR-VPN-012
title: "Suspected unauthorized VPN access after credential phishing"
classification: "suspected account compromise"
identity:
  account_id: "u-1042"
  privileged: false
vpn:
  gateway_id: "VPN-GW-A"
  session_id: "sess-9821"
  assigned_ip: "10.90.40.25"
  session_status: "terminated"
evidence:
  - id: "E-01"
    source: "IdP sign-in and MFA audit"
  - id: "E-03"
    source: "VPN connection/session logs"
  - id: "E-04"
    source: "Firewall flow and NAT records"
  - id: "E-06"
    source: "Application audit, pending review"
containment:
  - "Block new sign-ins and rotate exposed credential"
  - "Terminate affected VPN session"
  - "Revoke affected IdP tokens and MFA factors when supported"
unknowns:
  - "Whether application data was accessed or changed"
  - "Whether endpoint tokens or certificate were copied"
recovery_gate:
  - "Independent identity verification"
  - "Device remediation and trusted re-enrollment"
  - "Negative and positive access tests"
owner: "Security Incident Response + IAM + VPN Operations"
~~~

Mẫu này giúp ghi rõ **đã xử lý gì, bằng chứng ở đâu và chưa biết gì**. Không đánh dấu vụ việc “resolved” chỉ vì người dùng đã đăng nhập được bằng mật khẩu mới.

## 14. Những nhầm lẫn và lỗi vận hành cần tránh

1. **“Đổi mật khẩu là tự động cắt mọi VPN session.”** Tunnel/token/cert có thể tiếp tục hiệu lực theo policy khác.
2. **“VPN có MFA là không thể bị chiếm.”** Phishing, lừa phê duyệt MFA, session token theft và endpoint compromise vẫn cần xem xét.
3. **“IP nguồn lạ chắc chắn là attacker.”** NAT, roaming, nhà cung cấp mạng và proxy có thể thay đổi IP.
4. **“Tài khoản bị lộ đồng nghĩa dữ liệu chắc chắn bị lấy.”** Phải xác minh application/data access riêng.
5. **“Không có VPN log nghĩa không có truy cập.”** Log retention, sampling, thiếu region/gateway hoặc ZTNA path khác có thể tạo điểm mù.
6. **“Chặn tunnel IP là đủ cho mọi session của user.”** Pool IP có thể tái sử dụng và session khác có thể nhận địa chỉ khác.
7. **“Disable IdP user luôn ngắt tunnel hiện hành ngay lập tức.”** Gateway có thể cache quyền hoặc có session riêng.
8. **“Thu hồi certificate trong CA ngay lập tức chặn mọi phiên.”** Gateway có thể cache revocation và phiên đã thiết lập có thể cần chấm dứt riêng.
9. **“Khóa một WireGuard peer có thể thực hiện bằng reset password VPN mặc định.”** Với WireGuard thuần phải xử lý peer key/control plane tương ứng.
10. **“Split tunnel cho phép SOC thấy mọi traffic của client.”** Traffic ngoài tunnel không nhất thiết đi qua gateway doanh nghiệp.
11. **“Firewall allow chứng minh API đã đọc dữ liệu.”** Cần log ứng dụng và kết quả thực tế.
12. **“MFA enrollment mới là thao tác vô hại.”** Khi account nghi bị chiếm, enrollment mới có thể là dấu hiệu persistence.
13. **“Thiết bị đang đăng nhập được thì chắc chắn sạch.”** Endpoint malware có thể tiếp tục lấy token/credential mới.
14. **“Để làm việc lại nhanh, tạm cấp full network access.”** Điều đó tăng blast radius đúng lúc danh tính đang có rủi ro.
15. **“Một VPN gateway duy nhất đã được revoke là đủ.”** Có thể còn gateway region, portal, profile hoặc app session khác.
16. **“Tạm khóa toàn bộ VPN luôn là cách an toàn nhất.”** Có thể làm mất đường ứng cứu/quản trị và gây outage lớn; cần quyết định theo risk và tác động.
17. **“Khóa IPv4 là hết rủi ro.”** IPv6 routes, split DNS và alternative access path có thể còn hoạt động.
18. **“User xác nhận qua chính email đang bị nghi takeover là đủ.”** Cần independent verification.
19. **“Khôi phục VPN xong là đóng case.”** Còn cần đánh giá dữ liệu, role, hệ thống downstream, telemetry và lessons learned.

## 15. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Password đã đổi nhưng VPN vẫn hoạt động

Một nhân viên phát hiện mật khẩu VPN bị phơi lộ và reset qua IdP. Sau đó dashboard gateway vẫn có một tunnel trước đó của account. Có thể đóng case không?

**Gợi ý:** chưa. Phải xác định tunnel thuộc session nào, chủ thể nào, có traffic không và cách revoke/terminate ở gateway; kiểm tra IdP tokens, MFA, các gateway khác, app sessions, sau đó thực hiện negative test theo phạm vi được phép.

### Bài 2 — Thiết bị bị mất và certificate client

Laptop bị mất khi đang lưu certificate xác thực VPN. Tài khoản SSO đã được disable nhưng certificate có thể còn dùng trên một gateway. Hãy đề xuất chuỗi containment.

**Gợi ý:** thu hồi certificate/private-key identity ở PKI/gateway, xác nhận trạng thái CRL/OCSP hoặc allowlist, ngắt session, rà soát mọi service dùng certificate, kiểm tra khóa/secret khác trên thiết bị, thu hồi MDM/EDR device identity rồi cấp credential mới trên endpoint tin cậy.

### Bài 3 — IP pool trùng sau khi session kết thúc

Gateway cấp **10.90.40.25** cho account A đến 09:20. Đến 09:40 địa chỉ này được cấp cho account B. SOC thấy firewall flow lúc 09:50 và gán cho A. Kết luận có hợp lệ không?

**Gợi ý:** không. Cần ghép địa chỉ tunnel với **session ID, user ID, gateway và khoảng thời gian lease**, đồng thời xét NAT/flow logs. Trùng IP sau tái cấp phát không phải bằng chứng liên quan account cũ.

### Bài 4 — MFA push bị lạm dụng

Nhân viên nói nhận liên tiếp nhiều MFA push khi không đăng nhập, sau đó có một sự kiện MFA success. Những thông tin nào phải kiểm chứng trước khi kết luận user chủ động login?

**Gợi ý:** kênh xác minh độc lập, auth event ID, time/source/device, số prompt bị từ chối, method sử dụng, có thay factor hay trusted-device state không, VPN session và app activity. Tạm bảo vệ account theo risk policy, không dựa vào trạng thái success duy nhất.

### Bài 5 — Phân đoạn quyền sau VPN

Nhà thầu chỉ cần truy cập một web application nội bộ nhưng group VPN hiện cho phép toàn bộ subnet quản trị. Đề xuất **threat → control → test** phù hợp.

**Gợi ý:** tách role/segmentation để chỉ tới app/port cần thiết, bổ sung application authorization và MFA/device posture; dùng positive test truy cập app hợp lệ, negative test tới management subnet, đối chiếu firewall policy/log và định kỳ rà soát quyền.

### Bài 6 — WireGuard key bị rò trong repository

Một private key WireGuard dùng cho laptop bị đưa vào repository có người ngoài quyền truy cập. Chủ thiết bị đã tạo key mới nhưng gateway vẫn giữ cấu hình public key cũ. Vấn đề còn lại?

**Gợi ý:** cặp khóa cũ vẫn có thể được server chấp nhận. Cần vô hiệu hóa public key cũ ở tất cả gateway/controller liên quan, cập nhật thiết bị tin cậy, kiểm chứng peer cũ không truy cập được và tìm dấu hiệu sử dụng bất thường trước khi đóng case.

### Bài 7 — Xây dựng timeline từ nhiều nguồn

Một VPN session có source public IP, assigned tunnel IP, group, connect/disconnect logs, firewall flow và app audit. Hãy lập bảng evidence cho thấy **những hoạt động đã được chứng minh**, **những hoạt động chỉ có thể xảy ra về mặt quyền**, và **những nguồn chưa có dữ liệu**.

**Gợi ý:** tách khả năng truy cập (route/role), kết nối mạng (firewall flow), request ứng dụng (app log) và thao tác dữ liệu (audit outcome). Ghi đủ timezone, session mapping và giới hạn retention; không khẳng định exfiltration từ mỗi allow event.

## 16. Checklist dành cho SOC, IAM và VPN operations

| Câu hỏi bắt buộc | Bằng chứng / hành động |
| --- | --- |
| Tài khoản có thực sự bị phơi lộ hoặc bị dùng trái phép? | Report + IdP/VPN auth events + independent verification |
| Loại credential nào bị ảnh hưởng? | Password, MFA, certificate/key, token/session và device inventory |
| Có những gateway/profiles/regions nào chấp nhận account? | VPN inventory, SSO policy, portal/peer mapping |
| Có active session hoặc token còn sống không? | Gateway session list, IdP/token audit, application sessions |
| Đã chặn đăng nhập mới và terminate session cũ chưa? | Auth rejection, session disconnect, revoke audit |
| Có private key/certificate hoặc MFA factor phải rotate không? | PKI/peer state, MFA enrollment/verification |
| Thiết bị có bị malware hoặc takeover không? | EDR/MDM investigation, device posture |
| Session được cấp IP/route/role nào, và trong khoảng nào? | VPN pool mapping, routing policy, session ID |
| Tài nguyên nào thực tế đã được truy cập hoặc thay đổi? | Firewall/NAT/DNS/IDS + app/cloud audit |
| Có nguy cơ lateral movement hoặc persistence không? | Changes to IAM role, account, token, admin resources |
| Có cần bảo vệ dữ liệu hoặc thông báo sự cố không? | Risk/privacy/legal assessment theo quy định |
| Khôi phục có dùng credential, MFA và thiết bị tin cậy không? | Recovery approval, credential/factor re-enrollment |
| Negative/positive tests đã PASS chưa? | Auth reject cũ, no old tunnel, app access đúng scope, deny ngoài quyền |
| Có giám sát sau khôi phục và owner không? | SIEM alert, playbook, thời hạn rà soát, post-incident tasks |

### Mẫu kết luận ngắn, không phóng đại evidence

> Trong khoảng thời gian đã xác minh, tài khoản **u-1042** có session VPN **sess-9821** từ nguồn chưa được chủ tài khoản xác nhận. Gateway đã ghi nhận chấm dứt session, IdP đã chặn đăng nhập mới và thu hồi các phiên/token thuộc phạm vi hỗ trợ. Firewall ghi nhận một số flow từ IP tunnel được cấp cho phiên, nhưng **chưa đủ chứng cứ kết luận dữ liệu bị đọc hoặc bị lấy đi**. Điều tra ứng dụng và endpoint đang tiếp tục; tài khoản chỉ được khôi phục sau xác minh danh tính, xử lý thiết bị và kiểm thử lại các quyền truy cập.

Trong báo cáo production, thay các ID minh họa bằng tham chiếu được phân quyền và mô tả chính xác **phần nào đã được chứng minh, phần nào còn bất định và khi nào sẽ rà soát lại**.

## 17. Tổng kết

**Xử lý tài khoản VPN bị lộ** là một quy trình **incident response xuyên nhiều lớp** chứ không phải chỉ là thao tác đổi mật khẩu. Cần nhận diện loại bí mật bị lộ, **khóa khả năng đăng nhập mới, chấm dứt phiên/tunnel đang tồn tại, thu hồi token, certificate hoặc peer key tương ứng**, bảo quản evidence, dựng timeline và xác định các tài nguyên đã bị tiếp cận.

Khi khôi phục, phải xác minh danh tính qua kênh tin cậy, kiểm tra hoặc xây dựng lại endpoint, cấp credential/MFA mới và quyền tối thiểu, sau đó thực hiện **positive/negative tests** để xác nhận trạng thái cũ không còn được sử dụng. Một kiến trúc **SECURITY_NETWORK_SECURITY** an toàn kết hợp **VPN/ZTNA, MFA chống phishing, segmentation, firewall, DNS protection, IDS/IPS, endpoint posture và cloud audit** để giới hạn phạm vi nếu một tài khoản bị lộ và để SOC có bằng chứng điều tra đầy đủ.

Chỉ đóng sự cố khi đã xác minh **khả năng truy cập trái phép được ngăn trong phạm vi cần thiết, người dùng hợp lệ phục hồi đúng quyền, rủi ro còn lại được ghi nhận và những biện pháp phòng ngừa/giám sát đã có người chịu trách nhiệm**.
