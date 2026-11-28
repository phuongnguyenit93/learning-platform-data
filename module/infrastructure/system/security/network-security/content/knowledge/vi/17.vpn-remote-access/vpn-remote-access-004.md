# Lựa chọn giao thức WireGuard, IPsec và TLS VPN cho truy cập từ xa

**VPN (Virtual Private Network)** tạo một đường truyền logic được bảo vệ giữa các thiết bị hoặc mạng qua hạ tầng không nhất thiết đáng tin cậy. Trong thực tế, nhóm thiết kế thường phải cân nhắc ba họ giải pháp phổ biến: **WireGuard**, **IPsec (thường dùng IKEv2)** và **TLS VPN**. Không có giao thức nào luôn tốt nhất cho mọi môi trường; lựa chọn phụ thuộc vào **mô hình đe dọa, đối tượng truy cập, phương thức xác thực, khả năng quản trị thiết bị, đường mạng đi qua, chính sách phân đoạn và nhu cầu vận hành**.

Trong chương **VPN và truy cập từ xa** của học phần **SECURITY_NETWORK_SECURITY**, lựa chọn VPN là một quyết định kiến trúc bảo mật mạng, liên quan đến firewall, phân đoạn, xác thực kết nối, IDS/IPS, DNS, Wi-Fi và hạ tầng cloud. **Mã hóa tunnel là điều kiện cần nhưng không đủ**: một client đã vào VPN vẫn phải có quyền phù hợp với tài nguyên, không mặc nhiên được truy cập toàn bộ mạng nội bộ.

Bài học này giúp so sánh kỹ thuật và cách triển khai, thiết kế quy trình chọn giao thức theo yêu cầu thực tế, phân tích rủi ro bảo mật, xây ma trận kiểm thử và xử lý những sự cố thường gặp. Các cấu hình và địa chỉ bên dưới chỉ là **minh họa trong lab**; không chứa khóa hoặc credential thật.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích VPN bảo vệ những gì trên đường truyền và những rủi ro vẫn còn ở endpoint, gateway hoặc dịch vụ đích.
2. Phân biệt **remote-access VPN**, **site-to-site VPN**, **tunnel lớp mạng** và **truy cập qua proxy/portal ở lớp ứng dụng**.
3. Mô tả các thành phần chính của WireGuard, IKEv2/IPsec và TLS VPN, tránh đánh đồng mọi VPN đi qua TLS với cùng một cơ chế.
4. So sánh xác thực khóa công khai, PKI, EAP, chứng chỉ, MFA/SSO và quản lý vòng đời danh tính.
5. Phân tích NAT, firewall, mạng chỉ cho HTTPS, roaming, IPv4/IPv6, MTU và kết nối bị gián đoạn.
6. Lựa chọn **full tunnel** hay **split tunnel** phù hợp với chính sách DNS, egress, truy cập nội bộ và thiết bị người dùng.
7. Xây yêu cầu **least privilege**, phân đoạn, kiểm tra posture, logging, revoke, HA và khôi phục.
8. Lập bảng quyết định có trọng số theo use case, không xếp hạng giao thức chỉ từ tốc độ hoặc tên công nghệ.
9. Định nghĩa và thực hiện các ca kiểm thử được phép, gồm cả **luồng hợp lệ và luồng bị cấm**.
10. Trình bày khuyến nghị dựa trên bằng chứng, điều kiện và giới hạn thay vì khẳng định một giao thức luôn an toàn nhất.

## 2. VPN nằm ở đâu trong kiến trúc mạng?

Hai kiểu kết nối thường gặp:

- **Remote access:** một người dùng hoặc thiết bị ở bên ngoài kết nối vào những dịch vụ nội bộ được cấp quyền.
- **Site to site:** hai mạng hoặc hai site, VPC/VNet hay vùng hạ tầng trao đổi dữ liệu qua tunnel.

~~~mermaid
flowchart LR
    U[Thiết bị nhân viên] -->|Đường Internet không tin cậy| G[VPN gateway]
    G --> P[Firewall / policy theo identity và zone]
    P --> J[Jump host]
    P --> A[Ứng dụng nội bộ]
    P -.Mặc định chặn.-> D[(Data zone)]
    S[Site chi nhánh] -->|Site-to-site tunnel| G
    G -.Audit, session và flow logs.-> SOC[SIEM / SOC]
~~~

Sơ đồ minh họa: gateway xác thực/tạo tunnel, còn **firewall/policy phía sau gateway** quyết định những subnet, ứng dụng và cổng nào được dùng. Kiến trúc thực tế có thể kết hợp chính sách trên chính VPN gateway, firewall hoặc ZTNA gateway.

### 2.1. Những thuộc tính cơ bản cần bảo vệ

| Thuộc tính | Câu hỏi cần trả lời | Ghi chú |
|---|---|---|
| **Bí mật** | Người nghe lén trên Wi-Fi/Internet có đọc được payload trong tunnel không? | Phụ thuộc thuật toán, khóa, cấu hình và điểm cuối |
| **Toàn vẹn** | Traffic có được phát hiện khi bị sửa trên đường không? | Thường dùng cơ chế xác thực thông điệp hoặc AEAD |
| **Xác thực peer** | Client có biết đang liên lạc với đúng gateway không? | Khóa public, chứng chỉ, trust store, identity binding |
| **Chống phát lại** | Traffic cũ có thể bị phát lại làm gói hợp lệ không? | Cơ chế nonce/sequence/replay window tùy giao thức |
| **Phân quyền** | Sau khi tunnel mở, máy/user được vào tài nguyên nào? | VPN **không tự** đồng nghĩa least privilege |
| **Sẵn sàng** | Khi link/ISP/gateway lỗi, kết nối có thể phục hồi không? | Cần HA, health check, route và kiểm thử thực tế |
| **Khả năng điều tra** | Ai kết nối, từ thiết bị nào, tới dịch vụ nào, lúc nào? | Cần session + identity + flow + app logs |
| **Thu hồi** | Khi mất thiết bị/nhân sự nghỉ, có tắt quyền kịp không? | Phải xét key, cert, session, token và policy cache |

**Lưu ý:** tunnel VPN thường kết thúc ở VPN gateway hoặc endpoint được cấu hình. Traffic sau điểm giải mã đi tới ứng dụng có thể cần **TLS/mTLS riêng**, firewall và xác thực nghiệp vụ.

### 2.2. VPN không đồng nhất với Zero Trust

Một VPN lớp mạng có thể cấp route tới nhiều subnet; mô hình **Zero Trust Network Access (ZTNA)** thường cố gắng kiểm soát chi tiết hơn theo người dùng, thiết bị và ứng dụng, đôi khi tránh cấp khả năng định tuyến rộng. Hai cách không nhất thiết loại trừ nhau: có thể dùng VPN cho mạng nền và dùng identity-based authorization ở lớp ứng dụng.

Không nên khẳng định một kết nối được gọi là “Zero Trust VPN” chỉ vì có mã hóa hoặc MFA. Phải kiểm chứng quyền theo tài nguyên, device posture, thời hạn phiên, ngữ cảnh và cơ chế thực thi.

## 3. Ba họ giao thức trong một bức tranh

**WireGuard** là giao thức VPN lớp mạng hiện đại, ưu tiên thiết kế gọn, cấu hình peer dựa trên khóa công khai và một bộ thuật toán mật mã được định nghĩa trong giao thức.

**IPsec** là bộ giao thức bảo vệ lưu lượng IP. Trong nhiều thiết kế, **IKEv2** thương lượng các Security Association (SA) và xác thực peer; **ESP** mang dữ liệu được bảo vệ. IPsec có nhiều chế độ và cơ chế tích hợp.

**TLS VPN** là một **họ giải pháp**, không phải một giao thức mạng duy nhất. Một số sản phẩm tạo tunnel mạng qua một control plane xác thực bằng TLS (ví dụ các triển khai dạng OpenVPN); các sản phẩm khác cung cấp **portal/proxy HTTPS** để truy cập một tập ứng dụng. Cần xem chính xác **control channel và data channel** của sản phẩm, vì không phải mọi dữ liệu của mọi “TLS VPN” đều được vận chuyển dưới dạng bản ghi TLS.

### 3.1. Sơ đồ lớp chức năng

~~~text
                     Remote-access VPN
                            |
          +-----------------+-----------------+
          |                 |                 |
       WireGuard       IKEv2 / IPsec       TLS VPN family
          |                 |                 |
  Peer public keys    IKE SA, CHILD SA    TLS auth / control
  Cryptokey routing   ESP protected IP    App proxy hoặc L3 tunnel
  UDP datagrams       ESP / NAT-T         TCP/UDP tùy sản phẩm
          |                 |                 |
          +-----------------+-----------------+
                            |
             Route, DNS, Firewall, MFA, Policy
                            |
                   Internal applications
~~~

**Đừng chọn theo port trước khi chọn theo yêu cầu bảo mật.** Giao thức chạy được trên mạng khách sạn là một điều; có đáp ứng SSO/MFA, cấp quyền theo nhóm và thu hồi truy cập đúng SLA hay không là điều khác.

## 4. WireGuard: mô hình peer và cryptokey routing

WireGuard được thiết kế với tập tính năng cốt lõi tương đối nhỏ. Mỗi peer có **khóa riêng (private key)** và **khóa công khai (public key)**; các peer cấu hình khóa public của nhau và những dải IP gắn với peer đó.

Các thành phần điển hình:

- **Interface tunnel:** tạo địa chỉ nội bộ VPN, ví dụ 10.77.0.1/24 ở gateway.
- **Key pair:** private key phải giữ kín; public key được trao cho peer được phê duyệt.
- **Peer configuration:** public key, tập **AllowedIPs**, và endpoint khi cần.
- **UDP transport:** dùng UDP, port nghe do người triển khai chọn; 51820 là giá trị ví dụ thường gặp, không phải cổng bắt buộc.
- **Handshake và phiên:** peer trao đổi thông tin xác thực mật mã và cập nhật khóa phiên theo cơ chế giao thức.
- **Roaming:** một peer có thể cập nhật endpoint mạng từ những packet đã xác thực hợp lệ theo giao thức.
- **Optional preshared key:** có thể cấu hình thêm PSK để bổ sung bảo vệ khóa, không thay thế key pair.

WireGuard sử dụng các primitive được quy định như Curve25519, ChaCha20-Poly1305, BLAKE2s và HKDF trong thiết kế giao thức. Không nên quảng bá “không thể bị tấn công” chỉ vì bộ thuật toán hiện đại: bảo mật còn phụ thuộc triển khai, hệ điều hành, key storage, cấu hình và endpoint.

### 4.1. AllowedIPs là gì?

**AllowedIPs** có hai vai trò thường gặp trong WireGuard:

1. Ở **đường gửi**, quyết định peer nào phù hợp với địa chỉ đích để chuyển packet vào tunnel.
2. Ở **đường nhận**, ràng buộc địa chỉ nguồn bên trong packet với peer đã xác thực trong cấu hình tương ứng.

Ví dụ gateway có hai client, mỗi client được gắn địa chỉ /32 riêng:

