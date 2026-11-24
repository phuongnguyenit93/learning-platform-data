# Thu thập bằng chứng và cô lập máy nghi bị xâm nhập

Khi một máy ảo có dấu hiệu bị xâm nhập, đội vận hành cần vừa hạn chế khả năng kẻ tấn công tiếp tục hoạt động, vừa giữ lại dữ liệu đủ tin cậy để xác định chuyện gì đã xảy ra. Nếu tắt máy hoặc xóa tài nguyên quá sớm, dữ liệu trong RAM, kết nối mạng đang mở và một số dấu vết tạm thời có thể mất. Nếu để máy tiếp tục kết nối bình thường, kẻ tấn công có thể xóa log, đánh cắp thêm dữ liệu hoặc di chuyển sang workload khác.

Ứng phó sự cố vì vậy cần phối hợp giữa **bảo toàn bằng chứng**, **cô lập có kiểm soát**, **điều tra**, **loại bỏ nguyên nhân** và **khôi phục dịch vụ**. Quyết định cụ thể phụ thuộc mức độ ảnh hưởng, yêu cầu nghiệp vụ, khả năng của nền tảng cloud và quy trình pháp lý của tổ chức. Bài học này tập trung vào máy ảo và workload compute, đồng thời áp dụng được cho instance chạy ứng dụng, worker và máy chủ dữ liệu.

## 1. Nhận diện dấu hiệu máy có thể bị xâm nhập

Một cảnh báo đơn lẻ chưa đủ để kết luận máy đã bị xâm nhập. Tuy nhiên, một số dấu hiệu cần được xem xét và đối chiếu nhanh:

- Đăng nhập thành công từ tài khoản, địa chỉ hoặc thời điểm bất thường; xuất hiện tài khoản quản trị hoặc khóa SSH mới.
- Tiến trình lạ, tiến trình chạy dưới quyền cao, binary mới trong thư mục tạm hoặc lệnh được thực thi ngoài lịch triển khai.
- CPU, RAM, network throughput hoặc số kết nối tăng bất thường mà không giải thích được bằng tải nghiệp vụ.
- Kết nối outbound tới địa chỉ, domain hoặc cổng không thuộc danh sách dịch vụ đã biết.
- Log bị xóa, audit bị tắt, agent bảo mật ngừng hoạt động hoặc cấu hình firewall thay đổi không có ticket.
- File ứng dụng, scheduled task, cron job, service hoặc startup script bị thay đổi ngoài quy trình phát hành.
- Cảnh báo từ EDR, antivirus, vulnerability detection, cloud security posture hoặc hệ thống phát hiện hành vi.
- Secret, access key hoặc token được sử dụng từ nguồn không mong đợi; xuất hiện hành động cloud control plane bất thường.

Hãy kiểm tra cả guest OS lẫn control plane. Máy có thể vẫn chạy ứng dụng bình thường trong khi một credential bị đánh cắp đã được dùng để tạo snapshot, sửa security group, thay đổi IAM role hoặc khởi tạo instance khác. Ngược lại, CPU tăng cao có thể chỉ do batch job hoặc traffic đột biến. Ghi nhận cảnh báo, thời điểm, tài nguyên và nguồn phát hiện trước khi thay đổi trạng thái máy.

## 2. Mục tiêu và thứ tự ưu tiên khi ứng phó

Khi xác nhận hoặc nghi ngờ hợp lý một máy bị xâm nhập, mục tiêu thường là:

1. Bảo vệ con người, dữ liệu nhạy cảm và các hệ thống quan trọng.
2. Ngăn hoạt động độc hại tiếp tục hoặc lan sang tài nguyên khác.
3. Giữ lại bằng chứng có giá trị điều tra và đáp ứng yêu cầu kiểm toán.
4. Xác định phạm vi ảnh hưởng, tài khoản và tài nguyên liên quan.
5. Loại bỏ quyền truy cập trái phép, lỗ hổng hoặc cơ chế duy trì hiện diện.
6. Khôi phục dịch vụ từ trạng thái đáng tin cậy và theo dõi tái xâm nhập.

Không phải mọi sự cố đều có cùng thứ tự thao tác. Nếu máy đang mã hóa dữ liệu, phát tán mã độc hoặc truy cập hệ thống trọng yếu, cô lập ngay có thể quan trọng hơn thu thập đầy đủ dữ liệu volatile. Nếu máy là nguồn bằng chứng duy nhất cho một sự cố nghiêm trọng và hiện chưa gây thêm thiệt hại, đội ứng phó có thể thu thập một số dữ liệu trong RAM trước khi cô lập hoàn toàn. Quyết định phải do người có trách nhiệm ứng phó đưa ra và được ghi lại.

