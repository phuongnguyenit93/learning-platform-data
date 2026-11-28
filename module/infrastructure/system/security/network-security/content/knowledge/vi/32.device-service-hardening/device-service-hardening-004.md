# Quản trị qua kênh mã hóa trong hardening thiết bị và dịch vụ mạng

## 1. Quản trị qua kênh mã hóa là gì?

Router, switch, firewall, VPN gateway, IDS/IPS, access point, load balancer, thiết bị quản lý mạng và dịch vụ hạ tầng thường có một **mặt phẳng quản trị (management plane)** cho phép đăng nhập, xem cấu hình, đẩy chính sách, tạo tài khoản, nâng cấp firmware hoặc trích xuất log. Kênh quản trị đặc biệt nhạy cảm: ai chiếm được phiên quản trị có thể thay đổi cách mạng hoạt động, vô hiệu hóa giám sát, mở đường truy cập hoặc làm gián đoạn dịch vụ.

**Quản trị qua kênh mã hóa** là tổ chức các phiên điều khiển, API, giám sát và trao đổi tệp quản trị trên những giao thức bảo mật đã được xác thực, như **SSH, HTTPS/TLS, SNMPv3 authPriv, NETCONF over SSH, RESTCONF over HTTPS, gNMI qua TLS**, kết hợp phân đoạn mạng và kiểm soát danh tính. Mục tiêu là bảo vệ **tính bí mật, tính toàn vẹn và tính xác thực** của thông tin trên đường truyền, đồng thời hạn chế ai có thể thiết lập phiên.

Bài thuộc chương **Hardening thiết bị và dịch vụ mạng** trong module **SECURITY_NETWORK_SECURITY**. Kỹ năng này cần thiết khi triển khai phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và hạ tầng đám mây; ngay cả cơ chế phòng vệ mạnh cũng có thể bị vô hiệu hóa nếu đường quản trị lộ ra hoặc không được xác thực đúng.

Sau bài học, người học có thể:

- Phân biệt dữ liệu quản trị, control plane và data plane, nhận diện bề mặt quản trị có rủi ro.
- Giải thích SSH, TLS và SNMPv3 bảo vệ phiên ra sao và chúng **không** giải quyết điều gì.
- Thiết kế luồng quản trị dùng mạng riêng, ACL, bastion/jump host và VPN/ZTNA khi phù hợp.
- Quản lý định danh người quản trị, khóa SSH, chứng chỉ TLS, MFA, AAA, phân quyền và nhật ký.
- Thực hiện chuyển đổi khỏi Telnet, HTTP plaintext, SNMPv1/v2c và cách truyền tệp không an toàn.
- Kiểm tra cấu hình, chứng chỉ, quyền truy cập, dấu vết kiểm toán và phương án rollback.
- Chẩn đoán lỗi kết nối quản trị mà không hạ cấp cơ chế bảo mật một cách tùy tiện.

> **Nguyên tắc:** Kênh mã hóa chỉ là **một lớp**. Muốn quản trị an toàn phải kết hợp **đường truyền được xác thực + danh tính mạnh + phân quyền tối thiểu + mặt phẳng quản trị được cô lập + audit + vòng đời khóa/chứng chỉ**.

## 2. Mối đe dọa và giới hạn của mã hóa

### 2.1. Những tình huống cần phòng vệ

| Mối đe dọa | Ví dụ | Kiểm soát phù hợp |
|---|---|---|
| Nghe lén (eavesdropping) | Quan sát username, password hoặc lệnh quản trị trên Telnet | SSH/TLS được cấu hình và kiểm tra đúng |
| Man-in-the-middle (MITM) | Thiết bị giả mạo giao diện web của switch | Xác minh host key SSH hoặc chứng chỉ TLS |
| Sửa nội dung trên đường truyền | Can thiệp lệnh cấu hình hoặc phản hồi API | Bảo vệ toàn vẹn của giao thức được xác thực |
| Credential theft | Mật khẩu dùng lại, token API rò rỉ | MFA, vault, khóa ngắn hạn, quản lý phạm vi token |
| Đánh cắp phiên | Session/cookie/API token bị lộ | TLS, cookie flags khi áp dụng, session expiration, revoke |
| Lộ management plane | SSH/HTTPS có thể truy cập trực tiếp từ Internet | Phân đoạn, firewall, bastion, VPN/ZTNA, allowlist |
| Chiếm account đã được cấp quyền | Tài khoản admin bị phishing hoặc endpoint bị nhiễm mã độc | MFA, least privilege, PAM, ghi log và giám sát |
| Misconfiguration/downgrade | Bật lại HTTP, chấp nhận chứng chỉ sai hoặc thuật toán yếu | Baseline, kiểm tra cấu hình và change control |
| Supply-chain/firmware compromise | Thiết bị bị cài firmware độc hại | Firmware integrity, update, inventory, EDR/attestation khi có |

**Mã hóa không bảo vệ dữ liệu sau khi endpoint đã giải mã.** Nếu máy quản trị bị xâm nhập hoặc người dùng có đặc quyền quá rộng, phiên SSH/HTTPS hợp lệ vẫn có thể bị lợi dụng. Kênh mã hóa cũng không xác nhận thay đổi cấu hình là đúng về nghiệp vụ; cần phê duyệt, phân quyền, kiểm tra thay đổi và khả năng khôi phục.

### 2.2. Phân biệt ba lớp yêu cầu

1. **Transport security:** byte có được mã hóa, chống sửa và xác thực đúng peer trên đường truyền không?
2. **Authentication:** ai là người/ứng dụng đăng nhập, mức tin cậy của chứng thực có đủ không?
3. **Authorization và audit:** người đó được thực hiện lệnh gì, ở đâu, trong bao lâu; có ai kiểm tra hành động sau đó không?

Ví dụ: SSH với khóa hợp lệ chỉ đảm bảo phiên SSH sử dụng chứng thực thích hợp; tài khoản được cấp toàn bộ quyền cấu hình vẫn là rủi ro nếu bị chiếm. Ngược lại, tài khoản chỉ đọc nhưng kết nối qua Telnet vẫn có thể để lộ thông tin vận hành và mật khẩu.

## 3. Kiến trúc mặt phẳng quản trị an toàn

### 3.1. Data plane, control plane và management plane

| Mặt phẳng | Nhiệm vụ | Ví dụ lưu lượng |
|---|---|---|
| Data plane | Chuyển tiếp dữ liệu người dùng | HTTP của khách hàng, DNS query, ứng dụng |
| Control plane | Điều khiển trạng thái định tuyến/chuyển mạch | OSPF, BGP, routing adjacency và signaling |
| Management plane | Quản lý, giám sát và thay đổi thiết bị/dịch vụ | SSH, HTTPS API, SNMP, syslog, NETCONF, controller |