~~~text
Gateway peer Alice:
  PublicKey = ALICE_PUBLIC_KEY
  AllowedIPs = 10.77.0.2/32

Gateway peer Bob:
  PublicKey = BOB_PUBLIC_KEY
  AllowedIPs = 10.77.0.3/32
~~~

**AllowedIPs không phải hệ thống phân quyền người dùng theo ứng dụng.** Nếu client Alice cần truy cập App subnet 10.20.20.0/24 nhưng không được truy cập DB 10.20.30.0/24, vẫn phải thiết kế firewall/ACL/identity policy sau tunnel. Đặc biệt **không gán cùng một dải rộng cho mọi peer gateway** khi cần phân biệt client.

### 4.2. Minh họa cấu hình tối giản cho lab

Cấu hình sau là **mẫu minh họa**, không thể dùng nguyên văn: các khóa là placeholder và còn thiếu phần quản trị firewall, forwarding, DNS, NAT, persistence và quyền.

~~~ini
# Gateway (minh họa; không dùng khóa thật trong tài liệu)
[Interface]
Address = 10.77.0.1/24
ListenPort = 51820
PrivateKey = <GATEWAY_PRIVATE_KEY_PLACEHOLDER>

[Peer]
PublicKey = <ALICE_PUBLIC_KEY_PLACEHOLDER>
AllowedIPs = 10.77.0.2/32
~~~

~~~ini
# Client Alice: chỉ đi tới mạng ứng dụng và IP tunnel qua VPN
[Interface]
Address = 10.77.0.2/32
PrivateKey = <ALICE_PRIVATE_KEY_PLACEHOLDER>
DNS = 10.20.1.53

[Peer]
PublicKey = <GATEWAY_PUBLIC_KEY_PLACEHOLDER>
Endpoint = vpn.lab.example:51820
AllowedIPs = 10.20.20.0/24, 10.20.1.53/32, 10.77.0.0/24
PersistentKeepalive = 25
~~~

Giải thích:

- **Endpoint** là hostname/IP và UDP port của gateway nếu client cần chủ động kết nối.
- **Client AllowedIPs** trong ví dụ mô tả các đích đi tunnel (split tunnel), **không** tự cấp quyền ở phía server.
- **Gateway AllowedIPs** chỉ gắn địa chỉ VPN của Alice vào public key của Alice.
- **PersistentKeepalive 25** là giá trị minh họa khi cần giữ NAT binding cho peer đứng sau NAT; không bắt buộc hoặc tối ưu trong mọi mạng.
- **DNS 10.20.1.53** phải reachable và được phép qua tunnel; nếu thiếu route/firewall, tên miền có thể không phân giải được.
- Trong thực tế cần **key management, quyền trên file, gateway firewall, IPv6 policy và quy trình revoke**.

Không chép private key vào Git, ticket, wiki hoặc báo cáo. Không dùng lại cùng private key cho nhiều máy; nên cấp khóa riêng cho từng thiết bị/peer.

### 4.3. Mạnh ở đâu, thiếu gì ở lớp quản trị?

WireGuard phù hợp khi cần **tunnel IP gọn, hiệu năng tốt trong thiết kế phù hợp, roaming và cấu hình peer rõ ràng**. Tuy nhiên giao thức lõi **không cung cấp một hệ thống tài khoản, SSO/MFA tương tác, cấp IP động từ dịch vụ danh tính, chính sách nhóm, portal hoặc quản lý vòng đời người dùng**. Các tính năng này có thể được xây bằng controller, agent, IdP và sản phẩm bổ sung.

Bởi vậy “WireGuard không hỗ trợ MFA” cần diễn đạt chính xác hơn: **giao thức lõi WireGuard không tự thực hiện MFA**, nhưng hệ thống truy cập xây trên WireGuard có thể yêu cầu SSO/MFA, cấp khóa ngắn hạn, device posture và authorization ở các lớp bổ sung. Cần kiểm chứng các bước đó thật sự xảy ra **trước và trong lúc cấp quyền**.

## 5. IPsec: ESP, IKEv2 và Security Association

**IPsec** là một họ giao thức bảo vệ IP. Trong nhiều triển khai remote access hoặc site to site, kiến trúc dùng:

- **IKEv2:** xác thực peer, thương lượng chính sách mật mã, thiết lập và quản lý các SA.
- **IKE SA:** kênh bảo vệ quá trình điều khiển của IKE.
- **CHILD SA:** tập trạng thái khóa/tham số phục vụ traffic IPsec (thường ESP).
- **ESP (Encapsulating Security Payload):** bảo vệ dữ liệu IP theo tập thuật toán và chế độ được thương lượng.
- **Traffic selectors:** mô tả tập traffic được đưa qua những SA tương ứng.
- **Tunnel mode và transport mode:** cách ESP bảo vệ packet tùy kiến trúc.

**ESP là thành phần mang dữ liệu, không phải “TLS qua VPN”.** IPsec được xây khác với TLS VPN; cần đọc đúng khái niệm đường điều khiển và đường dữ liệu.

### 5.1. Mô hình IKEv2/IPsec

~~~mermaid
sequenceDiagram
    participant C as Client IKEv2
    participant G as IPsec Gateway
    participant N as Mạng nội bộ
    C->>G: IKE_SA_INIT - thương lượng & trao đổi khóa
    G-->>C: IKE_SA_INIT response
    C->>G: IKE_AUTH - identity/authentication
    G-->>C: IKE_AUTH response, CHILD SA
    Note over C,G: SA và policy được thiết lập nếu xác thực đạt
    C->>G: ESP / NAT-T traffic được bảo vệ
    G->>N: Packet sau IPsec policy và firewall
    N-->>G: Response nếu được cho phép
    G-->>C: Response qua IPsec
~~~

Sơ đồ khái niệm rút gọn. IKEv2 có thể có thêm exchanges như CREATE_CHILD_SA, INFORMATIONAL, rekey, delete và các mở rộng tùy cấu hình. **Đừng kết luận SA tồn tại nghĩa ứng dụng đã truy cập thành công.**

### 5.2. IKEv2 dùng những cổng nào?

| Thành phần | Đặc trưng mạng | Lưu ý |
|---|---|---|
| IKEv2 thông thường | UDP/500 | Dùng thiết lập/duy trì phiên IKE |
| NAT Traversal (NAT-T) | Thường UDP/4500 | Đóng gói ESP qua UDP khi cần NAT traversal |
| ESP không đóng gói UDP | IP protocol number 50 | Không phải TCP port 50 |
| AH (Authentication Header) | IP protocol number 51 | Ít dùng trong VPN remote access phổ biến; không đánh đồng AH với ESP |

Không phải mọi IPsec đều chỉ chạy qua UDP/4500: tùy NAT, gateway và triển khai, ESP có thể là IP protocol 50. Một số sản phẩm có kỹ thuật đóng gói đặc thù để đi qua các đường mạng khác; không suy diễn chúng là khả năng chung của IKEv2/IPsec chuẩn.

### 5.3. IKEv2, danh tính và MFA

IKEv2 có thể dùng chứng chỉ, khóa và các cơ chế xác thực như EAP trong các profile phù hợp. Một gateway có thể tích hợp **RADIUS/IdP/MFA** qua kiến trúc sản phẩm.

- **Client phải xác minh đúng danh tính gateway**, ví dụ chứng chỉ máy chủ và chính sách trust.
- **Server phải xác thực client/user** theo phương thức được cấp.
- **MFA/SSO không tự có** chỉ vì giao thức là IKEv2; cần xác minh cụ thể client, EAP method, gateway và IdP.
- **EAP không đồng nghĩa mọi lần xác thực đều dùng client certificate.** Phương thức EAP và cơ chế bảo vệ credential khác nhau.
- Kiểm tra password policy, certificate lifecycle, CRL/OCSP hoặc phương án thu hồi phù hợp nếu dùng PKI.

Với thiết bị đã quản lý, **xác thực dựa trên chứng chỉ và device identity** có thể phù hợp hơn chia sẻ PSK tĩnh giữa nhiều người dùng. Tuy nhiên vẫn cần quy trình cấp, thay, thu hồi và quản lý private key.

### 5.4. Tunnel mode, transport mode và traffic selectors

**Tunnel mode** thường dùng để vận chuyển packet IP qua hai gateway hoặc giữa client và gateway, với IP header ngoài phục vụ route qua mạng. **Transport mode** bảo vệ payload của IP packet theo mô hình phù hợp và có ứng dụng khác.

Một thiết kế IKEv2/IPsec có thể dùng **route-based VPN** với interface/tunnel logic hoặc **policy-based VPN** với selectors xác định traffic. Khi chọn cần biết thiết bị có hỗ trợ dynamic routing, VRF, HA và selectors cần thiết không.

**Traffic selectors và firewall policy là hai cơ chế khác nhau.** Một traffic selector rộng không đồng nghĩa user phải được quyền đi tới mọi DB; phải kiểm tra ACL/SG/identity authorization phù hợp.

### 5.5. NAT, roaming và MOBIKE

IPsec truyền thống có thể gặp NAT; **NAT-T** được dùng để hỗ trợ môi trường có NAT. IKEv2 còn có khả năng roaming/thay đổi địa chỉ qua các mở rộng như **MOBIKE**, nhưng **không mặc định mọi gateway/client đều hỗ trợ hoặc bật MOBIKE**.

Trên mạng khách sạn, mạng di động hoặc nhiều lớp NAT, UDP/500/4500 có thể bị chặn. Khi đó IKEv2/IPsec có thể không hoạt động dù HTTPS/443 vẫn bình thường, nên cần kiểm thử thực tế và phương án dự phòng.

## 6. TLS VPN: không phải mọi sản phẩm là cùng một giao thức

**TLS VPN** thường nói tới những giải pháp dùng TLS để bảo vệ quá trình kết nối và xác thực, nhưng cách truyền dữ liệu rất đa dạng. Hai mô hình nên phân biệt:

### 6.1. Full-tunnel hoặc routed VPN với client chuyên dụng

Một số sản phẩm như OpenVPN triển khai **đường điều khiển dựa trên TLS** để xác thực/thỏa thuận khóa và **đường dữ liệu VPN riêng** để bảo vệ packet sau khi tunnel hình thành. Đường dữ liệu không được mặc định xem là các bản ghi TLS của HTTPS.

Đặc điểm:

- Tạo interface ảo (TUN/TAP hoặc tương đương tùy hệ điều hành/sản phẩm).
- Có thể cấp route, DNS, split tunnel hoặc full tunnel.
- Thường dùng TCP hoặc UDP tùy sản phẩm/cấu hình.
- Có thể tích hợp PKI, username/password, MFA/SSO qua gateway/plugin/IdP.
- Gateway có chính sách về nhóm, thiết bị và subnet.

Một sản phẩm quảng bá “TLS VPN trên TCP/443” **không tự chứng minh** mọi traffic trông giống HTTPS trình duyệt hoặc sẽ đi qua mọi proxy/TLS inspection. Một số proxy yêu cầu giao thức HTTP thực sự, còn VPN client có thể bị chặn bởi policy mạng.

