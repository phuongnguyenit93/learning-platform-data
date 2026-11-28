# Mô phỏng lateral movement trong red team

**Chương:** Red team và mô phỏng tấn công mạng  
**Chủ đề:** Mô phỏng lateral movement (di chuyển ngang)  
**Phạm vi:** Bảo mật mạng trong môi trường doanh nghiệp, bao gồm phân đoạn mạng, kiểm soát truy cập, xác thực kết nối, giám sát lưu lượng và khả năng phát hiện hành vi xâm nhập.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích lateral movement khác gì với truy cập ban đầu, leo thang đặc quyền, pivoting và truy cập dữ liệu.
2. Mô hình hóa đường di chuyển giữa các máy, vùng mạng và danh tính dựa trên quyền truy cập thực tế.
3. Thiết kế một bài diễn tập có phạm vi được phê duyệt, mục tiêu đo được và điều kiện dừng rõ ràng.
4. Thực hiện phép kiểm chứng kết nối và phiên đăng nhập **vô hại trong lab**, đồng thời thu thập bằng chứng từ endpoint, hệ thống danh tính và mạng.
5. Đánh giá hiệu quả của segmentation, firewall, VPN/đường quản trị, EDR, SIEM và biện pháp kiểm soát quyền.
6. Phân tích một chuỗi sự kiện để phân biệt thao tác quản trị hợp lệ với dấu hiệu di chuyển ngang bất thường, rồi đề xuất cải tiến phòng vệ.

> **Nguyên tắc phạm vi:** Các ví dụ thao tác chỉ dành cho máy và tài khoản thử nghiệm được cấp phép trong mạng lab cô lập. Bài học tập trung vào mô phỏng có kiểm soát, quan sát và phòng vệ; không yêu cầu trích xuất mật khẩu, chiếm phiên, phát tán công cụ hoặc thực hiện lệnh gây ảnh hưởng dịch vụ.

## 2. Lateral movement là gì?

**Lateral movement** là hành vi chuyển từ một hệ thống hoặc phiên truy cập đã có sang một hệ thống khác trong cùng môi trường, nhằm tiếp cận tài nguyên, quyền hoặc vị trí mạng mới. Điểm cốt lõi là **một ranh giới tin cậy khác được vượt qua**: từ máy trạm sang máy chủ, từ máy quản trị sang ứng dụng, hoặc từ danh tính ở một vùng sang dịch vụ ở vùng khác.

Ví dụ: một tài khoản được sử dụng trên máy trạm có thể đăng nhập từ xa vào máy chủ ứng dụng vì chính sách cấp quyền quá rộng. Kẻ tấn công có thể lợi dụng đường truy cập đó để tiếp tục tiến sâu vào hệ thống. Trong bài diễn tập, red team sử dụng tài khoản lab và hành động đọc thông tin vô hại để kiểm tra xem đường truy cập này có thật, có bị ngăn chặn và có được phát hiện hay không.

| Khái niệm | Ý nghĩa | Quan hệ với lateral movement |
|---|---|---|
| Initial access (truy cập ban đầu) | Có được chỗ đứng đầu tiên trong môi trường | Thường là trạng thái khởi đầu của kịch bản |
| Discovery (khám phá) | Nhận biết máy, dịch vụ, tài khoản, quan hệ tin cậy | Cung cấp dữ liệu để lựa chọn đường đi |
| Privilege escalation (leo thang quyền) | Tăng mức quyền trên một máy hoặc trong một hệ thống danh tính | Có thể tạo điều kiện cho di chuyển ngang nhưng không phải điều kiện bắt buộc |
| Lateral movement | Chuyển khả năng truy cập từ một điểm sang điểm khác | Trọng tâm của bài học |
| Pivoting (chuyển tiếp qua điểm trung gian) | Dùng máy trung gian để đưa lưu lượng hoặc phiên đến mạng khác | Là một cách tạo đường đi; chưa tự chứng minh đã đăng nhập hay thực thi trên đích |
| Collection / exfiltration | Tập hợp hoặc đưa dữ liệu ra khỏi phạm vi kiểm soát | Có thể xảy ra sau đó; không nằm trong bài diễn tập này |

Không nên đánh đồng **kết nối TCP thành công** với **đăng nhập thành công** hoặc **thực thi lệnh thành công**. Cổng đang mở chỉ xác nhận khả năng tới dịch vụ ở thời điểm kiểm tra. Để kết luận đã có một bước lateral movement, cần bằng chứng về phiên xác thực/phiên điều khiển ở **máy đích**, gắn với danh tính, nguồn kết nối và thời gian cụ thể.

### Các bề mặt thường liên quan

