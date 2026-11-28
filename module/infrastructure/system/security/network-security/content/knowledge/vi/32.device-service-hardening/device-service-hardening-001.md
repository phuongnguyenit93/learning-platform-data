# Inventory thiết bị mạng và phiên bản firmware

## 1. Vì sao inventory là bước đầu của hardening?

Khi quản trị an toàn mạng, không thể vá lỗ hổng hoặc kiểm tra cấu hình nếu chưa biết **đang vận hành những thiết bị nào, ở đâu, do ai quản lý và đang chạy phiên bản phần mềm/firmware nào**. Một thiết bị mạng bị bỏ sót có thể tiếp tục dùng giao thức quản trị yếu, firmware đã hết hỗ trợ hoặc cấu hình không còn phù hợp với chính sách phân đoạn.

**Inventory thiết bị mạng** là danh mục tài sản có cấu trúc, được cập nhật và có nguồn chứng cứ, bao gồm thông tin nhận diện, vị trí, vai trò, chủ sở hữu, trạng thái vận hành, cấu hình phần mềm và vòng đời hỗ trợ. Trong chương **Hardening thiết bị và dịch vụ mạng**, inventory là đầu vào cho quản lý lỗ hổng, kiểm soát truy cập quản trị, chuẩn hóa cấu hình, quản lý thay đổi và xử lý sự cố.

Phạm vi bài học thuộc module **SECURITY_NETWORK_SECURITY**: thiết bị đảm nhiệm routing/switching, phân đoạn, firewall, VPN, IDS/IPS, DNS, Wi-Fi, kết nối đám mây và các mặt phẳng điều khiển liên quan. Hệ thống inventory phải giúp trả lời cả câu hỏi **bảo mật** (thiết bị nào có khả năng bị ảnh hưởng bởi advisory?) lẫn câu hỏi **vận hành** (nếu nâng cấp thiết bị này, vùng mạng hoặc dịch vụ nào có thể bị gián đoạn?).

Sau bài học, người học có thể:

- Xác định phạm vi thiết bị cần quản lý và những trường dữ liệu tối thiểu.
- Phân biệt **network OS**, firmware, bootloader, BIOS/UEFI và firmware của module/line card.
- Lập quy trình thu thập thông tin đáng tin cậy bằng nguồn thụ động và truy vấn chỉ đọc đã được phê duyệt.
- Chuẩn hóa mã định danh, làm giàu dữ liệu, hòa giải nguồn khác nhau và phát hiện thiết bị chưa được quản lý.
- Dùng inventory để đối chiếu bản tin bảo mật, vòng đời hỗ trợ và ưu tiên thay đổi có kiểm soát.
- Xây dựng cơ chế đo độ phủ, độ mới và độ chính xác để inventory luôn hữu ích sau lần kiểm kê đầu tiên.

> **Nguyên tắc:** Inventory cần có **đối tượng rõ ràng, phiên bản đang thực sự chạy, thời điểm xác minh và nguồn chứng cứ truy vết được**. Một bảng địa chỉ IP được nhập thủ công chưa đủ để coi là inventory bảo mật.

## 2. Xác định chính xác đối tượng kiểm kê

### 2.1. Những loại tài sản cần đưa vào

| Nhóm | Ví dụ | Điều cần quan tâm |
| --- | --- | --- |
| Thiết bị chuyển mạch/định tuyến | Switch access/distribution/core, router biên, thiết bị SD-WAN | Phiên bản NOS, cấu hình routing, stack/member, line card, management plane |
| Thiết bị phòng vệ | Firewall, IDS/IPS appliance, DDoS appliance, secure gateway | Phiên bản hệ điều hành và engine, signature/database nếu được quản lý riêng, HA state |
| Truy cập từ xa | VPN concentrator, ZTNA gateway | Phiên bản phần mềm, patch level, giao thức xác thực, giao diện quản trị |
| Mạng không dây | Wireless controller, access point, mesh gateway | Firmware controller/AP, hardware revision, phiên bản profile triển khai |
| Dịch vụ hạ tầng | DNS/DHCP appliance, NTP appliance, load balancer, ADC | Network OS hoặc bản phần mềm appliance, dịch vụ đang chạy, tính sẵn sàng cao |
| Quản trị và kết nối phụ trợ | Out-of-band switch, console server, BMC của thiết bị liên quan, hệ quản lý mạng | Tài khoản quản trị, phiên bản, phụ thuộc vào đường cứu hộ |
| Thiết bị mạng ảo/đám mây | Virtual router/firewall, cloud network appliance, gateway trong VPC/VNet | Image/build ID, template, patch level, phiên bản controller hoặc managed-service khi có |

Cần phân biệt **tài sản logic** (cluster, stack, dịch vụ firewall HA, VPC gateway) với **thành phần vật lý/ảo** (từng chassis, member, node VM, line card). Một firewall HA có thể hiển thị chung một tên dịch vụ, nhưng hai node chạy phiên bản khác nhau trong giai đoạn nâng cấp. Vì vậy danh mục phải hỗ trợ quan hệ **parent–child** và kiểm kê từng thành phần.