### 6.2. Clientless portal hoặc application proxy

Một số giải pháp cho user truy cập ứng dụng web qua **portal HTTPS**, reverse proxy hoặc gateway cấp quyền ứng dụng:

~~~text
Browser
   |
   v
TLS / HTTPS portal + SSO/MFA
   |
   v
Application proxy / per-app policy
   |
   v
Ứng dụng web được phê duyệt
~~~

Trong mô hình này, người dùng có thể **không nhận một IP nội bộ hoặc route tới toàn subnet**. Điều này thuận lợi với một số ứng dụng web và thiết bị không cài client. Tuy nhiên:

- Không phải mọi giao thức (SSH, RDP, database, UDP custom) có thể đi qua portal không cần client.
- Một số giải pháp cần agent, browser extension hoặc proxy chuyên dụng để hỗ trợ ứng dụng khác HTTP.
- HTTPS portal có thể hỗ trợ authorization theo ứng dụng, nhưng mức độ phụ thuộc sản phẩm.
- Clientless không đồng nghĩa thiết bị BYOD được phép truy cập dữ liệu nhạy cảm không cần posture/MFA.

### 6.3. TLS, DTLS, QUIC và HTTP/3

Một số VPN tối ưu data path bằng **UDP**, DTLS, QUIC hoặc cơ chế của sản phẩm. Không được khẳng định **TLS VPN luôn dùng TCP**. Khi gặp tài liệu nhà sản xuất, kiểm tra:

1. Cổng và transport thực (TCP, UDP hoặc cả hai).
2. TLS được dùng cho **control, data hay cả hai**.
3. Có fallback UDP→TCP không, điều kiện chuyển ra sao.
4. Phiên bản/thuật toán TLS và cơ chế xác thực.
5. Client có đi qua corporate proxy, captive portal hoặc TLS-inspection gateway được không.
6. Dữ liệu có được bảo vệ end-to-end đến VPN gateway đúng danh tính không.

### 6.4. TCP-over-TCP và hiệu năng

Nếu traffic TCP của ứng dụng được tunnel qua một VPN vận chuyển bằng **TCP** khác, mất gói hoặc retransmission ở cả hai tầng có thể gây **head-of-line blocking** và hiệu ứng hồi phục kém trên đường mất gói. Đây là rủi ro thiết kế thường được gọi là TCP-over-TCP.

Không phải mọi VPN qua TCP đều chậm trong mọi trường hợp; nó còn phụ thuộc độ mất gói, implementation và ứng dụng. Khi có UDP transport an toàn được hỗ trợ, nên đo hai phương án thay vì đưa ra kết luận chỉ từ tên giao thức.

## 7. Bảng so sánh kỹ thuật WireGuard, IKEv2/IPsec và TLS VPN

| Tiêu chí | WireGuard | IKEv2/IPsec | TLS VPN |
|---|---|---|---|
| Bản chất | Tunnel lớp mạng dựa trên peer/key | Bộ giao thức bảo vệ IP, IKEv2 + ESP phổ biến | Họ giải pháp TLS control/tunnel hoặc application portal |
| Transport phổ biến | UDP port tùy chọn | UDP/500, UDP/4500 NAT-T, ESP proto 50 tùy đường | TCP/UDP/HTTPS tùy sản phẩm |
| Phương thức xác thực lõi | Static public keys/peer association | Chứng chỉ, PSK, EAP hoặc phương thức triển khai | TLS certificates, auth gateway, IdP/plugin tùy sản phẩm |
| MFA tích hợp ngay trong giao thức lõi? | Không | Không tự có; có thể tích hợp qua stack EAP/IdP | Không tự có; thường do gateway/IdP tích hợp |
| Roaming | Peer có thể đổi endpoint đã xác thực | MOBIKE/DPD và profile nếu hỗ trợ | Client reconnect/session mobility tùy sản phẩm |
| NAT traversal | UDP với endpoint/NAT binding, đôi khi cần keepalive | NAT-T và IKEv2 mechanisms | Tùy transport, proxy và client |
| Mã hóa | Suite đã định nghĩa trong thiết kế WireGuard | Thuật toán được thương lượng qua IKEv2/profile | TLS/control và data channel phụ thuộc sản phẩm |
| PKI bắt buộc? | Không dùng mô hình X.509 trong lõi | Không luôn bắt buộc, nhưng PKI phổ biến | Thường dùng certificate TLS, client cert tùy sản phẩm |
| Remote access user | Cần hệ thống identity/policy bổ sung nếu muốn SSO/MFA | Có nhiều client OS/profile enterprise | Có nhiều lựa chọn portal/client theo vendor |
| Site to site | Phù hợp khi hai đầu kiểm soát được | Rất phổ biến trong thiết bị mạng/cloud | Có sản phẩm hỗ trợ, không phải mặc định |
| Tích hợp network equipment | Phụ thuộc OS/router/vendor/controller | Phổ biến trên firewall/router/OS/cloud gateway | Phụ thuộc VPN concentrator/portal/gateway |
| Per-app access | Cần giải pháp bổ sung | Thường cần policy/ZTNA bổ sung | Portal/proxy có thể hỗ trợ theo app tùy sản phẩm |
| Quản lý key/cert/identity | Peer lifecycle/controller | PKI/EAP/SA và policy | PKI/IdP/session/plugin và policy |
| Khả năng quan sát | Handshake/peer/bytes, cần log bổ sung | IKE/SA/ESP status, gateway logs | TLS/auth/session/application logs theo sản phẩm |

Bảng mô tả **khuynh hướng kỹ thuật**, không phải công bố rằng mọi sản phẩm đều có tính năng như nhau. Lựa chọn phải kiểm tra phiên bản đang dùng, hệ điều hành, yêu cầu pháp lý và hỗ trợ của nhà cung cấp.

### 7.1. “Nhanh hơn” và “an toàn hơn” cần đo theo điều kiện

Kết quả đo throughput/latency phụ thuộc CPU, khả năng tăng tốc mật mã, driver/kernel/userspace, MTU, UDP/TCP, phần cứng thiết bị, packet size, đường truyền, session count, NIC offload và policy logging. Một benchmark trên laptop không dự báo chính xác hiệu năng của firewall HA có IPS hoặc gateway cloud.

**Mật mã mạnh không bù được cấu hình authorization yếu.** Một VPN hiệu năng cao có thể rủi ro nếu cấp route Any→Any hoặc dùng chung khóa quá lâu.

## 8. So sánh theo mô hình triển khai thực tế

### 8.1. Nhân viên dùng máy doanh nghiệp được quản trị

Yêu cầu thường gồm **SSO/MFA, thiết bị đạt posture, tài khoản theo nhóm, thu hồi nhanh, split/full tunnel, DNS nội bộ, hoạt động khi chuyển Wi-Fi/4G và logging**.

- **IKEv2/IPsec:** đáng cân nhắc khi hệ điều hành có client phù hợp, tổ chức đã có PKI/IdP và gateway hỗ trợ profile quản trị.
- **TLS VPN:** đáng cân nhắc khi sản phẩm có IdP/SSO, client posture, policy nhóm và hỗ trợ những mạng chỉ cho HTTPS.
- **WireGuard:** phù hợp nếu được bổ sung hệ thống enrollment, MFA trước cấp quyền, phân quyền và thu hồi peer theo danh tính.

Không chọn chỉ vì client đã tích hợp sẵn trong OS. Cần kiểm tra chính sách thiết bị và khả năng chặn truy cập sau khi session bị thu hồi.

### 8.2. Quản trị viên truy cập mạng nhạy cảm

Đối với Management, DB và hạ tầng điều khiển, nên hạn chế mặt phẳng truy cập:

- Yêu cầu MFA và thiết bị quản trị đáng tin.
- Tách VPN role/network zone cho admin.
- Chỉ cho admin vào **jump host hoặc ứng dụng quản trị được phê duyệt**, không mở toàn bộ Data subnet.
- Có session logging và log xác thực của SSH/RDP/DB.
- Định kỳ review quyền, khóa/chứng chỉ, session duration và emergency access.
- Có thể sử dụng ZTNA/bastion bổ sung hoặc thay thế route VPN rộng.

**Giao thức tunnel không được quyết định thay cho mô hình least privilege.**

### 8.3. Site-to-site giữa chi nhánh và trung tâm

**IKEv2/IPsec** thường là lựa chọn đáng kiểm tra sớm khi hai đầu là router/firewall doanh nghiệp, yêu cầu interoperability và hỗ trợ chính thức từ nhà mạng/cloud. **WireGuard** cũng có thể hợp lý khi hai đầu do tổ chức quản lý, muốn cấu hình peer rõ và vận hành khóa tốt.

Hãy đánh giá **route-based vs policy-based, BGP/static routing, NAT, HA, key rotation, vendor interoperability, route filtering và failover**. TLS VPN có thể phù hợp trong các sản phẩm nhất định, nhưng phải xác minh khả năng chuyển lưu lượng giữa hai mạng và HA thực tế.

### 8.4. Truy cập ứng dụng web của đối tác trên thiết bị không quản trị

**Application proxy/portal TLS có SSO/MFA và quyền theo ứng dụng** thường đáng cân nhắc vì không cần cấp route cả subnet. Tuy nhiên còn phụ thuộc chính sách BYOD, browser security, session handling, DLP và dữ liệu ứng dụng. Nếu cần SSH/UDP/custom protocols, portal HTTPS đơn giản có thể không đủ.

### 8.5. IoT hoặc thiết bị nhúng

Kiểm tra bộ nhớ, CPU, khả năng cập nhật, lưu khóa an toàn, hỗ trợ VPN stack và cách đổi/revoke key. Nếu endpoint không đáp ứng yêu cầu, có thể đặt tunnel tại gateway quản trị của mạng IoT thay vì cấp khóa và route cho từng thiết bị không đáng tin.

### 8.6. Cloud, Kubernetes và hạ tầng hybrid

Cloud provider có thể hỗ trợ site-to-site IPsec managed, VPN client service, private connectivity hoặc đối tác WireGuard/TLS. Tiêu chí quan trọng là **phạm vi dịch vụ managed, HA/region, IAM, route propagation, security group/network ACL, DNS/private zone, logging và chi phí**.

Trong Kubernetes, không coi Pod IP là identity ổn định; nếu workload cần VPN ra ngoài, quản lý qua **gateway/sidecar/egress policy hoặc service identity** theo kiến trúc được phê duyệt. VPN không tự thay thế Kubernetes NetworkPolicy hoặc mTLS.

## 9. Xác thực: thiết bị, người dùng và dịch vụ là ba lớp khác nhau

Một chương trình remote access cần xác định **ai** và **cái gì** đang truy cập:

1. **Identity người dùng:** tài khoản trong IdP, MFA, nhóm và trạng thái nhân sự.
2. **Identity thiết bị:** certificate, enrollment, MDM/EDR posture, khóa gắn thiết bị hoặc hardware-backed key.
3. **Identity peer/gateway:** chứng chỉ hoặc public key được client xác thực.
4. **Danh tính workload/tài nguyên:** ứng dụng, host, subnet, service account và policy.
5. **Phiên và thời hạn:** giờ bắt đầu/kết thúc, thay role, revoke, token expiry và reconnect.