Các loại lưu lượng này có thể dùng chung interface/vật lý ở một số thiết bị. Hardening cần tạo **ranh giới logic và quyền truy cập** cho đường quản trị, không mặc định chỉ cần bật TLS trên cổng web.

### 3.2. Mẫu kiến trúc quản trị

~~~mermaid
flowchart LR
    U["Admin workstation được quản lý"] --> I["IdP / MFA / cấp quyền có hạn"]
    I --> Z["VPN hoặc ZTNA"]
    Z --> J["Bastion / PAM / jump host"]
    J --> F["Firewall policy management-zone"]
    F --> R["Router, switch, firewall: SSH"]
    F --> W["Web UI / API: HTTPS, mTLS nếu phù hợp"]
    F --> N["SNMPv3 / telemetry / controller"]
    R --> L["Audit / SIEM"]
    W --> L
    N --> L
    J --> L
~~~

Luồng chỉ minh họa. Tùy hạ tầng, IdP kiểm tra danh tính ở ZTNA hoặc PAM, còn thiết bị xác thực riêng qua AAA. Một số thiết bị cần mạng quản trị ngoài băng (out-of-band, OOB) độc lập với data plane để vẫn truy cập được khi routing sản xuất lỗi.

**Thiết kế nên xác định:**

- **Mạng quản trị riêng:** VLAN/VRF/subnet quản trị, interface OOB nếu thiết bị hỗ trợ; hạn chế đường từ mạng người dùng và Internet.
- **Điểm vào kiểm soát:** bastion/PAM hoặc VPN/ZTNA cấp quyền theo người, thiết bị, thời gian và thiết bị đích; không coi việc ở trong VPN là tự động được phép quản trị mọi thiết bị.
- **ACL/firewall hai chiều:** chỉ từ nguồn quản trị được phê duyệt tới cổng cần thiết; quản lý cả IPv4 và IPv6, vùng cloud security group và đường quản trị qua tunnel.
- **Danh tính và quyền:** MFA trước khi vào vùng đặc quyền; tích hợp AAA hoặc identity provider thích hợp, phân vai đọc/cấu hình/duyệt.
- **Quan sát:** log đăng nhập, phiên, thay đổi cấu hình, lệnh quan trọng, cấp quyền và thất bại; gửi về nơi có quyền quản trị tách biệt.
- **Phương án khẩn cấp:** OOB, break-glass có giám sát và thông tin khôi phục; không tự tắt đường quản trị cuối cùng khi thay đổi policy.

### 3.3. Quản trị trong băng và ngoài băng

**In-band management** đi qua mạng mang lưu lượng sản xuất. Nó tiết kiệm kết nối nhưng có thể bị gián đoạn khi routing, switch, ACL hoặc tunnel sản xuất gặp sự cố.

**Out-of-band management** dùng một mạng/đường riêng, đôi khi có console server và modem/đường truyền dự phòng, để xử lý sự cố ngay cả khi data plane không hoạt động. OOB vẫn phải có xác thực mạnh, mã hóa nơi giao thức cho phép, hạn chế truy cập, audit và kiểm soát console; **đường riêng không tự động an toàn**.

Một cổng console nối vật lý có thể không cung cấp mã hóa giống SSH. Khi truy cập console từ xa, bảo vệ hop mạng đến console server bằng SSH/TLS/VPN và kiểm soát thiết bị console server. Đồng thời cần kiểm soát truy cập vật lý.

## 4. Chọn giao thức quản trị phù hợp

| Nhu cầu | Ưu tiên | Giao thức/thói quen nên loại bỏ hoặc giới hạn |
|---|---|---|
| CLI quản trị thiết bị và máy chủ | SSH phiên bản hiện đại với host-key validation, khóa/certificate và AAA | Telnet, rlogin, rsh, SSHv1, thuật toán yếu |
| Web UI, portal và API | HTTPS/TLS 1.2/1.3 theo khả năng thiết bị, cert hợp lệ, kiểm tra hostname | HTTP plaintext, bỏ xác minh cert, TLS/SSL lỗi thời |
| Truyền cấu hình/log/tệp | SFTP/SSH, SCP được triển khai an toàn, HTTPS upload/download | FTP plaintext, TFTP qua đường không tin cậy |
| Quản lý cấu hình tự động | NETCONF over SSH, RESTCONF over HTTPS, gNMI với TLS | API HTTP không mã hóa hoặc token chia sẻ dài hạn |
| Giám sát trạng thái qua SNMP | SNMPv3 với authPriv, tài khoản chỉ đọc khi đủ | SNMPv1/v2c community string trên mạng không tin cậy |
| Log từ thiết bị đến collector | Syslog qua TLS khi có hỗ trợ, đường truyền bảo vệ, xác thực collector | Syslog UDP plaintext cho dữ liệu nhạy cảm |
| AAA cho quản trị | Cơ chế AAA được bảo vệ trong vùng quản trị; RADIUS/TLS khi hỗ trợ | Gửi bí mật AAA qua đoạn mạng không tin cậy |
| Quản lý cloud/network controller | API HTTPS với service identity, mTLS/OAuth theo sản phẩm và RBAC | Access key cố định, API công khai rộng quyền |

**Không phải cứ tên giao thức là bảo đảm an toàn.** Cần xác minh phiên bản, thiết lập thuật toán, danh tính peer, cấu hình authorization, bản vá và cách lưu credential. Ví dụ SNMPv3 chỉ ở mức `noAuthNoPriv` hoặc `authNoPriv` chưa có mã hóa payload; cần `authPriv` cho quản trị/telemetry nhạy cảm.

Tính năng và cú pháp tùy hãng, firmware và yêu cầu tuân thủ. Không sao chép lệnh Cisco, Juniper, Fortinet, Linux, Windows hoặc cloud sang nền tảng khác mà chưa đọc tài liệu tương ứng; ở đây tập trung vào nguyên lý và phương pháp kiểm tra.

## 5. SSH: bảo vệ CLI, tự động hóa và chuyển tệp

SSH thiết lập phiên có mã hóa, kiểm tra tính toàn vẹn và xác thực server bằng **host key**; sau đó client xác thực người dùng bằng khóa công khai, chứng chỉ SSH hoặc cơ chế được hỗ trợ. Các yếu tố quan trọng:

