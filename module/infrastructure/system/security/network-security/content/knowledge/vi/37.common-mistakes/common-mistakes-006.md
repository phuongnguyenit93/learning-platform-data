# Sai lầm: Không bảo vệ kênh quản trị trong bảo mật mạng

## 1. Bản chất sai lầm: bảo vệ lưu lượng người dùng nhưng bỏ quên đường điều khiển

Một doanh nghiệp có thể đã phân đoạn VLAN, cấu hình firewall khá chặt, triển khai VPN, IDS/IPS và DNS filtering nhưng vẫn để giao diện quản trị của router, switch, firewall, access point, hypervisor hoặc cloud controller truy cập bằng giao thức yếu hay từ mạng không đáng tin. **Đây là lỗi thiết kế và vận hành có thể vô hiệu hóa nhiều lớp phòng thủ cùng lúc.**

**Kênh quản trị (management channel)** là đường mà người hoặc hệ thống tự động sử dụng để đọc trạng thái, thay cấu hình, cấp quyền, cập nhật firmware, xoay vòng chứng chỉ hoặc thao tác khẩn cấp trên hạ tầng. Kênh này bao gồm cả đường mạng và toàn bộ chuỗi kiểm soát: thiết bị quản trị, giao thức, danh tính, quyền, điểm trung gian, API, secrets, audit và đường khôi phục.

Sai lầm **“Không bảo vệ kênh quản trị”** có nhiều hình thức:

- Dùng **Telnet, HTTP, FTP hoặc SNMPv1/v2c** để truy cập hoặc giám sát thiết bị qua đoạn mạng có khả năng bị nghe lén.
- Bật SSH/HTTPS nhưng **không xác minh host key hoặc chứng chỉ**, chấp nhận cảnh báo của client theo thói quen.
- Để cổng quản trị reachable từ **Internet, guest Wi-Fi, user VLAN hoặc subnet không liên quan**.
- Dùng một tài khoản `admin` chung, mật khẩu mặc định hoặc token API không có giới hạn; thiếu MFA/PAM và tách quyền.
- Đặt private key, token, backup cấu hình hoặc credential trong script/CI log không bảo vệ.
- Không ghi log thao tác hoặc cho phép cùng một quyền admin xóa log, tắt IDS/IPS và thay rule.
- Để đường **out-of-band (OOB)**, console server, API cloud/controller hoặc kênh bảo trì của nhà cung cấp thành cửa hậu ít được giám sát.
- Thay đổi ACL/SSH/TLS mà không có đường rollback, khiến người quản trị tự khóa quyền truy cập và phải mở lại kênh yếu để cứu hệ thống.

Bài học thuộc chương **Sai lầm thường gặp** trong module **SECURITY_NETWORK_SECURITY**. Mục tiêu không chỉ là nhớ “hãy bật SSH/HTTPS”, mà là **nhìn thấy các trường hợp đã dùng mã hóa nhưng vẫn không an toàn, biết xác minh bằng chứng và thiết kế biện pháp bù trừ** cho firewall, VPN, IDS/IPS, DNS, Wi-Fi, cloud và hệ thống điều khiển mạng.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích vì sao management plane là tài sản có mức ảnh hưởng cao và khác lưu lượng ứng dụng thông thường.
2. Liệt kê các giả định sai và lỗi cấu hình dẫn tới kênh quản trị bị nghe lén, giả mạo hoặc lạm dụng.
3. Phân biệt **mã hóa**, **xác thực peer**, **xác thực người dùng**, **phân quyền**, **giới hạn mạng** và **khả năng kiểm toán**.
4. Kiểm tra mức phơi bày theo từng nguồn truy cập, IPv4/IPv6, VPN, OOB và cloud control plane.
5. Thực hiện đánh giá an toàn có phạm vi đối với SSH, HTTPS/TLS, SNMPv3, API và đường log.
6. Thiết kế quy trình chuyển đổi khỏi kênh yếu mà không tự cắt quyền khôi phục.
7. Phân loại rủi ro, xử lý sự cố và theo dõi hiệu quả khắc phục bằng metric/bằng chứng.
8. Nhận diện ngoại lệ trên thiết bị cũ/OT và áp dụng kiểm soát bù trừ có thời hạn.

> **Nguyên tắc trọng tâm:** **Kênh mã hóa chưa chắc là kênh quản trị an toàn.** Phải đồng thời bảo vệ **đường đi, đầu cuối, danh tính, quyền, secret, sự kiện và phương án khôi phục**.

## 2. Phân biệt management plane, control plane và data plane

| Mặt phẳng | Vai trò | Ví dụ | Tác động khi bị lạm dụng |
|---|---|---|---|
| **Data plane** | Chuyển tiếp, lọc hoặc xử lý traffic đang đi qua | Firewall forwarding, switch ASIC, reverse proxy | Nghe lén, làm gián đoạn hoặc định tuyến sai traffic |
| **Control plane** | Xác lập trạng thái điều khiển: tuyến, phiên, policy và logic mạng | Routing protocols, SDN controller, policy decision | Thay đổi đường đi, mở rộng vùng ảnh hưởng |
| **Management plane** | Cấu hình, quản trị quyền, giám sát, backup và nâng cấp | SSH CLI, HTTPS UI/API, SNMP, NETCONF, cloud console | Đổi rule, cấp tài khoản, tắt kiểm soát, xóa dấu vết |

Các mặt phẳng có thể dùng chung phần cứng và interface. Một firewall vừa xử lý packet qua data plane, vừa có HTTPS/SSH để quản trị. Nếu quản trị viên có thể tắt kiểm tra IPS hoặc sửa policy NAT, **chiếm management plane có thể làm mất ý nghĩa của data-plane segmentation**.

Một địa chỉ IP quản trị trong subnet private cũng **không tự trở thành an toàn**. Từ guest Wi-Fi, máy người dùng nhiễm mã độc, VPN quá rộng quyền, peering VPC hoặc laptop của nhà cung cấp có thể tồn tại route vào subnet đó.

### 2.1. Tại sao mức độ ưu tiên thường cao?

Giả sử có ba lỗ hổng: một web app lộ dữ liệu của một dịch vụ; một switch quản trị cho phép sửa VLAN; một firewall manager có quyền đẩy policy tới 100 thiết bị. Mức độ ưu tiên **không thể đánh giá chỉ bằng số cổng mở**. Quyền quản trị càng rộng thì **blast radius** khi bị chiếm càng cao.

Nhưng cũng không mặc định mọi SSH reachable đều là rủi ro nghiêm trọng giống nhau: cần xét nguồn có thể tiếp cận, MFA, host key verification, account role, đường OOB, log và kiểm soát bù trừ.

## 3. Mô hình đe dọa của một phiên quản trị

~~~mermaid
flowchart LR
    A["Admin workstation / automation runner"] --> B["VPN / ZTNA / PAM / bastion"]
    B --> C["Management VLAN / VRF / firewall"]
    C --> D["SSH / HTTPS / API / SNMPv3 service"]
    D --> E["Router, switch, firewall, IDS, DNS, controller"]
    A -. "malware / credential theft" .-> T["Rủi ro"]
    B -. "identity/session abuse" .-> T
    C -. "routing/ACL exposure" .-> T
    D -. "MITM / weak TLS / legacy protocol" .-> T
    E -. "excessive privilege / missing audit" .-> T
~~~

Các nhóm rủi ro gồm:

- **Nghe lén:** mật khẩu, community string, lệnh, cấu hình hoặc dữ liệu giám sát đi ở dạng rõ trên đường truyền.
- **Giả mạo endpoint / man-in-the-middle (MITM):** client nghĩ mình đang kết nối đúng router/API nhưng thực chất tới một điểm chèn hoặc proxy không đáng tin.
- **Đánh cắp danh tính và phiên:** private key, bearer token, cookie hoặc thông tin xác thực bị lấy tại endpoint hoặc từ kho secret.
- **Quyền quá rộng:** kênh có TLS hợp lệ nhưng user/app được cấp quyền chỉnh toàn bộ firewall hoặc disable audit.
- **Đường ngoài phạm vi:** một interface, IPv6, NAT, vendor portal hoặc tài khoản cloud bypass mạng quản trị chính.
- **Thiếu phát hiện:** không thể xác định ai đã thay policy, khi nào và vì sao.
- **Mất khả năng khôi phục:** thay ACL/AAA/SSH khiến đường quản trị duy nhất không còn hoạt động, thúc đẩy người vận hành bật lại cơ chế yếu.

**TLS/SSH bảo vệ tính bí mật và toàn vẹn trên từng phiên khi cấu hình/xác minh đúng**, không bảo vệ dữ liệu đã được endpoint giải mã, không ngăn admin hợp lệ làm điều sai và không bảo đảm mọi hop qua proxy đều có bảo vệ.

## 4. Sai lầm số 1: Dùng giao thức quản trị plaintext

### 4.1. Telnet, HTTP và FTP

Telnet thường truyền dữ liệu phiên, bao gồm thông tin xác thực, mà không cung cấp cơ chế mã hóa hiện đại. HTTP plaintext cũng không tạo bảo đảm về bí mật, tính toàn vẹn và danh tính máy chủ. FTP truyền control channel plaintext; việc dùng một cơ chế mã hóa cho riêng đường mạng khác không có nghĩa mọi nơi đều được bảo vệ.