### 9.1. Những nhầm lẫn phổ biến

- **Biết WireGuard private key** chứng minh peer sở hữu khóa, không tự chứng minh người hiện đang dùng máy đã hoàn thành MFA.
- **IKEv2 tạo CHILD SA** nghĩa tunnel data plane được thương lượng, không chứng minh mọi user trong tổ chức được phép vào DB.
- **TLS server certificate hợp lệ** chứng minh client đã xác thực đúng endpoint theo chính sách, không chứng minh user đã đăng nhập vào dịch vụ phía sau.
- **MFA lúc enrollment** không tự đồng nghĩa MFA được kiểm tra cho mỗi phiên hoặc khi thay quyền, nếu sản phẩm không thiết kế như vậy.
- **Device posture lúc kết nối** có thể trở nên lỗi thời; cần chính sách re-evaluate khi rủi ro thay đổi.

### 9.2. Quản lý vòng đời

| Sự kiện | Cần làm gì |
|---|---|
| Nhân sự mới | Xác minh danh tính, role, thiết bị quản trị và cấp quyền tối thiểu |
| Thiết bị mới | Enrollment, key/cert riêng, posture, log người phê duyệt |
| Chuyển nhóm | Cập nhật VPN role, network group, app policy; thu hồi quyền cũ |
| Mất thiết bị | Thu hồi/revoke key/cert/session/token trong hệ thống áp dụng |
| Nhân sự nghỉ | Disable IdP, revoke peers/certs, dừng session và xóa quyền ứng dụng |
| Lộ khóa | Rotating key và khóa được tin, điều tra thời gian exposure |
| Chứng chỉ hết hạn | Quy trình thay/renew với giám sát để tránh outage |
| Gateway bị thay | Cập nhật trust material và kiểm chứng client xác thực đúng gateway |

**Thu hồi trên hệ thống quản lý không luôn làm mọi session đang mở biến mất ngay.** Phải kiểm chứng chính sách session termination/rekey/cache và kiểm tra các lớp truy cập ứng dụng.

## 10. Lựa chọn thuật toán và cấu hình mật mã

Không nên dùng tuyên bố “giao thức X không cần kiểm tra crypto”. Mỗi lựa chọn cần có quy trình cấu hình và bảo trì.

### 10.1. WireGuard

Ưu điểm là tập primitive giao thức được chuẩn hóa/gọn; người vận hành ít phải thương lượng một danh sách cipher suite dài. Vẫn cần:

- Private key đủ ngẫu nhiên, lưu an toàn và không xuất ra log.
- Key riêng cho từng peer; hạn chế key sharing.
- Quy trình rotate/revoke, xóa peer cũ và đổi public keys.
- Kiểm tra client/gateway được cập nhật bảo mật.
- Quản lý optional PSK nếu có, bao gồm lưu và thay khóa.
- Giám sát handshake và traffic mà không lưu secret.

### 10.2. IKEv2/IPsec

Do tính linh hoạt, cần thống nhất **crypto proposal** phù hợp với chính sách tổ chức, các loại thuật toán được hỗ trợ và năng lực phần cứng:

- Chọn thuật toán mã hóa/xác thực mạnh, ưu tiên AEAD phù hợp khi triển khai hỗ trợ.
- Chọn nhóm trao đổi khóa và mức bảo vệ phù hợp cho IKE/CHILD SA.
- Cấu hình lifetime/rekey và PFS theo policy.
- Tránh phương thức PSK chia sẻ tràn lan hoặc proposal yếu/lỗi thời.
- Kiểm tra anti-replay window, DPD, NAT-T và authentication.
- Kiểm soát certificate validation và trust chain đầy đủ.

**Đừng copy một profile IPsec trên Internet mà không kiểm tra version và hỗ trợ cụ thể** của gateway/client: mismatch IKE proposals, authentication hoặc selectors có thể làm tunnel không lên hoặc âm thầm dùng cấu hình không mong muốn.

### 10.3. TLS VPN

- Sử dụng phiên bản và cấu hình TLS còn được tổ chức chấp nhận, với certificate validation đúng.
- Xác định rõ data channel sử dụng cơ chế nào, key negotiation và rekey thế nào.
- Kiểm tra host/client trust, revocation, hostname verification và quy trình cấp cert.
- Vô hiệu hóa authentication mode yếu hoặc fallback plaintext nếu có.
- Kiểm soát session cookies/tokens, SSO/MFA, CSRF/session fixation và browser security cho portal.
- Kiểm tra chính sách HTTPS proxy hoặc TLS interception tác động ra sao tới xác thực gateway.

**Một sản phẩm TLS VPN không tự mạnh hơn IPsec/WireGuard chỉ vì “dùng TLS”.** Cần kiểm tra threat model, chính sách và implementation.

## 11. NAT, firewall và khả năng kết nối trong mạng hạn chế

Nhiều người dùng làm việc qua Wi-Fi khách sạn, mạng di động, proxy công ty hoặc CGNAT. Khả năng tiếp cận gateway có thể quyết định trải nghiệm.

| Môi trường | WireGuard | IKEv2/IPsec | TLS VPN |
|---|---|---|---|
| Wi-Fi gia đình hỗ trợ UDP | Thường thuận tiện nếu UDP tới endpoint được phép | Có thể hoạt động với IKE/ESP hoặc NAT-T | Tùy sản phẩm và transport |
| CGNAT phía client | Có thể dùng outbound UDP + NAT binding/keepalive | NAT-T thường giúp vượt NAT nếu gateway và đường hỗ trợ | Tùy cơ chế, thường client chủ động mở kết nối |
| Chỉ outbound TCP/443 | UDP WireGuard có thể bị chặn | UDP/500/4500 thường bị chặn | Một số sản phẩm TCP/443 có lợi thế, cần xác minh proxy |
| Corporate HTTP proxy | WireGuard UDP trực tiếp thường không đi qua proxy HTTP đơn giản | IPsec có thể không qua HTTP proxy | Một số TLS VPN có proxy support; không mặc định |
| Mạng di động chuyển IP | Peer roaming có thể giúp cập nhật endpoint | MOBIKE nếu hỗ trợ và cấu hình | Client reconnect/session resume tùy sản phẩm |
| Site có IP public cố định | Thường thuận tiện cho cả hai bên | Phù hợp với site-to-site truyền thống | Phụ thuộc sản phẩm |
| Đường mất gói cao | Cần đo latency/MTU/packet loss | Cần đo NAT-T/ESP/CPU/SA | UDP variant hoặc TCP variant có hành vi khác |

**Không có giao thức nào bảo đảm “vượt mọi firewall”.** Một mạng có chính sách chặn VPN có thể từ chối các kết nối không được phép; người quản trị nên chọn giải pháp đáp ứng chính sách thay vì cố che giấu traffic để vượt hạn chế.

### 11.1. Các luồng cần cho phép ở biên

- **WireGuard:** UDP listener được cấu hình; ví dụ 51820.
- **IKEv2/IPsec:** thường UDP/500 và UDP/4500, cùng ESP protocol 50 khi không encapsulate trong UDP, tùy topology.
- **TLS VPN:** port/transport do gateway công bố; không áp đặt tất cả là TCP/443.

Sau khi xác thực tunnel, còn phải cho phép **traffic nội bộ hợp lệ**, đường trả về, DNS, NTP/PKI endpoints hoặc những phụ thuộc cần thiết theo thiết kế. **Mở port listener không đồng nghĩa tunnel hoặc ứng dụng đang hoạt động**.

### 11.2. NAT mapping và source attribution

VPN gateway có thể ghi:
- Public source IP/port trước tunnel.
- Tunnel virtual IP được cấp cho peer/client.
- User/Device ID, key fingerprint/cert identifier, session ID.
- NAT translation nếu gateway xử lý egress.
- Thời điểm gắn kết và ngắt kết nối.

Nếu nhiều client cùng xuất hiện từ một public IP của mạng di động, **public IP không đủ để xác định người dùng**. Cần session ID hoặc identity và đúng khoảng thời gian.

## 12. Roaming, mất mạng và phục hồi phiên

Một người dùng có thể chuyển Wi-Fi → 4G, suspend laptop, đóng/mở nắp máy hoặc thay public IP trong lúc VPN đang hoạt động.

### 12.1. WireGuard

Các peer có thể cập nhật endpoint từ những packet đã được xác thực hợp lệ, thuận lợi khi client đổi IP. Nhưng:
- Client vẫn cần có route/UDP connectivity tới gateway.
- DNS endpoint của gateway phải phân giải đúng khi client thay mạng.
- Ứng dụng TCP có thể reconnect sau mất mạng.
- NAT keepalive và battery impact cần cân nhắc.
- Identity/session management của lớp sản phẩm bổ sung phải đồng bộ.

### 12.2. IKEv2/IPsec

IKEv2 có thể dùng cơ chế DPD/keepalive và **MOBIKE** khi cả hai phía hỗ trợ để xử lý thay đổi địa chỉ. Nếu không, có thể phải thiết lập lại IKE/CHILD SA. **MOBIKE không thay thế kiểm tra route chiều về, gateway HA và policy.**

### 12.3. TLS VPN

Một số client hỗ trợ reconnect, session resumption hoặc transport fallback. Tuy nhiên thay gateway, nguồn IP hoặc đường vận chuyển có thể làm TCP/TLS/ứng dụng gián đoạn. Với mô hình portal, browser session còn phụ thuộc cookie/token và chính sách identity.

### 12.4. Định nghĩa “phục hồi” có nhiều mức

| Chỉ báo | Ý nghĩa |
|---|---|
| Client hiển thị “Connected” | Giao diện người dùng tin rằng một trạng thái kết nối đạt |
| Handshake/SA mới | Kênh bảo mật được thiết lập hoặc cập nhật |
| Route/DNS hợp lệ | Client đã nhận/chọn đường tới tài nguyên cần dùng |
| Lưu lượng hai chiều | Packet tới đích và phản hồi quay về theo policy |
| App transaction thành công | HTTPS/API/SSH/DB hoạt động với auth và permission hợp lệ |
| Existing session survives | Session đang mở không bị mất hoặc ứng dụng tự phục hồi |

**Sự kiện handshake thành công không đủ để tuyên bố ứng dụng đã phục hồi.**

## 13. Full tunnel và split tunnel

**Full tunnel** thường hướng phần lớn hoặc toàn bộ Internet-bound traffic của client qua VPN gateway (ví dụ route 0.0.0.0/0 và ::/0 nếu áp dụng IPv6). **Split tunnel** chỉ hướng một tập mạng hoặc ứng dụng qua VPN, còn lưu lượng khác đi theo kết nối local.

~~~mermaid
flowchart TD
    U[Remote Client]
    U -->|Corporate destinations| T[VPN tunnel]
    T --> G[Gateway + Firewall + DNS]
    U -->|Internet khác khi split tunnel| I[Local Internet]
    G --> A[Internal Applications]
    G --> E[Managed Internet Egress nếu full tunnel]