- **Windows:** Remote Desktop (RDP), SMB và Windows Admin Shares, WinRM/PowerShell Remoting, DCOM/WMI và các dịch vụ quản trị từ xa.
- **Linux/Unix:** SSH, cơ chế đăng nhập từ xa và quyền tài khoản trên nhiều máy.
- **Danh tính:** tài khoản miền, tài khoản cục bộ dùng chung, tài khoản dịch vụ, khóa/chứng chỉ và vé xác thực; việc sử dụng thông tin xác thực hợp lệ có thể vẫn là hành vi bất thường.
- **Hybrid/cloud:** vai trò được phép giả định (role assumption), tài khoản đồng bộ, máy quản trị đám mây, quyền truy cập chéo tài khoản và các hệ thống điều khiển tập trung.
- **Mạng:** kết nối đi qua VLAN/subnet, firewall, VPN, jump host và các vùng bảo mật với chính sách khác nhau.

## 3. Mô hình hóa đường di chuyển như một đồ thị tin cậy

Một đường đi khả thi không chỉ cần có tuyến mạng. Ta có thể mô tả một **cạnh truy cập** bằng bộ:

`(nguồn, đích, danh tính, dịch vụ, quyền, điều kiện, bằng chứng)`

Trong đó:

- **Nguồn/đích:** máy hoặc workload trước và sau bước chuyển.
- **Danh tính:** tài khoản hay phiên chứng thực được dùng tại bước đó.
- **Dịch vụ:** RDP, SSH, WinRM, SMB hoặc API quản trị.
- **Quyền:** cho phép đăng nhập, đọc chia sẻ hay thực thi từ xa ở mức nào.
- **Điều kiện:** ACL, nhóm quyền, chính sách thiết bị, thời gian, MFA, trạng thái VPN, jump host.
- **Bằng chứng:** sự kiện xác thực, phiên truy cập, kết nối mạng và dấu vết tiến trình.

Một cạnh được xem là **đã chứng minh** khi cả đường mạng, điều kiện xác thực và hành động mục tiêu đều được xác minh phù hợp với phạm vi bài diễn tập. Một sơ đồ có mũi tên dự đoán chưa phải là kết quả kiểm thử.

Ví dụ kiến trúc lab:

~~~mermaid
flowchart LR
    WS["WS-01<br/>Vùng máy trạm"]
    JUMP["JUMP-01<br/>Vùng quản trị"]
    APP["APP-01<br/>Vùng ứng dụng"]
    DC["DC-01<br/>Vùng danh tính"]

    WS -->|"RDP: đường được phê duyệt"| JUMP
    JUMP -->|"WinRM HTTPS: đường được phê duyệt"| APP
    WS -.->|"Kết nối trực tiếp: phải chặn"| APP
    APP -.->|"Ngoài phạm vi thử nghiệm"| DC
~~~

Trong sơ đồ, **đường liền** là các bước diễn tập với danh tính thử nghiệm; **đường nét đứt** chỉ các ranh giới cần xác nhận chính sách hoặc không được phép đi tiếp. Khi tổ chức có nhiều VLAN, mục đích của segmentation là giảm số cạnh truy cập không cần thiết, không chỉ làm tăng số lượng subnet.

### Ma trận giả thuyết kiểm thử

| Từ | Đến | Dịch vụ | Kỳ vọng chính sách | Điều cần quan sát |
|---|---|---|---|---|
| WS-01 | JUMP-01 | RDP/TCP 3389 | Cho phép tài khoản lab theo điều kiện đã duyệt | Phiên RDP, nguồn, đích, thời gian, danh tính |
| JUMP-01 | APP-01 | WinRM HTTPS/TCP 5986 | Chỉ cho phép từ vùng quản trị và nhóm phù hợp | Xác thực, phiên từ xa, tiến trình vô hại |
| WS-01 | APP-01 | WinRM HTTPS/TCP 5986 | Chặn truy cập trực tiếp | Bản ghi firewall deny, không xuất hiện phiên thành công |
| APP-01 | DC-01 | Dịch vụ quản trị từ xa | Không thực hiện trong bài này | Không có hành động hay truy cập thử tới DC-01 |

**Lưu ý về kiểm soát:** kết quả mong đợi tùy chính sách đã thống nhất với chủ hệ thống. Một luồng “được phép” trong bảng chỉ đúng cho môi trường lab này; nó không mặc nhiên là cấu hình nên dùng trong sản xuất.

## 4. Kỹ thuật và điểm quan sát theo MITRE ATT&CK

ATT&CK cung cấp ngôn ngữ chung để mô tả hành vi. Bảng dưới là **ánh xạ tham khảo**, không phải danh sách kỹ thuật cần thực hiện toàn bộ trong một bài diễn tập.