Những hệ thống do nhà cung cấp quản lý mà khách hàng **không trực tiếp biết hoặc điều khiển firmware** vẫn cần được liệt kê theo *dịch vụ, trách nhiệm, bằng chứng tuân thủ, lịch thông báo thay đổi và cam kết hỗ trợ*. Không tự đặt số firmware cho một dịch vụ được quản lý hoàn toàn.

### 2.2. Phân biệt phiên bản nào với phiên bản nào

| Khái niệm | Ý nghĩa | Cách ghi trong inventory |
| --- | --- | --- |
| **Network operating system (NOS)** | Phần mềm điều khiển routing, switching, firewall và quản trị thiết bị | Tên hệ điều hành, release, build/patch, image đang chạy |
| **Firmware** | Mã chạy gần phần cứng hoặc trong thành phần chuyên dụng | Firmware revision theo bộ phận, bản đang hoạt động và bản cài chờ |
| **Bootloader / ROM monitor** | Thành phần hỗ trợ khởi động, recovery và xác minh image | Phiên bản bootloader/ROMMON, trạng thái bảo vệ boot nếu có |
| **BIOS/UEFI / BMC** | Firmware nền tảng và bộ điều khiển quản trị ngoài băng trên thiết bị phù hợp | Revision riêng, phương thức quản trị và vòng đời vá |
| **ASIC/FPGA/CPLD/line card firmware** | Firmware gắn với dataplane hoặc module phần cứng | Module ID, slot, hardware revision, firmware revision |
| **Signature/rule database** | Tập nội dung phát hiện của IDS/IPS hoặc cơ sở dữ liệu bảo vệ | Phiên bản và thời điểm cập nhật riêng, không nhầm với firmware |
| **Boot image / standby image** | Tệp hoặc phân vùng dự phòng, có thể khác image đang chạy | Active slot, next-boot image, checksum/signature khi nguồn hỗ trợ |

Một thiết bị có thể đã **tải image mới nhưng chưa khởi động vào image đó**. Muốn đánh giá lỗ hổng cần biết **phiên bản đang chạy**; muốn lập kế hoạch thay đổi phải biết cả phiên bản đã cài chờ và khả năng rollback. Không kết luận thiết bị đã được vá chỉ vì kho cập nhật báo “download completed”.

## 3. Mô hình dữ liệu inventory

Danh mục nên có một **mã tài sản nội bộ ổn định** (ví dụ asset ID/UUID) để liên kết dữ liệu thu được từ nhiều nguồn. Địa chỉ IP quản trị, hostname và MAC có thể thay đổi hoặc bị dùng chung, nên thường là **thuộc tính**, không phải khóa duy nhất toàn hệ thống. Serial number có ích để định danh thiết bị vật lý nhưng có thể thiếu, không ổn định ở máy ảo hoặc không phân biệt các module nếu nhà sản xuất định danh khác nhau.

### 3.1. Nhóm trường khuyến nghị

| Nhóm | Trường quan trọng | Lý do cần lưu |
| --- | --- | --- |
| Định danh | `asset_id`, `device_type`, `vendor`, `model`, `serial`, `hardware_revision` | Phân biệt thiết bị, đối chiếu advisory và hỗ trợ nhà sản xuất |
| Vị trí/vai trò | Site, rack, zone/VRF/VLAN, environment, criticality, business service | Đánh giá mức độ phơi lộ và tác động khi thay đổi |
| Quản lý | Owner, technical contact, support contract, source of truth | Xác định ai chịu trách nhiệm cập nhật và xử lý |
| Kết nối quản trị | Management IP/FQDN, management interface, OOB path, controller ID | Truy vấn bảo mật và kiểm soát đường quản trị |
| Phiên bản | NOS name/release/build, running image, bootloader, firmware/module revisions | Đối chiếu chính xác với bản vá và ma trận hỗ trợ |
| Chu kỳ sống | First seen, last seen, commissioned, decommissioned, EoS/EoL/EoSS dates | Nhận diện thiết bị bỏ quên và rủi ro hết hỗ trợ |
| Chứng cứ | Source system, observed at, collection method, raw record ID, confidence | Kiểm chứng và phân xử kết quả mâu thuẫn |
| Kiểm soát | Approved baseline, exception ID, vulnerability/advisory status, last review | Nối inventory với hardening và quản trị rủi ro |

Không phải mọi trường đều áp dụng cho mọi loại thiết bị. Dùng **giá trị chưa biết/không áp dụng một cách tường minh**; không điền giả phiên bản hoặc serial chỉ để hoàn thành bảng. Nên quy định trường bắt buộc theo từng loại tài sản và phân quyền truy cập vì IP quản trị, sơ đồ phân đoạn và danh mục lỗ hổng đều là dữ liệu nhạy cảm.

### 3.2. Ví dụ một record YAML

Đây là mẫu dữ liệu **giả lập**, không đại diện thiết bị hoặc advisory của nhà sản xuất cụ thể:

~~~yaml
asset_id: NET-DC1-FW-001
asset_type: physical_firewall
vendor: Vendor-Example
model: FX-1000
serial_number: EXAMPLE-SN-001
hardware_revision: R2
site: DC-1
security_zone: perimeter
business_criticality: critical
owner_team: Network-Security
management_ip: 192.0.2.10
ha_group: FW-DC1
ha_member: node-a
software:
  os_name: Example-NOS
  running_version: "10.4.2-build7"
  running_image: "example-nos-10.4.2"
  bootloader_version: "2.1"
  standby_image_version: "10.4.3"
  components:
    - component_id: line-card-1
      firmware_version: "3.0"