~~~

### 13.1. So sánh theo mục tiêu

| Tiêu chí | Full tunnel | Split tunnel |
|---|---|---|
| Giám sát Internet egress | Có thể tập trung ở gateway nếu không có đường bypass | Một phần lưu lượng đi trực tiếp, cần endpoint/security controls |
| Băng thông gateway | Tốn hơn vì mang thêm traffic | Giảm tải đường vào VPN |
| Độ trễ tới dịch vụ Internet gần client | Có thể tăng do hairpin | Thường thuận lợi hơn cho dịch vụ public |
| DNS và quản lý policy | Có thể tập trung nhưng vẫn cần kiểm chứng leak | Cần tách DNS theo suffix và routing |
| Khả năng dùng LAN/printer local | Có thể bị hạn chế theo policy | Thường thuận tiện hơn, cũng tăng bề mặt tiếp xúc |
| Risk exposure | VPN gateway tập trung thành điểm nghẽn | Endpoint có đường ngoài VPN đồng thời |
| Người dùng ở mạng không ổn định | Có thể chịu tác động tới mọi ứng dụng | Có thể giảm ảnh hưởng tới app ngoài tunnel |

**Không mặc định full tunnel luôn an toàn hơn.** Một full tunnel thiếu giám sát, phân quyền hay HA vẫn rủi ro. Ngược lại split tunnel có thể phù hợp nếu endpoint được quản trị, DNS policy rõ và các ứng dụng nhạy cảm được bảo vệ độc lập.

### 13.2. Tính cả IPv6

Nếu chỉ định tuyến **0.0.0.0/0** qua VPN nhưng client có IPv6 Internet trực tiếp, một số ứng dụng có thể đi qua IPv6 ngoài tunnel. Với full tunnel dual-stack, cần xác định **::/0**, IPv6 firewall, DNS AAAA và hành vi của ứng dụng. Nếu gateway không hỗ trợ IPv6, phải có chính sách rõ để tránh leak hoặc mất kết nối.

### 13.3. Kill switch và điều kiện mất VPN

Một số client hoặc host firewall có thể chặn traffic bên ngoài VPN khi tunnel mất (**kill switch**). Đây là chính sách quan trọng với những nhóm thiết bị nhạy cảm, nhưng có thể gây gián đoạn nếu áp dụng sai, nhất là captive portal, DHCP, DNS bootstrap và phần mềm quản trị.

Cần thử **tunnel mất, reconnect, boot/login, sleep/wake và network switching** để xác định có traffic rò ra ngoài hay không và liệu người dùng còn đường hỗ trợ/khôi phục hợp lệ.

## 14. DNS, split DNS và quyền riêng tư trong VPN

VPN làm thay đổi **đường đi tới resolver**, nhưng không tự bảo đảm mọi ứng dụng dùng resolver doanh nghiệp.

### 14.1. Các vấn đề phổ biến

- **Split DNS:** tên nội bộ chỉ được resolver công ty phân giải đúng.
- **Browser DoH override:** browser có thể chọn resolver riêng khác OS/VPN.
- **DNS leak:** query đi ngoài đường DNS mong muốn theo policy.
- **IPv6 resolver ngoài chính sách:** client vẫn dùng resolver IPv6 không thuộc VPN.
- **DNS cache:** tên được phân giải trước khi kết nối có thể còn trong cache.
- **Gateway HA:** khi VPN gateway thay đổi, địa chỉ DNS hoặc route tới DNS phải còn hợp lệ.
- **DNSSEC validation và DNS filtering:** là lớp khác với mã hóa tunnel; cần quyết định nơi thực thi.

### 14.2. Ma trận minh họa

| Trường hợp | Kỳ vọng |
|---|---|
| Máy managed vào app.corp.example qua VPN | Truy vấn tới resolver private đã phê duyệt và nhận IP nội bộ đúng |
| Full-tunnel client tìm public site | DNS policy và Internet egress đi đúng đường được quản lý |
| Split-tunnel client tìm public site | Có thể dùng resolver ngoài nếu policy cho phép, cần ghi rõ |
| Browser bật DoH riêng | Phải phù hợp enterprise/browser policy và không làm hỏng private zones |
| VPN mất | Không gửi truy vấn private zone tới resolver public ngoài ý muốn |
| Client IPv6 | DNS và route IPv6 không tạo đường rò ra ngoài |

Không thể xác định DNS leak chỉ từ một kết nối HTTPS tới IP public, vì đó có thể là truy cập ứng dụng thông thường. Cần biết **resolver thực tế, giao diện mạng, thời điểm và tên/loại query**.

## 15. Phân đoạn, firewall và quyền sau khi VPN kết nối

Một cấu hình VPN có thể bảo vệ lưu lượng tốt nhưng vẫn tạo **lateral movement path** quá rộng nếu cấp route tới tất cả subnet.

### 15.1. Ma trận phân quyền đề xuất

Giả sử doanh nghiệp có:

- VPN subnet: 10.77.0.0/24.
- Staff application: 10.20.20.0/24.
- Database: 10.20.30.0/24.
- Management jump host: 10.20.99.10.
- Internal DNS: 10.20.1.53.

| Vai trò | Nguồn đã xác thực | Đích/port | Kỳ vọng |
|---|---|---|---|
| Employee | Client thuộc role Employee | App HTTPS TCP/443 | Allow |
| Employee | Client thuộc role Employee | DB TCP/5432 | Deny |
| Employee | Client thuộc role Employee | Jump host TCP/22 | Deny |
| Admin | Client đạt Admin role + posture | Jump host TCP/22 hoặc giao thức quản trị được duyệt | Allow theo policy |
| Admin | Client thuộc Admin role | DB direct TCP/5432 | Deny trừ khi có quyền riêng |
| Managed client | Tunnel endpoint đã hợp lệ | Resolver nội bộ UDP/TCP 53 hoặc giao thức DNS đã duyệt | Allow |
| Unknown/unmanaged | Không hoàn tất xác thực/authorization | Mọi mạng nội bộ | Deny |

**Một AllowedIPs của WireGuard hoặc traffic selector IPsec không thay cho ma trận trên.** Cần enforcement tại gateway/firewall/ZTNA và xác minh cả luồng được phép lẫn bị cấm.

### 15.2. Identity-aware segmentation

Nếu tổ chức gắn user/session với virtual IP động, policy phải xác định **identity→address/session mapping theo thời gian**. Nếu IP pool tái sử dụng nhưng firewall policy cache hoặc log không cập nhật, một kết nối cũ có thể bị gán nhầm role.

Với workload thay IP thường xuyên, cân nhắc policy theo identity/nhóm được quản lý nếu gateway hỗ trợ thực thi đáng tin. Dù dùng role, phải bảo vệ quyền sửa nhóm trong IdP, controller và control plane.

### 15.3. Không quên return path

Client có virtual IP 10.77.0.2 tới App 10.20.20.15. Nếu App hoặc gateway nội bộ không có route trả về 10.77.0.0/24 (hoặc NAT phù hợp), request có thể đi đến nhưng response mất. Firewall stateful có thể chặn response đi sai đường.

**Một đường đi VPN thành công phải có chiều đi, chiều về, NAT/route và policy phù hợp ở từng điểm.**

## 16. Logging, giám sát và IDS/IPS đối với VPN

Trong tunnel đã mã hóa, sensor trên Internet thường chỉ nhìn thấy **metadata lớp ngoài** và không đọc được packet IP nội bộ. Khi VPN kết thúc tại gateway, các lớp giám sát phía sau có thể nhìn thấy traffic đã giải mã nếu được đặt đúng chỗ.

~~~mermaid
flowchart LR
    C[Remote Client] -->|Encrypted tunnel| G[VPN Gateway]
    OBS1[External firewall / NIDS] -.Outer metadata.-> G
    G -->|Inner traffic sau kiểm tra| FW[Internal firewall]
    FW --> APP[Application]
    G -.Auth/session logs.-> SIEM[SIEM]
    FW -.Flow/deny logs.-> SIEM
    APP -.App/identity logs.-> SIEM
~~~

### 16.1. Nguồn dữ liệu nên ghép

| Nguồn | Dữ liệu có thể cho biết | Không chứng minh riêng lẻ |
|---|---|---|
| WireGuard peer stats | Last handshake, transfer bytes, peer key identity | User hiện tại đã qua MFA hay đã mở API thành công |
| IKEv2/IPsec gateway | IKE/CHILD SA, authentication result, rekey, tunnel errors | Mọi ứng dụng phía sau đã được cấp quyền |
| TLS VPN gateway | User/session, source IP, endpoint, authorization/profile | Host không nhiễm mã độc |
| IdP/RADIUS/MFA | Identity, policy result, thời điểm xác thực | Người đó thực hiện mọi flow từ endpoint |
| DHCP/IPAM/VPN pool | Mapping IP tunnel với session/peer | Mapping hiện tại đúng cho log lịch sử |
| Firewall/flow/NIDS | Source, destination, port, rule, allow/deny, behavior | Một deny nghĩa tấn công thành công |
| EDR/MDM | Thiết bị, posture, process theo khả năng agent | Tất cả traffic ở các host khác |
| App/SSH/DB logs | Đăng nhập/authorization và kết quả nghiệp vụ | Toàn bộ đường mạng an toàn |

### 16.2. Những trường quan trọng cho VPN log

- Event time có timezone/UTC và ingest time.
- Gateway instance/region và version chính sách.
- Peer key ID hoặc certificate fingerprint, **không log private key**.
- User identity, IdP session/role và MFA result khi có.
- Device ID/posture status và phương thức quản trị nếu có.
- Public source IP/port, virtual tunnel IP, routing domain.
- Session start/end, reconnect/rekey, nguyên nhân lỗi.
- VPN protocol/transport, cipher/profile được thương lượng khi áp dụng.
- Rule/zone, đường vào những tài nguyên quan trọng.
- Alert mất log/collector, clock drift hoặc HA failover.

**Gắn một event với user phải dựa trên mapping tại thời điểm đó.** NAT, DHCP, VPN IP pool và cloud workload đều có thể tái sử dụng địa chỉ.

### 16.3. Phát hiện bất thường

Các tín hiệu đáng xem:
- Nhiều đăng nhập thất bại vào gateway hoặc account.
- Một user đăng nhập từ thiết bị/địa điểm khác baseline (cần thận trọng với IP geolocation).
- Client mới truy cập nhiều subnet/port quản trị ngoài role.
- Peer key/certificate từng bị thu hồi vẫn cố kết nối.
- Tăng session, CPU, handshake errors hoặc tunnel churn.
- Đổi route/DNS/role bất thường sau kết nối.
- Khối lượng egress từ tài sản nhạy cảm vượt baseline.

Một cảnh báo này **không tự chứng minh account bị chiếm**. Cần xác minh IdP/EDR, thay đổi kinh doanh, NAT/ISP và kết quả ứng dụng.