Một nguyên tắc quan trọng là không tự ý xóa, format, terminate hoặc rebuild máy nghi bị xâm nhập trước khi đánh giá yêu cầu bảo toàn bằng chứng. Khi cần hành động khẩn cấp để ngăn thiệt hại, hãy ghi rõ lý do, người quyết định, thời điểm và tác động có thể có tới bằng chứng.

## 3. Chuẩn bị trước khi xảy ra sự cố

Việc thu thập bằng chứng sẽ chậm và dễ sai nếu tổ chức chỉ bắt đầu chuẩn bị sau khi có cảnh báo. Mỗi môi trường compute nên có sẵn quy trình, quyền truy cập và công cụ cần thiết.

Những nội dung nên chuẩn bị:

- Danh sách liên hệ của incident commander, đội cloud/platform, security, ứng dụng, pháp chế và chủ sở hữu dữ liệu.
- Quyền khẩn cấp có kiểm soát để đọc log, cô lập NIC/security group, tạo snapshot và truy cập console.
- Quy trình cấp quyền tạm thời theo least privilege; tài khoản ứng phó cần MFA và audit.
- Cloud audit log, network flow log, DNS log, load balancer log, EDR và log guest được bật, đồng bộ thời gian và chuyển tới nơi lưu trữ tập trung.
- Quy tắc lưu giữ log, snapshot, disk image, memory capture và bằng chứng có thể liên quan đến pháp lý.
- Khu vực lưu bằng chứng riêng, mã hóa, giới hạn người truy cập, bật versioning hoặc immutable retention khi phù hợp.
- Image sạch, quy trình tạo máy thay thế và cách khôi phục dữ liệu đã xác minh.
- Runbook cô lập theo từng nền tảng và cách kiểm tra tác động tới các workload phụ thuộc.

Thực hiện diễn tập định kỳ để xác nhận đội ứng phó thực sự có thể tìm đúng instance, tạo snapshot, lấy log và cô lập mạng. Một quyền được ghi trong tài liệu nhưng chưa từng thử có thể không hoạt động khi cần.

## 4. Xác định tài nguyên và mở hồ sơ sự cố

Trước khi thay đổi, xác định chính xác tài nguyên đang bị nghi ngờ. Tên máy trong hệ điều hành có thể khác tên instance trong cloud; IP có thể đã thay đổi hoặc được dùng lại. Nên đối chiếu nhiều định danh.

| Thông tin | Vì sao cần ghi nhận |
|---|---|
| Cloud account/subscription/project và region | Xác định phạm vi quản lý và nơi lưu tài nguyên |
| Instance/resource ID | Định danh ổn định hơn hostname hoặc IP |
| Hostname, private/public IP, NIC ID và MAC | Liên hệ dấu vết guest với tài nguyên mạng |
| Image ID, loại máy, zone và thời điểm tạo | Xác định nguồn gốc và cấu hình ban đầu |
| Disk/volume ID, snapshot và encryption key | Biết dữ liệu nằm ở đâu và cách bảo toàn |
| IAM role/service identity và security group/NSG | Xác định quyền và đường giao tiếp của máy |
| Ứng dụng, owner, môi trường và mức độ quan trọng | Đánh giá ảnh hưởng nghiệp vụ |
| Alert ID, thời điểm phát hiện và người báo | Liên kết bằng chứng với nguồn phát hiện |

Mở một hồ sơ sự cố với mã định danh riêng. Ghi thời gian theo UTC hoặc lưu rõ múi giờ và độ lệch. Đồng hồ guest có thể sai; vì vậy, giữ cả timestamp từ cloud control plane và timestamp gốc trong log, sau đó ghi nhận chênh lệch khi xây dựng timeline.

Không chỉ điều tra máy được cảnh báo đầu tiên. Xác định những tài nguyên có cùng IAM role, subnet, security group, image, secret, deployment pipeline hoặc kết nối mạng. Kẻ tấn công có thể đã dùng máy đầu tiên làm điểm trung chuyển sang các máy khác.

## 5. Bảo toàn bằng chứng volatile trước khi tắt máy

**Bằng chứng volatile** là dữ liệu có thể biến mất khi máy tắt, reboot hoặc tiến trình kết thúc. Một số ví dụ:

- Nội dung RAM, tiến trình và thread đang chạy.
- Kết nối TCP/UDP, socket, bảng định tuyến và trạng thái firewall trong guest.
- Process tree, command line, biến môi trường và module đang nạp.
- Người dùng đang đăng nhập, session và thông tin xác thực tạm thời trong bộ nhớ.
- Dữ liệu trong RAM của ứng dụng, queue hoặc cache chưa ghi xuống đĩa.
- Thông tin tạm thời về file đang mở và hoạt động hệ thống.