- Dùng SSHv2, phiên bản phần mềm còn hỗ trợ và các thuật toán đáp ứng baseline của tổ chức; ưu tiên thuật toán hiện đại được phần mềm và chính sách mật mã cho phép.
- Xác minh host key **trước khi cung cấp credential**. Ở lần đầu kết nối, fingerprint phải được đối chiếu với inventory đáng tin cậy hoặc một kênh độc lập được quản lý.
- Ưu tiên khóa SSH cá nhân hoặc SSH certificate, key lưu ở thiết bị/tokens an toàn nếu khả thi, có passphrase và kế hoạch rotate/revoke.
- Tài khoản quản trị riêng cho từng người hoặc identity có thể quy trách nhiệm; hạn chế tài khoản chia sẻ.
- Chỉ định nhóm/user có quyền đăng nhập, thời gian session, idle timeout và số lần thử phù hợp.
- Đưa quyền quản trị đặc biệt qua bastion/PAM hoặc AAA với kiểm soát riêng; ghi nhật ký đăng nhập, thất bại và hành động thay đổi.

**SSH host key** xác thực máy chủ, còn **user key** xác thực client. Hai loại khóa có nhiệm vụ khác nhau và cần quản lý vòng đời riêng. Nếu host key thay đổi bất ngờ, không tự động xóa entry cũ trong `known_hosts` hoặc tắt `StrictHostKeyChecking`; xác minh việc thay thiết bị, rebuild, rotation hay khả năng MITM.

### 5.1. Ví dụ kết nối SSH qua bastion

~~~bash
# Ví dụ mạng quản trị thử nghiệm. Host key của bastion và thiết bị
# đã được xác minh, lưu sẵn trong known_hosts.
ssh -o StrictHostKeyChecking=yes \
  -J admin@bastion.example.test \
  netadmin@192.0.2.10

# Kết nối SSH trực tiếp chỉ dùng khi policy và vị trí máy cho phép.
ssh -o StrictHostKeyChecking=yes netadmin@192.0.2.10

# Truyền file qua SFTP (trong phiên SSH được bảo vệ).
sftp netadmin@192.0.2.10
~~~

`192.0.2.10` là địa chỉ tài liệu thuộc TEST-NET, không phải IP thiết bị thật. Ví dụ giả định tài khoản, mạng và host key đã được thiết lập. Với cơ chế jump host, cần xác thực **cả bastion và thiết bị đích**. Không copy private key lên bastion chỉ để có thể kết nối; ưu tiên `ProxyJump`, SSH certificate hoặc cơ chế PAM phù hợp. Khi dùng agent forwarding, đánh giá rủi ro agent bị lạm dụng trên host trung gian và chỉ bật khi thực sự cần.

Lệnh `ssh-keyscan` hữu ích để *thu thập* public host key nhưng không tự xác thực key là đúng. Fingerprint thu qua mạng chưa tin cậy cần đối chiếu với inventory/vật chứng đáng tin trước khi tin tưởng.

### 5.2. Ví dụ hardening OpenSSH Server trên Linux

Đây là **đoạn cấu hình minh họa** cho một môi trường OpenSSH có nhóm `netadmin`, đã triển khai truy cập bằng public key và có đường khôi phục. Không áp dụng trực tiếp vào thiết bị production trước khi kiểm tra quyền và lối truy cập dự phòng.

~~~text
# Ví dụ một phần /etc/ssh/sshd_config (tùy phiên bản và policy).
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowGroups netadmin
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowTcpForwarding no
~~~

Giải thích và điều kiện:

- `PasswordAuthentication no` chỉ nên bật **sau khi** tài khoản được cấp quyền đã kiểm tra đăng nhập bằng khóa thành công và có lối OOB/console. Có nơi cần MFA qua keyboard-interactive hoặc PAM: `KbdInteractiveAuthentication no` có thể vô hiệu hóa luồng MFA đang dùng.
- `AllowGroups netadmin` phải khớp nhóm thực và cách IAM/LDAP/SSSD ánh xạ danh tính; sai tên nhóm có thể khóa toàn bộ admin.
- `PermitRootLogin no` yêu cầu phương thức nâng quyền có kiểm toán, chẳng hạn sudo theo vai trò.
- `AllowTcpForwarding no` và `X11Forwarding no` hạn chế khả năng forwarding không cần thiết, nhưng có thể ảnh hưởng workflows vận hành hợp lệ; đánh giá trước khi thay.
- `ClientAliveInterval` là tín hiệu keepalive ở SSH, không thay thế hoàn toàn idle timeout theo chính sách PAM/bastion; cần hiểu cách áp dụng theo phiên bản.
- Các file `sshd_config.d`, thứ tự xử lý tùy chọn và khối `Match` có thể làm chính sách thực tế khác đoạn minh họa.

Quy trình kiểm tra trước khi reload:

~~~bash
# Lệnh kiểm tra cú pháp cho OpenSSH Server trên Linux.
sudo sshd -t

# Xem cấu hình hiệu lực cho một ngữ cảnh, nếu phiên bản hỗ trợ.
sudo sshd -T -C user=netadmin,host=router-admin.example.test,addr=192.0.2.20

# Chỉ reload bằng cơ chế quản lý dịch vụ phù hợp SAU khi
# thử phiên SSH thứ hai, giữ phiên quản trị đang hoạt động.
# Ví dụ trên hệ thống systemd có service tên sshd:
# sudo systemctl reload sshd
~~~

`192.0.2.20` cũng là địa chỉ TEST-NET minh họa. Tên service có thể là `ssh` hoặc `sshd`; một số appliance không chạy OpenSSH như Linux. Kiểm tra đúng platform, đặt kế hoạch rollback và giữ console/OOB trước khi áp chính sách.

**Không sao chép một bộ ciphers/kex hard-code** từ bài hướng dẫn vào mọi firmware. Danh sách thuật toán an toàn thay đổi theo phiên bản, yêu cầu FIPS và hỗ trợ của client; kiểm thử negotiation theo baseline của tổ chức và loại bỏ thuật toán yếu theo hướng dẫn của nhà cung cấp.

### 5.3. Vòng đời khóa SSH và chứng chỉ SSH

- **Tạo khóa:** trên endpoint hoặc phần cứng tin cậy; chọn thuật toán/độ dài theo policy, ví dụ Ed25519 khi được phép hoặc RSA/ECDSA theo yêu cầu tương thích/tuân thủ.
- **Phân phối public key:** thông qua IAM/config management và phê duyệt. Không gửi private key qua chat, email hoặc commit vào repository.
- **Bảo vệ private key:** passphrase, quyền file, vault/token, MFA hoặc key hardware-backed khi phù hợp.
- **Rotate/revoke:** khi nghỉ việc, đổi vai trò, nghi bị lộ hoặc hết hạn; thu hồi khóa ở tất cả thiết bị/bastion, cập nhật danh sách được phép.
- **SSH certificates:** dùng CA SSH tin cậy và certificate người dùng có hạn ngắn để giảm phân phối static keys; bảo vệ và kiểm toán khóa CA riêng, thiết lập thu hồi và quy trình xử lý ngoại lệ.
- **Host-key rotation:** công bố fingerprint mới qua kênh đáng tin; cập nhật trust store trước hoặc đồng bộ với thay đổi, ghi log sự kiện.