## 17. Gateway HA, route failover và độ sẵn sàng

Remote-access VPN có thể trở thành điểm lỗi tập trung. Khi gateway mất, việc hai ISP vẫn hoạt động không đủ để duy trì phiên.

### 17.1. Các câu hỏi HA cần trả lời

- Có nhiều gateway/region/AZ không, hoạt động active-active hay active-standby?
- Client khám phá gateway dự phòng bằng DNS, load balancer hay cơ chế của sản phẩm?
- Khi endpoint/gateway IP đổi, WireGuard/IPsec/TLS VPN có cần re-handshake hoặc reconnect không?
- Có chia sẻ session/SA state không, hay application session phải khởi tạo lại?
- Tunnel IP/DNS/route có đổi làm rơi các TCP session đang mở không?
- Backend firewall/ACL và policy giống nhau trên mọi gateway?
- Gateway còn đủ CPU, băng thông và license khi toàn bộ user dồn về một phía?
- Monitoring, IdP, PKI và DNS có đường dự phòng tương ứng không?

### 17.2. Failover không bảo đảm continuity của mọi kết nối

Một gateway mới có thể không sở hữu session state cũ, và public IP/source NAT có thể đổi. Giao thức/client có thể phục hồi tunnel nhanh nhưng **TCP/SSH/DB session đang mở vẫn có thể mất**, tùy topology và hỗ trợ HA.

Nên định nghĩa:
- **Tunnel reconnection time**.
- **Application recovery time** cho giao dịch mới.
- **Session continuity** riêng cho phiên đang mở.
- **Security policy parity** khi chuyển gateway.
- **Failback stability** và các lỗi flapping.

### 17.3. Lưu lượng quản trị khi sự cố

Đường truy cập **out-of-band** tới gateway, PKI và control plane quan trọng nếu sự cố VPN chặn chính nhóm vận hành. Tuy nhiên OOB cũng phải được bảo vệ bằng identity, MFA, logging và quy trình emergency access.

## 18. MTU, encapsulation, latency và năng lực gateway

Một tunnel thêm header/metadata, làm **effective MTU** của packet bên trong giảm so với đường vật lý. Nếu không được xử lý, có thể xuất hiện tình huống **ping nhỏ thành công nhưng tải file hoặc TLS handshake lớn lại chậm/timeout**.

### 18.1. MTU và Path MTU Discovery

- WireGuard thường chạy qua UDP và thêm overhead của UDP/IP/tunnel.
- IPsec ESP/NAT-T thêm overhead theo mode, cipher và đường NAT.
- TLS VPN có thêm overhead của transport, TLS/control/data framing và interface tunnel tùy sản phẩm.
- Với IPv4/IPv6, Path MTU Discovery và ICMP lỗi liên quan cần hoạt động phù hợp.
- TCP MSS clamping có thể là một công cụ xử lý một số tình huống TCP tunnel, không thay cho sửa nguyên nhân.

Không dùng một MTU “chuẩn cho mọi VPN” khi môi trường còn có PPPoE, GRE, cloud overlay hoặc IPsec bọc thêm nhiều lớp. Hãy đo và kiểm chứng ở đường thực tế được cấp phép.

### 18.2. Đo throughput/latency công bằng

Nếu benchmark ba lựa chọn, giữ các điều kiện giống nhau:
- Cùng client/server, OS/kernel, CPU và năng lực NIC.
- Cùng đường mạng, loss/jitter, cùng tải và thời điểm.
- Cùng policy firewall, logging và TLS/application workload.
- Đo cả **single flow và multi-flow** nếu cần.
- Có thử small/large packet, long-lived session, reconnect và roaming.
- Theo dõi CPU per packet, packet drop, p95/p99 và application success.

**Throughput VPN cao không bảo đảm latency ứng dụng thấp**, nếu DB, DNS, authentication hoặc route backend là nút nghẽn.

### 18.3. DDoS và bảo vệ gateway

VPN gateway có thể đối mặt với:
- UDP/ESP floods hoặc lưu lượng kết nối lớn.
- IKE/TLS handshake/authentication overload.
- Credential stuffing/password spraying vào cổng đăng nhập.
- Khai thác lỗ hổng sản phẩm, giao diện quản trị public.
- Log pipeline đầy và monitoring bị mất trong giờ cao điểm.

Cần bảo vệ **network edge, rate limiting/anti-abuse phù hợp, patching, MFA, admin plane isolation, upstream DDoS protection và capacity/HA**. Không công bố địa chỉ quản trị gateway trên cùng giao diện truy cập người dùng nếu không có chính sách bảo vệ phù hợp.

## 19. Quy trình ra quyết định có cấu trúc

Để chọn VPN, nhóm kiến trúc nên viết **yêu cầu bắt buộc** trước rồi mới đánh giá ưu/nhược điểm.

### 19.1. Bước 1 — Xác định use case

- Nhân viên từ xa truy cập app theo role?
- Kỹ sư cần SSH/RDP vào jump host?
- Chi nhánh kết nối trung tâm qua hai ISP?
- Đối tác BYOD chỉ cần một website?
- Service cloud liên lạc tới data center?
- Thiết bị IoT/OT không có khả năng cài client mới?

**Không gộp những use case này vào một kết luận chung.**

### 19.2. Bước 2 — Phân loại yêu cầu bắt buộc

Ví dụ:

| Nhóm | Câu hỏi / yêu cầu |
|---|---|
| Identity | SSO, MFA, user/device certificate, posture có bắt buộc? |
| Connectivity | Chỉ TCP/443 được phép hay UDP/IKEv2 dùng được? |
| Application | Truy cập full subnet, một ứng dụng web, SSH/RDP hay UDP custom? |
| Client | OS/browser/version có hỗ trợ, có cần agent? |
| Security | Quản lý khóa, authorization theo role, revoke, audit, segmentation |
| Privacy | DNS/Internet egress, split tunnel, địa điểm xử lý log |
| Availability | Gateway HA, roaming, RTO, failover và capacity |
| Operations | IaC/MDM, API controller, PKI, IdP, monitoring, support |
| Compliance | Yêu cầu thuật toán, chứng chỉ, lưu log, cách đánh giá sản phẩm |
| Cost | License, appliance, cloud egress, support và vận hành |

Nếu một giải pháp **không đáp ứng yêu cầu bắt buộc**, không nên chọn chỉ vì đạt điểm throughput cao.

### 19.3. Bước 3 — Chọn ứng viên phù hợp

Ví dụ khung đánh giá, dùng dấu **cần xác minh** thay vì mặc định PASS:

| Trường hợp | Ứng viên hợp lý để đánh giá trước | Điều kiện bắt buộc kiểm chứng |
|---|---|---|
| Site-to-site router/firewall–cloud managed | IKEv2/IPsec | Profile của provider, BGP, HA, PSK/cert rotation, policy |
| Remote access trên laptop được quản trị | IKEv2/IPsec hoặc TLS VPN; WireGuard có controller | SSO/MFA, posture, revoke, OS client và DNS |
| Remote access trong mạng chỉ cho proxy/HTTPS | TLS VPN phù hợp transport/proxy | Gateway thật sự hỗ trợ mạng/proxy đó và xác thực đúng |
| Tunnel giữa host/service do đội vận hành quản lý | WireGuard hoặc IKEv2/IPsec | Key lifecycle, route, policy và automation |
| Clientless web của đối tác | TLS application portal/proxy | Per-app authorization, MFA, browser/SSO và dữ liệu |
| Thiết bị nhúng ít tài nguyên | Chọn theo stack được hỗ trợ và bảo trì | Cryptographic support, secure key storage và update path |

### 19.4. Bước 4 — Bảng điểm có trọng số

Có thể dùng mô hình nội bộ để so sánh **sản phẩm và cấu hình cụ thể**, không chấm điểm “giao thức trừu tượng”:

~~~text
Điểm ứng viên = tổng (trọng số yêu cầu_i × điểm kiểm chứng_i)

Trọng số tổng = 100%
Điểm kiểm chứng_i: chỉ chấm sau demo/POC/tài liệu đã xác minh
Yêu cầu bắt buộc: FAIL thì loại ứng viên, không cộng điểm bù.
~~~

Một ví dụ phân bổ trọng số cho remote access của doanh nghiệp:

| Tiêu chí | Trọng số minh họa |
|---|---:|
| Xác thực/SSO/MFA, posture và revoke | 30% |
| Phân quyền/segmentation và audit | 25% |
| Client compatibility + NAT/proxy/roaming | 20% |
| HA, performance và DNS | 15% |
| Automation, support, cost | 10% |
| **Tổng** | **100%** |

Các tỷ trọng là ví dụ để giải thích phương pháp, không phải chuẩn công nghiệp. Với kết nối site-to-site, interoperability và dynamic routing có thể cần trọng số cao hơn.

### 19.5. Bước 5 — POC và lựa chọn có điều kiện

Thử kết nối từ **mạng/thiết bị đại diện** và so sánh các sản phẩm theo cùng test matrix. Báo cáo:

- Kịch bản, threat model, requirement ID.
- Sản phẩm/version/profile, không chỉ tên WireGuard/IPsec/TLS VPN.
- Kết quả positive/negative testing và SSO/MFA/revoke.
- Throughput, latency, roaming, NAT/proxy, HA, IPv6/DNS.
- Đường quản trị, audit, ownership và cost.
- Các giới hạn đã biết và phương án giảm rủi ro.

## 20. Ma trận kiểm thử trước khi triển khai

| ID | Điều kiện | Kỳ vọng | Nguồn bằng chứng |
|---|---|---|---|
| T01 | Client được cấp quyền, gateway bình thường | Kênh được xác thực và tunnel/portal hoạt động | VPN session + identity log |
| T02 | Chứng chỉ gateway sai/tên không khớp | Client từ chối xác thực sai | TLS/IKE client logs |
| T03 | Peer key/client cert không được cấp phép | Không mở quyền truy cập | Gateway deny + config |
| T04 | Tài khoản chưa hoàn tất MFA | Không cấp session theo policy | IdP + VPN gateway logs |
| T05 | User hợp lệ truy cập app được cấp quyền | HTTPS/API transaction thành công | Firewall + app logs |
| T06 | User thường truy cập DB quản trị trực tiếp | Bị deny | Gateway/segmentation logs |
| T07 | Peer/user được thu hồi | Không tạo mới session; xử lý session đang có theo policy | Revocation + session logs |
| T08 | Client chuyển Wi-Fi sang mạng di động | Reconnect/roam theo mục tiêu | Client logs + app SLO |
| T09 | IPv4 full tunnel | Không rò traffic ngoài policy | Route, firewall, flow |
| T10 | IPv6 dual-stack | IPv6 đi đúng policy hoặc bị hạn chế rõ ràng | IPv6 route/flow |
| T11 | Truy vấn tên private qua VPN | Resolver được duyệt, đáp ứng đúng | DNS client + resolver logs |
| T12 | Browser dùng DoH riêng | Không bypass private DNS/policy ngoài ý muốn | Browser settings + DNS telemetry |
| T13 | Client sau CGNAT | Kết nối được nếu transport được phép | Outer flow, handshake, session |
| T14 | Client trong mạng có HTTP proxy | Chỉ PASS khi sản phẩm hỗ trợ cấu hình này | Client/proxy/gateway logs |
| T15 | Gateway primary mất trong lab | Backup hoạt động, vẫn giữ access policy | HA, routing, app logs |
| T16 | MTU thấp hơn đường chính | Request dữ liệu lớn không treo ngoài ngưỡng | PMTU/trace/app logs |
| T17 | DNS hoặc IdP tạm lỗi | Fallback đúng policy, không tự mở quyền | Gateway/IdP logs |
| T18 | Device posture không đạt | Không cấp tài nguyên nhạy cảm | MDM/EDR + policy |
| T19 | User logout/disable account | Phiên và quyền được thu hồi theo thiết kế | IdP/VPN/app events |
| T20 | Sensor/SIEM pipeline lỗi | Có cảnh báo thiếu telemetry | Health/ingestion logs |
| T21 | Tunnel hoạt động nhưng route trả lời thiếu | Phát hiện lỗi và không đánh dấu PASS giả | Route/NAT + flow |
| T22 | Gateway quá tải theo POC được duyệt | Thời gian/chi phí phục vụ trong giới hạn thiết kế | CPU/pps/bandwidth/SLO |

