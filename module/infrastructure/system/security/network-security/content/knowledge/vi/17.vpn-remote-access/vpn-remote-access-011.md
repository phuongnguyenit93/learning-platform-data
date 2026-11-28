# Theo dõi phiên VPN và phát hiện bất thường trong truy cập từ xa

## 1. Vì sao phải giám sát phiên VPN?

**Virtual Private Network (VPN)** tạo một đường kết nối được bảo vệ bằng cơ chế mật mã phù hợp giữa thiết bị/người dùng từ xa và hạ tầng mạng hoặc giữa các mạng. Với **remote-access VPN**, người dùng có thể truy cập dịch vụ làm việc khi ở ngoài văn phòng; điều này kéo ranh giới truy cập từ mạng nội bộ ra nhiều điểm cuối và môi trường kết nối khác nhau.

**Theo dõi phiên VPN** là hoạt động thu thập, đối chiếu và đánh giá **vòng đời kết nối**, **danh tính**, **điều kiện xác thực**, **địa chỉ và tài nguyên được cấp**, **quyền truy cập** cùng **hành vi lưu lượng** trong thời gian một phiên tồn tại. **Phát hiện bất thường** là nhận ra những sự kiện hoặc chuỗi hành vi không phù hợp với chính sách, đường cơ sở (baseline) hay kịch bản đe dọa đã xác định để điều tra và phản ứng đúng mức.

Chủ đề thuộc chương **VPN và truy cập từ xa** của học phần **SECURITY_NETWORK_SECURITY**. Nó liên kết với phân đoạn mạng, firewall, IDS/IPS, xác thực kết nối, bảo vệ DNS và giám sát hạ tầng/cloud: VPN cho phép đi vào một số tài nguyên, nhưng **không tự bảo đảm tất cả hành động sau khi thiết lập tunnel là hợp lệ**.

**Ví dụ:** một tài khoản thường đăng nhập VPN từ thiết bị được quản trị vào giờ làm việc. Trong một buổi tối, hệ thống nhận hàng loạt yêu cầu đăng nhập bị từ chối từ nhiều IP, sau đó có một phiên thành công từ thiết bị chưa từng thấy và kết nối tới máy chủ quản trị. Từng sự kiện riêng lẻ chưa chứng minh có tấn công; kết hợp **lịch sử xác thực, thiết bị, rủi ro phiên và truy cập nội bộ** mới tạo được tín hiệu điều tra có ý nghĩa.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vòng đời phiên VPN từ xác thực, thiết lập tunnel, cấp địa chỉ/chính sách đến gia hạn, ngắt kết nối và thu hồi quyền.
2. Chọn dữ liệu giám sát từ **VPN gateway, IdP/MFA, RADIUS/AAA, endpoint, firewall, DNS, IDS/IPS và SIEM**.
3. Xây dựng sơ đồ tương quan **người dùng – thiết bị – phiên – IP ngoài – IP trong tunnel – thời điểm – ứng dụng đích**.
4. Phân biệt bất thường thực sự với roaming, CGNAT, thay đổi IP, reconnect hoặc chuyển ca hợp lệ.
5. Viết những điều kiện phát hiện khái niệm cho password spraying, MFA abuse, phiên song song bất thường, truy cập lệch baseline và lưu lượng dữ liệu khác thường.
6. Thiết kế cảnh báo, triage, ngăn chặn và khôi phục có bằng chứng, đồng thời bảo vệ dữ liệu cá nhân trong log.

## 2. Threat model: VPN tạo ra những ranh giới nào?

### 2.1. Các thành phần cần bảo vệ

| Thành phần | Tài sản hoặc chức năng | Rủi ro khi thiếu giám sát |
| --- | --- | --- |
| Tài khoản/IdP | Nhận diện người dùng, nhóm và trạng thái đăng nhập | Credential theft, password spray, MFA abuse |
| Thiết bị đầu cuối | Laptop, điện thoại, máy cá nhân hoặc thiết bị được quản trị | Endpoint bị chiếm quyền rồi dùng tunnel hợp lệ |
| VPN gateway/concentrator | Điểm kết thúc tunnel, chính sách và năng lực kết nối | Session hijacking, cấu hình sai, cạn tài nguyên |
| AAA/RADIUS hoặc hệ thống tương đương | Xác thực/authorization/accounting | Mất dấu vết ai đăng nhập và phiên kết thúc lúc nào |
| Pool địa chỉ tunnel | Gán IP/IPv6 prefix cho phiên | Không thể ánh xạ luồng mạng tới phiên đúng thời điểm |
| Firewall/segmentation | Kiểm soát VPN → vùng nội bộ | Một phiên vượt phạm vi quyền, lateral movement |
| DNS và ứng dụng | Phân giải tên, truy cập và hành vi nghiệp vụ | DNS bất thường, lạm dụng dịch vụ nhạy cảm |
| Logging/SIEM | Thu thập, chuẩn hóa, tương quan và cảnh báo | Không phát hiện kịp hoặc tạo quá nhiều false positive |

### 2.2. Mô hình trust boundary

~~~mermaid
flowchart LR
    U[Người dùng từ xa / endpoint] --> WAN[Internet / mạng không tin cậy]
    WAN --> V[VPN gateway]
    V --> ID[IdP / MFA / AAA]
    V --> FW[Firewall / policy giữa VPN và nội bộ]
    FW --> APPS[Ứng dụng được cấp quyền]
    FW -. Chặn mặc định .-> MGMT[Vùng quản trị hoặc dữ liệu nhạy cảm]
    U -. Endpoint telemetry .-> SOC[SIEM / SOC]
    V -. Session logs .-> SOC
    ID -. Authentication logs .-> SOC
    FW -. Flow / deny logs .-> SOC
    APPS -. App audit .-> SOC
~~~

Sơ đồ là kiến trúc chức năng. Thực tế IdP có thể được gọi **trước, trong hoặc khi tái đánh giá** một phiên; dữ liệu VPN có thể được tunnel về trung tâm hoặc cấp quyền ứng dụng theo mô hình khác. Điều quan trọng là hiểu **đường dữ liệu thực tế**: một hệ thống giám sát ngoài Internet chỉ thấy phần tunnel được mã hóa, không nhất thiết nhìn thấy các kết nối ứng dụng ở bên trong.

**Nguyên tắc:** xác thực thành công không làm máy trở thành đáng tin vĩnh viễn. Phân quyền VPN phải giới hạn tài nguyên cần thiết, và theo dõi phải tiếp tục **trong suốt thời gian phiên còn hiệu lực**, kể cả khi tài khoản đã đăng nhập bằng MFA.

## 3. Vòng đời một phiên VPN cần quan sát

Một kết nối truy cập từ xa có thể tạo ra nhiều sự kiện tách biệt: bắt đầu phiên transport, xác thực danh tính, xác thực yếu tố thứ hai, thiết lập security association hoặc tunnel, nhận địa chỉ/tuyến, truy cập tài nguyên, gia hạn khóa, reconnect, idle timeout, logout hoặc mất liên lạc.

~~~mermaid
sequenceDiagram
    participant C as VPN client
    participant G as VPN gateway
    participant I as IdP / MFA / AAA
    participant F as Firewall / ứng dụng
    participant S as SIEM
    C->>G: Yêu cầu kết nối
    G->>I: Xác thực / kiểm tra chính sách
    I-->>G: Thành công hoặc từ chối
    G-->>S: Auth event (nếu có)
    opt Được phép
        G-->>C: Tunnel / địa chỉ / route / DNS theo profile
        G-->>S: Session established + session ID
        C->>G: Lưu lượng đã bảo vệ qua tunnel
        G->>F: Lưu lượng đã xử lý theo policy
        F-->>S: Flow / application audit
        G-->>S: Interim counters / rekey / reconnect
        C->>G: Disconnect hoặc mất liên lạc
        G-->>S: Session closed / timeout + counters
    end
~~~

### 3.1. Phân biệt trạng thái với nhãn log của sản phẩm

| Trạng thái logic | Ví dụ thông tin cần thu | Cách diễn giải |
| --- | --- | --- |
| **CONNECT_ATTEMPT** | Timestamp, nguồn, gateway, client type | Có thử kết nối; chưa chứng minh đã xác thực |
| **AUTH_FAILED** | Account, reason category, IdP/correlation ID | Đăng nhập bị từ chối; có thể do sai mật khẩu, chính sách hoặc MFA |
| **AUTH_SUCCESS** | Account, auth method, MFA result, device context | Danh tính được xác thực trong bước tương ứng; tunnel có thể chưa sẵn sàng |
| **TUNNEL_ESTABLISHED** | Session ID, external IP, assigned tunnel IP, VPN profile | Client đã có một kết nối/tunnel theo cách sản phẩm định nghĩa |
| **SESSION_ACTIVE** | Last seen, byte counters, route/policy, health | Phiên đang được gateway theo dõi; chưa bảo đảm thiết bị đang tương tác với ứng dụng |
| **REKEY/REAUTH** | Security association/credentials, thời gian | Khóa hoặc trạng thái được làm mới; không luôn là một phiên người dùng mới |
| **RECONNECT/ROAM** | Old/new source, device ID, connection ID | Có thể do đổi Wi-Fi/4G, NAT, VPN client hoặc sự cố mạng |
| **SESSION_TERMINATED** | Stop reason, duration, bytes, logout/timeout | Phiên đã đóng theo nguồn ghi nhận; log có thể đến trễ |
| **ACCESS_DENIED** | User/session, destination, policy ID, action | Tài nguyên nội bộ bị từ chối; cần đối chiếu bối cảnh |

Các tên trạng thái viết hoa chỉ là **mô hình chuẩn hóa trong bài học**, không phải bộ event chuẩn dùng chung của mọi giải pháp VPN.

