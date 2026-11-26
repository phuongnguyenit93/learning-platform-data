Bạn sẽ xác định phạm vi bảo vệ của một nền tảng chạy ứng dụng gồm máy chủ, mạng, lưu trữ, container và cloud như thế nào?
Những tài sản, ranh giới tin cậy và đường tấn công nào cần được lập bản đồ trước khi thiết kế chương trình platform security?
Bạn sẽ áp dụng nguyên tắc least privilege cho tài khoản người dùng, tài khoản dịch vụ và tiến trình hệ thống như thế nào?
Hardening một máy chủ mới cần bắt đầu từ baseline nào, và bạn sẽ điều chỉnh baseline theo vai trò workload ra sao?
Bạn sẽ đánh giá và giảm attack surface của một máy chủ có nhiều dịch vụ, cổng mạng và gói phần mềm được cài sẵn như thế nào?
Secure Boot, measured boot và TPM hỗ trợ bảo vệ tính toàn vẹn của chuỗi khởi động ra sao?
Bạn sẽ quản lý firmware, BIOS/UEFI và cấu hình phần cứng để giảm nguy cơ can thiệp trước khi hệ điều hành khởi chạy như thế nào?
Những rủi ro nào phát sinh khi kernel hoặc driver chạy với đặc quyền cao, và quy trình cập nhật chúng nên được kiểm soát ra sao?
Bạn sẽ quyết định module kernel, service và daemon nào cần tắt hoặc giới hạn trên một máy chủ production như thế nào?
Linux capabilities giúp phân tách đặc quyền của tiến trình ra sao, và khi nào việc cấp CAP_SYS_ADMIN tạo ra rủi ro lớn?
SELinux, AppArmor hoặc cơ chế mandatory access control khác bổ sung điều gì so với quyền sở hữu và permission truyền thống?
Bạn sẽ xây dựng chính sách phân quyền file, thư mục, socket và thiết bị để ngăn tiến trình không liên quan truy cập chéo như thế nào?
Quản lý sudo, administrator và tài khoản break-glass cần những kiểm soát nào để vừa hỗ trợ vận hành khẩn cấp vừa bảo đảm truy vết?
Bạn sẽ bảo vệ thông tin xác thực cục bộ, SSH key và cơ chế đăng nhập quản trị trên máy chủ như thế nào?
Những biện pháp nào giúp giảm rủi ro brute force, credential theft và lateral movement qua các tài khoản quản trị hạ tầng?
Bạn sẽ cô lập workload bằng process boundary, user namespace, cgroup và namespace của hệ điều hành như thế nào?
Seccomp hoặc syscall filtering có thể giảm bề mặt tấn công của tiến trình ra sao, và bạn sẽ xác định syscall cần cho workload bằng cách nào?
Bạn sẽ kiểm soát tiến trình chạy nền, scheduled task và startup mechanism để phát hiện persistence trái phép như thế nào?
Memory protection như ASLR, DEP/NX và control-flow protection góp phần giảm khả năng khai thác lỗi phần mềm ra sao?
Bạn sẽ đánh giá rủi ro từ quyền truy cập trực tiếp vào thiết bị, kernel interface và các pseudo-filesystem nhạy cảm như thế nào?
Thiết kế network segmentation giữa management plane, control plane, data plane và workload network cần dựa trên tiêu chí nào?
Bạn sẽ áp dụng firewall rule theo default-deny mà vẫn duy trì khả năng vận hành và quan sát lưu lượng hợp lệ như thế nào?
Network ACL, host firewall và security group khác nhau ở phạm vi thực thi nào, và nên phối hợp chúng ra sao?
Bạn sẽ bảo vệ kênh quản trị từ xa như SSH, RDP hoặc console access bằng xác thực mạnh, giới hạn nguồn và giám sát như thế nào?
Jump host hoặc bastion có vai trò gì trong truy cập quản trị, và làm sao tránh biến nó thành điểm tập trung rủi ro?
DNS, DHCP, NTP và các dịch vụ hạ tầng dùng chung có thể trở thành điểm tấn công hoặc gây sai lệch bảo mật ra sao?
Bạn sẽ phát hiện và xử lý traffic east-west bất thường giữa các workload trong cùng mạng nội bộ như thế nào?
TLS bảo vệ lưu lượng giữa các thành phần nền tảng ra sao, và bạn sẽ quản lý trust store cùng việc xoay vòng chứng thư như thế nào?
Bạn sẽ phân biệt yêu cầu mã hóa in transit, at rest và in use khi thiết kế bảo vệ dữ liệu trên nền tảng như thế nào?
Quản lý khóa mã hóa cho disk, volume, object storage và backup cần những ranh giới quyền hạn nào?
Bạn sẽ thiết kế phân quyền storage để ngăn dữ liệu của workload hoặc tenant này bị truy cập từ workload hoặc tenant khác như thế nào?
Snapshot và backup có thể mở rộng bề mặt rò rỉ dữ liệu ra sao, và cần kiểm soát mã hóa, quyền truy cập cùng thời hạn lưu giữ thế nào?
Bạn sẽ xác minh khả năng khôi phục backup và tính toàn vẹn của dữ liệu sau restore bằng quy trình nào?
Những rủi ro nào xuất hiện từ volume mount, hostPath, shared filesystem và quyền ghi của container?
Container image cần được kiểm tra nguồn gốc, chữ ký, dependency và lỗ hổng trước khi đưa vào môi trường chạy như thế nào?
Bạn sẽ giảm rủi ro từ container chạy privileged, dùng host network hoặc mount Docker/container runtime socket như thế nào?
Rootless container, user namespace và non-root execution tạo thêm lớp cô lập nào, và giới hạn thực tế của chúng là gì?
Bạn sẽ thiết kế seccomp, AppArmor/SELinux và Linux capabilities cho container theo nguyên tắc tối thiểu như thế nào?
Ranh giới bảo mật giữa container và host khác gì ranh giới giữa các máy ảo, và các tình huống nào cần mức cô lập mạnh hơn?
Hypervisor, virtual machine monitor và firmware của máy chủ ảo hóa cần được harden và giám sát theo cách nào?
Bạn sẽ đánh giá rủi ro khi nhiều workload không cùng mức tin cậy chia sẻ một node hoặc một cụm compute như thế nào?
Trong Kubernetes hoặc nền tảng điều phối tương tự, bạn sẽ bảo vệ control plane, node, admission path và workload identity ra sao?
RBAC của nền tảng điều phối cần được thiết kế thế nào để hạn chế quyền cluster-admin và quyền truy cập secret?
Network policy giữa các workload cần thể hiện nguyên tắc least privilege và kiểm soát ingress/egress như thế nào?
Bạn sẽ quản lý secret được workload sử dụng để tránh hard-code, lộ qua environment, image layer hoặc log như thế nào?
Cloud shared responsibility model thay đổi trách nhiệm bảo vệ giữa nhà cung cấp cloud và đội vận hành workload ra sao?
Bạn sẽ thiết kế cloud IAM role, policy và service identity để tránh quyền wildcard hoặc quyền quản trị dài hạn như thế nào?
Metadata service của máy ảo cloud có thể bị khai thác để lấy credential ra sao, và những kiểm soát nào giúp giảm rủi ro đó?
Bạn sẽ bảo vệ cloud storage bucket, snapshot, image registry và control-plane API khỏi cấu hình public hoặc quyền truy cập quá rộng như thế nào?
Private endpoint, routing, egress control và service endpoint giúp giảm rủi ro truy cập cloud service từ mạng không tin cậy ra sao?
Bạn sẽ phân tách tài khoản, subscription, project hoặc cloud environment để cô lập production khỏi development và sandbox như thế nào?
Những rủi ro nào phát sinh từ cloud-init, startup script, instance template và image customization, và cách kiểm soát thay đổi là gì?
Bạn sẽ quản lý bản vá cho kernel, hệ điều hành, firmware, hypervisor và agent nền tảng theo mức độ nghiêm trọng và khả năng gián đoạn ra sao?
Quy trình vulnerability management cần kết hợp asset inventory, scanning, risk prioritization, remediation và exception như thế nào?
Bạn sẽ đánh giá một lỗ hổng có điểm CVSS cao nhưng không thể khai thác trong kiến trúc hiện tại so với lỗ hổng điểm thấp nhưng đang bị khai thác thực tế ra sao?
Configuration drift xảy ra khi nào, và bạn sẽ phát hiện, đối chiếu baseline cùng tự động khôi phục cấu hình an toàn như thế nào?
Bạn sẽ sử dụng infrastructure as code và configuration management để bảo đảm cấu hình nền tảng có thể kiểm tra, tái lập và review ra sao?
Những thay đổi nào trên máy chủ, firewall, IAM, storage và cluster cần approval, audit trail hoặc kiểm soát triển khai riêng?
Bạn sẽ quản lý ngoại lệ khỏi security baseline sao cho có chủ sở hữu, lý do, thời hạn và biện pháp giảm thiểu rõ ràng như thế nào?
Logging ở lớp hệ điều hành, mạng, container, cloud control plane và storage cần được tập trung và đồng bộ thời gian ra sao?
Những tín hiệu nào giúp phát hiện privilege escalation, persistence, credential abuse, crypto-mining hoặc hành vi truy cập dữ liệu bất thường?
Bạn sẽ thiết kế giám sát tính toàn vẹn file hệ thống, cấu hình nhạy cảm và binary nền tảng để nhận diện thay đổi trái phép như thế nào?
EDR, host intrusion detection và runtime threat detection bổ sung cho vulnerability scanning và configuration compliance ra sao?
Khi một node nền tảng bị nghi xâm nhập, bạn sẽ cô lập node, bảo toàn bằng chứng và duy trì dịch vụ như thế nào?
Quy trình ứng phó sự cố platform security cần phối hợp đội hệ điều hành, mạng, cloud, lưu trữ và ứng dụng theo trách nhiệm nào?
Bạn sẽ đánh giá mức độ ảnh hưởng và phạm vi lan truyền khi credential quản trị hoặc control-plane token bị lộ như thế nào?
Những tiêu chí nào quyết định việc rebuild máy chủ từ image sạch thay vì cố gắng làm sạch hệ thống đã bị xâm nhập?
Bạn sẽ kiểm thử hiệu quả hardening bằng benchmark, attack simulation, penetration test và continuous compliance như thế nào?
Các chỉ số nào phản ánh chất lượng vận hành platform security, chẳng hạn độ phủ inventory, patch latency, drift, quyền đặc quyền và thời gian xử lý cảnh báo?
Bạn sẽ xây dựng quy trình onboarding và decommission hạ tầng để thu hồi identity, secret, certificate, volume và quyền truy cập còn sót lại như thế nào?
Trong môi trường hybrid và multi-cloud, bạn sẽ duy trì baseline bảo mật nhất quán mà vẫn đáp ứng khác biệt về dịch vụ và mô hình trách nhiệm ra sao?
Bạn sẽ cân bằng giữa hardening nghiêm ngặt, tính sẵn sàng, hiệu năng và khả năng khôi phục khi thiết kế nền tảng cho workload trọng yếu như thế nào?