**Rủi ro còn lại:** private key không bị lộ vẫn có thể bị lạm dụng nếu máy của admin đang bị kiểm soát; kiểm tra posture máy, chống malware, PAM/JIT access và giám sát session.

## 6. HTTPS/TLS cho giao diện web, API và controller

### 6.1. Cấu hình TLS phải xác minh cả máy chủ

HTTPS thiết lập TLS bên dưới HTTP, bảo vệ nội dung và tính toàn vẹn trên đường truyền. Tuy nhiên, nếu client chấp nhận bất kỳ chứng chỉ nào hoặc người vận hành bỏ qua cảnh báo, attacker có thể giả mạo endpoint.

Những yếu tố cần có:

1. **Certificate hợp lệ:** hostname/FQDN quản trị xuất hiện trong Subject Alternative Name (SAN), chuỗi CA tin cậy và thời hạn hợp lệ.
2. **Xác minh hostname và chain:** client/admin tool không dùng chế độ bỏ xác thực như `--insecure` của curl hoặc tự động “Accept all certificates”.
3. **TLS version/cipher policy:** ưu tiên TLS 1.3, duy trì TLS 1.2 chỉ khi được policy cho phép và còn cần tương thích; loại bỏ SSL/TLS cũ, thuật toán đã bị loại.
4. **Quản lý private key:** key file/vault/HSM chỉ cấp quyền cần thiết, rotate khi nghi bị lộ, không copy key lên máy quản trị không kiểm soát.
5. **Quản lý chứng chỉ:** cấp phát, SAN, chain, gia hạn, thu hồi, cảnh báo trước hết hạn, NTP và thử lại sau rotate.
6. **Session/API:** xác thực người dùng mạnh, RBAC, CSRF/session control khi áp dụng, access log và các header/cookie an toàn.
7. **Giới hạn phơi bày:** HTTPS trên management interface/VRF, ACL đúng nguồn; không để UI controller có quyền admin công khai Internet vì “đã bật TLS”.

TLS bảo vệ **từng kết nối được thiết lập**. Nếu dùng load balancer hoặc reverse proxy kết thúc TLS, đường từ proxy tới backend là một đoạn riêng; cần đánh giá mã hóa và xác thực cho đoạn đó, tránh giả định end-to-end chỉ vì client thấy ổ khóa HTTPS.

### 6.2. Kiểm thử TLS từ máy quản trị được phép

~~~bash
# Kiểm tra chain/hostname mà không bỏ qua xác minh chứng chỉ.
openssl s_client \
  -connect router.example.test:443 \
  -servername router.example.test \
  -verify_return_error \
  -verify_hostname router.example.test \
  </dev/null

# Thử yêu cầu HTTPS với xác minh chứng chỉ mặc định của curl.
curl --verbose --output /dev/null \
  https://router.example.test/
~~~

Đây là hostname minh họa; trong thực tế, cần DNS và CA trust store đã cấu hình đúng. Lỗi certificate không được “giải quyết” bằng cách tắt verify; cần xác định SAN, root/intermediate CA, thời gian máy, proxy inspection và cert ở đúng endpoint. Một lệnh `curl` thành công cũng chưa kiểm tra toàn bộ cipher/TLS policy: cần công cụ kiểm tra cấu hình TLS được phê duyệt hoặc cấu hình thiết bị và log negotiation.

### 6.3. Mutual TLS (mTLS) và API automation

Trong **mTLS**, client cũng trình chứng chỉ để server kiểm tra danh tính máy/ứng dụng, bổ sung cơ chế xác thực client ở tầng TLS. mTLS hữu ích cho controller-to-device, agent, automation hoặc API nội bộ nhưng đòi hỏi vòng đời chứng chỉ, SAN/identity mapping, CA, revocation, rotate và khả năng kiểm tra log.

mTLS không tự cấp quyền API. API vẫn cần RBAC/scopes/authorization và hạn chế thay đổi cấu hình nguy hiểm. Với OAuth/token, sử dụng token ngắn hạn và scope tối thiểu khi sản phẩm hỗ trợ; secret lưu trong vault, không đặt ở URL hoặc log. Thời gian thực của thiết bị cần đáng tin để đánh giá chứng chỉ, JWT và chính sách hiệu lực.

## 7. SNMPv3, telemetry và kênh log bảo mật

SNMP thường được dùng thu trạng thái interface, CPU, routing, cảnh báo và đôi khi hỗ trợ thay đổi cấu hình. SNMPv1/v2c dùng community string, **không cung cấp mức bảo vệ mật mã thích hợp** cho dữ liệu quản trị qua mạng không tin cậy.

Các mức bảo mật SNMPv3:

| Security level | Xác thực message | Mã hóa dữ liệu | Nhận xét |
|---|---|---|---|
| `noAuthNoPriv` | Không | Không | Không phù hợp cho dữ liệu quản trị nhạy cảm |
| `authNoPriv` | Có | Không | Giữ integrity/authentication, payload vẫn lộ |
| **`authPriv`** | **Có** | **Có** | Ưu tiên cho polling/trap/inform nhạy cảm |

Triển khai SNMPv3 cần kiểm tra **security level**, user/role, authentication/privacy algorithm được thiết bị hỗ trợ và đáp ứng baseline, SNMP engine ID, thông số khóa, ACL tới manager và quyền OID. Khi có thể, chỉ cấp quyền **read-only** cho hoạt động giám sát, tránh sử dụng quyền ghi không cần thiết.

Không giả định SNMPv3 tự động an toàn nếu dùng `noAuthNoPriv`, bí mật mặc định, thuật toán cũ hoặc management service vẫn public. Khi chuyển đổi, cần kiểm tra cả polling, traps/informs và các hệ thống giám sát; tắt community string và SNMPv1/v2c chỉ sau khi các collector tương ứng đã hoạt động qua SNMPv3.

**Telemetry streaming và log:** syslog UDP plaintext dễ bị nghe lén hoặc giả mạo và không đảm bảo giao hàng. Khi thiết bị/collector hỗ trợ, dùng **syslog qua TLS** với xác thực server và cấu hình đáng tin; cân nhắc xác thực client khi có nhu cầu. Những sản phẩm chỉ hỗ trợ syslog plaintext cần vận hành qua vùng mạng được cô lập hoặc tunnel được bảo vệ cùng các biện pháp bổ sung. Khả năng delivery, buffer, retry, định dạng và tính nguyên bản của log cần được đánh giá riêng; TLS không bảo đảm collector không mất event.