### 3.2. Không đồng nhất phiên với socket hoặc security association

- **User session:** khoảng thời gian người dùng/thiết bị được gateway xem là có quyền truy cập.
- **Transport connection:** TCP, UDP hoặc kết nối đến gateway có thể được tạo lại khi đường mạng thay đổi.
- **IKE Security Association / CHILD_SA:** với IPsec/IKEv2, các trạng thái và lần rekey có vòng đời riêng; **một CHILD_SA mới không mặc nhiên là một người dùng đăng nhập mới**.
- **TLS-based VPN:** có thể có TLS session/connection, application session, token và tunnel logic không trùng nhau hoàn toàn.
- **WireGuard-style tunnels:** peer/khóa, thời điểm handshake và bộ đếm truyền/nhận **không tự cung cấp phiên đăng nhập gắn username/MFA**. Nếu giải pháp dùng WireGuard cho remote access, cần tích hợp control plane/IdP hoặc hệ thống audit phù hợp để tạo quan hệ với danh tính.

Vì vậy trước khi dựng dashboard, phải chọn **đơn vị đang đếm**: user session, tunnel, IKE SA, endpoint peer, transport connection hay lần xác thực. Cộng các loại này vào một chỉ số “active VPN users” sẽ gây báo cáo sai.

### 3.3. Sự kiện nào có thể thiếu?

Trong trường hợp client mất điện, mất kết nối Internet hoặc gateway reboot, log **logout/stop** không phải lúc nào cũng được gửi đúng lúc. Cần dựa vào idle/session timeout, session table, RADIUS Accounting-Stop nếu thực sự có, hoặc quá trình đối chiếu định kỳ để xác định trạng thái sau cùng.

Một sự kiện **START** không có STOP lập tức không chứng minh tài khoản đang bị chiếm, và hai event START có thể thuộc một lần reconnect hợp lệ. Cần correlation ID, event time, trạng thái hiện tại và thời gian chờ trước khi báo bất thường.

## 4. Nguồn dữ liệu để theo dõi phiên

### 4.1. VPN gateway/concentrator

Nguồn quan trọng nhất để biết tunnel được **cho phép** và **được gán quyền gì**. Tùy sản phẩm có thể ghi:

- Username/account ID, realm/tenant, nhóm quyền, profile và kết quả authorization.
- Session ID, tunnel ID, peer ID, client version, gateway/cluster node.
- IP ngoài tunnel (source public IP), port, ASN/geo-IP nếu được enrichment.
- IP hoặc prefix được cấp bên trong tunnel, IPv4/IPv6, DNS, routes, split/full tunnel.
- Connected/disconnected/reauth/rekey/reconnect event và nguyên nhân đóng.
- Thời gian bắt đầu, kết thúc, idle time, byte/packet vào–ra và số lần reconnect.
- Thông tin posture, compliance hay chứng chỉ máy nếu gateway thực sự hỗ trợ.

**Không giả định** mọi giao thức hoặc vendor ghi đủ các trường. Nhiều giá trị chỉ tồn tại trong hệ thống IdP/endpoint hoặc API điều khiển khác.

### 4.2. IdP, MFA, RADIUS/AAA

| Nguồn | Dữ liệu có thể có | Giới hạn cần hiểu |
| --- | --- | --- |
| **Identity provider (IdP)** | Account ID, sign-in result, conditional access, session token, device/risk signal | Không chứng minh tunnel đã được thiết lập hoặc traffic nội bộ đã đi qua |
| **MFA service** | Challenge, approve/deny, phương pháp, request ID | MFA thành công không tự loại trừ phishing hoặc lạm dụng phiên đã cấp |
| **RADIUS authentication** | Access-Request/Accept/Reject, NAS, account, policy | Không mặc định có thông tin traffic sau đăng nhập |
| **RADIUS accounting** | Start, Interim-Update, Stop, session ID, counters tùy thiết bị | Có thể mất hoặc trễ bản tin Stop/Interim; cần kiểm tra cấu hình thực tế |
| **Certificate/PKI service** | Trạng thái cert, identity mapping, expiry/revocation | Cert hợp lệ không chứng minh endpoint không nhiễm mã độc |

Theo **RFC 2866**, RADIUS Accounting hỗ trợ các sự kiện như **Accounting-Start, Accounting-Stop** và thông tin thống kê tùy NAS/client; khả năng có **interim updates** và các attribute cụ thể còn phụ thuộc triển khai. Không dùng accounting event thay thế việc đánh giá quyền truy cập ứng dụng.

### 4.3. Firewall, DNS, proxy và ứng dụng nội bộ

Khi VPN gateway đã giải mã và chuyển tiếp lưu lượng nội bộ, các điểm khác có thể quan sát:

- Firewall/ISFW: session/flow, IP nguồn tunnel, đích, port, rule, allow/deny và lượng dữ liệu.
- DNS resolver: truy vấn tên miền, client tunnel IP, policy DNS và thời điểm.
- Proxy/SWG/WAF: request HTTP(S), route, policy, web category nếu có thể quan sát đúng phạm vi.
- Ứng dụng: principal được xác thực, hành động nghiệp vụ, object/dữ liệu truy cập và request ID.
- IDS/IPS/NDR: phát hiện thăm dò, lateral movement và mẫu lưu lượng bất thường khi đặt đúng vị trí.

**Dữ liệu bị mã hóa:** sensor ngoài tunnel thường chỉ thấy địa chỉ gateway, metadata kết nối VPN, thời gian và lượng byte; nó không đương nhiên đọc được truy vấn nội bộ. Đối với TLS bên trong tunnel, sensor sau gateway cũng có thể **không thấy nội dung ứng dụng** nếu không ở điểm được phép giải mã; ứng dụng/WAF/proxy phù hợp mới có ngữ cảnh tương ứng.

### 4.4. Endpoint/EDR và quản lý thiết bị

Thông tin endpoint giúp phân biệt tài khoản bị lộ với hoạt động hợp lệ:

- Device ID do hệ thống quản lý cấp, chứng chỉ và trạng thái quản trị.
- OS, VPN client version, thời điểm boot, thay đổi mạng và reconnect.
- Posture/compliance theo tiêu chí được quản lý, tình trạng EDR và cảnh báo malware.
- Process/network telemetry liên quan tới kết nối, trong phạm vi thu thập được phép.
- Dấu hiệu thiết bị mới, cert thay đổi hoặc trình duyệt/token bị chiếm đoạt.

Không tự tin vào một trường **device_name** do client gửi: định danh cần có nguồn xác thực/tin cậy. Với thiết bị BYOD, khả năng thu thập có thể bị hạn chế về kỹ thuật, chính sách và quyền riêng tư.

## 5. Thiết kế bản ghi phiên và tương quan nhiều nguồn

### 5.1. Mô hình dữ liệu chuẩn hóa

Một session record hữu ích nên có:

| Nhóm trường | Trường cần lưu nếu có | Mục đích |
| --- | --- | --- |
| Định danh | **user_id, device_id, session_id, gateway_id** | Gắn sự kiện với đúng phiên và thiết bị |
| Thời gian | **event_time_utc, received_time_utc**, start/end/last_seen | Sắp thứ tự theo thời điểm gốc và theo lúc log tới |
| Kết nối | **external_ip, external_port, tunnel_ip, tunnel_ipv6**, gateway endpoint | Tra nguồn ngoài và lưu lượng nội bộ |
| Xác thực | auth_result, auth_method, MFA result, IdP correlation ID | Kiểm tra chất lượng xác thực và đường điều kiện truy cập |
| Chính sách | VPN profile, group, route set, allowed segment, policy version | Biết tài nguyên nào được phép truy cập |
| Hoạt động | bytes_in/out, packet counters, active/idle seconds, disconnect reason | Đánh giá hành vi phiên và lưu lượng |
| Nguồn/độ tin cậy | log_source, collector, parser version, identity confidence | Biết dữ liệu nào quan sát được và giới hạn |
| Điều tra | alert_id, ticket, triage verdict, context | Liên kết sự kiện với quá trình phản ứng |

Không nên dùng IP ngoài làm **session ID**. Một địa chỉ công cộng có thể đại diện nhiều người qua CGNAT, văn phòng hoặc proxy; IP cũng thay đổi khi roaming. IP tunnel cũng có thể được cấp lại cho người khác sau khi phiên cũ kết thúc.

### 5.2. Ví dụ bản ghi phiên đã làm sạch

~~~json
{
  "event_time_utc": "2026-11-28T09:15:00Z",
  "event_type": "vpn_session_established",
  "gateway_id": "vpn-lab-01",
  "session_id": "lab-session-1042",
  "user_id": "user-lab-07",
  "device_id": "managed-device-07",
  "external_ip": "198.51.100.45",
  "tunnel_ip": "192.0.2.105",
  "vpn_profile": "employees-standard",
  "auth_result": "success",
  "mfa_result": "success",
  "policy_version": "vpn-policy-2026-11",
  "log_source": "vpn-gateway-lab"
}
~~~

Đây là **JSON minh họa**, không phải schema chuẩn của nhà sản xuất hoặc bản ghi người dùng thật. IP **198.51.100.0/24**, **192.0.2.0/24** và **203.0.113.0/24** là dải dành cho tài liệu theo RFC 5737. Chỉ sử dụng dữ liệu giả hoặc đã được xử lý theo quyền truy cập.

### 5.3. Tương quan IP tunnel theo thời gian

Giả sử gateway cấp **192.0.2.105** cho user A từ 09:00 đến 10:00, sau đó cấp lại cho user B từ 10:30 đến 11:30. Một firewall log lúc 10:45 ghi IP nguồn 192.0.2.105.