Nếu tổ chức có công cụ memory acquisition phù hợp và được phép sử dụng, có thể cân nhắc thu thập RAM trước khi tắt hoặc cô lập hoàn toàn máy. Việc này cần được thực hiện bởi người có chuyên môn, theo quy trình đã kiểm thử. Công cụ thu thập có thể làm thay đổi một phần bộ nhớ và trạng thái hệ thống; phải ghi rõ công cụ, phiên bản, lệnh, thời điểm bắt đầu/kết thúc và ảnh hưởng đã biết.

Trong môi trường máy ảo cloud, khách hàng thường không có quyền truy cập trực tiếp bộ nhớ vật lý hoặc hypervisor. Một số nhà cung cấp không hỗ trợ memory snapshot hay memory dump cho instance. Không giả định thao tác tạo disk snapshot sẽ lưu RAM; disk snapshot chỉ bảo toàn dữ liệu trên volume theo cơ chế của dịch vụ lưu trữ. Nếu memory acquisition không khả thi, ghi nhận hạn chế này và ưu tiên bảo toàn các nguồn log, disk và control plane còn lại.

Nếu máy đang gây thiệt hại nghiêm trọng, không trì hoãn cô lập chỉ để cố lấy mọi dữ liệu volatile. Hãy ưu tiên ngăn thiệt hại theo playbook, ghi nhận dữ liệu nào đã mất hoặc không thể thu thập và lý do quyết định.

## 6. Thu thập thông tin trạng thái trước khi cô lập

Nếu tình huống cho phép và việc truy cập không làm tăng rủi ro, thu thập nhanh các thông tin trạng thái có giá trị. Có thể dùng EDR, cloud guest agent hoặc công cụ điều tra đã được phê duyệt.

Trên Linux, những nguồn thông tin có thể gồm:

```bash
date -u
hostnamectl
who -a
ps auxfww
ss -antup
ip address
ip route
sudo lsof -nP
sudo journalctl --since "2 hours ago" --utc
```

Các lệnh này có thể cho biết thời gian, hostname, session, process tree, kết nối, route, file đang mở và log gần đây. Tùy distribution, một số lệnh cần package hoặc quyền cao. Không cài thêm công cụ tùy tiện lên máy nghi bị xâm nhập nếu có thể thu thập từ agent đã được chuẩn bị hoặc disk image.

Trên Windows, có thể thu thập thông tin tương đương bằng công cụ được phê duyệt, ví dụ:

```powershell
(Get-Date).ToUniversalTime()
hostname
quser
Get-Process | Sort-Object CPU -Descending
Get-NetTCPConnection
Get-NetRoute
Get-NetIPAddress
Get-WinEvent -LogName Security -MaxEvents 200
```

Các truy vấn có thể tạo thêm log hoặc tác động nhẹ tới hệ thống. Lưu output vào nơi lưu bằng chứng có quyền hạn chế, không ghi đè log gốc và không lưu credential. Nếu nghi ngờ attacker đang theo dõi session hoặc có quyền quản trị sâu, ưu tiên dùng telemetry ngoài máy như EDR hoặc cloud control plane thay vì đăng nhập tương tác.

## 7. Bảo toàn bằng chứng trên đĩa và snapshot

Disk evidence thường gồm boot volume, data volume, volume tạm có liên quan và snapshot có sẵn. Trước khi tạo snapshot, xác định yêu cầu nhất quán dữ liệu và tác động của thao tác đối với workload.

Một số nguyên tắc:

- Ghi nhận volume ID, kích thước, loại volume, encryption key, attachment và thời điểm snapshot.
- Tạo snapshot theo quy trình của nhà cung cấp và lưu trong tài khoản hoặc khu vực điều tra được kiểm soát.
- Bảo vệ snapshot bằng mã hóa, quyền truy cập tối thiểu và chính sách retention phù hợp.
- Ghi rõ snapshot được tạo khi máy đang chạy hay đã dừng, có quiesce filesystem/application hay không.
- Không gắn bản gốc vào máy điều tra theo chế độ ghi nếu chưa có quy trình bảo toàn phù hợp.
- Tạo bản sao phục vụ phân tích và giữ một bản gốc chỉ đọc hoặc được bảo vệ khỏi thay đổi.

Snapshot được tạo từ volume đang hoạt động thường chỉ đảm bảo một mức nhất quán phụ thuộc dịch vụ lưu trữ. Nếu ứng dụng đang ghi dữ liệu, snapshot có thể tương tự trạng thái sau sự cố mất điện (crash-consistent), không nhất thiết nhất quán ở cấp transaction. Nếu cần application-consistent snapshot, dùng cơ chế quiesce hoặc backup agent được hỗ trợ, nhưng cân nhắc liệu việc quiesce có làm thay đổi trạng thái cần điều tra hay không.

