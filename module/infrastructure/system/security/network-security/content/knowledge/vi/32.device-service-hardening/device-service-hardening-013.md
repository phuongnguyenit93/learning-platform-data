# Hardening SNMP và giao thức quản trị

## 1. Vai trò của giao thức quản trị trong an toàn mạng

Thiết bị mạng thường có ít nhất hai nhóm luồng: **lưu lượng dữ liệu (data plane)** để chuyển tiếp gói và **lưu lượng quản trị (management plane)** để cấu hình, đọc trạng thái, cập nhật, giám sát hoặc điều khiển thiết bị. Một router có ACL bảo vệ người dùng rất tốt vẫn có thể bị chiếm quyền nếu dịch vụ Telnet, giao diện web hoặc SNMP được mở từ một vùng mạng không đáng tin cậy.

**Hardening SNMP và giao thức quản trị** là việc giảm bề mặt tấn công của management plane: lựa chọn giao thức có bảo vệ phù hợp, tắt dịch vụ không cần, giới hạn nguồn truy cập, phân quyền tối thiểu, quản lý bí mật, ghi nhật ký và kiểm chứng sau thay đổi. Nội dung áp dụng cho router, switch, firewall, VPN gateway, wireless controller/AP, IDS/IPS appliance, thiết bị DNS/load balancer và cả thiết bị mạng ảo hay hệ thống quản lý trên đám mây.

Trong module **SECURITY_NETWORK_SECURITY**, hardening management plane hỗ trợ các lớp phòng vệ mạng như phân đoạn, firewall, VPN, kiểm soát kết nối, DNS, giám sát xâm nhập và kiến trúc mạng an toàn. **SNMP** thiên về giám sát/truy vấn hoặc một số tác vụ cấu hình nếu được cấp quyền; **SSH, NETCONF, RESTCONF, HTTPS và API** thường dùng để quản trị tương tác và tự động hóa. Chính sách an toàn phải dựa trên **tài sản, chức năng và khả năng thực tế của từng firmware**, không áp dụng một dòng lệnh cho mọi hãng.

Sau bài học, người học có thể:

- Phân biệt SNMPv1, SNMPv2c và SNMPv3; giải thích các chế độ bảo mật của SNMPv3.
- Xây dựng chính sách SNMP theo nguyên tắc **chỉ đọc, xác thực, mã hóa và giới hạn phạm vi**.
- Bảo vệ SSH, giao diện web, NETCONF, RESTCONF và dịch vụ AAA của thiết bị mạng.
- Phân đoạn mạng quản trị, giảm tiếp xúc từ các mạng người dùng/Internet và kiểm soát đường cứu hộ.
- Thiết kế kế hoạch chuyển đổi từ giao thức yếu, kiểm chứng luồng hợp lệ và luồng bị chặn, có rollback.
- Giám sát sai lệch cấu hình, mất telemetry, lỗi xác thực và dấu hiệu truy cập quản trị trái phép.

> **Nguyên tắc chủ đạo:** Một giao thức có hỗ trợ mã hóa vẫn cần được **giới hạn nguồn truy cập, phân quyền, bảo vệ thông tin xác thực, giám sát và cập nhật**. Không có một cài đặt riêng lẻ nào thay thế được toàn bộ các kiểm soát trên.

## 2. Nhận diện bề mặt tấn công management plane

### 2.1. Các giao thức thường gặp

| Giao thức/dịch vụ | Mục đích | Rủi ro cần quản lý | Hướng hardening |
| --- | --- | --- | --- |
| **SNMPv1/v2c** | Giám sát qua community string | Community truyền trong bản tin không mã hóa, dễ bị lộ khi lưu lượng bị quan sát; phân quyền dựa trên community | Ưu tiên ngừng sử dụng và chuyển sang SNMPv3 có bảo vệ |
| **SNMPv3** | Giám sát qua user/security level, có thể gửi thông báo | Tùy chọn `noAuthNoPriv` hoặc `authNoPriv` chưa đáp ứng yêu cầu bí mật; cấu hình user/view yếu | Ưu tiên `authPriv`, chỉ đọc, giới hạn collector và thuật toán được hỗ trợ an toàn |
| **Telnet / rlogin / rsh** | Điều khiển terminal cũ | Không bảo vệ đầy đủ mật khẩu/phiên và thiếu cơ chế bảo mật hiện đại | Tắt khi đã có đường thay thế an toàn |
| **SSHv2** | CLI, truyền file và kênh quản trị an toàn | Cấu hình cipher/KEX yếu, quản lý khóa kém, truy cập từ mọi nơi | Dùng thuật toán được hãng hỗ trợ an toàn, khóa host được kiểm chứng, AAA/RBAC và giới hạn nguồn |
| **HTTP / HTTPS UI** | Giao diện web quản trị | HTTP rõ, TLS cũ, tài khoản mặc định, session yếu, ứng dụng có lỗ hổng | Tắt HTTP; bảo vệ HTTPS, phiên, MFA/SSO khi được hỗ trợ, giới hạn nguồn |
| **NETCONF qua SSH** | Quản lý cấu hình dạng YANG/XML, thường dùng TCP/830 | Tài khoản API quyền rộng, thay đổi cấu hình tự động thiếu kiểm soát | SSH tin cậy, phân quyền thao tác, audit, xác nhận thay đổi và rollback |
| **RESTCONF qua HTTPS** | Quản lý dữ liệu YANG qua HTTP/TLS | Token bị lộ, API quá quyền, endpoint công khai | TLS, token/cert theo danh tính, RBAC, giới hạn nguồn và audit |
| **Vendor API / controller** | Quản lý mạng tập trung, tự động hóa | Service account dùng chung, token không có hạn, controller quá quyền | Mỗi tác nhân một danh tính, scope tối thiểu, quản lý secrets và log |
| **Console / OOB / BMC** | Quản trị cứu hộ ngoài đường dữ liệu | Tài khoản dự phòng yếu, đường OOB bị kết nối vào mạng không tin cậy | Vùng quản trị riêng, MFA/jump host, ghi log và kiểm soát truy cập vật lý |