**Kết luận đúng:** không thể gán log này cho user A chỉ vì từng thấy A dùng địa chỉ đó. Phải tra **dải thời gian hiệu lực của phiên**, đồng bộ đồng hồ và đối chiếu session/gateway. Nếu log đến trễ, dùng **event time** thay vì mặc định dùng thời điểm collector nhận được log.

Quy tắc tương quan khái niệm:

~~~text
flow.src_ip == vpn_session.tunnel_ip
AND flow.event_time nằm trong khoảng session.start_time .. session.end_time
AND flow.network_zone == VPN_REMOTE_ACCESS
AND route/gateway context tương thích
~~~

Khi thiếu end_time, cần một trạng thái phiên được gateway xác minh hoặc quy tắc timeout được **ghi chú là ước lượng**, không tự coi phiên kéo dài vô hạn. Một số thiết kế có thể cấp trùng tunnel IP ở các gateway/VRF khác nhau; phải bao gồm **network context** thay vì so IP toàn cục.

### 5.4. Đồng bộ thời gian và tính toàn vẹn

SIEM cần đồng bộ timestamp giữa gateway, IdP, MFA, firewall, DNS và endpoint; lý tưởng ghi UTC cùng timezone/offset rõ ràng. Hãy theo dõi **log ingestion delay**, clock skew, trùng event, thiếu sequence và lỗi parser.

Log an ninh cần được chuyển qua kênh bảo vệ phù hợp, hạn chế quyền chỉnh sửa/xóa, kiểm soát thời gian lưu và có quy trình điều tra thay đổi cấu hình. Không lưu plaintext mật khẩu, mã OTP, private key, session cookie hoặc token thật trong log.

## 6. Kiến trúc thu thập và cảnh báo

Một nền tảng quan sát phiên VPN thường cần ít nhất ba khả năng: **thu thập đầy đủ**, **chuẩn hóa và liên kết đúng**, **đưa ra cảnh báo có ngữ cảnh và hành động được kiểm soát**.

~~~mermaid
flowchart TD
    V[VPN gateway / AAA] --> P[Log collector / pipeline]
    I[IdP / MFA] --> P
    E[EDR / Endpoint management] --> P
    N[Firewall / DNS / IDS / App] --> P
    P --> Q[Normalize + quality checks]
    Q --> C[Correlation: user, device, session, IP, time]
    C --> B[Baseline / detection rules]
    B --> A[Alert + evidence]
    A --> SOC[SOC triage]
    SOC --> R[Response có phê duyệt]
    SOC --> T[Feedback: tune và regression tests]
    T --> B
~~~

### 6.1. Những nguyên tắc kỹ thuật

1. **Không chỉ lưu sự kiện đăng nhập:** cần thời điểm phiên thành lập, truy cập vùng nội bộ, hoạt động trong phiên và lý do đóng phiên khi dữ liệu có thể thu.
2. **Không gom mọi nguồn theo IP:** ưu tiên session ID và user/device ID đã xác thực; bổ sung gateway/VRF/time khi đối chiếu tunnel IP.
3. **Không dùng địa chỉ geo-IP như nguồn sự thật tuyệt đối:** mạng di động, VPN của ISP, CGNAT và tuyến đường ISP có thể khiến địa lý không chính xác.
4. **Phân biệt thời gian sự kiện và thời gian ingest:** log có thể đến trễ hoặc không đúng thứ tự.
5. **Ghi phiên bản rule và policy:** để điều tra một alert quá khứ, cần biết lúc đó policy VPN/MFA/firewall nào đang hiệu lực.
6. **Đánh giá độ tin cậy của bằng chứng:** một cột “unknown” hoặc “not available” có ý nghĩa khác với “mfa_result=false”.

### 6.2. Pipeline mất log cũng là một rủi ro

Một hệ thống không có alert có thể do **không có hành vi đáng ngờ**, nhưng cũng có thể do gateway không gửi log, collector ngừng chạy, field mapping bị lỗi hoặc SIEM bỏ event vì quá tải.

Theo dõi sức khỏe pipeline bằng các chỉ số:

- Thời gian từ event tới lúc có thể tìm kiếm trong SIEM.
- Số event theo nguồn/gateway và tỷ lệ parser error.
- Collector queue, lỗi kết nối, duplicate và dropped events.
- Độ phủ của các VPN node/site, không chỉ một gateway.
- Sự xuất hiện của event thử nghiệm/heartbeat được phép hoặc bản ghi vận hành có ý nghĩa.
- Khả năng lưu vết thời điểm gateway/reconnect bị lỗi và log đã bị thiếu.

Đừng đánh đồng **sensor health** với chất lượng detector: đủ log chưa chắc rule phát hiện đúng, và rule tốt cũng vô ích khi dữ liệu không tới.

## 7. Xây dựng baseline phiên VPN

**Baseline** mô tả hoạt động thường thấy hoặc được phép để phát hiện những thay đổi đáng xem xét. Nó có thể dựa trên ngưỡng cố định, thống kê theo nhóm, lịch sử riêng từng người dùng hoặc kết hợp tín hiệu rủi ro.

### 7.1. Đặc trưng nên quan sát

| Nhóm đặc trưng | Ví dụ baseline | Cần cân nhắc |
| --- | --- | --- |
| Lịch | Thời gian đăng nhập theo ngày/ca | Người dùng trực đêm, đi công tác và sự kiện khẩn |
| Thiết bị | Danh sách device ID được quản trị/chứng chỉ hợp lệ | Laptop thay mới, thiết bị BYOD được phép |
| Nguồn mạng | ASN/quốc gia/loại kết nối thường thấy | Roaming, CGNAT, proxy công ty, geo-IP sai |
| Tần suất | Số lần login fail/success, reconnect mỗi giờ | Chập chờn Wi-Fi, ứng dụng VPN tự reconnect |
| Đồng thời | Số phiên đang hoạt động mỗi user/device | Một người dùng laptop và điện thoại được phép |
| Thời lượng | Phân bố session duration và idle time | Always-on VPN so với phiên mở thủ công |
| Lưu lượng | Byte vào/ra, đích, cổng, khối lượng theo phiên | Backup, họp video, tải bản phát hành, công việc theo mùa |
| Quyền | Nhóm tài nguyên thường truy cập | Chuyển vai trò, hỗ trợ khẩn cấp, chính sách thay đổi |
| DNS | Resolver, nhóm tên miền nội bộ, số truy vấn | Split DNS, DoH/DoT, thay đổi ứng dụng |
| Hành vi thiết bị | Trạng thái MDM/EDR/posture | Thiếu telemetry không mặc định là thiết bị độc hại |

### 7.2. Baseline cá nhân và baseline theo nhóm

Nếu mỗi nhân viên có ít lịch sử đăng nhập, baseline cá nhân có thể không đủ dữ liệu. Có thể so sánh theo **nhóm vai trò** (helpdesk, kế toán, kỹ sư on-call) và theo **VPN profile** nhưng cần tránh “bình thường hóa” những hành vi nguy hiểm chỉ vì nhiều người cùng thực hiện.

Ngưỡng thường cần **chu kỳ giờ/ngày/tuần** và nhãn của các chiến dịch hợp lệ. Ví dụ job backup cuối tuần có thể tạo byte counters cao; nếu chỉ so với giờ làm việc thông thường, hệ thống dễ sinh nhiều false positive.

### 7.3. Baseline không phải allowlist vô điều kiện

Đừng cho phép một nguồn luôn vượt qua kiểm tra chỉ vì nó “xuất hiện thường xuyên”. Một endpoint quản trị có thể bị xâm phạm và tiếp tục hoạt động đều đặn. Nên sử dụng baseline để **ưu tiên điều tra**, kết hợp chính sách bắt buộc (MFA, quyền truy cập, thiết bị hợp lệ), thay vì dùng baseline để phủ định mọi tín hiệu khác.

## 8. Các nhóm bất thường cần phát hiện

### 8.1. Nhiều lần xác thực thất bại

**Dấu hiệu:** một tài khoản có nhiều lần đăng nhập thất bại trong khoảng ngắn, đặc biệt khi có nhiều vị trí nguồn, thử liên tục sau khóa tài khoản hoặc xuất hiện sự kiện MFA liên quan.

**Nguyên nhân hợp lệ có thể có:** người dùng quên mật khẩu, client đang lưu mật khẩu cũ, hệ thống đổi chính sách hoặc IdP gặp sự cố.

**Dữ liệu cần:** account, source IP/ASN, thiết bị, error category, user agent/client type, timestamp, IP thay đổi và số lần thành công tiếp theo.

**Cách cảnh báo:** kết hợp threshold và yếu tố bối cảnh; không mặc định “5 lần fail” luôn là tấn công trong mọi môi trường.

### 8.2. Password spraying theo nhiều tài khoản

**Dấu hiệu:** cùng một nguồn hoặc tập nguồn liên quan có các lượt thất bại trên **nhiều tài khoản**, trong khi mỗi tài khoản có thể chỉ bị thử một vài lần. Đây là mẫu hình khác với brute force tập trung vào một user.

**Điểm khó:** nhiều người sau cùng một IP doanh nghiệp/CGNAT có thể đồng loạt lỗi khi IdP hoặc máy chủ xác thực gặp vấn đề. Cần xét số tài khoản khác nhau, error category, phân phối thời gian, trạng thái IdP và tương quan nhiều nguồn.

### 8.3. MFA fatigue và yêu cầu yếu tố thứ hai bất thường

**Dấu hiệu:** hàng loạt thông báo MFA, nhiều yêu cầu bị từ chối/hết hạn, sau đó có một yêu cầu được chấp nhận trong hoàn cảnh bất thường; hoặc có lần xác thực thành công nhưng thiết bị, nguồn mạng và phiên không khớp lịch sử.