**Sai lầm phổ biến:** “Cổng Telnet chỉ nằm trong LAN, không ai từ Internet truy cập được nên vẫn dùng.” LAN không phải luôn là ranh giới tin cậy: thiết bị người dùng bị nhiễm mã độc, mạng Wi-Fi guest nối sai, máy của bên thứ ba hoặc port mirror/tap trái phép có thể tạo điểm quan sát. Một VLAN riêng giảm bớt đường tiếp cận nhưng **không bổ sung mã hóa cho bản thân giao thức**.

| Tình huống | Vấn đề | Hướng thay đổi |
|---|---|---|
| Telnet tới switch | Không có confidentiality phù hợp | SSHv2 với xác minh host key và identity mạnh |
| HTTP admin portal | Có thể bị đọc/sửa thông tin phiên trên đường | HTTPS/TLS được xác minh hostname và chain |
| FTP backup cấu hình | Lộ nội dung cấu hình/credential qua truyền tệp | SFTP/SSH hoặc HTTPS có auth |
| TFTP phục hồi firmware qua LAN chung | Không có bảo vệ truyền tải tích hợp | Kênh/mạng phục hồi cô lập, artifact integrity và phương án bảo vệ thích hợp |
| Script quản trị dùng HTTP API | Bearer token và dữ liệu có thể bị lộ | HTTPS, token scope tối thiểu, xác thực endpoint |

Đường truyền plaintext là **vấn đề ngay cả khi password mạnh**. Mật khẩu dài không ngăn việc bị quan sát trực tiếp trên mạng.

### 4.2. Biện pháp bù trừ không nên bị hiểu nhầm

Nếu một appliance cũ chỉ hỗ trợ Telnet hoặc TFTP, đặt thiết bị trong mạng OOB cô lập hoặc tunnel mã hóa **có thể giảm phơi bày của hop mạng**, nhưng không biến giao thức gốc thành SSH/HTTPS. Cần xác định nơi tunnel bắt đầu/kết thúc, ai có quyền vào vùng plaintext và liệu traffic có đi qua đoạn không tin cậy nào không. Một ngoại lệ như vậy cần **owner, thời hạn, risk acceptance, kế hoạch nâng cấp/thay thế**.

Không nên đề nghị “cứ để Telnet nhưng chặn port 23 từ Internet” như giải pháp cuối cùng nếu còn khả năng chuyển sang SSH.

## 5. Sai lầm số 2: Bật SSH nhưng không xác minh máy chủ

SSH thường được coi là đáp án cho Telnet. Tuy nhiên, client phải biết **host key của server nào là đúng**; nếu tin bất kỳ khóa nào vừa thấy mà không kiểm chứng, nguy cơ kết nối nhầm thiết bị hoặc MITM vẫn tồn tại.

Các biểu hiện:

- Script dùng `StrictHostKeyChecking=no` hoặc cấu hình tương đương trên mọi host.
- Người vận hành xóa `known_hosts` khi SSH báo host key changed mà không hỏi nguyên nhân.
- Dùng `ssh-keyscan` để lấy key rồi mặc nhiên coi đó là bằng chứng xác thực.
- Các tài khoản dùng chung private key, một key có mặt trên nhiều thiết bị mà không có khả năng thu hồi theo người.
- SSHv2 vẫn bật song song với Telnet hoặc thuật toán/phiên bản lỗi thời trên appliance.
- Cấp quyền trực tiếp `root` hoặc account admin chung cho mọi kết nối, bỏ qua bastion và audit.

### 5.1. Host key khác user key

| Loại | Xác thực ai? | Cần quản lý gì? |
|---|---|---|
| **SSH host key** | Server/thiết bị đích đối với client | Fingerprint, trust-on-first-use có kiểm soát, rotation, inventory |
| **SSH user key/certificate** | Client/user đối với server | Private key, passphrase/token, role, hạn sử dụng, revoke |
| **Bastion/PAM identity** | Người hoặc workload đi qua điểm quản trị | MFA, JIT, session audit, đường đích được phép |

Việc có user public key đúng **không giải quyết** việc client kết nối tới server giả; và việc host key đúng **không giải quyết** user có quyền quá rộng.

### 5.2. Cách kiểm tra an toàn

~~~bash
# Chỉ với máy quản trị và thiết bị được phép; host key đã
# được đăng ký và đối chiếu độc lập qua kênh tin cậy.
ssh -o StrictHostKeyChecking=yes \
    -J netadmin@bastion.example.test \
    operator@192.0.2.10

# Thu key công khai để đối chiếu, KHÔNG mặc định đã xác thực.
ssh-keyscan -T 5 -p 22 192.0.2.10
~~~

`192.0.2.10` là địa chỉ tài liệu TEST-NET, không phải đích được cấp phép thực tế. Tất cả lệnh mẫu chỉ dùng trong lab hoặc theo change/test scope đã được phê duyệt. Khi fingerprint bất ngờ thay đổi, cần xác minh đổi thiết bị, firmware, host-key rotation, DNS/IP mapping hoặc sự cố MITM; không hạ tiêu chuẩn xác minh để kết nối bằng mọi giá.

**Dấu hiệu khắc phục thành công:** các máy quản trị được phép nhận đúng host key; nguồn không hợp lệ bị chặn; key/identity cá nhân có thể thu hồi; login và thay đổi cấu hình có audit.

## 6. Sai lầm số 3: HTTPS/TLS có mã hóa nhưng bỏ kiểm tra danh tính

Một browser hoặc API client có thể thiết lập phiên TLS với **bất kỳ endpoint nào** nếu người dùng hoặc code tắt certificate validation. Khi đó traffic được mã hóa tới endpoint đang kết nối, nhưng không nhất thiết là endpoint intended.

Các lỗi thường gặp:

- Dùng `curl -k`, `--insecure` hoặc thư viện HTTP với `verify=false` trong automation.
- Chấp nhận certificate tự ký không được phân phối/trust đúng quy trình, hoặc nhấn bỏ qua browser warning.
- Chứng chỉ không khớp **hostname/SAN**, hết hạn, chuỗi CA thiếu, clock lệch hoặc key bị lộ.
- TLS chỉ kết thúc ở reverse proxy/load balancer nhưng hop phía sau tới thiết bị lại plaintext trên đường không đáng tin.
- Dùng TLS quá cũ, cipher không đáp ứng policy, vẫn cho phép HTTP redirect ngược về plaintext khi lẽ ra phải bảo vệ toàn bộ phiên.
- Một chứng chỉ wildcard hoặc CA nội bộ có quyền quá rộng, không bảo vệ private key/không có kiểm soát cấp phát.
- Tưởng **mTLS** thay thế RBAC: có chứng chỉ client không có nghĩa API được phép thực hiện mọi thao tác.

### 6.1. Ba thứ cần phân biệt

1. **Confidentiality/integrity:** TLS thực hiện bảo vệ dữ liệu của phiên với bộ thuật toán được đàm phán.
2. **Server identity:** client xác minh certificate chain, hostname/SAN, thời gian và trust anchor theo chính sách.
3. **Client identity và authorization:** người dùng/automation được xác thực và cấp **quyền cụ thể**, bằng MFA, mTLS, token scope, RBAC/PAM hoặc cơ chế phù hợp.

Nếu chỉ có bước 1, câu “đã dùng HTTPS nên an toàn” không đủ cơ sở.

### 6.2. Ví dụ xác minh có điều kiện

~~~bash
# Kiểm tra hostname và chain; không sử dụng tùy chọn bỏ xác minh.
openssl s_client \
  -connect mgmt.example.test:443 \
  -servername mgmt.example.test \
  -verify_return_error \
  -verify_hostname mgmt.example.test \
  </dev/null

# Gọi HTTPS với certificate verification mặc định.
curl --head --silent --show-error --max-time 5 \
  https://mgmt.example.test/
~~~

Các host `.example.test` chỉ là minh họa. Một lệnh TLS thành công chưa chứng minh RBAC, khả năng chống CSRF hay bảo vệ backend; cần kiểm tra riêng các lớp đó. Nếu certificate không hợp lệ, **điều tra lỗi** (FQDN, CA, SAN, proxy, NTP, rotation), không đưa `--insecure` thành thói quen sản xuất.

## 7. Sai lầm số 4: Có giao thức bảo mật nhưng management plane bị lộ rộng

Đây là kiểu sai lầm nguy hiểm vì các nhóm thường chỉ kiểm tra “SSH chạy” mà không kiểm tra **ai có thể tới được SSH**.