observation:
  source: authenticated-read-only-collection
  observed_at: "2026-11-28T09:30:00+07:00"
  evidence_id: COLLECT-20261128-001
  confidence: verified
support:
  lifecycle_status: pending_vendor_verification
  advisory_reviewed_at: null
asset_status: active
~~~

**Chú ý:** địa chỉ `192.0.2.10` thuộc dải dành cho tài liệu; phiên bản và tên thiết bị trong mẫu là hư cấu. Tên field chỉ là gợi ý thiết kế schema. Nếu lưu inventory vào CMDB/IPAM hoặc API, nên xây dựng validation schema, định nghĩa danh sách giá trị hợp lệ và mối quan hệ giữa parent–child.

## 4. Thu thập inventory an toàn

Không nên bắt đầu bằng quét toàn bộ dải mạng với quyền cao. Trước hết phải biết phạm vi được phê duyệt, chủ sở hữu, mạng quản trị, cơ chế truy cập và đặc thù thiết bị. Thiết bị hạ tầng cũ hoặc mạng OT có thể nhạy cảm với lưu lượng truy vấn; lịch và cường độ thu thập cần được thống nhất với đơn vị vận hành.

### 4.1. Nguồn thụ động và nguồn quản lý hiện có

- **CMDB, IPAM, sơ đồ mạng, hồ sơ cấp phát và hợp đồng:** cung cấp danh mục ban đầu, vị trí, chức năng, serial và chủ sở hữu. Đây là dữ liệu quản trị, có thể đã cũ.
- **NMS/controller/SDN/cloud inventory:** cung cấp danh sách thiết bị đã đăng ký, hình ảnh topology, trạng thái và nhiều khi cả phiên bản đang chạy.
- **Syslog, NETCONF notifications, telemetry, AAA logs:** giúp biết thiết bị nào đã hoạt động hoặc thay đổi cấu hình/phiên bản.
- **LLDP/CDP hoặc bảng neighbor được thu từ thiết bị đã quản lý:** phát hiện liên kết và thành phần lân cận; thông tin do neighbor công bố cần được kiểm chứng.
- **DHCP/ARP/ND, DNS, NAC, VPN logs:** giúp phát hiện địa chỉ hoặc máy mới; không thể chỉ dựa vào những nguồn này để xác định model và firmware.
- **Biên bản nghiệm thu, bản sao cấu hình và danh sách bảo trì:** làm dữ liệu tham chiếu, không thay thế kiểm tra phiên bản đang chạy.

Một asset xuất hiện trong log nhưng chưa có trong CMDB là **ứng viên cần kiểm tra**. Không tự động nhận đó là thiết bị mạng hợp lệ; có thể là thiết bị không được quản lý, hệ thống ảo, IP dịch chuyển, địa chỉ bị tái sử dụng hoặc log giả mạo.

### 4.2. Thu thập có xác thực và quyền tối thiểu

| Giao diện | Phù hợp để thu | Yêu cầu an toàn |
| --- | --- | --- |
| **SNMPv3** | sysName, sysDescr, sysObjectID, một số trường ENTITY-MIB | Ưu tiên `authPriv`, user chỉ đọc, ACL chỉ collector, quản lý khóa bí mật |
| **SSH CLI chỉ đọc** | Thông tin hệ thống, running image, bootloader, member/slot | Tài khoản phân quyền, log truy cập, không chạy lệnh thay đổi cấu hình |
| **NETCONF/RESTCONF** | Operational state, software version, chassis/module metadata | TLS/SSH và xác thực phù hợp, phân quyền chỉ đọc, kiểm soát rate limit |
| **Vendor/controller API** | Inventory theo thiết bị, cluster/stack member, firmware và trạng thái | Dùng service account giới hạn quyền, token vòng đời ngắn và audit |
| **Cloud API** | Virtual appliance, image/build ID, resource ID, state | Quyền đọc theo resource, tách tenant/account, lưu nguồn và thời điểm |
| **Redfish / BMC API** | Firmware của thành phần quản trị/hardware khi có | Chỉ quản trị qua mạng OOB tin cậy, hạn chế scope và credential |

Một số OID SNMP thường hữu ích để bắt đầu kiểm tra các thiết bị hỗ trợ:

| Trường | OID (mã chuẩn) | Ý nghĩa/giới hạn |
| --- | --- | --- |
| sysDescr.0 | `1.3.6.1.2.1.1.1.0` | Mô tả hệ thống; có thể chứa tên release nhưng không có cấu trúc đồng nhất |
| sysObjectID.0 | `1.3.6.1.2.1.1.2.0` | Định danh loại thiết bị theo MIB; cần ánh xạ vendor/model |
| sysUpTime.0 | `1.3.6.1.2.1.1.3.0` | Uptime tác nhân quản lý; không nhất thiết phản ánh chính xác thời gian khởi động toàn thiết bị |
| sysName.0 | `1.3.6.1.2.1.1.5.0` | Tên do quản trị viên đặt, không phải khóa định danh chắc chắn |
| entPhysicalFirmwareRev | `1.3.6.1.2.1.47.1.1.1.1.8` | Firmware revision theo **index của từng thực thể** |
| entPhysicalSoftwareRev | `1.3.6.1.2.1.47.1.1.1.1.10` | Software revision của thành phần nếu agent cung cấp |
| entPhysicalSerialNum | `1.3.6.1.2.1.47.1.1.1.1.11` | Serial theo index, có thể trống hoặc khác serial chassis |
| entPhysicalModelName | `1.3.6.1.2.1.47.1.1.1.1.13` | Model của thành phần; phải liên kết với entPhysicalIndex |