Snapshot đĩa không bảo toàn RAM, kết nối mạng đang mở hoặc toàn bộ trạng thái tiến trình. Nếu máy có ephemeral/instance store, dữ liệu trên đó có thể bị mất khi stop, terminate hoặc thao tác vòng đời nhất định. Kiểm tra tài liệu của loại instance trước khi thay đổi power state.

## 8. Thu thập log từ control plane và các dịch vụ mạng

Guest log có thể bị xóa hoặc sửa nếu attacker đã có quyền cao. Vì vậy, cần lấy dữ liệu độc lập từ cloud control plane và các dịch vụ mạng. Những nguồn thường hữu ích gồm:

| Nguồn bằng chứng | Nội dung có thể làm rõ |
|---|---|
| Cloud audit/activity log | Ai đã tạo, start/stop, resize, attach disk, thay đổi NIC, security group, IAM hoặc snapshot |
| Identity/IAM log | Đăng nhập, MFA, token, assume role, thay đổi quyền và hành vi credential bất thường |
| VPC/VNet flow log | Luồng nguồn/đích, port, protocol, thời điểm và trạng thái accept/reject theo khả năng dịch vụ |
| DNS resolver log | Domain được truy vấn, máy nguồn và thời điểm |
| Load balancer/reverse proxy log | Client, request, backend, response code và latency |
| WAF/firewall/IDS log | Request hoặc kết nối bị phát hiện, cho phép hay chặn |
| EDR/endpoint telemetry | Process, file, persistence, alert và hành động response |
| Centralized OS/application log | Đăng nhập, service, ứng dụng, lỗi và thay đổi cấu hình |
| CI/CD và artifact registry | Phiên bản triển khai, người phê duyệt, artifact và thay đổi pipeline |

Kiểm tra phạm vi thời gian đủ rộng trước và sau thời điểm phát hiện. Một sự kiện bất thường có thể bắt đầu nhiều ngày trước khi alert xuất hiện. Lưu dữ liệu ở định dạng gốc nếu có thể, giữ metadata và không chỉ lưu ảnh chụp màn hình.

Flow log thường không chứa payload và không nhất thiết ghi mọi packet. Nó hữu ích để phân tích metadata kết nối nhưng không thay thế packet capture hoặc log ứng dụng. Cũng cần hiểu độ trễ ingest, thời gian lưu và cách nền tảng biểu diễn trạng thái flow để không kết luận sai từ dữ liệu chưa đầy đủ.

## 9. Cô lập máy ảo ở lớp mạng

Cô lập mạng nhằm ngăn máy nghi bị xâm nhập giao tiếp với hệ thống khác hoặc Internet trong khi vẫn giữ được khả năng điều tra cần thiết. Cách triển khai phụ thuộc nền tảng, nhưng thường có một số lựa chọn:

- Thay security group/NSG bằng policy quarantine chỉ cho phép các kết nối phục vụ điều tra.
- Cập nhật firewall hoặc network ACL để chặn lưu lượng tới các mạng nhạy cảm và Internet.
- Chuyển NIC hoặc workload sang subnet cách ly nếu nền tảng và kiến trúc hỗ trợ mà không phá hủy bằng chứng.
- Áp dụng rule ở firewall trung tâm, transit gateway hoặc network virtual appliance.
- Chặn credential và quyền cloud có thể bị lạm dụng để tạo thêm đường truy cập.

Một policy quarantine nên xác định rõ:

1. Chặn inbound từ người dùng và workload thông thường.
2. Chặn outbound tới Internet, mạng nội bộ và dịch vụ khác, trừ các luồng được phê duyệt.
3. Cho phép kênh quản trị điều tra có kiểm soát nếu cần, chẳng hạn từ jump host hoặc forensic workstation chuyên dụng.
4. Cho phép gửi log hoặc telemetry tới nơi lưu bằng chứng nếu điều đó an toàn và cần thiết.
5. Ghi log các lần kết nối bị chặn và thay đổi policy.

Không dùng một security group “deny all” một cách máy móc nếu thao tác đó làm mất kênh quản trị, EDR hoặc khả năng thu thập log cần thiết. Mặt khác, không giữ một đường outbound rộng chỉ để tiện truy cập Internet. Thiết kế quarantine cần được chuẩn bị và thử nghiệm trước.