## 8. NETCONF, RESTCONF, gNMI và tự động hóa

Hệ thống network automation có thể có quyền thay đổi hàng trăm thiết bị; **service account và controller** vì thế là mục tiêu trọng yếu.

| Giao thức/cách sử dụng | Kênh bảo vệ điển hình | Điểm cần kiểm soát |
|---|---|---|
| NETCONF | SSH (thường cổng 830, tùy thiết bị) | SSH host key, AAA, datastore permissions, commit/rollback |
| RESTCONF | HTTPS/TLS | Certificate, authorization theo endpoint, token và scope |
| gNMI | gRPC qua TLS, có thể mTLS | Peer identity, role, stream permissions, client cert lifecycle |
| API quản trị cloud | HTTPS + identity service | IAM policy, role assumption/JIT, access key lifecycle, audit |
| Ansible/automation CLI | SSH/API bảo mật | Vault secret, inventory, change approval, giới hạn concurrency |

**Thử nghiệm khối lượng thay đổi:** nếu automation có thể làm sai ACL trên toàn mạng, cần code review, policy lint, dry-run/diff (khi được hỗ trợ), triển khai theo đợt, canary, health checks và rollback. Quản trị qua TLS giúp lệnh không bị sửa giữa đường, nhưng không bảo đảm cấu hình gửi đi đã đúng.

Không đặt mật khẩu, private key, token API trong playbook plaintext, terminal history hay CI logs. Dùng secret manager, biến môi trường được kiểm soát hoặc cơ chế cấp credential động, đồng thời giới hạn ai có thể đọc output của job automation.

## 9. Danh tính, AAA, MFA và đặc quyền

### 9.1. Từ “đăng nhập được” đến “được phép làm gì”

Một thiết kế quản trị cần quyết định:

- **Authentication:** admin hoặc service được xác thực bằng gì? Khóa SSH, chứng chỉ, AAA/IdP, FIDO2 hoặc MFA ở bastion/ZTNA khi sản phẩm hỗ trợ.
- **Authorization:** role nào được xem log, thay ACL, chỉnh định tuyến, cập nhật IDS signature hoặc reboot?
- **Accounting:** những sự kiện nào được ghi? Login success/failure, config diff, command execution, API call, privilege escalation, session timeout và break-glass.
- **Separation of duties:** người đề xuất, duyệt và triển khai thay đổi rủi ro cao có cần tách vai trò?
- **Emergency access:** ai có quyền mở truy cập khẩn cấp, ai giám sát, hạn bao lâu và cần review sau đó?

MFA ở VPN/bastion giảm nguy cơ lộ mật khẩu nhưng không tự chứng minh mọi CLI/API phía sau đã dùng MFA. Chính sách phải rõ ràng về **ranh giới đã xác thực**: thiết bị đích có tin danh tính qua proxy/AAA không, hay vẫn cho tài khoản local chung đi thẳng từ nguồn khác.

### 9.2. AAA và bảo vệ kênh đến máy chủ xác thực

Thiết bị mạng thường dùng TACACS+, RADIUS hoặc AAA tích hợp của hãng để xác thực và phân quyền lệnh. Không phải mọi phiên bản triển khai AAA truyền thống đều có mã hóa toàn bộ bản tin theo chuẩn bảo mật hiện đại. Cần giữ dịch vụ AAA trong **mạng quản trị bảo vệ**, chọn transport được mã hóa/xác thực được hãng hỗ trợ (ví dụ RADIUS/TLS khi tương thích), giới hạn client source và bảo vệ shared secret.

Xác định hành vi **AAA server không sẵn sàng**: fail-open nguy hiểm; fail-closed có thể khóa admin khỏi hệ thống. Thiết kế phương án local break-glass tối thiểu, password/secret trong vault, console/OOB và lịch kiểm thử định kỳ theo chính sách.

### 9.3. Quyền theo phiên và tài khoản khẩn cấp

- **Named accounts** dễ quy trách nhiệm hơn tài khoản `admin` dùng chung.
- **Just-in-time access:** chỉ cấp quyền cấu hình cho khoảng thời gian thay đổi, tự thu hồi sau khi kết thúc.
- **Privileged Access Management (PAM):** thực hiện cấp quyền, ghi session, phê duyệt, kiểm soát secrets theo khả năng của nền tảng.
- **Break-glass:** tài khoản khẩn cấp được bảo vệ trong vault, kiểm soát người truy cập, có log và review sau dùng.
- **Offboarding:** khi thay người/đổi vai trò, revoke key/cert, token, group, AAA, VPN/ZTNA và session đang tồn tại nếu cần.

Thiết bị quản trị nên có idle/session timeout hợp lý để không giữ phiên đặc quyền vô hạn. Logging toàn bộ lệnh có thể chứa secret và dữ liệu nhạy cảm; cân bằng audit với redaction, phân quyền đối với chính log và retention.

## 10. Quy trình chuyển đổi khỏi giao thức quản trị không an toàn

Ví dụ: một thiết bị switch được quản lý bằng Telnet và HTTP nội bộ, monitoring dùng SNMPv2c. Mục tiêu chuyển thành SSH/HTTPS/SNMPv3, qua management VLAN với jump host, vẫn có khả năng khôi phục nếu cấu hình sai.

~~~mermaid
flowchart TD
    A["Kiểm kê thiết bị, giao thức, đường vào và phụ thuộc"] --> B["Định nghĩa baseline và đường khôi phục OOB"]
    B --> C["Bật kênh an toàn song song, cấp khóa/chứng chỉ"]
    C --> D["Kiểm tra xác thực, role, log, certificate/host key"]
    D --> E{"Kết nối quản trị và monitoring đạt yêu cầu?"}
    E -->|"Không"| F["Phân tích, sửa hoặc rollback có kiểm soát"]
    F --> C
    E -->|"Có"| G["Giới hạn management ACL, thử từ nguồn hợp lệ và bị chặn"]
    G --> H["Tắt Telnet/HTTP/SNMPv1-v2c khi không còn phụ thuộc"]
    H --> I["Theo dõi sự cố, drift, ghi bằng chứng và lịch rotate"]
~~~

### 10.1. Các bước chi tiết để tránh tự khóa quyền quản trị