Port thường gặp: **UDP/161** cho SNMP request/response, **UDP/162** cho SNMP trap/inform, **TCP/22** cho SSH, **TCP/830** cho NETCONF over SSH và **TCP/443** cho HTTPS/RESTCONF. Đây là **port thông dụng**, không phải bằng chứng rằng dịch vụ đang chạy hoặc an toàn; cần kiểm tra cấu hình thực tế của thiết bị, đặc biệt khi hãng cho phép thay đổi port hoặc có proxy/controller trung gian.

### 2.2. Mô hình nguồn truy cập hợp lệ

~~~mermaid
flowchart LR
    A["Quản trị viên"] -->|"MFA/SSO"| B["Bastion / Jump host"]
    B -->|"SSH/HTTPS đã kiểm soát"| C["VRF/VLAN quản trị"]
    D["Monitoring collector"] -->|"SNMPv3 authPriv"| C
    C --> E["Router / Switch / Firewall / AP"]
    E -->|"SNMPv3 trap/inform"| F["Trap collector"]
    E -->|"Syslog bảo vệ"| G["SIEM / Log server"]
    H["Mạng người dùng / Internet"] -.->|"Deny"| C
~~~

Sơ đồ diễn tả **quan hệ chính sách**, không phải đường đi vật lý bắt buộc. Jump host, collector, SIEM và thiết bị có thể ở các mạng khác nhau; mọi đường truyền phải được rà soát theo thực tế. Với hệ thống hỗ trợ out-of-band, đường cứu hộ nên độc lập với data plane nhưng vẫn cần xác thực, phân quyền và audit.

## 3. SNMP: cơ chế và khác biệt giữa các phiên bản

SNMP dùng để truy vấn và nhận các thông số thiết bị thông qua **Management Information Base (MIB)** và **Object Identifier (OID)**. Thành phần **manager/collector** thực hiện GET/GETNEXT/GETBULK để đọc dữ liệu; **agent** trên thiết bị phản hồi. SNMP cũng có **SET** nhằm thay đổi giá trị nếu agent hỗ trợ và danh tính được cấp quyền, nên SNMP là bề mặt có thể phát sinh thay đổi chứ không đơn thuần là telemetry.

### 3.1. Chọn phiên bản và chế độ bảo mật

| Phiên bản/chế độ | Xác thực | Bảo mật nội dung truyền | Khuyến nghị |
| --- | --- | --- | --- |
| SNMPv1 | Community string | Không mã hóa | Loại bỏ khi có thể; chỉ duy trì tạm thời với biện pháp bù trừ được phê duyệt |
| SNMPv2c | Community string | Không mã hóa | Không phù hợp cho môi trường cần bảo mật metadata và bí mật truy cập |
| SNMPv3 `noAuthNoPriv` | Không xác thực người dùng bằng mật mã | Không mã hóa | Tránh dùng trong môi trường sản xuất |
| SNMPv3 `authNoPriv` | Xác thực và kiểm tra toàn vẹn | Không mã hóa nội dung PDU | Chỉ xem xét ngoại lệ có giải trình; không đạt mục tiêu bảo mật nội dung |
| SNMPv3 `authPriv` | Xác thực + kiểm tra toàn vẹn | Mã hóa nội dung PDU | Lựa chọn ưu tiên khi thiết bị và collector hỗ trợ thuật toán đủ mạnh |

SNMPv3 thường triển khai **User-based Security Model (USM)** và phân quyền bằng **View-based Access Control Model (VACM)**. USM xác thực và bảo vệ bản tin; VACM kiểm soát user/group được đọc hoặc thay đổi phần nào của cây OID. Một số triển khai còn có các security model và transport model khác; không nên giả định mọi thiết bị đều hỗ trợ cùng mức chức năng.

Trong USM, các thuật toán cụ thể phụ thuộc firmware và collector. Ưu tiên thuật toán xác thực hiện đại như **HMAC-SHA-2** và thuật toán mã hóa được nhà sản xuất hỗ trợ an toàn như **AES**, nhưng phải xác minh profile, độ dài khóa, hỗ trợ của cả hai phía và khuyến nghị hãng. Tránh lựa chọn thuật toán đã lỗi thời chỉ vì cấu hình mẫu cũ dùng nó. Không tự suy rằng mọi lệnh gọi `SHA` hoặc `AES` trên các nền tảng có cùng cơ chế và độ mạnh mật mã.

**SNMP engine ID** là một phần quan trọng trong cơ chế USM; việc thay engine ID, khôi phục cấu hình hoặc thay thiết bị có thể ảnh hưởng user/key localization và đồng bộ thông tin cần thiết để xử lý thông điệp. Hệ thống SNMPv3 cũng dựa vào thông tin như engine boots/time cho khả năng chống phát lại theo cơ chế giao thức. Sau thay đổi hoặc thay node, cần kiểm chứng polling/trap thực tế chứ không chỉ thấy cấu hình user xuất hiện.

### 3.2. Những loại thông tin SNMP có thể tiết lộ

- Hostname, tên và phiên bản hệ điều hành, model, serial number, uptime.
- Danh sách interface, địa chỉ IP, tốc độ, trạng thái, VLAN và đôi khi thông tin định tuyến.
- CPU, RAM, nhiệt độ, nguồn, lỗi giao diện và các thông số vận hành.
- Thông tin cấu trúc, module, quản trị và đặc thù nhà sản xuất.

Ngay cả các thông số **chỉ đọc** cũng có giá trị đối với kẻ tấn công vì phơi lộ cấu trúc và trạng thái mạng. Do đó phải hạn chế OID, collector, đường mạng và quyền truy cập tới dữ liệu giám sát; tránh công khai SNMP ra Internet hoặc mạng người dùng.

## 4. Hardening SNMP theo nhiều lớp

### 4.1. Bước 1: kiểm kê và thiết kế chính sách

Trước khi thay đổi, liệt kê thiết bị/phiên bản firmware, agent đang bật, SNMP version, community, user/group/view, source ACL, destination trap, collector phụ thuộc, tần suất polling, OID đang sử dụng và các hệ thống tự động hóa có gọi SNMP SET hay không.

**Đừng xóa community string hoặc tắt SNMPv2c ngay khi chưa xác định phụ thuộc vận hành:** có thể làm mất cảnh báo từ hệ thống giám sát. Trước tiên thiết kế quyền thay thế tương đương hoặc hẹp hơn trên SNMPv3, kiểm chứng cùng collector, rồi loại bỏ đường cũ trong thay đổi được phê duyệt.