| Dạng phơi bày | Tại sao dễ bỏ sót? | Kiểm soát |
|---|---|---|
| SSH/HTTPS quản trị reachable từ user VLAN | Có route chung, ACL đặt nhầm interface | Management VRF/VLAN, firewall deny by default, allowlist bastion |
| Port quản trị public Internet | NAT/LB/public IP hoặc security group mở rộng | Private management endpoint, VPN/ZTNA, restrict source |
| IPv6 chưa được giới hạn | Chỉ audit IPv4; interface có địa chỉ IPv6 | Rule tương đương cho IPv6; test cả hai family |
| Guest Wi-Fi vào controller/AP | SSID mapping/VLAN leak hoặc ACL thiếu | Client isolation, NAC/segmentation và kiểm tra đường thực |
| Cloud peering/transit đi vào admin subnet | Phạm vi route tăng sau tích hợp mạng | Microsegmentation, SG/NACL, route review, VPC flow logs |
| Vendor remote support không quản lý | Tunnel duy trì thường trực, credential chia sẻ | JIT access, time bound session, vendor identity và audit |
| Kubernetes/dashboard/API | Ingress/load balancer mở ngoài phạm vi | Private endpoint, IAM/RBAC, NetworkPolicy, API audit |
| VPN kết nối là có quyền tới mọi host | Đồng nhất “đã xác thực VPN” với “được phép quản trị” | Per-application authorization, least privilege |

Một kết nối VPN được mã hóa **không bảo đảm** người dùng có đủ quyền truy cập từng thiết bị phía sau. “Tất cả người dùng VPN vào được cổng quản trị” vẫn là quyền quá rộng.

### 7.1. Nên kiểm tra từ nhiều nguồn

~~~mermaid
flowchart LR
    A["Managed admin workstation"] --> Z["ZTNA/VPN + MFA"]
    Z --> J["Bastion/PAM"]
    J --> F["Management firewall rules"]
    F --> R["Router/Firewall/Switch: SSH/HTTPS"]

    U["User VLAN"] -. "Expected DENY" .-> F
    G["Guest Wi-Fi"] -. "Expected DENY" .-> F
    X["Public Internet"] -. "Expected DENY" .-> F
    V["Unauthorized VPN role"] -. "Expected DENY" .-> F
~~~

Kết quả kiểm thử phải gắn **source zone, destination IP/FQDN, cổng, thời gian và quy tắc firewall**. Một lần thử từ bastion thành công không chứng minh user VLAN, guest hoặc IPv6 đã bị chặn.

## 8. Sai lầm số 5: Nhầm giám sát mạng với kênh chỉ đọc, nên không bảo vệ

Nhiều đội bảo mật coi SNMP, syslog hoặc telemetry chỉ “đọc thông tin” và ít ưu tiên hơn CLI. Nhưng dữ liệu thu thập có thể tiết lộ cấu trúc mạng, IP, trạng thái interface, tên host, routing hoặc cấu hình; một số giao thức/role còn hỗ trợ **ghi**.

### 8.1. SNMPv1/v2c và SNMPv3

| Cơ chế | Authentication | Payload privacy | Nhận xét |
|---|---|---|---|
| SNMPv1/v2c community | Community string không phải cơ chế xác thực/mã hóa hiện đại | Không có | Không phù hợp qua mạng không tin cậy |
| SNMPv3 `noAuthNoPriv` | Không có cơ chế xác thực thông điệp mật mã | Không | Chưa đáp ứng bảo vệ |
| SNMPv3 `authNoPriv` | Có authentication/integrity | Không | Payload vẫn có thể bị đọc |
| **SNMPv3 `authPriv`** | **Có** | **Có** | Ưu tiên khi cần giám sát nhạy cảm |

SNMPv3 không tự an toàn chỉ vì có chữ “v3”. Phải xác minh **security level, thuật toán theo baseline, user/view, quyền read-only, engine/config, source ACL và vòng đời bí mật**. Khi chuyển đổi cần kiểm tra polling, traps/informs, collector và tắt community cũ sau khi phụ thuộc đã được xử lý.

### 8.2. Syslog và telemetry

Syslog qua UDP plaintext không cung cấp confidentiality/integrity hoặc bảo đảm giao hàng đầu cuối. **Syslog over TLS**, một đường tunnel được kiểm soát hoặc collector nội bộ trên segment bảo vệ có thể giảm rủi ro, tùy tính năng thiết bị. Nhưng TLS không bảo đảm log không bị mất ở queue/collector và không ngăn admin có quyền quá rộng thay audit policy.

Cần phân biệt:

- **Kênh vận chuyển:** có mã hóa, xác thực collector, hạn chế network sources hay không.
- **Integrity của event:** log bị sửa/xóa/trùng, timestamp sai, buffer tràn hoặc thiếu retention hay không.
- **Authority:** người chỉnh firewall/IDS có được quyền xóa log tương ứng không?
- **Audit completeness:** sự kiện login, config change, role change, token rotation và reboot có được ghi và giám sát không?

## 9. Sai lầm số 6: Danh tính yếu và đặc quyền không được giới hạn

Một phiên SSH/HTTPS qua TLS mạnh vẫn dễ bị lạm dụng nếu credential bị lộ hoặc account quá nhiều quyền.

Những anti-pattern:

- Tài khoản `admin` chung, không thể truy trách nhiệm theo người.
- Mật khẩu mặc định, password reuse hoặc khóa SSH dùng chung trong nhiều site.
- Một token API có thể chỉnh tất cả firewall/route/role và không có expiry.
- MFA chỉ áp dụng ở VPN, nhưng còn đường trực tiếp đến UI/API không cần MFA.
- Người vận hành được cấp quyền vĩnh viễn dù chỉ cần quyền thay rule vài phút.
- Tài khoản bị nghỉ việc/đổi vai trò vẫn còn group, certificate, SSH key, VPN/ZTNA access.
- Break-glass account sử dụng thường xuyên, không có cảnh báo hoặc review.

### 9.1. Authentication và authorization là hai quyết định riêng

- **Authentication:** “Có đúng là người hoặc workload được tuyên bố không?”
- **Authorization:** “Chủ thể này có được thao tác trên tài nguyên này **ngay lúc này** không?”

MFA, khóa SSH hoặc mTLS có thể tăng độ tin cậy của identity; **không tự làm role admin trở nên an toàn**. Cần RBAC/ABAC theo tài sản, loại thay đổi, môi trường, thời gian và mục đích; kết hợp SoD (người yêu cầu không tự phê duyệt thay đổi rủi ro), JIT/PAM và session audit.

### 9.2. Các lớp quyền nên có

| Chủ thể | Quyền phù hợp | Không nên có mặc định |
|---|---|---|
| NOC operator | Xem health, metrics, read-only CLI/telemetry | Tắt firewall/IDS, cấp tài khoản admin |
| Network engineer | Thay config đúng thiết bị/tenant theo workflow | Thay config mọi site, sửa audit logs |
| Security reviewer | Đánh giá, phê duyệt policy/ngoại lệ | Tự thực thi mọi thay đổi đã duyệt |
| Automation identity | Áp artifact đã được duyệt vào nhóm đích giới hạn | Toàn quyền API, secret không hết hạn |
| Vendor support | Truy cập có hạn, theo session và tài sản | VPN truy cập toàn LAN, shared admin |
| Break-glass | Khôi phục theo sự kiện khẩn cấp có giám sát | Dùng hằng ngày thay PAM và approval |

Quyền và trách nhiệm cụ thể cần dựa trên tổ chức; bảng là mô hình tham khảo. Một account có cả quyền thay cấu hình và xóa chứng cứ cần được xem là tổ hợp quyền rủi ro cao.

## 10. Sai lầm số 7: Lộ private key, API token và backup cấu hình

Kênh quản trị còn bao gồm **credential lifecycle** và đường đưa lệnh vào thiết bị. Các lỗi thường xuất hiện trong automation, chứ không nằm ở cấu hình SSH/HTTPS:

- Hard-code password, bearer token, SNMP secret hoặc SSH private key trong script/repository.
- In token/Authorization header vào CI logs, issue tracker, terminal history hoặc chat.
- Private key copy lên jump host không cần thiết, rồi được backup/đọc bởi nhiều bên.
- Backup cấu hình chứa community string, PSK, shared secret được lưu plaintext trên share.
- Dùng một credential dài hạn cho tất cả device/API/cloud account.
- Không rotate/revoke sau incident hoặc offboarding; “đổi mật khẩu” nhưng session/token cũ vẫn có hiệu lực.
- Cấp quyền service account lớn hơn yêu cầu, không giới hạn IP/tenant/operation.
- Đưa vault và policy publish API lên cùng máy không được harden.

### 10.1. Vòng đời secret an toàn

1. **Create:** tạo bằng nguồn ngẫu nhiên và thuật toán phù hợp; xác định owner/tài sản/mục đích.
2. **Store:** vault/HSM/token hardware-backed khi phù hợp, giới hạn đọc, MFA và audit.
3. **Distribute:** qua cơ chế cấp phát có kiểm soát, không đính kèm plaintext trong ticket.
4. **Use:** giới hạn scope/time; không để secret lọt vào log hoặc diagnostic output.
5. **Rotate:** có kế hoạch không làm gián đoạn service; cập nhật mọi client/collector.
6. **Revoke:** thu hồi khi nghi lộ, thay role, hết hạn; vô hiệu hóa session/token còn tồn tại theo chính sách.
7. **Verify:** kiểm tra credential cũ thật sự bị từ chối và credential mới chỉ có đúng quyền cần thiết.

**Bảo vệ đường truyền không thể bù trừ cho secrets đã bị lộ ở điểm cuối.**