Không test nào nên được ghi **PASSED** nếu không có thời gian, môi trường, dữ liệu kiểm chứng và owner. Những ca làm gián đoạn phải chạy trong **lab hoặc change window được phê duyệt** với rollback.

### 20.1. Hai loại thử nghiệm bảo mật quan trọng

**Positive tests**: tài khoản/thiết bị được phép truy cập đúng ứng dụng qua VPN và hoàn thành giao dịch.

**Negative tests**: khóa bị thu hồi, cert sai, user chưa MFA, device không đạt posture, guest/employee truy cập DB hoặc management trái quyền **vẫn bị chặn**.

Chỉ kiểm thử “tunnel connected” mà không kiểm thử negative cases là chưa đủ để chốt giải pháp.

## 21. Thực hành quan sát an toàn trên máy được quản trị

Các lệnh dưới đây nhằm **xem thông tin** trong lab hoặc trên máy đã được cấp quyền. Không cần tự triển khai gateway thật hoặc thử cấu hình vào hệ thống sản xuất.

### 21.1. Linux: kiểm tra route và interface

~~~bash
# Xem interface và các địa chỉ IPv4/IPv6
ip -br addr

# Xem route hiện hành
ip -4 route show
ip -6 route show

# Xem luật policy routing
ip rule show

# Xem địa chỉ DNS và routing domains nếu dùng systemd-resolved
resolvectl status
~~~

Nếu máy dùng **WireGuard** và người học được cấp quyền kiểm tra:

~~~bash
# Hiển thị trạng thái WireGuard peer/handshake/transfer, không xuất private key
sudo wg show

# Quan sát quyết định route tới một server private của lab
ip route get 10.20.20.15
~~~

**Lưu ý:** output một số lệnh có thể chứa public IP, peer public key và tên interface nhạy cảm; không chia sẻ ra ngoài phạm vi quản trị. **Không dùng lệnh xuất toàn bộ cấu hình bao gồm private key** trong tài liệu, log hoặc ticket.

### 21.2. Windows PowerShell: kiểm tra mạng client

~~~powershell
# Xem interface/địa chỉ và route
Get-NetIPConfiguration
Get-NetRoute |
  Select-Object DestinationPrefix, NextHop, InterfaceIndex, RouteMetric

# Xem DNS server mà OS được cấu hình
Get-DnsClientServerAddress

# Kết nối kiểm tra TCP tới endpoint lab do mình quản trị
Test-NetConnection -ComputerName 10.20.20.15 -Port 443
~~~

Lệnh Test-NetConnection tạo một phép thử kết nối nhỏ tới port TCP; **không chứng minh tunnel bảo mật hoặc ứng dụng đã xác thực thành công**. Với sản phẩm VPN cụ thể, xem client/gateway logs theo hướng dẫn nhà sản xuất và chính sách doanh nghiệp.

### 21.3. IPsec trạng thái không đồng nghĩa application success

Nếu thiết bị/gateway có giao diện đọc status IKE/CHILD SA, cần kiểm tra:

- Peer được xác thực nào, đúng identity/certificate không.
- IKE SA/CHILD SA có up/rekey đúng.
- Traffic selectors, next-hop, route và NAT-T.
- Counters hai chiều, replay/authentication failures.
- Session/route sau khi roaming hoặc HA failover.

Sau đó mới kiểm tra ứng dụng thông qua request nhỏ **được cấp quyền**. Không lấy trạng thái “IKE SA established” làm bằng chứng app đã hoàn thành giao dịch.

### 21.4. TLS VPN status không đồng nghĩa HTTPS tới app thành công

VPN portal có thể xác thực user thành công nhưng backend API vẫn trả 403, TLS certificate app sai hoặc proxy không hỗ trợ protocol cần dùng. Nên kiểm tra:
- Gateway/portal authentication và authorization decision.
- Per-app route/proxy rule.
- HTTPS/TLS chứng chỉ backend.
- Response code và application-level logs.
- Session timeout/SSO token refresh.

## 22. Quy trình triển khai có kiểm soát

### Giai đoạn A — Chuẩn bị thiết kế

1. Xác định danh sách tài sản, mạng, ứng dụng và nhóm người dùng.
2. Chọn **loại truy cập cần cấp**: full network, subnet, per-app hoặc site-to-site.
3. Dựng threat model và tiêu chí đánh giá theo mục 19.
4. Thống nhất identity provider, MFA, device posture, secret/PKI, authorization.
5. Thiết kế DNS, split/full tunnel, IPv6, NAT, firewall và route return.
6. Chọn HA, capacity, monitoring, lifecycle và phương án recovery.
7. Review data protection, logging retention và quyền truy cập.
8. Có owner, approval và tài liệu rollback.

### Giai đoạn B — Pilot

1. Chọn nhóm thiết bị/OS và vị trí mạng đại diện.
2. Cấp identity/key/cert qua kênh an toàn, không dùng cùng credential cho nhiều thiết bị.
3. Áp policy theo nhóm nhỏ, mặc định không mở toàn bộ subnet.
4. Chạy positive và negative tests.
5. Đo roaming, latency, DNS, IPv6, captive portal và client compatibility.
6. Thu phản hồi user và số liệu vận hành.
7. Sửa lỗi mà không tắt certificate validation/MFA để “cho chạy”.

### Giai đoạn C — Mở rộng và vận hành

1. Gán quyền/thiết bị theo quy trình onboarding.
2. Tự động hóa certificate/key rotation và revoke nơi được hỗ trợ.
3. Theo dõi VPN active sessions, auth failures, gateway health, HA và bandwidth.
4. Tương quan traffic với firewall/IDS/EDR/app logs.
5. Review access groups, idle peers và các key/cert không sử dụng.
6. Cập nhật bản vá hệ điều hành, client/gateway và control plane.
7. Diễn tập failover, expired cert, mất thiết bị và sự cố IdP/DNS.
8. Hủy quyền khi offboarding và bảo toàn audit theo retention.

### Giai đoạn D — Thay đổi hoặc thay thế giao thức

Nếu chuyển từ TLS VPN sang IKEv2 hoặc WireGuard, cần **giai đoạn song song có kiểm soát**:
- Mapping lại user/group/role, route, DNS, app access và posture.
- Thu hồi credential ở VPN cũ sau khi kiểm tra VPN mới.
- Bảo đảm không có đường bypass do cả hai gateway cùng mở rộng policy.
- Đo ảnh hưởng tới ứng dụng và các session lâu dài.
- Có rollback được phê duyệt và thời hạn ngừng hệ thống cũ.

Không coi đổi giao thức là tự động cải thiện bảo mật nếu **quyền, key hygiene và giám sát** vẫn yếu như trước.

## 23. Những rủi ro và sai lầm phổ biến khi lựa chọn VPN

1. **Chọn chỉ theo throughput benchmark.** Bỏ qua MFA, posture, revoke và least privilege.
2. **Gọi WireGuard “không thể có MFA”.** Lõi không có MFA nhưng giải pháp controller có thể tích hợp, phải kiểm chứng.
3. **Cho mọi WireGuard peer cùng AllowedIPs rất rộng trên gateway.** Dễ mất ranh giới phân biệt peer và routing policy.
4. **Coi AllowedIPs là ứng dụng firewall toàn diện.** Nó không thay thế quyền theo user/app.
5. **Dùng chung một WireGuard private key cho cả nhóm.** Khó truy nguồn và thu hồi từng thiết bị.
6. **Không có key rotation/revoke process.** Thiết bị cũ hoặc thất lạc có thể còn quyền.
7. **Cho rằng IKEv2 luôn có MFA.** Cần cấu hình EAP/IdP/gateway và client cụ thể.
8. **Bỏ qua kiểm tra cert gateway.** Client có thể tin sai đầu kết nối hoặc bị điều hướng.
9. **Coi IPsec = chỉ UDP/500.** NAT-T, ESP và routing traffic có yêu cầu khác.
10. **Nói ESP dùng TCP/50.** ESP là IP protocol 50, không phải TCP port 50.
11. **Đồng nhất mọi TLS VPN với HTTPS tunnel trên 443.** Sản phẩm khác nhau về control/data channel và transport.
12. **Cho rằng TLS VPN qua mọi proxy.** HTTP proxy/TLS inspection có thể chặn hoặc yêu cầu support riêng.
13. **Giả định UDP chắc chắn nhanh hơn.** Cần đo thực tế theo path/loss/CPU/policy.
14. **Không xét TCP-over-TCP khi tunnel trên TCP.** Một số đường mất gói có thể suy giảm đáng kể.
15. **Chọn full tunnel nhưng quên IPv6.** Có thể rò egress ngoài VPN hoặc làm lỗi ứng dụng.
16. **Split tunnel nhưng quên DNS private zone.** Browser hoặc OS không phân giải được hostname nội bộ.
17. **Mở route vào Data/Management cho mọi user.** VPN kết nối đúng vẫn có nguy cơ lateral movement.
18. **Không kiểm tra return path/NAT.** Tunnel up nhưng ứng dụng không nhận response.
19. **Chỉ nhìn handshake/SA rồi đánh dấu PASS.** Cần kiểm chứng application-level success.
20. **Không test certificate/key revocation.** Quyền còn tồn tại sau khi mất thiết bị hoặc user nghỉ.
21. **Không test mạng khách sạn, CGNAT, IPv6 và roaming.** Pilot mạng LAN có thể tạo cảm giác thành công giả.
22. **Không giám sát đường sau giải mã.** NIDS Internet không thấy payload bên trong tunnel.
23. **VPN HA không có identity/DNS dự phòng.** Gateway còn hoạt động nhưng user vẫn không đăng nhập/giải quyết tên.
24. **Chặn traffic ngoài policy bằng cách tắt TLS verification.** Làm mất bảo vệ identity của gateway.
25. **Thiếu bảo vệ admin plane.** Gateway có MFA cho user nhưng giao diện cấu hình lại bị lộ và yếu.
26. **Tin rằng VPN thay thế HTTPS, DB auth hoặc ứng dụng ZTNA.** Các lớp kiểm soát có mục tiêu khác nhau.
27. **Không kiểm thử negative case.** Một quyền bị cấm vẫn mở có thể nguy hiểm hơn việc app tạm chậm.
28. **Không có owner và incident response.** Khi lộ khóa hoặc gateway lỗi, không biết ai chịu trách nhiệm.