1. **Inventory:** liệt kê firmware, interface, management IP/FQDN, IPv4/IPv6, Telnet/HTTP/SSH/HTTPS/SNMP, tài khoản, automation, collector và nơi cấu hình được lưu. Kiểm tra các thiết bị chưa hỗ trợ giao thức an toàn.
2. **Xác định đường khôi phục:** console/OOB hoặc phiên đang hoạt động, config backup đã mã hóa, lệnh rollback theo hãng, người và thời gian thực hiện.
3. **Chuẩn bị trust:** tạo/đăng ký SSH host key hoặc TLS certificate, nạp CA nếu cần, cấu hình NTP, tài khoản/AAA, key và quyền theo role.
4. **Mở kênh an toàn:** bật SSH/HTTPS/SNMPv3 trong mạng quản trị giới hạn, chưa tắt đường cũ khi đường mới chưa được kiểm tra.
5. **Xác minh truy cập:** admin thật và account automation đăng nhập thành công, đúng role, ghi log, cert/key hợp lệ; SNMPv3 polling/traps và API automation hoạt động.
6. **Giới hạn ACL:** chỉ nguồn qua bastion/management network tới cổng cần thiết; kiểm tra firewall, NAT, IPv6, cloud SG và đường OOB.
7. **Vô hiệu hóa kênh cũ:** tắt Telnet, HTTP plaintext, community SNMPv1/v2c hoặc đóng cổng; đảm bảo không còn tool phụ thuộc.
8. **Diễn tập rollback:** kiểm tra tình huống AAA down, chứng chỉ hết hạn, DNS lỗi, bastion không sẵn sàng hoặc chính sách ACL sai.
9. **Giám sát sau thay đổi:** kiểm tra audit log, đăng nhập thất bại, availability của collector, config drift và tính đúng của quyền.
10. **Ghi hồ sơ:** cấu hình trước/sau, change ID, người duyệt, kết quả test, ngoại lệ/tạm giữ và hạn review.

**Không tắt Telnet/HTTP ngay từ bước đầu** nếu đó là đường truy cập duy nhất của thiết bị; cũng không giữ giao thức yếu lâu dài chỉ vì lo lockout. Cần kế hoạch chuyển đổi và kiểm thử có thể xác minh, với mốc vô hiệu hóa rõ ràng.

### 10.2. Mẫu baseline mang tính chính sách

~~~yaml
management_plane:
  access_paths:
    - "managed-admin-workstation -> ZTNA/VPN -> bastion -> management-zone"
  allowed_sources:
    - "management-zone CIDRs defined by network team"
  allowed_protocols:
    cli: SSHv2
    web_api: HTTPS_with_verified_TLS
    monitoring: SNMPv3_authPriv
    configuration: NETCONF_over_SSH_or_RESTCONF_over_HTTPS
  prohibited_legacy_protocols:
    - Telnet
    - HTTP_plaintext
    - SNMPv1
    - SNMPv2c
    - FTP_plaintext
  identity:
    - "individual_accounts"
    - "MFA_at_privileged_access_boundary"
    - "role_based_authorization"
  session:
    - "audited_access"
    - "idle_timeout"
    - "limited_emergency_access"
  crypto:
    - "approved_algorithms_and_versions"
    - "verified_host_keys_and_certificate_chains"
    - "managed_key_and_certificate_lifecycle"
  assurance:
    - "config_backup_with_encryption"
    - "logging_to_protected_collector"
    - "change_review_and_rollback_tested"
~~~

Mẫu này là **policy mô tả mục tiêu**, không phải file cấu hình áp dụng trực tiếp. Trên thiết bị không hỗ trợ một giao thức, cần đánh giá nâng cấp, thay thiết bị hoặc giải pháp bù trừ có phê duyệt và ngày hết hạn.

## 11. Xác minh rằng đường quản trị thực sự an toàn

Bật SSH hoặc HTTPS là bước đầu; cần **kiểm thử từ nhiều nguồn** để phát hiện ACL sai, fallback plaintext hoặc chứng chỉ không đúng.

| Kiểm tra | Cách xác minh | Kết quả mong đợi |
|---|---|---|
| Nguồn quản trị được phép | Từ managed workstation/bastion, kết nối SSH/HTTPS | Kết nối thành công qua đường được phê duyệt |
| Nguồn không được phép | Thử kết nối từ mạng user/test không có quyền | Bị chặn và có log phù hợp |
| Giao thức cũ | Kiểm tra Telnet, HTTP plaintext, SNMPv1/v2c | Không còn service phơi bày ngoài ngoại lệ được duyệt |
| Host key SSH | Đối chiếu fingerprint với inventory tin cậy | Khớp, cảnh báo khi thay bất thường |
| TLS certificate | Xác minh hostname/SAN, trust chain và ngày hết hạn | Hợp lệ, không bỏ qua verify |
| Chứng thực người dùng | Kiểm tra MFA tại điểm cần thiết, named identity, offboarding | Không dùng credential chia sẻ trái policy |
| Quyền | Thử tài khoản read-only và config role | Read-only không thể sửa cấu hình |
| SNMPv3 | Poll/trap ở authPriv, quyền OID và ACL | Hoạt động đúng, không fallback cộng đồng cũ |
| Kênh backend | Xem cách TLS kết thúc ở proxy và đi tiếp tới device | Các đoạn có kiểm soát và xác thực thích hợp |
| Logging/audit | Thử login đúng/sai, thay đổi cấu hình test | Sự kiện tới collector, có actor, UTC, action và outcome |
| Backup/rollback | Diễn tập khôi phục cấu hình và console/OOB | Có thể khôi phục quyền quản trị mà không phá policy |

Ví dụ dùng các công cụ mạng chỉ trên **mạng thử nghiệm hoặc hệ thống được phép**:

~~~bash
# Kiểm tra TCP SSH port từ máy quản trị Linux.
nc -vz 192.0.2.10 22

# Kiểm tra HTTPS certificate/hostname (không bỏ qua verify).
openssl s_client \
  -connect router.example.test:443 \
  -servername router.example.test \
  -verify_return_error \
  -verify_hostname router.example.test \
  </dev/null

# Đăng nhập SSH với host-key checking bật.
ssh -o StrictHostKeyChecking=yes netadmin@192.0.2.10
~~~

**Không dùng phép thử cổng làm kết luận đầy đủ.** Cổng 22 đang mở chưa chứng minh SSH server có host key đúng, thuật toán phù hợp hoặc quyền người dùng tối thiểu. Cổng 443 đang mở chưa chứng minh cert đúng hoặc HTTPS đã được bảo vệ ở backend.

Khi kiểm tra nguồn không được phép, nên dùng môi trường kiểm thử có phê duyệt và giữ bằng chứng log từ firewall. Trạng thái không kết nối được có thể do routing/NAT/thiết bị tắt, nên cần kiểm tra cùng policy counter và vùng quan sát.