## 11. Sai lầm số 8: Mạng OOB/console bị xem là “đã an toàn”

Out-of-band (OOB) cho phép tiếp cận console/management ngay cả khi data plane sản xuất gặp sự cố. Đây là thành phần quan trọng của recovery, nhưng cũng là đường điều khiển đặc quyền.

Các sai lầm:

- Console server dùng HTTP/Telnet qua mạng quản trị chung.
- OOB modem/remote access để tài khoản mặc định hoặc truy cập public.
- Thiết bị console không có audit ai đã kết nối tới cổng của router/firewall nào.
- OOB dùng chung credential với mạng sản xuất, không có khả năng revoke tách biệt.
- Đường console từ xa đi qua hop plaintext hoặc tunnel không được kiểm soát.
- OOB chỉ có một đường phụ thuộc chính firewall đang sửa, không thể dùng khi firewall lỗi.
- “Break-glass” không có vault, MFA, người chịu trách nhiệm hoặc lịch diễn tập.

**OOB là một miền tin cậy cần hardening riêng**, không phải ngoại lệ mặc định cho mọi kiểm soát. Console vật lý có thể không cung cấp mã hóa trong bản thân serial link; khi mở rộng qua console server cần bảo vệ hop từ máy admin tới server bằng SSH/TLS/VPN, giới hạn truy cập vật lý, session logging và người có thể sử dụng.

### 11.1. Kiểm thử OOB phải chứng minh cả availability lẫn authorization

Trong lab/maintenance window được duyệt, mô phỏng mất đường quản trị chính; xác minh:

- Chỉ người có quyền mới đăng nhập OOB.
- Không có mật khẩu mặc định/shared account ngoài chính sách.
- Có thể định danh cổng console/asset và lưu bản ghi session.
- Có thể rollback config một cách có kiểm soát.
- Khi hoàn tất, quyền emergency được thu hồi và event được review.

Không thực hiện thao tác cắt WAN/firewall production chỉ để thử OOB nếu chưa có authorization và kế hoạch phục hồi.

## 12. Sai lầm số 9: API và bộ điều khiển cloud được coi là kênh “không thuộc mạng”

Trong mạng hiện đại, một thao tác trên cloud console, Kubernetes API, SDN controller hoặc GitOps pipeline có thể tạo firewall rule, sửa routing, mở service endpoint hoặc cập nhật security group. **Quản trị bằng API cũng là quản trị mạng.**

Những điểm dễ bỏ sót:

| Bối cảnh | Anti-pattern | Hướng kiểm soát |
|---|---|---|
| Cloud console | Owner/admin lâu dài trên nhiều account; thiếu MFA | IAM theo vai trò, JIT, MFA, audit API |
| Service account | Access key không hết hạn, lưu trong CI plaintext | Workload identity/federation, short-lived token, secret manager |
| Cloud API | Public endpoint/token rộng quyền; không giới hạn source/trust | API authn/authz, private connectivity khi phù hợp, monitoring |
| Kubernetes | Dashboard/API lộ; RBAC quá rộng; service account token bị mount không cần | Private access, RBAC, admission/policy, audit |
| GitOps/IaC | Người tự merge PR và triển khai, sửa pipeline để bypass | Protected branches, code owner review, artifact approval binding |
| SDN controller | Controller API không có TLS/mTLS hoặc quyền thay toàn mạng | Controller hardening, least privilege, signed/validated release |
| Vendor portal | Remote access thường trực, account dùng chung | Vendor identity, allowlist/JIT, session recording |
| IaC state/backup | State lưu secret và policy nhạy cảm trong storage rộng quyền | Encryption, access control, secure backend và retention |

Đặc biệt, **TLS certificate hợp lệ của cloud provider không thay thế kiểm soát IAM**. Một access key bị lộ có thể tạo request HTTPS hoàn toàn hợp lệ và được server thực thi nếu scope cho phép.

### 12.1. Con đường control plane không giống đường traffic data plane

Một security group chỉ cho phép ứng dụng kết nối qua cổng 443 có thể vẫn bị thay đổi bằng cloud API bởi user IAM có quyền rộng. Quét port ứng dụng sẽ không phát hiện user IAM đang sở hữu `ec2:AuthorizeSecurityGroupIngress` hoặc quyền tương đương ở nền tảng khác. Kiểm kê management plane cần bao gồm **API permissions, identity federation, IaC runners và audit settings**, không chỉ các cổng TCP trên thiết bị.

## 13. Sai lầm số 10: Chỉ harden một giao diện, bỏ đường còn lại

Các thiết bị có thể sở hữu nhiều kênh:

- Cổng management chuyên dụng.
- SSH/HTTPS trên IP của data interface nếu được bật.
- IPv4 và IPv6.
- Console/OOB, VPN/vendor tunnel.
- SNMP, NETCONF over SSH, RESTCONF over HTTPS, gNMI qua TLS.
- Web UI, CLI, API machine-to-machine.
- Wireless controller/SSID quản trị.
- Cloud agent hoặc controller có kênh callback.
- Bootstrapping, firmware recovery và backup channel.

Đóng cổng Telnet trên một interface không có nghĩa Telnet đã tắt trên tất cả interface/VRF. Dùng rule IPv4 không tự ngăn truy cập IPv6. Một port 443 có thể dẫn tới load balancer/proxy hoặc vhost khác nhau theo SNI/Host header.

### 13.1. Tạo bản đồ kênh quản trị

~~~mermaid
flowchart TD
    S["Asset inventory / CMDB"] --> I["All interfaces and management endpoints"]
    I --> T["TCP/UDP/IPv4/IPv6 + FQDN/API"]
    T --> N["Source zones: admin, user, VPN, guest, cloud, OOB"]
    N --> C["Authentication, peer verification, RBAC, secrets"]
    C --> L["Audit, logs, emergency recovery"]
    L --> R["Risk findings and remediation owner"]
~~~

Mỗi entry cần chỉ rõ **asset/owner, service, source allowed, protocol, trust, credential class, privilege, logging, exception và test evidence**. Bản đồ này là cơ sở chống việc một đường phụ bị bỏ quên.

## 14. Bảng chẩn đoán nhanh: giả định sai và kết luận đúng

| Giả định sai | Vì sao sai | Câu hỏi cần kiểm tra |
|---|---|---|
| “Mạng private là đủ.” | Host nội bộ hoặc đường peering/VPN vẫn có rủi ro | Nguồn nào tới được port admin? |
| “Có HTTPS thì không cần MFA.” | TLS không xác thực/constrain người dùng theo role | Identity/RBAC/MFA/JIT ở đâu? |
| “SSH hiện cảnh báo key đổi cứ xóa known_hosts.” | Cảnh báo có thể liên quan MITM | Fingerprint mới được xác minh thế nào? |
| “MFA ở VPN bảo vệ mọi CLI.” | Có thể còn đường trực tiếp hoặc account local | Có bypass qua interface/API khác không? |
| “SNMP chỉ đọc nên không nhạy cảm.” | Topology/metadata có giá trị; role ghi có thể tồn tại | SNMPv3 authPriv, view và ACL đã đúng chưa? |
| “Máy quản trị sạch thì credential an toàn.” | Secret có thể rò qua CI/vault/log/backup | Vòng đời và quyền đọc secret ra sao? |
| “Quản trị qua OOB không cần audit.” | OOB vẫn có đặc quyền cao | Ai vào console, lúc nào và đã làm gì? |
| “Bật TLS trên load balancer đã mã hóa tới backend.” | TLS có thể kết thúc tại LB | Hop backend có bảo vệ đúng mức không? |
| “Đã block port 22 từ Internet, xong.” | Có thể lộ qua IPv6, VPN, API, vendor tunnel | Đã kiểm tra toàn bộ nguồn và surface chưa? |
| “Có log ở thiết bị là đủ.” | Admin có thể xóa/sửa log tại chỗ | Có collector tách quyền, retention và alert không? |
| “Đổi config không cần rollback vì chỉ là một ACL.” | Một ACL sai có thể khóa đường quản trị | Có console/OOB và phiên dự phòng chưa? |
| “Chứng chỉ self-signed phải bỏ verify để chạy.” | Tắt verify bỏ kiểm tra danh tính | Có CA/trust store/host verification đúng chưa? |
| “Cloud service không phải network equipment.” | Cloud API có thể thay route/firewall | Đã kiểm tra IAM, CI/CD và API audit chưa? |
| “Giao thức yếu có thể duy trì vô thời hạn vì thiết bị cũ.” | Risk tăng và ngoại lệ thành thường trực | Có owner, giảm phơi bày, ngày nâng cấp/thay thế? |

## 15. Phân loại rủi ro và ưu tiên khắc phục

Không nên chỉ dựa vào giao thức mà xếp mức độ. Một cổng Telnet lộ từ Internet trên firewall manager có mức ảnh hưởng khác Telnet trong lab cô lập sắp được ngừng sử dụng. Cần xem xét:

1. **Reachability:** Internet, mạng người dùng, VPN rộng quyền, management zone hoặc OOB cô lập.
2. **Privilege:** read-only, operator, full admin; số tài sản/control domains chịu ảnh hưởng.
3. **Secrets và dữ liệu:** password, SNMP credential, cấu hình/VPN keys, log nhạy cảm.
4. **Identity:** named account, MFA, device posture, token expiry, vendor support.
5. **Peer verification:** SSH host key/TLS certificate có bị bỏ qua không?
6. **Detectability:** audit tách quyền, session recording, SOC alerts, khả năng truy xuất.
7. **Recovery:** có OOB, backup, rollback đã kiểm thử không?
8. **Compensating controls:** ACL, tunnel, microsegmentation, monitoring, thời hạn ngoại lệ.
9. **Business impact:** tính trọng yếu của router/firewall/core DNS/VPN và môi trường OT.
10. **Exposure duration:** bao lâu chưa vá; hệ thống có tự động tạo lại cấu hình không?

### 15.1. Ma trận minh họa

| Finding | Bối cảnh | Mức ưu tiên tham khảo |
|---|---|---|
| Web admin plaintext public Internet | Quyền cấu hình firewall, không MFA, không audit | Rất cao, cần giảm phơi bày khẩn cấp có kiểm soát |
| SSH host key verification bị tắt trong pipeline | Runner triển khai hàng chục site, token rộng quyền | Cao vì nguy cơ giả mạo endpoint và blast radius |
| SNMPv2c trong VLAN giám sát chưa cô lập | Có asset quan trọng, secrets chia sẻ | Cao hoặc trung bình tùy reachability và quyền |
| TLS cert hết hạn trên portal OOB | Admin đang bỏ verify để vận hành | Cao do khôi phục dựa vào đường không xác thực |
| SSH từ bastion theo role, host key đã xác minh | ACL, MFA/PAM, audit, owner rõ | Có thể chấp nhận, tiếp tục giám sát/bảo trì |
| Telnet trên thiết bị lab không nối production | Owner, cách ly, thời hạn tháo dỡ | Cần xử lý theo lịch và xác minh cách ly |

Bảng không thay thế risk assessment thực tế và không phải chuẩn điểm số chính thức. Khắc phục phải **giảm rủi ro ngay** nhưng không gây outage do tắt đường quản trị duy nhất.

## 16. Phát hiện sai lầm: kiểm kê và xác minh đúng nguồn

Một lần quét port đơn lẻ không đủ. Dùng nhiều nguồn bằng chứng:

- **CMDB/IPAM/device inventory:** thiết bị, owner, firmware, interface, IPv4/IPv6, OOB, management service.
- **Firewall/VPC flow logs:** nguồn nào truy cập management port, số phiên, deny/allow và lưu lượng bất thường.
- **AAA/IdP/PAM logs:** login success/failure, MFA decision, role, break-glass, session.
- **Device config và API inventory:** giao thức bật, management ACL, vty/SSH policy, role, certificate, SNMP.
- **TLS/SSH metadata:** certificate SAN/expiry/issuer, host-key fingerprint, phiên bản và thuật toán.
- **Secret inventory:** khóa, token, public key, tuổi credential, scope, nơi lưu.
- **SIEM/IDS/IPS:** hành động cấu hình, truy cập khác thường, telemetry gaps.
- **Change management:** policy change/approval, diff, ai thực hiện, expiration và rollback.

### 16.1. Ma trận nguồn–đích cần kiểm tra

Ví dụ giả định về một switch quản trị ở `192.0.2.10`:

| Nguồn kiểm thử | SSH/22 | HTTPS/443 | Telnet/23 | Kỳ vọng |
|---|---|---|---|---|
| Bastion qua management VLAN | Allow | Theo nhu cầu | Deny | Danh tính và host key/cert hợp lệ |
| User VLAN | Deny | Deny | Deny | Không truy cập trực tiếp |
| Guest Wi-Fi | Deny | Deny | Deny | Cô lập với management plane |
| VPN thường | Deny | Deny | Deny | VPN không mặc định có quyền admin |
| VPN admin group qua bastion | Allow theo policy | Theo policy | Deny | MFA, JIT, audit |
| Internet | Deny | Deny | Deny | Không public cổng quản trị |

Cần thử từ các nguồn **được phép kiểm thử** và xác nhận bằng firewall hit logs, route, policy effective; một kết nối timeout có thể do host down chứ không chứng minh ACL đúng.

### 16.2. Một số lệnh xác minh không xâm lấn

~~~bash
# Ví dụ lab/đích được phê duyệt. Các câu lệnh kiểm tra khả năng
# kết nối/certificate, không thực hiện thử mật khẩu hay khai thác.
nc -vz -w 3 192.0.2.10 22
nc -vz -w 3 192.0.2.10 23

# TLS được xác thực theo FQDN thay vì tắt verify.
openssl s_client \
  -connect mgmt.example.test:443 \
  -servername mgmt.example.test \
  -verify_return_error \
  -verify_hostname mgmt.example.test \
  </dev/null

# Kênh SSH chỉ kết nối khi host key đã được kiểm chứng.
ssh -o StrictHostKeyChecking=yes operator@192.0.2.10
~~~

Các lệnh này **không thay thế** kiểm tra thiết lập MFA, RBAC, API authorization, session logs hoặc config effective. Cổng SSH mở không đồng nghĩa rủi ro; cổng Telnet đóng từ một subnet không chứng minh đã tắt trên mọi interface.

Trong môi trường production/OT cần scope, rate limit, owner và stop conditions; nếu không được phép active probing, ưu tiên config snapshot/telemetry sẵn có.

## 17. Thiết lập baseline bảo vệ kênh quản trị

Một baseline nên thể hiện nhiều chiều, không chỉ liệt kê “dùng SSH và HTTPS”.

### 17.1. Các lớp bắt buộc hoặc cần đánh giá

| Lớp | Mục tiêu tối thiểu |
|---|---|
| **Asset/Surface** | Biết mọi interface/IPv4/IPv6/FQDN/API, cả OOB và cloud |
| **Network Path** | Mạng quản trị giới hạn, ACL allow theo source, bastion/VPN/ZTNA, không public |
| **Transport** | SSHv2, HTTPS/TLS được xác minh, SNMPv3 authPriv, kênh log bảo vệ |
| **Endpoint Trust** | SSH host key và TLS chain/SAN/hostname; không bỏ qua warning |
| **Identity** | Named accounts, MFA ở boundary phù hợp, device posture khi cần |
| **Authorization** | Least privilege, RBAC/PAM/JIT, SoD và emergency access có kiểm soát |
| **Secrets** | Vault, rotate/revoke, short-lived token/cert khi khả thi, không hard-code |
| **Audit** | Login, privilege escalation, config diff, API events; log tới kho tách quyền |
| **Lifecycle** | Patch firmware, cert expiry, SSH host-key rotation, decommission legacy |
| **Recovery** | OOB, backup config mã hóa, rollback và diễn tập khôi phục |
| **Verification** | Thử allow/deny từ đúng vùng, kiểm tra IPv4/IPv6, applied config và drift |

Các yêu cầu phải được ánh xạ theo khả năng của từng hãng. Ví dụ một router không hỗ trợ SNMPv3 authPriv hoặc syslog over TLS cần risk acceptance/compensating controls, không cố dùng cú pháp không tương thích.

### 17.2. Mẫu chính sách minh họa

~~~yaml
management_security_baseline:
  version: "example-2026-01"
  scope:
    asset_groups: ["routers", "switches", "firewalls", "controllers"]
    include: ["ipv4", "ipv6", "oob", "cloud-management-api"]
  network:
    approved_sources: ["admin-workstations-via-bastion", "approved-automation"]
    default_management_access: "deny"
    public_management_exposure: "prohibited"
  transport:
    cli: "SSHv2_with_verified_host_key"
    web_api: "HTTPS_with_verified_TLS"
    monitoring: "SNMPv3_authPriv_when_supported"
    legacy_plaintext: "disabled_or_exception_with_expiry"
  identity:
    named_accounts: true
    mfa_at_privileged_boundary: true
    least_privilege: true
    pam_jit_where_supported: true
  secrets:
    location: "approved-vault"
    rotation_and_revocation: "documented"
    plaintext_in_ci_logs: "prohibited"
  audit:
    privileged_login_and_config_changes: true
    off_device_collector: true
    separate_log_admin_rights: true
  recovery:
    protected_oob_or_console: true
    tested_rollback: true
  assurance:
    source_zone_verification: true
    certificate_and_key_expiry_alerts: true
    config_drift_monitoring: true
~~~

Đây là **mẫu mục tiêu**, không phải file cấu hình dùng trực tiếp cho thiết bị. Chính sách thật phải chỉ định owner, phạm vi, ngoại lệ, định nghĩa time window, yêu cầu kiểm chứng và bản hướng dẫn của vendor.

## 18. Khắc phục theo thứ tự an toàn: đừng tự khóa quản trị

Lỗi thứ hai thường xảy ra khi sửa lỗi thứ nhất: đội vận hành quyết định tắt Telnet và HTTP ngay lập tức, nhưng chưa kiểm tra SSH key, HTTPS cert, AAA hoặc management ACL. Hậu quả là không còn đường vào thiết bị, đặc biệt khi network đang gặp sự cố.