| Kỹ thuật | Biểu hiện tổng quát | Dấu hiệu phòng vệ cần kiểm tra |
|---|---|---|
| `T1021 — Remote Services` | Dùng dịch vụ điều khiển/đăng nhập từ xa để truy cập máy khác; các nhánh bao gồm RDP, SMB/Windows Admin Shares, SSH, WinRM | Đăng nhập qua dịch vụ từ xa, máy nguồn lạ, thay đổi vùng mạng |
| `T1078 — Valid Accounts` | Sử dụng tài khoản hợp lệ, có thể là tài khoản miền, cục bộ hoặc cloud | Đăng nhập thành công nhưng lệch vai trò, giờ làm việc, thiết bị hoặc vị trí |
| `T1550 — Use Alternate Authentication Material` | Dùng vật liệu xác thực thay thế, ví dụ hash/vé xác thực | Tương quan xác thực và phiên bất thường; **chỉ mô phỏng bằng sự kiện tổng hợp nếu cần kiểm thử phát hiện** |
| `T1570 — Lateral Tool Transfer` | Chuyển công cụ/tệp giữa các máy trong môi trường | Ghi tệp/đọc chia sẻ và hoạt động mạng không thuộc luồng quản trị chuẩn; bài lab **không chuyển payload** |
| `T1047 — Windows Management Instrumentation` | Dùng WMI cho tác vụ quản trị có thể liên quan đến thực thi từ xa | Tiến trình cha-con và kết nối quản trị bất thường trên máy đích |

Một lần đăng nhập RDP hợp lệ có thể khớp hành vi `T1021` mà vẫn hoàn toàn đúng chính sách. Phân tích cần ghép **ngữ cảnh danh tính + nguồn/đích + loại tài nguyên + tính bất thường + hoạt động sau đăng nhập**, thay vì chỉ dựa vào tên giao thức.

## 5. Chuẩn bị một bài diễn tập có thể lặp lại

### 5.1. Xác định mục tiêu, phạm vi và quy tắc thực hiện

Một bài red team/purple team hữu ích bắt đầu bằng câu hỏi kiểm chứng, ví dụ:

> “Với một phiên lab trên WS-01 và tài khoản thử nghiệm `LAB\rt.operator`, có thể đi qua JUMP-01 đến APP-01 theo đường quản trị đã phê duyệt không? Blue team có quan sát được đủ hai bước và chặn được đường đi tắt từ WS-01 không?”

Biên bản diễn tập nên có:

| Mục | Nội dung tối thiểu |
|---|---|
| Tài sản cho phép | WS-01, JUMP-01, APP-01 cùng IP/hostname chính xác trong lab |
| Tài sản loại trừ | DC-01, hệ thống sản xuất, dữ liệu thật, mạng ngoài danh sách |
| Danh tính | Một tài khoản thử nghiệm, chỉ có quyền cần cho bài; không dùng mật khẩu thật |
| Thời gian | Khung diễn tập, giờ chuẩn UTC và người liên hệ khi cần dừng |
| Hành động cho phép | Kiểm tra cổng, đăng nhập thử trên máy cho phép, chạy `hostname` / `whoami` |
| Hành động không cho phép | Lấy thông tin xác thực, dò quét diện rộng, khai thác lỗ hổng, vô hiệu hóa EDR, cài persistence, chuyển dữ liệu |
| Dừng khẩn cấp | Có cảnh báo ảnh hưởng dịch vụ, đụng máy ngoài scope, quyền bất thường hoặc người điều phối yêu cầu dừng |
| Khôi phục | Đăng xuất, đóng phiên, xóa tài khoản/thay đổi thử nghiệm theo kế hoạch, khôi phục snapshot nếu cần |

Chọn sẵn **tiêu chí thành công**: xác minh hai bước truy cập hợp lệ, đường đi tắt bị chặn, blue team thu được log và giải thích được chuỗi sự kiện. Nếu sản phẩm đang chạy production, nên chọn hình thức replay log hoặc sử dụng bản sao cô lập.

### 5.2. Thiết lập lab và đồng bộ thời gian

Ví dụ địa chỉ riêng dành cho bài tập (có thể đổi theo môi trường):

| Máy | Vai trò | Vùng | Địa chỉ ví dụ |
|---|---|---|---|
| WS-01 | Máy trạm bắt đầu | user | `10.77.10.11` |
| JUMP-01 | Điểm truy cập quản trị | management | `10.77.20.11` |
| APP-01 | Máy chủ đích | application | `10.77.30.11` |
| DC-01 | Dịch vụ danh tính mô phỏng | identity | `10.77.90.11`, ngoài phạm vi thao tác |