Lưu ý rằng hành vi áp dụng security group, NSG, ACL và firewall khác nhau giữa nền tảng. Rule stateful có thể xử lý kết nối đang tồn tại khác với rule stateless; một số thay đổi cần thời gian lan truyền. Sau khi cô lập, kiểm tra từ nguồn độc lập rằng kết nối không mong muốn thực sự bị chặn.

## 10. Khi nào nên stop hoặc shutdown máy?

Stop hoặc shutdown có thể ngăn tiến trình độc hại tiếp tục chạy, nhưng cũng làm mất dữ liệu volatile. Dừng máy còn có thể ảnh hưởng tới dữ liệu trên ephemeral storage hoặc dịch vụ phụ thuộc. Vì vậy, quyết định cần dựa trên mục tiêu containment và yêu cầu điều tra.

| Lựa chọn | Lợi ích | Tác động cần cân nhắc |
|---|---|---|
| Cô lập mạng, giữ máy chạy | Giữ được RAM và trạng thái tiến trình để điều tra; giảm giao tiếp ra ngoài | Malware vẫn có thể chạy cục bộ, phá hoại dữ liệu hoặc chờ lệnh |
| Graceful shutdown sau khi thu thập | Cho ứng dụng dừng có kiểm soát và giảm thay đổi dữ liệu | Tiến trình kết thúc, RAM mất; shutdown script có thể ghi thêm dữ liệu |
| Hard stop/force power off | Ngăn CPU tiếp tục thực thi nhanh | Mất dữ liệu volatile, filesystem có thể không nhất quán |
| Terminate/delete instance | Loại bỏ máy khỏi hạ tầng nhanh | Có thể phá hủy bằng chứng, ephemeral data và khả năng tái hiện |

Nếu máy đang phát tán mã độc, mã hóa volume, đánh cắp dữ liệu hoặc điều khiển tài nguyên khác, cô lập mạng và/hoặc dừng máy khẩn cấp có thể là lựa chọn cần thiết. Nếu mục tiêu là điều tra pháp chứng và chưa có nguy cơ lan rộng tức thời, hãy cân nhắc thu thập volatile data và snapshot theo runbook trước.

Không xóa instance chỉ vì đã tạo snapshot. Xác minh snapshot hoàn tất, metadata được lưu, bản sao có thể truy cập và yêu cầu bảo toàn đã được đáp ứng trước khi quyết định thay đổi vòng đời máy.

## 11. Bảo vệ danh tính và ngăn kẻ tấn công quay lại

Máy bị xâm nhập có thể chứa credential đã bị đọc hoặc dùng để truy cập tài nguyên khác. Cô lập mạng của một instance không tự thu hồi credential bị đánh cắp.

Các bước thường cần đánh giá:

- Vô hiệu hóa, rotate hoặc thu hồi access key, token, certificate và mật khẩu bị nghi lộ.
- Xem xét IAM role/service account gắn với instance; giảm quyền hoặc tạm thu hồi quyền không cần thiết theo quy trình khẩn cấp.
- Thu hồi session hoặc token đang hoạt động nếu nền tảng hỗ trợ.
- Kiểm tra tài khoản quản trị, SSH authorized keys, Windows credentials, scheduled task và cơ chế persistence.
- Đổi secret dùng chung mà máy có thể truy cập, bao gồm database credential, API token và khóa triển khai.
- Thực hiện rotate từ máy quản trị sạch, có MFA; không dùng lại session trên máy nghi bị xâm nhập.
- Kiểm tra audit log để tìm hành động đã được thực hiện bằng danh tính bị lộ.

Thay đổi IAM có thể làm gián đoạn workload khác dùng chung role hoặc secret. Xác định phạm vi phụ thuộc trước khi thu hồi quyền, nhưng ưu tiên chặn quyền đang bị lạm dụng. Ghi lại giá trị định danh của credential và thời điểm thu hồi; không ghi nội dung secret vào hồ sơ sự cố.

## 12. Quy trình thu thập và bảo quản bằng chứng

Bằng chứng chỉ hữu ích khi người điều tra có thể xác định nguồn gốc, tính toàn vẹn và lịch sử xử lý. Mỗi hiện vật cần có metadata và được quản lý theo chuỗi bàn giao (chain of custody).

Với từng hiện vật, ghi nhận tối thiểu:

- Mã evidence duy nhất.
- Tài nguyên nguồn, account/project, region và resource ID.
- Loại dữ liệu: memory dump, disk snapshot, log export, packet capture hoặc file cụ thể.
- Người thu thập, người chứng kiến nếu quy trình yêu cầu và người tiếp nhận.
- Thời điểm bắt đầu/kết thúc theo UTC, nguồn đồng hồ và sai lệch đã biết.
- Công cụ, phiên bản, lệnh hoặc thao tác đã thực hiện.
- Hash mật mã, thường dùng SHA-256, của file export sau khi thu thập.
- Vị trí lưu, encryption key, quyền truy cập, retention và mọi lần sao chép/chuyển giao.
- Những thay đổi hoặc giới hạn có thể ảnh hưởng tới tính toàn vẹn.