### 18.1. Quy trình chuyển đổi

~~~mermaid
flowchart TD
    A["Inventory management channels and dependencies"] --> B["Risk assessment + approved change"]
    B --> C["Backup config + protected console/OOB + rollback plan"]
    C --> D["Enable verified SSH/HTTPS/SNMPv3 in parallel"]
    D --> E["Test admin identity, AAA, monitoring, logs"]
    E --> F{"New channels fully usable?"}
    F -->|"No"| G["Fix/rollback with old channel temporarily constrained"]
    G --> D
    F -->|"Yes"| H["Apply management ACL and limit source zones"]
    H --> I["Disable Telnet/HTTP/SNMPv1-v2c + revoke old secrets"]
    I --> J["Validate from allowed and denied sources; IPv4/IPv6"]
    J --> K["Record evidence, owner sign-off, drift/expiry monitoring"]
~~~

### 18.2. Thứ tự thực hiện chi tiết

1. **Tạo danh mục:** mọi endpoint quản trị, giao thức, admin/service account, SNMP collectors, NMS, backup, OOB, cloud/CI runners và phụ thuộc. Ghi firmware/vendor limitations.
2. **Đánh giá đường đi:** ai có thể truy cập từ đâu; xác định nơi bắt đầu/kết thúc TLS/tunnel, LB/proxy, NAT/IPv6 và dữ liệu nào đi qua.
3. **Bảo toàn khả năng khôi phục:** backup cấu hình trong kho an toàn, đường console/OOB, người trực, change ticket, maintenance window và cách rollback.
4. **Chuẩn bị trust:** SSH host key fingerprint đã xác minh, FQDN/CA/SAN cho TLS, đồng bộ thời gian, identity/AAA, quyền và credential vòng đời.
5. **Bật đường an toàn song song:** thử từ máy quản trị được quản lý qua bastion; test user/automation và các công cụ monitoring theo profile.
6. **Kiểm tra authentication + authorization:** không chỉ đăng nhập thành công; read-only user không được sửa config, MFA/PAM có hiệu lực, session được ghi.
7. **Kiểm tra access policy:** allow nguồn quản trị đúng, deny user VLAN/guest/Internet/VPN không đủ quyền; kiểm tra IPv4/IPv6 và cloud routes.
8. **Chuyển automation/telemetry:** SFTP/HTTPS, NETCONF over SSH, RESTCONF over HTTPS, SNMPv3, syslog over TLS khi có hỗ trợ.
9. **Tắt cơ chế yếu:** Telnet/HTTP plaintext/SNMPv1/v2c, tài khoản default, community strings, API tokens cũ; kiểm tra không còn route phụ.
10. **Xác minh sau thay đổi:** config effective, allow/deny tests, logs, availability, latency và khả năng rollback/OOB; ghi kết quả, hạn review.

**Không kéo dài bước chạy song song vô thời hạn.** Đặt deadline cụ thể để loại bỏ cơ chế cũ sau khi đường mới được kiểm thử.

### 18.3. Quy tắc khi thay SSH/AAA/ACL

- Dùng **phiên quản trị thứ hai** để kiểm thử; giữ phiên hiện tại và đường OOB khi thay cấu hình có thể lockout.
- Trên thiết bị hỗ trợ **commit confirmed/auto rollback**, xem xét sử dụng theo tài liệu vendor và thẩm quyền đã duyệt.
- Kiểm tra syntax/effective config trước reload; tính năng và lệnh tùy platform.
- Không tự disable password authentication nếu public key/MFA/PAM chưa được xác nhận hoạt động.
- Không cho phép “đã có HTTPS” là tiêu chí hoàn tất nếu certificate/hostname chưa hợp lệ hoặc admin UI vẫn public.
- Tránh thay đổi đồng loạt toàn bộ site; rollout canary/waves và đo lỗi.

## 19. Kiểm thử trong lab: nhận diện và xử lý một kênh quản trị yếu

### 19.1. Bối cảnh

Giả sử lab có switch tại `192.0.2.10`, hai vùng `admin-zone` và `user-zone`. Ban đầu SSH/22 có sẵn, Telnet/23 vẫn bật, HTTPS/443 dùng chứng chỉ không khớp hostname. Firewall policy cho phép người dùng ở `user-zone` tới cả ba port.

**Mục tiêu:** xác minh và sửa kênh quản trị mà không làm mất đường truy cập hợp lệ. Lab do tổ chức kiểm soát và việc kiểm thử đã được phê duyệt.

### 19.2. Bước quan sát

| Kiểm tra | Bằng chứng giả định | Diễn giải |
|---|---|---|
| Từ admin-zone, SSH/22 | Open, fingerprint khớp inventory | Đường SSH có thể dùng; cần kiểm tra user/RBAC/log |
| Từ user-zone, SSH/22 | Open | Vi phạm segmentation của management plane |
| Từ user-zone, Telnet/23 | Open | Vừa plaintext vừa phơi bày sai vùng |
| HTTPS theo FQDN | TLS warning do SAN sai | Không có server identity verification hợp lệ |
| Admin login | Account dùng chung, không MFA qua bastion | Không thể quy trách nhiệm theo người |
| Audit | Chỉ log local, cùng quyền admin có thể xóa | Khả năng điều tra yếu |

Đây là kết quả **minh họa**, không phải output kiểm thử thực tế.

### 19.3. Phân tích nguyên nhân gốc

- Telnet vẫn được giữ “phòng khi SSH lỗi” vì chưa có quy trình OOB/rollback.
- ACL quản trị chỉ được áp cho một vùng, không cập nhật sau thay đổi VLAN.
- Chứng chỉ HTTPS được sinh tự ký với IP nhưng admin truy cập bằng FQDN; đội vận hành đã quen bỏ qua cảnh báo.
- Account chia sẻ là di sản của quy trình trực ca; chưa triển khai AAA/PAM.
- Đầu ra syslog chỉ đến local storage, không được bảo vệ khỏi cùng admin role.
- Không có owner chịu trách nhiệm kiểm tra ngoại lệ và tắt kênh legacy.

### 19.4. Hành động khắc phục

1. Xác định asset owner và change ID; chuẩn bị OOB, config backup, rollback.
2. Xác minh SSH host key qua nguồn tin cậy, cấp named identity, MFA ở boundary phù hợp và giới hạn quyền.
3. Sửa TLS cert/SAN/CA trust cho FQDN; kiểm tra backend hop nếu đi qua proxy.
4. Áp ACL cho management interface/VLAN/IPv4/IPv6: chỉ bastion/admin-zone được truy cập port cần thiết.
5. Chuyển script và monitoring khỏi Telnet/HTTP plaintext; kiểm tra đường mới rồi tắt Telnet.
6. Chuyển log tới collector với quyền tách biệt, kiểm tra alert login/config change.
7. Re-test từ admin-zone và user-zone, kiểm tra cả port phải mở và port phải bị chặn.
8. Ghi applied config/version, TTL ngoại lệ, owner sign-off và theo dõi config drift.

### 19.5. Tiêu chí hoàn thành

- Bastion theo role truy cập đúng SSH/HTTPS và xác minh host key/certificate.
- User-zone/guest/Internet không tới management service.
- Telnet/HTTP plaintext đã tắt hoặc có ngoại lệ tạm thời được duyệt rõ.
- Tài khoản admin cá nhân/automation có quyền cần thiết, thu hồi được và có audit.
- Log thay đổi config tới collector bảo vệ; khôi phục OOB được thử theo kế hoạch.
- Monitoring vẫn hoạt động, không có service regression sau chuyển đổi.

**Bài học:** Sai lầm không chỉ là có port 23 mở; vấn đề là **nhiều lớp kiểm soát management plane bị thiếu cùng lúc**. Sửa riêng giao thức mà không sửa phơi bày, identity và audit vẫn để lại rủi ro lớn.

## 20. Case study thứ hai: cloud firewall an toàn trên mạng nhưng API quá rộng quyền

### 20.1. Bối cảnh giả định

Một nhóm cloud có các security group riêng, backend API chỉ private và HTTPS đúng chuẩn. Kiểm tra port từ Internet không thấy đường quản trị mở. Tuy vậy, CI/CD sử dụng static access key có quyền thay network security groups ở nhiều tài khoản, và key được lưu trong một biến build mà nhiều người có thể đọc.

### 20.2. Vì sao đây vẫn là lỗi kênh quản trị?

- Kênh quản trị không chỉ là SSH/HTTPS của thiết bị; **cloud management API là đường điều khiển cấu hình mạng**.
- Một token bị lộ vẫn có thể dùng để gửi request HTTPS hợp lệ; TLS không phát hiện người dùng token có phải là người được cấp quyền ban đầu hay không.
- Quyền quá rộng khiến một pipeline bị compromise có thể mở firewall ở nhiều tài sản.
- Nếu log cloud API và log CI chỉ có cùng một nhóm quản trị được chỉnh sửa, khả năng truy vết yếu.

### 20.3. Biện pháp giảm rủi ro