Chính sách cơ sở nên xác định:

1. **Đối tượng được đọc:** phần MIB/OID phục vụ giám sát, không rộng hơn mức cần thiết.
2. **Người dùng SNMPv3 riêng cho collector**, không dùng chung danh tính với quản trị viên.
3. **Security level authPriv**, thuật toán và độ dài bí mật được nhà sản xuất và collector hỗ trợ.
4. **Read-only VACM view**, không cấp write/SET nếu tác vụ không thực sự yêu cầu.
5. **Source IP/VRF/VLAN cụ thể**, chỉ tới các agent được quản lý, không mở toàn bộ mạng quản trị.
6. **Quy tắc rotation, thu hồi và kiểm tra bí mật** khi thay collector, đổi người quản lý hoặc nghi ngờ lộ.
7. **Trap/inform destination được phê duyệt**, cùng cơ chế xác thực, chống mất sự kiện và quy trình test.

Ví dụ mô tả **ý định chính sách** bằng YAML, không phải cú pháp cấu hình trực tiếp của một hãng:

~~~yaml
management_policy:
  purpose: read_only_monitoring
  agent: "192.0.2.10"             # Địa chỉ minh họa
  management_vrf: "MGMT"
  collectors:
    - "192.0.2.20"
    - "192.0.2.21"
  snmp:
    allowed_version: "v3"
    security_level: "authPriv"
    authentication: "SHA-2 (nếu hai phía hỗ trợ)"
    privacy: "AES (profile theo vendor)"
    user: "monitoring_ro"
    access: "read-only"
    allowed_mib_view: "monitoring-required-only"
    allow_set: false
    trap_destinations:
      - "192.0.2.30"
  controls:
    restrict_source_addresses: true
    encrypt_and_audit_secret_storage: true
    log_authentication_failures: true
    review_change_ticket: true
~~~

Các địa chỉ trong dải `192.0.2.0/24` là **địa chỉ tài liệu**, cần thay bằng dải quản trị thật khi triển khai. Tên profile SHA-2/AES chỉ thể hiện nguyên tắc: cú pháp, thuật toán và chuẩn mã hóa phải được xác minh theo firmware và khả năng của collector.

### 4.2. Bước 2: giới hạn truy cập agent

**Bật SNMP trên interface quản trị khi thiết bị hỗ trợ**, dùng VRF/management plane riêng, chính sách firewall/ACL và control-plane protection. Chỉ cho phép đúng IP collector gọi agent; xét riêng cả IPv4 và IPv6 để tránh bỏ sót một giao diện quản trị khác. Tường lửa mạng không thay thế ACL của thiết bị vì lưu lượng nội bộ hoặc thay đổi route có thể đi qua đường khác.

Ma trận ví dụ:

| Nguồn | Đích | Dịch vụ | Kết quả mong đợi |
| --- | --- | --- | --- |
| Collector A/B | IP quản trị của router/switch | UDP/161, SNMPv3 authPriv | **Allow** cho danh tính có quyền chỉ đọc |
| Thiết bị mạng | Trap collector | UDP/162, SNMPv3 notification được bảo vệ | **Allow** tới đích đã đăng ký |
| Jump host được phép | IP quản trị thiết bị | TCP/22, TCP/443 khi dùng | **Allow** theo danh tính quản trị |
| Hệ thống automation được cấp phép | Thiết bị có NETCONF/RESTCONF | TCP/830 hoặc HTTPS theo thiết kế | **Allow** với scope tối thiểu |
| Mạng người dùng/guest/Internet | IP quản trị hoặc agent SNMP | UDP/161, TCP/22/443/830 | **Deny** |
| Collector không được đăng ký | IP quản trị thiết bị | UDP/161 | **Deny** và ghi nhận khi phù hợp |

Luồng trap thường đi **từ agent tới collector** (UDP/162), khác chiều polling SNMP request/response (collector tới agent UDP/161). Với **inform**, agent mong nhận xác nhận theo cơ chế giao thức; kiểm tra chiều phản hồi, NAT, firewall state và thời gian timeout thực tế. Đôi khi collector là một hệ thống tập trung dùng IP ảo hoặc HA; phải ghi cả danh tính và các IP có thể dùng sau failover.

Giới hạn tốc độ hoặc control-plane policing có thể giúp giảm ảnh hưởng của yêu cầu dồn dập, nhưng phải **điều chỉnh theo khả năng phần cứng và lưu lượng giám sát hợp lệ** để tránh mất polling/trap. Không áp một ngưỡng cố định lên tất cả thiết bị.

### 4.3. Bước 3: hạn chế OID và quyền

SNMPv3 hỗ trợ mô hình user/group/view. Cần xây một **read view** đủ cho những OID mà collector sử dụng và một **write view rỗng hoặc không được cấp** nếu chỉ giám sát. Hạn chế vùng dữ liệu nhạy cảm mà collector không cần: một collector đọc nhiệt độ interface không nhất thiết cần truy cập toàn bộ cấu hình hoặc cây OID mở rộng của nhà sản xuất.

**SNMP GET/GETNEXT/GETBULK** đọc dữ liệu, còn **SET** có thể thay đổi cấu hình hoặc trạng thái tùy MIB/agent. Hãy kiểm tra cả quyền **truy vấn** lẫn việc **thử SET không được phép** trong môi trường kiểm thử được ủy quyền. Một lệnh SET thử trên thiết bị thật có thể gây thay đổi không mong muốn; tránh kiểm thử bằng cách đặt một OID ảnh hưởng hoạt động.

VACM hoặc vendor ACL có thể áp dụng khác nhau theo SNMPv3 context, security level và MIB subtree. Với hệ thống nhiều tenant/VRF/context, cần kiểm tra user không nhìn thấy dữ liệu ngoài phạm vi của mình.

### 4.4. Bước 4: bảo vệ và xoay vòng bí mật

SNMPv3 auth/priv credentials là **bí mật vận hành**. Lưu trong secret manager hoặc kho đã kiểm soát, phân quyền service account theo từng collector, tránh xuất hiện trong file cấu hình dùng chung, commit Git, log CI hoặc tham số dòng lệnh dễ lộ qua history/process list. Không chia sẻ một user và cùng bí mật cho toàn bộ môi trường nếu có thể phân tách theo site, vùng hoặc nhóm thiết bị.