Các trường ENTITY-MIB trên là **các cột của bảng**, không phải scalar có đuôi `.0` như sysDescr. Collector cần truy vấn bảng, đọc chỉ số tương ứng và liên kết phần tử chassis, module, PSU, line card theo cấu trúc mà agent xuất. Không giả định mọi thiết bị đều triển khai đủ MIB hoặc cập nhật chính xác.

Ví dụ lệnh kiểm tra **chỉ đọc** trên CLI của thiết bị, cú pháp tùy hãng:

~~~text
show version
show inventory
show system information
show boot
show chassis hardware
show modules
show high-availability status
~~~

Đây là **các ví dụ cú pháp**, không phải tập lệnh có thể chạy nguyên khối trên mọi thiết bị. Cần tra tài liệu đúng hệ điều hành và model, đánh giá trước tác động của lệnh, đặc biệt với thiết bị đang chịu tải. Dữ liệu xác thực phải được lấy từ kho bí mật và không nhúng vào script, lệnh shell lưu history hoặc tệp inventory.

### 4.3. Luồng thu thập và hòa giải nguồn

~~~mermaid
flowchart TD
    A["Phạm vi và quyền được phê duyệt"] --> B["Nguồn nền: CMDB / IPAM / controller"]
    B --> C["Nguồn bổ sung: logs, LLDP, NAC, cloud"]
    C --> D["Thu chỉ đọc qua SNMPv3 / SSH / API"]
    D --> E["Lưu raw evidence và thời điểm"]
    E --> F["Chuẩn hóa asset / module / version"]
    F --> G{"Nguồn mâu thuẫn?"}
    G -->|"Có"| H["Đánh dấu conflict và xác minh"]
    G -->|"Không"| I["Cập nhật inventory đã kiểm chứng"]
    H --> I
    I --> J["Đối chiếu baseline, advisory, lifecycle"]
    J --> K["Review, xử lý drift và tái kiểm tra"]
~~~

Không nên **đè bản ghi mới lên bản cũ** khi dữ liệu mâu thuẫn nếu chưa biết nguồn nào đáng tin hơn. Ví dụ: CMDB nói firmware 7.1, controller báo 7.2 nhưng `show version` trên node HA đang chạy 7.1. Đây có thể là image 7.2 đã tải nhưng chưa active hoặc do dữ liệu controller chưa đồng bộ. Hãy lưu cả chứng cứ, timestamp và kết luận xác minh.

## 5. Chuẩn hóa, định danh và độ tin cậy

### 5.1. Quy tắc định danh

Đề xuất dùng **asset ID nội bộ** làm khóa chính, trong khi vendor/model/serial và cloud instance ID giúp liên kết:

1. **Thiết bị vật lý:** ưu tiên asset ID gắn với serial chassis và vị trí; kiểm tra trường hợp đổi mainboard làm thay đổi serial nhưng thiết bị vẫn cùng tài sản quản lý.
2. **Stack/cluster:** biểu diễn stack/cluster như nhóm logic; giữ từng member với serial và phiên bản riêng.
3. **Thiết bị ảo:** dùng resource ID/VM UUID kèm tenant/account và vùng triển khai; IP/hostname chỉ là thuộc tính thay đổi.
4. **Line card/module:** dùng cặp asset ID cha + module identifier/slot, nhưng phải kiểm tra slot có thể thay module sau bảo trì.
5. **Managed service:** inventory theo service ID, provider, trách nhiệm quản lý, version công khai hoặc status tương đương; không gán serial không có căn cứ.

Các trường nhạy cảm như quản trị IP, serial, topology và trạng thái lỗ hổng cần được phân quyền phù hợp với nhu cầu công việc và chính sách lưu trữ.

### 5.2. Chọn nguồn ưu tiên khi có xung đột

Nguồn dữ liệu ưu tiên không luôn cố định. Với **phiên bản đang chạy**, kết quả vận hành mới thu trực tiếp qua API/CLI có xác thực và chỉ đọc thường đáng tin hơn bản khai báo CMDB cũ. Với **chủ sở hữu kinh doanh**, CMDB được phê duyệt hoặc chủ dịch vụ có thể đáng tin hơn tên hostname trên thiết bị. Với **danh tính vật lý**, serial của chassis từ inventory đã đối chiếu tem hoặc hồ sơ tiếp nhận có thể cần thiết để xử lý sai lệch.

Mỗi trường cần:

- Giá trị chuẩn hóa, giá trị gốc và **nguồn cụ thể**.
- Thời điểm quan sát, thời điểm dữ liệu được nhập và **độ mới**.
- Mức tin cậy (verified, inferred, unverified, conflict).
- Phương pháp xác minh và người/tiến trình chịu trách nhiệm.
- Cách xử lý khi dữ liệu mâu thuẫn hoặc không còn thấy thiết bị.

Không xóa thiết bị chỉ vì mất một lần poll; phân biệt **temporarily unreachable**, **decommissioned** và **unknown**. Khi nghi thiết bị không được quản lý, ưu tiên xác minh qua đội vận hành và các nguồn thụ động trước khi tác động lên mạng sản xuất.

## 6. Đối chiếu phiên bản firmware với bảo mật và vòng đời

Phiên bản inventory chỉ có giá trị khi được gắn với **model, phần cứng, tính năng đang bật và nhánh phát hành**. Một firmware “mới hơn về chuỗi ký tự” chưa chắc đã là bản sửa lỗi tương ứng hoặc được phép dùng cho model đó. Các hãng có thể sử dụng tên release train, hậu tố hotfix, patch bundle hoặc cấu trúc version không thể so sánh bằng phép sắp xếp chuỗi.

### 6.1. Đánh giá rủi ro theo advisory

Khi có bản tin bảo mật mới:

1. Xác nhận **nhà sản xuất, dòng sản phẩm, hardware revision, OS/firmware branch** của từng asset.
2. Đọc thông tin **phiên bản bị ảnh hưởng, phiên bản đã sửa, điều kiện khai thác và điều kiện tính năng/cấu hình** trong advisory chính thức.
3. So với **phiên bản đang chạy** chứ không chỉ image đã tải; kiểm tra cả node trong HA, stack và module nếu advisory tác động các thành phần này.
4. Xác định mức phơi lộ: giao diện quản trị reachable từ đâu, dịch vụ bị ảnh hưởng có bật không, có phòng vệ firewall/ACL/MFA hay biện pháp bù trừ không.
5. Kết hợp độ nghiêm trọng của lỗ hổng, khả năng khai thác, phơi lộ thực tế và độ quan trọng dịch vụ để lập thứ tự xử lý.
6. Lưu advisory ID, ngày kiểm tra, bằng chứng, quyết định cập nhật, ngoại lệ và thời hạn kiểm tra lại.

**CVE** là mã định danh lỗ hổng công khai, không phải danh sách mọi lỗ hổng có thể áp dụng cho một thiết bị. CPE hoặc dữ liệu nhận diện sản phẩm có thể hỗ trợ đối chiếu tự động, nhưng sai khớp tên sản phẩm và nhánh phát hành có thể tạo false positive/false negative. Thông tin nhà sản xuất và phạm vi advisory vẫn phải được kiểm chứng trước khi kết luận **affected/fixed/not affected**.

**EoS / EoL / EoSS** có thể được nhà sản xuất dùng với định nghĩa khác nhau: ngừng bán, ngừng bảo trì, ngừng cập nhật bảo mật hoặc kết thúc hỗ trợ. Inventory nên lưu **tên mốc vòng đời, định nghĩa hãng, ngày áp dụng, URL tài liệu gốc và ngày xác minh**, không gộp mọi mốc thành một nhãn “hết hạn”.

### 6.2. Ma trận tình trạng mẫu

Các tên hãng, model và phiên bản dưới đây **hoàn toàn giả lập**; bảng minh họa cách ghi nhận quyết định và độ chắc chắn, không phải khuyến nghị nâng cấp:

| Asset | Vai trò | Running version | Kết quả kiểm tra | Hành động |
| --- | --- | --- | --- | --- |
| NET-EDGE-01 | Router biên | R-8.4.2 | Advisory yêu cầu kiểm tra điều kiện tính năng | Đối chiếu feature và vendor advisory, cập nhật ticket |
| NET-FW-02 | Firewall HA node B | F-10.1.1 | Khác node A và baseline | Kiểm tra tương thích HA, lập kế hoạch đồng bộ theo tài liệu hãng |
| NET-WLC-01 | Wireless controller | W-6.2.0 | Phiên bản được thu trước 20 ngày | Thu lại bản đang chạy; chưa kết luận mức rủi ro |
| NET-OOB-03 | Console server | Không xác định | Không có bằng chứng phiên bản | Kiểm tra quyền thu thập, chủ sở hữu và đường quản trị |
| NET-AP-31 | Access point | A-4.0.5 | Có thông tin vendor EoSS cần xác minh | Kiểm tra ngày EoSS và kế hoạch thay thế/biện pháp bù trừ |

Một trường hợp **không xác định** phải xuất hiện trong báo cáo là **unknown/pending review**, không bị tự động phân loại “đã an toàn”. Khi có ngoại lệ vì không thể nâng cấp ngay, cần ghi biện pháp giảm thiểu tạm thời, thời hạn, người chấp thuận và kế hoạch xử lý tiếp.

### 6.3. Tại sao nâng cấp cần chuẩn bị?

Firmware/NOS mới có thể ảnh hưởng routing, VPN, firewall policy, driver, HA, tính năng xử lý gói hoặc tương thích controller–access point. Kế hoạch thay đổi cần kiểm tra compatibility matrix, release notes, đường nâng cấp được hỗ trợ, khả năng dự phòng và rollback, nguồn image xác thực (signature/hash khi hãng hỗ trợ), bản sao cấu hình và phương pháp kiểm thử sau thay đổi.