Không nên suy ra mọi lần bấm “Approve” đều chứng minh người dùng có chủ ý cho phép đăng nhập. Kỹ thuật **MFA fatigue**, lừa đảo thời gian thực và chiếm session token có thể làm thay đổi bối cảnh. Khi có khả năng, xem xét phương thức xác thực **chống phishing** và ràng buộc thiết bị/phiên theo hệ thống IdP hỗ trợ.

### 8.4. Đăng nhập từ vị trí/ASN bất thường

**Dấu hiệu:** user có một phiên thành công từ ASN/quốc gia chưa từng thấy, thiết bị không quản trị hoặc mạng được đánh giá rủi ro cao.

**Không nên dựa riêng vào quốc gia/IP reputation:** geo-IP là suy luận, dịch vụ VPN thương mại, proxy doanh nghiệp, mạng di động và ISP có thể thay đổi điểm thoát. Một số người có lịch đi công tác hoặc truy cập từ hạ tầng cloud được phê duyệt.

Một bất thường địa lý mạnh hơn khi **kèm thiết bị lạ, MFA không mong đợi, thay đổi profile truy cập và hành vi sau đăng nhập**.

### 8.5. Impossible travel

**Impossible travel** thường dùng khoảng cách giữa những lần đăng nhập để phát hiện trường hợp một người có vẻ xuất hiện ở hai địa điểm xa nhau trong một thời gian quá ngắn.

~~~text
Event A: user-lab-07, 09:00 UTC, nguồn định vị gần thành phố X
Event B: user-lab-07, 09:15 UTC, nguồn định vị gần thành phố Y
Distance X–Y: rất lớn so với khả năng di chuyển thực tế
~~~

Đây là **tín hiệu rủi ro**, không phải bằng chứng tự đủ: IP có thể đổi theo proxy, địa chỉ CGNAT, đường ra của ISP, mạng di động, VPN lồng hoặc geo-IP sai. Cần xác minh **sự kiện là login tương tác hay refresh token tự động**, thiết bị và các phiên hiện hữu trước khi coi là account compromise.

### 8.6. Phiên song song hoặc trùng danh tính

**Dấu hiệu:** nhiều VPN user session đồng thời từ các thiết bị khác nhau, một phiên được mở từ thiết bị quản trị và một phiên khác từ client chưa từng thấy, hoặc chính sách chỉ cho một phiên nhưng hệ thống ghi nhiều kết nối thành công.

**False positive phổ biến:** reconnect tạo session ID mới trước khi session cũ timeout, thay gateway HA, một người dùng cả laptop lẫn điện thoại, hoặc gateway đếm nhiều tunnel/SA dưới một user session.

Hãy tính **overlap thực** theo event time và **logical user session**; không chỉ đếm số record Start trong 10 phút.

### 8.7. Thời lượng phiên và idle time khác thường

Một phiên kéo dài bất thường có thể đáng chú ý nếu tài khoản đó thông thường chỉ sử dụng VPN trong vài giờ, hoặc được ghi “active” dù không có lưu lượng tương tác. Nhưng **always-on VPN** và thiết bị làm việc từ xa cả ngày có thể tạo phiên lâu hoàn toàn hợp lệ.

Kiểm tra các yếu tố: session timeout, idle timeout, gateway heartbeat, last activity và chính sách reauthentication. Dựa vào trường **duration** một mình để coi phiên dài là tấn công rất dễ tạo nhiễu.

### 8.8. Nhiều reconnect, thay IP hoặc thay gateway

Đổi Wi-Fi sang 4G/5G, chuyển vùng, NAT mapping thay đổi hoặc tunnel bị rớt có thể làm tăng reconnect. Một kẻ xấu cũng có thể liên tục mở lại phiên để thử né chính sách hoặc kiểm tra trạng thái gateway.

**Dữ liệu cần:** device ID, outer source, gateway node, reason code, VPN client version, link quality và khoảng thời gian. Phân nhóm theo **nguyên nhân kỹ thuật** trước khi kết luận bất thường an ninh.

### 8.9. Thiết bị chưa quản trị hoặc posture giảm

Nếu profile chỉ cho thiết bị đã đăng ký, một phiên được ghi nhận từ thiết bị **không có chứng chỉ/MDM/EDR theo yêu cầu** là tín hiệu nghiêm trọng. Tuy nhiên, thiếu dữ liệu posture vì mất kết nối với MDM khác với một kết luận thiết bị đã bị chiếm.

**Hành động phù hợp:** xác minh danh tính thiết bị, chính sách cập nhật, trạng thái cert và kết quả conditional access. Với trường hợp đáng ngờ, có thể yêu cầu xác thực lại hoặc giới hạn quyền theo cơ chế được phê duyệt.

### 8.10. Truy cập nội bộ ngoài mô hình quyền

**Dấu hiệu:** sau khi VPN thành công, một tài khoản chỉ dùng ứng dụng kế toán lại cố kết nối qua SSH/RDP đến vùng máy chủ quản trị, hoặc một profile chỉ có quyền web bắt đầu dò nhiều cổng.

**Dữ liệu cần:** assigned tunnel IP, session ID, user/group, firewall allow/deny, source/destination zone, port, lịch công việc và quyền được cấp.

Một số kết nối bị từ chối có thể đến từ phần mềm discovery, VPN client hoặc lỗi DNS. Nhưng chuỗi hành vi vượt quyền đặc biệt đáng chú ý khi **có thiết bị lạ hoặc các sự kiện xác thực đáng ngờ** ngay trước đó.

### 8.11. Dung lượng hoặc hướng truyền dữ liệu bất thường

**Dấu hiệu:** bytes out/in tăng mạnh so với vai trò, phiên có nhiều kết nối đến vùng nhạy cảm hoặc lượng dữ liệu truyền vào/ra không phù hợp thói quen.

**Điểm cần cẩn trọng:** cách gateway đặt tên **bytes_in/bytes_out** có thể tính theo hướng nhìn của **client** hoặc **gateway**. Trước khi gọi một spike là exfiltration, phải xác nhận hướng đếm, nơi giải mã, dữ liệu từ ứng dụng và những công việc hợp lệ như backup, cài đặt phần mềm hoặc xuất báo cáo.

Một bộ đếm byte cao **không tự chứng minh có đánh cắp dữ liệu**. Kết hợp log ứng dụng/file access, dữ liệu xuất ra và tài khoản có quyền truy cập.

### 8.12. DNS bất thường và dấu hiệu truy cập tên miền

Khi DNS đi qua resolver được giám sát, có thể phát hiện tên miền mới, thay đổi tần suất, truy vấn thất bại bất thường hoặc cố truy cập domain thuộc vùng không được phép.

**Giới hạn:** với **split tunneling**, DNS trên Internet hoặc các luồng ngoài route VPN có thể đi trực tiếp qua mạng người dùng. Client dùng **DoH/DoT** cũng có thể không hiện trong DNS log truyền thống. Không kết luận “không thấy DNS event” nghĩa là client không truy vấn.

### 8.13. Đăng nhập thành công sau chuỗi thất bại

Một trong những kịch bản có giá trị là nhiều failure rồi một success **cùng tài khoản**, đặc biệt khi thiết bị và source ASN khác baseline, sau đó có truy cập hệ thống nhạy cảm. Đây là quy tắc tương quan đa tầng mạnh hơn việc chỉ xem một event success bất thường.

Tuy vậy, user gõ nhầm mật khẩu vài lần rồi đăng nhập đúng cũng tạo mẫu này. Cần xét **số lượng, phân bố, nguồn, MFA, device và quyền truy cập sau đó**.

### 8.14. Hoạt động trong lúc tài khoản đã bị thu hồi

Nếu tài khoản bị vô hiệu hóa hoặc phiên bị thu hồi ở IdP nhưng gateway vẫn báo tunnel active, cần kiểm tra **cách hệ thống đồng bộ authorization, thời hạn session/token và cơ chế disconnect**. Một số VPN chỉ kiểm tra danh tính tại lúc đăng nhập rồi cho phiên tồn tại đến timeout nếu không có kết nối điều khiển thu hồi.

Đây có thể là **khoảng trống chính sách**, không tự là tấn công. Hãy thiết kế quy trình revoke/terminate chính xác với từng sản phẩm và thử kết quả trên lab.

## 9. Ma trận use case phát hiện bất thường

| Use case | Tín hiệu tối thiểu | Tín hiệu bổ sung tăng độ tin cậy | Đối tượng hành động |
| --- | --- | --- | --- |
| Brute force một tài khoản | Nhiều auth failure cùng user trong cửa sổ | ASN/source khác thường; thành công sau fail | SOC / IdP protection |
| Password spraying | Nhiều user khác nhau bị fail từ nguồn/tập nguồn | Mẫu thời gian/credential error tương tự | IdP/SOC |
| MFA fatigue | Nhiều challenge bị deny/timeout rồi approve | Device mới, sign-in risk cao, user xác nhận không yêu cầu | IdP/SOC |
| Impossible travel | Hai login nguồn địa lý xa gần nhau | Device mismatch, token context, geo-IP confidence | Analyst triage |
| Simultaneous sessions | Hai user sessions overlap trái policy | Device ID khác, không phải failover/reconnect | VPN admin / SOC |
| Unmanaged device | Session success với posture không hợp lệ | Cert/MDM thiếu, quyền được cấp vượt policy | IAM/NAC/VPN |
| Lateral movement | Nhiều deny tới vùng MGMT hoặc nhiều cổng nội bộ | Endpoint alert, ứng dụng không thuộc profile | Network SOC |
| Dữ liệu bất thường | Byte counters/flow tăng lớn so baseline | App export logs, data classification, thời gian | SOC/Data owner |
| Suspicious DNS | Truy vấn tên miền/loại truy vấn khác thường | Endpoint/IDS context, policy DNS | DNS/SOC |
| Revocation failure | User disabled nhưng tunnel active | Session còn truy cập tài nguyên | IAM/VPN owner |
| VPN gateway outage | Nhiều reconnect/drop gần nhau | Node health, ISP/WAN events | Network operations |