Vòng đời bí mật gồm: cấp phát an toàn → đưa vào agent/collector → kiểm chứng → định kỳ hoặc theo sự kiện thay đổi → thu hồi bí mật cũ. Rotation SNMPv3 có thể cần tạo **user mới song song** để không gián đoạn giám sát, sau đó đổi collector và loại bỏ user cũ khi đã có bằng chứng hoạt động. Quy trình phải tính tới engine ID, key localization và giới hạn cấu hình của thiết bị.

Không đưa community string v2c hoặc auth/priv passphrase thật vào ví dụ hướng dẫn, lệnh chụp màn hình hay báo cáo sự cố.

### 4.5. Bước 5: hardening trap, inform và collector

Mất trap có thể khiến SOC không nhận cảnh báo interface down, reload hoặc lỗi xác thực. Đảm bảo:

- Trap/inform gửi tới **đúng collector và vùng mạng**; không gửi tới host thử nghiệm còn tồn tại sau nghiệm thu.
- Dùng thông báo **SNMPv3 được xác thực và bảo vệ** khi thiết bị và collector hỗ trợ; với hệ thống legacy cần đánh giá rủi ro và đường truyền bù trừ.
- Giám sát tình trạng **truyền nhận, hàng đợi, lỗi phân giải tên, đồng bộ thời gian và bộ đếm thông báo**, không chỉ nhìn dashboard “xanh”.
- Phân quyền truy cập collector, giữ nhật ký, cập nhật collector và bản MIB parser; không cho mọi người dùng đọc inventory/serial hay dữ liệu topology.
- Phân biệt **trap** không có cơ chế xác nhận giao thức với **inform** có xác nhận; inform giúp phát hiện lỗi chuyển giao theo cơ chế protocol nhưng vẫn cần giám sát và không bảo đảm tuyệt đối mọi sự kiện đều đến nơi.

Đối với phát hiện và phản ứng sự cố, collector/SIEM cần nhận log lỗi SNMPv3 authentication, nguồn gửi không được phép, thay đổi cấu hình SNMP và lưu lượng polling bất thường.

## 5. Hardening SSH và giao diện terminal

**SSH v2** là lựa chọn phổ biến cho CLI quản trị. Bật SSH chỉ ở giao diện quản trị, chặn Telnet, rlogin, rsh và các giao thức terminal rõ. Với thiết bị có SSHv1 hoặc SSHv2 cấu hình thuật toán cũ, cập nhật software/firmware hoặc chính sách thuật toán theo khuyến nghị nhà sản xuất.

### 5.1. Kiểm soát kết nối và thuật toán

- Giới hạn nguồn tới **bastion/jump host, quản trị viên hoặc automation** đã được phê duyệt. Không expose SSH của router/firewall lên Internet công khai.
- Dùng **SSHv2**, ưu tiên key exchange, host key, cipher và MAC hiện đại theo khả năng firmware và chính sách tổ chức; vô hiệu thuật toán lỗi thời khi đã xác minh tương thích.
- **Kiểm chứng SSH host key** trước khi kết nối lần đầu hoặc sau thay đổi thiết bị. Khi fingerprint đổi ngoài kế hoạch, cần điều tra trước khi chấp nhận.
- Bật session timeout, giới hạn số lần xác thực, cơ chế bảo vệ login brute-force và audit lệnh/phiên nếu nền tảng hỗ trợ.
- Dùng **key-based authentication hoặc AAA tập trung** phù hợp thiết bị; mật khẩu cục bộ và tài khoản cứu hộ cần được kiểm soát riêng, không dùng chung.
- Giới hạn SCP/SFTP, port forwarding, agent forwarding hoặc tính năng tunnel theo nhu cầu và khả năng cấu hình; không giả định mọi firmware hỗ trợ đầy đủ các tùy chọn OpenSSH.

**Lưu ý:** các dòng cấu hình SSH phổ biến của Linux/OpenSSH thường **không thể áp nguyên xi** cho switch/router/NGFW. Hãy dùng cú pháp dành riêng cho model, release và cơ chế quản lý của thiết bị sau khi đọc tài liệu hãng.

### 5.2. Xác thực tập trung và quyền quản trị

Mô hình thường dùng:

~~~mermaid
flowchart TD
    Admin["Quản trị viên"] -->|"MFA và thiết bị tin cậy"| Jump["Bastion"]
    Jump -->|"SSH/HTTPS theo ACL"| Dev["Thiết bị mạng"]
    Dev -->|"TACACS+ / RADIUS theo thiết kế"| AAA["AAA Server"]
    Dev -->|"Audit logs"| SIEM["SIEM"]
    Dev -.->|"Fallback khẩn cấp có kiểm soát"| Local["Tài khoản local break-glass"]
~~~

**AAA** gồm Authentication (xác thực), Authorization (cấp quyền) và Accounting (ghi nhận hoạt động). Nơi được hỗ trợ, **TACACS+** thường cung cấp mô hình phân quyền lệnh quản trị chi tiết; **RADIUS** thường dùng cho xác thực truy cập mạng, VPN và một số chức năng quản trị. Việc hỗ trợ cụ thể phụ thuộc hãng/firmware. Không mặc định đường truyền TACACS+/RADIUS truyền thống có cùng mức bảo mật toàn bộ như TLS; tách mạng quản trị và cân nhắc phương án bảo vệ vận chuyển phù hợp (ví dụ RADIUS/TLS khi được cả hai phía hỗ trợ).

Phân vai theo trách nhiệm: **monitoring readonly**, **network operator**, **security auditor**, **change administrator**, **emergency administrator**. Tài khoản automation cần quyền thao tác cụ thể, sử dụng secret manager và có thể thu hồi riêng. Tài khoản local break-glass phải được kiểm kê, kiểm soát, giám sát và thử nghiệm định kỳ theo quy trình khẩn cấp; tránh tạo điểm phụ thuộc duy nhất vào AAA khi chính hệ thống AAA đang gặp sự cố.