Các máy có thể dùng DNS nội bộ trong lab. Dùng đồng hồ đồng bộ NTP để ghép log; lưu rõ múi giờ và sai số đồng hồ. Bật trước những nguồn log có thể cần: Windows Security Audit, WinRM/PowerShell Operational, EDR/Sysmon nếu đã triển khai, firewall giữa các vùng, DNS nội bộ và hệ thống danh tính. Kiểm tra dung lượng lưu log và chính sách ghi nhận sự kiện.

Nên tạo bản ghi `exercise_id = RT-005` trong **nhật ký người điều phối**. Đây là nhãn để đối chiếu thời điểm, **không phải field mặc định của Windows Event Log**.

## 6. Quy trình mô phỏng có kiểm soát

### Bước 1 — Chốt trạng thái ban đầu

Trên WS-01, ghi thời điểm, tài khoản đang dùng, địa chỉ máy, danh sách máy được phép và ảnh chụp cấu hình kiểm soát. Blue team đo nền: ở trạng thái bình thường máy trạm có được quản trị APP-01 trực tiếp không, những người nào thường vào JUMP-01, và luồng WinRM đến APP-01 thường đến từ đâu?

**Bằng chứng cần giữ:** bảng ACL/luật firewall, quan hệ nhóm quyền, baseline đăng nhập, trạng thái cấu hình logging. Không nên suy ra “an toàn” chỉ vì hiện chưa có cảnh báo.

### Bước 2 — Kiểm tra đường mạng đúng scope

Đo khả năng tiếp cận dịch vụ từ từng nguồn đã duyệt, sử dụng PowerShell trên Windows:

~~~powershell
# Chạy tại WS-01: kiểm tra đường quản trị được phép
Test-NetConnection -ComputerName JUMP-01 -Port 3389

# Chạy tại WS-01: kiểm tra đường đi tắt được kỳ vọng bị chặn
Test-NetConnection -ComputerName APP-01 -Port 5986
~~~

Ở đường đầu, `TcpTestSucceeded: True` chỉ cho biết TCP 3389 có thể kết nối, **chưa xác nhận đăng nhập RDP**. Ở đường thứ hai, `False` phù hợp với chính sách chặn nhưng cũng có thể do DNS, host tắt hoặc service không lắng nghe. Để kết luận firewall hoạt động, đối chiếu thêm rule và log deny. Không quét những cổng/địa chỉ không có trong ma trận.

### Bước 3 — Mô phỏng bước WS-01 → JUMP-01

Người điều phối dùng **giao diện RDP thông thường**, đăng nhập JUMP-01 bằng tài khoản lab được ủy quyền, không chia sẻ hoặc ghi lại mật khẩu trong tài liệu. Trên JUMP-01, chạy hai lệnh không thay đổi trạng thái:

~~~powershell
hostname
whoami
~~~

Ghi chính xác thời điểm bắt đầu/kết thúc, máy nguồn, tài khoản và kết quả hiển thị. Blue team truy tìm sự kiện đăng nhập thành công trên JUMP-01, IP/hostname nguồn WS-01 và thông tin phiên. Nếu công cụ ghi nhật ký không thu được nguồn kết nối, đánh dấu đó là **khoảng trống quan sát**, không tự điền giá trị phỏng đoán.

### Bước 4 — Mô phỏng bước JUMP-01 → APP-01

Chỉ trên JUMP-01, sau khi người điều phối đã xác nhận APP-01 và tài khoản thử nghiệm được cấp quyền WinRM HTTPS:

~~~powershell
# Kiểm tra đường mạng từ jump host đến đích
Test-NetConnection -ComputerName APP-01 -Port 5986

# Lệnh đọc thông tin vô hại trên máy đích của lab
Invoke-Command -ComputerName APP-01 -UseSSL -Authentication Kerberos -ScriptBlock {
    hostname
    whoami
}
~~~

Ví dụ giả định các máy đã cấu hình WinRM HTTPS, chứng chỉ được tin cậy và Kerberos hoạt động; **không tự bật WinRM, nới firewall hoặc cấp thêm quyền** chỉ để lệnh chạy được. Nếu điều kiện chưa có, ghi `NOT_TESTED` kèm lý do và chuyển sang phân tích sự kiện mô phỏng; không đổi giao thức hoặc thử phương thức xác thực khác ngoài kịch bản.