**Tách an ninh khỏi sự cố vận hành:** một đợt reconnect hàng loạt do gateway failover có thể rất bất thường về thống kê nhưng nên tạo **incident về availability**, không hàng nghìn cảnh báo nghi compromise.

## 10. Thiết kế rule phát hiện có ngữ cảnh

### 10.1. Ví dụ: Nhiều thất bại và một lần thành công

Giả mã dưới đây mô tả ý định một phép phát hiện, **không phải câu lệnh của SIEM cụ thể**:

~~~text
for each (user_id):
    failures = AUTH_FAILED events trong 10 phút
    successes = AUTH_SUCCESS events trong cùng cửa sổ và ngay sau đó

    if count(failures) >= 8 and count(successes) >= 1:
        alert(
          rule="VPN_AUTH_FAILURES_FOLLOWED_BY_SUCCESS",
          context={
            user_id,
            unique_source_ips,
            distinct_devices,
            mfa_results,
            vpn_session_ids,
            idp_incident_or_outage
          }
        )
~~~

**Ngưỡng 8 lần/10 phút chỉ là ví dụ trong phòng lab**, không phải chuẩn áp dụng cho mọi tổ chức. Rule thực tế phải xử lý event trễ, duplicate, mật khẩu cũ được client thử lại và dấu hiệu IdP outage.

### 10.2. Ví dụ: Password spraying

~~~text
group AUTH_FAILED by source_group trong 15 phút
where source_group có thể là IP hoặc tập nguồn được liên kết bằng bằng chứng

if count_distinct(user_id) >= 10
   and count(events) >= 12:
    alert candidate_password_spray

enrich: CGNAT/proxy classification, IdP error code,
        failed_auth_methods, account types, previous success
~~~

Ngưỡng là **ví dụ**. Một địa chỉ NAT chứa hàng trăm nhân viên có thể tạo nhiều lỗi đăng nhập khi chính sách IdP thay đổi. Ngược lại, nguồn phân tán có thể không bị phát hiện bằng một khóa IP đơn lẻ; cần các trường bối cảnh phù hợp và bảo vệ danh tính.

### 10.3. Ví dụ: Truy cập trái profile sau đăng nhập bất thường

~~~text
Step A: tìm VPN_SESSION_ESTABLISHED với:
        device_posture không hợp lệ
        OR device_id mới so với user
        OR sign_in_risk được IdP đánh giá cao

Step B: ánh xạ tunnel_ip + session time + gateway/context
        tới firewall / application logs

Step C: phát hiện truy cập MGMT, RDP/SSH hoặc
        dữ liệu nhạy cảm ngoài quyền đã được duyệt

Alert nếu có bằng chứng A và C trong cùng logical session.
~~~

Điều kiện **thiết bị mới** không tự đủ kết luận xâm nhập; có thể là laptop thay thế. Thay vì tự động block mọi trường hợp, triage cần xem bằng chứng, mức nhạy cảm tài nguyên và thiết bị được phê duyệt.

### 10.4. Ví dụ: Phiên chồng lấn

~~~text
for sessions with same user_id:
    compute overlap between logical session start/end
    if overlapping sessions trên hai device_id khác nhau
       and policy chỉ cho phép một thiết bị:
        alert "CONCURRENT_SESSION_POLICY_VIOLATION"

exclude only verified reconnect / gateway HA transitions
retain evidence of exclusion reason and duration
~~~

Không gom phiên theo **IP public khác nhau** rồi cho rằng thiết bị chắc chắn khác: một điện thoại có thể đổi kết nối mạng, hoặc một client dùng nhiều outer endpoint. Phải dùng device/session identity có thể kiểm chứng.

### 10.5. Chọn mức cảnh báo và ưu tiên

| Mức ưu tiên minh họa | Bối cảnh | Phản ứng đề xuất |
| --- | --- | --- |
| **Thông tin** | Reconnect tăng theo sự kiện gateway failover đã xác minh | Theo dõi availability, không gửi nhiều alert bảo mật trùng |
| **Thấp / trung bình** | Đăng nhập từ ASN mới trên thiết bị hợp lệ, MFA bình thường | Enrich và xem lịch di chuyển/thay đổi |
| **Trung bình / cao** | Nhiều lần fail, success từ thiết bị lạ, MFA bất thường | Điều tra nhanh, xác minh chủ tài khoản |
| **Cao** | Session của tài khoản bị thu hồi vẫn truy cập vùng nhạy cảm | Kích hoạt quy trình chặn/thu hồi được phê duyệt |
| **Nghiêm trọng** | Đăng nhập nghi chiếm đoạt + hành vi trái quyền + dấu vết endpoint/ứng dụng | Điều phối incident response và bảo toàn bằng chứng |

Các mức chỉ là **gợi ý thiết kế**, phải căn cứ thang severity của tổ chức. Rule nên tạo **một incident có các bằng chứng liên quan**, tránh alert storm cho mỗi packet hoặc mỗi reconnect thuộc cùng một chuỗi.

## 11. Precision, false positive, false negative và coverage

Các cảnh báo VPN thường chứa tín hiệu yếu hoặc không đầy đủ. Cần đánh giá quality trên các sự kiện đã có nhãn:

- **True positive (TP):** phát hiện đúng trường hợp bất thường thuộc use case đã định nghĩa.
- **False positive (FP):** cảnh báo khi hành vi thực tế được xác minh là hợp lệ theo use case.
- **False negative (FN):** hành vi cần phát hiện có xảy ra, nhưng detector không báo.
- **True negative (TN):** mẫu được xác minh là bình thường và detector không báo.

~~~text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
FPR       = FP / (FP + TN)
FNR       = FN / (TP + FN)
~~~

**Không thể tính FNR production chính xác chỉ từ số alert:** các trường hợp bị bỏ sót không hiện trên dashboard và cần kiểm thử có nhãn, incident review hoặc phương pháp lấy mẫu phù hợp.

### 11.1. False positive thường gặp

| Tín hiệu gây báo nhầm | Tình huống hợp lệ | Hướng giảm nhiễu |
| --- | --- | --- |
| Impossible travel | Corporate proxy / cloud egress / mạng di động | Xác minh device, IdP token context và chất lượng geo-IP |
| Concurrent sessions | Client reconnect hoặc gateway HA | Gộp logical session và khoảng overlap |
| Nhiều auth failure | User đổi mật khẩu, client lưu credential cũ | Phân tích error code, source và IdP outage |
| Nhiều bytes truyền | Backup, job đồng bộ, update hệ điều hành | Baseline theo nhóm ứng dụng, session và lịch thay đổi |
| Đăng nhập ngoài giờ | On-call, nhân viên làm ca, đi công tác | Role/schedule context và bằng chứng chuyển lịch |
| Device mới | Laptop thay máy hoặc thiết bị được cấp phép | MDM enrollment, owner, chứng chỉ và change record |

### 11.2. False negative thường gặp

- Gateway không ghi hoặc không chuyển event về collector.
- Chỉ theo dõi login mà không xem **lưu lượng/tài nguyên trong phiên**.
- Tunnel split-tunnel khiến traffic ngoài phạm vi VPN không được nhìn thấy.
- Attacker dùng **account/device có thật** và hoạt động gần baseline.
- Rule chỉ nhóm theo một IP và bỏ lỡ password spray phân tán.
- Mapping tunnel IP không tính thời gian nên gắn sai phiên.
- Sensor đặt bên ngoài phần mã hóa không nhìn được nội dung ứng dụng.
- Suppression/allowlist quá rộng hoặc rule bị vô hiệu hóa sau khi tăng false positive.

**Coverage** phải được báo riêng cho VPN gateway/site, loại client, IPv4/IPv6, split/full tunnel, IdP/MFA và ứng dụng nhạy cảm. Không có một rule nào đủ phát hiện mọi hành vi xấu nếu thiếu điểm quan sát.

## 12. Split tunneling, full tunneling và giới hạn quan sát

### 12.1. Full tunnel

Với **full-tunnel VPN**, thiết bị được định tuyến phần lớn hoặc toàn bộ lưu lượng IP qua VPN gateway theo chính sách. Điều này có thể tập trung kiểm soát egress, DNS và quan sát ở hạ tầng doanh nghiệp, nhưng cũng làm tăng tải gateway/băng thông và không mặc nhiên cung cấp nội dung HTTP đang mã hóa.

**Không suy ra** full tunnel luôn thực sự bao phủ mọi traffic nếu client có các interface, cấu hình ứng dụng hoặc ngoại lệ đường đi. Cần kiểm tra route table, DNS và policy hiệu lực trên thiết bị.

### 12.2. Split tunnel

Với **split tunneling**, chỉ một số prefix hoặc ứng dụng đi qua VPN, lưu lượng Internet khác có thể đi trực tiếp từ client. Khi đó:

- VPN gateway có thể chỉ thấy **luồng vào ứng dụng/vùng nội bộ**.
- DNS có thể được chia theo tên miền hoặc resolver, khiến một số truy vấn không qua hạ tầng doanh nghiệp.
- Một hành vi tải dữ liệu ra Internet trực tiếp từ endpoint có thể không xuất hiện trong log gateway.
- Điều tra phải kết hợp endpoint/EDR, secure web gateway hoặc log khác nếu tổ chức có quyền thu thập.