MFA có thể áp dụng ở **IdP, VPN/ZTNA, bastion hoặc cổng quản trị** tùy nền tảng. Nếu CLI của thiết bị không hỗ trợ MFA trực tiếp, cần làm rõ biện pháp bảo vệ ở từng chặng thay vì khẳng định có MFA end-to-end khi thực tế chỉ kiểm soát bước vào jump host.

## 6. Hardening web UI, NETCONF, RESTCONF và automation API

### 6.1. HTTPS và giao diện web

Nếu giao diện web không cần thiết cho vận hành, **vô hiệu hóa**. Khi cần dùng, tắt HTTP rõ, chỉ bật HTTPS với TLS và cipher suite được chính sách và firmware hỗ trợ an toàn (thông thường ưu tiên TLS 1.2/1.3 khi nền tảng hỗ trợ), sử dụng chứng thư hợp lệ, hostname chính xác và quy trình gia hạn. Tránh ngoại lệ trình duyệt như bỏ qua cảnh báo chứng thư.

Đồng thời kiểm soát:

- Tài khoản mặc định và quyền rộng; triển khai RBAC/SSO/MFA khi có.
- Thời gian hết hạn phiên, đăng xuất, giới hạn login và bảo vệ khỏi lạm dụng API.
- Chức năng upload image/config, backup và debug chỉ dành cho vai trò phù hợp.
- Cập nhật bản vá lỗi web UI; kiểm tra advisory đối với endpoint quản trị.
- Session/cookie security, chống CSRF và kiểm tra server-side authorization theo khả năng thiết bị; người dùng có thể bấm nút trong UI không đồng nghĩa họ được phép gọi trực tiếp API.

Không mở web admin qua NAT public/port-forwarding tới Internet để “tiện hỗ trợ”. Dùng đường truy cập quản trị được phê duyệt, VPN/ZTNA/bastion với quyền tối thiểu.

### 6.2. NETCONF, RESTCONF và API

NETCONF thường chạy qua **SSH** (cổng chuẩn TCP/830); RESTCONF thường chạy qua **HTTPS**. Chỉ bật khi có automation/controller thực sự sử dụng. Cả hai có khả năng đọc và **thay đổi cấu hình**, nên quyền của service account phải giới hạn theo model dữ liệu, thao tác và phạm vi thiết bị nếu hỗ trợ.

Biện pháp quản trị bổ sung:

1. Tách danh tính **read-only discovery** và **configuration change**.
2. Dùng chứng thư hoặc token/SSH key được quản lý có thời hạn và quy trình rotation; không hard-code vào pipeline.
3. Bật log API request và kết quả theo cách không làm lộ token, bí mật hoặc payload nhạy cảm.
4. Hạn chế account/controller theo IP, VRF, device group; đánh giá độ tin cậy của orchestrator vì một token controller bị lộ có thể ảnh hưởng nhiều thiết bị.
5. Trước thay đổi cấu hình, thực hiện validation, lưu snapshot, review/phê duyệt và xây rollback. Với NETCONF, kiểm tra khả năng lock datastore, validate và commit/confirmed-commit nếu thiết bị hỗ trợ.
6. Giới hạn tốc độ và khả năng đồng thời để không quá tải control plane; không để vòng tự động hóa cấu hình lặp vô hạn.
7. Sau thay đổi, kiểm tra trạng thái **operational/running configuration** thật, không chỉ tin phản hồi API “accepted”.

**Một API trả HTTP 200 không bảo đảm thay đổi đã có hiệu lực trên dataplane**: có thể yêu cầu chưa được commit, đợi đồng bộ cluster hoặc cần reload. Các bước readback phải phù hợp ngữ nghĩa giao thức và hãng.

## 7. Kiến trúc mạng quản trị và nguồn tin cậy

Management plane nên được đặt trong **VRF/VLAN/VPC subnet quản trị** riêng, sử dụng các bộ lọc truy cập đến địa chỉ quản trị của thiết bị. Mức tách biệt phụ thuộc kiến trúc; VRF/VLAN đơn lẻ chỉ giúp phân tách logic, không tự đảm bảo an toàn nếu vẫn có route, shared service hoặc ACL cho phép quá rộng.

Thiết kế vùng quản trị cần:

| Thành phần | Kiểm soát đề xuất | Cần kiểm chứng |
| --- | --- | --- |
| Management interfaces | Chỉ bind dịch vụ cần thiết trên interface/VRF được phép | Interface khác, IPv6 và public IP không expose dịch vụ |
| ACL/firewall | Chỉ cho allowlist nguồn, đích, port, danh tính khi nền tảng hỗ trợ | Test dương và test âm ở mỗi tuyến |
| Bastion/jump host | MFA, phân quyền, hardening OS, cập nhật, ghi phiên nếu phù hợp | Thiết bị chỉ nhận kết nối từ nguồn đã ủy quyền |
| AAA/IdP | Có HA hoặc phương án cứu hộ; log login và phân quyền | Mất AAA không vô hiệu hóa toàn bộ phương án recovery |
| Secret manager | Khóa, SNMP user, chứng thư, token được phân quyền và xoay vòng | Không có secrets trong Git, log, file snapshot phổ thông |
| NTP | Đồng bộ thời gian đáng tin cậy; xác thực khi được hỗ trợ | Thời gian log, token và chứng thư có thể đối chiếu |
| Syslog/SIEM | Gửi sự kiện qua đường tin cậy, bảo vệ dữ liệu | Có log login, thay đổi cấu hình, thất bại xác thực |
| Out-of-band | Cô lập khỏi mạng người dùng; vật lý/logic được bảo vệ | Có thể truy cập cứu hộ khi data plane gặp lỗi |

**Control-plane policing** giúp bảo vệ CPU/control plane trước các burst và lưu lượng không hợp lệ; áp dụng cùng ACL. Cần phân biệt luồng quản trị được phép với các giao thức điều khiển thiết yếu như routing, BFD hoặc HA heartbeat để không gây gián đoạn mạng khi cấu hình chính sách.

Không lấy việc “truy cập từ LAN” làm chứng cứ tin cậy: kẻ tấn công có thể đã chiếm một máy trong LAN hoặc một tài khoản VPN. Nên xác minh **người dùng + thiết bị + tuyến quản trị + quyền thao tác** ở những lớp có thể kiểm soát.

## 8. Quy trình chuyển đổi từ giao thức yếu sang cấu hình an toàn