Kết quả `hostname` và `whoami` trả về từ APP-01, khi đi kèm bằng chứng xác thực và phiên, cho phép xác nhận một bước remote execution theo quyền lab. Ghi lại lệnh, kết quả, dấu thời gian, mã lỗi nếu có và người thực hiện. Không dùng tác vụ ghi file, tạo user, thao tác registry hay thu thập dữ liệu thật.

### Bước 5 — Kiểm tra phát hiện và dừng

Blue team tìm chuỗi `WS-01 → JUMP-01 → APP-01` bằng thông tin tài khoản và cửa sổ thời gian thống nhất, sau đó kiểm chứng nguồn bằng log gốc. Đối chiếu:

- Sự kiện xác thực vào JUMP-01 có thật không, và có phân biệt được RDP với SMB/WinRM không?
- Phiên trên APP-01 có nguồn JUMP-01 và khớp hành động `hostname` / `whoami` không?
- Log firewall có ghi rõ luồng WS-01 → APP-01 bị từ chối không?
- EDR/SIEM phát cảnh báo nào, mất bao lâu, có đủ ngữ cảnh cho người trực xử lý không?
- Có dấu hiệu vượt phạm vi hay ảnh hưởng hoạt động không? Nếu có, dừng và phối hợp xử lý.

Cuối bài, đăng xuất/đóng các phiên, loại bỏ cấu hình tạm theo danh sách phê duyệt, lưu chứng cứ kiểm thử vào kho có quyền truy cập hạn chế.

## 7. Thu thập telemetry và tương quan sự kiện

| Vị trí | Tín hiệu tiêu biểu | Giới hạn khi diễn giải |
|---|---|---|
| Windows Security tại máy đích | Event ID `4624` (logon thành công), `4625` (thất bại); Logon Type `10` thường gặp với RDP, Type `3` với truy cập mạng | Loại đăng nhập và trường nguồn phụ thuộc phương thức, hệ điều hành, cấu hình |
| Windows Security tại máy nguồn | `4648` khi có đăng nhập dùng thông tin xác thực được chỉ định rõ; `4688` nếu bật audit tạo tiến trình | Không phải phiên truy cập nào cũng sinh 4648; command line cần chính sách ghi nhận riêng |
| Domain Controller | `4768`/`4769` liên quan yêu cầu vé Kerberos khi được audit | Có thể không xuất hiện ở mọi lần kết nối do cache hoặc phương thức xác thực |
| Dịch vụ chia sẻ file | `5140`/`5145` nếu bật audit truy cập share chi tiết | Một kết nối SMB không chứng minh có thực thi từ xa |
| PowerShell/WinRM | Operational logs; `4103`/`4104` nếu bật module/script block logging | Không có log script block không đồng nghĩa không có thực thi |
| Endpoint/EDR | Tạo tiến trình, quan hệ cha-con, đăng nhập và kết nối mạng; Sysmon `1`/`3` nếu cấu hình thu thập | Tùy agent, cấu hình và khả năng lưu sự kiện |
| Network/firewall/NDR | Luồng source/destination/port, allow/deny, bắt tay mạng, lưu lượng bất thường | Dữ liệu mã hóa thường không cho biết danh tính hay nội dung lệnh |
| Linux SSH (nếu mở rộng lab) | `journalctl`, `/var/log/auth.log` hoặc `/var/log/secure` tùy distro | Vị trí log và trường chi tiết khác nhau theo hệ điều hành |
| Cloud/IdP (nếu mở rộng lab) | Sign-in audit, role-assumption, API activity, thiết bị và điều kiện truy cập | Sự kiện ở control plane không nhất thiết là phiên điều khiển trên máy chủ |

Trong Windows, **Logon ID** thường phục vụ tương quan các sự kiện trên **cùng máy** và không phải ID phiên toàn cục. Ghép chuỗi qua máy bằng tổ hợp dấu thời gian, danh tính, IP/hostname nguồn, máy đích, giao thức, dấu vết tiến trình và thông tin phiên nếu có. Chú ý NAT, tài khoản chia sẻ và tên máy có thể tái sử dụng khiến việc quy kết kém chắc chắn.

### Ví dụ log đã chuẩn hóa (dữ liệu giả)

~~~json
[
  {
    "time_utc": "2026-11-28T03:10:00Z",
    "source_host": "WS-01",
    "destination_host": "JUMP-01",
    "identity": "LAB\\rt.operator",
    "protocol": "RDP",
    "result": "success",
    "evidence": ["Windows 4624/type 10", "RDP session audit"]
  },
  {
    "time_utc": "2026-11-28T03:15:00Z",
    "source_host": "JUMP-01",
    "destination_host": "APP-01",
    "identity": "LAB\\rt.operator",
    "protocol": "WinRM",
    "result": "success",
    "evidence": ["Windows 4624/type 3", "WinRM operational", "EDR process telemetry"]
  }
]
~~~