- Chuyển sang workload identity hoặc credential ngắn hạn theo khả năng cloud/CI; không hard-code static key.
- Giảm scope của role theo account/region/resource và loại API operation; dùng JIT/approval cho network changes.
- Protected branch, code review độc lập, bind exact change artifact, policy-as-code và rollback.
- Audit API action tới collector độc lập, alert cho thay security group/network ACL, kiểm tra drift giữa IaC và actual state.
- Rotate/revoke key cũ, xác minh session/token liên quan, rà soát history để phát hiện thay đổi không có ticket.

**Điểm rút ra:** Khóa cổng SSH ở mạng sản xuất là cần thiết, nhưng **không đủ** nếu con đường API và quyền automation cho phép thay cấu hình từ bên ngoài.

## 21. Incident response khi nghi kênh quản trị bị lạm dụng

Dấu hiệu có thể gồm:

- Đăng nhập admin từ nguồn không có trong allowlist, thời điểm bất thường, địa điểm/thiết bị chưa biết.
- SSH host key thay đổi không có change ticket, TLS cert bị thay hoặc trust store bị chỉnh.
- Có tài khoản/quyền mới, API token mới, session từ vendor portal ngoài lịch.
- Rule firewall/ACL/NAT/VPN/DNS/IPS bị chỉnh mà không có approval hoặc config diff rõ.
- Syslog/telemetry đột ngột ngừng, collector bị thay, log retention hoặc audit setting bị giảm.
- Có chuyển cấu hình/backup ra ngoài hoặc truy cập vault/token khác thường.
- Config drift xuất hiện đồng thời ở nhiều site do controller/CI runner có quyền tập trung.

### 21.1. Các bước xử lý có kiểm soát

1. **Triage và xác nhận:** phân biệt bảo trì hợp lệ với bất thường dựa trên ticket, actor, device posture, time, network path và logs.
2. **Bảo toàn chứng cứ:** thu bản gốc log/AAA/API/config snapshot theo quy trình, ghi UTC/nguồn/hash và quyền truy cập; không chỉnh sửa chứng cứ để che thông tin.
3. **Giảm quyền bị lạm dụng:** nếu nghi lộ credential, revoke/rotate theo thứ tự có kế hoạch để không làm mất khả năng vận hành; áp hạn chế nguồn truy cập qua quản trị đáng tin.
4. **Giữ recovery path:** xác minh console/OOB, backup configuration và điều kiện khôi phục; không tự khóa toàn bộ đội vận hành.
5. **Xác minh tác động:** review ACL, routing, DNS, IDS/IPS, VPN, account, secrets, cloud policy và những tài sản khác cùng thuộc controller.
6. **Khôi phục:** đưa policy về bản đã duyệt, loại bỏ quyền/tunnel không hợp lệ, nâng cấp, thay khóa/chứng chỉ nếu cần.
7. **Theo dõi tái diễn:** giám sát login, token use, config change, drift, flow access và SIEM; hoàn tất post-incident review.

**Không suy diễn** rằng một lần host key thay đổi chắc chắn là MITM: có thể do rotation hoặc đổi thiết bị. Nhưng cũng không bỏ qua cảnh báo; phải xác minh nguồn tin cậy trước khi chấp nhận kết nối.

### 21.2. Vai trò forensic

Traffic SSH/TLS đã mã hóa thường không cho thấy nội dung lệnh trực tiếp từ PCAP bên ngoài endpoint. Bằng chứng quan trọng thường đến từ:

- Bastion/PAM session recording và authentication logs.
- AAA, API gateway, cloud audit và change management.
- Device configuration history/commit logs và SIEM.
- Endpoint telemetry của máy quản trị hoặc CI runner.
- Certificate/host-key inventory và secret access audit.
- Firewall/VPC flow logs để xác định network path và thời gian.

Điều tra cần kiểm tra độ lệch đồng hồ và chất lượng log; việc không có alert chưa chứng minh hành động không xảy ra.

## 22. Xử lý thiết bị cũ, OT và các ngoại lệ khó thay thế

Một số router, switch cũ hoặc hệ thống OT có thể không hỗ trợ SSH/TLS hiện đại. Không nên lựa chọn giữa **mở rộng phơi bày nguy hiểm** và **tắt thiết bị đột ngột** mà thiếu đánh giá.

### 22.1. Kiểm soát bù trừ tham khảo

| Rủi ro không thể xử lý trực tiếp | Kiểm soát giảm thiểu có thể xem xét | Rủi ro còn tồn tại |
|---|---|---|
| Chỉ hỗ trợ Telnet | Mạng OOB cô lập, jump/gateway bảo vệ phía ngoài, source allowlist | Hop plaintext vẫn tồn tại ở phía sau gateway |
| Không có SNMPv3 | Vùng giám sát tách biệt, read-only community, kiểm soát đường đi và thu hẹp quyền | Community không có bảo vệ mật mã tương đương |
| HTTPS/TLS không cập nhật được | Giới hạn truy cập, reverse proxy bảo vệ hop khi phù hợp, giảm quyền | Backend TLS/plaintext vẫn phải đánh giá rõ |
| Không hỗ trợ MFA trên appliance | MFA tại bastion/PAM, cấm đường trực tiếp, account giới hạn | Nếu đường bypass tồn tại, MFA ở bastion không có tác dụng |
| Không có audit lệnh | Console/PAM session recording, syslog ở mức hỗ trợ và config diff | Visibility có thể không đầy đủ |
| Không có rollback tự động | Console/OOB, backup, maintenance window và runbook thử trong lab | Thời gian khôi phục có thể cao |

**Mỗi ngoại lệ phải có:**

- Asset ID, owner, loại dữ liệu, business justification và mức ảnh hưởng.
- Giải thích vì sao không thể nâng cấp ngay, nguy cơ còn lại và người chấp nhận rủi ro.
- Kiểm soát bù trừ, phương pháp kiểm chứng và bằng chứng.
- Deadline nâng cấp/thay thế hoặc review định kỳ, không để tồn tại vô thời hạn.
- Stop conditions, recovery plan, liên lạc khẩn cấp và cách phát hiện lạm dụng.

Đặc biệt trong OT/ICS, active scanning hoặc đổi protocol có thể gây tác động không mong muốn. Ưu tiên đánh giá từ configuration và telemetry thụ động, lab/vendor guidance, kế hoạch bảo trì và quyền của người sở hữu hệ thống.

## 23. Đo lường hiệu quả: từ “đã bật SSH” đến chứng cứ kiểm soát

Một chương trình hardening cần metric có thể kiểm chứng, phân loại theo nhóm tài sản và môi trường.

| Metric | Cách hiểu | Những điều không nên suy luận |
|---|---|---|
| % tài sản có inventory đầy đủ management paths | Mức bao phủ | Inventory đủ không đảm bảo đường đã an toàn |
| % endpoint không reachable từ nguồn ngoài policy | Hiệu quả segmentation theo source | Một nguồn bị chặn không chứng minh mọi nguồn khác bị chặn |
| % endpoint dùng SSH/HTTPS/SNMPv3 đúng baseline | Giao thức phù hợp | Protocol name không chứng minh cert/host key hoặc RBAC |
| % TLS cert và SSH host key được theo dõi/kiểm chứng | Khả năng xác thực endpoint và rotation | Cert hợp lệ không thay MFA/authorization |
| % admin sessions qua PAM/MFA | Coverage của privileged access boundary | Có thể còn đường bypass direct |
| Thời gian revoke credential | Mức phản ứng khi lộ/đổi nhân sự | Revoke trong IAM chưa chắc cắt mọi session cũ |
| % change có audit và owner/approval | Traceability | Log tồn tại không chứng minh không bị sửa |
| Số cấu hình lệch baseline/ngoại lệ quá hạn | Drift và technical debt | Drift giảm có thể do mất dữ liệu kiểm kê |
| Mức sẵn sàng OOB và rollback được thử | Recovery readiness | Một lab test không khẳng định toàn bộ site |
| Mất telemetry hoặc chênh lệch clock | Chất lượng bằng chứng | Không thấy event có thể do đường log bị lỗi |

### 23.1. Công thức minh họa

~~~text
Management exposure compliance =
  Số management endpoints chỉ reachable từ nguồn được phép
  / Tổng endpoints đã kiểm tra đầy đủ nguồn/đích

Authenticated transport coverage =
  Số management channels xác minh được SSH/TLS/SNMPv3 đúng baseline
  / Tổng management channels thuộc phạm vi

Privileged audit coverage =
  Số privileged sessions có identity + timestamp + event/command evidence
  / Tổng privileged sessions được xác định

Legacy exception overdue rate =
  Số ngoại lệ legacy quá hạn
  / Tổng ngoại lệ legacy đến kỳ xem xét
~~~

Khi báo cáo, phải ghi **mẫu số, thời gian đo, nguồn chứng cứ, vùng chưa kiểm tra và mức tin cậy**. Không công bố “100% an toàn” khi chưa kiểm tra OOB, cloud API, IPv6 hoặc automation paths.

## 24. Runbook chẩn đoán và xử lý nhanh

~~~text
1. DEFINE
   Xác định asset, owner, nhóm dịch vụ, đường quản trị, nguy cơ và change ID.