## 12. Logging, giám sát và điều tra sự cố kênh quản trị

Kênh quản trị là một phần quan trọng trong **network forensics** và incident response. Mỗi hành động có ảnh hưởng an ninh cần có dấu vết đủ để tái lập diễn biến.

### 12.1. Những sự kiện nên ghi

- Login success/failure, source IP, device/user identity, MFA decision (nếu thấy được), thời điểm UTC.
- Khởi tạo/kết thúc phiên, session timeout, quyền được cấp và thay đổi role.
- Thay đổi cấu hình, command/API quan trọng, config version/diff, commit/rollback.
- Tạo/xóa user, thêm public key SSH, cấp/thu hồi cert, thay CA trust, thay token hoặc secret.
- Bật/tắt Telnet/HTTP/SNMP, thay rule firewall, ACL, VPN, IDS/IPS, DNS resolver và routing.
- Truy cập khẩn cấp và break-glass, lý do, người duyệt, thời hạn, review.
- Tình trạng hệ thống thu log, đường TLS/syslog, đồng bộ thời gian và lỗi xuất log.

Dữ liệu log quản trị có thể chứa command parameters nhạy cảm; cần mask secrets khi có thể, không ghi private key/password/token trong plaintext. Audit log nên được chuyển tới hệ thống có quyền tách biệt với admin của thiết bị, theo chính sách retention và bảo toàn chứng cứ.

### 12.2. Tình huống phát hiện hoạt động bất thường

Nếu SIEM thấy đăng nhập SSH thành công từ nguồn quản trị chưa từng thấy, ngay sau đó có thay ACL firewall:

1. Kiểm tra admin identity, device posture, thời gian, điểm đi qua bastion và AAA logs.
2. Đối chiếu config diff, command/session audit, change ticket, VPN/IdP authentication và phê duyệt.
3. Tách dấu hiệu **sử dụng hợp lệ nhưng bất thường** với **truy cập trái phép** dựa trên bằng chứng, tránh kết luận chỉ từ một IP.
4. Nếu nghi bị lộ khóa/token, thu hồi session/credential liên quan theo quy trình, cô lập quyền có thể bị lợi dụng và giữ log đầy đủ.
5. Bảo toàn các dấu vết quan trọng (hash, thời gian, nguồn, chain of custody), kiểm tra policy khác bị đổi và theo dõi sau khắc phục.

**Mã hóa làm khó nghe lén trên mạng**, nhưng forensic của phiên có thể dựa vào bastion/PAM logs, SSH server audit, API gateway, AAA và config change history. Không kỳ vọng một PCAP ở ngoài endpoint tự đọc được lệnh SSH hay nội dung HTTPS đã mã hóa.

## 13. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SSH hỏi “host key changed” | Thay thiết bị, rotate key, sai IP/DNS hoặc MITM | Xác minh fingerprint qua kênh tin cậy, không bỏ qua cảnh báo |
| SSH key đúng nhưng không đăng nhập | Quyền file, group, AAA, authorized keys, algorithm policy | Xem auth log và effective config, thử trên phiên dự phòng |
| Không truy cập sau tắt password | Public key chưa được cấp, KbdInteractive bị vô hiệu, ACL sai | Dùng console/OOB đã chuẩn bị, khôi phục theo quy trình |
| Web UI báo certificate error | SAN sai, CA thiếu, cert hết hạn, clock lệch, inspection | Kiểm tra cert chain, FQDN, NTP và peer thực sự |
| TLS thành công nhưng API trả 403 | Authorization/RBAC/API scope thiếu | Kiểm tra role, policy, log của endpoint |
| SNMPv3 không có dữ liệu | Sai security level, engine/user/secret, ACL, collector không hỗ trợ | Đối chiếu cấu hình hai đầu, không fallback về v2c tràn lan |
| VPN thành công nhưng quản trị không vào | Segmentation, jump host, route, policy chưa cấp quyền | So firewall logs, IAM và đường đến management zone |
| Mất syslog qua TLS | Collector cert/trust, routing, queue, expiry | Kiểm tra logs/queue và chuỗi chứng chỉ, không mặc định bỏ TLS |
| SSH/TLS có thuật toán yếu | Thiết bị quá cũ, fallback hoặc cấu hình còn legacy | Kiểm tra inventory/firmware, nâng cấp và baseline được duyệt |
| Break-glass account bị dùng nhiều | AAA lỗi, quy trình JIT bất tiện hoặc hành vi bất thường | Điều tra nguyên nhân, giảm dùng tài khoản khẩn, audit |

Thói quen nguy hiểm nhất là **tắt xác minh TLS hoặc host key để “làm cho kết nối chạy”**. Đây có thể che giấu giả mạo máy chủ. Cần xử lý đúng nguồn tin cậy, DNS, certificate và đường quản trị.

## 14. Case study: nâng cấp quản trị của switch và firewall ở chi nhánh

Một chi nhánh quản trị switch qua Telnet ở VLAN chung, firewall có giao diện HTTP nội bộ và hệ thống monitoring dùng SNMPv2c. Đội bảo mật muốn bảo vệ mặt phẳng quản trị mà không mất khả năng xử lý sự cố.

### 14.1. Phân tích rủi ro ban đầu

- Người dùng có quyền vào VLAN chung có thể tiếp cận cổng Telnet/HTTP; thông tin đăng nhập và lệnh cấu hình có nguy cơ bị nghe lén.
- Community string SNMPv2c có thể bị quan sát/tái sử dụng; polling và cấu hình giám sát thiếu quyền theo user.
- Không có bastion/session audit; khó xác định ai đã đổi ACL.
- Một số script dùng tài khoản quản trị chung và chưa ghi rõ phụ thuộc.
- Nếu tắt các cổng cũ trước khi có đường mới, on-call có thể bị khóa khỏi thiết bị.

### 14.2. Thiết kế đích

- Tạo management VLAN/VRF và ACL cho bastion đã được bảo vệ; kiểm tra routing và IPv6.
- Thiết lập SSH, danh tính individual, khóa SSH/SSH certificate theo hỗ trợ; HTTPS với certificate được trust và hostname rõ.
- Nâng hệ thống giám sát lên SNMPv3 authPriv, gán read-only view khi phù hợp.
- Tạo quyền automation riêng, kiểm tra token/keys và phân quyền lệnh; dùng PAM/JIT cho thay đổi có rủi ro.
- Gửi auth/config logs tới collector bảo vệ, có đồng bộ thời gian.
- Chuẩn bị OOB/console, config backup, rollback, canary một switch trước khi mở rộng.

### 14.3. Quy trình triển khai và tiêu chí chấp nhận