## 24. Tình huống thực hành và đáp án gợi ý

### Tình huống A — Nhóm phát triển có 200 laptop được quản trị

Doanh nghiệp có IdP, MFA, MDM, VPN gateway sẵn và yêu cầu truy cập HTTPS/API nội bộ từ Windows/macOS/Linux.

**Câu hỏi:** nên chọn giao thức nào?

**Gợi ý:** lập yêu cầu bắt buộc SSO/MFA/posture/revoke, client OS, DNS/split tunnel và logging rồi POC **IKEv2/IPsec, TLS VPN** hoặc **WireGuard có controller hỗ trợ identity**. Không thể kết luận một giao thức thuần túy chỉ từ số người dùng; nên chọn **triển khai** đáp ứng các tiêu chí.

### Tình huống B — Kỹ sư dùng WireGuard để vào Management

Tunnel kết nối được, nhưng key của mọi người dùng chung một public key và AllowedIPs được cấu hình quá rộng. Firewall phía sau gateway cho phép mọi VPN client vào tất cả subnet.

**Gợi ý:** cấp **khóa riêng cho từng thiết bị**, xác định danh tính/owner, quy trình revoke, tách role và subnet/quyền. Cấu hình firewall mặc định deny tới DB/Management trừ vai trò được duyệt. Không coi handshake thành công là đủ bảo mật.

### Tình huống C — IKEv2 thất bại trong Wi-Fi khách sạn

Laptop truy cập website HTTPS được nhưng IKEv2 luôn timeout khi thiết lập SA.

**Gợi ý:** xác minh UDP/500/4500, ESP/NAT-T, DNS endpoint, gateway logs, NAT và policy mạng. Có thể mạng hạn chế UDP; một **TLS VPN có transport phù hợp và được phê duyệt** có thể là phương án khác, nhưng phải kiểm chứng proxy, cert, MFA và policy. Không cố vượt hạn chế mạng trái quyền.

### Tình huống D — Đối tác chỉ cần portal tài liệu

Đối tác dùng BYOD chỉ cần một web app, không cần truy cập subnet hay giao thức custom.

**Gợi ý:** xem **TLS application portal/proxy với SSO/MFA, per-app authorization và session controls** thay vì cấp full L3 VPN. Đánh giá posture, DLP và khả năng proxy ứng dụng theo sản phẩm; không coi clientless tự an toàn.

### Tình huống E — Tunnel lên, DB vẫn không truy cập được

Client nhận virtual IP 10.77.0.2, route App subnet đúng, nhưng request TCP/5432 timeout.

**Gợi ý:** kiểm tra **đúng destination**, firewall role/zone, route phản hồi, NAT, DB listener, MTU và DB authentication. Handshake/tunnel status không chứng minh TCP path hoặc DB authorization.

### Tình huống F — Client đổi Wi-Fi sang 4G

WireGuard có handshake lại sau chuyển mạng; IKEv2 client khác phải kết nối mới. Ứng dụng WebSocket vẫn mất một khoảng thời gian.

**Gợi ý:** phân biệt **roaming của peer, thiết lập lại VPN và khả năng phục hồi của session ứng dụng**. Với IKEv2 kiểm tra MOBIKE/DPD nếu được hỗ trợ; với WireGuard kiểm tra UDP/NAT. Đánh giá SLO ứng dụng thay vì chỉ đo thời gian handshake.

### Tình huống G — Full tunnel bị DNS/IPv6 leak

IPv4 Internet traffic qua VPN, nhưng truy vấn DNS/HTTPS từ browser một số lần đi ra ngoài qua IPv6 hoặc DoH resolver riêng.

**Gợi ý:** kiểm tra route ::/0, IPv6 firewall, browser enterprise DoH policy, OS resolver, DNS suffix và kill switch. Không khẳng định “full tunnel” khi chỉ mới kiểm chứng IPv4.

### Tình huống H — Nhân viên nghỉ nhưng vẫn có session

IdP đã disable account nhưng client vẫn giữ tunnel đang mở một khoảng thời gian.

**Gợi ý:** xác định cơ chế revoke session tại gateway, token caching, cert/peer key còn được phép và thời điểm re-auth/rekey. Cần offboarding tích hợp cả IdP **và** VPN controller/gateway, không giả định disable ở một nơi sẽ vô hiệu ngay mọi quyền.

### Tình huống I — Hai data center cần kết nối thường trực

Hai bên có firewall/router hỗ trợ IPsec managed, cần dynamic routing BGP và failover, peer public IP ổn định.

**Gợi ý:** **IKEv2/IPsec route-based** thường là ứng viên thực tế để POC nhờ interoperability và tính năng của thiết bị, nhưng phải kiểm tra selectors, crypto proposals, BGP, HA, NAT-T, route filters, log và quyền ứng dụng. WireGuard cũng có thể đánh giá nếu hai đầu quản trị được và đủ hỗ trợ.

### Tình huống J — TLS VPN qua TCP hoạt động nhưng tải file chậm

Kết nối qua mạng mất gói; dữ liệu ứng dụng TCP đi trong VPN data channel vận chuyển TCP.

**Gợi ý:** xem packet loss, retransmissions, head-of-line blocking, tunnel CPU/MTU, TCP-over-TCP và throughput. Đánh giá UDP transport phù hợp trong lab nếu sản phẩm hỗ trợ; không chỉ tăng băng thông khi nút nghẽn nằm ở packet loss.

### Tình huống K — VPN chuyển gateway sau sự cố

Gateway A lỗi, client kết nối lại gateway B và nhận virtual IP khác. SSH session cũ bị mất, nhưng HTTPS request mới hoạt động.

**Gợi ý:** phân biệt **reconnection và session continuity**. Kịch bản có thể đạt RTO cho giao dịch mới nhưng không đạt tiêu chí giữ session nếu đó là yêu cầu bắt buộc. Kiểm tra policy parity và negative cases khi chuyển gateway.

### Tình huống L — VPN an toàn nhưng truy cập trái quyền được phép

Client Employee kết nối qua IKEv2 chứng chỉ hợp lệ và MFA thành công. Sau đó có thể truy cập SSH tới máy quản trị vì firewall cho toàn VPN subnet vào Management.

**Gợi ý:** **thất bại về authorization và segmentation** dù tunnel có mật mã đúng. Thu hẹp rule theo identity/role, chỉ cho đường cần thiết qua jump host, kiểm chứng denied flows và review mapping từ session VPN sang firewall.

## 25. Checklist chọn và vận hành WireGuard, IPsec và TLS VPN

- [ ] Xác định remote access, site-to-site hay per-app access; không gộp yêu cầu.
- [ ] Có threat model, tài sản nhạy cảm, trust boundary và hành vi đối thủ.
- [ ] Có tiêu chí bắt buộc SSO/MFA, device posture, PKI/key lifecycle và revoke.
- [ ] Biết mỗi giao thức/triển khai xác thực **gateway, thiết bị, user** ra sao.
- [ ] Đã phân biệt WireGuard public key/AllowedIPs với authorization ứng dụng.
- [ ] Đã phân biệt IKEv2 control SA/CHILD SA, ESP và NAT-T.
- [ ] Đã kiểm tra TLS VPN là full tunnel, application portal hay data channel riêng.
- [ ] Đã xác minh transport, port và khả năng đi qua NAT/proxy/captive portal.
- [ ] Đã kiểm tra tính tương thích OS, client version và MDM/endpoint management.
- [ ] Đã đánh giá thuật toán, certificate validation, crypto proposals và key storage.
- [ ] Mỗi peer/device có identity/credential riêng hoặc cơ chế truy nguồn tương đương.
- [ ] Có lịch rotate/revoke keys, certs, tokens, sessions và quy trình offboarding.
- [ ] Có ma trận allow/deny từ từng VPN role tới ứng dụng, DB và Management.
- [ ] Có kiểm chứng return route, NAT, stateful firewall và HA trên các đường.
- [ ] Quyết định split/full tunnel có xét IPv4, IPv6, DNS, DoH và kill switch.
- [ ] Có resolver private, split DNS, DNS policy và tránh leak theo yêu cầu.
- [ ] Có kiểm tra chuyển Wi-Fi/4G, CGNAT, mất UDP và reconnect.
- [ ] Có capacity test được duyệt, MTU/PMTUD, latency, session limits và gateway CPU.
- [ ] Có gateway HA, IdP/DNS/PKI availability và kịch bản failback.
- [ ] Có log session/identity/virtual IP, firewall/IDS/EDR và app transactions.
- [ ] Có monitoring gateway health, denied logins, brute-force signals và log loss.
- [ ] Có quyền quản trị gateway tách biệt, MFA và audit thay đổi policy.
- [ ] Có positive và negative test cases, không chỉ test tunnel “connected”.
- [ ] Có quy trình rollback khi pilot hoặc migration ảnh hưởng người dùng.
- [ ] Có owner, tài liệu vận hành, incident runbook và review định kỳ.
- [ ] Có báo cáo so sánh **sản phẩm + cấu hình + môi trường**, không chỉ tên giao thức.

## 26. Tổng kết

**WireGuard, IPsec và TLS VPN** đều có thể là lựa chọn tốt nếu chúng phù hợp với bối cảnh và được triển khai đúng. **WireGuard** nổi bật với mô hình peer public key rõ ràng và tunnel UDP gọn, nhưng thường cần lớp quản trị danh tính/MFA và vòng đời key bổ sung. **IKEv2/IPsec** là lựa chọn rất thực tế cho nhiều thiết bị mạng, site-to-site và remote access nhờ hệ sinh thái hiện có, với điều kiện cấu hình chuẩn xác SA, crypto, PKI/EAP và NAT-T. **TLS VPN** bao phủ cả routed tunnel lẫn portal/proxy ứng dụng, thuận lợi trong một số môi trường HTTPS/SSO nhưng cần xem cụ thể data channel, proxy support và quyền theo ứng dụng.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, lựa chọn đúng không chỉ bảo vệ packet trên đường đi mà còn phải **xác thực đúng người và thiết bị, thu hẹp quyền sau tunnel, giữ DNS/IPv6/route đúng chính sách, kiểm chứng luồng được phép và bị cấm, giám sát IDS/IPS, bảo vệ gateway và thu hồi quyền kịp thời**. Quyết định nên được chốt bằng **ma trận yêu cầu, proof of concept và bằng chứng kiểm thử end-to-end**, thay vì khẳng định một giao thức luôn an toàn hoặc nhanh hơn tất cả giao thức khác.