### 8.1. Các cổng kiểm soát triển khai

| Giai đoạn | Công việc | Điều kiện chuyển tiếp |
| --- | --- | --- |
| **G0: Inventory** | Kiểm kê agent, phiên bản, SNMP user/community, SSH/UI, collector, trap, automation, AAA | Biết luồng đang dùng, chủ sở hữu và phiên bản của mỗi thành phần |
| **G1: Chuẩn bị** | Xác minh firmware hỗ trợ, cặp thuật toán, nguồn quản trị, bí mật mới, cấu hình dự phòng | Có cấu hình, người thực hiện/phê duyệt, cửa sổ thay đổi và rollback |
| **G2: Song song** | Bật SNMPv3 authPriv read-only, giới hạn source, cấu hình collector mới; kiểm tra SSH/HTTPS | Polling và trap/inform hoạt động, lỗi thấp, log đầy đủ |
| **G3: Khóa đường cũ** | Chuyển hết collector phụ thuộc rồi tắt v1/v2c, Telnet/HTTP nếu không cần | Không mất giám sát, đường yếu bị chặn từ ngoài phạm vi |
| **G4: Xác minh** | Kiểm thử dương/âm, quyền đọc/ghi, AAA/failover, dashboard, cảnh báo | Đạt tiêu chí bảo mật và chức năng đã định |
| **G5: Duy trì** | Ghi baseline, audit, monitor drift, rotation secrets, kiểm soát ngoại lệ | Có owner, lịch review và bằng chứng kiểm tra |

Nếu thiết bị không hỗ trợ SNMPv3 authPriv/cipher an toàn, **không nên giả vờ rằng mạng nội bộ làm SNMPv2c tương đương SNMPv3**. Có thể áp dụng biện pháp bù trừ như mạng quản trị bị cô lập, allowlist hẹp, transport tunnel được thiết kế/phê duyệt, giảm OID/phạm vi, tăng giám sát và lập kế hoạch nâng cấp/thay thiết bị. Ghi nhận rủi ro còn lại và người chấp thuận.

### 8.2. Kiểm thử có kiểm soát

Không chỉ kiểm tra SNMPv3 trả dữ liệu. Phải xác nhận **chỉ những nguồn/danh tính hợp lệ mới được đọc**, và quyền có thể thực hiện đúng tác vụ. Các kiểm thử âm giúp phát hiện firewall rule hoặc user view quá rộng.

| Kiểm thử | Kỳ vọng | Nguồn chứng cứ |
| --- | --- | --- |
| Collector được phép dùng v3 authPriv lấy OID thuộc read view | Thành công | Collector log, SNMP response, device log |
| Collector hợp lệ lấy OID ngoài view được cấp | Bị từ chối theo cơ chế agent/VACM | Kết quả query, agent policy |
| Nguồn khác mạng quản trị gọi UDP/161 | Bị chặn | ACL/firewall counters, flow log |
| SNMPv1/v2c sau khi cutover | Không còn được chấp nhận | Device config + kiểm thử được ủy quyền |
| User chỉ đọc thử thao tác SET an toàn trong lab | Không có quyền thay đổi | VACM policy/test lab và audit |
| Quản trị SSH từ jump host đúng quyền | Thành công, ghi log và phiên | AAA, session log, syslog |
| SSH/HTTPS từ mạng người dùng | Bị chặn | ACL/firewall log |
| Login sai quyền hoặc token đã thu hồi | Bị từ chối và sinh cảnh báo theo chính sách | AAA/API log |
| Trap/inform được tạo qua sự kiện thử không phá hoạt động | Đến đúng collector và được phân loại | Collector/SIEM event |
| Mất AAA/collector hoặc failover theo kịch bản được duyệt | Có lộ trình cứu hộ và cảnh báo giám sát | Biên bản bài test vận hành |

**Cách kiểm chứng kỹ thuật** nên dựa vào NMS/collector có kết nối được ủy quyền, chức năng SNMP test của hãng, log của agent và công cụ đọc cấu hình. Nếu dùng `snmpget`/`snmpwalk`, tránh truyền passphrase thực qua tham số lệnh dễ lộ; ưu tiên tích hợp secret manager có cơ chế che bí mật. Hạn chế SNMP walk toàn bộ OID tree trên thiết bị chịu tải: có thể làm tăng CPU, lưu lượng quản trị và độ trễ.

Ví dụ dạng **lệnh kiểm tra quan sát** (không phụ thuộc một nhà sản xuất):

~~~text
# Tên lệnh chính xác cần tra theo NOS/firmware.
show snmp status
show snmp users
show snmp groups
show snmp views
show management access
show ssh status
show logging
show aaa status

# Đối chiếu bằng collector có xác thực, không nhập secret lên CLI:
SNMPv3 GET sysUpTime.0 từ collector A -> agent
SNMPv3 GET theo read view -> agent
SNMPv3 unauthorized OID request -> expected deny
Kiểm tra trap/inform thử trong NMS/SIEM
~~~

Đây là **pseudo-playbook**: các lệnh có thể không tồn tại trên thiết bị cụ thể. Bản kiểm thử sản xuất phải dựa trên cú pháp và tác động đã được xác minh; phép thử thay đổi dữ liệu nên thực hiện trong lab hoặc môi trường được kiểm soát.

### 8.3. Rollback mà vẫn giữ trạng thái bảo vệ

Trước thay đổi cần snapshot cấu hình, danh sách phiên đang hoạt động, secret/credential cũ đã lưu trong kho an toàn theo quy trình, trạng thái AAA và phương án OOB. **Rollback** nên ưu tiên đưa về **trạng thái chức năng an toàn đã biết**; không mặc nhiên mở lại Telnet hoặc SNMPv2c ra toàn mạng. Nếu giám sát bị đứt, có thể tạm dừng cutover, chỉnh collector, phục hồi route/ACL được phê duyệt hoặc dùng kênh OOB để cứu hộ.

Điều kiện dừng ví dụ:

- Collector chính và dự phòng không lấy được dữ liệu thiết yếu sau thay đổi.
- Trap/inform ngừng đến collector và không có nguồn cảnh báo thay thế.
- SSH/AAA hoặc OOB không truy cập được theo phương án cứu hộ.
- CPU/control plane hoặc packet loss vượt ngưỡng an toàn đã thống nhất.
- Xuất hiện truy cập quản trị trái phép hoặc thông tin xác thực bị lộ.