| Giai đoạn | Hoạt động | Bằng chứng thành công |
|---|---|---|
| Pilot | Cấu hình một switch trong maintenance window | SSH/HTTPS xác minh đúng peer, audit log đầy đủ |
| Quyền | Thử tài khoản viewer và config-admin | Viewer không đổi config; admin có approval |
| Monitoring | Chuyển collector SNMPv3 | Counters và alerts hoạt động; không dùng community cũ |
| Segmentation | Test từ bastion, VLAN user và đường ngoài VPN | Chỉ đường được phép thành công; deny có logs |
| Chuyển đổi | Vô hiệu Telnet/HTTP và SNMPv2c | Service kiểm tra không còn tiếp cận từ nguồn không hợp lệ |
| Recovery | Mô phỏng sai ACL/AAA hoặc cert hết hạn ở lab | Có thể dùng OOB và rollback đúng quy trình |
| Mở rộng | Rollout theo nhóm thiết bị có giám sát | Không tăng bất thường failed logins, config drift hoặc mất telemetry |

**Kết luận:** đường quản trị được mã hóa giúp giảm nghe lén và MITM, nhưng kết quả an toàn phụ thuộc việc **xác minh đúng peer, hạn chế nguồn truy cập, phân quyền theo danh tính, audit và khôi phục khi lỗi cấu hình**. Hệ thống vẫn cần theo dõi độ tin cậy, bản vá thiết bị và bảo vệ endpoint của admin.

## 15. Checklist thực hành

### Trước thay đổi

- [ ] Đã kiểm kê thiết bị/dịch vụ, firmware, interface, IPv4/IPv6 và kênh quản trị.
- [ ] Đã xác định vùng quản trị, sơ đồ route và điểm vào bastion/VPN/ZTNA/OOB.
- [ ] Đã có quyền, change ticket, backup config và kế hoạch rollback.
- [ ] Đã chuẩn bị host key/certificate, CA trust, DNS, NTP và chính sách crypto.
- [ ] Đã xác định account, SSH keys, MFA, AAA, role và những script/collector phụ thuộc giao thức cũ.
- [ ] Đã thiết kế log/audit và thời gian lưu dữ liệu nhạy cảm phù hợp.

### Trong thay đổi

- [ ] SSH/HTTPS đã được bật với kiểm tra host key/chứng chỉ, không bỏ qua xác minh.
- [ ] SNMPv3 authPriv, SFTP/NETCONF/RESTCONF/gNMI được bảo vệ theo nhu cầu và khả năng.
- [ ] Người thật và automation account đăng nhập đúng quyền; không lộ secret trong log.
- [ ] Management ACL cho đúng nguồn, IPv4/IPv6, cổng và interface/VRF.
- [ ] Đã test bastion, AAA, MFA, session timeout, local emergency access và đường OOB.
- [ ] Đã tắt Telnet, HTTP plaintext, SNMPv1/v2c cùng giao thức cũ sau khi kiểm chứng tương đương.
- [ ] Có xác nhận traffic hợp lệ, audit logs, monitoring và config diff.

### Sau thay đổi

- [ ] Theo dõi thất bại đăng nhập, certificate expiry, host-key rotation, thay đổi ACL và config drift.
- [ ] Kiểm tra source không được phép thực sự bị deny, có log minh chứng.
- [ ] Kiểm tra phân quyền read-only, hành động admin và khả năng revoke credential.
- [ ] Đã rà soát tệp cấu hình/secret backup, bản ghi session, retention và quyền truy cập.
- [ ] Đã cập nhật inventory, runbook, kết quả test, ngoại lệ còn tồn tại và lịch rotate.
- [ ] Đã có lịch diễn tập OOB/rollback và kiểm tra khả năng khôi phục.

## 16. Câu hỏi tự kiểm tra

**1. Chỉ bật HTTPS trên giao diện firewall có đủ bảo mật quản trị không?**

Không. Cần xác minh chứng chỉ/hostname và phiên bản TLS, giới hạn nguồn truy cập qua management zone, sử dụng authentication/MFA/RBAC, audit và vòng đời khóa/chứng chỉ.

**2. Vì sao không nên tự động “accept new host key” khi SSH báo fingerprint thay đổi bất ngờ?**

Host key mới có thể hợp lệ do thay thiết bị hoặc rotation, nhưng cũng có thể là MITM. Cần xác minh fingerprint với nguồn tin cậy trước khi cập nhật trust store.

**3. SNMPv3 authNoPriv đã đáp ứng mã hóa dữ liệu giám sát chưa?**

Chưa. `authNoPriv` xác thực và bảo vệ toàn vẹn message nhưng không mã hóa payload. Cần `authPriv` với thuật toán được phê duyệt cho dữ liệu nhạy cảm.

**4. Vì sao cần giữ đường console/OOB khi tắt Telnet và password authentication?**

Một cấu hình sai về SSH key, ACL, nhóm quyền hoặc AAA có thể chặn mọi phiên từ xa. Console/OOB được bảo vệ và phương án rollback giúp khôi phục truy cập an toàn.

**5. SSH qua bastion có làm cho mọi lệnh trên thiết bị đều hợp lệ không?**

Không. Bastion là một lớp kiểm soát đường đi và danh tính; vẫn cần RBAC/AAA, phê duyệt thay đổi, audit lệnh/session và kiểm soát quyền thiết bị đích.

**6. HTTPS đến load balancer có nghĩa là traffic từ load balancer tới thiết bị/backend cũng mã hóa không?**

Không mặc định. TLS có thể kết thúc ở proxy/LB. Phải kiểm tra hop phía sau, cách xác thực peer, token và quyền API riêng.

**7. Vì sao không nên dùng một khóa SSH chung cho toàn bộ đội Network?**

Khó truy vết người thực hiện, khó thu hồi khi thay nhân sự và tăng blast radius khi khóa bị lộ. Nên dùng danh tính riêng, khóa/certificate có lifecycle và least privilege.

**8. Để xác nhận đã vô hiệu Telnet sau migration, chỉ quét cổng 23 thấy đóng đã đủ chưa?**

Chưa. Cần kiểm tra đúng interface/IPv4/IPv6/vùng nguồn, cấu hình hiệu lực và log, đồng thời xác minh SSH/HTTPS và hệ thống giám sát hoạt động sau chuyển đổi.

---

**Ghi nhớ:** Hardening management plane không dừng ở việc “bật SSH/HTTPS”. Một hệ thống quản trị an toàn cần **giao thức mã hóa được xác thực, mạng quản trị cô lập, danh tính/đặc quyền được kiểm soát, secret và chứng chỉ có vòng đời, audit đầy đủ, kiểm thử rollback và loại bỏ giao thức plaintext**.