Đây là sự kiện **minh họa sau chuẩn hóa**, không phải cấu trúc log gốc của Windows. Khi đọc, phân tích viên có thể nêu giả thuyết hai bước cùng một chiến dịch vì đích trước đó trở thành nguồn tiếp theo và danh tính/thời gian phù hợp. Để xác nhận, cần mở các bản ghi gốc, kiểm tra trạng thái phiên và lịch công việc hợp lệ.

### Ý tưởng truy vấn phát hiện

Đoạn KQL sau là **mẫu logic** cho bảng `AuthEvents` đã được SIEM chuẩn hóa; tên bảng và field phải ánh xạ theo schema thực tế trước khi chạy:

~~~kusto
AuthEvents
| where Timestamp > ago(24h)
| where Result == "Success"
| where Protocol in ("RDP", "WinRM", "SSH", "SMB")
| where SourceZone == "user" and DestinationZone == "server"
| where ApprovedRoute == false
| project Timestamp, Identity, SourceHost, DestinationHost, Protocol, SourceZone, DestinationZone
~~~

Truy vấn nêu trên phát hiện đăng nhập từ **vùng máy trạm** thẳng đến **vùng máy chủ** trái chính sách. Nó **không trực tiếp phát hiện chuỗi hai bước qua jump host**. Muốn kiểm thử chuỗi, xây thêm rule tương quan hai sự kiện trong khoảng thời gian phù hợp:

1. Sự kiện A: tài khoản `u` đăng nhập thành công từ `WS-01` đến `JUMP-01`.
2. Sự kiện B: cùng `u` (hoặc danh tính tương ứng được cấp phép trong kịch bản) đăng nhập từ `JUMP-01` đến `APP-01`.
3. `0 < time(B) - time(A) <= 15 phút`, máy nguồn của B bằng máy đích của A, và đường đi nằm trong tập cần theo dõi.
4. Kết luận là **candidate chain** để điều tra; có thể kiểm tra bổ sung phiên thực tế, dấu vết tiến trình, ticket/credential context và lịch bảo trì.

Không nên tự động gắn nhãn “tấn công” cho mọi chuỗi như vậy: jump host có thể là đường quản trị chuẩn. Rule cần đối chiếu vai trò tài khoản, cửa sổ bảo trì, danh sách máy được phép, thiết bị và baseline. Với dữ liệu mạng không có identity, cần join thêm nguồn xác thực để tránh suy diễn.

## 8. Red team kiểm thử những lớp phòng vệ nào?

| Lớp phòng vệ | Câu hỏi diễn tập | Điều chỉnh khi phát hiện vấn đề |
|---|---|---|
| Network segmentation | Máy trạm có truy cập trực tiếp cổng quản trị trên server không? | Chặn east-west không cần thiết, mặc định deny giữa vùng, allow theo nguồn/đích/dịch vụ |
| Firewall/ACL | Đường đi tắt có bị chặn và có bằng chứng deny không? | Rà rule quá rộng, đặt quyền theo subnet/host tối thiểu, kiểm tra logging |
| Identity và least privilege | Tài khoản nào được phép đi từ jump host đến server? | Nhóm quyền riêng, tài khoản quản trị tách biệt, hạn chế local admin dùng chung |
| MFA/conditional access | RDP, VPN, jump host hoặc lớp truy cập đặc quyền có ràng buộc xác minh phù hợp? | Bổ sung kiểm soát dựa vào danh tính, thiết bị, vị trí truy cập, rủi ro |
| Endpoint hardening | Dịch vụ quản trị và công cụ từ xa có bị hạn chế theo vai trò? | Tắt dịch vụ không dùng; quản lý WinRM/SSH/RDP theo chính sách, EDR coverage |
| Monitoring & response | SOC có nối được các phiên trên nhiều máy thành chuỗi? | Chuẩn hóa schema, đồng bộ thời gian, bổ sung tương quan, playbook điều tra |
| DNS và quản lý tài sản | Tên máy đích có được định danh đúng, phát hiện máy lạ không? | Tăng độ tin cậy asset inventory, DNS logs, kiểm soát tên máy và tài sản |
| Cloud/hybrid | Quyền vai trò hoặc quản trị từ xa có cho phép đi giữa vùng bảo mật ngoài dự kiến? | Rà trust policy, quyền IAM, audit trail và đường vào management plane |

Việc dùng VPN hoặc jump host **không tự bảo đảm** mọi hành vi từ đó đều đáng tin. Các phiên đi ra từ điểm quản trị vẫn phải bị giới hạn theo danh tính, host đích, mục đích và thời gian, đồng thời có khả năng truy vết.