Ví dụ tạo hash cho file evidence sau khi export:

```bash
sha256sum evidence-disk-image.raw
```

Trên Windows:

```powershell
Get-FileHash .\evidence-disk-image.raw -Algorithm SHA256
```

Hash giúp phát hiện nội dung file thay đổi sau thời điểm tính hash. Nó không tự chứng minh dữ liệu ban đầu được thu thập đúng cách hoặc nguồn gốc của file; chain of custody và metadata vẫn cần thiết.

Lưu bản gốc trong kho bằng chứng có quyền ghi hạn chế. Dùng bản sao để phân tích; ghi hash trước và sau khi sao chép. Nếu cần mount disk image, ưu tiên chế độ chỉ đọc và tránh thực thi binary hoặc script từ image nghi nhiễm. Môi trường phân tích nên tách biệt mạng production, có kiểm soát outbound và được giám sát.

## 13. Xây dựng timeline và xác định phạm vi ảnh hưởng

Sau khi thu thập dữ liệu, kết hợp các nguồn để dựng timeline theo UTC. Không dựa vào một log duy nhất. Ví dụ, sự kiện đăng nhập trong guest có thể được đối chiếu với identity log, thay đổi security group trong control plane, flow log và request tới load balancer.

Timeline có thể gồm:

1. Hoạt động hợp lệ gần nhất trước khi có dấu hiệu bất thường.
2. Lần đăng nhập, thực thi lệnh hoặc thay đổi cấu hình đáng ngờ đầu tiên.
3. Thời điểm credential hoặc quyền bị lạm dụng.
4. Kết nối outbound, truy cập dữ liệu hoặc di chuyển sang tài nguyên khác.
5. Thời điểm cảnh báo được tạo và người vận hành tiếp nhận.
6. Thời điểm bắt đầu containment, snapshot và thu hồi credential.
7. Thời điểm xác nhận hoạt động độc hại dừng lại.

Đánh giá phạm vi ảnh hưởng theo các câu hỏi:

- Những tài khoản, khóa, token hoặc role nào đã được sử dụng trên máy?
- Máy có truy cập secret, database, object storage, queue hoặc control plane nào?
- Có instance, NIC, disk, snapshot, security group hoặc IAM policy mới được tạo không?
- Có dấu hiệu truy cập ngang trong subnet hoặc qua peering/VPN không?
- Dữ liệu nào có thể đã bị đọc, sửa, xóa hoặc đưa ra ngoài?
- Có máy khác dùng cùng image, credential, deployment artifact hoặc cấu hình dễ bị khai thác không?
- Log nào thiếu, bị xóa hoặc không được bật trong khoảng thời gian liên quan?

Phân biệt điều đã xác minh với giả thuyết. Ví dụ, flow log cho thấy máy gửi dữ liệu tới một địa chỉ IP nhưng chưa chứng minh payload là dữ liệu nhạy cảm. Ghi mức độ tin cậy và bằng chứng hỗ trợ cho từng kết luận.

## 14. Điều tra trên bản sao và xử lý nguyên nhân gốc

Khi đã bảo toàn bản gốc, tạo bản sao làm việc trong môi trường pháp chứng hoặc sandbox được kiểm soát. Có thể phân tích:

- Log đăng nhập, sudo, SSH, RDP, Windows event và lịch sử service.
- Process, startup item, cron, scheduled task, systemd unit và registry autorun.
- Binary, script, thư viện, package và file mới hoặc bị thay đổi.
- Web shell, persistence mechanism, tài khoản và khóa mới.
- Browser/application cache, shell history và dữ liệu tạm nếu có liên quan.
- Cấu hình mạng, DNS, proxy, firewall và route.
- Secret hoặc token có khả năng bị truy cập, theo quy trình xử lý bí mật.

Không chạy trực tiếp file đáng ngờ trên máy phân tích thông thường. Dùng sandbox, công cụ phân tích phù hợp và quy trình xử lý malware của tổ chức. Nếu cần phân tích sâu, phối hợp chuyên gia incident response hoặc digital forensics.

Sau khi hiểu nguyên nhân, xác định cách loại bỏ: vá lỗ hổng, thu hồi credential, sửa cấu hình IAM/network, loại bỏ persistence, thay image, cập nhật ứng dụng hoặc thay đổi quy trình triển khai. Không chỉ xóa file malware mà bỏ qua điểm xâm nhập ban đầu; nếu lỗ hổng hoặc credential vẫn còn, máy thay thế có thể bị xâm nhập lại.