Không kết luận split tunnel “luôn nguy hiểm” hoặc full tunnel “luôn an toàn”. Cần quyết định dựa trên use case, thiết bị, network exposure, hiệu năng, chính sách DNS, threat model và các điểm kiểm soát khác.

### 12.3. IPv6 và DNS có thể tạo đường bỏ sót

Một thiết kế chỉ route IPv4 vào VPN nhưng vẫn cho IPv6 trực tiếp có thể tạo khoảng trống so với kỳ vọng. Trong dual-stack, kiểm tra:

1. IPv4/IPv6 route table và interface hiện hữu.
2. Resolver DNS theo ứng dụng/domain, DoH/DoT nếu dùng.
3. Firewall cho IPv4 và IPv6 của nguồn VPN.
4. Policy đối với lưu lượng nội bộ không đi qua gateway tập trung.
5. Cách telemetry ghi nhận tunnel IPv4, IPv6 và các luồng được cấp quyền.

**DNS leak** hoặc traffic ngoài VPN không thể được kết luận chỉ từ một lần không thấy query ở resolver nội bộ; cần thu thập bằng chứng từ endpoint/route và giải pháp thực thi tương ứng.

## 13. Triage: Điều tra một cảnh báo VPN theo bằng chứng

### 13.1. Quy trình ưu tiên

1. **Xác minh nguồn và thời điểm:** rule ID, severity, gateway, log source, timestamp, thứ tự các sự kiện và tình trạng log pipeline.
2. **Xác minh danh tính:** user ID, nhóm quyền, IdP event, MFA result, authentication method và risk signals.
3. **Xác minh thiết bị:** device ID, posture, chứng chỉ/MDM, OS và các thay đổi gần đây.
4. **Xác minh session:** logical session ID, external IP/ASN, tunnel IP, gateway/VRF, thời gian bắt đầu/kết thúc, reconnect và policy version.
5. **Xác minh hành vi trong phiên:** các đích nội bộ, firewall allow/deny, DNS, ứng dụng, EDR và lượng dữ liệu.
6. **Đối chiếu bối cảnh hợp lệ:** lịch công tác/ca trực, ticket thay máy, đổi mật khẩu, gateway failover, change window hoặc kiểm thử đã phê duyệt.
7. **Phân loại và quyết định:** true positive, false positive, chưa xác định hoặc sự cố khả dụng; nêu bằng chứng và phần chưa biết.
8. **Phản ứng tương xứng:** theo runbook và quyền được cấp, có rollback, phối hợp với user/owner và bảo toàn dữ liệu điều tra.

### 13.2. Ví dụ điều tra

Một alert ban đầu ghi:

~~~text
09:00  AUTH_FAILED    user-lab-07  source=198.51.100.45
09:01  AUTH_FAILED    user-lab-07  source=198.51.100.45
09:03  MFA_DENIED     user-lab-07  source=198.51.100.45
09:05  AUTH_SUCCESS   user-lab-07  device=unknown-lab-02
09:06  VPN_SESSION_ESTABLISHED session=lab-s-105
09:08  FIREWALL_DENY  tunnel_ip=192.0.2.105 dst_zone=MGMT tcp/22
~~~

Các sự kiện và địa chỉ ở đây **hoàn toàn giả lập**. Chuỗi này đủ để **ưu tiên điều tra**, nhưng chưa đủ chứng minh một tài khoản đã bị chiếm. Cần xác nhận liệu user vừa đổi laptop, có yêu cầu MFA hợp lệ hay không, IP tunnel thuộc đúng phiên nào, và dịch vụ quản trị có thuộc công việc được phê duyệt không.

### 13.3. Nhãn kết luận và mức độ tin cậy

| Nhãn | Khi nào dùng | Ví dụ bằng chứng cần |
| --- | --- | --- |
| **Confirmed suspicious / TP** | Hoạt động đúng use case nguy hiểm và được xác minh | User phủ nhận đăng nhập, endpoint compromise, truy cập trái phép đã xác nhận |
| **Benign / FP** | Hoạt động hợp lệ đã được kiểm chứng | Ticket thay thiết bị, failover, ca trực hợp lệ, app tạo retry |
| **Undetermined** | Chưa có đủ bằng chứng kết luận | Thiếu IdP/endpoint log, IP chưa ánh xạ chắc với phiên |
| **Operational incident** | Sự kiện thực nhưng chủ yếu là lỗi khả dụng/cấu hình | Gateway HA loop, IdP outage hoặc chính sách deploy lỗi |

Đừng ép toàn bộ sự kiện **Undetermined** thành FP để làm dashboard trông ít báo sai. Cần ghi rõ độ phủ dữ liệu và công việc xác minh tiếp theo.

## 14. Phản ứng sự cố và hạn chế tác động

**Mục tiêu:** ngăn hành vi không được phép mà **không vô tình ngắt toàn bộ truy cập từ xa** hoặc xóa bằng chứng khi chưa có kế hoạch.

### 14.1. Các hành động theo mức tin cậy

| Mức bằng chứng | Hành động có thể phù hợp | Điều cần xác minh |
| --- | --- | --- |
| Chỉ có một yếu tố bất thường yếu | Enrich, mở case, theo dõi hoặc yêu cầu xác minh mềm | Lịch công tác, IP/geo, thiết bị, chính sách |
| Nhiều lần fail/MFA abuse rõ rệt | Bảo vệ đăng nhập, xác minh user, tăng giám sát | Có bị IdP outage hoặc retry loop không? |
| Phiên có rủi ro cao, vi phạm policy | Thu hẹp quyền, yêu cầu reauthentication/MFA hoặc revoke session theo runbook | Hệ thống nào thật sự thực thi và khi nào hết quyền? |
| Có bằng chứng tài khoản bị chiếm | Vô hiệu hóa/đặt lại thông tin xác thực, revoke token/phiên, điều tra endpoint | Còn token, cert hoặc tunnel khác sống không? |
| Có dấu hiệu dữ liệu bị truy cập trái phép | Bảo toàn log, phối hợp IR/data owner, kiểm tra scope ứng dụng | Dữ liệu nào được đọc, lúc nào, chủ thể nào? |
| Gateway/IdP lỗi diện rộng | Xử lý availability, failover/rollback theo kế hoạch | Không nhầm lỗi hệ thống với tấn công quy mô lớn |

**Thu hồi tài khoản ở IdP không luôn tự ngắt mọi tunnel đang hoạt động.** Tùy sản phẩm, phải gọi chức năng disconnect session trên gateway, revoke token/credentials hoặc thay đổi policy với cơ chế đẩy hiệu lực. Cần kiểm tra xác nhận thực tế: **phiên đã đóng, không tạo được phiên mới và đường truy cập nội bộ đã bị chặn**.

### 14.2. Bảo toàn bằng chứng

Trước khi thay đổi nếu điều kiện an toàn cho phép:

- Ghi lại user/device/session/gateway IDs và các timestamp theo UTC.
- Lưu trữ các event liên quan từ VPN, IdP/MFA, firewall, ứng dụng và endpoint theo quyền được cấp.
- Giữ phiên bản rule, trạng thái policy, thông tin cấp phát tunnel IP, route và phạm vi log.
- Giới hạn truy cập bằng chứng, tránh sao chép bí mật chưa cần thiết.
- Ghi rõ ai ra quyết định và hành động thực hiện theo ticket/incident.

Khi đang có nguy cơ cấp bách, tổ chức có thể cần **ngăn chặn ngay** theo playbook. Dù vậy, hãy bảo đảm hành động và bằng chứng được ghi nhận phù hợp, không tự ý xoá log hoặc thay đổi cấu hình ngoài phạm vi phê duyệt.

### 14.3. Sau sự cố

Sau khi ổn định:

1. Xác minh nguyên nhân: credential theft, MFA abuse, endpoint compromise, cấu hình VPN hay lỗi rule.
2. Kiểm tra các phiên khác của cùng user, device và các tài khoản liên quan trong giới hạn điều tra.
3. Rà soát quyền VPN, group membership và phân đoạn truy cập.
4. Điều chỉnh rule phát hiện, giữ bài kiểm thử hồi quy cho tình huống đã xảy ra.
5. Phân biệt chỉ số **time to detect, time to triage và time to contain** để xác định điểm chậm.
6. Cập nhật runbook và tài liệu hỗ trợ người dùng, tránh tái diễn lỗi vận hành.

## 15. Triển khai theo dõi VPN theo từng bước

### Bước 1 — Xác định use case và phạm vi

Ghi rõ loại remote-access VPN, gateway/site, giao thức đang sử dụng, IdP/MFA, nhóm tài khoản, các VPN profile và tài nguyên nội bộ có độ nhạy cao. Chọn use case cần ưu tiên theo threat model, ví dụ chiếm đoạt tài khoản và truy cập trái quyền.

### Bước 2 — Kiểm kê nguồn log

Đối chiếu **khả năng ghi log thực tế** của gateway, IdP, RADIUS/AAA, firewall/ISFW, DNS, endpoint/EDR và ứng dụng. Xác định dữ liệu nào **không có** trong từng hệ thống để tránh viết detector không thể triển khai.

### Bước 3 — Chuẩn hóa session ID và thời gian

Thiết kế mapping user–device–session–tunnel IP, phân biệt outer IP và address trong tunnel, ghi timezone/UTC, trạng thái reconnection và phiên bản cấu hình. Thử với **IP tunnel được tái sử dụng** và **cùng user trên hai thiết bị**.

### Bước 4 — Xây baseline có phân nhóm

Theo vai trò, profile, gateway/site, nhóm ứng dụng, giờ/ca và môi trường mạng. Đánh dấu các hoạt động được phép có thể gây nhiễu như on-call, thay máy, reset mật khẩu, migration và backup.