Ngưỡng và khoảng quan sát phải được đặt theo thiết bị, tải và mục tiêu vận hành, không dùng một con số chung cho mọi hạ tầng.

## 9. Tình huống thực hành: chuyển SNMPv2c sang SNMPv3

**Bối cảnh.** Một doanh nghiệp có 40 switch access được giám sát bằng SNMPv2c từ hai NMS collector. SNMP agent đang lắng nghe trên cả management VLAN và interface định tuyến phía người dùng. Nhóm an ninh phát hiện một số đường vào UDP/161 từ vùng user.

**Mục tiêu.** Chuyển sang SNMPv3 authPriv chỉ đọc, chỉ cho collector hợp lệ truy vấn qua management VRF, vẫn duy trì cảnh báo interface down và kiểm soát truy cập CLI.

**Bước 1 — Kiểm kê.** Thu model/firmware và khả năng hỗ trợ SNMPv3 của 40 switch, cộng community đang sử dụng, OID NMS cần, trap/inform, các site phụ thuộc và phiên bản collector. Kiểm tra liệu có hệ thống cũ nào đang dùng community đó.

**Bước 2 — Chuẩn bị lab.** Dùng thiết bị/model phù hợp để thử thuật toán hỗ trợ và read view tối thiểu. Xác định authentication/priv profile, user read-only và bản kế hoạch rotation không làm lộ secret.

**Bước 3 — Pilot ít thiết bị.** Bật SNMPv3 authPriv trên một nhóm switch thử nghiệm, giới hạn nguồn vào collector A/B, kiểm tra CPU và OID. Đọc dữ liệu trên NMS, kiểm tra trap/inform tới đích và thử truy cập từ nguồn không được cho phép.

**Bước 4 — Chuyển từng nhóm.** Đưa collector dùng v3, so biểu đồ và cảnh báo trong một cửa sổ giám sát; khi v3 ổn định, loại bỏ v2c/community trên nhóm đó. Ghi lại trạng thái thực tế và ticket cho từng switch.

**Bước 5 — Bảo vệ SSH/UI.** Chỉ mở SSH/HTTPS nếu cần, từ jump host; tắt Telnet/HTTP; kiểm tra AAA, tài khoản cứu hộ và log login. Đừng tự cắt đường quản trị duy nhất khi chưa có OOB hoặc khả năng hồi phục tương đương.

**Bước 6 — Nghiệm thu.** Đối chiếu trên toàn bộ 40 thiết bị: mức độ bao phủ, sự kiện từ cả collector, cảnh báo interface, không còn v2c/Telnet, SNMPv3 read view đúng và ACL chặn vùng người dùng. Xử lý ngoại lệ cho thiết bị legacy bằng rủi ro được ghi nhận.

Một ví dụ nhật ký nghiệm thu:

~~~text
Change ID: CHG-SNMP-EXAMPLE
Thiết bị: SW-ACCESS-17
Firmware/NOS: đã xác minh trước thay đổi
Source được phép: collector-a, collector-b trong MGMT VRF
SNMP: v3 authPriv, read-only view; v2c disabled
SSH: chỉ từ jump host; Telnet disabled
Positive test: collector đọc interface counters thành công
Negative test: user VLAN -> UDP/161 bị từ chối
Trap/inform test: sự kiện thử hiển thị trên collector
Audit: SSH login, lỗi SNMP authentication có log
Rollback: cấu hình quản trị đã kiểm chứng, có OOB
Kết luận: PASS hoặc NEEDS_FOLLOW_UP, kèm evidence ID
~~~

Nếu một NMS vẫn cần SNMPv2c cho vài OID đặc thù, cần làm rõ OID và khả năng hỗ trợ SNMPv3 trước khi xét ngoại lệ. Không mặc nhiên giữ nguyên community string trên toàn bộ 40 switch vì một thiết bị chưa chuyển được.

## 10. Giám sát liên tục và quản lý sai lệch

Hardening chỉ bền vững khi được đưa vào **baseline và kiểm soát thay đổi**. Nên có bản cấu hình chuẩn theo loại thiết bị, vai trò và firmware; đối chiếu định kỳ với trạng thái đang chạy và nguồn inventory đã xác minh.

| Dấu hiệu theo dõi | Ý nghĩa | Phản ứng gợi ý |
| --- | --- | --- |
| SNMPv2c/community tái xuất hiện | Config drift hoặc cấu hình bị khôi phục sai | Kiểm tra change ticket, owner, phiên bản và nguyên nhân |
| Authentication failures trên SNMPv3/SSH/API tăng | Sai secret, hệ thống mới chưa đăng ký hoặc truy cập trái phép | Đối chiếu nguồn, thời gian, kiểm tra credential và SOC |
| Collector bị mất polling nhiều thiết bị | Sự cố mạng quản trị, AAA/cipher mismatch hoặc collector lỗi | Kiểm tra khả năng kết nối, thay đổi gần nhất và OOB |
| Trap/inform không xuất hiện | Đường UDP/162, user profile, engine context hoặc collector gặp lỗi | Kiểm tra thông báo thử, log và chính sách chiều trả lời |
| Web/SSH admin mới được bật | Tăng bề mặt tấn công quản trị | Xác minh nhu cầu, ACL, TLS/host key, role và thời hạn ngoại lệ |
| Service account gọi NETCONF/RESTCONF ngoài lịch | Automation thay đổi hành vi hoặc lộ token | Kiểm tra pipeline, token usage, audit và scope |
| Các thiết bị có firmware quá cũ | Không hỗ trợ cipher/giao thức mới hoặc có advisory | Đánh giá nâng cấp, biện pháp bù trừ, chủ sở hữu và lộ trình |

Các chỉ số quản trị có thể gồm: **tỷ lệ thiết bị dùng SNMPv3 authPriv**, **tỷ lệ vô hiệu v1/v2c**, **tỷ lệ giao thức quản trị chỉ mở trong mgmt VRF**, **độ phủ xác thực đa yếu tố ở đường quản trị**, **tỷ lệ tài khoản được phân quyền đúng**, **số ngoại lệ quá hạn**, và **thời gian phát hiện config drift**.