## 15. Khôi phục workload từ trạng thái đáng tin cậy

Trong nhiều trường hợp, cách khôi phục an toàn là tạo máy mới từ golden image đã kiểm duyệt, cài bản vá và triển khai artifact ứng dụng đã xác minh. Không nên mặc định máy đã bị xâm nhập có thể trở lại trạng thái tin cậy chỉ bằng cách xóa tiến trình lạ.

Quy trình khôi phục có thể gồm:

1. Xác nhận nguyên nhân gốc đã được xử lý hoặc có biện pháp ngăn tái khai thác.
2. Tạo image hoặc instance mới từ nguồn tin cậy và baseline hiện hành.
3. Cấp danh tính workload mới với quyền tối thiểu; tạo lại host key và agent identity.
4. Cài artifact đã xác minh chữ ký/hash và cấu hình sạch.
5. Khôi phục dữ liệu từ backup đã kiểm tra, quét và xác định thời điểm sạch.
6. Rotate secret và cập nhật endpoint phụ thuộc.
7. Kiểm thử health, security control, logging, monitoring và kết nối mạng.
8. Đưa traffic trở lại theo từng đợt, theo dõi cảnh báo và dấu hiệu tái xâm nhập.
9. Giữ bằng chứng và máy gốc theo thời hạn điều tra hoặc yêu cầu pháp lý.

Backup có thể đã chứa malware, web shell, credential hoặc dữ liệu bị sửa trước thời điểm phát hiện. Trước khi restore, kiểm tra tính toàn vẹn, thời điểm backup, nội dung và khả năng tái tạo lỗ hổng. Không ghi đè bằng chứng gốc bằng dữ liệu khôi phục.

## 16. Ví dụ tình huống: API server có kết nối outbound bất thường

Giả sử EDR phát hiện một tiến trình lạ trên máy `orders-api-07` và flow log cho thấy máy có kết nối outbound tới một địa chỉ không thuộc danh sách dịch vụ. API vẫn đang phục vụ request bình thường.

Một cách xử lý có kiểm soát:

1. Mở incident, ghi resource ID, NIC, IP, IAM role, volume ID, image ID, alert ID và thời điểm.
2. Đối chiếu cloud audit log và EDR để xác định hành động gần thời điểm cảnh báo.
3. Nếu rủi ro cho phép, thu thập process tree, network connections, logged-on users và dữ liệu volatile theo runbook.
4. Export log guest và log ngoài máy như flow log, DNS, load balancer, identity và control plane.
5. Tạo snapshot volume theo quy trình bảo toàn, ghi nhận trạng thái nhất quán và encryption metadata.
6. Áp dụng quarantine policy: chặn outbound bất thường và truy cập ngang; chỉ giữ kênh forensic cần thiết nếu đã phê duyệt.
7. Thu hồi hoặc rotate credential có thể bị lộ, đánh giá IAM role và secret mà máy được phép truy cập.
8. Phân tích bản sao disk, đối chiếu timeline và kiểm tra những máy dùng cùng image hoặc credential.
9. Tạo máy thay thế từ image sạch sau khi xử lý nguyên nhân; triển khai artifact đã xác minh và kiểm tra readiness.
10. Theo dõi máy mới, giữ máy gốc trong trạng thái cách ly và hoàn tất hồ sơ bằng chứng.

Nếu phát hiện máy đang đánh cắp dữ liệu hoặc phát tán mã độc, containment cần được thực hiện ngay theo mức độ khẩn cấp; bước thu thập volatile có thể rút ngắn hoặc bỏ qua. Mọi quyết định cần được ghi lại để người điều tra hiểu được dữ liệu nào còn và dữ liệu nào không còn.

## 17. Vai trò, phối hợp và truyền thông sự cố

Ứng phó sự cố compute cần phân định trách nhiệm để tránh nhiều người cùng thay đổi một tài nguyên mà không phối hợp:

| Vai trò | Trách nhiệm điển hình |
|---|---|
| Incident commander | Điều phối ưu tiên, quyết định containment và ghi nhận phê duyệt |
| Cloud/platform engineer | Xác định resource, thu thập control-plane evidence, cô lập network và tạo snapshot |
| Security/IR analyst | Phân tích alert, telemetry, malware, timeline và phạm vi ảnh hưởng |
| Application owner | Đánh giá ảnh hưởng nghiệp vụ, dependency, dữ liệu và readiness khi khôi phục |
| IAM/security administrator | Thu hồi credential, role, session và kiểm tra quyền bị lạm dụng |
| Legal/privacy/compliance | Hướng dẫn yêu cầu bảo toàn, thông báo và thời hạn lưu giữ khi cần |