2. INVENTORY
   Liệt kê SSH/HTTPS/HTTP/Telnet/SNMP, API, OOB, vendor tunnel,
   IPv4/IPv6, controller, bastion, credentials và automation.

3. CLASSIFY
   Xác định ai tới được từ Internet/user/VPN/guest/cloud,
   dữ liệu nhạy cảm, quyền và blast radius.

4. VERIFY
   Kiểm tra SSH host key, TLS certificate/hostname,
   SNMPv3 security level, MFA/RBAC, logs, secret rotation.

5. PROTECT RECOVERY
   Backup config, protected OOB, test session thứ hai,
   approval, maintenance window và rollback.

6. MIGRATE
   Bật và thử kênh an toàn song song; áp management ACL;
   tắt giao thức yếu sau khi script/collector đã chuyển.

7. TEST
   Allow từ admin đúng role; deny từ nguồn không được phép;
   kiểm tra IPv4/IPv6, actual config và monitoring.

8. CLOSE
   Revoke secret cũ, lưu evidence, asset owner sign-off,
   exception expiry, drift và cert/key lifecycle alerts.
~~~

### 24.1. Dấu hiệu cần dừng thay đổi ngay

- Không thể xác minh đường OOB/console hoặc backup trước khi đổi ACL/AAA.
- Host key/certificate đích xuất hiện thay đổi bất thường chưa xác minh.
- Việc tắt giao thức cũ làm mất monitoring hoặc công cụ tự động quan trọng.
- Có traffic hợp lệ bị chặn hoặc management path không thể dùng từ đúng nguồn.
- Firewall/IPS/controller xuất hiện overload hoặc session drops ngoài mức đã duyệt.
- Phát hiện một nguồn quản trị chưa được kiểm kê hoặc tài sản nằm ngoài scope.

Khi gặp, dừng phần thay đổi liên quan, thông báo owner, giữ evidence và thực hiện rollback có thẩm quyền. Không vội **bật lại toàn bộ management service cho mọi nguồn** để khôi phục nhanh.

## 25. Checklist tự kiểm tra hệ thống

### 25.1. Nhận diện bề mặt

- [ ] Đã kiểm kê toàn bộ cổng, FQDN, IP/IPv6, API, OOB, Wi-Fi controller và vendor access.
- [ ] Mỗi endpoint có owner, business purpose, nguồn được phép và loại quyền quản trị.
- [ ] Đã đối chiếu inventory với config effective, firewall/cloud flow logs và asset discovery.
- [ ] Các đường quản trị “tạm” hoặc thừa được xử lý hoặc có ngoại lệ được phê duyệt.

### 25.2. Giao thức và peer verification

- [ ] Không dùng Telnet, HTTP plaintext, FTP/SNMPv1-v2c ở nơi yêu cầu cơ chế bảo vệ, trừ ngoại lệ được duyệt.
- [ ] SSH dùng phiên bản phù hợp và **host key được xác minh**.
- [ ] HTTPS/TLS certificate có SAN/hostname/chain/expiry hợp lệ; không tắt verify.
- [ ] SNMPv3 dùng authPriv khi dữ liệu nhạy cảm và được thiết bị hỗ trợ; source ACL/read-only view phù hợp.
- [ ] Các hop của proxy, load balancer, tunnel và log collector đã được đánh giá độc lập.
- [ ] Có quản lý vòng đời cert, SSH host key và thuật toán theo baseline.

### 25.3. Danh tính, mạng và secrets

- [ ] Admin/automation dùng identity riêng, có MFA ở privileged access boundary và RBAC least privilege.
- [ ] Management VLAN/VRF/firewall/SG chỉ allow đúng nguồn; thử từ user/guest/VPN thường/Internet.
- [ ] Không có bypass qua IPv6, OOB, cloud controller, vendor portal hoặc direct management interface.
- [ ] SSH private key, API tokens, VPN keys, SNMP secrets và backup config nằm trong kho bảo vệ.
- [ ] Có quy trình rotate/revoke credential, offboarding và cắt session/token phù hợp.
- [ ] Quyền emergency/break-glass có thời hạn, cảnh báo và audit.

### 25.4. Audit, vận hành và recovery

- [ ] Login, role, config change, API operation và thay đổi audit setting được ghi/truy vết.
- [ ] Log được đẩy tới nơi tách quyền, có retention/integrity và cảnh báo mất telemetry.
- [ ] Có kế hoạch backup, console/OOB, rollback và thử nghiệm trong scope được phép.
- [ ] Khi migration, các collector và script vẫn hoạt động; Telnet/HTTP/SNMP legacy đã được tắt sau kiểm chứng.
- [ ] Có source-zone verification, cert/key expiry alert, drift monitoring và owner sign-off.
- [ ] Các ngoại lệ có owner, risk acceptance, deadline và kế hoạch thay thế.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao Telnet trên VLAN nội bộ vẫn là một sai lầm bảo mật?**

Telnet không có bảo vệ mật mã thích hợp cho thông tin xác thực/lệnh. VLAN giảm đường truy cập nhưng không làm dữ liệu plaintext trở thành bí mật khi một điểm trên đoạn mạng bị quan sát. Cần SSH và kiểm soát nguồn cùng danh tính.

**2. “Đã bật SSH và dùng public key” có đảm bảo không bị MITM không?**

Chưa. Client còn phải xác minh **host key của server** bằng fingerprint hoặc trust mechanism đáng tin; user key chỉ xác thực phía client.

**3. Tại sao không dùng `curl -k` để bỏ qua lỗi certificate khi kiểm tra admin API?**

Vì bỏ certificate validation làm mất bảo đảm về danh tính server, có thể che giấu giả mạo. Phải xử lý CA/SAN/FQDN/expiry/clock hoặc đúng proxy.

**4. SNMPv3 ở mức `authNoPriv` có mã hóa dữ liệu không?**

Không. Nó hỗ trợ xác thực/toàn vẹn thông điệp nhưng không mã hóa payload. Với dữ liệu giám sát nhạy cảm cần `authPriv` và thuật toán phù hợp, cùng ACL/least privilege.

**5. Chỉ kiểm tra cổng SSH từ Internet và thấy bị chặn đã đủ chưa?**

Chưa. Management plane còn có thể reachable từ user VLAN, guest Wi-Fi, VPN, IPv6, cloud peering, API hoặc OOB. Cần kiểm thử theo ma trận nguồn–đích.

**6. VPN đã có MFA. Tại sao một thiết bị sau VPN vẫn cần RBAC và ACL?**

MFA ở VPN xác thực người vào VPN, không quyết định họ được phép quản trị mỗi thiết bị. Cần quyền theo asset/role, bastion/JIT, hạn chế route và audit.

**7. SSH/HTTPS hoạt động an toàn nhưng automation token có thể sửa tất cả security group. Rủi ro nằm ở đâu?**

Nằm ở cloud management API, token scope và vòng đời credential. Kênh HTTPS hợp lệ vẫn có thể thực thi yêu cầu trái mục đích bằng token bị lộ. Cần least privilege, short-lived identity, approval và audit.

**8. Vì sao không tắt Telnet ngay khi tìm thấy trên một thiết bị chỉ có một đường quản trị?**

Có thể tự khóa quyền truy cập hoặc làm đứt collector/automation. Cần chuẩn bị OOB/backup, chuyển sang kênh an toàn, thử xác thực/quyền/log, sau đó tắt giao thức cũ với rollback.

**9. OOB là đường mạng riêng, vậy có cần bảo vệ bằng SSH, MFA hoặc audit không?**

Có. OOB là đường quản trị đặc quyền, có thể bị lợi dụng nếu account và console server yếu. Mạng riêng không thay thế bảo vệ hop từ xa, danh tính, phân quyền và session logs.

**10. Khi thấy host key SSH thay đổi, có thể khẳng định đã bị tấn công không?**

Không. Host key có thể thay do thiết bị thay mới hoặc rotation; nhưng cần xác minh theo change record và nguồn tin cậy trước khi cập nhật trust store.

**11. Nếu SIEM không có log của một phiên cấu hình, có nghĩa phiên đó không xảy ra?**

Không. Có thể log chưa được bật, collector mất kết nối, queue tràn, clock lệch hoặc một admin có quyền xóa log. Cần phối hợp audit tại thiết bị, AAA/PAM và flow records.

**12. Biện pháp khắc phục nào quan trọng nhất khi thiết bị không hỗ trợ mã hóa hiện đại?**

Không có một biện pháp duy nhất đủ. Cần giảm đường phơi bày, hạn chế nguồn và quyền, giám sát, bảo vệ console/đường trung gian, xác nhận mức rủi ro còn lại và có kế hoạch nâng cấp/thay thế với thời hạn rõ.

---

**Ghi nhớ:** Sai lầm **không bảo vệ kênh quản trị** không chỉ là dùng Telnet hay HTTP. Một hệ thống có SSH/HTTPS vẫn có thể mất an toàn nếu **peer không được xác minh, cổng quản trị lộ sai vùng, danh tính/secret quá rộng, audit có thể bị xóa hoặc không có phương án khôi phục**. Bảo mật mạng nhiều lớp chỉ bền vững khi **đường điều khiển những lớp đó được kiểm soát và kiểm chứng độc lập**.