## 9. Đánh giá kết quả bằng bằng chứng

Tạo một bản ghi cho **mỗi cạnh truy cập**. Ví dụ:

| Kiểm thử | Kỳ vọng | Kết quả giả định | Bằng chứng | Đánh giá |
|---|---|---|---|---|
| WS-01 → JUMP-01/RDP | Được phép cho tài khoản lab | RDP thành công | 4624 type 10 và session audit trên JUMP-01 | PASS |
| JUMP-01 → APP-01/WinRM | Được phép cho tài khoản lab | `hostname`, `whoami` trả về từ APP-01 | 4624 type 3, WinRM và EDR trên APP-01 | PASS |
| WS-01 → APP-01/5986 | Bị chặn | Không kết nối TCP | `Test-NetConnection` + firewall deny | PASS |
| SOC nhìn thấy chuỗi hai bước | Gắn được cùng danh tính và tuyến truy cập | Chỉ phát hiện một bước | Bản ghi SIEM và truy vấn điều tra | GAP |

“PASS” ở đây đánh giá **so với kỳ vọng từng kiểm thử**, không khẳng định toàn bộ kiến trúc an toàn. “GAP” là thiếu hụt về giám sát hoặc điều kiện bảo vệ cần đưa vào kế hoạch khắc phục.

Các chỉ số hữu ích:

- **Path coverage:** số cạnh trong danh sách được kiểm chứng / tổng số cạnh có kế hoạch; tách `NOT_TESTED` khỏi `FAILED`.
- **Control effectiveness:** số kiểm thử allow/deny cho kết quả đúng kỳ vọng / số kiểm thử đã thực hiện.
- **Telemetry coverage:** tỷ lệ bước có log đủ nguồn, đích, danh tính, thời điểm, giao thức và kết quả.
- **Detection latency:** thời điểm cảnh báo đầu tiên trừ thời điểm hành vi được ghi nhận; báo rõ múi giờ và độ lệch đồng hồ.
- **Investigation quality:** SOC có tái dựng đúng chuỗi và phân biệt hoạt động quản trị với hành vi bất thường hay không.

Với một kết quả thiếu log, ghi cụ thể “không thu được 4624 trên APP-01” và điều kiện audit lúc kiểm thử. Không biến sự vắng mặt dữ liệu thành kết luận rằng sự kiện không xảy ra.

## 10. Tình huống phân tích

**Tình huống:** công ty có VLAN máy trạm, vùng quản trị và vùng ứng dụng. Firewall cấm máy trạm WinRM thẳng vào ứng dụng nhưng cho phép nhóm operator đi qua jump host. Trong bài diễn tập:

1. Một operator dùng tài khoản lab RDP từ WS-01 đến JUMP-01 lúc 10:10.
2. Lúc 10:15, cùng tài khoản thực hiện một lệnh đọc thông tin trên APP-01 qua WinRM HTTPS.
3. SIEM có alert cho đăng nhập RDP nhưng không liên kết được phiên WinRM tiếp theo.
4. Kiểm thử kết nối trực tiếp WS-01 → APP-01/5986 thất bại và firewall ghi nhận deny.

**Phân tích:** segmentation đã chặn được đường đi tắt theo chính sách, nhưng chưa có đủ tương quan giữa đăng nhập vào jump host và hoạt động quản trị tiếp theo. Khả năng nhìn thấy một sự kiện RDP riêng lẻ chưa đáp ứng mục tiêu phát hiện chuỗi lateral movement. Cần gắn session/danh tính trên jump host với hoạt động trên APP-01, bổ sung dữ liệu từ endpoint và điều chỉnh quy tắc phát hiện theo tuyến quản trị.