### Bước 5 — Tạo detection rule theo độ ưu tiên

Bắt đầu với use case có giá trị và nhiều bằng chứng: login failures kèm success lạ, MFA bất thường, phiên truy cập ngoài quyền, user disabled nhưng tunnel còn hoạt động. Mỗi rule có owner, dữ liệu đầu vào, logic, ngưỡng, suppression giới hạn và điều kiện nâng severity.

### Bước 6 — Chạy ở chế độ quan sát

Theo dõi số alert, thời gian triage, TP/FP/undetermined và độ thiếu dữ liệu. Đối chiếu các bản ghi với user/team được phép, tránh phản ứng tự động từ một yếu tố yếu như geo-IP.

### Bước 7 — Kiểm thử hồi quy và rollout

Thử các kịch bản có nhãn ở lab/staging (failed login theo ngưỡng nhỏ, reconnect, token revoke, client roaming, tunnel IP reuse, session overlap, deny tới MGMT). Bật hành động chặn tự động chỉ với trường hợp đủ chắc chắn, có playbook và rollback.

### Bước 8 — Vận hành liên tục

Theo dõi log coverage, gateway health, IdP status, parser failures, sự thay đổi profile/policy, số incident và feedback của analyst. Định kỳ kiểm tra rule bị tắt, suppression quá rộng, tài khoản không còn sử dụng, thiết bị không compliant và session còn treo.

## 16. Chỉ số vận hành và chất lượng phát hiện

| Chỉ số | Ý nghĩa | Lưu ý khi diễn giải |
| --- | --- | --- |
| Login success/failure theo user/gateway | Nhận biết lỗi và bất thường xác thực | Tỷ lệ fail tăng có thể do IdP outage |
| Số logical active sessions | Ước lượng số phiên người dùng thực sự | Không đếm SA/transport connection như user |
| Tỷ lệ session có device ID đáng tin | Độ phủ tương quan thiết bị | BYOD hoặc vendor có thể không cung cấp |
| Session start/end completeness | Chất lượng vòng đời | Stop event có thể mất/trễ |
| Failed MFA / denied challenges | Giám sát quy trình xác thực mạnh | Người dùng nhấn từ chối có thể do prompt không mong muốn |
| Unique sources / unusual ASN | Theo dõi mạng nguồn | CGNAT/geo-IP và roaming tạo sai lệch |
| VPN → MGMT/DATA deny | Xác minh segmentation và tìm vượt quyền | Deny không tự chứng minh tấn công |
| Bytes/session và destinations/session | Phát hiện hoạt động lệch baseline | Cần xác định hướng byte, split tunnel và nghiệp vụ |
| Log delivery latency / drop rate | Độ tin cậy của telemetry | Không có alert có thể là lỗi thu thập |
| Alert TP/FP/undetermined | Tính hữu ích với SOC | Chỉ so sánh khi nhãn và phương pháp xác minh ổn định |
| MTTD / time to triage / containment | Hiệu quả vận hành sự cố | Phải định nghĩa điểm bắt đầu/kết thúc rõ |
| Policy/session revocation success | Khả năng thực thi thu hồi quyền | Không chỉ đếm lệnh revoke; kiểm tra tunnel và truy cập thực tế |

### 16.1. Hai con số dễ gây hiểu nhầm

**Số lượt đăng nhập thành công** không phải số người đang kết nối: một user có thể login nhiều lần vì reconnect hoặc trên nhiều thiết bị. Tương tự, **số IP khác nhau** không phải số thiết bị: CGNAT gộp nhiều người vào một địa chỉ, và cùng một thiết bị có thể dùng nhiều IP nguồn theo thời gian.

### 16.2. Privacy và data minimization

Log VPN chứa thông tin có thể liên quan tới người dùng: thời điểm đăng nhập, IP nguồn, thiết bị, nhóm quyền, hostname hoặc tên miền truy vấn. Do đó cần:

- Chỉ thu thập dữ liệu phục vụ mục tiêu an ninh/vận hành đã xác định.
- Giới hạn người có quyền xem và tìm kiếm lịch sử phiên; ghi audit việc truy cập log.
- Đặt retention và chính sách xóa dựa trên nghĩa vụ pháp lý và chính sách tổ chức.
- Tránh ghi token/session cookie, OTP, private key, password hoặc payload ứng dụng không cần thiết.
- Ẩn danh/pseudonymize trong dashboard tổng hợp khi phù hợp mà vẫn giữ khả năng điều tra có kiểm soát.
- Có quy trình truy cập và chia sẻ bằng chứng sự cố an toàn.

Không đánh đổi quyền riêng tư lấy việc lưu toàn bộ nội dung hoạt động của khách hoặc nhân viên một cách không có mục đích và quyền hạn rõ ràng.

## 17. Bài thực hành trong lab: Quan sát phiên và tương quan log

**Môi trường:** một VPN gateway hoặc simulator được phép dùng, hai user giả lập, hai thiết bị lab, một ứng dụng web và một endpoint MGMT mô phỏng. Tạo dữ liệu kiểm thử không chứa bí mật, không thử đăng nhập trái phép hoặc dò quét hệ thống thật.

### 17.1. Kịch bản kiểm thử

| Bài thử | Kết quả mong đợi |
| --- | --- |
| Một lần đăng nhập hợp lệ với MFA | Có event xác thực và session established với đúng user/device |
| Một lần nhập sai thông tin đăng nhập | Có failure đúng mã nguyên nhân, không tạo tunnel hợp lệ |
| Một đợt fail nhỏ rồi success | Detector nhận diện chuỗi theo ngưỡng lab, không gửi nhiều alert trùng |
| Client đổi Wi-Fi sang mạng di động | Reconnect được ghi, không báo compromise chỉ dựa trên IP đổi |
| Hai thiết bị dùng cùng user | Nhận diện đúng logical sessions và chính sách đồng thời |
| Gửi yêu cầu tới MGMT không được phép | Firewall ghi deny và SIEM ánh xạ đúng session tại thời điểm đó |
| Tunnel IP được cấp lại cho user khác | Flow ở phiên sau không bị gán nhầm cho user trước |
| User bị revoke | Tunnel hiện tại bị đóng/giới hạn đúng cách theo sản phẩm, không tạo được session mới |
| Dùng split tunnel | Xác định traffic nào đi trong và ngoài tunnel |
| Log collector ngừng trong lab | Health alert xuất hiện, không bị hiểu là “không có bất thường” |

### 17.2. Quan sát đường đi ở Windows và Linux

Các lệnh sau chủ yếu **chỉ đọc** trên endpoint có quyền quản trị:

~~~powershell
# Windows: xem interface, IP/gateway và bảng định tuyến.
Get-NetIPConfiguration
Get-NetRoute | Sort-Object DestinationPrefix

# Xem VPN profile trong Windows nếu profile được quản lý bởi cơ chế này.
# Không phải mọi sản phẩm SSL/IPsec VPN đều xuất hiện ở đây.
Get-VpnConnection
~~~

~~~bash
# Linux: xem interface và route IPv4/IPv6.
ip -br address
ip -4 route
ip -6 route

# Nếu NetworkManager quản lý VPN, xem connection đang hoạt động.
nmcli connection show --active
~~~

Các lệnh không chứng minh session được IdP cấp quyền như thế nào hay mọi packet đều đi qua tunnel. Cần đối chiếu log của VPN gateway, policy, route thực tế và các luồng kiểm tra được phê duyệt.

### 17.3. Bộ log JSON Lines giả lập

Giả sử lab chuẩn bị file **vpn-lab-events.jsonl** với một JSON object trên mỗi dòng:

~~~json
{"ts":"2026-11-28T09:00:00Z","event":"auth_failed","user":"user-lab-07","src":"198.51.100.45"}
{"ts":"2026-11-28T09:01:00Z","event":"auth_failed","user":"user-lab-07","src":"198.51.100.45"}
{"ts":"2026-11-28T09:05:00Z","event":"session_started","user":"user-lab-07","session":"lab-s-105","tunnel_ip":"192.0.2.105"}
{"ts":"2026-11-28T09:15:00Z","event":"session_ended","user":"user-lab-07","session":"lab-s-105","tunnel_ip":"192.0.2.105"}
{"ts":"2026-11-28T10:30:00Z","event":"session_started","user":"user-lab-08","session":"lab-s-106","tunnel_ip":"192.0.2.105"}
~~~

Đây là **dữ liệu giả lập** để dạy cách đọc và đối chiếu. Nó không phải log thật từ nhà cung cấp VPN. Một số thao tác phân tích an toàn khi file đã có sẵn:

~~~bash
# Với jq, lọc những sự kiện có loại session_started.
jq 'select(.event == "session_started") |
    {ts, user, session, tunnel_ip}' vpn-lab-events.jsonl

# Đếm các event auth_failed theo username (không phải TP/FP).
jq -r 'select(.event == "auth_failed") | .user' vpn-lab-events.jsonl |
  sort | uniq -c | sort -nr
~~~

Kết quả count chỉ nói số event có trong file. **Không phải bằng chứng brute force**, không tự xác nhận số người dùng thật hay kết luận bảo mật. Muốn tính TP/FP phải có ground truth từ bài thử hoặc quá trình điều tra.

### 17.4. Phân tích bài toán tunnel IP reuse

Với file giả lập:

- 09:05–09:15: IP **192.0.2.105** thuộc session **lab-s-105**, user **user-lab-07**.
- Từ 10:30: IP **192.0.2.105** có thể thuộc session **lab-s-106**, user **user-lab-08**.