Mẫu số của mỗi chỉ số phải đến từ **inventory đã xác minh**, bao gồm thiết bị ngắt kết nối, node HA, thiết bị ảo và thiết bị legacy chưa hỗ trợ. Nếu chỉ tính các thiết bị NMS đang polling thành công, dashboard có thể trông đạt 100% dù vẫn còn thiết bị bỏ quên.

## 11. Sai lầm phổ biến và cách tránh

1. **Cho phép SNMPv3 nhưng để `noAuthNoPriv`:** giao thức “v3” không tự chứng minh đủ an toàn. Xác nhận security level và thuật toán thực tế trên cả agent lẫn collector.
2. **Dùng `authNoPriv` cho dữ liệu quản trị nhạy cảm:** thông điệp được xác thực nhưng nội dung không được mã hóa. Ưu tiên `authPriv` theo chính sách.
3. **Chỉ tắt v2c trên một interface:** IPv6, loopback, VLAN khác hoặc NAT có thể vẫn expose agent. Kiểm tra mọi giao diện và đường đi.
4. **SNMPv3 user có write view rộng:** người giám sát bị cấp khả năng thay đổi cấu hình. Áp dụng VACM và quyền chỉ đọc rõ ràng.
5. **Tắt Telnet/v2c trước khi chuẩn bị đường thay thế:** có thể làm mất giám sát hoặc khóa quản trị. Cutover có pilot, OOB, test và rollback.
6. **Dùng chung secret hoặc bỏ secret trong script/Git:** một điểm lộ ảnh hưởng toàn mạng. Quản lý bí mật theo vòng đời, phân tách vai trò và xoay vòng có kiểm soát.
7. **Tin rằng VPN hoặc VLAN quản trị đủ an toàn:** thiết bị/tài khoản trong VLAN hoặc VPN vẫn có thể bị chiếm quyền. Thêm danh tính, quyền tối thiểu và audit.
8. **Lẫn lộn telemetry với cấu hình:** SNMP view, NETCONF và API có thể có tác vụ ghi. Giới hạn thao tác và xác minh kết quả thực.
9. **Chỉ kiểm thử kết nối thành công:** cần kiểm thử đường phải bị chặn, user sai quyền, phương án failover và log.
10. **Bỏ qua firmware và phiên bản collector:** một phía không hỗ trợ thuật toán có thể gây gián đoạn hoặc ép dùng cấu hình yếu. Lập ma trận tương thích và kế hoạch nâng cấp.

## 12. Checklist triển khai và tự kiểm tra

| Câu hỏi kiểm chứng | Có / Chưa / Không áp dụng |
| --- | --- |
| Đã kiểm kê toàn bộ thiết bị, agent SNMP, collector, controller và đường quản trị? | |
| Đã xác minh khả năng SNMPv3 authPriv, thuật toán và phiên bản firmware của từng nhóm? | |
| Đã vô hiệu hoặc ghi ngoại lệ có thời hạn cho SNMPv1/v2c, Telnet và HTTP? | |
| Đã đặt user/group/view chỉ đọc; quyền SET không được cấp khi không cần? | |
| Đã giới hạn SNMP/SSH/HTTPS/API tới đúng IP, VRF/VLAN, danh tính và vai trò? | |
| Đã bảo vệ SNMP credentials, SSH keys, API tokens và chứng thư, có kế hoạch rotation? | |
| Đã có AAA/MFA theo đường quản trị, OOB cứu hộ và audit? | |
| Đã bảo vệ collector/trap, syslog, NTP và xác minh notification hoạt động? | |
| Đã kiểm thử dương, kiểm thử âm, tình huống mất AAA/NMS và rollback? | |
| Đã lưu chứng cứ, owner, change ticket, baseline và lịch kiểm tra drift? | |

### Câu hỏi luyện tập

1. Vì sao SNMPv3 dùng `authNoPriv` vẫn chưa đáp ứng đầy đủ yêu cầu bảo vệ thông tin quản trị trên đường truyền?
2. Một thiết bị chỉ cho SNMPv3 GET từ collector nhưng vẫn cấp write view. Điều gì cần thay đổi và vì sao?
3. Trong môi trường có hai NMS collector, cần xác minh gì trước khi vô hiệu SNMPv2c?
4. Vì sao một router bị giới hạn SSH vào management VLAN vẫn cần ACL nguồn, AAA và log?
5. Điểm khác nhau giữa SNMP trap và inform là gì, và ảnh hưởng tới kiểm chứng cảnh báo ra sao?
6. Khi một thiết bị legacy không hỗ trợ SNMPv3 authPriv phù hợp, nên tổ chức biện pháp bù trừ và quản lý ngoại lệ thế nào?
7. Vì sao HTTP 200 từ RESTCONF/API không đủ chứng minh cấu hình đã áp dụng chính xác?

**Gợi ý trả lời:** (1) `authNoPriv` có xác thực/toàn vẹn nhưng không mã hóa PDU. (2) Gỡ quyền ghi/SET và kiểm tra view trên các context; chỉ giám sát cần read-only. (3) OID, user/profile, trap/inform, dashboard, luồng từ cả collector, điều kiện rollback. (4) VLAN có thể bị truy cập qua route hoặc host bị chiếm; quyền và audit bảo vệ thêm các lớp. (5) Inform có cơ chế xác nhận, trap không có; vẫn cần kiểm tra việc đến nơi và độ đầy đủ sự kiện. (6) Cô lập mạng quản trị, giới hạn nguồn, theo dõi, chấp thuận rủi ro và lộ trình thay thế/nâng cấp. (7) Còn có thể cần commit, đồng bộ cluster hoặc readback trạng thái thực.

**Ghi nhớ:** Hardening SNMP và giao thức quản trị là tổ hợp **giao thức an toàn + quyền tối thiểu + phân đoạn mạng quản trị + bảo vệ bí mật + nhật ký + kiểm chứng liên tục**. Với SNMP, ưu tiên **SNMPv3 authPriv và read-only VACM**; với các giao diện thay đổi cấu hình, kiểm soát chặt **danh tính, thao tác, đường truy cập và vòng đời thay đổi**. Luôn kiểm chứng khả năng giám sát và phục hồi trước khi đóng một đường quản trị cũ.