Nên tách hai trạng thái: **firmware compliance** theo baseline được phê duyệt và **security exposure** theo advisory/rủi ro hiện tại. Một phiên bản trùng baseline không đồng nghĩa luôn an toàn nếu vừa xuất hiện advisory mới; ngược lại, phiên bản khác baseline có thể là một hotfix được phê duyệt nhưng danh mục chưa kịp cập nhật.

## 7. Quy trình vận hành inventory

### 7.1. Thu thập lần đầu

1. **Xác định phạm vi:** liệt kê site, network zone, loại thiết bị, cloud tenant, môi trường production/test và phần do đối tác quản lý.
2. **Lập danh sách ban đầu:** hợp nhất CMDB, IPAM, sơ đồ, controller/cloud inventory và hồ sơ mua sắm.
3. **Xác minh quyền truy cập:** được phê duyệt, có tài khoản chỉ đọc, kênh quản trị bảo vệ và giới hạn tải/rate.
4. **Thu thập:** dùng nguồn thụ động trước, sau đó API/SSH/SNMPv3 khi thích hợp; lưu snapshot gốc và timestamp.
5. **Chuẩn hóa:** tách version của NOS, bootloader, firmware thành phần; giữ raw version string và định danh nền tảng.
6. **Hòa giải:** tìm asset chưa được quản lý, serial trùng, IP đã đổi, node HA chưa ghi nhận hoặc phiên bản xung đột.
7. **Phê duyệt baseline:** chủ thiết bị kiểm tra thông tin nhận diện, vai trò, criticality, version và nguồn chứng cứ.
8. **Thiết lập vòng lặp:** lên lịch tái thu, kiểm tra sau thay đổi và theo dõi unknown/stale/conflict.

### 7.2. Duy trì inventory sau mỗi thay đổi

Mọi hoạt động **nâng cấp, rollback, thay module, thay chassis, chuyển site, đổi cluster hoặc hủy thiết bị** phải cập nhật inventory. Có thể tích hợp change ticket với job thu thập phiên bản sau triển khai để phát hiện mismatch giữa “planned version” và “running version”. Với hệ thống dùng controller, đối chiếu cả dữ liệu controller và node thành viên sau khi thiết bị reboot.

Các chu kỳ như **thu thập hằng ngày, rà soát sai lệch hằng tuần, xác minh chủ sở hữu hằng quý** chỉ là ví dụ. Tần suất thật phụ thuộc độ quan trọng, biến động môi trường, chính sách nội bộ và khả năng collector. Hệ thống lõi/biên trọng yếu hoặc vừa có advisory có thể cần xác minh sớm hơn.

### 7.3. Các chỉ số đánh giá inventory

| KPI | Công thức / ý nghĩa | Điều phải diễn giải |
| --- | --- | --- |
| **Coverage** | Số tài sản thuộc phạm vi đã được kiểm chứng / tổng tài sản ước tính thuộc phạm vi | Mẫu số khó chính xác; phải đối chiếu nhiều nguồn để phát hiện unknown assets |
| **Firmware completeness** | Số asset có running version đã xác minh / số asset cần theo dõi version | Tách loại không áp dụng và loại chưa có quyền thu thập |
| **Freshness** | Tỷ lệ bản ghi có chứng cứ mới hơn ngưỡng theo chính sách | Ngưỡng phải khác nhau theo nhóm thiết bị |
| **Conflict rate** | Số asset có field mâu thuẫn chưa giải quyết / số asset đã rà soát | Cần điều tra nguồn, tránh tự ghi đè |
| **Unknown owner rate** | Số thiết bị chưa có người/nhóm chịu trách nhiệm / tổng asset thuộc phạm vi | Là rủi ro quản trị và phản ứng sự cố |
| **EoSS visibility** | Tỷ lệ thiết bị có tình trạng hỗ trợ đã được đối chiếu | Không nhầm “không thấy EoSS” với “đang được hỗ trợ” |
| **Post-change verification** | Số thay đổi có readback running version thành công / số thay đổi version | Kiểm tra bản thực sự chạy sau reboot/failover |

Đặt mục tiêu đo lường dựa trên năng lực và yêu cầu tổ chức, đồng thời công khai các nhóm chưa có dữ liệu. **Coverage 100% trên CMDB** vẫn có thể bỏ sót thiết bị ngoài CMDB; vì vậy cần nguồn phát hiện độc lập.

## 8. Ví dụ kiểm tra tình trạng từ file CSV

Ví dụ dưới đây sử dụng **Python 3 với thư viện chuẩn** để kiểm tra các trường bắt buộc, version chưa xác minh và thông tin quá cũ. Đây là **logic rà soát dữ liệu**, không truy cập thiết bị và không tự quyết định thiết bị có lỗ hổng.

Giả sử file CSV chứa các cột:

~~~csv
asset_id,owner,device_type,vendor,model,running_version,observed_at
NET-EDGE-01,NetOps,router,Vendor-Example,RX100,R-8.4.2,2026-11-28T09:00:00+07:00
NET-FW-02,SecOps,firewall,Vendor-Example,FX100,F-10.1.1,2026-11-27T10:00:00+07:00
NET-WLC-01,NetOps,wireless_controller,Vendor-Example,WX100,W-6.2.0,2026-11-05T11:30:00+07:00
NET-OOB-03,NetOps,console_server,Vendor-Example,CX100,,2026-11-28T08:00:00+07:00
~~~