Một firewall flow lúc **10:40** không được gán cho user-lab-07 chỉ vì từng thấy IP đó vào buổi sáng. Tương quan cần dùng **thời gian hiệu lực, gateway/zone và session**, không lookup IP hiện tại.

### 17.5. Tiêu chí nghiệm thu

1. Session start/end và IdP events có thể đối chiếu trong phạm vi thời gian xác định.
2. Các route và tunnel IP/IPv6 được cấp đúng profile.
3. Alert xác thực thất bại không bị nhầm với sự cố IdP.
4. Roaming/reconnect và session overlap được nhận diện đúng loại.
5. Firewall deny từ một VPN user được ánh xạ tới đúng session và user.
6. Split/full tunnel và đường DNS được xác minh với những dữ liệu thực sự quan sát được.
7. Hành động revoke được xác nhận ở **gateway và ứng dụng/đường truy cập**, không chỉ trên giao diện IdP.
8. Log không chứa credential hoặc thông tin nhạy cảm vượt nhu cầu kiểm thử.

## 18. Tình huống tổng hợp: Phiên VPN hợp lệ nhưng hoạt động đáng ngờ

**Bối cảnh:** user **user-lab-07** là nhân viên kế toán, thường sử dụng VPN trong giờ làm việc trên laptop quản trị. Một ngày lab ghi các sự kiện giả định:

| Thời điểm UTC | Sự kiện | Dữ kiện |
| --- | --- | --- |
| 08:55 | AUTH_SUCCESS | Thiết bị đã quản trị, MFA hợp lệ |
| 09:00 | SESSION_STARTED | Tunnel IP 192.0.2.105; profile accounting |
| 09:20 | SESSION_ENDED | Người dùng ngắt VPN |
| 10:05 | AUTH_FAILED nhiều lần | Một số nguồn IP lạ |
| 10:08 | MFA_DENIED | Có yêu cầu MFA không được chấp nhận |
| 10:10 | AUTH_SUCCESS | Thiết bị chưa từng thấy, nguồn ASN lạ |
| 10:11 | SESSION_STARTED | Một gateway khác, tunnel IP 192.0.2.145 |
| 10:13 | FIREWALL_DENY | Thử kết nối vùng MGMT qua SSH |
| 10:17 | APP_ACCESS | Có truy cập ứng dụng tài chính được phép |
| 10:25 | BYTES_OUT tăng | Theo cách đo của gateway trong ví dụ |

### 18.1. Câu hỏi phân tích

1. Sự kiện nào chỉ phản ánh **xác thực**, sự kiện nào chứng minh **tunnel đã được thiết lập**?
2. Tại sao AUTH_SUCCESS trên thiết bị mới chưa đủ kết luận tài khoản bị xâm phạm?
3. Sự kết hợp nào khiến cảnh báo 10:10 cần ưu tiên hơn một login từ ASN lạ đơn lẻ?
4. Nếu hệ thống báo **impossible travel**, cần xác minh gì trước khi đưa ra kết luận?
5. Làm sao nối FIREWALL_DENY lúc 10:13 với **đúng session** khi tunnel IP có thể được tái sử dụng?
6. Firewall deny đến MGMT đã chứng minh **lateral movement thành công** chưa?
7. BYTES_OUT tăng đã chứng minh **exfiltration** chưa, và vì sao?
8. Nếu người dùng xác nhận không thực hiện MFA lúc 10:08, SOC cần làm gì tiếp?
9. Nếu IdP vô hiệu hóa account nhưng VPN gateway còn phiên active, vấn đề kiến trúc nào cần kiểm tra?
10. Những log nào có thể bị thiếu nếu VPN đang dùng split tunneling?

### 18.2. Gợi ý giải

**(1)** AUTH_SUCCESS xác thực ở một bước; SESSION_STARTED ghi tunnel được tạo theo semantics của gateway. **(2)** Có thể là máy mới cấp hoặc thay thế; cần xác minh chủ sở hữu, MDM, MFA và bối cảnh. **(3)** Failures + MFA denied + success từ thiết bị lạ + truy cập trái quyền tạo chuỗi tín hiệu liên quan. **(4)** Geo-IP, thời gian, proxy/CGNAT, device ID, token context và session cũ. **(5)** Dùng session ID/gateway/zone và time-range mapping của tunnel IP. **(6)** Không; deny chỉ cho biết một kết nối bị chặn theo policy. **(7)** Không; phải xác định hướng byte và dữ liệu ứng dụng thực. **(8)** Xác minh account compromise theo runbook, bảo vệ xác thực và xem xét thu hồi phiên/quyền với phê duyệt. **(9)** Khả năng đẩy revocation, reauthentication và timeout của gateway. **(10)** Internet/DNS traffic đi trực tiếp từ endpoint có thể không xuất hiện tại VPN gateway.

## 19. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “VPN được mã hóa thì không cần giám sát nữa.” | Vẫn cần quan sát xác thực, phiên, cấp quyền và hành vi sau giải mã ở điểm phù hợp. |
| “Auth success là đã có tunnel và quyền truy cập mọi mạng nội bộ.” | Xác thực, thiết lập tunnel và authorization là các giai đoạn khác nhau. |
| “Một RADIUS Start không có Stop nghĩa là attacker giữ phiên.” | Stop có thể bị mất/trễ; cần session table và timeout. |
| “Số IKE CHILD_SA bằng số người dùng VPN.” | SA/rekey không luôn tương đương logical user session. |
| “WireGuard handshake là người dùng đã MFA thành công.” | Peer handshake không tự là chứng cứ định danh/MFA; phụ thuộc hệ thống điều khiển. |
| “Public IP thay đổi nghĩa là account đã bị chiếm.” | Roaming, CGNAT và proxy thường làm IP biến động. |
| “Một quốc gia lạ trong geo-IP đủ để block chắc chắn.” | Geo-IP có sai số; cần kiểm tra thiết bị, nguồn và ngữ cảnh. |
| “Hai phiên cùng user chắc chắn là gian lận.” | Có thể là reconnect hoặc nhiều thiết bị hợp lệ theo policy. |
| “Không thấy DNS trong log VPN nghĩa là client không phân giải tên.” | Split tunnel, resolver khác hoặc DNS mã hóa có thể tạo điểm mù. |
| “VPN gateway thấy mọi nội dung HTTPS.” | Tunnel kết thúc không tự giải mã TLS của ứng dụng bên trong. |
| “Một flow bị deny chứng minh có tấn công.” | Deny có thể do policy, discovery hoặc lỗi client; phải triage. |
| “Nhiều bytes out là đánh cắp dữ liệu.” | Cần xác minh hướng byte, hoạt động nghiệp vụ và application logs. |
| “Vô hiệu hóa account luôn ngắt ngay phiên VPN.” | Phụ thuộc revocation, token, timeout và cơ chế disconnect của gateway. |
| “Không có alert nghĩa là không có bất thường.” | Có thể thiếu log, sensor coverage hoặc rule phát hiện. |
| “Chỉ cần xem IP tunnel hiện tại để truy vết sự kiện cũ.” | IP được tái sử dụng; phải đối chiếu khoảng thời gian và ngữ cảnh mạng. |

## 20. Tổng kết

**Theo dõi phiên VPN** phải đi xa hơn việc đếm đăng nhập thành công. Một quy trình tốt liên kết **người dùng, thiết bị, nguồn kết nối, kết quả IdP/MFA, session/tunnel ID, IP được cấp, VPN policy, tài nguyên nội bộ đã truy cập và thời điểm phiên thay đổi/kết thúc**. Đó là cơ sở để phân biệt sự cố vận hành với hành vi đáng ngờ và xác định được những trường hợp cần phản ứng.

Các use case có giá trị gồm **password spraying, MFA abuse, thiết bị mới không phù hợp policy, impossible travel có ngữ cảnh, session chồng lấn ngoài quyền, truy cập vượt phân đoạn và biến động dữ liệu bất thường**. Mỗi tín hiệu có thể bị ảnh hưởng bởi roaming, split tunneling, CGNAT, DNS mã hóa và log trễ; không được tự kết luận từ một trường dữ liệu duy nhất.

Trong **SECURITY_NETWORK_SECURITY**, giám sát VPN là lớp kết nối **xác thực từ xa với firewall, phân đoạn, IDS/IPS, DNS, bảo mật endpoint và điều tra sự cố**. Thành công được đo bằng **độ phủ log, chất lượng tương quan, tỷ lệ cảnh báo có ích, khả năng thu hồi phiên thực sự và tác động tới người dùng hợp lệ**, với quyền riêng tư và quản trị thay đổi được bảo vệ.

### Tài liệu tham khảo

- **NIST SP 800-46 Rev. 2 — Guide to Enterprise Telework, Remote Access, and Bring Your Own Device (BYOD) Security:** rủi ro truy cập từ xa và bảo vệ thiết bị.
- **NIST SP 800-207 — Zero Trust Architecture:** nguyên tắc kiểm soát theo ngữ cảnh, tài nguyên và phiên.
- **NIST SP 800-61 — Computer Security Incident Handling Guide:** cơ sở xây dựng quy trình phản ứng và điều tra sự cố.
- **RFC 7296 — Internet Key Exchange Protocol Version 2 (IKEv2):** vòng đời IKE SA/CHILD_SA và bảo mật kết nối.
- **RFC 4301 — Security Architecture for the Internet Protocol:** các khái niệm IPsec và security associations.
- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3:** bảo vệ transport trong các giao thức sử dụng TLS.
- **RFC 2866 — RADIUS Accounting:** sự kiện accounting và các bản ghi phiên liên quan.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** các dải IP minh họa trong bài.
- **MITRE ATT&CK — Enterprise Matrix:** khung mô tả hành vi đối thủ để thiết kế use case phát hiện; không đồng nghĩa tự động có coverage.