Chỉ định một người ghi nhật ký thao tác hoặc dùng hệ thống case management để ghi tự động. Cập nhật trạng thái theo dữ kiện đã xác minh, tránh suy đoán về nguyên nhân hoặc phạm vi trước khi có bằng chứng. Chỉ chia sẻ log, disk image hoặc memory dump cho người có quyền và nhu cầu công việc rõ ràng.

## 18. Những sai lầm thường gặp

- **Terminate máy ngay khi có cảnh báo:** có thể mất RAM, ephemeral data và bằng chứng. Đánh giá containment, thu thập volatile nếu phù hợp rồi mới quyết định.
- **Chỉ lấy snapshot ổ đĩa:** snapshot không chứa RAM hoặc kết nối đang mở. Ghi nhận rõ loại bằng chứng đã thu thập.
- **Để máy online để tiện điều tra:** attacker có thể tiếp tục điều khiển hoặc đánh cắp dữ liệu. Dùng quarantine network được chuẩn bị trước.
- **Chặn toàn bộ mạng mà không giữ kênh IR:** có thể mất EDR, log hoặc quyền quản trị. Chỉ giữ các luồng điều tra được phê duyệt và kiểm tra hiệu quả cô lập.
- **Tin hoàn toàn vào log trên guest:** attacker có quyền cao có thể sửa hoặc xóa log. Đối chiếu control plane và telemetry ngoài máy.
- **Mount bản gốc ở chế độ ghi:** có thể thay đổi metadata hoặc nội dung bằng chứng. Giữ bản gốc và phân tích trên bản sao chỉ đọc.
- **Không hash hoặc ghi chain of custody:** khó chứng minh file không bị thay đổi và khó xác định ai đã xử lý.
- **Chỉ xóa malware:** điểm xâm nhập hoặc credential bị lộ vẫn còn. Xử lý nguyên nhân gốc và thay máy từ image tin cậy khi phù hợp.
- **Restore backup mà không kiểm tra:** có thể đưa malware hoặc dữ liệu đã bị sửa trở lại production. Xác minh backup trước khi khôi phục.
- **Không xem xét IAM và secret:** attacker có thể dùng credential đánh cắp từ máy để quay lại qua đường khác. Rotate và kiểm tra quyền liên quan.

## 19. Checklist thu thập bằng chứng và cô lập

- [ ] Đã mở incident và ghi nhận người quyết định, thời điểm, alert cùng resource ID.
- [ ] Đã xác định account/project, region, instance, NIC, volume, IAM role và security policy.
- [ ] Đã đánh giá nguy cơ tiếp tục thiệt hại và quyết định thứ tự volatile collection/containment.
- [ ] Đã thu thập hoặc ghi rõ lý do không thể thu thập RAM và trạng thái tiến trình.
- [ ] Đã export log guest và log độc lập từ cloud audit, IAM, flow, DNS, load balancer, WAF/EDR.
- [ ] Đã tạo snapshot/bản sao theo quy trình, ghi rõ mức nhất quán và encryption metadata.
- [ ] Bằng chứng có mã định danh, timestamp UTC, nguồn, công cụ, người thu thập và hash phù hợp.
- [ ] Bản gốc được bảo vệ; phân tích thực hiện trên bản sao trong môi trường kiểm soát.
- [ ] Máy đã được cô lập và kết nối cần thiết cho IR được giới hạn, kiểm tra từ nguồn độc lập.
- [ ] Credential, token, key và IAM role có nguy cơ bị lộ đã được đánh giá và xử lý.
- [ ] Timeline và phạm vi ảnh hưởng đã đối chiếu nhiều nguồn dữ liệu.
- [ ] Nguyên nhân gốc được xử lý trước khi khôi phục workload.
- [ ] Máy mới được tạo từ image tin cậy; backup và artifact được xác minh trước khi dùng.
- [ ] Có giám sát tăng cường, kế hoạch rollback và thời hạn lưu giữ bằng chứng.

Thu thập bằng chứng và cô lập máy nghi bị xâm nhập là hai hoạt động phải được điều phối cùng nhau. Khi đội vận hành nhận diện đúng tài nguyên, giữ lại dữ liệu volatile và disk/log cần thiết, cô lập bằng policy có kiểm soát, bảo vệ credential và ghi nhận chuỗi bàn giao, tổ chức có thể hạn chế thiệt hại mà vẫn duy trì cơ sở đáng tin cậy để điều tra và khôi phục workload.