Script minh họa:

~~~python
import csv
from datetime import datetime, timezone, timedelta

AS_OF = datetime(2026, 11, 28, tzinfo=timezone.utc)
MAX_AGE = timedelta(days=7)  # Ví dụ, thay bằng chính sách thực tế.
REQUIRED = {
    "asset_id", "owner", "device_type", "vendor",
    "model", "running_version", "observed_at"
}

def analyze_inventory(csv_path):
    seen = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing_columns = REQUIRED - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                "Thiếu cột: " + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            asset_id = (row["asset_id"] or "").strip()
            issues = []

            if not asset_id:
                issues.append("missing_asset_id")
            elif asset_id in seen:
                issues.append("duplicate_asset_id")
            else:
                seen.add(asset_id)

            if not (row["owner"] or "").strip():
                issues.append("missing_owner")
            if not (row["running_version"] or "").strip():
                issues.append("unknown_running_version")

            try:
                observed_at = datetime.fromisoformat(row["observed_at"])
                if observed_at.tzinfo is None:
                    raise ValueError("Thiếu timezone")
                observed_utc = observed_at.astimezone(timezone.utc)
                if observed_utc > AS_OF:
                    issues.append("future_timestamp_check_clock")
                elif AS_OF - observed_utc > MAX_AGE:
                    issues.append("stale_version_evidence")
            except (ValueError, TypeError):
                issues.append("invalid_observed_at")

            if issues:
                print(asset_id or "<missing>", ", ".join(issues))

analyze_inventory("network_inventory.csv")
~~~

Kết quả kỳ vọng với **ngày đánh giá cố định 28/11/2026 UTC** là `NET-WLC-01` cần cập nhật bằng chứng do quá 7 ngày, còn `NET-OOB-03` thiếu running version. Mẫu kiểm tra này **không so sánh phiên bản theo thứ tự từ điển**, bởi việc đánh giá bản vá cần ma trận vendor/model/release train, điều kiện tính năng và advisory đã được xác minh.

Trong triển khai thật, bổ sung kiểm tra loại thiết bị, ngày giờ sai, ID trùng với nhiều hệ thống, liên kết tới nguồn chứng cứ và logic xử lý ngoại lệ. Nếu muốn đối chiếu baseline, nên lấy **tập phiên bản được phê duyệt theo model và nhánh** từ kho chính sách, kèm ngày phê duyệt; chưa xác định chính sách thì kết quả phải là **pending review**.

## 9. Tình huống thực hành: firmware không đồng nhất trên firewall HA

**Bối cảnh.** CMDB ghi nhóm firewall tại trung tâm dữ liệu đang chạy phiên bản `F-10.1.2`. Dữ liệu controller có cùng số phiên bản, nhưng truy vấn chỉ đọc từ hai node cho thấy:

| Đối tượng | Thông tin đang chạy | Nguồn | Quan sát |
| --- | --- | --- | --- |
| FW-Cluster-01 | F-10.1.2 | CMDB | Bản khai báo sau kế hoạch bảo trì |
| FW-Node-A | F-10.1.2 | API quản trị node | Đang active |
| FW-Node-B | F-10.1.1 | API quản trị node | Đang standby |
| FW-Node-B | F-10.1.2 | Kho image chờ boot | Image có sẵn nhưng chưa active |

Từ tình huống này, **không được gắn toàn cluster là “đã vá” chỉ vì node A đang chạy release mới**. Node B vẫn cần được đánh giá theo phiên bản đang chạy, vai trò failover và ma trận hỗ trợ nâng cấp của hãng.

Quy trình xử lý đề xuất:

1. Ghi nhận **hai tài sản node riêng** thuộc cluster; bổ sung hai trường running image và standby/next-boot image.
2. Đối chiếu lịch sử change ticket, kết quả lần bảo trì, log reboot và tình trạng HA; đánh dấu version conflict giữa nguồn.
3. Kiểm tra advisory áp dụng cho model, branch và tính năng có liên quan; không suy ra mức độ ảnh hưởng chỉ từ chênh lệch phiên bản.
4. Trình nhóm vận hành/an ninh phương án xác minh và hoàn tất nâng cấp theo kế hoạch kiểm soát thay đổi, có kiểm tra tương thích HA và rollback.
5. Sau thay đổi, đọc lại phiên bản **đang chạy trên cả hai node**, trạng thái đồng bộ, kết nối và quy tắc firewall; cập nhật inventory với timestamp và evidence ID.

Đầu ra mong đợi là một danh mục phản ánh **trạng thái thực tế của từng node**, cùng quyết định rủi ro, người phụ trách, hạn xử lý và chứng cứ rõ ràng.

## 10. Các sai lầm thường gặp