**Hành động khắc phục đề xuất:** đảm bảo thu audit đăng nhập trên APP-01, chuẩn hóa mapping IP/host giữa EDR và SIEM, tạo correlation rule theo chuỗi nguồn–đích–danh tính, và diễn tập lại cùng kịch bản sau khi cấu hình. Nếu một tài khoản có quyền truy cập vượt quá vai trò, cần sửa quyền thực tế trước khi tối ưu cảnh báo.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Xem một cổng mở là lateral movement thành công | Đánh giá sai khả năng truy cập | Tách kiểm thử TCP, xác thực và thực thi/phiên đích |
| Chỉ xem log ở máy bắt đầu | Mất dấu vết của bước tiếp theo | Thu log tại cả nguồn, đích, danh tính và mạng |
| Dùng một tài khoản admin chung cho mọi máy | Không phân biệt được người/phiên thực hiện | Tạo tài khoản thử nghiệm có định danh và quyền rõ |
| Vừa diễn tập vừa thay đổi ACL hoặc bật dịch vụ | Không biết kết quả phản ánh cấu hình nào | Chốt baseline; ghi mọi thay đổi và có rollback |
| Không đồng bộ thời gian | Ghép nhầm hoặc mất chuỗi sự kiện | Bật NTP, ghi UTC, đo sai số |
| Coi mọi công cụ quản trị từ xa là độc hại | Alert nhiều, bỏ sót ngữ cảnh | Ưu tiên quan hệ tin cậy, sự bất thường, quyền và hoạt động tiếp theo |
| Dừng ở “có cảnh báo” | Không đánh giá được năng lực ứng phó | Đo thời gian phát hiện, độ đầy đủ bằng chứng và quyết định của SOC |
| Thử trực tiếp trên hệ thống ngoài phạm vi | Có thể gây ảnh hưởng và không còn giá trị diễn tập có kiểm soát | Dùng allowlist, lab cô lập và điều kiện dừng |

## 12. Mẫu báo cáo sau diễn tập

Một báo cáo ngắn có thể đi theo cấu trúc:

~~~text
Exercise ID: RT-005
Objective: Mô phỏng WS-01 -> JUMP-01 -> APP-01 và kiểm tra đường đi tắt
Scope: WS-01, JUMP-01, APP-01; không thử DC-01 hoặc máy sản xuất
Identity: Tài khoản lab được cấp riêng (không ghi mật khẩu)
Window (UTC): [bắt đầu] - [kết thúc]

Step 1: WS-01 -> JUMP-01 | RDP | PASS/FAIL/NOT_TESTED
Evidence: [event ID, host, UTC timestamp, log location]
Step 2: JUMP-01 -> APP-01 | WinRM HTTPS | PASS/FAIL/NOT_TESTED
Evidence: [session, command benign, endpoint/identity/network log]
Negative path: WS-01 -> APP-01 | expected DENY | PASS/FAIL/NOT_TESTED
Evidence: [firewall rule và log, phép thử TCP]

Detected by SOC: [có/không; thời gian phát hiện]
Observed gaps: [thiếu log, ACL quá rộng, rule chưa tương quan...]
Impact: [không phát sinh / mô tả nếu có]
Cleanup: [đăng xuất, đóng phiên, khôi phục thay đổi]
Retest owner/date: [người phụ trách, lịch kiểm thử lại]
~~~

Báo cáo nên đính kèm bằng chứng tối thiểu cần thiết, đã loại bỏ bí mật và thông tin nhạy cảm. Những kết luận về lỗ hổng quyền hoặc khả năng phát hiện cần dựa vào log gốc và cấu hình tại thời điểm thử nghiệm.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `Test-NetConnection` trả về `True` chưa đủ để xác nhận lateral movement?
2. Điều kiện nào khiến một phiên WinRM hợp lệ trở thành dấu hiệu đáng điều tra?
3. Khi WS-01 không vào được APP-01 nhưng JUMP-01 vào được, cần xem thêm chứng cứ nào để chứng minh segmentation hoạt động đúng?
4. Vì sao chỉ ghép các sự kiện có cùng username mà bỏ qua host, phiên và thời gian dễ gây kết luận sai?
5. Nếu SIEM chỉ thu log JUMP-01, bạn sẽ bổ sung nguồn nào trước để tái dựng bước truy cập APP-01?

**Gợi ý trả lời:** (1) TCP chỉ phản ánh khả năng kết nối; cần xác thực và bằng chứng trên máy đích. (2) Nguồn, danh tính, giờ, quyền hoặc đích khác baseline/chính sách. (3) Rule firewall, deny log, DNS/service availability và log đích. (4) Tài khoản có thể được dùng đồng thời ở nhiều máy, còn ID phiên thường chỉ có phạm vi cục bộ. (5) Ưu tiên Security/WinRM/EDR trên APP-01 rồi tương quan với log định danh và firewall.

## 14. Ghi nhớ khi áp dụng thực tế

Lateral movement là vấn đề của **quan hệ tin cậy giữa danh tính, hệ thống và mạng**. Một bài mô phỏng tốt cần chứng minh từng bước trong đường đi, xác nhận những đường cần chặn, kiểm tra SOC có nhìn được toàn bộ chuỗi, và chuyển các phát hiện thành thay đổi cụ thể về quyền, phân đoạn, hardening và telemetry. Hiệu quả phòng thủ đến từ việc giảm đường truy cập ngoài nhu cầu và tăng chất lượng phát hiện, chứ không chỉ chặn một giao thức đơn lẻ.