- **Chỉ dùng bảng IP/hostname:** dễ bỏ sót thiết bị ảo, cluster member, node HA và module; cần asset ID cùng quan hệ logic–vật lý.
- **Đồng nhất firmware với network OS:** bỏ qua bootloader, line card, BMC hoặc signature engine; cần dữ liệu theo từng thành phần.
- **Tin vào bản khai báo CMDB cũ:** bản đã lên kế hoạch không nhất thiết là bản đang chạy; cần readback có timestamp.
- **Coi version lớn hơn là an toàn hơn:** không xét nhánh phát hành, feature, advisory và compatibility; phải dùng ma trận hãng.
- **Dùng SNMPv2c/community hoặc tài khoản quyền cao không cần thiết:** tăng rủi ro lộ thông tin và thay đổi ngoài ý muốn; ưu tiên kênh xác thực, mã hóa và tài khoản chỉ đọc.
- **Tự động quét dải IP không có phạm vi kiểm soát:** có thể ảnh hưởng mạng nhạy cảm và gây nhiễu giám sát; phối hợp người phụ trách và đánh giá tải trước.
- **Xóa thiết bị sau một lần timeout:** khiến tài sản không thấy tạm thời biến mất khỏi báo cáo; phân biệt unreachable, retired và unknown.
- **Không lưu provenance:** khó chứng minh thông tin nào đã được dùng để quyết định thay đổi; cần giữ timestamp, source ID, raw evidence và người phê duyệt.
- **Không kiểm tra sau nâng cấp hoặc failover:** inventory tưởng đã cập nhật trong khi node thực tế vẫn chạy bản cũ; luôn xác minh trạng thái sau thay đổi.

## 11. Checklist để tự đánh giá

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Phạm vi | Đã bao gồm router, switch, firewall, VPN, AP/controller, dịch vụ mạng, OOB và thiết bị ảo/cloud chưa? |
| Định danh | Có asset ID ổn định, owner, vị trí, vai trò, zone và serial/resource ID phù hợp không? |
| Phiên bản | Đã tách NOS, bootloader, firmware thành phần, running và next-boot image chưa? |
| Chứng cứ | Có nguồn cụ thể, thời điểm quan sát, record gốc và trạng thái xác minh không? |
| An toàn thu thập | Có phạm vi, quyền chỉ đọc, xác thực an toàn, rate limit và nhật ký truy cập không? |
| Hòa giải | Có xử lý khác biệt giữa CMDB, controller và thiết bị thật không? |
| Lỗ hổng | Có đối chiếu advisory theo model/feature/branch và trạng thái hỗ trợ của vendor không? |
| Thay đổi | Sau nâng cấp/rollback/failover có readback và cập nhật bản ghi không? |
| Độ phủ | Có cơ chế tìm thiết bị chưa quản lý và đo freshness/unknown/conflict không? |
| Bàn giao | Có người xử lý, SLA/priority, ngoại lệ và kỳ đánh giá lại không? |

## 12. Câu hỏi tự kiểm tra

1. Vì sao địa chỉ IP quản trị hoặc hostname không nên là khóa duy nhất để định danh thiết bị mạng?
2. Một firewall đã có image mới trên ổ đĩa nhưng đang chạy phiên bản cũ. Khi đối chiếu advisory cần dùng phiên bản nào?
3. SNMPv3 có thể cung cấp những loại thông tin inventory nào? Vì sao không nên chỉ dựa trên `sysDescr`?
4. Khi controller và CLI báo hai phiên bản khác nhau, nên cập nhật inventory theo nguyên tắc nào?
5. Một bản vá được đánh dấu “fixed” trên một nhánh NOS. Ta cần xác minh những thông tin gì trước khi khuyến nghị áp dụng cho mọi thiết bị cùng hãng?
6. Vì sao việc inventory đạt độ phủ 100% theo danh sách CMDB vẫn có thể bỏ sót tài sản?
7. Nếu một node HA chưa khởi động vào image mới, inventory phải thể hiện trạng thái và mức độ chắc chắn thế nào?

**Gợi ý trả lời:** (1) Vì IP, hostname có thể thay đổi, dùng lại hoặc đại diện nhiều thành phần; sử dụng asset ID và identifier phù hợp. (2) Dùng **running version**, đồng thời lưu image chờ và kế hoạch chuyển đổi. (3) Có thể có model, serial, mô tả, revision theo module; nhiều MIB/agent không đầy đủ và sysDescr thiếu cấu trúc. (4) Lưu provenance của cả hai, xác minh active image, thời gian và ngữ cảnh trước khi phân xử. (5) Kiểm tra model, hardware rev, release train, feature, điều kiện ảnh hưởng và compatibility matrix. (6) CMDB có thể thiếu thiết bị ngoài quy trình hoặc chưa đăng ký; cần đối chiếu nguồn độc lập. (7) Ghi rõ running version từng node, next-boot image, nguồn, thời điểm và trạng thái review.

**Ghi nhớ:** Inventory phục vụ hardening là một **nguồn dữ liệu có thể kiểm chứng và duy trì liên tục**, không phải danh sách thiết bị tạo một lần. Mỗi thiết bị, cluster và module cần được nhận diện chính xác; phiên bản phải phân biệt *đang chạy* với *đã cài hoặc dự kiến*; mọi quyết định vá lỗi, thay thế và giảm thiểu rủi ro phải dựa trên nguồn chứng cứ, tính tương thích và phạm vi ảnh hưởng thực tế.
